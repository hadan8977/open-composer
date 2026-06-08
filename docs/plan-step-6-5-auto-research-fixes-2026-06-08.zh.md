# Open Composer Step 6.5：auto research 流水线修补与真实数据接入

日期：2026-06-08
执行者：Codex / Claude Code
前置：Step 6（因子库 + `oc research auto`）已完成
后续：（按数据决定）Step 7.A / 7.B / 7.C

## 0. 一句话目标

Step 6 落地后跑了 5 个 unique thesis（trend / mean_reversion / volatility / overnight / regime），暴露 4 个真问题。本步骤**一个会话内修完**，让 `oc research auto` 输出真正有用的策略，并接入真实数据让 evidence 可以走出 `strict_data` blocker。**不引入新概念，纯修补 G1 已有零件**。

## 1. 背景（无上下文也能看懂）

Open Composer 是个人 AI 量化策略工作台。`StrategySpec`（YAML）是策略真相源，CLI 入口是 `oc`。Step 6 引入了 `oc research auto <thesis>` 让 AI 用一句话 thesis 自动跑「假设 → 选因子 → 单因子 IC → 组合 → 回测 → evidence」流水线，并把 `factor_library.py` 扩到 ~80 个 catalog 因子。

Step 6 完成后跑出 11 个 auto run（5 个 unique thesis），审计 `reports/research/auto/*/report.md` 发现 4 个具体问题：

### 问题 1：Overnight thesis 选错 factor family

Thesis = `"Overnight thesis: exploit overnight gap behavior on SYN daily bars."`，本应选 `overnight_gap` family 的 alpha158_overnight_gap / alpha158_overnight_gap_abs / alpha101_024_open_gap_reversal。实际选出的 candidates 是 **2 个 relative_strength + 3 个 overnight_gap**，最终 selected 是 **2 个 relative_strength**（`leadership_satellite_rank` / `cross_sectional_relative_momentum_120`），与 thesis 完全无关。

### 问题 2：overnight_gap family 的所有因子 IC = n/a

`alpha101_024_open_gap_reversal` / `alpha158_overnight_gap` / `alpha158_overnight_gap_abs` 三个候选 IC 全部 `n/a` 加 `warning` 标签。报告里没有给出根因。可能原因：
- expression 第一根 bar 因 `lag(close, 1)` 产生 NaN，未在 IC 计算前 dropna
- expression 输出 std = 0（rank 后全相同），rank IC 公式分母为 0 返回 None
- `run_factor_lab` 内部 metric 缺失被静默返回 None

### 问题 3：4/5 thesis 单一 family 锁死，缺 risk filter

```text
trend          → 100% trend_momentum (3/3 同 family)
mean_reversion → 100% momentum_short
overnight      → 100% relative_strength（错选）
regime         → 100% risk_regime
volatility     → 主要 risk_regime + volatility_rank（跨 2 family，唯一例外）
```

机构标准：每个 thesis 都应该有 **alpha generator + risk filter + execution timing** 三类因子。当前 trend thesis 完全没有 risk_regime 过滤，大跌时仍持有 long。

### 问题 4：所有 evidence 永远卡在 `strict_data`

11/11 run 的 `promotion_status = blocked`，根因都是：

```
promotion:strict_data:Promotion requires research_strict or paper_ready data;
sample data is workflow smoke-test evidence only
```

`data.source = sample` 永远无法通过 promotion 的 `strict_data` check。Step 6 流水线技术上跑通，但 `oc research auto` 默认走 sample 数据，**产出的策略本质上无法升级到 paper readiness**。

## 2. 目标 / 非目标

### 目标

1. **修 overnight selection bug**：Overnight thesis 必须选出 overnight_gap family 的因子。
2. **修 IC = n/a 问题**：overnight_gap family 因子能给出有效 rank IC 数值（或明确说明"数据不足"）；`_run_single_factor_ic` 输出可诊断的 status 字段。
3. **强制跨 family 选择**：每个 thesis 至少从 ≥ 2 个 family 选 candidate；强制加 ≥ 1 个 risk filter（risk_regime / drawdown_guard / volatility_rank）。
4. **接入真实数据**：`oc research auto` 增加 `--data-source alpaca|longbridge`，让默认走真实数据时能通过 `strict_data` check。
5. **新增 `oc research compare`**：汇总 `reports/research/auto/*/ic_scores.json`，跨 thesis 展示 factor 出现频率、IC 稳定性、被 reject 原因。

### 非目标（明确不做）

- 不引入 ML 依赖（留给 Step 7.A）。
- 不引入 LLM 自动 propose（留给 Step 7.C.L1）。
- 不动 4-pass / harness / paper safety / AST 白名单。
- 不动 `factor_library.py` 的 catalog（除非确认某个因子 expression 本身有 bug，那时单点修）。
- 不重新设计 `_run_single_factor_ic` 整体结构（仅补诊断与 robust 处理）。
- 不动 Step 6 的 `factor_lineage.py`。

## 3. 当前状态扫描（关键文件 + 行号）

```text
open_composer/research/auto_research.py
  L50-61  _FAMILY_KEYWORDS               keyword → family 映射；overnight_gap 触发词已含 "overnight/gap/open gap"
  L169    _select_with_keyword_heuristic 选 candidate 主入口
  L172    for family, triggers ...        当前遍历逻辑：keyword 命中就加 family
  L175-176  fallback                       matched_families 为空时 fallback ["trend_momentum","risk_regime"]
  L180-187  candidates 累积               每 family ≤ 5 个；总数 ≤ 15
  L258    _run_single_factor_ic           调用 run_factor_lab；IC=None 时静默丢失诊断
  L286    run_factor_lab(...)             返回 FactorLabResult
  L305    _select_top_k                   要求 rank_ic 非 None + obs≥30 + coverage≥70
  L686-696 _factors_for_family_or_alias   overnight_gap / volatility_rank 没有 fallback 别名

open_composer/research/factor_library.py
  ALPHA158_LIBRARY 含 alpha158_overnight_gap / alpha158_overnight_gap_abs
  ALPHA101_LIBRARY 含 alpha101_024_open_gap_reversal
  → 三个 factor 都有 expression，但 IC 算出来 n/a；需要进 expression / data 路径

open_composer/research/factor_lab.py
  run_factor_lab 返回 FactorLabResult
  L42 FactorLabResult
  L52 def run_factor_lab(...)
  ⚠ metric.rank_ic 在某些情况返回 None（数据不足、std=0、全 NaN）；调用方需区分

reports/research/auto/{run_id}/
  thesis.md / candidates.json / ic_scores.json / selected_factors.json / report.md
  ⚠ Step 6.5 需新增：cross_thesis_compare.json / cross_thesis_compare.md
                     （oc research compare 输出）

open_composer/cli.py
  research_app 已注册（Step 6）
  ⚠ 缺 oc research compare 命令

capabilities/registry.yaml
  market.synthetic_daily_long  ← Step 6.5 已用，sample 数据天花板
  market.alpaca_bars            ← 接入用
  market.longbridge_bars        ← 接入用

data/sample/syn_daily.csv         1000 daily bar；strict_data 永远 blocked

reports/research/auto/             11 已有 run；Step 6.5 不动旧数据，新跑写新 run
```

## 4. 改动清单（按 Wave 分批；一个会话顺序完成）

### Wave 6.5.1 — 修 overnight selection bug + 强制跨 family（45 分钟）

**4.5.1.1 重写 `_select_with_keyword_heuristic`**

文件：`open_composer/research/auto_research.py:169`

```python
# === 核心规则 ===
# 1. keyword 触发 + 同义词扩展（保留现有 _FAMILY_KEYWORDS）
# 2. 触发的 family 内最多 5 个 factor
# 3. **强制至少 2 个 family**：单 family 触发时，按 thesis tag 补一个 "complementary family"
#    - 任何 alpha generator 类（trend_momentum/momentum_short/relative_strength/overnight_gap/kline_shape）
#      → 补 risk_regime 作为 risk filter
#    - 任何 risk_regime/drawdown_guard/volatility_rank
#      → 补 trend_momentum 作为 alpha generator
# 4. 每个候选必须 expression != None
# 5. **断言**：如果 thesis 含 "overnight" / "gap" / "open gap"，selected 中必须有 ≥ 1 个 overnight_gap factor
#    （否则 raise ValueError 让 Codex 看到 selection 失败）

_COMPLEMENT_RULES: dict[str, str] = {
    # alpha generator → risk filter
    "trend_momentum": "risk_regime",
    "momentum_short": "risk_regime",
    "relative_strength": "risk_regime",
    "overnight_gap": "risk_regime",
    "kline_shape": "risk_regime",
    "volume_momentum": "risk_regime",
    # risk filter → alpha generator
    "risk_regime": "trend_momentum",
    "drawdown_guard": "trend_momentum",
    "volatility_rank": "trend_momentum",
    "breadth_canary": "trend_momentum",
}


def _select_with_keyword_heuristic(thesis: str) -> list[FactorDefinition]:
    text = thesis.lower()
    matched_families: list[str] = []
    for family, triggers in _FAMILY_KEYWORDS.items():
        if any(trigger in text for trigger in triggers):
            matched_families.append(family)
    if not matched_families:
        matched_families = ["trend_momentum", "risk_regime"]

    # 强制跨 family：补 complementary family（去重保持顺序）
    extended: list[str] = list(matched_families)
    for primary in matched_families:
        comp = _COMPLEMENT_RULES.get(primary)
        if comp and comp not in extended:
            extended.append(comp)
    matched_families = extended

    candidates: list[FactorDefinition] = []
    seen: set[str] = set()
    per_family_quota = 5
    for family in matched_families:
        added = 0
        for factor in _factors_for_family_or_alias(family):
            if factor.id in seen or not factor.expression:
                continue
            candidates.append(factor)
            seen.add(factor.id)
            added += 1
            if added >= per_family_quota:
                break

    # 显式断言 thesis 关键词与 selected family 自洽（防止 Step 6 中的 overnight 错选）
    text_assertions = [
        (["overnight", "gap", "open gap"], "overnight_gap"),
        (["drawdown", "crash"], "drawdown_guard"),
        (["volatility", " vol "], "volatility_rank"),
    ]
    for triggers, must_have_family in text_assertions:
        if any(t in text for t in triggers):
            if not any(c.family == must_have_family for c in candidates):
                # 没匹到说明 catalog 缺这个 family 的 expressionable factor
                fallback = _factors_for_family_or_alias(must_have_family)[:3]
                for f in fallback:
                    if f.id not in seen and f.expression:
                        candidates.append(f)
                        seen.add(f.id)

    return candidates[:15]
```

**4.5.1.2 修 `_factors_for_family_or_alias` 增加 overnight_gap / volatility_rank fallback**

文件：`open_composer/research/auto_research.py:686`

```python
def _factors_for_family_or_alias(family: str) -> list[FactorDefinition]:
    direct = list_factors(family=family, expression_only=True)
    if direct:
        return direct
    # Fallback 别名：当 catalog 中某 family 没有 expressionable factor 时，按 id 关键词回退
    fallbacks = {
        "drawdown_guard": lambda f: "drawdown" in f.id or f.family == "risk_regime",
        "overnight_gap":  lambda f: "overnight" in f.id or "gap" in f.id,
        "volatility_rank": lambda f: "volatility" in f.id or "atr" in f.id or "bollinger" in f.id,
        "breadth_canary": lambda f: "breadth" in f.id or "canary" in f.id,
    }
    if family in fallbacks:
        return [f for f in list_factors(expression_only=True) if fallbacks[family](f)]
    return []
```

**4.5.1.3 测试**

新增 `tests/test_auto_research_selection.py`：

```python
"""Step 6.5: enforce cross-family selection and thesis-keyword alignment."""
from __future__ import annotations

import pytest

from open_composer.research.auto_research import _select_with_keyword_heuristic


def test_overnight_thesis_selects_overnight_gap_family():
    thesis = "Overnight thesis: exploit overnight gap behavior on SYN daily bars."
    candidates = _select_with_keyword_heuristic(thesis)
    assert any(c.family == "overnight_gap" for c in candidates), (
        f"overnight thesis must include overnight_gap factors; got families "
        f"{[c.family for c in candidates]}"
    )


def test_trend_thesis_adds_risk_filter():
    thesis = "Trend thesis: find a strong daily uptrend continuation strategy on SYN."
    candidates = _select_with_keyword_heuristic(thesis)
    families = {c.family for c in candidates}
    assert "trend_momentum" in families
    # 强制 cross-family：必须含 risk_regime 或 drawdown_guard / volatility_rank
    assert families & {"risk_regime", "drawdown_guard", "volatility_rank"}, (
        f"trend thesis must include a risk filter; got families {families}"
    )


def test_mean_reversion_thesis_adds_risk_filter():
    thesis = "Mean reversion thesis: buy oversold daily pullbacks on SYN."
    candidates = _select_with_keyword_heuristic(thesis)
    families = {c.family for c in candidates}
    assert "momentum_short" in families
    assert families & {"risk_regime", "drawdown_guard", "volatility_rank"}, (
        f"mean reversion thesis must include a risk filter; got families {families}"
    )


def test_drawdown_thesis_selects_drawdown_family():
    thesis = "Defensive thesis: reduce exposure during drawdowns and crashes."
    candidates = _select_with_keyword_heuristic(thesis)
    families = {c.family for c in candidates}
    assert "drawdown_guard" in families or any(
        "drawdown" in c.id for c in candidates
    ), f"drawdown thesis must surface drawdown factors; got families {families}"


def test_volatility_thesis_selects_volatility_family():
    thesis = "Volatility thesis: trade only when volatility is calm."
    candidates = _select_with_keyword_heuristic(thesis)
    families = {c.family for c in candidates}
    assert "volatility_rank" in families or "risk_regime" in families


def test_at_least_two_families_in_all_cases():
    """No thesis should be locked to a single family."""
    for thesis in [
        "Trend continuation on SYN.",
        "Mean reversion buy the dip.",
        "Volatility breakout regime.",
        "Risk regime defensive switch.",
        "Overnight gap exploit.",
    ]:
        candidates = _select_with_keyword_heuristic(thesis)
        families = {c.family for c in candidates}
        assert len(families) >= 2, (
            f"single-family lockdown still present for thesis={thesis!r}; "
            f"families={families}"
        )
```

**Wave 6.5.1 验收**：

```bash
.venv/bin/pytest tests/test_auto_research_selection.py -v
# 期望：6 个 test 全过
.venv/bin/oc research auto "Overnight thesis: exploit overnight gap behavior on SYN daily bars." \
  --universe SYN --timeframe daily --data-source sample --data-path data/sample/syn_daily.csv --max-factors 5
# 检查 candidates.json：必须含至少 1 个 overnight_gap family factor
# 检查 candidates.json：families 数量 ≥ 2
```

---

### Wave 6.5.2 — 修 IC = n/a 问题（45 分钟）

**4.5.2.1 给 `_run_single_factor_ic` 增加诊断**

文件：`open_composer/research/auto_research.py:258`

```python
def _run_single_factor_ic(
    *,
    candidates,
    thesis,
    universe,
    timeframe,
    data_source,
    data_path,
    base,
    run_dir,
) -> dict[str, dict[str, Any]]:
    scores: dict[str, dict[str, Any]] = {}
    mini_dir = ensure_dir(run_dir / "mini_specs")
    for factor in candidates:
        if not factor.expression:
            scores[factor.id] = {
                "status": "skipped",
                "reason": "no_expression_template",
                "rank_ic": None,
            }
            continue
        spec_path = _mini_spec_path(
            factor=factor, thesis=thesis, universe=universe,
            timeframe=timeframe, data_source=data_source, data_path=data_path,
            base=base, mini_dir=mini_dir,
        )
        try:
            result = run_factor_lab(spec_path, base, forward_bars=5, quantiles=5)
        except Exception as exc:  # noqa: BLE001
            scores[factor.id] = {
                "status": "failed",
                "reason": "factor_lab_exception",
                "error": str(exc),
                "rank_ic": None,
            }
            continue

        metric = result.factor_metrics[0] if result.factor_metrics else None
        if metric is None:
            scores[factor.id] = {
                "status": "failed",
                "reason": "no_metric_returned",
                "rank_ic": None,
                "flags": ["missing_metric"],
            }
            continue

        # ✦ 显式诊断 rank_ic = None 的根因
        rank_ic = metric.rank_ic
        diagnosis = None
        if rank_ic is None:
            if metric.observations < 30:
                diagnosis = "insufficient_observations"
            elif metric.coverage_pct < 50:
                diagnosis = "low_coverage"
            elif "constant_series" in (metric.flags or []) or "zero_variance" in (metric.flags or []):
                diagnosis = "zero_variance_signal"
            elif "all_nan" in (metric.flags or []):
                diagnosis = "all_nan_signal"
            else:
                diagnosis = "rank_ic_undefined_unknown_reason"

        scores[factor.id] = {
            "status": result.status if rank_ic is not None else "diagnostic",
            "rank_ic": rank_ic,
            "rank_ic_diagnosis": diagnosis,
            "rolling_rank_ic_mean": metric.rolling_rank_ic_mean,
            "stability_score": metric.stability_score,
            "coverage_pct": metric.coverage_pct,
            "observations": metric.observations,
            "top_bottom_spread_pct": metric.top_bottom_spread_pct,
            "flags": metric.flags or [],
            "spec_path": _relpath(spec_path, base),
            "json_path": _relpath(result.json_path, base),
        }
    return scores
```

**4.5.2.2 让 `run_factor_lab` 在 zero-variance / all-NaN 时给明确 flag**

文件：`open_composer/research/factor_lab.py`

在计算 rank IC 前增加显式检查（具体行号请 Codex 用 grep 找 `rank_ic` 赋值处；通常在 `_compute_factor_metric` 类的函数内）：

```python
# 在算 rank IC 前
factor_series = ...  # 已经构造好的 factor 时间序列
# 显式检查
if factor_series.dropna().empty:
    flags.append("all_nan")
    rank_ic = None
elif factor_series.dropna().std() == 0 or factor_series.dropna().nunique() <= 1:
    flags.append("zero_variance")
    rank_ic = None
elif (factor_series.notna() & forward_returns.notna()).sum() < min_observations:
    flags.append("insufficient_observations")
    rank_ic = None
else:
    rank_ic = factor_series.corr(forward_returns, method="spearman")
    if pd.isna(rank_ic):
        flags.append("rank_ic_nan_unknown")
        rank_ic = None
```

**关键**：让 Codex 自己用 grep / read 找到 `factor_lab.py` 里 rank_ic 计算的精确位置。`flags` 字段已存在（factor_lab.py:38 已声明 `flags: list[str]`），只需扩充触发条件。

**4.5.2.3 修 overnight expression 的 lag NaN 处理**

在 `evaluate_raw_expression` 或 `prepare_factor_frame` 调用链中，每个 factor 计算完后**显式 dropna 前 N 行**（N = max lag），让 IC 计算时不被首段 NaN 拉低 coverage。

但这是侵入式改动，**保守做法**：在 factor_lab 计算 rank IC 前对 factor_series 和 forward_returns 同步 dropna：

```python
combined = pd.concat([factor_series, forward_returns], axis=1).dropna()
if len(combined) < min_observations:
    flags.append("insufficient_observations_after_dropna")
    rank_ic = None
else:
    rank_ic = combined.iloc[:, 0].corr(combined.iloc[:, 1], method="spearman")
```

**4.5.2.4 测试**

新增 `tests/test_auto_research_ic_diagnostics.py`：

```python
"""Step 6.5: IC = n/a must come with an explicit diagnosis."""
from __future__ import annotations
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_overnight_factors_produce_ic_or_diagnosis(tmp_path, monkeypatch):
    """alpha158_overnight_gap should either give a numeric rank_ic or an explicit diagnosis."""
    monkeypatch.chdir(ROOT)
    from open_composer.research.auto_research import run_auto_research

    result = run_auto_research(
        thesis="Overnight thesis: exploit overnight gap behavior on SYN daily bars.",
        universe=["SYN"], timeframe="daily",
        data_source="sample", data_path="data/sample/syn_daily.csv",
        max_factors=5, use_llm=False,
    )

    import json
    ic = json.loads((Path(result.report_path).parent / "ic_scores.json").read_text())
    overnight_ids = [k for k in ic if "overnight" in k.lower() or "gap" in k.lower()]
    assert overnight_ids, f"no overnight factor candidate found; ic keys = {list(ic)}"

    for fid in overnight_ids:
        row = ic[fid]
        rank_ic = row.get("rank_ic")
        diagnosis = row.get("rank_ic_diagnosis")
        # 要么有数值，要么有明确诊断（不能两者都 None / 缺失）
        assert (rank_ic is not None) or (diagnosis is not None), (
            f"factor {fid}: rank_ic=None AND no diagnosis. row={row}"
        )


def test_ic_diagnosis_values_are_known():
    """All diagnosis values come from a fixed enum."""
    from open_composer.research.auto_research import _run_single_factor_ic  # noqa
    # 静态检查：在 _run_single_factor_ic 源码里 diagnosis 取值必须属于以下集合
    known = {
        "insufficient_observations",
        "low_coverage",
        "zero_variance_signal",
        "all_nan_signal",
        "rank_ic_undefined_unknown_reason",
    }
    source = Path(__file__).resolve().parents[1] / "open_composer" / "research" / "auto_research.py"
    text = source.read_text(encoding="utf-8")
    for value in known:
        assert value in text, f"expected diagnosis enum {value!r} missing from auto_research.py"
```

**Wave 6.5.2 验收**：

```bash
.venv/bin/pytest tests/test_auto_research_ic_diagnostics.py -v
.venv/bin/oc research auto "Overnight thesis: exploit overnight gap behavior on SYN daily bars." \
  --universe SYN --timeframe daily --data-source sample --data-path data/sample/syn_daily.csv --max-factors 5
# 检查 ic_scores.json：alpha158_overnight_gap 等必须出现 rank_ic_diagnosis 字段
# 期望 rank_ic 为数值（不再 n/a），或 diagnosis 明确说明
```

---

### Wave 6.5.3 — 接入真实数据（30 分钟）

**4.5.3.1 验证 `--data-source alpaca|longbridge` 已支持**

CLI 入口 `oc research auto`（Step 6 已实现）已经接受 `--data-source`，但默认 `sample`。

文件：`open_composer/cli.py` 找到 `research_auto_command`，确认参数：

```python
@research_app.command("auto")
def research_auto_command(
    thesis: str,
    universe: Annotated[str, typer.Option("--universe")] = "QQQ",
    timeframe: Annotated[str, typer.Option("--timeframe")] = "daily",
    data_source: Annotated[str, typer.Option("--data-source", help="sample|alpaca|longbridge")] = "alpaca",  # ✦ 默认改 alpaca
    data_path: Annotated[str | None, typer.Option("--data-path")] = None,
    max_factors: Annotated[int, typer.Option("--max-factors")] = 5,
    use_llm: Annotated[bool, typer.Option("--use-llm/--no-llm")] = False,
) -> None:
    ...
```

把默认 universe 从 `SYN` 改为 `QQQ`（更接近真实用户场景），默认 data_source 从 `sample` 改为 `alpaca`。

**4.5.3.2 增加 capability 自动检测与降级**

文件：`open_composer/research/auto_research.py:703 _market_capability`

新增 `_check_data_source_available`：

```python
def _check_data_source_available(
    data_source: str, root: Path
) -> tuple[bool, str]:
    """检查 data_source 在当前环境是否可用；不可用时返回 (False, reason)。"""
    if data_source == "sample":
        return True, ""
    from open_composer.config import (
        alpaca_api_key_id, alpaca_api_secret_key,
    )
    if data_source == "alpaca":
        if not (alpaca_api_key_id() and alpaca_api_secret_key()):
            return False, "ALPACA_API_KEY_ID / ALPACA_API_SECRET_KEY not configured"
        return True, ""
    if data_source == "longbridge":
        import os
        keys = ["LONGBRIDGE_APP_KEY", "LONGBRIDGE_APP_SECRET", "LONGBRIDGE_ACCESS_TOKEN"]
        missing = [k for k in keys if not os.getenv(k)]
        if missing:
            return False, f"Longbridge env missing: {','.join(missing)}"
        return True, ""
    return False, f"unknown data_source: {data_source}"
```

`run_auto_research` 开头检查：

```python
def run_auto_research(thesis, universe, *, timeframe="daily", data_source="alpaca", ...):
    base = root or project_root()
    available, reason = _check_data_source_available(data_source, base)
    if not available:
        # 降级到 sample，明确警告
        fallback_msg = f"data_source={data_source} unavailable ({reason}); falling back to sample"
        data_source = "sample"
        data_path = data_path or "data/sample/syn_daily.csv"
        # 写入 run_dir/data_source_fallback.txt
```

**4.5.3.3 文档更新**

`docs/user-guide.md` 在 "AI-Driven Research" 段后增加：

```markdown
### Default data source

`oc research auto` defaults to `--data-source alpaca` and `--universe QQQ` for
real-data research. If Alpaca credentials are not configured, it falls back to
sample synthetic data (`data/sample/syn_daily.csv`) and writes a fallback note
into the run directory.

For sample-only research:

```bash
uv run oc research auto "<thesis>" --universe SYN --timeframe daily \
  --data-source sample --data-path data/sample/syn_daily.csv
```

For real data:

```bash
# Configure .env first:
#   ALPACA_API_KEY_ID=...
#   ALPACA_API_SECRET_KEY=...
#   ALPACA_PAPER=true

uv run oc research auto "<thesis>" --universe QQQ --timeframe daily
# 默认 alpaca，evidence 可以走出 strict_data blocker
```
```

**Wave 6.5.3 验收**：

```bash
# 无 alpaca 凭证时降级测试
.venv/bin/oc research auto "Trend thesis on QQQ daily." --universe QQQ --max-factors 3
# 期望：输出包含 "falling back to sample" 警告；run_dir 含 data_source_fallback.txt

# 有 alpaca 凭证时真实拉取（用户手动跑）
.venv/bin/oc research auto "Trend thesis on QQQ daily." --universe QQQ --data-source alpaca --max-factors 3
# 期望：promotion strict_data 不再 blocked（变 warning 或 ok）
```

---

### Wave 6.5.4 — 新增 `oc research compare` 命令（45 分钟）

**4.5.4.1 新模块**

新增 `open_composer/research/auto_compare.py`：

```python
"""Cross-thesis factor comparison across reports/research/auto/*/ic_scores.json.

Output:
  reports/research/auto/_compare/cross_thesis_compare.json
  reports/research/auto/_compare/cross_thesis_compare.md

The .md table shows:
  - factor_id, family, total appearances, # selected, mean rank IC, std rank IC
  - top theses where the factor was selected
  - diagnosis breakdown (insufficient_observations / zero_variance / all_nan / ...)
"""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from open_composer.config import ensure_dir, project_root
from open_composer.research.factor_library import get_factor


@dataclass
class FactorAggregate:
    factor_id: str
    family: str = ""
    appearances: int = 0
    selected_count: int = 0
    rank_ics: list[float] = field(default_factory=list)
    diagnoses: dict[str, int] = field(default_factory=dict)
    theses: list[str] = field(default_factory=list)
    selected_theses: list[str] = field(default_factory=list)


def build_cross_thesis_compare(root: Path | None = None) -> dict[str, Any]:
    base = root or project_root()
    auto_dir = base / "reports" / "research" / "auto"
    aggregates: dict[str, FactorAggregate] = {}
    runs: list[dict[str, Any]] = []

    for run_dir in sorted(auto_dir.iterdir() if auto_dir.exists() else []):
        if not run_dir.is_dir() or run_dir.name.startswith("_"):
            continue
        ic_path = run_dir / "ic_scores.json"
        selected_path = run_dir / "selected_factors.json"
        thesis_path = run_dir / "thesis.md"
        if not (ic_path.exists() and thesis_path.exists()):
            continue
        try:
            ic = json.loads(ic_path.read_text(encoding="utf-8"))
            selected = (
                json.loads(selected_path.read_text(encoding="utf-8"))
                if selected_path.exists() else []
            )
            thesis = thesis_path.read_text(encoding="utf-8").strip().splitlines()[0]
        except (OSError, json.JSONDecodeError):
            continue
        runs.append({"run_id": run_dir.name, "thesis": thesis,
                      "candidates": len(ic), "selected": len(selected)})
        for factor_id, row in ic.items():
            agg = aggregates.setdefault(factor_id, FactorAggregate(factor_id=factor_id))
            try:
                agg.family = get_factor(factor_id).family
            except KeyError:
                pass
            agg.appearances += 1
            agg.theses.append(thesis[:80])
            if factor_id in selected:
                agg.selected_count += 1
                agg.selected_theses.append(thesis[:80])
            rank_ic = row.get("rank_ic")
            if isinstance(rank_ic, (int, float)):
                agg.rank_ics.append(float(rank_ic))
            diag = row.get("rank_ic_diagnosis")
            if diag:
                agg.diagnoses[diag] = agg.diagnoses.get(diag, 0) + 1

    summary = {
        "generated_at": datetime.now(UTC).isoformat(),
        "total_runs": len(runs),
        "total_factors_seen": len(aggregates),
        "runs": runs,
        "factors": [
            {
                "factor_id": agg.factor_id,
                "family": agg.family,
                "appearances": agg.appearances,
                "selected_count": agg.selected_count,
                "selection_rate": agg.selected_count / max(agg.appearances, 1),
                "rank_ic_count": len(agg.rank_ics),
                "rank_ic_mean": (sum(agg.rank_ics) / len(agg.rank_ics)) if agg.rank_ics else None,
                "rank_ic_min":  min(agg.rank_ics) if agg.rank_ics else None,
                "rank_ic_max":  max(agg.rank_ics) if agg.rank_ics else None,
                "diagnoses": agg.diagnoses,
                "selected_theses": agg.selected_theses[:5],
            }
            for agg in sorted(
                aggregates.values(),
                key=lambda a: (a.selected_count, a.appearances),
                reverse=True,
            )
        ],
    }
    return summary


def write_cross_thesis_compare(root: Path | None = None) -> tuple[Path, Path]:
    base = root or project_root()
    payload = build_cross_thesis_compare(base)
    out_dir = ensure_dir(base / "reports" / "research" / "auto" / "_compare")
    json_path = out_dir / "cross_thesis_compare.json"
    md_path = out_dir / "cross_thesis_compare.md"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=False), encoding="utf-8")
    md_path.write_text(_render_markdown(payload), encoding="utf-8")
    return json_path, md_path


def _render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Cross-Thesis Factor Comparison",
        "",
        f"- Generated: `{payload['generated_at']}`",
        f"- Runs analyzed: {payload['total_runs']}",
        f"- Unique factors seen: {payload['total_factors_seen']}",
        "",
        "## Runs",
        "",
        "| run_id | thesis | candidates | selected |",
        "|---|---|---:|---:|",
    ]
    for r in payload["runs"]:
        lines.append(f"| `{r['run_id']}` | {r['thesis'][:60]} | {r['candidates']} | {r['selected']} |")
    lines.extend([
        "",
        "## Factor performance",
        "",
        "| factor | family | shown | selected | sel% | IC mean | IC min | IC max | diagnoses |",
        "|---|---|---:|---:|---:|---:|---:|---:|---|",
    ])
    for f in payload["factors"][:50]:
        diag_brief = ", ".join(f"{k}:{v}" for k, v in (f["diagnoses"] or {}).items())[:60]
        ic_mean = f"{f['rank_ic_mean']:.3f}" if f["rank_ic_mean"] is not None else "n/a"
        ic_min  = f"{f['rank_ic_min']:.3f}" if f["rank_ic_min"] is not None else "n/a"
        ic_max  = f"{f['rank_ic_max']:.3f}" if f["rank_ic_max"] is not None else "n/a"
        lines.append(
            f"| `{f['factor_id']}` | {f['family']} | "
            f"{f['appearances']} | {f['selected_count']} | "
            f"{f['selection_rate']*100:.0f}% | "
            f"{ic_mean} | {ic_min} | {ic_max} | {diag_brief} |"
        )
    return "\n".join(lines) + "\n"
```

**4.5.4.2 新 CLI**

文件：`open_composer/cli.py` 在 `research_app` 段加：

```python
@research_app.command("compare")
def research_compare_command() -> None:
    """Aggregate ic_scores.json across all auto research runs."""
    from open_composer.research.auto_compare import write_cross_thesis_compare

    json_path, md_path = write_cross_thesis_compare(project_root())
    console.print(f"[green]cross-thesis compare written[/green]")
    console.print(f"json: {json_path}")
    console.print(f"markdown: {md_path}")
```

**4.5.4.3 测试**

新增 `tests/test_auto_compare.py`：

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_compare_aggregates_existing_runs(tmp_path, monkeypatch):
    monkeypatch.chdir(Path(__file__).resolve().parents[1])
    from open_composer.research.auto_compare import build_cross_thesis_compare

    payload = build_cross_thesis_compare(Path.cwd())
    # 仓库已有 ≥ 5 个 run（Step 6 执行后）
    assert payload["total_runs"] >= 1
    assert payload["total_factors_seen"] >= 1
    assert isinstance(payload["factors"], list)
    if payload["factors"]:
        first = payload["factors"][0]
        assert "factor_id" in first
        assert "appearances" in first
        assert "selection_rate" in first


def test_compare_writes_json_and_md(tmp_path, monkeypatch):
    monkeypatch.chdir(Path(__file__).resolve().parents[1])
    from open_composer.research.auto_compare import write_cross_thesis_compare

    json_path, md_path = write_cross_thesis_compare(Path.cwd())
    assert json_path.exists()
    assert md_path.exists()
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert "factors" in data
```

**Wave 6.5.4 验收**：

```bash
.venv/bin/pytest tests/test_auto_compare.py -v
.venv/bin/oc research compare
# 期望产物：
test -f reports/research/auto/_compare/cross_thesis_compare.json
test -f reports/research/auto/_compare/cross_thesis_compare.md
cat reports/research/auto/_compare/cross_thesis_compare.md | head -30
```

---

### Wave 6.5.5 — 文档与 CURRENT_DOCS（10 分钟）

**4.5.5.1 更新 user-guide.md** —— 见 4.5.3.3

加 "Cross-thesis comparison" 段：

```markdown
### Cross-thesis comparison

After running multiple `oc research auto` theses, generate a cross-thesis view:

```bash
uv run oc research compare
```

Output at `reports/research/auto/_compare/cross_thesis_compare.md` shows:

- Which factors appear across the most theses
- Selection rate (how often a factor passes top-K)
- Mean / min / max rank IC across runs
- Diagnosis breakdown (insufficient_observations / zero_variance / all_nan / ...)

Use this to decide:
- Stop investigating factors with diagnoses across many runs
- Promote factors with high selection rate to your default catalog filter
- Spot single-family lockdown (one family dominates across unrelated theses)
```

**4.5.5.2 CURRENT_DOCS 同步**

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
    "docs/plan-step-6-factor-catalog-and-ai-research-2026-05-26.zh.md",
    "docs/plan-step-6-5-auto-research-fixes-2026-06-08.zh.md",    # ✦ 本文档
}
```

同步在 `README.md` Project Docs 段加链接。

## 5. 完整验收清单

```text
[ ] _select_with_keyword_heuristic 强制跨 family + 关键词断言（overnight/drawdown/volatility）
[ ] _factors_for_family_or_alias 增加 overnight_gap / volatility_rank / breadth_canary fallback
[ ] _run_single_factor_ic 输出 status + rank_ic_diagnosis 字段
[ ] factor_lab.py 显式生成 all_nan / zero_variance / insufficient_observations flag
[ ] oc research auto --data-source 默认改 alpaca；缺凭证降级 sample + 写 fallback 文件
[ ] oc research compare 命令可用；写 cross_thesis_compare.{json,md}
[ ] tests/test_auto_research_selection.py 6 个 test 全过
[ ] tests/test_auto_research_ic_diagnostics.py 2 个 test 全过
[ ] tests/test_auto_compare.py 2 个 test 全过
[ ] 旧 11 个 run 仍可被 compare 读取（向后兼容）
[ ] 重跑 5 个 unique thesis 后：
    [ ] overnight thesis 至少含 1 个 overnight_gap factor
    [ ] 4/5 thesis 含 risk filter（risk_regime / drawdown_guard / volatility_rank）
    [ ] 所有 IC=None 都附 rank_ic_diagnosis
[ ] README + user-guide.md 加新段
[ ] CURRENT_DOCS 与 README Project Docs 同步本文档
[ ] .venv/bin/pytest 全绿
[ ] .venv/bin/oc repo check --strict 通过
[ ] make verify 通过（如改了 dashboard）
```

## 6. 不做什么

```text
✗ 不改 factor_library.py catalog（除非 expression 本身有 bug 需要单点修）
✗ 不引入 ML / Optuna / Optuna（留给 Step 7.A）
✗ 不做 LLM 因子自动 propose（留给 Step 7.C.L1）
✗ 不改 4-pass / harness / paper safety
✗ 不动 AST 安全白名单
✗ 不动 backtest engine
✗ 不动 Step 6 的 factor_lineage.py
✗ 不删除任何旧 run（向后兼容）
```

## 7. 风险与对冲

| 风险 | 对冲 |
|---|---|
| 强制跨 family 让 candidates 数超过 max_factors 限制 | per_family_quota=5 + 总数 ≤ 15 不变；selected_top_k 仍只取 max_factors |
| overnight_gap factor 的 IC 即使修了 NaN 处理仍是 None | diagnosis 字段会明确"insufficient_observations"等；不再静默 |
| Alpaca 默认接入后 sample 测试失败 | _check_data_source_available 自动降级；写 fallback 文件 |
| cross_thesis_compare 在旧 run 缺字段时 KeyError | 全用 .get() / try-except；缺字段当 None 处理 |
| 关键词断言阻塞普通 thesis | 仅在 thesis 明确含 "overnight/drawdown/volatility" 时断言；不影响其他 thesis |
| 兼容旧 run（无 rank_ic_diagnosis 字段） | aggregate 时 diagnoses 用 .get() 默认空 dict |
| factor_lab.py 改动破坏现有 promotion factor_lab check | 仅扩 flags 列表 + 在 rank_ic=None 时补 flag；不改返回结构 |

## 8. 回滚

每个 Wave 单独 commit：
- Wave 6.5.1 → revert 单独，selection 回到 Step 6 状态
- Wave 6.5.2 → revert 单独，IC 诊断不输出但不影响其余
- Wave 6.5.3 → revert 单独，data source 默认回 sample
- Wave 6.5.4 → revert 单独，oc research compare 命令消失

## 9. 完成定义

执行完 Wave 6.5.1-6.5.5 后：

- Overnight thesis 选出 overnight_gap factor（不再选 relative_strength）
- 所有 IC=None 都附明确 diagnosis（不再"n/a"无原因）
- 每个 thesis 至少含 ≥ 2 个 family 的 factor，且必含 risk filter
- `oc research auto` 默认走 alpaca 真实数据；无凭证时显式降级
- `oc research compare` 给出跨 thesis 因子对比表
- 用户重跑 5 个 thesis 后能用 `oc research compare` 看到：
  - 哪些 factor 跨 thesis 稳定有 IC
  - 哪些 factor 总是 selected 但跨 thesis 不一致
  - 哪些 factor 有 diagnostic blocker 应该被弃用

完成后**再判断**是否触发 Step 7.A / 7.B / 7.C。如果真实数据上 IC 仍 ≥ 0.04，Step 7.A 仍不需要做。

## 10. 执行顺序总览（写给无上下文 Codex）

```text
Wave 6.5.1 (45min)  修 selection 强制跨 family + overnight 关键词断言
Wave 6.5.2 (45min)  修 IC = n/a：诊断字段 + factor_lab flags
Wave 6.5.3 (30min)  接入真实数据 + 降级机制
Wave 6.5.4 (45min)  oc research compare 跨 thesis 对比命令
Wave 6.5.5 (10min)  文档 + CURRENT_DOCS

总计：约 3 小时，单个 agent 会话内完成。

每个 Wave 完成后跑：
  .venv/bin/pytest tests/ -q
  .venv/bin/oc repo check --strict
  （Wave 6.5.5 之后）make verify

完成后立刻跑 5 个 unique thesis 验证：
  for thesis in \
    "Trend continuation on QQQ daily." \
    "Mean reversion buy oversold on QQQ daily." \
    "Volatility breakout regime on QQQ daily." \
    "Risk regime defensive switch on QQQ daily." \
    "Overnight gap exploit on QQQ daily."; do
    .venv/bin/oc research auto "$thesis" --universe QQQ --max-factors 5
  done
  .venv/bin/oc research compare
  cat reports/research/auto/_compare/cross_thesis_compare.md | head -40
```
