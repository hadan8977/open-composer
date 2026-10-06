# 策略库总清单（T-20261006-13，2026-10-06）

清单本体是 `catalog.json`（每行一条策略，字段见第 2 节）；本文所有数字由 `build_stats.py` 从 `catalog.json`、`first-batch.json` 和登记簿快照算出，运行 `python3 reports/research/strategy-library/build_stats.py` 可以重现。没有跑任何回测。

## 1. 现状（建清单前已有的东西）

- 方向登记簿 `reports/research/harvest/directions.jsonl`：269 个方向（同一 id 取最后一行），状态分布 refuted 111、evidence_too_weak 59、not_executable 44、parked 22、partial 12、testing 5、queued 5、duplicate 4、passed 3、triaged 2、harvested 2。
- 已导入的因子库（2026-10-06 核对列数）：规则因子库 `open_composer/research/factor_library.py` 84 个定义；`data/features/alpha158` 154 列（计划写 158，末年文件 154 列）、`alpha101` 20 列、`alpha191` 34 列、`osap_price` 25 列（OSAP 价格类）、`daily` 46 列；另有 Alpha191 公式移植的登记结论 `dir:gtja191_alpha_formulas`（refuted）。
- 已筛过什么：公开因子/异象库只按作者自己发表的收益序列做了结果普查（`I-20260923-01`，609 个序列，OSAP 只有 198 个多空 predictor 的 2023-10..2024-12 共 15 个月窗口，窗口极短，不能当作我们自己的复现）；本地自己复现过的只有价格类和 SEC 会计类的一小部分，进入了股票多空书信号表（`docs/equity-book-design.zh.md` 第 4 节：价值、质量、投资/发行、动量、低风险、盈余、内部人、卖空信息、季节性、快信号，约 10 类）和 `dir:ml_ranking_liquid500_recent_vs_momentum_rule`（refuted）。
- 结论：登记簿里没有任何一条旧否定带深度台账（`depth_curve.jsonl` 在仓库里一个都没有，2026-10-04 的五条深度规则晚于全部旧结论），所以 `prior_depth_ok` 只能写 unknown；本清单把"测过但未到深度"和"从没单独测过"分开数。
- 本清单里满足五条深度规则的旧否定数量：0。

## 2. 登记口径

四个来源，共 694 行：

| 来源 | 行数 | 说明 |
|---|---|---|
| 151 Trading Strategies（Kakushadze-Serur 2018，SSRN 3247865） | 175 | 全书目录里所有带编号的策略条目 174 条，加第 20 章基础设施 1 条；'Generalities'、'A few comments' 是背景章节，不登记。PDF 取自镜像（SSRN 直链 403），361 页，sha256 见来源快照。 |
| Open Source Asset Pricing SignalDoc.csv | 331 | 331 行全登记：212 个 Predictor、114 个 Placebo、5 个 Drop；Placebo/Drop 登记但不进筛选。 |
| QuantConnect Strategy Library | 83 | 抓取时目录页共 84 个教程链接，其中大小写重复 1 个；2 个页面返回 'Page Not Found'（仍登记，页面缺失写在 alpaca_note）。目录页和文档页都是静态 HTML，可能落后于 QC 现行库，见第 7 节。 |
| 本地登记簿补充行 | 105 | 只取日内、高频、事件、另类数据、加密、期权、文本类方向（status 不是 duplicate），因为三个公开清单在这些类别很薄，不补就没法判断覆盖；字段比前三个来源粗。 |

字段：`id, name, source, original_paper, origin_list, asset_class, frequency, direction, data_needed, data_local(+detail), alpaca_tradable(+note, basis), prior_local, prior_ids, prior_best_status, prior_scope, prior_depth_ok, screen_lane_ready, engine, lane_adapter, complexity, family_key, notes`，另有 `adapter_1d`（一天内能补数据）。

- `prior_scope`：none（没有旧结论）、generic_only（只被通用 ML 排序类方向覆盖）、family_level（OSAP 因子所在机制族测过，本因子没有单独测）、specific（登记簿里就是这一条）。
- `engine`：lane（`scripts/screen_lane.py`：长仓、日/周/月、ETF 或股票收盘价面板，改参数即可进）、book（股票多空书信号列，不走 screen_lane）、new（需要新代码）。`screen_lane_ready` 只对 lane 且数据齐的条目为真。
- Alpaca 可交易判定：期权只认文档列出的 Level 1–3；未列出但风险有限的组合标 inferred；任何裸空头一律 no；期货、外汇、现券、CDS、可转债、房地产等一律 no（见 `alpaca_scope_snapshot.md`）。

## 3. 统计

**按来源 × 状态**（状态由 `build_stats.py` 的 `state()` 判定）：

| 来源 | 行数 | never_tested_individually | tested_not_at_depth | in_progress_or_live | registry_not_executable | not_tradable |
|---|---|---|---|---|---|---|
| k151 | 175 | 41 | 9 | 21 | 7 | 97 |
| osap | 331 | 178 | 11 | 22 | 1 | 0 |
| qc | 83 | 19 | 32 | 14 | 2 | 16 |
| reg | 105 | 39 | 43 | 7 | 0 | 16 |
| **total** | 694 | 277 | 95 | 64 | 10 | 129 |

**按资产类 × 状态**：

| 资产类 | 行数 | never_tested_individually | tested_not_at_depth | in_progress_or_live | registry_not_executable | not_tradable |
|---|---|---|---|---|---|---|
| crypto | 9 | 2 | 6 | 0 | 0 | 1 |
| etf | 37 | 8 | 24 | 5 | 0 | 0 |
| fixed_income | 27 | 0 | 0 | 0 | 0 | 27 |
| futures | 27 | 0 | 0 | 0 | 0 | 27 |
| fx | 11 | 0 | 0 | 0 | 0 | 11 |
| options | 75 | 35 | 2 | 11 | 0 | 27 |
| other | 25 | 0 | 0 | 0 | 0 | 25 |
| us_equity | 483 | 232 | 63 | 48 | 10 | 11 |
| **total** | 694 | 277 | 95 | 64 | 10 | 129 |

**按频率 × 状态**：

| 频率 | 行数 | never_tested_individually | tested_not_at_depth | in_progress_or_live | registry_not_executable | not_tradable |
|---|---|---|---|---|---|---|
| daily | 60 | 14 | 9 | 4 | 8 | 25 |
| event | 87 | 28 | 28 | 7 | 0 | 24 |
| intraday | 32 | 10 | 17 | 0 | 1 | 4 |
| monthly | 511 | 225 | 38 | 53 | 1 | 75 |
| weekly | 4 | 0 | 3 | 0 | 0 | 1 |
| **total** | 694 | 277 | 95 | 64 | 10 | 129 |

**按数据可得性（仅策略条目）**：

| data_local | 条数 | 其中 Alpaca 可交易 |
|---|---|---|
| yes | 215 | 215 |
| partial | 214 | 196 |
| no | 146 | 35 |

- 机制族（`family_key`）共 303 个；出现在两个及以上来源的 32 个（`families.json`）。

## 4. 关键数字

| 指标 | 数量 |
|---|---|
| 总条目 | 694 |
| 策略条目（扣除 OSAP 安慰剂/放弃项） | 575 |
| Alpaca 能交易的策略条目 | 446 |
| 能交易且本地数据齐（data_local=yes） | 215 |
| 能交易且数据齐或一天内能补（adapter_1d） | 255 |
| **能交易 + 数据齐 + 从没单独测过** | 97 |
| 能交易 + 数据齐或一天内能补 + 从没单独测过 | 131 |
| 能交易 + 从没单独测过（不管数据） | 277 |
| **能交易 + 数据齐 + 以前测过但未到深度** | 68 |
| 能交易 + 数据齐或一天内能补 + 以前测过但未到深度 | 70 |
| 能交易 + 以前测过但未到深度（不管数据） | 95 |
| 进行中或已在用（不重复） | 64 |
| 不能交易（登记但不筛选） | 129 |

"从没单独测过"包含 OSAP 里只有机制族被测过、本因子没单独测的 `family_level` 条目；这类条目的族级结论不能当作本因子的否定。

## 5. 第一批（50 个，规则见 `selection-rule.md`，选择由 `select_first_batch.py` 机械执行）

合格候选池 201 个；各资格条件排除的行数（一行可能同时不满足几条）：E2 360、E4 95、E1 129、E3 209。
配额缺口：无，四个桶都满足最低配额。
重测配额用掉 8 / 14：这些是登记簿里单独在本地测过、被否定但没到深度的方向（`prior_locally_tested` 为启发式判定），规则允许补深度，上次缺什么写在 `first-batch.json` 的 `retest_reason`。其余日内、事件条目在登记簿里是 parked 或只有文献否定，没有本地测试。

构成：

| 资产类 | 个数 |
|---|---|
| etf | 8 |
| us_equity | 42 |

| 频率 | 个数 |
|---|---|
| daily | 7 |
| event | 8 |
| intraday | 8 |
| monthly | 27 |

| 来源 | 个数 |
|---|---|
| osap | 24 |
| qc | 19 |
| reg | 7 |

| 通道 | 个数（lane=screen_lane 模板；book=股票多空书；new=新代码） |
|---|---|
| book | 25 |
| lane | 8 |
| new | 17 |

机制族 32 个，每族最多 3 个。

| # | id | 名称 | 频率 | 资产 | 通道 | 证据等级 | 机制族 | 重测 |
|---|---|---|---|---|---|---|---|---|
| 1 | qc-intraday-dynamic-pairs-trading-using-correlation-and-cointegration-approach | Intraday Dynamic Pairs Trading Using Correlation And Coint | intraday | us_equity | new | 2 | intraday_pairs |  |
| 2 | qc-dual-thrust-trading-algorithm | Dual Thrust Trading Algorithm | intraday | us_equity | new | 2 | intraday_breakout_dual_thrust | 是 |
| 3 | qc-gradient-boosting-model | Gradient Boosting Model | intraday | us_equity | new | 2 | ml_intraday_direction | 是 |
| 4 | qc-intraday-arbitrage-between-index-etfs | Intraday Arbitrage Between Index ETFs | intraday | etf | new | 2 | intraday_etf_arbitrage | 是 |
| 5 | qc-intraday-etf-momentum | Intraday ETF Momentum | intraday | etf | new | 2 | single_etf_intraday_momentum | 是 |
| 6 | reg-cn_sellside_hf_factors | Chinese sell-side high-frequency factors (理想反转, 聪明钱, 适度冒险) | intraday | us_equity | new | 3 | high_frequency_microstructure |  |
| 7 | reg-end_of_day_reversal | End-of-day reversal (Baltussen-Da-Soebhag) | intraday | us_equity | new | 3 | intraday_reversal |  |
| 8 | reg-intraday_reversal_reit_pwb | Intraday time-series reversal, including REITs (paperswith | intraday | us_equity | new | 3 | intraday_reversal |  |
| 9 | qc-option-expiration-week-effect | Option Expiration Week Effect | event | etf | lane | 2 | option_expiration_week | 是 |
| 10 | qc-pre-holiday-effect | Pre Holiday Effect | event | etf | lane | 2 | pre_holiday_effect | 是 |
| 11 | qc-turn-of-the-month-in-equity-indexes | Turn Of The Month In Equity Indexes | event | etf | lane | 2 | turn_of_month | 是 |
| 12 | qc-standardized-unexpected-earnings | Standardized Unexpected Earnings | event | us_equity | book | 2 | earnings_surprise_pead | 是 |
| 13 | reg-insider_buy_independent_broad_universe | Insider buying as an independent broad-universe monthly lo | event | us_equity | new | 3 | insider_independent_broad |  |
| 14 | reg-merger_arbitrage_target_announcement_drift | M&A target-stock post-announcement drift (long-only, next- | event | us_equity | new | 3 | merger_arbitrage_target_drift |  |
| 15 | reg-news_attention_features | News count/novelty attention features (no LLM) as a gate o | event | us_equity | new | 3 | news_attention_features |  |
| 16 | reg-prediction_market_macro_release_uncertainty_premium | Kalshi-implied uncertainty about scheduled US macro releas | event | us_equity | new | 3 | prediction_market_macro_uncertainty |  |
| 17 | qc-svm-wavelet-forecasting | SVM Wavelet Forecasting | daily | us_equity | new | 2 | ml_single_asset_direction |  |
| 18 | qc-pairs-trading-copula-vs-cointegration | Pairs Trading Copula Vs Cointegration | daily | us_equity | new | 2 | stat_arb_pairs |  |
| 19 | qc-the-dynamic-breakout-ii-strategy | The Dynamic Breakout II Strategy | daily | us_equity | lane | 2 | breakout_channel |  |
| 20 | qc-ichimoku-clouds-in-the-energy-sector | Ichimoku Clouds In The Energy Sector | daily | us_equity | lane | 2 | ichimoku_technical |  |
| 21 | qc-gaussian-naive-bayes-model | Gaussian Naive Bayes Model | daily | us_equity | new | 2 | ml_single_asset_direction |  |
| 22 | qc-optimal-pairs-trading | Optimal Pairs Trading | daily | us_equity | new | 2 | stat_arb_pairs |  |
| 23 | osap-ConvDebt | Convertible debt indicator | monthly | us_equity | book | 1 | external_financing_issuance |  |
| 24 | osap-ReturnSkew | Return skewness | monthly | us_equity | book | 1 | skewness_lottery |  |
| 25 | osap-ReturnSkew3F | Idiosyncratic skewness (3F model) | monthly | us_equity | book | 1 | skewness_lottery |  |
| 26 | osap-BetaTailRisk | Tail risk beta | monthly | us_equity | book | 1 | low_risk_beta |  |
| 27 | osap-GrAdExp | Growth in advertising expenses | monthly | us_equity | book | 1 | rd_intangibles |  |
| 28 | osap-RDAbility | R&D ability | monthly | us_equity | book | 1 | rd_intangibles |  |
| 29 | osap-OrgCap | Organizational capital | monthly | us_equity | book | 1 | rd_intangibles |  |
| 30 | osap-EarningsStreak | Earnings surprise streak | monthly | us_equity | book | 1 | earnings_surprise_pead |  |
| 31 | osap-IntMom | Intermediate Momentum | monthly | us_equity | book | 1 | xs_price_momentum |  |
| 32 | osap-InvGrowth | Inventory Growth | monthly | us_equity | book | 1 | investment_growth |  |
| 33 | osap-Cash | Cash to assets | monthly | us_equity | book | 1 | profitability_quality |  |
| 34 | osap-PctAcc | Percent Operating Accruals | monthly | us_equity | book | 1 | accruals |  |
| 35 | osap-ChTax | Change in Taxes | monthly | us_equity | book | 1 | investment_growth |  |
| 36 | osap-OPLeverage | Operating leverage | monthly | us_equity | book | 1 | profitability_quality |  |
| 37 | osap-ChEQ | Growth in book equity | monthly | us_equity | book | 1 | investment_growth |  |
| 38 | osap-roaq | Return on assets (qtrly) | monthly | us_equity | book | 1 | profitability_quality |  |
| 39 | osap-MomOffSeason06YrPlus | Off season reversal years 6 to 10 | monthly | us_equity | book | 1 | xs_price_momentum |  |
| 40 | osap-MomOffSeason16YrPlus | Off season reversal years 16 to 20 | monthly | us_equity | book | 1 | xs_price_momentum |  |
| 41 | osap-MomSeason06YrPlus | Return seasonality years 6 to 10 | monthly | us_equity | book | 1 | seasonality_same_calendar_month_xs |  |
| 42 | osap-MomSeason11YrPlus | Return seasonality years 11 to 15 | monthly | us_equity | book | 1 | seasonality_same_calendar_month_xs |  |
| 43 | osap-MomSeason16YrPlus | Return seasonality years 16 to 20 | monthly | us_equity | book | 1 | seasonality_same_calendar_month_xs |  |
| 44 | osap-CompositeDebtIssuance | Composite debt issuance | monthly | us_equity | book | 1 | external_financing_issuance |  |
| 45 | osap-BPEBM | Leverage component of BM | monthly | us_equity | book | 1 | value_composite |  |
| 46 | osap-EBM | Enterprise component of BM | monthly | us_equity | book | 1 | value_composite |  |
| 47 | qc-capm-alpha-ranking-strategy-on-dow-30-companies | CAPM Alpha Ranking Strategy On Dow 30 Companies | monthly | us_equity | lane | 2 | capm_alpha_ranking |  |
| 48 | qc-january-barometer | January Barometer | monthly | etf | lane | 2 | calendar_seasonality_index |  |
| 49 | qc-pairs-trading-with-country-etfs | Pairs Trading With Country ETFs | daily | etf | new | 2 | stat_arb_pairs |  |
| 50 | qc-can-crude-oil-predict-equity-returns | Can Crude Oil Predict Equity Returns | monthly | etf | lane | 2 | oil_predicts_equity_timing |  |

每项的数据适配、模板、成本口径、满足的规则在 `first-batch.json`。成本口径对应：lane 条目 10 bp/边基线、20 bp 压力、次日开盘成交、超额对 BIL；book 条目按 `equity-book-design.zh.md` 第 7 节；日内、期权、加密的成本合同还没冻结，写"待定"，没有自造数字。

## 6. 剩下的怎么排到 10 月底

第一批之外，合格候选池还剩 151 个，按同一排序切三批；第一批 10-15 前完成筛选，之后每批前先重跑 `select_first_batch.py` 的资格检查（旧批的结果会改变 E4/E5）：

| 批次 | 日期 | 个数 | 通道构成 | 频率构成 |
|---|---|---|---|---|
| 第二批 | 10-19..10-22 | 50 | {'book': 50} | {'weekly_monthly': 50} |
| 第三批 | 10-23..10-27 | 50 | {'book': 35, 'lane': 13, 'new': 2} | {'weekly_monthly': 47, 'daily': 3} |
| 第四批 | 10-28..10-31 | 51 | {'lane': 13, 'book': 11, 'new': 27} | {'daily': 5, 'weekly_monthly': 20, 'intraday': 16, 'event': 10} |

这些日期是估计的排期，不是承诺；每批要先过 `oc research direction-check` 和迭代门禁（CLAUDE.md），且受 Modal 月度额度和轮次预算约束，预算未知的部分不自行猜定。

**数据补给能解锁的条目**（能交易但被 E2 挡住；数字来自 catalog.json）：

| 被挡住的类别（来源/数据类型/本地状态） | 条数 |
|---|---|
| reg/partial | 54 |
| k151/partial | 49 |
| OSAP/Accounting/partial | 21 |
| OSAP/Analyst/no | 18 |
| OSAP/Options/partial | 9 |
| OSAP/13F/no | 8 |
| OSAP/Event/partial | 8 |
| OSAP/Other/no | 6 |
| OSAP/Other/partial | 6 |
| qc/partial | 6 |
| OSAP/Price/partial | 3 |
| OSAP/Trading/no | 2 |
| qc/no | 1 |

OSAP 会计类缺的 XBRL 科目（Compustat 名，数字是它出现在多少个被挡条目里；一次解析 `companyfacts.zip` 补齐一批科目，能同时解锁多个条目）：che 8、dlc 8、dltt 7、act 3、lct 3、cogs 3、xrd 3、xsga 3、pstk 3、prstkc 3、sstk 3、txp 2、invt 2、rect 2。

## 7. 没查清的

- QuantConnect 现行策略库可能比抓到的 84 个教程多（抓到的目录页页脚写 2022；官方博客说策略来源还包括 Quantpedia 免费策略、SSRN、arXiv）；本清单只登记了抓到的这些，没找到更大的官方目录入口。
- Alpaca 对信用价差、蝶式、秃鹰、日历价差等多腿期权的支持只有文档的"买入看涨/看跌价差"一条明确说明；这些条目的 `alpaca_basis` 标 inferred，需要一次模拟盘探测才能定。
- 登记簿旧否定的深度状态全是 unknown，没有逐条核对当时满足了五条里的几条；`retest_reason` 只是摘录登记簿 verdict，不是深度审计。
- 本地数据判断（`data_local`）按目录和列名做的，没有逐个因子检查覆盖率和起止日；OSAP 会计类"一天内能补"按缺失 Compustat 科目数（≤2）粗估，XBRL 到 Compustat 科目的映射可能需要更多工作。
- 登记簿补充行的字段由登记簿记录粗略推出，频率、资产类和数据可得性比三个公开清单的行粗。
- 选择规则改过一次（见 `selection-rule.md` 第 7 节的修订记录）：第一次运行后发现一个登记簿 id 写错（`multi_signal_equity_book` 是机制族名，真 id 是 `dir:multi_signal_risk_controlled_equity_book`），以及把登记簿的 evidence_too_weak/parked 一律当成"本地测过"。两处都是定义和数据错误，修正发生在看过第一次名单之后；第一次的名单保存在 `first-batch.v1-superseded.json`，没有按名单内容改配额。
- `prior_locally_tested` 是启发式（登记簿状态加证据路径加 verdict 关键词），不是逐条审计；个别条目可能误判（例如 `dir:news_attention_features` 状态是 refuted 但被判为本地未测）。
