# README 与策略优化完成审计

日期：2026-05-11

## 目标拆解

1. 学习成熟高星项目的 README 和 code review 风格。
2. 重写本仓库 README，去掉冗余和 AI 味。
3. 建立严格的代码与文档审查方法。
4. 在优化后的产品基础上生成一个满足高门槛的研究策略。

## 证据清单

| 需求 | 证据 | 结论 |
|---|---|---|
| 学习成熟 README 风格 | 参考 `fastapi/fastapi`、`microsoft/playwright`、`pandas-dev/pandas`、`psf/requests` | 已完成 |
| 学习代码审查方法 | 参考 Google 和 Atlassian 的公开 code review 指南 | 已完成 |
| 重写 README | [README.md](../README.md) | 已完成 |
| 新增审查方法 | [docs/review-methodology.zh.md](review-methodology.zh.md) | 已完成 |
| 生成高门槛策略 | `strategy_specs/drafts/mu_breakout_volume_15m_optimized_volume_plus.yaml` | 已完成 |
| 策略回测达标 | [reports/backtests/mu_breakout_volume_15m_optimized_volume_plus-20260511T043443Z.md](../reports/backtests/mu_breakout_volume_15m_optimized_volume_plus-20260511T043443Z.md) | 已完成 |
| Dashboard 同步 | `uv run oc dashboard catalog`、`uv run oc dashboard html`、`uv run oc dashboard review-plan` | 已完成 |
| 运行验证 | `uv run oc spec validate`、`uv run oc spec capabilities`、`uv run ruff check .`、`uv run pytest` | 已完成 |

## README 审查结论

- 入口更短。
- 快速开始更直接。
- 数据与 paper 边界写清楚了。
- 研究结果和生产证据分开了。
- 不再把长篇背景塞进首页。

## 策略审查结论

- `mu_breakout_volume_15m_optimized_volume_plus` 使用了扩展后的表达式能力。
- 它满足年化和 Sharpe 门槛。
- 它只在 52 根 MU 15m sample 数据上成立，所以必须标记为 research-only。
- 这条策略适合继续做更长历史、成本敏感性和 out-of-sample 验证。

