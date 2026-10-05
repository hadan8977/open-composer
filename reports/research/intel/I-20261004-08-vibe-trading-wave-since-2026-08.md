# I-20261004-08：2026 年 8 月以来的 vibe trading / AI 交易项目潮（整类调研）

- 任务码：T-20261004-83（协调码 R1004-T83），执行：Sonnet 5.5 high；2026-10-04 18:35 UTC 起，因额度中断后于 10-05 04:30 UTC 续做，2026-10-05 05:02 UTC 完成。
- 状态：**主体完成，三处交付物齐全。未完成项**见第 8 节：X 渠道不可用；Reddit 被拦（403）；**GitHub 的 stargazers 接口现需认证，机器上没有令牌，所以老项目"8 月以来新增星数"无法抽样**，只能给速率近似；多数卡片读的是 README/文档，没有审源码；Trendshift 只看到每档前 25 名。
- 星数、创建日、推送日、许可证：来自 GitHub REST API（未认证）。搜索接口取数在 2026-10-04 18:35–18:47 UTC，刷新取数在 2026-10-05 04:33 UTC，逐行取数时间见 JSON 的 `stats_fetched_utc`。
- 与 T-76（`I-20261004-02-vibe-trading-github-survey.md`）的关系：T-76 里已有的项目（Vibe-Trading、TradingAgents、QuantDinger、LangAlpha 等）只补 8 月以来的变化；本篇的对象是 **8 月 1 日以后新建的项目**，加上少数 8 月后有明显动静的老项目。
- 原文快照：`reports/research/intel/sources/vibe-wave-2026-10-04/`（46 个文件，每个 ≤200 KB，文件头注明来源 URL 与取数时间）。

## 1. 一页结论

**这波潮的形状：数量爆炸，深度很浅，没有一个扣成本、可核验、够长的前向结果。**

1. **量大。** 同一窗口（8 月 1 日至 10 月 4 日）新建的仓库，"trading agent"关键词命中 3,459 个，去年同窗口是 603 个（5.7 倍）；"alpaca agent"767 对 9；"claude trading"443 对 40；"trading MCP"624 对 88。但带 ≥50 星的只有 11 对 6 个。我收集到的 1,276 个新仓库里，≥1000 星的只有 3 个，≥300 星的 12 个，而且这 3 个里一个是名人发布日爆星（jev-trader，2,799 星，一次推送后再没动）、一个是 A 股桌面应用、一个是我们的结构近亲（ALTA）。**星数和质量脱节**：文档最扎实的 Alpaca 期权代理 swiftward 只有 4 星。Trendshift 今天/本周/本月前 25 名里一个交易项目都没有（10-04 18:50 UTC 取，只看得到前 25）。老牌的 Vibe-Trading 仍在涨（约 194 星/天），TradingAgents 约 121 星/天，其余老项目（ai-hedge-fund、LangAlpha、AI-Trader）接近零。
2. **潮流由事件驱动，不是自然生长。** 三个事件造出了大部分新仓库：(a) **Alpaca AI Trading Agents 黑客松**（lablab.ai，8 月 28 日–9 月 4 日，奖金池 $5,000，用 Alpaca API/MCP/CLI），贡献了几十个 Alpaca 期权代理；(b) **TypeSafe Jev**（9 月 15 日发布的"System One"类型化决策模型），一周内冒出一批 Jev 交易机器人（搜索命中 113 个，我见到的至少 7 个）；(c) **Robinhood Chain 主网**（7 月 1 日）加 Robinhood 官方 **Agentic Trading**（5 月 27 日，专用 MCP 账户），带来一批 Robinhood Chain 代币机器人。另有 Karpathy autoresearch（3 月 7 日）被搬到交易，和 DeepSeek Harness（dsh-*，A 股为主）的插件热。
3. **真正有信息量的东西在边角，不在高星项目里。** 值得我们读的新东西是：(i) DXRG 的人群级实测（3,505 个真币金库 + 500–599 个永续代理，**没有方向性优势，输给匹配的散户基准**），附 17 条方法纪律；(ii) 黑客松里几个把"风控引擎代理改不了、拒绝要记录、数字可一条命令重算"做到位的工程；(iii) 把"试验计数、一次性留出、哈希链账本、门槛放宽留痕"做成机制的研究环（autonomous-quant-researcher、Qanat）。
4. **有没有人公开了扣成本的前向/实盘结果？没有够格的。** 最接近的是：DXRG（真币，但同一实验室自报、聚合数据、结论为负）；swiftward（Alpaca 模拟盘，4 个交易日 +2.59% 对 SPY +0.76%，窗口太短，作者自己写明"四个交易日分不开技能和运气"）；atlas-gic（自报实盘 +22%/173 天，未核验，回测按分群出现 -13% 到 -30%）；aitradingcompetition.com（约 20 个 LLM 机器人，纸上交易，第一名 +45.58% 对标普 +4.16%，无成本，牛市窗口，自报）。
5. **对我们：这批项目几乎不提供"赚钱的想法"，提供的是几件工程和方法纪律**，与 T-76 的结论一致，但补了 T-76 没有的：Alpaca 专用的失败清单、人群级的"代理为什么亏"的测量、研究环的防自欺机制。

### 最值得借鉴的 5 件事（详表见第 6 节）

| # | 借什么 | 放进哪条线 | 工作量 | 与 T-76 是否重复 |
|---|---|---|---|---|
| 1 | **DXRG 的 17 条方法纪律和三个可直接复用的发现**：固定括号出场胜过所有自由裁量出场（+39.0 bps/仓）、仓位不随波动调整、调度偏移 ±15 分钟能把结果从 -88 变成 +21 美元（"时点运气下限"） | **E 流程**（评估清单）；**D/A**（对我们自己的模拟盘成交和信号做出场对照、日期中性报告） | S | 不重复 |
| 2 | **swiftward 的 34 条"避免的失败"和风控引擎结构**：代理不持有券商密钥、订单经它改不了的服务放行或拒绝并报规则名、拒绝与被拦的调用一起记录、期权价差用单张多腿订单、按到期最坏损失定仓位、每个公开数字一条命令重算、旁边必须放 SPY；Deflow 补：工作单不算持仓，直到券商确认成交；券商 `equity` 字段曾返回收益序列，必须校验口径 | **A4 实盘/模拟盘通道清单（T-72）**、**B 报告** | S–M | 部分重复(T-76 #1 是 Vibe-Trading 的失败清单)，这里是 Alpaca/期权专用且更完整 |
| 3 | **研究环的防自欺机制**（autonomous-quant-researcher + Qanat）：准入先去重(语义/近似/假设族配额)再花试验、一次性留出带持久回执(评估失败也算用掉)、预算耗尽≠成功、**给出盈亏平衡成本而不是假设成本**、门槛放宽要记录是谁、研究代理的工具范围里没有"改门槛" | **E 流程**（`oc research iteration` 门） | S–M | 不重复 |
| 4 | **LuxAlgo edge-stats 的"统计诚实信封"**：任何百分比必带 N、Wilson 区间、半段稳定性、分年计数，N<10 不出估计 | **B 报告**、**C 频率**（日内条件概率探索） | S | 不重复 |
| 5 | **SPY 0DTE 看跌信用价差的一条自报线索 + 同一仓库的否定记录**（8 个任务里 6 个被否、1 个只是预注册，唯一晋级者是它；QQQ 复制品的一次性留出被用掉后被否）：2024-01 至 2026-08，629 个交易日，净 +55.7/+71.6 bps 价宽/日，盈亏平衡成本 0.5%–1% 价宽，**30% 的候选日因缺期权成交被跳过，样本无熊市年** | **期权线**（Alpaca 期权 1–3 级）：作为"便宜的否定测试"候选，不是结论 | M(需期权成交数据，覆盖待核对) | 不重复 |

### 不借鉴（摘要，详表见第 7 节）

Jev 包装的交易机器人、Robinhood Chain 代币/股票代币机器人、Polymarket 跟单机器人、A 股桌面应用、DeepSeek Harness 的 A 股插件、带返佣链接或自家代币的项目、星≈复刻的推广型仓库、"一句话回测"平台、EdotEnv（只有使命宣言）。

## 2. 发现方法与覆盖范围

**GitHub 搜索接口**（未认证，搜索 10 次/分钟，核心 60 次/小时；环境里没有 GitHub 令牌——只检查了变量名，没有打印任何值）：

- `created:>2026-08-01` + 排序按星数，每个关键词取前 50：vibe trading、vibe investing、trading agent、AI trader、LLM trading、quant agent、alpha agent、factor mining、backtest agent、trading MCP、alpaca MCP、broker MCP、claude code trading、codex trading、trading skills、polymarket agent、prediction market agent、crypto trading agent、hyperliquid agent、AI hedge fund、autonomous trading、agentic finance、vibe-trading、stock agent LLM、quantitative research agent、trading bot LLM、algo trading claude、finance agent skills（28 个）。
- 通用词补查（trading / stock / quant / finance agent / investing / backtest / polymarket / hyperliquid / crypto agent / topic:*），再加 16 个主题词（autoresearch、alpaca paper trading agent、robinhood agentic trading、deepseek harness quant、jev trading、self-improving trading agent 等）。去重后得到 1,276 个新仓库。
- `pushed:>2026-08-01 stars:>1500` 的老项目：28 个，其中 8 月后明显动静的见第 3 节。
- 同窗口对比计数：12 个关键词在 2025-08-01–10-04 与 2026-08-01–10-04 两个窗口的仓库数（含 ≥50 星子集）。

**其他渠道**：

| 渠道 | 状态 |
|---|---|
| Hacker News（Algolia API，`created_at_i>1754006400`，14 个查询） | **已覆盖**。8 月后相关帖：WSJ《Americans are vibe-coding trading algorithms》（09-06，10 分，付费墙，只见标题）；Show HN: LLMs each trading $100K vs a frozen rulebook（08-17，12 分，即 aitradingcompetition.com）；Launch HN: EdotEnv(YC S26)（08-04，39 分）；TradingAgents（09-08，120 分，81 评论）；The0（07-20）。 |
| Trendshift（今日/本周/本月前 25 名） | **已覆盖，但只有前 25**。三档里没有交易项目；本周出现 `deepseek-ai/deepseek-harness`。 |
| Reddit（r/algotrading、r/ClaudeAI、r/LocalLLaMA JSON 接口） | **被拦**，三个都返回 403。 |
| X | **没有**（`twscrape` 未安装，按边界不装）。 |
| WebSearch | 用于核实：Robinhood Agentic Trading、Robinhood Chain、TypeSafe Jev、Karpathy autoresearch、Alpaca 黑客松。 |
| 星数增长抽样 | **失败**：`/repos/{r}/stargazers` 现在未认证返回 401。OSS Insight 的星历史接口数据标明"degraded"（OpenAlice 显示 1,210 星，实际 7,208），**弃用**；star-history.com 对未认证请求返回 403。 |

**8 月以来新增星数的估计口径**：创建日在 8 月 1 日之后的项目，当前星数就是 8 月以来新增（未扣取消星标）；老项目只有 T-76 的 17:54Z 取数与 10-05 04:35Z 取数两个时点的**速率**（间隔 10.7 小时，夜间，偏低），逐行见表。

**星数可信度检验**：部分仓库星≈复刻（TetreesAgent_EX 304/307、polymarket-tennis 274/232）或复刻远多于星（ai-robinhood-chain 134 星/963 复刻），是推广或空投式星标的特征；jev-trader 2,799 星/524 复刻、一次推送、发布当日爆星。atlas-gic 的 README 写 944 星而 API 为 2,307，且有同名克隆仓库（Army161/atlas-gic，0 星）。

## 3. 新项目总表

星/复刻/推送/许可证取数时间见 JSON。"读过"的深度在卡片里写明。证据等级：无 / 只有回测 / 模拟盘 / 实盘自报 / 实盘可核验。**取向**是对我们的建议。

| 项目 | 创建日 | 星 | 复刻 | 8 月以来新增星(估) | 类别 | 一句话 | 证据等级 | 取向 |
|---|---|---:|---:|---|---|---|---|---|
| [ProjectDXAI/continuous-record-llm-trading-agents](https://github.com/ProjectDXAI/continuous-record-llm-trading-agents) | 2026-09-01 | 79 | 0 | 79(=总星) | G 测量研究 | DXRG 论文 arXiv 2609.05663 配套数据：3,505 个真币金库 21 天 + 500–599 个 Hyperliquid 永续代理 69 天，无方向性优势 | 实盘自报(聚合数据，同一实验室，未独立复现) | 借鉴 |
| [swiftward/swiftward-alpaca-options-agents](https://github.com/swiftward/swiftward-alpaca-options-agents) | 2026-08-23 | 4 | 0 | 4(=总星) | D 券商/护栏 | Alpaca 模拟盘期权代理：代理手里没有券商密钥，订单经它改不了的风控引擎放行/拒绝，34 条'避免的失败'清单 | 模拟盘(4 个交易日，账号公开，自报 +2.59% 对 SPY +0.76%) | 借鉴 |
| [mrnetwork0001/Deflow](https://github.com/mrnetwork0001/Deflow) | 2026-09-01 | 1 | 0 | 1(=总星) | D 券商/护栏 | Alpaca 模拟盘多代理期权台：4 个代理提案、12 个确定性断路器裁决，哈希链账本，首日 190 次拒绝对 5 次成交 | 模拟盘(自 09-01 起公开账本，未核验) | 部分借鉴 |
| [henryzhangpku/autonomous-quant-researcher](https://github.com/henryzhangpku/autonomous-quant-researcher) | 2026-09-17 | 1 | 1 | 1(=总星) | B 自动研究环 | LLM 只提严格 JSON 假设，可信代码评估；发现→验证→一次性留出墙；哈希链试验账本；附 8 个任务的结论(多数被否) | 只有回测(含自报否定结果与 1 个有条件幸存者) | 借鉴 |
| [fidetolabs/qanat](https://github.com/fidetolabs/qanat) | 2026-09-05 | 289 | 52 | 289(=总星) | B 自动研究环 | 量化因子 MCP 服务器：逐日回放只读当日行、试验计数驱动显著性门槛、门槛放宽留痕、按范围裁剪工具 | 无(工具，无业绩声明) | 借鉴 |
| [kyky2347/ALTA](https://github.com/kyky2347/ALTA) | 2026-08-27 | 1,038 | 122 | 1038(=总星) | A 研究工作台 | 4 个 Scout + 双独立评审(互不可见) + 代码排名 + 表达代理 + 独立审计；影子账本/券商 API 两种执行；基于改造的 Codex harness | 无(明说'未证明 alpha'，916 个软件测试) | 部分借鉴 |
| [Sixian-Li/plain-backtest](https://github.com/Sixian-Li/plain-backtest) | 2026-09-26 | 96 | 14 | 96(=总星) | F 回测/工具 | 自然语言→冻结实验→PyBroker 执行+独立账本对账→哈希化报告；83 个实验定义，3 个技能 | 只有回测 | 部分借鉴 |
| [YellowPancake/quant-autoresearch](https://github.com/YellowPancake/quant-autoresearch) | 2026-09-15 | 22 | 3 | 22(=总星) | B 自动研究环 | Karpathy autoresearch 搬到量化：代理只改 strategy.py，数据切分和评估器固定，同时报冻结冠军与事后最好 | 只有回测(自报；A 股/宽基指数为主) | 部分借鉴 |
| [heranliu/AlphaResearchOS](https://github.com/heranliu/AlphaResearchOS) | 2026-09-22 | 77 | 0 | 77(=总星) | B 自动研究环 | 本地研究工作台：假设→特征+模型→开发评估→独立会话评审→留出；9 只美股行业 ETF 基准 | 只有回测(2023-05 至 2026-09 留出 841 日，自报) | 对照基线 |
| [Simreal-AI/Xitadel-QuantBench](https://github.com/Simreal-AI/Xitadel-QuantBench) | 2026-09-21 | 102 | 8 | 102(=总星) | C 评测/竞技场 | 订单簿回放基准：代理写策略，在没见过的一天上对照同日最佳人类选手评分；留出日只发布哈希 | 模拟(仿真器回放，榜单自报) | 部分借鉴(只借原则) |
| [oaia-fun/code](https://github.com/oaia-fun/code) | 2026-08-21 | 0 | 0 | 0(=总星) | C 评测/竞技场 | 加密代理基准：每个代理对 2,048 个抛硬币影子代理评百分位；预测按 sha256+ed25519 签名提交 | 前向(加密，自报) | 部分借鉴 |
| [caiovicentino/eikos](https://github.com/caiovicentino/eikos) | 2026-09-23 | 41 | 1 | 41(=总星) | B 模型 | 开源(MIT)类型化决策模型 4B/27B：一次前向给出每个选项的校准概率，附训练/量化/评测全套 | 无(厂商自测，对 Jev 比较) | 观察 |
| [caiovicentino/eikos-arena](https://github.com/caiovicentino/eikos-arena) | 2026-09-24 | 7 | 3 | 7(=总星) | C 评测/竞技场 | Eikos-27B 对 Jev，14 个 Hyperliquid 永续各 $10,000 模拟，每 5 分钟同一快照 | 模拟盘(3 天，作者称'大半是运气') | 不借鉴 |
| [jarrodwatts/jev-trader](https://github.com/jarrodwatts/jev-trader) | 2026-09-16 | 2,799 | 528 | 2799(=总星) | E 链上/加密 | 每个 Monad 区块让 Jev 判买卖，在 Kuru MON-USDC 挂只做 maker 单 | 无(默认 dry-run，mock 模型) | 不借鉴 |
| [LuxAlgo/edge-stats](https://github.com/LuxAlgo/edge-stats) | 2026-08-25 | 100 | 30 | 100(=总星) | F 回测/工具 | 条件概率查询引擎 P(结果|条件)，每个结果带 N、Wilson 95% 区间、半段稳定性、分年计数；10 个只读 MCP 工具；有 Alpaca 1 分钟适配器 | 无(统计工具，明说不是预测) | 借鉴 |
| [LuxAlgo/broker-sdk](https://github.com/LuxAlgo/broker-sdk) | 2026-08-24 | 25 | 18 | 25(=总星) | D 券商/护栏 | 统一券商连接 API，面向代码、应用和 AI 代理 | 无 | 观察 |
| [Loopera-ai/loopera](https://github.com/Loopera-ai/loopera) | 2026-09-08 | 459 | 76 | 459(=总星) | B 自动研究环 | 基本面因子研究代理(A 股财报)；仓库只有产品资料，不发布源码，BSL 1.1 | 无 | 不借鉴 |
| [Superior-Trade/trading-terminal](https://github.com/Superior-Trade/trading-terminal) | 2026-08-21 | 316 | 17 | 316(=总星) | D 券商/护栏 | Hyperliquid AI 终端：在图上画线→代理生成 Freqtrade 策略，验证器拒绝不安全策略 | 无 | 观察(docs/strategy-pipeline.md 未读) |
| [zhu1090093659/dsh-trading](https://github.com/zhu1090093659/dsh-trading) | 2026-08-30 | 226 | 23 | 226(=总星) | A 研究工作台 | 基于 DeepSeek Harness 的多市场 AI 终端，默认 dry-run，人工批准实盘；PolyForm Noncommercial | 无 | 不借鉴 |
| [yuanwang589-dev/deepseek-harness-quant](https://github.com/yuanwang589-dev/deepseek-harness-quant) | 2026-08-16 | 226 | 78 | 226(=总星) | A 研究工作台 | DSH 上的 A 股低频决策系统 | 无 | 不借鉴 |
| [MariusOTB/OpenTrade-Agent](https://github.com/MariusOTB/OpenTrade-Agent) | 2026-08-25 | 135 | 201 | 135(=总星) | D 券商/护栏 | macOS 应用：让 Claude Code/Codex 代理经 Robinhood 官方 MCP 在专用账户里下单，带批准、回合上限、逐代理订单记账；Elastic License 2.0 | 无 | 观察 |
| [0xethanq/astra-quant-agent](https://github.com/0xethanq/astra-quant-agent) | 2026-08-30 | 340 | 108 | 340(=总星) | E 链上/加密 | OKX 加密多模型委员会 + 确定性风控；README 内含返佣链接；AGPL+Commons Clause | 无 | 不借鉴 |
| [mogons/noraz-agent](https://github.com/mogons/noraz-agent) | 2026-09-11 | 223 | 167 | 223(=总星) | E 链上/加密 | Robinhood Chain 链上代币多代理共识信号，带自家代币链接 | 无 | 不借鉴 |
| [TetreesEX/TetreesAgent_EX](https://github.com/TetreesEX/TetreesAgent_EX) | 2026-08-29 | 304 | 307 | 304(=总星) | H 噪音/推广 | AI Pack 市场的 MCP 集成套件；星 304、复刻 307 | 无 | 不借鉴 |
| [nahrek/polyledger](https://github.com/nahrek/polyledger) | 2026-09-02 | 623 | 110 | 623(=总星) | E 链上/加密 | 可续跑的 Polymarket 索引器：CLOB 市场元数据 + Polygon OrderFilled 链上成交→DuckDB | 无(数据管线) | 观察(预测市场线的数据来源) |
| [nftechie/stonkfly](https://github.com/nftechie/stonkfly) | 2026-09-10 | 865 | 161 | 865(=总星) | H 噪音/推广 | 果蝇连接组模拟操作 Coinbase 账户；自述'尚未证明能学到盈利' | 无 | 不借鉴 |
| [jundizhou/easy-stock](https://github.com/jundizhou/easy-stock) | 2026-08-07 | 1,270 | 105 | 1270(=总星) | A 研究工作台 | A 股行情+题材+盘后复盘 AI 桌面工作台 | 无 | 不借鉴 |
| [brainbrick-trades/The-Quant-Trading-Vault](https://github.com/brainbrick-trades/The-Quant-Trading-Vault) | 2026-09-27 | 337 | 98 | 337(=总星) | H 噪音/推广 | '5800+ 策略解锁'，无许可证，仅一次推送 | 无 | 不借鉴 |
| [imikerussell/beebots](https://github.com/imikerussell/beebots) | 2026-09-25 | 234 | 110 | 234(=总星) | E 链上/加密 | 三个 Jev 驱动的 OKX 模拟交易'蜜蜂' | 无 | 不借鉴 |
| [muratmula/ai-robinhood-chain](https://github.com/muratmula/ai-robinhood-chain) | 2026-08-25 | 134 | 963 | 134(=总星) | H 噪音/推广 | Robinhood Chain 多代理加密生态；星 134、复刻 963 | 无 | 不借鉴 |
| [rp7o/trade-foundry](https://github.com/rp7o/trade-foundry) | 2026-08-18 | 9 | 2 | 9(=总星) | B 自动研究环 | '生成交易策略的 autoresearch 工厂' | 无 | 观察 |
| [chiefsmurph/alpaca-ai-agents-hackathon](https://github.com/chiefsmurph/alpaca-ai-agents-hackathon) | 2026-09-04 | 1 | 0 | 1(=总星) | D 券商/护栏 | 黑客松参赛：执行/风控层的干净室参考实现，27 个可运行测试(含'成交中卖价上涨 50% 不得越过到达价上限') | 模拟盘(闭源 alpha，开源只是风控参考) | 部分借鉴 |
| [ihsieh31/traders](https://github.com/ihsieh31/traders) | 2026-09-03 | 1 | 0 | 1(=总星) | D 券商/护栏 | 只限模拟盘的多代理研究/风控/执行韧性框架，1,919 个测试，'模拟盘恢复门' | 无(明说不证明 alpha) | 观察 |
| [EkoTerminal/eko](https://github.com/EkoTerminal/eko) | 2026-10-02 | 0 | 0 | 0(=总星) | E 链上/加密 | Robinhood Chain 上给交易代理的 harness：感知、护栏、飞行记录仪 | 无 | 不借鉴 |
| [livetennisapi/polymarket-tennis](https://github.com/livetennisapi/polymarket-tennis) | 2026-08-18 | 274 | 232 | 274(=总星) | E 链上/加密 | Polymarket 网球市场工具(只观察)；星 274、复刻 232 | 无 | 不借鉴 |
| [chrisworsey55/atlas-gic](https://github.com/chrisworsey55/atlas-gic) | 2026-03-11 | 2,307 | 416 | 见备注 | A 研究工作台 | 25+ 个代理按 Sharpe 改写提示词(autoresearch)，自称实盘+22%/173 天；README 写 944 星，API 为 2,307 | 实盘自报(未核验；回测含模型训练截止日暴露) | 不借鉴 |
| [TraderAlice/OpenAlice](https://github.com/TraderAlice/OpenAlice) | 2026-02-18 | 7,208 | 1135 | 见备注 | A 研究工作台 | 本地研究工作台：Claude Code/Codex 等代理 + 行情工具 + AutoQuant(量化实验)和 Auto Prediction(预测市场)工作区；AGPL-3.0 | 无 | 观察 |
| [tradermonty/claude-trading-skills](https://github.com/tradermonty/claude-trading-skills) | 2025-10-19 | 2,947 | 667 | 见备注 | F 回测/工具 | Claude 技能式交易流程：每个工作流有机器可读 YAML(技能、决策门、产物)，含交易记忆和信号事后复盘 | 无 | 观察 |
| [quantskills/quantskills](https://github.com/quantskills/quantskills) | 2026-06-25 | 2,385 | 133 | 见备注 | F 回测/工具 | PandaAI 发起的量化技能目录：214 项资产分 10 类，含'前视/幸存者/Walk-forward/校准'12 项 | 无 | 观察 |
| [alsk1992/CloddsBot](https://github.com/alsk1992/CloddsBot) | 2026-01-26 | 2,897 | 339 | 见备注 | E 链上/加密 | 预测市场/加密/永续/代币发行的 21 平台聊天交易机器人，黑客松 12 天作品 | 无 | 不借鉴 |
| [HKUDS/Vibe-Trading](https://github.com/HKUDS/Vibe-Trading) | 2026-04-01 | 34,714 | 5634 | 见备注 | A 研究工作台 | (T-76 已评)老牌；8 月后仍在快速改版 | 只有回测 | 借鉴(见 T-76) |
| [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) | 2024-12-28 | 109,796 | 21107 | 见备注 | A 研究工作台 | (T-76 已评)0.4–0.6 的前视修复 | 只有回测 | 借鉴(见 T-76) |


另有约 1,230 个新仓库没有逐个看，主要是：Robinhood Chain 代币/股票代币机器人（`robinhood` 关键词 88 个）、Jev 包装（113 个）、Alpaca 黑客松期权代理（`alpaca agent` 767 个，抽看了十几个）、DeepSeek Harness 插件（19 个）、Polymarket 机器人（80 个）、印度 NSE/中国 A 股桌面应用。去重后的完整列表没有保存进仓库；JSON 里只放表中的 42 项和计数表。

### 同窗口对比计数（仓库数，窗口 8 月 1 日–10 月 4 日；括号内为 ≥50 星）

| 关键词 | 2025 | 2026 | 倍数 |
|---|---:|---:|---:|
| trading agent | 603 (6) | 3,459 (11) | 5.7× |
| LLM trading | 138 (4) | 640 (5) | 4.6× |
| trading MCP | 88 (4) | 624 (5) | 7.1× |
| alpaca agent | 9 (1) | 767 (0) | 85× |
| claude trading | 40 (2) | 443 (1) | 11× |
| quant agent | 87 (2) | 518 (7) | 6.0× |
| backtest agent | 32 (0) | 220 (4) | 6.9× |
| trading skills | 107 (0) | 397 (1) | 3.7× |
| vibe trading | 20 (0) | 104 (0) | 5.2× |
| polymarket agent | 8 (0) | 80 (0) | 10× |
| hyperliquid agent | 7 (1) | 53 (2) | 7.6× |
| AI hedge fund | 42 (0) | 78 (1) | 1.9× |

说明：关键词按名称、描述、README 匹配，同一仓库会被多个关键词重复计数；GitHub 对搜索总数有近似。取数 2026-10-05 04:4x UTC。"alpaca agent"85 倍几乎全部来自黑客松。

## 4. 项目卡片

每张卡写：做什么、架构、评估、与 T-76 老项目比新在哪、许可证、我们能借什么、风险。**除特别注明外都只读了 README/文档，没有审源码。**

### 4.1 测量研究：DXRG《What LLM Trading Agents Actually Do in Production》

- **来源**：`ProjectDXAI/continuous-record-llm-trading-agents`（79 星，CC-BY-4.0，09-01 创建）；arXiv 2609.05663（2026-09-04 提交）。读过 README、DISCUSSION；论文的 17 条规则与费用口径来自 WebFetch 对 arXiv HTML 的转述（快照 `web__arxiv-2609.05663-abs.md` 只含摘要接口，规则清单没有逐字落盘，**待核对**）。
- **做什么**：同一设计谱系的两个部署。DX Terminal Pro：3,505 个用户出资的金库在 Base 链上交易真 ETH，21 天（2026-02-26 至 03-18），Qwen3-235B，约 750 万次调用、约 30 万次链上动作、约 $2,000 万成交额。DXAP：500–599 个用户创建的代理在 Hyperliquid 永续上，69 天（06-08 至 08-15），**主要是按实时价格的纸上执行加一小本真币账**（6/19 个用户的 5,035 笔真币成交，已标注），231,638 个多工具回合，14,596 笔成交。
- **关键发现（作者自报，聚合数据，同一实验室，未经独立复现）**：
  1. 行为由"操作层"决定，不是策略文字：风险滑块解释杠杆（每档 +0.425），代理固定效应吸收 60% 方差，提示里渲染的九行排行榜决定 46.5% 的入场，回归断点正好落在渲染边界（1.75 倍）。
  2. **仓位对波动盲**：中位杠杆在每个波动六分位都是 5.0 倍（波动相差 5.7 倍）；一个姿态+滑块组合占 11% 仓位却占 62% 爆仓；在提示里告知强平距离没有变化。
  3. **代理够到了利润却留不住**：43.2% 的仓位在 24 小时内触及 +300 bps 浮盈，其中 49.3% 最终亏损收场，中位捕获率 2.0%；**固定 2%/4% 括号出场胜过测过的每一种自由裁量出场，每仓 +39.0 bps**（作者强调这是记录仓位上的配对反事实，不是可部署策略）。
  4. 车队层面"没有方向性优势"，往返胜率 41% 对匹配散户基准（Hyperliquid 排行榜上 $1K–$100K 的 1,961 个交易者）的 50%；三个前沿模型在 416 个场景的回放联赛中决策质量并列，选择一致性差别很大（翻转率 35% 对 90%+）。
  5. 论文末尾 **17 条方法纪律**（"每一条都是用一次撤回或失败的主张换来的"，三个自家结论被撤回）：以交易日为推断单位；预注册分析带或报告全部扫描；要求优于具体基线；留窗交叉验证而非随机切分；每个实验臂做置换零假设；对"已成交"条件化属事后处理(仅描述)；偏好显示偏好指标；**代理文本不能提拔实验，只有重建的成交可以**；接受组间差异前先查日历足迹；读完整回合(曾因只读最后一条消息出过 argmax 错误)；跨时代按相同费率比较(builder 费 4.5→14.5→5.5 bps，统一重述为 5.5)；检查主指标排除了什么；看 P&L 表前先对零假设臂校准；传输成功不等于工具成功(错误载荷在信封里)；滚动 p 值多次查看无效；警惕偏好稀有事件姿态的栖息地选择偏差；**时点运气下限**(调度 ±15 分钟偏移让结果在 -88 和 +21 美元之间摆动)。
- **新在哪**：T-76 里没有任何项目给过**人群级**的实测；这是第一个有规模的"代理实际做了什么"的记录，结论为负。
- **评估怎么做 / 可核验**：附聚合数据和图的 CSV；逐笔数据不公开；HuggingFace 上另有两个数据集（未打开）。不可独立复现；实验室自己的产品是 DXAP，存在利益。
- **局限**：永续合约与 memecoin 池，不是美股；加密；"2026-08-15 之后的系统已改版"，论文只是改版前基线。
- **我们能借**：见第 6 节第 1 项。

### 4.2 Alpaca 黑客松系：期权代理与"风控引擎代理改不了"

**事件**：lablab.ai × Alpaca "AI Trading Agents Hackathon"，2026-08-28 至 09-04，在线，奖金池 $5,000，用 Alpaca Trading API、MCP 服务器和 CLI 建 AI 交易代理（WebSearch 转述 lablab 页面，未打开原页；我对 lablab 里 milan-ai-week 那个页面的 WebFetch 返回的是另一个黑客松，已弃用）。参赛作品普遍用 Alpaca 模拟盘 + 期权，**评估是 4 个交易日（8 月 31 日开盘至 9 月 3 日收盘）的账户净值**。

#### swiftward/swiftward-alpaca-options-agents（4 星，MIT，08-23 创建，最后推送 09-04）

- **读过**：README、`docs/failures-this-avoids.md`（34 条，我读了前面约十条与目录）。
- **做什么/架构**：代理（一个模型会话）住在私有网络里，**手里只有风险引擎的地址和令牌，没有券商密钥**；订单经风险引擎放行或拒绝（拒绝时报规则名），思考经模型网关，其他一切经主机白名单代理；Alpaca MCP 服务器持有唯一的券商密钥。代理的行为是一份声明文件（唤醒窗口、可加载的剧本、所有数字），测试会拒绝一个没说明出处的数字。窗口可以命名场合（财报、宏观数据），**不能命名交易**。只做定义风险的期权结构（OTM 信用价差、反向价差、两个事件押注），**一单多腿**（`order_class=mleg`），按到期最坏损失定仓位而不是按权利金；三层上限（单仓、同向合计、全账户），阈值来自 646 个交易日的期权价格测量（其中一次测量删掉了他们交易过的一条规则）。
- **评估**：账户 `PA3BXFR0ZVYC`（Alpaca 模拟盘）从 $100,000 到 $102,588.74（+2.59%），同期 SPY +0.76%。作者明说："四个交易日分不开技能和运气"；公开 25 个数字，`make claims` 无凭证无网络重算。**无成本口径之外的核验**，我没有重算。
- **新在哪**：T-76 里没有"代理与券商密钥隔离 + 风控服务代理改不了"这种结构；也没有把"每个能拒绝交易的规则都配一个去掉规则就变红的测试"当作验收。
- **我们能借**：第 6 节第 2 项。
- **风险**：4 个交易日，+2.59% 是噪声量级；真正的价值是那份失败清单。

#### mrnetwork0001/Deflow（1 星，README 标 MIT）、chiefsmurph/alpaca-ai-agents-hackathon（1 星）、ihsieh31/traders（1 星）等

- **读过**：Deflow README 的检索行（约 30 行命中，没有通读）；Silver Lynx 与 traders 的 README 开头。
- Deflow：4 个代理提案、12 个确定性断路器裁决（单笔最大亏损 ≤2% 权益、账户 |vega| ≤ 每 $1,000 权益 2.5 等）；"提交不等于成交"：工作单持久化，券商确认成交才改账本；首个实盘日 190 次拒绝对 5 次成交；账本带哈希链；**踩过的坑：某个接口（我读到的行里没点名是 Alpaca 的哪一个）在 equity 字段里返回了收益序列，未校验时画成"+133.68% 收益"**，现在曲线拒绝非权益口径序列；这条对我们读 Alpaca 账户历史时同样适用，待核对。
- Silver Lynx：开源的只是执行/风控参考层，27 个可运行测试，其中一个把卖价在成交中抬高 50% 并断言**任何产出价格都不得越过以到达价锚定的上限**；以及把大型嵌套持仓压缩 ~100 倍进提示的"两层标量投影"。
- ihsieh31/traders：只限模拟盘，1,919 个测试，"模拟盘恢复门"；README 明说不证明 alpha。
- **共同点**：把"模型是最不可信的部件"当设计原则。**没有一个有够长的结果。**

### 4.3 自动研究环：把 Karpathy autoresearch 搬到交易

背景：Karpathy 的 autoresearch 于 2026-03-07 发布（检索转述），"代理便宜，围绕它的循环才是产品"。以下四个是 8 月后的交易版本，**防自欺的程度差别很大**。

#### henryzhangpku/autonomous-quant-researcher（1 星，MIT，09-17 创建，10-04 仍有推送）

- **读过**：README、`spy-odte-credit/FINDINGS.md`、`qqq-0dte-holdout/HOLDOUT-SPEND.md`（快照已存）。
- **做什么**：LLM 只提**严格 JSON 假设**（一个入场分钟、一个在批准的因果观测上的有界布尔信号、一个定义风险的期权结构），没有可执行代码字段，所以没有东西要沙箱；确定性评估器在不可变的按时间切分数据上跑，**发现→验证→一次性留出墙**；留出只能由人显式打开一次，先写持久回执，**评估失败也算用掉**；准入先去重（语义重复、近似重复=拧一个旋钮、假设族配额），所以 50 次试验买到 50 个不同想法；账本哈希链、只追加；**预算耗尽不等于成功**；验收是门集合（成本后正边际、净 P&L 正、周聚类 bootstrap 下界为正、提高成本后仍正、分年稳定、样本下限），排名分只在过门者之间选择。
- **结果（自报，只有回测，无前向）**：8 个任务里 **1 个有条件晋级、6 个被否、1 个只是预注册**。被否的：`bars-rules`（8 只 ETF 的 232 个预注册单规则格子，4 个发现期通过者 0 个晋级，四个都是同一个特征的多空两个方向，即"多头 beta"而不是规则）、`ta-premises`（斐波那契、回归通道、均线带、支撑位：**每个前提都在验证期失败**，一个过了九个发现门后每日亏 22 bps）、`smartfit-channels`、`overnight-spx`（40 次试验无候选通过发现期）、`kalshi-btc-hourly`（138 个假设零个通过，唯一形式通过者是已记录的前视伪影）、QQQ 0DTE（发现期幸存者，一次性留出被用掉后被否）。**唯一幸存者**：`spy-odte-credit`——SPY 0DTE 看跌信用价差，宽 5、短腿 OTM 5 点、10:00 ET 入场、持有到期按内在价值结算，**用实际成交的期权分钟线定价**，629 个交易日（2024-01-19 至 2026-08-10）；净 **+55.7 bps 价宽/日(发现，377 日)、+71.6 bps(验证，126 日)**，夏普 0.70/0.88，毛 +119.9 bps、胜率 95.2%；**盈亏平衡成本在 0.5% 与 1.0% 价宽之间**（0.5% 全过，1.0% 时发现期 +5.7、验证 +21.6 但两半一致和加倍成本门失败，1.5% 为负）。作者自己列出的局限：成本是假设不是实测；898 个候选日里 **269 个（30%）因缺期权成交被跳过**，偏向可交易日（乐观方向）；只有一种几何（宽 5/偏 5，未扫描）；只持有到期，无止损；**样本无熊市年和波动冲击**。
- **新在哪**：T-76 的 `Vibe-Trading` 有"同宇宙随机对照"，但没有"一次性留出回执 + 准入去重 + 预算耗尽不算成功"这种把自欺堵死的机制，也没有把**否定结果当主要产出**公开。它和我们的预注册流程是同类，最像的是 `oc research iteration` 门。
- **我们能借**：第 6 节第 3、5 项；同时**把它的否定结果当作现成的负面证据**：8 只 ETF 单规则格子、TradingView 趋势脚本前提、overnight SPX——在我们重开这些方向前先对照。
- **风险**：1 星，一人项目；所有结果是作者自报，没有第三方复现；SPY 0DTE 是**短波动溢价**，尾部风险是它的真实成本，2024 年以来的牛市样本不能说明这一点；我没有审其代码。

#### fidetolabs/qanat（289 星，MIT，09-05 创建，09-30 推送）

- **读过**：README、`docs/backtest.md`。
- **做什么**：量化因子的 MCP 服务器：一个 `qanat.yaml` 定义数据源和步骤；**逐日回放，每步只读当日已存在的行**，`ctx.read()` 拒绝步骤未声明的表；出费用和滑点后的组合；DuckDB 存储；明说**不下单**。
- **评估纪律（新东西）**：(1) **试验计数**——`record_trial`/`list_trials` 记录你问了多少个不同问题，`bar.rule: count` 把显著性除以尝试次数，`floor` 是固定 t 值，`gate: true` 时没过门就**不能把结果叫"live"**；(2) **放宽门槛要记录是谁做的**，"因为提出策略的东西也是能移动线的东西"；(3) **工具范围分三档**（data 6 个工具 / research 19 个 / 默认 31 个），`set_bar` 只在最高档，所以研究档的代理能记录它试了什么，**不能降低对它的要求**；(4) `live_from` 日期在行存在之前盖章，"live 是唯一不能靠看得出来的期间"。作者自己写明两个局限：窗口没封，"点时视图阻止步骤看到未来，但没有东西阻止代理在决定试什么时读过某个日期之后"；"没有搜索目标，因为提出策略并保留赢家的循环，在门槛拦住而不是只报告之前，是一种昂贵的自欺方式"。
- **新在哪**：T-76 没有"代理的工具范围里没有改门槛"这一条。
- **风险**：beta，作者自称"几乎没有别人运行过"；美股/Alpaca 不是它的重点。

#### YellowPancake/quant-autoresearch（22 星，MIT，09-15 创建）与 heranliu/AlphaResearchOS（77 星，MIT，09-22 创建）

- **读过**：两者 README。
- quant-autoresearch：代理只改 `strategy/strategy.py`，`prepare.py` 封住训练/验证/最终测试切分，留出放在兄弟目录（作者承认"目录隔离和哈希不是沙箱"）。**同时报冻结冠军和事后最优**：宽基指数研究 488 次尝试，事后挑的 #162 测试期 +172.52%（CAGR 31.24%，最大回撤 30.05%），**验证期选出并冻结的 #478 测试 CAGR 只有 23.33%**；CSI300 #84 事后 +77.30% 对冻结 #178 的 12.93% CAGR。作者注明"验证集上的持续改进不一定转化为更好的测试表现"。这个"事后挑和冻结的差距"是现成的选择偏差量化，对象是 A 股和宽基指数，成本 0.03%/边。
- AlphaResearchOS：本地工作台，假设→特征+模型→开发评估→**独立模型会话评审**→留出。美股 9 只行业 ETF 基准：开发期到 2023-05-08，之后 841 个交易日留出（2023-05-11 至 2026-09-17），双特征 Ridge 选前 3、每 5 个交易日调仓、单边 10 bps：总收益 117.53%、CAGR 26.22%、夏普 1.56、最大回撤 -16.21%；对照等权 63.22%/1.27/-15.61%，60 日动量 65.63%/1.18。40 bps 时 92.15%。**自报，未核验，牛市窗口；我读到的 README 部分没有写出两个特征具体是什么**。可作为我们行业 ETF 线的现成对照基线（见第 6 节）。
- **新在哪**：无新方法，价值在于**冻结 vs 事后**和**行业 ETF 留出基线**两组公开数字。

#### CamusGIT/EvoQuant（152 星，Apache-2.0，08-17 创建）、rp7o/trade-foundry（9 星）

- EvoQuant（读过 README）：基于 DeepAgents/LangGraph 的自进化量化研究代理：券商研报 PDF→结构化知识库→锚点优先的想法生成（继承 ≥70% 锚点方法、≤30% 创新增量，用 ELO 锦标赛排序）→在离线行情上跑因子实验，指标为 IC/ICIR/RankIC。**无任何业绩，只有 IC 流水线；A 股研报语境。**
- trade-foundry 只读了元数据，"生成交易策略的 autoresearch 工厂"，无结果。
- 另有 `JingHao-Leon/dsh-alpha-desk`、`Shelpid/SETS` 两个 README 已抓取（快照在目录里）但**没有细读**，不下结论。

### 4.4 评测/基准/竞技场

#### Simreal-AI/Xitadel-QuantBench（102 星，MIT，09-21 创建）

- **读过**：README。公开预览：7 个任务（单品做市、篮子与成分、期权对标的、带关税与仓储的外部转换、多资产带对手身份），代理写 Python 策略，在没见过的一天上**对同日最好的人类比赛策略**评分；人类 = 80 分，榜单（自报）GPT 6 77.28、GLM 5.3 30.12、Kimi K3 27.68、DeepSeek V4 Pro 24.58，**无模型超过人类**；留出日只公开哈希（`COMMITMENT.json`）。**风险计入分数**：`max(0, P − 0.1×D)` 乘夏普质量因子，作者举例：修复一个人类策略的三个逻辑缺陷使 P&L 提高 63% 而夏普从 7.27 降到 3.03，"只按 P&L 排名会得出相反结论"。这与我们的"先看夏普、不看规模"规则同向。
- **局限**：做市/订单簿类任务，与我们的低频美股线不对口；撮合引擎与留出日不在仓库里，**无法核验**。

#### oaia-fun/code（0 星，MIT）与 aitradingcompetition.com 与 caiovicentino/eikos-arena

- oaia：加密代理的公开基准，每个代理对 **2,048 个做同样交易的抛硬币影子代理**评百分位；预测 `agent、pair、direction、size_pct、horizon、p、ts_commit` 以 `sha256(规范 JSON + 32 位随机数)` 提交并 ed25519 签名；MCP 服务器公开读。**这就是我们的"安慰剂"思路做成公共榜单**；只做 BTC/ETH/SOL、1/4/24/168 小时。
- aitradingcompetition.com（HN 08-17 Show HN，12 分）：约 20 个机器人，ChatGPT/Claude/Grok/Gemini 四家，**纸上交易**，每个机器人对标普 500；"Super Bot"每天按全擂台的证据改写规则；第一名 Patience·Grok +45.58%（"自 7 月 28 日"，约 75% 满仓，最多 40% 押在下跌上，61% 胜率/335 笔），标普同期 +4.16%；页面无成本与滑点信息。**自报、牛市窗口、无成本、不可核验。**（网页由 WebFetch 转述，快照为原始 HTML。）
- eikos-arena：Eikos-27B 对 Jev，14 个永续各 $10,000 模拟，每 5 分钟同一快照、28 个问题，同时按 Brier 分数评估；作者自己写"三天的结果大半是运气"。

### 4.5 券商/MCP/执行类

- **Robinhood Agentic Trading**（官方，2026-05-27，检索转述）：为外部代理开**专用 MCP 账户**（自主个人账户，最多 10 个自主账户含它），代理可交易股票（测试版）、计划加期权/加密/期货；支持 Claude Code、Codex、ChatGPT、Cursor 等。8 月后的仓库 `MariusOTB/OpenTrade-Agent`（135 星，复刻 201，Elastic License 2.0）是 macOS 应用，用 Claude Code/Codex 代理经该 MCP 下单，带手动/自动批准、后台回合上限、逐代理订单记账。**它是实盘，不在我们的范围内**；可借的只是"专用账户、逐代理记账"的做法。
- **Robinhood Chain**：2026-07-01 主网，24/7 股票代币，面向 120 多个国家。8–9 月出现大量 Robinhood Chain 代币机器人（noraz、ai-robinhood-chain、rh-*、EKO 等），**多为链上代币和 memecoin 信号，与我们无关**，部分带自家代币链接。
- **LuxAlgo 开源套件**：edge-stats（见 4.6）、broker-sdk（25 星，统一券商连接）、trade-relay（TradingView webhook/代理→券商执行中继）、luxalgo-mcp-server（84 星）。
- **Superior-Trade/trading-terminal**（316 星，Apache-2.0）：Hyperliquid 上"在图上画线，代理生成 Freqtrade 策略"，**验证器拒绝不安全策略**，"每条规则都因为曾有策略不带它就上线而存在"（`docs/strategy-pipeline.md`，**未读**）。Hyperliquid 永续不在我们的范围。

### 4.6 工具类

#### LuxAlgo/edge-stats（100 星，MIT，08-25 创建，09-24 推送）

- **读过**：README。把 Alpaca/Binance/Coinbase/Databento 等 1 分钟数据同步进本地 DuckDB，一次派生会话特征，然后任何问题都是一条查询 `P(结果 | 条件)`，例如"周二缺口回补率"。**统计诚实信封**：点估计 + N + Wilson 95% 区间；N<30 警告、N<10 不出估计；前半/后半稳定性分裂；最近 250 个会话 vs 全历史；分年计数；连续结果给分布；"没有任何代码路径会打印不带样本量的百分比"；换日线和夏令时有测试夹具；期货换月日自动排除。10 个只读 MCP 工具。
- **我们能借**：第 6 节第 4 项。**风险**：它只给条件频率不给成本后收益；多重比较要自己管。

#### Sixian-Li/plain-backtest（96 星，MIT）

- **读过**：README。冻结实验后经 PyBroker 执行，再由**独立账本对订单和每日账户余额对账**，记录代码与数据哈希；三个技能；83 个实验定义；示例是 QQQ SMA20/100，次日开盘成交、5 bps/边。PyBroker 是 Apache 2.0+Commons Clause。**可借**：第二套独立账本对账（我们的回测与模拟盘对账已有，差异比对 S）。

#### nahrek/polyledger（623 星，MIT）

- **读过**：README 开头。可续跑的 Polymarket 索引器：CLOB 全部市场元数据 + 经 Envio HyperSync 流式取 Polygon 的 `OrderFilled` 事件→DuckDB，行与区块游标同事务提交，`(transaction_hash, log_index)` 幂等。**观察**：对预测市场线是现成的数据管线，不是研究结论。

#### Loopera-ai/loopera（459 星，BSL 1.1）

- 产品资料仓库，**不发布源码**，面向 A 股基本面因子；"假设→因子→证据门→记忆"流程只有描述。**不借鉴。**

### 4.7 研究工作台与"高星"项目

#### kyky2347/ALTA（1,038 星，Apache-2.0，08-27 创建，10-01 推送）

- **读过**：README、CHANGELOG（前 3.5 KB）、REPRODUCIBILITY（快照）。**这是本批里与我们结构最近的**（Codex App Server 作 harness，PostgreSQL，券商连接器含 Alpaca）。
- **做什么/架构**：四个 Scout（变化/事件、市场错位、因果/政策、预期差），各有自己的"交易者心智"（研究风格与累积教训）；每个机会是一个**带版本的、不可由代理改写的记录**（证据 + 假设 + 评审 + 表达 + 后续），证据区分**事件时间与检索时间**；**两个评估者各自提交意见之前互相看不到**，主持人只能从已存的记录出发、不能用共识补缺失来源；**排名由代码做，不是第三个代理投票**；表达代理比较最多三种收益方案，独立审计员选一个或"等待"；"等待"是合法结果；对立评审角色必须用不同模型，作者自己写"模型多样性是控制，不是统计独立的证明"。执行两种：影子（内部账本）或券商 API（六个连接器；Tiger/Alpaca/IBKR/Futu 有条件路径，其余被阻塞），**当前券商生命周期只支持"每账户一个活动计划、美元多头股票/ETF、整股、DAY 限价单"**，不支持期权和做空；出场是软件管理，"停止 ALTA 不会平仓"。
- **评估**：**没有任何业绩**。README 写："仍未证明：持续的样本外 alpha"；916 个软件测试、一次无订单的研究运行；"成功的搜索不是被证实的论点，被批准的论点不是成交，盈利的观察不是确立的 alpha"，把软件检查、已记录研究运行、前向投资结果分成三种证据。
- **新在哪**：对立评审"锁定视图"、事件时间/检索时间分离、前向结果归属到冻结的入场决策、校准只能收紧不能放松执行策略。T-76 的 TradingAgents 是辩论式的，这里是**提交-再披露**式的。
- **许可证**：ALTA 自身 Apache-2.0；内含改造过的 OpenAI Codex 快照（Apache-2.0）。
- **我们能借**：第 6 节第 7 项；**风险**：零结果，一个人项目；"独立审计员"和"评估者"若由同一类模型担任，独立性有限（作者自己承认）。

#### 老项目 8 月后的动静

- **HKUDS/Vibe-Trading**：34,714 星，当前约 194 星/天；T-76 已评。
- **TauricResearch/TradingAgents**：109,796 星，约 121 星/天；HN 09-08 一帖 120 分/81 评论；T-76 已评。
- **TraderAlice/OpenAlice**（2026-02-18 创建，7,208 星，AGPL-3.0，10-05 仍有推送）：本地工作台，Claude Code/Codex/OpenCode 等原生代理 + 行情工具 + **AutoQuant（量化实验）和 Auto Prediction（预测市场研究）专用工作区**，带 Git 历史的工作区、定时"Issue"、Inbox。星数近乎不动（10-04 17:5x 至 10-05 04:3x 增 1 星）。**观察**：它把"工作区 + 定时议题 + 收件箱"做成产品，与我们的"轮次+简报+队列"同构，无结果。
- **tradermonty/claude-trading-skills**（2025-10-19 创建，2,947 星，MIT）：机器可读的工作流清单（`workflows/*.yaml` 写明技能、决策门、产物），有交易记忆和信号事后复盘；明说不是信号服务。**观察**。
- **chrisworsey55/atlas-gic**（2026-03-11 创建，2,307 星，NOASSERTION）：25+ 代理按滚动夏普改写提示词，"提示词是权重，夏普是损失"；**自报**：18 个月回测，改动存活率 30%（16/53），部署期 "+22%/173 天"，最佳单笔 AVGO +128%；分群表在危机/加息期为 -13.1%/-30.2%/-29.0%（作者写"崩盘太快，自动研究来不及，代理必须预训练"）；作者承认瓶颈在"合成/决策层"。**不借鉴**：LLM 提示词优化回测暴露在模型训练截止日之前；星数口径不一致；有克隆仓库。
- **quantskills/quantskills**（2,385 星，无许可证字段）：PandaAI 发起的量化技能目录，214 项资产分十类，其中"研究验证与质量工具"12 项（前视、幸存者、Walk-forward/OOS、校准）；只是目录，**观察**，与 T-76 的 ml4t/skills 比对一起做一次差异比对即可。
- 其余（CloddsBot、AI-Trader、ai-hedge-fund、LangAlpha）8 月后无需补充，见 T-76。

#### Jev 生态与 Eikos

- **TypeSafe Jev**（2026-09-15 发布，检索转述，未打开官方页）：非 LLM 的"System One"模型，"非结构化状态进、类型化概率决策出"，一次并行前向给出每个选项的概率，训练方法称 RLCD（校准决策强化学习），定价约 $42/十亿输入 token，输出免费，响应亚秒；宣称 20–200 倍快、40–400 倍便宜。**发布后一周内冒出的 Jev 交易机器人**：jev-trader（Monad，2,799 星，一次推送）、beebots（OKX 模拟，234 星）、warrenduffer（印度 Nifty 50，94 星）、Jev-Trades、polymarket-btc5m-jev-trading 等。**全部默认 dry-run 或 mock，没有结果。**
- **caiovicentino/eikos**（41 星，MIT）：开源对手，4B/27B 类型化决策模型，一次前向读出每个选项的校准概率，附完整数据管线、训练、量化、评测；厂商自测"在 90% 以上置信度时错误率 2.4%（7,140 题、6 套）"。**我们自己的评估未做**。与机主的"GRPO Qwen 在 ≥9B 值得评估、27B 更好"相关（记忆：2026-09-30）。
- **对我们**：这是"LLM 作为可审计的信息接口，输出类型化的校准概率"的现成接口形态，与我们"LLM 输入必须先成为时点特征包"的规则同构；**不是 alpha 来源**。

## 5. 趋势综合

| 趋势 | 数据点 | 有结果还是只有演示 |
|---|---|---|
| **A. 黑客松驱动的 Alpaca 期权代理潮** | "alpaca agent"767 对 9；黑客松 08-28 至 09-04，评估为 4 个交易日净值 | **演示**。唯一有账号公开的自报 +2.59% 对 SPY +0.76%，4 天；价值在风控工程文档，不在收益。 |
| **B. "围绕代理的循环才是产品"（autoresearch 交易版）** | quant-autoresearch、autonomous-quant-researcher、atlas-gic、trade-foundry | **有结果的是否定结果**：autonomous-quant-researcher 8 个任务里 6 个被否、1 个有条件晋级；quant-autoresearch 公开了冻结 vs 事后差（+172% 对 23% CAGR）。 |
| **C. 类型化校准决策模型（Jev / Eikos）** | 09-15 发布，一周内十几个机器人 | **演示**，全是 dry-run；Eikos 竞技场 3 天"大半是运气"。 |
| **D. 券商官方代理通道** | Robinhood Agentic Trading（05-27）、Alpaca MCP v2（T-76）、OpenTrade-Agent、LuxAlgo broker-sdk | **基础设施，无业绩**。Robinhood 是实盘专用账户，不在我们范围。 |
| **E. 链上/加密/预测市场代理** | Robinhood Chain（07-01）、Hyperliquid、Polymarket；`polymarket agent` 80 对 8 | **演示/推广**；星≈复刻、自家代币链接常见。唯一有量的测量是 DXRG（负）。 |
| **F. 多代理"投委会"** | ALTA、ai-hedge-fund 系 | 无业绩；ALTA 的价值在记录结构。 |
| **G. DeepSeek Harness 插件热** | `deepseek-ai/deepseek-harness` 上了 Trendshift 周榜；dsh-* 插件 20 多个，A 股为主 | 无业绩，市场不对口。 |
| **H. 评测基准化** | Xitadel（对人类同日成绩）、oaia（对抛硬币影子代理）、aitradingcompetition | 基准的**方法**有借鉴价值（对安慰剂百分位、留出日哈希承诺）；榜单本身自报。 |

**有结果 vs 只是演示**：公开且量大的**测量**只有 DXRG 一份，结论是负的（没有方向性优势，输给匹配散户，仓位对波动盲，浮盈留不住）。其余"收益"都是自报、窗口极短（3–4 天）、无成本或牛市窗口。**没有人公开扣成本、够长、可核验的前向或实盘结果。** 这与 T-76 的结论一致；新增的一点是：8 月后的项目比 T-76 那批**更愿意**把"未证明 alpha"写在 README 第一屏（ALTA、traders、swiftward、stonkfly），说明这一类的做法在向"工程与审计"而不是"收益声明"收敛。

**对我们的位置**：我们的预注册 + 安慰剂 + 一次性留出 + 成本口径 + 分档投入，在这一类里属于**少数派的严格一端**（只有 autonomous-quant-researcher、Qanat 在同一水平）。这类项目能补的是：Alpaca 专用的通道失败清单、人群级的"代理怎么亏"的测量、统计信封的呈现规范，而不是研究方向。

## 6. 借鉴清单（按期望价值排序）

| # | 借什么 | 对应的线/模块 | 工作量 | 与 T-76 | 备注 |
|---|---|---|---|---|---|
| 1 | **DXRG 17 条方法纪律**（逐条核对哪些我们已有、哪些缺）+ 三个可测发现：固定括号出场对自由裁量出场；仓位对波动盲(强制而非请求)；调度偏移的"时点运气下限"；**跨时期按相同费率重述** | E 评估清单；D 线；A1 前向记录（日期中性） | S：先对我们已有的评估标准文档做差异比对半天，再在模拟盘成交上做一次括号出场对照 | 不重复 | 规则清单来自 WebFetch 转述，先读论文原文再落进标准 |
| 2 | **swiftward 的 34 条失败清单 + 风控引擎结构**；Deflow 的"工作单≠持仓"、权益口径校验、哈希链账本；Silver Lynx 的"成交中价格上涨 50% 不得越过到达价上限"测试 | A4（T-72）验收测试与清单；B 报告 | S–M：约 1–2 天，把每条改写为验收测试 | 部分重复（T-76 #1） | 增量是 Alpaca/期权/MCP 专用部分；代理不持有券商密钥的结构我们已有类似（Paseo 会话+脚本）需对照 |
| 3 | **研究环防自欺机制**：准入去重（语义/近似/族配额）、一次性留出持久回执（失败也算用掉）、预算耗尽≠成功、**报盈亏平衡成本**；Qanat 的"门槛放宽留痕"和"研究档工具范围里没有改门槛"、试验计数驱动显著性 | E：`oc research iteration` 门与 `direction-check` | S–M | 不重复 | 先 grep 看 `oc research` 已有多少，避免重造 |
| 4 | **edge-stats 的统计信封**：任何百分比带 N、Wilson 区间、半段稳定性、分年、N<10 不出估计；"没有不带样本量的百分比" | B 日报/周报生成器；C 频率（日内条件概率探索） | S | 不重复 | 只借规范，不安装；MIT |
| 5 | **SPY 0DTE 看跌信用价差线索**，以及同仓库的否定记录当现成负面证据（8 只 ETF 单规则格子 0 晋级、TradingView 趋势脚本前提全败、overnight SPX） | 期权线；方向登记（`oc research directions`）补负面条目 | M（需 Alpaca 历史期权成交覆盖，待核对）；负面条目 S | 不重复 | 先查 `I-20260924-01-alpaca-options-feasibility` 已有结论；**线索是自报、无熊市年、30% 日被跳过** |
| 6 | **Xitadel 的风险入分**：`P − 0.1×D` 乘夏普质量因子，及"修复缺陷 P&L +63% 而夏普 7.27→3.03"的例子；留出日只公布哈希 | E 评估标准（已有"夏普优先"规则的外部佐证）；留出窗承诺 | XS | 不重复 | 不借其订单簿任务 |
| 7 | **ALTA 的记录结构**：对立评审"先提交再披露"、事件时间与检索时间分离、前向结果归属冻结入场决策、校准只收紧不放松 | E：`llm_contribution_pass` 与新闻/事件特征包；A1 | M | 不重复 | 零结果，仅借结构；不借其执行层 |
| 8 | **oaia 的"对影子抛硬币群评百分位"和签名承诺提交** | A1 前向记录（承诺时间戳）；安慰剂呈现 | S | 部分重复（T-76 #5 哈希链） | 同类，只补"影子群百分位"的呈现 |
| 9 | **AlphaResearchOS 的 9 只行业 ETF 留出基线**与 **quant-autoresearch 的"冻结 vs 事后最优"呈现** | D 线行业 ETF（EOM/季节性）对照；E 汇报格式 | S | 不重复 | 基线是自报且牛市窗口，先复算再用；呈现格式直接可用 |
| 10 | **Eikos/Jev 类型化校准决策接口**作为 LLM→PIT 特征包的形态；Eikos 的 MIT 开源权重 | E 的 LLM 贡献测试；GPU 评估（Modal） | M–L | 不重复 | 厂商自测，先做小规模评估；不是 alpha 来源 |
| 11 | **polyledger**（Polymarket CLOB+链上 OrderFilled→DuckDB）作为预测市场线的数据管线候选 | 预测市场线 | S | 不重复 | 观察，需先看预测市场线是否仍开着 |
| 12 | **claude-trading-skills 的工作流 YAML**（技能、决策门、产物）与 quantskills 的"研究验证"12 项 | E 技能差异比对 | XS | 与 ml4t/skills 一次做 | 只读比对，不安装 |

## 7. 不借清单

| 项目/类别 | 原因 |
|---|---|
| Jev 包装的机器人（jev-trader、beebots、warrenduffer 等） | 全是 dry-run/mock，无结果；jev-trader 星是名人发布日爆星，一次推送后停；Monad/加密/做市，与我们不对口。 |
| Robinhood Chain 代币/股票代币机器人（noraz、ai-robinhood-chain、rh-*、EKO、seat 等） | 链上代币与 memecoin，常带自家代币链接；ai-robinhood-chain 134 星/963 复刻；与 Alpaca 模拟盘无关。 |
| Robinhood Agentic Trading / OpenTrade-Agent | 实盘通道，超出我们的范围（实盘写权限不在范围内）；只借"专用账户、逐代理记账"的思路。 |
| Polymarket 跟单/网球/Telegram 机器人 | 推广型，星≈复刻（polymarket-tennis 274/232）。 |
| A 股桌面应用与 DeepSeek Harness 插件（easy-stock、dsh-trading、deepseek-harness-quant、dsh-quant 等） | 市场与数据源不对口；dsh-trading 为 PolyForm Noncommercial。 |
| 带返佣/自家代币/付费墙的项目（astra-quant-agent、TetreesAgent_EX、LLM-trader-test 类） | 激励的是推广，不是研究；astra 的许可为 AGPL+Commons Clause。 |
| atlas-gic | 自报实盘未核验；LLM 提示词优化的回测暴露在模型训练截止日之前；星数口径不一致；有克隆。 |
| stonkfly、openreality、MysticGSI 等噪音/无关 | 作者自己写"尚未证明盈利"；或根本不是交易项目（搜索误命中）。 |
| EdotEnv（YC S26） | 网站只有使命宣言，没有客户、评分方法、成本或结果（WebFetch）。 |
| aitradingcompetition.com 的收益数字 | 纸上、无成本、牛市窗口、自报；只借"frozen 对照臂"概念，我们已有。 |
| Xitadel 的订单簿任务、Hyperliquid 永续类项目 | 我们的范围是 Alpaca 可交易的美股/ETF/期权/加密现货；永续不在内。 |
| "一句话回测"平台与 vibe 工作台（Vibe-Research 类） | 我们的 StrategySpec 先行 + 预注册更严；与 T-76 同。 |

## 8. 没做完 / 拿不准的地方

- **X 渠道**没有；**Reddit** 三个子版块全部 403；**Hacker News** 只能看标题和分数，没有读评论；WSJ 那篇只见标题（付费墙）。
- **老项目的 8 月以来新增星数没有测到**：stargazers 接口需要认证，而环境里没有 GitHub 令牌。只有 7 个项目有两个时点的速率（夜间区间 10.7 小时，偏低）；OSS Insight 数据被其自身标为 degraded，弃用。新项目的"8 月以来新增"就是当前星数。
- **只读 README/文档，没审源码**：所有"做什么/架构"来自作者的 README 与文档，没有一个项目的代码被我核对；swiftward 的 34 条失败清单只读了开头约十条，Deflow 的 README 只读了检索行，Loopera、dsh-trading、easy-stock 只读 README 开头，十几个项目只读了 GitHub 元数据（表里"读过"列写明）。
- **DXRG 论文的 17 条规则和费用口径**来自 WebFetch 对 arXiv HTML 的转述，没有逐字落盘；落盘的只有摘要接口和 DISCUSSION。**待核对**，先读原文再把规则放进评估标准。
- **Alpaca 黑客松页面**：lablab 页面的详细规则、评委、获奖名单我没有打开原页（WebFetch 对一个错误 slug 返回了 milan-ai-week 那个黑客松，已弃用）；"Miramar Labs +3.7%"来自检索摘要，未核对。
- **TypeSafe Jev** 的发布日期、定价与性能声明来自检索摘要（eesel.ai、dealroom 等），未打开官方页。
- **Robinhood Agentic Trading** 的日期来自 Axios/pulse2 的检索摘要；官方支持文档（WebFetch）没有写发布日期。
- **SPY 0DTE 的数字**是作者自报；我没有重算，也没有核对它所依赖的期权成交数据的来源与覆盖（"no-fallback OPRA replay"一词来自 README，来源未核对）。
- **Alpaca 对期权多腿订单、0DTE 的规则和我们账户的期权级别**没有核对（这属于期权线自己的可行性文档 `I-20260924-01`）。
- **Trendshift** 只有每档前 25 名；"本月没有交易项目上榜"不等于"没有交易项目上过榜"。
- 去重后 1,276 个新仓库的完整列表没有保存进仓库；JSON 里只有表中的 42 项、计数表与来源。

## 9. 来源清单

快照目录：`reports/research/intel/sources/vibe-wave-2026-10-04/`（文件名 `OWNER__REPO.md` 或 `OWNER__REPO__文件.md`；`web__*.md` 为网页）。取数时间在文件头。

| 类别 | 来源 |
|---|---|
| GitHub README（读过） | kyky2347/ALTA（+CHANGELOG、REPRODUCIBILITY）、jarrodwatts/jev-trader、Loopera-ai/loopera、0xethanq/astra-quant-agent、Superior-Trade/trading-terminal、fidetolabs/qanat（+docs/backtest）、TetreesEX/TetreesAgent_EX、zhu1090093659/dsh-trading、mogons/noraz-agent、Sixian-Li/plain-backtest、LuxAlgo/edge-stats、ProjectDXAI/continuous-record-llm-trading-agents（+DISCUSSION）、CamusGIT/EvoQuant、YellowPancake/quant-autoresearch、heranliu/AlphaResearchOS、Simreal-AI/Xitadel-QuantBench、caiovicentino/eikos、nftechie/stonkfly、jundizhou/easy-stock、TraderAlice/OpenAlice、tradermonty/claude-trading-skills、chrisworsey55/atlas-gic、alsk1992/CloddsBot、quantskills/quantskills、MariusOTB/OpenTrade-Agent、swiftward/swiftward-alpaca-options-agents（+failures-this-avoids）、EkoTerminal/eko、henryzhangpku/autonomous-quant-researcher（+spy-odte FINDINGS、qqq HOLDOUT-SPEND）、caiovicentino/eikos-arena、oaia-fun/code、mrnetwork0001/Deflow、rp7o/trade-foundry、chiefsmurph/alpaca-ai-agents-hackathon、ihsieh31/traders、nahrek/polyledger |
| 网页 | aitradingcompetition.com（原始 HTML，`web__aitradingcompetition.md`）；arXiv 2609.05663 摘要接口 |
| 只有检索/WebFetch 转述，未落盘或未打开原页 | Robinhood 支持文档与新闻（Axios、pulse2）、Robinhood Chain 主网（The Block、Arbitrum 论坛）、TypeSafe Jev（eesel.ai、dealroom）、Karpathy autoresearch（Fortune 等）、Alpaca 黑客松（lablab 检索摘要）、EdotEnv、eikos-arena 网页、arXiv 2609.05663 的 17 条规则 |
| API 与计数 | GitHub `/search/repositories`（约 135 次）、`/repos/{r}`（25 次）；HN Algolia；Trendshift（今日/本周/本月） |
