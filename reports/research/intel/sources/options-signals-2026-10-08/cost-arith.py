"""Arithmetic only: net edge of a long-short book after per-side costs. Inputs are stated assumptions, not estimates of our fills."""
import json
from math import sqrt
res = {}
# gross per 4-week cycle, bp (CW replication thesis 2011-15, 4-factor alpha, 4-week hold: 73bp); MPP: abnormal return shrinks to ~1/3 after borrow fee
for name, gross in (("CW_thesis_4w_gross_bp", 73.0), ("CW_thesis_x_one_third_after_borrow_bp", 73.0 / 3)):
    for c in (5, 10, 20):
        for turnover in (1.0, 0.6):
            # per cycle: both legs, enter+exit at turnover share, c bp per side
            cost = 2 * 2 * c * turnover
            res[f"{name}|c={c}bp|turnover={turnover}"] = {"gross_bp_per_4w": round(gross, 1), "cost_bp_per_4w": cost, "net_bp_per_4w": round(gross - cost, 1)}
# 1-week hold, gross 19 bp (CW thesis weekly 4-factor alpha), cost per week
for c in (5, 10, 20):
    for turnover in (1.0, 0.6):
        cost = 2 * 2 * c * turnover
        res[f"CW_thesis_1w_gross_19bp|c={c}bp|turnover={turnover}"] = {"gross_bp_per_1w": 19.0, "cost_bp_per_1w": cost, "net_bp_per_1w": round(19.0 - cost, 1)}
json.dump(res, open("cost-arith-output.json", "w"), indent=1)
for k, v in res.items():
    print(k, v)
