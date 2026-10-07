"""Shared statistics for T-20261006-15 (all groups): window and phase stats, placebo percentile,
robustness checks and the P1 tier of config/evaluation-standard-v2.json (v2.1)."""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from open_composer.research import scorecard_v2 as S  # noqa: E402

SQ = math.sqrt(252.0)
UP_PHASES = ("P01", "P04", "P07", "P10", "P11")  # phases labelled 上涨 (state of the current phase)


def sr_rows(X: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Annual Sharpe of each row of X over the masked columns (NaN ignored)."""
    m = X[:, mask]
    n = np.sum(np.isfinite(m), axis=1)
    mean = np.nanmean(m, axis=1)
    sd = np.nanstd(m, axis=1, ddof=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        out = mean / sd * SQ
    out[(n < 20) | ~(sd > 0)] = np.nan
    return out


def mean_rows(X: np.ndarray, mask: np.ndarray) -> np.ndarray:
    return np.nanmean(X[:, mask], axis=1)


def clean(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, float)
    return x[np.isfinite(x)]


def placebo_pct(observed: float, placebos) -> float | None:
    return S.placebo_percentile(observed, placebos)


def robustness(
    net1: np.ndarray,
    net2: np.ndarray,
    dates: pd.DatetimeIndex,
    masks: dict[str, np.ndarray],
    gross_pct: float | None,
) -> dict:
    """The six v2.1 checks on a daily series; d (rebalance offsets) is not applicable intraday."""
    rec = masks["recent"]
    r1 = net1[rec]
    r1c = clean(r1)
    sr1 = S.annual_sharpe(r1c) if len(r1c) > 20 else float("nan")
    sr2 = S.annual_sharpe(clean(net2[rec])) if len(r1c) > 20 else float("nan")
    chk = {}
    chk["a_cost2x_ratio"] = bool(sr1 > 0 and sr2 / sr1 >= 0.5)
    up = np.zeros(len(dates), bool)
    for ph in UP_PHASES:
        up |= masks[ph]
    up_r = clean(net1[up])
    chk["b_up_state_sharpe_gt0"] = bool(len(up_r) > 20 and S.annual_sharpe(up_r) > 0)
    tot = np.nansum(net1[rec])
    share = []
    for ph in (f"P{i:02d}" for i in range(1, 12)):
        share.append(float(np.nansum(net1[masks[ph]]) / tot) if tot > 0 else float("nan"))
    chk["c_max_phase_share"] = float(np.nanmax(share)) if tot > 0 else None
    chk["c_ok"] = bool(tot > 0 and np.nanmax(share) <= 0.5)
    last63 = clean(net1[rec])[-63:]
    cur = clean(net1[masks["P11"]])
    zs = []
    for w in (last63, cur):
        if len(w) >= S.MIN_WINDOW_SESSIONS and len(r1c) > 20 and sr1 == sr1:
            zs.append(S.sharpe_z(S.annual_sharpe(w), len(w), sr1, len(r1c)))
    chk["e_z"] = [float(z) for z in zs]
    chk["e_ok"] = bool(zs and min(zs) >= -2.0)
    chk["f_gross_placebo_pct"] = gross_pct
    chk["f_ok"] = bool(gross_pct is not None and gross_pct >= 0.95)
    chk["d_offsets"] = "n/a_intraday"
    chk["score"] = (
        int(chk["a_cost2x_ratio"])
        + int(chk["b_up_state_sharpe_gt0"])
        + int(chk["c_ok"])
        + int(chk["e_ok"])
        + int(chk["f_ok"])
    )
    return chk


def tier_p1(dsr: float | None, net_pct: float | None, rob_score: int) -> dict:
    ok = (
        dsr is not None and dsr >= 0.7 and net_pct is not None and net_pct >= 0.9 and rob_score >= 3
    )
    return {
        "P1_paper_incubation": bool(ok),
        "detail": {"dsr>=0.7": dsr, "net_placebo_pct>=0.9": net_pct, "robustness>=3": rob_score},
    }


def n_eff_estimate(
    X: np.ndarray, mask: np.ndarray, n_trials: int, sample: int = 500, seed: int = 7
):
    """N_eff = 1 + (N-1)(1 - mean pairwise corr) from a random sample of version rows."""
    rng = np.random.default_rng(seed)
    idx = rng.choice(len(X), size=min(sample, len(X)), replace=False)
    M = np.nan_to_num(X[idx][:, mask], nan=0.0)
    M = M[np.std(M, axis=1) > 0]
    c = np.corrcoef(M)
    iu = np.triu_indices(len(M), 1)
    rho = float(np.nanmean(c[iu]))
    return {
        "mean_pairwise_corr": rho,
        "n_trials": n_trials,
        "n_eff": S.n_eff_from_corr(n_trials, rho),
    }


def dsr_of(series: np.ndarray, var_sr: float, n_eff: float) -> dict:
    r = clean(series)
    return S.dsr(r, var_sr_annual=var_sr, n_eff=n_eff)


def nw(series: np.ndarray) -> dict:
    return S.signal_t_stats(clean(series))
