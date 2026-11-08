"""Typed loading with a schema contract."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

COLUMNS = ["Invoice", "StockCode", "Description", "Quantity", "InvoiceDate", "Price", "Customer ID", "Country"]
FILES = ["online_retail_II.csv", "online_retail_II2.csv"]
DATE_FORMAT = "%d/%m/%Y %H:%M"  # day first: 01/12/2009 is 1 December


class ContractError(ValueError):
    """Raised when an input file breaks the schema contract."""


def validate(df: pd.DataFrame, name: str) -> pd.DataFrame:
    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        raise ContractError(f"{name}: missing columns {missing}")
    out = df.copy()
    dates = pd.to_datetime(out["InvoiceDate"], format=DATE_FORMAT, errors="coerce")
    if dates.isna().any():
        raise ContractError(f"{name}: {int(dates.isna().sum())} dates not in dd/mm/yyyy hh:mm form")
    out["InvoiceDate"] = dates
    for col in ("Quantity", "Price"):
        num = pd.to_numeric(out[col], errors="coerce")
        if num.isna().any():
            raise ContractError(f"{name}: {int(num.isna().sum())} non-numeric values in {col}")
        out[col] = num
    if out["Invoice"].isna().any() or out["StockCode"].isna().any():
        raise ContractError(f"{name}: blank Invoice or StockCode")
    # Customer IDs arrive as '13085.0' in one file and '13085' in the other.
    cid = out["Customer ID"].astype("string").str.replace(r"\.0$", "", regex=True)
    if not cid.dropna().str.fullmatch(r"\d{5}").all():
        raise ContractError(f"{name}: customer IDs are not 5-digit numbers")
    out["Customer ID"] = cid
    return out


def load(raw_dir: Path) -> pd.DataFrame:
    frames = []
    for i, name in enumerate(FILES, start=1):
        df = pd.read_csv(raw_dir / name, dtype=str, encoding="utf-8-sig", keep_default_na=True)
        df = validate(df, name)
        df["source_file"] = i
        df["source_row"] = range(len(df))
        frames.append(df)
    return pd.concat(frames, ignore_index=True)
