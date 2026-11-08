"""Analysis settings. Every date and threshold the pipeline uses lives here."""

from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class Settings:
    # Two snapshots, six months apart. Segments are built at the first and
    # judged on what customers did after the second, which they never saw.
    snapshot_fit: str = "2010-12-01"
    snapshot_test: str = "2011-06-01"
    lookback_months: int = 12   # behaviour window before a snapshot
    horizon_months: int = 6     # outcome window after a snapshot

    k_min: int = 2
    k_max: int = 8
    k_floor: int = 3            # fewer than 3 segments is too coarse to act on
    stability_reps: int = 30
    stability_min_ari: float = 0.80
    bootstrap_reps: int = 500
    seed: int = 11

    def ts(self, name: str) -> pd.Timestamp:
        return pd.Timestamp(getattr(self, name))

    def window(self, snapshot: str) -> dict[str, pd.Timestamp]:
        s = self.ts(snapshot)
        return {
            "lookback_start": s - pd.DateOffset(months=self.lookback_months),
            "snapshot": s,
            "horizon_end": s + pd.DateOffset(months=self.horizon_months),
        }


SETTINGS = Settings()

# Stock codes that are charges, fees, adjustments or vouchers, not products.
NON_PRODUCT_CODES = {
    "POST", "DOT", "M", "m", "C2", "C3", "D", "S", "BANK CHARGES", "ADJUST", "ADJUST2",
    "AMAZONFEE", "B", "CRUK", "TEST001", "TEST002", "PADS", "GIFT",
}
NON_PRODUCT_PATTERN = re.compile(r"^gift_0001_")
