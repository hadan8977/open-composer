# ruff: noqa: E501
"""Validation of the equity-book risk model v1 (design section 6, acceptance 1-3).

Writes ``reports/research/program/risk-model-v1-2026-10-01/{results.json,report.md}``.

1. Bias statistics: realised / predicted volatility over the following 21 sessions for 100 random
   dollar-neutral portfolios per month-end and for the Stage-0 decile books (MOM_12_1, COMP4;
   P1000, long top decile / short bottom decile, equal weights, $1 / $1).
2. Beta prediction: the same Stage-0 books hedged with SPY so that the *predicted* beta is zero --
   (a) model beta (``RiskModel.predicted_beta``), (b) the naive 252-day OLS beta Stage 0 used --
   mean absolute realised 21-session beta to SPY.
3. Cross-check: 20-factor PCA of the residuals by year against a column-shuffled null, and the
   share of return variance the model explains.
4. Runtime and peak memory.

    scripts/run_capped.sh --mem 1.8G -- uv run python scripts/validate_equity_book_risk.py
"""

from __future__ import annotations

import json
import resource
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import diag_s0_hedged_books as s0  # noqa: E402

from open_composer.research.equity_book import risk as rk  # noqa: E402
from open_composer.research.equity_book.panel import DEFAULT_DIR, PricePanel  # noqa: E402

OUT = ROOT / "reports/research/program/risk-model-v1-2026-10-01"
WINDOWS = {
    "stress": ("2017-10-02", "2023-08-31"),
    "gap": ("2023-09-01", "2023-12-31"),
    "anchor": ("2024-01-08", "2026-09-17"),
}
H = 21
N_RANDOM = 100
N_PER_LEG = 30
SEED = 20261001
BAND = (0.8, 1.2)
BETA_TARGET = 0.15
PCA_K = 20
BETA_METHODS = ("ewma", "vasicek", "model")
HEDGES = (*BETA_METHODS, "naive")


def _log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def window_of(d: pd.Timestamp) -> str | None:
    for name, (a, b) in WINDOWS.items():
        if pd.Timestamp(a) <= d <= pd.Timestamp(b):
            return name
    return None


def forward_returns(close: np.ndarray, pos: int, cols: np.ndarray) -> np.ndarray:
    """``(H, len(cols))`` close-to-close returns of sessions pos+1 .. pos+H; a missing price gives 0
    (no padding across holes)."""
    blk = close[pos : pos + H + 1][:, cols]
    with np.errstate(invalid="ignore", divide="ignore"):
        r = blk[1:] / blk[:-1] - 1.0
    return np.where(np.isfinite(r), r, 0.0)


def stage0_books(dates: pd.DatetimeIndex) -> list[dict]:
    """Decile books of Stage 0 (P1000, MOM_12_1 and COMP4) from its cache, one entry per formation
    date and signal: long / short symbols, equal weights, and Stage-0's own 252-day beta."""
    df, periods = s0.load_joined_panel()
    out = []
    for fd, sub in df.groupby("formation_date"):
        sub = s0._eligible(sub, 1, 1000)
        if len(sub) < s0.MIN_NAMES:
            continue
        mom = sub["MOM_12_1"].to_numpy("float64")
        comp = s0.comp4(
            mom,
            sub["ON252"].to_numpy("float64"),
            sub["GP"].to_numpy("float64"),
            sub["SUE"].to_numpy("float64"),
        )
        beta = sub["beta"].to_numpy("float64")
        beta = np.where(np.isfinite(beta), beta, s0.BETA_FILL)
        syms = sub["symbol"].to_numpy()
        for sig, score in (("MOM_12_1", mom), ("COMP4", comp)):
            m = np.isfinite(score)
            if m.sum() < s0.MIN_NAMES:
                continue
            lg, sh = s0.select_legs(score[m], None, size_neutral=False)
            out.append(
                {
                    "date": pd.Timestamp(fd),
                    "signal": sig,
                    "long": syms[m][lg],
                    "short": syms[m][sh],
                    "beta_long": beta[m][lg],
                    "beta_short": beta[m][sh],
                    "beta_naive": dict(zip(syms[m], beta[m], strict=True)),
                }
            )
    _log(f"stage-0 books: {len(out)} (date, signal) entries")
    return out


def _saved(rm: rk.RiskModel, year: int) -> pd.DatetimeIndex:
    try:
        return rm.saved_dates(year)
    except FileNotFoundError:
        return pd.DatetimeIndex([])


def bias_and_beta(
    rm: rk.RiskModel, prices: PricePanel, books: list[dict], spy_ret: np.ndarray
) -> tuple[dict, dict]:
    close = prices.close
    dates = prices.dates
    col_of = {s: j for j, s in enumerate(prices.symbols)}
    rng = np.random.default_rng(SEED)
    # the last saved session of every month = the Stage-0 formation dates
    all_saved = pd.DatetimeIndex(sorted({d for y in range(2017, 2027) for d in _saved(rm, y)}))
    month_ends = list(
        pd.Series(all_saved, index=all_saved).groupby([all_saved.year, all_saved.month]).max()
    )
    bias_rows: list[dict] = []
    beta_rows: list[dict] = []
    book_by_date: dict[pd.Timestamp, list[dict]] = {}
    for b in books:
        book_by_date.setdefault(b["date"], []).append(b)
    for d in month_ends:
        win = window_of(d)
        pos = int(dates.get_loc(d)) if d in dates else None
        if win is None or pos is None or pos + H >= len(dates):
            continue
        x, f, dvar = rm.at(d, exact=True)
        names = list(x.index)
        cols = np.array([col_of.get(s, -1) for s in names])
        keep = cols >= 0
        xm, dv = x.to_numpy(), dvar.to_numpy()
        fm = f.to_numpy()
        r = forward_returns(close, pos, np.where(keep, cols, 0))
        r[:, ~keep] = 0.0
        # --- random dollar-neutral portfolios (rows: 100 portfolios)
        n = len(names)
        w_mat = np.zeros((n, N_RANDOM))
        for k in range(N_RANDOM):
            pick = rng.choice(n, 2 * N_PER_LEG, replace=False)
            w_mat[pick[:N_PER_LEG], k] = 1.0 / N_PER_LEG
            w_mat[pick[N_PER_LEG:], k] = -1.0 / N_PER_LEG
        xw = xm.T @ w_mat
        pred_var = np.einsum("ik,ij,jk->k", xw, fm, xw) + (w_mat**2 * dv[:, None]).sum(0)
        pr = r @ w_mat
        real_vol = pr.std(axis=0, ddof=1)
        for k in range(N_RANDOM):
            bias_rows.append(
                {
                    "date": d,
                    "window": win,
                    "set": "random_dollar_neutral",
                    "pred_vol": float(np.sqrt(pred_var[k])),
                    "real_vol": float(real_vol[k]),
                }
            )
        # --- Stage-0 decile books
        beta_preds = {m: rm.predicted_beta(d, m) for m in BETA_METHODS}
        for b in book_by_date.get(d, []):
            wv = pd.Series(0.0, index=names)
            lg = [s for s in b["long"] if s in wv.index]
            sh = [s for s in b["short"] if s in wv.index]
            if len(lg) < 10 or len(sh) < 10:
                continue
            wv[lg] = 1.0 / len(lg)
            wv[sh] = -1.0 / len(sh)
            w = wv.to_numpy()
            pv = float((xm.T @ w) @ fm @ (xm.T @ w) + (w**2 * dv).sum())
            ret = r @ w
            bias_rows.append(
                {
                    "date": d,
                    "window": win,
                    "set": f"stage0_{b['signal']}",
                    "pred_vol": float(np.sqrt(pv)),
                    "real_vol": float(ret.std(ddof=1)),
                    "coverage_long": len(lg) / len(b["long"]),
                    "coverage_short": len(sh) / len(b["short"]),
                }
            )
            # beta: hedge so that the predicted beta of the book is zero, one hedge per estimator
            naive = b["beta_naive"]
            hedges = {
                m: -float(
                    np.nansum(w * beta_preds[m].reindex(names).fillna(s0.BETA_FILL).to_numpy())
                )
                for m in BETA_METHODS
            }
            hedges["naive"] = -float(sum(wv[s] * naive.get(s, s0.BETA_FILL) for s in lg + sh))
            spy = spy_ret[pos + 1 : pos + H + 1]
            var_spy = float(spy.var(ddof=1))

            def realised_beta(
                hedge: float,
                ret: np.ndarray = ret,
                spy: np.ndarray = spy,
                var_spy: float = var_spy,
            ) -> float:
                p = ret + hedge * spy
                return float(np.cov(p, spy, ddof=1)[0, 1] / var_spy)

            # sampling noise of a 21-session beta: even a perfect hedge shows |beta| ~ 0.8 * se
            slope = np.cov(ret, spy, ddof=1)[0, 1] / var_spy
            resid = ret - slope * spy
            se = float(resid.std(ddof=2) / (spy.std(ddof=1) * np.sqrt(H - 1)))
            row = {
                "date": d,
                "window": win,
                "signal": b["signal"],
                "unhedged": realised_beta(0.0),
                "se_beta_21d": se,
            }
            for m, h in hedges.items():
                row[f"beta_{m}"] = realised_beta(h)
                row[f"pred_book_{m}"] = -h
            beta_rows.append(row)
    return pd.DataFrame(bias_rows), pd.DataFrame(beta_rows)


def summarise_bias(df: pd.DataFrame) -> dict:
    out: dict = {}
    df = df.assign(ratio=df["real_vol"] / df["pred_vol"])
    groups = [((s, w), g) for (s, w), g in df.groupby(["set", "window"])]
    groups += [((s, "all"), g) for s, g in df.groupby("set")]
    for (s, w), g in groups:
        out.setdefault(s, {})[w] = {
            "n": int(len(g)),
            "mean_ratio": float(g["ratio"].mean()),
            "median_ratio": float(g["ratio"].median()),
            "rms_ratio": float(np.sqrt((g["ratio"] ** 2).mean())),
            "in_band_0.8_1.2": bool(BAND[0] <= g["ratio"].mean() <= BAND[1]),
            "share_of_portfolios_in_band": float(g["ratio"].between(*BAND).mean()),
        }
    return out


def summarise_beta(df: pd.DataFrame) -> dict:
    out: dict = {}
    rows = [((s, w), g) for (s, w), g in df.groupby(["signal", "window"])]
    rows += [((s, "all"), g) for s, g in df.groupby("signal")]
    rows += [(("both", w), g) for w, g in df.groupby("window")]
    rows += [(("both", "all"), df)]
    for (s, w), g in rows:
        floor = float(g["se_beta_21d"].mean() * np.sqrt(2.0 / np.pi))
        d: dict = {
            "n": int(len(g)),
            "mean_abs_beta_unhedged": float(g["unhedged"].abs().mean()),
            "mean_beta_unhedged": float(g["unhedged"].mean()),
            "noise_floor_mean_abs_beta": floor,
        }
        for m in HEDGES:
            col = g[f"beta_{m}"]
            d[m] = {
                "mean_abs_beta": float(col.abs().mean()),
                "mean_beta": float(col.mean()),
                "mean_predicted_book_beta": float(g[f"pred_book_{m}"].mean()),
                "below_0.15": bool(col.abs().mean() < BETA_TARGET),
                "beats_naive": bool(col.abs().mean() < g["beta_naive"].abs().mean()),
            }
        out.setdefault(s, {})[w] = d
    return out


def pca_and_variance(prices: PricePanel, meta: dict) -> dict:
    """Residual PCA by year (top-20 share vs a column-shuffled null) and variance explained."""
    close = prices.close
    dates = prices.dates
    col_of = {s: j for j, s in enumerate(prices.symbols)}
    out: dict = {}
    rng = np.random.default_rng(SEED)
    for p in sorted((DEFAULT_DIR / "risk").glob("residuals_20*.parquet")):
        year = int(p.stem.split("_")[1])
        res = pd.read_parquet(p)
        res["j"] = res["symbol"].map(col_of)
        res["pos"] = dates.get_indexer(res["trade_date"])
        res = res.dropna(subset=["j"])
        j = res["j"].to_numpy(int)
        pos = res["pos"].to_numpy(int)
        with np.errstate(invalid="ignore", divide="ignore"):
            r = close[pos, j] / close[pos - 1, j] - 1.0
        e = res["resid"].to_numpy("float64")
        ok = np.isfinite(r)
        ss_res, ss_tot = float((e[ok] ** 2).sum()), float((r[ok] ** 2).sum())
        piv = res.pivot(index="trade_date", columns="symbol", values="resid")
        cover = piv.notna().mean()
        mat = piv.loc[:, cover >= 0.9].fillna(0.0).to_numpy("float64")
        t_n, n = mat.shape
        mat = mat / np.maximum(mat.std(axis=0, keepdims=True), 1e-12)  # correlation PCA
        ev = np.linalg.svd(mat, compute_uv=False) ** 2
        share = ev / ev.sum()
        null = mat.copy()
        for k in range(n):
            null[:, k] = rng.permutation(null[:, k])
        evn = np.linalg.svd(null, compute_uv=False) ** 2
        sn = evn / evn.sum()
        out[year] = {
            "days": int(t_n),
            "names": int(n),
            "variance_explained_uncentred": 1.0 - ss_res / ss_tot,
            "mean_weighted_r2": meta["stats"]["r2_by_year"].get(str(year)),
            "pca_top1_share": float(share[0]),
            "pca_top5_share": float(share[:5].sum()),
            "pca_top20_share": float(share[:PCA_K].sum()),
            "null_top1_share": float(sn[0]),
            "null_top5_share": float(sn[:5].sum()),
            "null_top20_share": float(sn[:PCA_K].sum()),
            "top20_excess_over_null": float(share[:PCA_K].sum() - sn[:PCA_K].sum()),
        }
        _log(f"pca {year}: {out[year]}")
    return out


def write_report(res: dict) -> None:
    b, bt, px, rt = res["bias"], res["beta"], res["pca"], res["runtime"]
    lines = [
        "# Risk model v1: validation (design section 6)",
        "",
        f"Generated {res['generated_utc']} by `scripts/validate_equity_book_risk.py`; model files "
        "`data/research/equity_book/risk/`; numbers copied from `results.json`.",
        "",
        "## 1. Bias statistics (realised / predicted volatility, next 21 sessions)",
        "",
        "Portfolios are held at constant weights for the 21 sessions after each month-end. Target "
        "band 0.8 - 1.2 on the mean ratio. Random: 100 dollar-neutral portfolios (30 long / 30 short "
        "equal weight, drawn from the U3000 cohort) per month-end. Stage 0 books: P1000 deciles, "
        "$1 long / $1 short.",
        "",
        "| set | window | n | mean | median | rms | in band | share in band |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for s, wins in b.items():
        for w, v in wins.items():
            lines.append(
                f"| {s} | {w} | {v['n']} | {v['mean_ratio']:.3f} | {v['median_ratio']:.3f} | "
                f"{v['rms_ratio']:.3f} | {v['in_band_0.8_1.2']} | {v['share_of_portfolios_in_band']:.2f} |"
            )
    lines += [
        "",
        "## 2. Beta prediction (mean absolute realised 21-session beta to SPY)",
        "",
        "Stage-0 decile books hedged with SPY so that the predicted beta is zero, one hedge per beta "
        "estimator: naive = Stage 0's 252-day OLS beta; ewma63 = exponentially weighted (half-life 63, "
        "252-session window) beta; vasicek = ewma63 shrunk toward the cross-sectional mean (the beta "
        "style input); model-implied = `x_i' F x_m / var_m` from the factor model. The brief's target "
        "is a mean absolute realised beta < 0.15. `noise floor` = sqrt(2/pi) x the mean standard error "
        "of a 21-session beta of the same book, i.e. what a *perfect* hedge would still show.",
        "",
        "| signal | window | n | noise floor | unhedged | naive | ewma63 | vasicek | model-implied |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for s, wins in bt.items():
        for w, v in wins.items():
            lines.append(
                f"| {s} | {w} | {v['n']} | {v['noise_floor_mean_abs_beta']:.3f} | "
                f"{v['mean_abs_beta_unhedged']:.3f} | {v['naive']['mean_abs_beta']:.3f} | "
                f"{v['ewma']['mean_abs_beta']:.3f} | {v['vasicek']['mean_abs_beta']:.3f} | "
                f"{v['model']['mean_abs_beta']:.3f} |"
            )
    lines += [
        "",
        "Signed mean realised beta after the hedge (the bias):",
        "",
        "| signal | window | unhedged | naive | ewma63 | vasicek | model-implied |",
        "|---|---|---|---|---|---|---|",
    ]
    for s, wins in bt.items():
        for w, v in wins.items():
            lines.append(
                f"| {s} | {w} | {v['mean_beta_unhedged']:.3f} | {v['naive']['mean_beta']:.3f} | "
                f"{v['ewma']['mean_beta']:.3f} | {v['vasicek']['mean_beta']:.3f} | "
                f"{v['model']['mean_beta']:.3f} |"
            )
    lines += [
        "",
        "## 3. Cross-check: residual PCA and variance explained",
        "",
        "Correlation-matrix PCA of the model residuals (names with >= 90% coverage in the year) "
        "against the same matrix with every column shuffled in time (null). Variance explained = "
        "1 - sum(e^2)/sum(r^2), pooled over the year's name-days.",
        "",
        "| year | days | names | var explained | weighted R2 (mean daily) | top1 | top5 | top20 | null top20 | excess top20 |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for y, v in px.items():
        lines.append(
            f"| {y} | {v['days']} | {v['names']} | {v['variance_explained_uncentred']:.3f} | "
            f"{(v['mean_weighted_r2'] or float('nan')):.3f} | {v['pca_top1_share']:.3f} | "
            f"{v['pca_top5_share']:.3f} | {v['pca_top20_share']:.3f} | {v['null_top20_share']:.3f} | "
            f"{v['top20_excess_over_null']:.3f} |"
        )
    lines += [
        "",
        "## 4. Runtime and peak memory",
        "",
        f"- model build: {rt['build_runtime_s']:.0f} s, peak RSS {rt['build_peak_rss_mb']:.0f} MB "
        "(under `run_capped.sh --mem 1.8G`)",
        f"- this validation: {rt['validation_runtime_s']:.0f} s, peak RSS {rt['validation_peak_rss_mb']:.0f} MB",
        f"- factors {res['model']['n_factors']} (market, {res['model']['n_groups']} industry groups, "
        f"{res['model']['n_styles']} styles)",
        "",
        "## Notes",
        "",
    ]
    lines += [f"- {n}" for n in res["notes"]]
    (OUT / "report.md").write_text("\n".join(lines) + "\n")


def main() -> None:
    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    meta = json.loads((DEFAULT_DIR / "risk/meta.json").read_text())
    rm = rk.RiskModel()
    prices = PricePanel.from_dir(include_etfs=True, load_open=False)
    spy_close = prices.close[:, prices.col("SPY")]
    spy_ret = np.full(len(spy_close), np.nan)
    spy_ret[1:] = spy_close[1:] / spy_close[:-1] - 1.0
    books = stage0_books(prices.dates)
    bias_df, beta_df = bias_and_beta(rm, prices, books, spy_ret)
    _log(f"bias rows {len(bias_df)}, beta rows {len(beta_df)}")
    bias = summarise_bias(bias_df)
    beta = summarise_beta(beta_df)
    pca = pca_and_variance(prices, meta)
    cov_cov = (
        bias_df[bias_df["set"].str.startswith("stage0")][["coverage_long", "coverage_short"]]
        .mean()
        .to_dict()
    )
    res = {
        "generated_utc": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
        "model": {
            "n_factors": len(meta["factors"]),
            "n_groups": len(meta["groups"]),
            "n_styles": len(meta["styles"]),
            "first_saved_date": "2017-07 (126 factor-return observations needed)",
        },
        "bias": bias,
        "beta": beta,
        "pca": pca,
        "stage0_name_coverage_in_model": cov_cov,
        "runtime": {
            "build_runtime_s": meta["runtime_s"],
            "build_peak_rss_mb": meta["peak_rss_mb"],
            "validation_runtime_s": time.time() - t0,
            "validation_peak_rss_mb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0,
        },
        "notes": [
            "Realised vol = std (ddof 1) of the 21 daily returns of a constant-weight portfolio; "
            "names without a price on a day contribute 0.",
            "Stage-0 books use only names present in the model cohort (U3000 with mcap > 0); "
            f"mean coverage {cov_cov}. Legs are re-equal-weighted over the covered names.",
            "Model beta is the beta to the cap-weighted U3000 portfolio, used as the SPY beta proxy.",
        ],
    }
    (OUT / "results.json").write_text(json.dumps(res, indent=1, default=float))
    write_report(res)
    bias_df.to_parquet(OUT / "bias_rows.parquet")
    beta_df.to_parquet(OUT / "beta_rows.parquet")
    _log(f"done in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
