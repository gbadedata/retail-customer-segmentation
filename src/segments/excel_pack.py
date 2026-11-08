"""Excel segment pack: live summaries and a customer lookup driven by formulas."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.formatting.rule import ColorScaleRule, DataBarRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from .rfm import ACTIONS, SEGMENT_ORDER

FONT = "Arial"
NAVY = "1F3864"
HEAD = Font(name=FONT, bold=True, color="FFFFFF")
HEAD_FILL = PatternFill("solid", fgColor=NAVY)
TITLE = Font(name=FONT, bold=True, size=14, color=NAVY)
BODY = Font(name=FONT, size=10)
BOLD = Font(name=FONT, size=10, bold=True)
NOTE = Font(name=FONT, size=9, italic=True, color="52514E")
INPUT_FONT = Font(name=FONT, size=10, bold=True, color="0000FF")
INPUT_FILL = PatternFill("solid", fgColor="FFFF00")
THIN = Border(bottom=Side(style="thin", color="D9D9D9"))
PCT, INT, GBP = "0.0%", "#,##0", "£#,##0"


def _header(ws, row: int, labels: list[str], col: int = 1) -> None:
    for j, lab in enumerate(labels):
        c = ws.cell(row=row, column=col + j, value=lab)
        c.font, c.fill = HEAD, HEAD_FILL
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)


def _table(ws, df: pd.DataFrame, start_row: int, start_col: int = 1, formats: dict | None = None) -> int:
    _header(ws, start_row, list(df.columns), start_col)
    formats = formats or {}
    for i, rec in enumerate(df.itertuples(index=False), start=start_row + 1):
        for j, v in enumerate(rec):
            c = ws.cell(row=i, column=start_col + j, value=None if pd.isna(v) else v)
            if df.columns[j] in formats:
                c.number_format = formats[df.columns[j]]
    return start_row + len(df)


def _arial(ws) -> None:
    for row in ws.iter_rows():
        for c in row:
            f = c.font
            if f.name != FONT:
                c.font = Font(name=FONT, bold=f.b, italic=f.i, size=f.sz, color=f.color)


def build(customers: pd.DataFrame, cluster_names: dict[int, str], migration: pd.DataFrame,
          validation: pd.DataFrame, cleaning_log: pd.DataFrame, reconciliation: dict, path: Path,
          snapshot: str, horizon: str, generated: str | None = None) -> Path:
    wb = Workbook()
    generated = generated or datetime.now().strftime("%d %b %Y")

    # ---------------- Customers (data) ----------------
    data = pd.DataFrame({
        "Customer ID": customers.index.astype(int),
        "Country": customers["country"],
        "Days since last order": customers["recency_days"].astype(int),
        "Orders (12m)": customers["frequency"].astype(int),
        "Net spend (12m)": customers["monetary"].round(2),
        "R": customers["r_score"], "F": customers["f_score"], "M": customers["m_score"],
        "RFM segment": customers["rfm_segment"],
        "Cluster": customers["cluster"].astype(int),
        "Cluster name": customers["cluster"].map(cluster_names),
        "Ordered again (next 6m)": customers["repeat"].astype(int),
        "Net spend (next 6m)": customers["next_spend"].round(2),
    }).reset_index(drop=True).sort_values("Customer ID")
    n = len(data)
    last = n + 1
    ws_c = wb.active
    ws_c.title = "Customers"
    _table(ws_c, data, 1, formats={"Net spend (12m)": "#,##0.00", "Net spend (next 6m)": "#,##0.00"})
    ws_c.freeze_panes = "B2"
    ws_c.auto_filter.ref = f"A1:M{last}"
    for col, w in zip("ABCDEFGHIJKLM", [12, 18, 12, 10, 14, 5, 5, 5, 20, 8, 32, 12, 14], strict=True):
        ws_c.column_dimensions[col].width = w
    col = {name: get_column_letter(i + 1) for i, name in enumerate(data.columns)}
    R = {k: f"Customers!${v}$2:${v}${last}" for k, v in col.items()}

    # ---------------- Lists ----------------
    ws_x = wb.create_sheet("Lists")
    for i, v in enumerate(["All", "United Kingdom", "International"], start=1):
        ws_x.cell(row=i, column=1, value=v)
    ws_x.sheet_state = "hidden"

    # ---------------- Segment summary ----------------
    ws = wb.create_sheet("Segment_Summary", 0)
    ws["A1"] = "Customer segments"
    ws["A1"].font = TITLE
    ws["A2"] = (f"Customers who bought in the 12 months before {snapshot}. 'Next 6m' columns show what they "
                f"did from {snapshot} to {horizon}. Change the yellow cell to filter by market.")
    ws["A2"].font = NOTE
    ws["A4"] = "Market"
    ws["B4"] = "All"
    ws["B4"].font, ws["B4"].fill = INPUT_FONT, INPUT_FILL
    dv = DataValidation(type="list", formula1="=Lists!$A$1:$A$3", allow_blank=False)
    ws.add_data_validation(dv)
    dv.add(ws["B4"])
    ws["C4"] = "All, United Kingdom or International"
    ws["C4"].font = NOTE
    ws["L4"] = '=IF($B$4="All","*",IF($B$4="United Kingdom","United Kingdom","<>United Kingdom"))'
    ws.column_dimensions["L"].hidden = True

    heads = ["Customers", "Share of customers", "Net spend (12m)", "Share of spend", "Avg orders (12m)",
             "Avg days since last order", "Ordered again (next 6m)", "Share of next-6m spend"]
    country = f"{R['Country']},$L$4"

    def block(top: int, title: str, key_col: str, keys: list, labels: list[str] | None = None) -> int:
        ws.cell(row=top - 1, column=1, value=title).font = BOLD
        _header(ws, top, ["Segment"] + heads)
        first, lastr = top + 1, top + len(keys)
        for i, k in enumerate(keys):
            r = top + 1 + i
            ws.cell(row=r, column=1, value=labels[i] if labels else k)
            key = f'"{k}"' if isinstance(k, str) else str(k)
            crit = f"{R[key_col]},{key},{country}"
            ws.cell(row=r, column=2, value=f"=COUNTIFS({crit})").number_format = INT
            ws.cell(row=r, column=3, value=f"=IFERROR(B{r}/SUM($B${first}:$B${lastr}),0)").number_format = PCT
            ws.cell(row=r, column=4, value=f"=SUMIFS({R['Net spend (12m)']},{crit})").number_format = GBP
            ws.cell(row=r, column=5, value=f"=IFERROR(D{r}/SUM($D${first}:$D${lastr}),0)").number_format = PCT
            avg_orders = f'=IFERROR(AVERAGEIFS({R["Orders (12m)"]},{crit}),"-")'
            ws.cell(row=r, column=6, value=avg_orders).number_format = "0.0"
            ws.cell(row=r, column=7, value=f'=IFERROR(AVERAGEIFS({R["Days since last order"]},{crit}),"-")'
                    ).number_format = "0"
            ws.cell(row=r, column=8, value=f'=IFERROR(AVERAGEIFS({R["Ordered again (next 6m)"]},{crit}),"-")'
                    ).number_format = PCT
            ws.cell(row=r, column=9, value=f"=IFERROR(SUMIFS({R['Net spend (next 6m)']},{crit})/"
                    f"SUMIFS({R['Net spend (next 6m)']},{country}),0)").number_format = PCT
            for c in range(2, 10):
                ws.cell(row=r, column=c).border = THIN
        tot = lastr + 1
        ws.cell(row=tot, column=1, value="Total").font = BOLD
        ws.cell(row=tot, column=2, value=f"=SUM(B{first}:B{lastr})").number_format = INT
        ws.cell(row=tot, column=4, value=f"=SUM(D{first}:D{lastr})").number_format = GBP
        ws.cell(row=tot, column=8, value=f'=IFERROR(AVERAGEIFS({R["Ordered again (next 6m)"]},{country}),"-")'
                ).number_format = PCT
        for c in (2, 4, 8):
            ws.cell(row=tot, column=c).font = BOLD
        ws.conditional_formatting.add(f"H{first}:H{lastr}", ColorScaleRule(
            start_type="min", start_color="FFFFFF", end_type="max", end_color="6DA7EC"))
        ws.conditional_formatting.add(f"E{first}:E{lastr}", DataBarRule(start_type="num", start_value=0,
                                                                         end_type="max", color="9EC5F4"))
        return tot

    segs = [s for s in SEGMENT_ORDER if s in set(data["RFM segment"])]
    t1 = block(7, "RFM segments", "RFM segment", segs)
    clusters = sorted(cluster_names)
    t2 = block(t1 + 4, "K-means segments", "Cluster", clusters,
               [f"{c}. {cluster_names[c]}" for c in clusters])
    ws.cell(row=t2 + 2, column=1, value="All figures recalculate from the Customers sheet. RFM segments use a "
            "standard recency-by-frequency grid; k-means segments were fitted on the December 2010 snapshot "
            "and applied here unchanged.").font = NOTE
    widths = {"A": 40, "B": 11, "C": 11, "D": 14, "E": 10, "F": 11, "G": 12, "H": 12, "I": 12}
    for k, v in widths.items():
        ws.column_dimensions[k].width = v
    ws.freeze_panes = "A6"

    # ---------------- Actions ----------------
    ws_a = wb.create_sheet("Actions", 1)
    ws_a["A1"] = "Suggested action by RFM segment"
    ws_a["A1"].font = TITLE
    ws_a["A2"] = "A starting playbook to test, not a proven result. Measure each action against a hold-out group."
    ws_a["A2"].font = NOTE
    acts = pd.DataFrame({"RFM segment": list(ACTIONS), "Suggested action": list(ACTIONS.values())})
    a_last = _table(ws_a, acts, 4)
    for r in range(5, a_last + 1):
        ws_a.cell(row=r, column=2).alignment = Alignment(wrap_text=True, vertical="top")
    ws_a.column_dimensions["A"].width = 22
    ws_a.column_dimensions["B"].width = 95

    # ---------------- Customer lookup ----------------
    ws_l = wb.create_sheet("Customer_Lookup", 1)
    ws_l["A1"] = "Look up a customer"
    ws_l["A1"].font = TITLE
    ws_l["A3"] = "Customer ID"
    ws_l["B3"] = int(data["Customer ID"].iloc[0])
    ws_l["B3"].font, ws_l["B3"].fill = INPUT_FONT, INPUT_FILL
    ws_l["C3"] = "type any customer ID from the Customers sheet"
    ws_l["C3"].font = NOTE
    ws_l["A4"] = "Found"
    ws_l["B4"] = f'=IF(ISNUMBER(MATCH($B$3,{R["Customer ID"]},0)),"yes","not in this snapshot")'
    fields = ["Country", "Days since last order", "Orders (12m)", "Net spend (12m)", "R", "F", "M",
              "RFM segment", "Cluster name", "Ordered again (next 6m)", "Net spend (next 6m)"]
    for i, f in enumerate(fields, start=6):
        ws_l.cell(row=i, column=1, value=f)
        ws_l.cell(row=i, column=2, value=f'=IFERROR(INDEX({R[f]},MATCH($B$3,{R["Customer ID"]},0)),"")')
        if "spend" in f.lower():
            ws_l.cell(row=i, column=2).number_format = "£#,##0.00"
    act_row = 6 + len(fields)
    ws_l.cell(row=act_row, column=1, value="Suggested action").font = BOLD
    ws_l.cell(row=act_row, column=2, value=f'=IFERROR(INDEX(Actions!$B$5:$B${a_last},'
              f'MATCH(B{6 + fields.index("RFM segment")},Actions!$A$5:$A${a_last},0)),"")')
    ws_l.cell(row=act_row, column=2).alignment = Alignment(wrap_text=True, vertical="top")
    for r in range(3, act_row + 1):
        ws_l.cell(row=r, column=2).alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
    ws_l.column_dimensions["A"].width = 26
    ws_l.column_dimensions["B"].width = 60

    # ---------------- Migration ----------------
    ws_m = wb.create_sheet("Migration", 3)
    ws_m["A1"] = "Segment movement, December 2010 to June 2011 (static, from Python)"
    ws_m["A1"].font = TITLE
    ws_m["A2"] = "Rows: segment in December 2010. Columns: segment in June 2011. Each row sums to 100%."
    ws_m["A2"].font = NOTE
    mig = migration.reset_index().rename(columns={migration.index.name or "index": "December 2010"})
    m_last = _table(ws_m, mig, 4, formats={c: "0%" for c in mig.columns[1:]})
    ws_m.conditional_formatting.add(f"B5:{get_column_letter(mig.shape[1])}{m_last}", ColorScaleRule(
        start_type="num", start_value=0, start_color="FFFFFF", end_type="max", end_color="3987E5"))
    ws_m.column_dimensions["A"].width = 22
    for i in range(2, mig.shape[1] + 1):
        ws_m.column_dimensions[get_column_letter(i)].width = 12
    ws_m.row_dimensions[4].height = 45

    # ---------------- Validation ----------------
    ws_v = wb.create_sheet("Validation", 4)
    ws_v["A1"] = "Do the segments predict what customers did next? (static, from Python)"
    ws_v["A1"].font = TITLE
    ws_v["A2"] = ("Segments built on December 2010 data, applied at June 2011 and scored on June to November "
                  "2011. AUC: 0.5 = coin toss, 1 = perfect. Spearman: rank correlation with actual spend.")
    ws_v["A2"].font = NOTE
    vv = validation.reset_index(drop=True)[["label", "segments", "repeat_auc", "repeat_auc_low", "repeat_auc_high",
                                            "spend_spearman", "spend_spearman_low", "spend_spearman_high"]]
    vv.columns = ["Scheme", "Groups", "Repeat AUC", "AUC low", "AUC high", "Spend Spearman", "Spearman low",
                  "Spearman high"]
    _table(ws_v, vv, 4, formats={c: "0.000" for c in vv.columns[2:]})
    ws_v.column_dimensions["A"].width = 42
    for c in "BCDEFGH":
        ws_v.column_dimensions[c].width = 12

    # ---------------- Cleaning log ----------------
    ws_q = wb.create_sheet("Cleaning_Log", 5)
    ws_q["A1"] = "Where every raw row went"
    ws_q["A1"].font = TITLE
    q = cleaning_log[["reason", "description", "rows", "share_of_rows", "value"]].copy()
    q.columns = ["Outcome", "Rule", "Rows", "Share of rows", "Line value (£)"]
    q_last = _table(ws_q, q, 3, formats={"Rows": INT, "Share of rows": PCT, "Line value (£)": "£#,##0.00"})
    for r in range(4, q_last + 1):
        ws_q.cell(row=r, column=2).alignment = Alignment(wrap_text=True, vertical="top")
    ws_q.cell(row=q_last + 2, column=1, value="Raw rows").font = BOLD
    ws_q.cell(row=q_last + 2, column=3, value=reconciliation["raw_rows"]).number_format = INT
    ws_q.cell(row=q_last + 3, column=1, value="Raw line value").font = BOLD
    ws_q.cell(row=q_last + 3, column=5, value=round(reconciliation["raw_value"], 2)).number_format = "£#,##0.00"
    ws_q.cell(row=q_last + 4, column=1, value="Check: rows and value balance").font = BOLD
    ws_q.cell(row=q_last + 4, column=3, value=f'=IF(SUM(C4:C{q_last})=C{q_last + 2},"balanced","CHECK")')
    ws_q.cell(row=q_last + 4, column=5,
              value=f'=IF(ABS(SUM(E4:E{q_last})-E{q_last + 3})<0.01,"balanced","CHECK")')
    for k, v in {"A": 30, "B": 60, "C": 12, "D": 10, "E": 16}.items():
        ws_q.column_dimensions[k].width = v

    # ---------------- About ----------------
    ws_ab = wb.create_sheet("About", 0)
    lines = [
        ("Customer segmentation pack", TITLE),
        (f"Generated {generated} by retail-customer-segmentation.", NOTE),
        ("", BODY),
        ("Segment_Summary - live tables for RFM and k-means segments, filterable by market.", BODY),
        ("Customer_Lookup - type a customer ID to see their scores, segment and suggested action.", BODY),
        ("Actions - suggested treatment per RFM segment (a playbook to test).", BODY),
        ("Migration - how customers moved between segments in six months.", BODY),
        ("Validation - how well each segmentation predicted what customers did next.", BODY),
        ("Cleaning_Log - every raw row accounted for, with a balance check.", BODY),
        ("Customers - one row per customer at the snapshot; the live sheets read from here.", BODY),
        ("", BODY),
        ("Definitions", BOLD),
        ("Net spend: product sales minus returns, excluding postage, fees and adjustments.", BODY),
        ("R, F, M: 1-5 scores from percentile ranks of days since last order, orders and net spend in the "
         "12 months before the snapshot (5 = best). Ties get the same score.", BODY),
        ("Yellow cells are inputs. Everything on Segment_Summary and Customer_Lookup is a formula.", BODY),
        ("", BODY),
        ("Source data", BOLD),
        ("Online Retail II, UCI Machine Learning Repository (Chen, 2012), CC BY 4.0. A UK-based online "
         "retailer of gift-ware; many customers are wholesalers.", BODY),
    ]
    for i, (txt, f) in enumerate(lines, start=1):
        ws_ab.cell(row=i, column=1, value=txt).font = f
    ws_ab.column_dimensions["A"].width = 110

    for w in wb.worksheets:
        w.sheet_view.showGridLines = w.title == "Customers"
        _arial(w)
    wb.active = wb.sheetnames.index("Segment_Summary")
    wb.save(path)
    return path
