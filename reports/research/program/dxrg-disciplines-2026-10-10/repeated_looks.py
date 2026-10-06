"""Repeated-look inflation for daily-read forward monitoring rules (DXRG rule 15).

iid normal daily returns; z_t is the standardized deviation of the running mean
from the null mean, so a single look at any fixed t has the nominal rate.
"""

import json

import numpy as np

rng = np.random.default_rng(20261006)
N, T = 20000, 252
eps = rng.standard_normal((N, T))
t = np.arange(1, T + 1)
z = np.cumsum(eps, axis=1) / np.sqrt(t)  # N(0,1) at every fixed t under the null

out = {"paths": N, "seed": 20261006, "rules": {}}
for horizon in (63, 126, 252):
    w = slice(9, horizon)  # read daily from session 10 on (L1 needs >= 10 sessions)
    out["rules"][f"z<-2 ever, sessions 10..{horizon}"] = float((z[:, w].min(axis=1) < -2).mean())
    w21 = slice(20, horizon)
    out["rules"][f"PSR>=0.9 ever under SR=0, sessions 21..{horizon}"] = float(
        (z[:, w21].max(axis=1) >= 1.2816).mean()
    )

# Drawdown rule: halve when MDD(t) exceeds the 95% quantile of MDD at elapsed t
# (Kaminski-Lo style boundary), daily vol 1%, annual Sharpe 0.8 under the null.
mu, sd = 0.8 / np.sqrt(252) * 0.01, 0.01
r = mu + sd * rng.standard_normal((N, T))
logeq = np.cumsum(np.log1p(r), axis=1)
peak = np.maximum.accumulate(np.maximum(logeq, 0.0), axis=1)
mdd = np.maximum.accumulate(peak - logeq, axis=1)
half = N // 2  # boundary from one half, crossing rate on the other half
q95 = np.quantile(mdd[:half], 0.95, axis=0)
q99 = np.quantile(mdd[:half], 0.99, axis=0)
for horizon in (63, 126, 252):
    w = slice(9, horizon)
    test = mdd[half:, w]
    out["rules"][f"MDD>q95(t) ever, sessions 10..{horizon}"] = float((test > q95[w]).any(axis=1).mean())
    out["rules"][f"MDD>q99(t) ever, sessions 10..{horizon}"] = float((test > q99[w]).any(axis=1).mean())

out["single_look_nominal"] = {"z<-2": 0.0228, "PSR>=0.9 under SR=0": 0.10, "MDD>q95": 0.05, "MDD>q99": 0.01}
print(json.dumps(out, indent=1))
with open("reports/research/program/dxrg-disciplines-2026-10-10/repeated_looks.json", "w") as f:
    json.dump(out, f, indent=1)
