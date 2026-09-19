# 情报简报：2025-2026 被广泛分享的 Agent Workbench / Mission-Control UI —— 功能清单

- 场景：机主在一台 Linux 机器上长驻跑 Claude Code + Codex CLI，手机/笔记本经公网访问，**只想看不想发指令**（发指令走 Paseo）。这份简报回答"网上晒的那些'未来感/高效'workbench 截图里到底装了什么功能"，是功能清单，不是选型推荐。
- 方法：WebSearch 定位候选 → WebFetch 打开官网/文档/GitHub README 验证具体 UI → GitHub API（`api.github.com`，结构化字段，视为已核实）拉 star/最后 push/是否 archived/license，统一在 2026-09-19 取样。
- 标注规则：**已打开链接**（WebFetch 打开过原页面，或 GitHub API 结构化字段）／**仅搜索摘要**（只见 WebSearch 摘要或第三方博客转述，未打开原文）／**未核实**（无法确认）。

## 功能清单

| 功能 | 谁做了（含 URL） | 具体形态 | 对单人无人值守场景的价值 |
|---|---|---|---|
| 每个任务/agent 独立 git worktree（或容器）+ 独立分支/终端/diff | Conductor `conductor.build`（已打开链接：`conductor.build/docs`，原文"Each task gets its own workspace, branch, files, terminal, diff, and review path"）；Vibe Kanban `github.com/BloopAI/vibe-kanban`（已打开链接：GitHub API，28,126★，今日仍有 push，Apache-2.0）；Crystal `github.com/stravu/crystal`（已打开链接：GitHub API，2026-02-26 后停更，README 自称"已改名 Nimbalyst"）；Claude Squad `github.com/smtg-ai/claude-squad`（已打开链接：GitHub API，8,498★，tmux+worktree，AGPL-3.0）；Sculptor `imbue.com/product/sculptor`（已打开链接，用 Docker 容器代替 worktree，避免多 agent 抢本地依赖） | 每张任务卡=一条隔离的工作区，diff/terminal 挂在卡片下 | 高——本机已经在跑多个无人值守 agent，worktree/容器隔离是让"看得清谁改了什么"成立的地基，不是装饰 |
| 会话/线程关系图可视化 | Sourcegraph Amp Thread Map `ampcode.com/news/thread-map`（仅搜索摘要：`tessl.io`、`hackernoon.com`、`ainativedev.io` 三方独立报道口径一致；`ampcode.com/threads` 需登录，已尝试 WebFetch 被重定向到登录页，未能打开原始 UI 截图） | 节点=thread，边=引用/延续/交接产生的关系，图形视图，选中节点回车直接跳进那个线程 | 高——多个并行 agent 之间"谁引用了谁的产出/谁在重复劳动"正是"进度如何"这一问题的可视化答案，比平铺列表信息密度高 |
| 实时状态标签（working/waiting/error/idle）+ 浏览器/推送通知 | Terragon（已停运，`github.com/terragon-labs/terragon-oss` 已打开链接：GitHub API，2026-02-10 后为关站快照，259★，Apache-2.0；产品在世时的描述为仅搜索摘要）；`futin/claude-agents-dashboard`（已打开链接：README，1★，2026-09-17 push） | 会话按行列出状态，右侧抽屉提示"answer / plan? / reply? / allow?"，需要人时才推送 ntfy | 高——直接回答"现在需不需要我看一眼"，是"别再打断我"诉求的正面解法 |
| 额度燃尽倒计时 + 用量热力图 | `futin/claude-agents-dashboard`（已打开链接：README，"5h / Week account rate-limit bars"+ 燃烧率 + 到 100% 的预测带；"24×7 hour-of-week heatmap" + "tokens per 1% of 5-hour window per model"） | 顶部两条进度条（5小时/本周），下方每小时用量热力图 | 高——这正是长驻 agent 最实际的痛点（撞额度中断），且是纯只读指标，天然适配 cockpit 定位 |
| 移动端专属排版（非简单响应式缩放） | Factory `factory.com/product/web`（已打开链接，原文"Diff viewer, terminal output, and chat history are tuned for small screens"，另有"Shareable session links"可发链接给人围观） | 手机上 diff/terminal/聊天记录用专门布局，而非桌面版等比缩小 | 高——机主明确要从手机看，这是少数真正为手机场景重新设计过、而非"网页能在手机打开"级别的案例 |
| 会话时间线 + checkpoint 分支回溯（类 git 时间旅行） | opcode（原 getAsterisk/claudia，现已转移到 `github.com/winfunc/opcode`，已打开链接：GitHub API，22,409★，2026-09-18 push，AGPL-3.0；README 原文"Visual Timeline"/"Instant Restore"/"Create new branches from existing checkpoints"） | 会话历史画成可分支的时间线，任意 checkpoint 一键回退/派生新分支 | 中——对"事后复盘 agent 某一步做了什么"有用，但机主是被动观察，不太需要"回退"这个写操作本身，可偷视觉隐喻（时间线）不必偷交互（回退按钮） |
| 容器改动一键"配对"回本地 | Sculptor `imbue.com/product/sculptor`（已打开链接，"With one click, Sculptor brings an agent's work from its container into your local repo"） | 单击把某个隔离容器里的改动同步进本地 IDE/git 状态 | 中/低——这是"把结果拉回来处理"的控制动作，对只读 cockpit 参考价值有限，但"零手动 worktree/依赖重装"这个免摩擦设计值得记一笔 |
| 全局热键把当前窗口截图+隐藏文本注入 agent 上下文 | OpenAI Codex App「Appshots」（仅搜索摘要：`9to5mac.com`、`the-decoder.com`、`developers.openai.com/codex/appshots` 口径一致，2026-05-21 发布，macOS 按两次 Cmd / Windows 按两次 Alt） | 截图 + Accessibility 提取的屏外文本一起发进当前 agent 线程 | 低——这是给 agent"发新指令/新上下文"的输入通道，与"绝不发指令"的目标方向相反；仅作为"如何用一个手势替代大段打字描述"的交互设计参考 |
| 云端任务面板：搜索/启动/改名/停止 + 快捷键 | OpenAI Codex cloud/app（仅搜索摘要：`proflead.dev`、OpenAI 官方博客 `openai/index/introducing-the-codex-app`，官方博客页面本身返回 403 未能直接打开正文，故标"仅搜索摘要"） | 任务卡片列表，`Ctrl+R` 改名、`/rename` 命令、可配置快捷键批量操作 | 中——信息密度高的任务卡片设计值得偷，但整体是控制面（启动/停止任务），只读价值中等 |
| Slack/GitHub 内联 @mention 派单，结果流回原对话 | Cursor 后台 agent `cursor.com/docs/integrations/slack`（已打开链接，"You mention @Cursor in any channel... reads the thread... provides status updates"）；Terragon（仅搜索摘要，"@-mentioning Terragon tools like Slack or GitHub"） | 在已有协作工具里 @机器人 派活，agent 把状态更新贴回同一线程 | 低——这是团队协作场景的派单机制，单人场景发指令已经走 Paseo，没有"团队频道"可贴回 |
| 组织级用量/成本看板 + 角色权限 | Charlie Labs `dash.charlielabs.ai`（仅搜索摘要，"org and repo health, core usage metrics"）；OpenHands Enterprise `openhands.dev`（仅搜索摘要，"role management (owner, administrator, member), API keys, secrets storage"） | 多租户仪表盘，按 org/repo/成员维度切数据 | 低——单人单账号没有"组织"维度，这套复杂度纯属浪费 |
| LLM 调用级 span tree（invoke_agent → chat → execute_tool） | Langfuse `langfuse.com`、LangSmith `smith.langchain.com`、Arize Phoenix `github.com/Arize-ai/phoenix`、Braintrust `braintrust.dev`（均为仅搜索摘要，综合自 `laminar.sh`、`marktechpost.com` 2026 年对比文）；标准由 OpenTelemetry GenAI SIG 定义（仅搜索摘要：`opentelemetry.io/blog/2026/genai-observability`，`gen_ai.request.model`/`gen_ai.usage.*`/`execute_tool` span 等属性，2026-03 仍是 experimental 状态） | 每次工具调用/模型调用变成一条子 span，前端画成瀑布图 | 中——粒度比"这个会话在跑什么工具"更细，适合调试策略研究 agent 内部逻辑，但这些是给应用开发者接 SDK 用的可观测性平台，不是拿来即用的 agent cockpit，且 Codex CLI 无官方对应导出（与 I-20260919-01 结论一致） |
| tmux 会话编排 + 自动继续/限额自愈 | Claude Squad（已打开链接：GitHub API）；`Tmux-Orchestrator` 系列 fork（仅搜索摘要，多个二次开发版本如 `AW2307/Tmux-Orchestrator-Enhanced-AW`，"auto-responder, limit monitoring, audio notifications"） | 每个 agent 一个 tmux pane，脚本监测限额自动 respond/续跑 | 中——对"无人值守跑通宵"这个诉求本身很关键，但这是控制/自愈脚本，不是只读监控面 |
| 拟人化状态吉祥物 + Kanban 状态板 | `hoangsonww/Claude-Code-Agent-Monitor`（已打开链接：README + GitHub API，1,010★，2026-09-19 push，MIT，"a Kanban status board... a cute buddy"） | 看板列=状态，另有一个随状态变化的卡通形象 | 中——纯装饰但符合"一眼扫过去、不用读文字就感知健康度"的外围视觉设计思路 |
| 自我定位为"只读、无遥测、本地优先"的多 agent 控制塔 | `aymandakirgh/agentcontroltower`（已打开链接：GitHub API，2026-09-19 今天有 push，3★、0 fork，描述原文"A local-first control tower for fleets of AI coding agents — observe & steer many parallel Claude Code agents from one screen. Read-only, no telemetry."） | 本地 Web Dashboard，只读 `~/.claude/projects` | 高——定位与本次需求逐字重合，但项目今天刚推、无第三方验证，只支持 Claude Code，需自己审代码再决定要不要接公网（与 I-20260919-01 第 2 条重合，此处仅作定位参照） |
| 手机/Web 端语音+双向控制客户端（对照组） | `slopus/happy`（已打开链接：GitHub API，23,832★，2026-09-19 push，MIT，"Mobile and Web client for Codex and Claude Code, with realtime voice, encryption"） | 手机 App 直接对两种 agent 下指令+看回复，端到端加密 | 低（对本次"绝不发指令"目标而言）——它是双向控制通道，能力上覆盖了"看"，但打开了一个能对 agent 下指令的公网入口，与只读诉求的安全模型冲突（与 I-20260919-01 第 5 条同一结论） |

## 值得偷的交互细节

1. **5小时/本周额度条 + 燃烧率 + 到 100% 的预测带**——`futin/claude-agents-dashboard`：顶部两条进度条不只显示"已用多少"，还画出按当前速率推算的"预计几点撞线"预测带。
2. **按状态分类的推送，而非按事件分类**——同一项目：只在会话进入"question / plan / permission-dialog / finished-turn"四种"需要人"的状态时才 ntfy 推送，其余全部静默；另设 `NTFY_TOPIC_DESK` 让在电脑前时推送改走桌面、手机保持安静。
3. **线程关系图，节点回车即跳转**——Amp Thread Map：把"我开了 10 个并行会话，哪个依赖哪个、哪个在重复劳动"画成图而不是列表，选中节点直接跳进那个线程继续看。
4. **每 1% 额度对应多少 token 的换算 + 一周用量热力图**——`futin/claude-agents-dashboard`："Token Value" 面板把抽象的百分比额度换算成"每 1% 相当于多少 token"，配合 24×7 热力图看清哪几个时间段最容易撞限额。
5. **移动端不是缩放，是重新布局**——Factory Web/Mobile：diff viewer、terminal 输出、聊天记录三块内容在手机上有专门排版，明确写"tuned for small screens"而不是响应式自适应。
6. **会话时间线做成可分支的 git 图**——opcode/winfunc-opcode：把一次 agent 会话的历史节点画成时间线，checkpoint 之间可以"从任意一点再分一条支线"，而不是线性聊天记录。
7. **拟人化吉祥物做外围视觉状态**——`hoangsonww/Claude-Code-Agent-Monitor`：Kanban 看板旁边放一个随整体健康度变化的卡通形象，用于"不读文字也能瞟一眼知道大概状态"。
8. **任务派单发生在原有协作场所，结果流回原线程**——Terragon（已停运，仅作模式参考）/ Cursor Slack 集成：不用切换到专门 App，@ 一下机器人、结果和进度更新自动贴回同一条 Slack 消息串。
9. **只读、无遥测作为项目的第一句自我描述**——`aymandakirgh/agentcontroltower`：README 开篇就是"Read-only, no telemetry"，把安全边界写成产品定位本身，而不是一个可选开关。
10. **全局热键把当前窗口"拍"进 agent 上下文，含屏外文本**——Codex Appshots：按两下 Cmd/Alt，不仅截图，还通过 Accessibility API 把窗口里滚动到屏幕外的文本一起发送，免去手动复制/描述（这条是"发指令"侧的设计，仅供交互手法参考，不建议照搬到只读面）。

## 只在多人/多仓库场景才有意义的

- **PR/diff 上的多人评论线程**（Factory"leave comments"、Cursor Slack @团队成员）——没有队友可以留言，本机只有机主一个人看。
- **组织角色与权限管理**（OpenHands Enterprise 的 owner/administrator/member、API keys、secrets 分租户存储）——单账号场景没有"组织"这一层，加了纯粹是维护负担。
- **团队级线程共享库 + 采纳率分析**（Amp"team can reuse solutions, monitor adoption"）——没有团队去"采纳"别人的会话产出。
- **按坐席计费的用量看板 / 多租户成本中心**（Charlie Labs 的 org/repo 健康度仪表盘、Factory Slack workspace 管理员设置）——一个人一个钱包，不存在"哪个同事花超了"的问题。
- **人与人之间的任务交接/审批队列**（Devin 把会话指派给同事、Charlie Labs 由 issue/PR 事件触发的团队级值班机器人）——没有下一个人可以交接。
- **同一 buffer 里多个人类 + 多个 agent 同时编辑的协作层**（Zed 把"多人多 agent 同 buffer 协作"当作头等特性）——本机没有并发的第二个人类编辑者。
- **面向组织的插件/Agent 市场**（OpenHands"internal add-on marketplace per organization"）——市场机制服务的是"多团队复用配置"，单人自己维护几个 skill 文件就够。

## 三个最像用户想要的产品

**Conductor（`conductor.build`）**——它给人"未来感"不是因为好看，而是因为它把"多个 agent 并行"直接映射成"多个独立工作区"这个开发者已经熟悉的心智模型：每个任务=一条分支+一份文件+一个终端+一份 diff，四样东西摆在一起就能判断"这个任务走到哪一步、改了什么、能不能直接看 diff 决定要不要采纳"，不需要先读一堆日志文字再在脑子里拼出状态。它被 Linear/Vercel/Notion/Stripe 的工程师分享（仅搜索摘要），说明这套"工作区并排"的隐喻已经被验证能大幅降低"追踪多个并行 agent"的认知负担，这正是机主想要的东西——只是它是双向控制面板，机主可以只用它的展示层（worktree+diff 并排），不使用其派发功能。

**Vibe Kanban（`github.com/BloopAI/vibe-kanban`，已打开链接：GitHub API，28,126★，今天仍在更新，Apache-2.0）**——"未来感"来自于它把大家最熟悉的项目管理隐喻（看板）直接套在 agent 编排上：任务卡片从"待办"移动到"进行中"到"待审"到"完成"，每次移动背后是真实发生的 git worktree 创建/PR 生成，而不是人工拖拽。这种"熟悉的界面外壳 + 全自动的内容"组合，是"高效"感的来源——用户不需要学一套新工具的心智模型，agent 在后台做的事直接落进一个他已经会用的看板里。即便公司层面"即将 sunset"（仅搜索摘要），代码库本身今天仍有提交、社区仍在维护，说明这个交互隐喻本身比公司的商业模式更长寿，值得单独抽取视觉层（看板列=状态）而不抽取派单层。

**Amp Thread Map（`ampcode.com/news/thread-map`）**——三者中最不像"日志查看器"的一个：前两者本质仍是"列表/看板 + 文字状态"，Thread Map 是唯一把"多个并行 agent 之间的关系"画成图论结构（节点+边）的产品，直接回应了"agent 一多，我就搞不清哪个依赖哪个、哪个在重复劳动"这个真实困惑（三方独立报道口径一致：`tessl.io`、`hackernoon.com`、`ainativedev.io`，仅搜索摘要，未能打开需登录的原始 UI）。这种"空间化"的信息组织方式，是"高效/未来感"和"能用但笨重的日志墙"之间最直观的分界线——机主想要的"一眼看出几个 agent 现在各自在做什么、进展如何"，图论可视化比时间序列日志更接近这个诉求的本质，只是目前该功能只在需要登录的 CLI/Web 里，且限 Amp 自己的会话数据，尚未看到可迁移到 Claude Code/Codex 会话的独立实现。
