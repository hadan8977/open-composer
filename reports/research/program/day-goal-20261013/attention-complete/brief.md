# 完整任务：Attention联合因子与交易模型的真实市场收益价值

task_id: DAY3-ATTENTION-COMPLETE
review-partner-state: reports/research/program/day-goal-20261013/pressure-event-return/current-state.json

投资问题：联合学习可交易残差和成本后交易政策，是否比同输入的两步PCA/条件因子+同一交易模型增加可实施净收益？这是一条新模型完整任务；不延续DLSA匿名扰动收益，也不因论文Sharpe高就默认其能完成账户高绝对收益目标。

来源已实际打开：Epstein/Pelger/Zhang《Attention Factors for Statistical Arbitrage》https://arxiv.org/html/2510.11616v1。复用research-frontier/new-sources.json的attention/attention_independent来源卡、来源快照与counterevidence，按需要读完整正文/附录和实际实现。Root复核Table2：K30净Sharpe2.28，净年均9.52%、波动4.18%；成本为5bp*换仓L1+每天1bp*短头寸，资产grossL1=1。不是20k账户年化100%。作者500股/39特征+中位数与RF成79维/8年滚动；去past-return特征后弱化，说明必须检验信息与联合架构贡献。2026独立实现https://bsic.it/attention-factors/是对方自做结果，200股/18特征/短窗/全样本流动性筛选等差异不能冒称忠实复现。先核正式作者代码/公开数据和较新修订，再实际打开要用的实现。

完整路径：
1. 用已有目录和小manifest核对可用的真实日期、证券身份、收益/39特征、作者输入和许可，定位可忠实复现层。不要再完整清点全仓或重训匿名DLSA。原数据无法得到时，可设计明确区分的真实可交易应用层，但须有经济同义理由与独立review，不为了数据方便改成ETF动量或把当前成分回填历史。
2. 建立完整科学问题和有界候选：联合Attention vs同特征两步方法、同交易政策PCA、简单残差基线；price-only/full-information、缺失回退/因果时钟和placebo；因子/训练容量、足够样本跨度和小账户执行为三条有信息深度轴。原30epoch/滚动8年/LongConv对照按来源绑定，不能用一个tiny模型失败否定。实际fit计数须把折/seed/对照算清；不铺笛卡尔网格，不要求填满预算。
3. 经独立完整plan review和真实门后，在现有已批资源内连续实现/验证/训练/评价。输出源表复现差异及真实市场应用的毛净收益、同风险增量、资金/整股/借券和连续亏损恢复特征。源路径受阻但应用已就绪可独立推进；两层证据不得混用。
4. 若确无合法真实输入，不把继续堆代码/匿名fit当完成；交具体无法解决的依赖、已有可用替代及是否值得投入的判断。研究优先级由可信潜力与实际差距共同决定。

既有知识入口：research-frontier/new-sources.json、root-selection.json；DLSA/root-three-fit-acceptance.json只读方法对照和已见范围，不接管它；equity-role/root-result-acceptance.json说明风险缩放收益不能冒充均值模型贡献。

共同执行约定：这是一个完整研究问题，不是调研/计划/修复三个短任务。你负责原文、真实输入、设计、独立审查接续、实现、必要修复、实测与投资解释。先读使命最新条款、task-owned-research方法和本brief；不通读旧会话。默认6.1Sol/xhigh/full-access，首次实际回读一次；真实容量失败才按Astra/high回退，不轮询。Root负责重大取舍和最后判断。

新经济假设先完整计划与独立review、实际direction/campaign/iteration/knowledge/能力等适用门；未过门不拟合/回测。优先复用新鲜来源/标准模块，允许同语义修复和预算内技术调整自主做完。独立review由另一完整任务owner对本计划独立完成（从review-partner-state读取实际owner），作者不能自审或代写批准。审查请求/修订直接在双方接续，不逐文件找Root；凡普通实现问题，由原owner修并核对。若现有资源无法开展独立review，明确交接原任务而非自批或增开代理。

来源复现、同义输入重建和交易应用分别留证据。必须考虑真实证券身份/历史资格/退市、可见时点、成熟标签/截断、同风险同信息同成本基线、至少三个有经济信息深度点、安慰剂/缺失回退、借券/融资/滑点/整数仓位/资金占用和适用家族统计。固定候选/分区/试验上限后运行；旧已见窗口不能洗成新OOS，旧失败与消耗不重置。组件可有价值，但不能把IC、匿名数据模型效果或毛收益叫成本后账户Alpha。最终约2万美元、美股可买证券、无人值守目标、长期亏损1–2个月需降级、高净绝对收益与Sharpe并重；不为目标自行提高杠杆或下单。

资源是任务上界，不是预批准经济启动：本地数值最多2 CPU-core-hours、单job<=900MiB/单核/现有freshmemory/capped，项目保留500MiB。元数据/公开文献与代码前置可做，新增非行情公开文献/代码下载<=64MiB/40请求，零自动重试；不下载权重/大行情包冒充已准入。计划通过后如数值资源不够，优先已有Hadan且freshready，必须先核Chinco原F05回传lane，不能抢其任务或混用C:\paseo目录/50GiB。云仅原$25共享免费cap内、本任务最多$1、现有budget工具验证确有未分配余量后才可保守预约，原Chinco/DLSA预约不动，无新付费。经济数据的正常已授权只读能力可在独立计划明确请求/响应/资源边界后使用；不读印密钥，不额外购买数据。需要更大真实研究深度时给完整投入理由，而非小烟雾测试否定方向。

首轮持续工作窗口8小时，2小时常规汇报只读现有state，不通知Root每个阶段；跨日深度优先。若原始输入有不可解决许可/PIT/报价缺口，记录已经核实的缺口和最有价值可行替代，不修通用平台、不重复已证阻塞；不能把纯计划称整个任务完成。最终交付原始/可复算数值、同输入成本后比较、失败/累计预算、是否继续/暂缓/可部署判断；workflow/research/ML/LLM/paper分开。无当期有效结果N/A。全流程一个owner，常规修复继续；只完整结果或真正需改变研究/预算的阻塞结束通知，正常终局只原生finish，不再显式重复Root消息。不得派更多执行子代理/新定时器/LLM轮询/经纪商写/生产修改。
