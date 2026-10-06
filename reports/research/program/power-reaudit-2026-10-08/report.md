# T-20261005-35 旧否定的功效复查（P-1 五条）

写于 2026-10-06，执行轮 sonnet-high 子代理，协调码 R1005-T35。**只做机械判定；"可以重开"一栏是候选，待主审。** 没有跑任何回测。

## 1. 结论一页

- 复查范围：方向登记（最后一行）状态为 `refuted` 的全部 111 条（`evidence_too_weak` / `not_executable` 从未被我们测过，不在范围内）。
- 满足 P-1 五条：**3** 条（`cross_sectional_gap_fade`、`overnight_intraday_gap_retail_pwb`、`intraday_same_slot_periodicity`）。
- 标"未到深度"：**107** 条；P-1 不适用 1 条（`dolthub_free_options_eod_chain_data`：数据源验收失败，不是对方向的检验）。
- 各条的缺口：c3（≥3 个深度点）不满足 95 条（满足 6、不适用 10）；c5（功效）不满足 37 条、无法判定 52 条、满足 13 条、不适用 9 条。只缺 c3 的仅 1 条（`s3_rebalance_timing_luck_tranching`，本身是偏移度量）。
- 最小可检出效应（MDE）算出 52 条，其中 31 条的 MDE 高于它声称要排除的效应；另 59 条原结果缺检验统计量或样本长度，写"无法计算"。
- 重开候选（待主审）：30 条，见第 4 节。

**系统性发现（对所有 K1/K2 筛选车道的否定都成立）。** 冻结窗口：锚定 2024-01-08..2026-09-17 共 2.69 年，压力 2016-05-02..2023-08-31 共 7.33 年。夏普的标准误是 1/√T，在 K=1.645+0.842 的口径（单侧 5%、80% 功效，同 h20261004_pm_earnings_beat_odds 的 results.json）下：

| 窗口 | 年数 | 夏普 MDE | 夏普差 MDE（ρ=0.5） | 夏普差 MDE（ρ=0.8） |
|---|---|---|---|---|
| anchor | 2.69 | 1.52 | 1.516 | 0.959 |
| stress | 7.33 | 0.92 | 0.919 | 0.581 |
| pooled | 10.02 | 0.79 | 0.786 | 0.497 |

K1 条是 1.19（锚定）/0.65（压力），K2 的增量条是 0.05-0.10。锚定窗口单独看，真夏普恰为 1.19 时的检出概率只有约 50%-60%（取决于单侧/双侧口径）；K2 的 0.05-0.10 增量远低于任一窗口的 MDE（0.5-1.5），不可能被检出。所以 K1/K2 是**晋级门槛**，不是**否定检验**；用它们的未通过去关闭一个方向，只在观测夏普的单侧 95% 上界低于目标时才有统计含义（c5 的自动判定就是这样做的：MDE ≤ 目标，或上界 < 目标）。自检：按同一公式复现了第二版计划第 1 节的检出概率表（13/38/70/91%，T=2.73），并复现了预测市场财报条目自报的 MDE（0.1107 对 0.1101）。

## 2. 按缺口类型汇总

| 类型 | 条数 | 含义 | 代表条目 |
|---|---|---|---|
| power | 42 | 检验看不到声称的效应（或窗口太短/事件太少） | giants_sweep_published_etf_rules, spy_noise_band_intraday, levered_industry_trend_second_bet |
| fidelity | 25 | 代理/部分实现/合同无效，没有忠实复现原文 | composer_rsi_branch_uvxy, earnings_8k_tone_next_day, news_attention_features |
| depth | 6 | 单点或单次训练，无规模/容量曲线 | ml_ranking_broad_universe_custom, lightgbm_price_volume_recipe_v1_closed, chart_image_cnn_jkx_replication |
| budget | 1 | 预算远未用完 | llm_hypothesis_code_backtest_loop |
| data | 5 | 数据（幸存者偏差、覆盖、映射）限制了检验 | wikipedia_pageview_attention_signal, sec_fails_to_deliver_signal, multiscale_intraday_event_r5 |
| contract | 6 | 效应存在但在最早可入场点前已定价，或成本/执行合同决定结果 | event_13d_drift, orb_etf_opening_range_breakout, levered_single_asset_sma_trend_gate |
| sizing | 6 | 仓位/风控叠加，owner 规则下优先级低 | s1_sector_rotation_voltarget, drawdown_brake_overlay, meta_labeling_position_tiers |
| internal | 14 | 自家账本的归因/组合比较，无外部声称可复现 | levered_menu_expansion, s3_rank_optimization, insider_form4_confirmation_gate |
| repro | 2 | 原文数字未复现 | turn_of_month_equity_seasonality, option_expiration_week_calendar_effect |
| met | 3 | 五条都满足 | cross_sectional_gap_fade, overnight_intraday_gap_retail_pwb, intraday_same_slot_periodicity |

## 3. 复查方法和口径（要核对的地方）

- 数字来自登记册 verdict 文本（它抄自所引报告），关键几条对 results.json 抽查：预测市场财报 `h20261004_pm_earnings_beat_odds/results.json`（mde_ic 0.1101、620 事件/30 周、IC 0.0191）；尾盘再平衡 `h20260930_01_rebalancing_front_run/results.json`（锚定 SPY 日内系数 -0.400、HC3 SE 0.476，全样本 -0.520，SE 0.183）；隔夜持续性 `t20260930_14_overnight_persistence_12m/results.json`（delta_lo20 -5.88 bp，20 天）。**111 份原报告没有逐份通读**，c1-c4 的 Y/N 是按 verdict 文本和所引报告摘要的判断；`?` 表示记录里查不到（多为 2026-09-23 前的旧假设卡：没有预算、没有检验统计量）。
- c1 复现原文：登记册的结论是"我们的结果为负"时，只有在原文的相对结论/曲线形状先被复现、或失败有直接机制解释（如已被定价）时才记 Y；否则记 N（这是第二版计划补充条款的字面读法，没有放宽）。c3：只有数据规模、模型容量、样本长度、实现保真度上有 ≥3 个点才记 Y；参数网格不算深度点。无规模维度的纯日历规则记 A。
- c5：IC/CAR/系数类用 SE=|观测|/t；夏普类用 1/√T 的 iid 近似（有自相关时 SE 更大，MDE 是下界）；夏普差用 √(2(1-ρ)/T)，ρ 取登记册里报告的相关系数，缺时给 0.5/0.8 两档。"声称的效应"优先取原文声称值，没有时取 K1 条（压力 0.6447 / 锚定 1.1882）。
- `compute.py` 里每条的 c 码、缺口说明和候选标记是手工写进去的（带注释），`audit.json` 是它的输出；`apply_registry.py` 把结果追加进方向登记。

## 4. 可以重开的候选（候选，待主审）

排序不代表优先级，只按"重开前要补什么便宜、且原结论的缺口明确"粗分；是否重开、顺序和预算由主审决定。

| 方向 | 登记原判定（摘要） | 缺的深度/功效 | 重开前要补 |
|---|---|---|---|
| composer_rsi_branch_uvxy | platform triple-digit returns = leverage + survivorship + bull window 2026-09-23: the new batch reproduces the… | 无法计算 | 平台收益声明未用 composer-trade-py 的 value_history 与回测对比，未取实盘记录 |
| news_attention_features | coverage is not the bottleneck (97.4% of momentum holdings have news in 20 days, vs 98.2% pool) -- the count/n… | 无法计算 | 只做了阶段 1（计数/新颖度）；阶段 2 LLM 内容打分未测，文献的池子/频率（小盘、月频、长持）未对应 |
| pead_xbrl_8k_llm | refuted: t_dates 1.064 < 3, beats_redated False, book_positive_20bp False in both windows (full and 2024+ both… | 无法计算 | t_dates 1.064；8-K 覆盖把样本限制在 2024-2026（约 2.7 年），无法检出文献量级的 SUE 漂移；需把 8-K 2.02 时间戳回补到 2016+ |
| insider_buy_independent_broad_universe | closed. Every variant loses to SPY on a vol-matched basis; the literature's 'zero-cost fixes' (role filter, 10… | 无法计算 | 原报告自述 10b5-1 排除只触及 1.6-4.0% 买入且功效不足；10b5-1 标志史仅 42 个月（2023-04 起）；短腿未测 |
| ml_ranking_broad_universe_custom | T-20260928-10 Stage-1 kill test on Modal, 2026-09-28 (stress window 2016-05-02..2023-08-31, walk-forward valid… | RankIC lift vs B0 (single-IC MDE; paired SE <= sqrt2 x) MDE 0.01776（声称 0.01） | 只做阶段 1 杀伤测试，阶段 2 未用；缺数据规模/容量三点曲线；单个 RankIC 的 MDE 已高于所需提升 0.010 |
| reversal_trend_hourly_selection_alpha | not viable as a selection alpha; kept only as a one-off entry-timing A/B, not a standalone signal… | 无法计算 | 只测了 1 小时棒；用户原始要求的 1 分钟版本代码未写 |
| monday_afternoon_reversal_index_timing | Tested as monday_afternoon_spy/qqq (single-index weekly timing: hold the asset Tuesday-open through Friday if … | 夏普 T=10.02y MDE 0.786（目标 0.6447） | 用 close-vs-open 代替论文 12:00-vs-open；横截面因子本身没测；SIP 分钟线（2023+）已用于别处，字面信号现在可测 |
| llm_hypothesis_code_backtest_loop | Refuted for this scope: one 2-round hypothesis-code-IC-feedback batch did not beat an already-strong professio… | 无法计算 | 只跑 2 轮、12 个候选；赢家 TEST ICIR 0.197 为正号；预算（>2 轮/>12 候选）远未用尽 |
| text_to_pit_feature_extraction | stop for this construction (8-K risk_score, 50 tickers, 8 quarters, single DeepSeek prompt): real IC is negati… | 无法计算 | 8-K risk_score 代替 10-K Item 1A，50 只股票 x 8 个季度；真实 IC 为负但与安慰剂不可分（8 个季度几乎无功效） |
| dual_class_share_arbitrage_pwb | T-20260929-37 (h20260929_37_ls_short_unlocked): 0/6 dual-class share-pair z-score candidates (10 US pairs excl… | 夏普 T=10.02y MDE 0.786（目标 0.6447） | 毛夏普锚定 0.50-1.05 为正，成本（冻结 10/20 bp）是约束；GOOG/GOOGL 等腿的实测价差约 2 bp 以下；缺实测报价成本合同 |
| pre_fomc_announcement_drift | H-20260928-05 batch2 (iteration h20260928_05_registry_etf_batch2): both FOMC_DRIFT_SPY (anchor Sharpe -0.8449,… | 夏普 T=10.02y MDE 0.786（目标 0.55） | SPY 变体为负，但每年约 8 次 FOMC，锚定窗口只有约 20 个事件；TQQQ 变体 0.31/-0.03；原文夏普 0.5-0.6 在该长度下检出概率低 |
| etf_dip_reversion_ibs_connors | Re-judgment appended 2026-09-29 (T-20260929-01 part B): H-20260924-01's 6 published ETF dip-reversion rules (D… | 夏普 T=2.69y MDE 1.516（目标 1.1882） | 最优 DIP_D1_SPY 锚定 1.127 为 K1 条的 95%；阶段 B（15:50 ET 代理 + MOC 时点）未实现；锚定窗口 MDE 高于条 |
| momentum_daily_crash_guard | 0/5 pass (H-20260924-02). The Daniel-Moskowitz bear/panic state and a -7% single-day market stop never trigger… | 无法计算 | Daniel-Moskowitz 熊/恐慌状态与 -7% 单日停止在 2024-2026 从未触发，该机制在此窗口零功效；需含崩溃的窗口做崩溃诊断 |
| chart_image_cnn_jkx_replication | REFUTED (kill test run 2026-09-28 on Modal, full spec, not a stage-1 pilot). Fixed OOS-rendering timeout bug f… | 无法计算 | 单个 I20/R5 模型、训练期 2016-2019（原文 1993-2000）、n=413,128；无训练规模/容量/窗口三点曲线；NW t -1.176；缺 I60 变体 |
| core_satellite_momentum_sector_etf_r7 | No candidate selected; workflow_pass=false, research_pass=false. Raw audit-only diagnostics: D01 29.01% return… | 无法计算 | StrategySpec 未编码多标的目标权重行为、折叠成本边界未冻结 —— 合同无效；DSR 0.578 |
| etf_structural_family_daily_r9 | Stop; research_pass=false, no selected candidate. R9D04's primary Sharpe was 0.967 against a frozen raw-BIL-Sh… | 无法计算 | 冻结的 BIL 原始夏普 9.38 作为风险策略门槛——原记录自己也标为方法上有疑；R9D04 夏普 0.967 |
| multiscale_low_turnover_etf_r6 | Daily core path: stop selection, preserve all returns only as invalid-contract audit evidence -- D01-D04 viola… | 无法计算 | D01-D04 违反 40% 单标的上限、D02-D05 非自融资记账：无合同有效的历史结果 |
| robust_momentum_deterministic_ml_r4 | P1: stop -- no accepted diagnostic candidates; all evidence is current-universe (survivorship-biased) diagnost… | 无法计算 | 全部为当前宇宙（幸存者偏差）诊断；缺 PIT 成分、退市收益、公司行动谱系 |
| nasdaq_long_short_event_router_1m | Refuted on consolidated SIP 1-minute data (h20260929_36_router_sip, frozen route, no parameter change, 2024-01… | 夏普 T=2.72y MDE 1.508（目标 0.33） | 做空腿从未触发（top_n=1 时空头榜与多头榜相同）——测的是仅多头的开盘抄底；压力窗口 2016-2023 无分钟数据（待办） |
| tqqq_post_drawdown_reentry_router | Not promotion-eligible. 2026-07-10 subjective pivot: judged too conservative for the project's aggressive-mome… | 无法计算 | 判定依赖 qqq_capture_ratio（登记册 step10 条目记录该复合式度量对 beta<1 策略不可通过且 09-04 后修正）；本条 09-02/03 复核是否按修正口径重算待核对 |
| reversal_trend_user_indicator | Daily event study: judged 'informative: no' in both full-sample and recent windows (fBear/fRecS showed a posit… | 无法计算 | 18 格 0/18；1 分钟版本代码未写（用户原始要求） |
| owner_azevedo_hoegner_ml_anomalies_2023 | Owner's claim (traditional ~0.9, ML ~1.3-1.4) verified almost exactly (GLM OOS Sharpe 1.3868 vs baseline ~0.92… | 无法计算 | 类比判定：未直接测该论文的 GLM/ML 方案；登记册自述依据是同机制的本地测试 |
| ipo_lockup_expiration_drift | 13 preregistered candidates (h20260929_21_ipo_lockup_expiry), TEST 2024-01-08..2026-09-17: best by TEST Sharpe… | 夏普 T=2.69y MDE 1.516（目标 1.1882） | 事件表 20 样本核查 6/20 非普通股或错配（30%，过滤前上界）；180 日近似代替合同解禁日 |
| crypto_weekend_to_monday_equity_transmission | Step 1 (h20260929_50_crypto_weekend_monday, 2026-09-29) refuted: the published weekend-crypto effect replicate… | 无法计算 | 周末效应在周五收盘-周一开盘复现（QQQ -51..-62 bp, t -3.0..-4.6）但开盘前已定价；Alpaca 周日 20:00 ET 夜盘填单未测 |
| small_cap_background_drift_short_basket | Refuted at ETF level (T-20260929-51, step 1 gate failed, step 2 not run): SSD_IWM_M252 anchor median Sharpe af… | 夏普 T=10.02y MDE 0.786（目标 1.35） | 只做 ETF 层（步骤 1），步骤 2 个股篮子因无借券费历史未做；原文个股夏普 1.35 不可用免费 ETB 对冲复现 |
| dolthub_free_options_eod_chain_data | T-20260929-60 acceptance (2026-09-29, results.json in reports/research/iterations/h20260929_60_dolthub_options… | 无法计算 | 这是数据源验收失败（覆盖 0.54-0.62 对 0.85），不是对方向的功效检验；仅 2024-09-04 起稠密 |
| pension_rebalancing_front_run_equity_leg | Refuted at the regression gate (h20260930_01_rebalancing_front_run, results.json): SPY open-to-close Threshold… | SPY ID coef, anchor 2024-01-08+; claimed = own full-sample -0.520 (results.json regression_table) MDE 1.18429（声称 0.52） | 2024+ 系数 -0.400（HC3 SE 0.476，t -0.84）与全样本 -0.520（t -2.84）同号同量级——并未反驳；2.7 年窗口的 MDE 1.18 高于 0.52，只是看不见 |
| overnight_return_persistence_auction | 1-month and 1-week formulations refuted in T-20260929-35 (ON21_P1500_LS +2.56 bp/night, NW t 0.66 in 2024-01-0… | bp/night delta_lo20 MDE 5.41613（声称 4.0） | 门 A 在未见股票通过（+13.69 bp/夜 t 5.19）；门 B 官方开盘拍卖价 20 个种子日 1,958 对，delta -5.88 对门槛 -4，SE 2.18 的 MDE 5.4 高于 4；缺上市交易所开盘集合竞价价源 |
| prediction_market_earnings_beat_odds | refuted 2026-10-04 (T-20261004-51) for effects of the size detectable here: 620 events, 30 weeks, mean weekly … | IC MDE 0.11069 | 620 事件/30 周，周 IC 0.019 t 0.43，最小可检出 0.110；原论文只读到二手报道（页面 403），行业调整版与结束时点代理未跑；单一通道（15:00 ET 的 P）；重开：约 450 个新事件或不同通道（公告日盘中赔率变化） |
| prediction_market_policy_odds_leadlag_glw2026 | refuted 2026-10-04 (T-20261004-53, mechanical stop rule, pending lead review) for the midterm setting over 202… | 夏普 T=0.98y MDE 2.512（目标 1.95） | 窗口 0.98 年 27 个资产；回归 5.0 bp/pp (t 0.91) 对论文 13 bp/pp：MDE(5.5 x 2.486 = 13.7) 约等于论文效应；前向影子到 2026-11-04 在继续 |

**最值得主审先看的三条**（我的排序依据：缺口可直接量化、补测便宜或数据已在手、且一旦成立对近期利润有意义）：

1. `prediction_market_earnings_beat_odds`：620 事件、30 周的 MDE 是周 IC 0.110（观测 0.019，t 0.43，我按 SE=|IC|/t 复算得 0.1107）；原论文只读到二手报道；行业调整版和结束时点代理未跑；等约 450 个新事件或换通道（公告日盘中赔率变化）。
2. `nasdaq_long_short_event_router_1m`：做空腿从未触发（top_n=1 时空头榜与多头榜相同），所测的是仅多头的开盘抄底，不是原来设想的多空路由；压力窗口因 2023 前无分钟数据而待办；SIP 分钟线现已有。
3. `overnight_return_persistence_auction`：门 A 在未见股票上成立（+13.69 bp/夜，NW t 5.19；压力 +17.35，t 12.02），门 B 在官方开盘拍卖价上只用了 20 个种子日（delta -5.88 bp，对门槛 -4 bp，SE 2.18 → MDE 5.4 > 4）；效应本身是真的，执行路径没有被足够深地测。

另有两条值得一提但不是候选之首：`pension_rebalancing_front_run_equity_leg` 的 2024+ 系数 -0.400（SE 0.476）与全样本 -0.520 同号同量级，原判"t -0.84 未达 -2.0"并未反驳全样本效应，只是 2.7 年窗口看不到（MDE 1.18）；`momentum_daily_crash_guard` 的 Daniel-Moskowitz 状态在 2024-2026 从未触发，这一机制在该窗口零功效，不能算被检验。

## 5. 外部负面证据（I-20261004-08 第 6 节第 6 项）

来源：henryzhangpku/autonomous-quant-researcher（1 星，一人项目，自报，无第三方复现，代码未审）。T-83 只读了 README 与 SPY 0DTE / QQQ 留出文件；三份任务文件这次补抓并存档（`reports/research/intel/sources/power-reaudit-2026-10-08/`，抓取 2026-10-06T17:07Z，manifest.json 有 URL）。各登记一条（状态 `evidence_too_weak`，含 `external_negative_evidence` 字段，不是我们自己的检验）：

| 登记 id | 作者自报结果 | 作者自己列的局限 |
|---|---|---|
| `dir:ext_neg_single_rule_etf_grid_bars_rules` | 8 只 ETF 232 个预注册单规则格子，4 个发现期通过者 0 个晋级；通过者都是 ret_20d 的多空两个方向（长头寸 beta）；验证期 +18.87 bp/笔但 -12.22 bp/日（夏普 -0.86） | 发现期只有一种市场方向；只测单条件规则；5 bp 是假设；日频收盘决策 |
| `dir:ext_neg_tradingview_ta_premises_fib_channel_ribbon` | 斐波那契/回归通道/均线带/支撑位：验证期全败（-30.10/-22.32/-7.14/-11.08 bp/日，均劣于始终做多 -3.11）；回归通道过了 9 道发现期门（+16.26 bp）后 -22.32 | 一个宇宙、日线收盘决策；作者在同一文件更正过一个数字 |
| `dir:ext_neg_overnight_spx_put_credit_premium` | 隔夜 SPX 看跌信用价差 40 次试验无候选过发现期；溢价真实但很薄（00:00 ET 对照净 +0.004..+0.014 个价宽），在成本加倍门死亡（需 ≥+0.05，最好约 +0.014） | 黑-斯科尔斯估价、无夜间报价；历史仅 2024-09+；作者自己把后续留出否定标为"功效不足"（7 周、30 笔），不是证明不存在 |

第三条里作者自己说明了功效不足，所以它对我们只算"在重开前先读"的负面证据，不能当作对该溢价的否定。

## 6. 代码与登记的变更（向后兼容）

- `open_composer/research/harvest_registry.py`：`Direction` 新增可选字段 `depth_audit`（`DepthAudit`：audited_at、label、p1 五码、原判定、MDE、观测值、缺的深度点、audit_file）和 `external_negative_evidence`（`ExternalNegative`）；已有字段含义不变；`validate_registry` 要求 under_depth 带缺口说明；`check_direction` 在已审条目的 verdict 前加"(under-depth audit …)"；`registry_summary` 增加 `depth_audit` 计数。测试：`tests/test_harvest_registry.py` 新增 3 个。
- `reports/research/harvest/directions.jsonl`：只追加 114 行（111 条审计修订 + 3 条外部负面），原 423 行逐字节未动（已对比前缀）。因登记册"同 id 取最后一行"，每条修订行是该 id 最新行的完整副本加 `depth_audit`，`status`/`verdict`/`evidence`/`reopen_if` 原样保留，仅 `updated` 改为 2026-10-06。
- 没有改任何条目的状态，也没有把任何方向标为重开；"未到深度"是 `depth_audit.label=under_depth` 的机械标签。
