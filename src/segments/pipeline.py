"""End-to-end run: python -m segments.pipeline [--download]"""

from __future__ import annotations

import argparse
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from . import bgnbd, cluster, excel_pack, features, figures, recalc, report, rfm, validate
from .clean import clean
from .config import SETTINGS, Settings
from .download import ROOT, fetch
from .load import load


def segment_summary(df: pd.DataFrame, col: str, order: list) -> pd.DataFrame:
    g = df.groupby(col).agg(
        customers=("monetary", "size"), spend_12m=("monetary", "sum"), median_spend_12m=("monetary", "median"),
        median_recency_days=("recency_days", "median"), median_orders=("frequency", "median"),
        repeat_rate_next6m=("repeat", "mean"), next_spend=("next_spend", "sum"),
    )
    g["share_customers"] = g["customers"] / g["customers"].sum()
    g["share_spend_12m"] = g["spend_12m"] / g["spend_12m"].sum()
    g["share_next_spend"] = g["next_spend"] / g["next_spend"].sum()
    return g.reindex([o for o in order if o in g.index])


def data_quality_items(raw: pd.DataFrame, res, a: pd.DataFrame, b: pd.DataFrame) -> list[dict]:
    log = res.log.set_index("reason")
    raw_value = res.reconciliation["raw_value"]
    miss = log.loc["missing_customer"]
    ov = res.overlap_check
    returns_share = -log.loc["return", "value"] / log.loc["purchase", "value"]
    return [
        {"code": "DQ01", "severity": "high", "title": "The two yearly files overlap",
         "finding": f"{ov['rows']:,} rows dated {ov['from']} to {ov['to']} appear in both files; all "
                    f"{ov['matched']:,} are exact copies of rows in the first file.",
         "impact": f"Stacking the files double-counts £{log.loc['overlap_duplicate', 'value']:,.0f} of sales in "
                   "the busiest pre-Christmas week.",
         "handling": "Rows from the second file inside the first file's date range are quarantined."},
        {"code": "DQ02", "severity": "high", "title": "Dates are day-first",
         "finding": "InvoiceDate is written dd/mm/yyyy hh:mm (01/12/2009 is 1 December).",
         "impact": "Month-first parsing silently swaps day and month for days 1-12 and fails on the rest.",
         "handling": "Parsed with an explicit format; the contract fails the run on any unparsed date."},
        {"code": "DQ03", "severity": "high", "title": "No customer ID on a fifth of rows",
         "finding": f"{int(miss['rows']):,} rows ({miss['share_of_rows']:.1%}) carry no customer ID, worth "
                    f"£{miss['value']:,.0f} ({miss['value'] / raw_value:.1%} of raw line value).",
         "impact": "These sales cannot be segmented; segment revenue shares describe identified customers only.",
         "handling": "Quarantined and reported; not imputed."},
        {"code": "DQ04", "severity": "medium", "title": "Non-product lines mixed with sales",
         "finding": f"{int(log.loc['non_product', 'rows']):,} lines are postage, fees, manual adjustments, "
                    "bad-debt write-offs, vouchers or test products (codes such as POST, DOT, M, AMAZONFEE, B).",
         "impact": "They distort spend, especially single large adjustments.",
         "handling": "Listed explicitly in config.py and quarantined."},
        {"code": "DQ05", "severity": "medium", "title": "Exact duplicate lines",
         "finding": f"{int(log.loc['exact_duplicate', 'rows']):,} rows repeat an earlier row in every field.",
         "impact": f"Keeping them adds £{log.loc['exact_duplicate', 'value']:,.0f} of probably double-keyed sales.",
         "handling": "First copy kept, the rest quarantined. This is a judgement: a customer could genuinely "
                     "order the same line twice on one invoice."},
        {"code": "DQ06", "severity": "low", "title": "Returns recorded as cancellation invoices",
         "finding": f"Cancellations ('C' invoices) from known customers equal {returns_share:.1%} of purchase value.",
         "impact": "Ignoring them overstates customer value; dropping them as noise loses a behaviour signal.",
         "handling": "Kept as returns and netted off each customer's spend in the same window."},
        {"code": "DQ07", "severity": "low", "title": "Inconsistent ID format and file encoding",
         "finding": "Customer IDs are '13085.0' in one file and '13085' in the other; the second file starts "
                    "with a byte-order mark.",
         "impact": "A naive join treats the same customer as two, and the first column name is corrupted.",
         "handling": "IDs normalised to 5-digit strings and checked by the contract; files read as utf-8-sig."},
        {"code": "DQ08", "severity": "low", "title": "Zero or negative net spend",
         "finding": f"{a.attrs['excluded_non_positive']} customers at the fit snapshot and "
                    f"{b.attrs['excluded_non_positive']} at the test snapshot returned as much as they bought.",
         "impact": "They cannot be scored on spend.",
         "handling": "Excluded from that snapshot's segmentation and counted here."},
        {"code": "DQ09", "severity": "pass", "title": "Every raw row is accounted for",
         "finding": f"{res.reconciliation['raw_rows']:,} rows and £{raw_value:,.2f} of line value reconcile to "
                    f"purchases + returns + quarantine with a difference of £{res.reconciliation['difference']:.2f}.",
         "impact": "None.", "handling": "Asserted in the pipeline and in the tests."},
    ]


def run(raw_dir: Path, out: Path, s: Settings = SETTINGS, make_excel: bool = True) -> dict:
    warnings.filterwarnings("ignore", category=FutureWarning)
    for sub in ("reports", "figures", "outputs"):
        (out / sub).mkdir(parents=True, exist_ok=True)

    raw = load(raw_dir)
    res = clean(raw)
    if not res.reconciliation["balanced"]:
        raise RuntimeError(f"cleaning does not reconcile: {res.reconciliation}")

    a = rfm.add_rfm(features.snapshot(res.purchases, res.returns, "snapshot_fit", s))
    b = rfm.add_rfm(features.snapshot(res.purchases, res.returns, "snapshot_test", s))

    ks, k = cluster.select_k(cluster.matrix(a), s)
    model = cluster.fit(a, k, s)
    a["cluster"], b["cluster"] = model.predict(a), model.predict(b)
    for df in (a, b):
        df["m_decile"] = np.ceil(df["monetary"].rank(pct=True, method="average") * 10).astype(int)
        df["r_only"] = df["r_score"]

    # Out-of-time validation.
    schemes = [("rfm_segment", "RFM named segments (10)"), ("cluster", f"K-means segments ({k})"),
               ("rfm_sum", "RFM score total (3-15)"), ("m_decile", "Spend deciles only (10)"),
               ("r_only", "Recency score only (5)")]
    rows, preds = [], {}
    for col, label in schemes:
        m, _ = validate.evaluate(a, b, col)
        rows.append({"scheme": col, "label": label, **m})
        preds[col] = validate.predictions(a, b, col)
    bg = bgnbd.fit(b["bg_x"], b["bg_t_x"], b["bg_T"])
    horizon_weeks = (s.window("snapshot_test")["horizon_end"] - s.ts("snapshot_test")).days / 7
    e = bg.expected_purchases(horizon_weeks, b["bg_x"], b["bg_t_x"], b["bg_T"])
    spend_e = e * b["avg_order_value"].to_numpy()
    rows.append({"scheme": "bgnbd", "label": "BG/NBD per customer (no segments)",
                 **validate.evaluate_scores(b, e, spend_e)})
    preds["bgnbd"] = (e, spend_e)
    ci = validate.bootstrap(b, preds, s.bootstrap_reps, s.seed)
    val = pd.DataFrame(rows)
    for metric in ("repeat_auc", "spend_spearman"):
        val[f"{metric}_low"] = val["scheme"].map(lambda k_, m=metric: ci[k_][m][0])
        val[f"{metric}_high"] = val["scheme"].map(lambda k_, m=metric: ci[k_][m][1])
    _, rfm_cal = validate.evaluate(a, b, "rfm_segment")
    rfm_cal = rfm_cal.reindex([x for x in rfm.SEGMENT_ORDER if x in rfm_cal.index])

    mig = validate.migration(a, b, "rfm_segment", rfm.SEGMENT_ORDER)
    mig.index.name = "rfm_segment"
    rfm_sum = segment_summary(b, "rfm_segment", rfm.SEGMENT_ORDER)
    prof = segment_summary(b, "cluster", sorted(model.names))
    prof.insert(0, "name", [model.names[c] for c in prof.index])
    cap = validate.value_capture(b, "rfm_segment", a)

    snap = lambda df: {**df.attrs, "customers": len(df), "repeat_rate": float(df["repeat"].mean()),
                       "pareto": features.pareto(df["monetary"]),
                       "uk_share": float((df["country"] == "United Kingdom").mean())}
    dq = data_quality_items(raw, res, a, b)
    results = {
        "settings": s.__dict__,
        "cleaning": {"log": res.log, "reconciliation": res.reconciliation, "overlap": res.overlap_check},
        "snapshots": {"fit": snap(a), "test": snap(b)},
        "rfm": {"summary": rfm_sum.reset_index()},
        "clustering": {"k": k, "k_selection": ks, "names": model.names, "tertiles": model.tertiles,
                       "profiles": prof.reset_index()},
        "validation": {"schemes": val, "rfm_calibration": rfm_cal.reset_index()},
        "bgnbd": {"r": bg.r, "alpha": bg.alpha, "a": bg.a, "b": bg.b, "log_likelihood": bg.log_likelihood,
                  "horizon_weeks": horizon_weeks},
        "migration": mig.reset_index(),
        "value_capture_rfm": cap.reset_index(),
        "data_quality": dq,
    }

    figures.cleaning(res.log, out / "figures" / "01_cleaning_reconciliation.png")
    figures.choose_k(ks, s.stability_min_ari, out / "figures" / "02_choosing_k.png")
    figures.profiles(prof, out / "figures" / "03_cluster_profiles.png")
    figures.validation(val.assign(label=val["label"]), out / "figures" / "04_out_of_time_validation.png")
    figures.value_capture(cap, out / "figures" / "05_segment_value_next_6m.png")
    figures.migration(mig, out / "figures" / "06_segment_migration.png")
    figures.pareto(b["monetary"], out / "figures" / "07_spend_concentration.png")

    if make_excel:
        xlsx = excel_pack.build(
            b, model.names, mig, val, res.log, res.reconciliation, out / "outputs" / "customer_segments_pack.xlsx",
            snapshot=b.attrs["snapshot"], horizon=b.attrs["horizon_end"])
        if recalc.available():
            rc = recalc.recalc(xlsx)
            if rc["errors"]:
                raise RuntimeError(f"formula errors in workbook: {rc['errors'][:5]}")
            results["workbook"] = {"formulas": rc["total_formulas"], "errors": 0}

    report.write_json(results, out / "reports" / "results.json")
    report.write_results_md(json.loads((out / "reports" / "results.json").read_text()), out / "reports" / "RESULTS.md")
    report.write_dq_md(dq, out / "reports" / "DATA_QUALITY.md")
    cols = ["country", "recency_days", "frequency", "monetary", "r_score", "f_score", "m_score", "rfm_segment",
            "cluster", "repeat", "next_spend"]
    export = b[cols].assign(cluster_name=b["cluster"].map(model.names))
    export.to_csv(out / "outputs" / f"customer_segments_{b.attrs['snapshot']}.csv")
    return results


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--download", action="store_true", help="fetch and verify the data first")
    ap.add_argument("--raw-dir", type=Path, default=ROOT / "data" / "raw")
    ap.add_argument("--out", type=Path, default=ROOT)
    args = ap.parse_args()
    if args.download:
        fetch(args.raw_dir)
    r = run(args.raw_dir, args.out)
    v = {x["scheme"]: x for x in json.loads(json.dumps(r["validation"]["schemes"], default=report._jsonable))}
    print(f"k = {r['clustering']['k']}; test customers {r['snapshots']['test']['customers']}; "
          f"RFM repeat AUC {v['rfm_segment']['repeat_auc']:.3f}; BG/NBD {v['bgnbd']['repeat_auc']:.3f}")


if __name__ == "__main__":
    main()
