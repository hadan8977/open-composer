# Open Composer 本地部署指南

**目标读者**: 第一次在本地跑 Open Composer 的人 (你 / Codex / Claude Code)
**适用模式**: 单机开发 / 试用 / 离线研究
**VPS 远程模式**: 见 [docs/remote-dashboard-deploy.zh.md](./remote-dashboard-deploy.zh.md)
**最后验证**: 2026-05-16 (Windows 11 / Python 3.13 / Node 24)

---

## 一键入口 (推荐)

Linux / macOS 用户可以直接运行：

```bash
make start
```

它会调用 `scripts/setup-local.sh`，完成依赖安装、仓库检查、`.env` 初始化、
Dashboard catalog/build 和本地 Dashboard 启动。

Windows PowerShell 用户使用：

```powershell
.\scripts\setup-local.ps1
```

## 一键脚本

| 系统 | 命令 |
|---|---|
| Windows PowerShell | `.\scripts\setup-local.ps1` |
| Linux / macOS | `./scripts/setup-local.sh` |

脚本会按顺序跑 10 步并显示 `[N/10] ✓/⚠/✗ <result>`,**到第一个真失败处停下并告诉你下一步该做什么**。可以反复重跑——已完成的步骤会跳过。

跑完后:
- ✅ Dashboard 在 http://127.0.0.1:8000 可访问
- ⚠️ 显示哪些可选 API key 还没配,按 §3 写入 `.env`
- ⚠️ 显示哪些 capability 用的 fixture 数据 (没配 key 时正常)

---

## 0. 前置工具

| 工具 | 最低版本 | 装法 (Windows) | 装法 (Linux/Mac) |
|---|---|---|---|
| **uv** (Python 包管理) | 0.11+ | `winget install astral-sh.uv` 或 PS: `powershell -c "irm https://astral.sh/uv/install.ps1 | iex"` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| **Node** | 20+ | https://nodejs.org/ LTS | `nvm install --lts` |
| **Git** | 2.30+ | 已有 | 已有 |

uv 自带 Python 3.13,**不需要单独装 Python**。

---

## 1. 手动步骤 (10 步)

每步给:**命令 / 预期输出 / 失败时怎么办**。

### Step 1: 验证工具链

```bash
uv --version       # 期望: uv 0.11.x 或更高
node --version     # 期望: v20.x 或更高
npm --version      # 期望: 10.x 或更高
```

❌ 任意一个 not found → 回到 §0 安装。

### Step 2: 安装 Python 依赖

```bash
uv sync
```

**预期**: `Resolved 54 packages` + `Installed N packages` (首次约 5-10 分钟,后续秒级)。

`.venv/` 应在仓库根创建。

❌ 失败常见原因:
- 网络问题 → 设置 `UV_INDEX_URL` 用国内镜像
- Windows 上 `Failed to hardlink` 警告 → **不影响**,可忽略;或加 `export UV_LINK_MODE=copy`

### Step 3: 安装 Dashboard 前端依赖

```bash
npm --prefix dashboard install
```

**预期**: `added N packages` (首次约 1-2 分钟)。

`dashboard/node_modules/` 应被创建。

### Step 4: 检查仓库一致性

```bash
uv run oc repo check
```

**预期**: 末行 `status=ok ready=yes`。

❌ `status=blocked`:
- `docs_inventory` blocked → 看 `extra_docs` vs `allowed_docs`,要么删多余文档要么把新文档加进 `open_composer/repo_check.py:CURRENT_DOCS`
- 其他 blocked → 看 `reports/repo/repo-check.md` 的 `Next action` 列

### Step 5: 配置 .env (可选但建议)

```bash
# 首次复制 example
cp .env.example .env       # Linux/Mac
copy .env.example .env     # Windows
```

然后按 §3 表格填 key。**不配也可以跑**,只是部分 capability 走 fixture 数据。

❌ 安全提示:`.env` 已被 `.gitignore`,**永远不要 commit**。VPS 上 `chmod 600 .env`。

### Step 6: 验证环境配置

```bash
uv run oc doctor
```

**预期**: Python/包都 `ok`;API key 显示 `missing` 是正常的 (除非你配了)。

特别注意:
- `ALPACA_PAPER` 应该是 `true` (硬约束,实盘 out of scope)

### Step 7: 评估 capability (可选)

```bash
uv run oc capability test
```

**预期**: 每个 capability 一行 `score >= min_score` 或 `using fixture`。

❌ 报错时:多半是某个外部 API 不通,看具体哪个 capability。

### Step 8: 构建 Dashboard catalog (read model)

```bash
uv run oc dashboard catalog
```

**预期**: 表格列出 strategies / versions / signals / runs 数,末行 `Read model` 指到 `reports/dashboard/catalog.json`。

这一步读取 `strategy_specs/`、`signal_logs/`、`reports/` 生成给前端用的 JSON。

### Step 9: 构建 Dashboard 前端

```bash
uv run oc dashboard html       # 生成 reports/dashboard/index.html (静态版,无需 JS)
npm --prefix dashboard run build   # 构建 React + Vite 版,产出 dashboard/dist/
```

**预期**:
- HTML 文件:`reports/dashboard/index.html`
- Vite bundle:`dashboard/dist/assets/index-*.js` (~300 KB)、`index-*.css` (~30 KB)

### Step 10: 启动本地 Dashboard

```bash
uv run oc dashboard serve --port 8000
```

**预期**: `Serving dashboard at http://127.0.0.1:8000` (不退出,Ctrl+C 停)。

浏览器打开 http://127.0.0.1:8000 应看到完整 UI。

验证端点:
```bash
curl http://127.0.0.1:8000/api/dashboard/health
# 期望: {"status":"ok","dashboard_root":"<POSIX path>","auth_required":false}
```

---

## 2. 跑完后的状态

| 状态项 | 必须 ok | 可以 ⚠️ |
|---|---|---|
| `oc doctor` Python 包 | ✓ | |
| `oc repo check` | ✓ status=ok | |
| `oc dashboard catalog` | ✓ 生成成功 | strategies/signals=0 (新仓库) |
| `oc dashboard serve` | ✓ HTTP 200 | |
| API keys | | 全 missing 也能跑 (用 fixture) |
| Alpaca paper sync | | 缺 ALPACA_API_KEY_ID 则 dashboard Paper tab 显示 0 |

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

**配了之后才能**:`paper.sync.account / paper.sync.orders` 命令、Paper tab 真实数据。

### 3.3 News / Macro / 港股

| 变量 | 必需? | 用途 | 在哪拿 |
|---|---|---|---|
| `ALPHA_VANTAGE_API_KEY` | 可选 | 新闻情感 capability | https://www.alphavantage.co/support/#api-key |
| `FRED_API_KEY` | 可选 | 宏观数据 capability | https://fred.stlouisfed.org/docs/api/api_key.html |
| `LONGBRIDGE_APP_KEY` | 可选 | 港股数据 (Longbridge) | https://open.longportapp.com/account |
| `LONGBRIDGE_APP_SECRET` | 可选 | 同上 | 同上 |
| `LONGBRIDGE_ACCESS_TOKEN` | 可选 | live API key auth | 同上 |

**没配时**:对应 capability 走 fixture/示例数据,可正常跑回测、但数据不是实时的。

### 3.4 Dashboard 远程鉴权 (仅 VPS 模式)

| 变量 | 必需? | 用途 |
|---|---|---|
| `OPEN_COMPOSER_DASHBOARD_TOKEN` | 可选 | 本地 dashboard API token (本地默认不需要) |
| `OC_REMOTE_SHARED_SECRET` | 仅 VPS | Vercel BFF ↔ VPS daemon HMAC |
| `OC_DASHBOARD_PASSWORD_HASH` | 仅 VPS | Dashboard 登录密码 hash |
| `OC_DASHBOARD_SESSION_SECRET` | 仅 VPS | session cookie 签名 |
| `OC_DASHBOARD_ALLOWED_ORIGIN` | 仅 VPS | CORS allowed origin |
| `OC_DASHBOARD_OWNER` | 仅 VPS | 显示用户名 |

VPS 模式用 `oc remote bootstrap-vps --apply --generate-password` 自动生成,见 [docs/remote-dashboard-deploy.zh.md](./remote-dashboard-deploy.zh.md)。

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
- 大小写或路径分隔符不一致 → 已修 (commit `<hotfix>` 之后),拉最新即可
- 真的多了文档 → 把它加到 `open_composer/repo_check.py:CURRENT_DOCS`,或删/移走

### Q3: Dashboard 端口被占
```bash
uv run oc dashboard serve --port 8001
```

### Q4: 浏览器打开是白屏 / 没渲染
按 F12 看 console:
- "Failed to fetch /api/dashboard/catalog" → daemon 没起或路径错
- 模块加载 404 → `npm --prefix dashboard run build` 是否跑了
- 401 → 本地不该有 token,删 `OPEN_COMPOSER_DASHBOARD_TOKEN` 或 localStorage

### Q5: `make verify` 不存在
Windows 没装 GNU Make。两种选项:
1. 装 `choco install make`
2. 直接跑等价命令: `uv run ruff check . && uv run pytest && uv run oc repo check && uv run oc dashboard catalog`

### Q6: pytest 失败
**与本地 dashboard 部署无关** 的常见情况:
- NautilusTrader native lib 相关测试
- Linux-only 的 VPS bootstrap 测试
- 依赖 Alpaca / Longbridge / OpenAI 凭证的测试

跑核心 smoke:
```bash
uv run pytest tests/test_repo_check.py tests/test_dashboard_server.py tests/test_notifications.py tests/test_dashboard_catalog.py -q
```

---

## 5. 下一步

跑完本地后可以做:

| 想做 | 命令 |
|---|---|
| 草拟一个策略 | `uv run oc strategy draft --idea "QQQ 15min breakout with volume filter"` |
| 跑一遍样本回测 | `uv run oc backtest strategy_specs/drafts/qqq_pullback_15m.yaml` |
| 看 paper readiness | `uv run oc paper readiness qqq_pullback_15m` |
| 部署到 VPS | 见 [docs/remote-dashboard-deploy.zh.md](./remote-dashboard-deploy.zh.md) |
| 配 Telegram 通知 | `uv run oc notify test --dry-run` |

---

## 6. 一切顺利时长什么样

跑完 `setup-local.{ps1,sh}` 期望看到:

```
[1/10] ✓ uv 0.11.14
[2/10] ✓ node v24.11.0 / npm 11.6.1
[3/10] ✓ Python deps in sync (54 packages)
[4/10] ✓ Dashboard node deps installed (1615 modules)
[5/10] ✓ Repo consistency: ok
[6/10] ⚠ .env: 0/4 Alpaca keys, 0/2 LLM keys, 0/2 macro/news keys (optional)
[7/10] ⚠ Capability test: 3 ok / 5 using fixture
[8/10] ✓ Dashboard catalog built: 3 strategies, 4 versions, 11 signals
[9/10] ✓ Dashboard frontend built: 303 KB JS / 28 KB CSS
[10/10] ✓ Dashboard serve: ready at http://127.0.0.1:8000

──────────────────────────────────────────────────────────────────
✓ Open Composer is ready locally.

Optional next steps:
  • Add API keys:   docs/setup-local.zh.md §3
  • Try a strategy: uv run oc strategy draft --idea "..."
  • Deploy to VPS:  docs/remote-dashboard-deploy.zh.md

Server PID: 12345  (kill with: Stop-Process -Id 12345 [PS] / kill 12345 [bash])
──────────────────────────────────────────────────────────────────
```
