# Open Composer 代码与文档审查方法

日期：2026-05-13

## 目标

这份方法用于审查仓库代码、README、产品文档和生成物，目标是：

1. 找出重复、冗余、过度承诺和难以维护的内容。
2. 确认仓库里只有一个可信真相源。
3. 确认每个公开能力都能用命令、测试或产物证明。
4. 把 README 写成简洁、可执行、可复现的入口页，而不是宣传页。
5. 确认 Codex 在策略研究中不会被单点参数束缚，而是输出参数范围、批量测试、再从方法层继续迭代。

## 参考风格

审查时参考了几类成熟项目的 README 结构：

- FastAPI：一句话定位、快速开始、明确入口。
- Playwright：安装、最小示例、文档入口、功能边界。
- pandas：清楚的项目定位、文档入口、开发入口、贡献入口。
- Requests：短句说明、实用命令、边界清晰。

代码审查方法参考了公开的 code review best practices：

- 先看改动是否必要，再看实现是否正确。
- 先看事实证据，再看描述。
- 先看边界和失败路径，再看主路径。
- 先看数据流和权限流，再看展示层。

Codex 审查方法参考 OpenAI 官方 Codex 文档：

- Codex 可靠性来自“写测试、跑检查、确认行为、复审 diff”的闭环，而不是只生成代码。
- 项目应把稳定工作流写入 `AGENTS.md`、README 和 repo skill，避免每次靠长提示词重新约束。
- GitHub/Codex review 可读取 `AGENTS.md` 的 review guidelines，因此项目级审查标准要放在仓库里。

量化研究方法参考 Bailey、Borwein、Lopez de Prado、Zhu 关于 backtest overfitting 的研究、Deflated Sharpe Ratio 思路，以及 Lopez de Prado 的 purged / embargoed cross-validation 方向：

- 大量试参会抬高“最佳结果”的偶然性，单一最高收益不能作为策略质量证据。
- 参数搜索和策略设计要分离：Codex 可以提出参数范围，工具负责批量跑，下一轮迭代优先讨论方法、数据和因子，而不是围绕一个数值继续微调。
- 任何候选进入 paper 前都必须有样本外、walk-forward、成本敏感性、买入持有基准、数据源对照和未来函数检查。

## 审查顺序

1. 先看 `git status` 和 `git diff --stat`。
2. 再看 `README.md`、`AGENTS.md`、`OPEN-COMPOSER-BUILD-HANDOFF.md` 和产品计划文档。
3. 再看核心模型、CLI、能力注册、数据适配器、执行后端、Dashboard、paper 管控。
4. 再看测试，确认每个公开能力都有覆盖。
5. 最后看生成物和报告，确认没有重复真相源。
6. 对策略研究路径单独检查：自然语言 idea -> draft spec -> capability evaluation -> spec validate -> backtest -> parameter sweep -> promotion report -> signal log / review，而不是 idea -> 单一策略结果。

## 本项目的专门检查点

- `StrategySpec` 是否仍然是唯一真相源。
- `AGENTS.md`、`.agents/skills/` 和 `capabilities/registry.yaml` 是否和 README 里的控制说明一致。
- `paper_auto`、`alpaca_paper`、`NautilusTrader` 和 Dashboard 是否被正确门控。
- sample / fixture / cache / live fetch 是否被正确标注，不把研究数据写成生产证据。
- README 是否只保留入口信息，不堆叠背景和重复说明。
- 回测报告是否同时显示策略收益、buy-and-hold、Alpha、交易数、bar 数、成本和 data sanity。
- `OPENAI_BASE_URL` 是否按用户本地信任配置处理；允许 OpenAI 兼容中转，不因非官方域名直接阻断 review / drafting 调用。
- LLM 因子是否通过 point-in-time feature packet replay，不允许在 backtest loop 中动态调用 LLM 或读未来信息。
- 参数扫描是否只写 draft / manual_signal 候选，并且标注 in-sample、质量旗标和 promotion 前置条件。

## 代码审查清单

- 是否出现第二个真相源。
- 是否出现重复实现，尤其是执行、回测、数据和版本逻辑。
- 是否存在未门控的写操作。
- 是否把试验能力误写成已完成能力。
- 是否把 sample / fixture 结果当成生产市场证据。
- 是否缺少版本、spec hash、数据 provenance 或审计信息。
- 是否有未使用的代码、过度抽象或难以解释的分支。
- 是否新增功能后补了对应测试。
- 是否存在未来函数风险：未 lag 的 breakout level、使用完整样本统计、事件/news published_at 缺失、执行前可见性不明。
- 是否存在过拟合风险：短样本、低交易数、高 Sharpe、高年化、大量参数组合、只报最佳候选、不报失败候选。
- 是否缺少买入持有基准或 Alpha 对照。

## 文档审查清单

- 开头是否在两三句内说清楚项目是什么。
- 是否直接告诉读者怎么跑。
- 是否把边界写清楚。
- 是否只保留真实可用的命令。
- 是否把研究结果和生产证据分开。
- 是否告诉 Codex：先输出可调参数范围，再用 `oc strategy parameter-sweep` 批量跑，不要只给一套参数。
- 是否告诉 Codex：参数扫描结果只能推动 promotion report，不能直接成为 benchmark 或 paper candidate。
- 是否避免空泛表述和“未来将支持一切”的说法。
- 是否把 README 当入口页，而不是文档总目录。

## 结论标准

只有同时满足下面几条，才算审查通过：

- 命令能跑。
- 测试能过。
- 公开文档和实际能力一致。
- 产物之间可以回链到版本、数据和审计。
- 没有新的未经验证承诺。

## 本次审查结论

以本地提交 `3d7ed69a6674b4a358039951d26679702dc15cba` 为基线；由于 `.git/FETCH_HEAD` 在沙箱内只读，`git fetch origin` 未能更新本地远端引用，因此 GitHub README 通过公开 raw URL 进行核对。当前 README 与本地版本在主体结构上保持一致。

项目已经具备较好的底座：`StrategySpec` 仍是真相源；Python reference 是确定性回测；NautilusTrader 是事件驱动执行路径；参数扫描、promotion report、data sanity、feature packet replay 和 paper safety gate 已存在。

主要缺口是入口引导和研究报告的证据密度：Codex 第一眼不够明确地看到“参数范围 -> 批量 sweep -> promotion report -> paper gate”的主路径；参数扫描和回测报告此前没有把 buy-and-hold / Alpha 放到同等显眼位置。已通过本轮修改补上。

## 后续必须保持的底线

- 不把 sample / fixture / fallback 结果当市场证据。
- 不把单次最优参数当策略能力。
- 不在回测执行循环里调用 LLM。
- 不因 `OPENAI_BASE_URL` 是受信任的第三方 OpenAI 兼容中转而阻断结构化 review / drafting；风险边界由本地配置和用户信任决定。
- 不自动提交 paper order；paper order 仍需 active `paper_auto` spec、readiness 和显式确认。
