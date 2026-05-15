# 7 小时任务复盘：LLM 量化研究链路与 Open Composer 产品不足

日期：2026-05-14

## 结论摘要

这次任务完成了一个可运行、可验证的研究工作流，但也暴露出一个关键产品问题：系统可以比较稳地跑出“防泄漏、可审计、带样本外指标”的量化候选，却还不能稳定地产出“LLM 深度参与并产生独立贡献”的策略。纯量化策略和 LLM 混合策略最终指标完全一样，不是偶然，而是因为它们共享同一套 `AAOI` 15m 数据、同一个 OOS 区间、同一类动态暴露切换规则，并且最终信号路径几乎相同。

更严格地说，当前 LLM 路径证明的是“LLM/Codex 可以在看不到最终 OOS 的情况下参与候选选择”，而不是“LLM 创造了新因子、新 regime 判断、新信息处理能力或新的交易 Alpha”。因此，之前的完成审计中把 LLM 混合策略标为通过，是对“流程完整性”的通过，不应被解读为“LLM Alpha 已被证明”。

这份报告的核心建议是：Open Composer 必须把 LLM 的作用从“候选参数选择器”提升为“研究假设、因子结构、语义事件特征、风险反证和策略复盘”的结构化参与者。同时，产品必须把参数扫描、候选多样性、反过拟合、运行耗时、数据新鲜度、LLM 调用状态、信号差异度做成一等产物，而不是靠 Codex 在最后人工解释。

## 本报告依据

本地证据：

- `reports/research/optical-ai-strategy-iteration-2026-05-14.md`
- `reports/research/optical-ai-strategy-completion-audit-2026-05-14.md`
- `reports/research/optical_ai_pure_quant_rotation_15m-exposure-switch-research.json`
- `reports/research/optical_ai_pure_quant_rotation_15m-llm-exposure-switch.json`
- `reports/research/optical_ai_pure_quant_rotation_15m-llm-exposure-switch-prompt.json`
- `open_composer/research/exposure_switch.py`
- `open_composer/research/llm_exposure_switch.py`
- `tests/test_exposure_switch_research.py`
- `tests/test_llm_exposure_switch_research.py`

外部调研依据：

- OpenAI Codex 文档建议把重复工作模式沉淀到 `AGENTS.md`，并让 Codex 通过运行测试、lint、扫描器形成工具闭环：<https://developers.openai.com/codex/learn/best-practices#make-guidance-reusable-with-agentsmd>
- OpenAI `AGENTS.md` 文档说明 Codex 会按全局、项目、子目录层级加载指令，适合把产品级研究规则固化成可复用约束：<https://developers.openai.com/codex/guides/agents-md>
- OpenAI AI-native engineering 文档把 agent 的价值定位为覆盖计划、设计、构建、测试、评审、文档和维护，而不是只生成代码片段：<https://developers.openai.com/codex/guides/build-ai-native-engineering-team>
- OpenAI reasoning model 文档强调 Responses API、structured outputs、tool calling、prompt caching、state management 和 compaction 对 agentic workflow 的可靠性、延迟和成本很关键：<https://developers.openai.com/api/docs/guides/latest-model.md#using-reasoning-models>
- Bailey、Borwein、Lopez de Prado、Zhu 的 PBO 论文指出，普通 holdout 在投资回测场景中不可靠，并提出 CSCV/PBO 来估计回测过拟合概率：<https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253>
- Bailey、Lopez de Prado 的 Deflated Sharpe Ratio 论文指出，大量试参和只报告正结果会带来选择偏差，DSR 用于修正多重测试和非正态收益下的 Sharpe 膨胀：<https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551>
- scikit-learn `TimeSeriesSplit` 文档确认时间序列交叉验证不能训练未来、测试过去，并支持通过 `gap` 排除训练集末端样本：<https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html>
- TradingAgents 论文展示了 LLM 在金融交易中更自然的角色是多 agent 分工、基本面/情绪/技术/风控协作，而不是只选一个参数：<https://arxiv.org/abs/2412.20138>
- 一篇关于 LLM 执行金融交易指令的研究显示，LLM 生成率高不等于执行准确和完整，金融交易系统必须用结构化输出、校验和安全边界约束模型：<https://arxiv.org/abs/2412.04856>

## 一、7 小时工作路径复盘

### 1. 起点：用户目标是产品级审查，不只是跑策略

原始目标包含几层要求：

- 审查本地项目和 GitHub 最新版本。
- 先调研适合 Codex 的审查方式。
- 审查 README 是否能同时服务用户和 Codex。
- 检查部署、Dashboard、数据源和环境。
- 针对美股光通信领域制定两类策略：纯量化策略、大模型结合策略。
- 策略要比较直接买入收益，尽可能发掘 Alpha。
- 必须防止未来函数、过拟合、单点参数调参陷阱。
- 让 Codex 在迭代时关注方法、数据和因子，而不是被参数数值束缚。

这是一个混合任务：产品审查、代码修复、文档优化、环境验证、数据接入、量化研究、LLM 工作流设计、Dashboard 部署和最终复盘都混在一起。Codex 的优势是可以跨文件、跨命令、跨报告推进；不足是如果产品没有把每一步抽象成明确 gate，就容易在长期任务中把“完成了一个可跑流程”误认为“完成了业务本质目标”。

### 2. 中段：产品能力是在任务中被补齐的

本次任务不是单纯使用已有产品，而是一边审查一边补了多个关键能力。已知新增或强化的部分包括：

- `repo check`：把 README、AGENTS、技能、能力注册、Dashboard、paper 边界等做成仓库级检查。
- Alpaca cache window filtering：让缓存数据按请求区间过滤，避免有缓存时强制走 live fetch。
- `primary-alpha` 或直接基准 Alpha 目标：避免只和等权行业篮子比，忽略用户要求的“直接买入收益”。
- 研究命令加入 `--start` / `--end`：支持明确 current-year / last-three-month window。
- anchored rotation、same-symbol market timing、dynamic exposure switch：在发现轮动和普通择时打不过 `AAOI` 后补入更贴合目标的研究族。
- `acceptance_gate`：把 OOS Alpha、Sharpe、drawdown、walk-forward、quality flags 写入 JSON/Markdown。
- `llm-exposure-switch`：保存 prompt artifact，隐藏最终 OOS/full-window，只让 LLM/本地 Codex 基于训练和验证证据选候选。
- fallback 状态记录：`fallback_api_error`、`codex_local_choice`、`external_api_called` 进入报告。
- README 增加 Codex 控制面说明：不让 Codex 只返回一套固定参数，而是输出参数范围、批量 sweep、再方法层迭代。
- 测试补充：新增 exposure switch、LLM exposure switch、repo check、dashboard catalog、readiness 等测试。

这说明产品底座已经具备可扩展性，但也说明许多关键 guardrail 不是最初就成熟存在，而是在用户要求和实际踩坑中补上的。

### 3. 后段：策略结果通过了流程 gate，但暴露了 LLM 贡献不足

最终纯量化策略：

- 数据：Alpaca IEX cache，`AAOI` 15m，约 2026-02-13 到 2026-05-12。
- 方法：动态暴露切换。
- OOS return：`30.65%`
- 直接 `AAOI` buy-hold：`22.21%`
- OOS Alpha：`8.44%`
- OOS Sharpe：`2.75`
- walk-forward positive Alpha folds：`3/3`
- gate：`passed=true`

最终 LLM 混合策略：

- 同一数据和 OOS 窗口。
- 同一类动态暴露切换。
- 状态：`codex_local_choice`
- `external_api_called=false`
- OOS return：`30.65%`
- 直接 `AAOI` buy-hold：`22.21%`
- OOS Alpha：`8.44%`
- OOS Sharpe：`2.75`
- visible validation positive Alpha folds：`3/3`
- gate：`passed=true`

两者指标一致的原因不是“LLM 找到了相同最优 Alpha”，而是最终暴露路径没有实质差异。LLM 版本多了 `max_volatility_pct=6.0`，纯量化版本为 `null`，但在该数据路径下这个过滤条件没有改变实际交易结果。

因此，完成审计应该被修正为：

- 纯量化研究候选：通过当前研究 gate。
- LLM 混合研究候选：通过防泄漏候选选择 workflow gate。
- LLM Alpha 证明：未通过或未充分证明。
- 外部 LLM API 真实参与：未通过，因为本次环境没有成功调用外部模型。

## 二、产品不足与复盘

### 1. LLM 参与层级过浅

当前 `llm-exposure-switch` 的核心设计是：

1. 生成同一类动态暴露候选。
2. 计算训练、内部验证和 prior validation folds。
3. 把候选摘要写入 prompt artifact。
4. LLM 或本地 Codex 选择一个候选。
5. 选择后再计算 hidden OOS/full-window。

这个设计防泄漏是正确的，但 LLM 的作用太窄。它没有：

- 生成新的可解释因子。
- 读取新闻、财报、行业事件、供应链信息并生成 point-in-time 特征。
- 判断光通信行业 regime。
- 提出不同策略族之间的结构性选择。
- 设计风险反证或失败场景。
- 解释为什么某个 Alpha 是行业结构、beta、杠杆暴露、流动性或事件驱动导致的。
- 对纯量化策略做实质性 ablation。

结果就是 LLM 被压缩成“候选排序器”，而不是“研究合作者”。这限制了大模型的最大优势。

### 2. 策略族差异没有被产品显式检查

产品现在能报告单个策略的 OOS Alpha、Sharpe 和 quality flags，但没有把“两个策略是否真的不同”作为 gate。

应该新增 `strategy_distinctiveness` 检查：

- exposure path correlation
- signal timestamp overlap
- selected symbol overlap
- position size overlap
- factor family overlap
- OOS trade overlap
- return attribution overlap
- strategy lineage overlap

如果 LLM 版本和纯量化版本的信号相同或高度相关，报告必须自动降级为：

> LLM-assisted selection, no independent LLM signal contribution demonstrated.

这类降级不应该依赖用户追问后人工解释。

### 3. 回测和研究运行等待过长

我用当前 96 个候选、3 个 walk-forward folds 的 exposure switch 命令做了一次计时。命令使用本地 cache，未重新做网络数据抓取。结果：

- candidate count：`96`
- walk-forward folds：`3`
- elapsed：`251.18s`
- 约 `4.19` 分钟

这说明等待回测确实是体验瓶颈。根因在当前实现：

- 每个候选重复构造 EMA、momentum、volatility、drawdown 等指标。
- 每个候选重复跑 train、OOS、full-window。
- walk-forward 每个 fold 重新评估全部候选。
- LLM reviewed candidates 又重复计算 train/validation/folds。
- 没有 job progress、resume、cache key、parallel worker、top-N 延迟计算。
- 报告写入没有记录每个阶段耗时，用户看不到卡在哪里。

粗略复杂度不是 `candidates`，而接近：

```text
候选数 * (train + OOS + full + folds 内部验证) * 每次指标构造成本
```

当候选从 96 增加到几百、数据从单一 `AAOI` 扩到行业 universe、多 timeframe、多数据源对照时，等待会迅速放大。

### 4. 数据新鲜度和数据质量仍是核心弱点

本次任务的数据事实：

- `AAOI` 15m Alpaca IEX cache 最新 bar 是 `2026-05-12T19:45:00+00:00`。
- 对 `2026-05-13` 到 `2026-05-14` 的 strict live fetch 返回 `0` bars。
- 当前结果基于 IEX，不是 SIP。
- 期权链 probe 对多个光通信标的返回零 snapshots，不能支撑真实期权 overlay 证据。

产品已经记录 provenance，但 Dashboard 和报告还需要更强地把这些状态显示为风险：

- data as-of
- feed type
- strict-live success/failure
- cache fallback
- missing sessions
- bar count per symbol
- OOS 是否覆盖最近交易日
- 数据供应商差异

否则用户很容易把“研究结果”误读成“最新市场结果”。

### 5. 完成标准和研究标准还不够分层

当前有多个层级混在一起：

- 命令能跑。
- 测试通过。
- 报告写出。
- OOS Alpha 正。
- walk-forward 正。
- Dashboard 能看。
- LLM prompt 防泄漏。
- LLM 真的产生新信息。
- 策略适合 paper。

这几件事的强度完全不同。产品应该把 gate 分成：

- `workflow_ok`：命令、报告、schema、测试通过。
- `data_ok`：数据新鲜度、bar count、provenance、缺失检测通过。
- `research_ok`：OOS、walk-forward、成本、基准、quality flags 通过。
- `anti_overfit_ok`：trial count、PBO/DSR、参数稳定性、候选多样性通过。
- `llm_contribution_ok`：LLM 有真实调用或明确本地 Codex路径；有结构性贡献；信号和纯量化不同；有 ablation。
- `paper_candidate_ok`：paper readiness、spec lifecycle、broker gate、监控和风险限制通过。

本次 LLM 策略最多是 `workflow_ok + research_ok`，不应自动得到 `llm_contribution_ok`。

### 6. Dashboard 还没有成为研究驾驶舱

Dashboard 目前能作为可视入口和部署检查，但还不足以承担量化研究驾驶舱。用户最需要一眼看到：

- 哪些策略是真实通过，哪些只是 workflow evidence。
- LLM 是否真实调用，调用了哪个模型，是否 fallback。
- 是否看到 hidden OOS。
- 策略和 buy-hold 的差异。
- 策略和另一个策略的信号差异。
- 当前数据是否 stale。
- 当前候选是否过拟合风险高。
- 当前耗时瓶颈在哪里。
- 下一轮应该方法层迭代还是参数层扩展。

当前这些信息分散在 JSON、Markdown、命令输出和聊天解释里。

## 三、交互与优势发挥

### 1. 人和 Codex 的最佳分工

用户最应该掌握：

- 业务目标：例如“今年或近三个月、光通信、低中频、相对直接买入有 Alpha”。
- 约束优先级：收益、回撤、换手、融资成本、数据源可信度、是否允许杠杆。
- 可信外部资源：例如第三方 `OPENAI_BASE_URL` 是否允许发送项目上下文。
- 判断策略是否符合真实预期：例如 LLM 混合策略是否必须体现语义信息。
- 接受或拒绝下一轮研究方向：继续扩展方法，还是先修产品结构。

Codex 最应该承担：

- 审查代码、README、AGENTS、skills、capabilities 和报告一致性。
- 把自然语言目标转成 `StrategySpec`、参数范围、factor alternatives。
- 批量运行 sweep、walk-forward、promotion-report。
- 自动检查未来函数、数据 provenance、quality flags。
- 生成报告、Dashboard 数据、测试和文档。
- 在用户追问时追溯事实，不为结果辩护。

LLM 最应该承担：

- 研究假设生成：为什么光通信板块可能有动量、事件、订单、供应链、AI capex、earnings surprise、short interest、流动性挤压等因子。
- 因子结构设计：把自然语言 insight 变成 point-in-time features。
- regime 标注：行业风险开关、财报窗口、政策/订单/产能周期。
- 反证：解释为什么一个高收益候选可能只是 `AAOI` 单票 beta 或杠杆结果。
- 失败复盘：看所有候选失败原因，建议下一轮方法层修改。
- 报告生成：把证据转成结构化、可审计、用户可读的结论。

### 2. LLM 不应该被要求“直接给一个策略结果”

用户指出的担心是准确的：如果 prompt 是“帮我生成一个策略”，模型很容易返回一套方法和一组参数。下一轮优化又围绕这组参数微调，导致研究视野越来越窄。

更好的协议是让 LLM 输出：

```yaml
research_hypothesis:
  claim: ...
  economic_reason: ...
  target_symbols: [...]
  expected_failure_modes: [...]
factor_families:
  - name: ...
    point_in_time_inputs: [...]
    leakage_risks: [...]
method_alternatives:
  - name: ...
    when_it_should_work: ...
    when_it_should_fail: ...
parameter_ranges:
  - field: ...
    values: [...]
hard_constraints:
  - ...
evaluation_plan:
  train: ...
  validation: ...
  hidden_oos: ...
  anti_overfit: ...
```

也就是说，LLM 输出研究空间，工具负责穷举、并行、回测、校验。下一轮再让 LLM 看失败分布和反证证据，决定换因子、换数据、换方法，而不是继续追一个参数。

### 3. Codex 的优势应该进入产品主链路

Codex 的优势不是只“会写代码”，而是能在同一上下文里读代码、改代码、跑命令、解释结果、更新文档、补测试。产品应该把这个优势制度化：

- 每次策略研究都生成 `research_manifest.json`。
- manifest 记录目标、数据、候选空间、trial count、命令、耗时、模型调用、失败原因。
- Codex 每轮必须先读 manifest，再决定下一步。
- Codex 不能只输出自然语言策略，必须落地到 spec、feature packet schema、sweep config、report。
- Codex 的每次方法层变更要写 `hypothesis_ledger`，记录为什么变更、预期改善什么、如何反证。
- Codex 的每次参数层变更要写 `search_space_delta`，记录新增范围是否扩大过拟合风险。

这样 Codex 会从“临时执行者”变成“产品内的研究操作系统”。

## 四、策略生成与迭代：如何更好发挥优势

### 1. 推荐的新策略研究主流程

建议把策略研究固定为 12 步：

1. `ResearchBrief`：用户目标、标的池、周期、基准、风险限制、数据源、禁止项。
2. `CapabilityEvaluation`：检查价格、新闻、事件、宏观、财报、期权等能力是否真实可用。
3. `HypothesisPortfolio`：LLM 生成多个经济假设和失败条件。
4. `FeaturePlan`：每个假设对应 point-in-time 特征、数据源和泄漏风险。
5. `StrategySpecDraft`：Codex 生成一个或多个 draft specs。
6. `SearchSpaceSpec`：LLM/Codex 输出参数范围和方法 alternatives，而不是单点参数。
7. `BatchBacktest`：产品批量跑候选，记录所有候选，不只记录赢家。
8. `AntiLeakageCheck`：自动检查 bar lag、published_at、数据窗口和 OOS 隐藏。
9. `AntiOverfitCheck`：trial count、walk-forward、PBO/DSR、参数稳定性、成本敏感性。
10. `LLMCritique`：LLM 基于训练和验证证据做结构性复盘，不看 hidden OOS。
11. `HiddenOOSUnlock`：选择后才计算最终 OOS，并自动生成通过/失败原因。
12. `DecisionReport`：输出用户可读结论、Dashboard 卡片、下一轮研究建议。

### 2. LLM 混合策略的最低通过标准

以后只要声称“LLM 混合策略”，至少要满足：

- `external_api_called=true`，或明确标为 `local_codex_research`，不能混称。
- LLM 输入只包含 point-in-time 可见信息。
- prompt artifact、response artifact、schema validation 全部保存。
- LLM 输出不只是 label，而是因子、假设、风险、参数范围或 regime。
- 最终信号和纯量化基线有可测差异。
- 有 ablation：移除 LLM 特征后收益、Sharpe、回撤或风险识别发生变化。
- 有 `llm_contribution_summary`：
  - LLM 新增了什么信息？
  - 改变了哪些交易？
  - 哪些收益来自这些改变？
  - 哪些风险被降低或增加？
- 如果 LLM 只选择了和纯量化相同的候选，gate 必须显示：
  - `llm_contribution_ok=false`
  - `reason=same_signal_path_as_quant_baseline`

### 3. 防止过拟合的产品机制

量化产品不能只靠“我提醒自己不要过拟合”。必须落成机制：

- 记录所有 trial，不只记录 top candidates。
- 报告 candidate count、family count、parameter dimensions。
- 对每个策略族估计 PBO 或至少输出 PBO proxy。
- 对 Sharpe 使用 DSR 或至少报告 multiple-testing adjusted warning。
- OOS 只能解锁一次；如果反复看 OOS 后继续调参，应生成新 holdout 或降级证据强度。
- walk-forward fold 需要带 gap/embargo，尤其是事件特征或 overlapping labels。
- 报告参数稳定性：相邻参数是否也有效，还是只有一个孤点最优。
- 报告失败候选分布：如果 96 个候选只有 1 个有效，风险比 40 个稳健有效要高。
- 成本敏感性必须覆盖 slippage、commission、financing、borrow/short cost。
- 数据源对照必须覆盖至少 cache/live 或 Alpaca/Longbridge/SIP 之一。

### 4. 未来函数和信息泄漏控制

本次 exposure switch 已经做到“前一根 bar close 指标决定当前 bar open 暴露”，这是正确方向。但产品还需要统一检查：

- 所有 rolling/EMA/突破位是否在执行前 lag。
- 财报、新闻、SEC、宏观数据是否有 `published_at` 和可交易时点。
- 盘后数据是否被错误用于盘中交易。
- vendor 修正数据是否回写历史。
- 同一事件多次出现在 train 和 test 是否需要 embargo。
- LLM feature packet 是否记录 input hash、prompt hash、model、timestamp。
- 任何 LLM 输出都不能在回测循环中动态读取未来上下文。

### 5. 性能优化建议

短期优化：

- 在报告里记录每个阶段耗时：fetch、indicator、candidate_eval、walk_forward、write_report。
- 加 `--top-n-oos`：先用训练/验证筛 top N，再对 top N 算 full-window 和更贵的 diagnostics。
- 预计算指标矩阵：同一 `fast/slow/momentum/volatility/drawdown` 不应每个候选重复算。
- 缓存 returns、open-to-open returns、buy-hold curve。
- 对候选评估做 multiprocessing 或 joblib parallel。
- LLM reviewed candidates 复用 exposure switch 的中间结果，不重复评估。
- Dashboard 显示 job progress 和 ETA。

中期优化：

- 建立 `research_runs/` artifact store，用参数 hash 做增量复用。
- 把 candidate evaluation 改成可恢复 job queue。
- 对大 universe 使用分层搜索：先粗筛方法和标的，再细扫参数。
- 对重复报告生成使用 stable JSON + diff，避免无意义重写。
- 对长任务支持 checkpoint/resume，Codex 中断后继续而不是重跑。

长期优化：

- 把 deterministic Python engine 保留为参考实现。
- 对事件驱动路径迁移到 NautilusTrader，避免重复造执行引擎。
- 对向量化研究路径考虑专门 research backend，但必须和 deterministic engine 做 parity test。
- 引入策略相似度、归因和 ablation 作为核心分析层。

## 五、产品改进路线

### P0：必须尽快修正的真实性问题

1. 增加 `llm_contribution_ok` gate。
2. 增加 `strategy_distinctiveness` 报告。
3. LLM fallback 不允许被展示成“LLM 策略通过”，只能展示成“本地 Codex 选择 workflow”。
4. Dashboard 展示 `external_api_called`、`llm_status`、`hidden_oos_policy`。
5. 报告显示数据 as-of、feed、strict-live 结果和 cache fallback。
6. 完成审计模板拆分 workflow pass、research pass、LLM contribution pass、paper readiness pass。

### P1：释放 Codex/LLM 研究能力

1. 新增 `ResearchBrief` 和 `HypothesisPortfolio` schema。
2. 新增 `SearchSpaceSpec`，强制 LLM 输出参数范围和方法 alternatives。
3. 新增 `HypothesisLedger`，记录每轮方法层改变和反证。
4. LLM 输出必须用 structured outputs 验证，不靠自由文本解析。
5. Codex 每轮自动生成失败复盘，不只总结赢家。
6. README 和 AGENTS 加入“LLM 混合策略最低通过标准”。

### P1：降低等待成本

1. 研究命令增加阶段耗时日志。
2. 加 candidate cache 和参数 hash。
3. 先 train/validation 筛 top N，再算贵的 OOS/full diagnostics。
4. 并行候选评估。
5. Dashboard 增加 progress、ETA、已完成候选、当前 fold。

### P2：增强专业金融能力

1. 引入 PBO/DSR 或等价 overfit risk score。
2. 增加 purged/embargoed time-series CV。
3. 增加数据源对照和 stale data hard gate。
4. 加事件/news/macro feature packet replay 的真实样例。
5. 对 optical/AI 通信行业建立行业知识库：订单、capex、客户集中度、short interest、earnings window、同业传导。
6. 期权能力在真实链数据可用前只能标为 workflow test，不能作为 Alpha 证据。

## 六、对本次结果的修正评价

纯量化策略：

- 当前可以作为 research candidate。
- 它的 Alpha 是动态暴露和杠杆时机相对 unlevered `AAOI` buy-hold 的 Alpha。
- 它不是 sector stock-selection Alpha。
- 样本短、标的波动大、数据截至 2026-05-12，应继续保持 research evidence，不应进入 paper。

LLM 混合策略：

- 当前只能称为 LLM-assisted / Codex-assisted meta-selection workflow。
- 它没有证明真实外部 LLM API 参与。
- 它没有证明 LLM 产生独立信号或新增因子。
- 它和纯量化策略结果相同，应自动触发 distinctiveness warning。
- 完成审计中 `passed=true` 应解释为防泄漏选择流程和 OOS gate 通过，而不是 LLM Alpha 通过。

产品状态：

- 工程底座比任务开始时更完整。
- README、AGENTS、skills、capability registry、tests、readiness、Dashboard 的控制面已经能支撑 Codex 工作。
- 最大不足不是“跑不起来”，而是“没有把 LLM 贡献和策略真实性做成硬约束”。

## 七、建议写入 AGENTS.md / README 的新规则

建议新增以下规则：

```md
## LLM Strategy Rules

- Do not call a strategy "LLM-combined" only because an LLM selected one candidate from a grid.
- A valid LLM-combined strategy must include a saved prompt artifact, response artifact, schema-valid output, point-in-time inputs, and a measurable signal or factor difference versus the pure-quant baseline.
- If `external_api_called=false`, label the result as local Codex-assisted workflow evidence, not external LLM evidence.
- Always compute strategy distinctiveness versus the closest pure-quant baseline.
- If exposure path, signal timestamps, and returns are identical, set `llm_contribution_ok=false`.

## Research Iteration Rules

- Codex must output parameter ranges and method alternatives, not a single fixed parameter set.
- Batch tools own parameter search; Codex owns hypothesis generation, failure analysis, and method-level iteration.
- Every research run must record trial count, candidate count, data as-of, runtime, OOS policy, walk-forward folds, and anti-overfit flags.
- Do not unlock hidden OOS before the candidate selection decision is fixed.
- If OOS has been inspected and the method changes afterward, mark the evidence as contaminated or create a new holdout.
```

## 八、最终判断

这 7 小时最有价值的成果不是那两个策略的收益数字，而是暴露了产品下一阶段真正该解决的问题：

- Open Composer 已经能让 Codex 把一个复杂量化研究目标拆成命令、代码、报告、测试和部署。
- 但它还没有充分释放 LLM 的研究优势，尤其没有让 LLM 在假设、因子、语义信息、风险反证和方法层迭代中成为一等参与者。
- 它还需要用产品机制防止“流程通过”被误读成“经济结论成立”。
- 它还需要把策略差异、LLM 贡献、过拟合概率、数据新鲜度和运行耗时做成 Dashboard 和报告里的核心字段。

下一阶段不应该先继续追求更高收益，而应该先把这些 gate 和报告结构补齐。否则产品会很容易产出看似漂亮、实则只是同一信号路径变体的策略结果。

## 九、本轮继续验证记录

继续接手后，对本文档中的结论做了三类核对：

- OpenAI Codex 官方文档确认：`AGENTS.md` 适合承载可复用仓库规则，Codex 工作流应包含测试、lint、行为确认和 diff review；reasoning model 工作流应优先使用结构化输出、tool calling、state/compaction 和 prompt caching。
- 量化研究外部依据确认：PBO/CSCV、Deflated Sharpe Ratio、TimeSeriesSplit gap、LLM 多 agent 金融研究和 LLM 交易指令执行准确性问题，均支持本文对“防过拟合、结构化输出、LLM 不应只选参数”的判断。
- 仓库规则核对：`AGENTS.md` 和 `README.md` 已经写入参数范围、方法/factor alternatives、workflow/research/llm/paper 分层、LLM fallback 降级、strategy distinctiveness 和 PIT feature packet 要求。

同时补齐了上一轮留下的一个悬空运行产物：`strategy_specs/drafts/optical_storage_intraday_llm_feature_rotation_30m.yaml` 引用的 `feature_logs/optical_storage_local_codex_theme_2026q2.jsonl` 不存在。已新增一个最小的 `local_codex_research` point-in-time replay packet，包含 `AAOI`、`MU`、`CIEN` 三个标的的静态主题分数，`visible_at` 均设在研究窗口起点，避免把当前知识注入历史 bar。该 packet 只证明本地 Codex feature replay workflow 完整，不是外部 LLM API Alpha 证据。

本轮验证结果：

```bash
env UV_CACHE_DIR=/tmp/uv-cache-spec uv run oc spec validate strategy_specs/drafts/optical_storage_intraday_llm_feature_rotation_30m.yaml
env UV_CACHE_DIR=/tmp/uv-cache-spec2 uv run oc spec validate strategy_specs/drafts/optical_storage_intraday_quant_15m.yaml
env UV_CACHE_DIR=/tmp/uv-cache-feature uv run oc feature validate --output reports/features/validation.json
env UV_CACHE_DIR=/tmp/uv-cache-repo uv run oc repo check
env UV_CACHE_DIR=/tmp/uv-cache-pytest uv run pytest tests/test_feature_validation.py tests/test_spec_validation.py tests/test_repo_check.py
```

结果：

- 两个 optical/storage draft spec 均通过 `oc spec validate`。
- `oc feature validate` 写出 `reports/features/validation.json`、`validation.md` 和 `manifest.json`；所有 feature packets 状态为 `complete`。
- `oc repo check` 状态为 `ok` / `ready=yes`。
- 相关测试 `19 passed in 5.32s`。
