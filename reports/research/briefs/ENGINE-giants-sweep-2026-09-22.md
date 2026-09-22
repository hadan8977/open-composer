# Brief ENGINE：通用扫荡引擎 `scripts/run_giants_sweep.py`

执行者：Opus（B-1 / B-2 之一回来后立刻接）。读本文件、`docs/plan-giants-sweep-2026-09-22.zh.md`、`docs/plan-strategy-factory-2026-09-22.zh.md` 第 1 节、`scripts/run_h20260918_05_recent_menu.py` 全文、B-1 与 B-2 的脚本（`reports/research/iterations/h20260922_0{2,4}_*/` 下）。目标：把三者合成一个引擎，一个 manifest 一次跑完所有候选。

## 输入：`config/giants_sweep/manifest.yaml`

每个候选一个条目：`id`、`family`、`source_url`、`reported`（原文年化/回撤/夏普/期间）、`spec`。`spec` 支持的原语（全部日线，信号日收盘出信号、次日开盘成交）：
- `menu`：标的列表；`universe_filter`：可选（历史 ≥ N 日、成交额 ≥ X）
- `rank`：{`lookback` 或 `blend` 列表, `top_n`, `rebalance`: daily|weekly|biweekly|monthly, `weighting`: equal|inverse_vol}
- `abs_filter`：{`cash_asset`: SHY|BIL, `lookback`} 相对现金的绝对动量
- `canary`：{`assets`: [...], `lookback` 或 13612W 型加权} BAA/DAA/VAA 型：canary 动量 ≤ 0 → 全进防守菜单 `defensive_menu`（其内再 rank）
- `gate`：{`type`: sma|rsi|vol|drawdown, `asset`, `window`, `threshold`, `on_true`: 资产或子 spec, `on_false`: 资产或子 spec}，可嵌套（Composer 型决策树）
- `vol_target`：{`target_ann`, `window`, `max_leverage`: 1.0, `cash_asset`}
- `drawdown_brake`：{`threshold`, `scale`, `recover`: new_high|days:N}
- `fixed_weights`：{`weights`: {sym: w}, `rebalance`}（HFEA/9-sig 型；9-sig 用 `signal_growth`: {rate, period}）
- `vix_term_structure`：{`front`: 数据源, `second`: 数据源, `long_asset`, `short_asset`, `flat_asset`}（若本机无 VIX 期货数据则标 `unrunnable` 跳过，不猜）
- `costs_bp`：[10, 20]；`exclusions`：按产品类别（short_vol, lev_3x）显式声明允许

## 输出：`reports/research/iterations/giants_sweep_20260922/`

`summary.parquet`（每 cell：id, family, params, select/holdout/anchor 的年化、回撤、夏普、换手，20 bp 下同上，安慰剂打赢比例，G1–G5 布尔，SPY/MTUM/SPMO/同波动超额）、`placebo.parquet`、`report.md`（按 G 全过 → 部分过 → 不过 分组的排名表，每组前 20）、`candidate-manifest.json`、`direction-review.json`（来源为各候选的 source_url，快照从普查简报转存）。

## 协议（不改）

窗口 warmup 2022-06-01→2023-09-15、select 2023-09-18→2025-12-31、holdout 2026-01-02→最新、anchor 2024-01-08→最新；成本 10/20 bp；安慰剂：同菜单随机挑 60 种子；门控/分支信号日历平移 1–20 日 ×20 种子；固定权重型用随机权重 60 种子。每 cell 只算一次，向量化；总运行 `./scripts/run_capped.sh --mem 1.8G`，目标 ≤ 30 分钟跑 1,000 cell。缺数据的标的写进 `unrunnable.md` 并缩窗或跳过，不猜。

## 验收

- 用 H-20260918-05 的 S1/S2/S3 三个 cell 回归：数字与该卡第 5 节一致（±0.01 夏普）。
- 单元测试只覆盖原语的最小样例（不跑全量 pytest）。
- 一个 commit；结果文件 `reports/research/briefs/ENGINE-result.md`（≤ 30 行）；回复 ≤ 300 字。
