import pandas as pd, numpy as np
res = pd.read_parquet("/tmp/lead1307/holding_series.parquet")
W = {"main": ("2024-01-08", "2026-09-29"), "selection": ("2023-09-18", "2025-12-31"), "stress": ("2016-05-02", "2023-08-31"), "contam2026": ("2026-01-02","2026-09-17")}
def st(x):
    x = x.dropna(); return f"{x.mean()*1e4:6.1f}bp sh {x.mean()/x.std()*np.sqrt(252):5.2f} vol {x.std()*np.sqrt(252)*100:5.1f}%"
for w,(a,b) in W.items():
    s = res.loc[a:b]; to = s["turnover"].fillna(0)
    print(f"== {w} n={len(s.dropna(subset=['on']))} turnover/day {s['turnover'].mean():.3f} o2o_miss {s['o2o_miss'].mean():.4f}")
    for k in ["on","idn","c2c","o2o","pool_on","pool_c2c"]: print(f"  {k:9s} {st(s[k])}")
    print(f"  o2o_net10 {st(s['o2o']-to*2*10e-4)}   o2o_net20 {st(s['o2o']-to*2*20e-4)}")
    print(f"  on_auc2x  {st(s['on']-8e-4)}   o2o-pool_c2c {st(s['o2o']-s['pool_c2c'])}")
