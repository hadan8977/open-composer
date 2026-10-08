#!/usr/bin/env python3
# ruff: noqa: E501
"""T-20261007-01 F axis: FCX = (60 * FC_EW + sum_k s_k z_k) / 67 over the 7 intraday daily features.

z_k: per date, rank-normal of feature k over the rows of the FC_EW store of that date, missing = 0.
s_k: sign of the stress-window (2017-10-02..2023-08-31) mean daily rank IC between z_k(t) and the lag-2
label (close(t+1) -> close(t+2) return, industry-demeaned); no recent-window number is computed here.
Features come from data/features/intraday_daily (2017..2026, rows up to 2026-09-04 for 2026) and
data/research/t0701_store/intraday_daily_2026_09.parquet (rows after 2026-09-04, cut at 2026-09-17).
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import ndtri

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FEATS = (
    "overnight_return",
    "intraday_return",
    "intraday_amplitude",
    "open_30min_volume_share",
    "close_30min_volume_share",
    "vwap_deviation",
    "intraday_skew",
)
STORE = ROOT / "data/research/t0701_store"
STRESS = ("2017-10-02", "2023-08-31")
LAST = "2026-09-17"


def rn(x: np.ndarray) -> np.ndarray:
    """rank-normal, missing -> 0 (as P1 stage 0 inputs)."""
    fin = np.isfinite(x)
    out = np.zeros(len(x))
    n = int(fin.sum())
    if n:
        r = pd.Series(x[fin]).rank(method="average").to_numpy()
        out[fin] = ndtri((r - 0.5) / n)
    return out


def main() -> None:
    from scripts import realism_ladder_book_ls as T25

    t0 = time.time()
    fc = pd.read_parquet(STORE / "fc_ew.parquet")
    fc["trade_date"] = pd.to_datetime(fc["trade_date"])
    frames = []
    for y in range(2017, 2027):
        df = pd.read_parquet(
            ROOT / f"data/features/intraday_daily/{y}.parquet",
            columns=["symbol", "trade_date", *FEATS],
        )
        frames.append(df)
    feat = pd.concat(frames, ignore_index=True)
    feat["trade_date"] = pd.to_datetime(feat["trade_date"])
    feat = feat[feat["trade_date"] <= pd.Timestamp("2026-09-04")]
    sep = pd.read_parquet(
        STORE / "intraday_daily_2026_09.parquet", columns=["symbol", "trade_date", *FEATS]
    )
    sep["trade_date"] = pd.to_datetime(sep["trade_date"])
    sep = sep[
        (sep["trade_date"] > pd.Timestamp("2026-09-04")) & (sep["trade_date"] <= pd.Timestamp(LAST))
    ]
    feat = pd.concat([feat, sep], ignore_index=True).drop_duplicates(
        ["symbol", "trade_date"], keep="last"
    )
    m = fc.merge(feat, on=["symbol", "trade_date"], how="left")
    print(
        "merged",
        len(m),
        "feature coverage",
        {k: round(float(m[k].notna().mean()), 3) for k in FEATS},
        flush=True,
    )
    m = m.sort_values(["trade_date", "symbol"]).reset_index(drop=True)
    d = m["trade_date"].to_numpy()
    cut = np.flatnonzero(d[1:] != d[:-1]) + 1
    starts = np.concatenate([[0], cut])
    ends = np.concatenate([cut, [len(m)]])
    Z = np.zeros((len(m), len(FEATS)))
    for a, b in zip(starts, ends, strict=True):
        for j, k in enumerate(FEATS):
            Z[a:b, j] = rn(m[k].to_numpy("float64")[a:b])
    # signs from the stress window only
    ctx = T25.Context()
    px = ctx.px
    dates = pd.DatetimeIndex(m["trade_date"].iloc[starts])
    ic_sum = np.zeros(len(FEATS))
    n_ic = np.zeros(len(FEATS))
    for a, b, t in zip(starts, ends, dates, strict=True):
        if t < pd.Timestamp(STRESS[0]) or t > pd.Timestamp(STRESS[1]):
            continue
        p = int(px.dates.get_loc(t))
        idx = px.symbols.get_indexer(m["symbol"].iloc[a:b])
        ok = idx >= 0
        r = np.full(b - a, np.nan)
        r[ok] = px.C[p + 2, idx[ok]] / px.C[p + 1, idx[ok]] - 1.0
        ind = ctx.sig.at(t)["ind_code"].reindex(m["symbol"].iloc[a:b]).fillna(-1).to_numpy()
        s = pd.Series(r)
        r_dm = (s - s.groupby(ind).transform("mean")).to_numpy()
        good = np.isfinite(r_dm)
        if good.sum() < 50:
            continue
        rr = pd.Series(r_dm[good]).rank().to_numpy()
        for j in range(len(FEATS)):
            zj = Z[a:b, j][good]
            if np.ptp(zj) == 0:
                continue
            ic_sum[j] += float(np.corrcoef(pd.Series(zj).rank().to_numpy(), rr)[0, 1])
            n_ic[j] += 1
    ic_mean = ic_sum / np.maximum(n_ic, 1)
    signs = np.where(ic_mean > 0, 1.0, -1.0)
    fcx = (60.0 * m["fc_ew"].to_numpy("float64") + Z @ signs) / 67.0
    out = pd.DataFrame(
        {"trade_date": m["trade_date"], "symbol": m["symbol"], "fcx": fcx.astype("float32")}
    )
    out.to_parquet(STORE / "fcx.parquet", index=False)
    meta = {
        "features": list(FEATS),
        "stress_window": STRESS,
        "stress_mean_rank_ic_lag2": dict(zip(FEATS, ic_mean.tolist(), strict=True)),
        "stress_days": dict(zip(FEATS, n_ic.tolist(), strict=True)),
        "signs": dict(zip(FEATS, signs.tolist(), strict=True)),
        "rows": int(len(out)),
        "last_date": str(out["trade_date"].max().date()),
        "seconds": round(time.time() - t0, 1),
    }
    (STORE / "fcx_meta.json").write_text(json.dumps(meta, indent=1))
    print(json.dumps(meta), flush=True)


if __name__ == "__main__":
    main()
