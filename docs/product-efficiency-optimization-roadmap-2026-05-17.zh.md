# Open Composer 产品强化计划：Dashboard、策略工作流与研究共享内核

日期：2026-05-17

## 结论

Open Composer 当前已经具备个人 AI 策略工作台的骨架：`StrategySpec`、能力注册表、确定性 Python 回测、promotion/readiness、Factor Lab、Execution Reality、StrategyDAG、Dashboard catalog 和远程 BFF/daemon 都已经存在。但它仍然更像一个 MVP，主要问题不是“缺一个大功能”，而是三类产品能力还没有形成统一内核：

1. Dashboard 还是产物浏览和受控命令面，没有成为研究决策工作台。
2. 策略生成、候选构造、参数搜索、评估、选择和 promotion 的内部边界还不够清楚。
3. 研究模块已经有很多专用能力，但缺少共享的窗口、候选、试验账本、评分、工件写入和门禁内核。

本计划的目标不是把产品扩张成多人 SaaS 或机构级交易系统，而是在 `CLI plus files`、`StrategySpec` 源头、可回放证据、Dashboard 读模型这些核心原则下，把 MVP 强化为更可靠、更可解释、更高效的个人研究工作台。

## 本地事实

本计划基于当前本地项目文件，而不是旧设想：

- `docs/product-golden-path-codex-quant-review-2026-05-13.zh.md` 明确裁定：Open Composer 是个人 AI 策略工作台；Dashboard 是读模型和受控操作面，不是第二真相源。
- `reports/research/open-composer-quant-product-gap-review.zh.md` 已指出关键缺口：真多因子研究、默认防过拟合闭环、回测与实盘差异、另类数据/LLM DAG、几何/拓扑特征都需要继续产品化。
- `open_composer/research/research_report.py` 已能串联 research contract、capability、backtest、factor lab、alternative data、promotion、paper readiness，但目前仍像“聚合脚本”，不是可复用研究内核。
- `open_composer/research/factor_lab.py` 已有 RankIC、rolling RankIC、quantile return、turnover、correlation 和 stability 的雏形，但还不是横截面因子平台。
- `open_composer/analytics/execution_reality.py` 已有 OHLCV-only liquidity、participation、capacity curve 和 slippage stress，但还不是完整成交模型。
- `open_composer/research/strategy_dag.py` 已有 replay-only DAG 和 LLM packet validation，但还没有成为策略生成/回测/实盘一致的节点系统。
- `open_composer/dashboard/catalog.py` 约 2117 行，承担文件发现、解析、分类、聚合、Markdown 渲染等多种职责；`open_composer/dashboard/html.py` 约 1198 行，fallback HTML 也需要组件化。
- 研究模块中 `intraday_daily_rotation.py` 约 1925 行，`rotation.py`、`promotion.py`、`exposure_switch.py` 均超过 1100 行，说明共享内核抽取已经有现实维护收益。

## 外部依据

本计划参考成熟项目和论文，但只吸收适合本产品定位的部分：

- [QuantConnect LEAN Algorithm Framework](https://www.quantconnect.com/docs/v1/algorithm-framework/overview)：把交易算法拆成 Universe Selection、Alpha Creation、Portfolio Construction、Execution、Risk Management 等模块。依据：Open Composer 的生成和迭代流程也需要清楚分离“产生想法、构造候选、评估、组合/执行/风控”的职责。
- [QuantConnect Reality Modeling](https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/key-concepts)：把 fill、fee、slippage、brokerage 等现实假设作为模型。依据：Dashboard 和研究报告不能只展示收益，需要默认展示执行现实和可交易性。
- [Alphalens](https://alphalens.ml4trading.io/)：成熟因子分析关注 forward returns、IC/RankIC、分位收益、换手和 tear sheet。依据：Factor Lab 应成为策略研究共享能力，而不是每个研究模块各写一套指标。
- [Zipline Slippage](https://zipline.ml4trading.io/_modules/zipline/finance/slippage.html)：`VolumeShareSlippage` 一类模型把成交量参与率和价格冲击纳入成交假设。依据：Open Composer 的 Execution Reality 应继续从固定 bps 升级到 participation/capacity/impact。
- [MLFinLab Cross Validation](https://random-docs.readthedocs.io/en/latest/implementations/cross_validation.html)：purged/embargo 和 combinatorial purged CV 用于降低时间序列交叉验证泄漏和选择偏差。依据：策略优化不能默认选择最高 Sharpe，必须有试验账本和过拟合控制。
- [MLflow Tracking](https://www.mlflow.org/docs/latest/ml/tracking)：把 runs、params、metrics、artifacts 作为实验跟踪核心对象。依据：Dashboard 的下一步不是“更多按钮”，而是把研究运行、候选、指标、工件和阻塞原因组织成可比较的实验视图。
- [NautilusTrader Backtesting](https://nautilustrader.io/docs/latest/concepts/backtesting)：事件驱动回测强调数据、venue、执行算法、参与者和引擎配置的分层。依据：Open Composer 不应自研第二套完整执行引擎，而应让共享研究内核产出可供 Nautilus adapter 消费的结构化证据。
- Bailey/Lopez de Prado 的 Deflated Sharpe Ratio、Probability of Backtest Overfitting 论文：多次试验后的最好结果需要调整选择偏差。依据：参数搜索和 LLM 辅助选择必须记录 trial ledger，不能把反复试出来的最优值当 Alpha。
- 拓扑和路径签名研究，例如 [Topological Data Analysis of Financial Time Series](https://arxiv.org/abs/1703.04385) 和 [A Primer on the Signature Method in Machine Learning](https://arxiv.org/abs/1603.03788)。依据：几何/拓扑特征可作为 research-only feature family，但必须进入同一 Factor Lab、OOS、成本和 ablation 门禁。

## 产品原则

- `StrategySpec` 仍是策略行为源头，Dashboard、报告和优化器都不能成为第二真相源。
- CLI 和文件仍是第一产品表面；Dashboard 是读模型、研究解释面和受控命令面。
- Codex/Cloud Code 的优势应体现在：自动生成结构化策略、补全研究报告、解释阻塞原因、提出下一步，而不是让 LLM 在回测里不可回放地临时决策。
- Vercel 只做 password session、CSRF、HMAC、BFF proxy 和静态 UI；回测、扫描、pytest、文件写入、paper 操作都留在本地/VPS daemon。
- 样本、fixture、fallback、trial-only 数据不能被升级为 paper-ready 证据。
- 每个产品增强都必须写入 JSON/Markdown 工件，能被 Dashboard、repo check 和测试重建。

## 目标架构

目标是形成三层边界：

| 层 | 责任 | 不做 |
|---|---|---|
| Strategy layer | `StrategySpec`、版本、capability、research contract、StrategyDAG schema | 不直接存放不可审计的运行状态 |
| Research kernel | 数据窗口、候选生成、trial ledger、指标、评分、门禁、artifact writer | 不调用实时 LLM，不提交订单，不绕过 capability registry |
| Dashboard layer | runs/strategies/evidence/blockers/commands 的读模型和受控操作 | 不运行长任务，不编辑源文件，不保存第二份策略状态 |

标准流程应收敛为：

```text
Idea
  -> ResearchBrief
  -> StrategySpec draft + bounded search space
  -> CapabilityPlan
  -> CandidateSet
  -> TrialLedger
  -> EvaluationBundle
  -> PromotionDecision
  -> PaperReadiness
  -> Dashboard evidence and next action
```

## P0：产品对象和研究运行索引

### 计划

先补一层轻量对象，不改策略行为：

- `ResearchBrief`：记录用户想法、假设、适用市场、不可做范围、默认风险和必须验证的问题。
- `SearchSpace`：把参数范围、method variants、factor variants、universe variants、成本假设和最大 trial 数结构化。
- `ResearchRunIndex`：集中索引每次研究运行的 spec、版本、数据 profile、候选数、试验数、耗时、状态、报告路径和阻塞项。
- `EvaluationBundle`：统一承载 performance、factor、execution、data、LLM contribution、promotion、paper readiness 的摘要。
- Dashboard catalog 只读取这些对象，不重新推断复杂业务含义。

### 依据

- 本地 `research_report.py` 已在做聚合，但缺少可复用对象，导致 Dashboard 和研究模块需要各自猜测字段。
- MLflow 的核心启发是 run/params/metrics/artifacts 的统一索引；Open Composer 可以用文件实现，不需要引入服务端数据库。
- 用户的核心要求是“不提防过拟合也默认考虑”，这要求每个 draft 从一开始就带 research brief 和 search space，而不是回测后补解释。

### 验收

- 每个 `oc strategy draft` 产出 StrategySpec 后，同时能产出或引用 ResearchBrief/SearchSpace。
- 每个 research report 写入 `ResearchRunIndex`。
- Dashboard 能显示最新 run、候选数、试验数、状态、阻塞项和源文件路径。
- 不改变现有 backtest/promotion 数值结果。

## P1：研究共享内核

### 计划

新增 `open_composer/research/kernel/`，按稳定职责拆分：

- `windows.py`
  - `ResearchWindowSplit`
  - `WalkForwardSlice`
  - `PurgedEmbargoConfig`
- `candidates.py`
  - `CandidateSpec`
  - `CandidateSet`
  - `CandidateScore`
- `trials.py`
  - `TrialRecord`
  - `TrialLedger`
  - trial budget、search cost、random seed、local choice label
- `metrics.py`
  - performance、factor、execution、data quality、LLM contribution 的统一摘要接口
- `gates.py`
  - workflow_pass、research_pass、llm_contribution_pass、paper_ready_pass 的统一 gate result
- `artifacts.py`
  - JSON/Markdown path、manifest、runtime payload、data profile、hash 写入
- `workflow.py`
  - deterministic runner，协调 capability、data load、candidate eval、score、gate、artifact

迁移顺序：

1. `promotion.py`：先抽 walk-forward、cost sensitivity、artifact writer，风险最低。
2. `parameter_sweep.py`：接入 CandidateSet、TrialLedger、CandidateScore。
3. `factor_lab.py`、`execution_reality.py`、`alt_data_quality.py`：作为 metrics providers 接入。
4. `exposure_switch.py`、`llm_exposure_switch.py`：共享窗口、候选评分、LLM contribution gate。
5. `rotation.py`、`llm_rotation.py`、`intraday_daily_rotation.py`：最后迁移大模块，避免一次性大改。

### 依据

- 当前多个研究模块重复实现候选、OOS、walk-forward、scoring、report writing；大文件和重复逻辑已经成为维护成本。
- MLFinLab 的 purged/embargo 思路要求时间窗口成为共享基础设施，不能每个模块各自定义。
- AGENTS 规则要求区分 workflow_pass、research_pass、llm_contribution_pass、paper_ready_pass；这应该是共享 gate，而不是散落在每个研究脚本里。

### 验收

- 迁移后核心 JSON 字段兼容，旧 Dashboard catalog 不回归。
- `tests/test_promotion_report.py`、`tests/test_parameter_sweep.py`、`tests/test_factor_lab.py`、`tests/test_exposure_switch_research.py`、`tests/test_llm_exposure_switch_research.py` 通过。
- 每个研究报告都写 trial count、estimated passes、runtime_seconds、data_profile、gate result。
- 大模块逐步变薄，但不要求一轮重写全部研究代码。

## P2：策略生成和优化迭代的内部边界

### 计划

把“生成策略”和“优化策略”拆成可审计流水线，而不是一个 prompt 直接变结果：

| 模块 | 输入 | 输出 | 依据 |
|---|---|---|---|
| Idea Interpreter | 用户想法、市场约束 | ResearchBrief | 初学者不会主动声明所有风险，系统要默认补全研究问题 |
| Strategy Designer | ResearchBrief、capability registry | StrategySpec draft、SearchSpace | AGENTS 要求可调参数必须有范围、method variants、factor variants |
| Capability Planner | StrategySpec、SearchSpace | CapabilityPlan、data readiness | 新数据源必须先走 registry 和 capability evaluation |
| Candidate Generator | SearchSpace | CandidateSet | 防止 prompt 只返回单一参数集 |
| Experiment Runner | CandidateSet、data windows | TrialLedger、raw metrics | MLflow/MLFinLab 启发：试验必须可追踪，时间序列要防泄漏 |
| Evaluator Suite | raw metrics、packets、fills | EvaluationBundle | Alphalens、Reality Modeling、Zipline 都说明收益不是唯一评价 |
| Selector | EvaluationBundle | CandidateScore、selected candidate | 选择应看稳定性、成本、容量、基准和阻塞项，不是最高 Sharpe |
| Promotion Gate | CandidateScore、evidence | PromotionDecision | 保持 workflow/research/LLM/paper readiness 分层 |
| Report Writer | 全部结构化对象 | JSON/Markdown、Dashboard index | 文件优先，Dashboard 可重建 |

### 依据

- QuantConnect Algorithm Framework 的模块化说明：成熟交易系统会把 alpha、portfolio、execution、risk 分开，而不是让一个策略函数承担全部职责。
- Open Composer 的产品定位是 Codex 辅助研究；Codex 更适合生成结构化对象和解释差距，不适合在一个黑盒 prompt 中完成全部决策。
- 当前 `drafter.py` 已能生成 research_design，但后续 optimizer/promotion 没有完全围绕这份设计运转。

### 验收

- `oc strategy draft` 输出不只是 YAML，还能告诉用户搜索空间、默认验证和不可晋升原因。
- `oc strategy research-report <spec>` 默认串联 draft/search/evaluation/promotion evidence。
- 参数优化必须写 TrialLedger；没有 trial ledger 的结果不能晋升为 `research_pass`。
- LLM 参与只能出现在 ResearchBrief、StrategySpec 设计、replay packet 或 advisory review 中；回测循环禁止实时 LLM 调用。

## P3：Dashboard 从 MVP 浏览器升级为研究工作台

### 计划

Dashboard 不做第二真相源，但需要成为“看得懂、能比较、知道下一步”的工作台。

优先新增或强化以下视图：

| 视图 | 内容 | 依据 |
|---|---|---|
| Research Runs | run 状态、spec version、data source、候选数、trial 数、耗时、gate 状态、报告路径 | MLflow 的 runs/artifacts 思路；本地 ResearchRunIndex 可支撑 |
| Strategy Decision Card | 当前 lifecycle、latest research、readiness、blockers、next actions、相关版本 | 用户需要知道为什么不能 paper，而不是只看收益 |
| Candidate Compare | 参数/因子/方法候选横向比较，展示 OOS、walk-forward、DSR/PBO、cost、capacity、benchmark delta | 防止最高 Sharpe 诱导过拟合 |
| Factor Lab | RankIC、rolling RankIC、quantile spread、turnover、factor correlation、ablation 状态 | Alphalens 因子 tear sheet 的产品化 |
| Execution Reality | dollar volume、bar/ADV participation、capacity curve、slippage stress、paper fill calibration | QuantConnect Reality Modeling 和 Zipline slippage 的产品化 |
| Data & Capability | provider、timeframe、source mode、sample/fallback、PIT status、packet evidence、coverage warnings | capability registry 是数据入口，Dashboard 应暴露数据可信度 |
| StrategyDAG & LLM Evidence | quant/LLM/risk/execution 节点、packet path、visible_at、prompt_hash、marginal lift、missing-modality robustness | LLM/另类数据必须可回放和可审计 |
| Command Queue | command plan、confirmation、remote job status、audit event、failure reason | 远程模式下 Vercel 不能执行长任务，只能展示和代理 |

Dashboard 结构建议：

- `Monitor`：运行健康、paper 状态、最新阻塞项。
- `Strategies`：策略库和 decision card。
- `Research`：runs、candidate compare、factor/execution/data evidence。
- `DAG`：StrategyDAG 和 LLM/另类数据证据。
- `Activity`：signals、orders、audits、command events。
- `Settings`：只展示本地/远程状态和缺失配置，不保存敏感 secret。

### 依据

- 当前 React Dashboard 已有 Monitor、Strategies、Activity 和 command plan/run；扩展为 Research 视图比重写 UI 风险低。
- `catalog.py` 已经读取大量 artifacts，但职责过重；先把 read model 拆清，再加视图。
- 用户当前的问题集中在“产品能否默认回答研究质量问题”，Dashboard 应把这些答案结构化展示。

### 验收

- Dashboard 每个关键数字都能回链到 JSON/Markdown 源文件。
- Dashboard 不在浏览器/Vercel 里运行 backtest、pytest、scan、file write。
- 远程 Dashboard 只显示 daemon job 状态和结果，不泄露 daemon secret。
- 对新手用户，首屏能看到：当前是否 paper-ready、为什么不行、下一步该跑什么。

## P4：性能与轻量化

### 计划

研究能力增强后必须控制运行成本：

- 单次 research workflow 只加载一次 OHLCV，并复用 data profile。
- 指标计算建立 feature frame/cache key，按 spec hash、data path、timeframe、window、factor expression 缓存。
- candidate search 默认 bounded：最大 trial、top-k、early stop、cost estimate、runtime_seconds 必填。
- Dashboard catalog 拆成 readers/classifiers/view_models/summary，减少每次 rebuild 的重复解析。
- 新增 `oc cache status` / `oc cache clean --dry-run`，显式区分 tracked sample/fixture 与 ignored runtime/cache。

### 依据

- 当前 `.venv`、`dashboard/node_modules`、`data/cache` 体积较大，用户需要知道哪些是工作环境/缓存，哪些是产品证据。
- 研究模块强化后，若不做运行索引和缓存，Dashboard 和 CLI 会重复扫描 reports 与 data。
- Google 小步重构实践适合这里：先加 cache/status 和 facade，不做大规模改写。

### 验收

- 清理 cache 不删除 tracked sample、fixtures 或当前文档。
- catalog rebuild 时间和解析次数可度量。
- research report 写入 estimated passes、actual trial count、runtime_seconds。
- `oc repo check --strict` 能提醒 docs inventory 和运行产物边界。

## P5：几何/拓扑与高级研究沙盒

### 计划

将微分几何/拓扑想法作为 `research_only` feature family，而不是直接作为 Alpha 宣称：

- `geometry_features.path_signature`：低阶路径签名，输入价格、成交量、波动率路径。
- `geometry_features.tda`：滑窗嵌入后的 persistent homology / persistence landscape 摘要。
- `geometry_features.covariance_manifold`：滚动协方差矩阵的 log-Euclidean/Riemannian 距离。
- `geometry_features.graph_topology`：相关、lead-lag、流动性网络的中心性、聚类、断裂指标。

这些特征必须进入统一 Factor Lab：

- 与动量、反转、波动率、成交量等简单基线比较。
- 做 OOS、walk-forward、成本后、capacity、ablation。
- 只有通过 marginal lift 和 stability gate，才允许从 `research_only` 升级。

### 依据

- TDA、path signatures、协方差流形和网络拓扑确实是成熟研究方向，但金融市场不是封闭物理系统；漂亮解释不能替代可交易证据。
- 当前产品已经有 Factor Lab、feature packet、research contract，可以承载这类特征而不破坏安全边界。
- 用户是初学者，产品必须把这类高级方法放在“可否证研究沙盒”里，而不是变成默认交易信号。

### 验收

- 新特征默认 `research_only`。
- 没有 baseline、OOS、cost、capacity、ablation 的几何/拓扑结果不能进入 paper readiness。
- Dashboard 明确显示特征 family、输入、窗口、延迟规则、baseline 对照和阻塞项。

## P6：远程 Dashboard 与 VPS 模式协同

### 计划

远程模式继续保持 BFF/daemon 分工，但 Dashboard 要能完整显示自动化部署和作业状态：

- Vercel BFF 只代理 session、catalog、command-plan、command-run、events。
- VPS daemon 负责 backtest、scan、pytest、file write、paper action。
- async jobs 写入 `reports/agent_requests/` 或 dashboard command artifacts。
- Dashboard 显示 job queue、running/failed/succeeded、stdout 摘要、产物路径和下一步。
- Red actions 保持双确认和 audit。

### 依据

- AGENTS 明确要求 Vercel 不能运行长任务。
- 当前 remote deploy 文档和 remote jobs 已有基础，问题在于产品体验还没有把“自动部署/一键运行/返回结果”做成稳定工作流。
- 用户之前希望 VPS 模式脚本化、一键部署；这个能力应由脚本和 Dashboard job 状态承载，而不是依赖人工跟进。

### 验收

- 设置 `VERCEL_TOKEN` 后，部署脚本能输出 Dashboard URL、daemon URL、密码文件路径和 verify 状态。
- Dashboard 能看到 daemon health 和最近 deploy/command job。
- 关闭/删除远程部署有可审计脚本，不需要手工在 Vercel UI 逐项操作。

## 执行顺序

| 阶段 | 优先级 | 交付 | 原因 |
|---|---|---|---|
| 0 | P0 | ResearchRunIndex、EvaluationBundle、Dashboard 读取 run index | 先统一产品对象，避免继续堆 UI 和专用脚本 |
| 1 | P1 | research kernel MVP：windows、candidates、trials、artifacts、gates | 最大化复用，降低研究模块重复 |
| 2 | P3 | Dashboard Research Runs、Decision Card、Blockers、source links | 用户最能感知，也能验证研究内核是否可解释 |
| 3 | P2 | 生成/优化流水线重组，draft 自动产出 ResearchBrief/SearchSpace | 让 prompt 生成策略默认进入合格研究流程 |
| 4 | P4 | cache/status、catalog 拆分、运行成本字段 | 规模扩大前控制性能和轻量化 |
| 5 | P5 | 几何/拓扑 research-only feature family | 高潜力但高误用风险，必须放在底座之后 |
| 6 | P6 | 远程 job queue 与部署状态产品化 | 在本地闭环稳定后增强远程体验 |

## Review

### 可行性

可行。当前项目已经有 `StrategySpec`、research contract、factor lab、execution reality、promotion、paper readiness、StrategyDAG、Dashboard catalog、remote BFF/daemon。计划主要是抽象和连接已有能力，不需要推倒重写。

### 主要风险

- 把 Dashboard 做成第二真相源：用 read model 和 source links 避免。
- 一次性重构研究模块导致行为漂移：按 promotion、parameter_sweep、factor/execution、小研究模块、大研究模块顺序迁移。
- 过早引入复杂数据库或任务队列：先用文件索引、JSONL、agent_requests 和现有 daemon。
- LLM 节点破坏回放性：回测只读 packet，live/paper 先落 packet 再决策。
- 高级几何/拓扑特征被误宣传：默认 research_only，必须过 baseline/OOS/cost/ablation。

### 不做范围

- 不做真金交易写入。
- 不做多人 SaaS、权限系统或云数据库。
- 不在 Vercel 运行 backtest、scan、pytest、dashboard build、文件写入或 shell 命令。
- 不自研替代 NautilusTrader 的完整事件驱动执行引擎。
- 不把 sample、fixture、fallback 或 trial-only 结果当 paper-ready 市场证据。

## 验证计划

每阶段至少运行：

```bash
uv run ruff format .
uv run ruff check .
uv run oc repo check --strict
uv run oc capability test
```

按影响范围追加：

```bash
uv run pytest tests/test_repo_check.py
uv run pytest tests/test_dashboard_catalog.py tests/test_dashboard_server.py tests/test_dashboard_commands.py
uv run pytest tests/test_research_contract_and_dag.py tests/test_factor_lab.py
uv run pytest tests/test_promotion_report.py tests/test_parameter_sweep.py
uv run pytest tests/test_exposure_switch_research.py tests/test_llm_exposure_switch_research.py
uv run pytest
```

## 下一步推荐

下一轮实现应从 P0 和 P1 的最小闭环开始：

1. 定义 `ResearchRunIndex`、`EvaluationBundle`、`TrialLedger` schema。
2. 让 `build_strategy_research_report` 写入 run index。
3. Dashboard catalog 读取 run index，并在 React Dashboard 增加 Research Runs 和 Blockers。
4. 抽取 `ResearchArtifactWriter`，先迁移 promotion 和 parameter_sweep。

这样做的收益最大：它不会改变策略收益计算，却会立刻让 Dashboard、策略生成、优化迭代和研究报告共用同一套证据结构。
