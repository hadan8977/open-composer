# ruff: noqa: E501
"""Run h20261004_pm_midterm_odds_leadlag exactly as frozen in hypotheses.md (T-20261004-53).

Out-of-sample test of Goldstein, Li, Wang (2026): the 4pm-to-4pm change of the Polymarket 2026
House and Senate Republican-control probabilities, transformed as in the paper (EMA span 5,
60-session rolling percentile rank, map to [-1, 1], lag one session), times each asset's direction,
equal weighted, executed MOC at the close of t-1.

Reads ``data/research/prediction_markets/midterms/daily.parquet`` (scripts/build_pm_midterm_data.py)
and SIP daily bars (read-only). Writes results.json, report.md, decision-record.md and
trial-ledger.jsonl into the iteration folder. No broker or prediction-market write.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import build_pm_midterm_data as bd  # noqa: E402

ITER_ID = bd.ITER_ID
ITER_DIR = bd.ITER_DIR
DATA_DIR = bd.OUT_DIR
SEED = 20261004
N_SHIFTS = 1000
SHIFT_MIN = 20
NW_LAGS = 5
EMA_SPAN = 5
RANK_WINDOW = 60
ANN = 252
COST_BP = 2.0
COST_BP_THIN = 10.0
THIN = {"DJT", "PHUN"}
GATE_SHARPE = 0.5
GATE_T = 2.0
GATE_PCT = 95.0


# ------------------------------------------------------------------ signal


def delta_p(prices: pd.DataFrame) -> pd.Series:
    """Mean over markets of the 4pm-to-4pm change in percentage points; NaN if all are missing."""
    prices = prices.sort_index().ffill()
    change = prices.diff() * 100.0
    return change.mean(axis=1, skipna=True)


def transform(dp: pd.Series) -> pd.Series:
    """Paper transformation: EMA span 5, 60-session percentile rank (current included), to [-1, 1]."""
    ema = dp.ewm(span=EMA_SPAN, adjust=False).mean().where(dp.notna())
    rank = ema.rolling(RANK_WINDOW, min_periods=RANK_WINDOW).rank(pct=True, method="average")
    return 2.0 * rank - 1.0


def lagged_position_signal(signal: pd.Series) -> pd.Series:
    """Signal known at 16:00 of t-1, held over the close-to-close return of t."""
    return signal.shift(1)


# ------------------------------------------------------------------ statistics


def nw_variance(x: np.ndarray, lags: int = NW_LAGS) -> float:
    """Bartlett-kernel long-run variance of a series (mean removed)."""
    x = np.asarray(x, dtype=float)
    x = x - x.mean()
    n = len(x)
    var = float(x @ x) / n
    for lag in range(1, min(lags, n - 1) + 1):
        w = 1.0 - lag / (lags + 1.0)
        var += 2.0 * w * float(x[lag:] @ x[:-lag]) / n
    return var


def nw_t(x: np.ndarray, lags: int = NW_LAGS) -> float:
    x = np.asarray(x, dtype=float)
    x = x[~np.isnan(x)]
    if len(x) < 3:
        return float("nan")
    var = nw_variance(x, lags)
    if var <= 0:
        return float("nan")
    return float(x.mean() / np.sqrt(var / len(x)))


def sharpe(x: np.ndarray) -> float:
    x = np.asarray(x, dtype=float)
    x = x[~np.isnan(x)]
    if len(x) < 3 or x.std(ddof=1) == 0:
        return float("nan")
    return float(x.mean() / x.std(ddof=1) * np.sqrt(ANN))


def series_stats(x: np.ndarray) -> dict[str, Any]:
    x = np.asarray(x, dtype=float)
    x = x[~np.isnan(x)]
    return {
        "n": int(len(x)),
        "mean_daily_bp": float(x.mean() * 1e4) if len(x) else float("nan"),
        "ann_return_pct": float(x.mean() * ANN * 100.0) if len(x) else float("nan"),
        "ann_vol_pct": float(x.std(ddof=1) * np.sqrt(ANN) * 100.0) if len(x) > 2 else float("nan"),
        "sharpe": sharpe(x),
        "nw_t": nw_t(x),
    }


def _ols_nw(y: np.ndarray, x: np.ndarray, lags: int = NW_LAGS) -> dict[str, float]:
    """Time-series OLS y = a + b x with Newey-West standard error for b."""
    ok = ~(np.isnan(y) | np.isnan(x))
    y, x = y[ok], x[ok]
    z = np.column_stack([np.ones(len(x)), x])
    zz_inv = np.linalg.inv(z.T @ z)
    beta = zz_inv @ z.T @ y
    e = y - z @ beta
    h = z * e[:, None]
    s = h.T @ h
    for lag in range(1, min(lags, len(y) - 1) + 1):
        w = 1.0 - lag / (lags + 1.0)
        g = h[lag:].T @ h[:-lag]
        s = s + w * (g + g.T)
    v = zz_inv @ s @ zz_inv
    se = float(np.sqrt(v[1, 1]))
    return {
        "beta": float(beta[1]),
        "se": se,
        "t": float(beta[1] / se) if se > 0 else float("nan"),
        "n": int(len(y)),
    }


def dk_regression(y: np.ndarray, x: np.ndarray, lags: int = NW_LAGS) -> dict[str, float]:
    """Pooled OLS of y[t, i] on x[t] with an intercept and Driscoll-Kraay standard errors."""
    t_count, a_count = y.shape
    ok = ~np.isnan(y) & ~np.isnan(x)[:, None]
    zs, ys, ts = [], [], []
    for t in range(t_count):
        for i in np.flatnonzero(ok[t]):
            zs.append((1.0, x[t]))
            ys.append(y[t, i])
            ts.append(t)
    z = np.array(zs)
    yv = np.array(ys)
    tv = np.array(ts)
    zz_inv = np.linalg.inv(z.T @ z)
    beta = zz_inv @ z.T @ yv
    e = yv - z @ beta
    h = np.zeros((t_count, 2))
    np.add.at(h, tv, z * e[:, None])
    s = h.T @ h
    for lag in range(1, min(lags, t_count - 1) + 1):
        w = 1.0 - lag / (lags + 1.0)
        g = h[lag:].T @ h[:-lag]
        s = s + w * (g + g.T)
    v = zz_inv @ s @ zz_inv
    se = float(np.sqrt(v[1, 1]))
    return {
        "beta_bp_per_pp": float(beta[1]),
        "se": se,
        "t": float(beta[1] / se) if se > 0 else float("nan"),
        "n_obs": int(len(yv)),
        "n_sessions": int(len(np.unique(tv))),
    }


# ------------------------------------------------------------------ strategy


def cost_vector(tickers: list[str], mult: float = 1.0) -> np.ndarray:
    return np.array([(COST_BP_THIN if t in THIN else COST_BP) * mult for t in tickers])


def direction_vector(tickers: list[str], flip: bool = False) -> np.ndarray:
    cat_of = {t: c for c, ts in bd.CATEGORIES.items() for t in ts}
    d = np.array([bd.DIRECTION[cat_of[t]] for t in tickers], dtype=float)
    return -d if flip else d


def net_series(
    sig: np.ndarray, ret: np.ndarray, dirs: np.ndarray, costs_bp: np.ndarray, *, gross: bool = False
) -> np.ndarray:
    """Equal-weight mean over assets of position*return minus cost per unit position change.

    ``sig`` is the lagged signal per session, ``ret`` the close-to-close returns (sessions x
    assets). The position before the first session is zero, so the first session pays entry cost.
    """
    pos = sig[:, None] * dirs[None, :]
    pnl = np.nanmean(pos * ret, axis=1)
    if gross:
        return pnl
    prev = np.vstack([np.zeros((1, pos.shape[1])), pos[:-1]])
    turn_cost = (np.abs(pos - prev) * costs_bp[None, :] / 1e4).mean(axis=1)
    return pnl - turn_cost


def circular_shift_test(
    sig: np.ndarray,
    ret: np.ndarray,
    dirs: np.ndarray,
    costs_bp: np.ndarray,
    *,
    n_shifts: int = N_SHIFTS,
    seed: int = SEED,
) -> dict[str, Any]:
    n = len(sig)
    rng = np.random.default_rng(seed)
    ks = rng.integers(SHIFT_MIN, n - SHIFT_MIN + 1, size=n_shifts)
    real = float(np.nanmean(net_series(sig, ret, dirs, costs_bp)))
    means = np.array(
        [np.nanmean(net_series(np.roll(sig, int(k)), ret, dirs, costs_bp)) for k in ks]
    )
    return {
        "n_shifts": n_shifts,
        "seed": seed,
        "real_mean_daily_bp": real * 1e4,
        "p95_mean_daily_bp": float(np.percentile(means, GATE_PCT) * 1e4),
        "shift_mean_bp": float(means.mean() * 1e4),
        "percentile_of_real": float((means < real).mean() * 100.0),
        "above_p95": bool(real > np.percentile(means, GATE_PCT)),
    }


def evaluate(
    sig: np.ndarray,
    ret: np.ndarray,
    tickers: list[str],
    *,
    dirs: np.ndarray | None = None,
    with_shifts: bool = True,
) -> dict[str, Any]:
    dirs = direction_vector(tickers) if dirs is None else dirs
    costs = cost_vector(tickers)
    net = net_series(sig, ret, dirs, costs)
    out: dict[str, Any] = {
        "net": series_stats(net),
        "gross": series_stats(net_series(sig, ret, dirs, costs, gross=True)),
        "cost_x2": series_stats(net_series(sig, ret, dirs, cost_vector(tickers, 2.0))),
        "mean_abs_position": float(np.nanmean(np.abs(sig))),
    }
    if with_shifts:
        out["circular_shifts"] = circular_shift_test(sig, ret, dirs, costs)
    return out


def verdict(h_m: dict[str, Any]) -> dict[str, Any]:
    net = h_m["net"]
    shifts = h_m["circular_shifts"]
    rule = {
        "net_sharpe_ge_0_5": bool(net["sharpe"] >= GATE_SHARPE),
        "nw_t_ge_2_0": bool(net["nw_t"] >= GATE_T),
        "above_p95_of_1000_shifts": bool(shifts["above_p95"]),
    }
    rule["all_pass"] = all(rule.values())
    rule["stop_net_sharpe_le_0"] = bool(net["sharpe"] <= 0)
    if rule["all_pass"]:
        label = "continue"
    elif rule["stop_net_sharpe_le_0"]:
        label = "stop_refuted"
    else:
        label = "inconclusive"
    return {"continue_rule": rule, "verdict": label}


# ------------------------------------------------------------------ data assembly


def price_panel(daily: pd.DataFrame, names: list[str]) -> pd.DataFrame:
    parts = {n: daily[daily["series"] == n].set_index("session")["price"] for n in names}
    return pd.DataFrame(parts).sort_index()


def build_signals(
    daily: pd.DataFrame,
) -> dict[str, pd.Series]:
    """Lagged position signal per series family, indexed by session."""
    out = {}
    families = {
        "polymarket": ["polymarket_house_r", "polymarket_senate_r"],
        "kalshi": ["kalshi_house_r", "kalshi_senate_r"],
        "placebo": ["placebo_market"],
    }
    for fam, names in families.items():
        panel = price_panel(daily, names)
        out[fam] = lagged_position_signal(transform(delta_p(panel)))
        out[fam + "_dp"] = delta_p(panel)
    return out


def asset_returns(
    bars: dict[str, pd.Series], sessions: pd.DatetimeIndex, tickers: list[str]
) -> pd.DataFrame:
    close = pd.DataFrame({t: bars[t].reindex(sessions) for t in tickers})
    return close.pct_change(fill_method=None)


def regressions(
    dp: pd.Series, ret: pd.DataFrame, tickers: list[str], window: pd.DatetimeIndex
) -> dict[str, Any]:
    dirs = direction_vector(tickers)
    signed = ret * dirs[None, :] * 1e4  # bp, direction signed
    basket = signed.mean(axis=1)
    out: dict[str, Any] = {}
    for label, sample in (("backtest_window", window), ("full_sample", dp.dropna().index)):
        x = dp.reindex(sample)
        y1 = signed.shift(-1).reindex(sample)
        y2 = signed.shift(-2).reindex(sample)
        y0 = signed.reindex(sample)
        valid = x.notna() & y1.notna().all(axis=1)
        out[label] = {
            "n_sessions": int(valid.sum()),
            "next_day_pooled_dk": dk_regression(y1[valid].to_numpy(), x[valid].to_numpy()),
            "next_day_basket_nw": _ols_nw(
                basket.shift(-1).reindex(sample)[valid].to_numpy(), x[valid].to_numpy()
            ),
            "day2_pooled_dk": dk_regression(
                y2[valid & y2.notna().all(axis=1)].to_numpy(),
                x[valid & y2.notna().all(axis=1)].to_numpy(),
            ),
            "same_day_pooled_dk_descriptive": dk_regression(
                y0[x.notna() & y0.notna().all(axis=1)].to_numpy(),
                x[x.notna() & y0.notna().all(axis=1)].to_numpy(),
            ),
        }
    return out


def run(daily: pd.DataFrame, bars: dict[str, pd.Series]) -> dict[str, Any]:
    signals = build_signals(daily)
    sessions = pd.DatetimeIndex(
        sorted(set(daily[daily["series"] == "polymarket_house_r"]["session"]))
    )
    start = bd.signal_start_index(len(sessions))
    assert start is not None
    window = sessions[start:]
    kept = [t for t in bd.ASSETS if t in bars]
    # drop assets without 80 percent bar coverage in the window
    cov = {t: float(pd.DatetimeIndex(window).isin(bars[t].index).mean()) for t in kept}
    kept = [t for t in kept if cov[t] >= bd.MIN_ASSET_COVERAGE]
    dropped = [t for t in bd.ASSETS if t not in kept]
    ret_all = asset_returns(bars, sessions, kept)
    ret = ret_all.reindex(window)
    ret_np = ret.to_numpy()
    sig_pm = signals["polymarket"].reindex(window)
    assert sig_pm.notna().all(), "signal must be valid across the window after burn-in"

    h_m = evaluate(sig_pm.to_numpy(), ret_np, kept)
    out: dict[str, Any] = {
        "iter_id": ITER_ID,
        "generated_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "seed": SEED,
        "window": {
            "sessions": int(len(window)),
            "first": str(window[0].date()),
            "last": str(window[-1].date()),
            "years": round(len(window) / ANN, 3),
        },
        "assets": {"kept": kept, "dropped": dropped, "n_kept": len(kept)},
        "H_M": h_m,
    }
    out.update(verdict(h_m))

    # unconditional baseline: constant position 1
    out["baseline_constant_position"] = series_stats(
        net_series(np.ones(len(window)), ret_np, direction_vector(kept), cost_vector(kept))
    )

    out["regressions"] = regressions(signals["polymarket_dp"], ret_all, kept, window)

    # categories (report only)
    cats = {}
    for cat, tickers in bd.CATEGORIES.items():
        tk = [t for t in tickers if t in kept]
        if not tk:
            continue
        cats[cat] = evaluate(sig_pm.to_numpy(), ret[tk].to_numpy(), tk) | {"assets": tk}
    out["categories"] = cats

    # Kalshi signal, same window
    sig_k = signals["kalshi"].reindex(window)
    out["kalshi_signal"] = evaluate(sig_k.to_numpy(), ret_np, kept) | {
        "valid_sessions": int(sig_k.notna().sum())
    }
    out["kalshi_signal_vs_polymarket_corr"] = float(sig_pm.corr(sig_k))

    # placebos
    placebos: dict[str, Any] = {"circular_shifts": h_m["circular_shifts"]}
    placebos["sign_flip"] = evaluate(
        sig_pm.to_numpy(), ret_np, kept, dirs=direction_vector(kept, flip=True), with_shifts=False
    )
    sig_p = signals["placebo"].reindex(window)
    valid = sig_p.notna().to_numpy()
    if valid.sum() > 2 * SHIFT_MIN + 5:
        first = int(np.argmax(valid))
        placebos["unrelated_market"] = evaluate(sig_p.to_numpy()[first:], ret_np[first:], kept) | {
            "valid_sessions": int(valid.sum()),
            "first_valid_session": str(window[first].date()),
            "note": "same transformation; burn-in and the market start leave a shorter sample",
        }
    else:
        placebos["unrelated_market"] = {
            "valid_sessions": int(valid.sum()),
            "note": "too few valid sessions",
        }
    out["placebos"] = placebos

    # power statement, from the realised window length
    years = len(window) / ANN
    out["power"] = {
        "window_years": round(years, 3),
        "expected_t_at_sharpe_1_0": round(1.0 * np.sqrt(years), 2),
        "expected_t_at_sharpe_1_95": round(1.95 * np.sqrt(years), 2),
        "sharpe_needed_for_t_2_0": round(2.0 / np.sqrt(years), 2),
        "note": "hypotheses.md said about 1.4 years and expected t 1.2 / 2.3; the realised window is shorter",
    }
    out["workflow_pass"] = True
    out["research_pass"] = bool(out["verdict"] == "continue")
    out["llm_contribution_pass"] = False
    out["paper_ready_pass"] = False
    return out


# ------------------------------------------------------------------ outputs


def _f(x: Any, nd: int = 3) -> str:
    return "nan" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:.{nd}f}"


def write_report(res: dict[str, Any], path: Path) -> None:
    h = res["H_M"]
    rule = res["continue_rule"]
    reg = res["regressions"]["backtest_window"]
    regf = res["regressions"]["full_sample"]
    lines = [
        f"# Report: {ITER_ID}",
        "",
        f"Verdict (mechanical, pending lead review): **{res['verdict']}**.",
        "",
        "## Numbers",
        "",
        f"- Window: {res['window']['first']} to {res['window']['last']}, {res['window']['sessions']} sessions "
        f"({res['window']['years']} years), {res['assets']['n_kept']} assets "
        f"(dropped: {', '.join(res['assets']['dropped']) or 'none'}).",
        f"- H-M net: Sharpe {_f(h['net']['sharpe'])}, NW(5) t {_f(h['net']['nw_t'])}, "
        f"annual return {_f(h['net']['ann_return_pct'], 2)}%, vol {_f(h['net']['ann_vol_pct'], 2)}%, "
        f"mean {_f(h['net']['mean_daily_bp'], 2)} bp/day.",
        f"- H-M gross: Sharpe {_f(h['gross']['sharpe'])}, NW t {_f(h['gross']['nw_t'])}; "
        f"costs doubled: Sharpe {_f(h['cost_x2']['sharpe'])}.",
        f"- Circular shifts ({h['circular_shifts']['n_shifts']}, seed {h['circular_shifts']['seed']}): real mean "
        f"{_f(h['circular_shifts']['real_mean_daily_bp'], 2)} bp/day, p95 "
        f"{_f(h['circular_shifts']['p95_mean_daily_bp'], 2)} bp/day, real at the "
        f"{_f(h['circular_shifts']['percentile_of_real'], 1)}th percentile.",
        f"- Continue rule: Sharpe >= 0.5 {rule['net_sharpe_ge_0_5']}; NW t >= 2.0 {rule['nw_t_ge_2_0']}; "
        f"above p95 of shifts {rule['above_p95_of_1000_shifts']}; stop (Sharpe <= 0) "
        f"{rule['stop_net_sharpe_le_0']}.",
        f"- Predictive regression, next-session direction-signed return in bp on dP(t) in pp (pooled, "
        f"Driscoll-Kraay): backtest window beta {_f(reg['next_day_pooled_dk']['beta_bp_per_pp'], 2)} "
        f"(t {_f(reg['next_day_pooled_dk']['t'], 2)}, {reg['next_day_pooled_dk']['n_sessions']} sessions); "
        f"full sample beta {_f(regf['next_day_pooled_dk']['beta_bp_per_pp'], 2)} "
        f"(t {_f(regf['next_day_pooled_dk']['t'], 2)}, {regf['next_day_pooled_dk']['n_sessions']} sessions). "
        f"The paper reports +13 bp per 1 pp.",
        f"- Basket-level NW regression, backtest window: beta {_f(reg['next_day_basket_nw']['beta'], 2)} "
        f"(t {_f(reg['next_day_basket_nw']['t'], 2)}).",
        f"- Day-2 coefficient (backtest window): {_f(reg['day2_pooled_dk']['beta_bp_per_pp'], 2)} bp per pp "
        f"(t {_f(reg['day2_pooled_dk']['t'], 2)}). Same-day coefficient (descriptive, not tradable): "
        f"{_f(reg['same_day_pooled_dk_descriptive']['beta_bp_per_pp'], 2)} "
        f"(t {_f(reg['same_day_pooled_dk_descriptive']['t'], 2)}).",
        "",
        "## Categories (report only)",
        "",
    ]
    for cat, c in res["categories"].items():
        lines.append(
            f"- {cat}: net Sharpe {_f(c['net']['sharpe'])}, NW t {_f(c['net']['nw_t'])}, "
            f"gross Sharpe {_f(c['gross']['sharpe'])}, shift percentile "
            f"{_f(c['circular_shifts']['percentile_of_real'], 1)}."
        )
    k = res["kalshi_signal"]
    lines += [
        "",
        "## Kalshi signal (robustness, same window)",
        "",
        f"- Net Sharpe {_f(k['net']['sharpe'])}, NW t {_f(k['net']['nw_t'])}, gross Sharpe "
        f"{_f(k['gross']['sharpe'])}, shift percentile {_f(k['circular_shifts']['percentile_of_real'], 1)}; "
        f"correlation with the Polymarket signal {_f(res['kalshi_signal_vs_polymarket_corr'], 2)}.",
        "",
        "## Placebos",
        "",
    ]
    sf = res["placebos"]["sign_flip"]
    lines.append(
        f"- Sign flip: net Sharpe {_f(sf['net']['sharpe'])}, gross Sharpe {_f(sf['gross']['sharpe'])} "
        f"(gross should mirror H-M gross {_f(h['gross']['sharpe'])})."
    )
    um = res["placebos"]["unrelated_market"]
    if "net" in um:
        lines.append(
            f"- Unrelated Polymarket market ({um['valid_sessions']} valid sessions from "
            f"{um['first_valid_session']}): net Sharpe {_f(um['net']['sharpe'])}, NW t "
            f"{_f(um['net']['nw_t'])}, shift percentile {_f(um['circular_shifts']['percentile_of_real'], 1)}."
        )
    else:
        lines.append(f"- Unrelated market: {um.get('note')}.")
    b = res["baseline_constant_position"]
    p = res["power"]
    lines += [
        f"- Constant-position baseline (direction-signed basket held long): Sharpe {_f(b['sharpe'])}, "
        f"NW t {_f(b['nw_t'])}.",
        "",
        "## Power",
        "",
        f"- Window {p['window_years']} years. Expected t is {p['expected_t_at_sharpe_1_0']} at a true Sharpe "
        f"of 1.0 and {p['expected_t_at_sharpe_1_95']} at the paper's 1.95; a Sharpe of "
        f"{p['sharpe_needed_for_t_2_0']} is needed for t = 2. {p['note']}.",
        "",
        "## Caveats",
        "",
        "- Directions are the paper's Table A.1 and map a Republican-Congress probability to the "
        "Trump-win exposure; this is the assumption under test.",
        "- Short legs carry no borrow charge; DJT and PHUN shorts are costed at 10 bp per side only.",
        "- The daily 16:00 ET price is the last hourly CLOB point at or before the cut; thin periods "
        "carry the last price (max gap in the data build: see data-feasibility.json).",
        "- Forward shadow to 2026-11-04 is preregistered and runs regardless; the verdict here covers the "
        "backtest window only.",
    ]
    path.write_text("\n".join(lines) + "\n")


def write_decision_record(res: dict[str, Any], path: Path) -> None:
    h = res["H_M"]
    v = res["verdict"]
    rule = res["continue_rule"]
    reg = res["regressions"]["backtest_window"]["next_day_pooled_dk"]
    if v == "continue":
        decision = "continue: all three gates passed; forward shadow already runs and the lead decides on capital"
        nxt = "Forward shadow to 2026-11-04, then the lead's decision on a paper sleeve."
    elif v == "stop_refuted":
        decision = "stop: net Sharpe <= 0 on the backtest window; refuted for the midterm setting"
        nxt = (
            "No further midterm-odds variants without a new mechanism; the forward shadow keeps "
            "running to 2026-11-04 because it is preregistered, but cannot revive the line alone."
        )
    else:
        decision = (
            "pivot to the forward sample: between the continue and stop rules, so inconclusive; "
            "the verdict is recomputed on 2026-11-05 on backtest plus forward shadow with the same three rules"
        )
        nxt = "Run summary on 2026-11-05 over backtest plus forward shadow; apply the same three rules."
    text = f"""# Decision Record: {ITER_ID}

Verdict (mechanical, pending lead review): **{v}**. Numbers come from `results.json` (`H_M`, `continue_rule`, `regressions`, `placebos`) and `report.md`.

## P1

- Path: midterm_control_odds_trump_trades (H-M decision candidate; M-CAT and M-KAL report only)
- Decision: {decision}.
- Reason: net Sharpe {_f(h["net"]["sharpe"], 2)}, NW t {_f(h["net"]["nw_t"], 2)}, real mean at the {_f(h["circular_shifts"]["percentile_of_real"], 1)}th percentile of 1000 circular shifts (p95 gate {rule["above_p95_of_1000_shifts"]}); gross Sharpe {_f(h["gross"]["sharpe"], 2)}; predictive regression {_f(reg["beta_bp_per_pp"], 2)} bp per pp (t {_f(reg["t"], 2)}) against the paper's 13. Window {res["window"]["first"]} to {res["window"]["last"]}, {res["window"]["sessions"]} sessions.
- Directions source: paper Internet Appendix Table A.1, verbatim (identical to the frozen fallback).
- Caveats: window about {res["power"]["window_years"]} years, shorter than the 1.4 years assumed in hypotheses.md; power: expected t {res["power"]["expected_t_at_sharpe_1_0"]} at a true Sharpe of 1.0; no borrow charge on shorts; Republican-control odds stand in for the Trump-win probability.
- Next iteration suggestion: {nxt}
"""
    path.write_text(text)


def write_ledger(res: dict[str, Any], path: Path) -> None:
    rows = [
        {
            "candidate_id": "H-M",
            "decision_eligible": True,
            "net_sharpe": res["H_M"]["net"]["sharpe"],
            "nw_t": res["H_M"]["net"]["nw_t"],
            "gross_sharpe": res["H_M"]["gross"]["sharpe"],
            "shift_percentile": res["H_M"]["circular_shifts"]["percentile_of_real"],
            "n_sessions": res["H_M"]["net"]["n"],
            "verdict": res["verdict"],
        },
        {
            "candidate_id": "M-CAT",
            "decision_eligible": False,
            "categories": {
                c: {"net_sharpe": v["net"]["sharpe"], "nw_t": v["net"]["nw_t"]}
                for c, v in res["categories"].items()
            },
            "verdict": "secondary_no_decision",
        },
        {
            "candidate_id": "M-KAL",
            "decision_eligible": False,
            "net_sharpe": res["kalshi_signal"]["net"]["sharpe"],
            "nw_t": res["kalshi_signal"]["net"]["nw_t"],
            "verdict": "secondary_no_decision",
        },
    ]
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-dir", type=Path, default=DATA_DIR)
    ap.add_argument("--out-dir", type=Path, default=ITER_DIR)
    args = ap.parse_args(argv)
    daily = pd.read_parquet(args.data_dir / "daily.parquet")
    sessions = bd.sessions_between(date(2025, 7, 11), bd.END_DATE)
    bars = bd.load_bars(bd.ASSETS, sessions[0], bd.END_DATE)
    res = run(daily, bars)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "results.json").write_text(json.dumps(res, indent=2, default=float) + "\n")
    write_report(res, args.out_dir / "report.md")
    write_decision_record(res, args.out_dir / "decision-record.md")
    write_ledger(res, args.out_dir / "trial-ledger.jsonl")
    print(
        json.dumps(
            {
                "verdict": res["verdict"],
                "continue_rule": res["continue_rule"],
                "H_M_net": res["H_M"]["net"],
            },
            indent=1,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
