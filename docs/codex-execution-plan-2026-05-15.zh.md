# Open Composer 修复与演进计划 (Codex 执行版)

**版本**: 2026-05-15 v1
**作者**: Open Composer 审计 (基于 2026-05-15 全仓库审计 + 2026-05-14 QuantML 论文学习报告)
**执行者**: Codex / Claude Code
**预期总工时**: P1-P3 ≈ 1-1.5 天;F1-F7 按优先级渐进,可独立并行
**前置阅读**: `AGENTS.md`、`CLAUDE.md`、`AUDIT-REPORT.md`、`reports/quantml_agent_papers_2026-05-14/quantml_agent_paper_study_report.zh.md`

---

## 0. 给 Codex 的执行须知 (READ FIRST)

> **如果你 (Codex / Claude Code) 是带着这份文档进入项目的,这一节是你能完成本计划的最低准备。**

### 0.1 你是谁,这份文档是什么

你是 Codex / Claude Code。你被一个 Open Composer 维护者授权,根据本文档执行一系列修复 (P1-P3) 和功能扩展 (F1-F7)。本文档**自包含**——你不需要看到我和维护者的对话,就能完成全部工作。

本文档的每一阶段都给出:**动机 → 文件路径 → 具体改法 → 验收命令 → 完成定义**。请按阶段顺序完成,每完成一阶段就跑 `make verify` 然后提交一个独立 PR。

### 0.2 项目一句话:Open Composer 是什么

文件优先 (file-first) 的 AI 量化策略工作台。`StrategySpec` (YAML/Pydantic) 是单一真值源,Python 是确定性参考运行时,NautilusTrader 是事件驱动执行路径,TradingView Pine 仅作兼容导出。**实盘券商写入明确 out of scope**;唯一自动写入路径是 Alpaca Paper(模拟盘)。

### 0.3 项目当前状态 (你接手时)

- **Lint**: `uv run ruff check .` clean (零警告)
- **测试**: 在 Linux/macOS 上 159/159 通过;在 Windows 上 138/159 通过(剩 21 个失败均为路径分隔符或 fsspec URI 解析的 Windows 特定问题——本计划 P1 阶段修复)
- **架构**: 139 Python 文件 / ~32K LOC + 65 TS/TSX (Dashboard) / 8 个 capability 适配器 / 22 个 CLI 命令组 / 36 个测试文件
- **审计评级**: B+(可投产 paper 场景);P1 完成后预期升 A-

### 0.4 核心硬约束 (不要触线)

| 触线动作 | 后果 / 处理 |
|---|---|
| 写代码绕过 `oc capability test` | 直接违反 AGENTS.md。先跑 capability test。 |
| 任何方式接触实盘券商 (`alpaca-py` 的非 `paper=True` 路径,或非 Alpaca 的 trading client) | **停下并要求人工确认**。OC 明文 paper-only。 |
| 自建一个完整执行引擎与 NautilusTrader 并行 | AGENTS.md 明文反对。NautilusTrader 是目标路径。 |
| 在 Vercel 端跑回测/pytest/dashboard build/任意 shell 命令 | 明文反对。长任务走 `reports/agent_requests/`。 |
| 在 PR 里改 `.env`、`.codex/config.toml`、远程共享密钥 | 不要 commit secrets。`.gitignore` 已排除,确认一下你没新增。 |
| 在 review/llm 模块直接 `openai.chat.create` 而不经 `feature_packets` | feature 必须 point-in-time 化。 |
| 在路径校验代码绕过 `is_relative_to(root)` | 路径遍历是审计 P1 的核心修项,不要往回走。 |
| 用 `# noqa: ...` 一抹了之地压 ruff 警告 | 全代码库 ruff 干净,任何新警告都是回归。 |

### 0.5 Codex 工作姿态(应对 LLM 自身弱点的 10 条纪律)

(详见 §16,这里是摘要。每个新 session 开始时先读一遍。)

1. 进项目第一件事: `cat AGENTS.md && cat CLAUDE.md`
2. 写代码前: `oc capability test` + `oc spec validate <path>`
3. 长任务 (>5 分钟) 走 `oc agent request-create`,**绝不在主对话里 sleep 等结果**
4. 任何文件写入路径必须经 `Path(...).resolve().is_relative_to(root.resolve())` 验证
5. LLM feature 必须经 `feature_packets.write_feature_packet`,带 `visible_at / published_at / fetched_at / source / input_hash / prompt_hash`
6. PR 前 `make verify` 必须全绿
7. commit message 挂 spec_hash / signal_id / signal_log 路径
8. 不确定数据来源时**不要写下来**
9. `--allow-paper-orders` / `--allow-paper-auto` 出现时停下来要求人工确认
10. ruff 警告别压,先想是不是 schema 漏了字段

---

## 1. 战略指南:5 条核心 invariant

> 这 5 条是从 2026-05-14 论文学习报告 + 当前审计提炼出的总指针。每个阶段都应该问一次「这个改动是否符合这 5 条」。

### Invariant 1 — 五连否定(每个等号都需要单独验证)
> 研究通过 ≠ Alpha;通过回测 ≠ 可交易;通过 Agent 共识 ≠ 事实;通过多模态融合 ≠ 信息增量;**通过代码可运行 ≠ 策略正确**。

工程含义: `workflow_pass / research_pass / llm_contribution_pass / paper_ready_pass` 严格分离;promotion-report 必须把 5 个 pass 显式渲染为 PASS/FAIL 表(F1)。

### Invariant 2 — Ticker 记忆与 uniform trust 是 LLM 默认 bias
> LLM 看到 AAPL 就 confidently bullish 的部分,可能来自训练语料叙事而非市场理解(BlindTrade);LLM 把检索来的信息当同等可信(TrustTrade)。

工程含义: 任何 LLM-driven 选股或评分必须支持 BlindTrade 协议(F3);review card 必须显式打印每条 evidence 的 source + 置信度,不同 source 不能直接相加。

### Invariant 3 — 多模态/多 Agent 不是「越多越好」
> Acoustic Camouflage 证明新增模态可降低尾部召回(66% → 47%);多 Agent 数量本身不是优势,可能只是把同一 bias × N(Reliable Evaluation)。

工程含义: 接收新 feature packet 时强制提供 `single_modality_baseline + marginal_lift`(F2);多 skill/Agent 系统加贡献归因(F7)。

### Invariant 4 — 成本模型决定算法排名
> MACE 证明从固定 bps 切到 Almgren-Chriss / 平方根冲击模型后,RL 算法排名会变。

工程含义: promotion-report 必须包含 cost-grid 敏感性矩阵,而不是单一成本假设(F5)。

### Invariant 5 — 制度可识别性 > 单点预测精度
> History Rhymes 在 OOD 测试中的 PF=1.18 来自宏观制度检索,不是新模型结构。

工程含义: 长期方向加 `oc strategy regime-search` 子命令,把 capability registry 里已有的 macro/news 数据接入(F6)。

---

## 2. 计划全景

> 单人节奏估算。P1 是必做项(修测试),F1-F7 按优先级渐进,可挑选执行。

| 阶段 | 范围 | 必做? | 预估 | 风险 | 关键产出 |
|---|---|---|---|---|---|
| **P1** 跨 OS 路径根治 | M1 (路径分隔符) + M2 (NautilusTrader URI) | **是** | 0.5-1 day | 低 | Windows pytest 158-159/159 |
| **P2** 边界硬化 | L1 (Win 路径语义) + L2 (Dashboard CORS) | 推荐 | 1-2 hours | 低 | UNC 路径拒绝;CORS 收紧 |
| **P3** 命名 + CI matrix | L3 (Dashboard 包名) + L4 (CI 三 OS × 双 Python) | 推荐 | 0.5-1 hour | 极低 | CI 三 OS × py311/313 全绿 |
| **F1** promotion-report 五连否定渲染 | review_card / promotion_report 模板扩展 | **强烈推荐** | 1 day | 低 | report 渲染 5×PASS/FAIL 表 |
| **F2** feature_packets 模态接收 gate | feature_packets 强制 marginal_lift | 推荐 | 1-2 day | 低 | 新模态必须证边际贡献 |
| **F3** `oc strategy blind-test` | 新子命令 + research/blind_test.py | 推荐 | 1 周 | 中(逻辑复杂) | 4 组对照协议 |
| **F4** `expressions.py` AST 白名单 | expressions.py 改造 + 拒绝危险 import | **强烈推荐**(为后续 F6/B-future 铺路) | 1 周 | 低-中 | LLM 生成因子的安全门 |
| **F5** `oc strategy cost-grid` | 新子命令 + research/cost_sensitivity.py | 推荐 | 1 周 | 低 | 多成本模型敏感性矩阵 |
| **F6** `oc strategy regime-search` | 新子命令 + research/regime_retrieval.py | 中期 | 1-2 月 | 中(需嵌入空间) | 历史制度检索 |
| **F7** `.agents/skills/` 贡献归因 | 新模块 research/skill_attribution.py | 中期 | 1-2 月 | 中(需多次回测样本) | DAG-Shapley 近似归因 |

**强烈建议执行顺序**: P1 → F1 → F4 → P2 → P3 → F2 → F3 → F5 → F6 → F7

理由: P1 修测试是先决条件 (没绿 CI 后续无法可靠验证);F1/F4 是低成本但高战略价值的 gate;P2/P3 顺手做完;F2/F3/F5 都是单 backlog 一周内可结束的 self-contained 工作;F6/F7 需要更多前置数据。

---

## 3. 阶段 P1 — 跨 OS 路径根治 (M1 + M2)

> **价值**: 把 21 个 Windows-only 测试失败修到 0,跨 OS 报告可移植。

### 3.1 问题背景

#### M1 — 路径分隔符序列化进 JSON / HTML / CLI 字符串

代码大量使用 `str(path)` 或 `str(path.relative_to(root))`。在 Windows 上 `str(Path("a/b"))` 返回 `'a\\b'`,这些字符串被原样写入 JSON/HTML/CLI 字符串,导致:
- 跨 OS 不可移植 (Linux/Mac 浏览器消费 Windows 生成的 catalog.json 时路径解析错误)
- HTML Dashboard 相对链接 404
- 18 个测试失败的根因

#### M2 — Windows 路径被 fsspec 误判为 URI

`open_composer/adapters/execution/nautilus_runtime.py:372` 调用:
```python
catalog = ParquetDataCatalog.from_uri(str(catalog_root.resolve()))
```
Windows 上 `D:\Users\...` 被 fsspec 当成 URI,`D` 被误判为 scheme,后续 `\Users\...` 让 urlparse 在 port 解析时 `ValueError`。3 个 Nautilus 测试因此失败。

### 3.2 M1 修复 — `as_posix()` 统一序列化边界

#### 原则
- **内部计算继续用 `Path` 对象**(不要把 `Path` 提前 `str()` 化)
- **任何把路径写进 JSON / HTML / CLI 字符串 / 跨 OS 传递场景**,统一调用 `.as_posix()`
- **永远不在序列化边界用 `str(path)` 或 `f"{path}"`**

#### Step 1: 定位所有需要修的写入点

```bash
cd D:/hadan/finance/open-composer  # (或你的工作目录)
rg -n 'str\((.*\.relative_to\(.*\))\)' open_composer/
rg -n 'str\((.*\.resolve\(\))\)' open_composer/
rg -n 'str\(.*Path\(' open_composer/
rg -nP '\bf?["\x27].*\{[^}]*path[^}]*\}' open_composer/   # f-string 里的 path 插值
```

预期会扫到 ≥12 处。已知热点:

| 文件 | 已知模式 | 改法 |
|------|---------|------|
| `open_composer/dashboard/catalog.py` | `path = str(file_path.relative_to(root))` 写进 catalog | `path = file_path.relative_to(root).as_posix()` |
| `open_composer/dashboard/commands.py` | `output_paths.append(str(p.relative_to(root)))` | `output_paths.append(p.relative_to(root).as_posix())` |
| `open_composer/deployment.py` | `report.report_json_path = str(json_path)` 类似字段 | `... = json_path.relative_to(root).as_posix()` (按字段语义决定要不要 relative) |
| `open_composer/paper_readiness.py:118-119` | 同上 | 同上 |
| `open_composer/paper_controls.py` | `report_json_path / report_markdown_path` 字段 | 同上 |
| `open_composer/feature_packets.py` | manifest_path 序列化 | 同上 |
| `open_composer/agent_requests.py:123` | `return str(candidate)` | `return candidate.as_posix()` |
| `open_composer/repo_check.py` | report 中的路径字段 | 同上 |
| `open_composer/dashboard/server.py` | `build_dashboard_command_run_payload` 等返回字段 | 同上 |
| `open_composer/dashboard/html.py` | HTML 模板里的路径 | 同上(注意 HTML link href) |

#### Step 2: 加单元测试加固(防回归)

在 `tests/conftest.py` 增加 helper:

```python
# tests/conftest.py 顶部新增
import re

_PATH_PREFIX_PATTERN = re.compile(
    r'(reports|strategy_specs|signal_logs|data|\.codex|\.agents|tests)\\\\'
)

def assert_no_windows_paths(payload) -> None:
    """递归断言任何字符串字段都不含 Windows 反斜杠路径。"""
    if isinstance(payload, dict):
        for v in payload.values():
            assert_no_windows_paths(v)
    elif isinstance(payload, list):
        for item in payload:
            assert_no_windows_paths(item)
    elif isinstance(payload, str):
        if _PATH_PREFIX_PATTERN.search(payload):
            raise AssertionError(
                f"non-POSIX path detected (use .as_posix() at boundary): {payload!r}"
            )
```

并在 `tests/test_dashboard_catalog.py`、`tests/test_dashboard_commands.py`、`tests/test_deployment.py`、`tests/test_dashboard_server.py` 顶层用一次。

#### Step 3: 验收

```bash
uv run pytest tests/test_dashboard_catalog.py \
              tests/test_dashboard_commands.py \
              tests/test_deployment.py \
              tests/test_feature_validation.py \
              tests/test_repo_check.py \
              tests/test_dashboard_server.py \
              tests/test_agent_requests.py \
              -v
```

期望: 在 Windows + Linux + Mac 三平台全 pass。

### 3.3 M2 修复 — Windows 路径转 file URI

#### 改法
[open_composer/adapters/execution/nautilus_runtime.py:372](../open_composer/adapters/execution/nautilus_runtime.py)

```python
# 旧
catalog = ParquetDataCatalog.from_uri(str(catalog_root.resolve()))
# 新
catalog = ParquetDataCatalog.from_uri(catalog_root.resolve().as_uri())
```

`Path.as_uri()` 在 Windows 输出 `file:///D:/...`,在 POSIX 输出 `file:///...`,fsspec 两边都正确解析。

#### 同模式扫描
```bash
rg -n 'from_uri\(str\(' open_composer/
rg -n '\.from_uri\(' open_composer/   # 全部 from_uri 调用挨个看
```

#### 验收
```bash
uv run pytest tests/test_strategy_versions_and_capability_expansion.py -k nautilus -v
```
期望: 在 Windows + Linux + Mac 三平台 3/3 pass。

### 3.4 P1 阶段 DoD

- [ ] `uv run pytest -q` 在 Windows 上 ≥ 158/159 pass(允许 1 个真正环境性 skip)
- [ ] `uv run pytest -q` 在 Linux/Mac 上 159/159 pass(本来就过,确认无回归)
- [ ] `uv run ruff check .` 仍 clean
- [ ] 任意 OS 生成的 `reports/dashboard/catalog.json` 内不含 `\\\\reports\\\\` 等 Windows 风格路径(用 `python -c` 抽样检查)
- [ ] 提交一个 PR: `chore(paths): unify path serialization to POSIX across boundaries`

---

## 4. 阶段 P2 — 边界硬化 (L1 + L2)

### 4.1 L1 — Windows 上的绝对路径语义对齐

#### 问题
`open_composer/agent_requests.py:112-123` 的 `_validate_relative_path` 在 Windows 上让 `/etc/passwd` 绕过第一道 `is_absolute()` 检查。**仍被第二道 `is_relative_to(root)` 拦下**(安全没破),但错误信息从 "workspace-relative" 变成 "stay within",导致 `tests/test_agent_requests.py:40` 的 `pytest.raises(ValueError, match="workspace-relative")` 在 Windows 上不命中。

#### 改法
```python
# open_composer/agent_requests.py 顶部新增
import re
_POSIX_ABS_OR_DRIVE = re.compile(r"^([/\\]|[A-Za-z]:[\\/])")

def _validate_relative_path(root: Path, value: str) -> str:
    path = value.strip()
    if not path:
        return path
    if _POSIX_ABS_OR_DRIVE.match(path):
        raise ValueError("agent request paths must be workspace-relative")
    candidate = Path(path)
    if candidate.is_absolute():
        raise ValueError("agent request paths must be workspace-relative")
    resolved = (root / candidate).resolve()
    root_resolved = root.resolve()
    if resolved != root_resolved and not resolved.is_relative_to(root_resolved):
        raise ValueError("agent request paths must stay within the workspace")
    return candidate.as_posix()  # 顺便修 M1 在这一处的实例
```

#### 加新测试
```python
# tests/test_agent_requests.py 新增
def test_agent_request_rejects_unc_paths(sample_workspace) -> None:
    """Windows UNC 路径 (\\\\server\\share) 必须被拒绝为 workspace-relative。"""
    with pytest.raises(ValueError, match="workspace-relative"):
        create_agent_request(
            AgentRequestCreate(
                title="UNC path",
                prompt="UNC path",
                related_paths=["\\\\server\\share\\evil.txt"],
            ),
            sample_workspace,
        )

def test_agent_request_rejects_windows_drive_paths(sample_workspace) -> None:
    """Windows 盘符路径 (C:\\xxx 或 D:/xxx) 必须被拒绝。"""
    with pytest.raises(ValueError, match="workspace-relative"):
        create_agent_request(
            AgentRequestCreate(
                title="Drive path",
                prompt="Drive path",
                related_paths=["C:\\Windows\\evil.txt"],
            ),
            sample_workspace,
        )
```

#### 验收
- Windows + POSIX 上 `pytest tests/test_agent_requests.py` 全 pass

### 4.2 L2 — Dashboard CORS 收紧

#### 问题
`open_composer/dashboard/server.py:41` 当前是 `Access-Control-Allow-Origin: *`。即使配了 token,反代到公网后任意 origin 都能发起带 token 的 fetch。

#### 改法

**Step 1**: 在 `open_composer/config.py` 增加:
```python
def dashboard_allowed_origin() -> str | None:
    return os.getenv("OC_DASHBOARD_ALLOWED_ORIGIN", "").strip() or None
```

**Step 2**: 改 `open_composer/dashboard/server.py:end_headers`:
```python
from open_composer.config import dashboard_allowed_origin, dashboard_api_token

def end_headers(self) -> None:
    allowed = dashboard_allowed_origin()
    request_origin = self.headers.get("Origin", "")
    if allowed:
        # 显式配置时严格匹配
        if request_origin == allowed:
            self.send_header("Access-Control-Allow-Origin", allowed)
        # 不匹配时不发 ACAO header,浏览器侧会拒绝
    else:
        # 未配置时,默认仅允许 localhost 系
        port = self.server.server_port
        local_origins = {
            "http://127.0.0.1:8000", "http://localhost:8000",
            f"http://127.0.0.1:{port}", f"http://localhost:{port}",
        }
        if request_origin in local_origins:
            self.send_header("Access-Control-Allow-Origin", request_origin)
    self.send_header("Vary", "Origin")
    self.send_header(
        "Access-Control-Allow-Headers",
        "Authorization, Content-Type, X-Open-Composer-Token",
    )
    self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
    self.send_header("Cache-Control", "no-store")
    super().end_headers()
```

**Step 3**: 在 `.env.example` 已有的 `OC_DASHBOARD_ALLOWED_ORIGIN` 旁加注释说明。在 README.md 的 Dashboard 章节加一段:
> `OC_DASHBOARD_ALLOWED_ORIGIN` 默认未设置时,仅允许 `http://127.0.0.1:<port>` / `http://localhost:<port>`。如果通过反代暴露,请显式设置该环境变量。

#### 加新测试
```python
# tests/test_dashboard_server.py 新增
def test_dashboard_cors_blocks_external_origin_when_unconfigured(...):
    # 用 unittest.mock 或 starting test server,GET /api/dashboard/health
    # 带 Origin: https://evil.example header
    # 断言响应 不包含 Access-Control-Allow-Origin header
    ...

def test_dashboard_cors_allows_localhost_origin_when_unconfigured(...):
    # 同上但 Origin: http://127.0.0.1:8000
    # 断言响应 包含 Access-Control-Allow-Origin: http://127.0.0.1:8000
    ...
```

#### 验收
- 浏览器从 `http://127.0.0.1:8000` 打开 Dashboard 仍能跑全部 API
- `curl -H "Origin: https://evil.example" -H "X-Open-Composer-Token: <token>" http://127.0.0.1:8000/api/dashboard/catalog -i | grep -i access-control` 应**没有** ACAO header

### 4.3 P2 阶段 DoD
- [ ] L1 + L2 测试新增并 pass
- [ ] README Dashboard 章节同步说明
- [ ] 提交 PR: `fix(security): tighten path-traversal guard for Windows + scope dashboard CORS`

---

## 5. 阶段 P3 — 命名 + CI matrix (L3 + L4)

### 5.1 L3 — Dashboard 包名

```diff
# dashboard/package.json:2
-  "name": "@figma/my-make-file",
+  "name": "@open-composer/dashboard",
```

顺手扫一下 Figma 残留:
```bash
rg -ni 'figma|my-make' dashboard/ --glob '!node_modules' --glob '!*.lock'
```
逐项替换或删除。

### 5.2 L4 — CI 三 OS × 双 Python matrix

新增 `.github/workflows/ci.yml`:

```yaml
name: CI
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, windows-latest, macos-latest]
        python: ["3.11", "3.13"]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - name: Install uv
        uses: astral-sh/setup-uv@v3
      - name: Install dependencies
        run: uv sync --python ${{ matrix.python }}
      - name: Lint
        run: uv run ruff check .
      - name: Test
        run: uv run pytest -q
```

### 5.3 P3 阶段 DoD
- [ ] PR 上能看到 6 个 (3 OS × 2 Python) 都绿
- [ ] 提交 PR: `chore(meta): rename dashboard package + add CI matrix`

---

## 6. 阶段 F1 — promotion-report 五连否定渲染

### 6.1 动机
论文 §10 的「五连否定」与 OC `AGENTS.md` 的四级 pass 哲学完全一致,但当前 `promotion-report` 没有显式渲染这 5 个 pass 的状态。Codex 读 report 时容易把"workflow OK"误读成"可以纸面交易了"。

### 6.2 改动点
- 文件: `open_composer/research/promotion.py` (扩展;**注意:不是 promotion_report.py**) + `open_composer/research/__init__.py` 导出
- 调用方: `open_composer/cli.py` 中的 `oc strategy promotion-report` 命令(已有)
- 同步: `open_composer/models/review_card.py` 加字段

### 6.3 实现要点

**Step 1**: 在 `PromotionReport` 上加字段。**注意现有 `PromotionReport` 是 `@dataclass(frozen=True)`,不是 Pydantic BaseModel** (`open_composer/research/promotion.py:35`)。保持同一风格:

```python
# open_composer/research/promotion.py
from dataclasses import dataclass, field
from typing import Literal

FivePassStatus = Literal["pass", "fail", "skipped", "not_applicable"]

@dataclass(frozen=True)
class FivePassChecks:
    workflow_pass: FivePassStatus
    research_pass: FivePassStatus
    llm_contribution_pass: FivePassStatus
    paper_ready_pass: FivePassStatus
    code_correctness_pass: FivePassStatus   # NEW: QuantCode-Bench 启发
    workflow_reason: str = ""
    research_reason: str = ""
    llm_contribution_reason: str = ""
    paper_ready_reason: str = ""
    code_correctness_reason: str = ""

@dataclass(frozen=True)
class PromotionReport:
    strategy_name: str
    source_spec_path: str
    status: PromotionStatus
    ready: bool
    checks: list[PromotionCheck]
    report_path: str
    json_path: str
    five_pass_checks: FivePassChecks | None = None   # 新字段,默认 None 保向后兼容
```

**Step 2**: 在 `build_promotion_report(...)` 内基于现有 sub-checks 推导五个 pass 状态:

| Pass | 推导逻辑 |
|---|---|
| workflow_pass | spec validate + capability test 都过 → pass |
| research_pass | 有 OOS + 滚动 + 多窗口 + 净成本 → pass |
| llm_contribution_pass | 若 spec 用了 LLM feature: 检查 BlindTrade-style 反事实(F3 完成后) + 不是 fallback/local choice → pass;若未用 LLM → not_applicable |
| paper_ready_pass | `assess_paper_strategy_readiness` 全 ok → pass |
| code_correctness_pass | 表达式过 AST 白名单(F4 完成后) + spec 描述与代码逻辑一致(用 review_card 的 LLM judge) → pass |

**Step 3**: Markdown 渲染加一段表格:
```markdown
## 五连否定检查 (Reliable Evaluation × QuantCode-Bench)

| Pass | 状态 | 原因 |
|---|---|---|
| workflow_pass | ✅ pass | spec valid + capability test ok |
| research_pass | ⚠️ fail | OOS 缺 walk-forward |
| llm_contribution_pass | ⏭️ not_applicable | 未使用 LLM feature |
| paper_ready_pass | ❌ fail | ALPACA_API_KEY_ID missing |
| code_correctness_pass | ✅ pass | AST 白名单通过 + LLM judge ok |

**整体可推进 paper readiness?** ❌ 否(paper_ready_pass 失败)
```

**Step 4**: review_card 同步扩展(LLM 必须填):
```python
class ReviewCard(BaseModel):
    # ... 已有字段 ...
    primary_risk_source: str   # "主要风险来源"
    if_wrong_top_3_reasons: list[str] = Field(min_length=0, max_length=3)
    # ↑ 强制 LLM 在生成 review 时显式列出"如果错了最可能的 3 种原因"
    # 对抗 LLM "言之凿凿" 倾向(对应 §1 Invariant 2)
```

**Step 5**: 测试:
```python
# tests/test_promotion_report.py 新增
def test_promotion_report_renders_five_pass_table(...):
    # 给一个故意缺 OOS 的 spec,断言 markdown 有 "research_pass | ⚠️ fail" 行
    ...

def test_promotion_report_marks_llm_contribution_not_applicable(...):
    # 给一个不带 LLM feature 的 spec,断言为 not_applicable
    ...
```

### 6.4 F1 DoD
- [ ] PromotionReport schema 加 five_pass_checks 字段(Pydantic 严格,不破坏既有字段)
- [ ] markdown 渲染 5 行表格
- [ ] review_card 加 primary_risk_source + if_wrong_top_3_reasons
- [ ] 新增 ≥3 个测试
- [ ] 在 README.md 的 promotion 章节加一段说明

---

## 7. 阶段 F2 — feature_packets 模态接收 gate

### 7.1 动机
论文 Acoustic Camouflage 证明:新增模态可能让尾部召回从 66% 掉到 47%。OC 当前接收 feature packet 时只检查 schema/timestamp,不要求作者证明"这个模态有边际贡献"。

### 7.2 改动点
- 文件: `open_composer/feature_packets.py`
- Schema: 在实际类 **`FeaturePacketRow`** (Pydantic, `extra="allow"`,见 `feature_packets.py:26`) 上加新字段
- 同步: `open_composer/paper_readiness.py:_feature_packet_binding_check`

### 7.3 实现要点

**Step 1**: 加新字段(向后兼容,默认 None,但走 paper_auto 时强制要求)。**注意 `FeaturePacketRow` 用 `extra="allow"`,所以新字段不会破坏老 packet**:
```python
# open_composer/feature_packets.py
class FeaturePacketEvidence(BaseModel):
    """新模态进入 paper_auto 路径前,必须证明边际贡献(Acoustic Camouflage 反例驱动)。"""
    model_config = ConfigDict(extra="forbid")

    single_modality_baseline_metric: str   # 例 "auroc=0.62 on validation set"
    marginal_lift_metric: str              # 例 "auroc lift +0.04 over price-only baseline"
    missing_modality_robustness: str       # 例 "graceful degrade: -0.02 auroc when modality missing"
    fixture_path: str | None = None        # POSIX-style relative path to fixture (见 P1 §3.2)
    notes: str = ""

class FeaturePacketRow(BaseModel):
    model_config = ConfigDict(extra="allow")
    # ... 已有字段 (timestamp, published_at, fetched_at, visible_at, source, symbol,
    #     dedupe_key, schema_version, summary, sentiment, model, input_hash, prompt_hash, features) ...
    evidence: FeaturePacketEvidence | None = None   # 新字段
```

**Step 2**: 写入 gate(在 `write_feature_packet(...)` 入口):
```python
def write_feature_packet(
    row: FeaturePacketRow,
    root: Path,
    *,
    allow_research_only: bool = True,
) -> Path:
    # 已有的 ensure_dir / append_jsonl 逻辑前面加:
    if row.evidence is None and not allow_research_only:
        raise FeaturePacketError(
            f"feature packet {row.symbol}@{row.timestamp} lacks evidence; "
            "cannot enter paper_auto path. Either populate row.evidence or "
            "set allow_research_only=True (then it will be tagged research-only)."
        )
    # ... 已有逻辑 ...
```

**Step 3**: 在 `paper_readiness.py:_feature_packet_binding_check` 中调用:
- 如果 spec 用了 LLM feature 但对应 packet 没有 evidence → readiness check fail("blocked")

**Step 4**: look-ahead lint(顺手):
- 加 helper `assert_visible_at_not_in_future(packet, now=None)`,如果 `visible_at > now` 直接 raise
- 在 `write_feature_packet` 入口调用

**Step 5**: 测试:
```python
def test_feature_packet_without_evidence_blocks_paper_readiness(...):
    # 写一个无 evidence 的 packet,assess_paper_strategy_readiness 应返回 blocked
    ...

def test_feature_packet_with_future_visible_at_rejected(...):
    # 写一个 visible_at=未来时间的 packet,write 时应 raise
    ...
```

### 7.4 F2 DoD
- [ ] FeaturePacket 加 evidence 字段
- [ ] paper_readiness 拒绝缺 evidence 的 packet
- [ ] look-ahead lint 生效
- [ ] 新增 ≥2 个测试
- [ ] AGENTS.md 增加一段说明

---

## 8. 阶段 F3 — `oc strategy blind-test` 子命令

### 8.1 动机
BlindTrade(arXiv:2603.17692)证明:LLM 看到 ticker 后的 confident 预测可能来自训练语料叙事记忆而非市场理解。匿名化协议是反事实验证。

### 8.2 改动点
- 新文件: `open_composer/research/blind_test.py`
- CLI: 在 `open_composer/cli.py` 的 `strategy_app` 加 `blind-test` 子命令
- 测试: `tests/test_blind_test.py`

### 8.3 实现要点

**Step 1**: 新模块 `research/blind_test.py`:
```python
from __future__ import annotations
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from open_composer.config import ensure_dir, project_root
from open_composer.engines.backtest_engine import run_backtest
from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec
from open_composer.storage import write_json

BlindMode = Literal["real", "anonymous", "random_remap", "sector_preserved"]

class BlindTestResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: BlindMode
    ticker_mapping_hash: str   # sha256 of the mapping JSON
    return_pct: float
    sharpe: float
    signal_count: int
    correlation_with_real: float | None = None   # populated for non-real modes

class BlindTestReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    strategy_name: str
    strategy_path: str
    results: list[BlindTestResult]
    interpretation: str   # human-readable summary

def run_blind_test(
    spec_path: Path,
    root: Path | None = None,
    *,
    seed: int = 42,
) -> BlindTestReport:
    """运行 4 组对照: real / anonymous / random_remap / sector_preserved。"""
    base = root or project_root()
    spec = load_strategy_spec(spec_path)
    results: list[BlindTestResult] = []
    for mode in ("real", "anonymous", "random_remap", "sector_preserved"):
        rewritten_spec, mapping = _rewrite_spec(spec, mode, seed=seed)
        # 写到临时 path,跑 backtest
        tmp_path = base / "tmp" / "blind_test" / f"{spec.name}_{mode}.yaml"
        ensure_dir(tmp_path.parent)
        tmp_path.write_text(rewritten_spec.model_dump_json(), encoding="utf-8")
        artifacts = run_backtest(tmp_path, root=base)
        result = _build_result(mode, mapping, artifacts)
        results.append(result)
    real_signals = _signals_of(results[0])
    for r in results[1:]:
        r.correlation_with_real = _signal_correlation(real_signals, _signals_of(r))
    interpretation = _interpret(results)
    report = BlindTestReport(
        strategy_name=spec.name,
        strategy_path=spec_path.resolve().relative_to(base.resolve()).as_posix(),
        results=results,
        interpretation=interpretation,
    )
    out_path = base / "reports" / "blind_test" / f"{spec.name}.json"
    write_json(out_path, report)
    return report

def _rewrite_spec(spec, mode, *, seed): ...   # 实现细节: 真实=不变;anonymous=ticker → "ASSET_001";random_remap=洗牌;sector_preserved=同行业内洗牌
def _build_result(mode, mapping, artifacts): ...
def _signal_correlation(a, b): ...
def _interpret(results) -> str:
    """根据 4 组结果生成人类可读结论。
    - 若 anonymous 模式 return/sharpe 与 real 一致 → 信号更可能来自结构,不是记忆
    - 若 anonymous 显著退化 → 信号高度依赖 ticker,警告 LLM 记忆 bias
    - sector_preserved 介于两者之间能定位 bias 在 ticker 还是行业层
    """
```

**Step 2**: CLI 入口:
```python
# open_composer/cli.py 在 strategy_app 下加
@strategy_app.command("blind-test")
def strategy_blind_test(
    spec: Annotated[Path, typer.Argument(help="StrategySpec YAML path")],
    seed: Annotated[int, typer.Option(help="random seed for remap")] = 42,
) -> None:
    """Run BlindTrade-protocol counterfactual evaluation."""
    from open_composer.research.blind_test import run_blind_test
    report = run_blind_test(spec, root=project_root(), seed=seed)
    console = Console()
    table = Table(title=f"BlindTest {report.strategy_name}")
    for col in ("Mode", "Return %", "Sharpe", "Signals", "Corr w/ real"):
        table.add_column(col)
    for r in report.results:
        table.add_row(
            r.mode,
            f"{r.return_pct:.2f}",
            f"{r.sharpe:.2f}",
            str(r.signal_count),
            f"{r.correlation_with_real:.2f}" if r.correlation_with_real is not None else "—",
        )
    console.print(table)
    console.print(f"\n[bold]Interpretation:[/bold] {report.interpretation}")
```

**Step 3**: 接入 promotion-report:
- 在 F1 的 `llm_contribution_pass` 推导逻辑里:**如果 spec 用了 LLM feature**,要求 `reports/blind_test/<name>.json` 存在,且 anonymous 模式与 real 模式的 sharpe 差异 < 阈值(例 0.3),否则 `llm_contribution_pass = fail`。

**Step 4**: 测试用 sample data,确保确定性。

### 8.4 F3 DoD
- [ ] `oc strategy blind-test <spec>` 命令可跑
- [ ] 输出 4 组对照结果 + interpretation
- [ ] 报告写到 `reports/blind_test/`
- [ ] promotion-report 中的 `llm_contribution_pass` 检查 blind_test 报告
- [ ] ≥3 个测试

---

## 9. 阶段 F4 — `expressions.py` AST 白名单

### 9.1 动机
Hubble(arXiv:2604.09601)的核心安全机制是:LLM 只能生成安全子语言中的操作树,通过 AST 层白名单执行。

**重要事实**: `open_composer/expressions.py` **已经用了一个自定义 AST walker** (`_eval_node` 和相关 helper),只递归识别它认识的节点。但当前实现是**「不识别即抛异常」式的隐式白名单**,缺三点:

1. **没有显式的 `FORBIDDEN_NAMES` / `FORBIDDEN_FUNCTIONS` 列表**—— `os.system` 之类的攻击当前会因为「未知 name」被拒,但拒绝原因不明显;debug 时容易被误以为只是配置问题
2. **没有可独立调用的 `assert_expression_safe(expression: str)` 函数** —— 当前安全性绑死在 `_eval_node` 里,LLM 因子生成场景下没有「先验证后入库」的钩子
3. **没有针对恶意输入的回归测试** —— 一旦后续重构 `_eval_node`,可能不知不觉打开 `__import__` 等攻击面

F4 的目标:**显式硬化 + 加可独立调用的安全检查 + 加恶意输入回归测试**。

### 9.2 改动点
- 文件: `open_composer/expressions.py` (重构)
- 测试: `tests/test_expressions_ast.py` (新)

### 9.3 实现要点

**Step 1**: 在 `expressions.py` 顶部增加显式白名单与禁止列表(与现有 `OHLCV_NAMES`、`SERIES_WINDOW_FUNCTIONS` 等并列):
```python
# open_composer/expressions.py 顶部
import ast

# 允许的 Python AST 节点类型
ALLOWED_NODES = frozenset({
    ast.Module, ast.Expression, ast.Expr,
    ast.Load, ast.Store,   # 允许变量读取(必要)
    ast.Constant, ast.Name,
    ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod, ast.Pow, ast.FloorDiv,
    ast.UAdd, ast.USub, ast.Not,
    ast.And, ast.Or,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
    ast.IfExp,                  # 三元
    ast.Call,                   # 函数调用(配合 ALLOWED_FUNCTIONS)
    ast.Attribute,              # 属性访问(配合 ALLOWED_ATTRIBUTES)
    ast.Subscript, ast.Index, ast.Slice,
    ast.List, ast.Tuple,
    ast.keyword,
})

# 允许的函数名(白名单,必须显式列出)
ALLOWED_FUNCTIONS = frozenset({
    # numpy
    "abs", "log", "log1p", "exp", "sqrt", "sign", "minimum", "maximum",
    # pandas-style aggregation (只能调用 series 自带方法,不允许 import)
    "mean", "median", "std", "sum", "min", "max", "shift", "rolling", "rank",
    # OC 自定义算子(在 indicators/ 下定义)
    "ts_zscore", "ts_rank", "regime_label", "winsorize",
})

# 允许的属性(序列方法 + 已知 indicator)
ALLOWED_ATTRIBUTES = frozenset({
    "rolling", "ewm", "shift", "diff", "pct_change",
    "mean", "median", "std", "sum", "min", "max", "rank",
})

# 显式禁止的 import / 名称
FORBIDDEN_NAMES = frozenset({
    "os", "sys", "subprocess", "socket", "requests", "urllib", "httpx",
    "open", "exec", "eval", "compile", "__import__",
    "globals", "locals", "vars", "getattr", "setattr", "delattr",
    "input", "breakpoint",
})

class ExpressionSafetyError(ValueError):
    pass

class _SafetyVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.violations: list[str] = []

    def generic_visit(self, node: ast.AST) -> None:
        if type(node) not in ALLOWED_NODES:
            self.violations.append(
                f"forbidden AST node: {type(node).__name__} at line {getattr(node, 'lineno', '?')}"
            )
        super().generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if node.id in FORBIDDEN_NAMES:
            self.violations.append(f"forbidden name: {node.id!r}")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        if isinstance(func, ast.Name):
            if func.id not in ALLOWED_FUNCTIONS:
                self.violations.append(f"forbidden function call: {func.id!r}")
        elif isinstance(func, ast.Attribute):
            if func.attr not in ALLOWED_ATTRIBUTES:
                self.violations.append(f"forbidden attribute call: {func.attr!r}")
        else:
            self.violations.append(f"unrecognized call form: {ast.dump(func)}")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr in FORBIDDEN_NAMES or node.attr.startswith("__"):
            self.violations.append(f"forbidden attribute: {node.attr!r}")
        self.generic_visit(node)

    def visit_Import(self, node) -> None:
        self.violations.append("import is not allowed in expressions")

    def visit_ImportFrom(self, node) -> None:
        self.violations.append("import is not allowed in expressions")

def assert_expression_safe(expression: str) -> None:
    """Raise ExpressionSafetyError if the expression uses forbidden constructs.

    Use before any compile/eval of an LLM-generated expression.
    """
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ExpressionSafetyError(f"expression is not valid Python: {exc}") from exc
    visitor = _SafetyVisitor()
    visitor.visit(tree)
    if visitor.violations:
        raise ExpressionSafetyError(
            "expression failed AST safety check:\n  - "
            + "\n  - ".join(visitor.violations)
        )
```

**Step 2**: 在 `evaluate_raw_expression(expression, frame)` 入口先调 `assert_expression_safe(expression)`,并在 `validate_expression(...)` 也调一次:
```python
def evaluate_raw_expression(expression: str, frame: pd.DataFrame) -> Any:
    assert_expression_safe(expression)   # 新增,在解析之前
    try:
        parsed = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ExpressionError(f"invalid expression syntax: {expression}") from exc
    return _eval_node(parsed, frame)
```

注意:**不要把 `assert_expression_safe` 直接做成 `_eval_node` 的内部检查**——把它做成可独立 import 的公共 API,让 F3 的 blind-test、未来的 LLM 因子生成器都能在「写入 spec 前」就调用。

扫一下其他可能调用点(本审计已确认 expressions.py 无 `eval()/compile()`,但下游可能有):
```bash
rg -n '\beval\(|\bcompile\(' open_composer/   # 期望只在 ast.parse 上下文里出现
```

**Step 3**: 测试:
```python
# tests/test_expressions_ast.py
import pytest
from open_composer.expressions import assert_expression_safe, ExpressionSafetyError

@pytest.mark.parametrize("safe_expr", [
    "close.rolling(20).mean()",
    "ts_zscore(close, 20)",
    "(close - close.shift(5)) / close.shift(5)",
    "log(close / close.shift(1))",
    "minimum(volume, 1000000)",
])
def test_safe_expressions_pass(safe_expr):
    assert_expression_safe(safe_expr)   # no raise

@pytest.mark.parametrize("evil_expr,reason", [
    ("__import__('os').system('rm -rf /')", "forbidden name"),
    ("eval('1+1')", "forbidden function call"),
    ("open('/etc/passwd').read()", "forbidden function call"),
    ("getattr(close, '__class__')", "forbidden function call"),
    ("subprocess.call(['ls'])", "forbidden name"),
    ("close.__dict__", "forbidden attribute"),
    ("[i for i in range(10)]", "forbidden AST node"),   # ListComp not allowed
])
def test_unsafe_expressions_rejected(evil_expr, reason):
    with pytest.raises(ExpressionSafetyError, match=reason):
        assert_expression_safe(evil_expr)
```

### 9.4 F4 DoD
- [ ] `assert_expression_safe()` 函数实现并被所有 compile/eval 调用点调用
- [ ] ≥10 个测试覆盖 safe + unsafe 两类
- [ ] 在 README.md 加一段说明:OC 表达式语法是受限子集
- [ ] AGENTS.md 增加一段:Codex 生成因子前必须先验证可被 `assert_expression_safe()` 接受

---

## 10. 阶段 F5 — `oc strategy cost-grid` 成本敏感性矩阵

### 10.1 动机
MACE(arXiv:2603.29086)证明:固定 bps 成本下 PPO 排第一,切到 Almgren-Chriss 模型后排名变。OC 当前 `costs.commission_pct` 和 `costs.slippage_bps` 是常量,promotion-report 已支持 `--cost-slippage-bps` 多值但只是单维。

### 10.2 改动点
- 新文件: `open_composer/research/cost_sensitivity.py`
- CLI: `open_composer/cli.py` strategy_app 加 `cost-grid` 子命令
- 模型: 在 `open_composer/models/strategy_spec.py` 的 `CostConfig` 加 `impact_model: Literal["linear", "sqrt", "almgren_chriss"]` (可选,默认 linear)

### 10.3 实现要点

**Step 1**: 扩展 CostConfig:
```python
class CostConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    commission_pct: float = Field(default=0.0, ge=0)
    slippage_bps: float = Field(default=0.0, ge=0)
    impact_model: Literal["linear", "sqrt", "almgren_chriss"] = "linear"
    impact_eta: float = Field(default=0.0, ge=0)   # for sqrt / AC
    impact_gamma: float = Field(default=0.0, ge=0)   # for AC permanent impact
```

**Step 2**: 在 `engines/backtest_engine.py` 中根据 impact_model 计算 fill price 调整。这步需要慎重:不要破坏现有 backtest 数值,默认 linear + impact_eta=0 应等价于现状。

**Step 3**: `cost_sensitivity.py`:
```python
def run_cost_grid(
    spec_path: Path,
    *,
    commission_grid: list[float],
    slippage_grid: list[float],
    impact_models: list[str],
    root: Path | None = None,
) -> CostGridReport:
    """跨 |commission_grid| × |slippage_grid| × |impact_models| 跑 backtest。
    输出:每个组合的 return / sharpe;算法/参数排名变化矩阵。
    """
    ...
```

**Step 4**: CLI:
```python
@strategy_app.command("cost-grid")
def strategy_cost_grid(
    spec: Annotated[Path, typer.Argument()],
    commission: Annotated[list[float], typer.Option(help="可重复")] = [0.0, 0.0001, 0.0005],
    slippage: Annotated[list[float], typer.Option(help="可重复 (bps)")] = [0.0, 5.0, 10.0],
    impact_model: Annotated[list[str], typer.Option(help="可重复")] = ["linear", "sqrt"],
) -> None:
    ...
```

**Step 5**: 接入 promotion-report:
- 在 F1 的 `research_pass` 推导里加一项: 如果 `reports/cost_grid/<name>.json` 存在,且 sharpe 在不同 impact_model 间的 spread > 阈值(例 1.0),warn(说明策略对成本假设敏感,排名不稳)。

### 10.4 F5 DoD
- [ ] `oc strategy cost-grid <spec>` 可跑
- [ ] 报告写到 `reports/cost_grid/`
- [ ] CostConfig 扩展且向后兼容(默认值不改变现有 backtest 数值)
- [ ] ≥3 个测试

---

## 11. 阶段 F6 — `oc strategy regime-search` 制度检索 (中期)

### 11.1 动机
History Rhymes(arXiv:2511.09754)在 OOD 测试中达到 PF=1.18 的核心机制是「检索历史最像现在的宏观制度期」。OC 的 capability registry 已经有 `macro.fred_series`(FRED 宏观)+ `news.alpha_vantage`(新闻情感),恰好是 History Rhymes 输入。

### 11.2 改动点
- 新文件: `open_composer/research/regime_retrieval.py`
- CLI: strategy_app 加 `regime-search` 子命令

### 11.3 实现要点

**Step 1**: 嵌入空间设计
- 输入特征: CPI YoY、失业率、收益率曲线斜率(10y-2y)、GDP 增速、SPX 30 日波动率 + 新闻情感聚合(VADER 或简单 transformer)
- 时间窗口: 月度对齐
- 嵌入: 简单的标准化 + cosine 相似;不引入大模型嵌入(保持 file-first 哲学)

**Step 2**: 检索接口:
```python
def search_similar_regimes(
    target_window_end: datetime,
    *,
    lookback_months: int = 6,
    top_k: int = 5,
    macro_capability: str = "macro.fred_series",
    news_capability: str = "news.alpha_vantage",
    root: Path | None = None,
) -> RegimeSearchReport:
    """检索历史上与 [target_window_end - lookback_months, target_window_end] 最相似的 K 个时期。
    输出:相似度、当时市场表现 (SPX/symbol)、失败案例。
    """
    ...
```

**Step 3**: 接入 promotion-report:
- 在 markdown 末尾加「当前最像哪段历史」一小节,展示 top-3 相似制度 + 当时市场表现

### 11.4 F6 DoD
- [ ] `oc strategy regime-search <spec>` 可跑
- [ ] 报告写到 `reports/regime_search/`
- [ ] 在 promotion-report 中作为可选节
- [ ] ≥3 个测试(用 fixture 数据)

---

## 12. 阶段 F7 — `.agents/skills/` 贡献归因 (中期)

### 12.1 动机
HiveMind(arXiv:2512.06432)用 DAG-Shapley 找出哪个 skill 真正贡献,DAG 剪枝省 80% LLM 调用。OC 有 7 个 skill (capability-evaluator, strategy-designer, …),需要诊断哪些长期低贡献。

### 12.2 改动点
- 新文件: `open_composer/research/skill_attribution.py`

### 12.3 实现要点

**Step 1**: 离线模式
- 在已有 promotion 通过的策略集合上,做 leave-one-skill-out
- 度量: 各 skill 缺席时,promotion 通过率、报告生成时间、token 成本变化
- 用 DAG-Shapley 近似(只评估实际有依赖关系的 subset,不爆所有 2^7 组合)

**Step 2**: 报告:
```python
class SkillAttributionReport(BaseModel):
    skill_name: str
    shapley_value: float
    avg_token_cost_per_invocation: int
    contribution_per_token: float   # value / cost
    promotion_pass_rate_with: float
    promotion_pass_rate_without: float
    recommendation: Literal["keep", "review", "deprecate"]
```

**Step 3**: CLI:
```python
@strategy_app.command("skill-attribution")
def strategy_skill_attribution(
    sample_size: int = 20,   # 用最近 N 个 promotion 报告
):
    ...
```

### 12.4 F7 DoD
- [ ] 报告写到 `reports/skill_attribution/`
- [ ] 至少跑通 leave-one-out(DAG-Shapley 可作为后续优化)
- [ ] ≥2 个测试

---

## 13. 不在范围 (避免被论文风潮带偏)

| 不做 | 理由 |
|---|---|
| 自建一套完整执行引擎与 NautilusTrader 并行 | AGENTS.md 明文反对;NautilusTrader 是目标 |
| LLM 接到实盘券商(非 paper) | OC 明文 paper-only;OOM-RL 提倡的"实盘亏损训练"踩线 |
| Uni-FinLLM 式统一主干模型 | OC 是 spec-first 不是 model-first,范式不兼容 |
| MetaRL-GBWM 式财富管理 | 业务场景与 OC 不重合 |
| SBCA 式 BERT 主干 | 显存/运维成本与 file-first 哲学冲突 |
| SEMF 式频谱特征 | 在文本/宏观/因子还没饱和前不必加新模态 |
| SNAPO 式可微模拟 | 与 NautilusTrader 离散事件路径冲突 |
| Vercel 端跑回测/pytest/dashboard build | AGENTS.md 明文反对 |
| 任何绕过 capability evaluation 的"我先试试" | 直接违反工作纪律 |
| NonceStore 加文件锁 | 单用户场景,真出现问题再说 |
| 让 LLM 直接执行未经 AST 检查的因子代码 | F4 完成前**绝对不允许** |

---

## 14. 全局完成定义 (DoD)

P1-P3 完成后:
- [ ] `pytest` 在 Windows / Linux / macOS 上 ≥ 158/159 通过(允许 1 个真正环境性 skip)
- [ ] `ruff check .` 仍 clean
- [ ] `make verify` 在三平台都过
- [ ] 任意 OS 生成的 `reports/dashboard/catalog.json` 能被另一 OS 正确消费
- [ ] CI matrix 6 格全绿(3 OS × py3.11/3.13)
- [ ] AUDIT-REPORT.md 顶部加一行 `已修复: M1, M2, L1, L2, L3, L4 (commit XXX, 2026-MM-DD)`

F1-F7 完成度按需检查;每个 F 阶段独立 DoD 见各自小节。

---

## 15. 提交节奏

按 P1 → P2 → P3 → F1 → F4 → F2 → F3 → F5 → F6 → F7 顺序提交,每阶段一个独立 PR:

1. `chore(paths): unify path serialization to POSIX across boundaries (M1+M2)`
2. `fix(security): tighten path-traversal guard for Windows + scope dashboard CORS (L1+L2)`
3. `chore(meta): rename dashboard package + add CI matrix for win/posix × py3.11/3.13 (L3+L4)`
4. `feat(promotion): render five-pass checks (workflow/research/llm_contribution/paper_ready/code_correctness) (F1)`
5. `feat(expressions): enforce AST safety whitelist for LLM-generated expressions (F4)`
6. `feat(feature_packets): require evidence (baseline + marginal_lift) for paper_auto path (F2)`
7. `feat(strategy): blind-test counterfactual command for ticker-memory check (F3)`
8. `feat(strategy): cost-grid sensitivity matrix command (F5)`
9. `feat(strategy): regime-search macro-context retrieval command (F6)`
10. `feat(skills): contribution attribution for .agents/skills/ (F7)`

每个 PR 跑完 `make verify` 再合。

---

## 16. Codex 工作纪律(完整版,任何新 session 必读)

> 这一节是 §0.5 的展开。LLM 在 OC 项目上的常见失败模式 + OC 已有 gate + Codex 该采取的姿态。

### 16.1 进项目 / 开新 session 的开机 checklist
1. `cat AGENTS.md` (项目硬规则)
2. `cat CLAUDE.md` (针对 Claude Code 的规则,与 AGENTS 重叠但有差异)
3. `cat reports/readiness/readiness.md` (如果存在,看当前可推进哪些 paper)
4. 读本 plan 文档的 §0-§2(战略 invariant)
5. 长任务每 ~30 轮重新打一次 §0.4 + §0.5,对抗 recency bias

### 16.2 写代码前
- `uv run oc capability test` (确认依赖能力可用)
- `uv run oc spec validate <path>` (确认 spec 合法)
- **不要凭训练记忆决定用哪个数据源**——用 `capabilities/registry.yaml` 里实际声明的

### 16.3 长任务 (>5 分钟)
```bash
uv run oc agent request-create \
  --title "<short title>" \
  --prompt "<self-contained prompt>" \
  --task-type research|review|parameter_scan|strategy_optimization \
  --related-path <spec_path>
```
**不要在主对话里 sleep 等结果**。完成后另一个 session 用 `oc agent request-list` 查看。

### 16.4 文件写入
- 路径必须先经 `Path(...).resolve().is_relative_to(root.resolve())` 验证
- 写入字符串字段(JSON/HTML/CLI)前用 `.as_posix()`,**不要 `str(path)`**

### 16.5 LLM feature
- 必须经 `feature_packets.write_feature_packet`,带 `visible_at / published_at / fetched_at / source / input_hash / prompt_hash`
- F2 完成后,paper_auto 路径还要带 `evidence` (single_modality_baseline + marginal_lift + missing_robustness)
- **不要在策略代码里直接 `openai.chat.create`**;走 `review/llm.py` 的 review_signal_with_status

### 16.6 PR 前
- `make verify` 必须全绿。失败先 `uv run oc doctor` 看环境。
- commit message 必须挂 spec_hash / signal_id / signal_log 路径,不是「调整若干」「优化策略」

### 16.7 不确定时
- **不要写下来**虚构的数字。改 prompt 让上游用 `oc agent request-create` 异步去取真实数据,在结果回来前先 stub 出接口
- 引用论文/数据要挂 input_hash / arXiv ID / 报告路径

### 16.8 触线动作
- 出现 `--allow-paper-orders` / `--allow-paper-auto` / 实盘 trading client / 改 `.env` 时**停下并要求人工确认**

### 16.9 ruff 报警
- 别用 `# noqa` 一抹了之;先想是不是 schema 漏了字段
- 全代码库 ruff lint 是干净的,任何新警告都是回归

### 16.10 不重发明轮子
- 写新 capability 前 `cat capabilities/registry.yaml`
- 写新 skill 前 `ls .agents/skills/`
- 加新 CLI 前 `uv run oc --help` 看是否已有

---

## 附录 A: 19 篇论文索引(本计划引用关系)

| Key | arXiv ID | 在本计划中的角色 |
|---|---|---|
| AlphaCrafter | 2605.05580 | 全栈 Multi-Agent 框架的灵感来源,F1/F4 间接引用 |
| TrustTrade | 2603.22567 | Invariant 2(uniform trust);F1 review_card 扩展 |
| BlindTrade | 2603.17692 | **F3** 的核心协议 |
| Expert Investment Teams | 2602.23330 | OC `.agents/skills/` 已实现细粒度,无新 backlog |
| HiveMind | 2512.06432 | **F7** 的核心方法 (DAG-Shapley) |
| OOM-RL | 2604.11477 | Invariant 5 反例(实盘亏损训练 OUT OF SCOPE) |
| SNAPO | 2605.06570 | 不在范围(可微模拟与 Nautilus 冲突) |
| MetaRL-GBWM | 2605.02300 | 不在范围(业务不重合) |
| MACE | 2603.29086 | **F5** 的核心动机(成本模型改变排名) |
| SBCA | 2605.01384 | 不在范围(BERT 主干与 file-first 冲突) |
| FactorEngine | 2603.16365 | F4 间接灵感(程序级因子) |
| Hubble | 2604.09601 | **F4** 的核心方法 (AST 白名单) |
| SEMF | 2603.27321 | 不在范围(频谱特征优先级低) |
| Uni-FinLLM | 2601.02677 | 不在范围(model-first 范式不兼容) |
| History Rhymes | 2511.09754 | **F6** 的核心方法 (宏观检索) |
| Acoustic Camouflage | 2604.14619 | Invariant 3 反例,**F2** 的核心动机 |
| PolyBench | 2604.14199 | Invariant 1 间接证据(LLM 能力评估) |
| QuantCode-Bench | 2604.15151 | **F1** 的 code_correctness_pass 灵感 |
| Reliable Evaluation | 2603.27539 | Invariant 1 的方法论底座(全计划遵循) |

完整笔记见 `docs/quantml-paper-study-research-notes-2026-05-15.zh.md`;原报告见 `reports/quantml_agent_papers_2026-05-14/quantml_agent_paper_study_report.zh.md`。

---

## 附录 B: 当前 Windows 测试失败明细 (P1 验收对照)

P1 完成后,以下 21 个失败用例都应该转绿(在 Windows 上)。如果还有红的,说明 P1 修不全。

**M1 类(路径分隔符,18 个)**:
1. `tests/test_agent_requests.py::test_agent_request_file_lifecycle` — `result_links` 含 `\\`
2. `tests/test_agent_requests.py::test_agent_request_rejects_path_traversal` — Windows 上 `is_absolute()` 语义(L1 修)
3. `tests/test_dashboard_catalog.py::test_dashboard_catalog_rebuilds_repo_artifacts` — readiness_report.path 含 `\\`
4. `tests/test_dashboard_commands.py::test_dashboard_strategy_lifecycle_command_plan_is_bound_to_spec` — cli_args 含 `\\`
5. `tests/test_dashboard_commands.py::test_dashboard_strategy_draft_command_creates_draft_spec`
6. `tests/test_dashboard_commands.py::test_dashboard_strategy_backtest_command_writes_reports`
7. `tests/test_dashboard_commands.py::test_dashboard_strategy_validate_and_capability_commands_write_reports`
8. `tests/test_dashboard_commands.py::test_dashboard_strategy_workflow_verify_runs_core_checks`
9. `tests/test_dashboard_commands.py::test_dashboard_strategy_scan_command_writes_reports`
10. `tests/test_dashboard_commands.py::test_dashboard_sync_commands_are_paper_only_and_write_results`
11. `tests/test_dashboard_commands.py::test_dashboard_system_commands_prepare_workspace_and_refresh_readiness`
12. `tests/test_dashboard_server.py::test_dashboard_server_payloads_expose_health_catalog_and_command_api`
13. `tests/test_deployment.py::test_prepare_workspace_writes_deployment_artifacts`
14. `tests/test_feature_validation.py::test_feature_validate_command_writes_report`
15. `tests/test_feature_validation.py::test_feature_write_command_writes_complete_point_in_time_packet`
16. `tests/test_feature_validation.py::test_feature_from_context_command_writes_replayable_context_features`
17. `tests/test_feature_validation.py::test_backtest_auto_writes_context_feature_packets_for_context_capable_strategy`
18. `tests/test_repo_check.py::test_repo_check_passes_for_repo_control_surface`

**M2 类(NautilusTrader URI,3 个)**:
19. `tests/test_strategy_versions_and_capability_expansion.py::test_nautilus_backtest_plan_is_written_for_nautilus_backend`
20. `tests/test_strategy_versions_and_capability_expansion.py::test_generated_strategy_can_run_real_nautilus_backtest`
21. `tests/test_strategy_versions_and_capability_expansion.py::test_nautilus_backtest_replays_feature_packets_as_custom_data`

---

## 附录 C: 已验证的环境(参考)

审计在以下环境中跑过 P1-P3 之前的状态:
- OS: Windows 11 Home China 10.0.26200
- Python: 3.13.7 (uv 0.11.14 自举)
- Node: v24.11.0 / npm 11.6.1
- 依赖装好后 `.venv` 大小 ~2.3 GB(含 nautilus-trader / pyarrow 等大型 native 包)
- `uv sync` 首次运行约 5-10 分钟

`oc doctor` 应该显示所有可选环境变量为 `missing`(本地审计无 API key),Python 包全 `ok`。

---

*Plan v1, 2026-05-15. 自包含。Codex 可不依赖任何外部上下文执行。完成 P1-P3 后请把本节顶部的「执行者」字段改成你 (Codex / Claude Code) 的具体 model id + 完成日期,作为可追溯标记。*
