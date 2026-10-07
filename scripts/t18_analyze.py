# ruff: noqa: E501
"""T-20261006-18 analysis: tier-1/2/3 statistics, placebo, FF5 alpha, DSR, labels (rules of hypotheses.md section 5).

scripts/heavy_run.sh --mem 0.8G -- uv run python scripts/t18_analyze.py merge_map     # closest theme per factor (features only)
scripts/heavy_run.sh --mem 0.8G -- uv run python scripts/t18_analyze.py placebo       # gross within-date permutation, tier-1 main spec
uv run python scripts/t18_analyze.py report                                            # results.json from saved series (light)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from open_composer.research import scorecard_v2 as sc  # noqa: E402
from open_composer.research.equity_book import signals as sg  # noqa: E402
from open_composer.research.equity_book.evaluate import load_rf_spy  # noqa: E402
from scripts import t18_engine as E  # noqa: E402
from scripts import t18_factors as F  # noqa: E402

OUT = ROOT / "reports/research/iterations/t20261006_18_library_batch1"
DATA = E.OUTD
RECENT, DIAG = E.RECENT, E.DIAG
THEMES = list(sg.THEMES)
PLACEBO_DIR = E.OUTD / "placebo"
N_PERM = 200
SEED = 20261006
BOOT = 2000
BLOCK = 21


def main_spec(name: str) -> tuple[str, str]:
    return "U3000", ("dm" if name in E.ACCOUNTING else "raw")


def load(key: str) -> pd.DataFrame | None:
    p = E.SERIES / f"{key}.parquet"
    return pd.read_parquet(p) if p.exists() else None


def ex_series(net: pd.Series, rf: pd.Series) -> pd.Series:
    return net - rf.reindex(net.index).fillna(0.0)


def sharpe(x: np.ndarray) -> float:
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    sd = x.std(ddof=1) if len(x) > 2 else 0.0
    return float(x.mean() / sd * np.sqrt(252)) if sd > 0 else float("nan")


def win(s: pd.Series, a: str, b: str) -> pd.Series:
    return s[(s.index >= a) & (s.index <= b)]


def block_returns(df: pd.DataFrame, col: str) -> pd.Series:
    """Per decision block sum of daily values, labelled by the calendar month of the block's last session."""
    g = df.groupby("blk")
    s = g[col].sum()
    last = g.apply(lambda x: x.index[-1])
    s.index = pd.DatetimeIndex(last.to_numpy()).to_period("M")
    return s.groupby(level=0).sum()


# ------------------------------------------------------------------ merge map
def merge_map() -> None:
    ctx = E.make_ctx()
    fs = E.FactorStore()
    px = ctx.px
    dec = [
        p
        for p in E.month_end_positions(px, E.START, px.T - 24)
        if px.dates[p] <= pd.Timestamp(DIAG[1])
    ]
    out = {}
    corr_all = {}
    for name in F.COMPUTED:
        cors = {t: [] for t in THEMES}
        for p in dec:
            t = px.dates[p]
            th = ctx.themes.at(t)
            members = th.index[th["in_u3000"].to_numpy(bool)]
            raw = fs.at(t)[name].reindex(members).to_numpy("float64")
            codes = E._codes(ctx, t, members)
            sc_, cov = sg.process_signal(raw, codes, name in E.ACCOUNTING)
            if cov.sum() < 100:
                continue
            for th_name in THEMES:
                v = th.reindex(members)[th_name].to_numpy("float64")
                cors[th_name].append(E.spearman(np.where(cov, sc_, np.nan), v))
        m = {k: float(np.nanmean(np.abs(v))) if v else float("nan") for k, v in cors.items()}
        corr_all[name] = m
        out[name] = max(m, key=lambda k: m[k] if np.isfinite(m[k]) else -1)
        print(name, out[name], flush=True)
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "merge_map.json").write_text(json.dumps(out, indent=1))
    (DATA / "merge_map_corr.json").write_text(json.dumps(corr_all, indent=1))


# ------------------------------------------------------------------ gross placebo (tier 1 main spec)
def placebo() -> None:
    ctx = E.make_ctx()
    fs = E.FactorStore()
    px = ctx.px
    dec = E.month_end_positions(px, E.START, px.T - 24)
    rng = np.random.default_rng(SEED)
    res = {}
    for name in F.COMPUTED:
        uni, proc = main_spec(name)
        scores, rets, dts = [], [], []
        for p in dec:
            t = px.dates[p]
            th = ctx.themes.at(t)
            members = th.index[th["in_u3000"].to_numpy(bool)]
            raw = fs.at(t)[name].reindex(members).to_numpy("float64")
            codes = E._codes(ctx, t, members)
            s_, cov = sg.process_signal(raw, codes, proc == "dm")
            idx = px.symbols.get_indexer(members)
            ok = cov & (idx >= 0)
            if ok.sum() < 100 or p + 22 >= px.T:
                continue
            with np.errstate(invalid="ignore", divide="ignore"):
                fwd = px.C[p + 22, idx[ok]] / px.C[p + 1, idx[ok]] - 1.0
            good = np.isfinite(fwd)
            code = codes[ok][good]
            s2 = s_[ok][good]
            scores.append((s2, code))
            rets.append(fwd[good])
            dts.append(t)

        def ls(s2: np.ndarray, code: np.ndarray, r: np.ndarray) -> float:
            dm = s2 - pd.Series(s2).groupby(code).transform("mean").to_numpy()
            g = np.abs(dm).sum()
            return float(2.0 * (dm * r).sum() / g) if g > 0 else 0.0

        real = np.array([ls(s2, c, r) for (s2, c), r in zip(scores, rets, strict=True)])
        perm = np.zeros((N_PERM, len(real)))
        for k in range(N_PERM):
            for i, ((s2, c), r) in enumerate(zip(scores, rets, strict=True)):
                perm[k, i] = ls(rng.permutation(s2), c, r)
        d = pd.DatetimeIndex(dts)
        rec = d >= pd.Timestamp(RECENT[0])

        def msr(v: np.ndarray) -> float:
            return (
                float(v.mean() / v.std(ddof=1) * np.sqrt(12))
                if len(v) > 2 and v.std(ddof=1) > 0
                else float("nan")
            )

        res[name] = {
            "recent": {
                "real_sharpe_gross_monthly": msr(real[rec]),
                "pct_below": float(
                    np.mean([msr(perm[k, rec]) < msr(real[rec]) for k in range(N_PERM)])
                ),
                "n_months": int(rec.sum()),
            },
            "full": {
                "real_sharpe_gross_monthly": msr(real),
                "pct_below": float(np.mean([msr(perm[k]) < msr(real) for k in range(N_PERM)])),
                "n_months": len(real),
            },
        }
        print(name, res[name]["recent"], flush=True)
    PLACEBO_DIR.mkdir(parents=True, exist_ok=True)
    (PLACEBO_DIR / "placebo_gross.json").write_text(json.dumps(res, indent=1))


# ------------------------------------------------------------------ report pieces
def ff5() -> pd.DataFrame:
    p = ROOT / "data/raw/factor_libraries/french/ff5_extract/F-F_Research_Data_5_Factors_2x3.csv"
    rows = []
    for line in p.read_text().splitlines():
        parts = [x.strip() for x in line.split(",")]
        if len(parts) >= 7 and parts[0].isdigit() and len(parts[0]) == 6:
            rows.append(parts[:7])
    df = pd.DataFrame(rows, columns=["ym", "Mkt", "SMB", "HML", "RMW", "CMA", "RF"])
    df.index = pd.PeriodIndex(df["ym"], freq="M")
    return df.drop(columns="ym").astype(float) / 100.0


def ols_alpha(y: pd.Series, X: pd.DataFrame, lags: int = 2) -> dict[str, float]:
    d = pd.concat([y.rename("y"), X], axis=1).dropna()
    if len(d) < X.shape[1] + 8:
        return {"n": int(len(d))}
    A = np.column_stack([np.ones(len(d)), d[X.columns].to_numpy()])
    yv = d["y"].to_numpy()
    beta, *_ = np.linalg.lstsq(A, yv, rcond=None)
    e = yv - A @ beta
    n, k = A.shape
    XtXi = np.linalg.inv(A.T @ A)
    S = (A * e[:, None]).T @ (A * e[:, None])
    for L in range(1, lags + 1):
        w = 1 - L / (lags + 1)
        G = (A[L:] * e[L:, None]).T @ (A[:-L] * e[:-L, None])
        S += w * (G + G.T)
    V = XtXi @ S @ XtXi
    r2 = 1 - (e @ e) / (((yv - yv.mean()) ** 2).sum())
    return {
        "n": int(n),
        "alpha_ann": float(beta[0] * 12),
        "alpha_t": float(beta[0] / np.sqrt(V[0, 0])),
        "r2": float(r2),
    }


def memmel_mde(a: np.ndarray, b: np.ndarray) -> dict[str, float]:
    """Minimum detectable Sharpe difference (80% power, one-sided 5%) from the Memmel (2003) variance."""
    ok = np.isfinite(a) & np.isfinite(b)
    a, b = a[ok], b[ok]
    T = len(a) / 252.0
    sa, sb = a.mean() / a.std(ddof=1) * np.sqrt(252), b.mean() / b.std(ddof=1) * np.sqrt(252)
    rho = float(np.corrcoef(a, b)[0, 1])
    var = (2 * (1 - rho) + 0.5 * (sa**2 + sb**2 - 2 * sa * sb * rho**2)) / T
    se = float(np.sqrt(max(var, 1e-12)))
    return {"corr": rho, "se_delta": se, "mde_80": 2.487 * se}


def boot_delta(a: np.ndarray, b: np.ndarray) -> dict[str, float]:
    """Paired moving-block bootstrap of Sharpe(a) - Sharpe(b)."""
    rng = np.random.default_rng(SEED)
    n = len(a)
    nb = int(np.ceil(n / BLOCK))
    d = np.empty(BOOT)
    for i in range(BOOT):
        st = rng.integers(0, n - BLOCK, size=nb)
        idx = (st[:, None] + np.arange(BLOCK)[None, :]).reshape(-1)[:n]
        d[i] = sharpe(a[idx]) - sharpe(b[idx])
    return {
        "p_pos": float((d > 0).mean()),
        "lo90": float(np.quantile(d, 0.05)),
        "hi90": float(np.quantile(d, 0.95)),
    }


def family_dsr(series: dict[str, pd.Series]) -> dict[str, dict]:
    """DSR per series with N_eff and var_SR from the family (standard v2.1 section 3)."""
    names = list(series)
    panel = pd.DataFrame(series).dropna()
    corr = panel.corr().to_numpy()
    n = len(names)
    rho = float((corr.sum() - n) / (n * (n - 1))) if n > 1 else 0.0
    sr = np.array([sc.annual_sharpe(series[k].dropna()) for k in names])
    var_sr = float(np.nanvar(sr, ddof=1))
    n_eff = sc.n_eff_from_corr(n, rho)
    out = {"_family": {"n": n, "mean_corr": rho, "n_eff": n_eff, "var_sr": var_sr}}
    for k in names:
        out[k] = sc.dsr(series[k].dropna().to_numpy(), var_sr_annual=var_sr, n_eff=n_eff)
    return out


def report() -> None:
    rf, spy = load_rf_spy()
    ff = ff5()
    plc = (
        json.loads((PLACEBO_DIR / "placebo_gross.json").read_text())
        if (PLACEBO_DIR / "placebo_gross.json").exists()
        else {}
    )
    mm = (
        json.loads((DATA / "merge_map.json").read_text())
        if (DATA / "merge_map.json").exists()
        else {}
    )
    res: dict = {"factors": {}, "families": {}}
    t1 = {}
    for name in F.COMPUTED:
        r: dict = {"definition": F.DEFINITIONS[name], "tier1": {}}
        for uni in ("U3000", "P1000"):
            for proc in ("raw", "dm"):
                df = load(f"t1__{name}__{uni}__{proc}")
                if df is None:
                    continue
                ex = ex_series(df["net"], rf)
                t1[f"{name}|{uni}|{proc}"] = win(ex, *RECENT)
                ic = df["ic"].dropna()
                gross_ex = ex_series(df["gross"], rf)
                c2 = (
                    df["net"] - df["cost"] - 3.0 * df["borrow"]
                )  # 2x trading cost, borrow 25 -> 100 bp
                r["tier1"][f"{uni}_{proc}"] = {
                    "ic_recent": E.ic_stats(ic, *RECENT),
                    "ic_diag": E.ic_stats(ic, *DIAG),
                    "net_recent": E.window_stats(df["net"], rf, *RECENT),
                    "net_diag": E.window_stats(df["net"], rf, *DIAG),
                    "gross_sharpe_recent": sharpe(win(gross_ex, *RECENT).to_numpy()),
                    "net_2xcost_excess_recent": float(win(ex_series(c2, rf), *RECENT).mean() * 252),
                    "turnover_ann": float(df["turnover"].mean() * 252),
                    "n_names_mean": float(df["n_names"].mean()),
                }
        uni, proc = main_spec(name)
        main = load(f"t1__{name}__{uni}__{proc}")
        if main is not None:
            bm = block_returns(main, "net")
            for tag, (a, b) in (("recent", RECENT), ("full", ("2017-10-01", "2026-09-30"))):
                y = bm[(bm.index >= pd.Period(a[:7], "M")) & (bm.index <= pd.Period(b[:7], "M"))]
                r[f"ff5_alpha_{tag}"] = ols_alpha(
                    y - ff["RF"].reindex(y.index),
                    ff[["Mkt", "SMB", "HML", "RMW", "CMA"]].reindex(y.index),
                )
        r["placebo_gross"] = plc.get(name)
        r["closest_theme"] = mm.get(name)
        res["factors"][name] = r
    if t1:
        res["families"]["tier1"] = family_dsr(t1)
    # tier 2
    themes = {}
    for th in (*THEMES, "M0"):
        df = load(f"t2__theme__{th}")
        if df is not None:
            themes[th] = block_returns(df, "gross")
    if themes:
        T = pd.DataFrame({k: v for k, v in themes.items() if k != "M0"})
        for name in F.COMPUTED:
            uni, proc = main_spec(name)
            df = load(f"t1__{name}__{uni}__{proc}")
            if df is None:
                continue
            y = block_returns(df, "gross")
            rec = y.index >= pd.Period(RECENT[0][:7], "M")
            res["factors"][name]["tier2"] = {
                "spanning_full": ols_alpha(y, T),
                "spanning_recent": ols_alpha(y[rec], T[T.index.isin(y[rec].index)]),
                "corr_themes_full": {k: float(y.corr(v)) for k, v in themes.items()},
                "corr_themes_recent": {
                    k: float(y[rec].corr(v[v.index.isin(y[rec].index)])) for k, v in themes.items()
                },
            }
    # tier 3
    base = [load(f"t3__base__o{o}") for o in range(5)]
    if all(b is not None for b in base):
        base_net = pd.concat([ex_series(b["net"], rf) for b in base], axis=1).mean(axis=1)
        base_rec = win(base_net, *RECENT)
        t3 = {"base": base_rec}
        for name in F.COMPUTED:
            for v in ("w0.5", "w1.0", "w2.0", "merge"):
                parts = [load(f"t3__{name}__{v}__o{o}") for o in range(5)]
                if any(p is None for p in parts):
                    continue
                net = pd.concat([ex_series(p["net"], rf) for p in parts], axis=1).mean(axis=1)
                rec = win(net, *RECENT)
                t3[f"{name}|{v}"] = rec
                a, b = rec.to_numpy(), base_rec.reindex(rec.index).to_numpy()
                ent = {
                    "sharpe": sharpe(a),
                    "base_sharpe": sharpe(b),
                    "delta": sharpe(a) - sharpe(b),
                    **boot_delta(a, b),
                    **memmel_mde(a, b),
                }
                ent["per_offset_delta"] = [
                    sharpe(win(ex_series(p["net"], rf), *RECENT).to_numpy())
                    - sharpe(win(ex_series(base[o]["net"], rf), *RECENT).to_numpy())
                    for o, p in enumerate(parts)
                ]
                res["factors"][name].setdefault("tier3", {})[v] = ent
        res["families"]["tier3"] = family_dsr(t3)
        res["base_recent_sharpe"] = sharpe(base_rec.to_numpy())
    (OUT / "t3_analysis_raw.json").write_text(json.dumps(res, indent=1, default=float))
    print("wrote t3_analysis_raw.json")


if __name__ == "__main__":
    st = sys.argv[1] if len(sys.argv) > 1 else ""
    {"merge_map": merge_map, "placebo": placebo, "report": report}[st]()
