# I-20260923-04：paperswithbacktest.com 策略库普查与注册

## 范围与 2026 红线

任务：把 paperswithbacktest.com（自称收录约 5,000 个"同行评审、1990–2026 年重新回测、按夏普排序"的策略）系统性地过一遍，把满足条件的最强候选登记进方向登记表。全程未登录、未绕过付费墙、未使用任何凭证；只抓取匿名可见的内容。**硬性规则**：本文档不出现任何 2026 年或 2026 年至今的单独收益数字；凡是"1990–2026 全周期"统计量（该站点绝大多数策略页面唯一提供的统计口径），按任务说明"可以照抄，但要标注 `period_includes_2026: true`"处理——本文档表格中的年化收益/夏普/回撤全部来自这种全周期统计，未对任何 2026 年区间单独计算或引用。

## 一、访问条款与定价

- `robots.txt`（`https://paperswithbacktest.com/robots.txt`）：只禁止 `/admin/` 和 `/api/`，其余（含全部 `/strategies/*`）允许；给出了 `sitemap.xml`。
- 运营方：EADBA（法国 SARL 公司）；条款最后更新 2026-08-12。
- 定价四档：**Free**（免费浏览全部列表/摘要/数据集页面/课程；终身一次策略解锁含代码+数据；$1 一次性 research-agent 额度）→ **Reader** $10/月 → **Backtester** $50/月或 $300/年（"5,000+ 策略可跑 Python"、"1.04 TB 干净数据集"、$10/月 research-agent、MCP 连接器、100 次/月解锁、课程）→ **Institution** 定制。
- **没有公开 API，没有批量数据集下载**。`robots.txt` 点名的 `/api/` 是站点自身前端用的私有接口（分页、搜索都走它），未公开文档化，本次严格未触碰。存在一个"research agent"（浏览器内沙箱）和 MCP 连接器，但都是付费档位功能，作用于账号自己解锁过的策略，不是批量导出通道。
- 全程未创建账号、未登录、未解锁任何付费策略/代码/数据集；本文档所有数字都是匿名未登录请求能看到的内容。

## 二、目录枚举：分页被 `/api/` 挡住，改用站内搜索采样

- `sitemap.xml` 共 5,780 条 URL，其中 `/strategies/<slug>` 个体策略页 **5,341** 个，另有 32 个分类/状态页（如 `/strategies/awaiting-data/*`）。5,341 与站点宣传的"5,000 个"基本吻合。
- **默认列表页 `/strategies`（不带页码）是完整服务端渲染的**：50 张策略卡片，每张卡片的 HTML 里直接嵌了名称、发表年份/作者、资产类别标签、调仓频率标签、夏普比率、回测区间——这一步验证了卡片解析方案。
- **路径分页 `/strategies/page/2` … `/strategies/page/88`（分页控件显示的最大页码）返回 HTTP 200，但内容是空壳**（约 112KB，只有导航/页脚，零策略卡片）：对 `/strategies/page/2` 重复请求两次字节数完全一致（111,689 字节），排除了缓存未命中之类的偶然情况；`/strategies/page/88` 同样是空壳。查询字符串写法 `/strategies?page=2` 会 308 重定向掉。结论：**该站的路径分页依赖客户端 JS，几乎可以肯定最终调用的是 `robots.txt` 明确禁止的 `/api/`**；因此本次既没有直接调用 `/api/`，也没有用无头浏览器去"代替"触发同一个被禁止的接口——那只是把同一次被禁止的请求换了个执行者，不算合规。
- **好消息：站内全文搜索 `/strategies?q=<关键词>` 是服务端渲染的**（用 `?q=momentum` 验证，返回 50 张带完整统计量的真实卡片），且路径仍在 `/strategies` 之下，不属于 `/api/`，是允许的。于是改用它作为合规的广度采样手段：四轮共 **102 个关键词查询**（覆盖资产类别词、经典因子词、行业/大宗商品主题词、调仓风格词），每次请求间隔 ≥2 秒（`sleep 2`），全部 200 状态，无一次被限流或拒绝。
- 采样结果：**去重后拿到 2,335 个不同策略的完整卡片数据**（占 5,341 个 sitemap 条目的 43.7%）。四轮的边际收益递减很明显——第 1 轮 30 个查询后，满足下节筛选条件的候选有 38 个；第 2 轮累计 60 个查询后 44 个；第 3 轮累计 85 个查询后 46 个；第 4 轮累计 100 个查询后 47 个。也就是说后期每批新查询新增的合格候选已经从平均 1.5 个/查询降到约 0.1 个/查询，判断继续加查询词的边际价值很低，遂停止——剩余约 56% 的目录未被覆盖，具体见下文"未能触达"。
- 全部 2,335 行已写入 `reports/research/intel/sources/20260923-paperswithbacktest/catalog.csv`（列：url, name, asset_class, rebalancing_frequency, backtest_period, sharpe_shown, paper_pub_year_shown, period_includes_2026, found_via），抓取细节、条款摘录、分页排查过程记录在同目录 `manifest.json`。

### 目录构成（2,335 个已采样策略；一张卡片可以同时打多个资产类别标签，因此各类别加总会超过 2,335）

| 资产类别标签 | 数量 |
|---|---:|
| Equities | 2,028 |
| Bonds | 482 |
| Derivatives | 479 |
| Commodities | 310 |
| REITs | 81 |
| Currencies | 73 |
| Cryptocurrencies | 54 |
| Indices | 12 |
| ETFs | 8 |
| Event-driven | 3 |
| Forex | 1 |

| 调仓频率 | 数量 |
|---|---:|
| Monthly | 1,330 |
| Daily | 441 |
| Yearly | 291 |
| Quarterly | 156 |
| Weekly | 113 |
| （未显示） | 3 |
| Annually | 1 |

## 三、按任务口径筛选出的候选清单（47 个，按夏普降序）

筛选口径：(a) 资产类别为 equities/ETF/commodities 且可通过美股 ETF 交易，剔除纯 currencies/crypto/bonds-only；(b) 调仓频率为 daily/weekly/monthly；(c) 显示夏普 ≥ 1.0。在 2,335 个已采样策略中共有 47 个满足全部三条（任务规定"最多开 60 个页面"，这里全部打开，未达到上限）。逐页打开后记录年化收益、波动率、最大回撤、持仓数、是否需要做空、是否展示代码、以及分年收益。

**代码展示**：47 个详情页无一展示可运行代码——与定价页一致："5,000+ 策略可跑 Python"是 Backtester（$50/月）档位的功能，本次匿名访问全程未见任何页面内嵌代码块，只见统计卡片 + 当前持仓表。

**分年收益**：47 个详情页都不提供分年（或分月）静态文本形式的收益拆解——每页有一个"Net worth"曲线图（可切换 1Y/3Y/5Y/10Y/Max），但曲线数据点不在服务端渲染的 HTML 里（大概率是客户端另行拉取），本文档如实记录为"未以静态文本形式展示"，没有尝试逆向工程图表的客户端数据源，也因此不存在意外记录到 2026 年数字的风险。

| # | 名称 | 资产类别 | 调仓频率 | 年化收益 | 夏普 | 最大回撤 | 需要做空 | 注册结果 |
|---:|---|---|---|---:|---:|---:|:---:|---|
| 1 | [The Investment CAPM](https://paperswithbacktest.com/strategies/the-investment-capm-1) | Equities | Monthly | 5.33% | 1.80 | 8.17% | 是 | duplicate_of dir:classic_long_short_anomalies_recent (0.80) |
| 2 | [Untying the Knot: Disentangling Cash Flow and Voting Rights for Better Price Informativeness](https://paperswithbacktest.com/strategies/untying-the-knot-disentangling-cash-flow-and-voting-rights-for-better-price-informativeness) | Equities | Monthly | 5.20% | 1.68 | 12.47% | 是 | dir:dual_class_share_arbitrage_pwb |
| 3 | [Expectations and the Option Implied-Variance](https://paperswithbacktest.com/strategies/expectations-and-the-option-implied-variance) | Derivatives; Equities | Monthly | 5.41% | 1.64 | 6.38% | 否 | dir:option_implied_variance_premium_pwb |
| 4 | [Explaining low annuity demand: an optimal portfolio application to Japan](https://paperswithbacktest.com/strategies/explaining-low-annuity-demand-an-optimal-portfolio-application-to-japan) | Bonds; Derivatives; Equities | Daily | 7.93% | 1.60 | 13.44% | 否 | excluded：理论论文，非交易规则（Merton 式年金/生命周期模型） |
| 5 | [Diverging roads: Theory-based vs. machine learning-implied stock risk premia](https://paperswithbacktest.com/strategies/diverging-roads-theory-based-vs-machine-learning-implied-stock-risk-premia) | Derivatives; Equities | Monthly | 13.41% | 1.57 | 11.73% | 是 | dir:ml_implied_risk_premia_pwb |
| 6 | [Nominal price anomaly in emerging markets: Risk or mispricing?](https://paperswithbacktest.com/strategies/nominal-price-anomaly-in-emerging-markets-risk-or-mispricing) | Equities | Monthly | 9.08% | 1.56 | 8.44% | 是 | dir:nominal_price_anomaly_pwb |
| 7 | [The Role of Beta and Size in the Cross-Section of European Stock Returns](https://paperswithbacktest.com/strategies/the-role-of-beta-and-size-in-the-cross-section-of-european-stock-returns) | Equities | Monthly | 8.11% | 1.56 | 9.26% | 是 | dir:classic_anomalies_beta_size_europe_pwb |
| 8 | [Overnight-Intraday Return Gap and the Retail Ebb and Flow](https://paperswithbacktest.com/strategies/overnight-intraday-return-gap-and-the-retail-ebb-and-flow) | Equities | Monthly | 8.73% | 1.55 | 5.66% | 是 | dir:overnight_intraday_gap_retail_pwb |
| 9 | [Multivariate Affine GARCH with Heavy Tails](https://paperswithbacktest.com/strategies/multivariate-affine-garch-with-heavy-tails-a-unified-framework-for-portfolio-optimization-and-option-valuation) | Equities | Daily | 5.08% | 1.49 | 6.12% | 是 | dir:risk_based_portfolio_construction_pwb |
| 10 | [The Anomalous Behavior of the S&P Covered Call Closed End Fund](https://paperswithbacktest.com/strategies/the-anomalous-behavior-of-the-s-p-covered-call-closed-end-fund) | Derivatives; Equities | Monthly | 26.60% | 1.36 | 31.62% | 否 | dir:covered_call_cef_income_pwb |
| 11 | [Fact, Fiction, and the Size Effect](https://paperswithbacktest.com/strategies/fact-fiction-and-the-size-effect) | Equities | Monthly | 3.45% | 1.35 | 5.48% | 是 | dir:classic_anomalies_factor_reviews_pwb |
| 12 | [Understanding Momentum and Reversal?](https://paperswithbacktest.com/strategies/understanding-momentum-and-reversal) | Equities | Monthly | 6.87% | 1.34 | 9.85% | 是 | duplicate_of dir:classic_long_short_anomalies_recent (0.50) |
| 13 | [Systematic Abnormal Return Variation and Global Market Inefficiencies](https://paperswithbacktest.com/strategies/systematic-abnormal-return-variation-and-global-market-inefficiencies) | Equities | Monthly | 11.04% | 1.33 | 16.06% | 是 | dir:market_inefficiency_scoring_pwb |
| 14 | [The cross-section of returns in frontier equity markets](https://paperswithbacktest.com/strategies/the-cross-section-of-returns-in-frontier-equity-markets-integrated-or-segmented-pricing) | Equities | Monthly | 5.11% | 1.31 | 12.97% | 是 | dir:frontier_market_factor_pricing_pwb |
| 15 | [Analytical Solution for Kelly's Criterion for Multiple Outcomes](https://paperswithbacktest.com/strategies/analytical-solution-for-kelly-s-criterion-for-multiple-outcomes) | Equities | Monthly | 17.55% | 1.30 | 34.33% | 否 | duplicate_of dir:conformal_kelly_sizing (0.50) |
| 16 | [Inconsistent investment and consumption problems](https://paperswithbacktest.com/strategies/inconsistent-investment-and-consumption-problems) | Bonds; Equities | Daily | 3.31% | 1.26 | 6.96% | 否 | excluded：理论论文（HJB 消费-投资最优化） |
| 17 | [Macroeconomic Implications of Immigration Quality Shifts](https://paperswithbacktest.com/strategies/macroeconomic-implications-of-immigration-quality-shifts-short-canada-long-global-productivity) | Bonds; Commodities; Derivatives; Equities; REITs | Monthly | 9.72% | 1.24 | 9.95% | 是 | dir:macro_relative_value_us_vs_canada_pwb |
| 18 | [Intraday time series reversal](https://paperswithbacktest.com/strategies/intraday-time-series-reversal) | Equities; REITs | Daily | 16.91% | 1.24 | 78.90% | 否 | dir:intraday_reversal_reit_pwb |
| 19 | [End-to-End Large Portfolio Optimization ... through Covariance Cleaning](https://paperswithbacktest.com/strategies/end-to-end-large-portfolio-optimization-for-variance-minimization-with-neural-networks-through-covariance-cleaning) | Equities | Weekly | 17.99% | 1.22 | 49.58% | 是 | dir:risk_based_portfolio_construction_pwb |
| 20 | [Any role for mean reversion in short term asset](https://paperswithbacktest.com/strategies/any-role-for-mean-reversion-in-short-term-asset) | Bonds; Equities | Monthly | 9.82% | 1.22 | 25.98% | 否 | dir:tactical_mean_reversion_multi_asset_pwb |
| 21 | [Generalized Risk-Based Investing](https://paperswithbacktest.com/strategies/generalized-risk-based-investing) | Equities | Monthly | 17.67% | 1.17 | 49.20% | 否 | dir:risk_based_portfolio_construction_pwb |
| 22 | [Betting Against Correlation](https://paperswithbacktest.com/strategies/betting-against-correlation-testing-theories-of-the-low-risk-effect) | Equities | Monthly | 15.94% | 1.17 | 39.98% | 否 | dir:risk_based_portfolio_construction_pwb |
| 23 | [Learning the Shrinkage Intensity](https://paperswithbacktest.com/strategies/learning-the-shrinkage-intensity-a-data-driven-approach-for-risk-optimized-portfolios) | Equities | Monthly | 14.68% | 1.16 | 32.53% | 否 | dir:risk_based_portfolio_construction_pwb |
| 24 | [Meta-t Portfolio Optimization](https://paperswithbacktest.com/strategies/meta-t-portfolio-optimization) | Equities | Daily | 21.27% | 1.15 | 38.97% | 否 | dir:risk_based_portfolio_construction_pwb |
| 25 | [Leakage-Safe Financial News Sentiment Trading in United States Equities](https://paperswithbacktest.com/strategies/leakage-safe-financial-news-sentiment-trading) | Equities | Daily | 23.29% | 1.14 | 23.17% | 否 | dir:news_sentiment_trading_pwb |
| 26 | [Does Probability Weighting Drive Skewness Preferences?](https://paperswithbacktest.com/strategies/does-probability-weighting-drive-skewness-preferences) | Equities | Monthly | 14.22% | 1.11 | 29.33% | 是 | dir:skewness_preference_52wk_high_pwb |
| 27 | [A Cost-effective Approach to Portfolio Construction with Range-based Risk Measures](https://paperswithbacktest.com/strategies/a-cost-effective-approach-to-portfolio-construction-with-range-based-risk-measures) | Equities | Daily | 17.88% | 1.10 | 43.07% | 否 | dir:risk_based_portfolio_construction_pwb |
| 28 | [Concentrated portfolios of momentum stocks](https://paperswithbacktest.com/strategies/concentrated-portfolios-of-momentum-stocks) | Equities | Monthly | 24.27% | 1.09 | 54.58% | 否 | dir:equity_momentum_concentrated_pwb |
| 29 | [Deep Reinforcement Learning for Asset Allocation in US Equities](https://paperswithbacktest.com/strategies/deep-reinforcement-learning-for-asset-allocation-in-us-equities) | Equities | Daily | 18.80% | 1.09 | 40.42% | 否 | duplicate_of dir:finrl_deep_rl (0.57) |
| 30 | [Asset Pricing with Slope Factors](https://paperswithbacktest.com/strategies/asset-pricing-with-slope-factors-model-and-evidence-of-outperformance) | Equities | Monthly | 10.21% | 1.09 | 20.28% | 是 | dir:classic_anomalies_factor_reviews_pwb（slope-factor 变体） |
| 31 | [Markowitz Meets Technical Analysis](https://paperswithbacktest.com/strategies/markowitz-meets-technical-analysis-building-optimal-portfolios-by-exploiting-information-in-trend-following-signals) | Equities | Daily | 19.87% | 1.09 | 51.32% | 否 | dir:trend_filtered_mean_variance_pwb |
| 32 | ["Long" Factors, not "Short" change: Long Only Factor Portfolios in India](https://paperswithbacktest.com/strategies/long-factors-not-short-change-long-only-factor-portfolios-in-india) | Equities | Monthly | 22.38% | 1.08 | 51.49% | 否 | dir:equity_momentum_concentrated_pwb |
| 33 | [The Stock Selection and Performance of Buy-Side Analysts](https://paperswithbacktest.com/strategies/the-stock-selection-and-performance-of-buy-side-analysts) | Equities | Daily | 19.42% | 1.08 | 46.64% | 否 | dir:buy_side_analyst_recommendations_pwb |
| 34 | [Improving time-varying minimum variance portfolio](https://paperswithbacktest.com/strategies/improving-time-varying-minimum-variance-portfolio-through-penalized-likelihood-estimation) | Equities | Monthly | 11.58% | 1.08 | 39.15% | 是 | dir:risk_based_portfolio_construction_pwb |
| 35 | [A Risk Based Approach to Tactical Asset Allocation](https://paperswithbacktest.com/strategies/a-risk-based-approach-to-tactical-asset-allocation) | Bonds; Commodities; Equities | Weekly | 5.27% | 1.06 | 12.87% | 否 | dir:risk_based_portfolio_construction_pwb |
| 36 | [Factor Investing Revisited](https://paperswithbacktest.com/strategies/factor-investing-revisited) | Equities | Monthly | 11.47% | 1.05 | 34.51% | 否 | dir:classic_anomalies_factor_reviews_pwb |
| 37 | [Performance of ESG-integrated smart beta strategies in Asia-Pacific stock markets](https://paperswithbacktest.com/strategies/performance-of-esg-integrated-smart-beta-strategies-in-asia-pacific-stock-markets) | Equities | Monthly | 12.77% | 1.04 | 37.90% | 否 | dir:esg_smart_beta_pwb |
| 38 | [Does Momentum Investing work in Indian Equities?](https://paperswithbacktest.com/strategies/does-momentum-investing-work-in-indian-equities) | Equities | Monthly | 17.69% | 1.04 | 45.68% | 否 | dir:equity_momentum_concentrated_pwb |
| 39 | [Risk Parity Portfolios with Risk Factors](https://paperswithbacktest.com/strategies/risk-parity-portfolios-with-risk-factors) | Bonds; Commodities; Derivatives; Equities | Monthly | 16.99% | 1.03 | 40.37% | 否 | dir:risk_based_portfolio_construction_pwb |
| 40 | [Market Regimes / Smart Beta Shariah-Compliant Equity Portfolios](https://paperswithbacktest.com/strategies/the-effect-of-market-regimes-on-the-performance-of-market-capitalization-weighted-and-smart-beta-shariah-compliant-equity-portfolios) | Equities | Monthly | 13.48% | 1.03 | 42.20% | 否 | dir:regime_smart_beta_shariah_pwb |
| 41 | [Implementing a Systematic Long-only Momentum Strategy: Evidence From India](https://paperswithbacktest.com/strategies/implementing-a-systematic-long-only-momentum-strategy-evidence-from-india) | Equities | Monthly | 10.57% | 1.02 | 20.21% | 否 | duplicate_of dir:classic_long_short_anomalies_recent (0.60) |
| 42 | [Differential Rates and Transaction Costs](https://paperswithbacktest.com/strategies/differential-rates-and-transaction-costs-a-toolkit-for-practitioners-accountants-and-financial-economists) | Bonds; Derivatives | Monthly | 3.21% | 1.02 | 8.89% | 否 | excluded：方法论/会计工具书，非交易规则 |
| 43 | [Trading Volume Effects of Moving Average Heuristics](https://paperswithbacktest.com/strategies/trading-volume-effects-of-moving-average-heuristics) | Equities | Daily | 11.27% | 1.01 | 34.92% | 否 | dir:moving_average_volume_heuristic_pwb |
| 44 | [When Passive Funds Affect Prices: Volatility and Commodity ETFs](https://paperswithbacktest.com/strategies/when-passive-funds-affect-prices-evidence-from-volatility-and-commodity-etfs) | Commodities; Derivatives | Daily | 2.79% | 1.00 | 4.14% | 否 | dir:passive_flow_commodity_etf_price_impact_pwb |
| 45 | [Long/Short Extensions: How Much is Enough?](https://paperswithbacktest.com/strategies/long-short-extensions-how-much-is-enough) | Equities | Monthly | 17.37% | 1.00 | 43.33% | 是 | dir:long_short_ratio_extension_pwb |
| 46 | [Macro Risk of Low-Volatility Portfolios](https://paperswithbacktest.com/strategies/macro-risk-of-low-volatility-portfolios) | Equities | Monthly | 12.86% | 1.00 | 41.49% | 否 | dir:risk_based_portfolio_construction_pwb |
| 47 | [Factor Investing in Portfolio Construction: Theory, Evidence, and Practical Applications](https://paperswithbacktest.com/strategies/factor-investing-in-portfolio-construction-theory-evidence-and-practical-applications) | Equities | Monthly | 9.44% | 1.00 | 24.34% | 否 | dir:classic_anomalies_factor_reviews_pwb |

（"注册结果"列：`dir:xxx_pwb` = 本轮新登记的方向 id；`duplicate_of dir:xxx (分数)` = `oc research directions check` 命中已有方向且判断机制相同，按任务要求跳过未写入新行，分数是该命令给出的匹配度；`excluded` = 虽机械满足三条筛选条件，但读了详情页正文后判断这不是一条可执行的交易规则，未注册。）

## 四、注册结果汇总

对 47 个候选逐一执行 `uv run oc research directions check <3-5 个关键词>`（全部命令与输出见执行记录），结果：

- **5 个判定为已有方向的重复**（分数 ≥0.5 且机制确认一致），按任务要求未写入新行，只在上表标注匹配 id：`the-investment-capm-1`、`understanding-momentum-and-reversal`、`implementing-a-systematic-long-only-momentum-strategy-evidence-from-india` → `dir:classic_long_short_anomalies_recent`（经典长短因子族，该方向早先结论是"近期窗口普遍不работ"）；`analytical-solution-for-kelly-s-criterion-for-multiple-outcomes` → `dir:conformal_kelly_sizing`（Kelly 仓位法家族，已被作者自己的留出样本否定）；`deep-reinforcement-learning-for-asset-allocation-in-us-equities` → `dir:finrl_deep_rl`（深度强化学习配置，已有独立负面证据）。
- **3 个判定为非交易策略，未注册**：`explaining-low-annuity-demand`（Merton 式年金/生命周期最优化理论论文）、`inconsistent-investment-and-consumption-problems`（Black-Scholes 市场下的 HJB 消费-投资理论）、`differential-rates-and-transaction-costs`（差分利率/交易成本会计方法论工具书）。读完三篇的摘要后确认它们都没有一条可执行的买卖规则——**这暴露了该平台的一个方法论问题：它似乎对"任何金融论文"都套了一层自动回测包装，哪怕论文本身是纯理论/方法论、根本不含交易规则**；这类页面的夏普/回测数字应被视为平台自造的默认实现，而不是论文作者的策略主张，本次未采信其数字作为任何策略证据。
- **其余 39 个映射到 24 个新登记的方向**（`family_key` 归并了机制相同的多篇论文，避免登记表因近乎重复的条目膨胀）：
  - `dir:risk_based_portfolio_construction_pwb`（11 篇来源）：collapse 了 GARCH/收缩估计/惩罚似然/神经网络协方差清洗/相关性/风险平价/战术资产配置等 11 种"更聪明的协方差·风险模型"论文，夏普集中在 1.00–1.22；纯股票版本回撤普遍 32–58%（与仓库里已否定的 `dir:s1_sector_rotation_voltarget`"波动率目标是收益税"的结论同形状），只有做得很防御（GARCH，仅 30 只持仓，回撤 6.12%）或真正跨资产（TAA，含债券/商品，回撤 12.87%）的两个变体回撤可控。
  - `dir:equity_momentum_concentrated_pwb`（3 篇）：区别于仓库已测过的 ETF 级双动量轮动，这是"个股集中动量"角度；美股版本（37 只持仓）24.27% 年化 / 夏普 1.09，但回撤 54.58%；另两篇印度市场复现仅作旁证，不可直接执行。
  - `dir:classic_anomalies_factor_reviews_pwb`（4 篇，含事后追加的 slope-factor 篇）：规模效应史 + 两篇"重温经典因子"综述 + slope-factor 构造法，均属 `dir:classic_long_short_anomalies_recent` 同一机制族，均未超过该方向已有结论。
  - 其余 20 个为独立条目，逐一见 `directions.jsonl`；其中对近期盈利目标最直接相关的两条：
    - **`dir:covered_call_cef_income_pwb`**（S&P covered-call 封闭式基金异象）：全表最高年化 26.60%（夏普 1.36，回撤 31.62%），**做多一只已上市的封闭式基金即可执行，我们自己不需要任何期权能力**——本轮最值得优先精读原文的一条。
    - **`dir:news_sentiment_trading_pwb`**（Leakage-Safe 新闻情绪交易）：年化 23.29%/夏普 1.14/回撤 23.17%，2026-05-22 发表（发表日期而非收益数字，不违反红线），与用户在 alpha 来源分层里排在较前的"新闻/文本"类信号直接相关，且方法论本身聚焦"防泄漏"（point-in-time），与仓库既有的 `dir:text_to_pit_feature_extraction` 基础设施可以对接。
  - 详细的每条 claim / data_needs / executable_for_us 见 `reports/research/harvest/directions.jsonl`（24 行，`updated: 2026-09-23`，`found_by: ["search:20260923:pwb:catalog"]`）。
- `search-log.jsonl` 追加了一行 `id: search:20260923:pwb:catalog`，`results_seen: 2335`，`new_directions` 列出全部 24 个新 id。
- `uv run oc research directions validate` 执行结果：`{"status": "ok", "problems": 0}`。

## 五、值得注意的数据质量问题（延续 I-20260923-02 的发现）

I-20260923-02 已经记录过该站点 `good-volatility-bad-volatility-and-the-cross-section-of-stock-returns` 页面出现物理上不可能的数字（波动率 6276%、回撤 -185%），判定为该页面实现有 bug、不采信。本轮补充两点：

1. **该站会给纯理论论文也套一个回测**（见上节"3 个排除项"），意味着"5,000 个同行评审策略"里混有相当比例并非真正的交易策略，逐条读正文摘要是必要的过滤步骤，不能只看卡片上的夏普数字。
2. **样本内 47 个候选里，"1990–2026"是几乎唯一出现的回测区间**，且绝大多数论文原始发表样本远早于当前——例如 `betting-against-correlation`（2016 年论文）、`fact-fiction-and-the-size-effect`（2018）、`macro-risk-of-low-volatility-portfolios`（2022）——这些"年化/夏普"都是平台自己用 1990–2026 全历史重新跑出来的数字，不是论文作者原始样本内的数字，也没有独立第三方复现来验证该平台自己的实现是否正确；`leakage-safe-financial-news-sentiment-trading`（2026-05）和 `systematic-abnormal-return-variation`（2025-11）等几篇发表时间非常新，几乎不可能有独立复现存在。这些数字应定位为"paperswithbacktest re-run"这一单一来源的说法，如 claim 字段所标注，不是多方交叉验证过的证据。

## 六、未能触达 / 未能完成的部分

- **约 56% 的目录（约 3,006 个策略）未被本轮采样覆盖**：根源是路径分页 `/strategies/page/N` 依赖 `robots.txt` 禁止的 `/api/`（详见第二节），只能用 102 个关键词的站内搜索采样，边际收益递减后停止，不是被网站拒绝或限流（全程零 403/429/5xx）。
- **可运行 Python 代码**：全站均未在公开页面展示，是付费档位功能，本次未解锁、未尝试绕过。
- **分年/分月收益拆解**：详情页图表数据不在服务端渲染 HTML 内，静态抓取拿不到，已如实记录为"未展示"而非编造或从图表估读。
- **个别详情页的"当前持仓"计数**：少数页面（如 `expectations-and-the-option-implied-variance`、`the-anomalous-behavior-of-the-s-p-covered-call-closed-end-fund`）未渲染持仓表格，`positions_total` 记为空，不是解析失败。
- 未尝试注册、未登录、未在 `.env`/凭证/爬虫层面做任何绕过；未运行 pytest；未触碰 crontab/broker/交易代码；未安装新包；未修改本任务范围外的任何既有文件。

## 结论与下一步建议（不是新的委托，仅供参考）

优先级最高的两条可执行、长期可持续关注的方向：`dir:covered_call_cef_income_pwb`（现成上市 CEF，最高毛年化）和 `dir:news_sentiment_trading_pwb`（贴合用户 alpha 分层里较高优先级的新闻/文本类信号，且方法论强调 point-in-time）。`dir:risk_based_portfolio_construction_pwb` 这个 11 源大类的核心教训是"换一个更聪明的协方差估计量，不能单独解决纯股票组合的深回撤问题"，与仓库已有的 vol-target 结论互相印证，短期不建议作为独立方向投入算力，除非结合真正的多资产分散或严格的仓位控制。三条"以论文之名、行理论之实"的排除项提示：以后再扫这个网站（或类似"paper→backtest"平台）时，逐条读详情页摘要仍然是必须的一步，不能只信任卡片夏普数字做筛选。
