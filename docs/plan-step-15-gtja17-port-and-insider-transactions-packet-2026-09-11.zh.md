# Step 15 计划：补齐美股有效的 17 个 GTJA 因子 + 内部人交易（Form 4）PIT 特征包

日期：2026-09-11。作者：协调者。执行者：额度重置后的执行代理（无上下文，按本文件执行；来源卡见
`reports/harness/source_cards/step15_us_alpha_survey_round2.jsonl`）。

## A. 17 个在美股存活的 GTJA Alpha191 因子（先做，纯价量，零新数据）

证据：Du/Walter/Ulrich, arXiv 2601.06499（S&P 500，2002-2022，月频，双选择 LASSO 控制 151 个基本面因子后 17 个 t > 2）：
**046, 084, 073, 123, 049, 071, 184, 155, 054, 181, 161, 190, 039, 015, 063, 001, 086**。
1. 在 `open_composer/research/features/alpha191.py` 里按 GTJA 原始公式实现其中尚未实现的 id（以 `IMPLEMENTED_IDS` 为准），
   每个公式在 docstring 引用原式；`gtja017` 那类 `rank ** delta` 的退化写法要在实现时就做有界化（或按原文的正确解释），不再靠注册表剔除。
2. 重建 `data/features/alpha191/{year}.parquet`（`scripts/build_alpha101_alpha191_features.py`，`run_capped.sh --mem 1.8G`，逐年检查点）。
3. 用 `scripts/screen_factors.py` 重筛（它已有检查点；删除 alpha191 的旧检查点即可只重算该库），在 F 轨章节加一节
   "US-17 在 2016-2026 / 2024-2026 的 IC、ICIR、FDR、符号稳定性"，与论文的月频结论对照（我们是周频、PIT 前 500 ADV）。
4. 若 US-17 中有 ≥ 5 个在近期窗通过 FDR，跑一个 `feature_set = screened_top40_recent ∪ us17` 的 M1 单元（真实 + 占位），记账本。

## B. 内部人交易 PIT 特征包（用户 2026-09-11 指名关注的方向）

数据：SEC Insider Transactions Data Sets（免费、官方、2006-01 起、季度发布、as-filed XML 展平；表 SUBMISSION / REPORTINGOWNER /
NONDERIV_TRANS，字段 FILING_DATE、TRANS_DATE、TRANS_CODE、TRANS_SHARES、TRANS_PRICEPERSHARE、TRANS_ACQUIRED_DISP_CD、
RPTOWNER_RELATIONSHIP、ISSUERTRADINGSYMBOL）。实时尾段用 EDGAR 每日 Form 4 索引补齐（季度包有滞后）。
先在 `capabilities/registry.yaml` 登记为新能力并跑能力评估（项目规则），再写采集器。
1. `open_composer/research/insider/collector.py`：下载季度 zip → DuckDB → `data/features/insider_packets/{year}.parquet`，
   只保留 TRANS_CODE ∈ {P, S}（公开市场买卖）、剔除 10b5-1 计划交易（若字段可辨）与修正重复；PIT 可见日 = FILING_DATE 的下一个交易日（无受理时间戳，日粒度）。
2. 日频特征（每 symbol × 交易日，只用可见日 ≤ t 的记录）：`ins_net_buy_60d_mcap`（净买入金额 / 市值）、`ins_n_buyers_60d`（不同买入内部人数）、
   `ins_officer_buy_60d`（高管买入金额）、`ins_sell_pressure_60d`、`ins_opportunistic_buy_90d`（按 Cohen-Malloy-Pomorski 2012 的"非例行"定义：
   过去 3 年在同一日历月都有交易的视为例行，其余为机会型——该文献需先补来源卡）、`ins_days_since_last_buy`。
3. 两种用法，分别评估：(a) 作为因子进 `scripts/screen_factors.py`（新库 `insider`，同一协议：IC、FDR、符号稳定性）；
   (b) 作为**确认信号**叠加在动量规则上（JEF 2025 的思路：内部人在动量多头腿的净买入比例作为动量择时器）——预注册：
   门开条件 = 过去 60 日多头腿净买入比例 > 中位数，比较开/关两个孪生单元。
4. 门槛不变（合同 v2，`cagr_excess_vol_matched_spy` 不放宽）；标的允许 TQQQ 类自带杠杆 ETF。

## C. 不做 / 后做

- AQuA 式的自改进研究循环：表达式与代码未公开，只借鉴"密封测试窗 + 失败分析记忆"的设计，并入仓库内因子挖掘循环计划（LLM 端点恢复后）。
- 投资者共同提及网络：A 股、私有数据、商业产品，不做。
- 新闻情绪因子择时（Cogent 2026）：等 L 轨端点恢复后，用已采集的 Alpaca 新闻包做因子级情绪聚合，只作为体制输入。
- "FinSentiment Alpha"（SSRN 6908879）无法核实，不引用。

预计：A 一个执行代理工作日（含重筛）；B 两个工作日（采集器 + 特征 + 两种评估）。
