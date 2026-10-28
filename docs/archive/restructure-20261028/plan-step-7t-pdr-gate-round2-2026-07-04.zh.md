# Step 7.T PDR 防御放行门第二轮（路径生存标签）+ risk_on_ranked 规则评审（2026-07-04）

> 执行者注意：本文档自包含，不依赖会话上下文。所有路径相对仓库根
> `/root/codex-test/open-composer`，当前分支
> `step-7r-pdr-router-ml-gate-2026-07-03`（tip `f8d1b20`，Step 7.S 已完成并验收）。
> 按 Wave 顺序执行，每个 Wave 一个独立提交，红灯即停。

## 0. 背景（必要事实，无需翻旧文档）

**策略**：活跃 paper 候选是固定路由的 PDR 路由器
（`strategy_specs/drafts/nasdaq_tqqq_post_drawdown_reentry_router_delayed30_offensive.yaml`，
活跃副本在 `strategy_specs/active/`）。同数据基线（longbridge 物化缓存，
2012-01-03 → 2026-05-22）：全窗口 5643.76% / 年化 35.72% / Sharpe 1.014 /
MaxDD -43.24%；三个危机窗口 q4_2018 -16.01%、covid_crash -13.13%、
calendar_2022 -17.76%，全部远胜 TQQQ。

**Step 7.R 负面结果**（`reports/research/control/pdr-router-ml-gate-eval-20260703.{md,json}`）：
用「未来 10 天 TQQQ 收益 > +2%」终值标签训练 LightGBM 防御放行门，
`ml_gate_beats_fixed_route=False`。机制：反弹标签在崩盘中途经常为真，
模型在崩盘反弹和 2022 阴跌中都放行了 GLD 防御——MaxDD -43.24 → -66.70，
q4_2018 保护 -16.01 → -36.75。管道无罪（非 hard_stress 日变化 = 0），
错在标签不回答真正的交易问题。

**Step 7.S 已交付的可复用件**（本轮必须直接用，不得重建）：
- `oc strategy router-attribution`（按折/按状态归因，核心在
  `open_composer/research/pdr_attribution.py`）。
- `oc strategy router-gate-eval`（基线 vs 门控同数据对比 + 六硬门验收，核心在
  `open_composer/research/pdr_ml_gate_evaluation.py::evaluate_pdr_router_ml_gate`，
  支持 `--output-dir`；验收全过退出码 0，否则非零）。
- `oc data verify-research-cache`（manifest 哈希校验；任何回测前先跑，
  确保同数据对比纪律）。
- 设计依据：`reports/research/control/next-iteration-readiness-20260703.md`
  （路径生存标签设计 + 能力评估结论 + 队列决策）。

**本轮能力决策（已定，不再讨论）**：第一轮路径标签迭代只用现有路由器特征
（qqq/tqqq/gld 的 mom20/60/120、vol60、dd20/60 + canary_breadth + vol_rank，
共 20 列，index-1 对齐），**不引入** FRED/宏观/广度新能力。若本轮因「缺体制
上下文」失败，宏观能力评估才升格为下一轮前置（readiness 文档 §2 已写明路径）。

## 1. 目标与硬门

一句话目标：让 ML 门学会「什么时候离开 GLD 持有 3 倍杠杆是安全的」，
而不是「什么时候会反弹」；同时用非 ML 评审搞清 risk_on_ranked 选资产
（fold2 -14.9pp、fold3 -23.6pp）该不该改规则。

验收裁决沿用 `ml_gate_beats_fixed_route`，六门全过才算过；任何一门失败 ⇒
负面结果入 control/ + 追加迭代日志 + 草稿保持草稿。相对 7.R 的变化：
**危机门从「仍胜 TQQQ」收紧为「不得劣于基线」**（7.R 的教训：门控 q4_2018
-36.75% 仍「胜」TQQQ -50%，保护力却腰斩，旧门形同虚设）。

| # | 硬门 | 阈值 | 7.R 基线参考 |
|---|---|---|---|
| 1 | `wf_beats_tqqq_at_least_4_of_6` | ≥ 4/6 折胜 TQQQ 买入持有 | 基线 2/6 |
| 2 | `full_window_annualized_return_at_least_33` | 年化 ≥ 33% | 基线 35.72% |
| 3 | `full_window_sharpe_at_least_1_1` | Sharpe ≥ 1.1 | 基线 1.014 |
| 4 | `full_window_maxdd_not_worse_than_baseline` | MaxDD ≥ 基线（同数据重算） | 基线 -43.24% |
| 5 | `crisis_windows_not_worse_than_baseline`（新） | q4_2018 / covid_crash / calendar_2022 每个窗口：门控总收益 ≥ 基线 - 2pp **且** 窗口内 MaxDD ≥ 基线 - 2pp，且仍胜 TQQQ | 见 §0 |
| 6 | `current_oos_sharpe_and_total_gate` | 2024-11-04 起：Sharpe ≥ 1.7 且总收益 ≥ 1.5 × TQQQ | 7.R 门控 1.395 / 1.20× |

## 2. Wave T.0 risk_on_ranked 选资产规则评审（非 ML，只分析，零 spec 改动）

依据归因（`reports/research/control/pdr-router-fold-attribution-20260703.md`）：
`risk_on_ranked` 的动量排名在震荡牛市反复选中 USD/QLD 而落后，fold2 同日差
-14.9pp、fold3 -23.6pp。这是活跃 paper 策略的第二大拖累，先用便宜的规则评审
确认「该不该改、改成什么」，不上 ML。

1. 数据前置：`uv run oc data verify-research-cache` 必须通过。
2. 用 `open_composer/research/pdr_attribution.py` 与
   `open_composer/research/router_common.py::symbol_holding_return` 隔离全窗口所有
   `risk_on_ranked` 日，做同日对照（持仓替换法，不重放全路由）：
   实际排名选择 vs 固定 TQQQ vs 固定 QLD vs 固定 QQQ vs
   排名平滑规则（新领先者需连续保持 k∈{3,5} 日才切换）vs
   平局偏向 TQQQ（排名分差 < ε 时选 TQQQ，ε 用动量分差 2pp）。
   按折与全窗口输出算术同日差与状态段复利差。
3. 若某变体在 fold2、fold3 显著占优且其他折不劣化，**只对该最优变体**做 1-2 次
   全路由重放（改 label 段生成变体路由，跑 `backtest_router_params`），
   与基线同数据对比——这是验证不是搜索，禁止扫参。
4. 交付 `reports/research/control/risk-on-ranked-rule-review-20260704.{md,json}`：
   结论必须落在三选一——(a) 规则变体值得作为未来一轮独立门控迭代（写明变体与
   预期收益）、(b) 现有规则已接近最优（写明证据）、(c) 证据不足需要什么数据。
   本轮不改任何 spec、不改 `post_drawdown_reentry_router.py` 行为。
5. 单测：对照计算函数给小 fixture 测试（复用 `tests/fixtures/pdr_router/`）。

## 3. Wave T.1 路径生存标签 ML 门（第二轮，8 组合）

只扩展 Step 7.R 已有的 `pdr_defensive_exit_ml_gate` 家族，不新增方法族。
锚点都在 `open_composer/research/pdr_ml_gate.py`：

- `PDRMLGateConfig`（约 60 行）：新增字段 `label_kind`
  （`"terminal_return"` 保持旧行为 | `"path_survival"` 新）、
  `max_drawdown_pct: float | None`、`min_terminal_return_pct: float`。
  token 第二轮用 `mlgate2_h{h}_dd{dd}_p{θ}`（如 `mlgate2_h10_dd8_p60`），
  `pdr_ml_gate_from_token`（89 行）需同时解析两代 token。
- `build_pdr_ml_gate_label`（216 行）：`path_survival` 分支按
  readiness 文档 §1 伪代码实现——决策日 i 的特征只用 ≤ i-1；
  标签窗口 `[i+1, i+horizon]` 的 TQQQ open_to_open 复利路径：
  `label = (期末收益 ≥ min_terminal_return) AND (路径内 MaxDD ≥ -max_drawdown_pct)`；
  窗口不完整（尾部）置 NaN 并从训练中剔除。
- 搜索空间（`pdr_ml_gate_search_space` 或新函数）：
  `horizon ∈ {10, 20}` × `max_drawdown_pct ∈ {8, 12}` × `θ ∈ {0.6, 0.7}`，
  `min_terminal_return = 0` 固定 ⇒ **恰好 8 个组合，硬上限 8，不得加**。
- `validate_pdr_ml_gate_training_config`（112 行）：强制 `embargo_bars ≥ horizon_bars`
  （h=20 ⇒ embargo ≥ 20）。purged/embargo 切片继续复用
  `open_composer/research/ml_backend/windows.py`，规则
  `train_end ≤ test_start - horizon - embargo` 逐 trial 写入 ledger。
- 模型：LightGBM 7.A 保守默认（`ml_backend/model_factory.py`），与 7.R 相同。
- 训练脚本沿用 `scripts/train_pdr_router_ml_gate.py`（加 `--label-kind` 参数）。
- Trial ledger：`reports/research/ml/nasdaq_tqqq_pdr_router_mlgate_iter2/pdr_mlgate_trial_ledger.jsonl`，
  每组合一条，记录 label_kind、正类占比、mean_test_rank_ic、release 数。
- 草稿 spec：`strategy_specs/drafts/nasdaq_tqqq_pdr_router_mlgate_iter2.yaml`
  （参照 iter1 结构，路由 label 段用 mlgate2 token），并按 `.gitignore` 44 行
  的 iter1 先例加白名单。
- 干预面不变：只在基线状态为 `hard_stress_defensive` 的日子求值；
  p ≥ θ ⇒ 走既有 reentry 路径，否则维持 GLD；模型/预测缺失 ⇒ fail-safe 等价基线。
- 单测：扩展 `tests/test_pdr_ml_gate.py`——path_survival 标签的手算小样例
  （构造一段已知路径验证 MaxDD 与终值联合条件）、两代 token 解析往返、
  embargo 校验拒绝 `embargo < horizon`。

## 4. Wave T.2 评估与裁决

- 扩展 `open_composer/research/pdr_ml_gate_evaluation.py`：
  - 六门中第 5 门替换为 `crisis_windows_not_worse_than_baseline`（§1 定义，
    容差 2pp 写成常量并在报告中显示）；其余五门阈值不变。
  - 评估必须从 spec 读取 mlgate2 token 与 label_kind，对 iter1/iter2 都能跑
    （向后兼容，iter1 的历史报告不重写）。
- 通过 `uv run oc strategy router-gate-eval --spec strategy_specs/drafts/nasdaq_tqqq_pdr_router_mlgate_iter2.yaml --report-date 20260704`
  产出 `reports/research/control/pdr-router-ml-gate-eval-20260704.{md,json}`
  （S.0 白名单已覆盖 md；json 参照 iter1 先例加白名单）。
- 报告必须含：同数据基线块、attribution 块（`non_hard_stress_state_or_weight_changes`
  必须为 0）、每折对比、六门验收表、`ml_gate_beats_fixed_route` 裁决。
- **无论裁决如何**，在 `reports/research/control/strategy-iteration-progress-2026-07-01.md`
  追加 7.T 条目（Result / Mechanism / Decision 体例，参照 7.R 条目）。
  失败即负面结果入档，草稿保持草稿；通过则在条目中列出进入 promotion
  检查前仍缺的证据（benchmark family、成本敏感性、数据源敏感性等），
  **本轮也不做 promotion、不动 paper**。
- 单测：新危机门的通过/失败两条路径（构造窗口指标断言容差逻辑）。

## 5. 边界与安全（全程有效，越界即红灯）

- 搜索硬上限 8 组合；不因接近门槛而加组合、改阈值、换特征。
- 不引入宏观/FRED/广度等新数据能力；特征列固定为 §0 所列 20 列。
- 活跃 spec 与 paper 行为零改动；一切新 spec 仅限草稿目录。
- 不 push、不 merge、不删分支、不删备份；S.1 报告
  （`reports/research/control/branch-reconciliation-map-20260703.md`）的
  用户决策清单仍属用户，Codex 不得代做。
- 不重抓 `data/research/longbridge_adjusted_daily/`（黄金对照锚定于当前数据）；
  每个 Wave 回测前先 `oc data verify-research-cache`。
- 不新增第三方依赖；不触碰 `.env`/密钥；LLM 不进路由决策。
- 每个 Wave 独立提交：T.0 → T.1 → T.2。

## 6. 验收命令

每个 Wave 提交前：

```bash
uv run ruff format . && uv run ruff check .
uv run pytest -q
uv run oc repo check --strict
make verify
```

T.2 额外：

```bash
uv run oc data verify-research-cache
uv run oc strategy router-gate-eval \
  --spec strategy_specs/drafts/nasdaq_tqqq_pdr_router_mlgate_iter2.yaml \
  --report-date 20260704 ; echo "exit=$?"
```

（退出码非零且报告完整写出 = 负面结果的正常形态，不是执行失败。）

## 7. 交付清单

- [ ] T.0：`risk-on-ranked-rule-review-20260704.{md,json}`（三选一结论）+ 对照函数单测。
- [ ] T.1：path_survival 标签 + mlgate2 token + 8 组合训练 + iter2 草稿 spec +
      trial ledger + 单测。
- [ ] T.2：收紧危机门的评估器 + `pdr-router-ml-gate-eval-20260704.{md,json}` +
      迭代日志 7.T 条目 + 单测。
- [ ] 本计划注册进 `open_composer/repo_check.py` CURRENT_DOCS 与
      `tests/test_repo_check.py`（参照 7.R/7.S 先例，各 +1 行）。
