# Open Composer 策略优化目标与进展日志

文档版本：`1.0`  
当前快照时间：`2026-08-24T16:28:29Z`  
当前执行状态：`已暂停`  
最终目标状态：`未完成`  
当前 campaign：`mom_independent_mechanisms_qd_r2`

本文件是当前策略优化工作的统一状态入口，用于记录用户目标、固定研究方法、验收门槛、
累计工作量、历史工作摘要、当前结果和下一步停止/转向规则。详细历史过程保留在原始
日志、合同和评估报告中，本文件通过链接引用，不复制或改写已经封存的证据。

本文件不是策略晋级、模拟盘启动或券商写入授权。任何旧文档中的旧门槛与本文件冲突时，
以当前 `AGENTS.md`、当前 campaign 合同和进展汇报模板为准。

## 1. 用户要求与最终目标

### 1.1 产品与研究能力

- 充分理解 Open Composer 的产品结构、主要功能、代码和研究工作流。
- 以 `StrategySpec` 作为策略行为的唯一事实来源。
- 充分使用知识索引、source cards、经验记忆、模型记忆、注册因子库、Factor Lab 和
  `capabilities/registry.yaml`，而不是绕过产品能力另建不可审计流程。
- 每个新信息模态必须先完成能力评估；样例、fixture、缓存回退和 research-only 数据
  不能被描述为 paper-ready 证据。

### 1.2 策略发现与优化方法

- 采用广度优先、树状的策略探索：先测试经济机制彼此独立的方向，再分别做有限优化。
- 不用遗传变异或大量相近参数制造虚假探索宽度，不在已经失败或暴露的参数邻域反复调参。
- 每个 campaign 和子迭代必须在训练或回测前预注册假设、候选、数据、特征、成本、
  基准、折、回退、质量指标和累计试验暴露。
- 每轮开始前运行相应 campaign/iteration validation；验证不通过时不得训练、回测、
  晋级或修改 paper-stage 策略。
- development、frozen OOS、challenge 和 forward 分区严格隔离。失败分支封存后转向
  真正独立的经济假设，不读取 frozen OOS 后做补救调优。
- 提升实际优化效率：治理必须服务于防泄漏和可复核，但不能长期替代策略收益实验。

### 1.3 动量与股票池要求

- 不允许把当前热门行业、当前赢家或当前指数成分股固定回填到历史。
- 股票选择策略必须在每个历史决策日按当时可见的成员、永久证券身份、退市收益、
  公司行动和流动性重新构建合格股票池。
- 当前主题和静态成分股只能作为明确不可晋级的控制组。缺少 PIT 能力时必须
  `dependency_skipped`，不能用当前股票池替代。
- 必须承认不同年份的动量来源、领先行业和领先股票会变化；策略应验证跨时期机制，
  不能只围绕某一阶段的热点区域。

### 1.4 ML、LLM 与新模态要求

- 必须反思并用证据解释 ML 为什么没有超过普通确定性组合。
- 只有确定性分支先表现出信号后才允许增加 ML；ML 不是扩大试验数量的工具。
- ML 必须在相同数据、成本、时序折和回退条件下超过匹配确定性基线与 price-only ML，
  并通过校准、覆盖、精确回退、missing-modality、placebo 和成本后增量价值门。
- LLM/news/event/macro 输入必须是可重放的 PIT packet，包含 `visible_at`、
  `published_at`、`fetched_at`、来源、输入 hash 和 prompt/transform hash。
- 失败的模型、模态和消融必须作为负面记忆保留，不能在后续轮次无记录重试。

### 1.5 策略组与模拟盘边界

- 至少两个经济机制独立通过且收益相关性足够低后，才允许建立策略组组合迭代。
- 组合方法只测试少量透明方案，例如等权、逆波动和受限风险平价。
- 最终交付应达到“无需再等研究或实现工作，即可开始模拟盘测试”的状态。
- 本目标不包含实际启动、运行或等待模拟盘，也不包含真实资金写入。
- 当前 R2 不提交模拟盘或券商订单；任何历史 Paper 基础设施证据都不能替代当前策略
  的 Alpha、执行现实或 paper readiness 证据。

### 1.6 固定进展汇报要求

以后用户询问“现在进展怎样”“优化迭代怎么样了”“策略现在咋样了”或同义问题时，
必须按照[策略优化进展汇报模板](strategy-optimization-progress-report-template.zh.md)回答：

- 重新从当前产物统计轮次、候选、trial、模型、因子和知识规模。
- 区分目录数、manifest 轮次、候选数、ledger 原始行、去重行、跳过/无效行、实际承载、
  唯一模型 ID 和未落盘训练暴露，不能合并成一个含糊的“尝试次数”。
- 分开报告 `workflow_pass`、`research_pass`、`ml_contribution_pass`、
  `llm_contribution_pass` 和 `paper_ready_pass`。
- 当前轮没有 evaluation report 时，当前绩效必须为 `N/A`；旧结果只能作为历史基线。
- 必须报告时间、统计口径、当前轮增量、全部冻结门槛、ML 增量、知识/因子/数据体量、
  阻塞项和下一项可证伪动作。

## 2. 当前冻结验收口径

适用于首次冻结晚于 `2026-08-15` 的新可晋级候选。所有指标必须来自相同主成本、
连续、无终端清算的收益流；已锁定迭代不得事后修改门槛。

| 指标 | 当前门槛 |
|---|---:|
| 20 bps OOS 年化 Sharpe-excess-BIL | 严格 `>1.0` |
| 20 bps 净 CAGR | `>=45%` |
| 相对 QQQ CAGR 提升 | `>=8` 个百分点 |
| 匹配 TQQQ CAGR 捕获 | `>=85%` |
| TQQQ 上行捕获 | `>=0.85` |
| TQQQ 下行捕获 | `<=0.90` |
| 最大回撤 | `>=-65%` |
| MAR | `>=0.40` |
| 正向时序折 | `>=3/4` |
| DSR | `>=0.75` |
| PBO | `<=0.40` |
| SPA p-value | `<=0.05` |
| 成本压力 | 同时报 `10/20/40 bps`，40 bps 总收益严格 `>0` |
| 独立机制相关性 | 至少一对通过，绝对 Pearson 相关性 `<=0.70` |

研究流程通过或某一个局部指标通过不等于 Alpha、策略组完成或 paper readiness。

## 3. 产品研究链路理解

当前采用的产品原生链路为：

`StrategySpec -> capability evaluation -> knowledge build/scout/assess ->`
`campaign contract -> child dossier/manifest -> iteration validate ->`
`development evaluation -> QD archive/allocation ledger seal -> frozen OOS ->`
`backtest forensics -> execution reality/TCA -> risk and paper safety -> paper entry`

关键职责边界：

- `StrategySpec`：信号、参数、资产、执行、成本和回退的事实来源。
- 知识库：管理外部 claim、时效、负面实验和模型/数据记忆，不直接证明 Alpha。
- 因子库：提供注册定义、表达式和来源 lineage；因子数量不等于有效因子数量。
- capability registry：决定数据能否用于 workflow、research 或 paper，不允许 fixture 升格。
- campaign/iteration contracts：在看到结果前冻结候选和统计身份。
- trial/model/prediction/signal ledgers：记录真实试验、训练、预测、信号和审计关联。
- promotion 与 paper safety：只有完整研究证据通过后才处理执行现实和模拟盘入口。

## 4. 历史优化工作摘要

完整迭代产物位于[研究迭代目录](../reports/research/iterations/)，campaign 证据位于
[campaign 目录](../reports/research/campaigns/)。以下按研究阶段概括此前工作。

| 阶段 | 主要工作 | 结果与保留结论 | 详细记录 |
|---|---|---|---|
| 早期 QQQ/ML 因子研究 | 真实 QQQ 日线、LightGBM、均值回归/趋势/突破/隔夜/风险状态；参数、模型、频率和低相关特征变体 | 局部 Sharpe 较高但样本和交易数不足、绝对收益落后 QQQ，不能晋级；阈值和频率微调会破坏边际 | [2026-07-01 迭代日志](../reports/research/control/strategy-iteration-progress-2026-07-01.md) |
| 分钟动量 R1-R4 | 分钟数据可行性、确定性搜索、ML 与组合研究 | `mom_minute_r2` 有历史 `research_pass=true`，但不是 paper-ready；后续轮次未形成当前可用策略组 | [mom_minute_r2](../reports/research/iterations/mom_minute_r2/) |
| 多资产与结构策略 R1-R9 | 多资产动量、AI/ML、多模态、稳健动量、事件、多尺度、core-satellite、双趋势和 ETF 结构 | 多数 workflow 通过但 research 失败；paper-control R7 的历史 research pass 使用已暴露窗口，不能选择或晋级 shadow | [多资产 R1](../reports/research/iterations/mom_multiasset_r1/)、[paper-control R7](../reports/research/iterations/mom_multiasset_paper_control_r7/) |
| 动态主题与 PIT R8-R24 | ETF 主题链、股票聚类、事件 seed、PIT 语义框架、压力/恢复状态与高 Beta 路径 | 识别静态幸存者、主题寿命短、价格相关性不能代表经济关系；R19/R22 局部收益达标但 DSR、折稳定或捕获率失败，全部封存 | [历史执行计划](strategy-alpha-paper-execution-plan-2026-08-04.zh.md) |
| 高 Beta sleeve R1 | 确定性核心、ML 覆盖、回退、placebo 和统计门 | 主路径接近收益门，但 Sharpe/DSR/ML 增量不足；`workflow_pass=true`、其余研究和 paper 门失败 | [评估报告](../reports/research/iterations/mom_high_beta_sleeve_ensemble_r1/evaluation-run/evaluation-report.json) |
| VIX 期限结构 R1 | VIX/VIX3M 状态、确定性与 ML 角色、精确回退、校准、missing-modality、placebo、DSR/PBO | 实现修复轮完成 312 个 fit 和 6,528 条预测；ML 成本后增量为负，`ml_contribution_pass=false`，整个 family 停止 | [评估报告](../reports/research/iterations/mom_vix_term_structure_overlay_r1_implfix1/evaluation-run/evaluation-report.json) |
| 广度优先 QD R1 | 19 个候选覆盖日历流、跨时段、跨资产趋势、短反转、PIT 横截面动量、静态热点控制和波动 Beta | 实评 16、依赖跳过 3、0 advance；最佳 `VOL02` 仍未通过 Sharpe、CAGR、DSR 和捕获率，未读取 frozen OOS | [campaign 报告](../reports/research/campaigns/mom_breadth_qd_r1/development-evaluation-report.json) |
| 独立机制 QD R2 | 从 `VOL02` 邻域转向 CFTC 持仓、波动压缩突破、ETF 相对价值三个机制 | campaign 合同与 13 个候选蓝图已冻结，`pre-discovery=ok`；子迭代和实际评估尚未开始 | [R2 合同](../reports/research/campaigns/mom_independent_mechanisms_qd_r2/research-campaign-contract.json) |

历史上还验证过 Alpaca Paper 订单链路和状态漂移处理。该工作只作为产品执行基础设施
证据保留；它不属于当前 R2 模拟盘活动，也不能为任何当前候选提供 Alpha 或
`paper_ready_pass`。当前没有新增订单或自动处置动作。

## 5. 当前阶段总览

### 5.1 一句话结论

`未完成，当前已暂停`：R2 的研究治理和独立机制设计已经完成第一步，但尚未产生任何
有效收益流；上一最佳开发候选 `VOL02` 的 Sharpe、CAGR、DSR 和捕获率均未达标。
目前没有两个独立通过的低相关机制，不能建立最终策略组，也未达到可立即接入模拟盘阶段。

### 5.2 状态表

| 项目 | 当前值 | 判断 |
|---|---|---|
| 当前 campaign | `mom_independent_mechanisms_qd_r2` | `pre-discovery=ok` |
| 当前候选 | 13 个 campaign 蓝图 | 尚无正式 child manifest |
| workflow_pass | `N/A` | R2 没有 evaluation report |
| research_pass | `N/A` | 没有 R2 收益流或统计结果 |
| ml_contribution_pass | `N/A` | R2 禁止 ML，训练数为 0 |
| llm_contribution_pass | `N/A` | 当前三分支不使用 LLM |
| paper_ready_pass | `N/A` | 尚未进入执行现实与安全审查 |
| 独立通过机制 | `0` | 建组至少需要 2 个 |
| R2 模拟盘/券商活动 | 未启动，0 订单 | 符合当前目标边界 |

### 5.3 R2 候选结构

| 分支 | 蓝图数 | 合同上可晋级 | 当前可行性 |
|---|---:|---:|---|
| CFTC positioning | 5 | 2 | 研究可用；仍需量化-only、CFTC-only、combined、精确回退和 placebo |
| Volatility compression | 4 | 3 | 价格数据可研究；纯突破为不可晋级对照 |
| ETF relative value | 4 | 4 | 缺历史 shortability、borrow rate、recall/buy-in 与 paired-fill，当前应整支跳过 |

R2 合同 SHA-256：
`c44eb396e60a133a0cfdb331ed8fc63605b5a0db6682c0e07fd50c805a34f85b`。

## 6. 累计工作量

以下数字按当前仓库产物重新统计。`本轮增量` 指 R2 正式 child iteration 产物；campaign
合同和蓝图另列，避免把计划候选当作已经运行的试验。

| 统计 | 累计值 | R2 正式增量 | 口径 |
|---|---:|---:|---|
| 研究迭代目录 | 48 | 0 | 含研究、前向和控制轮次 |
| manifest 优化轮次 | 37 | 0 | 存在 `candidate-manifest.json` |
| 历史锁定轮次 | 16 | 0 | 独立一次性历史锁 |
| 有评估报告轮次/报告 | 37/37 | 0 | 不等于通过 |
| manifest 预注册候选 | 317 | 0 | 尚未加 R2 的 13 个蓝图 |
| trial ledger 原始/去重行 | 545/537 | 0 | 8 行重复发布 |
| dependency skipped / invalid | 66/8 | 0 | 从实际承载中排除 |
| 实际承载记录 | 463 | 0 | 不代表全部成功回测 |
| 模型 ledger 原始/唯一 ID | 4,286/4,018 | 0 | 268 行重复发布 |
| 有模型 ledger 轮次/候选角色 | 18/46 | 0 | 角色不等于模型架构数 |
| 历史未落盘训练暴露 | 最多 312 | 0 | 原失败 VIX R1，未并入正式模型数 |
| 自动研究目录/IC 报告 | 264/260 | 0 | 与正式 trial 分开 |
| 自动因子评估行/唯一因子 | 2,630/33 | 0 | 大量跨轮重复筛选 |
| R2 campaign 合同/蓝图 | 1/13 | 1/13 | 不计入 manifest 或 trial |

全仓 37 份评估报告中，36 份 `workflow_pass=true`；3 份报告、2 个独立轮次曾记录
`research_pass=true`。当前 `ml_contribution_pass`、`llm_contribution_pass` 和
`paper_ready_pass` 的通过报告数均为 0。

旧 breadth campaign 使用的 `8195` 是累计多重检验校正的有效试验数，不是物理执行了
8195 次回测；该 campaign 实际注册 19 个候选、评估 16 个、依赖跳过 3 个。

## 7. 当前表现与门槛差距

R2 没有 evaluation report，因此所有当前指标均为 `N/A`。`VOL02` 只作为上一份
可审计的 development-validation 基线，不是冻结 OOS 结果；该 campaign 的 frozen OOS
读取行数为 0。

| 指标 | R2 当前 | `VOL02` 开发基线 | 当前门槛 | 基线判定 |
|---|---:|---:|---:|---|
| 20 bps 净 CAGR | N/A | 26.28% | `>=45%` | 失败，差 18.72pp |
| Sharpe-excess-BIL | N/A | 0.9329 | 严格 `>1.0` | 失败，至少差 0.0671 |
| 相对 QQQ CAGR | N/A | +15.93pp | `>=8pp` | 通过 |
| TQQQ CAGR 捕获 | N/A | 4.988 | `>=0.85` | 通过 |
| 最大回撤 | N/A | -21.82% | `>=-65%` | 通过 |
| MAR | N/A | 1.205 | `>=0.40` | 通过 |
| TQQQ 上行捕获 | N/A | 0.0002 | `>=0.85` | 失败 |
| TQQQ 下行捕获 | N/A | 0.9694 | `<=0.90` | 失败 |
| DSR / PBO / SPA | N/A | 0.0150 / N/A / N/A | `>=0.75 / <=0.40 / <=0.05` | 失败/未定义 |
| 正向折数 | N/A | 4/4 | `>=3/4` | 通过 |
| 40 bps 总收益 | N/A | 83.80% | 严格 `>0` | 通过 |

局部风险门通过不能抵消收益、Sharpe、DSR 和捕获率失败。`VOL02` 已封存，不允许在
其参数邻域继续补救调优。

## 8. ML 为什么没有超过确定性策略

### 8.1 当前证据

- R2 当前模型角色、fit、预测、覆盖和回退均为 0，复杂度信用为 `0/N/A`。
- 最近 VIX 实现修复轮包含 4 个训练角色、312 个持久化 fit 和 6,528 条预测。
- 三种 ML 覆盖方案的成本后 aggregate log-wealth 增量为 `-0.2123`、`-0.7217`、
  `-0.5111`，都只有 1/4 折超过确定性回退。
- combined ML 相对 price-only ML 的 aggregate log-wealth 增量为 `-0.2988`，
  0/4 折胜出。
- 因此 `ml_strategy_pass=false`、`ml_contribution_pass=false`、复杂度信用为 0。

### 8.2 当前反思

- 底层确定性信号本身不够稳定时，ML 只能学习噪声和已暴露的状态边界，无法创造经济机制。
- 金融标签噪声高、状态非平稳；有限周频或稀疏事件数据不足以支撑复杂决策边界。
- 覆盖模型增加了错误覆盖和时点风险，触发次数并没有转化为跨折的正政策价值。
- 目标函数、校准和覆盖若只优化预测指标，可能与含成本的组合价值和上行捕获不一致。
- price-only ML 已经吸收主要可学价格关系，新模态没有稳定边际信息，combined 反而更差。
- 后续正确路径不是训练更多相近模型，而是先找到可重复的确定性机制，再用严格匹配消融
  判断 ML 是否只在少数状态提供正增量。

## 9. 知识库、因子库与数据体量

| 资产 | 当前规模 | 质量与表现 | 当前缺口 |
|---|---:|---|---|
| 知识索引 | 191 个去重来源、1,541 次出现、61 条经验记忆、8 条模型记忆 | 183 新鲜、8 过期 | 最后生成于 2026-08-18；R2 child-specific baseline/scout 尚无 |
| 来源卡 | 71 文件、854 行、454 个 claim、195 个 URL | 724 行直接验证、7 行新鲜复用、123 行旧格式/缺状态 | 旧格式仍需逐步归一化 |
| 知识评估 | 39 份 | 39 份 `status=ok` | 只证明知识流程，不证明 Alpha |
| 注册因子库 | 84 个因子、20 个 family | 71 个有可执行 expression | R2 尚无策略级因子产物、IC、消融或收益归因 |
| 自动因子筛选 | 260 份 IC 报告、2,630 行、33 个唯一因子 | 平均覆盖 96.02%；427 行正 rank IC；均值/中位数 -0.0138/-0.0306 | 1,609 行带 flag，重复筛选多且整体信号偏弱 |
| 数据能力 | 13 项：5 approved、8 trial | 2 项声明非空 paper-ready timeframe；4 项 research-only | PIT、借券、修订和实时延迟证据不足 |
| CFTC 快照 | 495 条下载、483 条可回放 | 机械 blocker 为 0 | 仍非 paper-ready；需边际增量、placebo 和修订敏感性 |
| ETF 做空能力 | 未具备 | 无法给相对价值分支真实晋级信用 | 缺逐日 shortability、borrow cost、recall/buy-in 和 paired-fill |

主要入口：[知识索引](../reports/research/knowledge/index.json)、
[注册因子库](../open_composer/research/factor_library.py)、
[数据能力注册表](../capabilities/registry.yaml)。

## 10. 已完成、不足与当前判断

### 10.1 已完成

- 已建立产品原生、可审计的研究链路和固定进展统计口径。
- 已保留多轮确定性、ML、多模态、主题、PIT、VIX 和 breadth 负面实验。
- 已封存旧 breadth campaign，确认 0 个候选可进入 frozen OOS。
- 已从 `VOL02` 邻域转向三个经济机制明显不同的 R2 分支。
- R2 campaign 合同已通过 `pre-discovery`：4 个假设、3 个分支、13 个候选，
  `blocked=[]`、`warnings=[]`。
- 固定门槛没有因历史结果不足而降低。

### 10.2 当前主要不足

- R2 三个 child iteration 目录均不存在：`mom_cftc_positioning_r3`、
  `mom_volatility_compression_r1`、`mom_etf_relative_value_r1`。
- 尚无 R2 StrategySpec、knowledge scout/assessment、candidate manifest、
  `pre-backtest` validation、runner、trial ledger 或 evaluation report。
- 因而 R2 当前没有一条正式收益流，实际策略优化尚未开始产生新绩效证据。
- ETF relative-value 分支在现有能力下预期整支依赖跳过；实际可运行宽度暂时只有 CFTC
  与波动压缩两个方向。
- R2 的“独立”目前只是经济假设独立，尚无收益流可验证经验相关性。
- 当前知识索引没有纳入 R2 的 child-specific 新研究。
- 历史工程治理和证据完整性工作防止了泄漏与伪晋级，但占用时间较多，Alpha 实验效率
  低于用户要求。
- 两个 R2 实现任务曾因上游 `429 Too Many Requests` 在写入前失败，没有产生可用文件。

### 10.3 当前判断

- 用户最终要求：`未满足`。
- 是否需要继续优化：`需要`，但当前按用户要求暂停。
- 是否应继续修改 `VOL02`：`不应`，该分支已失败并封存。
- 是否已有策略组：`没有`，独立通过机制数为 0。
- 是否可立即接入模拟盘：`不可以`。
- 当前 R2 是否启动模拟盘或券商活动：`没有`。

## 11. 下一步计划（仅记录，当前不执行）

1. 为三个 child iteration 生成 StrategySpec、知识 baseline/scout/assessment、数据/特征/
   成本/基准/验证合同和 candidate manifest；通过条件是每个可运行分支
   `pre-backtest status=ok`。ETF 依赖不足则整支 `dependency_skipped`。
2. 只读取 development partitions，执行 CFTC 和波动压缩的固定候选；生成完整 trial、
   return、benchmark、fold、DSR/PBO/SPA 和 QD archive/ledger 证据。失败分支立即封存，
   不做附近参数补救。
3. 只有至少两个机制分别通过全部 development 门且绝对相关性 `<=0.70`，才打开一次
   小型策略组组合迭代；随后封存 cohort，最多进行一次 frozen OOS。若不足两个机制，
   则转向新的独立机制，不组合、不启动模拟盘。

## 12. 证据索引与历史记录

- 当前固定汇报格式：[策略优化进展汇报模板](strategy-optimization-progress-report-template.zh.md)
- 早期详细优化日志：[Strategy Iteration Progress - 2026-07-01](../reports/research/control/strategy-iteration-progress-2026-07-01.md)
- R8-R24/R1 等详细历史计划：[Alpha 与 Alpaca Paper 优化迭代执行计划](strategy-alpha-paper-execution-plan-2026-08-04.zh.md)
- 旧 breadth campaign 合同：[mom_breadth_qd_r1 contract](../reports/research/campaigns/mom_breadth_qd_r1/research-campaign-contract.json)
- 旧 breadth development 结果：[development evaluation report](../reports/research/campaigns/mom_breadth_qd_r1/development-evaluation-report.json)
- 旧 breadth 发布回执：[development evaluation receipt](../reports/research/campaigns/mom_breadth_qd_r1/development-evaluation-receipt.json)
- 当前 R2 合同：[mom_independent_mechanisms_qd_r2 contract](../reports/research/campaigns/mom_independent_mechanisms_qd_r2/research-campaign-contract.json)
- VIX ML 负面证据：[VIX implfix1 evaluation](../reports/research/iterations/mom_vix_term_structure_overlay_r1_implfix1/evaluation-run/evaluation-report.json)
- 高 Beta sleeve 负面证据：[high-beta R1 evaluation](../reports/research/iterations/mom_high_beta_sleeve_ensemble_r1/evaluation-run/evaluation-report.json)
- 当前知识索引：[knowledge index](../reports/research/knowledge/index.json)
- 当前因子库：[factor library](../open_composer/research/factor_library.py)
- 当前数据能力：[capability registry](../capabilities/registry.yaml)

旧历史文档中的 `Sharpe >=0.8` 等旧门槛仅用于解释当时决策，不再适用于 2026-08-15
之后首次冻结的新候选。当前统一使用严格 `Sharpe >1.0` 及本文件第 2 节的完整门槛。

## 13. 更新日志

### 2026-08-24

- 建立本统一进展日志。
- 记录用户完整目标、研究方法、PIT 动量要求、ML 增量要求、策略组条件和模拟盘边界。
- 固化当前累计统计、知识/因子/数据规模、`VOL02` 开发基线和 R2 空绩效状态。
- 将早期详细日志和 8 月历史计划保留为链接证据，不让旧口径覆盖当前门槛。
- 当前按用户要求暂停，没有生成、训练、回测、模拟盘或券商写入。
