import itertools

import numpy as np
import pandas as pd
import pytest

from segments import features, rfm
from segments.config import Settings


def _tx(rows):
    df = pd.DataFrame(rows, columns=["Invoice", "InvoiceDate", "value", "Customer ID"])
    df["StockCode"], df["Country"] = "10001", "United Kingdom"
    return df


S = Settings(snapshot_fit="2011-01-01", snapshot_test="2011-06-01")


def test_snapshot_respects_windows_and_nets_returns():
    t = pd.Timestamp
    purchases = _tx([
        ("1", t("2009-06-01"), 50.0, "A"),   # before lookback: tenure only
        ("2", t("2010-03-01"), 100.0, "A"),  # in lookback
        ("3", t("2010-12-31 23:00"), 40.0, "A"),
        ("4", t("2011-01-01 00:00"), 999.0, "A"),  # on the snapshot: outcome, not feature
        ("5", t("2010-02-01"), 30.0, "B"),
        ("6", t("2009-01-01"), 500.0, "C"),  # no purchase in lookback: not in base
    ])
    returns = _tx([("C1", t("2010-04-01"), -20.0, "A"), ("C2", t("2010-05-01"), -30.0, "B")])
    f = features.snapshot(purchases, returns, "snapshot_fit", S)
    assert set(f.index) == {"A"}              # B nets to zero and is excluded; C is outside the lookback
    a = f.loc["A"]
    assert a["frequency"] == 2
    assert a["monetary"] == pytest.approx(120.0)
    assert a["recency_days"] == 0
    assert a["tenure_days"] == (t("2011-01-01") - t("2009-06-01")).days
    assert a["next_spend"] == pytest.approx(999.0) and a["repeat"]
    assert f.attrs["excluded_non_positive"] == 1
    assert a["bg_x"] == 2 and a["bg_t_x"] <= a["bg_T"]


def test_scores_give_ties_the_same_score_and_reward_recency():
    df = pd.DataFrame({"recency_days": [1, 5, 50, 200, 300, 300], "frequency": [1, 1, 1, 1, 2, 9],
                       "monetary": [10, 20, 30, 40, 50, 60.0]})
    out = rfm.add_rfm(df)
    assert out["f_score"].iloc[:4].nunique() == 1            # four one-order customers, one score
    assert out["r_score"].iloc[0] == 5 and out["r_score"].iloc[-1] == out["r_score"].iloc[-2]
    assert out[["r_score", "f_score", "m_score"]].isin(range(1, 6)).all().all()


def test_grid_covers_every_rf_code_once():
    for r, f in itertools.product(range(1, 6), repeat=2):
        name = rfm.segment_for(f"{r}{f}")
        assert name in rfm.SEGMENT_ORDER and name in rfm.ACTIONS
    assert rfm.segment_for("55") == "Champions"
    assert rfm.segment_for("11") == "Hibernating"
    assert rfm.segment_for("15") == "Can't lose them"


def test_pareto_shares():
    p = features.pareto(pd.Series([100.0] + [0.0] * 9), shares=(0.1, 0.5))
    assert p == {"top_10pct": 1.0, "top_50pct": 1.0}
    flat = features.pareto(pd.Series(np.ones(10)), shares=(0.2,))
    assert flat["top_20pct"] == pytest.approx(0.2)


def test_snapshots_on_synthetic_data_have_outcomes(tx):
    from segments.clean import clean

    res = clean(tx)
    a = features.snapshot(res.purchases, res.returns, "snapshot_fit")
    b = features.snapshot(res.purchases, res.returns, "snapshot_test")
    assert len(a) > 50 and len(b) > 50
    assert 0 < a["repeat"].mean() < 1
    assert (a["recency_days"] <= 366).all()
