"""The PySpark engine must agree with the pandas pipeline row for row and customer for customer.

Skipped when PySpark (or Java) is not installed; the spark CI job installs both.
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd
import pytest

# The spark CI job sets REQUIRE_SPARK=1 so a missing install fails instead of skipping.
REQUIRED = os.environ.get("REQUIRE_SPARK") == "1"
pyspark = __import__("pyspark") if REQUIRED else pytest.importorskip("pyspark")

from segments import clean, features, rfm  # noqa: E402
from segments import spark_engine as se  # noqa: E402
from test_load_and_clean import _frame  # noqa: E402

INT_COLS = ["frequency", "products", "recency_days", "tenure_days", "bg_x", "next_orders"]
FLOAT_COLS = ["gross_spend", "returns_value", "monetary", "avg_order_value", "return_rate", "bg_t_x", "bg_T",
              "next_gross", "next_returns", "next_spend"]
RFM_COLS = ["r_score", "f_score", "m_score", "rfm_sum"]


@pytest.fixture(scope="module")
def spark():
    try:
        s = se.session("segments-tests", "local[2]")
    except Exception as exc:  # no Java on this machine
        if REQUIRED:
            raise
        pytest.skip(f"Spark unavailable: {exc}")
    yield s
    s.stop()


def _with_rows(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "source_row" not in out:
        out["source_row"] = range(len(out))
    return out


def _clean_both(spark, df: pd.DataFrame):
    df = _with_rows(df)
    return clean.clean(df), se.clean(se.from_pandas(spark, df)), df


def test_clean_matches_pandas_on_edge_cases(spark):
    pres, sres, df = _clean_both(spark, _frame())
    plog = pres.log.set_index("reason")
    for row in sres.log:
        assert row["rows"] == plog.loc[row["reason"], "rows"], row["reason"]
        assert row["value"] == pytest.approx(plog.loc[row["reason"], "value"], abs=1e-9), row["reason"]
    assert sres.reconciliation["balanced"]
    assert sres.overlap_check == pres.overlap_check


def test_every_row_gets_the_same_bucket(spark, tx):
    pres, sres, df = _clean_both(spark, tx)
    p = pd.concat([pres.purchases.assign(bucket="purchase"), pres.returns.assign(bucket="return"),
                   pres.quarantine.rename(columns={"reason": "bucket"})])
    p = p.set_index(["source_file", "source_row"])["bucket"].sort_index()
    s = sres.rows.select("source_file", "source_row", "bucket").toPandas()
    s = s.set_index(["source_file", "source_row"])["bucket"].sort_index()
    assert len(p) == len(s) == len(df)
    assert (p == s).all()


def test_first_rule_wins_in_spark_too(spark):
    df = _frame()
    extra = df.iloc[[4]].copy()
    extra["Customer ID"] = pd.NA
    df = pd.concat([df, extra], ignore_index=True)
    _, sres, _ = _clean_both(spark, df)
    log = {r["reason"]: r for r in sres.log}
    assert log["missing_customer"]["rows"] == 2


@pytest.mark.parametrize("which", ["snapshot_fit", "snapshot_test"])
def test_snapshot_features_and_rfm_match(spark, tx, which):
    pres, sres, _ = _clean_both(spark, tx)
    pf = rfm.add_rfm(features.snapshot(pres.purchases, pres.returns, which))
    base, excluded = se.snapshot(sres.purchases, sres.returns, which)
    sf = se.add_rfm(base).toPandas().set_index("Customer ID").sort_index()
    pf = pf.sort_index()

    assert excluded == pf.attrs["excluded_non_positive"]
    assert list(sf.index) == list(pf.index)
    for c in INT_COLS + RFM_COLS:
        assert (sf[c].astype(int).to_numpy() == pf[c].astype(int).to_numpy()).all(), c
    for c in FLOAT_COLS:
        np.testing.assert_allclose(sf[c].to_numpy(float), pf[c].to_numpy(float), rtol=1e-9, atol=1e-9, err_msg=c)
    assert (sf["country"] == pf["country"]).all()
    assert (sf["repeat"].astype(bool) == pf["repeat"].astype(bool)).all()
    assert (sf["rfm_segment"] == pf["rfm_segment"]).all()


def test_score_averages_ties_like_pandas(spark):
    vals = pd.Series([1, 1, 1, 2, 3, 3, 4, 5, 5, 5, 5, 9], dtype=float)
    expected = rfm.score(vals).to_list()
    sdf = spark.createDataFrame(pd.DataFrame({"i": range(len(vals)), "v": vals}))
    got = sdf.withColumn("s", se._score("v")).orderBy("i").toPandas()["s"].to_list()
    assert got == expected


def test_load_contract_matches_pandas(spark, tmp_path):
    header = "Invoice,StockCode,Description,Quantity,InvoiceDate,Price,Customer ID,Country\n"
    (tmp_path / "online_retail_II.csv").write_text(
        header + "1,10001,X,2,01/12/2009 07:45,1.5,13085.0,United Kingdom\n", encoding="utf-8-sig")
    (tmp_path / "online_retail_II2.csv").write_text(
        header + "2,10001,X,2,13/12/2010 09:58,1.5,13085,United Kingdom\n", encoding="utf-8")
    got = se.load(spark, tmp_path).orderBy("source_file").toPandas()
    assert list(got["Customer ID"]) == ["13085", "13085"]
    assert got["InvoiceDate"].iloc[1] == pd.Timestamp("2010-12-13 09:58")

    (tmp_path / "online_retail_II.csv").write_text(
        header + "1,10001,X,2,2009-12-01 07:45,1.5,13085,United Kingdom\n", encoding="utf-8")
    with pytest.raises(se.ContractError, match="dd/mm"):
        se.load(spark, tmp_path)
