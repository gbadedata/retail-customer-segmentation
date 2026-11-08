"""Customer features at a snapshot date, and what each customer did next.

Features use only transactions before the snapshot. Outcomes use only the
horizon after it. A customer is in the base if they bought at least once in
the lookback window and their net spend there is positive.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import SETTINGS, Settings

CID = "Customer ID"


def snapshot(purchases: pd.DataFrame, returns: pd.DataFrame, which: str, s: Settings = SETTINGS) -> pd.DataFrame:
    w = s.window(which)
    snap, start, end = w["snapshot"], w["lookback_start"], w["horizon_end"]

    hist = purchases[purchases["InvoiceDate"] < snap]
    lb = hist[hist["InvoiceDate"] >= start]
    lb_ret = returns[(returns["InvoiceDate"] >= start) & (returns["InvoiceDate"] < snap)]

    g = lb.groupby(CID).agg(
        frequency=("Invoice", "nunique"),
        gross_spend=("value", "sum"),
        products=("StockCode", "nunique"),
    )
    g["returns_value"] = lb_ret.groupby(CID)["value"].sum().reindex(g.index, fill_value=0.0)
    g["monetary"] = g["gross_spend"] + g["returns_value"]  # returns are negative
    h = hist[hist[CID].isin(g.index)].groupby(CID)["InvoiceDate"].agg(["min", "max"])
    g["recency_days"] = (snap - h["max"]).dt.days
    g["tenure_days"] = (snap - h["min"]).dt.days
    g["avg_order_value"] = g["monetary"] / g["frequency"]
    g["return_rate"] = (-g["returns_value"] / g["gross_spend"]).clip(lower=0)
    g["country"] = lb.groupby(CID)["Country"].agg(lambda x: x.mode().iat[0])

    # Inputs for the BG/NBD model (weeks, full history before the snapshot).
    days = hist[hist[CID].isin(g.index)].assign(day=lambda x: x["InvoiceDate"].dt.normalize())
    dg = days.groupby(CID)["day"].agg(["nunique", "min", "max"])
    g["bg_x"] = dg["nunique"] - 1
    g["bg_t_x"] = (dg["max"] - dg["min"]).dt.days / 7
    g["bg_T"] = (snap.normalize() - dg["min"]).dt.days / 7

    # What happened next.
    fut = purchases[(purchases["InvoiceDate"] >= snap) & (purchases["InvoiceDate"] < end)]
    fut_ret = returns[(returns["InvoiceDate"] >= snap) & (returns["InvoiceDate"] < end)]
    nxt = fut.groupby(CID).agg(next_orders=("Invoice", "nunique"), next_gross=("value", "sum"))
    g = g.join(nxt, how="left")
    g[["next_orders", "next_gross"]] = g[["next_orders", "next_gross"]].fillna(0)
    g["next_returns"] = fut_ret.groupby(CID)["value"].sum().reindex(g.index, fill_value=0.0)
    g["next_spend"] = g["next_gross"] + g["next_returns"]
    g["repeat"] = g["next_orders"] > 0

    g.attrs.update({"snapshot": f"{snap:%Y-%m-%d}", "lookback_start": f"{start:%Y-%m-%d}",
                    "horizon_end": f"{end:%Y-%m-%d}", "excluded_non_positive": int((g["monetary"] <= 0).sum())})
    out = g[g["monetary"] > 0].copy()
    out.attrs = g.attrs
    return out


def pareto(spend: pd.Series, shares=(0.1, 0.2, 0.5)) -> dict[str, float]:
    v = np.sort(spend.to_numpy())[::-1]
    total = v.sum()
    return {f"top_{int(p * 100)}pct": float(v[: int(round(p * len(v)))].sum() / total) for p in shares}
