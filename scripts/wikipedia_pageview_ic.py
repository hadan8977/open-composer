#!/usr/bin/env python3
"""T-20260929-71 cheapest negation test: weekly RankIC of Wikipedia page-view change.

Frozen design (direction-review.json / hypotheses.md of h20260929_71_wikipedia_pageviews):

* VC7_28(d) = ln((sum views d-6..d + 1) / (7 * mean views d-34..d-7 + 1)); valid only if the
  prior-28-day mean is >= 20 views/day.  VC28_90 (control) = ln((sum d-27..d + 1) /
  (28 * mean d-117..d-28 + 1)), same validity rule on the 90-day mean.
* Views of UTC day d are complete only after d ends, so the signal of trading day t is used
  from the close of t: fill at the open of t+1+lag, return open(t+1+lag) -> open(t+6+lag),
  minus SPY over the same window.  Formation on every 5th trading day at offsets 0..4.
* RankIC = cross-sectional Spearman per formation date (>= 100 names), Newey-West (Bartlett,
  4 lags) t on the weekly IC series, per offset; statistics reported are the median across
  the five offsets.  Segments by formation date: <= 2023-12-31 and >= 2024-01-08.
* Placebo: 500 permutations of the stock <-> title assignment (seed 20260929); the statistic is
  the median-offset 2024+ mean IC at the gating lag 0.
* Continue only if (a) 2024+ IC > 0 with t >= 2.5, (b) 2016-2023 IC > 0, (c) real 2024+ IC above
  the 95th percentile of the placebo distribution.  All at lag 0.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import rankdata

ITER = "h20260929_71_wikipedia_pageviews"
DATA = Path("data/wikipedia_pageviews")
OUT = Path("reports/research/iterations") / ITER / "results.json"
MIN_MEAN_VIEWS = 20.0
MIN_NAMES = 100
SEG1_END = pd.Timestamp("2023-12-31")
SEG2_START = pd.Timestamp("2024-01-08")
N_PLACEBO = 500
SEED = 20260929
NW_LAGS = 4
OFFSETS = (0, 1, 2, 3, 4)
DROP_FALL = 0.90  # series dropped if its 28-day mean views fell by more than this in 90 days


# --------------------------------------------------------------------------- signals


def load_views(data_dir: Path) -> tuple[pd.DataFrame, list[str]]:
    """Wide (calendar day x ticker) view counts; missing days are zero; empty series dropped."""
    frames: dict[str, pd.Series] = {}
    empty: list[str] = []
    for path in sorted(data_dir.glob("*.parquet")):
        df = pd.read_parquet(path)
        if df.empty:
            empty.append(path.stem)
            continue
        s = pd.Series(df["views"].to_numpy(dtype=float), index=pd.to_datetime(df["date"]))
        frames[path.stem] = s
    wide = pd.DataFrame(frames)
    full = pd.date_range(wide.index.min(), wide.index.max(), freq="D")
    return wide.reindex(full).fillna(0.0), empty


def vc7_28(views: pd.DataFrame) -> pd.DataFrame:
    s7 = views.rolling(7).sum()
    m28 = views.shift(7).rolling(28).mean()
    sig = np.log((s7 + 1.0) / (7.0 * m28 + 1.0))
    return sig.where(m28 >= MIN_MEAN_VIEWS)


def vc28_90(views: pd.DataFrame) -> pd.DataFrame:
    s28 = views.rolling(28).sum()
    m90 = views.shift(28).rolling(90).mean()
    sig = np.log((s28 + 1.0) / (28.0 * m90 + 1.0))
    return sig.where(m90 >= MIN_MEAN_VIEWS)


def drop_list(views: pd.DataFrame) -> dict[str, dict]:
    """Series whose 28-day mean views fell by more than 90% within 90 days (rename breaks)."""
    r = views.rolling(28).mean()
    prior = r.shift(90)
    ratio = (r / prior).where(prior >= MIN_MEAN_VIEWS)
    out: dict[str, dict] = {}
    for col in views.columns:
        col_ratio = ratio[col].dropna()
        if col_ratio.empty:
            continue
        worst = col_ratio.min()
        if worst < 1.0 - DROP_FALL:
            out[col] = {
                "min_ratio_28d_mean_vs_90d_earlier": float(worst),
                "date": str(col_ratio.idxmin().date()),
            }
    return out


# --------------------------------------------------------------------------- statistics


def nw_t(x: np.ndarray, lags: int = NW_LAGS) -> float:
    """Newey-West (Bartlett) t-stat of the mean of ``x`` (NaNs removed)."""
    x = x[np.isfinite(x)]
    n = len(x)
    if n < lags + 2:
        return float("nan")
    e = x - x.mean()
    s = float(e @ e) / n
    for lag in range(1, lags + 1):
        w = 1.0 - lag / (lags + 1.0)
        s += 2.0 * w * float(e[lag:] @ e[:-lag]) / n
    if s <= 0:
        return float("nan")
    return float(x.mean() / np.sqrt(s / n))


def rank_ic_rows(sig: np.ndarray, exc: np.ndarray, min_names: int = MIN_NAMES) -> np.ndarray:
    """Row-wise Spearman correlation on the jointly valid entries; NaN if too few names."""
    valid = np.isfinite(sig) & np.isfinite(exc)
    s = np.where(valid, sig, np.nan)
    e = np.where(valid, exc, np.nan)
    rs = rankdata(s, axis=1, nan_policy="omit")
    re_ = rankdata(e, axis=1, nan_policy="omit")
    n = valid.sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        ms = np.nanmean(rs, axis=1, keepdims=True)
        me = np.nanmean(re_, axis=1, keepdims=True)
        ds = rs - ms
        de = re_ - me
        num = np.nansum(ds * de, axis=1)
        den = np.sqrt(np.nansum(ds * ds, axis=1) * np.nansum(de * de, axis=1))
        ic = num / den
    return np.where(n >= min_names, ic, np.nan)


def formation_frame(
    dates: pd.DatetimeIndex,
    open_: np.ndarray,
    spy_col: int,
    offset: int,
    lag: int,
    horizon: int = 5,
) -> tuple[np.ndarray, np.ndarray]:
    """Formation trading-day indices and the SPY-excess open-to-open returns per stock."""
    t = np.arange(offset, len(dates), 5)
    e = t + 1 + lag
    x = e + horizon
    keep = x < len(dates)
    t, e, x = t[keep], e[keep], x[keep]
    with np.errstate(invalid="ignore", divide="ignore"):
        ret = open_[x] / open_[e] - 1.0
    exc = ret - ret[:, [spy_col]]
    return t, exc


def segment_stats(dates: pd.DatetimeIndex, ic: np.ndarray) -> dict[str, dict]:
    seg1 = dates <= SEG1_END
    seg2 = dates >= SEG2_START
    out = {}
    for name, mask in (("seg_2016_07_to_2023_12", seg1), ("seg_2024_01_08_onward", seg2)):
        x = ic[mask]
        x = x[np.isfinite(x)]
        out[name] = {
            "n_weeks": int(len(x)),
            "ic_mean": float(x.mean()) if len(x) else float("nan"),
            "nw_t": nw_t(x),
        }
    return out


def median_over_offsets(per_offset: dict[int, dict[str, dict]]) -> dict[str, dict]:
    out = {}
    for seg in next(iter(per_offset.values())):
        ics = [per_offset[o][seg]["ic_mean"] for o in per_offset]
        ts = [per_offset[o][seg]["nw_t"] for o in per_offset]
        out[seg] = {
            "ic_mean_median_offset": float(np.nanmedian(ics)),
            "nw_t_median_offset": float(np.nanmedian(ts)),
            "ic_mean_by_offset": [float(v) for v in ics],
            "nw_t_by_offset": [float(v) for v in ts],
        }
    return out


def gate(real: dict[str, dict], placebo_p95: float) -> dict:
    s1 = real["seg_2016_07_to_2023_12"]
    s2 = real["seg_2024_01_08_onward"]
    a = bool(s2["ic_mean_median_offset"] > 0 and s2["nw_t_median_offset"] >= 2.5)
    b = bool(s1["ic_mean_median_offset"] > 0)
    c = bool(s2["ic_mean_median_offset"] > placebo_p95)
    return {
        "a_2024_ic_positive_and_t_ge_2_5": a,
        "b_2016_2023_same_sign_positive": b,
        "c_real_2024_ic_above_placebo_p95": c,
        "pass": a and b and c,
    }


# --------------------------------------------------------------------------- driver


def ic_for(
    dates: pd.DatetimeIndex,
    open_: np.ndarray,
    spy_col: int,
    sig_full: np.ndarray,
    stock_cols: list[int],
    lag: int,
    perm: np.ndarray | None = None,
) -> dict[int, dict[str, dict]]:
    per_offset: dict[int, dict[str, dict]] = {}
    for o in OFFSETS:
        t, exc = formation_frame(dates, open_, spy_col, o, lag)
        sig = sig_full[t]
        if perm is not None:
            sig = sig[:, perm]
        ic = rank_ic_rows(sig, exc[:, stock_cols])
        per_offset[o] = segment_stats(dates[t], ic)
    return per_offset


def load_spy_open(dates: pd.DatetimeIndex) -> np.ndarray:
    """SPY open on the market trading dates (SIP daily, through sanitize_price_matrices)."""
    import duckdb

    from open_composer.research.features.price_hygiene import sanitize_price_matrices

    con = duckdb.connect()
    try:
        df = con.execute(
            "SELECT CAST(timestamp AT TIME ZONE 'America/New_York' AS DATE) AS d, open, close "
            "FROM read_parquet('data/sip/daily/20*/*.parquet') WHERE symbol = 'SPY'"
        ).df()
    finally:
        con.close()
    df["d"] = pd.to_datetime(df["d"])
    df = df.drop_duplicates("d").set_index("d").sort_index().reindex(dates)
    c, o, _ = sanitize_price_matrices(df[["close"]], df[["open"]])
    return o["open"].to_numpy(dtype=np.float64)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", type=Path, default=DATA)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--placebos", type=int, default=N_PLACEBO)
    ap.add_argument("--allow-partial", action="store_true")
    args = ap.parse_args(argv)

    from open_composer.research.signal_card import load_market

    title_map = json.loads((args.data / "_title_map.json").read_text())
    views, empty = load_views(args.data)
    n_list = len(title_map)
    seen_titles: dict[str, str] = {}
    dup_titles: dict[str, str] = {}
    for row in title_map:
        if row["title"] in seen_titles:
            dup_titles[row["ticker"]] = seen_titles[row["title"]]
        else:
            seen_titles[row["title"]] = row["ticker"]
    have = [t for t in views.columns if t not in dup_titles]
    drops = drop_list(views[have])
    kept = [t for t in have if t not in drops]

    market = load_market(top_n=3000)
    data_last = str(market.dates[-1].date())
    sym_index = market.symbols
    matched, unmatched, sip_alias = [], [], {}
    for t in kept:
        for cand in (t, t.replace(".", "-"), t.replace(".", "")):
            if cand in sym_index:
                matched.append(t)
                sip_alias[t] = cand
                break
        else:
            unmatched.append(t)
    cols = [sym_index.get_loc(sip_alias[t]) for t in matched]
    spy_open = load_spy_open(market.dates)
    open_ = np.hstack([market.open_[:, cols].astype(np.float64), spy_open[:, None]])
    spy_col = len(matched)
    stock_cols = list(range(len(matched)))
    dates = market.dates
    del market

    coverage = {
        "sp500_list_tickers": n_list,
        "tickers_with_views_file": int(len(views.columns) + len(empty)),
        "empty_404_series": empty,
        "duplicate_title_tickers_dropped": dup_titles,
        "drop_rule_dropped": drops,
        "unmatched_to_sip_symbols": unmatched,
        "n_series_used": len(matched),
        "views_first_day": str(views.index.min().date()),
        "views_last_day": str(views.index.max().date()),
        "market_last_trading_day": data_last,
        "partial_fetch": bool(len(views.columns) + len(empty) < n_list),
    }
    if coverage["partial_fetch"] and not args.allow_partial:
        raise SystemExit("fetch incomplete; pass --allow-partial only for debugging")

    used = views[matched]
    results: dict = {"iter_id": ITER, "generated_at": datetime.now(UTC).isoformat()}
    results["coverage"] = coverage
    ic_table: dict = {}
    for name, fn in (("VC7_28", vc7_28), ("VC28_90_control", vc28_90)):
        sig_full = fn(used).reindex(dates)[matched].to_numpy(dtype=float)
        for lag in (0, 1):
            per_offset = ic_for(dates, open_, spy_col, sig_full, stock_cols, lag)
            ic_table[f"{name}_lag{lag}"] = {
                "per_offset": {str(o): v for o, v in per_offset.items()},
                "median_over_offsets": median_over_offsets(per_offset),
            }
        if name == "VC7_28":
            vc_sig = sig_full
    results["ic_table"] = ic_table

    rng = np.random.default_rng(SEED)
    n = len(matched)
    stats1, stats2 = [], []
    for i in range(args.placebos):
        perm = rng.permutation(n)
        med = median_over_offsets(ic_for(dates, open_, spy_col, vc_sig, stock_cols, 0, perm))
        stats1.append(med["seg_2016_07_to_2023_12"]["ic_mean_median_offset"])
        stats2.append(med["seg_2024_01_08_onward"]["ic_mean_median_offset"])
        if (i + 1) % 50 == 0:
            print(f"placebo {i + 1}/{args.placebos}", file=sys.stderr, flush=True)
    real = ic_table["VC7_28_lag0"]["median_over_offsets"]
    p95 = float(np.nanpercentile(stats2, 95))
    real2 = real["seg_2024_01_08_onward"]["ic_mean_median_offset"]
    real1 = real["seg_2016_07_to_2023_12"]["ic_mean_median_offset"]
    results["placebo"] = {
        "n_permutations": args.placebos,
        "seed": SEED,
        "seg_2024_onward": {
            "p05": float(np.nanpercentile(stats2, 5)),
            "p50": float(np.nanpercentile(stats2, 50)),
            "p95": p95,
            "p99": float(np.nanpercentile(stats2, 99)),
            "real": real2,
            "share_of_placebos_at_or_above_real": float(np.mean(np.array(stats2) >= real2)),
        },
        "seg_2016_2023_info": {
            "p95": float(np.nanpercentile(stats1, 95)),
            "real": real1,
            "share_of_placebos_at_or_above_real": float(np.mean(np.array(stats1) >= real1)),
        },
    }
    results["gate_lag0"] = gate(real, p95)
    results["verdict"] = "continue_to_screen" if results["gate_lag0"]["pass"] else "refuted"
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(results, indent=1, default=str))
    print(json.dumps({"verdict": results["verdict"], "gate": results["gate_lag0"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
