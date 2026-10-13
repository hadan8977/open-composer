# 完整任务研究方法（机主2026-10-13）

## 当前状态与适用性

每次启动先读取 `reports/research/control/owner-compute-hold.json`，判断其最新暂停字段与机主明确恢复范围；不能仅按旧 `status` 或历史训练许可推断允许执行。当前 `research_paused=true`：全部研究、训练、代理、自动研究与报告生成暂停。缺失、不可读或相互冲突时不自动启动，记录具体缺口。只有人类明确限定的方法维护可在该限定范围完成；本次实施与发布不恢复研究、报告、调度、设备探测或目标运行。

本方法替代旧 high/max 执行默认、固定周期 Astra 值守和普通修补逐次经济审查。保留历史正文、原有效合同与预算、失败、冻结候选/标准、累计曝光和未见 OOS；不更改科学定义、资金/设备/订单授权。旧研究 cron 入口退役，未来恢复也不重新启动固定 Astra 研究轮。三条既有 Sol 报告入口仅在对应报告范围明确恢复后沿用原 cadence：约2小时整轮、北京时间09:00日报/周日周报与既有写作时段；正常邮件和单一专用会话路线保持。暂停记录和路由是运行部署依赖，不是本次发布已启动工作的证明。

## 问题、收益用途与投入

最终目标是整个账户滚动12个月扣成本后大几十至100%以上净收益，同时追求账户/组合扣成本后目标 Sharpe >2、有意义绝对收益及约2万美元拟定实盘的可执行性；这是前瞻研究目标，不是已实现结果或收益承诺，不覆盖旧实验冻结门。研究美股可买到的品种，包括商品 ETF，以及原授权允许的股票/ETF 多空、期权和加密现货；研究适用性不等于新实盘或订单许可。日内/HFT 是可部署收益方向，要核验嘉信接口、行情/延迟、订单和资金限制，不提前宣称支持。

先选择可信已发表/分享成果、原实现、发表后表现、独立复现与反证，再决定忠实复现、本地适配或创新。来源强而本地暂未重现时，研究者应找决定性差异并解释继续深挖的价值；数据现成、包数或一次便宜失败不能决定科学优先级。来源缺失时先完成允许的准备并写出具体缺口，不虚构 source fetched、input ready、准入或成功。

研究对象可以是策略、因子、数据、择时/风险、模型或执行。Astra 在 brief 中说明它改变什么投资决策、怎样接入组合、预期收益角色、匹配基线和投入理由。方向性收益比较同风险净增量；低相关贡献要检验共同日期组合边际和压力共损。负收益保险与动态集中可以研究，比较收益、回撤/压力损失、波动、资本/杠杆、亏损持续性和恢复时间，不能把低相关亏损线直接晋级。约30%回撤只是既有比较参照，超出它的研究方案不构成改旧风控或扩大仓位授权。

深度优先于日/周数量，可信复现和扩展可跨日推进，交每日新增实证里程碑。24小时是规划周期，非任务寿命、常醒 Astra 或研究截止；周目标仍与机主共同制定。既有日 goal 与未完成清单保留，不能因 turn 结束、跨日或治理交付结算经济完成，也不无限续开任务直到赚钱。

## 角色与一次完整交付

角色模型只在 [research-agent-roles.json](../config/research-agent-roles.json) 维护；这里描述责任，具体启动从配置取值。当前 Astra/xhigh 是决策角色，写详细完整任务、重要取舍和最终判断；Sol/xhigh 是完整任务 owner，从来源/输入准备、实现、普通修复、实测到解释和可接续交付负责；报告 Sol/xhigh 复用现有 target，整理真实证据，不代替科研判断。重要独立科学 review 由独立 Sol/xhigh reviewer 做，不能与执行作者或最终 Astra 判断混同。

使用 [完整 brief 模板](../prompts/research-task-brief.template.zh.md)。brief 一次给全问题、科学边界、证据、真实输入与允许分区、候选/深度、匹配比较、现成命令或缺失入口建设、总预算/已用量、原生断点、验收及退出分支。Astra 提供充分判断依据，Sol 可在已批科学定义与累计预算内智能调整技术路线、实现、分片、普通恢复和实验顺序，不反复申请逐文件许可。材料不齐时以实际解除的依赖和具体缺口交付，不把准备标经济结果。

新经济假设、关键科学定义（信号/标签/模型角色/候选选择/验证分区/交易时点/成本/成功标准）或超批准范围工作，先适用独立深度计划 review 和原生门。普通路径、接口、日志、同语义 bug 修复与预算内恢复留给 owner，按相关差异/结果验收；不逐次送 Astra 或重开经济审查。晋级和重要科学判断保留独立 review，最后由 Astra 根据证据作继续、暂缓、`not_at_depth` 或严格否定判断。

## 科学验收与原生入口

执行前绑定真实原文快照、原实现/负结果、数据许可与 PIT 可见时间、永久证券身份/成分、价格卫生和允许分区，忠实复现与本地适配分别记证据。可调参数/多模型冻结候选 manifest、累计试验暴露、选择规则与未见窗口；campaign 依其既定 development/OOS 边界执行，不以新版本抹除已见数据。

计划至少三个改变经济信息的深度点并解释适用性，例如样本/状态跨度、数据/特征信息、模型容量/拟合深度或执行机会；邻近参数和成本档不充数。便宜检查只能提速或支持加深；否定需忠实源复现、足够深度、事前预算耗尽、功效、简单基线/安慰剂、真实成本和组合边际充分，不足写 `not_at_depth`。同输入、同风险、同成本比较，原适用 benchmark family 与 DSR/PBO/SPA 等家族统计要求保持。

AI/ML 或新模态声明决策角色、训练截止/数据/特征/标签/提示 provenance，控制先验记忆污染与数据泄漏，检验 quant-only、modality-only、combined、missing-modality、placebo、校准/覆盖和确定 fallback；不适用项给原因。模型自述、内部机制文献和流程通过不等于金融增量；负实验和版本修正保留。

复用现有 `oc research direction-check <path>`、`oc research iteration validate <iter_id>`、适用的 `oc research knowledge assess <iter_id>` 和 `oc research campaign validate <campaign_id> --stage <stage>`，以及数据/执行/晋级门。冻结输入与计划先接受，再分配经济计算。入口缺失就明确建设工作与验证，命令未知写待核对；文档列出门不代表实际通过。保留 `StrategySpec` 语义与既有 Python/NautilusTrader 路径，不另造执行/报告/恢复平台。

结果分别给出 `workflow_pass`、`research_pass`、`ml_contribution_pass`、`llm_contribution_pass`、`paper_ready_pass`；无当前有效评估时收益/Sharpe/模型增量为 N/A。说明成本、样本、功效、匹配净增量和执行限制，区分历史回测、shadow、模拟订单和实盘状态。论文收益、准备、治理变更和已排队通知均不记为本期经济成果。

## 持续任务、事件与交接

一个问题一个逻辑 owner，先核对本地/远端实际 owner 和进程，独立完整包按实际槽位与资源准入并行。只读任务小状态，必要时追溯原证据；不重复全仓、旧会话或大报告上下文。每任务复用一个小 state，可放在原任务目录，不强制新 schema：保存任务/owner 与权限出处、brief/review/结果路径、实际进程ID与已核验状态/时间、原生 checkpoint/已完分片、累计数据/计算时间/费用/请求/模型fit与trial、剩余预算、失败、阻塞/触发条件和下一动作。大表与日志仍在原证据文件。

**agent turn 结束不等于进程结束，更不等于经济完成。** 运行继续时留下可接续 owner、真实 process/checkpoint 和受管交接；接手先核实旧进程/输出，不能以会话 idle、断网或通知成功推断停机、保存或完成。沿用现有 runner 的退出码/状态文件、Paseo 原生完成通知和已有脚本事件；代理完成通知还须核对实际进程与产物。现有 `scripts/hadan_availability_watch.py` 只提供设备状态变化证据，不证明实验完成，暂停期不启动或探测它。若没有可靠进程事件，登记明确缺口和一次必要人工/owner核验入口，不临时建设守护平台。

等待与机器观察由既有脚本/事件处理，不能生成反复 LLM 轮询、定时 Astra 值守或无限 self-restart。**只在真实结果、实质阻塞、科学/输入/评估定义变化、预算/权限变化或机主请求决策时通知 Astra**；一次消息给出证据、影响、建议和决策点。同一状态不重复提醒，普通修补与进度留在 state，由 Sol 报告读取。Astra 不需要等待所有长进程的常驻 turn；任务归属和累计记录不因协调 turn 结束消失。

## 资源、授权与运行配置

恢复后启动一次显式设置角色 provider、`settings.modeId="full-access"`、`settings.thinkingOptionId="xhigh"`；回读真实 provider、effective thinking，并在接口提供时核对 `currentModeId` 和 `runtimeInfo.modeId`。提示文字不替代设置；字段不支持/不可读就记录真实限制，不声称激活已验证。已有 schedule 不支持 thinking 设置时，实际启动后一次设置/回读即可；本次不为验证而新建/运行代理。

保留 Linux 约500 MiB机主余量、现有 kernel/project/job 与 agent caps，使用现有 memory admission/capped；并发取实际槽位与资源/累计预算准入较小值。只用已有有效许可和剩余额度，失败/中断也累计；模型 load/download 需当前 manifest，不复活撤回实验。Modal 仍受原免费预算及 timeout admission，无新付费或新 provider。DS parked，等机主新可用 token 和明确恢复，不探测、不换 key/provider、不重复催决策。

Hadan 仅通过 Paseo，在线且 fresh remote preflight 成功、worker=ready、usage_ok=true、实际使用严格<50 GiB，全部输入/输出/临时/缓存在 `C:\paseo`。机主可随时 pause/关机，日历不等于 ready；不唤醒/resume/hard-on 或绕本机开关。复用原生 checkpoint 和已完分片，固定实验/种子/版本，回连 fresh ready 先查旧 job，原生续跑或同定义重跑累计记账；可恢复中断保留唯一完整点，核验回传/完成或明确放弃后清理，失联不声称已保存或停机。本次不探测 Hadan。

既有模拟盘独立按原授权运行，研究暂停不声明其停止；资金、纸/实盘、续签与生产权限不扩大。live paper 代码沿原独立 worktree/审查/交互合并路径。正常报告仍走既有配置和专用 hub，报告恢复不自动恢复研究。hub closed 时暂停期不重建；明确恢复后由 Sol 触发器核对唯一有效 hub，必要时一次创建 Sol/xhigh/full-access hub，初始 prompt 已含本事件和 hub 入口，同步两既有 route，不嵌套触发、不向 closed 的旧协调会话循环发送。不能定位有效决策 owner 时在报告写明具体缺口。

## 方法演进与最小验证

模型映射、提示和方法可以随完整任务质量、耗时/费用、实证与能力升级调整，写清问题、替代和可核验改善，优先删除重复监督；不以模型自评或报告数量判断效果。普通方法维护按范围、差异、角色/暂停/链接一致性验收；代码按受影响行为检查，生产规则仍有效。重要科学变化保留独立 review 与 Astra 最终判断，资金权限需机主明确范围。任何改法均不伪造数据、不清零消耗、不解封已看 OOS、不改旧科学标准。

关联入口：[Astra任务决策](../prompts/continuous-alpha-lead.zh.md)、[Sol完整执行](../prompts/continuous-alpha-execution.zh.md)、[日报/周报写作](../prompts/owner-daily-weekly-writer.zh.md)、[报告触发](../prompts/owner-report-dispatch.zh.md)、[专用报告会话](../prompts/owner-report-hub.zh.md)。运行需现有 `config/owner-reporting.json`、`config/autonomous-report-target.json`、`reports/research/control/` 状态及相关脚本；这些路径为已有运行依赖，若发布基线未含文件，不能据此启动。本文关键责任与边界自包含，历史本地规范按任务需要读取。
