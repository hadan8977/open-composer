# ruff: noqa: E501
"""T-20261007-06 cost measurement: SIP NBBO half spreads at the fill times of groups G1-G3.

Method frozen in hypotheses.md section 0 (before any backtest): 40 random full NYSE sessions in
2024-01-08..2026-09-15 (seed 20261007); per session the symbols are the G1 top-20 pool in force, the
LETF6 stocks, the 15 ETFs of G3, and 20 random stocks from each of the rank buckets 21-100, 101-250,
251-500; half spread (bp) of the last valid quote in [T-60 s, T) at 09:35, 09:45, 12:00, 15:30, 15:45,
15:55 ET (reused fetcher of the D4 cost model). Credentials stay inside DataSession; nothing is printed.
Resumable: results per (day) under data/research/t0706_quotes/result.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import t0706_grid as G  # noqa: E402

from open_composer.research.equity_book.costs import quote_half_spread_bp  # noqa: E402
from scripts import run_t20260930_15_quote_check as qc  # noqa: E402
from scripts.sample_equity_book_spreads import is_early_close  # noqa: E402

OUT = ROOT / "data/research/t0706_quotes"
RES = OUT / "result"
SEED = 20261007
N_DAYS = 40
TIMES = [(9, 35), (9, 45), (12, 0), (15, 30), (15, 45), (15, 55)]
WINDOW_S = 60
PER_BUCKET = 20


def pick_days() -> list[str]:
    d = pd.read_parquet(ROOT / "data/features/t15_minute/SPY.parquet", columns=["date"])["date"]
    days = sorted({x.strftime("%Y-%m-%d") for x in d.unique()})
    days = [
        x
        for x in days
        if G.RECENT_START <= pd.Timestamp(x) <= G.DATA_END
        and not is_early_close(date.fromisoformat(x))
    ]
    rng = np.random.default_rng(SEED)
    return sorted(rng.choice(np.asarray(days), N_DAYS, replace=False).tolist())


def plan_day(day: str, rng: np.random.Generator) -> pd.DataFrame:
    ts = pd.Timestamp(day)
    u = G.universe_table()
    py, pm = (ts.year, ts.month - 1) if ts.month > 1 else (ts.year - 1, 12)
    snap = u[(u["month_end"].dt.year == py) & (u["month_end"].dt.month == pm)]
    rows = []
    for s in snap.loc[snap["rank_dedup"] <= 20, "symbol"]:
        rows.append((s, "top20"))
    for s in G.LETF6:
        rows.append((s, "letf6"))
    for s in G.ETF15:
        rows.append((s, "etf"))
    for lo, hi, name in ((21, 100, "r21_100"), (101, 250, "r101_250"), (251, 500, "r251_500")):
        pool = snap.loc[
            (snap["rank_in_pool"] >= lo) & (snap["rank_in_pool"] <= hi), "symbol"
        ].tolist()
        for s in rng.choice(pool, min(PER_BUCKET, len(pool)), replace=False):
            rows.append((str(s), name))
    df = pd.DataFrame(rows, columns=["symbol", "bucket"])
    # a symbol can sit in several buckets (letf6 inside top20): keep every label, fetch once
    return df


def fetch_all() -> None:
    from scripts.run_t20260930_11_gap_fade_auction import DataSession

    qc.QUOTE_CACHE = OUT / "raw_last"
    RES.mkdir(parents=True, exist_ok=True)
    session = DataSession()
    rng = np.random.default_rng(SEED + 1)
    t0 = time.time()
    for i, day in enumerate(pick_days()):
        path = RES / f"{day}.parquet"
        plan = plan_day(day, rng)
        if path.exists():
            continue
        syms = sorted(set(plan["symbol"]))
        out = []
        for hh, mm in TIMES:
            parts = []
            for j in range(0, len(syms), qc.BATCH):
                parts.append(
                    qc.fetch_last_quotes_batch(
                        session, day, hh, mm, syms[j : j + qc.BATCH], WINDOW_S
                    )
                )
            df = pd.concat(parts, ignore_index=True)
            df["hs_bp"] = quote_half_spread_bp(df["bid"].to_numpy(), df["ask"].to_numpy())
            df["mid"] = (df["bid"] + df["ask"]) / 2.0
            df["t"] = f"{hh:02d}{mm:02d}"
            out.append(df[["symbol", "t", "hs_bp", "mid"]])
        res = pd.concat(out, ignore_index=True).merge(plan, on="symbol")
        res.insert(0, "day", day)
        tmp = path.with_suffix(".tmp")
        res.to_parquet(tmp, index=False)
        tmp.replace(path)
        print(
            json.dumps(
                {
                    "day": day,
                    "n": len(res),
                    "i": i + 1,
                    "sec": round(time.time() - t0),
                    "calls": session.calls,
                    "n429": session.n429,
                }
            ),
            flush=True,
        )


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "days":
        print(pick_days())
    else:
        fetch_all()
