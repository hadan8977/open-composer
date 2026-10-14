# ruff: noqa: E501
"""T-20261007-06 frozen grids and point-in-time pools (shared by registration and runners).

Every variant below is a counted trial. Do not edit after the pre-backtest validation stamp.
"""

from __future__ import annotations

from functools import lru_cache
from itertools import product
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RECENT_START = pd.Timestamp("2024-01-08")
DATA_END = pd.Timestamp("2026-09-15")  # nothing after this date is read
V4_START = pd.Timestamp("2017-10-02")
V4_END = pd.Timestamp("2023-08-31")

ETF14 = [
    "SPY",
    "QQQ",
    "IWM",
    "XLB",
    "XLC",
    "XLE",
    "XLF",
    "XLI",
    "XLK",
    "XLP",
    "XLRE",
    "XLU",
    "XLV",
    "XLY",
]
INDEX4 = ["SPY", "QQQ", "IWM", "DIA"]
ETF15 = ["SPY", "QQQ", "IWM", "DIA", "XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY"]  # fmt: skip

# Stocks that had a 1.5x/2x single-stock leveraged ETF listed before the window start (2024-01-08).
# Sources: Direxion press release 2022-09-07 (TSLL/AAPU first four on 2022-08, AMZU/GGLL/MSFU 2022-09-07),
# Direxion NVDU 2023-09-13, T-REX NVDX/TSLT 2023-10 (see external-brief.md).
LETF6 = ["NVDA", "TSLA", "AAPL", "AMZN", "GOOGL", "MSFT"]
SHARE_CLASS_DROP = {"GOOG": "GOOGL"}  # keep the higher-ranked/primary line in G1 pools

# ---- G1: noise band on options-active mega caps (rule fixed to paper-sleeve-noiseband-qqq.md)
G1_POOLS = ["TOP5", "TOP10", "TOP20", "LETF6"]
G1_INTERVAL = [15, 30, 60]
G1_MULT = [1.0, 1.5]
G1_FIXED = {"lookback": 14, "stop": "both", "vt_cap": 1.0, "vt_target": 0.02}
G1_PAPER = {
    "pool": "TOP10",
    "interval": 30,
    "mult": 1.0,
}  # anchor only; selection uses the median rule

# ---- G2: end-of-day reversal (Baltussen-Da-Soebhag 2025)
G2_UNIVERSE = ["ETF14", "TOP100", "TOP500"]
G2_GROUP = ["decile", "extreme5", "long_only"]
G2_SIGNAL = ["pc_to_1500", "pc_to_1530", "open_to_1530"]  # prev close/open -> signal end
G2_ENTRY = "15:30"  # fill at the open of the 15:30 bar
G2_EXIT = "15:55"  # market exit at the close of the 15:50-15:55 bar

# ---- G3: ETF gap fill (entry/exit minutes after the open)
G3_PCT = [0.75, 0.90, 0.95]  # trailing-250-day percentile of |overnight gap|
G3_ENTRY = [5, 15]  # 09:35, 09:45 (minutes after 09:30)
G3_EXIT = [30, 45, 60]  # 10:00, 10:15, 10:30
G3_BASKET_MAIN = "INDEX4"
G3_DEPTH_BASKETS = ["SPY", "INDEX4", "ETF15"]


def grid_g1() -> list[dict]:
    return [
        {"id": f"G1|{p}|k{k}|M{m}", "group": "G1", "pool": p, "interval": k, "mult": m}
        for p, k, m in product(G1_POOLS, G1_INTERVAL, G1_MULT)
    ]


def grid_g2() -> list[dict]:
    return [
        {"id": f"G2|{u}|{g}|{s}", "group": "G2", "universe": u, "grouping": g, "signal": s}
        for u, g, s in product(G2_UNIVERSE, G2_GROUP, G2_SIGNAL)
    ]


def grid_g3() -> list[dict]:
    main = [
        {
            "id": f"G3|{G3_BASKET_MAIN}|p{int(p * 100)}|e{e}|x{x}",
            "group": "G3",
            "basket": G3_BASKET_MAIN,
            "pct": p,
            "entry": e,
            "exit": x,
        }
        for p, e, x in product(G3_PCT, G3_ENTRY, G3_EXIT)
    ]
    return main


def all_trials() -> list[dict]:
    return grid_g1() + grid_g2() + grid_g3()


# ------------------------------------------------------------------ point-in-time pools
@lru_cache(maxsize=1)
def universe_table() -> pd.DataFrame:
    """Previous-month-end snapshot ranks of data/features/universe_broad (excludes ETFs, close >= $5)."""
    parts = [
        pd.read_parquet(p)
        for p in sorted((ROOT / "data/features/universe_broad").glob("*.parquet"))
    ]
    u = pd.concat(parts, ignore_index=True)
    u = u[u["close"] >= 5.0].copy()
    u["month_end"] = pd.to_datetime(u["month_end"])
    u = u.sort_values(["month_end", "adv_rank"])
    u["rank_in_pool"] = u.groupby("month_end").cumcount() + 1
    # share-class dedup used by the G1 pools only
    drop = set(SHARE_CLASS_DROP)
    keep = u[~u["symbol"].isin(drop)].copy()
    keep["rank_dedup"] = keep.groupby("month_end").cumcount() + 1
    u = u.merge(keep[["month_end", "symbol", "rank_dedup"]], on=["month_end", "symbol"], how="left")
    return u


def pool_for_month(year: int, month: int, name: str) -> list[str]:
    """Pool in force for sessions of (year, month): the snapshot at the previous calendar month-end."""
    u = universe_table()
    py, pm = (year, month - 1) if month > 1 else (year - 1, 12)
    me = u["month_end"]
    snap = u[(me.dt.year == py) & (me.dt.month == pm)]
    if snap.empty:
        return []
    if name.startswith("TOP"):
        n = int(name[3:])
        col = "rank_dedup" if n <= 20 else "rank_in_pool"
        return snap.loc[snap[col] <= n, "symbol"].tolist()
    if name == "LETF6":
        return list(LETF6)
    raise ValueError(name)


def pool_symbols(name: str, start: str = "2017-09-01", end: str = "2026-09-30") -> list[str]:
    """Union of a pool over all months in [start, end] (what must be loaded, not what trades)."""
    out: set[str] = set()
    for ts in pd.period_range(start, end, freq="M"):
        out.update(pool_for_month(ts.year, ts.month, name))
    return sorted(out)


if __name__ == "__main__":
    for g, f in (("G1", grid_g1), ("G2", grid_g2), ("G3", grid_g3)):
        print(g, len(f()))
    print("total", len(all_trials()))
    for n in ("TOP20", "LETF6"):
        print(n, len(pool_symbols(n)))
    print(pool_for_month(2024, 1, "TOP10"))
