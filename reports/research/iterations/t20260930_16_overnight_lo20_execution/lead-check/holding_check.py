"""Lead check 2026-09-30 13:07: ON252_P500 top-20 -- overnight-only vs close-to-close vs open-to-open holding.
Reads only the T-35 panel cache (contaminated windows, diagnostic, not a gate)."""
import json, sys
import numpy as np, pandas as pd
P = "reports/research/iterations/t20260929_35_overnight_persistence/cache/panel.parquet"
df = pd.read_parquet(P, columns=["date", "symbol", "p500", "on252", "r", "idn"])
df["symbol"] = df["symbol"].astype(str)
dates = pd.DatetimeIndex(sorted(df["date"].unique()))
di = {d: i for i, d in enumerate(dates)}
df["di"] = df["date"].map(di).astype(np.int32)
syms = sorted(df["symbol"].unique()); si = {s: i for i, s in enumerate(syms)}
df["si"] = df["symbol"].map(si).astype(np.int32)
R = np.full((len(dates), len(syms)), np.nan, np.float32); I = R.copy()
R[df["di"].to_numpy(), df["si"].to_numpy()] = df["r"].to_numpy("float32")
I[df["di"].to_numpy(), df["si"].to_numpy()] = df["idn"].to_numpy("float32")
N = 20
rows = []
prev = set()
for i, g in df.groupby("di", sort=True):
    m = g["p500"].to_numpy() & np.isfinite(g["on252"].to_numpy()) & np.isfinite(g["r"].to_numpy())
    if m.sum() < 40:
        rows.append((i, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan)); prev = set(); continue
    gg = g[m]
    order = np.argsort(gg["on252"].to_numpy("float64"), kind="stable")
    sel = gg["si"].to_numpy()[order[-N:]]
    on = np.nanmean(R[i, sel]); idn = np.nanmean(I[i, sel])
    c2c = np.nanmean((1 + R[i, sel]) * (1 + I[i, sel]) - 1)
    o2o = np.nan; miss = np.nan
    if i + 1 < len(dates):
        v = (1 + I[i, sel]) * (1 + R[i + 1, sel]) - 1
        miss = float(np.mean(~np.isfinite(v))); o2o = np.nanmean(v)
    pool_on = np.nanmean(gg["r"].to_numpy("float64"))
    pool_c2c = np.nanmean((1 + gg["r"].to_numpy("float64")) * (1 + gg["idn"].to_numpy("float64")) - 1)
    s = set(sel.tolist()); to = (len(s - prev) / N) if prev else np.nan; prev = s
    rows.append((i, on, idn, c2c, o2o, miss, to, pool_on, pool_c2c))
res = pd.DataFrame(rows, columns=["di", "on", "idn", "c2c", "o2o", "o2o_miss", "turnover", "pool_on", "pool_c2c"])
res.index = dates[res["di"].to_numpy()]
W = {"main": ("2024-01-08", "2026-09-29"), "selection": ("2023-09-18", "2025-12-31"), "stress": ("2016-05-02", "2023-08-31")}
def st(x):
    x = x.dropna(); 
    return {"mean_bp": round(x.mean() * 1e4, 2), "sharpe": round(x.mean() / x.std() * np.sqrt(252), 2), "n": int(len(x))}
out = {}
for w, (a, b) in W.items():
    s = res.loc[a:b]
    to = s["turnover"].mean()
    d = {k: st(s[k]) for k in ["on", "idn", "c2c", "o2o", "pool_on", "pool_c2c"]}
    d["turnover_mean"] = round(float(to), 4)
    d["o2o_net10"] = st(s["o2o"] - s["turnover"].fillna(0) * 2 * 10e-4)
    d["o2o_net20"] = st(s["o2o"] - s["turnover"].fillna(0) * 2 * 20e-4)
    d["on_auction1x"] = st(s["on"] - 4e-4); d["on_auction2x"] = st(s["on"] - 8e-4)
    d["o2o_miss"] = round(float(s["o2o_miss"].mean()), 4)
    out[w] = d
yr = res.groupby(res.index.year).agg({"on": "mean", "idn": "mean", "c2c": "mean", "o2o": "mean", "pool_c2c": "mean"}) * 1e4
out["by_year_bp"] = yr.round(1).to_dict(orient="index")
res.to_parquet("/tmp/lead1307/holding_series.parquet")
print(json.dumps(out, indent=0, default=str))
