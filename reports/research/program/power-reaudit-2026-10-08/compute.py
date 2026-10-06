# ruff: noqa: E501
"""T-20261005-35: power re-audit of directions registered as `refuted`.

Mechanical, no backtest: reads reports/research/harvest/directions.jsonl (last
row per id), applies the plan-v2 P-1 five-condition check, and computes the
minimum detectable effect (MDE) from the numbers the original reports already
contain. Writes audit.json next to this file.

P-1 (docs/plan-v2-2026-10-05.zh.md section 1), codes per condition:
  c1 original result reproduced (relative conclusion / curve shape)
  c2 faithful implementation of the original or industry practice
  c3 >= 3 depth points (data scale, model capacity, history, fidelity)
  c4 preregistered iteration budget used up
  c5 power analysis shows the test could see the claimed effect
  Y met, N not met, A not applicable, ? cannot be established from the record.
  p1_met needs every code in {Y, A}.  Anything else is labelled "未到深度".

MDE conventions (stated, not tuned):
  K = 1.645 + 0.842 = 2.486 : one-sided 5%, 80% power -- the convention of the
      iteration h20261004_pm_earnings_beat_odds results.json (basis string
      there; reproduced below as a self-test: 2.486 * 0.019139/0.43 = 0.1107 vs
      reported 0.1101).
  Sharpe-type: standard error of an annualised Sharpe from T years of iid
      returns is 1/sqrt(T); MDE = K/sqrt(T).  Autocorrelation and non-normality
      make the true SE larger, so these MDEs are lower bounds.
  IC / CAR / coefficient type: SE = |observed| / t as reported by the original
      run (Newey-West or event-date t); MDE = K * SE.
  Sharpe-difference ("edge" vs a correlated benchmark, K2 style):
      SE = sqrt(2 (1 - rho) / T).
c5 is set automatically when the inputs exist: Y if MDE <= claimed effect, or
the one-sided 95% upper bound of the observed effect is below the claimed
effect (the test positively excludes it); otherwise N.  When the claimed effect
is unknown the MDE is reported and c5 stays as hand-coded ("?").
"""

from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent / "audit.json"
DIRECTIONS = ROOT / "reports/research/harvest/directions.jsonl"

K = 1.645 + 0.842
Z95 = 1.645
# Frozen windows of the screening lane (config / iteration reports):
ANCHOR_YEARS = (date(2026, 9, 17) - date(2024, 1, 8)).days / 365.25
STRESS_YEARS = (date(2023, 8, 31) - date(2016, 5, 2)).days / 365.25
K1_ANCHOR_BAR = 1.1882
K1_STRESS_BAR = 0.6447


def sharpe_block(d: dict) -> dict:
    parts = []  # (years, observed)
    if d.get("anchor") is not None:
        parts.append((d.get("anchor_years", ANCHOR_YEARS), d["anchor"]))
    if d.get("stress") is not None:
        parts.append((d.get("stress_years", STRESS_YEARS), d["stress"]))
    years = sum(p[0] for p in parts)
    obs = sum(p[0] * p[1] for p in parts) / years
    target = d.get("claimed")
    basis = "claimed"
    if target is None:
        both = d.get("anchor") is not None and d.get("stress") is not None
        target = K1_STRESS_BAR if both else K1_ANCHOR_BAR
        basis = "K1 bar (stress 0.6447 if both windows else anchor 1.1882)"
    mde = K / math.sqrt(years)
    upper = obs + Z95 / math.sqrt(years)
    return {
        "type": "sharpe",
        "years": round(years, 2),
        "observed_pooled": round(obs, 3),
        "se": round(1 / math.sqrt(years), 3),
        "mde_80": round(mde, 3),
        "upper95_one_sided": round(upper, 3),
        "target": round(target, 4),
        "target_basis": basis,
        "c5_auto": "Y" if (mde <= target or upper < target) else "N",
    }


def stat_block(d: dict) -> dict:
    """IC / CAR / coefficient from (observed, t)."""
    obs, t = d["obs"], d["t"]
    se = abs(obs) / abs(t)
    mde = K * se
    out = {
        "type": d.get("type", "ic"),
        "unit": d.get("unit", "IC"),
        "observed": obs,
        "t": t,
        "se": round(se, 5),
        "mde_80": round(mde, 5),
        "upper95_one_sided": round(obs + Z95 * se, 5),
    }
    claimed = d.get("claimed")
    if claimed is not None:
        out["claimed"] = claimed
        out["c5_auto"] = "Y" if (mde <= abs(claimed) or abs(obs) + Z95 * se < abs(claimed)) else "N"
        if d.get("claimed_is_signed") and obs > 0 and claimed < 0:
            out["c5_auto"] = "N"
    return out


def edge_block(d: dict) -> dict:
    parts = []
    for years, obs, rho in d["windows"]:
        se = math.sqrt(2 * (1 - rho) / years)
        parts.append(
            {
                "years": round(years, 2),
                "observed_edge": obs,
                "rho": rho,
                "se": round(se, 3),
                "mde_80": round(K * se, 3),
            }
        )
    bar = d["bar"]
    ok = all(p["mde_80"] <= bar for p in parts)
    return {"type": "sharpe_edge", "windows": parts, "bar": bar, "c5_auto": "Y" if ok else "N"}


A, S = ANCHOR_YEARS, STRESS_YEARS

# id (without "dir:"), kind, data, c1..c5, class, what is missing / note, reopen candidate
# classes: power | fidelity | depth | budget | contract (priced in / cost) |
#          sizing | data | internal (own-book attribution) | met
ENTRIES: list[tuple] = [
    (
        "s1_sector_rotation_voltarget",
        "none",
        {},
        "AYN??",
        "sizing",
        "原报告无检验统计量，无法计算 MDE；目标波动率只测单点，需 >=3 个目标水平",
        False,
    ),
    (
        "drawdown_brake_overlay",
        "none",
        {},
        "AYN??",
        "sizing",
        "H-20260922-02 12 个格子是参数点不是深度点；无统计量，无法计算",
        False,
    ),
    (
        "levered_menu_expansion",
        "none",
        {},
        "AYN??",
        "internal",
        "归因分析（H-20260923-09），无检验统计量，无法计算",
        False,
    ),
    (
        "s3_rank_optimization",
        "none",
        {},
        "A?N??",
        "internal",
        "判定仅一句话 'not worth it'，原报告无数字，无法计算",
        False,
    ),
    (
        "composer_rsi_branch_uvxy",
        "none",
        {},
        "NNN??",
        "fidelity",
        "平台收益声明未用 composer-trade-py 的 value_history 与回测对比，未取实盘记录",
        True,
    ),
    (
        "giants_sweep_published_etf_rules",
        "none",
        {},
        "NYNY?",
        "power",
        "原报告无逐规则检验统计量；各规则只测单规格",
        False,
    ),
    (
        "earnings_8k_tone_next_day",
        "none",
        {},
        "NNN??",
        "fidelity",
        "论文的可交易对象是电话会逐字稿（机主未购买），这里测的是 8-K 文本，对象不同",
        False,
    ),
    (
        "spy_noise_band_intraday",
        "none",
        {},
        "NYN??",
        "power",
        "毛边际约 3.6%/年低于无风险；无统计量，无法计算；缺成本/退出规格曲线",
        False,
    ),
    (
        "cross_sectional_gap_fade",
        "none",
        {},
        "YYYYY",
        "met",
        "8 个组合（4 档 ADV x 2 种账本）x 2 个窗口 + 拍卖执行复核；毛边际 +11.5 bp/日 对成本 -38.5 bp/日是直接测量，"
        "不是功效问题；拍卖口径 E_off 7.09 bp（90% CI -2.1..16.0）与 8 bp 门槛相交，该子项另见 smallcap_gap_down_fade",
        False,
    ),
    (
        "levered_industry_trend_second_bet",
        "none",
        {},
        "AYNY?",
        "power",
        "NUGT/JNUG 2026 留出窗仅约 0.7 年；报告无 t 值；对象是 5 个行业 ETF 的单一规则",
        False,
    ),
    (
        "insider_form4_confirmation_gate",
        "none",
        {},
        "AYN??",
        "internal",
        "结构性错配（内部人买入落在动量前 50 的比例 1.9% 对池子 5.8%）；无统计量",
        False,
    ),
    (
        "news_attention_features",
        "none",
        {},
        "NNNN?",
        "fidelity",
        "只做了阶段 1（计数/新颖度）；阶段 2 LLM 内容打分未测，文献的池子/频率（小盘、月频、长持）未对应",
        True,
    ),
    (
        "meta_labeling_position_tiers",
        "none",
        {},
        "AYN??",
        "sizing",
        "分层等价于按比例降杠杆；停止条件命中，无统计量",
        False,
    ),
    (
        "event_13d_drift",
        "none",
        {},
        "YYA?A",
        "contract",
        "漂移已在最早可入场点（次日开盘）之前定价；是入场合同问题，不是功效问题；缺预算记录",
        False,
    ),
    (
        "pead_xbrl_8k_llm",
        "stat",
        {"obs": None},
        "NYNYN",
        "power",
        "t_dates 1.064；8-K 覆盖把样本限制在 2024-2026（约 2.7 年），无法检出文献量级的 SUE 漂移；需把 8-K 2.02 时间戳回补到 2016+",
        True,
    ),
    (
        "short_interest_avoidance_gate",
        "none",
        {},
        "AYN??",
        "power",
        "随机去除安慰剂损失更少；无统计量；短利息历史样本较短",
        False,
    ),
    (
        "short_interest_ratio_crowding_factor",
        "none",
        {},
        "YYN?A",
        "internal",
        "分解安慰剂：打乱分子仍复现 81%/65%，纯 1/ADV 复现 86%/52%——价值在分母（流动性）不在短利息；分解已直接说明机制",
        False,
    ),
    (
        "insider_cluster_buy_top500",
        "stat",
        {"obs": 0.15, "t": 0.78, "unit": "20d excess %", "type": "car"},
        "NYNY?",
        "power",
        "20 日超额 +0.15% t 0.78；原文声称量级未登记；缺角色/美元加权/10b5-1 三种变体深度",
        False,
    ),
    (
        "insider_buy_independent_broad_universe",
        "none",
        {},
        "YYNYN",
        "power",
        "原报告自述 10b5-1 排除只触及 1.6-4.0% 买入且功效不足；10b5-1 标志史仅 42 个月（2023-04 起）；短腿未测",
        True,
    ),
    (
        "ml_ranking_broad_universe_custom",
        "stat",
        {
            "obs": 0.0180,
            "t": 2.52,
            "claimed": 0.010,
            "unit": "RankIC lift vs B0 (single-IC MDE; paired SE <= sqrt2 x)",
        },
        "NYNNN",
        "depth",
        "只做阶段 1 杀伤测试，阶段 2 未用；缺数据规模/容量三点曲线；单个 RankIC 的 MDE 已高于所需提升 0.010",
        True,
    ),
    (
        "momentum_risk_control_vs_spmo",
        "none",
        {},
        "YYNY?",
        "sizing",
        "波动率目标沿同一风险收益线滑动；无统计量；owner 规则：减仓不算夏普改善",
        False,
    ),
    (
        "orb_etf_opening_range_breakout",
        "none",
        {},
        "NYN?A",
        "contract",
        "随机方向安慰剂拿到 92.7-92.9% 收益（残差是日内 beta）；论文夏普依赖零滑点+4 倍杠杆，非我们合同",
        False,
    ),
    (
        "levered_single_asset_sma_trend_gate",
        "none",
        {},
        "NYNYA",
        "contract",
        "日历平移安慰剂 100% 种子胜过真信号；40 格族整体作废；无 t 值",
        False,
    ),
    (
        "pooled_etf_relative_strength_no_menu",
        "none",
        {},
        "AYN?A",
        "internal",
        "机制退化分析（T-bill 基金 / 单股杠杆产品）；非功效问题",
        False,
    ),
    (
        "mechanical_volband_beta_grouping",
        "none",
        {},
        "AYNY?",
        "internal",
        "0/16 族过线，但 corr>=0.70 过滤在 8/8 配对改善留出夏普——重开前缺相关上限+杠杆排除规则的测试",
        False,
    ),
    (
        "reversal_trend_hourly_selection_alpha",
        "none",
        {},
        "AYN??",
        "fidelity",
        "只测了 1 小时棒；用户原始要求的 1 分钟版本代码未写",
        True,
    ),
    (
        "gtja191_alpha_formulas",
        "none",
        {},
        "NYN??",
        "power",
        "忠实移植但在近期美股衰减为零；无按公式的检验统计量；gtja017 数值发散被排除",
        False,
    ),
    (
        "lightgbm_price_volume_recipe_v1_closed",
        "none",
        {},
        "AYN??",
        "depth",
        "'特征集已耗尽' 的笔记式结论；无规模曲线；后续 ml_* 条目另有数字",
        False,
    ),
    (
        "finra_daily_short_volume_bjz",
        "stat",
        {"obs": 0.002, "t": 1.1},
        "NYNY?",
        "power",
        "5 日 IC 0.002 t 1.1；原文声称量级未登记，无法判 c5",
        False,
    ),
    (
        "activist_13d_long_horizon_hold",
        "sharpe",
        {"anchor": 0.49, "stress": 0.21},
        "YYYYN",
        "power",
        "3 个持有期（126/252/504 日），锚定窗口夏普最高 0.49、压力窗口 0.21；钱在入场前已被定价（next-open 不可得）",
        False,
    ),
    (
        "orb_stocks_in_play_relative_volume",
        "sharpe",
        {"anchor": -8.4, "anchor_years": 2.3},
        "NNNYA",
        "fidelity",
        "盘内止损顺序（one_bar_late 宽松成交使 SIP01 select -2.2% / 2026 +23.0%）与原文 tick 成交不可分；原文多空佣金口径夏普 3.75 未复现",
        False,
    ),
    (
        "monday_afternoon_reversal_index_timing",
        "sharpe",
        {"anchor": 0.63, "stress": -0.03},
        "NNNY?",
        "fidelity",
        "用 close-vs-open 代替论文 12:00-vs-open；横截面因子本身没测；SIP 分钟线（2023+）已用于别处，字面信号现在可测",
        True,
    ),
    (
        "llm_hypothesis_code_backtest_loop",
        "none",
        {},
        "NYNNN",
        "budget",
        "只跑 2 轮、12 个候选；赢家 TEST ICIR 0.197 为正号；预算（>2 轮/>12 候选）远未用尽",
        True,
    ),
    (
        "text_to_pit_feature_extraction",
        "none",
        {},
        "NNNNN",
        "power",
        "8-K risk_score 代替 10-K Item 1A，50 只股票 x 8 个季度；真实 IC 为负但与安慰剂不可分（8 个季度几乎无功效）",
        True,
    ),
    (
        "vix_term_structure_short_vol",
        "sharpe",
        {"anchor": 0.42, "stress": 0.90},
        "NNNYN",
        "fidelity",
        "无 VX 期货曲线，用已实现波动代理；锚定最优 0.42、压力最优 0.90（取各窗口最大值，偏乐观）；静态 50/50 SMH/QQQ 对照 1.20/0.89 反超",
        False,
    ),
    (
        "equity_momentum_concentrated_pwb",
        "sharpe",
        {"anchor": 1.03, "stress": 0.51},
        "NNNYN",
        "fidelity",
        "k=37/252-21 取自摘要，原论文全文细则未取得；单规格",
        False,
    ),
    (
        "dual_class_share_arbitrage_pwb",
        "sharpe",
        {"anchor": -0.015, "stress": 0.133},
        "ANNYY",
        "contract",
        "毛夏普锚定 0.50-1.05 为正，成本（冻结 10/20 bp）是约束；GOOG/GOOGL 等腿的实测价差约 2 bp 以下；缺实测报价成本合同",
        True,
    ),
    (
        "overnight_intraday_gap_retail_pwb",
        "sharpe",
        {"anchor": -3.99, "stress": -3.59},
        "YYAYY",
        "met",
        "夏普 -3.99/-3.59，远低于任何声称；成本对日往返是机制性约束，文献自己也警告",
        False,
    ),
    (
        "covered_call_cef_income_pwb",
        "sharpe",
        {"anchor": 0.8903, "stress": 0.4704, "claimed": 1.36},
        "NNNYN",
        "fidelity",
        "用 XYLD 代替已消失的 BEP 封闭基金；与 Simon (2008) 夏普 1.36 不同口径",
        False,
    ),
    (
        "skewness_preference_52wk_high_pwb",
        "sharpe",
        {"anchor": 0.82, "stress": 0.54},
        "NNNYN",
        "fidelity",
        "Blau 等 95 多/100 空的十分位切点未取得，用 k=95 近似",
        False,
    ),
    (
        "letf_published_rules_live_tracked",
        "sharpe",
        {"anchor": 0.5387, "stress": 0.4549},
        "NNNYN",
        "fidelity",
        "HFEA 按月近似季度再平衡；9Sig 不可测；LRS 未重开",
        False,
    ),
    (
        "turn_of_month_equity_seasonality",
        "sharpe",
        {"anchor": -0.6876, "stress": -0.1036},
        "NYAYY",
        "met",
        "SPY 单规则，夏普为负、其上界低于条栏；规则无规模维度（c3=A）；历史存在的五个来源并存是 c1 的缺口，故标 N",
        False,
    ),
    (
        "pre_fomc_announcement_drift",
        "sharpe",
        {"anchor": -0.8449, "stress": -1.0922, "claimed": 0.55},
        "NYANN",
        "power",
        "SPY 变体为负，但每年约 8 次 FOMC，锚定窗口只有约 20 个事件；TQQQ 变体 0.31/-0.03；原文夏普 0.5-0.6 在该长度下检出概率低",
        True,
    ),
    (
        "sectoral_intramonth_momentum",
        "sharpe",
        {"anchor": 0.26, "stress": 0.37, "claimed": 0.55},
        "NYNYN",
        "power",
        "毛夏普 0.26/0.37 对原文 0.55；毛 0.55 在 ~10 年窗口的 SE 0.32 内不能排除；换手 141.7 单位/年使成本成为主因",
        False,
    ),
    (
        "volatility_gated_momentum_aegis",
        "sharpe",
        {"anchor": 0.95, "stress": 0.57},
        "NNNYN",
        "fidelity",
        "只做步骤 1（vol 调整动量 top-50），略去极小极大相关多样化与 SLSQP Sortino 配置；是部分代理",
        False,
    ),
    (
        "s3_bear_regime_guard",
        "none",
        {},
        "AYNY?",
        "sizing",
        "无门通过 +10pt 回撤且 +0.10 夏普，含 18/20 循环平移；无统计量",
        False,
    ),
    (
        "s3_defense_first_remainder",
        "edge",
        {"windows": [(S, 0.07, 0.8)], "bar": 0.10},
        "AYNYN",
        "sizing",
        "提升 +0.07/+0.05 对门槛 +0.10；窗口 2016-2023 内夏普差的 MDE 远高于 0.10（相关系数 0.8 为假设）",
        False,
    ),
    (
        "wikipedia_pageview_attention_signal",
        "stat",
        {"obs": -0.0030, "t": -0.53},
        "NNNY?",
        "data",
        "467 个当前标普成分序列（无退市）；锚定 IC -0.0030 NW t -0.53；2016-2023 IC +0.0050 t 1.40 带幸存者偏差",
        False,
    ),
    (
        "sec_fails_to_deliver_signal",
        "stat",
        {"obs": 0.0003, "t": 0.05},
        "NNNY?",
        "data",
        "代码映射只覆盖文件行的 29.7%，其中 26.0% 被 20% 价格规则剔除；2024+ IC 0.0003 t 0.05 (20 日)",
        False,
    ),
    (
        "etf_constituent_lead_lag_reversion",
        "sharpe",
        {"anchor": 0.758, "stress": -0.223},
        "NNNYN",
        "fidelity",
        "原仓库的日换手账本未测，测的是低换手变体；LL_SOXX_K3_H5 锚定 0.758 但压力 -0.223",
        False,
    ),
    (
        "high_freq_news_return_underreaction_drift",
        "stat",
        {"obs": -0.005, "t": -0.9},
        "NYNY?",
        "power",
        "原文声称量级未登记；时间戳更早的新闻源（PR wire）未用",
        False,
    ),
    (
        "composite_momentum_quality_v1",
        "none",
        {},
        "AYNY?",
        "internal",
        "无复合优于单动量；无统计量",
        False,
    ),
    (
        "etf_dip_reversion_ibs_connors",
        "sharpe",
        {"anchor": 1.127},
        "YYNYN",
        "power",
        "最优 DIP_D1_SPY 锚定 1.127 为 K1 条的 95%；阶段 B（15:50 ET 代理 + MOC 时点）未实现；锚定窗口 MDE 高于条",
        True,
    ),
    (
        "pead_xbrl_sue_filing_date",
        "stat",
        {"obs": 0.016, "t": 1.2},
        "YNNY?",
        "fidelity",
        "按申报日而非公告日，已由 8-K 版本取代；CAR +0.71% t 3.6 但不胜过重定日期安慰剂",
        False,
    ),
    (
        "composite_momentum_roe_v2",
        "none",
        {},
        "AYNY?",
        "internal",
        "ROE 使动量账本防御而非更好；无统计量",
        False,
    ),
    (
        "momentum_daily_crash_guard",
        "none",
        {},
        "YYNYN",
        "power",
        "Daniel-Moskowitz 熊/恐慌状态与 -7% 单日停止在 2024-2026 从未触发，该机制在此窗口零功效；需含崩溃的窗口做崩溃诊断",
        True,
    ),
    (
        "paper_sleeve_combination",
        "edge",
        {"windows": [(A, 0.086, 0.79), (S, -0.001, 0.83)], "bar": 0.10},
        "AYNYN",
        "power",
        "混合相对同波动 S3 的夏普增量 +0.086/-0.001 对门槛 0.10；该长度下夏普差的 MDE 约 1.1/0.7，无法检出 0.10",
        False,
    ),
    (
        "s3_rebalance_timing_luck_tranching",
        "none",
        {},
        "AYNYA",
        "internal",
        "月底是 21 个偏移中最幸运的一个——该结论本身是功效/偏移度量，不是对策略的否定",
        False,
    ),
    (
        "chart_image_cnn_jkx_replication",
        "none",
        {},
        "NYNY?",
        "depth",
        "单个 I20/R5 模型、训练期 2016-2019（原文 1993-2000）、n=413,128；无训练规模/容量/窗口三点曲线；NW t -1.176；缺 I60 变体",
        True,
    ),
    (
        "regime_trust_uncertainty_gate_momentum_ranker",
        "none",
        {},
        "NYNY?",
        "power",
        "AUROC 0.522；无 t 值，无法计算",
        False,
    ),
    (
        "managed_futures_etf_hold_batch1_2026",
        "sharpe",
        {"anchor": 0.8157},
        "NYNYN",
        "power",
        "最优 DBMF 锚定 0.8157；F1_CTA 仅 1.46 年；单窗口",
        False,
    ),
    (
        "keller_antonacci_faber_taa_batch1_2026",
        "sharpe",
        {"anchor": 0.957, "stress": 0.6487},
        "NYNYN",
        "power",
        "9 条规则各单规格；最优 GEM 锚定 0.957",
        False,
    ),
    (
        "alt_diversifier_etf_hold_batch1_2026",
        "sharpe",
        {"anchor": 0.9203},
        "NYNYN",
        "power",
        "F3_UPAR 仅 1.62 年；单窗口",
        False,
    ),
    (
        "step10_beta_exposure_vol_managed_router",
        "none",
        {},
        "AYNY?",
        "internal",
        "0/24；冻结门含 sharpe_excess_bil>1.0 与 CAGR 超额>=5pp；无 t 值，无法计算",
        False,
    ),
    (
        "step10_cross_asset_trend_tsmom_etf",
        "none",
        {},
        "AYNY?",
        "internal",
        "0/12；最佳 CAGR 超额 +1.33pp、sharpe_excess_bil 0.65；无 t 值",
        False,
    ),
    (
        "step10_xsmom_pit_liquidity_liquid500",
        "none",
        {},
        "AYNY?",
        "internal",
        "0/4；已做幸存者偏差复测（非实质）；无 t 值",
        False,
    ),
    (
        "step10_sleeve_combination_beta_crossasset",
        "none",
        {},
        "AYNY?",
        "internal",
        "组合改善 sharpe_excess_bil 至 0.743、CAGR 超额 +2.44pp 但未过门；第三个袖子因相关性排除",
        False,
    ),
    (
        "core_satellite_momentum_sector_etf_r7",
        "none",
        {},
        "ANNN?",
        "fidelity",
        "StrategySpec 未编码多标的目标权重行为、折叠成本边界未冻结 —— 合同无效；DSR 0.578",
        True,
    ),
    (
        "dynamic_theme_semantic_chain_momentum",
        "none",
        {},
        "AYY??",
        "depth",
        "17 轮（R8-R24）均未过开发门；DSR 0.035；终止指令已下；模态未变（价格变换）",
        False,
    ),
    (
        "etf_structural_family_daily_r9",
        "none",
        {},
        "ANNN?",
        "fidelity",
        "冻结的 BIL 原始夏普 9.38 作为风险策略门槛——原记录自己也标为方法上有疑；R9D04 夏普 0.967",
        True,
    ),
    (
        "multiscale_intraday_event_r5",
        "none",
        {},
        "ANN??",
        "data",
        "无不可变的历史新闻/文本档案，LLM 输出无法回填；确定性路径安慰剂未过",
        False,
    ),
    (
        "multiscale_low_turnover_etf_r6",
        "none",
        {},
        "ANNN?",
        "fidelity",
        "D01-D04 违反 40% 单标的上限、D02-D05 非自融资记账：无合同有效的历史结果",
        True,
    ),
    (
        "robust_momentum_deterministic_ml_r4",
        "none",
        {},
        "ANN??",
        "data",
        "全部为当前宇宙（幸存者偏差）诊断；缺 PIT 成分、退市收益、公司行动谱系",
        True,
    ),
    (
        "spy_dual_trend_core_r8",
        "none",
        {},
        "AYNY?",
        "power",
        "夏普 0.737 对匹配 40/60 SPY-现金 0.887；DSR 0.075；SIP/IEX 转换门失败；净 40.46%",
        False,
    ),
    (
        "nasdaq_long_short_event_router_1m",
        "sharpe",
        {"anchor": -0.126, "anchor_years": 2.72, "claimed": 0.33},
        "YNNNY",
        "fidelity",
        "做空腿从未触发（top_n=1 时空头榜与多头榜相同）——测的是仅多头的开盘抄底；压力窗口 2016-2023 无分钟数据（待办）",
        True,
    ),
    (
        "multiasset_ml_ranking_vs_12_1_baseline",
        "none",
        {},
        "AYNY?",
        "depth",
        "R1-R3、R7 四轮；特征/标签变化不是规模曲线；4 折",
        False,
    ),
    (
        "tqqq_post_drawdown_reentry_router",
        "none",
        {},
        "ANNN?",
        "fidelity",
        "判定依赖 qqq_capture_ratio（登记册 step10 条目记录该复合式度量对 beta<1 策略不可通过且 09-04 后修正）；本条 09-02/03 复核是否按修正口径重算待核对",
        True,
    ),
    (
        "pdr_router_ml_gate",
        "none",
        {},
        "AYNY?",
        "power",
        "walk-forward 2/6、1/6 胜；6 折；无 t 值",
        False,
    ),
    (
        "single_etf_intraday_momentum_cost_adjusted",
        "none",
        {},
        "YYNY?",
        "power",
        "18 组合有效 N=3，无净夏普；无 t 值",
        False,
    ),
    (
        "ml_ranking_liquid500_recent_vs_momentum_rule",
        "none",
        {},
        "AYNY?",
        "depth",
        "480 项筛选 + 若干模型格；无规模/容量曲线；比较是 CAGR，无 t 值",
        False,
    ),
    (
        "reversal_trend_user_indicator",
        "none",
        {},
        "AYNY?",
        "fidelity",
        "18 格 0/18；1 分钟版本代码未写（用户原始要求）",
        True,
    ),
    (
        "baseline_chain_b0_b1_b2_market_neutral_vs_long",
        "none",
        {},
        "AYYY?",
        "internal",
        "B0-B3 四级模型容量阶梯（深度点已有）；B1 4/8 门；功效/置信区间未报",
        False,
    ),
    (
        "owner_chatgpt_systematic_investing_news_momentum_2026",
        "none",
        {},
        "NNNY?",
        "data",
        "缺 PIT 市值权重特征；新闻密度不足，论文最优的回看/标题上限无法匹配",
        False,
    ),
    (
        "owner_azevedo_hoegner_ml_anomalies_2023",
        "none",
        {},
        "NNNNN",
        "fidelity",
        "类比判定：未直接测该论文的 GLM/ML 方案；登记册自述依据是同机制的本地测试",
        True,
    ),
    (
        "lgbm_price_volume_ranking_small_caps",
        "sharpe",
        {"anchor": 0.333},
        "YYYYN",
        "power",
        "多模型族 x 2 池子 x 21 偏移 x 2 窗口，深度点充足；最优锚定 0.333 对 1.19；DSR(30) 0.009-0.083；锚定窗口 MDE 高于条",
        False,
    ),
    (
        "factor_style_etf_momentum_rotation",
        "sharpe",
        {"anchor": 1.437, "stress": 0.405},
        "NYNYN",
        "power",
        "5 个候选过锚定-only 条但过不了压力；锚定 1.437 的 SE 约 0.6",
        False,
    ),
    (
        "narrow_industry_etf_momentum_rotation",
        "sharpe",
        {"anchor": 0.987},
        "NYNYN",
        "power",
        "12 个候选 0 过；最优锚定 0.987",
        False,
    ),
    (
        "option_expiration_week_calendar_effect",
        "sharpe",
        {"anchor": -0.176, "stress": 0.038},
        "NYAYY",
        "met",
        "8 个主候选夏普均为负/近零，且 2 周安慰剂更好；规则无规模维度",
        False,
    ),
    (
        "congressional_political_trade_replica_etf_rotation",
        "sharpe",
        {"anchor": 0.9015},
        "NYNYN",
        "power",
        "NANC/GOP 2023-02 才上市，无压力窗口；24 个候选最优锚定 0.9015",
        False,
    ),
    (
        "etf_pair_relative_strength_switch",
        "sharpe",
        {"anchor": 1.2848, "stress": 0.7679},
        "NYNYN",
        "power",
        "SMH/QQQ 候选过 K1 本身，被静态 50/50 对照（压力 0.8882）降级；分辨 0.77 与 0.89 需要远超 7 年",
        False,
    ),
    (
        "letf_close_rebalancing_flow_reversal",
        "sharpe",
        {"anchor": 0.796},
        "YYNYN",
        "power",
        "真信号胜过随机日安慰剂（SMH 0.796 对 -0.237）——机制方向为真，经济量级小",
        False,
    ),
    (
        "pre_holiday_effect_small_cap_tier",
        "sharpe",
        {"anchor": -0.81, "stress": -0.43},
        "NNAYY",
        "fidelity",
        "用 ETF（IWM/IJR 等）代替 Ko & Yang 的 CRSP 十分位个股；夏普为负且劣于随机安慰剂",
        False,
    ),
    (
        "merger_arbitrage_target_announcement_drift",
        "stat",
        {"obs": -0.75, "t": -2.36, "unit": "20d CAR %", "type": "car"},
        "YNAYA",
        "contract",
        "溢价在入场前已被定价（-5..-1 日 +5.7%、0 日 +17%）；持有至交割/价格-报价比版本因无免费数据未测",
        False,
    ),
    (
        "insider_cluster_buy_top500_weekly_independent",
        "stat",
        {"obs": 0.15, "t": 0.78, "unit": "20d excess %", "type": "car"},
        "NYNY?",
        "power",
        "同 insider_cluster_buy_top500（9,352 事件）；原文声称量级未登记",
        False,
    ),
    (
        "ipo_lockup_expiration_drift",
        "sharpe",
        {"anchor": 0.419},
        "NNNYN",
        "fidelity",
        "事件表 20 样本核查 6/20 非普通股或错配（30%，过滤前上界）；180 日近似代替合同解禁日",
        True,
    ),
    (
        "news_vs_nonews_drop_reversal",
        "sharpe",
        {"anchor": 0.67},
        "NYNYN",
        "power",
        "12 个候选；仅 8-K 2.02 条目新闻；DSR <= 0.178",
        False,
    ),
    (
        "crypto_weekend_to_monday_equity_transmission",
        "none",
        {},
        "YYAY?",
        "contract",
        "周末效应在周五收盘-周一开盘复现（QQQ -51..-62 bp, t -3.0..-4.6）但开盘前已定价；Alpaca 周日 20:00 ET 夜盘填单未测",
        True,
    ),
    (
        "small_cap_background_drift_short_basket",
        "sharpe",
        {"anchor": 0.390, "stress": 0.554, "claimed": 1.35},
        "NNNNN",
        "fidelity",
        "只做 ETF 层（步骤 1），步骤 2 个股篮子因无借券费历史未做；原文个股夏普 1.35 不可用免费 ETB 对冲复现",
        True,
    ),
    (
        "ml_multiquarter_sue_history",
        "sharpe",
        {"anchor": 0.60, "stress": 0.38},
        "NYNYN",
        "power",
        "ENET_TOP50 劣于 SUE1 0.88、MOM 1.10、标签打乱 0.68；4/8 年度模型全零",
        False,
    ),
    (
        "dolthub_free_options_eod_chain_data",
        "none",
        {},
        "AAAYA",
        "data_acceptance",
        "这是数据源验收失败（覆盖 0.54-0.62 对 0.85），不是对方向的功效检验；仅 2024-09-04 起稠密",
        True,
    ),
    (
        "net_share_issuance_pontiff_woodgate_recent",
        "stat",
        {"obs": 0.0106, "t": 0.81, "claimed": 0.019},
        "YYNYN",
        "power",
        "全样本 IC +0.019 (t 2.06) 在 2020-2023；2024+ 窗口的 MDE 高于该全样本效应，无法确认其衰减",
        False,
    ),
    (
        "ipo_quiet_period_expiry_and_post_pop_drift",
        "stat",
        {"obs": -1.40, "t": -2.21, "unit": "net %", "type": "car"},
        "NYNY?",
        "power",
        "399 个 IPO；A 腿净 -1.40% t -2.21；B 空腿 2024+ 仅 n=13",
        False,
    ),
    (
        "pension_rebalancing_front_run_equity_leg",
        "stat",
        {
            "obs": -0.400,
            "t": -0.84,
            "claimed": 0.520,
            "unit": "SPY ID coef, anchor 2024-01-08+; claimed = own full-sample -0.520 (results.json regression_table)",
        },
        "YYNYN",
        "power",
        "2024+ 系数 -0.400（HC3 SE 0.476，t -0.84）与全样本 -0.520（t -2.84）同号同量级——并未反驳；2.7 年窗口的 MDE 1.18 高于 0.52，只是看不见",
        True,
    ),
    (
        "tax_loss_selling_year_end_rebound",
        "stat",
        {"obs": 0.94, "t": 0.69, "claimed": 1.5, "unit": "%", "type": "car"},
        "NYNYN",
        "power",
        "年度聚类 t 0.69（仅 10 个年份）；MDE 高于冻结的 +1.5% 门槛",
        False,
    ),
    (
        "smallcap_gap_down_fade_auction_execution",
        "stat",
        {"obs": -5.4, "t": -1.03, "claimed": 42.5, "unit": "bp/day"},
        "YNNYY",
        "fidelity",
        "C1 的 +42.5 bp 是前视条件子集；盘前 SIP 棒只覆盖池子 35%；缺实时 SIP 盘前数据；未测极端缺口规则（事后设计）",
        False,
    ),
    (
        "front_running_industry_etf_seasonality",
        "sharpe",
        {"anchor": 1.12},
        "NYNYN",
        "power",
        "6 格；缺 20 年同月均值（KLN 原文口径）的更长价格史",
        False,
    ),
    (
        "overnight_return_persistence_auction",
        "stat",
        {"obs": -5.88, "t": -2.70, "claimed": 4.0, "unit": "bp/night delta_lo20"},
        "YYYYN",
        "power",
        "门 A 在未见股票通过（+13.69 bp/夜 t 5.19）；门 B 官方开盘拍卖价 20 个种子日 1,958 对，delta -5.88 对门槛 -4，SE 2.18 的 MDE 5.4 高于 4；缺上市交易所开盘集合竞价价源",
        True,
    ),
    (
        "intraday_same_slot_periodicity",
        "none",
        {},
        "YYAYA",
        "met",
        "毛边际 17.1 bp 主要是日线/分钟线股息复权基准错配；剔除后 2.3 bp，实测报价后净 -16.1 bp；成本是直接测量",
        False,
    ),
    (
        "dash_for_cash_settlement_timing",
        "none",
        {},
        "YYNY?",
        "power",
        "M3 单日位移复现 (theta 125.7 bp, t 3.05)；M1 pre-window D1 -7.66 bp NW t -0.86（SE 约 8.9 bp，MDE 约 22 bp）；6 日窗口缺独立机构流数据",
        False,
    ),
    (
        "prediction_market_earnings_beat_odds",
        "stat",
        {"obs": 0.019139, "t": 0.43},
        "NNNYN",
        "power",
        "620 事件/30 周，周 IC 0.019 t 0.43，最小可检出 0.110；原论文只读到二手报道（页面 403），行业调整版与结束时点代理未跑；"
        "单一通道（15:00 ET 的 P）；重开：约 450 个新事件或不同通道（公告日盘中赔率变化）",
        True,
    ),
    (
        "prediction_market_policy_odds_leadlag_glw2026",
        "sharpe",
        {"anchor": -1.20, "anchor_years": 0.98, "claimed": 1.95},
        "NYNYN",
        "power",
        "窗口 0.98 年 27 个资产；回归 5.0 bp/pp (t 0.91) 对论文 13 bp/pp：MDE(5.5 x 2.486 = 13.7) 约等于论文效应；前向影子到 2026-11-04 在继续",
        True,
    ),
]


def load_current() -> dict[str, dict]:
    cur: dict[str, dict] = {}
    for line in DIRECTIONS.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            cur[row["id"]] = row
    return cur


def audit_entry(row: dict, entry: tuple) -> dict:
    dirid, kind, data, codes, cls, need, cand = entry
    c = {f"c{i + 1}": ch for i, ch in enumerate(codes)}
    mde: dict | str
    if kind == "sharpe":
        mde = sharpe_block(data)
    elif kind == "stat" and data.get("obs") is not None:
        mde = stat_block(data)
    elif kind == "edge":
        mde = edge_block(data)
    else:
        mde = "无法计算：原结果缺必要数字（无检验统计量或样本长度）"
    if isinstance(mde, dict) and mde.get("c5_auto"):
        c["c5"] = mde["c5_auto"]
    p1_met = all(v in ("Y", "A") for v in c.values())
    if cls == "met" and not p1_met:
        cls = "repro"  # c1 not met while the rest holds: the original result was not reproduced
    not_applicable = cls == "data_acceptance"
    blocking = [k for k, v in c.items() if v in ("N", "?") and k != "c3"]
    missing = []
    if c["c1"] in ("N", "?"):
        missing.append("复现原文结果（相对结论/曲线形状）")
    if c["c2"] in ("N", "?"):
        missing.append("忠实实现")
    if c["c3"] in ("N", "?"):
        missing.append("至少三个深度点的规模曲线")
    if c["c4"] in ("N", "?"):
        missing.append("用完事先写定的迭代预算")
    if c["c5"] in ("N", "?"):
        missing.append("功效分析：检验能看到声称的效应")
    evidence = [p for p in row.get("evidence", []) if (ROOT / p).exists()]
    observed: dict | str = {}
    if isinstance(mde, dict):
        observed = {
            k: v
            for k, v in mde.items()
            if k.startswith("observed") or k in ("t", "upper95_one_sided")
        }
    return {
        "id": f"dir:{dirid}",
        "original_status": row["status"],
        "original_verdict": row.get("verdict", "")[:400],
        "p1_conditions": c,
        "p1_met": p1_met and not not_applicable,
        "new_label": (
            "P-1不适用（数据源验收失败，不是对方向的检验）"
            if not_applicable
            else "满足P-1（机械判定）"
            if p1_met
            else "未到深度"
        ),
        "p1_not_applicable": not_applicable,
        "only_c3_missing": (not p1_met) and not blocking,
        "blocking_conditions_other_than_c3": blocking,
        "gap_class": cls,
        "min_detectable_effect": mde,
        "observed": observed or "见 original_verdict",
        "missing_depth_points": missing,
        "what_is_missing_specifically": need,
        "source_report": evidence[0] if evidence else (row.get("evidence") or [""])[0],
        "source_report_exists": bool(evidence),
        "reopen_candidate_pending_lead_review": cand,
    }


def self_test() -> dict:
    # plan v2 section 1 detection-probability table (T = 2.73 years, t >= 1.96)
    from statistics import NormalDist

    nd = NormalDist()
    plan = {0.5: 13, 1.0: 38, 1.5: 70, 2.0: 91}
    got = {sr: round(100 * nd.cdf(sr * math.sqrt(2.73) - 1.96)) for sr in plan}
    pm = round(K * 0.019139 / 0.43, 4)
    return {
        "plan_detection_table_reproduced": got == plan,
        "computed": got,
        "pm_earnings_mde_from_t": pm,
        "pm_earnings_mde_reported": 0.11007,
        "anchor_years": round(ANCHOR_YEARS, 3),
        "stress_years": round(STRESS_YEARS, 3),
    }


def k2_table() -> list[dict]:
    rows = []
    for years, label in (
        (ANCHOR_YEARS, "anchor"),
        (STRESS_YEARS, "stress"),
        (ANCHOR_YEARS + STRESS_YEARS, "pooled"),
    ):
        for rho in (0.5, 0.8):
            se = math.sqrt(2 * (1 - rho) / years)
            rows.append(
                {
                    "window": label,
                    "years": round(years, 2),
                    "rho": rho,
                    "se": round(se, 3),
                    "mde_80": round(K * se, 3),
                }
            )
    return rows


def main() -> None:
    cur = load_current()
    refuted = [i for i, r in cur.items() if r["status"] == "refuted"]
    listed = [f"dir:{e[0]}" for e in ENTRIES]
    missing = sorted(set(refuted) - set(listed))
    extra = sorted(set(listed) - set(refuted))
    dup = sorted({x for x in listed if listed.count(x) > 1})
    assert not missing and not extra and not dup, (missing, extra, dup)
    entries = [audit_entry(cur[f"dir:{e[0]}"], e) for e in ENTRIES]
    n_under = sum(1 for e in entries if not e["p1_met"] and not e["p1_not_applicable"])
    out = {
        "task": "T-20261005-35",
        "audited_at": "2026-10-06",
        "scope": "all directions whose last registry row has status=refuted (not evidence_too_weak / not_executable: those were never tested)",
        "method": "see compute.py docstring; numbers come from the registry verdict text, which copies the cited report; key figures spot-checked against results.json",
        "conventions": {
            "K": K,
            "z95": Z95,
            "anchor_years": round(ANCHOR_YEARS, 3),
            "stress_years": round(STRESS_YEARS, 3),
        },
        "self_test": self_test(),
        "k2_sharpe_difference_mde": k2_table(),
        "counts": {
            "audited": len(entries),
            "under_depth": n_under,
            "p1_met": sum(1 for e in entries if e["p1_met"] and not e["p1_not_applicable"]),
            "p1_not_applicable": sum(1 for e in entries if e["p1_not_applicable"]),
            "only_c3_missing": sum(1 for e in entries if e["only_c3_missing"]),
            "reopen_candidates_pending_lead_review": sum(
                1 for e in entries if e["reopen_candidate_pending_lead_review"]
            ),
            "mde_computed": sum(1 for e in entries if isinstance(e["min_detectable_effect"], dict)),
            "mde_not_computable": sum(
                1 for e in entries if not isinstance(e["min_detectable_effect"], dict)
            ),
            "by_gap_class": {},
        },
        "entries": entries,
    }
    for e in entries:
        out["counts"]["by_gap_class"][e["gap_class"]] = (
            out["counts"]["by_gap_class"].get(e["gap_class"], 0) + 1
        )
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(out["counts"], ensure_ascii=False), out["self_test"])


if __name__ == "__main__":
    main()
