"""Synthetic transactions shaped like Online Retail II, so tests run offline."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


def make_transactions(n_customers: int = 400, seed: int = 3) -> pd.DataFrame:
    """Customers of three kinds (heavy, regular, one-off) buying over two years."""
    rng = np.random.default_rng(seed)
    start, end = pd.Timestamp("2009-12-01"), pd.Timestamp("2011-12-09")
    span = (end - start).days
    rows = []
    inv = 500000
    for c in range(n_customers):
        cid = f"{12000 + c}"
        kind = rng.choice(["heavy", "regular", "oneoff"], p=[0.15, 0.45, 0.40])
        n_orders = {"heavy": rng.integers(15, 40), "regular": rng.integers(2, 8), "oneoff": 1}[kind]
        first = rng.integers(0, span - 30)
        days = np.sort(rng.integers(first, span, n_orders))
        country = "United Kingdom" if rng.random() < 0.85 else "France"
        for d in days:
            inv += 1
            when = start + pd.Timedelta(days=int(d), hours=10)
            for _ in range(rng.integers(1, 4)):
                rows.append({"Invoice": str(inv), "StockCode": f"{rng.integers(10000, 99999)}",
                             "Description": "ITEM", "Quantity": int(rng.integers(1, 24)),
                             "InvoiceDate": when, "Price": float(rng.choice([0.85, 1.65, 2.95, 4.95])),
                             "Customer ID": cid, "Country": country})
    df = pd.DataFrame(rows)
    df["source_file"] = np.where(df["InvoiceDate"] < pd.Timestamp("2010-12-01"), 1, 2)
    df["source_row"] = range(len(df))
    return df


@pytest.fixture(scope="session")
def tx() -> pd.DataFrame:
    return make_transactions()
