"""Reason-coded cleaning with a revenue reconciliation.

Every raw row ends up in exactly one place: purchases, returns, or quarantine
with a single reason (the first rule it breaks, in the order below). The
reconciliation proves nothing was lost: raw value = purchases + returns +
quarantined value, to the penny.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .config import NON_PRODUCT_CODES, NON_PRODUCT_PATTERN

KEY = ["Invoice", "StockCode", "Description", "Quantity", "InvoiceDate", "Price", "Customer ID", "Country"]

RULES = [
    ("overlap_duplicate", "Row from the 2010-11 file that repeats a row already in the 2009-10 file (1-9 Dec 2010)"),
    ("missing_customer", "No customer ID, so it cannot be tied to a customer"),
    ("non_product", "Postage, fees, manual adjustments, bad-debt write-offs, vouchers or test lines"),
    ("bad_price", "Price of zero or less"),
    ("bad_quantity", "Zero or negative quantity on a normal invoice, or positive quantity on a cancellation"),
    ("exact_duplicate", "Identical to an earlier row in every field"),
]


@dataclass
class CleanResult:
    purchases: pd.DataFrame
    returns: pd.DataFrame
    quarantine: pd.DataFrame
    log: pd.DataFrame
    reconciliation: dict
    overlap_check: dict


def _is_non_product(codes: pd.Series) -> pd.Series:
    return codes.isin(NON_PRODUCT_CODES) | codes.str.match(NON_PRODUCT_PATTERN)


def overlap_rows(df: pd.DataFrame) -> tuple[pd.Series, dict]:
    """Flag file-2 rows that fall inside file 1's date range, and check they really are copies."""
    f1, f2 = df["source_file"] == 1, df["source_file"] == 2
    if not f1.any() or not f2.any():
        return pd.Series(False, index=df.index), {"rows": 0, "matched": 0, "unmatched": 0}
    end1, start2 = df.loc[f1, "InvoiceDate"].max(), df.loc[f2, "InvoiceDate"].min()
    flag = f2 & (df["InvoiceDate"] <= end1)
    def counts(rows: pd.DataFrame) -> pd.Series:
        return rows[KEY].astype(object).fillna("<blank>").astype(str).value_counts(dropna=False)

    a = counts(df.loc[f1 & (df["InvoiceDate"] >= start2)])
    b = counts(df.loc[flag])
    matched = int(np.minimum(a, b.reindex(a.index, fill_value=0)).sum())
    return flag, {"rows": int(flag.sum()), "matched": matched, "unmatched": int(flag.sum()) - matched,
                  "from": f"{start2:%Y-%m-%d}", "to": f"{end1:%Y-%m-%d}"}


def clean(df: pd.DataFrame) -> CleanResult:
    d = df.copy()
    d["value"] = d["Quantity"] * d["Price"]
    is_cancel = d["Invoice"].str.startswith("C")
    reason = pd.Series(pd.NA, index=d.index, dtype="string")

    def assign(mask: pd.Series, name: str) -> None:
        reason[mask & reason.isna()] = name

    ov, overlap_check = overlap_rows(d)
    assign(ov, "overlap_duplicate")
    assign(d["Customer ID"].isna(), "missing_customer")
    assign(_is_non_product(d["StockCode"]), "non_product")
    assign(d["Price"] <= 0, "bad_price")
    assign((~is_cancel & (d["Quantity"] <= 0)) | (is_cancel & (d["Quantity"] >= 0)), "bad_quantity")
    still = reason.isna()
    dup = d.loc[still].duplicated(subset=KEY, keep="first")
    assign(dup.reindex(d.index, fill_value=False), "exact_duplicate")
    d["reason"] = reason

    ok = d["reason"].isna()
    purchases = d[ok & ~is_cancel].drop(columns="reason")
    returns = d[ok & is_cancel].drop(columns="reason")
    quarantine = d[~ok]

    rows = [{"reason": "purchase", "description": "Kept: product sale to a known customer",
             "rows": len(purchases), "value": float(purchases["value"].sum())},
            {"reason": "return", "description": "Kept: cancelled product line from a known customer",
             "rows": len(returns), "value": float(returns["value"].sum())}]
    for name, desc in RULES:
        q = quarantine[quarantine["reason"] == name]
        rows.append({"reason": name, "description": desc, "rows": len(q), "value": float(q["value"].sum())})
    log = pd.DataFrame(rows)
    log["share_of_rows"] = log["rows"] / len(d)

    raw_value = float(d["value"].sum())
    accounted = float(log["value"].sum())
    reconciliation = {
        "raw_rows": len(d), "accounted_rows": int(log["rows"].sum()),
        "raw_value": raw_value, "accounted_value": accounted,
        "difference": raw_value - accounted,
        "balanced": bool(len(d) == log["rows"].sum() and abs(raw_value - accounted) < 0.005),
    }
    return CleanResult(purchases, returns, quarantine, log, reconciliation, overlap_check)
