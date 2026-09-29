"""T-20260929-51 step 1: beta-hedged ETF short spreads ("short small caps, long
beta * SPY") under the frozen screen_lane contract, with an explicit borrow fee.

`scripts/screen_lane.py` cannot be used directly: `weights_frame` keeps only
weights > 0 and asserts long-only, so a short book would silently become 100%
SHY. This script therefore reuses the lane's frozen pieces unedited -- panel
loader (`base.load_panel`), `salvage.legs`/`salvage.simulate` (which do use
signed weights: gross = sum(w * ret), turnover = sum|w - w_prev|), the
signal-date/offset convention (`screen_lane.signal_dates`), `screen_lane.WINDOWS`,
the metrics (`base.metrics`), the diversifier test and DSR -- and only adds the
signed weight builder and the borrow-fee deduction.

Book convention (preregistered in candidate-manifest.json): a cash-financed
overlay. Short 1.0 of X, long beta * SPY (beta = trailing OLS beta of X on SPY
daily close-to-close returns, known at the signal close), effective at the next
open; SHY weight 0. Reported Sharpe is the Sharpe of the overlay return itself,
i.e. of the excess return over a collateral that earns the T-bill rate (interest
on short proceeds is neither credited nor charged beyond the borrow fee).
Borrow fee per day = sum of |short weights| * annual_rate / 252, charged on
every session the position is held.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import screen_lane as lane  # noqa: E402

from open_composer.research.campaign_statistics import deflated_sharpe_probability  # noqa: E402

base = lane.base
salvage = lane.salvage

ITER_ID = "h20260929_51_small_cap_short_drift"
OUT_DIR = ROOT / "reports/research/iterations" / ITER_ID
BENCH = "SPY"
BORROW_ETF_ANNUAL = 0.005  # ETB index ETFs, preregistered
K1_ANCHOR, K1_STRESS = 1.1882, 0.6447  # 0.8 x S3 median-offset Sharpe (runbook section 5)
K2_EDGE_MIN = 0.05
STEP2_GATE = 0.6  # anchor median Sharpe after borrow, T-20260929-51 plan
N_TRIALS = 9  # 8 candidates + 1 mirror placebo (step 2 would add to this)


@dataclass(frozen=True)
class SpreadCandidate:
    id: str
    short: str
    freq: str  # "M" or "W"
    beta_window: int | None  # None = unhedged pure short
    mirror: bool = False  # placebo: long X, short beta * SPY
    borrow_annual: float = BORROW_ETF_ANNUAL


CANDIDATES: list[SpreadCandidate] = [
    SpreadCandidate("SSD_IWM_M252", "IWM", "M", 252),
    SpreadCandidate("SSD_RSP_M252", "RSP", "M", 252),
    SpreadCandidate("SSD_IJR_M252", "IJR", "M", 252),
    SpreadCandidate("SSD_XRT_M252", "XRT", "M", 252),
    SpreadCandidate("SSD_KRE_M252", "KRE", "M", 252),
    SpreadCandidate("SSD_IWM_W252", "IWM", "W", 252),
    SpreadCandidate("SSD_IWM_M63", "IWM", "M", 63),
    SpreadCandidate("SSD_IWM_M_NOHEDGE", "IWM", "M", None),
    SpreadCandidate("SSD_PLACEBO_LONG_IWM_M252", "IWM", "M", 252, mirror=True),
]
PLACEBO_ID = "SSD_PLACEBO_LONG_IWM_M252"


def trailing_beta(close: pd.DataFrame, x: str, asof: pd.Timestamp, window: int) -> float:
    """OLS beta of x on SPY over the `window` daily returns ending at `asof`
    (close-to-close, known at the signal close). NaN if history is short."""
    hist = close[[x, BENCH]].loc[:asof].iloc[-(window + 1) :]
    rets = hist.pct_change().dropna()
    if len(rets) < window:
        return float("nan")
    var = float(rets[BENCH].var(ddof=1))
    if not np.isfinite(var) or var <= 0:
        return float("nan")
    return float(rets[x].cov(rets[BENCH]) / var)


def target_weights(
    close: pd.DataFrame, cand: SpreadCandidate, asof: pd.Timestamp
) -> dict[str, float]:
    sign = 1.0 if cand.mirror else -1.0
    book = {cand.short: sign}
    if cand.beta_window is not None:
        beta = trailing_beta(close, cand.short, asof, cand.beta_window)
        if not np.isfinite(beta):
            return {}
        book[BENCH] = -sign * beta
    return book


def weights_frame(
    close: pd.DataFrame, cand: SpreadCandidate, offset: int
) -> tuple[pd.DataFrame, list[pd.Timestamp]]:
    """Signed target weights, effective at the OPEN of the session after each
    signal date (same piecewise-constant convention as `screen_lane`), SHY 0."""
    cols = sorted({cand.short, BENCH, lane.CASH})
    dates = lane.signal_dates(close.index, cand.freq, offset)
    pos = {d: i for i, d in enumerate(close.index)}
    next_change: dict[int, dict[str, float]] = {}
    for d in dates:
        i = pos[d]
        if i + 1 >= len(close.index):
            continue
        book = target_weights(close, cand, d)
        if book:
            next_change[i + 1] = book
    rows: list[dict[str, float]] = []
    current: dict[str, float] = {}
    for i in range(len(close.index)):
        if i in next_change:
            current = next_change[i]
        rows.append(dict(current))
    frame = pd.DataFrame(rows, index=close.index).reindex(columns=cols).fillna(0.0)
    return frame, dates


def borrow_cost(weights: pd.DataFrame, annual_rate: float) -> pd.Series:
    short_abs = (-weights.where(weights < 0, 0.0)).sum(axis=1)
    return short_abs * annual_rate / 252.0


def first_valid_date(weights: pd.DataFrame) -> pd.Timestamp:
    active = (weights.drop(columns=[lane.CASH]).abs().sum(axis=1) > 0).to_numpy()
    idx = int(np.argmax(active)) if active.any() else len(weights) - 1
    return weights.index[idx]


def simulate_overlay(
    weights: pd.DataFrame,
    leg_open: pd.DataFrame,
    leg_close: pd.DataFrame,
    cost_bps: float,
    borrow_annual: float,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """(gross-of-borrow net-of-trade-cost return, after-borrow return, turnover)."""
    ret, turn = salvage.simulate(weights, leg_open, leg_close, np.ones(len(weights)), cost_bps)
    after = ret - borrow_cost(weights, borrow_annual)
    return ret, after, turn


def window_metrics(
    ret: pd.Series, turn: pd.Series, window: tuple[str, str], first_valid: pd.Timestamp
) -> dict[str, float]:
    start = lane.window_actual_start(window[0], first_valid)
    mask = (ret.index >= start) & (ret.index <= pd.Timestamp(window[1]))
    zero = pd.Series(0.0, index=ret.index)
    m = base.metrics(ret.loc[mask], zero, turn.loc[mask])
    return {
        "days": m.days,
        "cagr": m.cagr,
        "vol": m.vol,
        "sharpe": m.sharpe,
        "max_dd": m.max_dd,
        "turnover_yr": m.turnover_yr,
        "actual_start": str(start.date()),
    }


def med(values: list[float]) -> float:
    return float(np.median(np.array(values, dtype=float)))


def monthly_beta_adjusted_drift(
    close: pd.DataFrame, cand: SpreadCandidate, window: tuple[str, str]
) -> float | None:
    """Mean monthly return of X minus beta_252 * SPY (calendar months, beta known
    at the prior month end) inside the window, in percent -- the paper's
    'background drift' metric, for comparison with -0.92%/month."""
    if cand.beta_window is None or cand.mirror:
        return None
    rets = close[[cand.short, BENCH]].pct_change()
    month_end = close.index.to_series().groupby(close.index.to_period("M")).max()
    vals = []
    prev = None
    for d in month_end.to_list():
        if prev is not None and pd.Timestamp(window[0]) <= d <= pd.Timestamp(window[1]):
            beta = trailing_beta(close, cand.short, prev, cand.beta_window)
            seg = rets.loc[(rets.index > prev) & (rets.index <= d)]
            if np.isfinite(beta) and len(seg):
                x = float((1 + seg[cand.short]).prod() - 1)
                s = float((1 + seg[BENCH]).prod() - 1)
                vals.append(x - beta * s)
        prev = d
    return float(np.mean(vals) * 100.0) if vals else None


def evaluate(
    cand: SpreadCandidate,
    close: pd.DataFrame,
    leg_open: pd.DataFrame,
    leg_close: pd.DataFrame,
    rf: pd.Series,
    shy_ret: pd.Series,
    s3_ret10: pd.Series,
) -> dict[str, object]:
    offsets = lane.offsets_for_freq(cand.freq)
    per: dict[int, dict[str, dict[str, object]]] = {}
    ret_after10: dict[int, pd.Series] = {}
    first_valid = None
    for off in offsets:
        w, _ = weights_frame(close, cand, off)
        fv = first_valid_date(w)
        first_valid = fv if first_valid is None else max(first_valid, fv)
    assert first_valid is not None
    for off in offsets:
        w, _ = weights_frame(close, cand, off)
        g10, a10, t10 = simulate_overlay(
            w, leg_open, leg_close, lane.COST_BPS_PRIMARY, cand.borrow_annual
        )
        _g20, a20, t20 = simulate_overlay(
            w, leg_open, leg_close, lane.COST_BPS_STRESS, cand.borrow_annual
        )
        ret_after10[off] = a10
        per[off] = {}
        for wname, window in lane.WINDOWS.items():
            per[off][wname] = {
                "before_borrow_10bp": window_metrics(g10, t10, window, first_valid),
                "after_borrow_10bp": window_metrics(a10, t10, window, first_valid),
                "after_borrow_20bp": window_metrics(a20, t20, window, first_valid),
            }
    summary: dict[str, dict[str, object]] = {}
    for wname in lane.WINDOWS:
        sh_before = [per[o][wname]["before_borrow_10bp"]["sharpe"] for o in offsets]
        sh_after = [per[o][wname]["after_borrow_10bp"]["sharpe"] for o in offsets]
        sh_20 = [per[o][wname]["after_borrow_20bp"]["sharpe"] for o in offsets]
        cagr_20 = [per[o][wname]["after_borrow_20bp"]["cagr"] for o in offsets]
        cagr_10 = [per[o][wname]["after_borrow_10bp"]["cagr"] for o in offsets]
        dd = [per[o][wname]["after_borrow_10bp"]["max_dd"] for o in offsets]
        summary[wname] = {
            "median_sharpe_before_borrow_10bp": med(sh_before),
            "median_sharpe_after_borrow_10bp": med(sh_after),
            "min_sharpe_after_borrow_10bp": float(np.min(sh_after)),
            "max_sharpe_after_borrow_10bp": float(np.max(sh_after)),
            "median_sharpe_after_borrow_20bp": med(sh_20),
            "median_cagr_after_borrow_10bp": med(cagr_10),
            "median_cagr_after_borrow_20bp": med(cagr_20),
            "median_max_dd_after_borrow_10bp": med(dd),
            "actual_start": per[offsets[0]][wname]["after_borrow_10bp"]["actual_start"],
        }
    sharpe_by_off = {o: per[o]["anchor"]["after_borrow_10bp"]["sharpe"] for o in offsets}
    judged = lane.judged_offset(sharpe_by_off)
    # K2: sleeve = overlay + T-bill collateral, so it is comparable with S3's total return
    edges: dict[str, dict[str, float]] = {}
    for wname in ("anchor", "stress"):
        by_off = {
            o: lane.diversifier_edge_for_offset(
                s3_ret10,
                ret_after10[o] + rf.reindex(ret_after10[o].index).fillna(0.0),
                shy_ret,
                rf,
                lane.WINDOWS[wname],
            )
            for o in offsets
        }
        edges[wname] = {
            "median": float(np.median(list(by_off.values()))),
            "min": float(min(by_off.values())),
        }
    a_start = lane.window_actual_start(lane.WINDOWS["anchor"][0], first_valid)
    jr = ret_after10[judged]
    mask = (jr.index >= a_start) & (jr.index <= pd.Timestamp(lane.WINDOWS["anchor"][1]))
    try:
        dsr = float(
            deflated_sharpe_probability(
                jr.loc[mask].to_numpy(), trial_count=N_TRIALS, hac_lag=lane.DSR_HAC_LAG
            )
        )
    except ValueError:
        dsr = None
    anc, stress = summary["anchor"], summary["stress"]
    k1 = bool(
        anc["median_sharpe_after_borrow_10bp"] >= K1_ANCHOR
        and stress["median_sharpe_after_borrow_10bp"] >= K1_STRESS
        and anc["median_cagr_after_borrow_20bp"] > 0
        and stress["median_cagr_after_borrow_20bp"] > 0
    )
    k2 = bool(edges["anchor"]["median"] >= K2_EDGE_MIN and edges["stress"]["median"] >= K2_EDGE_MIN)
    watch = bool(anc["median_sharpe_after_borrow_10bp"] >= K1_ANCHOR and not k1)
    if cand.mirror:
        tier = "placebo"
    elif k1 or k2:
        tier = "keep"
    elif watch:
        tier = "watch_recent"
    else:
        tier = "reject"
    return {
        "id": cand.id,
        "short": cand.short,
        "freq": cand.freq,
        "beta_window": cand.beta_window,
        "mirror_placebo": cand.mirror,
        "borrow_annual": cand.borrow_annual,
        "n_offsets": len(offsets),
        "first_valid_signal_effective": str(first_valid.date()),
        "windows": summary,
        "judged_anchor_offset": judged,
        "k2_edge_vs_s3": edges,
        "k1": k1,
        "k2": k2,
        "tier": tier,
        "dsr_anchor_after_borrow": dsr,
        "n_trials": N_TRIALS,
        "anchor_monthly_beta_adjusted_drift_pct": monthly_beta_adjusted_drift(
            close, cand, lane.WINDOWS["anchor"]
        ),
        "stress_monthly_beta_adjusted_drift_pct": monthly_beta_adjusted_drift(
            close, cand, lane.WINDOWS["stress"]
        ),
        "per_offset": {str(o): per[o] for o in offsets},
    }


def load_step1_panel() -> tuple[pd.DataFrame, pd.DataFrame]:
    base.WARMUP_START = lane.PANEL_START
    symbols = sorted(
        set(salvage.symbols()) | {lane.CASH, lane.RF, BENCH} | {c.short for c in CANDIDATES}
    )
    return base.load_panel(symbols)


def main() -> int:
    close, open_ = load_step1_panel()
    missing = sorted({c.short for c in CANDIDATES} - set(close.columns))
    if missing:
        raise SystemExit(f"missing from panel: {missing}")
    leg_open, leg_close = salvage.legs(close, open_)
    rf = (close[lane.RF] / close[lane.RF].shift(1) - 1.0).fillna(0.0)
    shy_ret = (close[lane.CASH] / close[lane.CASH].shift(1) - 1.0).fillna(0.0)
    s3_ret10, _ = lane.s3_incumbent(close, leg_open, leg_close, lane.COST_BPS_PRIMARY)
    rows = []
    for cand in CANDIDATES:
        rows.append(evaluate(cand, close, leg_open, leg_close, rf, shy_ret, s3_ret10))
        a = rows[-1]["windows"]["anchor"]
        s = rows[-1]["windows"]["stress"]
        b0, b1 = a["median_sharpe_before_borrow_10bp"], a["median_sharpe_after_borrow_10bp"]
        c0, c1 = s["median_sharpe_before_borrow_10bp"], s["median_sharpe_after_borrow_10bp"]
        tier = rows[-1]["tier"]
        print(
            f"{cand.id}: anchor {b0:.3f}->{b1:.3f} stress {c0:.3f}->{c1:.3f} tier {tier}",
            flush=True,
        )
    iwm = next(r for r in rows if r["id"] == "SSD_IWM_M252")
    anchor_iwm = iwm["windows"]["anchor"]["median_sharpe_after_borrow_10bp"]
    placebo = next(r for r in rows if r["id"] == PLACEBO_ID)
    out = {
        "iter_id": ITER_ID,
        "generated_at": datetime.now(UTC).isoformat(),
        "step": 1,
        "contract": {
            "windows": lane.WINDOWS,
            "cost_bps_primary": lane.COST_BPS_PRIMARY,
            "cost_bps_stress": lane.COST_BPS_STRESS,
            "borrow_annual_etf": BORROW_ETF_ANNUAL,
            "k1_anchor": K1_ANCHOR,
            "k1_stress": K1_STRESS,
            "k2_edge_min": K2_EDGE_MIN,
            "step2_gate_anchor_median_sharpe_after_borrow": STEP2_GATE,
            "sharpe_convention": (
                "Sharpe of the cash-financed long/short overlay return (collateral interest "
                "excluded), median over all rebalance offsets (21 monthly, 5 weekly)"
            ),
        },
        "step1_gate": {
            "candidate": "SSD_IWM_M252",
            "anchor_median_sharpe_after_borrow_10bp": anchor_iwm,
            "threshold": STEP2_GATE,
            "step2_authorized": bool(anchor_iwm >= STEP2_GATE),
        },
        "placebo_check": {
            "id": PLACEBO_ID,
            "anchor_median_sharpe_after_borrow_10bp": placebo["windows"]["anchor"][
                "median_sharpe_after_borrow_10bp"
            ],
            "expected": "negative",
        },
        "step2": {
            "run": False,
            "reason": (
                "step-1 gate failed: SSD_IWM_M252 anchor median Sharpe after borrow "
                f"{anchor_iwm:.4f} < {STEP2_GATE}; a stock basket after higher borrow cannot "
                "exceed the ETF spread (T-20260929-51 plan)"
                if anchor_iwm < STEP2_GATE
                else "gate passed: step 2 candidates must be appended to the manifest first"
            ),
        },
        "verdict": (
            "reject"
            if anchor_iwm < STEP2_GATE
            and not any(r["tier"] in ("keep", "watch_recent") for r in rows)
            else "see candidates[].tier"
        ),
        "notes": [
            "data/sip/daily starts 2016-01, so 252-day-beta candidates first trade 2017-02-01 "
            "(stress window shortened to 2017-02..2023-09; SSD_IWM_M63 and the unhedged control "
            "start 2016-05); windows[stress].actual_start records the exact start per candidate",
            "sharpe fields are the overlay's excess Sharpe; cagr is the overlay CAGR (collateral "
            "interest excluded)",
            "K2 sleeve = overlay + T-bill collateral return, blended with S3 by screen_lane",
        ],
        "candidates": [{k: v for k, v in r.items() if k != "per_offset"} for r in rows],
        "per_offset": {r["id"]: r["per_offset"] for r in rows},
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "results.json").write_text(
        json.dumps(out, indent=2, default=float) + "\n", encoding="utf-8"
    )
    print("wrote", OUT_DIR / "results.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
