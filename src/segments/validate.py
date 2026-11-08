"""Out-of-time validation: do segments built on one snapshot predict the next?

For each scheme, segment-level repeat rates and average spend are learned from
the fit snapshot's outcomes (Dec 2010 to May 2011). Customers at the test
snapshot (June 2011) are assigned to segments with the same rules or model,
given their segment's learned values as predictions, and scored against what
they actually did from June to November 2011.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.metrics import roc_auc_score


def segment_stats(df: pd.DataFrame, col: str) -> pd.DataFrame:
    return df.groupby(col).agg(customers=("repeat", "size"), repeat_rate=("repeat", "mean"),
                               mean_next_spend=("next_spend", "mean"))


def predictions(fit_df: pd.DataFrame, test_df: pd.DataFrame, col: str) -> tuple[np.ndarray, np.ndarray]:
    learned = segment_stats(fit_df, col)
    p_rep = test_df[col].map(learned["repeat_rate"]).fillna(fit_df["repeat"].mean())
    p_spend = test_df[col].map(learned["mean_next_spend"]).fillna(fit_df["next_spend"].mean())
    return p_rep.to_numpy(dtype=float), p_spend.to_numpy(dtype=float)


def evaluate(fit_df: pd.DataFrame, test_df: pd.DataFrame, col: str) -> tuple[dict, pd.DataFrame]:
    learned = segment_stats(fit_df, col)
    p_rep, p_spend = predictions(fit_df, test_df, col)
    y = test_df["repeat"].astype(int)
    metrics = {
        "segments": int(test_df[col].nunique()),
        "repeat_auc": float(roc_auc_score(y, p_rep)),
        "spend_spearman": float(stats.spearmanr(p_spend, test_df["next_spend"]).statistic),
    }
    observed = segment_stats(test_df, col)
    calib = learned.add_suffix("_fit").join(observed.add_suffix("_test"), how="outer")
    return metrics, calib


def evaluate_scores(test_df: pd.DataFrame, repeat_score: np.ndarray, spend_score: np.ndarray) -> dict:
    return {
        "segments": None,
        "repeat_auc": float(roc_auc_score(test_df["repeat"].astype(int), repeat_score)),
        "spend_spearman": float(stats.spearmanr(spend_score, test_df["next_spend"]).statistic),
    }


def bootstrap(test_df: pd.DataFrame, scores: dict[str, tuple[np.ndarray, np.ndarray]], reps: int,
              seed: int) -> dict[str, dict[str, list[float]]]:
    """95% bootstrap intervals for each scheme's repeat AUC and spend Spearman on the test customers."""
    rng = np.random.default_rng(seed)
    y = test_df["repeat"].astype(int).to_numpy()
    spend = test_df["next_spend"].to_numpy()
    draws: dict[str, dict[str, list[float]]] = {k: {"repeat_auc": [], "spend_spearman": []} for k in scores}
    for _ in range(reps):
        idx = rng.integers(0, len(y), len(y))
        for k, (p_rep, p_spend) in scores.items():
            draws[k]["repeat_auc"].append(roc_auc_score(y[idx], p_rep[idx]))
            draws[k]["spend_spearman"].append(stats.spearmanr(p_spend[idx], spend[idx]).statistic)
    return {k: {m: [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))] for m, v in d.items()}
            for k, d in draws.items()}


def value_capture(test_df: pd.DataFrame, col: str, fit_df: pd.DataFrame) -> pd.DataFrame:
    """Segments ranked by learned spend: cumulative share of customers and of next-6-month spend."""
    learned = segment_stats(fit_df, col)["mean_next_spend"]
    obs = test_df.groupby(col).agg(customers=("next_spend", "size"), next_spend=("next_spend", "sum"),
                                   repeat_rate=("repeat", "mean"))
    obs["learned_mean_spend"] = learned.reindex(obs.index)
    obs = obs.sort_values("learned_mean_spend", ascending=False)
    obs["share_customers"] = obs["customers"] / obs["customers"].sum()
    obs["share_next_spend"] = obs["next_spend"] / obs["next_spend"].sum()
    obs["cum_customers"] = obs["share_customers"].cumsum()
    obs["cum_next_spend"] = obs["share_next_spend"].cumsum()
    return obs


def migration(fit_df: pd.DataFrame, test_df: pd.DataFrame, col: str, order: list[str]) -> pd.DataFrame:
    """Row-normalised movement between segments; customers with no purchase in the
    test lookback are counted as 'No purchase in 12 months'."""
    to = test_df[col].reindex(fit_df.index).fillna("No purchase in 12 months")
    tab = pd.crosstab(fit_df[col], to, normalize="index")
    cols = [c for c in order if c in tab.columns] + (["No purchase in 12 months"]
                                                      if "No purchase in 12 months" in tab.columns else [])
    rows = [r for r in order if r in tab.index]
    return tab.loc[rows, cols]
