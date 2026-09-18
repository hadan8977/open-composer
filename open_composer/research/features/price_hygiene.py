"""Price-panel hygiene: vendor ghost bars, unadjusted regime breaks, and
returns that must never be padded across a hole in the tape.

Promoted from ``scripts/run_h20260916_05_13d_drift.py``'s local
``mask_unadjusted_corporate_actions`` (2026-09-17) so every experiment sees
the same cleaning instead of each round rediscovering it. That round's first
tradability run printed a 2024-onward CAGR of **154%** with 448% annualized
volatility -- all of it from two symbols, and it looked like a discovery
rather than a bug, which is why this belongs in a shared module with a
manifest rather than in whichever script happens to remember.

Three separate defects, in the order they happen:

``ghost bars``
    ``data/sip/daily`` carries placeholder sessions for a security that is
    not trading: ``volume = 0``, ``trade_count = 0``, and
    ``open = high = low = close`` at the last price the security ever
    printed. WW (WW International) prints 0.2496 with zero volume on every
    session from 2025-06-02 to 2025-07-03 -- the old, cancelled equity's
    final trade carried forward -- and then the post-Chapter-11 *new* equity
    prints 40.00 on 2025-07-07. 68,720 such rows exist across 341 symbols of
    the universe union (1.1% of the daily archive, measured 2026-09-17).
    They are not prices. They manufacture warm-up history -- a symbol that
    has not traded for two years still "accumulates" the 252 rows
    ``daily_features.py``'s row-count guard asks for, so ``ret_252`` divides
    today's price by a dead company's frozen quote (measured: TLN's
    ``momentum_252_21`` on 2024-11-29 was 14.08, i.e. +1,408%, against the
    pre-bankruptcy stub; after the fix it is null until a real year of
    trading exists). They also flatten the return series (``ret_1 == 0``, so
    ``vol_*``/``amihud_*``/``dollar_adv_*`` are wrong) and they *hide* the
    hole in the tape, so a gap rule cannot see it. Dropped at the source by
    :data:`GHOST_BAR_SQL_PREDICATE` in ``features/daily_features.py``;
    :func:`drop_ghost_bars` is the pandas equivalent for a caller reading the
    archive directly.

``regime breaks`` (:func:`detect_price_breaks`)
    Even with ghost bars gone, two consecutive *real* observations can be
    two different securities or two different share bases:

    * ``jump`` -- a one-day price ratio above ``max_one_day_price_ratio``
      (equivalently ``|log-return| > log(ratio)``, 2.30 at the 10x default)
      with no corresponding corporate action. Post-bankruptcy relistings
      under a reused ticker (WW, CBL 0.0622 -> 20.88, GPOR, VAL, DBD, BTU,
      CRC, CORZ, LINE), IPOs on a recycled ticker (SNOW 23.75 -> 253.93 --
      the pre-2020 rows are Intrawest, not Snowflake) and unadjusted reverse
      splits on micro-caps and leveraged ETNs all look like this.
    * ``gap`` -- at least ``max_gap_sessions`` sessions of the shared
      trading calendar between two observations. AZUL disappears from the
      tape for 253 sessions and comes back at 8.88; AZN has a 21-session
      hole with a 2.05x ADR-ratio step that no jump threshold would catch.

    The adjustment factor is **not recoverable from the panel** (Alpaca
    serves ``adjustment=all`` prices with no factor column, and for a
    cancelled-equity reorganization there is no factor to serve), so the
    pre-break series is treated as a *different security* and blanked rather
    than spliced on. Blanking the price *level*, not just the single return,
    is what makes it impossible for any holding window to straddle the join.
    Where a real corporate-action feed exists, reconcile against it instead
    -- see ``open_composer/research/corporate_action_reconciliation.py``;
    ``known_corporate_actions`` below is the hook for that feed, and the
    manifest records that none was supplied.

``padded returns`` (:func:`daily_returns_no_pad`)
    ``DataFrame.pct_change()`` defaults to ``fill_method="pad"``, which
    carries the last price across a ``NaN`` hole and books the whole
    multi-session move as one day's return (AZUL: +1,730%). Every return
    taken off a price matrix in this repo must go through
    :func:`daily_returns_no_pad`, which leaves the crossing day ``NaN`` so
    the caller's own missing-data convention (the kernel's ``fillna(0.0)``:
    "no move") applies instead of a fabricated one.

Masking is deliberately conservative in one direction and honest about it:
a symbol's history is blanked up to and including its **last** break, so a
single bad vendor bar (AQB prints 0.144 and 3.328 on 2017-01-09/10 between
neighbours near 500) costs that symbol its earlier history too. The
alternative -- splicing -- requires a factor nobody in this repo has.

Residuals, stated rather than hidden:

* Gaps shorter than ``max_gap_sessions`` become ``NaN`` returns (not
  fabricated ones) but are not masked, so a two-session halt that reopens
  30% lower still books that move on the reopen day. That is a real price
  move for a holder, so this is a choice, not an oversight.
* This module cleans *prices*. The feature tables are built by windows that
  count rows, not sessions, so whenever the real rows on both sides of a
  hole add up to the window length, a trailing 252-row ``momentum_252_21``
  still reaches across it and scores the wrong security's return -- the
  2024-onward rule-momentum book picks WOLF nine times in 2026-07/08 on a
  momentum figure that partly measures the pre-Chapter-11 equity. Masking
  prices stops the fabricated P&L; it does not stop the fabricated
  *selection*. Fixing that needs a calendar-distance guard in
  ``features/daily_features.py``'s window definitions (recorded in
  ``reports/research/control/price-hygiene-fix-2026-09-17.md``).
"""

from __future__ import annotations

import dataclasses
import warnings
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np
import pandas as pd

#: SQL predicate selecting vendor placeholder bars, for a DuckDB reader over
#: ``data/sip/daily``. ``trade_count`` is ``COALESCE``d because an older
#: shard may not carry it; a bar with no trades and no volume is a
#: placeholder whether or not the vendor said so. Every row this matched in
#: the archive (2026-09-17: 68,720 rows) also had ``open = high = low =
#: close``, so the flat-OHLC condition is documentation, not a second test.
GHOST_BAR_SQL_PREDICATE = "(volume = 0 AND COALESCE(trade_count, 0) = 0)"

#: Columns the full predicate wants, in the order they tighten it.
_GHOST_BAR_OHLC_COLUMNS = ("open", "high", "low", "close")


def ghost_bar_sql_predicate(available_columns: Collection[str]) -> str | None:
    """The strictest ghost-bar predicate expressible over
    ``available_columns``, or ``None`` when the columns cannot express one.

    A caller reading a bar table it did not write (a test fixture, an older
    archive, a delisted-names side archive) may not have ``trade_count`` or
    the full OHLC set. Rather than fail, or silently widen the predicate to
    plain ``volume = 0`` (which would also drop the ~20k real sessions whose
    adjusted volume rounds to zero -- ABTC's back-adjusted 303,000 price with
    a handful of trades), this returns the tightest form the schema supports
    and lets the caller record which one it used.
    """
    columns = {str(column).lower() for column in available_columns}
    if "volume" not in columns:
        return None
    parts = ["volume = 0"]
    if "trade_count" in columns:
        parts.append("COALESCE(trade_count, 0) = 0")
    if set(_GHOST_BAR_OHLC_COLUMNS) <= columns:
        parts.append("open = high AND high = low AND low = close")
    return "(" + " AND ".join(parts) + ")"


#: A one-day price ratio at or beyond this (or its reciprocal) is treated as
#: a share-basis or security change rather than a return. 10x = a 2.30
#: absolute log-return; the widest *real* single-day move in the liquid
#: universe is far below it (2025-04-09 TQQQ +35%), and a 3x leveraged ETN
#: cannot reach it either.
DEFAULT_MAX_ONE_DAY_PRICE_RATIO = 10.0

#: Sessions of the shared trading calendar between two observations before
#: the join is *reported* as a break. ``5`` (one week) keeps ordinary one-
#: and two-session halts as real, tradeable history.
DEFAULT_MAX_GAP_SESSIONS = 5

#: A reported ``gap`` is only *masked* when it also looks like a different
#: security rather than an illiquid name that simply did not trade: either
#: the price steps by at least this much in absolute log terms across the
#: hole, or the hole is at least ``DEFAULT_MASK_GAP_LONG_SESSIONS`` long.
#: Measured on the rebuilt panel (2026-09-17): of 807 holes, 643 reopen
#: within +-5% -- masking a microcap's whole prior history because it went
#: five sessions without a trade is over-reach, and the un-padded return
#: already refuses to fabricate the crossing move. 0.20 (~22%) keeps every
#: economically meaningful join: AZN's 2.05x ADR step, AZUL, TLN, WW.
DEFAULT_MASK_GAP_MIN_ABS_LOG_STEP = 0.20

#: A hole this long (~one calendar month) is masked whatever the price step:
#: NBIS/Yandex was off the tape for 666 sessions and came back 5.6% higher,
#: which the step rule alone would wave through.
DEFAULT_MASK_GAP_LONG_SESSIONS = 21

#: Stamp for anything priced through this module, so a metric computed with
#: hygiene on can never be silently compared with one computed without it.
PRICE_HYGIENE_CONTRACT = "price_hygiene.mask_regime_breaks_no_pad.v1"

BreakKind = Literal["jump", "gap"]


@dataclass(frozen=True)
class PriceBreak:
    """One discontinuity in one symbol's price series."""

    symbol: str
    kind: BreakKind
    #: Last session with a valid price before the break.
    last_session_before: pd.Timestamp
    #: First session with a valid price after it.
    first_session_after: pd.Timestamp
    #: ``price_after / price_before`` (close).
    price_ratio: float
    #: Distance in shared-calendar sessions (1 = consecutive sessions).
    gap_sessions: int
    #: True when a caller-supplied corporate-action feed explains this date.
    explained_by_corporate_action: bool = False
    #: Set by :func:`mask_regime_breaks`: whether this break is the one that
    #: actually blanked the symbol's earlier history.
    masked: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "kind": self.kind,
            "last_session_before": str(self.last_session_before.date()),
            "first_session_after": str(self.first_session_after.date()),
            "price_ratio": float(f"{self.price_ratio:.6g}"),
            "log_return": float(f"{np.log(self.price_ratio):.6g}")
            if self.price_ratio > 0
            else None,
            "gap_sessions": int(self.gap_sessions),
            "explained_by_corporate_action": bool(self.explained_by_corporate_action),
            "masked": bool(self.masked),
        }


@dataclass(frozen=True)
class PriceHygieneReport:
    """What :func:`sanitize_price_matrices` found and did, ready to be
    written into an experiment manifest verbatim.
    """

    breaks: tuple[PriceBreak, ...] = ()
    max_one_day_price_ratio: float = DEFAULT_MAX_ONE_DAY_PRICE_RATIO
    max_gap_sessions: int = DEFAULT_MAX_GAP_SESSIONS
    mask_gap_min_abs_log_step: float = DEFAULT_MASK_GAP_MIN_ABS_LOG_STEP
    mask_gap_long_sessions: int = DEFAULT_MASK_GAP_LONG_SESSIONS
    symbols_masked: int = 0
    symbols_masked_for_jump: int = 0
    symbols_masked_for_gap: int = 0
    price_cells_masked: int = 0
    corporate_action_feed: str | None = None
    contract: str = PRICE_HYGIENE_CONTRACT
    notes: tuple[str, ...] = field(default_factory=tuple)
    #: Symbols whose pre-break history was actually blanked -- a subset of
    #: the symbols in ``breaks`` (a break explained by a corporate-action
    #: feed is reported but not masked).
    masked_symbols: tuple[str, ...] = ()

    def manifest(self) -> dict[str, Any]:
        """JSON-ready summary. ``breaks_by_symbol`` keeps every break, not
        just the masking one, so the next reader can audit the threshold.
        """
        by_symbol: dict[str, list[dict[str, Any]]] = {}
        for break_ in self.breaks:
            by_symbol.setdefault(break_.symbol, []).append(break_.as_dict())
        return {
            "contract": self.contract,
            "pad_across_gaps": False,
            "thresholds": {
                "max_one_day_price_ratio": self.max_one_day_price_ratio,
                "max_one_day_abs_log_return": float(f"{np.log(self.max_one_day_price_ratio):.6g}"),
                "max_gap_sessions": self.max_gap_sessions,
                "mask_gap_min_abs_log_step": self.mask_gap_min_abs_log_step,
                "mask_gap_long_sessions": self.mask_gap_long_sessions,
            },
            "breaks_detected": len(self.breaks),
            "symbols_masked": self.symbols_masked,
            "symbols_masked_for_jump": self.symbols_masked_for_jump,
            "symbols_masked_for_gap": self.symbols_masked_for_gap,
            "price_cells_masked": self.price_cells_masked,
            "masked_symbols": list(self.masked_symbols),
            "corporate_action_feed": self.corporate_action_feed or "none_available",
            "breaks_by_symbol": by_symbol,
            "notes": list(self.notes),
        }


def is_ghost_bar(frame: pd.DataFrame) -> pd.Series:
    """Boolean mask of vendor placeholder bars (see
    :data:`GHOST_BAR_SQL_PREDICATE`). Requires ``volume``; uses
    ``trade_count`` when present.
    """
    volume = pd.to_numeric(frame["volume"], errors="coerce").fillna(0.0)
    if "trade_count" in frame.columns:
        trade_count = pd.to_numeric(frame["trade_count"], errors="coerce").fillna(0.0)
    else:
        trade_count = pd.Series(0.0, index=frame.index)
    return (volume == 0.0) & (trade_count == 0.0)


def drop_ghost_bars(frame: pd.DataFrame) -> pd.DataFrame:
    """``frame`` without vendor placeholder bars. A session with no trades
    and no volume is not a session for that security, so removing it turns a
    hidden flat line into an honest hole that :func:`detect_price_breaks`
    can see.
    """
    return frame.loc[~is_ghost_bar(frame)].copy()


def _normalize_action_dates(
    known_corporate_actions: Mapping[str, Collection[Any]] | None,
) -> dict[str, set[pd.Timestamp]]:
    if not known_corporate_actions:
        return {}
    return {
        str(symbol): {pd.Timestamp(value).normalize() for value in values}
        for symbol, values in known_corporate_actions.items()
    }


def detect_price_breaks(
    close_wide: pd.DataFrame,
    *,
    max_one_day_price_ratio: float = DEFAULT_MAX_ONE_DAY_PRICE_RATIO,
    max_gap_sessions: int = DEFAULT_MAX_GAP_SESSIONS,
    known_corporate_actions: Mapping[str, Collection[Any]] | None = None,
) -> list[PriceBreak]:
    """Every discontinuity in ``close_wide`` (sessions x symbols).

    A break is a pair of consecutive *valid* observations (finite, > 0)
    whose price ratio leaves ``[1 / max_one_day_price_ratio,
    max_one_day_price_ratio]`` (``jump``) or which sit at least
    ``max_gap_sessions`` sessions apart in ``close_wide``'s own index
    (``gap``). A pair that is both is reported as a ``jump``.

    ``known_corporate_actions`` maps symbol -> dates explained by a real
    corporate-action feed; matching breaks are still reported but marked
    ``explained_by_corporate_action`` and are not masked by
    :func:`mask_regime_breaks`.
    """
    if max_gap_sessions < 2:
        raise ValueError("max_gap_sessions must be at least 2 (1 = consecutive sessions)")
    if max_one_day_price_ratio <= 1.0:
        raise ValueError("max_one_day_price_ratio must be greater than 1")

    actions = _normalize_action_dates(known_corporate_actions)
    index = pd.DatetimeIndex(close_wide.index)
    breaks: list[PriceBreak] = []
    for symbol in close_wide.columns:
        values = pd.to_numeric(close_wide[symbol], errors="coerce").to_numpy(dtype="float64")
        valid = np.flatnonzero(np.isfinite(values) & (values > 0))
        if valid.size < 2:
            continue
        ratios = values[valid[1:]] / values[valid[:-1]]
        gaps = np.diff(valid)
        is_jump = (ratios > max_one_day_price_ratio) | (ratios < 1.0 / max_one_day_price_ratio)
        is_gap = gaps >= max_gap_sessions
        symbol_actions = actions.get(str(symbol), set())
        for position in np.flatnonzero(is_jump | is_gap):
            first_after = index[int(valid[position + 1])]
            breaks.append(
                PriceBreak(
                    symbol=str(symbol),
                    kind="jump" if is_jump[position] else "gap",
                    last_session_before=index[int(valid[position])],
                    first_session_after=first_after,
                    price_ratio=float(ratios[position]),
                    gap_sessions=int(gaps[position]),
                    explained_by_corporate_action=pd.Timestamp(first_after).normalize()
                    in symbol_actions,
                )
            )
    return breaks


def _is_maskable(
    break_: PriceBreak,
    *,
    mask_gap_min_abs_log_step: float,
    mask_gap_long_sessions: int,
) -> bool:
    """Whether this break looks like a *different security*, not a halt.

    Every ``jump`` does (a 10x one-session move is not a price). A ``gap``
    only does when the price also steps materially across the hole, or when
    the hole is long enough that "the same security did not trade" stops
    being the likely explanation. Without this second test, dropping ghost
    bars (which is what makes holes visible at all) would blank the entire
    prior history of every illiquid microcap that went a week without a
    trade: 225 symbols instead of 150 on the 2026-09-17 panel, 643 of whose
    807 holes reopen within +-5%.
    """
    if break_.explained_by_corporate_action:
        return False
    if break_.kind == "jump":
        return True
    if break_.gap_sessions >= mask_gap_long_sessions:
        return True
    ratio = break_.price_ratio
    return ratio > 0 and abs(float(np.log(ratio))) >= mask_gap_min_abs_log_step


def mask_regime_breaks(
    close_wide: pd.DataFrame,
    *other_frames: pd.DataFrame | None,
    max_one_day_price_ratio: float = DEFAULT_MAX_ONE_DAY_PRICE_RATIO,
    max_gap_sessions: int = DEFAULT_MAX_GAP_SESSIONS,
    mask_gap_min_abs_log_step: float = DEFAULT_MASK_GAP_MIN_ABS_LOG_STEP,
    mask_gap_long_sessions: int = DEFAULT_MASK_GAP_LONG_SESSIONS,
    known_corporate_actions: Mapping[str, Collection[Any]] | None = None,
    corporate_action_feed: str | None = None,
    notes: Sequence[str] = (),
) -> tuple[list[pd.DataFrame | None], PriceHygieneReport]:
    """Blank each symbol's history up to and including its last *maskable*
    break (see :func:`_is_maskable`), in ``close_wide`` and in every frame of
    ``other_frames`` sharing its index/columns (``open``, typically).

    Non-maskable breaks are still reported in the manifest with
    ``"masked": false`` -- they are real holes, they are simply handled by
    :func:`daily_returns_no_pad` refusing to invent the crossing return
    rather than by deleting history.

    The inputs are never mutated: copies are returned, in the order
    ``[close_wide, *other_frames]`` (``None`` entries pass through as
    ``None`` so a close-only caller needs no special case).
    """
    detected = detect_price_breaks(
        close_wide,
        max_one_day_price_ratio=max_one_day_price_ratio,
        max_gap_sessions=max_gap_sessions,
        known_corporate_actions=known_corporate_actions,
    )
    frames: list[pd.DataFrame | None] = [
        None if frame is None else frame.copy() for frame in (close_wide, *other_frames)
    ]
    index = pd.DatetimeIndex(close_wide.index)
    last_break: dict[str, PriceBreak] = {}
    for break_ in detected:
        if not _is_maskable(
            break_,
            mask_gap_min_abs_log_step=mask_gap_min_abs_log_step,
            mask_gap_long_sessions=mask_gap_long_sessions,
        ):
            continue
        current = last_break.get(break_.symbol)
        if current is None or break_.first_session_after >= current.first_session_after:
            last_break[break_.symbol] = break_
    breaks = tuple(
        dataclasses.replace(break_, masked=last_break.get(break_.symbol) is break_)
        for break_ in detected
    )

    cells_masked = 0
    jump_symbols = 0
    gap_symbols = 0
    for symbol, break_ in last_break.items():
        cutoff = index <= break_.last_session_before
        jump_symbols += break_.kind == "jump"
        gap_symbols += break_.kind == "gap"
        for frame in frames:
            if frame is None or symbol not in frame.columns:
                continue
            if frame is frames[0]:
                cells_masked += int(frame.loc[cutoff, symbol].notna().sum())
            frame.loc[cutoff, symbol] = np.nan

    report = PriceHygieneReport(
        breaks=breaks,
        max_one_day_price_ratio=max_one_day_price_ratio,
        max_gap_sessions=max_gap_sessions,
        mask_gap_min_abs_log_step=mask_gap_min_abs_log_step,
        mask_gap_long_sessions=mask_gap_long_sessions,
        symbols_masked=len(last_break),
        symbols_masked_for_jump=jump_symbols,
        symbols_masked_for_gap=gap_symbols,
        price_cells_masked=cells_masked,
        corporate_action_feed=corporate_action_feed,
        notes=tuple(notes),
        masked_symbols=tuple(sorted(last_break)),
    )
    return frames, report


def daily_returns_no_pad(prices: pd.DataFrame | pd.Series) -> pd.DataFrame | pd.Series:
    """One-day simple returns that never bridge a hole.

    ``pct_change()``'s default ``fill_method="pad"`` carries the last price
    across ``NaN`` and books a multi-session move as a single day; this
    leaves the crossing day ``NaN`` instead.
    """
    return prices.pct_change(fill_method=None)


def daily_returns_padding_gaps_legacy(
    prices: pd.DataFrame | pd.Series,
) -> pd.DataFrame | pd.Series:
    """The pre-2026-09-17 formula, **defect included**: padded across holes.

    Kept for exactly one purpose -- reproducing a number that was computed
    before this module existed (a ``portfolio_returns.buy_and_hold_drift.v2``
    ledger row), so a before/after comparison measures the fix rather than
    two unrelated code paths. Never use it for a new result.
    """
    with warnings.catch_warnings():
        # pandas 2.x deprecates the padding it is being asked for here on
        # purpose; the deprecation is the point of this function's existence.
        warnings.simplefilter("ignore", FutureWarning)
        return prices.pct_change(fill_method="pad")


def sanitize_price_matrices(
    close_wide: pd.DataFrame,
    open_wide: pd.DataFrame | None = None,
    *,
    max_one_day_price_ratio: float = DEFAULT_MAX_ONE_DAY_PRICE_RATIO,
    max_gap_sessions: int = DEFAULT_MAX_GAP_SESSIONS,
    mask_gap_min_abs_log_step: float = DEFAULT_MASK_GAP_MIN_ABS_LOG_STEP,
    mask_gap_long_sessions: int = DEFAULT_MASK_GAP_LONG_SESSIONS,
    known_corporate_actions: Mapping[str, Collection[Any]] | None = None,
    corporate_action_feed: str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame | None, PriceHygieneReport]:
    """``(close_wide, open_wide, report)`` with every symbol's pre-break
    history blanked -- the one call a pricing path needs.
    """
    frames, report = mask_regime_breaks(
        close_wide,
        open_wide,
        max_one_day_price_ratio=max_one_day_price_ratio,
        max_gap_sessions=max_gap_sessions,
        mask_gap_min_abs_log_step=mask_gap_min_abs_log_step,
        mask_gap_long_sessions=mask_gap_long_sessions,
        known_corporate_actions=known_corporate_actions,
        corporate_action_feed=corporate_action_feed,
    )
    masked_close, masked_open = frames
    assert masked_close is not None  # close_wide is never None
    return masked_close, masked_open, report
