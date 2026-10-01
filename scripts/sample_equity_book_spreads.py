"""D4 quote sampler: Alpaca SIP NBBO half spreads for the equity-book cost model.

Plan: 60 random NYSE sessions (stratified, ~7 per year 2018-2025, 4 in 2026; seed 20261001)
x 10 liquidity deciles x 30 random U3000 symbols per decile, three snapshots per session
(ET): ``open`` = median half spread of every valid quote in 09:35:00-09:45:00, ``mid`` = last
valid quote before 12:00:00 within 60 s, ``close`` = last valid quote before 15:45:00 within
60 s.  The valid-quote rule (bid > 0, ask > bid), the 100-symbol-style batching and the
paged, rate-paced, 429-backoff fetch are reused from ``run_t20260930_15_quote_check.py``.

The half spread in bp, ``(ask - bid) / 2 / mid * 1e4``, is scale free: raw (as printed)
quotes give the same number as split-adjusted ones, so the price rescaling of the quote
check is not needed here.

Credentials come from ``DataSession`` (``.env`` via load_dotenv) and live only in request
headers; nothing here prints, logs or stores them.

Resumable: every (day, decile) result is a parquet under ``data/research/equity_book/quotes/
result/``; last-quote responses are cached by the reused fetcher under ``.../raw_last/``;
open-window aggregates (not the 10^5..10^6 raw quotes) under ``.../open_window/``.

    scripts/run_capped.sh --mem 1.8G -- uv run python scripts/sample_equity_book_spreads.py plan
    scripts/run_capped.sh --mem 1.8G -- uv run python scripts/sample_equity_book_spreads.py fetch
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import polars as pl  # noqa: E402

from open_composer.research.equity_book.costs import quote_half_spread_bp  # noqa: E402
from scripts import run_t20260930_15_quote_check as qc  # noqa: E402

OUT = ROOT / "data" / "research" / "equity_book" / "quotes"
PLAN_PATH = OUT / "plan.parquet"
RESULT_DIR = OUT / "result"
OPEN_DIR = OUT / "open_window"
RAW_LAST_DIR = OUT / "raw_last"
SEED = 20261001
PER_YEAR = 7
LAST_YEAR_N = 4
N_DECILES = 10
PER_DECILE = 30
DAY_START = "2018-01-03"
DAY_END = "2026-09-17"
OPEN_START = (9, 35)
OPEN_END = (9, 45)
MID_T = (12, 0)
CLOSE_T = (15, 45)
LAST_WINDOW_S = 60
OPEN_PAGE_CAP = 400
FEATURES = ROOT / "data" / "features"
ASSET_METADATA = FEATURES / "universe" / "_asset_metadata.parquet"


# --------------------------------------------------------------------------
# plan (pure parts unit tested)
# --------------------------------------------------------------------------


def is_early_close(d: date) -> bool:
    """NYSE 13:00 closes (no 15:45 quote): Friday after Thanksgiving, Dec 24, Jul 3."""
    if d.month == 12 and d.day == 24:
        return True
    if d.month == 7 and d.day == 3:
        return True
    if d.month == 11 and d.weekday() == 4:  # fourth Thursday + 1 day
        thursdays = [x for x in range(1, 31) if date(d.year, 11, x).weekday() == 3]
        return d.day == thursdays[3] + 1
    return False


def pick_days(trading_days: list[str], seed: int = SEED) -> list[str]:
    """Stratified random sessions: ``PER_YEAR`` per year 2018-2025 and ``LAST_YEAR_N`` in 2026,
    early-close sessions and sessions outside [DAY_START, DAY_END] excluded.  Returns the
    sample in a seeded random order (so a partial run still spans the years)."""
    rng = np.random.default_rng(seed)
    days = sorted(
        d
        for d in {str(x)[:10] for x in trading_days}
        if DAY_START <= d <= DAY_END and not is_early_close(date.fromisoformat(d))
    )
    picked: list[str] = []
    for year in sorted({d[:4] for d in days}):
        pool = [d for d in days if d[:4] == year]
        n = LAST_YEAR_N if year == DAY_END[:4] else PER_YEAR
        picked.extend(rng.choice(np.asarray(pool), min(n, len(pool)), replace=False).tolist())
    order = rng.permutation(len(picked))
    return [picked[i] for i in order]


def assign_deciles(adv_rank: pd.Series, n_deciles: int = N_DECILES) -> pd.Series:
    """Equal-count liquidity deciles (0 = most liquid) by ``adv_rank`` order."""
    order = adv_rank.rank(method="first").to_numpy() - 1.0
    return pd.Series(np.floor(order * n_deciles / len(adv_rank)).astype(int), index=adv_rank.index)


def draw_symbols(pool: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """``PER_DECILE`` random symbols per decile from the pool (needs adv_rank, symbol)."""
    pool = pool.sort_values("adv_rank").reset_index(drop=True)
    pool["decile"] = assign_deciles(pool["adv_rank"])
    parts = []
    for _, g in pool.groupby("decile"):
        idx = rng.choice(len(g), min(PER_DECILE, len(g)), replace=False)
        parts.append(g.iloc[np.sort(idx)])
    return pd.concat(parts, ignore_index=True)


def build_plan() -> pd.DataFrame:
    OUT.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED + 1)
    years = range(2018, 2027)
    cols = [
        "symbol",
        "trade_date",
        "close",
        "dollar_adv_21",
        "vol_21",
        "ret_252",
        "idio_vol_63",
    ]
    tdays = (
        pl.concat(
            [
                pl.scan_parquet(FEATURES / "daily_broad" / f"{y}.parquet")
                .select("trade_date")
                .unique()
                .collect()
                for y in years
            ]
        )["trade_date"]
        .unique()
        .sort()
        .to_list()
    )
    tdays = [pd.Timestamp(t) for t in tdays]
    tday_str = [t.strftime("%Y-%m-%d") for t in tdays]
    days = pick_days(tday_str)
    meta = pd.read_parquet(ASSET_METADATA, columns=["symbol", "is_probable_fund_or_etf"])
    fund = set(meta.loc[meta["is_probable_fund_or_etf"].fillna(False), "symbol"])
    uni = pd.concat(
        [pd.read_parquet(FEATURES / "universe_broad" / f"{y}.parquet") for y in range(2017, 2027)]
    )
    uni["month_end"] = pd.to_datetime(uni["month_end"])
    rows = []
    for day in days:
        i = tday_str.index(day)
        prior = tdays[i - 1]
        me = uni.loc[uni["month_end"] <= prior, "month_end"].max()
        u = uni[(uni["month_end"] == me) & (uni["adv_rank"] <= 3000) & (uni["close"] >= 5.0)]
        u = u[~u["symbol"].isin(fund)]
        f = (
            pl.scan_parquet(FEATURES / "daily_broad" / f"{prior.year}.parquet")
            .filter(pl.col("trade_date") == prior.to_pydatetime())
            .select(cols)
            .collect()
            .to_pandas()
        )
        f = f.dropna(subset=["close", "dollar_adv_21", "vol_21", "ret_252"])
        f = f[(f["vol_21"] > 0) & (f["dollar_adv_21"] > 0)]
        pool = u[["symbol", "adv_rank"]].merge(f, on="symbol", how="inner")
        drawn = draw_symbols(pool, rng)
        drawn["day"] = day
        drawn["prior_session"] = prior.strftime("%Y-%m-%d")
        drawn["universe_month_end"] = me.strftime("%Y-%m-%d")
        drawn["pool_size"] = len(pool)
        rows.append(drawn)
    plan = pd.concat(rows, ignore_index=True).rename(columns={"close": "price"})
    plan = plan.drop(columns=["trade_date"])
    plan.to_parquet(PLAN_PATH, index=False)
    return plan


# --------------------------------------------------------------------------
# open window: every valid quote in [09:35, 09:45)
# --------------------------------------------------------------------------


def weighted_median(values: np.ndarray, weights: np.ndarray) -> float:
    ok = np.isfinite(values) & np.isfinite(weights) & (weights > 0)
    if not ok.any():
        return float("nan")
    v, w = values[ok], weights[ok]
    o = np.argsort(v, kind="stable")
    cw = np.cumsum(w[o])
    return float(v[o][np.searchsorted(cw, 0.5 * cw[-1])])


def window_stats(t_ns: np.ndarray, bid: np.ndarray, ask: np.ndarray, end_ns: int) -> dict:
    """Per-symbol aggregates of the valid quotes of one window: the median half spread over
    quotes (the cost-model target), the time-weighted median (sensitivity), p25/p75, count,
    median mid.  Time weights = seconds until the next valid quote (last: window end)."""
    hs = quote_half_spread_bp(bid, ask)
    ok = np.isfinite(hs)
    if not ok.any():
        return {
            "n_valid": 0,
            "n_all": int(len(t_ns)),
            "hs_med_bp": np.nan,
            "hs_tw_med_bp": np.nan,
            "hs_p25_bp": np.nan,
            "hs_p75_bp": np.nan,
            "mid_med": np.nan,
        }
    t, h = t_ns[ok], hs[ok]
    mid = ((bid + ask) / 2.0)[ok]
    o = np.argsort(t, kind="stable")
    t, h, mid = t[o], h[o], mid[o]
    dur = np.diff(np.append(t, end_ns)).astype("float64") / 1e9
    return {
        "n_valid": int(ok.sum()),
        "n_all": int(len(t_ns)),
        "hs_med_bp": float(np.median(h)),
        "hs_tw_med_bp": weighted_median(h, dur),
        "hs_p25_bp": float(np.quantile(h, 0.25)),
        "hs_p75_bp": float(np.quantile(h, 0.75)),
        "mid_med": float(np.median(mid)),
    }


def fetch_open_window(session: Any, day: str, symbols: list[str]) -> pd.DataFrame:
    """Window aggregates for one batch; cached as parquet (resumable)."""
    h = hashlib.md5(",".join(symbols).encode()).hexdigest()[:10]
    path = OPEN_DIR / f"{day}_{h}.parquet"
    if path.exists():
        return pd.read_parquet(path)
    start_ns = qc.et_to_utc_ns(day, *OPEN_START)
    end_ns = qc.et_to_utc_ns(day, *OPEN_END)
    params: dict[str, Any] = {
        "symbols": ",".join(symbols),
        "start": qc.rfc3339(start_ns),
        "end": qc.rfc3339(end_ns),
        "feed": "sip",
        "limit": qc.LIMIT,
    }
    acc: dict[str, list[tuple[np.ndarray, np.ndarray, np.ndarray]]] = {s: [] for s in symbols}
    token = None
    for _ in range(OPEN_PAGE_CAP):
        if token:
            params["page_token"] = token
        data = session.get_url(qc.QUOTES_URL, params)
        for sym, qs in (data.get("quotes") or {}).items():
            if not qs:
                continue
            t = qc.quote_times_ns([q["t"] for q in qs])
            bid = np.array([q.get("bp", np.nan) for q in qs], dtype="float64")
            ask = np.array([q.get("ap", np.nan) for q in qs], dtype="float64")
            keep = (t >= start_ns) & (t < end_ns)
            acc.setdefault(sym, []).append((t[keep], bid[keep], ask[keep]))
        token = data.get("next_page_token")
        if not token:
            break
    else:
        raise RuntimeError(f"open window page cap hit for {day}")
    rows = []
    for s in symbols:
        parts = acc.get(s) or []
        if parts:
            t = np.concatenate([p[0] for p in parts])
            b = np.concatenate([p[1] for p in parts])
            a = np.concatenate([p[2] for p in parts])
        else:
            t, b, a = np.array([], "int64"), np.array([]), np.array([])
        rows.append({"symbol": s, **window_stats(t, b, a, end_ns)})
    df = pd.DataFrame(rows)
    OPEN_DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    df.to_parquet(tmp, index=False)
    tmp.replace(path)
    return df


def last_quote_snapshot(
    session: Any, day: str, t: tuple[int, int], symbols: list[str]
) -> pd.DataFrame:
    """Half spread (bp) of the last valid quote in [T - 60 s, T) per symbol."""
    df = qc.fetch_last_quotes_batch(session, day, t[0], t[1], symbols, LAST_WINDOW_S)
    out = pd.DataFrame({"symbol": df["symbol"]})
    out["hs_bp"] = quote_half_spread_bp(df["bid"].to_numpy(), df["ask"].to_numpy())
    out["mid"] = (df["bid"].to_numpy() + df["ask"].to_numpy()) / 2.0
    return out


def run_one(session: Any, day: str, decile: int, symbols: list[str]) -> pd.DataFrame:
    op = fetch_open_window(session, day, symbols)
    mid = last_quote_snapshot(session, day, MID_T, symbols)
    cl = last_quote_snapshot(session, day, CLOSE_T, symbols)
    res = op.rename(columns={c: f"open_{c}" for c in op.columns if c != "symbol"})
    res = res.merge(
        mid.rename(columns={"hs_bp": "mid_hs_bp", "mid": "mid_mid"}), on="symbol", how="left"
    )
    res = res.merge(
        cl.rename(columns={"hs_bp": "close_hs_bp", "mid": "close_mid"}), on="symbol", how="left"
    )
    res.insert(0, "day", day)
    res.insert(1, "decile", decile)
    return res


def fetch_all(max_days: int | None = None) -> None:
    from scripts.run_t20260930_11_gap_fade_auction import DataSession

    plan = pd.read_parquet(PLAN_PATH)
    qc.QUOTE_CACHE = RAW_LAST_DIR  # raw last-quote responses cached under the equity_book dir
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    session = DataSession()
    days = list(dict.fromkeys(plan["day"]))
    if max_days:
        days = days[:max_days]
    t0 = time.time()
    for di, day in enumerate(days):
        for decile, g in plan[plan["day"] == day].groupby("decile"):
            path = RESULT_DIR / f"{day}_{int(decile):02d}.parquet"
            if path.exists():
                continue
            syms = sorted(g["symbol"])
            t1 = time.time()
            res = run_one(session, day, int(decile), syms)
            tmp = path.with_suffix(".tmp")
            res.to_parquet(tmp, index=False)
            tmp.replace(path)
            print(
                json.dumps(
                    {
                        "day": day,
                        "decile": int(decile),
                        "sec": round(time.time() - t1, 1),
                        "open_ok": int(res["open_n_valid"].gt(0).sum()),
                        "calls": session.calls,
                        "n429": session.n429,
                    }
                ),
                flush=True,
            )
        print(f"day {di + 1}/{len(days)} {day} done, elapsed {time.time() - t0:.0f}s", flush=True)


def load_results() -> pd.DataFrame:
    parts = [pd.read_parquet(p) for p in sorted(RESULT_DIR.glob("*.parquet"))]
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "plan":
        plan = build_plan()
        print(f"plan rows {len(plan)}, days {plan['day'].nunique()}")
        return 0
    if cmd == "fetch":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else None
        fetch_all(n)
        return 0
    print("usage: plan | fetch [max_days]")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
