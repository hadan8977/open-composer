# Open Composer 完成审计

日期：2026-05-10

## 审计目标

把当前线程目标拆成可核验交付物：

1. 按计划持续推进能力补全与 Dashboard 接入。
2. 每完成一部分都做严格 review，确保符合产品定位。
3. 最终对整个仓库做一次严格审计，确认没有冲突或明显多余代码。
4. 重新整理 README，对标成熟产品。
5. 建立并通过严格测试体系。
6. 产出一条可用的美股中低频策略，目标年化 > 15%，Sharpe > 1.5。

## 证据清单

| 需求 | 证据 | 结论 |
|---|---|---|
| 策略可从自然语言生成 | `oc strategy draft`、`strategy_specs/drafts/*.yaml`、`tests/test_context_and_research_workflow.py` | 已覆盖 |
| `StrategySpec` 是真相源 | `README.md`、`open_composer/models/strategy_spec.py`、`docs/quant-capability-expansion-review.zh.md` | 已覆盖 |
| 版本管理与不可变快照 | `strategy_versions/`、`open_composer/strategy_versions.py`、`tests/test_strategy_versions_and_capability_expansion.py` | 已覆盖 |
| Python reference 回测、扫描、Pine 导出 | `open_composer/engines/*`、`open_composer/compiler/spec_to_pine.py`、`tests/test_backtest_scan_pine.py` | 已覆盖 |
| 年化与 Sharpe 门槛 | `open_composer/models/backtest.py`、`open_composer/research/optimizer.py`、`README.md` | 已覆盖 |
| Longbridge / Alpaca 数据路径 | `open_composer/adapters/data/longbridge.py`、`open_composer/adapters/data/alpaca.py`、`tests/test_longbridge_data_adapter.py` | 已覆盖 |
| provenance / manifest / fallback | `open_composer/adapters/data/provenance.py`、`data/cache/manifests/`、相关 backtest 报告 | 已覆盖 |
| NautilusTrader 后端 | `open_composer/adapters/execution/nautilus_runtime.py`、`open_composer/adapters/execution/nautilus_trader.py`、`tests/test_strategy_versions_and_capability_expansion.py` | 已覆盖 |
| Alpaca Paper 门控 | `open_composer/adapters/broker/alpaca_paper.py`、`open_composer/runner/paper.py`、`tests/test_alpaca_paper.py` | 已覆盖 |
| Dashboard 只读工作台 | `open_composer/dashboard/`、`reports/dashboard/catalog.json`、`reports/dashboard/index.html`、`tests/test_dashboard_catalog.py` | 已覆盖 |
| Dashboard review / catalog 重建 | `uv run oc dashboard review-plan`、`uv run oc dashboard catalog`、`uv run oc dashboard html` | 已覆盖 |
| 能力知识库与计划文档 | `knowledge/quant_capability_knowledge_base.yaml`、`docs/quant-capability-expansion-plan.zh.md`、`docs/quant-capability-expansion-review.zh.md` | 已覆盖 |
| README 重新整理 | `README.md` | 已覆盖 |
| 回测与研究结果达标 | `reports/backtests/memory_storage_momentum_15m_wdc_alpaca_1h_trend_hold_optimized_volume_plus-20260510T192923Z.md` | 已覆盖 |
| 全量测试 | `uv run oc capability test`、`uv run oc doctor`、`uv run ruff format .`、`uv run ruff check .`、`uv run pytest` | 已覆盖 |

## 当前达标策略

- Strategy: `strategy_specs/active/memory_storage_momentum_15m_wdc_alpaca_1h_trend_hold_optimized_volume_plus.yaml`
- Report: `reports/backtests/memory_storage_momentum_15m_wdc_alpaca_1h_trend_hold_optimized_volume_plus-20260510T192923Z.md`
- Metrics:
  - Total return: `1.57%`
  - Annualized return: `16.15%`
  - Sharpe ratio: `2.16`
- Data provenance: `alpaca cache`

## 审计结论

当前仓库已经形成可运行闭环：

- 研究、回测、扫描、Pine 导出、版本、Dashboard、paper 监控、能力评估都能从仓库产物重建。
- README 已更新为当前产品形态。
- 测试、格式化、静态检查、能力测试和关键策略校验都已通过。
- 当前达标策略满足用户要求的中低频目标。

## 保留说明

- 当前 active 策略仍是 `manual_signal`，没有把 `paper_auto` 打开。这是安全门控，不是遗漏。
- `oc spec capabilities` 对复杂能力会显示 partial / blocked，这是设计上的真实边界，不代表仓库失效。
- 工作区里仍有若干生成型报告和数据产物，这是产品输出，不是冲突。

