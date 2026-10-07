"""T-20261006-15 frozen version grids (shared by the registration script and the runners).

Every version below is a counted trial. Do not edit after the pre-backtest validation stamp.
"""

from __future__ import annotations

from itertools import product

ETFS_INDEX = ["SPY", "QQQ", "IWM", "DIA"]
ETFS_SECTOR = ["XLK", "XLF", "XLE", "XLV", "XLY", "XLP", "XLI", "XLB", "XLU", "XLRE", "XLC"]
ETFS_LEV = ["TQQQ", "SPXL"]
ETFS_ALL = ETFS_INDEX + ETFS_SECTOR + ETFS_LEV

# Symbol-count depth points (scale curve axis for A and B): cumulative sets.
DEPTH_SETS = {
    "S1_spy": ["SPY"],
    "S2_spy_qqq": ["SPY", "QQQ"],
    "S3_index4": ETFS_INDEX,
    "S4_index4_sector11": ETFS_INDEX + ETFS_SECTOR,
    "S5_all17": ETFS_ALL,
}

# ---- group A: noise-band intraday momentum (Zarattini-Aziz-Barbon 2024)
A_MULT = [0.5, 1.0, 1.5, 2.0]
A_LOOKBACK = [7, 14, 28]
A_INTERVAL = [5, 15, 30]
A_STOP = ["band", "vwap", "both"]
A_VT = [0, 1]  # 1 = daily volatility target 2%, leverage cap 4 (paper)
A_PAPER = {"mult": 1.0, "lookback": 14, "interval": 30, "stop": "both", "vt": 1}

# ---- group B: market intraday momentum (Gao-Han-Li-Zhou 2018)
B_PRED = ["r1_intraday", "r1_overnight", "r1_plus_r12"]
B_THRESH = [0.0, 0.5, 1.0]
B_PAPER = {"pred": "r1_overnight", "thresh": 0.0}

# ---- group C: stocks-in-play opening range (Zarattini-Barbon-Aziz 2024)
C_RANGE = [5, 15, 30]
C_TOPK = [20, 50, 100]
C_STOP = ["opposite", "atr10", "atr5"]
C_POOL = [100, 300, 600]
C_FILL = ["stop_price", "trigger_bar_close"]
C_PAPER = {"range": 5, "topk": 20, "stop": "atr10", "pool": 600, "fill": "stop_price"}

# ---- group D: Reversal Trend indicator (owner Pine), hourly and 1-minute bars
D_TF = ["1h", "1m"]
D_HOLD = {"1h": [6, 13, 26], "1m": [30, 90, 180]}  # bars
D_EXIT = ["time_stop", "time_stop_or_reverse", "atr_trailing_2x"]
D_SIGNAL = ["primary_only", "primary_and_reclaim"]
D_SIDE = ["long_only", "long_short"]
D_UNIVERSE = ["QQQ", "SPY", "TOP50"]


def grid_a() -> list[dict]:
    return [
        {
            "id": f"A|{s}|m{m}|L{lb}|k{k}|{st}|vt{vt}",
            "group": "A",
            "symbol": s,
            "mult": m,
            "lookback": lb,
            "interval": k,
            "stop": st,
            "vt": vt,
        }
        for s, m, lb, k, st, vt in product(ETFS_ALL, A_MULT, A_LOOKBACK, A_INTERVAL, A_STOP, A_VT)
    ]


def grid_b() -> list[dict]:
    return [
        {"id": f"B|{s}|{p}|th{t}", "group": "B", "symbol": s, "pred": p, "thresh": t}
        for s, p, t in product(ETFS_ALL, B_PRED, B_THRESH)
    ]


def grid_c() -> list[dict]:
    return [
        {
            "id": f"C|pool{po}|r{r}|top{k}|{st}|{fl}",
            "group": "C",
            "pool": po,
            "range": r,
            "topk": k,
            "stop": st,
            "fill": fl,
        }
        for po, r, k, st, fl in product(C_POOL, C_RANGE, C_TOPK, C_STOP, C_FILL)
    ]


def grid_d() -> list[dict]:
    out = []
    for tf, side, u, h, ex, sg in product(D_TF, D_SIDE, D_UNIVERSE, [0, 1, 2], D_EXIT, D_SIGNAL):
        hold = D_HOLD[tf][h]
        out.append(
            {
                "id": f"D|{tf}|{u}|{side}|h{hold}|{ex}|{sg}",
                "group": "D",
                "tf": tf,
                "universe": u,
                "side": side,
                "hold": hold,
                "exit": ex,
                "signal": sg,
            }
        )
    return out


def all_trials() -> list[dict]:
    return grid_a() + grid_b() + grid_c() + grid_d()


if __name__ == "__main__":
    for g, f in (("A", grid_a), ("B", grid_b), ("C", grid_c), ("D", grid_d)):
        print(g, len(f()))
    print("total", len(all_trials()))
