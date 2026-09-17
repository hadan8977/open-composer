"""News-attention gates over an existing weekly pick book (H-20260916-02).

Why this is a module and not inline in
``scripts/run_h20260916_02_news_attention.py``: the same three reasons
``kernel/insider_gate.py`` gives -- the stop conditions are read off both a
literal book and an exposure-normalized one (lesson ``L-20260916-03``), the
same-size random control has to permute states *inside* each rebalance week to
be a control at all (lesson ``L-20260916-01``), and both of those are easy to
get subtly wrong once and then copy. They are defined here once, with tests in
``tests/test_kernel_news_gate.py``.

Nothing here selects stocks, prices a book, or reads a file. It takes a frame
that already has one row per (rebalance date, held symbol) with that date's
point-in-time news-attention columns, and returns states, rescaled weights and
diagnostics.

What the card's gate sentence actually says
-------------------------------------------
The card (and the round's brief) specify one gate: *"surge >= 2 and novelty >=
median -> full; no news in 20d -> half"*. Read literally that sentence leaves
the middle group -- has news, did not surge -- at full weight, and then the
"surge and novel" clause is **non-binding**: it names a subset of a group that
is already at 1.0. So the sentence does not pin down one experiment; it pins
down a family whose extremes are:

* :data:`GATE_NONEWS` -- the literal reading. Only the no-news names are
  halved; ``surge & novel`` changes nothing. This is an *avoid-the-ignored*
  gate.
* :data:`GATE_SURGE` -- the reading in which the clause binds: only
  ``surge & novel`` is at full weight and everything else is halved. This is a
  *keep-the-confirmed* gate. (Note that a name with no news in 20 sessions
  necessarily has ``news_count_5d == 0`` and therefore ``surge == 0``, so it is
  halved here too; the two conditions never conflict.)
* :data:`GATE_TIERED` -- both clauses binding with a middle tier at 0.75.
  The 0.75 is **invented** (the card gives no middle multiplier); it exists so
  the "both clauses bind monotonically" reading gets one shot too, and it is
  disclosed as invented in the report rather than presented as the card's.

All three are run, and all three count against the ``news_attention_features``
trial family, because choosing one of them after seeing the numbers is the
multiple-testing failure the family budget exists to prevent.

The novelty median is **not** computed here
-------------------------------------------
``gate_states`` compares ``novelty_5d`` against a ``novelty_median_ref``
column the caller supplies. The median of *which* population is a research
decision with a point-in-time consequence (the book's own median is endogenous
to the book; the top-500 pool's median is exogenous and is what a live
implementation could compute at the open), so it belongs in the driver, where
it is recorded in the report, not hidden in a predicate.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

#: The states a held name can be in. ``partial`` exists only for the tiered
#: gate; the two two-state gates never produce it.
FULL = "full"
PARTIAL = "partial"
HALF = "half"

#: State -> multiplier applied to the name's baseline (equal) weight.
STATE_WEIGHT_MULTIPLIER: Mapping[str, float] = {FULL: 1.0, PARTIAL: 0.75, HALF: 0.5}

#: The card's own thresholds, verbatim. Not tunable from the CLI: a gate whose
#: cut can be swept is a parameter search, and this card is not preregistered
#: as one.
SURGE_THRESHOLD = 2.0

GATE_SURGE = "gate_N_surge"
GATE_NONEWS = "gate_N_nonews"
GATE_TIERED = "gate_N_tiered"


@dataclass(frozen=True)
class GateSpec:
    """One gate: which feature columns it reads and what it does with them."""

    name: str
    description: str
    columns: tuple[str, ...]


GATE_SPECS: Mapping[str, GateSpec] = {
    GATE_SURGE: GateSpec(
        name=GATE_SURGE,
        description=(
            "keep-the-confirmed：`attention_surge_5d >= 2` 且 "
            "`novelty_5d >= novelty_median_ref` 则满仓，其余减半"
        ),
        columns=("attention_surge_5d", "novelty_5d", "novelty_median_ref"),
    ),
    GATE_NONEWS: GateSpec(
        name=GATE_NONEWS,
        description=(
            "avoid-the-ignored（卡上句子的字面读法）：过去 20 个交易日无报道则减半，其余满仓"
        ),
        columns=("news_count_20d",),
    ),
    GATE_TIERED: GateSpec(
        name=GATE_TIERED,
        description=(
            "两个子句同时生效的三档读法：突增且新颖 → 1.0；20 日无报道 → 0.5；"
            "其余 → 0.75（**0.75 是本轮自己定的**，卡上没有中间档）"
        ),
        columns=("attention_surge_5d", "novelty_5d", "novelty_median_ref", "news_count_20d"),
    ),
}

#: Every feature column any gate reads, for one-shot loading.
GATE_FEATURE_COLUMNS: tuple[str, ...] = tuple(
    sorted({column for spec in GATE_SPECS.values() for column in spec.columns})
)


def _surge_and_novel(frame: pd.DataFrame) -> pd.Series:
    """``surge >= 2 and novelty >= novelty_median_ref``, with missing values
    counting as *not* confirmed.

    ``novelty_5d`` is null exactly when the name had no article in the trailing
    5 sessions (novelty of nothing is undefined, see
    ``features/news_attention.novelty_from_overlaps``), so a null can never
    make this true -- which is the conservative direction.
    """
    surge = pd.to_numeric(frame["attention_surge_5d"], errors="coerce").fillna(0.0)
    novelty = pd.to_numeric(frame["novelty_5d"], errors="coerce")
    reference = pd.to_numeric(frame["novelty_median_ref"], errors="coerce")
    novel = (novelty >= reference).fillna(False)
    return (surge >= SURGE_THRESHOLD) & novel


def _no_news_20d(frame: pd.DataFrame) -> pd.Series:
    """``news_count_20d == 0``, with missing counting as no news.

    The news-attention table has a row for every stock-day in the point-in-time
    top-1000 cohort with 0 -- not null -- where nothing was published, so a
    null here means the join found no row at all for that (date, symbol); the
    conservative reading of "we have no evidence anybody wrote about it" is
    "nobody wrote about it".
    """
    counts = pd.to_numeric(frame["news_count_20d"], errors="coerce").fillna(0.0)
    return counts <= 0.0


def gate_states(frame: pd.DataFrame, gate: str) -> pd.Series:
    """The per-row state (``full``/``partial``/``half``) that ``gate`` assigns."""
    spec = GATE_SPECS[gate]
    missing = [column for column in spec.columns if column not in frame.columns]
    if missing:
        raise KeyError(f"{gate} needs columns {missing} which the frame does not have")
    if gate == GATE_SURGE:
        return pd.Series(
            np.where(_surge_and_novel(frame), FULL, HALF), index=frame.index, dtype="object"
        )
    if gate == GATE_NONEWS:
        return pd.Series(
            np.where(_no_news_20d(frame), HALF, FULL), index=frame.index, dtype="object"
        )
    if gate == GATE_TIERED:
        confirmed = _surge_and_novel(frame)
        ignored = _no_news_20d(frame)
        return pd.Series(
            np.where(confirmed, FULL, np.where(ignored, HALF, PARTIAL)),
            index=frame.index,
            dtype="object",
        )
    raise KeyError(gate)


def state_shares(states: pd.Series) -> dict[str, float]:
    """``{state: share of rows}`` for all three states, so a state a gate never
    produced reports as an explicit 0.0 rather than silently missing. ``{}``
    only when there are no rows at all.
    """
    total = len(states)
    if total == 0:
        return {}
    counts = states.astype(str).value_counts()
    return {state: float(counts.get(state, 0)) / total for state in (FULL, PARTIAL, HALF)}


def normalize_weights_to_full_exposure(
    frame: pd.DataFrame,
    *,
    weight_column: str = "weight",
    date_column: str = "rebalance_date",
) -> pd.DataFrame:
    """``frame`` with ``weight_column`` rescaled so each date's weights sum to
    1.0 -- the exposure-normalized book required by ``L-20260916-03``.

    Behaviourally identical to ``insider_gate.normalize_weights_to_full_exposure``
    and deliberately duplicated rather than imported: that module's docstring
    ties its convention to the Form 4 card's gates, and a shared helper would
    make either card's meaning depend on the other card's edits. A date whose
    weights all came out zero is left at zero rather than divided by zero.
    """
    out = frame.copy()
    totals = out.groupby(date_column)[weight_column].transform("sum")
    scaled = out[weight_column].where(totals <= 0.0, out[weight_column] / totals)
    out[weight_column] = scaled.fillna(0.0)
    return out


def shuffle_states_within_date(
    states: pd.DataFrame,
    seed: int,
    *,
    state_columns: Sequence[str] | None = None,
    date_column: str = "rebalance_date",
) -> pd.DataFrame:
    """``states`` with every state column permuted **within each rebalance
    date** -- the same-size random control ``L-20260916-01`` made mandatory.

    Permuting inside the week (not across the frame) keeps each week's exact
    full/partial/half counts, so the control book has the same position count,
    the same gross exposure after normalization and the same turnover profile
    as the real gate's; only *which* names get which tier is randomized. An
    "improvement" that survives this is about identity; one that does not is
    about size.

    Every state column is permuted with the **same** permutation per date, so a
    row that the real gate put in the top tier of every gate stays internally
    consistent across gates in the control too.
    """
    columns = (
        list(state_columns)
        if state_columns is not None
        else [column for column in states.columns if column.startswith("state_")]
    )
    if not columns:
        raise KeyError("no state_* columns to shuffle")
    rng = np.random.default_rng(seed)
    out = states.copy()
    arrays = {column: out[column].to_numpy(copy=True) for column in columns}
    for index in out.groupby(date_column, sort=True).indices.values():
        order = rng.permutation(len(index))
        for column in columns:
            arrays[column][index] = arrays[column][index][order]
    for column in columns:
        out[column] = arrays[column]
    return out


def gate_state_changes_per_year(
    frame: pd.DataFrame,
    gate: str,
    *,
    date_column: str = "rebalance_date",
    symbol_column: str = "symbol",
) -> dict[str, int]:
    """``{year: number of (date, symbol) pairs whose state differs from that
    symbol's state at the previous date it was held}``. A name entering the
    book for the first time is not a change.
    """
    column = f"state_{gate}"
    if column not in frame.columns:
        raise KeyError(f"frame has no {column}")
    ordered = frame.sort_values([symbol_column, date_column])
    previous = ordered.groupby(symbol_column, sort=False)[column].shift(1)
    changed = previous.notna() & (ordered[column].astype(str) != previous.astype(str))
    years = pd.to_datetime(ordered[date_column]).dt.year
    counts = years[changed].value_counts().sort_index()
    return {str(year): int(count) for year, count in counts.items()}


def rebalances_with_gate_change_per_year(
    frame: pd.DataFrame,
    gate: str,
    *,
    date_column: str = "rebalance_date",
    symbol_column: str = "symbol",
) -> dict[str, int]:
    """``{year: number of rebalance dates on which the gate changed at least
    one carried name's state}``. Every year with at least one rebalance date
    appears, with 0 when the gate never moved that year.
    """
    column = f"state_{gate}"
    if column not in frame.columns:
        raise KeyError(f"frame has no {column}")
    ordered = frame.sort_values([symbol_column, date_column])
    previous = ordered.groupby(symbol_column, sort=False)[column].shift(1)
    changed = previous.notna() & (ordered[column].astype(str) != previous.astype(str))
    dates = pd.to_datetime(ordered[date_column])
    counts = {str(year): 0 for year in sorted(dates.dt.year.unique())}
    for year, date in dates[changed].groupby(dates[changed].dt.year):
        counts[str(year)] = int(date.nunique())
    return counts
