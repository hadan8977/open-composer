"""Publish attribution from completed receipts; no numerical account replay."""
from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import sys
import time

import numpy as np
import pandas as pd
from scipy.stats import kurtosis, skew

sys.path.insert(0, str(Path(__file__).resolve().parent))
from attribution import BASE, OLD, OUT, ROOT, RUN, save
from open_composer.research.agent_workflow import Results, completed_tokens, validate_results


def read(name):
    return json.loads((OUT / name).read_text())


def money(x):
    return f"${x:,.0f}"


def pct(x):
    return f"{100*x:.2f}%"


def ci(row, reverse=False):
    a, b = row["paired_uncertainty"]["usd_increment_95pct"]
    if reverse:
        a, b = -b, -a
    return f"[{money(a)}, {money(b)}]"


def main():
    pairs = read("comparisons.json")
    lookup = {(p["candidate"], p["cost"], p["control"]): p for p in pairs}
    diagnostics = read("account-diagnostics.json")
    by_account = {p["account"]: p for p in diagnostics}
    counts, inventory = read("counts.json"), read("trial-inventory.json")
    summaries = read("allocation-summary.json")
    dsr = read("conditional-dsr.json")
    rf_close = pd.read_parquet(OLD / "close.parquet").BIL
    rf_close.index = rf_close.index.as_unit("ns")
    rf = rf_close.pct_change(fill_method=None).loc["2023-09-18":"2025-12-31"]
    details = {}
    for cid in ["A4", "L1", "H1"]:
        for cost in [10, 20]:
            row = lookup[cid, cost, "same_risk_fixed_D1"]
            folder = ROOT / row["candidate_metrics"]["account"]
            r = pd.read_csv(folder / "ledger.csv", index_col=0, parse_dates=True).net
            assert r.index.equals(rf.index)
            excess = (r - rf).to_numpy()
            centered = excess - excess.mean()
            n, moment2 = len(excess), float(np.mean(centered**2))
            inflation = max(1., 1. + 2 * sum((1 - lag/22) * float(np.dot(centered[lag:], centered[:-lag]) / n) / moment2 for lag in range(1, 22)))
            details[f"{cid}-{cost}"] = {**dsr[f"{cid}-{cost}"],
                "daily_mean_excess": float(excess.mean()), "daily_std_excess_ddof1": float(excess.std(ddof=1)),
                "annual_excess_sharpe": float(excess.mean()/excess.std(ddof=1)*np.sqrt(252)),
                "sample_skew_bias_corrected": float(skew(excess, bias=False)),
                "sample_pearson_kurtosis_bias_corrected": float(kurtosis(excess, fisher=False, bias=False)),
                "hac_inflation_floor_one": inflation, "hac_effective_sessions": n/inflation,
                "dispersion_assumption": "Native null-standard-normal maximum at all 54 known starts, sample moments; no survivor-fitted dispersion"}
    save("dsr-detail.json", details)
    old_pairs = json.loads((OLD / "comparisons.json").read_text())
    decomposition = []
    annual_rows = []
    for cost in [10, 20]:
        a = lookup["A4", cost, "same_risk_fixed_D1"]
        old = next(p for p in old_pairs if p["candidate"] == "A4" and p["cost_bp_per_side"] == cost)
        fixed_part = a["control_metrics"]["net_profit_usd"] - old["matched_control_metrics"]["net_profit_usd"]
        decomposition.append({"cost": cost, "prior_increment_over_same_risk_S3_SHY_usd": old["increment_matched_usd"],
            "fixed_D1_level_step_usd": fixed_part, "remaining_A4_over_fixed_D1_usd": a["increment_usd"],
            "fixed_level_fraction_of_prior_increment": fixed_part / old["increment_matched_usd"],
            "meaning": "Accounting decomposition via two fitted risk-normalized controls; not a unique causal mediation estimate"})
        ca = by_account[a["candidate_metrics"]["account"]]["year_contributions"]
        cb = by_account[a["control_metrics"]["account"]]["year_contributions"]
        for year in ["2023", "2024", "2025"]:
            annual_rows.append({"cost": cost, "year": year,
                "A4_actual_account_profit_usd": ca[year]["profit_usd"],
                "same_risk_fixed_actual_account_profit_usd": cb[year]["profit_usd"],
                "difference_usd": ca[year]["profit_usd"] - cb[year]["profit_usd"],
                "note": "2023 begins Sep18; actual daily dollar changes, never a newly reset annual account or selection slice"})
    save("attribution-decomposition.json", {"cost_scenarios": decomposition, "calendar_year_contributions": annual_rows,
        "worker_decision": "stop A4 timing refinement; retain fixed-allocation and M1/W4 research evidence for fresh Lead",
        "basis": "A4 residual intervals include zero at both costs; L1 close in dollars with inconclusive pair; residual concentrated in 2025; 27 effective monthly updates; finite lineage investment 25 mechanisms",
        "next_method": "No new parameter search. Fresh Lead may prioritize unchanged fixed D1/S3 allocation evidence and signal mechanisms under a separate accepted economic scope."})
    states = {name: json.loads((BASE / "runs" / name / "run.json").read_text())
              for name in ["mechanisms-20261102-1", "mechanisms-20261102-2"]}
    now = datetime.now(UTC)
    cost_snapshot = {"observed_at": now.isoformat(), "source": "Existing driver run.json; no account-quota RPC or task-dollar inference",
        "runs": {k: {"tokens": completed_tokens(v), "elapsed_seconds": v.get("elapsed_seconds"),
            "ended_role_seconds": sum(p.get("elapsed_seconds", 0) for p in v["phases"].values()),
            "active_roles_observed_seconds": {name: (now - datetime.fromisoformat(p["started"])).total_seconds()
                for name, p in v["phases"].items() if "elapsed_seconds" not in p and p.get("started")}}
            for k, v in states.items()},
        "account_computation_seconds": counts["account_seconds_new"], "engine_elapsed_seconds": counts["engine_elapsed_seconds"],
        "failed_attempts_this_worker": ["Initial read used unavailable python (exit127); continued with python3. Early receipt listing found output not created yet; actual existing process retained.",
            "Numerical batch: zero failed selectable starts or unfinished native accounts; prior 24 failed publications retained."],
        "unknown": ["Current Worker and future Lead final usage pending driver", "Provider dollars and missing historical totals"],
        "scope": "Ordinary all-role research including failed work. Cached input included in input. Per-session cumulative maxima used; no restructuring costs. Numerical/check seconds nested in role time, not additive."}
    save("research-costs.json", cost_snapshot)
    p10, p20 = lookup["A4", 10, "same_risk_fixed_D1"], lookup["A4", 20, "same_risk_fixed_D1"]
    primary_diag = by_account[p10["candidate_metrics"]["account"]]
    forensic = {"strategy_name": "cross_asset_allocation_attribution_20261102",
        "source_strategy_spec": "strategy_specs/drafts/h20260928_02_cross_asset_sleeve.yaml",
        "scope": "Accepted attribution component using unchanged source signals; no new StrategySpec or promotion claim",
        "lookahead_check": "pass", "future_leak_check": "pass", "overfit_risk": "high",
        "multiple_testing_count": inventory["n_trials"], "pbo_proxy": None, "dsr_proxy": None, "pbo": None,
        "dsr": details["A4-10"]["dsr"],
        "statistical_methods": {"dsr": details, "bootstrap": {"block_sessions": 21, "draws": 1000, "seed": 20261102,
            "scope": "Paired conditional dollar intervals with fixed fitted controls; selection unadjusted"},
            "pbo_note": "No new PBO for the small ablation. Prior 24-configuration Sharpe-ranking PBO 0.171429 retained only as its original diagnostic.",
            "prior_pbo_artifact": str((OLD / "pbo.json").relative_to(ROOT))},
        "sample_data_caveats": ["575 seen development sessions but only 27 effective monthly updates; 28 final-close decisions, final Dec31 decision outside window",
            "Same-risk and same-average controls ex-post descriptive; prewindow fixed, L1, H1 causal",
            "No unseen window, new reference account or paper acceptance", "Broader S3 ancestry unknown; 24 failed publications retained",
            "Known fractional-share order books; whole-share/auction/capacity and actual broker fees unverified",
            "Previous stress normalization controls each have two price-unavailable frozen attempts; not new primary evidence"],
        "trade_count": primary_diag["order_count"], "trade_session_count": p10["candidate_metrics"]["trade_sessions"],
        "trading_days": 575, "short_sample": False,
        "capacity_assessment": "No new ADV/auction claim; retained maximum actual A4 order $21,115.97 at 10bp; fractional $20k research books",
        "conclusion": "warning", "notes": "Two new allocation-clock checks passed in one pytest. Fifty used development receipts reconcile (40 new, 10 reused); no account replay. Stop timing investment is an opportunity-cost judgment, not scientific rejection of cross-asset trend. Original K1/K2 and paper/schedules unchanged."}
    path = ROOT / "reports/harness/forensics/cross_asset_allocation_attribution_20261102-backtest-forensics.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(forensic, ensure_ascii=False, indent=2) + "\n")
    path.with_suffix(".md").write_text(
        f"归因取证结论为 warning。575 个已见开发交易日仅含 27 次窗内生效月度更新。两项新增时钟检查通过，50 个使用账户的份额／现金、实际净额订单费、权益复利及次日开盘成交核对一致；其中 40 个为本轮新账户。\n\n"
        f"累计 54 次已知启动含失败发布，A4 10bp 条件 DSR 为 {details['A4-10']['dsr']:.6f}；全部六组矩、HAC21 与试验假设见 dsr-detail.json。两种事后控制仅用于已见期归因。配对区间固定控制系数，未校正选择；没有重新计算小型消融 PBO。\n\n"
        "当前月风险信息相对滞后一月的作用不确定；建议停止此项择时细化。该判断没有否定 D1、M1/W4 或跨资产趋势，原 K1 通过、K2 的 +0.037 未达 +0.05 保持。整股、容量和真实成本仍须后续独立证据，当前无 paper 晋级。\n", encoding="utf-8")
    report = ROOT / "reports/research/cross_asset_mechanisms_20261102/allocation-attribution.zh.md"
    text = [
        "建议停止 A4 当月择时的继续细化，保留固定 D1/S3 配置和 M1/W4 的研究证据。改用同风险固定 D1/S3 对照后，A4 在 10/20bp 下的剩余净增量为 $3,662/$3,542，约为前轮增量的一半；两档条件区间均跨零。现有结果支持配置水平解释相当一部分贡献，尚不能认定全部来自平均配置，也没有证明当月调整提供稳定增益。",
        "",
        "本轮全部金额来自初始 $20,000 的完整份额／现金账户，窗口固定为 2023-09-18 至 2025-12-31，共 575 个已见开发交易日。使用已保存价格、原 D1 与 S3 信号及独立账户的成本后历史；收盘决定在下一开盘成交，旧持仓先赚隔夜变化。所有新账户共用 A4 事件并集，任一事件恢复两袖目标，事件间持股份额漂移。净额资产订单实际计费，未混合两条收益曲线代替账户。",
        "",
        "同风险对照在每档成本分别求固定 D1 比例，S3 为其余部分；它是事后风险归一化。冻结的五个区间节点波动率单调下降，六个匹配均只有一个观察到的括区间根，绝对年化波动差均小于 1e-6；求根全过程与账户保留，没有按收益挑根。",
        "",
        "| 单边成本 | A4 净利 | 同风险固定 D1 比例 | 固定账户净利 | A4 剩余增量 | 条件95%区间 | 两账户波动率 |",
        "|---|---:|---:|---:|---:|---|---:|",
    ]
    for cost in [10, 20]:
        p = lookup["A4", cost, "same_risk_fixed_D1"]
        text.append(f"| {cost}bp | {money(p['candidate_metrics']['net_profit_usd'])} | {pct(p['fixed_D1_share'])} | {money(p['control_metrics']['net_profit_usd'])} | {money(p['increment_usd'])} | {ci(p)} | {pct(p['candidate_metrics']['volatility_annual'])} |")
    text += ["", f"10bp 下 A4／固定对照最大回撤为 {pct(p10['candidate_metrics']['max_drawdown'])}／{pct(p10['control_metrics']['max_drawdown'])}，最长水下期为 88／138 个交易日。相对前轮同风险 S3/SHY 对照的 $7,557/$7,376 增量，经固定 D1 配置这一步分别解释 {money(decomposition[0]['fixed_D1_level_step_usd'])}/{money(decomposition[1]['fixed_D1_level_step_usd'])}，约 52%；余下约 48% 是本轮尚不确定的残差。这是经过两个事后风险归一化对照的账面分解，并非唯一的因果贡献分配。", "",
        "同平均对照按 A4 目标从已知收盘移至生效开盘后取算术平均，没有按后续收益加权；D1 比例为 71.3056%／71.2996%。开窗前最后收盘 2023-09-15 可设的比例为 75%，对应既有 A2。A4 两档均有 471/575 个生效开盘处于 75% 上限。以下未匹配风险的差额须连同风险差解读。", "",
        "| 成本 | 固定对照 | 对照净利 | A4减对照 | 对照减A4波动差（百分点） | 配对95%区间 |",
        "|---|---|---:|---:|---:|---|",
    ]
    for cost in [10, 20]:
        for control, label in [("same_average_A4", "开盘同平均"), ("prewindow_fixed_A4", "开窗前固定75%")]:
            p = lookup["A4", cost, control]
            text.append(f"| {cost}bp | {label} | {money(p['control_metrics']['net_profit_usd'])} | {money(p['increment_usd'])} | {p['control_minus_candidate_vol_gap']*100:+.3f} | {ci(p)} |")
    text += ["", "L1 每月使用前一次月度决定的配置；H1 使用此前所有两袖 63 日波动均有效为正的月度配置均值，排除当前决定。H1 包含开窗前 89 次有效月度决定，空历史为 50/50；其本窗 D1 配置约在 69%–70% 缓慢变化。每档成本分别读对应成本后历史。", "",
        "| 干预／成本 | 净利 | 波动率 | 自身同风险固定D1比例 | 对自身固定对照增量 | 配对95%区间 |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for cid in ["L1", "H1"]:
        for cost in [10, 20]:
            p = lookup[cid, cost, "same_risk_fixed_D1"]
            text.append(f"| {cid}／{cost}bp | {money(p['candidate_metrics']['net_profit_usd'])} | {pct(p['candidate_metrics']['volatility_annual'])} | {pct(p['fixed_D1_share'])} | {money(p['increment_usd'])} | {ci(p)} |")
    l1, h1 = lookup["L1", 10, "A4"], lookup["H1", 10, "A4"]
    text += ["", f"A4 比 L1 在 10/20bp 下多赚 $731/$682；10bp 配对区间为 {ci(l1, True)}，L1 波动率比 A4 高 0.379 个百分点。A4 比 H1 多赚 $3,342/$3,237；10bp 区间为 {ci(h1, True)}，H1 波动率高 0.221 个百分点，均不能当成同风险差。H1 对自身同风险固定配置仅多 $37/$38，说明平滑历史水平几乎重现固定配置；L1 仍保留部分点估计残差。两项反证没有确认“当前月信息必须及时响应”。", "",
        "区间沿用 21 个交易日移动块、1,000 次、种子 20261102 的配对美元诊断。控制系数在抽样内保持固定，区间条件于拟合及已知选择，未校正事后选优。窗口内有 28 次月末决定，但 2025-12-31 决定只能影响下一窗口，故只有 27 次窗内生效更新，不能把 575 日当作 575 次独立择时试验。", "",
        "年度金额直接来自原日账的实际权益变化；2023 仅为 9 月18日起的部分年度，各年没有重新投入 $20,000。这些分片只用于诊断集中度。", "",
        "| 年份 | 10bp A4净利贡献 | 10bp固定对照贡献 | 10bp残差 | 20bp残差 |",
        "|---|---:|---:|---:|---:|",
    ]
    for year in ["2023", "2024", "2025"]:
        a = next(r for r in annual_rows if r["cost"] == 10 and r["year"] == year)
        b = next(r for r in annual_rows if r["cost"] == 20 and r["year"] == year)
        text.append(f"| {year} | {money(a['A4_actual_account_profit_usd'])} | {money(a['same_risk_fixed_actual_account_profit_usd'])} | {money(a['difference_usd'])} | {money(b['difference_usd'])} |")
    text += ["", "残差集中在 2025，2024 反而为负。配置历史显示 A4 在 2025 年4月底将 D1 从75%降到48.98%，5月底进一步到25%，6月底回到59.51%，7月底恢复75%；均下一开盘生效。这些少数决定与收益集中相符，不能据此事后挑选该段作为验证窗口。", "",
        "高收益方案的机会成本继续保留，以下账户风险不同。", "",
        "| 方案 | 10/20bp净利 | 10bp CAGR | 10bp波动率 | 10bp最大回撤 | 10bp最长水下期 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for label, ctrl in [("纯S3", "pure_S3"), ("固定25% D1（A1）", "fixed_0.25"), ("固定50% D1", "fixed_0.50"), ("固定75% D1（A2）", "fixed_0.75")]:
        a, b = lookup["A4", 10, ctrl]["control_metrics"], lookup["A4", 20, ctrl]["control_metrics"]
        text.append(f"| {label} | {money(a['net_profit_usd'])}／{money(b['net_profit_usd'])} | {pct(a['cagr_252'])} | {pct(a['volatility_annual'])} | {pct(a['max_drawdown'])} | {a['longest_underwater_sessions']} |")
    a, b = p10["candidate_metrics"], p20["candidate_metrics"]
    text.append(f"| A4 | {money(a['net_profit_usd'])}／{money(b['net_profit_usd'])} | {pct(a['cagr_252'])} | {pct(a['volatility_annual'])} | {pct(a['max_drawdown'])} | {a['longest_underwater_sessions']} |")
    text += ["", "A4 比纯 S3 在10/20bp少赚 $35,604/$33,927，比 A1 少赚 $19,873/$18,981；降低波动与回撤的代价是真实美元收益。原 M1/W4 的10bp同风险增量 $4,926/$4,872、条件区间 [$331,$13,731]/[$147,$13,664] 继续作为另一条信号机制证据，不能因本轮择时不确定而抹去。原 BIL/SHY 及等权篮子的简单对照保留在前轮报告和日账。", "",
        "所有账户各有36个实际交易日；A4 的10bp订单240笔。下表订单费为实际净额买卖金额乘单边费率，融资为原生小额负现金融资，已各扣一次。独立手续费、冲击模型为零属于本实验假设，未覆盖真实券商费用与开盘冲击。", "",
        "| 账户 | 10/20bp订单扣费 | 10/20bp现金融资 | 10bp年化买卖总换手 |",
        "|---|---:|---:|---:|",
    ]
    for cid in ["A4", "L1", "H1"]:
        a, b = lookup[cid, 10, "same_risk_fixed_D1"]["candidate_metrics"], lookup[cid, 20, "same_risk_fixed_D1"]["candidate_metrics"]
        text.append(f"| {cid} | ${a['costs_usd']['cost_spread']:,.2f}／${b['costs_usd']['cost_spread']:,.2f} | ${a['costs_usd']['cost_margin']:.2f}／${b['costs_usd']['cost_margin']:.2f} | {a['turnover_annual']:.2f}倍 |")
    a, b = p10["control_metrics"], p20["control_metrics"]
    text.append(f"| A4同风险固定对照 | ${a['costs_usd']['cost_spread']:,.2f}／${b['costs_usd']['cost_spread']:,.2f} | ${a['costs_usd']['cost_margin']:.2f}／${b['costs_usd']['cost_margin']:.2f} | {a['turnover_annual']:.2f}倍 |")
    text += ["", "A4 两档终值少 $884，包含直接费用、复利及成本历史导致的小幅配置变化，不能把该差额全部称为扣费。10bp平均杠杆 ETF 面值权重，A4／同风险固定／L1／H1分别为18.16%／18.31%／19.13%／18.67%；基金内部杠杆未展开。每日各资产敞口、换手、成本分项与最大订单都在日账、订单及账户诊断中，整股、容量与开盘成交可行性仍待部署证据。", "",
        f"本轮新增 L1/H1 两个不同机制，方向累计25个，已达到20–50的投入参考；没有为归因任务另开20个参数。新增40个数值账户（含求根），复用10个开发账户和4个独立历史账户，完成46项配对比较；其中开窗前75%与既有固定75%是同一对照，明确重复展示，没有算成新机制。50个使用的开发账户权益、份额现金、净额费率和次日开盘成交核对一致。两项新增配置时钟检查在一次 pytest 中通过。累计341个保存数值账户；全部54次已知试验启动含四个祖先候选、24次失败发布、24次前轮恢复及本轮两次，无未闭合试验或未完成账户。", "",
        f"按完整已知库存，A4对齐BIL的条件DSR为{dsr['A4-10']['dsr']:.6f}/{dsr['A4-20']['dsr']:.6f}，10bp超额Sharpe为{details['A4-10']['annual_excess_sharpe']:.3f}；HAC=21及偏度、峰度、频率和假设均保存。更广S3祖先仍未知。旧24配置Sharpe排序PBO=0.171429只保留其原含义，本轮未构造小型消融PBO或新晋级门。原K1通过、K2的+0.037低于+0.05保持；Carlson全文缺失限制保持。2026、anchor与stress均已见，仅引用原报告，两个旧stress归一化账户各有两次价格不可用冻结尝试，未作新参照批次。", "",
        "普通研究成本包含独立计划审阅、失败工作、Worker及随后Lead，由原driver收尾。前轮全角色结束用时3,785.18秒、墙钟3,787.12秒，token下界18,363,443（含缓存的输入18,206,066及输出157,377）；同会话重复记录取累计最大值，完整总数与提供方美元仍未知。本轮审阅159.30秒、已记token563,207；Worker/Lead最终用量尚待收尾。数值引擎71.46秒，其中新账户计算45.60秒，包含在Worker时间内，不重复相加。一次只读调用因python命令不存在改用python3，旧24次失败发布及其未知费用均保留；本次数值启动无失败。未加入重构成本、共享额度推算或新费用门槛。", "",
        "本任务以 stop 结束 A4 择时细化投入：残差跨成本保留正点估计，却集中在少数2025决定，且当前月相对滞后一月的优势不确定。fresh Lead 应核对完整账户后决定固定配置与 M1/W4 哪条线更符合收益目标；若重开择时，需要新的信息证据或验证方法，继续同一窗口调波动率周期与上下限的机会成本较高。该投入判断不构成跨资产趋势的科学否定。当前无新增paper候选、订单、提供方或调度变更，也无新的机主决策依赖。", "",
        "证据：", "",
        f"- [完整配对与条件区间](/{OUT.relative_to(ROOT)}/comparisons.json)",
        f"- [配置与年度美元分解](/{OUT.relative_to(ROOT)}/attribution-decomposition.json)",
        f"- [账户、订单成本及敞口核对](/{OUT.relative_to(ROOT)}/account-diagnostics.json)",
        f"- [计数](/{OUT.relative_to(ROOT)}/counts.json)和[研究成本快照](/{OUT.relative_to(ROOT)}/research-costs.json)",
        f"- [取证记录](/{path.relative_to(ROOT)})和[逐组DSR](/{OUT.relative_to(ROOT)}/dsr-detail.json)",
        f"- [本轮数值Results](/{OUT.relative_to(ROOT)}/results.json)；fresh Lead以最终补充Results接收。",
    ]
    # Repo report links are relative to the report directory, independent of host.
    import os
    for i, line in enumerate(text):
        for prefix in ["research/", "reports/"]:
            start = 0
            while (at := line.find("](/" + prefix, start)) >= 0:
                end = line.index(")", at)
                target = ROOT / line[at+3:end]
                line = line[:at+2] + os.path.relpath(target, report.parent) + line[end:]
                start = at + 2
        text[i] = line
    report.write_text("\n".join(text) + "\n", encoding="utf-8")
    result = Results.model_validate_json((OUT / "results.json").read_text())
    result.source_artifacts += [str((OUT / f).relative_to(ROOT)) for f in ["dsr-detail.json", "attribution-decomposition.json", "research-costs.json"]]
    result.source_artifacts += [str(path.relative_to(ROOT)), str(report.relative_to(ROOT)), str((RUN / "worker/checks.log").relative_to(ROOT))]
    result.limitations.append("Worker recommends stopping A4 timing refinement on opportunity cost; fresh Lead reception pending, no field-wide rejection")
    save("results-with-forensics.json", result.model_dump())
    (BASE / "results.json").write_text(result.model_dump_json(indent=2) + "\n")
    validate_results(ROOT, str((BASE / "results.json").relative_to(ROOT)), BASE.name)
    print(json.dumps({"schema": "Results validated", "report": str(report.relative_to(ROOT)),
                      "comparisons": len(pairs), "audited_development_accounts": len(diagnostics), "worker_decision": "stop timing refinement"}))


if __name__ == "__main__":
    main()
