"""T-20260929-12: build the 20 candidate x form books (5 ensembles x
{a, b, bp, c}) from the ensemble scores produced by
``build_h20260929_12_ensembles.py``, and compute Stage 1 results:
diversifier edge vs vol-matched S3, correlation with S3, K1 info, DSR, and
test rank IC.

TWO ALIGNMENT BUGS FOUND AND FIXED (coordinator review, 2026-09-29, voiding
two successive Stage 1 runs before this one):

Bug 1 (forward vs ending open-to-open labeling): ``market.next_open_returns()``
labels row t with the return from open(t) to open(t+1) -- a FORWARD
("starting point") convention -- while an open-to-open ``series.shift(1)``
labels row t with the return ENDING at open(t) -- a BACKWARD convention. The
first run paired a forward-labeled stock leg with backward-labeled hedge
legs directly, a one-session misalignment (voided; see decision-record.md).
That was "fixed" by relabeling everything into a shared open-to-open
convention with a trailing ``shift_rows(net, 1)``.

Bug 2 (open-to-open vs close-to-close, the deeper issue): even after fix 1,
``corr(form a, S3)`` stayed at 0.10-0.18 (below the 0.3 sanity floor). The
coordinator measured directly: ``screen_lane.s3_incumbent`` is NOT an
open-to-open series at all -- ``salvage.legs()``/``salvage.simulate()``
split each rebalance day at the open (old weights earn the overnight gap
``open(t)/close(t-1)-1``, new weights earn the intraday move
``close(t)/open(t)-1``), so row t of S3's own return series is a
CLOSE-TO-CLOSE realized return (close(t-1) -> close(t)), not open(t-1) ->
open(t). Over the Stage 1 window, corr(SPY close-to-close, S3) = 0.58 and
corr(QQQ close-to-close, S3) = 0.70, vs. corr(SPY open-to-open, S3) = 0.23 --
confirming the SECOND fix (below), not any property of S3 itself, was the
actual defect.

FIX (supersedes fix 1's forward/shift approach entirely): every book (a,
b, bp, c) is now built with ``simulate_book``, an exact reimplementation of
``salvage.simulate()``'s own leg-mixing formula (same overnight/intraday
split, applied to the stock panel and to the hedge instrument's existing
``leg_open``/``leg_close`` columns from ``salvage.legs()``, reused
unmodified). Row t of every book's output is therefore realized entirely
within calendar day t (close(t-1) -> close(t)) -- the SAME convention as
``screen_lane.s3_incumbent`` -- so no relabeling/shift step is needed at
all; ``shift_rows`` and the forward/ending helper functions from fix 1 are
removed. ``hedge_weight_series``'s trailing-beta lookback now correctly
INCLUDES the current signal-date row (a close-to-close return realized AT
the close of day i is fully known at that exact moment, unlike fix 1's
forward-labeled return which needed the next day's open).
``tests/test_h20260929_12_hedged_ensemble.py`` adds a regression test that
runs a synthetic single-asset book through both ``simulate_book`` and
``salvage.simulate`` directly and asserts an exact match.

TWO hard sanity checks run before results.json is written and ABORT the run
(nonzero exit, no results.json written) if any fails, over the Stage 1
window, against the close-to-close SPY series: (1) corr(form a, SPY) > 0.5
for every ensemble; (2) realized beta(form b, SPY) in [-0.25, 0.25] for
every ensemble. A third heuristic, corr(form a, S3) > 0.3, was DROPPED
2026-09-29 (coordinator decision; see ``run_sanity_checks``'s docstring and
decision-record.md) -- it was a heuristic for catching misalignment, not a
preregistered criterion, and is no longer needed once alignment is proven
by the two remaining checks plus the ``simulate_book`` vs. frozen
``salvage.simulate`` test. corr(form a, S3) is still computed and reported
as information. ``screen_lane.assert_same_session_convention`` (frozen lane
code, reused via ``diversifier_edge_for_offset``/``correlation_with_s3``)
independently raises if any candidate still looks one session off S3's
convention.

Reuses ``scripts/screen_lane.py`` (``s3_incumbent``, ``combine_two_sleeves``,
``diversifier_edge_for_offset``, ``correlation_with_s3``, ``judged_offset``,
``CASH``, ``RF``, ``COST_BPS_PRIMARY``, ``COST_BPS_STRESS``, ``PANEL_START``),
``run_h20260922_05_salvage`` (``legs``, ``simulate``, ``symbols``),
``run_h20260928_01_s3_rebalance_tranching.shifted_signal_dates``, and
``open_composer.research.signal_card`` (``load_market``, ``rank_ic``,
``ic_summary``) unmodified.

Stage 1 window: 2024-01-02..2026-09-08 (the queue brief's own anchor).

Usage::

    scripts/run_capped.sh --mem 1.8G -- uv run python \\
        scripts/run_h20260929_12_hedged_books.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_h20260918_05_recent_menu as base  # noqa: E402
import run_h20260922_05_salvage as salvage  # noqa: E402
import run_h20260928_01_s3_rebalance_tranching as tranche  # noqa: E402
import screen_lane  # noqa: E402

from open_composer.research.campaign_statistics import deflated_sharpe_probability  # noqa: E402
from open_composer.research.signal_card import (  # noqa: E402
    ic_summary,
    load_market,
    rank_ic,
)

ITER_DIR = ROOT / "reports/research/iterations/h20260929_12_hedged_factor_ensemble"
SCORE_DIR = ITER_DIR / "scores"

ENSEMBLE_IDS = ["E10", "E20", "E40", "E20D", "R40"]
OFFSETS = [0, 5, 10, 15]
TOP_K = 50
MIN_ELIGIBLE = 50
HEDGE_LOOKBACK = 63
HEDGE_BETA_CAP = (0.0, 1.5)
COST_BPS_PRIMARY = screen_lane.COST_BPS_PRIMARY
COST_BPS_STRESS = screen_lane.COST_BPS_STRESS
CASH = screen_lane.CASH
RF = screen_lane.RF
DSR_HAC_LAG = 21
N_TRIALS = 20  # 5 ensembles x 4 forms, matches candidate-manifest.json

STAGE1_WINDOW = ("2024-01-02", "2026-09-08")
STAGE1_PASS_EDGE_MIN = 0.05
STAGE1_PASS_CORR_MAX = 0.30
K1_ANCHOR_SHARPE_MIN = 1.19

HEDGE_PAIRS = {"b": ("SH", "SPY"), "bp": ("PSQ", "QQQ")}

SANITY_CORR_SPY_MIN = 0.5
SANITY_BETA_HEDGED_RANGE = (-0.25, 0.25)
# corr(a,S3) > 0.3 was DROPPED as a hard gate 2026-09-29 (coordinator
# decision) -- see run_sanity_checks' docstring and decision-record.md.


def _log(msg: str, t0: float) -> None:
    print(f"[h20260929_12_books] {msg} ({time.monotonic() - t0:.0f}s)", flush=True)


def load_ensemble_score(eid: str) -> tuple[pd.DatetimeIndex, pd.Index, np.ndarray]:
    npz = np.load(SCORE_DIR / f"{eid}.npz", allow_pickle=True)
    dates = pd.DatetimeIndex(npz["dates"])
    symbols = pd.Index(npz["symbols"])
    score = npz["score"]
    return dates, symbols, score


def load_etf_panel() -> dict:
    """Reuses screen_lane's own PANEL_START/CASH/RF and
    run_h20260922_05_salvage.symbols() (the S3 universe), plus SPY/QQQ/SH/PSQ
    for the hedge legs. Mirrors ``screen_lane.load_batch_panel`` exactly
    (same WARMUP_START assignment, same base.load_panel/salvage.legs calls)
    with the hedge symbols added to the union."""
    symbols = sorted(set(salvage.symbols()) | {CASH, RF, "SPY", "QQQ", "SH", "PSQ"})
    base.WARMUP_START = screen_lane.PANEL_START
    close, open_ = base.load_panel(symbols)
    leg_open, leg_close = salvage.legs(close, open_)
    rf = (close[RF] / close[RF].shift(1) - 1.0).fillna(0.0)
    shy_ret = (close[CASH] / close[CASH].shift(1) - 1.0).fillna(0.0)
    return {
        "close": close,
        "open_": open_,
        "leg_open": leg_open,
        "leg_close": leg_close,
        "rf": rf,
        "shy_ret": shy_ret,
    }


def stock_legs(open_: np.ndarray, close: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Per-stock overnight/intraday legs, the SAME formula as
    ``salvage.legs()`` applied to the (T, N) stock panel instead of the
    ETF-only S3 panel: ``leg_open[t] = open[t]/close[t-1]-1`` (the overnight
    gap ending at open(t)), ``leg_close[t] = close[t]/open[t]-1`` (intraday,
    open(t) to close(t)). Row 0's ``leg_open`` is NaN (no close[-1]) and
    filled to 0 by ``simulate_book``."""
    prev_close = np.empty_like(close)
    prev_close[0] = np.nan
    prev_close[1:] = close[:-1]
    with np.errstate(invalid="ignore", divide="ignore"):
        leg_open = open_ / prev_close - 1.0
        leg_close = close / open_ - 1.0
    return leg_open, leg_close


def simulate_book(
    weights: np.ndarray, leg_open: np.ndarray, leg_close: np.ndarray, cost_bps: float
) -> tuple[np.ndarray, np.ndarray]:
    """Exact reimplementation of ``salvage.simulate()``'s core leg-mixing
    formula, without that function's CASH-column remix (callers fold any
    deleverage/hedge-instrument exposure directly into ``weights`` before
    calling; this is identical to calling ``salvage.simulate()`` with
    ``scale=1`` everywhere -- verified in
    ``test_simulate_book_matches_salvage_simulate_for_single_asset``). On
    day i, the OLD weights (row i-1, held through the close of day i-1)
    earn the overnight gap ``leg_open[i]``, and the (possibly rebalanced)
    NEW weights (row i) earn the intraday move ``leg_close[i]``; turnover
    (and therefore cost) is ``|weights[i]-weights[i-1]|.sum()``, zero on
    non-rebalance days since ``weights[i]==weights[i-1]`` there. Row i of
    the output is therefore realized entirely within calendar day i
    (close(i-1) -> close(i)) -- the SAME convention as
    ``screen_lane.s3_incumbent``, so no further relabeling is needed before
    comparing against S3 or SPY."""
    T, N = weights.shape
    w_prev = np.zeros(N, dtype=np.float64)
    gross = np.zeros(T, dtype=np.float64)
    turnover = np.zeros(T, dtype=np.float64)
    lo_filled = np.where(np.isfinite(leg_open), leg_open, 0.0)
    lc_filled = np.where(np.isfinite(leg_close), leg_close, 0.0)
    for i in range(T):
        w = weights[i]
        gross[i] = float(w_prev @ lo_filled[i] + w @ lc_filled[i])
        turnover[i] = float(np.abs(w - w_prev).sum())
        w_prev = w
    net = gross - turnover * cost_bps / 1e4
    return net, turnover


def build_hedged_book(
    raw_w: np.ndarray,
    stock_leg_open: np.ndarray,
    stock_leg_close: np.ndarray,
    hedge_leg_open: np.ndarray,
    hedge_leg_close: np.ndarray,
    hedge_w: np.ndarray,
    stock_scale: np.ndarray,
    cost_bps: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Builds the combined (stock sub-book scaled by ``stock_scale``) +
    (hedge instrument at weight ``hedge_w``) weight/leg panel and runs it
    through ONE ``simulate_book`` call -- mirroring exactly how S3 itself
    mixes multiple instruments in a single ``salvage.simulate()`` call, so
    the hedge overlay's turnover/cost accounting is on the identical
    convention. ``hedge_leg_open``/``hedge_leg_close`` are 1-D columns
    already produced by ``salvage.legs()`` for the hedge instrument (reused
    unmodified from ``load_etf_panel()``)."""
    T, N = raw_w.shape
    combo_w = np.empty((T, N + 1), dtype=np.float64)
    combo_w[:, :N] = raw_w * stock_scale[:, None]
    combo_w[:, N] = hedge_w
    combo_leg_open = np.empty((T, N + 1), dtype=np.float64)
    combo_leg_open[:, :N] = stock_leg_open
    combo_leg_open[:, N] = hedge_leg_open
    combo_leg_close = np.empty((T, N + 1), dtype=np.float64)
    combo_leg_close[:, :N] = stock_leg_close
    combo_leg_close[:, N] = hedge_leg_close
    return simulate_book(combo_w, combo_leg_open, combo_leg_close, cost_bps)


def build_top50_weights(
    score: np.ndarray, dates: pd.DatetimeIndex, offset: int, top_k: int, min_eligible: int
) -> tuple[np.ndarray, int]:
    """Piecewise-constant top-K equal-weight stock weights, signal observed
    at the close of the offset-shifted month-end date
    (``tranche.shifted_signal_dates``, reused unmodified); the new target
    weight vector takes effect starting the NEXT session (row i+1), which
    ``simulate_book`` interprets as: old weights (row i) earn that session's
    overnight gap, new weights (row i+1) earn that session's intraday move
    -- i.e. a next-open fill, exactly as the lane's own tranche/salvage
    engines execute rebalances. A month with fewer than ``min_eligible``
    finite scores is skipped (zero stock exposure that month) rather than
    picking a smaller-than-intended book -- the candidate-manifest's
    declared fallback."""
    sig_dates = tranche.shifted_signal_dates(dates, offset)
    pos = {d: i for i, d in enumerate(dates)}
    T, N = score.shape
    next_change: dict[int, np.ndarray] = {}
    skipped = 0
    for d in sig_dates:
        i = pos.get(d)
        if i is None or i + 1 >= T:
            continue
        row = score[i]
        eligible = np.isfinite(row)
        n_elig = int(eligible.sum())
        if n_elig < min_eligible:
            skipped += 1
            next_change[i + 1] = np.zeros(N, dtype=np.float32)
            continue
        k = min(top_k, n_elig)
        masked = np.where(eligible, row, -np.inf)
        idx = np.argpartition(-masked, k - 1)[:k]
        w = np.zeros(N, dtype=np.float32)
        w[idx] = 1.0 / k
        next_change[i + 1] = w
    weights = np.zeros((T, N), dtype=np.float32)
    current = np.zeros(N, dtype=np.float32)
    for i in range(T):
        if i in next_change:
            current = next_change[i]
        weights[i] = current
    return weights, skipped


def hedge_weight_series(
    stock_ret_cc: np.ndarray,
    underlying_ret_cc: np.ndarray,
    dates: pd.DatetimeIndex,
    sig_dates: list[pd.Timestamp],
    lookback: int,
    cap: tuple[float, float],
) -> tuple[np.ndarray, np.ndarray]:
    """(hedge_weight, stock_scale) piecewise-constant series, effective
    starting the session after each signal date (mirrors
    ``build_top50_weights``). Both input series MUST already be
    close-to-close labeled (row t = the return realized BY the close of day
    t, i.e. ``simulate_book``'s own output convention, matching
    ``screen_lane``/S3): at the moment a signal is observed at the close of
    day i, row i's return is realized AT that exact close and may safely be
    included in the trailing lookback -- rows [i-lookback+1, i] inclusive
    (unlike a forward-labeled return, which would need information not yet
    available). hedge_weight = beta/(1+beta), stock_scale = 1/(1+beta),
    beta capped to ``cap``."""
    pos = {d: i for i, d in enumerate(dates)}
    T = len(dates)
    hedge_w = np.zeros(T, dtype=np.float64)
    stock_scale = np.ones(T, dtype=np.float64)
    current_hedge, current_scale = 0.0, 1.0
    next_change: dict[int, tuple[float, float]] = {}
    for d in sig_dates:
        i = pos.get(d)
        if i is None or i + 1 >= T:
            continue
        lo = max(0, i - lookback + 1)
        s = stock_ret_cc[lo : i + 1]
        m = underlying_ret_cc[lo : i + 1]
        finite = np.isfinite(s) & np.isfinite(m)
        s, m = s[finite], m[finite]
        if len(s) < lookback // 2:
            beta = 0.0
        else:
            var_m = float(np.var(m, ddof=1))
            beta = float(np.cov(s, m, ddof=1)[0, 1] / var_m) if var_m > 0 else 0.0
        beta = float(np.clip(beta, cap[0], cap[1]))
        next_change[i + 1] = (beta / (1.0 + beta), 1.0 / (1.0 + beta))
    for i in range(T):
        if i in next_change:
            current_hedge, current_scale = next_change[i]
        hedge_w[i] = current_hedge
        stock_scale[i] = current_scale
    return hedge_w, stock_scale


def spread_return(
    score: np.ndarray,
    dates: pd.DatetimeIndex,
    leg_open: np.ndarray,
    leg_close: np.ndarray,
    offset: int,
    cost_bps: float,
) -> tuple[np.ndarray, np.ndarray]:
    """INFO ONLY form (c): top-decile minus bottom-decile equal-weight
    spread, both legs costed, borrow costs NOT modeled (flagged in
    report.md). Signal/fill timing identical to ``build_top50_weights``;
    run through ``simulate_book`` on the stock legs so it lands on the SAME
    close-to-close convention as forms a/b/bp and S3."""
    sig_dates = tranche.shifted_signal_dates(dates, offset)
    pos = {d: i for i, d in enumerate(dates)}
    T, N = score.shape
    next_change: dict[int, np.ndarray] = {}
    for d in sig_dates:
        i = pos.get(d)
        if i is None or i + 1 >= T:
            continue
        row = score[i]
        eligible = np.isfinite(row)
        n_elig = int(eligible.sum())
        if n_elig < MIN_ELIGIBLE:
            next_change[i + 1] = np.zeros(N, dtype=np.float32)
            continue
        decile = max(1, n_elig // 10)
        order = np.argsort(np.where(eligible, row, np.nan))
        valid_order = [j for j in order if eligible[j]]
        bottom = valid_order[:decile]
        top = valid_order[-decile:]
        w = np.zeros(N, dtype=np.float32)
        w[top] = 1.0 / decile
        w[bottom] = -1.0 / decile
        next_change[i + 1] = w
    weights = np.zeros((T, N), dtype=np.float64)
    current = np.zeros(N, dtype=np.float64)
    for i in range(T):
        if i in next_change:
            current = next_change[i]
        weights[i] = current
    return simulate_book(weights, leg_open, leg_close, cost_bps)


def window_metrics(ret: pd.Series, rf: pd.Series, turnover: pd.Series, window: tuple[str, str]):
    a, b = pd.Timestamp(window[0]), pd.Timestamp(window[1])
    mask = (ret.index >= a) & (ret.index <= b)
    return base.metrics(
        ret.loc[mask], rf.reindex(ret.index).fillna(0.0).loc[mask], turnover.loc[mask]
    )


def window_corr(x: pd.Series, y: pd.Series, window: tuple[str, str]) -> float:
    a, b = pd.Timestamp(window[0]), pd.Timestamp(window[1])
    idx = x.index.intersection(y.index)
    idx = idx[(idx >= a) & (idx <= b)]
    sub = pd.DataFrame({"x": x.loc[idx], "y": y.loc[idx]}).dropna()
    if len(sub) < 30 or sub["x"].std() == 0 or sub["y"].std() == 0:
        return float("nan")
    return float(sub["x"].corr(sub["y"]))


def window_beta(x: pd.Series, y: pd.Series, window: tuple[str, str]) -> float:
    """beta of x on y (x = a*y + resid): cov(x,y)/var(y)."""
    a, b = pd.Timestamp(window[0]), pd.Timestamp(window[1])
    idx = x.index.intersection(y.index)
    idx = idx[(idx >= a) & (idx <= b)]
    sub = pd.DataFrame({"x": x.loc[idx], "y": y.loc[idx]}).dropna()
    if len(sub) < 30:
        return float("nan")
    var_y = float(sub["y"].var(ddof=1))
    if var_y <= 0:
        return float("nan")
    cov_xy = float(sub["x"].cov(sub["y"]))
    return cov_xy / var_y


def run_sanity_checks(
    form_a: dict[str, pd.Series],
    form_b: dict[str, pd.Series],
    spy_cc: pd.Series,
    qqq_cc: pd.Series,
    s3_ret10: pd.Series,
    window: tuple[str, str],
) -> dict:
    """Aborts (raises SystemExit) if any ensemble's form (a)/(b) fails the
    TWO remaining hard checks (corr(a,SPY_cc)>0.5, beta(b,SPY_cc) in
    [-0.25,0.25]), measured on the close-to-close convention. The third
    heuristic check from the first rerun, corr(a,S3)>0.3, was DROPPED
    2026-09-29 (coordinator decision, see decision-record.md): it was a
    heuristic for catching misalignment, not a preregistered criterion, and
    alignment is now proven three independent ways (simulate_book matches
    the frozen salvage.simulate/.legs in tests; corr(a,SPY_cc) and
    beta(b,SPY_cc) both pass cleanly; corr(SPY_cc,S3)/corr(QQQ_cc,S3) match
    the coordinator's own independent measurement). corr(a,S3) is still
    computed and reported below as information (it is feasible for it to be
    low even with correct alignment, given corr(a,SPY_cc)~0.78 and
    corr(SPY_cc,S3)~0.58 alone bound it only to roughly [-0.06, 0.96]).
    ``screen_lane.diversifier_edge_for_offset``/``correlation_with_s3``
    (called later in ``main()`` for every form) also independently call
    ``screen_lane.assert_same_session_convention``, which raises if a
    candidate's returns still look one session off S3's -- that exception
    is intentionally left unhandled so the run stops and reports it."""
    report: dict[str, dict] = {}
    failures: list[str] = []
    for eid in ENSEMBLE_IDS:
        corr_a_spy = window_corr(form_a[eid], spy_cc, window)
        corr_a_s3 = window_corr(form_a[eid], s3_ret10, window)
        beta_b_spy = window_beta(form_b[eid], spy_cc, window)
        report[eid] = {
            "corr_a_spy_cc": corr_a_spy,
            "corr_a_s3_info_only": corr_a_s3,
            "beta_b_spy_cc": beta_b_spy,
        }
        if not (np.isfinite(corr_a_spy) and corr_a_spy > SANITY_CORR_SPY_MIN):
            failures.append(f"{eid}: corr(a,SPY_cc)={corr_a_spy:.4f} <= {SANITY_CORR_SPY_MIN}")
        lo, hi = SANITY_BETA_HEDGED_RANGE
        if not (np.isfinite(beta_b_spy) and lo <= beta_b_spy <= hi):
            failures.append(f"{eid}: beta(b,SPY_cc)={beta_b_spy:.4f} outside [{lo},{hi}]")
    print(f"[sanity] full report (all ensembles, pass or fail): {report}", flush=True)
    corr_spy_s3 = window_corr(spy_cc, s3_ret10, window)
    corr_qqq_s3 = window_corr(qqq_cc, s3_ret10, window)
    print(
        f"[sanity] diagnostic corr(SPY_cc, S3) over {window} = {corr_spy_s3:.4f}, "
        f"corr(QQQ_cc, S3) = {corr_qqq_s3:.4f}",
        flush=True,
    )
    if failures:
        msg = "SANITY CHECK FAILURE (alignment likely still broken):\n" + "\n".join(failures)
        print(msg, flush=True)
        raise SystemExit(msg)
    return report


def main() -> int:
    t0 = time.monotonic()
    market = load_market(top_n=1000, memory_limit="1200MB")
    _log(f"market loaded: {len(market.dates)} x {len(market.symbols)}", t0)
    fwd21 = market.forward_returns(21)
    member = market.member()

    panel = load_etf_panel()
    close = panel["close"]
    leg_open, leg_close = panel["leg_open"], panel["leg_close"]
    rf, shy_ret = panel["rf"], panel["shy_ret"]
    _log("ETF panel loaded", t0)

    s3_ret10, _s3_turn10 = screen_lane.s3_incumbent(close, leg_open, leg_close, COST_BPS_PRIMARY)
    _log("S3 incumbent computed", t0)

    unified_index = market.dates.intersection(close.index)
    overlap_frac = len(unified_index) / max(len(market.dates), 1)
    _log(f"unified_index len={len(unified_index)} overlap_frac={overlap_frac:.4f}", t0)

    stock_pos = market.dates.get_indexer(unified_index)
    mkt_open_u = market.open_[stock_pos].astype(np.float64)
    mkt_close_u = market.close[stock_pos].astype(np.float64)
    stock_leg_open_u, stock_leg_close_u = stock_legs(mkt_open_u, mkt_close_u)
    _log("stock legs (close-to-close convention) built", t0)

    spy_cc = (close["SPY"] / close["SPY"].shift(1) - 1.0).reindex(unified_index)
    qqq_cc = (close["QQQ"] / close["QQQ"].shift(1) - 1.0).reindex(unified_index)
    underlying_ret_cc = {"SPY": spy_cc, "QQQ": qqq_cc}
    hedge_leg_open_map = {
        sym: leg_open[sym].reindex(unified_index).to_numpy() for sym in ("SH", "PSQ")
    }
    hedge_leg_close_map = {
        sym: leg_close[sym].reindex(unified_index).to_numpy() for sym in ("SH", "PSQ")
    }

    results: dict[str, object] = {}
    all_series: dict[str, dict] = {}
    form_a_by_eid: dict[str, pd.Series] = {}
    form_b_by_eid: dict[str, pd.Series] = {}

    for eid in ENSEMBLE_IDS:
        e_dates, e_symbols, score = load_ensemble_score(eid)
        if not e_dates.equals(market.dates) or not e_symbols.equals(market.symbols):
            raise RuntimeError(f"{eid}: score dates/symbols do not match freshly loaded Market")
        score_u = score[stock_pos]
        _log(f"{eid}: score aligned to unified index", t0)

        # ---- form (a): long-only, close-to-close via simulate_book ----
        a_net10_by_offset: dict[int, np.ndarray] = {}
        a_net20_by_offset: dict[int, np.ndarray] = {}
        skipped_by_offset: dict[int, int] = {}
        raw_weights_by_offset: dict[int, np.ndarray] = {}
        for off in OFFSETS:
            raw_w, skipped = build_top50_weights(score_u, unified_index, off, TOP_K, MIN_ELIGIBLE)
            raw_w64 = raw_w.astype(np.float64)
            raw_weights_by_offset[off] = raw_w64
            skipped_by_offset[off] = skipped
            net10, _t10 = simulate_book(
                raw_w64, stock_leg_open_u, stock_leg_close_u, COST_BPS_PRIMARY
            )
            net20, _t20 = simulate_book(
                raw_w64, stock_leg_open_u, stock_leg_close_u, COST_BPS_STRESS
            )
            a_net10_by_offset[off] = net10
            a_net20_by_offset[off] = net20

        # ---- forms (b)/(bp): hedged, close-to-close via build_hedged_book ----
        hedged_net10_by_form_offset: dict[str, dict[int, np.ndarray]] = {"b": {}, "bp": {}}
        for form, (hsym, usym) in HEDGE_PAIRS.items():
            u_ret = underlying_ret_cc[usym].to_numpy()
            h_leg_open = hedge_leg_open_map[hsym]
            h_leg_close = hedge_leg_close_map[hsym]
            for off in OFFSETS:
                raw_w64 = raw_weights_by_offset[off]
                a_net10 = a_net10_by_offset[off]  # close-to-close beta input
                sig_dates = tranche.shifted_signal_dates(unified_index, off)
                hedge_w, stock_scale = hedge_weight_series(
                    a_net10, u_ret, unified_index, sig_dates, HEDGE_LOOKBACK, HEDGE_BETA_CAP
                )
                net10, _turn = build_hedged_book(
                    raw_w64,
                    stock_leg_open_u,
                    stock_leg_close_u,
                    h_leg_open,
                    h_leg_close,
                    hedge_w,
                    stock_scale,
                    COST_BPS_PRIMARY,
                )
                hedged_net10_by_form_offset[form][off] = net10

        # ---- form (c): info-only spread, close-to-close via simulate_book ----
        c_net10_by_offset = {
            off: spread_return(
                score_u, unified_index, stock_leg_open_u, stock_leg_close_u, off, COST_BPS_PRIMARY
            )[0]
            for off in OFFSETS
        }

        all_series[eid] = {
            "a": a_net10_by_offset,
            "b": hedged_net10_by_form_offset["b"],
            "bp": hedged_net10_by_form_offset["bp"],
            "c": c_net10_by_offset,
            "skipped_by_offset": skipped_by_offset,
        }
        form_a_by_eid[eid] = pd.Series(a_net10_by_offset[0], index=unified_index)
        form_b_by_eid[eid] = pd.Series(hedged_net10_by_form_offset["b"][0], index=unified_index)
        _log(f"{eid}: all forms computed", t0)

        # ---- test rank IC (reused signal_card.rank_ic/ic_summary) ----
        ic = rank_ic(score, fwd21, member)
        stage1_mask = (market.dates >= pd.Timestamp(STAGE1_WINDOW[0])) & (
            market.dates <= pd.Timestamp(STAGE1_WINDOW[1])
        )
        ic_stage1 = ic_summary(ic[stage1_mask], market.dates[stage1_mask], 21)

        cell: dict[str, object] = {"test_rank_ic": ic_stage1}
        for form in ["a", "b", "bp", "c"]:
            net_by_offset = all_series[eid][form]
            edge_by_offset = {}
            corr_by_offset = {}
            sharpe_by_offset = {}
            for off, net in net_by_offset.items():
                s = pd.Series(net, index=unified_index)
                m = window_metrics(s, rf, pd.Series(0.0, index=unified_index), STAGE1_WINDOW)
                sharpe_by_offset[off] = m.sharpe
                if form in ("b", "bp"):
                    edge_by_offset[off] = screen_lane.diversifier_edge_for_offset(
                        s3_ret10, s, shy_ret, rf, STAGE1_WINDOW
                    )
                corr_by_offset[off] = screen_lane.correlation_with_s3(s, s3_ret10, STAGE1_WINDOW)
            judged_off = screen_lane.judged_offset(sharpe_by_offset)
            judged_series = pd.Series(net_by_offset[judged_off], index=unified_index)
            judged_m = window_metrics(
                judged_series, rf, pd.Series(0.0, index=unified_index), STAGE1_WINDOW
            )
            a1, b1 = pd.Timestamp(STAGE1_WINDOW[0]), pd.Timestamp(STAGE1_WINDOW[1])
            mask = (judged_series.index >= a1) & (judged_series.index <= b1)
            excess = (
                (judged_series.loc[mask] - rf.reindex(judged_series.index).fillna(0.0).loc[mask])
                .dropna()
                .to_numpy()
            )
            dsr = None
            if (
                len(excess) > max(DSR_HAC_LAG, 3)
                and np.isfinite(excess).all()
                and np.std(excess) > 0
            ):
                try:
                    dsr = float(
                        deflated_sharpe_probability(
                            excess, trial_count=N_TRIALS, hac_lag=DSR_HAC_LAG
                        )
                    )
                except ValueError:
                    dsr = None
            cell[form] = {
                "sharpe_by_offset": sharpe_by_offset,
                "sharpe_median": float(np.median(list(sharpe_by_offset.values()))),
                "judged_offset": judged_off,
                "judged_sharpe": judged_m.sharpe,
                "judged_cagr": judged_m.cagr,
                "judged_max_dd": judged_m.max_dd,
                "correlation_with_s3_by_offset": corr_by_offset,
                "correlation_with_s3_median": float(np.nanmedian(list(corr_by_offset.values()))),
                "dsr_anchor": dsr,
            }
            if form in ("b", "bp"):
                cell[form]["edge_by_offset"] = edge_by_offset
                cell[form]["edge_median"] = float(np.median(list(edge_by_offset.values())))
            if form == "a":
                cell[form]["k1_pass_anchor"] = bool(
                    cell[form]["sharpe_median"] >= K1_ANCHOR_SHARPE_MIN
                )
        results[eid] = cell
        _log(f"{eid}: metrics computed", t0)

    # ---- hard sanity checks (abort if alignment is still broken) ----
    sanity_report = run_sanity_checks(
        form_a_by_eid, form_b_by_eid, spy_cc, qqq_cc, s3_ret10, STAGE1_WINDOW
    )
    _log(f"sanity checks passed: {sanity_report}", t0)

    # ---- Stage 1 verdict ----
    stage1_candidates = []
    for eid in ENSEMBLE_IDS:
        for form in ("b", "bp"):
            c = results[eid][form]
            edge = c["edge_median"]
            sharpe = c["judged_sharpe"]
            corr = c["correlation_with_s3_median"]
            passed = bool(
                edge is not None
                and edge >= STAGE1_PASS_EDGE_MIN
                and sharpe is not None
                and sharpe > 0
                and corr is not None
                and corr < STAGE1_PASS_CORR_MAX
            )
            stage1_candidates.append(
                {
                    "ensemble": eid,
                    "form": form,
                    "edge_median": edge,
                    "standalone_sharpe": sharpe,
                    "correlation_with_s3": corr,
                    "passed": passed,
                }
            )
    stage1_pass = any(c["passed"] for c in stage1_candidates)

    payload = {
        "generated_at": pd.Timestamp.utcnow().isoformat(),
        "stage1_window": list(STAGE1_WINDOW),
        "offsets": OFFSETS,
        "n_trials_dsr": N_TRIALS,
        "unified_index_overlap_frac": overlap_frac,
        "sanity_checks": sanity_report,
        "results": results,
        "stage1_candidates": stage1_candidates,
        "stage1_pass": stage1_pass,
        "skipped_months_by_ensemble": {
            eid: all_series[eid]["skipped_by_offset"] for eid in ENSEMBLE_IDS
        },
    }
    out_path = ITER_DIR / "results.json"
    out_path.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    _log(f"wrote {out_path}, stage1_pass={stage1_pass}", t0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
