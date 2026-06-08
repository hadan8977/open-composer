# Open Composer Step 7：条件触发的 ML / 衰减监控 / LLM 三角色（G2）

日期：2026-05-26
执行者：Codex / Claude Code
前置：Step 6（因子库 + `oc research auto`）完成
后续：无（路线图收尾，本步骤完成后进入"用 AI 持续生成迭代策略"日常运营）

## 0. 一句话目标

Step 6 让用户能用一句话 thesis 让 AI 跑研究。Step 7 在 Step 6 基础上**条件触发**地补三件事：

- **7.A** ML backend（LightGBM + Optuna）：当线性表达式因子的 IC 不够时启用。
- **7.B** 因子血统 + 衰减监控：无条件做，作为 active 策略的安全网。
- **7.C** LLM 三角色（propose / explain / factor）：当因子重复或想加新维度时启用。

**关键设计**：三条路径完全独立。任意一条可单独发，单独 revert，互不依赖。

## 1. 背景（无上下文也能看懂）

Open Composer 是个人 AI 量化策略工作台。Step 1-4 把基础设施做完整（StrategySpec / 4-pass / harness / 6 位精度回测 / LLM materialization / Dashboard 全交互）；Step 6 把 factor catalog 接线 + 引入 `oc research auto` 让 AI 用一句话 thesis 自动跑研究流水线。

但 Step 6 跑出的策略仍然受三个限制：

### 限制 1：线性 + 阈值规则的天花板

`oc research auto` 选 3-5 个因子后用 `entry.all/any` AND/OR 组合 → 表达力等于"线性决策树深度 1"。机构标准做法是 **LightGBM 在因子上做非线性组合 + 滚动重训**（Microsoft Qlib Alpha158 baseline）。

### 限制 2：因子上线后 alpha decay 不监控

因子被多人挖掘后 IC 会衰减。当前产品没有"active 策略每周自动重测因子 IC + 报警"的机制。Step 6 加了 `reports/factors/{factor_id}/lineage.json`，但没有 decay-monitor.jsonl。

### 限制 3：LLM 只能"当因子"，不能"设计因子 / 解释模型"

Step 2 把 LLM 当 factor（生成 PIT packet）跑通了。但**没有 `oc factor propose` 让 LLM 看 catalog 提出新因子**，也**没有 `oc strategy explain` 让 LLM 解释 ML 模型行为**。R&D-Agent-Quant / QuantaAlpha 论文证明这两个角色的 ROI 比"LLM 当因子"还高。

### 决策依据

不要预设三条都做。让 Step 6 跑 ≥ 5 个 thesis 后看数据：

```text
触发条件                                              → 优先做
─────────────────────────────────────────────────────────────
≥ 60% 策略 max abs(rank IC) < 0.02                   → 7.A (ML backend)
≥ 3 个策略 OOS Sharpe < 50% in-sample Sharpe          → 7.A 或 7.B
任何 active 策略部署 ≥ 4 周                            → 7.B (始终做)
≥ 5 个策略选中同一组 ≤ 3 个核心因子                   → 7.C (因子重复)
想加 news/sentiment/macro 维度                        → 7.C.L1 (propose)
ML 模型黑箱难调试                                     → 7.C.L2 (explain)
```

## 2. 目标 / 非目标

### 目标（三条独立路径）

**7.A**：StrategySpec 增加 `model:` 段；新增 `oc strategy train / backtest-walk-forward / explain` 命令；backtest engine 支持 model-driven branch；promotion 增加 ML-only gate（feature importance consistency / prediction calibration / no-information baseline lift）。

**7.B**：`reports/factors/{factor_id}/decay-monitor.jsonl` schema + `oc factor decay-monitor / decay-report / retire` 命令；Dashboard Factor Catalog tab 显示衰减状态；Telegram 报警渠道接入。

**7.C.L1**：`oc factor propose --thesis <text>` 让 LLM 看 catalog 提新候选因子；自动 AST 验证 + IC 测试 + 写入 `reports/factor_proposals/`。
**7.C.L2**：`oc strategy explain <run_id>` 让 LLM 看 feature_importance + 错例 → 输出策略解释；写入 trace.jsonl 与 promotion.md。
**7.C.L3**：把现有唯一 LLM 策略 `qqq_news_regime_15m` 重新全历史 materialize（Step 4 修了 `tail(16)` 但没 backfill）+ 加 2-3 个新 LLM factor。

### 非目标

- 不引入 PyTorch / Transformer 端到端模型（个人量化默认场景外；本地 1 卡训练单标的 LSTM 收益不抵复杂度）。
- 不引入 deep RL（数据需求 + 算力 + 调试难度）。
- 不引入 Qlib qrun YAML workflow（与 Step 6 决定一致：借鉴 Alpha158 因子，不接 workflow）。
- 不让 LLM 直接执行交易决策（promotion 仍是唯一晋级路径）。
- 不动 4-pass / harness / paper safety。
- 不动 Step 6 的 factor_library / auto_research 模块。

## 3. 当前状态扫描（Step 6 完成后）

```text
open_composer/research/
  factor_library.py        ≥ 80 FactorDefinition + ALL_FACTORS
  factor_lineage.py        append_lineage() 已实现
  factor_lab.py            run_factor_lab() 单因子 IC
  auto_research.py         oc research auto 流水线
  llm_materialize.py       Step 2 的 LLM factor materialize
  llm_backends.py          OpenAIBackend + LocalTestStub
  promotion.py             _llm_marginal_lift_checks 5 项边际证据

reports/factors/{factor_id}/
  lineage.json             Step 6 已写
  ⚠ 缺：decay-monitor.jsonl

reports/research/auto/{run_id}/
  thesis.md / candidates.json / ic_scores.json /
  selected_factors.json / report.md           ← Step 6 已写

pyproject.toml
  ⚠ 0 ML 依赖；7.A 需要加 lightgbm + optuna + scikit-learn

dashboard/src/app/components/
  ⚠ 没有 "Factor Catalog" tab；7.B 需要新增
```

## 4. 路径 7.A — ML Backend（条件触发）

### 4.A.0 触发判断

执行前先跑：

```bash
.venv/bin/python -c "
import json, glob
from pathlib import Path
results = []
for d in glob.glob('reports/research/auto/*/'):
    ic_path = Path(d) / 'ic_scores.json'
    if ic_path.exists():
        ic = json.loads(ic_path.read_text())
        max_ic = max(
            (abs(v.get('rank_ic', 0) or 0) for v in ic.values()),
            default=0,
        )
        results.append((d, max_ic))
weak = sum(1 for _, m in results if m < 0.02)
print(f'auto-research runs: {len(results)}')
print(f'with max abs(rank_ic) < 0.02: {weak} ({weak/max(len(results),1)*100:.0f}%)')
print('Trigger 7.A?', 'YES' if weak >= 0.6 * len(results) and len(results) >= 5 else 'NO')
"
```

如果触发 7.A，按下文执行。

### 4.A.1 依赖

`pyproject.toml`：

```toml
dependencies = [
  # ... 已有 ...
  "lightgbm>=4.5",
  "optuna>=4.0",
  "scikit-learn>=1.5",
]
```

`uv sync` 后体积增加约 50MB。本地 CPU 训练单标的 500 bar × 30 factor 模型秒级完成。

### 4.A.2 StrategySpec 扩展

文件：`open_composer/models/strategy_spec.py`

```python
class MLModelLabel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["forward_return", "forward_direction"] = "forward_return"
    horizon_bars: int = Field(default=5, ge=1)
    threshold_pct: float | None = None     # forward_direction 时阈值（>=阈值算正）


class MLModelTraining(BaseModel):
    model_config = ConfigDict(extra="forbid")
    window_bars: int = Field(default=504, ge=100)
    retrain_every_bars: int = Field(default=21, ge=1)
    cv_splits: int = Field(default=5, ge=2, le=20)
    test_window_bars: int = Field(default=63, ge=21)
    seed: int = 42


class MLModelSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    method: Literal["threshold", "top_n_by_prediction"] = "threshold"
    threshold: float | None = None         # method=threshold 用
    top_n: int | None = None               # method=top_n_by_prediction 用
    rebalance: Literal["daily", "weekly", "monthly"] = "weekly"


class MLModelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["lightgbm_classifier", "lightgbm_regressor", "linear"] = "lightgbm_regressor"
    label: MLModelLabel
    features: list[str] = Field(min_length=1)        # factor name 引用 spec.factors
    training: MLModelTraining = Field(default_factory=MLModelTraining)
    selection: MLModelSelection = Field(default_factory=MLModelSelection)
    hyperparameters: dict[str, Any] = Field(default_factory=dict)
    optuna_trials: int | None = Field(default=None, ge=10, le=200)  # 启用 Optuna

    @model_validator(mode="after")
    def selection_requires_threshold_or_top_n(self) -> MLModelConfig:
        if self.selection.method == "threshold" and self.selection.threshold is None:
            raise ValueError("ML selection.method=threshold requires selection.threshold")
        if self.selection.method == "top_n_by_prediction" and self.selection.top_n is None:
            raise ValueError("ML selection.method=top_n_by_prediction requires top_n")
        return self


class StrategySpec(BaseModel):
    # ... 已有字段 ...
    model: MLModelConfig | None = None              # ✦ 新增；None 时走规则路径
```

### 4.A.3 ML 后端模块

新增目录：`open_composer/research/ml_backend/`

```text
ml_backend/
  __init__.py                   暴露 train_rolling / predict_for_backtest
  model_factory.py              create_model(spec.model.kind) → sklearn-style wrapper
  feature_pipeline.py           build_X_y_at(spec, frame, t) - 严格无 lookahead
  training.py                   rolling train + Optuna hyperparameter tuning
  prediction.py                 predict_rolling(spec, frame) → pd.Series
  metrics.py                    IC / IR / hit_ratio / calibration_score
  explain.py                    feature_importance / SHAP-lite extraction
```

**关键文件 1：feature_pipeline.py**（约 150 行，严格无 lookahead）

```python
"""Build (X, y) feature matrix from spec.factors at time t.

Critical: y is the FUTURE label (horizon_bars 之后)，必须保证训练时只用 t-1 之前数据。
预测时模型从 t 时刻的因子值预测 t+horizon 的标签。
"""
from __future__ import annotations
import pandas as pd

from open_composer.expressions import evaluate_expression, prepare_factor_frame
from open_composer.models.strategy_spec import MLModelLabel, StrategySpec


def build_feature_matrix(spec: StrategySpec, frame: pd.DataFrame, root) -> pd.DataFrame:
    """Compute all factor values for the entire frame. Cached per spec."""
    prepared = prepare_factor_frame(frame, spec.factors, root=root)
    cols: dict[str, pd.Series] = {}
    for fname in spec.model.features:
        if fname not in spec.factors:
            raise ValueError(f"model feature {fname!r} not declared in spec.factors")
        cols[fname] = evaluate_expression(fname, prepared)
    X = pd.DataFrame(cols)
    return X


def build_label(spec: StrategySpec, frame: pd.DataFrame) -> pd.Series:
    """Compute forward label aligned with frame index."""
    horizon = spec.model.label.horizon_bars
    fwd = frame["close"].pct_change(horizon).shift(-horizon)
    if spec.model.label.type == "forward_direction":
        thr = spec.model.label.threshold_pct or 0.0
        return (fwd >= thr).astype(int)
    return fwd


def slice_train_test(
    X: pd.DataFrame, y: pd.Series, *, retrain_t: int, window_bars: int, test_bars: int,
) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame, pd.Series]:
    """No lookahead: train uses [retrain_t - window, retrain_t); test [retrain_t, retrain_t + test).

    Crucially, the last `horizon_bars` rows of train are dropped because their y
    would be from the test window (label leakage).
    """
    from open_composer.config import project_root  # noqa
    train_end = retrain_t
    train_start = max(0, train_end - window_bars)
    test_start = retrain_t
    test_end = min(len(X), test_start + test_bars)
    horizon = (y.shift(-1).isna() ^ y.isna()).sum() or 1  # rough horizon detect
    # 安全裁剪：训练集最后 horizon 行 y 是未来窗口的，必须丢
    safe_train_end = max(train_start, train_end - horizon)
    X_train = X.iloc[train_start:safe_train_end].dropna()
    y_train = y.loc[X_train.index]
    X_test = X.iloc[test_start:test_end].dropna()
    y_test = y.loc[X_test.index]
    return X_train, y_train, X_test, y_test
```

**关键文件 2：training.py**（约 200 行）

```python
"""Rolling-window training with optional Optuna hyperparameter tuning."""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

from open_composer.research.ml_backend.feature_pipeline import (
    build_feature_matrix, build_label, slice_train_test,
)
from open_composer.research.ml_backend.model_factory import create_model


@dataclass
class FoldResult:
    retrain_t: int
    train_start: int
    train_end: int
    test_start: int
    test_end: int
    feature_importance: dict[str, float]
    predictions: pd.Series                 # index aligned with test window
    train_metrics: dict[str, float]
    test_metrics: dict[str, float]


@dataclass
class TrainingRun:
    spec_name: str
    folds: list[FoldResult] = field(default_factory=list)
    full_predictions: pd.Series | None = None     # 全部 fold test 拼接


def run_rolling_training(spec, frame: pd.DataFrame, root: Path) -> TrainingRun:
    """Walk-forward training. Returns predictions aligned with frame index."""
    if spec.model is None:
        raise ValueError("spec.model is None; not an ML strategy")

    X = build_feature_matrix(spec, frame, root)
    y = build_label(spec, frame)
    window = spec.model.training.window_bars
    retrain = spec.model.training.retrain_every_bars
    test_w = spec.model.training.test_window_bars

    run = TrainingRun(spec_name=spec.name)
    predictions = pd.Series(index=frame.index, dtype=float)

    for retrain_t in range(window, len(frame) - test_w, retrain):
        X_train, y_train, X_test, y_test = slice_train_test(
            X, y, retrain_t=retrain_t, window_bars=window, test_bars=test_w,
        )
        if len(X_train) < 50 or len(X_test) < 10:
            continue
        hyperparams = _resolve_hyperparams(spec, X_train, y_train)
        model = create_model(spec.model.kind, hyperparams, seed=spec.model.training.seed)
        model.fit(X_train, y_train)
        y_pred = pd.Series(model.predict(X_test), index=X_test.index)
        predictions.loc[y_pred.index] = y_pred
        run.folds.append(FoldResult(
            retrain_t=retrain_t,
            train_start=X_train.index[0], train_end=X_train.index[-1],
            test_start=X_test.index[0], test_end=X_test.index[-1],
            feature_importance=_extract_importance(model, X_train.columns),
            predictions=y_pred,
            train_metrics=_metrics(y_train, model.predict(X_train)),
            test_metrics=_metrics(y_test, y_pred),
        ))
    run.full_predictions = predictions
    return run


def _resolve_hyperparams(spec, X_train, y_train) -> dict:
    base = dict(spec.model.hyperparameters or {})
    if spec.model.optuna_trials is None:
        return base
    # Optuna 调参；只在第一个 fold 调，后续 fold 复用
    import optuna
    def objective(trial):
        params = {
            **base,
            "n_estimators": trial.suggest_int("n_estimators", 50, 400),
            "max_depth": trial.suggest_int("max_depth", 3, 10),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
            "num_leaves": trial.suggest_int("num_leaves", 10, 200),
        }
        # 3-fold time-series CV 内部
        from sklearn.model_selection import TimeSeriesSplit
        scores = []
        for tr_idx, te_idx in TimeSeriesSplit(n_splits=3).split(X_train):
            m = create_model(spec.model.kind, params, seed=spec.model.training.seed)
            m.fit(X_train.iloc[tr_idx], y_train.iloc[tr_idx])
            from sklearn.metrics import mean_squared_error, accuracy_score
            pred = m.predict(X_train.iloc[te_idx])
            if spec.model.label.type == "forward_direction":
                scores.append(accuracy_score(y_train.iloc[te_idx], pred > 0.5))
            else:
                scores.append(-mean_squared_error(y_train.iloc[te_idx], pred))
        return float(np.mean(scores))
    study = optuna.create_study(direction="maximize")
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    study.optimize(objective, n_trials=spec.model.optuna_trials, show_progress_bar=False)
    return {**base, **study.best_params}


def _extract_importance(model, feature_names) -> dict[str, float]:
    if hasattr(model, "feature_importances_"):
        return dict(zip(feature_names, model.feature_importances_.astype(float).tolist()))
    if hasattr(model, "coef_"):
        coef = model.coef_
        if coef.ndim > 1:
            coef = coef[0]
        return dict(zip(feature_names, np.abs(coef).astype(float).tolist()))
    return {}


def _metrics(y_true, y_pred):
    from sklearn.metrics import mean_squared_error, accuracy_score
    if set(np.unique(y_true)).issubset({0, 1}):
        return {"accuracy": float(accuracy_score(y_true, np.asarray(y_pred) > 0.5))}
    return {"mse": float(mean_squared_error(y_true, y_pred))}
```

**关键文件 3：prediction.py**（约 50 行）

```python
def predictions_to_signals(predictions: pd.Series, spec) -> tuple[pd.Series, pd.Series]:
    """Convert model predictions to entry/exit masks per spec.model.selection."""
    sel = spec.model.selection
    if sel.method == "threshold":
        entry = predictions > sel.threshold
        exit_ = predictions < (-(sel.threshold or 0) if spec.model.label.type == "forward_return"
                                else 1 - sel.threshold)
    else:  # top_n_by_prediction
        # 时间序列上的 "top_n" = 滚动窗口内 top quantile
        rolling_q = predictions.rolling(window=21, min_periods=10).quantile(1 - sel.top_n / 100)
        entry = predictions > rolling_q
        exit_ = predictions < rolling_q
    return entry.fillna(False), exit_.fillna(False)
```

### 4.A.4 backtest engine integration

文件：`open_composer/engines/backtest_engine.py:147` 的 `backtest_frame`

在 `entry_mask, exit_mask = signal_masks(spec, frame, root=root)` 之前插入：

```python
def backtest_frame(spec, frame, root=None, ...):
    frame = frame.copy()
    frame.attrs.update({"strategy_name": spec.name})

    # ✦ 新增：ML 后端
    if spec.model is not None:
        from open_composer.research.ml_backend.training import run_rolling_training
        from open_composer.research.ml_backend.prediction import predictions_to_signals
        from open_composer.config import project_root
        training = run_rolling_training(spec, frame, root or project_root())
        entry_mask, exit_mask = predictions_to_signals(training.full_predictions, spec)
        # 把训练结果挂到 frame.attrs 供下游消费（promotion / explain）
        frame.attrs["ml_training_run"] = training
    else:
        entry_mask, exit_mask = signal_masks(spec, frame, root=root)

    # ... 原有逻辑 ...
```

### 4.A.5 ML-specific promotion checks

文件：`open_composer/research/promotion.py`，在 `build_promotion_report` 现有 checks 之后增加（仅当 `spec.model is not None`）：

```python
def _ml_specific_checks(spec, full_artifacts) -> list[GateResult]:
    """ML-only quality checks."""
    if spec.model is None:
        return []
    training = full_artifacts.frame_attrs.get("ml_training_run")
    if training is None or not training.folds:
        return [GateResult(
            name="ml_training_present", status="blocked",
            message="ML spec but no training folds completed.",
        )]
    checks: list[GateResult] = []

    # 1. Feature importance consistency
    top_k = 10
    fold_tops = [
        sorted(f.feature_importance.items(), key=lambda kv: kv[1], reverse=True)[:top_k]
        for f in training.folds
    ]
    fold_top_sets = [set(name for name, _ in tops) for tops in fold_tops]
    if len(fold_top_sets) >= 2:
        overlaps = [
            len(a & b) / max(len(a | b), 1)
            for a, b in zip(fold_top_sets, fold_top_sets[1:])
        ]
        avg_jaccard = sum(overlaps) / len(overlaps)
        checks.append(GateResult(
            name="ml_feature_importance_consistency",
            status="ok" if avg_jaccard >= 0.5 else "warning" if avg_jaccard >= 0.3 else "blocked",
            message=f"Adjacent-fold top-{top_k} feature Jaccard = {avg_jaccard:.2f}",
            evidence={"jaccard": avg_jaccard, "fold_count": len(training.folds)},
        ))

    # 2. Train vs test metric degradation
    if training.folds[0].train_metrics and training.folds[0].test_metrics:
        train_scores = [next(iter(f.train_metrics.values())) for f in training.folds]
        test_scores = [next(iter(f.test_metrics.values())) for f in training.folds]
        avg_train = sum(train_scores) / len(train_scores)
        avg_test = sum(test_scores) / len(test_scores)
        # MSE: lower is better; accuracy: higher is better
        key = next(iter(training.folds[0].train_metrics))
        if key == "mse":
            degradation = (avg_test - avg_train) / max(abs(avg_train), 1e-6)
        else:
            degradation = (avg_train - avg_test) / max(abs(avg_train), 1e-6)
        checks.append(GateResult(
            name="ml_train_test_degradation",
            status="ok" if degradation < 0.3 else "warning" if degradation < 0.6 else "blocked",
            message=f"Test vs train {key} degradation = {degradation:.1%}",
            evidence={"avg_train": avg_train, "avg_test": avg_test, "metric": key},
        ))

    # 3. No-information baseline lift
    actual_sharpe = full_artifacts.run.sharpe_ratio or 0
    # 随机预测 baseline：把 predictions 随机洗牌后跑 backtest
    # 工程上简化：用历史 forward return mean / std 作为随机基准
    import numpy as np
    rng = np.random.default_rng(spec.model.training.seed)
    random_pred = pd.Series(
        rng.standard_normal(len(training.full_predictions)),
        index=training.full_predictions.index,
    )
    random_signals_entry, random_signals_exit = predictions_to_signals(random_pred, spec)
    # 这里简化：不实际跑 backtest，只比较信号集大小
    actual_signal_count = full_artifacts.run.signals
    random_signal_density = float(random_signals_entry.sum()) / max(len(random_pred), 1)
    actual_density = actual_signal_count / max(len(training.full_predictions), 1)
    lift_evidence = {
        "random_signal_density": random_signal_density,
        "actual_signal_density": actual_density,
        "actual_sharpe": actual_sharpe,
    }
    checks.append(GateResult(
        name="ml_no_information_baseline",
        status="ok" if actual_sharpe > 0.3 else "warning",
        message=f"Actual Sharpe = {actual_sharpe:.2f} vs random baseline (signal density: actual={actual_density:.3f} vs random={random_signal_density:.3f})",
        evidence=lift_evidence,
    ))
    return checks


# build_promotion_report 末尾 append:
if spec.model is not None:
    checks.extend(_ml_specific_checks(spec, full_artifacts))
```

### 4.A.6 新 CLI

```python
@strategy_app.command("train")
def strategy_train_command(spec: Path) -> None:
    """Run rolling-window training once. Print feature importance + fold metrics."""
    from open_composer.research.ml_backend.training import run_rolling_training
    from open_composer.adapters.data import load_ohlcv_for_spec

    spec_obj = load_strategy_spec(spec)
    if spec_obj.model is None:
        raise typer.BadParameter("spec.model is None; not an ML strategy")
    frame = load_ohlcv_for_spec(spec_obj, project_root())
    training = run_rolling_training(spec_obj, frame, project_root())
    console.print(f"[green]training complete[/green] folds={len(training.folds)}")
    if training.folds:
        last = training.folds[-1]
        console.print(f"\nLast fold feature importance (top 10):")
        for name, imp in sorted(last.feature_importance.items(), key=lambda kv: kv[1], reverse=True)[:10]:
            console.print(f"  {name:40s} {imp:.4f}")
        console.print(f"\nTrain metrics: {last.train_metrics}")
        console.print(f"Test metrics:  {last.test_metrics}")


@strategy_app.command("explain")
def strategy_explain_command(run_id: str) -> None:
    """LLM-narrated explanation of a recent ML run (for 7.C.L2; stub in 7.A)."""
    console.print("[yellow]explain command stub — full implementation in Step 7.C[/yellow]")
```

### 4.A.7 测试

`tests/test_ml_backend.py`：

```python
"""ML backend integration tests on synthetic data."""
from __future__ import annotations
from pathlib import Path
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def _make_ml_spec(tmp_path: Path) -> Path:
    spec_yaml = {
        "name": "test_ml_spec",
        "description": "ML test on syn_daily",
        "timeframe": "daily",
        "universe": ["SYN"],
        "lifecycle": "draft",
        "entry": {"all": [], "any": ["close > 0"]},
        "exit": {"all": [], "any": ["close < 0"]},
        "risk": {"max_trades_per_day": 1, "max_position_weight": 1.0},
        "costs": {"commission_pct": 0.0, "slippage_bps": 0.0, "impact_model": "linear",
                  "impact_eta": 0.0, "impact_gamma": 0.0},
        "execution": {"backend": "python_reference", "mode": "manual_signal",
                       "signal_on": "bar_close", "fill_assumption": "next_bar_open",
                       "broker": "none"},
        "data": {"source": "sample", "symbol": "SYN", "path": "data/sample/syn_daily.csv"},
        "data_assumptions": {"source": "sample", "adjusted": True, "timezone": "America/New_York"},
        "factors": {
            "mom_5": {"source": "expression", "expression": "(close - lag(close, 5)) / lag(close, 5)"},
            "mom_20": {"source": "expression", "expression": "(close - lag(close, 20)) / lag(close, 20)"},
            "vol_20": {"source": "expression", "expression": "stddev(close, 20)"},
        },
        "model": {
            "kind": "lightgbm_regressor",
            "label": {"type": "forward_return", "horizon_bars": 5},
            "features": ["mom_5", "mom_20", "vol_20"],
            "training": {"window_bars": 200, "retrain_every_bars": 50, "cv_splits": 3, "test_window_bars": 50},
            "selection": {"method": "threshold", "threshold": 0.005, "rebalance": "weekly"},
        },
        "llm_review": {"enabled": False},
        "notes": {"intent": "ML test"},
        "required_capabilities": [],
    }
    path = tmp_path / "test_ml_spec.yaml"
    path.write_text(yaml.safe_dump(spec_yaml, sort_keys=False), encoding="utf-8")
    return path


def test_rolling_training_runs_on_syn_daily(tmp_path, monkeypatch):
    monkeypatch.chdir(ROOT)
    from open_composer.models.strategy_spec import load_strategy_spec
    from open_composer.adapters.data import load_ohlcv_for_spec
    from open_composer.research.ml_backend.training import run_rolling_training

    spec_path = _make_ml_spec(tmp_path)
    spec = load_strategy_spec(spec_path)
    frame = load_ohlcv_for_spec(spec, ROOT)
    run = run_rolling_training(spec, frame, ROOT)
    assert len(run.folds) >= 3
    assert run.full_predictions is not None
    # 每个 fold feature importance 都非空
    for fold in run.folds:
        assert sum(fold.feature_importance.values()) > 0


def test_ml_spec_backtest_engine_integration(tmp_path, monkeypatch):
    """Full backtest_frame() must dispatch to ML branch when spec.model set."""
    monkeypatch.chdir(ROOT)
    from open_composer.models.strategy_spec import load_strategy_spec
    from open_composer.adapters.data import load_ohlcv_for_spec
    from open_composer.engines.backtest_engine import backtest_frame

    spec_path = _make_ml_spec(tmp_path)
    spec = load_strategy_spec(spec_path)
    frame = load_ohlcv_for_spec(spec, ROOT)
    artifacts = backtest_frame(spec, frame, root=ROOT, run_id_value="test_ml")
    assert artifacts.run.bars == len(frame)
    # ML 模型应该产生少量信号（threshold 限制）
    assert artifacts.run.signals >= 0


def test_no_lookahead_in_feature_pipeline():
    """Critical: y at time t must not leak into training data ending at t."""
    import numpy as np
    import pandas as pd
    from open_composer.research.ml_backend.feature_pipeline import slice_train_test
    X = pd.DataFrame({"f1": range(100)}, index=range(100))
    y = pd.Series(range(100), index=range(100))
    X_tr, y_tr, X_te, y_te = slice_train_test(X, y, retrain_t=80, window_bars=50, test_bars=10)
    # 训练集不能含 test 区间索引
    assert X_tr.index.max() < 80
    assert y_tr.index.max() < 80
```

### 4.A.8 路径 7.A 验收

```text
[ ] pyproject.toml 加 lightgbm + optuna + scikit-learn
[ ] open_composer/research/ml_backend/ 6 文件就位
[ ] StrategySpec.model 段 (MLModelConfig + 4 sub-models) schema 通过
[ ] backtest_frame 检测 spec.model is not None 时走 ML 分支
[ ] promotion 增加 3 项 ML-only check
[ ] oc strategy train CLI 可输出特征重要性
[ ] tests/test_ml_backend.py 3 个测试全过
[ ] 无 lookahead 测试明确隔离 train/test
[ ] .venv/bin/pytest tests/ -q 全绿
[ ] .venv/bin/oc repo check --strict 通过
```

预计工作量：~1500-2000 行 + 测试，1 个会话完成。

---

## 5. 路径 7.B — 衰减监控（无条件做，作为安全网）

### 4.B.1 触发

任何 active 策略部署 ≥ 4 周后启用。**建议 7.A / 7.C 之前先做这一条，因为基础设施**。

### 4.B.2 schema 与数据流

每个 active 策略每周（cron 或 Dashboard 触发）跑一次：

```text
reports/factors/{factor_id}/decay-monitor.jsonl

每行：
{
  "monitor_ts": "2026-06-13T03:00:00Z",
  "rolling_12m_rank_ic": 0.045,
  "rolling_12m_ir": 0.62,
  "rolling_3m_rank_ic": 0.038,
  "ic_historical_25pct": 0.040,
  "ic_historical_50pct": 0.052,
  "ic_historical_75pct": 0.068,
  "decay_alert": false,
  "alert_reason": null,
  "specs_using_factor": ["nasdaq_tqqq_momentum_iter3", "qqq_pullback_15m"],
  "sample_size": 252
}
```

### 4.B.3 新模块

`open_composer/research/factor_decay.py`（约 250 行）：

```python
"""Factor decay monitoring: track rolling IC/IR vs historical distribution.

Triggers an alert when rolling 3-month rank IC falls below historical 25th percentile.
"""
from __future__ import annotations
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from open_composer.adapters.data import load_ohlcv_for_spec
from open_composer.config import ensure_dir, project_root
from open_composer.expressions import evaluate_expression, prepare_factor_frame
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.notifications import safe_dispatch_notification
from open_composer.research.factor_library import get_factor, materialize_expression
from open_composer.research.factor_lineage import _relpath
from open_composer.storage import append_jsonl


def monitor_factor_decay(
    factor_id: str,
    *,
    rolling_3m_bars: int = 63,
    rolling_12m_bars: int = 252,
    horizon_bars: int = 5,
    historical_lookback_bars: int = 1260,    # 约 5 年
    root: Path | None = None,
) -> dict[str, Any]:
    """Compute rolling IC vs historical distribution for one factor.

    Uses the latest spec that consumes this factor (read from lineage.json).
    """
    base = root or project_root()
    lineage_path = base / "reports" / "factors" / factor_id / "lineage.json"
    if not lineage_path.exists():
        raise FileNotFoundError(f"no lineage for {factor_id}; run oc factor use-in first")
    lineage = json.loads(lineage_path.read_text(encoding="utf-8"))
    used_specs = lineage.get("used_in_specs", [])
    if not used_specs:
        raise ValueError(f"factor {factor_id} not used in any spec")
    sample_spec_path = base / used_specs[-1]["spec_path"]
    spec = load_strategy_spec(sample_spec_path)
    frame = load_ohlcv_for_spec(spec, base)

    factor = get_factor(factor_id)
    rendered = materialize_expression(factor, {})
    prepared = prepare_factor_frame(frame, {factor_id: spec.factors.get(factor_id) or _stub_factor_config(rendered)}, root=base)
    signal = evaluate_expression(factor_id, prepared)
    fwd = frame["close"].pct_change(horizon_bars).shift(-horizon_bars)

    # rolling IC series
    rolling_ics = []
    for i in range(rolling_3m_bars, len(signal)):
        win = slice(i - rolling_3m_bars, i)
        s = signal.iloc[win].rank()
        f = fwd.iloc[win].rank()
        if s.notna().sum() > 30 and s.std() > 0 and f.std() > 0:
            rolling_ics.append((signal.index[i], float(s.corr(f))))
    if not rolling_ics:
        return {"factor_id": factor_id, "error": "insufficient_data", "monitor_ts": _now()}
    rolling_series = pd.Series([v for _, v in rolling_ics])

    # historical distribution
    hist = rolling_series.iloc[:-rolling_3m_bars] if len(rolling_series) > rolling_3m_bars else rolling_series
    historical_25 = float(hist.quantile(0.25))
    historical_50 = float(hist.quantile(0.50))
    historical_75 = float(hist.quantile(0.75))
    current_3m = float(rolling_series.tail(rolling_3m_bars).mean())
    current_12m = float(rolling_series.tail(rolling_12m_bars).mean()) if len(rolling_series) >= rolling_12m_bars else current_3m
    ir_12m = float(rolling_series.tail(rolling_12m_bars).mean() / max(rolling_series.tail(rolling_12m_bars).std(), 1e-6)) if len(rolling_series) >= rolling_12m_bars else None

    alert = current_3m < historical_25
    alert_reason = None
    if alert:
        alert_reason = (
            f"3m rank IC ({current_3m:.3f}) below historical 25th percentile ({historical_25:.3f}); "
            f"alpha decay suspected"
        )

    record = {
        "monitor_ts": _now(),
        "rolling_3m_rank_ic": current_3m,
        "rolling_12m_rank_ic": current_12m,
        "rolling_12m_ir": ir_12m,
        "ic_historical_25pct": historical_25,
        "ic_historical_50pct": historical_50,
        "ic_historical_75pct": historical_75,
        "decay_alert": alert,
        "alert_reason": alert_reason,
        "specs_using_factor": [u["spec_path"] for u in used_specs],
        "sample_size": len(rolling_series),
    }

    out_dir = ensure_dir(base / "reports" / "factors" / factor_id)
    append_jsonl(out_dir / "decay-monitor.jsonl", [record])

    if alert:
        safe_dispatch_notification(
            kind="signal_alert",
            severity="warn",
            title=f"Factor {factor_id} alpha decay",
            body=alert_reason or "",
            metadata={"factor_id": factor_id, "specs": record["specs_using_factor"]},
            root=base,
        )
    return record


def monitor_all_active_factors(root: Path | None = None) -> list[dict[str, Any]]:
    base = root or project_root()
    factors_dir = base / "reports" / "factors"
    if not factors_dir.exists():
        return []
    results = []
    for d in sorted(factors_dir.iterdir()):
        if not d.is_dir() or not (d / "lineage.json").exists():
            continue
        try:
            results.append(monitor_factor_decay(d.name, root=base))
        except Exception as exc:                                    # noqa: BLE001
            results.append({"factor_id": d.name, "error": str(exc)})
    return results


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _stub_factor_config(expression: str):
    from open_composer.models.strategy_spec import FactorConfig
    return FactorConfig(source="expression", expression=expression)
```

### 4.B.4 CLI

```python
@factor_app.command("decay-monitor")
def factor_decay_monitor_command(
    factor_id: Annotated[str | None, typer.Option("--factor-id")] = None,
) -> None:
    """Run one decay-monitor cycle. Without --factor-id, monitor all factors with lineage."""
    from open_composer.research.factor_decay import monitor_all_active_factors, monitor_factor_decay
    if factor_id:
        result = monitor_factor_decay(factor_id, root=project_root())
        console.print(result)
    else:
        results = monitor_all_active_factors(project_root())
        table = Table(title=f"Decay Monitor — {len(results)} factors")
        table.add_column("factor")
        table.add_column("3m IC")
        table.add_column("12m IR")
        table.add_column("alert")
        for r in results:
            alert = "[red]⚠[/red]" if r.get("decay_alert") else "[green]ok[/green]"
            table.add_row(
                r.get("factor_id", "n/a"),
                f"{r.get('rolling_3m_rank_ic', 0):.3f}",
                f"{r.get('rolling_12m_ir') or 0:.2f}",
                alert,
            )
        console.print(table)


@factor_app.command("decay-report")
def factor_decay_report_command(
    days: Annotated[int, typer.Option("--days")] = 90,
) -> None:
    """Aggregate decay history; show factors with consecutive alerts."""
    import json
    from datetime import datetime, timedelta, UTC
    factors_dir = project_root() / "reports" / "factors"
    cutoff = datetime.now(UTC) - timedelta(days=days)
    table = Table(title=f"Decay Report (last {days} days)")
    table.add_column("factor")
    table.add_column("checks")
    table.add_column("alerts")
    table.add_column("latest 3m IC")
    table.add_column("status")
    for d in sorted(factors_dir.iterdir() if factors_dir.exists() else []):
        decay_path = d / "decay-monitor.jsonl"
        if not decay_path.exists():
            continue
        rows = [json.loads(line) for line in decay_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        rows = [r for r in rows if datetime.fromisoformat(r.get("monitor_ts", "1970-01-01T00:00:00Z").replace("Z", "+00:00")) >= cutoff]
        if not rows:
            continue
        alerts = sum(1 for r in rows if r.get("decay_alert"))
        status = "[red]⚠ retire?[/red]" if alerts >= 3 else "[yellow]watch[/yellow]" if alerts >= 1 else "[green]healthy[/green]"
        table.add_row(d.name, str(len(rows)), str(alerts), f"{rows[-1].get('rolling_3m_rank_ic', 0):.3f}", status)
    console.print(table)


@factor_app.command("retire")
def factor_retire_command(factor_id: str, reason: Annotated[str, typer.Option("--reason")] = "") -> None:
    """Mark factor as retired; update lineage; warn affected specs."""
    import json
    from datetime import datetime, UTC
    lineage_path = project_root() / "reports" / "factors" / factor_id / "lineage.json"
    if not lineage_path.exists():
        raise typer.BadParameter(f"factor {factor_id} has no lineage")
    data = json.loads(lineage_path.read_text(encoding="utf-8"))
    data["retired_at"] = datetime.now(UTC).isoformat()
    data["retirement_reason"] = reason
    lineage_path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    console.print(f"[yellow]factor retired[/yellow] {factor_id}")
    if data.get("used_in_specs"):
        console.print(f"Affected specs:")
        for u in data["used_in_specs"]:
            console.print(f"  - {u['spec_path']}")
```

### 4.B.5 Dashboard 集成（最小）

`open_composer/dashboard/server.py` 加 `/api/factors/{factor_id}/decay` 端点：

```python
def build_factor_decay_payload(root: Path, factor_id: str) -> dict[str, Any]:
    import json
    decay_path = root / "reports" / "factors" / factor_id / "decay-monitor.jsonl"
    if not decay_path.exists():
        return {"factor_id": factor_id, "history": [], "latest": None}
    rows = [json.loads(line) for line in decay_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return {
        "factor_id": factor_id,
        "history": rows[-90:],
        "latest": rows[-1] if rows else None,
        "alert_count_last_90": sum(1 for r in rows[-90:] if r.get("decay_alert")),
    }
```

Dashboard 前端：在已有 LLM Factors tab 旁加 "Factor Catalog" tab（约 200 行 React），列 ≥80 因子 + 衰减状态颜色。

### 4.B.6 Cron 部署

`deploy/cron/factor-decay-monitor.sh`：

```bash
#!/bin/bash
# Run weekly on Sunday 03:00 server time.
# crontab -e:
#   0 3 * * 0 /srv/open-composer/repo/deploy/cron/factor-decay-monitor.sh

cd /srv/open-composer/repo
.venv/bin/oc factor decay-monitor 2>&1 | tee -a reports/factors/_cron.log
```

文档说明放进 `docs/remote-dashboard-deploy.zh.md`。

### 4.B.7 路径 7.B 验收

```text
[ ] open_composer/research/factor_decay.py 完整
[ ] reports/factors/{factor_id}/decay-monitor.jsonl 写入
[ ] oc factor decay-monitor / decay-report / retire 3 CLI 通过测试
[ ] Telegram 报警渠道（用现有 safe_dispatch_notification）
[ ] Dashboard /api/factors/{id}/decay 端点
[ ] Dashboard Factor Catalog tab（含衰减颜色）
[ ] cron 脚本 + 文档
[ ] tests/test_factor_decay.py 覆盖 alert 阈值与无 lineage 错误
[ ] make verify 通过
```

预计工作量：~1200 行 + 测试 + 前端，1 个会话完成。

---

## 6. 路径 7.C — LLM 三角色

### 4.C.1 触发

**L1 propose**：≥ 5 个 auto research run 后选中的 factor 集合高度重叠（top 5 因子在 ≥ 60% 策略中出现）→ 需要新维度。

**L2 explain**：执行 7.A 后 ML 模型 feature importance 难解读（用户看不懂为什么 fold-1 重 mom_5，fold-3 重 vol_20）。

**L3 backfill**：执行 7.B 后想给已有 `qqq_news_regime_15m` 全历史 materialize + 加 2-3 个新 LLM factor。

### 4.C.2 L1 — `oc factor propose <thesis>`

新增 `open_composer/research/factor_propose.py`（约 350 行）：

核心逻辑：
1. LLM 看 thesis + ALL_FACTORS catalog 摘要 + 用户 `--base-factors` 提示
2. structured output 约束 LLM 只输出新候选 `FactorDefinition` JSON（不能输出 catalog 已有 id）
3. 沙箱 AST 验证 expression
4. 自动跑 single-factor IC（复用 auto_research.py 的 `_run_single_factor_ic`）
5. IC 通过阈值（rank IC > 0.02 且 IR > 0.3 且与现有 ≥ 1 个 factor Spearman corr < 0.7）才写入 `reports/factor_proposals/{date}-batch.jsonl`
6. 人工 review 后用 `oc factor approve <proposal_id>` 升级到 `factor_library.py`（追加到 USER_PROPOSED_LIBRARY tuple）

```python
@dataclass
class FactorProposal:
    proposal_id: str        # date + slug
    thesis: str
    proposed_definition: dict[str, Any]    # 序列化的 FactorDefinition
    ic_score: float
    ir_score: float
    correlation_with_existing: dict[str, float]
    status: Literal["pending_review", "approved", "rejected"]
    created_at: str


def propose_factors(thesis, base_factors, *, max_candidates=10, root=None):
    # 1. 调 LLM
    # 2. 沙箱验证
    # 3. IC 测试
    # 4. 与现有因子相关性
    # 5. 写 reports/factor_proposals/
    ...

@factor_app.command("propose")
def factor_propose_command(
    thesis: str,
    base_factors: Annotated[str | None, typer.Option("--base-factors")] = None,
    max_candidates: Annotated[int, typer.Option("--max-candidates")] = 10,
) -> None:
    """Use LLM to propose new factor expressions beyond the existing catalog."""
    proposals = propose_factors(thesis, base_factors.split(",") if base_factors else [], max_candidates=max_candidates)
    accepted = [p for p in proposals if p.status == "pending_review"]
    console.print(f"[green]{len(accepted)} candidates passed initial gates[/green]")
    for p in accepted:
        console.print(f"  {p.proposal_id} IC={p.ic_score:.3f} IR={p.ir_score:.2f}")


@factor_app.command("approve")
def factor_approve_command(proposal_id: str) -> None:
    """Promote a passing proposal into factor_library.py USER_PROPOSED_LIBRARY."""
    # 读 reports/factor_proposals/{proposal_id}.json
    # 写入 factor_library.py USER_PROPOSED_LIBRARY tuple（追加 Python 代码块）
    # git stage 但不 commit；让 codex/用户 review 后 commit
    ...
```

### 4.C.3 L2 — `oc strategy explain <run_id>`

新增 `open_composer/research/llm_explainer.py`（约 200 行）：

```python
"""LLM-narrated explanation of ML training results.

Input: a recent run_id (run artifacts under reports/backtests/{run_id}.md
       and reports/research/{spec}-ml-training.json)
Output:
  - reports/research/{spec}-explanation.md
  - trace.jsonl row with operation="llm_explain"
  - promotion report 末尾追加 "Model Interpretation" 段
"""


def explain_ml_run(run_id, root=None):
    base = root or project_root()
    # 1. 找 ML training JSON（fold feature importance + train/test metrics）
    # 2. 找最近 10 个错例（实际收益方向与预测相反 top 10）
    # 3. 构造 prompt：spec.factors 描述 + fold importance 表 + 错例
    # 4. 调 LLM (structured output): {summary, top_drivers, failure_modes, suggestions}
    # 5. 写 explanation.md + trace.jsonl + 追加 promotion.md
    ...

@strategy_app.command("explain")
def strategy_explain_command(run_id: str) -> None:
    """LLM-narrated explanation of an ML run."""
    from open_composer.research.llm_explainer import explain_ml_run
    result = explain_ml_run(run_id, project_root())
    console.print(f"[green]explanation written[/green] {result.explanation_path}")
```

### 4.C.4 L3 — 全历史 materialize 现有 LLM 策略

```bash
.venv/bin/oc feature materialize strategy_specs/drafts/qqq_news_regime_15m.yaml \
  --factor news_regime_score --refresh

# 验证 packets 数从 16 涨到 ~3000+
wc -l reports/features/qqq_news_regime_15m/news_regime_score/packets.jsonl
```

如果想加新 LLM factor：

1. 在 `prompts/` 新建 `sentiment_score.md` + `earnings_surprise.md` + `macro_regime_score.md`
2. 在某 spec 中加 `source: llm_feature` 引用
3. `oc feature materialize` 跑全历史
4. `oc strategy evidence` 验证 5 项 marginal lift checks

### 4.C.5 路径 7.C 验收

```text
[ ] open_composer/research/factor_propose.py + factor_approve 流程
[ ] LLM structured output 限制不能输出 catalog 已有 id
[ ] 沙箱 AST 验证 + IC > 0.02 + 与现有 corr < 0.7 才入 pending
[ ] reports/factor_proposals/{date}-batch.jsonl 写入
[ ] open_composer/research/llm_explainer.py + oc strategy explain 命令
[ ] LLM explanation 写入 explanation.md + trace.jsonl + promotion.md 追加
[ ] qqq_news_regime_15m 全历史 backfill 完成（packets ≥ 1000）
[ ] tests/test_factor_propose.py + test_llm_explainer.py
[ ] make verify 通过
```

预计工作量：~1500 行（L1: 800 + L2: 500 + L3: 200），1-2 个会话。

---

## 7. 三条路径互不依赖证明

```text
7.A 独立：
  - 改 StrategySpec.model
  - 新增 ml_backend/ 目录
  - 加 backtest_frame ML 分支
  - 不动 factor_library / auto_research / decay 监控

7.B 独立：
  - 新增 factor_decay.py
  - 新增 decay CLI / 端点 / Dashboard tab
  - 不依赖 ML（7.A）
  - 不依赖 LLM propose（7.C）

7.C 独立：
  - L1 改 factor_propose.py + approve 流程
  - L2 改 llm_explainer.py（仅当 7.A 存在时有上下文；否则可跑在规则策略 trace 上）
  - L3 仅是 materialize 命令使用
  - 不动 ML backend / 衰减监控

任意组合可并发开发 → 不必排序。
```

## 8. 全局决策树

```text
[ 启动条件 ] Step 6 已发，跑 ≥ 5 个 oc research auto thesis

[ 数据收集 ] 检视：
  • 各 thesis 的 max abs(rank IC)
  • Step 6 选中的 factor 集合是否高度重叠
  • 任何 active 策略部署天数

[ 决策 ]
  if 任何 active ≥ 4 周
      → 7.B 必做（始终）
  if ≥ 60% thesis 的 max IC < 0.02
      → 7.A 必做（ML 提升表达力）
  if 5 + thesis 选中同一 ≤ 3 个核心 factor
      → 7.C.L1 propose 必做（catalog 多样性不足）
  if 7.A 已做且 feature importance 难解释
      → 7.C.L2 explain 必做
  其余 → 不做，看 Step 6 + 7.B 是否够用
```

## 9. 不做什么

```text
✗ 不引入 PyTorch / Transformer 端到端
✗ 不引入 deep RL
✗ 不引入 Qlib qrun / DataHandler / workflow
✗ 不让 LLM 直接生成 entry/exit rule（结构化 propose 限定到 factor 级别）
✗ 不动 4-pass / harness / paper safety
✗ 不动 Step 6 的 factor_library / auto_research
✗ 不让 7.A 改成支持 cross-sectional rank（个人量化默认场景外）
✗ 7.B 不强制 daily cron（可手工 oc factor decay-monitor 触发）
```

## 10. 风险与对冲

| 风险 | 对冲 |
|---|---|
| 7.A 引入 lightgbm 50MB 体积膨胀 | 写 docstring；个人量化必要代价；可选 import |
| 7.A label leakage（最致命 ML bug） | `slice_train_test` 显式裁剪最后 horizon 行；测试断言隔离 |
| 7.A Optuna 在每个 fold 调参导致 1 次 backtest 跑数小时 | 默认 optuna_trials=None 关闭；用户显式 opt-in；50 trial 限上限 |
| 7.A feature importance 不一致（adjacent fold Jaccard < 0.3） | 直接 blocked promotion；强制返回 schema rewrite |
| 7.B 历史 IC 分布样本不足（新 factor < 1 年数据） | 阈值改 50% 历史代替 25%；明确 status="insufficient_data" |
| 7.B 报警过频 | 24 小时内同 factor 仅一次报警；可配置 cooldown |
| 7.C.L1 LLM 输出 catalog 已有 factor_id | OpenAI structured output enum 排除已有 ID |
| 7.C.L1 LLM 输出过拟合表达式（如 `(close - lag(close, 1) + lag(close, 2) - lag(close, 3) + ...)`）| AST 验证 + IC 阈值 + 与现有相关性 < 0.7 三道闸门 |
| 7.C.L2 LLM 解释幻觉（把噪声当模式） | 仅用 structured output；明确 "I see X, NOT Y, suggests Z" 三段式 |
| 7.C.L3 全历史 materialize 触发大量 OpenAI 调用 | 用户已确认 token 不是约束；提供 `--limit-bars N` 参数控制 |

## 11. 路径选择推荐（写给执行 agent）

```text
推荐执行顺序（如果三条都触发）：
  1. 7.B 衰减监控（最低风险，所有路径都受益的基础设施）
  2. 7.A ML backend（最高 ROI；触发条件最常见）
  3. 7.C 在 7.A 之后做（L2 explain 需要 ML 模型；L1 propose 需要看 7.A 训练后 feature importance 决定 catalog 缺什么）

  → 7.B → 7.A → 7.C.L2 → 7.C.L1 → 7.C.L3

如果时间紧只做一条：
  if 用户感觉策略 IC 普遍弱 → 7.A
  if 用户感觉已有 active 策略难管理 → 7.B
  if 用户想加 news/macro → 7.C.L3 (最快)
```

## 12. 完成定义

完成本步骤选择的路径（≥ 1 条）后：

- **7.A**：StrategySpec 可声明 `model:` 段，backtest 自动走 LightGBM 滚动训练 + Optuna 调参；promotion 3 项 ML gate；Codex/Claude 可用 `oc strategy train` 看特征重要性
- **7.B**：每个 active 策略的 factor 自动衰减监控；Telegram 报警；Dashboard 显示 factor catalog 衰减状态
- **7.C.L1**：`oc factor propose` 让 LLM 在 catalog 外挖新候选；通过 3 道闸门才入 pending review
- **7.C.L2**：`oc strategy explain` 让 LLM 解读 ML 模型 feature importance + 错例
- **7.C.L3**：全 LLM 策略 backfill；2-3 个新 LLM factor 入库

完成后，Open Composer 达到「个人 AI 量化工作台 v2.0」状态：
1. 用户描述 thesis → AI 选 catalog 因子 → 跑 IC → 生成 spec（Step 6）
2. 若 IC 弱 → AI 自动转 ML（7.A）
3. 上线后 → 自动衰减监控 + 报警（7.B）
4. 想加新维度 → LLM 提候选 → 入 catalog（7.C.L1）
5. 模型黑箱 → LLM 解释（7.C.L2）

## 13. 执行顺序总览（写给无上下文 Codex）

```text
[ 前置 ] Step 6 已完成；oc research auto 已可用

[ 决策 ] 跑 §4.A.0 触发判断脚本 + §4.B / §4.C 各自触发条件

[ 路径 1：7.B 衰减监控 (推荐先做) ]
  4.B.2 → 4.B.7  约 4-5 小时

[ 路径 2：7.A ML Backend (条件触发) ]
  4.A.1 → 4.A.8  约 6-8 小时

[ 路径 3：7.C LLM 三角色 (条件触发) ]
  4.C.2 → 4.C.5  约 4-6 小时

每条独立 PR；每条完成后跑：
  .venv/bin/pytest tests/ -q
  .venv/bin/oc repo check --strict
  make verify
```

---

完成 Step 7 后，路线图收官。建议执行顺序：

```text
Today:   Step 6 G1（一个会话，3-4 小时）
+1 周:   测试 Step 6 输出，跑 ≥ 5 个 thesis
+1 周后: 按触发条件选 Step 7 路径
+2 周:   Step 7.B（必做）+ Step 7.A 或 7.C（按数据决定）
进入日常: 用 oc research auto 每天/每周生成新策略，依赖衰减监控控制 portfolio
```
