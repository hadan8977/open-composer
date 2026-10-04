#!/usr/bin/env python3
"""Frozen test of h20261004_pm_earnings_beat_odds (T-20261004-51, step 3).

Reads the event table built by ``scripts/build_pm_earnings_events.py`` and SIP daily bars
(read-only, adjusted). Order of work, as frozen in hypotheses.md:

1. positive control (realized beat vs window excess return); t < 3 -> ``pipeline_suspect``
   and stop before H-A;
2. calibration table;
3. H-A: weekly IC of A1, tercile spread gross/net, 1000 within-week shuffles (seed
   20261004), A3 with Holm over A1 and A3, three placebos, sub-periods, minimum detectable
   effect;
4. overlay scoring only if the continue rule passes.

Interpretations the design left open (fixed here before the first real run):

* the positive control gate is the event-level pooled t with week-clustered SE (lead ruling
  2026-10-04, before any H-A statistic); the weekly-IC t is reported next to it;
* weeks with fewer than 6 events are pooled forward within a reporting season (event weeks
  at most 2 weeks apart); a short tail merges into the previous pool; a season with fewer
  than 6 events in total is dropped and counted;
* A3 needs a P7 print (no staleness filter on P7); A1 is also reported on that subsample;
* tercile: percent rank (average ties) > 2/3 is top, <= 1/3 is bottom;
* net per pair = gross - 4 x side cost - 1%/yr borrow x sessions held / 252;
* the Holm p values come from one-sided t tests on the weekly IC series.
"""

# ruff: noqa: E501
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from open_composer.market_sessions import us_equity_session_dates  # noqa: E402

ITER_ID = "h20261004_pm_earnings_beat_odds"
ITER_DIR = ROOT / "reports/research/iterations" / ITER_ID
EVENTS_PATH = ROOT / "data/research/prediction_markets/polymarket_earnings/events.parquet"
SEED = 20261004
N_SHUFFLES = 1000
MIN_EVENTS_PER_WEEK = 6
MIN_VOLUME = 5000.0
MIN_CLOSE = 5.0
SPLIT_DATE = pd.Timestamp("2026-03-01")
SIDE_BPS = {"primary": 10.0, "stress": 20.0}
BORROW_ANNUAL = 0.01
SEASON_GAP_WEEKS = 2
CONTROL_T_MIN = 3.0
EXTREME_P = 0.03  # P >= 0.97 or <= 0.03 counts as outcome-revealing at the cut
EXTREME_SHARE_FLAG = 0.05
#: Lead ruling (2026-10-04 08:2x UTC, before any H-A statistic was seen): the positive control
#: "its t" is the event-level t of beat vs window excess return with week-clustered SE; the
#: weekly-IC t is reported next to it. The announcement time is the EDGAR "Accepted" time.
CONTROL_RULING = (
    "Lead ruling 2026-10-04 (Opus, interactive session), made before any H-A statistic was seen: "
    "the positive-control t is the event-level pooled t with week-clustered SE; the weekly-IC t "
    "was the implementer's reading and is reported only. Corrected EDGAR timing is the frozen test."
)
CONTINUE_T = 2.0
STOP_T = 1.0
ALPHA_ONE_SIDED = 0.05
POWER_Z = 1.6449 + 0.8416  # 5% one-sided test at 80% power


# ------------------------------------------------------------------ returns


def load_bars(symbols: set[str], start: date, end: date) -> dict[str, pd.DataFrame]:
    """Adjusted daily open/close per symbol, indexed by the Eastern session date."""
    import duckdb

    quoted = ",".join(f"'{s}'" for s in sorted(symbols))
    con = duckdb.connect()
    try:
        con.execute("SET memory_limit='400MB'")
        df = con.execute(
            "SELECT symbol, timestamp, open, close FROM read_parquet('data/sip/daily/**/*.parquet') "
            f"WHERE symbol IN ({quoted}) AND timestamp >= TIMESTAMPTZ '{start} 00:00:00+00' "
            f"AND timestamp <= TIMESTAMPTZ '{end} 23:59:59+00' ORDER BY symbol, timestamp"
        ).fetchdf()
    finally:
        con.close()
    ts = pd.to_datetime(df["timestamp"], utc=True).dt.tz_convert("America/New_York")
    df["date"] = pd.to_datetime(ts.dt.date)
    return {s: g.set_index("date")[["open", "close"]] for s, g in df.groupby("symbol")}


def _px(bars: dict[str, pd.DataFrame], sym: str, day: pd.Timestamp, col: str) -> float:
    frame = bars.get(sym)
    if frame is None or pd.isna(day) or day not in frame.index:
        return float("nan")
    return float(frame.at[day, col])


def attach_returns(events: pd.DataFrame, bars: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Window excess return (S close -> R close), the R+1 placebo and the open-exit variant."""
    out = events.copy()
    r1 = [_next_session(r) for r in out["R"]]
    out["R1"] = r1
    cols: dict[str, list[float]] = {
        k: [] for k in ("close_S", "ret_win", "ret_next", "ret_open_exit", "hold_sessions")
    }
    sessions = {}
    for ev, r_next in zip(out.itertuples(), r1, strict=True):
        t = ev.ticker
        cs = _px(bars, t, ev.S, "close")
        cr = _px(bars, t, ev.R, "close")
        cr1 = _px(bars, t, r_next, "close")
        o1 = _px(bars, t, r_next, "open")
        ms, mr = _px(bars, "SPY", ev.S, "close"), _px(bars, "SPY", ev.R, "close")
        mr1, mo1 = _px(bars, "SPY", r_next, "close"), _px(bars, "SPY", r_next, "open")
        cols["close_S"].append(cs)
        cols["ret_win"].append((cr / cs - 1.0) - (mr / ms - 1.0))
        cols["ret_next"].append((cr1 / cr - 1.0) - (mr1 / mr - 1.0))
        cols["ret_open_exit"].append((o1 / cs - 1.0) - (mo1 / ms - 1.0))
        key = (ev.S, ev.R)
        if key not in sessions and not (pd.isna(ev.S) or pd.isna(ev.R)):
            sessions[key] = max(len(us_equity_session_dates(ev.S.date(), ev.R.date())) - 1, 1)
        cols["hold_sessions"].append(float(sessions.get(key, 1)))
    for k, v in cols.items():
        out[k] = v
    return out


def _next_session(day: pd.Timestamp) -> pd.Timestamp:
    if pd.isna(day):
        return pd.NaT
    from open_composer.market_sessions import next_us_equity_session

    return pd.Timestamp(next_us_equity_session(day.date()))


# ------------------------------------------------------------------ samples and groups


def primary_sample(df: pd.DataFrame) -> pd.DataFrame:
    keep = (
        df["ticker"].notna()
        & df["beat"].notna()
        & df["sip_bars_ok"].fillna(False).astype(bool)
        & df["R"].notna()
        & df["P"].notna()
        & ~df["P_stale"].fillna(True).astype(bool)
        & (df["volume_usd"].fillna(0) >= MIN_VOLUME)
        & (df["close_S"] >= MIN_CLOSE)
        & df["ret_win"].notna()
    )
    return df[keep].copy()


def secondary_sample(df: pd.DataFrame) -> pd.DataFrame:
    keep = (
        df["ticker"].notna()
        & df["beat"].notna()
        & df["R"].notna()
        & df["P"].notna()
        & (df["close_S"] >= MIN_CLOSE)
        & df["ret_win"].notna()
    )
    return df[keep].copy()


def funnel_with_returns(df: pd.DataFrame) -> dict[str, int]:
    steps = [
        ("all_events", pd.Series(True, index=df.index)),
        ("ticker_parsed_and_resolved", df["ticker"].notna() & df["beat"].notna()),
        ("sip_bars", df["sip_bars_ok"].fillna(False).astype(bool)),
        ("timing_matched_8k", df["R"].notna()),
        ("p_valid", df["P"].notna()),
        ("not_stale", ~df["P_stale"].fillna(True).astype(bool)),
        ("volume_ge_5k", df["volume_usd"].fillna(0) >= MIN_VOLUME),
        ("close_ge_5_and_returns", (df["close_S"] >= MIN_CLOSE) & df["ret_win"].notna()),
    ]
    mask = pd.Series(True, index=df.index)
    out = {}
    for name, m in steps:
        mask = mask & m
        out[name] = int(mask.sum())
    return out


def assign_groups(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    """Pool ISO weeks of R into groups of at least MIN_EVENTS_PER_WEEK within a season."""
    if df.empty:
        return df.assign(grp=pd.Series(dtype=int)), {"groups": 0, "dropped_events": 0}
    monday = pd.to_datetime(df["R"]).dt.normalize() - pd.to_timedelta(
        pd.to_datetime(df["R"]).dt.weekday, unit="D"
    )
    week_no = ((monday - pd.Timestamp("2000-01-03")).dt.days // 7).astype(int)
    counts = week_no.value_counts().sort_index()
    weeks = list(counts.index)
    seasons: list[list[int]] = []
    for w in weeks:
        if seasons and w - seasons[-1][-1] <= SEASON_GAP_WEEKS:
            seasons[-1].append(w)
        else:
            seasons.append([w])
    mapping: dict[int, int] = {}
    dropped_weeks: set[int] = set()
    gid = 0
    for season in seasons:
        groups: list[list[int]] = []
        current: list[int] = []
        total = 0
        for w in season:
            current.append(w)
            total += int(counts[w])
            if total >= MIN_EVENTS_PER_WEEK:
                groups.append(current)
                current, total = [], 0
        if current:
            if groups:
                groups[-1].extend(current)
            else:
                dropped_weeks.update(current)
        for members in groups:
            for w in members:
                mapping[w] = gid
            gid += 1
    out = df.copy()
    out["grp"] = week_no.map(mapping)
    dropped = int(out["grp"].isna().sum())
    out = out[out["grp"].notna()].copy()
    out["grp"] = out["grp"].astype(int)
    return out, {"groups": gid, "dropped_events": dropped}


# ------------------------------------------------------------------ statistics


def t_stat(x: np.ndarray) -> float:
    x = np.asarray(x, dtype=float)
    x = x[~np.isnan(x)]
    if len(x) < 2 or x.std(ddof=1) == 0:
        return float("nan")
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x))))


def one_sided_p(t: float, n: int) -> float:
    if math.isnan(t) or n < 2:
        return float("nan")
    return float(stats.t.sf(t, n - 1))


def _rank_z(values: np.ndarray) -> np.ndarray | None:
    r = stats.rankdata(values)
    sd = r.std()
    if sd == 0:
        return None
    return (r - r.mean()) / sd


def weekly_ic(df: pd.DataFrame, sig: str, ret: str) -> pd.Series:
    """Spearman IC per group (n >= 6, non-constant series only)."""
    vals: dict[int, float] = {}
    for g, part in df.groupby("grp"):
        if len(part) < MIN_EVENTS_PER_WEEK:
            continue
        a, b = _rank_z(part[sig].to_numpy(float)), _rank_z(part[ret].to_numpy(float))
        if a is None or b is None:
            continue
        vals[int(g)] = float((a * b).mean())
    return pd.Series(vals, dtype=float)


def pooled_ic(df: pd.DataFrame, sig: str, ret: str) -> dict[str, float]:
    """Pooled rank-z regression slope through the origin with group-clustered SE."""
    xs, ys, gs = [], [], []
    for g, part in df.groupby("grp"):
        if len(part) < MIN_EVENTS_PER_WEEK:
            continue
        a, b = _rank_z(part[sig].to_numpy(float)), _rank_z(part[ret].to_numpy(float))
        if a is None or b is None:
            continue
        xs.append(a)
        ys.append(b)
        gs.append(np.full(len(a), g))
    if not xs:
        return {"ic": float("nan"), "se": float("nan"), "t": float("nan"), "n": 0}
    x, y, g = np.concatenate(xs), np.concatenate(ys), np.concatenate(gs)
    sxx = float((x * x).sum())
    beta = float((x * y).sum() / sxx)
    resid = y - beta * x
    cluster = pd.Series(x * resid).groupby(g).sum().to_numpy()
    se = math.sqrt(float((cluster**2).sum())) / sxx
    return {"ic": beta, "se": se, "t": beta / se if se > 0 else float("nan"), "n": int(len(x))}


def tercile_spreads(df: pd.DataFrame, sig: str, ret: str) -> pd.DataFrame:
    rows = []
    for g, part in df.groupby("grp"):
        if len(part) < MIN_EVENTS_PER_WEEK:
            continue
        pr = part[sig].rank(method="average") / len(part)
        top, bot = part.loc[pr > 2 / 3, ret], part.loc[pr <= 1 / 3, ret]
        if top.empty or bot.empty:
            continue
        rows.append(
            {
                "grp": int(g),
                "spread": float(top.mean() - bot.mean()),
                "n_top": len(top),
                "n_bottom": len(bot),
                "hold": float(part["hold_sessions"].mean()),
                "date": part["R"].min(),
            }
        )
    return pd.DataFrame(rows)


def spread_summary(spreads: pd.DataFrame) -> dict[str, Any]:
    if spreads.empty:
        return {"n_groups": 0}
    gross = spreads["spread"].to_numpy()
    borrow = BORROW_ANNUAL * spreads["hold"].to_numpy() / 252.0
    out: dict[str, Any] = {
        "n_groups": int(len(spreads)),
        "gross_mean_bp": float(gross.mean() * 1e4),
        "gross_t": t_stat(gross),
        "borrow_mean_bp": float(borrow.mean() * 1e4),
    }
    for name, side_bp in SIDE_BPS.items():
        net = gross - 4 * side_bp / 1e4 - borrow
        out[f"net_{name}_mean_bp"] = float(net.mean() * 1e4)
        out[f"net_{name}_t"] = t_stat(net)
    return out


def shuffle_ics(
    df: pd.DataFrame, sig: str, ret: str, n: int = N_SHUFFLES, seed: int = SEED
) -> np.ndarray:
    """Mean weekly IC under within-group shuffles of the signal."""
    rng = np.random.default_rng(seed)
    prepared = []
    for _, part in df.groupby("grp"):
        if len(part) < MIN_EVENTS_PER_WEEK:
            continue
        a, b = _rank_z(part[sig].to_numpy(float)), _rank_z(part[ret].to_numpy(float))
        if a is None or b is None:
            continue
        prepared.append((a, b))
    out = np.empty(n)
    for i in range(n):
        out[i] = (
            np.mean([(a[rng.permutation(len(a))] * b).mean() for a, b in prepared])
            if prepared
            else np.nan
        )
    return out


def ic_block(df: pd.DataFrame, sig: str, ret: str) -> dict[str, Any]:
    ic = weekly_ic(df, sig, ret)
    t = t_stat(ic.to_numpy())
    return {
        "n_events": int(len(df)),
        "n_weeks": int(len(ic)),
        "mean_ic": float(ic.mean()) if len(ic) else float("nan"),
        "sd_ic": float(ic.std(ddof=1)) if len(ic) > 1 else float("nan"),
        "t": t,
        "p_one_sided": one_sided_p(t, len(ic)),
        "pooled": pooled_ic(df, sig, ret),
    }


def mde(sd: float, n: int) -> float:
    return float(POWER_Z * sd / math.sqrt(n)) if n > 0 and not math.isnan(sd) else float("nan")


def holm(p_values: dict[str, float]) -> dict[str, float]:
    order = sorted(p_values, key=lambda k: p_values[k])
    adjusted: dict[str, float] = {}
    running = 0.0
    for i, k in enumerate(order):
        running = max(running, min(1.0, (len(order) - i) * p_values[k]))
        adjusted[k] = running
    return adjusted


# ------------------------------------------------------------------ analysis blocks


def calibration(df: pd.DataFrame) -> dict[str, Any]:
    p, y = df["P"].to_numpy(float), df["beat"].to_numpy(float)
    deciles = []
    try:
        bins = pd.qcut(df["P"], 10, duplicates="drop")
    except ValueError:
        bins = pd.Series(0, index=df.index)
    for _, part in df.groupby(bins, observed=True):
        deciles.append(
            {
                "n": int(len(part)),
                "mean_p": float(part["P"].mean()),
                "beat_rate": float(part["beat"].mean()),
            }
        )
    base = float(y.mean())
    ranks = stats.rankdata(p)
    pos, neg = y == 1, y == 0
    auc = (
        float((ranks[pos].sum() - pos.sum() * (pos.sum() + 1) / 2) / (pos.sum() * neg.sum()))
        if pos.any() and neg.any()
        else float("nan")
    )
    return {
        "n": int(len(df)),
        "base_rate": base,
        "mean_p": float(p.mean()),
        "brier_p": float(((p - y) ** 2).mean()),
        "brier_base_rate": float(((base - y) ** 2).mean()),
        "auc": auc,
        "deciles": deciles,
    }


def extreme_p_share(df: pd.DataFrame) -> dict[str, Any]:
    """Share of events whose P at the cut is already near 0 or 1, by announcement timing."""
    out: dict[str, Any] = {}
    kinds = df["timing_kind"] if "timing_kind" in df else pd.Series("all", index=df.index)
    for kind in sorted(kinds.dropna().unique()):
        part = df[kinds == kind]
        ext = (part["P"] >= 1 - EXTREME_P) | (part["P"] <= EXTREME_P)
        out[str(kind)] = {
            "n": int(len(part)),
            "n_extreme": int(ext.sum()),
            "share": float(ext.mean()),
        }
    return out


def a1_with_shuffle(df: pd.DataFrame) -> dict[str, Any]:
    block = hA_block(df, "P")
    grouped, _ = assign_groups(df)
    shuffles = shuffle_ics(grouped, "P", "ret_win")
    block["shuffle"] = {
        "n": int(len(shuffles)),
        "p95": float(np.nanpercentile(shuffles, 95)),
        "mean": float(np.nanmean(shuffles)),
        "percentile_of_real": float((shuffles < block["mean_ic"]).mean() * 100.0),
    }
    return block


def hA_block(df: pd.DataFrame, sig: str, ret: str = "ret_win") -> dict[str, Any]:
    grouped, pooling = assign_groups(df)
    block = ic_block(grouped, sig, ret)
    block["pooling"] = pooling
    block["spread"] = spread_summary(tercile_spreads(grouped, sig, ret))
    block["mde_ic"] = mde(block["sd_ic"], block["n_weeks"])
    return block


def control_diagnostics(prim: pd.DataFrame) -> dict[str, Any]:
    """Positive-control cuts that never touch P: by timing kind, period and return window."""
    if "timing_kind" not in prim:
        prim = prim.assign(timing_kind=None)
    cuts: dict[str, pd.DataFrame] = {
        f"timing_{k}": prim[prim["timing_kind"] == k]
        for k in sorted(prim["timing_kind"].dropna().unique())
    }
    cuts["before_2026-03-01"] = prim[prim["R"] < SPLIT_DATE]
    cuts["from_2026-03-01"] = prim[prim["R"] >= SPLIT_DATE]
    out: dict[str, Any] = {}
    for name, part in cuts.items():
        grouped, _ = assign_groups(part)
        blk = ic_block(grouped, "beat", "ret_win") if len(grouped) else {"n_events": 0}
        out[name] = {k: blk.get(k) for k in ("n_events", "n_weeks", "mean_ic", "t")}
        out[name]["pooled_t"] = blk.get("pooled", {}).get("t")
    grouped, _ = assign_groups(prim)
    mean_gap = grouped.groupby("beat")["ret_win"].mean()
    out["mean_excess_return_by_outcome"] = {str(int(k)): float(v) for k, v in mean_gap.items()}
    out["open_exit_variant"] = {
        k: ic_block(grouped.dropna(subset=["ret_open_exit"]), "beat", "ret_open_exit").get(k)
        for k in ("n_weeks", "mean_ic", "t")
    }
    return out


def run_analysis(events: pd.DataFrame, bars: dict[str, pd.DataFrame]) -> dict[str, Any]:
    df = attach_returns(events, bars)
    df["A3"] = df["P"] - df["P7"]
    funnel = funnel_with_returns(df)
    prim = primary_sample(df)
    result: dict[str, Any] = {
        "iter_id": ITER_ID,
        "generated_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "seed": SEED,
        "sample": {
            "funnel": funnel,
            "primary_events": int(len(prim)),
            "first_R": str(prim["R"].min().date()) if len(prim) else None,
            "last_R": str(prim["R"].max().date()) if len(prim) else None,
        },
    }
    grouped, pooling = assign_groups(prim)
    result["sample"]["pooling"] = pooling
    result["sample"]["groups_with_ge_6"] = pooling["groups"]

    # 1. positive control
    control = ic_block(grouped, "beat", "ret_win")
    control["gate_t_min"] = CONTROL_T_MIN
    control["gate_statistic"] = "pooled_event_level_t_week_clustered"
    control["gate_t"] = control["pooled"]["t"]
    control["ruling"] = CONTROL_RULING
    result["positive_control"] = control
    result["calibration"] = calibration(prim)
    leak = extreme_p_share(prim)
    result["leakage_diagnostic"] = {
        "definition": "share of primary events with P >= 0.97 or P <= 0.03 at the 15:00 ET cut on S",
        "by_timing": leak,
        "flag_threshold": EXTREME_SHARE_FLAG,
    }
    if not control["gate_t"] >= CONTROL_T_MIN:
        result["verdict"] = "pipeline_suspect"
        result["positive_control_diagnostics"] = control_diagnostics(prim)
        result["continue_rule"] = {"evaluated": False, "reason": "positive_control_t_below_3"}
        result["overlay_scoring"] = "not_run"
        return result

    # 3. H-A
    a1 = a1_with_shuffle(prim)
    real = a1["mean_ic"]
    flagged = [k for k, v in leak.items() if v["n"] and v["share"] > EXTREME_SHARE_FLAG]
    if flagged:
        kinds = prim["timing_kind"]
        extreme = (prim["P"] >= 1 - EXTREME_P) | (prim["P"] <= EXTREME_P)
        drop = kinds.isin(flagged) & extreme
        result["robustness_excluding_extreme_p"] = {
            "note": "reported for reference only, not part of the verdict",
            "flagged_timing_kinds": flagged,
            "n_excluded": int(drop.sum()),
            "A1": a1_with_shuffle(prim[~drop]),
        }
    a3_sample = prim[prim["P7"].notna()]
    a3 = hA_block(a3_sample, "A3")
    a1_on_a3_sample = hA_block(a3_sample, "P")
    p_a1, p_a3 = a1["p_one_sided"], a3["p_one_sided"]
    adj = holm({"A1": p_a1, "A3": p_a3}) if not (math.isnan(p_a1) or math.isnan(p_a3)) else {}
    a3["holm_p"] = adj.get("A3")
    a1["holm_p"] = adj.get("A1")
    result["H_A"] = {"A1": a1, "A3": a3, "A1_on_A3_sample": a1_on_a3_sample}

    rule1 = bool(real > 0 and a1["t"] >= CONTINUE_T)
    rule2 = bool(a1["spread"].get("net_primary_mean_bp", float("nan")) > 0)
    rule3 = bool(real > a1["shuffle"]["p95"])
    stop = bool(real <= 0 or a1["t"] < STOP_T)
    verdict = (
        "continue" if (rule1 and rule2 and rule3) else "stop_refuted" if stop else "inconclusive"
    )
    result["continue_rule"] = {
        "evaluated": True,
        "rule1_ic_positive_t_ge_2": rule1,
        "rule2_net_spread_positive": rule2,
        "rule3_above_shuffle_p95": rule3,
        "stop_rule_triggered": stop,
        "mean_ic": real,
        "t": a1["t"],
        "net_spread_primary_bp": a1["spread"].get("net_primary_mean_bp"),
        "shuffle_p95": a1["shuffle"]["p95"],
    }
    result["verdict"] = verdict
    result["minimum_detectable_effect"] = {
        "mean_ic": a1["mde_ic"],
        "basis": "2.486 x realized sd of weekly IC / sqrt(weeks); 5% one-sided, 80% power",
        "spread_bp": mde(
            float(tercile_spreads(grouped, "P", "ret_win")["spread"].std(ddof=1) * 1e4)
            if len(grouped)
            else float("nan"),
            a1["spread"].get("n_groups", 0),
        ),
    }

    # secondary and placebos
    sec = secondary_sample(df)
    result["secondary"] = {
        "all_valid_p": hA_block(sec, "P"),
        "exit_open_after_R": hA_block(prim, "P", "ret_open_exit"),
        "sector_adjusted": {
            "status": "not_run",
            "reason": "no SIC/ticker to SPDR sector ETF map in the repo; building one now would be a new unfrozen input",
        },
    }
    p7_sample = prim[prim["P7"].notna()]
    next_sample = prim[prim["ret_next"].notna()]
    placebos = {
        "shuffle": a1["shuffle"],
        "stale_p7_signal": hA_block(p7_sample, "P7"),
        "next_session_return": hA_block(next_sample, "P", "ret_next"),
    }
    result["placebos"] = placebos
    pre = prim[prim["R"] < SPLIT_DATE]
    post = prim[prim["R"] >= SPLIT_DATE]
    result["sub_periods"] = {
        "before_2026-03-01": hA_block(pre, "P") if len(pre) else {"n_events": 0},
        "from_2026-03-01": hA_block(post, "P") if len(post) else {"n_events": 0},
    }

    if verdict == "continue":
        spreads = tercile_spreads(grouped, "P", "ret_win")
        net = spreads["spread"].to_numpy() - 4 * SIDE_BPS["primary"] / 1e4
        span_years = max((prim["R"].max() - prim["R"].min()).days / 365.25, 1e-9)
        active_per_year = len(spreads) / span_years
        result["weekly_long_short"] = {
            "active_weeks_per_year": active_per_year,
            "sharpe_net_primary": float(net.mean() / net.std(ddof=1) * math.sqrt(active_per_year)),
        }
        result["overlay_scoring"] = "pending"
    else:
        result["overlay_scoring"] = "not_run_continue_rule_not_passed"
    return result


# ------------------------------------------------------------------ outputs


DATA_DEFECT_NOTE = [
    "",
    "## Data-layer defect: `data/features/earnings_events/` acceptance_utc",
    "",
    "- Finding (2026-10-04): `acceptance_utc` is later than the true UTC acceptance instant by 4 h "
    "in daylight time and 5 h in standard time. The source value was already UTC and was converted "
    "once more as if it were Eastern wall-clock. Against EDGAR filing-index Accepted times: 11 of 11 "
    "hand-checked filings, and 1055 of 1055 matched accessions agree with the formula below "
    "(`data/research/prediction_markets/polymarket_earnings/edgar_accepted_cache.json`).",
    "- Affected: the `acceptance_utc` column of `earnings_events/{2024,2025,2026}.parquet` and every "
    "consumer that reads it as a true UTC instant (`scripts/build_sue_8k_visible.py` documents it that "
    "way and converts it to Eastern again). Dates near midnight and after-close classification shift; "
    "the `text_path`, `ex99_url` and accession fields are unaffected.",
    "- Cause: `scripts/build_earnings_events.py` treats the submissions API `acceptanceDateTime` as "
    "Eastern wall-clock (its `_EASTERN` comment). For these filings the API value is true UTC.",
    "- Suggested fix: in the builder, parse `acceptanceDateTime` as UTC; for the existing tables "
    "recover with `pd.to_datetime(x, utc=True).dt.tz_convert('America/New_York').dt.tz_localize(None)"
    ".dt.tz_localize('UTC')` (see `eastern_from_double_shifted` in "
    "`scripts/build_pm_earnings_events.py`). Check rows from other sources in the same table "
    "(10-K note: mixed conventions) before rewriting, and re-run the consumers that depend on the "
    "timestamp (`build_sue_8k_visible.py`, the earnings-text forward test).",
    "- Not changed here: neither the table nor its builder was edited; the lead schedules the repair.",
]


def _f(x: Any, nd: int = 3) -> str:
    return "n/a" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:.{nd}f}"


def write_outputs(result: dict[str, Any], out_dir: Path) -> None:
    flags = {
        "workflow_pass": True,
        "research_pass": result.get("verdict") == "continue",
        "llm_contribution_pass": False,
        "paper_ready_pass": False,
    }
    result = {**result, **flags}
    (out_dir / "results.json").write_text(json.dumps(result, indent=2, default=str) + "\n")
    rows = []
    if "H_A" in result:
        for cid, block in (("A1", result["H_A"]["A1"]), ("A3", result["H_A"]["A3"])):
            rows.append(
                {
                    "candidate_id": cid,
                    "decision_eligible": cid == "A1",
                    "mean_ic": block["mean_ic"],
                    "t": block["t"],
                    "n_weeks": block["n_weeks"],
                    "n_events": block["n_events"],
                    "spread": block["spread"],
                    "holm_p": block.get("holm_p"),
                    "verdict": result["verdict"] if cid == "A1" else "secondary_no_decision",
                }
            )
    else:
        rows.append(
            {"candidate_id": "A1", "decision_eligible": False, "verdict": result["verdict"]}
        )
    (out_dir / "trial-ledger.jsonl").write_text(
        "".join(json.dumps(r, default=str) + "\n" for r in rows)
    )

    lines = [f"# Report: {ITER_ID}", ""]
    s = result["sample"]
    lines.append(
        f"Verdict (mechanical, pending lead review): **{result['verdict']}**. "
        f"Primary events {s['primary_events']} ({s['first_R']} to {s['last_R']}), "
        f"{s['groups_with_ge_6']} week groups."
    )
    c = result["positive_control"]
    lines.append(
        f"- Positive control (gate: pooled event-level t, week-clustered SE, >= 3): "
        f"t {_f(c['pooled']['t'], 2)} on {c['pooled']['n']} events; weekly-IC {_f(c['mean_ic'])}, "
        f"t {_f(c['t'], 2)} over {c['n_weeks']} weeks (reported only). {c['ruling']}"
    )
    leak = result["leakage_diagnostic"]["by_timing"]
    lines.append(
        "- Leakage check (P >= 0.97 or <= 0.03 at the cut, share of events): "
        + "; ".join(f"{k} {_f(v['share'] * 100, 1)}% (n={v['n']})" for k, v in leak.items())
        + "."
    )
    cal = result["calibration"]
    lines.append(
        f"- Calibration: base rate {_f(cal['base_rate'])}, mean P {_f(cal['mean_p'])}, AUC {_f(cal['auc'])}, "
        f"Brier P {_f(cal['brier_p'], 4)} vs base-rate {_f(cal['brier_base_rate'], 4)}."
    )
    if "H_A" in result:
        a1, a3 = result["H_A"]["A1"], result["H_A"]["A3"]
        sp = a1["spread"]
        lines += [
            f"- A1: mean weekly IC {_f(a1['mean_ic'], 4)}, t {_f(a1['t'], 2)}, {a1['n_weeks']} weeks, "
            f"shuffle percentile {_f(a1['shuffle']['percentile_of_real'], 1)} (p95 {_f(a1['shuffle']['p95'], 4)}); "
            f"pooled IC {_f(a1['pooled']['ic'], 4)} (clustered t {_f(a1['pooled']['t'], 2)}).",
            f"- A1 tercile spread: gross {_f(sp.get('gross_mean_bp'), 1)} bp, net {_f(sp.get('net_primary_mean_bp'), 1)} bp "
            f"(stress {_f(sp.get('net_stress_mean_bp'), 1)} bp) per pair.",
            f"- A3: IC {_f(a3['mean_ic'], 4)}, t {_f(a3['t'], 2)}, {a3['n_weeks']} weeks; raw one-sided p "
            f"{_f(a3['p_one_sided'], 3)}, Holm {_f(a3.get('holm_p'), 3)}.",
            f"- MDE (IC): {_f(result['minimum_detectable_effect']['mean_ic'], 4)}; spread "
            f"{_f(result['minimum_detectable_effect']['spread_bp'], 1)} bp.",
        ]
        for name, blk in result["sub_periods"].items():
            lines.append(
                f"- {name}: IC {_f(blk.get('mean_ic'), 4)}, t {_f(blk.get('t'), 2)}, "
                f"{blk.get('n_weeks', 0)} weeks, {blk.get('n_events', 0)} events."
            )
        pl = result["placebos"]
        lines.append(
            f"- Placebos: P7 signal IC {_f(pl['stale_p7_signal']['mean_ic'], 4)} (t {_f(pl['stale_p7_signal']['t'], 2)}); "
            f"R+1 return IC {_f(pl['next_session_return']['mean_ic'], 4)} (t {_f(pl['next_session_return']['t'], 2)})."
        )
        cr = result["continue_rule"]
        lines.append(
            f"- Continue rule: IC>0 and t>=2 {cr['rule1_ic_positive_t_ge_2']}; net spread>0 "
            f"{cr['rule2_net_spread_positive']}; above shuffle p95 {cr['rule3_above_shuffle_p95']}; "
            f"stop rule triggered {cr['stop_rule_triggered']}."
        )
    if "robustness_excluding_extreme_p" in result:
        rb = result["robustness_excluding_extreme_p"]
        a = rb["A1"]
        lines.append(
            f"- Robustness (reference only, not in the verdict), excluding {rb['n_excluded']} extreme-P "
            f"events in {rb['flagged_timing_kinds']}: A1 IC {_f(a['mean_ic'], 4)}, t {_f(a['t'], 2)}, "
            f"{a['n_weeks']} weeks, shuffle percentile {_f(a['shuffle']['percentile_of_real'], 1)}, "
            f"net spread {_f(a['spread'].get('net_primary_mean_bp'), 1)} bp."
        )
    lines.append(f"- Overlay scoring: {result['overlay_scoring']}.")
    lines += DATA_DEFECT_NOTE
    (out_dir / "report.md").write_text("\n".join(lines) + "\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--events", type=Path, default=EVENTS_PATH)
    ap.add_argument("--out-dir", type=Path, default=ITER_DIR)
    args = ap.parse_args(argv)
    events = pd.read_parquet(args.events)
    for col in ("S", "R"):
        events[col] = pd.to_datetime(events[col])
    symbols = set(events["ticker"].dropna()) | {"SPY"}
    start = (events["S"].min() - pd.Timedelta(days=5)).date()
    end = (events["R"].max() + pd.Timedelta(days=8)).date()
    bars = load_bars(symbols, start, end)
    result = run_analysis(events, bars)
    write_outputs(result, args.out_dir)
    print(
        json.dumps(
            {"verdict": result["verdict"], "primary_events": result["sample"]["primary_events"]}
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
