# I-20261004-02：GitHub 近期热门 vibe trading / AI 交易项目系统调研

- 任务码：T-20261004-76（协调码 R1004-T76），执行：Sonnet 5.5 high，2026-10-04 17:50–18:10 UTC。
- 状态：**主体完成，三处文件齐全。未完成项**见第 6 节：X 渠道不可用（`twscrape` 未安装，按边界不装包），Reddit/HN 没搜到原帖；多数卡片读的是 README 和 CHANGELOG，没有逐个审代码；nof1 官网 leaderboard 现为 404。
- 星数、创建日、推送日、许可证：全部来自 GitHub REST API（未认证），2026-10-04 17:50–17:58 UTC 取数，每行的精确取数时间在 JSON 的 `stats_fetched_utc`。机器上没有 `gh`。
- 已避开重复：`I-20260919-03/-06`（工作台界面）、`I-20260922-03`（巨人普查）、`rl-llm-trading-evidence-2026-09-30`（RL/LLM 证据）里已有结论的项目，这里只写 **9 月 19 日以后的新变化**和对我们 A–E 工作线的借鉴点。
- 原文快照：`reports/research/intel/sources/vibe-trading-2026-10-04/`（README、CHANGELOG、关键源码片段、网页文本；每个文件 ≤200 KB，Vibe-Trading README 超长，已截断并在文件尾注明）。

## 1. 一页结论

**总判断**：这一批项目里，没有一个给出"扣成本、截止日后、可核验"的盈利证据。能核验的实盘只有 nof1 Alpha Arena（零样本 LLM，多数亏）。**值得借的不是"AI 选股"，而是围绕它的工程防呆件**：时间合同、衰减监控、可核对的报告、实盘下单路径的失效模式清单。这些项目的最新版本（Vibe-Trading 0.1.16、TradingAgents 0.5/0.6）把大量精力花在修前视、对账、失效关闭上，正好是我们的 A4（实盘通道）、E（流程）、B（报告）的短板。

### 最值得借鉴的 5 件事

| # | 借什么 | 来源 | 放进哪条线 | 工作量 | 预期价值 |
|---|---|---|---|---|---|
| 1 | **实盘下单路径的"失效即关闭"测试清单**：做空数量符号（`qty` 是绝对值，方向在 `side`，卖空曾被记成正敞口，导致越卖越放松总敞口上限）；限价单按"报价与限价较差者"算名义额；券商读失败≠空仓；杀开关遇到错误响应不能记成功；杀开关"只触发一次"的锁要落盘并绑定停机事件（重启不重复平仓）；`client_order_id` 确定性生成以便重试去重；纸盘与实盘凭证分开、各自绑定主机；mandate 含标的/单笔/总敞口/杠杆/日上限/自动到期 | Vibe-Trading README 2026-08-25、08-27、08-29、09-06 条目及 Alpaca 连接器章节 | **A4**（T-20261004-72） | 小：约 1 天，把每条改写成验收测试和清单项 | **高**：这些都是会直接亏钱的缺陷，对方已在真实使用中踩过 |
| 2 | **衰减/失效状态机**：`created→benching→active→monitoring→decayed→disabled`，每个指标按健康/警告/衰减/危急四档，"最差指标定总信号"，转移需要连续 N 次检查（active→monitoring 连续 3 次警告，monitoring→decayed 再连续 2 次，恢复只需 1 次健康），基线取初始或前 5 次定期评估 | `HKUDS__Vibe-Trading__decay_thresholds.md`、`src/strategy_store/decay.py` | **A1/A5**（前向记录、提议里的"失效信号和减半规则"），**D** | 小：规格半天，代码 1 天，接 `reports/owner/live-track.json` | **高**：把使命文件要求的"适用状态、有效期、失效信号、退出规则"从文字变成可测试的监控。注意他们的阈值（IC 比 0.7/0.5/0.3、Sharpe 1.0/0.5/0）是未校准的经验值，必须用我们自己的前向 z 和跟踪差重新标定 |
| 3 | **时间合同**：(a) 数据按"当时已公开"供给，无法定日期的来源在过去日期的运行里**拒绝提供**而不是悄悄给今天的数（TradingAgents：SEC EDGAR 按申报日、重述前读首次披露值；Yahoo 财报按期末日定日期所以过去运行被"withheld"；FRED 曾用今天的版本泄漏修订值）；(b) 每张 run card 写 `model_training_cutoff`，窗口早于截止日自动标"可能暴露"，未设置按暴露；严格因子评测用 `--training-cutoff` 把样本外段放在截止日之后；(c) **截断不变性测试**：freqtrade `lookahead-analysis` 与 Vibe-Trading 的 300 行哨兵测试，思路相同——用截断数据重算信号，应与全量数据在同一时点的信号一致 | TradingAgents README 与 CHANGELOG 0.4–0.5；Vibe-Trading README；freqtrade 文档 | **E**，并直接服务 `llm_contribution_pass` 与 T-20261004-54 PIT 审计的后续 | 中：约 2 天（能力登记表加"可得性语义"字段；run card 加模型截止日；一个通用的截断不变性 pytest 夹具）。本仓库现有的 `tests/test_ml_no_lookahead.py` 只覆盖 ML 特征管线，别的信号生成器是否有同类测试**没有审计过** | **高**：与 9 月 30 日证据简报一致——大模型截止日前的回测都是样本内，干净窗口是 2025-01 起 |
| 4 | **数字必须带出处，审计无证据时失败而非通过**：Vibe-Trading 0.1.16 的"落地检查"让模型声明每个数字的角色（观测/推导/提议/引用/计数），再对照本次会话的工具证据核对，核对失败的数字被剔除而不是整篇拒绝；run card 只有在保存的 CSV 与指标一致时才引用该指标，并记录回测执行记录的哈希；报告审计器曾"没有任何证据却报 PASS"，已改为无证据即失败 | Vibe-Trading README 2026-09-27、09-29、09-06 | **B1/B2**（轮次汇报落盘、日报）、**E** | 中：2–3 天，在 `owner_digest` 前加一道"声明-出处"核对：每个数字带文件路径和哈希，脚本复核后才发邮件 | **高**：机主 10-01 看不到证据；我们已踩过"转述代理结论但它没过自己的安慰剂"（记忆 2026-09-24）。这是把"汇报给出证据"做成程序检查 |
| 5 | **防篡改的前向时钟 + 决策结算**：AgentStockBenchmark 把代理代码合入**只追加登记表**，在次日行情出现前拿到服务器端时间戳，信号只能看到 t-1 收盘截断的快照，代码出错按中位排名处理；TradingAgents 把每个决策记入日志，持有期满后按同期区域基准结算，写入已实现收益、超额与一段反思，并在报告头写明结算失败 | `xsunsim__AgentStockBenchmarkResults.md`；TradingAgents README"Persistence"和 CHANGELOG | **A1**（拼接前向记录） | 小：约 1 天——每日信号文件做哈希链，哈希同时写入外部可核对的位置（邮件日报或 Drive 副本），结算脚本按持有期对基准 | 中高：让前向 z 能声称是真样本外。**不抄**它的"不计成本、借券费和冲击"的计分，这是它的弱点 |

另有几件二级借鉴（价值中，不挤进前五）：Vibe-Trading Run Detail 的 **Positions 页**（毛敞口饼图与净敞口条形图并列，行业净暴露条形图，直接对应 D1 的半导体集中度和 B2 的"盈亏来自哪些持仓"）；Portfolio 页"出错的来源不计入总数、快照标记为不完整、绝不沿用上次数据"（B3 对账展示规则）；Lumibot 的**决策回放缓存**（回测中重放同一批代理决策，不再花一次模型调用；对应 `prompt_hash/input_hash` 已有字段，E 线做 LLM 贡献测试时省钱且可复现）；LangAlpha 的**逐回合来源面板**（B3）；`ml4t/skills` 的 61 条防泄漏清单可与我们的 `backtest-forensics` 技能做一次差异比对（XS 工作量，只读比对，不安装）；《The Alpha Illusion》的六个结构性有效性维度作为 `llm_contribution_pass` 的评分表（见 4.5 节）。

### 不值得借鉴

- **多代理"投委会辩论"式交易决策**（TradingAgents、ai-hedge-fund、TradingAgents-CN/AShare、FinRobot V0/V1）：没有任何截止日后、扣成本、可核验的收益；独立研究（Profit Mirage、The Alpha Illusion）认为报告的夏普不应当作部署证据；与我们"LLM 只通过 PIT 特征包进入"的规则相反。
- **Alpha Arena 式让大模型直接下单**（nof1、nof0、LLM-trader-test、AI-Trader 的跟单/信号市场）：第 1.5 季 32 账户仅 6 个为正（三手转述，见旧简报），nof1 官网自己写"当前一代大模型在金融市场上表现很差，版本间几乎没有进步"。
- **Kronos、FinGPT、FinRL**：星多但没有美股可交易、扣成本的证据；FinRL 有独立负面诊断。
- **自然语言→策略代码的"一句话回测"**：我们的 StrategySpec 先行、预注册、安慰剂的流程更严；Vibe-Trading 自己的第一版 191 因子文章因未复权价和用今天的指数成分而出错，2026-09-29 才修正（见 2.2）。
- **IM 渠道和远程控制面**（Vibe-Trading 14+ 聊天通道、AI-Trader 的"让代理读 URL 注册"、QuantDinger 的 Agent Gateway）：与"驾驶舱只读、无命令入口"的边界冲突，增加攻击面。
- **TAP（第三方凭证代理）**：Vibe-Trading 可选的 Alpaca"TAP 模式"把真实密钥放在对方代理里并由人工审批写入；我们不应把券商密钥交给第三方。只借它的设计要点（凭证按主机绑定、确定性 `client_order_id`、审批竞态说明），见第 1 项。
- **重型基础设施**（QuantDinger 的 Kafka+Postgres+Redis+Celery、Hummingbot、freqtrade、Nautilus、vectorbt PRO、OpenBB Workspace）：与 3.9 GB 机器和 Alpaca 单通道不匹配，且大多面向加密或做市。
- **A 股专用项目**（Vibe-Research、vibe-astock、AlphaAgent、TradingAgents-CN/AShare、vibe-investing）：市场和数据源不对口。

## 2. "vibe trading"是什么

### 2.1 词的来源和用法

- 词根是 vibe coding。检索到的概述称它由 Andrej Karpathy 在 2025-02-02 的一条帖子里提出（"There's a new kind of coding I call 'vibe coding' ... where you fully give in to the vibes ... and forget that the code even exists"），2025 年成为 Collins 词典年度词。出处是检索摘要里的二手转述（scrimba 等），未打开 X 原帖。
- **vibe trading 指"用自然语言让 AI 生成、测试、部署交易策略"**。BlockEden 2026-03-10 的文章写道："vibe trading ... is a systematic process in which users prompt AI models to create, test, and deploy trading strategies — effectively turning large language models into junior quantitative analysts."（快照 `web__blockeden_vibe-trading.md`）。同文把它放在 2026 年 3 月 Binance Skills Hub、OKX Agent Trade Kit（80+ MCP 工具）、Bitget Agent Hub 三家几乎同时上线的背景下，并引用算法交易员 Austin Starks 的警告：同样的易得性也拿掉了原本阻止粗糙策略上线的护栏。
- 项目层面的几种用法：HKUDS/Vibe-Trading 自称"Your Personal Trading Agent"，README："an open-source research workspace for turning finance questions into runnable analysis ... designed for research, simulation, and backtesting — and, when you choose, autonomous trading through a broker you authorize yourself"；QuantDinger 的描述直接写"Open-source AI Trading OS, agent trading, and vibe trading"；ginlix-ai/LangAlpha 写"A vibe investing agent harness"，并有一节标题"From vibe coding to vibe investing"，核心主张是把 Claude Code 式的持久工作区带到投资研究（"every commit builds on what came before"）。
- **机主"最近很多新的 vibe Trading 项目"最可能指**：HKUDS/Vibe-Trading（2026-04-01 创建，API 取数 34,628 星，今天仍有推送）。检索摘要称它在 2026-07-12 首次登上 GitHub Trending 第一（来自 Trendshift/aitoolly 摘要，未打开原页）。同期的相近项目还有 QuantDinger（12.4k）、Vibe-Research（2.6k）、LangAlpha（1.8k）。
- X、Reddit、Hacker News 的原帖：**没找到**。`harvest_search.py` 的 X 渠道因 `twscrape` 未安装失败（按边界不装包），Reddit 渠道无输出，WebSearch 的 `site:` 查询只返回项目页和博客。所以"潮流"的描述来自 GitHub 数据和博客，没有社交媒体原文。
- 独立检索得到的警示：Finance Magnates 一篇标题为"Can you trust vibe coding to build your next trading tool"的文章（仅见标题，未读）；Vibe-Trading 自己的限制说明里写有"LLM 幻觉可能产生无效公式或含未来信息的函数，AST 检查只能降低风险，仍需人工复核"（来自检索摘要，未在 README 原文逐字核对）。

### 2.2 它自己的"战绩"：一个有用的反面例子

Vibe-Trading 的研究实验室文章《Which of the 191 GTJA alphas still work in 2026?》（`web__vibetrading-wiki_alpha-191-in-2026.md`）：

- 修订版（2026-09-29，0.1.16，沪深 300 时点成分，复权价，2018–2025，日度 IC 研究，不含成本）：191 个因子中 **8 个仍有效（4%）、14 个符号反转且显著（7%）、168 个失效（88%）、1 个因 99% 为 NaN 无法测试**。"有效"的门槛是平均 IC>0.02、t>2、正 IC 天数≥55%。
- 首版（2026-05-17）报告 10 个有效、15 个反转、165 个失效，原因是**价格未复权、并且把今天的沪深 300 名单套在整个窗口上**；两者于 2026-08-04 修复，另在 2026-09 起"任一输入缺失的那一天不再输出值"。
- 对我们的含义：热门项目首发的"回测发现"也会有复权和幸存者偏差错误；它的 `bench_runner_strict.py` 注释还声称，Soli22de/Bili_Stock 的 9 个月审计发现 12 个单因子里只有 1 个通过"同宇宙随机对照"（作者注释所称，我们没核对）。这与我们已有的安慰剂做法同向，不是新方法。

## 3. 总表

星数取自 GitHub API（取数时间 2026-10-04 17:50–17:58 UTC，逐行时间见 JSON）。nof1 Alpha Arena 没有仓库，无星数。

| 项目 | 星数 | 创建 | 最近推送 | 许可证 | 类别 | 一句话 | 证据等级 | 取向 |
|---|---|---|---|---|---|---|---|---|
| [HKUDS/Vibe-Trading](https://github.com/HKUDS/Vibe-Trading) | 34,628 | 2026-04-01 | 2026-10-04 | MIT | A LLM代理/vibe trading | 自然语言→数据加载→策略代码→回测→报告的研究工作台，带 462 因子库、假设登记、衰减监控、18 家券商连接器 | 只有回测 | 借鉴(流程件) |
| [OpenByteInc/QuantDinger](https://github.com/OpenByteInc/QuantDinger) | 12,436 | 2025-12-28 | 2026-10-02 | Apache-2.0 | A LLM代理/vibe trading | 自托管 AI 交易操作系统：策略进化(随机/网格/TPE+滚动验证+盲留出+PBO/DSR/Bootstrap/成本压力)+纸上/实盘执行 | 无 | 部分借鉴 |
| [HKUDS/AI-Trader](https://github.com/HKUDS/AI-Trader) | 22,649 | 2025-10-23 | 2026-06-11 | — | A LLM代理/vibe trading | 让 AI 代理注册、发信号、跟单的平台；$10 万模拟盘，Polymarket 模拟 | 模拟盘 | 不借鉴(平台/跟单) |
| [virattt/ai-hedge-fund](https://github.com/virattt/ai-hedge-fund) | 63,857 | 2024-11-29 | 2026-10-02 | MIT | A LLM代理/vibe trading | 投资大师人设代理 + 风控 + 组合经理的教学演示；现为终端应用，模拟盘 + 回测 | 无 | 不借鉴 |
| [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) | 109,742 | 2024-12-28 | 2026-10-03 | Apache-2.0 | A LLM代理/vibe trading | 分析师→多空辩论→交易员→风控→组合经理的 LangGraph 多代理框架 | 只有回测 | 借鉴(数据合同/决策结算) |
| [hsliuping/TradingAgents-CN](https://github.com/hsliuping/TradingAgents-CN) | 32,146 | 2025-06-26 | 2026-09-22 | NOASSERTION | A LLM代理/vibe trading | TradingAgents 的 A 股中文版，Streamlit/Web，模拟交易 | 无 | 不借鉴 |
| [KylinMountain/TradingAgents-AShare](https://github.com/KylinMountain/TradingAgents-AShare) | 851 | 2026-03-02 | 2026-09-18 | NOASSERTION | A LLM代理/vibe trading | 14–15 个代理的 A 股辩论可视化应用 | 无 | 不借鉴 |
| [AI4Finance-Foundation/FinRobot](https://github.com/AI4Finance-Foundation/FinRobot) | 8,140 | 2024-02-27 | 2026-09-28 | Apache-2.0 | A LLM代理/vibe trading | 金融代理平台，V2 桌面端：确定性计算与 LLM 叙述严格分离，产出带溯源的研究报告 | 无 | 借鉴(原则) |
| [AI4Finance-Foundation/FinGPT](https://github.com/AI4Finance-Foundation/FinGPT) | 21,348 | 2023-02-11 | 2026-09-23 | MIT | A LLM代理/vibe trading | 开源金融大模型（情绪分类等微调） | 无 | 不借鉴 |
| [TauricResearch/Trading-R1](https://github.com/TauricResearch/Trading-R1) | 499 | 2025-09-15 | 2025-09-15 | — | A LLM代理/vibe trading | Qwen3-4B + SFT/GRPO 课程训练的交易推理模型（论文） | 只有回测 | 观察 |
| [ginlix-ai/LangAlpha](https://github.com/ginlix-ai/LangAlpha) | 1,801 | 2026-01-18 | 2026-10-04 | Apache-2.0 | A LLM代理/vibe trading | 'Claude Code for Financial Market'：持久工作区、子代理、PTC(代理写代码处理数据)、逐回合来源面板 | 无 | 借鉴(工作区/溯源面板) |
| [simonlin1212/Vibe-Research](https://github.com/simonlin1212/Vibe-Research) | 2,625 | 2026-07-05 | 2026-09-25 | MIT | A LLM代理/vibe trading | 面向个人的 A/美/港股投研聊天工作台（资讯雷达、每日复盘） | 无 | 不借鉴 |
| [gameworkerkim/vibe-investing](https://github.com/gameworkerkim/vibe-investing) | 338 | 2026-04-18 | 2026-10-04 | — | A LLM代理/vibe trading | 韩语策展/专栏/提示词/小工具杂烩仓库 | 无 | 不借鉴 |
| [Lumiwealth/lumibot](https://github.com/Lumiwealth/lumibot) | 2,103 | 2020-09-10 | 2026-10-03 | GPL-3.0 | D 基础设施 | Python 回测/实盘一体框架，新增 AI 代理运行时：决策可回放、PIT 工具防前视 | 无 | 部分借鉴(决策回放) |
| [microsoft/RD-Agent](https://github.com/microsoft/RD-Agent) | 14,840 | 2024-04-03 | 2026-10-02 | MIT | B 量化研究/因子挖掘 | 因子-模型联合进化的研发代理 RD-Agent(Q)，NeurIPS 2025 | 只有回测 | 观察(09-19 已评) |
| [microsoft/qlib](https://github.com/microsoft/qlib) | 49,131 | 2020-08-14 | 2026-09-22 | MIT | B 量化研究/因子挖掘 | AI 量化平台(Alpha158、MLflow 实验管理) | 只有回测 | 不再投入 |
| [RndmVariableQ/AlphaAgent](https://github.com/RndmVariableQ/AlphaAgent) | 418 | 2025-05-30 | 2026-07-03 | — | B 量化研究/因子挖掘 | A 股 CSI1000 因子 DSL + FactorZoo + AgentScope 因子挖掘 | 只有回测 | 不借鉴 |
| [ml4t/skills](https://github.com/ml4t/skills) | 22 | 2026-04-01 | 2026-10-04 | Apache-2.0 | B 量化研究/因子挖掘 | 61 个防泄漏/前视/幸存者/成本等的 SKILL.md 清单（纯 Markdown） | 无 | 借鉴(审查清单) |
| [shiyu-coder/Kronos](https://github.com/shiyu-coder/Kronos) | 39,910 | 2025-07-01 | 2026-04-13 | MIT | B 量化研究/因子挖掘 | K 线基础模型(AAAI 2026)，附 A 股微调示例 | 只有回测 | 不借鉴 |
| [AI4Finance-Foundation/FinRL](https://github.com/AI4Finance-Foundation/FinRL) | 16,549 | 2020-07-26 | 2026-09-28 | MIT | B 量化研究/因子挖掘 | 金融强化学习框架（已转向 FinRL-X/FinRL-Trading） | 只有回测 | 不借鉴 |
| [AI4Finance-Foundation/FinRL-Trading](https://github.com/AI4Finance-Foundation/FinRL-Trading) | 3,780 | 2020-07-26 | 2026-09-18 | Apache-2.0 | B 量化研究/因子挖掘 | FinRL-X：面向生产的模块化 AI 原生量化基础设施 | 无 | 观察 |
| [wquguru/nof0](https://github.com/wquguru/nof0) | 2,748 | 2025-10-22 | 2025-12-07 | — | C 基准/竞赛 | 开源复刻 nof1 Alpha Arena 的加密 LLM 交易竞技场（Hyperliquid） | 无 | 不借鉴 |
| [kojott/LLM-trader-test](https://github.com/kojott/LLM-trader-test) | 144 | 2025-10-21 | 2025-12-29 | — | C 基准/竞赛 | DeepSeek 驱动的 Binance 行情纸上交易机器人，可选 Hyperliquid 实盘 | 实盘自报 | 不借鉴 |
| [xsunsim/AgentStockBenchmarkResults](https://github.com/xsunsim/AgentStockBenchmarkResults) | 16 | 2026-05-21 | 2026-09-22 | MIT | C 基准/竞赛 | 标普 500 每日排序擂台：代理代码冻结入追加式登记、服务器端时间戳、美元中性阶梯计分 | 模拟盘 | 借鉴(时钟/登记方式) |
| [nof1/Alpha Arena](https://nof1.ai/) | n/a | — | — | — | C 基准/竞赛 | 6 个 LLM 在 Hyperliquid 各 $10,000 实盘比赛（第 1 季 2025-10-18 至 11-03） | 实盘自报 | 观察(仅方法论) |
| [nautechsystems/nautilus_trader](https://github.com/nautechsystems/nautilus_trader) | 29,617 | 2018-06-25 | 2026-10-04 | LGPL-3.0 | D 基础设施 | Rust 核心的事件驱动引擎，回测与实盘同一套策略代码 | 无 | 观察 |
| [freqtrade/freqtrade](https://github.com/freqtrade/freqtrade) | 55,024 | 2017-05-17 | 2026-10-04 | GPL-3.0 | D 基础设施 | 加密机器人：回测、hyperopt、FreqAI 自适应 ML、Web UI、Telegram | 无 | 不借鉴 |
| [hummingbot/hummingbot](https://github.com/hummingbot/hummingbot) | 20,304 | 2019-04-02 | 2026-09-28 | Apache-2.0 | D 基础设施 | 做市/套利机器人；新增 Condor AI harness (LLM 决策+确定性执行) | 无 | 不借鉴 |
| [polakowo/vectorbt](https://github.com/polakowo/vectorbt) | 9,275 | 2017-11-14 | 2026-09-26 | NOASSERTION | D 基础设施 | 向量化回测、参数曲面可视化；PRO 版收费，社区版 Fair Code | 无 | 不借鉴 |
| [OpenBB-finance/OpenBB](https://github.com/OpenBB-finance/OpenBB) | 73,843 | 2020-12-20 | 2026-10-02 | NOASSERTION | D 基础设施 | '连一次，到处用'的数据平台(ODP)：Python、Workspace、MCP、REST | 无 | 不借鉴 |
| [alpacahq/alpaca-mcp-server](https://github.com/alpacahq/alpaca-mcp-server) | 1,007 | 2025-06-03 | 2026-09-25 | MIT | D 基础设施 | Alpaca 官方 MCP 服务器 v2（FastMCP+OpenAPI），ALPACA_TOOLSETS 可裁剪工具 | 无 | 观察(只读工具集) |
| [atilaahmettaner/tradingview-mcp](https://github.com/atilaahmettaner/tradingview-mcp) | 4,911 | 2025-08-08 | 2026-10-04 | MIT | D 基础设施 | TradingView 技术分析/筛选器 MCP | 无 | 不借鉴 |

证据等级说明：无 / 只有回测 / 模拟盘 / 实盘自报 / 实盘可核验或独立复现。这是**证据的强度**，不是项目好坏。表中"取向"是对我们的建议：借鉴 / 部分借鉴 / 观察 / 不借鉴。

## 4. 项目卡片

每张卡的"读过"一行列出本次实际打开的原文快照（均在 `sources/vibe-trading-2026-10-04/`）。

### 4.1 LLM / 多代理 / vibe trading 类

#### HKUDS/Vibe-Trading（34,628★，MIT，2026-04-01 创建，2026-10-04 仍推送）

- **读过**：`HKUDS__Vibe-Trading.md`（README 截至 200 KB）、`HKUDS__Vibe-Trading__decay_thresholds.md`、`..._src_hypotheses_registry.py.md`、`..._src_strategy_store_decay.py.md`、`..._bench_runner_strict_head.py.md`、`web__vibetrading-wiki_alpha-191-in-2026.md`、`web__devto_claude-code-vibe-trading-mcp.md`、`web__blockeden_vibe-trading.md`。
- **做什么**：自然语言研究请求 → 技能/工具选择 → 行情加载（28 个数据源，按"被封 IP 风险"排序的回退链）→ 策略代码 → 回测引擎 → 指标、基准、蒙特卡洛、Bootstrap、Walk-Forward → run card 与报告，导出 TradingView Pine、通达信、MetaTrader 5。另有 Shadow Account（用券商流水提炼用户规则并对比）、462 因子库的一行评测、18 家券商连接器（读 + 纸上下单，部分支持"受限实盘"）、定时研究和 14+ 个聊天通道。
- **架构**：ReAct 代理 + DAG 多代理"swarm"预设；FastAPI + React 19 + CLI/MCP；MIT。持久记忆和可编辑技能。研究路径：Plan → Ground → Execute → Validate → Deliver。
- **评估怎么做**：自带回测报告而非业绩声明。因子库评测用日度 IC 研究（不含成本），自家文章给出 191 因子的存活率（见 2.2）。0.1.16 起 run card 含执行记录哈希与"指标↔CSV"核对。**没有任何实盘或前向收益记录。**
- **成本与前视**：因子算子层禁止未来函数（AST 纯度检查 + 300 行哨兵测试 + `pytest-socket` 断网）；基本面用 SEC 申报日锚定；run card 记录写配置的模型与 `model_training_cutoff`，窗口早于截止日标"可能暴露"，未知按暴露；严格评测 `--training-cutoff` 把样本外放在截止日后；`bench_runner_strict` 要求同宇宙随机对照和样本外切分才能晋级 `confirmed_alive`。回测引擎含 A 股 T+1/印花税/涨跌停/手数、印度 STT 成本栈、永续资金费率；**美股股票的佣金、滑点、借券成本是否建模：README 没有逐项写明，待核对**。
- **我们能借的具体东西**：(1) 衰减状态机和阈值表（第 1 节第 2 项）；(2) 实盘路径的失效模式清单（第 1 节第 1 项，见 2026-08-25/08-27/08-29/09-06 的修复条目）；(3) 数字落地检查和 run card 哈希（第 1 节第 4 项）；(4) 假设登记状态（exploring/testing/validated/rejected/monitoring + 无效化备注 + 关联 run card）——我们已有 `oc research directions` 登记表，这里不用换，只对照字段；(5) Run Detail 的四个页签（因子研究：IC 序列、分位组净值、IC 相关矩阵；持仓：毛/净暴露、行业净暴露；收益单：月度热图、前 5 大回撤标注；仪表盘：滚动夏普）用于 B3/D1 的信息架构；(6) 一个 Claude Code 驱动它的 MCP 用法（dev.to 2026-08-02）可当作"Claude Code + 回测器"的现成接线样例。
- **风险和疑点**：版本节奏极快（0.1.15→0.1.16 一个周期 492 个提交、116 个合并 PR、16 位贡献者），首发数字被修正过；大量功能面（IM 通道、18 家券商、28 数据源）带来大攻击面——它在 2026-07-13 才关闭一次外部安全审计的 10 条发现；A 股和加密为主，美股细节不如它们；无独立复现的收益证据。

#### OpenByteInc/QuantDinger（12,436★，Apache-2.0，2025-12-28 创建，2026-10-02 推送）

- **读过**：`OpenByteInc__QuantDinger.md`。
- **做什么**：自托管"AI 交易操作系统"：AI 市场研究、Python 指标与 Strategy API V2、服务器端回测与实验、加密和传统券商（含 IBKR、Alpaca）的纸上/实盘执行、Web/H5/API/MCP 入口。
- **架构**：Flask+Gunicorn、PostgreSQL、两套 Redis、Kafka 事件骨干、Celery、独立交易/调度/评估 worker、Prometheus/Grafana。生产覆盖层以非 root、只读根文件系统运行。
- **评估怎么做**：**策略进化**——对声明的可调参数做随机/网格/TPE 搜索，按K线数的滚动验证 + 最终盲留出，输出组合评分、PBO、Deflated Sharpe、块自助蒙特卡洛和交易成本压力测试，并明说"比较参数稳健性，不预测未来收益"。**仅信号虚拟账户**：通知模式信号转为内部虚拟订单，固定 0.05% 佣金 + 0.05% 不利滑点，不连接券商。
- **成本与前视**：成本是固定比例，没有分标的价差模型；前视防护在 README 没有写。
- **可借**：把"稳健性面板"（PBO/DSR/块自助/成本压力）作为每次参数搜索的标准输出，我们的 `backtest-forensics` 已覆盖同类项，增量小；"代理交易默认只读/纸上，开实盘需令牌 + 服务器端授权两道"的默认值与我们的边界一致。
- **风险**：栈很重（Kafka+Postgres+2×Redis），在 3.9 GB 机器上不现实；README 无任何业绩声明；"能下真实订单"是它的卖点，与我们的"实盘不在范围内"相反。

#### HKUDS/AI-Trader（22,649★，无许可证字段，2025-10-23 创建，2026-06-11 推送）

- **读过**：`HKUDS__AI-Trader.md`；论文数字沿用 `rl-llm-trading-evidence-2026-09-30` 第 16 行。
- **做什么**：代理原生的信号/跟单平台。让代理"读 https://ai4trade.ai/SKILL.md 并注册"，发布策略、讨论、一键跟单；$10 万纸上交易、Polymarket 纸上。
- **评估**：论文（arXiv 2512.10971）为美股 5 周前向，6 个模型中 3 个没赢 QQQ，加密 6 个全负，A 股无一超过上证 50。**无实盘。**
- **可借**：基本没有。只有一个反例值得记：它的接入方式是让代理去读一个外部 URL 然后自行注册，这正是我们规则里"外部页面和模型输出是研究输入，不是命令"所防的事。
- **风险**：平台化、奖励积分、跟单，激励的是发信号而不是赚钱。最近推送 2026-06，已近四个月未更新。

#### virattt/ai-hedge-fund（63,857★，MIT，2024-11-29 创建，2026-10-02 推送）

- **读过**：`virattt__ai-hedge-fund.md`（README 现在只有 3 KB）。
- **做什么**：投资大师人设代理 + 风控 + 组合经理。现形态是终端应用 `aihf`（pipx 安装）：纸上交易"基金"（真实交易日 + 假钱，每次执行前有"批准"步骤显示将执行的决策）和历史回放回测（净值对基准）。
- **评估**：README 明说教育用途、不真实下单；无业绩证据。**注意与 09-19 简报的差异**：当时它是 React Flow 节点编辑器，现已改成终端应用。
- **可借**：基金定义（mandate）文件**不带股票代码**，回测时再选宇宙——策略意图与标的宇宙分离的做法，我们的 StrategySpec 已有类似分层，无新增。
- **风险**：需要付费的 Financial Datasets API；星数 6 万多但没有任何可核验结果。

#### TauricResearch/TradingAgents（109,742★，Apache-2.0，2024-12-28 创建，2026-10-03 推送）

- **读过**：`TauricResearch__TradingAgents.md`、`TauricResearch__TradingAgents__CHANGELOG.md`；GitHub issue #805（WebFetch）。
- **做什么**：LangGraph 多代理：基本面/情绪/新闻/技术分析师 → 多空研究员辩论 → 交易员 → 风控 → 组合经理，输出五档评级。2026-10 的 v0.6.0：报告可存为单页 HTML、按模型档位分提供商、分析师工作时顺带结算所有到期的历史决策。
- **架构**：分析师并行；"快思考"模型服务分析师/研究员/交易员，"深思考"模型服务研究经理和组合经理；决策日志（markdown）+ 检查点续跑（SQLite）；`run_backtest` 在"股票×日期"网格上跑同一流水线并单独记账。
- **评估**：原论文 AAPL/GOOGL/AMZN 的 3 个月回测，累计 26.62%/24.36%/23.21%，夏普 8.21/6.39/5.60，作者自注"超出预期经验区间"，归因于"回撤少"（见旧简报第 7 行）。**独立证据偏负**：Profit Mirage（arXiv 2510.07920）称基座模型发布后夏普衰减 55.68%；issue #805 提出"2026 年训练的模型回测 2023 年会带着对未来的知识"，**该 issue 没有量化数据，也没有看到维护者回复**。
- **成本与前视**：这是本批项目里**对前视最认真的一个**——0.4.0（2026-08）修 FRED 宏观用今天版本的泄漏、社交情绪无日期过滤、记忆日志返回未来结算的决策；0.5.0（2026-09）"每条带日期的路径都保证时点完整"：SEC EDGAR 按申报日供给、重述前读首次披露值，非 SEC 公司在过去日期的运行里财报与内部人交易被告知"withheld"；0.5.2 的新闻条目写"backtests that see only data published by e…"（README 原句在此截断，意思是按日期只看已发布数据）。成本：框架本身没有成交与手续费模型（决策以评级和相对基准的超额结算）。
- **可借**：第 1 节第 3、5 项——"无法定日期就拒绝供给"的数据合同，和"决策日志 + 持有期满后对基准结算 + 一段反思"的闭环。反思进入下一次决策的上下文，这与我们禁止的"LLM 影响交易行为必须先成为 PIT 特征包"一致，**可借的是结算机制，不是反思文本本身进交易**。
- **风险**：109k 星是关注度，不是业绩；项目自己的 README 声明"仅用于研究，表现随模型、温度、时期、数据质量变化"。

#### hsliuping/TradingAgents-CN（32,146★，NOASSERTION，2025-06-26 创建，2026-09-22 推送）与 KylinMountain/TradingAgents-AShare（851★，2026-03-02 创建，2026-09-18 推送）

- **读过**：两者 README。
- **做什么**：TradingAgents 的 A 股化分支。CN 版是 Apache-2.0 核心 + 专有源码可见应用层的混合许可，功能包括单股辩论研究、选股助手、学习中心、纸面交易。AShare 版有 14–15 个代理、辩论可视化抽屉，并推广第三方中转服务。
- **评估**：无业绩证据，自称"不构成投资建议"。
- **可借**：无。09-19 简报已记录其可展开的多阶段进度条（B3 已吸收）。
- **风险**：许可证混合；商业推广混入 README。

#### AI4Finance-Foundation/FinRobot（8,140★，Apache-2.0，2024-02-27 创建，2026-09-28 推送）与 FinGPT（21,348★，MIT）

- **读过**：两者 README。
- **FinRobot 做什么**：三代并存：V0 AutoGen（教学）、V1 OpenAI Agents SDK（自托管报告生成）、V2 PydanticAI 桌面研究工作站（"生产"），V3 开发中。核心原则：**"models reason, software computes, agents orchestrate, systems verify"**；所有金融数字由纯 Python 算子产生，LLM 只做推理与叙述，"Numbers are code-calculated. Narratives are LLM-assisted. Every output is provenance-tracked."
- **评估**：偏估值与研报，没有交易业绩声明。FinGPT 是微调的金融大模型（情绪等任务），与 09-22 结论一致，无交易证据。
- **可借**：这条原则正好是第 1 节第 4 项的哲学依据——汇报里的数字必须由代码产出并带出处，LLM 只写叙述。无需引入任何代码。
- **风险**：无。

#### TauricResearch/Trading-R1（499★，无许可证，2025-09-15 创建，同日最后推送）

- **读过**：README 在 `HEAD` 路径返回 404（快照文件里已注明）；论文数字沿用 09-30 简报第 4 行。
- **做什么**：Qwen3-4B + SFT/GRPO 三阶段课程的交易推理模型（论文）。
- **评估**：2024-06 至 08 的 3 个月回测；仓库创建后再没有推送，描述仍是"Terminal coming soon ..."，没有权重链接。
- **取向**：观察。09-30 的重开条件（独立复现）未满足。

#### ginlix-ai/LangAlpha（1,801★，Apache-2.0，2026-01-18 创建，2026-10-04 推送）

- **读过**：`ginlix-ai__LangAlpha.md`。
- **做什么**："A vibe investing agent harness"。主张投资是贝叶斯式的迭代过程，因此给代理一个持久工作区（每个研究目标一个沙箱，`agent.md` 笔记跨会话累积，另有长期记忆目录）。关键机制：渐进式工具发现（MCP 工具只放摘要，完整文档放工作区）、**程序化工具调用**（代理写 Python 处理金融数据，不把原始数据倒进上下文）、并行子代理（隔离上下文、中途引导、检查点续跑）、定时/价格触发自动化、"秘书"代理、逐回合来源面板。
- **架构**：React 19/Vite + FastAPI + PostgreSQL（双连接池）+ Redis 缓冲 SSE。
- **评估**：无业绩声明；它是研究工具而不是策略。
- **可借**：**逐回合来源面板**对应 B3 里"这个数字从哪来"；工作区笔记 + 子代理 + 检查点续跑的模式，我们的"轮次 + 简报 + 队列"文件体系已经在做，不需换。
- **风险**：数据库与 Redis 的重栈；价格触发自动化若连券商会越过我们的边界（它是研究侧，未看到下单）。

#### simonlin1212/Vibe-Research（2,625★）、gameworkerkim/vibe-investing（338★）

- **读过**：两者 README 开头。
- Vibe-Research：A/美/港股个人投研聊天工作台（"Agent 默认关闭，需要联网查证再开启"），README 顶部是作者求职信息。vibe-investing：韩语策展/专栏/小工具杂烩（含一个 TokenForge 提示词压缩器和一个 DART 公告监控应用）。均无回测与业绩。**不借鉴。**

### 4.2 自动化量化研究 / 因子挖掘类

#### microsoft/RD-Agent（14,840★，MIT，2024-04-03 创建，2026-10-02 推送）

- **读过**：`microsoft__RD-Agent.md`（News 与 RD-Agent(Q) 章节）。
- **做什么**：研发代理。量化场景 RD-Agent(Q)："data-centric, multi-agent framework ... coordinated factor-model co-optimization"；Qlib 自循环 `rdagent fin_quant`。2026 新闻是 FT-Agent（ICML 2026，LLM 微调）、Agent² RL-Bench 等，**量化部分没有新更新**。
- **评估**：论文（NeurIPS 2025 数据集与基准赛道）称成本低于 $10 时年化收益约为基准因子库的 2 倍、因子少 70%+，基准市场为 A 股；**两轮检索都没有找到独立复现或样本外批评**。
- **取向**：观察（沿用 09-19 的判断：它的 UI 停在看日志层级）。**借鉴价值**：多臂老虎机在"因子 vs 模型"方向间调度的思路，在我们"每周盘点各引擎预算"里有对应，不需要它的代码。

#### microsoft/qlib（49,131★，MIT，2020-08-14 创建，2026-09-22 推送）

- 读过 README 开头：首屏就是 RD-Agent 的发布公告。本仓库的 Alpha158 美股版已被 H-20260918-03 否定，**不再投入**。

#### RndmVariableQ/AlphaAgent（418★，无许可证，2025-05-30 创建，2026-07-03 推送）

- 读过 README：A 股 CSI1000 因子 DSL + FactorZoo + AgentScope 因子挖掘；数据在百度网盘。仓库无业绩。**不借鉴。**

#### ml4t/skills（22★，Apache-2.0，2026-04-01 创建，2026-10-04 推送）

- **读过**：README 的目录表（61 个技能，纯 Markdown，无脚本、无网络调用）。
- **做什么**：把《Machine Learning for Algorithmic Trading》第 3 版的纪律做成给编码代理用的 SKILL.md，每条按"问题/错误写法/正确写法/护栏/清单"组织。概念类含 backtest-overfitting、data-leakage、lookahead-bias、point-in-time、survivorship-bias、regime-awareness、transaction-costs、non-stationarity、information-coefficient、causal-identification。
- **可借**：与我们已有的 `backtest-forensics`、`data-capability-reviewer` 技能做一次**只读差异比对**（看它多了哪些检查项，例如 `define-universe` 的时点宇宙、`regime-awareness` 的"把状态当条件变量而不是择时信号"）。不安装、不拷贝，缺的检查项手写进我们自己的技能。XS 工作量。
- **风险**：星数只有 22；README 自己引用的研究提醒第三方技能有 26.1% 含漏洞（arXiv 2601.10338，我没打开该论文），安装前应逐个审读。

#### shiyu-coder/Kronos（39,910★，MIT，2025-07-01 创建，2026-04-13 推送）

- 读过 README：K 线基础模型（AAAI 2026），附 Qlib 准备数据的 A 股微调示例；README 声明"演示性质，不是生产量化系统"。**无美股可交易回测**，2026-04 后无推送。星数高于多数交易框架，但与 09-22 结论一致：不借鉴。

#### AI4Finance-Foundation/FinRL（16,549★）、FinRL-Trading（3,780★，Apache-2.0，推送 2026-09-18）

- FinRL 的 README 首屏提示它"保留教育与研究框架"，最新架构和实盘部署请用 FinRL-X/FinRL-Trading。独立 PPO 诊断（夏普 0.559 < 等权 1.115）见 09-30 简报。FinRL-Trading 本次只取了元数据。**不借鉴。**

### 4.3 带实盘/前向记录的基准与竞赛

#### nof1 Alpha Arena（无仓库）

- **读过**：`web__nof1-home.md`（nof1.ai 首页文本，2026-10-04 取得）。`/blog` 与 `/leaderboard` 现返回 404（09-30 时 blog 索引还能打开，TechPost1 和排行榜则是 429）。
- **现状**：首页现在把 nof1 定位为"AI research lab for financial markets"，原文："The current generation of LLMs are shockingly bad at navigating financial markets. They've read vast amounts of financial text, but struggle with even the simplest investing tasks, showing minimal signs of improvement between releases." 并强调市场非平稳、基准会被快速记住和饱和。
- **第 2 季**：扩展检索摘要称截至本次未见公开的第 2 季名单或结果，网站博客只列一篇 2025-10-27 的文章（**搜索摘要，未经原页核对**，且与首页现状一致）。
- 第 1、1.5 季的数字与三手来源问题见 `rl-llm-trading-evidence-2026-09-30` 第 1、2 行与第 6 节，本次无新数据。
- **前视与成本**：实盘本身没有前视；成本是真实手续费，滑点与资金费率数字未公开；**没有买入持有基线**，单次运行。这是与我们"比同输入表格基线"最大的差距。
- **取向**：观察，只借方法论（真钱 + 链上可核验 + 固定提示），不借结果。

#### xsunsim/AgentStockBenchmarkResults（16★，MIT，2026-05-21 创建，2026-09-22 推送）

- **读过**：`xsunsim__AgentStockBenchmarkResults.md`。
- **做什么**：每日标普 500 排序擂台。代理代码被合入**只追加登记表**，获得服务器端时间戳；每日收盘后自动评分，全程无人工修 bug；代理只返回每只股票的原始分数，由固定的美元中性"阶梯"定仓位（最高分 +$250、最低分 −$250，中间等距）；代码报 NaN 或丢票就把该预测推到中位（$0）。有 MCP 服务器版和 GitHub Pages 看板。
- **评估**：前向实测，榜单有每日摘要（例如 2026-09-21 的 OpenAI O3 日 $221.92）；**但 README 明说"假设可买零股并忽略交易成本、借券费和市场冲击"**。成绩是自报，我无法核验；16 星说明没有外部关注。
- **前视处理**："严格 t-1 → t → t+1 时间不变式"，数据快照截到昨日收盘，"双仓库干净室"。
- **可借**：第 1 节第 5 项——登记表加服务器端时间戳的前向时钟，以及"代理只给分数、仓位由固定规则决定"的评估口径（把模型贡献与仓位设计分开，正对我们的 `ml_contribution_pass` 分离要求）。
- **风险**：零成本计分，这对短周期排序是致命缺陷（旧简报多处证明毛边际 2–4%/年扣费后不剩）。

#### wquguru/nof0（2,748★，无许可证，2025-10-22 创建，2025-12-07 最后推送）

- **读过**：README。"完整复刻 nof1 Alpha Arena"的开源加密竞技场（Next.js + Go-Zero + Hyperliquid），自报前端 100%、后端 70%、AI 交易引擎 80%。无结果、近 10 个月无推送。**不借鉴。**

#### kojott/LLM-trader-test（144★，无许可证，2025-10-21 创建，2025-12-29 推送）

- **读过**：README。DeepSeek 驱动的 Binance 行情纸上交易机器人，可选 Hyperliquid 主网（"Beta，请愿意用真钱的人来当测试者"）。"Sniper"提示词、动态多币种选择、高级回测需 Patreon 订阅，路线图按每档 $1,000 赞助解锁。文中称近期 +17%，**无法核验**。**不借鉴**——这是"晒结果卖订阅"的典型形态。

### 4.4 交易与回测基础设施

#### Lumiwealth/lumibot（2,103★，GPL-3.0，2020 年创建，2026-10-03 推送）

- **读过**：`Lumiwealth__lumibot.md`。
- **做什么**：Python 回测/实盘一体框架，口号"AI agents that actually place the trade"；12 家券商含 Alpaca；`lumibot demo` 在免费日线上跑真实回测并出 tearsheet。**新增 AI 代理运行时**：回测与实盘里同样运行代理；可建只读研究代理（`allow_trading=False`）；DuckDB 做时间序列分析；挂 MCP 服务器；**"Replay identical agent decisions in backtests without paying for another model call"**；README 配图称"Point-in-time AI agent tools prevent look-ahead bias"；"确定性 Python 门"让模型无法绕过。
- **评估**：示例只有回测记录，并说明"重放保存的决策与让模型重新推理不同"；无实盘证据。
- **可借**：决策回放缓存——键 = (模型, prompt_hash, input_hash)，让 LLM 贡献测试可复现且省调用；"确定性门"与我们的 PIT 特征包同向。GPL-3.0：只借思路，不拷代码。
- **风险**：官方配套托管服务 BotSpot 与付费数据商推广混在 README 中。

#### nautechsystems/nautilus_trader（29,617★，LGPL-3.0）

- 读过 README。Rust 核心的事件驱动引擎，"同一套策略和执行算法代码"跑回测和实盘，并专门有一页"回测与实盘差异"。09-19 简报已评。对我们：基础设施太重，**只借"明写回测/实盘差异清单"的做法**，放进 A4 验收。**观察。**

#### freqtrade/freqtrade（55,024★，GPL-3.0）、hummingbot/hummingbot（20,304★，Apache-2.0）、polakowo/vectorbt（9,275★，NOASSERTION）、OpenBB（73,843★，NOASSERTION，API 重定向到 `openbq-org/OpenBB`，组织名变更待核对）

- 读过四者 README。freqtrade 以加密为主；其 **`lookahead-analysis`** 与 `recursive-analysis` 命令（先跑全量回测拿基线，再对每个入场/出场单独截断重跑，比较指标值与信号位移）是第 1 节第 3(c) 项"截断不变性测试"的原型，文档页 `docs/lookahead-analysis.md` 已读。Hummingbot 新增 Condor（LLM 决策 + 确定性执行的 AI harness，Telegram 或网页控制），面向做市。vectorbt 社区版已降级，PRO 收费。OpenBB 把自己定位成"connect once, consume everywhere"的数据层，含 MCP 服务器；其 Workspace 云端 UI 要求公网可达，与我们的只读边界冲突（09-19 已记）。**除 freqtrade 的方法外，均不借鉴。**

#### alpacahq/alpaca-mcp-server（1,007★，MIT，2025-06-03 创建，2026-09-25 推送）与 atilaahmettaner/tradingview-mcp（4,911★，MIT）

- 读过两者 README。Alpaca 官方 MCP v2（FastMCP + OpenAPI，`ALPACA_TOOLSETS` 可按工具集裁剪）。**观察**：若以后让 Claude 在会话里查询账户，可用只读工具集，但我们的写路径已走既定的 Alpaca Paper 通道，不需要加 MCP 写权限。tradingview-mcp 是技术指标/筛选器，机主不看好此类，**不借鉴**。

### 4.5 独立批评文献（不是项目，但决定了该怎么看上面的星数）

这四篇的摘要通过 arXiv API 取得（`arxiv-<id>.md`），均只读了摘要；Beyond Agent Architecture 只有二手转述。

- **《The Alpha Illusion》（arXiv 2605.16895）**：LLM 交易代理的报告收益"不应当作部署证据"；须通过六类结构性有效性检验——时间完整性、现实摩擦、反事实稳健性、预测校准、数值执行、多代理拆解；提出最小报告协议 P1–P6，并主张保守的模块化替代：**LLM 作为可审计的信息接口，位于独立的校准、风控、执行模块上游**。这与我们"LLM 输入先成为 PIT 特征包"的规则同构，可当成 `llm_contribution_pass` 的评分表（六个维度逐条打勾）。（我用 WebFetch 想取 P1–P6 的逐条定义，返回内容与摘要对不上，没采用。）
- **《Toward Reliable Evaluation of LLM-Based Financial Multi-Agent Systems》（arXiv 2603.27539）**：对 12 个多代理系统的四维分类；记录五类普遍的评估失败（前视、幸存者、回测过拟合、忽略交易成本、状态切换盲区），称其可以**翻转报告收益的符号**；提出"协调盈亏平衡价差"（CBS）衡量多代理协调在扣成本后是否真有增量。我没取到 CBS 的公式。
- **《Can Blindfolded LLMs Still Trade?》（arXiv 2603.17692）**：匿名化代码和公司名后，LLM 评分 + 图神经网络 + PPO，2025 年初至 8 月 1 日夏普 1.40±0.22（20 个种子），做了负对照实验；扩展到 2024–2025 发现**状态依赖**：波动期强，趋势牛市里 alpha 缩小。**方法可借**：匿名化 + 负对照正是 09-30 简报里"P1 阶段"的前视防护设计。
- **《Look-Ahead-Bench》（arXiv 2601.13770）**：用 alpha 衰减度量标准 LLM 的前视偏差，对照时点推理（PiT）模型家族 Pitinf。
- **《Beyond Agent Architecture: Execution Assumptions and Reproducibility in LLM-Based Trading Systems》（2026-06-06 提交，Yao & Zheng）**：对 30 项研究编码审计，结论是瓶颈在执行时点、成本处理、泄漏控制，而不是模型选择。仅有 letsdatascience 的转述（快照 `web__letsdatascience_reproducibility-gaps.md`），论文本体未打开；另有检索摘要称 TradingAgents 与 QuantAgent 在 2025–2026 一年、含真实成本的受控复现下显著退化，**未能与论文原文对上，待核对**。

## 5. 对 A–E 各线的建议

| 线 | 建议动作 | 对应借鉴项 | 工作量 |
|---|---|---|---|
| **A1 前向记录** | 每日信号文件哈希链 + 外部可核对的时间戳（邮件日报/Drive 副本）；持有期满后按同期基准结算；A1 报告里加衰减状态机的状态列 | 1.5、1.2 | S |
| **A4 实盘清单** | 把第 1 节第 1 项的每条失效模式改写成验收测试，并加入 T-20261004-72 的清单；增加"回测/实盘差异清单" | 1.1、Nautilus | S |
| **A5 提议** | 每份提议的"失效信号和减半规则"直接用状态机转移条件表达（连续 N 次警告 → 减半；连续危急 → 停） | 1.2 | S |
| **B1/B2 报告** | `owner_digest` 之前加"声明-出处"核对：每个数字附文件路径与哈希，核对失败的数字剔除并在邮件里点名；审计器无证据时失败 | 1.4、FinRobot 原则 | M |
| **B3 看板** | 持仓页：毛/净敞口并列、行业净暴露条形图；对账页：出错的来源不计入总数、标记快照不完整；逐数字来源面板 | Vibe-Trading Run Detail/Portfolio、LangAlpha | S–M |
| **C 频率** | 本次调研无直接借鉴项；freqtrade 的 `lookahead-analysis` 思路可在日频/日内引擎上线前先跑一次截断不变性 | 1.3(c) | S |
| **D 稳健性** | 持仓页的行业净暴露直接服务 D1 的半导体贡献；衰减状态机可用作 D2/D4 里"状态择时规则"的失效监控骨架 | Vibe-Trading Positions、1.2 | S |
| **E 流程** | 时间合同（能力登记表加"可得性语义"、run card 加模型截止日、截断不变性夹具）；`llm_contribution_pass` 评分表用《The Alpha Illusion》六维；`ml4t/skills` 差异比对；决策回放缓存 | 1.3、4.5、Lumibot | S–M |

建议顺序：先做 A4 的清单（最高优先、1 天）和 A1 的哈希链/结算（1 天），再做 B1 的声明-出处核对（2–3 天），E 线的时间合同可以并入 T-20261004-54 PIT 审计的后续。

## 6. 没做完 / 拿不准的地方

- **X 渠道**：`harvest_search.py --channel x` 报 `ModuleNotFoundError: twscrape`，按边界没有安装。Reddit 渠道运行但无输出。HN/Reddit 的 `site:` 检索没返回原帖。所以"vibe trading 潮流"的社交媒体层是空的。
- **没有读源码**：除 Vibe-Trading 的衰减、假设登记、严格评测三个文件的片段和 freqtrade 文档外，其余项目只读 README/CHANGELOG。第 1 节第 1 项里的失效模式来自 Vibe-Trading 的更新日志描述（他们对自己缺陷的叙述），我没有逐个核对代码修复。
- **Vibe-Trading 在美股上的成本模型**（佣金、滑点、借券）README 没有逐项写明，待核对。
- **OpenBB 的组织名**：API 把 `OpenBB-finance/OpenBB` 重定向到 `openbq-org/OpenBB`，星数 73,843 是重定向后的值，组织名变更的原因待核对。
- **`Beyond Agent Architecture` 的 10 只股票示例**与"TradingAgents/QuantAgent 复现退化"的说法，只有二手转述。
- 我没有核对 Alpha Arena 第 1/1.5 季的数字（官网抓取受限），沿用 09-30 简报的三手来源警告。
- WebFetch 对 arXiv PDF 返回了与摘要对不上的 P1–P6 细节，已弃用；两篇 PDF 副本在会话工具结果目录，不在仓库内。
- 本仓库现有防前视测试：只看到 `tests/test_ml_no_lookahead.py`（ML 特征管线），没有审计其他信号生成器，所以"截断不变性夹具缺失"是未核实的推断，应先 grep 再动手。

## 7. 来源清单（快照在 `reports/research/intel/sources/vibe-trading-2026-10-04/`）

取数时间均为 2026-10-04 UTC，17:50–18:10 之间。GitHub README 的 URL 形式 `https://raw.githubusercontent.com/<owner>/<repo>/HEAD/README.md`，文件名 `<owner>__<repo>.md`。

| 类别 | 来源 | 快照 |
|---|---|---|
| GitHub README | HKUDS/Vibe-Trading（截断至 200 KB）、HKUDS/AI-Trader、OpenByteInc/QuantDinger、virattt/ai-hedge-fund、TauricResearch/TradingAgents、hsliuping/TradingAgents-CN、KylinMountain/TradingAgents-AShare、AI4Finance-Foundation/{FinRobot,FinGPT,FinRL}、ginlix-ai/LangAlpha、simonlin1212/Vibe-Research、gameworkerkim/vibe-investing、microsoft/{RD-Agent,qlib}、RndmVariableQ/AlphaAgent、ml4t/skills、shiyu-coder/Kronos、wquguru/nof0、kojott/LLM-trader-test、xsunsim/AgentStockBenchmarkResults、nautechsystems/nautilus_trader、freqtrade/freqtrade、hummingbot/hummingbot、polakowo/vectorbt、Lumiwealth/lumibot、OpenBB（`openbq-org__OpenBB.md`）、alpacahq/alpaca-mcp-server、atilaahmettaner/tradingview-mcp | `<owner>__<repo>.md` |
| 其他 GitHub 原文 | TradingAgents `CHANGELOG.md`；Vibe-Trading 的 `decay_thresholds.md`、`hypotheses/registry.py`、`strategy_store/decay.py`、`factors/bench_runner_strict.py`（前 9 KB）；freqtrade `docs/lookahead-analysis.md`（只读 WebFetch/curl，未存快照） | `TauricResearch__TradingAgents__CHANGELOG.md`、`HKUDS__Vibe-Trading__*.md` |
| 网页 | nof1.ai 首页；BlockEden 2026-03-10《Vibe Trading: When Natural Language Replaces Code in Crypto》；vibetrading.wiki《Which of the 191 GTJA alphas still work in 2026?》；dev.to 2026-08-02 Claude Code + Vibe-Trading MCP；letsdatascience 2026-06-09 转述 | `web__*.md` |
| arXiv 摘要 | 2603.17692、2603.27539、2601.13770、2605.16895（经 export.arxiv.org API） | `arxiv-*.md` |
| 只有检索摘要，未打开原文 | Trendshift/ossinsight（Vibe-Trading 2026-07-12 登 Trending 第一）、Finance Magnates 文章、TradingAgents issue #805 的 WebFetch 摘要（无量化数据）、扩展检索里 Alpha Arena 第 2 季状态、arXiv 2601.10338（技能漏洞研究）、Karpathy 2025-02-02 原帖 | 无 |

GitHub API 取数：`/repos/<owner>/<repo>`（核心接口限额每小时 60 次，用了约 25 次）与 `/search/repositories`（搜索限额每分钟 10 次，用了约 17 次，中途触发过一次限额，等待后重试）。搜索关键词：`vibe trading`、`vibe-trading`、`ai hedge fund multi-agent trading`、`LLM trading agents stock`、`alpha factor mining LLM agent`、`quant research agent autonomous backtest`、`alpha arena trading LLM`、`trading MCP server claude`、`claude code trading skills quant`、`topic:llm topic:trading`、`openclaw trading skills` 等，均带 `created:>2025-01-01` 或同类过滤。完整机器可读总表见 `I-20261004-02-vibe-trading-github-survey.json`。
