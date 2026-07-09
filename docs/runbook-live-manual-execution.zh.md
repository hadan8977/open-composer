# Open Composer 人工实盘执行 Runbook

本文只定义人工实盘流程，不新增实盘 API，也不授权自动实盘下单。实盘启动前必须同时满足：

- `reports/paper/validation/paper-validation-report-<date>.json` 中 `paper_validation_pass=true`
- `reports/research/control/route-cross-source-validation-<date>.json` 中 `route_cross_source_pass=true`
- `uv run oc paper readiness nasdaq_tqqq_post_drawdown_reentry_router_delayed30_offensive_paper_auto_candidate --strict` 通过
- `uv run oc paper status` 显示 kill switch 未启用

## 每日流程

1. 开盘前读取通知与 `reports/paper/review_cards/YYYYMMDD.md`。
2. 若 Action 为 `No operation.`，当天不做实盘操作。
3. 若有变化，按 review card 的 `50% live weight` 列人工下单；剩余仓位放 BIL 或现金。
4. 成交后追加一行 `reports/live/manual_journal.jsonl`。
5. 若 paper cycle、state drift、数据、对账任一项 warning/error 未解释，当天实盘不操作。

`manual_journal.jsonl` 每行格式：

```json
{"date":"2026-07-09","symbol":"GLD","action":"buy","qty":100,"price":350.12,"source_review_card":"reports/paper/review_cards/20260709.md","note":"manual 50pct mapping"}
```

## 50% 仓位映射

| 路由状态 | review card 目标 | 实盘首期 |
| --- | --- | --- |
| `confirmation_transition_overlay_TQQQ` | TQQQ | TQQQ 50% + BIL/现金 50% |
| `post_drawdown_reentry` | TQQQ | TQQQ 50% + BIL/现金 50% |
| `risk_on_ranked` | 当日 selected symbol | selected 50% + BIL/现金 50% |
| `confirmation_transition` | QLD | QLD 50% + BIL/现金 50% |
| `early_deterioration_downshift` | QQQ | QQQ 50% + BIL/现金 50% |
| `hard_stress_defensive` | GLD | GLD 50% + BIL/现金 50% |
| `cooldown_transition_overlay_TQQQ` | TQQQ | TQQQ 50% + BIL/现金 50% |
| `soft_stress` | QQQ | QQQ 50% + BIL/现金 50% |
| `cooldown_transition` | QLD | QLD 50% + BIL/现金 50% |
| `selected_asset_blocked` | QLD | QLD 50% + BIL/现金 50% |
| `melt_up_peak_guard` | QLD | QLD 50% + BIL/现金 50% |

执行时以当天 review card 为准；上表用于人工复核状态是否合理。

## Kill 规则

- 每日循环连续 2 个交易日失败：暂停实盘新操作，仅允许降风险，并启用 `uv run oc paper kill-switch --enable --reason "daily cycle failed twice"`。
- 实盘账户自启动以来回撤超过 -25%：全部转 BIL/现金，强制复盘后才能恢复。
- 数据、对账、state drift 当日异常：当天实盘不操作，维持现状。
- `route_cross_source_pass=false` 或 `paper_validation_pass=false`：不得启动实盘。

## 月检

每月运行：

```bash
uv run oc data verify-research-cache
uv run oc strategy router-replay-audit
uv run oc paper validation-report
```

若 replay audit 出现 drift，先检查 research cache manifest hash，再比较策略数字；不得用调参修复审计漂移。
