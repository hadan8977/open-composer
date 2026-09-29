"""T-20260929-34 batch: `scripts/screen_batch.py --batch h20260929_34_levered_single_stock
--iteration h20260929_34_levered_single_stock`.

Individual-stock version of S3 (us_etf_levered_rotation_63_top2_monthly,
scripts/run_h20260922_05_salvage.py): 63-session momentum ranking within a
point-in-time megacap-by-liquidity menu (top 20 or top 50 S&P 500
constituents by trailing 63-session median dollar volume,
`reports/research/iterations/h20260929_34_levered_single_stock/menu.parquet`,
built by `scripts/build_h20260929_34_menu.py`), absolute-momentum filter
(momentum_63 <= 0 excluded, no backfill -- the slot's weight falls through to
the harness's own SHY remainder), top-k equal weight, optionally expressed on
a synthetic daily-reset 2x series (`L2_<SYM>`, built by this module's
`extend_panel` hook), with a vt40 (40% target) volatility overlay.

14 candidates (`CANDIDATES: list[lane.ScreenCandidate]`, `freq="M"`):

  12  LSS_N{20,50}_K{1,2,3}_{1X,2X}   -- the full grid: menu size x
                                          concentration x leverage
  1   LSS_N20_EW_2X                   -- equal-weight, no momentum ranking,
                                          top-20 menu, 2x, vt40 (external
                                          "no stock-picking" control)
  1   LSS_RAND_K2_2X                  -- deterministic random 2-of-top-20
                                          pick (seed 20260929), 2x, vt40
                                          (internal falsification placebo)

`LSS_N20_EW_2X` and `LSS_RAND_K2_2X` are never eligible for a keep tier;
see candidate-manifest.json's `eligible_for_keep_tiers` and keep_rule.

vt40 is a **single-pass proxy**, not `salvage.vol_scale`'s two-pass exact
simulated-book calculation: `screen_lane.ScreenCandidate.weights_fn` receives
only `close` (not `open_`), so the harness cannot re-simulate the actual
executed book inside the signal function. This module instead computes, at
each rebalance date, the trailing 21-session realized volatility of what the
CURRENT month's picks would have returned over the past 21 sessions (using
only `close.loc[:asof]`, so no look-ahead), and scales down (never up,
capped at 1.0x) if that exceeds the 40% target -- documented as a
preregistered simplification in direction-review.json and cost-contract.json,
not a post-hoc choice.

Every `weights_fn` reads only `close.loc[:asof]` plus the module-level
`menu.parquet` table (itself built with no look-ahead -- see
`scripts/build_h20260929_34_menu.py`'s docstring) -- no look-ahead by
construction, same convention as every other screen_lane batch module.
"""

from __future__ import annotations

import bisect
import sys
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import screen_lane as lane  # noqa: E402

MENU_PATH = ROOT / "reports/research/iterations/h20260929_34_levered_single_stock/menu.parquet"

BIL = "BIL"
SHY = "SHY"
FIN_D = 0.025 / 252.0  # brief's fixed 2.5%/year financing spread
VT40_TARGET = 0.40
VT40_WINDOW = 21
MOMENTUM_LOOKBACK = 63
RAND_SEED = 20260929

# --- point-in-time menu (built offline by scripts/build_h20260929_34_menu.py) ---

_MENU_DF = pd.read_parquet(MENU_PATH)
_MENU_DF["month_end"] = pd.to_datetime(_MENU_DF["month_end"])
MENU_SYMBOLS: tuple[str, ...] = tuple(sorted(_MENU_DF["symbol"].unique()))
L2_SYMBOLS: tuple[str, ...] = tuple(f"L2_{s}" for s in MENU_SYMBOLS)
UNIVERSE: tuple[str, ...] = tuple(sorted({*MENU_SYMBOLS, *L2_SYMBOLS}))

_MENU_MONTH_ENDS: list[pd.Timestamp] = sorted(_MENU_DF["month_end"].unique())
_MENU_BY_MONTH: dict[pd.Timestamp, dict[int, list[str]]] = {}
for _me, _grp in _MENU_DF.groupby("month_end"):
    _ranked = list(_grp.sort_values("rank")["symbol"])
    _MENU_BY_MONTH[_me] = {20: _ranked[:20], 50: _ranked[:50]}


def menu_for_asof(asof: pd.Timestamp, top_n: int) -> list[str]:
    """Top-`top_n` menu symbols for the most recent menu month-end <= asof.

    No look-ahead: `_MENU_MONTH_ENDS` are the month-end dates the menu was
    itself computed as of (trailing-window, no future data); using the
    largest one <= asof means an offset-shifted signal date within the same
    calendar month (screen_lane's 21 monthly offsets) always sees the same
    menu a real month-end rebalance would have seen, never next month's.
    """
    idx = bisect.bisect_right(_MENU_MONTH_ENDS, asof) - 1
    if idx < 0:
        return []
    return _MENU_BY_MONTH[_MENU_MONTH_ENDS[idx]][top_n]


# --- synthetic 2x daily-reset series + delisted-symbol panel extension -----


def _load_delisted(symbols: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Close/open for `symbols` from the delisted-since-2016 archive only,
    with the same ghost-bar hygiene filter `run_h20260918_05_recent_menu.
    load_panel` applies. Returns empty frames if `symbols` is empty."""
    if not symbols:
        empty = pd.DataFrame()
        return empty, empty
    import duckdb

    con = duckdb.connect()
    con.execute("SET memory_limit='600MB'")
    con.execute("SET threads=2")
    in_list = ",".join(f"'{s}'" for s in symbols)
    frame = con.execute(
        f"""
        SELECT symbol, timestamp::DATE AS d, open, close, volume, trade_count
        FROM read_parquet('data/sip-delisted/daily/*.parquet')
        WHERE symbol IN ({in_list})
        ORDER BY symbol, d
        """
    ).df()
    con.close()
    if frame.empty:
        empty = pd.DataFrame()
        return empty, empty
    ghost = (frame["volume"].fillna(0) <= 0) & (frame["trade_count"].fillna(0) <= 0)
    frame = frame.loc[~ghost]
    close = frame.pivot(index="d", columns="symbol", values="close").sort_index()
    open_ = frame.pivot(index="d", columns="symbol", values="open").sort_index()
    close.index = pd.to_datetime(close.index)
    open_.index = pd.to_datetime(open_.index)
    return close, open_


def _synthetic_l2(
    under_close: pd.DataFrame, under_open: pd.DataFrame, rf_d: pd.Series
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """L2_<SYM> daily-reset 2x series for every column of `under_close`/
    `under_open` (both already aligned onto the same DatetimeIndex).

    close_L(t) = close_L(t-1) * (1 + 2*r_cc(t) - rf_d(t) - fin_d)
    open_L(t)  = close_L(t-1) * (1 + 2*(open(t)/close(t-1) - 1))

    close_L is seeded at the underlying's own first valid close (base level
    is arbitrary -- only returns matter downstream); NaN before that date,
    matching the brief's "no fill" instruction. Vectorized via cumprod per
    column (path-dependent, but the per-column recursion has a closed form
    once the daily multiplicative factor is known).
    """
    index = under_close.index
    l2_close = pd.DataFrame(np.nan, index=index, columns=under_close.columns)
    l2_open = pd.DataFrame(np.nan, index=index, columns=under_close.columns)
    rf = rf_d.reindex(index).fillna(0.0)
    for sym in under_close.columns:
        px = under_close[sym]
        first = px.first_valid_index()
        if first is None:
            continue
        pos = index.get_loc(first)
        r_cc = px.pct_change(fill_method=None)
        factor = (1.0 + 2.0 * r_cc - rf - FIN_D).fillna(1.0)
        tail_factor = factor.iloc[pos + 1 :]
        cum = tail_factor.cumprod()
        vals = pd.Series(np.nan, index=index)
        vals.iloc[pos] = px.iloc[pos]
        if len(cum) > 0:
            vals.iloc[pos + 1 :] = float(px.iloc[pos]) * cum.to_numpy()
        l2_close[sym] = vals
        prev_close = under_close[sym].shift(1)
        open_leg = 2.0 * (under_open[sym] / prev_close - 1.0)
        l2_open[sym] = l2_close[sym].shift(1) * (1.0 + open_leg)
    l2_close.columns = [f"L2_{c}" for c in l2_close.columns]
    l2_open.columns = [f"L2_{c}" for c in l2_open.columns]
    return l2_close, l2_open


def extend_panel(close: pd.DataFrame, open_: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Adds: (a) real-symbol columns for menu symbols delisted since 2016
    (missing from the currently-listed sip/daily panel `close` already
    loaded), and (b) L2_<SYM> synthetic 2x series for every menu symbol
    (real or delisted). See module docstring and cost-contract.json."""
    missing_real = [s for s in MENU_SYMBOLS if s not in close.columns]
    delisted_close, delisted_open = _load_delisted(missing_real)

    under_close = close.reindex(columns=list(MENU_SYMBOLS))
    under_open = open_.reindex(columns=list(MENU_SYMBOLS))
    if missing_real:
        dc = delisted_close.reindex(close.index)
        do = delisted_open.reindex(open_.index)
        for s in missing_real:
            if s in dc.columns:
                under_close[s] = dc[s]
            if s in do.columns:
                under_open[s] = do[s]

    if BIL not in close.columns:
        raise ValueError("extend_panel: BIL must already be in the base panel")
    rf_d = (close[BIL] / close[BIL].shift(1) - 1.0).fillna(0.0)

    l2_close, l2_open = _synthetic_l2(under_close, under_open, rf_d)

    extra_close_parts = [l2_close]
    extra_open_parts = [l2_open]
    if missing_real:
        extra_close_parts.insert(0, under_close[missing_real])
        extra_open_parts.insert(0, under_open[missing_real])
    extra_close = pd.concat(extra_close_parts, axis=1)
    extra_open = pd.concat(extra_open_parts, axis=1)
    return extra_close, extra_open


# --- shared caches (keyed by id(close), matching h20260928_18_vix_putw.py's
# own `_ALIGN_CACHE` convention -- `close` is the same object across every
# weights_fn call within one screen_batch run) --------------------------


_RET1_CACHE: dict[int, pd.DataFrame] = {}
_MOM63_CACHE: dict[int, pd.DataFrame] = {}


def _cached_ret1(close: pd.DataFrame) -> pd.DataFrame:
    key = id(close)
    if key not in _RET1_CACHE:
        _RET1_CACHE[key] = close.pct_change(fill_method=None)
    return _RET1_CACHE[key]


def _cached_mom63(close: pd.DataFrame) -> pd.DataFrame:
    key = id(close)
    if key not in _MOM63_CACHE:
        _MOM63_CACHE[key] = close.pct_change(MOMENTUM_LOOKBACK, fill_method=None)
    return _MOM63_CACHE[key]


def _vt40_scale(close: pd.DataFrame, asof: pd.Timestamp, picks: dict[str, float]) -> float:
    """Down-only vol-target scale (single-pass proxy, see module docstring).
    `picks` keys are the actual instrument columns held (real or L2_)."""
    if not picks or asof not in close.index:
        return 1.0
    ret1 = _cached_ret1(close)
    pos = close.index.get_loc(asof)
    start = pos - VT40_WINDOW + 1
    if start < 0:
        return 1.0
    hist = ret1.iloc[start : pos + 1]
    cols = [s for s in picks if s in hist.columns]
    if not cols:
        return 1.0
    weights = np.array([picks[s] for s in cols])
    sub = hist[cols].to_numpy()
    if np.isnan(sub).any():
        return 1.0
    blended = sub @ weights
    vol = float(np.std(blended, ddof=1)) * np.sqrt(252.0)
    if not np.isfinite(vol) or vol <= 0:
        return 1.0
    return float(min(1.0, VT40_TARGET / vol))


# --- weights_fn factories ----------------------------------------------


def _lev_col(sym: str, leverage: str) -> str:
    return f"L2_{sym}" if leverage == "2x" else sym


def _momentum_topk_weights_fn(
    top_n: int, k: int, leverage: str
) -> Callable[[pd.DataFrame, pd.Timestamp], dict[str, float]]:
    def fn(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
        menu = menu_for_asof(asof, top_n)
        if not menu or asof not in close.index:
            return {}
        mom = _cached_mom63(close)
        cols = [s for s in menu if s in mom.columns]
        row = mom.loc[asof, cols].dropna()
        if row.empty:
            return {}
        top = list(row.sort_values(ascending=False).index[:k])
        survivors = [s for s in top if row[s] > 0.0]
        if not survivors:
            return {}
        w = 1.0 / k
        picks_raw = {s: w for s in survivors}
        picks = {_lev_col(s, leverage): weight for s, weight in picks_raw.items()}
        scale = _vt40_scale(close, asof, picks)
        return {sym: weight * scale for sym, weight in picks.items()}

    return fn


def _equal_weight_control_fn(
    top_n: int, leverage: str
) -> Callable[[pd.DataFrame, pd.Timestamp], dict[str, float]]:
    def fn(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
        menu = menu_for_asof(asof, top_n)
        if not menu:
            return {}
        w = 1.0 / len(menu)
        picks_raw = {s: w for s in menu}
        picks = {_lev_col(s, leverage): weight for s, weight in picks_raw.items()}
        scale = _vt40_scale(close, asof, picks)
        return {sym: weight * scale for sym, weight in picks.items()}

    return fn


def _rand_pick_placebo_fn(
    top_n: int, k: int, leverage: str, seed: int
) -> Callable[[pd.DataFrame, pd.Timestamp], dict[str, float]]:
    def fn(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
        menu = sorted(menu_for_asof(asof, top_n))
        if not menu:
            return {}
        yyyymm = asof.year * 100 + asof.month
        rng = np.random.default_rng([seed, yyyymm])
        n_pick = min(k, len(menu))
        chosen = sorted(rng.choice(menu, size=n_pick, replace=False).tolist())
        w = 1.0 / n_pick
        picks_raw = {s: w for s in chosen}
        picks = {_lev_col(s, leverage): weight for s, weight in picks_raw.items()}
        scale = _vt40_scale(close, asof, picks)
        return {sym: weight * scale for sym, weight in picks.items()}

    return fn


# --- candidates -----------------------------------------------------------

CANDIDATES: list[lane.ScreenCandidate] = []
for _n in (20, 50):
    for _k in (1, 2, 3):
        for _lev, _tag in (("1x", "1X"), ("2x", "2X")):
            CANDIDATES.append(
                lane.ScreenCandidate(
                    id=f"LSS_N{_n}_K{_k}_{_tag}",
                    name=f"top-{_n} menu, 63d momentum top-{_k}, {_lev}, vt40",
                    source_card="dir_equity_momentum_concentrated_pwb_registry",
                    universe=UNIVERSE,
                    freq="M",
                    weights_fn=_momentum_topk_weights_fn(_n, _k, _lev),
                )
            )

CANDIDATES.append(
    lane.ScreenCandidate(
        id="LSS_N20_EW_2X",
        name="top-20 menu, equal weight (no picking), 2x, vt40 -- control",
        source_card="dir_levered_single_asset_sma_trend_gate_registry",
        universe=UNIVERSE,
        freq="M",
        weights_fn=_equal_weight_control_fn(20, "2x"),
    )
)

CANDIDATES.append(
    lane.ScreenCandidate(
        id="LSS_RAND_K2_2X",
        name="top-20 menu, random pick k=2 (seed 20260929), 2x, vt40 -- placebo",
        source_card="dir_levered_single_asset_sma_trend_gate_registry",
        universe=UNIVERSE,
        freq="M",
        weights_fn=_rand_pick_placebo_fn(20, 2, "2x", RAND_SEED),
    )
)
