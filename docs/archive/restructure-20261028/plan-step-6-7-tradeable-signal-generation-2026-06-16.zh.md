# Open Composer Step 6.7：auto research 可交易信号生成修复

日期：2026-06-16
执行者：Codex / Claude Code
前置：Step 6（因子库 + `oc research auto`）、Step 6.5（selection/IC/data 修复）、Step 6.6（证据链加固）均已完成
后续：（按真实数据策略效果决定）Step 7.A/B/C

## 0. 一句话目标

修 `oc research auto` 生成的 StrategySpec 在真实数据上 **0 signals / 0 trades** 的问题。根因是 `_draft_spec` 的信号组合逻辑（全 AND + 不看 IC 符号 + 裸 `> 0` 阈值）。**这是从"流水线跑通"到"产出可评估的可交易策略"的最后一公里**，范围明确、单点、可快速验证（修完跑一个真实 QQQ thesis 看 signal 数 > 5 即可）。

## 1. 背景（无上下文也能看懂）

Open Composer 是个人 AI 量化策略工作台。`oc research auto "<thesis>"` 让 AI 自动跑「选因子 → 单因子 IC → 生成 StrategySpec → 回测 → evidence」流水线。

Step 6.6 完成后，真实 Alpaca 数据已经能跑通且通过 research strict_data gate（`acquisition_tier=research_strict`，promotion 从 blocked → warning）。**这是真实进步**。

**但暴露了一个普遍且阻塞性的问题**：在真实 QQQ daily 数据（505 bars）上，8 个真实数据 run 里 7 个是 **0 signals / 0 trades**，promotion 报 `data_quality: low signal count: 0 signals is below the 5-signal minimum`。

### 根因（已定位，与数据无关，是 `_draft_spec` 的信号生成逻辑）

以 `reports/research/auto/20260608T173302Z_trend_continuation_p0_refresh_smoke_on_qqq_daily` 为例，selected 3 个因子，生成的 spec 是：

```yaml
entry:
  all:
  - volatility_rank_20_252_signal > 0
  - drawdown_guard_20_60_signal > 0
  - alpha101_007_price_above_sma_10d_signal > 0
  any: []
exit:
  all: []
  any:
  - volatility_rank_20_252_signal < 0   # 等等
```

对应的真实 IC（来自该 run 的 `ic_scores.json`）：

```text
volatility_rank_20_252         rank_ic = +0.1833   ← 很强
drawdown_guard_20_60           rank_ic = -0.0737   ← 负
alpha101_007_price_above_sma   rank_ic = -0.0419   ← 负
```

三个缺陷：

1. **entry 用全 `all`（AND）**：要求 3 个因子 signal 同时 `> 0` —— 真实数据上几乎从不同时成立 → 0 signal。
2. **不按 IC 符号定方向**：`drawdown_guard` rank IC 是 **负的**（因子值高 → 未来收益低），spec 却用 `> 0`，方向完全用反。
3. **裸 `> 0` 阈值**：因子 expression 多是连续值（如 `stddev(close, 20)` 永远 > 0），`> 0` 不区分因子语义，没有"偏离常态多少才算信号"的概念。

4. **架构缺陷**：`_draft_spec`（`auto_research.py:584`）**根本没有接收 `ic_scores` 参数**（调用点 `auto_research.py:164` 没传），所以它没有任何信息来按 IC 符号定方向。

## 2. 目标 / 非目标

### 目标

1. `_draft_spec` 接收 `ic_scores`，按每个因子的 **rank IC 符号决定方向**（正 IC → 因子高时做多；负 IC → 因子低时做多）。
2. 用 **zscore 标准化 + 阈值** 替代裸 `> 0`，让不同量纲的连续因子可比、有"偏离常态"语义。
3. 用 **方向化 composite score（多数票）** 替代全 AND，保证真实数据上能产出非空信号。
4. 跳过 rank IC 缺失（`rank_ic = None` / diagnostic）或过弱（`|rank IC| < 0.02`）的因子，不纳入 composite。
5. **验收硬指标**：重跑真实 QQQ daily thesis，signal 数 **> 5**（不再 0），promotion 的 `low signal count` blocker 消失。

### 非目标（明确不做）

- 不引入 ML（留给 Step 7.A）。
- 不改 factor_library catalog 因子定义。
- 不改 4-pass / harness / paper safety / strict_data tier 逻辑（Step 6.6 已正确，不动）。
- 不改 backtest engine / promotion gate。
- 不动 AST 安全白名单（zscore 已在白名单内，无需扩展）。
- 不追求"策略赚钱"——本步骤只保证"产出非空、方向正确、可被 promotion 评估的策略"。赚不赚钱由后续真实数据研究决定。
- 不改 `_select_top_k` 的因子选择逻辑（它已经在 Step 6.5 做对了 IC×stability×coverage 排序 + 跨 family）。

## 3. 当前状态扫描（精确行号）

```text
open_composer/research/auto_research.py
  L94    ic_scores = _run_single_factor_ic(...)        # ic_scores 在这里算出，含每个 factor 的 rank_ic
  L106   selected = _select_top_k(ic_scores, candidates, max_factors)
  L164   spec_path = _draft_spec(                       # ⚠ 调用点：没有传 ic_scores
           thesis=..., run_id=..., selected=selected, universe=..., ...)
  L584   def _draft_spec(*, thesis, run_id, selected, universe, timeframe,
                          data_source, data_path, base, zero_cost_smoke=False)
                                                        # ⚠ 签名缺 ic_scores 参数
  L600   factor_names = [_factor_signal_name(f) for f in selected]
  L601-608  factors = { name: {source: factor_library, factor_id, params} }
  L621   "entry": {"all": [f"{name} > 0" ...], "any": []}    # ⚠ 缺陷 1+2+3
  L622   "exit":  {"all": [], "any": [f"{name} < 0" ...]}    # ⚠ 同上
  L1133  def _factor_signal_name(factor) -> str          # name = re.sub(\W,_,id)+"_signal"

open_composer/expressions.py
  L47-56  STATISTICAL_FUNCTIONS 含 "zscore"             # ✅ zscore 可用，无需改白名单
  L217    prepare_factor_frame 支持 factor 间依赖         # ✅ composite 可引用其他 factor signal
                                                          #    (while remaining 渐进解析)

ic_scores 结构（每个 factor.id → dict）：
  {
    "rank_ic": float | None,
    "rank_ic_diagnosis": str | None,
    "coverage_pct": float, "observations": int, "stability_score": float, ...
  }
```

**关键确认**：
- `zscore(series, window)` 已在 `expressions.py` 白名单（`STATISTICAL_FUNCTIONS`），entry rule 与 expression factor 中都可调用。
- `prepare_factor_frame` 用 `while remaining` 渐进解析，支持一个 expression factor 引用另一个 factor 的 signal 列（composite 可以引用 f1_signal/f2_signal）。

## 4. 改动清单（单个 Wave，约 2 小时）

### Wave 6.7.1 — 方向化 composite 信号生成

**4.1 调用点传入 ic_scores**

`auto_research.py:164` 的 `_draft_spec(...)` 调用增加 `ic_scores=ic_scores`：

```python
spec_path = _draft_spec(
    thesis=thesis,
    run_id=run_id,
    selected=selected,
    ic_scores=ic_scores,          # ✦ 新增
    universe=symbols,
    timeframe=timeframe,
    data_source=data_source,
    data_path=data_path,
    base=base,
    zero_cost_smoke=zero_cost_smoke,   # 若该调用点已有此参数则保留
)
```

> 注意：`run_auto_research` 中可能有多个 `_draft_spec` 调用点（如 smoke 路径）。用 `grep -n "_draft_spec(" open_composer/research/auto_research.py` 找出全部，每个都传 `ic_scores`。

**4.2 `_draft_spec` 签名 + 信号生成重写**

```python
# 模块顶部常量
_ZSCORE_WINDOW_BY_TIMEFRAME: dict[str, int] = {
    "daily": 60, "weekly": 26, "4h": 60, "1h": 120,
    "30m": 120, "15m": 120, "5m": 240, "1m": 240,
}
_DEFAULT_ZSCORE_WINDOW = 60
_COMPOSITE_ENTRY_THRESHOLD = 0.3      # composite z-score 进场阈值
_COMPOSITE_EXIT_THRESHOLD = -0.3      # 反向出场阈值
_MIN_ABS_RANK_IC_FOR_SIGNAL = 0.02    # 弱于此的因子不进 composite


def _draft_spec(
    *,
    thesis: str,
    run_id: str,
    selected: list[FactorDefinition],
    ic_scores: dict[str, dict[str, Any]],     # ✦ 新增
    universe: list[str],
    timeframe: str,
    data_source: str,
    data_path: str | None,
    base: Path,
    zero_cost_smoke: bool = False,
) -> Path:
    slug = run_id.lower().replace("-", "_")
    spec_name = f"auto_{slug}"
    spec_path = base / "strategy_specs" / "drafts" / f"{spec_name}.yaml"
    ensure_dir(spec_path.parent)

    factor_names = [_factor_signal_name(factor) for factor in selected]
    factors: dict[str, dict[str, Any]] = {
        name: {"source": "factor_library", "factor_id": factor.id, "params": {}}
        for name, factor in zip(factor_names, selected, strict=True)
    }

    zwin = _ZSCORE_WINDOW_BY_TIMEFRAME.get(timeframe, _DEFAULT_ZSCORE_WINDOW)

    # 方向化：按 rank IC 符号决定每个因子的 oriented z-score 项
    oriented_terms: list[str] = []
    signal_factor_count = 0
    for name, factor in zip(factor_names, selected, strict=True):
        rank_ic = _float_or_none((ic_scores.get(factor.id) or {}).get("rank_ic"))
        if rank_ic is None or abs(rank_ic) < _MIN_ABS_RANK_IC_FOR_SIGNAL:
            # 弱因子 / 无 IC：保留在 factors（供研究可见），但不进 composite 信号
            continue
        sign_prefix = "" if rank_ic >= 0 else "-1 * "
        oriented_terms.append(f"({sign_prefix}zscore({name}, {zwin}))")
        signal_factor_count += 1

    entry_all: list[str] = []
    exit_any: list[str] = []
    if oriented_terms:
        # composite = 方向化项均值；多数因子方向一致且偏离常态时进场
        composite_expr = "(" + " + ".join(oriented_terms) + f") / {len(oriented_terms)}"
        factors["composite_score"] = {"source": "expression", "expression": composite_expr}
        entry_all = [f"composite_score > {_COMPOSITE_ENTRY_THRESHOLD}"]
        exit_any = [f"composite_score < {_COMPOSITE_EXIT_THRESHOLD}"]
    else:
        # 兜底：所有 selected 因子 IC 都缺失/过弱 → 用第一个因子的单边 z-score
        # （保证 spec 合法且非空；promotion 会如实标记弱证据）
        if factor_names:
            first = factor_names[0]
            factors["composite_score"] = {
                "source": "expression",
                "expression": f"zscore({first}, {zwin})",
            }
            entry_all = [f"composite_score > {_COMPOSITE_ENTRY_THRESHOLD}"]
            exit_any = [f"composite_score < {_COMPOSITE_EXIT_THRESHOLD}"]
        else:
            # 没有任何因子（理论上不会发生，_select_top_k 至少返回 1 个）
            entry_all = ["close > sma(close, 20)"]
            exit_any = ["close < sma(close, 20)"]

    parameter_space = {
        f"{name}.{param}": values
        for name, factor in zip(factor_names, selected, strict=True)
        for param, values in factor.default_parameter_space.items()
        if values and all(_is_scalar(item) for item in values)
    }

    spec_yaml: dict[str, Any] = {
        "name": spec_name,
        "description": f"Auto-generated by oc research auto. Thesis: {thesis}",
        "timeframe": timeframe,
        "universe": universe,
        "lifecycle": "draft",
        "entry": {"all": entry_all, "any": []},
        "exit": {"all": [], "any": exit_any},
        "risk": {"max_trades_per_day": 1, "max_position_weight": 0.5, "stop_loss_pct": 3.0},
        "costs": {
            "commission_pct": 0.0,
            "slippage_bps": 0.0 if zero_cost_smoke else _default_slippage_bps(timeframe),
            "impact_model": "linear",
            "impact_eta": 0.0,
            "impact_gamma": 0.0,
        },
        "execution": {
            "backend": "python_reference",
            "mode": "manual_signal",
            "signal_on": "bar_close",
            "fill_assumption": "next_bar_open",
            "broker": "none",
        },
        "data": {"source": data_source, "symbol": universe[0], "path": data_path, "feed": None},
        "data_assumptions": {"source": data_source, "adjusted": True, "timezone": "America/New_York"},
        "factors": factors,
        "llm_review": {"enabled": False},
        "notes": {
            "intent": f"AI-driven research from thesis: {thesis}",
            "open_questions": [],
            "signal_construction": (
                f"Oriented composite z-score over {signal_factor_count} factors with "
                f"|rank_ic| >= {_MIN_ABS_RANK_IC_FOR_SIGNAL}; window={zwin}; "
                f"entry>{_COMPOSITE_ENTRY_THRESHOLD}, exit<{_COMPOSITE_EXIT_THRESHOLD}."
            ),
        },
        "research_design": {
            # ... 保留现有 research_design 内容不变 ...
        },
        # ... 其余字段保留 ...
    }
    # ... 写文件逻辑保留 ...
```

> **实现要点**：
> - composite 用 **方向化 z-score 均值 + 阈值**，不是全 AND。多数因子方向一致且偏离常态 0.3 个标准差才进场。
> - `composite_score` 作为 `source: expression` factor，引用各 `<factor>_signal` 列（`prepare_factor_frame` 渐进解析支持）。
> - 弱因子（`|rank_ic| < 0.02`）保留在 `factors`（供 factor lab / 研究可见），但**不进 composite 信号**——避免噪声因子稀释信号。
> - 兜底分支保证即使全部因子 IC 缺失也产出合法非空 spec。

**4.3 entry rule 表达式安全性自检**

`composite_score` expression 形如 `((zscore(f1, 60)) + (-1 * zscore(f2, 60))) / 2`，确认它通过 `assert_expression_safe`：
- `zscore` ∈ ALLOWED_FUNCTIONS ✅
- `+` `-` `*` `/` ∈ ALLOWED_AST_NODES（Add/Sub/Mult/Div）✅
- `-1 * ...` 用 BinOp（不是 UnaryOp），更稳 ✅

实现后用一条 spec 跑 `oc spec validate` 确认。

## 5. 测试

**5.1 新增 `tests/test_auto_research_signal_generation.py`**

```python
"""Step 6.7: auto research must produce tradeable (non-empty, IC-oriented) signals."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.research.auto_research import _draft_spec
from open_composer.research.factor_library import get_factor

ROOT = Path(__file__).resolve().parents[1]


def _fake_ic(rank_ic: float) -> dict:
    return {"rank_ic": rank_ic, "coverage_pct": 95.0, "observations": 500, "stability_score": 0.1}


def test_draft_spec_orients_by_ic_sign(tmp_path):
    # 一个正 IC、一个负 IC 因子
    pos = get_factor("volatility_rank_20_252")
    neg = get_factor("drawdown_guard_20_60")
    ic_scores = {pos.id: _fake_ic(0.18), neg.id: _fake_ic(-0.07)}
    spec_path = _draft_spec(
        thesis="orientation test", run_id="t_orient", selected=[pos, neg],
        ic_scores=ic_scores, universe=["SYN"], timeframe="daily",
        data_source="sample", data_path="data/sample/syn_daily.csv", base=ROOT,
    )
    spec = load_strategy_spec(spec_path)
    composite_expr = spec.factors["composite_score"].expression
    pos_name = f"{pos.id}_signal" if not pos.id.endswith("_signal") else pos.id
    # 正 IC 因子项不带 -1；负 IC 因子项带 -1
    assert "-1 * zscore(" in composite_expr, "negative-IC factor must be sign-flipped"
    assert "zscore(" in composite_expr
    # entry 不再是裸 "> 0" 全 AND
    assert spec.entry.all == ["composite_score > 0.3"]
    assert spec.entry.any == []
    spec_path.unlink(missing_ok=True)


def test_draft_spec_skips_weak_factors(tmp_path):
    strong = get_factor("volatility_rank_20_252")
    weak = get_factor("drawdown_guard_20_60")
    ic_scores = {strong.id: _fake_ic(0.18), weak.id: _fake_ic(0.005)}  # weak < 0.02
    spec_path = _draft_spec(
        thesis="weak skip", run_id="t_weak", selected=[strong, weak],
        ic_scores=ic_scores, universe=["SYN"], timeframe="daily",
        data_source="sample", data_path="data/sample/syn_daily.csv", base=ROOT,
    )
    spec = load_strategy_spec(spec_path)
    composite_expr = spec.factors["composite_score"].expression
    # 只有强因子进 composite（弱因子被跳过）
    assert composite_expr.count("zscore(") == 1
    spec_path.unlink(missing_ok=True)


def test_draft_spec_produces_signals_on_synthetic(tmp_path, monkeypatch):
    """End-to-end: generated spec must produce >= 5 signals on syn_daily (1000 bars)."""
    monkeypatch.chdir(ROOT)
    from open_composer.adapters.data import load_ohlcv_for_spec
    from open_composer.engines.backtest_engine import backtest_frame

    strong = get_factor("volatility_rank_20_252")
    ic_scores = {strong.id: _fake_ic(0.18)}
    spec_path = _draft_spec(
        thesis="signal count", run_id="t_signals", selected=[strong],
        ic_scores=ic_scores, universe=["SYN"], timeframe="daily",
        data_source="sample", data_path="data/sample/syn_daily.csv", base=ROOT,
    )
    spec = load_strategy_spec(spec_path)
    frame = load_ohlcv_for_spec(spec, ROOT)
    artifacts = backtest_frame(spec, frame, root=ROOT, run_id_value="t_signals")
    assert artifacts.run.signals >= 5, (
        f"expected >= 5 signals from oriented composite, got {artifacts.run.signals}"
    )
    spec_path.unlink(missing_ok=True)
```

**5.2 更新现有测试**

`grep -rn '_signal > 0\|"all": \[f"{name}' tests/` 找出断言旧 entry 格式（`name > 0` 全 AND）的测试，更新为 composite 格式。可能涉及：
- `tests/test_factor_catalog_and_auto_research.py`
- `tests/test_auto_research_selection.py`（如有断言 entry 结构）

## 6. 验收清单

```text
[ ] _draft_spec 签名增加 ic_scores 参数
[ ] auto_research.py 所有 _draft_spec 调用点都传 ic_scores（grep 确认无遗漏）
[ ] 正 IC 因子项不带 -1；负 IC 因子项带 "-1 * zscore(...)"
[ ] |rank_ic| < 0.02 的因子被跳过，不进 composite
[ ] composite_score 作为 source=expression factor 写入 spec.factors
[ ] entry.all = ["composite_score > 0.3"]；exit.any = ["composite_score < -0.3"]
[ ] composite expression 通过 assert_expression_safe（oc spec validate 验证）
[ ] tests/test_auto_research_signal_generation.py 3 个 test 全过
[ ] 现有断言旧 entry 格式的测试已更新
[ ] .venv/bin/pytest tests/ -q 全绿
[ ] .venv/bin/oc repo check --strict 通过

★ 硬验收（真实数据，必须做）：
[ ] 重跑真实 QQQ thesis：
    .venv/bin/oc research auto "Trend continuation on QQQ daily." \
      --universe QQQ --timeframe daily --data-source alpaca --max-factors 5
[ ] 该 run 的 report.md 中 signal 数 > 5（不再 0）
[ ] promotion 的 "low signal count: 0 signals" blocker 消失
[ ] data_profile.json 仍显示 acquisition_tier=research_strict（6.6 不被破坏）
```

## 7. 不做什么

```text
✗ 不引入 ML / Optuna（Step 7.A）
✗ 不改 factor_library catalog 因子定义
✗ 不改 _select_top_k 选择逻辑（Step 6.5 已正确）
✗ 不改 4-pass / harness / paper safety / strict_data tier（Step 6.6 已正确）
✗ 不改 backtest engine / promotion gate
✗ 不扩 AST 白名单（zscore 已可用）
✗ 不为了"产出信号"而放宽 promotion 的 5-signal / 5-trade sanity 阈值
✗ 不追求策略盈利——只保证非空、方向正确、可评估
```

## 8. 风险与对冲

| 风险 | 对冲 |
|---|---|
| composite OR/阈值导致信号过多（过度交易） | `max_trades_per_day=1` 限制 + exit 反向阈值；promotion 的 turnover/cost check 会如实标记，后续可调阈值 |
| zscore window 60 在短数据上 NaN | zscore 在 `expressions.py` 有 `fillna(0)` 保护；syn_daily 1000 bar / QQQ 505 bar 充足 |
| composite expression 引用的 factor signal 未先算 | `prepare_factor_frame` 渐进解析（while remaining）保证依赖顺序；composite 依赖会在被引用 factor 之后求值 |
| 负 IC 用 `-1 * zscore` 是否被 AST 接受 | 用 BinOp（Mult）不是 UnaryOp；`-1` 是 Constant；已在白名单 |
| 所有因子 IC 缺失 → composite 为空 | 兜底分支用第一个因子单边 z-score，再不行用 `close vs sma(close,20)`；保证非空合法 spec |
| 阈值 0.3 对某些 thesis 仍偏严/偏松 | 默认 0.3 是温和值（约 z>0.3 触发 38% 时间）；后续可做成 spec 可配；本步骤不参数化 |
| 真实 QQQ 上即使方向对信号仍少 | 验收只要求 > 5（不是"赚钱"）；若 < 5，降低阈值到 0.2 重试；记录在 report |

## 9. 回滚

单个 Wave 单独 commit。出问题 `git revert` 即回到 Step 6.6 状态（流水线仍跑通，只是回到 0 signal 行为）。

## 10. 完成定义

执行完 Wave 6.7.1 后：

- `oc research auto` 生成的 spec 按因子 rank IC 符号方向化（负 IC 因子不再用反方向）
- entry/exit 用方向化 composite z-score 阈值，不再全 AND 裸 `> 0`
- **真实 QQQ daily thesis 产出 > 5 signals**，promotion 不再被 `low signal count` blocker 卡住
- evidence 从"0 信号空策略"进入"有信号、可被 OOS / walk-forward / 成本 / benchmark family 评估"的状态
- 这时才真正"可以生成可交易策略并迭代"

完成后：用 `oc research auto --data-source alpaca` 跑 5 个不同真实 thesis，用 `oc research compare` 看哪些因子在真实数据上跨 thesis 稳定有 IC（区别于 sample 数据的假信号），据此决定是否触发 Step 7。

## 11. 执行顺序（写给无上下文 Codex）

```text
1. 读本文档 + auto_research.py 的 _draft_spec (L584) 与调用点 (L164)
2. grep -n "_draft_spec(" open_composer/research/auto_research.py  找全部调用点
3. Wave 6.7.1：
   a. _draft_spec 签名加 ic_scores
   b. 所有调用点传 ic_scores
   c. 重写 entry/exit 为方向化 composite（按本文档 §4.2）
   d. 模块常量 _ZSCORE_WINDOW_* / _COMPOSITE_*_THRESHOLD / _MIN_ABS_RANK_IC_FOR_SIGNAL
4. 写 tests/test_auto_research_signal_generation.py（3 个 test）
5. 更新断言旧 entry 格式的现有测试
6. 跑：
   .venv/bin/ruff format . && .venv/bin/ruff check .
   .venv/bin/pytest tests/ -q
   .venv/bin/oc repo check --strict
7. ★ 硬验收：跑真实 QQQ thesis（§6 末），确认 signal > 5
8. commit "Wave 6.7.1 oriented composite signal generation"
9. STOP and report：贴出真实 QQQ run 的 signal 数 + report.md 关键段；
   不要自行启动 Step 7。
```

完成后即从"流水线跑通"进入"可产出可交易策略"。
