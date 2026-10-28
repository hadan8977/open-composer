# Open Composer Step 6.8：skill 治理与 research workflow 加固

日期：2026-06-17
执行者：Codex
前置：Step 6 / 6.5 / 6.6 / 6.7
后续：仅在本步骤验收通过后再判断 Step 7.A/B/C

## 0. 一句话目标

在进入 Step 7 之前，把 Open Composer 的 agent skill 治理和 research evidence
基础路径再收紧一轮：skill 里不能保留失效 CLI 命令，manifest/repo check 必须能发现
skill 漂移，`strategy evidence` 的真实数据刷新路径不能因为 backtest 签名不兼容而中断。

## 1. 背景

Step 6.7 已经修复 `oc research auto` 的可交易信号生成问题，生成的 StrategySpec
不再依赖全 AND 和裸 `> 0` 阈值，而是使用按 rank IC 方向化的 composite score。

新的阻塞点不在因子表达式本身，而在产品工作流治理：

1. 部分 skill 仍引用不存在或过时的 CLI，例如 `oc capability evaluate <spec>`。
2. `harness/skill_manifest.yaml` 声明自己用于 repo check parity，但 repo check 只做
   很弱的存在性校验，不能验证 manifest 的 skill/hook/agent 路径。
3. `data-capability-reviewer` 要求输出 `reports/harness/data/{strategy}-capability-review.json`，
   但 harness artifact contracts 未验证该输出。
4. `strategy evidence` 会调用 `build_strategy_research_report(..., refresh_data=...)`，
   但 `run_backtest` 还不接 `refresh_data`，真实数据 evidence 路径存在 TypeError 风险。
5. 新增的 `ultracode-reviewer` 已经有价值，但尚未进入 manifest 和 repo check 治理。

## 2. 目标

- skill 指令只保留当前真实可执行的 CLI 命令。
- 明确 skill 边界：
  - `capability-evaluator`：全局 registry / fixture hygiene。
  - `data-capability-reviewer`：策略级 required capabilities、PIT、paper readiness 审查。
  - `strategy-researcher`：轻量 quick path。
  - `strategy-research-orchestrator`：完整专业 workflow。
  - `ultracode-reviewer`：代码、架构、研究 workflow 的 meta-review。
- `harness/skill_manifest.yaml` 覆盖全部 repo skills，且 repo check 校验 manifest 中的
  skill path、frontmatter name、hook path、agent path、`skills_used`。
- `llm_or_news_signal` 风险域要求 `capability_review` artifact。
- `run_backtest(..., refresh_data=True)` 能把 refresh 传给 `load_ohlcv_for_spec`。

## 3. 非目标

- 不启动 Step 7 的 ML、decay、LLM 自动提出方案。
- 不引入 sklearn / lightgbm / torch / optuna 等 ML 依赖。
- 不改 AST 表达式安全 allowlist。
- 不改 broker paper/live 写入边界。
- 不重写 backtest engine，只补 `refresh_data` 参数兼容。
- 不删除任何现有 skill；只修正边界、命令、manifest 和校验。

## 4. 执行计划

### Wave 6.8.1 — Skill 命令和边界修复

- 将 `oc capability evaluate <spec>` 替换为：
  - `uv run oc spec capabilities <spec> --json`，用于策略级 capability 检查；
  - `uv run oc capability test`，用于全局 registry / fixture 检查。
- 将 `oc strategy research-control <spec>` 从主路径替换为 `uv run oc strategy evidence <spec>`；
  deprecated research-control 只作为兼容背景，不作为推荐步骤。
- 将 `oc paper kill-switch <strategy>` 修成真实命令：
  `uv run oc paper kill-switch --enable --reason "<reason>"` /
  `uv run oc paper kill-switch --disable --reason "<reason>"`。
- 统一 quick path skill 的可复制命令格式。

### Wave 6.8.2 — Manifest 与 repo check 治理

- 把 `strategy-researcher` 和 `ultracode-reviewer` 加入 `harness/skill_manifest.yaml`。
- 把 `data-capability-reviewer` 和 `ultracode-reviewer` 纳入 repo check 的 skill 覆盖。
- repo check 校验 manifest 中：
  - 每个 `skill_path` 存在；
  - `SKILL.md` frontmatter `name` 与 manifest key 一致；
  - hooks 的 `path` 存在；
  - agents 的 `path` 存在；
  - agents 的 `skills_used` 均指向真实 skills。

### Wave 6.8.3 — Data capability artifact contract

- 在 `harness/artifact_contracts.yaml` 增加 `capability_review`。
- 在 `llm_or_news_signal.required_artifacts` 增加 `capability_review`。
- 保持普通 quant 策略不受该 artifact gate 影响。

### Wave 6.8.4 — Research evidence refresh_data P0

- 给 `open_composer/engines/backtest_engine.py::run_backtest` 增加
  `refresh_data: bool = False` 参数。
- 将其传给 `load_ohlcv_for_spec(spec, base, refresh=refresh_data)`。
- 补测试证明 `run_backtest(refresh_data=True)` 会请求刷新数据。

### Wave 6.8.5 — 验证与清理

- `scripts/sync-agent-skills.py`
- `scripts/check-agent-parity.py`
- `.venv/bin/ruff format .`
- `.venv/bin/ruff check .`
- `.venv/bin/pytest tests/ -q`
- `.venv/bin/oc repo check --strict`

## 5. 验收标准

- `rg "oc capability evaluate" .agents/skills harness` 无结果。
- `rg "oc paper kill-switch <strategy>" .agents/skills harness` 无结果。
- `oc repo check --strict` 能发现 manifest 中缺失的 skill/hook/agent 路径。
- `llm_or_news_signal` 风险域会要求 `capability_review` artifact。
- `run_backtest(refresh_data=True)` 测试通过。
- 全量测试和 repo check 通过。

## 6. Step 7 判断

本步骤完成前不执行 Step 7.A/B/C。原因是 Step 7 会放大研究 workflow 的自动化强度，
如果 skill 命令、evidence refresh、capability artifact gate 还不可靠，后续 ML/LLM/decay
结果会缺少可信治理基础。
