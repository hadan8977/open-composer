"""Tests for T-20260929-11 (multi-quarter SUE elastic net): point-in-time
feature visibility, training-set cutoff, seeded label-shuffle placebo, and the
batch module's deterministic tie rule."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import build_h20260929_11_multiq_sue_scores as sc  # noqa: E402


def _events() -> pd.DataFrame:
    # symbol A reports on 2020-02-10, 2020-05-11 and (future) 2020-08-10.
    return pd.DataFrame(
        {
            "symbol": ["A", "A", "A", "B"],
            "trade_date": pd.to_datetime(["2020-02-10", "2020-05-11", "2020-08-10", "2020-03-02"]),
            "sue_eps": [1.0, -2.0, 99.0, 0.5],
            "sue_rev": [0.1, 0.2, 0.3, np.nan],
        }
    )


def test_future_filing_not_in_earlier_features() -> None:
    store = sc.EventStore(_events(), ["A", "B"])
    dates = pd.DatetimeIndex(["2020-02-09", "2020-05-11", "2020-08-09", "2020-08-10"])
    counts = store.counts(dates)
    assert counts[:, 0].tolist() == [0, 2, 2, 3]  # event visible on its own session, not before
    k = counts[[2], 0]  # 2020-08-09: the 99.0 event is not yet visible
    feats = store.features(k, np.array([0]))
    assert feats[0, 0] == -2.0 and feats[0, 1] == 1.0  # lag1, lag2
    assert 99.0 not in feats[0]
    assert np.isnan(feats[0, 2])  # lag3 does not exist yet
    assert feats[0, 8 + 0] == 0.2  # sue_rev lag1
    assert feats[0, 16] == 0.0 and feats[0, 17] == 1.0  # streaks: last SUE negative
    assert feats[0, 18] == 6.0  # six missing eps lags out of 8
    last = store.last_visible(k, np.array([0]))
    assert last[0] == np.datetime64("2020-05-11")


def test_streaks_break_on_missing_and_sign() -> None:
    vals = np.array([1.0, 2.0, np.nan, 3.0, -1.0, -2.0])
    assert sc._streaks(vals, True).tolist() == [1, 2, 0, 1, 0, 0]
    assert sc._streaks(vals, False).tolist() == [0, 0, 0, 0, 1, 2]


def test_rank_standardize_fills_missing_with_zero_before_ranking() -> None:
    raw = np.array([[-1.0], [np.nan], [2.0]])
    out = sc.rank_standardize(raw)[:, 0]
    assert out.tolist() == pytest.approx([1 / 3 - 0.5, 2 / 3 - 0.5, 1.0 - 0.5])


def test_training_set_excludes_samples_whose_label_reaches_test_year() -> None:
    end_pos = np.array([100, 200, 260, 261, 400])
    usable = [True, True, True, True, False]
    assert sc.training_months_for_year(end_pos, usable, first_pos=261) == [0, 1, 2]
    assert sc.training_months_for_year(end_pos, usable, first_pos=100) == []


def test_label_end_is_22_sessions_after_signal_close() -> None:
    idx = pd.bdate_range("2020-01-01", periods=60)
    open_ = pd.DataFrame({"X": np.arange(1.0, 61.0)}, index=idx)
    lab, end_pos = sc.labels_month_end(open_, np.array([5]))
    assert end_pos[0] == 27
    assert lab[0, 0] == pytest.approx(open_["X"].iloc[27] / open_["X"].iloc[6] - 1.0)


def test_shuffle_placebo_is_seeded_and_keeps_month_multiset() -> None:
    rng = np.random.default_rng(0)
    y = rng.random(300)
    month = np.repeat(np.arange(3), 100)
    a = sc.shuffle_labels(y, month, 2021)
    b = sc.shuffle_labels(y, month, 2021)
    c = sc.shuffle_labels(y, month, 2022)
    assert np.array_equal(a, b)
    assert not np.array_equal(a, c)
    assert not np.array_equal(a, y)
    for m in range(3):
        assert sorted(a[month == m]) == sorted(y[month == m])


def test_cv_splits_leave_a_one_month_gap() -> None:
    month = np.repeat(np.arange(30), 5)
    for tr, va in sc.cv_splits(month):
        assert month[tr].max() + 1 < month[va].min()


def test_elastic_net_fit_recovers_signal_and_zero_on_noise() -> None:
    rng = np.random.default_rng(1)
    n_months, per = 40, 60
    month = np.repeat(np.arange(n_months), per)
    X = rng.random((n_months * per, 4)) - 0.5
    y = 0.6 * X[:, 0] + 0.05 * rng.standard_normal(len(X))
    fit = sc.fit_enet(X, y, month)
    assert fit["model"].coef_[0] > 0.2
    noise = sc.fit_enet(X, rng.standard_normal(len(X)), month)
    assert np.count_nonzero(noise["model"].coef_) <= 1


@pytest.mark.skipif(
    not (sc.OUT_DIR / "scores.parquet").exists(), reason="scores.parquet not built yet"
)
def test_batch_tie_break_is_deterministic_and_uninformative() -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "batch_mod", ROOT / "scripts/screen_batches/h20260929_11_multiq_sue.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    asof = pd.Timestamp("2021-03-31")
    const = np.zeros(200)
    r1 = mod._rank_desc(const, asof)
    r2 = mod._rank_desc(const, asof)
    assert np.array_equal(r1, r2)
    assert sorted(r1) == list(range(1, 201))
    assert not np.array_equal(r1, np.arange(1, 201))  # not alphabetical
    vals = np.array([0.1, 0.9, 0.5])
    assert mod._rank_desc(vals, asof).tolist() == [3, 1, 2]
    assert [c.id for c in mod.CANDIDATES] == [
        "ENET_TOP50",
        "ENET_TOP20",
        "ENET_MOM_TOP50",
        "SUE1_TOP50",
        "MOM12_1_TOP50",
        "EW_POOL",
        "RAND_TOP50",
        "ENET_SHUF_TOP50",
    ]
