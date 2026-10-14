# T03 Step5 接续：raw 与 canonical

本任务保留三种不同判定：

1. **原始事实错误**：错认客户、漏掉应抽关系、编造比例、错误分母/年份，或引句不支持属性。确定性适配不得补答案或隐藏此类错误；按准入条件停用。
2. **原答schema错误**：模型原答不符合约定输出，例如basis正确为receivables、原文应收占比准确，却仍把比例填在只允许总收入占比的pct字段。保留raw与其失败，不能称模型原答schema通过。
3. **确定性canonical投影**：既有T03定义明确要求receivables的pct为null。仅raw basis正确、逐字引句明确支持应收事实、原数值吻合引句时执行；完整raw和映射谱系保留，其他实体、basis、年份、收入数值不改。

此前v3仅接入引句边界适配而遗漏原normalize_reply，错误把可由已授权schema投影处理的应收字段问题分类为须结束科学任务的事实错误。Root离线复核给出新决定：技术修复、离线接收已有四答、不重复调用、原14样本条件不变。原停用结论/latch和所有18次消耗保留在before-projection-recovery，追加纠正而不改写模型历史。

当前准入见root-v3-projection-recovery-decision.json；现态见current-state.json，原生输出在data/features/economic_links/_llm_step5_research。最终解释见result.md。此处只记录本任务教训，不改全局规则或经济/PIT准入。

引句可做既有精确引句适配：仅移除非原文终止句号，或仅纠正首字母大小写，且完整结果逐字存在于原文。原答的quote校验失败照实保留；不做模糊匹配、改数字/实体或补不存在的句子。表头续验的大小写案例见projection-quote-case-repair.json。
