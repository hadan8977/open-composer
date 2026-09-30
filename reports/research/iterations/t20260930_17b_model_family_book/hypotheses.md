# Hypotheses: t20260930_17b_model_family_book

## Hypothesis

Null: none of the six books reaches K1 (offset-median Sharpe at 10 bp >= 0.65 stress and >= 1.19 anchor, CAGR > 0 at 20 bp in both) or K2 (S3 combination edge >= +0.05 in both windows).

## Failure mode

Stage-1 RankIC sits in the illiquid terciles (T3 0.087-0.093, T1 liquid <= 0.012 with t < 1); fixed costs understate small-cap spreads, and the 2024-26 anchor window was already weak for B0 (V1 flat10 0.33).

## Measurement

Offset-median Sharpe over 21 monthly offsets per window at flat10/flat20; K2 via screen_lane.diversifier_edge_for_offset; 20 random-rank placebo books; DSR with 30 trials (report only).

## Stop/Pivot criterion

refuted: pure price-volume ranking gets no more cells; pass_pending_spreads: measured NBBO spread check on the held names before any paper proposal.

## 预注册全文（2026-09-30 19:07 主审轮写，早于任何阶段 2 数字）

本档案是 T-20260930-17 的阶段 2。判定规则在 `reports/research/iterations/t20260930_17_model_family_sweep/hypotheses.md` 的"阶段 2"一节里已经写死（13:48 提交），这里只把它落成可执行的口径，不改任何门槛。单独建档是因为轻量档案最多一条路径、24 个候选，阶段 1 已用满。

### 阶段 1 主审结论（对照 `results_stage1.json` 核过）

- `b0_parity` true（LGBM_W3_H21 RankIC 0.020001），h21 目标核对最大差 0.0。
- 四组里单一模型族对同组 LightGBM 的增量都不到 +0.010：XGB、CAT、RIDGE、MLP 最多 +0.0072（CAT_WX_H63）。只有秩均值集成在 WX_H63 过线（0.0588 对 0.0467，+0.0121，t 4.47），所以 `answer_family = material` 来自集成，不来自换模型族。
- 影响更大的是周期和训练窗：H63 的 RankIC 约为 H21 的 2 倍（LGBM 0.0467 对 0.0232，都是 WX），扩张窗比 3 年滚动高 0.003–0.006。
- 排序能力集中在流动性差的股票：三个入选格 T3 为 0.070–0.093，T1（流动性最好）只有 0.009–0.012，t 都小于 1。
- 入选格（按压力期 NW t 机械选出，核对无误）：XGB_WX_H63（t 5.65）、LGBM_WX_H63（5.40）、CAT_WX_H63（5.21）。

### 候选（6 个，全部计入试验）

`{XGB,LGBM,CAT}_WX_H63_{V1,V2}`。V1：全池前 50；V2：流动性最差三分位内前 50。等权，缓冲 150，21 个月度偏移，单只 ≤ 21 日成交额中位数的 1%，账户 $10 万。超参数同阶段 1，不调。

### 判定（照抄阶段 1 档案，不改）

- K1：固定 10 bp/边下偏移中位数夏普压力期 ≥ 0.65 且对标窗 ≥ 1.19，并且 20 bp/边下两窗年化 > 0。
- K2：10 bp/边下与 S3 同波动对比的组合夏普增量，两窗都 ≥ +0.05（`screen_lane.diversifier_edge_for_offset`，偏移中位数）。
- 任一本书过 K1 或 K2 → `pass_pending_spreads`（下一步是持仓的实测 NBBO 价差，不是模拟盘）；否则 `refuted`。
- 20 个随机排名安慰剂（同池、同 N、同缓冲、同成本、同偏移），报告打赢比例。
- DSR 试验次数 30（阶段 1 档案写死），只报告。
- 日线 AR 价差成本只报告，标明偏高（数据坑 #58）。

### 执行口径（本轮新写，都是实现细节）

- **复用**：`scripts/run_t20260928_30_smallcap_ml_book.py` 的 cohort、liquidity 两个阶段和 `build_signal_book`、`simulate_book`、`build_random_book`、`resolve_windows`、`offset_metric_summary`，以及它 `stage_report` 里 K2 和 DSR 的算法；模型用 `scripts/run_t20260930_17_model_family_sweep.py` 的 `FamilyModel`、`EXPANDING_TRAIN_YEARS`，H63 目标用 `kt.build_target(..., 63)`，embargo 63。两个旧脚本只导入，不改。
- **预测**：每个折的模型只用于它测试季度的每个交易日，同 T-28-30。
- **核对一（阶段 1 复现）**：用同一批折模型在压力期验证日期上重算 RankIC，每格与阶段 1 相差 ≤ 0.002。
- **核对二（组合引擎复现）**：LGBM_W3_H21（即 B0）只跑 V1、flat10，在 T-28-30 的窗口上（压力期 2017-07-03→2023-08-31，对标窗 2024-01-08→2026-09-17），偏移中位数夏普与 T-28-30 相差 ≤ 0.05（压力期 0.462，对标窗 0.327）。它是复现，不算试验。
- 任一核对不过：照常写出全部数字，但 `verdict = parity_failed`，由主审决定。
- **安慰剂**：三个 WX_H63 格用同一套折和同一股票池。先断言三格预测面板的（日期, 股票）集合相同，再每个 V 只算一套安慰剂，三格共用。
- **窗口**：用 `resolve_windows(first_predicted, latest)`；另报 2026 留出窗（受污染，只参考）。

### 已知偏差

- 入选格是按压力期 t 选出来的，所以压力期夏普对它们偏乐观。真正有约束力的是对标窗：这些格在 2024 年以后从没被看过（B0 看过）。
- 模拟器对退市后的缺失价格记 0 收益，拿不到退市收益。小盘股的退市收益平均为负，所以这是对策略有利的偏差。
- 固定 10 bp/边对流动性最差三分位偏低。所以 V2 就算过了，也只是 `pass_pending_spreads`。

### 先验

阶段 1 档案写的是"任何格子过 K1 的概率低于 5%"，本轮维持。依据：B0 的书在对标窗只有 0.33；RankIC 集中在成本最高的股票；K2 要在 S3 最强的 2024–26 年加分。
