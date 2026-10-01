# ruff: noqa: E501
"""D4: fit the half-spread model on the quote sample, write cost_model_v1.json + the report.

Inputs: ``data/research/equity_book/quotes/{plan.parquet,result/*.parquet}`` from
``scripts/sample_equity_book_spreads.py``.  Steps:

* ``ar``   -- optional: trailing 21-session Abdi-Ranaldo estimate for every sampled
  (day, symbol) from the daily bars (``spread_estimate_from_ohlc`` of
  ``run_t20260928_30_smallcap_ml_book.py``), for the comparison table.
* ``fit``  -- OLS per snapshot, 20% day holdout, deciles, ratios, year trend, comparison.

    scripts/run_capped.sh --mem 1.8G -- uv run python scripts/fit_equity_book_cost_model.py ar
    scripts/run_capped.sh --mem 1.8G -- uv run python scripts/fit_equity_book_cost_model.py fit
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from open_composer.research.equity_book import costs  # noqa: E402

QUOTES = ROOT / "data" / "research" / "equity_book" / "quotes"
AR_PATH = QUOTES / "ar_estimates.parquet"
MODEL_JSON = ROOT / "open_composer" / "research" / "equity_book" / "cost_model_v1.json"
REPORT_DIR = ROOT / "reports" / "research" / "program" / "cost-model-v1-2026-10-01"
HOLDOUT_FRAC = 0.2
HOLDOUT_SEED = 20261003
HS_MIN_BP, HS_MAX_BP = 0.01, 1000.0
SNAP_COLS = {"open": "open_hs_med_bp", "mid": "mid_hs_bp", "close": "close_hs_bp"}
FLAT_BP = 10.0


# --------------------------------------------------------------------------
# data
# --------------------------------------------------------------------------


def load_sample() -> pd.DataFrame:
    plan = pd.read_parquet(QUOTES / "plan.parquet")
    parts = [pd.read_parquet(p) for p in sorted((QUOTES / "result").glob("*.parquet"))]
    res = pd.concat(parts, ignore_index=True)
    df = res.merge(plan, on=["day", "symbol"], how="inner", suffixes=("", "_plan"))
    df["year"] = df["day"].str[:4].astype(int)
    df["tier_bp"] = costs.tiered_cost_bp(df["adv_rank"])
    if AR_PATH.exists():
        ar = pd.read_parquet(AR_PATH)
        df = df.merge(ar, on=["day", "symbol"], how="left")
    return df


def snapshot_frame(df: pd.DataFrame, snap: str) -> pd.DataFrame:
    col = SNAP_COLS[snap]
    d = df[np.isfinite(df[col]) & (df[col] >= HS_MIN_BP) & (df[col] <= HS_MAX_BP)].copy()
    d["hs_bp"] = d[col]
    for c in ("price", "dollar_adv_21", "vol_21"):
        d = d[np.isfinite(d[c]) & (d[c] > 0)]
    return d


def split_days(days: list[str]) -> tuple[list[str], list[str]]:
    rng = np.random.default_rng(HOLDOUT_SEED)
    days = sorted(days)
    n_hold = max(1, int(round(HOLDOUT_FRAC * len(days))))
    hold = sorted(rng.choice(np.asarray(days), n_hold, replace=False).tolist())
    return [d for d in days if d not in hold], hold


# --------------------------------------------------------------------------
# AR estimate for the comparison table
# --------------------------------------------------------------------------


def compute_ar(plan: pd.DataFrame) -> pd.DataFrame:
    import duckdb

    from open_composer.research.features import price_hygiene as ph
    from scripts.run_t20260928_30_smallcap_ml_book import spread_estimate_from_ohlc

    out = []
    for year, g in plan.groupby(plan["day"].str[:4].astype(int)):
        syms = sorted(set(g["symbol"]))
        lo = (pd.Timestamp(g["day"].min()) - pd.Timedelta(days=50)).date()
        hi = pd.Timestamp(g["day"].max()).date()
        frames = []
        for y in range(lo.year, year + 1):
            for root in (
                ROOT / "data" / "sip" / "daily" / str(y),
                ROOT / "data" / "sip-delisted" / "by_year" / str(y),
            ):
                if not list(root.glob("*.parquet")):
                    continue
                con = duckdb.connect()
                con.execute("SET memory_limit='1GB'; SET threads=2;")
                con.register("cand", pd.DataFrame({"symbol": syms}))
                cols = con.execute(f"DESCRIBE SELECT * FROM read_parquet('{root}/*.parquet')").df()[
                    "column_name"
                ]
                ghost = ph.ghost_bar_sql_predicate(list(cols))
                ghost_clause = f"AND NOT {ghost}" if ghost else ""
                frames.append(
                    con.execute(
                        f"""
                        SELECT symbol, CAST(timezone('America/New_York', "timestamp") AS DATE) AS date,
                               high, low, close
                        FROM read_parquet('{root}/*.parquet')
                        WHERE open > 0 AND high > 0 AND low > 0 AND close > 0 {ghost_clause}
                          AND symbol IN (SELECT symbol FROM cand)
                        """
                    ).df()
                )
                con.close()
        bars = pd.concat(frames, ignore_index=True)
        bars["date"] = pd.to_datetime(bars["date"])
        bars = bars[(bars["date"] >= pd.Timestamp(lo)) & (bars["date"] <= pd.Timestamp(hi))]
        bars = bars.drop_duplicates(["symbol", "date"], keep="last").sort_values(["symbol", "date"])
        est = {}
        for sym, b in bars.groupby("symbol"):
            s = spread_estimate_from_ohlc(
                b.set_index("date")["close"],
                b.set_index("date")["high"],
                b.set_index("date")["low"],
            )
            est[sym] = s
        for _, r in g.iterrows():
            s = est.get(r["symbol"])
            val = np.nan
            if s is not None:
                prior = s[s.index <= pd.Timestamp(r["prior_session"])]
                if len(prior) and prior.index[-1] == pd.Timestamp(r["prior_session"]):
                    val = float(prior.iloc[-1])
            out.append({"day": r["day"], "symbol": r["symbol"], "ar_spread_frac": val})
        print(f"AR {year}: {len(g)} rows", flush=True)
    df = pd.DataFrame(out)
    df["ar_half_bp"] = df["ar_spread_frac"] * 0.5 * 1e4  # AR spread is a full-spread fraction
    return df


# --------------------------------------------------------------------------
# fit + evaluation
# --------------------------------------------------------------------------


def predict(coef: dict[str, Any], d: pd.DataFrame, smear: bool = False) -> np.ndarray:
    return costs.predict_half_spread_bp(
        coef, d["price"], d["dollar_adv_21"], d["vol_21"], d["year"], smear=smear
    )


def decile_table(d: pd.DataFrame, pred: np.ndarray) -> list[dict[str, Any]]:
    d = d.assign(pred=pred)
    rows = []
    for dec, g in d.groupby("decile"):
        rows.append(
            {
                "decile": int(dec),
                "n": int(len(g)),
                "median_adv_rank": float(g["adv_rank"].median()),
                "median_price": float(g["price"].median()),
                "median_dollar_adv_21": float(g["dollar_adv_21"].median()),
                "realized_median_bp": float(g["hs_bp"].median()),
                "realized_mean_bp": float(g["hs_bp"].mean()),
                "predicted_median_bp": float(g["pred"].median()),
                "pred_over_realized_median": float(g["pred"].median() / g["hs_bp"].median()),
                "median_abs_log_error": float(np.median(np.abs(np.log(g["pred"] / g["hs_bp"])))),
            }
        )
    return rows


def fit_snapshot(df: pd.DataFrame, snap: str) -> dict[str, Any]:
    d = snapshot_frame(df, snap)
    days = sorted(set(d["day"]))
    train_days, hold_days = split_days(days)
    tr, ho = d[d["day"].isin(train_days)], d[d["day"].isin(hold_days)]
    kw = lambda x: (x["hs_bp"], x["price"], x["dollar_adv_21"], x["vol_21"], x["year"])  # noqa: E731
    c_tr = costs.fit_log_linear(*kw(tr))
    # holdout accuracy (train-only fit); baselines on the same holdout rows
    pred_ho = predict(c_tr, ho)
    err = np.abs(np.log(pred_ho / ho["hs_bp"]))
    base_const = float(np.exp(np.log(tr["hs_bp"]).mean()))
    base_dec = tr.groupby("decile")["hs_bp"].median()
    pred_dec = ho["decile"].map(base_dec).to_numpy()
    holdout = {
        "n_days_train": len(train_days),
        "n_days_holdout": len(hold_days),
        "holdout_days": hold_days,
        "n_train": int(len(tr)),
        "n_holdout": int(len(ho)),
        "median_abs_log_error": float(np.median(err)),
        "mean_abs_log_error": float(np.mean(err)),
        "median_abs_log_error_constant_baseline": float(
            np.median(np.abs(np.log(base_const / ho["hs_bp"])))
        ),
        "median_abs_log_error_decile_median_baseline": float(
            np.median(np.abs(np.log(pred_dec / ho["hs_bp"])))
        ),
        "median_pred_over_realized": float(np.median(pred_ho) / np.median(ho["hs_bp"])),
        "calibration_by_decile": decile_table(ho, pred_ho),
        "r2_train_log": c_tr["r2"],
    }
    # final fit on all rows
    coef = costs.fit_log_linear(*kw(d))
    pred_all = predict(coef, d)
    pred_mean = predict(coef, d, smear=True)
    return {
        "coef": coef,
        "train_only_coef": c_tr,
        "holdout": holdout,
        "in_sample_calibration_by_decile": decile_table(d, pred_all),
        "n_rows": int(len(d)),
        "n_days": len(days),
        "frame": d.assign(pred=pred_all, pred_mean=pred_mean),
    }


def ratios_and_trend(df: pd.DataFrame) -> dict[str, Any]:
    ok = df[
        np.isfinite(df["open_hs_med_bp"])
        & np.isfinite(df["mid_hs_bp"])
        & np.isfinite(df["close_hs_bp"])
    ]
    ok = ok[(ok["open_hs_med_bp"] > 0) & (ok["mid_hs_bp"] > 0) & (ok["close_hs_bp"] > 0)]
    r_om = ok["open_hs_med_bp"] / ok["mid_hs_bp"]
    r_oc = ok["open_hs_med_bp"] / ok["close_hs_bp"]
    r_mc = ok["mid_hs_bp"] / ok["close_hs_bp"]
    out: dict[str, Any] = {
        "n_paired": int(len(ok)),
        "median_ratio_open_over_mid": float(r_om.median()),
        "median_ratio_open_over_close": float(r_oc.median()),
        "median_ratio_mid_over_close": float(r_mc.median()),
        "ratio_of_medians_open_over_mid": float(
            ok["open_hs_med_bp"].median() / ok["mid_hs_bp"].median()
        ),
        "ratio_of_medians_open_over_close": float(
            ok["open_hs_med_bp"].median() / ok["close_hs_bp"].median()
        ),
        "geo_mean_ratio_open_over_mid": float(np.exp(np.log(r_om).mean())),
        "geo_mean_ratio_open_over_close": float(np.exp(np.log(r_oc).mean())),
    }
    by_dec = []
    for dec, g in ok.groupby("decile"):
        by_dec.append(
            {
                "decile": int(dec),
                "n": int(len(g)),
                "open_median_bp": float(g["open_hs_med_bp"].median()),
                "mid_median_bp": float(g["mid_hs_bp"].median()),
                "close_median_bp": float(g["close_hs_bp"].median()),
                "median_ratio_open_over_mid": float(
                    (g["open_hs_med_bp"] / g["mid_hs_bp"]).median()
                ),
                "median_ratio_open_over_close": float(
                    (g["open_hs_med_bp"] / g["close_hs_bp"]).median()
                ),
            }
        )
    out["by_decile"] = by_dec
    trend = []
    for yr, g in ok.groupby("year"):
        trend.append(
            {
                "year": int(yr),
                "n": int(len(g)),
                "n_days": int(g["day"].nunique()),
                "open_median_bp": float(g["open_hs_med_bp"].median()),
                "mid_median_bp": float(g["mid_hs_bp"].median()),
                "close_median_bp": float(g["close_hs_bp"].median()),
                "median_ratio_open_over_mid": float(
                    (g["open_hs_med_bp"] / g["mid_hs_bp"]).median()
                ),
            }
        )
    out["trend_by_year"] = trend
    return out


def comparison_by_decile(frames: dict[str, pd.DataFrame]) -> dict[str, Any]:
    """Per decile and snapshot: realized median half spread vs the model, flat 10 bp,
    tiered 3/6/12/25 and the daily-bar Abdi-Ranaldo half spread (when computed)."""
    out: dict[str, Any] = {}
    for snap, d in frames.items():
        rows = []
        for dec, g in d.groupby("decile"):
            real = float(g["hs_bp"].median())
            real_mean = float(g["hs_bp"].mean())
            row = {
                "decile": int(dec),
                "n": int(len(g)),
                "median_adv_rank": float(g["adv_rank"].median()),
                "realized_half_spread_median_bp": real,
                "realized_half_spread_mean_bp": real_mean,
                "model_half_spread_median_bp": float(g["pred"].median()),
                "model_half_spread_mean_bp": float(g["pred_mean"].mean()),
                "model_per_side_cost_incl_fee_bp": float(
                    g["pred_mean"].mean() + costs.FEES_BP_PER_SIDE
                ),
                "flat_bp": FLAT_BP,
                "flat_over_realized_mean": FLAT_BP / real_mean,
                "flat_over_realized_median": FLAT_BP / real,
                "tiered_mean_bp": float(g["tier_bp"].mean()),
                "tiered_over_realized_mean": float(g["tier_bp"].mean() / real_mean),
            }
            if "ar_half_bp" in g.columns and g["ar_half_bp"].notna().any():
                ar = float(g["ar_half_bp"].median())
                row["ar_half_spread_median_bp"] = ar
                row["ar_over_realized_median"] = ar / real
                row["ar_over_realized_mean"] = float(g["ar_half_bp"].mean()) / real_mean
            rows.append(row)
        # sample-weighted means of per-side costs across the pool
        out[snap] = {
            "rows": rows,
            "pool_median_realized_bp": float(d["hs_bp"].median()),
            "pool_mean_realized_bp": float(d["hs_bp"].mean()),
            "pool_mean_model_bp": float(d["pred_mean"].mean()),
            "pool_mean_model_median_pred_bp": float(d["pred"].mean()),
            "pool_mean_tiered_bp": float(d["tier_bp"].mean()),
            "flat_bp": FLAT_BP,
        }
    return out


def run_fit() -> dict[str, Any]:
    df = load_sample()
    fits = {s: fit_snapshot(df, s) for s in costs.SNAPSHOTS}
    # sensitivity: as-printed price (open-window quote mid) instead of the adjusted close
    raw_df = df.assign(price=df["open_mid_med"])
    raw_fits = {s: fit_snapshot(raw_df, s) for s in costs.SNAPSHOTS}
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    model = {
        "version": "v1",
        "fit_date_utc": now,
        "model": "log(hs_bp) = a + b*log(price) + c*log(dollar_adv_21) + d*log(vol_21) + year effect",
        "inputs": "data/features/daily_broad prior session: close (split adjusted), dollar_adv_21, vol_21 (daily return std)",
        "target": "(ask - bid) / 2 / mid * 1e4; open = median of valid quotes 09:35-09:45 ET, mid = last valid quote before 12:00 (60 s), close = last valid quote before 15:45 (60 s)",
        "sample": {
            "n_days": int(df["day"].nunique()),
            "n_symbol_days": int(len(df)),
            "seed": 20261001,
            "days": sorted(df["day"].unique().tolist()),
        },
        "snapshots": {s: fits[s]["coef"] for s in costs.SNAPSHOTS},
        "snapshots_printed_price": {s: raw_fits[s]["coef"] for s in costs.SNAPSHOTS},
        "price_basis_note": (
            "'snapshots' use the adjusted daily_broad close (default, what the panel carries); "
            "'snapshots_printed_price' were fitted on the as-printed price (open-window quote mid) "
            "and fit better, use only with unadjusted prices"
        ),
    }
    for s in costs.SNAPSHOTS:
        model["snapshots"][s]["n_days"] = fits[s]["n_days"]
    frames = {s: fits[s]["frame"] for s in costs.SNAPSHOTS}
    results = {
        "fit_date_utc": now,
        "n_days": int(df["day"].nunique()),
        "n_symbol_days": int(len(df)),
        "coverage": {
            s: {
                "n_valid": int(fits[s]["n_rows"]),
                "share_of_rows": float(fits[s]["n_rows"] / len(df)),
            }
            for s in costs.SNAPSHOTS
        },
        "coefficients": {s: fits[s]["coef"] for s in costs.SNAPSHOTS},
        "holdout": {s: fits[s]["holdout"] for s in costs.SNAPSHOTS},
        "in_sample_calibration_by_decile": {
            s: fits[s]["in_sample_calibration_by_decile"] for s in costs.SNAPSHOTS
        },
        "sensitivity_printed_price": {
            s: {
                "coef": {
                    k: raw_fits[s]["coef"][k]
                    for k in ("a", "b_log_price", "c_log_dollar_adv_21", "d_log_vol_21", "r2")
                },
                "holdout_median_abs_log_error": raw_fits[s]["holdout"]["median_abs_log_error"],
            }
            for s in costs.SNAPSHOTS
        },
        "ratios": ratios_and_trend(df),
        "comparison": comparison_by_decile(frames),
        "ar_available": bool("ar_half_bp" in df.columns),
        "price_basis_check": {
            "median_quote_mid_over_adjusted_close_open_window": float(
                (df["open_mid_med"] / df["price"]).median()
            ),
            "share_ratio_outside_0.9_1.1": float(
                ((df["open_mid_med"] / df["price"]).dropna().sub(1).abs() > 0.10).mean()
            ),
        },
    }
    MODEL_JSON.write_text(json.dumps(model, indent=2), encoding="utf-8")
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / "results.json").write_text(
        json.dumps(results, indent=2, default=lambda o: None), encoding="utf-8"
    )
    return results


def _fmt(x: Any, nd: int = 2) -> str:
    return "n/a" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f"{x:.{nd}f}"


def write_report(res: dict[str, Any]) -> None:
    L: list[str] = []
    L.append("# Cost model v1 (D4): measured half spreads, 2026-10-01\n")
    L.append(
        "Source files: `results.json` (this directory), `open_composer/research/equity_book/"
        "cost_model_v1.json`, sample `data/research/equity_book/quotes/`. Code: "
        "`scripts/sample_equity_book_spreads.py`, `scripts/fit_equity_book_cost_model.py`, "
        "`open_composer/research/equity_book/costs.py`.\n"
    )
    L.append(
        f"Sample: {res['n_days']} random NYSE sessions (stratified by year, seed 20261001), "
        f"{res['n_symbol_days']} symbol-days, 30 random symbols per liquidity decile of the "
        "U3000 pool of each day (the pool is about 2,200 names after the close >= $5 / not-fund / "
        "252-session filters; deciles are equal-count within it). Half spread in bp = "
        "(ask - bid) / 2 / mid x 1e4 on SIP NBBO, valid quotes only (bid > 0, ask > bid). "
        "open = median over valid quotes 09:35-09:45 ET; mid = last valid quote before 12:00 "
        "(<= 60 s); close = last valid quote before 15:45 (<= 60 s).\n"
    )
    op = res["comparison"]["open"]
    first_over = next(
        (r["decile"] for r in op["rows"] if r["realized_half_spread_mean_bp"] > FLAT_BP), None
    )
    L.append("## Summary\n")
    L.append(
        f"- Open-window half spread (what a next-open fill faces) averages "
        f"{_fmt(op['pool_mean_realized_bp'], 1)} bp over the pool (median "
        f"{_fmt(op['pool_median_realized_bp'], 1)} bp): {_fmt(res['ratios']['ratio_of_medians_open_over_mid'], 1)}x "
        f"the 12:00 value and {_fmt(res['ratios']['ratio_of_medians_open_over_close'], 1)}x the 15:45 value.\n"
        f"- The flat 10 bp per side covers the realized mean open half spread only up to decile "
        f"{(first_over - 1) if first_over else 'all'} (0 = most liquid); beyond that it understates it "
        f"(decile 9: {_fmt(op['rows'][-1]['realized_half_spread_mean_bp'], 1)} bp). It overstates mid-day and "
        f"close costs for most deciles. The 3/6/12/25 tiers are "
        f"{_fmt(min(r['tiered_over_realized_mean'] for r in op['rows']), 2)}x to "
        f"{_fmt(max(r['tiered_over_realized_mean'] for r in op['rows']), 2)}x the realized open mean "
        f"by decile (below it where under 1) and "
        f"{_fmt(min(r['tiered_over_realized_mean'] for r in res['comparison']['mid']['rows']), 2)}x to "
        f"{_fmt(max(r['tiered_over_realized_mean'] for r in res['comparison']['mid']['rows']), 2)}x the mid-day mean.\n"
        f"- Holdout median absolute log error: open {_fmt(res['holdout']['open']['median_abs_log_error'], 2)}, "
        f"mid {_fmt(res['holdout']['mid']['median_abs_log_error'], 2)}, close "
        f"{_fmt(res['holdout']['close']['median_abs_log_error'], 2)} (constant baseline "
        f"{_fmt(res['holdout']['open']['median_abs_log_error_constant_baseline'], 2)} / "
        f"{_fmt(res['holdout']['mid']['median_abs_log_error_constant_baseline'], 2)} / "
        f"{_fmt(res['holdout']['close']['median_abs_log_error_constant_baseline'], 2)}): i.e. a typical name is "
        f"predicted within a factor of about {_fmt(float(np.exp(res['holdout']['open']['median_abs_log_error'])), 2)} "
        f"at the open. The model prices the liquidity ladder, not individual-name spreads.\n"
        "- Measured on NBBO quotes in a 10-minute window after the open, not on auction fills: "
        "a market-on-open or opening-auction fill may be tighter or wider; this is the quote cost "
        "of trading just after 09:35.\n"
    )
    L.append("## Coefficients\n")
    L.append(
        "log(hs_bp) = a + b log(price) + c log(dollar_adv_21) + d log(vol_21) + year effects\n"
    )
    L.append("| snapshot | n | a | b price | c dollar_adv_21 | d vol_21 | R2 | resid sd |")
    L.append("|---|---|---|---|---|---|---|---|")
    for sn in costs.SNAPSHOTS:
        c = res["coefficients"][sn]
        L.append(
            f"| {sn} | {c['n']} | {_fmt(c['a'], 3)} | {_fmt(c['b_log_price'], 3)} | "
            f"{_fmt(c['c_log_dollar_adv_21'], 3)} | {_fmt(c['d_log_vol_21'], 3)} | "
            f"{_fmt(c['r2'], 3)} | {_fmt(c['resid_sd'], 3)} |"
        )
    L.append("\nYear effects (baseline 2018): ")
    for sn in costs.SNAPSHOTS:
        ye = res["coefficients"][sn]["year_effects"]
        L.append(f"- {sn}: " + ", ".join(f"{k}: {v:+.3f}" for k, v in ye.items()))
    L.append("\n## Holdout (20% of days, train-only fit)\n")
    L.append(
        "| snapshot | holdout days | holdout rows | median abs log error | constant baseline | "
        "decile-median baseline | median pred / realized |"
    )
    L.append("|---|---|---|---|---|---|---|")
    for sn in costs.SNAPSHOTS:
        h = res["holdout"][sn]
        L.append(
            f"| {sn} | {h['n_days_holdout']} | {h['n_holdout']} | {_fmt(h['median_abs_log_error'], 3)} | "
            f"{_fmt(h['median_abs_log_error_constant_baseline'], 3)} | "
            f"{_fmt(h['median_abs_log_error_decile_median_baseline'], 3)} | "
            f"{_fmt(h['median_pred_over_realized'], 3)} |"
        )
    L.append("\n## Calibration by liquidity decile on the holdout (median bp; 0 = most liquid)\n")
    for sn in costs.SNAPSHOTS:
        L.append(f"### {sn}\n")
        L.append(
            "| decile | n | realized median | predicted median | pred / realized | median abs log err |"
        )
        L.append("|---|---|---|---|---|---|")
        for r in res["holdout"][sn]["calibration_by_decile"]:
            L.append(
                f"| {r['decile']} | {r['n']} | {_fmt(r['realized_median_bp'])} | "
                f"{_fmt(r['predicted_median_bp'])} | {_fmt(r['pred_over_realized_median'], 3)} | "
                f"{_fmt(r['median_abs_log_error'], 3)} |"
            )
        L.append("")
    L.append("## Realized half spread by decile and comparison with the flat and tiered costs\n")
    L.append(
        "Realized mean = mean over the sample of the per-name half spread (what a trade pays on average); "
        "model mean = Duan-smeared mean prediction. Per-side cost = half spread (+ fee 0.5 bp in the model column). Flat = 10 bp per side; "
        "tiered = 3/6/12/25 bp for adv_rank <= 500/1000/1500/beyond "
        "(`run_h20260929_21_lockup_books.py`). AR = trailing 21-session daily-bar "
        "Abdi-Ranaldo half spread (0.5 x spread), the estimator data pitfall #58 calls 20-60x "
        "too high for large caps.\n"
    )
    for sn in costs.SNAPSHOTS:
        comp = res["comparison"][sn]
        L.append(f"### {sn} (all in bp)\n")
        L.append(
            "| decile | n | median adv_rank | realized median | realized mean | model mean | "
            "model per side (+0.5 fee) | flat | flat / realized mean | tiered mean | tiered / realized mean | "
            "AR half (median) | AR / realized median |"
        )
        L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        for r in comp["rows"]:
            L.append(
                f"| {r['decile']} | {r['n']} | {_fmt(r['median_adv_rank'], 0)} | "
                f"{_fmt(r['realized_half_spread_median_bp'])} | {_fmt(r['realized_half_spread_mean_bp'])} | "
                f"{_fmt(r['model_half_spread_mean_bp'])} | {_fmt(r['model_per_side_cost_incl_fee_bp'])} | "
                f"{_fmt(r['flat_bp'], 1)} | {_fmt(r['flat_over_realized_mean'], 2)}x | "
                f"{_fmt(r['tiered_mean_bp'], 1)} | {_fmt(r['tiered_over_realized_mean'], 2)}x | "
                f"{_fmt(r.get('ar_half_spread_median_bp'))} | {_fmt(r.get('ar_over_realized_median'), 1)}x |"
            )
        L.append(
            f"\nPool: median realized {_fmt(comp['pool_median_realized_bp'])} bp, mean "
            f"{_fmt(comp['pool_mean_realized_bp'])} bp, model mean {_fmt(comp['pool_mean_model_bp'])} bp, "
            f"tiered mean {_fmt(comp['pool_mean_tiered_bp'])} bp, flat {_fmt(comp['flat_bp'], 1)} bp.\n"
        )
    rt = res["ratios"]
    L.append("## Open vs mid vs close\n")
    L.append(
        f"Paired rows (all three snapshots valid): {rt['n_paired']}. Median of per-name ratios: "
        f"open/mid {_fmt(rt['median_ratio_open_over_mid'], 2)}, open/close "
        f"{_fmt(rt['median_ratio_open_over_close'], 2)}, mid/close {_fmt(rt['median_ratio_mid_over_close'], 2)}. "
        f"Ratio of pooled medians: open/mid {_fmt(rt['ratio_of_medians_open_over_mid'], 2)}, "
        f"open/close {_fmt(rt['ratio_of_medians_open_over_close'], 2)}. Geometric means: "
        f"open/mid {_fmt(rt['geo_mean_ratio_open_over_mid'], 2)}, open/close "
        f"{_fmt(rt['geo_mean_ratio_open_over_close'], 2)}.\n"
    )
    L.append(
        "| decile | n | open median | mid median | close median | open/mid (median ratio) | open/close |"
    )
    L.append("|---|---|---|---|---|---|---|")
    for r in rt["by_decile"]:
        L.append(
            f"| {r['decile']} | {r['n']} | {_fmt(r['open_median_bp'])} | {_fmt(r['mid_median_bp'])} | "
            f"{_fmt(r['close_median_bp'])} | {_fmt(r['median_ratio_open_over_mid'], 2)} | "
            f"{_fmt(r['median_ratio_open_over_close'], 2)} |"
        )
    L.append("\n## Trend by year (median half spread, bp, all deciles pooled)\n")
    L.append("| year | days | n | open | mid | close | open/mid |")
    L.append("|---|---|---|---|---|---|---|")
    for r in rt["trend_by_year"]:
        L.append(
            f"| {r['year']} | {r['n_days']} | {r['n']} | {_fmt(r['open_median_bp'])} | "
            f"{_fmt(r['mid_median_bp'])} | {_fmt(r['close_median_bp'])} | "
            f"{_fmt(r['median_ratio_open_over_mid'], 2)} |"
        )
    L.append("\n## Sensitivity: as-printed price instead of the adjusted close\n")
    L.append(
        "| snapshot | b price (adjusted, main) | b price (printed) | R2 printed | holdout median abs log error printed |"
    )
    L.append("|---|---|---|---|---|")
    for sn in costs.SNAPSHOTS:
        sp_ = res["sensitivity_printed_price"][sn]
        L.append(
            f"| {sn} | {_fmt(res['coefficients'][sn]['b_log_price'], 3)} | {_fmt(sp_['coef']['b_log_price'], 3)} | "
            f"{_fmt(sp_['coef']['r2'], 3)} | {_fmt(sp_['holdout_median_abs_log_error'], 3)} |"
        )
    pb = res["price_basis_check"]
    L.append(
        "\n## Caveats\n\n"
        "- The `price` regressor is the split-adjusted `daily_broad` close of the prior session "
        "(the field the backtest panel will carry; it is back-adjusted (splits, and with the vendor's adjustment=all also dividends), so for old sessions it sits below the as-printed price). Median open-window quote mid / that close = "
        f"{_fmt(pb['median_quote_mid_over_adjusted_close_open_window'], 3)}; share of rows more "
        f"than 10% apart (later splits, overnight gaps): {_fmt(pb['share_ratio_outside_0.9_1.1'], 3)}.\n"
        "- Seven to eight sessions per year, 300 names per session: year effects and the 2026 "
        "level rest on 4 sessions. Spreads are measured on NBBO quotes, not on fills; no "
        "queue/adverse-selection effect, no auction fills.\n"
        "- AR comparison: the sample's most liquid decile has median adv_rank about 150, so the "
        "ratios above (about 1x to 12.6x) are for mid-caps and large-caps outside the top 100; "
        "the 20-60x of data pitfall #58 refers to mega-caps and is not tested here.\n"
        "- Open-window raw quotes (10^5 to 10^6 per batch) are not stored; per-name aggregates are.\n"
    )
    (REPORT_DIR / "report.md").write_text("\n".join(L), encoding="utf-8")


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "ar":
        plan = pd.read_parquet(QUOTES / "plan.parquet")
        done = {p.name[:10] for p in (QUOTES / "result").glob("*.parquet")}
        plan = plan[plan["day"].isin(done)] if "--done-only" in sys.argv else plan
        compute_ar(plan).to_parquet(AR_PATH, index=False)
        print("wrote", AR_PATH)
        return 0
    if cmd == "fit":
        res = run_fit()
        write_report(res)
        print(json.dumps({k: res[k] for k in ("n_days", "n_symbol_days", "coverage")}, indent=1))
        for s in costs.SNAPSHOTS:
            c, h = res["coefficients"][s], res["holdout"][s]
            print(
                s,
                {
                    k: round(c[k], 3)
                    for k in ("a", "b_log_price", "c_log_dollar_adv_21", "d_log_vol_21")
                },
                "r2",
                round(c["r2"], 3),
                "holdout MALE",
                round(h["median_abs_log_error"], 3),
                "const",
                round(h["median_abs_log_error_constant_baseline"], 3),
            )
        return 0
    print("usage: ar [--done-only] | fit")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
