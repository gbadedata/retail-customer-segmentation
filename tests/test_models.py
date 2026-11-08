from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from segments import bgnbd, cluster, validate
from segments.config import Settings

FIXTURE = Path(__file__).parent / "fixtures" / "cdnow_customers_summary.csv"


def test_bgnbd_reproduces_published_cdnow_estimates():
    d = pd.read_csv(FIXTURE)
    m = bgnbd.fit(d["frequency"], d["recency"], d["T"])
    # Fader, Hardie and Lee (2005), Table 1.
    assert m.r == pytest.approx(0.243, abs=0.002)
    assert m.alpha == pytest.approx(4.414, abs=0.01)
    assert m.a == pytest.approx(0.793, abs=0.005)
    assert m.b == pytest.approx(2.426, abs=0.01)
    assert m.log_likelihood == pytest.approx(-9582.4, abs=0.5)
    # Worked example in the paper: x=2, t_x=30.43, T=38.86, next 39 weeks -> 1.226
    assert m.expected_purchases(39, [2], [30.43], [38.86])[0] == pytest.approx(1.226, abs=0.002)


def test_bgnbd_behaviour():
    m = bgnbd.BGNBD(r=0.243, alpha=4.414, a=0.793, b=2.426, log_likelihood=0)
    alive = m.p_alive([0, 5, 5], [0, 30, 5], [38, 38, 38])
    assert alive[0] == 1.0 and 0 < alive[2] < alive[1] < 1   # a recent buyer is more likely alive
    e = m.expected_purchases(10, [5, 5], [37, 5], [38, 38])
    assert e[0] > e[1]
    with pytest.raises(ValueError):
        bgnbd.fit([1], [10], [5])


def test_select_k_finds_clear_structure():
    rng = np.random.default_rng(0)
    centres = [(5, 1, 100), (30, 5, 1000), (200, 20, 10000)]
    rows = []
    for r, f, m in centres:
        for _ in range(150):
            rows.append((r * rng.lognormal(0, 0.15), f * rng.lognormal(0, 0.15), m * rng.lognormal(0, 0.15)))
    df = pd.DataFrame(rows, columns=cluster.FEATURES)
    s = Settings(k_max=6, stability_reps=8)
    table, k = cluster.select_k(cluster.matrix(df), s)
    assert k == 3
    assert table.loc[table["k"] == 3, "ari_mean"].iloc[0] > 0.95
    model = cluster.fit(df, k, s)
    labels = model.predict(df)
    spend = df.groupby(labels)["monetary"].mean()
    assert list(spend.index) == [1, 2, 3] and spend.is_monotonic_decreasing   # 1 = highest spend
    assert len(set(model.names.values())) == 3


def test_validation_metrics_and_migration():
    fit_df = pd.DataFrame({"seg": ["hi"] * 50 + ["lo"] * 50, "repeat": [True] * 45 + [False] * 5 + [True] * 5 +
                           [False] * 45, "next_spend": [100.0] * 50 + [1.0] * 50})
    test_df = fit_df.copy()
    m, cal = validate.evaluate(fit_df, test_df, "seg")
    assert m["repeat_auc"] == pytest.approx(0.9)
    assert set(cal.index) == {"hi", "lo"}
    mig = validate.migration(fit_df.iloc[:60], test_df.iloc[:50], "seg", ["hi", "lo"])
    assert np.allclose(mig.sum(axis=1), 1)
    assert mig.loc["lo", "No purchase in 12 months"] == 1.0
