#!/usr/bin/env python3
# ruff: noqa: E501
"""T-20261007-02 post-run diagnostic (report only, written after results, changes no verdict): does the mapped ETF move
in the hour BEFORE the odds point (contemporaneous check of the theme sign mapping)? Not tradable."""

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, "scripts")
sys.path.insert(0, ".")
import t0702_pm_grid as G
import t0702_run as R

R.load_px()
jumps = R.load_j_jumps(3.0)
eps, _, _ = R.j_episodes(jumps, 3.0)
rows = []
for _, e in eps.iterrows():
    _, sign, etf, _x = G.THEMES[e.theme]
    d = int(np.sign(e.dp)) * sign
    tm = int(e.t1 // 60)
    a = R.bar_open(etf, tm - 60)
    b = R.bar_open(etf, tm)
    if a and b and b[1] > a[1]:
        rows.append(
            {"theme": e.theme, "r": d * math.log(b[0] / a[0]) * 1e4, "date": str(R.et_date(tm))}
        )
df = pd.DataFrame(rows)


def tstat(g):
    by = g.groupby("date").r.mean()
    return float(by.mean() / (by.std(ddof=1) / math.sqrt(len(by)))) if len(by) > 2 else None


out = {"all": {"n": int(len(df)), "mean_bp": float(df.r.mean()), "t_date_clustered": tstat(df)}}
for th, g in df.groupby("theme"):
    out[th] = {"n": int(len(g)), "mean_bp": float(g.r.mean()), "t_date_clustered": tstat(g)}
Path(
    "reports/research/iterations/t20261007_02_pm_event_study/j_contemporaneous_diag.json"
).write_text(json.dumps(out, indent=2) + "\n")
print(json.dumps(out, indent=1))
