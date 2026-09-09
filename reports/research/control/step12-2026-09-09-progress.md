# Step 12 · 策略 B 组 · 进度账本（2026-09-09 起）

任务书：`docs/plan-step-12-groupb-recent-regime-high-hit-rate-2026-09-09.zh.md`。执行者：Sonnet 5（无上下文接手）。本文件每个交付物一行，含 commit 号；与 A 组的 `step11-*-progress.md` 系列并行、互不覆盖。

## 时间线纪律

- 09-09 22:00 UTC 前：F1、F5 结果进账本 + 报告初稿。**F2 因内存约束变化延后**（见下）。
- 09-10 22:00 UTC 前：F3、F4 结果，报告成稿，B 组最佳候选导出。

## 内存约束变化记录（如实记录，非违反纪律）

- 09-09 早：A 组 `run_b3_grid.py`（B3 网格）正在跑，占约 2.6G。规则：只能跑 F1、F5（`--mem 0.6G`）。F1、F5 均已完成。
- 09-09 03:23 UTC：确认该网格已结束（`pgrep` 为空）。
- 09-09 07:40 UTC：协调者消息——A 组即将启动**新的**日内特征网格（同一脚本 `run_b3_grid.py`，不同调用参数，`--mem 1.8G`，预计跑数小时）。**新规则**：它跑的时候只能跑 F3（`--mem 1.2G`，数据量适中可并行）；F2、F4 需要产品线新落地的 `open_composer/research/features/panel.py`（`load_price_panel()`+`load_feature_panel()`），必须等这个网格结束。
- 09-09 07:4x UTC 起：确认新网格已在跑（`run_b3_grid.py --only step11_b3_lightgbm_grid_daily_only --test-years 2025 2026`）。按新规则，F2 顺序后移到网格结束之后，F3 提前。**F2 未能在 09-09 22:00 UTC 前交付，原因是内存纪律的强约束变化（协调者明确指示）,不是懈怠**；F2 将在网格结束后立即执行，最迟随 F3/F4 一并在 09-10 22:00 UTC 前交付。

## 交付物

| 时间 (UTC) | 交付物 | commit | 说明 |
|---|---|---|---|
| 09-09 ~02:30 | 门槛文件 `config/promotion/recent-regime-high-hit-rate-gates.json` | `5685b62` | `recent_regime_high_hit_rate_gates_v1`，与 A 组门槛独立 |
| 09-09 ~02:45 | `open_composer/research/regime/{metrics,gates}.py` + 30 测试 | `7628254` | 胜率/盈亏比/季度正比例/披露指标；门槛评估复用 `mechanism_eval`/`campaign_statistics` |
| 09-09 ~03:00 | F1 机制 `etf_pullback_mean_reversion.py`（状态机/组合合成）+ 16 测试 | `40365a1` | 10 ETF 回调均值回归,固定 1/10 仓位,next_open 成交 |
| 09-09 ~03:05 | F1 数据装载 helper（`load_common_bars`/`compute_warmup_complete_date`）+ 4 测试 | `43b58a8` | |
| 09-09 ~03:10 | F5 机制 `beta_router_reference.py`（移植 VOL02）+ 9 测试 | `fe53758` | 参考项,不参与晋级 |
| 09-09 ~03:15 | F1 驱动脚本 + 真实数据结果 + 账本记录 | `062929d` | `groupb_f1_etf_pullback_mean_reversion_v1`：7/8 门槛通过（不含 N/A 的 ML 门槛）,仅 `cagr_recent_net`(9.1% vs 20%) 与 `sharpe_excess_bil_recent`(1.15 vs 1.5) 未过 |
| 09-09 ~03:20 | F5 驱动脚本 + 真实数据结果 + 账本记录 | `e271108` | `groupb_f5_beta_router_reference_v1`：`cagr_recent_net` 21.3%（过）,但回撤 -26.4%、胜率/盈亏比/季度正比例均未过；`reference_only=True` 强制不可晋级 |
| 09-09 ~08:xx | F3 驱动脚本 `scripts/evaluate_groupb_f3_qqq_intraday_momentum.py` | TBD | 复用 `intraday_momentum_etf.py` 原 18 格网格（与任务书 prose 的"信号窗口/阈值/多空"8 格描述不一致，已在脚本/报告内如实记录并给出取舍理由）；结果见下 |
| TBD | 报告初稿 `step12-groupb-recent-regime-2026-09.md` | TBD | |
| TBD | F2 驱动脚本 + 结果 | TBD | 待 A 组网格结束 |
| TBD | F4 驱动脚本 + 结果 | TBD | 待 A 组网格结束,`--mem 1.8G` |
| TBD | B 组最佳候选导出 `reports/research/candidates/groupb_<experiment_id>/` | TBD | 需要先给 `.gitignore` 加 `reports/research/candidates/` 的窄范围放行（当前被 `reports/research/*` 规则挡住,已核实） |
| TBD | 报告成稿 | TBD | |

## 账本（`reports/research/ledger/experiments.jsonl`，gitignored，仅本地）

family 统一为 `groupb_recent_regime_high_hit_rate`（模仿 A 组 `step11_baseline_chain` 的共享 family 惯例,DSR 试验数按此 family 下累计的不同 config_hash 数自动增长）。已写入：

1. `groupb_f1_etf_pullback_mean_reversion_v1`（config_hash `f130d7e1f758fdcf`）
2. `groupb_f5_beta_router_reference_v1`（config_hash `5613290ab92f428c`）
3. `groupb_f3_qqq_intraday_momentum_v1`（跑完后补充本行）

## blocked_on_user

无。
