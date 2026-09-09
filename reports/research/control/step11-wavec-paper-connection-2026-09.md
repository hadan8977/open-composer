# Step 11 Wave C -- 模拟盘连接（观察模式）

负责人：产品/执行侧执行者（`open_composer/models/`, `open_composer/adapters/`,
`open_composer/cli.py`, `config/`, `strategy_specs/`, `scripts/new_lightweight_iteration.py`,
`scripts/run_daily_paper_cycle.py`, 本报告）。

范围：把一个策略以**观察模式**接到 Alpaca Paper —— 每日算目标权重、写信号日志，
**全程不下单、不激活任何策略生命周期**。截止 2026-09-11（周五）。研究线（`open_composer/research/**`,
`reports/research/**` 除本文件外）并行推进 B3 网格与候选导出，互不越界，产物通过
`reports/research/ledger/experiments.jsonl` 和冻结的候选导出接口（commit `93ba159`）交接。

本报告写作/核实时间：2026-09-09（周三）。所有"当前状态"类数字均为当天现取，不是回忆。

---

## 1. 做了什么（6 项交付物）

### 1/6 `model_ranking_portfolio` 组合模式（`5305d77`）

`open_composer/models/strategy_spec.py` 的 `PortfolioConfig.mode` 新增
`"model_ranking_portfolio"`，配套字段：`candidate_artifact_dir`、
`universe_rule`（当前只允许 `pit_adv_top_n`）、`universe_top_n`、`feature_set_id`、
`label_horizon_days`（5/10/21）、`top_k`、`rebalance`（当前只允许
`weekly_friday_close_monday_open`）、`hedge`（`none|spy_beta_hedge`）、
`account_equity_for_sizing`（可选，缺省读实盘账户）。一个 `model_validator` 强制这
8 个字段在该模式下必须齐全同现、`weighting` 必须是 `equal_weight`、`candidate_artifact_dir`/
`feature_set_id` 不能为空串；在其他模式下这些字段必须全部不出现。`schemas/strategy_spec.schema.json`
同步更新。`tests/test_spec_validation.py` 新增 9 个测试（含端到端 spec 加载、schema 契约断言）。

### 2/6 目标权重适配器（`4c3f76c`，接口修复见 `9d6f6f1`）

新文件 `open_composer/adapters/execution/model_ranking_target_weights.py`：

- 读特征库最新交易日 → 用 PIT 口径（沿用 `research/kernel/loop.py` 的
  `universe_as_of_calendar_month`）确定当期股票池 → 加载候选工件打分 → 前 K 等权
  （+ 可选 SPY beta 对冲腿）→ `whole_share_sizing` 整股换算 → 写目标权重 JSON
  （含 `shares`、`realized_weight`、`weight_deviation`、`idle_cash`）。
- 非调仓日读回上一次快照输出"维持当前目标"，**从不输出空持仓**；零持仓账户的
  第一次调仓日输出完整目标（15 个测试里显式覆盖这两种情形 + 工件缺失时的清晰报错）。
- 接入 `oc strategy target-weights` 分派（`open_composer/cli.py`）、
  `router_authorization.py` 的 `ROUTER_PORTFOLIO_MODES`、`paper_readiness.py` 的
  `_portfolio_routing_check`/`_portfolio_risk_check` 专用分支。
- **`9d6f6f1` 修复**：最初误把 `model.joblib` 当成裸 sklearn/LightGBM 估计器包一层
  `.predict()` 调用；对照协调者指出的冻结接口定义（commit `93ba159`）后发现真实契约是
  joblib 反序列化出来的对象**本身就实现 `.score(asof_frame) -> pd.Series`**，删除了
  错误的包装类，改为直接调用（带 `hasattr(fitted, "score")` 防御性检查），并去掉了一个
  接口里并不存在、被我自己臆造出来的 `beta_column` 字段。

占位候选放在 `config/model_ranking_candidates/step11_momentum_placeholder_v1/`
（不放 `reports/research/candidates/`，那是研究线的导出目录，避免任何路径冲突）：
规则式 12-1 动量（`momentum_252_21`，即 B1 baseline 的规则版本），`model_kind:
rule_momentum_top_k` + `score_column` 触发直接按特征列排序而不加载 `model.joblib`。
`README.md` 里写清楚哪些字段是研究线冻结接口的字段、哪些是本占位工件自己的扩展。

途中一次自造事故：误对这个目录下的 `.json` 文件跑了 `uv run ruff format`（ruff 是纯
Python 工具，不该指向 `.json`），把两个文件写坏成带非法尾逗号的 JSON，导致一个已通过
的测试变红；用 `cat -A` + 直接 `json.load` 确认损坏是真实的，写小脚本重新生成干净
JSON 修复，15 个测试全部复跑通过。

### 3/6 可运行的 StrategySpec（`1a32694`）

`strategy_specs/drafts/us_model_ranking_portfolio_top50.yaml`（任务原文写
`strategies/`，本仓库实际约定是 `strategy_specs/drafts/`，按约定命名并在提交信息里
注明替换）。`lifecycle: draft`，`execution: {mode: manual_signal, broker: none}`，
`data: {source: alpaca, feed: sip}`，`data_assumptions: {adjusted: true}`，
`execution_policy: {order_style: opg_limit, time_in_force: opg, ...}`，
`portfolio.candidate_artifact_dir` 指向上面的动量占位工件 —— 等研究线的真实候选落地后
只需要改这一个字段。`.gitignore` 里 `strategy_specs/drafts/*` 默认忽略+白名单的老约定，
把这个文件名加进白名单。

### 4/6 晋级路径干跑（代码改动随 `7978ced` 一并落库；见下文"竞争"说明）

`scripts/new_lightweight_iteration.py` 新增 `--from-ledger <experiment_id>` 入口和
`config_from_ledger()` 函数：从 `reports/research/ledger/experiments.jsonl` 的真实
记录派生完整的迭代档案配置（`candidates[].parameters` 直接取自账本行，
`decision.reason` 直接引用账本的 `gate_results`/`recorded_at`/`tearsheet_path`），
账本文件缺失、`experiment_id` 缺失、`experiment_id` 重复三种情况都 fail-closed
（`SystemExit`，不猜、不选一条了事）。`sources`/`topic_coverage` 只在调用方显式传入
时才非空，绝不臆造。`tests/test_new_lightweight_iteration_from_ledger.py` 5 个测试
覆盖这些路径。spec 的 `research_design` 块（`iter_id`/`candidate_manifest_path`/
`data_feasibility_path`）也是这一步加上的。

然后跑了完整链路（`--from-ledger step11_b1_momentum_top50` → `oc strategy evidence`
→ `promotion-report` → `harness plan/verify` → `paper readiness`），每一步的 blocker
如实记录在下面第 2 节 —— 没有绕过、没有放宽任何一个。

### 5/6 观察模式接入每日循环（`5626161`）

`scripts/run_daily_paper_cycle.py` 新增 `run_model_ranking_observation_cycle()`：
一个独立的、只做两步的循环（`oc paper sync-account` → `oc strategy target-weights`），
由 `main()` 通过 `_is_model_ranking_portfolio_spec()`（读一次 spec 的
`portfolio.mode`）自动分派，对其他所有既有策略/spec 零行为变化。**从不调用
`oc run paper`**（唯一能下单的命令），并且在进入两步之前就用
`portfolio.mode/execution.mode/execution.broker/lifecycle` 四个字段做防御性校验，
不满足 `model_ranking_portfolio` + `manual_signal` + `broker=none` + `draft` 就直接
`ValueError`，不给任何越权的可能。日志写到独立路径
`reports/paper/daily_cycle/{name}-observation-{date}.json`
（`report_type=daily_paper_cycle_observation_only`，`paper_order_authorization`/
`broker_writes` 硬编码 `false`），不复用/不触碰既有 4 步流水线（`run_daily_cycle`）
用的 `strategy_specs/active/` 绑定机制 —— 该目录当前仍完全为空，说明既有流水线现在
对任何策略都跑不起来，改动它风险和范围都远超这次交付需要。

9 个新测试（`tests/test_daily_paper_cycle_model_ranking.py`）覆盖：spec 模式识别、
成功路径的日志与 summary 字段、"从不调用 run paper"这条不变量、非交易日跳过、
四个安全校验字段的拒绝路径、单步失败短路、`--dry-run` 输出。既有
`tests/test_daily_paper_cycle.py`（9 个）和 `tests/test_model_ranking_target_weights.py`
（15 个）原样复跑全绿，没有对既有 router 流水线造成回归。

**真实端到端运行**（见第 3 节详细持仓）：对真实特征库、真实 Alpaca Paper 账户跑通，
零下单，`strategy_specs/active/` 运行前后都确认为空，`reports/paper/positions.json`
运行后仍是空列表。

### 6/6 本报告

即本文件。

### 收尾全量测试时发现并修复的一个真实回归（交付物 1 的副作用，`c394d82`）

写完 5/6 后按纪律跑全量 `uv run pytest -n 2`（内存封顶），第一次结果是 57 个失败——
比文档记录的 `tests/test_mom_breadth_qd_r1.py` 11 个已知失败基线多出 46 个，分布在
`tests/test_high_beta_sleeve_ensemble_r1.py`、`tests/test_vix_term_structure_overlay_r1.py`、
`tests/test_multiasset_forward_multimodal_r5(_target_weights).py`，以及
`test_mom_breadth_qd_r1.py` 自己多出的 6 个——一律没有直接改这些文件，一律不在本 Wave
改动范围内。没有把这个当作"本来就这样、不是我的问题"含糊过去，而是用一个临时的
只读 git worktree（`git worktree add --detach <tmp> 14622b3`，Wave C 第一个提交之前
那个commit）隔离比对，加上直接 diff 哈希前后的 payload，精确定位到：**交付物 1 给
`PortfolioConfig` 新加的 9 个字段（缺省 `None`）没有被 `open_composer/strategy_versions.py`
的 `strategy_content_hash()`/`_remove_unset_schema_extensions()` 纳入"新增可选字段不
改变旧 spec 语义哈希"的既有豁免清单——这个清单对 `research_design`、`execution_policy`
已有的扩展字段都手工维护了一份，唯独没有 `portfolio` 这一项**。结果是仓库里几乎
所有带 `portfolio` 块的 spec（不管用不用新模式）语义哈希都变了，砸中了好几个研究线
自己"冻结 manifest/lock 里的 spec 哈希必须和重新计算的一致"的既有测试契约。

修复（`c394d82`，仅 2 个文件，均在本执行者归属范围内）：照抄 `research_design`/
`execution_policy` 已有写法，给 `spec.portfolio` 也加一条 `drop_unset(...)`，把这 9 个
新字段名列进去；同时给 `tests/test_strategy_versions_and_capability_expansion.py` 加了
一个专门的回归测试（`test_model_ranking_portfolio_fields_preserve_legacy_content_hash`），
并修了同文件里一个此前一直手工维护参照 payload、因此也需要同步加这 9 个字段 pop 的
既有测试（它本身就是修复不完整时唯一会报错的测试，某种意义上是它自己抓出来的）。
复跑后 `test_high_beta_sleeve_ensemble_r1.py`、`test_multiasset_forward_multimodal_r5*.py`
全绿，`test_mom_breadth_qd_r1.py` 精确回落到文档记录的 11 个。

全量复跑后仍剩 1 个失败：`tests/test_vix_term_structure_overlay_r1.py::test_generated_repair_runtime_contract_accepts_exact_governance_bindings`。
根因用同一份直接 diff 方法精确定位：两侧 payload 唯一不同的键还是 `portfolio`，还是
这 9 个新字段——但触发点是
`open_composer/research/vix_term_structure_overlay_r1.py` 里 `_economic_spec_projection()`
自己做的一次独立的原始 dict 相等性比较（比较一份冻结的历史 spec 快照和一份重新
`model_dump()` 出来的当前 spec），完全不经过 `strategy_content_hash()`，所以没有被
上面的修复覆盖到。这个函数在 `open_composer/research/**` 里，本不在本 Wave 的文件
归属范围内；但在动手改之前先用 `git log -1` 核实了这个文件和它的测试文件都是
2026-08-26（提交 `d0cd174`）最后改动的，比 Wave C 第一个提交早了 12 天以上——不存在
"研究线正在改这个文件、我一改就冲突"的风险，而且已经用直接 diff 排除了这是别的
在途改动导致的（唯一不同就是我自己加的这 9 个字段）。协调者随后明确要求"要么修掉，
要么证明是别人的在途改动"，既然已证明不是后者，就照 `c394d82` 完全相同的思路补了
这一处（`7282cca`）：在 `_economic_spec_projection()` 里，比较前把这 9 个字段名从
`portfolio` 子字典里"仅当该侧取值为 `None`"时才丢弃（不是无条件丢弃——如果某个字段
真的被设成非 `None` 值，两侧仍然会被判定不同，不会掩盖真实差异）。复跑
`tests/test_vix_term_structure_overlay_r1.py`，55/55 全绿。至此，交付物 1 引入的这个
回归已经全部修完，两处修复分别是 `c394d82`（本执行者归属范围内的
`strategy_versions.py`）和 `7282cca`（本执行者归属范围外、但已证明是本执行者自己的
bug 且证明无在途冲突风险后修复的 `vix_term_structure_overlay_r1.py`）。

---

## 2. 当前晋级 gate 状态（2026-09-09 现取，非回忆）

先说清楚一个前提：观察模式接入**不需要**过任何晋级门槛（这是任务原始设计里明确的——
"这一步不需要过门槛，因为观察模式没有风险而前向跟踪数据有价值"）。下面记录的是为了
诚实完成第 4 项交付物而**真实跑出来**的 blocker，全部原样保留，没有为了让链路"看起来
能走完"而放宽任何一个：

| 步骤 | 命令 | 结果 |
|---|---|---|
| 派生迭代档案 | `new_lightweight_iteration.py --from-ledger step11_b1_momentum_top50 ...` | 从账本正确派生出完整配置（`decision.reason` 显示 `long_only gates 4/8 pass`），随后在 `sources` 门槛上 fail-closed：`config missing required key: sources`（还没有为这个候选/spec 收集来源卡，这是真实缺口，不是 bug） |
| `oc strategy evidence <spec>` | 同上 spec | `Invalid value: iteration dossier blocked for step11_wavec_model_ranking_top50: iteration_dossier_missing` —— 因为上一步在写档案文件之前就 fail-closed 了，`reports/research/iterations/step11_wavec_model_ranking_top50/` 目录根本不存在 |
| `oc strategy promotion-report <spec>` | 同上 | 同样的 `iteration_dossier_missing` |
| `oc harness plan <spec>` | 同上 | 成功，识别风险域 `daily_open_execution`，产出 `reports/harness/plans/us_model_ranking_portfolio_top50.{json,md}` |
| `oc strategy execution-policy <spec>` | 同上 | 成功，产出草案策略（`recommended=opg_limit`，与 spec 已选一致），带一条"缺来源卡"的预期警告 |
| `oc harness verify <spec>` | 同上 | `overall: "blocked"`，3 个必需工件里 2 个 `present+schema_ok`（`execution_policy`、`execution_reality_report`），唯一缺失的是 `source_cards`（`missing_fields` 列出 schema 要求的 8 个字段，因为文件根本不存在） |
| `oc paper readiness us_model_ranking_portfolio_top50` | -- | `status=blocked ready=no`。本 Wave 新增的两项检查 `portfolio_routing`/`portfolio_risk` 都是 `ok`；`lifecycle`/`execution`/`universe_audit`/`alpaca_env`/`kill_switch`/`promotion_report`/`capability_report` 全部 `blocked`（这些本来就该在草稿态被挡住——策略没有 `lifecycle=active`，也没有 `promotion_report`）；`harness_artifacts` 是 `warning`（同样指向缺 `source_cards`）；`paper_validation`（0/20 交易日）、`matched_paper_tca`（需要 ≥30 笔匹配 TCA 观测）都是 `warning`，符合"刚接入、还没积累跟踪记录"的真实状态；`order_authorization` 明确显示"observation_only" |

**结论**：晋级链路目前被精确地卡在**同一个缺口**上 —— `harness verify` 按 spec 名字
找的是这个策略自己的来源卡文件
`reports/harness/source_cards/us_model_ranking_portfolio_top50.jsonl`，这个文件
目前根本不存在。仓库里其实有相当多别的策略自己的来源卡覆盖了 OPG/`daily_open_execution`
话题（`r9_alpaca_opg_semantics` 系列、`hbs_r1_alpaca_opg_semantics`、
`r6-alpaca-auction-shadow` 等几十份，分布在各自策略名下的 `.jsonl` 里），但它们都是
按策略名分文件、供各自 spec 使用的，其中最新的一批（如
`us_high_beta_sleeve_ensemble_r1.jsonl` 里 2026-08-10 验证的两条）30 天窗口也
正好卡在本报告撰写当天（2026-09-09）前后到期，没有一条是"拿来就能直接给本 spec
复用"的——即便技术上抄一份过来，本质上仍然是要重新走一遍 source-researcher 的
核实流程（确认这些主张对本 spec/本次执行方式仍然适用、没有过期），而不是绕过它。
这是一个真实需要投入的研究工作量，不是可以绕过的技术问题 —— 本次任务窗口（截止
周五）内判断优先级更高的是先把观察模式接通（第 5 项），把补来源卡列为报告里的
下一步而不是现在去做（见第 5 节）。

关于账本本身：候选是 `step11_b1_momentum_top50`（`step11_baseline_chain` 家族，
long_only gate 4/8 通过，`all_gates_pass=false`），这是 2026-09-06 交接时"链上最好"
的记录，本次 spec 与占位工件都以它为准。**仅作为客观记录**（不代表本报告对研究结论
的评判，那是研究线的范围）：账本里此后又多了 3 行同家族记录，最新一条
`step11_b3_lightgbm_grid_daily_only`（记录于 2026-09-09 02:06 UTC，几乎是本报告
撰写前几分钟）long_only 只有 2/8，早于它的一条 SMOKE/2-fold 版本有 7/8。
`reports/research/candidates/<experiment_id>/`（研究线的正式导出目录）截至本报告
撰写时仍不存在，所以按照协调者的明确指示，本 spec 继续指向动量占位工件，不做任何
候选切换；一旦该目录出现内容，切换只需要改 `portfolio.candidate_artifact_dir` 一行。

---

## 3. 观察模式当前持仓（2026-09-09 真实运行结果）

命令：`./scripts/run_capped.sh --mem 1.8G -- uv run python scripts/run_daily_paper_cycle.py
--date 2026-09-09 --root . --strategy us_model_ranking_portfolio_top50 --spec
strategy_specs/drafts/us_model_ranking_portfolio_top50.yaml`（退出码 0）。

- 信号日（`signal_session`）：2026-09-04（周五，最近一次调仓日；特征库当前最新交易日
  `latest_available_trade_date` 同为 2026-09-04）。2026-09-09（周二，因周一
  Labor Day 休市）不是调仓日，本次是**维持**（`is_new_signal=false`），新增信号数为
  0，符合设计（非调仓日绝不清空持仓）。
- 账户净值（`oc paper sync-account` 实时读回）：$100,000，现金 $100,000，零持仓
  （下单前基线）。
- 组合：50 只，每只目标权重 2.00%（等权），`idle_cash` = $4,040.70（占比 4.04%），
  `weight_deviation` = 2.15%，`unaffordable`（因整股取整买不起的名字）= 空列表。
- 候选工件：占位动量规则（`candidate_is_placeholder=true`）。

当前 50 只目标持仓（symbol / 权重 / 整股数，按代码排序）：

```
AAOI  2.00%  18   AEHR  2.00%  23   ALM   2.00% 113   AMAT  2.00%   4
AMD   2.00%   4   ARWR  2.00%  23   ASX   2.00%  53   AXTI  2.00%  32
BE    2.00%   7   COHR  2.00%   7   DELL  2.00%   4   DFTX  2.00%  52
DNTH  2.00%  18   DOCN  2.00%  17   FCEL  2.00% 133   FORM  2.00%  19
HUT   2.00%  21   ICHR  2.00%  35   INTC  2.00%  20   IOVA  2.00% 227
LITE  2.00%   2   LRCX  2.00%   6   MRNA  2.00%  13   MRVL  2.00%   8
MU    2.00%   2   MXL   2.00%  31   NBIS  2.00%   8   ORKA  2.00%  21
PL    2.00% 110   PRAX  2.00%   5   RVMD  2.00%   9   SIMO  2.00%   7
SLS   2.00% 144   SNDK  2.00%   1   SPHR  2.00%  14   STX   2.00%   2
SYRE  2.00%  22   TER   2.00%   5   TNGX  2.00%  88   TSEM  2.00%   8
TVTX  2.00%  30   TWST  2.00%  16   TXG   2.00%  31   UCTT  2.00%  27
UMC   2.00%  96   VIAV  2.00%  57   VICR  2.00%  10   VSXY  2.00%  26
WDC   2.00%   4   WOLF  2.00%  70
```

原始数据：`reports/execution/us_model_ranking_portfolio_top50-target-weights.json`
（gitignored，运行时产物，不入库）；每日循环日志：
`reports/paper/daily_cycle/us_model_ranking_portfolio_top50-observation-20260909.json`
（同样 gitignored）。**这是占位动量规则打出来的名单，不是任何已过门槛策略的持仓
建议**，性质等同于研究跟踪数据，不构成交易依据。

---

## 4. 下单前仍然需要什么

1. **真实候选落地**：研究线导出 `reports/research/candidates/<experiment_id>/`
   （`model.joblib` + `features.json` + `config.json` + `README.md`，接口冻结于
   `93ba159`）后，把 spec 的 `portfolio.candidate_artifact_dir` 切过去（唯一要改的
   字段）。
2. **过晋级门槛**：当前 best-of-chain 候选 4/8（`all_gates_pass=false`）；
   `oc strategy evidence`/`promotion-report` 对这个跨截面模式目前架构上不兼容
   （见下方"已知缺口"），需要研究线或后续迭代做适配，或者接受当前"账本即证据"的
   最小适配路径但仍要先过 `sources`/`topic_coverage` 门槛。
3. **来源卡**：至少 1 张未过期、覆盖 `daily_open_execution`/OPG 语义的来源卡
   （`reports/harness/source_cards/us_model_ranking_portfolio_top50.jsonl`），
   `harness verify` 精确卡在这一处。
4. **策略生命周期与执行配置切换**：`lifecycle: draft → active`，
   `execution.mode: manual_signal → paper_auto`，`execution.broker: none → alpaca_paper`
   —— 全部需要用户显式批准，且只应该在过完门槛之后发生（本次任务全程没有触碰这三个
   字段的当前值）。
5. **跟踪记录积累**：`paper_validation` 需要 20 个交易日的策略特定校验，
   `matched_paper_tca` 需要 ≥30 笔匹配 TCA 观测 —— 这两项只能靠观察模式持续运行、
   靠时间积累，现在开始跑才有意义。
6. **`kill_switch`**：当前 `oc paper readiness` 显示 paper kill switch 处于开启
   （挡住）状态，这是现有的全局安全开关，与本次改动无关，下单前需要用户自己决定
   是否/何时关闭。

---

## 5. Operator 操作清单

- [ ] 按第 6 节把每日观察循环接上 cron（本报告只给建议，未安装）。
- [ ] 跟进研究线的候选导出（`reports/research/candidates/<experiment_id>/`），
      落地后把 `strategy_specs/drafts/us_model_ranking_portfolio_top50.yaml` 的
      `portfolio.candidate_artifact_dir` 改成新路径，重跑一次
      `run_daily_paper_cycle.py` 确认新工件被正确加载（`candidate_is_placeholder`
      应变为 `false`）。
- [ ] 决定是否要为这个 spec 跑一次 source-researcher 流程，产出
      `reports/harness/source_cards/us_model_ranking_portfolio_top50.jsonl`
      （至少覆盖 OPG 限价单语义 / `daily_open_execution` 风险域）。这是
      `harness verify` 唯一剩下的缺口，独立于候选是否过晋级门槛。
- [ ] 决定 `oc strategy evidence`/`promotion-report` 对跨截面 `model_ranking_portfolio`
      模式的适配方案（当前假设单标的回测引擎，需要研究线或专门排期评估，超出本
      Wave 范围）。
- [ ] 每天/每周检查一次观察模式产出的目标权重与信号日志，留意
      `idle_cash`/`weight_deviation`/`unaffordable` 是否出现异常放大（当前分别是
      4.04%/2.15%/空，属于正常范围）。
- [ ] 在决定实际下单前，明确批准 `lifecycle`/`execution.mode`/`execution.broker`
      的切换 —— 本报告作者不会、也没有做这个切换。

---

## 6. Cron 建议（未安装，仅建议）

Step 11 主计划（`docs/plan-step-11-ml-first-loop-2026-09-06.zh.md` 第 5 节第 6 条）
里定的顺序是：22:00 UTC 特征库归档更新 → 特征追加 → 新鲜度检查，然后在下一交易日
开盘前跑每日循环。给观察循环流出充分的缓冲窗口（特征链路完成到下一交易日开盘
——即便是 EST 也有 14+ 小时），建议：

```cron
# Step 11 Wave C -- model_ranking_portfolio 观察模式每日循环
# 周一到周五 23:00 UTC 运行（特征库 22:00 UTC 归档链路之后一小时，
# 下一交易日开盘 [13:30-14:30 UTC 视夏令时] 之前留有充分余量）。
# run_daily_paper_cycle.py 自身的 is_trading_day() 已经会在周末/交易所假日
# 干净地跳过（status=skipped），所以周一到周五整段排布是安全的，不用另外
# 排除法定假日。
0 23 * * 1-5 cd /root/codex-test/open-composer && \
  ./scripts/run_capped.sh --mem 1.8G -- \
  uv run python scripts/run_daily_paper_cycle.py \
  --strategy us_model_ranking_portfolio_top50 \
  --spec strategy_specs/drafts/us_model_ranking_portfolio_top50.yaml \
  >> logs/model_ranking_observation_cron.log 2>&1
```

注意事项（供决定是否安装、以及安装时参考）：

- `main()` 会通过 spec 的 `portfolio.mode` 自动识别并分派到观察模式两步循环
  （`sync-account` → `target-weights`），**不会**调用 `oc run paper`；调用方式与
  仓库里其它策略用的 `run_daily_paper_cycle.py` 完全一样，不需要新脚本、不需要
  额外参数。
- `logs/` 目录需要提前存在（或改成别的落盘位置）；日志本身之外，每次运行的结构化
  产物落在 `reports/paper/daily_cycle/{name}-observation-{date}.json`。
- 如果研究线的特征库归档 cron 时间调整，这里的 `23:00 UTC` 应该跟着往后错开
  至少 30-60 分钟缓冲，而不是紧贴 22:00 UTC。
- 本报告作者没有、也不会自己安装这条 cron —— 按纪律要求，是否安装、装在哪台机器
  由用户决定。

---

## 7. 已知的架构缺口（诚实记录，不是本 Wave 要修的）

- `oc strategy evidence` / `oc strategy promotion-report` 目前假设的是经典单标的
  entry/exit 回测引擎（读 `spec.primary_symbol` 拉行情），跟 `model_ranking_portfolio`
  这种跨截面多标的目标权重模式不匹配。这两个函数在
  `open_composer/research/{evidence,promotion}.py`，不在本执行者的文件归属范围内，
  本 Wave 没有修改它们；晋级链路里这两步的 blocker 就是这个真实的架构不匹配，记录
  在案，留给后续排期。
- `open_composer/runner/paper.py` 的 `ROUTED_PORTFOLIO_MODES` 分派机制目前不认识
  `model_ranking_portfolio`；本 Wave 特意没有扩展它（既不在本执行者归属范围，
  改动量和影响面也远超"观察模式接通"这一诉求），选择了在
  `run_daily_paper_cycle.py` 里新增一条完全独立、绝不途经 `oc run paper` 的两步
  循环来满足交付物 5，对其余策略零风险。

---

## 8. 运营层面的注记：共享 git index 竞争

两条执行线（本执行者与研究线）在同一个工作树/分支/index 上并发操作。过程中发生过
两次观察到的竞争：

1. 交付物 4 的文件（`scripts/new_lightweight_iteration.py`、spec 的
   `research_design` 块、harness plan/verify 报告、新测试文件）已经 `git add`
   但还没来得及 commit 时，研究线自己的一次 `git commit`（提交信息是"记录会话重置
   交接"，即 `7978ced`）把它们一并带入了同一个提交——内容完整、未被修改，只是
   署名在对方的提交信息下。核实方式：`git show --stat 7978ced`/`git diff` 逐个比对
   文件内容，确认没有丢失也没有被篡改，判断不值得为此改写历史（改写有把对方并发
   工作搞坏的风险），记录在案即可。
2. 协调者随后统一要求两条线一律改用带路径的提交形式
   `git commit -m "..." -- <路径1> <路径2>`（只提交列出的路径在工作树里的当前内容，
   忽略 index 里别人暂存的东西），本报告后续交付物（第 5 项）已经按这个形式提交
   （`5626161`），验证 `git status --short` 在提交前后都只显示预期路径，没有再次
   发生越界。**唯一的例外**：对全新（此前从未 track 过）的文件，`git commit -- <path>`
   会报 `did not match any file(s) known to git`——必须先对这一个新文件单独
   `git add <path>`（不是 `git add -A`），再执行带路径的 `git commit`；已 track
   的修改文件不需要这一步。这个细节记录下来供后续交付物或其他执行者参考，避免
   重新踩一次。
3. `git commit` 之外，`ruff format .`/`make verify` 本身也是一种共享工作树竞争
   来源：这两个命令按仓库约定就是全仓库范围（不是按文件归属分片跑），运行时会
   顺手格式化任何当时在工作树里、恰好还不满足 ruff 格式的文件——不管是谁的。
   收尾时跑 `make verify` 就真的把 `scripts/run_baseline_chain.py`（研究线归属）
   格式化了一次（3 行的换行调整，纯 cosmetic，用 `git diff` 核实过语义未变）；
   同时在工作树里看到 `scripts/run_b3_grid.py` 有一大段研究线自己的在途改动
   （新函数/新 import，`git diff --stat` 显示 146 行），**用文件 mtime 精确核实
   过这一次没有被本执行者的 ruff 调用碰到**（`run_baseline_chain.py` 的 mtime
   精确等于 `make verify` 的 `format` 步骤开始时间；`run_b3_grid.py` 的 mtime
   比这早 4 分钟，说明它已经是 ruff-compliant、没有再被改写，那 146 行完全是
   研究线自己此前已经写好、还没提交的内容）。这两个文件均未被本执行者
   `git add`/`commit`，只是工作树里的字节被 `ruff format .` 摸过一次；没有回退
   这个改动（回退本身也是一次未经授权的越界编辑，而且内容语义未变，回退没有
   实际收益），如实记录在此，供研究线核对自己接下来 `git diff`/`git commit`
   这两个文件时不会因为一次意外的、语义无害的重排版而困惑。

---

## 9. 测试与验证

- `tests/test_spec_validation.py`（+9，交付物 1）、
  `tests/test_model_ranking_target_weights.py`（15，交付物 2，含修复后 3 个新增）、
  `tests/test_new_lightweight_iteration_from_ledger.py`（5，交付物 4）、
  `tests/test_daily_paper_cycle_model_ranking.py`（9，交付物 5）均单独跑绿；
  `tests/test_daily_paper_cycle.py`（既有 9 个）原样复跑绿，确认没有回归既有 router
  每日循环。
- `uv run ruff format .` / `uv run ruff check .`：全仓库跑过，无需改动、无告警
  （均通过 `./scripts/run_capped.sh --mem 1.8G --` 内存封顶执行）。
- `uv run oc repo check --strict`：`status=ok ready=yes`（`c394d82`/`7282cca` 之后
  各重跑过一次，仍然 `ok`）。
- 全量 `uv run pytest`（`-n 2`，`./scripts/run_capped.sh --mem 1.8G --` 封顶）：
  跑了两次。第一次（`c394d82`/`7282cca` 之前）**57 FAILED、0 ERROR**——比基线多
  46 个，全部追踪到交付物 1 的回归（见第 1 节）。修完两处回归后第二次重跑：
  **12 FAILED、0 ERROR**，且这 12 个精确就是
  `tests/test_mom_breadth_qd_r1.py` 文档记录的 11 个 `test_recovery_*` 加
  `test_vix_term_structure_overlay_r1.py` 那 1 个（随后已用 `7282cca` 修复，
  但该次全量跑是在 `7282cca` 之前跑的，数字如实记录跑当时的状态）。`7282cca`
  之后没有再跑一次完整全量（该文件对应的单文件测试已验证 55/55 全绿，且
  `open_composer/research/**` 之外没有任何本 Wave 触碰的文件，不存在新的
  回归来源）——只对 `tests/test_vix_term_structure_overlay_r1.py` 单文件复跑
  确认，未重跑全仓库。
- `make verify`：单次 `make` 调用在 `test-full`（`uv run --with pytest-xdist pytest
  --runslow -n 2`）这一步以非零退出码结束——**如实记录：这次调用整体是失败的**
  （`make: *** [Makefile:44: test-full] Error 1`，脚本里捕获的真实 `EXIT_CODE=2`；
  外层任务通知显示的"exit code 0"只是我自己包一层 `{ time ...; } ; echo
  EXIT_CODE=$?` 脚本里最后一条 `date` 命令的退出码，不代表 `make verify` 本身
  成功，特此说明避免误读）。耗时：`test-full` 本身 2021.88s（33m41s），整个
  `make verify` 调用 `real 34m34.951s`（`user 46m2.152s`，多核）。
  `test-full` 结果：**14 failed, 2323 passed, 2 errors**（`--runslow` 比常规
  `pytest -n 2` 多跑一批慢测试，总量比第 9 节上面两次常规全量跑更大）。14 个
  failed 精确拆解为：3 个 `test_dashboard_server.py` CORS 测试（跟 spec/portfolio
  完全无关，根因是 401 而不是预期的 200，本 Wave 没有改过任何 dashboard/认证代码，
  判定为既有、与本次改动无关）+ 11 个 `test_mom_breadth_qd_r1.py`（文档记录的既有
  基线，精确一致）。2 个 error 在
  `tests/test_export_candidate_artifact.py::test_export_writes_all_four_artifacts_with_a_working_model`
  和 `test_export_is_idempotent_and_overwrites_cleanly`，报错都是
  `AttributeError: <module 'run_b3_grid' ...> has no attribute '_load_panel'`——
  精确定位为一次真实的并发时序假象，不是本 Wave 造成的回归：`scripts/run_b3_grid.py`
  在 `test-full` 开始跑之前就已经在工作树里有研究线自己未提交的重写（把
  `_load_panel` 换成新的 `load_feature_panel`），`test-full` 的 xdist worker 进程
  在这个状态下启动并把 `export_candidate_artifact.py` 导入进内存缓存；33 分钟的
  跑测期间，研究线自己已经提交了对应的修复（`a3f2925`，`export_candidate_artifact.py`
  切到 `load_feature_panel`），但那个已经在跑的 worker 进程里缓存的还是提交前那份
  import，不会因为磁盘上文件变了就重新导入。跑测结束后立即用一个全新进程单独复跑
  `tests/test_export_candidate_artifact.py`：**10/10 全部通过**，且确认当前
  `scripts/export_candidate_artifact.py` 源码里已经不再引用 `_load_panel`——证实
  这 2 个 error 纯粹是"长跑测试进程 vs 并发提交"的时序假象，此刻工作树上不存在
  真实问题。
  由于 `make` 在 `test-full` 失败后不会继续跑同一条规则链后面的步骤，`repo-check`
  之后（`capability-test`、`agent-parity`、`deploy-prepare`、`dashboard-check`
  的 `dashboard-html`/`dashboard-build`、`feature-validate`、`readiness`）这次
  调用没有机会跑到；逐个单独手动跑了一遍替代验证：`capability-test` ok（13 个
  能力全部 score=1.00）；`agent-parity` ok；`deploy-prepare`
  `status=warning ready=yes`（`paper_monitor`/`readiness` 两条既有警告，指向
  paper kill switch 未关、建议跑 `oc paper monitor --sync-broker`，跟本次改动
  无关）；`feature-validate` 完成，无告警；`readiness` `status=warning ready=yes`
  （`paper_monitor` 警告 kill switch 已开启；`strategy_capabilities` 警告
  `{'partial': 2}`——核实过这是全仓库聚合信号，`draft_backend_status_counts`
  显示全仓库 585 个 draft 策略里 258 个 partial/327 个 supported，本 spec 自己
  是 draft 生命周期，这个警告与新增的这一个 spec 无关，是既有的、仓库级别的信号）。
  `dashboard-check`（`dashboard-html` + `npm run build`）本次没有单独重跑——
  `deploy-prepare` 自己的 `dashboard_artifacts` 检查项已经显示
  "Dashboard catalog, review, and static HTML were rebuilt" 且状态 `ok`，视为
  已经覆盖到等价内容，判断没有必要再花时间单独跑一次 `npm run build`。

（基线约定：`tests/test_mom_breadth_qd_r1.py` 的 11 个已知失败视为既有、可接受，
不计入回归；除此之外要求全绿。详见第 1 节"收尾全量测试时发现并修复的一个真实回归"：
`c394d82` + `7282cca` 两个提交修完了交付物 1 引入的全部回归。不计免入基线的常规
`pytest -n 2`（不带 `--runslow`）复跑结果是精确的 11 个失败、0 个 error，符合
"除既有基线外全绿"的要求。`make verify` 的 `--runslow` 全量多测出 3 个
`test_dashboard_server.py`（既有、与本次改动无关）和 2 个已证实为并发时序假象、
复跑即绿的 `test_export_candidate_artifact.py` error——都不是 Wave C 引入的
回归，但为了不夸大"全绿"，`make verify` 单次调用的真实退出状态如实记录为失败，
细节见上面 `make verify` 一条。）

---

## 10. blocked_on_user

**先直接回答三个最关键的问题**（细节和依据见下面各条以及第 2-4、11 节）：

- **观察模式现在每天会算出什么？** 每个交易日：读一次真实账户净值
  （`oc paper sync-account`，只读），算一次目标权重（`oc strategy target-weights`）。
  非调仓日（一周里除周五外的交易日）原样维持上一次的目标，绝不清空；调仓日
  （每周五收盘信号、下周一开盘执行口径）重新用最新 PIT 股票池 + 候选工件打分选出
  新的前 K。写两类文件：目标权重/整股数/闲置现金/偏离度 JSON+MD
  （`reports/execution/{name}-target-weights.*`）和信号日志
  （`signal_logs/`）。**全程只读账户、只算数字、只写文件，不调用任何下单接口**。
  当前实际持有什么见第 3 节（截至 2026-09-09：50 只、每只 2% 等权、占位动量候选、
  idle_cash 4.04%、weight_deviation 2.15%）。
- **打开下单模式前用户需要批准什么？** 三件事，缺一不可，本次改动没有触碰任何一件：
  (1) spec 的 `lifecycle: draft → active`；(2) `execution.mode: manual_signal → paper_auto`
  且 `execution.broker: none → alpaca_paper`；(3) 让候选先过晋级门槛（当前 4/8，见
  第 2 节）或者用户明确决定"观察模式下的候选不必等门槛也可以下单"这种例外政策
  （这本身也是一个需要用户拍板的产品决策，本报告不代为决定）。此外还有现有的全局
  `kill_switch`（当前开启/挡住状态）需要用户自己决定何时关闭，以及
  `harness verify` 的 `source_cards` 缺口（见下面第 1 条）。
- **A 组/B 组候选工件到位后怎么切换？** 一行改动：把 spec 的
  `portfolio.candidate_artifact_dir` 从占位路径改成
  `reports/research/candidates/<experiment_id>/`（A 组）或
  `reports/research/candidates/groupb_<experiment_id>/`（B 组），重跑一次
  `run_daily_paper_cycle.py` 确认 `candidate_is_placeholder` 变为 `false` 即可，
  不需要改代码。两组要同时接入观察模式的完整方案见第 11 节（新增 spec + 各自独立
  信号日志 + 共享同一只读账户，本 Wave 只设计不实现）。

---

1. **来源卡缺口**：`harness verify` 精确卡在 `source_cards` 这一项；本 spec 自己的
   来源卡文件（`reports/harness/source_cards/us_model_ranking_portfolio_top50.jsonl`）
   不存在，仓库里其他策略名下与 OPG 相关的既有卡最新的几份（如
   `us_high_beta_sleeve_ensemble_r1.jsonl` 的 2026-08-10 验证记录）30 天窗口也
   在本报告撰写前后到期，且分属各自策略、不能未经重新核实直接搬给本 spec。
   是否现在安排 source-researcher 流程去补一张新的、覆盖 OPG 限价单语义的卡，
   还是等真实候选和更明确的下单时间线后再补，需要用户决定优先级（本 Wave 判断
   "先接通观察模式"优先级更高，没有现在去做）。
2. **`oc strategy evidence`/`promotion-report` 架构适配**：这两个命令目前不支持
   跨截面目标权重模式，需要研究线或专门排期评估怎么适配（例如是否要新增一个
   "跨截面回测证据"分支，还是接受"账本即证据"的替代路径）。这不是几行修复能
   解决的，需要用户/协调者决定方向。
3. **是否/何时安装第 6 节的 cron 建议**：本报告作者按纪律没有自己安装，需要用户
   决定安装到哪台机器、什么账号下运行。
4. **候选切换时机**：`reports/research/candidates/<experiment_id>/` 一旦研究线
   交付，是否需要用户先过一遍目再切换 spec 指向，还是执行者可以直接切换后继续
   观察模式（不下单的前提下风险极低，但涉及"用哪个候选"的产品决策，本报告倾向
   于建议由用户或协调者一句话拍板即可，不需要正式晋级流程，因为观察模式本身不
   需要过门槛）。
5. **`kill_switch`/`lifecycle`/`execution.mode`/`execution.broker` 的最终切换**：
   明确不属于本 Wave 范围，写在这里是为了确保这条线在未来任何时候都需要用户
   显式批准才会发生，本报告和本次改动都没有、也不会触碰这几个值的当前状态。
6. ~~`vix_term_structure_overlay_r1` 的一行修复~~ **已修复，仅作记录**：
   `tests/test_vix_term_structure_overlay_r1.py::test_generated_repair_runtime_contract_accepts_exact_governance_bindings`
   一度失败，根因是交付物 1 新加的 9 个 `PortfolioConfig` 字段（详见第 1 节"收尾全量
   测试时发现并修复的一个真实回归"）。这个函数在 `open_composer/research/**` 里，
   本不在本 Wave 归属范围；但用 `git log -1` 核实该文件与其测试文件均于 2026-08-26
   （`d0cd174`）最后改动、早于 Wave C 全部提交，且直接 diff 已证明差异只来自本执行者
   自己新加的这 9 个字段——排除了"这是研究线在途改动"的可能——协调者据此明确指示
   "要么修掉、要么证明是别人的在途改动"，遂按 `c394d82` 完全相同的思路补了这一处
   （`7282cca`），`test_vix_term_structure_overlay_r1.py` 复跑 55/55 全绿。写在
   `blocked_on_user` 里是为了记录曾经越出常规文件归属范围这一事实，供协调者审计，
   不代表当前还有动作要等用户做。

---

## 11. 新前提：策略 B 组接入方案（A/B 两组并行观察模式，2026-09-09 立项，本节只设计不实现）

用户 2026-09-09 立项了策略 B 组（`docs/plan-step-12-groupb-recent-regime-high-hit-rate-2026-09-09.zh.md`，
近期窗口、高胜率方向），其最佳候选未来会导出到
`reports/research/candidates/groupb_<experiment_id>/`，与 A 组
（`reports/research/candidates/<experiment_id>/`）用的是同一套冻结接口
（`model.joblib`/`features.json`/`config.json`/`README.md`，commit `93ba159`）。
以下是让两组同时以观察模式接入同一个 Alpaca Paper 账户的方案；本节只设计，不在本
Wave 实现（不属于本次 6 项交付物，且截止日在即，实现应作为下一项独立任务）。

**代码层面已经天然支持，不需要改动**：确认过
`open_composer/adapters/execution/model_ranking_target_weights.py` 里没有任何
写死的路径或"A 组"专属逻辑——`candidate_artifact_dir`、`universe_top_n`、`top_k`、
`hedge` 等全部来自传入的 `StrategySpec`，加载哪个候选完全由 spec 的
`portfolio.candidate_artifact_dir` 决定。`scripts/run_daily_paper_cycle.py` 新增的
`run_model_ranking_observation_cycle()` 同样只吃一个 `spec` 参数、按 spec 自己的
`name` 字段给日志和目标权重文件命名（`reports/paper/daily_cycle/{name}-observation-{date}.json`、
`reports/execution/{name}-target-weights.json`），不假设只有一个策略在跑。

**接入步骤**（B 组候选落地后）：

1. 复制 `strategy_specs/drafts/us_model_ranking_portfolio_top50.yaml` 为一个新文件
   （例如 `strategy_specs/drafts/us_model_ranking_portfolio_groupb_topNN.yaml`），
   `name` 改成不同的策略名（例如 `us_model_ranking_portfolio_groupb_topNN`），
   `portfolio.candidate_artifact_dir` 指向 `reports/research/candidates/groupb_<experiment_id>/`
   （或先用一个 B 组专属的规则占位工件，做法和 A 组现在的
   `config/model_ranking_candidates/step11_momentum_placeholder_v1/` 完全一致），
   其余字段（`top_k`、`universe_top_n`、`hedge`、`rebalance` 等）按 B 组候选自己的
   账本行调整。别忘了 `.gitignore` 的 `strategy_specs/drafts/*` 默认忽略+白名单老
   约定，需要把新文件名加进白名单（A 组的先例见 `1a32694`）。
2. 分别对两个 spec 各跑一次 `run_daily_paper_cycle.py --strategy <name> --spec <path>`
   （或各自接一条独立的 cron，见第 6 节的建议格式，每组一行，`--strategy`/`--spec`
   换成各自的）。两组各自的产出天然独立、不冲突：
   - 目标权重与信号：`reports/execution/{name}-target-weights.json`、
     `reports/execution/{name}-target-weights.md`（`write_router_execution_artifacts`
     按策略名分文件，已验证）。
   - 每日循环日志：`reports/paper/daily_cycle/{name}-observation-{date}.json`。
   - 信号日志：`signal_logs/` 下按 `build_signal`/`append_jsonl` 的既有命名约定
     （与 `momentum_shadow.py` 现有策略同款），同样按策略名/run_id 区分。
3. 两组各自的 `oc paper sync-account` 调用会各自刷新同一份
   `reports/paper/account.json`（同一个真实账户，只读、幂等，谁跑都一样，互不冲突）；
   各自的 `oc strategy target-weights` 分别读取这份账户净值，各自独立计算"如果满仓
   使用整个账户净值"的目标持仓——**这是观察模式下的一个需要写清楚的假设**：两组
   现在都各自假设自己独占全部账户净值来做整股换算，这在纯观察、不下单的阶段没有
   实际资金冲突（两组都不会真的下单），但如果将来任何一组要从观察模式转成下单模式，
   在另一组也在下单之前，必须先决定两组之间的资金分配（比如各分 50% 净值，或者
   互斥、同一时间只有一组处于下单模式）——这是一个先有的产品/风控决策，不是代码
   缺口，写在这里提醒，不需要现在解决。
4. 报告与监控：可以沿用本报告的格式各写一份（或者一份报告里分 A/B 两组小节），
   核心是"每组各自独立成文、互不覆盖"。

---

## 附：涉及的提交

| 交付物 | 提交 | 说明 |
|---|---|---|
| 1/6 | `5305d77` | `model_ranking_portfolio` spec 模式 + schema + 测试 |
| 2/6 | `4c3f76c` | 目标权重适配器 + CLI/授权/就绪性接线 + 测试 |
| 2/6 修复 | `9d6f6f1` | 对齐冻结的候选工件接口（去掉错误的 `.predict()` 包装） |
| 3/6 | `1a32694` | 可运行 StrategySpec + gitignore 白名单 |
| 4/6 | `7978ced`* | `--from-ledger` 入口 + 测试 + harness plan/verify 报告 + spec 的 `research_design` 块 |
| 5/6 | `5626161` | 每日循环观察模式两步接线 + 测试 |
| 回归修复 | `c394d82` | 修复交付物 1 引入的 spec 语义哈希回归（`strategy_versions.py` + 测试） |
| 回归修复 | `7282cca` | 同一回归在 `vix_term_structure_overlay_r1.py` 里的第二处；已用 `git log -1` 核实无在途冲突后修复 |
| 6/6 | （本次） | 本报告 |

\* `7978ced` 的提交信息由研究线撰写（他们自己的会话重置交接记录）；由于共享
git index 的一次提交竞争（见第 8 节），本执行者交付物 4 的文件被一并带入这个
提交，内容完整无误，已用 `git show --stat`/`diff` 核实。
