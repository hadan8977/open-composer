"""H-20260928-04 batch screening, batch 1: 19 published long-only US-listed-ETF
rules for `scripts/screen_batch.py --batch h20260928_04_batch1 --iteration
h20260928_04_s3_alt_div_batch1`.

Deliberately does NOT import `screen_lane` (per the brief): every function
here is a standalone pure `fn(close: pd.DataFrame, asof: pd.Timestamp) ->
dict[str, float]` that only reads `close.loc[:asof]` -- never a later row.
`SPECS` is a list of plain dicts (`id, name, source_card, universe, freq,
fn`), matched by id to `reports/research/iterations/h20260928_04_s3_alt_div_
batch1/candidate-manifest.json`. No return, Sharpe, or backtest number is
computed by this module and it is not run as part of this preregistration
round -- the interactive screening session wires `SPECS` into the lane.

Every rule is implemented exactly as published (see the source cards in
`reports/harness/source_cards/h20260928_04_s3_alt_div_batch1.jsonl`), with the
source's own parameters. Weights always sum to <= 1; the remainder is SHY by
the screening lane's own convention (never written explicitly here).

Families
--------
F1 (hold outright, no rule): DBMF, KMLM, CTA, WTMF, FMF -- managed-futures
   ETFs; the candidate is simply the fund's own listed NAV.
F2 (published tactical-allocation rules, computed over public ETF universes):
   VAA-G4, DAA-G12, PAA-CPR, HAA, GPM, GEM, GTAA-5, ADM, BAA-Balanced.
F3 (hold outright, no rule): RPAR, UPAR, NTSX, QAI, TRTY -- other
   alt-diversifier ETFs; the candidate is simply the fund's own listed NAV.

Momentum formulas used (all computed on a month-end-resampled close series,
never on raw daily closes -- see `_month_end_series`):
  - 13612W (VAA, DAA, BAA canary gate):
        12*(p0/p1-1) + 4*(p0/p3-1) + 2*(p0/p6-1) + (p0/p12-1)
  - SMA13 ratio (PAA):        p0 / mean(last 13 month-end closes incl. p0) - 1
  - avg 1/3/6/12-month return (HAA, GPM base r_i):
        mean(p0/p1-1, p0/p3-1, p0/p6-1, p0/p12-1)
  - sum 1/3/6-month return (ADM):  (p0/p1-1) + (p0/p3-1) + (p0/p6-1)
  - relative momentum (BAA ranking, distinct from its canary gate):
        p0 / mean(last 13 month-end closes incl. p0)
  - price vs 10-month SMA (GTAA):  p0 > mean(last 10 month-end closes incl. p0)
  - correlation-hedged momentum (GPM): z_i = r_i * (1 - c_i), c_i = trailing
    12-month correlation of asset i's monthly returns to the equal-weight
    return of the 12-asset risk universe.

`p0` is always the most recent month-end close at or before `asof`; `p1` is
one month-end back from `p0`, `p3` three, etc. -- never a calendar-day offset.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------
# Shared helpers -- month-end resampling and momentum formulas.
# --------------------------------------------------------------------------


def _month_end_series(hist: pd.Series) -> pd.Series:
    """Last known value per calendar month, from a series already sliced to
    `:asof`. Only ever reads rows already present in `hist` -- callers must
    pass `close[sym].loc[:asof]`, never the full unsliced column."""
    s = hist.dropna()
    if s.empty:
        return s
    # Grouping keys are plain numpy arrays (not a list of tuples -- pandas'
    # groupby key resolution can misparse a list of `(year, month)` tuples
    # as column/level labels). Only the chronological ORDER of the result
    # matters to every caller (`_lookback` indexes positionally), so the
    # resulting (year, month) MultiIndex is never read.
    return s.groupby([s.index.year, s.index.month], sort=False).last()


def _lookback(m: pd.Series, k: int) -> float | None:
    """`k` months back from the most recent month-end (`k=0` is the most
    recent month-end itself). `None` if there is not enough history."""
    if len(m) <= k:
        return None
    return float(m.iloc[-1 - k])


def _mom_13612w(m: pd.Series) -> float | None:
    p0, p1, p3, p6, p12 = (_lookback(m, k) for k in (0, 1, 3, 6, 12))
    if None in (p0, p1, p3, p6, p12) or 0 in (p1, p3, p6, p12):
        return None
    return 12.0 * (p0 / p1 - 1.0) + 4.0 * (p0 / p3 - 1.0) + 2.0 * (p0 / p6 - 1.0) + (p0 / p12 - 1.0)


def _mom_sma_ratio(m: pd.Series, window: int) -> float | None:
    if len(m) < window:
        return None
    tail = m.iloc[-window:]
    sma = float(tail.mean())
    if sma == 0:
        return None
    return float(tail.iloc[-1]) / sma - 1.0


def _relative_momentum(m: pd.Series, window: int) -> float | None:
    if len(m) < window:
        return None
    tail = m.iloc[-window:]
    sma = float(tail.mean())
    if sma == 0:
        return None
    return float(tail.iloc[-1]) / sma


def _price_above_sma(m: pd.Series, window: int) -> bool | None:
    if len(m) < window:
        return None
    tail = m.iloc[-window:]
    return bool(tail.iloc[-1] > tail.mean())


def _mom_avg_1_3_6_12(m: pd.Series) -> float | None:
    p0, p1, p3, p6, p12 = (_lookback(m, k) for k in (0, 1, 3, 6, 12))
    if None in (p0, p1, p3, p6, p12) or 0 in (p1, p3, p6, p12):
        return None
    return float(np.mean([p0 / p1 - 1.0, p0 / p3 - 1.0, p0 / p6 - 1.0, p0 / p12 - 1.0]))


def _mom_sum_1_3_6(m: pd.Series) -> float | None:
    p0, p1, p3, p6 = (_lookback(m, k) for k in (0, 1, 3, 6))
    if None in (p0, p1, p3, p6) or 0 in (p1, p3, p6):
        return None
    return (p0 / p1 - 1.0) + (p0 / p3 - 1.0) + (p0 / p6 - 1.0)


def _pct_change_over_months(m: pd.Series, k: int) -> float | None:
    p0, pk = _lookback(m, 0), _lookback(m, k)
    if p0 is None or pk is None or pk == 0:
        return None
    return p0 / pk - 1.0


def _month_end_frame(hist: pd.DataFrame, universe: tuple[str, ...]) -> dict[str, pd.Series]:
    return {sym: _month_end_series(hist[sym]) for sym in universe if sym in hist.columns}


def _best_by_score(scores: dict[str, float | None]) -> str | None:
    available = {k: v for k, v in scores.items() if v is not None}
    if not available:
        return None
    return max(available, key=lambda k: available[k])


def _hold_if_present(hist: pd.DataFrame, sym: str) -> dict[str, float]:
    if sym not in hist.columns:
        return {}
    series = hist[sym].dropna()
    if series.empty:
        return {}
    return {sym: 1.0}


# --------------------------------------------------------------------------
# F1 -- managed-futures ETFs held outright (no rule, no free parameter).
# --------------------------------------------------------------------------


def w_f1_dbmf(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
    return _hold_if_present(close.loc[:asof], "DBMF")


def w_f1_kmlm(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
    return _hold_if_present(close.loc[:asof], "KMLM")


def w_f1_cta(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
    return _hold_if_present(close.loc[:asof], "CTA")


def w_f1_wtmf(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
    return _hold_if_present(close.loc[:asof], "WTMF")


def w_f1_fmf(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
    return _hold_if_present(close.loc[:asof], "FMF")


# --------------------------------------------------------------------------
# F2_VAA_G4 -- Vigilant Asset Allocation (Keller & Keuning 2017, SSRN 3002624)
# --------------------------------------------------------------------------

_VAA_OFFENSIVE = ("SPY", "EFA", "EEM", "AGG")
_VAA_DEFENSIVE = ("LQD", "IEF", "SHY")


def w_f2_vaa_g4(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
    hist = close.loc[:asof]
    off = _month_end_frame(hist, _VAA_OFFENSIVE)
    dfn = _month_end_frame(hist, _VAA_DEFENSIVE)
    if len(off) < len(_VAA_OFFENSIVE) or len(dfn) < len(_VAA_DEFENSIVE):
        return {}
    off_scores = {sym: _mom_13612w(m) for sym, m in off.items()}
    if None in off_scores.values():
        return {}
    if all(score > 0 for score in off_scores.values()):
        winner = _best_by_score(off_scores)
        return {winner: 1.0} if winner else {}
    dfn_scores = {sym: _mom_13612w(m) for sym, m in dfn.items()}
    winner = _best_by_score(dfn_scores)
    return {winner: 1.0} if winner else {}


# --------------------------------------------------------------------------
# F2_DAA_G12 -- Defensive Asset Allocation (Keller & Keuning 2018, SSRN 3212862)
# --------------------------------------------------------------------------

_DAA_RISKY = ("SPY", "IWM", "QQQ", "VGK", "EWJ", "VWO", "VNQ", "GSG", "GLD", "TLT", "HYG", "LQD")
_DAA_CASH = ("SHY", "IEF", "LQD")
_DAA_CANARY = ("VWO", "BND")
_DAA_T = 6
_DAA_B = 2


def w_f2_daa_g12(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
    hist = close.loc[:asof]
    risky = _month_end_frame(hist, _DAA_RISKY)
    cash = _month_end_frame(hist, _DAA_CASH)
    canary = _month_end_frame(hist, _DAA_CANARY)
    if len(risky) < len(_DAA_RISKY) or len(cash) < len(_DAA_CASH) or len(canary) < len(_DAA_CANARY):
        return {}
    canary_scores = {sym: _mom_13612w(m) for sym, m in canary.items()}
    if None in canary_scores.values():
        return {}
    b = sum(1 for v in canary_scores.values() if v < 0)
    cf = min(1.0, b / _DAA_B)
    risky_scores = {sym: _mom_13612w(m) for sym, m in risky.items()}
    if None in risky_scores.values():
        return {}
    top = sorted(risky_scores, key=lambda s: risky_scores[s], reverse=True)[:_DAA_T]
    weights: dict[str, float] = {}
    if cf < 1.0:
        per_asset = (1.0 - cf) / _DAA_T
        for sym in top:
            weights[sym] = per_asset
    if cf > 0:
        cash_scores = {sym: _mom_13612w(m) for sym, m in cash.items()}
        cash_winner = _best_by_score(cash_scores)
        if cash_winner:
            weights[cash_winner] = weights.get(cash_winner, 0.0) + cf
    return weights


# --------------------------------------------------------------------------
# F2_PAA -- Protective Asset Allocation, CPR variant (Keller & Keuning 2016,
# SSRN 2759734; CP asset rotates IEF/SHY by momentum, the paper's own choice)
# --------------------------------------------------------------------------

_PAA_UNIVERSE = ("SPY", "QQQ", "IWM", "VGK", "EWJ", "EEM", "VNQ", "DBC", "GLD", "HYG", "LQD", "TLT")
_PAA_CP = ("IEF", "SHY")
_PAA_TOP_N = 6
_PAA_BREADTH_DENOM = 6
_PAA_SMA_WINDOW = 13


def w_f2_paa(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
    hist = close.loc[:asof]
    universe = _month_end_frame(hist, _PAA_UNIVERSE)
    cp = _month_end_frame(hist, _PAA_CP)
    if len(universe) < len(_PAA_UNIVERSE) or len(cp) < len(_PAA_CP):
        return {}
    mom = {sym: _mom_sma_ratio(m, _PAA_SMA_WINDOW) for sym, m in universe.items()}
    if None in mom.values():
        return {}
    n_positive = sum(1 for v in mom.values() if v > 0)
    cp_pct = 1.0 if n_positive <= _PAA_TOP_N else (12 - n_positive) / _PAA_BREADTH_DENOM
    cp_pct = max(0.0, min(1.0, cp_pct))
    weights: dict[str, float] = {}
    if cp_pct < 1.0:
        top = sorted(mom, key=lambda s: mom[s], reverse=True)[:_PAA_TOP_N]
        per_asset = (1.0 - cp_pct) / _PAA_TOP_N
        for sym in top:
            weights[sym] = per_asset
    if cp_pct > 0:
        cp_mom = {sym: _mom_sma_ratio(m, _PAA_SMA_WINDOW) for sym, m in cp.items()}
        winner = _best_by_score(cp_mom)
        if winner:
            weights[winner] = weights.get(winner, 0.0) + cp_pct
    return weights


# --------------------------------------------------------------------------
# F2_HAA -- Hybrid Asset Allocation (Keller & Keuning 2023, SSRN 4346906)
# --------------------------------------------------------------------------

_HAA_CANARY = "TIP"
_HAA_OFFENSIVE = ("SPY", "IWM", "EFA", "EEM", "VNQ", "PDBC", "IEF", "TLT")
_HAA_DEFENSIVE = "IEF"
_HAA_TOP_N = 4


def w_f2_haa(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
    hist = close.loc[:asof]
    if _HAA_CANARY not in hist.columns or _HAA_DEFENSIVE not in hist.columns:
        return {}
    canary_m = _month_end_series(hist[_HAA_CANARY])
    canary_mom = _mom_avg_1_3_6_12(canary_m)
    if canary_mom is None:
        return {}
    ief_m = _month_end_series(hist[_HAA_DEFENSIVE])
    ief_mom = _mom_avg_1_3_6_12(ief_m)
    if canary_mom <= 0:
        return {_HAA_DEFENSIVE: 1.0} if ief_mom is not None and ief_mom > 0 else {}
    offensive = _month_end_frame(hist, _HAA_OFFENSIVE)
    if len(offensive) < len(_HAA_OFFENSIVE):
        return {}
    mom = {sym: _mom_avg_1_3_6_12(m) for sym, m in offensive.items()}
    if None in mom.values():
        return {}
    top = sorted(mom, key=lambda s: mom[s], reverse=True)[:_HAA_TOP_N]
    weights: dict[str, float] = {}
    slot = 1.0 / _HAA_TOP_N
    for sym in top:
        if mom[sym] > 0:
            weights[sym] = weights.get(sym, 0.0) + slot
        elif ief_mom is not None and ief_mom > 0:
            weights[_HAA_DEFENSIVE] = weights.get(_HAA_DEFENSIVE, 0.0) + slot
        # else: redirected slot is left unallocated (= SHY by convention)
    return weights


# --------------------------------------------------------------------------
# F2_GPM -- Generalized Protective Momentum (Keller, Butler & Kipnis, SSRN
# 2606884, "Momentum and Markowitz: A Golden Combination")
# --------------------------------------------------------------------------

_GPM_UNIVERSE = ("SPY", "QQQ", "IWM", "VGK", "EWJ", "EEM", "VNQ", "DBC", "GLD", "HYG", "LQD", "TLT")
_GPM_CP = ("IEF", "SHY")
_GPM_TOP_N = 3
_GPM_BREADTH_DENOM = 6
_GPM_CORR_WINDOW = 12


def _monthly_returns(m: pd.Series) -> pd.Series:
    return m.pct_change().dropna()


def _gpm_scores(month_end: dict[str, pd.Series]) -> dict[str, float | None]:
    rets = {sym: _monthly_returns(m) for sym, m in month_end.items()}
    tails = {}
    for sym, r in rets.items():
        if len(r) < _GPM_CORR_WINDOW:
            tails[sym] = None
        else:
            tails[sym] = r.iloc[-_GPM_CORR_WINDOW:]
    if any(v is None for v in tails.values()):
        return {sym: None for sym in month_end}
    universe_avg = pd.concat(tails.values(), axis=1).mean(axis=1)
    scores: dict[str, float | None] = {}
    for sym, m in month_end.items():
        r_i = _mom_avg_1_3_6_12(m)
        tail = tails[sym]
        if r_i is None or tail is None or tail.std() == 0 or universe_avg.std() == 0:
            scores[sym] = None
            continue
        c_i = float(tail.corr(universe_avg))
        scores[sym] = r_i * (1.0 - c_i)
    return scores


def w_f2_gpm(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
    hist = close.loc[:asof]
    universe = _month_end_frame(hist, _GPM_UNIVERSE)
    cp = _month_end_frame(hist, _GPM_CP)
    if len(universe) < len(_GPM_UNIVERSE) or len(cp) < len(_GPM_CP):
        return {}
    z = _gpm_scores(universe)
    if None in z.values():
        return {}
    n_positive = sum(1 for v in z.values() if v > 0)
    cp_pct = 1.0 if n_positive <= _GPM_TOP_N * 2 else (12 - n_positive) / _GPM_BREADTH_DENOM
    cp_pct = max(0.0, min(1.0, cp_pct))
    weights: dict[str, float] = {}
    if cp_pct < 1.0:
        top = sorted(z, key=lambda s: z[s], reverse=True)[:_GPM_TOP_N]
        per_asset = (1.0 - cp_pct) / _GPM_TOP_N
        for sym in top:
            weights[sym] = per_asset
    if cp_pct > 0:
        cp_all = dict(universe)
        cp_all.update(cp)
        cp_z = _gpm_scores(cp_all)
        cp_only = {sym: cp_z.get(sym) for sym in _GPM_CP}
        winner = _best_by_score(cp_only)
        if winner:
            weights[winner] = weights.get(winner, 0.0) + cp_pct
    return weights


# --------------------------------------------------------------------------
# F2_GEM -- Global Equities Momentum (Antonacci, "Risk Premia Harvesting
# Through Dual Momentum"; VEU used for the international leg per the
# BestFolio replication opened for this batch)
# --------------------------------------------------------------------------

_GEM_UNIVERSE = ("SPY", "VEU", "AGG", "BIL")


def w_f2_gem(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
    hist = close.loc[:asof]
    month_end = _month_end_frame(hist, _GEM_UNIVERSE)
    if len(month_end) < len(_GEM_UNIVERSE):
        return {}
    ret12 = {sym: _pct_change_over_months(m, 12) for sym, m in month_end.items()}
    if None in ret12.values():
        return {}
    if ret12["SPY"] > ret12["BIL"]:
        winner = "SPY" if ret12["SPY"] >= ret12["VEU"] else "VEU"
        return {winner: 1.0}
    return {"AGG": 1.0}


# --------------------------------------------------------------------------
# F2_GTAA -- Faber Global Tactical Asset Allocation, 5-asset 10-month SMA
# (Faber 2007, SSRN 962461)
# --------------------------------------------------------------------------

_GTAA_UNIVERSE = ("SPY", "EFA", "TIP", "GSG", "VNQ")
_GTAA_SMA_WINDOW = 10
_GTAA_SLEEVE = 1.0 / 5.0


def w_f2_gtaa(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
    hist = close.loc[:asof]
    month_end = _month_end_frame(hist, _GTAA_UNIVERSE)
    if len(month_end) < len(_GTAA_UNIVERSE):
        return {}
    weights: dict[str, float] = {}
    for sym, m in month_end.items():
        above = _price_above_sma(m, _GTAA_SMA_WINDOW)
        if above is None:
            return {}
        if above:
            weights[sym] = _GTAA_SLEEVE
    return weights


# --------------------------------------------------------------------------
# F2_ADM -- Accelerating Dual Momentum (Engineered Portfolio, 2018-05-02;
# SPY/SCZ ETF proxy for the original VFINX/VINEX mutual funds)
# --------------------------------------------------------------------------

_ADM_EQUITY = ("SPY", "SCZ")
_ADM_DEFENSIVE = ("TLT", "TIP")


def w_f2_adm(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
    hist = close.loc[:asof]
    equity = _month_end_frame(hist, _ADM_EQUITY)
    defensive = _month_end_frame(hist, _ADM_DEFENSIVE)
    if len(equity) < len(_ADM_EQUITY) or len(defensive) < len(_ADM_DEFENSIVE):
        return {}
    scores = {sym: _mom_sum_1_3_6(m) for sym, m in equity.items()}
    if None in scores.values():
        return {}
    if max(scores.values()) > 0:
        winner = _best_by_score(scores)
        return {winner: 1.0} if winner else {}
    ret1m = {sym: _pct_change_over_months(m, 1) for sym, m in defensive.items()}
    winner = _best_by_score(ret1m)
    return {winner: 1.0} if winner else {}


# --------------------------------------------------------------------------
# F2_BAA_BAL -- Bold Asset Allocation, Balanced variant (Keller & Keuning,
# SSRN 3592671). Re-included from giants_sweep_20260922 (f5_baa_balanced,
# anchor Sharpe 0.49 under the old frozen-gate criterion) because the keep
# rule changed to K1/K2; see direction-review.json.
# --------------------------------------------------------------------------

_BAA_CANARY = ("SPY", "EFA", "EEM", "AGG")
_BAA_OFFENSIVE = (
    "SPY",
    "QQQ",
    "IWM",
    "VGK",
    "EWJ",
    "EEM",
    "VNQ",
    "DBC",
    "GLD",
    "TLT",
    "HYG",
    "LQD",
)
_BAA_DEFENSIVE = ("TIP", "DBC", "BIL", "IEF", "TLT", "LQD", "AGG")
_BAA_OFFENSIVE_TOP_N = 6
_BAA_DEFENSIVE_TOP_N = 3
_BAA_RELATIVE_WINDOW = 13


def w_f2_baa_bal(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
    hist = close.loc[:asof]
    canary = _month_end_frame(hist, _BAA_CANARY)
    if len(canary) < len(_BAA_CANARY):
        return {}
    canary_mom = {sym: _mom_13612w(m) for sym, m in canary.items()}
    if None in canary_mom.values():
        return {}
    if all(v > 0 for v in canary_mom.values()):
        universe = _month_end_frame(hist, _BAA_OFFENSIVE)
        top_n = _BAA_OFFENSIVE_TOP_N
    else:
        universe = _month_end_frame(hist, _BAA_DEFENSIVE)
        top_n = _BAA_DEFENSIVE_TOP_N
    needed = len(_BAA_OFFENSIVE) if top_n == _BAA_OFFENSIVE_TOP_N else len(_BAA_DEFENSIVE)
    if len(universe) < needed:
        return {}
    rel = {sym: _relative_momentum(m, _BAA_RELATIVE_WINDOW) for sym, m in universe.items()}
    if None in rel.values():
        return {}
    top = sorted(rel, key=lambda s: rel[s], reverse=True)[:top_n]
    per_asset = 1.0 / top_n
    return {sym: per_asset for sym in top}


# --------------------------------------------------------------------------
# F3 -- other alt-diversifier ETFs held outright (no rule, no free parameter).
# --------------------------------------------------------------------------


def w_f3_rpar(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
    return _hold_if_present(close.loc[:asof], "RPAR")


def w_f3_upar(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
    return _hold_if_present(close.loc[:asof], "UPAR")


def w_f3_ntsx(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
    return _hold_if_present(close.loc[:asof], "NTSX")


def w_f3_qai(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
    return _hold_if_present(close.loc[:asof], "QAI")


def w_f3_trty(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
    return _hold_if_present(close.loc[:asof], "TRTY")


# --------------------------------------------------------------------------
# SPECS -- wired into the screening lane by the interactive session.
# --------------------------------------------------------------------------

SPECS: list[dict] = [
    {
        "id": "F1_DBMF",
        "name": "iMGP DBi Managed Futures Strategy ETF (hold outright)",
        "source_card": "imgp_dbmf_product_page_cta_replication_2026",
        "universe": ("DBMF",),
        "freq": "M",
        "fn": w_f1_dbmf,
    },
    {
        "id": "F1_KMLM",
        "name": "KFA Mount Lucas Managed Futures Index Strategy ETF (hold outright)",
        "source_card": "kfa_kmlm_factsheet_mlm_index_2024",
        "universe": ("KMLM",),
        "freq": "M",
        "fn": w_f1_kmlm,
    },
    {
        "id": "F1_CTA",
        "name": "Simplify Managed Futures Strategy ETF (hold outright)",
        "source_card": "simplify_cta_fund_page_sg_cta_index_2026",
        "universe": ("CTA",),
        "freq": "M",
        "fn": w_f1_cta,
    },
    {
        "id": "F1_WTMF",
        "name": "WisdomTree Managed Futures Strategy Fund (hold outright)",
        "source_card": "wisdomtree_wtmf_form10_dti_index_2011",
        "universe": ("WTMF",),
        "freq": "M",
        "fn": w_f1_wtmf,
    },
    {
        "id": "F1_FMF",
        "name": "First Trust Managed Futures Strategy Fund (hold outright)",
        "source_card": "ftportfolios_fmf_summary_2026",
        "universe": ("FMF",),
        "freq": "M",
        "fn": w_f1_fmf,
    },
    {
        "id": "F2_VAA_G4",
        "name": "Vigilant Asset Allocation (VAA-G4, T=1/B=1)",
        "source_card": "keller_keuning_vaa_ssrn_2017_allocatesmartly_replication",
        "universe": _VAA_OFFENSIVE + _VAA_DEFENSIVE,
        "freq": "M",
        "fn": w_f2_vaa_g4,
    },
    {
        "id": "F2_DAA_G12",
        "name": "Defensive Asset Allocation (DAA-G12, T=6/B=2)",
        "source_card": "keller_keuning_daa_g12_turingtrader_code_replication_2019",
        "universe": tuple(sorted(set(_DAA_RISKY) | set(_DAA_CASH) | set(_DAA_CANARY) | {"BND"})),
        "freq": "M",
        "fn": w_f2_daa_g12,
    },
    {
        "id": "F2_PAA",
        "name": "Protective Asset Allocation (PAA-CPR, T=6, denom=6)",
        "source_card": "keller_keuning_paa_cpr_ssrn_2016_allocatesmartly_replication",
        "universe": _PAA_UNIVERSE + _PAA_CP,
        "freq": "M",
        "fn": w_f2_paa,
    },
    {
        "id": "F2_HAA",
        "name": "Hybrid Asset Allocation (single TIP canary)",
        "source_card": "keuning_haa_trendxplorer_primary_2023",
        "universe": (_HAA_CANARY,) + _HAA_OFFENSIVE,
        "freq": "M",
        "fn": w_f2_haa,
    },
    {
        "id": "F2_GPM",
        "name": "Generalized Protective Momentum (correlation-hedged, top-3)",
        "source_card": "keller_keuning_gpm_allocatesmartly_replication",
        "universe": _GPM_UNIVERSE + _GPM_CP,
        "freq": "M",
        "fn": w_f2_gpm,
    },
    {
        "id": "F2_GEM",
        "name": "Global Equities Momentum (Antonacci dual momentum, SPY/VEU/AGG/BIL)",
        "source_card": "antonacci_gem_risk_premia_harvesting_2013_primary",
        "universe": _GEM_UNIVERSE,
        "freq": "M",
        "fn": w_f2_gem,
    },
    {
        "id": "F2_GTAA",
        "name": "Faber Global Tactical Asset Allocation (GTAA-5, 10-month SMA)",
        "source_card": "faber_gtaa_ssrn_2007_primary",
        "universe": _GTAA_UNIVERSE,
        "freq": "M",
        "fn": w_f2_gtaa,
    },
    {
        "id": "F2_ADM",
        "name": "Accelerating Dual Momentum (SPY/SCZ, TLT/TIP defensive)",
        "source_card": "engineeredportfolio_adm_primary_2018",
        "universe": _ADM_EQUITY + _ADM_DEFENSIVE,
        "freq": "M",
        "fn": w_f2_adm,
    },
    {
        "id": "F2_BAA_BAL",
        "name": "Bold Asset Allocation (BAA-Balanced)",
        "source_card": "giants_sweep_baa_prior_result_2026_09_22",
        "universe": tuple(sorted(set(_BAA_CANARY) | set(_BAA_OFFENSIVE) | set(_BAA_DEFENSIVE))),
        "freq": "M",
        "fn": w_f2_baa_bal,
    },
    {
        "id": "F3_RPAR",
        "name": "RPAR Risk Parity ETF (hold outright)",
        "source_card": "tidal_rpar_sec_485apos_2019",
        "universe": ("RPAR",),
        "freq": "M",
        "fn": w_f3_rpar,
    },
    {
        "id": "F3_UPAR",
        "name": "UPAR Ultra Risk Parity ETF (hold outright)",
        "source_card": "tidal_upar_product_page_2026",
        "universe": ("UPAR",),
        "freq": "M",
        "fn": w_f3_upar,
    },
    {
        "id": "F3_NTSX",
        "name": "WisdomTree U.S. Efficient Core Fund, 90/60 (hold outright)",
        "source_card": "wisdomtree_ntsx_sec_497_2018",
        "universe": ("NTSX",),
        "freq": "M",
        "fn": w_f3_ntsx,
    },
    {
        "id": "F3_QAI",
        "name": "NYLI Hedge Multi-Strategy Tracker ETF (hold outright)",
        "source_card": "nyli_qai_product_page_2026",
        "universe": ("QAI",),
        "freq": "M",
        "fn": w_f3_qai,
    },
    {
        "id": "F3_TRTY",
        "name": "Cambria Trinity ETF (hold outright)",
        "source_card": "cambria_trty_sec_ncsr_2019",
        "universe": ("TRTY",),
        "freq": "M",
        "fn": w_f3_trty,
    },
]

assert len(SPECS) == 19
assert len({spec["id"] for spec in SPECS}) == 19
