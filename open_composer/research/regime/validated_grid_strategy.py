"""Step 13 Track M: a leakage-safe, out-of-sample validation-selected grid
strategy for LightGBM ranking cells.

docs/plan-step-13-recent-high-return-ml-and-llm-tracks-2026-09-09.zh.md
section 3.4 ("泄漏纪律") and the 2026-09-09 14:10 UTC coordinator message
this module was written in direct response to.

**The bug this exists to avoid, precisely.** The A-group placebo (label-
shuffled data, real Step 11 grid) initially came back with the selected
cell's validation rank IC at 0.21 -- a real-looking number produced from
data with the true label destroyed. Root cause, read directly from
``open_composer.research.kernel.b3_grid_strategy.GridSelectedLightGBMStrategy
.fit`` (its own docstring said so explicitly, as a deliberate reading of the
plan's wording): every grid cell was fit on the *entire* training window,
**including** the year it was then scored against for cell selection. The
model had already seen those exact rows (and, for a tree model, can come
close to memorizing their exact labels) during fit, so "validation" IC on
them is not out-of-sample at all -- it stayed inflated even with shuffled
labels. A-group's own fix (commit ``bb21f27``) now holds out its validation
*year* plus an embargo before refitting the same way this module holds out a
validation *quarter*; the two are independent, correctly-scoped fixes for
two different refit cadences (Step 11's B3 refits yearly, Track M's M1/M2
refit quarterly -- see ``loop.ExperimentConfig.refit_frequency``), not one
importing the other.

**The split, per call to** :meth:`ValidationSelectedLightGBMStrategy.fit`.
``train_frame`` arrives already anchored and outer-embargoed against the
real test quarter by ``loop.build_weight_schedule`` (or, when
``train_window_months`` is set, already truncated to a trailing window) --
exactly like every other ``loop.RankingStrategy`` this kernel has. This
class further splits *that* window::

    |---------------- fit window -----------------|-embargo-|--val window--|
    train_frame.trade_date.min()                              train_frame.trade_date.max()
                                                                  (== the walk-forward
                                                                   fold's own embargoed
                                                                   train_cutoff)

* **Validation window** = the calendar quarter containing
  ``train_frame["trade_date"].max()`` (the coordinator's "the validation
  quarter is the last quarter of the 24-month training window").
* **Embargo** = each cell's own ``label_horizon_days`` trading days,
  counted on ``train_frame``'s own date sequence (not the full market
  calendar -- this window may already be a memory-lean, rebalance-dates-only
  subset; embargoing on whatever dates are actually present is the correct,
  conservative choice either way).
* **Fit window** = every training row at or before the embargoed cutoff.
  Cells with a longer ``label_horizon_days`` lose more of the fit window to
  embargo than shorter-horizon cells -- an intentional, disclosed asymmetry,
  not a bug: a genuinely slower label needs a wider embargo to stay clean.
* Each cell's own model is fit **only** on the fit window, then scored on
  the validation window's rows -- rows that fit call never saw. The rank IC
  from that scoring is what selects the winning cell.
* Once a winner is chosen, this class refits that one cell's hyperparameters
  on the **full** ``train_frame`` (fit window + validation window) to serve
  the upcoming test quarter. This is not a leak: the validation quarter is
  still strictly before the real test quarter (which the *outer*
  embargo -- ``loop.embargo_cutoff`` -- already isolates), so folding it
  back in after selection is the standard "refit on train+val once the
  model/hyperparameter choice is made" step, and selection itself above
  never used it.

Every cell's validation IC is retained (``validation_ic_by_cell``) for the
ledger/report, matching the gate contract's "every cell's test-quarter
result is still written to the ledger for DSR counting" -- this module
writes the *selection* evidence; the caller (``scripts/run_step13_m_grid.py``)
is responsible for actually recording each cell's realized test-quarter
return too, if the grid design calls for that.
"""

from __future__ import annotations

import gc
from collections.abc import Sequence
from dataclasses import dataclass

import pandas as pd

from open_composer.research.kernel.lightgbm_rank_strategy import LightGBMRankStrategy
from open_composer.research.kernel.loop import (
    embargo_cutoff,
    fit_with_optional_sample_weight,
    recency_sample_weight,
)

DEFAULT_MAX_DEPTH = 3
#: Minimum names in a cross-section for that date's rank IC to be counted at
#: all -- matches b3_grid_strategy.py's own choice (a 2-3 name cross-section
#: correlation is not a meaningful rank statistic).
MIN_CROSS_SECTION_NAMES = 5


@dataclass(frozen=True)
class MLGridCell:
    """One grid point this module can select among: a label horizon, an
    optional recency sample-weight half-life, and a tree depth (plan section
    3.2 fixes ``max_depth=3`` for every M1 cell -- not searched -- but this
    stays a field, not a module constant, so a caller that *does* want to
    compare depths, e.g. an M2-style linear-vs-tree check, is not blocked).
    """

    label_horizon_days: int
    recency_halflife_days: float | None = None
    max_depth: int = DEFAULT_MAX_DEPTH

    @property
    def label_column(self) -> str:
        return f"label_rank_{self.label_horizon_days}"

    @property
    def config_id(self) -> str:
        halflife_part = (
            f"_hl{int(self.recency_halflife_days)}"
            if self.recency_halflife_days is not None
            else ""
        )
        return f"h{self.label_horizon_days}_d{self.max_depth}{halflife_part}"


def rank_ic_by_date(
    scores: pd.Series,
    frame: pd.DataFrame,
    label_column: str,
    *,
    min_names: int = MIN_CROSS_SECTION_NAMES,
) -> pd.Series:
    """Per-date cross-sectional rank IC: Pearson correlation of the
    predicted scores' rank against ``label_column`` (already a percentile
    rank of the true forward return, so this equals Spearman-correlating
    against the raw forward return -- percentile rank is a monotonic,
    ~affine transform of integer rank). ``scores`` must be positionally
    aligned with ``frame`` (same row order), matching how
    ``LightGBMRankStrategy.score`` returns its result. Dates with fewer than
    ``min_names`` names are dropped, not counted as IC==0 -- a 2-3-name
    cross-sectional correlation is not a meaningful statistic either way.

    Reimplemented here (rather than imported) from the same formula
    ``open_composer.research.kernel.b3_grid_strategy._rank_ic_by_date`` uses --
    that module is A-group-owned and that function is private to it; the
    bug this file exists to avoid was in *what data got fit*, never in this
    formula, so reusing the formula (not the file) is correct.
    """
    aligned = frame[["trade_date", label_column]].copy()
    aligned["score"] = scores.to_numpy()
    ic_per_date = aligned.groupby("trade_date").apply(
        lambda g: g["score"].rank().corr(g[label_column]) if len(g) >= min_names else float("nan"),
        include_groups=False,
    )
    return ic_per_date.dropna()


def split_fit_and_validation_rows(
    train_frame: pd.DataFrame, *, label_horizon_days: int
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Timestamp]:
    """The out-of-sample fit/validation split one grid cell uses (see module
    docstring). Returns ``(fit_rows, validation_rows, validation_quarter_start)``.
    ``fit_rows``/``validation_rows`` are disjoint by construction (an
    embargo gap of ``label_horizon_days`` trading days sits between them,
    counted on ``train_frame``'s own present dates) and neither is a copy of
    rows the other one also contains.

    Raises ``ValueError`` if the embargo would consume the entire fit
    window (not enough history before the validation quarter to embargo
    ``label_horizon_days`` trading days) or if the validation quarter has no
    rows at all in ``train_frame`` -- both signal a grid cell that is not
    usable for this training window, which callers should treat as a
    missing (NaN) validation IC, not a crash.
    """
    window_end = pd.Timestamp(train_frame["trade_date"].max())
    validation_start = window_end.to_period("Q").start_time
    local_calendar = pd.DatetimeIndex(sorted(train_frame["trade_date"].unique()))

    validation_mask = train_frame["trade_date"] >= validation_start
    validation_rows = train_frame.loc[validation_mask]
    if validation_rows.empty:
        raise ValueError(
            f"no rows on/after {validation_start.date()} (this window's last calendar "
            "quarter) to validate against"
        )

    # Same "how far back can a training window reach while staying
    # embargo_days trading days clear of a boundary" arithmetic the outer
    # walk-forward fit/test split uses (loop.embargo_cutoff) -- here applied
    # to the inner fit/validation boundary instead of the fit/test one.
    # Raises ValueError (propagated to the caller) exactly when there is not
    # enough history before validation_start to embargo label_horizon_days
    # trading days and still leave a non-empty fit window.
    fit_end = embargo_cutoff(local_calendar, validation_start, label_horizon_days)
    fit_rows = train_frame.loc[train_frame["trade_date"] <= fit_end]
    return fit_rows, validation_rows, validation_start


class ValidationSelectedLightGBMStrategy:
    """M1/M2: for every ``fit()`` call (once per walk-forward refit -- see
    ``loop.ExperimentConfig.refit_frequency``), fits every cell of ``grid``
    on that window's out-of-sample fit/validation split (see module
    docstring), picks the cell with the highest mean validation rank IC,
    then refits *that* cell on the full window to serve the next test
    period. A ``grid`` of exactly one cell degenerates gracefully into "fit
    one configuration, still report its own OOS validation IC" -- used
    directly by Track M's single-cell smoke test and its placebo, not just
    by the eventual full multi-cell grid.
    """

    def __init__(self, feature_columns: Sequence[str], grid: Sequence[MLGridCell]) -> None:
        if not grid:
            raise ValueError("ValidationSelectedLightGBMStrategy requires a non-empty grid")
        self.feature_columns = list(feature_columns)
        self.grid = list(grid)
        self._winner: LightGBMRankStrategy | None = None
        self.selected_cell: MLGridCell | None = None
        #: {config_id: mean OOS validation rank IC}, overwritten on every
        #: fit() call, matching every other per-period-refit strategy in
        #: this kernel (RidgeRankStrategy, LightGBMRankStrategy, B3).
        self.validation_ic_by_cell: dict[str, float] = {}
        self.validation_ic_series_by_cell: dict[str, pd.Series] = {}
        self.validation_quarter_start: pd.Timestamp | None = None

    def fit(self, train_frame: pd.DataFrame) -> None:
        best_ic = float("-inf")
        best_cell: MLGridCell | None = None
        ic_by_cell: dict[str, float] = {}
        ic_series_by_cell: dict[str, pd.Series] = {}
        validation_quarter_start: pd.Timestamp | None = None

        for cell in self.grid:
            required = [*self.feature_columns, cell.label_column]
            try:
                fit_rows, validation_rows, validation_quarter_start = split_fit_and_validation_rows(
                    train_frame, label_horizon_days=cell.label_horizon_days
                )
            except ValueError:
                ic_by_cell[cell.config_id] = float("nan")
                continue
            fit_rows = fit_rows.dropna(subset=required)
            validation_rows = validation_rows.dropna(subset=required)
            if fit_rows.empty or validation_rows.empty:
                ic_by_cell[cell.config_id] = float("nan")
                del fit_rows, validation_rows
                gc.collect()
                continue

            model = LightGBMRankStrategy(
                self.feature_columns, cell.label_column, max_depth=cell.max_depth
            )
            fit_sample_weight = None
            if cell.recency_halflife_days is not None:
                # as_of = this cell's own fit_end (the embargoed cutoff of
                # *this* cell's fit window, not the outer walk-forward
                # train_cutoff) -- a longer-embargo cell's fit window ends
                # earlier, so its rows' ages (and therefore weights) are
                # computed relative to its own last usable date, not a
                # shared date that some cells' fit rows never reach.
                fit_sample_weight = recency_sample_weight(
                    fit_rows["trade_date"],
                    as_of=fit_rows["trade_date"].max(),
                    halflife_days=cell.recency_halflife_days,
                )
            fit_with_optional_sample_weight(model, fit_rows, fit_sample_weight)
            # Same rationale as b3_grid_strategy.py: this loop can hold two
            # DataFrame-sized copies (fit_rows/validation_rows) plus a
            # LightGBM booster alive per iteration; pandas' BlockManager
            # keeps circular references, so explicit del + gc.collect() is
            # required to actually free them before the next cell, not just
            # tidiness (see that module's own comment for the OOM incident
            # this defends against).
            del fit_rows
            gc.collect()

            if "symbol" not in validation_rows.columns:
                validation_rows = validation_rows.assign(symbol=validation_rows.index.astype(str))
            scores = model.score(validation_rows)
            ic_series = rank_ic_by_date(scores, validation_rows, cell.label_column)
            mean_ic = float(ic_series.mean()) if not ic_series.empty else float("nan")
            ic_by_cell[cell.config_id] = mean_ic
            ic_series_by_cell[cell.config_id] = ic_series
            del validation_rows, scores
            gc.collect()

            if mean_ic == mean_ic and mean_ic > best_ic:  # NaN-safe: NaN != NaN
                best_ic = mean_ic
                best_cell = cell
            else:
                del model
                gc.collect()

        if best_cell is None:
            raise ValueError(
                "no grid cell produced a usable out-of-sample validation rank IC for "
                f"training window ending {pd.Timestamp(train_frame['trade_date'].max()).date()}"
            )

        # Serve the winner refit on the *full* window (fit + validation) --
        # see module docstring for why this is not a leak. Selection above
        # never used this combined fit.
        final_required = [*self.feature_columns, best_cell.label_column]
        final_rows = train_frame.dropna(subset=final_required)
        final_model = LightGBMRankStrategy(
            self.feature_columns, best_cell.label_column, max_depth=best_cell.max_depth
        )
        final_sample_weight = None
        if best_cell.recency_halflife_days is not None:
            final_sample_weight = recency_sample_weight(
                final_rows["trade_date"],
                as_of=final_rows["trade_date"].max(),
                halflife_days=best_cell.recency_halflife_days,
            )
        fit_with_optional_sample_weight(final_model, final_rows, final_sample_weight)

        self._winner = final_model
        self.selected_cell = best_cell
        self.validation_ic_by_cell = ic_by_cell
        self.validation_ic_series_by_cell = ic_series_by_cell
        self.validation_quarter_start = validation_quarter_start

    def score(self, asof_frame: pd.DataFrame) -> pd.Series:
        if self._winner is None:
            raise RuntimeError("ValidationSelectedLightGBMStrategy.score called before fit")
        return self._winner.score(asof_frame)

    def top_feature_importances(self, n: int = 20) -> pd.Series:
        if self._winner is None:
            raise RuntimeError("top_feature_importances called before fit")
        return self._winner.top_feature_importances(n=n)
