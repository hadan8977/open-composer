"""T-20261006-15 group C: opening-range breakout on stocks in play (Zarattini-Barbon-Aziz 2024).

Frozen design: hypotheses.md section C + amendment-2026-10-06-main-grid.md; this file executes it.

Stages (all resumable per month, outputs under data/features/t15_c/):

    pool     pool table (month, symbol, rank_in_pool) for 2017-09..2026-10 from universe_broad
    hist5m   5-minute bars for 2017-09..2022-12 from data/sip-hist/minute (pool symbols only)
    daily    per-month symbol-day daily features from the 5-minute bars
    base     feature table with hygiene (price_hygiene defaults + split-ratio trigger drop)
    trades   per-month candidate trades for every variant (3 ranges x 3 stops x 2 semantics, mirror
             direction, delayed entries)
    analyze  portfolios, selection, placebos, DSR, phases, V4 -> results_c.json, ledger

Run each stage via scripts/heavy_run.sh --mem 0.8G -- uv run python scripts/t15_c_orb.py <stage>.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import os  # noqa: E402

WORK = Path(os.environ.get("T15C_WORK", ROOT / "data/features/t15_c"))
P5 = ROOT / "data/features/intraday5m"
HIST_MIN = ROOT / "data/sip-hist/minute"
UNIVERSE_SRC = ROOT / "data/features/universe_broad"
BARS = 78
TOP_MAX = 600
FIRST_MONTH, LAST_MONTH = "2017-09", "2026-10"
HIST_LAST = "2022-12"  # months up to here come from sip-hist, 2023-01 on from intraday5m
RANGES = (5, 15, 30)
NB = {5: 1, 15: 3, 30: 6}
STOPS = ("atr10", "opposite", "atr5")
ATR_F = {"atr10": 0.10, "atr5": 0.05}
SEMS = ("stop_price", "trigger_bar_close")
DELAYS = (1, 2)
FEES_BP = 0.5
# split-like ratios (open_t / close_{t-1}); both directions
_SPLIT_R = np.array([1.5, 2, 2.5, 3, 4, 5, 6, 7, 8, 10, 12, 15, 20, 25, 30, 40, 50], float)
SPLIT_LOG = np.log(np.concatenate([_SPLIT_R, 1.0 / _SPLIT_R]))
SPLIT_TOL = 0.08
MIN_PRICE, MIN_AVGVOL, MIN_ATR = 5.0, 1_000_000.0, 0.5


def months(first: str, last: str) -> list[str]:
    return [p.strftime("%Y-%m") for p in pd.period_range(first, last, freq="M")]


def month_src(m: str) -> Path | None:
    y, mm = m.split("-")
    if m <= HIST_LAST:
        f = WORK / "hist5m" / y / f"{mm}.parquet"
        return f if (WORK / "hist5m" / y / f"{mm}.READY").exists() else None
    f = P5 / y / f"{mm}.parquet"
    return f if (P5 / y / f"{mm}.READY").exists() else None


# ------------------------------------------------------------------------------------ pool
def build_pool() -> pd.DataFrame:
    """Same rule as scripts/t21_intraday_ml/build_5m.build_universe, extended back to 2017-09."""
    frames = [pd.read_parquet(UNIVERSE_SRC / f"{y}.parquet") for y in range(2017, 2027)]
    u = pd.concat(frames, ignore_index=True)
    u["month_end"] = pd.to_datetime(u["month_end"])
    u = u[u["close"] >= 5.0].sort_values(["month_end", "adv_rank"])
    u["rank_in_pool"] = u.groupby("month_end").cumcount() + 1
    u = u[u["rank_in_pool"] <= TOP_MAX].copy()
    u["month"] = (u["month_end"] + pd.offsets.MonthBegin(1)).dt.strftime("%Y-%m")
    u = u[(u["month"] >= FIRST_MONTH) & (u["month"] <= LAST_MONTH)]
    return u[["month", "symbol", "rank_in_pool", "dollar_adv", "close"]].reset_index(drop=True)


def cmd_pool(args) -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    u = build_pool()
    u.to_parquet(WORK / "pool.parquet", index=False)
    ref = pd.read_parquet(P5 / "universe.parquet")
    chk = u[u["month"] >= "2023-01"].merge(
        ref[["month", "symbol", "rank_in_pool"]],
        on=["month", "symbol"],
        how="outer",
        suffixes=("", "_ref"),
        indicator=True,
    )
    chk = chk[chk["month"] <= ref["month"].max()]
    bad = chk[(chk["_merge"] != "both") | (chk["rank_in_pool"] != chk["rank_in_pool_ref"])]
    print(f"pool rows {len(u)}, mismatches vs intraday5m/universe.parquet: {len(bad)}")


# ------------------------------------------------------------------------------------ hist5m
def cmd_hist5m(args) -> None:
    import duckdb

    sys.path.insert(0, str(ROOT / "scripts/t21_intraday_ml"))
    import build_5m as B  # noqa: E402

    B.MIN_DIR = HIST_MIN
    pool = pd.read_parquet(WORK / "pool.parquet")
    con = duckdb.connect()
    con.execute("SET memory_limit='400MB'; SET threads=2; SET preserve_insertion_order=false")
    for m in args.months or months(FIRST_MONTH, HIST_LAST):
        y, mm = m.split("-")
        out_dir = WORK / "hist5m" / y
        out_dir.mkdir(parents=True, exist_ok=True)
        if (out_dir / f"{mm}.READY").exists() and not args.force:
            print(m, "ready", flush=True)
            continue
        syms = sorted(pool.loc[pool["month"] == m, "symbol"])
        t0 = time.time()
        raw = Path(f"/tmp/t15c_raw_{m}.parquet")
        B.build_month(con, m, syms, raw)
        present = [
            r[0]
            for r in con.execute(
                f"SELECT DISTINCT symbol FROM read_parquet('{raw}') ORDER BY 1"
            ).fetchall()
        ]
        parts = []
        for i in range(0, len(present), 100):
            chunk = present[i : i + 100]
            g = B.fill_grid(pd.read_parquet(raw, filters=[("symbol", "in", chunk)]))
            parts.append(
                g[["symbol", "d", "bar", "open", "high", "low", "close", "volume", "filled"]]
            )
        df = pd.concat(parts, ignore_index=True)
        tmp = out_dir / f"{mm}.parquet.tmp"
        df.to_parquet(tmp, compression="zstd", index=False)
        tmp.replace(out_dir / f"{mm}.parquet")
        raw.unlink()
        (out_dir / f"{mm}.READY").touch()
        print(f"{m}: {len(df)} rows, {len(present)} symbols, {time.time() - t0:.0f}s", flush=True)


# ------------------------------------------------------------------------------------ arrays
COLS = ["symbol", "d", "bar", "open", "high", "low", "close", "volume", "filled"]


def load_month(m: str) -> dict | None:
    f = month_src(m)
    if f is None:
        return None
    start = pd.Timestamp(m + "-01")
    df = pd.read_parquet(
        f, columns=COLS, filters=[("d", ">=", start), ("d", "<", start + pd.offsets.MonthBegin(1))]
    )
    if df.duplicated(["symbol", "d", "bar"]).any():
        raise ValueError(f"Duplicate 5m bars in {f}")
    syms = np.sort(df["symbol"].unique())
    days = np.sort(df["d"].unique())
    si = pd.Categorical(df["symbol"], categories=syms).codes
    di = np.searchsorted(days, df["d"].to_numpy())
    bi = df["bar"].to_numpy().astype(int)
    shp = (len(syms), len(days), BARS)
    A = {}
    for k in ("open", "high", "low", "close"):
        a = np.full(shp, np.nan, np.float32)
        a[si, di, bi] = df[k].to_numpy()
        A[k] = a
    v = np.zeros(shp, np.float32)
    v[si, di, bi] = df["volume"].to_numpy()
    A["volume"] = v
    valid = np.zeros(shp, bool)
    valid[si, di, bi] = df["filled"].to_numpy() == 0
    A["valid"] = valid
    return {"syms": syms, "days": pd.DatetimeIndex(days), "A": A}


def daily_of(M: dict) -> pd.DataFrame:
    A, syms, days = M["A"], M["syms"], M["days"]
    valid = A["valid"]
    anyv = valid.any(2)
    with np.errstate(all="ignore"):
        hi = np.nanmax(np.where(valid, A["high"], np.nan), axis=2)
        lo = np.nanmin(np.where(valid, A["low"], np.nan), axis=2)
    lb = BARS - 1 - np.argmax(valid[:, :, ::-1], axis=2)
    S, D = anyv.shape
    ii, jj = np.meshgrid(np.arange(S), np.arange(D), indexing="ij")
    cl = A["close"][ii, jj, lb]
    op = np.where(valid[:, :, 0], A["open"][:, :, 0], np.nan)
    vol = A["volume"].sum(2)
    v = A["volume"]
    out = pd.DataFrame(
        {
            "symbol": np.repeat(syms, D),
            "d": np.tile(days.to_numpy(), S),
            "o": op.ravel(),
            "h": hi.ravel(),
            "l": lo.ravel(),
            "c": np.where(anyv, cl, np.nan).ravel(),
            "vol": vol.ravel(),
            "rv5": v[:, :, 0].ravel(),
            "rv15": v[:, :, :3].sum(2).ravel(),
            "rv30": v[:, :, :6].sum(2).ravel(),
            "lastbar": np.where(anyv, lb, -1).ravel().astype(np.int16),
        }
    )
    return out[anyv.ravel()].reset_index(drop=True)


def cmd_daily(args) -> None:
    d = WORK / "daily"
    d.mkdir(parents=True, exist_ok=True)
    for m in args.months or months(FIRST_MONTH, LAST_MONTH):
        out = d / f"{m}.parquet"
        if out.exists() and not args.force:
            continue
        M = load_month(m)
        if M is None:
            print(m, "no 5m source", flush=True)
            continue
        df = daily_of(M)
        for k in ("o", "h", "l", "c", "vol", "rv5", "rv15", "rv30"):
            df[k] = df[k].astype("float64")
        df.to_parquet(out, index=False)
        print(m, len(df), flush=True)


# ------------------------------------------------------------------------------------ base
def split_events(o: pd.DataFrame, c: pd.DataFrame) -> pd.DataFrame:
    """Boolean frame: session s where open_s / close_{s-1} sits on a split ratio (|ln| >= 0.3)."""
    q = np.log(o / c.shift(1))
    a = q.to_numpy()
    near = np.zeros(a.shape, bool)
    for r in SPLIT_LOG:
        near |= np.abs(a - r) < SPLIT_TOL
    near &= np.abs(a) >= 0.3
    return pd.DataFrame(near, index=o.index, columns=o.columns)


def canonical_daily(frame: pd.DataFrame, month: str) -> tuple[pd.DataFrame, int]:
    """Use the trading-date partition; conflicting duplicate bars are an input error."""
    own_month = frame["d"].dt.strftime("%Y-%m").eq(month)
    frame = frame.loc[own_month].copy()
    distinct = frame.drop_duplicates()
    if distinct.duplicated(["d", "symbol"]).any():
        raise ValueError(f"Conflicting daily bars in {month}")
    return distinct, int((~own_month).sum())


def causal_features(W: dict) -> tuple[dict, pd.DataFrame, dict]:
    from open_composer.research.features import price_hygiene as H

    # The default full-panel mask is an audit only: its last-break cutoff uses future data.
    _, _, audit = H.sanitize_price_matrices(W["c"], W["o"])
    ev = split_events(W["o"], W["c"])
    for br in H.detect_price_breaks(W["c"]):
        maskable = (
            br.kind == "jump"
            or br.gap_sessions >= H.DEFAULT_MASK_GAP_LONG_SESSIONS
            or abs(np.log(br.price_ratio)) >= H.DEFAULT_MASK_GAP_MIN_ABS_LOG_STEP
        )
        if maskable:
            ev.loc[br.first_session_after, br.symbol] = True
    pc = W["c"].shift(1).mask(ev)
    tr = pd.DataFrame(
        np.fmax(np.fmax(W["h"] - W["l"], (W["h"] - pc).abs()), (W["l"] - pc).abs()),
        index=pc.index,
        columns=pc.columns,
    )
    segments = ev.cumsum()

    def trailing(frame, window, minimum, stat="mean"):
        out = pd.DataFrame(index=frame.index, columns=frame.columns, dtype=float)
        for symbol in frame:
            out[symbol] = (
                frame[symbol]
                .groupby(segments[symbol], sort=False)
                .transform(
                    lambda x: getattr(x.rolling(window, min_periods=minimum), stat)().shift(1)
                )
            )
        return out

    ret = (W["c"] / pc - 1.0).where(lambda x: x.abs() < 0.5)
    feat = {
        "pc": pc,
        "atr": trailing(tr, 14, 14),
        "avgvol": trailing(W["vol"], 14, 14),
        "adv21": trailing(W["c"] * W["vol"], 21, 15),
        "vol21": trailing(ret, 21, 15, "std"),
    }
    for R in RANGES:
        base = trailing(W[f"rv{R}"], 14, 14)
        feat[f"rel{R}"] = W[f"rv{R}"] / base.where(base > 0)
    return (
        feat,
        ev,
        {
            "hygiene_audit_masked_symbols": audit.symbols_masked,
            "hygiene_policy": (
                "default sanitizer audit; open-visible causal resets, no backward deletion"
            ),
        },
    )


def cmd_base(args) -> None:
    files = sorted((WORK / "daily").glob("*.parquet"))
    pool = pd.read_parquet(WORK / "pool.parquet")
    syms_all = sorted(pool["symbol"].unique())
    parts = []
    notes = {
        "symbols": len(syms_all),
        "hygiene_audit_masked_symbols": 0,
        "outside_partition_rows": 0,
        "split_events": 0,
        "split_event_list": [],
    }
    chunk = 100
    for i in range(0, len(syms_all), chunk):
        cs = syms_all[i : i + chunk]
        daily_parts = []
        for f in files:
            d, outside = canonical_daily(pd.read_parquet(f, filters=[("symbol", "in", cs)]), f.stem)
            notes["outside_partition_rows"] += outside
            daily_parts.append(d)
        dd = pd.concat(daily_parts, ignore_index=True)
        if dd.duplicated(["d", "symbol"]).any():
            raise ValueError("Duplicate canonical daily keys across partitions")
        if dd.empty:
            continue
        W = {
            k: dd.pivot(index="d", columns="symbol", values=k).sort_index()
            for k in ("o", "h", "l", "c", "vol", "rv5", "rv15", "rv30")
        }
        feat, ev, audit = causal_features(W)
        notes["hygiene_audit_masked_symbols"] += audit["hygiene_audit_masked_symbols"]
        notes["hygiene_policy"] = audit["hygiene_policy"]
        notes["split_events"] += int(ev.to_numpy().sum())
        if ev.to_numpy().any():
            for t, s in zip(*np.nonzero(ev.to_numpy()), strict=True):
                notes["split_event_list"].append([str(ev.columns[s]), str(ev.index[t].date())])
        long = {k: v.stack(dropna=False) for k, v in feat.items()}
        F = pd.DataFrame(long)
        F["splitday"] = ev.stack(dropna=False)
        F["o"] = W["o"].stack(dropna=False)
        F.index.names = ["d", "symbol"]
        F = F.reset_index()
        ok = (
            F["pc"].gt(MIN_PRICE)
            & F["avgvol"].ge(MIN_AVGVOL)
            & F["atr"].gt(MIN_ATR)
            & F["adv21"].notna()
            & F["o"].notna()
            & ~F["splitday"].fillna(False).astype(bool)
        )
        parts.append(F[ok].drop(columns=["splitday", "o"]))
        print(f"chunk {i // chunk}: kept {int(ok.sum())}", flush=True)
    B = pd.concat(parts, ignore_index=True)
    B["month"] = B["d"].dt.strftime("%Y-%m")
    B = B.merge(pool[["month", "symbol", "rank_in_pool"]], on=["month", "symbol"], how="inner")
    B.to_parquet(WORK / "base.parquet", index=False)
    (WORK / "base_notes.json").write_text(json.dumps({**notes, "rows": len(B)}, indent=1))
    print("base rows", len(B), {k: v for k, v in notes.items() if k != "split_event_list"})


# ------------------------------------------------------------------------------------ trades
def sim(Op, Hh, Ll, C, V, e, dirn, stop, sem, eod):
    """Stop-order simulation for N trades (arrays N x 78, e = entry bar): (gross, stopped)."""
    n = len(e)
    ar = np.arange(n)
    bars = np.arange(BARS)[None, :]
    active = (bars >= e[:, None]) & V
    long_ = dirn > 0
    hit = np.where(long_[:, None], Ll <= stop[:, None], Hh >= stop[:, None]) & active
    anyhit = hit.any(1)
    first = np.argmax(hit, 1)
    ob = Op[ar, first]
    cb = C[ar, first]
    if sem == "stop_price":
        fill_stop = np.where(long_, np.minimum(stop, ob), np.maximum(stop, ob))
    else:
        fill_stop = cb
    fill = np.where(anyhit, fill_stop, eod)
    entry = Op[ar, e]
    gross = dirn * (fill / entry - 1.0)
    return gross, anyhit


def stop_level(kind, dirn, entry, atr, rng_hi, rng_lo):
    if kind == "opposite":
        return np.where(dirn > 0, rng_lo, rng_hi)
    f = ATR_F[kind]
    return entry - dirn * f * atr


def month_trades(m: str, B: pd.DataFrame, cost_model) -> pd.DataFrame | None:
    from open_composer.research.equity_book.costs import half_spread_bp

    M = load_month(m)
    if M is None:
        return None
    sym_ix = {s: i for i, s in enumerate(M["syms"])}
    day_ix = {d: i for i, d in enumerate(M["days"])}
    b = B[B["month"] == m]
    keep = (b["rel5"] >= 1) | (b["rel15"] >= 1) | (b["rel30"] >= 1)
    b = b[keep]
    si = b["symbol"].map(sym_ix)
    di = b["d"].map(day_ix)
    ok = si.notna() & di.notna()
    b, si, di = b[ok], si[ok].to_numpy(int), di[ok].to_numpy(int)
    if len(b) == 0:
        return None
    A = M["A"]
    Op, Hh, Ll, C = (A[k][si, di].astype(float) for k in ("open", "high", "low", "close"))
    V = A["valid"][si, di]
    n = len(b)
    ar = np.arange(n)
    lastbar = BARS - 1 - np.argmax(V[:, ::-1], axis=1)
    eod = C[ar, lastbar]
    atr = b["atr"].to_numpy(float)
    year = b["d"].dt.year.to_numpy()
    price = b["pc"].to_numpy(float)
    adv = b["adv21"].to_numpy(float)
    vol21 = b["vol21"].to_numpy(float)
    with np.errstate(all="ignore"):
        hs_open = half_spread_bp(price, adv, vol21, year, "open", cost_model)
        hs_close = half_spread_bp(price, adv, vol21, year, "close", cost_model)
    hs_open = np.where(np.isfinite(hs_open), hs_open, 40.0)
    hs_close = np.where(np.isfinite(hs_close), hs_close, 40.0)
    out = {
        "symbol": b["symbol"].to_numpy(),
        "d": b["d"].to_numpy(),
        "pool": b["rank_in_pool"].to_numpy(np.int16),
        "pc": price.astype(np.float32),
        "atr": atr.astype(np.float32),
        "hs_open": hs_open.astype(np.float32),
        "hs_close": hs_close.astype(np.float32),
    }
    for R in RANGES:
        nb = NB[R]
        o0 = Op[:, 0]
        cR = C[:, nb - 1]
        dirn = np.sign(cR - o0)
        rng_hi = np.nanmax(np.where(V[:, :nb], Hh[:, :nb], np.nan), axis=1)
        rng_lo = np.nanmin(np.where(V[:, :nb], Ll[:, :nb], np.nan), axis=1)
        e = np.full(n, nb)
        entry_ok = V[ar, e] & np.isfinite(cR) & (dirn != 0) & V[:, 0] & (lastbar > e)
        dirn = np.where(entry_ok, dirn, 1.0)
        entry = Op[ar, e]
        rel = b[f"rel{R}"].to_numpy(float)
        out[f"ok{R}"] = (entry_ok & (rel >= 1)).astype(np.int8)
        out[f"rel{R}"] = rel.astype(np.float32)
        out[f"dir{R}"] = np.where(entry_ok, dirn, 0).astype(np.int8)
        out[f"fwd{R}"] = np.where(entry_ok, eod / entry - 1.0, np.nan).astype(np.float32)
        for stop_kind in STOPS:
            for who, dd in (("g", dirn), ("m", -dirn)):
                st = stop_level(stop_kind, dd, entry, atr, rng_hi, rng_lo)
                for sem in SEMS:
                    g, hit = sim(Op, Hh, Ll, C, V, e, dd, st, sem, eod)
                    out[f"{who}{R}_{stop_kind}_{sem}"] = np.where(entry_ok, g, np.nan).astype(
                        np.float32
                    )
                out[f"{who}s{R}_{stop_kind}"] = hit.astype(np.int8)
        if R == 5:
            for dl in DELAYS:
                ed = np.full(n, nb + dl)
                ok_d = entry_ok & V[ar, ed] & (lastbar > ed)
                entry_d = Op[ar, ed]
                for stop_kind in STOPS:
                    st = stop_level(stop_kind, dirn, entry_d, atr, rng_hi, rng_lo)
                    g, hit = sim(Op, Hh, Ll, C, V, ed, dirn, st, "stop_price", eod)
                    out[f"gd{dl}_{stop_kind}"] = np.where(ok_d, g, np.nan).astype(np.float32)
                    out[f"gds{dl}_{stop_kind}"] = hit.astype(np.int8)
    return pd.DataFrame(out)


def cmd_trades(args) -> None:
    from open_composer.research.equity_book.costs import load_model

    model = load_model()
    (WORK / "trades").mkdir(parents=True, exist_ok=True)
    B = pd.read_parquet(WORK / "base.parquet")
    for m in args.months or months("2017-10", LAST_MONTH):
        out = WORK / "trades" / f"{m}.parquet"
        if out.exists() and not args.force:
            continue
        t0 = time.time()
        T = month_trades(m, B, model)
        if T is None:
            print(m, "no data/candidates", flush=True)
            continue
        T.to_parquet(out, index=False)
        print(
            f"{m}: {len(T)} candidate rows, {T['d'].nunique()} days, {time.time() - t0:.0f}s",
            flush=True,
        )


def cmd_analyze(args) -> None:
    from t15_c_analyze import main as analyze

    analyze()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["pool", "hist5m", "daily", "base", "trades", "analyze"])
    ap.add_argument("--months", nargs="*")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    {
        "pool": cmd_pool,
        "hist5m": cmd_hist5m,
        "daily": cmd_daily,
        "base": cmd_base,
        "trades": cmd_trades,
        "analyze": cmd_analyze,
    }[args.stage](args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
