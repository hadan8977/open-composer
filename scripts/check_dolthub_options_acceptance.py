"""T-20260929-60: acceptance checks of the cached DoltHub options data.

Reads ``data/dolthub_options/{agg,option_chain,volatility_history}`` (built by
``scripts/fetch_dolthub_options.py``) and the SIP daily archive, evaluates tests (a)-(g) of
queue task T-20260929-60 against the criteria pre-written in
``reports/research/iterations/h20260929_60_dolthub_options_acceptance/results.json`` and writes
the ``tables`` and ``verdict`` fields back (the ``criteria`` field is never modified).

Run under the memory cap::

    scripts/run_capped.sh --mem 1.8G -- uv run python scripts/check_dolthub_options_acceptance.py
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "dolthub_options"
ITER = ROOT / "reports" / "research" / "iterations" / "h20260929_60_dolthub_options_acceptance"
SIP = ROOT / "data" / "sip" / "daily"
ACCEPTANCE = ("SPY", "QQQ", "AAPL", "NVDA", "TSLA")
EXTRA = ("IWM", "SMH", "TQQQ", "MSFT", "AMZN", "GOOGL", "META")
FIRST_DATE = date(2019, 2, 9)
SINCE_2024 = date(2024, 1, 2)
SPREAD_MAX = {"SPY": 0.03, "QQQ": 0.03}
DEFAULT_SPREAD_MAX = 0.10
BAND = (0.10, 0.90)
# SIP daily bars are adjustment="all" (splits AND dividends), so on older dates they sit below the
# raw prices the option chain refers to (SPY ~1.3%/yr). The parity criterion is therefore judged
# on sessions from this fixed date on, after every acceptance symbol's latest ex-dividend date
# (SPY ex-date about 2026-09-18/21; AAPL Aug; NVDA early Sep; TSLA pays none) so the adjustment
# factor is 1. Fixed before looking at the recent-window numbers.
CLEAN_PARITY_START = date(2026, 9, 22)


# --------------------------------------------------------------------------- SIP


def load_sip(symbols: list[str]) -> dict[str, pd.DataFrame]:
    """Daily bars per symbol (date index) from the shard layout; nothing else is read."""
    import pyarrow.parquet as pq

    layout = json.loads((SIP / "_LAYOUT.json").read_text())["shard_symbols"]
    shard_of = {s: sh for sh, syms in layout.items() for s in syms if s in symbols}
    out: dict[str, list[pd.DataFrame]] = {s: [] for s in symbols}
    for year_dir in sorted(p for p in SIP.iterdir() if p.is_dir()):
        for symbol, shard in shard_of.items():
            path = year_dir / f"shard-{shard}.parquet"
            if not path.is_file():
                continue
            table = pq.read_table(
                path,
                columns=["symbol", "timestamp", "open", "close"],
                filters=[("symbol", "=", symbol)],
            ).to_pandas()
            out[symbol].append(table)
    frames = {}
    for symbol, parts in out.items():
        if not parts:
            continue
        df = pd.concat(parts, ignore_index=True)
        df["date"] = pd.to_datetime(df["timestamp"]).dt.tz_convert("UTC").dt.date
        frames[symbol] = df.drop(columns=["timestamp", "symbol"]).set_index("date").sort_index()
    return frames


# --------------------------------------------------------------------------- loaders


def load_agg() -> pd.DataFrame:
    parts = [pd.read_parquet(p) for p in sorted((CACHE / "agg").glob("agg_*.parquet"))]
    parts = [p for p in parts if len(p)]
    if not parts:
        return pd.DataFrame()
    agg = pd.concat(parts, ignore_index=True)
    agg["date"] = pd.to_datetime(agg["date"]).dt.date
    return agg.drop_duplicates(["date", "act_symbol"])


def load_chain() -> pd.DataFrame:
    parts = [pd.read_parquet(p) for p in sorted((CACHE / "option_chain").glob("part_*.parquet"))]
    if not parts:
        return pd.DataFrame()
    chain = pd.concat(parts, ignore_index=True)
    chain["date"] = pd.to_datetime(chain["date"]).dt.date
    chain["expiration"] = pd.to_datetime(chain["expiration"]).dt.date
    return chain.drop_duplicates(["date", "act_symbol", "expiration", "strike", "call_put"])


def load_volhist() -> pd.DataFrame:
    parts = [pd.read_parquet(p) for p in sorted((CACHE / "volatility_history").glob("*.parquet"))]
    parts = [p for p in parts if len(p)]
    if not parts:
        return pd.DataFrame()
    vh = pd.concat(parts, ignore_index=True)
    vh["date"] = pd.to_datetime(vh["date"]).dt.date
    return vh.drop_duplicates(["date", "act_symbol"])


# --------------------------------------------------------------------------- (a)(f)(g)


def _pct(x: float) -> float | None:
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else round(float(x), 6)


def coverage_table(agg: pd.DataFrame, sip: dict[str, pd.DataFrame]) -> dict[str, Any]:
    """(a) coverage = sessions with option rows / SIP sessions, by symbol, window and year."""
    out: dict[str, Any] = {}
    for symbol, bars in sip.items():
        sessions = [d for d in bars.index if d >= FIRST_DATE]
        have = set(agg.loc[agg["act_symbol"] == symbol, "date"]) if len(agg) else set()
        row: dict[str, Any] = {}
        for label, lo in (("since_2019", FIRST_DATE), ("since_2024", SINCE_2024)):
            den = [d for d in sessions if d >= lo]
            row[label] = {
                "sessions": len(den),
                "with_data": sum(d in have for d in den),
                "coverage": _pct(sum(d in have for d in den) / len(den)) if den else None,
            }
        den = [d for d in sessions if d >= date(2024, 9, 4)]
        row["posthoc_since_2024_09_04_NOT_A_CRITERION"] = {
            "sessions": len(den),
            "with_data": sum(d in have for d in den),
            "coverage": _pct(sum(d in have for d in den) / len(den)) if den else None,
        }
        by_year = {}
        for year in sorted({d.year for d in sessions}):
            den = [d for d in sessions if d.year == year]
            by_year[str(year)] = {
                "sessions": len(den),
                "with_data": sum(d in have for d in den),
                "coverage": _pct(sum(d in have for d in den) / len(den)),
            }
        row["by_year"] = by_year
        out[symbol] = row
    return out


def contracts_table(agg: pd.DataFrame) -> dict[str, Any]:
    """(f) contracts and expiries per symbol-day by year."""
    out: dict[str, Any] = {}
    if agg.empty:
        return out
    frame = agg.copy()
    frame["year"] = [d.year for d in frame["date"]]
    for (symbol, year), grp in frame.groupby(["act_symbol", "year"]):
        out.setdefault(symbol, {})[str(year)] = {
            "days": int(len(grp)),
            "median_contracts": float(grp["n_rows"].median()),
            "median_expiries": float(grp["n_exp"].median()),
            "median_strikes": float(grp["n_strikes"].median()),
            "median_max_dte": float(
                np.median(
                    [
                        (pd.Timestamp(e).date() - d).days
                        for e, d in zip(grp["max_exp"], grp["date"], strict=True)
                    ]
                )
            ),
        }
    return out


def bad_quote_table(agg: pd.DataFrame) -> dict[str, Any]:
    """(g) exact server-side quote-hygiene shares (before the sampled stale test)."""
    out: dict[str, Any] = {}
    if agg.empty:
        return out
    for symbol, grp in agg.groupby("act_symbol"):
        rows = float(grp["n_rows"].sum())
        band = float(grp["n_band"].sum())
        bad_band = float(
            grp[
                [
                    "n_band_null",
                    "n_band_neg_bid",
                    "n_band_nonpos_ask",
                    "n_band_crossed",
                    "n_band_zero_bid",
                ]
            ]
            .sum()
            .sum()
        )
        out[symbol] = {
            "rows": int(rows),
            "band_rows": int(band),
            "band_bad_share_excluding_stale": _pct(bad_band / band) if band else None,
            "band_components": {
                c: int(grp[c].sum())
                for c in (
                    "n_band_null",
                    "n_band_neg_bid",
                    "n_band_nonpos_ask",
                    "n_band_crossed",
                    "n_band_zero_bid",
                )
            },
            "all_rows_crossed_share": _pct(float(grp["n_crossed"].sum()) / rows),
            "all_rows_zero_bid_share": _pct(float(grp["n_zero_bid"].sum()) / rows),
            "all_rows_null_share": _pct(float(grp["n_null"].sum()) / rows),
            "all_rows_vol_missing_share": _pct(float(grp["n_vol_missing"].sum()) / rows),
        }
    return out


# --------------------------------------------------------------------------- (b)(c)(g)-stale


def _valid(df: pd.DataFrame) -> pd.DataFrame:
    return df[(df["bid"] > 0) & (df["ask"] > 0) & (df["ask"] >= df["bid"])]


def _rel_spread(df: pd.DataFrame) -> pd.Series:
    mid = (df["ask"] + df["bid"]) / 2
    return (df["ask"] - df["bid"]) / mid


def chain_day_metrics(day_df: pd.DataFrame, d: date, ref_close: float | None) -> dict[str, Any]:
    """Parity S_hat, ATM/25-delta relative spreads, stale counts for one symbol-day."""
    out: dict[str, Any] = {"n_rows": len(day_df), "n_exp": int(day_df["expiration"].nunique())}
    dte = np.array([(e - d).days for e in day_df["expiration"]])
    day_df = day_df.assign(dte=dte)
    # stale legs inside the delta band vs intrinsic value at the reference close
    if ref_close:
        band = day_df[day_df["delta"].abs().between(*BAND)]
        valid_q = band[band["bid"].notna() & band["ask"].notna()]
        mid = (valid_q["bid"] + valid_q["ask"]) / 2
        intrinsic = np.where(
            valid_q["call_put"] == "Call",
            np.maximum(ref_close - valid_q["strike"], 0),
            np.maximum(valid_q["strike"] - ref_close, 0),
        )
        out["stale_n"] = int((mid < intrinsic - 0.01 * ref_close).sum())
        out["band_n"] = int(len(band))
    # parity: shortest expiry with DTE >= 3
    for key, min_dte in (("parity", 3), ("parity_m", 25)):
        ok = sorted(e for e, x in zip(day_df["expiration"], dte, strict=True) if x >= min_dte)
        if not ok:
            continue
        exp = ok[0]
        legs = _valid(day_df[day_df["expiration"] == exp])
        calls = legs[legs["call_put"] == "Call"].set_index("strike")
        puts = legs[legs["call_put"] == "Put"].set_index("strike")
        common = calls.index.intersection(puts.index)
        if len(common) == 0:
            continue
        c_mid = (calls.loc[common, "bid"] + calls.loc[common, "ask"]) / 2
        p_mid = (puts.loc[common, "bid"] + puts.loc[common, "ask"]) / 2
        k = (c_mid - p_mid).abs().idxmin()
        out[key] = float(c_mid.loc[k] - p_mid.loc[k] + k)
        out[key + "_dte"] = int((exp - d).days)
    # spread: shortest expiry with DTE >= 7
    ok = sorted(e for e, x in zip(day_df["expiration"], dte, strict=True) if x >= 7)
    if ok:
        exp = ok[0]
        legs = _valid(day_df[day_df["expiration"] == exp])
        calls = legs[legs["call_put"] == "Call"].set_index("strike")
        puts = legs[legs["call_put"] == "Put"].set_index("strike")
        common = calls.index.intersection(puts.index)
        if len(common):
            k = (calls.loc[common, "delta"] - 0.5).abs().idxmin()
            out["atm_spread"] = float(
                (_rel_spread(calls.loc[[k]]).iloc[0] + _rel_spread(puts.loc[[k]]).iloc[0]) / 2
            )
            out["atm_delta"] = float(calls.loc[k, "delta"])
            out["atm_vol"] = float(calls.loc[k, "vol"])
        if len(puts) and len(calls):
            kp = (puts["delta"] + 0.25).abs().idxmin()
            kc = (calls["delta"] - 0.25).abs().idxmin()
            out["d25_put_spread"] = float(_rel_spread(puts.loc[[kp]]).iloc[0])
            out["d25_call_spread"] = float(_rel_spread(calls.loc[[kc]]).iloc[0])
            out["d25_put_delta"] = float(puts.loc[kp, "delta"])
    return out


def chain_sample_metrics(chain: pd.DataFrame, sip: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for (symbol, d), grp in chain.groupby(["act_symbol", "date"]):
        bars = sip.get(symbol)
        ref = None
        rec: dict[str, Any] = {"act_symbol": symbol, "date": d}
        if bars is not None and d in bars.index:
            idx = list(bars.index)
            i = idx.index(d)
            ref = float(bars.loc[d, "close"])
            rec["close_d"] = ref
            rec["open_d1"] = float(bars.iloc[i + 1]["open"]) if i + 1 < len(idx) else np.nan
            rec["close_d1"] = float(bars.iloc[i + 1]["close"]) if i + 1 < len(idx) else np.nan
            rec["close_dm1"] = float(bars.iloc[i - 1]["close"]) if i > 0 else np.nan
            rec["open_d"] = float(bars.loc[d, "open"])
        # stale test needs a raw (unadjusted) reference: clean window only
        rec.update(chain_day_metrics(grp, d, ref if d >= CLEAN_PARITY_START else None))
        rows.append(rec)
    return pd.DataFrame(rows)


def _med(series: pd.Series) -> float | None:
    s = series.dropna()
    return _pct(float(s.median())) if len(s) else None


def parity_table(m: pd.DataFrame) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for symbol, grp in m.groupby("act_symbol"):
        row: dict[str, Any] = {"n_days": int(len(grp))}
        refs = {
            "close_d": "close_d",
            "open_d1": "open_d1",
            "close_d1": "close_d1",
            "close_dm1": "close_dm1",
        }
        devs = {}
        for name, col in refs.items():
            if col in grp and "parity" in grp:
                dev = (grp["parity"] / grp[col] - 1).abs()
                signed = grp["parity"] / grp[col] - 1
                devs[name] = _med(dev)
                row[f"median_abs_dev_vs_{name}"] = devs[name]
                row[f"median_signed_dev_vs_{name}"] = _med(signed)
        # the closer of close_d and open_d1 (criterion reference)
        pair = {k: v for k, v in devs.items() if k in ("close_d", "open_d1") and v is not None}
        if pair:
            best = min(pair, key=lambda k: pair[k])
            row["closer_reference"] = best
            row["criterion_median_abs_dev"] = pair[best]
        if "parity" in grp and "close_d" in grp:
            by_dte = {}
            for label, lo, hi in (("dte3_7", 3, 7), ("dte8_14", 8, 14), ("dte15plus", 15, 999)):
                sub = grp[grp["parity_dte"].between(lo, hi)]
                if len(sub):
                    by_dte[label] = {
                        "n": int(len(sub)),
                        "median_abs_dev_vs_close_d": _med(
                            (sub["parity"] / sub["close_d"] - 1).abs()
                        ),
                        "median_signed_dev_vs_close_d": _med(sub["parity"] / sub["close_d"] - 1),
                    }
            row["by_dte_bucket"] = by_dte
        if "parity_m" in grp and "close_d" in grp:
            row["monthly_expiry_median_abs_dev_vs_close_d"] = _med(
                (grp["parity_m"] / grp["close_d"] - 1).abs()
            )
        clean = grp[grp["date"] >= CLEAN_PARITY_START]
        if len(clean) and "parity" in clean:
            cdev = {}
            for name in ("close_d", "open_d1"):
                dev = (clean["parity"] / clean[name] - 1).abs().dropna()
                cdev[name] = _pct(float(dev.median())) if len(dev) else None
            cvalid = {k: v for k, v in cdev.items() if v is not None}
            row["clean_window"] = {
                "start": CLEAN_PARITY_START.isoformat(),
                "n_days": int(len(clean)),
                "median_abs_dev_vs_close_d": cdev["close_d"],
                "median_abs_dev_vs_open_d1": cdev["open_d1"],
                "closer_reference": min(cvalid, key=lambda k: cvalid[k]) if cvalid else None,
                "criterion_median_abs_dev": min(cvalid.values()) if cvalid else None,
            }
        recent = grp[grp["date"] >= date(2026, 9, 10)].sort_values("date")
        if len(recent) and "parity" in recent:
            row["recent_series"] = [
                {
                    "date": r["date"].isoformat(),
                    "dte": int(r["parity_dte"]),
                    "S_hat": round(float(r["parity"]), 3),
                    "vs_close_d_pct": round(100 * (r["parity"] / r["close_d"] - 1), 3),
                    "vs_open_d1_pct": None
                    if pd.isna(r.get("open_d1"))
                    else round(100 * (r["parity"] / r["open_d1"] - 1), 3),
                    "vs_close_d1_pct": None
                    if pd.isna(r.get("close_d1"))
                    else round(100 * (r["parity"] / r["close_d1"] - 1), 3),
                }
                for _, r in recent.iterrows()
                if not pd.isna(r.get("parity"))
            ]
        out[symbol] = row
    return out


def spread_table(m: pd.DataFrame) -> dict[str, Any]:
    out: dict[str, Any] = {}
    m = m.copy()
    m["year"] = [d.year for d in m["date"]]
    for symbol, grp in m.groupby("act_symbol"):
        row: dict[str, Any] = {"n_days": int(len(grp))}
        for label, sub in (
            ("full", grp),
            ("since_2024", grp[grp["date"] >= SINCE_2024]),
        ):
            row[label] = {
                "atm_n": int(sub["atm_spread"].notna().sum()) if "atm_spread" in sub else 0,
                "atm_median": _med(sub["atm_spread"]) if "atm_spread" in sub else None,
                "atm_p25": _pct(float(sub["atm_spread"].quantile(0.25)))
                if "atm_spread" in sub and sub["atm_spread"].notna().any()
                else None,
                "atm_p75": _pct(float(sub["atm_spread"].quantile(0.75)))
                if "atm_spread" in sub and sub["atm_spread"].notna().any()
                else None,
                "d25_put_median": _med(sub["d25_put_spread"]) if "d25_put_spread" in sub else None,
                "d25_call_median": _med(sub["d25_call_spread"])
                if "d25_call_spread" in sub
                else None,
            }
        row["by_year_atm_median"] = {
            str(y): {"n": int(g["atm_spread"].notna().sum()), "median": _med(g["atm_spread"])}
            for y, g in grp.assign(year=grp["year"]).groupby("year")
            if "atm_spread" in g
        }
        out[symbol] = row
    return out


def stale_table(m: pd.DataFrame) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if "stale_n" not in m:
        return out
    for symbol, grp in m.groupby("act_symbol"):
        band_n = float(grp["band_n"].sum())
        out[symbol] = {
            "sample_days": int(len(grp)),
            "band_rows": int(band_n),
            "stale_rows": int(grp["stale_n"].sum()),
            "stale_share": _pct(float(grp["stale_n"].sum()) / band_n) if band_n else None,
        }
    return out


# --------------------------------------------------------------------------- (d)(e)


def iv_table(vh: pd.DataFrame, m: pd.DataFrame) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if vh.empty:
        return out
    for symbol, grp in vh.groupby("act_symbol"):
        s = grp.sort_values("date").set_index("date")["iv_current"].dropna()
        row: dict[str, Any] = {"n_days": int(len(s))}
        if len(s) > 30:
            row["iv_current_lag1_autocorr"] = _pct(float(s.autocorr(1)))
        mm = m[m["act_symbol"] == symbol]
        if len(mm) and "atm_vol" in mm:
            joined = mm.set_index("date")["atm_vol"].to_frame().join(s.rename("iv_current"))
            joined = joined.dropna()
            if len(joined):
                row["n_days_with_atm_vol"] = int(len(joined))
                row["median_abs_rel_diff_iv_current_vs_atm_vol"] = _pct(
                    float(
                        (
                            (joined["iv_current"] - joined["atm_vol"]).abs() / joined["iv_current"]
                        ).median()
                    )
                )
                row["median_iv_current_minus_atm_vol"] = _pct(
                    float((joined["iv_current"] - joined["atm_vol"]).median())
                )
        out[symbol] = row
    return out


def gap_table(agg: pd.DataFrame, sip: dict[str, pd.DataFrame]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for symbol, bars in sip.items():
        have = set(agg.loc[agg["act_symbol"] == symbol, "date"]) if len(agg) else set()
        ret = bars["close"].pct_change().abs()
        sessions = [d for d in ret.index if d >= SINCE_2024]
        miss = [ret[d] for d in sessions if d not in have and not math.isnan(ret[d])]
        pres = [ret[d] for d in sessions if d in have and not math.isnan(ret[d])]
        row = {
            "since_2024_missing_days": len(miss),
            "since_2024_present_days": len(pres),
            "mean_abs_ret_missing": _pct(float(np.mean(miss))) if miss else None,
            "mean_abs_ret_present": _pct(float(np.mean(pres))) if pres else None,
        }
        # post-hoc diagnostics (NOT criteria): weekday pattern and the later dense regime
        weekday: dict[str, Any] = {}
        for label, lo, hi in (
            ("2020-01..2024-08", date(2020, 1, 1), date(2024, 8, 31)),
            ("2024-09-04..end", date(2024, 9, 4), date(2099, 1, 1)),
        ):
            days = [d for d in bars.index if lo <= d <= hi]
            weekday[label] = {
                name: _pct(sum(d in have for d in days if d.weekday() == wd) / n)
                for wd, name in enumerate(("Mon", "Tue", "Wed", "Thu", "Fri"))
                if (n := sum(d.weekday() == wd for d in days))
            }
            weekday[label]["overall"] = (
                _pct(sum(d in have for d in days) / len(days)) if days else None
            )
        row["posthoc_coverage_by_weekday"] = weekday
        if miss and pres:
            row["ratio_missing_to_present"] = _pct(float(np.mean(miss) / np.mean(pres)))
            row["flag_non_random_ratio_gt_1_25"] = bool(np.mean(miss) / np.mean(pres) > 1.25)
        out[symbol] = row
    return out


# --------------------------------------------------------------------------- verdict


def symbol_judgement(
    symbol: str,
    cov: dict[str, Any],
    par: dict[str, Any],
    spr: dict[str, Any],
    bad: dict[str, Any],
    stale: dict[str, Any],
    criteria: dict[str, Any],
) -> dict[str, Any]:
    th = criteria["thresholds"]
    spread_limit = th["atm_rel_spread_median_max"].get(symbol, DEFAULT_SPREAD_MAX)
    c = cov.get(symbol, {})
    cov19 = c.get("since_2019", {}).get("coverage")
    cov24 = c.get("since_2024", {}).get("coverage")
    p = par.get(symbol, {}).get("clean_window", {}).get("criterion_median_abs_dev")
    s_full = spr.get(symbol, {}).get("full", {}).get("atm_median")
    s_24 = spr.get(symbol, {}).get("since_2024", {}).get("atm_median")
    b_exact = bad.get(symbol, {}).get("band_bad_share_excluding_stale")
    b_stale = stale.get(symbol, {}).get("stale_share")
    b_total = None if b_exact is None else b_exact + (b_stale or 0.0)
    checks = {
        "coverage_since_2019": cov19 is not None and cov19 >= th["coverage_since_2019_min"],
        "coverage_since_2024": cov24 is not None and cov24 >= th["coverage_since_2024_min"],
        "parity": p is not None and p <= th["parity_median_abs_rel_dev_max"],
        "spread_full": s_full is not None and s_full <= spread_limit,
        "spread_since_2024": s_24 is not None and s_24 <= spread_limit,
        "bad_quotes": b_total is not None and b_total <= th["bad_quote_share_max"],
    }
    return {
        "values": {
            "coverage_since_2019": cov19,
            "coverage_since_2024": cov24,
            "parity_median_abs_dev_closer_reference_clean_window": p,
            "parity_reference": par.get(symbol, {}).get("clean_window", {}).get("closer_reference"),
            "parity_clean_window_days": par.get(symbol, {}).get("clean_window", {}).get("n_days"),
            "atm_spread_median_full": s_full,
            "atm_spread_median_since_2024": s_24,
            "spread_limit": spread_limit,
            "bad_share_exact_excluding_stale": b_exact,
            "stale_share_sample": b_stale,
            "bad_share_total": _pct(b_total) if b_total is not None else None,
        },
        "checks": checks,
        "meets_every_criterion": all(checks.values()),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--fetch-complete", action="store_true", help="all acceptance chains fully pulled"
    )
    ap.add_argument("--no-write", action="store_true")
    args = ap.parse_args()

    results_path = ITER / "results.json"
    results = json.loads(results_path.read_text())
    criteria = results["criteria"]

    agg = load_agg()
    chain = load_chain()
    vh = load_volhist()
    symbols = sorted(set(ACCEPTANCE) | (set(agg["act_symbol"]) if len(agg) else set()))
    sip = load_sip(symbols)
    metrics = chain_sample_metrics(chain, sip) if len(chain) else pd.DataFrame()

    cov = coverage_table(agg, sip)
    tables = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "coverage_a": cov,
        "parity_b": parity_table(metrics) if len(metrics) else {},
        "spread_c": spread_table(metrics) if len(metrics) else {},
        "iv_d": iv_table(vh, metrics if len(metrics) else pd.DataFrame(columns=["act_symbol"])),
        "gap_randomness_e": gap_table(agg, sip),
        "contracts_f": contracts_table(agg),
        "bad_quotes_g": bad_quote_table(agg),
        "stale_g_sample": stale_table(metrics) if len(metrics) else {},
        "cache": {
            "agg_symbol_days": int(len(agg)),
            "chain_rows": int(len(chain)),
            "chain_symbol_days_sampled": int(len(metrics)),
            "chain_sample_days_by_symbol": (
                metrics.groupby("act_symbol").size().to_dict() if len(metrics) else {}
            ),
            "volatility_history_rows": int(len(vh)),
        },
    }
    judgement = {
        s: symbol_judgement(
            s,
            cov,
            tables["parity_b"],
            tables["spread_c"],
            tables["bad_quotes_g"],
            tables["stale_g_sample"],
            criteria,
        )
        for s in symbols
        if s in cov
    }
    tables["judgement"] = judgement
    passing = [s for s, j in judgement.items() if j["meets_every_criterion"]]
    all_five = all(judgement.get(s, {}).get("meets_every_criterion") for s in ACCEPTANCE)
    if not args.fetch_complete:
        tier = "incomplete"
    elif all_five:
        tier = "pass"
    elif passing:
        tier = "partial"
    else:
        tier = "fail"
    tables["verdict_computation"] = {
        "tier_by_preregistered_rule": tier,
        "symbols_meeting_every_criterion": passing,
        "fetch_complete_flag": args.fetch_complete,
    }
    if args.no_write:
        print(json.dumps(tables, indent=1, default=str))
    else:
        print(json.dumps(tables["verdict_computation"] | {"judgement": judgement}, indent=1))
    if not args.no_write:
        results["tables"] = tables
        results_path.write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
