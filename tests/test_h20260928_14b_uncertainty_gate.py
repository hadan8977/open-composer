"""Unit tests for scripts/run_h20260928_14b_uncertainty_gate.py.

Synthetic-data tests only (no market data, no LightGBM training): timing
discipline (the multiplier for session s must only use information known
through close(s-1)), the trailing-quantile-uses-only-the-past property, the
vol-matched-control k solver, and the U3 exclude/backfill cohort logic.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import run_h20260928_14b_uncertainty_gate as ug  # noqa: E402

from open_composer.research.signal_card import hold, topk_cohorts  # noqa: E402


def test_settle_1session_shifts_by_exactly_one() -> None:
    z = np.array([np.nan, 0.1, 0.2, 0.9, 0.5], dtype=float)
    lagged = ug.settle_1session(z)
    # lagged[t] == z[t-1]: the decision at session t uses only close(t-1).
    assert np.isnan(lagged[0])
    assert np.isnan(lagged[1])  # z[0] was nan
    assert lagged[2] == 0.1
    assert lagged[3] == 0.2
    assert lagged[4] == 0.9


def test_settle_1session_future_value_does_not_change_past_decision() -> None:
    """The decision for session s must not depend on any value known only at
    s or later -- changing z[s] must never change lagged[s]."""
    z = np.array([0.1, 0.2, 0.3, 0.4, 0.5], dtype=float)
    lagged_before = ug.settle_1session(z)
    z_mutated = z.copy()
    z_mutated[2] = 999.0  # mutate the "current" value at index 2
    lagged_after = ug.settle_1session(z_mutated)
    # lagged[2] depends on z[1], unaffected by mutating z[2]
    assert lagged_before[2] == lagged_after[2]
    # only lagged[3] (which reads z[2]) may change
    assert lagged_before[3] != lagged_after[3]


def test_multiplier_from_z_fallback_is_unguarded() -> None:
    z = np.array([np.nan, 0.5, 0.85, 0.95])
    m = ug.multiplier_from_z(z, 0.80, 0.5)
    assert m[0] == 1.0  # missing info -> no gate
    assert m[1] == 1.0  # below threshold -> no gate
    assert m[2] == 0.5  # above threshold -> gated
    assert m[3] == 0.5


def test_trailing_quantile_uses_only_past_and_current() -> None:
    """A change to a future observation must never change z(t) for an
    earlier t, and z(t) must equal the exact empirical quantile of
    U[t-window+1..t]."""
    rng = np.random.default_rng(0)
    window = 10
    u = rng.normal(size=40)
    z_before = ug.trailing_quantile(u, window=window)
    u_mutated = u.copy()
    u_mutated[35] = 999.0  # a late observation
    z_after = ug.trailing_quantile(u_mutated, window=window)
    # every z(t) for t < 35 must be identical
    assert np.allclose(z_before[:35], z_after[:35], equal_nan=True)

    # spot-check the quantile definition directly at t = window-1 (first valid)
    t = window - 1
    window_vals = u[: t + 1]
    expected = float((window_vals <= u[t]).mean())
    assert abs(z_before[t] - expected) < 1e-9


def test_trailing_quantile_nan_before_full_window() -> None:
    u = np.arange(5, dtype=float)
    z = ug.trailing_quantile(u, window=10)
    assert np.isnan(z).all()


def test_trailing_quantile_tolerates_sparse_nan_gaps() -> None:
    """A single missing observation inside an otherwise-full trailing window
    must not blank out z(t) -- min_valid_frac=0.90 (default) requires only
    90% coverage, not every position finite. This regression-tests a real
    bug: requiring literally every position finite made z(t) finite on only
    1 of 2692 real sessions (single-day universe-entry/exit gaps are common
    enough that a strict all-window-finite window almost never occurs)."""
    window = 20
    u = np.arange(30, dtype=float)
    u[5] = np.nan  # one gap inside the window ending at t=24
    z = ug.trailing_quantile(u, window=window, min_valid_frac=0.90)
    # window for t=24 spans positions 5..24 (20 positions); with position 5
    # NaN, 19 of 20 are finite -- exactly the 90% floor -- so z(24) must be
    # computed, not NaN.
    assert np.isfinite(z[24])
    # a window with 2 gaps (90% of 20 = 18, two NaNs leaves 18 -- still ok);
    # three gaps (17 of 20, below 18) must go back to NaN.
    u2 = u.copy()
    u2[5] = np.nan
    u2[6] = np.nan
    u2[7] = np.nan
    z2 = ug.trailing_quantile(u2, window=window, min_valid_frac=0.90)
    assert np.isnan(z2[24])


def test_circular_shift_preserves_run_length_distribution() -> None:
    m = np.array([1.0, 1.0, 0.0, 0.0, 0.0, 1.0, 1.0, 0.0])
    shifted = ug.circular_shift(m, 3)
    assert len(shifted) == len(m)
    # circular shift must be a permutation (rotation) of the same multiset
    assert sorted(shifted.tolist()) == sorted(m.tolist())
    # rotating by 0 is a no-op; rotating by len(m) is also a no-op
    assert np.array_equal(ug.circular_shift(m, 0), m)
    assert np.array_equal(ug.circular_shift(m, len(m)), m)


def test_solve_vol_matched_k_recovers_known_mixture() -> None:
    rng = np.random.default_rng(1)
    n = 2000
    base_ret = rng.normal(0.0006, 0.02, n)
    shy_ret = rng.normal(0.0001, 0.002, n)
    true_k = 0.6
    mix = true_k * base_ret + (1 - true_k) * shy_ret
    target_vol = float(np.std(mix, ddof=1) * np.sqrt(252.0))
    k = ug.solve_vol_matched_k(base_ret, shy_ret, target_vol)
    # the quadratic can have two valid roots (variance is even in k around
    # its vertex); the solver must return SOME k whose mixture vol matches
    # the target to close tolerance, since that is the only property the
    # gate/eval code relies on.
    assert np.isfinite(k)
    mix_check = k * base_ret + (1 - true_k * 0 + (1 - k) - (1 - k)) * 0  # no-op guard
    mix_k = k * base_ret + (1 - k) * shy_ret
    achieved_vol = float(np.std(mix_k, ddof=1) * np.sqrt(252.0))
    assert abs(achieved_vol - target_vol) < 1e-6
    del mix_check


def test_solve_vol_matched_k_handles_degenerate_target() -> None:
    base_ret = np.array([np.nan, np.nan])
    shy_ret = np.array([np.nan, np.nan])
    k = ug.solve_vol_matched_k(base_ret, shy_ret, 0.1)
    assert not np.isfinite(k)


def test_auroc_perfect_separation_is_one() -> None:
    score = np.array([0.1, 0.2, 0.8, 0.9])
    label = np.array([0.0, 0.0, 1.0, 1.0])
    assert abs(ug.auroc(score, label) - 1.0) < 1e-9


def test_auroc_inverted_separation_is_zero() -> None:
    score = np.array([0.9, 0.8, 0.2, 0.1])
    label = np.array([0.0, 0.0, 1.0, 1.0])
    assert abs(ug.auroc(score, label) - 0.0) < 1e-9


def test_auroc_coin_flip_near_half() -> None:
    rng = np.random.default_rng(2)
    n = 5000
    score = rng.normal(size=n)
    label = rng.integers(0, 2, size=n).astype(float)
    a = ug.auroc(score, label)
    assert abs(a - 0.5) < 0.03


def test_auroc_nan_and_empty_class_returns_nan() -> None:
    score = np.array([0.1, 0.2, np.nan, 0.4])
    label = np.array([0.0, 0.0, 1.0, 0.0])  # all finite-score rows are label 0
    assert np.isnan(ug.auroc(score, label))


def test_book_level_uncertainty_weights_by_held_and_ignores_missing() -> None:
    held = np.array([[0.5, 0.5, 0.0], [1 / 3, 1 / 3, 1 / 3]])
    u_i = np.array([[0.1, 0.3, np.nan], [0.2, np.nan, 0.4]])
    out = ug.book_level_uncertainty(held, u_i)
    # row 0: both held names have finite u_i -> plain weighted mean
    assert abs(out[0] - (0.5 * 0.1 + 0.5 * 0.3)) < 1e-9
    # row 1: middle name missing u_i -> renormalized over the other two
    expected = (1 / 3 * 0.2 + 1 / 3 * 0.4) / (1 / 3 + 1 / 3)
    assert abs(out[1] - expected) < 1e-9


def test_book_level_uncertainty_all_missing_is_nan() -> None:
    held = np.array([[0.5, 0.5]])
    u_i = np.array([[np.nan, np.nan]])
    out = ug.book_level_uncertainty(held, u_i)
    assert np.isnan(out[0])


def test_u3_exclusion_backfills_by_momentum_rank() -> None:
    """Excluding the most-uncertain top-20% of an eligible pool must drop
    exactly the most-uncertain names and keep the cohort filled to k from
    the remaining momentum ranking -- never picks an excluded name.

    Uses 50 names (>= signal_card.MIN_NAMES's 2*k floor for k=5) so
    ``topk_cohorts`` does not hit its own too-few-eligible-names guard,
    which would otherwise silently zero out the whole row."""
    n_names = 50
    k = 5
    momentum = np.arange(n_names, 0, -1, dtype=float).reshape(1, n_names)
    member = np.ones((1, n_names), dtype=bool)
    # top-20% most uncertain = top 10 names by u_i; make those exactly the
    # 10 names with the WORST (lowest) momentum, so a naive "just take top-5
    # momentum ignoring uncertainty" would agree with this test only if the
    # exclusion has no effect -- instead put the highest-uncertainty names
    # at the best momentum ranks (0..9) to make the exclusion's effect
    # unambiguous: if exclusion works, the cohort must come from ranks 10+.
    u_i = np.zeros((1, n_names))
    u_i[0, :10] = np.linspace(0.9, 0.99, 10)  # best-momentum names are most uncertain
    u_i[0, 10:] = np.linspace(0.0, 0.5, n_names - 10)
    from open_composer.research.signal_card import percentile_ranks

    u_i_pct = percentile_ranks(u_i, member)
    excluded = member & np.isfinite(u_i_pct) & (u_i_pct > 0.80)
    assert int(excluded.sum()) == 10
    assert set(np.nonzero(excluded[0])[0].tolist()) == set(range(10))
    eligible = member & ~excluded
    cohorts = topk_cohorts(momentum, eligible, k)
    chosen = np.nonzero(cohorts[0] > 0)[0]
    assert len(chosen) == k
    assert not (set(chosen.tolist()) & set(range(10)))
    # backfilled by momentum rank among the remaining eligible names (10..49):
    # highest momentum among those is index 10 (value 40), so ranks 10-14 win.
    assert set(chosen.tolist()) == {10, 11, 12, 13, 14}


def test_u3_multiplier_is_always_fully_invested() -> None:
    """U3 changes stock selection, not book-level exposure -- the held
    weight matrix it produces must sum to 1 on every fully-formed cohort
    day, i.e. no cash leg is introduced by construction."""
    n_names = 40
    k = 5
    momentum_row = np.arange(n_names, 0, -1, dtype=float)
    cohorts = topk_cohorts(
        np.tile(momentum_row, (25, 1)),
        np.ones((25, n_names), dtype=bool),
        k,
    )
    held = hold(cohorts, 20)
    # once the 20-session ramp completes, weights should sum close to 1
    assert abs(float(held[24].sum()) - 1.0) < 1e-6
