# Open Composer 策略研究产品补救计划

日期：2026-05-26

状态：Claude 严格 review 后修订版

## 0. 给 no-context Codex / Claude Code 的阅读说明

这份文档是给没有上下文的 Codex、Claude Code 或审查 agent 使用的。它记录一次 TQQQ 策略生成与优化过程中暴露的产品和执行问题，并给出下一步产品修改计划。

审查或实施前必须同时读取：

- `AGENTS.md`
- `README.md`
- `docs/product-golden-path-codex-quant-review-2026-05-13.zh.md`
- `docs/local-product-optimization-plan-2026-05-25.zh.md`
- `.agents/skills/strategy-research-orchestrator/SKILL.md`
- `.agents/skills/source-researcher/SKILL.md`
- `.agents/skills/backtest-forensics/SKILL.md`
- `.agents/skills/data-capability-reviewer/SKILL.md`
- `.agents/skills/execution-reality-reviewer/SKILL.md`
- `reports/research/control/product-strategy-research-process-memory.md`

核心结论：这次问题不是“某个参数没有调好”，而是策略研究产品没有把专业研究流程硬化成不可绕过的本地门禁。严格 review 后进一步确认：约 70% 的能力不是缺系统，而是已有零件没有接到 fail-fast 门禁；真正新增应集中在 search budget 强制、random search、PBO/CSCV proxy、universe audit 和统一 gate 写入函数。

## 1. 产品边界

Open Composer 是个人 AI 策略工作台，不是投资建议系统、多人 SaaS、真金交易系统或纯聊天助手。

必须保持的边界：

- `StrategySpec` 是策略行为真相来源。
- Dashboard 是本地读模型和受控操作面，不是第二真相源。
- 长任务由 CLI / files / Codex / Claude Code 执行，并写入可审计产物。
- LLM、新闻、事件、宏观信号必须先物化为 point-in-time replay packet，才能影响回测、promotion 或 paper readiness。
- `workflow_pass`、`research_pass`、`llm_contribution_pass`、`paper_ready_pass` 必须分离。
- 样本、fixture、cache fallback、trial/research-only 数据不能作为 paper-ready 市场证据。
- Alpaca Paper 是当前唯一自动化模拟盘写入路径，且必须显式确认；真金 broker 写入不在 MVP 范围内。

## 2. 修订后的诊断

### 2.1 研究权威倒置

问题：策略方法的有效性过多来自用户想法，而不是 agent 主动联网调研成熟量化方法、数据约束和执行约束。

表现：

- 用户提出市场周期、做空、SQQQ、VIX、更多股票扫描等方向后，agent 很快进入测试，而不是先做独立文献和平台规则调研。
- 用户明确说明自己不是专业量化研究员，但 agent 仍把用户想法当作主要方法来源。
- 缺少“用户偏好”和“专业方法有效性”的显式分离。

产品修复方向：Research Brief Gate 必须先记录 `user_preferences`，但只有被 source cards、factor lab 或明确 exploratory 标记支持的方法才能进入 search space。

### 2.2 研究假设缺失或过晚

问题：策略优化先跑了大量组合，再补解释。

表现：

- 没有先写清楚 central hypothesis、失败模式、验收标准和拒绝标准。
- 没有先定义哪些因素是理论驱动，哪些只是探索性特征。
- 没有明确“什么结果会否定这条研究路线”。

产品修复方向：已有 `ResearchBrief` 类，但没有 CLI init/validate，也没有在 `parameter-sweep` 前 fail-fast。

### 2.3 参数和路线组合测试过重

问题：大量网格搜索替代了因子研究。

表现：

- iter5 曾测试约 `3480` 个候选。
- candidate ledger 约 `106MB`，trial ledger 约 `7.3MB`；两者都说明输出膨胀，但后续报告必须区分 candidate ledger 和 trial ledger，不能混称。
- 很多试验是在 route label、lookback、gate 参数之间排列组合，而不是先证明单因子边际贡献。

产品修复方向：`StrategySpec.research_design.candidate_budget` 已存在，但 `parameter-sweep` 没有把它作为硬预算；大网格默认应被阻止或要求 large-search justification。

### 2.4 过拟合控制后置

问题：walk-forward、PBO/多重检验风险、参数稳定性和 OOS 衰减更多是在结果出来后评论，而不是进入优化协议本身。

表现：

- 高收益候选出现后，才用回撤、负年份、walk-forward 做否决。
- 试验数量、参数数量、研究耗时没有在优化开始前成为预算。
- 最佳结果容易被叙述成策略能力，而不是候选发现。

产品修复方向：promotion 已有 OOS、walk-forward、cost sensitivity、data sanity、benchmark family；缺口是把多重试验风险量化为 PBO/CSCV 或 DSR proxy，并让高 trial count 自动触发。

### 2.5 数据范围和宇宙质量没有先决

问题：用户要求更长回测后，才暴露历史数据不足对优化质量的影响。

表现：

- 没有先完成 long-history data source review，再开始设定跨周期标准。
- 当前符号宇宙容易产生 survivorship bias。
- 当前大盘股宇宙与用户期望的高收益扫描之间没有明确数据能力差距说明。

产品修复方向：capability registry 已覆盖 provider/timeframe 等能力，但不负责 PIT universe、current-symbol bias、survivorship bias；需要新增 universe audit，聚焦这三件事。

### 2.6 因子研究没有成为前置

问题：策略组合测试多，因子质量证据少。

表现：

- `oc strategy factor-lab` 已存在，但没有在策略优化前成为强约束。
- Factor lab 结果更多是 promotion evidence，而不是进入 search space 的前置证据。
- 没有把 factor family 失败记录用于剪枝。

产品修复方向：不重建 Factor Lab；只把已有 `run_factor_lab()`、promotion check 和 Dashboard 指标接到 research_pass 前置，并把指标分级。

### 2.7 做空 / SQQQ / VIX 方向测试过于机械

问题：防守和熊市收益的方向被机械组合，而不是先分析产品结构、风险来源和替代方案。

表现：

- 直接引入 SQQQ 或做空方向，理论分析不够。
- 对 leveraged / inverse ETF 的日度复利、路径依赖、交易成本和持有期风险说明不足。
- 对 VIX 产品、volatility risk premium、contango/backwardation 等结构没有形成清晰方法边界。

产品修复方向：已有 source card 和 execution reality 能力；缺口是 search space 与 source card 的双向 link 校验，未被支持的方法只能标为 exploratory，不得进入 promotion。

### 2.8 接入模拟盘的标准不够产品化

问题：用户说“可以接入模拟盘”后，agent 容易把 workflow pass 或研究候选说得过于接近 paper readiness。

表现：

- 策略可以跑通不等于 research pass。
- research pass 不等于 paper_ready_pass。
- leveraged ETF、daily open execution、router target weights、order style、slippage/gap stress、signal logs 都必须独立通过。

产品修复方向：execution reality reviewer、RealityModel、execution policy、paper readiness 都已存在；主要是 Dashboard 和 CLI 文案必须把 blocker 显示成硬状态，而不是“接近可交易”。

### 2.9 Dashboard 与 Codex 入口不等价

问题：Dashboard 可能通过项目、queue、trace 展示结构化流程；Codex 直接对话时，如果 agent 自律不足，就会跳过门禁。

表现：

- 用户在 Codex 中直接推进策略时，流程主要依赖 agent 记忆和自我约束。
- 技能文件存在，但没有每一步都由工具或 artifact contract 自动校验。
- Dashboard 的建议和 Codex 的执行之间缺少同一套 gate 写入路径。

产品修复方向：不新增 `gate-state.json` 或 `research_state.json`。已有 `ProjectGateSummary`、`projects/{id}/project.yaml.gate_summary` 和 `trace.jsonl`；只新增一个 `update_gate_state()` 函数，让 CLI、Dashboard、agent 入口都走同一写入路径。

### 2.10 LLM 的优势没有正确发挥

问题：LLM 主要被用来解释、排列组合和响应用户，而不是用于研究生产力最大化。

应发挥的优势：

- 快速搜集成熟方法、官方文档、论文和风险警示。
- 把用户想法转为可验证假设，而不是直接视为方法真理。
- 自动生成 research brief、factor lab plan、search space、failure modes、review checklist。
- 把失败试验归纳成 memory，减少重复搜索。
- 生成结构化报告和审查包，便于另一个 agent 反驳。

修订判断：多 agent specialist review 是推荐实践，不是 Step 5 必做门禁。Codex / Claude Code 单进程无法强制 role 隔离；强制角色分工不会比现有 skill prompt 多提供产品保证。

## 3. 已有零件与真正缺口

| 计划项 | 仓库已有 | 真正缺口 |
|---|---|---|
| Research Brief Gate | `open_composer/research/kernel/workflow.py` 已有 `ResearchBrief` | CLI `research-brief init/validate`、spec hash 绑定、`parameter-sweep` fail-fast |
| Source Research Gate | `open_composer/models/source_card.py`、`harness/source_policy.yaml` | brief 与 source card 双向 link 校验 |
| Factor Lab 前置 | `oc strategy factor-lab`、`open_composer/research/factor_lab.py`、promotion factor check | factor-lab 作为 research_pass 前置，缺失时 blocked 而非弱 warning |
| Trial Ledger | `open_composer/research/kernel/trials.py`、`parameter_sweep` 已写 ledger | budget 强制、pruned/rejection_reason 字段、random search |
| Robustness | promotion 已有 OOS、walk-forward、cost、data、benchmark | PBO/CSCV 或 DSR proxy |
| Universe Audit | capability registry 覆盖 provider/timeframe | PIT universe、current-symbol bias、survivorship audit |
| LLM Contribution | `_llm_marginal_lift_checks` 已有 baseline、variant、missing modality、lift、independence | prompt/version stability |
| Execution Reality | execution reviewer、RealityModel、execution policy、promotion check | leveraged ETF 路径依赖说明更硬化；大部分是接线 |
| Gate State | `ProjectGateSummary`、`project.yaml.gate_summary`、`trace.jsonl` | 单一 `update_gate_state()` 写入函数 |
| Multi-agent Review | `.agents/skills/` 和 handoff 文件协议 | 不做强制角色分工，保留为最佳实践 |

## 4. 外部方法依据

本计划不是凭空增加流程，而是把成熟研究实践产品化：

- QuantConnect Research Guide 强调 hypothesis-driven research，并把 backtest count、parameter count、research time 作为 overfit 风险信号；它也提醒偏离核心假设时应回到 thesis development。来源：https://www.quantconnect.com/docs/v1/key-concepts/research-guide
- QuantConnect walk-forward 文档说明，参数最优值随训练窗口变化，walk-forward 需要在过度频繁优化和过拟合风险之间取舍。来源：https://www.quantconnect.com/docs/v2/writing-algorithms/optimization/walk-forward-optimization
- Bergstra & Bengio 的 JMLR 论文指出，在很多高维参数空间中，random search 比 grid search 更高效，因为通常只有少数参数真正重要。来源：https://jmlr.org/papers/v13/bergstra12a.html
- Optuna 论文提出 define-by-run、pruning 和可扩展优化框架，适合混合搜索空间和试验早停；本修订版将它降级为 Phase 2 可选项。来源：https://arxiv.org/abs/1907.10902
- Bailey、Borwein、Lopez de Prado、Zhu 的 PBO 研究提出用 CSCV 估计 backtest overfitting 概率，适合作为多重试验后的风险诊断依据。来源：https://www.semanticscholar.org/paper/The-Probability-of-Backtest-Overfitting-Bailey-Borwein/b1233b4f5384f003e85c2e0eec1a2dfc08f624c5
- pymoo 文档展示了多目标优化和遗传算法工具链；本修订版将 NSGA-II 降级为 router 专用扩展，不作为普通策略默认优化器。来源：https://pymoo.org/algorithms/index.html

## 5. 目标工作流

未来任何策略生成或优化必须按这个顺序运行：

```text
用户想法
  -> 读取 AGENTS / skills / strategy memory
  -> 外部 source research
  -> research brief validate
  -> capability / data / universe review
  -> factor lab / marginal factor evidence
  -> 预注册 search space 和 search budget
  -> random 或 bounded grid candidate discovery
  -> benchmark family
  -> chronological OOS / walk-forward
  -> PBO/CSCV or DSR proxy when trial count is high
  -> backtest forensics
  -> execution reality review
  -> promotion report
  -> paper readiness
  -> paper-only command gate
```

禁止路径：

```text
用户想法
  -> 直接大规模 grid search
  -> 选择最高收益
  -> 事后补报告
  -> 宣称可接入模拟盘
```

## 6. Step 5 必做计划

这版计划不再分散成 P0-P10，而是收敛为一个 Step 5，分三波交付。目标是先接上已有零件，再做少量真正新增。

### Wave 5.1：硬门禁

目标：直接阻止“没有 brief、没有预算、先大网格”的路径。

修改：

- 复用并扩展 `open_composer/research/kernel/workflow.py:ResearchBrief`，不要重建另一套 brief schema。
- 新增 CLI：

```bash
uv run oc strategy research-brief init <spec>
uv run oc strategy research-brief validate <spec>
```

- Research brief 最小必填字段：
  - `spec_hash`
  - `central_hypothesis`
  - `source_cards_required`
  - `search_budget`
  - `acceptance_criteria`
  - `rejection_criteria`
  - `known_failure_modes`
- 其他字段作为选填或自动生成，不把旧文档中 22 个字段全部设为硬必填。
- `oc strategy parameter-sweep <spec>` 调用前 fail-fast：
  - 缺 brief：abort。
  - brief 的 `spec_hash` 与当前 spec hash 不一致：abort。
  - 计划候选数超过 `search_budget`：abort。
  - 默认 `search_budget=64`。
  - 超过 64 必须有 `justification_for_large_search`。
- `parameter-sweep` 执行过程中 ledger 行数超过 budget 必须 abort，不只是 warning。
- `oc strategy evidence` 或 promotion 入口也应调用 `validate_research_brief`，防止绕过 sweep。

验收测试：

- `test_parameter_sweep_blocked_without_brief`
- `test_parameter_sweep_blocked_when_brief_hash_is_stale`
- `test_parameter_sweep_blocked_when_candidates_exceed_budget`
- `test_evidence_blocks_without_valid_brief_for_optimized_strategy`

### Wave 5.2：已有零件接线

目标：把已经存在的 source card、factor lab、gate summary 接到研究门禁。

修改：

- Source research linkage：
  - 扩展 source card 或 brief link 校验，不强行替换 `SourceCard` 现有 schema。
  - brief 中每个 `method_family` 必须有 source card，或标记 `exploratory=true`。
  - search space 中出现 `inverse_etf`、`shorting`、`vix`、`llm_feature`、`news`、`macro`、`event` 时，必须能找到对应 source card 或 capability evidence。
- Factor Lab 前置：
  - 复用 `oc strategy factor-lab` 和 `run_factor_lab()`。
  - promotion 已经会跑 factor lab，但 research_pass 前置要更硬：缺失 factor lab 或 status blocked 时，`research_pass=false` 且 blocked reason 写入报告。
  - 指标分级，不让简单策略被 13 个指标全部卡死：
    - baseline 必须：coverage、missing rate、rank IC、top-bottom spread。
    - research_pass 必须：rolling IC mean/min、single-factor baseline、marginal lift。
    - paper_ready 建议：missing-factor robustness、IR、factor decay。
- Gate state 写入：
  - 不新增 `gate-state.json`。
  - 不新增 `projects/{id}/research_state.json`。
  - 在 `open_composer/projects.py` 新增 `update_gate_state(project_id, gate_name, status, reasons, agent)`。
  - 函数内部同时更新 `projects/{id}/project.yaml.gate_summary` 和追加 `trace.jsonl`。
  - CLI、Dashboard server、agent/file queue 都调用这个函数，避免多套真相源。

验收测试：

- `test_research_brief_requires_source_cards_for_method_families`
- `test_factor_lab_missing_blocks_research_pass`
- `test_gate_state_writers_go_through_single_function`
- `test_project_gate_update_writes_project_yaml_and_trace`

### Wave 5.3：真正新增

目标：补上这次策略试验暴露的真实缺口。

修改：

- Random search：
  - 新增 `open_composer/research/optimizers/random_search.py`。
  - `parameter-sweep` 增加 `--search-strategy random|grid`。
  - 默认改为 `random`，小空间或显式 `--search-strategy grid` 才用 grid。
  - random 必须记录 seed、sampled params、budget、rejection_reason。
  - Optuna、LHS 暂不做；NSGA-II 仅列为 router 专用 Phase 2 扩展。
- Trial ledger 扩展：
  - 在 `TrialRecord` 中增加或允许记录 `optimizer_type`、`seed`、`generation_or_iteration`、`train_window`、`validation_window`、`pruned`、`rejection_reason`。
  - 保持向后兼容，不破坏旧 ledger。
- Universe audit：
  - 新增 `open_composer/research/universe_audit.py`。
  - 新增 CLI：

```bash
uv run oc strategy universe-audit <spec>
```

  - artifact：

```text
reports/research/{strategy}-universe-audit.json
reports/research/{strategy}-universe-audit.md
```

  - 只聚焦 capability registry 不处理的三件事：PIT universe、current-symbol bias、survivorship bias。
  - 多股票扫描策略缺 universe audit 时不能 `research_pass=true`。
- PBO / DSR proxy：
  - 新增 `open_composer/research/pbo.py`。
  - 当 trial count > 100 或 search budget > 100 时，promotion 自动触发。
  - 输出 `reports/research/{strategy}-overfit-risk.json`。
  - 若 PBO/DSR proxy 指示高风险，报告必须降级为 research-only，除非 walk-forward 和 OOS 明确支持。
- LLM prompt/version stability：
  - 复用已有 `_llm_marginal_lift_checks`。
  - 新增 prompt/version stability check，作为后续 Dashboard Edit Prompt 工作流的副产品。

验收测试：

- `test_random_search_respects_candidate_budget_and_seed`
- `test_trial_ledger_records_optimizer_metadata`
- `test_universe_audit_flags_current_symbol_universe`
- `test_pbo_proxy_triggers_for_large_trial_count`
- `test_llm_prompt_version_stability_warning`

## 7. Step 6 可选项

以下不进入 Step 5 必做范围：

- Optuna TPE：仅当参数维度高、连续空间复杂、random search 明显不足时再接入。
- LHS / Sobol：候选数小于 100 时收益有限，暂不做默认。
- NSGA-II：仅对 router 策略的结构选择 + 多目标 Pareto front 有意义，作为 router 专用扩展。
- 强制多 agent specialist roles：保留 skill 和 handoff packet 作为最佳实践，不做单进程强制角色机制。
- 新建 `gate-state.json` 或 `research_state.json`：不做，避免与 `project.yaml.gate_summary` 三套并列。

## 8. 修订后要删除或降级的原计划内容

必须从旧思路中删除或降级：

- 删除“22 个 Research Brief 字段全部必填”的设想，改为 7 个硬字段加自动生成/选填字段。
- 删除“新建 gate-state.json + research_state.json”的设想，改为单一 `update_gate_state()`。
- 删除“random / LHS / Optuna / NSGA-II 全部 Step 5 实现”的设想，Step 5 只做 random，NSGA-II router 专用后置。
- 删除“P10 多 agent 强制角色分工”的必做定位，改为可选最佳实践。
- 删除“Factor Lab 13 个指标全部硬卡简单策略”的设想，改为 baseline / research_pass / paper_ready 分级。
- 明确 LLM contribution 基础设施已存在；Step 5 只补 prompt/version stability，不重建 LLM Alpha 体系。

## 9. 专业标准建议

这些标准不是固定收益承诺，而是产品默认审查标准。具体策略可在 research brief 中调整，但必须说明理由。

- 先验证可解释 alpha，再追求高收益。
- 优先控制 survivorship bias、lookahead、multiple testing 和 execution fantasy。
- 优化目标必须多目标：收益、回撤、Sharpe/Sortino、换手、成本、稳定性、OOS 衰减、benchmark superiority。
- leveraged ETF 策略必须明确 path dependency 和极端回撤风险。
- 高收益策略如果 drawdown、OOS、walk-forward 或数据质量不过关，只能 research-only。
- 不以“超过 TQQQ”作为唯一目标；如果目标是超过 TQQQ，必须同时说明可接受的回撤、波动、换手、成本和失效条件。
- 每次策略研究都应有明确 stop rule：何时停止这条路线，而不是无限调参。

## 10. Review 任务说明

请其他 agent 审查时重点看：

1. Step 5 是否足够小，是否优先做接线和硬门禁，而不是重建系统？
2. Research brief 的 7 个硬字段是否足够阻止“先大网格、后补理论”？
3. `spec_hash` 绑定和 budget abort 是否能防止旧 brief 配新 spec、以及 trial 数失控？
4. `update_gate_state()` 是否比新增 artifact 更稳？是否会遗漏 Dashboard 或 CLI 写入点？
5. Random search 默认是否会破坏现有小规模 grid 工作流？
6. Universe audit 是否聚焦 PIT/current-symbol/survivorship，避免和 capability registry 重复？
7. PBO/DSR proxy 的触发阈值是否合理？
8. Factor Lab 分级是否既能阻止无因子证据的组合策略，又不阻塞简单策略起步？
9. LLM prompt/version stability 是否应进入 Step 5.3，还是等 Dashboard Edit Prompt 再做？
10. 哪些测试必须先写，才能防止下一次 agent 绕过流程？

审查输出应包含：

- blocking issues
- non-blocking issues
- existing components that were missed
- missing modules/functions/tests
- suggested smaller implementation order
- parts of this plan that should be removed or delayed

## 11. 完成定义

Step 5 完成后，应满足：

- 新策略优化请求不能绕过 valid research brief。
- Research brief 与当前 spec hash 绑定。
- 每个可调参数策略都有 bounded search space 和 search budget。
- 大规模 grid search 默认被阻止，超过 64 候选必须有 large-search justification。
- `parameter-sweep` 预算超限会 abort，而不是只 warning。
- Optimizer 输出被视为候选发现，不是最终策略证明。
- 每个候选都有 trial ledger、benchmark family、OOS、walk-forward、forensics 和 rejection reason。
- 新因子进入组合策略前必须有分级 factor lab 或明确 research-only 标记。
- 多股票扫描策略必须有 universe audit，至少说明 PIT/current-symbol/survivorship 风险。
- LLM 影响交易必须有 PIT packets、边际贡献证据，并补 prompt/version stability 检查。
- Dashboard、CLI、Codex、Claude Code 都通过同一个 `update_gate_state()` 写 gate summary 和 trace。
- 模拟盘接入只在 paper readiness 通过后可见。
- no-context agent 可以从 README、本文、project gate summary 和 reports artifacts 判断下一步，不依赖聊天历史。

Step 5 每个 wave 完成后必须运行：

```bash
uv run ruff format .
uv run ruff check .
uv run pytest
uv run oc repo check --strict
```

如果涉及 Dashboard：

```bash
npm --prefix dashboard run build
make verify
```
