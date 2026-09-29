"""T-20260929-01 batch (part B): `scripts/screen_batch.py --batch
h20260929_01_dip_rejudge --iteration h20260929_01_dip_rejudge`.

Re-judges the 6 published ETF dip-reversion rules from
`reports/research/iterations/h20260924_01_etf_dip_reversion/` (H-20260924-01;
registry `dir:etf_dip_reversion_ibs_connors`, refuted 2026-09-24) under THIS
project's frozen batch-screening contract (`scripts/screen_lane.py`): 10bp/
20bp per side, close signal -> next session's open fill, K1/K2 keep tiers
against the S3 incumbent, judged across the 2024-01-08..2026-09-17 anchor
and 2016-05-02..2023-09-15 stress windows. This differs from H-20260924-01 in
three ways (see `direction-review.json` for the full comparison): (1) this
round's fill convention is next-open on BOTH entry and exit, identical in
substance to H-20260924-01's own "T2" timing (H-20260924-01 additionally
computed an unexecutable same-close "T0" upper bound and a minute-bar-proxy
"T1", neither of which this round repeats); (2) the keep bar is K1/K2 against
a vol-matched S3 control, not the old giants-sweep G1-G5 CAGR/Sharpe/placebo
gates; (3) this round adds the frozen stress window (2016-2023), which
H-20260924-01 never tested (its own WARMUP_START was 2022-06-01).

Six rules (D1-D6, formulas copied verbatim from `scripts/run_h20260924_01_
etf_dip_reversion.py`'s `_d{1..6}_entry/_exit` -- that module is imported
directly for `ibs`/`ema`/`sma`/the Wilder RSI(2) helpers, not re-derived) x
two 1x signal/execution tickers (SPY, QQQ) = 12 candidates, `DIP_{rule}_
{TICKER}`. 3x execution (TQQQ/UPRO) is NOT re-tested here -- the queue task's
02:1x revision scopes this batch to "SPY, QQQ 1x" only.

One implementation difference from `run_h20260924_01_etf_dip_reversion.py`'s
own trade simulator, documented here rather than silently: that script DROPS
an unbounded-hold (D3/D4/D5/D6, no `max_hold`) trade that never finds an exit
signal before the data window ends ("the position never closes within the
data window; drop it"). This module's daily-weights representation has no
retroactive trade removal mechanism -- such a trade is simply still open
(marked-to-market) at the end of its window instead of dropped. This is a
minor, conservative-to-neutral deviation (it does not erase a real trade),
expected to be immaterial for SPY/QQQ given RSI(2)/EMA5-crossing exit
conditions fire frequently in practice.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import run_h20260924_01_etf_dip_reversion as dip  # noqa: E402
import screen_lane as lane  # noqa: E402

DAILY_GLOB = "data/sip/daily/*/*.parquet"

TICKERS: tuple[str, ...] = ("SPY", "QQQ")
RULES: tuple[str, ...] = ("D1", "D2", "D3", "D4", "D5", "D6")

_OHLC_CACHE: dict[str, pd.DataFrame] = {}


def _load_ohlc(symbol: str) -> pd.DataFrame:
    """Lazily load `symbol`'s full local daily OHLC history. `screen_lane`'s
    own harness-supplied `close` panel is close/open only -- IBS (D1/D2/D6)
    and the 3-day high/low pattern (D5) need high/low too, so this module
    loads its own small OHLC panel for SPY/QQQ, independent of and read-only
    alongside the harness's own close/open load. Cached after first call;
    importing this module (or constructing `CANDIDATES`) never reads market
    data -- only the first actual `weights_fn` call for a given symbol does,
    and tests inject synthetic frames directly into `_OHLC_CACHE` instead."""
    if symbol not in _OHLC_CACHE:
        import duckdb

        con = duckdb.connect()
        con.execute("SET memory_limit='512MB'")
        con.execute("SET threads=1")
        frame = con.execute(
            f"""
            SELECT timestamp::DATE AS d, open, high, low, close, volume, trade_count
            FROM read_parquet('{DAILY_GLOB}')
            WHERE symbol = '{symbol}'
            ORDER BY d
            """
        ).df()
        con.close()
        ghost = (frame["volume"].fillna(0) <= 0) & (frame["trade_count"].fillna(0) <= 0)
        frame = frame.loc[~ghost].drop(columns=["volume", "trade_count"])
        frame["d"] = pd.to_datetime(frame["d"])
        frame = frame.set_index("d").sort_index()
        _OHLC_CACHE[symbol] = frame
    return _OHLC_CACHE[symbol]


class _DipIndicators:
    __slots__ = (
        "close",
        "high",
        "low",
        "ibs",
        "ema220",
        "ema200",
        "ema5",
        "sma200",
        "sma5",
        "rsi2",
    )


_DIP_IND_CACHE: dict[str, _DipIndicators] = {}


def _dip_indicators(symbol: str) -> _DipIndicators:
    """Every series a D1-D6 rule needs, built once (vectorized, causal --
    `ema`/`sma`/Wilder-RSI are all one-sided rolling computations) from
    `_load_ohlc(symbol)` and cached. Identical formulas to `run_h20260924_01_
    etf_dip_reversion.py`'s `build_bundle` at its "T0"/"T2" (official-price)
    timing -- this module never builds the T1 minute-bar proxy path."""
    if symbol not in _DIP_IND_CACHE:
        ohlc = _load_ohlc(symbol)
        close, high, low = ohlc["close"], ohlc["high"], ohlc["low"]
        ind = _DipIndicators()
        ind.close = close
        ind.high = high
        ind.low = low
        ind.ibs = dip.ibs(high, low, close)
        ind.ema220 = dip.ema(close, 220)
        ind.ema200 = dip.ema(close, 200)
        ind.ema5 = dip.ema(close, 5)
        ind.sma200 = dip.sma(close, 200)
        ind.sma5 = dip.sma(close, 5)
        gain, loss = dip._wilder_rsi_state(close, 2)  # noqa: SLF001 -- reuse, not re-derive
        ind.rsi2 = dip._wilder_rsi_from_state(gain, loss)  # noqa: SLF001
        _DIP_IND_CACHE[symbol] = ind
    return _DIP_IND_CACHE[symbol]


def _dip_signals(
    symbol: str, rule: str
) -> tuple[pd.Series, pd.Series | None, int | None, int | None]:
    """(entry_series, exit_series_or_None, max_hold, fixed_hold) -- full-
    history boolean series, one boolean per trading day, built once per
    (symbol, rule). Formulas copied verbatim from `run_h20260924_01_etf_dip_
    reversion.py`'s `_d{1..6}_entry`/`_d{1..6}_exit`."""
    ind = _dip_indicators(symbol)
    close, high, low = ind.close, ind.high, ind.low
    ibs_s = ind.ibs
    rsi2 = ind.rsi2

    if rule == "D1":
        threshold = 0.09 if symbol == "QQQ" else 0.11
        exit_threshold = 0.985 if symbol == "QQQ" else 0.995
        trend = ind.ema220 if symbol == "QQQ" else ind.ema200
        entry = (ibs_s <= threshold) & (close > trend)
        exit_ = ibs_s >= exit_threshold
        return entry.fillna(False), exit_.fillna(False), 14, None
    if rule == "D2":
        entry = ibs_s < 0.20
        return entry.fillna(False), None, None, 1
    if rule == "D3":
        r1, r2, r3 = rsi2.shift(1), rsi2.shift(2), rsi2.shift(3)
        falling = (rsi2 < r1) & (r1 < r2) & (r2 < r3)
        entry = (close > ind.ema200) & falling & (r3 < 60) & (rsi2 < 10)
        prior = rsi2.shift(1)
        exit_ = (rsi2 > 70) & (prior <= 70)
        return entry.fillna(False), exit_.fillna(False), None, None
    if rule == "D4":
        entry = (close > ind.sma200) & (rsi2 <= 5)
        exit_ = close > ind.sma5
        return entry.fillna(False), exit_.fillna(False), None, None
    if rule == "D5":
        h1, h2, h3 = high.shift(1), high.shift(2), high.shift(3)
        l1, l2, l3 = low.shift(1), low.shift(2), low.shift(3)
        lower_highs = (high < h1) & (h1 < h2) & (h2 < h3)
        lower_lows = (low < l1) & (l1 < l2) & (l2 < l3)
        entry = (close > ind.ema200) & (close < ind.ema5) & lower_highs & lower_lows
        prior_close = close.shift(1)
        prior_ema5 = ind.ema5.shift(1)
        exit_ = (close > ind.ema5) & (prior_close <= prior_ema5)
        return entry.fillna(False), exit_.fillna(False), None, None
    if rule == "D6":
        entry_d4 = (close > ind.sma200) & (rsi2 <= 5)
        entry = entry_d4 & (ibs_s < 0.20)
        exit_ = close > ind.sma5
        return entry.fillna(False), exit_.fillna(False), None, None
    raise ValueError(f"unknown rule {rule!r}")


def _make_dip_weights_fn(symbol: str, rule: str):
    """Stateful `weights_fn`: entry/exit are decided from the precomputed
    boolean series above; hold semantics (retrigger-while-active is ignored,
    no stacking/extension) match `run_h20260924_01_etf_dip_reversion.py`'s
    own `simulate_rule` loop (which jumps past a trade's exit index before
    scanning for the next entry, i.e. never re-checks entries mid-trade).
    Resets on a non-increasing `asof`, same convention as
    `h20260929_01_letf_flow_reversal.py`'s `_make_event_hold_weights_fn`."""
    entry_series, exit_series, max_hold, fixed_hold = _dip_signals(symbol, rule)
    state = {"last_pos": None, "active": False, "entry_pos": None}

    def fn(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
        index = close.index
        try:
            pos = int(index.get_loc(asof))
        except KeyError:
            return {}
        if state["last_pos"] is not None and pos <= state["last_pos"]:
            state["active"] = False
            state["entry_pos"] = None
        state["last_pos"] = pos
        if symbol not in close.columns:
            return {}

        if state["active"]:
            hold = pos - state["entry_pos"]
            exit_now = False
            if fixed_hold is not None:
                exit_now = hold >= fixed_hold
            else:
                exited = bool(exit_series.get(asof, False)) if exit_series is not None else False
                if exited:
                    exit_now = True
                elif max_hold is not None and hold >= max_hold:
                    exit_now = True
            if exit_now:
                state["active"] = False
                state["entry_pos"] = None
                return {}
            return {symbol: 1.0}

        if bool(entry_series.get(asof, False)):
            state["active"] = True
            state["entry_pos"] = pos
            return {symbol: 1.0}
        return {}

    return fn


_SOURCE_CARD_BY_RULE = {
    "D1": "pagonidis_ibs_algotradekit_ema_trend_filter",
    "D2": "pagonidis_ibs_raw_no_trend_filter",
    "D3": "connors_alvarez_rsi2_falling_streak",
    "D4": "connors_alvarez_turtle_rsi2_sma200",
    "D5": "three_day_high_low_pattern",
    "D6": "connors_rsi2_sma200_plus_ibs_combo",
}

CANDIDATES: list[lane.ScreenCandidate] = []

for _rule in RULES:
    for _sym in TICKERS:
        CANDIDATES.append(
            lane.ScreenCandidate(
                id=f"DIP_{_rule}_{_sym}",
                name=f"Dip reversion {_rule} on {_sym} (1x), next-open fill re-judge",
                source_card=_SOURCE_CARD_BY_RULE[_rule],
                universe=(_sym,),
                freq="D",
                weights_fn=_make_dip_weights_fn(_sym, _rule),
            )
        )

assert len(CANDIDATES) == 12, f"expected 12 candidates, got {len(CANDIDATES)}"
assert len({c.id for c in CANDIDATES}) == 12, "duplicate candidate ids"
