# DLSA真实市场方法续行：实际输入到匹配成本感知实验

机主明确要求DLSA继续深入；2026-10-14独立方法审计已接受其正向方法发现、区间反证与真实输入缺口。你持有完整研究问题，不能以写完新缺口报告结束。Root负责最终科学/资源选择，你负责来源/实际输入/实施/实测/解释及普通修复；逻辑owner跨turn保留。优先Sol6.1/xhigh/full-access，实际不可用沿既有Astra/high fallback，不轮询切换。

## 问题与已知证据

在具备真实证券和回报含义的近年数据上，成本感知残差路径模型相对同输入简单残差策略、同结构毛收益训练，能否提供稳定且有意义的净增量？它不是部署审批，不必先齐备逐笔成交/ETB/整股现金账户；证券episode、公司行动/退市终值、历史资格与防泄漏仍影响方法结果本身。

先读 reports/research/program/research-method-audit-20261014/independent-review.zh.md 第5节和关联原证据；docs/research-mission.zh.md、docs/task-owned-research.zh.md。旧DLSA已接受12 fits/9600updates，原31fold作者锚及两匹配fold保留。fold00 cost-aware方法episode+6.456% vs gross-trained−2.056%，fold10−1.574% vs−3.654%；H5追加反证保留。不自动补余12匿名fits，匿名/扰动数据不产生真实市场账户Alpha。

关键已有入口：
- reports/research/program/day-goal-20261013/dlsa/deepening/root-H5-result-acceptance.json
- reports/research/program/day-goal-20261013/dlsa/deepening/real-market-B-feasibility.json
- reports/research/program/day-goal-20261013/joint-daily-method/minimum-connected-input-contract.json
- reports/research/program/day-goal-20261013/joint-daily-method/independent-scientific-input-review.json
- reports/research/program/day-goal-20261013/real-market-input-bridge/及acquisition/已接受实际输入
- reports/research/program/day-goal-20261011/source-led-selection/dlsa-reproduction-plan.json及root-dlsa-source/input-package/
- reports/research/program/day-goal-20261011-2/dlsa-matched-training/已接受模型、loss、projection代码
- data/sip/daily、minute的已有本地/Drive索引及旧delisted backfill；不能全量扫云盘或重复下载。

## 完整推进

1. 检查已知资产的真正可构建路径，交付实际dated security-return/action/terminal/feature连接与样本，不把CIK当shareclass，不按未来存活/收益删证券，不用当前赢家模拟历史。问题按实际cohort和持仓暴露定义，无须先修复全部16000+symbol，不硬绑500股/8年/09:45。允许复用并完成已有范围内数据修复/版本化重建，限本任务隔离产物，不能改生产或原始数据。
2. 比较有权限的原IPCA/已有完整连接导出与明确的价格PCA残差适配。新实质选择先查原文/公开实现和反证；优先复用已核来源。PCA适配须保留原论文差异，不能叫原IPCA数值复现；不预先因方便选最弱输入或把ETF动量替代原问题。
3. 一次形成完整、可执行的方法计划：共同证券、信息、投影、日历、训练/验证/近期段、成本和基线；原则上先比较确定性残差基线、同CNN毛训练、同CNN成本感知训练。必要的模型容量、持有政策或对照由决定性问题论证，不机械扫参数。明确近期数据曝光状态；2023–2026不是默认未见OOS。保留历史原门，方法收益不可冒充paper就绪。
4. 初期可用连续分数仓位和有根据的来源/实际成本范围，计算换手与保本成本；固定订单费用归因、成本影响政策两种问题分开。20bp不是所有方法实验默认真实成本。股票整股、借券/fill/结算及真实账户规模留到有信息价值后补，不作为首个方法实验的全套前置。不因N/A自动结束母问题。
5. 新科学定义按适用独立计划审查，冻结完整输入/候选/实际预算，再实际执行原生门、训练、成本后匹配结果、解释。保留同一owner，不拆成没人负责的准备子卡。当前未获新训练资源分配或经济准入；完整实际规模/资源方案随科学包一次交Root，之后预算内技术恢复自主。原已接受可复用部分不重做11项、来源检索或全套hash。
6. 若一个真实输入出口不通，比较同价值的已有路径并落实下一步，不反复交同一句not_ready；只有不可解外部权限/新费用/重大科学取舍才合并交Root。目标是首个可运行真实方法包及其最终完整结果，首次有意义里程碑争取6小时内，必要深度可跨日，时间不是新的秒级kill门。

## 资源与并行

现有数据/代码的轻量核对、必要隔离数据准备和公开原文研究已授权；不触发新bulk行情请求/权重下载/付费。实际重计算、训练及新来源范围先按完整科学包确定，不把旧未清算reservation当新余额。共享Modal$25硬上限、原账本/失败/预留保持；不用新provider或付费额度。Local fresh memory admission，默认单核900MiB，保留机主约500MiB及正常模拟盘的9533075101 bytes磁盘预留；不要建立双份巨型panel。原匿名训练实测RSS约28.36GiB，不假定16GiB Hadan能照搬；如更合适实现使用Hadan须fresh ready/usage_ok/C:\paseo/<50GiB/尊重pause与原生checkpoint，不在本任务恢复旧匿名job。

Root、Martin、HF之外你为第三完整owner；当前最大4活跃槽含Root，暂不派子代理。需要独立审查时用既有reviewer并实际让出slot，不造第五个。只最终结果或实质决定通知一次；无heartbeat/LLM轮询。一个current-state.json保存实际进程、科学/输入状态、历史消耗与接续，不建平台。旧DLSA、HF、Martin、纸盘产物/owner均不覆盖，无订单。
