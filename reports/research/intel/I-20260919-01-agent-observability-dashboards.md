# 情报简报：可自托管的编码 Agent 只读监控驾驶舱（Claude Code + Codex CLI）

- 范围：单台 Linux 机器上跑 Claude Code 和 OpenAI Codex CLI，机主想从手机/浏览器远程（经公网）**只看不发指令**：每个 agent 现在在干什么（含推理/思考流）、会话历史、token/成本消耗、订阅额度剩余。
- 方法：WebSearch 定位候选项目 → 对最相关的用 WebFetch 打开 README/文档验证 → 用 GitHub API（`api.github.com`，视为已核实的结构化数据，而非搜索摘要）拉取 license / star / 最后一次 push 时间，统一在今天（2026-09-19）取样。
- 标注规则：每条声明后括注校验等级——**已打开链接**（我用 WebFetch 打开过页面，或用 GitHub API 拉取过结构化字段）／**仅搜索摘要**（只看到 WebSearch 返回的摘要，没有打开原文）／**未核实**（无法确认，按不成立处理）。

---

## 1. Claude Code 官方 OpenTelemetry 导出

`CLAUDE_CODE_ENABLE_TELEMETRY=1` 是官方内建的可观测性开关（已打开链接：`code.claude.com/docs/en/monitoring-usage`）。

- **指标（metrics，OTLP）**：`claude_code.session.count`、`claude_code.lines_of_code.count`、`claude_code.pull_request.count`、`claude_code.commit.count`、`claude_code.cost.usage`、`claude_code.token.usage`、`claude_code.code_edit_tool.decision`、`claude_code.active_time.total`。
- **事件（logs/events）**：`claude_code.user_prompt`、`claude_code.assistant_response`、`claude_code.tool_result`。默认全部**脱敏**（prompt/response/tool 参数显示 `<REDACTED>`），要拿到明文需分别设 `OTEL_LOG_USER_PROMPTS=1`、`OTEL_LOG_ASSISTANT_RESPONSES=1`、`OTEL_LOG_TOOL_DETAILS=1`。
- **红旗/未核实点**：文档没有说明 `assistant_response` 事件里是否包含 extended-thinking 的 `thinking` 内容块本身，还是只有最终回答文本——**未核实**，需要自己开一次带 `OTEL_LOG_ASSISTANT_RESPONSES=1` 的会话去看 Loki/日志里的字段。
- **官方 Grafana 面板**：文档页面**没有提到任何官方预制 Grafana dashboard**（已打开链接，同一页面）——都是社区做的（见下节）。
- **Codex CLI 对应物**：搜索未找到 OpenAI 官方对 Codex CLI 的等价 OTel 导出开关（仅搜索摘要，倾向于**不存在**）。Codex CLI 自己的可观测性只有本地 rollout JSONL 文件（见第 4 节）。

## 2. 消费官方 OTel 数据的 Grafana 方案（社区，非官方）

| 项目 | 展示什么 | 数据管线 | 自托管 | 协议 | 最后更新 | 校验 |
|---|---|---|---|---|---|---|
| `ColeMurray/claude-code-otel` | 成本/token/DAU-WAU-MAU/工具成功率/API 延迟/代码产出率，Grafana 多面板 | Claude Code → OTel Collector → Prometheus(指标)+Loki(日志) → Grafana，docker-compose 一键起 | 是 | MIT | 2025-06-17（已打开链接，GitHub API `pushed_at`），距今超一年，**已停更** |
| `aaraujodata/claude-code-otel` | 同上定位，自称"成本/事件"面板 | 同架构 OTLP gRPC → Collector → Prometheus/Loki → Grafana | 是 | MIT | 2026-02-19（已打开链接），0 star，**几乎无人用过** |
| `li0nel/claude-otel` | 按会话的成本/token 指标，对接 Grafana Cloud | OTel → Grafana Cloud | 是（但示例默认打 Grafana Cloud，需要改成本地栈） | 未声明 license | 2026-03-05（已打开链接） | 
| `NikiforovAll/ccdashboard` | OTel 可视化 | 未详查 | 未详查 | 未声明 license | 2025-12-21（已打开链接），4 star |
| Grafana Labs 官方市场 **#25255**「Claude Code Metrics (Prometheus)」 | 总览 KPI、按用户/模型/会话排行榜、成本趋势、缓存命中率 | Prometheus/VictoriaMetrics/Mimir/Thanos 均可，需 Grafana 11+ | 是（导入 JSON 即可） | 面板本身 Apache-2.0 风格市场协议 | 页面未显示具体日期（已打开链接：`grafana.com/grafana/dashboards/25255-...`），作者 `rockdarko`，社区作品非 Anthropic 官方 |
| Grafana Labs 官方市场 **#25052**「Claude Code」 | 同类 KPI，但数据源是 **Azure Monitor / Application Insights**（KQL 查询），不是 Prometheus | Azure 专属，不适配纯本机 Prometheus 栈 | 是 | 同上 | 最近修订 2026-05-01，初版 2026-03-23（已打开链接） |

结论：官方遥测 + 社区 Grafana 面板可以覆盖"token/成本/会话数/工具成功率"这一层，**只对 Claude Code 有效，找不到 Codex CLI 的对应遥测源**；"推理流"要额外开 `OTEL_LOG_ASSISTANT_RESPONSES=1` 且未核实是否含 thinking 块。

## 3. 只看 usage/quota 的终端小工具（本地文件，无网络请求）

| 项目 | 展示什么 | 数据来源 | 远程/Web UI | 协议 | 最后更新 | 双支持(Claude+Codex) | 校验 |
|---|---|---|---|---|---|---|---|
| `ccusage/ccusage`（原 `ryoppippi/ccusage`，已迁移组织） | 按日/周/月/会话/5小时窗口的 token 与成本报表；`blocks --live` 实时监控模式**已在 v18.0.0 移除**，改用 `statusline` | 本地 JSONL 日志，纯离线 | 无（终端表格/JSON输出） | MIT | 2026-09-19，今天仍有提交（已打开链接：GitHub API + Discussion #803） | 是，文档列出 `ccusage codex daily` 等命令（已打开链接） |
| `Maciek-roboblog/Claude-Code-Usage-Monitor`（`pip install claude-monitor`） | 实时终端仪表盘：燃烧率、P90 预测、额度耗尽预警、`--warehouse` 长期历史 | `~/.config/claude` 下本地 JSONL，无网络回传 | 无（Rich 终端 UI），可导出 JSON/CSV | MIT | 2026-07-05（已打开链接），8.7k star | 仅 Claude Code |
| `Dicklesworthstone/coding_agent_usage_tracker`（caut） | 一条命令看 16+ 家（含 Codex、Claude、Gemini、Cursor、Copilot）**剩余订阅额度百分比 + 倒计时** | CLI 调用/本地 OAuth token/本地 JSONL，多策略 | 无 Web UI，仅终端三种输出格式 | MIT + OpenAI/Anthropic Rider | 2026-09-04（已打开链接），87 star | 是 |
| `steipete/CodexBar` | macOS 菜单栏图标，同时显示 Codex/Claude/Cursor 等额度窗口与重置时间 | 本地登录态/CLI，无需重新登录 | 仅 macOS 菜单栏，**非 Linux/非手机** | MIT | 2026-09-19（已打开链接），21.6k star | 是，但平台不符（本机是 Linux） |
| `junhoyeo/tokscale` | 终端 + 全球排行榜，年度总结图 | 本地文件解析 | 有自托管 docker/compose 栈，但默认模式会把用户名/总 token/模型明细**公开发布到公共排行榜并被搜索引擎收录** | MIT | 2026-09-18（已打开链接），5.5k star | 是（含 Codex/Claude 等） | 红旗：默认路径不是纯本地私有，需要显式选择自托管模式避免数据外泄 |
| `eckardt/cchistory` | 类似 shell history，列出某次会话里 Claude Code 跑过的 Bash 命令，支持 `tail -f` 式实时流 | 本地会话 JSONL | 无 Web UI | MIT | 2026-06-10（仅搜索摘要），137 star | 仅 Claude Code |

## 4. 能看到"会话内容/推理流"的查看器

- **Claude Code 侧的数据基础**：会话 transcript JSONL（`~/.claude/projects/**/*.jsonl`）里，assistant message 的 content block 包含 `thinking` 字段（含 `signature`），是明文可读的（仅搜索摘要：`huytieu.com` 博客与社区 issue `anthropics/claude-code#78343` 印证 `.jsonl` 里确有 thinking block，但**官方桌面 App 的 Transcript 视图在 Windows 上有已知 bug 不渲染 thinking**，说明"读文件里有没有"和"某个查看器愿不愿意画出来"是两件事）。
- **Codex CLI 侧的数据基础**：rollout JSONL（`~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`）里有 `agent_reasoning` 事件类型，官方定位是"模型内部推理"（仅搜索摘要：`dev.to/milkoor` 逆向工程记录 + `openai/codex` discussion #3827），但 OpenAI 模型的"推理"通常是摘要而非原始思维链，**具体这个字段是摘要还是更完整——未核实**。

| 项目 | 展示什么 | 数据来源 | 能否公网远程访问 | 自托管 | 协议 | 最后更新 | 双支持 | 校验 |
|---|---|---|---|---|---|---|---|---|
| `chiphuyen/sniffly` | 用量统计、错误分类、可浏览的消息历史，可生成分享链接 | 本地 JSONL，`sniffly init` 后起 `localhost:8081` | 本身只监听本地，需要自己套反向代理/隧道才能公网访问 | 是 | MIT | 2025-08-08（已打开链接），1.3k star，**一年多没更新** | 仅 Claude Code |
| `davila7/claude-code-templates`（Conversation Monitor + Analytics Dashboard） | 官方文案称"实时看 Claude 回复、分析 AI 推理、监控工具用法与生产力指标" | 本地会话文件 | **`--chats --tunnel` 内置 Cloudflare Tunnel，是目前唯一现成的"一条命令拿到公网可访问只读页面"的方案** | 是 | MIT | 2026-09-19（已打开链接），30.8k star，活跃度最高 | 文档未提 Codex（仅搜索摘要/已打开链接均未见） |
| `Victarry/codex-trace` | Codex CLI 会话查看器：对话、工具调用、token、多 agent 协作链，支持"live SSE tailing"看进行中会话，桌面+Web 两种模式 | 本地 rollout JSONL | 可配置 host/port（`CODEXTRACE_HTTP_PORT`），**未内置公网隧道/鉴权**，需要自己加反代 | 是 | MIT | 2026-09-07（已打开链接），fork 仓库 0 star | **仅 Codex CLI**（README 明确写"Claude Code 用户请去用 claude-code-trace"） |
| `Quantum-vik/claude-view` | 逐字符终端镜像 + 面板：prompt/回复/thinking/工具输出/子 agent 树/逐轮成本 | 本地 PTY + JSONL，Tauri 桌面应用 | **只绑定 localhost，桌面原生应用，无法从手机浏览器访问** | 是（本机） | 未声明 license | 2026-09-19（已打开链接），0 star，个人项目 | 仅 Claude Code |
| `jhlee0409/claude-code-history-viewer` | 桌面 App，浏览/分析 Claude Code 会话历史，README 提到覆盖 29 家 provider（含 Codex CLI、Gemini CLI、Cursor 等） | 本地会话文件，多 provider 适配 | 桌面应用，非远程 | 是 | MIT | 2026-09-04（已打开链接），2.2k star | **是**（多 provider，含 Codex），但没有远程/Web 形态 |
| `ly4096x/ClaudeCodeTranscriptViewer` | 零依赖网页，渲染单个 `.jsonl`（含可折叠 thinking block），支持拖拽上传 | 手动喂 `.jsonl` 文件，不自动 tail 实时会话 | 静态网页，非实时、非多 agent 总览 | 是 | GPL-3.0 | 2026-09-15（已打开链接），1 star | 仅 Claude Code |
| `aymandakirgh/agentcontroltower` | **专门定位为"多个并行 Claude Code agent 的只读驾驶舱"**：每个 agent 的实时状态（working/waiting/error/idle）、当前工具、token、成本估算、告警 | 读 `~/.claude/projects/**/<session>.jsonl`，另有 `generic-jsonl` 适配器可指向任意目录 | Ink 终端 UI + 本地 Web Dashboard（`127.0.0.1:4517`，含钻取/成本趋势），未内置公网隧道 | 是 | MIT | 2026-09-19（已打开链接），**仅 3 star、0 fork，今天刚推的仓库，无使用记录/无第三方验证** | README 只写 Claude Code 原生适配，Codex 未提；`generic-jsonl` 理论上可能指向 Codex 的 rollout 目录，但**未核实**是否真的解析得出字段 |
| `abhijit-s/abtop`（及多个同名 fork：`ntung`、`cikichen`、`graykode`、`ShinnChow` 等） | htop 风格 TUI：**同时监控 Claude Code 与 Codex CLI** 的会话、token、上下文窗口占用、速率限制、端口、子 agent；明确设计为"不显示文件内容和 prompt 文本"（隐私优先） | 仅本地文件 + 进程/端口元数据，不需要 API key | 纯终端，无 Web/远程；要手机看需自己套 `ttyd`/`gotty` 或走 SSH 客户端 | 是 | MIT | 2026-09-15（已打开链接），0 star（新项目，多个人各自 fork 说明它刚火起来但**无长期验证**） | **是**（唯一明确原生双支持、且强调只读、隐私优先的 TUI） |

## 5. "控制塔/编排"类工具——名字常被提到，但不是只读监控（按题目要求也过一遍）

| 项目 | 实质 | 是否只读 | 手机/公网 | 协议 | 最后更新 | 校验 |
|---|---|---|---|---|---|---|
| Vibe Kanban（`BloopAI/vibe-kanban`，最初叫法与仓库路径在检索中出现过变化） | 看板式编排多个 agent（Claude Code/Codex/Gemini/Copilot 等），每个任务起独立 git worktree | **否**——核心功能是派发/启动任务，不是纯查看 | Web UI，但设计给同机器/局域网用，非"只读远程监控"定位 | Apache-2.0 | 2026-09-19（已打开链接），28.1k star | "即将 sunset、转社区维护"的说法仅搜索摘要，未核实 |
| Claude Squad（`smtg-ai/claude-squad`） | 基于 tmux + git worktree 管理多个 Claude Code/Codex/OpenCode/Amp 会话 | 否——是控制/切换会话的工具 | 纯终端，非手机原生 | AGPL-3.0 | 2026-08-20（已打开链接），8.5k star | 仅搜索摘要（功能描述） |
| opcode（原 Claudia，`getAsterisk/opcode`） | Tauri 桌面 GUI：建自定义 agent、管理交互式会话、跑后台 agent | 否——是控制台，不是只读仪表盘 | 桌面应用，非手机/非公网 | 仅搜索摘要（README 提及 15k+ star，未逐字核实 license） | 未逐一核实 push 时间 | 仅搜索摘要 |
| `slopus/happy`（Happy Coder） | 手机/Web 客户端，**同时支持 Codex 和 Claude Code**，端到端加密，经自建 Happy Server 中转 | **否，产品定位就是"从手机远程操控/发指令"**，与题目"不想发指令"的要求正相反；不过既然能控制，自然也能看实时流 | **是**——这是目前唯一"手机 App + 公网 + 双支持 Claude/Codex"都占全的产品，但代价是它是双向控制通道，不是纯只读 | MIT | 2026-09-19（已打开链接），23.8k star，Server 组件在同仓库、可自托管 | 若只用来"看"而从不在手机上发消息，理论上可以把它当只读用，但**信任/攻击面等于开放了一个能对两个 agent 下指令的入口**，与题目要求的"绝不发指令"精神冲突，不建议 |
| `coder/agentapi` | Go 写的 HTTP API，通过终端模拟统一控制 Claude Code/Goose/Aider/Gemini/Amp/Codex | 否——是控制面 API | 无内置公网层 | MIT | **已归档（archived），2026-09-13 后不再维护**（已打开链接：GitHub API `archived: true`） | fork `k1dav-c/agentapi` 仍在更新（2026-09-18，已打开链接），但也是控制面，非监控 |

## 6. 代理/中间人类工具——按题目要求单独标红，禁用

- **`snipeship/ccflare`（及多个 `better-ccflare` fork）**：定位是"终极 CC 代理"，在 Claude Code 和 Anthropic 之间做负载均衡/多账号切换/请求级分析，仪表盘展示 token 用量（仅搜索摘要）。**它本质是替换请求路径的反向代理**，即便它声称支持"Claude OAuth 账号"，也是把 OAuth 会话接管到自己的代理进程里做多账号调度——这正是题目要求排除的"API 流量代理/中间人"模式，与本机"直接用订阅 OAuth、不经代理"的现状不兼容，**不建议使用**（MIT，1.0k star，最后更新 2026-04-19，已打开链接：GitHub API）。

---

## 可复用的

按"离题目要求（只读、手机/公网可达、双支持、含推理流、含额度）"的贴合度排序，最多 5 个：

1. **Claude Code 官方 OTel 导出 + 自托管 Prometheus/Loki/Grafana**（`CLAUDE_CODE_ENABLE_TELEMETRY=1` 官方开关，接 `aaraujodata/claude-code-otel` 或 `rockdarko` 的 Grafana #25255 面板）。理由：唯一有官方数据契约（不是逆向解析 jsonl）、纯导出无需代理、Grafana 本身天然是可远程访问的 Web UI（自己套反代/HTTPS 即可手机看）。**缺口**：只覆盖 Claude Code；"推理流"是否真能通过 `assistant_response` 事件拿到 thinking 内容未核实，需要先跑一次验证。
2. **`aymandakirgh/agentcontroltower`**：README 对"只读"的自我承诺（只读 `~/.claude`、绝不写)与题目描述几乎逐字对应，自带本地 Web Dashboard，是本次检索里**唯一专门为"多 Claude Code agent 只读驾驶舱"这个精确需求设计的项目**。**缺口**：今天刚推、3 star、0 第三方验证，只支持 Claude Code，用前必须自己审代码再决定要不要暴露到公网。
3. **`abhijit-s/abtop`**：本次检索里**唯一原生同时支持 Claude Code 和 Codex CLI**、且明确以"隐私优先/不展示 prompt 内容"为设计原则的实时状态工具（session、token、上下文窗口、速率限制）。**缺口**：纯 TUI，要手机看得自己包一层 `ttyd`/`gotty`；不展示推理文本本身（只给状态和用量）。
4. **`davila7/claude-code-templates` 的 Conversation Monitor（`--chats --tunnel`）**：本次检索里**唯一自带"一条命令 + Cloudflare Tunnel 直接公网可访问"的现成方案**，官方文案称能看实时回复与推理，项目本身活跃度最高（今天有提交、30.8k star）。**缺口**：只支持 Claude Code；具体展示多少推理内容、隧道端的鉴权强度都未独立核实，接公网前要自己确认隧道加了密码/Access 策略。
5. **额度/成本层：`ccusage` + `Maciek-roboblog/Claude-Code-Usage-Monitor`（Claude 侧）配 `Dicklesworthstone/coding_agent_usage_tracker` 或 `steipete/CodexBar`（Codex 侧，CodexBar 是 macOS-only，此处更适合参考其判额度逻辑而非直接用它)**：三者都只读本地文件/本地登录态，无需代理，能拿到 token/成本/剩余额度百分比。**缺口**：都没有自带的远程 Web UI，需要自己把输出（JSON 模式都支持）钉到一个小状态页上才能手机看——这是最省心、最该复用的"数据层"，但"呈现层"要自己接。

## 必须自己写的部分

以下内容不存在于任何上面调研到的开源项目里，因为它们本质是 Open Composer 自己的领域数据，不是"agent 跑得怎么样"这类通用可观测性指标：

- **策略研究进度**（哪个假设卡在哪一步、`research_pass`/`llm_contribution_pass` 状态机走到哪）——这些是 `reports/research/` 下的 JSON/Markdown 文件和 `capabilities/registry.yaml` 里的状态，没有通用 agent 监控工具知道这个 schema。
- **回测结果**（`workflow_pass`/`paper_ready_pass` 门禁、benchmark family、walk-forward 证据、执行现实性评审结论）——这些结构化产物只存在于本仓库的 report 文件里；上面所有工具最多只能告诉你"某个 Claude Code 会话跑了多久、花了多少 token"，不知道那次会话产出的回测报告本身是否通过了门禁。
- **假设卡状态**（H-YYYYMMDD-NN 系列卡片的存活/证伪状态、否定条件是否触发）——同样是本仓库自定义的文件格式（`reports/research/iterations/`、`reports/research/intel/` 等），需要专门写一个小的只读聚合视图（读文件、渲染状态），这部分只能自己实现，且应遵守本项目"只读、不经代理、不暴露密钥"的同一套铁律。

这三块建议的落地方式是：写一个很薄的自建只读页面/状态聚合器，专门渲染本仓库的文件系统状态（不涉及给 agent 发指令），可以和上面第 4 条选定的 agent 可观测性方案共享同一个反向代理/隧道入口，但代码本身必须自己写——这不在本次情报调研范围内建议直接采纳任何现成项目。
