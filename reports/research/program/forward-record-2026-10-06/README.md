# 前向记录拼接（T-20261004-70，A1）

生成：`scripts/forward_record_t70.py assemble`，数据最后一个交易日 2026-10-02。本记录只做记账：不下结论，不改设计，不改评判标准；所有数字由脚本写入 `summary.json`，本文件的表格由同一脚本从 `summary.json` 渲染。

## 方法

- 记录起点 2026-09-01。每个候选分三段：**设计时看过**（起点到冻结日）、**样本外影子**（冻结日次日到模拟盘首个成交日的前一天，用冻结规则重算）、**模拟盘**（模拟盘子策略的真实净值收益）。
- 冻结日 = 冻结规则文件首次提交时间之前最后一个已收盘的交易日（收盘按 20:00 UTC 计）。用的文件见下表。另报一版“回测所用数据边界”（回测面板的最后一个交易日）作对照，两者不同的候选在 `summary.json` 的 `alt_boundary_backtest_data` 里。
- 影子引擎：S1/S2/S3 用 `run_h20260927_01_sleeve_combination.sleeve_returns`（冻结的叠加层引擎，与 T-43 同一份），C2 用筛选通道 offset 0（`screen_lane.candidate_returns_for_offset`，与 `returns.sip-repaired-20261002.parquet` 在 2026-09-17 之前逐日一致，最大差 0.0）；成本每单位换手 10 bp，收盘信号、次日开盘成交；面板 `shadow_forward.load_forward_panel`（不设 HOLD_END 上限），数据为 10-02 之后修复过的 SIP 档案。
- v1.2 F1/F2：研究文件 `data/research/book_v12/A1_M0_U3000_F*.parquet`（按 T-43 的口径换成按实现日索引，除以 100 万）。T-43 组合：`run_program_dd30_allocation.path`，权重 S3 0.60 / C2 0.335 / F2 0.12 / F1 0.025 / 借款 0.08，偏移 0，每月第 1 个交易日再平衡，5 bp。
- 模拟盘：`open_composer.cockpit.data.paper.build_paper_report` 的子策略净值（20:00 UTC 标记），第一天相对子策略预算 15000 美元。
- 夏普 = 日超额收益（减 BIL）均值 / 标准差 × √252；不足 20 天只作描述。最大回撤在各段内从 1.0 起复利计算。SPY 为同日期收盘到收盘。
- **前向 z** = (前向日均收益 − 回测日均收益) / (回测日标准差 / √n前向)；回测基准用同一引擎在 2017-10-02..冻结日（全期）和 2024-01-08..冻结日（近期窗口，即冻结合同的 anchor 窗口起点）两版；另报“仅影子”版（同一批前向日只用影子引擎，去掉执行差异）。
- **跟踪差** = 模拟盘日收益 − 同日影子收益；逐日拆为 成交价（成交文件里 `slippage_vs_open_bps` 加权）、成交时点（成交时间 UTC）、影子成本（影子每单位换手扣 10 bp，模拟盘没有）、整股取整（观察日志的闲置现金比例 × 影子收益，估计值）、残差。
- **哈希链** `hash_chain.jsonl`：每行 日期、候选、文件路径、文件 SHA-256、前一行 `chain_hash`、本行 `chain_hash = sha256('|'.join([prev_hash, date, candidate, path, sha256]))`，第一行 prev 为 64 个 0。只登记现有文件；复核命令见文末。

## 冻结日与依据

| 候选 | 冻结规则文件（首次提交） | 首次提交时间 UTC | 最后一个已见收盘（提交口径） | 回测数据边界 | 模拟盘首日 |
|---|---|---|---|---|---|
| S1 | `strategy_specs/drafts/us_etf_sector_rotation_252_top2_weekly.yaml`（84db4ef） | 2026-09-18 13:49:34 | 2026-09-17 | 2026-09-17 | 2026-09-21 |
| S2 | `strategy_specs/drafts/us_etf_growth_rotation_blend_top2_monthly.yaml`（84db4ef） | 2026-09-18 13:49:34 | 2026-09-17 | 2026-09-17 | 2026-09-21 |
| S3 | `strategy_specs/drafts/us_etf_levered_rotation_63_top2_monthly.yaml`（84db4ef） | 2026-09-18 13:49:34 | 2026-09-17 | 2026-09-17 | 2026-09-21 |
| C2 | `scripts/screen_batches/h20260928_20_recent_opt.py`（9b15143） | 2026-09-28 06:43:15 | 2026-09-25 | 2026-09-17 | 2026-10-01 |
| V12F1 | `reports/research/iterations/t20261002_book_v12/hypotheses.md`（9dcb7d5） | 2026-10-02 05:35:51 | 2026-10-01 | 2026-09-15 | 无 |
| V12F2 | `reports/research/iterations/t20261002_book_v12/hypotheses.md`（9dcb7d5） | 2026-10-02 05:35:51 | 2026-10-01 | 2026-09-15 | 无 |
| T43 | `reports/research/program/allocation-dd30-2026-10-02/prereg.md`（469ae13） | 2026-10-02 13:14:40 | 2026-10-01 | 2026-09-15 | 无 |

S1–S3 的提交口径与回测留出边界（`HOLD_END` 2026-09-17）一致。C2 另有规格文件 `strategy_specs/drafts/us_etf_eom_sector_blend_monthly.yaml`（首次提交 2026-09-30 03:48 UTC，最后一个已见收盘 09-29）；主口径取规则模块 `h20260928_20_recent_opt.py`（kept.jsonl 记录 09-28 06:43 UTC），保守版见 `summary.json`。

## 每候选三段与合计（提交口径）

| 候选 | 段 | 区间 | 天数 | 累计收益 | 年化波动 | 夏普 | 最大回撤 | SPY 同期累计 |
|---|---|---|---|---|---|---|---|---|
| S1 | 设计时看过 | 2026-09-01..2026-09-17 | 12 | 0.91% | 14.52% | 1.14（<20天，仅描述） | -1.98% | -0.58% |
| S1 | 样本外影子 | 2026-09-18..2026-09-18 | 1 | 0.28% | n/a | n/a | 0.00% | 0.13% |
| S1 | 模拟盘 | 2026-09-21..2026-10-02 | 10 | 1.55% | 8.87% | 4.01（<20天，仅描述） | -0.87% | 1.04% |
| S1 | 合计 | 2026-09-01..2026-10-02 | 23 | 2.76% | 11.76% | 2.29 | -1.98% | 0.59% |
| S1 | 前向（影子+模拟盘拼接） | 2026-09-18..2026-10-02 | 11 | 1.83% | 8.44% | 4.54（<20天，仅描述） | -0.87% | 1.17% |
| S1 | 前向（同日仅影子引擎） | 2026-09-18..2026-10-02 | 11 | 2.18% | 8.56% | 5.40（<20天，仅描述） | -0.88% | 1.17% |
| S2 | 设计时看过 | 2026-09-01..2026-09-17 | 12 | 0.52% | 13.63% | 0.62（<20天，仅描述） | -2.18% | -0.58% |
| S2 | 样本外影子 | 2026-09-18..2026-09-18 | 1 | 0.71% | n/a | n/a | 0.00% | 0.13% |
| S2 | 模拟盘 | 2026-09-21..2026-10-02 | 10 | 3.50% | 10.63% | 7.92（<20天，仅描述） | -1.05% | 1.04% |
| S2 | 合计 | 2026-09-01..2026-10-02 | 23 | 4.77% | 12.16% | 3.99 | -2.18% | 0.59% |
| S2 | 前向（影子+模拟盘拼接） | 2026-09-18..2026-10-02 | 11 | 4.23% | 10.23% | 9.03（<20天，仅描述） | -1.05% | 1.17% |
| S2 | 前向（同日仅影子引擎） | 2026-09-18..2026-10-02 | 11 | 5.00% | 10.83% | 10.10（<20天，仅描述） | -0.66% | 1.17% |
| S3 | 设计时看过 | 2026-09-01..2026-09-17 | 12 | -1.48% | 5.60% | -6.20（<20天，仅描述） | -1.63% | -0.58% |
| S3 | 样本外影子 | 2026-09-18..2026-09-18 | 1 | -0.15% | n/a | n/a | -0.15% | 0.13% |
| S3 | 模拟盘 | 2026-09-21..2026-10-02 | 10 | 1.70% | 26.03% | 1.61（<20天，仅描述） | -4.30% | 1.04% |
| S3 | 合计 | 2026-09-01..2026-10-02 | 23 | 0.05% | 17.29% | -0.10 | -4.30% | 0.59% |
| S3 | 前向（影子+模拟盘拼接） | 2026-09-18..2026-10-02 | 11 | 1.55% | 24.74% | 1.38（<20天，仅描述） | -4.30% | 1.17% |
| S3 | 前向（同日仅影子引擎） | 2026-09-18..2026-10-02 | 11 | 2.78% | 12.43% | 4.81（<20天，仅描述） | -0.33% | 1.17% |
| C2 | 设计时看过 | 2026-09-01..2026-09-25 | 18 | 0.48% | 11.82% | 0.31（<20天，仅描述） | -2.52% | 0.81% |
| C2 | 样本外影子 | 2026-09-28..2026-09-30 | 3 | -0.67% | 7.77% | -7.52（<20天，仅描述） | -0.76% | -1.13% |
| C2 | 模拟盘 | 2026-10-01..2026-10-02 | 2 | 0.39% | 6.86% | 6.06（<20天，仅描述） | -0.11% | 0.92% |
| C2 | 合计 | 2026-09-01..2026-10-02 | 23 | 0.19% | 10.88% | -0.10 | -2.52% | 0.59% |
| C2 | 前向（影子+模拟盘拼接） | 2026-09-28..2026-10-02 | 5 | -0.28% | 7.43% | -2.44（<20天，仅描述） | -0.78% | -0.22% |
| C2 | 前向（同日仅影子引擎） | 2026-09-28..2026-10-02 | 5 | -0.20% | 7.56% | -1.81（<20天，仅描述） | -0.76% | -0.22% |
| V12F1 | 设计时看过 | 2026-09-01..2026-09-15 | 10 | 0.27% | 5.18% | 0.66（<20天，仅描述） | -1.04% | -1.26% |
| V12F1 | 样本外影子 | - | 0 | n/a | n/a | n/a | n/a | n/a |
| V12F1 | 模拟盘 | - | 0 | n/a | n/a | n/a | n/a | n/a |
| V12F1 | 合计 | 2026-09-01..2026-09-15 | 10 | 0.27% | 5.18% | 0.66（<20天，仅描述） | -1.04% | -1.26% |
| V12F1 | 前向（影子+模拟盘拼接） | - | 0 | n/a | n/a | n/a | n/a | n/a |
| V12F1 | 前向（同日仅影子引擎） | - | 0 | n/a | n/a | n/a | n/a | n/a |
| V12F2 | 设计时看过 | 2026-09-01..2026-09-15 | 10 | -1.42% | 11.33% | -3.48（<20天，仅描述） | -2.46% | -1.26% |
| V12F2 | 样本外影子 | - | 0 | n/a | n/a | n/a | n/a | n/a |
| V12F2 | 模拟盘 | - | 0 | n/a | n/a | n/a | n/a | n/a |
| V12F2 | 合计 | 2026-09-01..2026-09-15 | 10 | -1.42% | 11.33% | -3.48（<20天，仅描述） | -2.46% | -1.26% |
| V12F2 | 前向（影子+模拟盘拼接） | - | 0 | n/a | n/a | n/a | n/a | n/a |
| V12F2 | 前向（同日仅影子引擎） | - | 0 | n/a | n/a | n/a | n/a | n/a |
| T43 | 设计时看过 | 2026-09-01..2026-09-15 | 10 | -1.55% | 6.64% | -6.52（<20天，仅描述） | -1.55% | -1.26% |
| T43 | 样本外影子 | - | 0 | n/a | n/a | n/a | n/a | n/a |
| T43 | 模拟盘 | - | 0 | n/a | n/a | n/a | n/a | n/a |
| T43 | 合计 | 2026-09-01..2026-09-15 | 10 | -1.55% | 6.64% | -6.52（<20天，仅描述） | -1.55% | -1.26% |
| T43 | 前向（影子+模拟盘拼接） | - | 0 | n/a | n/a | n/a | n/a | n/a |
| T43 | 前向（同日仅影子引擎） | - | 0 | n/a | n/a | n/a | n/a | n/a |

## 回测数据边界口径（两者不同的候选）

| 候选 | 段 | 区间 | 天数 | 累计收益 | 年化波动 | 夏普 | 最大回撤 | SPY 同期累计 |
|---|---|---|---|---|---|---|---|---|
| C2 | 设计时看过 | 2026-09-01..2026-09-17 | 12 | -0.16% | 11.80% | -0.53（<20天，仅描述） | -2.52% | -0.58% |
| C2 | 样本外影子 | 2026-09-18..2026-09-30 | 9 | -0.04% | 11.21% | -0.35（<20天，仅描述） | -1.51% | 0.25% |
| C2 | 模拟盘 | 2026-10-01..2026-10-02 | 2 | 0.39% | 6.86% | 6.06（<20天，仅描述） | -0.11% | 0.92% |
| C2 | 合计 | 2026-09-01..2026-10-02 | 23 | 0.19% | 10.88% | -0.10 | -2.52% | 0.59% |
| C2 | 前向（影子+模拟盘拼接） | 2026-09-18..2026-10-02 | 11 | 0.35% | 10.34% | 0.44（<20天，仅描述） | -1.54% | 1.17% |
| C2 | 前向（同日仅影子引擎） | 2026-09-18..2026-10-02 | 11 | 0.44% | 10.36% | 0.64（<20天，仅描述） | -1.51% | 1.17% |
| V12F1 | 设计时看过 | 2026-09-01..2026-09-15 | 10 | 0.27% | 5.18% | 0.66（<20天，仅描述） | -1.04% | -1.26% |
| V12F1 | 样本外影子 | - | 0 | n/a | n/a | n/a | n/a | n/a |
| V12F1 | 模拟盘 | - | 0 | n/a | n/a | n/a | n/a | n/a |
| V12F1 | 合计 | 2026-09-01..2026-09-15 | 10 | 0.27% | 5.18% | 0.66（<20天，仅描述） | -1.04% | -1.26% |
| V12F1 | 前向（影子+模拟盘拼接） | - | 0 | n/a | n/a | n/a | n/a | n/a |
| V12F1 | 前向（同日仅影子引擎） | - | 0 | n/a | n/a | n/a | n/a | n/a |
| V12F2 | 设计时看过 | 2026-09-01..2026-09-15 | 10 | -1.42% | 11.33% | -3.48（<20天，仅描述） | -2.46% | -1.26% |
| V12F2 | 样本外影子 | - | 0 | n/a | n/a | n/a | n/a | n/a |
| V12F2 | 模拟盘 | - | 0 | n/a | n/a | n/a | n/a | n/a |
| V12F2 | 合计 | 2026-09-01..2026-09-15 | 10 | -1.42% | 11.33% | -3.48（<20天，仅描述） | -2.46% | -1.26% |
| V12F2 | 前向（影子+模拟盘拼接） | - | 0 | n/a | n/a | n/a | n/a | n/a |
| V12F2 | 前向（同日仅影子引擎） | - | 0 | n/a | n/a | n/a | n/a | n/a |
| T43 | 设计时看过 | 2026-09-01..2026-09-15 | 10 | -1.55% | 6.64% | -6.52（<20天，仅描述） | -1.55% | -1.26% |
| T43 | 样本外影子 | - | 0 | n/a | n/a | n/a | n/a | n/a |
| T43 | 模拟盘 | - | 0 | n/a | n/a | n/a | n/a | n/a |
| T43 | 合计 | 2026-09-01..2026-09-15 | 10 | -1.55% | 6.64% | -6.52（<20天，仅描述） | -1.55% | -1.26% |
| T43 | 前向（影子+模拟盘拼接） | - | 0 | n/a | n/a | n/a | n/a | n/a |
| T43 | 前向（同日仅影子引擎） | - | 0 | n/a | n/a | n/a | n/a | n/a |

## 前向 z（提交口径）

| 候选 | n 前向 | z（回测全期） | z（回测近期窗口） | z（仅影子，全期） | z（仅影子，近期） |
|---|---|---|---|---|---|
| S1 | 11 | 0.28 | 0.21 | 0.36 | 0.31 |
| S2 | 11 | 0.97 | 0.74 | 1.18 | 0.95 |
| S3 | 11 | -0.03 | -0.23 | 0.09 | -0.11 |
| C2 | 5 | -0.27 | -0.50 | -0.23 | -0.43 |
| V12F1 | 0 | n/a | n/a | n/a | n/a |
| V12F2 | 0 | n/a | n/a | n/a | n/a |
| T43 | 0 | n/a | n/a | n/a | n/a |

## 前向 z（回测数据边界口径）

| 候选 | n 前向 | z（回测全期） | z（回测近期窗口） | z（仅影子，全期） | z（仅影子，近期） |
|---|---|---|---|---|---|
| C2 | 11 | -0.06 | -0.24 | -0.03 | -0.20 |
| V12F1 | 0 | n/a | n/a | n/a | n/a |
| V12F2 | 0 | n/a | n/a | n/a | n/a |
| T43 | 0 | n/a | n/a | n/a | n/a |

z 的前向样本很短（见 n 前向），日收益也不独立，这一列只用来记录，不构成通过或否定的依据。

## 跟踪差（模拟盘 − 影子）

| 候选 | 子集 | 天数 | 日均差(bp) | 日标准差(bp) | 最差 3 天 |
|---|---|---|---|---|---|
| S1 | 全部模拟盘日 | 10 | -3.5 | 9.3 | 2026-09-21 -29.4; 2026-10-01 -3.6; 2026-09-23 -2.5 |
| S2 | 全部模拟盘日 | 10 | -7.4 | 23.8 | 2026-09-21 -58.6; 2026-09-24 -38.1; 2026-09-29 -2.7 |
| S2 | 09-23 前（模拟盘尚无波动率叠加层） | 3 | -10.9 | 43.8 | 2026-09-21 -58.6; 2026-09-23 -1.4; 2026-09-22 +27.4 |
| S2 | 09-24 起 | 7 | -5.9 | 14.3 | 2026-09-24 -38.1; 2026-09-29 -2.7; 2026-09-25 -2.2 |
| S3 | 全部模拟盘日 | 10 | -11.2 | 130.7 | 2026-09-23 -196.7; 2026-09-28 -170.2; 2026-09-30 -56.8 |
| S3 | T-55 数据翻转日 | 8 | -21.2 | 145.1 | 2026-09-23 -196.7; 2026-09-28 -170.2; 2026-09-30 -56.8 |
| S3 | 其余日 | 2 | +28.9 | 47.9 | 2026-10-02 -4.9; 2026-10-01 +62.8 |
| S3 | 09-23 前（模拟盘尚无波动率叠加层） | 3 | +16.5 | 226.2 | 2026-09-23 -196.7; 2026-09-22 -7.6; 2026-09-21 +253.8 |
| S3 | 09-24 起 | 7 | -23.0 | 89.6 | 2026-09-28 -170.2; 2026-09-30 -56.8; 2026-09-24 -50.1 |
| C2 | 全部模拟盘日 | 2 | -4.4 | 1.8 | 2026-10-01 -5.7; 2026-10-02 -3.1 |

### S1 逐日（模拟盘 − 影子，bp）

| 日期 | 模拟盘 | 影子 | 差 | 成交价 | 影子成本 | 整股取整(估) | 残差 | 说明 |
|---|---|---|---|---|---|---|---|---|
| 2026-09-21 | -1.6 | +27.8 | -29.4 | -26.5 | +0.0 | -0.2 | -2.6 | fill price: 2 orders, 14,847 USD, adverse slippage vs official open -26.5 bp of NAV; timing: executed 13:31-13:34 UTC (day_market after the open) while the shadow earns the official open; whole-share rounding / idle cash 0.90% of equity: estimate -0.2 bp; residual -2.6 bp (holdings/data/mark differences) |
| 2026-09-22 | -15.7 | -17.8 | +2.1 | -0.0 | +0.0 | +0.2 | +1.9 | no orders that day (fill price / timing: none); whole-share rounding / idle cash 0.90% of equity: estimate +0.2 bp; residual +1.9 bp (holdings/data/mark differences) |
| 2026-09-23 | +21.5 | +24.0 | -2.5 | -0.0 | +0.0 | -0.2 | -2.3 | no orders that day (fill price / timing: none); whole-share rounding / idle cash 0.90% of equity: estimate -0.2 bp; residual -2.3 bp (holdings/data/mark differences) |
| 2026-09-24 | +1.4 | +3.3 | -1.9 | -0.0 | +0.0 | -0.0 | -1.8 | no orders that day (fill price / timing: none); whole-share rounding / idle cash 0.90% of equity: estimate -0.0 bp; residual -1.8 bp (holdings/data/mark differences) |
| 2026-09-25 | -2.7 | -4.6 | +1.9 | -0.0 | +0.0 | +0.0 | +1.9 | no orders that day (fill price / timing: none); whole-share rounding / idle cash 0.26% of equity: estimate +0.0 bp; residual +1.9 bp (holdings/data/mark differences) |
| 2026-09-28 | -40.6 | -39.0 | -1.6 | -0.0 | +0.0 | +0.1 | -1.7 | no orders that day (fill price / timing: none); whole-share rounding / idle cash 0.26% of equity: estimate +0.1 bp; residual -1.7 bp (holdings/data/mark differences) |
| 2026-09-29 | -44.3 | -45.1 | +0.8 | -0.0 | +0.0 | +0.1 | +0.7 | no orders that day (fill price / timing: none); whole-share rounding / idle cash 0.26% of equity: estimate +0.1 bp; residual +0.7 bp (holdings/data/mark differences) |
| 2026-09-30 | +29.6 | +29.0 | +0.7 | -0.0 | +0.0 | -0.1 | +0.8 | no orders that day (fill price / timing: none); whole-share rounding / idle cash 0.26% of equity: estimate -0.1 bp; residual +0.8 bp (holdings/data/mark differences) |
| 2026-10-01 | +147.1 | +150.7 | -3.6 | -0.0 | +0.0 | -0.4 | -3.2 | no orders that day (fill price / timing: none); whole-share rounding / idle cash 0.26% of equity: estimate -0.4 bp; residual -3.2 bp (holdings/data/mark differences) |
| 2026-10-02 | +60.7 | +61.7 | -1.0 | -0.0 | +0.0 | -0.2 | -0.9 | no orders that day (fill price / timing: none); whole-share rounding / idle cash 0.25% of equity: estimate -0.2 bp; residual -0.9 bp (holdings/data/mark differences) |

### S2 逐日（模拟盘 − 影子，bp）

| 日期 | 模拟盘 | 影子 | 差 | 成交价 | 影子成本 | 整股取整(估) | 残差 | 说明 |
|---|---|---|---|---|---|---|---|---|
| 2026-09-21 | +120.8 | +179.5 | -58.6 | -1.7 | +0.0 | -3.6 | -53.3 | fill price: 1 orders, 7,567 USD, adverse slippage vs official open -1.7 bp of NAV; timing: executed 13:30-13:30 UTC (day_market after the open) while the shadow earns the official open; whole-share rounding / idle cash 2.03% of equity: estimate -3.6 bp; residual -53.3 bp (holdings/data/mark differences); paper ran the pre-renewal rule without the volatility overlay until the 09-23 renewal (overlay trades filled 09-24, spec commit 97c992c 2026-09-23 07:35 UTC); the shadow engine applies the frozen overlay from the start |
| 2026-09-22 | +97.9 | +70.5 | +27.4 | -0.0 | +0.0 | -1.4 | +28.8 | no orders that day (fill price / timing: none); whole-share rounding / idle cash 2.03% of equity: estimate -1.4 bp; residual +28.8 bp (holdings/data/mark differences); paper ran the pre-renewal rule without the volatility overlay until the 09-23 renewal (overlay trades filled 09-24, spec commit 97c992c 2026-09-23 07:35 UTC); the shadow engine applies the frozen overlay from the start |
| 2026-09-23 | -51.3 | -49.9 | -1.4 | -0.0 | +0.0 | +0.4 | -1.8 | no orders that day (fill price / timing: none); whole-share rounding / idle cash 0.71% of equity: estimate +0.4 bp; residual -1.8 bp (holdings/data/mark differences); paper ran the pre-renewal rule without the volatility overlay until the 09-23 renewal (overlay trades filled 09-24, spec commit 97c992c 2026-09-23 07:35 UTC); the shadow engine applies the frozen overlay from the start |
| 2026-09-24 | -51.1 | -13.0 | -38.1 | -19.8 | +0.0 | +0.1 | -18.3 | fill price: 3 orders, 15,215 USD, adverse slippage vs official open -19.8 bp of NAV; timing: executed 13:30-13:33 UTC (day_market after the open) while the shadow earns the official open; whole-share rounding / idle cash 0.71% of equity: estimate +0.1 bp; residual -18.3 bp (holdings/data/mark differences) |
| 2026-09-25 | +51.5 | +53.7 | -2.2 | -0.0 | +0.0 | -0.4 | -1.8 | no orders that day (fill price / timing: none); whole-share rounding / idle cash 0.71% of equity: estimate -0.4 bp; residual -1.8 bp (holdings/data/mark differences) |
| 2026-09-28 | -54.4 | -56.7 | +2.3 | -0.0 | +0.0 | +0.4 | +1.9 | no orders that day (fill price / timing: none); whole-share rounding / idle cash 0.71% of equity: estimate +0.4 bp; residual +1.9 bp (holdings/data/mark differences) |
| 2026-09-29 | +29.8 | +32.5 | -2.7 | -0.0 | +0.0 | -0.2 | -2.4 | no orders that day (fill price / timing: none); whole-share rounding / idle cash 0.71% of equity: estimate -0.2 bp; residual -2.4 bp (holdings/data/mark differences) |
| 2026-09-30 | +27.1 | +27.9 | -0.8 | -0.0 | +0.0 | -0.1 | -0.7 | no orders that day (fill price / timing: none); whole-share rounding / idle cash 0.46% of equity: estimate -0.1 bp; residual -0.7 bp (holdings/data/mark differences) |
| 2026-10-01 | +79.4 | +78.4 | +1.0 | -0.6 | +2.6 | -0.3 | -0.6 | fill price: 3 orders, 4,069 USD, adverse slippage vs official open -0.6 bp of NAV; timing: executed 13:30-13:33 UTC (day_market after the open) while the shadow earns the official open; shadow turnover 0.26 charges 2.6 bp that paper does not pay explicitly; whole-share rounding / idle cash 0.42% of equity: estimate -0.3 bp; residual -0.6 bp (holdings/data/mark differences) |
| 2026-10-02 | +96.9 | +97.8 | -0.9 | -0.0 | +0.0 | -0.4 | -0.5 | no orders that day (fill price / timing: none); whole-share rounding / idle cash 0.42% of equity: estimate -0.4 bp; residual -0.5 bp (holdings/data/mark differences) |

### S3 逐日（模拟盘 − 影子，bp）

| 日期 | 模拟盘 | 影子 | 差 | 成交价 | 影子成本 | 整股取整(估) | 残差 | 说明 |
|---|---|---|---|---|---|---|---|---|
| 2026-09-21 | +260.0 | +6.2 | +253.8 | -15.2 | +0.0 | -0.1 | +269.1 | fill price: 1 orders, 14,836 USD, adverse slippage vs official open -15.2 bp of NAV; timing: executed 13:32-13:32 UTC (day_market after the open) while the shadow earns the official open; whole-share rounding / idle cash 0.82% of equity: estimate -0.1 bp; residual +269.1 bp (holdings/data/mark differences); T-55 data flip: shadow on the repaired SIP archive holds SHY, the paper sleeve holds UPRO (chosen on the pre-repair archive); not an execution error; paper ran the pre-renewal rule without the volatility overlay until the 09-23 renewal (overlay trades filled 09-24, spec commit 97c992c 2026-09-23 07:35 UTC); the shadow engine applies the frozen overlay from the start |
| 2026-09-22 | -3.9 | +3.7 | -7.6 | -0.0 | +0.0 | -0.0 | -7.5 | no orders that day (fill price / timing: none); whole-share rounding / idle cash 0.82% of equity: estimate -0.0 bp; residual -7.5 bp (holdings/data/mark differences); T-55 data flip: shadow on the repaired SIP archive holds SHY, the paper sleeve holds UPRO (chosen on the pre-repair archive); not an execution error; paper ran the pre-renewal rule without the volatility overlay until the 09-23 renewal (overlay trades filled 09-24, spec commit 97c992c 2026-09-23 07:35 UTC); the shadow engine applies the frozen overlay from the start |
| 2026-09-23 | -221.4 | -24.7 | -196.7 | -0.0 | +0.0 | +0.0 | -196.7 | no orders that day (fill price / timing: none); whole-share rounding / idle cash 0.17% of equity: estimate +0.0 bp; residual -196.7 bp (holdings/data/mark differences); T-55 data flip: shadow on the repaired SIP archive holds SHY, the paper sleeve holds UPRO (chosen on the pre-repair archive); not an execution error; paper ran the pre-renewal rule without the volatility overlay until the 09-23 renewal (overlay trades filled 09-24, spec commit 97c992c 2026-09-23 07:35 UTC); the shadow engine applies the frozen overlay from the start |
| 2026-09-24 | -53.8 | -3.7 | -50.1 | -6.0 | +0.0 | +0.0 | -44.1 | fill price: 2 orders, 6,048 USD, adverse slippage vs official open -6.0 bp of NAV; timing: executed 13:33-13:33 UTC (day_market after the open) while the shadow earns the official open; whole-share rounding / idle cash 0.17% of equity: estimate +0.0 bp; residual -44.1 bp (holdings/data/mark differences); T-55 data flip: shadow on the repaired SIP archive holds SHY, the paper sleeve holds UPRO (chosen on the pre-repair archive); not an execution error |
| 2026-09-25 | +119.7 | +14.8 | +104.9 | -0.0 | +0.0 | -0.0 | +104.9 | no orders that day (fill price / timing: none); whole-share rounding / idle cash 0.17% of equity: estimate -0.0 bp; residual +104.9 bp (holdings/data/mark differences); T-55 data flip: shadow on the repaired SIP archive holds SHY, the paper sleeve holds UPRO (chosen on the pre-repair archive); not an execution error |
| 2026-09-28 | -182.5 | -12.4 | -170.2 | -0.0 | +0.0 | +0.0 | -170.2 | no orders that day (fill price / timing: none); whole-share rounding / idle cash 0.17% of equity: estimate +0.0 bp; residual -170.2 bp (holdings/data/mark differences); T-55 data flip: shadow on the repaired SIP archive holds SHY, the paper sleeve holds UPRO (chosen on the pre-repair archive); not an execution error |
| 2026-09-29 | -40.7 | +6.2 | -46.9 | -0.0 | +0.0 | -0.0 | -46.9 | no orders that day (fill price / timing: none); whole-share rounding / idle cash 0.17% of equity: estimate -0.0 bp; residual -46.9 bp (holdings/data/mark differences); T-55 data flip: shadow on the repaired SIP archive holds SHY, the paper sleeve holds UPRO (chosen on the pre-repair archive); not an execution error |
| 2026-09-30 | -51.8 | +5.0 | -56.8 | -0.0 | +0.0 | -0.1 | -56.7 | no orders that day (fill price / timing: none); whole-share rounding / idle cash 1.17% of equity: estimate -0.1 bp; residual -56.7 bp (holdings/data/mark differences); T-55 data flip: shadow on the repaired SIP archive holds SHY, the paper sleeve holds UPRO (chosen on the pre-repair archive); not an execution error |
| 2026-10-01 | +104.4 | +41.6 | +62.8 | -8.4 | +20.0 | -0.5 | +51.7 | fill price: 3 orders, 14,714 USD, adverse slippage vs official open -8.4 bp of NAV; timing: executed 13:30-13:32 UTC (day_market after the open) while the shadow earns the official open; shadow turnover 2.00 charges 20.0 bp that paper does not pay explicitly; whole-share rounding / idle cash 1.11% of equity: estimate -0.5 bp; residual +51.7 bp (holdings/data/mark differences) |
| 2026-10-02 | +250.6 | +255.5 | -4.9 | -0.0 | +0.0 | -2.8 | -2.1 | no orders that day (fill price / timing: none); whole-share rounding / idle cash 1.11% of equity: estimate -2.8 bp; residual -2.1 bp (holdings/data/mark differences) |

### C2 逐日（模拟盘 − 影子，bp）

| 日期 | 模拟盘 | 影子 | 差 | 成交价 | 影子成本 | 整股取整(估) | 残差 | 说明 |
|---|---|---|---|---|---|---|---|---|
| 2026-10-01 | -11.0 | -5.3 | -5.7 | +9.4 | +10.0 | +0.2 | -25.3 | fill price: 3 orders, 14,286 USD, adverse slippage vs official open +9.4 bp of NAV; timing: executed 13:30-13:33 UTC (day_market after the open) while the shadow earns the official open; shadow turnover 1.00 charges 10.0 bp that paper does not pay explicitly; whole-share rounding / idle cash 4.54% of equity: estimate +0.2 bp; residual -25.3 bp (holdings/data/mark differences) |
| 2026-10-02 | +50.1 | +53.2 | -3.1 | -0.0 | +0.0 | -2.4 | -0.7 | no orders that day (fill price / timing: none); whole-share rounding / idle cash 4.54% of equity: estimate -2.4 bp; residual -0.7 bp (holdings/data/mark differences) |

## 一致性核对

```json
{
 "T43_path_vs_stored_program_returns": {
  "overlap_days": 2250,
  "last_overlap_date": "2026-09-15",
  "max_abs_diff": 0.003366501620563067,
  "max_abs_diff_since_2026_01_01": 0.0004993097034602378
 },
 "T43_path_prerepair_C2_vs_stored_program_returns_max_abs_diff": 0.0,
 "T43_note": "stored T-43 program_returns used the pre-repair C2 file (T-55: repaired C2 differs by up to 1.005% on 2019-01-02); this record uses the repaired C2 series.",
 "F_book_last_stored_date": "2026-09-15",
 "F_book_last_date_used": "2026-09-15"
}
```

## 哈希链

90 行，写入时校验通过=True，链头 `f9cfe4698b7c4ab4c1feab9f2c70d078c1531f9b838b472decb3e73e6e811f3e`。

## 发现的问题

1. **样本外影子段很短，z 只能描述。** S1–S3 的冻结日是 09-17，模拟盘 09-21 才有成交，所以真正"冻结后、模拟盘前"的影子只有 09-18 一天；C2 是 09-28..09-30 三天。绝大部分前向天数来自模拟盘段。9 月 1–17 日在 S1–S3 的设计窗口内（叠加层参数用到 09-17 的数据冻结），不能当样本外。
2. **模拟盘 S2、S3 在 09-24 才套上波动率叠加层。** 09-21 首批成交用的是叠加层之前的规则（S3 买入 UPRO 99 股，满仓；S2 买入 SMH 13 股），09-23 的更新（规格提交 97c992c，2026-09-23 07:35 UTC）后 09-24 成交了叠加层的调仓（S3：卖 UPRO 20 股买 SHY 38 股；S2：卖 SMH 7、买 XLK 20、买 SHY 89）。影子引擎从一开始就用冻结的叠加层，所以 S2/S3 在 09-21..09-23 的跟踪差反映的是规则不同，不是执行误差。表中单列了"09-23 前"与"09-24 起"两个子集。
3. **S3 九月的跟踪差主要是 T-55 的数据翻转，不是执行偏差。** 影子引擎在修复后的 SIP 档案上，08-31 信号选 SHY（UPRO 对 SHY 的差 −23.7 bp），模拟盘 09-18 是在修复前的档案上决定的，持有 UPRO（见 `reports/research/program/paper-consistency-2026-10-04/report.md` 第 1 节）。因此 S3 影子 9 月几乎平（SHY），模拟盘随 UPRO 波动；10-01 月末调仓后两者持仓一致（TECL、UPRO 各 0.5），10-02 差 −4.9 bp。"T-55 数据翻转日"子集的统计单独列出。
4. **ETF 子策略的目标权重文件每天被覆盖。** `reports/execution/<策略>-target-weights.json` 只保留最新一份，没有逐日归档，所以哈希链对这类文件只能证明"现在的状态"；逐日可证的是 `reports/paper/daily_cycle/*-observation-*.json`（含目标权重摘要）和 `reports/paper/rehearsal/*-<日期>-<时间>.json`（含订单和账本持仓），链里登记了这两类和 v1.2 的 `targets/`、`plans/` 日文件。若要逐日可证的目标权重，需要模拟盘管线每天另存一份（本任务不改管线，只提出）。
5. **T-43 已存的 `program_returns.parquet` 用的是修复前的 C2 文件**（`returns.parquet`）。本记录的 T-43 用修复后的 C2；两者在 2026 年以来最大日差 5.0 bp，全期最大 33.7 bp（2019-01-02，C2 当日差 1.005% × 0.335）。用修复前 C2 重建时与已存文件逐日一致（最大差 0.0），说明路径引擎是同一个。
6. 模拟盘第一天的收益是第一个净值相对子策略预算（15000 美元）计算的，因此含首批成交价与开盘价的差：S1 首日成交价吃掉约 26.5 bp（XLE 逆向 65.5 bp，占一半仓位）。
7. 夏普在不足 20 个交易日时只作描述；一天的段没有波动率和夏普。
8. **S2/S3 叠加层规则的预注册晚于规格文件。** 影子引擎用的叠加层规则（`reports/research/iterations/h20260922_05_salvage/candidate-manifest.json`，提交 ba59708，2026-09-22 11:36 UTC）比规格文件首次提交（09-18）晚；回测留出边界仍是 09-17，按简报取 09-17。若改取叠加层预注册口径，09-18 也要算"已见"，S2/S3 的样本外影子段就变成零天；数字不变，只有分段标签不同。

## 未完成项

- **按模拟盘实际规则重放的影子**：S2/S3 在 09-21..09-23 的"无叠加层"规则、S3 在修复前档案上的 08-31 信号，都没有对应的影子序列（需要在修复前档案 `data/live/backup-sip-daily-preswap-20261002` 上重算，且该档案只到 09-17）。目前只做了标注，没有把这部分跟踪差拆开。
- **v1.2 F1/F2 与 T-43 没有模拟盘段**（v1.2 10-07 才开始；T-43 是研究权重，没有对应的模拟盘组合净值）。
- 配置第二版定稿后的组合不在本任务范围内，未做。
- 衰减规则的所有阈值和连续天数 **待主审校准**。
- 队列文件未改（按简报由主代理处理）。
- **v1.2 F1/F2 与 T-43 在 2026-09-15 之后没有数字**：研究文件到 09-15 为止；用实时数据根重跑账户引擎（`forward_record_t70.py book`，混合根：实时根加上缺失的 2025 年前主题和信号文件，输出写 /tmp，不覆盖 data/research）在本任务时限内没有跑完（约 200 个决策日 / 5 分钟，已分离后台运行）。跑完后执行 `forward_record_t70.py assemble /tmp/t70_notes.md` 即可补上这三项的影子段和 z（脚本已支持，会同时报告重跑与已存文件在重叠段的最大差）。

## 衰减规则草案（供 A5 提议使用；所有阈值和天数均为 **待主审校准**，本任务没有拍数）

输入：每个候选的前向日净收益（影子+模拟盘拼接，见上）、前向 z（相对回测近期窗口）、前向最大回撤相对该候选冻结时回测回撤分布的分位、
以及 `config/evaluation-standard-v2.json` 的 `forward_monitoring` 里已有的硬停止（回撤 95% 分位减半、99% 分位停用、
21 日 beta 绝对值上限、成本超支比、后验 P(SR>0) 低于 0.5 停用）。下列四档与这些已有条目对齐，不改动它们。

| 档 | 进入条件（任一） | 动作 | 回到上一档的条件 |
|---|---|---|---|
| 健康 | z ≥ Z_OK 且回撤分位 < Q_WARN | 按计划规模运行 | - |
| 警告 | z < Z_WARN 连续 N_WARN 个交易日；或回撤分位 ≥ Q_WARN | 不加仓；每日复核，日报标红 | z ≥ Z_OK 且回撤分位 < Q_WARN 连续 M_UP 个交易日 |
| 衰减 | z < Z_DECAY 连续 N_DECAY 个交易日；或回撤分位 ≥ 0.95（已有 halve_dd_percentile）；或 21 日 beta 越界 / 成本超支触发既有规则 | 规模减半，提请主审复核 | z ≥ Z_WARN 且回撤分位 < Q_WARN 连续 M_UP 个交易日 |
| 停用 | z < Z_STOP 连续 N_STOP 个交易日；或回撤分位 ≥ 0.99（已有 stop_dd_percentile）；或后验 P(SR>0) < 0.5（已有）| 停止新开仓并平仓到现金，写失效原因 | 只能由主审重新批准，不自动回升 |

约定：
- 往下转移需要"连续 N 个交易日"（N_WARN < N_DECAY < N_STOP，防止一天噪声触发）；往上回升需要更长的 M_UP（滞回），M_UP > N_DECAY。N_*、M_UP、Z_*、Q_WARN 全部待主审校准。
- 前向样本少于 n_min 个交易日时（待校准，与评判标准的"短窗口不单独一票否决"一致）z 不触发降档，只触发回撤分位和已有硬停止。
- z 的前提是日收益近似独立同分布；日收益有自相关和厚尾，校准时应改用块自助法的 z 或按有效样本数缩放，并用本记录的跟踪差检验"模拟盘 vs 影子"的偏差是否单独构成降档理由。
- 模拟盘与影子的跟踪差持续偏离（日均差或其 z 超限，阈值待校准）时，先按"执行偏差"处理（检查成交价、成交时点、整股取整、现金、数据源），不直接按策略衰减处理。

## 复现与复核

```
scripts/run_capped.sh --mem 1.0G -- uv run python scripts/forward_record_t70.py shadow
scripts/run_capped.sh --mem 1.0G -- uv run python scripts/forward_record_t70.py book     # 可选，v1.2 影子重跑
uv run python scripts/forward_record_t70.py assemble /tmp/t70_notes.md
uv run python scripts/forward_record_t70.py verify   # 重算 hash_chain.jsonl
```
