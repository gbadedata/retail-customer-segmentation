"""RFM scores and named segments.

Scores are 1-5 from percentile ranks with ties averaged, so two customers with
identical behaviour always get the same score. (Quintiles on a ranked-first
basis would split the many one-order customers between scores at random.)
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

# A commonly used recency-by-frequency grid. Order matters: first match wins.
SEGMENT_GRID: list[tuple[str, str]] = [
    (r"5[4-5]", "Champions"),
    (r"[3-4][4-5]", "Loyal"),
    (r"[1-2]5", "Can't lose them"),
    (r"[1-2][3-4]", "At risk"),
    (r"[1-2][1-2]", "Hibernating"),
    (r"3[1-2]", "About to sleep"),
    (r"33", "Need attention"),
    (r"41", "Promising"),
    (r"51", "New customers"),
    (r"[4-5][2-3]", "Potential loyalists"),
]
SEGMENT_ORDER = ["Champions", "Loyal", "Potential loyalists", "New customers", "Promising", "Need attention",
                 "About to sleep", "Can't lose them", "At risk", "Hibernating"]

ACTIONS = {
    "Champions": "Reward and protect: early access, account contact, ask for referrals.",
    "Loyal": "Grow the basket: cross-sell related ranges and volume offers.",
    "Potential loyalists": "Build the habit: loyalty or reorder reminders around their usual cycle.",
    "New customers": "Onboard: second-order incentive within the first month.",
    "Promising": "Nurture: range highlights and a light second-order offer.",
    "Need attention": "Re-engage: time-limited offers on lines they already buy.",
    "About to sleep": "Reactivate early: reminder and best-seller showcase before they lapse.",
    "Can't lose them": "Win back personally: call or email from a named contact; find out why they stopped.",
    "At risk": "Win back: personalised offer on past purchases.",
    "Hibernating": "Low-cost only: occasional email; do not spend on paid reactivation.",
}


def score(values: pd.Series, higher_is_better: bool = True) -> pd.Series:
    v = values if higher_is_better else -values
    pct = v.rank(pct=True, method="average")
    return np.ceil(pct * 5).clip(1, 5).astype(int)


def add_rfm(features: pd.DataFrame) -> pd.DataFrame:
    df = features.copy()
    df["r_score"] = score(df["recency_days"], higher_is_better=False)
    df["f_score"] = score(df["frequency"])
    df["m_score"] = score(df["monetary"])
    df["rfm_sum"] = df[["r_score", "f_score", "m_score"]].sum(axis=1)
    rf = df["r_score"].astype(str) + df["f_score"].astype(str)
    df["rfm_segment"] = rf.map(segment_for)
    return df


def segment_for(rf: str) -> str:
    for pattern, name in SEGMENT_GRID:
        if re.fullmatch(pattern, rf):
            return name
    raise ValueError(f"RF code {rf} not covered by the grid")
