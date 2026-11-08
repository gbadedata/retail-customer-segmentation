"""The segment workbook's formulas must agree with pandas, including the market filter."""

import pytest
from openpyxl import load_workbook

from segments import cluster, excel_pack, features, recalc, rfm, validate
from segments.clean import clean
from segments.config import Settings


@pytest.fixture(scope="module")
def built(tx, tmp_path_factory):
    s = Settings(stability_reps=5, k_max=5)
    res = clean(tx)
    a = rfm.add_rfm(features.snapshot(res.purchases, res.returns, "snapshot_fit", s))
    b = rfm.add_rfm(features.snapshot(res.purchases, res.returns, "snapshot_test", s))
    _, k = cluster.select_k(cluster.matrix(a), s)
    model = cluster.fit(a, k, s)
    a["cluster"], b["cluster"] = model.predict(a), model.predict(b)
    mig = validate.migration(a, b, "rfm_segment", rfm.SEGMENT_ORDER)
    import pandas as pd

    val = pd.DataFrame([{"label": "x", "segments": 1, "repeat_auc": 0.7, "repeat_auc_low": 0.6,
                         "repeat_auc_high": 0.8, "spend_spearman": 0.5, "spend_spearman_low": 0.4,
                         "spend_spearman_high": 0.6}])
    path = tmp_path_factory.mktemp("xl") / "pack.xlsx"
    excel_pack.build(b, model.names, mig, val, res.log, res.reconciliation, path, "2011-06-01", "2011-12-01",
                     generated="test")
    return path, b


def test_structure(built):
    path, _ = built
    wb = load_workbook(path)
    assert wb.sheetnames[:3] == ["About", "Segment_Summary", "Customer_Lookup"]
    ws = wb["Segment_Summary"]
    assert ws["B8"].value.startswith("=COUNTIFS(")
    assert ws.data_validations.dataValidation


@pytest.mark.skipif(not recalc.available(), reason="needs LibreOffice")
def test_formulas_match_pandas_and_filter_works(built, tmp_path):
    path, b = built
    for market, mask in (("All", b["country"].notna()),
                         ("International", b["country"] != "United Kingdom")):
        wb = load_workbook(path)
        wb["Segment_Summary"]["B4"] = market
        p = tmp_path / f"{market}.xlsx"
        wb.save(p)
        rc = recalc.recalc(p)
        assert rc["status"] == "success", rc["errors"][:5]
        ws = load_workbook(p, data_only=True)["Segment_Summary"]
        sub = b[mask]
        got = {}
        for row in ws.iter_rows(min_row=8, max_row=17, max_col=4, values_only=True):
            if row[0]:
                got[row[0]] = (row[1], row[3])
        expect = sub.groupby("rfm_segment").agg(n=("monetary", "size"), m=("monetary", "sum"))
        assert got.pop("Total")[0] == len(sub)
        for seg, (n, m) in got.items():
            exp_n = int(expect["n"].get(seg, 0))
            assert n == exp_n, (market, seg)
            assert m == pytest.approx(float(expect["m"].get(seg, 0.0)), abs=0.05 * max(exp_n, 1))
        lk = load_workbook(p, data_only=True)["Customer_Lookup"]
        assert lk["B4"].value == "yes"
