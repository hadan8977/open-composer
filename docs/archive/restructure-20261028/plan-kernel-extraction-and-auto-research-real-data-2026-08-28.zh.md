# 研究内核化与自动循环接入真实数据执行计划（工作项 E / F）

日期：`2026-08-28`
计划版本：`1.0`
基线提交：`a38c349`
执行者：无上下文执行者（Sonnet）
状态：待执行
前置计划：`docs/plan-gate-recalibration-and-research-velocity-2026-08-26.zh.md`（门槛重校准，已完成 D/A/B/C）

---

## 0. 给执行者的前置说明

你不需要读历史文档。本文件自包含。前置计划里的 A/B/C/D 已经完成并提交，本计划只做剩下的 E 和 F。

**这个仓库是什么**：Open Composer，个人 AI 量化策略研究工作台。`StrategySpec`（YAML）是策略行为的唯一事实来源，研究产物写到 `reports/`。

**环境准备**（每条 shell 命令都要）：
```bash
export PATH="$HOME/.local/bin:$PATH"
export UV_CACHE_DIR=/tmp/open-composer-uv-cache
```

**每次代码改动后必须跑**：
```bash
uv run ruff format .
uv run ruff check .
uv run pytest -q                      # 默认已自动跳过 slow 测试，约 7 分钟
```
产品面改动还要跑 `uv run oc repo check --strict`。

**机器约束（重要）**：6 核 / 3.8GB 内存。
- **绝对不要用 `pytest -n auto`**，会 OOM 把机器跑死（本周已发生过一次）。并行上限 `-n 2`。
- 全量套件（含 slow）用 `make test-full` 或 `uv run pytest --runslow`，约 30-50 分钟。

---

## 1. 全局禁改文件清单（最重要的约束，先读这个）

仓库里有 7 个已封存 campaign（`mom_breadth_*`）的 `phase-one-preregistration-lock.json`，
用 SHA-256 **硬绑定**了下面这些文件。**改动其中任何一个都会让锁校验失败，
连带打挂 `tests/test_mom_breadth_qd_r1.py`。**

```
capabilities/registry.yaml
open_composer/market_calendar.py
open_composer/models/strategy_spec.py
open_composer/research/campaign_statistics.py
open_composer/research/iteration_dossier.py
open_composer/research/quality_diversity.py
open_composer/storage.py
pyproject.toml
uv.lock
open_composer/research/mom_breadth_qd_r1.py
tests/test_mom_breadth_qd_r1.py
scripts/prepare_mom_breadth_qd_r1.py
strategy_specs/drafts/us_breadth_*.yaml   （全部 16 个）
```

**规则：这些文件只能 import / 读取，不能修改。** 如果你觉得非改不可，
停下来先在报告里说明，不要自行修改。

`open_composer/research/campaign.py` 也在锁里，但前置计划已经为它建立了
`GATE_RECALIBRATION_DRIFT_BLOCKERS` 授权修正条目（见 `mom_breadth_qd_r1.py:224` 附近），
所以改它是被授权的、不会产生新的失败。

**本计划要改的文件都不在锁里**，已核实：
`open_composer/research/kernel/*`、`open_composer/research/pit_semantic_theme_r17.py`、
`r18.py`、`open_composer/research/auto_research.py`、对应测试文件 —— 全部安全。

### 1.1 已知的既有失败（不是你造成的，不要试图修）

`tests/test_mom_breadth_qd_r1.py` 当前有 **11 个测试失败**，全仓其他文件零失败。
原因：那个已封存 campaign 的预注册树内容派生自一份合同，而门槛重校准必须修改该合同的
schema，导致派生树无法在"不伪造预注册历史"的前提下自洽。这是已记录的遗留问题
（前置计划 §9.3），**与 E/F 无关，不在本计划范围内，也不要尝试修复它**。

判断标准：跑完测试后，失败数应当**仍然是 11 个且全部来自 `test_mom_breadth_qd_r1.py`**。
只要出现第 12 个失败或其他文件失败，就是你引入的回归。

---

## 2. 工作项 E：研究内核化（试点）

### 2.1 为什么做

`open_composer/research/` 有 135 个模块、134,288 行，其中 **36 个是按轮次命名的一次性模块，
共 73,991 行 = 55%**。每加一轮研究就复制粘贴约 1650 行模块 + 600 行测试，永久留在仓库和 CI 里。
这是迭代慢、测试慢、维护重的共同根因。

### 2.2 实测事实（已核实，不要重新调查）

试点对象 `pit_semantic_theme_r17.py` 与 `r18.py`：

| 项 | 数值 |
|---|---:|
| 各自行数 | 1657 / 1657 |
| 函数+类数量 | 36 / 36（归一化后名单**完全一致**） |
| 归一化后真实差异 | **64 行 / 1658 = 3.9%** |
| 逐字节相同的函数 | **26 个，783 行** |
| 有差异的函数 | 10 个，且多数只差 2-6 行 |
| 对应测试 | 401 / 403 行，归一化后只差 **8 行** |

**全部实质差异就是把 leadership 标的从 `SOXL` 换成 `USD`**，外加一个
`EFFECTIVE_TRIAL_COUNT`（8086 → 8094，这个常量已被前置计划的 A1 淘汰，
DSR 不再使用终身累计计数）。差异分布：

```
28 行  build_rNN_feature_dataset      <- 特征名 soxl_* -> usd_*
12 行  <module>                        <- LEADERSHIP_WEIGHTS / 特征名常量 / EFFECTIVE_TRIAL_COUNT
 6 行  _model_comparison
 4 行  build_segment_targets
 2 行  其余 7 个函数各 2 行
```

逐字节相同的 26 个函数（内核候选，共 783 行）：
```
RNNFreezeResult  RNNEvaluationResult  FittedRouteModel  SegmentTargets
_stress_recovery_contract   freeze_pit_semantic_theme_rNN(105行)
load_and_validate_rNN_specs  load_rNN_price_panel(70行)  development_folds(34行)
_preflight(49行)  _ConstantProbabilityModel  _rNN_frame_hash(32行)
_target_weights  _leadership_target  _stress_route_for_row  _predict_probability
_validate_target_frame  run_pit_semantic_theme_rNN(205行)  _record_evaluation_paths
_evaluate_folds(41行)  _trial_rows(27行)  _fitted_model_hash  _gate
_write_jsonl  _render_markdown(33行)  _write_forensics(47行)
```

### 2.3 要做什么

**范围严格限定在 r17 / r18 两个模块。不要碰其余 34 个轮次模块。**

1. 把上述 26 个逐字节相同的函数抽到 `open_composer/research/kernel/` 下的新模块
   （建议 `open_composer/research/kernel/semantic_theme.py`，或按职责拆成
   `panel.py` / `folds.py` / `evaluation.py` / `reporting.py`，你判断哪种更清晰）。
2. 对那 10 个"只差几行"的函数，把差异部分参数化（leadership 标的、特征名前缀），
   同样抽进内核。目标是让轮次模块只保留**真正的研究差异**。
3. 把 `pit_semantic_theme_r17.py` / `r18.py` 改成薄封装：只声明该轮的配置
   （leadership 标的、特征名、常量）并调用内核。
4. 同样处理两个测试文件（它们只差 8 行）：抽出共享断言，参数化轮次。

### 2.4 硬性约束

- **这是纯重构，不是行为变更。** 现有测试的断言值**一个都不许改**。
  如果你想改某个断言，说明重构错了，回去改实现。
- `EFFECTIVE_TRIAL_COUNT` 保留为轮次常量（历史记录），但不要让它进入任何
  DSR 计算路径——前置计划 A1 已经把 DSR 的试验计数改成族内口径、上限 32。
- 不要修改 §1 禁改清单里的任何文件。

### 2.5 验收标准

```bash
uv run pytest -q tests/test_pit_semantic_theme_r17.py tests/test_pit_semantic_theme_r18.py
# 必须全绿，且断言值零改动
uv run pytest -q      # 失败数仍为 11 且全部来自 test_mom_breadth_qd_r1.py
uv run ruff check .   # 全绿
```
- `pit_semantic_theme_r17.py` + `r18.py` 合计行数从 **3314 降到 800 以下**。
- 新增 `open_composer/research/kernel/README.md`，说明抽出的内核接口，
  让后续轮次能直接基于它写（而不是继续复制粘贴）。

### 2.6 完成后的后续（记录，本次不做）

家族内两两归一化差异率实测：相邻轮次 12-15%，跨度大的（r14 vs r22）28%。
所以 r17/r18 是最相似的一对、最适合试点；把内核推广到 r14-r24 全家族是
下一步的独立工作，**本次不要做**。

---

## 3. 工作项 F：自动循环接入真实数据

### 3.1 为什么做

`open_composer/research/auto_research.py:132` 硬性拒绝任何非 sample 数据源：

```python
if data_source != "sample":
    raise ValueError(
        "market-data auto research requires a preregistered iteration workflow; "
        "use sample data for workflow-only smoke")
```

后果（187 份 auto memo 实测）：156/187（83%）跑在 2.5KB 的 sample CSV 上，
170/187（91%）卡在同一个 `promotion:strict_data` blocker，
**268 轮 auto 目录产出可晋级候选 0 个**。而 `data/cache/` 里有 371MB 真实数据。
自动化火力全部打在一条按设计不可能赢的路上。

### 3.2 实测事实（已核实，不要重新调查）

- `auto_research.py` **不在禁改清单里**，可以改。
- 能力注册表里**只有 `market.alpaca_bars`** 同时满足 `status=approved` 且
  `paper_ready_timeframes` 非空（`['1m','5m','15m','30m','1h','4h','daily','weekly']`）。
  用 `open_composer.capabilities.load_registry()` / `get_capability()` 在**运行时读取**，
  不要把 `"alpaca_bars"` 硬编码成特例字符串。`capabilities/registry.yaml` 在禁改清单里。
- `auto_research.py:1363` 的 `_check_data_source_available()` **已经**校验了
  Alpaca 凭证是否配置，可直接复用。
- 「预注册迭代」的既有概念在 `open_composer/research/iteration_dossier.py:287`
  的 `require_iteration_execution_gate()`。**该文件在禁改清单里 —— 只能 import 调用，不能改。**

### 3.3 一个必须先解决的设计接缝

`run_auto_research()` 的签名是 `(thesis, universe, ...)` —— 它**不从已有 spec 出发，
而是自己生成 draft**。而前置计划 A1 实现的族内计数器
`family_effective_trial_count_from_ledger(contract, ledger)`（在 `campaign.py`，
上限 `MAX_FAMILY_EFFECTIVE_TRIAL_COUNT = 32`）需要一份 campaign contract + allocation ledger，
auto_research 两者都没有。

**因此不要硬套 campaign 级计数器。** 建议方案：
- 给 `run_auto_research()` 增加一个显式的 `iter_id: str | None = None` 参数。
- 真实数据路径要求 `iter_id` 必填，并用 `require_iteration_execution_gate()`
  或 `validate_iteration_dossier()` 校验该迭代确实已预注册。
- 计数落在**迭代级**：`open_composer/research/kernel/trials.py` 的 `TrialLedger`
  已经有 `family` 和 `max_candidates` 字段，是天然的落点，且 kernel 不在禁改清单里。
- 上限沿用 `MAX_FAMILY_EFFECTIVE_TRIAL_COUNT`（从 `campaign.py` import，不要重新定义 32）。

如果你在实现中发现更合理的接法，可以调整，但必须在报告里说明理由，
并且**不能新造第二套平行的计数机制**。

### 3.4 要做什么

改 `run_auto_research()` 的准入逻辑：

**允许真实数据源**，当且仅当同时满足：
1. 调用方显式传入了 `iter_id`，且该迭代已预注册（用 iteration_dossier 的只读 API 校验）；
2. 该 `data_source` 对应的能力在 registry 里 `status == "approved"` 且
   `paper_ready_timeframes` 非空（运行时读取，不硬编码）；
3. `_check_data_source_available()` 通过（凭证已配置）。

**否则**保持现有行为完全不变：只允许 sample，走原有回退路径。

**计数与封存**：每一次真实数据运行都要计入该迭代的族内计数。
达到 `MAX_FAMILY_EFFECTIVE_TRIAL_COUNT`（32）时，必须**拒绝继续运行**并给出清晰错误，
要求调用方封存该族、另开独立机制。这是新体系纪律的核心 ——
自动化跑得越多，N 涨得越快，DSR 惩罚越重，所以自动循环必须受候选预算约束。

**draft 标记**：现有代码在 `auto_research.py:749` 与 `:938` 附近有
`"workflow_only_ungated_draft": data_source == "sample"`。走真实数据路径时
它自然会变成 `False`，这是正确的（意味着下游执行会受迭代门约束）。确认这个行为，
不要绕过它。

### 3.5 验收标准

新增测试（建议放 `tests/test_auto_research_real_data_gate.py`）：
1. 未传 `iter_id` 而请求真实数据源 → 仍然抛出原来的错误，行为不变；
2. 传了未预注册的 `iter_id` → 拒绝；
3. 传了已预注册的 `iter_id` + `market.alpaca_bars` → 正常运行，且族内计数正确 +1；
4. 该族计数已达 32 → 拒绝继续，错误信息明确要求封存；
5. 某能力 `status != approved` 或 `paper_ready_timeframes` 为空 → 拒绝
   （构造一个 fixture 能力来测，**不要修改 `capabilities/registry.yaml`**）。

回归验证：
```bash
uv run pytest -q tests/test_auto_research_ic_diagnostics.py \
                 tests/test_auto_research_selection.py \
                 tests/test_auto_research_signal_generation.py \
                 tests/test_factor_catalog_and_auto_research.py \
                 tests/test_auto_research_real_data_gate.py
uv run pytest -q   # 失败数仍为 11 且全部来自 test_mom_breadth_qd_r1.py
```

**注意**：本机可能没有配置 Alpaca 凭证，所以第 3 条测试要 monkeypatch
`_check_data_source_available` 或凭证读取，**不要真的去打网络请求**。

---

## 4. 执行顺序

E 和 F 互不依赖，可以任意顺序或并行。建议先 F（改动面小、直接解开自动循环的死结），
再 E（改动面大）。

每完成一项：跑验收标准 → `ruff` → `pytest` → commit。**不要把 E 和 F 混在一个 commit 里。**

## 5. 禁止事项

1. **不要用 `pytest -n auto`**（会 OOM）。上限 `-n 2`。
2. **不要修改 §1 禁改清单里的任何文件。**
3. **不要尝试修复 `test_mom_breadth_qd_r1.py` 的 11 个既有失败**（§1.1），
   也不要修改 `reports/research/iterations/mom_breadth_*/` 或
   `reports/research/campaigns/mom_breadth_qd_r1/` 下的任何文件 —— 那棵树很脆，
   批量改写会造成比原问题更大的不一致（前置计划 §9.6 有教训记录）。
4. **E 是纯重构**：不许改任何现有测试的断言值。
5. **不要新造第二套试验计数机制**（§3.3）。
6. 不要在测试里发真实网络请求。
7. 不要碰 `.env`、券商密钥或任何凭证。
8. 不要把 sample / fixture / cache-fallback 数据描述成 paper-ready 证据。

## 6. 完成的定义

1. `uv run pytest -q` 失败数**仍为 11 且全部来自 `test_mom_breadth_qd_r1.py`**；
   `uv run ruff check .` 全绿；`uv run oc repo check --strict` 为 `status=ok`。
2. E：r17+r18 合计 < 800 行，两个测试文件全绿且断言零改动，内核有 README。
3. F：五条新测试全绿，真实数据路径受"已预注册 + 能力 approved + 族内计数 ≤32"三重约束。
4. 两项分别独立 commit，commit message 说明做了什么、以及任何偏离本计划的地方和理由。
