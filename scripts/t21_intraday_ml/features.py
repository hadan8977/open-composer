"""T-20261006-21 step 3: features, labels, baseline signals and cost inputs, one month at a time.

    flock /tmp/oc-heavy.lock ./scripts/run_capped.sh --mem 1.2G -- \
        uv run python scripts/t21_intraday_ml/features.py [--months 2024-01 ...]

Reads  data/features/intraday5m/<Y>/<M>.parquet (+ previous month for history), universe.parquet,
       data/features/daily_broad/<Y>.parquet (cost inputs, beta).
Writes data/features/t21_panel/<Y>-<M>.parquet: one row per (symbol, day, decision bar t) for the month's
top-600 pool; 2023 months keep the training grid t = 11 + 3j only, 2024+ months keep every bar 11..76.
Decision bar t closes at 09:30 + 5*(t+1) minutes; entry is the open of bar t+1; exit is the close of bar t+h/5.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
import os

IN_DIR = Path(os.environ.get("T21_IN_DIR", ROOT / "data/features/intraday5m"))
OUT_DIR = Path(os.environ.get("T21_OUT_DIR", ROOT / "data/features/t21_panel"))
DAILY = Path(os.environ.get("T21_DAILY", ROOT / "data/features/daily_broad"))
BARS = 78
T_MIN, T_MAX = 11, 76
HORIZONS = {15: 3, 30: 6, 60: 12, 25: 5}  # 25 = baseline B1 (15:30 -> 15:55) only
RET_NAMES = ["r5", "r15", "r30", "r60", "r_open", "gap", "r_d1", "r_d5"]
RAW = RET_NAMES
REL = [f"{n}_rel" for n in RET_NAMES]
OTHER = ["vol_ratio", "rv30", "vwap_dist", "slot", "spy_r30"]
RANK_RAW = [f"rk_{n}" for n in RET_NAMES]
RANK_BETA = [f"rkb_{n}" for n in RET_NAMES]
RANK_OTHER = ["rk_vol_ratio", "rk_rv30", "rk_vwap_dist"]
FEATURES = RAW + REL + OTHER + RANK_RAW + RANK_BETA + RANK_OTHER
assert len(FEATURES) == 40, len(FEATURES)
SPLIT_GAP = 0.5


def prev_month(month: str) -> str:
    return str(pd.Period(month, "M") - 1)


def load_bars(month: str, symbols: list[str]) -> pd.DataFrame | None:
    y, m = month.split("-")
    f = IN_DIR / y / f"{m}.parquet"
    if not (IN_DIR / y / f"{m}.READY").exists():
        return None
    df = pd.read_parquet(f, filters=[("symbol", "in", symbols)])
    return df


def tensors(
    bars: pd.DataFrame, symbols: list[str], days: list[pd.Timestamp]
) -> dict[str, np.ndarray]:
    s_idx = {s: i for i, s in enumerate(symbols)}
    d_idx = {d: i for i, d in enumerate(days)}
    si = bars["symbol"].map(s_idx).to_numpy()
    di = bars["d"].map(d_idx).to_numpy()
    ok = ~(pd.isna(si) | pd.isna(di))
    si, di = si[ok].astype(int), di[ok].astype(int)
    bi = bars["bar"].to_numpy()[ok].astype(int)
    out = {}
    for name in ("open", "high", "low", "close", "volume", "vwap", "n_min"):
        a = np.full((len(symbols), len(days), BARS), np.nan, dtype=np.float32)
        a[si, di, bi] = bars[name].to_numpy()[ok]
        out[name] = a
    return out


def cs_rank(x: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """Cross-sectional percentile rank over axis 0 among valid entries; NaN elsewhere. x shape (S, ...)."""
    v = np.where(valid & np.isfinite(x), x, np.nan)
    order = np.argsort(np.argsort(np.where(np.isnan(v), np.inf, v), axis=0, kind="stable"), axis=0)
    n = np.sum(~np.isnan(v), axis=0)
    r = (order + 0.5) / np.maximum(n, 1)
    return np.where(np.isnan(v), np.nan, r)


def cost_inputs(month: str, symbols: list[str], days: list[pd.Timestamp]) -> pd.DataFrame:
    """Prior-session close, dollar_adv_21, vol_21 and beta_252_spy per (symbol, day): the latest daily_broad
    row strictly before the day."""
    y = int(month[:4])
    files = [
        str(DAILY / f"{yy}.parquet") for yy in (y - 1, y) if (DAILY / f"{yy}.parquet").exists()
    ]
    lo = (min(days) - pd.Timedelta(days=12)).strftime("%Y-%m-%d")
    con = duckdb.connect()
    con.execute("SET memory_limit='500MB'; SET threads=2")
    con.execute("CREATE TEMP TABLE syms(symbol VARCHAR)")
    con.executemany("INSERT INTO syms VALUES (?)", [(s,) for s in symbols])
    q = f"""SELECT symbol, CAST(trade_date AS DATE) AS dd, close AS px_prev, dollar_adv_21 AS adv21,
                   vol_21 AS vol21, beta_252_spy AS beta
            FROM read_parquet({files}) WHERE symbol IN (SELECT symbol FROM syms)
              AND CAST(trade_date AS DATE) >= DATE '{lo}'"""
    daily = con.execute(q).df()
    daily["dd"] = pd.to_datetime(daily["dd"]).astype("datetime64[ns]")
    daily = daily.sort_values(["dd", "symbol"])
    sd = pd.MultiIndex.from_product([symbols, days], names=["symbol", "d"]).to_frame(index=False)
    sd["d"] = pd.to_datetime(sd["d"]).astype("datetime64[ns]")
    sd["key"] = sd["d"] - pd.Timedelta(days=1)  # strictly before: merge_asof backward on d-1 day
    sd = sd.sort_values("key")
    out = pd.merge_asof(sd, daily, left_on="key", right_on="dd", by="symbol", direction="backward")
    return out[["symbol", "d", "px_prev", "adv21", "vol21", "beta"]]


def build_month(month: str, uni: pd.DataFrame) -> pd.DataFrame | None:
    pool = uni[uni["month"] == month].sort_values("rank_in_pool")
    symbols = ["SPY"] + [s for s in pool["symbol"] if s != "SPY"]
    cur = load_bars(month, symbols)
    if cur is None:
        return None
    prev = load_bars(prev_month(month), symbols)
    bars = cur if prev is None else pd.concat([prev, cur], ignore_index=True)
    days_all = sorted(bars["d"].unique())
    # half days: SPY has no volume in bars 70..76
    spy = bars[bars["symbol"] == "SPY"]
    late = spy[(spy["bar"] >= 70) & (spy["bar"] <= 76)].groupby("d")["volume"].sum()
    full_days = [d for d in days_all if late.get(d, 0) > 0]
    days = [pd.Timestamp(d) for d in full_days]
    cur_days = [d for d in days if d.strftime("%Y-%m") == month]
    if not cur_days:
        return None
    T = tensors(bars, symbols, days)
    O, C, V, VW, NM = T["open"], T["close"], T["volume"], T["vwap"], T["n_min"]
    S, D = len(symbols), len(days)
    day_open = np.full((S, D), np.nan, dtype=np.float32)
    for b in range(0, 12):  # first valid open among the first 12 bars (known by t >= 11)
        day_open = np.where(np.isnan(day_open), O[:, :, b], day_open)
    last_close = C[:, :, 77]
    lc = pd.DataFrame(last_close).ffill(axis=1)
    prev_close = lc.shift(1, axis=1).to_numpy()
    prev2 = lc.shift(2, axis=1).to_numpy()
    prev6 = lc.shift(6, axis=1).to_numpy()
    gap_day = day_open / prev_close - 1.0
    split_flag = (np.abs(gap_day) > SPLIT_GAP) & np.isfinite(gap_day)
    sf = pd.DataFrame(split_flag.astype(float))
    bad_day = sf.T.rolling(6, min_periods=1).max().T.to_numpy() > 0  # event within d-5..d
    r_d1 = prev_close / prev2 - 1.0
    r_d5 = prev_close / prev6 - 1.0
    # same-slot history for volume ratio
    vm = V.astype(np.float64)
    vm[NM == 0] = 0.0  # filled bars carry volume 0 (real zero)
    vm[np.isnan(V)] = np.nan
    vol_hist = np.full_like(vm, np.nan)
    for d in range(1, D):
        lo = max(0, d - 20)
        with np.errstate(all="ignore"):
            vol_hist[:, d, :] = np.nanmean(vm[:, lo:d, :], axis=1)
    tv = np.nan_to_num(VW.astype(np.float64) * V.astype(np.float64))
    cumtv = np.cumsum(tv, axis=2)
    cumv = np.cumsum(np.nan_to_num(V.astype(np.float64)), axis=2)
    cost = cost_inputs(month, symbols, cur_days)
    cost_idx = cost.set_index(["symbol", "d"])
    # labels over all days (needed for the HKS 20-day history)
    Y = {}
    R = {}
    for h, m in HORIZONS.items():
        ret = np.full((S, D, BARS), np.nan, dtype=np.float64)
        for t in range(T_MIN, T_MAX - m + 1):
            ret[:, :, t] = C[:, :, t + m] / O[:, :, t + 1] - 1.0
        R[h] = ret
        Y[h] = ret - ret[0:1, :, :]
    # HKS same-slot history: mean of the previous 20 days' relative label at the same t
    b2 = {}
    for h in (15, 30, 60):
        a = np.full((S, D, BARS), np.nan)
        for d in range(1, D):
            lo = max(0, d - 20)
            with np.errstate(all="ignore"):
                a[:, d, :] = np.nanmean(Y[h][:, lo:d, :], axis=1)
        b2[h] = a
    rows = []
    spy_i = 0
    dif = np.diff(
        np.log(C.astype(np.float64)), axis=2
    )  # (S, D, 77): dif[..., b-1] = return of bar b
    rv_all = np.lib.stride_tricks.sliding_window_view(dif, 6, axis=2).std(axis=3, ddof=1) * np.sqrt(
        6
    )  # (S,D,72)
    traded_cs = np.concatenate(
        [np.zeros((S, D, 1)), np.cumsum(np.nan_to_num(NM) > 0, axis=2)], axis=2
    )  # (S,D,79)
    pr_map = pool.set_index("symbol")["rank_in_pool"].reindex(symbols).to_numpy(dtype=np.float32)
    for d_pos, d in enumerate(days):
        if d not in cur_days:
            continue
        tt = np.array(
            [t for t in range(T_MIN, T_MAX + 1) if d.year >= 2024 or (t - T_MIN) % 3 == 0]
        )
        T = len(tt)
        cd = cost_idx.xs(d, level="d")
        beta = cd["beta"].reindex(symbols).to_numpy(dtype=np.float64)
        beta = np.where(np.isfinite(beta), beta, 1.0)
        c_t = C[:, d_pos, tt].astype(np.float64)
        o0 = day_open[:, d_pos].astype(np.float64)

        def back(k):
            idx = tt - k
            return np.where(
                (idx >= 0)[None, :],
                C[:, d_pos, np.clip(idx, 0, None)].astype(np.float64),
                o0[:, None],
            )

        feats = {
            "r5": c_t / back(1) - 1.0,
            "r15": c_t / back(3) - 1.0,
            "r30": c_t / back(6) - 1.0,
            "r60": c_t / back(12) - 1.0,
            "r_open": c_t / o0[:, None] - 1.0,
            "gap": np.repeat(gap_day[:, d_pos].astype(np.float64)[:, None], T, axis=1),
            "r_d1": np.repeat(r_d1[:, d_pos].astype(np.float64)[:, None], T, axis=1),
            "r_d5": np.repeat(r_d5[:, d_pos].astype(np.float64)[:, None], T, axis=1),
        }
        for n in RET_NAMES:
            feats[f"{n}_rel"] = feats[n] - feats[n][spy_i][None, :]
        feats["rv30"] = rv_all[:, d_pos, tt - 6]
        cv = cumv[:, d_pos, tt]
        ctv = cumtv[:, d_pos, tt]
        with np.errstate(all="ignore"):
            feats["vwap_dist"] = np.where(
                cv > 0, c_t / (ctv / np.where(cv > 0, cv, 1)) - 1.0, np.nan
            )
            vh = vol_hist[:, d_pos, tt]
            feats["vol_ratio"] = np.where(
                vh > 0, vm[:, d_pos, tt] / np.where(vh > 0, vh, 1), np.nan
            )
        feats["slot"] = np.repeat(tt.astype(np.float64)[None, :], S, axis=0)
        feats["spy_r30"] = np.repeat(feats["r30"][spy_i][None, :], S, axis=0)
        traded = traded_cs[:, d_pos, tt + 1] - traded_cs[:, d_pos, tt - 11]
        valid = (
            np.isfinite(c_t)
            & (traded >= 6)
            & np.isfinite(o0)[:, None]
            & ~bad_day[:, d_pos][:, None]
            & np.isfinite(gap_day[:, d_pos])[:, None]
        )
        valid[spy_i, :] = False
        for n in RET_NAMES:
            feats[f"rk_{n}"] = cs_rank(feats[n], valid)
            feats[f"rkb_{n}"] = cs_rank(feats[n] - beta[:, None] * feats[n][spy_i][None, :], valid)
        for n in ("vol_ratio", "rv30", "vwap_dist"):
            feats[f"rk_{n}"] = cs_rank(feats[n], valid)
        cols = {"symbol": np.repeat(np.array(symbols, dtype=object)[None, :], T, axis=0).ravel()}
        cols["d"] = np.full(S * T, d)
        cols["t"] = np.repeat(tt.astype(np.int8)[:, None], S, axis=1).ravel()
        cols["pool_rank"] = np.repeat(pr_map[None, :], T, axis=0).ravel()
        for k_, v_ in feats.items():
            cols[k_] = v_.T.astype(np.float32).ravel()
        for h, m in HORIZONS.items():
            ok = valid & ((tt + m) <= T_MAX)[None, :]
            ret = R[h][:, d_pos, tt]
            cols[f"y{h}"] = np.where(ok, Y[h][:, d_pos, tt], np.nan).T.astype(np.float32).ravel()
            cols[f"ret{h}"] = np.where(ok, ret, np.nan).T.astype(np.float32).ravel()
            spy_h = np.where((tt + m) <= T_MAX, R[h][spy_i, d_pos, tt], np.nan)
            cols[f"spy{h}"] = np.repeat(spy_h.astype(np.float32)[:, None], S, axis=1).ravel()
            if h != 25:
                cols[f"b2_{h}"] = (
                    np.where(valid, b2[h][:, d_pos, tt], np.nan).T.astype(np.float32).ravel()
                )
        for nm in ("px_prev", "adv21", "vol21"):
            v_ = cd[nm].reindex(symbols).to_numpy(dtype=np.float32)
            cols[nm] = np.repeat(v_[None, :], T, axis=0).ravel()
        cols["beta"] = np.repeat(beta.astype(np.float32)[None, :], T, axis=0).ravel()
        vm_ = valid.T.ravel()
        cols["valid"] = vm_
        df = pd.DataFrame(cols)
        rows.append(df[vm_])
    out = pd.concat(rows, ignore_index=True)
    out["symbol"] = out["symbol"].astype("category")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", nargs="*")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--nshards", type=int, default=1)
    args = ap.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    uni = pd.read_parquet(IN_DIR / "universe.parquet")
    todo = (args.months or sorted(uni["month"].unique()))[args.shard :: args.nshards]
    for month in todo:
        out = OUT_DIR / f"{month}.parquet"
        if out.exists() and not args.force:
            print(month, "exists, skip", flush=True)
            continue
        t0 = time.time()
        df = build_month(month, uni)
        if df is None:
            print(month, "no bars (not READY?)", flush=True)
            continue
        tmp = OUT_DIR / f"{month}.parquet.tmp"
        df.to_parquet(tmp, index=False, compression="zstd")
        tmp.replace(out)
        print(
            f"{month}: {len(df)} rows, {df['symbol'].nunique()} symbols, {df['d'].nunique()} days, {time.time() - t0:.0f}s",
            flush=True,
        )
        del df
    return 0


if __name__ == "__main__":
    sys.exit(main())
