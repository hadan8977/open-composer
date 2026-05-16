# Open Composer Dashboard 精简重构计划 (Codex 执行版)

**版本**: 2026-05-16 v1
**作者**: Open Composer 维护者审计 (基于 2026-05-16 维护者反馈与产品决策)
**执行者**: Codex / Claude Code
**前置阅读**: `AGENTS.md`、`CLAUDE.md`、`docs/codex-execution-plan-v2-dashboard-telegram-2026-05-16.zh.md` (v2)、`docs/quantml-paper-study-research-notes-2026-05-15.zh.md`

---

## 0. 给 Codex 的执行须知 (READ FIRST)

### 0.1 这份文档是什么

本文档是 **Open Composer Dashboard 的"精简重构"计划**,把现在的 9 个 tab 压缩为 3 个,并把"策略创建/迭代"工作流从 dashboard 完全剥离到 Codex/Claude Code 终端中。

### 0.2 与已有计划文档的关系

| 文档 | 状态 | 关系 |
|---|---|---|
| `docs/codex-execution-plan-2026-05-15.zh.md` (v1) | 已执行完毕 | 不冲突。本计划是 UI 层重构,与 v1 后端工作正交 |
| `docs/codex-execution-plan-v2-dashboard-telegram-2026-05-16.zh.md` (v2) | 进行中 (G1+G2) | **本计划部分取代 v2 G1**:v2 G1 是"在 9 tab 基础上修 bug",本计划是"把 9 tab 重构为 3 tab"。**本计划优先**——重构后 G1 列出的部分 bug 会自然消失或转化为新 tab 上的 bug。v2 G2 (Telegram 通知) 与本计划独立并行 |
| `docs/setup-standardization-plan-2026-05-16.zh.md` | 待执行 | 与本计划独立 |
| `docs/codex-execution-plan-v2-2026-05-16.zh.md` (v2 第一版,我提交但未合并) | 已被 v2 收敛版取代 | 忽略 |

### 0.3 维护者 2026-05-16 决策回放

| 问题 | 决策 |
|---|---|
| 删哪些 tab? | Versions, LLM, Groups, Audit (4 个全删) |
| Strategy channel toggle 形态? | **两个独立 toggle**:`paper_auto on/off` + `live_advisory on/off` (可同时开,双轨验证) |
| 使用场景? | **响应式 (双优先)** — 手机 + 桌面都要好用 |
| 推进节奏? | 合成一份具体详细计划交给 Codex |

### 0.4 核心产品哲学 (本次新写,要写进 AGENTS.md)

> **Dashboard 的职责是监控与生命周期管理,不是策略创作工具。**
> **策略的发现、设计、迭代、评估**在 Codex / Claude Code 终端中完成。
> **策略的启用、监控、应急控制、回顾**在 Dashboard 完成。

类比: GitHub.com vs VSCode。GitHub 看 PR/CI/release,VSCode 写代码。没人在 GitHub 上写代码。

---

## 1. 现状与目标对照

### 1.1 现有 9 tab (现状审计)

| # | Tab | 主要内容 | 真实交互 | 删除/保留/合并 |
|---|---|---|---|---|
| 1 | Overview | KPI 卡 + 最近版本 + active strategies + audit feed | 无 | **重新设计为 Monitor** |
| 2 | Strategies (Library) | 全策略列表 + **Draft strategy 输入框 + LLM 复选** | Draft 按钮 + 进入 Detail | **保留为 Strategies**,**删除 Draft 输入** |
| 3 | Strategy Detail | 单策略详情 + 6 个 lifecycle 按钮 | 全部 lifecycle 操作 | **保留**,改为 Strategies tab 内嵌抽屉,不再是独立页 |
| 4 | Versions | git-style 版本时间轴 | rollback (disabled) | **删除** — 用 `git log strategy_specs/` |
| 5 | Paper | 账户/持仓/订单/kill switch/8 个 paper 操作 | 全部 paper 操作 | **合并进 Monitor** (主要 panel) |
| 6 | Events | 事件流 | 无 | **合并进 Activity** |
| 7 | LLM | review card 浏览 | 无 | **删除** — review card 是工件,Codex 写完直接读 |
| 8 | Groups | 按 sector/group 分组 | 无 | **删除** — 改为 Strategies tab 的筛选器 |
| 9 | Audit | 审计日志浏览 | 无 | **合并进 Activity** |
| 10 | Notifications (Codex 刚加) | 通知配置 + 历史 | 测试发送 | **拆分**:配置进 Monitor 顶部,历史进 Activity |

### 1.2 重构后 3 tab (目标)

```
┌──────────────────────────────────────────────────────────────┐
│ Open Composer                              [👤 owner] [出]    │
├──────────────────────────────────────────────────────────────┤
│  📊 Monitor    🎯 Strategies    📜 Activity                  │
└──────────────────────────────────────────────────────────────┘
```

- **Monitor** (默认首页): "现在怎样? 有什么要我注意的?"
- **Strategies**: "我的策略库 / 谁开谁关"
- **Activity**: "上周/今天发生过什么?"

---

## 2. 详细 UI 规格

### 2.1 Tab 1: Monitor

#### 设计意图
**首页 = 紧急情况第一时间看到 + 当前 paper 状态一目了然 + 今日值得我关注的事**。

mobile 单列堆叠;桌面 grid 12 列。

#### 区域 (从上到下)

##### 2.1.1 紧急横幅 (Alert banner) — 只在有事时出现

红色横幅,显示**最高优先级的 unresolved 状态**:

| 触发条件 | 横幅文案 | 操作按钮 |
|---|---|---|
| `kill_switch.enabled == true` | `🚨 Kill switch 已启用 — 自 <time>` | `Clear` |
| `alpaca_sync.last_status == "failed"` 且超过 30 min | `⚠️ Alpaca sync 失败 — <minutes_ago> min 前` | `Retry sync` |
| 有 `is_live_candidate=true` 且无 attestation 的 signal 超过 30min | `🔔 有 N 个实盘候选待你确认下单` | `Jump to list` (滚到 §2.1.5) |
| daemon 与 catalog 失联 >15min | `⏸️ Catalog 过期 — 自 <time>` | `Refresh` |

无紧急情况时**不渲染**这个区域,不占垂直空间。

##### 2.1.2 Paper 账户 KPI (4 张卡片)

|  Equity  |  今日 P/L  |  开放订单  |  持仓数  |
|----------|-----------|-----------|----------|
| $50,123  | +$234 (0.47%) | 3 | 5 |

- 移动端: 2×2 网格
- 桌面: 1×4 横排
- 数据缺失 (没 Alpaca key) 时显示 "—" 并加灰色说明 "Add ALPACA_API_KEY_ID to enable"

##### 2.1.3 今日信号列表 (today's signals)

时间倒序,最近的在上,默认显示 today (00:00 UTC 起):

```
🟢 09:42  qqq_pullback_15m   BUY  QQQ  100 @ $476.20  paper_filled
🔴 09:15  mu_breakout_15m    SELL MU   50 @ $124.30   awaiting_my_live  [I executed this]
🟡 08:30  eth_meanrev_5m     BUY  ETH  0.5 @ $3220    paper_pending
```

每行点击展开:
- 信号详情 (rule_id, confidence, feature snapshot)
- 关联 spec_hash / signal_log 路径
- 如 `awaiting_my_live`: 显著 `I executed this` 按钮 → 走 G4 attestation 流程

筛选: 切换 `Today | Last 24h | This week`,默认 Today。

##### 2.1.4 持仓快照 (collapsed by default)

折叠 panel,点击展开,显示当前 paper 持仓表 (Sym/Qty/Avg/Mkt/uPnL)。

##### 2.1.5 通知历史 (合并自 Notifications tab)

最近 5 条 outbound 通知,带 channel icon (📲 Telegram / 📧 Email / 📝 log)。

底部 "View all" → 跳 Activity tab 筛 `notifications`。

##### 2.1.6 系统状态 (footer 状态条)

显示在页面底部 (固定 footer):

```
⚙️ daemon: ok  ·  📊 catalog: 30s ago  ·  🔄 next sync: 4 min  ·  Kill switch: clear  ·  v0.1.0
```

mobile 上简化为只显示 `daemon: ok  ·  catalog: 30s`。

#### 2.1.7 顶部按钮

- 🔄 **Refresh now** — 强制 `dashboard catalog` 重建 + paper sync + 拉最新 signal
- 🚨 **Enable Kill Switch** (red) / 🟢 **Clear** (green) — 走二次确认 phrase

### 2.2 Tab 2: Strategies

#### 设计意图
**一张表显示我所有的策略 + 谁开谁关 + 每行可展开做 lifecycle 操作**。

**不允许在此 tab 创建新策略** — UI 顶部加 hint 指向 CLI。

#### 区域

##### 2.2.1 顶部 banner

```
+----------------------------------------------------------------------+
| Strategies (3)                            🔍 [search]  [filter ▾]    |
| To create a new strategy: run                                        |
| `uv run oc strategy draft "..."` in your terminal (Codex/Claude).    |
+----------------------------------------------------------------------+
```

filter dropdown:
- Lifecycle: All / draft / approved / active / retired
- Group: All / momentum / mean-reversion / ... (从 spec.group 自动收集)
- Channel: Has paper_auto / Has live_advisory / None

##### 2.2.2 主表 — 每行一个策略

mobile 列: `Name / Channel state / Sharpe / 30d`
桌面列: `Name / Status / Sharpe / 30d / Paper auto / Live advisory / Updated`

```
| Name              | Status   | Sharpe | 30d    | Paper auto | Live advisory | Updated     |
|-------------------|----------|--------|--------|------------|---------------|-------------|
| qqq_pullback_15m  | active   | 1.34   | +2.1%  | ✅ on       | ⬜ off         | 2 days ago  |
| mu_breakout_15m   | approved | 0.92   | -0.4%  | ⬜ off      | ⬜ off         | 5 days ago  |
| eth_meanrev_5m    | draft    | —      | —      | (disabled) | (disabled)    | yesterday   |
```

toggle 行为:
- 点击 toggle → 弹 modal 二次确认 (沿用现有 `promptDashboardConfirmations`,但改用 React Dialog 而非 `window.prompt`)
- modal 显示 channel 切换的后果:
  - turning paper_auto ON: "OC 会开始自动 paper 下单。需要 paper_readiness=ok。Continue?"
  - turning live_advisory ON: "OC 不会下单。每个新信号会通过 Telegram/Email 推给你 + 显示在 Monitor。Continue?"
- 走 dashboard command plan/run (`strategy.set_channel`) — 见 §3.2
- toggle 期间显示 spinner;失败显示具体原因 (如 "paper_readiness blocked: ALPACA_API_KEY_ID missing")

draft 策略两个 toggle 都 disabled,提示 "Validate + Approve first"。

##### 2.2.3 行展开抽屉 (drawer,在 tab 内,不跳页)

点击行 → 在该行下方插入抽屉:

- **左半**: 策略基本信息
  - spec 路径 (点击复制) — "Open in your editor for changes"
  - 描述、universe、timeframe、关键参数
  - 5 个最近信号 (mini list)

- **右半**: lifecycle 控制
  - 4 个按钮: `Validate` / `Approve` / `Disable` / `Retire`
  - 每个按钮带 description tooltip
  - 当前 lifecycle 用 badge 标出

- **底部**: paper readiness 状态
  - 6 项 readiness check 的 PASS/FAIL/BLOCKED 列表
  - 任意 fail/blocked 的 check 显示 `Why?` 链接 → 展开看 detail

#### 2.2.4 删除/迁移说明

- 原 Strategy Detail 独立页 → 改为本 tab 抽屉
- 原 Library 顶部 Draft 输入框 → 删除,改为顶部 hint 文案
- 原 Groups tab → 改为本 tab 的 filter dropdown

### 2.3 Tab 3: Activity

#### 设计意图
**时间轴回放,合并了原 Events + Audit + LLM card history + Notifications history**。

#### 区域

##### 2.3.1 顶部 filter bar

```
+-----------------------------------------------------------+
| 📅 [today ▾]  🏷️ [all events ▾]  🔍 [search]   [export ⬇] |
+-----------------------------------------------------------+
```

时间范围: today / yesterday / last 7d / last 30d / custom

事件类型 (multi-select):
- 📊 signals
- 💵 paper orders
- 🎯 live attestations
- 🚨 kill switch events
- 🔄 regime changes
- 🤖 LLM reviews
- 📲 notifications sent
- 📝 audit events
- ⚠️ system alerts

##### 2.3.2 主时间轴

```
2026-05-16 Thu
├ 14:32 📲 notification: kill_switch enabled (telegram, email)
├ 14:32 🚨 kill switch: enabled by owner reason="bad print volume"
├ 13:45 💵 paper order: BUY 100 QQQ @ $476.20 filled (strategy: qqq_pullback_15m)
├ 13:42 📊 signal: qqq_pullback_15m BUY QQQ
├ 11:15 🎯 live attestation: BUY 50 MU @ $124.30 (strategy: mu_breakout_15m)
└ 09:00 🤖 LLM review: qqq_pullback_15m → 70% confidence

2026-05-15 Wed
├ ...
```

每条事件可展开看完整 JSON metadata。

##### 2.3.3 导出

- Export CSV (按筛选范围)
- Export JSONL
- 每条事件提供 "Open file" 链接 (复制对应 jsonl 文件路径,供 Codex 中 cat)

### 2.4 响应式设计规范

> 维护者明确:双优先 (手机 + 桌面)。

#### Tailwind breakpoint
- `sm` (≥640px): tablet 立直
- `md` (≥768px): tablet 横屏
- `lg` (≥1024px): laptop
- `xl` (≥1280px): desktop

#### 布局原则

| 区域 | mobile (< 768px) | desktop (≥ 1024px) |
|---|---|---|
| 导航 | 顶部水平 3 个 tab,icon + label | 顶部水平 3 个 tab,icon + label,更大字号 |
| Monitor KPI 卡 | 2×2 grid | 1×4 横排 |
| Monitor 信号列表 | 单列卡片,大点击区 | 表格行 |
| Strategies 表 | 折叠列:只显示 Name / Channel state / 30d | 全列 |
| Strategies 抽屉 | 全屏覆盖 (modal-like) | inline drawer (行下方) |
| Activity 时间轴 | 单列垂直 | 单列垂直 (已经是好布局) |
| Footer 状态条 | 简化:`daemon: ok · catalog: 30s` | 完整 |

#### 字号

| 元素 | mobile | desktop |
|---|---|---|
| Tab label | 14px | 14px |
| 主标题 | 20px (KPI 数值) | 32px |
| 表格行 | 14px | 14px |
| 时间戳 | 11px | 12px |

字号定义放进现有 design system (`dashboard/src/app/styles/` 或 Tailwind config),不在组件里 inline。

#### 触摸区
所有 toggle / button **最小 44×44 px** (Apple HIG 推荐),mobile 上 toggle 用 native-feel switch 组件 (Radix `<Switch>`)。

---

## 3. 实施阶段

### 3.1 阶段 D1 — Schema + Backend (3-5 days, 与 v2 G2 并行)

> 这一阶段不动 UI,只改 spec 和后端命令,**向后兼容**。

#### D1.1 — StrategySpec 加 `execution.live_advisory`

文件: `open_composer/models/strategy_spec.py`

```python
class ExecutionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # ... 已有字段 (mode 等) ...

    # NEW v3
    live_advisory: bool = False
    """If True, signals from this strategy generate `is_live_candidate=true`
    and trigger outbound notification (Telegram/Email).
    OC NEVER places live broker orders; maintainer must execute manually.
    """
```

**重要**: `paper_auto` 已存在 (作为 `execution.mode == "paper_auto"`)。`live_advisory` 是**正交**的新字段——一个 strategy 可以同时 `mode == "paper_auto"` 且 `live_advisory == True` (双轨验证,paper 自动 + 实盘建议)。

迁移: 加默认值 False,旧 spec 自动兼容。

#### D1.2 — Signal 模型加 `is_live_candidate` (沿用 v2 G4 计划)

```python
class Signal(BaseModel):
    # ... 已有字段 ...
    is_live_candidate: bool = False
    live_attestation: LiveAttestation | None = None
```

`LiveAttestation` 定义见 v2 G4。如 v2 已落 schema,本阶段确认即可。

#### D1.3 — Backend Dashboard 新命令

在 `open_composer/dashboard/commands.py` 加新 DashboardCommandAction:

```python
DashboardCommandAction = Literal[
    # ... 已有 ...
    "strategy.set_paper_auto",        # NEW: turn paper_auto on/off
    "strategy.set_live_advisory",     # NEW: turn live_advisory on/off
    "signal.attest_live",             # NEW: record live execution (v2 G4)
]
```

每个新 action 实现:
- plan 阶段:验证 strategy 存在 + paper_readiness check + 生成 confirmation phrase
- run 阶段:atomically 改 spec yaml 文件 (preserve formatting, see `open_composer/strategy_lifecycle.py` 的现有模式) + 写 audit
- backup manifest (yellow action):写 yaml diff 到 `reports/backups/`

confirmation phrase 示例:
- `CONFIRM PAPER AUTO ON: qqq_pullback_15m`
- `CONFIRM LIVE ADVISORY ON: qqq_pullback_15m`
- `CONFIRM LIVE ATTESTATION: signal-abc123`

#### D1.4 — Backend Catalog 增强

`open_composer/dashboard/catalog.py` 的 strategy 行加字段:

```python
class DashboardStrategy(BaseModel):
    # ... 已有 ...
    paper_auto_enabled: bool          # 派生自 execution.mode == "paper_auto"
    live_advisory_enabled: bool       # 派生自 execution.live_advisory
    paper_readiness_status: Literal["ok", "warning", "blocked", "unknown"]
    paper_readiness_blocking_count: int
```

#### D1.5 — 测试

- `tests/test_strategy_spec_v3_channels.py`:旧 spec 不带 live_advisory 也能 load,默认 False
- `tests/test_dashboard_commands.py` 加 `strategy.set_paper_auto` / `strategy.set_live_advisory` 的 plan + run 用例
- `tests/test_dashboard_catalog.py` 加新字段断言

#### D1 DoD

- [ ] `execution.live_advisory: bool = False` 落到 `models/strategy_spec.py`
- [ ] 旧 spec 无变化加载通过 (backward-compat 测试)
- [ ] 3 个新 dashboard action 实现 + 测试 + 走完二次确认链路
- [ ] catalog.json 新字段对所有现存 strategy 都正确生成
- [ ] `make verify` 全绿
- [ ] PR: `feat(channels): paper_auto + live_advisory dual-channel strategy spec + backend`

### 3.2 阶段 D2 — Frontend 重构 (5-7 days)

> 这一阶段做 UI,**完全替换** sidebar / sections / library / strategy-detail / overview。

#### D2.1 — 设计 token 准备

在 `dashboard/src/app/styles/` 加 design tokens (如果已有则修改):
- 字号 scale (mobile/desktop)
- spacing scale
- colors (semantic: success/warn/danger/info)
- touch target min 44px

#### D2.2 — 删除文件

```
dashboard/src/app/components/versions.tsx     -> 删除
dashboard/src/app/components/llm.tsx          -> 删除 (如果存在,在 sections.tsx 里的 export)
dashboard/src/app/components/groups.tsx       -> 删除 (同上)
dashboard/src/app/components/audit.tsx        -> 删除 (同上)
```

实际上现在 `sections.tsx` 把多个 panel 写在一个文件里,需要逐个删除 export 并清理 import。

#### D2.3 — 重写 Sidebar / NavKey

`dashboard/src/app/components/sidebar.tsx`:

```typescript
export type NavKey = "monitor" | "strategies" | "activity";

function navItems(): { key: NavKey; label: string; icon: any }[] {
  return [
    { key: "monitor",     label: "Monitor",    icon: Activity },
    { key: "strategies",  label: "Strategies", icon: Target },
    { key: "activity",    label: "Activity",   icon: ScrollText },
  ];
}
```

#### D2.4 — 新文件结构

```
dashboard/src/app/components/
  Monitor/
    Monitor.tsx              # 主入口
    AlertBanner.tsx          # §2.1.1
    PaperKpi.tsx             # §2.1.2
    TodaySignals.tsx         # §2.1.3
    PositionSnapshot.tsx     # §2.1.4
    NotificationFeed.tsx     # §2.1.5
    SystemStatusBar.tsx      # §2.1.6
  Strategies/
    Strategies.tsx           # 主入口
    StrategiesTable.tsx      # §2.2.2
    StrategyDrawer.tsx       # §2.2.3 (行展开)
    ChannelToggle.tsx        # 共享 paper_auto / live_advisory toggle
    ConfirmDialog.tsx        # Radix Dialog 替代 window.prompt
  Activity/
    Activity.tsx             # 主入口
    ActivityFilters.tsx      # §2.3.1
    ActivityTimeline.tsx     # §2.3.2
    EventCard.tsx            # 单条事件
  shared/
    KpiCard.tsx
    StatusBadge.tsx
    EmptyState.tsx
```

`sections.tsx` 删除 (37K 行清空)。`strategy-detail.tsx` 也删除 (40K 行,逻辑迁到 `StrategyDrawer.tsx`)。`library.tsx` 删除。`overview.tsx` 删除 (内容迁到 Monitor)。

#### D2.5 — App.tsx 重写

```tsx
export default function App() {
  useDashboardCatalogSync();
  const session = useDashboardSession();
  const [tab, setTab] = useState<NavKey>("monitor");

  if (session.loading) return <RemoteGate status="Checking session" />;
  if (session.remote && !session.authenticated) return <RemoteLogin ... />;

  return (
    <div className="min-h-screen flex flex-col">
      <TopBar tab={tab} onTabChange={setTab} owner={session.owner} onLogout={session.logout} />
      <main className="flex-1 overflow-auto">
        {tab === "monitor" && <Monitor />}
        {tab === "strategies" && <Strategies />}
        {tab === "activity" && <Activity />}
      </main>
    </div>
  );
}
```

TopBar 改为顶部水平 (mobile + desktop 一致),不再用左侧 Sidebar。3 个 tab 平铺更直观。

#### D2.6 — Confirmation Dialog 替换 window.prompt

文件: `dashboard/src/app/components/Strategies/ConfirmDialog.tsx`

```tsx
import * as Dialog from "@radix-ui/react-dialog";

export function ConfirmDialog({
  open, onOpenChange,
  title, body,
  phrase, doublePhrase,
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (b: boolean) => void;
  title: string;
  body: string;
  phrase: string;
  doublePhrase?: string;
  onConfirm: (confirm: string, doubleConfirm: string) => Promise<void>;
}) {
  const [input1, setInput1] = useState("");
  const [input2, setInput2] = useState("");
  const [busy, setBusy] = useState(false);
  // ... validate input1 === phrase, input2 === doublePhrase if present
  // ... show real-time feedback (input mismatch in red)
}
```

完全替代 `runtime.ts:promptDashboardConfirmations`:
- 移动端可用 (window.prompt 在 iOS Safari 会被拦)
- 可显示更多上下文 (要切换的策略名 / 后果说明)
- 双重确认在同一 modal,不弹两次

更新所有调用方:
- `Strategies/ChannelToggle.tsx`
- `Strategies/StrategyDrawer.tsx` (lifecycle 按钮)
- `Monitor/AlertBanner.tsx` (kill switch)
- `Monitor/TopBar.tsx` (refresh / kill switch)

#### D2.7 — 响应式 Tailwind classes

例:`Monitor/PaperKpi.tsx`

```tsx
<div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
  <KpiCard label="Equity" value="$50,123" />
  <KpiCard label="Today P/L" value="+$234" trend="up" />
  <KpiCard label="Orders" value="3" />
  <KpiCard label="Positions" value="5" />
</div>
```

`Strategies/StrategiesTable.tsx` 用 Tailwind `hidden md:table-cell` 控制列在 mobile 上隐藏。

#### D2.8 — 测试

- `dashboard/src/app/__tests__/Monitor.test.tsx`:渲染 + 空状态 + 紧急横幅 + KPI 数字
- `dashboard/src/app/__tests__/Strategies.test.tsx`:渲染表 + toggle 触发 confirm dialog + 抽屉打开
- `dashboard/src/app/__tests__/Activity.test.tsx`:渲染时间轴 + 筛选

测试框架:**保留现有的** (我没查到具体是 vitest 还是 jest,Codex 自行确认 `dashboard/package.json`)

#### D2 DoD

- [ ] 9 tab → 3 tab,删除 4 个文件、重写 5 个文件
- [ ] 所有原 lifecycle 操作可在新 Strategies tab 完成
- [ ] kill switch 在 Monitor tab 可操作
- [ ] mobile (Chrome devtools iPhone 14) 上单列布局可用,触摸区合规
- [ ] desktop (1440px) 上信息密度合适
- [ ] 用 Radix Dialog 替换所有 window.prompt
- [ ] catalog 字段缺失时显示有意义的 EmptyState,不白屏
- [ ] `npm run build` 体积应**小于现状** (旧 296 KB JS,目标 ≤ 250 KB,因为删了 ~50% UI 代码)
- [ ] PR: `feat(dashboard): slim to 3 tabs (Monitor / Strategies / Activity) + responsive`

### 3.3 阶段 D3 — 文档与文化更新 (1-2 days)

#### D3.1 — AGENTS.md 加哲学声明

在 `AGENTS.md` 加一段 (放在 "Dashboard" 章节顶部):

```markdown
## Dashboard 设计哲学

Dashboard 的职责是**监控与生命周期管理**,不是策略创作工具。

- **在 Codex / Claude Code 终端中做**: 策略的发现、设计、迭代、回测、评估、报告生成
- **在 Dashboard 中做**: 策略的启用/禁用、信号监控、应急控制 (kill switch)、回顾

任何对 dashboard UI 的扩展前,先问: "这件事用 CLI 做不是更顺手吗?" 如果答案是肯定的,**不要往 dashboard 加**。Dashboard 永远是 3 个 tab: Monitor / Strategies / Activity。
```

#### D3.2 — CLAUDE.md 同步

同样的声明加到 CLAUDE.md。

#### D3.3 — README.md 更新

在 "Dashboard" 章节顶部加:

```markdown
The dashboard is a monitor — not an authoring tool.
Create / edit strategies in your terminal with `uv run oc strategy draft "..."`.
Dashboard is for: today's signals, kill switch, channel toggles, history.
```

#### D3.4 — 删除/更新过时文档

| 文档 | 处理 |
|---|---|
| `docs/setup-local.zh.md` | 更新 Step 9-10 部分以匹配新 dashboard |
| `docs/remote-dashboard-deploy.zh.md` | 更新 (mention 3 tab) |
| `docs/codex-execution-plan-v2-dashboard-telegram-2026-05-16.zh.md` | 加 note: "G1 部分已被本计划吸收" |

#### D3.5 — `oc dashboard` CLI 命令文案更新

`oc dashboard serve --help` 输出加一行:

```
The dashboard is a monitor - create strategies via `oc strategy draft` in your terminal.
```

#### D3 DoD

- [ ] AGENTS.md / CLAUDE.md / README.md 三处声明同步
- [ ] 过时文档更新
- [ ] PR: `docs(dashboard): document monitor-only philosophy + slim 3-tab UX`

---

## 4. 与现有 v2 G1 的关系细节

### 4.1 v2 G1 中"应该修但本计划吃掉"的部分

| v2 G1 子任务 | 本计划处理 |
|---|---|
| G1.1 数据加载层修复 (catalog 加载失败) | 由 Monitor 的 EmptyState + catalog 刷新指示器接管。**不再修旧 Overview tab** |
| G1.2 按钮执行层修复 (window.prompt 拦截) | 由 D2.6 的 Radix Dialog 替换。完整解决 |
| G1.2 Library 无 enable/disable 入口 | 由 D2.4 的 Strategies/StrategiesTable + ChannelToggle 解决 |
| G1.3 ErrorBoundary / EmptyState polish | 由 D2.4 的 shared/EmptyState 解决 |

### 4.2 v2 G1 中"独立保留"的部分 (本计划不吃)

| v2 G1 子任务 | 状态 |
|---|---|
| G1.0 系统性 audit | 仍建议先跑,但 audit 结果只用于决定**新 3 tab 的 panel 优先级** |
| G1.1 根因 1 (catalog 缺失) - daemon 启动 ExecStartPre | 必须保留,新 UI 仍需 catalog |
| G1.1 根因 2 (缺 Alpaca key 提示) | 保留,新 Monitor 的 KPI 卡片显示 "Add ALPACA_API_KEY_ID" |
| G1.1 根因 3 (HMAC 401) | 保留 (基础设施) |
| G1.1 根因 4 (Linux 路径退化) | 保留 (回归测试) |

**建议**:Codex 看到本计划后,**先停 v2 G1 的 UI 修复部分**,先做 v2 G2 (通知系统) 和本计划 D1。D2 (UI 重构) 在 G2 完成后再做,因为 D2 需要 Notifications 在后端就绪。

### 4.3 与 v2 G2 (Telegram) 的并行

- D1 (schema + backend) ↔ v2 G2 (Telegram outbound):**完全并行**,无冲突
- D2 (UI 重构) ↔ v2 G2:**等 G2 完成后启动**,因为新 Monitor tab 要展示通知历史

---

## 5. Migration 与兼容性

### 5.1 数据迁移

无需迁移。新字段 `execution.live_advisory` 默认 False,旧 spec 加载即可。

### 5.2 用户认知迁移

- 第一次打开新 dashboard:顶部加一次性 banner "Dashboard 已重构 — 3 个 tab,strategy 创建移到 CLI。<dismiss>"
- 老的 URL hash (`#versions` 等) 自动重定向到 `#activity` (因为 versions 内容并入 activity)

### 5.3 备份

D2 PR 前在 release notes 注明:旧 dashboard 代码作为 `dashboard/legacy/` 保留 1 个版本周期 (1 month),之后真正删除。如果用户强烈反弹,可以快速 revert。

---

## 6. 验收清单 (整体)

### 6.1 功能验收 (从用户视角)

- [ ] 打开 dashboard 第一眼就在 Monitor,1 秒内看到当前 paper P&L 和今日信号
- [ ] kill switch 在 1 次点击 + 二次确认内可操作
- [ ] 在 Strategies 列表找到一个策略,2 次点击 (toggle + confirm) 可开关 paper_auto 或 live_advisory
- [ ] 在 mobile (375×667) 上每个 tab 都可滚动浏览,没横向滚动
- [ ] 切换 tab 不丢失正在编辑的 toggle state (Strategies 抽屉的开关半路打开时)
- [ ] 紧急横幅在 kill switch 启用 / Alpaca 失败 / 待 attestation 信号 / catalog 过期任一时显示

### 6.2 技术验收

- [ ] 删除 4 个旧 component 文件 (Versions/LLM/Groups/Audit) 总计 ~10K LoC
- [ ] 新增 ~3 个 Monitor / Strategies / Activity 主目录,总计 ~6K LoC
- [ ] `npm run build` 输出 ≤ 250 KB JS (现 296 KB)
- [ ] 全 dashboard 不再使用 `window.prompt`
- [ ] `make verify` 全绿
- [ ] 在 VPS 上 (remote mode) 行为与本地一致

### 6.3 文档验收

- [ ] AGENTS.md / CLAUDE.md / README.md 加 dashboard-is-monitor 声明
- [ ] `oc dashboard serve --help` 提到 "monitor only"
- [ ] `docs/setup-local.zh.md` Step 10 部分指向新 Monitor 首页

---

## 7. 不在范围 (避免偏移)

| 不做 | 理由 |
|---|---|
| 在 Strategies tab 加"创建新策略"按钮 | 违反 dashboard-as-monitor 哲学 |
| 在 dashboard 里写/编辑 spec YAML | 同上 |
| 在 dashboard 里 review LLM card | LLM card 是工件,Codex 写完直接读 |
| 在 dashboard 里跑 backtest | backtest 是长任务,走 `reports/agent_requests/` |
| 在 dashboard 里 group strategy (创建 group) | group 是 spec metadata,改 spec 即可 |
| 桌面端"工作站模式" (多列、多面板) | 维护者要求响应式但首要 mobile |
| 把 Audit tab 单独保留 | 维护者明确要删 |
| 在 Activity tab 加"重放" (re-execute event) | 危险操作,不在 dashboard 暴露 |
| 让 Telegram bot 接收回调来下单 | v2 已确立 I7: 通知单向 outbound |
| OC 调任何 live broker API | v2 已确立 I6: paper-only |

---

## 8. 提交节奏

按 D1 → D2 → D3 顺序提交,每阶段一个独立 PR:

1. `feat(channels): paper_auto + live_advisory dual-channel strategy spec + backend (D1)`
2. `feat(dashboard): slim to 3 tabs (Monitor/Strategies/Activity) + responsive (D2)`
3. `docs(dashboard): monitor-only philosophy + slim 3-tab UX (D3)`

每个 PR 跑完 `make verify` 再合,且每个 PR 必须更新对应章节的文档。

---

## 9. Codex 工作纪律增量 (基于 v1+v2 已有)

> 沿用 v1 §16 + v2 §16 的所有条目,新增以下 2 条:

14. **任何 Dashboard UI 扩展前,问"用 CLI 做不更顺手吗?"** 如果答案是肯定的,**不要往 dashboard 加**。Dashboard 永远是 3 个 tab。

15. **任何 strategy channel 切换**:必须经 `strategy.set_paper_auto` / `strategy.set_live_advisory` 命令链路 + 二次确认 + audit 写入,绝不允许直接编辑 spec yaml 文件。**唯一例外**:维护者自己在 Codex 终端中编辑 (那是 spec 作者层,不是 dashboard 层)。

---

## 附录 A: 旧 tab → 新位置映射 (便于 user 适应)

| 我想做 (旧 dashboard 用法) | 现在去哪 (新 dashboard) | 备选 (CLI) |
|---|---|---|
| 看今天 paper P&L | Monitor 顶部 | `cat reports/paper/status.json` |
| 看 paper 持仓 | Monitor 折叠 panel | `cat reports/paper/positions.json` |
| 开启 kill switch | Monitor 顶部 / 紧急横幅 | `uv run oc paper kill-switch enable --reason "..."` |
| 看版本时间轴 | (已删) | `git log strategy_specs/<name>.yaml` |
| 看 LLM review card | (已删) | `cat reports/reviews/<id>.json` |
| 按 group 筛选策略 | Strategies tab → filter dropdown | `oc strategy list --group <name>` |
| 看 audit log | Activity tab → filter `audit events` | `cat reports/audit/*.jsonl` |
| 创建新策略 | (移除) | `uv run oc strategy draft "..."` |
| 验证策略 | Strategies → 点击行 → 抽屉 → `Validate` | `uv run oc strategy validate <path>` |
| 启用 paper_auto | Strategies → 行尾 toggle | `uv run oc strategy activate-paper-auto <name>` |
| 启用 live_advisory | Strategies → 行尾 toggle (新) | `uv run oc strategy set-live-advisory <name> --on` (新 CLI) |
| 看通知历史 | Monitor 底部 / Activity | `cat reports/notifications/log.jsonl` |
| 编辑通知配置 | (CLI only,因为是 secret 敏感) | 编辑 `config/notifications.yaml` |

---

## 附录 B: 与论文研究的关系

本计划与 `docs/quantml-paper-study-research-notes-2026-05-15.zh.md` 中的论文关系:

| 论文洞察 | 本计划如何体现 |
|---|---|
| Reliable Evaluation: 工具维度评估 | dashboard-as-monitor 哲学就是工具维度的分工 |
| TrustTrade: 选择性共识 | live_advisory 强制人工 attestation,人是最后的共识层 |
| BlindTrade: 反事实验证 | (与 dashboard 无关,Codex 端做) |
| Acoustic Camouflage: 多模态不一定好 | 类比:多 tab 不一定好,9 → 3 是同样的精简思路 |

---

## 附录 C: 维护者 2026-05-16 决策原文回放

| 问题 | 选择 | 说明 |
|---|---|---|
| 删哪些 tab? | Versions / LLM / Groups / Audit (4 个全删) | 直接选择 |
| Channel toggle 形态? | 两个独立 toggle: paper_auto + live_advisory | "可同时开" = 双轨验证 |
| 使用场景? | 双优先 (响应式) | 手机 + 桌面都要好用 |
| 推进? | 合成一个计划文档,具体详细,交给 codex 执行 | 即本文档 |

---

*Plan v1, 2026-05-16. Self-contained for Codex/Claude Code execution. 完成 D1+D2+D3 后请把本节顶部「执行者」字段改为你的 model id + 完成日期。*
