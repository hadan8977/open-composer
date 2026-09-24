# Open Composer 本地部署指南

**目标读者**: 第一次在本地跑 Open Composer 的人 (你 / Codex / Claude Code)
**适用模式**: 单机开发 / 试用 / 离线研究
**远程模式**: 只读 Cockpit + Cloudflare Access + Paseo 会话，见 [docs/plan-step-18-readonly-cockpit-2026-09-19.zh.md](./plan-step-18-readonly-cockpit-2026-09-19.zh.md)
**最后验证**: 2026-09-24 (Linux，对齐 `scripts/setup-local.sh`/`.ps1` 当前实现)

> 2026-09-24 更正：这份文档原来讲的是 Step 18（2026-09-19）之前的旧前端 `dashboard/`（npm + Vite），
> 那个目录已经删除，仓库改用只读 Cockpit（`open_composer/cockpit` 服务端渲染 + 可选的
> `frontend/cockpit-v2` React 前端，用 pnpm 不是 npm）。下面按当前的 `scripts/setup-local.sh`
> （6 步，非旧版的 10 步）重写。

---

## 一键入口 (推荐)

Linux / macOS 用户可以直接运行：

```bash
make start
```

它会调用 `scripts/setup-local.sh`，完成依赖安装、仓库检查、`.env` 初始化和 Cockpit catalog 构建。

Windows PowerShell 用户使用：

```powershell
.\scripts\setup-local.ps1
```

## 一键脚本

| 系统 | 命令 |
|---|---|
| Windows PowerShell | `.\scripts\setup-local.ps1` |
| Linux / macOS | `./scripts/setup-local.sh` (加 `--dry-run` 只预览不执行) |

脚本按顺序跑 **6 步** 并显示 `[N/6] <title> OK/WARN/FAIL/SKIP`，**到第一个真失败处停下并告诉你下一步该做什么**。可以反复重跑——已完成的步骤会跳过。

跑完后:
- ✅ Cockpit catalog 已生成 (`reports/dashboard/catalog.json`，字段名是历史遗留，内容是 Cockpit 的 read model)
- ⚠️ 显示哪些可选 API key 还没配,按 §3 写入 `.env`
- ⚠️ 显示哪些 capability 用的 fixture 数据 (没配 key 时正常)

---

## 0. 前置工具

| 工具 | 最低版本 | 装法 (Windows) | 装法 (Linux/Mac) | 是否必需 |
|---|---|---|---|---|
| **uv** (Python 包管理) | 0.11+ | `winget install astral-sh.uv` 或 PS: `powershell -c "irm https://astral.sh/uv/install.ps1 | iex"` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` | 必需 |
| **Git** | 2.30+ | 已有 | 已有 | 必需 |
| **Node + pnpm** | Node 20+ | https://nodejs.org/ LTS，`corepack enable` | `nvm install --lts && corepack enable` | 仅构建可选的 `frontend/cockpit-v2` 前端时需要 |

uv 自带 Python 3.13,**不需要单独装 Python**。默认的只读 Cockpit（`/` 路由）是服务端渲染的
FastAPI + Jinja2，**不需要 Node**；Node/pnpm 只在你想构建 `/v2/` 的 React 前端时才要装。

---

## 1. 手动步骤 (对齐 `scripts/setup-local.sh` 的 6 步)

每步给:**命令 / 预期输出 / 失败时怎么办**。

### Step 1: 验证工具链

```bash
uv --version       # 期望: uv 0.11.x 或更高
```

❌ not found → 回到 §0 安装。

### Step 2: 安装 Python 依赖

```bash
uv sync --extra workbench
```

**预期**: 首次约 5-10 分钟,后续秒级，`.venv/` 在仓库根创建。

❌ 失败常见原因:
- 网络问题 → 设置 `UV_INDEX_URL` 用国内镜像
- Windows 上 `Failed to hardlink` 警告 → **不影响**,可忽略;或加 `export UV_LINK_MODE=copy`

### Step 3: 检查仓库一致性

```bash
uv run oc repo check
```

**预期**: 末行 `status=ok ready=yes`。

❌ `status=blocked` → 看 `reports/repo/repo-check.md` 的 `Next action` 列；文档相关的
blocked 通常是 `docs_inventory`，把新文档加进 `open_composer/repo_check.py:CURRENT_DOCS`
或删/移走多余文档。

### Step 4: 配置 .env (可选但建议)

```bash
cp .env.example .env       # Linux/Mac
copy .env.example .env     # Windows
```

首次运行 `setup-local.sh` 会在没有 `.env` 时自动从 `.env.example` 复制一份占位文件。
然后按 §3 表格填 key。**不配也可以跑**,只是部分 capability 走 fixture 数据。

❌ 安全提示:`.env` 已被 `.gitignore`,**永远不要 commit**。VPS 上 `chmod 600 .env`。

### Step 5: 验证环境配置

```bash
uv run oc doctor --plain
```

**预期**: Python/包都 `ok`;API key 显示 `missing` 是正常的 (除非你配了)。

特别注意:
- `ALPACA_PAPER` 应该是 `true` (硬约束,实盘 out of scope)

### Step 6: 构建 Cockpit catalog (read model)

```bash
uv run oc cockpit index
```

**预期**: 表格列出 strategies / versions / signals / runs 等计数,末行 `Read model` 指到
`reports/dashboard/catalog.json`（路径名沿用旧称呼，内容已经是 Cockpit 的数据）。

这一步读取 `strategy_specs/`、`signal_logs/`、`reports/` 生成给 Cockpit 用的 JSON。

### （可选）启动本地只读 Cockpit

```bash
uv run oc cockpit serve --port 8770
```

**预期**: 服务只监听 `127.0.0.1:8770`（应用内**没有任何鉴权代码**，故意拒绝绑定
`0.0.0.0`/`::`/`*`；远程访问必须走 Cloudflare Access，见 §3.4）。浏览器打开
http://127.0.0.1:8770 看到六个只读屏幕。

### （可选）构建 Cockpit 前端 B（React/Vite，`/v2/`）

```bash
make cockpit-v2
```

等价于 `cd frontend/cockpit-v2 && pnpm install --frozen-lockfile && pnpm exec tsc --noEmit && pnpm exec vite build`。
产物落到 `open_composer/cockpit/static/v2/`，`oc cockpit serve` 检测到该目录后会在 `/v2/` 挂载它。
服务端本身从不跑 node；不构建也完全不影响 `/` 主界面。

---

## 2. 跑完后的状态

| 状态项 | 必须 ok | 可以 ⚠️ |
|---|---|---|
| `oc doctor` Python 包 | ✓ | |
| `oc repo check` | ✓ status=ok | |
| `oc cockpit index` | ✓ 生成成功 | strategies/signals=0 (新仓库) |
| `oc cockpit serve` (可选) | ✓ HTTP 200 | |
| API keys | | 全 missing 也能跑 (用 fixture) |
| Alpaca paper sync | | 缺 ALPACA_API_KEY_ID 则 Cockpit 的 Paper 屏显示 0 |

⚠️ 不阻塞本地跑,但限制功能 —— 见 §3 决定要不要加 key。

---

## 3. 环境变量配置 (.env)

按用途分组。所有 key **都是可选**——本地跑不需要,但开了对应 capability 会更真实。

### 3.1 LLM (review cards / 策略草稿)

| 变量 | 必需? | 用途 | 在哪拿 |
|---|---|---|---|
| `OPENAI_API_KEY` | 可选 | review_card 调 OpenAI | https://platform.openai.com/api-keys |
| `OPENAI_BASE_URL` | 可选 | 改用第三方 gateway / 自部署模型 | 自部署 / aigateway / `https://ai.input.im` 等 |
| `OPENAI_MODEL` | 可选 | 默认 review 模型 | 默认 `gpt-4.1-mini` |

**只有需要 LLM review/draft 时才需要**。`oc strategy draft --idea "..."` 不带 `--use-llm` 时不需要。

### 3.2 Alpaca Paper (模拟盘自动写入)

| 变量 | 必需? | 用途 | 在哪拿 |
|---|---|---|---|
| `ALPACA_API_KEY_ID` | 可选 | paper trading API | https://app.alpaca.markets/paper/dashboard/overview → 右上 "View API Keys" |
| `ALPACA_API_SECRET_KEY` | 可选 | 同上 | 同上 |
| `ALPACA_PAPER` | **强制** `true` | OC 硬约束:**永远 paper-only** | (无需改,默认 true) |
| `ALPACA_API_BASE_URL` | 可选 | 默认 `https://paper-api.alpaca.markets` | (无需改) |
| `ALPACA_DATA_FEED` | 可选 | 默认 `iex` (免费) 或 `sip` (订阅) | (无需改) |

**配了之后才能**:`paper.sync.account` / `paper.sync.orders` 命令、Cockpit Paper 屏真实数据。

### 3.3 News / Macro / 港股

| 变量 | 必需? | 用途 | 在哪拿 |
|---|---|---|---|
| `ALPHA_VANTAGE_API_KEY` | 可选 | 新闻情感 capability | https://www.alphavantage.co/support/#api-key |
| `FRED_API_KEY` | 可选 | 宏观数据 capability | https://fred.stlouisfed.org/docs/api/api_key.html |
| `LONGBRIDGE_APP_KEY` | 可选 | 港股数据 (Longbridge) | https://open.longportapp.com/account |
| `LONGBRIDGE_APP_SECRET` | 可选 | 同上 | 同上 |
| `LONGBRIDGE_ACCESS_TOKEN` | 可选 | live API key auth | 同上 |

**没配时**:对应 capability 走 fixture/示例数据,可正常跑回测、但数据不是实时的。

### 3.4 Cockpit 远程访问 (仅需要手机/远程查看时)

Cockpit 应用内**零鉴权代码**，只监听 `127.0.0.1:8770`；远程访问的推荐方式是
Cloudflare Tunnel（`cloudflared tunnel run --token-file` 起的 systemd 服务）+ Cloudflare
Access 在边缘做鉴权，公共主机名指向 `http://127.0.0.1:8770`。没有一键部署脚本，
Tunnel connector 和 Access 策略（team domain、AUD、允许邮箱）在 Cloudflare Zero Trust
控制台配置。完整背景和验收标准见
[docs/plan-step-18-readonly-cockpit-2026-09-19.zh.md](./plan-step-18-readonly-cockpit-2026-09-19.zh.md)。

Cockpit 本身不提供任何命令入口（只读）；需要远程发指令时走 Paseo 会话，不是 Cockpit。

### 3.5 通知

| 变量 | 必需? | 用途 | 在哪拿 |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | 可选 | Telegram 推送 | https://t.me/BotFather → `/newbot` |
| `TELEGRAM_CHAT_ID` | 可选 | 推送给谁 | 创建 bot 后,给它发任意消息,然后 `curl https://api.telegram.org/bot<TOKEN>/getUpdates` 看 `chat.id` |
| `SMTP_HOST` | 可选 | Email digest | (任何 SMTP server,如 smtp.gmail.com) |
| `SMTP_PORT` `SMTP_USER` `SMTP_PASS` `SMTP_FROM` `SMTP_TO` | 可选 | 同上 | |

详见 `config/notifications.yaml.example`。

---

## 4. 常见问题

### Q1: `uv sync` 在 Windows 上警告 `Failed to hardlink`
✅ **可忽略**。性能略低但功能正常。要消除警告可在 .env 加 `UV_LINK_MODE=copy`。

### Q2: `oc repo check` 报 `docs_inventory blocked` 但目录看着没问题
看 `reports/repo/repo-check.json` 的 `extra_docs` vs `allowed_docs`:
- 真的多了文档 → 把它加到 `open_composer/repo_check.py:CURRENT_DOCS`,或删/移走

### Q3: Cockpit 端口被占
```bash
uv run oc cockpit serve --port 8771
```

### Q4: 浏览器打开是白屏 / 没渲染 (`/v2/`)
按 F12 看 console:
- "Failed to fetch /api/..." → cockpit 服务没起或路径错
- 模块加载 404 → `make cockpit-v2` 是否跑了、`open_composer/cockpit/static/v2/` 是否存在
- `/` 主界面（服务端渲染）不会有这类问题，排查时先确认走的是 `/` 还是 `/v2/`

### Q5: `make verify` 不存在
Windows 没装 GNU Make。两种选项:
1. 装 `choco install make`
2. 直接跑等价命令: `uv run ruff check . && uv run pytest && uv run oc repo check && uv run oc cockpit index`

### Q6: pytest 失败
**与本地部署无关** 的常见情况:
- NautilusTrader native lib 相关测试
- Linux-only 的 VPS bootstrap 测试
- 依赖 Alpaca / Longbridge / OpenAI 凭证的测试

跑核心 smoke:
```bash
uv run pytest tests/test_repo_check.py tests/test_cockpit_api.py tests/test_notifications.py tests/test_cockpit_catalog.py -q
```

---

## 5. 下一步

跑完本地后可以做:

| 想做 | 命令 |
|---|---|
| 草拟一个策略 | `uv run oc strategy draft --idea "QQQ 15min breakout with volume filter"` |
| 跑一遍回测 | `uv run oc backtest strategy_specs/drafts/<strategy>.yaml` |
| 看 paper readiness | `uv run oc paper readiness <strategy>` |
| 配置远程 Cockpit | 见 [docs/plan-step-18-readonly-cockpit-2026-09-19.zh.md](./plan-step-18-readonly-cockpit-2026-09-19.zh.md) |
| 配 Telegram 通知 | `uv run oc notify test --dry-run` |

---

## 6. 一切顺利时长什么样

跑完 `setup-local.{ps1,sh}` 期望看到类似输出（6 步，形式为 `[N/6] <title>  <status>`）:

```
[ 1/6] uv toolchain                     OK   uv 0.11.14
[ 2/6] Python deps (.venv)               OK   .venv synced
[ 3/6] Repo consistency check            OK   all checks passed
[ 4/6] .env file                         OK   0 keys configured
[ 5/6] Doctor (env check)                WARN 3 ok / 5 missing (optional: ...)
[ 6/6] Cockpit catalog                   OK   0 strategies / 0 versions / 0 signals

----------------------------------------------------------------------
Open Composer is ready locally.

Warnings (non-blocking):
  - 5 optional keys missing - capabilities will use fixtures: ...

Next steps:
  - Configure env keys:  docs/setup-local.zh.md section 3
  - Try a strategy:      uv run oc strategy draft --idea "..."
----------------------------------------------------------------------
```
