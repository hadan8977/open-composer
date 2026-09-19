# 情报简报：多 agent / 7x24 场景下的其余量化工作台界面扫描

- 范围：owner 已看过 Freqtrade / OpenAlgo / QuantDinger / OpenStock / hashtrade.ai（另一份简报 `I-20260919-05` 覆盖，此处不重复）。本简报找"适合多 agent 或 7x24 运行"的**其余**候选，分执行侧（自托管 7x24 交易系统的监控界面）和研究侧（LLM 多 agent 量化研究循环自带的界面）两块。
- 约束背景（沿用 `I-20260919-04` 实测）：单机 3.9GB 内存，agent 24/7 跑研究循环+纸上账户；驾驶舱只读、数据是仓库里的文件（`reports/**`、`strategy_specs/**`、YAML/Markdown/JSONL），不是数据库。
- 校验标注：**已打开链接**（GitHub API `api.github.com` 结构化字段，或 WebFetch 打开过原始页面/文档——按任务要求两者都视为已核实）／**仅搜索摘要**（只看到 WebSearch 摘要，未打开原文）／**未核实**（无法确认，按不成立处理）。Star/License/最后 push 一律 `api.github.com`，采样时间 2026-09-19。

## A 执行侧：界面里有什么

| 项目 | URL | License | Star / 最后 push | UI 实际显示什么 | 技术栈 | 自托管内存代价 | 校验 |
|---|---|---|---|---|---|---|---|
| Hummingbot（核心） | github.com/hummingbot/hummingbot | Apache-2.0 | 20,057★ / 2026-09-18 | 核心是 CLI，无内建图形面板 | Python，每实例约 200MB RAM（官方博客口径） | 单实例约 200MB，多实例线性叠加 | 已打开链接（repo）+ 仅搜索摘要（RAM 数字） |
| Hummingbot Dashboard | github.com/hummingbot/dashboard | Apache-2.0 | 367★ / **2025-10-27**（近一年未更新，红旗） | Streamlit 页面：策略配置、回测结果、机器人实例管理、组合总览 | Streamlit UI + 独立 backend-api（FastAPI）+ broker(MQTT) 容器，docker-compose 多容器 | 三容器起步，Streamlit 本身有"会话关闭内存不释放"的已知问题（`I-20260919-04` 已核实同类问题）；叠加多实例后在 3.9GB 机器上偏紧 | 已打开链接（repo 状态）+ 仅搜索摘要（内部机制） |
| Jesse（jesse.trade） | github.com/jesse-ai/jesse | MIT | 8,529★ / 2026-09-17 | 内建 Web Dashboard（localhost:9000）：K线+指标+订单+成交同步图表，回测与实盘/纸上共用同一套图表组件，WebSocket 实时推流，移动端做过优化 | FastAPI 后端 + Nuxt.js 前端；官方部署需 Postgres + Redis + 主容器 | 未见官方最低 RAM 数字；同类 Postgres+Redis+应用 compose 栈通用经验值 4GB 起步较稳（未核实，非 Jesse 官方数据，仅作参考） | 仅搜索摘要 |
| NautilusTrader | github.com/nautechsystems/nautilus_trader | LGPL-3.0 | 29,126★ / 2026-09-19 | **没有常驻 GUI/仪表盘**。回测后生成自包含交互式 HTML tearsheet（Plotly）：权益曲线、回撤、月/年收益、分布、滚动 Sharpe、成交明细图 | Rust 核心引擎，报表层 Python+Plotly，产物是静态 HTML，无需服务器 | 引擎本身是无头、为性能设计，报表是一次性静态文件，无常驻内存代价 | 已打开链接（官方文档 Visualization/Reports 页摘要，经搜索确认无独立 GUI 产品） |
| QuantConnect LEAN（本地 CLI） | github.com/QuantConnect/Lean | Apache-2.0 | 21,676★ / 2026-09-18 | `lean report` 生成单次回测的静态 `report.html`（权益曲线、回撤、月度收益、订单、统计表）；本地"研究环境"是 Jupyter notebook，不是常驻面板；官方原话：更丰富的多图表/日志页面**只在云端 Web UI，本地版没有** | CLI + 模板 HTML/CSS | 静态文件生成，无常驻服务 | 已打开链接（`lean-cli` issue + docs 摘要） |
| StockSharp | github.com/StockSharp/StockSharp | NOASSERTION（核心 LGPL + 部分商业组件） | 10,776★ / 2026-09-15 | Designer（可视化策略设计器+C#调试器）、Terminal（图表交易终端）等**桌面 WPF 应用**，功能很全但是 Windows/.NET 桌面软件 | .NET/WPF | 桌面应用，非本机 Linux 无头场景可直接复用，且非手机友好 | 仅搜索摘要 |
| Lumibot | github.com/Lumiwealth/lumibot | GPL-3.0 | 2,074★ / 2026-09-19 | 开源仓库**本身不带官方 Web 面板**；官方配套是付费托管服务 BotSpot（数据/回测/监控/一键停止打包），可通过网页/手机/Telegram/Discord/Claude/ChatGPT(MCP) 访问；社区第三方 Vue+Flask 面板（如 `Kingsxai/lumibot-web-interface`）star 数很低、非官方 | BotSpot 为云托管；第三方面板栈不一 | 若走 BotSpot 是别人机器，不占本机内存；社区面板未核实内存 | 仅搜索摘要 |
| Backtesting.py | github.com/kernc/backtesting.py | AGPL-3.0 | 8,974★ / 2026-08-05 | `Backtest.plot()` 生成单次运行的 Bokeh 交互 HTML（K线+指标+成交+权益+回撤），**没有多次运行/组合级别的仪表盘**，无研究循环概念 | Python + Bokeh，产物静态 HTML | 静态文件，无常驻服务 | 仅搜索摘要 |
| vectorbt | github.com/polakowo/vectorbt | NOASSERTION（免费版功能受限，商业版另收费） | 9,124★ / 2026-09-17 | Jupyter 内嵌 Plotly/ipywidgets 图表，擅长参数曲面/热力图等批量回测可视化，**本质是 notebook 组件库，不是常驻服务器面板** | Python + Plotly + ipywidgets，跑在 Jupyter 里 | 无常驻服务，跟随 Jupyter kernel | 仅搜索摘要 |
| OctoBot | github.com/Drakkar-Software/OctoBot | GPL-3.0 | 6,588★ / 2026-09-19 | 内建 Web UI：多交易所组合总览、"tentacles"（策略插件）管理、Grid/DCA 自动化状态、内建回测入口，面向消费者、偏简单 | Python 后端 + JS 前端，自带 Web 服务器 | 未见官方数字，未核实 | 仅搜索摘要 |
| Gekko（时代幸存者，**未幸存**） | github.com/askmike/gekko | MIT | 10,180★ / **已归档 2020-02-16** | 停止维护 6 年+，仅作历史参照 | Node.js | 不适用 | 已打开链接 |
| Kelp（时代幸存者，**未幸存**） | github.com/stellar-deprecated/kelp | — | 1,123★ / **已归档 2023-11-03**（Stellar 基金会自己弃用） | 停止维护，仅作历史参照 | Go | 不适用 | 已打开链接 |
| OpenBB Workspace / Terminal Pro | github.com/OpenBB-finance/OpenBB；workspace.openbb.co | NOASSERTION（部分组件已转为 OpenBB 自有非 OSI 许可） | 核心仓库 73,234★ / 2026-09-19 | **Workspace 本体是云托管 SaaS**（不是自托管软件），个人 Community 版免费：无限自定义 widget/dashboard、自带 API key、20 次/天 Copilot；表格/图表/KPI 卡片式 BI 界面，**不是 agent 活动/研究循环视图** | 你自己写一个极简 FastAPI+Uvicorn"custom backend"（官方模板 `OpenBB-finance/backends-for-openbb`），暴露 `widgets.json`/`apps.json` + REST 端点返回 JSON，OpenBB 云端 UI 来读 | 你这边只需跑一个轻量 FastAPI 进程（几十 MB 级，未核实具体数字）；**关键限制**：云端 Workspace 要访问它，官方文档给的方案是用 ngrok 把本机端口开放到公网（穿透 NAT/防火墙），即必须让读文件的后端可被公网访问——与本项目"远程面板须走密码会话/HMAC/Vercel BFF"的既定安全要求存在张力 | 已打开链接（openbb.co/pricing 官方页、docs.openbb.co/workspace/developers/data-integration 官方页）+ 仅搜索摘要（ngrok 穿透细节） |

## B 研究侧：谁真的把研究循环画出来了

| 项目 | URL | License | Star / 最后 push | UI 显示什么 | 是否画出研究循环本身（假设→试验→结果→下一假设，含被证伪的） | 校验 |
|---|---|---|---|---|---|---|
| Microsoft RD-Agent | github.com/microsoft/RD-Agent | MIT | 14,679★ / 2026-09-15 | 两套独立界面：①`rdagent ui --data-science`（Streamlit）看运行日志/trace，是目前唯一确认支持量化(data_science)场景的界面；②更新的 `server_ui`（Flask 后端+React 前端）做实时交互和 trace 查看，但官方明确**还不支持 data_science/量化场景** | 论文层面 RD-Agent(Q) 的 5 阶段循环（Specification→Synthesis→Implementation→Validation→Analysis）有明确定义，但**未找到证据证明现有 Web UI 把这个循环端到端画出来**——已验证的界面停留在"看 trace/日志"层级，不是"假设卡片→试验→证伪"的可视化 | 已打开链接（GitHub README/repo 结构）+ 仅搜索摘要（UI 面板细节，未能确认量化场景的具体面板名） |
| TradingAgents（TauricResearch） | github.com/TauricResearch/TradingAgents | Apache-2.0 | 107,556★ / 2026-09-18 | 官方 CLI 实时进度条；可自托管一个 FastAPI+Web UI+REST API，把 4 类分析师→多空研究员辩论→交易员综合→风控 的单次 (ticker, date) 分析流程可视化出来 | 画的是"单次调用内部的多 agent 流水线"，**不是跨天持久化的假设积压/证伪账本**——每次调用独立，不构成长期研究循环视图 | 仅搜索摘要 |
| TradingAgents-CN | github.com/hsliuping/TradingAgents-CN | NOASSERTION | 31,880★ / 2026-07-24（约2个月未更新） | Streamlit 应用（localhost:8501）：12 阶段实时进度条（7 分析师→质检→辩论→风控→决策），每阶段报告可展开查看，一键导出 PDF/Markdown，中文原生 | 与上游同样的限制：可视化的是单次分析的流水线阶段，不是"昨天试了什么、被拒了什么、今天试什么"的持久循环 | 仅搜索摘要 |
| AI Hedge Fund（virattt） | github.com/virattt/ai-hedge-fund | MIT | 63,528★ / 2026-09-18 | React+Vite 单页应用，React Flow 可视化节点编辑器（拖拽连接分析师 agent）+ SSE 实时进度；官方定位是"持续运行、保留完整操作账本"而非一次性脚本 | 有"持续运行+账本"的产品意图，UI 侧重流程编排和单次运行监控，**未见证据显示它把假设/试验/证伪结构化展示成一个可回溯的研究看板** | 仅搜索摘要 |
| FinRobot | github.com/AI4Finance-Foundation/FinRobot | Apache-2.0 | 8,031★ / 2026-09-11 | 主体是 AutoGen 驱动的 notebook/agent 库；据称"FinRobot Pro"子系统有 FastAPI 股票研究 Web 界面，另有独立"FinRobot Desktop"估值报告桌面应用 | 未找到证据支持研究循环可视化 | 仅搜索摘要，未能核实截图/面板名 |
| AlphaAgent | github.com/RndmVariableQ/AlphaAgent | 未声明 license | 414★ / 2026-07-03 | 论文配套的"自主因子挖掘框架"代码发布，**未发现任何 Web UI** | 无 UI，不适用 | 仅搜索摘要 |
| FinGPT | github.com/AI4Finance-Foundation/FinGPT | MIT | 21,264★ / 2026-09-14 | 有为"FinGPT 搜索 agent"做的聊天式 GUI（主窗口+来源按钮+清除按钮），是问答界面，不是量化研究循环面板 | 不适用，方向不对口 | 仅搜索摘要 |
| Qlib 自带 Recorder/UI | github.com/microsoft/qlib | MIT | 48,668★ / 2026-09-17 | 内建 `QlibRecorder`/`qrun` 实验管理，后端是 `MLflowExpManager`，官方查看方式就是跑 `mlflow ui`——通用 ML 实验追踪器（run/metric/param/artifact），本身不懂"金融策略"或"研究循环"语义 | 只有"实验列表+指标对比"，没有假设/证伪的领域语义 | 已打开链接（Qlib Recorder 官方文档摘要） |
| 第三方 Qlib Studio（非官方） | github.com/ximilu0114-droid/qlib-studio | 未声明 | 18★ / 2026-08-24 | 据称把 Qlib 工作流封装成一个浏览器应用：环境检查、YAML 编辑、异步 `qrun`+实时日志、MLflow 浏览、回测收益/回撤图、风险表，**还带一个 RD-Agent 的"看门"启动器和健康面板** | 意图上最接近"把 RD-Agent 的循环塞进一个正经前端"，但项目极小众（18★）、未核实代码质量，只能当设计参考，不能当依赖 | 已打开链接（repo 存在性/star）+ 仅搜索摘要（功能描述） |
| `henryzhangpku/autonomous-quant-researcher` | github.com/henryzhangpku/autonomous-quant-researcher | 未声明 | **1★** / 2026-09-17（几天前） | 一个"research board"网页 demo：真实研究引擎跑在浏览器里（Pyodide/WASM），对合成行情数据驱动一个脚本化的假设提议器，界面展示①假设提议（JSON 卡片）②试验阶段推进（discovery→validation→holdout）③门槛通过/未通过④**显式演示一个被埋的假异常——discovery 阶段发现了它，validation 阶段把它证伪**，说明是怎么防过拟合的 | **是本次调研里唯一一个把"假设→试验→门槛→证伪"字面意义上画出来的项目**——但这是一个刚发布几天、1 星的个人业余项目，不代表任何生产成熟度，只能当 UI 设计范式抄 | 已打开链接（WebFetch 打开 repo README） |

**这一块最好的例子是哪个，看你要什么**：如果要"今天就能指给别人看、Streamlit 已经跑起来、中文原生"的**产品**，`TradingAgents-CN`（31,880★）最成熟——12 阶段实时展开面板、一键导出，观感专业；但它和上游 TradingAgents 一样，本质是"点一个股票、看一次多 agent 辩论流水线跑完"，跑完即止，**不持久化多天的研究积压/证伪历史**，不是 owner 要的"7x24 研究进展总览"。如果要"UI 概念上完全对题"的**范式**，1 星的 `henryzhangpku/autonomous-quant-researcher` 反而是唯一命中靶心的——它的"research board"直接把假设卡片、discovery/validation/holdout 三段式试验状态、门槛通过/拒绝、以及一次证伪演示画在一个页面里，这正是 owner 描述的"研究进展+被证伪了什么"。两者的落差本身就是一个信号：**"把研究循环本身画出来"这件事，在成熟、多星的开源项目里几乎不存在**——大家都在做"运行一次、看一次结果"的界面，没人把跨天的假设账本当作 UI 的一等公民。

## 最值得抄的五个具体设计

1. **NautilusTrader：自包含静态 Plotly HTML tearsheet**——一次回测/研究运行结束直接产出一个可以脱离服务器打开的 `.html`（权益、回撤、滚动 Sharpe 等标准面板都在一个文件里）。这和"数据是仓库文件、不是数据库"的前提完全匹配：每次研究/回测跑完在 `reports/**` 下多一个静态文件，手机 cockpit 只需要一个能浏览这些静态文件的入口页，不需要为这部分单独起常驻服务。
2. **Jesse：回测回放和实盘/纸上监控共用同一套图表组件**（K线+指标+订单+成交同步叠加），而不是"回测一个视图、实盘另一个视图"两套代码。抄这个设计，避免 cockpit 里回测报告和纸上账户状态变成两套互不复用的渲染逻辑。
3. **TradingAgents-CN：可展开的多阶段实时进度条**（12 个阶段，每阶段报告可点开看详情）。抄这个做"agent 现在在干什么"面板：把 open-composer 自己的流程（策略校验→能力评估→源研究→搜索空间→试验→基准家族→回测取证→执行现实性→晋升报告→纸上就绪）列成一排阶段徽标，点开某一阶段直接展示对应的 markdown 产物，不用另外维护一套"进度状态"数据结构。
4. **`henryzhangpku/autonomous-quant-researcher` 的 research board 卡片布局**——假设卡片 → discovery/validation/holdout 三段式试验状态芯片 → 门槛通过/拒绝徽标 → 证伪说明，按时间线排列。这是唯一直接对题"研究循环可视化"的范式，抄它的卡片/泳道结构去读我们自己 `reports/research/**` 里已有的假设、试验清单和 forensics 结论，不需要引入它的代码本身。
5. **OpenBB Workspace 的"自定义后端"分层模式**——只写一个极简、只读、返回 JSON 的小 API（FastAPI/Uvicorn），把"渲染"完全交给前端/客户端；这与本项目已经定下的 Vercel BFF 架构是同一思路（薄只读 API + 前端渲染），可以直接抄这个分层，但**不要抄它"经公网隧道把后端暴露给云端 UI"的连接方式**——那和本项目"远程面板必须走密码会话/HMAC/双重确认"的既有安全要求冲突，我们应该让前端直接在自己的 Vercel BFF 后面，而不是再套一层需要公网可达的第三方 SaaS。

## 结论：有没有一个可以直接用

没有一个能整体拿来用，原因分两层：

- **执行侧**（Hummingbot Dashboard、Jesse、OctoBot 等）都是为"这个引擎自己去下单"设计的完整多容器栈（自己的 broker/exchange 连接器 + Postgres/Redis + API + UI），要用它们的界面就意味着把它们的下单/broker 模型也一起接进来，这和本项目"Alpaca Paper 是唯一自动化纸上写路径"的既定架构冲突；而且 Hummingbot Dashboard 已经近一年没更新、是 Streamlit（已知的"会话内存不释放"问题在 `I-20260919-04` 里核实过），叠加到 3.9GB 机器上和 24/7 跑的 agent 抢内存不划算。NautilusTrader/Backtesting.py/vectorbt 这类"只产出静态报告或 notebook 组件"的反而更安全，但它们本来就不是仪表盘产品，只是报表片段。
- **研究侧**（RD-Agent、TradingAgents(-CN)、AI Hedge Fund）全部是"点一次、看一次、跑完就完"的单次任务型 UI，没有一个把"过去几天试了哪些假设、哪些被拒了、接下来要试什么"当作持久化的一等数据结构去展示——这恰恰是 owner 要的核心，而这个仓库自己的 `reports/research/**` + StrategySpec 已经是这个账本的事实来源。采用它们中的任何一个，等于放弃已经在跑的文件化研究轨迹，换一套假设它们自己内部状态模型的 UI，得不偿失。
- **OpenBB Workspace 自定义后端**是这次调研里"模式"最值得学但"产品"最不该直接接入的一个：免费、个人可用、天然只读友好、就是"服务自己的 widget/数据"，但它的云端 UI 要求本机后端公网可达（ngrok 隧道），和本项目远程面板必须走密码会话/HMAC/Vercel BFF 的规则正面冲突，而且它是通用 BI 网格（表格/图表/KPI 卡片），画不出"agent 正在做什么"这种叙事型面板。
- 唯一在 UI 语义上真正对题的（假设→试验→门槛→证伪的研究看板）是 `henryzhangpku/autonomous-quant-researcher`——但它是一个 1 星、发布几天的个人 demo，本身就说明"读文件、专给单用户、把研究循环本身可视化"这个细分需求目前市面上基本是空的，没有现成产品可以替代自建。

**结论**：不建议引入以上任何一个作为依赖；建议直接在既有 `reports/dashboard/`（`I-20260919-04` 已确认存在的静态 HTML 生成器）基础上，按上面五条设计抄过来自建只读页面——数据继续读 `reports/**`、`strategy_specs/**`、签名日志等仓库文件，服务端保持薄只读 API + Vercel BFF，不接入任何一个外部平台的运行时。
