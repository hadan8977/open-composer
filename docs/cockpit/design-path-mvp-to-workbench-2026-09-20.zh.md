# 从功能 MVP 到有设计的工作台：怎么走 — 2026-09-20

> 机主 2026-09-20 看过截图后的判断：现在这版只能算功能 MVP，字多、格式糙、没有设计感；要的是最新一代苹果设计语言、交互像原生、高效简洁直接的工作台。
> 时间前提：今天是 2026-09-20。WWDC 2027 还没发生；能对标的最新一代是 WWDC 2025 引入、WWDC 2026（iOS 27 / macOS 27 Golden Gate）修订的 Liquid Glass 与配套 HIG。下文不编造 2027 的内容。

## 1. 苹果这一代设计语言里，对一个数据密集型工作台真正有约束力的几条

来源：Apple「Meet Liquid Glass」（WWDC25）、Liquid Glass 技术总览、MacRumors / Cult of Mac 对 WWDC 2026 变化的报道（链接见文末）。

| 规则 | 对我们意味着什么 |
|---|---|
| **两层结构**：内容层（不透明）与控制层（玻璃）。玻璃属于导航、工具栏、标签栏、侧栏、检视器这些"浮在内容上"的东西；内容本身用普通背景 | 表格、卡片、图表**永远不透明**；只有外壳用玻璃 |
| **不许玻璃叠玻璃**；"多数内容用普通背景、标准材质、颜色或留白就能建立层级" | 我们现在"面板里套面板"的做法要拆掉 |
| WWDC 2026 的修订方向：**默认透明度降低**、新增透明度滑杆、玻璃边缘加深、高光更亮、对背后复杂内容的扩散更强，以提升可读性 | 玻璃是克制的、可关的；可读性优先于效果，`prefers-reduced-transparency` 必须尊重 |
| **同心圆角**：内层圆角 = 外层圆角 − 内边距，与硬件圆角呼应 | 容器 16–20，内部元素 10–12，不是到处一个 2px（那是终端味，也不是苹果味） |
| 控件**按内容和上下文自适应**：标签栏滚动时收缩、工具栏合并相关动作、组件在不同窗口尺寸下变形而不是缩放 | 手机是浮动标签栏 + Sheet；桌面是侧栏 + 内容 + 检视器；不是同一套布局等比缩放 |
| 材质与动效**只为功能服务**：表达深度、反馈、上下文变化，不做装饰 | 动效只有三种：标签栏收缩、检视器滑入、实时行淡入。没有数字滚动、没有渐变呼吸 |
| 文字：SF Pro 的文本样式阶梯（Large Title → Caption 2）、动态字号；数字用 SF Mono 或**等宽数字**（tabular figures） | 数字承担视觉重量，标签退到次级颜色；不再全大写小字标签 |
| 颜色：系统语义色（label / secondaryLabel / tertiary；systemGreen / Orange / Red / Gray）+ 一个应用 tint | 我们的 `ok / warn / stale / unknown` 直接映射到四个系统色；tint 只用于选中和链接 |

## 2. 现在这版差在哪（对照截图）

不是配色问题，是**结构**问题：

1. 没有"层"。整页是一个平面上排着的面板，面板里再套面板，每个面板一个大标题、一段说明文字。苹果的做法是：一个工具栏标题、一条主指标带、一张列表/表格，细节在检视器或 Sheet 里。
2. 没有"进阶披露"。kill switch 的整段原因、四条 join 警告、卡片正文——全在第一屏。应该是：一行摘要 → 点开检视器 → 再点开原始内容。
3. 字是主角，数字不是。看板每行 4 个字段全是文字；额度页数字被标签包围。Stocks / Activity 的做法是数字大、标签小灰、变化量带色。
4. 桌面和手机是同一套布局等比缩放（手机上每张卡变成 4 行键值表）。应该是两种壳。
5. 时间戳是机器格式（微秒 ISO）。应该是相对时间（`2m ago`）+ 悬停绝对值。

## 3. 目标形态（一句话一屏）

**壳**：macOS / iPad = 侧栏（玻璃）+ 内容 + 右侧检视器（点一行不跳页）；iPhone = 浮动标签栏（Hypotheses · Agents · Paper · Quota · More）+ 下滑 Sheet 看详情。搜索框即时过滤当前列表。快捷键：⌘1–6 切屏、⌘F 过滤、↑↓ 选行、空格预览、Esc 关检视器。

**顶部状态带**（所有屏，单行，不是现在的两行文字）：Claude 5h / 7d 两条细进度条（或一个可点击的原因芯片）· 新鲜 token 估算 · 每个活着的 agent 一个圆点 · 数据新鲜度圆点 · 最近一次授权到期倒计时。

| 屏 | 主指标带（顶部 3–4 个大数字） | 主体 | 检视器 / Sheet |
|---|---|---|---|
| Hypotheses | running · shipped · refuted · unclassified 计数 | 泳道式列表，每行：id · 标题 · 状态点 · 结果数字（有则显示） | 卡片正文；criteria vs result 并排；安慰剂直方图 + 真值线；试验预算条；血统邻居 |
| Lineage | 声明边 · 提及边 · 根数 | 桌面：仅画有边的连通分量，孤立节点成列；手机：缩进列表 | 同 Hypotheses 的卡片检视器 |
| Agents | running · idle · error · 今日新鲜 token | 每 agent 一行：provider · 模型 · 状态 · 时长 · 当前文件 · 最近一行思考 | 实时时间线（时间 · 工具 · 目标 · 耗时 · 结果），自动滚动；重活区 |
| Paper | 账户净值 · 今日盈亏 · 开放订单 · 最近到期 | 每策略一行：名 · 授权芯片 · 到期天数 · 上次周期 · 成交率 · 最近订单 | 授权块；目标 vs 实际；订单；成交与滑点；净值柱（有历史才画） |
| Quota | 5h 新鲜 · 7d 新鲜 · 上次撞线量 · 缓存读 | 按角色/模型的表；子代理任务表按新鲜降序 | 凭证来源表；限流事件；缓存与熔断状态 |
| Health | 过期数据源 · 失败 cron · 磁盘 · 内存 | cron 表；数据源表；错误尾部 | 单条日志尾部 |

**文字规则不变**（计划第 3.5 节）：名词不用句子；每个可能过期的值带时间；空即 `None` / `No data yet`。

## 4. 实现路径（三条，附我的推荐）

| 路径 | 能到多像原生 | 代价 | 备注 |
|---|---|---|---|
| **A. 保持服务端渲染，换一套设计系统 CSS** | 80%：SF 字体栈、语义色变量（自动明暗）、`backdrop-filter` 只用于外壳并尊重 reduce-transparency、`font-variant-numeric: tabular-nums`、容器查询做两种壳、HTMX 加载检视器、SSE 实时行 | 最低；不引入 node；现有 JSON 数据层不动 | 拿 Figma Make v2 的产出当参考稿逐屏对齐 |
| B. 同一 JSON API + 用 Figma Make 的代码产出做前端 | 90% | 需要构建步骤（我们刚为了内存和依赖把 node 删了；可在别处构建后提交静态产物） | 适合 A 做完后仍不满意的局部 |
| C. SwiftUI 原生 App（iPhone + Mac）读同一 JSON API | 100%：真正的 Liquid Glass、原生标签栏/侧栏/检视器、动态字号、Live Activity | 最高：要 Mac + Xcode + TestFlight 分发 | 唯一能"像苹果原生"的路；API 契约保持干净就随时可走 |

**推荐**：先走 A（把接下来的 T5c 从"界面修正"升级成"设计系统 pass"），API 契约保持干净，Figma Make v2 的稿子既当 A 的参考也当 C 的起点。判断标准：A 做完后你在手机上打开，第一眼是数字不是文字、一屏能回答一个问题、不用滚动就看到状态带——达到就够；达不到再谈 C。

## 5. 顺序

1. T6c（进行中）→ T7 agent 实时流 → T8 手机壳 + Cloudflare 上线（先让你能在手机上打开）。
2. 你拿到 Figma Make v2 的稿子后，我做**设计系统 pass**：字体阶梯、语义色、同心圆角、两种壳、检视器、主指标带、相对时间、删说明文字。
3. 之后按屏对齐 Figma 稿，保留它更好的想法，丢掉它编出来的数据。

## 来源

- [Meet Liquid Glass — WWDC25](https://developer.apple.com/videos/play/wwdc2025/219/)
- [Liquid Glass — Apple Developer Documentation](https://developer.apple.com/documentation/technologyoverviews/liquid-glass)
- [Here's How Liquid Glass Is Changing in iOS 27 — MacRumors](https://www.macrumors.com/2026/06/10/how-liquid-glass-is-changing-in-ios-27/)
- [5 biggest Liquid Glass changes in iOS 27 and macOS 27 — Cult of Mac](https://www.cultofmac.com/news/liquid-glass-changes-ios-27-macos-27)
- [Apple finally brings the slider for Liquid Glass — Neowin](https://www.neowin.net/news/apple-finally-brings-the-slider-for-liquid-glass-and-many-other-changes/)
- [Liquid Glass: Hierarchy, Harmony and Consistency — Create with Swift](https://www.createwithswift.com/liquid-glass-redefining-design-through-hierarchy-harmony-and-consistency/)
- [Liquid Glass Design: Best Practices — Bitrig](https://bitrig.com/blog/liquid-glass-best-practices)
