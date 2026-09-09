"""Tests for open_composer.research.regime.validated_grid_strategy.

Step 13 Track M. Several of these tests exist specifically to prevent a
repeat of the 2026-09-09 A-group leak (see the module's own docstring):
fitting a grid cell on rows it is then "validated" against.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from open_composer.research.kernel.lightgbm_rank_strategy import LightGBMRankStrategy
from open_composer.research.regime import validated_grid_strategy as vgs

DEFAULT_N_SYMBOLS = 50


def _synthetic_train_frame(
    n_days: int = 300, seed: int = 11, n_symbols: int = DEFAULT_N_SYMBOLS
) -> pd.DataFrame:
    """A cross-sectional panel spanning ``n_days`` business days with a
    genuine, learnable relationship: ``label_rank_5``/``label_rank_10`` are
    the same-date cross-sectional percentile rank of ``feature1`` (mirroring
    how ``labels.py`` actually builds ``label_rank_h`` from a real forward
    return) for ``label_rank_5``, and pure noise (uncorrelated with
    ``feature1``) for ``label_rank_10`` -- a deliberately *uninformative*
    second column so multi-cell selection tests have a real loser to reject.

    ``n_symbols`` is a parameter (not a module constant) because the
    label-shuffle placebo test below needs many more names per
    cross-section than the structural/selection tests do, to keep its
    statistical margin comfortable -- see that test's own docstring.
    """
    dates = pd.bdate_range("2023-01-02", periods=n_days)
    rng = np.random.default_rng(seed)
    rows = []
    for date in dates:
        feature_values = rng.normal(size=n_symbols)
        noise_labels = rng.uniform(size=n_symbols)
        for i in range(n_symbols):
            rows.append(
                {
                    "trade_date": date,
                    "symbol": f"S{i:03d}",
                    "feature1": float(feature_values[i]),
                    "_noise_label": float(noise_labels[i]),
                }
            )
    frame = pd.DataFrame(rows)
    frame["label_rank_5"] = frame.groupby("trade_date")["feature1"].rank(pct=True)
    frame["label_rank_10"] = frame.groupby("trade_date")["_noise_label"].rank(pct=True)
    return frame.drop(columns=["_noise_label"])


def test_split_fit_and_validation_rows_are_disjoint_with_an_embargo_gap() -> None:
    frame = _synthetic_train_frame()
    fit_rows, validation_rows, validation_start = vgs.split_fit_and_validation_rows(
        frame, label_horizon_days=5
    )
    assert fit_rows["trade_date"].max() < validation_rows["trade_date"].min()
    fit_dates = set(fit_rows["trade_date"].unique())
    validation_dates = set(validation_rows["trade_date"].unique())
    assert fit_dates.isdisjoint(validation_dates)

    # validation_start is the calendar quarter containing the window's last
    # date, and every validation row is on/after it.
    window_end = frame["trade_date"].max()
    assert validation_start == pd.Timestamp(window_end).to_period("Q").start_time
    assert (validation_rows["trade_date"] >= validation_start).all()

    # The embargo gap itself: at least 5 trading days separate the fit
    # window's last date from validation_start (not just from validation's
    # first *row*, which could coincide with validation_start exactly).
    local_calendar = pd.DatetimeIndex(sorted(frame["trade_date"].unique()))
    fit_end_pos = local_calendar.searchsorted(fit_rows["trade_date"].max(), side="left")
    val_start_pos = local_calendar.searchsorted(validation_start, side="left")
    assert val_start_pos - fit_end_pos >= 6  # >= 5 embargo days + the fit_end day itself


def test_split_fit_and_validation_rows_raises_when_history_is_too_short() -> None:
    frame = _synthetic_train_frame(n_days=5)  # far less than a 5-day embargo can clear
    with pytest.raises(ValueError, match="not enough trading history"):
        vgs.split_fit_and_validation_rows(frame, label_horizon_days=5)


def test_rank_ic_by_date_recovers_a_perfect_relationship() -> None:
    frame = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(["2024-01-02"] * 6),
            # Evenly spaced -- an exact affine transform of rank 1..6, so a
            # perfectly rank-monotonic score correlates at exactly 1.0
            # (rank_ic_by_date correlates *raw* label values against score
            # rank, which only equals Spearman when the label is itself an
            # affine function of rank, as label_rank_h's percentile rank
            # construction ensures in production).
            "label_rank_5": [0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
        }
    )
    scores = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])  # perfectly monotonic with the label
    ic = vgs.rank_ic_by_date(scores, frame, "label_rank_5")
    assert ic.loc[pd.Timestamp("2024-01-02")] == pytest.approx(1.0)


def test_rank_ic_by_date_drops_thin_cross_sections() -> None:
    frame = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(["2024-01-02"] * 3 + ["2024-01-03"] * 6),
            "label_rank_5": [0.1, 0.5, 0.9] + [0.1, 0.3, 0.5, 0.7, 0.9, 1.0],
        }
    )
    scores = pd.Series([1.0, 2.0, 3.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    ic = vgs.rank_ic_by_date(scores, frame, "label_rank_5", min_names=5)
    # 2024-01-02 has only 3 names (< min_names=5) and must be dropped, not
    # scored as some default value.
    assert list(ic.index) == [pd.Timestamp("2024-01-03")]


def test_ml_grid_cell_config_id_encodes_horizon_depth_and_halflife() -> None:
    assert vgs.MLGridCell(label_horizon_days=5).config_id == "h5_d3"
    assert vgs.MLGridCell(label_horizon_days=10, max_depth=6).config_id == "h10_d6"
    assert (
        vgs.MLGridCell(label_horizon_days=5, recency_halflife_days=126.0).config_id == "h5_d3_hl126"
    )


def test_validation_selected_strategy_rejects_an_empty_grid() -> None:
    with pytest.raises(ValueError, match="non-empty grid"):
        vgs.ValidationSelectedLightGBMStrategy(["feature1"], grid=[])


def test_validation_selected_strategy_single_cell_fits_and_scores() -> None:
    frame = _synthetic_train_frame()
    strategy = vgs.ValidationSelectedLightGBMStrategy(
        ["feature1"], grid=[vgs.MLGridCell(label_horizon_days=5)]
    )
    strategy.fit(frame)
    assert strategy.selected_cell == vgs.MLGridCell(label_horizon_days=5)
    assert "h5_d3" in strategy.validation_ic_by_cell
    ic = strategy.validation_ic_by_cell["h5_d3"]
    assert ic == ic  # not NaN: the real feature1->label_rank_5 relationship is learnable

    asof = frame.loc[frame["trade_date"] == frame["trade_date"].max()]
    scores = strategy.score(asof)
    assert set(scores.index) == set(asof["symbol"])


def test_validation_selected_strategy_selects_the_cell_with_real_out_of_sample_signal() -> None:
    # label_rank_5 is genuinely predictable from feature1; label_rank_10 is
    # pure noise (see _synthetic_train_frame). Selection must prefer h=5
    # using only out-of-sample validation evidence -- not by peeking at
    # which one "is" the real relationship.
    frame = _synthetic_train_frame()
    strategy = vgs.ValidationSelectedLightGBMStrategy(
        ["feature1"],
        grid=[
            vgs.MLGridCell(label_horizon_days=5),
            vgs.MLGridCell(label_horizon_days=10),
        ],
    )
    strategy.fit(frame)
    assert strategy.selected_cell == vgs.MLGridCell(label_horizon_days=5)
    assert strategy.validation_ic_by_cell["h5_d3"] > strategy.validation_ic_by_cell["h10_d3"]


def test_validation_selected_strategy_never_fits_a_selection_candidate_on_validation_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frame = _synthetic_train_frame()
    _, validation_rows, _ = vgs.split_fit_and_validation_rows(frame, label_horizon_days=5)
    validation_dates = set(validation_rows["trade_date"].unique())

    seen_fit_date_sets: list[set] = []
    original_fit = LightGBMRankStrategy.fit

    def _recording_fit(self, train_frame, sample_weight=None):  # noqa: ANN001
        seen_fit_date_sets.append(set(train_frame["trade_date"].unique()))
        return original_fit(self, train_frame, sample_weight=sample_weight)

    monkeypatch.setattr(LightGBMRankStrategy, "fit", _recording_fit)

    strategy = vgs.ValidationSelectedLightGBMStrategy(
        ["feature1"], grid=[vgs.MLGridCell(label_horizon_days=5)]
    )
    strategy.fit(frame)

    # Exactly one fit call (the final "serve the winner" refit) is allowed
    # to touch validation dates; every other fit call (the selection-phase
    # fit(s)) must be completely disjoint from validation_dates.
    overlap_counts = [len(dates & validation_dates) for dates in seen_fit_date_sets]
    assert overlap_counts.count(0) == len(overlap_counts) - 1
    assert len(seen_fit_date_sets) == 2  # one selection fit + one final refit, for a 1-cell grid


def test_validation_selected_strategy_raises_when_no_cell_is_usable() -> None:
    frame = _synthetic_train_frame(n_days=5)  # too short to embargo any cell
    strategy = vgs.ValidationSelectedLightGBMStrategy(
        ["feature1"], grid=[vgs.MLGridCell(label_horizon_days=5)]
    )
    with pytest.raises(ValueError, match="no grid cell produced a usable"):
        strategy.fit(frame)


def test_label_shuffled_fit_gives_near_zero_out_of_sample_validation_ic() -> None:
    """The exact property the coordinator asked this module to prove
    (2026-09-09 14:10 UTC message, in direct response to the A-group
    placebo's real finding): shuffling the label destroys any true
    feature/label relationship everywhere (fit window *and* validation
    window, mirroring run_b3_grid.py's own --placebo-only mechanism, which
    is a global label shuffle, not a validation-only one). If a grid cell's
    selection-phase fit genuinely never sees validation rows, it has no way
    to predict validation's now-random labels above chance, so the reported
    out-of-sample validation rank IC must stay small. The real, now-fixed
    A-group bug (this module's docstring; commit bb21f27) showed this same
    placebo at IC=0.21 before the fix and IC=0.0013 after -- this test is
    this module's own version of that same tripwire.

    Sizing note: a *correct* implementation's validation IC is not exactly
    zero on any single shuffle draw, it is a noisy statistic centered near
    zero, with standard error shrinking as sqrt(n_names) * sqrt(n_val_dates)
    grows. At the default fixture's 50 names the 0.02 gate is under 1.1
    sampling standard deviations away -- too close to be a stable tripwire
    (it was observed to fail on an entirely correct implementation during
    this test's own development). 150 names x ~55 validation dates pushes
    the gate out to a comfortable margin (empirically verified stable
    across 6 independent (data seed, shuffle seed) draws, |IC| <= 0.012
    every time, before fixing the two seeds below) without the O(n) fit
    cost of also scaling n_days.
    """
    frame = _synthetic_train_frame(n_days=380, seed=23, n_symbols=150)
    rng = np.random.default_rng(99)
    shuffled = frame.copy()
    shuffled["label_rank_5"] = rng.permutation(shuffled["label_rank_5"].to_numpy())

    strategy = vgs.ValidationSelectedLightGBMStrategy(
        ["feature1"], grid=[vgs.MLGridCell(label_horizon_days=5)]
    )
    strategy.fit(shuffled)
    ic = strategy.validation_ic_by_cell["h5_d3"]
    assert ic == ic, "validation IC was NaN -- the cell produced no usable score at all"
    assert abs(ic) < 0.02, (
        f"label-shuffled validation IC={ic!r} looks leaked (expected |IC| < 0.02)"
    )
