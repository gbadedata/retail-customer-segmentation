"""The loading, cleaning, snapshot features and RFM scoring steps, written in PySpark.

This mirrors load.py, clean.py, features.py and rfm.py rule for rule, so the two
engines can be checked against each other: same rows in each bucket, same
customers at each snapshot, same RFM scores. scripts/spark_parity.py runs that
check on the full 1,067,371-row dataset; tests/test_spark_parity.py runs it on
synthetic data in CI.

Install with: pip install -e ".[spark]" (needs Java 17 or 21).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pyspark.sql import Column, DataFrame, SparkSession, Window
from pyspark.sql import functions as F

from .clean import KEY, RULES
from .config import NON_PRODUCT_CODES, NON_PRODUCT_PATTERN, SETTINGS, Settings
from .load import COLUMNS, FILES, ContractError
from .rfm import SEGMENT_GRID

CID = "Customer ID"
DATE_PATTERN = "d/M/yyyy H:mm"  # day first, as in load.DATE_FORMAT; also accepts unpadded days and hours


def session(app: str = "segments", cores: str = "local[*]") -> SparkSession:
    """A local session on UTC, so day arithmetic never crosses a clock change."""
    return (SparkSession.builder.appName(app).master(cores)
            .config("spark.sql.session.timeZone", "UTC")
            .config("spark.driver.extraJavaOptions", "-Duser.timezone=UTC")
            .config("spark.executor.extraJavaOptions", "-Duser.timezone=UTC")
            .config("spark.sql.shuffle.partitions", "8")
            .config("spark.ui.enabled", "false")
            .getOrCreate())


def _ts(value) -> Column:
    """A timestamp literal parsed the same way as the data (session time zone)."""
    return F.to_timestamp(F.lit(f"{value:%Y-%m-%d %H:%M:%S}"))


# ---------------------------------------------------------------- loading

def validate(df: DataFrame, name: str) -> DataFrame:
    """The schema contract from load.validate, raising ContractError on the same problems."""
    df = df.toDF(*[c.lstrip("﻿") for c in df.columns])  # byte-order mark on the first header
    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        raise ContractError(f"{name}: missing columns {missing}")
    out = (df.withColumn("InvoiceDate", F.try_to_timestamp(F.col("InvoiceDate"), F.lit(DATE_PATTERN)))
             .withColumn("Quantity", F.col("Quantity").try_cast("long"))
             .withColumn("Price", F.col("Price").try_cast("double"))
             .withColumn(CID, F.regexp_replace(F.col(CID), r"\.0$", "")))
    bad = out.select(
        F.sum(F.col("InvoiceDate").isNull().cast("int")).alias("dates"),
        F.sum((F.col("Quantity").isNull() | F.col("Price").isNull()).cast("int")).alias("numbers"),
        F.sum((F.col("Invoice").isNull() | F.col("StockCode").isNull()).cast("int")).alias("keys"),
        F.sum((F.col(CID).isNotNull() & ~F.col(CID).rlike(r"^\d{5}$")).cast("int")).alias("ids"),
    ).first()
    if bad["dates"]:
        raise ContractError(f"{name}: {bad['dates']} dates not in dd/mm/yyyy hh:mm form")
    if bad["numbers"]:
        raise ContractError(f"{name}: {bad['numbers']} non-numeric values in Quantity or Price")
    if bad["keys"]:
        raise ContractError(f"{name}: blank Invoice or StockCode")
    if bad["ids"]:
        raise ContractError(f"{name}: customer IDs are not 5-digit numbers")
    return out.select(*COLUMNS)


def _with_row_numbers(df: DataFrame, source_file: int) -> DataFrame:
    """source_row as in pandas: 0, 1, 2... in file order."""
    w = Window.orderBy("_mid")
    return (df.withColumn("_mid", F.monotonically_increasing_id())
              .withColumn("source_row", F.row_number().over(w) - 1)
              .withColumn("source_file", F.lit(source_file))
              .drop("_mid"))


def load(spark: SparkSession, raw_dir: Path) -> DataFrame:
    frames = []
    for i, name in enumerate(FILES, start=1):
        raw = spark.read.csv(str(raw_dir / name), header=True, inferSchema=False, encoding="UTF-8")
        frames.append(_with_row_numbers(validate(raw, name), i))
    return frames[0].unionByName(frames[1])


def from_pandas(spark: SparkSession, df) -> DataFrame:
    """A pandas frame already through load.validate (for tests and parity checks)."""
    pdf = df[KEY + ["source_file", "source_row"]].copy()
    pdf["Customer ID"] = pdf["Customer ID"].astype(object).where(pdf["Customer ID"].notna(), None)
    pdf["Description"] = pdf["Description"].astype(object).where(pdf["Description"].notna(), None)
    schema = ("Invoice string, StockCode string, Description string, Quantity long, InvoiceDate timestamp, "
              "Price double, `Customer ID` string, Country string, source_file int, source_row long")
    return spark.createDataFrame(pdf, schema=schema)


# ---------------------------------------------------------------- cleaning

@dataclass
class SparkCleanResult:
    purchases: DataFrame
    returns: DataFrame
    quarantine: DataFrame
    rows: DataFrame          # every row with its bucket: purchase, return or a quarantine reason
    log: list[dict]
    reconciliation: dict
    overlap_check: dict


def _key_string() -> Column:
    parts = [F.coalesce(F.col(c).cast("string"), F.lit("<blank>")) for c in KEY]
    return F.concat_ws("␟", *parts)


def _overlap(d: DataFrame) -> tuple[Column, dict]:
    """File-2 rows inside file 1's date range, and a check that they really are copies."""
    span = d.groupBy("source_file").agg(F.min("InvoiceDate").alias("lo"), F.max("InvoiceDate").alias("hi"))
    spans = {r["source_file"]: r for r in span.collect()}
    if 1 not in spans or 2 not in spans:
        return F.lit(False), {"rows": 0, "matched": 0, "unmatched": 0}
    end1, start2 = spans[1]["hi"], spans[2]["lo"]
    flag = (F.col("source_file") == 2) & (F.col("InvoiceDate") <= _ts(end1))
    a = (d.where((F.col("source_file") == 1) & (F.col("InvoiceDate") >= _ts(start2)))
          .groupBy(_key_string().alias("k")).agg(F.count("*").alias("a")))
    b = d.where(flag).groupBy(_key_string().alias("k")).agg(F.count("*").alias("b"))
    rows = d.where(flag).count()
    matched = a.join(b, "k").select(F.sum(F.least("a", "b")).alias("m")).first()["m"] or 0
    return flag, {"rows": int(rows), "matched": int(matched), "unmatched": int(rows - matched),
                  "from": f"{start2:%Y-%m-%d}", "to": f"{end1:%Y-%m-%d}"}


def clean(df: DataFrame) -> SparkCleanResult:
    d = df.withColumn("value", F.col("Quantity") * F.col("Price"))
    is_cancel = F.col("Invoice").startswith("C")
    flag, overlap_check = _overlap(d)
    non_product = F.col("StockCode").isin(sorted(NON_PRODUCT_CODES)) | F.col("StockCode").rlike(
        NON_PRODUCT_PATTERN.pattern)
    bad_qty = (~is_cancel & (F.col("Quantity") <= 0)) | (is_cancel & (F.col("Quantity") >= 0))

    # First rule broken wins, in the order of clean.RULES.
    d = d.withColumn("reason", F.when(flag, "overlap_duplicate")
                                 .when(F.col(CID).isNull(), "missing_customer")
                                 .when(non_product, "non_product")
                                 .when(F.col("Price") <= 0, "bad_price")
                                 .when(bad_qty, "bad_quantity"))
    # Exact duplicates among rows still unassigned: keep the first in file order.
    first = Window.partitionBy(*KEY).orderBy("source_file", "source_row")
    still = d.where(F.col("reason").isNull()).withColumn("_n", F.row_number().over(first))
    still = still.withColumn("reason", F.when(F.col("_n") > 1, "exact_duplicate")).drop("_n")
    d = d.where(F.col("reason").isNotNull()).unionByName(still)

    bucket = F.coalesce(F.col("reason"), F.when(is_cancel, "return").otherwise("purchase"))
    rows = d.withColumn("bucket", bucket).cache()
    ok = F.col("reason").isNull()
    purchases = rows.where(ok & ~is_cancel).drop("reason", "bucket")
    returns = rows.where(ok & is_cancel).drop("reason", "bucket")
    quarantine = rows.where(~ok).drop("bucket")

    agg = {r["bucket"]: r for r in rows.groupBy("bucket").agg(F.count("*").alias("rows"),
                                                              F.sum("value").alias("value")).collect()}
    total = sum(r["rows"] for r in agg.values())
    names = [("purchase", "Kept: product sale to a known customer"),
             ("return", "Kept: cancelled product line from a known customer")] + RULES
    log = []
    for name, desc in names:
        r = agg.get(name)
        n, v = (int(r["rows"]), float(r["value"] or 0.0)) if r else (0, 0.0)
        log.append({"reason": name, "description": desc, "rows": n, "value": v,
                    "share_of_rows": n / total if total else 0.0})
    raw = d.agg(F.count("*").alias("n"), F.sum("value").alias("v")).first()
    accounted = sum(x["value"] for x in log)
    reconciliation = {
        "raw_rows": int(raw["n"]), "accounted_rows": int(sum(x["rows"] for x in log)),
        "raw_value": float(raw["v"]), "accounted_value": accounted,
        "difference": float(raw["v"]) - accounted,
        "balanced": bool(raw["n"] == sum(x["rows"] for x in log) and abs(float(raw["v"]) - accounted) < 0.005),
    }
    return SparkCleanResult(purchases, returns, quarantine, rows, log, reconciliation, overlap_check)


# ---------------------------------------------------------------- features at a snapshot

def _days_between(later: Column, earlier: Column) -> Column:
    """Whole days, floored, as pandas Timedelta.days does for positive gaps."""
    return F.floor((F.unix_timestamp(later) - F.unix_timestamp(earlier)) / 86400).cast("long")


def snapshot(purchases: DataFrame, returns: DataFrame, which: str, s: Settings = SETTINGS) -> tuple[DataFrame, int]:
    """Customer features before the snapshot and outcomes after it, as features.snapshot.

    Returns the base (customers with positive net spend) and the number excluded for
    zero or negative net spend.
    """
    w = s.window(which)
    snap, start, end = _ts(w["snapshot"]), _ts(w["lookback_start"]), _ts(w["horizon_end"])
    date = F.col("InvoiceDate")

    hist = purchases.where(date < snap)
    lb = hist.where(date >= start)
    lb_ret = returns.where((date >= start) & (date < snap))

    g = lb.groupBy(CID).agg(F.countDistinct("Invoice").alias("frequency"), F.sum("value").alias("gross_spend"),
                            F.countDistinct("StockCode").alias("products"))
    ret = lb_ret.groupBy(CID).agg(F.sum("value").alias("returns_value"))
    g = g.join(ret, CID, "left").fillna({"returns_value": 0.0})
    g = g.withColumn("monetary", F.col("gross_spend") + F.col("returns_value"))

    h = hist.join(g.select(CID), CID).groupBy(CID).agg(
        F.min(date).alias("first"), F.max(date).alias("last"),
        F.countDistinct(F.to_date(date)).alias("days"),
        F.min(F.to_date(date)).alias("first_day"), F.max(F.to_date(date)).alias("last_day"))
    g = (g.join(h, CID)
          .withColumn("recency_days", _days_between(snap, F.col("last")))
          .withColumn("tenure_days", _days_between(snap, F.col("first")))
          .withColumn("avg_order_value", F.col("monetary") / F.col("frequency"))
          .withColumn("return_rate", F.greatest(-F.col("returns_value") / F.col("gross_spend"), F.lit(0.0)))
          .withColumn("bg_x", F.col("days") - 1)
          .withColumn("bg_t_x", F.datediff("last_day", "first_day") / 7)
          .withColumn("bg_T", F.datediff(F.to_date(snap), F.col("first_day")) / 7)
          .drop("first", "last", "days", "first_day", "last_day"))

    # Country: the most frequent in the lookback window, ties to the first alphabetically (pandas mode).
    cc = lb.groupBy(CID, "Country").count()
    pick = Window.partitionBy(CID).orderBy(F.desc("count"), F.asc("Country"))
    country = cc.withColumn("_r", F.row_number().over(pick)).where("_r = 1").select(CID, F.col("Country").alias(
        "country"))
    g = g.join(country, CID, "left")

    fut = purchases.where((date >= snap) & (date < end))
    fut_ret = returns.where((date >= snap) & (date < end))
    nxt = fut.groupBy(CID).agg(F.countDistinct("Invoice").alias("next_orders"), F.sum("value").alias("next_gross"))
    nret = fut_ret.groupBy(CID).agg(F.sum("value").alias("next_returns"))
    g = (g.join(nxt, CID, "left").join(nret, CID, "left")
          .fillna({"next_orders": 0, "next_gross": 0.0, "next_returns": 0.0})
          .withColumn("next_spend", F.col("next_gross") + F.col("next_returns"))
          .withColumn("repeat", F.col("next_orders") > 0)).cache()

    positive = F.round("monetary", 2) > 0  # whole pennies, as features.snapshot
    excluded = g.where(~positive).count()
    return g.where(positive), int(excluded)


# ---------------------------------------------------------------- RFM

def _score(col: str, higher_is_better: bool = True) -> Column:
    """1-5 from percentile ranks with ties averaged, as rfm.score.

    pandas rank(pct=True, method="average") is the average rank of a tie group over n.
    The average rank is the group's lowest rank plus (group size - 1) / 2.
    """
    v = F.col(col) if higher_is_better else -F.col(col)
    order = Window.orderBy(v)
    n = F.count(F.lit(1)).over(Window.partitionBy(F.lit(1)))
    ties = F.count(F.lit(1)).over(Window.partitionBy(v))
    pct = (F.rank().over(order) + (ties - 1) / 2) / n
    return F.least(F.greatest(F.ceil(pct * 5), F.lit(1)), F.lit(5)).cast("int")


def _segment(rf: Column) -> Column:
    out = None
    for pattern, name in SEGMENT_GRID:
        cond = rf.rlike(f"^{pattern}$")
        out = F.when(cond, name) if out is None else out.when(cond, name)
    return out


def add_rfm(features: DataFrame) -> DataFrame:
    df = (features.withColumn("r_score", _score("recency_days", higher_is_better=False))
                  .withColumn("f_score", _score("frequency"))
                  .withColumn("m_score", _score("monetary")))
    df = df.withColumn("rfm_sum", F.col("r_score") + F.col("f_score") + F.col("m_score"))
    rf = F.concat(F.col("r_score").cast("string"), F.col("f_score").cast("string"))
    return df.withColumn("rfm_segment", _segment(rf))
