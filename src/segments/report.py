"""results.json and generated markdown."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


def md_table(df: pd.DataFrame, formats: dict[str, str] | None = None, index: bool = True) -> str:
    formats = formats or {}
    d = df.reset_index() if index else df.copy()
    cols = list(d.columns)
    out = ["| " + " | ".join(str(c).replace("_", " ") for c in cols) + " |",
           "|" + "|".join("---:" if pd.api.types.is_numeric_dtype(d[c]) else "---" for c in cols) + "|"]
    for _, r in d.iterrows():
        cells = []
        for c in cols:
            v = r[c]
            if v is None or (isinstance(v, (float, np.floating)) and np.isnan(v)):
                cells.append("")
            elif c in formats:
                cells.append(format(v, formats[c]))
            elif isinstance(v, (bool, np.bool_)):
                cells.append("yes" if v else "no")
            else:
                cells.append(str(v))
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out)


def _jsonable(o):
    if isinstance(o, pd.DataFrame):
        flat = o.reset_index(drop=isinstance(o.index, pd.RangeIndex) and o.index.name is None)
        return json.loads(flat.to_json(orient="records"))
    if isinstance(o, pd.Series):
        return json.loads(o.to_json())
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        return float(o)
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, pd.Timestamp):
        return o.strftime("%Y-%m-%d")
    raise TypeError(type(o))


def write_json(results: dict, path: Path) -> None:
    path.write_text(json.dumps(results, indent=2, default=_jsonable))


def write_results_md(r: dict, path: Path) -> None:
    pct, f3 = ".1%", ".3f"
    log = pd.DataFrame(r["cleaning"]["log"])
    ks = pd.DataFrame(r["clustering"]["k_selection"])
    prof = pd.DataFrame(r["clustering"]["profiles"])
    val = pd.DataFrame(r["validation"]["schemes"])
    rfm_sum = pd.DataFrame(r["rfm"]["summary"])
    cal = pd.DataFrame(r["validation"]["rfm_calibration"])
    mig = pd.DataFrame(r["migration"]).set_index("rfm_segment")
    b = r["snapshots"]["test"]
    a = r["snapshots"]["fit"]
    s = [
        "# Results (generated)", "", "Written by `make run`. Do not edit by hand.", "",
        "## 1. Cleaning and reconciliation", "",
        md_table(log, {"rows": ",.0f", "value": ",.2f", "share_of_rows": pct}, index=False), "",
        f"Raw rows {r['cleaning']['reconciliation']['raw_rows']:,}; raw line value "
        f"£{r['cleaning']['reconciliation']['raw_value']:,.2f}; difference after accounting "
        f"£{r['cleaning']['reconciliation']['difference']:.2f} "
        f"(balanced: {r['cleaning']['reconciliation']['balanced']}).",
        f"Overlap check: {r['cleaning']['overlap']['rows']:,} rows dated {r['cleaning']['overlap']['from']} to "
        f"{r['cleaning']['overlap']['to']} appear in both files; {r['cleaning']['overlap']['matched']:,} match "
        "a row in the first file exactly.", "",
        "## 2. Snapshots", "",
        f"- Fit snapshot {a['snapshot']}: {a['customers']:,} customers bought between {a['lookback_start']} and the "
        f"snapshot; {a['repeat_rate']:.1%} ordered again by {a['horizon_end']}. {a['excluded_non_positive']} "
        "customers with zero or negative net spend excluded.",
        f"- Test snapshot {b['snapshot']}: {b['customers']:,} customers; {b['repeat_rate']:.1%} ordered again by "
        f"{b['horizon_end']}. {b['excluded_non_positive']} excluded.",
        f"- Spend concentration at the test snapshot: top 10% of customers = {b['pareto']['top_10pct']:.1%} of "
        f"12-month net spend; top 20% = {b['pareto']['top_20pct']:.1%}.", "",
        "## 3. RFM segments at the test snapshot", "",
        md_table(rfm_sum, {"share_customers": pct, "share_spend_12m": pct, "repeat_rate_next6m": pct,
                           "share_next_spend": pct, "median_spend_12m": ",.0f", "spend_12m": ",.0f",
                           "next_spend": ",.0f", "median_recency_days": ".0f", "median_orders": ".0f",
                           "customers": ",.0f"}, index=False), "",
        "## 4. Choosing k (fit snapshot)", "",
        md_table(ks, {"inertia": ",.0f", "silhouette": f3, "davies_bouldin": f3, "calinski_harabasz": ",.0f",
                      "ari_mean": f3, "ari_min": f3}, index=False), "",
        f"Chosen k = {r['clustering']['k']} by the pre-declared rule (k >= {r['settings']['k_floor']}, mean "
        f"bootstrap ARI >= {r['settings']['stability_min_ari']}, then highest silhouette).", "",
        "Profiles at the test snapshot:", "",
        md_table(prof, {"share_customers": pct, "share_spend_12m": pct, "repeat_rate_next6m": pct,
                        "share_next_spend": pct, "median_spend_12m": ",.0f", "median_recency_days": ".0f",
                        "median_orders": ".0f", "customers": ",.0f", "spend_12m": ",.0f",
                        "next_spend": ",.0f"}, index=False), "",
        "## 5. Out-of-time validation (scored on the test snapshot's next six months)", "",
        md_table(val[["label", "segments", "repeat_auc", "repeat_auc_low", "repeat_auc_high", "spend_spearman",
                      "spend_spearman_low", "spend_spearman_high"]],
                 {"segments": ".0f"} | {c: f3 for c in ["repeat_auc", "repeat_auc_low", "repeat_auc_high",
                                                        "spend_spearman",
                                  "spend_spearman_low", "spend_spearman_high"]}, index=False), "",
        f"BG/NBD fitted on purchase history before {b['snapshot']}: r = {r['bgnbd']['r']:.3f}, "
        f"alpha = {r['bgnbd']['alpha']:.3f}, a = {r['bgnbd']['a']:.3f}, b = {r['bgnbd']['b']:.3f}.", "",
        "RFM segment repeat rates, learned at the fit snapshot vs observed at the test snapshot:", "",
        md_table(cal, {"repeat_rate_fit": pct, "repeat_rate_test": pct, "mean_next_spend_fit": ",.0f",
                       "mean_next_spend_test": ",.0f", "customers_fit": ",.0f", "customers_test": ",.0f"},
                 index=False), "",
        "## 6. Migration, December 2010 to June 2011 (row shares)", "",
        md_table(mig, {c: ".0%" for c in mig.columns}), "",
    ]
    path.write_text("\n".join(s))


def write_dq_md(items: list[dict], path: Path) -> None:
    s = ["# Data quality log (generated)", "",
         "What was found in the raw files, what it would have done to the analysis, and how it is handled.", ""]
    for i in items:
        s += [f"## {i['code']} [{i['severity']}] {i['title']}", "", f"- **Finding:** {i['finding']}",
              f"- **Impact if ignored:** {i['impact']}", f"- **Handling:** {i['handling']}", ""]
    path.write_text("\n".join(s))
