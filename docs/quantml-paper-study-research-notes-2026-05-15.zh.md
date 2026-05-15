# 论文学习报告研究笔记 (2026-05-15)

**输入**: `reports/quantml_agent_papers_2026-05-14/` (上游新增 commit `6529a46`)
**研究目的**: 把这份新报告读完,提炼对 Open Composer **后续路线/产品决策**的可执行启示
**口径**: 只复述论文事实部分照搬作者结论;但「报告 → Open Composer」的对齐与新需求由本笔记独立判断
**前置阅读**: `AUDIT-REPORT.md` (架构盘点)、`docs/audit-fix-plan-2026-05-15.zh.md` (短期修复)

---

## 1. 这份报告是什么

| 维度 | 数值 |
|---|---|
| 主体文档 | `quantml_agent_paper_study_report.zh.md` (753 行 / ~67k 非空白字符 / 174 KB) |
| 同名 HTML / PDF | 已生成,便于离线阅读 |
| 覆盖论文 | **19 篇**,arXiv 全部可核验,已下载 PDF 与抽取文本 |
| 时间分布 | 2025-11 至 2026-05 (近 7 个月窗口) |
| 主题章节 | 5 大类 + 技术依赖图 + 未来研究方向 + 实践检查清单 + 术语表 + 逐篇附录 |
| 配套文件 | `paper_inventory.csv`(元数据)、`claims_traceability.md`(结论可追溯)、`source_post_extraction.md`、`unresolved_mentions.md`、`references.bib`、`scripts/{collect_sources,generate_report}.py` |

报告**坦诚没有找到完整的 61 篇清单**,只覆盖截图中可解析、可联网核验的 19 篇,这是非常诚实的写法 (符合仓库一贯的 evidence-first 文化)。

---

## 2. 19 篇论文一句话索引

> 用「定位 + 当前 Open Composer 已有 / 缺什么 / 距离落地多远」表示

### 2.1 LLM Agent 与多智能体交易 (6 篇)

| 论文 | 一句话定位 | 与 Open Composer 的距离 |
|---|---|---|
| **AlphaCrafter** (arXiv:2605.05580) | Miner-Screener-Trader 三 Agent 全栈闭环,把因子搜索 ↔ 制度感知 ↔ 风险约束执行接成回路 | OC 已有 capability registry + strategy lifecycle + paper_auto;**缺**「Miner Agent」生成因子的环节 |
| **TrustTrade** (arXiv:2603.22567) | 用「选择性共识」替代多数投票,根据语义/数值/时间一致性给信号动态加权 | OC 的 `review/llm.py` 仅单 Agent ReviewCard;**缺**多 Agent 共识聚合层 |
| **BlindTrade** (arXiv:2603.17692) | 匿名化 ticker 后再让 LLM 评分,验证「真理解 vs 记忆叙事」 | OC 暂无 LLM 选股,但**反事实评估协议**这个思想完全可以加进 `research/` 模块 |
| **Expert Investment Teams** (arXiv:2602.23330) | 角色细粒度 > 粗粒度,任务拆得越细越好做消融 | OC 的 `.agents/skills/` 已有 7 个 skill (capability-evaluator, strategy-designer …),已经在做细粒度;**缺**消融指标 |
| **HiveMind** (arXiv:2512.06432) | DAG-Shapley 给多 Agent 工作流做贡献归因,DAG 剪枝省 80% LLM 调用 | 与 OC `.agents/skills/` 体系强相关,可以做「skill 贡献归因」的 V2 |
| **OOM-RL** (arXiv:2604.11477) | 用真实资金亏损作为对齐信号,而非语言奖励或离线 benchmark | 与 OC 的「paper_ready_pass ≠ workflow_pass」 价值观一致,但 OC 不做实盘;OC 的对应物是「严守 promotion gate + paper readiness 多门」 |

### 2.2 强化学习组合优化 (4 篇)

| 论文 | 一句话定位 | 与 Open Composer 的距离 |
|---|---|---|
| **SNAPO** (arXiv:2605.06570) | 神经策略 + 可微模拟 + 伴随反传,一次 reverse pass 给一堆敏感度 | OC 当前 `engines/` 是离散事件 + Nautilus,**离可微模拟很远**;短期不必上,但敏感度报告思想可借鉴 |
| **MetaRL-GBWM** (arXiv:2605.02300) | MetaRL 预训练 + 目标型财富管理,新客户 0.01s 出近最优策略 | OC 是单用户量化研究台,**与 GBWM 业务场景不重合**,记忆即可 |
| **MACE** (arXiv:2603.29086) | Almgren-Chriss + 平方根冲击重建 RL 环境,**成本模型会改变 RL 算法排名** | **强相关**:OC 的 `costs.commission_pct / slippage_bps` 是常数化的,需引入容量/冲击曲线 |
| **SBCA** (arXiv:2605.01384) | Cross-modal BERT + Actor-Critic,把文本+价格融合做组合优化 | OC 的 LLM feature 走 `feature_packets`,跨模态融合是另一条路,**短期不必上** |

### 2.3 自动化因子挖掘 (2 篇)

| 论文 | 一句话定位 | 与 Open Composer 的距离 |
|---|---|---|
| **FactorEngine** (arXiv:2603.16365) | 程序级因子表达 + 知识注入 + 逻辑/参数/LLM/计算 separation of concerns | OC 已有 `expressions.py`,可以朝 FactorEngine 方向扩展为「Miner」 |
| **Hubble** (arXiv:2604.09601) | AST 沙箱 + 白名单算子 + 双通道 RAG + 公式相似度去拥挤 + 零运行时崩溃 | **最直接借鉴对象**;OC 的 `expressions.py` 应增加 AST 白名单 + factor 多样性约束 |

### 2.4 多模态金融预测 (4 篇)

| 论文 | 一句话定位 | 与 Open Composer 的距离 |
|---|---|---|
| **SEMF** (arXiv:2603.27321) | 小波频谱图 + ViT + 外生变量 Transformer,双向交叉注意力 | OC 的 `indicators/` 主要是经典 TA,**频域是空白**,可以加,但优先级低 |
| **Uni-FinLLM** (arXiv:2601.02677) | 共享主干 + 模块化任务头,统一文本/数值/基本面/视觉 | 与 OC 哲学不同 (OC 是 spec-first 而非 model-first),不必模仿 |
| **History Rhymes** (arXiv:2511.09754) | 把宏观指标 + 新闻情感嵌共享空间,检索「历史最像现在的制度」 | **直接对接** OC 的 `capabilities/registry.yaml` 中已有的 `macro.fred_series` 和 `news.alpha_vantage`,可做一个 `oc strategy regime-search` 子命令 |
| **Acoustic Camouflage** (arXiv:2604.14619) | 财报电话会声学特征反而让尾部风险召回从 66% 掉到 47% — **多模态反例** | OC 不做声学,但「新增模态需先证边际贡献」这条原则要写进 `feature_packets` 的接收 gate |

### 2.5 评估基准与可靠性 (3 篇)

| 论文 | 一句话定位 | 与 Open Composer 的距离 |
|---|---|---|
| **PolyBench** (arXiv:2604.14199) | Polymarket 实时快照 + CLOB + 新闻流,7 个 LLM 中只有 2 个有正收益,MiMo-V2-Flash CWR 17.6% | **可借鉴评估协议**:时间锁定 + 真实订单簿,但 OC 不做预测市场 |
| **QuantCode-Bench** (arXiv:2604.15151) | 评 LLM 生成可执行算法策略 — 语法 → 回测 → 真实交易 → 语义对齐四级门 | **直接对接** OC 的 `oc compile pine-strategy`、`oc strategy workflow.verify`;可以把 OC 的 verify 流水线做成开放评测集 |
| **Reliable Evaluation** (arXiv:2603.27539) | 提出 12 系统分类法 + 协调优先假设 + Coordination Break-even Spread (CBS) | **本报告的方法论底座**;OC 的 AGENTS.md 已经在做相同的事 (workflow_pass / research_pass / llm_contribution_pass / paper_ready_pass 分离) |

---

## 3. 报告说了什么超越「论文综述」的事

### 3.1 一个清晰的「三层框架」

报告反复回到这个抽象 ([§1](../reports/quantml_agent_papers_2026-05-14/quantml_agent_paper_study_report.zh.md)):

```
信号层  ── 模型能否从价格/基本面/新闻/宏观/语音/频谱/链上数据中提出有预测意义的特征
   ↓
决策层  ── 信号如何进入组合,如何受风险预算/换手/冲击/制度约束
   ↓
系统层  ── 多 Agent 协作,谁发现/谁筛选/谁执行/谁复盘/谁担责/如何防回声室
```

这与 Open Composer 现有的 `信号生成 → 风险/容量约束 → 纸面交易闸门 → 复盘` 的产品骨架几乎一一对应。**说明仓库的设计哲学和近期 SOTA 方向是同步的。**

### 3.2 「研究通过 ≠ Alpha」五连否定 ([§10 实践检查清单](../reports/quantml_agent_papers_2026-05-14/quantml_agent_paper_study_report.zh.md#10))

报告在结尾抛出一句很硬的话:

> 研究通过不等于 Alpha,通过回测不等于可交易,通过 Agent 共识不等于事实,通过多模态融合不等于信息增量,通过代码可运行不等于策略正确。**每个「等号」都需要单独验证。**

这恰好是 Open Composer 的 `AGENTS.md` 第 18 行已经规范化的:
> Separate `workflow_pass`, `research_pass`, `llm_contribution_pass`, and `paper_ready_pass`; do not promote a workflow pass as Alpha or paper readiness.

**两份文档的语义高度重合**。报告把分级原则讲给了「外部读者」,AGENTS.md 把分级原则压成了「Agent 必须遵守的规则」。

### 3.3 引入了 OC 当前未明确的 3 个新检查项

报告 §10 的清单提到 3 个 Open Composer **目前没有明文落地**的检查:

1. **匿名化反事实验证 (BlindTrade)** — 同一信号跑「真实标识 / 匿名 / 随机映射 / 行业保留匿名」四组实验,看信号差异
2. **Coordination Break-even Spread (Reliable Evaluation)** — 多 Agent 协调带来的信号增益是否覆盖实际价差和协调成本
3. **AST 白名单 + 公式相似度去拥挤 (Hubble)** — LLM 生成因子时,候选必须通过 AST 安全检查 + 公式相似度惩罚,避免拥挤模板

下文 §5 的「建议」会把这 3 项映射成具体 issue/feature。

---

## 4. 报告本身的质量评估 (作为审计员的视角)

### 4.1 优点

- **诚实声明覆盖范围**:不假装找到 61 篇,只覆盖可核验的 19 篇,unresolved_mentions.md 把没纳入的截图明示出来 — 透明度 A
- **可追溯性**:`claims_traceability.md` 把每条核心结论挂回原论文,符合 OC 的 evidence-first 价值观
- **保守口径反复重申**:每篇论文都有「报告采用保守口径:论文报告的数值只说明在作者设定的数据/窗口/成本/基准下成立,不能直接外推到实盘」的统一免责;**比大多数券商研报严谨**
- **结构化产物全套**:PDF、抽取文本、笔记、引用、生成脚本都齐 — 可复现
- **配 BibTeX**:`references.bib` 让后续学术写作能直接 cite

### 4.2 可改进点 (写给报告维护者的建议)

| 项 | 建议 | 优先级 |
|---|---|---|
| **正文重复度高** | 每篇论文的「研究问题 / 创新与边界 / 与论文网络」段落里都嵌入了同一句「从没有上下文的读者角度看,论文真正关心的是『传统金融机器学习假设在 Agent 时代哪里失效』…」的样板话。读到第 5 篇就会发现是模板填充。建议把「公共背景段」抽成 §1 末尾,正文不再重复 | 中,影响阅读体验 |
| **数据被截图二次转述,数值有失真风险** | `BlindTrade Sharpe=1.40±0.22`、`Uni-FinLLM 67.4% vs 61.7%`、`OOM-RL Sharpe=2.06`、`AlphaCrafter 在 CSI 300 / S&P 500 显著超越基线` 等数字均「截图称」,不是直接从抽取文本复核。建议在 paper_notes/ 内为每个数字标 `verified: yes/no/截图转述`,避免误传 | 中 |
| **没有给 Open Composer 的具体集成 backlog** | 报告止于「实践检查清单」,但**没有 → Open Composer 当前哪个模块对应 / 缺什么 / 下一步怎么做**的转译。本笔记 §5 补这一段 | 高 (本笔记目的之一) |
| **`AlphaCrafter Sharpe`、`OOM-RL Sharpe=2.06` 等论文性能可被噪声驱动** | 报告已经在 §10 反复警告,但建议在 `paper_inventory.csv` 增 `performance_skepticism_level: high/med/low` 字段 | 低 |
| **未来研究方向写得偏综述风** | §9 的 6 条都是好的研究方向,但缺一个**「假如我们(Open Composer)只能做 3 件事,做哪 3 件」的 narrowed-down 排序** | 中 (取决于报告定位) |

### 4.3 可信度速评

- **核心结论**: A (出处都能挂回 arXiv,所有 PDF 在 `pdfs/` 都有)
- **数值引用**: B+ (多处「截图称…」,可再校对)
- **方法论判断**: A (与 Reliable Evaluation 等高质量 survey 一致)
- **对 Open Composer 的可操作性**: C+ (报告本身没显式写,需要本笔记 §5 补全)

---

## 5. 对 Open Composer 的可执行 backlog (我的判断,非报告原文)

按 ROI 排序 (高 → 低)。每条都标了 [文件] / [新模块名] / [大概工作量]。

### 5.1 立即可做 (1-3 天,纯设计/规则)

#### B1. 把「五连否定」写入 promotion gate 报告模板
- **来源**: 报告 §10
- **文件**: `open_composer/research/promotion_report.py` (扩展)
- **实现**: 在 `promotion-report` 输出中加一段「五个等号检查」,把现有 `workflow_pass / research_pass / llm_contribution_pass / paper_ready_pass` 渲染成显式的 5×PASS/FAIL 表
- **价值**: 低成本就让 OC 的报告读起来更像 Reliable Evaluation 推荐的风格

#### B2. 在 `feature_packets` 接收 gate 加「新模态必须证边际贡献」检查
- **来源**: Acoustic Camouflage 反例 + 报告 §6.5
- **文件**: `open_composer/feature_packets.py`
- **实现**: 接收一个新 source 时,要求 manifest 里附带 `single_modality_baseline` 和 `marginal_lift`,否则该 packet 只能走「研究」标签,不能进入 `paper_auto` 路径
- **价值**: 防止 Acoustic Camouflage 式的「越多模态越差」

### 5.2 短期 (1-2 周,需要工程)

#### B3. 加 `oc strategy blind-test` 子命令 (BlindTrade 协议)
- **来源**: BlindTrade
- **文件**: 新建 `open_composer/research/blind_test.py` + 加入 CLI
- **实现**:
  - 输入: 一个 strategy spec + 一个 LLM-feature 用到的 ticker 列表
  - 输出: 4 组对照实验 (真实标识 / 完全匿名 / 随机映射 / 行业保留匿名),并比较信号一致性
  - 加入 `promotion-report` 作为可选 gate
- **价值**: 把「LLM 是不是在记忆 ticker」做成可机检的一道流程,比写在 docs 里有约束力

#### B4. 给 `expressions.py` 加 AST 白名单 (Hubble 协议)
- **来源**: Hubble + FactorEngine
- **文件**: `open_composer/expressions.py`
- **实现**:
  - 显式列出允许的 numpy/pandas 函数 + 算子集合
  - 拒绝 `os.*`、`subprocess.*`、`__import__`、`eval`、`exec`、`open`、网络相关 import
  - 用 `ast.NodeVisitor` 在编译时拦截
  - 拒绝时给清晰的「为什么这个表达式不安全」错误信息
- **价值**: Open Composer 之后只要支持 LLM 生成因子,就一定会面对这个问题,不如先打底

#### B5. `MACE`-启发的成本敏感性矩阵
- **来源**: MACE
- **文件**: `open_composer/research/cost_sensitivity.py` (`promotion-report` 里 `--cost-slippage-bps` 已支持类似思想,但只是单维)
- **实现**:
  - `oc strategy cost-grid <spec> --slippage 0,5,10 --commission 0,1,3 --impact-model linear,sqrt,almgren-chriss`
  - 输出二维或三维敏感性表格 + 排名变化
  - 在 `promotion-report` 增加「成本模型变化下排名是否稳定」子检查
- **价值**: 让「algorithm rank changes when cost model changes」(MACE 的核心结论) 变成 OC 的硬指标

### 5.3 中期 (1-2 月,需要新模块)

#### B6. `oc strategy regime-search` (History Rhymes 协议)
- **来源**: History Rhymes
- **依赖**: `capabilities/registry.yaml` 里已有的 `macro.fred_series` (FRED) + `news.alpha_vantage` 已可走通
- **实现**:
  - 把宏观指标 (CPI / 失业率 / 收益率曲线) + 新闻情感嵌入共享向量空间
  - 给定当前窗口,检索历史 K 个最相似制度期
  - 输出: 相似度、当时市场表现、当时策略表现 (如果有 backtest)、失败案例
  - 在 `promotion-report` 末尾附「当前最像哪段历史」一小节
- **价值**: 直接对应 History Rhymes 在 OOD 测试中 PF=1.18 的核心机制,且 OC 的 capability registry 完全够用

#### B7. 「贡献归因」做给 `.agents/skills/`
- **来源**: HiveMind + Expert Investment Teams
- **文件**: 新增 `open_composer/research/skill_attribution.py`
- **实现**:
  - 离线模式:在 paper_ready 通过的策略集合上,做 leave-one-skill-out,记录每个 skill (capability-evaluator, strategy-designer, …) 对最终 promotion 通过率的边际贡献
  - 用 DAG-Shapley 近似 (HiveMind 公开了思想,无需复现整套)
  - 报告写到 `reports/skill_attribution/`
- **价值**: 当 `.agents/skills/` 数量增长后,可以诊断哪些 skill 长期低贡献,反向优化

### 5.4 不建议追的 (避坑)

| 论文 / 思想 | 不建议原因 |
|---|---|
| Uni-FinLLM 的统一主干 | OC 是 spec-first,不是 model-first;走另一种范式 |
| MetaRL-GBWM | OC 不做财富管理,业务场景不重合 |
| SBCA 的 BERT 主干 | 增加显存与运维复杂度,与 OC 的 file-first 哲学冲突 |
| OOM-RL 「让 Agent 真亏钱学习」 | OC 明文「实盘券商写入 out of scope」,触线;且报告自己也不建议「实盘烧钱训练」 |
| SEMF 的频谱特征 | 优先级低,在文本 / 宏观 / 因子还没饱和前不必加新模态 |
| SNAPO 的可微模拟 | 与 NautilusTrader 离散事件路径冲突,选型已定 |

---

## 6. 战略反思:发挥 Open Composer × LLM × Codex 的长处,弥补三者的短板

> 这一节是本笔记的核心增量。前面 §1-§5 是事实复述与 backlog;这一节是「为什么这些 backlog 是对的」的战略推理,以及 Codex/Claude Code 在执行时应当采取的具体姿态。

### 6.1 三方各自的长处与弱点

#### OC 产品的长处 (从审计 + 论文对照得出)
1. **file-first / CLI-first**:所有产物 (signal_logs / orders.jsonl / kill_switch_events.jsonl / reports/*) 都是可 grep / diff / 版本化的文件。这天然解决了论文 §10 反复要求的「provenance、可重放、可审计」。
2. **StrategySpec 是单一真值源 + Pydantic `extra="forbid"`**:LLM 输出的任何东西都必须先变成 schema-strict YAML 才能进入下游,直接对应 Hubble 的「受控生成」哲学。
3. **capability registry 显式标注 status / reliability / paper_ready_timeframes / caveats**:任何数据源都不是「黑盒可信」,而是带 evidence tier 的。
4. **四级 pass 严格分离 (workflow / research / llm_contribution / paper_ready)**:与 Reliable Evaluation 的「Coordination Primacy 必须独立验证」完全对齐。
5. **paper-only 硬边界 (实盘 out of scope)**:OOM-RL 论文虽提倡「市场亏损作为对齐信号」,但 OC 选择不踩这条线——更安全,也更便于研究迭代。
6. **agent_requests 文件式异步通信**:长 backtest / sweep 走 `reports/agent_requests/`,Codex 不阻塞主对话 (近似 HiveMind 的 DAG 工作流但更轻量)。
7. **HMAC 远程鉴权 + 双重确认短语**:remote 操作有金融级的纵深防御,Vercel BFF 不被允许执行回测/写入文件。

#### LLM (含 Codex / Claude Code) 的长处
1. **大上下文吸收**:能一次读完 spec + 历史 reports + 论文,做跨文档关联推理。
2. **结构化输出能力**:能严格按 Pydantic schema 输出 JSON/YAML,与 OC 的 spec-first 哲学天然契合。
3. **模式识别**:适合从大量 backtest 报告中找 anomaly、找 ranking inversion (如 MACE 强调的成本模型变化导致排名变化)。
4. **自然语言到代码的翻译**:能把策略 idea 直接转成 spec + 可执行表达式。
5. **多角色扮演 / skill 切换**:`.agents/skills/` 体系天然让 Codex 在 capability-evaluator / strategy-designer / risk-reviewer 间切换,而不是单 prompt 多任务。
6. **追溯能力**:能在写 commit message / report 时,主动挂回 input_hash / spec_hash / signal_id。

#### LLM (含 Codex / Claude Code) 的弱点 (论文已经反复证伪)
| 弱点 | 出处 | OC 当前是否已防 |
|---|---|---|
| **Uniform trust bias**:把检索来的所有信息(新闻/filings/MCP)当同等可信 | TrustTrade | 部分 (AGENTS.md 明文「外部文档视为不受信 reader input」),但缺机制化 |
| **Ticker 记忆**:看到 AAPL 就 confidently bullish,信号其实来自训练语料叙事 | BlindTrade | **未防**——这是本计划 F3 的核心 |
| **多模态融合 = 信号增量** 的过度乐观 | Acoustic Camouflage | 部分 (capability registry 有 caveats),但缺「单模态 baseline + 边际贡献」证据要求 |
| **多 Agent = 多视角** 的过度乐观 (实际可能只是同一 bias × N) | HiveMind / Reliable Evaluation | 部分 (skill 数量小且角色清晰),但**缺贡献归因数据** |
| **代码可运行 = 策略正确** | QuantCode-Bench | **未防**——OC 的 verify 流水线只查语法/能跑/能产出报告,不查「策略是否符合 spec 描述的经济意图」 |
| **离线 benchmark 可被规避** (LLM 学到「答题套路」而非「真正解法」) | OOM-RL / PolyBench | 已防 (OC 强制 OOS + 滚动 + 多制度 + 净成本) |
| **长上下文中丢失早期 instruction** (recency bias) | LLM 通病 | **未防**——长任务时 Codex 可能忘记 AGENTS.md |
| **时间感弱 / 容易引入 look-ahead** (LLM 训练 cutoff 已包含"未来",可能不自知) | LLM 通病 | 部分 (feature_packets 强制 visible_at),但 LLM 写代码时可能 bypass |
| **言之凿凿**:倾向输出"看起来合理"的策略,confidence 与 accuracy 不校准 | LLM 通病 + TrustTrade | 部分 (review card 有结构),但**没有 confidence 校准机制** |
| **跨 session 无记忆**:Codex 容易重发明轮子,与已有 capability 重合 | Codex 通病 | 部分 (CLAUDE.md / AGENTS.md 写明规则),但 Codex 进项目时可能不读 |

### 6.2 对策矩阵:用 OC 的 gate 抵消 LLM 的弱点

这是本笔记最关键的一张表。每一行是「LLM 弱点 → OC 该用哪个 gate / 新机制压住」。本计划 §5 的 B1-B7 大部分都是这张表的具体落地。

| LLM 弱点 | OC 已有机制 | OC 还缺什么 (= backlog) | 对应 backlog ID |
|---|---|---|---|
| Uniform trust | AGENTS.md 不受信原则 | review card 显式打印每条 evidence 的 source + 置信度;不同 source 不能直接相加 | (建议在 B1 顺手做) |
| Ticker 记忆 | (无) | BlindTrade 协议:同信号跑「真实/匿名/随机/行业保留匿名」4 组对照 | **B3** |
| 多模态过度乐观 | capability registry caveats | 接收新模态 packet 时强制带 `single_modality_baseline + marginal_lift + missing_robustness`,否则只能进研究标签 | **B2** |
| 多 Agent 自我放大 | skill 数量小 (7 个) + AGENTS.md 显式分工 | DAG-Shapley 贡献归因数据;低贡献 skill 离线降级 | **B7** |
| 代码可运行 ≠ 策略正确 | verify 流水线 (语法 / 能跑 / 能产报告) | promotion-report 增「五连否定」表格,显式区分 5 个等号 | **B1** |
| LLM 写危险/有 look-ahead 的代码 | (无,只在 review 时人看) | `expressions.py` 加 AST 白名单 + 拒绝 `os/subprocess/__import__/eval/exec/open/网络` import | **B4** |
| 长上下文 recency bias | (无) | Codex 每次开始长任务前必须 `cat AGENTS.md && cat CLAUDE.md`;长任务开始前打印 5 条核心 invariant | (写进 §6.4 工作纪律,不是代码 backlog) |
| 时间感弱 / look-ahead | feature_packets visible_at | feature_packets 加 lint:任何 feature 引用未来 timestamp 立刻 fail | (建议在 B2 顺手加) |
| Confidence 不校准 | review card 有结构 | 强制 LLM 在 review card 给出「主要风险来源」+「如果错了最可能的 3 种原因」 | (review card schema 扩展,可放入 B1) |
| Codex 无记忆 / 重发明轮子 | CLAUDE.md / AGENTS.md | 计划文档自带「Codex 工作纪律」一节;CI 强制 `make verify` | (写进本笔记 §6.4 + 统一计划) |
| 单调成本假设 (论文 MACE 警示) | costs.commission_pct / slippage_bps 是常量 | `oc strategy cost-grid` 子命令做成本模型敏感性矩阵 | **B5** |
| OOD/制度迁移弱 (History Rhymes 警示) | 已有 macro.fred_series capability | `oc strategy regime-search` 检索历史最像现在的制度 | **B6** |

### 6.3 发挥三者长处的「正向组合拳」

矩阵之外,还有 4 条「OC + LLM + Codex 一起赢」的组合拳,本计划 backlog 里隐含但值得显化:

1. **spec → code → test → report 的全链路 LLM 化**
   - Codex 已经能把策略 idea 转成 spec、再 generate 表达式;OC 已经能把 spec 跑出 backtest + report
   - 把 promotion-report 的 5 个等号检查全部 LLM 可读 → Codex 能根据 report 自动判断「这个策略卡在哪个 pass」并改 spec 重跑
   - 这是 OC × LLM 最具规模化潜力的飞轮

2. **agent_requests 异步把 Codex 从「同步执行长任务」中解放出来**
   - 任何 ≥5 分钟的 backtest/sweep 都该走 `oc agent request-create`,Codex 主对话立刻返回
   - 完成后另一个 Codex session 跑 `oc agent request-list` 就能看见结果
   - 与 HiveMind 的 DAG 工作流同构,但实现成本只是「几个 jsonl 文件」

3. **capability registry + Codex 的"工具感知"**
   - Codex 写新策略前必须 `oc capability test`,而不是凭训练记忆决定数据源
   - 任何新 capability 必须先在 registry 加 fixture + min_score + caveats,这强制 Codex 把"我以为可以用"变成"已经验证可以用"
   - 直接呼应 Reliable Evaluation 的"工具维度"分类

4. **paper readiness gate 让 LLM 的「言之凿凿」无害化**
   - 即使 LLM 输出了高度 confident 的策略,只要它没过 6 重 paper readiness gate,就不会下任何单
   - 这是 OOM-RL 思想的安全实现:不靠真实亏损惩罚 LLM,而靠 gate 让 LLM 的错误自然被拒绝

### 6.4 Codex / Claude Code 在 OC 上的工作纪律 (写给后续 Codex 执行者)

> 这一节是任何接手 Codex session 在开干前必须读的。

1. **每个新 session 第一件事**:`cat AGENTS.md && cat CLAUDE.md && cat reports/readiness/readiness.md` (如果存在)。无论上下文多长,长任务里每 ~30 轮重新打一次,对抗 recency bias。

2. **任何写代码前**:`uv run oc capability test` (确认依赖能力可用)、`uv run oc spec validate <path>` (确认 spec 合法)。**不要凭训练记忆决定用哪个数据源**。

3. **任何 backtest/sweep > 5 分钟**:走 `uv run oc agent request-create --title ... --prompt ...` 异步,**不要在主对话里 sleep 等结果**。完成后用 `oc agent request-complete` 回写。

4. **任何要写文件的操作**:绝不写到仓库根之外;路径必须先经 `Path(...).resolve().is_relative_to(root.resolve())` 验证。

5. **任何 LLM feature**:必须经 `feature_packets.write_feature_packet`,带 `visible_at / published_at / fetched_at / source / input_hash / prompt_hash`。**不要在策略代码里直接 `openai.chat.create`**。

6. **任何 PR 前**:`make verify` 必须全绿。失败先 `uv run oc doctor` 看环境。

7. **任何 commit message**:必须挂 spec_hash / signal_id / signal_log 路径,而不是「调整若干」「优化策略」。

8. **如果你 (Codex) 不确定一个数据/数字的来源**:**不要写下来**。改 prompt 让上游用 `oc agent request-create` 异步去取真实数据,在结果回来前先 stub 出接口。

9. **如果你写到 `--allow-paper-orders` 或 `--allow-paper-auto`**:**停下来要求人工确认**。这是触线动作。

10. **如果 ruff 报警告**:别用 `# noqa` 一抹了之。先想想是不是 schema 漏了字段。OC 全代码库的 ruff lint 是干净的,任何新警告都是回归。

### 6.5 「不要做」清单 (避免被论文风潮带偏)

不是所有论文方向都值得追。以下清单 Codex 应该主动拒绝任何"我们也加一个"的提议:

| 不做 | 理由 |
|---|---|
| 自建一套完整的执行引擎 (与 NautilusTrader 并行) | AGENTS.md 明文反对;NautilusTrader 是目标 |
| 把 LLM 接到实盘券商 | OC 明文 paper-only;OOM-RL 提倡的"实盘亏损训练"踩线 |
| Uni-FinLLM 式统一主干模型 | OC 是 spec-first 不是 model-first,范式不兼容 |
| MetaRL-GBWM 式财富管理 | 业务场景与 OC 不重合 |
| SBCA 式 BERT 主干 | 显存/运维成本与 file-first 哲学冲突 |
| SEMF 式频谱特征 | 在文本/宏观/因子还没饱和前不必加新模态 |
| SNAPO 式可微模拟 | 与 NautilusTrader 离散事件路径冲突 |
| Vercel 端跑回测/pytest/dashboard build | AGENTS.md 明文反对 |
| 任何绕过 capability evaluation 的"我先试试" | 直接违反 §6.4 第 2 条 |

---

## 7. 与上一份「审计修复计划」的衔接

`docs/audit-fix-plan-2026-05-15.zh.md` 解决的是**当前能跑但跨 OS 不齐**的工程债;本研究笔记的 §5 backlog 是**功能扩展**。两者无依赖,可并行:

```
P1 路径修复 ──┐
              ├── P2 安全硬化 ──┐
              │                  ├── 跨 OS 全绿 (可发布)
P3 命名/CI ──┘                  │
                                  │
B1/B2 设计层 (低成本) ────────┐  │
                                ├── ──── 进入 paper readiness 的 2.0 报告模板
B4 AST 白名单 (短期工程) ─────┘     │
                                     │
B3 BlindTrade ───┐                   │
                 ├──── 与 ────────┤
B5 MACE 成本网格 ┘                   │
                                     │
B6 regime-search ──── (中期) ────┘
B7 skill 归因   ──── (中期)
```

按这个排:把跨 OS 修干净 → 把报告新检查项写进 promotion gate → 再做 BlindTrade/AST/cost grid → 最后是 regime-search 与 skill 归因。

---

## 8. 一句话总结

报告本身是**高质量的、保守口径的、结构化交付物**(评级 A-),与 Open Composer 的 evidence-first 文化对齐。它最有价值的不是论文综述本身,而是把当前 SOTA 量化 Agent 研究里**已经被反复证伪的几个失败模式** (统一信任 / ticker 记忆 / 多模态噪声 / 协调成本未覆盖 / 代码可执行 ≠ 策略正确) 清晰列出。Open Composer 应该把这些失败模式直接转成 promotion gate 里的硬检查项 (即本笔记 §5 的 B1-B7),把综述沉淀成产品规则。

---

*Notes by Open Composer auditor, 2026-05-15. 论文事实部分来自原报告与 arXiv 摘要;对 Open Composer 模块映射与 backlog 排序为本笔记独立判断,需与项目维护者再对齐。*
