# Open Composer MVP 强化研究计划：Dashboard、策略生成优化与共享研究内核

日期：2026-05-17

## 结论

Open Composer 现在已经具备个人 AI 策略工作台的主链路，但产品形态仍偏 MVP：可以跑通策略、报告和 Dashboard，但还没有把“研究过程、策略迭代、证据比较、阻塞原因、下一步行动”组织成一个足够成熟的工作台。

本计划的目标是把当前原型强化为一个可持续迭代的个人量化研究产品，而不是扩张成多人 SaaS、机构级交易系统或 Dashboard-only 产品。核心方向有三条：

1. Dashboard 从产物浏览器升级为研究决策工作台。
2. 策略生成和优化从 prompt 到结果，拆成可审计的内部流水线。
3. 研究模块从多个专用脚本，收敛到共享研究内核。

每个方向都必须遵守当前产品原则：`StrategySpec` 是源头，CLI plus files 是第一产品界面，Dashboard 是读模型和受控操作面，LLM/新闻/事件/宏观数据影响交易前必须先变成 point-in-time packet，样本和 trial-only 结果不能升级为 paper-ready 证据。

## 本地依据

本计划基于当前本地项目文件：

- `AGENTS.md` 明确规定：`StrategySpec` 是策略行为源头；策略设计必须有参数范围、方法变体、因子变体和有限搜索空间；必须区分 `workflow_pass`、`research_pass`、`llm_contribution_pass`、`paper_ready_pass`。
- `docs/product-golden-path-codex-quant-review-2026-05-13.zh.md` 已裁定：Open Composer 是个人 AI 策略工作台，Dashboard 是读模型和受控操作面，不是第二真相源。
- `reports/research/open-composer-quant-product-gap-review.zh.md` 已指出缺口：真多因子研究、防过拟合默认闭环、回测与实盘差异、另类数据/LLM DAG、几何/拓扑研究都需要继续产品化。
- `docs/product-efficiency-optimization-roadmap-2026-05-17.zh.md` 已提出目标架构：`ResearchBrief -> StrategySpec draft + SearchSpace -> CandidateSet -> TrialLedger -> EvaluationBundle -> PromotionDecision -> PaperReadiness -> Dashboard evidence`。
- 当前本地代码已出现共享内核雏形：`open_composer/research/kernel/` 包含 workflow、trials、gates、metrics、artifacts、windows、candidates。
- 当前 Dashboard 已有 React UI、Python catalog、command plan/run、paper 状态和 research runs 初步展示，但还缺候选比较、决策卡、因子/执行/数据证据的工作台级组织。

## 外部调研依据

本计划只吸收与 Open Composer 定位相符的成熟实践：

- [QuantConnect Algorithm Framework](https://www.quantconnect.com/docs/v1/algorithm-framework/overview)：把策略拆成 Universe Selection、Alpha Creation、Portfolio Construction、Execution、Risk Management。依据：Open Composer 的策略生成和优化也应拆分职责，而不是让一个 prompt 直接决定全部行为。
- [QuantConnect Reality Modeling](https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/key-concepts)：把 fee、fill、slippage、brokerage 等现实假设模型化。依据：Dashboard 和研究报告不能只显示收益，必须默认显示执行现实和可交易性。
- [NautilusTrader Backtesting](https://nautilustrader.io/docs/latest/concepts/backtesting/)：事件驱动回测围绕数据流、venue、execution、portfolio、actors/strategies 组织。依据：Open Composer 不应自研第二套完整执行引擎，而应把研究证据结构化后供 Nautilus adapter 消费。
- [Qlib Recorder](https://qlib.readthedocs.io/en/stable/component/recorder.html)：用 Experiment、Recorder 组织实验和单次运行。依据：Open Composer 可以用文件和 JSONL 实现轻量 run tracking，不必引入数据库。
- [MLflow Tracking](https://www.mlflow.org/docs/latest/ml/tracking)：围绕 runs、params、metrics、artifacts 做实验追踪。依据：研究运行、候选参数、指标和产物应该被统一索引，Dashboard 只读取索引。
- [Alphalens](https://alphalens.ml4trading.io/)：因子研究关注 IC、RankIC、分位收益、换手、tear sheet。依据：Open Composer 的 Factor Lab 应成为共享研究指标源，而不是每个研究脚本各写一套。
- [MLFinLab Cross Validation](https://random-docs.readthedocs.io/en/latest/implementations/cross_validation.html)：purged/embargo CV 用于降低时间序列泄漏。依据：参数优化和 LLM 选择不能默认使用普通随机 CV 或只看最高 Sharpe。
- [Bailey 和 Lopez de Prado 的 Deflated Sharpe Ratio](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551)：多次试验后的表现需要校正选择偏差。依据：必须记录 trial ledger，不能把反复试出来的最优参数当作独立 Alpha。
- [A Primer on the Signature Method in Machine Learning](https://arxiv.org/abs/1603.03788)：路径签名可把路径转为特征。依据：几何方法可以进入 research-only feature family，但必须通过同一套基线、OOS、成本和消融门禁。
- [Topological Data Analysis of Financial Time Series](https://arxiv.org/abs/1703.04385)：TDA 可用于金融时间序列结构变化研究。依据：拓扑特征有研究价值，但不能跳过可交易证据直接进入 paper readiness。

## 产品原则

### 原则 1：Dashboard 不能成为第二真相源

计划：Dashboard 只读 `reports/`、`strategy_specs/`、signals、paper artifacts、remote job artifacts 和 audit logs。任何策略行为、参数、状态变更仍由 `StrategySpec`、CLI 和受控 command artifacts 落盘。

依据：本地 `AGENTS.md` 和 golden path 文档均明确 `StrategySpec` 是源头；QuantConnect 的框架也把策略职责结构化，而不是让 UI 直接改变策略语义。

验收：Dashboard 每个关键数字都能回链 JSON/Markdown 源文件；Dashboard 不直接运行回测、扫描、pytest、文件写入或 shell 命令。

### 原则 2：Codex 的优势是生成结构化证据，不是制造不可回放状态

计划：Codex 负责把自然语言想法变成 `ResearchBrief`、`StrategySpec`、`SearchSpace`、报告、测试和 review card。LLM 若影响交易逻辑，必须先落为 point-in-time packet 或 replayable DAG 节点。

依据：本地安全规则要求 LLM/news/event/macro 特征必须带 `visible_at`、`published_at`、`fetched_at`、`source`、`input_hash`、`prompt_hash`；LLM review 只能是结构化 advisory。

验收：回测循环禁止实时 LLM 调用；live/paper 调用 LLM 时先写 packet，再进入决策；报告显示 LLM 边际贡献和缺失模态鲁棒性。

### 原则 3：研究结果必须区分 workflow、research、LLM contribution、paper readiness

计划：共享 gate 层统一输出四类通过状态，不允许把 workflow pass 或 sample-data pass 推广成 Alpha 或 paper readiness。

依据：`AGENTS.md` 和 `risk-reviewer` 技能都要求区分这些状态；Bailey/Lopez de Prado 的 DSR 思路说明多次试验结果需要选择偏差校正。

验收：所有 promotion、parameter sweep、research report、Dashboard decision card 都显示四类 gate，而不是一个笼统的 ready。

## 当前问题评估

### 1. Dashboard 层面仍偏 MVP

现状：Dashboard 已能展示策略、paper 状态、activity、command plan/run 和 research runs，但多数视图仍是产物列表，缺少“我现在应该相信什么、为什么不能升级、下一步跑什么”的研究决策体验。

是否构成问题：构成问题。用户是初学者时，产品不能只给一堆 JSON/Markdown 链接。它必须把阻塞项、证据、候选比较和下一步动作显式整理出来。

依据：MLflow 和 Qlib 的共同启发是 run tracking 和 artifact tracking；Open Composer 已经 file-first，因此 Dashboard 应该把 run、params、metrics、artifacts 组织成决策视图。

### 2. 策略生成和优化的内部边界还不够清楚

现状：项目已有 drafter、parameter sweep、promotion、factor lab、alt data quality、paper readiness，但“生成策略、构造候选、评估、选择、晋升”的对象边界还没有完全产品化。

是否构成问题：构成问题。prompt 生成策略时，如果用户不主动提出防过拟合、成本、容量、因子稳定性，产品也应该默认补上。

依据：QuantConnect Algorithm Framework 把交易系统拆成清晰模块；本地 AGENTS 要求可调策略必须包含参数范围、方法变体、因子变体和有限搜索空间。

### 3. 研究模块需要共享内核

现状：`open_composer/research/` 中已有大量模块，且 promotion、rotation、exposure switch、intraday rotation 等文件较长。当前内核雏形已经开始抽取 trial、artifact、gate、workflow，但还没有覆盖所有研究路径。

是否构成问题：构成问题，但不应一次性大重写。最合理方式是先稳定共享对象，再逐步迁移模块。

依据：本地维护成本已经体现在大文件和重复逻辑中；Alphalens、Qlib、MLflow 都显示成熟研究产品需要共享指标、运行记录和 artifacts，而不是每个研究脚本自成体系。

## 目标架构

目标架构分为三层：

| 层 | 责任 | 禁止事项 | 依据 |
|---|---|---|---|
| Strategy layer | `StrategySpec`、版本、capability、research contract、StrategyDAG schema | 不保存不可审计运行状态 | 本地规则要求 `StrategySpec` 是源头 |
| Research kernel | windows、candidates、trials、metrics、gates、artifacts、run index | 不实时调用 LLM，不提交订单，不绕过 capability registry | Qlib/MLflow 的 run tracking 与 AGENTS gate 规则 |
| Dashboard layer | read model、decision card、candidate compare、job status、source links | 不运行长任务，不编辑源文件，不保存第二真相源 | Vercel BFF/daemon 分工和远程 Dashboard 规则 |

标准流水线：

```text
Idea
  -> ResearchBrief
  -> StrategySpec draft + SearchSpace
  -> CapabilityPlan
  -> CandidateSet
  -> TrialLedger
  -> EvaluationBundle
  -> SelectionDecision
  -> PromotionDecision
  -> PaperReadiness
  -> Dashboard Decision Card
```

## A. Dashboard 强化计划

### A1：Research Cockpit

计划：新增或强化一个 Research Cockpit，按研究运行展示 `run_id`、spec version/hash、data source、candidate count、trial count、runtime、gate status、blockers、report paths、source artifacts。

依据：

- 本地已经有 `ResearchRunIndexRecord` 和 `reports/research/index.jsonl` 的雏形。
- MLflow Tracking 和 Qlib Recorder 都把单次运行作为实验管理核心对象。

验收：

- Dashboard 能按策略、状态、kind、时间过滤 research runs。
- 每条 run 都能打开源 JSON/Markdown 路径。
- invalid JSONL、缺文件、旧格式不会让 Dashboard 崩溃，只显示 warning。

### A2：Strategy Decision Card

计划：为每个策略生成一个 decision card，展示当前 lifecycle、latest research、workflow/research/LLM/paper 四类 gate、主要 blocker、推荐下一步命令。

依据：

- 用户当前核心问题不是“能不能回测”，而是“是否可信、差什么、下一步做什么”。
- `risk-reviewer` 技能要求 review 必须区分证据、风险、失效条件和行动建议。

验收：

- 新手打开 Dashboard 首屏能看到每个策略为什么不能 paper-ready。
- decision card 的下一步命令来自已注册 CLI/command plan，不是自由文本幻想。
- sample、fixture、fallback、trial-only 证据在 card 上明确标红或 warning。

### A3：Candidate Compare

计划：增加候选横向比较视图，展示参数、方法变体、因子变体、OOS、walk-forward、DSR/PBO 输入、成本后表现、capacity、benchmark delta、选择理由。

依据：

- 本地 `parameter_sweep.py` 已有 trial 思路，但选择偏差控制还不完整。
- Bailey/Lopez de Prado 的 DSR 说明多次试验后最高 Sharpe 会被高估。

验收：

- 没有 TrialLedger 的优化结果不能显示为 research_pass。
- 默认排序不只按 Sharpe，而是综合 OOS、稳定性、成本、容量、基准超额和 blocker。
- Candidate Compare 支持“未选择原因”，避免只解释 winner。

### A4：Factor Lab 视图

计划：Dashboard 展示 RankIC、rolling RankIC、分位收益、long-short spread、turnover、factor correlation、ablation、factor timing 状态。

依据：

- Alphalens 的成熟因子 tear sheet 明确包含 IC、分位收益和换手等维度。
- 本地 gap review 已确认当前多因子还不是完整真多因子研究平台。

验收：

- 单因子和多因子都能显示诊断摘要。
- 缺少横截面数据、样本过短、因子不可回放时显示 blocker。
- 因子结果必须进入 EvaluationBundle，而不是只作为孤立报告。

### A5：Execution Reality 视图

计划：Dashboard 展示 dollar volume、bar/ADV participation、spread proxy、capacity curve、slippage stress、paper fill calibration、partial-fill 风险。

依据：

- QuantConnect Reality Modeling 把执行现实作为模型。
- NautilusTrader 的事件驱动 backtesting 强调 venue、matching 和数据粒度。
- 本地 `execution_reality.py` 已有 OHLCV-only liquidity、capacity 和 slippage stress 雏形。

验收：

- 每个策略都显示成本后表现和容量上限。
- 低流动性、过高参与率、样本没有真实成交量时阻塞 paper readiness。
- paper fills 写回后可用于校准 backtest friction。

### A6：Data & LLM Evidence 视图

计划：Dashboard 展示 provider、timeframe、source mode、sample/fallback、PIT packet status、coverage、freshness、LLM prompt/model/input hash、marginal lift 和 missing-modality robustness。

依据：

- 本地 capability registry 是数据入口。
- AGENTS 明确要求 LLM/news/event/macro 数据影响交易前必须 point-in-time replay。

验收：

- 未注册数据源不能作为 required strategy capability。
- LLM 输出如果没有 packet 元数据，只能显示 advisory，不能显示 Alpha。
- 另类数据缺失时，报告必须说明策略是否退化为 pure quant baseline。

### A7：Remote Job 与部署状态

计划：远程 Dashboard 显示 daemon health、job queue、running/failed/succeeded、stdout 摘要、artifact paths、deploy/stop/delete 审计记录。Vercel 只做代理和 UI。

依据：

- 本地远程文档规定 Vercel 不能运行 backtests、scans、pytest、dashboard builds、file writes 或 shell commands。
- 用户之前明确希望 VPS 模式脚本化、一键部署，并返回 Dashboard URL 与密码。

验收：

- 设置 `VERCEL_TOKEN` 后部署脚本输出 Dashboard URL、daemon URL、password path 和 verify status。
- Dashboard 只显示 job 状态，不暴露 daemon secret。
- Red actions 保持双确认、HMAC、audit。

## B. 策略生成与优化内部功能划分

### B1：Idea Interpreter

计划：把自然语言想法先转成 `ResearchBrief`，包含目标、假设、适用市场、不可做范围、默认风险、必须验证的问题。

依据：

- 初学者不会主动提出未来函数、过拟合、成本、容量、基准族等约束，产品必须默认补全。
- 本地 `build_default_research_brief()` 已经提供雏形。

验收：

- 每个 draft 都有 ResearchBrief。
- Brief 必须列出 leakage、overfit、execution、data、benchmark、LLM contribution 问题。
- Brief 不直接作为交易逻辑，只作为研究合约输入。

### B2：Strategy Designer

计划：从 ResearchBrief 生成或修改 `StrategySpec draft`，同时写入 bounded `SearchSpace`：参数范围、method variants、factor variants、universe variants、cost assumptions、max candidates。

依据：

- `AGENTS.md` 明确策略设计不能只返回一个固定参数集。
- QuantConnect 的模块化启发说明 alpha、portfolio、execution、risk 的职责要分开表达。

验收：

- 可调参数没有范围时，draft 阶段给 blocker。
- SearchSpace 必须有 trial budget，避免无限搜索。
- LLM 只能帮助设计 spec 和 search space，不能在回测中临时改参数。

### B3：Capability Planner

计划：在回测前根据 StrategySpec 和 SearchSpace 生成 CapabilityPlan，检查 provider、timeframe、source mode、paper-ready status、PIT packet 要求。

依据：

- 本地 `capabilities/registry.yaml` 是数据、事件、宏观、新闻源入口。
- 用户已确认 Alpaca 和 Longbridge 本地配置存在，产品不能误把样例 15m 当能力上限。

验收：

- 新 required capability 必须先通过 capability evaluation。
- sample/fixture/fallback 可以用于 workflow smoke test，但不能 paper-ready。
- Dashboard 显示真实支持频率和 provider 状态。

### B4：Candidate Generator

计划：将 SearchSpace 转为 `CandidateSet`，每个候选有参数、方法、因子、universe、成本假设、生成来源和 hash。

依据：

- 参数优化如果没有候选账本，就无法判断选择偏差。
- MLflow/Qlib 的 run 体系都要求可追踪参数和结果。

验收：

- CandidateSet 可重复生成。
- 候选数量超过预算时先 top-k 或采样，并记录 local choice label。
- 所有候选都能回链到 StrategySpec hash。

### B5：Experiment Runner

计划：统一运行候选，写 `TrialLedger`。每个 trial 记录 raw metrics、OOS、walk-forward、cost stress、data profile、runtime、random seed、artifact paths。

依据：

- MLflow Tracking 的核心是 params、metrics、artifacts。
- DSR/PBO 需要知道试验数量和选择过程。

验收：

- 没有 TrialLedger 的 sweep 结果不能进入 research_pass。
- trial count、estimated passes、runtime_seconds 必填。
- 重跑同一候选时能识别 spec/data/cache 变化。

### B6：Evaluator Suite

计划：统一生成 `EvaluationBundle`，承载 performance、factor、execution、data、alternative data、LLM contribution、promotion、paper readiness 摘要。

依据：

- 本地 `research_report.py` 已经在聚合这些报告，但还像一个聚合脚本。
- Alphalens、Reality Modeling、NautilusTrader 都说明收益不是唯一评价。

验收：

- 每个 research report 都有 EvaluationBundle。
- Dashboard 不再重新猜业务含义，而是读取 EvaluationBundle。
- 缺失评估项显示 blocker 或 warning，不静默忽略。

### B7：Selector 与 Promotion Gate

计划：Selector 依据 EvaluationBundle 选择候选，Promotion Gate 明确输出 workflow/research/LLM/paper 四类状态。

依据：

- 本地 AGENTS 强制区分 pass 类型。
- Bailey/Lopez de Prado 的选择偏差研究说明不能把最高回测表现作为唯一标准。

验收：

- Selector 必须写选择理由和拒绝理由。
- promotion report 显示 benchmark family、OOS、walk-forward、cost sensitivity、data comparison、feature packet evidence。
- paper readiness 只接受严格证据，不接受 trial-only winner。

### B8：StrategyDAG 与 LLM/另类数据节点

计划：将复杂策略表达成 StrategyDAG：quant_signal、feature_packet、llm_judge、risk_gate、liquidity_gate、execution_gate、portfolio_allocator。回测只能读取冻结 packet，live/paper 先写 packet 再决策。

依据：

- 本地已有 StrategyDAG schema 和 LLM packet validation 方向。
- 用户提出“节点化策略”是合理方向，但必须可回放。

验收：

- DAG validation 能阻塞缺少 `visible_at`、`input_hash`、`prompt_hash`、model、schema_version 的 LLM 节点。
- 每个 LLM 节点都需要无 LLM、纯量化、缺失 LLM、错误/延迟 LLM 的对照或 blocker。
- LLM fallback 或与 pure quant 相同的信号不能标为独立 LLM Alpha。

## C. 共享研究内核计划

### C1：Artifacts 与 Run Index

计划：把 `ResearchArtifactWriter`、`ResearchRunIndexRecord`、JSON/Markdown 写入、manifest、source_artifacts、runtime_seconds 作为所有研究模块的公共写入方式。

依据：

- 本地已经有 `open_composer/research/kernel/artifacts.py` 和 run index 雏形。
- MLflow/Qlib 均以 run/artifact 管理实验结果。

验收：

- 每个研究模块写入 index.jsonl。
- Dashboard 只读 index 和报告 payload，不扫描每个模块的私有字段。
- 写入失败不留下半截不可解析 JSON。

### C2：Windows 与泄漏防护

计划：统一 `ResearchWindowSplit`、`WalkForwardSlice`、`PurgedEmbargoConfig`。所有 OOS、walk-forward、LLM/另类数据研究都共享时间切分逻辑。

依据：

- MLFinLab purged/embargo CV 用于降低时间序列标签重叠和信息泄漏。
- 本地 gap review 已指出当前 walk-forward 仍记录 `purged: False`、`embargo_bars: 0` 的不足。

验收：

- 默认报告显示 train/OOS/walk-forward/purge/embargo 配置。
- 没有足够样本支持 purge/embargo 时，报告显示 warning 或 blocker。
- 不同研究模块不再各写一套切分。

### C3：Candidates、Trials 与 Scores

计划：共享 `CandidateSpec`、`CandidateSet`、`TrialRecord`、`TrialLedger`、`CandidateScore`，统一记录候选来源、参数、指标、质量标记和选择理由。

依据：

- 本地 parameter sweep 和多个研究模块已有重复候选/评分逻辑。
- DSR/PBO 需要知道试验数量、局部选择和候选空间。

验收：

- sweep、exposure switch、rotation、LLM selection 都接入 TrialLedger。
- CandidateScore 至少包含收益、稳定性、成本、容量、基准、数据质量、LLM 贡献维度。
- Dashboard Candidate Compare 使用统一 score，不读取模块私有结构。

### C4：Metrics Providers

计划：把 factor lab、execution reality、data quality、alternative data、benchmark family、LLM contribution 做成 metrics providers，统一进入 EvaluationBundle。

依据：

- Alphalens 说明因子诊断应该标准化。
- QuantConnect Reality Modeling 和 NautilusTrader 说明执行现实应该作为模型层。
- 本地已有这些模块，但连接方式仍不够统一。

验收：

- 新研究模块只需注册 metrics provider，不重复写报告结构。
- EvaluationBundle 缺某类指标时给出显式 reason。
- repo check 可检查核心 provider 是否仍存在。

### C5：Gates

计划：统一 gate 结果：`workflow_pass`、`research_pass`、`llm_contribution_pass`、`paper_ready_pass`。所有模块只输出结构化 GateResult。

依据：

- 本地 AGENTS、strategy-researcher、risk-reviewer 都要求四类状态。
- 这是防止 MVP 误把样本结果推成交易建议的关键边界。

验收：

- Dashboard、Markdown、JSON 的 gate 口径一致。
- paper-ready 必须依赖 research、execution、data、benchmark、feature packet 证据。
- LLM contribution 缺证据时不影响 pure quant workflow pass，但阻塞 LLM Alpha 声明。

### C6：Cache 与性能

计划：共享 data profile、feature frame/cache key、spec hash、data hash、timeframe、window、provider、factor expression。Dashboard catalog 分 reader、classifier、view model、summary，避免重复解析。

依据：

- 本地 `data/cache` 已经较大；研究模块增强后如果没有缓存和索引，会拖慢工作流。
- 文件优先产品不需要数据库，但需要明确 cache/status/clean 策略。

验收：

- `oc cache status` 能显示 provider/symbol/timeframe 级别信息。
- research report 写 estimated pass、actual trial count、runtime_seconds。
- Dashboard catalog rebuild 时间可度量，失败时显示 source path。

### C7：Geometry/Topology Research Sandbox

计划：几何/拓扑方法只作为 research-only feature family：path signature、TDA/persistent homology、covariance manifold、graph topology。默认不能 paper-ready，必须进入同一 Factor Lab、OOS、成本、capacity、ablation 门禁。

依据：

- 路径签名和 TDA 是成熟研究方向，但金融市场不是封闭物理系统。
- 本地用户提出的微分几何/拓扑想法有研究价值，但产品必须防止把漂亮解释误当 Alpha。

验收：

- 输出 `research_only: true`。
- 没有 simple baseline、OOS、cost、capacity、ablation 时显示 blocker。
- Dashboard 明确显示输入、窗口、延迟规则、baseline 对照和不能 paper 的原因。

## 执行路线

### P0：稳定产品对象和索引

交付：

- 完善 ResearchBrief、SearchSpace、EvaluationBundle、ResearchRunIndex、TrialLedger。
- 让 draft、research-report、parameter-sweep、promotion-report 都写 run index。
- Dashboard Research Cockpit 读取 run index。

依据：当前本地已有内核雏形，先统一对象不会改变策略收益计算，风险最低。

验收：现有 backtest/promotion 数值不变；Dashboard 能展示 indexed runs、blockers、source paths。

### P1：Dashboard 决策工作台

交付：

- Strategy Decision Card。
- Candidate Compare。
- Factor Lab、Execution Reality、Data & LLM Evidence 摘要卡。
- Next action command plan。

依据：用户最需要的是“产品能否回答研究质量问题”；Dashboard 是最直接的产品表面。

验收：每个策略可以一屏看出是否 paper-ready、为什么不行、下一步跑什么。

### P2：策略生成与优化流水线

交付：

- draft 默认写 ResearchBrief 和 SearchSpace。
- CapabilityPlan 前置。
- CandidateSet/TrialLedger 强制接入 parameter sweep 和主要研究模块。
- Selector 写选择和拒绝理由。

依据：用户不提防过拟合时，产品也必须默认考虑；AGENTS 已要求 bounded search space。

验收：没有 research contract、search space、trial ledger、evaluation bundle 的策略不能 promotion。

### P3：共享内核迁移

交付：

- 先迁移 promotion、parameter_sweep。
- 再迁移 factor_lab、execution_reality、alt_data_quality。
- 最后迁移 exposure_switch、llm_exposure_switch、rotation、intraday_daily_rotation。

依据：这些模块存在重复逻辑和大文件问题，但一次性重写风险高。

验收：迁移后 JSON 字段兼容，旧 Dashboard 不回归，测试通过。

### P4：默认防过拟合与实盘差异闭环

交付：

- Purged/embargo window config。
- DSR/PBO 或阻塞性 warning。
- Execution reality gate 默认进入 promotion 和 paper readiness。
- paper fill calibration report。

依据：MLFinLab、DSR、Reality Modeling 都说明这不是高级选项，而是策略可信度基础。

验收：默认 research report 必须显示 leakage、overfit、live gap checklist。

### P5：LLM/另类数据 DAG 强化

交付：

- StrategyDAG decision packets。
- Alternative data coverage/freshness/latency report。
- LLM marginal lift、single-modality baseline、missing-modality robustness。

依据：用户提出节点化策略是合理方向；本地安全规则要求可回放 packet。

验收：回测中 LLM 只能 replay packet；缺 packet 元数据阻塞 LLM contribution pass。

### P6：高级研究沙盒

交付：

- geometry/topology research-only feature reports。
- 接入 Factor Lab、EvaluationBundle 和 Dashboard。

依据：路径签名和 TDA 有研究价值，但高误用风险，必须晚于研究内核和 gate。

验收：没有 baseline/OOS/cost/capacity/ablation 不允许升级。

## Review

### 可行性

可行。当前项目已经具备 `StrategySpec`、capability registry、research contract、factor lab、execution reality、promotion、paper readiness、StrategyDAG、Dashboard catalog、remote BFF/daemon。计划主要是抽象、连接和产品化已有能力，不需要推倒重写。

### 主要风险

- 风险：Dashboard 变成第二真相源。控制：所有视图只读 artifacts，写操作走 command plan/audit。
- 风险：研究内核重构导致行为漂移。控制：按模块小步迁移，先保证 JSON 兼容和测试通过。
- 风险：LLM 节点不可回放。控制：回测只读 packet，live/paper 先落 packet。
- 风险：高级数学特征被误宣传。控制：默认 research-only，强制 baseline/OOS/cost/ablation。
- 风险：性能下降。控制：run index、cache key、bounded search、runtime_seconds、catalog 分层。

### 不做范围

- 不做真金 broker 写入。
- 不做多人 SaaS、权限系统或云数据库。
- 不在 Vercel 运行回测、扫描、pytest、dashboard build、文件写入或 shell 命令。
- 不自研替代 NautilusTrader 的完整事件驱动执行引擎。
- 不把 sample、fixture、fallback、trial-only 结果当 paper-ready 市场证据。

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

Dashboard 改动追加：

```bash
cd dashboard
npm run build
```

## 下一步建议

下一步最值得先做 P0 和 P1：

1. 把 ResearchRunIndex、EvaluationBundle、TrialLedger 的字段稳定下来。
2. 让所有核心研究命令写入同一个 run index。
3. Dashboard 先做 Research Cockpit 和 Strategy Decision Card。
4. 再把 Candidate Compare、Factor Lab、Execution Reality 接到同一 read model。

这样收益最大：不会改变策略计算逻辑，却能立刻让用户看懂产品是否真的回答了“可信度、过拟合、实盘差异、因子有效性、LLM 贡献”这些关键问题。
