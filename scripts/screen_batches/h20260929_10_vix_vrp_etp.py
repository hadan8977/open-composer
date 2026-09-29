"""T-20260929-10 batch: `scripts/screen_batch.py --batch h20260929_10_vix_vrp_etp
--iteration h20260929_10_vix_vrp_etp`.

Long-only ETP version of Zarattini/Aziz/Mele (2025, SSRN 5316487 / SFI RP
25-91)'s dual-VIX-signal volatility risk premium strategy, replicated per the
independent QuantConnect writeup (`quantconnect_dual_vix_signal_replication`
in `reports/harness/source_cards/h20260929_10_vix_vrp_etp.jsonl`):

  Signal 1 (eVRP): eVRP_t = VIX_t - eRV_t, eRV_t = std(trailing N daily SPY
  close-to-close returns ending at t, ddof=1) * sqrt(252) * 100. N=10 in the
  original/QC default; this batch also tests N=5 and N=20 as the "2-3 nearby
  parameters" the brief asks for.

  Signal 2 (term structure): VIX_t vs VIX3M_t (FRED VXVCLS). VIX < VIX3M is
  upward-sloping/contango (favors short-vol); VIX > VIX3M is inverted/
  backwardation (favors long-vol).

  Original 4-case position logic (QC replication, target_weight on VIXY):
    Case 1: eVRP>0 & VIX<VIX3M  -> target_weight = -VIX/100   (full short-vol)
    Case 2: eVRP<0 & VIX<VIX3M  -> target_weight = -0.5*VIX/100 (half short-vol)
    Case 3: eVRP<0 & VIX>VIX3M  -> target_weight = +VIX/100   (full long-vol)
    Case 4: else                -> target_weight = 0          (cash)

  This batch's long-only-ETP simplification (brief: no short selling, no
  VIXY/UVXY long-vol leg): cases 3 and 4 collapse into one "not short-vol"
  state. Whenever the original signal is short-vol (case 1 or 2), hold SVXY
  at weight min(1, |target_weight|) (1x SVXY weight = VIX/100 or 0.5*VIX/100
  -- NOT QC's suggested 2x SVXY-beta-matching, a deliberate, preregistered
  simplification, see direction-review.json). Whenever it is not (cases 3/4
  combined), hold SPY (the `_SPY` candidates) or nothing, which
  `screen_lane.weights_frame` automatically tops up to SHY (the `_SHY`
  candidates -- SHY is a cash substitute here, not a cross-asset return
  source, per the brief).

12 candidates total (`CANDIDATES: list[lane.ScreenCandidate]`, `freq="D"`,
following `h20260928_18_vix_putw.py`'s external-CSV-in-module-scope pattern
for reading `data/research/vix/VIXCLS.csv` and `VXVCLS.csv`):

  6  VVRP_COMBO_RV{5,10,20}_{SPY,SHY}   -- full 2-signal rule, 3 RV windows
  2  VVRP_SIG1ONLY_{SPY,SHY}            -- eVRP sign only (RV window 10),
                                           term structure dropped
  2  VVRP_SIG2ONLY_{SPY,SHY}            -- VIX vs VIX3M only, eVRP dropped
  1  VVRP_RAND_PLACEBO                  -- deterministic pseudo-random
                                           short-vol day, frequency-matched
                                           to VVRP_COMBO_RV10_SHY's own real
                                           trigger rate; SHY remainder;
                                           NOT eligible for any keep tier
                                           (internal falsification control)
  1  STATIC5050_SMH_QQQ                 -- fixed monthly 50/50 SMH/QQQ blend
                                           (no VIX signal at all); NOT
                                           eligible for any keep tier
                                           (external benchmark control, same
                                           `make_static5050_fn` pattern as
                                           `h20260928_44_etf_pair_switch.py`,
                                           reimplemented here rather than
                                           imported since that module is
                                           another task's in-flight file)

Every `weights_fn` reads only `close.loc[:asof]` (the harness panel) plus
VIX/VIX3M history truncated at `asof` (`.loc[:asof]` on the module-level
Series loaded once from the CSVs) -- no look-ahead by construction, same
convention as `h20260928_18_vix_putw.py`.
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

VIXCLS_PATH = ROOT / "data" / "research" / "vix" / "VIXCLS.csv"
VXVCLS_PATH = ROOT / "data" / "research" / "vix" / "VXVCLS.csv"

SVXY = "SVXY"
SPY = "SPY"
SMH = "SMH"
QQQ = "QQQ"

RV_WINDOWS: tuple[int, ...] = (5, 10, 20)
DEFAULT_RV_WINDOW = 10


def _load_fred_series(path: Path, column: str) -> pd.Series:
    """Load a FRED `observation_date,<column>` CSV into a date-indexed
    Series. FRED already omits non-trading days as absent rows (see
    `VIXCLS.meta.json` / `VXVCLS.meta.json`); no forward fill is applied here
    -- callers align via `.reindex(...).ffill(limit=1)` at use time, matching
    the meta files' documented "gap of 1 trading day forward-filled, 2+ stays
    NaN" policy."""
    frame = pd.read_csv(path)
    frame["observation_date"] = pd.to_datetime(frame["observation_date"])
    series = frame.set_index("observation_date")[column].sort_index()
    return pd.to_numeric(series, errors="coerce")


_VIX_FULL = _load_fred_series(VIXCLS_PATH, "VIXCLS")
_VIX3M_FULL = _load_fred_series(VXVCLS_PATH, "VXVCLS")


def _aligned_vix_vix3m(index: pd.DatetimeIndex) -> tuple[pd.Series, pd.Series]:
    """VIX and VIX3M reindexed onto the panel's own trading-day index, each
    forward-filled by at most 1 trading day (documented FRED gap policy)."""
    vix = _VIX_FULL.reindex(index).ffill(limit=1)
    vix3m = _VIX3M_FULL.reindex(index).ffill(limit=1)
    return vix, vix3m


_ALIGN_CACHE: dict[int, tuple[pd.Series, pd.Series]] = {}


def _cached_aligned(index: pd.DatetimeIndex) -> tuple[pd.Series, pd.Series]:
    key = id(index)
    if key not in _ALIGN_CACHE:
        _ALIGN_CACHE[key] = _aligned_vix_vix3m(index)
    return _ALIGN_CACHE[key]


def _evrp(close: pd.DataFrame, asof: pd.Timestamp, rv_window: int) -> tuple[float, float] | None:
    """(eVRP, VIX) at `asof`, or None if data is insufficient. eRV = std of
    the trailing `rv_window` SPY close-to-close returns ending at `asof`
    (inclusive), annualized (`*sqrt(252)*100`), ddof=1 -- matches the QC
    replication's `np.std(returns, ddof=1) * np.sqrt(252) * 100`, using only
    daily-close returns (no same-day intraday return -- this project's
    frozen contract computes realized vol from closes only, per the brief)."""
    if SPY not in close.columns or asof not in close.index:
        return None
    vix, _vix3m = _cached_aligned(close.index)
    if asof not in vix.index or not np.isfinite(vix.loc[asof]):
        return None
    spy_hist = close[SPY].loc[:asof]
    rets = spy_hist.pct_change().dropna()
    if len(rets) < rv_window:
        return None
    window_rets = rets.iloc[-rv_window:]
    if window_rets.std(ddof=1) is None or not np.isfinite(window_rets.std(ddof=1)):
        return None
    e_rv = float(window_rets.std(ddof=1)) * np.sqrt(252.0) * 100.0
    vix_t = float(vix.loc[asof])
    return vix_t - e_rv, vix_t


def _term_structure(close: pd.DataFrame, asof: pd.Timestamp) -> tuple[bool, float] | None:
    """(vix_below_vix3m, VIX) at `asof`, or None if data is insufficient."""
    if asof not in close.index:
        return None
    vix, vix3m = _cached_aligned(close.index)
    if asof not in vix.index or asof not in vix3m.index:
        return None
    v, v3 = vix.loc[asof], vix3m.loc[asof]
    if not (np.isfinite(v) and np.isfinite(v3)):
        return None
    return bool(v < v3), float(v)


def _svxy_weight(target_abs_weight: float) -> dict[str, float]:
    return {SVXY: float(min(1.0, max(0.0, target_abs_weight)))}


def _combo_weights_fn(
    rv_window: int, non_short_vol_leg: str | None
) -> Callable[[pd.DataFrame, pd.Timestamp], dict[str, float]]:
    """Full 2-signal rule. `non_short_vol_leg`: "SPY" holds SPY whenever not
    short-vol; `None` returns {} (harness fills the SHY remainder)."""

    def fn(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
        evrp_res = _evrp(close, asof, rv_window)
        ts_res = _term_structure(close, asof)
        if evrp_res is None or ts_res is None:
            return {}
        evrp, vix_evrp = evrp_res
        vix_below_vix3m, vix_ts = ts_res
        vix_t = vix_evrp if np.isfinite(vix_evrp) else vix_ts
        if evrp > 0 and vix_below_vix3m:
            return _svxy_weight(vix_t / 100.0)
        if evrp < 0 and vix_below_vix3m:
            return _svxy_weight(0.5 * vix_t / 100.0)
        # Cases 3 (eVRP<0 & backwardation) and 4 (else) collapse: not short-vol.
        if non_short_vol_leg == SPY:
            if SPY not in close.columns or asof not in close.index or pd.isna(close.loc[asof, SPY]):
                return {}
            return {SPY: 1.0}
        return {}

    return fn


def _sig1_only_weights_fn(
    rv_window: int, non_short_vol_leg: str | None
) -> Callable[[pd.DataFrame, pd.Timestamp], dict[str, float]]:
    """Signal 1 (eVRP) only: eVRP>0 -> full short-vol (VIX/100 in SVXY);
    else -> not short-vol. Term structure dropped entirely."""

    def fn(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
        evrp_res = _evrp(close, asof, rv_window)
        if evrp_res is None:
            return {}
        evrp, vix_t = evrp_res
        if evrp > 0:
            return _svxy_weight(vix_t / 100.0)
        if non_short_vol_leg == SPY:
            if SPY not in close.columns or asof not in close.index or pd.isna(close.loc[asof, SPY]):
                return {}
            return {SPY: 1.0}
        return {}

    return fn


def _sig2_only_weights_fn(
    non_short_vol_leg: str | None,
) -> Callable[[pd.DataFrame, pd.Timestamp], dict[str, float]]:
    """Signal 2 (term structure) only: VIX<VIX3M -> full short-vol (VIX/100
    in SVXY); else -> not short-vol. eVRP dropped entirely."""

    def fn(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
        ts_res = _term_structure(close, asof)
        if ts_res is None:
            return {}
        vix_below_vix3m, vix_t = ts_res
        if vix_below_vix3m:
            return _svxy_weight(vix_t / 100.0)
        if non_short_vol_leg == SPY:
            if SPY not in close.columns or asof not in close.index or pd.isna(close.loc[asof, SPY]):
                return {}
            return {SPY: 1.0}
        return {}

    return fn


_RAND_RATE_CACHE: dict[str, float] = {}


def _rand_trigger_rate(close: pd.DataFrame) -> float:
    """Fraction of days in the FULL local VIX/VIX3M/SPY history (not
    restricted to select/anchor) where VVRP_COMBO_RV10's real short-vol
    condition (case 1 or case 2) fires -- the RAND placebo's calibrated
    trigger frequency. Computed once per panel, cached."""
    key = "rate"
    if key in _RAND_RATE_CACHE:
        return _RAND_RATE_CACHE[key]
    fn = _combo_weights_fn(DEFAULT_RV_WINDOW, non_short_vol_leg=None)
    n_short = 0
    n_total = 0
    for d in close.index:
        n_total += 1
        raw = fn(close, d)
        if raw.get(SVXY, 0.0) > 0:
            n_short += 1
    rate = float(n_short) / float(n_total) if n_total else 0.0
    _RAND_RATE_CACHE[key] = rate
    return rate


def _rand_placebo_weights_fn(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
    """Deterministic pseudo-random day: a SHA-256 hash of the calendar date
    is compared against `_rand_trigger_rate`, calibrated once from
    VVRP_COMBO_RV10's own real trigger frequency over the full local history.
    On a trigger day, holds SVXY at that day's VIX/100 weight (same sizing
    convention as the real candidates -- isolates the value of the eVRP/
    term-structure *conditioning*, not the VIX-scaled sizing itself).
    Never reads price/VIX data to decide the trigger itself, only the VIX
    level for sizing on a triggered day."""
    rate = _rand_trigger_rate(close)
    digest = hashlib.sha256(f"VVRP|RAND|{asof.date().isoformat()}".encode()).hexdigest()
    draw = int(digest[:16], 16) / float(16**16)
    if draw >= rate:
        return {}
    vix, _vix3m = _cached_aligned(close.index)
    if asof not in vix.index or not np.isfinite(vix.loc[asof]):
        return {}
    return _svxy_weight(float(vix.loc[asof]) / 100.0)


def _static5050_weights_fn(
    leg_a: str, leg_b: str
) -> Callable[[pd.DataFrame, pd.Timestamp], dict[str, float]]:
    """Fixed 50/50 monthly-rebalanced blend of `leg_a`/`leg_b` -- no VIX
    signal at all. Reimplemented from `h20260928_44_etf_pair_switch.py`'s
    `make_static5050_fn` (that module belongs to another in-flight task and
    is not imported here). Reads only `close.loc[:asof]`."""

    def fn(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
        hist = close.loc[:asof]
        if leg_a not in hist.columns or leg_b not in hist.columns:
            return {}
        if asof not in hist.index:
            return {}
        if pd.isna(hist.loc[asof, leg_a]) or pd.isna(hist.loc[asof, leg_b]):
            return {}
        return {leg_a: 0.5, leg_b: 0.5}

    return fn


CANDIDATES: list[lane.ScreenCandidate] = []

for _rv in RV_WINDOWS:
    for _leg, _suffix in ((SPY, "SPY"), (None, "SHY")):
        CANDIDATES.append(
            lane.ScreenCandidate(
                id=f"VVRP_COMBO_RV{_rv}_{_suffix}",
                name=(
                    f"VIX dual-signal VRP (eVRP RV{_rv}d + VIX/VIX3M term structure), "
                    f"SVXY sized VIX/100, non-short-vol leg={_suffix}"
                ),
                source_card="quantconnect_dual_vix_signal_replication",
                universe=(SVXY, SPY) if _leg == SPY else (SVXY,),
                freq="D",
                weights_fn=_combo_weights_fn(_rv, non_short_vol_leg=_leg),
            )
        )

for _leg, _suffix in ((SPY, "SPY"), (None, "SHY")):
    CANDIDATES.append(
        lane.ScreenCandidate(
            id=f"VVRP_SIG1ONLY_{_suffix}",
            name=f"VIX VRP, signal 1 only (eVRP RV10d sign), non-short-vol leg={_suffix}",
            source_card="quantconnect_dual_vix_signal_replication",
            universe=(SVXY, SPY) if _leg == SPY else (SVXY,),
            freq="D",
            weights_fn=_sig1_only_weights_fn(DEFAULT_RV_WINDOW, non_short_vol_leg=_leg),
        )
    )

for _leg, _suffix in ((SPY, "SPY"), (None, "SHY")):
    CANDIDATES.append(
        lane.ScreenCandidate(
            id=f"VVRP_SIG2ONLY_{_suffix}",
            name=(
                f"VIX VRP, signal 2 only (VIX vs VIX3M term structure), non-short-vol leg={_suffix}"
            ),
            source_card="quantconnect_dual_vix_signal_replication",
            universe=(SVXY, SPY) if _leg == SPY else (SVXY,),
            freq="D",
            weights_fn=_sig2_only_weights_fn(non_short_vol_leg=_leg),
        )
    )

CANDIDATES.append(
    lane.ScreenCandidate(
        id="VVRP_RAND_PLACEBO",
        name="Placebo: pseudo-random short-vol day, frequency-matched to VVRP_COMBO_RV10_SHY",
        source_card="vix_vrp_etp_internal_placebo_random_day",
        universe=(SVXY,),
        freq="D",
        weights_fn=_rand_placebo_weights_fn,
    )
)

CANDIDATES.append(
    lane.ScreenCandidate(
        id="STATIC5050_SMH_QQQ",
        name="Static 50/50 SMH/QQQ monthly-rebalanced hold (no VIX signal)",
        source_card="quantconnect_dual_vix_signal_replication",
        universe=(SMH, QQQ),
        freq="M",
        weights_fn=_static5050_weights_fn(SMH, QQQ),
    )
)

assert len(CANDIDATES) == 12, f"expected 12 candidates, got {len(CANDIDATES)}"
assert len({c.id for c in CANDIDATES}) == 12, "duplicate candidate ids"
