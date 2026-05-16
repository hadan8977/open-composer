# Open Composer Setup Standardization Plan (`oc setup` CLI)

**版本**: 2026-05-16 v1
**作者**: Open Composer 维护者审计反馈 + 2026-05-16 本地部署实测
**执行者**: Codex / Claude Code
**前置阅读**: `AGENTS.md`、`CLAUDE.md`、`docs/setup-local.zh.md` (现有的清单式文档)、`scripts/setup-local.ps1` / `setup-local.sh` (现有的临时脚本)

---

## 0. 背景与动机

### 0.1 维护者反馈 (2026-05-16)

> "整体部署应该做得更标准化流程化一点，比如整体的配置步骤，需要配置什么环境和key等等，这个项目应该引导 codex 和 claude code 根据要求让用户输入，或者做成脚本来辅助也可以，最好是能显示输出整体的步骤，到哪一步了，需要做什么等等"

### 0.2 实测痛点 (2026-05-16 本地部署回放)

在 Windows 11 + Python 3.13 + Node 24 上从零部署时遇到的真实问题:

| # | 痛点 | 现象 | 当前规避方法 |
|---|---|---|---|
| P1 | 没有"我该跑什么"的入口命令 | 用户/Codex 要翻 Makefile + README 拼命令序列 | 翻 `Makefile` 看 target |
| P2 | `oc repo check` 失败时没说人话 | 输出 `status=blocked` 但 blocked 原因要去 reports/repo/repo-check.json 翻 | 手动 `Read` reports |
| P3 | Windows 路径 bug 阻断 docs_inventory | `str(path.relative_to(...))` 在 Win 出 `\\`,与 POSIX-form `CURRENT_DOCS` 比较失败 | 手动改 `.as_posix()` |
| P4 | `oc dashboard catalog` 跑完不告诉你下一步 | 显示了几个 strategy,但用户不知道是否要 `dashboard html` 还是 `npm run build` | 翻 Makefile 的 `dashboard-build` target |
| P5 | `.env` 配置没引导 | `.env.example` 列了 30+ 变量,哪些必要哪些可选不清晰 | 自己 grep + 读代码 |
| P6 | 没有进度可见性 | 一系列命令跑完后,不知道当前在哪个 phase | 跑 doctor 自己看 |
| P7 | 失败时不可续 | 跑到第 8 步失败,前 7 步要重跑还是可以跳过? 不明 | 凭经验跳过 |
| P8 | Codex/Claude Code 没机器可读 setup 状态 | Agent 无法 query 当前状态做下一步决策 | 解析 stdout |

### 0.3 当前缓解方案 (已交付,见仓库)

- `docs/setup-local.zh.md` — 清单式部署指南,10 步 + env keys 表 + troubleshooting
- `scripts/setup-local.ps1` — Windows PS 脚本,顺序跑 + 进度显示 + 失败处停 + 末尾总结
- `scripts/setup-local.sh` — Linux/Mac 同等脚本

这两个临时方案能解决 P1/P4/P5/P6/P7。**但还不够好**:
- 脚本是 PS/bash 双套,容易漂移
- Codex 不容易 query 状态 (要 parse stdout)
- 没法增量配置 (要么全跑要么自己拆开)
- 没解决 P2 (repo check 失败原因不人话)
- 没解决 P3 (Windows 路径 bug,要源代码层修)
- 没解决 P8 (机器可读)

本计划要做的是**永久解决方案**:把这些脚本能力固化进 `oc setup` 子命令,跨 OS 一致、可 query、可续、可 dry-run。

---

## 1. 目标产品形态

### 1.1 命令面

```bash
uv run oc setup                              # = oc setup status (默认子命令)
uv run oc setup status                       # 显示当前 setup 状态表
uv run oc setup status --json                # 同上但机器可读
uv run oc setup run                          # 跑所有 auto 步骤到第一个手动 blocker
uv run oc setup run --step <name>            # 只跑某一个步骤
uv run oc setup run --skip <name>            # 跑所有但跳过某步
uv run oc setup keys                         # 交互式 .env 配置向导
uv run oc setup keys --set KEY=value         # 非交互写入单个 key
uv run oc setup keys --check                 # 只检查不修改,列出缺什么
uv run oc setup reset --step <name>          # 标记某步为未完成,下次 run 会重跑
uv run oc setup --profile <name>             # 切换 profile (local | vps-daemon | vps-full | dashboard-only)
uv run oc setup --help                       # 显示用法
```

### 1.2 默认输出形态 (`oc setup` / `oc setup status`)

```
                       Open Composer Setup — local profile
+-----------------------------------------------------------------------------+
| #  | Step                       | Status | Detail                          |
|----+----------------------------+--------+---------------------------------|
| 1  | uv toolchain               |   ok   | uv 0.11.14                      |
| 2  | node + npm                 |   ok   | v24.11.0 / 11.6.1               |
| 3  | Python deps                |   ok   | .venv synced (54 packages)      |
| 4  | Dashboard node deps        |   ok   | 1615 modules                    |
| 5  | Repo consistency           |   ok   | docs_inventory + 7 others       |
| 6  | .env configuration         |   warn | 6/19 keys (see `oc setup keys`) |
| 7  | Capability evaluation      |   warn | 3/8 ok, 5 using fixture         |
| 8  | Dashboard catalog          |   ok   | 3 strategies / 4 versions       |
| 9  | Dashboard frontend (Vite)  |   ok   | 296 KB JS                       |
| 10 | Dashboard serve            | pending| Run `oc setup run --step serve` |
+-----------------------------------------------------------------------------+

Profile: local
State:   8 ok / 2 warn / 1 pending / 0 fail
Next:    oc setup run --step serve

Tip: run `oc setup status --json` for machine-readable state.
```

### 1.3 `oc setup run` 输出

```
[ 1/10] uv toolchain              ok   uv 0.11.14
[ 2/10] node + npm                ok   v24.11.0 / 11.6.1
[ 3/10] Python deps               ok   .venv synced
[ 4/10] Dashboard node deps       ok   node_modules present
[ 5/10] Repo consistency          ok   all checks passed
[ 6/10] .env configuration        warn 6/19 keys (run `oc setup keys` to configure)
[ 7/10] Capability evaluation     warn 3/8 ok, 5 fixture
[ 8/10] Dashboard catalog         ok   3 strategies / 4 versions / 11 signals
[ 9/10] Dashboard frontend        ok   296 KB JS
[10/10] Dashboard serve           ok   http://127.0.0.1:8000 (PID 12345)

──────────────────────────────────────────────────────────────────
✓ Open Composer is ready locally.

Optional next steps:
  • Configure API keys:  oc setup keys
  • Try a strategy:      oc strategy draft "..."
  • Browse dashboard:    http://127.0.0.1:8000
──────────────────────────────────────────────────────────────────
```

### 1.4 `oc setup keys` 输出 (交互式)

```
+-----------------------------------------------------------------------------+
|                       Open Composer Env Wizard                              |
+-----------------------------------------------------------------------------+

This wizard updates D:/hadan/finance/open-composer/.env.
Press ENTER to skip a key (leave it missing).
Type 'q' to quit at any prompt.

Group 1/5: LLM (Review cards, strategy drafts)
  [1/3] OPENAI_API_KEY (optional)
        Current: missing
        Where:   https://platform.openai.com/api-keys
        Used by: review/llm.py, strategy draft --use-llm
        Value:   _

  [2/3] OPENAI_BASE_URL (optional)
        Current: missing
        Default: https://api.openai.com/v1
        Used by: 3rd-party gateways / self-hosted models
        Value:   _

  [3/3] OPENAI_MODEL (optional)
        Current: gpt-4.1-mini (default)
        Used by: review card generation
        Value:   _

Group 2/5: Alpaca Paper (paper trading sync)
...
```

### 1.5 `oc setup status --json` 输出

```json
{
  "profile": "local",
  "generated_at": "2026-05-16T15:00:00Z",
  "summary": {
    "total": 10,
    "ok": 8,
    "warn": 2,
    "pending": 1,
    "fail": 0
  },
  "steps": [
    {
      "name": "uv_toolchain",
      "title": "uv toolchain",
      "status": "ok",
      "detail": "uv 0.11.14",
      "actionable": false,
      "next_action": null,
      "blocking": false,
      "auto_runnable": true
    },
    {
      "name": "dashboard_serve",
      "title": "Dashboard serve",
      "status": "pending",
      "detail": "not started",
      "actionable": true,
      "next_action": "uv run oc setup run --step dashboard_serve",
      "blocking": false,
      "auto_runnable": true,
      "metadata": {
        "default_port": 8000,
        "log_path": null
      }
    }
  ]
}
```

Codex 用此 JSON 决定:
- `status == "ok"`:跳过
- `status == "warn"` + `blocking == false`:可继续
- `status == "fail"`:必须修
- `auto_runnable == true`:可由 `oc setup run` 自动执行
- `auto_runnable == false`:需要 `oc setup keys` 或人工

---

## 2. 实现细节

### 2.1 文件结构

```
open_composer/
  setup/
    __init__.py        # public API: get_setup_status, run_setup_step, ...
    cli.py             # typer commands wired into open_composer.cli.app
    steps.py           # Step abstraction + concrete step implementations
    profiles.py        # Profile registry (local, vps-daemon, vps-full, dashboard-only)
    state.py           # On-disk state cache (reports/setup/state.json)
    keys_wizard.py     # Interactive env wizard
    env_writer.py      # Safe .env read/write (preserves comments, no key leakage)
    models.py          # Pydantic: SetupStep, SetupStatus, SetupReport
```

### 2.2 Step 抽象 (Pydantic + 函数指针)

```python
# open_composer/setup/models.py
from __future__ import annotations
from typing import Callable, Literal
from pydantic import BaseModel, ConfigDict, Field
from datetime import UTC, datetime

StepStatus = Literal["ok", "warn", "fail", "pending", "skipped"]


class StepResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: StepStatus
    detail: str
    next_action: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
    duration_seconds: float | None = None


class StepDefinition(BaseModel):
    """Static description of a setup step."""
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    name: str                          # machine-readable id, e.g. "uv_toolchain"
    title: str                         # display name
    description: str                   # 1-line user-facing description
    profile_membership: list[str]      # which profiles this step is part of
    auto_runnable: bool                # if False, requires human (e.g. env keys)
    blocking: bool                     # if True, downstream steps cannot proceed
    depends_on: list[str] = Field(default_factory=list)
    # The runtime function for status check and run are looked up
    # in steps.py registry by `name`; they are NOT stored in the model
    # (Pydantic + callables = pain).


class SetupReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    steps: list[dict]                  # list of step + StepResult merged dicts
    summary: dict[str, int]
```

```python
# open_composer/setup/steps.py
from collections.abc import Callable
from pathlib import Path

from open_composer.setup.models import StepDefinition, StepResult

# Registry: name -> (definition, check_fn, run_fn)
_REGISTRY: dict[str, tuple[StepDefinition, Callable, Callable | None]] = {}


def register_step(
    definition: StepDefinition,
    check: Callable[[Path], StepResult],
    run: Callable[[Path], StepResult] | None = None,
) -> None:
    _REGISTRY[definition.name] = (definition, check, run)


def all_step_definitions(profile: str) -> list[StepDefinition]:
    return [d for d, _, _ in _REGISTRY.values() if profile in d.profile_membership]


def check_step(name: str, root: Path) -> StepResult:
    _, check_fn, _ = _REGISTRY[name]
    return check_fn(root)


def run_step(name: str, root: Path) -> StepResult:
    _, _, run_fn = _REGISTRY[name]
    if run_fn is None:
        raise ValueError(f"step {name} is not auto-runnable")
    return run_fn(root)


# ---- concrete step implementations ----

def _check_uv_toolchain(root: Path) -> StepResult:
    import shutil
    uv = shutil.which("uv")
    if not uv:
        return StepResult(
            status="fail",
            detail="uv not found in PATH",
            next_action="Install uv: https://docs.astral.sh/uv/getting-started/installation/",
        )
    import subprocess
    proc = subprocess.run([uv, "--version"], capture_output=True, text=True)
    return StepResult(
        status="ok",
        detail=proc.stdout.strip(),
        metadata={"path": uv},
    )

# `register_step(...)` for each step, called at module import.
```

### 2.3 Step 列表 (按 dependency 排序)

| # | name | title | auto_runnable | blocking |
|---|---|---|---|---|
| 1 | `uv_toolchain` | uv toolchain | False (install requires shell access) | True |
| 2 | `node_toolchain` | node + npm | False | True (only for local/vps-full profile) |
| 3 | `python_deps` | Python deps (.venv) | True (`uv sync`) | True |
| 4 | `dashboard_node_deps` | Dashboard node deps | True (`npm install`) | True (for serve) |
| 5 | `repo_consistency` | Repo consistency | False (check only) | False (warn,可越过) |
| 6 | `env_file` | .env file | True (copy from example) | False |
| 7 | `doctor` | Doctor (env keys check) | False (check only) | False |
| 8 | `dashboard_catalog` | Dashboard catalog | True (`oc dashboard catalog`) | True (for serve) |
| 9 | `dashboard_frontend` | Dashboard frontend (Vite) | True (`npm run build`) | True (for serve) |
| 10 | `dashboard_serve` | Dashboard serve | True (start background process) | False |

VPS profile 额外:
| 11 | `vps_systemd` | systemd unit | True (with --apply) | False |
| 12 | `vps_caddy` | Caddyfile | True | False |
| 13 | `vps_vercel_env` | Vercel env | True (with VERCEL_TOKEN) | False |
| 14 | `vps_health_verify` | post-deploy health checks | True | False |

dashboard-only profile 只有: 1, 2, 3, 4, 8, 9, 10

### 2.4 Profiles (`open_composer/setup/profiles.py`)

```python
PROFILES = {
    "local": {
        "description": "Local development on a single machine.",
        "steps": [
            "uv_toolchain", "node_toolchain", "python_deps", "dashboard_node_deps",
            "repo_consistency", "env_file", "doctor",
            "dashboard_catalog", "dashboard_frontend", "dashboard_serve",
        ],
    },
    "vps-daemon": {
        "description": "VPS daemon only (assumes Vercel BFF is configured separately).",
        "steps": [
            "uv_toolchain", "python_deps",
            "repo_consistency", "env_file", "doctor",
            "vps_systemd", "vps_caddy",
        ],
    },
    "vps-full": {
        "description": "VPS daemon + Vercel BFF + post-deploy health verify.",
        "steps": [
            "uv_toolchain", "node_toolchain", "python_deps", "dashboard_node_deps",
            "repo_consistency", "env_file", "doctor",
            "dashboard_catalog", "dashboard_frontend",
            "vps_systemd", "vps_caddy", "vps_vercel_env", "vps_health_verify",
        ],
    },
    "dashboard-only": {
        "description": "Rebuild and serve the dashboard, skip env config / capability tests.",
        "steps": [
            "uv_toolchain", "node_toolchain", "python_deps", "dashboard_node_deps",
            "dashboard_catalog", "dashboard_frontend", "dashboard_serve",
        ],
    },
}
```

### 2.5 State 缓存 (`open_composer/setup/state.py`)

设计原则:**不依赖** state cache 来知道 step 状态——每次都重新 check。state cache 只用于:
- 记录 last_run_at (避免无谓重复)
- 记录 background process PID (dashboard_serve)
- 记录 user 显式 skip / reset 标记

```python
# reports/setup/state.json
{
  "profile": "local",
  "last_run_at": "2026-05-16T15:00:00Z",
  "step_states": {
    "dashboard_serve": {
      "last_pid": 12345,
      "last_port": 8000,
      "last_started_at": "2026-05-16T15:00:00Z",
      "user_skipped": false
    }
  }
}
```

### 2.6 `.env` 写入器 (`open_composer/setup/env_writer.py`)

```python
from pathlib import Path

def read_env(path: Path) -> dict[str, str]:
    """读 .env,保留 comment / 空行 / 顺序。"""
    ...

def write_env_key(path: Path, key: str, value: str, *, comment: str | None = None) -> None:
    """写一个 key 到 .env,如果存在则更新,否则追加。
    保留文件其他内容不动。永远 chmod 600 (Unix) 或 ACL 收紧 (Windows)。
    永远不打印 value 到 stdout / log。
    """
    ...

def env_status() -> dict[str, dict]:
    """返回所有已知 key 的状态:
    {
      "OPENAI_API_KEY": {"present": False, "required": False, "group": "llm",
                         "description": "...", "where": "...", "used_by": "..."},
      ...
    }
    """
    ...
```

Key catalog 单独成文件 `open_composer/setup/known_keys.py`,跟 `docs/setup-local.zh.md §3` 的表格 1:1 对应。

### 2.7 CLI 注册 (`open_composer/setup/cli.py`)

```python
import typer
from open_composer.setup import (
    build_setup_report,
    run_setup_steps,
    interactive_keys_wizard,
)

setup_app = typer.Typer(no_args_is_help=False)


@setup_app.callback(invoke_without_command=True)
def setup_default(
    ctx: typer.Context,
    profile: str = typer.Option("local", "--profile", help="Setup profile"),
):
    """默认子命令 = status"""
    if ctx.invoked_subcommand is None:
        ctx.invoke(setup_status, profile=profile, json_output=False)


@setup_app.command("status")
def setup_status(
    profile: str = typer.Option("local", "--profile"),
    json_output: bool = typer.Option(False, "--json"),
):
    ...


@setup_app.command("run")
def setup_run(
    profile: str = typer.Option("local"),
    step: str | None = typer.Option(None, "--step"),
    skip: list[str] = typer.Option([], "--skip"),
    dry_run: bool = typer.Option(False, "--dry-run"),
):
    ...


@setup_app.command("keys")
def setup_keys(
    set_kv: str | None = typer.Option(None, "--set"),
    check_only: bool = typer.Option(False, "--check"),
):
    ...


@setup_app.command("reset")
def setup_reset(step: str = typer.Argument(...)):
    ...
```

然后在 `open_composer/cli.py` 注册:

```python
from open_composer.setup.cli import setup_app
app.add_typer(setup_app, name="setup", help="Setup wizard and progress tracker")
```

---

## 3. 实施阶段

### 3.1 阶段 S1 — Core framework + `status` 子命令 (2-3 days)

**交付**:
- `open_composer/setup/` 目录 + 所有文件骨架
- 4 个 steps 实现 (auto + check):`uv_toolchain`, `node_toolchain`, `python_deps`, `dashboard_node_deps`
- `oc setup status` / `oc setup status --json` 可跑
- `tests/test_setup_status.py`

**验收**:
- `oc setup status` 输出与 §1.2 表格一致
- `oc setup status --json` 输出与 §1.5 schema 一致
- 所有 4 个 step check fn 都有单元测试 + integration test
- ruff/mypy/pytest 全绿

### 3.2 阶段 S2 — `run` 子命令 + 剩余 steps (3-5 days)

**交付**:
- 完成 6-10 步: `repo_consistency`, `env_file`, `doctor`, `dashboard_catalog`, `dashboard_frontend`, `dashboard_serve`
- `oc setup run` 可跑完整序列
- State cache (`reports/setup/state.json`)
- Background process management for `dashboard_serve`
- `tests/test_setup_run.py`

**验收**:
- 在干净环境从零跑 `oc setup run --profile local` 能成功端到端
- 跑 2 次,第二次几乎瞬时 (idempotent)
- 中途 Ctrl+C 后再 `oc setup status` 显示正确部分完成状态
- `dashboard_serve` 启动的后台进程能被 `oc setup status` 检测到 (PID alive + port responding)

### 3.3 阶段 S3 — `keys` 子命令 + env wizard (2-3 days)

**交付**:
- `open_composer/setup/known_keys.py` 完整 (≥19 个 key,与 `docs/setup-local.zh.md §3` 对齐)
- `open_composer/setup/env_writer.py` 完整实现 (保留 .env comment/order)
- `oc setup keys` 交互式向导
- `oc setup keys --set KEY=value` 非交互
- `oc setup keys --check` 只列出
- 安全: 永远不打印 value 到 stdout/log;Unix 上 chmod 600;Windows 上 ACL 收紧
- `tests/test_setup_keys.py`

**验收**:
- 跑 `oc setup keys --set OPENAI_API_KEY=sk-test` 后,.env 文件有这一行,且文件权限正确
- 交互向导可通过 stdin redirection 测试
- 任何 key value 不出现在 stdout/stderr/log/state.json

### 3.4 阶段 S4 — VPS profile + 与 `oc remote bootstrap-vps` 集成 (3-5 days)

**交付**:
- 把现有 `oc remote bootstrap-vps` 的逻辑作为 vps-* steps 实现
- `vps-daemon` / `vps-full` profile 完整
- `oc setup run --profile vps-full` 等价于现有 `oc remote bootstrap-vps --apply --generate-password`
- 保留旧命令 `oc remote bootstrap-vps` 作为别名,内部转发到 `oc setup run --profile vps-full`
- `tests/test_setup_vps.py`

**验收**:
- 旧 VPS bootstrap 测试不破坏
- 新 `oc setup run --profile vps-full` 在 dry-run 模式与旧命令输出一致

### 3.5 阶段 S5 — 替换临时脚本 + 文档收尾 (1-2 days)

**交付**:
- `scripts/setup-local.{ps1,sh}` 改为薄 wrapper:`exec uv run oc setup run --profile local "$@"`
- `docs/setup-local.zh.md` 顶部加 "推荐用 `oc setup` CLI" 说明
- README 加快速开始: `uv run oc setup run`
- AGENTS.md 加: "Codex 第一次进项目时,跑 `uv run oc setup status` 看当前状态"

**验收**:
- 临时脚本仍可用 (作为入口),但内部委托给 CLI
- `oc setup` 出现在 `oc --help` 顶层

---

## 4. 关键设计约束

### 4.1 安全 (Security)

| 约束 | 实现 |
|---|---|
| 不打印任何 .env value 到 stdout/stderr/log | `env_writer.py` 严格分离 read (返回 dict) 和 display (只显示 key + masked value) |
| state.json 不包含 secret | 只存 PID / port / timestamps / step results 的非敏感 metadata |
| `.env` 文件权限 | Unix `chmod 600`,Windows 设置 ACL 仅 owner 可读 (用 `icacls`) |
| 错误信息不泄露路径上下文 | path 错误时只显示相对路径 |
| Telegram bot token / Vercel token 等通过环境变量传入,不存 state | `oc setup keys --set` 写文件后立即从内存擦除 |

### 4.2 跨 OS

| 关注点 | 处理 |
|---|---|
| 所有路径写入字符串前用 `.as_posix()` | 沿用 v1 P1 规则 |
| `dashboard_serve` 启动后台进程 | Linux 用 `subprocess.Popen(..., start_new_session=True)`,Windows 用 `CREATE_NEW_PROCESS_GROUP` |
| port 检查 | `socket.bind(("127.0.0.1", port))` 替代 `lsof`/`Get-NetTCPConnection` |
| `.env` 权限 | Unix `os.chmod(path, 0o600)`,Windows `subprocess.run(["icacls", str(path), "/inheritance:r", "/grant:r", f"{getuser()}:F"])` |
| 控制台 UTF-8 | Windows 上启动时 `sys.stdout.reconfigure(encoding="utf-8")` |

### 4.3 幂等 + 可续

- 每个 step 的 check 是**纯函数**,无副作用
- 每个 step 的 run 必须可重复调用 (e.g. `uv sync` 已 synced 时不报错;`npm install` 已装好时秒级)
- state.json 损坏时,自动重建,不阻塞
- Ctrl+C 中断后,再次 `oc setup run` 从最近未完成的步骤继续

### 4.4 与既有命令的关系

| 既有命令 | 关系 |
|---|---|
| `oc doctor` | 不变。`oc setup` 的 Step 7 内部调用它 |
| `oc repo check` | 不变。`oc setup` 的 Step 5 内部调用它 |
| `oc dashboard catalog` | 不变。Step 8 调用 |
| `oc dashboard serve` | 不变。Step 10 调用,但加 background 管理 |
| `oc remote bootstrap-vps` | S4 后改为内部委托给 `oc setup run --profile vps-full` |
| `make verify` | 不变。`oc setup status` 不替代 `make verify` (verify 跑全部 test,setup 只跑配置) |

### 4.5 Codex / Agent 集成

- AGENTS.md 加一条: **"Codex 第一次进项目或环境疑似不一致时,先跑 `uv run oc setup status --json` 看状态,不要凭记忆决定下一步。"**
- CLAUDE.md 同步加
- 长任务前的姿态 checklist (`v2 §16.1`) 加一项: "`cat AGENTS.md && cat CLAUDE.md && uv run oc setup status`"

---

## 5. 测试策略

### 5.1 单元测试

每个 step 的 check 和 run 函数:
- 正常路径 (everything ok)
- 缺少前置 (e.g. uv not in PATH)
- 部分完成 (e.g. .venv 存在但 outdated)
- 失败重试

### 5.2 集成测试

`tests/test_setup_integration.py`:
- 干净 worktree → `oc setup run --profile local --dry-run` → 不修改任何文件
- 干净 worktree → `oc setup run --profile local` → 端到端成功
- 已 setup 完成的 worktree → 第二次 run 全部 skip / instant
- 部分完成 → resume 正确

### 5.3 跨 OS 验证

- CI matrix 加 `oc setup run --profile local --skip dashboard_serve` 跑通 (避免 CI 起 background 进程)
- Windows / Linux / macOS 都跑

### 5.4 安全测试

- `oc setup keys --set OPENAI_API_KEY=sk-secret` 后,grep stdout/stderr/.audit-*.txt/state.json 都不能出现 "sk-secret"
- 故意把 .env 改成 chmod 777,跑 `oc setup status`,应警告

---

## 6. 不在范围 (Out of Scope)

| 不做 | 理由 |
|---|---|
| GUI 安装向导 (Electron / native) | 与 file-first/CLI-first 哲学冲突 |
| 自动下载安装 uv/node | 跨 OS 复杂度高,且这是用户自己机器的事 |
| 自动注册 SSL 证书 (Let's Encrypt) | VPS bootstrap 现有 Caddy 模板已经处理 |
| 改造 `oc doctor` 输出格式以匹配 setup | 保留 doctor 独立用途 |
| 替代 `make verify` | verify 跑 lint/test/repo check,与 setup 关注点不同 |
| 多用户 setup (per-user state) | OC 是单用户工具 |
| 远程触发 setup (Vercel BFF → daemon) | 安全边界:Vercel 不能跑命令 |

---

## 7. 提交节奏

按 S1 → S2 → S3 → S4 → S5 顺序,每阶段一个 PR:

1. `feat(setup): add `oc setup status` + Step abstraction + 4 baseline steps (S1)`
2. `feat(setup): add `oc setup run` + remaining 6 steps + state cache (S2)`
3. `feat(setup): add `oc setup keys` interactive env wizard (S3)`
4. `feat(setup): integrate VPS profile + delegate `oc remote bootstrap-vps` (S4)`
5. `chore(setup): replace temp setup-local.{ps1,sh} scripts with `oc setup` wrapper + docs (S5)`

每个 PR 跑完 `make verify` 再合。

---

## 8. 验收清单 (整体)

- [ ] `uv run oc setup` (无参数) 显示状态表
- [ ] `uv run oc setup status --json` 输出符合 §1.5 schema
- [ ] `uv run oc setup run --profile local` 在干净环境端到端成功
- [ ] `uv run oc setup run` 第二次跑全部 skip / instant
- [ ] `uv run oc setup keys --set X=Y` 写 .env,不打印 Y
- [ ] `uv run oc setup keys` 交互式 wizard 可走完所有 5 个 group
- [ ] `uv run oc setup --profile vps-full` 等价于 `oc remote bootstrap-vps --apply`
- [ ] CI 三 OS × py3.11/3.13 跑 `oc setup run --profile local --skip dashboard_serve` 全绿
- [ ] AGENTS.md / CLAUDE.md 引用 `oc setup status` 作为开机姿态
- [ ] `scripts/setup-local.{ps1,sh}` 改为薄 wrapper

---

## 附录 A: 与现有计划文档的关系

| 文档 | 关系 |
|---|---|
| `docs/codex-execution-plan-2026-05-15.zh.md` (v1) | 已完成。本计划与 v1 无直接交集 |
| `docs/codex-execution-plan-v2-dashboard-telegram-2026-05-16.zh.md` (Codex 收敛版) | 并行,本计划独立 |
| `docs/setup-local.zh.md` (本仓库现有) | 现在是临时文档,S5 阶段会改成"推荐用 `oc setup`" |
| `docs/remote-dashboard-deploy.zh.md` (VPS 文档) | S4 阶段 vps-full profile 完工后,VPS 部署的"推荐方式"改为 `oc setup run --profile vps-full` |

---

*Plan v1, 2026-05-16. Self-contained for Codex/Claude Code execution.*
