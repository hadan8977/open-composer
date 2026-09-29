"""h20260929_50: does weekend crypto return W predict Monday US equity returns
only in the Friday-close -> Monday-open gap, or also after the open?

Step 1 (cheapest negative test) of T-20260929-50. Statistics only, no trading
rule and no costs. Preregistered in
reports/research/iterations/h20260929_50_crypto_weekend_monday/
candidate-manifest.json before this script was run.

Signal W: crypto return from Friday 16:00 America/New_York (open of the 15m
bar opening at 16:00 ET) to Sunday 24:00 UTC = Monday 00:00 UTC (close of the
15m bar opening 23:45 UTC). No crypto bar with open time at or after Monday
00:00 UTC is used.

Monday sample: first ETF trading date on or after the calendar Monday of the
week (flagged holiday_monday when it is not the calendar Monday).
Segments (bp): gap = open[M]/close[prev]-1, oc = close[M]/open[M]-1,
o2o = open[next]/open[M]-1.

Usage: uv run python scripts/run_h20260929_50_weekend_split.py
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, date, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

ET = ZoneInfo("America/New_York")
ITER_ID = "h20260929_50_crypto_weekend_monday"
OUT_DIR = ROOT / "reports" / "research" / "iterations" / ITER_ID
BAR = timedelta(minutes=15)
PLACEBO_SEED = 20260929
N_SHUFFLES = 500
ETFS = ["SPY", "QQQ", "IWM"]
SEGMENTS = ["gap", "oc", "o2o"]
SIGNALS = ["BTC", "ETH", "EW10"]
COINS = ["BTC", "ETH", "LTC", "BCH", "LINK", "DOGE", "AVAX", "UNI", "AAVE", "DOT"]
MIN_COINS_EW = 2
SAMPLES = {
    "full": "2016-05-01",
    "post_luna": "2022-06-01",
    "anchor": "2024-01-08",
}
GROUPINGS = {"neg": 0.0, "big": -0.03}  # group A = W < threshold
GATING_SAMPLES = ["post_luna", "anchor"]
GATING_ETFS = ["QQQ", "SPY"]
GATING_SEGMENTS = ["oc", "o2o"]
T_MIN = 2.0
PLACEBO_PCT = 90.0


# ---------------------------------------------------------------- windows


def weekend_window(monday: date) -> tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp]:
    """(start_bar_open_utc, last_bar_open_utc, end_utc) for the weekend before
    the calendar Monday `monday`. start = Friday 16:00 ET, end = Monday 00:00 UTC."""
    friday = monday - timedelta(days=3)
    start_et = datetime(friday.year, friday.month, friday.day, 16, 0, tzinfo=ET)
    start = pd.Timestamp(start_et.astimezone(UTC))
    end = pd.Timestamp(datetime(monday.year, monday.month, monday.day, tzinfo=UTC))
    return start, end - BAR, end


def weekend_return(bars: pd.DataFrame, monday: date) -> float:
    """W from a 15m frame with open_time_utc/open/close; NaN if an endpoint bar
    is missing. Only the bar opening at 16:00 ET Friday (its open) and the bar
    opening 23:45 UTC Sunday (its close) are read."""
    start, last_open, end = weekend_window(monday)
    indexed = bars.set_index("open_time_utc")
    p0 = indexed["open"].get(start, np.nan)
    p1 = indexed["close"].get(last_open, np.nan)
    if not np.isfinite(p0) or not np.isfinite(p1) or p0 <= 0:
        return float("nan")
    assert last_open + BAR == end
    return float(p1 / p0 - 1.0)


def weekend_returns_series(bars: pd.DataFrame, mondays: list[date]) -> pd.Series:
    indexed = bars.set_index("open_time_utc")
    opens = indexed["open"]
    closes = indexed["close"]
    starts = [weekend_window(m)[0] for m in mondays]
    lasts = [weekend_window(m)[1] for m in mondays]
    p0 = opens.reindex(starts).to_numpy(dtype=float)
    p1 = closes.reindex(lasts).to_numpy(dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        w = np.where((p0 > 0) & np.isfinite(p0) & np.isfinite(p1), p1 / p0 - 1.0, np.nan)
    return pd.Series(w, index=pd.Index(mondays, name="monday"))


def monday_samples(trading_dates: list[date]) -> pd.DataFrame:
    """One row per calendar week that has a trading date on or before Friday:
    calendar_monday, target date M, prev trading date, next trading date, flags."""
    tds = sorted(trading_dates)
    td_set = set(tds)
    idx = {d: i for i, d in enumerate(tds)}
    first = tds[0]
    monday = first - timedelta(days=first.weekday())
    if monday < first:
        monday += timedelta(days=7)
    rows = []
    last = tds[-1]
    while monday <= last:
        target = None
        for k in range(5):
            cand = monday + timedelta(days=k)
            if cand in td_set:
                target = cand
                break
        if target is not None and 0 < idx[target] < len(tds) - 1:
            friday = monday - timedelta(days=3)
            rows.append(
                {
                    "calendar_monday": monday,
                    "target": target,
                    "prev": tds[idx[target] - 1],
                    "next": tds[idx[target] + 1],
                    "holiday_monday": target != monday,
                    "friday_holiday": friday not in td_set,
                }
            )
        monday += timedelta(days=7)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- statistics


def welch(a: np.ndarray, b: np.ndarray) -> tuple[float, float, int, int]:
    """(mean(a)-mean(b), Welch t, n_a, n_b)."""
    na, nb = len(a), len(b)
    if na < 2 or nb < 2:
        return float("nan"), float("nan"), na, nb
    va, vb = a.var(ddof=1), b.var(ddof=1)
    se = np.sqrt(va / na + vb / nb)
    diff = float(a.mean() - b.mean())
    t = diff / se if se > 0 else float("nan")
    return diff, float(t), na, nb


def welch_perms(ret: np.ndarray, groupA: np.ndarray) -> np.ndarray:
    """Welch t for many boolean group-A masks at once. groupA: (P, n)."""
    n = ret.shape[0]
    mask = groupA.astype(float)
    na = mask.sum(axis=1)
    nb = n - na
    sa = mask @ ret
    sb = ret.sum() - sa
    ssa = mask @ (ret**2)
    ssb = (ret**2).sum() - ssa
    with np.errstate(divide="ignore", invalid="ignore"):
        ma, mb = sa / na, sb / nb
        va = (ssa - na * ma**2) / (na - 1)
        vb = (ssb - nb * mb**2) / (nb - 1)
        t = (ma - mb) / np.sqrt(va / na + vb / nb)
    t[(na < 2) | (nb < 2)] = np.nan
    return t


@lru_cache(maxsize=8)
def _shuffle_cached(n: int, n_shuffles: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    out = np.stack([rng.permutation(n) for _ in range(n_shuffles)])
    out.setflags(write=False)
    return out


def shuffle_indices(n: int, n_shuffles: int = N_SHUFFLES, seed: int = PLACEBO_SEED) -> np.ndarray:
    """(n_shuffles, n) permutation index matrix; same seed -> identical output."""
    return _shuffle_cached(n, n_shuffles, seed)


def placebo_stats(w: np.ndarray, ret: np.ndarray, thr: float, real_abs_t: float) -> dict:
    perms = shuffle_indices(len(w))
    wp = w[perms]
    t = welch_perms(ret, wp < thr)
    absr = np.abs(t[np.isfinite(t)])
    if len(absr) == 0 or not np.isfinite(real_abs_t):
        return {"placebo_share_below": None, "placebo_p90_abs_t": None, "n_valid_shuffles": 0}
    return {
        "placebo_share_below": float((absr < real_abs_t).mean()),
        "placebo_p90_abs_t": float(np.percentile(absr, PLACEBO_PCT)),
        "n_valid_shuffles": int(len(absr)),
    }


# ---------------------------------------------------------------- data loading


def load_etf_daily() -> pd.DataFrame:
    con = duckdb.connect()
    try:
        con.execute("SET memory_limit='400MB'")
        df = con.execute(
            "SELECT symbol, timestamp, open, close FROM "
            "read_parquet('data/sip/daily/**/*.parquet') "
            "WHERE symbol IN ('SPY','QQQ','IWM') ORDER BY symbol, timestamp"
        ).fetchdf()
    finally:
        con.close()
    df["date"] = pd.to_datetime(df["timestamp"], utc=True).dt.tz_convert(ET).dt.date
    return df[["symbol", "date", "open", "close"]]


def load_crypto_bars() -> dict[str, pd.DataFrame]:
    import fetch_crypto_session_prices as fc

    now = pd.Timestamp.now(tz="UTC")
    out: dict[str, pd.DataFrame] = {}
    for sym in COINS:
        bars = fc.load_binance_15m(sym, through=now)
        if sym in fc.COINBASE_SYMBOLS:
            start = bars["open_time_utc"].min() if not bars.empty else now
            cb = fc.load_coinbase_15m_backfill(sym, end_utc=start)
            bars = pd.concat([cb, bars], ignore_index=True)
            bars = bars.drop_duplicates(subset="open_time_utc").sort_values("open_time_utc")
        out[sym] = bars.reset_index(drop=True)
    return out


def build_panel(etf: pd.DataFrame, crypto: dict[str, pd.DataFrame]) -> pd.DataFrame:
    spy_dates = sorted(etf[etf.symbol == "SPY"]["date"].unique())
    weeks = monday_samples(list(spy_dates))
    mondays = list(weeks["calendar_monday"])
    w = {c: weekend_returns_series(b, mondays) for c, b in crypto.items()}
    wdf = pd.DataFrame(w)
    weeks = weeks.copy()
    weeks["W_BTC"] = wdf["BTC"].to_numpy()
    weeks["W_ETH"] = wdf["ETH"].to_numpy()
    n_coins = wdf.notna().sum(axis=1).to_numpy()
    ew = wdf.mean(axis=1, skipna=True).to_numpy()
    ew = np.where(n_coins >= MIN_COINS_EW, ew, np.nan)
    weeks["W_EW10"] = ew
    weeks["n_coins"] = n_coins
    for sym in ETFS:
        e = etf[etf.symbol == sym].set_index("date")
        o, c = e["open"], e["close"]
        weeks[f"{sym}_gap"] = (
            o.reindex(weeks["target"]).to_numpy() / c.reindex(weeks["prev"]).to_numpy() - 1
        ) * 1e4
        weeks[f"{sym}_oc"] = (
            c.reindex(weeks["target"]).to_numpy() / o.reindex(weeks["target"]).to_numpy() - 1
        ) * 1e4
        weeks[f"{sym}_o2o"] = (
            o.reindex(weeks["next"]).to_numpy() / o.reindex(weeks["target"]).to_numpy() - 1
        ) * 1e4
    return weeks


# ---------------------------------------------------------------- analysis


def sample_rows(panel: pd.DataFrame, sample: str) -> pd.DataFrame:
    return panel[pd.to_datetime(panel["target"]) >= pd.Timestamp(SAMPLES[sample])]


def analyse(panel: pd.DataFrame) -> dict:
    cells: list[dict] = []
    for sig in SIGNALS:
        for sample in SAMPLES:
            sub = sample_rows(panel, sample)
            sub = sub[np.isfinite(sub[f"W_{sig}"])]
            for etf in ETFS:
                for seg in SEGMENTS:
                    col = f"{etf}_{seg}"
                    ok = sub[np.isfinite(sub[col])]
                    w = ok[f"W_{sig}"].to_numpy(dtype=float)
                    r = ok[col].to_numpy(dtype=float)
                    hol = ok["holiday_monday"].to_numpy(dtype=bool)
                    for gname, thr in GROUPINGS.items():
                        a = w < thr
                        diff, t, na, nb = welch(r[a], r[~a])
                        row = {
                            "signal": sig,
                            "sample": sample,
                            "etf": etf,
                            "segment": seg,
                            "grouping": gname,
                            "mean_diff_bp": diff,
                            "welch_t": t,
                            "n_A": na,
                            "n_B": nb,
                            "mean_A_bp": float(r[a].mean()) if na else None,
                            "mean_B_bp": float(r[~a].mean()) if nb else None,
                        }
                        row.update(placebo_stats(w, r, thr, abs(t)))
                        nh = ~hol
                        d2, t2, na2, nb2 = welch(r[nh & a], r[nh & ~a])
                        row["ex_holiday"] = {
                            "mean_diff_bp": d2,
                            "welch_t": t2,
                            "n_A": na2,
                            "n_B": nb2,
                        }
                        cells.append(row)
    return {"cells": cells}


def _cell(cells: list[dict], **kw) -> dict:
    for c in cells:
        if all(c[k] == v for k, v in kw.items()):
            return c
    raise KeyError(kw)


def _passes(c: dict) -> dict:
    p90 = c["placebo_p90_abs_t"]
    t = c["welch_t"]
    finite = np.isfinite(c["mean_diff_bp"]) and np.isfinite(t) and p90 is not None
    return {
        "diff_negative": bool(finite and c["mean_diff_bp"] < 0),
        "abs_t_ge_2": bool(finite and abs(t) >= T_MIN),
        "abs_t_above_placebo_p90": bool(finite and abs(t) > p90),
        "mean_diff_bp": c["mean_diff_bp"],
        "welch_t": t,
        "placebo_p90_abs_t": p90,
        "placebo_share_below": c["placebo_share_below"],
        "n_A": c["n_A"],
        "n_B": c["n_B"],
    }


def continue_rule(cells: list[dict]) -> dict:
    per_cell = []
    any_pass = False
    for sig in SIGNALS:
        for etf in GATING_ETFS:
            for seg in GATING_SEGMENTS:
                by_sample = {}
                ok_all = True
                for sample in GATING_SAMPLES:
                    c = _cell(
                        cells,
                        signal=sig,
                        sample=sample,
                        etf=etf,
                        segment=seg,
                        grouping="neg",
                    )
                    pr = _passes(c)
                    by_sample[sample] = pr
                    ok_all &= (
                        pr["diff_negative"] and pr["abs_t_ge_2"] and pr["abs_t_above_placebo_p90"]
                    )
                any_pass |= ok_all
                per_cell.append(
                    {"signal": sig, "etf": etf, "segment": seg, "passes_both": ok_all, **by_sample}
                )
    gap_rep = []
    gap_any = False
    for sig in SIGNALS:
        for etf in GATING_ETFS:
            flags = []
            for sample in GATING_SAMPLES:
                c = _cell(cells, signal=sig, sample=sample, etf=etf, segment="gap", grouping="neg")
                flags.append(
                    bool(
                        np.isfinite(c["welch_t"])
                        and c["mean_diff_bp"] < 0
                        and abs(c["welch_t"]) >= T_MIN
                    )
                )
            gap_rep.append(
                {"signal": sig, "etf": etf, "gap_effect_in_both_recent_samples": all(flags)}
            )
            gap_any |= all(flags)
    if any_pass:
        verdict = "continue_to_batch"
        label = "post-open predictive power survives the frozen gate in both recent samples"
    elif gap_any:
        verdict = "refuted"
        label = "predictive power in the gap, priced before the fill"
    else:
        verdict = "refuted"
        label = "no predictive power (not even in the gap)"
    return {
        "rule": (
            "exists (signal, ETF in QQQ/SPY, segment in oc/o2o), grouping neg (W<0 vs W>=0): in "
            "BOTH post_luna and anchor samples mean(W<0) < mean(W>=0), |Welch t| >= 2.0 and "
            f"|t| > placebo p{int(PLACEBO_PCT)} of |t| ({N_SHUFFLES} shuffles, seed {PLACEBO_SEED})"
        ),
        "continue_to_batch": bool(any_pass),
        "gap_effect_replicates_in_our_data": bool(gap_any),
        "verdict": verdict,
        "refutation_label": None if any_pass else label,
        "label_if_any": label,
        "gating_cells": per_cell,
        "gap_replication": gap_rep,
    }


def render_markdown(results: dict) -> str:
    cells = results["cells"]
    lines = [
        f"# {ITER_ID}: weekend crypto W vs Monday ETF segments",
        "",
        "Cell = mean(W<0) - mean(W>=0) in bp (Welch t) [placebo percentile of |t|], n_A/n_B. "
        "gap = Fri close to Mon open; oc = Mon open to close; o2o = Mon open to Tue open.",
        "",
    ]
    for gname in GROUPINGS:
        lines.append(f"## Grouping {gname} (A: W < {GROUPINGS[gname]:+.2f})")
        lines.append("")
        lines.append("| signal | sample | ETF | gap | oc | o2o |")
        lines.append("|---|---|---|---|---|---|")
        for sig in SIGNALS:
            for sample in SAMPLES:
                for etf in ETFS:
                    parts = []
                    for seg in SEGMENTS:
                        c = _cell(
                            cells,
                            signal=sig,
                            sample=sample,
                            etf=etf,
                            segment=seg,
                            grouping=gname,
                        )
                        pct = c["placebo_share_below"]
                        pct_s = "n/a" if pct is None else f"{pct * 100:.0f}"
                        parts.append(
                            f"{c['mean_diff_bp']:+.1f} ({c['welch_t']:+.2f}) [{pct_s}] "
                            f"{c['n_A']}/{c['n_B']}"
                        )
                    lines.append(f"| {sig} | {sample} | {etf} | " + " | ".join(parts) + " |")
        lines.append("")
    cr = results["continue_rule"]
    lines += [
        "## Continue rule",
        "",
        f"continue_to_batch = {cr['continue_to_batch']}; gap effect replicates = "
        f"{cr['gap_effect_replicates_in_our_data']}; verdict = {cr['verdict']} "
        f"({cr['refutation_label'] or cr['label_if_any']})",
        "",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    etf = load_etf_daily()
    crypto = load_crypto_bars()
    panel = build_panel(etf, crypto)
    coverage = {
        c: {
            "first_bar": str(b["open_time_utc"].min()),
            "last_bar": str(b["open_time_utc"].max()),
            "rows": int(len(b)),
        }
        for c, b in crypto.items()
    }
    res = analyse(panel)
    res["continue_rule"] = continue_rule(res["cells"])
    valid = panel[np.isfinite(panel["W_EW10"]) | np.isfinite(panel["W_BTC"])]
    samples_meta = {}
    for sample in SAMPLES:
        sub = sample_rows(panel, sample)
        samples_meta[sample] = {
            "start": SAMPLES[sample],
            "n_weeks_calendar": int(len(sub)),
            **{f"n_weeks_W_{s}": int(np.isfinite(sub[f"W_{s}"]).sum()) for s in SIGNALS},
            "n_holiday_monday": int(sub["holiday_monday"].sum()),
            "n_friday_holiday": int(sub["friday_holiday"].sum()),
            "first_monday": str(sub["target"].min()),
            "last_monday_with_W": str(sub[np.isfinite(sub["W_BTC"])]["target"].max()),
        }
    res["meta"] = {
        "iter_id": ITER_ID,
        "generated_at": datetime.now(UTC).isoformat(),
        "placebo": {"shuffles": N_SHUFFLES, "seed": PLACEBO_SEED},
        "signals": SIGNALS,
        "coins": COINS,
        "etfs": ETFS,
        "segments": SEGMENTS,
        "groupings": {k: f"W < {v}" for k, v in GROUPINGS.items()},
        "samples": samples_meta,
        "crypto_bar_coverage": coverage,
        "etf_last_date": str(max(etf["date"])),
        "n_cells": len(res["cells"]),
        "n_weeks_with_any_W": int(len(valid)),
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "results.json").write_text(json.dumps(res, indent=1, default=float) + "\n")
    (OUT_DIR / "split-table.md").write_text(render_markdown(res))
    cr = res["continue_rule"]
    print(
        json.dumps(
            {
                "continue_to_batch": cr["continue_to_batch"],
                "gap_replicates": cr["gap_effect_replicates_in_our_data"],
                "verdict": cr["verdict"],
                "label": cr["refutation_label"] or cr["label_if_any"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
