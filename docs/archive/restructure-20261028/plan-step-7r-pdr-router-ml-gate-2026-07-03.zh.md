# Open Composer Step 7.R 执行计划：PDR Router 源码恢复 + ML 防守退出门

日期：2026-07-03
方法：逐 wave 实现 + golden parity 测试 + 本地验证 + 逐 wave 提交
前置：Step 6.5-6.8、7.A（ML backend）、7.B（factor decay）、7.C（LLM 三角色）已落地
执行者假设：本文档自包含，执行者不依赖任何对话上下文

## 0. 目标

针对现有 QQQ/TQQQ 混合自适应路由策略
`nasdaq_tqqq_post_drawdown_reentry_router_delayed30_offensive`（active paper 候选
`..._paper_auto_candidate` 的来源），完成三件事：

- R.0 恢复 post_drawdown_reentry 路由器与两个 overlay 的**源码**（当前仅存孤儿字节码），
  并让执行面能解析 active route label。
- R.1 引入**唯一新方法族**：ML 防守退出门（LightGBM 二分类），只作用于
  `hard_stress_defensive` 状态的"继续持有 GLD vs 提前转入再入场路径"决策。
- R.2 长窗评估 harness + 硬门 `ml_gate_beats_fixed_route`：ML 门变体必须在同数据、
  同窗口上按第 1 节目标全面对比 baseline，不达标记录负结果并保持 draft。

## 1. 迭代目标（已确认：长窗稳健性优先）

所有 baseline 数字以 **2026-07-03 重拉数据上重跑的结果**为准（见第 3.6 节复权漂移）：

| 指标 | baseline（2026-07-03 数据重跑） | 目标门（gated 变体） |
| --- | --- | --- |
| 长窗 6 折 WF 跑赢 TQQQ 同窗折数 | 2/6（仅 fold5、fold6） | **≥4/6** |
| 全窗（2013-01-08→2026-05-21）总收益 | +5643.76%（TQQQ B&H +13619.96%） | 年化 **≥33%** |
| 全窗 Sharpe | ≈0.96（旧 artifact 口径） | **≥1.1** |
| 全窗 MaxDD | -42.56%（旧 artifact 口径） | **不差于同数据 baseline** |
| 危机窗 q4_2018 / covid_crash / calendar_2022 | 全部大幅跑赢 TQQQ | **三窗全部仍跑赢 TQQQ** |
| 近端窗 current_oos（2024-11-04→2026-05-21） | +182.86% vs TQQQ +120.78%（≈1.51×） | Sharpe **≥1.7** 且 total **≥1.5×TQQQ** |

判定规则：R.2 的 acceptance 块逐项给 pass/fail；任一 fail ⇒
`ml_gate_beats_fixed_route=false` ⇒ 负结果写入
`reports/research/control/`，策略保持 draft，不进 promotion，不动 paper。

## 2. 证据：为什么是"防守退出门"（2026-07-03 归因结论）

证据文件（已生成，勿重算即可引用）：

- `reports/research/control/pdr-router-fold-attribution-20260703.md` / `.json`
- `reports/research/control/pdr-router-golden-daily-decisions-20260703.jsonl`（3342 行逐日 golden）
- `reports/research/control/longbridge-adjusted-refetch-manifest-20260703.json`（数据重拉 manifest）

核心发现：`hard_stress_defensive`（持 GLD）是牛市折的最大拖累，同时是熊市折的最大贡献：

| 折 | 窗口 | hard_stress 天数 | 同天 gap vs TQQQ（算术和） |
| --- | --- | --- | --- |
| 1 | 2013-01→2015-03 | 31 | -59.6pp |
| 2 | 2015-04→2017-06 | 107 | -28.6pp |
| 3 | 2017-06→2019-09 | 149 | **-77.9pp**（本折总收益 -13.5%） |
| 4 | 2019-09→2021-12 | 133 | **-88.1pp**（COVID 后再入场过慢） |
| 5 | 2021-12→2024-02 | 306 | **+24.1pp**（2022 熊市，正贡献，必须保住） |
| 6 | 2024-02→2026-05 | 137 | -22.7pp |

全窗 `hard_stress_defensive` 863 天（25.8%），gap 合计 -252.8pp。ML 任务的本质：
**区分"2018/2020 式快速恢复（应提前退出防守）"与"2022 式持续下行（应留在 GLD）"**。

次要发现（本计划**不**处理，留下一迭代）：`risk_on_ranked` 的动量选资产在震荡牛中
选 USD/QLD 亏损（fold2 gap -14.9pp、fold3 gap -23.6pp）。
保持不动的部分：`soft_stress`、`selected_asset_blocked`、`melt_up_peak_guard` 为正贡献；
overlay 的 TQQQ 替换态（confirmation/cooldown_overlay_TQQQ）紧贴 TQQQ（gap 仅成本级）。

## 3. 关键事实（执行前必读）

### 3.1 策略与标签

- draft spec：`strategy_specs/drafts/nasdaq_tqqq_post_drawdown_reentry_router_delayed30_offensive.yaml`
- active spec（**禁止修改**）：`strategy_specs/active/nasdaq_tqqq_post_drawdown_reentry_router_delayed30_offensive_paper_auto_candidate.yaml`
- `portfolio.mode: hybrid_adaptive_router`；route label 全文：

```
defensive_overlay:transition_TQQQ_replacement_mom_positive_lb20_min0_delay30_base[pdr:semi_light_harddd6_v0.65_breadth1_softQQQ_defGLD_rec104_mom60max20_ext35_cool5QLD_confirm5_melt6040x25_detdd8m10]
```

### 3.2 孤儿字节码（本计划要修复的债）

以下模块**源码已被删除且从未提交**，仅存
`open_composer/research/__pycache__/{name}.cpython-311.pyc`：

- `post_drawdown_reentry_router`（2026-06-06）
- `defensive_transition_overlay`、`delayed_entry_overlay`（2026-06-02）
- `router_base`（2026-05-23）、`multi_sleeve_router`（2026-06-02，**不在本计划范围**）

后果（已实测）：`hybrid_router_core.hybrid_params_from_label(<上述 label>)` 抛
`ValueError: unsupported hybrid route label`，即 `oc strategy target-weights` 对
active 策略不可用；active 候选也没有任何 `reports/execution/*-target-weights.json` 制品。

字节码加载方式（诊断脚本 `scripts/diagnose_pdr_router_fold_attribution.py` 已用，按序）：

```python
import importlib.machinery, sys
for name in ["router_base", "delayed_entry_overlay",
             "post_drawdown_reentry_router", "defensive_transition_overlay"]:
    full = f"open_composer.research.{name}"
    path = f"open_composer/research/__pycache__/{name}.cpython-311.pyc"
    sys.modules[full] = importlib.machinery.SourcelessFileLoader(full, path).load_module()
```

### 3.3 需恢复的 API（内省所得，签名必须保持）

`post_drawdown_reentry_router`：

- `@dataclass PostDrawdownReentryParams`（字段见 3.4 解码表）
- `post_drawdown_reentry_params_from_label(label: str) -> PostDrawdownReentryParams`
  （注意：只接受 `post_drawdown_reentry:` 前缀；`pdr:` 缩写由 overlay 的
  `_expand_base_label` 展开）
- `post_drawdown_reentry_target_weight_snapshot(spec, dataset, params, index) -> TargetSnapshot`
- `_route_decisions(dataset, params) -> list[tuple[str | None, str]]`（逐日 资产,状态）
- 内部：`_features, _trend_ok, _defensive_asset, _transition_asset, _reentry_ok,
  _post_stress_confirmed, _meltup_guard, _early_deterioration_guard,
  _selected_asset_blocked, _select_asset, _score_symbol(mom20,mom60,mom120,vol60,dd20,dd60), _safe`

`delayed_entry_overlay`：

- `@dataclass DelayedEntryOverlay(delay_minutes, base_route_label, covered_symbols)`
- `delayed_entry_overlay_from_label(label)`、`is_delayed_entry_label(label)`、`_expand_base_label(label)`

`defensive_transition_overlay`：

- `@dataclass DefensiveTransitionOverlay(scope, replacement_symbol, condition,
  lookback_days, min_momentum_pct, delay_minutes, base_route_label, covered_symbols)`
- `defensive_transition_overlay_from_label(label)`
- `defensive_transition_overlay_target_weight_snapshot(spec, dataset, overlay, index) -> TargetSnapshot`
- `defensive_transition_overlay_effective_lookback(overlay) -> int`（该 label 下 = 252）
- `defensive_transition_overlay_summary(overlay)`、`is_defensive_transition_overlay_label(label)`
- 内部：`_condition_matches, _scope_matches, _features, _expand_base_label, _safe`

依赖的现存源码（勿重建）：`open_composer/research/router_common.py` 的
`RouterFrameDataset / TargetSnapshot / load_daily_dataset / backtest_router_params /
symbol_holding_return` 等。

### 3.4 label 解码表（实测 roundtrip）

base label `post_drawdown_reentry:semi_light_harddd6_v0.65_breadth1_softQQQ_defGLD_rec104_mom60max20_ext35_cool5QLD_confirm5_melt6040x25_detdd8m10` 解析为：

| token | 字段 | 值 |
| --- | --- | --- |
| semi_light | risk_universe | "semi_light" |
| harddd6 | hard_drawdown_pct | 6.0 |
| v0.65 | vol_rank_high | 0.65 |
| breadth1 | canary_breadth_min | 1 |
| softQQQ | soft_stress_asset | "QQQ" |
| defGLD | defensive_mode | "GLD" |
| rec104 | reentry_recovery10_min_pct | 4.0 |
| mom60max20 | reentry_momentum60_max_pct | 20.0 |
| ext35 | extension_guard_pct | 35.0 |
| cool5QLD | cooldown_days=5, cooldown_asset="QLD" |  |
| confirm5 | confirmation_days | 5 |
| melt6040x25 | meltup_momentum60_min_pct=40.0, meltup_extension_pct=25.0 |  |
| detdd8m10 | deterioration_tqqq_dd20_pct=8.0, deterioration_momentum60_max_pct=10.0 |  |

overlay label：`defensive_overlay:transition_{SYMBOL}_replacement_{condition}_lb{N}_min{M}_delay{D}_base[...]`
→ scope="transition", replacement_symbol="TQQQ", condition="mom_positive",
lookback_days=20, min_momentum_pct=0.0, delay_minutes=30, base_route_label=`[...]` 内文
（`pdr:` 展开为 `post_drawdown_reentry:`）。

状态枚举（golden 中全部出现）：`risk_on_ranked, hard_stress_defensive,
confirmation_transition, confirmation_transition_overlay_TQQQ, cooldown_transition,
cooldown_transition_overlay_TQQQ, post_drawdown_reentry, early_deterioration_downshift,
soft_stress, selected_asset_blocked, melt_up_peak_guard`。

### 3.5 数据

- 路径：`data/research/longbridge_adjusted_daily/{symbol}_daily_longbridge_adjusted.csv`
  （11 symbol：QQQ TQQQ QLD SOXL USD SMH SOXX XLK IGV GLD BIL；2010/2012→2026-05-21；
  2026-07-03 已重拉，manifest 见第 2 节）。
- 缺失时重拉：调用
  `scripts/research_return_enhanced_longbridge_history.py::_ensure_longbridge_history(root, symbols)`
  （分块 live 拉取，幂等，需 Longbridge 凭证；R.0 应将其提炼为独立脚本
  `scripts/materialize_longbridge_adjusted_history.py --symbols ...`）。
- `open_composer/adapters/data/longbridge.py` 的 `fetch_ohlcv(source="longbridge")` 会自动
  优先读该 materialized 目录（`_load_materialized_history`）。

### 3.6 复权漂移警告（对比纪律）

同一路由在旧 artifact（2026-05 拉取）与 2026-07-03 重拉数据上的全窗总收益分别为
4334.28% 与 5643.76%（每折方向与排序不变）。原因：复权序列随新分红整体重标定 +
交易日数差 13 天。**纪律：一切 gated vs baseline 对比必须在同一份数据上同跑双方；
禁止与历史 artifact 数字直接比较。**

## 4. Wave R.0 路由源码恢复（必须最先做）

新增源码文件：

- `open_composer/research/post_drawdown_reentry_router.py`
- `open_composer/research/delayed_entry_overlay.py`
- `open_composer/research/defensive_transition_overlay.py`
- （`router_base.py` 仅当上述模块 import 它时恢复；multi_sleeve 不做）

方法：

1. 用 3.2 的 loader 加载字节码，`dis.dis` 逐函数反汇编对照重写；保持 3.3 签名与
   3.4 语义完全一致。
2. 接入执行面：在 `hybrid_router_core` 的 label 分发（`hybrid_params_from_label` 及
  target-weight snapshot 选择处）注册 `defensive_overlay:` / `post_drawdown_reentry:`
  / `delayed:`（如存在）前缀，使 `oc strategy target-weights --spec <active spec>` 可运行。
3. 数据工具：把 `_ensure_longbridge_history` 提炼为
   `scripts/materialize_longbridge_adjusted_history.py`（参数化 symbols/start/end，写 manifest）。

测试（新增）：

- `tests/test_pdr_router_label.py`：label 解析 roundtrip、`pdr:` 展开、非法 label 报错。
- `tests/test_pdr_router_parity.py`：
  - 小窗全等：把 golden JSONL 与对应输入价格切片收进 `tests/fixtures/`（或 `data/fixtures/`），
    对固定小窗逐日断言 (state, weights, net_return) 与 golden 全等；
  - 长窗全等：完整 3342 天逐日全等 + fold 汇总对
    `pdr-router-fold-attribution-20260703.json`，`skipif` 数据目录缺失。

验收：

- 逐日 (state, weights) 与 golden **100% 全等**（net_return 容差 1e-9）。
- `oc strategy target-weights` 对 active spec 不再抛 unsupported label（只写制品，不下单）。
- 源码提交后，诊断脚本改为 import 源码路径（loader 保留为 fallback 并打印告警）。

## 5. Wave R.1 ML 防守退出门（唯一新方法族）

行为定义：

- 决策点**只有一个**：base 路由当日 state == `hard_stress_defensive`。
- 每日推理 `p = P(QQQ 前瞻 h 日累计收益 ≥ τ)`；`p ≥ θ` ⇒ 视 reentry 条件为满足，
  走**既有** confirmation/cooldown 再入场路径（不新增状态、不新增资产）；`p < θ` ⇒ 维持 GLD。
- fail-safe：模型文件/特征缺失、推理异常 ⇒ 行为与 baseline **完全一致**（用测试锁定）。
- 新状态名后缀区分：如 `hard_stress_defensive_ml_release`，便于归因复跑。

特征（全部 index-1，禁止未来数据）：QQQ/TQQQ/GLD 的 mom20/60/120、vol60、dd20/dd60、
semi_light canary breadth——即 `_score_symbol` 与 `_features` 已用的量，不引入新数据源。

标签与搜索空间（**硬上限 12 组合**，全部入 trial ledger）：
h ∈ {10, 20}；τ ∈ {0%, +2%}；θ ∈ {0.6, 0.7, 0.8}。

训练：LightGBM，7.A 保守默认（num_leaves=15, max_depth=4, min_child_samples=20,
lr=0.05, n_estimators=200, subsample/colsample=0.8, reg_lambda=1.0）；
purged+embargo rolling walk-forward 复用
`open_composer/research/ml_backend/windows.py::ml_walk_forward_slices`
（`train_end = test_start - horizon - embargo`，embargo ≥ h）；θ 作为超参在外层 WF 选择，
禁止在报告窗内选 θ。

label 表达：overlay label 增加 mlgate 段（示例
`defensive_overlay:transition_TQQQ_..._mlgate_h10_t2_p70_base[...]`），保持
"route label 全参数化"传统；训练细节放 draft spec 的 `model` 块（7.A schema）。

产物：`reports/research/ml/{strategy}/`（训练 JSON、stitched OOS、fold 元数据）、
trial ledger、`oc strategy explain` 可运行。

## 6. Wave R.2 评估 harness + 硬门

新增 `scripts/evaluate_pdr_router_ml_gate.py`（或 `oc` 子命令，执行时定）：

- 同一份 materialized 数据上同跑 baseline route 与 gated route；
- 输出窗口：全窗（warmup 252）、6 折（边界沿用
  fold1 2013-01-08→2015-03-31 / fold2 →2017-06-27 / fold3 →2019-09-17 /
  fold4 →2021-12-06 / fold5 →2024-02-28 / fold6 →2026-05-21，向后顺延到最新数据）、
  危机窗 q4_2018（2018-10-01→2018-12-28）、covid_crash（2020-02-19→2020-03-20）、
  calendar_2022（2022-01-03→2022-12-29）、近端窗 current_oos（2024-11-04→最新）；
- 写 `reports/research/control/pdr-router-ml-gate-eval-{date}.md/.json`，acceptance 块含
  第 1 节 6 项 gate 逐项 pass/fail 与总判定 `ml_gate_beats_fixed_route`；
- 同时输出 gated 变体的逐日归因（复用诊断脚本的 attribute_window 逻辑），确认收益改善
  确实来自 `hard_stress_defensive` 天数的转化，而非其他状态漂移。

负结果路径：gate fail ⇒ 报告写明失败项与原因，draft 保留，计划终止于此（不得为凑数
扩大搜索空间）。

## 7. 边界与非目标

- 不修改 active spec；一切在 draft 副本（新 draft：
  `strategy_specs/drafts/nasdaq_tqqq_pdr_router_mlgate_iter1.yaml`，从 draft 复制）。
- 不改 paper_auto、broker、nautilus 执行路径；R.0 只是让 target-weights **可运行**。
- 搜索空间硬上限 12 组合；不做全局重搜、不调 base 路由 16 个参数。
- 不引入新依赖（lightgbm、scikit-learn 已在 7.A 引入）。
- LLM 不参与任何路由决策（`oc strategy explain` 仅 advisory）。
- 不做 `risk_on_ranked` 资产选择 ML、不恢复 multi_sleeve_router、不做 7.A.2 截面 ML。
- 不提交 `data/` 大文件与 `reports/` 大制品；golden fixture 子集除外（入 tests/fixtures）。

## 8. 全局验收

- `uv run ruff format .`、`uv run ruff check .`、`uv run pytest tests/ -q`
- `uv run oc repo check --strict`、`make verify`
- 本文档加入 `repo_check.CURRENT_DOCS`
- parity 测试绿：逐日全等 + fold 汇总一致
- 工作树扫描：只提交源码、测试、文档、必要脚本
