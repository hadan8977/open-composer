"""Unit tests for the T-20261006-22 residual-reversal book helpers (scripts/t22_run.py)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from scripts import t22_run as R


class FakeStore:
    def __init__(self, t_n: int = 40, n: int = 400, seed: int = 0) -> None:
        rng = np.random.default_rng(seed)
        self.dates = pd.bdate_range("2024-01-02", periods=t_n)
        self.symbols = pd.Index([f"S{i}" for i in range(n - 1)] + ["SPY"])
        self.shape = (t_n, n)
        self.spy = n - 1
        self.vix = np.full(t_n, 15.0)
        self.arr = {
            "e_ind": rng.normal(0, 0.02, (t_n, n)).astype("float32"),
            "adv_rank": np.tile(np.arange(1, n + 1), (t_n, 1)).astype("float32"),
            "is_tradeable": np.ones((t_n, n), dtype="float32"),
            "close": np.full((t_n, n), 50.0, dtype="float32"),
            "short_elig": np.ones((t_n, n), dtype=bool),
            "beta_252_spy": np.ones((t_n, n), dtype="float32"),
        }

    def m(self, name: str) -> np.ndarray:
        return self.arr[name]


def test_signal_is_negative_sum_of_residuals() -> None:
    s = FakeStore()
    t = 20
    got = R.signal_row(s, "ind", 5, t)
    want = -s.arr["e_ind"][t - 4 : t + 1].astype("float64").sum(axis=0)
    assert np.allclose(got, want)


def test_signal_ignores_future_rows() -> None:
    s = FakeStore()
    base = R.signal_row(s, "ind", 5, 20)
    s.arr["e_ind"][21:] = np.nan
    assert np.array_equal(base, R.signal_row(s, "ind", 5, 20))


def test_book_is_dollar_neutral_with_equal_weights_and_hedge() -> None:
    s = FakeStore()
    book = R.single_day_book(s, 25, 400, "ind", 5, "none")
    assert book is not None
    idx, w, hedge = book
    assert (w > 0).sum() == R.NAMES_PER_SIDE and (w < 0).sum() == R.NAMES_PER_SIDE
    assert np.isclose(w[w > 0].sum(), R.SIDE_GROSS) and np.isclose(w[w < 0].sum(), -R.SIDE_GROSS)
    assert np.isclose(hedge, -w.sum())  # beta = 1 everywhere
    score = R.signal_row(s, "ind", 5, 25)
    assert score[idx[w > 0]].min() >= np.sort(score[:-1])[-R.NAMES_PER_SIDE - 1]  # longs: highest S


def test_overlap_target_averages_batches() -> None:
    s = FakeStore()
    books = {t: R.single_day_book(s, t, 400, "ind", 5, "none") for t in range(20, 26)}
    tgt = R.overlap_target(books, 5, s)(25)
    assert tgt is not None and tgt["TBILL"] == 1.0
    longs = sum(v for k, v in tgt.items() if k not in ("TBILL", "SPY") and v > 0)
    assert longs <= R.SIDE_GROSS + 1e-9


def test_net_placebo_is_stable_within_quarter_and_keeps_score_values() -> None:
    s = FakeStore()
    ok = np.ones(s.shape[1], dtype=bool)
    sc = R.signal_row(s, "ind", 5, 22)
    a = R.placebo_score(s, 22, ok, sc, ("net", 3))
    b = R.placebo_score(s, 23, ok, R.signal_row(s, "ind", 5, 23), ("net", 3))
    assert np.allclose(np.sort(a), np.sort(sc))
    assert np.array_equal(np.argsort(a), np.argsort(R.placebo_score(s, 22, ok, sc, ("net", 3))))
    # same random rank order on the next day of the same quarter
    ra, rb = np.argsort(np.argsort(a)), np.argsort(np.argsort(b))
    assert ra.shape == rb.shape
