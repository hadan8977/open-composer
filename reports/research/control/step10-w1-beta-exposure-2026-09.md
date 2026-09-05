# Step 10 Wave 1 / F1: 波动率管理的 beta 暴露路由（`beta_exposure_router`）

计划：`docs/plan-step-10-mechanism-supplementation-2026-09-03.zh.md` 第 4.1 节。
账本：`reports/research/control/step10-2026-09-04-progress.md`（本报告是该账本 Wave 1/F1 小节的正式产物；捕获比定义修正的完整数学推导见账本新增小节，本报告只给结论）。
证据 JSON（本地，未入库，`reports/research/control/*.json` 属仓库既有的 gitignore 白名单外文件）：`reports/research/control/step10-w1-beta-exposure-2026-09.json`（2026-09-05 用修正后的 `mechanism_eval.py` 重新跑出）。
迭代档案：`reports/research/iterations/step10_w1_beta_exposure/`（轻量路径，`status: ok`，`warnings: [lightweight_single_mechanism_exemption_used]`）。
来源卡：`reports/harness/source_cards/step10_w1_beta_exposure.jsonl`（8 条，复用本仓库 `mom_breadth_qd_r1` 已核实文献）。

## 结论（先说结果）

**0/24 候选通过新合同（`config/promotion/unlevered-family-paper-tier-gates.json`）。** 捕获比定义修正后，24/24 候选都通过了 `benchmark_vm_capture_ratio`/`benchmark_vm_downside_capture` 两道捕获门（修正前是 0/24），但 `cagr_excess_vol_matched_benchmark`（相对波动率匹配基准的超额 CAGR，门槛 ≥5pp）与 `sharpe_excess_bil`（门槛 >1.0）仍然 24/24 全部不过。旧合同（`kernel-paper-tier-gates.json`，仅作参照，不裁定）下同样 0/24 通过。**负结论不因本次修正改变**：路由的趋势/回撤/波动率门控确实压低了名义敞口和回撤，但去杠杆本身不产生超额收益，换成风险匹配的比较基准后这一点看得更清楚。

## 方法

- 数据：`load_beta_router_dataset(..., data_source="sip_parquet")`，SIP 日线 2016-01-04 至 2026-09-04，QQQ/SPY 均 2684 个公共交易日。
- 网格（24 组，写死于 `candidate-manifest.json`，未增删）：`market ∈ {QQQ, SPY} × trend_sma_days ∈ {100, 200} × target_volatility_annual_pct ∈ {10, 15, none} × max_drawdown_pct ∈ {none, -15}`。固定：`momentum_lookback_days=60, min_momentum_pct=0, volatility_lookback_days=20, max_volatility=none, drawdown_lookback_days=60`，不加杠杆（`leverage_* = none`），`risk_on = market@1.0, neutral = market@0.5, risk_off = BIL@1.0`。
- 评估：`scripts/evaluate_beta_exposure_family_sip.py`，`fold_count=5` 滚动起点折叠、5 bar 禁运；成本 5bps/边（压力 40bps）；DSR 两遍（探路 24 → `effective_n=1`，`breadth_ratio≈0.042`，24 组高度相关聚成 1 个有效独立试验 → 正式试验数取 `max(1, 2)=2` 下限）；CRISIS_WINDOWS（2018Q4、2020 疫情、2022 全年）+ 选择后窗口（2026-07-09 起）为纯诊断，不参与裁定。
- 裁定：`evaluate_candidate(..., benchmark_returns=候选自身的 risk_on_symbol 序列, benchmark_name=risk_on_symbol)`，即 QQQ 候选比 QQQ、SPY 候选比 SPY，按波动率匹配后的基准 `benchmark_vm = w·benchmark + (1-w)·BIL` 评估（`w = 候选已实现波动率 / 基准已实现波动率`，w>1 表示按 BIL 利率融资加杠杆匹配基准）。

## 捕获比定义修正（结论如何变化）

`benchmark_vm_capture_ratio`/`benchmark_vm_downside_capture` 原先复用 `campaign._conditional_capture`——把候选和基准在"基准上涨/下跌"两个子集上各自的**总复利收益**相除。在 2016-2026 这种上千行的拼接 OOS 窗口上，这个比值会随窗口长度指数级收缩，与真实的"捕获不对称性"无关：一个零 alpha、beta=0.5 的基准复制品（本该读作捕获比 ≈1.0，因为上行下行都按比例打五折，比值相互抵消）在旧定义下会被算成 ≈0.06-0.2（见 `tests/test_mechanism_eval.py::test_geometric_mean_capture_ratio_is_beta_invariant_unlike_the_compounded_one`，24 个候选里最好的 C12 修正前也正是 0.2007，见下表 `cap_legacy` 列）。本项目所有候选恰好都是"部分暴露、beta<1"的构造（趋势/波动率/回撤门控只会降低敞口），所以旧定义系统性地让这整个族看起来"完全没有捕获上行的能力"，而这其实是窗口长度的定义artefact，不是候选的真实缺陷。

修正后的 `benchmark_vm_upside_capture`/`benchmark_vm_downside_capture` 改用**每期几何平均收益**之比（`_conditional_geometric_mean_capture`，Morningstar 惯例，对窗口长度不敏感），`benchmark_vm_capture_ratio_compounded_legacy` 字段保留旧定义作对照，从不参与裁定。修正后 24/24 通过捕获门，符合预期——但这只是把一个失真的门槛修正为能正确衡量的门槛，候选本身的经济表现（超额 CAGR、Sharpe-ex-BIL）完全没变，而这两道门才是真正卡住这个族的门槛。

## 门槛通过分布（新合同，24 候选）

| 门槛 | 通过数 | 备注 |
|---|---:|---|
| `dsr_probability` | 24/24 | |
| `max_drawdown` | 24/24 | -35%（QQQ/SPY 十年最差回撤）以内 |
| `positive_fold_fraction` | 24/24 | |
| `benchmark_vm_capture_ratio` | **24/24**（修正前 0/24） | 本次修正的直接效果 |
| `benchmark_vm_downside_capture` | 24/24 | |
| `mar` | 13/24 | 11 组不过 |
| `cagr_excess_vol_matched_benchmark` | **0/24** | 门槛 ≥5pp，最好 +0.99pp |
| `sharpe_excess_bil` | **0/24** | 门槛 >1.0，最好 0.59 |

## 最好的候选：C12

`label = beta:sma200_mom60_min0_vol20_maxvnone_dd60_maxdd-15_..._onQQQ1_neuQQQ0.5_offBIL1_vtnone`（QQQ、SMA200 趋势、-15% 回撤止损、不设波动率目标）。

| 指标 | 值 | 门槛 | 通过？ |
|---|---:|---:|---|
| `cagr`（候选原始 CAGR） | 11.86% | — | — |
| `cagr_excess_vol_matched_benchmark` | **+0.99pp** | ≥5pp | 否 |
| `sharpe_excess_bil` | **0.589** | >1.0 | 否 |
| `benchmark_vm_capture_ratio`（新定义） | 1.116 | ≥1.0 | 是 |
| `benchmark_vm_capture_ratio_compounded_legacy`（旧定义，仅对照） | 0.201 | — | — |
| `benchmark_vm_downside_capture` | 0.536 | ≤1.0 | 是 |
| `mar` | 0.762 | ≥0.6 | 是 |
| `max_drawdown` | -15.58% | ≥-35% | 是 |
| `vol_match_weight`（w） | 0.620 | — | 候选波动率是基准的 62% |
| `dsr_probability` | 0.770 | ≥0.5 | 是 |
| 在场天数占比 | 100.0% | — | 诊断 |
| 年化换手事件数 | 11.9 | — | 诊断 |
| 平均持仓天数 | 21.2 天 | — | 诊断 |
| 旧合同（`kernel-paper-tier-gates.json`，仅参照） | `promotion_eligible=False` | — | 8 门过 5（`cagr_excess_qqq`/`qqq_capture_ratio`/`sharpe_excess_bil` 不过） |

**选择后窗口诊断**（2026-07-09 至 2026-09-03，41 个交易日，非门槛）：C12 CAGR -8.23%，同期 QQQ +5.51%，Sharpe -0.39。样本极短，仅供参考，不构成额外裁定依据。

## 全部 24 候选（按超额 CAGR 排序，`cap_new`/`cap_legacy` 为捕获比新旧定义并列）

| 候选 | market | trend_sma | target_vol | max_dd_stop | cagr | 超额CAGR(vm) | cap_new | cap_legacy | sharpe_ex_bil | mar | 通过？ |
|---|---|---:|---|---|---:|---:|---:|---:|---:|---:|---|
| C12 | QQQ | 200 | none | -15% | 11.86% | +0.99pp | 1.116 | 0.201 | 0.589 | 0.762 | 否 |
| C10 | QQQ | 200 | 15% | -15% | 10.61% | +0.80pp | 1.118 | 0.283 | 0.587 | 0.890 | 否 |
| C09 | QQQ | 200 | 15% | none | 10.41% | +0.54pp | 1.111 | 0.276 | 0.567 | 0.873 | 否 |
| C17 | SPY | 100 | none | none | 10.02% | +0.40pp | 1.127 | 0.327 | 0.581 | 0.595 | 否 |
| C11 | QQQ | 200 | none | none | 11.26% | +0.31pp | 1.102 | 0.191 | 0.547 | 0.697 | 否 |
| C23 | SPY | 200 | none | none | 9.45% | +0.05pp | 1.099 | 0.376 | 0.553 | 0.520 | 否 |
| …（其余 18 组超额 CAGR 全部为负，详见证据 JSON）| | | | | | | | | | | |
| C01 | QQQ | 100 | 10% | none | 6.45% | -1.84pp | 1.065 | 0.362 | 0.330 | 0.374 | 否 |
| C06 | QQQ | 100 | none | -15% | 8.24% | -2.72pp | 1.049 | 0.158 | 0.358 | 0.629 | 否 |
| C05 | QQQ | 100 | none | none | 7.72% | -3.32pp | 1.038 | 0.150 | 0.323 | 0.359 | 否 |

（省略号中间的 18 组：market/trend_sma/target_vol/max_dd 网格的其余组合，超额 CAGR 介于 -0.4pp 至 -3.3pp 之间，捕获比新定义均在 1.0-1.09 区间通过、legacy 定义均在 0.15-0.36 区间不通过，`mar` 是这些组合里唯一偶有不过的门；完整 24 行数字见证据 JSON 的 `candidates[].new_contract.metrics`。）

## 旧合同（参照，不裁定）

24/24 `promotion_eligible=False`；主要卡在 `cagr_excess_qqq`（绝对 CAGR 差 QQQ 十年 20.2% 太远）与 `qqq_capture_ratio`（同样的总复利定义缺陷，但旧合同键名 `qqq_capture_ratio` 本身不受本次修正影响——本次修正只新增了 `benchmark_returns` 给定时的 vm 路径，`benchmark_returns=None` 的旧路径逐字节不变，已有回归测试 `test_benchmark_returns_none_keeps_the_existing_qqq_path_byte_for_byte` 保证）。

## 数据来源与可复现性

`gate_contract_sha256`：新合同 `a8431ca4e6d8936eb16eb49a2f004962d94ba801919a4afb889a195f5493d157`，旧合同 `3b3ce418b64056005d0c6143af4155b8c2d0b85a66db9b83c1ebf99ab47a9c9b`（两者均 `gates_provenance: preregistered`）。重跑命令：
```
export PATH="$HOME/.local/bin:$PATH"; export UV_CACHE_DIR=/tmp/open-composer-uv-cache
uv run python scripts/evaluate_beta_exposure_family_sip.py
```
