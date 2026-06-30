# Open Composer Step 7.A：ML 训练后端（非线性因子组合 + 防过拟合闸门）

日期：2026-06-30
执行者：Codex / Claude Code
前置：Step 6（因子库 + `oc research auto`）、Step 6.5（IC/IR selection 修复）、Step 6.6（strict_data 加固）、Step 6.7（方向化 composite 可交易信号）、6.8 + IR gating commit `c39c487` 均已完成
后续：Step 7.A.2（cross-sectional 多标的 ML，可选）、Step 7.B（衰减监控）、Step 7.C（LLM 三角色，暂缓）

> 本文档**取代** `plan-step-7-conditional-ml-decay-llm-2026-05-26.zh.md` 中的 7.A 部分。旧文档写于 6.5–6.8 之前，其 ML 设计假设已过时（详见 §2）。7.B/7.C 仍以旧文档为准，但本步骤只做 7.A。

---

## 0. 一句话目标

给 `StrategySpec` 加一个可选 `model:` 段，用 **LightGBM 在已选因子上做非线性组合**，通过**无前视的 purged+embargo walk-forward** 训练，并**复用仓库已有的 DSR/PBO 闸门**评估过拟合。**硬约束：ML 策略只有在真实 OOS 上「成本后、DSR 校正后」打败 6.7 的线性 composite 基线，才允许进入可晋级状态；打不赢就如实留在 draft（负结果也是有效结果）。**

这一步把产品从「线性 + 阈值因子组合」推进到「机构标准的 GBDT 因子组合」，但**不放松任何防过拟合纪律**。

---

## 1. 背景（无上下文也能看懂）

Open Composer 是个人 AI 量化策略工作台。`oc research auto "<thesis>"` 让 AI 自动跑「选因子 → 单因子 IC/IR → 生成 StrategySpec → 回测 → evidence → promotion」流水线。

Step 6.7 修好了信号生成：现在 `_draft_spec` 用**方向化 composite z-score**（按 rank IC 符号定方向、\|IC\|<0.02 跳过、阈值进出场）产出非空可交易信号（真实 QQQ daily 513 bar → 64 signals / 32 trades）。**这是当前的线性基线。**

但线性 composite 的表达力 = 「深度 1 的线性决策」。机构标准做法是 **GBDT（LightGBM）在因子上做非线性组合 + 滚动重训**（参考 Microsoft Qlib Alpha158 baseline）。Step 7.A 在不破坏现有流水线的前提下，**条件性**地补上这一层。

---

## 2. 关键发现：为什么这版计划和旧 Step 7 文档不一样

执行前我核对了当前代码与 76 个真实 auto-research run，有四个发现直接改写了 7.A 的设计：

### 发现 1：旧文档的「弱 IC」触发条件**不成立**

旧文档 §4.A.0 的触发判据是「≥60% 策略 max\|rank IC\|<0.02 → 上 ML」。实跑当前 76 个 run：

```text
auto-research runs with IC: 76
with max abs(rank_ic) < 0.02: 2 (3%)        ← 远低于 60% 阈值
runs with a usable factor (|IC|>=0.02): 74 ; median best IC = 0.0960
```

**结论：因子不弱。** ML 的目的**不是**「拯救没有信号的弱因子」。真正的驱动力是旧文档决策表里的**第二条**触发：「≥3 个策略 OOS 不稳定」——6.7 的 QQQ run 里 5 个选中因子有 **3 个 OOS IC 翻号**（train/test 符号不一致）。

→ **7.A 的正确目标改写为**：用非线性组合产出一个**比线性 composite 更稳的 OOS 表现**，而不是「制造信号」。这条 reframing 决定了下面的「必须打败 linear baseline」硬闸门。

### 发现 2：仓库已经有 purged/embargo walk-forward 与 DSR/PBO，**不要重造**

旧文档提议新建一个独立 `ml_backend/`，自带 rolling training 和一套**很弱**的过拟合检查（用「随机洗牌信号密度」当 baseline）。但当前代码里已有更专业的现成件：

```text
open_composer/research/kernel/windows.py
  PurgedEmbargoConfig(purged: bool, embargo_bars: int)     ← López de Prado purge+embargo
  ResearchWindowSplit(train/test start/end, rows, embargo)
  WalkForwardSlice(fold, train, test, selected_candidate_ids)
open_composer/research/kernel/trials.py
  TrialRecord / TrialLedger                                ← Optuna 多重检验账本
open_composer/research/pbo.py
  build_overfit_risk_report(...) / OverfitRiskResult
  _compute_dsr_proxy(...)  _compute_pbo_proxy(...)         ← DSR/PBO proxy 已实现
open_composer/research/parameter_sweep.py:808
  _compute_dsr_proxy(trial_count, best, mean, stddev)      ← 极值型 DSR proxy
open_composer/research/factor_lab.py
  prepare_factor_frame → joined["factor"]/["forward_return"] + rank_ic/IR
                                                            ← 现成的特征/标签管线
```

→ **7.A 复用这些**：walk-forward 用 `kernel/windows.py`，过拟合闸门用 `pbo.py` 的 DSR/PBO proxy + `kernel/trials.py` 账本，特征/标签管线复用 `factor_lab` 已有逻辑。**新增代码只有「LightGBM 训练 + 预测→信号 + ML 专属 gate 装配」，不重写 CV / DSR / PBO。**

### 发现 3：单标的 + 日线 = ML 最难加价值的场景（必须诚实对待）

当前 auto_research 是**单标的**（QQQ daily，约 500 bar）。5-bar horizon 的非重叠样本只有约 100 个；在 ~100 样本上训 GBDT 组合 5–30 个因子，**过拟合风险极高**。Web 调研也确认：在非平稳金融数据上，过参数化模型难泛化，GBDT 必须强正则 + 严格 walk-forward + embargo。

→ **Phase 1（本步骤）= 单标的 ML，但强制 shallow+正则 + DSR/PBO 闸门 + 必须打败线性 baseline。** 同时明确：**ML 在量化里真正的主场是 cross-sectional（多标的、截面排序）**（Qlib Alpha158 即截面）。把「多标的截面 ML」列为 **Step 7.A.2**（§9 路线），本步骤不做，但 schema 预留 `universe` 多标的扩展位。

### 发现 4：StrategySpec 还没有 `model:` 段

`strategy_spec.py:369` 的 `StrategySpec` 当前字段止于 `reality_model`（:392），**无 `model:` 字段**。`backtest_engine.py:162` 是 `entry_mask, exit_mask = signal_masks(spec, frame, root=root)` —— ML 分支在此之前插入即可，干净单点。

---

## 3. 目标 / 非目标

### 目标

1. `StrategySpec` 增加可选 `model: MLModelConfig | None`（None 时完全走现有规则路径，零行为变化）。
2. 新增 `open_composer/research/ml_backend/`：特征/标签管线（复用 `factor_lab`）、LightGBM 训练（复用 `kernel/windows.py` 的 purged+embargo walk-forward）、预测→信号。
3. `backtest_engine.backtest_frame` 在 `spec.model is not None` 时走 ML 分支产出 entry/exit mask，否则不变。
4. ML 专属 promotion 闸门，**复用 `pbo.py` 的 DSR/PBO proxy**，并新增**「打败线性 composite baseline」硬闸门**（同一标的、同一窗口，ML 的成本后 OOS 风险调整收益必须 ≥ 线性 composite，否则 `blocked`）。
5. 新 CLI：`oc strategy train`（跑一次滚动训练，打印 fold 指标 + feature importance）、`oc strategy backtest-walk-forward`（OOS 回测）、`oc strategy explain`（feature importance + 错例）。
6. **硬验收**：在真实 QQQ daily 上生成一个 ML spec，OOS 跑通，promotion 报告里同时给出 ML 与 linear baseline 两条曲线 + DSR/PBO + 是否打败 baseline 的结论。

### 非目标（明确不做）

- ✗ 不做 cross-sectional 多标的 ML（留 Step 7.A.2；本步骤 schema 预留但不实现）。
- ✗ 不引入 PyTorch / Transformer / deep RL（个人单卡单标的场景外）。
- ✗ 不接 Qlib qrun workflow（沿用 Step 6 决定：借鉴 Alpha158 因子，不接 workflow 引擎）。
- ✗ 不重写 CV / DSR / PBO / walk-forward（复用 `kernel/windows.py` + `pbo.py` + `kernel/trials.py`）。
- ✗ 不改 4-pass / harness / paper safety / strict_data tier（6.6 已正确）。
- ✗ 不改 `_select_top_k` / 6.7 的 `_draft_spec` 线性逻辑（线性路径是 ML 的对照基线，必须保持不动）。
- ✗ 不让 ML 直接触发交易：promotion 仍是唯一晋级路径；ML 打不赢 baseline 就留 draft。
- ✗ 不放松 promotion 的任何现有 sanity 阈值（5-signal / 5-trade / 成本 / benchmark family / OOS）。

---

## 4. 当前状态扫描（精确行号 + 可复用资产）

```text
open_composer/models/strategy_spec.py
  L369  class StrategySpec(BaseModel)
  L392    reality_model: RealityModel | None = None     ← 在其后加 model 字段
  L435  load_strategy_spec(...)                          ← extra="forbid"，新字段需进 schema

open_composer/engines/backtest_engine.py
  L148  def backtest_frame(spec, frame, root=None, ...)
  L162    entry_mask, exit_mask = signal_masks(spec, frame, root=root)   ← ML 分支插入点

open_composer/expressions.py
  L199  evaluate_expression(expression, frame) -> pd.Series
  L217  prepare_factor_frame(frame, factors, root=...)    ← 渐进解析，算所有因子列
  L166  assert_expression_safe(expression)

open_composer/research/factor_lab.py
  L93   prepared = prepare_factor_frame(...)              ← 复用：特征矩阵来源
  L165  _factor_metric(...) joined["factor"]/["forward_return"]  ← 复用：标签构造逻辑

open_composer/research/kernel/windows.py   ★ 复用 CV
  PurgedEmbargoConfig / ResearchWindowSplit / WalkForwardSlice

open_composer/research/kernel/trials.py    ★ 复用试验账本
  TrialRecord / TrialLedger

open_composer/research/pbo.py              ★ 复用过拟合闸门
  build_overfit_risk_report / _compute_dsr_proxy / _compute_pbo_proxy

open_composer/research/promotion.py
  L51   PromotionStatus = Literal["ok","warning","blocked"]
  build_promotion_report(...)  GateResult(...)            ← 末尾 append ML gate

open_composer/research/auto_research.py
  _draft_spec(...)                                        ← 可选：加 --model 时 emit model 段

open_composer/cli.py
  strategy_app（~L2200 已有 strategy_parameter_sweep）     ← 加 train/backtest-walk-forward/explain

pyproject.toml
  ⚠ 0 ML 依赖；需加 lightgbm + scikit-learn（optuna 可选，见 Wave 7.A.5）
```

---

## 5. 改动清单（按 Wave，逐 Wave 独立 commit）

### Wave 7.A.1 — 依赖 + StrategySpec `model:` schema（无行为变化）

**5.1 依赖**（`pyproject.toml`）：
```toml
"lightgbm>=4.5",
"scikit-learn>=1.5",
# optuna 暂不加；Wave 7.A.5 决定是否引入
```
`uv sync` 后体积约 +50MB，CPU 训练 500bar×30factor 秒级。

**5.2 schema**（`strategy_spec.py`，在 `RealityModel` 附近新增，`StrategySpec` 加字段）：
```python
class MLLabel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["forward_return", "forward_direction"] = "forward_return"
    horizon_bars: int = Field(default=5, ge=1, le=60)
    threshold_pct: float | None = None      # forward_direction 用

class MLTraining(BaseModel):
    model_config = ConfigDict(extra="forbid")
    window_bars: int = Field(default=378, ge=120)   # ~1.5y daily
    retrain_every_bars: int = Field(default=21, ge=5)
    test_window_bars: int = Field(default=63, ge=21)
    embargo_bars: int = Field(default=5, ge=0)       # ≥ horizon_bars 推荐
    seed: int = 42

class MLSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    method: Literal["threshold", "top_quantile"] = "threshold"
    threshold: float | None = None          # 预测值阈值；regression 默认 0
    quantile: float | None = None           # top_quantile 用，0<q<1

class MLModelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["lightgbm_regressor", "lightgbm_classifier"] = "lightgbm_regressor"
    label: MLLabel = Field(default_factory=MLLabel)
    features: list[str] = Field(min_length=1)   # 引用 spec.factors 的 key
    training: MLTraining = Field(default_factory=MLTraining)
    selection: MLSelection = Field(default_factory=MLSelection)
    hyperparameters: dict[str, Any] = Field(default_factory=dict)   # 透传 LGBM；缺省走保守正则
    baseline: Literal["linear_composite", "none"] = "linear_composite"  # 必须打败的基线

    @model_validator(mode="after")
    def _check(self) -> "MLModelConfig":
        if self.selection.method == "threshold" and self.selection.threshold is None:
            object.__setattr__(self.selection, "threshold", 0.0)  # regressor 缺省 0
        if self.selection.method == "top_quantile" and not self.selection.quantile:
            raise ValueError("selection.method=top_quantile requires 0<quantile<1")
        if self.training.embargo_bars < self.label.horizon_bars:
            # 不报错，但记录：embargo 应 ≥ horizon 才能完全消除标签重叠泄漏
            pass
        return self
```
`StrategySpec` 加：`model: MLModelConfig | None = None`（在 `reality_model` 之后）。

**5.3 校验**：`features` 里每个名字必须 ∈ `spec.factors`（在 `StrategySpec` 加一个 `model_validator`，None 时跳过）。

**测试**：`tests/test_strategy_spec_model.py`——合法 spec 解析、`features` 引用未声明因子报错、`top_quantile` 缺 quantile 报错、`model=None` 时旧 spec 不受影响（回归）。

> 本 Wave 结束：schema 就位，但没有任何 ML 行为。`oc spec validate` 对 model spec 通过。

---

### Wave 7.A.2 — 特征/标签管线 + 无前视 walk-forward（最高风险，最先写测试）

新增 `open_composer/research/ml_backend/feature_pipeline.py`：

```python
def build_feature_matrix(spec, frame, root) -> pd.DataFrame:
    """复用 prepare_factor_frame 算 spec.model.features 各列；返回与 frame 同 index 的 X。"""
    # prepared = prepare_factor_frame(frame, spec.factors, root=root)
    # X = pd.DataFrame({f: prepared[f] for f in spec.model.features})

def build_label(spec, frame) -> pd.Series:
    """forward_return = close.pct_change(h).shift(-h)；forward_direction = (fwd>=thr).int。
    末尾 h 行 label 为 NaN（无未来），必须保留 NaN 让下游 purge 丢弃。"""
```

新增 `ml_backend/windows.py`（**薄封装**，把 `kernel/windows.py` 的 `WalkForwardSlice` 用于 ML）：

```python
def ml_walk_forward_slices(n_rows, *, window_bars, test_window_bars,
                           retrain_every_bars, horizon_bars, embargo_bars) -> list[WalkForwardSlice]:
    """生成 purged+embargo 滚动切片。每个 fold：
       train = [t-window, t)；test = [t, t+test)；
       PURGE：丢掉 train 末尾 (horizon_bars) 行——其 label 落在 test 窗口（泄漏）。
       EMBARGO：train 末尾再额外丢 embargo_bars 行。
       复用 kernel.windows.PurgedEmbargoConfig 记录 purged=True, embargo_bars。"""
```

> **这是整步最容易出错、也最关键的部分**：label 是未来值，任何「训练用到了 ≥ test_start − horizon 的样本」都是前视泄漏。purge + embargo 必须在切片层强制，不能依赖调用方。

**测试（必须先写、覆盖泄漏）`tests/test_ml_no_lookahead.py`**：
1. **合成泄漏探针**：构造 `label = close.shift(-h)` 的「完美未来标签」，确认 purge 后 train 的最大 index < `test_start - h - embargo`（断言切片边界，杜绝泄漏）。
2. **特征矩阵无未来**：`build_feature_matrix` 任意行只依赖 ≤ 当前 bar（对一个已知因子如 `sma(close,20)` 做逐行核对）。
3. **label 对齐**：`build_label` 末尾 h 行为 NaN，且 `fwd[i]` 等于 `close[i+h]/close[i]-1`。
4. **embargo ≥ horizon 时 train/test label 时间无重叠**（断言）。

---

### Wave 7.A.3 — LightGBM 训练 + 预测→信号 + backtest 挂钩

新增 `ml_backend/model_factory.py`：
```python
def create_model(spec):
    """lightgbm_regressor/classifier；缺省保守正则（防小样本过拟合）：
       num_leaves=15, max_depth=4, min_child_samples=20, learning_rate=0.05,
       n_estimators=200, subsample=0.8, colsample_bytree=0.8, reg_lambda=1.0。
       spec.model.hyperparameters 覆盖缺省。"""
```

新增 `ml_backend/training.py`：
```python
@dataclass
class FoldResult:
    fold:int; train_rows:int; test_rows:int
    train_metric:float; test_metric:float       # regressor: rank-IC of pred vs label; clf: AUC
    feature_importance: dict[str,float]
    test_index: list; test_pred: list[float]

@dataclass
class MLTrainingRun:
    folds: list[FoldResult]
    full_predictions: pd.Series                 # 拼接所有 fold 的 OOS 预测（仅 test 段，无 train 段）
    feature_importance_mean: dict[str,float]

def run_rolling_training(spec, frame, root) -> MLTrainingRun:
    """对每个 WalkForwardSlice：fit(train) → predict(test)；只收集 OOS 预测。
       full_predictions 只含各 fold test 段（这是诚实的 OOS 曲线）。"""
```

新增 `ml_backend/prediction.py`：
```python
def predictions_to_signals(pred: pd.Series, spec, frame) -> tuple[pd.Series, pd.Series]:
    """按 spec.model.selection 把预测转 entry/exit mask（与 frame index 对齐）：
       threshold: entry = pred > threshold; exit = pred < threshold（或 < -threshold 对称）
       top_quantile: entry = pred >= rolling_quantile(pred, q)。
       pred 为 NaN（无预测/train 段）→ 不进场。"""
```

**backtest 挂钩**（`backtest_engine.py:162` 之前）：
```python
if spec.model is not None:
    from open_composer.research.ml_backend.training import run_rolling_training
    from open_composer.research.ml_backend.prediction import predictions_to_signals
    training = run_rolling_training(spec, frame, root or project_root())
    entry_mask, exit_mask = predictions_to_signals(training.full_predictions, spec, frame)
    frame.attrs["ml_training_run"] = training
else:
    entry_mask, exit_mask = signal_masks(spec, frame, root=root)
```

**测试 `tests/test_ml_backend_training.py`**：
- 在 `data/sample/syn_daily.csv`（长样本）上跑一个 regressor spec：fold 数 > 1、`full_predictions` 只覆盖 test 段、不含 NaN 泄漏、backtest 产出 ≥ 5 signals。
- 确定性：固定 seed 两次训练 `full_predictions` 完全一致。
- `model=None` 的旧 spec 回测结果与改动前逐 bar 一致（回归，保护规则路径）。

---

### Wave 7.A.4 — ML promotion 闸门（复用 DSR/PBO + 打败 baseline 硬闸门）

`promotion.py`，`build_promotion_report` 末尾（仅 `spec.model is not None`）append `_ml_specific_checks`：

1. **`ml_training_present`**：有 fold 才继续，否则 `blocked`。
2. **`ml_feature_importance_consistency`**：相邻 fold top-k 特征 Jaccard 均值；≥0.5 ok / ≥0.3 warning / else blocked（特征重要性漂移=不稳定）。
3. **`ml_oos_degradation`**：fold 平均 train_metric vs test_metric 衰减；<0.3 ok / <0.6 warning / else blocked。
4. **`ml_overfit_risk`（复用 `pbo.py`）**：把 fold OOS 分数序列喂给 `_compute_dsr_proxy`/`_compute_pbo_proxy`，DSR proxy>1 或 PBO proxy>0.5 → warning/blocked。把 fold 当作 trial 写入 `kernel/trials.py` 的 `TrialLedger`。
5. **★ `ml_beats_linear_baseline`（硬闸门，本步骤核心）**：
   - 同一 spec 临时关掉 `model`（用 6.7 线性 composite 规则）在**同一 OOS 窗口**回测 → baseline 曲线。
   - 指标用**成本后、DSR 校正后的 OOS 风险调整收益**（如 OOS Sharpe；样本少时辅以 hit-ratio + 累计收益）。
   - ML ≥ baseline → ok；持平（±5%）→ warning；ML < baseline → **blocked**，message 写明「ML 未跑赢线性基线，留 draft」。
   - 证据写 `reports/research/auto/{run}/ml_vs_baseline.json`（两条曲线 + 指标差）。

> 这条闸门把「ML 不能为上 ML 而上 ML」制度化：跑不赢线性就不晋级。这是对发现 1/3 的直接回应。

**测试 `tests/test_promotion_ml_gate.py`**：构造 ML 明显优/劣于 baseline 两个合成场景，断言 gate 分别 ok / blocked；DSR/PBO proxy 被正确调用。

---

### Wave 7.A.5 — CLI + （可选）Optuna + auto_research emit

**CLI**（`cli.py` strategy_app）：
- `oc strategy train <spec>`：跑 `run_rolling_training`，打印各 fold 指标 + `feature_importance_mean`；写 `reports/research/ml/{spec}/training.json`。
- `oc strategy backtest-walk-forward <spec>`：ML OOS 回测 + 写 report（含 ml_vs_baseline）。
- `oc strategy explain <spec>`：打印 feature importance 排序 + 最大错例（|pred−label| top-N），写 `explain.md`。

**Optuna（可选，默认关闭）**：只有当 `spec.model.optuna_trials` 设置时启用；在**每个 train 窗口内部**用 `kernel/windows.py` 再切 validation（purged），TPE 调参；**trials 数写入 `TrialLedger`，并把 best-trial 过 `_compute_dsr_proxy` 做多重检验校正**（trials 越多，DSR 要求越高）。若不引入 optuna 依赖，本 Wave 只留 `hyperparameters` 透传，Optuna 留作 7.A 的后续小 Wave。

**auto_research emit（可选）**：给 `oc research auto` 加 `--model lightgbm` flag；置位时 `_draft_spec` 额外 emit 一个 `model:` 段（features = 已选因子、baseline=linear_composite）。**缺省不置位**，保持 6.7 线性行为为默认。

**测试**：`oc spec validate` 对 emit 的 model spec 通过；`oc strategy train` 在 syn_daily 上 smoke 通过。

---

### Wave 7.A.6 — 真实 QQQ 硬验收（ML vs 线性基线）

```bash
# 1) 用 6.7 线性路径跑一个真实 QQQ baseline（已有）
.venv/bin/oc research auto "Trend continuation on QQQ daily." \
  --universe QQQ --timeframe daily --data-source alpaca --max-factors 5
# 2) 用同因子集生成 ML 变体（--model）
.venv/bin/oc research auto "Trend continuation on QQQ daily." \
  --universe QQQ --timeframe daily --data-source alpaca --max-factors 5 --model lightgbm
# 3) walk-forward OOS 回测 + 看 ml_vs_baseline
.venv/bin/oc strategy backtest-walk-forward strategy_specs/drafts/auto_*_qqq_*.yaml
```

**验收看 `ml_vs_baseline.json` + promotion report**：ML 是否在成本后 OOS 打赢线性 composite。**两种结果都算通过本步骤**：
- ML 打赢 → 记录，进入「可迭代 ML 策略」状态。
- ML 没打赢 → gate 如实 `blocked`、留 draft；这证明在单标的日线上线性已接近天花板 → 触发 §9 的 cross-sectional 路线决策。

---

## 6. 测试总览

```text
[ ] tests/test_strategy_spec_model.py        schema 解析 / 校验 / model=None 回归
[ ] tests/test_ml_no_lookahead.py            ★ 泄漏探针 / purge+embargo 边界 / label 对齐
[ ] tests/test_ml_backend_training.py        滚动训练 / OOS-only 预测 / 确定性 / 规则路径回归
[ ] tests/test_promotion_ml_gate.py          DSR/PBO 复用 / 打败 baseline gate ok+blocked
[ ] .venv/bin/ruff format . && .venv/bin/ruff check .
[ ] .venv/bin/pytest tests/ -q   全绿
[ ] .venv/bin/oc repo check --strict   status=ok ready=yes
[ ] make verify（产品面变更）
```

---

## 7. 验收清单

```text
[ ] StrategySpec.model 字段 + 4 个子模型（MLLabel/MLTraining/MLSelection/MLModelConfig）
[ ] features 必须引用 spec.factors（校验通过）
[ ] model=None 时回测逐 bar 与改动前一致（规则路径零回归）
[ ] feature_pipeline 复用 prepare_factor_frame；label 末尾 h 行 NaN
[ ] walk-forward 复用 kernel/windows.py；purge 丢 train 末尾 horizon 行 + embargo
[ ] ★ 合成泄漏探针测试通过：train 最大 index < test_start − horizon − embargo
[ ] LightGBM 缺省保守正则（num_leaves≤15, max_depth≤4, min_child_samples≥20）
[ ] full_predictions 只含 OOS（各 fold test 段），固定 seed 可复现
[ ] backtest_frame ML 分支只在 spec.model 时触发
[ ] promotion ML gate 复用 pbo.py 的 _compute_dsr_proxy/_compute_pbo_proxy
[ ] ★ ml_beats_linear_baseline 硬闸门：ML<baseline → blocked，写 ml_vs_baseline.json
[ ] oc strategy train / backtest-walk-forward / explain 三命令可用
[ ] 不放松任何现有 promotion sanity 阈值

★ 硬验收（真实数据）：
[ ] 真实 QQQ 上跑出 ML 变体，OOS 回测产出 ml_vs_baseline.json
[ ] promotion report 同时呈现 ML 与线性 baseline + DSR/PBO + 打败结论
[ ] data_profile acquisition_tier=research_strict 未被破坏（6.6 不回退）
```

---

## 8. 风险与对冲

| 风险 | 对冲 |
|---|---|
| **前视泄漏**（ML 头号风险）：label 是未来值 | purge+embargo 在切片层强制（复用 kernel/windows）；合成泄漏探针测试是 P0 must-pass；embargo_bars ≥ horizon_bars |
| 单标的 ~100 有效样本 → 过拟合 | 保守正则缺省 + DSR/PBO 闸门 + 必须打败线性 baseline；打不赢就 blocked（不强行晋级） |
| Optuna 调参本身过拟合验证集 | trials 写 TrialLedger，best-trial 过 DSR proxy 多重检验校正；Optuna 默认关闭 |
| ML 训练不确定性 → 结果不可复现 | 固定 seed；测试断言两次训练 full_predictions 一致 |
| 破坏现有规则路径 | spec.model 分支隔离；model=None 逐 bar 回归测试 |
| LightGBM 依赖体积/安装 | 仅 +lightgbm+sklearn（~50MB）；CPU 即可；不引入 GPU/torch |
| 「为上 ML 而上 ML」 | ml_beats_linear_baseline 硬闸门制度化；负结果如实记录 |
| 单标的天花板导致 ML 永远打不赢 | 这是有效信号 → 触发 §9 cross-sectional（多标的截面）路线，而非放松闸门 |

---

## 9. 后续路线（本步骤之后）

```text
Step 7.A.2  cross-sectional 多标的 ML（ML 真正主场）：
            universe=[多标的] → 截面特征矩阵（每 bar 多标的一截面）→ LightGBM 排序 →
            top_quantile 选股。样本量 ×N 标的，更接近 Qlib Alpha158。
            触发：本步骤 ML 在单标的上打不赢线性 baseline（发现 3 的预期）。
Step 7.B    因子衰减监控（无条件安全网）：reports/factors/{id}/decay-monitor.jsonl +
            oc factor decay-monitor/report；沿用旧文档 §5。
Step 7.C    LLM 三角色（propose/explain/factor）：暂缓，沿用旧文档 §6。
```

---

## 10. 回滚

每个 Wave 单独 commit。出问题 `git revert` 对应 Wave 即可。`spec.model=None` 是默认，ML 路径完全旁路——即使 ml_backend 有 bug，不带 model 的现有策略与流水线零影响。

---

## 11. 完成定义

执行完 7.A：
- `StrategySpec` 支持可选 `model:`；不带 model 的一切行为零变化。
- ML 走 **无前视 purged+embargo walk-forward**，OOS 预测诚实拼接。
- promotion **复用 DSR/PBO** 评估过拟合，并用**打败线性 baseline** 硬闸门把关。
- 真实 QQQ 上能产出 ML 变体并与线性 baseline 对照；**无论 ML 是否打赢，都得到一个诚实、可复现、防过拟合的结论**。
- 这时产品具备「线性 + GBDT 双路径，按证据择优」的能力，可以开始真正意义上的「生成 + 迭代 + 训练」循环。

---

## 12. 执行顺序（写给无上下文 Codex）

```text
1. 读本文档 + 旧 plan-step-7-...-2026-05-26.zh.md（仅作背景，7.A 以本文为准）
2. 复跑 §2 发现 1 的触发脚本，确认 reframing（弱 IC 触发不成立）
3. Wave 7.A.1：依赖 + StrategySpec model schema + 校验 + 测试（无行为）
4. Wave 7.A.2：feature/label 管线 + purged+embargo walk-forward（复用 kernel/windows）
   —— ★ 先写 tests/test_ml_no_lookahead.py，再写实现，泄漏探针必须先红后绿
5. Wave 7.A.3：LightGBM 训练 + 预测→信号 + backtest_frame 挂钩 + 测试
6. Wave 7.A.4：ML promotion gate（复用 pbo.py DSR/PBO + 打败 baseline 硬闸门）+ 测试
7. Wave 7.A.5：CLI train/backtest-walk-forward/explain（Optuna 可选，默认关）+ auto emit
8. 跑：ruff format/check；pytest -q 全绿；oc repo check --strict；make verify
9. Wave 7.A.6：★ 真实 QQQ 硬验收，产出 ml_vs_baseline.json
10. STOP & report：贴 ml_vs_baseline 结论 + DSR/PBO + 是否打赢 baseline；
    不要自行启动 7.A.2 / 7.B / 7.C，交回决策。
```

完成后即从「线性可交易策略」进入「线性 + GBDT 双路径、按 OOS 证据择优」的可迭代训练状态。
