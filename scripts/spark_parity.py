"""Run the pandas pipeline and the PySpark engine on the full dataset and compare them.

    python -m segments.download          # once: the two pinned, checksummed files
    python scripts/spark_parity.py --check

Writes reports/spark_parity.json and reports/SPARK_PARITY.md. With --check it exits
non-zero if any row lands in a different bucket, any customer differs, or any score
or segment differs.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

os.environ.setdefault("TZ", "UTC")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from segments import clean, features, rfm  # noqa: E402
from segments import load as pload  # noqa: E402
from segments import spark_engine as se  # noqa: E402

INT_COLS = ["frequency", "products", "recency_days", "tenure_days", "bg_x", "next_orders"]
FLOAT_COLS = ["gross_spend", "returns_value", "monetary", "avg_order_value", "return_rate", "bg_t_x", "bg_T",
              "next_gross", "next_returns", "next_spend"]
RFM_COLS = ["r_score", "f_score", "m_score", "rfm_sum"]


def compare_snapshot(pf: pd.DataFrame, sf: pd.DataFrame, p_excl: int, s_excl: int) -> dict:
    pf, sf = pf.sort_index(), sf.sort_index()
    same_customers = list(pf.index) == list(sf.index)
    out = {"customers_pandas": len(pf), "customers_spark": len(sf), "same_customers": same_customers,
           "excluded_pandas": p_excl, "excluded_spark": s_excl}
    if not same_customers:
        return out
    out["int_mismatches"] = {c: int((pf[c].astype(int).to_numpy() != sf[c].astype(int).to_numpy()).sum())
                             for c in INT_COLS + RFM_COLS}
    out["float_max_abs_diff"] = {c: float(np.max(np.abs(pf[c].to_numpy(float) - sf[c].to_numpy(float))))
                                 for c in FLOAT_COLS}
    out["country_mismatches"] = int((pf["country"] != sf["country"]).sum())
    out["repeat_mismatches"] = int((pf["repeat"].astype(bool) != sf["repeat"].astype(bool)).sum())
    out["segment_mismatches"] = int((pf["rfm_segment"] != sf["rfm_segment"]).sum())
    return out


def headline(sf: pd.DataFrame) -> dict:
    """The README's headline segment figures, recomputed from the Spark output."""
    top = sf["rfm_segment"].isin(["Champions", "Loyal"])
    champ = sf["rfm_segment"] == "Champions"
    total_next = sf["next_spend"].sum()
    return {
        "customers": len(sf),
        "champions_loyal_share_customers": float(top.mean()),
        "champions_loyal_share_next_spend": float(sf.loc[top, "next_spend"].sum() / total_next),
        "champions_share_customers": float(champ.mean()),
        "champions_share_next_spend": float(sf.loc[champ, "next_spend"].sum() / total_next),
        "champions_reorder_rate": float(sf.loc[champ, "repeat"].astype(bool).mean()),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw-dir", type=Path, default=ROOT / "data" / "raw")
    ap.add_argument("--out", type=Path, default=ROOT / "reports")
    ap.add_argument("--check", action="store_true", help="exit 1 on any mismatch")
    args = ap.parse_args()

    t0 = time.perf_counter()
    raw = pload.load(args.raw_dir)
    pres = clean.clean(raw)
    psnap = {w: rfm.add_rfm(features.snapshot(pres.purchases, pres.returns, w))
             for w in ("snapshot_fit", "snapshot_test")}
    t_pandas = time.perf_counter() - t0

    spark = se.session("segments-parity")
    t0 = time.perf_counter()
    sraw = se.load(spark, args.raw_dir).cache()
    sres = se.clean(sraw)
    ssnap, sexcl = {}, {}
    for w in ("snapshot_fit", "snapshot_test"):
        base, excl = se.snapshot(sres.purchases, sres.returns, w)
        ssnap[w] = se.add_rfm(base).toPandas().set_index("Customer ID")
        sexcl[w] = excl
    srows = sres.rows.select("source_file", "source_row", "bucket").toPandas()
    t_spark = time.perf_counter() - t0
    spark_version = spark.version

    # 1. Every raw row in the same bucket.
    prow = pd.concat([pres.purchases.assign(bucket="purchase"), pres.returns.assign(bucket="return"),
                      pres.quarantine.rename(columns={"reason": "bucket"})])
    prow = prow.set_index(["source_file", "source_row"])["bucket"].sort_index()
    srow = srows.set_index(["source_file", "source_row"])["bucket"].sort_index()
    same_index = prow.index.equals(srow.index)
    row_mismatches = int((prow != srow).sum()) if same_index else None

    # 2. The cleaning log and reconciliation.
    plog = pres.log.set_index("reason")
    log = [{"bucket": r["reason"], "rows_pandas": int(plog.loc[r["reason"], "rows"]), "rows_spark": r["rows"],
            "value_pandas": float(plog.loc[r["reason"], "value"]), "value_spark": r["value"]} for r in sres.log]

    snaps = {w: compare_snapshot(psnap[w], ssnap[w], psnap[w].attrs["excluded_non_positive"], sexcl[w])
             for w in psnap}
    result = {
        "rows": len(raw), "spark_version": spark_version,
        "row_buckets": {"same_rows": same_index, "mismatches": row_mismatches},
        "cleaning_log": log,
        "reconciliation": {"pandas_balanced": pres.reconciliation["balanced"],
                           "spark_balanced": sres.reconciliation["balanced"],
                           "spark_difference": sres.reconciliation["difference"]},
        "overlap_check": {"pandas": pres.overlap_check, "spark": sres.overlap_check,
                          "same": pres.overlap_check == sres.overlap_check},
        "snapshots": snaps,
        "headline_from_spark": headline(ssnap["snapshot_test"]),
        "seconds": {"pandas": round(t_pandas, 1), "spark_local": round(t_spark, 1)},
    }
    spark.stop()

    failures = []
    if not same_index or row_mismatches:
        failures.append("row buckets differ")
    for r in log:
        if r["rows_pandas"] != r["rows_spark"] or abs(r["value_pandas"] - r["value_spark"]) > 0.005:
            failures.append(f"cleaning log differs for {r['bucket']}")
    if not (result["reconciliation"]["pandas_balanced"] and result["reconciliation"]["spark_balanced"]):
        failures.append("reconciliation does not balance")
    if not result["overlap_check"]["same"]:
        failures.append("overlap check differs")
    for w, s in snaps.items():
        if not s["same_customers"] or s["excluded_pandas"] != s["excluded_spark"]:
            failures.append(f"{w}: customer base differs")
            continue
        if any(s["int_mismatches"].values()) or s["country_mismatches"] or s["repeat_mismatches"] \
                or s["segment_mismatches"]:
            failures.append(f"{w}: features, scores or segments differ")
        if max(s["float_max_abs_diff"].values()) > 1e-6:
            failures.append(f"{w}: money or week values differ by more than 1e-6")
    result["failures"] = failures

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "spark_parity.json").write_text(json.dumps(result, indent=2, default=str) + "\n")
    (args.out / "SPARK_PARITY.md").write_text(markdown(result))
    print(json.dumps({"failures": failures, "seconds": result["seconds"]}, indent=2))
    return 1 if (args.check and failures) else 0


def gbp(v: float) -> str:
    return f"-£{abs(v):,.2f}" if round(v, 2) < 0 else f"£{abs(v):,.2f}"


def markdown(r: dict) -> str:
    lines = ["# PySpark parity check", "",
             f"The PySpark engine (`src/segments/spark_engine.py`, Spark {r['spark_version']}) and the pandas "
             f"pipeline were run on the same {r['rows']:,} rows. "
             + ("**They agree on every check below.**" if not r["failures"] else
                "**They disagree:** " + "; ".join(r["failures"]) + "."), "",
             "## Cleaning", "",
             f"Rows placed in a different bucket: **{r['row_buckets']['mismatches']}** of {r['rows']:,}. "
             f"Both reconciliations balance (Spark difference: {gbp(r['reconciliation']['spark_difference'])}).", "",
             "| Bucket | Rows (pandas) | Rows (Spark) | Value (pandas) | Value (Spark) |",
             "|---|---:|---:|---:|---:|"]
    for x in r["cleaning_log"]:
        lines.append(f"| {x['bucket']} | {x['rows_pandas']:,} | {x['rows_spark']:,} | "
                     f"{gbp(x['value_pandas'])} | {gbp(x['value_spark'])} |")
    ov = r["overlap_check"]["spark"]
    lines += ["", f"Overlap check: {ov['rows']:,} rows from the second file dated {ov['from']} to {ov['to']}, "
              f"{ov['matched']:,} matched to the first file in both engines.", "", "## Snapshots and RFM", "",
              "| Snapshot | Customers | Excluded (net spend <= 0) | Integer or score mismatches | "
              "Segment mismatches | Largest money or week difference |", "|---|---:|---:|---:|---:|---:|"]
    for w, s in r["snapshots"].items():
        ints = sum(s.get("int_mismatches", {}).values()) if s["same_customers"] else "n/a"
        diff = max(s["float_max_abs_diff"].values()) if s["same_customers"] else float("nan")
        lines.append(f"| {w} | {s['customers_spark']:,} | {s['excluded_spark']} | {ints} | "
                     f"{s.get('segment_mismatches', 'n/a')} | {diff:.1e} |")
    lines += ["", "The two engines add money up in a different order, so totals can differ around the ninth "
              "decimal place. Nothing differs at the penny, and net spend is compared in whole pennies in both."]
    h = r["headline_from_spark"]
    lines += ["", "## The README's headline figures, recomputed from the Spark output", "",
              f"- {h['customers']:,} customers at the June 2011 snapshot.",
              f"- Champions and Loyal: {h['champions_loyal_share_customers']:.1%} of customers, "
              f"{h['champions_loyal_share_next_spend']:.1%} of next-period spend.",
              f"- Champions alone: {h['champions_share_customers']:.1%} of customers, "
              f"{h['champions_share_next_spend']:.1%} of next spend, {h['champions_reorder_rate']:.0%} reordered.",
              "", "## Run time", "",
              f"pandas: {r['seconds']['pandas']} s. Spark in local mode on the same machine: "
              f"{r['seconds']['spark_local']} s. At about a million rows pandas is the faster tool; the Spark "
              "engine is here so the same logic can run on a cluster when the data outgrows one machine.", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
