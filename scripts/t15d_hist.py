# ruff: noqa: E501, E741
"""T-20261006-15-D V4 for the stock basket: the selected spec on the 2017-10 .. 2023-08 stress period.

Only run when the selected stock spec meets every other P1 criterion (a spec that already fails DSR,
placebo or robustness cannot reach a tier, so its V4 is moot; the decision rule is written in
report_d.md before the stock numbers are looked at).

Steps (each resumable, run through scripts/heavy_run.sh):
  universe   point-in-time top-50 pools 2017-07 .. 2023-08 from data/features/universe_broad (same rule as
             data/features/intraday5m/universe.parquet: previous month-end snapshot, close >= 5)
  extract    1-minute bars of every pool member from data/sip-hist/minute (<= 2022) and data/sip/minute (2023)
  series     indicator signals per symbol (cache data/features/t15_work/d_sig_hist/)
  v4         selected spec -> daily net -> data/features/t15_work/d_acc/stock_v4_<period>_<dir>_<sig>.npz

    scripts/heavy_run.sh --mem 0.8G -- uv run python scripts/t15d_hist.py <step> [period direction signal]
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import t15d_engine as X  # noqa: E402
import t15d_extract_stock_minutes as XS  # noqa: E402
import t15d_run as R  # noqa: E402

WORK = X.WORK
HIST_MIN = WORK / "d_min_hist"
HIST_SIG = WORK / "d_sig_hist"
HIST_UNIVERSE = WORK / "d_universe_hist.parquet"
UNIV_SRC = ROOT / "data/features/universe_broad"
FIRST_TRADE_MONTH, LAST_TRADE_MONTH = "2017-10", "2023-08"
FIRST_EXTRACT_MONTH = "2017-06"


def build_universe() -> pd.DataFrame:
    frames = [pd.read_parquet(UNIV_SRC / f"{y}.parquet") for y in range(2017, 2024)]
    u = pd.concat(frames, ignore_index=True)
    u["month_end"] = pd.to_datetime(u["month_end"])
    u = u[u["close"] >= 5.0].sort_values(["month_end", "adv_rank"])
    u["rank_in_pool"] = u.groupby("month_end").cumcount() + 1
    u["month"] = (u["month_end"] + pd.offsets.MonthBegin(1)).dt.strftime("%Y-%m")
    u = u[(u["month"] >= FIRST_TRADE_MONTH) & (u["month"] <= LAST_TRADE_MONTH)]
    u = u[u["rank_in_pool"] <= XS.TOP_N]
    return u[["month", "month_end", "symbol", "adv_rank", "rank_in_pool", "dollar_adv", "close"]]


def step_universe() -> None:
    u = build_universe()
    u.to_parquet(HIST_UNIVERSE)
    print(len(u), "rows,", u["symbol"].nunique(), "symbols,", u["month"].nunique(), "months")


def step_extract() -> None:
    u = pd.read_parquet(HIST_UNIVERSE)
    symbols = sorted(u["symbol"].unique())
    months = XS.month_list(FIRST_EXTRACT_MONTH, LAST_TRADE_MONTH)
    (HIST_MIN / "_done").mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute("SET memory_limit='500MB'")
    con.execute("SET threads=2")
    for month in months:
        marker = HIST_MIN / "_done" / month
        if marker.exists():
            continue
        y = int(month[:4])
        XS.MIN_DIR = ROOT / ("data/sip-hist/minute" if y <= 2022 else "data/sip/minute")
        t0 = time.time()
        n = XS.extract_month(con, month, symbols, HIST_MIN)
        if n >= 0:
            marker.write_text(f"{n}\n")
        print(f"{month}: {n} rows, {time.time() - t0:.0f}s", flush=True)


def patch_hist() -> pd.DataFrame:
    X.D_MIN = HIST_MIN
    X.SIG_DIR = HIST_SIG
    u = pd.read_parquet(HIST_UNIVERSE)
    syms = sorted(u["symbol"].unique())
    R.baskets = lambda: {"TOP50": dict(kind="stock", syms=syms, N=50)}
    return u


def step_series() -> None:
    patch_hist()
    syms = R.baskets()["TOP50"]["syms"]
    for sym in syms:
        for period, ph in (("1m", 0), ("1h", 0)):
            if (X.SIG_DIR / f"{sym}_{period}_ph{ph}.npz").exists():
                continue
            S = X.build_series(sym, "stock", period, ph)
            print(sym, period, None if S is None else len(S["o"]), flush=True)


def step_v4(period: str, dirn: str, sig: str) -> None:
    u = patch_hist()
    a = R.series_sum("TOP50", period, dirn, sig, R.PERIODS[period]["H"], universe=u)
    net = a["g"] - (a["cv"] + a["cf"]) / 1e4 / float(a["N"])
    out = X.WORK / "d_acc" / f"stock_v4_{period}_{dirn}_{sig}.npz"
    np.savez_compressed(out, net=net, g=a["g"], cv=a["cv"], cf=a["cf"], ent=a["ent"])
    print("wrote", out)


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "universe":
        step_universe()
    elif cmd == "extract":
        step_extract()
    elif cmd == "series":
        step_series()
    elif cmd == "v4":
        step_v4(*sys.argv[2:5])
    else:
        raise SystemExit(f"unknown step {cmd}")
