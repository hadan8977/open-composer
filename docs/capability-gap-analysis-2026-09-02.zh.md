# 能力差距分析：项目现状、主流做法与必须补齐的能力

日期：`2026-09-02`
性质：**分析与清单，不是执行计划**。回答三个问题：项目现在有什么、主流/前沿怎么做、离目标还差什么。排期与指派另开计划。
证据口径：标 **[实测]** 的是本轮在本机/本账户上核实过的；标 **[文献]** 的来自本轮检索的外部来源（§9）；标 **[待核实]** 的是有来源但未在本账户实测的。
配套清单：`docs/data-layer-pitfalls-and-capabilities.zh.md`（数据层坑清单，本轮已补第八章）。

---

## 0. 结论先说

目标（用户 2026-07 起多次明确）：一条自主运转的策略工厂——搜索先行 → 有界搜索/ML → 统计门 → 模拟盘验证 → 用户批准 → 手动实盘；当前阶段是美股分钟线动量；并要求 AI 把非常规信息（新闻/情绪/实时）转成信号，而不是只做传统量化。

离目标的距离用两个数字说：**48 轮正式迭代、0 个可晋级候选；运营闭环（定时任务、告警、模拟盘验证）从未自动运行过一次。** 两个瓶颈都不是"再多搜几百个候选"能解决的：

1. **搜索面太窄。** 内核搜索只在 QQQ/BIL 一对标的上做单资产择时。29GB 全市场 SIP 归档（13,405 只、10 年日线 + 3.5 年分钟线）已抓完，但没有任何一条搜索用到 3 只以上标的。真正的 alpha 搜索是横截面的，而横截面的前提——幸存者偏差修复、复权因子表、PIT 成分股、流动性过滤、列式查询——全部 ❌。
2. **运营闭环是空的。** crontab 为空，4 个 paper systemd 单元被 mask 到 `/dev/null`，Telegram 23/23 次 skipped，TCA 报告 0 条观测，模拟盘验证 0/20 天，10,235 股 TQQQ 从 5 月 20 日滞留至今，kill switch 自 8 月 5 日开着。

两条好消息 **[实测]**：
- Alpaca SIP 历史数据**本身包含退市标的**（SIVB/FRC/TWTR/ATVI/VMW/CS 都能取到到退市日为止的日线）。幸存者偏差的病根只是抓取脚本用了 `AssetStatus.ACTIVE`。
- Alpaca 公司行动 API 在本账户可用（TQQQ 三次拆股、BIL 101 次分红，2020 年起）。复权因子表可以直接建。

主流/前沿对照后，**真正必要**的新能力是：横截面数据底座、列式查询层、假设先行的 LLM 因子生成（替代已实测在拟合噪声的盲目 GP）、regime 作为共享特征列、知识时间纪律下的 LLM 信息抽取、期权/微观结构特征的前向收集。**不必要**的是：时序基础模型、合成数据、强化学习、向量 RAG（§5 给理由）。

---

## 1. 项目现状（实测，不是文档声称）

### 1.1 规模

| 项 | 数值 |
|---|---|
| Python 代码 | 195,341 行；`research/` 140,044 行 / 163 文件，其中按轮次命名的一次性模块约 55% |
| CLI | `cli.py` 8,665 行，约 110 个 `oc strategy *` 子命令 |
| 测试 | 181 文件、64,370 行；`test_mom_breadth_qd_r1.py` 的 11 个既有失败是回归基线 |
| 策略 | drafts 578、approved 2、active 2、retired 4 |
| 研究 | 48 个 iteration 目录、2 个 campaign、37 份评估报告、317 个预注册候选、**0 个可晋级** |
| 数据 | `data/sip/` 29GB / 50,467 个 parquet。日线 2016-2026 全市场；分钟线 2023-2026 全市场 13,405 只、1,279,495,748 行，完成标记 2026-09-02 03:56 UTC |
| 机器 | 6 核 / 3.8GB 内存（可用约 1.5GB）/ 磁盘 217GB 剩 118GB |
| 产品面 | `oc repo check --strict` = `status=ok ready=yes`（2026-09-02） |

### 1.2 各层成熟度评级

评级：A 可直接依赖 · B 可用但有已知缺陷 · C 存在但从未产生证据 · D 缺失

| 层 | 评级 | 一句话 |
|---|---|---|
| 研究内核 `research/kernel/` | **A-** | 嵌套前推逐折重选、有效 N 聚类、门槛合同 git 锁定、GP 因果性校验——仓库里最好的代码；但只能从 `scripts/` 调用，且只做过单资产 |
| 统计检验 | **B** | DSR / CSCV-PBO / SPA 都有；但 DSR+PBO 有 3 份实现、rank IC 有 5 份；`pbo.py` 是代理指标不是 PBO；`router_common.walk_forward_router` 无 embargo 仍被路由器 CLI 使用 |
| ML 训练 | **B** | LightGBM / Ridge / Logistic，purged+embargo 前推，单标的；无 NN、无 Optuna、无 SHAP；4 轮 ML 全部负结果（7.R、7.T、VIX、高 Beta） |
| 因子库 | **B** | 84 个因子 20 族，几乎全是 OHLCV 技术类；无基本面、宏观、新闻/LLM 因子族；无特征存储 |
| 数据底座 | **C+** | SIP 归档完整且有 provenance；但宇宙只含现存标的、复权烘焙、无 PIT 成分股、无重采样器、无流动性过滤、无列式查询、新鲜度检查未挂定时 |
| 回测引擎 | **B-** | 单资产事件循环、次开盘成交；"冲击模型"是常数 bps 不随规模变化；分钟线无交易时段处理；多资产走 `router_common` 第二套引擎，成本口径不同且无互校 |
| 组合层 | **C** | 逆波动、受限风险平价、收缩最小方差散落在轮次模块里；`RiskConfig` 只有 4 个字段，无组合级回撤 kill 规则 |
| 执行 / 模拟盘 | **B-**（代码）/ **C**（证据） | Alpaca paper 适配器 2,079 行、fail-closed；但累计 11 笔订单、5 笔成交，最后成交 2026-05-26 |
| 运营闭环 | **D** | 没有任何定时任务在跑；告警从未离开本机；模拟盘验证 0/20 |
| NautilusTrader | **C** | 真实代码、硬依赖；`len(universe)==1` 守卫使路由器策略永远走不到；`reports/parity/` 为空 |
| AI 层 | **B**（纪律）/ **C**（能力） | 7 个单次结构化 OpenAI 调用，全部有确定性回退；PIT packet 纪律严；但无代理循环、无成本计量、`llm_contribution_pass` 在 readiness 里硬编码 `None`、eval_cases 无运行器 |
| 治理 | **A** | dossier 3,299 行 + campaign 2,437 行合同校验，SHA-256 复核，fail-closed；代价是治理代码远多于 alpha 代码 |

### 1.3 关键实测事实

**数据层**
- 宇宙构建：`scripts/fetch_sip_universe.py:65` 用 `AssetStatus.ACTIVE`。**[实测]** 对 Alpaca SIP 直接请求退市标的日线全部有数据：SIVB 297 行至 2023-03-09、FRC 332 行至 2023-04-28、TWTR 207 行至 2022-10-27、ATVI 448 行至 2023-10-13、VMW 至 2023-11-21、CS 至 2023-06-09。**[实测]** Alpaca `inactive` 资产列表 19,187 条，**不含**上述任何一个（被收购/破产的名字会消失）——退市名单必须来自外部。
- 公司行动：**[实测]** Alpaca Corporate Actions API 可用，返回 TQQQ 拆股 2021-01-21 / 2022-01-13 / 2025-11-20（各 2:1）和 BIL 2020 年起 101 次现金分红。仓库里 `research/corporate_action_reconciliation.py` 已有消费这类数据的模型，但没有生成复权因子表。
- 符号复用：**[文献]** Alpaca bars 端点有 `asof` 参数（"identify the underlying entity of the provided symbol(s), so that name changes for this entity can be found"），仓库未使用。
- 环境：**[实测]** `.env` 的 `ALPACA_DATA_FEED` 仍是 `iex`（`config.py:116` 默认也是 iex），而抓取脚本硬编码 `feed="sip"`。凡走 `data_feed()` 的运行时取数（模拟盘上下文）看的是 IEX，研究看的是 SIP。**[待核实]** 具体哪些运行时路径受影响。
- 存储：全仓只有 `pyarrow.parquet` 一处导入；无 DuckDB / Polars / SQLite。分片索引缓存仅进程内（冷启动日线 15s、分钟 47s）。
- 重采样：`.resample(` 只出现在 `adapters/data/alpaca.py` 与 `__init__.py`；`sip_parquet.py` 无 RTH 过滤。
- 新鲜度：`scripts/check_sip_freshness.py` 已写（提交 `1997c9f`），**未挂**任何调度。

**研究内核与统计**
- 最新内核搜索 `reports/research/search/expression-trees-p2b-search.json`（2026-09-02）：QQQ↔BIL 两腿轮动、633 个表达式、DSR 试验数 168、DSR 0.034、8 门过 3；逐折演化后 churn 1.00——**GP 在拟合噪声**（`docs/review-kernel-search-2026-09-01.zh.md` §3.3）。
- `router_common.walk_forward_router:492/507` 训练窗 `end_index=test_start`，无 purge/embargo；`kernel/nested_walk_forward.py` 的文档明确指出这是有缺陷的前身，但所有 `*-router-research` CLI 仍走它。
- `campaign_statistics.py` 是唯一正统的 DSR/PBO/SPA；`dynamic_theme_chain_r8.py:882/923` 与 `dynamic_theme_stock_r9_evaluation.py:472/512` 各有一份拷贝，r24 引用的是 r8 的拷贝。
- `optimizers/` 只有 46 行随机抽样；参数网格在 `parameter_sweep`、`kernel/parameter_search`、`market_timing`、`exposure_switch`、`optimizer.py` 各建一套。

**回测与执行**
- `engines/backtest_engine.py:473` `_impact_rate`：`linear→0`、`sqrt→eta/1e4`、`almgren_chriss→(eta+gamma)/1e4`，**与成交规模无关**。无价差、无融资、无借券、无分红。
- `router_common.py:559-563` 收益求和 `if weight > 0`：负权重不计收益，但仍计换手成本。
- 两套引擎无互校；`tests/test_backtest_reference_parity.py` 只覆盖单标的引擎。
- Nautilus：`backtest_engine.py:69-73` 守卫 `len(spec.universe)==1`；`reports/parity/` 0 个文件；`reports/backtests/` 无一份来自 nautilus 后端；paper runner 硬编码 `execution_backend="python_reference"`。

**运营**
- 调度：`crontab -l` 为空；`/etc/systemd/system/open-composer-paper-{runner,monitor}.{service,timer}` → `/dev/null`；`r23-tier0-observation` 单元存在但 disabled/inactive、journal 无记录；`deploy/cron/factor-decay-monitor.sh` 指向不存在的 `/srv/open-composer/repo`。
- 模拟盘：11 笔券商订单（5 成交、4 取消、2 过期），最后一笔 2026-07-10 过期；`positions.json` 10,235 股 TQQQ、浮亏 -$22,607（快照 2026-08-06）；`kill_switch.json` 自 2026-08-05 enabled；`paper-validation-progress.json` 0/20 天；review card 共 2 张；`reports/live/` 不存在，`journal/` 为空。
- 告警：`reports/notifications/log.jsonl` 24 条，Telegram 23 次 skipped（disabled），无邮件通道。
- TCA：`paper_tca.py` 1,368 行、门槛完整，唯一一份报告 `valid_observation_count: 0`。
- 治理证据：`reports/research/harness-runs.jsonl` 2 条 vs `reports/harness/plans/` 140 份计划——plan 路径不写 run 日志。

**AI 层**
- 调用点：`llm_backends.py:74`（通用因子物化）、`review/llm.py:127`（评审卡，advisory）、`drafter.py:209`（草拟 spec）、`auto_research.py:422`（从 84 因子里选 ID，schema enum 约束，异常静默回退到关键词启发式）、`llm_exposure_switch.py:491` / `llm_rotation.py:451` / `intraday_daily_rotation.py:1475`（训练期证据上的元选择）、`momentum_multimodal.py:293`。全部单次请求、无 tool-calling、无重试策略、**无 token/成本计量**。
- `llm_explainer.py:141-152` 与 `factor_propose.py:62-65` 声称支持 `use_llm` 但从不调用。
- `paper_readiness.py:1401` `"llm_contribution_pass": None`。
- `harness/eval_cases/` 5 个用例无运行器。
- 死资产：`knowledge/quant_capability_knowledge_base.yaml`（18.7KB，零引用）；`prompts/examples/llm_beta_regime_score.md`（被 2 个 draft spec 引用但不存在）；`agent_backend/codex_sdk.py`（依赖未安装的包，永远回退到文件队列）；`compiler/spec_to_python.py`（23 行，无调用者）。
- 知识索引：191 个去重来源、61 条经验记忆、8 条模型记忆；检索是词法匹配 + arXiv API，无向量。

---

## 2. 目标与差距的定位

把目标拆成五段，逐段标出现在处在哪一格：

| 段 | 目标要求 | 现状 | 差距性质 |
|---|---|---|---|
| 搜索先行 | 每轮先做外部研究再写策略 | dossier 强制 ≥8 来源 / ≥3 论文、query manifest 哈希、arXiv 自动抓取 | **已成型**；非 arXiv 网页只能靠代理手工填 `curated_candidates` |
| 有界搜索 | 撒网 → 精英 → 有效 N 门 | 内核三层结构完整，GP/参数变异/QD 可用 | **成型但空转**：单资产、盲目 GP、CLI 不可达 |
| 统计门 | DSR/PBO/SPA、预注册、不可事后改阈值 | 全部实现并 git 锁定 | **已成型**；重复实现待归并 |
| 模拟盘验证 | 20 天执行链验证、漂移监控、TCA | 代码全有，证据全零 | **从未运行** |
| AI 信息补充 | 非常规信息 → PIT packet → 信号 | packet 纪律严；Alpaca news 前向收集自 R11 起；无历史 first-seen | **只能前向积累**，历史回测在原则上不可得 |

所以"还差多少"的诚实回答：治理和统计已经领先于绝大多数个人项目，**缺的是喂给它们的东西**——横截面数据、真实成本、更多机制假设——以及**让它们每天转起来的运营层**。

---

## 3. 主流 / 个人 / AI / 前沿量化怎么做（本轮检索）

### 3.1 数据层

- **机构范式（CRSP/Compustat 一脉）**：永久证券 ID、退市收益、as-first-reported 基本面、指数成分历史、原始价 + 复权因子表。这五项是任何横截面研究的地基，缺一项就有一类系统性偏差。
- **个人可得来源 [文献]**：
  - Norgate：美股 2000 年起，含退市与历史指数成分，日线，survivorship-bias-free 是其卖点。
  - Sharadar（Nasdaq Data Link）：SEP 日线 25,000+ 只含退市（1998 起）、SF1 基本面（1990 起）、S&P 500 成分变动（1957 起）、8-K 事件、内部人交易。
  - FirstRate Data：1 分钟线 2000 年起，16,300 只含 7,000+ 退市，一次性购买。
  - Massive（原 Polygon）：官方称退市标的保留完整历史并有 Ticker Events 端点；第三方评价"退市数据参差"，且数据按 ticker 而非公司组织，改名要自己接。
  - Databento：`instrument_id` 跨改名/退市稳定，按日期区间解析符号；按量计费。
  - AlgoSeek / Kibot：机构级或长历史分钟线。
- **存储与查询**：Arrow/Parquet + DuckDB/Polars 是 2026 年个人到中小机构的标配，"in-process analytics"取代了单机 pandas 扫描；ArcticDB 用于更大的时序库。特征存储的核心语义是 **PIT join**（按 knowledge_time 对齐），不是缓存。
- **宏观 PIT**：FRED API 的 `realtime_start` / `realtime_end` / `vintage_dates` 参数就是 ALFRED 口径——同一 API、同一 key，不需要新供应商。
- **期权**：Alpaca 历史期权数据仅自 2024-02 起；IV/Greeks 只在 snapshot 端点（历史不可回补）。CBOE DataShop 有带 calc 的 EOD 期权报价（付费）。

### 3.2 验证方法

- **CPCV**：合成对照实验（Arian, Norouzi, Seco 2024）显示 CPCV 的 PBO/DSR 表现优于 walk-forward 与 purged K-fold。本项目有 CSCV-PBO、DSR、SPA、有效 N 聚类、嵌套前推；缺 CPCV 的路径重建。差距不大。
- **Regime**：统计跳跃模型（Statistical Jump Models）2024-2026 文献里稳定优于 HMM——状态更持久、假警报更少，有开源实现。本项目 regime 全是阈值规则，且每个策略各做一遍。
- **日内动量参考**：Zarattini / Aziz / Barbon（2024，更新至 2025-02）SPY 日内动量 2007-2024 净成本年化 19.6%、Sharpe 1.33；这是分钟线动量轮次的外部简报该纳入的直接文献。

### 3.3 ML 与 AI 量化

- **表格 GBDT 仍是主力**：Qlib 的 model zoo 以 LightGBM/XGBoost/CatBoost 为核心，外加 GRU/Transformer 等；Qlib 的 PIT 数据层 + online serving / rolling 是可参照的架构。本项目选 LightGBM 是主流选择，问题不在模型。
- **时序基础模型**：Rahimikia（FoFI 2026）实测 Chronos-large / TimesFM 零样本预测日超额收益 R² 为负、方向准确率约 50%，**不如 CatBoost/LightGBM**。Kronos（AAAI 2026）金融专用预训练在 RankIC 上大幅优于通用 TSFM，但没有扣成本、多重检验后的证据。
- **LLM alpha 挖掘（前沿主线）**：RD-Agent(Q)（Microsoft 2025）假设 → 代码 → 回测 → bandit 反馈的因子+模型联合优化，报告 2× 年化、因子数少 70%；AlphaAgent（KDD 2025）对 alpha 衰减做显式正则；QuantaAlpha、AlphaMemo、XALPHA、AlphaPROBE、AlphaLogics（2026）。共同点：**LLM 生成的是带经济逻辑的假设与代码，不是随机树；用记忆避免重复；用衰减/拥挤正则约束探索。** 这正是本项目盲目 GP 缺的东西。
- **LLM 当交易决策者**：StockBench（2025）——多数 SOTA 模型跑不赢 buy-and-hold；Agentic Trading 证据地图（2026-03）——77 篇里 19 篇达到最低实证标准，只有 1 篇记录交易成本、1 篇处理幸存者偏差，无一达到最高可复现级。结论：**LLM 当决策者没有可靠证据；当假设生成器和信息抽取器有。** 本项目"advisory-only + packet 回放"的纪律与此一致。
- **知识时间**：ChronoBERT / ChronoGPT（He, Lv, Manela, Wu 2025）按年份截止训练的模型，用于新闻→次日收益预测时前视偏差实证为"modest"；"Scaling Point-in-Time Language Models"（2026）延续。含义：新闻打分要么只做抽取不做判断，要么用截止早于测试期的模型，并把模型截止日期写进 packet。

### 3.4 执行与运营

- **PDT 规则已取消 [文献]**：SEC 2026-04-14 批准、2026-06-04 生效（FINRA Regulatory Notice 26-10）。PDT 身份、4 次/5 日计数、$25k 门槛全部取消，改为日内保证金监控框架；Reg T 50%/25% 不变；现金账户仍受 T+1 与 good-faith 约束；券商过渡期至 2027-10-20。**含义**：小账户做分钟级往返不再受次数限制，但仍需保证金账户，且券商可能对小账户收更高利率。本项目执行假设未反映这一变化。
- **Alpaca 订单 [文献]**：TIF `day/gtc/opg/cls/ioc/fok`；OPG 需 19:00 后至次日 9:28 前提交；**Alpaca 学习文章称 OPG/CLS 仅 Elite Smart Router 用户可用**（官方订单文档未提及）；延长时段仅限 limit + day/gtc；碎股仅 day。本项目 canary 只允许 `opg_limit` / `loo_limit`，**必须在本账户实测能否下单**——这可能解释历史上 6 月以来所有出场单都取消/过期。
- **运营主流**：live-vs-backtest 漂移是策略衰减最早的信号；模型注册 + 再训练触发；TCA 闭环。本项目三者的框架都有，数据都是 0。

---

## 4. 必须具备的能力（差距清单）

优先级：**P0** 目标被阻塞 · **P1** 分钟线动量与横截面必需 · **P2** 有价值但非当前必需。成本：低 = 天级，中 = 周级，高 = 多周。

### P0

| # | 能力 | 现状 | 主流做法 / 本轮证据 | 建议 | 成本 |
|---|---|---|---|---|---|
| 1 | 退市标的补抓 + 退市名单 | ❌ 宇宙只含 ACTIVE | **[实测]** Alpaca SIP 有退市标的历史；inactive 列表不含它们 | 退市名单取自外部（Sharadar/Norgate 付费，或 Wikipedia 成分变动衍生的免费名单先顶上）；对名单逐个重抓 | 低 |
| 2 | 原始价 + 复权因子表 | ❌ `adjustment=all` 烘焙 | **[实测]** CA API 可用（2020 起）；此外对同一标的抓 `raw` 与 `all` 两次，两者之比即全期因子序列 | 建 `adjustment_factors` 表（symbol, date, split_factor, div_factor, source）；查询时施加 | 中 |
| 3 | PIT 指数/宇宙成分 + 每日合格池 | ❌ | Sharadar SP500 表 / Norgate；免费方案：Wikipedia 变动表衍生数据集 | 合格池 = 当日在成分内 AND ADV ≥ 阈值 AND 价格 ≥ 阈值 AND 上市 ≥ N 天；每个决策日重建 | 中 |
| 4 | 列式查询层 | ❌ 分片扫描 + 进程内索引 | DuckDB/Polars 直查 parquet 是标配 | DuckDB 视图覆盖 `data/sip/`；分片索引持久化到磁盘；横截面按日期切片而非按标的 | 低 |
| 5 | 正确的多周期重采样器 | ❌ | 规则已在坑清单 9-14 | RTH-only、成交量加权 VWAP、以 09:30 为锚的小时线、最低覆盖率、半日市、禁止分钟合成日线；用现有 `market_calendar` | 低 |
| 6 | 运营闭环真正运行 | ❌ 全部手动 | 主流：定时抓取 + 新鲜度告警 + 每日周期 + 送达验证 | 挂 SIP 增量抓取与 `check_sip_freshness`；挂每日 paper cycle；启用 Telegram 并验证送达；处置滞留 TQQQ（用户操作）；复核 kill switch | 低 |
| 7 | 假设先行的 LLM 机制/因子生成 | ❌ 只有盲目 GP 与 84 因子选 ID | RD-Agent(Q) / AlphaAgent 模式 | LLM 产出 `{经济假设, 表达式, 预期方向, 失效条件}`，进入现有内核的因果校验 + 有效 N + 门槛；记忆负结果避免重复 | 中 |
| 8 | 引擎统一与漏洞修补 | ❌ 两套引擎、一套漏 embargo | 一套成本口径 + parity 测试 | 路由器路径改用逐笔成本或与单资产引擎对齐；负权重处理写明；`walk_forward_router` 加 embargo 或退役 | 中 |

### P1

| # | 能力 | 现状 | 主流做法 / 本轮证据 | 建议 | 成本 |
|---|---|---|---|---|---|
| 9 | 横截面评估内核 | ❌ 单资产 | 日线全市场横截面是 alpha 搜索的常态 | 先日线全市场（33M 行，DuckDB 可承受）；分钟线只对已过门候选、≤10 只或预计算 5m/30m 面板 | 中高 |
| 10 | 真实交易成本 | ❌ 固定 20bps + 常数"冲击" | 价差 + 平方根冲击随规模 + 借券费 | SIP 分钟 bar 已带 vwap/trade_count；价差需抓 quotes；冲击用 `σ·sqrt(Q/ADV)` | 中 |
| 11 | Regime 数据产品 | ❌ 各策略各做阈值规则 | 统计跳跃模型优于 HMM | 每日产出共享 regime 列（含 knowledge_time），策略只读 | 低 |
| 12 | 组合层与组合级风控 | ⚠️ 散落 | 波动率目标、受限风险平价、回撤 kill | 抽成共享模块；`RiskConfig` 增加 `max_drawdown`；runner 在下单前复核 `gross_exposure_limit` / `max_symbol_weight` | 中 |
| 13 | 微观结构特征 | ❌ | tick-rule 签名成交量、Amihud、VWAP 偏离、开盘 30 分钟量比 | 依赖 #5，有分钟线后成本极低 | 低 |
| 14 | 期权特征前向收集 | ⚠️ 只有 VIX/VIX3M | GEX 是波动率状态图不是方向预测；Alpaca IV/Greeks 只有实时 snapshot | 每日落盘 SPY/QQQ 链 snapshot（IV 期限结构、skew、按行权价 OI）；先积累再回测 | 低 |
| 15 | 知识时间纪律下的 LLM 抽取 | ⚠️ packet 纪律有，内容能力弱 | ChronoGPT；extraction-only | packet 记录模型截止日期；历史新闻只做实体/事件抽取；判断类打分只用于前向 | 中 |
| 16 | TCA 观测入库 | ❌ 0 观测 | 每笔成交自动生成 observation | paper 成交回执 → `tca-ingest` 自动化 | 低 |
| 17 | 可解释性与试验一致性 | ❌ 只有 `feature_importances_` | permutation importance / SHAP | 并入 `oc strategy explain`；超参网格计入试验数 | 低 |
| 18 | PIT 宏观与基本面 | ❌ | FRED realtime 参数；SEC XBRL companyfacts 带 `filed` 日期 | `macro.fred_series` 改用 vintage 参数；基本面从 companyfacts 起步 | 中 |

### P2

| # | 能力 | 建议 |
|---|---|---|
| 19 | Nautilus parity | 要么跑出第一份 parity 报告，要么把 `nautilus_backend` 从 readiness 检查名里降级为"计划产物"，不要挂着一个从未产生证据的硬依赖 |
| 20 | CPCV 路径重建 | 现有 CSCV 之上加路径级统计；优先级低于 #9 |
| 21 | LLM 成本/token 账本 | 每次调用记录 model、tokens、cost、prompt_hash；自主循环没有这个会失控 |
| 22 | eval_cases 运行器 | 5 个用例已写好，缺 30 行运行器 |
| 23 | 代码归并 | 3 份 DSR/PBO → 1；5 份 rank IC → 1；55% 一次性轮次模块归档到 `research/archive/`，只保留其证据 |
| 24 | 内存 | 3.8GB 是分钟横截面的硬天花板；DuckDB 能把日线横截面救回来，分钟横截面需要更大机器或预计算面板 |

---

## 5. 前沿能力逐项评估

| 能力 | 判定 | 理由 |
|---|---|---|
| 假设先行的 LLM 因子/机制生成（RD-Agent 模式） | **必要** | GP 已实测在拟合噪声（churn 1.00）；文献主线一致转向"LLM 出假设与代码 + 严格回测门"；本项目的门槛、有效 N、因果校验正好是它缺的另一半 |
| 知识时间安全的 LLM 抽取 | **必要**（AI 信息目标的前提） | 否则 2026 年模型给 2019 年新闻打分就是未来函数；ChronoGPT 证明可以做对 |
| 统计跳跃模型 regime | **必要，低成本** | 优于 HMM 的证据充分；做成数据产品避免每策略重做 |
| 微观结构特征 | **必要，低成本** | 分钟线已在手；文献与实务都把签名成交量/流动性作为短周期动量的条件变量 |
| 期权衍生特征 | **前向收集** | 历史仅 2024-02 起且无历史 Greeks；GEX 只是波动率状态图；先落盘再决定 |
| 时序基础模型（Chronos/TimesFM/Kronos） | **不做** | 通用 TSFM 实测不如 LightGBM；Kronos 无扣成本证据；本机 3.8GB 也跑不动 |
| 合成数据增强 | **不做** | 生成模型学到伪影、策略再拟合伪影；稳健性检验用块自助法即可 |
| 强化学习 | **不做** | 样本效率与过拟合问题在小样本金融数据上无解；文献里没有扣成本后的稳定证据 |
| 向量 RAG 知识库 | **低优先** | 191 个来源用词法索引够用；先把 `curated_candidates` 的网页搜索接成真正的抓取 |
| 多代理 LLM 交易员（TradingAgents 类） | **不做** | StockBench 与 Agentic Trading 审计都指向：作为决策者无可靠 alpha |
| 保形预测弃权 | **已有，保留** | `MLModelConfig` 已支持 split-conformal 下界弃权 |

---

## 6. 项目的结构性不足

1. **搜索面与数据面脱节。** 花了大成本抓全市场 SIP，研究代码却仍是单资产。横截面所需的五项地基（#1-#5）没有一项存在。
2. **两套回测引擎、一套漏 embargo、零互校。** 这是坑清单第 23-24 条的同类问题在引擎层的重现。
3. **运营闭环为零。** 所有"自动"都是模板；模板还指向错误路径。用户 2026-07-06 就指出"瓶颈是运营循环不是研究"，两个月后仍然如此。
4. **治理厚、alpha 薄。** 约 5,700 行合同校验 vs 约 350 行 LLM 逻辑；55% 研究代码是一次性轮次拷贝；每轮 1-2 天写近似重复代码。治理挡住了假晋级（这是成绩），但没有把省下的时间变成机制假设。
5. **AI 层是纪律性的，不是生产性的。** 它防止 LLM 作弊做得很好，但 LLM 产出的内容只有"从 84 个 ID 里选几个"和"在候选里挑一个"。
6. **多处"有框架无数据"。** TCA、drift、harness-runs、parity、journal、notifications——每一个都能在文档里读成已具备，产物里都是零或近零。**产物永远为准**（坑清单第 44 条）。
7. **机器规格是硬约束。** 3.8GB 内存决定了分钟横截面在本机不可行；这不是代码能修的。
8. **两处环境残留会咬人。** `ALPACA_DATA_FEED=iex`；OPG/CLS 权限未在本账户实测。

---

## 7. 建议的落地顺序（不是排期）

先后关系按"解锁最多后续"排：

1. **运营闭环跑起来**（#6）——全是已有脚本，半天；没有它，后面所有 paper 证据都不会产生。滞留 TQQQ 与 kill switch 需要用户决定。
2. **横截面数据底座**（#1 → #2 → #4 → #5 → #3）——退市补抓最便宜且已验证可行；复权因子表次之；DuckDB 层让后面的一切快一个量级。
3. **引擎修补**（#8）——在横截面内核之前统一成本口径，否则新内核会继承旧漏洞。
4. **横截面内核 + 假设先行的 LLM 生成**（#9 + #7）——这是从"0 可晋级"里出来的真正路径：更多的、经济上独立的机制假设，而不是同一机制的更多参数。
5. **regime 数据产品、微观结构、期权前向收集**（#11、#13、#14）——低成本，作为横截面内核的特征输入。
6. **组合层与组合级风控**（#12）——在有 ≥2 个通过的机制之前不急，但 `max_drawdown` 进 runner 应提前。

**明确不要做的**：时序基础模型、合成数据、RL、多代理交易员；不要为了让候选通过而放松门槛（坑清单第 6 章禁令继续有效）；不要在修好 #1-#3 之前跑任何横截面选股回测——那只会产出幸存者偏差的"alpha"。

---

## 8. 本轮核实方法

- 代码：4 个只读扫描（研究/ML、执行/运营、AI/治理各一份完成；数据层扫描因配额中断，改由直接核对补齐）+ 逐条 grep 复核本文引用的每个行号。
- 账户：用仓库 `.env` 凭据只读调用 Alpaca 历史 bars（feed=sip, adjustment=all）、assets（active/inactive）、corporate actions；未打印任何密钥。
- 环境：`crontab -l`、`systemctl list-timers`、`/etc/systemd/system` 目录、`ps`、`free`、`df`。
- 产物：`reports/paper/*`、`reports/parity/`、`reports/notifications/log.jsonl`、`reports/research/harness-runs.jsonl`、`data/sip/*/_LAYOUT.json`、`_COMPLETE_2023_2026.json`。
- 文献：§9 列出的检索结果；未做实测的一律标 [文献] 或 [待核实]。

---

## 9. 来源

数据与供应商
- Alpaca 历史 bars 参数（`adjustment` / `feed` / `asof`）：https://docs.alpaca.markets/reference/stockbars
- Alpaca 公司行动 API：https://alpaca.markets/blog/introducing-corporate-actions-api-announcements/ ；https://docs.alpaca.markets/us/reference/corporateactions-1
- Alpaca 订单与 TIF：https://docs.alpaca.markets/us/docs/orders-at-alpaca ；https://alpaca.markets/learn/13-order-types-you-should-know-about ；https://docs.alpaca.markets/docs/alpaca-elite-smart-router
- Alpaca 历史期权数据：https://docs.alpaca.markets/us/docs/historical-option-data
- Massive（Polygon）退市处理：https://massive.com/knowledge-base/article/what-does-polygon-do-with-delisted-tickers ；第三方评价：https://github.com/shinathan/polygon.io-stock-database
- Databento 符号体系：https://databento.com/docs/standards-and-conventions/symbology ；https://databento.com/docs/venues-and-datasets/equs-mini
- Sharadar 数据集：https://www.quantrocket.com/sharadar/ ；https://sharadar.com/prices
- Norgate 幸存者偏差数据库：https://concretumgroup.com/how-to-construct-a-survivorship-bias-free-database-in-norgate-using-python/
- FirstRate Data：https://firstratedata.com/ ；Kibot：https://www.kibot.com/
- FRED/ALFRED realtime 参数：https://fred.stlouisfed.org/docs/api/fred/series_observations.html ；https://github.com/mortada/fredapi
- Polars + DuckDB 栈：https://www.opensourceforu.com/2026/03/polars-duckdb-the-new-power-combo-for-in-process-analytics/ ；回测框架景观：https://python.financial/

验证方法与 regime
- CPCV 对照实验（Arian, Norouzi, Seco）：https://www.sciencedirect.com/science/article/abs/pii/S0950705124011110
- purged/CPCV/DSR 开源实现：https://github.com/eslazarev/purged-cross-validation
- 统计跳跃模型：https://arxiv.org/html/2402.05272v2 ；https://arxiv.org/pdf/2406.09578 ；https://arxiv.org/pdf/2410.14841
- SPY 日内动量（Zarattini, Aziz, Barbon）：https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4824172

ML 与 AI 量化
- Qlib 架构：https://www.alphanova.tech/blog/what-is-microsoft-qlib ；https://refft.com/en/microsoft_qlib.html
- RD-Agent(Q)：https://arxiv.org/abs/2505.15155
- AlphaAgent：https://arxiv.org/abs/2502.16789 ；QuantaAlpha：https://arxiv.org/html/2602.07085 ；AlphaMemo：https://arxiv.org/pdf/2606.20625 ；XALPHA：https://arxiv.org/pdf/2607.08332 ；AlphaPROBE：https://arxiv.org/pdf/2602.11917 ；AlphaLogics：https://arxiv.org/pdf/2603.20247
- StockBench：https://arxiv.org/abs/2510.02209
- Agentic Trading 证据地图：https://arxiv.org/html/2605.19337v1
- TradingAgents：https://arxiv.org/html/2412.20138v5 ；FinMem：https://arxiv.org/pdf/2311.13743
- 时序基础模型在金融的再评估（Rahimikia, FoFI 2026）：http://wp.lancs.ac.uk/fofi2026/files/2026/03/FoFI-2026-020-Eghbal-Rahimikia.pdf
- Kronos：https://arxiv.org/abs/2508.02739
- ChronoBERT / ChronoGPT：https://arxiv.org/abs/2502.21206 ；Scaling Point-in-Time LMs：https://arxiv.org/html/2607.11889v2

执行与监管
- FINRA PDT 取消（Notice 26-10）：https://www.quantinsti.com/articles/finra-pdt-rule-removal-2026/ ；https://optionstradingiq.com/pdt-rule-eliminated-2026/
- GEX 定义与局限：https://spotgamma.com/gamma-exposure-gex/ ；https://optionstradingiq.com/what-is-gex/
