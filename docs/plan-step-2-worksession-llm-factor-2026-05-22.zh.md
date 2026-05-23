# Open Composer Step 2：工作会话 + LLM 因子 + Codex SDK 集成（Plan B）

日期：2026-05-22
执行者：Codex / Claude Code
前置：Step 1 完成（删 legacy / 合并抽象 / Router 重构 / Pydantic 收缩 / 研究证据合并）
后续：Step 3（Dashboard-first 全交互）

## 0. 一句话目标

把"agent 一次性工单"升级为"持续工作会话"，把"LLM 因子合规检查"升级为"完整的 prompt 设计 → PIT 物化 → 回测 replay → 边际验证闭环"，同时引入 Codex SDK 作为可选的 agent 真实绑定（保留文件契约作为审计源）。

## 1. 背景（无上下文也能看懂）

Open Composer 是一个个人 AI 量化策略工作台，源头是 `StrategySpec`（YAML），CLI 入口是 `oc`，agent 是 Codex / Claude Code。Step 1 完成后产品基线干净，但仍有两个核心能力缺口：

### 缺口 A：策略迭代是"一次性工单"，不是"持续会话"

当前用户点 Dashboard "继续优化" → 写一个 `reports/agent_requests/*.json` → 用户手动跑 codex / claude → agent 不知道上次做了什么 → 同样的失败容易重复发生。`research/control.py` 有个 1KB 的 LLM memory packet，但 1KB 在 200K-1M context 模型上几乎不携带任何事实。

### 缺口 B：LLM/news/event/macro 因子只能"检查合规"，不能"设计-物化-回放-验证"

当前 `FactorConfig.source = expression | llm_feature | feature_packet`，可以校验 PIT 元数据是否齐全，但没有：

- 一个标准的 prompt template / output schema / cache policy 声明
- 一个"对历史输入窗口批量调 LLM 生成 PIT packets"的 pipeline
- 一个"quant baseline vs LLM variant vs missing modality fallback"的边际贡献评估闭环

### 缺口 C：Codex / Claude Code 不能被产品可靠驱动

Codex CLI v0.128 已有 native session persistence（`~/.codex/sessions/*.jsonl`）+ Memories 系统，并提供 Python SDK + JSON-RPC 2.0 协议（codex app-server）。Claude Agent SDK 有 `ClaudeSDKClient` 持久 session。用户已确认 token 成本不是约束，可以使用 GPT 系列 SDK。

## 2. 目标 / 非目标

### 目标

1. **删除 1KB memory 截断**，把 context 编译扩到 32KB 默认 / 128KB 上限，落入 `projects/{id}/context.md`。
2. **新增双向文件通道**：`projects/{id}/queue.jsonl`（用户/Dashboard → agent）+ `projects/{id}/trace.jsonl`（agent → 历史，OpenTelemetry GenAI 字段命名）。
3. **删除 `reports/agent_requests/` 路径**，把 IterationController 改写为 "context 编译器 + queue 写入器"。
4. **扩展 `FactorConfig.source = llm_feature`** 加 `input_view / input_view_version / prompt_template_path / output_schema / cache_policy` 子字段。
5. **新增 `oc feature materialize <strategy>`**：对历史窗口批量调 LLM，写 PIT feature packets，落到 `reports/features/{strategy}/{factor}/`。
6. **扩展 promotion**：加 quant baseline / LLM variant / missing-modality fallback / marginal lift / robustness 5 项 LLM 因子边际证据（合并到现有 `promotion.py`，不新建报告）。
7. **新增 `open_composer/agent_backend/`**：`CodexAgentBackend`（基于 codex app-server JSON-RPC）作为可选实时绑定；保留 `FileQueueAgentBackend` 作为永远可用的 fallback。
8. **新增 `oc project continue` 命令**：写入 queue + 编译 context + 可选触发 CodexAgentBackend。

### 非目标（明确不做）

- 不引入 Python Strategy Module（违反 `expressions.py` 的 AST 安全白名单）。
- 不引入 `strategy_kind` 独立字段（可从 factors.source + portfolio.mode 推导）。
- 不引入 `llm_factors` 并行字典（扩展现有 `FactorConfig` 即可）。
- 不允许 backtest loop 中 live LLM call —— 必须先 materialize 再 replay。
- 不改 4 个 pass 语义（workflow / research / llm_contribution / paper_ready）。
- 不改 harness 规则（`harness/risk_domains.yaml` 等）。
- 不改 Dashboard UI（留给 Step 3 大改）。
- 不删 file 契约作为审计源（即使有 CodexAgentBackend，trace.jsonl / context.md 仍是真相）。

## 3. 当前状态扫描（Step 1 完成后的关键文件）

```text
open_composer/
  models/
    strategy_spec.py        # FactorConfig 在这里扩展
    project.py              # StrategyProject / StrategyProjectRun（已存在）
  research/
    control.py              # 1KB memory 截断，需改 32KB
    iteration_controller.py # create_project_iteration_request（要改写）
    drafter.py
    evidence.py             # Step 1 新增的研究证据汇总
  projects.py               # StrategyProject 生命周期
  feature_packets.py        # FeaturePacketRow 已存在（PIT schema）
  agent_requests.py         # Step 1 已标 deprecated；Step 2 完全删除
  cli.py                    # 加新命令的入口
  dashboard/
    server.py               # /api/projects/.../request 端点（要改）

projects/{id}/
  project.yaml              # 已存在
  context.md                # 已存在（1KB-32KB 扩展）
  runs/round-XXX.yaml       # 已存在

reports/
  features/                 # 已存在（feature packet 落盘）
  research/                 # 已存在
```

## 4. 改动清单（按 Wave 分批）

### Wave 2.1 — context 扩容 + queue/trace 通道（**基础设施**）

**4.1.1 改 `research/control.py`：1KB → 32KB context.md 编译器**

```python
# 改动前：
MAX_MEMORY_BYTES = 1024

# 改动后：
DEFAULT_CONTEXT_BYTES = 32 * 1024     # 32KB 默认
MAX_CONTEXT_BYTES = 128 * 1024        # 128KB 上限
```

`update_research_control` 不再写"1KB memory packet"，而是写 `projects/{id}/context.md`。结构（Markdown）：

```markdown
# Project Context — {project_name}

Last updated: 2026-05-22T10:30:00Z
Last spec hash: abc123def...
Project state: iterating | candidate | paper_review | ...

## Strategy Spec Summary
- Name: ...
- Universe: ...
- Timeframe: ...
- Position direction: ...
- Portfolio mode: ...
- Required capabilities: ...
- Factors (count by source): expression=N, llm_feature=N, feature_packet=N

## Four-Pass Status
- workflow_pass: ✅ / ❌ — reason
- research_pass: ✅ / ❌ — reason
- llm_contribution_pass: ✅ / ❌ / N/A — reason
- paper_ready_pass: ✅ / ❌ — reason

## Evidence Tracks
### Factor Quality
- Status: ok / warning / blocked
- Summary: 1-3 lines
- Artifact: reports/research/{strategy}-factor-lab.json

### Execution Reality
- Status: ...
- Artifact: ...

### Alt/LLM Evidence
- Status: ...
- LLM factor materialization status: prompt_hash / packet_count / last_materialized_at
- Artifact: ...

## Latest 5 Runs (from runs/round-XXX.yaml)
1. Round 3 (2026-05-21): status=warning, changed={spec, factor_lab.json}, blocker=walk_forward_failed
2. Round 2 (2026-05-20): ...
...

## Blockers and Warnings
- promotion: cost_sensitivity check has blocked status (slippage_50bps degrades alpha to -0.3%)
- ...

## Do Not Repeat (from blocker_summary history)
- Already tried RSI threshold 70/80 — no improvement; do not retry without volume filter
- ...

## Artifact Path Index (not full content; agent should read on demand)
- spec: strategy_specs/active/{name}.yaml
- latest backtest: reports/runs/{run_id}.json
- promotion: reports/research/{name}-promotion.json
- factor lab: reports/research/{name}-factor-lab.json
- ...

## Pending User Commands (latest 5 from queue.jsonl)
- [2026-05-22T08:15] continue: "尝试更激进的止损 0.5-0.8%"
- [2026-05-22T07:50] advice: "重点关注成交量过滤"
- ...
```

写入路径：`projects/{id}/context.md`（覆盖写，每次刷新整体重建）。

**4.1.2 新增 `projects/{id}/queue.jsonl`**

每行一个 JSON 对象：

```json
{"ts": "2026-05-22T10:00:00Z", "id": "q_abc123", "from": "user", "via": "dashboard|cli|api", "kind": "continue|advice|stop|llm_factor_eval|materialize|approve|activate_paper", "body": "....", "metadata": {"requested_by": "..."}}
```

`kind` 取值：

```text
continue            # 继续下一轮研究优化
advice              # 用户给定方向建议（含在 body）
stop                # 停止迭代
llm_factor_eval     # 评估 LLM 因子边际贡献
materialize         # 触发 feature materialize
approve             # 提升到 approved
activate_manual     # 激活手动 signal
activate_paper      # 激活 paper auto（需额外确认）
disable             # 退役
```

新增 `open_composer/projects.py` 接口：

```python
def append_queue(
    project_id: str,
    kind: QueueCommandKind,
    body: str,
    *,
    via: Literal["dashboard", "cli", "api"] = "cli",
    metadata: dict[str, Any] | None = None,
    root: Path | None = None,
) -> QueueCommand: ...

def read_queue(project_id: str, root: Path | None = None) -> list[QueueCommand]: ...

def mark_queue_command_consumed(
    project_id: str, command_id: str, root: Path | None = None
) -> None: ...
```

**4.1.3 新增 `projects/{id}/trace.jsonl`**

每行一个 JSON 对象（字段命名兼容 OpenTelemetry GenAI semantic conventions）：

```json
{
  "ts": "2026-05-22T10:01:30Z",
  "span_id": "sp_abc123",
  "parent_span_id": null,
  "agent": "codex|claude_code|cli",
  "operation": "tool_call|inference|file_write|cli_command",
  "tool.name": "oc strategy evidence",
  "tool.input_hash": "sha256:...",
  "tool.output_hash": "sha256:...",
  "artifact.path": "reports/research/foo-promotion.json",
  "gate.name": "promotion_report",
  "gate.status": "warning",
  "model": "gpt-5.0|claude-opus-4-7",
  "input_tokens": 12345,
  "output_tokens": 678,
  "error.type": null,
  "queue_command_id": "q_abc123"
}
```

新增 `open_composer/projects.py` 接口：

```python
def append_trace(
    project_id: str,
    *,
    agent: Literal["codex", "claude_code", "cli", "system"],
    operation: str,
    queue_command_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    root: Path | None = None,
) -> TraceEntry: ...

def read_trace_tail(project_id: str, n: int = 20, root: Path | None = None) -> list[TraceEntry]: ...
```

**4.1.4 删除 `reports/agent_requests/` 与 `open_composer/agent_requests.py` 模块**

```bash
rm -rf reports/agent_requests/
rm open_composer/agent_requests.py
```

清理引用：

- `open_composer/projects.py`：删除 `create_agent_request` 相关调用，`create_project` 不再生成 agent request。
- `open_composer/research/iteration_controller.py`：改写 `create_project_iteration_request` 见 4.1.5。
- `open_composer/cli.py`：删除 `agent_app` 整个子命令组（Step 1 已删，确认）。
- `open_composer/dashboard/server.py`：删除任何 agent_request 相关端点。

**4.1.5 改写 `research/iteration_controller.py`**

新接口：

```python
def continue_project(
    project_id: str,
    *,
    body: str = "",
    kind: QueueCommandKind = "continue",
    via: Literal["dashboard", "cli", "api"] = "cli",
    root: Path | None = None,
) -> ContinueResult:
    """
    1. 加载 project
    2. 刷新 artifact_state（projects/{id}/artifact-state.json）
    3. 重新编译 context.md（32KB）
    4. append queue.jsonl 一行
    5. 返回 ContinueResult（含 context_path / queue_command_id / 推断的 intent）
    
    不再生成 reports/agent_requests/*.json。
    不再生成 iteration-plan-latest.json（已并入 context.md）。
    """
```

旧 `create_project_iteration_request` 保留为 `def create_project_iteration_request(*args, **kwargs): return continue_project(...)` 的薄包装，标 deprecated。

**4.1.6 CLI：新增 `oc project continue`**

```python
@project_app.command("continue")
def project_continue_command(
    project_id: str,
    advice: Annotated[str | None, typer.Option("--advice")] = None,
    advice_file: Annotated[Path | None, typer.Option("--advice-file")] = None,
    kind: Annotated[str, typer.Option("--kind")] = "continue",
    rounds: Annotated[int, typer.Option("--rounds")] = 1,
    requested_by: Annotated[str, typer.Option("--requested-by")] = "cli",
) -> None:
    """Append a queue command and recompile context for a strategy project."""
    body = (advice or "")
    if advice_file:
        body = advice_file.read_text(encoding="utf-8")
    result = continue_project(
        project_id,
        body=body,
        kind=kind,
        via="cli",
        root=project_root(),
    )
    console.print(f"[green]queue command written[/green] {result.queue_command_id}")
    console.print(f"context: projects/{project_id}/context.md ({result.context_bytes} bytes)")
```

`oc project iterate` 保留为 alias（hidden=True）。

**Wave 2.1 验收**：

```bash
uv run oc project create --name foo --thesis "test" --idea "..."
uv run oc project continue foo --advice "test advice"
# 文件存在：
ls projects/foo/queue.jsonl projects/foo/trace.jsonl projects/foo/context.md
# context.md 大小 > 1KB（已扩容）
wc -c projects/foo/context.md

# 旧路径不存在
test ! -d reports/agent_requests
test ! -f open_composer/agent_requests.py

uv run pytest tests/
make verify
```

---

### Wave 2.2 — FactorConfig 扩展（**LLM 因子 schema 升级**）

**4.2.1 改 `open_composer/models/strategy_spec.py` 的 `FactorConfig`**

```python
class LLMFactorOutputSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # JSON Schema 风格，限定 LLM 输出格式
    type: Literal["object"] = "object"
    required: list[str] = Field(default_factory=list)
    properties: dict[str, dict[str, Any]] = Field(default_factory=dict)


class LLMFactorCachePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["materialize_then_replay"] = "materialize_then_replay"
    key_fields: list[str] = Field(
        default_factory=lambda: [
            "symbol", "visible_at", "input_view_version",
            "input_hash", "prompt_hash", "model", "schema_version",
        ]
    )


class FactorConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: Literal["expression", "llm_feature", "feature_packet"] = "expression"
    expression: str | None = None
    path: str | None = None
    field: str | None = None
    default: float | bool = 0.0
    description: str = ""

    # ✦ 新增：仅 source=llm_feature 时使用
    input_view: str | None = None              # 例如 "news_window_v1"
    input_view_version: int | None = None      # 数字版本，input_view 内部结构变更时升版
    prompt_template_path: str | None = None    # 例如 "prompts/news_regime_score.md"
    output_schema: LLMFactorOutputSchema | None = None
    cache_policy: LLMFactorCachePolicy | None = None
    model_ref: str | None = None               # 例如 "gpt-5.0"；None 时用环境默认

    @model_validator(mode="after")
    def require_factor_source_fields(self) -> FactorConfig:
        if self.source == "expression" and not self.expression:
            raise ValueError("expression factors require expression")
        if self.source == "feature_packet" and not self.field:
            raise ValueError("feature_packet factors require field")
        if self.source == "llm_feature":
            missing = [
                name for name, value in {
                    "field": self.field,
                    "input_view": self.input_view,
                    "input_view_version": self.input_view_version,
                    "prompt_template_path": self.prompt_template_path,
                    "output_schema": self.output_schema,
                }.items() if not value
            ]
            if missing:
                raise ValueError(
                    f"llm_feature factor requires: {', '.join(missing)}"
                )
            # cache_policy 给默认即可
            if self.cache_policy is None:
                self.cache_policy = LLMFactorCachePolicy()
        return self
```

同步更新 `schemas/strategy_spec.schema.json`。

**4.2.2 示例 spec（写入文档与测试）**

```yaml
# strategy_specs/drafts/qqq_news_regime_15m.yaml （示例片段）
factors:
  news_regime_score:
    source: llm_feature
    field: regime_score
    default: 0.0
    description: "News regime score derived from headlines window."
    input_view: news_window_v1
    input_view_version: 3
    prompt_template_path: prompts/news_regime_score.md
    output_schema:
      type: object
      required: [score, confidence]
      properties:
        score: {type: number, minimum: -1, maximum: 1}
        confidence: {type: number, minimum: 0, maximum: 1}
    cache_policy:
      mode: materialize_then_replay
      key_fields: [symbol, visible_at, input_view_version, input_hash, prompt_hash, model, schema_version]
    model_ref: gpt-5.0
```

**4.2.3 删除并行 `llm_factors` / `strategy_kind` / `strategy_module` 字段计划**

明确：不引入这些新字段。原 agent-native-worksession-plan 中 P4/P7 的对应内容**作废**。

**Wave 2.2 验收**：

```bash
uv run oc spec validate strategy_specs/drafts/qqq_news_regime_15m.yaml
# 应通过；故意缺 input_view 时应明确报错

uv run pytest tests/ -k "factor_config"
```

---

### Wave 2.3 — Feature Materialization Pipeline（**核心新能力**）

**4.3.1 新增 `open_composer/research/llm_materialize.py`**

```python
"""LLM Feature Materialization — 对历史输入窗口批量调 LLM，写 PIT feature packets。

cache key = symbol + visible_at + input_view_version + input_hash + prompt_hash + model + schema_version

prompt 改了 → prompt_hash 变 → cache miss → 触发重算
input_view 结构变了 → input_view_version 升 → cache miss
LLM 模型升级 → model 变 → cache miss
feature packet schema 升级 → schema_version 变 → cache miss
"""

from __future__ import annotations
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from open_composer.models.strategy_spec import FactorConfig, StrategySpec, load_strategy_spec
from open_composer.feature_packets import FeaturePacketRow, write_feature_packet
from open_composer.config import project_root, ensure_dir


SCHEMA_VERSION = "2"   # bump 时全部 packets 失效


@dataclass(frozen=True)
class MaterializationResult:
    strategy_name: str
    factor_name: str
    prompt_hash: str
    input_view_version: int
    model: str
    packet_count: int
    cache_hits: int
    cache_misses: int
    packets_path: Path
    run_path: Path
    trial_ledger_path: Path
    skipped_for_existing: int
    errors: int


def materialize_factor(
    spec_path: Path,
    factor_name: str,
    *,
    root: Path | None = None,
    backend: str = "openai",       # 见 4.4 节
    refresh: bool = False,         # True 时强制重算
) -> MaterializationResult:
    """对一个 llm_feature factor 跑物化。

    1. 加载 spec，校验 factor.source == 'llm_feature'
    2. 加载 prompt template，算 prompt_hash
    3. 构造 input view（input_view + symbol + visible_at 窗口）
    4. 对每个历史时间点：
       a. 算 input_hash
       b. 查 cache（packets.jsonl 已有相同 key 的行）
       c. miss 时调 LLM backend，校验 output_schema
       d. append FeaturePacketRow 到 packets.jsonl
       e. append 到 prompt-trial-ledger.jsonl
    5. 写 materialization-run.json
    """
```

输出路径：

```text
reports/features/{strategy}/{factor}/packets.jsonl
reports/features/{strategy}/{factor}/materialization-run.json
reports/features/{strategy}/{factor}/prompt-trial-ledger.jsonl
prompts/{factor}.md                              # prompt 模板，被 prompt_template_path 引用
```

**4.3.2 CLI：`oc feature materialize`**

```python
@feature_app.command("materialize")
def feature_materialize_command(
    spec: Path,
    factor: Annotated[str | None, typer.Option("--factor",
        help="单一 factor 名；省略则物化 spec 中所有 llm_feature factors。")] = None,
    backend: Annotated[str, typer.Option("--backend",
        help="openai | anthropic | local_test_stub。")] = "openai",
    refresh: Annotated[bool, typer.Option("--refresh",
        help="强制重算，忽略 cache。")] = False,
) -> None:
    """对 llm_feature factor 跑 PIT 物化。"""
    spec_obj = load_strategy_spec(spec)
    targets = (
        [factor] if factor
        else [name for name, fc in spec_obj.factors.items() if fc.source == "llm_feature"]
    )
    if not targets:
        raise typer.BadParameter("spec 没有 source=llm_feature 的 factor")
    for name in targets:
        result = materialize_factor(spec, name, backend=backend, refresh=refresh)
        console.print(
            f"[green]{name}[/green] packets={result.packet_count} "
            f"hits={result.cache_hits} misses={result.cache_misses} "
            f"errors={result.errors} path={result.packets_path}"
        )
```

**4.3.3 严格"无 live LLM call in backtest loop"**

修改 `open_composer/expressions.py`：当 `evaluate_rule_block` 遇到 `source=llm_feature` 的 factor 时，**只从已落盘的 packets.jsonl 读取**；找不到 visible_at ≤ bar timestamp 的对应 packet 时，使用 `factor.default`，并把 cache miss 写入当次 run 的 `data_sanity.warnings`。

新增 `open_composer/feature_packets.py` 函数：

```python
def lookup_factor_value(
    strategy_name: str,
    factor: FactorConfig,
    factor_name: str,
    symbol: str,
    at: datetime,
    root: Path,
) -> tuple[Any, Literal["pit_hit", "default_fallback"]]:
    """从 reports/features/{strategy}/{factor}/packets.jsonl 找最新 visible_at ≤ at 的 packet。"""
```

**4.3.4 backend 抽象（占位）**

```python
# open_composer/research/llm_backends.py
from typing import Protocol

class LLMBackend(Protocol):
    def infer(
        self,
        *,
        model: str,
        prompt: str,
        input_payload: dict[str, Any],
        output_schema: dict[str, Any],
    ) -> dict[str, Any]: ...


class OpenAIBackend:
    def infer(self, **kwargs):
        # 用 OPENAI_API_KEY / OPENAI_BASE_URL / OPENAI_MODEL（已有 config）
        # JSON schema mode 输出
        ...


class LocalTestStub:
    """单元测试用：返回确定性虚拟值。"""
    def infer(self, **kwargs):
        return {"score": 0.0, "confidence": 0.5}


def get_backend(name: str) -> LLMBackend: ...
```

`materialize_factor` 通过 `get_backend(name)` 获取后端。`OpenAIBackend` 默认使用 GPT 系列（用户已确认 token 不是约束）。

**Wave 2.3 验收**：

```bash
# 准备示例 prompt 与 spec（见 4.2.2）
echo "Given the following news headlines for {symbol} window {window}, output {score, confidence} ..." \
  > prompts/news_regime_score.md

# 物化
uv run oc feature materialize strategy_specs/drafts/qqq_news_regime_15m.yaml --backend local_test_stub

# 验证
test -f reports/features/qqq_news_regime_15m/news_regime_score/packets.jsonl
test -f reports/features/qqq_news_regime_15m/news_regime_score/materialization-run.json
test -f reports/features/qqq_news_regime_15m/news_regime_score/prompt-trial-ledger.jsonl

# 再跑一次：应该全 hit
uv run oc feature materialize strategy_specs/drafts/qqq_news_regime_15m.yaml --backend local_test_stub
# 输出 hits=N misses=0

# 改 prompt 后再跑：应该全 miss
echo "MODIFIED PROMPT" >> prompts/news_regime_score.md
uv run oc feature materialize strategy_specs/drafts/qqq_news_regime_15m.yaml --backend local_test_stub
# 输出 hits=0 misses=N
```

---

### Wave 2.4 — Promotion 扩展：LLM 因子边际证据

**4.4.1 改 `open_composer/research/promotion.py`**

在 `build_promotion_report` 的 default 路径增加 5 个 LLM 因子专属 check（只在 spec 含有 `source=llm_feature` factor 时激活）：

```python
def _llm_marginal_lift_checks(
    spec: StrategySpec,
    frame: pd.DataFrame,
    root: Path,
) -> list[GateResult]:
    """LLM 因子边际贡献证据。

    返回 5 个 GateResult：
    1. quant_baseline_metric        — 去掉所有 llm_feature factor，跑 baseline backtest
    2. llm_variant_metric           — 含 llm_feature factor，跑 variant backtest
    3. missing_modality_robustness  — llm packet 故意删一部分后跑 backtest（模拟 LLM 服务故障）
    4. marginal_lift                — variant - baseline 的指标差（Sharpe / Return / Win rate）
    5. independence_check           — variant 信号集是否与 baseline 显著不同（Jaccard < 0.7）
    """
```

5 项任一 blocked 时 `llm_contribution_pass = False`；全部 ok 时 `llm_contribution_pass = True`；spec 不含 llm_feature factor 时 `llm_contribution_pass = None`（N/A）。

**4.4.2 现有 `alt_data_quality.py` / `hybrid_news_evidence.py` / `alternative_data_evidence.py` 不动**

它们仍负责 PIT 完整性 / 数据质量检查；新增的 5 个 check 专注边际贡献。

**Wave 2.4 验收**：

```bash
uv run oc strategy evidence strategy_specs/drafts/qqq_news_regime_15m.yaml
# promotion 报告含 5 个新 check：quant_baseline / llm_variant / missing_modality / marginal_lift / independence
# llm_contribution_pass 字段有明确值
```

---

### Wave 2.5 — Codex SDK 集成（**可选 agent 真实绑定**）

**4.5.1 新增 `open_composer/agent_backend/`**

```text
open_composer/agent_backend/
  __init__.py
  base.py            # AgentBackend Protocol
  file_queue.py      # FileQueueAgentBackend（永远可用的 fallback）
  codex_sdk.py       # CodexAgentBackend（用 codex app-server JSON-RPC）
```

```python
# base.py
from typing import Protocol, Any
from dataclasses import dataclass

@dataclass
class AgentSessionStatus:
    backend: str
    session_id: str | None
    status: Literal["idle", "running", "lost", "disabled"]
    last_seen_at: datetime | None
    queue_pending: int

class AgentBackend(Protocol):
    name: str
    def send_command(
        self,
        project_id: str,
        *,
        kind: str,
        body: str,
        root: Path,
    ) -> str:  # 返回 queue_command_id
        ...

    def status(self, project_id: str, root: Path) -> AgentSessionStatus: ...

    def stop(self, project_id: str, root: Path) -> None: ...
```

**4.5.2 `file_queue.py`（fallback，永远可用）**

```python
class FileQueueAgentBackend:
    name = "file_queue"

    def send_command(self, project_id, *, kind, body, root):
        # 只 append queue.jsonl，依赖用户/外部 agent tail
        return append_queue(project_id, kind=kind, body=body, root=root).id

    def status(self, project_id, root):
        # 通过 trace.jsonl 最后一行 ts 推断
        ...

    def stop(self, project_id, root):
        append_queue(project_id, kind="stop", body="", root=root)
```

**4.5.3 `codex_sdk.py`（Codex 真实绑定）**

```python
"""CodexAgentBackend — 通过 codex app-server JSON-RPC 2.0 控制持久 codex session。

需要环境：
- 已安装 codex CLI （ codex --version 可用）
- 已配置 OPENAI_API_KEY 或 Codex auth
- Python 包：codex_sdk（OpenAI 官方 Python SDK for codex app-server）

session 持久化：codex CLI 自身已经把 session 落到 ~/.codex/sessions/*.jsonl，
我们用 session_id 关联 projects/{id}/session-binding.yaml。
"""
import json
from pathlib import Path

# 占位依赖（codex-sdk 是 OpenAI 提供的 python 包；codex CLI v0.128+）
try:
    from codex_sdk import CodexAppServerClient   # type: ignore
except ImportError:
    CodexAppServerClient = None


class CodexAgentBackend:
    name = "codex_sdk"

    def __init__(self, model: str = "gpt-5-codex"):
        if CodexAppServerClient is None:
            raise RuntimeError(
                "codex_sdk package not installed. Run `uv add codex-sdk` or fall back to file_queue."
            )
        self.model = model
        self._client: CodexAppServerClient | None = None

    def _session_binding_path(self, project_id: str, root: Path) -> Path:
        return root / "projects" / project_id / "session-binding.yaml"

    def _load_or_create_session(self, project_id: str, root: Path) -> str:
        path = self._session_binding_path(project_id, root)
        if path.exists():
            import yaml
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            sid = data.get("codex_session_id")
            if sid and self._client.is_session_alive(sid):
                return sid
        # 新建 session
        sid = self._client.start_session(
            cwd=str(root),
            model=self.model,
            system_prompt_path=str(root / "projects" / project_id / "context.md"),
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"codex_session_id: {sid}\nmodel: {self.model}\n", encoding="utf-8")
        return sid

    def send_command(self, project_id, *, kind, body, root):
        cmd_id = append_queue(project_id, kind=kind, body=body, via="api", root=root).id
        sid = self._load_or_create_session(project_id, root)
        self._client.send_user_message(
            session_id=sid,
            content=f"[queue:{cmd_id}] {kind}: {body}\n\n请读取 projects/{project_id}/context.md 与 queue.jsonl。",
        )
        return cmd_id

    def status(self, project_id, root):
        path = self._session_binding_path(project_id, root)
        if not path.exists():
            return AgentSessionStatus(
                backend=self.name, session_id=None, status="disabled",
                last_seen_at=None, queue_pending=len(unconsumed_queue(project_id, root)),
            )
        ...

    def stop(self, project_id, root):
        sid = self._load_or_create_session(project_id, root)
        self._client.cancel_session(sid)
```

> ⚠️ **实现备注**：`codex_sdk` 包的真实 API（v0.128+）由 OpenAI 提供。如果安装时发现 API 与上面草图不一致，请按官方 SDK 调整方法名，但保持 `AgentBackend` Protocol 不变。如果 SDK 包暂时无法用，可以先实现 `FileQueueAgentBackend` 单独跑通，CodexAgentBackend 留 stub 抛 NotImplementedError，Step 3 再激活。

**4.5.4 backend 选择策略**

`open_composer/config.py` 加：

```python
def agent_backend_name() -> str:
    """选择 agent backend。

    优先级：
    1. 环境变量 OPEN_COMPOSER_AGENT_BACKEND（codex_sdk | file_queue）
    2. spec.execution.backend 提示
    3. 默认 file_queue（永远可用）
    """
    explicit = os.getenv("OPEN_COMPOSER_AGENT_BACKEND", "").strip()
    if explicit in {"codex_sdk", "file_queue"}:
        return explicit
    return "file_queue"


def get_agent_backend() -> AgentBackend:
    name = agent_backend_name()
    if name == "codex_sdk":
        try:
            return CodexAgentBackend()
        except RuntimeError:
            return FileQueueAgentBackend()
    return FileQueueAgentBackend()
```

**4.5.5 CLI 加 `oc agent status / use / stop`**

```python
agent_app = typer.Typer(no_args_is_help=True)
app.add_typer(agent_app, name="agent")

@agent_app.command("status")
def agent_status_command(project_id: str) -> None:
    backend = get_agent_backend()
    status = backend.status(project_id, project_root())
    console.print(f"backend={status.backend} status={status.status} "
                  f"session={status.session_id} queue_pending={status.queue_pending}")

@agent_app.command("use")
def agent_use_command(
    backend: Annotated[str, typer.Option("--backend", help="codex_sdk | file_queue")]
) -> None:
    """切换默认 agent backend（写到 .env）。"""
    ...

@agent_app.command("stop")
def agent_stop_command(project_id: str) -> None:
    backend = get_agent_backend()
    backend.stop(project_id, project_root())
```

**4.5.6 `oc project continue` 接入 backend**

```python
@project_app.command("continue")
def project_continue_command(
    project_id: str,
    advice: ...,
    via_backend: bool = typer.Option(True, "--via-backend/--queue-only",
        help="True 时通过 AgentBackend 发送（如配置了 codex_sdk 会实时驱动）；False 仅 append queue。"),
    ...,
):
    result = continue_project(project_id, body=body, kind=kind, via="cli", root=project_root())
    if via_backend:
        backend = get_agent_backend()
        backend.send_command(project_id, kind=kind, body=body, root=project_root())
    ...
```

**Wave 2.5 验收**：

```bash
# fallback 路径（无 codex_sdk）
OPEN_COMPOSER_AGENT_BACKEND=file_queue uv run oc project continue foo --advice "test"
uv run oc agent status foo
# 输出 backend=file_queue queue_pending=N

# codex_sdk 路径（已安装 codex CLI + codex_sdk python pkg）
OPEN_COMPOSER_AGENT_BACKEND=codex_sdk uv run oc project continue foo --advice "test"
test -f projects/foo/session-binding.yaml
uv run oc agent status foo
# 输出 backend=codex_sdk session=... status=running|idle

uv run oc agent stop foo
```

---

### Wave 2.6 — 文档与样例

**4.6.1 新增 prompt 样例**

```text
prompts/
  README.md                      # 一页说明：什么是 prompt template / 怎么写 / 怎么 hash
  examples/
    news_regime_score.md
    sentiment_score.md
    macro_regime_score.md
```

**4.6.2 新增样例 spec**

```text
strategy_specs/drafts/qqq_news_regime_15m.yaml         # 用 llm_feature factor 的完整样例
strategy_specs/drafts/qqq_macro_regime_15m.yaml        # macro 因子样例
```

**4.6.3 更新 `docs/user-guide.md` 增加 LLM 因子段**

加一节"Working with LLM Factors"，含 materialize / promotion / fallback 行为说明。

**4.6.4 更新 `docs/product-golden-path-codex-quant-review-2026-05-13.zh.md`**

把"Golden Path"末段加入：

```text
Idea
  -> draft StrategySpec
  -> spec validation
  -> oc feature materialize <strategy>     # ← 新增（仅 llm_feature factor）
  -> oc strategy evidence <strategy>
  -> promotion-report + 4 pass
  -> paper readiness
  -> Alpaca Paper command gate
```

## 5. 验收清单（Wave 2.1 - 2.6 全部完成）

```text
[ ] research/control.py 的 1KB MAX_MEMORY_BYTES 已改为 32 * 1024
[ ] projects/{id}/context.md 编译器输出 ≤ 32KB / ≤ 128KB
[ ] projects/{id}/queue.jsonl / trace.jsonl 文件契约就位
[ ] reports/agent_requests/ 路径已删除；open_composer/agent_requests.py 已删除
[ ] FactorConfig 扩展支持 input_view / input_view_version / prompt_template_path / output_schema / cache_policy / model_ref
[ ] schemas/strategy_spec.schema.json 同步更新
[ ] schema validation：缺 input_view 等字段时报错
[ ] oc feature materialize 跑通：cache key 含 prompt_hash + input_view_version + schema_version
[ ] prompt 改后 cache miss；input_view_version 升后 cache miss；schema_version 升后 cache miss
[ ] reports/features/{strategy}/{factor}/{packets.jsonl, materialization-run.json, prompt-trial-ledger.jsonl} 三个文件均存在
[ ] backtest 严格只读 packets.jsonl，禁止 live LLM call（grep 检查 expressions.py 与 backtest_engine.py 不含 openai/anthropic 调用）
[ ] promotion 含 5 项 LLM 因子边际证据 check（quant_baseline / llm_variant / missing_modality / marginal_lift / independence）
[ ] llm_contribution_pass 字段语义正确（has llm_feature factor 时给 True/False；否则给 None）
[ ] open_composer/agent_backend/ 模块就位，含 file_queue + codex_sdk + base.py
[ ] oc agent status / use / stop 三命令可用
[ ] oc project continue 接入 backend 选择
[ ] 三个样例 spec + prompt 模板入仓
[ ] user-guide.md / golden-path.md 更新
[ ] uv run pytest 全绿
[ ] uv run oc repo check --strict 通过
[ ] make verify 通过
```

## 6. 不做什么（Step 2 边界）

```text
✗ 不引入 Python Strategy Module（违反 AST 安全白名单；与 file-first 哲学冲突）
✗ 不引入 strategy_kind / llm_factors 并行字段（用 FactorConfig 扩展）
✗ 不引入 session.yaml / checkpoint.md 独立文件（project.yaml + context.md 已覆盖）
✗ 不改 4 个 pass 语义
✗ 不改 harness 规则
✗ 不删 paper safety chain
✗ 不允许 backtest loop 中 live LLM call
✗ 不改 Dashboard UI（留给 Step 3）
✗ 不接入除 Codex 外的 SDK（先做 Codex；Claude Code SDK 视 Step 3 需求再加）
```

## 7. 风险与对冲

| 风险 | 对冲 |
|---|---|
| codex_sdk python 包 API 与文档草图不一致 | 实现时按官方 SDK 调整方法名，保持 `AgentBackend` Protocol 不变；先做 file_queue，codex_sdk 留 stub |
| prompt template 改但 prompt_hash 不变（用户忘了 bump） | 自动 hash prompt 文件原文（不要求用户手动 bump）；改文件就改 hash |
| schema_version 全局升级时所有 packets 失效 | 提供 `oc feature materialize --refresh` 一键重算 |
| LLM 调用失败导致 materialize 中断 | 每行 packet 独立，错误写入 `prompt-trial-ledger.jsonl` 的 error 字段；可断点续跑 |
| backtest 仍意外调 live LLM | repo check 加新 check：grep `import openai` / `import anthropic` 不应出现在 engines/expressions.py |
| context.md 32KB 仍不够 agent 用 | 上限 128KB；超大策略用 `--max-context-bytes` 参数；agent 自己按需 read 文件路径索引 |
| Codex session 失联（process crash / ~/.codex/sessions 损坏） | session-binding.yaml 记录 session_id；is_session_alive 失败时自动新建 session 并把 context.md 重新 inject |
| 用户改 spec 但忘了 re-materialize | promotion gate 检查 packet 的 input_view_version / prompt_hash 与 spec 当前是否一致；不一致 → blocked |

## 8. 回滚预案

每个 Wave 单独 PR。Wave 2.1 / 2.2 / 2.3 是必做基础；Wave 2.5（Codex SDK）出问题时单独 revert，不影响 2.1 / 2.2 / 2.3（file_queue 仍工作）。

## 9. 完成定义

执行完 Wave 2.1 - 2.6 后：

- 用户在 Dashboard 或 CLI 触发"继续优化"时，agent 拿到的 context 是 32KB 完整摘要而非 1KB 缩略
- LLM/news/event/macro 因子从"声明 + 合规检查"升级到"设计 → 物化 → 回放 → 边际证明"完整闭环
- 用户可以选择 `OPEN_COMPOSER_AGENT_BACKEND=codex_sdk` 让产品实时驱动 Codex session，也可以保留 `file_queue` 让 agent 自驱
- 任何 agent 操作都通过 `trace.jsonl` 落盘审计
- `agent_requests/` 这一不一致路径完全消失

完成后即可进入 Step 3（Dashboard-first 全交互）。
