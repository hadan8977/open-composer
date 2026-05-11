# XHigh 级别计划与审查

日期：2026-05-11

## 目标

1. 用成熟项目的 README 和审查结构，收紧本仓库文档。
2. 保持 `StrategySpec`、AGENTS、skills、capability registry 和 dashboard 的控制链一致。
3. 把部署入口缩短到最少步骤。
4. 不把 sample / fixture 研究结果写成生产证据。

## 计划

1. 调研成熟项目的 README 和 code review 结构。
2. 形成项目专用的审查方法。
3. 重写 README 和部署配置说明。
4. 检查 Codex 的控制面是否写清楚。
5. 用 `oc doctor`、`oc capability test`、`ruff` 和 `pytest` 复核。

## 计划审查标准

- README 必须短，且只保留入口信息。
- 部署说明必须只包含 `.env` 和 `.codex/config.toml` 的最小步骤。
- Codex 控制路径必须明确写出 `AGENTS.md`、`.agents/skills/`、`capabilities/registry.yaml`。
- 研究策略结果必须标明数据来源和边界。
- 代码和文档不得留下冲突标记、空洞承诺或重复真相源。

## 结论

这套计划适合当前项目，因为它把重点放在：

- 规则优先，而不是自由编辑优先；
- 文档入口优先，而不是背景堆叠优先；
- 可验证产物优先，而不是口号优先。

