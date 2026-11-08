"""Static charts for the README and report."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#8a8984"
GRID = "#e4e3df"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
BLUES = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]


def _style() -> None:
    plt.rcParams.update({
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
        "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
        "text.color": INK, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
        "axes.spines.top": False, "axes.spines.right": False, "font.size": 10,
        "axes.titlesize": 12, "axes.titleweight": "bold", "axes.titlelocation": "left",
        "lines.linewidth": 2, "legend.frameon": False,
    })


def _pct(ax, axis: str = "y") -> None:
    fmt = matplotlib.ticker.PercentFormatter(1.0, decimals=0)
    (ax.yaxis if axis == "y" else ax.xaxis).set_major_formatter(fmt)


LABELS = {
    "purchase": "Kept: purchases", "return": "Kept: returns", "overlap_duplicate": "Overlap between files",
    "missing_customer": "No customer ID", "non_product": "Postage, fees, adjustments",
    "bad_price": "Zero or negative price", "bad_quantity": "Bad quantity", "exact_duplicate": "Exact duplicate",
}


def cleaning(log: pd.DataFrame, path: Path) -> None:
    _style()
    d = log[log["rows"] > 0].iloc[::-1]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 3.8), sharey=True)
    y = np.arange(len(d))
    names = [LABELS.get(r, r) for r in d["reason"]]
    kept = d["reason"].isin(["purchase", "return"]).to_numpy()
    colors = [SERIES[0] if k else MUTED for k in kept]
    a1.barh(y, d["rows"], color=colors, height=0.6)
    for i, v in enumerate(d["rows"]):
        a1.text(v, i, f" {v:,.0f}", va="center", fontsize=8.5, color=INK2)
    a1.set_yticks(y, names)
    a1.set_xlim(0, d["rows"].max() * 1.3)
    a1.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v / 1e3:,.0f}k"))
    a1.set_title("Rows")
    a2.barh(y, d["value"] / 1e6, color=colors, height=0.6)
    for i, v in enumerate(d["value"] / 1e6):
        label = f" -£{abs(v):,.2f}m" if v < 0 else f" £{v:,.2f}m"
        a2.text(max(v, 0), i, label, va="center", fontsize=8.5, color=INK2)
    a2.axvline(0, color=INK2, lw=0.8)
    a2.set_xlim(min(-1, d["value"].min() / 1e6 * 1.3), d["value"].max() / 1e6 * 1.3)
    a2.set_title("Line value (£m)")
    fig.suptitle("Where every raw row went (1,067,371 rows; value reconciles to the penny)",
                 x=0.01, ha="left", fontsize=12, fontweight="bold")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def choose_k(t: pd.DataFrame, min_ari: float, path: Path) -> None:
    _style()
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(9.5, 3.6))
    k = t["k"].to_numpy()
    chosen = int(t.loc[t["chosen"], "k"].iloc[0])
    a1.plot(k, t["silhouette"], "o-", color=SERIES[0], ms=7)
    a2.plot(k, t["ari_mean"], "o-", color=SERIES[0], ms=7)
    a2.axhline(min_ari, color=INK2, lw=1, ls="--")
    a2.text(k.max(), min_ari, f"stability threshold {min_ari:.2f} ", ha="right", va="bottom", fontsize=8.5,
            color=INK2)
    for a, col in ((a1, "silhouette"), (a2, "ari_mean")):
        v = float(t.loc[t["k"] == chosen, col].iloc[0])
        a.plot(chosen, v, "o", ms=13, mfc="none", mec=INK, mew=1.5)
        a.annotate(f"k = {chosen}", (chosen, v), textcoords="offset points", xytext=(8, 8), fontsize=9)
        a.set_xticks(k)
        a.set_xlabel("Number of segments (k)")
    a1.set_title("Separation (silhouette)")
    a2.set_title("Stability (bootstrap ARI)")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def profiles(prof: pd.DataFrame, path: Path) -> None:
    _style()
    fig, axes = plt.subplots(1, 4, figsize=(11, 3.4), sharey=True)
    y = np.arange(len(prof))[::-1]
    cols = [("customers", "Customers", "{:,.0f}"), ("median_recency_days", "Days since last order (median)", "{:.0f}"),
            ("median_orders", "Orders in 12 months (median)", "{:.0f}"),
            ("median_spend_12m", "Spend in 12 months (median, £)", "£{:,.0f}")]
    for ax, (c, title, fmt) in zip(axes, cols, strict=True):
        ax.barh(y, prof[c], color=SERIES[0], height=0.55)
        for yy, v in zip(y, prof[c], strict=True):
            ax.text(v, yy, " " + fmt.format(v), va="center", fontsize=8.5, color=INK2)
        ax.set_xlim(0, prof[c].max() * 1.45)
        ax.set_title(title, fontsize=9.5)
        ax.tick_params(axis="x", labelsize=8)
    axes[0].set_yticks(y, [f"{i}. {n}" for i, n in zip(prof.index, prof["name"], strict=True)])
    fig.suptitle("K-means segments at June 2011 (fitted on December 2010)", x=0.01, ha="left", fontsize=12,
                 fontweight="bold")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def validation(v: pd.DataFrame, path: Path) -> None:
    _style()
    d = v.sort_values("repeat_auc")
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 3.8), sharey=True)
    y = np.arange(len(d))
    for ax, m in ((a1, "repeat_auc"), (a2, "spend_spearman")):
        for i, (_, r) in enumerate(d.iterrows()):
            ax.plot([r[f"{m}_low"], r[f"{m}_high"]], [i, i], color=SERIES[0])
            ax.plot(r[m], i, "o", ms=8, color=SERIES[0])
            ax.text(r[f"{m}_high"] + 0.004, i, f" {r[m]:.3f}", va="center", fontsize=8.5, color=INK2)
    a1.set_yticks(y, d["label"])
    a1.set_title("Who buys again (ROC AUC)")
    a2.set_title("How much they spend (Spearman)")
    a1.set_xlabel("Jun-Nov 2011, 95% bootstrap interval")
    a2.set_xlabel("Jun-Nov 2011, 95% bootstrap interval")
    for ax, m in ((a1, "repeat_auc"), (a2, "spend_spearman")):
        lo, hi = d[f"{m}_low"].min(), d[f"{m}_high"].max()
        ax.set_xlim(lo - 0.02, hi + 0.04)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def value_capture(cap: pd.DataFrame, path: Path) -> None:
    _style()
    d = cap.iloc[::-1]
    fig, ax = plt.subplots(figsize=(8.5, 4.6))
    y = np.arange(len(d))
    ax.barh(y + 0.19, d["share_customers"], height=0.36, color=SERIES[0], label="Share of customers")
    ax.barh(y - 0.19, d["share_next_spend"], height=0.36, color=SERIES[1], label="Share of Jun-Nov 2011 spend")
    for yy, a, b in zip(y, d["share_customers"], d["share_next_spend"], strict=True):
        ax.text(a, yy + 0.19, f" {a:.0%}", va="center", fontsize=8, color=INK2)
        ax.text(b, yy - 0.19, f" {b:.0%}", va="center", fontsize=8, color=INK2)
    ax.set_yticks(y, d.index)
    _pct(ax, "x")
    ax.set_xlim(0, max(d["share_customers"].max(), d["share_next_spend"].max()) * 1.2)
    ax.set_title("RFM segments at June 2011: customers vs what they spent next")
    ax.legend(loc="lower right")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def migration(mig: pd.DataFrame, path: Path) -> None:
    _style()
    fig, ax = plt.subplots(figsize=(10, 5.6))
    cmap = matplotlib.colors.LinearSegmentedColormap.from_list("blues", ["#fcfcfb"] + BLUES)
    ax.imshow(mig.to_numpy(), cmap=cmap, vmin=0, vmax=max(0.6, mig.to_numpy().max()), aspect="auto")
    ax.grid(False)
    for i in range(mig.shape[0]):
        for j in range(mig.shape[1]):
            v = mig.iat[i, j]
            if v >= 0.005:
                ax.text(j, i, f"{v:.0%}", ha="center", va="center", fontsize=8,
                        color="white" if v > 0.35 else INK)
    ax.set_xticks(range(mig.shape[1]), [c.replace(" in 12 months", "\nin 12 months") for c in mig.columns],
                  rotation=40, ha="right", fontsize=8.5)
    ax.set_yticks(range(mig.shape[0]), mig.index, fontsize=9)
    ax.set_xlabel("Segment at June 2011")
    ax.set_ylabel("Segment at December 2010")
    ax.set_title("Where customers moved in six months (each row sums to 100%)")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def pareto(spend: pd.Series, path: Path) -> None:
    _style()
    v = np.sort(spend.to_numpy())[::-1]
    x = np.arange(1, len(v) + 1) / len(v)
    cum = np.cumsum(v) / v.sum()
    fig, ax = plt.subplots(figsize=(6.5, 4.2))
    ax.plot(x, cum, color=SERIES[0])
    ax.plot([0, 1], [0, 1], color=MUTED, lw=1, ls="--")
    for p in (0.1, 0.2):
        c = cum[int(round(p * len(v))) - 1]
        ax.plot(p, c, "o", ms=7, color=SERIES[0])
        ax.annotate(f"top {p:.0%} of customers: {c:.0%} of spend", (p, c), textcoords="offset points",
                    xytext=(10, -14), fontsize=8.5, color=INK2)
    _pct(ax)
    _pct(ax, "x")
    ax.set_xlabel("Customers, highest spend first")
    ax.set_ylabel("Share of 12-month spend")
    ax.set_title("Spend is concentrated (June 2010 to May 2011)")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
