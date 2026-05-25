# Open Composer Step 4：LLM 因子闭环补完与 Dashboard 体验抛光

日期：2026-05-25
执行者：Codex / Claude Code
前置：Step 1（简化与重构）+ Step 2（worksession + LLM factor + Codex SDK）+ Step 3（Dashboard-first）均完成
后续：无（路线图收尾的局部修复）

## 0. 一句话目标

修补 Step 1-3 完成后审计发现的 9 处缺口：让 LLM 因子物化能跑完整历史（而非最近 16 根 bar），让 Activity 时间线汇总 agent 轨迹，让 LLM Factors tab 可以在 Dashboard 编辑 prompt 模板，让 Factor IC 图表展示真实数据，加 onboarding、tooltip、SSE 优化、Codex SDK 真实回归测试和 paper PnL 实时刷新。**不引入新概念，仅补全已有功能的实际可用性。**

## 1. 背景（无上下文也能看懂）

Open Composer 是个人 AI 量化策略工作台，源头是 `StrategySpec`（YAML），CLI 入口是 `oc`，agent 是 Codex / Claude Code。

Step 1-3 完成后产品具备：

- `projects/{id}/{project.yaml, context.md, queue.jsonl, trace.jsonl, runs/round-XXX.yaml, session-binding.yaml}` 文件契约
- `FactorConfig.source = llm_feature` 含 `input_view / input_view_version / prompt_template_path / output_schema / cache_policy / model_ref`
- `oc feature materialize` 跑 LLM 因子 PIT 物化（cache key = `symbol + visible_at + input_view_version + input_hash + prompt_hash + model + schema_version="2"`）
- `expressions.py:_load_feature_packet` 严格按 visible_at 做 PIT 回放，禁止 backtest loop 中 live LLM call
- `promotion.py:_llm_marginal_lift_checks` 跑 quant_baseline / variant / missing_modality 3 套 backtest，输出 5 项边际证据 check
- `open_composer/agent_backend/` 含 `FileQueueAgentBackend`（保底）+ `CodexAgentBackend`（基于 codex app-server JSON-RPC 持久 session）
- Dashboard 30+ API 端点 + Strategy Detail 7 tabs（Overview / Conversation / Spec / Runs / Promotion / Paper / LLM Factors / Trace） + sticky 4-Pass status bar + SSE trace stream
- `test_dashboard_cli_parity.py` 严格校验 14 个 Dashboard POST 动作都有 CLI 对偶

但审计发现 9 处实际可用性缺口，按优先级：

| 类别 | 编号 | 严重度 | 问题摘要 |
|---|---|---|---|
| LLM 因子 | C.1 | P0 | `_input_rows` 只物化 `frame.tail(16)`，promotion OOS/walk-forward 永远拿不到 LLM packet |
| Activity | C.2 | P0 | `ActivityView` 没合并 `projects/*/trace.jsonl`，看不到跨 project agent 工作 |
| LLM 因子 | C.3 | P1 | LLM Factors tab 没"Edit Prompt"按钮，改 prompt 必须开终端 |
| LLM 因子 | C.4 | P1 | Factor IC sparkline 用占位 `0.02`，没读 factor_lab.json |
| 体验 | D.1 | P2 | Overview 没 first-run onboarding hero |
| 体验 | D.2 | P2 | 4-Pass badge 没 hover tooltip 显示 blocked reasons |
| 工程 | D.3 | P2 | `CodexAgentBackend` 假设 `codex_sdk` 包 API，缺真实回归 |
| 工程 | D.3.5 | P2 | SSE `ticks=30` 默认 30 秒断流，前端频繁重连 |
| 体验 | D.4 | P2 | `LiveView` 的 paper PnL 用静态 data，没实时拉 `/api/paper/positions` |

修补这些项后，"专业地生成和优化迭代最佳策略"的目标完整实现。

## 2. 目标 / 非目标

### 目标

1. LLM 因子物化默认覆盖**全历史**（可选 `--window-bars` 缩小），让 promotion 的 OOS / walk-forward / marginal lift 有真实 LLM packet 支撑。
2. Activity 时间线汇总跨 project 的 `trace.jsonl`，与 signals / paper orders / reviews / audits 并列。
3. LLM Factors tab 提供 inline prompt 编辑器（写文件 + 写 trace + 显式提示需要 re-materialize）。
4. Factor IC chart 展示 `reports/research/{name}-factor-lab.json` 的真实 `rank_ic / rolling_rank_ic_mean / rolling_rank_ic_min`。
5. Overview 首次启动（无 project + 无 active 策略 + 无 run）显示 onboarding hero 三个引导动作。
6. 4-Pass badge hover 显示 blocked / warning check 名字与 message。
7. `CodexAgentBackend` 增加 integration test，验证真实 `codex_sdk` 包接口；提供失败时清晰错误信息。
8. SSE 默认 `ticks=300`（5 分钟），降低重连频率。
9. `LiveView` 改为定时（30s）从 `/api/paper/positions` + `/api/paper/orders` + `/api/paper/alerts` 拉取实时数据。

### 非目标（明确不做）

- 不引入新策略类型 / 新 schema 字段 / 新 agent backend。
- 不改 4 个 pass 语义 / harness 规则 / paper safety chain。
- 不改 backtest engine 与 expressions 安全白名单。
- 不让 backtest loop 调 live LLM（C.1 修复后仍只读已物化 packet）。
- 不重写前端框架（仍 React 18 + Vite + Tailwind + recharts）。
- 不引入 WebSocket（SSE 已够用）。
- 不引入新依赖（仅可能加 `codex_sdk` 已计划的可选依赖）。
- 不删除现有功能。

## 3. 当前状态扫描（关键文件 + 行号）

```text
open_composer/research/llm_materialize.py
  L42:  materialize_factor(spec_path, factor_name, *, root, backend, refresh, symbols)
  L222: def _input_rows(frame, symbol)
  L226: for raw in frame.tail(16).to_dict(orient="records"):     ← C.1 修复点

open_composer/dashboard/server.py
  L424:  ticks = _query_int(query, "ticks", default=30, ...)     ← D.3.5 修复点
  L1004: def build_strategy_detail_payload(root, strategy_name)
  L1054: "llm_factors": _llm_factor_rows(root, resolved_name)
  L1685: def _llm_factor_rows(root, strategy_name)
  L1704: "prompt_preview": _read_text(prompt_path, max_bytes=1200)
                                                                 ← C.4 在这里补 rank_ic 字段

open_composer/research/factor_lab.py
  L30:  rank_ic: float | None
  L31:  rolling_rank_ic_mean: float | None
  L32:  rolling_rank_ic_min: float | None
  L47:  factor_metrics: list[FactorLabFactorMetric]

dashboard/src/app/components/strategy-detail.tsx
  L577-611: LLMFactorsTab                                        ← C.3 + C.4 修复点
  L605: <FactorICChart data={[{ name: "IC", value: factor.packet_count ? 0.02 : 0 }]} />
  L636-644: PassBadge                                            ← D.2 修复点

dashboard/src/app/components/charts/factor-ic.tsx
  L3-21: FactorICChart 接收 {name, value}[]                       ← C.4 扩展 data shape

dashboard/src/app/components/overview.tsx
  L14-26: Overview 计算 highlightedStrategies                    ← D.1 在顶部增加 first-run 分支

dashboard/src/app/components/sections.tsx
  L70-95: ActivityView timeline 合并 signals / orders / events
                                                                 ← C.2 在 useMemo 里加 trace 行

dashboard/src/app/components/live.tsx
  L17:  export function LiveView()
  L18:  const activePaperProjects = projects.filter(...)         ← D.4 改为 useEffect 30s 轮询

open_composer/agent_backend/codex_sdk.py
  L14-16: from codex_sdk import CodexAppServerClient (optional)
  L19:  class CodexAgentBackend                                   ← D.3 加 integration test
  L92:  def _load_or_create_session(...)

tests/
  test_llm_materialize.py        # C.1 加新 test
  test_dashboard_server.py       # C.2/C.3/C.4 加新 test
  test_codex_sdk_backend.py      # D.3 新增（可标 @pytest.mark.slow）
```

## 4. 改动清单（按 Wave 分批；每个 Wave 单独可 PR）

### Wave 4.1 — P0 关键缺口（**先修，最大 ROI**）

#### 4.1.1 [C.1] LLM 因子物化覆盖全历史

**问题**：`_input_rows` 只取 `frame.tail(16)`，意味着 promotion 跑 OOS / walk-forward 时绝大部分历史 bar 没有 LLM packet，`_load_feature_packet` 回退到 `default=0.0`，导致 `llm_quant_baseline / llm_variant / llm_marginal_lift / llm_independence` 全部退化为同一条曲线，`llm_contribution_pass` 实际无意义。

**文件**：`open_composer/research/llm_materialize.py`

**改动**：

```python
# L42 函数签名加 window_bars 参数
def materialize_factor(
    spec_path: Path,
    factor_name: str,
    *,
    root: Path | None = None,
    backend: str = "openai",
    refresh: bool = False,
    symbols: list[str] | None = None,
    window_bars: int | None = None,   # ✦ 新增：None 表示全历史
) -> MaterializationResult:
    ...
    for symbol in target_symbols:
        frame = _load_symbol_frame(spec, base, symbol, refresh=refresh)
        rows = _input_rows(frame, symbol, window_bars=window_bars)   # ✦ 传入
        ...

# L222 函数签名加 window_bars
def _input_rows(
    frame, symbol: str, *, window_bars: int | None = None
) -> list[dict[str, Any]]:
    if "timestamp" not in frame.columns:
        raise ValueError("materialization requires timestamp column")
    target = frame if window_bars is None else frame.tail(int(window_bars))
    rows: list[dict[str, Any]] = []
    for raw in target.to_dict(orient="records"):
        timestamp = _timestamp(raw["timestamp"])
        rows.append(
            {
                "symbol": symbol,
                "timestamp": timestamp,
                "visible_at": timestamp,
                "ohlcv": {
                    key: raw.get(key)
                    for key in ("open", "high", "low", "close", "volume")
                    if key in raw
                },
            }
        )
    return rows
```

**CLI**：`open_composer/cli.py` 的 `feature_materialize_command`（约 L712）加参数：

```python
@feature_app.command("materialize")
def feature_materialize_command(
    spec: Path,
    factor: ... = None,
    symbols: ... = None,
    backend: ... = "openai",
    refresh: ... = False,
    window_bars: Annotated[
        int | None,
        typer.Option(
            "--window-bars",
            help="Limit to last N bars. Omit (default) to materialize the full history.",
        ),
    ] = None,
) -> None:
    ...
    for name in targets:
        result = materialize_factor(
            spec, name,
            root=root, backend=backend, refresh=refresh,
            symbols=selected_symbols,
            window_bars=window_bars,    # ✦ 传入
        )
        ...
```

**Dashboard API**：`open_composer/dashboard/server.py` 的 `build_strategy_action_payload`（处理 `action="materialize"`）读取 `payload.get("window_bars")` 并透传到 backend `kind="materialize"` 命令的 metadata，由消费 queue 的 agent / CLI 决定如何使用（推荐方案：将 `window_bars` 一并写入 `queue.jsonl` 的 `metadata.window_bars`，agent / CLI 在调 `oc feature materialize` 时把它转成 `--window-bars`）。

**前端**：`dashboard/src/app/components/strategy-detail.tsx` 的 `LLMFactorsTab`（约 L577）`Materialize` 按钮旁加一个 select："Last 16 / Last 200 / Last 1000 / Full history"，对应 `window_bars` 取值。Strategy Detail 顶部的 [Materialize] 按钮（约 L225）默认走"Full history"（即 `window_bars=null`）。

**测试**：`tests/test_llm_materialize.py` 新增：

```python
def test_materialize_full_history_by_default(tmp_path, ...):
    # 用 local_test_stub backend；准备 30 根 bar 的样本数据
    # 调 materialize_factor(spec, "factor_name") 不传 window_bars
    # 断言 packets.jsonl 行数 == 30（覆盖所有历史 bar）

def test_materialize_window_bars_limits_rows(tmp_path, ...):
    # 调 materialize_factor(..., window_bars=10)
    # 断言 packets.jsonl 行数 == 10（仅最后 10 根）

def test_materialize_default_is_not_tail_16(tmp_path, ...):
    # 30 根 bar；不传 window_bars
    # 断言行数 != 16，且 >= 30
```

#### 4.1.2 [C.2] Activity 合并 trace.jsonl

**问题**：`ActivityView` 的 `timeline`（`sections.tsx` 约 L20-95）仅汇总 `recentSignals / paperOrders / events / llmReviews / auditLog`，不含跨 project 的 agent `trace.jsonl`。用户在 Activity 看不到 agent 上周做了什么。

**Backend**：`open_composer/dashboard/server.py` 新增端点：

```python
# do_GET 路由表（约 L141 附近）加：
if path == "/api/activity/trace":
    self._handle_json_result(build_activity_trace_payload, parsed.query)
    return

# 新函数（建议放在文件靠后位置）：
def build_activity_trace_payload(root: Path, query: str) -> dict[str, Any]:
    """聚合所有 projects/*/trace.jsonl 的最近 N 条。

    Query params:
      limit: int (default 200, max 2000)
      project: str (optional filter)
      since_ts: ISO timestamp (optional filter)
      kind: str (optional, matches metadata.via or agent)
    """
    values = parse_qs(query)
    limit = _query_int(query, "limit", default=200, minimum=1, maximum=2000)
    project_filter = (values.get("project", [""])[0] or "").strip()
    since_ts = (values.get("since_ts", [""])[0] or "").strip()
    kind_filter = (values.get("kind", [""])[0] or "").strip()

    rows: list[dict[str, Any]] = []
    projects_dir = root / "projects"
    if projects_dir.exists():
        for project_dir in sorted(projects_dir.iterdir()):
            if not project_dir.is_dir():
                continue
            if project_filter and project_dir.name != project_filter:
                continue
            trace_file = project_dir / "trace.jsonl"
            if not trace_file.exists():
                continue
            for raw in _read_jsonl_rows(trace_file):
                ts = str(raw.get("ts") or "")
                if since_ts and ts <= since_ts:
                    continue
                if kind_filter and kind_filter not in {
                    str(raw.get("agent") or ""),
                    str((raw.get("metadata") or {}).get("via") or ""),
                }:
                    continue
                rows.append(
                    {
                        "project_id": project_dir.name,
                        "ts": ts,
                        "span_id": raw.get("span_id"),
                        "agent": raw.get("agent"),
                        "operation": raw.get("operation"),
                        "queue_command_id": raw.get("queue_command_id"),
                        "metadata": raw.get("metadata") or {},
                    }
                )
    rows.sort(key=lambda row: row["ts"], reverse=True)
    return {
        "schema_version": 1,
        "generated_at": _now_iso(),
        "limit": limit,
        "entries": rows[:limit],
        "total": len(rows),
    }
```

**前端**：`dashboard/src/app/components/sections.tsx` 的 `ActivityView`：

```tsx
// 新增 state 与 fetch
const [traceRows, setTraceRows] = useState<Array<Record<string, any>>>([]);
useEffect(() => {
  void getDashboardJson<{ entries: Array<Record<string, any>> }>(
    "/api/activity/trace?limit=200",
  )
    .then((payload) => setTraceRows(payload.entries))
    .catch(() => setTraceRows([]));
}, []);

// timeline useMemo 里追加 trace 行：
...traceRows.map((row) => ({
  id: `trace-${row.span_id ?? row.ts}`,
  time: row.ts,
  kind: "Trace",
  project: row.project_id,
  title: row.operation,
  detail: `${row.agent}${row.queue_command_id ? ` · ${row.queue_command_id}` : ""}`,
  color: traceColor(row.agent),
})),

// 增加 traceColor 工具：
function traceColor(agent: string): "green" | "cyan" | "purple" | "black" | "orange" {
  if (agent === "codex") return "green";
  if (agent === "claude_code") return "purple";
  if (agent === "dashboard") return "cyan";
  if (agent === "cli") return "black";
  return "orange";
}
```

**测试**：`tests/test_dashboard_server.py` 新增：

```python
def test_build_activity_trace_payload_aggregates_projects(tmp_path):
    # 创建 projects/a/trace.jsonl + projects/b/trace.jsonl 各 3 行
    # 调 build_activity_trace_payload(tmp_path, "limit=10")
    # 断言 entries 长度 = 6，按 ts desc 排序

def test_activity_trace_filters_by_project(tmp_path):
    # 调 build_activity_trace_payload(tmp_path, "limit=10&project=a")
    # 断言 entries 只含 a 的 3 行
```

**Wave 4.1 验收**：

```bash
.venv/bin/pytest tests/test_llm_materialize.py tests/test_dashboard_server.py -q
.venv/bin/oc feature materialize strategy_specs/drafts/<llm-strategy>.yaml \
    --backend local_test_stub --refresh
# 输出 packets 数与历史 bar 数一致（远大于 16）

curl http://127.0.0.1:8000/api/activity/trace?limit=20
# 返回所有 projects 的 trace 合并列表
.venv/bin/pytest tests/ -q   # 全绿
.venv/bin/oc repo check --strict
make verify
```

---

### Wave 4.2 — P1 LLM 因子 UX 完整化

#### 4.2.1 [C.3] LLM Factors tab 加 Edit Prompt 按钮

**问题**：当前 `LLMFactorsTab` 只显示 prompt 预览（约 L602）+ Materialize 按钮。用户要改 prompt 必须开终端编辑文件。

**Backend**：`open_composer/dashboard/server.py` 新增端点：

```python
# do_GET 路由（projects/strategies 路由块之间，约 L226 附近）：
if path.startswith("/api/strategies/"):
    parts = _api_parts(path)
    ...
    if len(parts) == 5 and parts[2] == "llm-factors" and parts[4] == "prompt":
        self._handle_json_result(
            build_strategy_llm_factor_prompt_payload, parts[1], parts[3]
        )
        return

# do_POST 路由（strategies 路由块，约 L264 附近）：
if path.startswith("/api/strategies/"):
    parts = _api_parts(path)
    ...
    if len(parts) == 5 and parts[2] == "llm-factors" and parts[4] == "prompt":
        self._handle_strategy_llm_factor_prompt(parts[1], parts[3], payload)
        return

# 处理器：
def _handle_strategy_llm_factor_prompt(
    self, strategy_name: str, factor_name: str, payload: dict[str, Any]
) -> None:
    try:
        self._send_json(
            build_strategy_llm_factor_prompt_update_payload(
                self.dashboard_root, strategy_name, factor_name, payload
            )
        )
    except (ValueError, FileNotFoundError) as exc:
        self._send_json({"error": str(exc)}, status=400)

# 构建函数：
def build_strategy_llm_factor_prompt_payload(
    root: Path, strategy_name: str, factor_name: str
) -> dict[str, Any]:
    """GET: 返回当前 prompt 全文 + hash + 关联 factor 元数据。"""
    spec_path = resolve_strategy_path(strategy_name, root)
    spec = load_strategy_spec(spec_path)
    factor = spec.factors.get(factor_name)
    if factor is None or factor.source != "llm_feature":
        raise ValueError(f"llm_feature factor not found: {factor_name}")
    if not factor.prompt_template_path:
        raise ValueError(f"factor {factor_name} has no prompt_template_path")
    prompt_path = root / factor.prompt_template_path
    text = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else ""
    import hashlib
    prompt_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return {
        "strategy_name": strategy_name,
        "factor_name": factor_name,
        "prompt_template_path": factor.prompt_template_path,
        "text": text,
        "prompt_hash": prompt_hash,
        "input_view": factor.input_view,
        "input_view_version": factor.input_view_version,
        "model_ref": factor.model_ref,
    }


def build_strategy_llm_factor_prompt_update_payload(
    root: Path, strategy_name: str, factor_name: str, payload: dict[str, Any]
) -> dict[str, Any]:
    """POST: 写新 prompt 全文 → 文件 + 写 trace + 提示需要 re-materialize。"""
    spec_path = resolve_strategy_path(strategy_name, root)
    spec = load_strategy_spec(spec_path)
    factor = spec.factors.get(factor_name)
    if factor is None or factor.source != "llm_feature":
        raise ValueError(f"llm_feature factor not found: {factor_name}")
    if not factor.prompt_template_path:
        raise ValueError(f"factor {factor_name} has no prompt_template_path")
    text = str(payload.get("text") or "").rstrip() + "\n"
    if not text.strip():
        raise ValueError("prompt text is empty")
    prompt_path = root / factor.prompt_template_path
    ensure_dir(prompt_path.parent)
    prompt_path.write_text(text, encoding="utf-8")
    import hashlib
    new_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()

    # 写 trace（不强制写 queue，避免误触全历史重算）
    project_id = _resolve_project_for_strategy(strategy_name, root)
    if project_id:
        append_trace(
            project_id,
            agent="dashboard",
            operation="dashboard_edit_llm_factor_prompt",
            metadata={
                "via": "dashboard",
                "factor_name": factor_name,
                "prompt_template_path": factor.prompt_template_path,
                "new_prompt_hash": new_hash,
            },
            root=root,
        )
    return {
        "status": "saved",
        "prompt_template_path": factor.prompt_template_path,
        "new_prompt_hash": new_hash,
        "needs_rematerialize": True,
        "next_action": (
            f"Run `oc feature materialize <spec> --factor {factor_name} --refresh` "
            "or click [Materialize] (Full history) to recompute packets."
        ),
    }
```

**前端**：`dashboard/src/app/components/strategy-detail.tsx` 的 `LLMFactorsTab`（约 L577）：

```tsx
function LLMFactorsTab({
  strategyName,
  factors,
  onMaterialize,
}: {
  strategyName: string;
  factors: Array<Record<string, any>>;
  onMaterialize: (factor: string, windowBars: number | null) => void;
}) {
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [draftHash, setDraftHash] = useState("");
  const [savedNotice, setSavedNotice] = useState<string | null>(null);

  const openEditor = async (factor: string) => {
    setEditing(factor);
    const payload = await getDashboardJson<{ text: string; prompt_hash: string }>(
      `/api/strategies/${strategyName}/llm-factors/${factor}/prompt`,
    );
    setDraft(payload.text);
    setDraftHash(payload.prompt_hash);
  };

  const save = async () => {
    if (!editing) return;
    const result = await postDashboardJson<Record<string, any>>(
      `/api/strategies/${strategyName}/llm-factors/${editing}/prompt`,
      { text: draft },
    );
    setSavedNotice(
      `Saved (new hash ${String(result.new_prompt_hash).slice(0, 10)}…). ${
        result.next_action
      }`,
    );
  };

  return (
    <div className="grid grid-cols-12 gap-3">
      {/* 已有的 factors.map(...) 渲染，每个 card 加 [Edit prompt] 按钮：*/}
      {factors.map((factor) => (
        <Card key={factor.name} className="col-span-6">
          <SectionTitle tick="purple" action={
            <div className="flex gap-2">
              <button className="pill pill-secondary" onClick={() => void openEditor(factor.name)}>
                Edit prompt
              </button>
              <button className="pill pill-secondary" onClick={() => onMaterialize(factor.name, null)}>
                <RefreshCw size={13} /> Materialize
              </button>
            </div>
          }>
            {factor.name}
          </SectionTitle>
          {/* ... 原有 KPI / FactorICChart / preview ... */}
        </Card>
      ))}

      {editing && (
        <Card className="col-span-12">
          <SectionTitle tick="orange" hint={savedNotice ?? "Editing prompt template"}>
            Editing: {editing}
          </SectionTitle>
          <textarea
            className="ds-input mt-4 w-full min-h-[280px] px-3 py-2 t-body-sm"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
          />
          <div className="mt-3 flex gap-2 items-center">
            <span className="t-body-xs ink-subtle">Current hash: {draftHash.slice(0, 10)}…</span>
            <div className="ml-auto flex gap-2">
              <button className="pill pill-secondary" onClick={() => setEditing(null)}>Close</button>
              <button className="pill pill-primary" onClick={() => void save()}>Save</button>
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}
```

调用方（`StrategyDetail` 内部）：

```tsx
{tab === "llm" && (
  <LLMFactorsTab
    strategyName={strategyId}
    factors={data?.llm_factors ?? []}
    onMaterialize={(factor, windowBars) =>
      void runAction("materialize", { factor, window_bars: windowBars })
    }
  />
)}
```

**测试**：`tests/test_dashboard_server.py` 新增：

```python
def test_get_llm_factor_prompt_returns_text(tmp_path):
    # 准备 spec + prompts/foo.md
    # 调 build_strategy_llm_factor_prompt_payload
    # 断言 text 包含 prompt 文件内容，prompt_hash 长度=64

def test_post_llm_factor_prompt_writes_file(tmp_path):
    # 调 build_strategy_llm_factor_prompt_update_payload(..., {"text": "new prompt"})
    # 断言 prompts/foo.md 已写入，trace.jsonl 多一行 dashboard_edit_llm_factor_prompt
    # 断言返回 needs_rematerialize=True
```

#### 4.2.2 [C.4] Factor IC chart 用真实数据

**问题**：`LLMFactorsTab` 渲染时 `<FactorICChart data={[{ name: "IC", value: factor.packet_count ? 0.02 : 0 }]} />` 是占位。

**Backend**：`open_composer/dashboard/server.py:_llm_factor_rows`（L1685-1711）补 `factor_lab` 字段：

```python
def _llm_factor_rows(root: Path, strategy_name: str) -> list[dict[str, Any]]:
    try:
        spec_path = resolve_strategy_path(strategy_name, root)
        spec = load_strategy_spec(spec_path)
    except (FileNotFoundError, ValueError):
        return []

    # 读 factor_lab JSON（如果存在）
    factor_lab_path = root / "reports" / "research" / f"{spec.name}-factor-lab.json"
    factor_lab_metrics: dict[str, dict[str, Any]] = {}
    if factor_lab_path.exists():
        try:
            import json
            raw = json.loads(factor_lab_path.read_text(encoding="utf-8"))
            for metric in raw.get("factor_metrics") or []:
                if isinstance(metric, dict) and metric.get("name"):
                    factor_lab_metrics[str(metric["name"])] = metric
        except (OSError, json.JSONDecodeError):
            factor_lab_metrics = {}

    rows: list[dict[str, Any]] = []
    for name, factor in spec.factors.items():
        if factor.source != "llm_feature":
            continue
        packet_path = root / factor.path if factor.path else None
        prompt_path = root / factor.prompt_template_path if factor.prompt_template_path else None
        metric = factor_lab_metrics.get(name) or {}
        rows.append(
            {
                "name": name,
                "field": factor.field,
                "path": factor.path,
                "packet_count": len(_read_jsonl_rows(packet_path)) if packet_path else 0,
                "prompt_template_path": factor.prompt_template_path,
                "prompt_preview": _read_text(prompt_path, max_bytes=1200) if prompt_path else "",
                "input_view": factor.input_view,
                "input_view_version": factor.input_view_version,
                "model_ref": factor.model_ref,
                "point_in_time_ready": bool(packet_path and packet_path.exists()),
                # ✦ 新增 factor_lab 真实指标
                "rank_ic": metric.get("rank_ic"),
                "rolling_rank_ic_mean": metric.get("rolling_rank_ic_mean"),
                "rolling_rank_ic_min": metric.get("rolling_rank_ic_min"),
                "coverage_pct": metric.get("coverage_pct"),
                "stability_score": metric.get("stability_score"),
                "top_bottom_spread_pct": metric.get("top_bottom_spread_pct"),
            }
        )
    return rows
```

**前端图表**：`dashboard/src/app/components/charts/factor-ic.tsx` 扩展支持多 bar：

```tsx
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

export function FactorICChart({
  data,
}: {
  data: Array<{ name: string; value: number | null | undefined }>;
}) {
  const rows = (data.length > 0 ? data : [{ name: "n/a", value: 0 }]).map((row) => ({
    name: row.name,
    value: Number.isFinite(Number(row.value)) ? Number(row.value) : 0,
  }));
  return (
    <div className="h-[128px] w-full min-w-0">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
          <XAxis dataKey="name" tick={{ fontSize: 10 }} />
          <YAxis tick={{ fontSize: 10 }} width={36} />
          <Tooltip formatter={(value) => Number(value).toFixed(3)} />
          <Bar dataKey="value" fill="#1AC8E8" isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
```

**LLMFactorsTab 卡片内部** 把固定 `0.02` 替换为：

```tsx
<div className="mt-3">
  <FactorICChart
    data={[
      { name: "rank IC", value: factor.rank_ic },
      { name: "rolling mean", value: factor.rolling_rank_ic_mean },
      { name: "rolling min", value: factor.rolling_rank_ic_min },
    ]}
  />
</div>
```

KPI 区也补一组：

```tsx
<div className="mt-4 grid grid-cols-3 gap-2">
  <KPI label="Packets" value={String(factor.packet_count ?? 0)} accent={factor.point_in_time_ready ? "green" : "orange"} />
  <KPI label="Input view" value={String(factor.input_view_version ?? "n/a")} accent="cyan" />
  <KPI label="Rank IC" value={formatNumber(factor.rank_ic)} accent="purple" />
</div>
```

**测试**：`tests/test_dashboard_server.py` 新增：

```python
def test_llm_factor_rows_attaches_factor_lab(tmp_path):
    # 准备 spec + reports/research/foo-factor-lab.json（含 factor_metrics）
    # 调 _llm_factor_rows(tmp_path, "foo")
    # 断言返回行含 rank_ic / rolling_rank_ic_mean / rolling_rank_ic_min
```

**Wave 4.2 验收**：

```bash
.venv/bin/pytest tests/test_dashboard_server.py -q   # 全绿
make dashboard-build
# 浏览器打开 dashboard，LLM Factors tab：
#   - 每个 factor 卡片有 [Edit prompt] 按钮，点击弹编辑器
#   - 保存后右上角出现 hash 与 "needs re-materialize" 提示
#   - FactorICChart 显示 3 个真实指标条（rank IC / rolling mean / rolling min）
.venv/bin/pytest tests/test_dashboard_cli_parity.py -q
# 加入 POST /api/strategies/{name}/llm-factors/{factor}/prompt → "(dashboard-only spec edit; mirrored by editing the prompt file)"
.venv/bin/oc repo check --strict
make verify
```

更新 `tests/test_dashboard_cli_parity.py` 的 `DASHBOARD_ACTIONS`：

```python
DASHBOARD_ACTIONS = {
    ...,
    "POST /api/strategies/{name}/llm-factors/{factor}/prompt":
        "(file edit only: prompts/<factor>.md)",
}
```

并相应在 `DASHBOARD_CLI_PARITY`（`open_composer/dashboard/server.py` 中的常量）同步加入此条。

---

### Wave 4.3 — P2 体验抛光

#### 4.3.1 [D.1] Overview 首次使用 Onboarding Hero

**问题**：干净仓库打开 Dashboard 直接看到一个空 catalog，没有引导。

**前端**：`dashboard/src/app/components/overview.tsx` 在 `Overview()` 函数顶部加 first-run 判断：

```tsx
import { Sparkles, Wand2, Upload } from "lucide-react";   // 增加图标

export function Overview() {
  const activeStrategies = strategies.filter((s) => s.status === "active");
  // ★ 新增：首次启动判断
  const isFirstRun =
    strategies.length === 0 &&
    (dashboardSummary.projectCount ?? 0) === 0 &&
    (dashboardSummary.runCount ?? 0) === 0;

  if (isFirstRun) {
    return <OnboardingHero />;
  }
  // ... 原有 Overview 渲染 ...
}

function OnboardingHero() {
  return (
    <div className="px-6 pb-8 space-y-3">
      <Hero
        theme="green"
        greeting="Welcome"
        headline="Open Composer"
        meta="Three ways to start: try the sample, build from your idea, or import an existing spec."
        stat={{ label: "Setup", value: "0/3 strategies", delta: "First-run guide" }}
      />
      <div className="grid grid-cols-3 gap-3">
        <Card>
          <SectionTitle tick="green">Try sample strategy</SectionTitle>
          <p className="t-body-sm ink-subtle mt-3">
            qqq_pullback_15m runs on bundled sample data. No credentials required.
          </p>
          <button
            className="pill pill-primary mt-4"
            onClick={() => void seedSampleStrategy()}
          >
            <Sparkles size={13} /> Try sample
          </button>
        </Card>
        <Card>
          <SectionTitle tick="cyan">Build from your idea</SectionTitle>
          <p className="t-body-sm ink-subtle mt-3">
            Describe a strategy in natural language. The agent drafts the StrategySpec.
          </p>
          <button
            className="pill pill-primary mt-4"
            onClick={() => (window.location.hash = "#build")}
          >
            <Wand2 size={13} /> Build new
          </button>
        </Card>
        <Card>
          <SectionTitle tick="orange">Import existing spec</SectionTitle>
          <p className="t-body-sm ink-subtle mt-3">
            Upload a YAML strategy file. It will be registered as a draft.
          </p>
          <button className="pill pill-secondary mt-4" disabled>
            <Upload size={13} /> Import (coming soon)
          </button>
        </Card>
      </div>
    </div>
  );
}

async function seedSampleStrategy() {
  // 调 POST /api/build/draft，body 用样例（template_id="memory_storage_momentum_15m" 或 "qqq_pullback_15m"）
  await postDashboardJson("/api/build/draft", {
    name: "Try qqq pullback 15m",
    thesis: "Sample strategy for first-run smoke test.",
    idea: "Use the bundled qqq_pullback_15m template to validate the local setup.",
    strategy_kind: "pure_quant",
    template_id: "qqq_pullback_15m",
    use_llm: false,
    max_rounds: 3,
  });
  // 刷新 catalog
  const catalog = await getDashboardJson<Parameters<typeof applyDashboardCatalog>[0]>(
    "/api/dashboard/catalog",
  );
  applyDashboardCatalog(catalog);
}
```

注意 `App.tsx` 当前用 `tab` state（不是 hash 路由），所以 `window.location.hash = "#build"` 不会工作。改用 callback：

```tsx
// Overview 接受 onNavigate prop
export function Overview({ onNavigate }: { onNavigate?: (tab: string) => void }) {
  ...
  if (isFirstRun) return <OnboardingHero onNavigate={onNavigate} />;
  ...
}

// OnboardingHero 用 onNavigate
<button onClick={() => onNavigate?.("build")}>Build new</button>

// App.tsx 传：
{tab === "overview" && <Overview onNavigate={handleNav} />}
```

**测试**：手测即可（first-run 状态需要清仓库）。

#### 4.3.2 [D.2] 4-Pass Badge Tooltip

**问题**：`PassBadge`（`strategy-detail.tsx` 约 L636-644）没 hover 信息，用户看不到失败原因。

**Backend**：`build_strategy_detail_payload`（`open_composer/dashboard/server.py:L1004`）已经返回 `project.gate_summary`。需要额外把 `promotion.json` 里的 blocked_checks / warning_checks reasons 挂上：

```python
# build_strategy_detail_payload 内：
promotion_path = root / "reports" / "research" / f"{resolved_name}-promotion.json"
pass_reasons: dict[str, list[dict[str, str]]] = {
    "workflow_pass": [], "research_pass": [],
    "llm_contribution_pass": [], "paper_ready_pass": [],
}
if promotion_path.exists():
    try:
        import json
        promo = json.loads(promotion_path.read_text(encoding="utf-8"))
        for check in promo.get("checks") or []:
            if not isinstance(check, dict):
                continue
            if check.get("status") in {"blocked", "warning"}:
                # 启发式：把 check 归到对应 pass（保守做法：blocked → 全部 pass；warning → 同上）
                for pass_name in pass_reasons:
                    pass_reasons[pass_name].append({
                        "name": str(check.get("name") or ""),
                        "status": str(check.get("status") or ""),
                        "message": str(check.get("message") or ""),
                    })
    except (OSError, json.JSONDecodeError):
        pass
# 在返回 payload 里加：
payload["pass_reasons"] = pass_reasons
```

（更精细的实现可以做"每个 check 标记它影响哪个 pass"，但当前 promotion 不带这个映射；保守把 blocked/warning 同时挂到 4 个 pass 即可，前端按 `gate_summary[name]` 状态过滤显示。）

**前端**：`strategy-detail.tsx` 的 `PassBadge`：

```tsx
function PassBadge({
  label,
  value,
  reasons,
}: {
  label: string;
  value: unknown;
  reasons?: Array<{ name: string; status: string; message: string }>;
}) {
  const color = value === true ? "green" : value === false ? "pink" : "orange";
  const tooltip = (reasons ?? [])
    .filter((row) => row.status === "blocked" || row.status === "warning")
    .slice(0, 6)
    .map((row) => `[${row.status}] ${row.name}: ${row.message}`)
    .join("\n");
  return (
    <div
      className="rounded-md bg-[var(--paper-3)] px-3 py-2 flex items-center justify-between gap-2 min-w-0"
      title={tooltip || `${label}: ${String(value)}`}
    >
      <span className="t-caption ink-subtle truncate">{label}</span>
      <Tag color={color}>{value === true ? "pass" : value === false ? "fail" : "unknown"}</Tag>
    </div>
  );
}

// 调用处：
<PassBadge label="workflow_pass" value={gate.workflow_pass} reasons={data?.pass_reasons?.workflow_pass} />
<PassBadge label="research_pass" value={gate.research_pass} reasons={data?.pass_reasons?.research_pass} />
<PassBadge label="llm_contribution_pass" value={gate.llm_contribution_pass} reasons={data?.pass_reasons?.llm_contribution_pass} />
<PassBadge label="paper_ready_pass" value={gate.paper_ready_pass ?? paperReport?.ready} reasons={data?.pass_reasons?.paper_ready_pass} />
```

**测试**：手测；可选加 `test_pass_reasons_in_detail_payload` 验证字段存在。

#### 4.3.3 [D.3.5] SSE 默认 ticks 提到 300

**问题**：30 秒断流，前端 EventSource 自动重连可见。

**改动**：`open_composer/dashboard/server.py:L424`：

```python
# 改前：
ticks = _query_int(query, "ticks", default=30, minimum=1, maximum=3600)

# 改后：
ticks = _query_int(query, "ticks", default=300, minimum=1, maximum=3600)
```

并在前端 `strategy-detail.tsx` 的 SSE useEffect 处理 `onopen` 给 toast/状态展示：

```tsx
source.onopen = () => {
  setStatus("Trace stream connected.");
};
source.onerror = () => {
  polling = true;
  source.close();
  setStatus("Trace stream interrupted; falling back to polling.");
};
```

**测试**：手测；EventSource 在断开后约 1-3 秒自动重连（浏览器默认行为）；用户看到 "Trace stream connected." 闪现是正常。

#### 4.3.4 [D.4] LiveView Paper PnL 实时拉取

**问题**：`live.tsx` 渲染数据全部来自静态 `data.ts` 的 `paperPositions / paperOrders`。

**前端**：`dashboard/src/app/components/live.tsx`：

```tsx
export function LiveView() {
  // ... 原有 state ...
  const [livePositions, setLivePositions] = useState<Array<Record<string, any>>>(paperPositions);
  const [liveOrders, setLiveOrders] = useState<Array<Record<string, any>>>(paperOrders);
  const [liveAlerts, setLiveAlerts] = useState<Array<Record<string, any>>>([]);
  const [livePnlSeries, setLivePnlSeries] = useState<Array<{ ts: string; value: number }>>([]);

  const refreshLive = async () => {
    try {
      const [positions, orders, alerts] = await Promise.all([
        getDashboardJson<{ positions: Array<Record<string, any>> }>("/api/paper/positions"),
        getDashboardJson<{ orders: Array<Record<string, any>> }>("/api/paper/orders"),
        getDashboardJson<{ alerts: Array<Record<string, any>> }>("/api/paper/alerts"),
      ]);
      setLivePositions(positions.positions ?? []);
      setLiveOrders(orders.orders ?? []);
      setLiveAlerts(alerts.alerts ?? []);
      // PnL 时间序列：用 account_equity 累加（如果 /api/dashboard/catalog 有 snapshot history，再用它）
      const equity = dashboardSummary.paperAccountEquity ?? 0;
      setLivePnlSeries((current) => [
        ...current.slice(-29),
        { ts: new Date().toISOString(), value: equity },
      ]);
    } catch {
      // 保持上次数据
    }
  };

  useEffect(() => {
    void refreshLive();
    const timer = window.setInterval(refreshLive, 30_000);
    return () => window.clearInterval(timer);
  }, []);

  // 渲染处把 paperPositions 改为 livePositions，paperOrders 改为 liveOrders
  // PaperPnlChart 用 livePnlSeries
  ...
}
```

**Backend**：`/api/paper/positions` / `/api/paper/orders` / `/api/paper/alerts` 已存在（`server.py:L227-235`），确认返回 shape 与前端使用一致即可。

**测试**：手测；可选加 `test_paper_positions_payload_shape`。

**Wave 4.3 验收**：

```bash
# 清仓库测 onboarding
rm -rf projects/ strategy_specs/active/ reports/runs/
make dashboard-build && make dashboard-serve
# 浏览器：Overview 显示三张引导卡片

# 4-Pass tooltip
# 任意 strategy detail，hover 红色 badge → 浏览器原生 tooltip 显示 blocked check 列表

# SSE 长连
# 打开 Strategy Detail → Conversation tab，观察 5 分钟内不断流

# LiveView 实时
# 修改 reports/paper/account.json，30 秒内 LiveView 数字自动刷新

.venv/bin/pytest tests/ -q
.venv/bin/oc repo check --strict
make verify
```

---

### Wave 4.4 — D.3 Codex SDK 真实回归测试

#### 4.4.1 [D.3] 集成测试 CodexAgentBackend

**问题**：`open_composer/agent_backend/codex_sdk.py` 调用的 `CodexAppServerClient.start_session / send_user_message / is_session_alive / cancel_session` 是按 OpenAI 设计草图写的。如果真实 `codex_sdk` python 包发布的 API 不一样，运行时会 `AttributeError`。

**改动 1**：`open_composer/agent_backend/codex_sdk.py` 加 API 兼容层：

```python
class CodexAgentBackend:
    name = "codex_sdk"
    REQUIRED_METHODS = {
        "start_session",
        "send_user_message",
        "is_session_alive",
        "cancel_session",
    }

    def __init__(self, model: str | None = None):
        if CodexAppServerClient is None:
            raise RuntimeError("codex_sdk package is not installed")
        self.model = model or default_openai_model()
        self._client = CodexAppServerClient()
        missing = [m for m in self.REQUIRED_METHODS if not hasattr(self._client, m)]
        if missing:
            raise RuntimeError(
                f"codex_sdk CodexAppServerClient is missing required methods: {sorted(missing)}. "
                f"Update CodexAgentBackend mappings or fall back to OPEN_COMPOSER_AGENT_BACKEND=file_queue."
            )
        self._fallback = FileQueueAgentBackend()
```

**改动 2**：新增 `tests/test_codex_sdk_backend.py`：

```python
"""集成测试 CodexAgentBackend。

默认 skip — 仅在环境里同时安装了 codex_sdk python 包 + codex CLI 时跑。
通过设置环境变量 OPEN_COMPOSER_RUN_CODEX_INTEGRATION=1 启用。
"""
import importlib.util
import os
from pathlib import Path
import pytest


def _codex_sdk_available() -> bool:
    return importlib.util.find_spec("codex_sdk") is not None


def _integration_enabled() -> bool:
    return os.getenv("OPEN_COMPOSER_RUN_CODEX_INTEGRATION") == "1"


@pytest.mark.skipif(
    not _codex_sdk_available(), reason="codex_sdk python package not installed"
)
def test_codex_agent_backend_signature_check(tmp_path: Path) -> None:
    """单元级：确认 CodexAppServerClient 暴露我们需要的 4 个方法。"""
    from codex_sdk import CodexAppServerClient
    instance = CodexAppServerClient()
    for method in ("start_session", "send_user_message", "is_session_alive", "cancel_session"):
        assert hasattr(instance, method), (
            f"codex_sdk API drift: missing {method!r} on CodexAppServerClient. "
            f"Update open_composer/agent_backend/codex_sdk.py mappings."
        )


@pytest.mark.skipif(
    not (_codex_sdk_available() and _integration_enabled()),
    reason="integration test disabled; set OPEN_COMPOSER_RUN_CODEX_INTEGRATION=1",
)
def test_codex_agent_backend_round_trip(tmp_path: Path, monkeypatch) -> None:
    """集成级：在临时仓库里启动 session → 发指令 → cancel。"""
    from open_composer.agent_backend.codex_sdk import CodexAgentBackend
    from open_composer.projects import create_project
    from open_composer.models.project import StrategyProjectCreate

    monkeypatch.chdir(tmp_path)
    # 准备最小仓库
    (tmp_path / "projects").mkdir()
    project, _ = create_project(
        StrategyProjectCreate(name="codex-int", thesis="t", idea="i", max_rounds=1),
        tmp_path,
    )

    backend = CodexAgentBackend()
    cmd_id = backend.send_command(
        project.project_id, kind="advice", body="hello", root=tmp_path
    )
    assert cmd_id
    status = backend.status(project.project_id, tmp_path)
    assert status.backend == "codex_sdk"
    assert status.session_id is not None
    backend.stop(project.project_id, tmp_path)
```

**改动 3**：在 `docs/setup-local.zh.md` 或新增 `docs/codex-sdk-setup.md` 加一段：

```markdown
## （可选）Codex SDK Backend

OpenAI Codex CLI v0.128+ 提供 codex app-server JSON-RPC 与 Python SDK，
可作为 Open Composer 的实时 agent backend。

```bash
# 安装 codex CLI（需要 OpenAI 账号）
brew install codex     # macOS；其他系统见官方文档

# 安装 Python SDK
uv add codex-sdk       # 已在主项目时
# 或单独：
pip install codex-sdk

# 切换 backend
uv run oc agent use --backend codex_sdk
```

切换后 `oc project continue` / Dashboard 的 "Continue" 按钮会通过 codex app-server
直接驱动持久 session，每次写 queue.jsonl 后同时发送 user message 给绑定的
session。当 codex 进程不可用时，自动回退到 file_queue 模式（trace 中 backend 字段
显示 "file_queue (fallback)"）。

集成测试：
```bash
export OPEN_COMPOSER_RUN_CODEX_INTEGRATION=1
.venv/bin/pytest tests/test_codex_sdk_backend.py -q
```
```

**Wave 4.4 验收**：

```bash
# 单元（API 签名）
.venv/bin/pytest tests/test_codex_sdk_backend.py::test_codex_agent_backend_signature_check -q
# 跳过（如果没装 codex_sdk）→ 报告 SKIPPED；装了 → 报告 PASSED

# 集成（可选；需要真实凭证）
OPEN_COMPOSER_RUN_CODEX_INTEGRATION=1 \
.venv/bin/pytest tests/test_codex_sdk_backend.py::test_codex_agent_backend_round_trip -q

# 即使没装 codex_sdk，主测试套件全绿
.venv/bin/pytest tests/ -q
```

---

## 5. 完整验收清单（4.1 - 4.4 全完成）

```text
[ ] C.1 _input_rows 加 window_bars 参数；默认 None = 全历史
[ ] C.1 oc feature materialize 支持 --window-bars
[ ] C.1 Dashboard Materialize 按钮提供 Last 16 / 200 / 1000 / Full history 选项
[ ] C.1 tests/test_llm_materialize.py 新增 3 个 test 全绿
[ ] C.1 promotion 跑 LLM-factor 策略时 packets 数 >> 16，marginal_lift 不再恒为 0

[ ] C.2 新增 GET /api/activity/trace?limit=&project=&since_ts=&kind=
[ ] C.2 ActivityView timeline 包含 kind="Trace" 行，按 agent 染色
[ ] C.2 跨 project trace 聚合按 ts desc 排序
[ ] C.2 tests/test_dashboard_server.py 新增 2 个 test 全绿

[ ] C.3 新增 GET/POST /api/strategies/{name}/llm-factors/{factor}/prompt
[ ] C.3 LLMFactorsTab 每张 factor card 有 [Edit prompt] 按钮
[ ] C.3 点击后展开 inline textarea + Save 写文件 + 显示 hash + "needs re-materialize"
[ ] C.3 Save 后写一行 trace.jsonl operation=dashboard_edit_llm_factor_prompt
[ ] C.3 DASHBOARD_CLI_PARITY 加新条目（标注 "file edit only"）
[ ] C.3 tests/test_dashboard_server.py 新增 2 个 test 全绿

[ ] C.4 _llm_factor_rows 读 reports/research/{name}-factor-lab.json 并挂 rank_ic 等字段
[ ] C.4 FactorICChart 接收多 bar 数据，显示 rank IC / rolling mean / rolling min
[ ] C.4 KPI 区显示真实 Rank IC 数值
[ ] C.4 tests/test_dashboard_server.py 新增 1 个 test 全绿

[ ] D.1 Overview 检测首次启动并显示 OnboardingHero 3 卡片
[ ] D.1 "Try sample" 按钮 POST /api/build/draft 创建样例项目
[ ] D.1 "Build new" 按钮通过 onNavigate prop 切换 tab

[ ] D.2 build_strategy_detail_payload 附 pass_reasons 字段
[ ] D.2 PassBadge 接收 reasons 并通过 title 属性显示 tooltip

[ ] D.3 CodexAgentBackend __init__ 检查 REQUIRED_METHODS，缺失时报清晰错误
[ ] D.3 tests/test_codex_sdk_backend.py 含 signature_check + round_trip 两个 test
[ ] D.3 文档更新（docs/setup-local.zh.md 或新增 codex-sdk-setup.md）

[ ] D.3.5 SSE 默认 ticks=300
[ ] D.3.5 前端 source.onopen 显示 "Trace stream connected."

[ ] D.4 LiveView useEffect 每 30s 拉取 positions/orders/alerts
[ ] D.4 PaperPnlChart 用真实账户 equity 时间序列

[ ] uv run pytest 全绿
[ ] uv run oc repo check --strict 通过
[ ] make verify 通过
[ ] git diff --stat 净增可控（预计 < +1500 行）
```

## 6. 不做什么（Step 4 边界）

```text
✗ 不引入新 StrategySpec 字段
✗ 不改 4 个 pass 语义
✗ 不改 harness 规则 / paper safety chain
✗ 不动 expressions AST 白名单
✗ 不允许 backtest loop 中 live LLM call
✗ 不引入 WebSocket（SSE 够用）
✗ 不引入新前端框架（React 18 + Vite + Tailwind + recharts 不变）
✗ 不引入新 agent backend（仅 codex_sdk + file_queue）
✗ 不重写 Router / promotion / paper / catalog 任何模块
✗ 不新增新策略类型 / 新模板
```

## 7. 风险与对冲

| 风险 | 对冲 |
|---|---|
| C.1 全历史物化耗时长 / token 消耗大 | 前端默认 Full history 但 confirm modal 提示预估 packet 数；CLI 与 API 支持 `--window-bars`；cache key 不变保证可断点续跑 |
| C.1 改完后历史 packet 失效 | `schema_version="2"` + `input_view_version` 联合 invalidation；不动现有 packets 直到下次 materialize；提供 `--refresh` 显式重算 |
| C.2 trace.jsonl 聚合慢（百个 project）| 每个 project 仅读 tail 200 行；按 ts desc 全局合并后再切 limit |
| C.2 跨 project 隐私 | 个人工作台无多用户场景；trace 已是仓库内文件，无新数据暴露 |
| C.3 编辑器 textarea 在大 prompt 上卡 | 限制 textarea 单次保存 ≤ 64KB；超长强制 CLI |
| C.3 编辑后忘了 re-materialize | Save 响应明确说 "needs_rematerialize=True"；promotion 在 packet prompt_hash 与 spec prompt_template 不一致时降级 status |
| C.4 没有 factor-lab.json 时图表空 | rank_ic 字段 null → chart 自动渲染 0；KPI 显示 "n/a" |
| D.1 onboarding 误触清空仓库测试 | seedSampleStrategy 用 confirm modal；template_id 校验白名单 |
| D.2 pass_reasons 可能过长导致 tooltip 太大 | 截到前 6 条；超长用 ellipsis；保留 promotion.md 链接 |
| D.3 codex_sdk 包 API 漂移 | REQUIRED_METHODS 检查在 __init__ 即抛清晰错误，附"如何回退到 file_queue"指南 |
| D.3.5 ticks=300 让请求挂太久 | HTTP 服务支持优雅断开；前端 EventSource 自动重连；ticks 仍可通过 query 参数缩短 |
| D.4 paper API 30s 轮询失败 | refreshLive 用 try/catch 保留上次数据；不阻塞 UI |

## 8. 回滚预案

- 每个 Wave 单独 PR。
- Wave 4.1（C.1+C.2）出问题：C.1 单独 revert 不影响 C.2；反之亦然。
- Wave 4.2（C.3+C.4）出问题：纯前端 + 单端点新增，revert 不影响主流程。
- Wave 4.3（D.1/D.2/D.3.5/D.4）问题：纯前端 + 1 行 backend 改动，单点 revert 容易。
- Wave 4.4（D.3）：仅新增测试与 init 检查，不影响生产路径；标 `@pytest.mark.skipif` 默认不跑，整套测试 safe to ignore。

## 9. 完成定义

执行完 Wave 4.1 - 4.4 后：

- 任何 LLM 因子策略跑 `oc strategy evidence` 时，promotion 报告的 `llm_marginal_lift` 是基于完整历史 backtest 的真实数值
- Dashboard Activity 视图能看到所有 project 的 agent 工作时间线
- LLM Factors tab 全功能可在 Dashboard 完成 prompt 设计 → 物化 → 因子诊断查看
- 干净仓库打开 Dashboard 显示三卡引导，"Try sample"一键创建可用样例项目
- 4-Pass badge hover 立即看到所有 blocked / warning check 原因
- SSE 连接 5 分钟稳定，不再频繁重连闪烁
- LiveView paper 仪表盘自动 30s 刷新
- 使用了 Codex SDK 的用户：启动时如 API 漂移，立即得到清晰错误而非神秘 AttributeError

完成后 Open Composer 达到"个人 AI 量化策略工作台 v1.0"的稳定形态：Dashboard 是用户唯一入口，CLI 是 agent 通道，文件契约是审计真相，4 个 pass + harness 是不可绕过的研究安全边界。

## 10. 执行顺序总览（写给无上下文的 Codex）

```text
Wave 4.1  C.1 + C.2     ← P0 必修，最大 ROI；最先做
Wave 4.2  C.3 + C.4     ← P1 LLM 因子 UX 完整化
Wave 4.3  D.1 + D.2 + D.3.5 + D.4   ← P2 体验抛光（4 项小改）
Wave 4.4  D.3           ← P2 codex_sdk 回归测试（与生产路径隔离，可最后做）
```

每个 Wave 独立 PR。每个 PR 后必须：

```bash
.venv/bin/pytest tests/ -q
.venv/bin/oc repo check --strict
make verify
```

全绿才进入下一个 Wave。

如果中途某个 Wave 受阻，**已完成的 Wave 都是可发布状态**，不会让仓库进入半残状态。

## 11. CURRENT_DOCS 同步

把本文档加入 `open_composer/repo_check.py` 的 `CURRENT_DOCS` 集合（约 L20-44）：

```python
CURRENT_DOCS = {
    NO_CONTEXT_START_DOC,
    "docs/user-guide.md",
    "docs/setup-local.zh.md",
    "docs/remote-dashboard-deploy.zh.md",
    "docs/longbridge-integration.md",
    "docs/plan-step-1-simplification-2026-05-22.zh.md",
    "docs/plan-step-2-worksession-llm-factor-2026-05-22.zh.md",
    "docs/plan-step-3-dashboard-first-2026-05-22.zh.md",
    "docs/plan-step-4-llm-completion-and-ux-polish-2026-05-25.zh.md",   # ★ 本文档
}
```

同步在 `README.md` 的 `## Project Docs` 段加一行：

```markdown
- [docs/plan-step-4-llm-completion-and-ux-polish-2026-05-25.zh.md](docs/plan-step-4-llm-completion-and-ux-polish-2026-05-25.zh.md) — Step 4 LLM 闭环补完与 Dashboard 抛光
```

更新 `_readme_project_docs_check`（约 L227 起）允许的链接列表，加入此条。

执行完后跑 `.venv/bin/oc repo check --strict` 确认 docs_inventory 通过。
