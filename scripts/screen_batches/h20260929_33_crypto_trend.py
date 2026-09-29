"""T-20260929-33 batch: `scripts/screen_batch.py --batch h20260929_33_crypto_trend
--iteration h20260929_33_crypto_trend`.

Published crypto trend/momentum rules (Alpaca spot, long-only), testing
whether dir:crypto_trend_btc (Zarattini/Pagani/Barbon 2025, SSRN 5209907) or
dir:crypto_xs_momentum (a long-only reinterpretation of Liu/Tsyvinski/Wu
2022) clear the K1/K2/watch_recent keep rule. See
`reports/research/iterations/h20260929_33_crypto_trend/direction-review.json`
for the reopening rationale and
`reports/research/iterations/h20260929_33_crypto_trend/candidate-manifest.json`
for every candidate's preregistered parameters.

Crypto prices are supplied via `extend_panel` (`screen_lane.apply_panel_extension`)
from `data/research/crypto/session_prices.parquet`, built by
`scripts/fetch_crypto_session_prices.py` (Binance public monthly klines +
Coinbase Exchange public candles, both keyless) -- session-aligned to the US
equity calendar (09:30/16:00 America/New_York), no forward fill.

13 candidates (`CANDIDATES: list[lane.ScreenCandidate]`):

  BTC_BUYHOLD                  -- BTC buy-and-hold (benchmark / K2 candidate)
  BTC_SMA200                   -- BTC above its own 138-session SMA (200
                                   calendar days x252/365) else SHY
  BTC_TSMOM_1M/3M/6M           -- BTC time-series momentum, 21/62/124-session
                                   lookback (1/3/6 calendar months x252/365),
                                   monthly rebalance
  BTC_DONCHIAN_ENSEMBLE        -- fraction of a 9-window Donchian-breakout
                                   ensemble in the "up" state (self-constructed
                                   window ladder -- SSRN 5209907's own exact
                                   windows are unrecoverable, 403-blocked; see
                                   direction-review.json remaining_evidence_gap)
  BTC_DONCHIAN_ENSEMBLE_VT40   -- same, scaled to a 40% annualized vol target
                                   (21-session realized vol)
  CRYPTO_DONCHIAN_TOP3         -- same Donchian ensemble, ranked across all 10
                                   coins, equal-weight top 3 with a positive
                                   score, else SHY, monthly
  BTC_ETH_DUAL_MOM             -- relative (BTC vs ETH, 62-session) + absolute
                                   momentum dual filter, monthly
  CRYPTO_XS_TOP3_EW            -- cross-sectional 63-session momentum, top 3
                                   of 10 coins with positive momentum, equal
                                   weight, else SHY, monthly
  CRYPTO_XS_TOP3_IVOL          -- same selection, inverse-21-session-vol
                                   weighted
  CRYPTO_XS_TOP3_EW_VT40       -- CRYPTO_XS_TOP3_EW scaled to a 40% annualized
                                   vol target (21-session realized vol of the
                                   unscaled book)
  BTC_RAND_PLACEBO             -- deterministic PRNG (seed 20260929) holds
                                   BTCUSD on a random subset of sessions,
                                   frequency-matched to BTC_SMA200's own
                                   live-fraction; internal falsification
                                   control only, never keep-eligible

Every weights_fn reads only `close.loc[:asof]` (directly, or via a
vectorized rolling/shift(1) precomputation over the whole panel -- which by
construction depends only on rows at or before each row's own date, so it is
equivalent to a fresh `close.loc[:asof]` recomputation at every asof and
carries no look-ahead) -- no future rows are ever read.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import screen_lane as lane  # noqa: E402

SESSION_PRICES_PATH = ROOT / "data" / "research" / "crypto" / "session_prices.parquet"

BTC = "BTCUSD"
ETH = "ETHUSD"
CRYPTO_SYMS: tuple[str, ...] = (
    "BTCUSD",
    "ETHUSD",
    "LTCUSD",
    "BCHUSD",
    "LINKUSD",
    "DOGEUSD",
    "AVAXUSD",
    "UNIUSD",
    "AAVEUSD",
    "DOTUSD",
)

SMA200_SESSIONS = 138  # 200 calendar days * 252/365, rounded
TSMOM_1M_SESSIONS = 21  # 30cd * 252/365
TSMOM_3M_SESSIONS = 62  # 90cd * 252/365
TSMOM_6M_SESSIONS = 124  # 180cd * 252/365
DONCHIAN_WINDOWS: tuple[int, ...] = (7, 14, 21, 31, 45, 66, 97, 138, 200)
XS_LOOKBACK_SESSIONS = 63
VOL_WINDOW_SESSIONS = 21
VOL_TARGET_ANNUAL = 0.40
TOP_N = 3

# ---------------------------------------------------------------------------
# Panel extension
# ---------------------------------------------------------------------------

_CRYPTO_PANEL_CACHE: tuple[pd.DataFrame, pd.DataFrame] | None = None


def _load_crypto_panel() -> tuple[pd.DataFrame, pd.DataFrame]:
    global _CRYPTO_PANEL_CACHE
    if _CRYPTO_PANEL_CACHE is None:
        frame = pd.read_parquet(SESSION_PRICES_PATH)
        close_wide = frame.pivot(index="date", columns="symbol", values="close").sort_index()
        open_wide = frame.pivot(index="date", columns="symbol", values="open").sort_index()
        close_wide.index = pd.to_datetime(close_wide.index)
        open_wide.index = pd.to_datetime(open_wide.index)
        _CRYPTO_PANEL_CACHE = (close_wide, open_wide)
    return _CRYPTO_PANEL_CACHE


def extend_panel(close: pd.DataFrame, open_: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    del close, open_  # the crypto panel does not depend on the equity panel
    return _load_crypto_panel()


# ---------------------------------------------------------------------------
# Cached, causal (shift(1)/rolling-only) signal precomputation. Every series
# below at row `t` depends only on rows <= t of its input -- reading it via
# `.loc[asof]` is exactly equivalent to recomputing on `close.loc[:asof]`
# fresh at every asof.
# ---------------------------------------------------------------------------

_SMA_CACHE: dict[tuple[int, str, int], pd.Series] = {}
_TSMOM_CACHE: dict[tuple[int, str, int], pd.Series] = {}
_DONCHIAN_FRAC_CACHE: dict[tuple[int, str], pd.Series] = {}
_XS_MOM_CACHE: dict[int, pd.DataFrame] = {}
_VOL_CACHE: dict[tuple[int, str], pd.Series] = {}


def _sma_above(close: pd.DataFrame, sym: str, window: int) -> pd.Series:
    key = (id(close), sym, window)
    if key not in _SMA_CACHE:
        price = close[sym]
        sma = price.rolling(window, min_periods=window).mean()
        _SMA_CACHE[key] = (price > sma).where(sma.notna())
    return _SMA_CACHE[key]


def _tsmom_positive(close: pd.DataFrame, sym: str, lookback: int) -> pd.Series:
    key = (id(close), sym, lookback)
    if key not in _TSMOM_CACHE:
        price = close[sym]
        ret = price / price.shift(lookback) - 1.0
        _TSMOM_CACHE[key] = (ret > 0).where(ret.notna())
    return _TSMOM_CACHE[key]


def _donchian_fraction(close: pd.DataFrame, sym: str) -> pd.Series:
    """Fraction of `DONCHIAN_WINDOWS` channels in breakout-up state: price
    strictly above the highest close of the trailing `w` sessions *before*
    today (shift(1), so today's own price never enters its own channel)."""
    key = (id(close), sym)
    if key not in _DONCHIAN_FRAC_CACHE:
        price = close[sym]
        states = []
        for w in DONCHIAN_WINDOWS:
            prior_max = price.shift(1).rolling(w, min_periods=w).max()
            states.append((price > prior_max).astype(float))
        frac = sum(states) / len(states)
        max_w = max(DONCHIAN_WINDOWS)
        warmup = price.shift(1).rolling(max_w, min_periods=max_w).max().isna()
        _DONCHIAN_FRAC_CACHE[key] = frac.where(~warmup)
    return _DONCHIAN_FRAC_CACHE[key]


def _realized_vol_annualized(close: pd.DataFrame, sym: str, window: int) -> pd.Series:
    key = (id(close), sym)
    if key not in _VOL_CACHE:
        ret = close[sym].pct_change()
        _VOL_CACHE[key] = ret.rolling(window, min_periods=window).std(ddof=1) * np.sqrt(252.0)
    return _VOL_CACHE[key]


def _xs_momentum_table(close: pd.DataFrame) -> pd.DataFrame:
    """`XS_LOOKBACK_SESSIONS`-session return for every symbol in
    `CRYPTO_SYMS`, one column per symbol, NaN before each symbol's own
    warmup."""
    key = id(close)
    if key not in _XS_MOM_CACHE:
        cols = {}
        for sym in CRYPTO_SYMS:
            price = close[sym]
            cols[sym] = price / price.shift(XS_LOOKBACK_SESSIONS) - 1.0
        _XS_MOM_CACHE[key] = pd.DataFrame(cols, index=close.index)
    return _XS_MOM_CACHE[key]


def _price_ok(close: pd.DataFrame, asof: pd.Timestamp, sym: str) -> bool:
    return sym in close.columns and asof in close.index and np.isfinite(close.loc[asof, sym])


def _vt40_scale(close: pd.DataFrame, asof: pd.Timestamp, book_sym: str) -> float:
    """min(1, 0.40 / trailing-21-session realized annualized vol of `book_sym`)."""
    vol_series = _realized_vol_annualized(close, book_sym, VOL_WINDOW_SESSIONS)
    if asof not in vol_series.index:
        return 0.0
    vol = vol_series.loc[asof]
    if not np.isfinite(vol) or vol <= 0:
        return 0.0
    return float(min(1.0, VOL_TARGET_ANNUAL / vol))


# ---------------------------------------------------------------------------
# weights_fn implementations
# ---------------------------------------------------------------------------


def _btc_buyhold(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
    if not _price_ok(close, asof, BTC):
        return {}
    return {BTC: 1.0}


def _btc_sma200(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
    if not _price_ok(close, asof, BTC):
        return {}
    series = _sma_above(close, BTC, SMA200_SESSIONS)
    if asof not in series.index or pd.isna(series.loc[asof]):
        return {}
    return {BTC: 1.0} if bool(series.loc[asof]) else {}


def _make_btc_tsmom(lookback: int):
    def fn(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
        if not _price_ok(close, asof, BTC):
            return {}
        series = _tsmom_positive(close, BTC, lookback)
        if asof not in series.index or pd.isna(series.loc[asof]):
            return {}
        return {BTC: 1.0} if bool(series.loc[asof]) else {}

    return fn


def _btc_donchian_ensemble(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
    if not _price_ok(close, asof, BTC):
        return {}
    frac_series = _donchian_fraction(close, BTC)
    if asof not in frac_series.index or pd.isna(frac_series.loc[asof]):
        return {}
    frac = float(frac_series.loc[asof])
    return {BTC: frac} if frac > 0 else {}


def _btc_donchian_ensemble_vt40(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
    base = _btc_donchian_ensemble(close, asof)
    if not base:
        return {}
    scale = _vt40_scale(close, asof, BTC)
    weight = min(1.0, base[BTC] * scale)
    return {BTC: weight} if weight > 0 else {}


def _crypto_donchian_top3(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
    scores: dict[str, float] = {}
    for sym in CRYPTO_SYMS:
        if not _price_ok(close, asof, sym):
            continue
        series = _donchian_fraction(close, sym)
        if asof not in series.index or pd.isna(series.loc[asof]):
            continue
        val = float(series.loc[asof])
        if val > 0:
            scores[sym] = val
    if not scores:
        return {}
    top = sorted(scores, key=lambda s: scores[s], reverse=True)[:TOP_N]
    weight_each = 1.0 / len(top)
    return {sym: weight_each for sym in top}


def _btc_eth_dual_mom(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
    if not (_price_ok(close, asof, BTC) and _price_ok(close, asof, ETH)):
        return {}
    btc_ret_series = close[BTC] / close[BTC].shift(TSMOM_3M_SESSIONS) - 1.0
    eth_ret_series = close[ETH] / close[ETH].shift(TSMOM_3M_SESSIONS) - 1.0
    if asof not in btc_ret_series.index or asof not in eth_ret_series.index:
        return {}
    btc_ret, eth_ret = btc_ret_series.loc[asof], eth_ret_series.loc[asof]
    if pd.isna(btc_ret) or pd.isna(eth_ret):
        return {}
    winner, winner_ret = (BTC, btc_ret) if btc_ret >= eth_ret else (ETH, eth_ret)
    if winner_ret <= 0:
        return {}
    return {winner: 1.0}


def _xs_top3_selection(close: pd.DataFrame, asof: pd.Timestamp) -> list[str]:
    table = _xs_momentum_table(close)
    if asof not in table.index:
        return []
    row = table.loc[asof]
    valid = {
        sym: float(row[sym])
        for sym in CRYPTO_SYMS
        if _price_ok(close, asof, sym) and pd.notna(row[sym]) and row[sym] > 0
    }
    if not valid:
        return []
    return sorted(valid, key=lambda s: valid[s], reverse=True)[:TOP_N]


def _crypto_xs_top3_ew(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
    top = _xs_top3_selection(close, asof)
    if not top:
        return {}
    weight_each = 1.0 / len(top)
    return {sym: weight_each for sym in top}


def _crypto_xs_top3_ivol(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
    top = _xs_top3_selection(close, asof)
    if not top:
        return {}
    inv_vols: dict[str, float] = {}
    for sym in top:
        vol_series = _realized_vol_annualized(close, sym, VOL_WINDOW_SESSIONS)
        vol = vol_series.loc[asof] if asof in vol_series.index else np.nan
        if pd.isna(vol) or vol <= 0:
            inv_vols[sym] = 0.0
        else:
            inv_vols[sym] = 1.0 / float(vol)
    total = sum(inv_vols.values())
    if total <= 0:
        weight_each = 1.0 / len(top)
        return {sym: weight_each for sym in top}
    return {sym: inv_vols[sym] / total for sym in top}


def _crypto_xs_top3_ew_vt40(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
    base = _crypto_xs_top3_ew(close, asof)
    if not base:
        return {}
    # 21-session realized vol of the equal-weighted book itself.
    top_syms = sorted(base)
    rets = pd.concat([close[s].pct_change() for s in top_syms], axis=1)
    book_ret = rets.mean(axis=1)
    vol_series = book_ret.rolling(VOL_WINDOW_SESSIONS, min_periods=VOL_WINDOW_SESSIONS).std(
        ddof=1
    ) * np.sqrt(252.0)
    vol = vol_series.loc[asof] if asof in vol_series.index else np.nan
    if pd.isna(vol) or vol <= 0:
        return {}
    scale = min(1.0, VOL_TARGET_ANNUAL / float(vol))
    out = {sym: w * scale for sym, w in base.items()}
    return {sym: w for sym, w in out.items() if w > 0}


def _btc_rand_placebo(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
    """Deterministic pseudo-random exposure: seeded solely by the session's
    ordinal date (so it is reproducible and depends only on `asof`, not on
    call order), matched in unconditional rate to BTC_SMA200's own live
    fraction (empirically ~0.55 of sessions once warmed up -- see
    direction-review.json). No information from `close` is used at all
    (other than confirming BTC has a price that day), by design: this is the
    internal falsification control for "does holding BTC roughly half the
    time already look like a trend edge"."""
    if not _price_ok(close, asof, BTC):
        return {}
    ordinal = int(pd.Timestamp(asof).toordinal())
    rng = np.random.default_rng(20260929 + ordinal)
    return {BTC: 1.0} if rng.random() < 0.55 else {}


CANDIDATES: list[lane.ScreenCandidate] = [
    lane.ScreenCandidate(
        id="BTC_BUYHOLD",
        name="BTC buy-and-hold",
        source_card="zarattini_pagani_barbon_2025_crypto_trend",
        universe=(BTC,),
        freq="D",
        weights_fn=_btc_buyhold,
    ),
    lane.ScreenCandidate(
        id="BTC_SMA200",
        name="BTC above 138-session (200cd) SMA else SHY",
        source_card="quantpedia_btc_trend_revisit_2024",
        universe=(BTC,),
        freq="D",
        weights_fn=_btc_sma200,
    ),
    lane.ScreenCandidate(
        id="BTC_TSMOM_1M",
        name="BTC 21-session (1cm) time-series momentum",
        source_card="quantpedia_btc_trend_revisit_2024",
        universe=(BTC,),
        freq="M",
        weights_fn=_make_btc_tsmom(TSMOM_1M_SESSIONS),
    ),
    lane.ScreenCandidate(
        id="BTC_TSMOM_3M",
        name="BTC 62-session (3cm) time-series momentum",
        source_card="quantpedia_btc_trend_revisit_2024",
        universe=(BTC,),
        freq="M",
        weights_fn=_make_btc_tsmom(TSMOM_3M_SESSIONS),
    ),
    lane.ScreenCandidate(
        id="BTC_TSMOM_6M",
        name="BTC 124-session (6cm) time-series momentum",
        source_card="quantpedia_btc_trend_revisit_2024",
        universe=(BTC,),
        freq="M",
        weights_fn=_make_btc_tsmom(TSMOM_6M_SESSIONS),
    ),
    lane.ScreenCandidate(
        id="BTC_DONCHIAN_ENSEMBLE",
        name="BTC 9-window Donchian-breakout ensemble (approx. Zarattini et al.)",
        source_card="zarattini_pagani_barbon_2025_crypto_trend",
        universe=(BTC,),
        freq="D",
        weights_fn=_btc_donchian_ensemble,
    ),
    lane.ScreenCandidate(
        id="BTC_DONCHIAN_ENSEMBLE_VT40",
        name="BTC Donchian ensemble, 40% annualized vol target",
        source_card="zarattini_pagani_barbon_2025_crypto_trend",
        universe=(BTC,),
        freq="D",
        weights_fn=_btc_donchian_ensemble_vt40,
    ),
    lane.ScreenCandidate(
        id="CRYPTO_DONCHIAN_TOP3",
        name="10-coin Donchian-ensemble top-3 rotation",
        source_card="zarattini_pagani_barbon_2025_crypto_trend",
        universe=CRYPTO_SYMS,
        freq="M",
        weights_fn=_crypto_donchian_top3,
    ),
    lane.ScreenCandidate(
        id="BTC_ETH_DUAL_MOM",
        name="BTC+ETH dual momentum (relative + absolute, 62-session)",
        source_card="quantpedia_btc_trend_revisit_2024",
        universe=(BTC, ETH),
        freq="M",
        weights_fn=_btc_eth_dual_mom,
    ),
    lane.ScreenCandidate(
        id="CRYPTO_XS_TOP3_EW",
        name="10-coin cross-sectional 63-session momentum, top-3 equal-weight",
        source_card="alpaca_crypto_supported_coins",
        universe=CRYPTO_SYMS,
        freq="M",
        weights_fn=_crypto_xs_top3_ew,
    ),
    lane.ScreenCandidate(
        id="CRYPTO_XS_TOP3_IVOL",
        name="10-coin cross-sectional 63-session momentum, top-3 inverse-vol",
        source_card="alpaca_crypto_supported_coins",
        universe=CRYPTO_SYMS,
        freq="M",
        weights_fn=_crypto_xs_top3_ivol,
    ),
    lane.ScreenCandidate(
        id="CRYPTO_XS_TOP3_EW_VT40",
        name="10-coin cross-sectional top-3 equal-weight, 40% vol target",
        source_card="alpaca_crypto_supported_coins",
        universe=CRYPTO_SYMS,
        freq="M",
        weights_fn=_crypto_xs_top3_ew_vt40,
    ),
    lane.ScreenCandidate(
        id="BTC_RAND_PLACEBO",
        name="Deterministic random BTC timing (internal falsification control)",
        source_card="zarattini_pagani_barbon_2025_crypto_trend",
        universe=(BTC,),
        freq="D",
        weights_fn=_btc_rand_placebo,
    ),
]
