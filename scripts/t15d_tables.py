# ruff: noqa: E501
"""Print markdown tables from results_d.json (helper for report_d.md; prints to stdout only)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "reports/research/iterations/t20261006_15_intraday_rules/results_d.json"


def f(x, nd=2):
    return "n/a" if x is None else f"{x:.{nd}f}"


def main() -> int:
    r = json.loads(RES.read_text())
    pts = r["main_grid_points"]
    print(
        "| 篮子 | 周期 | 方向 | 信号 | 近期净夏普 | 毛夏普 | 每笔毛利bp | 成本占毛利 | 笔/天 | 随机方向安慰剂(净/毛) | 同时段随机日安慰剂(净/毛) | 2倍成本净夏普 | 2016-23净夏普 |"
    )
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for k, p in pts.items():
        pl = p["placebo_random_direction"]
        rd = p["placebo_same_slot_random_day"]
        print(
            f"| {p['basket']} | {p['period']} | {p['direction']} | {p['signal']} | {f(p['sr_net_recent']['x1.0'])} | {f(p['sr_gross_recent'])} | {f(p['gross_bp_per_trade'])} | {f(p['cost_share_of_gross'])} | {f(p['trades_per_day'], 3)} | {f(pl['net_pct'])}/{f(pl['gross_pct'])} | {f(rd['net_pct'])}/{f(rd['gross_pct'])} | {f(p['sr_net_recent']['x2.0'])} | {f(p['sr_net_diag_2016_2023'])} |"
        )
    print()
    print("选中规格")
    for b, c in r["selected_candidates"].items():
        print(
            b,
            json.dumps(
                {k: v for k, v in c.items() if k not in ("robustness", "V4")}, ensure_ascii=False
            ),
        )
    print()
    print(
        "| 信息表 | 笔数 | 每笔毛利bp | t(按日聚类) | 对照bp/笔 | 超额bp | 超额分位 | 净夏普 | 毛夏普 |"
    )
    print("|---|---|---|---|---|---|---|---|---|")
    for k, v in r["information_table"].items():
        print(
            f"| {k} | {v['trades_recent']} | {f(v['gross_bp_per_trade'])} | {f(v['t_day_cluster'])} | {f(v['control_same_slot_random_day_bp_per_trade'])} | {f(v['excess_over_control_bp'])} | {f(v['excess_pct_vs_control_distribution'])} | {f(v['sr_net_recent'])} | {f(v['sr_gross_recent'])} |"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
