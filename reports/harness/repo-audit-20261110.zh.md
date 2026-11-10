# 代码仓库体检 + 代码地图 + 项目评估 · 2026-11-10

## 1. 方法与参考

- **既有工具**：`scripts/build_codemap.py` 是本项目自带的代码地图生成器（`docs/codemap/codemap.json|html|lock`，含 19 个首屏节点、依赖边、5 条端到端流程、逐节点测试与指纹锁）。先跑 `--verify`：**FAIL（290 个问题）**——行号锚点全部漂移、lock 过期。重建后 `--verify` **PASS**（19 节点 / 195 边 / 5 流程 / 931 文件 / 17 节点指纹）。
- **基线参考**：`docs/codemap/evaluation-2026-09-14.zh.md`（上一次基于地图的评估，提出"精简优先 + 三处局部重构"）、`docs/handoff-2026-10-28-restructure.md`（当前结构权威）、`docs/current-view.zh.md`。
- **本次新增度量**：census（按目录数文件/行）、import 耗时与内存、git 卫生、运维面、测试面。数字均为 2026-11-10T05:5x UTC 快照。

## 2. 代码地图（重建后）

| 节点 | 文件 | 行 | 最近提交 | 职责（摘要） |
|---|---:|---:|---|---|
| scripts | 402 | 194,786 | 11-04 | 数据归档/特征/筛选/网格/每日观察周期；研究内核最大的实际调用方 |
| cli | 194 | 71,863 | 11-03 | `oc` 入口（28 命令组，单文件 8.7k 行）、项目文件、repo check、部署就绪度 |
| routers | 71 | 35,413 | 11-03 | 2026-05~08 产品内置策略族（混合/贝塔/核心卫星/择时/杠杆） |
| governance | 32 | 18,912 | 09-22 | campaign 合同、迭代档案、晋级报告、证据托管 |
| paper | 21 | 13,730 | 10-28 | Alpaca Paper 唯一写路径：授权/就绪/kill switch/窗口/新鲜度/TCA/漂移/锁 |
| features | 35 | 12,249 | 10-14 | 日频/日内特征、Alpha158/101/191、OSAP、PIT 宇宙与标签 |
| kernel | 44 | 11,739 | 09-19 | PIT 宇宙、逐年扩展前推、成本后收益、DSR、git 封印门槛 |
| execution | 21 | 9,621 | 10-28 | 各组合模式目标权重、整股化、执行策略、Nautilus 平价 |
| autollm | 23 | 9,560 | 09-10 | `oc research auto` 论点→草稿 Spec、LLM 评审卡、新闻 PIT |
| data | 19 | 6,669 | 10-28 | 行情/事件/宏观抓取与回退清单 |
| spec | 20 | 4,299 | 09-30 | StrategySpec 唯一事实来源（pydantic extra=forbid） |
| ml | 12 | 4,113 | 09-14 | LightGBM/sklearn 后端、路由 ML 门 |
| engines | 17 | 4,010 | 10-28 | 确定性参考回测、信号/扫描、绩效与执行现实分析 |
| rounds | 4 | 2,556 | 10-14 | 以轮次命名的模块（多数已归档） |
| dsl | 10 | 1,846 | 09-30 | 受限 AST 表达式、指标函数、Spec→Pine/Python |
| shared | 6 | 378 | 09-19 | .env/路径/JSON/时间；零内部依赖 |
| store_data / store_artifacts / external | — | — | — | 数据与产物存储、外部服务（Alpaca/Longbridge/SEC/FRE） |

地图给出的可达性（其统计口径）：Python 909 文件 / 400,495 行；测试 479 文件 / 5,206 个函数 / 137,076 行；不可达 125 文件 / 23,251 行；仅 CLI 可达 59,997 行；cron 可达 54,649 行；门面 `research/__init__` 被 333 个文件导入。

## 3. 体检结果

**规模（我自己的 census，含未跟踪）**

| 目录 | py 文件 | 行 |
|---|---:|---:|
| open_composer | 526 | 205,782 |
| scripts | 416 | 202,283 |
| tests | 479 | 137,076 |
| **research（各轮运行产物）** | **4,960** | **1,804,078** |
| 合计 | 6,384 | 2,349,736 |

`git ls-files '*.py'` 只有 1,377 个文件 → **约 5,000 个 py 文件是未跟踪的研究运行产物**，占全部 Python 行的 **77%**。其中 `research/martin_funded_continuation_20261103` 一个目录就 3,956 文件 / 1.58M 行（每轮把 `open_composer/`、`scripts/` 复制进 `code-stage/`）。这不是死代码（审计需要原件），但它解释了"行数暴涨"和仓库体积。

**性能（本机实测）**

| 项 | 数值 |
|---|---|
| `oc --help` | **5.73 s / 142 MB** |
| `import open_composer.cli` | 6.18 s / 135 MB |
| `import open_composer.research.kernel.loop` | 2.54 s / 121 MB |

与 2026-09-14 的 5.0 s / 240 MB 相比：时间略差、内存下降。**结论未变：每条 `oc` 命令仍要付 5-6 秒导入成本**，主因仍是 `research/__init__` 门面（333 个文件导入它）。

**Git 卫生**

| 项 | 数值 |
|---|---|
| 未推送提交 | **896**（`@{upstream}..HEAD`） |
| 未跟踪文件 | 1,343（约 **12 GB**，其中 research 4.3G、reports/research 9.4G） |
| 已修改 | 140 |
| 类型变更（t 型）| **56**——2026-11-03 磁盘救援把跟踪文件换成了指向 `/mnt/gdrive` 的符号链接 |
| 删除 | 3（`.agents/skills/ultracode-reviewer`、`.claude/...`、一个前端 hash 资源） |
| `.git` | 172 MB |

**运维面**：6 个常驻服务（quant cockpit、six-paper、memory-governor、cloudflared-quant、hadan-ingress/proxy）；29 条有效 cron；磁盘 53%（99 G 可用）；内存 748 MB 可用（3.9 G 总量）。

**测试面**：479 文件 / 5,206 函数 / 137k 行。今天针对性跑过 `test_intraday_runner`、`test_book_paper`、`test_paper_tca`、三个 `six-paper` 用例、`test_paper_formation_continuity`、`test_dated_refresh_exec_recovery`：其中 `test_unsupported_month_or_missed_formation_is_not_K0` 在**提交版本**上即失败（测试要求"未支持月份"在调用 `feature_input` 之前拒绝，代码先算支撑），属既有口径差异。

## 4. 评估（按风险排序）

**P0 — 会直接造成经济损失或静默停摆**
1. `hold` 不收敛（见 `reports/ops/paper-automation-20261110.zh.md` 第 3 节）：已造成 BASE 4 个交易日、H5 7 个交易日未按目标持仓；今天做了止血，根治待评审。
2. 56 个 t 型符号链接：任何被回执绑定的输入一旦被"搬到 gdrive + 留链接"，`Path.resolve()` 会让绑定失败并 fail-closed（11-05..09 的 H5 拒单就是这么来的）。`scripts/check_bound_inputs.py` 已能扫出来，建议并入每日检查；同时让磁盘清理流程不要动被回执绑定的路径。
3. 12 GB 未跟踪产物 + 896 个未推送提交：既没有异地备份（gdrive 备份跑的是另一个目录），也让"上传最新版本到 GitHub"这件事无法一把梭（一次提交 12 GB 不可行）。

**P1 — 效率与可维护性**
4. `oc` 5.7 秒冷启动：门面 `research/__init__` 再导出 42 个模块，333 个文件导入它。建议按 `docs/codemap/plan-final-simplify-first-2026-09-14.zh.md` 的路线做**懒加载门面**（`__getattr__` 转发），目标 <1.5 秒。
5. `cli.py` 单文件 71,863 行 / 28 个命令组：新增命令的成本与冲突概率都高。建议把 28 组按域拆成 `open_composer/cli/*.py` 并用 Typer `add_typer` 组装（不改任何命令名）。
6. scripts 402 文件 / 194,786 行，是研究内核最大的调用方，但缺少目录级 README 与"哪些是每日在跑、哪些是一次性"的索引（cron 只用其中 7 个入口）。

**P2 — 卫生**
7. 3 个删除未提交（含 `.agents/skills/ultracode-reviewer`）：若是刻意移除要提交，若是误删要恢复——现在两边都不确定。
8. `research/` 与 `reports/research` 的体积（13.7 GB）与 77% 的 Python 行数：建议区分"冻结证据（保留）"与"可重跑产物（只留 manifest + 摘要）"。
9. 6 条常驻服务中有 3 条（hadan-*、cloudflared）与量化无关，缺一张"这台机器上跑什么、谁负责"的一页清单。

## 5. 与 2026-09-14 评估的对照

| 当时的建议 | 现在 |
|---|---|
| 精简优先，归档一次性轮次模块 | **未执行**：`routers` 35,413 行仍在，`rounds` 2,556 行仍在；新增 4.3 GB 运行产物 |
| `research` 门面改懒加载（性能） | 未做：`oc` 仍 5.7 s |
| 拆 `cli.py` | 未做：71,863 行（当时 8.7k 行单文件的核心逻辑之外又长了） |
| 回测主路径的迭代闸门提速 | 未复核（本次未跑回测主路径基准） |

也就是说：**过去两个月项目的增量主要在研究产物与证据上，产品代码的核心结构问题没有动**。这不一定是错的（研究优先），但代价已经具体化：冷启动 5.7 s、单文件 7.2 万行、12 GB 未跟踪、896 未推送。

## 6. 建议的下一步（按投入产出排序）

1. **先解决可备份性**（半天）：把 896 个提交推上去；`research/`、`reports/research` 用 manifest + 摘要入库，正文留本地/gdrive；这样"上传最新版本"才有意义。
2. **`hold` 根治按 B→A 两步灰度**（见自动化报告第 3 节）。
3. **`research/__init__` 懒加载**（1-2 天）：单点改动能把 `oc` 从 5.7 s 降到 ~1.5 s，所有命令受益。
4. **把 `check_bound_inputs.py` 并入每日检查**（半小时）。
5. `cli.py` 拆分与研究产物归档（1-2 周，可延后）。
