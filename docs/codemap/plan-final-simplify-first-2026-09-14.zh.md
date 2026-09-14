# 最终结论与执行计划：先精简、顺手修两处正确性、再小步重构（2026-09-14）

作者：Fable 5.1。合并了 `docs/codemap/evaluation-2026-09-14.zh.md`（Fable，基于代码地图的可达性与导入实测）
与 `docs/codemap/codex-analysis-2026-09-14.zh.md`（Codex，基于代码审阅与测试运行的正确性发现）。
面向无上下文执行代理：每一步都给出文件、动作、验收命令。所有数字取自 `docs/codemap/codemap.json`
（2026-09-14 10:04 UTC 生成）与本日实测，标注"估计"的是预期值。

## 0. 结论

**做精简，不做整体重构。** 顺序：先做两处小的正确性修复（Codex 发现，改动都在十行以内），
然后归档 40.7% 的一次性研究代码并把研究包门面改为惰性导入（Fable 的量化依据），最后才按命令域拆分 CLI。

合并原则：

- Codex 的三条高严重度发现全部采纳，但按用户 2026-09-14 的要求**只做最小修复，不新增任何哈希校验或封印机制**。
- 删什么由代码地图的可达性决定：cron 路径为 0 行、任何入口都不可达 36,829 行、只被 3 个源码文件引用的"按轮次一次性研究模块"整体归档。
- Dashboard 处于暂停状态：代码不动，只把它从 `make verify` 和默认测试里摘出来；一行可选改动让构建产物从 27 MB 降到约 1 MB。
- 不动的东西：StrategySpec 语义、四份门槛合同 JSON、实验账本与 `reports/` 历史、模拟盘安全逻辑、三条 cron、Step 14 运行器。

## 1. 用户约束（2026-09-14）

1. 不必做太多哈希之类的验证。
2. Dashboard 暂时不再继续，可以不管或注释掉；按已有结论做精简也可以。
3. 计划必须给出应用前后的预期差异。
4. 个人使用，目标是质量、效率、性能，以及策略产出与迭代速度。

## 2. 应用前后的预期差异

| 指标 | 现在 | Phase A+B 之后 | Phase C 之后 | 依据 |
|---|---:|---:|---:|---|
| Python 代码行 | 255,516 | ≈149,800（−41%） | ≈125,000（估计） | 归档 103,884 行轮次模块 + 905 行 CLI 命令 + 882 行两份 liquid500 脚本；C 阶段再归档三种路由模式 |
| Python 文件 | 411 | ≈355 | ≈330（估计） | 同上 |
| 测试函数 | 2,279 | ≈1,794 | ≈1,650（估计） | 41 个轮次测试文件里 39 个整体归档，2 个混合文件只删轮次用例 |
| 测试代码行 | 79,067 | ≈56,000（估计） | ≈50,000（估计） | 轮次测试 26,078 行 |
| 默认 pytest 失败数 | 11 基线 + W2 引入的哈希失败 | 0 | 0 | 11 个基线全部在 `tests/test_mom_breadth_qd_r1.py`（归档）；哈希失败由 A3 修复 |
| 全量 pytest 用时 | 约 17 分钟（Codex 实测） | ≤ 11 分钟（估计） | ≤ 9 分钟（估计） | 测试代码行 −30% |
| `oc` 命令数 | 217 | 187 | ≈150（估计） | −30 条 r4–r24 命令；C 阶段再减三种路由模式的命令 |
| `cli.py` | 8,695 行单文件 | ≈7,790 行 | 拆成按命令组的包 | B1、C4 |
| `oc --help` 冷启动 | 5.0 s / 240 MB | ≤ 1 s / ≤ 120 MB（目标，需实测） | 同左 | 5.09 s 花在门面链 `research/__init__` → hybrid 路由 → pdr_ml_gate → sklearn |
| 每次 cron 周期的导入开销 | 同上叠加三次/日 | −4 s、约 −200 MB / 次 | 同左 | 同上 |
| 研究包门面急切导出 | 42 个模块 | 0（惰性） | 0 | A1 |
| 任何入口都不可达的代码 | 39,040 行 | ≈2,200 行 | ≈1,500 行 | 轮次模块 36,829 行归档 |
| 只能经 CLI 到达的代码 | 61,071 行 | ≈31,500 行 | ≈20,000 行（估计） | 轮次 29,512 行归档 |
| `make verify` | 含 npm 构建 Dashboard | 不再构建 Dashboard | 同左 | C2 |
| Dashboard 构建产物 | 27 MB 单个 JS | 不变 | ≈1 MB（若做可选项 C2b） | 构建期内嵌全量 catalog |
| 账本记录 | 无计算口径字段 | 每行带 `calculation_contract` | 同左 | A4，不重算历史 |
| 研究一轮所需治理产物 | campaign 合同 + 迭代档案 | 不变 | 只需账本 + 门槛合同 | C3 |

不会变的：策略回测结果、门槛判定、观察模式 cron 的输出、模拟盘授权与 kill switch 逻辑、`reports/` 与 `signal_logs/` 历史。

## 3. 执行计划

### Phase A：立即可做，不碰 W2 正在改的文件（约半天）

W2（Step 14 通用运行器）的改动仍未提交：`open_composer/cli.py`、`open_composer/models/strategy_spec.py`、
`open_composer/research/bars/hourly.py`、`tests/test_hourly_bars.py` 有修改，`open_composer/execution/`、
`scripts/run_bar_cycle.py`、两个新测试文件未跟踪，最后修改 03:36 UTC。Phase A 只改其他文件。

| # | 动作 | 文件 | 验收 |
|---|---|---|---|
| A1 | 研究包门面惰性化：把 42 组 `from ... import` 改为 `_EXPORTS = {name: module}` 映射 + PEP 562 `__getattr__`/`__dir__`，保留 `__all__`。映射表由现有 import 语句机械生成，不手写 | `open_composer/research/__init__.py` | `uv run python -X importtime -c "import open_composer.research.kernel.loop" 2>&1 \| tail -1` 累计 < 1 s；6 处 `from open_composer.research import X` 仍可用（`grep -rn "from open_composer.research import "`） |
| A2 | 重库延迟导入：sklearn / lightgbm 的模块级导入移入函数 | `open_composer/research/ml_backend/model_factory.py`、`open_composer/research/kernel/lightgbm_rank_strategy.py`；`nautilus_runtime.py` 的 nautilus 导入同样处理 | `uv run python -c "import open_composer.research.ml_backend; import sys; print('sklearn' in sys.modules)"` 输出 False |
| A3 | 哈希最小修复：把 6 个 `event_*` 字段名加入 `_remove_unset_schema_extensions` 的 portfolio 元组。不加新的守卫测试、不加封印 | `open_composer/strategy_versions.py:45` 起 | `uv run pytest tests/test_iteration_dossier.py tests/test_research_campaign.py -q` 通过；若 W2 会话已修则跳过 |
| A4 | 收益口径标签：账本记录新增 `calculation_contract` 字段，值 `portfolio_returns.buy_and_hold_drift.v2`；写一次性脚本给 2026-09-10 提交 30879b4 之前的账本行补 `constant_weight_daily.v1`。只加字段，不重算 | `open_composer/research/kernel/loop.py::_append_ledger`、`open_composer/research/regime/gates.py::append_ledger`、新脚本 `scripts/tag_ledger_calculation_contract.py` | `python3 -c` 读取 `reports/research/ledger/experiments.jsonl` 每行都有该字段 |
| A5 | 归档两份仍用每日固定权重公式的脚本（Step 10 W2 证据已在 reports/research/control）：`scripts/evaluate_cross_sectional_momentum_liquid500.py`、`scripts/duckdb_survivorship_bias_comparison_liquid500.py` | 同 B1 的归档方式 | `uv run ruff check .` 通过 |

### Phase B：W2 提交之后（约 1 天）

| # | 动作 | 范围 | 验收 |
|---|---|---|---|
| B0 | 先让 W2 落地：由其会话提交，或经用户同意后由执行者以独立提交入库 | — | `git status --short` 里没有 W2 的文件 |
| B1 | 归档"按轮次一次性研究模块"：55 个源码文件（`open_composer/research/pit_semantic_theme_*.py`、`*_r<N>*.py`、`scripts/prepare_*.py`、`adapters/data/multiasset_paper_control_r7_snapshot.py`、`adapters/execution/multiasset_*_r*_target_weights.py`）、39 个轮次测试文件、`tests/test_iteration_dossier.py` 与 `tests/test_research_campaign.py` 里导入轮次模块的用例、30 条 `oc strategy *-r4…r24-*` 命令（905 行）、`cli.py` 里只被它们使用的 2 个模块级导入、`scripts/run_r7_forward_observation.py`。归档方式：先建分支 `archive/rounds-2026-09` 指向当前提交，再在工作分支删除；清单写入 `docs/codemap/archive-manifest-2026-09.md`（路径、行数、原用途、恢复命令） | 完整清单以 `docs/codemap/codemap.json` 中 `rounds` 节点的 `files` 与 `tests` 为准 | 见 B3 |
| B1b | `adapters/execution/etf_structural_target_weights.py:23` 导入 `research.etf_structural_r9`：`etf_structural_family` 模式若按 C1 默认归档则一并删除；若用户要保留该模式，则保留 `etf_structural_r9.py` 这一个文件 | — | — |
| B2 | `cli.py` 剩余 26 个模块级 `from open_composer.research ...` 导入移入各命令函数体 | `open_composer/cli.py` | `uv run python -X importtime -c "import open_composer.cli" 2>&1 \| tail -1` 累计 < 1 s |
| B3 | 验收 | — | `uv run ruff format . && uv run ruff check .` 干净；`uv run pytest -q` 0 失败；`time uv run oc --help` < 1 s；三条 cron 命令各跑一次 dry run（`scripts/check_sip_freshness.py`、`scripts/update_sip_archive.py --kind daily --dry-run` 若支持、`scripts/run_daily_paper_cycle.py --strategy us_recent_high_return_top50 --spec strategy_specs/drafts/us_recent_high_return_top50.yaml`）状态 ok；重建代码地图 `uv run python scripts/build_codemap.py && uv run python scripts/build_codemap.py --verify`，`rounds` 节点行数 < 1,000 |

### Phase C：看完 B 的结果后决定（约 1 天）

| # | 动作 | 说明 |
|---|---|---|
| C1 | 路由族取舍 | `portfolio.mode` 九种。默认保留：`single_symbol`、`model_ranking_portfolio`（两条 cron 在用）、`event_driven_capacity_book`（W2）、`beta_exposure_router`、`core_beta_satellite_router`（Step 10 F1/F2，产品可执行）、`cross_sectional_momentum`（168 份草稿）。冻结保留：`hybrid_adaptive_router`（approved 里两份 TQQQ spec 仍指向它，用户 09-03 已退役该策略但文件仍在 approved/）。默认归档：`adaptive_intraday_internal_router`（3 份草稿）、`momentum_signal_router`（1 份）、`etf_structural_family`（5 份），连同 `routers` 节点中只服务它们的模块与 56 条路由命令中的对应部分 |
| C2 | Dashboard 冻结 | `Makefile` 的 `verify` 去掉 `dashboard-check`；`tests/` 里涉及 Dashboard 的测试文件（`grep -li dashboard tests/test_*.py` 计 15 个）加 `@pytest.mark.dashboard` 并默认跳过（conftest 已有 slow 的同类机制）；README 标注"Dashboard 暂停维护"。可选 C2b：`dashboard/vite.config.ts` 的 `dashboardCatalogResolver` 默认输出空 catalog，改由现有 15 秒轮询接口加载，构建产物 27 MB → 约 1 MB |
| C3 | 治理减负 | 研究阶段不再要求 campaign 合同与迭代档案：`require_iteration_execution_gate` 只对 `lifecycle != draft`、`paper_auto`、`broker != none` 生效，去掉 `model is not None` 这一条；保留 `config/promotion/*.json` 门槛合同、账本、知识索引；`oc research campaign/iteration/knowledge` 三个命令组保留但从 README 主路径移除。不新增任何哈希校验 |
| C4 | `cli.py` 按命令组拆分为 `open_composer/cli/` 包（每组一个文件，`oc` 入口不变，命令内惰性导入） | 在 B 之后做，避免拆分即将删除的命令 |
| C5 | 草稿清理（运行时文件，非代码） | `strategy_specs/drafts/` 里 2026-07-01 之前的自动草稿移到 `strategy_specs/archived/`，Dashboard 与 `oc strategy list` 不再被 500 多份旧草稿淹没 |

## 4. 明确不做的事

- 不改门槛合同数值、不改 StrategySpec 字段语义、不改模拟盘授权与 kill switch 逻辑。
- 不新增哈希守卫、封印或 lock 类机制；现有的只做 A3 那一处最小修复。
- 不重跑历史账本；不做 Dashboard 新功能；不引入新的抽象层。
- 不在归档的同时调整任何策略参数。

## 5. 需要用户拍板的事项（括号内为默认）

1. 归档方式（默认：git 分支 `archive/rounds-2026-09` 保留历史，工作分支删除；备选：移到仓库内 `archive/` 目录，不进 import 路径）。
2. C1 的路由族保留集合（默认如上表）。
3. approved 里两份 TQQQ hybrid 路由 spec 是否移到 retired（默认：不动文件）。
4. W2 的未提交改动由谁提交（默认：等其会话提交；若两小时内没有动静，执行者跑通其两个测试文件后作为独立提交入库）。
5. Dashboard 可选项 C2b 做不做（默认：做，一行改动，可回退）。
6. 执行方式（默认：批准后 Fable 直接执行 Phase A，W2 落地后执行 Phase B，每个阶段一个提交并附前后对照表；Phase C 等你看完 B 的对照表再决定）。

## 6. 风险与对策

- W2 未提交改动与 B1/B2 都改 `cli.py`：B 严格排在 W2 之后，A 不碰该文件。
- 动态导入（`importlib`）与字符串引用不在导入图里：归档后以全量 pytest、`oc --help`、三条 cron dry run 作为兜底；发现遗漏就从归档分支取回单个文件。
- 归档会让 `reports/forward/us_pit_semantic_theme_r*` 等历史观察目录失去生成代码：目录保留，只是不可再生成；清单里注明。
- 门面惰性化后若某处依赖导入副作用（注册表、猴子补丁）会静默失效：A1 验收包含全量 pytest。
- 3.8 GB 内存机器：全量 pytest 与 npm 构建不要并行；执行者一次只跑一个重任务。

## 7. 补充（2026-09-14 执行中，回答"归档的轮次模块还有没有意义"）

**结论：有意义的是结论和少数机制，不是代码。** 55 个轮次文件没有一个带模块文档字符串；每轮的假设、数据、结果和决策都在
`reports/research/iterations/<iteration>/decision-record.md`（51 份档案，47 份是轮次），前瞻观察数据在 `reports/forward/`（5 个轮次）。
这些目录全部保留，归档只删可执行代码。

已经做了、不必重复的部分：

- 通用机制已经替代了"每轮复制一份 2,000 行模块"的模式：研究内核 `run_experiment`（特征集 × 模型种类 × 门槛合同 × 账本）、
  regime 门槛、Step 14 W2 的通用 bar 周期运行器。一个新假设现在是一条配置加一次预注册，不是一个新模块。
- 负结果记忆已有载体：`oc research knowledge build` 从决策记录生成 `reports/research/knowledge/index.json` 的 `empirical_memory`，
  自动研究的 memory packet 在 `reports/research/control/*-memory.md`。
- 轮次里"语义主题"这条线（r4–r24，约 48k 行，占归档量近一半）的想法是"按时点事件特征 → 路线/仓位决策"。
  它的继任实现已经存在于路线图 W3/W4：685k 篇新闻的 PIT 包、`research/news/extract.py` 的 LLM 事件抽取。
  从 r24 的结构看（路线切换、USD 压力、压力恢复、政策价值回归），代码本身是 ETF 路线策略模型，不是通用的新闻特征库。

没做、现在加入计划：

| # | 动作 | 说明 |
|---|---|---|
| B1c | 轮次结论登记表（归档前生成） | 从 51 份决策记录与账本生成一张表：轮次 → 假设 → 数据 → 结果 → 决策 → 可复用件，写入 `docs/codemap/rounds-outcome-register-2026-09.md`；同时重建知识索引并确认 `empirical_memory` 非空，让自动研究与 LLM 起草读得到"已证伪方向" |
| C6 | 机制抽取（按需，每项半天到一天，需要用户逐项点头） | 候选：(1) r24 的路线切换/政策价值回归 → 内核的 regime 模型种类；(2) multimodal r4–r6 的 scipy 权重优化 → 内核组合层的权重方法；(3) vix_term_structure_overlay_r1 的 VIX 期限结构过滤 → regime 特征；(4) high_beta_sleeve_ensemble_r1 的集成校准 → W4m 方法网格；(5) mom_breadth_qd_r1 的广度因子 → 特征集。原则：只搬机制，不搬轮次参数；进内核后以预注册 + 账本重跑一次 |
| 不抽取 | `scripts/prepare_pit_semantic_theme_r*.py`（13 份、17.8k 行）与 `multiasset_paper_control_r7*` | 前者的 event-features 只服务各自轮次，后者是已结束的模拟盘对照组 |
