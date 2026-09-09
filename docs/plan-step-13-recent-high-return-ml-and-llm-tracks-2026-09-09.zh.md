# Step 13 计划：近期高年化策略——M 轨（传统量化 + ML）与 L 轨（量化 + LLM 因子/决策）

日期：2026-09-09（周三）。截止：2026-09-11（周五）模拟盘观察模式接入。
执行者：两名无上下文执行代理（M 轨、L 轨各一）。本文自足；读者不需要其它对话记录。

## 0. 一句话

本周做出一条"近期（2024-01 至今）年化高、每周都在交易"的策略，接入 Alpaca 模拟盘观察模式；
两条并行赛道：**M 轨** = 传统量化 + ML 排序模型，**L 轨** = 量化 + LLM 负责一部分因子与决策。
门槛合同：`config/promotion/recent-regime-high-return-gates-v2.json`（已预注册，本文不重复数字）。

## 1. 用户需求原话与翻译

用户 2026-09-09 原话：
> 你前面说的这个策略感觉和我期望的差太多，收益太低了，虽然盈亏比和胜率都很好，但是交易很少……
> 我需要追求近期、年化高，同时能做传统的量化+模型的策略，以及量化+llm负责一部分因子、决策的
> 非传统量化的策略……你需要思考一些现在策略优化迭代的方向怎么调整，怎么在这周能有符合我需求的
> 策略能做出来接入模拟盘

翻译成可检验的东西（细节在门槛合同里）：

| 用户要求 | 合同化 |
|---|---|
| 近期 | 门槛窗口 2024-01-02 → 日线归档最新日；2018-2023 只披露不评分 |
| 年化高 | `cagr_recent_net ≥ 0.30`；诚实的对照不是 SPY 而是用户可以直接买的动量 ETF：SPMO 37.4%、MTUM 29.8%（同窗口，无成本）；同时不能输给波动率匹配的 SPY |
| 交易少不行 | 活跃度下限：每年 ≥30 个有持仓变化的周度调仓；换手与交易数披露 |
| 胜率/回撤 | 次要：周胜率 ≥0.55、最大回撤 ≥-25%（集中多头股票组合在本窗口能达到的量级） |
| 量化 + 模型 | M 轨：ML 单元必须在同一协议下打败自己的规则基线（否则规则就是候选） |
| 量化 + LLM | L 轨：LLM 变体必须相对"去掉 LLM 的孪生版本"有边际提升；缺失 LLM 输入时不能崩 |

## 2. 为什么现在的结果不达标（诊断，决定方向怎么调）

已有证据（账本 `reports/research/ledger/experiments.jsonl`）：

- Step 11 A 组：LightGBM 周频 top-50 等权、top-1500 宇宙、2018-2026 扩展窗口：CAGR 11.5%、
  最大回撤 -58%、输给波动率匹配 SPY 10 个点/年；加日内特征更差（-13.1%）；网格每年都选
  `h21_d6` 且验证年 rank IC 0.15-0.40 ——泄漏嫌疑，占位（placebo）检查正在跑，**结果出来前
  M 轨不得复用同一网格选择路径**（见 §3.4）。
- Step 12 B 组：F1 ETF 回调均值回归 9.1% CAGR、年均 105 笔、绝大多数时间空仓；F5 杠杆路由
  21%/-26%；F3 QQQ 日内动量约 8% 的交易日有仓位。用户明确说这类"交易少、收益低"不是重心。

根因（每条对应一个方向调整）：

1. **目标错配**：全天候 9 年门槛 vs 用户要的近期 regime。→ 窗口改为 2024 至今，24 个月滚动训练、
   按季重训（B 组协议），让模型"适配当前市场"。
2. **分散稀释收益**：top-50 等权基本是小盘倾斜的 beta。→ 集中到 top-20；宇宙加一个 top-500 变体
   （本窗口领涨的是大盘）。
3. **没有 regime 开关**：2020、2022、2025-04 的回撤全吃。→ 趋势门（SPY 收盘 > 200 日均线，否则
   全仓 BIL）作为预注册网格维度；给模型加 5 个 regime 特征列。
4. **模型没有价格以外的信息**：27 个 OHLCV 技术特征打不过 SPMO 这类"公开的动量"。→ L 轨引入
   新闻/事件信息，由 LLM 做**抽取**（不是预测），变成 PIT 特征列。
5. **所有历史等权训练**：不会随 regime 变。→ 近期样本加权（半衰期 126 日）作为网格维度。

## 3. M 轨：传统量化 + ML（执行者：B 组代理，接手原 F2/F4）

### 3.1 协议（与门槛合同一致）

- 宇宙：现有 PIT top-1500 美元 ADV（`data/features/universe/`，剔除 ETF）；变体 top-500（同表按
  ADV 排名截断，PIT）。
- 特征：`data/features/daily/{year}.parquet` 的 27 列日频特征（**不用**日内 20 列——已证明为负）
  + 5 个 regime 列（当日横截面计算，落在一个新表 `data/features/regime_daily/{year}.parquet`，
  每行 trade_date）：`spy_ret_20`、`spy_gap_200sma`（SPY 收盘/200 日均线 -1）、`vix_close`
  （`data/` 里已有 CBOE 指数则用，没有则 `spy_vol_21` 代替，并在报告里说明）、
  `cs_dispersion_21`（宇宙 21 日收益横截面标准差）、`breadth_50d`（宇宙中收盘 > 50 日均线的
  比例）。
- 标签：现有 `label_excess_{5,10}` / `label_rank_{5,10}`（h=21 不用：太慢且与"活跃"矛盾）。
- 训练：24 个月滚动窗，按季重训，禁运 = h；test 2024Q1 … 2026Q3（至今）。
- 执行：`next_open`（周五收盘信号 → 下周一开盘成交）为门槛路径；`close_marked` 披露。
- 成本：10 bp/边，压力 25 bp/边。
- 持仓：top-20 等权；趋势门关闭时 100% BIL。

### 3.2 预注册候选（≤ 22 个单元，全部写账本；家族 `step13_recent_high_return`）

M0 规则基线（6 单元）：分数 ∈ {`momentum_252_21`, `ret_126_rel`, `ret_63_rel`} × 趋势门 ∈ {开, 关}，
top-20，宇宙 top-1500。规则的"训练"= 在 24 个月回看窗内按夏普选分数列，季度切换。

M1 LightGBM 近期窗（12 单元）：h ∈ {5, 10} × 趋势门 ∈ {开, 关} × 近期加权半衰期 ∈ {无, 126 日}
× 宇宙 ∈ {top-1500}，再加 h=5/趋势门开/半衰期 126 的 top-500 变体 ×（regime 列有/无）= 12。
超参固定（不搜索）：`n_estimators=300, learning_rate=0.03, max_depth=3, min_child_samples=200,
feature_fraction=0.7, bagging_fraction=0.7, seed=7`。**深度 3 而不是 6**：每次拟合只有约 20 万行。

M2 岭回归对照（2 单元）：h=5，趋势门开/关。用现有 `RidgeRankStrategy`。目的是证明树模型相对线性
的增量，不是为了晋级。

M3（仅在用户明确要求时做；本周不做）：波动率目标的 TQQQ/SOXL 趋势——杠杆策略，合同里
`reference_only`。

网格内的服务单元由"训练窗最后一个季度"（验证季）的 rank IC 选，绝不看测试季。

### 3.3 需要改的代码（B 组代理负责，最小改动）

1. `open_composer/research/kernel/loop.py`：`ExperimentConfig` 增加
   `train_window_months: int | None = None`（None = 现有扩展窗）、`refit_frequency: "yearly"|"quarterly"`、
   `recency_halflife_days: float | None = None`（样本权重 `0.5 ** (age_days / halflife)` 传给 `fit`）、
   `trend_gate: dict | None = None`（`{"benchmark": "SPY", "sma_days": 200, "cash_symbol": "BIL"}`）、
   `universe_top_n: int | None = None`。`build_weight_schedule` 在门关闭的周把全部权重给 `BIL`
   （权重表里以真实符号 `BIL` 出现，不用伪符号，便于产品适配器直接下达）。
2. `open_composer/research/kernel/baseline_strategies.py` / `lightgbm_rank_strategy.py`：`fit` 接受可选
   `sample_weight`。
3. 新脚本 `scripts/run_step13_m_grid.py`：用 `panel.py` 精简加载器（`load_feature_panel(dates=weekly)`
   + `load_price_panel`），逐单元 `gc.collect()`，`--cells` 可只跑子集，结果调用
   `open_composer/research/regime/gates.py` 的评估函数（新增一个读 v2 合同的入口
   `evaluate_recent_high_return_candidate`，复用 `metrics.py`），账本追加，DSR 试验数按家族自动数。
4. 产品面：`open_composer/adapters/execution/model_ranking_target_weights.py` 读 `config.json` 里的
   `trend_gate` 与 `universe_top_n`；门关闭时目标权重 = `{"BIL": 1.0}`。`strategy_specs/drafts/
   us_model_ranking_portfolio_top50.yaml` 复制为 `us_recent_high_return_top20.yaml`
   （`top_k: 20`，`candidate_artifact_dir` 指向导出的 M 轨候选）。不得自行改 `execution.mode`/
   lifecycle。
5. `scripts/export_candidate_artifact.py`：支持 `train_window_months`/`trend_gate`/`recency_halflife_days`
   进 `config.json`；最终服务模型 = 用最近 24 个月重训一次（不是最后一个测试季的模型）。

### 3.4 泄漏纪律（硬约束）

A 组正在跑的 placebo（`scripts/run_b3_grid.py --placebo-only`）若显示打乱标签后 rank IC 仍 > 0.02，
说明网格选择路径有泄漏；M1 在 placebo 结论前只能跑**单单元**（h=5、门开、无加权）并同时跑自己
的 placebo（同一脚本 `--placebo`），两者一起写报告。任何 ML 单元的 placebo |IC| ≥ 0.02 → 该单元
作废，不进候选。

## 4. L 轨：量化 + LLM 因子/决策（执行者：A 组代理，接手 Wave B 收尾后）

项目已有结论（`docs/capability-gap-analysis-2026-09-02.zh.md`）：LLM 当自由交易员没有可靠 alpha
（不做）；LLM 作为"假设/因子生成 + 严格回测门"是主线；历史新闻只做**抽取**，判断类打分只用于
前向。本轨严格按这三条做。

### 4.1 L0 数据：Alpaca News（Benzinga）PIT 包

已实测（2026-09-09）：`GET https://data.alpaca.markets/v1beta1/news` 用现有 `ALPACA_API_KEY_ID`/
`ALPACA_API_SECRET_KEY` 可用；2024 年起覆盖稠密（20 只大盘股一周约 430-450 篇；全市场一天约
850 篇），2019 年稀疏。分页 `limit=50` + `next_page_token`。

- 新模块 `open_composer/research/news/collector.py` + 脚本 `scripts/collect_alpaca_news_packets.py`：
  按日拉取 2024-01-01 → 今，**不做 symbol 过滤**（一天约 17 次请求，全程约 1.2 万次请求；限速
  200 次/分 → 1-2 小时），落 `data/features/news_packets/{year}.parquet`，按日可断点续跑。
  字段：`id, created_at, updated_at, symbols(list), headline, summary, source, url, author,
  fetched_at, visible_at`。历史：`visible_at = created_at + 15 分钟`（供应商时间戳 + 固定滞后，
  合同 `knowledge_time_disclosure` 要求披露）；前向：`visible_at = fetched_at`。
  `content` 不拉（`include_content=false`），只用标题 + 摘要。
- 同一脚本加 `--forward` 模式（只拉最近 3 天，去重合并），给每日 cron 用。

### 4.2 L1 抽取：LLM 只做"标题说了什么"，不做判断

- 模块 `open_composer/research/news/extract.py` + 脚本 `scripts/extract_news_events_llm.py`。
- 后端：现有 `open_composer/research/llm_backends.py::OpenAIBackend`（`responses` API + JSON schema，
  已实测可用，默认模型 `gpt-5.6-sol`，配置端点只提供 gpt-5.5 / gpt-5.6-* 这类大模型，没有 mini）。
  每次调用打包 25 篇（标题 + 摘要 ≤ 300 字/篇），输出数组，每篇：
  `{"id", "event_type", "stated_direction": -1|0|1, "company_specific": bool, "confidence": 0-1}`；
  `event_type` 枚举：`earnings_beat, earnings_miss, guidance_raise, guidance_cut, analyst_upgrade,
  analyst_downgrade, price_target_up, price_target_down, ma_target, ma_acquirer, contract_or_product,
  regulatory_or_legal_negative, insider_or_buyback, offering_or_dilution, macro_or_sector, other_noise`。
  提示词必须包含："只抽取标题/摘要本身陈述的内容；不得使用任何外部知识或对后续走势的判断"。
- 范围（控制成本）：只抽取"候选池"里的文章——每周 M0/M1 排名前 150 + 当前持仓 的 symbol 并集
  （M 轨第一批结果出来前先用 `momentum_252_21` 前 150 代替），估计 4-8 万篇 → 2-3 千次调用 →
  约 8-12M tokens。**预算上限 30M tokens / 本周**；每次调用写
  `reports/research/llm_ledger/step13_news_extraction.jsonl`（`model, prompt_hash, input_tokens,
  output_tokens, article_ids`），超限停止并报告。
- 每条抽取结果记录 `model_id` 与 `knowledge_cutoff`（合同要求）。
- 缓存按 `article id + prompt_hash` 去重，重跑不重复付费。

### 4.3 L2 特征：PIT 日频新闻特征表

`open_composer/research/news/features.py` + `scripts/build_news_daily_features.py` →
`data/features/news_daily/{year}.parquet`，每行 (symbol, trade_date)，只用 `visible_at ≤ 当日 16:00 ET`
的文章（周五信号看不到周五收盘后的新闻）：

`news_count_5d, event_score_5d（Σ stated_direction × confidence，仅 company_specific）,
event_score_21d, earnings_surprise_dir_21d（最近一次 beat=+1/miss=-1，21 日内）, analyst_net_5d
（升级+目标价上调 − 降级+下调）, negative_binary_5d（regulatory/offering 标记）, news_abs_5d
（|direction| 之和，"关注度"）`。`panel.py::load_feature_panel` 增加 `extra_feature_roots`
参数把这张表左连接进来（缺失 = 0 且带 `news_missing` 标志列）。

### 4.4 L3 评估（三种 LLM 参与方式，各自对照"去掉 LLM 的孪生版本"）

1. **L-ml**：M1 最优单元 + 新闻 7 列 → 边际提升门（CAGR +3 个点且 rank IC +0.005）。
2. **L-rule**："新闻动量"规则：top-500 宇宙内按 `event_score_5d` 取前 20，趋势门开，周频。LLM 因子
   独立成策略，对照 = M0 同宇宙同门的动量规则。
3. **L-decision**（LLM 负责一部分决策，有边界）：M 最优单元的前 30 名，把每只最近 5 日标题给
   LLM，只允许输出 `keep | exclude` + 一句理由（排除条件限定为：持有期内有明确二元事件 / 增发 /
   监管负面），取前 20 保留者。对照 = 无覆盖层。**LLM 不能选股、不能加仓、不能改权重**。
   本项抽取用前向口径也可复用，评估时同样属于知识时间受污染的研究级证据。
4. 缺失模态：新闻列全置缺失后重跑 L-ml，必须仍通过 M 轨门槛（合同 `missing_modality_robustness`）。

### 4.5 前向（模拟盘）路径

`scripts/collect_alpaca_news_packets.py --forward` + `extract --forward` + `build_news_daily_features
--forward` 三步串成一个脚本 `scripts/run_news_feature_pipeline.py`，报告里给出 cron 建议（22:45 UTC，
在日线归档之后、观察循环 23:00 之前；**不自行安装**）。前向包的 `visible_at = fetched_at`，这才是
干净的 PIT 证据；报告必须把"历史（研究级）"与"前向（干净）"分开写。

## 5. 时间线与交付物

| 时点（UTC） | M 轨 | L 轨 |
|---|---|---|
| 周三 09-09 晚 | loop.py 扩展 + 单元测试；M0 六单元跑完；M1 单单元 + placebo | 收集器写好并开跑（1-2 小时）；抽取脚本 + 5 篇冒烟 |
| 周四 09-10 | M1/M2 全网格（≤2 小时/批，一次一个重任务）；选单元；导出候选；适配器 trend_gate；观察循环用新候选跑一次 | 抽取（候选池）跑完；特征表；L-ml / L-rule 评估；L-decision 若时间允许 |
| 周五 09-11 12:00 前 | 报告 `reports/research/control/step13-recent-high-return-2026-09.md`；spec `candidate_artifact_dir` 指向胜者（观察模式；下单仍需用户批准） | 报告 L 轨章节；前向管道脚本 + cron 建议；LLM token 账本汇总 |

诚实兜底：若没有单元通过 v2 全部门槛，仍把 M 轨最优单元以观察模式接入并在报告首段写清差距
（和当前占位候选的做法一致），由用户决定。

## 6. 纪律（两名执行者都适用）

- 内存：所有重任务 `./scripts/run_capped.sh --mem 1.8G -- …`；每个代理同一时间只跑一个重任务；
  不得调高上限；DuckDB `memory_limit ≤ 1.5GB, threads=2`。
- 提交：只 `git add <具体路径>`、`git commit -- <路径>`；禁止 `git add -A`；共享索引冲突就重试。
- 账本：`experiments.jsonl` 按 config hash 去重；家族 `step13_recent_high_return`；每个单元都记，
  包括失败的。
- 密钥：`.env` 不读不打印；报告里不出现 key。
- LLM：每次调用记 token；预算上限见 §4.2；抽取提示词固化在代码里并算 `prompt_hash`。
- 产品：不改 `execution.mode`、`execution.broker`、lifecycle、kill_switch；不下单；观察循环只算目标权重。
- 文件归属：M 轨代理拥有 `loop.py`、`baseline_strategies.py`、`lightgbm_rank_strategy.py`、
  `regime/`、`model_ranking_target_weights.py`、`export_candidate_artifact.py`、`scripts/run_step13_m_grid.py`；
  L 轨代理拥有 `open_composer/research/news/`、`panel.py`（只加 `extra_feature_roots`）、
  `scripts/*news*`、`scripts/run_step13_l_eval.py`。跨界修改先在报告进度文件里写一行说明。
- 进度文件：`reports/research/control/step13-2026-09-09-progress.md`，每完成一项加一行
  （时间、提交哈希、结果一句话）。
- 等待循环写法：`pgrep -f "run_step13_m_gri[d]\.py"`（方括号防自匹配）。
- 不做：LLM 自由选股/多代理交易员；日内特征；F1 继续调参；杠杆（除非用户要求）。

## 7. 不在本周范围但要记录的事

- Step 11 A 组 Wave B 收尾（placebo 结论、报告）由 A 组代理先完成再转 L 轨，因为 M 轨依赖其
  泄漏结论。
- 前向新闻收集一旦开始就不要停：干净的 PIT 证据只能前向积累（注册表 `news.alpaca` 的告诫）。
- 若 L 轨在本周没有通过边际提升门，下周继续：前向数据已在积累，L-decision 可在模拟盘上以
  "影子决策"（只记录不生效）方式并行评估。
