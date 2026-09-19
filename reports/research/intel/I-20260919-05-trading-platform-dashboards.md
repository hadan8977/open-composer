# 情报简报：五个交易平台的 Dashboard/UI 面板扫描（抄什么、不抄什么）

- 范围：owner 点名的五个产品，逐个看它们的 dashboard/UI 实际长什么样、怎么架构。目标不是选技术栈（见 `I-20260919-04`），是回答"面板级别抄什么"。
- 校验标注：**已打开链接**（GitHub API / raw README / WebFetch 打开过原始页面或文档）／**仅搜索摘要**（只有 WebSearch 摘要，未打开原文）／**未核实**。GitHub 的 star/license/最后 push 一律走 `api.github.com`，按任务要求视为已核实。

## 五个产品概况

| 产品 | URL | License | Star / 最后 push | 技术栈 | 自托管 | 校验 |
|---|---|---|---|---|---|---|
| OpenStock | github.com/Open-Dev-Society/OpenStock | AGPL-3.0 | 15,743★ / 2026-09-19 | Next.js 15 + TS + shadcn/ui，MongoDB，TradingView widgets | 是（Docker Compose） | 已打开链接 |
| HashTrade | hashtrade.ai；代码疑似 github.com/mertozbas/hashtrade | Apache-2.0 | 15★ / 2026-09-04 | Python + CCXT，多 LLM provider（Bedrock/Claude/GPT/Ollama） | 是（`pip install hashtrade`），官网另有在线 demo | 已打开链接（官网）+ 仅搜索摘要（仓库与官网是否同一团队未核实，README 404） |
| QuantDinger | github.com/OpenByteInc/QuantDinger | Apache-2.0 | 11,722★ / 2026-09-19 | 后端 Flask+Gunicorn（Python 3.12），PostgreSQL 18，Redis×2，Celery；前端框架未在 README 写明（未核实） | 是（一键安装脚本 + Docker Compose），也有官方 SaaS（ai.quantdinger.com） | 已打开链接 |
| Freqtrade / FreqUI | github.com/freqtrade/freqtrade 、github.com/freqtrade/frequi | GPL-3.0 | Freqtrade 54,523★ / 2026-09-19；FreqUI 1,077★ / 2026-09-17 | 后端 Python bot + REST API；前端 Vue（FreqUI） | 是 | 已打开链接 |
| OpenAlgo | github.com/marketcalls/openalgo | AGPL-3.0 | 2,693★ / 2026-09-18 | 后端 Python Flask，前端 React 19，DuckDB（历史数据） | 是 | 已打开链接 |

## 面板清单：五个产品各自有什么

**1. OpenStock**（已打开链接：README）—— 本质是"自选股 + 行情信息"App，不是交易/策略系统：全局搜索 + Cmd/Ctrl+K 命令面板；Watchlist（每用户去重存储）；个股详情页（TradingView K 线/高级图表、baseline、技术指标、公司概况与财务 widget、可选跨源情绪：Reddit/X/新闻/Polymarket）；大盘总览（热力图、报价、头条新闻，均为 TradingView widgets）；个性化 onboarding（国家/投资目标/风险偏好/行业）；每日 AI 个性化新闻摘要邮件。**没有持仓、没有 PnL、没有策略、没有回测、没有 agent 活动展示。**

**2. HashTrade**（已打开链接：官网首页；仅搜索摘要：GitHub 仓库）—— UI 是"agent 自己渲染"的动态界面，官网原文只说会出现 "cards, tables, charts, alerts"，移动优先 PWA；agent 按 5→25 分钟变周期自主唤醒、读历史决策+行情、用自然语言而非固定命令交互并可直接下单。官网原文明确："The page doesn't specify dedicated screens for positions, P&L, strategies, or backtest results"——**没有任何固定面板名可抄，卖点是"UI 由 LLM 按需生成"这个架构思路，不是具体面板**。

**3. QuantDinger**（已打开链接：README；仅搜索摘要：docs.quantdinger.com 细节）—— 面向"个人/小团队自托管 AI Trading OS"，面板包括：全局行情监控（加密/美股港股/外汇/大宗商品一屏，仅搜索摘要）；Indicator IDE + 回测面板（IndicatorStrategy/ScriptStrategy 两种策略写法，回测面板内可设杠杆）；Quick Trade 面板（含 "AI Decision Filter" 开关）；**JEV 决策网关的"可审计决策时间线"**——下单前把订单、策略上下文、敞口、持仓、预算状态发给决策引擎，UI 展示 provider、检查项、结果（typed Choice + 概率 + 置信度）、延迟、原因（README 原文已打开链接核实）；System Settings → AI/LLM 配置页；可选 Observability overlay（Grafana + Prometheus + Alertmanager，运维级，非策略级监控）；Web 桌面端 + Mobile H5 + Agent Gateway（58 个租户级工具，含异步回测、运行时可见性）+ MCP server。

**4. Freqtrade / FreqUI**（已打开链接：freqtrade.io 官方文档多页）——
- Login screen → **Trade view**（可视化交易，可强制开平仓，需配置启用）；
- **Dashboard**：多 bot 汇总总览，"an overview of all connected bots"，可切换单个 bot 或看子集——这就是"多 bot 一个 UI"的具体实现，机制是 FreqUI 里逐个添加多个 bot 的 API URL；
- **Wallet Balance**（2026.4 新增）：历史余额曲线，含未实现盈亏、出入金；
- **Plot Configurator**：齿轮图标进入，配置图表叠加指标（策略配置或手动 UI 设置二选一）；
- **Settings**：时区、favicon 交易可视化、K 线配色、通知偏好；
- **Backtesting 面板**（webserver 模式下）：加载并可视化历史回测结果，且"compare the results with each other"——多次回测结果并排对比；
- REST API 端点覆盖：`/trades`、`/performance`（按 pair 分组）、`/daily` `/weekly` `/monthly`、`/stats`（盈亏原因和持有时长分布）、`/entries` `/exits` `/mix_tags`、`/logs`、`/balance`、`/pair_candles` `/pair_history`、`/start` `/stop` `/pause` `/stopbuy` `/reload_config`；
- Telegram：只读监控指令（`/status` `/profit` `/performance` `/balance` `/daily` `/weekly` `/monthly` `/logs`）与主动控制指令（`/forcelong` `/forceexit` `/start` `/stop` `/stopentry` `/reload_config`）并存，**不是纯只读**；
- 24/7：dry-run 模式下不下真实单、只读交易所行情（仅搜索摘要）；生产建议换独立 DB 避免 dry-run 数据污染实盘统计；Docker `restart: always` 或 systemd 看门狗自动重启（sd_notify 在容器里不可用）；交易状态落 SQLite/PostgreSQL，跨重启恢复（仅搜索摘要）。

**5. OpenAlgo**（已打开链接：README + docs.openalgo.in 多页）——
- **Dashboard**：PnL 快照、策略级 MTM、可选一键全平仓 "panic button"；
- **Orderbook / Tradebook / Positionbook / Holdings**，均支持一键下载；
- **策略管理**：GUI 增删改策略、GUI 止损/移动止损/目标位设置、策略级 orderbook/tradebook/positionbook 视图；
- Chart Trading Terminal `/trading`（7 种持久化布局，单图到 4×2 八图网格）、Scalping Terminal `/scalping`（键盘驱动下单）；
- `/tools` 页：12 个期权分析面板（Strategy Builder+payoff+实时 Greeks、Option Chain、IV Smile、Max Pain、Vol Surface、GEX Dashboard、OI Tracker、OI Profile、Straddle Chart、Straddle PnL、Option Greeks History）；
- **API Analyzer**：独立 `sandbox.db`，模拟订单/持仓/资金/配置，与实盘数据完全隔离的沙箱回放环境；
- **Traffic/Latency Monitor**：总请求数、错误数、平均耗时、按 endpoint 统计，可按 `/api/v1` 或全部流量、按成功/失败过滤；
- **Action Center**：订单审批工作流，Auto Mode（个人交易即时执行）vs Approval Mode（人工确认）；
- `/agent`：聊天式 AI Agent 面板，读市场数据、画图/算指标、在 `/trading` 图表右侧标注，下单需逐笔人工批准；
- Telegram：完整 namespace（配置/生命周期/用户/通知/统计/偏好），`/api/v1/telegram/notify` 异步推送；Webhook 接收 TradingView/Amibroker 等外部信号。

## 值得抄进 cockpit 的

1. **FreqUI 的"多 bot 汇总 + 切换"Dashboard**——直接对应我们"一个 Alpaca paper 账户跑 4 个策略"的展示需求：一个总览页汇总全部策略，点进去看单个策略明细，不需要每个策略单开一个页面。
2. **QuantDinger 的"可审计决策时间线"部件**（provider / 检查项 / 结果 / 置信度 / 延迟 / 原因）——虽然它是下单前 AI gate 的记录，但这个"时间线卡片"UI 部件正好是我们缺的"agent 在做什么"的可视化语言，可以直接套用到研究迭代的每一步（搜索→候选→验证→晋级/拒绝）。
3. **Freqtrade Wallet Balance 曲线**（历史权益 + 未实现盈亏 + 出入金标注）——比单纯的当前 PnL 数字更贴近"这周表现如何"的问题，四个策略每个一条曲线即可。
4. **FreqUI Backtesting 面板的"多次结果并排对比"**——我们的研究循环本来就要反复出回测报告，抄它"选多个历史回测结果 → 并排对比"这个交互，而不是自己发明。
5. **OpenAlgo 的"按策略分组"组织原则**（策略级 MTM、策略级 orderbook/tradebook/positionbook）——把"策略"当成一等公民组织维度贯穿整个 cockpit，而不是按 symbol 或按订单堆数据。
6. **OpenAlgo Traffic/Latency Monitor 的 UI 模式**（总量 + 错误数 + 平均耗时 + 按维度过滤的极简面板）——这套通用"健康面板"布局可以照抄用来监控我们自己 agent 调用/研究任务的耗时与失败率，不必抄它监控 broker API 延迟这件事本身。
7. **Freqtrade `/performance`、`/stats`（盈亏归因+持仓时长分布）**——作为"每策略表现明细表"的字段清单参考，比自造指标列省事。

## 不适配的

- **交易所/券商绑定的下单集成**：HashTrade（CCXT 100+ 交易所）、QuantDinger（多交易所+传统券商实盘下单）、Freqtrade（纯加密，不支持股票/Alpaca）——都要整体剥离，我们唯一的执行面是 Alpaca Paper。
- **任何写路径/下单 UI**：FreqUI Trade view 的强制开平仓按钮、Telegram 的 `/forcelong` `/forceexit`、OpenAlgo 的 Scalping Terminal 和一键全平仓 panic button、Action Center 的 Auto Mode 即时下单——cockpit 明确只读，这些按钮语义一律不抄，哪怕换皮成"只读展示"也不必要。
- **在 UI 里管理 broker 凭证**：QuantDinger System Settings 直接配置/加密存储 broker API key（`CREDENTIAL_ENCRYPTION_KEY`）、OpenAlgo 36 个 broker 插件的凭证录入界面——CLAUDE.md 明确不得在制品中暴露 `.env`/私钥/broker 密钥，这类"设置页管密钥"的模式本身就不该出现在 cockpit 里。
- **多用户/多租户/计费**：QuantDinger 官方定位是"commercial-ready multi-tenant SaaS"，含用户管理、账单、支付、结算（billing/payments/settlement）和多租户 Agent Gateway token 体系——我们是单用户系统，这套整体不需要。
- **期权分析套件**：OpenAlgo 的 12 个期权面板（Option Chain、Greeks、Vol Surface、GEX 等）——现在四个策略是美股动量/ETF 轮动，不涉及期权，现在抄这套是过度建设。
- **OpenStock 的获客型功能**：跨源社交情绪聚合、每日 AI 个性化营销邮件、onboarding 问卷——这是面向"选股新手消费者"的获客机制，不是"运行中系统状态 cockpit"该有的东西。
- **"AI 故障默认放行"的执行语义**：QuantDinger JEV 网关在 AI provider 不可用时 fail-open 直接放行订单——这是执行策略选择，不是 UI 抄法问题；就算我们要类似的 gate，也要单独走 `paper-auto-safety-reviewer` 评审，不能当成"抄面板"顺带引入。

## 一个判断

五个产品**全部以执行/监控为中心构建，没有一个把"研究迭代进度、假设卡片、多候选比较"当作一等公民 UI 对象**。

- OpenStock、HashTrade：纯行情/自选股/自主下单，完全没有"研究"这层概念，agent（HashTrade）只做决策执行，不留研究轨迹。
- Freqtrade 的 Backtesting 面板是五者里最接近"研究结果"的东西，但它只是加载/对比历史回测 JSON 结果的静态视图，不追踪"假设→验证→晋级"这条状态机，也不区分样本内/样本外/walk-forward。
- OpenAlgo 的 API Analyzer 是"下单前用沙箱跑一遍"，属于执行前测试（更接近我们的 paper_ready 概念），同样不是假设管理。
- QuantDinger 最接近"agent 活动可视化"，因为它有 JEV 决策时间线和 Agent Gateway 的"运行时可见性"，但那展示的是**单笔下单前 AI 否决/放行的决策记录**，不是"这一轮研究做了什么、下一步候选有哪些、为什么被拒"这种研究迭代仪表盘。

结论：研究迭代/假设卡片/agent 活动这块 cockpit 需要我们自己设计信息架构，只能从这五个产品里借"时间线组件""并排对比列表""按策略分组"这类通用 UI 部件，不能照搬任何一个的整体信息架构。
