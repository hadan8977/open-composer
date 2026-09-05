# Step 10 Wave 1 / F2: 跨资产 ETF 趋势配置

计划：`docs/plan-step-10-mechanism-supplementation-2026-09-03.zh.md` 第 4.2 节。
账本：`reports/research/control/step10-2026-09-04-progress.md`（捕获比定义修正的完整数学推导见账本新增小节，本报告只给结论）。
证据 JSON（本地，未入库）：`reports/research/control/step10-w1-cross-asset-trend-2026-09.json`（2026-09-05 用修正后的 `mechanism_eval.py` 重新跑出）。
迭代档案：`reports/research/iterations/step10_w1_cross_asset_trend/`（轻量路径，`status: ok`）。
来源卡：`reports/harness/source_cards/step10_w1_cross_asset_trend.jsonl`（8 条）。

## 结论（先说结果）

**0/12 候选通过新合同。** 与 F1 同一模式：捕获比定义修正后 9/12 通过了 `benchmark_vm_capture_ratio` 门（修正前 0/12），但 `cagr_excess_vol_matched_benchmark`（门槛 ≥5pp）与 `sharpe_excess_bil`（门槛 >1.0）仍然 12/12 全部不过。旧合同下同样 0/12 通过。**负结论不变**：月度轮动确实降低了波动/回撤，但用风险匹配后的 SPY 基准比较后，超额收益不达标。

## 路由可行性核查（先查后定，计划要求）

`core_beta_satellite_router` **不能表达**这个机制，走独立内核机制评估（研究轨道，本周不接入模拟盘）。原因（详见 `open_composer/research/kernel/mechanisms/cross_asset_trend_etf.py` 模块 docstring）：`core_route_label()` 把 `onTQQQ.../offCASH0` 硬编码进 f-string，选不了标的；`universe_mode` 只是描述字符串，`_target_snapshot` 从不读取；卫星仓位是叠加在核心之上的 10% 战术仓，不是本机制需要的主体仓位；主题门用单一硬编码标的做总开关；`offCASH0` 是字面 0% 收益，不是 BIL 真实收益率。这些都需要重写路由核心逻辑，不是改参数能绕过的。

## 方法

- 标的：`SPY, QQQ, IWM, EFA, EEM, TLT, IEF, GLD, DBC, VNQ` + 现金腿 `BIL`，`daily_returns_on_naive_dates` 内连接，2016-01-05 至 2026-09-04，2683 个公共交易日。
- 机制：月末对每个 ETF 用**自身**过去 `lookback_months∈{6,12}` 个月总收益判正负（时间序列动量，非横截面排名），正的按动量高低排前 `top_n∈{3,5,all=10}`，权重 `weighting∈{equal, inverse_vol_60d}`；网格 2×3×2=12 组。**实现选择**（计划文本未明确，已记录）：`top_n` 是槽位数，未选满的槽位持有 BIL（标准 GTAA/双动量惯例），不是"10 只固定权重、选中的才替换"的读法。成本 5bps/边、压力 40bps。
- 评估：`scripts/evaluate_cross_asset_trend_sip.py`，方法与 F1 完全一致（`fold_count=5`、两遍 DSR：探路 12 → `effective_n=1`，`breadth_ratio≈0.083` → 正式试验数下限 2；CRISIS_WINDOWS + 选择后诊断）。裁定基准统一为 **SPY**（计划明确指定，不像 F1 按候选自身标的）。
- 单测中发现并修复的真实 bug（修复前的一次跑批已作废重跑）：`_month_end_positions` 过滤条件误用"交易日下标"而非"月份下标"比较，导致月份数不足时 `month_end_positions[month_idx - lookback_months]` 用 Python 负数下标绕到列表末尾，把最近月份错当成回看起点，污染最早几次换仓的动量判断。修复后 `tests/test_cross_asset_trend_etf.py` 8/8 通过。

## 捕获比定义修正

同 F1：`benchmark_vm_capture_ratio`/`benchmark_vm_downside_capture` 原先用 `campaign._conditional_capture`（总复利收益之比，在长窗口上随窗口长度指数衰减，任何 beta<1 候选都会被压到远低于其真实捕获能力），改为每期几何平均收益之比（`_conditional_geometric_mean_capture`，Morningstar 惯例，对窗口长度不敏感）后，9/12 候选的 `benchmark_vm_capture_ratio` 从不通过变为通过（新值 0.98-1.06 区间，旧定义值 0.32-0.71 区间，见下表 `cap_new`/`cap_legacy` 并列）。这只是修正了衡量口径，候选真实的超额收益表现未变。

## 门槛通过分布（新合同，12 候选）

| 门槛 | 通过数 | 备注 |
|---|---:|---|
| `dsr_probability` | 12/12 | |
| `max_drawdown` | 12/12 | |
| `positive_fold_fraction` | 12/12 | |
| `benchmark_vm_downside_capture` | 12/12 | |
| `benchmark_vm_capture_ratio` | **9/12**（修正前 0/12） | 本次修正的直接效果；3 组权重更集中/`top_n` 更小的仍不过 |
| `mar` | 9/12 | 3 组不过 |
| `cagr_excess_vol_matched_benchmark` | **0/12** | 门槛 ≥5pp，最好 +1.33pp |
| `sharpe_excess_bil` | **0/12** | 门槛 >1.0，最好 0.65 |

## 全部 12 候选（按超额 CAGR 排序，`cap_new`/`cap_legacy` 为捕获比新旧定义并列）

| lookback | top_n | weighting | cagr | 超额CAGR(vm) | cap_new | cap_legacy | downside | sharpe_ex_bil | mar | mdd | w | 通过？ |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 6 | 5 | equal | 11.08% | +1.33pp | 1.058 | 0.5915 | 0.782 | 0.648 | 0.994 | -11.1% | 0.657 | 否 |
| 12 | 5 | inv_vol | 11.52% | +1.22pp | 1.047 | 0.5909 | 0.806 | 0.631 | 0.800 | -14.4% | 0.724 | 否 |
| 12 | 5 | equal | 11.58% | +1.09pp | 1.041 | 0.6016 | 0.821 | 0.619 | 0.784 | -14.8% | 0.749 | 否 |
| 6 | 5 | inv_vol | 10.34% | +0.77pp | 1.049 | 0.5969 | 0.787 | 0.607 | 0.924 | -11.2% | 0.635 | 否 |
| 12 | 3 | equal | 11.45% | +0.55pp | 1.044 | 0.4608 | 0.761 | 0.579 | 0.622 | -18.4% | 0.799 | 否 |
| 12 | all | equal | 8.49% | +0.14pp | 1.038 | 0.7028 | 0.812 | 0.558 | 0.801 | -10.6% | 0.490 | 否 |
| 12 | 3 | inv_vol | 10.45% | -0.28pp | 1.031 | 0.4636 | 0.767 | 0.525 | 0.512 | -20.4% | 0.778 | 否 |
| 6 | all | equal | 6.89% | -0.94pp | 1.015 | 0.6894 | 0.803 | 0.427 | 1.129 | -6.1% | 0.430 | 否 |
| 12 | all | inv_vol | 6.75% | -0.98pp | 1.012 | 0.7079 | 0.815 | 0.418 | 0.760 | -8.9% | 0.419 | 否 |
| 6 | all | inv_vol | 5.50% | -1.88pp | 0.989 | 0.6760 | 0.795 | 0.276 | 0.962 | -5.7% | 0.380 | 否 |
| 6 | 3 | inv_vol | 6.79% | -3.85pp | 0.983 | 0.3469 | 0.723 | 0.278 | 0.505 | -13.4% | 0.767 | 否 |
| 6 | 3 | equal | 6.92% | -3.91pp | 0.985 | 0.3247 | 0.713 | 0.283 | 0.472 | -14.6% | 0.791 | 否 |

## 最好的候选：`lookback_months=6, top_n=5, weighting=equal`

| 指标 | 值 |
|---|---:|
| 平均持仓天数 | 104.1 天 |
| 在场天数占比 | 98.3% |
| 年化换手事件数 | 10.9 |
| 换仓次数（round trips） | 110 |
| 旧合同 `promotion_eligible` | False |

**选择后窗口诊断**（2026-07-09 至 2026-09-04，42 个交易日，非门槛）：CAGR **+27.6%**，同期 SPY 基准 +21.7%，Sharpe 2.54——近期跑赢，但样本仅 42 天，且不是本轮 5-fold 走查已经检验过的窗口的一部分，不构成额外裁定依据，只如实记录。

**危机窗口诊断**（非门槛）：2022 全年 -10.09%（SPY -18.17%）；2020 疫情崩盘 -12.52%（SPY -33.48%）；2018Q4 -8.13%（SPY -13.43%）——三个窗口都跌得比 SPY 少，但这正是"波动率匹配基准"要控制的那类效应（候选波动率约为 SPY 的 66%，`w=0.657`），不能作为独立于 CAGR/Sharpe 门槛之外的加分项。

## 数据来源与可复现性

`gate_contract_sha256`：新合同 `a8431ca4e6d8936eb16eb49a2f004962d94ba801919a4afb889a195f5493d157`，旧合同 `3b3ce418b64056005d0c6143af4155b8c2d0b85a66db9b83c1ebf99ab47a9c9b`。重跑命令：
```
export PATH="$HOME/.local/bin:$PATH"; export UV_CACHE_DIR=/tmp/open-composer-uv-cache
uv run python scripts/evaluate_cross_asset_trend_sip.py
```
