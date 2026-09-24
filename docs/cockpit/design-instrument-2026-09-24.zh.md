# Cockpit 设计第四稿「Instrument」：从模板到仪器 — 2026-09-24

> 机主 2026-09-24 的要求：重新审视 Cockpit 的设计和交互，要美观、有设计感、流畅、AI-native，不要太素太简陋；按规范的设计流程从头来（定目标 → 找参考 → 出方案 → 选择 → 实现 → 批评），专业作品集水准。
>
> 第三稿（`design-refresh-2026-09-21.zh.md`，冷色深色优先、Geist、发丝线）方向本身已被机主确认，本稿**不推翻方向**，只解决"素"：保留冷色 / 深色优先 / Geist / 低密度 / 玻璃只给控制层，给产品一个物理隐喻和真实数据的主视觉。

## 1. 诊断：第三稿为什么显得"素"

对 2026-09-24 实际渲染（6 屏 × 桌面深浅色 + 手机）逐屏检查，证据如下：

| 问题 | 证据 |
|---|---|
| 所有屏幕是同一个模板 | 6 屏都是"4 张等宽数字卡 + 一个带框列表"，换屏只换数字 |
| 一个量化 + agent 产品里没有任何图 | 权益、agent 活动、研究管线、token 消耗全是数字，没有一张真实数据图 |
| 没有视觉焦点 | 页面上最亮的东西是状态点，最大的东西是 30px 数字，彼此等重 |
| AI-native 很薄 | agent 是否在干活、在干什么，只有顶栏一个绿点 |
| 发光几乎看不见 | 画布径向光 14% 透明度，被卡片挡住 |
| 手机上标题重复、首屏被数字卡占满 | 顶栏"Paper"+页内"Paper"；首屏 4 张卡后才看到内容 |
| 落地页是假设卡列表 | 打开 Cockpit 第一眼看不到"有没有出事 / agent 在干什么 / 权益 / 额度" |

## 2. 目标与原则

**目标**

- G1 手机上 3 秒看完一屏：有没有需要处理的事、agent 在干什么、模拟盘权益、额度消耗。
- G2 有辨识度，不再像后台模板。
- G3 每屏一张真实数据主视觉，整体仍然低密度。
- G4 AI-native 靠"活着的状态"表达：运行中的脉冲、工具调用流、正在执行的命令，而不是聊天框。
- G5 流畅：屏内切换不刷新、动效解释状态变化、`prefers-reduced-motion` 全部停止。
- G6 诚实：只画真实观测点；没有数据就明确写"没有"。
- G7 深浅两套主题、桌面与手机两套外壳都成立。

**原则**

- P1 一个问题配一个主视觉。
- P2 光代表生命：亮度只留给活着的东西（环境光、LED、运行脉冲、最新一根权益柱）。
- P3 数字就是排版：大数字比例数字、负字距，列内用等宽数字。
- P4 结构靠感觉而不是线框：面板 = 机加工面板，图表 = 嵌在面板里的显示屏。
- P5 玻璃只给控制层（侧栏、状态条、标签栏、抽屉），内容永远不透明。
- P6 每个动效都在解释一个状态变化。

## 3. 参考（2026-09-24 以无头 Chromium 1440×900 深色截取；第三方素材不入库，只留链接）

| 设计想法 | 来源 | 取走的东西 | 不取的东西 |
|---|---|---|---|
| 光即信息：深黑上一个发光体 | [vercel.com](https://vercel.com)、[linear.app](https://linear.app) | 单一光源、单色、光只给活着的东西 | 营销页的大空洞与大标语 |
| 结构可感而不可见 | [Linear 设计刷新](https://linear.app/now/behind-the-latest-design-refresh)、[How we redesigned the Linear UI](https://linear.app/now/how-we-redesigned-the-linear-ui)、[2026-03-12 UI refresh](https://linear.app/changelog/2026-03-12-ui-refresh) | 侧栏退后、图标减少、"别争夺你还没赢得的注意力" | 他们转向暖灰（机主要冷色） |
| agent 是行动者：动词开头的实时叙述 | [cursor.com](https://cursor.com)、[amux 网页面板](https://amux.io/features/web-dashboard/)、[AgentsRoom](https://agentsroom.dev/multi-agent-dashboard) | 每个运行中的 agent 一行实时状态：工具 · 目标 · 耗时 | 聊天输入框（Cockpit 只读） |
| 仪器显示：安静的机身 + 小而亮的屏 | [teenage.engineering OP-1](https://teenage.engineering/products/op-1)、[nothing.tech](https://nothing.tech) | 模块化面板、哑光黑上的细亮图形、点阵作为签名元素 | 拟物按键、点阵字体做正文 |
| 图表承担重量 | [Robinhood Legend](https://robinhood.com/us/en/legend/) | 每屏一张真实数据主视觉；涨跌色是唯一饱和的一对 | 六屏密度、到处霓虹 |
| 玻璃只给控件 | [Apple Liquid Glass 发布](https://www.apple.com/newsroom/2025/06/apple-introduces-a-delightful-and-elegant-new-software-design/)、[Liquid Glass 文档](https://developer.apple.com/documentation/technologyoverviews/liquid-glass)、[WWDC25 219](https://developer.apple.com/videos/play/wwdc2025/219/)、[mercury.com](https://mercury.com) | 控制层玻璃 + 高光边，内容层不透明 | 摄影背景 |
| 同类产品对照 | [composer.trade](https://www.composer.trade) | 权益曲线与策略列表的主次关系 | 营销化文案 |

Fey（fey.com）当天已是停服公告页，Raycast 截图超时，二者未纳入。

## 4. 三个方案（同一份真实数据渲染，comps 见 `docs/cockpit-screens/v4/concept-{a,b,c}-{desktop,phone}.png`）

| 方案 | 构图 | 签名元素 | 结论 |
|---|---|---|---|
| A · Instrument | 便当格（bento）模块面板，图表嵌在凹陷的"显示屏"里 | 24 小时点阵 LED 活动表；只有活着的东西发光 | **选用**：最能同时满足 G1/G2/G3，工程上全部可服务端渲染 |
| B · Pulse | 以时间线为主轴的事件流，所有东西都是一条事件 | 流式"正在进行"卡片（工具行 + 光标） | 事件流适合审计，不适合 3 秒扫一眼；**借用其流式卡片**做 agent 面板 |
| C · Liquid | 大量玻璃层叠、手机上一个实时活动胶囊 | 灵动岛式的活动胶囊 | 玻璃过多违背 P5；**借用胶囊思路**：手机首屏的注意事项横向芯片条 |

A 的已知问题在实现中处理：agent 面板内容不足（加入第二个运行会话、错误会话、限额作业）；对数刻度让点阵饱和（改为线性）；手机上标题与元信息换行（手机隐藏页内标题、缩短元信息）。

## 5. 信息架构

- 新增 **Now**（`/`）：一屏回答四个问题。假设卡看板移到 `/hypotheses`。
- 桌面侧栏分组：Now｜Research（Hypotheses、Lineage）｜Operations（Agents、Paper）｜System（Quota、Health），⌘1–7 按此顺序。
- 手机标签栏 5 个：Now、Research、Agents、Paper、System；Lineage 从看板进入、Quota 从 Now 和状态条进入，标签会跟随子页高亮。
- 注意事项芯片（最多 4 个 + "+N more"）：kill switch、授权过期、agent 错误、cron 失败 → 红；实时额度、数据源陈旧、授权将到期、账户快照陈旧、磁盘 / 内存 → 琥珀；什么都没有时显示"All clear"。

## 6. 每屏主视觉（全部来自真实数据）

| 屏 | 主视觉 | 数据来源 |
|---|---|---|
| Now | 权益柱 + agent 实时卡 + 研究管线 + 5h token 柱 + 系统刻度 + 24h 点阵 | 以下各项的组合，`data/now.py` |
| Paper | 账户权益：每个交易日最后一个真实快照一根柱，以首个观测为基线，缺失日保留为点 | 各 sleeve 的周期快照 + `account.json` 的并集（同一个共享账户），`paper.build_account_equity_history`；按纽约时间归日 |
| Agents | 运行中会话的实时卡（最近 4 次工具调用、最后一句话、运行中光标）+ 24h 模型调用点阵；Now 上没有运行中会话时显示最近一次会话（灰色、"last active"），而不是空面板 | `agents.build_live_session`；`data/activity.py` |
| Hypotheses | 管线分段条 + 图例（点击直达对应泳道并展开） | 泳道计数，`now.summarize_research` |
| Quota | 24h 每 10 分钟新鲜 token 柱，当前 5h 窗口点亮 | `data/activity.py`（与 quota 同口径：input + output + cache_creation，不含 cache read） |
| Health | 读数面板内嵌数据源 / cron 状态刻度与磁盘 / 内存容量条 | 既有 health 报告 |
| Lineage | 图放进凹陷显示屏，声明边发光，节点标签加描边光晕避免被边线穿过 | 既有 lineage 布局 |

**24h 活动场**（`data/activity.py`）：每 10 分钟一桶，统计所有主会话与子 agent 转录里的不重复模型调用（按 `message.id` 去重，同一调用多行时取最后一行的 usage）。转录是追加写，所以每个文件保存字节游标：首次最多读末尾 32 MiB，之后只读新增部分（本机实测冷启动 0.47s、增量 5ms），由 warm 线程每 60 秒刷新；首次读取若没覆盖整个窗口会标 `partial`。

## 7. 视觉系统（`static/css/cockpit.css` 顶部令牌）

- **材质**：面板 = 顶部 1px 亮边 + 发丝环 + 柔和投影 + 极淡自上而下渐变（深色）/ 白面 + 阴影（浅色）；显示屏 = 凹陷的深色井（内阴影），图表与实时流都放在井里。
- **光**：画布顶部一处强调色环境光（深 15% / 浅 9%）；LED、运行脉冲、最新权益柱、当前导航图标是仅有的发光体；桌面上面板有跟随指针的微光（面与边），只在精确指针设备上出现。
- **色**：沿用第三稿的蓝黑梯与状态色；强调色深色 `#8196ff` / 浅色 `#4f5eff`；涨跌用 ok / stale 两色（唯一饱和的一对）。
- **字**：Geist / Geist Mono；主数字 56px（手机 44px）比例数字、-0.05em；次数字 40px；元信息 10.5px 等宽大写 +0.06em。
- **读数面板**：原来四张分离的数字卡改为一块面板内分格（发丝分隔），同一套模板在所有屏自动升级。
- **动效**：面板错峰上浮；权益柱从基线生长（14 根，transform）；点阵与 token 柱整体扫入（单元素 clip-path，**不再**对 144 个点各自做动画——实测在软件渲染下明显掉帧）；运行中光标闪烁、"now" 列呼吸；注意事项红点缓慢闪烁。全部在 `prefers-reduced-motion` 下停止。
- **提示**：所有图形标记都有 `data-tip`，脚本用一个浮层显示（`textContent` 写入），桌面悬停、手机轻点。

## 8. 流畅度

- 屏内切换保持第三稿机制（预取 + 原位替换 + View Transition），扩展到 7 屏；新增"屏 + 锚点"链接（如图例 → `/hypotheses#refuted`）在原位切换后展开对应泳道。
- 数据新鲜度汇总改为 60s 缓存：原先每个页面请求都重扫一次 parquet 页脚（本机约 0.5s），这是切屏最大的单项开销；`/health` 页本身仍然实时扫描。
- 预览实测（热缓存）：`/` 0.25s，其余各屏 0.08–0.25s。

## 9. 验证

- 渲染检查：7 屏 × 桌面深色 / 浅色 × 手机深色截图，逐屏批评并修正。入库的定稿截图在 `docs/cockpit-screens/v4/`：`now-desktop-{dark,light}`、`now-phone-dark`、`now-agents-resting`（无运行会话时的灰卡）、`{paper,agents}-{desktop,phone}-dark`、`{quota,hypotheses,health,lineage}-desktop-dark`（256 色量化以控制体积）。最后一轮批评修掉的：Now 权益面板在 Agents 面板更高时底部留白（图改为填满行高）、手机上 y 轴标签贴边、Agents 面板的错误 / 限额作业行各最多 3 条。
- 交互检查（无头 Chromium）：悬停提示、侧栏原位切换（页面不重载）、⌘7 / Ctrl+1、图例锚点跳转并展开泳道、实时卡打开检视器并接上 SSE，控制台无错误。
- 测试：`tests/test_cockpit_now.py`（活动场去重 / 增量 / 子 agent / 窗口外文件、权益按交易日归日与缺口、图形几何、注意事项排序、实时卡与"last active"灰卡、Now 路由空状态）。

## 10. 没做的与已知限制

- React 版 `/v2/` 未改动；本稿只改服务端渲染的 A 版。
- 活动场只统计 Claude 转录；Codex 会话不计入（当前不在用）。
- 会话标题来自 Paseo 记录的首条用户消息，可能与会话当前在做的事不一致；实时卡用"最后一句话 + 最近工具调用"补足。
- 冷启动后第一个请求要等 warm 线程首轮（本机 5–20s，视机器负载），之后走缓存。
