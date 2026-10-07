"""Full preregistered evaluation (writes ``results.json``).  See prereg.md in the report folder."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from . import evaluate as V
from . import registry as G
from . import rules as R
from .riskmodel import ledoit_wolf, sample_cov

OUT = G.ROOT / "reports/research/program/portfolio-layer-2026-10-07"
FULL_START = "2017-10-02"
END = "2026-09-15"
K_GRID = (2.0, 3.0, 4.0)
TRIALS = 8
STRESS_EVENTS = {
    "covid_2020-02-19..2020-03-23": ("2020-02-19", "2020-03-23"),
    "year_2022": ("2022-01-03", "2022-12-30"),
}


def spy_gap(root: Path = G.ROOT) -> pd.Series:
    e = pd.read_parquet(root / "data/live/equity_book/etf_daily.parquet")
    c = e[e.symbol == "SPY"].set_index("trade_date")["close"].astype(float)
    c.index = pd.to_datetime(c.index)
    return (c / c.rolling(200, min_periods=200).mean() - 1.0).dropna()


def regime_pit_test(root: Path = G.ROOT) -> dict:
    """Truncate the SPY history at several dates; the value on the cut date must not change."""
    e = pd.read_parquet(root / "data/live/equity_book/etf_daily.parquet")
    c = e[e.symbol == "SPY"].set_index("trade_date")["close"].astype(float)
    c.index = pd.to_datetime(c.index)
    full = c / c.rolling(200, min_periods=200).mean() - 1.0
    cuts = full.dropna().index[::97]
    worst = 0.0
    for d in cuts:
        cc = c.loc[:d]
        v = (cc / cc.rolling(200, min_periods=200).mean() - 1.0).iloc[-1]
        worst = max(worst, abs(float(v) - float(full.loc[d])))
    tab = pd.concat(
        [
            pd.read_parquet(root / f"data/features/regime_daily/{y}.parquet")
            for y in (2024, 2025, 2026)
        ]
    )
    tab["trade_date"] = pd.to_datetime(tab["trade_date"])
    tab = tab.set_index("trade_date")["spy_gap_200sma"].astype(float)
    both = pd.concat([full.rename("mine"), tab.rename("table")], axis=1).dropna()
    return {
        "truncation_max_abs_diff": worst,
        "n_cuts": len(cuts),
        "pass": worst < 1e-12,
        "table_overlap_days": len(both),
        "table_max_abs_diff": float((both.mine - both.table).abs().max()) if len(both) else None,
        "table_last_date": str(tab.index.max().date()),
    }


def regime_scale(r: pd.DataFrame, state: pd.Series) -> tuple[pd.DataFrame, dict]:
    a, b = V.STRESS
    sub = r.loc[a:b]
    # state known at the close of t-1 conditions the return of day t
    prev = state.shift(1).reindex(sub.index)
    off = sub[prev.fillna(False).astype(bool)]
    ratios, info = {}, {}
    for c in r.columns:
        sr_all = V.sharpe(sub[c])
        sr_off = V.sharpe(off[c]) if len(off) >= 60 else np.nan
        ratio = (
            1.0
            if (not np.isfinite(sr_off) or sr_all <= 0)
            else float(np.clip(sr_off / sr_all, 0.0, 2.0))
        )
        ratios[c] = ratio
        info[c] = {
            "sr_all_stress": sr_all,
            "sr_risk_off_stress": None if not np.isfinite(sr_off) else sr_off,
            "ratio": ratio,
        }
    info["risk_off_days_stress"] = int(len(off))
    scale = pd.DataFrame({"risk_on": {c: 1.0 for c in r.columns}, "risk_off": ratios}).T[
        list(r.columns)
    ]
    return scale, info


def window_stats(x: pd.Series, a: str, b: str, vol_target: float = 0.10) -> dict:
    s = x.loc[a:b]
    vol = float(s.std(ddof=1) * np.sqrt(252))
    scaled = s * (vol_target / vol) if vol > 0 else s
    return {
        "days": int(len(s)),
        "sharpe": V.sharpe(s),
        "ann_return": float(s.mean() * 252),
        "ann_vol": vol,
        "max_dd": V.max_drawdown(s),
        "max_dd_at_vol10": V.max_drawdown(scaled),
    }


def f1_gross_p95(root: Path = G.ROOT) -> float:
    d = pd.read_parquet(root / "data/research/book_v12/A1_M0_U3000_F1.parquet")
    return float((d["gross"] / d["equity"]).quantile(0.95))


def account_application(r, ev, reg, spec, statuses, state, scale) -> dict:
    """Per-account allocation, DD-budget leverage, margin cap and sensitivity (prereg section)."""
    lim = json.loads((G.ROOT / "config/portfolio-layer/limits.json").read_text())
    gross_mv = {
        "F1": f1_gross_p95(),
        "noiseband_qqq_obs": 1.0,
        "S1": 1.0,
        "S2": 1.0,
        "S3": 1.0,
        "C2": 1.0,
    }
    out = {}
    a, b = V.RECENT
    for acct in ("quant1", "quant2", "main"):
        ids = [s.id for s in ev if s.account == acct]
        if not ids:
            continue
        sub = r[ids]
        st_ = [s.status for s in ev if s.account == acct]
        cap_ = np.array([s.capital_usd for s in ev if s.account == acct])
        if len(ids) == 1:
            ser_full = sub[ids[0]].iloc[V.WINDOW :]
            ser = ser_full.loc[a:b]
            wbar = np.array([1.0])
            wlast = wbar
            cov = np.array([[float(sub[ids[0]].iloc[-V.WINDOW :].var(ddof=1))]])
        else:
            ser_all, wdf, _ = V.run_rule(
                sub,
                V.RuleSpec(spec.name, spec.kind, spec.k, spec.cov),
                st_,
                cap_,
                FULL_START,
                END,
                regime=state,
                regime_scale=scale,
            )
            ser_full = ser_all
            ser = ser_all.loc[a:b]
            wbar = wdf.loc[a:b].mean().to_numpy()
            wlast = wdf.iloc[-1].to_numpy()
            cov = ledoit_wolf(sub.iloc[-V.WINDOW :].to_numpy())[0]
        mu_prior = R.prior_mu(st_, cov)
        deploy = R.OBS_RISK_SHARE_MAX if all(x == "observation" for x in st_) else 1.0
        acct_ser = ser * deploy
        sd = float(acct_ser.std(ddof=1))
        years = len(acct_ser) / 252.0
        se = 1.0 / np.sqrt(years)
        sr_shrunk = R.portfolio_sharpe(wbar, mu_prior, cov)
        sr_raw = V.sharpe(ser)
        g = float(sum(wbar[i] * gross_mv[c] for i, c in enumerate(ids)) * deploy)
        gmax = lim["accounts"][acct]["gross_max"]
        l_margin = gmax / g if g > 0 else None
        cases = {
            "raw_sample": sr_raw,
            "shrunk_prior": sr_shrunk,
            "half_shrunk": 0.5 * sr_shrunk,
            "shrunk_minus_1se": max(0.0, sr_shrunk - se),
        }
        table = {}
        for cn, sr in cases.items():
            dm = sr * sd / np.sqrt(252.0)
            l_dd = V.solve_leverage(acct_ser.to_numpy(), 0.30, daily_mean=dm, fin_base=deploy)
            lev = min(l_dd, l_margin) if l_margin else l_dd
            ann = lev * dm * 252.0 - max(lev * deploy - 1.0, 0.0) * V.FIN_RATE
            path = lev * ser_full * deploy - max(lev * deploy - 1.0, 0.0) * V.FIN_RATE / 252.0
            diag = {
                "max_dd_full_history": V.max_drawdown(path),
                "max_dd_covid_2020": V.max_drawdown(path.loc["2020-02-19":"2020-03-23"])
                if len(path.loc["2020-02-19":"2020-03-23"])
                else None,
                "max_dd_2022": V.max_drawdown(path.loc["2022-01-03":"2022-12-30"])
                if len(path.loc["2022-01-03":"2022-12-30"])
                else None,
            }
            table[cn] = {
                **diag,
                "sharpe": float(sr),
                "L_dd": float(l_dd),
                "L_used": float(lev),
                "binding": "margin" if l_margin and l_margin < l_dd else "drawdown",
                "expected_ann_return": float(ann),
                "q95_dd_2y_at_L": V.boot_drawdown_q95(
                    acct_ser.to_numpy(), lev, dm, fin_base=deploy
                ),
            }
        out[acct] = {
            "sleeves": ids,
            "rule": spec.name,
            "weights_last": dict(zip(ids, wlast.tolist(), strict=True)),
            "deployed_fraction_of_account": deploy,
            "sharpe_raw_sample": sr_raw,
            "sharpe_shrunk_ex_ante": sr_shrunk,
            "gross_mv_per_equity_at_L1": g,
            "gross_max": gmax,
            "L_margin": l_margin,
            "sharpe_se": float(se),
            "sensitivity": table,
            "note": "observation-only accounts: policy recommendation is L=1 until forward evidence"
            if deploy < 1
            else "",
        }
    return out


def build() -> dict:
    reg = G.load_registry()
    ev = G.evaluable(reg)
    r = G.return_frame(reg)
    r = r.loc[:END]
    statuses = [s.status for s in ev]
    capital = np.array([s.capital_usd for s in ev])
    res: dict = {
        "generated_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%MZ"),
        "sleeves": [s.id for s in ev],
        "statuses": statuses,
        "capital_usd": capital.tolist(),
        "data_window": [str(r.index.min().date()), str(r.index.max().date())],
        "share_cap": R.share_cap(len(ev)),
    }
    # ---- A3 gate
    pit = regime_pit_test()
    res["regime_pit_test"] = pit
    state = spy_gap() < 0
    scale = None
    if pit["pass"]:
        scale, info = regime_scale(r, state)
        res["regime_scale"] = {"table": scale.to_dict(), "stress_estimates": info}
    else:
        res["regime_scale"] = "not done: PIT truncation test failed"

    specs = [V.RuleSpec("A0", "A0"), V.RuleSpec("A1", "A1"), V.RuleSpec("A2", "A2")]
    if scale is not None:
        specs.append(V.RuleSpec("A3", "A3"))
    specs += [V.RuleSpec(f"A4_k{int(k)}", "A4", k) for k in K_GRID]
    series, weights, turns = {}, {}, {}
    for sp in specs:
        ser, w, tn = V.run_rule(
            r, sp, statuses, capital, FULL_START, END, regime=state, regime_scale=scale
        )
        series[sp.name], weights[sp.name], turns[sp.name] = ser, w, tn
    res["rules_run"] = [sp.name for sp in specs]
    # sleeve stop activity (share of days at half weight) and post-freeze exploratory small k
    act = {}
    for k in (*K_GRID, 0.5, 1.0):
        m = V.stop_multipliers(r, k)
        act[f"k{k}"] = {
            "all_days": (m < 1.0).mean().round(4).to_dict(),
            "recent": (m.loc[V.RECENT[0] : V.RECENT[1]] < 1.0).mean().round(4).to_dict(),
        }
    res["stop_activity"] = act
    expl = {}
    for k in (0.5, 1.0):
        ser_k, _, _ = V.run_rule(
            r, V.RuleSpec(f"A4x_k{k}", "A4", k), statuses, capital, FULL_START, END
        )
        expl[f"A4x_k{k}"] = {
            wn: window_stats(ser_k, *wr)
            for wn, wr in {"recent": V.RECENT, "stress": V.STRESS}.items()
        }
    res["exploratory_post_freeze_not_selected"] = expl
    wins = {"recent": V.RECENT, "stress": V.STRESS}
    tab: dict = {}
    for name, ser in series.items():
        tab[name] = {}
        for wn, (a, b) in wins.items():
            row = window_stats(ser, a, b)
            tn = turns[name].loc[a:b]
            row["turnover_per_year"] = float(tn.sum() / (row["days"] / 252.0)) if len(tn) else None
            tab[name][wn] = row
    res["rule_table"] = tab
    # ---- single sleeves and equal-vol reference (recent)
    res["sleeve_recent"] = {c: window_stats(r[c], *V.RECENT) for c in r.columns}
    # ---- paired differences
    a, b = V.RECENT
    diffs = {}
    for name in series:
        if name in ("A0", "A1"):
            continue
        diffs[name] = {
            "vs_A0": V.paired_sharpe_diff(series[name].loc[a:b], series["A0"].loc[a:b]),
            "vs_A1": V.paired_sharpe_diff(series[name].loc[a:b], series["A1"].loc[a:b]),
        }
    diffs["A1"] = {"vs_A0": V.paired_sharpe_diff(series["A1"].loc[a:b], series["A0"].loc[a:b])}
    res["paired_diffs_recent"] = diffs
    # ---- mechanical selection
    base = max(tab["A0"]["recent"]["sharpe"], tab["A1"]["recent"]["sharpe"])
    cands = [n for n in series if n not in ("A0", "A1")]
    ok = [
        n
        for n in cands
        if tab[n]["recent"]["sharpe"] >= base + 0.15
        and tab[n]["stress"]["sharpe"] >= tab["A1"]["stress"]["sharpe"] - 0.15
    ]
    chosen = max(ok, key=lambda n: tab[n]["recent"]["sharpe"]) if ok else "A1"
    res["selection"] = {"baseline_recent_sharpe": base, "passing": ok, "chosen": chosen}
    # ---- EWMA robustness of the chosen rule
    ek = [sp for sp in specs if sp.name == chosen][0]
    ew_spec = V.RuleSpec(chosen + "_ewma", ek.kind, ek.k, "ewma")
    ew, _, _ = V.run_rule(
        r, ew_spec, statuses, capital, FULL_START, END, regime=state, regime_scale=scale
    )
    res["ewma_robustness"] = {
        "rule": ew_spec.name,
        "recent": window_stats(ew, *V.RECENT),
        "stress": window_stats(ew, *V.STRESS),
    }
    # ---- DSR of the chosen rule
    from open_composer.research.campaign_statistics import deflated_sharpe_probability

    try:
        res["dsr_chosen_recent"] = float(
            deflated_sharpe_probability(
                series[chosen].loc[a:b].to_numpy(), trial_count=TRIALS, hac_lag=5
            )
        )
    except ValueError as exc:
        res["dsr_chosen_recent"] = f"n/a: {exc}"
    # ---- stress diagnostics
    diag = {}
    for ev_name, (x0, x1) in STRESS_EVENTS.items():
        sub = r.loc[x0:x1]
        cum = (1.0 + sub).prod() - 1.0
        diag[ev_name] = {
            "sleeve_return": cum.to_dict(),
            "n_sleeves_losing": int((cum < 0).sum()),
            "n_sleeves": int(len(cum)),
            "rules": {
                n: float((1.0 + s.loc[x0:x1]).prod() - 1.0)
                for n, s in series.items()
                if len(s.loc[x0:x1])
            },
            "rule_max_dd": {
                n: V.max_drawdown(s.loc[x0:x1]) for n, s in series.items() if len(s.loc[x0:x1])
            },
        }
    res["stress_diagnostics"] = diag
    # ---- raw vs shrunk (ex-ante) at the end of the sample
    win = r.iloc[-V.WINDOW :].to_numpy()
    cov_raw, (cov_lw, shrink) = sample_cov(win), ledoit_wolf(win)
    mu_raw = win.mean(axis=0)
    mu_prior = R.prior_mu(statuses, cov_lw)
    w_star = weights[chosen].iloc[-1].to_numpy()
    w_raw, _ = R.max_sharpe(cov_raw, mu_raw, 1.0, np.zeros(len(statuses), bool), w_star)
    res["raw_vs_shrunk"] = {
        "lw_shrinkage": shrink,
        "weights_chosen_last": dict(zip(r.columns, w_star.tolist(), strict=True)),
        "sharpe_chosen_raw_inputs": R.portfolio_sharpe(w_star, mu_raw, cov_raw),
        "sharpe_chosen_shrunk_inputs": R.portfolio_sharpe(w_star, mu_prior, cov_lw),
        "sharpe_raw_tangency_in_sample": R.portfolio_sharpe(w_raw, mu_raw, cov_raw),
        "raw_tangency_weights": dict(zip(r.columns, w_raw.tolist(), strict=True)),
    }
    # ---- correlations and how many more sleeves
    rec = r.loc[a:b]
    corr = rec.corr()
    n = len(r.columns)
    rho_bar = float((corr.to_numpy().sum() - n) / (n * (n - 1)))
    sr_prior = float(np.mean([R.PRIOR_SHARPE[s] for s in statuses]))
    sr_p = R.portfolio_sharpe(w_star, mu_prior, cov_lw)
    grid = {}
    for rho in (0.0, 0.05, 0.1, 0.2, 0.3, round(rho_bar, 2)):
        for sr in (0.59, 0.8, 1.0, 1.2):
            d = sr**2 - 4 * rho
            grid[f"rho{rho}_sr{sr}"] = None if d <= 0 else float(4 * (1 - rho) / d)
    res["how_many_more"] = {
        "recent_corr": corr.round(3).to_dict(),
        "rho_bar": rho_bar,
        "avg_prior_sharpe": sr_prior,
        "n_eff": float(n / (1 + (n - 1) * rho_bar)),
        "equal_vol_account_sharpe": R.equal_vol_sharpe(n, rho_bar, sr_prior),
        "n_required_for_sharpe2": grid,
        "sharpe_limit_n_to_inf": sr_prior / np.sqrt(rho_bar) if rho_bar > 0 else None,
        "marginal_rule": (
            "a new sleeve with Sharpe s raises the account Sharpe iff its correlation "
            f"with the account is below s / {sr_p:.2f}"
        ),
        "account_sharpe_shrunk_chosen": sr_p,
        "check_8_sleeves_rho0.1_sr1": {
            "formula": R.equal_vol_sharpe(8, 0.1, 1.0),
            "simulated": V.simulate_equal_vol_sharpe(8, 0.1, 1.0),
        },
    }
    res["accounts"] = account_application(r, ev, reg, ek, statuses, state, scale)
    res["_series"] = {k: v for k, v in series.items()}
    res["_weights"] = {k: v for k, v in weights.items()}
    return res


def save(res: dict) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    ser = res.pop("_series")
    wts = res.pop("_weights")
    pd.DataFrame(ser).to_parquet(OUT / "rule_returns.parquet")
    (OUT / "results.json").write_text(json.dumps(res, indent=1, default=float))
    res["_series"], res["_weights"] = ser, wts
    return OUT / "results.json"
