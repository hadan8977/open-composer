# Open Composer 代码审计报告

**审计日期**: 2026-05-15
**仓库**: https://github.com/zhoucehuang-arch/open-composer
**部署位置**: `D:\hadan\finance\open-composer`
**版本**: `0.1.0` (commit at clone time)
**审计员**: Claude Code (Opus 4.7)
**环境**: Windows 11, Python 3.13.7 (uv 自举), Node 24.11, npm 11.6

---

## 1. 部署执行情况

| 步骤 | 结果 | 备注 |
|------|------|------|
| `git clone` | ✅ | 项目完整克隆 |
| 安装 `uv` (官方 PowerShell installer) | ✅ | uv 0.11.14 |
| `uv sync` | ✅ | 依赖装好，包含 nautilus-trader 1.219.0、alpaca-py、longbridge SDK 等 ~70 个包；`.venv` 内自动配 Python 3.13.7 |
| `cp .env.example .env` | ✅ | 仅占位，全部 API Key 留空 |
| `uv run oc doctor` | ✅ | 所有 Python 包就绪，可选 API Key 全显示 missing |
| `uv run oc capability test` | ✅ | 8 个 capability 全部 score=1.0 (基于 fixture 数据) |
| `uv run oc spec validate strategy_specs/drafts/qqq_pullback_15m.yaml` | ✅ | 策略规格通过 |
| `uv run oc backtest strategy_specs/drafts/qqq_pullback_15m.yaml` | ✅ | 端到端回测成功，return=1.01% |
| `uv run ruff check .` | ✅ | All checks passed (零 lint 警告) |
| `uv run pytest` | ⚠️ | **138/159 通过 (86.8%)**, 21 个 Windows 路径相关失败 (见 §4.1) |
| Dashboard build / serve | 未跑 | Vite + React 18 + Tailwind 4 + Radix UI + MUI 7,可在 Mac/Linux 上 `make dashboard-build` |

---

## 2. 项目概览

**Open Composer** 是个「文件优先 (file-first)」的 AI 量化策略工作台,专为 Codex 辅助的研究、回测、复盘、Dashboard 监控以及 Alpaca Paper(模拟盘)安全工作流而设计。

### 2.1 体量
- **Python**: 139 个文件 / ~32K LOC
- **TypeScript/TSX**: 65 个文件 (Dashboard 前端)
- **测试**: 36 个测试文件,159 个测试用例
- **能力适配器**: 8 个 (sample / alpaca / longbridge / sec_filings / fred / alpha_vantage / gdelt / memory_storage_sample)
- **CLI 命令组**: 22 个一级命令 (doctor / readiness / backtest / scan / spec / data / compile / paper / journal / capability / events / macro / context / strategy / run / options / feature / deploy / dashboard / repo / remote / agent / review-signal)

### 2.2 顶层目录
```
open_composer/         # Python 主包
├── adapters/          # broker(alpaca_paper) + data(alpaca/longbridge/sample) + events + execution
├── analytics/  capabilities/  compiler/  dashboard/  engines/  indicators/
├── journal/  models/  remote/  reports/  research/  review/  runner/
├── cli.py             # Typer CLI 总入口 (~大文件,聚合 22 个子命令)
├── config.py  context.py  deployment.py  storage.py  ...
└── paper_controls.py  paper_readiness.py  strategy_lifecycle.py  ...
dashboard/             # Vite + React 18 + Tailwind + Radix UI (~65 ts/tsx)
capabilities/          # registry.yaml — 数据源能力清单
strategy_specs/        # drafts/ active/ approved/ retired/
.agents/skills/        # 7 个 agent skill 描述,镜像到 .claude/skills/
data/                  # sample / fixtures / cache (gitignore)
docs/                  # 9 个中文设计/审计文档
```

### 2.3 核心理念
1. **`StrategySpec` 是真值源**:YAML 规格驱动一切下游产物 (Python 信号代码、Pine Script、回测、报告、订单)。
2. **CLI + 文件先行**:Dashboard 是 read-model,从 `reports/dashboard/catalog.json` 读取。
3. **强分级 gate**:`workflow_pass` ≠ `research_pass` ≠ `llm_contribution_pass` ≠ `paper_ready_pass`,严禁混用。
4. **Paper-only**:实盘券商写入明确排除在 MVP 之外。
5. **能力优先**:每个数据源都有 fixture、status、reliability、caveats 字段;新依赖必须先过 `oc capability test`。

---

## 3. 优点 (Strengths)

### 3.1 安全工程做得相当扎实

#### Paper 订单的多层闸门 ([open_composer/adapters/broker/alpaca_paper.py:125-135](open_composer/adapters/broker/alpaca_paper.py#L125))
提交一笔模拟单需同时满足 6 个条件:
1. `spec.lifecycle == "active"`
2. `execution.mode == "paper_auto"` 且 `broker == "alpaca_paper"` (且 Pydantic `model_validator` 在加载 spec 时已校验过这两者绑定)
3. `ALPACA_PAPER=true` 环境变量
4. Alpaca 双 Key 都存在
5. `paper_kill_switch` 未触发 ([paper_controls.py:35-92](open_composer/paper_controls.py))
6. 同 `signal_id` 未重复提交 (基于 `client_order_id = "oc-{signal.id}"` 幂等)

#### Remote Daemon 的 HMAC 鉴权 ([open_composer/remote/auth.py](open_composer/remote/auth.py))
教科书式实现:
- `hmac.compare_digest` 常时比较防 timing attack ([auth.py:154,166](open_composer/remote/auth.py#L154))
- 5 个签名 header (timestamp / nonce / actor / body-sha256 / signature) 全部必填
- 默认 ±300 秒时间窗口
- `NonceStore` 含 TTL 清理 + 重放拒绝 ([auth.py:31-44](open_composer/remote/auth.py))
- Body 长度上限 1 MB ([server.py:37](open_composer/remote/server.py#L37))
- 仅允许预设 `actor`
- 服务端返回 `Cache-Control: no-store`
- Yellow/Red 操作要求双重确认短语 (`CONFIRM REMOTE PAPER CONTROL` 等)

#### 路径遍历防护
- `agent_requests._validate_relative_path()` 对 `is_absolute()` + `resolve()/is_relative_to(root)` 双重校验 ([agent_requests.py:112-123](open_composer/agent_requests.py#L112))
- Dashboard 命令的 `plan_path` 同样做了 resolve + is_relative_to 校验 ([dashboard/server.py:251-256](open_composer/dashboard/server.py#L251))

#### Dashboard 本地服务的 Token 比较
`secrets.compare_digest()` 常时比较 ([dashboard/server.py:185](open_composer/dashboard/server.py#L185)),并支持 `Bearer` 与 `X-Open-Composer-Token` 两种头。

### 3.2 数据建模严谨
所有 Pydantic Model 都用 `ConfigDict(extra="forbid")` (扫描了 ~30 个模型,无一例外),从源头杜绝未知字段注入和 typo 静默吞噬。
模型间存在结构性 invariant (例 `ExecutionConfig.broker_matches_mode` `model_validator`)。

### 3.3 数据源能力治理 ([capabilities/registry.yaml](capabilities/registry.yaml))
8 个 capability 都有显式 `status` (approved / trial)、`reliability` (high / medium / unknown / noisy)、`use_for`、`paper_ready_timeframes`、`fixture` 路径、`caveats`。允许「样本数据上做工作流验证、绝不当作 paper 凭据」的语义干净分离。

### 3.4 工程纪律
- `ruff check .` 全部通过 (E/F/I/UP/B 规则集)
- `requires-python = ">=3.11"`,`from __future__ import annotations` 一致采用
- `.gitignore` 严防 `.env` / `.codex/config.toml` / `signal_logs/` / `reports/*` (仅放行少量演示)
- 9 篇内部中文设计/复盘文档,可见持续的方法论沉淀 ([docs/](docs/))
- `Makefile` 把 `bootstrap / verify / readiness / deploy-prepare` 封装成幂等命令
- 自带 `oc doctor` + `oc readiness --strict` + `oc remote doctor` 自检体系

### 3.5 可重放性 (Reproducibility)
- LLM/news/event/macro 输入必须被打包成 **point-in-time feature packet** (含 `visible_at`、`published_at`、`fetched_at`、`source`、`input_hash`、`prompt_hash`) 才能影响交易
- 信号写入 `signal_logs/*.jsonl`,订单写入 `reports/paper/orders.jsonl`,kill switch 事件写 `kill_switch_events.jsonl`,全部追加式
- LLM exposure-switch 报告会保存 prompt artifact、把 OOS 隐藏到选择之后,防止过拟合泄漏

---

## 4. 问题与建议

### 4.1 中等优先级 (Medium)

#### M1. Windows 路径序列化导致跨 OS 不可移植 — **确认是真 bug**
**症状**: 21 个失败用例中 18 个直接由这一类问题导致 (例:[test_dashboard_commands.py:73](tests/test_dashboard_commands.py#L73)、[test_deployment.py:21](tests/test_deployment.py#L21)、[test_dashboard_server.py:98](tests/test_dashboard_server.py#L98))。

```
AssertionError:
  - reports/paper/sync.jsonl     (期望 POSIX)
  + reports\paper\sync.jsonl     (实际 Windows 原生)
```

**根因**: 代码大量使用 `str(path.relative_to(root))`,在 Windows 上得到 `\` 分隔符;这些字符串又被原样写入:
- `reports/dashboard/catalog.json` → 浏览器/Dashboard 要消费的 URL
- `reports/dashboard/commands/*.result.json` 的 `output_paths`
- `cli_args` 里给 `uv run oc backtest …` 的命令行参数 (Windows 上 typer 能处理,但跨 OS 复制会断)
- `report_json_path / report_markdown_path` 字段

**影响**:
- 在 Windows 上生成的 Dashboard JSON 在 Linux/Mac 浏览器打开后路径解析错误
- HTML Dashboard 的相对链接会 404
- 自动化脚本里 `path.startswith("reports/")` 类断言失效

**建议**: 在所有 **写入 JSON / HTML / CLI 拼接** 的边界统一调用 `path.as_posix()`,内部计算继续保留 `Path` 对象。可写一条 `ruff` 自定义规则或 `grep -nE 'str\(.*relative_to'` 挨个改。

#### M2. NautilusTrader catalog URI 在 Windows 上崩溃
**症状**: 3 个测试失败 ([test_strategy_versions_and_capability_expansion.py:191/255/542](tests/test_strategy_versions_and_capability_expansion.py))
```
ValueError: Port could not be cast to integer value as
'\\Users\\hzc_\\AppData\\Local\\Temp\\pytest-of-hzc_\\…'
```

**根因**: [open_composer/adapters/execution/nautilus_runtime.py:372](open_composer/adapters/execution/nautilus_runtime.py#L372) 调用
`ParquetDataCatalog.from_uri(str(catalog_root.resolve()))`。
`str()` 出来的 `D:\Users\…` 进入 fsspec.utils.infer_storage_options,被当成 URL 解析:`D` 看作 scheme,后续 `\Users\…` 让 urlparse 失败。

**建议**: 改为 `ParquetDataCatalog.from_uri(catalog_root.resolve().as_uri())` 或使用 `from_path`(若 nautilus 暴露的话)。

### 4.2 低优先级 (Low)

#### L1. Windows 上 `Path("/etc/passwd").is_absolute()` 返回 False
[agent_requests._validate_relative_path](open_composer/agent_requests.py#L112) 在 Windows 上让 `/etc/passwd` 绕过第一道 `is_absolute()` 检查,但**仍被第二道 `is_relative_to(root)` 拦下** — 安全没破,只是错误信息从 "workspace-relative" 变成 "stay within"。
**建议**: 加一行 `if value.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:[\\/]", value): raise ValueError("workspace-relative")`,让两个 OS 上语义一致。测试 [test_agent_requests.py:40](tests/test_agent_requests.py#L40) 也就过了。

#### L2. 本地 Dashboard 服务的 CORS 是 `Allow-Origin: *`
[dashboard/server.py:41](open_composer/dashboard/server.py#L41)。在配置了 token 的情况下并无机密泄露 (token 校验是真实的),但若用户用反代把 8000 端口暴露出去,浏览器侧任意 origin 都能发起带 token 的请求 (token 通常由 query 注入到 localStorage)。
**建议**: 限定为 `http://127.0.0.1:8000` / `http://localhost:8000`,或读 `OC_DASHBOARD_ALLOWED_ORIGIN`。README 已警告 "Remote deployments must not use query tokens or `localStorage` tokens" — 可在 `serve_dashboard` 启动时再次打印提示。

#### L3. Dashboard `package.json` name 残留 Figma 模板痕迹
`"name": "@figma/my-make-file"` ([dashboard/package.json:2](dashboard/package.json#L2)),应该改成 `@open-composer/dashboard` 之类。纯属命名,但发布到任何 registry 前必须改。

#### L4. `pyproject.toml` 写 `requires-python = ">=3.11"`,实测拉的是 3.13
依赖里 `nautilus-trader==1.219.0` 在 3.13 上能跑,`websockets` 抛了一个 `legacy` deprecation warning。建议 CI 同时跑 3.11 和 3.13,锁定 lower bound 后再放宽。

### 4.3 信息性观察 (Informational)

#### I1. OPENAI_BASE_URL 可指向第三方 OpenAI 兼容网关 — **是设计选择,但需提醒**
我本机 `~/.codex/config.toml` 把 `OPENAI_BASE_URL` 配到了 `https://ai.input.im` (第三方 gateway),`oc doctor` 显示 `OPENAI_BASE_URL = codex / https://ai.input.im`。
README 第 25-27 行明确写了「项目不会因为 endpoint 不是官方 openai.com 域名就拒绝」 — 这是有意设计 (允许 trusted gateway / 自部署 LLM)。

**对仓库本身没问题**;只是任何用 LLM review / LLM exposure-switch 功能的人,都需要意识到提示和 signal context 数据会经过此 endpoint。.codex 配置不在仓库里 (`.gitignore` 已排除),OK。

#### I2. 文件型并发的轻微竞态
[remote/auth.py:NonceStore](open_composer/remote/auth.py#L26) 在 read-modify-write `remote-nonces.json` 时无文件锁。单用户场景几乎不可能触发,但若两个签名请求几乎同时进入,理论上一个 nonce 可能漏判。
**建议**: 加 `portalocker` 或 `fcntl` 包一层 (个人产品场景下,改不改皆可)。

#### I3. Nautilus + Python reference 双引擎并存
README 与 AGENTS.md 都说「不要再造一个完整执行引擎,Nautilus 是目标路径」,但仓库里同时维护 [open_composer/engines/backtest_engine.py](open_composer/engines/backtest_engine.py) (Python reference)。代码有意把 Python 引擎定位为「确定性参考实现 + 烟囱测试」,Nautilus 是产物路径,这个定位是清晰的;只是新人容易困惑两者差异。可在 [engines/backtest_engine.py](open_composer/engines/backtest_engine.py) 顶部加一行 docstring 说明双引擎策略。

---

## 5. 安全审查清单速览

| 项 | 状态 | 备注 |
|---|---|---|
| 命令注入 (`subprocess`/shell=True) | ✅ 未发现 | CLI 用 typer,广泛使用 list 形式 |
| SQL 注入 | N/A | 全部 JSONL/JSON/CSV/YAML,无数据库 |
| XSS / HTML 注入 | ⚠️ 待查 | Dashboard 是 React 18 (默认 escape);HTML report 见 [dashboard/html.py](open_composer/dashboard/html.py),建议确认所有用户/LLM 内容都走 `html.escape` |
| 路径遍历 | ✅ 已防 | `is_relative_to(root)` (一处 Windows 语义偏差见 L1) |
| HMAC / 鉴权 | ✅ 强 | constant-time compare + nonce TTL + ts 窗口 + actor 白名单 |
| Secrets 泄露 | ✅ 良好 | `.gitignore` 排除 `.env` / `.codex/config.toml`;`oc doctor` 只显示 `set/missing` 不打印值 |
| 反序列化 (yaml.load) | ✅ 安全 | 全部 `yaml.safe_load` (Grep 确认) |
| LLM 不受信输入 | ✅ 已规约 | AGENTS.md 明文「外部文档/MCP/新闻/filings/LLM 输出视为不受信 reader input」 |
| 默认 deny / 显式 allow | ✅ | Dashboard 命令是显式 18 项 allowlist;paper 订单需要 `--allow-paper-orders` flag |
| Kill switch | ✅ | 全局 + 个 strategy 级生效 |
| 依赖版本钉死 | ✅ | `uv.lock` 在仓库内 |

---

## 6. 总评

**评级**: **B+ / 可投产 (个人 paper 场景)**,跨 OS 发布前还差一处中等修复 (M1)。

| 维度 | 分 | 一句话 |
|---|---|---|
| 架构清晰度 | A | StrategySpec 单一真值源 + CLI/file-first 干净分层 |
| 安全工程 | A- | HMAC、Paper 多层闸门、Pydantic 严格、Path 校验都做到位 |
| 测试覆盖 | B+ | 159 个用例,86.8% 在 Windows 也能过;关键模块 (paper / dashboard / agent_requests) 都有 |
| 跨 OS 可移植 | C+ | M1 路径分隔符问题 + M2 Nautilus URI 问题,Windows 上有 21 个用例红 |
| 文档完整 | A | 9 篇中文方法论 + AGENTS.md + CLAUDE.md + 9 个 skill 描述 |
| 工程纪律 | A | Ruff 干净、`uv.lock` 钉版本、Makefile 完整 verify 流水线 |

**最优先建议** (按 ROI 排序):
1. **修 M1**:全局把 `str(path.relative_to(...))` 替成 `path.relative_to(...).as_posix()` (尤其是被序列化进 JSON / HTML / CLI 字符串的边界)。改完估计 21 个失败用例能掉到 0 - 3 个。
2. **修 M2**:`ParquetDataCatalog.from_uri(catalog_root.resolve().as_uri())`。
3. (可选) **L3**:把 `dashboard/package.json` 的 name 改掉再上 npm。
4. (可选) **CI 加 Windows runner** 来避免再次出现这类回归。

**强烈赞赏**:
- HMAC 实现是我审过的 Python 仓库里最干净的几个之一 (constant-time、nonce TTL、5 个 header 一个不少、actor 白名单、200 行内全在一个 module)。
- Paper 订单的 6 重 gate + 1 个 idempotency key,基本不可能误下单。
- AGENTS.md / CLAUDE.md 把「workflow_pass / research_pass / llm_contribution_pass / paper_ready_pass 严格区分」写进了 agent 规则,这是非常成熟的研究纪律。

---

*Report end. 审计依据为 ruff、pytest、源码静态阅读 (cli/config/remote/dashboard/paper_controls/paper_readiness/agent_requests/strategy_spec/capabilities/registry/broker/alpaca_paper/review/llm 等关键文件) 以及 oc doctor / oc capability test / oc spec validate / oc backtest 端到端冒烟。*
