# Step 11 执行计划：以模型为核心的策略迭代循环（v1.0，2026-09-06）

日期：`2026-09-06`
作者：Fable 5.1（规划）；执行者：Sonnet（无上下文执行者，本文件自包含）
基线提交：`1815fd0`（Step 10 全部完成，工作树干净）
状态：**待执行**
节奏：用户要求比 Step 10 更快。目标是 **2026-09-12 前**有一个模型排序策略以观察模式接入新的模拟盘账号并每日产出目标权重；之后每周一轮迭代。

---

## 0. 给执行者的前置说明

**先读**：本文件；`reports/research/control/step10-2026-09-04-progress.md`（上一轮账本，Wave 0 建好的数据更新、轻量迭代通道、门槛合同都在里面）；`AGENTS.md`、`CLAUDE.md`（项目规则，但见 §1 的例外声明）。

**环境**（每条 shell 命令都要）：
```bash
export PATH="$HOME/.local/bin:$PATH"
export UV_CACHE_DIR=/tmp/open-composer-uv-cache
```
**每次代码改动后**：`uv run ruff format . && uv run ruff check . && uv run pytest -q -n 2`（并行度上限 `-n 2`）。产品面改动再跑 `uv run oc repo check --strict` 与 `make verify`。

**机器**：6 核 / 3.8GB 内存，无 GPU。DuckDB 设 `memory_limit='2GB'` 并允许落盘。长任务用 nohup 放后台写日志到 `/tmp`，**等它时必须用带 `run_in_background: true` 的 Bash 跑一个会自己退出的循环**（例如 `while pgrep -f "脚本名" >/dev/null; do sleep 30; done; tail -5 日志`），循环退出时会收到通知；等待期间做别的事，绝不以"等通知"为由结束回合（Step 10 的第一个执行者因此空转了一天）。

**接续账本**：`reports/research/control/step11-2026-09-06-progress.md`。每个 Wave 一节：状态（todo/doing/done/blocked_on_user）、命令、产物路径、每个数字的来源、问题。每次会话先读账本再继续。每个 Wave 独立 commit，账本随 commit 入库，commit 信息末尾 `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`，不 push。

**安全边界（不变）**：不读 `.env`（项目权限 deny，含密钥）；任何产物不得含密钥；不提交任何模拟盘订单（下单模式必须用户明确批准后才开）；不动旧账号；不合并 `data/sip-hist/`、`data/sip-delisted/` 进 `data/sip/`；不删 Drive 推送任务。

---

## 1. 目标、原则与对旧框架的例外声明

用户目标不变：尽快找到能接入模拟盘、跑通后接入实盘并开始盈利的策略。用户 2026-09-05/06 的决定：

1. **机器学习是策略设计的第一等公民**，从一开始就和规则一起设计，不是"先找到规则策略再用模型强化"。
2. **不受项目旧框架约束**。旧框架（研究档案、活动合同、角色矩阵、消融清单、"确定性分支证明有信号后才允许 ML"）是基于用户当时的认知和当时 AI 能力做的保守约束，个人量化不需要。**本计划明确豁免**：`AGENTS.md` 第 18、20、21、30、31、37 条对研究阶段不再适用；`CLAUDE.md` 里"新研究轮必须绑定来源卡与预注册清单"对研究阶段不再适用。它们的**目的**（不用未来数据、不过拟合、不被多重检验骗）由 §3 的评估函数在代码里自动保证。产品晋级路径上的档案改为从实验账本自动生成（§5）。
3. 之前"禁改"的文件（`pyproject.toml`、`uv.lock`、`open_composer/models/strategy_spec.py` 等）**可以改**。它们被锁是为了保留已封存活动 `mom_breadth_qd_r1` 的可复现性，那把锁已经被更早的改动破坏，且该活动是历史记录，不再重跑。改动后 `tests/test_mom_breadth_qd_r1.py` 里可能新增哈希漂移类失败：**该文件之外的失败必须为零；该文件内因本计划允许的改动新增的失败，逐条列进账本即可接受**。
4. **规则和模型的分工**：规则负责框架（股票池、调仓频率、持仓数、加权、仓位与波动率上限、硬止损、下单方式、现金/对冲腿），模型负责预测（未来一到四周谁比谁涨得多的排序）。大盘择时默认用一条固定规则，模型版只在样本外打赢固定规则时替换。
5. **迭代逻辑**：想法 → 一个候选配置 → 同一个评估函数 → 自动记进实验账本 → 样本外扣成本后的结果决定去留。基线链 B0→B1→B2→B3（§3.5）每级必须打赢上一级才被采用；"模型必须打赢基线"由此自然成立。
6. **文献与社区**是想法来源，不再是开工前的关卡。

**节奏**：Wave A 两天、Wave B 两天、Wave C 两天，Wave D 见缝插针。总共约一周；上面几条能压缩的地方都压缩，但 §3.4 的三条诚实性要求不压缩。

---

## 2. 现有资产（直接复用，不要重建）

| 资产 | 位置 | 用途 |
|---|---|---|
| SIP 日线与分钟线档案，每日 22:00 UTC 自动增量更新 | `data/sip/`（2016-2026 日线；2023-2026 分钟线）、`data/sip-hist/minute/`（2016-2022 分钟线）、`scripts/update_sip_archive.py` | 全部特征的来源。分钟线两个 root **分别读再拼接**，`load_sip_bars` 接受任意 root |
| 按时点流动性宇宙与横截面面板（DuckDB） | `scripts/evaluate_cross_sectional_momentum_liquid500.py`、`scripts/duckdb_cross_sectional_feasibility.py` | 宇宙构造与 12-1 动量基线的模板（PIT 过滤已修正） |
| 评估框架 | `open_composer/research/kernel/mechanism_eval.py`（`evaluate_candidate`、`rolling_origin_folds`、`effective_independent_trials`，捕获比已改为每期几何平均） | §3.4 的评估函数在它上面包一层 |
| 策略族门槛合同（波动率匹配基准） | `config/promotion/unlevered-family-paper-tier-gates.json` | 裁定用它；`max_drawdown ≥ -0.35`、`sharpe_excess_bil > 1.0`、`cagr_excess_vol_matched_benchmark ≥ 0.05` 等 |
| ML 后端 | `open_composer/research/ml_backend/`（`windows.ml_walk_forward_slices`、`model_factory.create_lightgbm_classifier`、`training.run_rolling_training`、`evaluation.compare_ml_to_baseline`） | 单标的设计，滚动窗口、rank IC、线性基线对比的写法可搬到横截面 |
| 策略规格里的模型段 | `open_composer/models/strategy_spec.py::MLModelConfig`（kind、label、features、training、selection、hyperparameters、baseline） | 新模式的字段尽量挂在它上面 |
| 轻量迭代通道 | `scripts/new_lightweight_iteration.py`、`iteration_dossier.py` 的豁免分支 | 晋级时从账本生成档案 |
| 现有工作台 | `dashboard/`（React + Vite，已构建）、`oc dashboard serve/html/catalog`、`open_composer/models/dashboard.py::DashboardCatalog`（策略、运行、信号、订单、模拟盘持仓、准备度、研究报告等） | Wave D 往里加"实验账本"一节 |
| 模拟盘命令 | `oc paper readiness/status/sync/sync-account/tca-report`，`scripts/run_daily_paper_cycle.py` | Wave C 接入用 |
| 依赖已有 | `lightgbm>=4.5`、`scikit-learn>=1.5` | 主力模型与线性基线 |

已知负结果（不要重复）：Step 10 三个规则族与组合都不过门槛（`strategy-iteration-progress-2026-07-01.md` 的 Step 10 一节）；它们是本轮的对照基线。

---

## 3. Wave A：特征库、评估函数、基线链（第 1-2 天）

### 3.1 依赖

`pyproject.toml` 加 `duckdb`（正式依赖，不再 `--with`）、`quantstats`、`mlflow`（后两者放可选组 `workbench`），`uv lock`。账本记录这是用户允许的改动。

### 3.2 股票池（按时点）

每月末 t：用 ≤ t 的最近 60 个交易日的美元成交额均值排序，取前 **1500**（个人资金小，机构进不去的中小市值恰恰是横截面预测力更强的地方），`close > 5`，剔除 ETF/基金（符号列表用 Alpaca 资产元数据里的 `asset_class`/名称过滤，做不到就用简单规则并记录）。宇宙序列存 `data/features/universe/{year}.parquet`（列：`month_end, symbol, adv_rank`）。全历史并集通常两三千只，后续特征只对并集算。

### 3.3 特征库

新建包 `open_composer/research/features/`，两层存储，全部 parquet、按年分文件、每日增量追加，接在 22:00 UTC cron 的档案更新之后（cron 顺序：档案更新 → 特征追加 → 新鲜度检查）：

1. **分钟线派生的日聚合** `data/features/intraday_daily/{year}.parquet`（每 symbol 每交易日一行）：隔夜收益（今开/昨收−1）、日内收益（收/开−1）、日内已实现波动率（1 分钟收益标准差）、日内振幅（高低差/开）、开盘 30 分钟成交量占比、收盘 30 分钟成交量占比、收盘价相对全天 VWAP 的偏离、日内收益偏度、成交笔数、`|收益|/成交额`（Amihud 日值）。**这是本轮最重的一次性计算**：对 2016-2026 每年、每个分片流式聚合（DuckDB `read_parquet` + `GROUP BY symbol, trade_date`，`memory_limit='2GB'`），只算并集里的 symbol，按年落盘；先启动它再做别的，用等待循环盯。估计数小时。
2. **日线特征** `data/features/daily/{year}.parquet`（每 symbol 每交易日一行，约 40 列）：
   - 收益类：1、5、21、63、126、252 日收益，动量 `ret_252 − ret_21`（跳过最近一月），短期反转 = 5 日收益；
   - 风险类：21、63 日波动率，252 日对 SPY 的 beta，63 日特质波动率，21 日最大单日收益；
   - 流动性类：21 日美元成交额均值及其对 63 日的比值，21 日 Amihud；
   - 位置类：离 252 日最高价的距离；
   - 分钟线派生的滚动：上表每列的 5 日与 21 日均值（隔夜/日内收益拆分、日内波动率、成交量分布、VWAP 偏离、偏度等）；
   - 市场相对：每个收益类特征减去当日宇宙中位数。
   所有特征只用 ≤ t 的数据；所有价格用复权价（档案已是 `adjustment=all`）。
3. **标签**：未来 h 日收益减去当日宇宙中位数（h ∈ {5, 10, 21}），训练时按日期做排名变换（每天转成 0-1 的分位）。禁运期 = h。

单测：一个合成的 3 只股票、40 天的小档案，验证每个特征的定义与"只用过去"（把第 t+1 天的价格改掉，第 t 天的特征不能变）。

### 3.4 评估函数与实验账本（把"诚实"放进代码）

新建 `open_composer/research/kernel/loop.py`：

- `run_experiment(config) -> Verdict`：输入一个候选配置（策略族、框架参数、模型配置、特征集、标签周期、成本），产出**逐日组合收益序列**（长多头版与市场中性版各一条，见 §3.5），交给 `mechanism_eval.evaluate_candidate`（基准 SPY，波动率匹配，新合同）。
- 三条不可压缩的诚实性要求由代码强制：(1) 特征与宇宙按时点（§3.2/3.3 保证）；(2) 逐年扩展窗口的样本外：训练 2016-2017 → 测试 2018，训练 2016-2018 → 测试 2019，…，直到 2026；模型每年重训，超参数在训练窗口的最后一年上选（嵌套），禁运期 = 标签周期；(3) 扣成本，DSR 的试验数**自动**取账本里同一族的实验数，不用人手填。
- 每次运行自动追加 `reports/research/ledger/experiments.jsonl`：实验 id、配置哈希、族、数据窗口、指标、门槛结果、产物路径、时间。同一配置哈希重复运行只记一次。
- 每次运行自动产出 QuantStats HTML 报告 `reports/research/tearsheets/<实验id>.html`（策略 vs SPY：收益、回撤、月度热力图、滚动夏普），并把每次运行记成一个 MLflow run（`reports/research/mlruns/`，本地文件后端；`mlflow ui --backend-store-uri reports/research/mlruns` 就是实验看板）。
- 门槛只看和赚钱直接相关的：样本外扣成本后相对波动率匹配基准的超额 CAGR、Sharpe-ex-BIL、最大回撤、DSR、逐年为正的比例（沿用现有合同的键，不新建合同）。
- 研究阶段**不写**迭代档案、不写来源卡、不走 `iteration validate`；这些只在 §5 晋级时由账本自动生成。

### 3.5 组合框架与基线链

框架固定（本轮不搜索）：周度调仓（周五收盘出信号，下周一开盘竞价 OPG 成交），持有排序前 **K=50** 只、等权，长多头；市场中性版 = 同样多头 + 按 252 日 beta 卖空等额 SPY（Alpaca 可做空 SPY），两版都报；成本 **10 bps/边**，压力 25 bps；周度换手上限不设但要报告。

基线链按序跑并全部记账本（每级必须在样本外扣成本后打赢上一级才被采用）：

- **B0** 宇宙等权（对照）；
- **B1** 单因子：`ret_252 − ret_21` 动量排序取前 K；
- **B2** 线性：岭回归（标准化特征 → 标签分位），按年重训；
- **B3** LightGBM 排序（回归到标签分位，或 `lambdarank`，二选一并记录），按年重训。

Wave A 结束时 B0-B2 必须有结果；B3 在 Wave B。

---

## 4. Wave B：模型候选（第 3-4 天）

- B3 配置网格有界（≤ 12 个）：标签周期 {5, 10, 21} × 树深 {3, 6} × 特征集 {仅日线, 日线+分钟线派生}。其余超参固定（`n_estimators=400, learning_rate=0.03, num_leaves=2^depth−1, min_child_samples=200, feature_fraction=0.7, bagging_fraction=0.7, seed=7`）。每个配置一次 `run_experiment`。
- 选择规则写死：按训练窗口最后一年（验证年）的 rank IC 选，不看测试年。
- 报告：逐年 rank IC、逐年组合收益、换手、容量（每只持仓的成交额占比）、特征重要性前 20、长多头 vs 市场中性；一次**标签打乱的安慰剂**（rank IC 必须≈0，否则管线有泄漏，停下来查）。
- 判定用新合同；同时给出"B3 是否打赢 B1/B2"的直接对比（同窗口、同成本）。B3 打不赢基线是合法结果，如实记录。
- 产出 `reports/research/control/step11-w2-model-ranking-2026-09.md`。

---

## 5. Wave C：产品接入（第 4-6 天）

1. **新的组合模式** `model_ranking_portfolio`（改 `strategy_spec.py` 的 `PortfolioConfig.mode` Literal，加相应字段或复用 `MLModelConfig`）：股票池规则（PIT ADV 前 N）、模型工件路径（joblib）、特征集 id、标签周期、K、调仓频率、加权、对冲腿（`none | spy_beta_hedge`）。spec 里 `data.feed: sip`、`data_assumptions.adjusted: true`、`execution.order_style` 用 OPG 限价。
2. **目标权重映射** `open_composer/adapters/execution/model_ranking_target_weights.py`：读最新特征行（特征库必须是最新交易日，cron 顺序已保证）→ 模型打分 → 前 K 等权（+ 对冲腿）→ 目标权重 JSON；接进 `oc strategy target-weights` 的分派、`router_authorization.py` 与 `paper_readiness.py` 的允许列表、`run_daily_paper_cycle.py`。周度调仓在非调仓日输出"维持"。
3. **晋级路径**：用轻量通道从账本自动生成迭代档案（`new_lightweight_iteration.py` 加一个 `--from-ledger <实验id>` 入口），然后 `oc strategy evidence` → `promotion-report` → `harness plan/verify` → `paper readiness`，每步 blocker 记账本，不绕过；这个模式的回测证据就是账本里的实验产物，`promotion-report` 对该模式做最小适配。
4. **接入模拟盘**：无论是否过门槛，用当时最好的候选（B3 打赢基线就用 B3，否则用链上最好的那一级）以**观察模式**接入新账号，每日产出目标权重与信号日志，不下单；这一步不需要过门槛，因为观察模式没有风险而前向跟踪数据有价值。**下单模式只对过门槛且用户明确批准的候选开启。**
5. **blocked_on_user（第一天就写进账本）**：新模拟盘账号的凭据要用户本人写进 `.env`（`ALPACA_API_KEY_ID`、`ALPACA_API_SECRET_KEY`，`ALPACA_API_BASE_URL` 指向 paper 端点，`ALPACA_PAPER=true`），执行者不能读写该文件；凭据到位前用 `oc paper readiness`/`target-weights` 干跑验证全链路。
6. 每日 cron 顺序最终为：22:00 UTC 档案更新 → 特征追加 → 新鲜度检查；下一交易日开盘前跑每日循环（目标权重 → 信号日志 →（批准后）下单 → 监控）。

---

## 6. Wave D：工作台（并行、低优先，等后台任务时做）

不移植外部平台（Freqtrade/Jesse 面向加密货币，QuantConnect/OpenBB 太重且会替换整个引擎）。用三个现成件：

1. 实验看板 = MLflow UI（§3.4 已把每次实验记成 run）；
2. 每个实验的 QuantStats 报告（§3.4 已产出）；
3. 现有 React 工作台加一节"研究实验"：`DashboardCatalog` 新增 `experiments` 列表（读 `experiments.jsonl`，字段：id、族、窗口、Sharpe、超额 CAGR、门槛通过数、tearsheet 链接），`oc dashboard html` 的静态导出同步显示。模拟盘的持仓、订单、盈亏工作台已有（`paper_positions`、`orders`），加一张"当前候选与最新目标权重"的卡片。

---

## 7. 时间线

| 日 | 内容 |
|---|---|
| 09-06/07 | 3.1 依赖；3.2 宇宙；3.3 分钟线日聚合后台启动；3.4 评估函数与账本；B0/B1 |
| 09-08 | 3.3 日线特征完成；B2；Wave A commit |
| 09-09 | B3 网格与安慰剂；Wave B 报告与 commit |
| 09-10/11 | Wave C：新模式、目标权重映射、晋级路径干跑、观察模式接入（凭据到位即接） |
| 随时 | Wave D |

---

## 8. 完成的定义

1. 特征库两层都在，每日增量挂在 cron 上，单测通过。
2. `run_experiment` + 账本 + tearsheet + MLflow 可用；B0-B3 全部有账本记录与报告；安慰剂通过。
3. `model_ranking_portfolio` 模式能被 `oc strategy target-weights` 与每日循环执行；最好候选以观察模式接入（或账本记录"等待用户凭据"）。
4. 账本完整；`tests/test_mom_breadth_qd_r1.py` 之外的测试全绿；`oc repo check --strict` ok；ruff 全绿。
5. 最终报告：基线链每级的数字、B3 是否打赢基线、候选是否过门槛、接入状态、blocked_on_user、下一周的迭代候选清单。
