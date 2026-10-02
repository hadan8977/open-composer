"""Scorecard for evaluation standard v2 (docs/evaluation-standard.zh.md).

Every threshold is read from ``config/evaluation-standard-v2.json``; nothing numeric about a
pass/fail line lives in this file.  The module turns daily return series into one JSON-able
scorecard per variant: inputs, vetoes, DSR / PSR, signal t, placebo percentiles, six robustness
checks, the tier and the mapping to the pass flags.

Conventions (all stated in the output under ``method``):

* Offset blend: equal-weight mean of the offsets' daily series on dates where every offset
  exists.  Excess return is blended net minus BIL.
* Sharpe ratios are annualised with sqrt(252).  The Sharpe standard error is Lo (2002), iid:
  ``sqrt((1 + SR^2 / 2) / years)``.
* PSR / DSR follow Bailey and Lopez de Prado (2012, 2014) in per-period units with sample skew
  and Pearson kurtosis of the blended excess series.  The expected maximum Sharpe under the null
  uses ``var_SR`` (cross-variant variance of the annual Sharpe) and ``N_eff`` and is clamped at
  zero; ``N_eff <= 1`` gives zero, so DSR equals PSR(0).  ``campaign_statistics.
  deflated_sharpe_probability`` is not reused: it takes only a trial count (no ``var_SR``).
* Annual excess return for V3 is ``mean(daily excess) * 252``.
* The ex-ante state of day t is the state at the previous session (``state_lag=1``), so the
  conditioning uses information known before the return is earned.
* Missing evidence (no placebo, no signal series, V1/V2 not attested) counts as not met, never as
  met.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from statistics import NormalDist
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "config/evaluation-standard-v2.json"

TRADING_DAYS = 252
SHORT_WINDOW_SESSIONS = 63  # "last 63 sessions" of the standard
MIN_WINDOW_SESSIONS = 20  # a conditional / short window with fewer sessions is not evaluable
NW_LAG = 5
EULER = 0.5772156649015329
_N = NormalDist()

# tier key in the config -> the scorecard metric it is compared against (value >= threshold)
_TIER_KEYS = {
    "dsr_min": "dsr",
    "signal_t_min": "signal_t",
    "placebo_net_pct_min": "placebo_net_pct",
    "placebo_gross_pct_min": "placebo_gross_pct",
    "robustness_min": "robustness_score",
}


def load_config(path: Path | str = DEFAULT_CONFIG) -> dict[str, Any]:
    return json.loads(Path(path).read_text())


# ---------------------------------------------------------------------------
# primitives
# ---------------------------------------------------------------------------
def _n(x: Any) -> int:
    return 0 if x is None else len(x)


def _finite(x: Any) -> float | None:
    if x is None:
        return None
    x = float(x)
    return x if math.isfinite(x) else None


def annual_sharpe(r: Sequence[float] | np.ndarray | pd.Series) -> float:
    a = np.asarray(r, dtype=float)
    if len(a) < 2:
        return float("nan")
    sd = float(a.std(ddof=1))
    if not sd > 0:
        return float("nan")
    return float(a.mean() / sd * math.sqrt(TRADING_DAYS))


def sharpe_se(sharpe: float, sessions: int) -> float:
    """Lo (2002) iid standard error of an annual Sharpe estimated from ``sessions`` days."""
    return math.sqrt((1.0 + sharpe**2 / 2.0) / (sessions / TRADING_DAYS))


def sharpe_z(short_sr: float, short_n: int, main_sr: float, main_n: int) -> float:
    """z = (SR_short - SR_main) / sqrt(SE_short^2 + SE_main^2), Lo (2002) iid standard errors.

    Both standard errors are evaluated at ``main_sr``, the value the short window is tested
    against (H0: the short window has the main Sharpe).  Evaluating SE_short at the observed short
    Sharpe would make |z| bounded below 1 for any 63-session window, because the Lo variance grows
    with SR^2: a collapse to SR = -8 inflates its own standard error enough to hide itself.
    """
    se = math.sqrt(sharpe_se(main_sr, short_n) ** 2 + sharpe_se(main_sr, main_n) ** 2)
    return (short_sr - main_sr) / se


def _moments(r: np.ndarray) -> tuple[float, float]:
    """Sample skewness and Pearson kurtosis (population moments), as in the DSR paper."""
    c = r - r.mean()
    m2 = float(np.mean(c**2))
    return float(np.mean(c**3) / m2**1.5), float(np.mean(c**4) / m2**2)


def _sr_denominator(sr_pp: float, skew: float, kurt: float) -> float:
    d = 1.0 - skew * sr_pp + (kurt - 1.0) / 4.0 * sr_pp**2
    return math.sqrt(d) if d > 0 else float("nan")


def psr(r: np.ndarray, benchmark_annual: float = 0.0) -> float:
    """Probabilistic Sharpe ratio against an annual benchmark Sharpe (Bailey and LdP 2012)."""
    r = np.asarray(r, dtype=float)
    t = len(r)
    sr_pp = float(r.mean() / r.std(ddof=1))
    skew, kurt = _moments(r)
    den = _sr_denominator(sr_pp, skew, kurt)
    bench_pp = benchmark_annual / math.sqrt(TRADING_DAYS)
    return _N.cdf((sr_pp - bench_pp) * math.sqrt(t - 1) / den)


def n_eff_from_corr(n_trials: int, mean_corr: float) -> float:
    return 1.0 + (n_trials - 1.0) * (1.0 - mean_corr)


def expected_max_null(var_sr_annual: float, n_eff: float) -> float:
    """Expected maximum annual Sharpe of ``n_eff`` independent zero-skill trials (DSR eq. 1)."""
    if n_eff <= 1.0 or not var_sr_annual > 0:
        return 0.0
    v = math.sqrt(var_sr_annual) * (
        (1.0 - EULER) * _N.inv_cdf(1.0 - 1.0 / n_eff)
        + EULER * _N.inv_cdf(1.0 - 1.0 / (n_eff * math.e))
    )
    return max(0.0, v)


def dsr(r: np.ndarray, *, var_sr_annual: float, n_eff: float) -> dict[str, float]:
    """Deflated Sharpe ratio (Bailey and LdP 2014) of one daily series."""
    r = np.asarray(r, dtype=float)
    t = len(r)
    sr_pp = float(r.mean() / r.std(ddof=1))
    skew, kurt = _moments(r)
    den = _sr_denominator(sr_pp, skew, kurt)
    sr0 = expected_max_null(var_sr_annual, n_eff)
    stat = (sr_pp - sr0 / math.sqrt(TRADING_DAYS)) * math.sqrt(t - 1) / den
    return {
        "dsr": _N.cdf(stat),
        "psr0": psr(r, 0.0),
        "sr_annual": sr_pp * math.sqrt(TRADING_DAYS),
        "sr0_annual": sr0,
        "skew": skew,
        "kurtosis": kurt,
        "sessions": t,
    }


def signal_t_stats(x: pd.Series | np.ndarray, lag: int = NW_LAG) -> dict[str, float]:
    """iid t = mean / sd * sqrt(T) and a Newey-West (Bartlett, ``lag``) t of the mean."""
    a = np.asarray(x, dtype=float)
    a = a[np.isfinite(a)]
    t = len(a)
    mean = float(a.mean())
    sd = float(a.std(ddof=1))
    c = a - mean
    lrv = float(np.dot(c, c) / t)
    for k in range(1, lag + 1):
        lrv += 2.0 * (1.0 - k / (lag + 1.0)) * float(np.dot(c[k:], c[:-k]) / t)
    return {
        "t_iid": mean / sd * math.sqrt(t),
        "t_newey_west": mean / math.sqrt(lrv / t),
        "mean_daily": mean,
        "sessions": t,
    }


def newey_west_t_diff(a: pd.Series, b: pd.Series, lag: int = NW_LAG) -> float:
    d = (a - b).dropna()
    return signal_t_stats(d, lag)["t_newey_west"]


def placebo_percentile(observed: float, placebo: Sequence[float] | None) -> float | None:
    """Share of placebo Sharpe values below ``observed`` (ties count half)."""
    if placebo is None or len(placebo) == 0 or not math.isfinite(observed):
        return None
    p = np.asarray(placebo, dtype=float)
    p = p[np.isfinite(p)]
    if len(p) == 0:
        return None
    return float((np.sum(p < observed) + 0.5 * np.sum(p == observed)) / len(p))


def dd_thresholds(
    sr: float,
    vol: float,
    sessions: int,
    n_sims: int = 20000,
    seed: int = 20261002,
    percentiles: Sequence[float] = (0.95, 0.99),
) -> dict[str, float]:
    """Simulated max-drawdown percentiles of a Brownian motion with annual Sharpe ``sr`` and
    annual volatility ``vol`` over ``sessions`` days (Magdon-Ismail et al. 2004; Kaminski and Lo
    2014).  Drawdown is in cumulative-return units (peak minus current), returned positive.  The
    default percentiles are the standard's 95% (halve) and 99% (stop and review) lines.
    """
    rng = np.random.default_rng(seed)
    mu = sr * vol / TRADING_DAYS
    sd = vol / math.sqrt(TRADING_DAYS)
    mdd = np.empty(n_sims)
    chunk = max(1, min(n_sims, 4_000_000 // max(sessions, 1)))
    for lo in range(0, n_sims, chunk):
        hi = min(n_sims, lo + chunk)
        steps = mu + sd * rng.standard_normal((hi - lo, sessions))
        path = np.concatenate([np.zeros((hi - lo, 1)), np.cumsum(steps, axis=1)], axis=1)
        mdd[lo:hi] = (np.maximum.accumulate(path, axis=1) - path).max(axis=1)
    return {f"p{int(round(q * 100))}": float(np.quantile(mdd, q)) for q in percentiles}


# ---------------------------------------------------------------------------
# series preparation
# ---------------------------------------------------------------------------
def blend_offsets(long: pd.DataFrame, column: str) -> pd.DataFrame:
    """Equal-weight mean over offsets of ``column`` per variant, on dates where all of a
    variant's offsets exist.  Returns dates x variants."""
    out = {}
    for variant, g in long.groupby("variant"):
        wide = g.pivot(index="date", columns="offset", values=column).sort_index()
        out[variant] = wide.dropna(how="any").mean(axis=1)
    return pd.DataFrame(out)


def _offset_wide(long: pd.DataFrame, variant: str, column: str) -> pd.DataFrame:
    g = long[long["variant"] == variant]
    return g.pivot(index="date", columns="offset", values=column).sort_index().dropna(how="any")


def _norm_index(s: pd.Series | pd.DataFrame):
    s = s.copy()
    s.index = pd.DatetimeIndex(pd.to_datetime(s.index)).normalize()
    return s


def _window(s: pd.Series, a: str, b: str | None = None) -> pd.Series:
    s = s[s.index >= pd.Timestamp(a)]
    if b is not None:
        s = s[s.index <= pd.Timestamp(b)]
    return s.dropna()


def _stat(r: pd.Series) -> dict[str, Any]:
    n = len(r)
    sr = annual_sharpe(r)
    return {
        "sessions": n,
        "sharpe": _finite(sr),
        "se": _finite(sharpe_se(sr, n)) if n >= 2 and math.isfinite(sr) else None,
        "ann_mean": _finite(r.mean() * TRADING_DAYS) if n else None,
    }


def _phase_windows(
    phases: Sequence[Mapping[str, Any]], first: pd.Timestamp, last: pd.Timestamp
) -> list[tuple[str, pd.Timestamp, pd.Timestamp]]:
    """Phase windows clipped to ``[first, last]``; the last phase is extended to ``last``."""
    out = []
    for i, p in enumerate(phases):
        a = pd.Timestamp(p["start"])
        b = last if i == len(phases) - 1 else pd.Timestamp(p["end"])
        if a <= last:
            out.append((str(p["id"]), max(a, first), min(b, last)))
    return out


# ---------------------------------------------------------------------------
# per-variant pieces
# ---------------------------------------------------------------------------
def _veto_v3(cost2x_excess: pd.Series, cfg: Mapping[str, Any]) -> dict[str, Any]:
    ann = float(cost2x_excess.mean() * TRADING_DAYS)
    thr = cfg["vetoes"]["cost2x_recent_ann_excess_le"]
    return {
        "annual_excess": ann,
        "threshold": thr,
        "sessions": len(cost2x_excess),
        "triggered": bool(ann <= thr),
    }


def _veto_v4(net_stress: pd.Series, cfg: Mapping[str, Any]) -> dict[str, Any]:
    v = cfg["vetoes"]
    if len(net_stress) < 126:
        return {"triggered": None, "status": "not_evaluable", "sessions": len(net_stress)}
    daily_sd = float(net_stress.std(ddof=1))
    res: dict[str, Any] = {"sessions": len(net_stress), "daily_sd": daily_sd, "windows": {}}
    triggered, warn = False, False
    for k, veto_key, warn_key in (
        (21, "stress_21d_loss_sigma_veto", "stress_21d_loss_sigma_warn"),
        (63, "stress_63d_loss_sigma_veto", "stress_63d_loss_sigma_warn"),
    ):
        roll = net_stress.rolling(k).sum().dropna()
        sigma = daily_sd * math.sqrt(k)
        worst = float(roll.min())
        mult = -worst / sigma
        is_veto = bool(mult > v[veto_key])
        is_warn = bool((not is_veto) and mult > v[warn_key])
        triggered |= is_veto
        warn |= is_warn
        res["windows"][str(k)] = {
            "worst_sum": worst,
            "worst_end": str(roll.idxmin().date()),
            "sigma": sigma,
            "loss_in_sigma": mult,
            "veto_threshold": v[veto_key],
            "warn_threshold": v[warn_key],
            "veto": is_veto,
            "warn": is_warn,
        }
    res["triggered"] = triggered
    res["warn"] = warn
    return res


def _short_window_z(
    excess_recent: pd.Series, windows: Mapping[str, pd.Series], main: Mapping[str, Any]
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name, w in windows.items():
        if len(w) < MIN_WINDOW_SESSIONS or main["sharpe"] is None:
            out[name] = {"sessions": len(w), "z": None, "status": "not_evaluable"}
            continue
        s = _stat(w)
        out[name] = {
            "sessions": len(w),
            "sharpe": s["sharpe"],
            "z": sharpe_z(s["sharpe"], len(w), main["sharpe"], main["sessions"]),
        }
    return out


def _check_c(
    excess_recent: pd.Series,
    phase_wins: Sequence[tuple[str, pd.Timestamp, pd.Timestamp]],
    max_share: float,
) -> dict[str, Any]:
    total = float(excess_recent.sum())
    shares = {}
    for pid, a, b in phase_wins:
        pnl = float(excess_recent[(excess_recent.index >= a) & (excess_recent.index <= b)].sum())
        shares[pid] = {"pnl": pnl, "share": (pnl / total) if total > 0 else None}
    worst = max((v["share"] for v in shares.values() if v["share"] is not None), default=None)
    ok = bool(total > 0 and worst is not None and worst <= max_share)
    return {
        "value": worst,
        "total_pnl": total,
        "phases": shares,
        "threshold": max_share,
        "pass": ok,
        "note": "total recent P&L must be positive; a non-positive total fails",
    }


def _forward_block(
    fwd: pd.Series | None, main: Mapping[str, Any], dsr_res: Mapping[str, Any]
) -> dict[str, Any]:
    if fwd is None or len(fwd.dropna()) == 0:
        return {"status": "not_evaluable", "reason": "no forward record"}
    fwd = fwd.dropna()
    n = len(fwd)
    out: dict[str, Any] = {"status": "evaluated", "sessions": n, "months": n / 21.0}
    if n < 2 or main["sharpe"] is None:
        return out
    sr = annual_sharpe(fwd)
    out["sharpe"] = _finite(sr)
    if n >= MIN_WINDOW_SESSIONS and math.isfinite(sr):
        out["z_vs_backtest"] = sharpe_z(sr, n, main["sharpe"], main["sessions"])
    # inverse-variance merge of the selection-adjusted backtest estimate and the forward record
    adj = dsr_res["sr_annual"] - dsr_res["sr0_annual"]
    v_bt = sharpe_se(dsr_res["sr_annual"], dsr_res["sessions"]) ** 2
    if math.isfinite(sr):
        v_fw = sharpe_se(sr, n) ** 2
        w_bt, w_fw = 1.0 / v_bt, 1.0 / v_fw
        mean = (w_bt * adj + w_fw * sr) / (w_bt + w_fw)
        se = math.sqrt(1.0 / (w_bt + w_fw))
        out["posterior"] = {
            "backtest_adjusted_sr": adj,
            "mean": mean,
            "se": se,
            "p_sr_gt_0": _N.cdf(mean / se),
        }
    return out


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------
def score_family(
    returns: pd.DataFrame,
    cost2x: pd.DataFrame,
    bil: pd.Series,
    phases: Sequence[Mapping[str, Any]],
    state: pd.Series,
    *,
    config: Mapping[str, Any] | None = None,
    config_path: Path | str = DEFAULT_CONFIG,
    signal_ls: Mapping[str, pd.Series] | None = None,
    placebo: Mapping[str, Mapping[str, Sequence[float]]] | None = None,
    forward: Mapping[str, pd.Series] | None = None,
    attestations: Mapping[str, Mapping[str, bool]] | None = None,
    execution_acceptance: Mapping[str, bool | None] | None = None,
    paper_engine_checklist_ok: Mapping[str, bool] | None = None,
    n_trials: int | None = None,
    end: str | None = None,
    state_lag: int = 1,
) -> dict[str, Any]:
    """Score every variant in ``returns`` (long frame: date, variant, offset, net, gross).

    ``cost2x``: long frame with the same keys and a ``net`` column of the 2x-cost replay.
    ``bil``: daily BIL return indexed by date.  ``phases``: ``phases_recent`` of phases.json.
    ``state``: ex-ante state series (market_state.parquet ``state``).  Optional per-variant
    inputs: ``signal_ls`` (signal-level daily long-short), ``placebo`` ({variant: {"net": [...],
    "gross": [...]}} placebo Sharpe arrays), ``forward`` (daily forward returns),
    ``attestations`` ({variant: {"V1": bool, "V2": bool}}).  ``execution_acceptance``
    ({variant: bool}) and ``paper_engine_checklist_ok`` are caller attestations needed for L1 and
    ``paper_ready_pass``.  ``n_trials`` defaults to the number of variants scored.
    """
    cfg = dict(config) if config is not None else load_config(config_path)
    signal_ls = signal_ls or {}
    placebo = placebo or {}
    forward = forward or {}
    attestations = attestations or {}
    execution_acceptance = execution_acceptance or {}
    paper_engine_checklist_ok = paper_engine_checklist_ok or {}

    returns = returns.rename(columns={"trade_date": "date"})
    cost2x = cost2x.rename(columns={"trade_date": "date"})
    for df in (returns, cost2x):
        df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    bil = _norm_index(bil.astype(float))
    state = _norm_index(state)

    start = cfg["recent_window_start"]
    stress_a, stress_b = cfg["vetoes"]["stress_window"]
    net_b = blend_offsets(returns, "net")
    gross_b = blend_offsets(returns, "gross")
    cost_b = blend_offsets(cost2x, "net")
    variants = list(net_b.columns)
    last = net_b.dropna(how="all").index.max()
    if end is not None:
        last = min(last, pd.Timestamp(end))
    last = min(last, *([net_b[v].dropna().index.max() for v in variants]))

    def excess(s: pd.Series) -> pd.Series:
        return (s - bil.reindex(s.index).fillna(0.0)).dropna()

    ex_recent = {v: _window(excess(net_b[v].dropna()), start, str(last.date())) for v in variants}
    n_var = len(variants)
    n_trials = n_trials if n_trials is not None else n_var
    sharpes = {v: annual_sharpe(ex_recent[v]) for v in variants}
    panel = pd.DataFrame(ex_recent).dropna()
    corr = panel.corr().to_numpy()
    iu = np.triu_indices(n_var, k=1)
    mean_corr = float(corr[iu].mean()) if n_var > 1 else 1.0
    n_eff = n_eff_from_corr(n_trials, mean_corr) if n_var > 1 else 1.0
    var_sr = float(np.var(list(sharpes.values()), ddof=1)) if n_var > 1 else 0.0
    e_max = expected_max_null(var_sr, n_eff)

    # state of day t is the state known at the previous session
    state_ser = state.sort_index()
    state_exante = state_ser.shift(state_lag)
    cur_state_date = state_ser.dropna().loc[:last].index.max()
    cur_state = state_ser.loc[cur_state_date] if pd.notna(cur_state_date) else None

    phase_wins = _phase_windows(phases, pd.Timestamp(start), last)
    cur_phase = phase_wins[-1] if phase_wins else None

    family = {
        "n_variants": n_var,
        "n_trials": n_trials,
        "mean_pairwise_corr": mean_corr,
        "n_eff": n_eff,
        "var_sr_annual": var_sr,
        "expected_max_null_sr_annual": e_max,
        "recent_window": [start, str(last.date())],
        "recent_sessions": int(len(panel)),
    }

    cards: dict[str, Any] = {}
    for v in variants:
        ex = ex_recent[v]
        main = _stat(ex)
        d = dsr(ex.to_numpy(), var_sr_annual=var_sr, n_eff=n_eff)

        # signal level
        sig = signal_ls.get(v)
        if sig is not None:
            sig = _window(_norm_index(sig.astype(float)), start, str(last.date()))
            sig_stats = signal_t_stats(sig)
        else:
            sig_stats = None

        # placebo
        gx = _window(excess(gross_b[v].dropna()), start, str(last.date()))
        gross_sr = annual_sharpe(gx)
        pl = placebo.get(v, {})
        pl_net = placebo_percentile(sharpes[v], pl.get("net"))
        pl_gross = placebo_percentile(gross_sr, pl.get("gross"))

        # vetoes
        c2 = _window(excess(cost_b[v].dropna()), start, str(last.date()))
        v3 = _veto_v3(c2, cfg)
        v4 = _veto_v4(_window(net_b[v].dropna(), stress_a, stress_b), cfg)
        short = {"last_63_sessions": ex.iloc[-SHORT_WINDOW_SESSIONS:]}
        if cur_phase is not None:
            short["current_phase"] = ex[(ex.index >= cur_phase[1]) & (ex.index <= cur_phase[2])]
        zs = _short_window_z(ex, short, main)
        z_vals = [w["z"] for w in zs.values() if w["z"] is not None]
        zmin = min(z_vals) if z_vals else None
        thr5 = cfg["vetoes"]["recent_break_z_veto"]
        v5 = {
            "z_min": zmin,
            "windows": zs,
            "threshold": thr5,
            "triggered": (bool(zmin < thr5) if zmin is not None else None),
        }
        att = attestations.get(v, {})
        v1 = {
            "triggered": None if att.get("V1") is None else (not att["V1"]),
            "attested": att.get("V1"),
        }
        v2 = {
            "triggered": None if att.get("V2") is None else (not att["V2"]),
            "attested": att.get("V2"),
        }
        vetoes = {"V1": v1, "V2": v2, "V3": v3, "V4": v4, "V5": v5}
        triggered = [k for k, x in vetoes.items() if x.get("triggered") is True]
        unassessed = [k for k, x in vetoes.items() if x.get("triggered") is None]

        # robustness
        rb = cfg["robustness_checks"]
        base_sr, c2_sr = main["sharpe"], annual_sharpe(c2)
        a_ok = bool(
            base_sr is not None
            and base_sr > 0
            and math.isfinite(c2_sr)
            and c2_sr >= rb["a_cost2x_sharpe_ratio_min"] * base_sr
        )
        cond = state_exante.reindex(ex.index)
        if cur_state is not None:
            cond_days = ex[cond == cur_state]
        else:
            cond_days = ex.iloc[0:0]
        if len(cond_days) >= MIN_WINDOW_SESSIONS:
            b_sr = annual_sharpe(cond_days)
            b_ok = bool(math.isfinite(b_sr) and b_sr > rb["b_current_state_conditional_sharpe_gt"])
            b = {
                "state": cur_state,
                "state_date": str(cur_state_date.date()),
                "sessions": len(cond_days),
                "sharpe": _finite(b_sr),
                "pass": b_ok,
            }
        else:
            b = {
                "state": cur_state,
                "sessions": len(cond_days),
                "sharpe": None,
                "pass": False,
                "status": "not_evaluable",
            }
        c = _check_c(ex, phase_wins, rb["c_max_single_phase_share_of_recent_pnl"])
        offs = _offset_wide(returns, v, "net")
        off_sr = {}
        for k in offs.columns:
            off_sr[str(k)] = _finite(
                annual_sharpe(_window(excess(offs[k]), start, str(last.date())))
            )
        n_pos = sum(1 for s in off_sr.values() if s is not None and s > 0)
        d_chk = {
            "value": n_pos,
            "offset_sharpes": off_sr,
            "threshold": rb["d_min_positive_offsets"],
            "pass": bool(n_pos >= rb["d_min_positive_offsets"]),
        }
        e_chk = {
            "value": zmin,
            "threshold": rb["e_recent_consistency_z_min"],
            "pass": bool(zmin is not None and zmin >= rb["e_recent_consistency_z_min"]),
        }
        f_chk = {
            "value": pl_gross,
            "threshold": rb["f_gross_placebo_pct_min"],
            "pass": bool(pl_gross is not None and pl_gross >= rb["f_gross_placebo_pct_min"]),
            "status": "missing" if pl_gross is None else "evaluated",
        }
        robustness = {
            "a_cost2x": {
                "value": _finite(c2_sr / base_sr) if base_sr and base_sr > 0 else None,
                "cost2x_sharpe": _finite(c2_sr),
                "base_sharpe": base_sr,
                "threshold": rb["a_cost2x_sharpe_ratio_min"],
                "pass": a_ok,
            },
            "b_current_state": b,
            "c_single_phase": c,
            "d_offsets": d_chk,
            "e_recent_consistency": e_chk,
            "f_gross_placebo": f_chk,
        }
        score = sum(1 for x in robustness.values() if x["pass"])

        metrics = {
            "dsr": d["dsr"],
            "signal_t": sig_stats["t_iid"] if sig_stats else None,
            "placebo_net_pct": pl_net,
            "placebo_gross_pct": pl_gross,
            "robustness_score": score,
        }
        tier, tier_detail = _tier(cfg, metrics, triggered, unassessed)

        fwd = _forward_block(forward.get(v), main, d)
        l1, l2 = _forward_tiers(cfg, tier, fwd, execution_acceptance.get(v))

        v12 = [vetoes["V1"]["triggered"], vetoes["V2"]["triggered"]]
        ready = tier in ("P1", "P2") and bool(paper_engine_checklist_ok.get(v))
        cards[v] = {
            "inputs": {
                "main_excess": main,
                "gross_excess_sharpe": _finite(gross_sr),
                "recent_window": [start, str(last.date())],
                "current_state": cur_state,
                "current_phase": cur_phase[0] if cur_phase else None,
            },
            "dsr": {
                **d,
                "n_eff": n_eff,
                "var_sr_annual": var_sr,
                "n_trials": n_trials,
                "expected_max_null_sr_annual": e_max,
            },
            "signal": (
                {"status": "evaluated", **sig_stats}
                if sig_stats
                else {"status": "missing", "t_iid": None}
            ),
            "placebo": {
                "net_pct": pl_net,
                "gross_pct": pl_gross,
                "n_net": _n(pl.get("net")),
                "n_gross": _n(pl.get("gross")),
                "status": "evaluated" if pl_net is not None or pl_gross is not None else "missing",
            },
            "vetoes": vetoes,
            "vetoes_triggered": triggered,
            "vetoes_unassessed": unassessed,
            "robustness": robustness,
            "robustness_score": score,
            "tier": tier,
            "tier_detail": tier_detail,
            "forward": fwd,
            "L1": l1,
            "L2": l2,
            "pass_flags": {
                "workflow_pass": (
                    None if None in v12 else bool(v12[0] is False and v12[1] is False)
                ),
                "research_pass": tier == "P2",
                "paper_ready_pass": ready,
                "ml_contribution_pass": "see contribution_test()",
                "llm_contribution_pass": "see contribution_test()",
                "forward_evidence": "separate; not part of research_pass",
            },
            "config_version": cfg["version"],
        }

    return {
        "config_version": cfg["version"],
        "config_effective_utc": cfg.get("effective_utc"),
        "family": family,
        "method": {
            "offset_blend": cfg.get("offsets_blend"),
            "excess_over": cfg.get("excess_over"),
            "short_window_sessions": SHORT_WINDOW_SESSIONS,
            "min_window_sessions": MIN_WINDOW_SESSIONS,
            "newey_west_lag": NW_LAG,
            "state_lag_sessions": state_lag,
            "dsr_units": "per-period SR, sample skew and Pearson kurtosis of excess daily",
            "annual_excess": "mean daily excess * 252",
        },
        "variants": cards,
    }


def _tier(
    cfg: Mapping[str, Any],
    metrics: Mapping[str, Any],
    triggered: Sequence[str],
    unassessed: Sequence[str],
) -> tuple[str, dict[str, Any]]:
    detail: dict[str, Any] = {}
    best = "none"
    for tier_name, short in (("P1_paper_incubation", "P1"), ("P2_live_candidate", "P2")):
        spec = cfg["tiers"][tier_name]
        conds = {}
        for key, thr in spec.items():
            metric = _TIER_KEYS[key]
            val = metrics.get(metric)
            conds[key] = {
                "metric": metric,
                "value": val,
                "threshold": thr,
                "met": bool(val is not None and val >= thr),
            }
        conds["no_veto_triggered"] = {"triggered": list(triggered), "met": not triggered}
        conds["vetoes_all_assessed"] = {"unassessed": list(unassessed), "met": not unassessed}
        met = all(c["met"] for c in conds.values())
        detail[short] = {"met": met, "conditions": conds}
        if met:
            best = short
    return best, detail


def _forward_tiers(
    cfg: Mapping[str, Any], tier: str, fwd: Mapping[str, Any], exec_ok: bool | None
) -> tuple[dict[str, Any], dict[str, Any]]:
    if fwd.get("status") != "evaluated":
        ne = {"status": "not_evaluable", "reason": "no forward record"}
        return ne, ne
    l1c, l2c = cfg["tiers"]["L1_live_pilot_proposal"], cfg["tiers"]["L2_scale_up"]
    z = fwd.get("z_vs_backtest")
    l1_conds = {
        "is_P2": tier == "P2",
        "paper_sessions": fwd["sessions"] >= l1c["paper_sessions_min"],
        "forward_z": z is not None and z >= l1c["forward_z_min"],
        "execution_acceptance": None if exec_ok is None else bool(exec_ok),
    }
    if l1_conds["execution_acceptance"] is None:
        l1 = {
            "status": "not_evaluable",
            "reason": "execution acceptance not attested",
            "conditions": l1_conds,
        }
    else:
        l1 = {"status": "evaluated", "met": all(l1_conds.values()), "conditions": l1_conds}
    p = fwd.get("posterior", {}).get("p_sr_gt_0")
    l2_conds = {
        "is_L1": bool(l1.get("met")),
        "forward_months": fwd["months"] >= l2c["forward_months_min"],
        "posterior_p": p is not None and p >= l2c["posterior_p_sr_gt_0_min"],
    }
    l2 = {"status": "evaluated", "met": all(l2_conds.values()), "conditions": l2_conds}
    return l1, l2


def contribution_test(
    with_model: pd.Series,
    without_model: pd.Series,
    *,
    var_sr_annual: float,
    n_eff: float,
    min_t: float = 2.0,
) -> dict[str, Any]:
    """Standard section 7: the model variant has a higher recent DSR than the baseline on the
    same data and costs, and the Newey-West t of the daily net difference is >= ``min_t``."""
    idx = with_model.dropna().index.intersection(without_model.dropna().index)
    a, b = with_model.loc[idx], without_model.loc[idx]
    da = dsr(a.to_numpy(), var_sr_annual=var_sr_annual, n_eff=n_eff)["dsr"]
    db = dsr(b.to_numpy(), var_sr_annual=var_sr_annual, n_eff=n_eff)["dsr"]
    t = newey_west_t_diff(a, b)
    return {
        "dsr_with": da,
        "dsr_without": db,
        "nw_t_difference": t,
        "min_t": min_t,
        "pass": bool(da > db and t >= min_t),
    }
