# ruff: noqa: E501
"""T-20261006-22 feature store: residual-return matrices, attributes, news, short eligibility, VIX.

Contract: reports/research/iterations/t20261006_22_st_reversal/contract.md (sections 1-5 and addendum 1).
Output: data/research/t22_streversal/*.npy (float32 (T, N) on the master symbol order) + meta.json.

    flock /tmp/oc-heavy.lock ./scripts/run_capped.sh --mem 1.2G -- uv run python scripts/t22_build.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import os  # noqa: E402

from open_composer.research.equity_book import borrow  # noqa: E402
from open_composer.research.equity_book.panel import (  # noqa: E402
    DEFAULT_DIR,
    HEDGE_ETFS,
    PricePanel,
)

OUT = Path(os.environ.get("T22_STORE") or ROOT / "data/research/t22_streversal")
SMALL_RANK = int(
    os.environ.get("T22_SMALL_RANK") or 0
)  # debug: only names that ever have adv_rank <= this
PCA_K = 10
PCA_WINDOW = 252
PCA_REFRESH = 21
PCA_SET_RANK = 4000
PCA_MIN_OBS = 200


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def master_symbols() -> list[str]:
    import duckdb

    con = duckdb.connect()
    con.execute("SET memory_limit='400MB'")
    con.execute("SET threads=2")
    g = f"{DEFAULT_DIR}/panel/20*.parquet"
    lim = SMALL_RANK or PCA_SET_RANK
    df = con.execute(
        f"select distinct symbol from read_parquet('{g}') where adv_rank <= {lim} order by 1"
    ).df()
    return sorted(set(df["symbol"].astype(str)) | set(HEDGE_ETFS))


def load_attr(dates: pd.DatetimeIndex, cols: pd.Index, names: list[str]) -> dict[str, np.ndarray]:
    """Year-by-year pivot of the panel attributes onto the (T, N) master grid."""
    out = {n: np.full((len(dates), len(cols)), np.nan, dtype="float32") for n in names}
    col_pos = {s: j for j, s in enumerate(cols)}
    for year in range(dates[0].year, dates[-1].year + 1):
        f = pd.read_parquet(
            DEFAULT_DIR / f"panel/{year}.parquet",
            columns=["trade_date", "symbol", "mcap_source", *names],
        )
        r = dates.get_indexer(pd.DatetimeIndex(f["trade_date"]))
        k = np.array([col_pos.get(s, -1) for s in f["symbol"].astype(str)])
        ok = (r >= 0) & (k >= 0)
        for n in names:
            v = f[n].to_numpy("float64")
            if n == "mcap":
                v = np.where(
                    f["mcap_source"].eq("sec").to_numpy(), v, np.nan
                )  # sec-sourced mcap only
            out[n][r[ok], k[ok]] = v[ok]
        del f
        log(f"attributes {year}")
    return out


def pca_block(
    r: np.ndarray, w: np.ndarray, sel: np.ndarray, p: int, nxt: int, e_pca: np.ndarray
) -> float:
    """Loadings from the window ``w`` (rows through the refresh session ``p``), residuals for sessions
    p+1 .. nxt-1 written into ``e_pca``; returns the explained-variance share of the top components.
    Session t uses only returns through p <= t-1 for the loadings and r[t] for the regression."""
    ws = w[:, sel]
    lo, hi = np.nanpercentile(ws, [1, 99], axis=0)
    wc = np.clip(ws, lo, hi)  # estimation only
    mu = np.nanmean(wc, axis=0)
    sd = np.nanstd(wc, axis=0)
    sd = np.where(sd > 1e-8, sd, np.nan)
    z = (wc - mu) / sd
    z = np.where(np.isfinite(z), z, 0.0)
    _, s, vt = np.linalg.svd(z, full_matrices=False)
    load = vt[:PCA_K].T  # (n, K)
    expl = float((s[:PCA_K] ** 2).sum() / (s**2).sum())
    sig = np.nanstd(ws, axis=0)  # sigma of the unwinsorised window
    good = np.isfinite(sig) & (sig > 1e-8)
    for t in range(p + 1, nxt):
        rt = r[t, sel]
        v = np.isfinite(rt) & good
        if v.sum() < 100:
            continue
        zt = rt[v] / sig[v]
        coef, *_ = np.linalg.lstsq(load[v], zt, rcond=None)
        res = sig[v] * (zt - load[v] @ coef)
        row = np.full(len(sel), np.nan)
        row[v] = res
        e_pca[t, sel] = row.astype("float32")
    return expl


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    syms = master_symbols()
    log(f"master symbols {len(syms)}")
    px = PricePanel.from_dir(symbols=[s for s in syms if s not in HEDGE_ETFS], load_open=False)
    dates, cols = px.dates, px.symbols
    assert set(cols) >= set(syms), "missing master symbols in price panel"
    cols = pd.Index(sorted(set(syms)))
    c = px.frame("close").reindex(columns=cols).to_numpy("float64")
    del px
    T, N = c.shape
    log(f"close {c.shape}")
    r = np.full((T, N), np.nan, dtype="float32")
    with np.errstate(invalid="ignore", divide="ignore"):
        r[1:] = c[1:] / c[:-1] - 1.0
    np.save(OUT / "close.npy", c.astype("float32"))
    del c
    r[~np.isfinite(r)] = np.nan
    attrs = load_attr(dates, cols, ["adv_rank", "ff48", "beta_252_spy"])
    adv_rank = attrs["adv_rank"]
    spy = int(cols.get_loc("SPY"))
    r_spy = r[:, spy].astype("float64")

    # ---- beta residual
    beta = np.where(np.isfinite(attrs["beta_252_spy"]), attrs["beta_252_spy"], 1.0).clip(-0.5, 3.0)
    e_beta = np.full((T, N), np.nan, dtype="float32")
    e_beta[1:] = (r[1:].astype("float64") - beta[:-1] * r_spy[1:, None]).astype("float32")
    np.save(OUT / "e_beta.npy", e_beta)
    del e_beta, beta
    np.save(OUT / "beta_252_spy.npy", attrs.pop("beta_252_spy"))
    log("e_beta done")

    # ---- industry residual (group means over the top-3000 universe)
    ff = attrs["ff48"]
    e_ind = np.full((T, N), np.nan, dtype="float32")
    for t in range(1, T):
        rt = r[t]
        valid = np.isfinite(rt)
        uni = valid & (adv_rank[t] <= 3000)
        if uni.sum() < 50:
            continue
        mkt = float(rt[uni].mean())
        g = np.where(np.isfinite(ff[t]), ff[t], -1).astype(int) + 1  # 0 = no group
        gm = np.full(50, mkt)
        cnt = np.bincount(g[uni], minlength=50)
        sm = np.bincount(g[uni], weights=rt[uni], minlength=50)
        ok = (cnt >= 5) & (np.arange(50) > 0)
        gm[ok] = sm[ok] / cnt[ok]
        e_ind[t] = np.where(valid, rt - gm[g], np.nan).astype("float32")
    np.save(OUT / "e_ind.npy", e_ind)
    del e_ind
    log("e_ind done")

    # ---- PCA residual
    e_pca = np.full((T, N), np.nan, dtype="float32")
    explained = {}
    refresh = list(range(PCA_WINDOW, T, PCA_REFRESH))
    for k, p in enumerate(refresh):
        nxt = refresh[k + 1] if k + 1 < len(refresh) else T
        w = r[p - PCA_WINDOW + 1 : p + 1]
        nobs = np.isfinite(w).sum(axis=0)
        sel = np.flatnonzero((adv_rank[p] <= PCA_SET_RANK) & (nobs >= PCA_MIN_OBS))
        if len(sel) < 200:
            continue
        explained[int(p)] = pca_block(r, w, sel, p, nxt, e_pca)
        if k % 10 == 0:
            log(
                f"pca refresh {k + 1}/{len(refresh)} pos {p} n={len(sel)} expl={explained[int(p)]:.3f}"
            )
    np.save(OUT / "e_pca.npy", e_pca)
    del e_pca, r
    log("e_pca done")

    # ---- attributes
    np.save(OUT / "adv_rank.npy", adv_rank)
    np.save(OUT / "ff48.npy", attrs["ff48"])
    attrs2 = load_attr(
        dates, cols, ["dollar_adv_21", "mcap", "vol_21", "idio_vol_63", "is_tradeable"]
    )
    for n in ("dollar_adv_21", "vol_21", "idio_vol_63", "is_tradeable"):
        np.save(OUT / f"{n}.npy", attrs2[n])
    with np.errstate(invalid="ignore", divide="ignore"):
        np.save(OUT / "turnover.npy", (attrs2["dollar_adv_21"] / attrs2["mcap"]).astype("float32"))
    del attrs2

    # ---- short-eligibility proxy (adv_rank <= 2000, close >= 10, no reverse split in 252 sessions)
    ever = np.flatnonzero(np.nanmin(np.where(np.isfinite(adv_rank), adv_rank, 1e9), axis=0) <= 2000)
    px2 = PricePanel.from_dir(
        symbols=[cols[j] for j in ever if cols[j] not in HEDGE_ETFS], load_open=True
    )
    sub_cols = pd.Index([cols[j] for j in ever])
    o = px2.frame("open").reindex(columns=sub_cols).to_numpy("float64")
    cl = px2.frame("close").reindex(columns=sub_cols).to_numpy("float64")
    del px2
    with np.errstate(invalid="ignore", divide="ignore"):
        ratio = np.full_like(cl, np.nan)
        ratio[1:] = o[1:] / cl[:-1]
    flag = borrow.is_reverse_split_ratio(ratio)
    del ratio, o
    cs = np.cumsum(flag, axis=0, dtype=np.int32)
    lagged = np.zeros_like(cs)
    lagged[borrow.RS_WINDOW :] = cs[: -borrow.RS_WINDOW]
    rs = (cs - lagged) > 0
    elig = np.zeros((T, N), dtype=bool)
    elig[:, ever] = borrow.rule_mask(adv_rank[:, ever], cl, rs, None)
    np.save(OUT / "short_elig.npy", elig)
    del cl, flag, cs, lagged, rs
    log(f"short_elig share {elig.mean():.3f}")

    # ---- news
    news1d = np.full((T, N), np.nan, dtype="float32")
    surge = np.full((T, N), np.nan, dtype="float32")
    row = np.zeros((T, N), dtype=bool)
    pos = {s: j for j, s in enumerate(cols)}
    for y in (2024, 2025, 2026):
        f = pd.read_parquet(
            ROOT / f"data/features/news_attention/{y}.parquet",
            columns=["symbol", "trade_date", "visible_at", "news_count_1d", "attention_surge_5d"],
        )
        # point in time: only rows visible by the 16:00 ET close of their trade date (visible_at is 09:30 ET)
        close_utc = pd.DatetimeIndex(f["trade_date"]).tz_localize(
            "America/New_York"
        ) + pd.Timedelta(hours=16)
        f = f[pd.DatetimeIndex(f["visible_at"]) <= close_utc.tz_convert("UTC")]
        rr = dates.get_indexer(pd.DatetimeIndex(f["trade_date"]))
        kk = np.array([pos.get(s, -1) for s in f["symbol"].astype(str)])
        ok = (rr >= 0) & (kk >= 0)
        news1d[rr[ok], kk[ok]] = f["news_count_1d"].to_numpy("float32")[ok]
        surge[rr[ok], kk[ok]] = f["attention_surge_5d"].to_numpy("float32")[ok]
        row[rr[ok], kk[ok]] = True
    np.save(OUT / "news_1d.npy", news1d)
    np.save(OUT / "news_surge.npy", surge)
    np.save(OUT / "news_row.npy", row)

    # ---- VIX
    from scripts import analyze_equity_book_regimes as reg

    vix = reg.load_vix()["VIXCLS"].reindex(dates).ffill(limit=3).to_numpy("float64")
    np.save(OUT / "vix.npy", vix)

    meta = {
        "built_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "dates": [d.strftime("%Y-%m-%d") for d in dates],
        "symbols": list(cols),
        "pca_refresh_positions": refresh,
        "pca_explained_share_top10": explained,
        "shape": [T, N],
        "contract": "reports/research/iterations/t20261006_22_st_reversal/contract.md",
    }
    (OUT / "meta.json").write_text(json.dumps(meta))
    log("done")


if __name__ == "__main__":
    main()
