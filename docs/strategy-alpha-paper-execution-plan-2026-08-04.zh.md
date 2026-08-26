# Open Composer Alpha 与 Alpaca Paper 优化迭代执行计划

日期：2026-08-10  
计划版本：`4.2`  
基线提交：`e178eb79c5cc2ebff334bd538b5f19c9a362031c`  
当前迭代：`successor_capability_unlock`  
状态：R22/R24/R1 已封存并停止；R23 观测已暂停；当前能力下没有候选达到 `paper_entry_ready`

本文件是当前唯一执行依据。它合并并取代 1.x 版本、上传的 Claude 诊断行动清单，
并吸收 R8、R9、R10 的实际结果。除非出现新的数据、方法或运行证据，不因回测结果
不理想而放宽门槛。

## 0. 不可偏离的用户约束（2026-08-10 更新）

- 最终交付必须是八角色策略组：无训练确定性核心、确定性语义主题、ML 覆盖分类器、
  ML 尾部风险模型、LLM 结构化因子、量化与 LLM 组合、缺失模态精确回退和 placebo。
- 收益目标向 matched TQQQ 靠拢，允许最大回撤到约 `-65%`；不能用长期低仓位、低
  Beta 方案换取表面 Sharpe，也不能把低收益观察路径描述成完成。
- 主题和成员必须随时间变化，由当时可见的 SEC/新闻事件和经济关系产生。AI 产业链、
  机器人等是当前可能出现的主题，不是从历史起点固定不变的股票池。
- 历史阶段验证价格核心和模型方法；没有真实历史 PIT 文本时，不回填 LLM Alpha，
  LLM/组合角色保留为零资金、精确回退角色，不能阻塞合格确定性/ML 组合的交付。
- 当前工作只围绕策略研究、必要数据、回测真实性、目标仓位链路、执行设计和 Paper
  安全材料展开；终点停在可以立即开始模拟盘测试之前，不运行或等待模拟盘。
- 八个角色必须有可验证的 StrategySpec、回退合同和运行时映射；至少一个确定性策略和
  一个获得复杂度信用的 ML 策略必须通过相同成本、折和基准门，才可称策略组达标。
- 禁止真实资金写入，也不提交 Alpaca Paper 订单。未来会话、broker acceptance、fills、
  latency 和 TCA 属于下一阶段的 `paper_validated` 证据，不是本轮 `paper_entry_ready` 的
  等待项，也不能由历史回测或合成 receipt 伪造。

### 0.1 本轮更新的用户目标

- 先使用 StrategySpec、知识库、source cards、因子目录和 Factor Lab 形成可审计研究链；
  每轮必须先通过 `oc research iteration validate`，再 lock、训练或回测。
- ML 必须预测真实 D01 review point 上含切换成本、持有约束、硬压力退出和 terminal
  rejoin 的可执行政策价值；不确定时逐位回退 D01。
- 只有在相同数据、特征、成本和时序折下至少 3/4 折胜 exact D01、3/4 折下界覆盖达标、
  实现 override value 为正、至少 8 次有效 override、换手不超上限，并保留至少 95% 的
  D01 TQQQ 上行捕获时，ML 才获得复杂度信用；否则标记为无独立 ML Alpha。
- R24 transfer holdout 已暴露于研究设计，只能作为诊断；R24 不得晋级。新策略族必须
  使用新假设、新合同和预注册证据，不能继续微调 R22-R24 的已暴露价格路径。
- placebo seed 只能来自一个 canonical StrategySpec，R24 `R24P01` 固定为 `15108`。
- 当前目标是离线完成 `StrategySpec -> target weights -> signal/intent ledger ->
  execution policy` parity、forensics、execution reality 和安全预检；到达该边界后停止。
  既有 10,235 股 TQQQ Paper 持仓只记录为启动前处置项，系统不得自动处理。

R13-R17 均已冻结并停止，不允许修改或重跑。R15 把增强态集中到 `SOXL 100%`，
R16 证明慢压力态无条件持有 SQQQ 会被反向复利和反弹震荡破坏，R17 恢复 QQQ 并
增加固定的短周期 TQQQ 恢复态。R17 相对 R15 有改善，但仍未达到收益、折稳定性、
DSR 和 PBO 门槛。语义角色继续 forward-only、零股票预算。

## 1. 最终目标和完成定义

目标是在不接触真金账户、也不运行 Alpaca Paper 的前提下，交付一组下一步即可开始
模拟盘测试的策略，至少包含：

1. 不训练模型的确定性策略；
2. 严格按时间折训练的 ML 策略；
3. 将 SEC/新闻转换为结构化因子的 LLM 策略；
4. 量化与 LLM 因子的组合策略；
5. 缺失模态精确回退；
6. 打乱语义映射的 placebo 对照。

本轮完成状态固定为 `paper_entry_ready`：策略组通过冻结的历史表现、成本、四折、完整
基准族、DSR/PBO、forensics、Factor Lab lineage、运行时 target parity、execution reality
和 Paper 安全预检；没有未实现的 adapter，也不需要再补研究代码或材料。达到后停止，
不启动定时器、不提交订单、不等待成交。

`paper_validated` 是下一阶段状态：只有真实 Alpaca Paper 会话、broker acceptance、fills、
latency、slippage/TCA 和运行稳定性才能取得。LLM/组合角色只有在真实 PIT packet 证明
增量贡献后才允许获得资金权重；此前必须精确回退到通过门槛的量化策略。

状态必须分开记录：`workflow_pass`、`research_pass`、`llm_contribution_pass`、
`paper_entry_ready`、`paper_ready_pass` 和 `paper_validated`。`paper_entry_ready=true` 不会
把尚未运行的模拟盘证据伪装成 `paper_ready_pass=true` 或 `paper_validated=true`。

## 2. 用户目标的量化解释

用户接受更高回撤并希望收益向 TQQQ 靠拢，因此研究主口径固定为：

- 净 CAGR 至少 `max(45%, 0.85 * matched TQQQ CAGR)`；
- 相对 matched QQQ CAGR 至少增加 8 个百分点；
- 最大回撤不低于 `-65%`；
- 年化 Sharpe 至少 `0.80`；
- MAR 至少 `0.40`；
- TQQQ 上行捕获至少 `0.80`，下行捕获不高于 `0.90`；
- 主成本为每次单边换手 `20 bps`，同时报告 `10/20/40 bps`；
- 至少 3/4 个预注册时序折相对 QQQ 有正提升；
- 晋级时 DSR 概率至少 `0.75`，PBO 不高于 `0.40`；
- 所有“年化收益”均为几何复利 CAGR，不用算术平均冒充 CAGR。

Tier 0 储备门槛不等于 Alpha 通过：

- 净 CAGR 至少 30%；
- 相对 QQQ CAGR 至少增加 4 个百分点；
- 20 bps 后总收益为正；
- 无前视、错误记账、placebo 优势或数据合同违规。
- R24 ML 另须通过 3/4 折政策价值、下界覆盖、最少 override 和 D01 上行捕获门。

## 3. 当前真实进度

### 3.0 2026-08-13 R1 锁定结论与当前阻塞

R1 用独立固定资本袖套测试了 R22-R24 之外的新组合结构：50% TQQQ 持久锚仓，
另 50% 按月末 QQQ SMA200 在 TQQQ/BIL 间切换；同时配置了两种严格时序 ML 覆盖、
精确回退和零资本语义角色。唯一一次锁定评估已完成并封存，`workflow_pass=true`，
但 `research_pass=false`、`llm_contribution_pass=false`、`paper_entry_ready=false`。

- 主候选 S1D01 在 20 bps 后 CAGR `42.94%`、最大回撤 `-49.16%`、超 BIL Sharpe
  `0.860`、MAR `0.873`、TQQQ 上/下行捕获 `0.849/0.852`；40 bps CAGR 为
  `42.43%`。四折 QQQ 提升均为正，但仍低于 45% CAGR 门槛。
- 非晋级 60% 锚仓邻域 S1D04 达到本族最高的 20/40 bps CAGR
  `44.20%/43.76%`，仍未过门，且不能从事后邻域中选择晋级。
- 累计试验数为 `8,138`，零假设期望最大年化 Sharpe 为 `1.9069`；S1D01 DSR
  概率只有 `0.0286`，族 PBO 为 `0.8643`。当前主要缺口不是再补约两个百分点收益，
  而是在保留高收益和上行捕获时显著提升跨期平滑度与稳定性。
- S1M01 只有 1 次有效 OOS 覆盖、1/4 折胜核心，累计政策价值 `-0.001422`；
  S1M02 只有 6 次覆盖、2/4 折胜核心，累计政策价值 `-0.007400`。二者精确回退均
  无错，但样本稀疏、动作太少，未产生独立 ML Alpha。
- R1、R22、R24 不得重跑或继续调整锚仓、SMA200、Ridge alpha、Logistic 阈值。
  知识索引已修复为采用回执验证的最终 R1 `stop`，不再读取根目录旧 `pending` 模板。

对现有干净行情和能力注册的对抗审查没有找到值得立即增加一次计数试验的正交来源。
GLD、PSQ 和日线隔夜/日内分解可做研究诊断，但只是同一已暴露 ETF 价格面板上的局部
替代，缺乏将成本后 Sharpe 从约 0.94 提升到约 1.91 的机制证据。牛熊杠杆 ETF 等额
空头 carry 的固定、非候选体检也被否决：三对合成约 `1.26%` 年化、Sharpe `0.53`，
且仓库没有历史借券可用性或费用，Alpaca Paper 也不模拟借券费。

因此当前下一动作不是创建 R2 并消耗试验次数，而是先增加一种真正独立、PIT、可重放、
可交叉验证的数据能力。优先级为：

1. 连续期货合约、展期/期限结构、保证金和佣金数据，用于趋势与 carry 分散；
2. 期权链、NBBO、Greeks、公司行动和交易成本，用于定义风险的波动风险溢价；
3. 历史借券可用性/费用及独立反向 ETF 价格源，优先级较低。

任何能力解锁后，必须先注册并评估 capability，再完成知识 build/scout/assess、固定候选
manifest、成本/标签/验证/基准合同和 `oc research iteration validate`，才允许一次锁定
评估。没有这些新证据时，继续在当前 ETF 面板筛选因子只会增加多重检验负担。

### 3.1 高 Beta 确定性执行基线

策略：`nasdaq_tqqq_fixed_etf_router_daily_iter11_exposure_search`

- 方法：g0.80 TQQQ/杠杆 ETF 基础路由外包一层策略净值风险管理器；策略净值回撤
  达 18% 后把指定风险资产缩放到 35%，至少保持 10 个交易日，回撤恢复至 10%
  后解除，并把释放风险的 50% 配到 BIL。
- 旧 Alpaca/IEX 同窗数值已逐项复现：CAGR `66.5171%`、Sharpe `1.5050`、最大
  回撤 `-28.1454%`、454 个调仓会话。
- 该路径来自 660 个候选，过拟合风险高，只作为 Tier 0 执行基线，不作为新 Alpha。
- 2026-08-04 已恢复研究标签到产品运行时的状态重建，修复最后会话被丢弃的问题。
- 当前真实数据截至 `2026-08-03`，Alpaca IEX `live_fetch/strict_live=true`。
- 最新目标：`2026-08-04` 会话 `SOXS 2.6406596%`，状态 `equity_throttle`；前一
  会话为 `TECS 6.1780684%`。这是观察目标，不是已成交持仓。
- execution observation 为 `observation_only`，最新会话有 2 条需调整意图，
  `broker_writes=false`。

扩展到 2026-07-31 可计算收益区间后，同一路由 CAGR 降至 `55.0921%`、Sharpe
`1.3134`、最大回撤仍为 `-28.1454%`。这说明早期 `66%` 不是当前稳定预期，仍需
按新数据继续观察。

### 3.2 R8-R10 的有效负结果

| 迭代 | 唯一变化 | 结果 | 裁决 |
|---|---|---|---|
| R8 | ETF 代理形成动态主题链，含 ML | 主题层未产生稳定、可归因增量 | 停止，不把 ETF 分类当动态产业链 |
| R9 | 扩到当前股票池并每日聚类 | 成员过宽、寿命短、成本高，当前幸存者池不能晋级 | 停止，不回看锁箱调参 |
| R10 | 价格/成交量事件先形成 seed，再用残差相关扩散 | D01 CAGR 57.53%，D02 60.26%；D01 未胜控制，DSR 0.0267、PBO 0.5429，仅 2/4 折正提升 | 停止，不训练 R10 ML，不打开 252 日锁箱 |

R10 的关键归因：551 个 seed 产生 214 个主题、118 个确认主题，62 只股票中 61 只
至少入选一次；确认主题中位寿命仅 2 个会话。事件 seed 和关联成员在 1/3/5/10 日
相对 TQQQ 均未形成可靠正增量。结论不是“动量无效”，而是价格相关性不能发明
经济关系。

### 3.3 R11-R14 的有效结果

| 迭代 | 唯一变化 | 20 bps 最佳结果 | 裁决 |
|---|---|---|---|
| R11 | PIT 语义框架与干净 SIP 价格基线 | 数据/实现框架通过；旧拆股污染被识别 | 价格数据修复后进入 R12 |
| R12 | 修复独立 adjustment 快照与路径 | 洁净价格路径可评估，但收益门槛未过 | 停止，不改锁 |
| R13 | TQQQ 核心加每日短周期 ETF winner | M01 CAGR 11.59%，MDD -61.97%，换手 15.15x | 停止；日切换成本过高、上行捕获不足 |
| R14 | QQQ 压力态、TQQQ 常态、80/20 半导体增强 | M01 CAGR 22.89%，总收益 127.88%，MDD -60.83%，MAR 0.376，换手 7.41x | PBO 0.361 通过，但 45% CAGR、Sharpe、MAR、上行捕获和 DSR 未过；停止 |

R14 的 matched TQQQ CAGR 为 8.93%、MDD -81.58%，QQQ CAGR 为 12.42%。R14M01
不是低仓位策略，平均风险资产暴露为 100%；它的主要缺口是仅 67/1008 个会话进入
半导体增强态，TQQQ 上行捕获仍为 74.51%。R15 因此只测试增强态集中度，不改变
压力门、确认条件、模型阈值、成本、折、holdout 或统计门槛。

### 3.4 R15-R17 的有效结果

| 迭代 | 唯一变化 | 20 bps 最佳结果 | 裁决 |
|---|---|---|---|
| R15 | 80/20 半导体增强改为 SOXL100 | M01 CAGR 24.33%，MDD -60.58%，PBO 0.346 | 收益、Sharpe、上行捕获和 DSR 未过；停止 |
| R16 | 272 个慢压力会话从 QQQ 改为 SQQQ | M01 CAGR -1.66%，MDD -74.01%，PBO 0.575 | 反向复利与反弹震荡破坏路径；停止且永久保留负结果 |
| R17 | 恢复 QQQ；仅在 QQQ>SMA50、TQQQ 10 日动量>=8%、技术广度>=4/5 时临时恢复 TQQQ | M01 CAGR 26.64%，MDD -57.06%，Sharpe 0.647，MAR 0.467 | 19 个恢复会话有效，但仅 2/4 折胜 QQQ，PBO 0.629、DSR 0.009；停止，transfer holdout 未打开 |

R17 相对 R15 的 CAGR 提升 2.30 个百分点、MDD 改善 3.52 个百分点，证明快速恢复
机制有局部价值；但它只发生在 F2，未修复 F1/F4，不能据此接 Paper。R17 的 final
dossier 已通过，evaluation SHA-256 为
`46e8fbaa7abb56281a1d7eae7cde432726a0ddef6945daff2fdd1dd448ff474c`。

R18 已完成并停止。确定性 D01 在 20 bps 后达到 CAGR 32.86%、MDD -60.96%、
Sharpe 0.721、MAR 0.539，较 R17D01 的 CAGR 提高 10.67 个百分点；PBO 从 0.629
降到 0.175。它仍因 CAGR 低于 45%、仅 2/4 折胜 QQQ、DSR 0.0126 和换手 12.012
略超上限而失败。M01 只把 USD 用于 83 个会话，CAGR 降到 13.23%，证明旧分类器
错误过滤了确定性 USD 路径。R18 final dossier 通过，transfer holdout 访问次数仍为 0。

R19 的唯一机制是：保留 R17/R18 的慢压力 QQQ 和固定快速恢复 TQQQ 合同，把普通
风险态的确定性核心从 TQQQ100 改为 USD100，不再要求半导体领导门才能持有 USD；
M01 的方向反转为仅在高置信度时授权 TQQQ100 替代 USD100，M02 仍只做尾部退出。
调度、恢复阈值、模型家族、成本、四折、holdout 和语义零资本合同均不变。该机制继续
受已暴露 USD ex-post-best 选择影响，累计有效试验数预注册为 8,102；开发通过仍不能
直接宣称 Alpha，只有此前从未打开的 252 会话 transfer holdout 能提供独立选择证据。

R19 已完成一次性开发评估并停止。D01 在 20 bps 后达到 CAGR `48.37%`、MDD
`-64.76%`、Sharpe `0.880`、MAR `0.747`，首次同时达到用户的收益和回撤标题目标；
PBO `0.314` 也通过。但它只在 2/4 折胜 QQQ，DSR 概率仅 `0.0274`，因此
`research_pass=false`，transfer holdout 访问次数仍为 0。M01/F01 CAGR 为 `38.06%`，
M02 未触发任何尾部退出并与 M01 相同。

R19 路径归因显示，F1 和 F4 的相对损失都来自正常风险态继续持有 USD，而不是压力态
QQQ：F1 的 136 个 USD 区间收益 `-16.82%`，同区间 QQQ 为 `-8.49%`；F4 的 213 个
USD 区间收益 `3.13%`，同区间 QQQ 为 `6.84%`，且出现单日 `-23.61%`。F2/F3 的
USD 路径又是高收益来源。因此 R20 只增加一个 USD 自身趋势的快速压力覆盖，不删除
USD、不改变语义主题合同，也不做阈值扫参。累计有效试验数固定增加到 `8,110`。

R20 已完成一次性开发评估并停止。D01 在 20 bps 后为 CAGR `32.23%`、MDD
`-70.57%`、Sharpe `0.714`、MAR `0.457`；虽然 3/4 折胜 QQQ 且 PBO 为 `0`，但
收益、回撤、Sharpe、上行捕获和 DSR `0.0124` 均未过门。压力闩锁在 11 段共 348
个会话生效；这些会话 QQQ 复合收益为 `22.30%`，R19 锁定路径反事实为 `92.22%`。
它保护了 2022 年初和 2025 年春的持续下跌，却在多数急跌后反弹阶段长期压制高 Beta
恢复。transfer holdout 访问次数仍为 0。

R21 只测试一个机制：保留 R20 的 USD 压力触发和释放条件，但压力期不再禁止 R17
已经冻结的快速恢复条件；当 QQQ 位于 SMA50 上方、TQQQ 10 日动量至少 8%、且技术
广度至少 4/5 时临时持有 TQQQ，任一条件失败立即回 QQQ。不得搜索阈值、改变成本、
折、模型、holdout 或语义零资本合同。累计有效试验数固定为 `8,118`。

R21 已完成一次性开发评估并停止。D01 在 20 bps 后达到 CAGR `43.85%`、MDD
`-66.62%`、Sharpe `0.861`、MAR `0.658`，并在 3/4 折胜 QQQ、PBO 为 `0`；但
CAGR、回撤、TQQQ 上行捕获 `0.759` 和 DSR `0.0255` 未过门。M01/M02/F01 CAGR
均为 `29.17%`，训练模型没有改善 D01。348 个 USD 压力会话中，完整三条件恢复仅
触发 17 个会话；QQQ SMA50 与 TQQQ 10 日动量两个快速条件同时满足 49 个会话，
而慢速 100 日科技广度仅满足 32 个会话。transfer holdout 访问次数仍为 0。

R22 只测试一个机制：USD 压力状态继续要求 QQQ 位于 SMA50 上方且 TQQQ 10 日动量
至少 8%，但不再等待 100 日科技广度达到 4/5；普通压力状态继续使用原三条件恢复。
USD 压力闩锁、所有阈值、调度、模型、折、成本、holdout 和语义零资本合同均保持
不变。这个机制由已暴露的 R21 条件归因产生，开发结果仍不能单独证明 Alpha；累计
有效试验数固定为 `8,126`。

R22 已完成一次性开发评估并停止。D01 在 20 bps 后达到 CAGR `50.51%`、MDD
`-64.80%`、Sharpe `0.934`、MAR `0.779`、年化单边换手 `10.51x`，并在 3/4 折
胜 QQQ，PBO 为 `0`。它已达到用户的收益、回撤、Sharpe、MAR、QQQ 提升、折稳定、
换手和下行捕获目标，但 TQQQ 上行捕获 `0.7822` 低于 `0.80`，且按累计 `8,126`
次有效试验计算的 DSR 仅 `0.0353`，因此正式 `research_pass=false`，不宣称已验证
Alpha。M01/M02/F01 CAGR 均为 `33.82%`，训练模型没有改善 D01；transfer holdout
访问次数保持 `0`。历史价格路径不再继续调参，当前工作转入独立 forward epoch，八
角色均只做 Tier 0，语义股票预算仍为 0。

R22 历史锁 SHA-256 为
`796c01de14ee1c9b236d9ba3623a0b00050a175044eab272aea4954efda4b932`，评估报告
SHA-256 为
`6fa746c79dacd24296d8d2b7760f6b64436d5ea965403512414f6f854dd96b3d`。

### 3.5 R22 ML 失败反思与 R24 修正

R22 的 ML 失败首先是任务定义失败，不是简单的模型家族失败。M01 训练的是 20 日
`TQQQ100 vs USD100` 二元方向标签，而实际策略每 5 个会话审查、至少持有 10 个会话，
并且有 USD 压力闩锁、快速恢复、切换成本和 terminal rejoin。该标签忽略了收益幅度、
路径风险、可执行 review point 和切换经济学，因此即使方向判断正确，也可能产生较低的
净政策价值。20 bps 下 D01 CAGR 为 `50.51%`，M01/M02 均为 `33.82%`；四个时序折中
ML 全部落后 D01。M02 的尾部退出实际触发 `0` 次，和 M01 完全同路，不能算独立增量。

R24 的单一修正是把标签改成真实 review point 上的十会话 after-cost incremental
log wealth，使用 fold-local Ridge 与保守 LightGBM，下界不为正就 exact fallback。
外部研究（政策直接学习、friction-aware inaction band、turnover regularization 和
transaction-cost model comparison）只支持这个方法假设，不是本地 Alpha 证据；因此
仍保留 quant-only、combined、missing-modality 和 placebo 对照，并把 exposed transfer
holdout 仅作诊断。

### 3.6 R22 Tier 0 当前绑定状态

R22 八角色的 broker-write-free 决策链已经完成技术接入。当前唯一有效 epoch 为
`r22fwd_3d66e41859970451`，锚点会话为 `2026-08-05`，epoch lock SHA-256 为
`dbb10345d74182587ee757b10035fe05c88c7c777029767d2a6f6e656a8dc3c6`。

- `2026-08-05` 已生成八个角色各自的 target weights、rebalance intents 和 execution
  observation，共 24 份角色执行投影，并写入不可变 receipt 和 append-only ledger；
- 全部投影均为 `observation_only=true`、`broker_writes=false`、
  `order_authority=false`，权重和为 1，语义股票预算为 0；
- 当前八个角色均处于 `USD100` 状态。这是 R22 冻结规则对当日价格路径的输出，不是
  Paper 账户持仓，也没有触发任何订单；
- 当前价格快照来自 Alpaca IEX live fetch，`adjustment=all`，追加了 `2026-08-04` 和
  `2026-08-05` 两个会话；内容 SHA-256 为
  `3a094477d3817df1802e10cd53ac2ac53240269ec73d28122bbdb1875a925160`；
- 当前抓取 53 条 Alpaca News 记录，其中 52 条版本在新锁前已经出现并被排除；唯一
  锁后新版本形成 1 个 source packet、1 个确定性映射和 1 个严格 schema、实体白名单、
  packet 绑定均有效的 `gpt-5.6-sol` 因子；
- 该唯一新因子来自 SPY 宏观通胀新闻，只能作为 regime context，不能证明动态产业链
  Alpha。因此语义资金仍为 0，`llm_contribution_pass=false`；
- 首次技术观测等于 epoch 锚点，只证明链路可运行，不计为独立未来会话；当前稳定性
  计数为 `0/5`，`tier0_technical_pass=true`，`tier0_stability_pass=false`；
- Paper 只读对账成功，但账户已有 10,235 股 TQQQ，市值 742,139.85 美元，未实现
  损益 -22,606.93 美元，当前无挂单。R22 目标与现有持仓冲突，因此 reconciliation
  为 warning；系统没有改变该持仓。

首个 bootstrap epoch 因两项 provenance 缺陷被隔离：Alpaca live source 被错误标记为
`injected`，且认证错误文本曾包含被掩码的 key 片段。第二个 epoch
`r22fwd_b31c6058d3001ff8` 虽修复这两项且有效会话计数为 0，但 LLM backend 未使用
Codex provider base URL，并且重复抓取会重置新闻 first-seen；它也已完整隔离。两个旧
epoch 都不参与 forward、研究或 Paper 计数。当前实现已：

- 使用产品配置的兼容 provider base URL，实测 `gpt-5.6-sol` 严格 JSON 可用；
- 对相同 `article + updated_at + symbol` 保留全局最早 fetched/first-seen/visible 时间；
- 排除当前 epoch 锁建立前已见的版本；
- 正确记录 `live_fetch`、完全净化认证错误，并在认证失败后停止重复 LLM 调用。

### 3.7 R23 唯一新研究假设

R23 不再改 R22 的价格阈值，也不把单一市场代理新闻称为主题。唯一新增机制是
`multi_entity_economic_diffusion_gate`：

1. SPY、QQQ 和其他 ETF 的单实体新闻只进入市场状态上下文，不进入股票主题；
2. 主题至少包含两个当时可投资的公司实体；
3. 公司间必须有 source-bound 经济关系，或同一可核验事件对多个公司有明确影响；
4. 主题需同时通过 3-10 会话注意力加速、残差动量、成交量意外和成员广度确认；
5. 新闻注意力减速、领导者反转、拥挤或固定 3-20 会话到期时退出；
6. LLM 只抽取事件类型、影响对象、方向、置信度、关系和期限，不输出权重或订单；
7. R23 仍以零语义资金 forward 运行，只有 C01/L01 对 matched F01/M01 形成稳定增量且
   P01 不胜出后，才在全新 epoch 预注册非零预算。

### 3.8 R23 Tier 0 当前绑定状态

R23 dossier、knowledge scout/assessment 和 pre-backtest validator 均已通过。唯一当前
epoch 为 `r23fwd_6666346d7ed7e458`，锚点会话为 `2026-08-05`，lock SHA-256 为
`09956988e05ede8bac3256f0e7d0ecd77ef6ca2e6aba40c80279c48237899c5a`。

- `2026-08-05` bootstrap 已从 Alpaca IEX 和 Alpaca News 生成八角色 target weights、
  intents、execution observations、receipt、ledger 和账户只读 reconciliation；
- 81 条新闻中 41 条为 epoch 后可见，形成 11 个新 source packets，并选择 8 个动态
  公司主题候选；当日没有主题通过完整多实体经济关系、生命周期和量价确认门；
- 三个多公司 LLM 请求在 SDK 自动重试后仍遇到 provider 502，其余候选不足两个公司；
  因此 bootstrap 的有效 LLM 因子为 0。该日不计入 forward，不能据此否定或确认 LLM；
- 当日冻结价格核心输出为 `USD100`。这里的 `USD` 是 ProShares Ultra Semiconductors
  两倍杠杆 ETF，不是现金；该输出仅为 observation target；
- Paper 账户只读同步仍显示 10,235 股 TQQQ，系统未提交、修改或撤销任何订单；
- `tier0_technical_pass=true`，历史上曾记录 `2/5` 技术稳定和 `2/20` 研究资格；这些
  未来会话不是本轮完成条件，也不再继续计数；
- `research_pass=false`、`llm_contribution_pass=false`、`paper_ready_pass=false`；
- systemd timer `open-composer-r23-tier0-observation.timer` 已于 2026-08-10 明确禁用并
  停止（`disabled/inactive`）；所有 R23 观测产物保留，不删除、不回填；
- 所有产物保持 `observation_only=true`、`broker_writes=false`、
  `order_authority=false`，语义股票预算为 0。

### 3.9 R24 终局与产品缺口

- 31 张 R24 source cards 已绑定 external brief；2026-08-10 重新构建的知识索引含 156
  个唯一来源，knowledge assessment 为 `ok`：29 个复用、2 个新来源、0 个需刷新。
- R24 pre-backtest 通过后完成唯一一次 locked evaluation，裁决为 `stop_price_paths`；
  transfer holdout 未读，访问次数为 0，R24 dossier 已封存且不得修改或重跑。
- policy-value 标签的绝对/局部位置混用已修复，R24 专项测试为 16 个通过；P01 seed、
  F01=M02 modality contract 和 factor-library ID 已形成机器校验。
- 因子目录 ID 现在必须真实存在，但 R24 panel 因子仍是专用 expression 语义；在晋级前
  还必须产生同一快照和时序折上的 Factor Lab/lineage 证据，不能把 notes 中的 ID 当作
  已完成因子接入。
- R24 forward packet schema 和 PIT hash/timestamp validation 存在，但 observation
  runtime 与 target adapter 没有实现；当前状态明确为
  `pit_contract_validation_only_no_observation_or_orders`。
- 通用 target-weight mapper 不识别 R24 route label，paper readiness 也未做 adapter
  preflight。由于 R24 历史门失败，本轮不为 R24 建 adapter；该缺口由通过新研究门的
  successor 作为 P0 重新实现，并逐会话证明研究 target ledger、运行时 target、signal ID
  和 intent hash 一致。
- M01 仅 4 次 override，合计 realized policy value `-0.1307`，0/4 折为正、0/4 折胜
  D01、1/4 折下界覆盖达标；M02 零 override，精确等于 D01。正确标签没有弥补特征中
  缺失的增量信息，因此禁止在相同历史数据上继续 R25 变换。
- 当前仍为 `workflow_pass=true`、`research_pass=false`、
  `llm_contribution_pass=false`、`paper_ready_pass=false`。

### 3.10 已有知识和数据证据

可以继续使用的证据：

- SEC 年度产品文本可形成随时间变化的公司网络，而不是永久行业标签；
- 已验证客户/供应商关系存在延迟信息传播假设，但经典结果不保证现代长仓净 Alpha；
- 注意力研究支持约 3-10/10-20 会话的有限生命周期并要求反转保护；
- 新闻叙事因子和 LLM 新闻分数有外部研究候选证据，但必须用本地 PIT packet 验证；
- Stanford 2026 AI Index 支持把算力、存储、网络、散热、电力和数据中心作为当前
  seed 链，IFR 数据支持把机器人零部件、视觉、运动控制、集成和应用作为另一 seed；
  这些是经济活动证据，不是股票收益证据；
- 专题 ETF 历史研究提示热门主题可能在拥挤和高估阶段推出，因此主题热度不能直接
  等同于做多信号。
- 2023 年《ESG news spillovers across the value chain》报告客户/供应商链上的冲击可在
  数日内延迟扩散，支持 R23 要求 source-bound 经济关系和有限生命周期；该论文是
  ESG 特定样本，不证明 AI/机器人主题、R23 阈值、Alpha 或 Paper readiness。

仓库证据入口：

- `reports/harness/source_cards/us_event_seeded_theme_stock_r10.jsonl`；
- `reports/research/iterations/mom_event_seeded_theme_stock_r10/knowledge-scout.json`；
- `reports/research/iterations/mom_event_seeded_theme_stock_r10/stage-d-development-report.json`；
- `reports/research/knowledge/index.json`；
- `open_composer/research/factor_library.py`。

当前能力边界：

- `market.alpaca_bars` 可用于当前真实价格；
- `events.sec_filings` 已注册为 approved，`.env` 已配置真实联系格式的
  `SEC_USER_AGENT`；NVDA、PLTR 共 20 条 live filing 的 acceptance、fetched、
  first-seen、visible 字段已验证完整。R23 当前锁仍不把这些测试记录计入 forward；
- Alpaca 官方文档声明新闻历史可回溯至 2015，但历史下载不证明 decision-time
  first-seen，R11 只允许从 collector 启动时向前计数；
- Alpha Vantage key 未配置；GDELT 和现有新闻数据仍是 trial/fixture；
- 没有历史真实 PIT 文本，因此禁止历史 LLM Alpha、历史新闻回填和事后主题重建。

## 4. R11-R22 延续的唯一研究假设

R11 只改变一个核心假设：

> 主题必须先由当时可见的 SEC/新闻语义事件和可核验经济关系形成，价格、成交量、
> 广度和波动只负责确认、排序和退出；价格相关性不得创建产业链边。

这符合“不同时间寻找不同领域”的要求：股票池和主题都可以变化，但变化必须由
decision-time 事件驱动。AI、机器人只是当前 seed，不是永久板块。未来出现新的资本
开支、监管、产品、订单、供应约束或需求冲击时，可生成新主题并让旧主题自然衰退。

### 4.1 主题状态机

1. `seeded`：出现可验证事件 packet，记录 `visible_at/published_at/fetched_at/source`；
2. `mapped`：LLM 只输出固定 schema 的实体、方向、经济关系、置信度和有效期；
3. `confirmed`：至少两只高流动性成员通过价格加速、成交量、广度和市场残差门槛；
4. `active`：3-20 会话持有，每日更新，阈值触发或每周 2-3 次计划再平衡；
5. `cooling`：扩散下降、领导者反转、拥挤或不确定性上升；
6. `retired`：到期或确认消失，不允许因后续表现再次改写历史成员。

### 4.2 经济关系类型

只允许结构化枚举：`supplier`、`customer`、`equipment`、`material`、`energy`、
`infrastructure`、`competitor`、`complement`、`application`。每条边必须绑定来源 packet；
无法判断时输出 `unknown`，不能由 LLM 自由补全事实。

## 5. 固定候选组

| ID | 类型 | 角色 | 无有效语义数据时 |
|---|---|---|---|
| R24D01 | 确定性 | 冻结的 R22 高 Beta ETF 路径核心 | USD/QQQ/TQQQ 冻结状态机 |
| R24D02 | 确定性 | 多实体经济扩散主题门，未训练模型 | 股票权重为 0，回退 D01 |
| R24M01 | ML | review-point after-cost policy value Ridge | 下界不为正时精确回退 D01 |
| R24M02 | ML | 保守 LightGBM 与 Ridge 共识 policy override | 任一模型不确定时回退 D01 |
| R24L01 | LLM 因子 | 文本到结构化事件、关系、方向、置信度和期限 | 精确退化 D02/D01 |
| R24C01 | 组合 | M02 核心加确认后的 L01 主题观察 | 回退 M02/D01 |
| R24F01 | 缺失模态 | 强制移除文本的 matched fallback | 必须逐位等于 M02 |
| R24P01 | Placebo | seed 15108 固定置换语义主题/股票映射 | 永不晋级 |

LLM 不直接输出权重、订单或晋级决定。股票卫星初始资本预算固定为 0；只有 forward
matched 对照显示 L01/C01 相对 F01/M01 有稳定增量后，才在新 epoch 预注册非零预算。

## 6. 严格执行顺序

### Stage 0：高 Beta Tier 0 基线

状态：`完成`。

验收证据：

- 路由标签可解析并逐项复现旧数值；
- 当前数据到 2026-08-03；
- target/intents/observation 最新会话为 2026-08-04；
- parity `pass`，execution substate `observation_only`；
- 未调用 broker submit API。

### Stage 1：R11-R22 历史预注册与封存

状态：`完成`。R22 已封存，禁止重跑或修改锁定路径。

在读取任何新历史收益或训练模型前完成：

- 八份 draft StrategySpec；
- schema-v2 external brief 和复用/新增 source cards；
- data、feature、label、validation、cost、benchmark、holdout 合同；
- machine-readable candidate manifest、modality-role matrix、model reuse decision；
- 固定折、purge/embargo、成本、门槛、fallback 和 placebo seed；
- knowledge build/scout/assessment；
- 每一轮都必须在执行前通过对应 pre-backtest validator；当前 R23 validator 已通过且
  没有 blocker 或 warning。

### Stage 1.5：R24 政策价值修正

状态：`完成并停止`。

- 只允许一次 lock-bound 四折开发评估；累计有效试验数固定为 `8,128`；
- D01 完全复用 R22，不改价格阈值；新增历史候选只有 Ridge M01 与 LightGBM M02；
- 运行前已更新本计划并 freeze；评估后没有按结果调阈值或重跑；
- exposed transfer holdout 仅作诊断，不能独立授予 research 或 Paper 资格；
- 历史门失败，保留结果并停止 R24 ML；不实现失败候选的 Paper adapter，不打开 transfer
  holdout，不把 R24 接入 Paper。

### Stage 2：真实 forward event collector（暂停，不是当前门）

状态：`能力验证完成，观测暂停`。Alpaca News live collector、有效 LLM backend 和 SEC
live capability 均已运行；R23 不再等待新的日常会话，SEC 测试记录也不回填旧 epoch。

最小实现，不扩建通用平台：

- 复用 Alpaca 凭据读取当前新闻，注册并评估 `news.alpaca` 能力；
- SEC collector 使用本机 `.env` 的联系标识；任何把 SEC 引入 R23 日常决策的变更必须
  新建预注册 epoch，不能修改当前 lock 后继续计数；
- 原文是不可信输入，只存元数据、必要摘录、来源 URL 和 hash；
- 每条 packet 固定包含 `visible_at`、`published_at`、`fetched_at`、source、input hash、
  prompt hash、model ID、schema version、structured-output hash；
- 第一次启动之后的 packet 才可计入 future validation；本轮不等待、不回填，也不把它们
  写成历史 Alpha 证据。

### Stage 3：M01/M02 训练

状态：`R22/R24 完成但失败；successor 尚未开始`。R22 模型只使用截至 `2025-07-31` 的开发
标签，未读取 transfer outcome；R22M01/M02 在 20 bps 下 CAGR 均为 33.82%，不替代
D01。R24 的 one-shot lock 已完成且失败；任何 successor 只有在新合同和 validator 通过
后才允许 fold-local 训练。

M01 与语义路径解耦，可以立即研究：

- 只使用 ETF 的当时可见价格/量、趋势、波动、回撤、广度、相关性和路径状态；
- 每个 fold 从零训练，purge 至少覆盖标签 horizon，再加固定 embargo；
- 线性/逻辑模型为 matched baseline，非线性模型必须稳定胜出才保留；
- 训练、数据、特征、参数、预测和模型文件全部 hash 绑定；
- M02 若靠长期降仓提高 Sharpe、但显著降低 TQQQ 上行捕获，则失败。

### Stage 4：D02/L01/C01/F01/P01 forward 对照

状态：`R23 技术接入完成、贡献未验证并暂停`。当前真实 packet 已进入同一时点 matched
输出；bootstrap 因多公司请求遇到 provider 502 而没有有效 LLM 因子，所有语义股票
权重继续为 0。该 bootstrap 不计入历史研究或本轮完成定义。

- 同一事件、同一决策时刻、同一价格快照和成本；
- D02 只使用确定性事件字段和固定关系字典；
- L01 使用结构化 LLM 字段；
- C01 使用 M01 核心和已确认主题，但当前股票预算仍为 0；
- F01 在 packet 缺失时必须与 M01 输出完全相同；
- P01 的置换 seed 在首个 packet 前锁定，placebo 若胜出则 LLM 贡献失败；
- 不因短期热点名称变化而修改规则，只让 packet 内容变化。

### Stage 5：successor 研究到 Paper-entry-ready

状态：`进行中；不启动未来会话计数`。

successor 必须一次性完成并绑定：

- target weights；
- rebalance intents；
- execution observation；
- decision receipt 和 append-only ledger 的离线 parity；
- `broker_writes=false` 的 target/intents/observation 投影；
- 至少两种订单风格、三种滑点/缺口压力、容量和 TCA 计划；
- paper safety review、harness verify、kill switch、订单窗口、重复订单和凭证范围检查。

首次完整生成只证明工作流 parity；不把稳定性、broker fill、未来语义增量或 TCA 假装
已发生。所有未验证项应明确标为下一阶段 `paper_validated`，但不得阻塞本轮到达
`paper_entry_ready`。

### Stage 6：Tier 1 Alpaca Paper 金丝雀（下一阶段，当前不执行）

达到 `paper_entry_ready` 后才可请求一次用户明确确认；本轮不等待该确认、不启动金丝雀。

前置条件：

- 未来研究资格和 matched sessions（如用户之后需要）属于新的 `paper_validated` 阶段；
- LLM/组合角色若未证明增量，保持零语义预算，canary 只能来自通过门槛的确定性或 ML
  角色；
- 最新 broker 账户、持仓和挂单同步；
- 当前已观察到的 10,235 股 TQQQ 持仓必须由用户决定保留还是在 Paper 中处理，系统
  不会自动平仓；
- 零冲突挂单、kill switch clear；
- `paper_only`、长仓、受保护限价、短有效期；
- 单笔不超过 1,000 美元，并受现有 session/total/order-count 上限约束；
- 策略 spec/receipt/target hash 一致；
- 至少一笔订单 broker accepted 后完成订单、成交或撤单对账。

## 7. 停止条件

- R11 dossier/pre-backtest 失败：不读价格、不训练；
- Alpaca/SEC packet 缺 PIT 字段：语义角色回退，不伪造历史数据；
- D02 未在 forward 对照胜过 D01/M01：股票预算保持 0；
- L01/C01 未胜 F01/M01，或 P01 胜出：`llm_contribution_pass=false`；
- R24 ML 少于 3/4 折胜 D01、3/4 折 policy value 或下界覆盖不合格、少于 8 次
  override、上行捕获低于 D01 的 95%，或 DSR/PBO 不合格：保留 shadow，不替代 D01；
- successor target adapter 未通过研究 ledger parity：不得写 `paper_entry_ready=true`；
- 任何目标权重不守恒、时间戳未来泄漏、成本遗漏或账户冲突：停止当日运行；
- 研究失败后只能新建下一迭代并改变一个假设，禁止在已暴露的 R22-R24 历史内追结果调门槛。

## 8. 验收命令

```bash
uv run oc spec validate strategy_specs/drafts/<successor-spec>.yaml
uv run oc harness plan strategy_specs/drafts/<successor-spec>.yaml
uv run oc spec capabilities strategy_specs/drafts/<successor-spec>.yaml --json
uv run oc capability test
uv run oc research knowledge build
uv run oc research knowledge scout <successor-iter>
uv run oc research knowledge assess <successor-iter>
uv run oc research iteration validate <successor-iter> --stage pre-backtest --json
uv run pytest -p no:cacheprovider tests/test_<successor>.py
uv run ruff format .
uv run ruff check .
uv run pytest
```

参数优化后必须生成 backtest forensics；杠杆 ETF/daily-open 路径必须生成 execution
reality review；任何 `paper_auto` 变更必须生成 paper safety review。真金 broker 写入永远
不在范围内。

## 9. 当前用户依赖

- Alpaca Paper 凭据已可完成 live IEX、新闻和账户只读访问，无需在聊天中提供；
- 当前 Codex-compatible provider 已通过严格 JSON 实测并产生 source-bound LLM 因子；
  不在聊天、日志或仓库记录 key；
- SEC live capability 已配置并验证；联系标识只保存在本机 `.env`，不进入 Git；
- `paper_entry_ready` 前不需要用户确认，也不运行 Paper；到达该边界后才需要用户明确
  确认 paper-only 金丝雀，并说明如何处理当前 Paper TQQQ 持仓。
- 未来会话、broker fills 和 TCA 不属于本轮交付证据。

## 10. 不做事项

- 不让并行审查者写同一研究产物或绕过主线门禁；
- 不先抽象通用 round engine；
- 不清理与关键路径无关的旧报告；
- 不重新打开或修改 R10 锁定实现；
- 不使用固定现代股票篮子解释旧历史；
- 不让价格相关性创建供应链事实；
- 不把 fixture、sample、当前幸存者池或事后新闻称为 paper-ready Alpha；
- 不把 Tier 0、研究通过、LLM 贡献和 Tier 1/Tier 2 混为同一状态；
- 不提交真金订单，不在日志、Git 或聊天中记录 secret。

## 11. 进度记录

| 阶段 | 状态 | 证据 | 下一动作 |
|---|---|---|---|
| 高 Beta runtime parity | 完成 | 67 个相关回归测试通过；旧窗口数值完全复现 | 纳入 R11D01 |
| 当前 Tier 0 基线 | 完成 | 2026-08-03 live IEX，2026-08-04 target，observation_only | 每日刷新 |
| R8-R10 | 完成并停止 | R10D01 未胜 D02，DSR/PBO/折稳定性失败，锁箱未读 | 不返工 |
| R11-R13 | 完成并停止 | 干净 SIP 路径完成；R13M01 CAGR 11.59%，高换手 | 不返工 |
| R14 | 完成并停止 | M01 CAGR 22.89%，MDD -60.83%，PBO 通过但收益/DSR 未过 | 不修改、不重跑 |
| R15 | 完成并停止 | M01 CAGR 24.33%，MDD -60.58%，PBO 0.346 | 不修改、不重跑 |
| R16 | 完成并停止 | SQQQ 慢压力态使 M01 CAGR 降到 -1.66% | 永久保留负结果，不再使用无条件 SQQQ |
| R17 | 完成并停止 | M01 CAGR 26.64%，MDD -57.06%；final dossier ok，holdout 未读 | 不修改、不重跑；机制证据进入 R18 |
| R18 | 完成并停止 | D01 CAGR 32.86%，MDD -60.96%，PBO 0.175；M01 CAGR 13.23%；final dossier ok，holdout 未读 | 不修改、不重跑；确定性 USD 证据进入 R19 |
| R19 | 完成并停止 | D01 CAGR 48.37%、MDD -64.76%、PBO 0.314；仅 2/4 折胜 QQQ，DSR 0.0274；holdout 未读 | 不修改、不重跑；路径归因进入 R20 |
| R20 | 完成并停止 | D01 CAGR 32.23%、MDD -70.57%、3/4 折胜 QQQ、DSR 0.0124；压力期错失多数反弹；holdout 未读 | 不修改、不重跑；压力期归因进入 R21 |
| R21 | 完成并停止 | D01 CAGR 43.85%、MDD -66.62%、3/4 折胜 QQQ、PBO 0、DSR 0.0255；M01 CAGR 29.17%；final dossier ok，holdout 未读 | 不修改、不重跑；慢广度归因进入 R22 |
| R22 | 完成并停止 | D01 CAGR 50.51%、MDD -64.80%、3/4 折胜 QQQ、PBO 0；上行捕获 0.7822、DSR 0.0353；M01 CAGR 33.82%；holdout 未读 | 不修改、不重跑；D01 进入零资金 Tier 0 储备，不宣称 Alpha |
| R23 八角色 Tier 0 | 技术完成、贡献未验证、观测暂停 | 有效 epoch `r23fwd_6666346d7ed7e458`；最新决策会话 2026-08-07；timer `disabled/inactive` | 保留产物，不再等待或计数 |
| Alpaca 新闻 forward collector | 能力验证完成、观测暂停 | bootstrap 81 条事件、41 条 epoch 后可见、11 个新 packet、8 个绑定候选 | 仅供未来新 epoch 使用，不回填旧结果 |
| SEC forward collector | live capability 已验证、未进入当前 R23 lock | NVDA/PLTR 共 20 条 filing，PIT 时间字段完整 | 当前 epoch 不回填；若要进入决策，预注册 successor epoch |
| R23 语义角色 Tier 0 | 技术完成、贡献未通过、观测暂停 | bootstrap 多公司请求遭 provider 502，有效 LLM 因子 0；语义资金预算 0 | 保留精确回退和负结果，不再等待 |
| R23 多实体扩散门 | 已预注册并锁定、未取得贡献证据 | knowledge assessment 与 pre-backtest 均 ok；锁定多实体关系及 3/10 注意力、5 日残差、5/20 量比、60% 广度 | 只有新 epoch 明确需要时才重新研究 |
| R24 政策价值 ML | 完成并停止 | M01 4 次 override 合计价值 -0.1307、0/4 折正；M02 零 override；DSR 约 0.03；holdout 未读 | 不修改、不重跑；不从同一历史创建 R25 |
| R24 Paper runtime | 停止、不实施 | PIT packet 合同验证存在；通用 mapper 不支持 R24 label；R24 历史门失败 | 不为失败候选建设 adapter；缺口保留为未来 successor 的 P0 |
| R1 独立高 Beta 袖套 | 完成并停止 | S1D01 CAGR 42.94%、MDD -49.16%、Sharpe 0.860；DSR 0.0286、PBO 0.8643；ML 无独立增益 | 不修改、不重跑；负结果已进入知识索引 |
| successor capability unlock | 阻塞于正交数据 | 当前 ETF SIP 面板不足以支持预计可清除累计 DSR 的新收益源；空头 carry 机制与借券数据均失败 | 先取得并注册 PIT 期货或期权能力，再创建新 iteration |
| successor `paper_entry_ready` | 未达到 | 当前无候选满足全部表现门，运行时、执行和安全工件不能为失败候选补做成功 | 新能力上的锁定研究通过后再继续前置验收 |
| Tier 1 canary / `paper_validated` | 未开始、当前不执行 | 当前 Paper 持有 TQQQ，未授权新单 | 仅在 `paper_entry_ready` 后请求确认 |

## 12. 计划变更记录

| 版本 | 时间 | 变更 | 影响 |
|---|---|---|---|
| 1.0-1.2 | 2026-08-04 02:00-07:20 UTC | 建立 R8、分层 Paper 和数据边界 | 已被实际迭代结果取代 |
| 2.0 | 2026-08-04 | 记录 R8-R10 负结果；恢复高 Beta runtime；建立 PIT semantic R11 | R10 不重置；R11 从零预注册；无订单 |
| 2.1 | 2026-08-05 | 固定八角色、动态 PIT 主题、TQQQ-like 收益和首次 canary 定义 | 防止低 Beta 或把观察冒充接入 |
| 2.2 | 2026-08-05 | 记录 R11-R14；R15 只提高已确认半导体增强态集中度 | R14 不返工；继续单假设迭代 |
| 2.3 | 2026-08-05 | 记录 R15-R17、冻结快速恢复结果并固定 R18 USD2x 代理假设 | R15-R17 不返工；R18 必须用未读 transfer holdout 验证适应性选择 |
| 2.4 | 2026-08-05 | 记录 R18 终局并固定 R19 正常态 USD100 单机制 | R18 不返工、holdout 保持 0；R19 累计试验数 8,102 |
| 2.5 | 2026-08-05 | 记录 R19 终局和 F1/F4 路径归因；固定 R20 USD 自身趋势压力覆盖 | R19 不返工、holdout 保持 0；R20 累计试验数 8,110 |
| 2.6 | 2026-08-05 | 记录 R20 终局和压力期反弹损失；固定 R21 压力期快速恢复单机制 | R20 不返工、holdout 保持 0；R21 累计试验数 8,118 |
| 2.7 | 2026-08-05 | 记录 R21 终局与慢广度恢复延迟；固定 R22 压力期双快速确认单机制 | R21 不返工、holdout 保持 0；R22 累计试验数 8,126 |
| 2.8 | 2026-08-05 | 记录 R22 终局和封存 SHA；停止历史价格调参并启动独立八角色 forward epoch | R22D01 仅作为 Tier 0 储备；语义资金 0、无订单、holdout 保持 0 |
| 2.9 | 2026-08-05 | 记录被隔离 bootstrap、当前有效 epoch、八角色 Tier 0 技术完成、live 新闻与 Paper 只读对账 | 有效稳定性从 0/5 开始；LLM/SEC 配置和现有 TQQQ 持仓继续 fail closed；无订单 |
| 3.0 | 2026-08-05 | 修复 Codex provider base URL 与新闻 first-seen 持久化；隔离零计数旧 epoch；建立新锁并产生首个有效 LLM 因子 | 新有效 epoch 从 0/5 开始；R23 只测试多实体经济扩散门；SEC 和现有 TQQQ 持仓继续 fail closed；无订单 |
| 3.1 | 2026-08-06 | R23 dossier/knowledge/pre-backtest 通过；锁定新 epoch，完成真实 bootstrap 并启用 systemd 自动采集；统一 5 日技术稳定、20 日研究资格和 30 fills 扩权门槛 | R23 从 0/5、0/20 开始；provider 502 按缺失模态记录；无订单、无回填 |
| 4.0 | 2026-08-10 | 审计产品、知识库和因子目录；复盘 R22 ML 目标错位；完成并封存 R24 after-cost policy value 评估；修复标签索引、placebo 真源和 modality/factor 合同；收紧 ML 门 | R24 `stop_price_paths`；R23 观测后来暂停；所有 Alpha/LLM/Paper pass 仍为 false |
| 4.1 | 2026-08-10 | 按用户要求停止未来会话等待；新增 `paper_entry_ready` 与 `paper_validated` 分界，更新当前失败数据、successor 边界和停止条件 | 继续新策略族研究；到达可立即开始模拟盘前停止，不运行模拟盘 |
| 4.2 | 2026-08-13 | 记录 R1 锁定失败、ML 机制诊断、知识索引修复与当前 capability gap；否决无历史借券证据的空头 carry | 不创建低价值 R2；先解锁正交 PIT 数据能力，仍不运行模拟盘或下单 |
