"""P6 option-implied signals: data gate F1-F4 on the pulled DoltHub volatility_history.

T-20261005-44.  Reads the pulled ``data/dolthub_options/volatility_history/all_*.parquet``, the
equity-book panel (adv_rank) and adjusted prices, and checks the pre-registered data gate in
``reports/research/iterations/t20261005_p6_iv_signals/hypotheses.md`` section 4.

This script measures data availability and timing only.  It never relates any option field to a
future return: the only price statistic is the cross-sectional rank correlation between the
published ``hv_current`` and historical volatility computed from past closes (F2).  Nothing after
2026-09-17 is read (prices, panel, volatility_history); the single metadata query on ``dolt_log``
returns commit times and is filtered to data dates <= 2026-09-17.

Outputs: ``data-feasibility-measured.json`` and ``cache/volhist_sessions.parquet`` (column ``t`` is
the signal session under the measured as-of and publication rules).
"""

from __future__ import annotations

import json
import math
import os
import re
import sys
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

ITER = Path(
    os.environ.get(
        "P6_GATE_OUT",
        ROOT / "reports" / "research" / "iterations" / "t20261005_p6_iv_signals",
    )
)  # P6_GATE_OUT only redirects smoke runs
VOLHIST_DIR = ROOT / "data" / "dolthub_options" / "volatility_history"
EQUITY_BOOK = ROOT / "data" / "research" / "equity_book"

HOLDOUT_END = pd.Timestamp("2026-09-17")  # nothing later is read
WIN_START = pd.Timestamp("2024-01-08")
WIN_END = pd.Timestamp("2026-09-15")
LATE_START = pd.Timestamp("2024-10-01")
L12_RANK = 1000
SPEARMAN_MIN_N = 200
AUTOCORR_MIN_PAIRS = 100
F2_WINDOWS = (10, 20, 21, 22, 30)
VALUE_COLS = [
    "hv_current",
    "hv_week_ago",
    "hv_month_ago",
    "iv_current",
    "iv_week_ago",
    "iv_month_ago",
    "iv_year_high",
    "iv_year_low",
]
PREV_BETTER_MARGIN = 0.01
PUBLICATION_PASS_SHARE = 0.95
NEW_YORK = ZoneInfo("America/New_York")
DEADLINE_LOCAL = time(15, 50)

THRESHOLDS = {
    "f1_window_days_min": 550,
    "f1_late_coverage_min": 0.95,
    "f1_median_symbols_min": 1200,
    "f1b_median_l12_join_min": 0.60,
    "f3_iv_in_range_min": 0.99,
    "f3_iv_range": [0.02, 5.0],
    "f3_autocorr_median_min": 0.90,
    "f3_stale_max": 0.05,
    "f2_prev_better_margin": PREV_BETTER_MARGIN,
    "f2_publication_pass_share": PUBLICATION_PASS_SHARE,
    "f2_spearman_min_symbols": SPEARMAN_MIN_N,
    "f3_autocorr_min_pairs": AUTOCORR_MIN_PAIRS,
}
DELISTED_PROBES = [
    "TWTR", "SIVB", "FRC", "ATVI", "XLNX", "CTXS", "DISCA", "VIAC", "CERN", "KSU", "PXD", "SBNY",
]  # fmt: skip


# --------------------------------------------------------------------------- loading


def load_volhist(directory: Path = VOLHIST_DIR) -> pd.DataFrame:
    frames = [
        pd.read_parquet(p) for p in sorted(directory.glob("all_*.parquet")) if p.stat().st_size > 0
    ]
    frames = [f for f in frames if len(f)]
    if not frames:
        raise SystemExit("no volatility_history rows found")
    vh = pd.concat(frames, ignore_index=True)
    vh["date"] = pd.to_datetime(vh["date"])
    vh = vh[vh["date"] <= HOLDOUT_END].rename(columns={"act_symbol": "symbol"})
    for col in VALUE_COLS:
        vh[col] = vh[col].astype("float64")
    return vh.drop_duplicates(["date", "symbol"]).reset_index(drop=True)


def load_sessions() -> pd.DatetimeIndex:
    from scripts.analyze_equity_book_regimes import load_etf

    spy = load_etf()[0]["SPY"].dropna()
    idx = pd.DatetimeIndex(spy.index).normalize()
    return idx[idx <= HOLDOUT_END].sort_values()


# --------------------------------------------------------------------------- F1 / F1b


def coverage_stats(data_days: pd.DatetimeIndex, sessions: pd.DatetimeIndex) -> dict[str, Any]:
    win = sessions[(sessions >= WIN_START) & (sessions <= WIN_END)]
    late = sessions[(sessions >= LATE_START) & (sessions <= WIN_END)]
    have = set(data_days)
    n_win = sum(1 for s in win if s in have)
    n_late = sum(1 for s in late if s in have)
    return {
        "window_sessions": len(win),
        "window_days_with_data": n_win,
        "late_sessions": len(late),
        "late_days_with_data": n_late,
        "late_coverage": n_late / len(late) if len(late) else float("nan"),
    }


def join_rate_by_date(l12: pd.DataFrame, vh: pd.DataFrame) -> pd.Series:
    """|L12 ∩ vol| / |L12| per date, on dates that have volatility rows."""
    vh_days = vh["date"].unique()
    sub = l12[l12["date"].isin(vh_days)]
    denom = sub.groupby("date")["symbol"].nunique()
    merged = sub.merge(vh[["date", "symbol"]], on=["date", "symbol"], how="inner")
    num = merged.groupby("date")["symbol"].nunique().reindex(denom.index).fillna(0)
    return (num / denom).sort_index()


def never_matched_top(l12: pd.DataFrame, vh: pd.DataFrame, n: int = 20) -> list[dict[str, Any]]:
    vh_days = vh["date"].unique()
    sub = l12[l12["date"].isin(vh_days)]
    matched = set(sub.merge(vh[["date", "symbol"]], on=["date", "symbol"])["symbol"])
    miss = sub[~sub["symbol"].isin(matched)]
    agg = miss.groupby("symbol").agg(
        adv_median=("dollar_adv_21", "median"), l12_days=("date", "count")
    )
    agg = agg.sort_values("adv_median", ascending=False).head(n)
    return [
        {"symbol": s, "median_dollar_adv_21": float(r.adv_median), "l12_days": int(r.l12_days)}
        for s, r in agg.iterrows()
    ]


def load_l12() -> pd.DataFrame:
    frames = []
    for year in (2024, 2025, 2026):
        p = pd.read_parquet(
            EQUITY_BOOK / "panel" / f"{year}.parquet",
            columns=["trade_date", "symbol", "adv_rank", "dollar_adv_21"],
        )
        p = p[(p["adv_rank"] <= L12_RANK) & (p["trade_date"] <= WIN_END)]
        frames.append(p.rename(columns={"trade_date": "date"}))
    out = pd.concat(frames, ignore_index=True)
    out["date"] = pd.to_datetime(out["date"]).dt.normalize()
    return out.drop_duplicates(["date", "symbol"])


# --------------------------------------------------------------------------- F2


def median_cross_spearman(
    a: pd.DataFrame, b: pd.DataFrame, dates: pd.DatetimeIndex, min_n: int = SPEARMAN_MIN_N
) -> tuple[float, int, float]:
    """Median over dates of the cross-sectional Spearman between rows of ``a`` and ``b``.

    Returns (median, number of dates used, mean symbols per date).
    """
    cors: list[float] = []
    sizes: list[int] = []
    cols = a.columns.intersection(b.columns)
    for d in dates:
        if d not in a.index or d not in b.index:
            continue
        x = a.loc[d, cols].to_numpy(dtype="float64")
        y = b.loc[d, cols].to_numpy(dtype="float64")
        ok = np.isfinite(x) & np.isfinite(y)
        if ok.sum() < min_n:
            continue
        rx = pd.Series(x[ok]).rank().to_numpy()
        ry = pd.Series(y[ok]).rank().to_numpy()
        if rx.std() == 0 or ry.std() == 0:
            continue
        cors.append(float(np.corrcoef(rx, ry)[0, 1]))
        sizes.append(int(ok.sum()))
    if not cors:
        return float("nan"), 0, 0.0
    return float(np.median(cors)), len(cors), float(np.mean(sizes))


def f2_timing(
    hv: pd.DataFrame,
    log_ret: pd.DataFrame,
    dates: pd.DatetimeIndex,
    windows: tuple[int, ...] = F2_WINDOWS,
    min_n: int = SPEARMAN_MIN_N,
) -> dict[str, Any]:
    """Compare hv_current with historical vol ending at d (H_same) or the prior session (H_prev)."""
    table: list[dict[str, Any]] = []
    for w in windows:
        hist = log_ret.rolling(w, min_periods=w).std()
        for name, frame in (("H_same", hist), ("H_prev", hist.shift(1))):
            med, n_dates, mean_n = median_cross_spearman(hv, frame, dates, min_n)
            table.append(
                {
                    "w": w,
                    "hypothesis": name,
                    "median_spearman": med,
                    "n_dates": n_dates,
                    "mean_symbols": mean_n,
                }
            )
    best = {
        h: max(
            (
                r["median_spearman"]
                for r in table
                if r["hypothesis"] == h and not math.isnan(r["median_spearman"])
            ),
            default=float("nan"),
        )
        for h in ("H_same", "H_prev")
    }
    best_w = {
        h: max(
            (r for r in table if r["hypothesis"] == h and not math.isnan(r["median_spearman"])),
            key=lambda r: r["median_spearman"],
            default={"w": None},
        )["w"]
        for h in ("H_same", "H_prev")
    }
    prev_better = best["H_prev"] - best["H_same"]
    rule = "previous_session" if prev_better >= PREV_BETTER_MARGIN else "same_day"
    return {
        "table": table,
        "best_median_same": best["H_same"],
        "best_median_prev": best["H_prev"],
        "best_w_same": best_w["H_same"],
        "best_w_prev": best_w["H_prev"],
        "prev_minus_same": prev_better,
        "as_of_rule": rule,
    }


def holiday_identical_share(vh: pd.DataFrame, sessions: pd.DatetimeIndex) -> dict[str, Any]:
    """Share of rows on non-session weekdays identical to the previous trading day's row."""
    sess = set(sessions)
    days = sorted(d for d in vh["date"].unique() if pd.Timestamp(d) not in sess)
    by_day = {d: g.set_index("symbol")[VALUE_COLS] for d, g in vh.groupby("date")}
    same = total = 0
    same_late = total_late = 0
    for d in days:
        d = pd.Timestamp(d)
        pos = sessions.searchsorted(d) - 1
        if pos < 0 or sessions[pos] not in by_day:
            continue
        cur, prev = by_day[d], by_day[sessions[pos]]
        common = cur.index.intersection(prev.index)
        if not len(common):
            continue
        a, b = cur.loc[common], prev.loc[common]
        eq = ((a == b) | (a.isna() & b.isna())).all(axis=1)
        same += int(eq.sum())
        total += len(common)
        if d >= LATE_START:
            same_late += int(eq.sum())
            total_late += len(common)
    return {
        "holiday_dates_with_rows": len(days),
        "rows_compared": total,
        "identical_share": same / total if total else None,
        "rows_compared_from_2024_10": total_late,
        "identical_share_from_2024_10": same_late / total_late if total_late else None,
    }


def parse_dolt_log(rows: list[dict[str, str]]) -> list[tuple[pd.Timestamp, datetime]]:
    """(data date, commit time in UTC) for 'volatility_history YYYY-MM-DD update' commits."""
    out = []
    for r in rows:
        m = re.fullmatch(
            r"volatility_history (\d{4}-\d{2}-\d{2}) update", str(r.get("message", ""))
        )
        if not m:
            continue
        commit = pd.Timestamp(r["date"]).to_pydatetime().replace(tzinfo=UTC)
        out.append((pd.Timestamp(m.group(1)), commit))
    return out


def publication_delays(
    commits: list[tuple[pd.Timestamp, datetime]],
    sessions: pd.DatetimeIndex,
    calendar: pd.DatetimeIndex,
    rule: str,
) -> list[int]:
    """Sessions of delay per commit: commits after the 15:50 ET deadline of each later session.

    ``t`` is the data date (same_day) or the session before it (previous_session).  Deadline of
    delay 0 is 15:50 ET of the first calendar session after ``t``; each further session whose
    15:50 ET is also before the commit adds one.
    """
    delays = []
    for d, commit in commits:
        if d not in sessions:
            continue
        pos = sessions.get_loc(d)
        t = sessions[pos - 1] if rule == "previous_session" else d
        if rule == "previous_session" and pos == 0:
            continue
        later = calendar[calendar > t]
        count = 0
        for s in later:
            deadline = datetime.combine(s.date(), DEADLINE_LOCAL, tzinfo=NEW_YORK).astimezone(UTC)
            if commit > deadline:
                count += 1
            else:
                break
        delays.append(count)
    return delays


def publication_shift(delays: list[int]) -> tuple[int, float | None]:
    """0 when >= 95% of commits are on time, else the 95th percentile delay (>= 1, 'higher')."""
    if not delays:
        return 1, None
    on_time = sum(1 for k in delays if k == 0) / len(delays)
    if on_time >= PUBLICATION_PASS_SHARE:
        return 0, on_time
    return max(1, math.ceil(float(np.percentile(delays, 95, method="higher")))), on_time


# --------------------------------------------------------------------------- F3


def stale_share(wide: pd.DataFrame) -> tuple[float, int]:
    """Share of (symbol, session) pairs equal to the same symbol's previous-session value."""
    cur, prev = wide.iloc[1:].to_numpy(), wide.iloc[:-1].to_numpy()
    ok = np.isfinite(cur) & np.isfinite(prev)
    n = int(ok.sum())
    return (float((cur[ok] == prev[ok]).sum() / n) if n else float("nan")), n


def lag1_autocorr_median(
    wide: pd.DataFrame, min_pairs: int = AUTOCORR_MIN_PAIRS
) -> tuple[float, int]:
    cur, prev = wide.iloc[1:].to_numpy(), wide.iloc[:-1].to_numpy()
    ok = np.isfinite(cur) & np.isfinite(prev)
    n = ok.sum(axis=0)
    x = np.where(ok, cur, 0.0)
    y = np.where(ok, prev, 0.0)
    with np.errstate(invalid="ignore", divide="ignore"):
        mx, my = x.sum(axis=0) / n, y.sum(axis=0) / n
        dx, dy = np.where(ok, cur - mx, 0.0), np.where(ok, prev - my, 0.0)
        corr = (dx * dy).sum(axis=0) / np.sqrt((dx**2).sum(axis=0) * (dy**2).sum(axis=0))
    keep = (n >= min_pairs) & np.isfinite(corr)
    return (float(np.median(corr[keep])) if keep.any() else float("nan")), int(keep.sum())


# --------------------------------------------------------------------------- driver


def load_log_returns(symbols: list[str], sessions: pd.DatetimeIndex) -> pd.DataFrame:
    parts = []
    for year in (2023, 2024, 2025, 2026):
        p = pd.read_parquet(
            EQUITY_BOOK / "prices" / f"{year}.parquet", columns=["trade_date", "symbol", "close"]
        )
        p = p[(p["trade_date"] <= HOLDOUT_END) & p["symbol"].isin(symbols)]
        parts.append(p)
    px = pd.concat(parts, ignore_index=True).drop_duplicates(["trade_date", "symbol"])
    wide = px.pivot(index="trade_date", columns="symbol", values="close")
    wide.index = pd.DatetimeIndex(wide.index).normalize()
    wide = wide.reindex(sessions[sessions >= pd.Timestamp("2023-06-01")]).astype("float64")
    return np.log(wide).diff()


def fetch_dolt_log() -> list[dict[str, str]]:
    import fetch_dolthub_options as fdo  # noqa: PLC0415

    client = fdo.Client(min_interval=0.3)
    return client.query("SELECT date, message FROM dolt_log LIMIT 100")


def main() -> int:
    vh = load_volhist()
    sessions = load_sessions()
    sess_set = set(sessions)
    vh_all = vh
    vh = vh[vh["date"].isin(sess_set)].copy()
    data_days = pd.DatetimeIndex(sorted(vh["date"].unique()))

    # F1
    cov = coverage_stats(data_days, sessions)
    in_win = vh[(vh["date"] >= WIN_START) & (vh["date"] <= WIN_END)]
    per_day = in_win.groupby("date")["symbol"].nunique()
    f1 = cov | {"median_symbols_per_day": float(per_day.median())}
    f1["pass_days"] = f1["window_days_with_data"] >= THRESHOLDS["f1_window_days_min"]
    f1["pass_coverage"] = f1["late_coverage"] >= THRESHOLDS["f1_late_coverage_min"]
    f1["pass_symbols"] = f1["median_symbols_per_day"] >= THRESHOLDS["f1_median_symbols_min"]
    f1["pass"] = bool(f1["pass_days"] and f1["pass_coverage"] and f1["pass_symbols"])

    # F1b
    l12 = load_l12()
    rate = join_rate_by_date(l12, in_win)
    by_year = {
        str(y): float(rate[rate.index.year == y].median()) for y in sorted(set(rate.index.year))
    }
    f1b = {
        "median_l12_join": float(rate.median()),
        "dates": int(len(rate)),
        "median_by_year": by_year,
        "never_matched_top20": never_matched_top(l12, in_win),
    }
    f1b["pass"] = bool(f1b["median_l12_join"] >= THRESHOLDS["f1b_median_l12_join_min"])
    del l12

    # F3
    iv = in_win["iv_current"].dropna()
    lo, hi = THRESHOLDS["f3_iv_range"]
    pad_start = sessions[max(sessions.searchsorted(WIN_START) - 1, 0)]
    wide_iv = (
        vh[(vh["date"] >= pad_start) & (vh["date"] <= WIN_END)]
        .pivot(index="date", columns="symbol", values="iv_current")
        .reindex(sessions[(sessions >= pad_start) & (sessions <= WIN_END)])
    )
    ac, n_ac = lag1_autocorr_median(wide_iv[wide_iv.index >= LATE_START])
    stale_win, n_pairs_win = stale_share(wide_iv)
    stale_late, n_pairs_late = stale_share(wide_iv[wide_iv.index >= LATE_START])
    f3 = {
        "iv_nonnull_rows": int(len(iv)),
        "iv_in_range_share": float(((iv >= lo) & (iv <= hi)).mean()),
        "autocorr_lag1_median_from_2024_10": ac,
        "autocorr_symbols": n_ac,
        "stale_share_window": stale_win,
        "stale_pairs_window": n_pairs_win,
        "stale_share_from_2024_10": stale_late,
        "stale_pairs_from_2024_10": n_pairs_late,
    }
    f3["pass_range"] = f3["iv_in_range_share"] >= THRESHOLDS["f3_iv_in_range_min"]
    f3["pass_autocorr"] = ac >= THRESHOLDS["f3_autocorr_median_min"]
    f3["pass_stale"] = stale_window_ok = stale_win <= THRESHOLDS["f3_stale_max"]
    f3["pass"] = bool(f3["pass_range"] and f3["pass_autocorr"] and stale_window_ok)
    del wide_iv

    # F2 timing
    f2_dates = data_days[(data_days >= LATE_START) & (data_days <= WIN_END)]
    hv_wide = (
        vh[(vh["date"] >= LATE_START) & (vh["date"] <= WIN_END)]
        .pivot(index="date", columns="symbol", values="hv_current")
        .reindex(sessions[sessions >= pd.Timestamp("2023-06-01")])
    )
    log_ret = load_log_returns(list(hv_wide.columns), sessions)
    f2 = f2_timing(hv_wide, log_ret.reindex(columns=hv_wide.columns), f2_dates)
    del log_ret, hv_wide
    f2["holiday_rows"] = holiday_identical_share(vh_all, sessions)
    rule = f2["as_of_rule"]

    calendar_mod = importlib_calendar()
    cal = pd.DatetimeIndex(
        [pd.Timestamp(d) for d in calendar_mod(date(2026, 1, 1), date(2026, 12, 31))]
    )
    log_rows = fetch_dolt_log()
    commits = [c for c in parse_dolt_log(log_rows) if c[0] <= HOLDOUT_END]
    delays = publication_delays(commits, sessions, cal, rule)
    shift, on_time = publication_shift(delays)
    f2["publication"] = {
        "dolt_log_rows": len(log_rows),
        "volatility_history_commits_used": len(delays),
        "commit_time_zone_assumption": "dolt_log date is UTC",
        "share_on_time": on_time,
        "delay_counts": {str(k): delays.count(k) for k in sorted(set(delays))},
        "publication_shift_sessions": shift,
    }

    # F4
    first_last = {
        s: (
            [
                str(vh_all.loc[vh_all["symbol"] == s, "date"].min().date()),
                str(vh_all.loc[vh_all["symbol"] == s, "date"].max().date()),
            ]
            if (vh_all["symbol"] == s).any()
            else None
        )
        for s in DELISTED_PROBES
    }
    sym_2019 = set(vh_all.loc[vh_all["date"].dt.year == 2019, "symbol"])
    sym_2026 = set(vh_all.loc[vh_all["date"].dt.year == 2026, "symbol"])
    f4 = {
        "symbols_2019": len(sym_2019),
        "symbols_2019_absent_2026": len(sym_2019 - sym_2026),
        "probe_first_last": first_last,
    }

    gate_pass = bool(f1["pass"] and f1b["pass"] and f3["pass"])
    signal_rule = (
        f"as_of_rule={rule}: a DoltHub row dated d is treated as information up to the close of "
        + ("the session before d" if rule == "previous_session" else "d")
        + f"; signal session t is that session plus {shift} further session(s) "
        "(publication_shift_sessions); only session-dated rows are kept; "
        "the decision is made at the close of t and filled at the t+1 open per the frozen contract."
    )
    result = {
        "task": "T-20261005-44",
        "computed_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "pull": {
            "rows_total": int(len(vh_all)),
            "rows_on_sessions": int(len(vh)),
            "first_date": str(vh_all["date"].min().date()),
            "last_date": str(vh_all["date"].max().date()),
            "holdout_end_not_exceeded": bool(vh_all["date"].max() <= HOLDOUT_END),
        },
        "thresholds": THRESHOLDS,
        "f1": f1,
        "f1b": f1b,
        "f2": f2,
        "f3": f3,
        "f4": f4,
        "gate_pass": gate_pass,
        "as_of_rule": rule,
        "publication_shift_sessions": shift,
        "signal_date_rule": signal_rule,
    }
    (ITER / "cache").mkdir(parents=True, exist_ok=True)
    (ITER / "data-feasibility-measured.json").write_text(json.dumps(result, indent=1, default=str))

    pos = sessions.get_indexer(vh["date"])
    pos = pos - (1 if rule == "previous_session" else 0) + shift
    keep = (pos >= 0) & (pos < len(sessions))
    out = vh.loc[keep].copy()
    out["src_date"] = out["date"]
    out["t"] = sessions[pos[keep]]
    out = out[out["t"] <= HOLDOUT_END]
    cols = [
        "t",
        "symbol",
        "src_date",
        "iv_current",
        "iv_week_ago",
        "iv_month_ago",
        "hv_current",
        "hv_week_ago",
        "hv_month_ago",
    ]
    out[cols].to_parquet(ITER / "cache" / "volhist_sessions.parquet", index=False)
    print(
        json.dumps(
            {k: result[k] for k in ("gate_pass", "as_of_rule", "publication_shift_sessions")}
        )
    )
    return 0


def importlib_calendar():
    from open_composer.market_calendar import us_equity_session_dates

    return us_equity_session_dates


if __name__ == "__main__":
    raise SystemExit(main())
