"""T-20260929-01 batch (part A): `scripts/screen_batch.py --batch
h20260929_01_letf_flow_reversal --iteration h20260929_01_letf_flow_reversal`.

Leveraged-ETF close-rebalancing flow reversal (`dir:letf_close_rebalancing_
flow_reversal`): 2x/3x leveraged and inverse ETFs must rebalance daily near
the close to restore their target leverage ratio; on days with a large
underlying move this creates a predictable, direction-known buy/sell flow
that the literature (Lenkey 2024, AIMSPress Quantitative Finance and
Economics survey, http://www.aimspress.com/article/doi/10.3934/QFE.2024031 --
read in full via WebFetch) associates with next-day mean reversion in the
UNDERLYING (undelevered) index ETF, though the survey's own reading is that
the economic magnitude is small. Mechanism is mechanical (daily leverage-
ratio rebalancing), not a behavioral/calendar effect, so it should not have
decayed the way calendar anomalies have.

Per the 2026-09-29 02:1x UTC coordinator revision to T-20260929-01 (overrides
the queue task's original `plan` field where the two conflict): the reversal
is long-only and can only be conditioned on a DOWN day (a large one-day levered
sell-off triggers rebalancing BUYING of the underlying near the close, which
this project's frozen contract executes at the next session's open) -- an
UP day's rebalancing flow is itself a SELL, which a long-only-cash rule
cannot express as a distinct position. Signal source is the underlying's own
close-to-close return only (dropped the leveraged-product's own return as a
signal source: since a 3x product's daily return is ~3x the underlying's own
return by construction, it is a redundant, not independent, dimension at a
fixed threshold grid).

15 candidates, `CANDIDATES: list[lane.ScreenCandidate]` (imports `screen_lane`,
following `h20260928_18_vix_putw.py`'s single-shared-harness pattern):

  12 primary `LETF_{SPY,QQQ,SMH}_D{2,3}_H{1,3}`
  3  placebo `LETF_{SPY,QQQ,SMH}_RAND` (NOT eligible for any keep tier --
     internal falsification control, see `_make_rand_trigger`)

Rule (primary, `LETF_{TICKER}_D{pct}_H{hold}`): at the close of trading day
`d`, if `close[TICKER].loc[d] / close[TICKER].loc[d-1] - 1 <= -pct/100` (a
close-to-close drop of `pct` percent or worse), buy `TICKER` at the next
session's open, hold for `hold` sessions, then return to cash (SHY, via the
lane's own remainder rule). A new trigger while already holding is IGNORED
(no extend, no stacking) -- decided here, before any result is computed, to
resolve the "retrigger during hold" ambiguity the queue task flagged.
`weights_fn` reads only `close.loc[:asof]` (the harness-supplied close-only
panel), so there is no look-ahead by construction, same convention as every
other `screen_lane` module.

Rule (placebo, `LETF_{TICKER}_RAND`): a deterministic pseudo-random day
(SHA-256 hash of "TICKER|RAND|<date>", uniform draw compared against a fixed
trigger rate) substitutes for the real D2_H1 (`pct=2`, `hold=1`) drop
condition -- same hold length (1 session), same expected trigger frequency,
but the trigger day is NOT conditioned on price at all. The trigger rate is
the fraction of sessions in TICKER's full local daily history (2016-01-04
through the panel's last available date; not restricted to the select/anchor
window, since this is a frequency calibration for an internal control, not
itself a scored candidate) with a close-to-close return <= -2%, computed once
by `_d2_h1_trigger_rate` and cached. If a real LETF_{TICKER}_D2_H1 candidate
otherwise clears K1/K2/watch_recent but its own RAND placebo's anchor-window
Sharpe is >= its anchor-window Sharpe, the primary candidate is demoted to
"not kept (placebo replication)" -- see `candidate-manifest.json`'s
`keep_rule`. Placebo candidates themselves are never keep-eligible.
"""

from __future__ import annotations

import hashlib
import sys
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import screen_lane as lane  # noqa: E402

DAILY_GLOB = "data/sip/daily/*/*.parquet"

TICKERS: tuple[str, ...] = ("SPY", "QQQ", "SMH")
THRESHOLDS_PCT: tuple[int, ...] = (2, 3)
HOLDS: tuple[int, ...] = (1, 3)
RAND_THRESHOLD_PCT = 2  # matches D2_H1's trigger condition, per the module docstring

_CLOSE_CACHE: dict[str, pd.Series] = {}
_RAND_RATE_CACHE: dict[str, float] = {}


def _load_full_close(symbol: str) -> pd.Series:
    """Lazily load `symbol`'s full local daily close history (2016-01-04
    onward), used only to calibrate the RAND placebo's trigger rate --
    NOT used by the primary candidates, which read only the harness's own
    `close.loc[:asof]` argument. Cached after first call; importing this
    module never reads market data (only calling a RAND weights_fn does),
    so unit tests never hit real data unless they choose to."""
    if symbol not in _CLOSE_CACHE:
        import duckdb

        con = duckdb.connect()
        con.execute("SET memory_limit='512MB'")
        con.execute("SET threads=1")
        frame = con.execute(
            f"""
            SELECT timestamp::DATE AS d, close, volume, trade_count
            FROM read_parquet('{DAILY_GLOB}')
            WHERE symbol = '{symbol}'
            ORDER BY d
            """
        ).df()
        con.close()
        ghost = (frame["volume"].fillna(0) <= 0) & (frame["trade_count"].fillna(0) <= 0)
        frame = frame.loc[~ghost]
        frame["d"] = pd.to_datetime(frame["d"])
        series = frame.set_index("d")["close"].sort_index()
        _CLOSE_CACHE[symbol] = series
    return _CLOSE_CACHE[symbol]


def _d2_h1_trigger_rate(symbol: str) -> float:
    """Fraction of sessions in `symbol`'s full local daily history with a
    close-to-close return <= -2% (the D2_H1 condition) -- the RAND placebo's
    calibrated trigger frequency. Computed once, cached."""
    if symbol not in _RAND_RATE_CACHE:
        close = _load_full_close(symbol)
        ret = close.pct_change().dropna()
        rate = float((ret <= -RAND_THRESHOLD_PCT / 100.0).mean()) if len(ret) else 0.0
        _RAND_RATE_CACHE[symbol] = rate
    return _RAND_RATE_CACHE[symbol]


def _make_event_hold_weights_fn(
    symbol: str,
    entry_fn: Callable[[pd.DataFrame, pd.Timestamp], bool],
    *,
    fixed_hold: int,
) -> Callable[[pd.DataFrame, pd.Timestamp], dict[str, float]]:
    """Stateful `weights_fn`: on a trigger day, hold `symbol` for exactly
    `fixed_hold` sessions (the session immediately after the trigger day
    through `fixed_hold` sessions later), cash otherwise. A trigger seen
    while already holding is ignored (no extend, no stacking).

    Relies on the harness (`screen_lane.weights_frame`) calling `weights_fn`
    once per trading day in strictly increasing `asof` order for any single
    sweep, and re-starting a fresh sweep from `close.index[0]` for each of
    the (up to three) independent passes `screen_lane.evaluate_candidate`
    makes per candidate (`first_valid_signal_date`, then one
    `candidate_returns_for_offset` call per cost level). A non-increasing
    `asof` (a new sweep beginning) resets the internal hold state -- this
    is the only signal available to detect a new sweep, since `weights_fn`'s
    signature carries no explicit reset hook.
    """
    state = {"last_pos": None, "remaining": 0}

    def fn(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
        index = close.index
        try:
            pos = int(index.get_loc(asof))
        except KeyError:
            return {}
        if state["last_pos"] is not None and pos <= state["last_pos"]:
            state["remaining"] = 0
        state["last_pos"] = pos
        if symbol not in close.columns:
            return {}
        if state["remaining"] > 0:
            state["remaining"] -= 1
            return {symbol: 1.0}
        if bool(entry_fn(close, asof)):
            state["remaining"] = fixed_hold - 1
            return {symbol: 1.0}
        return {}

    return fn


def _make_letf_trigger(
    symbol: str, threshold_pct: int
) -> Callable[[pd.DataFrame, pd.Timestamp], bool]:
    """True iff `symbol`'s close-to-close return at `asof` is <=
    `-threshold_pct/100`. Reads only `close.loc[:asof]` -- no look-ahead."""
    threshold = threshold_pct / 100.0

    def fn(close: pd.DataFrame, asof: pd.Timestamp) -> bool:
        if symbol not in close.columns:
            return False
        hist = close[symbol].loc[:asof]
        if len(hist) < 2:
            return False
        prev, cur = hist.iloc[-2], hist.iloc[-1]
        if not (np.isfinite(prev) and np.isfinite(cur)) or prev == 0:
            return False
        return (cur / prev - 1.0) <= -threshold

    return fn


def _make_rand_trigger(symbol: str) -> Callable[[pd.DataFrame, pd.Timestamp], bool]:
    """Deterministic pseudo-random trigger: a SHA-256 hash of the ticker and
    calendar date, compared against `_d2_h1_trigger_rate(symbol)`. Never
    reads a price at call time (only the calibration rate, computed once
    from the FULL local history -- documented in the module docstring as a
    placebo-calibration constant, not a scored quantity)."""

    def fn(close: pd.DataFrame, asof: pd.Timestamp) -> bool:
        if symbol not in close.columns:
            return False
        rate = _d2_h1_trigger_rate(symbol)
        digest = hashlib.sha256(f"{symbol}|RAND|{asof.date().isoformat()}".encode()).hexdigest()
        draw = int(digest[:16], 16) / float(16**16)
        return draw < rate

    return fn


CANDIDATES: list[lane.ScreenCandidate] = []

for _sym in TICKERS:
    for _pct in THRESHOLDS_PCT:
        for _hold in HOLDS:
            CANDIDATES.append(
                lane.ScreenCandidate(
                    id=f"LETF_{_sym}_D{_pct}_H{_hold}",
                    name=(
                        f"LETF close-rebalancing flow reversal: {_sym} down "
                        f"{_pct}%+ at close -> next-open buy, hold {_hold}d"
                    ),
                    source_card="lenkey_2024_aimspress_letf_rebalancing_survey",
                    universe=(_sym,),
                    freq="D",
                    weights_fn=_make_event_hold_weights_fn(
                        _sym, _make_letf_trigger(_sym, _pct), fixed_hold=_hold
                    ),
                )
            )

for _sym in TICKERS:
    CANDIDATES.append(
        lane.ScreenCandidate(
            id=f"LETF_{_sym}_RAND",
            name=f"Placebo: {_sym} pseudo-random-day entry (D2_H1 trigger rate), hold 1d",
            source_card="letf_flow_reversal_internal_placebo_random_day",
            universe=(_sym,),
            freq="D",
            weights_fn=_make_event_hold_weights_fn(_sym, _make_rand_trigger(_sym), fixed_hold=1),
        )
    )

assert len(CANDIDATES) == 15, f"expected 15 candidates, got {len(CANDIDATES)}"
assert len({c.id for c in CANDIDATES}) == 15, "duplicate candidate ids"
