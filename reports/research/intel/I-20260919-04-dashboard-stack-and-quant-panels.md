# 情报简报：只读研究驾驶舱技术栈选型 + 量化研究面板标准清单

- 范围：单台 VPS（`free -h` 实测 3.8Gi 总内存、启动时已用 1.9Gi、~1.9Gi 可回收 buff/cache，`df -h` 实测 `/` 分区 35G 可用），同时跑 pandas 回测；驾驶舱只读、数据来自本仓库 `reports/**`、`strategy_specs/**`、`signal_logs/**`、Markdown/JSON/JSONL，以及本地 agent 会话 JSONL；经既有 Cloudflare Tunnel 暴露给手机浏览器；需要低开销的实时推送（agent 当前动作）。
- 方法：WebSearch 定位候选与数据点，对 5 个关键论据用 WebFetch 打开原文核实（Grafana 官方安装文档、QuantStats/pyfolio 源码、Datasette 插件市场、htmx SSE 扩展文档）。
- 校验标注：**已打开链接**（WebFetch 打开过原文）／**仅搜索摘要**（只有 WebSearch 返回的摘要，未打开原文，可能有模型总结误差）／**未核实**。
- 本仓库现状（已用 `du -sh` / `find` 核实，仅搜索摘要不适用——这是本地实测）：`reports/` 已 1.8G（`reports/research` 占 1.4G），`signal_logs/` 24M，`strategy_specs/` 4.3M；**`reports/dashboard/` 下已经有一套手写的静态每策略 HTML 报告生成器**（`catalog.json` + 每策略一个 `.html`），新驾驶舱应视其为既有数据源之一，不要重造。

## A 栈选型

| 栈 | 空闲内存占用 | 实时推送 | 无DB直接渲染MD/表/图 | 手机布局 | 隧道后鉴权 | 构建成本 | 校验 |
|---|---|---|---|---|---|---|---|
| **FastAPI + Jinja2 + HTMX/Alpine（服务端渲染）** | 单 uvicorn worker 空闲约 50–80MB RSS（仅搜索摘要） | 原生支持 SSE（`StreamingResponse`/`sse-starlette`），htmx SSE 扩展本身仅 2–3KB、零依赖、对后端框架无要求（已打开链接：`htmx.org/extensions/sse`） | 是，Jinja2 直接读文件渲染，图表用 CDN 引入的 Plotly/ECharts JS | 需自己写响应式 CSS，工作量在自己手上，上限高 | 应用层可不写登录页，交给 Cloudflare Access 边缘鉴权（见下） | 中：模板+少量 JS 手写 | 仅搜索摘要+已打开链接 |
| Vite/React SPA + FastAPI 只读 JSON API | React 静态构建产物运行期内存≈0，API 进程同上 50–80MB | 需自己接 SSE/WebSocket，无内建约定 | 是，前端 fetch JSON 自己画图 | 最优，完全自定义响应式组件 | 同上，交给边缘或简单 Bearer | 高：需维护 React 构建链、状态管理、图表库 | 仅搜索摘要 |
| SvelteKit（`adapter-static`） | 构建后无 Node 运行时，纯静态文件，运行期内存≈0（已打开链接材料佐证：adapter-static 编译为纯 HTML/CSS/JS，请求时无需 Node） | **无原生实时**，是纯构建期产物，需另起小型 API/SSE 端点外挂 | 是，构建期读文件生成 | 好，Svelte 编译产物小 | 需外挂鉴权，无内建会话 | 中高：需学 Svelte 组件模型 | 仅搜索摘要 |
| Observable Framework | Node 构建工具，产物是静态站点，运行期内存≈0；仅需要 Node 18+ 做 `build`（已打开链接材料：数据 loader 在构建时预计算快照） | **无原生实时**，范式是"构建期快照"，实时要么加轮询式重新构建，要么外挂 API | 是，Markdown+任意语言数据 loader（含 Python）直接产出静态站 | 好，Observable Plot 图表响应式 | 需外挂鉴权 | 中：需学它的 loader 约定 | 仅搜索摘要 |
| Evidence.dev | Node 构建工具，同样产出静态站；交互筛选用浏览器内 DuckDB-WASM，不回源服务器 | 无原生实时，同上构建期范式 | 是，SQL+Markdown，但更贴近"数据仓库查询"心智，本项目数据是文件不是仓库，需先落 DuckDB/CSV 视图 | 好 | 需外挂鉴权 | 中：比 Observable 更偏 BI，字段建模成本略高 | 仅搜索摘要 |
| Datasette (+插件) | ASGI 服务，量级与 FastAPI 接近（未见官方数字，按同类 Python ASGI 应用估计，未核实具体 MB） | **无实时推送插件**：翻遍插件市场，`datasette-dashboards`/`datasette-plot`/`datasette-vega`/`datasette-graphql` 都是请求-响应式，没有 WebSocket/SSE 插件（已打开链接：`datasette.io/plugins`） | 否——核心假设数据在 SQLite 表里，本项目数据是 JSONL/Markdown/YAML，要先做 ETL 灌库，增加构建成本 | 一般，表格类 UI 非移动优先 | 有 `datasette-auth` 类插件，但仍需自己接 | 中高（多出 ETL） | 已打开链接（插件清单）+ 仅搜索摘要（内存） |
| Marimo | Python 反应式 notebook，按 cell 依赖图只重跑受影响 cell，理论上比 Streamlit 全脚本重跑更省内存（仅搜索摘要，无官方 MB 数字） | 内建 WebSocket 反应式推送 | 是，Python 原生读文件+markdown+dataframe+Plotly/Altair | 一般，notebook/app 视图非移动优先设计 | 需外挂鉴权 | 低：纯 Python，零前端代码 | 仅搜索摘要 |
| Streamlit | 官方无固定数字；已知问题：session 关闭后内存不释放，多会话下会持续增长直至 OOM（GitHub issue 佐证，仅搜索摘要） | 无原生 SSE/WS，靠 rerun 轮询式交互 | 是，`st.*` 组件直接读文件画图表 | 一般，官方组件响应式有限 | 需外挂鉴权 | 低：最快出原型 | 仅搜索摘要 |
| Panel/HoloViz（Bokeh server） | Bokeh server 常驻进程，同样有"session 关闭后内存未释放"的已知 issue（GitHub 佐证，仅搜索摘要）；默认 WebSocket 单包上限约 10MB | 内建 WebSocket | 是 | 一般 | 需外挂 | 中：比 Streamlit 灵活但概念更多 | 仅搜索摘要 |
| Reflex | 编译为 React 前端 + FastAPI 后端，**每个会话在服务端持有 state**，worker 默认 100 连接后重启以防内存泄漏（仅搜索摘要） | 内建 WebSocket 状态同步 | 是，Python 定义 state 读文件 | 好（React 渲染） | 需外挂 | 高：需装 Node 工具链编译前端，对单用户是不必要的复杂度 | 仅搜索摘要 |
| Plotly Dash | Flask 常驻进程，量级与 Flask 应用相当（未核实具体 MB） | 默认 `dcc.Interval` 轮询；4.2 版起有原生 WebSocket callback，但需要 FastAPI/Quart 后端（已打开链接材料佐证的搜索摘要） | 是 | 一般 | 需外挂 | 中 | 仅搜索摘要 |
| **Grafana（+Prometheus/Loki/Alloy）** | Grafana 核心官方文档写"最低 512MB 内存、1 核"，小型生产部署建议 2–4GB（已打开链接：`grafana.com/docs/grafana/latest/setup-grafana/installation/`）；**这只是 Grafana 单体**，加上 Prometheus+Loki+Alloy 三个常驻进程，合计轻松超过 1.5–2GB | 原生（Loki 可 tail、Grafana 面板自动刷新，非严格推送但够用） | 否，全部要先过 Prometheus/Loki 的数据模型，文件类数据要写 exporter | 好，官方响应式面板 | 成熟（内建组织/角色，或套 Cloudflare Access） | 高：4 个组件的运维面 | 已打开链接（核心内存）+仅搜索摘要（组合总量） |
| **Metabase** | JVM 应用，社区建议 4GB 机器配 2.8GB heap 才"舒适"，2GB 是"绝对最低且容易在密集查询时崩溃"（仅搜索摘要，源自 Metabase 官方论坛/文档） | 无原生推送，轮询刷新 | 否，需接 JDBC 数据源，文件要先建库 | 好 | 需外挂 | 中，但前提是先有数据库 | 仅搜索摘要 |
| **Superset** | Flask+Celery+Redis+（通常）Postgres 多进程架构，官方口径最低 2048MB，社区实测 Docker 默认 2GB 会启动失败、建议 6GB，生产 8GB（仅搜索摘要） | 无原生推送 | 否，同样要先建仓库 | 好 | 成熟（RBAC），但装机复杂度高 | 高：组件最多的一档 | 仅搜索摘要 |

**明确判定太重、不适合这台边跑 pandas 回测边跑面板的 3.9GB 机器**：Grafana 全家桶（三个额外常驻进程叠加，见上）、Metabase（JVM heap 本身就要吃掉机器的一半以上）、Superset（Celery+Redis+Postgres 多进程，官方最低线已经是"启动失败"的边缘）。这三个都是把内存花在"给多用户、多数据源用的通用 BI 平台"上，而本项目是单用户、数据已经是文件。

**排名结论**：
1. **FastAPI + Jinja2 + HTMX/Alpine（服务端渲染）**：唯一同时满足"单进程内存可控、原生 SSE、直接读文件无需建库、鉴权可完全下放给 Cloudflare Access"四项的选择；代价是要手写模板和响应式 CSS，但这部分工作量是线性、可控的，不会像 Streamlit/Panel 那样带来"会话内存不释放"的运维风险。可以直接把已有的 `reports/dashboard/*.html` 用 `StaticFiles` 挂载/iframe 复用，不必重写。
2. **runner-up：Marimo**：如果想把构建成本压到接近零（不写一行 HTML/JS），Marimo 用纯 Python 就能拿到反应式 WebSocket 推送 + Markdown/表格/图表渲染；代价是 notebook/app 视图的移动端体验不如手写响应式页面，且是常驻 Python 进程（内存曲线不如无状态 FastAPI 请求可预测）。单用户场景下这个代价可接受，作为"先跑起来"的备选。

## B 标准面板清单

标注：**回测报告**（跑完一次历史回测后看的静态/半静态报告）／**实验追踪**（管理很多次参数搜索/训练试验的元层面板）／**实盘监控**（跑纸上/实盘时的运行时状态）。

**回测报告**（QuantStats `reports.py`/`plots.py`、pyfolio `tears.py`、ffn、vectorbt、NautilusTrader `ReportProvider`/tearsheet、Backtrader `analyzers`+pyfolio 集成 共同标准化的面板，已打开链接核实 QuantStats 与 pyfolio 的函数清单）：

- 权益曲线 vs 基准（cumulative returns vs benchmark）——QuantStats `returns`、pyfolio 各 tear sheet 共有底座。
- 滚动 Sharpe / Sortino / 波动率 / Beta——QuantStats `rolling_sharpe/rolling_sortino/rolling_volatility`，pyfolio `rolling_beta`。
- 回撤水下图（underwater plot）+ 最差 N 次回撤明细表——QuantStats `drawdown`，pyfolio underwater + drawdown table。
- 月度收益热力图 + 年度收益对比——QuantStats `monthly_heatmap`/`yearly_returns`，NautilusTrader tearsheet `monthly_returns`。
- 收益分布直方图 / 分位数——QuantStats `distribution`，pyfolio return quantiles。
- 统计摘要表（CAGR/Sharpe/Sortino/Calmar/MaxDD/VaR/SQN）——QuantStats metrics 报告，Backtrader `AnnualReturn/Calmar/SQN` 等 analyzers。
- 敞口/持仓集中度随时间变化（gross/net exposure、long-short、行业/板块）——pyfolio position tear sheet。
- 换手率 & 成交量分布——pyfolio txn tear sheet，Backtrader `Transactions`。
- **交易台账/成交明细**（逐笔 round-trip：持有时长、胜率、单笔盈亏）——pyfolio `create_round_trip_tear_sheet`，vectorbt trade records + `plot_pnl`，Backtrader `TradeAnalyzer`，NautilusTrader `ReportProvider` 的 fills/positions。
- 容量/滑点敏感性、极端历史时期对比——pyfolio `capacity_tear_sheet`/`interesting_times_tear_sheet`（这两项在其余库里较少见，属 pyfolio 特色）。
- 蒙特卡洛路径模拟——QuantStats `montecarlo`。
- 价格图叠加成交标记（bars with fills）——NautilusTrader 特色面板。

**实验追踪**（MLflow UI、Qlib Recorder 的 `MLflowExpManager`、Weights & Biases、Aim、Neptune.ai、Optuna Dashboard 共同标准化的面板）：

- 运行/试验列表 + 参数&指标表格，点列头按某个指标排序、最优结果自动置顶——MLflow（已打开链接材料佐证的摘要）。
- 多运行并排比较（参数差异高亮 + 指标对比）——MLflow "Compare"。
- 超参数**平行坐标图**（parallel coordinates）——MLflow、Optuna Dashboard 都有，是本类最标志性的面板。
- 超参数重要性排序——Optuna Dashboard `plot_param_importances`。
- 优化历史/收敛曲线，随 trial 数推进，支持 Live Update 持续刷新——Optuna Dashboard。
- 指标 vs 参数的散点图/等高线图——MLflow。
- 产物（artifact）版本化存储，挂在每次运行下便于复现——MLflow、Qlib Recorder（`R.save_objects`）、W&B/Neptune/Aim 的 artifact store。
- 团队协作型共享仪表盘——W&B 特色（单用户场景价值低）。
- 元数据深度查询/可复现性——Neptune.ai 特色。

**实盘监控**（纸上/实盘运行时状态，非回测报告，本项目 `signal_logs/**`、`reports/dashboard/catalog.json` 里的 `audits` 已经在积累这类数据）：

- 当前持仓/敞口实时视图、账户权益/PnL 实时曲线。
- 信号日志流（最近生成的信号 tail）。
- 订单生命周期/审计事件流（对应本仓库 `catalog.json` 的 `audits`：`paper_kill_switch`、`paper_order` 等 `kind`）。
- kill-switch 状态、阈值告警。
- Agent 当前动作实时流（正在跑哪个工具/哪一步）——这项已经在 `I-20260919-01-agent-observability-dashboards.md` 里单独调查过具体方案（官方 OTel 导出、或本地会话 JSONL tail + SSE），本简报不重复。

## 对本项目的取舍

- 用 **FastAPI + Jinja2 + HTMX/SSE** 做新增的唯一运行时依赖，直接读 `reports/**`、`strategy_specs/**`、`signal_logs/**`、`~/.claude/projects/**/*.jsonl`；不引入数据库、不做 ETL。
- 复用已有的 `reports/dashboard/*.html` + `catalog.json`（本仓库已有的静态每策略报告生成器）——新驾驶舱只做"索引 + 实时 + 跨策略汇总"这一层，不重造这套 HTML 生成逻辑。
- 回测报告面板照抄 QuantStats/pyfolio 的标准清单（权益曲线 vs 基准、滚动 Sharpe、水下回撤图、月度热力图、交易台账），不要自造指标名字或面板布局。
- 实验追踪那套"平行坐标图/trial 排行榜"词汇量先记下，等策略搜索空间/trial 元数据真正落盘规范化了再上对应面板；当前用一个只读列表页表达同一词汇即可，不必现在就常驻 MLflow/Optuna Dashboard 进程。
- **跳过 Grafana 全家桶、Metabase、Superset**——它们的内存底线（Grafana 核心 512MB 起，Metabase/Superset 建议档普遍要 4–8GB）本身就和"同机跑 pandas 回测、OOM killer 已经优先杀 agent 会话"（见既有 memory 记录）冲突，不值得为单用户装一整套通用 BI/可观测性平台。
- **对 Streamlit/Panel/Reflex 保持警惕**——三者都有"会话状态在服务端不释放、多会话下内存持续增长"的已知问题（社区 issue 佐证），本机是长期挂机的单进程，缓慢内存泄漏比界面稍逊一筹的风险更大；如果后续为了省前端代码换成 Marimo（runner-up），也要盯住它常驻 Python 进程的内存曲线。
- 鉴权直接交给已有的 **Cloudflare Tunnel + Cloudflare Access**（邮箱 one-time PIN），应用层不必自己写登录页；因为这个新驾驶舱**只读、不下达任何交易/写指令**，不适用 CLAUDE.md 里"Remote Dashboard 需要密码会话/Vercel BFF/HMAC/异步任务/双重确认"那一整套——那套规则的前提是命令面（Red actions），本简报调查的对象没有命令面。
- Agent 实时活动这一块直接对接 `I-20260919-01-agent-observability-dashboards.md` 里已经调查过的具体方案，不重新调研。
