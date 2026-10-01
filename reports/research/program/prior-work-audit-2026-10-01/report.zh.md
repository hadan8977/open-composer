# 过往工作审计：哪些能进多信号股票书（2026-10-01）

执行轮 R1001-1025-AUD，写于 2026-10-01 10:34 UTC。只做分类，不跑实验；数字全部来自登记簿 `reports/research/harvest/directions.jsonl` 和它指向的证据文件，找不到的写“not found”。逐行结果见同目录 `audit.json`（256 行）。

**读法**
- 登记簿 JSONL 是追加式历史，414 行只对应 264 个方向；同一个 id 有多行（如 harvested -> queued -> refuted）。本审计每个 id 取最后一行，共 264 个，其中 256 个落入任务范围（见第 8 节列出的 8 个排除项）。
- `evidence_grade`（审计新增字段）：A = 本地检验里有 |t|>=2 的 IC/事件/多空数字，或同池随机对照被打赢；B = 只有本地长仓绝对结果、已发表的多空数字、或仅有 IC 无 t；C = 没有可用数字。排序时先看它。
- ETF 规则行的 `signal_absent` 意思是“没过 K1/K2（以 S3 为参照的门槛）”，不是证明效应为零；这些行都没有股票层面的截面检验，对股票书基本没有价值，所以不影响结论。

## 1. reuse_class x failure_class 计数

| reuse_class | signal_real_unit_killed | signal_absent | not_tested | execution_or_data_infeasible | superseded_or_duplicate | passed_or_live | 合计 |
|---|---|---|---|---|---|---|---|
| S1_INPUT | 9 | 12 | 4 | 0 | 0 | 0 | 25 |
| S2_CANDIDATE | 5 | 1 | 13 | 4 | 0 | 0 | 23 |
| MODEL_ASSET | 1 | 0 | 0 | 0 | 0 | 0 | 1 |
| TIMING_OVERLAY | 9 | 3 | 2 | 0 | 0 | 0 | 14 |
| LLM_TEXT_ASSET | 1 | 3 | 1 | 0 | 1 | 0 | 6 |
| SLEEVE | 0 | 0 | 0 | 0 | 0 | 5 | 5 |
| INFRA | 0 | 3 | 5 | 0 | 0 | 1 | 9 |
| DEAD | 3 | 90 | 44 | 34 | 2 | 0 | 173 |
| 合计 | 28 | 112 | 69 | 38 | 3 | 6 | 256 |

登记状态：refuted 109，evidence_too_weak 59，not_executable 44，parked 23，partial 12，passed 3，queued 3，triaged 2，harvested 1。
证据等级：A 12，B 25，C 219。
优先级：P1 6，P2 18，P3 232。

要点：
- `signal_real_unit_killed` 共 28 行（A 级 12，B 级 16），其中能进书的有 25 行：TIMING_OVERLAY 9，S1_INPUT 9，S2_CANDIDATE 5，DEAD 3，LLM_TEXT_ASSET 1，MODEL_ASSET 1。
- 真正的“信号不存在”（`signal_absent`）集中在 ETF 规则、日内规则、仓位叠加、技术指标和 ML/LLM 方法论文上；股票截面信号反而大多是被单位杀掉的。
- 股票书的新输入（S2_CANDIDATE）有 23 行，其中磁盘上已有数据的只有一半左右；`passed_or_live` 只有 6 行，都是 ETF sleeve 或基础设施。

## 2. 最重要：signal_real_unit_killed（28 行）

排序规则：先看证据等级（A 在前），同级按对本书的价值排。“去向”是它进入股票书的路径。

| # | 方向 | 等级 | 被检验的单位 | 证据数字（来源：登记簿该行 claim/verdict） | 去向 |
|---|---|---|---|---|---|
| 1 | `lgbm_price_volume_ranking_small_caps` | A | model_ranking_long_only | walk-forward RankIC stress 0.020 (t 3.1), illiquid tercile 0.031 (t 5.75), liquid 0.013 (t 1.2); books anchor Sharpe 0.163/-0.172, 0.333/0.267, 0.239/0.422 vs 1.19; K2 anchor -0.389..-0.664 | 缓存预测直接进书：评估 `predictions_*_WX_H63.parquet`，作为对冲后的多空输入，在统一成本模型里报 beta 中性净夏普 |
| 2 | `overnight_return_persistence_auction` | A | long_short_decile | ON252 decile LS main +13.69 bp/night NW t 5.19, stress +17.35 t 12.02, placebo beat 1.00 (dv21 1501-3000); P500 LS +17.0 bp/night t 3.26; gate B delta_lo20 -5.88 bp/night vs -4 bar | S1_INPUT（快信号 on252，现在只给 ML）：升级为受检的书输入，周度调仓、开盘到开盘成交 |
| 3 | `signal_library_v1_price_anomalies` | A | standalone_long_only_stock | low idiosyncratic volatility (IC 0.052, t=3.4), low MAX (0.041, t=2.7), near 52-week high (0.041, t=2.4); 2017-2026 PIT top-3000 | S2：加入 neg_maxret 和 52 周新高接近度；neg_idio_vol_63 已在 S1 |
| 4 | `ml_ranking_liquid500_recent_vs_momentum_rule` | A | model_ranking_long_only | top-40-by-recent-ICIR screened set validation IC 0.035 (shuffled-label placebo 0.004); top-50 book 17.5-19.4% annualized vs rule 33.7%; FDR pass: Alpha158 29, Alpha101 10, Alpha191 5, OSAP 2, Reversal Trend 0 | S2：补完 alpha158_broad，先测 29 个过 FDR 的 Alpha158 因子对 S1 的边际 IC |
| 5 | `insider_buy_independent_broad_universe` | A | event_study | any60 most-illiquid band 1-month hold, 42 usable months from 2023-04: +114.0bp/month vs same-band equal-weight (t=2.412), -15.2bp/month vs SPY (t=-0.204) | S1_INPUT（insider 主题）：在书里按流动性三分位看，效应在低流动性带 |
| 6 | `insider_cluster_buy_top500` | A | event_study | +0.78% excess return over 20 sessions (t=5.0 across event dates; beats 20 redated placebos); calendar-time book +2.4%/yr over the universe; top-500 weekly 0.15% CAR at 20d, t=0.78 | S1_INPUT（cmp_opp_buy_60d、nonplan_buy_mcap_60d）：保留在 M0，看组合器给多少权重 |
| 7 | `crypto_weekend_to_monday_equity_transmission` | A | event_study | W<0 minus W>=0 Friday-close to Monday-open gap: QQQ -51 to -62 bp (Welch t -3.0 to -4.6), SPY -36 to -45 bp (t -2.7 to -4.4); after the open 0/12 cells pass | TIMING_OVERLAY：用 Alpaca 周日晚隔夜时段成交做新合同下的测试，作为周一缺口/beta 调节 |
| 8 | `reversal_trend_daily_signals` | A | event_study | after a daily bull signal stocks trail the universe by 0.40% over 5 sessions (t=-3.7, beats 20 redated placebos) | S2（做空侧/回避）：rt_bull_signal 的 5 日反转，先查与 rev_21_ind 的相关 |
| 9 | `sec_xbrl_accounting_signals_v1` | A | standalone_long_only_stock | ROE admitted (IC 0.026, t 3.0; 2024+ IC 0.021; T2 top-30 book +4.5%/yr excess full, +4.7% 2024+ at 20 bp); gross profitability (IC 0.019, t 2.2, 2024+ 0.006) | S1_INPUT（roe、gp_at）：已在 M0 质量主题 |
| 10 | `cross_sectional_gap_fade` | A | long_short_decile | gross 2016-2021 +99.0% / Sharpe 3.01 reproduced; decomposed gross short-leg edge +11.5bp/day vs realistic cost+borrow of -38.5bp/day; liquid tiers E_off 7.09 bp/day (90% CI -2.1..16.0) < 8 bp bar | S2（只进快层）：1 日信号，换手近 100%，进周度书的价值有限 |
| 11 | `dash_for_cash_settlement_timing` | A | event_study | M3 theta 125.7 bp, t 3.05 (2026 out-of-paper 120.7 bp, t 1.58); D1-SPY net Sharpe 0.27 stress / 0.39 anchor; DFC_U anchor Sharpe -0.50 / DFC_C -0.10 | TIMING_OVERLAY：月末结算日历特征 x 12 月输家，作为组合器的日历特征 |
| 12 | `levered_single_stock_momentum_top_k` | A | standalone_long_only_stock | 5 of 12 mechanism candidates clear K1 anchor (best LSS_N50_K3_1X 1.4415) but stress best 0.6425-0.6653 vs 0.6447 bar; random-pick placebo anchor 0.7181, EW control 0.975; best K2 edge +0.0363 | S1_INPUT（mom_12_1）：已有，不再单独做 |
| 13 | `composite_momentum_quality_v1` | B | standalone_long_only_stock | momentum + low idio vol + low MAX + near 52w high has IC 0.050 (vs 0.020 for momentum) but the book turns defensive: 9.3%/yr, max DD -29%, -5%/yr vs the universe | S1_INPUT：4 信号合成 IC 0.050 是 M0 必须打败的参照 |
| 14 | `skewness_preference_52wk_high_pwb` | B | standalone_long_only_stock | dist_from_252d_high top-95 monthly: anchor Sharpe 0.82, stress Sharpe 0.54 (need >=1.19/>=0.65); K2 edge -0.008 anchor / -0.014 stress; published LS 14.22% CAGR / Sharpe 1.11 | S2：与第 3 行同一个 52 周新高信号，合并做 |
| 15 | `small_cap_background_drift_short_basket` | B | long_short_decile | SSD_IWM_M252 anchor median Sharpe after 10 bp and 0.5%/yr borrow = 0.390 (gate 0.6), stress 0.554, DSR 0.19; unhedged short IWM -0.886; paper Sharpe 1.35 (0.78 at 20 bp) | TIMING_OVERLAY（规模因子倾斜）：小盘减大盘的趋势作为组合器特征 |
| 16 | `llm_hypothesis_code_backtest_loop` | B | model_ranking_long_only | F10 TEST rank IC 0.0274 vs zoo 0.0217 (Alpha158 CORD60); TEST 20bp top-50 book Sharpe 0.640 vs 0.879 | LLM_TEXT_ASSET：复用 12 个 Claude 写的因子面板（尤其 insider/short 类 F01/F08/F09/F12）作为 S2 输入 |
| 17 | `jump_model_regime` | B | sizing_overlay | independent replication: SPY 2008-2025 9.13% / -22.5% / 0.922 vs SPY 11.55% / -51.5% / 0.649; paper Sharpe 1.43 not reproduced | TIMING_OVERLAY：统计跳跃模型的状态概率，作为书的总敞口调节和组合器的状态特征 |
| 18 | `equity_momentum_concentrated_pwb` | B | standalone_long_only_stock | momentum_concentrated_k37: anchor Sharpe 1.03 (need >=1.19), stress Sharpe 0.51 (need >=0.65); K2 edge -0.143 anchor / -0.071 stress | S1_INPUT（mom_12_1） |
| 19 | `composite_momentum_roe_v2` | B | standalone_long_only_stock | C4 17.0%/yr, Sharpe 0.73, DD -36.8% vs same-universe momentum 29.0%/yr, Sharpe 0.82, DD -49.8% | S1_INPUT（mom_12_1、roe） |
| 20 | `step10_xsmom_pit_liquidity_liquid500` | B | standalone_long_only_stock | 0/4 candidates clear the frozen contract; benchmark_vm_capture_ratio 0.09-0.19 (legacy) vs 0.97-0.999 (corrected) | S1_INPUT（mom_12_1）：门槛是 capture 比率缺陷，不是信号被否 |
| 21 | `defense_first_taa_carlson_concretum` | B | standalone_long_only_etf | median-offset Sharpe anchor 1.48 / stress 0.73, corr with S3 0.27-0.30; combo stress edge only +0.04 | TIMING_OVERLAY（可选回撤对冲）：机主已不让它做 sleeve |
| 22 | `cross_asset_trend_sleeve_with_s3` | B | standalone_long_only_etf | D1 anchor edge +0.575 but stress edge +0.037 (<0.05 bar); D2 anchor edge +0.637 but stress edge -0.227 | TIMING_OVERLAY（同上） |
| 23 | `factor_style_etf_momentum_rotation` | B | standalone_long_only_etf | 12 candidates -- 0 K1, 0 K2; best FACTOR_L252_N1_WK anchor Sharpe 1.437 vs bar 1.1882 | TIMING_OVERLAY（风格因子倾斜） |
| 24 | `meta_strategy_trailing_return_rotation` | B | sizing_overlay | top-3 bucket compounded ~19.9%/yr vs ~7.3%/yr for the bottom-3 (14 TAA strategies, 1992-2026, 389 months) | TIMING_OVERLAY（按主题近期收益加权的组合器变体） |
| 25 | `dividend_payment_price_pressure` | B | event_study | top-quintile abnormal dividend payment days ~8 bp/day vs ~2 bp; top 2 weeks earns ~1.4% a year (published) | TIMING_OVERLAY（数据缺：应付日）；暂不做 |
| 26 | `groupb_recent_regime_screen` | B | intraday_rule | F1 7/8 gates pass, 11/11 positive quarters; cagr_recent_net 9.1% vs required (value truncated) | DEAD：ETF 回调反转，技术规则 |
| 27 | `crypto_trend_btc` | B | standalone_long_only_etf | BTC_DONCHIAN_ENSEMBLE_VT40 anchor Sharpe 0.906 (need >=1.19), stress 0.706 (clears 0.65); K2 anchor edge +0.164, stress edge -0.064; paper BTC net 30% CAGR / Sharpe 1.56 (2015-2025) | DEAD（对股票书）：加密货币趋势是另一条线 |
| 28 | `dual_class_share_arbitrage_pwb` | B | long_short_decile | gross Sharpe positive (anchor 0.50-1.05, stress 0.53-1.31) but net anchor -0.942..-0.015, net stress -0.242..0.133; mirror placebo -2.24..-0.86 | DEAD：只有约 10 对，不是截面信号；NBBO 半价差 < 2 bp 才重开 |

读法：前 12 行（等级 A）是这次审计的主要发现。它们的共同点是：效应在多空、同池对照或 IC 上成立（t 值 2.4 到 12.0），却被“只做多、单独成策略、过 S3 参照门槛、下一开盘成交”这些单位杀掉。对冲后的多信号书正是这些信号该去的地方。

第 7 行（crypto 周末）和第 11 行（dash for cash）的差异：前者的效应出现在周一开盘之前，要换成周日晚成交合同才能测；后者在 pre-window 上不成立（NW t -0.86），只能当弱日历特征。

## 3. 前 15 个 S2_CANDIDATE（书的新输入）

排序分 = 证据强度 E（A=3，B=2，C=1）x 数据就绪度 R（磁盘上已有且覆盖够=3，部分=2，没有=1）x 与 S1 的低相关度 D（含与周度书的期限匹配；高相关或期限不配=1，中=2，低=3）。分数是启发式，只用来排序，不是统计量。

| # | 信号 | E | R | D | 分 | 数据表（是否已在磁盘上） | 时点问题 | 一行构造 |
|---|---|---|---|---|---|---|---|---|
| 1 | Alpha158 里过 BH-FDR 的 29 个因子（`ml_ranking_liquid500_recent_vs_momentum_rule`） | 3 | 2 | 2 | 12 | `data/features/alpha158`（610 万行，156 列，2016-01-04..2026-09-08，已存在）；`alpha158_broad` 只有 `_scratch`，年度文件还没生成 | 因子由日线 OHLCV 构造，时点上没问题；风险是“近期 ICIR 前 40”这种筛选本身带选择偏差，必须在 walk-forward 里重筛；因子之间高度共线 | 用 Alpha158 的 29 个过 FDR 因子做截面 z 分，行业内去均值，并回归掉 S1 的 22 个慢信号取残差，测边际 IC |
| 2 | 收益-盈余缺口反转（REG）（`return_earnings_gap_reversal_ben_rephael_2024`） | 2 | 2 | 3 | 12 | `daily_broad` + `sec_fundamentals_daily`（sue_eps、申报日，2016+，已存在）；`earnings_events` 只有 2024 起 | 财报公告日不等于申报日：2016-2023 只能用 10-Q/10-K 申报日近似，会把公告后的漂移混进去；必须用 usable_session，不能用申报当天收益 | REG = 财报日窗口收益 - 由 SUE 推出的应得收益，取负号（约一半的缺口在随后数月反转），月度或更慢调仓 |
| 3 | 无新闻大幅波动反转 / 新闻后漂移（`no_news_price_shock_reversal_chan`） | 2 | 2 | 3 | 12 | `news_hf_reaction`（news_return、non_news_return，8,027 个代码，2024-01..2026-09-09，已存在）；`news_packets` 带 visible_at | 只有 2024 年起，没有压力窗；“没有新闻”是缺失状态，新闻覆盖随时间变化会造成假信号；本地短期（1-5 日）测试已全部失败，只剩月度期限没测 | 21 日 non_news_return 的反转分（取负号）加 21 日 news_return 的漂移分，行业内标准化，月度期限 |
| 4 | MAX（取负）与 52 周新高接近度（`signal_library_v1_price_anomalies`） | 3 | 3 | 1 | 9 | `osap_price_broad.maxret`；52 周新高从 `daily_broad` 算（都已存在，到 2026-09-17） | 时点上只用过去价格；必须先过 `sanitize_price_matrices`，坏价会直接抬高 MAX；52 周新高要用拆股调整后的价格序列 | neg_maxret = -（近 21 日最大单日收益），dist_52w = close / 近 252 日最高 - 1，各自 winsorise 后做正态分，行业内中性 |
| 5 | Reversal Trend 日线 bull 信号（做空/回避侧）（`reversal_trend_daily_signals`） | 3 | 3 | 1 | 9 | `reversal_trend_broad`（rt_bull_signal、rt_rsi14、rt_macd_hist 等，已存在，到 2026-09-17） | 只用价格，无时点问题；很可能只是短期反转的另一种写法，与 `rev_21_ind` 高度相关 | rt_bull_signal 在最近 5 个会话内触发则取 -1，否则 0，作为负向特征放进快层；先测与 rev_21_ind 的残差 |
| 6 | 13D 新申报标记（`event_13d_drift`） | 1 | 3 | 3 | 9 | `sec_13d`（visible_session、entry_session、percent_of_class，已存在） | 申报的 acceptance 时间到可见会话的映射、`issuer_verified` 的可信度；公告日收益 +1.73%（t=4.15）在下一开盘前基本被吃掉，事件只有 787 个 | 过去 60 个会话内出现新 13D（Item 4 为活动人士意图）记 1，其余 0，小权重输入；不单独成策略 |
| 7 | JKP 会计变动因子（ocf_at_chg1、niq_at_chg1、noa_gr1a）（`jkp_accounting_change_factors`） | 2 | 2 | 2 | 8 | `sec_fundamentals_daily`（OCF、净利润、总资产，已存在）；库存/应收等字段不确定（not found） | 首次披露值，申报后下一会话可用；季度同比变动需要上年同季值，后期重述会造成偏差 | ocf_at_chg1 = 经营现金流/总资产 的同比变动，niq_at_chg1 同理，行业内去均值，季度调整 |
| 8 | 1 日跳空反转（快层）（`cross_sectional_gap_fade`） | 2 | 3 | 1 | 6 | `gap_panel.parquet`、`intraday_daily`（已存在，到 2026-09-04） | 用官方开盘价；信号对 1 日有效，换手近 100%，扣成本后原始单位已死（毛 +11.5 bp/天 对 -38.5 bp/天） | 前一日收盘到当日开盘的跳空，取负号，只进 ML 快层，不进周度书的慢合成 |
| 9 | Lazy Prices：10-K/10-Q 文本年度变化（`lazy_prices_10k_changes`） | 2 | 1 | 3 | 6 | 磁盘上没有 10-K/10-Q 正文；`data/raw/sec_submissions/submissions.zip` 有申报索引（含 acceptanceDateTime 和 primaryDocument），`data/raw/earnings_text` 只有 8-K Ex-99 | 需要申报的 acceptance 时间戳，下载量大（U3000 约数万份）；不用 LLM，CPU 即可 | 每份 10-K/10-Q 与上年同期同章节的余弦相似度，取负号（变化越大越差），申报后下一会话生效 |
| 10 | 8-K Item 4.02 非依赖/重述回避标记（`event_8k_item402_restatement_drift`） | 2 | 1 | 3 | 6 | Item 4.02 的元数据没有解析（not found）；`earnings_events` 只有 8-K 2.02、2024 起；`data/raw/sec_submissions/submissions.zip`（99 万个 CIK 的 JSON，含 items 和 acceptanceDateTime，已核对）有 8-K 的 items 字段 | 需用 acceptance 时间；事件每年很少，只适合做否决项 | 过去 20 个会话内有 Item 4.02 申报则把该股 alpha 压到 0 或限制做多 |
| 11 | 期权 IV 价差 / 风险中性偏度（`alpaca_free_options_iv_signals`） | 2 | 1 | 3 | 6 | 没有可用的历史报价：`data/raw/alpaca_options_probe` 只有 570 个 name-day，覆盖 31-39%，IV 价差符号反了；DoltHub 覆盖率 0.54-0.62 未过验收（需 0.85） | 需要买卖报价而非稀疏成交价；必须有 quote 时间戳 | 认购与认沽隐含波动率之差，截面标准化；数据源解决前不动 |
| 12 | OSAP 非价格特征（200 多个会计/事件特征）（`osap_ml_ranking`） | 2 | 1 | 2 | 4 | `data/raw/osap/signal_doc.parquet`（331 行，只有说明，没有数值）；OSAP 数值文件没有（not found）；缺 permno 到代码的映射 | OSAP 以 permno 为键，发布滞后约定要逐个核对；用本地 SEC 数据重算是替代路径 | 先重算有 SEC 字段可得的 20-30 个会计类 OSAP 特征，不等 permno 映射 |
| 13 | 符号跳跃变差（RSJ）（`signed_jump_variation`） | 2 | 1 | 2 | 4 | 原始分钟线 `data/sip/minute`（29 GB，需要 Modal）；`minute_panel` 只有 SPY | 日内数据的复权基准要和日线一致（已有踩坑记录：NKE、RF、KEY、TSN 约 1%）；效应集中在低流动性股票 | 5 分钟收益的上行半方差减下行半方差，除以总方差，取负号 |
| 14 | 净回购收益率（实际回购金额）（`buyback_execution_vs_announcement`） | 1 | 2 | 2 | 4 | `data/raw/sec_xbrl/companyfacts.zip`（1.4 GB，已存在）里有 PaymentsForRepurchaseOfCommonStock，但未抽进 `sec_fundamentals_daily` | XBRL 的累计口径（YTD）要还原成单季；用申报后下一会话可用 | 净回购收益率 = 近 4 季回购金额 / 市值，与 neg_nsi_12m 比较边际 IC |
| 15 | 名义股价（log price）（`nominal_price_anomaly_pwb`） | 1 | 3 | 1 | 3 | `osap_price_broad.log_price`（已存在） | `daily_broad` 的收盘价是事后拆股调整的，历史名义价被低估；必须用成交时的未调整价 | -log(当日未调整收盘价)，行业内标准化；很可能与规模/特质波动相关，先看相关再决定 |

说明：
- 第 4 行同时吸收了 `skewness_preference_52wk_high_pwb`（52 周新高，发表的多空夏普 1.11；本地只做多版本 K2 边际 -0.008）。
- 没进前 15 的 S2 行：专利事件（数据没有，要写匹配器）、拆股公告（数据没有）、期权隐含方差溢价（数据没有）、资本利得动量/无股息动量（股息历史不在磁盘上）、波动率调整动量与 Clenow 斜率（与 mom_12_1 高度相关，边际价值低）、尾盘反转（要分钟线）。
- 磁盘上已有但登记簿里没有单独编号的 OSAP 价格列：`coskew_252`、`pricedelay_rsq`、`lrreversal`、`momseason_*`、`trend_ma*`（`osap_price_broad`）。登记簿里 OSAP 价格库只有“2 个过 FDR”的汇总数字，没有逐列数字，所以本审计没有给它们排名（not found）。

## 4. TIMING_OVERLAY 候选和进书方式

进书方式三类：**总敞口/波动缩放**（书的总敞口乘一个系数，由优化器的风险目标吸收）、**因子倾斜**（改主题权重）、**组合器状态特征**（给 M2/M3 的模型当输入）。

| 方向 | 等级 | 证据 | 进书方式 | 数据 |
|---|---|---|---|---|
| `jump_model_regime` | B | 统计跳跃模型（SPY 2008-2025：夏普 0.922 对 0.649，回撤 -22.5% 对 -51.5%；论文夏普 1.43 没复现） | 总敞口缩放 + 组合器状态特征 | `regime_daily` + SPY 日线；CPU 可做 |
| `letf_multi_signal_regime_vote` | C | 多信号投票（趋势/广度/VIX/信用/金丝雀），作者自报 16.8% 对 SPY 13.9%（未验证） | 总敞口缩放 + 状态特征 | `regime_daily` 的 spy_gap_200sma、breadth_50d、vix_close、cs_dispersion_21（到 2026-09-04） |
| `crypto_weekend_to_monday_equity_transmission` | A | 周末加密货币负收益预测周一缺口（QQQ -51 到 -62 bp，t -3.0 到 -4.6），但在周一开盘前 | 周日晚的 beta/总敞口调节；需要新的执行合同 | `data/research/crypto/session_prices.parquet`；执行要测 Alpaca 周日 8 PM ET 隔夜时段 |
| `dash_for_cash_settlement_timing` | A | 月末结算窗口，单日 theta 125.7 bp（t 3.05），但 pre-window 不成立 | 组合器日历特征，与 12 月输家动量交互（因子倾斜） | `daily_broad` + 结算日历；弱 |
| `small_cap_background_drift_short_basket` | B | 小盘相对 SPY 的背景漂移，beta 对冲后 IWM 夏普 0.390/0.554 | 因子倾斜（规模因子趋势） | `etf_daily`（IWM、SPY） |
| `factor_momentum_timing_decay` | C | Blitz：短期因子动量 2.8%/年（t=4.9）全样本，2011 后 0.4%/年 | 因子倾斜：主题近期收益作为组合器特征，不单独做 | S1 主题得分 `theme_*` |
| `factor_style_etf_momentum_rotation` | B | 5 个风格 ETF 仅锚窗过线（最好 1.437），压力窗不过 | 因子倾斜 | `etf_daily`（MTUM、QUAL、USMV、VLUE、SIZE） |
| `owner_multifactor_timing_deep_learning_2026` | C | 论文深度模型夏普 0.82 对 0.60（1990-2021），后期衰减 | 因子倾斜（先验：衰减） | S1 主题得分 |
| `meta_strategy_trailing_return_rotation` | B | 策略层面的动量：前 3 名约 19.9%/年，后 3 名约 7.3%，但输给等权 | 因子倾斜：按主题近期收益加权的组合器变体 | S1 主题得分 |
| `pension_rebalancing_front_run_equity_leg` | B | 全样本 t -2.84，压力窗 -2.68，2024 起 -0.84 | 组合器状态特征（弱，2024 起不成立） | `etf_daily`（SPY、债券 ETF） |
| `step10_beta_exposure_vol_managed_router` | C | 最好超额年化 +0.99pp，夏普没有提升 | 总敞口缩放（由优化器风险目标取代，不单独做） | `regime_daily`、`etf_daily` |
| `defense_first_taa_carlson_concretum` | B | K1 通过（锚窗 1.48，压力窗 0.73，与 S3 相关 0.27-0.30），K2 压力窗 +0.04 | 回撤对冲 sleeve（股票书之外）；机主已不要跨资产 sleeve | `etf_daily`（TLT、GLD、DBC、UUP） |
| `cross_asset_trend_sleeve_with_s3` | B | 同上：锚窗边际 +0.575，压力窗 +0.037 | 同上 | 同上 |
| `dividend_payment_price_pressure` | B | 高分红日约 8 bp/天对 2 bp | 日历总敞口；数据缺（应付日） | no |

建议顺序：先做 `jump_model_regime` 和 `letf_multi_signal_regime_vote`（都只用 `regime_daily`，成本最低，直接对应书的总敞口），再做周日晚隔夜合同下的周末加密货币测试（证据最强，但需要新的执行合同；只涉及纸面模拟）。因子倾斜类先验都是“衰减”，只当组合器特征，不单独立项。

## 5. MODEL_ASSET 与 LLM_TEXT_ASSET 清单和状态

### 5.1 MODEL_ASSET（登记簿里只有 1 行；其余缓存按磁盘检查补列）

| 资产 | 路径 | 状态 | 覆盖 | 时点特征包 |
|---|---|---|---|---|
| T-17b/T-19 滚动预测（LightGBM W3_H21、LightGBM/XGBoost/CatBoost WX_H63） | `reports/research/iterations/t20260930_17b_model_family_book/cache/predictions_{LGBM_W3_H21,LGBM_WX_H63,XGB_WX_H63,CAT_WX_H63}.parquet` | 已训练并缓存；列 trade_date、symbol、adv_tercile、adv_rank、prediction、fold_id；36-37 个折（共 40-41 个槽）；每个 76-93 MB | WX_H63：787 万行，2017-10-02..2026-09-17；W3_H21：806 万行，2017-07-03..2026-09-17 | 没有特征包；特征是 `daily_broad` 价量派生，按构造时点正确，折间留间隔。纯价量，登记簿禁止再加新模型族 |
| T-17 验证 IC 缓存与折元数据 | 同目录 `val_ic_*.parquet`、`fold_meta_*.json`、`ret_*_V1_o*.parquet`（21 个调仓偏移的收益） | 已缓存 | 压力窗 2016-05..2023-08 | 同上 |
| 不确定性门集成预测 | `reports/research/iterations/h20260928_14b_uncertainty_gate/cache/ensemble_predictions.npz`（7.1 MB，对象数组，未打开） | 已缓存，内容与覆盖没有核对（not found）；对应的门已被否（AUROC 0.522） | not found | 否 |
| 元标签预测 | `reports/research/iterations/h20260916_03_meta_label/predictions.parquet`（19.7 万行；rebalance_date、symbol、variant、model、quarter、p、label） | 已缓存；方向已否 | not found | 否 |
| 多季度 SUE 弹性网得分 | `reports/research/iterations/h20260929_11_multiq_sue/scores.parquet`；特征 `data/features/h20260929_11_multiq_sue/{open,close}.parquet` | 已缓存；已否（RankIC -0.0055） | 2019 起 | 否 |
| 图表 CNN | Modal 卷 `oc-data` 里的检查点；脚本 `scripts/modal_cnn_chart.py` | 已训练；已否（rank IC 绝对 t 小于 1.5） | 2016-2019 训练，2020-2026-09-25 预测 | 否 |

用法：第一行是目前唯一能直接喂书的模型资产。T-19 的结论是池内排序有效（压力窗 RankIC t 3.1，低流动性三分位 5.75，随机排序对照被打赢 1.00），长仓失败是因为 2024-26 低流动性池整体不赚钱，对冲后该问题可以去掉。书需要的下一步：对预测按成本模型、借券代理和风险模型做 beta 中性的净值，不是再训练。

### 5.2 LLM_TEXT_ASSET

| 资产 | 路径 | 状态 | 覆盖 | 时点特征包 |
|---|---|---|---|---|
| 新闻原文包 | `data/features/news_packets/{2024,2025,2026}.parquet` 和 `_daily/`（983 个日文件） | 原始文本，未评分；列 id、created_at、symbols、headline、summary、source、url、visible_at、fetched_at | 约 68.5 万行（26.2 万/24.9 万/17.4 万）；日文件 2024-01-01..2026-09-09；少量更早记录 | 有 visible_at，但不是特征包 |
| 新闻关注度/反应特征 | `data/features/news_attention`（1,237 个代码），`news_hf_reaction`（8,027 个代码） | 已构建（不用 LLM） | 2024-01..2026-09-09 | 有 visible_at；news_attention 已在 S1 快层 |
| 新闻事件 LLM 特征包 | `data/features/news_events/2024.parquet` | 只有 5 行（id、event_type、stated_direction、company_specific、confidence、model_id、knowledge_cutoff、prompt_hash、extracted_at） | 5 行，样例 | 这是特征包的格式模板，但几乎是空的 |
| 8-K 财报新闻稿语气分 | `data/features/earnings_text_scores/{2024,2025,unknown}.parquet`；原文 `data/raw/earnings_text`（335 MB，1,396 家公司） | DeepSeek-v4-flash 已评分：2024 年 2,087 条成功/62 失败；2025 年 138/2；200 条无日期 | 2024-01-03..2024-05-06；2025-01-02..2025-01-22 | 有 acceptance_utc、prompt_sha256、neutralised_text_sha256；方向已否（t 0.59） |
| 8-K/GDELT 情绪加速度分 | `data/features/h20260928_16_sentiment_accel_scores/items.parquet`；缓存 `data/research/llm_cache/h20260928_16_8k_sentiment_accel`（2,092 条） | 已评分；IC 结果没有找到，决策记录仍写 pending | 2026-04-01..2026-06-30（一个季度） | 有 visible_at、prompt_version、item_hash |
| 8-K 风险分 | `data/features/h20260928_17_filing_risk_labels_scores/items.parquet`；缓存 `.../llm_cache/h20260928_17_filing_risk_labels`（436 条） | 已评分；50 只股票 x 8 季度，已否（与安慰剂分不开） | visible_at 2024-07-03..2026-06-05 | 有 visible_at、prompt_version；是时点特征包的最完整样本 |
| 新闻动量重排分 | `data/features/h20260928_22_news_momentum_scores/items.parquet`（1,451 条）；缓存 `.../llm_cache/h20260928_22`（1,428 条） | 已评分；已否 | 2025-03..2026-09 的月末 | 有 asof、prompt_version、item_hash |
| Claude 写的 12 个因子面板 | `data/features/h20260928_15_claude_factors/F01..F12`（共 280 MB） | 不是 LLM 评分，是 LLM 写的公式在价量/insider/short/SEC 数据上算出的面板；F10 测试窗 rank IC 0.0274 | 2016-2026 | 数据是时点的；没有特征包 |

总判断：文本层现在没有一个能进书的 LLM 信号。可复用的是三样：格式（visible_at + prompt_hash + 缓存）、新闻原文包（可重新评分）、12 个因子面板。已记录的约束：不用 Claude token 做批量标注，评分走已配置的 DeepSeek 端点（有滚动调用上限）。

## 6. SLEEVE 与 INFRA

### SLEEVE（保持原样，不动）

- `s3_levered_rotation_voltarget_dip_boost`：S3 paper sleeve (levered ETF rotation, vol-target 40%)；Only direction that cleared G1-G5; edge is semis exposure (58.5% anchor / 69.4% holdout weight).
- `s2_growth_rotation_voltarget`：S2 growth-rotation paper sleeve (ETF)；Edge is the vol-target overlay, not selection (random-pick placebo 23.3%); paper sleeve already live.
- `recent_window_etf_menu_rotation`：S1 sector rotation, S2 growth rotation, S3 levered rotation paper sleeves；S1 sector rotation has the strongest ranking evidence (2% placebo win); S2 is mostly menu choice (20%), S3 leverage plus weak ranking (25%).
- `end_of_month_reversal_effect`：C2 paper sleeve E0 leg (SPY)；E0 is the half of the live C2 sleeve; 2026 YTD Sharpe -0.57 so the anchor number comes from 2024-25 only.
- `front_running_sector_seasonality`：C2 paper sleeve S0 leg (9 sector SPDRs)；S0 leg of the live C2 sleeve; random-shift placebo beaten on the anchor window but not on the select (0.38) or stress (0.64) windows.

### INFRA

- `ml_ranking_broad_universe_custom`（signal_absent）：scripts/modal_app.py, scripts/run_t20260930_17_model_family_sweep.py; features: daily_broad, sec_fundamentals_daily, insider_broad, short_interest, short_volume_broad。动作：Reuse the Modal walk-forward training harness for the M2/M3 combiner; do not rerun this candidate set
- `broad_universe_delisted_backfill_infra`（passed_or_live）：data/features/universe_broad (9,191 symbols, 2016..2026-09), daily_broad; data/raw/sec_ma/cik_symbol_history.parquet。动作：Keep as the base universe for the book
- `options_data_deferred_owner_decision`（not_tested）：data/raw/alpaca_options_probe (20 names x 3 months, sparse)。动作：Revisit options data capability now that the owner's 2026-09-29 scope covers options Levels 1-3
- `cogalpha_llm_code_alpha_generation`（not_tested）：no code on disk; method only。动作：Fold the 5-dimension candidate filter (predictive power, stability, robustness, financial logic, diversity) into the signal-admission checklist; reimplement, do not clone
- `alphaeval_backtest_free_prescreening`（not_tested）：no code on disk; method only。动作：Use the backtest-free stability and diversity checks as a cheap pre-screen before adding S2 signals to the combiner
- `risk_based_portfolio_construction_pwb`（not_tested）：open_composer/research/equity_book/risk (risk model) and optimize.py exist。动作：Use the 11-paper list as a checklist for covariance shrinkage and risk-parity variants in the optimizer; no stock-selection content
- `s3_rebalance_timing_luck_tranching`（signal_absent）：scripts/screen_lane.py (21-offset evaluation)。动作：Keep all-offset (date-neutral) reporting as the book backtest rule
- `s1_s2_rebalance_timing_luck`（signal_absent）：scripts/screen_lane.py。动作：Keep all-offset reporting; no further work
- `short_leg_anomalies_etb_borrow_cost`（not_tested）：data/research/equity_book/borrow (exists)。动作：Use as a prior for the borrow-cost model: assume anomaly short-leg profit concentrates in hard-to-borrow names

## 7. DEAD 汇总（按家族）和重开条件

| 家族（category） | DEAD 行数 | 主要死因 | 重开条件（来自登记簿 reopen_if 的摘要） |
|---|---|---|---|
| factor | 26 | not_tested 11，signal_absent 8，execution_or_data_infeasible 6，signal_real_unit_killed 1 | 欧洲/新兴/前沿市场要有数据和经纪路径；双重股要 NBBO 半价差 < 2 bp；付费 ESG/Shariah 数据 |
| etf_rule | 25 | signal_absent 18，not_tested 5，execution_or_data_infeasible 1，signal_real_unit_killed 1 | 已发表规则要有 2023-2025 内的实盘记录；跨资产要机主授权；ETF 菜单要加相关度上限和杠杆过滤 |
| model | 24 | signal_absent 12，not_tested 6，execution_or_data_infeasible 4，superseded_or_duplicate 2 | GPU 加美股样本外验证；纯价量模型只有加新数据层或新目标才重开（不因换模型族重开） |
| intraday | 16 | signal_absent 12，execution_or_data_infeasible 3，not_tested 1 | 分钟级微观结构数据与成交模型；期货通道；允许日内 >1 倍杠杆；周一 12:00 价格源 |
| event | 15 | signal_absent 11，execution_or_data_infeasible 2，not_tested 2 | 公告后更早的入场点；新的发表后研究证明仍显著；自由的 FDA/指数调仓日历 |
| levered_etf | 13 | signal_absent 7，not_tested 6 | 规则公开或有独立验证的实盘记录；整份论文文本；真正的 VX 期货曲线信号 |
| alt_data | 13 | execution_or_data_infeasible 6，signal_absent 4，not_tested 3 | 机主批准企业级数据订阅；或自由的时点分析师预期历史 |
| sizing | 11 | signal_absent 10，not_tested 1 | 一个与敞口匹配对照比较过的回撤信号，或独立样本外记录 |
| options | 9 | execution_or_data_infeasible 6，not_tested 2，signal_absent 1 | 带买卖报价的历史期权数据（付费来源或 DoltHub 覆盖率达 0.85）；Alpaca 支持多腿条件单 |
| text_llm | 7 | execution_or_data_infeasible 4，not_tested 3 | 转录文本来源；机主重开 LLM 网络搜索预算；美股样本外验证 |
| crypto | 6 | signal_absent 3，signal_real_unit_killed 1，not_tested 1，execution_or_data_infeasible 1 | 做市商成交（<= 2 bp/边）；2024 后长仓横截面证据过锚窗门槛；DAT 历史再积累约 2 年 |
| hf_factor | 5 | signal_absent 4，not_tested 1 | 2015 后的样本外记录；US 复制；更早时间戳的新闻源 |
| other | 3 | not_tested 2，execution_or_data_infeasible 1 | 公开规则；不可复制的竞赛成绩不算 |

DEAD 合计 173 行，占 256 行的 68%。其中 3 行（dual_class_share_arbitrage_pwb、crypto_trend_btc、groupb_recent_regime_screen）的 failure_class 是 signal_real_unit_killed，但因为不是股票截面信号，对股票书没有复用价值。

技术指标规则（RSI、MACD、布林、均线交叉、Pine 指标）一律 DEAD，没有截面证据：`reversal_trend_hourly_selection_alpha`、`reversal_trend_user_indicator`、`ema_crossover_atr_paper_track`、`etf_dip_reversion_ibs_connors`、`composer_rsi_branch_uvxy`、`moving_average_volume_heuristic_pwb`、ORB 系列。例外：`reversal_trend_daily_signals` 有对全市场的事件检验（5 日 t=-3.7，通过 20 个重定日期安慰剂），所以进了 S2 做空/回避侧。

## 8. 不确定与未能分类

- **范围**：264 个 id 中 8 个不在任务范围（4 个 duplicate：`precious_metals_levered_trend`、`etf_dual_momentum_rotation_gem_pools`、`cn_ashare_etf_rotation_posts`、`owner_automate_strategy_finding_llm_emnlp_2025`；4 个不在指定类别的 harvested/queued：`kaggle_jane_street_numerai_competition_methods`、`multi_signal_risk_controlled_equity_book`、`iv_hv_spread_stock_ranking_dolthub`、`industry_relative_momentum_and_peer_earnings_spillover`）。后两个 queued 的因子行是潜在 S2 候选：IV-HV 价差排序（数据受期权源限制）和行业相对动量 + 同行盈余外溢（行业分类已有 `sic_map`/风险模型）。
- **没有找到数字，写了 not found 的**：`llm_8k_gdelt_sentiment_acceleration` 的 IC（评分已跑，没有结果文件）；`minute_bar_momentum_multipath` 的 R3/R4 数字。
- **单位判断不确定**：`gtja191_alpha_formulas` 的 FDR 检验我归为 `other`（IC 筛选），登记簿没有直接说“十分位多空”；Step 15 另有 17 个 GTJA 因子 t>2 的记录，与“近期 0/16 通过”口径不同（全样本 vs 近期），我按近期口径判 `signal_absent`。
- **等级边界**：`composite_momentum_quality_v1` 给了 IC 0.050 但没有 t，所以降为 B；`ml_ranking_liquid500` 的验证 IC 0.035（安慰剂 0.004）也没有 t，仍给 A 是因为有安慰剂对比，可以降级。`signal_real_unit_killed` 里 B 级的行（16 行）证据弱，只能作先验。
- **近期失效 vs 单位被杀**：`net_share_issuance`、`pead_xbrl_sue_filing_date`、`pension_rebalancing_front_run` 全样本显著而 2024 起不显著，我判 `signal_absent`（近期窗口）。如果书的窗口是全样本，它们应改判。
- **数据状态来自元数据**：只读了 parquet 的页脚/列统计，没有加载大表；`alpha158_broad` 目录下没有年度 parquet（只有 `_scratch`），复审文档 2.1 写的是“只建了 2016 年”，磁盘上连 2016 年的文件也没有，建议核对构建任务状态。`regime_daily` 到 2026-09-04，早于其他表的 09-17。
- **没有核实**：Alpha158 在 U3000 上的覆盖率；`osap_price_broad` 各列的时点定义；T-19 预测的 `fold_id` 与训练截止日的对应关系（要读 `fold_meta_*.json`）。
