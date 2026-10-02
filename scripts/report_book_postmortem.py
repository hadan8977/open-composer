# ruff: noqa: E501
"""Part 3 additions and Part 4 of the equity book v1 post-mortem (T-20261001-19).

Reads ``postmortem/results.json`` (sections ``ladder``, ``tc``, ``attrib`` written by
``scripts/eval_book_postmortem.py``) and the offset-blended attribution frames, then

* adds the style-versus-specific split for L0 and L1 (section ``style_vs_specific``);
* independently recomputes numbers from the raw files with plain numpy (section ``recompute``) and
  checks them against the ladder at 1e-9;
* writes ``postmortem/report.md`` (Chinese, facts and the mechanical D1-D3 booleans only).

    scripts/run_capped.sh --mem 1.6G -- uv run python scripts/report_book_postmortem.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import eval_book_postmortem as ep  # noqa: E402

PM_DIR = ep.PM_DIR
RESULTS = ep.RESULTS
WINDOWS = ep.WINDOWS
RUNGS_LIN = ("L0", "L1")
SHOWN_WINDOWS = ("A", "B", "stress")
TOL = 1e-9
MODAL_BILLED = None  # filled from modal_budget status text by the caller (documented in report)


def style_vs_specific(styles: list[str]) -> dict[str, Any]:
    """Annualised contribution and Sharpe of the summed style components and of the specific
    component, plus market, industry and the ETF leg, from the offset-blended attribution frames."""
    out: dict[str, Any] = {}
    for rung in RUNGS_LIN:
        for v in ep.VARIANTS:
            df = pd.read_parquet(PM_DIR / f"attrib_{rung}_{v}.parquet")
            df["style_total"] = df[[f"style_{s}" for s in styles]].sum(axis=1)
            block: dict[str, Any] = {}
            for w, (a, b) in WINDOWS.items():
                sub = df[(df.index >= a) & (df.index <= b)]
                blk: dict[str, Any] = {}
                for c in (
                    "market",
                    "industry",
                    "style_total",
                    "specific",
                    "etf_leg",
                    "tbill_leg",
                    "costs",
                    "unreconciled",
                    "gross_reported",
                    "net_reported",
                ):
                    sd = float(sub[c].std(ddof=1))
                    blk[c] = {
                        "ann_contribution": float(sub[c].mean() * ep.TRADING_DAYS),
                        "sharpe": float(sub[c].mean() / sd * np.sqrt(ep.TRADING_DAYS))
                        if sd > 0
                        else float("nan"),
                    }
                for s in styles:
                    blk[f"style_{s}"] = {
                        "ann_contribution": float(sub[f"style_{s}"].mean() * ep.TRADING_DAYS)
                    }
                block[w] = blk
            out[f"{rung}_{v}"] = block
    return out


def independent_recompute(res: dict[str, Any]) -> dict[str, Any]:
    """Recompute, with numpy and raw parquet reads only (none of the eval helpers), the median over
    offsets of the A-window gross Sharpe of L0 and L1 for M0_A, and the D1 change; compare with
    ``results.json``."""
    etf = pd.read_parquet(
        ROOT / "data/research/equity_book/etf_daily.parquet",
        columns=["trade_date", "symbol", "close"],
    )
    bil = etf[etf["symbol"] == "BIL"].sort_values("trade_date")
    bil_ret = bil.set_index(pd.to_datetime(bil["trade_date"]))["close"].pct_change().fillna(0.0)
    a, b = WINDOWS["A"]

    def gross_sharpe(path: Path) -> float:
        d = pd.read_parquet(path / "daily.parquet")
        idx = pd.to_datetime(d["trade_date"])
        g = pd.Series(d["gross"].to_numpy("float64"), index=idx)
        g = g[(g.index >= a) & (g.index <= b)].dropna()
        x = (g - bil_ret.reindex(g.index).fillna(0.0)).to_numpy()
        return float(x.mean() / x.std(ddof=1) * np.sqrt(252.0))

    med: dict[str, float] = {}
    for rung in RUNGS_LIN:
        vals = [gross_sharpe(ep.path_dir(rung, "M0_A", k)) for k in ep.OFFSETS]
        med[rung] = float(np.median(vals))
    stored = {r: float(res["ladder"]["median"][r]["M0_A"]["gross_sharpe"]["A"]) for r in RUNGS_LIN}
    d1_recomputed = med["L1"] - med["L0"]
    d1_stored = float(res["ladder"]["decisions"]["D1"]["M0_A"]["gross_A_change"])
    rows = {
        "L0_M0_A_gross_A_median": {"recomputed": med["L0"], "results_json": stored["L0"]},
        "L1_M0_A_gross_A_median": {"recomputed": med["L1"], "results_json": stored["L1"]},
        "D1_M0_A_gross_A_change": {"recomputed": d1_recomputed, "results_json": d1_stored},
    }
    for r in rows.values():
        r["abs_diff"] = abs(r["recomputed"] - r["results_json"])
        r["match_1e-9"] = bool(r["abs_diff"] <= TOL)
    return {
        "method": "numpy mean/std(ddof=1)*sqrt(252) of daily gross minus BIL return, A window, "
        "raw daily.parquet and etf_daily.parquet; no eval helpers",
        "numbers": rows,
        "all_match": bool(all(r["match_1e-9"] for r in rows.values())),
    }


def f2(x: Any) -> str:
    return "n/a" if x is None or not np.isfinite(x) else f"{x:+.2f}"


def f3(x: Any) -> str:
    return "n/a" if x is None or not np.isfinite(x) else f"{x:.3f}"


def pct(x: Any) -> str:
    return "n/a" if x is None or not np.isfinite(x) else f"{100 * x:.1f}%"


def build_report(res: dict[str, Any], styles: list[str], now: str) -> str:
    lad = res["ladder"]
    med = lad["median"]
    dec = lad["decisions"]
    sig = lad["signal_reference"]
    tc = res["tc"]["median"]
    svs = res["style_vs_specific"]
    rc = res["recompute"]
    L: list[str] = []
    ap = L.append
    ap("# 账本 v1 事后分析：构建阶梯、转移系数与盈亏归因（T-20261001-19）")
    ap("")
    ap(f"生成时间 {now}（UTC）。预注册：`postmortem/prereg.md`（commit 3911971，未改动）。")
    ap("所有数字来自 `postmortem/results.json`；本报告只陈述事实与机械判定，不含结论性措辞。")
    ap("")
    ap("## 0. 范围与口径")
    ap(
        "- 配置：L0 = v1 原样（T-08 收盘成交路径，复用）；L1 = L0 去掉风格上限（`style_cap=None`，"
        "size 仍 0.10，beta 0.02，行业 0.01，单名 1%，事前波动 5%，总杠杆 1.0）；L2c = L1 + 开盘成交 + "
        "开盘成本快照；L2a = L1 + 开盘成交 + 收盘成本快照（乐观上界）。变体 M0_A、M1_C，偏移 0–4，"
        "共 30 条新路径（Modal，全部完成，见 `run-manifest.json`：150 个文件，缺失 0，不完整 0）。"
    )
    ap(
        "- 窗口：A 2024-01-08..2026-06-30；B 2026-07-01..2026-09-17；stress 2017-10-02..2023-08-31。"
        "净夏普 = 每个偏移取 min(plain, cash-aligned) 后再取 5 个偏移的中位数；毛夏普同样取中位数。"
    )
    ap(
        "- 数据口径提醒：2026-10-02 的主审轮发现 SIP 价格存档存在复权接缝（拆股/分红后供应商改写历史，"
        "例如 APH 在 2026-08-27 出现虚假的 −50%，9 月更多）。本分析沿用 v1 使用的同一研究快照以保持可比，"
        "B 窗口的数字可能带有少量接缝误差；未做任何数据修复。"
    )
    ap("")
    ap("## 1. 阶梯表（偏移中位数）")
    ap("")
    ap(
        "| 变体 | 配置 | 净 A | 净 B | 净 stress | 毛 A | 毛 B | 毛 stress | 净超额 A | 波动 A | 最大回撤 A | "
        "OLS beta A | Dimson beta A | 单边换手/年 A |"
    )
    ap("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for v in ep.VARIANTS:
        for r in ep.RUNGS:
            m = med[r][v]
            wa = m["windows"]["A"]
            ap(
                f"| {v} | {r} | {f2(m['net_sharpe']['A'])} | {f2(m['net_sharpe']['B'])} | "
                f"{f2(m['net_sharpe']['stress'])} | {f2(m['gross_sharpe']['A'])} | "
                f"{f2(m['gross_sharpe']['B'])} | {f2(m['gross_sharpe']['stress'])} | "
                f"{pct(wa['net_ann_excess'])} | {pct(wa['vol'])} | {pct(wa['max_dd'])} | "
                f"{f2(wa['beta_ols'])} | {f2(wa['beta_dimson'])} | {wa['turnover_one_sided_ann']:.1f} |"
            )
    ap("")
    ap("成本（bp/年，A 窗口，偏移中位数）：")
    ap("")
    ap("| 变体 | 配置 | 价差 | 冲击 | 手续费 | 借券 | 融资 | 合计 |")
    ap("|---|---|---|---|---|---|---|---|")
    for v in ep.VARIANTS:
        for r in ep.RUNGS:
            c = med[r][v]["windows"]["A"]["costs_bp_per_year"]
            ap(
                f"| {v} | {r} | {c['spread']:.1f} | {c['impact']:.1f} | {c['fees']:.1f} | "
                f"{c['borrow']:.1f} | {c['margin']:.1f} | {c['total']:.1f} |"
            )
    ap("")
    ap("B 与 stress 窗口的成本（bp/年，合计）：")
    ap("")
    ap("| 变体 | 配置 | B 合计 | stress 合计 |")
    ap("|---|---|---|---|")
    for v in ep.VARIANTS:
        for r in ep.RUNGS:
            w = med[r][v]["windows"]
            ap(
                f"| {v} | {r} | {w['B']['costs_bp_per_year']['total']:.1f} | "
                f"{w['stress']['costs_bp_per_year']['total']:.1f} |"
            )
    ap("")
    ap("## 1b. 风格收益 vs 特异收益（L0 与 L1，A、B、stress；年化贡献 / 夏普）")
    ap("")
    ap(
        "风格合计 = 9 个风险模型风格因子的贡献之和（使用不晚于前一交易日的最近一次保存的暴露）；特异 = 股票账户收益减去市场、行业、风格因子部分。国债腿、成本等见第 6 节。"
    )
    ap("")
    ap("| 变体 | 配置 | 窗口 | 风格合计 | 特异 | 风格夏普 | 特异夏普 |")
    ap("|---|---|---|---|---|---|---|")
    for v in ep.VARIANTS:
        for r in RUNGS_LIN:
            for w in SHOWN_WINDOWS:
                b = svs[f"{r}_{v}"][w]
                ap(
                    f"| {v} | {r} | {w} | {pct(b['style_total']['ann_contribution'])} | "
                    f"{pct(b['specific']['ann_contribution'])} | {f2(b['style_total']['sharpe'])} | "
                    f"{f2(b['specific']['sharpe'])} |"
                )
    ap("")
    ap("## 2. 机械判定 D1、D2、D3")
    ap("")
    ap("| 规则 | M0_A | M1_C | 两个变体都成立 |")
    ap("|---|---|---|---|")
    d1, d2, d2a, d3 = dec["D1"], dec["D2"], dec["D2a"], dec["D3"]
    ap(
        f"| D1（L1−L0 毛夏普 A ≥ +0.30 且 stress ≥ −0.30） | A {f2(d1['M0_A']['gross_A_change'])} / "
        f"stress {f2(d1['M0_A']['gross_stress_change'])} → {d1['M0_A']['pass']} | "
        f"A {f2(d1['M1_C']['gross_A_change'])} / stress {f2(d1['M1_C']['gross_stress_change'])} → "
        f"{d1['M1_C']['pass']} | {d1['both_variants']} |"
    )
    ap(
        f"| D2（L2c−L1 净夏普 A ≥ +0.15 且 stress ≥ 0） | A {f2(d2['M0_A']['net_A_change'])} / "
        f"stress {f2(d2['M0_A']['net_stress_change'])} → {d2['M0_A']['pass']} | "
        f"A {f2(d2['M1_C']['net_A_change'])} / stress {f2(d2['M1_C']['net_stress_change'])} → "
        f"{d2['M1_C']['pass']} | {d2['both_variants']} |"
    )
    ap(
        f"| D2a（同上，L2a 代替 L2c） | A {f2(d2a['M0_A']['net_A_change'])} / "
        f"stress {f2(d2a['M0_A']['net_stress_change'])} → {d2a['M0_A']['pass']} | "
        f"A {f2(d2a['M1_C']['net_A_change'])} / stress {f2(d2a['M1_C']['net_stress_change'])} → "
        f"{d2a['M1_C']['pass']} | {d2a['both_variants']} |"
    )
    ap(
        f"| D3（L1 成本拖累 毛−净 A > 0.30） | {f2(d3['M0_A']['cost_drag_A'])} → {d3['M0_A']['pass']} | "
        f"{f2(d3['M1_C']['cost_drag_A'])} → {d3['M1_C']['pass']} | {d3['both_variants']} |"
    )
    ap("")
    ap(
        "D2 通过只表示成本模型里开盘成交更好；Alpaca 员工称模拟盘 OPG/CLS 订单按报价成交、"
        "不按拍卖价成交（见 `reports/research/intel/sources/book-construction-2026-10-01/INDEX.md`），"
        "所以这不是模拟盘结果。"
    )
    ap("")
    ap("## 3. 信号参照（M0 复合多空，行业去均值，每日，开到开）")
    ap("")
    ap("| 窗口 | 毛夏普（原始 mean/std×√252，不减无风险利率） | 天数 |")
    ap("|---|---|---|")
    for w in ("A", "B", "stress", "anchor"):
        ap(f"| {w} | {f2(sig[w]['sharpe'])} | {sig[w]['n']:.0f} |")
    ap("")
    ap(f"信号序列止于 {sig['last_date']}（`signal_ls_daily.parquet`，列 `m0_composite`）。")
    ap("")
    ap("## 4. 转移系数（TC，L0 与 L1，每次调仓，5 个偏移合并取中位数）")
    ap("")
    ap(
        "TC = 目标股票权重与得分在多头候选池内的横截面皮尔逊相关（未持有 = 0，ETF 与国债排除）；"
        "风险调整 TC = 相关(w×σ_specific, 得分)（Clarke 等 2002 的形式，来自 Ding 2010 转述，"
        "原文未能读取，见 INDEX.md）。"
    )
    ap("")
    ap("| 变体 | 配置 | TC A | TC B | TC stress | 风险调整 TC A | B | stress | 调仓数 A |")
    ap("|---|---|---|---|---|---|---|---|---|")
    for v in ep.VARIANTS:
        for r in RUNGS_LIN:
            t = tc[f"{r}_{v}"]
            ap(
                f"| {v} | {r} | {f3(t['A']['tc'])} | {f3(t['B']['tc'])} | {f3(t['stress']['tc'])} | "
                f"{f3(t['A']['tc_risk_adjusted'])} | {f3(t['B']['tc_risk_adjusted'])} | "
                f"{f3(t['stress']['tc_risk_adjusted'])} | {t['A']['n']} |"
            )
    ap("")
    ap("## 5. 风格约束与风格暴露（A 窗口，目标暴露，偏移中位数）")
    ap("")
    ap(
        "「触及上限比例」按 L0 的上限计（size 0.10，其余风格 0.25）；在 L1 中它只是描述性阈值"
        "（size 除外，size 仍受约束）。"
    )
    ap("")
    ap(
        "| 风格 | M0_A L0 均值 | L0 触顶 | M0_A L1 均值 | L1 超阈值 | M1_C L0 均值 | L0 触顶 | M1_C L1 均值 | L1 超阈值 |"
    )
    ap("|---|---|---|---|---|---|---|---|---|")
    for s in styles:
        cells = []
        for v in ep.VARIANTS:
            for r in RUNGS_LIN:
                st = med[r][v]["windows"]["A"]["styles"][s]
                cells += [f2(st["mean"]), pct(st["share_at_ref_cap"])]
        ap(f"| {s} | " + " | ".join(cells) + " |")
    ap("")
    ap("## 6. 盈亏归因（L0 与 L1，5 个偏移逐日平均后）")
    ap("")
    ap(
        "股票账户收益拆为 市场、行业、9 个风格之和、特异；另列 ETF 对冲腿、国债腿、成本、"
        "未对账项（毛收益 − 三条腿）。数字为年化贡献（均值×252，占权益比例）与夏普。"
    )
    ap("")
    comps = [
        ("market", "市场"),
        ("industry", "行业"),
        ("style_total", "风格合计"),
        ("specific", "特异"),
        ("etf_leg", "ETF 对冲腿"),
        ("tbill_leg", "国债腿"),
        ("costs", "成本"),
        ("unreconciled", "未对账"),
        ("gross_reported", "毛（报告）"),
        ("net_reported", "净（报告）"),
    ]
    for v in ep.VARIANTS:
        for w in SHOWN_WINDOWS:
            ap(f"### {v}，窗口 {w}")
            ap("")
            ap("| 成分 | L0 年化贡献 | L0 夏普 | L1 年化贡献 | L1 夏普 |")
            ap("|---|---|---|---|---|")
            for key, name in comps:
                a0, a1 = svs[f"L0_{v}"][w][key], svs[f"L1_{v}"][w][key]
                ap(
                    f"| {name} | {pct(a0['ann_contribution'])} | {f2(a0['sharpe'])} | "
                    f"{pct(a1['ann_contribution'])} | {f2(a1['sharpe'])} |"
                )
            ap("")
    ap("### 各风格的年化贡献（A 窗口）")
    ap("")
    ap("| 风格 | M0_A L0 | M0_A L1 | M1_C L0 | M1_C L1 |")
    ap("|---|---|---|---|---|")
    for s in styles:
        ap(
            f"| {s} | "
            + " | ".join(
                pct(svs[f"{r}_{v}"]["A"][f"style_{s}"]["ann_contribution"])
                for v in ep.VARIANTS
                for r in RUNGS_LIN
            )
            + " |"
        )
    ap("")
    ap("## 7. 独立复算")
    ap("")
    ap(f"方法：{rc['method']}。")
    ap("")
    ap("| 数字 | 复算 | results.json | 差 | ≤1e-9 |")
    ap("|---|---|---|---|---|")
    for k, r in rc["numbers"].items():
        ap(
            f"| {k} | {r['recomputed']:.12f} | {r['results_json']:.12f} | {r['abs_diff']:.2e} | "
            f"{r['match_1e-9']} |"
        )
    ap("")
    ap("## 8. 其他事实")
    ap("")
    ap(
        "- 身份检验（`identity-check.json`）：新运行器在默认风格上限、收盘成交下与 `M0_A_o0_close` 在 2024-01-02..2024-03-28 的 daily net 最大绝对差 0.0（阈值 1e-12）。"
    )
    ap(
        "- 失败调仓：偏移 0–4 分别有 0、5、6、8、2 个日期求解失败（各配置与变体相同），"
        "不属于路径缺失；`run-manifest.json` 记录了 30 条路径的 sha256、行数与首末日期。"
    )
    ap("- 试验计数：新增 6 个（3 配置 × 2 变体），程序累计 89（供后续 DSR 使用）。")
    ap(
        "- Modal 花费：30 个分片总墙钟 8164 秒（最长 508 秒），按费率（1 核 0.0473 美元/小时 + 4 GiB × 0.008）"
        "估算约 0.18 美元；预检最坏情形 0.793 美元（`modal-ledger.jsonl`，上限 2 美元）；"
        "`modal_budget.py status` 的月累计已计费 0.9731 美元（含其他任务，30 条路径开始前为 0.707）。"
    )
    ap(
        "- 文献：Lee-Stefek、Ceria 等、Saxena-Stubbs、Clarke 等四篇原文付费墙未读，"
        "只读了公开二手文本；没有来源量化风格上限造成的 alpha 损失。"
    )
    ap("")
    ap("v1.1 设计由主审决定")
    return "\n".join(L) + "\n"


def main() -> int:
    res = json.loads(RESULTS.read_text())
    meta = json.loads((ep.RISK_DIR / "meta.json").read_text())
    styles = list(meta["styles"])
    res["style_vs_specific"] = style_vs_specific(styles)
    res["recompute"] = independent_recompute(res)
    now = subprocess.check_output(["date", "-u", "+%Y-%m-%dT%H:%M:%SZ"], text=True).strip()
    res["generated_at_utc"] = now
    RESULTS.write_text(json.dumps(ep.ev.clean(res), indent=1, ensure_ascii=False) + "\n")
    (PM_DIR / "report.md").write_text(build_report(res, styles, now))
    print(json.dumps(res["recompute"], indent=1))
    return 0 if res["recompute"]["all_match"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
