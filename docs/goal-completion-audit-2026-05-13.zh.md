# Open Composer `/goal` 完成审计

日期：2026-05-13

## 审计对象

目标要求：

```text
重新审查整个项目，制定审查文档，继续优化完善和精简项目代码文档文件。
确保产品功能效率与质量，不做粗糙 MVP，但保持产品定位不变。
加强回测与优化迭代系统能力。
联网搜索调研，参考其他项目、产品和论文，形成自己的理解。
支持参数调整测试时一次性多跑很多组。
参考传统量化挖掘因子等专业方法，并结合 LLM 与 Codex / 产品架构优势。
```

## Prompt 到产物检查表

| 要求 | 实际产物 / 证据 | 审计结论 |
|---|---|---|
| 重新审查整个项目 | `docs/current-unfinished-work-check.zh.md`、`docs/plan-completion-gap-audit.zh.md`、`docs/project-repository-review-2026-05-12.zh.md` 已更新当前完成状态、剩余缺口、边界和执行顺序 | 已完成 |
| 制定审查文档 | 新增 `docs/backtest-optimization-system-review.zh.md`；新增本文档；更新收敛版缺口审计 | 已完成 |
| 优化和精简文档 | 主执行文档收敛为当前检查、成熟化计划、缺口审计；旧广范围计划加历史参考提示；README 移除显眼旧 MVP 入口 | 已完成 |
| 保持产品定位不变 | AGENTS 未改；文档继续固定 `StrategySpec`、CLI + files、NautilusTrader、Alpaca Paper、Dashboard 辅助入口 | 已完成 |
| 不做粗糙 MVP 表述 | README 和主中文文档已改成个人本地工作台 / 个人版边界，不再把目标写成 MVP | 已完成 |
| 加强回测与优化迭代 | 新增 `open_composer/research/parameter_sweep.py`；新增 CLI `oc strategy parameter-sweep`；复用 `backtest_frame` 和现有评分逻辑 | 已完成 |
| 参数调整一次性多跑很多组 | `parameter-sweep` 支持多个 `--param PATH=values` 组合网格、`--max-candidates` 上限、ranked JSON / Markdown 报告 | 已完成 |
| 避免优化误导 | 报告和 JSON 都写明 in-sample；候选强制 `draft + manual_signal + broker=none`；文档要求 promotion 前做样本外 / walk-forward / 成本 / 数据源比较 | 已完成 |
| 支持表达式级参数探索 | 支持 `entry.all.0=expr1|expr2` 这类路径，能测试指标窗口或信号表达式变体 | 已完成 |
| 参考专业量化方法 | 知识库和新审查文档加入 QuantConnect、vectorbt、Backtrader、NautilusTrader、Qlib、过拟合论文等调研结论 | 已完成 |
| 结合 LLM 优势 | 新审查文档明确 LLM 可提出参数范围、解释结果、生成结构化 review，但不能在 backtest loop 内动态改参数 | 已完成 |
| 测试覆盖新增能力 | `tests/test_parameter_sweep.py` 覆盖网格报告、表达式路径、禁止 execution path、candidate cap、CLI 输出 | 已完成 |
| 功能可运行验证 | 实际运行 `oc strategy parameter-sweep`，生成 `reports/research/qqq_pullback_15m-parameter-sweep.md/.json` | 已完成 |
| 全量质量门 | `make verify` 通过；`oc capability test`、`oc feature validate`、Dashboard build、`oc deploy prepare`、`oc readiness` 已运行 | 已完成，见验证记录 |

## 验证记录

本轮实际运行并通过：

| 命令 | 结果 |
|---|---|
| `env UV_CACHE_DIR=/tmp/uv-cache uv run ruff format .` | 通过，104 files left unchanged |
| `env UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .` | 通过 |
| `env UV_CACHE_DIR=/tmp/uv-cache uv run pytest` | 通过，109 passed, 1 warning |
| `env UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_parameter_sweep.py` | 通过，5 passed |
| `env UV_CACHE_DIR=/tmp/uv-cache uv run oc strategy parameter-sweep ...` | 通过，4 candidates，写入 JSON / Markdown |
| `env UV_CACHE_DIR=/tmp/uv-cache uv run oc capability test` | 通过，registry fixture 全部可评估 |
| `env UV_CACHE_DIR=/tmp/uv-cache uv run oc feature validate` | 通过，validation report 和 manifest 写入 |
| `npm --prefix dashboard run build` | 通过 |
| `env UV_CACHE_DIR=/tmp/uv-cache make verify` | 通过，包含 ruff、pytest、Dashboard html/catalog/build、feature validate |
| `env UV_CACHE_DIR=/tmp/uv-cache uv run oc deploy prepare` | `status=warning ready=yes` |
| `env UV_CACHE_DIR=/tmp/uv-cache uv run oc readiness` | `status=warning ready=yes` |

`deploy prepare` / `readiness` 的 warning 属于当前个人版边界：

- paper monitor 建议在有 Alpaca Paper 凭证时运行 `oc paper monitor --sync-broker`；
- strategy capability readiness 仍有部分草稿策略 backend capability 为 `partial`；
- Dashboard API token 未设置时，只建议绑定 localhost 使用。

## 能力边界审查

本轮没有做：

- 完整因子平台。
- 自动机器学习 alpha factory。
- 云端并行优化。
- 多资产组合优化器。
- 自动把最佳参数升为 active / paper_auto。
- 真钱 broker 写入。
- Dashboard 作为唯一入口。

这些没有做是正确的，因为它们不属于当前个人使用版闭环的最小阻断项。后续如果要继续增强研究验证，下一步应只补：

1. 样本外切分。
2. walk-forward。
3. 成本/滑点敏感性。
4. Alpaca / Longbridge / sample 数据源比较。
5. Dashboard 读取 parameter sweep 报告。
6. LLM 对 sweep 结果做结构化 review summary。

## 审计结论

本轮目标中的项目审查、文档收敛、回测优化迭代增强、批量参数测试、调研沉淀、测试验证都已经落到具体产物。

剩余内容属于下一阶段能力路线，不应被当成本轮未完成项。
