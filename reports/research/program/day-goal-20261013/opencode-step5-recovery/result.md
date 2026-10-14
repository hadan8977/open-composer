# Step5/T03：应收投影修复完成，新原文属性错误后停止

按 [Root恢复决定](root-v3-projection-recovery-decision.json) 完成同定义adapter修复，未改grounding-v3提示、免费模型、low或8192上限。**原631361…应收失败分类已纠正，已有四答离线接受，没有重复请求。** 此后新单位销量病例出现真实的lower_bound方向/确定性错误，按事前条件停止；bulk **0/88**，没有另送启动申请或继续prompt救援。

## 分类纠正与真实续验

原631361…中应收basis、80%/19%/93%原文事实正确；模型原答违反只允许收入比例的pct schema。既有canonical投影应把这三个字段设null。此前call_one只接了引句适配、漏掉normalize_reply，误将该adapter缺失归为须停止的事实错误。现已接入受原文约束的投影：raw basis=receivables、完整引句逐字存在且明确支持应收，原数值匹配引句才转换。收入100%/96%及其他实体/basis/年份/引句不改；raw错误、原停用/latch及18次消耗完整保留，追加 [映射谱系](projection-reclassification.json)。**canonical通过不等于模型原答schema通过。**

原四份v3答复均以原文离线复核并通过canonical验收，0新调用。继续真实请求如下：

| 片段 / 调用 | 实际结果与原文判定 |
| --- | --- |
| 表头 `0000065270-26-000031` / `324fba5d…` | 41%集团与10.9%匿名、2026及exact lower_bound正确；未凭冒号表头生成10%群体。引句仅首字母大小写不同，由通用适配锚定完整逐字原句，原quote失败保留，其余字段不变；原文通过。另一个major-customers依存记录无pct/年份，支持于风险句。 |
| 匿名历年 `0001437749-26-031175` / `80471414…` | 2026的29%/24%/22%确数、2026/2025个体超过10%约束均有原文支持，无投影。2026阈值记录是冗余证据，不能数成第四个独立客户；匿名记录不认证永久身份或独立客户数量。 |
| 命名多年 `0001193125-14-321759` / `9dd4e36e…` | 240秒无最终JSON，241.243秒含清理后结束。原生元数据227.9秒时assistant未完成、reasoning part已开始，没有最终text/usage回执；不是已判的语义失败，费用回执未知。保留部分事件与原生session。 |
| 单位销量 `0000863894-14-000010` / `944f7403…` | 23.934秒正常返回。unit-sales pct已为null；应收12%经合法投影变null，canonical schema0issue。**四处lower_bound=true仍不受原文支持，原文验收失败。** |

最后一例原答与canonical都把USAID及Sekunjalo的2013“less than10 percent”标成lower_bound=true，把2012明确25%/20%也标成true。原T03定义只在“more than/over/at least”且没有确数时为true。这里分别是上界和确数，字段应为false；**没有手改四个布尔值使其通过。** 全原文、raw/canonical、四条违规与原指令见 [新失败证据](projection-source-failure.json)。runner结构性退出0不能代替原文验收。

原14冻结样本保持：6例原文+canonical通过、1例真实属性失败、1例技术超时未决、6例未再调用（包含3个原冻结留出）。留出没有替换或用于改prompt；没有新增SEC/其他来源。发现真实错误后没有继续质量请求，也取消了原本只在时间足够时进行的一次延后超时重试，不能以未测样本或旧版本结果补足14例pass。

## 资源、时钟与原生断点

此次真实新增4请求，累计 **22/120**，质量 **22/32**，bulk **0/88**；算术剩10quality/98total，但失败关闭后不自动续用。共享880/5h当前占22，ledger8175行，原DS8153行前缀SHA核对不变。旧18次、推理前失败、旧原答和原停用证据均保留。新增3个完成回执均cost=0；新超时1个及历史超时2个回执未知，不能宣称全部已核零费用。没有付费、充值或凭证绕行。

唯一恢复时钟在setup前固定 **09:41:35.846016–10:11:35.846016 UTC**。原45分钟、30分钟、v3的45分钟三份时钟字节不变。最后provider终态 **09:59:33.726711 UTC**，距恢复开始1077.881秒；随后只有source失败锁存、原生checkpoint/定向验证和报告收尾，静态收尾记录为10:12:48.227813 UTC，晚于窗口72.382秒，单独保留这段实际耗时；没有后续provider请求，不把收尾视为延期或重置。bulk45分钟时钟未创建。

对真实240秒超时，已确认owned CLI子进程清理后为0。根据未完成生成的原生证据，将后续单请求上限改为360秒，仍取实际剩余阶段时间减5秒；不改8192或提示。单位销量例随即正常完成；发现源错误后没有重打超时病例。延迟/token、实际四条capped命令和代码hash见 [命令与延迟](projection-commands-and-latency.json)。全部请求使用fresh memory admission、原900MiB capped、nobody/清空环境/公共scratch/--pure、tools审批且不授予；无tool事件、repo/secret传出。

raw、canonical和每次projection/quote变化均保留；旧坏call ID未删除，对原AR的canonical接收另有checksum/Root权威。新Gov源错误按call ID隔离，不计done；quality也不会因其JSON结构有效而跳过这份失败记录。原生pending8例保留（1失败、1超时、6未测），本次失败准入已关闭。

## 验证、教训与结论

[定向验证](projection-final-gate-check.json) 通过：source-supported应收投影、错误数值/basis/引句不投影、首字母引句适配不改事实、旧AR raw拒收与canonical谱系并存、新源坏call不计done、quality/bulk锁存入口均退出20且0请求、不变ledger/输出/四份时钟、bulk时钟不存在。ruff format/check、py_compile通过；原三脚本及DS failure SHA不变。before、各实际调用代码版本及最小diff见 [manifest](projection-recovery-manifest.json)、[diff](implementation.diff)。中间版本以逆向窄差异重建并逐一匹配真实call代码SHA，未伪造旧运行配置。

本任务 [README](README.md) 已记录教训：**原始事实错误、原答schema错误、确定性canonical投影必须分开。** 原文正确且已定义的schema投影属于adapter工作；JSON投影后合规仍可能有真实属性错误，后者不能手工改答强迫pass。没有重写全局规则。

**终局：adapter技术修复已验，但完整质量条件未通过，本轮集成v3自动抽取配置停用。** 原始/新事件、映射、账本、旧/新去重和未完成断点均留在isolated research lane，共7个跨版本不同accession的原文接受结果，不能称14例通过或已恢复bulk。DS仍parked；Hadan/Modal/生产、经济准入、PIT/永久证券身份/集团收入分母、订单不动，收益/Sharpe为N/A。下一步由Astra最终读新方向属性错误与分类纠正作判断，不自动重试、另调prompt或续期。此结果只限本轮配置，不证明Step5/LLM普遍无用。

[完整结果JSON](projection-recovery-result.json) · [现态](current-state.json)
