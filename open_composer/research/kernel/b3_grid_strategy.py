"""Step 11 Wave B: B3's bounded grid + validation-year selection.

docs/plan-step-11-ml-first-loop-2026-09-06.zh.md section 4: "配置网格有界
（<=12 个）：标签周期 {5, 10, 21} x 树深 {3, 6} x 特征集 {仅日线, 日线+分钟线
派生}" (this module covers one feature set at a time -- 6 cells -- the
caller assembles the daily-only and daily+intraday halves separately) and
"选择规则写死：按训练窗口最后一年（验证年）的 rank IC 选，不看测试年。"

Implements ``loop.RankingStrategy`` so it plugs directly into the existing
``build_weight_schedule``/``run_experiment`` machinery exactly like B0-B2 --
no changes to ``loop.py`` needed. All the grid/selection logic lives in
``fit()``:

1. The *validation year* is the last calendar year present in whatever
   training window ``build_weight_schedule`` hands to ``fit()`` (that
   window is itself already anchored + embargoed against the real test
   year, so the validation year is always strictly before the test year).
2. Every grid cell (a ``(label_horizon, max_depth)`` pair) is fit on the
   *entire* training window (including the validation year -- the plan's
   own wording is "训练窗口最后一年", not "held out from the training
   window", so this is a literal reading, not a from-scratch nested
   holdout) and scored on the validation year's rows.
3. Rank IC per validation-year row date is the Pearson correlation between
   the predicted scores' cross-sectional rank and ``label_rank_h`` (which
   is already a percentile rank of the true forward return -- correlating
   against it directly gives the same value as Spearman-correlating against
   the raw forward return, since percentile rank is a monotonic, ~affine
   transform of integer rank).
4. The cell with the highest mean validation rank IC wins; its
   already-fitted model (from step 2, no need to refit) is what ``score()``
   delegates to for the upcoming test year.

Every cell's validation IC and the winner are retained after ``fit()``
(``self.validation_ic_by_cell``, ``self.selected_cell``) for the Wave B
report's "逐年 rank IC" table.
"""

from __future__ import annotations

import gc
from collections.abc import Sequence
from dataclasses import dataclass

import pandas as pd

from open_composer.research.kernel.lightgbm_rank_strategy import LightGBMRankStrategy


@dataclass(frozen=True)
class GridCell:
    label_horizon_days: int
    max_depth: int

    @property
    def label_column(self) -> str:
        return f"label_rank_{self.label_horizon_days}"

    @property
    def config_id(self) -> str:
        return f"h{self.label_horizon_days}_d{self.max_depth}"


#: The plan's full grid for one feature set: 3 horizons x 2 depths = 6 cells.
#: A second GridSelectedLightGBMStrategy instance with a different
#: feature_columns list (daily+intraday) covers the plan's other 6 cells --
#: this module doesn't hardcode a feature set, so the same 6-cell DEFAULT_GRID
#: is reused for both halves.
DEFAULT_GRID: tuple[GridCell, ...] = tuple(
    GridCell(label_horizon_days=horizon, max_depth=depth)
    for horizon in (5, 10, 21)
    for depth in (3, 6)
)


def _rank_ic_by_date(scores: pd.Series, asof_frame: pd.DataFrame, label_column: str) -> pd.Series:
    """Mean cross-sectional rank IC per date is computed by the caller by
    averaging this function's per-date output; kept separate (rather than
    returning a single float) so the Wave B report can show the IC's
    stability across the validation year, not just its mean.
    """
    frame = asof_frame[["trade_date", label_column]].copy()
    frame["score"] = scores.to_numpy()
    ic_per_date = frame.groupby("trade_date").apply(
        lambda g: g["score"].rank().corr(g[label_column]) if len(g) >= 5 else float("nan"),
        include_groups=False,
    )
    return ic_per_date.dropna()


class GridSelectedLightGBMStrategy:
    """B3: picks the best ``(label_horizon, max_depth)`` cell of ``grid`` by
    validation-year rank IC every time ``fit()`` is called (i.e. once per
    walk-forward test year, same cadence as B2's per-year refit).
    """

    def __init__(
        self, feature_columns: Sequence[str], grid: Sequence[GridCell] = DEFAULT_GRID
    ) -> None:
        self.feature_columns = list(feature_columns)
        self.grid = list(grid)
        self._winner: LightGBMRankStrategy | None = None
        self.selected_cell: GridCell | None = None
        #: {config_id: mean validation rank IC}, populated by the most
        #: recent fit() call -- overwritten each test year, matching every
        #: other per-year-refit strategy in this kernel (B2, B3 itself).
        self.validation_ic_by_cell: dict[str, float] = {}
        self.validation_ic_series_by_cell: dict[str, pd.Series] = {}
        self.validation_year: int | None = None

    def fit(self, train_frame: pd.DataFrame) -> None:
        validation_year = int(train_frame["trade_date"].dt.year.max())
        self.validation_year = validation_year
        validation_frame = train_frame.loc[train_frame["trade_date"].dt.year == validation_year]

        best_ic = float("-inf")
        best_model: LightGBMRankStrategy | None = None
        best_cell: GridCell | None = None
        ic_by_cell: dict[str, float] = {}
        ic_series_by_cell: dict[str, pd.Series] = {}

        for cell in self.grid:
            fit_rows = train_frame.dropna(subset=[*self.feature_columns, cell.label_column])
            model = LightGBMRankStrategy(
                self.feature_columns, cell.label_column, max_depth=cell.max_depth
            )
            model.fit(fit_rows)
            # Real OOM incident, 2026-09-09 (full 9-year daily_only grid,
            # memcg killed the whole run_capped.sh scope): six cells x nine
            # years means 54 of these dropna()'d copies over the run's
            # lifetime, each briefly coexisting with LightGBMRankStrategy.
            # fit's own float32 numpy copy *and* LightGBM's internal
            # binned-data copy of the same rows -- three representations of
            # a several-hundred-MB frame alive at once per cell, at the
            # grid's largest (last-test-year) window. Pandas DataFrames hold
            # circular refs via their internal BlockManager (see
            # run_baseline_chain.py::_load_panel's docstring for the same
            # lesson learned there first), so plain refcounting does not
            # reliably free `fit_rows` the moment this loop reassigns it on
            # the next iteration -- explicit del + gc.collect() is required,
            # not just tidiness.
            del fit_rows
            gc.collect()

            eval_rows = validation_frame.dropna(subset=[*self.feature_columns, cell.label_column])
            if eval_rows.empty:
                ic_by_cell[cell.config_id] = float("nan")
                del eval_rows
                gc.collect()
                continue
            # LightGBMRankStrategy.score requires a "symbol" column (it
            # returns a symbol-indexed Series for build_weight_schedule's
            # live scoring path) -- but train_frame (and therefore
            # validation_frame/eval_rows, both sliced from it) never carries
            # "symbol": build_weight_schedule's narrow-copy fix (commit
            # 00911bc) only ever selects trade_date + feature_columns +
            # label_column(s) into train_frame, on the correct premise that
            # no B0-B3 strategy's *fit* needs symbol identity. This internal
            # validation-scoring call is the one exception (it needs *some*
            # column named "symbol" to satisfy score()'s contract, not the
            # real identity) -- _rank_ic_by_date below only ever reads
            # scores.to_numpy() positionally against eval_rows, so a
            # synthetic placeholder is correct, not just expedient.
            if "symbol" not in eval_rows.columns:
                eval_rows = eval_rows.assign(symbol=eval_rows.index.astype(str))
            scores = model.score(eval_rows)
            ic_series = _rank_ic_by_date(scores, eval_rows, cell.label_column)
            mean_ic = float(ic_series.mean()) if not ic_series.empty else float("nan")
            ic_by_cell[cell.config_id] = mean_ic
            ic_series_by_cell[cell.config_id] = ic_series
            del eval_rows, scores
            gc.collect()

            if mean_ic == mean_ic and mean_ic > best_ic:  # NaN-safe: NaN != NaN
                best_ic = mean_ic
                best_model = model
                best_cell = cell
            else:
                # Not the winner (so far) -- drop the last reference to its
                # fitted LightGBM booster now rather than waiting for the
                # loop's next `model = ...` reassignment to orphan it.
                del model
                gc.collect()

        if best_model is None or best_cell is None:
            raise ValueError(
                f"no grid cell produced a usable validation rank IC for year {validation_year}"
            )
        self._winner = best_model
        self.selected_cell = best_cell
        self.validation_ic_by_cell = ic_by_cell
        self.validation_ic_series_by_cell = ic_series_by_cell

    def score(self, asof_frame: pd.DataFrame) -> pd.Series:
        if self._winner is None:
            raise RuntimeError("GridSelectedLightGBMStrategy.score called before fit")
        return self._winner.score(asof_frame)

    def top_feature_importances(self, n: int = 20) -> pd.Series:
        if self._winner is None:
            raise RuntimeError("top_feature_importances called before fit")
        return self._winner.top_feature_importances(n=n)
