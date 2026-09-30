import numpy as np, pandas as pd
P = "reports/research/iterations/t20260929_35_overnight_persistence/cache/panel.parquet"
df = pd.read_parquet(P, columns=["date", "symbol", "p500", "on252", "r"])
df = df[(df["date"] >= "2016-05-02")]
df["symbol"] = df["symbol"].astype(str)
recs = []
for d, g in df.groupby("date", sort=True):
    m = g["p500"].to_numpy() & np.isfinite(g["on252"].to_numpy()) & np.isfinite(g["r"].to_numpy())
    if m.sum() < 40: continue
    gg = g[m]; o = np.argsort(gg["on252"].to_numpy("float64"), kind="stable")[-20:]
    sub = gg.iloc[o]
    for s, r in zip(sub["symbol"], sub["r"]): recs.append((d, s, r))
x = pd.DataFrame(recs, columns=["date", "symbol", "r"])
for w, (a, b) in {"main": ("2024-01-08", "2026-09-29"), "stress": ("2016-05-02", "2023-08-31")}.items():
    s = x[(x["date"] >= a) & (x["date"] <= b)]; nd = s["date"].nunique()
    agg = s.groupby("symbol").agg(nights=("r", "size"), sum_r=("r", "sum"))
    agg["share_of_pnl"] = agg["sum_r"] / s["r"].sum(); agg["freq"] = agg["nights"] / nd
    agg = agg.sort_values("sum_r", ascending=False)
    print(f"== {w}: nights {nd}, distinct names {len(agg)}, total mean bp {s['r'].sum()/nd/20*1e4:.1f}")
    print(agg.head(15).round(3).to_string())
    print("top10 share", round(agg["share_of_pnl"].head(10).sum(), 3), "| bottom5:", agg.tail(5).index.tolist())
