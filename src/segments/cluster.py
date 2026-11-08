"""K-means segmentation with an explicit, pre-declared rule for choosing k.

Rule: among k >= k_floor whose bootstrap stability (mean adjusted Rand index
against the full-data solution) is at least stability_min_ari, pick the k with
the highest silhouette. Clusters are relabelled by average spend so labels
are stable between runs, and named from where their medians sit in the
customer population.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import adjusted_rand_score, calinski_harabasz_score, davies_bouldin_score, silhouette_score
from sklearn.preprocessing import StandardScaler

from .config import SETTINGS, Settings

FEATURES = ["recency_days", "frequency", "monetary"]


def matrix(features: pd.DataFrame) -> np.ndarray:
    return np.log1p(features[FEATURES].to_numpy(dtype=float))


def select_k(X: np.ndarray, s: Settings = SETTINGS) -> tuple[pd.DataFrame, int]:
    Z = StandardScaler().fit_transform(X)
    rng = np.random.default_rng(s.seed)
    rows = []
    for k in range(s.k_min, s.k_max + 1):
        ref = KMeans(n_clusters=k, n_init=10, random_state=s.seed).fit(Z)
        aris = []
        for _ in range(s.stability_reps):
            idx = rng.integers(0, len(Z), len(Z))
            km = KMeans(n_clusters=k, n_init=5, random_state=int(rng.integers(1e9))).fit(Z[idx])
            aris.append(adjusted_rand_score(ref.labels_, km.predict(Z)))
        rows.append({
            "k": k, "inertia": float(ref.inertia_),
            "silhouette": float(silhouette_score(Z, ref.labels_, sample_size=min(len(Z), 5000), random_state=s.seed)),
            "davies_bouldin": float(davies_bouldin_score(Z, ref.labels_)),
            "calinski_harabasz": float(calinski_harabasz_score(Z, ref.labels_)),
            "ari_mean": float(np.mean(aris)), "ari_min": float(np.min(aris)),
        })
    t = pd.DataFrame(rows)
    t["stable"] = t["ari_mean"] >= s.stability_min_ari
    eligible = t[(t["k"] >= s.k_floor) & t["stable"]]
    if eligible.empty:
        eligible = t[t["k"] >= s.k_floor]
    chosen = int(eligible.sort_values(["silhouette", "k"], ascending=[False, True]).iloc[0]["k"])
    t["chosen"] = t["k"] == chosen
    return t, chosen


@dataclass
class SegmentModel:
    scaler: StandardScaler
    kmeans: KMeans
    relabel: dict[int, int]
    names: dict[int, str]
    tertiles: dict[str, list[float]]

    def predict(self, features: pd.DataFrame) -> pd.Series:
        raw = self.kmeans.predict(self.scaler.transform(matrix(features)))
        return pd.Series([self.relabel[c] for c in raw], index=features.index, name="cluster")


def _word(value: float, cuts: list[float], words: tuple[str, str, str]) -> str:
    return words[0] if value <= cuts[0] else words[1] if value <= cuts[1] else words[2]


def fit(features: pd.DataFrame, k: int, s: Settings = SETTINGS) -> SegmentModel:
    X = matrix(features)
    scaler = StandardScaler().fit(X)
    km = KMeans(n_clusters=k, n_init=20, random_state=s.seed).fit(scaler.transform(X))
    lab = pd.Series(km.labels_, index=features.index)
    order = features.groupby(lab)["monetary"].mean().sort_values(ascending=False).index
    relabel = {int(old): new for new, old in enumerate(order, start=1)}
    tert = {c: list(np.quantile(features[c], [1 / 3, 2 / 3])) for c in FEATURES}
    names = {}
    for old, new in relabel.items():
        med = features[lab == old][FEATURES].median()
        r = _word(med["recency_days"], tert["recency_days"], ("recent", "lapsing", "lapsed"))
        f = _word(med["frequency"], tert["frequency"], ("infrequent", "regular", "frequent"))
        m = _word(med["monetary"], tert["monetary"], ("low spend", "mid spend", "high spend"))
        names[new] = f"{r}, {f}, {m}"
    seen: dict[str, int] = {}
    for c in sorted(names):  # make names unique if two clusters share descriptors
        seen[names[c]] = seen.get(names[c], 0) + 1
        if seen[names[c]] > 1:
            names[c] = f"{names[c]} ({seen[names[c]]})"
    return SegmentModel(scaler, km, relabel, names, tert)
