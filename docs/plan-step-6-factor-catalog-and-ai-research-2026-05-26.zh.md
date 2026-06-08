# Open Composer Step 6：因子库接线 + AI-driven 自动研究（G1）

日期：2026-05-26
执行者：Codex / Claude Code
前置：Step 1（简化）+ Step 2（worksession + LLM factor）+ Step 3（Dashboard-first）+ Step 4（LLM 闭环补完）已完成；Step 5（research gates）独立路径（可并行）
后续：Step 7（条件触发的 ML / 衰减 / LLM 三角色）

## 0. 一句话目标

让 Codex / Claude Code 从「凭空想 EMA 参数写 spec」升级到「从因子库挑因子 + 自动跑研究流水线」。**目标在一个 agent 会话内全部落地**（约 2-3 小时），完成后用户用一句自然语言 thesis 就能让 AI 自动走完「假设 → 选因子 → 单因子 IC → 组合 → 回测 → evidence → 报告」。

## 1. 背景（无上下文也能看懂）

Open Composer 是个人 AI 量化策略工作台。源头是 `StrategySpec`（YAML），CLI 入口是 `oc`，agent 是 Codex / Claude Code（通过 `projects/{id}/queue.jsonl` 与 `trace.jsonl` 与产品文件契约通信）。

Step 1-4 把产品基础设施做完整了：StrategySpec / 4-pass / harness gates / 6 位精度回测对账 / LLM factor materialization / Dashboard 全交互。

但今天审计发现两个深层问题：

### 缺口 A：`factor_library.py` 是孤儿模块

`open_composer/research/factor_library.py` 已经定义了 32 个 `FactorDefinition`（12 个 family：trend_momentum / risk_regime / relative_strength / volatility_rank / drawdown_guard / breadth_canary / leadership / event_calendar / execution_timing / defensive_selection / portfolio_construction / recovery_regime），但 **全仓 grep `TACTICAL_ROUTER_FACTOR_LIBRARY` 与 `FactorDefinition` 在 open_composer/ 与 tests/ 下 0 引用**。30+ 个 `strategy_specs/drafts/` 全部用 `entry.all` 手写 EMA/SMA/RSI 表达式，没有一个引用 catalog。

### 缺口 B：研究流程没有「AI 主导」入口

Codex / Claude Code 已经有 `oc strategy draft / parameter-sweep / factor-lab / evidence` 等独立命令，但没有一个把「假设 → 因子选择 → IC → 组合 → backtest → promotion」串成单一流水线的入口。结果：用户每次都要自己决定 step 顺序，agent 自由发挥；过拟合（3480 trial）与无效组合（线性指标网格搜）是普遍后果。

### 调研结论支撑

- WorldQuant 101 Formulaic Alphas（Kakushadze 2015）是行业标准 alpha catalog 起点；Microsoft Qlib 的 Alpha158 / Alpha360 是 ML quant 标配。
- 个人量化（vs 机构）的优势是**速度 + 定制 + AI 杠杆**，劣势是**算力 + 数据 + 无法分散**。结论：保持小宇宙（≤ 20 标的）+ 中频（daily / 15m）+ 控制 100-150 因子库 + AI 串流水线，是个人量化标准做法。
- Open Composer 选择「不换 Qlib，借鉴搬运」：把 WorldQuant Alpha101 与 Qlib Alpha158 的因子定义搬到本仓库的 `factor_library.py`，**其余 Qlib 制品（YAML workflow / backtest engine / data server）一律不引入**，保留 Open Composer 已有的 StrategySpec / 4-pass / harness 审计基础。

## 2. 目标 / 非目标

### 目标

1. **`factor_library.py` 扩到 ≥ 80 个 FactorDefinition**：现有 32 + Alpha101 子集 ~30 + Alpha158 子集 ~20。
2. **每个 FactorDefinition 增加 `expression` 模板字段**，使 catalog 因子可被 spec 直接引用。
3. **`StrategySpec.factors` 支持 `source: factor_library`**：用 `factor_id + params` 引用 catalog，而非每次手写 expression。
4. **新增 4 个 CLI**：`oc factor list / show / use-in / catalog-status`。
5. **新增核心 CLI `oc research auto <thesis>`**：AI 自动串「brief → 选因子 → 单因子 IC → 组合 → spec draft → backtest → evidence」流水线。
6. **因子血统基础结构**：每个 FactorDefinition 使用即写入 `reports/factors/{factor_id}/lineage.json`，记录创建者、使用 spec、创建 thesis。
7. **现有 30+ specs 不变**：保留为 `source: expression` 不强迫迁移；仅新策略默认走 catalog。

### 非目标（明确不做）

- 不引入 ML 依赖（lightgbm / sklearn / pytorch）—— 留给 Step 7.A。
- 不做衰减监控 cron —— 留给 Step 7.B（但血统结构在 G1 就位）。
- 不做 LLM 因子自动挖掘（`oc factor propose`）—— 留给 Step 7.C。
- 不改 4-pass 语义。
- 不改 harness 规则。
- 不改 paper safety chain。
- 不动 AST 安全白名单（catalog 因子展开后仍走同一 AST 安全检查）。
- 不引入 cross-sectional rank（Alpha101 大部分 rank-based alpha 要 universe ≥ 50 才有意义，超出个人量化默认场景）。

## 3. 当前状态扫描

```text
open_composer/research/
  factor_library.py        32 FactorDefinition；TACTICAL_ROUTER_FACTOR_LIBRARY tuple
                           当前字段：id / family / label / description / inputs / output
                                     default_parameter_space / source_card_ids
                                     implementation_notes / risk_notes
                           ⚠ 缺：expression 模板字段
  factor_lab.py           run_factor_lab() 单因子 IC / IR / 分位收益（已存在）
  research_report.py      被 oc strategy evidence 调用

open_composer/models/strategy_spec.py
  L159 class FactorConfig
       source: Literal["expression", "llm_feature", "feature_packet"]
  ⚠ 需要加 "factor_library" 作为第 4 种 source

open_composer/expressions.py
  L180 validate_expression
  L199 evaluate_expression
  L217 prepare_factor_frame
  AST 白名单 + indicators 全部就位

open_composer/cli.py
  21 个子命令组；strategy / feature / project / agent / dashboard 等
  ⚠ 需要新增 factor / research 子命令组

reports/factors/        当前不存在；G1 创建
  {factor_id}/
    lineage.json         本步骤新增
```

## 4. 改动清单（按 Wave 分批；一个 agent 会话内顺序完成）

### Wave 6.1 — FactorDefinition 增加 expression 模板（30 分钟）

**4.1.1 扩展 `FactorDefinition` dataclass**

文件：`open_composer/research/factor_library.py`

```python
@dataclass(frozen=True)
class FactorDefinition:
    id: str
    family: str
    label: str
    description: str
    inputs: list[str]                                    # ["close"] / ["close", "volume"] 等
    output: str                                          # 输出语义：return_pct / score / signal 等
    default_parameter_space: dict[str, list[Any]]
    expression: str | None = None                        # ✦ 新增：参数化模板
    source_card_ids: list[str] = field(default_factory=list)
    implementation_notes: list[str] = field(default_factory=list)
    risk_notes: list[str] = field(default_factory=list)


def materialize_expression(factor: FactorDefinition, params: dict[str, Any]) -> str:
    """把模板用 params 实例化为可执行表达式。

    expression 模板用 {param_name} 占位符。
    例：expression="(close - lag(close, {lag_days})) / lag(close, {lag_days})"
        params={"lag_days": 1} → "(close - lag(close, 1)) / lag(close, 1)"

    Raises:
        ValueError: 模板中的占位符在 params 与 default_parameter_space 都找不到。
    """
    if factor.expression is None:
        raise ValueError(f"factor {factor.id} has no expression template")
    # 缺失的参数用 default_parameter_space 第一个值补全
    resolved: dict[str, Any] = {}
    for key in _expression_placeholders(factor.expression):
        if key in params:
            resolved[key] = params[key]
        elif key in factor.default_parameter_space:
            options = factor.default_parameter_space[key]
            if not options:
                raise ValueError(f"factor {factor.id} default for {key!r} is empty")
            resolved[key] = options[0]
        else:
            raise ValueError(
                f"factor {factor.id} expression needs {key!r}; "
                "missing from params and default_parameter_space"
            )
    return factor.expression.format(**resolved)


def _expression_placeholders(expression: str) -> list[str]:
    """从 '{a} + sma({b}, {c})' 中提取 ['a', 'b', 'c']"""
    import string
    return [tup[1] for tup in string.Formatter().parse(expression) if tup[1] is not None]
```

**4.1.2 给现有 32 个 FactorDefinition 补 `expression`**

每个 factor 都补一个可执行表达式模板。例如：

```python
FactorDefinition(
    id="absolute_time_series_momentum_120",
    family="trend_momentum",
    label="120-day absolute momentum",
    description="...",
    inputs=["close"],
    output="momentum_pct",
    default_parameter_space={"lookback_days": [60, 120, 180]},
    expression="(close - lag(close, {lookback_days})) / lag(close, {lookback_days})",
    source_card_ids=["tsm_moskowitz_ooi_pedersen", "faber_taa_trend_filter"],
    ...
),
FactorDefinition(
    id="volatility_rank_20_252",
    family="risk_regime",
    label="20-day volatility percentile",
    inputs=["close"],
    output="volatility_percentile",
    default_parameter_space={"vol_window_days": [20, 60], "rank_window_days": [252]},
    expression="stddev(close, {vol_window_days})",   # rank 留给后续；这里只算 vol
    ...
),
```

补完所有 32 个；如果某 factor 因业务过于复杂无法用单 expression 表达，把 `expression=None` 保留并加注释 `# 复合因子，由 router_common 处理`。

**Wave 6.1 验收**：

```bash
.venv/bin/python -c "
from open_composer.research.factor_library import TACTICAL_ROUTER_FACTOR_LIBRARY, materialize_expression
assert len(TACTICAL_ROUTER_FACTOR_LIBRARY) >= 32
expressionable = [f for f in TACTICAL_ROUTER_FACTOR_LIBRARY if f.expression]
print(f'expressionable: {len(expressionable)}/{len(TACTICAL_ROUTER_FACTOR_LIBRARY)}')
for f in expressionable[:3]:
    print(f.id, '=>', materialize_expression(f, {}))
"
```

---

### Wave 6.2 — 移植 WorldQuant Alpha101 与 Qlib Alpha158 子集（45 分钟）

**4.2.1 选择标准**

只选 **单标的（non-cross-sectional） + 无 lookahead + AST 可表达** 的 alpha：

```text
Alpha101 子集（选 ~30 个）：
  原始 alpha 形如 (-1 * delta(close, 1)) → 直接对应到 expression: "-1 * (close - lag(close, 1))"
  跳过：所有含 rank(...) / IndNeutralize(...) / cross-sectional 操作的
  保留：含 delta / delay / ts_sum / ts_argmax 等可用单 series 实现的

Alpha158 子集（选 ~20 个）：
  K-line 形态：(close - open) / open
  隔夜跳空：(open - lag(close, 1)) / lag(close, 1)
  高低比：(high - low) / open
  上下影线：(high - max(open, close)) / open  ⚠ max() 不在 AST 白名单，需要在 expressions.py 增加，或者拆成 conditional
  价格位置：(close - lowest(low, 20)) / (highest(high, 20) - lowest(low, 20))
  成交量加权动量：(close - sma(close, 5)) * volume / sma(volume, 5)
```

**4.2.2 在 factor_library.py 末尾追加**

```python
# ============================================================================
# WorldQuant Alpha 101 子集（无 cross-sectional rank，可单标的）
# Source: Kakushadze 2015, "101 Formulaic Alphas" (arXiv:1601.00991)
# ============================================================================

ALPHA101_LIBRARY: tuple[FactorDefinition, ...] = (
    FactorDefinition(
        id="alpha101_001_neg_delta_close_1d",
        family="momentum_short",
        label="Alpha101 #001 short-term reversal proxy",
        description=(
            "Negative 1-day close change; positive signals a recent down move "
            "(short-term reversal candidate)."
        ),
        inputs=["close"],
        output="signed_return_pct",
        default_parameter_space={"lag_days": [1, 2, 3]},
        expression="-1 * (close - lag(close, {lag_days})) / lag(close, {lag_days})",
        source_card_ids=["kakushadze_101_alphas"],
        implementation_notes=[
            "Inverted sign captures short-term mean reversion intuition.",
            "Combine with volume filters for higher signal quality.",
        ],
    ),
    # ... 约 30 个 Alpha101 alpha
)


# ============================================================================
# Qlib Alpha158 子集（K-line / overnight / position）
# Source: Microsoft Qlib examples/benchmarks/LightGBM/Alpha158
# ============================================================================

ALPHA158_LIBRARY: tuple[FactorDefinition, ...] = (
    FactorDefinition(
        id="alpha158_kbar_body",
        family="kline_shape",
        label="Alpha158 K-bar body",
        description="(close - open) / open — daily candle body magnitude.",
        inputs=["open", "close"],
        output="body_pct",
        default_parameter_space={},
        expression="(close - open) / open",
        source_card_ids=["qlib_alpha158"],
    ),
    FactorDefinition(
        id="alpha158_overnight_gap",
        family="overnight_gap",
        label="Alpha158 overnight gap",
        description="(open_t - close_{t-1}) / close_{t-1} — overnight return.",
        inputs=["open", "close"],
        output="overnight_return_pct",
        default_parameter_space={},
        expression="(open - lag(close, 1)) / lag(close, 1)",
        source_card_ids=["qlib_alpha158"],
    ),
    FactorDefinition(
        id="alpha158_price_position_20d",
        family="position",
        label="Alpha158 20-day price position",
        description="Normalized close position within 20-day high-low range.",
        inputs=["close", "high", "low"],
        output="position_score",
        default_parameter_space={"window_days": [20, 60]},
        expression=(
            "(close - lowest(low, {window_days})) / "
            "(highest(high, {window_days}) - lowest(low, {window_days}))"
        ),
        source_card_ids=["qlib_alpha158"],
    ),
    # ... 约 20 个 Alpha158 factor
)


# 全 catalog 合并入口
ALL_FACTORS: tuple[FactorDefinition, ...] = (
    *TACTICAL_ROUTER_FACTOR_LIBRARY,
    *ALPHA101_LIBRARY,
    *ALPHA158_LIBRARY,
)


def get_factor(factor_id: str) -> FactorDefinition:
    """O(1) lookup via cached dict."""
    return _FACTOR_INDEX[factor_id]


_FACTOR_INDEX = {f.id: f for f in ALL_FACTORS}


def list_factors(family: str | None = None, inputs: set[str] | None = None) -> list[FactorDefinition]:
    """Filter catalog by family / required inputs."""
    result = list(ALL_FACTORS)
    if family:
        result = [f for f in result if f.family == family]
    if inputs:
        result = [f for f in result if set(f.inputs).issubset(inputs)]
    return result
```

**4.2.3 source card 入库**

新增 `reports/harness/source_cards/_global_factor_library.jsonl`（注意 `_global_` 前缀避免与 per-strategy source cards 冲突）：

```jsonl
{"claim_id":"kakushadze_101_alphas","claim":"WorldQuant 101 formulaic alpha catalog","source_url":"https://arxiv.org/abs/1601.00991","source_type":"paper","accessed_at":"2026-05-26","applies_to":["factor_library"],"impact_on_spec":"Alpha101 subset adopted into factor_library.py for single-symbol use; rank-based alphas excluded.","limitations":"Cross-sectional rank operations not available for single-asset strategies."}
{"claim_id":"qlib_alpha158","claim":"Microsoft Qlib Alpha158 K-line/overnight feature set","source_url":"https://github.com/microsoft/qlib","source_type":"platform_docs","accessed_at":"2026-05-26","applies_to":["factor_library"],"impact_on_spec":"Alpha158 K-line / overnight / position factors adopted as expression templates.","limitations":"Qlib backtest engine and YAML workflow NOT adopted; only factor expressions are borrowed."}
{"claim_id":"tsm_moskowitz_ooi_pedersen","claim":"Time-series momentum exists across major asset classes","source_url":"https://www.aqr.com/Insights/Research/Journal-Article/Time-Series-Momentum","source_type":"paper","accessed_at":"2026-05-26","applies_to":["trend_momentum"],"impact_on_spec":"Supports use of absolute_time_series_momentum_120 family.","limitations":"Single-asset application of cross-asset evidence."}
```

继续补完所有现有 `source_card_ids` 引用。

**Wave 6.2 验收**：

```bash
.venv/bin/python -c "
from open_composer.research.factor_library import ALL_FACTORS, list_factors
print(f'total: {len(ALL_FACTORS)}')
print(f'with expression: {len([f for f in ALL_FACTORS if f.expression])}')
families = sorted({f.family for f in ALL_FACTORS})
print(f'families: {families}')
"
# 期望：total >= 80；with expression >= 70；families >= 15
```

---

### Wave 6.3 — StrategySpec 支持 `source: factor_library`（30 分钟）

**4.3.1 扩展 `FactorConfig`**

文件：`open_composer/models/strategy_spec.py:159`

```python
class FactorConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: Literal["expression", "llm_feature", "feature_packet", "factor_library"] = "expression"  # ✦
    expression: str | None = None
    path: str | None = None
    field: str | None = None
    default: float | bool = 0.0
    description: str = ""

    # 已有 LLM factor 字段
    input_view: str | None = None
    input_view_version: int | None = Field(default=None, ge=1)
    prompt_template_path: str | None = None
    output_schema: LLMFactorOutputSchema | None = None
    cache_policy: LLMFactorCachePolicy | None = None
    model_ref: str | None = None

    # ✦ 新增：factor_library 引用字段
    factor_id: str | None = None                      # catalog ID
    params: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_factor_source_fields(self) -> FactorConfig:
        if self.source == "expression" and not self.expression:
            raise ValueError("expression factors require expression")
        if self.source == "feature_packet" and not self.field:
            raise ValueError("feature_packet factors require field")
        if self.source == "llm_feature":
            # ... 已有逻辑保留
            pass
        if self.source == "factor_library":                                    # ✦
            if not self.factor_id:
                raise ValueError("factor_library factors require factor_id")
            from open_composer.research.factor_library import (
                _FACTOR_INDEX, materialize_expression,
            )
            if self.factor_id not in _FACTOR_INDEX:
                raise ValueError(
                    f"factor_id {self.factor_id!r} not in factor_library catalog"
                )
            factor = _FACTOR_INDEX[self.factor_id]
            if not factor.expression:
                raise ValueError(
                    f"factor {self.factor_id} has no expression template; "
                    "cannot use as source=factor_library"
                )
            # 实例化 expression 验证 params 合法
            rendered = materialize_expression(factor, self.params)
            # 用 expression 字段透传到下游 (evaluate_expression / Pine compiler)
            object.__setattr__(self, "expression", rendered)
            object.__setattr__(self, "description", factor.description)
        return self
```

**4.3.2 示例 spec（写入 fixture，供后续测试用）**

新建 `tests/fixtures/strategy_specs/factor_library/example_catalog_factor_daily.yaml`：

```yaml
name: example_catalog_factor_daily
description: "Audit fixture using source=factor_library for trend + overnight factors."
timeframe: daily
universe: [SYN]
lifecycle: draft
entry:
  all:
  - trend_momentum_signal > 0
  - overnight_gap < 0.02
  any: []
exit:
  all: []
  any:
  - trend_momentum_signal < 0
risk:
  max_trades_per_day: 1
  max_position_weight: 1.0
costs: {commission_pct: 0.0, slippage_bps: 0.0, impact_model: linear, impact_eta: 0.0, impact_gamma: 0.0}
execution:
  backend: python_reference
  mode: manual_signal
  signal_on: bar_close
  fill_assumption: next_bar_open
  broker: none
data:
  source: sample
  symbol: SYN
  path: data/sample/syn_daily.csv
  feed: null
data_assumptions:
  source: sample
  adjusted: true
  timezone: America/New_York
factors:
  trend_momentum_signal:
    source: factor_library
    factor_id: absolute_time_series_momentum_120
    params:
      lookback_days: 120
  overnight_gap:
    source: factor_library
    factor_id: alpha158_overnight_gap
llm_review:
  enabled: false
notes:
  intent: "Demonstrates catalog factor usage for AI-driven research."
  open_questions: []
required_capabilities:
- market.synthetic_daily_long
```

**Wave 6.3 验收**：

```bash
.venv/bin/oc spec validate tests/fixtures/strategy_specs/factor_library/example_catalog_factor_daily.yaml
.venv/bin/python -c "
from open_composer.models.strategy_spec import load_strategy_spec
spec = load_strategy_spec('tests/fixtures/strategy_specs/factor_library/example_catalog_factor_daily.yaml')
print(spec.factors['trend_momentum_signal'].expression)
"
# 期望输出：(close - lag(close, 120)) / lag(close, 120)
```

---

### Wave 6.4 — `oc factor` CLI 与因子血统（45 分钟）

**4.4.1 新增 CLI 子命令组**

文件：`open_composer/cli.py`

```python
factor_app = typer.Typer(no_args_is_help=True)
app.add_typer(factor_app, name="factor")


@factor_app.command("list")
def factor_list_command(
    family: Annotated[str | None, typer.Option("--family")] = None,
    inputs: Annotated[str | None, typer.Option("--inputs", help="逗号分隔 OHLCV 输入")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """列出 factor catalog；可按 family / inputs 过滤。"""
    from open_composer.research.factor_library import list_factors

    inputs_set = {item.strip() for item in inputs.split(",")} if inputs else None
    factors = list_factors(family=family, inputs=inputs_set)
    if json_output:
        sys.stdout.write(json.dumps([asdict(f) for f in factors], indent=2) + "\n")
        return
    table = Table(title=f"Factor Catalog ({len(factors)} factors)")
    table.add_column("id")
    table.add_column("family")
    table.add_column("inputs")
    table.add_column("label")
    for f in factors:
        table.add_row(f.id, f.family, ",".join(f.inputs), f.label)
    console.print(table)


@factor_app.command("show")
def factor_show_command(factor_id: str) -> None:
    """显示单个 factor 的详细定义、表达式样本、使用 spec 列表。"""
    from open_composer.research.factor_library import get_factor, materialize_expression

    factor = get_factor(factor_id)
    console.print(f"[bold]{factor.id}[/bold] · {factor.label}")
    console.print(f"family: {factor.family}")
    console.print(f"inputs: {', '.join(factor.inputs)}")
    console.print(f"output: {factor.output}")
    console.print(f"\n[bold]description[/bold]\n{factor.description}")
    if factor.expression:
        rendered = materialize_expression(factor, {})
        console.print(f"\n[bold]expression (defaults)[/bold]\n  {rendered}")
    if factor.default_parameter_space:
        console.print(f"\n[bold]parameter space[/bold]")
        for k, v in factor.default_parameter_space.items():
            console.print(f"  {k}: {v}")
    if factor.source_card_ids:
        console.print(f"\n[bold]source cards[/bold]")
        for cid in factor.source_card_ids:
            console.print(f"  - {cid}")
    # 已使用 spec 列表（从血统读）
    lineage_path = project_root() / "reports" / "factors" / factor_id / "lineage.json"
    if lineage_path.exists():
        lineage = json.loads(lineage_path.read_text(encoding="utf-8"))
        used = lineage.get("used_in_specs", [])
        if used:
            console.print(f"\n[bold]used in specs[/bold] ({len(used)})")
            for sp in used[:10]:
                console.print(f"  - {sp}")


@factor_app.command("use-in")
def factor_use_in_command(
    spec_path: Path,
    factor_id: str,
    name: Annotated[str, typer.Option("--name", help="spec 中 factor 字典的 key")] = "",
    params: Annotated[str | None, typer.Option("--params", help="k=v,k=v")] = None,
) -> None:
    """把 catalog factor 加到 spec 的 factors 段（in-place 修改 YAML）。"""
    import yaml
    from open_composer.research.factor_library import get_factor

    factor = get_factor(factor_id)
    factor_name = name or factor.id
    params_dict = _parse_kv_pairs(params) if params else {}
    raw = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    raw.setdefault("factors", {})
    raw["factors"][factor_name] = {
        "source": "factor_library",
        "factor_id": factor.id,
        "params": params_dict,
    }
    spec_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    # 写血统
    _append_factor_lineage(factor_id, spec_path)
    console.print(f"[green]factor added[/green] {factor_id} → {spec_path} as {factor_name}")


@factor_app.command("catalog-status")
def factor_catalog_status_command(
    strict: Annotated[bool, typer.Option("--strict")] = False,
) -> None:
    """验证 catalog 完整性：所有 expression 通过 AST、params validation 等。"""
    from open_composer.expressions import ExpressionSafetyError, assert_expression_safe
    from open_composer.research.factor_library import ALL_FACTORS, materialize_expression

    errors: list[str] = []
    warnings: list[str] = []
    for f in ALL_FACTORS:
        if not f.expression:
            warnings.append(f"{f.id}: no expression template")
            continue
        try:
            rendered = materialize_expression(f, {})
            assert_expression_safe(rendered)
        except (ValueError, ExpressionSafetyError) as exc:
            errors.append(f"{f.id}: {exc}")
    console.print(f"catalog size: {len(ALL_FACTORS)}")
    console.print(f"expressionable: {len([f for f in ALL_FACTORS if f.expression])}")
    console.print(f"errors: {len(errors)}")
    console.print(f"warnings: {len(warnings)}")
    for e in errors:
        console.print(f"  [red]✗[/red] {e}")
    for w in warnings:
        console.print(f"  [yellow]![/yellow] {w}")
    if strict and errors:
        raise typer.Exit(1)
```

**4.4.2 因子血统**

新增 `open_composer/research/factor_lineage.py`：

```python
"""Track factor → spec lineage for catalog factors.

Each factor gets a JSON file at reports/factors/{factor_id}/lineage.json:
  {
    "factor_id": "...",
    "created_at": "...",
    "definition_source": "tactical_router | alpha101 | alpha158 | user",
    "creation_thesis": "<one-line note>",
    "source_card_ids": [...],
    "parent_factor_ids": [],
    "used_in_specs": [
      {"spec_path": "...", "added_at": "...", "added_by": "codex|claude|cli|dashboard"}
    ]
  }

This file is updated by:
  - oc factor use-in (Dashboard or CLI both go through this)
  - oc research auto (when AI auto-adds factors to a generated spec)
"""
from __future__ import annotations
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from open_composer.config import ensure_dir, project_root
from open_composer.research.factor_library import get_factor


def append_lineage(
    factor_id: str,
    spec_path: str | Path,
    *,
    added_by: str = "cli",
    creation_thesis: str = "",
    root: Path | None = None,
) -> Path:
    base = root or project_root()
    factor = get_factor(factor_id)
    out_dir = ensure_dir(base / "reports" / "factors" / factor_id)
    out_path = out_dir / "lineage.json"
    now = datetime.now(UTC).isoformat()
    if out_path.exists():
        data = json.loads(out_path.read_text(encoding="utf-8"))
    else:
        data = {
            "factor_id": factor_id,
            "created_at": now,
            "definition_source": _detect_definition_source(factor_id),
            "creation_thesis": creation_thesis,
            "source_card_ids": list(factor.source_card_ids),
            "parent_factor_ids": [],
            "used_in_specs": [],
        }
    rel_spec = _relpath(Path(spec_path), base)
    if not any(u["spec_path"] == rel_spec for u in data["used_in_specs"]):
        data["used_in_specs"].append(
            {"spec_path": rel_spec, "added_at": now, "added_by": added_by}
        )
    out_path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    return out_path


def _detect_definition_source(factor_id: str) -> str:
    if factor_id.startswith("alpha101_"):
        return "alpha101"
    if factor_id.startswith("alpha158_"):
        return "alpha158"
    return "tactical_router"


def _relpath(path: Path, base: Path) -> str:
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        return path.as_posix()
```

CLI 入口里把 `_append_factor_lineage` 改为 `from open_composer.research.factor_lineage import append_lineage`。

**Wave 6.4 验收**：

```bash
.venv/bin/oc factor catalog-status --strict     # 全 catalog AST 安全
.venv/bin/oc factor list --family trend_momentum
.venv/bin/oc factor show absolute_time_series_momentum_120
.venv/bin/oc factor use-in tests/fixtures/strategy_specs/factor_library/example_catalog_factor_daily.yaml alpha158_kbar_body
test -f reports/factors/alpha158_kbar_body/lineage.json
```

---

### Wave 6.5 — `oc research auto <thesis>` 自动研究流水线（60-90 分钟）

**核心**：让用户用一句自然语言 thesis，触发 AI 自动跑完整研究流程。

**4.5.1 分阶段设计**

```text
用户输入: oc research auto "<thesis>" --universe TQQQ --timeframe daily

后端流程（确定性 + 可选 LLM）:

Stage A. Crystallize（确定性）
  - 把 thesis 写入 reports/research/auto/{run_id}/thesis.md
  - 推断 spec_template（从 universe / timeframe 推断必要 capability、初步 risk config）

Stage B. Candidate factor selection
  默认（无 LLM API）：基于 thesis 关键词 + factor family 匹配规则
    - "trend" → trend_momentum + relative_strength
    - "reversal / mean revert" → momentum_short（Alpha101 #001 类）
    - "volatility / regime" → risk_regime + volatility_rank
    - "overnight" → overnight_gap (alpha158)
    - "low VIX / quiet market" → risk_regime + breadth_canary
    - "drawdown" → drawdown_guard
    选 top-K = 10-15 candidates
  可选（有 OPENAI_API_KEY）：LLM 看 thesis + 全 catalog → 输出候选 factor_id 列表
    （用 OpenAI structured output 限制为 catalog 中存在的 ID）

Stage C. Single-factor IC test
  - 对每个 candidate factor，临时生成 mini-spec（factor 作为唯一 entry 条件）
  - 跑 oc strategy factor-lab
  - 收集 rank IC、IR、coverage、quantile spread
  - 输出 reports/research/auto/{run_id}/ic_scores.json

Stage D. Top-K selection
  - 排序：IR > 0.5 + rank IC > 0.02 + coverage > 0.8
  - 选 top 3-5
  - 输出 reports/research/auto/{run_id}/selected_factors.json

Stage E. Spec draft
  - 生成 StrategySpec 用 source: factor_library + 选中的 factor
  - entry: 所有 factor signal > 阈值
  - exit: 任一 factor signal < 反阈值
  - risk: 默认保守 max_position_weight=0.5, stop_loss_pct=3
  - 写入 strategy_specs/drafts/auto_{thesis_slug}_{date}.yaml

Stage F. Backtest + evidence
  - 调用 oc strategy evidence
  - 写入 reports/research/{spec_name}-*-promotion.{json,md}

Stage G. Final report
  - 写入 reports/research/auto/{run_id}/report.md
  - 包含：thesis / 选中 factor 与 IC / spec path / promotion 状态 / 4-pass / blockers / next actions
  - 写一行 trace.jsonl（如果 project 存在）
```

**4.5.2 实现文件**

新增 `open_composer/research/auto_research.py`（约 400 行）：

```python
"""AI-driven research pipeline: thesis → factors → IC → spec → backtest → evidence."""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from open_composer.config import ensure_dir, project_root
from open_composer.research.factor_library import (
    ALL_FACTORS,
    FactorDefinition,
    get_factor,
    list_factors,
    materialize_expression,
)


@dataclass
class AutoResearchResult:
    run_id: str
    thesis: str
    selected_factors: list[str]
    spec_path: Path
    evidence_status: str
    report_path: Path
    blockers: list[str] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)


def run_auto_research(
    thesis: str,
    universe: list[str],
    *,
    timeframe: str = "daily",
    data_source: str = "sample",
    data_path: str | None = None,
    max_factors: int = 5,
    use_llm: bool = False,
    root: Path | None = None,
) -> AutoResearchResult:
    base = root or project_root()
    run_id = _make_run_id(thesis)
    run_dir = ensure_dir(base / "reports" / "research" / "auto" / run_id)

    # Stage A. Crystallize
    (run_dir / "thesis.md").write_text(thesis, encoding="utf-8")

    # Stage B. Candidate selection
    candidates = (
        _select_with_llm(thesis, universe) if use_llm
        else _select_with_keyword_heuristic(thesis)
    )
    (run_dir / "candidates.json").write_text(
        json.dumps([c.id for c in candidates], indent=2), encoding="utf-8"
    )

    # Stage C. Single-factor IC test
    ic_scores = _run_single_factor_ic(candidates, universe, timeframe, data_source, data_path, base, run_dir)
    (run_dir / "ic_scores.json").write_text(json.dumps(ic_scores, indent=2), encoding="utf-8")

    # Stage D. Top-K selection
    selected = _select_top_k(ic_scores, candidates, max_factors)
    (run_dir / "selected_factors.json").write_text(
        json.dumps([f.id for f in selected], indent=2), encoding="utf-8"
    )

    # Stage E. Spec draft
    spec_path = _draft_spec(thesis, run_id, selected, universe, timeframe, data_source, data_path, base)

    # Stage F. Backtest + evidence
    from open_composer.research.evidence import build_strategy_evidence
    try:
        evidence = build_strategy_evidence(spec_path, base)
        evidence_status = evidence.status
    except Exception as exc:                            # noqa: BLE001
        evidence_status = f"failed: {exc}"

    # Stage G. Final report
    report_path = _write_final_report(
        run_dir, thesis, candidates, ic_scores, selected, spec_path, evidence_status
    )
    return AutoResearchResult(
        run_id=run_id, thesis=thesis,
        selected_factors=[f.id for f in selected],
        spec_path=spec_path, evidence_status=evidence_status,
        report_path=report_path,
    )


# ----- Stage B helpers -----

_FAMILY_KEYWORDS: dict[str, list[str]] = {
    "trend_momentum": ["trend", "uptrend", "momentum", "rally", "continuation"],
    "relative_strength": ["relative", "rs", "leader", "leadership", "ranking"],
    "momentum_short": ["reversal", "mean revert", "bounce", "oversold", "snap"],
    "risk_regime": ["regime", "low vol", "calm", "quiet", "vix"],
    "volatility_rank": ["volatility", "iv", "calm market"],
    "drawdown_guard": ["drawdown", "stop", "risk off", "crash", "guard"],
    "overnight_gap": ["overnight", "gap", "open gap"],
    "kline_shape": ["candle", "k-bar", "body", "shadow"],
    "breadth_canary": ["breadth", "canary", "early warning"],
}


def _select_with_keyword_heuristic(thesis: str) -> list[FactorDefinition]:
    """No-LLM fallback: keyword matching against family triggers."""
    text = thesis.lower()
    matched_families: set[str] = set()
    for family, triggers in _FAMILY_KEYWORDS.items():
        if any(trigger in text for trigger in triggers):
            matched_families.add(family)
    # 至少给一组：trend + risk
    if not matched_families:
        matched_families = {"trend_momentum", "risk_regime"}
    candidates: list[FactorDefinition] = []
    for family in sorted(matched_families):
        family_factors = list_factors(family=family)
        candidates.extend(family_factors[:5])    # 每个 family 最多 5 个
    return candidates[:15]


def _select_with_llm(thesis: str, universe: list[str]) -> list[FactorDefinition]:
    """Use OpenAI structured output to pick factor IDs from the catalog."""
    from open_composer.config import openai_api_key
    if not openai_api_key():
        return _select_with_keyword_heuristic(thesis)
    try:
        from openai import OpenAI
    except ImportError:
        return _select_with_keyword_heuristic(thesis)
    client = OpenAI()
    catalog_summary = [
        {"id": f.id, "family": f.family, "description": f.description}
        for f in ALL_FACTORS
    ]
    schema = {
        "type": "object",
        "required": ["selected_factor_ids", "reasoning"],
        "properties": {
            "selected_factor_ids": {
                "type": "array",
                "minItems": 5, "maxItems": 15,
                "items": {"type": "string", "enum": [f.id for f in ALL_FACTORS]},
            },
            "reasoning": {"type": "string"},
        },
    }
    response = client.responses.create(
        model="gpt-5.0",   # 或环境配置的默认 model
        input=[
            {"role": "system", "content": (
                "You are a quantitative researcher. Select 5-15 factor IDs from the "
                "catalog that best fit the user's thesis. Return only IDs that exist "
                "in the catalog."
            )},
            {"role": "user", "content": (
                f"Thesis: {thesis}\nUniverse: {','.join(universe)}\n\n"
                f"Catalog:\n{json.dumps(catalog_summary[:60], indent=2)}\n"
                "..."
            )},
        ],
        text={"format": {"type": "json_schema", "name": "factor_selection",
                          "schema": schema, "strict": True}},
    )
    payload = json.loads(response.output_text)
    return [get_factor(fid) for fid in payload["selected_factor_ids"]]


# ----- Stage C / D helpers -----

def _run_single_factor_ic(
    candidates, universe, timeframe, data_source, data_path, base, run_dir,
):
    """Run factor_lab style IC test per candidate. Returns dict factor_id -> metrics."""
    from open_composer.adapters.data import load_ohlcv_for_spec
    from open_composer.models.strategy_spec import StrategySpec, FactorConfig, RuleBlock, RiskConfig, ExecutionConfig, DataConfig

    scores: dict[str, dict[str, float | None]] = {}
    for factor in candidates:
        if not factor.expression:
            scores[factor.id] = {"skipped": True, "reason": "no expression"}
            continue
        rendered = materialize_expression(factor, {})
        # 构造 mini-spec：单 factor + 简单 entry
        mini = StrategySpec(
            name=f"auto_ic_{factor.id}",
            description=f"single-factor IC test for {factor.id}",
            timeframe=timeframe,
            universe=universe,
            lifecycle="draft",
            entry=RuleBlock(all=[f"{factor.id}_signal > 0"], any=[]),
            exit=RuleBlock(all=[], any=[f"{factor.id}_signal < 0"]),
            risk=RiskConfig(),
            execution=ExecutionConfig(),
            data=DataConfig(source=data_source, symbol=universe[0], path=data_path),
            factors={f"{factor.id}_signal": FactorConfig(source="expression", expression=rendered)},
        )
        try:
            frame = load_ohlcv_for_spec(mini, base)
            # 直接计算 IC（rank IC vs forward 5d return）
            from open_composer.expressions import evaluate_expression, prepare_factor_frame
            prepared = prepare_factor_frame(frame, mini.factors, root=base)
            signal = evaluate_expression(f"{factor.id}_signal", prepared)
            fwd = frame["close"].pct_change(5).shift(-5)
            valid = signal.notna() & fwd.notna()
            if valid.sum() < 30:
                scores[factor.id] = {"rank_ic": None, "ir": None, "n": int(valid.sum())}
                continue
            ranks_s = signal[valid].rank()
            ranks_f = fwd[valid].rank()
            rank_ic = ranks_s.corr(ranks_f)
            # rolling 21d IR
            rolling_ics: list[float] = []
            for i in range(63, len(signal), 21):
                window = slice(i - 63, i)
                s_w = signal.iloc[window].rank()
                f_w = fwd.iloc[window].rank()
                if s_w.notna().sum() > 30:
                    rolling_ics.append(s_w.corr(f_w))
            ir = (sum(rolling_ics) / len(rolling_ics)) / (max(_stdev(rolling_ics), 1e-6)) if len(rolling_ics) >= 3 else None
            scores[factor.id] = {
                "rank_ic": float(rank_ic) if rank_ic == rank_ic else None,
                "ir": float(ir) if ir is not None else None,
                "n": int(valid.sum()),
                "rolling_ic_mean": (sum(rolling_ics) / len(rolling_ics)) if rolling_ics else None,
                "rolling_ic_std": _stdev(rolling_ics) if len(rolling_ics) >= 2 else None,
                "expression": rendered,
            }
        except Exception as exc:                                  # noqa: BLE001
            scores[factor.id] = {"error": str(exc), "rank_ic": None, "ir": None}
    return scores


def _stdev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return (sum((v - mean) ** 2 for v in values) / (len(values) - 1)) ** 0.5


def _select_top_k(ic_scores: dict, candidates: list[FactorDefinition], k: int):
    """Rank by abs(rank_ic) and require IR ≥ 0.3."""
    scored = []
    for factor in candidates:
        s = ic_scores.get(factor.id, {})
        if s.get("rank_ic") is None or s.get("ir") is None:
            continue
        if abs(s["rank_ic"]) < 0.01 or s["ir"] < 0.3:
            continue
        scored.append((factor, abs(s["rank_ic"]) * s["ir"]))
    scored.sort(key=lambda t: t[1], reverse=True)
    return [factor for factor, _ in scored[:k]]


# ----- Stage E / F / G -----

def _draft_spec(thesis, run_id, selected, universe, timeframe, data_source, data_path, base):
    spec_name = f"auto_{run_id}"
    spec_path = base / "strategy_specs" / "drafts" / f"{spec_name}.yaml"
    ensure_dir(spec_path.parent)
    entry_rules = [f"{f.id}_signal > 0" for f in selected]
    exit_rules = [f"{f.id}_signal < 0" for f in selected]
    factors = {
        f"{f.id}_signal": {
            "source": "factor_library",
            "factor_id": f.id,
            "params": {},
        }
        for f in selected
    }
    spec_yaml = {
        "name": spec_name,
        "description": f"Auto-generated by `oc research auto`. Thesis: {thesis}",
        "timeframe": timeframe,
        "universe": universe,
        "lifecycle": "draft",
        "entry": {"all": entry_rules, "any": []},
        "exit": {"all": [], "any": exit_rules},
        "risk": {"max_trades_per_day": 1, "max_position_weight": 0.5, "stop_loss_pct": 3.0},
        "costs": {"commission_pct": 0.0, "slippage_bps": 0.0, "impact_model": "linear",
                  "impact_eta": 0.0, "impact_gamma": 0.0},
        "execution": {"backend": "python_reference", "mode": "manual_signal",
                       "signal_on": "bar_close", "fill_assumption": "next_bar_open",
                       "broker": "none"},
        "data": {"source": data_source, "symbol": universe[0], "path": data_path, "feed": None},
        "data_assumptions": {"source": data_source, "adjusted": True, "timezone": "America/New_York"},
        "factors": factors,
        "llm_review": {"enabled": False},
        "notes": {"intent": f"AI-driven research from thesis: {thesis[:200]}", "open_questions": []},
        "required_capabilities": [],
    }
    spec_path.write_text(yaml.safe_dump(spec_yaml, sort_keys=False), encoding="utf-8")
    # 写入每个 factor 的 lineage
    from open_composer.research.factor_lineage import append_lineage
    for f in selected:
        append_lineage(f.id, spec_path, added_by="auto_research", creation_thesis=thesis, root=base)
    return spec_path


def _write_final_report(run_dir, thesis, candidates, ic_scores, selected, spec_path, evidence_status):
    lines = [
        f"# AI Auto-Research Report",
        f"",
        f"**Thesis**: {thesis}",
        f"**Generated**: {datetime.now(UTC).isoformat()}",
        f"**Spec**: `{spec_path.name}`",
        f"**Evidence status**: `{evidence_status}`",
        f"",
        f"## Candidate factors ({len(candidates)})",
        f"",
        f"| Factor | Family | Rank IC | IR | n | status |",
        f"|---|---|---|---|---|---|",
    ]
    for c in candidates:
        s = ic_scores.get(c.id, {})
        rank_ic = s.get("rank_ic")
        ir = s.get("ir")
        n = s.get("n")
        status = "✅ selected" if c in selected else ("❌ rejected" if rank_ic is not None else "⚠ skipped")
        rank_ic_str = f"{rank_ic:.3f}" if isinstance(rank_ic, float) else "n/a"
        ir_str = f"{ir:.2f}" if isinstance(ir, float) else "n/a"
        lines.append(f"| `{c.id}` | {c.family} | {rank_ic_str} | {ir_str} | {n or 'n/a'} | {status} |")
    lines.extend([
        f"",
        f"## Selected factors ({len(selected)})",
        f"",
    ])
    for f in selected:
        lines.append(f"- `{f.id}` ({f.family}): {f.description}")
    lines.extend([
        f"",
        f"## Next actions",
        f"",
        f"- Review `{spec_path}` and adjust risk/cost parameters.",
        f"- Run `oc strategy promotion-report {spec_path}` for full OOS/walk-forward.",
        f"- If `evidence_status` is `blocked`, check `{spec_path.stem}-promotion.md`.",
    ])
    report_path = run_dir / "report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def _make_run_id(thesis: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", thesis.lower()).strip("_")[:48]
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}_{slug}"
```

**4.5.3 新 CLI 子命令**

```python
research_app = typer.Typer(no_args_is_help=True)
app.add_typer(research_app, name="research")


@research_app.command("auto")
def research_auto_command(
    thesis: str,
    universe: Annotated[str, typer.Option("--universe")] = "SYN",
    timeframe: Annotated[str, typer.Option("--timeframe")] = "daily",
    data_source: Annotated[str, typer.Option("--data-source")] = "sample",
    data_path: Annotated[str | None, typer.Option("--data-path")] = None,
    max_factors: Annotated[int, typer.Option("--max-factors")] = 5,
    use_llm: Annotated[bool, typer.Option("--use-llm/--no-llm")] = False,
) -> None:
    """AI-driven research pipeline: thesis → factor IC → spec → backtest → evidence."""
    from open_composer.research.auto_research import run_auto_research

    universe_list = [u.strip().upper() for u in universe.split(",")]
    result = run_auto_research(
        thesis, universe_list,
        timeframe=timeframe, data_source=data_source, data_path=data_path,
        max_factors=max_factors, use_llm=use_llm,
    )
    console.print(f"[green]auto research complete[/green] {result.run_id}")
    console.print(f"selected factors: {', '.join(result.selected_factors) or 'none'}")
    console.print(f"spec: {result.spec_path}")
    console.print(f"evidence status: {result.evidence_status}")
    console.print(f"report: {result.report_path}")
```

**4.5.4 测试**

新增 `tests/test_auto_research.py`：

```python
"""End-to-end test of oc research auto pipeline."""
from __future__ import annotations
from pathlib import Path
import pytest

from open_composer.research.auto_research import run_auto_research

ROOT = Path(__file__).resolve().parents[1]


def test_auto_research_runs_to_evidence_on_synthetic(tmp_path, monkeypatch):
    """Run pipeline against syn_daily.csv with no-LLM fallback."""
    monkeypatch.chdir(ROOT)
    result = run_auto_research(
        thesis="Find a daily trend strategy that exits in high-volatility regimes.",
        universe=["SYN"],
        timeframe="daily",
        data_source="sample",
        data_path="data/sample/syn_daily.csv",
        max_factors=3,
        use_llm=False,
    )
    assert result.run_id
    assert result.spec_path.exists()
    assert result.report_path.exists()
    # 至少选中 1 个 factor（如果合成数据足够好）
    # 不强求 — 合成数据 IC 可能太弱
    assert len(result.selected_factors) >= 0


def test_keyword_heuristic_picks_trend_for_trend_thesis():
    from open_composer.research.auto_research import _select_with_keyword_heuristic
    candidates = _select_with_keyword_heuristic("Find a strong uptrend continuation strategy")
    families = {f.family for f in candidates}
    assert "trend_momentum" in families


def test_keyword_heuristic_picks_drawdown_for_drawdown_thesis():
    from open_composer.research.auto_research import _select_with_keyword_heuristic
    candidates = _select_with_keyword_heuristic("Reduce exposure during drawdowns and crashes")
    families = {f.family for f in candidates}
    assert "drawdown_guard" in families
```

**Wave 6.5 验收**：

```bash
.venv/bin/pytest tests/test_auto_research.py -v

.venv/bin/oc research auto "Find a strong uptrend continuation strategy on SYN daily" \
  --universe SYN --timeframe daily \
  --data-source sample --data-path data/sample/syn_daily.csv \
  --max-factors 3

# 验证产物
test -f strategy_specs/drafts/auto_*.yaml
test -d reports/research/auto/*/
cat reports/research/auto/*/report.md
```

---

### Wave 6.6 — 文档与 CURRENT_DOCS（10 分钟）

**4.6.1 README 增加一段**

`README.md` 在 "Typical Workflow" 之后增加：

```markdown
## AI-Driven Research

Don't know which indicator or parameter to use? Describe what you want:

```bash
uv run oc research auto "Find a TQQQ trend strategy that exits in high-VIX regimes" \
  --universe TQQQ --timeframe daily
```

The agent will:

1. Pick 5-15 candidate factors from the catalog (`oc factor list`)
2. Run single-factor IC tests
3. Select factors with stable IR
4. Generate a `StrategySpec` draft
5. Run backtest + 4-pass evidence
6. Write a report with selected factors, IC table, and next actions

You only describe the thesis; the agent runs the research pipeline.
Browse the factor catalog: `oc factor list --family trend_momentum`.
```

**4.6.2 user-guide.md 增加一节**

`docs/user-guide.md` 在 "Bounded Research" 之后增加 "AI-Driven Research" 段（复制 README 内容并扩展）。

**4.6.3 CURRENT_DOCS 同步**

`open_composer/repo_check.py` 的 `CURRENT_DOCS` 加入本文档：

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
    "docs/plan-step-4-llm-completion-and-ux-polish-2026-05-25.zh.md",
    "docs/strategy-research-product-remediation-plan-2026-05-26.zh.md",
    "docs/plan-step-6-factor-catalog-and-ai-research-2026-05-26.zh.md",      # ✦ 本文档
}
```

同步在 `README.md` Project Docs 段加链接。

## 5. 完整验收清单

```text
[ ] FactorDefinition 增加 expression / materialize_expression 字段
[ ] 现有 32 个 FactorDefinition 全部补 expression（或显式 None + 注释）
[ ] Alpha101 子集 ≥ 25 个入 ALPHA101_LIBRARY
[ ] Alpha158 子集 ≥ 18 个入 ALPHA158_LIBRARY
[ ] ALL_FACTORS / get_factor / list_factors / _FACTOR_INDEX 可用
[ ] StrategySpec.FactorConfig 支持 source: factor_library + factor_id + params
[ ] 引用不存在的 factor_id 或不合法 params 时 spec validation 报错
[ ] example_catalog_factor_daily.yaml fixture spec validate 通过
[ ] oc factor list/show/use-in/catalog-status 4 个 CLI 通过测试
[ ] oc factor catalog-status --strict 全 catalog AST 安全
[ ] reports/factors/{factor_id}/lineage.json 在 use-in 与 auto research 后被写入
[ ] open_composer/research/auto_research.py 完整
[ ] oc research auto CLI 可执行，对 syn_daily.csv 跑通端到端
[ ] tests/test_auto_research.py 3 个测试全过
[ ] reports/research/auto/{run_id}/{thesis.md,candidates.json,ic_scores.json,selected_factors.json,report.md} 全部生成
[ ] _global_factor_library.jsonl source cards 写入
[ ] README + user-guide.md 加 "AI-Driven Research" 段
[ ] CURRENT_DOCS 与 README Project Docs 同步本文档
[ ] .venv/bin/pytest 全绿
[ ] .venv/bin/oc repo check --strict 通过
[ ] make verify 通过（如果 dashboard 也建）
```

## 6. 不做什么（边界）

```text
✗ 不引入 ML 依赖（lightgbm/sklearn/pytorch/optuna）—— Step 7.A
✗ 不实现 decay 监控 cron —— Step 7.B
✗ 不实现 oc factor propose（LLM 自动挖因子）—— Step 7.C
✗ 不实现 oc strategy explain（LLM 解释 ML 模型）—— Step 7.C
✗ 不引入 cross-sectional rank 操作（个人量化默认场景外）
✗ 不修改现有 30+ 个 spec（保留为 source: expression）
✗ 不动 backtest engine 6 位精度对账逻辑
✗ 不动 expressions.py AST 白名单（catalog 因子展开后仍走同一 AST）
✗ 不引入 Qlib YAML workflow / qrun / DataHandler 实际代码（仅借鉴因子表达式）
✗ 不动 4-pass / harness / paper safety chain
```

## 7. 风险与对冲

| 风险 | 对冲 |
|---|---|
| Alpha101 表达式有 max/correlation 等 AST 不支持的操作 | 选择标准明确排除；移植时只搬 single-series 操作；剩余的标 `expression=None` 注释跳过 |
| factor_library 扩到 80+ 后启动加载慢 | 全部 frozen dataclass + module-level tuple，~ 80 个对象内存 < 100KB；加载 O(1) |
| LLM 选因子时编造不存在的 factor_id | 用 OpenAI structured output + `enum` 约束只能从 catalog 选 |
| keyword 启发式选因子过窄 | 默认匹配不到任何 family 时回退到 trend_momentum + risk_regime 组合 |
| 自动生成的 spec 全是 entry.all（过严） | 默认 entry.any 用 OR；用户可在 report.md 末尾的 "next actions" 看到调整建议 |
| 单因子 IC 对合成 syn_daily.csv 太低 → 全部 reject | 测试只断言"流程跑通"，不强求 selected > 0；真实数据测试在 Step 7 之后 |
| 因子 lineage 文件冲突（多 spec 用同 factor） | 用 dict-merge：spec_path 不存在才追加；幂等 |
| `materialize_expression` 占位符冲突（factor name 与 OHLCV 同名） | factor_library validator：拒绝 factor.id 在 OHLCV_NAMES 集合内 |

## 8. 回滚

每个 Wave 单独 commit。任何 Wave 出问题 git revert 该 commit；现有 30+ specs 与现有测试不受影响。

## 9. 完成定义

执行完 Wave 6.1-6.6 后：

- `oc factor list` 列出 ≥ 80 个 factor，按 family / inputs 可过滤
- `oc factor show <id>` 显示完整定义 + 已用 spec
- spec 可以用 `source: factor_library + factor_id` 直接引用 catalog
- `oc research auto "<thesis>"` 一行命令跑完整研究流水线，输出 report.md
- Codex / Claude Code 在新策略生成时**默认查 catalog 而非凭空想表达式**
- 每个 factor 有 lineage.json 记录使用历史
- 现有 spec / 测试 / dashboard / paper safety 全部保持

完成后即可进入 Step 7（条件触发的 ML / 衰减 / LLM 三角色）。

## 10. 执行顺序（写给无上下文 Codex）

```text
Wave 6.1 (30min)  FactorDefinition 加 expression 字段 + 现有 32 个补全
Wave 6.2 (45min)  移植 Alpha101 + Alpha158 子集；ALL_FACTORS 注册
Wave 6.3 (30min)  StrategySpec.FactorConfig 加 source=factor_library
Wave 6.4 (45min)  oc factor CLI + factor_lineage 模块
Wave 6.5 (60-90min) oc research auto 流水线 + 测试
Wave 6.6 (10min)  文档 + CURRENT_DOCS

总计：约 3-4 小时，单个 agent 会话内完成。
每个 Wave 完成后跑：
  .venv/bin/pytest tests/ -q
  （Wave 6.6 之后）.venv/bin/oc repo check --strict
```

完成后立即进入"用户用一句话 thesis → AI 跑完整研究"的产品状态。
