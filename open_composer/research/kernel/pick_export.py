"""Persist a walk-forward weight schedule's *picks* (not just its weights).

Why this exists (H-20260916-03, 2026-09-16): every meta-labeling hypothesis
needs one row per (rebalance date, held symbol) carrying the primary
signal's own score/rank and the features that were visible at that date --
``build_weight_schedule`` computes exactly that internally (it scores the
PIT cohort, ranks it, takes the top ``k``) but only returns the surviving
``{symbol: weight}`` dict, so a second-stage model had no way to see the
score, the cohort percentile, or the as-of feature row without
re-implementing the selection loop and risking divergence from the cell it
is supposed to be filtering.

The hook is additive on both sides: ``build_weight_schedule`` grew one
optional ``pick_observer`` keyword (default ``None`` -- not part of
``ExperimentConfig``, so no config hash and no recorded result changes), and
this module supplies the collector that turns those callbacks into a frame.
Nothing here decides *which* rows are picked; it only records the rows
``build_weight_schedule`` already picked.

``weight_schedule_from_pick_frame`` is the inverse direction: a frame of
(rebalance_date, symbol, weight) -- e.g. the same picks after a second-stage
model has re-sized or dropped some of them -- becomes a
``list[RebalanceEvent]`` that ``returns_from_weight_schedule`` can price
with the identical cost/execution conventions as the original cell, so a
re-sized book and its equal-weight parent are never compared across two
different return engines.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from open_composer.research.kernel.loop import RebalanceEvent

#: Columns every collector emits, in order, before the as-of feature columns.
PICK_FRAME_COLUMNS: tuple[str, ...] = (
    "rebalance_date",
    "symbol",
    "weight",
    "score",
    "score_rank",
    "score_pct",
    "cohort_size",
    "universe_size",
)

#: Weights below this are treated as "not held" when rebuilding a schedule --
#: a second-stage model that sizes a name to 0 must produce a book without
#: that name, not a book with a zero-weight entry (which would still be
#: counted as a held column by ``returns_from_weight_schedule``'s turnover
#: bookkeeping and would inflate the reported position count).
MIN_HELD_WEIGHT = 1e-12


@dataclass
class PickCollector:
    """Accumulate one row per (rebalance date, symbol in the book).

    Pass an instance as ``build_weight_schedule(pick_observer=...)``. For
    every rebalance date that produced a non-empty as-of cross-section, it
    receives the date, that date's full PIT cohort frame, the strategy's
    scores over that whole cohort, and the final weights (after any trend-gate
    override), and records:

    * ``weight`` -- the weight actually assigned by the schedule, so a
      gate-closed week shows up as its cash leg rather than silently
      disappearing;
    * ``score`` -- the primary signal's own score for that symbol (``NaN``
      for a symbol that is in the book but not in the scored cohort, i.e. a
      cash or hedge leg);
    * ``score_rank`` -- 1 = highest score in that date's cohort;
    * ``score_pct`` -- ascending percentile of the score within that date's
      cohort (1.0 = best), the "momentum percentile" feature a second-stage
      model needs and cannot recover from the book alone (the book is a
      top-k truncation, so its own internal ranks say nothing about where
      the cohort's tail was);
    * ``cohort_size``/``universe_size`` -- how many rows were scored and how
      big the PIT universe was, for later breadth/coverage diagnostics.

    ``feature_columns`` are additionally copied from the as-of frame, which
    is the only PIT-safe place to read them from: they are that date's own
    rows, before any later data exists.
    """

    feature_columns: tuple[str, ...] = ()
    rows: list[dict[str, Any]] = field(default_factory=list)

    def __call__(
        self,
        *,
        date: pd.Timestamp,
        asof_frame: pd.DataFrame,
        scores: pd.Series,
        weights: Mapping[str, float],
        universe_size: int,
    ) -> None:
        ranks = scores.rank(ascending=False, method="first")
        percentiles = scores.rank(ascending=True, pct=True, method="average")
        wanted = [column for column in self.feature_columns if column in asof_frame.columns]
        features = asof_frame.set_index("symbol")[wanted] if wanted else None
        cohort = set(scores.index)
        for symbol, weight in weights.items():
            in_cohort = symbol in cohort
            row: dict[str, Any] = {
                "rebalance_date": pd.Timestamp(date),
                "symbol": str(symbol),
                "weight": float(weight),
                "score": float(scores[symbol]) if in_cohort else float("nan"),
                "score_rank": float(ranks[symbol]) if in_cohort else float("nan"),
                "score_pct": float(percentiles[symbol]) if in_cohort else float("nan"),
                "cohort_size": int(len(scores)),
                "universe_size": int(universe_size),
            }
            for column in self.feature_columns:
                if features is not None and column in features.columns and symbol in features.index:
                    row[column] = float(features.at[symbol, column])
                else:
                    row[column] = float("nan")
            self.rows.append(row)

    def to_frame(self) -> pd.DataFrame:
        columns = [*PICK_FRAME_COLUMNS, *self.feature_columns]
        if not self.rows:
            return pd.DataFrame({column: pd.Series(dtype="float64") for column in columns})
        frame = pd.DataFrame(self.rows)
        return frame[columns].sort_values(["rebalance_date", "symbol"], ignore_index=True)

    def write_parquet(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        self.to_frame().to_parquet(target, index=False)
        return target


def weight_schedule_from_pick_frame(
    frame: pd.DataFrame,
    *,
    weight_column: str = "weight",
    date_column: str = "rebalance_date",
    symbol_column: str = "symbol",
    cash_symbol: str | None = None,
    universe_size_column: str | None = "universe_size",
) -> list[RebalanceEvent]:
    """``list[RebalanceEvent]`` (one per rebalance date present in ``frame``)
    ready for :func:`loop.returns_from_weight_schedule`.

    Rows with a weight at or below :data:`MIN_HELD_WEIGHT` are dropped, so a
    second-stage model that sizes a name to zero produces a genuinely
    smaller book. When ``cash_symbol`` is given, whatever fraction of each
    date's book is left unassigned (``1 - sum(weights)``, clipped at zero) is
    placed on that symbol -- the explicit "the rest sits in BIL" convention,
    which matters because ``returns_from_weight_schedule``'s own implicit
    residual is *zero-return* cash, not a T-bill. A date whose weights sum to
    zero therefore becomes a full cash week rather than an empty (skipped)
    event.
    """
    events: list[RebalanceEvent] = []
    if frame.empty:
        return events
    for date, rows in frame.groupby(date_column, sort=True):
        weights: dict[str, float] = {}
        for symbol, weight in zip(rows[symbol_column], rows[weight_column], strict=True):
            value = float(weight)
            if value <= MIN_HELD_WEIGHT:
                continue
            weights[str(symbol)] = weights.get(str(symbol), 0.0) + value
        if cash_symbol is not None:
            residual = 1.0 - sum(weights.values())
            if residual > MIN_HELD_WEIGHT:
                weights[cash_symbol] = weights.get(cash_symbol, 0.0) + residual
        universe_size = 0
        if universe_size_column is not None and universe_size_column in rows.columns:
            universe_size = int(rows[universe_size_column].iloc[0])
        events.append(
            RebalanceEvent(
                date=pd.Timestamp(date).isoformat(),
                universe_size=universe_size,
                selected=weights,
                portfolio_beta=None,
            )
        )
    return events


def turnover_per_rebalance(schedule: Sequence[RebalanceEvent]) -> list[float]:
    """``sum |w_t - w_{t-1}|`` for every active event, in schedule order --
    the same two-sided turnover ``returns_from_weight_schedule`` charges cost
    on (its first event, from an empty book, is therefore ~1.0 for a fully
    invested start), exposed separately so a report can quote turnover
    without re-deriving it from the cost series.
    """
    out: list[float] = []
    previous: dict[str, float] = {}
    for event in schedule:
        if not event.selected:
            continue
        weights = {s: w for s, w in event.selected.items() if s != "__SPY_HEDGE__"}
        touched = set(weights) | set(previous)
        out.append(sum(abs(weights.get(s, 0.0) - previous.get(s, 0.0)) for s in touched))
        previous = weights
    return out
