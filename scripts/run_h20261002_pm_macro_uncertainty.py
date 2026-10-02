#!/usr/bin/env python3
"""h20261002_pm_macro_uncertainty: does Kalshi-implied release uncertainty scale the
equity announcement premium? (T-20261002-44)

Implements exactly hypotheses.md of the iteration (frozen, with candidate-manifest.json,
before this script was run):

  H0  descriptive announcement-day means (Welch t), no gate.
  H1  D = mean(QQQ R_cc | U_rel > 1) - mean(QQQ R_cc | U_rel <= 1) over non-FOMC release days,
      permutation p (1000 within-series shuffles of U_rel, seed 20261002), slope b with HC1 t,
      D in the anchor sample, D with R_co, FOMC days separately, D without 2022, leave-one-year-out.
      Continue rule: D >= +15 bp, p <= 0.10, D_anchor > 0.  Stop: D < +5 bp or wrong-signed.
  H2  Kalshi implied mean minus Cleveland Fed CPI nowcast (consensus proxy), CPI days only,
      hit rate of sign(gap) against sign(-TLT R_co) on |gap| >= median |gap|.
  Placebos  within-series shuffle (above), same signal on T+1, random non-release sessions
      matched by weekday and month.
  Candidates  U1-U7, G1, G2 with primary and stress costs and DSR across the 9.

Returns come from SIP daily bars in excess of BIL over the same interval.
Usage:
  scripts/run_capped.sh --mem 1.5G -- uv run python scripts/run_h20261002_pm_macro_uncertainty.py
"""

from __future__ import annotations

import json
import math
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from statistics import NormalDist
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import build_kalshi_release_uncertainty as bk  # noqa: E402

ET = ZoneInfo("America/New_York")
ITER_ID = "h20261002_pm_macro_uncertainty"
OUT_DIR = ROOT / "reports/research/iterations" / ITER_ID
RU_PATH = ROOT / "data/research/prediction_markets/kalshi/release_uncertainty.parquet"
CLEVELAND_JSON = ROOT / "data/research/prediction_markets/cleveland_fed/nowcast_month.json"
ALLOCATION_PATH = (
    ROOT / "reports/research/iterations/h20261002_program_dd30_allocation/program_returns.parquet"
)

SEED = 20261002
N_SHUFFLES = 1000
SAMPLE_END = pd.Timestamp("2026-09-17")
ANCHOR_START = pd.Timestamp("2024-01-08")
PRIMARY_SERIES = ["KXCPI", "KXPAYROLLS", "KXGDP"]
D_CONTINUE_BP = 15.0
D_STOP_BP = 5.0
P_CONTINUE = 0.10
COST_BP = {"QQQ": 2.0, "SPY": 2.0, "TLT": 2.0, "IWM": 3.0, "TQQQ": 5.0}
BORROW_ANNUAL = 0.005
SYMBOLS = ["QQQ", "SPY", "IWM", "TLT", "TQQQ", "BIL"]
H0_ASSETS = ["QQQ", "SPY", "IWM", "TLT"]

# (id, asset, rule); fill: R_cc for U*, R_co for G*.
CANDIDATES = {
    "U1": ("QQQ", "u_rel_gt_1", False),
    "U2": ("SPY", "u_rel_gt_1", False),
    "U3": ("IWM", "u_rel_gt_1", False),
    "U4": ("QQQ", "every_release_day", False),
    "U5": ("TQQQ", "u_rel_gt_1", False),
    "U6": ("QQQ", "u_rel_weight", False),
    "U7": ("QQQ", "u_rel_gt_1", True),
    "G1": ("TLT", "gap_sign", False),
    "G2": ("QQQ", "gap_sign", False),
}


# ------------------------------------------------------------------ statistics


def welch_t(a: np.ndarray, b: np.ndarray) -> dict[str, float]:
    a, b = np.asarray(a, float), np.asarray(b, float)
    if len(a) < 2 or len(b) < 2:
        return {"mean_a_bp": float("nan"), "mean_b_bp": float("nan"), "t": float("nan")}
    va, vb = a.var(ddof=1) / len(a), b.var(ddof=1) / len(b)
    t = (a.mean() - b.mean()) / math.sqrt(va + vb) if va + vb > 0 else float("nan")
    return {
        "mean_a_bp": float(a.mean() * 1e4),
        "mean_b_bp": float(b.mean() * 1e4),
        "diff_bp": float((a.mean() - b.mean()) * 1e4),
        "t": float(t),
        "n_a": int(len(a)),
        "n_b": int(len(b)),
    }


def diff_bp(frame: pd.DataFrame, ret: str, *, signal: str = "U_rel") -> float:
    """D = mean(ret | signal > 1) - mean(ret | signal <= 1) in bp (NaN when a group is empty)."""
    hi = frame.loc[frame[signal] > 1, ret]
    lo = frame.loc[frame[signal] <= 1, ret]
    if hi.empty or lo.empty:
        return float("nan")
    return float((hi.mean() - lo.mean()) * 1e4)


def hc1_slope(x: np.ndarray, y: np.ndarray) -> dict[str, float]:
    x, y = np.asarray(x, float), np.asarray(y, float)
    n = len(x)
    design = np.column_stack([np.ones(n), x])
    xtx_inv = np.linalg.inv(design.T @ design)
    beta = xtx_inv @ design.T @ y
    resid = y - design @ beta
    meat = (design * resid[:, None] ** 2).T @ design
    cov = xtx_inv @ meat @ xtx_inv * n / (n - 2)
    return {
        "a": float(beta[0]),
        "b": float(beta[1]),
        "b_bp_per_unit_log_u_rel": float(beta[1] * 1e4),
        "t_hc1": float(beta[1] / math.sqrt(cov[1, 1])),
        "n": int(n),
    }


def binom_p_one_sided(hits: int, n: int) -> float:
    """P(X >= hits) for X ~ Binomial(n, 0.5)."""
    return float(sum(math.comb(n, k) for k in range(hits, n + 1)) / 2**n)


# ----------------------------------------------------------------------- data


def load_prices() -> dict[str, pd.DataFrame]:
    import duckdb

    con = duckdb.connect()
    try:
        con.execute("SET memory_limit='400MB'")
        quoted = ",".join(f"'{s}'" for s in SYMBOLS)
        df = con.execute(
            "SELECT symbol, timestamp, open, close "
            "FROM read_parquet('data/sip/daily/**/*.parquet') "
            f"WHERE symbol IN ({quoted}) ORDER BY symbol, timestamp"
        ).fetchdf()
    finally:
        con.close()
    df["date"] = pd.to_datetime(pd.to_datetime(df["timestamp"], utc=True).dt.tz_convert(ET).dt.date)
    return {s: g.set_index("date")[["open", "close"]] for s, g in df.groupby("symbol")}


def return_table(prices: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Per session T: rcc, rco and next-session rcc (T+1), each in excess of BIL, per symbol."""
    cal = prices["SPY"].index
    out = pd.DataFrame(index=cal)
    for sym, px in prices.items():
        px = px.reindex(cal)
        prev_close = px["close"].shift(1)
        out[f"{sym}_cc"] = px["close"] / prev_close - 1.0
        out[f"{sym}_co"] = px["open"] / prev_close - 1.0
        out[f"{sym}_cc_next"] = px["close"].shift(-1) / px["close"] - 1.0
    for sym in prices:
        if sym == "BIL":
            continue
        for kind in ("cc", "co", "cc_next"):
            out[f"{sym}_{kind}_ex"] = out[f"{sym}_{kind}"] - out[f"BIL_{kind}"]
    return out


def build_event_tables(ru: pd.DataFrame, calendar: pd.DatetimeIndex) -> dict[str, pd.DataFrame]:
    ru = ru.copy()
    ru["release_date"] = pd.to_datetime(ru["release_date"])
    ok = (
        ru["U_rel"].notna()
        & ru["release_date"].notna()
        & (ru["release_date"] <= SAMPLE_END)
        & ru["release_date"].isin(calendar)
        & ~ru["diagnostic_only"].astype(bool)
    )
    valid = ru[ok]
    primary = valid[valid["series"].isin(PRIMARY_SERIES)]
    fomc = valid[valid["series"] == "KXFED"]
    full_start = primary["release_date"].min()
    primary = primary[primary["release_date"] >= full_start]
    fomc = fomc[fomc["release_date"] >= full_start]
    fomc_dates = set(pd.to_datetime(list(bk.FOMC_DECISION_DAYS))) | set(
        ru.loc[ru["series"] == "KXFED", "release_date"].dropna()
    )
    # a CPI, payrolls or GDP release on an FOMC decision day is an FOMC day (frozen choice)
    non_fomc = primary[~primary["release_date"].isin(list(fomc_dates))]
    return {
        "full_start": full_start,
        "primary_events": non_fomc,
        "primary_events_on_fomc_days": primary[primary["release_date"].isin(list(fomc_dates))],
        "fomc_events": fomc,
        "fomc_dates": fomc_dates,
    }


def day_signal(events: pd.DataFrame, rets: pd.DataFrame) -> pd.DataFrame:
    day = bk.day_level_signal(events)
    day["release_date"] = pd.to_datetime(day["release_date"])
    return day.merge(rets, left_on="release_date", right_index=True, how="left")


# -------------------------------------------------------------------------- H1


def shuffle_within_series(events: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Permute U_rel across the events of each series (never across series)."""
    shuffled = events[["series", "release_date", "U_rel"]].copy()
    for _, idx in shuffled.groupby("series").groups.items():
        shuffled.loc[idx, "U_rel"] = rng.permutation(shuffled.loc[idx, "U_rel"].to_numpy())
    return shuffled


def permuted_d(
    events: pd.DataFrame, rets: pd.DataFrame, rng: np.random.Generator, ret: str
) -> float:
    shuffled = shuffle_within_series(events, rng)
    day = bk.day_level_signal(shuffled.assign(event_ticker=""))
    day["release_date"] = pd.to_datetime(day["release_date"])
    day = day.merge(rets[[ret]], left_on="release_date", right_index=True, how="left")
    return diff_bp(day.dropna(subset=[ret]), ret)


def d_stats(day: pd.DataFrame, ret: str, *, mask: pd.Series | None = None) -> dict[str, float]:
    sub = day if mask is None else day[mask]
    sub = sub.dropna(subset=[ret, "U_rel"])
    return {
        "D_bp": diff_bp(sub, ret),
        "n_days": int(len(sub)),
        "n_hi": int((sub["U_rel"] > 1).sum()),
        "n_lo": int((sub["U_rel"] <= 1).sum()),
    }


def run_h1(tables: dict, rets: pd.DataFrame) -> tuple[dict, pd.DataFrame, np.ndarray]:
    events = tables["primary_events"]
    day = day_signal(events, rets)
    full = d_stats(day, "QQQ_cc_ex")
    anchor = d_stats(day, "QQQ_cc_ex", mask=day["release_date"] >= ANCHOR_START)
    rng = np.random.default_rng(SEED)
    perm = np.array(
        [permuted_d(events, rets, rng, "QQQ_cc_ex") for _ in range(N_SHUFFLES)], dtype=float
    )
    perm = perm[np.isfinite(perm)]
    d_real = full["D_bp"]
    p_value = float((1 + int((perm >= d_real).sum())) / (1 + len(perm)))
    sub = day.dropna(subset=["QQQ_cc_ex", "U_rel"])
    slope = hc1_slope(np.log(sub["U_rel"].to_numpy()), sub["QQQ_cc_ex"].to_numpy())
    by_year = {}
    for year in sorted(sub["release_date"].dt.year.unique()):
        by_year[int(year)] = d_stats(day, "QQQ_cc_ex", mask=day["release_date"].dt.year != year)
    loyo = [v["D_bp"] for v in by_year.values() if np.isfinite(v["D_bp"])]
    has_2022 = bool((day["release_date"].dt.year == 2022).any())
    result = {
        "primary_stat": {"asset": "QQQ", "ret": "R_cc excess BIL", **full},
        "permutation": {
            "shuffles": int(len(perm)),
            "seed": SEED,
            "p_one_sided": p_value,
            "perm_mean_bp": float(perm.mean()),
            "perm_p90_bp": float(np.percentile(perm, 90)),
            "perm_p95_bp": float(np.percentile(perm, 95)),
            "real_above_p90": bool(d_real > np.percentile(perm, 90)),
            "share_perm_below_real": float((perm < d_real).mean()),
            "p_definition": "(1 + #{D_perm >= D_real}) / (1 + shuffles), one-sided",
        },
        "slope_log_u_rel": slope,
        "anchor": anchor,
        "D_other_assets_full": {a: d_stats(day, f"{a}_cc_ex") for a in ["SPY", "IWM"]},
        "D_R_co_QQQ_full": d_stats(day, "QQQ_co_ex"),
        "D_R_co_QQQ_anchor": d_stats(day, "QQQ_co_ex", mask=day["release_date"] >= ANCHOR_START),
        "D_without_2022": (
            d_stats(day, "QQQ_cc_ex", mask=day["release_date"].dt.year != 2022)
            if has_2022
            else {"not_applicable": "full sample contains no 2022 release day", **full}
        ),
        "leave_one_year_out": {
            "D_bp_by_left_out_year": {str(k): v["D_bp"] for k, v in by_year.items()},
            "min_bp": float(min(loyo)) if loyo else None,
            "max_bp": float(max(loyo)) if loyo else None,
        },
        "by_series_events": {s: int((events["series"] == s).sum()) for s in PRIMARY_SERIES},
        "full_start": str(tables["full_start"].date()),
        "n_event_rows": int(len(events)),
        "n_release_days": int(len(day)),
    }
    fomc = tables["fomc_events"]
    fday = day_signal(fomc, rets) if len(fomc) else pd.DataFrame()
    if len(fday):
        result["fomc_only"] = {
            **d_stats(fday, "QQQ_cc_ex"),
            "anchor": d_stats(fday, "QQQ_cc_ex", mask=fday["release_date"] >= ANCHOR_START),
            "mean_cc_bp_all_fomc_events": float(fday["QQQ_cc_ex"].mean() * 1e4),
        }
    else:
        result["fomc_only"] = {"n_days": 0}
    rule = {
        "rule": (
            "D >= +15 bp and permutation p <= 0.10 (full sample) and D > 0 in the anchor sample"
        ),
        "D_bp": d_real,
        "D_ge_15": bool(d_real >= D_CONTINUE_BP),
        "p_value": p_value,
        "p_le_0_10": bool(p_value <= P_CONTINUE),
        "D_anchor_bp": anchor["D_bp"],
        "D_anchor_gt_0": bool(anchor["D_bp"] > 0),
    }
    rule["continue"] = bool(rule["D_ge_15"] and rule["p_le_0_10"] and rule["D_anchor_gt_0"])
    rule["stop_refuted"] = bool((not np.isfinite(d_real)) or d_real < D_STOP_BP)
    rule["verdict"] = (
        "continue" if rule["continue"] else ("refuted" if rule["stop_refuted"] else "inconclusive")
    )
    result["continue_rule"] = rule
    return result, day, perm


# ---------------------------------------------------------------------- H0


def run_h0(tables: dict, rets: pd.DataFrame, ru: pd.DataFrame) -> dict:
    start = tables["full_start"]
    sessions = rets.loc[(rets.index >= start) & (rets.index <= SAMPLE_END)]
    all_events = ru[
        ru["release_date"].notna()
        & ~ru["diagnostic_only"].astype(bool)
        & (pd.to_datetime(ru["release_date"]) >= start)
        & (pd.to_datetime(ru["release_date"]) <= SAMPLE_END)
    ].copy()
    all_events["release_date"] = pd.to_datetime(all_events["release_date"])
    release_days_all = set(all_events["release_date"])
    sets = {"pooled_all": release_days_all}
    for series in [*PRIMARY_SERIES, "KXFED"]:
        sets[series] = set(all_events.loc[all_events["series"] == series, "release_date"])
    sets["pooled_non_fomc"] = set(
        all_events.loc[all_events["series"].isin(PRIMARY_SERIES), "release_date"]
    )
    out: dict[str, dict] = {}
    for name, days in sets.items():
        mask = sessions.index.isin(list(days))
        other = ~sessions.index.isin(list(release_days_all))
        out[name] = {
            "n_release_days": int(mask.sum()),
            "n_other_sessions": int(other.sum()),
            **{
                asset: welch_t(
                    sessions.loc[mask, f"{asset}_cc_ex"].dropna().to_numpy(),
                    sessions.loc[other, f"{asset}_cc_ex"].dropna().to_numpy(),
                )
                for asset in H0_ASSETS
            },
        }
    return {"window": [str(start.date()), str(SAMPLE_END.date())], "tables": out}


# ------------------------------------------------------------------- placebos


def placebo_t_plus_1(day: pd.DataFrame) -> dict:
    return {
        "D_bp_full": d_stats(day, "QQQ_cc_next_ex")["D_bp"],
        "D_bp_anchor": d_stats(day, "QQQ_cc_next_ex", mask=day["release_date"] >= ANCHOR_START)[
            "D_bp"
        ],
        "n_days": int(day["QQQ_cc_next_ex"].notna().sum()),
    }


def placebo_random_sessions(
    day: pd.DataFrame, rets: pd.DataFrame, tables: dict, d_real: float
) -> dict:
    rng = np.random.default_rng(SEED + 3)
    release_all = set(day["release_date"]) | set(tables["fomc_events"]["release_date"])
    sessions = rets.loc[(rets.index >= tables["full_start"]) & (rets.index <= SAMPLE_END)]
    pool = sessions[~sessions.index.isin(list(release_all))]
    by_key = {
        k: g.index.to_numpy() for k, g in pool.groupby([pool.index.weekday, pool.index.month])
    }
    u_emp = day["U_rel"].to_numpy()
    ds = []
    for _ in range(N_SHUFFLES):
        picks, signal = [], []
        for d in day["release_date"]:
            cands = by_key.get((d.weekday(), d.month))
            if cands is None or len(cands) == 0:
                continue
            picks.append(rng.choice(cands))
            signal.append(rng.choice(u_emp))
        frame = pd.DataFrame({"U_rel": signal, "r": sessions.loc[picks, "QQQ_cc_ex"].to_numpy()})
        ds.append(diff_bp(frame.dropna(), "r"))
    arr = np.array([d for d in ds if np.isfinite(d)])
    return {
        "draws": int(len(arr)),
        "mean_D_bp": float(arr.mean()),
        "sd_D_bp": float(arr.std(ddof=1)),
        "p05_bp": float(np.percentile(arr, 5)),
        "p95_bp": float(np.percentile(arr, 95)),
        "share_ge_real": float((arr >= d_real).mean()),
    }


# ------------------------------------------------------------------------- H2


def load_cleveland_nowcast(path: Path = CLEVELAND_JSON) -> dict[str, pd.Series]:
    """Daily headline-CPI nowcast per target month: {'YYYY-M': Series(date -> value)}."""
    payload = json.loads(path.read_text())
    out: dict[str, pd.Series] = {}
    for chart in payload:
        target = chart["chart"]["subcaption"]
        year, month = (int(x) for x in target.split("-"))
        labels = [c["label"] for c in chart["categories"][0]["category"]]
        series = next(d for d in chart["dataset"] if d["seriesname"] == "CPI Inflation")
        stamps, values = [], []
        cur_year, last_month = year, month
        for label, point in zip(labels, series["data"], strict=False):
            try:
                m, d = (int(x) for x in label.split("/"))
            except ValueError:  # non-date category labels such as "PCE Jul"
                continue
            if m < last_month:
                cur_year += 1
            last_month = m
            if point.get("value", "") == "":
                continue
            stamps.append(pd.Timestamp(date(cur_year, m, d)))
            values.append(float(point["value"]))
        out[target] = pd.Series(values, index=pd.DatetimeIndex(stamps)).sort_index()
    return out


MONTHS = {m: i + 1 for i, m in enumerate("JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split())}


def event_target_month(ticker: str) -> str | None:
    """'KXCPI-26JUL' / 'CPI-23DEC' -> '2026-7' / '2023-12' (reference month of the CPI)."""
    tail = ticker.split("-")[-1]
    if len(tail) != 5 or tail[2:] not in MONTHS:
        return None
    return f"{2000 + int(tail[:2])}-{MONTHS[tail[2:]]}"


def build_gap_table(ru: pd.DataFrame, rets: pd.DataFrame, nowcasts: dict, calendar) -> pd.DataFrame:
    cpi = ru[
        (ru["series"] == "KXCPI")
        & ru["pmf_mean"].notna()
        & ru["release_date"].notna()
        & ~ru["excluded"].astype(bool)
    ].copy()
    cpi["release_date"] = pd.to_datetime(cpi["release_date"])
    cpi = cpi[(cpi["release_date"] <= SAMPLE_END) & cpi["release_date"].isin(calendar)]
    rows = []
    for _, ev in cpi.iterrows():
        target = event_target_month(ev["event_ticker"])
        series = nowcasts.get(target)
        if series is None:
            continue
        known = series[series.index <= ev["release_date"] - pd.Timedelta(days=1)]
        if known.empty:
            continue
        rows.append(
            {
                "event_ticker": ev["event_ticker"],
                "release_date": ev["release_date"],
                "kalshi_mean": float(ev["pmf_mean"]),
                "nowcast": float(known.iloc[-1]),
                "nowcast_date": known.index[-1],
            }
        )
    gap = pd.DataFrame(rows)
    if gap.empty:
        return gap
    gap["gap"] = gap["kalshi_mean"] - gap["nowcast"]
    return gap.merge(rets, left_on="release_date", right_index=True, how="left")


def run_h2(gap: pd.DataFrame) -> dict:
    if gap.empty:
        return {"status": "no_events"}
    use = gap.dropna(subset=["TLT_co_ex", "gap"])
    cutoff = float(use["gap"].abs().median())
    big = use[use["gap"].abs() >= cutoff]

    def hits(frame: pd.DataFrame) -> dict:
        hit = (np.sign(frame["gap"]) == np.sign(-frame["TLT_co_ex"])) & (frame["gap"] != 0)
        n = int(len(frame))
        h = int(hit.sum())
        return {
            "n": n,
            "hits": h,
            "hit_rate": float(h / n) if n else float("nan"),
            "binom_p_one_sided": binom_p_one_sided(h, n) if n else float("nan"),
        }

    pooled = hits(big)
    anchor = hits(big[big["release_date"] >= ANCHOR_START])
    rule = {
        "scope": "CPI days only (no free payrolls consensus history exists)",
        "abs_gap_median": cutoff,
        "pooled": pooled,
        "anchor": anchor,
        "hit_rate_ge_0_60": bool(pooled["hit_rate"] >= 0.60),
        "binom_p_le_0_10": bool(pooled["binom_p_one_sided"] <= 0.10),
        "anchor_same_direction": bool(anchor["hit_rate"] > 0.5),
    }
    rule["continue"] = bool(
        rule["hit_rate_ge_0_60"] and rule["binom_p_le_0_10"] and rule["anchor_same_direction"]
    )
    return {
        "status": "run",
        "n_cpi_events_with_gap": int(len(use)),
        "all_events_hit_rate": hits(use),
        "mean_gap": float(use["gap"].mean()),
        "continue_rule": rule,
    }


# ----------------------------------------------------------------- candidates


def candidate_returns(
    cid: str, day_all: pd.DataFrame, day_non_fomc: pd.DataFrame, gap: pd.DataFrame, cost_mult: float
) -> pd.DataFrame:
    asset, rule, with_fomc = CANDIDATES[cid]
    cost = 2 * COST_BP[asset] * cost_mult / 1e4  # entry MOC T-1 and exit T: two sides
    if rule == "gap_sign":
        use = gap.dropna(subset=[f"{asset}_co_ex", "gap"]).copy()
        use["w"] = -np.sign(use["gap"])  # hotter than consensus -> short
        gross = use["w"] * use[f"{asset}_co_ex"]
        borrow = np.where(use["w"] < 0, BORROW_ANNUAL / 252.0, 0.0)
        use["net"] = gross - cost * use["w"].abs() - borrow
        use["gross"] = gross
        return use[["release_date", "w", "gross", "net"]].rename(columns={"release_date": "date"})
    src = day_all if with_fomc else day_non_fomc
    use = src.dropna(subset=[f"{asset}_cc_ex", "U_rel"]).copy()
    if rule == "u_rel_gt_1":
        use["w"] = (use["U_rel"] > 1).astype(float)
    elif rule == "every_release_day":
        use["w"] = 1.0
    else:  # u_rel_weight
        use["w"] = np.minimum(use["U_rel"], 2.0) / 2.0
    use = use[use["w"] > 0]
    use["gross"] = use["w"] * use[f"{asset}_cc_ex"]
    use["net"] = use["gross"] - cost * use["w"]
    return use[["release_date", "w", "gross", "net"]].rename(columns={"release_date": "date"})


def candidate_stats(trades: pd.DataFrame, sessions: pd.DatetimeIndex, trial_count: int) -> dict:
    from open_composer.research.campaign_statistics import deflated_sharpe_probability

    if trades.empty:
        return {"n_events": 0}
    net = trades["net"].to_numpy()
    n = len(net)
    sd = net.std(ddof=1) if n > 1 else float("nan")
    daily = pd.Series(0.0, index=sessions)
    daily.loc[trades["date"].to_numpy()] = net
    try:
        dsr = deflated_sharpe_probability(daily.to_numpy(), trial_count=trial_count, hac_lag=5)
    except ValueError:
        dsr = None
    sd_daily = daily.std(ddof=1)
    return {
        "n_events": int(n),
        "mean_net_bp_per_event": float(net.mean() * 1e4),
        "mean_gross_bp_per_event": float(trades["gross"].mean() * 1e4),
        "t_per_event": float(net.mean() / sd * math.sqrt(n)) if sd and sd > 0 else None,
        "hit_rate": float((net > 0).mean()),
        "annualized_return_on_days_invested": float(net.mean() * 252.0),
        "share_of_sessions_invested": float(n / len(sessions)),
        "sharpe_full_session_series": (
            float(daily.mean() / sd_daily * math.sqrt(252.0)) if sd_daily > 0 else None
        ),
        "dsr_across_9": dsr,
    }


def run_candidates(
    tables: dict,
    rets: pd.DataFrame,
    gap: pd.DataFrame,
    h1_continue: bool,
    h2_run: bool,
    h2_continue: bool,
) -> dict:
    day_non_fomc = day_signal(tables["primary_events"], rets)
    all_events = pd.concat(
        [tables["primary_events"], tables["primary_events_on_fomc_days"], tables["fomc_events"]]
    )
    day_all = day_signal(all_events, rets)
    sessions = rets.loc[(rets.index >= tables["full_start"]) & (rets.index <= SAMPLE_END)].index
    out = {}
    for cid, (asset, rule, _with_fomc) in CANDIDATES.items():
        is_g = rule == "gap_sign"
        entry: dict = {"asset": asset, "rule": rule}
        if is_g and not h2_run:
            entry["status"] = "not_run"
            out[cid] = entry
            continue
        for label, mult in (("primary", 1.0), ("stress", 2.0)):
            trades = candidate_returns(cid, day_all, day_non_fomc, gap, mult)
            entry[label] = candidate_stats(trades, sessions, 9)
            if label == "primary":
                entry["anchor"] = candidate_stats(
                    trades[trades["date"] >= ANCHOR_START], sessions[sessions >= ANCHOR_START], 9
                )
        eligible = h2_continue if is_g else h1_continue
        entry["decision_eligible"] = bool(eligible)
        entry["not_decision_eligible_reason"] = (
            None
            if eligible
            else ("h2_continue_rule_not_passed" if is_g else "h1_continue_rule_not_passed")
        )
        out[cid] = entry
    return out


# ------------------------------------------------------------------------ main


def main() -> int:
    if not RU_PATH.exists():
        raise SystemExit(f"missing {RU_PATH}; run scripts/build_kalshi_release_uncertainty.py")
    ru = pd.read_parquet(RU_PATH)
    ru["release_date"] = pd.to_datetime(ru["release_date"])
    prices = load_prices()
    rets = return_table(prices)
    tables = build_event_tables(ru, rets.index)

    h1, day, perm = run_h1(tables, rets)
    h0 = run_h0(tables, rets, ru)
    d_real = h1["primary_stat"]["D_bp"]
    placebos = {
        "within_series_shuffle": {
            "perm_p90_bp": h1["permutation"]["perm_p90_bp"],
            "real_D_bp": d_real,
            "real_above_p90": h1["permutation"]["real_above_p90"],
        },
        "t_plus_1_session": placebo_t_plus_1(day),
        "random_sessions_matched_weekday_month": placebo_random_sessions(day, rets, tables, d_real),
    }

    if CLEVELAND_JSON.exists():
        gap = build_gap_table(ru, rets, load_cleveland_nowcast(), rets.index)
        gap = gap[gap["release_date"] >= tables["full_start"]] if len(gap) else gap  # full window
        h2 = run_h2(gap)
    else:
        gap = pd.DataFrame()
        h2 = {"status": "blocked_data", "reason": f"{CLEVELAND_JSON} missing"}
    h2_run = h2.get("status") == "run"
    h2_continue = bool(h2_run and h2["continue_rule"]["continue"])
    h1_continue = h1["continue_rule"]["continue"]

    cands = run_candidates(tables, rets, gap, h1_continue, h2_run, h2_continue)

    if not h1_continue:
        overlay = "not_scored_h1_continue_rule_failed"
    elif not ALLOCATION_PATH.exists():
        overlay = "pending_allocation"
    else:
        overlay = "allocation_file_present_scoring_requires_lead_schema"

    results = {
        "iter_id": ITER_ID,
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "sample": {
            "full": [str(tables["full_start"].date()), str(SAMPLE_END.date())],
            "anchor": [str(ANCHOR_START.date()), str(SAMPLE_END.date())],
            "n_calendar_sessions": int(
                ((rets.index >= tables["full_start"]) & (rets.index <= SAMPLE_END)).sum()
            ),
        },
        "H0": h0,
        "H1": h1,
        "placebos": placebos,
        "H2": h2,
        "continue_rule": {
            "H1": h1["continue_rule"],
            "H2": h2.get("continue_rule", {"continue": False, "status": h2.get("status")}),
        },
        "candidates": cands,
        "overlay_scoring": overlay,
        "workflow_pass": True,
        "research_pass": bool(h1_continue),
        "llm_contribution_pass": False,
        "paper_ready_pass": False,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "results.json").write_text(json.dumps(results, indent=2, default=_json_default))
    ledger = [
        json.dumps(
            {"candidate_id": cid, "hypothesis": "H2" if v.get("rule") == "gap_sign" else "H1", **v},
            default=_json_default,
        )
        for cid, v in cands.items()
    ]
    (OUT_DIR / "trial-ledger.jsonl").write_text("\n".join(ledger) + "\n")
    print(
        json.dumps(
            {"H1_verdict": h1["continue_rule"], "H2": h2.get("status")}, default=_json_default
        )
    )
    return 0


def _json_default(obj):
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return None if not np.isfinite(obj) else float(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, (pd.Timestamp, datetime, date)):
        return str(obj)
    raise TypeError(type(obj))


_NORMAL = NormalDist()

if __name__ == "__main__":
    sys.exit(main())
