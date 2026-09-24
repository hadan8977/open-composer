# Bulk-feed classification digest -- 2026-09-24

Bottom-up pass over the archive feed (`docs/plan-research-coverage-2026-09-23.zh.md` section 4 rule 7): every pulled item is classified against the coverage map independently of any search topic, so gaps show up by what never lands in a cell.

## By coverage cell

### alt_data.news_social -- News flow, social attention, sentiment

335 relevant item(s); by evidence tier: live_record=1, author_backtest=227, claim_only=49, theory=34, tool_or_data=24

- [Relative Sentiment and Machine Learning for Tactical Asset Allocation](https://alphaarchitect.com/2022/06/relative-sentiment-and-machine-learning-for-tactical-asset-allocation/) -- Alpha Architect, 2022-06-16: Describes a live asset management ensemble using relative sentiment indicators for tactical asset allocation.
- [Public Trader Identity: Adverse Selection and Return Predictability](https://arxiv.org/abs/2608.04373) -- arXiv, 2026-08-05: Uses decentralized exchange wallet identities to show persistent informativeness and return predictability from aggressive orders.
- [From News to Returns: A Granger-Causal Hypergraph Transformer on the Sphere](https://arxiv.org/abs/2510.04357) -- arXiv, 2025-10-05: A hypergraph transformer that models Granger-causal news and sentiment effects on asset returns.
- [Can ChatGPT Forecast Stock Price Movements? Return Predictability and Large Language Models](https://arxiv.org/abs/2304.07619) -- arXiv, 2023-04-15: A paper showing ChatGPT can predict stock price movements from news headlines, with about 90% hit rates for initial reactions. -- reported: 90% portfolio-day hit rates for initial reaction; strategy returns decline after costs
- [Risk & returns around FOMC press conferences: a novel perspective from computer vision](https://arxiv.org/abs/2012.06573) -- arXiv, 2020-12-11: A computer vision measure of FOMC press conference discussion complexity is associated with higher equity returns and lower realized volatility.
- [Are AI Risks Priced in the U.S. Stock Market? Evidence from Financial News Factors](https://arxiv.org/abs/2609.05485) -- arXiv, 2026-08-23: A paper constructs four news-based AI risk factors from WSJ articles and finds only the Misinformation factor is robustly priced in U.S. stock returns.
- [Disclosed Human-Capital Disruption and Firm-Specific Risk](https://arxiv.org/abs/2608.14859) -- arXiv, 2026-08-14: Constructs a measure of disclosed human-capital disruption from earnings calls and shows it is associated with higher firm-specific risk. -- reported: 0.55 pp higher idiosyncratic vol, 0.58 pp higher downside deviation, 0.46 pp lower worst monthly return per 1 SD
- [Large Language Model-Driven Small-Capitalization Trading: Integrating Financial News Sentiment, Macroeconomic Indicators, and Technical Signals](https://arxiv.org/abs/2608.12283) -- arXiv, 2026-08-12: Proposes an uncertainty-aware LLM-driven trading pipeline for Russell 2000 stocks combining news sentiment, macro indicators, and technical signals.
- [FinSMART: Financial Sentiment Analysis for Algorithmic Trading through Market-Aligned Reinforcement Learning](https://arxiv.org/abs/2607.28127) -- arXiv, 2026-07-30: FinSMART uses reinforcement learning to align financial sentiment analysis with market outcomes for algorithmic trading.
- [Zero-Copy Semantic Contagion: An In-Memory Streaming Architecture for Evolving Attention Graphs](https://arxiv.org/abs/2606.05733) -- arXiv, 2026-06-04: A streaming architecture that maps cross-company attention from news text to predict equity prices, with performance metrics on ingestion speed.
- [The Value of Information: A Puzzle](https://arxiv.org/abs/2605.11180) -- arXiv, 2026-05-11: Measures the value of information to informed traders via covariance between price changes and order flow in US equities. -- reported: Value of information about $3.5 million per year for average stock; aggregate 0.04% of market cap
- [Generalized Stock Price Prediction for Multiple Stocks Combined with News Fusion](https://arxiv.org/abs/2603.19286) -- arXiv, 2026-03-08: Introduces an LLM-based approach integrating daily financial news with stock price prediction using attention-based pooling.

### alt_data.short_selling -- FINRA daily short volume, short interest, fails-to-deliver

26 relevant item(s); by evidence tier: independent_replication=1, author_backtest=10, claim_only=6, theory=5, tool_or_data=4

- [Loosening Short Sale Constraints Makes Markets More Efficient](http://blog.alphaarchitect.com/2016/02/04/21959/) -- Alpha Architect, 2016-02-06: Examines the causal effect of short sale constraints on ten asset pricing anomalies using Regulation SHO, showing loosening constraints improves market efficiency.
- [Is There Alpha in Borrow Fees?](https://web.archive.org/web/20240524212550/https://www.quantrocket.com/blog/borrow-fees-alpha) -- Quant Rocket, 2024-05-18: Explores whether borrow fees can be used as an alpha factor in trading strategies using Alphalens.
- [Synthetic Lending Rates Predict Subsequent Market Return](https://quantpedia.com/synthetic-lending-rates-predict-subsequent-market-return/?a=6080) -- Quantpedia, 2021-12-10: Suggests that synthetic lending rates can predict subsequent market returns.
- [Short Selling + Insider Selling = Profitable Strategy?](https://web.archive.org/web/20221007213734/https://alphaarchitect.com/2019/05/13/short-selling-insider-selling-bad-news-part-2/) -- Alpha Architect, 2019-05-14: Studies combining short selling and insider selling data from 1977-2014 to form a profitable strategy.
- [Short Selling + Insider Selling = Bad News](https://web.archive.org/web/20220525203745/https://alphaarchitect.com/2019/04/01/short-selling-may-not-destabilize-markets-but-rather-improve-market-efficiency/) -- Alpha Architect, 2019-04-02: Examines relationship between short selling and insider selling and their combined impact on trading strategies.
- [Short Sellers Profitably Trade Prior to Credit Rating Agency Announcements](https://web.archive.org/web/20220808050625/https://alphaarchitect.com/2018/02/12/short-sellers-profitably-trade-prior-credit-rating-agency-announcements/) -- Alpha Architect, 2018-02-13: Examines how short sellers profitably trade prior to credit rating agency announcements, focusing on unexpected short selling behavior.
- [Industry Herding by Short Sellers Signals that Conditions are Changing](https://web.archive.org/web/20240712135356/https://alphaarchitect.com/2017/12/18/academic-research-insight-industry-herding-short-sellers-signals-conditions-changing/) -- Alpha Architect, 2017-12-20: Investigates whether industry concentration in short sellers' holdings conveys material information and generates excess returns.
- [The Double-Edged Sword of Short-Selling Bans](https://arxiv.org/abs/2609.08881) -- arXiv, 2026-09-08: A study of short-selling bans in Europe in 2020, showing effects on liquidity and price drawdowns.
- [Short Positions – do investors underreact due to illiquidity?](https://web.archive.org/web/20240812034605/https://alphaarchitect.com/2024/06/short-positions/) -- Alpha Architect, 2024-06-23: Examines whether investors underreact to short positions due to illiquidity, focusing on the role of short sellers in keeping prices efficient.
- [Behavioral Bias Benefits: Beating Benchmarks By Bundling Bouncy Baskets](https://arxiv.org/abs/2109.03740) -- arXiv, 2021-08-10: An investment strategy that takes long positions in heavily shorted securities expected to benefit from a market rally.
- [Compound Your Knowledge Episode 7: Momentum & Short Sellers](https://web.archive.org/web/20220525204339/https://alphaarchitect.com/2019/04/08/compound-your-knowledge-episode-7-momentum-short-sellers/) -- Alpha Architect, 2019-04-09: Video discussing articles on momentum of news and an out-of-sample test related to short sellers.
- [Betting on a Short Squeeze as Investment Strategy](https://web.archive.org/web/20240527230050/https://alphaarchitect.com/2024/03/short-squeeze/) -- Alpha Architect, 2024-03-12: Explores short squeeze as an investment strategy, referencing academic research on lottery-like payoffs.

### alt_data.web_and_other -- Web attention, analysts, institutional holdings and other alternative data

87 relevant item(s); by evidence tier: author_backtest=56, claim_only=9, theory=11, tool_or_data=11

- [AI Premium](https://arxiv.org/abs/2606.30583) -- arXiv, 2026-06-29: Constructs an AI factor from token consumption data and estimates firm-level AI betas and the AI premium.
- [The Price of Permission: Classification Uncertainty in Constrained Capital Markets](https://arxiv.org/abs/2608.12634) -- arXiv, 2026-08-12: Introduces a classification-uncertainty measure from Shariah-compliant equity screening rules and tests its predictive power for next-month returns in a US equity panel.
- [Consuming Values](https://arxiv.org/abs/2607.27569) -- arXiv, 2026-07-30: A study using payment card transactions to measure how firm stances on social issues affect consumer spending and revenue. -- reported: 19 percent increase in consumption in the month following a firm's social stance
- [Needles in a haystack: using forensic network science to uncover insider trading](https://arxiv.org/abs/2512.18918) -- arXiv, 2025-12-21: Proposes a network science approach to flag coordinated insider trading using 2.9 million SEC-reported insider trades.
- [Sources and Nonlinearity of High Volume Return Premium: An Empirical Study on the Differential Effects of Investor Identity versus Trading Intensity (2020-2024)](https://arxiv.org/abs/2512.14134) -- arXiv, 2025-12-16: Resolves the Low Volume Return Premium puzzle in Korea by showing HVRP exists when institutional buying intensity is normalized by market cap, with a monotonic return pattern. -- reported: Monotonic relationship between institutional buying intensity and returns
- [Quantifying firm-level risks from nature deterioration](https://arxiv.org/abs/2501.14391) -- arXiv, 2025-01-24: Quantifies firm-level risks from nature deterioration, estimating value losses for global equities. -- reported: global equities shed 26.8% in a scenario of unabated nature decline
- [The Value of Information from Sell-side Analysts](https://arxiv.org/abs/2411.13813) -- arXiv, 2024-11-21: Shows that qualitative information in sell-side analyst reports, extracted via LLM embeddings, explains over 10% of contemporaneous stock returns out-of-sample. -- reported: Explains above 10% of contemporaneous stock returns out-of-sample
- [Extracting Alpha from Financial Analyst Networks](https://arxiv.org/abs/2410.20597) -- arXiv, 2024-10-27: A momentum trading signal is built from the coverage network of financial analysts, using co-coverage to construct firm networks.
- [Insights from the Geopolitical Sentiment Index made with Google Trends](https://web.archive.org/web/20240904080130/https://quantpedia.com/insights-from-the-geopolitical-sentiment-index-made-with-google-trends/?a=6080) -- Quantpedia, 2024-09-04: Describes a geopolitical sentiment index built from Google Trends and its potential market insights.
- [Predicting public market behavior from private equity deals](https://arxiv.org/abs/2407.01818) -- arXiv, 2024-07-01: Uses private equity deal data to predict quarterly public market and sector returns with a logit model.
- [How to Track Retail Investor Activity in TAQ](https://web.archive.org/web/20240619054223/https://alphaarchitect.com/2024/06/subpenny-price-movements/) -- Alpha Architect, 2024-06-19: Explores the effectiveness of the BJZZ algorithm in identifying and signing retail trades executed off exchanges with subpenny price improvements in TAQ data.
- [Can market volumes reveal traders' rationality and a new risk premium?](https://arxiv.org/abs/2406.05854) -- arXiv, 2024-06-09: Proposes a trading strategy model based on volume and risk aversion, estimating a price of risk from market volumes.

### event.8k_item_events -- 8-K item-coded events (1.01, 2.02, 5.02, ...), offerings/ATM, spin-offs, M&A targets, dividend changes, biotech catalysts

30 relevant item(s); by evidence tier: author_backtest=19, claim_only=6, theory=4, tool_or_data=1

- [Market Reactions to Material Cybersecurity Incident Disclosures](https://arxiv.org/abs/2512.06144) -- arXiv, 2025-12-05: Examines short-term market reactions to material cybersecurity incident disclosures under 8-K Item 1.05, finding negative price responses.
- [A Deep Learning Method for Predicting Mergers and Acquisitions: Temporal Dynamic Industry Networks](https://arxiv.org/abs/2404.07298) -- arXiv, 2024-04-10: A deep learning model predicts M&A activities using temporal dynamic industry networks and peer effects.
- [Machine learning-based similarity measure to forecast M&A from patent data](https://arxiv.org/abs/2404.07179) -- arXiv, 2024-04-10: The MASS algorithm uses patent data similarity to forecast M&A deals.
- [New drugs and stock market: how to predict pharma market reaction to clinical trial announcements](https://arxiv.org/abs/2208.07248) -- arXiv, 2022-08-11: Predicts pharma stock price reactions to clinical trial announcements using statistical evidence.
- [Trade the Event: Corporate Events Detection for News-Based Event-Driven Trading](https://arxiv.org/abs/2105.12825) -- arXiv, 2021-05-26: Introduces an event-driven trading strategy that detects corporate events from news articles to predict stock movements and profit from temporary mispricing.
- [A study about who is interested in stock splitting and why: considering companies, shareholders or managers](https://arxiv.org/abs/2510.15879) -- arXiv, 2025-08-23: This paper studies the motivations and effects of stock splits, examining why companies and managers split stock and shareholder reactions.
- [Monopoly Unveiled: Telecom Breakups in the US and Mexico](https://arxiv.org/abs/2407.09695) -- arXiv, 2024-07-12: Analyzes the market capitalization decline of AT&T and AMX after monopoly breakups to gauge market power valuation. -- reported: AT&T value drop 65%, AMX drop 32% post-breakup
- [The impact of Facebook-Cambridge Analytica data scandal on the USA tech stock market: An event study based on clustering method](https://arxiv.org/abs/2402.14206) -- arXiv, 2024-02-22: Event study of the Facebook-Cambridge Analytica scandal's intra-industry effects on US tech stocks using clustering and cumulative abnormal returns.
- [Prioritizing Investments in Cybersecurity: Empirical Evidence from an Event Study on the Determinants of Cyberattack Costs](https://arxiv.org/abs/2402.04773) -- arXiv, 2024-02-07: An event study on the cost of cyberattacks on listed firms using a three-day window, relevant to event-driven trading.
- [Security Issuance, Institutional Investors and Quid Pro Quo](https://arxiv.org/abs/2211.16643) -- arXiv, 2022-11-30: A study of SPAC investor behavior and returns, relevant to event-driven trading.
- [Stock price reaction to power outages following extreme weather events: Evidence from Texas power outage](https://arxiv.org/abs/2210.16905) -- arXiv, 2022-10-30: A study measuring the stock price reaction of firms to the 2021 Texas winter storm using abnormal return models.
- [Automatic Identification and Classification of Share Buybacks and their Effect on Short-, Mid- and Long-Term Returns](https://arxiv.org/abs/2209.12863) -- arXiv, 2022-09-26: Uses NLP to detect share buyback announcements and analyzes their effect on short-, mid-, and long-term returns. -- reported: accuracy up to 90% for detection; excess return analysis

### event.earnings_pead -- Post-earnings drift, earnings-day gap continuation, guidance

45 relevant item(s); by evidence tier: author_backtest=36, claim_only=4, theory=5

- [Which Voices Move Markets? Speaker Identity and the Cross-Section of Post-Earnings Returns](https://arxiv.org/abs/2604.13260) -- arXiv, 2026-04-14: Uses FinBERT on earnings call transcripts to show speaker-weighted sentiment predicts post-earnings returns with significant alpha. -- reported: IC 0.142 OOS, monthly long-short alpha 2.03% (t=6.49)
- [Forecasting Future Language: Context Design for Mention Markets](https://arxiv.org/abs/2602.21229) -- arXiv, 2026-02-04: Studies how input context design affects LLM forecasts for keyword-mention outcomes in earnings-call prediction markets.
- [Warp speed price moves: Jumps after earnings announcements](https://arxiv.org/abs/2601.08962) -- arXiv, 2026-01-13: Shows earnings announcements almost always induce jumps in stock prices and raise co-jump probability in non-announcing firms.
- [Retail Investor Horizon and Earnings Announcements](https://arxiv.org/abs/2512.00280) -- arXiv, 2025-11-29: Shows that retail investor holding period from StockTwits differentiates earnings-related anomalies, with long-horizon retail linked to stronger PEAD.
- [Corporate Earnings Calls and Analyst Beliefs](https://arxiv.org/abs/2511.15214) -- arXiv, 2025-11-19: Shows that narratives extracted from earnings calls improve prediction of realized earnings and analyst expectations, using a text-morphing methodology with LLMs.
- [Does Overnight News Explain Overnight Returns?](https://arxiv.org/abs/2507.04481) -- arXiv, 2025-07-06: Shows that overnight news topics explain a large part of the overnight return premium in US stocks.
- [Harnessing Earnings Reports for Stock Predictions: A QLoRA-Enhanced LLM Approach](https://arxiv.org/abs/2408.06634) -- arXiv, 2024-08-13: Uses LLMs fine-tuned with QLoRA to predict stock movements after earnings reports.
- [ECC Analyzer: Extract Trading Signal from Earnings Conference Calls using Large Language Model for Stock Performance Prediction](https://arxiv.org/abs/2404.18470) -- arXiv, 2024-04-29: Uses large language models to extract trading signals from earnings conference calls for stock performance prediction.
- [Option Smile Volatility and Implied Probabilities: Implications of Concavity in IV Curves](https://arxiv.org/abs/2307.15718) -- arXiv, 2023-07-27: Studies concavity in implied volatility smiles before earnings announcements and compares returns between concave and non-concave smiles.
- [ESG Reputation Risk Matters: An Event Study Based on Social Media Data](https://arxiv.org/abs/2307.11571) -- arXiv, 2023-07-21: Event study using 114 million tweets to measure ESG reputational risk spikes and their impact on S&P100 stock returns.
- [Expectations Formation with Fat-tailed Processes: Evidence from Sales Forecasts](https://arxiv.org/abs/2210.10169) -- arXiv, 2022-10-18: This paper analyzes sales forecast errors and finds non-linear under/overreaction, which can inform earnings-related trading strategies.
- [Investor Emotions and Earnings Announcements](https://arxiv.org/abs/2006.13934) -- arXiv, 2020-06-24: Tests whether pre-earnings social media emotions predict earnings and announcement returns, finding excitement leads to lower returns. -- reported: 7.8 bps lower announcement return per std dev excitement

### event.insider_13d -- Insider buying and 13D activist filings

31 relevant item(s); by evidence tier: author_backtest=18, claim_only=4, theory=7, tool_or_data=2

- [Detecting and Explaining Unlawful Insider Trading: A Shapley Value and Causal Forest Approach to Identifying Key Drivers and Causal Relationships](https://arxiv.org/abs/2602.19841) -- arXiv, 2026-02-23: Uses SHAP and causal forests to detect unlawful insider trading and identify key drivers.
- [The Information Dynamics of Insider Intent: How Reporting Inversions (Form 144) Mask Informational Rents in Insider Sales (Form 4)](https://arxiv.org/abs/2602.17890) -- arXiv, 2026-02-19: A study on informational frictions in SEC Form 144 and Form 4 insider sales, using event-study methodology.
- [Needles in a haystack: using forensic network science to uncover insider trading](https://arxiv.org/abs/2512.18918) -- arXiv, 2025-12-21: Proposes a network science approach to flag coordinated insider trading using 2.9 million SEC-reported insider trades.
- [Do Activists Align with Larger Mutual Funds?](https://arxiv.org/abs/2411.16553) -- arXiv, 2024-11-25: Hedge funds align activist campaigns with large institutional shareholders' preferences, increasing campaign success.
- [A Random Forest approach to detect and identify Unlawful Insider Trading](https://arxiv.org/abs/2411.13564) -- arXiv, 2024-11-09: Uses a random forest to detect and identify unlawful insider trading from high-dimensional financial and trade data.
- [Form 3 and Form 4 Alpha: Focus on What Insiders Don’t Trade](https://alphaarchitect.com/2022/05/following-what-insiders-dont-trade/) -- Alpha Architect, 2022-05-17: Focuses on insider non-trades (Form 3/4) as an alpha signal.
- [Short Selling + Insider Selling = Profitable Strategy?](https://web.archive.org/web/20221007213734/https://alphaarchitect.com/2019/05/13/short-selling-insider-selling-bad-news-part-2/) -- Alpha Architect, 2019-05-14: Studies combining short selling and insider selling data from 1977-2014 to form a profitable strategy.
- [Short Selling + Insider Selling = Bad News](https://web.archive.org/web/20220525203745/https://alphaarchitect.com/2019/04/01/short-selling-may-not-destabilize-markets-but-rather-improve-market-efficiency/) -- Alpha Architect, 2019-04-02: Examines relationship between short selling and insider selling and their combined impact on trading strategies.
- [Mining Illegal Insider Trading of Stocks: A Proactive Approach](https://arxiv.org/abs/1807.00939) -- arXiv, 2018-07-02: This paper presents a deep-learning approach to detect and predict illegal insider trading from heterogeneous data sources.
- [Following Opportunistic insiders Earns over 1% Monthly Alpha](http://blog.alphaarchitect.com/2016/01/25/following-opportunistic-insiders-earns-1-alpha/) -- Alpha Architect, 2016-01-26: Shows that opportunistic insider traders can be identified by profitability of trades before earnings, yielding over 1% monthly alpha. -- reported: over 1% monthly alpha
- [Insider Purchase Signals in Microcap Equities: Gradient Boosting Detection of Abnormal Returns](https://arxiv.org/abs/2602.06198) -- arXiv, 2026-02-05: Uses gradient boosting on SEC Form 4 insider purchase filings to predict abnormal returns in US microcap stocks. -- reported: AUC 0.70, precision 0.38, recall 0.69 on 2024 OOS
- [An extreme Gradient Boosting (XGBoost) Trees approach to Detect and Identify Unlawful Insider Trading (UIT) Transactions](https://arxiv.org/abs/2511.08306) -- arXiv, 2025-11-11: This paper uses XGBoost to detect unlawful insider trading transactions.

### factor_library.anomaly_replication -- Published anomalies and formulaic factor libraries

723 relevant item(s); by evidence tier: independent_replication=11, author_backtest=379, claim_only=93, theory=226, tool_or_data=14

- [Publication Bias in Asset Pricing Research](https://arxiv.org/abs/2209.13623) -- arXiv, 2022-09-27: A meta-study on publication bias in asset pricing research, discussing replication and out-of-sample persistence of return predictors.
- [International Tests of Factor Anomalies: Most Don   t Survive](https://web.archive.org/web/20210828053602/https://alphaarchitect.com/2021/08/27/international-tests-of-anomalies-most-dont-survive/) -- Alpha Architect, 2021-08-28: Examines international tests of factor anomalies, finding most do not survive out of sample.
- [Day of the week and the cross-section of returns](https://web.archive.org/web/20220808052216/https://eranraviv.com/day-of-the-week-and-the-cross-section-of-returns/) -- Eran Raviv, 2019-03-16: Replicates a paper on day-of-the-week effects in the cross-section of stock returns.
- [Factor Decay](https://www.taltoncm.com/blog/2019/2/21/factor-decay) -- Talton Capital, 2019-02-22: Studies persistence of nine anomalies in the U.K. equity market.
- [Equity Anomalies Persist in International Markets](https://web.archive.org/web/20210926003757/http://quantpedia.com/Blog/Details/equity-anomalies-persist-in-international-markets?a=6080) -- Quantpedia, 2016-08-24: Study of 138 anomalies across 39 international markets examining pre- and post-publication return predictability.
- [Does Academic Research Destroy Stock Return Predictability? (h/t @AbnormalReturns)](http://www.afajof.org/details/journalArticle/8811701/Does-Academic-Research-Destroy-Stock-Return-Predictability.html) -- , 2016-02-09: Studies out-of-sample and post-publication return predictability of 97 cross-sectional stock return predictors. -- reported: Portfolio returns are 26% lower out-of-sample and 58% lower post-publication
- [Factors are global, respectable and repeatable](https://web.archive.org/web/20250414162519/https://alphaarchitect.com/2024/11/factors-are-global-respectable-and-repeatable/) -- Alpha Architect, 2024-11-26: Argues that factor research is not chaotic and that 82% of factors are repeatable globally. -- reported: 82% of factors are repeatable
- [Revisiting Boehmer et al. (2021): Recent Period, Alternative Method, Different Conclusions](https://arxiv.org/abs/2403.17095) -- arXiv, 2024-03-25: Replicates and extends Boehmer et al. (2021) retail order imbalance study, finding weakened predictive power in recent period. -- reported: ROI predictive power weakens; long-short strategy no longer profitable in 2016-2021
- [Can the Best Stock Pickers Still Beat the Market? An Out of Sample Test](https://alphaarchitect.com/2020/09/14/are-fund-managers-stars-skilled-at-picking-stocks-an-out-of-sample-test/) -- Alpha Architect, 2020-09-17: Out-of-sample test of whether top stock pickers can beat the market, likely replicating a published anomaly.
- [10 Large Scale Factor Anomaly Studies with Definitions](https://web.archive.org/web/20221007213734/https://www.twocenturies.com/blog/2019/4/24/a-list-of-comprehensive-multi-factor-academic-papers) -- Two Centuries Investments, 2019-05-14: Lists large-scale factor anomaly studies with definitions, including replication of published anomalies.
- [Academic Research Insights: Global Equities and Overreaction](https://web.archive.org/web/20170908010807/https://alphaarchitect.com/2017/08/28/academic-research-insight-global-equities-overreaction/) -- Alpha Architect, 2017-08-30: Reviews academic research on long-term overreaction patterns in global equity markets.
- [Wasserstein-Barycentric Interaction Fields for Spatial Factor Models: Evidence from Language-Model Representations](https://arxiv.org/abs/2608.29669) -- arXiv, 2026-08-30: Constructs a spatial factor model from language-model article embeddings and shows it outperforms equal-weighted peer support in a 52-firm sample. -- reported: penalty ratio 3.46 (95% CI [2.89, 4.17]) for 2023-2026

### flows_structural.calendar_and_fomc -- Turn of month, pre-FOMC, pre-holiday

141 relevant item(s); by evidence tier: independent_replication=1, author_backtest=99, claim_only=36, theory=5

- [Front Running Commodity Seasonality](https://web.archive.org/web/20250215073230/https://allocatesmartly.com/front-running-commodity-seasonality/?aff=634) -- Allocate Smartly, 2024-12-24: Independently tests and extends commodity seasonality front-running strategies.
- [Modeling Hawkish-Dovish Latent Beliefs in Multi-Agent Debate-Based LLMs for Monetary Policy Decision Classification](https://arxiv.org/abs/2511.02469) -- arXiv, 2025-11-04: Uses multi-agent LLM debate to classify FOMC policy decisions, potentially useful for predicting market reactions to FOMC announcements.
- [It's not always about the money, sometimes it's about sending a message: Evidence of Informational Content in Monetary Policy Announcements](https://arxiv.org/abs/2111.06365) -- arXiv, 2021-11-11: Identifies informational content of FOMC announcements using linguistic tools on statements and news, showing impact on short-term yields.
- [When the Fed Speaks: Dynamics and Forecasts of the Volatility Surface](https://arxiv.org/abs/2608.10693) -- arXiv, 2026-08-11: A study forecasting implied volatility surface dynamics around FOMC meetings, testing if ML can beat a random walk.
- [Front-Running Seasonality in US Stock Sectors](https://web.archive.org/web/20250215073230/https://quantpedia.com/front-running-seasonality-in-us-stock-sectors/?a=6080) -- Quantpedia, 2024-12-24: Describes front-running seasonality patterns in US stock sectors.
- [The Worst One-Day Shocks and Biggest Geopolitical Events of the Past Century](https://quantpedia.com/the-worst-one-day-shocks-and-the-biggest-geopolitical-events-of-the-past-century/?a=6080) -- Quantpedia, 2022-07-12: Analyzes the 50 worst one-day shocks and subsequent days across asset classes over a century.
- [A Rare    Inverse Zweig Breadth Collapse    Triggers](https://quantifiableedges.com/a-rare-inverse-zweig-breadth-collapse-triggers/) -- Quantifiable Edges, 2022-06-14: Describes a rare inverse Zweig breadth collapse signal based on NYSE up issues, likely a market-timing indicator.
- [Diving Deeper: Does the Day of the Month Matter?](https://allocatesmartly.com/diving-deeper-does-the-day-of-the-month-matter/?aff=634) -- Allocate Smartly, 2021-11-18: Investigates whether the day of the month matters for TAA strategies.
- [Spillovers of US Interest Rates: Monetary Policy & Information Effects](https://arxiv.org/abs/2111.08631) -- arXiv, 2021-11-16: Quantifies international spillovers of US monetary policy and information shocks around FOMC announcements.
- [$SPX Loves Tax Day](https://quantifiableedges.com/spx-loves-tax-day/) -- Quantifiable Edges, 2021-05-18: Studies the historical tendency of the S&P 500 to rise on US tax day, possibly due to IRA contributions.
- [Pre-Election Drift in the Stock Market](https://web.archive.org/web/20200922081002/https://quantpedia.com/pre-election-drift-in-the-stock-market/?a=6080) -- Quantpedia, 2020-01-24: Describes the pre-election drift anomaly as a calendar-based seasonal effect in the stock market.
- [January Opex Weak](http://quantifiableedges.com/january-opex-weak-2/) -- Quantifiable Edges, 2019-01-13: Examines the historical performance of buying during January opex week, noting it is typically weak.

### flows_structural.rebalance_and_hedging_flows -- Index rebalance, month-end pension rebalance, options expiration and dealer hedging, leveraged-ETF close rebalancing, ETF creation/redemption

61 relevant item(s); by evidence tier: author_backtest=26, claim_only=10, theory=24, tool_or_data=1

- [Research Review | 10 March 2023 | ETFs](https://www.capitalspectator.com/research-review-10-march-2023-etfs/) -- Capital Spectator, 2023-03-13: Reviews a paper on ETF dividend cycles, noting ETFs collect about 7% of U.S. corporate dividends and redistribute them.
- [Can Market Maker Capital Constraints Result in Mispricing of ETFs?](https://alphaarchitect.com/2022/04/can-market-maker-capital-constraints-result-in-mispricing-of-etfs/) -- Alpha Architect, 2022-04-22: Explores whether market maker capital constraints can lead to mispricing in ETFs.
- [Evidence of Crowding on Russell 3000 Reconstitution Events](https://arxiv.org/abs/2006.07456) -- arXiv, 2020-06-12: Develops a methodology to replicate Russell 3000 reconstitutions and measures permanent and temporary price impacts, providing a Python package.
- [Intraday Momentum with Leveraged ETFs](https://www.quantrocket.com/blog/leveraged-etf-intraday-momentum) -- Quant Rocket, 2019-03-06: Explores an intraday momentum strategy based on leveraged ETF forced buying and selling.
- [Co-impact: Crowding effects in institutional trading activity](https://arxiv.org/abs/1804.09565) -- arXiv, 2018-04-25: An analysis of crowding effects on market impact using institutional metaorder data, relevant for understanding flow-driven price moves.
- [Index Front Running: What Happens When a Stock is Added to an Index?](https://web.archive.org/web/20220703124319/http://www.signalplot.com/index-front-running-what-happens-when-a-stock-is-added-to-an-index/) -- Signal Plot, 2016-10-04: Research on index front running by buying stocks before they are added to indexes tracked by passive funds.
- [A Levered ETF Anomaly Explained](https://arxiv.org/abs/2604.27287) -- arXiv, 2026-04-30: Explains the underperformance of levered ETFs versus the S&P 500 during 2022-2023 through compounding, volatility, and covariance effects. -- reported: Two-thirds of return difference attributed to compounding/volatility; rest to covariance
- [On the hidden costs of passive investing](https://arxiv.org/abs/2506.21775) -- arXiv, 2025-06-26: Analysis of hidden costs in passive investing during index reconstitution, showing that gradual acquisition is cheaper than buying at market close. -- reported: Costs of hundreds of basis points compared to gradual acquisition
- [Smart leverage? Rethinking the role of Leveraged Exchange Traded Funds in constructing portfolios to beat a benchmark](https://arxiv.org/abs/2412.05431) -- arXiv, 2024-12-06: Investigates dynamically-optimal long-term investment strategies using broad stock market index LETFs to outperform benchmarks.
- [Markets Becoming More Efficient: The Disappearing Index Effect](https://web.archive.org/web/20250414163847/https://alphaarchitect.com/2024/11/disappearing-index-effect/) -- Alpha Architect, 2024-11-19: Discusses the disappearing index effect and abnormal returns to index additions, indicating market efficiency changes.
- [How to Utilize Anticipated ETF Rebalances](https://quantpedia.com/how-to-utilize-anticipated-etf-rebalances/?a=6080) -- Quantpedia, 2022-02-12: Discusses how to anticipate and trade ETF rebalances.
- [Tesla’s inclusion in the S&P 500 – Is there a trade?](https://web.archive.org/web/20201120063623/https://robotwealth.com/tsla-spx-index-inclusion/) -- Robot Wealth, 2020-11-20: Explores potential trading opportunities around Tesla's inclusion in the S&P 500 index.

### fundamental.pit_accounting -- Value, quality, profitability, accruals, accounting changes

509 relevant item(s); by evidence tier: live_record=2, author_backtest=275, claim_only=90, theory=134, tool_or_data=8

- [Graham Value Portfolio Update](http://www.scottsinvestments.com/2015/04/16/graham-value-portfolio-update-2/) -- Scott’s Investments, 2015-04-18: Update on a Benjamin Graham-inspired value stock portfolio started in January 2012.
- [Dividend Champion Portfolio April Update](http://www.scottsinvestments.com/2015/04/08/dividend-champion-portfolio-april-update/) -- Scott’s Investments, 2015-04-10: A publicly tracked portfolio of high-yield dividend champions with a history of raising dividends.
- [DisclosureBeta: A Measurement-Channel Theory for Regime-Conditioned Betas from LLM-Read Risk Disclosures](https://arxiv.org/abs/2609.02900) -- arXiv, 2026-07-05: A theory for regime-conditioned betas from LLM-read risk disclosures, with a claimed empirical IPO accuracy improvement.
- [Supply Chain Propagation of Textual Signals: LLM Embeddings and Cross-Sectional Return Predictability](https://arxiv.org/abs/2606.29290) -- arXiv, 2026-06-28: Proposes augmenting LLM embeddings of 10-K MD&A sections with supply chain knowledge graph propagation, finding significant return predictability in cross-sectional regressions. -- reported: Newey-West t-statistic significant for net_pc_5
- [Financial Statement Analysis with Large Language Models](https://arxiv.org/abs/2407.17866) -- arXiv, 2024-07-25: Investigates whether LLMs can perform financial statement analysis to predict future earnings direction, outperforming human analysts.
- [Disclosed Human-Capital Disruption and Firm-Specific Risk](https://arxiv.org/abs/2608.14859) -- arXiv, 2026-08-14: Constructs a measure of disclosed human-capital disruption from earnings calls and shows it is associated with higher firm-specific risk. -- reported: 0.55 pp higher idiosyncratic vol, 0.58 pp higher downside deviation, 0.46 pp lower worst monthly return per 1 SD
- [The Price of Permission: Classification Uncertainty in Constrained Capital Markets](https://arxiv.org/abs/2608.12634) -- arXiv, 2026-08-12: Introduces a classification-uncertainty measure from Shariah-compliant equity screening rules and tests its predictive power for next-month returns in a US equity panel.
- [How Much of a 10-K Matters? Aggregation-Dependent Value of Full-Text versus Risk-Factor Sentiment](https://arxiv.org/abs/2607.14174) -- arXiv, 2026-07-15: Extends a supervised lexicon-learning approach to 10-K filings and risk-factor sections, training sentiment against return and volatility labels.
- [Temperature Anomalies and Climate Physical Risk in Portfolio Construction](https://arxiv.org/abs/2604.11143) -- arXiv, 2026-04-13: Introduces climate risk metrics based on temperature anomalies and studies their impact on global equity portfolios.
- [When David becomes Goliath: Repo dealer-driven bond mispricing](https://arxiv.org/abs/2603.10690) -- arXiv, 2026-03-11: Shows how repo dealer market power and linkages cause bond mispricing and liquidity frictions. -- reported: 0.5-1.3 pp yield deviation from market power; 2-4 pp from dealer shocks
- [Multimodal Insights into Credit Risk Modelling: Integrating Climate and Text Data for Default Prediction](https://arxiv.org/abs/2601.00478) -- arXiv, 2026-01-01: A multimodal framework integrating structured credit variables, climate data, and text for default prediction of micro and small enterprises.
- [From Binary Screens to Continuous Compliance: A Shariah Screening Measure for Portfolio Design](https://arxiv.org/abs/2512.22858) -- arXiv, 2025-12-28: Develops a continuous Shariah compliance index for US equities and tests it with monthly portfolio formation from 1999-2024.

### infra.universe_data -- Tradable universe, delisted backfill, data hygiene

255 relevant item(s); by evidence tier: live_record=1, author_backtest=8, claim_only=10, theory=38, tool_or_data=198

- [How I Automated My Trading Strategy Using AWS Cloud for Free (Part 1)](https://web.archive.org/web/20241108234244/https://www.blackarbs.com/blog/how-i-automated-my-trading-strategy-using-aws-cloud-for-free) -- Black Arbs, 2024-10-11: Describes automating a long-only ETF strategy using AWS cloud, with lessons learned from launching a subscription service.
- [When Alpha Disappears: A One-Switch Benchmark for Decision-Time Leakage in Financial Backtests](https://arxiv.org/abs/2605.23959) -- arXiv, 2026-05-12: A benchmark for diagnosing decision-time leakage in financial backtests by toggling evaluation conventions.
- [Data-driven measures of high-frequency trading](https://arxiv.org/abs/2405.08101) -- arXiv, 2024-05-13: Develops data-driven measures of high-frequency trading activity using machine learning on public intraday data for the U.S. stock universe.
- [Multi-Industry Simplex : A Probabilistic Extension of GICS](https://arxiv.org/abs/2310.04280) -- arXiv, 2023-10-06: Develops a probabilistic industry classification extension to GICS for diversified firms.
- [Statistical Industry Classification](https://arxiv.org/abs/1607.04883) -- arXiv, 2016-07-17: Presents algorithms for statistical industry classification and hybrid classifications, with backtests showing these details matter.
- [Canonical Sectors and Evolution of Firms in the US Stock Markets](https://arxiv.org/abs/1503.06205) -- arXiv, 2015-03-20: Uses unsupervised machine learning on stock returns to identify canonical sectors for classification.
- [Impact of Dataset Selection on the Performance of Trading Strategies](https://quantpedia.com/impact-of-dataset-selection-on-the-performance-of-trading-strategies/?a=6080) -- Quantpedia, 2022-11-15: Discusses how dataset selection affects trading strategy performance.
- [How Does ETF Liquidity Affect ETF Returns, Volatility, and Tracking Error?](https://alphaarchitect.com/2021/01/11/how-does-etf-liquidity-affect-etf-returns-volatility-and-tracking-error/) -- Alpha Architect, 2021-01-13: Examines how ETF liquidity affects returns, volatility, and tracking error.
- [Backtesting   A Cautionary Example](http://www.scottsinvestments.com/2015/06/24/backtesting-a-cautionary-example/) -- Scott’s Investments, 2015-06-26: Presents a cautionary example of backtesting, showing that impressive historical results may not hold out-of-sample. -- reported: impressive risk-adjusted results since 2004
- [Index Replication: avoid the negatives!](https://alphaarchitect.com/2023/06/index-replication/) -- Alpha Architect, 2023-06-21: Highlights benefits of index funds and discusses index replication challenges.
- [Visualizing the Robustness of the US Equity ETF Market](https://alphaarchitect.com/2022/06/visualizing-active-share-across-all-us-equity-etfs/) -- Alpha Architect, 2022-06-09: Discusses the robustness and differentiation of US equity ETFs, questioning the notion that they are all undifferentiated index funds.
- [Myth-Busting: ETFs Are Eating the World](https://insights.factorresearch.com/research-myth-busting-etfs-are-eating-the-world/) -- Factor Research, 2022-01-25: Debunks myths about ETF ownership and trading impact on US stocks.

### intraday_hf.etf_intraday -- ETF opening-range breakout, SPY noise-band momentum

11 relevant item(s); by evidence tier: author_backtest=7, claim_only=1, theory=3

- [Push-response anomalies in high-frequency S&P 500 price series](https://arxiv.org/abs/2511.06177) -- arXiv, 2025-11-09: Analyzes high-frequency SPY price data to test for conditional nonrandomness in intraday price changes, finding structural shifts in push-response patterns.
- [The market drives ETFs or ETFs the market: causality without Granger](https://arxiv.org/abs/2204.03760) -- arXiv, 2022-04-07: Uses deep learning to analyze causality between ETF and stock transaction imbalances, finding ETF imbalances more informative.
- [Intraday Momentum with Leveraged ETFs](https://www.quantrocket.com/blog/leveraged-etf-intraday-momentum) -- Quant Rocket, 2019-03-06: Explores an intraday momentum strategy based on leveraged ETF forced buying and selling.
- [Forecasting Intraday Volume in Equity Markets with Machine Learning](https://arxiv.org/abs/2505.08180) -- arXiv, 2025-05-13: A study forecasting intraday trading volumes with machine learning, showing high predictability and economic benefits via VWAP.
- [Market intraday momentum](https://web.archive.org/web/20220808042308/https://eranraviv.com/market-intraday-momentum/) -- Eran Raviv, 2018-07-30: Discusses market intraday momentum based on S&P 500 ETF data.
- [Entropy and efficiency of the ETF market](https://arxiv.org/abs/1609.04199) -- arXiv, 2016-09-14: Measures information efficiency of 55 NYSE ETFs using Shannon entropy on high-frequency price series, isolating inefficiencies from microstructure effects.
- [Risk-Adjusted Performance of Random Forest Models in High-Frequency Trading](https://arxiv.org/abs/2412.15448) -- arXiv, 2024-12-19: Evaluates random forest models with technical indicators on minute-level SPY data, finding a stark contrast between in-sample and out-of-sample performance. -- reported: R^2 values for in-sample and out-of-sample
- [Slava Ukraini! Latest from Only VIX, Quantocracy contributor in Ukraine: Nightshares ETFs](http://onlyvix.blogspot.com/2022/07/nightshares-etfs.html) -- Only VIX, 2022-07-06: Describes ETFs capturing the night effect, the difference between overnight and intraday returns.
- [Trading against disorderly liquidation of a large position under asymmetric information and market impact](https://arxiv.org/abs/1610.01937) -- arXiv, 2016-10-06: Models trading against a large trader's disorderly liquidation under asymmetric information and market impact.
- [Autocorrelation of SPY, and the Redneck Correlogram](http://throwinggoodmoney.com/2016/02/autocorrelation-of-spy-and-the-redneck-correlogram/) -- Throwing Good Money, 2016-02-06: Discusses autocorrelation of SPY and a 'Redneck Correlogram' for time series analysis, likely for intraday patterns.
- [ETF Trading: What’s the best time?](https://alphaarchitect.com/2023/05/best-times-etf-investors-trade/) -- Alpha Architect, 2023-05-03: Discusses the best time of day to trade ETFs based on bid/ask spreads, focusing on transaction costs.

### intraday_hf.hf_derived_daily -- High-frequency-derived daily signals (jumps, realized skewness)

199 relevant item(s); by evidence tier: forward_test=1, author_backtest=71, claim_only=4, theory=119, tool_or_data=4

- [Interpretable Hypothesis-Driven Trading:A Rigorous Walk-Forward Validation Framework for Market Microstructure Signals](https://arxiv.org/abs/2512.12924) -- arXiv, 2025-12-15: A walk-forward validation framework for market microstructure signals, combining interpretable hypotheses with reinforcement learning and out-of-sample testing.
- [Cross-sectional topological anomaly scores and intraday return predictability in the S&P 500: A BallMapper, decoder-conditional VAE, and Function-on-Function regression approach](https://arxiv.org/abs/2606.08586) -- arXiv, 2026-06-07: Constructs a topological anomaly score for S&P 500 stocks and tests its predictive content for intraday return curves.
- [Trade Execution Flow as the Underlying Source of Market Dynamics](https://arxiv.org/abs/2511.01471) -- arXiv, 2025-11-03: Proposes that trade execution flow is the fundamental driver of market dynamics and develops a framework to calculate it from data.
- [Explainable Deep Learning for Price-Trade Dynamics: From Black-Box Forecasts to Effective Parametric Models](https://arxiv.org/abs/2609.06085) -- arXiv, 2026-09-05: Uses deep learning to discover interpretable parametric models for high-frequency price-trade dynamics.
- [Large-Scale Asset Selection via Metric Dependence with Enriched High Frequency Information](https://arxiv.org/abs/2605.02326) -- arXiv, 2026-05-04: A metric dependence screening method for asset selection using high-frequency information as object-valued data.
- [Warp speed price moves: Jumps after earnings announcements](https://arxiv.org/abs/2601.08962) -- arXiv, 2026-01-13: Shows earnings announcements almost always induce jumps in stock prices and raise co-jump probability in non-announcing firms.
- [Optimal Signal Extraction from Order Flow: A Matched Filter Perspective on Normalization and Market Microstructure](https://arxiv.org/abs/2512.18648) -- arXiv, 2025-12-21: Establishes a matched filter principle for order flow normalization, showing market cap normalization is optimal for institutional investors and trading value for VWAP/TWAP algorithms. -- reported: up to 1.99x higher signal correlation
- [Hidden Order in Trades Predicts the Size of Price Moves](https://arxiv.org/abs/2512.15720) -- arXiv, 2025-12-02: Shows that real-time order-flow entropy predicts the magnitude of intraday price moves for SPY, without directional information. -- reported: 38.5 million SPY trades over 36 days; entropy below 5th percentile increases subsequent 5-min absolute returns by a factor
- [Forecasting Liquidity Withdraw with Machine Learning Models](https://arxiv.org/abs/2509.22985) -- arXiv, 2025-09-26: Forecasts individual-stock liquidity withdrawal using machine learning on Nasdaq order book data.
- [A Framework for Predictive Directional Trading Based on Volatility and Causal Inference](https://arxiv.org/abs/2507.09347) -- arXiv, 2025-07-12: Proposes a framework combining Gaussian Mixture Model clustering and causal inference to identify predictive lead-lag relationships among nine stocks.
- [Stochastic Price Dynamics in Response to Order Flow Imbalance: Evidence from CSI 300 Index Futures](https://arxiv.org/abs/2505.17388) -- arXiv, 2025-05-23: Models price dynamics in response to order flow imbalance as an Ornstein-Uhlenbeck process with memory, applied to CSI 300 Index Futures.
- [Trading Under Uncertainty: A Distribution-Based Strategy for Futures Markets Using FutureQuant Transformer](https://arxiv.org/abs/2505.05595) -- arXiv, 2025-05-08: Introduces FutureQuant Transformer, a model that forecasts price ranges and volatility for futures trading using attention mechanisms on limit order book data.

### intraday_hf.stock_intraday -- Stocks-in-play opening-range breakout, news momentum, auctions, VWAP deviation, lead-lag

75 relevant item(s); by evidence tier: live_record=1, author_backtest=40, claim_only=10, theory=18, tool_or_data=6

- [Interview with Scott Andrews](http://bettersystemtrader.com/018-scott-andrews/) -- Better System Trader, 2015-08-03: Interview with a trader who has found success trading the opening gap.
- [ViperQ: Order Flow Pattern Recognition via Auction Market Theory for Reinforcement Learning Trading](https://arxiv.org/abs/2609.13825) -- arXiv, 2026-09-12: A reinforcement learning trading system using Auction Market Theory primitives for order flow pattern recognition.
- [Overreaction as an indicator for momentum in algorithmic trading: A Case of AAPL stocks](https://arxiv.org/abs/2602.18912) -- arXiv, 2026-02-21: Uses Twitter sentiment and machine learning to predict short-term overreactions in AAPL as momentum signals.
- [Optimal Signal Extraction from Order Flow: A Matched Filter Perspective on Normalization and Market Microstructure](https://arxiv.org/abs/2512.18648) -- arXiv, 2025-12-21: Establishes a matched filter principle for order flow normalization, showing market cap normalization is optimal for institutional investors and trading value for VWAP/TWAP algorithms. -- reported: up to 1.99x higher signal correlation
- [Mamba Outpaces Reformer in Stock Prediction with Sentiments from Top Ten LLMs](https://arxiv.org/abs/2510.01203) -- arXiv, 2025-09-14: Proposes a framework for minute-level stock prediction using sentiment scores from ten LLMs combined with intraday price data for AAPL.
- [Lunch Effect in the U.S. Stock Market Indices](https://web.archive.org/web/20240914035943/https://quantpedia.com/lunch-effect-in-the-u-s-stock-market-indices/?a=6080) -- Quantpedia, 2024-08-26: Describes a lunchtime effect in US stock market indices, a pattern of intraday price behavior.
- [Investigation of Lead-Lag Effect in Easily-Mistyped Tickers](https://web.archive.org/web/20240812034605/https://quantpedia.com/oh-my-i-bought-a-wrong-stock-investigation-of-lead-lag-effect-in-easily-mistyped-tickers/?a=6080) -- Quantpedia, 2024-06-23: Investigates the lead-lag effect between prominent stocks and smaller, less-known stocks with similar ticker symbols, such as TSLA and TLSA.
- [Predicting Stock Price Movement as an Image Classification Problem](https://arxiv.org/abs/2303.01111) -- arXiv, 2023-03-02: Treats intraday stock price movement as an image classification problem, using a CNN to predict close from first-hour trading.
- [Price impact in equity auctions: zero, then linear](https://arxiv.org/abs/2301.05677) -- arXiv, 2023-01-13: Studies price impact in equity auctions on the Paris stock exchange, relevant to intraday trading but not US markets.
- [Hierarchical Deep Reinforcement Learning for VWAP Strategy Optimization](https://arxiv.org/abs/2212.14670) -- arXiv, 2022-12-11: Proposes a hierarchical deep reinforcement learning architecture for optimizing VWAP execution strategies.
- [Stock Trading Optimization through Model-based Reinforcement Learning with Resistance Support Relative Strength](https://arxiv.org/abs/2205.15056) -- arXiv, 2022-05-30: A model-based reinforcement learning approach for stock trading that uses resistance and support levels as regularization.
- [Matrix profile: Using Weakly Labeled Time Series to Predict Outcomes](https://web.archive.org/web/20210906053530/http://dekalogblog.blogspot.com/2021/09/back-in-may-of-this-year-i-posted-about.html) -- Dekalog Blog, 2021-09-06: Uses matrix profile to cluster initial balance of Market Profile charts for intraday prediction.

### intraday_hf.true_hft -- Market making, latency arbitrage, order-book imbalance

573 relevant item(s); by evidence tier: forward_test=1, independent_replication=1, author_backtest=149, claim_only=6, theory=389, tool_or_data=27

- [Universal features of price formation in financial markets: perspectives from Deep Learning](https://arxiv.org/abs/1803.06917) -- arXiv, 2018-03-19: Uses deep learning on high-frequency order book data for US equities to show a universal price formation mechanism and tests out-of-sample predictions of price move direction.
- [Testing replication for an agent-based model of market fragmentation and latency arbitrage](https://arxiv.org/abs/2604.20067) -- arXiv, 2026-04-22: An independent replication attempt of a latency arbitrage model in fragmented markets, highlighting missing details and proposing bootstrap confidence intervals.
- [Public Trader Identity: Adverse Selection and Return Predictability](https://arxiv.org/abs/2608.04373) -- arXiv, 2026-08-05: Uses decentralized exchange wallet identities to show persistent informativeness and return predictability from aggressive orders.
- [Trade Execution Flow as the Underlying Source of Market Dynamics](https://arxiv.org/abs/2511.01471) -- arXiv, 2025-11-03: Proposes that trade execution flow is the fundamental driver of market dynamics and develops a framework to calculate it from data.
- [HLOB -- Information Persistence and Structure in Limit Order Books](https://arxiv.org/abs/2405.18938) -- arXiv, 2024-05-29: A deep learning model for limit order book mid-price change forecasting, tested against state-of-the-art models.
- [Market Dynamics: On Directional Information Derived From (Time, Execution Price, Shares Traded) Transaction Sequences](https://arxiv.org/abs/1903.11530) -- arXiv, 2019-03-27: A method to extract directional market information from transaction sequences based on execution flow dynamics.
- [Deep Learning of Robust Market Making under Regime-Switching Order Flow](https://arxiv.org/abs/2609.11614) -- arXiv, 2026-09-10: A deep reinforcement-learning market-making strategy that handles regime-switching order flow.
- [Velocity- and Regime-Aware Detection of Intraday Options Market Manipulation, with Explainable Attribution](https://arxiv.org/abs/2608.05373) -- arXiv, 2026-08-05: A paper on detecting intraday options market manipulation using velocity and regime-aware signals.
- [Data-Driven Measures of High-Frequency Trading](https://arxiv.org/abs/2608.00858) -- arXiv, 2026-08-01: The paper introduces data-driven measures of high-frequency trading that distinguish liquidity-supplying and liquidity-demanding strategies, applied to U.S. stocks from 2010-2023.
- [Can Reinforcement Learning Efficiently Discover Price Manipulation?](https://arxiv.org/abs/2607.06121) -- arXiv, 2026-07-07: Tests whether reinforcement learning can discover price manipulation strategies in an Almgren-Chriss market.
- [Order Splitting and Liquidity Replenishment Are Jointly Necessary for the Square-Root Law of Market Impact:](https://arxiv.org/abs/2607.04280) -- arXiv, 2026-07-05: Tests three quantitative predictions for the square-root law of market impact using a limit-order-book model. -- reported: Tokyo Stock Exchange benchmark delta=0.489
- [The Inference-Compute Frontier and a Latency-Efficient Architecture for Limit Order Book Prediction](https://arxiv.org/abs/2606.25986) -- arXiv, 2026-06-24: Studies scaling-law frontiers in limit order book prediction using the FI-2010 dataset and various models. -- reported: R^2=0.941 on extrapolated frontier

### macro_cross_asset.defensive_rotation -- Cross-asset defensive rotation and macro state

588 relevant item(s); by evidence tier: author_backtest=249, claim_only=100, theory=237, tool_or_data=2

- [Risk & returns around FOMC press conferences: a novel perspective from computer vision](https://arxiv.org/abs/2012.06573) -- arXiv, 2020-12-11: A computer vision measure of FOMC press conference discussion complexity is associated with higher equity returns and lower realized volatility.
- [Asymmetric Network Connectedness of Fears](https://arxiv.org/abs/1810.12022) -- arXiv, 2018-10-29: Introduces forward-looking network connectedness measures from option prices of US banks to predict macroeconomic conditions and systemic risk.
- [Emergence of frustration signals systemic risk](https://arxiv.org/abs/1807.02923) -- arXiv, 2018-07-09: Shows that systemic risk in NYSE can be detected via frustration in functional networks from 1926-2016.
- [CAST: A Cross-Asset State-Space Trading System for Drawdown Control in Stock Markets](https://arxiv.org/abs/2609.14205) -- arXiv, 2026-09-13: A cross-asset state-space trading system using Kalman filters for drawdown control in stock markets.
- [The Reconfiguration Premium: Co-movement Structure as an Unspanned Dimension of the Variance Risk Premium](https://arxiv.org/abs/2608.20020) -- arXiv, 2026-08-20: A study showing that the rate of change in S&P 500 correlation structure is priced and relates to the variance risk premium.
- [The Triadic Stress Index in Financial Markets](https://arxiv.org/abs/2608.10788) -- arXiv, 2026-08-11: A network-based stress index applied to financial asset correlation networks, tested on five markets including equities.
- [Estimating the Stochastic Discount Factor from Option Prices and Predicting the Equity Premium](https://arxiv.org/abs/2607.08500) -- arXiv, 2026-07-09: Estimates a stochastic discount factor from S&P 500 options to predict the equity premium.
- [Continuous Cash-Overlay Filters for a Static Growth--Defensive Risk Sleeve: Slow-Tail Compensation, V-Shape Crash Brakes, Walk-Forward Validation, and Max-Cash Combination](https://arxiv.org/abs/2606.09025) -- arXiv, 2026-06-08: Develops continuous cash-overlay filters for a static growth-defensive ETF sleeve, targeting slow-tail compensation and V-shape crash brakes with walk-forward validation.
- [Geometric Observables for Financial Regime Detection](https://arxiv.org/abs/2605.17117) -- arXiv, 2026-05-16: Extracts geometric observables from equity-index returns and evaluates them as regime-shift detectors against classical baselines. -- reported: median Cohen's d = 0.72, 67% fewer false alarms
- [Multiplicative Contractions, Additive Recoveries: Functional-Form Restrictions on Risk Exposure Dynamics](https://arxiv.org/abs/2604.23315) -- arXiv, 2026-04-25: Tests functional-form restrictions on risk-exposure dynamics using FINRA margin debt data, relevant to macro regime analysis.
- [Interpretable Systematic Risk around the Clock](https://arxiv.org/abs/2604.13458) -- arXiv, 2026-04-15: Decomposes systematic jump risk using high-frequency data and news narratives, constructing a factor with significant risk premia.
- [Skewness Dispersion and Stock Market Returns](https://arxiv.org/abs/2604.07870) -- arXiv, 2026-04-09: Cross-sectional dispersion in firm-level realized skewness negatively predicts future stock market returns, with gains concentrated in monetary policy announcement months. -- reported: Economic gains in portfolio allocation, robust in-sample and out-of-sample

### model.automated_research -- LLM-driven factor and model search loops

199 relevant item(s); by evidence tier: forward_test=1, author_backtest=37, claim_only=38, theory=70, tool_or_data=53

- [Coding live forward tests](https://web.archive.org/web/20241008104636/https://www.quantitativo.com/p/coding-live-forward-tests) -- Quantitativo, 2024-09-02: Discusses the process of coding live forward tests for trading strategies, emphasizing iterative testing.
- [Beyond Prompting: An Autonomous Framework for Systematic Factor Investing via Agentic AI](https://arxiv.org/abs/2603.14288) -- arXiv, 2026-03-15: Develops an autonomous agentic AI framework for systematic factor investing in US equities, with out-of-sample validation. -- reported: Annualized Sharpe ratio (value not fully stated)
- [FactorMiner: A Self-Evolving Agent with Skills and Experience Memory for Financial Alpha Discovery](https://arxiv.org/abs/2602.14670) -- arXiv, 2026-02-16: A self-evolving agent framework for formulaic alpha factor mining, combining modular skills and experience memory to discover novel signals.
- [QuantaAlpha: An Evolutionary Framework for LLM-Driven Alpha Mining](https://arxiv.org/abs/2602.07085) -- arXiv, 2026-02-06: Evolutionary framework for LLM-driven alpha mining that improves factors via trajectory-level mutation and crossover.
- [Alpha-R1: Alpha Screening with LLM Reasoning via Reinforcement Learning](https://arxiv.org/abs/2512.23515) -- arXiv, 2025-12-29: Uses LLM reasoning via reinforcement learning to screen alpha factors, addressing signal decay and regime shifts.
- [AlphaSAGE: Structure-Aware Alpha Mining via GFlowNets for Robust Exploration](https://arxiv.org/abs/2509.25055) -- arXiv, 2025-09-29: Presents AlphaSAGE, a GFlowNet-based method for automated alpha mining that addresses reward sparsity and structural representation issues.
- [EFS: Evolutionary Factor Searching for Sparse Portfolio Optimization Using Large Language Models](https://arxiv.org/abs/2507.17211) -- arXiv, 2025-07-23: Uses LLMs to evolve alpha factors for sparse portfolio optimization, framing asset selection as a ranking task.
- [To Trade or Not to Trade: An Agentic Approach to Estimating Market Risk Improves Trading Decisions](https://arxiv.org/abs/2507.08584) -- arXiv, 2025-07-11: Develops an agentic system using LLMs to iteratively discover stochastic differential equations for financial time series, generating risk metrics for daily trading decisions.
- [AlphaRJM: Reward-Jump Memory for Stochastic Return-Guided Alpha Discovery](https://arxiv.org/abs/2609.08581) -- arXiv, 2026-09-08: A method for formulaic alpha discovery using reward-jump memory to handle delayed feedback.
- [AlphaCrafter: A Full-Stack Multi-Agent Framework for Cross-Sectional Quantitative Trading](https://arxiv.org/abs/2605.05580) -- arXiv, 2026-05-07: Proposes a multi-agent framework for cross-sectional quantitative trading integrating factor discovery, regime adaptation, and execution.
- [Performance-Driven Causal Signal Engineering for Financial Markets under Non-Stationarity](https://arxiv.org/abs/2603.13638) -- arXiv, 2026-03-13: Introduces a causal signal engineering framework with walk-forward adaptation for non-stationary financial time series.
- [Alpha Discovery via Grammar-Guided Learning and Search](https://arxiv.org/abs/2601.22119) -- arXiv, 2026-01-29: Presents AlphaCFG, a grammar-guided framework for automatically discovering formulaic alpha factors that are syntactically valid, interpretable, and efficient.

### model.deep_and_foundation -- Deep cross-sectional and sequence models, time-series foundation models, tabular foundation models

1782 relevant item(s); by evidence tier: live_record=1, forward_test=3, independent_replication=2, author_backtest=833, claim_only=62, theory=792, tool_or_data=89

- [Increase Alpha: Performance and Risk of an AI-Driven Trading Framework](https://arxiv.org/abs/2509.16707) -- arXiv, 2025-09-20: Describes a deep-learning framework mapping over 800 U.S. equities into daily directional signals for production use.
- [Autonomous Market Intelligence: Agentic AI Nowcasting Predicts Stock Returns](https://arxiv.org/abs/2601.11958) -- arXiv, 2026-01-17: A paper deploying an agentic LLM to nowcast Russell 1000 stock returns daily, with out-of-sample predictions collected in real time.
- [PriceSeer: Evaluating Large Language Models in Real-Time Stock Prediction](https://arxiv.org/abs/2601.06088) -- arXiv, 2025-12-31: Introduces PriceSeer, a live benchmark for evaluating LLMs on real-time stock prediction for 110 US stocks.
- [Universal features of price formation in financial markets: perspectives from Deep Learning](https://arxiv.org/abs/1803.06917) -- arXiv, 2018-03-19: Uses deep learning on high-frequency order book data for US equities to show a universal price formation mechanism and tests out-of-sample predictions of price move direction.
- [Strategy Replication   Nonlinear SVMs can systematically identify stocks with high and low future returns](http://mintegration.eu/2015/09/03/strategy-replication-nonlinear-svms-can-systematically-identify-stocks-with-high-and-low-future-returns/) -- Mintegration, 2015-09-05: Replicates an academic paper using nonlinear support vector machines to identify stocks with high and low future returns.
- [Calibrating an adaptive Farmer-Joshi agent-based model for financial markets](https://arxiv.org/abs/2104.09863) -- arXiv, 2021-04-20: Replicates the calibration of the Farmer-Joshi agent-based model of financial markets using genetic algorithms and threshold accepting.
- [Square-Root Price Impact Is Necessary for Endogenous Manipulation Cycles in Learning-Agent Markets](https://arxiv.org/abs/2607.05141) -- arXiv, 2026-07-06: Shows that square-root price impact is necessary for endogenous manipulation cycles in a learning-agent market, with an agent discovering a predatory strategy. -- reported: total portfolio return +51% (best of 20 seeds; mean +37.7%) over 2000 trading days
- [Trading-R1: Financial Trading with LLM Reasoning via Reinforcement Learning](https://arxiv.org/abs/2509.11420) -- arXiv, 2025-09-14: Trading-R1 uses LLM reasoning with reinforcement learning for financial trading decisions.
- [Quantum Stochastic Walks for Portfolio Optimization: Theory and Implementation on Financial Networks](https://arxiv.org/abs/2507.03963) -- arXiv, 2025-07-05: Proposes a quantum stochastic walk optimizer for portfolio weights, showing improved out-of-sample Sharpe ratios on S&P 500 constituents. -- reported: out-of-sample Sharpe ratio up by 27%, 2016-2024
- [Controllable Financial Market Generation with Diffusion Guided Meta Agent](https://arxiv.org/abs/2408.12991) -- arXiv, 2024-08-23: Formulates controllable financial market generation using a diffusion-guided meta agent for order-flow modeling.
- [HLOB -- Information Persistence and Structure in Limit Order Books](https://arxiv.org/abs/2405.18938) -- arXiv, 2024-05-29: A deep learning model for limit order book mid-price change forecasting, tested against state-of-the-art models.
- [Nyström Attention Matches Full Attention for Cross-Sectional Stock Prediction](https://arxiv.org/abs/2609.08106) -- arXiv, 2026-09-08: A paper showing that Nyström attention can match full attention in cross-sectional stock prediction models.

### model.llm_text_features -- LLM-extracted features from news and filings

485 relevant item(s); by evidence tier: live_record=1, forward_test=3, author_backtest=272, claim_only=49, theory=64, tool_or_data=96

- [Signal or Noise in Multi-Agent LLM-based Stock Recommendations?](https://arxiv.org/abs/2604.17327) -- arXiv, 2026-04-19: Portfolio-level validation of a deployed multi-agent LLM equity system with live signals, testing if buy recommendations add value.
- [Autonomous Market Intelligence: Agentic AI Nowcasting Predicts Stock Returns](https://arxiv.org/abs/2601.11958) -- arXiv, 2026-01-17: A paper deploying an agentic LLM to nowcast Russell 1000 stock returns daily, with out-of-sample predictions collected in real time.
- [Generative AI-enhanced Sector-based Investment Portfolio Construction](https://arxiv.org/abs/2512.24526) -- arXiv, 2025-12-31: Uses LLMs to select and weight stocks within S&P 500 sectors, combined with portfolio optimization, tested out-of-sample.
- [PriceSeer: Evaluating Large Language Models in Real-Time Stock Prediction](https://arxiv.org/abs/2601.06088) -- arXiv, 2025-12-31: Introduces PriceSeer, a live benchmark for evaluating LLMs on real-time stock prediction for 110 US stocks.
- [Wasserstein-Barycentric Interaction Fields for Spatial Factor Models: Evidence from Language-Model Representations](https://arxiv.org/abs/2608.29669) -- arXiv, 2026-08-30: Constructs a spatial factor model from language-model article embeddings and shows it outperforms equal-weighted peer support in a 52-firm sample. -- reported: penalty ratio 3.46 (95% CI [2.89, 4.17]) for 2023-2026
- [Your AI, On a Dial: Controlling Investment Bias in LLMs with a Single Neuron](https://arxiv.org/abs/2608.22852) -- arXiv, 2026-08-24: A paper introducing an inference-time intervention on a single neuron in LLMs to continuously adjust the model's investment bias toward buying or selling.
- [DisclosureBeta: A Measurement-Channel Theory for Regime-Conditioned Betas from LLM-Read Risk Disclosures](https://arxiv.org/abs/2609.02900) -- arXiv, 2026-07-05: A theory for regime-conditioned betas from LLM-read risk disclosures, with a claimed empirical IPO accuracy improvement.
- [Supply Chain Propagation of Textual Signals: LLM Embeddings and Cross-Sectional Return Predictability](https://arxiv.org/abs/2606.29290) -- arXiv, 2026-06-28: Proposes augmenting LLM embeddings of 10-K MD&A sections with supply chain knowledge graph propagation, finding significant return predictability in cross-sectional regressions. -- reported: Newey-West t-statistic significant for net_pc_5
- [ChatGPT as a Time Capsule: The Limits of Price Discovery](https://arxiv.org/abs/2604.21433) -- arXiv, 2026-04-23: Frozen LLM checkpoints extract pre-cutoff text signals predicting future US equity returns.
- [Alpha-R1: Alpha Screening with LLM Reasoning via Reinforcement Learning](https://arxiv.org/abs/2512.23515) -- arXiv, 2025-12-29: Uses LLM reasoning via reinforcement learning to screen alpha factors, addressing signal decay and regime shifts.
- [Inferring Latent Market Forces: Evaluating LLM Detection of Gamma Exposure Patterns via Obfuscation Testing](https://arxiv.org/abs/2512.17923) -- arXiv, 2025-12-08: Introduces obfuscation testing to validate LLM detection of dealer hedging patterns like gamma exposure and 0DTE hedging. -- reported: 71.5% detection rate on 242 trading days
- [From News to Returns: A Granger-Causal Hypergraph Transformer on the Sphere](https://arxiv.org/abs/2510.04357) -- arXiv, 2025-10-05: A hypergraph transformer that models Granger-causal news and sentiment effects on asset returns.

### model.meta_labeling_and_filters -- Meta-labeling and trade filters on independent signals

156 relevant item(s); by evidence tier: live_record=1, forward_test=1, independent_replication=1, author_backtest=28, claim_only=24, theory=98, tool_or_data=3

- [Trading a Complete Starter System Live with  @AlpacaHQ](https://raposa.trade/trading-a-complete-starter-system-live-with-alpaca/) -- Raposa Trade, 2021-12-16: Trading a starter system live with Alpaca, based on a moving average crossover and volatility targeting.
- [Interpretable Hypothesis-Driven Trading:A Rigorous Walk-Forward Validation Framework for Market Microstructure Signals](https://arxiv.org/abs/2512.12924) -- arXiv, 2025-12-15: A walk-forward validation framework for market microstructure signals, combining interpretable hypotheses with reinforcement learning and out-of-sample testing.
- [A replication of the Practical Application section in ‘The Probability of Backtest Overfitting’](https://web.archive.org/web/20190918174005/https://opensourcequant.wordpress.com/2018/08/04/a-replication-of-the-practical-application-section-in-the-probability-of-backtest-overfitting-bailey-et-al/) -- Open Source Quant, 2018-08-06: Replicates a method for detecting backtest overfitting, relevant to strategy validation.
- [Harvesting the Volatility Risk Premium: A Learning-to-Rank Approach](https://arxiv.org/abs/2608.24786) -- arXiv, 2026-08-25: A learning-to-rank approach to harvesting the volatility risk premium from S&P 500 weekly options.
- [Calibration-Induced Degeneracy in LLM Financial Forecasting: An Audit-Trailed Case Study on Next-Day Market Risk](https://arxiv.org/abs/2608.20304) -- arXiv, 2026-08-20: A case study showing that LLM features can be zeroed out by calibration, while a simple headline count improves risk forecasts. -- reported: Headline count reduced SPY variance-forecast loss by 0.001720
- [When Alpha Disappears: A One-Switch Benchmark for Decision-Time Leakage in Financial Backtests](https://arxiv.org/abs/2605.23959) -- arXiv, 2026-05-12: A benchmark for diagnosing decision-time leakage in financial backtests by toggling evaluation conventions.
- [When Alpha Breaks: Two-Level Uncertainty for Safe Deployment of Cross-Sectional Stock Rankers](https://arxiv.org/abs/2603.13252) -- arXiv, 2026-02-24: Discusses two-level uncertainty for safe deployment of cross-sectional stock rankers, with a case study of a LightGBM ranker failing during regime shifts. -- reported: 20-day horizon, 2024 holdout breaks signal
- [A Test of Lookahead Bias in LLM Forecasts](https://arxiv.org/abs/2512.23847) -- arXiv, 2025-12-29: Develops a statistical test to detect lookahead bias in LLM forecasts, applied to news headlines predicting stock returns.
- [Discovery of a 13-Sharpe OOS Factor: Drift Regimes Unlock Hidden Cross-Sectional Predictability](https://arxiv.org/abs/2511.12490) -- arXiv, 2025-11-16: A cross-sectional equity factor combining value and short-term reversal signals only during stock-specific drift regimes, achieving high out-of-sample Sharpe ratios. -- reported: OOS Sharpe >13, annualized return 158.6%, vol 12.0%, max drawdown -11.9%, 20 years S&P 500
- [DNN-ForwardTesting: A New Trading Strategy Validation using Statistical Timeseries Analysis and Deep Neural Networks](https://arxiv.org/abs/2210.11532) -- arXiv, 2022-10-20: A new trading strategy validation method using deep neural networks for stock price forecasting and forward testing.
- [Trading via Selective Classification](https://arxiv.org/abs/2110.14914) -- arXiv, 2021-10-28: Proposes a selective classification framework for trading that allows a classifier to abstain from taking positions, improving accuracy-coverage trade-off.
- [Tail-risk protection: Machine Learning meets modern Econometrics](https://arxiv.org/abs/2010.03315) -- arXiv, 2020-10-07: A dynamic tail-risk protection strategy using machine learning classifiers to control Value-at-Risk while participating in bull markets.

### model.multi_source_ranking -- One per-stock feature table (price, events, alt data, text) with a ranking model

75 relevant item(s); by evidence tier: live_record=1, forward_test=1, author_backtest=41, claim_only=6, theory=19, tool_or_data=7

- [Signal or Noise in Multi-Agent LLM-based Stock Recommendations?](https://arxiv.org/abs/2604.17327) -- arXiv, 2026-04-19: Portfolio-level validation of a deployed multi-agent LLM equity system with live signals, testing if buy recommendations add value.
- [Generative AI-enhanced Sector-based Investment Portfolio Construction](https://arxiv.org/abs/2512.24526) -- arXiv, 2025-12-31: Uses LLMs to select and weight stocks within S&P 500 sectors, combined with portfolio optimization, tested out-of-sample.
- [Large Language Model-Driven Small-Capitalization Trading: Integrating Financial News Sentiment, Macroeconomic Indicators, and Technical Signals](https://arxiv.org/abs/2608.12283) -- arXiv, 2026-08-12: Proposes an uncertainty-aware LLM-driven trading pipeline for Russell 2000 stocks combining news sentiment, macro indicators, and technical signals.
- [Market Regime Council for Dynamic Credit Assignment in Multi-Agent LLM Decision Systems](https://arxiv.org/abs/2605.24490) -- arXiv, 2026-05-23: A multi-agent LLM portfolio management system using Shapley credits for agent weighting.
- [A Bipartite Graph Approach to U.S.-China Cross-Market Return Forecasting](https://arxiv.org/abs/2603.10559) -- arXiv, 2026-03-11: Uses a bipartite graph to capture cross-market predictive linkages between US and Chinese stocks for return forecasting.
- [Toward Expert Investment Teams:A Multi-Agent LLM System with Fine-Grained Trading Tasks](https://arxiv.org/abs/2602.23330) -- arXiv, 2026-02-26: Proposes a multi-agent LLM trading framework that decomposes investment analysis into fine-grained tasks for improved inference and transparency.
- [Stochastic Discount Factors with Cross-Asset Spillovers](https://arxiv.org/abs/2602.20856) -- arXiv, 2026-02-24: Develops a unified SDF framework linking firm-level signals and cross-asset spillovers, showing out-of-sample outperformance. -- reported: Out-of-sample outperformance vs benchmarks
- [Cross-Market Alpha: Testing Short-Term Trading Factors in the U.S. Market via Double-Selection LASSO](https://arxiv.org/abs/2601.06499) -- arXiv, 2026-01-10: Tests 191 short-term trading signals from Chinese A-shares on the S&P 500 using double-selection LASSO, finding alpha potential.
- [AlphaAgents: Large Language Model based Multi-Agents for Equity Portfolio Constructions](https://arxiv.org/abs/2508.11152) -- arXiv, 2025-08-15: A multi-agent LLM system for equity portfolio construction and stock selection.
- [Foreign Signal Radar](https://arxiv.org/abs/2504.07855) -- arXiv, 2025-04-10: Introduces a machine learning approach to detect value-relevant foreign information from 47 markets for U.S. stocks, showing out-of-sample predictability. -- reported: Out-of-sample return predictability for a subset of U.S. stocks
- [MarketSenseAI 2.0: Enhancing Stock Analysis through LLM Agents](https://arxiv.org/abs/2502.00415) -- arXiv, 2025-02-01: Presents MarketSenseAI 2.0, an LLM-agent framework processing news, prices, fundamentals, and macro for stock analysis.
- [TradingAgents: Multi-Agents LLM Financial Trading Framework](https://arxiv.org/abs/2412.20138) -- arXiv, 2024-12-28: A multi-agent LLM framework for stock trading that combines fundamental, sentiment, and technical analysis, with backtested results.

### options.options_income -- Option selling income

74 relevant item(s); by evidence tier: author_backtest=52, claim_only=8, theory=14

- [Harvesting the Volatility Risk Premium: A Learning-to-Rank Approach](https://arxiv.org/abs/2608.24786) -- arXiv, 2026-08-25: A learning-to-rank approach to harvesting the volatility risk premium from S&P 500 weekly options.
- [The Hidden Cost in Costless Put-Spread Collars: Rebalance Timing Luck](https://blog.thinknewfound.com/2023/01/the-hidden-cost-in-costless-put-spread-collars-rebalance-timing-luck/) -- Flirting with Models, 2023-01-25: Presents a paper on rebalance timing luck in costless put-spread collars.
- [Harvesting the Variance Risk Premium in Nuclear and Energy Equities: A Short-Put Portfolio Derisking Strategy](https://arxiv.org/abs/2609.01183) -- arXiv, 2026-09-01: A study of a cash-secured short-put strategy on nuclear and energy equities, harvesting the variance risk premium. -- reported: positive average option premia, high win rates, lower volatility than benchmark
- [Sizing the Risk: Kelly, VIX, and Hybrid Approaches in Put-Writing on Index Options](https://arxiv.org/abs/2508.16598) -- arXiv, 2025-08-09: Evaluates Kelly, VIX-based, and hybrid position sizing for systematic put-writing on S&P 500 index options.
- [High-Frequency Options Trading | With Portfolio Optimization](https://arxiv.org/abs/2408.08866) -- arXiv, 2024-08-16: Explores high-frequency options trading strategies on SPY with portfolio optimization, using five-minute interval data and option pricing models.
- [Construction and Hedging of Equity Index Options Portfolios](https://arxiv.org/abs/2407.13908) -- arXiv, 2024-07-18: Evaluates systematic S&P500 index option-writing strategies with hedging, using 1-minute data from 2018-2023.
- [Improving Hedged Equity With a Short-Dated Ladder](https://www.simplify.us/blog/improving-hedged-equity-short-dated-ladder) -- Simplify, 2023-04-03: Describes a costless collar strategy using short-dated options to hedge equity exposure.
- [A Python Investigation of a New Proposed Short Vol ETF – SVIX](https://web.archive.org/web/20220520072143/https://quantstrattrader.wordpress.com/2020/01/06/a-python-investigation-of-a-new-proposed-short-vol-etf-svix/) -- QuantStrat TradeR, 2020-01-07: Analyzes a proposed short volatility ETF (SVIX) that aims to provide short vol exposure without the blow-up risk of XIV.
- [Broken Wing Butterfly Price and Volatility – CDN](https://web.archive.org/web/20220703113914/http://dtr-trading.blogspot.com/2017/10/broken-wing-butterfly-price-and_44.html) -- DTR Trading, 2017-10-31: Analyzes implied volatility and option strike prices in broken wing butterfly strategies over time.
- [Model for Constructing an Options Portfolio with a Certain Payoff Function](https://arxiv.org/abs/1707.02087) -- arXiv, 2017-07-07: Proposes an integer linear programming model to construct an options portfolio with a target payoff function, demonstrated on Taiwan Futures Exchange options.
- [PutWrite vs. BuyWrite Index Differences](http://quantpedia.com/Blog/Details/putwrite-vs-buywrite-index-differences?a=6080) -- Quantpedia, 2017-01-23: Compares CBOE PutWrite and BuyWrite index performance and discusses the theoretical implications. -- reported: PutWrite outperformed BuyWrite by ~1.1% per year 1986-2015
- [SPX Straddle – 73 DTE – Results Summary](http://dtr-trading.blogspot.com/2015/10/spx-straddle-73-dte-results-summary.html) -- DTR Trading, 2015-10-30: Summarizes backtest results for selling SPX straddles at 73 days to expiration with eight loss approaches. -- reported: 4160 straddles backtested

### options.options_signals -- Implied-volatility skew, IV minus realized vol, unusual options volume

869 relevant item(s); by evidence tier: live_record=1, forward_test=1, author_backtest=177, claim_only=22, theory=656, tool_or_data=12

- [Small Trader Alpha: An Arbitrage Strategy in SPY Options](https://web.archive.org/web/20240221173918/https://returnsources.com/f/small-trader-alpha-an-arbitrage-strategy-in-spy-options) -- Return Sources, 2023-11-15: Describes an arbitrage trade in SPY options that was run for about a year.
- [What Does Deep Hedging Actually Learn? Delta Corrections, Regime Fragility, and Symbolic Distillation](https://arxiv.org/abs/2605.21696) -- arXiv, 2026-05-20: Studies deep hedging for S&P 500 options, finding systematic delta corrections and regime fragility.
- [Arbitrage-Aware Multi-Step Forecasting of Implied Volatility Surfaces: Modelling Surface Trajectories Using Latent Diffusion](https://arxiv.org/abs/2608.22478) -- arXiv, 2026-08-23: A paper proposing a conditional latent diffusion framework for generating joint 30-step trajectories of implied volatility surfaces and underlying returns, evaluated on SPX surfaces.
- [Inferring Latent Market Forces: Evaluating LLM Detection of Gamma Exposure Patterns via Obfuscation Testing](https://arxiv.org/abs/2512.17923) -- arXiv, 2025-12-08: Introduces obfuscation testing to validate LLM detection of dealer hedging patterns like gamma exposure and 0DTE hedging. -- reported: 71.5% detection rate on 242 trading days
- [Asymmetric Network Connectedness of Fears](https://arxiv.org/abs/1810.12022) -- arXiv, 2018-10-29: Introduces forward-looking network connectedness measures from option prices of US banks to predict macroeconomic conditions and systemic risk.
- [Derivatives pricing using signature payoffs](https://arxiv.org/abs/1809.09466) -- arXiv, 2018-09-25: Introduces signature payoffs for pricing path-dependent derivatives, demonstrating high accuracy on European, American, Asian, lookback options, and variance swaps. -- reported: high accuracy in pricing various options
- [DYSANOS Generative Dynamic Smooth Arbitrage-free Non-parametric Option Surfaces](https://arxiv.org/abs/2608.12587) -- arXiv, 2026-08-12: A generative model for arbitrage-free option surfaces, tested on S&P index options data from 2020 to 2025.
- [Velocity- and Regime-Aware Detection of Intraday Options Market Manipulation, with Explainable Attribution](https://arxiv.org/abs/2608.05373) -- arXiv, 2026-08-05: A paper on detecting intraday options market manipulation using velocity and regime-aware signals.
- [Inverse Learning of Latent Risk-Neutral Densities from Irregular Option Quotes](https://arxiv.org/abs/2607.27188) -- arXiv, 2026-07-29: A study on recovering latent risk-neutral densities from option quotes, comparing mixture models and learned operators. -- reported: DeepONet reduces 1% quantile and variance error by 39.0% and 34.6% relative to the mixture
- [One Other Option Pricing Scheme](https://arxiv.org/abs/2607.24680) -- arXiv, 2026-07-27: A new option pricing scheme parameterizing the risk-neutral distribution with localized control over the implied volatility curve, calibrated on S&P 500 options. -- reported: Accurate calibration across a quarter million curves from a two-year S&P 500 index option dataset
- [Estimating the Stochastic Discount Factor from Option Prices and Predicting the Equity Premium](https://arxiv.org/abs/2607.08500) -- arXiv, 2026-07-09: Estimates a stochastic discount factor from S&P 500 options to predict the equity premium.
- [The P behind Q: Empirical Evidence from Physical Drift in Put-Call Parity](https://arxiv.org/abs/2605.12250) -- arXiv, 2026-05-12: Analyzes the carry gap in put-call parity for SPX and RUT options, interpreting it as an implementation premium. -- reported: Improved in-sample and leave-one-year-out fit, especially in SPX

### out_of_scope.crypto_nonus -- Crypto, non-US and other markets we cannot trade

37 relevant item(s); by evidence tier: author_backtest=6, claim_only=5, theory=26

- [An Information Theory Approach to the Stock and Cryptocurrency Market: A Statistical Equilibrium Perspective](https://arxiv.org/abs/2310.04907) -- arXiv, 2023-10-07: Applies statistical equilibrium model to cross-sectional return distributions of cryptocurrencies and S&P 500 stocks.
- [Improving MF-DFA model with applications in precious metals market](https://arxiv.org/abs/2006.15214) -- arXiv, 2020-06-26: Proposes an improved multifractal detrended fluctuation analysis method to analyze price fluctuations in the precious metals market.
- [Short-horizon mean reversion in cryptocurrency markets: a matched cross-market measurement](https://arxiv.org/abs/2608.21888) -- arXiv, 2026-08-22: A study of 15-minute mean reversion in crypto markets, with a brief comparison to US equities. -- reported: 90% of 183 Binance pairs significant vs 2.7% of 187 US stocks/ETFs
- [Digital Asset ETFs: Not Crypto Enough?](https://web.archive.org/web/20210727054707/https://insights.factorresearch.com/research-digital-asset-etfs-not-crypto-enough/) -- Factor Research, 2021-07-27: Analyzes digital asset ETFs, finding they are not crypto exposure.
- [Financial Return Distributions: Past, Present, and COVID-19](https://arxiv.org/abs/2107.06659) -- arXiv, 2021-07-14: Analyzes return distributions of currencies, cryptocurrencies, and CFDs, modeling tails with power-law, stretched exponential, and q-Gaussian functions.
- [Equity index futures returns: lessons of 2000-2018](http://www.sr-sv.com/equity-index-futures-returns-lessons-of-2000-2018/) -- SR SV, 2018-08-19: Reviews returns of equity index futures across 25 international markets from 2000-2018. -- reported: average annualized return 6%, std dev ~20%
- [Less Efficient Markets = Higher Alpha?](https://web.archive.org/web/20211012054523/https://insights.factorresearch.com/research-less-efficient-markets-higher-alpha/) -- Factor Research, 2021-10-12: Discusses alpha generation in emerging markets, which are outside the US equity focus.
- [Bitcoin: An Asset Allocation Perspective](https://lightfinance.blog/bitcoin-asset-allocation/) -- Light Finance, 2021-04-02: Analyzes Bitcoin from an asset allocation perspective.
- [Investing Outside the U.S. – Purgatory for Pessimists](https://web.archive.org/web/20240105125743/https://www.factorinvestor.com/blog/investing-outside-the-us-purgatory-for-pessimists) -- Factor Investor, 2017-11-15: Discusses non-U.S. equity allocations and the TINA argument.
- [A Case Against Overweighting International Equity](https://web.archive.org/web/20220525191507/https://blog.thinknewfound.com/2017/11/case-overweighting-international-equity/) -- Flirting with Models, 2017-11-14: Argues against overweighting international equities in favor of U.S. equities.
- [The Art of Financial Illusion: How to Use Martingale Betting Systems to Fool People](https://web.archive.org/web/20240812034732/https://quantpedia.com/the-art-of-financial-illusion-how-to-use-martingale-betting-systems-to-fool-people/?a=6080) -- Quantpedia, 2024-06-26: Discusses martingale betting systems and how they can be used to create financial illusions, likely in the context of crypto and trading scams.
- [Modeling structure and credit risk of the economy: a multilayer bank-firm network approach](https://arxiv.org/abs/2603.09854) -- arXiv, 2026-03-10: Models credit risk propagation through a multilayer bank-firm network.

### portfolio.combination_and_risk -- Combining strategies, risk budgets, account-level drawdown

1731 relevant item(s); by evidence tier: live_record=9, forward_test=3, independent_replication=1, author_backtest=395, claim_only=152, theory=1126, tool_or_data=45

- [Evaluating Structured Strategy Backtests: Peer Benchmarks, Regime Timing, and Live Performance](https://arxiv.org/abs/2604.18821) -- arXiv, 2026-04-20: Evaluates the portability of pro-forma backtests to live performance for structured strategies, using data from 1,726 strategies.
- [Trading and investing performance: year eight](https://qoppac.blogspot.com/2022/04/trading-and-investing-performance-year.html) -- Investment Idiocy, 2022-04-15: An individual's eight-year track record of trading and investing performance, starting from a systematic futures fund background.
- [Clustering trading rule p&l](https://qoppac.blogspot.com/2023/05/clustering-trading-rule-p.html) -- Investment Idiocy, 2023-05-14: Author describes upgrading live production system and consolidating trading rules.
- [Trading and investing performance year nine – part 2: Futures trading](https://qoppac.blogspot.com/2023/05/trading-and-investing-performance-year.html) -- Investment Idiocy, 2023-05-07: Annual review of futures trading performance as part of a live portfolio.
- [Trading and investing performance: year nine, part one](https://qoppac.blogspot.com/2023/04/trading-and-investing-performance-year.html) -- Investment Idiocy, 2023-04-29: Reports the author's trading and investing performance for the UK tax year 2022-23, a live record.
- [Trading and investing performance – year seven](https://qoppac.blogspot.com/2021/04/trading-and-investing-performance-year.html) -- Investment Idiocy, 2021-04-14: Annual review of the author's investing and trading performance over seven years.
- [Tactical Asset Allocation in August](https://allocatesmartly.com/tactical-asset-allocation-in-august-2018/?aff=634) -- Allocate Smartly, 2018-09-03: Summary of recent performance of tactical asset allocation strategies net of transaction costs.
- [Trading performance – year four](https://web.archive.org/web/20220525183450/https://qoppac.blogspot.com/2018/04/trading-performance-year-four.html) -- Investment Idiocy, 2018-04-17: Provides an annual update on the author's personal investment and trading performance.
- [Interview with Kevin Davey](http://bettersystemtrader.com/005-kevin-davey/) -- Better System Trader, 2015-05-04: An interview with a trader who has developed strategies across many futures markets for over 25 years. -- reported: Top 2
- [Day 30: Summing up](https://web.archive.org/web/20250215070957/https://www.optionstocksmachines.com/post/2024-12-12-day-30-summing-up/) -- OSM, 2024-12-13: Summarizes an out-of-sample test of four strategies, with an adjusted strategy ranking top.
- [Day 29: Out of sample](https://web.archive.org/web/20250215070157/https://www.optionstocksmachines.com/post/2024-12-06-day-29-out-of-sample/) -- OSM, 2024-12-07: Reports out-of-sample results of a strategy, with an adjusted version performing better.
- [September update, paper trading with IB](http://www.regressionist.com/2020/09/25/september-update-paper-trading-with-ib/) -- Regressionist, 2020-09-27: A personal update on paper trading with Interactive Brokers after quitting a job.

### public_records.copy_verified_live -- Copy or learn from third-party-verified live strategies

5 relevant item(s); by evidence tier: live_record=4, author_backtest=1

- [AI in Asset Management and Rebellion Research](https://arxiv.org/abs/2206.14876) -- arXiv, 2022-06-29: Describes Rebellion Research's AI Global Equity strategy, claiming a live record of outperforming the S&P 500 for 14 years. -- reported: +6.8% gross for first three quarters of 2021; outperforming S&P 500 for 14 years
- [Interview with Michael Cook](http://bettersystemtrader.com/039-michael-cook/) -- Better System Trader, 2016-01-11: Interview with a World Cup Trading Championships winner discussing trading strategies.
- [Interview with Larry Williams](http://bettersystemtrader.com/020-larry-williams/) -- Better System Trader, 2015-08-18: Interview with Larry Williams, a trader with a documented live trading championship record. -- reported: Turned $10,000 into $1.1 million in 12 months (1987)
- [Rob Hanna Wins the 2024 NAAIM Founders Award](https://web.archive.org/web/20240622212209/https://quantifiableedges.com/rob-hanna-wins-the-2024-naaim-founders-award/) -- Quantifiable Edges, 2024-05-14: Announces that Rob Hanna won the NAAIM Founders Award for his active investment management work.
- [Factor Attribution of Jim Cramer’s Mad Money Charitable Trust](https://web.archive.org/web/20160611182603/http://quantpedia.com/Blog/Details/factor-attribution-of-jim-cramers-mad-money-charitable-trust-performance?a=6080) -- Quantpedia, 2016-06-04: Analyzes the historical performance of Jim Cramer's Charitable Trust portfolio from 2001 to 2016.

### relative_value.pairs_stat_arb -- Pairs, statistical arbitrage on residuals, ETF-versus-constituent spreads

191 relevant item(s); by evidence tier: independent_replication=1, author_backtest=84, claim_only=4, theory=96, tool_or_data=6

- [New related paper to #12 – Pairs Trading with Stocks](http://quantpedia.com/Blog/Details/1-new-related-paper-to-12-pairs-trading-with-stocks?a=6080) -- Quantpedia, 2015-05-06: Test of pairs trading strategy, investigating profitability after above-average volume days.
- [Neural networks can detect model-free static arbitrage strategies](https://arxiv.org/abs/2306.16422) -- arXiv, 2023-06-19: Neural networks detect model-free static arbitrage opportunities in markets with many securities, enabling near-immediate execution.
- [Gaussian Boson Sampling for Asset Clustering in Statistical Arbitrage Portfolios](https://arxiv.org/abs/2607.19279) -- arXiv, 2026-07-21: Benchmarks classical and quantum clustering algorithms on S&P 500 residual correlations for statistical arbitrage portfolios.
- [Hierarchical Graph Learning for Calendar Spread Strategies in Commodity Futures Markets](https://arxiv.org/abs/2606.25811) -- arXiv, 2026-06-24: Proposes a hierarchical graph learning approach for calendar spread strategies in commodity futures markets.
- [Cross-Stock Predictability via LLM-Augmented Semantic Networks](https://arxiv.org/abs/2604.19476) -- arXiv, 2026-04-21: Proposes a two-stage framework using LLMs to filter spurious edges in text-based financial networks for cross-stock mean-reversion signals.
- [Forecasting Equity Correlations with Hybrid Transformer Graph Neural Network](https://arxiv.org/abs/2601.04602) -- arXiv, 2026-01-08: Proposes a hybrid Transformer-GNN to forecast 10-day ahead stock correlations for S&P 500 constituents to improve basket trading clustering.
- [Attention Factors for Statistical Arbitrage](https://arxiv.org/abs/2510.11616) -- arXiv, 2025-10-13: Develops Attention Factors for statistical arbitrage using conditional latent factors and sequence models.
- [LLMs for Time Series: an Application for Single Stocks and Statistical Arbitrage](https://arxiv.org/abs/2412.09394) -- arXiv, 2024-12-12: Uses the Chronos LLM for time series prediction on US stocks to construct a long/short statistical arbitrage strategy.
- [Statistical Arbitrage in Rank Space](https://arxiv.org/abs/2410.06568) -- arXiv, 2024-10-09: Demonstrates statistical arbitrage in rank space (by capitalization) outperforms name space, with intraday rebalancing.
- [Statistical arbitrage in multi-pair trading strategy based on graph clustering algorithms in US equities market](https://arxiv.org/abs/2406.10695) -- arXiv, 2024-06-15: A statistical arbitrage strategy using graph clustering algorithms and machine learning for US equities.
- [Advanced Statistical Arbitrage with Reinforcement Learning](https://arxiv.org/abs/2403.12180) -- arXiv, 2024-03-18: Introduces a model-free reinforcement learning framework for statistical arbitrage on paired stocks, optimizing mean reversion time.
- [End-to-End Policy Learning of a Statistical Arbitrage Autoencoder Architecture](https://arxiv.org/abs/2402.08233) -- arXiv, 2024-02-13: This paper proposes an autoencoder-based statistical arbitrage strategy on US stock returns.

### reversal.end_of_day_and_gap -- End-of-day reversal and overnight gap fade

101 relevant item(s); by evidence tier: author_backtest=63, claim_only=27, theory=11

- [A Validated Volatility-Volume-Gap Classifier for Regime Identification in MNQ Intraday Data](https://arxiv.org/abs/2605.11423) -- arXiv, 2026-05-12: A classifier for MNQ futures day types based on pre-market conditions, finding directional morning drift and late-session reversal, but no profitable directional strategy.
- [Structural Limits of OHLCV-Based Intraday Signals in MNQ Futures: A Systematic Falsification Study](https://arxiv.org/abs/2605.04004) -- arXiv, 2026-05-05: A systematic falsification study of OHLCV-based intraday signals in MNQ futures under realistic execution constraints.
- [A Guide to Forecast Scalars](https://web.archive.org/web/20240221180954/https://returnsources.com/f/a-guide-to-forecast-scalars) -- Return Sources, 2023-11-29: Describes a guide to forecast scalars for a trading signal based on overnight versus intraday returns.
- [The Overnight Anomaly: Alive and Well](https://web.archive.org/web/20240221180301/https://returnsources.com/f/the-overnight-anomaly-alive-and-well) -- Return Sources, 2023-11-22: Examines the overnight anomaly, where overnight returns exceed intraday returns, and its persistence.
- [Are There Intraday and Overnight Seasonality Effects in China?](https://quantpedia.com/are-there-intraday-and-overnight-seasonality-effects-in-china/?a=6080) -- Quantpedia, 2022-08-29: Investigates intraday and overnight seasonality effects in Chinese markets, noting the focus on US equities but extending to China.
- [The Worst One-Day Shocks and Biggest Geopolitical Events of the Past Century](https://quantpedia.com/the-worst-one-day-shocks-and-the-biggest-geopolitical-events-of-the-past-century/?a=6080) -- Quantpedia, 2022-07-12: Analyzes the 50 worst one-day shocks and subsequent days across asset classes over a century.
- [New Site! Trailing Stops in Various AutoCorrelation and Volatility Regimes](https://web.archive.org/web/20210924075942/https://www.dwongresearch.com/posts/trailingstopsautocorrelatedvolatility/) -- Derek Wong, 2021-09-24: Examines trailing stops in various autocorrelation and volatility regimes using synthetic data.
- [Monday   s Strong Selling & New Lows Triggered This Historically Bullish Setup](https://web.archive.org/web/20210922172250/https://quantifiableedges.com/mondays-strong-selling-new-lows-triggered-a-historically-bullish-setup/) -- Quantifiable Edges, 2021-09-22: Describes a historically bullish setup after strong selling and new lows, with turnaround Tuesday bounce.
- [When DJI Rallies From 50-day Low to 50-day High Very Quickly](https://quantifiableedges.com/when-dji-rallies-from-50-day-low-to-50-day-high-very-quickly/) -- Quantifiable Edges, 2021-07-08: Examines historical instances when the Dow rallies from a 50-day low to a 50-day high very quickly.
- [Market Sentiment and an Overnight Anomaly](https://quantpedia.com/market-sentiment-and-an-overnight-anomaly/?a=6080) -- Quantpedia, 2021-04-21: Explores how market sentiment relates to an overnight anomaly in returns.
- [Evidence and Behaviour of Support and Resistance Levels in Financial Time Series](https://arxiv.org/abs/2101.07410) -- arXiv, 2021-01-19: Develops a heuristic to discover support and resistance levels in intraday price series that reverse trends significantly. -- reported: Statistically significant price reversals
- [What Comes After a Dead Cat Bounce?](https://web.archive.org/web/20201203064814/https://www.quantrocket.com/blog/dead-cat-bounce) -- Quant Rocket, 2020-12-03: Examines the dead cat bounce pattern after large one-day losses.

### reversal.etf_mean_reversion -- ETF short-term mean reversion rules

12 relevant item(s); by evidence tier: author_backtest=9, claim_only=2, theory=1

- [Push-response anomalies in high-frequency S&P 500 price series](https://arxiv.org/abs/2511.06177) -- arXiv, 2025-11-09: Analyzes high-frequency SPY price data to test for conditional nonrandomness in intraday price changes, finding structural shifts in push-response patterns.
- [Overnight Reversal Effects in the High-Yield Market](https://web.archive.org/web/20240916190114/https://quantpedia.com/overnight-reversal-effects-in-the-high-yield-market/?a=6080) -- Quantpedia, 2024-08-27: Examines overnight reversal effects in high-yield bond ETFs, which hold illiquid securities but trade liquidly.
- [Daylight is Bad for Gold Stocks (Apparently)](http://jayonthemarkets.com/2015/11/05/daylight-is-bad-for-gold-stocks-apparently/) -- Jay On The Markets, 2015-11-06: Investigates a daylight effect on gold mining ETF returns.
- [Using Internal Bar Strength as a Key Indicator for Trading Country ETFs](https://arxiv.org/abs/2306.12434) -- arXiv, 2023-06-14: Tests internal bar strength (IBS) as a mean-reversion signal for country ETFs over 10 years of historical data.
- [Video Digest: Mean Reversion and Bond ETF Returns](https://web.archive.org/web/20210119082447/https://blog.thinknewfound.com/2018/08/video-digest-mean-reversion-and-bond-etf-returns/) -- Flirting with Models, 2018-08-11: Video digest on mean reversion and bond ETF returns.
- [SPY Mean Reversion With John Ehlers Adaptive RSI](https://web.archive.org/web/20201029191525/https://flare9xblog.com/2018/08/07/spy-mean-reversion-with-john-ehlers-adaptive-rsi/) -- Flare 9x, 2018-08-09: Explores SPY mean reversion using John Ehlers' adaptive RSI indicator.
- [Mean Reversion and Bond ETF Returns](https://blog.thinknewfound.com/2018/08/mean-reversion-and-bond-etf-returns/) -- Flirting with Models, 2018-08-07: Argues that bond ETF returns exhibit mean reversion due to defined maturity and coupon rate.
- [A simple statistical edge in SPY](http://tradingwithpython.blogspot.com/2016/02/a-simple-statistical-edge-in-spy.html) -- Trading with Python, 2016-02-21: Describes a simple statistical edge in SPY, likely mean-reversion based.
- [Blast Buy & Hold with this simple Bollinger Band strategy](http://bettersystemtrader.com/bollinger-band-trading-strategy/) -- Better System Trader, 2015-04-27: A Bollinger Band strategy that aims to beat buy-and-hold.
- [Mean Reversion Volatility Strategy](http://miltonfmr.com/mean-reversion-volatility-strategy/) -- Milton FMR, 2016-12-25: Discusses a mean reversion strategy for volatility ETFs, noting they are inefficient long-term vehicles but can be traded profitably short-term.
- [Free Friday #14 and #14a](https://web.archive.org/web/20220808034547/http://www.buildalpha.com/free-friday-14-and-14a/) -- Build Alpha, 2017-03-31: A strategy that shorts the Gold Miners ETF (GDX).
- [Mean Reverting and Trending Properties of SPX and VIX](https://web.archive.org/web/20220525195148/http://blog.harbourfronts.com/2017/12/29/mean-reverting-trending-properties-spx-vix/) -- Relative Value Arbitrage, 2017-12-30: Investigating the mean reverting and trending properties of SPX and VIX.

### reversal.stock_short_term_reversal -- Individual-stock 1-5 day reversal, industry-adjusted, by liquidity tier

126 relevant item(s); by evidence tier: forward_test=1, author_backtest=70, claim_only=31, theory=23, tool_or_data=1

- [Two Swing Trade Systems (Part 2)](http://throwinggoodmoney.com/2017/02/two-swing-trade-systems-part-2/) -- Throwing Good Money, 2017-02-04: Two swing-trade systems that work well in out-of-sample data, with overlapping signals.
- [The Bounce Has No Direction: Sign, Magnitude, and the Microstructure of Equity Return Predictability](https://arxiv.org/abs/2606.29591) -- arXiv, 2026-06-28: Decomposes SPY's negative lag-1 autocorrelation into sign and magnitude channels, with implications for reversal trading. -- reported: SPY lag-1 autocorrelation -0.081, z=-7.4
- [Trends and Reversion in Financial Markets on Time Scales from Minutes to Decades](https://arxiv.org/abs/2501.16772) -- arXiv, 2025-01-28: Empirical analysis of trend and reversion across time scales from minutes to decades, finding trending regimes from hours to years and reversion on shorter/longer scales.
- [StockGPT: A GenAI Model for Stock Prediction and Trading](https://arxiv.org/abs/2404.05101) -- arXiv, 2024-04-07: StockGPT is an autoregressive transformer model trained on 70 million daily US stock returns that learns predictive patterns and forms long-short portfolios spanning momentum and reversals. -- reported: Strong performance on held-out test sample 2001-2023, daily and monthly rebalanced long-short portfolios
- [NYSE Price Correlations Are Abitrageable Over Hours and Predictable Over Years](https://arxiv.org/abs/2305.08241) -- arXiv, 2023-05-14: Studies one-minute price discrepancies from martingale for NYSE stocks, finding slight mean reversion and backtests an arbitrage strategy. -- reported: Hurst exponent 0.465, mean-reverting; backtest on actual data
- [Joint News, Attention Spillover,and Stock Returns](https://arxiv.org/abs/1703.02715) -- arXiv, 2017-03-08: Shows that joint news coverage causes attention spillovers, leading to inflated valuations and subsequent reversals, and predicts market returns out-of-sample.
- [Fractal Investment Strategy](http://blog.johnorford.com/2015/06/21/fractal-investment-strategy/) -- John Orford, 2015-06-22: Proposes using the Hurst exponent to predict future returns as a fractal investment strategy, building on a mean reversion and momentum idea.
- [Visibility graphs can make money in financial markets](https://arxiv.org/abs/2605.01300) -- arXiv, 2026-05-02: Introduces a Visibility Graphs Relative Strength Index (VGRSI) and tests it in an automated trading strategy on DJI30, EUR/USD, and XAU/USD.
- [Entropy-Assisted Quality Pattern Identification in Finance](https://arxiv.org/abs/2503.06251) -- arXiv, 2025-03-08: An entropy-assisted framework for identifying short-term price patterns in financial time series for algorithmic trading.
- [Measuring Performance Chasing](https://web.archive.org/web/20240605085915/https://insights.finominal.com/research-measuring-performance-chasing/) -- Finominal, 2024-06-05: Measures performance chasing via extreme excess returns, showing abnormal negative returns lead to subsequent outperformance and vice versa.
- [How Volatility and Turnover Affect Return Reversals](https://web.archive.org/web/20240622212209/https://alphaarchitect.com/2024/05/how-volatility-and-turnover-affect-return-reversals/) -- Alpha Architect, 2024-05-14: Analyzes how aggregate market liquidity affects the time-series performance of reversal strategies.
- [Efficiency Ratio and Mean Reversion](https://alvarezquanttrading.com/blog/efficiency-ratio-and-mean-reversion/) -- Alvarez Quant Trading, 2023-06-08: Discusses using Kaufman's Efficiency Ratio to decide between trend-following and mean-reversion strategies.

### trend_momentum.etf_letf_rotation -- ETF and leveraged-ETF momentum rotation

365 relevant item(s); by evidence tier: live_record=19, forward_test=2, independent_replication=4, author_backtest=199, claim_only=106, theory=33, tool_or_data=2

- [Tactical Asset Allocation in November](https://web.archive.org/web/20200918193426/https://allocatesmartly.com/tactical-asset-allocation-in-november-2019/?aff=634) -- Allocate Smartly, 2019-12-07: Summarizes recent performance of various tactical asset allocation strategies net of transaction costs.
- [State of Trend Following in April](https://web.archive.org/web/20190818125518/http://www.automated-trading-system.com/state-of-trend-following-in-april-6/) -- Au Tra Sy, 2019-05-11: Reports monthly performance of a trend-following index. -- reported: April return: 2.89%, YTD return: 0%
- [Tactical Asset Allocation in March](https://web.archive.org/web/20220525203745/https://allocatesmartly.com/tactical-asset-allocation-in-march-2019/?aff=634) -- Allocate Smartly, 2019-04-02: Summarizes recent performance of tactical asset allocation strategies net of costs. -- reported: net of transaction costs
- [Tactical Asset Allocation in October](https://allocatesmartly.com/tactical-asset-allocation-in-october-2018/?aff=634) -- Allocate Smartly, 2018-11-02: Summarizes recent performance of tactical asset allocation strategies. -- reported: Net of transaction costs
- [State of Trend Following in August](http://www.automated-trading-system.com/state-of-trend-following-in-august-4/) -- Au Tra Sy, 2018-09-18: Reports on the state of trend following with strong August returns and positive year-to-date figures. -- reported: Strong return for August, YTD back in black
- [Tactical Asset Allocation in July](https://allocatesmartly.com/tactical-asset-allocation-in-july-2018/?aff=634) -- Allocate Smartly, 2018-08-04: Summarizes recent performance of tactical asset allocation strategies, net of costs.
- [Wisdom State of Trend Following in April](https://web.archive.org/web/20220703124253/http://www.wisdomtrading.com/wisdom-state-trend-following-april/) -- Wisdom Trading, 2017-05-06: Reports the April 2017 performance of a trend-following index. -- reported: April 2017: -1.35%, YTD: -11.65%
- [Dual Momentum August Update](http://www.scottsinvestments.com/2015/08/10/dual-momentum-august-update/) -- Scott’s Investments, 2015-08-12: A monthly update of a dual ETF momentum strategy.
- [Wisdom State of Trend Following – July 2015](http://www.wisdomtrading.com/state-trend-following-july-rebound/) -- Wisdom Trading, 2015-08-11: A monthly report on the performance of a trend following strategy.
- [State of Trend Following in May](https://web.archive.org/web/20220808034931/http://www.automated-trading-system.com/state-of-trend-following-in-may-7/) -- Au Tra Sy, 2019-06-11: Reports on the May performance of a trend following index, noting strong results and positive year-to-date performance. -- reported: May strong result, YTD positive
- [State of Trend Following in October](http://www.automated-trading-system.com/state-of-trend-following-in-october-5/) -- Au Tra Sy, 2018-11-11: Reports monthly performance of a trend-following strategy, noting a negative October. -- reported: October return negative, YTD just in red
- [State of Trend Following in June](https://web.archive.org/web/20220525190634/http://www.automated-trading-system.com/state-of-trend-following-in-june-4/) -- Au Tra Sy, 2018-07-10: Reports the monthly performance of trend following strategies, noting a slight uptick but negative YTD. -- reported: YTD negative at half-time

### trend_momentum.stock_momentum -- Individual-stock momentum (cross-sectional, residual, industry-relative)

289 relevant item(s); by evidence tier: author_backtest=178, claim_only=63, theory=47, tool_or_data=1

- [Trends, Volatility, Correlations, and Critical Phenomena in Financial Markets](https://arxiv.org/abs/2606.20145) -- arXiv, 2026-06-18: Forecasts future volatilities and correlations based on current market trends, showing that strong trends increase volatility and correlations, especially in down-trends.
- [ChatGPT in Systematic Investing -- Enhancing Risk-Adjusted Returns with LLMs](https://arxiv.org/abs/2510.26228) -- arXiv, 2025-10-30: Uses ChatGPT to score firm-specific news for cross-sectional momentum strategies, enhancing risk-adjusted returns. -- reported: Outperforms standard long-only momentum
- [Supervised Similarity for Firm Linkages](https://arxiv.org/abs/2506.19856) -- arXiv, 2025-06-09: Introduces Characteristic Vector Linkages for firm similarity and shows momentum spillover strategies using Euclidean and quantum cognition machine learning similarity, with QCML outperforming Euclidean.
- [Trends and Reversion in Financial Markets on Time Scales from Minutes to Decades](https://arxiv.org/abs/2501.16772) -- arXiv, 2025-01-28: Empirical analysis of trend and reversion across time scales from minutes to decades, finding trending regimes from hours to years and reversion on shorter/longer scales.
- [Enhancement of price trend trading strategies via image-induced importance weights](https://arxiv.org/abs/2408.08483) -- arXiv, 2024-08-16: Uses deep learning image analysis to identify price chart patterns and weight moving average trend signals, tested on Chinese stocks.
- [DeepUnifiedMom: Unified Time-series Momentum Portfolio Construction via Multi-Task Learning with Multi-Gate Mixture of Experts](https://arxiv.org/abs/2406.08742) -- arXiv, 2024-06-13: Introduces a deep learning framework for unified momentum portfolios using multi-task learning and mixture of experts. -- reported: Outperforms traditional momentum strategies in backtests across asset classes
- [StockGPT: A GenAI Model for Stock Prediction and Trading](https://arxiv.org/abs/2404.05101) -- arXiv, 2024-04-07: StockGPT is an autoregressive transformer model trained on 70 million daily US stock returns that learns predictive patterns and forms long-short portfolios spanning momentum and reversals. -- reported: Strong performance on held-out test sample 2001-2023, daily and monthly rebalanced long-short portfolios
- [Few-Shot Learning Patterns in Financial Time-Series for Trend-Following Strategies](https://arxiv.org/abs/2310.10500) -- arXiv, 2023-10-16: Proposes a few-shot learning trend-following model (X-Trend) that adapts quickly to new market regimes.
- [Learning to Learn Financial Networks for Optimising Momentum Strategies](https://arxiv.org/abs/2308.12212) -- arXiv, 2023-08-23: Proposes an end-to-end machine learning framework that jointly learns financial networks and optimizes momentum strategies.
- [Network Momentum across Asset Classes](https://arxiv.org/abs/2308.11294) -- arXiv, 2023-08-22: Investigates network momentum as a trading signal derived from momentum spillover across asset classes.
- [Momentum – a separate factor or does it subsume stock risk?](https://alphaarchitect.com/2022/09/is-momentum-a-separate-factor/) -- Alpha Architect, 2022-09-15: Presents a novel view on the nature and source of momentum as a separate factor.
- [Transfer Ranking in Finance: Applications to Cross-Sectional Momentum with Data Scarcity](https://arxiv.org/abs/2208.09968) -- arXiv, 2022-08-21: Proposes Fused Encoder Networks for transfer ranking in cross-sectional momentum with data scarcity.

### volatility.vol_targeting_and_regime -- Volatility targeting, VIX regime, bear gates

384 relevant item(s); by evidence tier: author_backtest=158, claim_only=52, theory=167, tool_or_data=7

- [Rough Volatility Across Assets](https://arxiv.org/abs/2608.16749) -- arXiv, 2026-08-17: Measures volatility roughness across US equities and other assets, with implications for volatility modeling and regime detection.
- [Regime-Gated Residual Mixture-of-Experts for Cross-Sectional Volatility Forecasting](https://arxiv.org/abs/2608.12251) -- arXiv, 2026-08-12: Proposes a regime-gated residual mixture-of-experts architecture for cross-sectional volatility forecasting on 1,027 US equities with walk-forward evaluation.
- [Trends, Volatility, Correlations, and Critical Phenomena in Financial Markets](https://arxiv.org/abs/2606.20145) -- arXiv, 2026-06-18: Forecasts future volatilities and correlations based on current market trends, showing that strong trends increase volatility and correlations, especially in down-trends.
- [Continuous Cash-Overlay Filters for a Static Growth--Defensive Risk Sleeve: Slow-Tail Compensation, V-Shape Crash Brakes, Walk-Forward Validation, and Max-Cash Combination](https://arxiv.org/abs/2606.09025) -- arXiv, 2026-06-08: Develops continuous cash-overlay filters for a static growth-defensive ETF sleeve, targeting slow-tail compensation and V-shape crash brakes with walk-forward validation.
- [On options-driven realized volatility forecasting: Information gains via rough volatility model](https://arxiv.org/abs/2604.02743) -- arXiv, 2026-04-03: Shows that options-derived spot volatility estimates from a rough volatility model improve HAR realized volatility forecasts.
- [Regime Discovery and Intra-Regime Return Dynamics in Global Equity Markets](https://arxiv.org/abs/2601.08571) -- arXiv, 2026-01-13: Identifies market regimes using Hilbert-Huang transform and models return dynamics across regimes in global equity indices.
- [Probability Weighting Meets Heavy Tails: An Econometric Framework for Behavioral Asset Pricing](https://arxiv.org/abs/2511.16563) -- arXiv, 2025-11-20: Develops an econometric framework combining heavy-tailed distributions with behavioral probability weighting, showing improved VaR estimation on 86 assets from 2004-2024. -- reported: Student's t outperforms Gaussian in 88.4% of cases; VaR underestimation 19.7% vs 3.2%
- [Rethinking Portfolio Risk: Forecasting Volatility Through Cointegrated Asset Dynamics](https://arxiv.org/abs/2509.23533) -- arXiv, 2025-09-28: Introduces volatility ratios and a VECM to forecast portfolio volatility using cointegration between equity and index volatilities, improving MAPE.
- [Foundation Time-Series AI Model for Realized Volatility Forecasting](https://arxiv.org/abs/2505.11163) -- arXiv, 2025-05-16: Evaluates TimesFM foundation model for realized volatility forecasting with fine-tuning.
- [Modeling Regime Structure and Informational Drivers of Stock Market Volatility via the Financial Chaos Index](https://arxiv.org/abs/2504.18958) -- arXiv, 2025-04-26: A regime-switching framework using a Financial Chaos Index to identify low, intermediate, and high chaos regimes in stock market volatility.
- [Bridging Econometrics and AI: VaR Estimation via Reinforcement Learning and GARCH Models](https://arxiv.org/abs/2504.16635) -- arXiv, 2025-04-23: Proposes a hybrid framework for VaR estimation combining GARCH models with deep reinforcement learning.
- [Tail Risk Alert Based on Conditional Autoregressive VaR by Regression Quantiles and Machine Learning Algorithms](https://arxiv.org/abs/2412.06193) -- arXiv, 2024-12-09: Develops a multivariate CAViaR model with machine learning to provide early warning of tail risk spillover across US stock, FX, and credit markets.

## Items pointing at missing cells (`new:*`)

### new:agent_based_market_model (3 item(s))

- [Model of cunning agents](https://arxiv.org/abs/2012.08517) -- arXiv, 2020-12-16: Presents a numerical agent-based spin model of financial markets based on the Potts model, where agents' actions are inferred from spin changes.
- [A model of adaptive, market behavior generating positive returns, volatility and system risk](https://arxiv.org/abs/1809.09601) -- arXiv, 2018-09-25: Presents an agent-based model of speculative trading with adaptive behavior that generates persistent price bubbles and system risk.
- [Asynchronous stochastic price pump](https://arxiv.org/abs/1809.09273) -- arXiv, 2018-09-25: Proposes an asynchronous stochastic price pump model for equity trading with adaptive agents, showing stationary return regimes via simulations.

### new:agent_based_simulation (1 item(s))

- [Exploring Narrative Economics: An Agent-Based-Modeling Platform that Integrates Automated Traders with Opinion Dynamics](https://arxiv.org/abs/2012.08840) -- arXiv, 2020-12-16: Introduces an agent-based modeling platform integrating automated traders with opinion dynamics to explore narrative economics and asset price dynamics.

### new:american_option_pricing (1 item(s))

- [Time Deep Gradient Flow Method for pricing American options](https://arxiv.org/abs/2507.17606) -- arXiv, 2025-07-23: Neural network methods for pricing multidimensional American options, comparing Time Deep Gradient Flow and Deep Galerkin methods.

### new:antifragility_measure (1 item(s))

- [Stocks and Cryptocurrencies: Anti-fragile or Robust?](https://arxiv.org/abs/2005.13033) -- arXiv, 2020-05-26: Introduces a measure of antifragility applied to stock and cryptocurrency return data.

### new:arbitrage_conditions (1 item(s))

- [No Arbitrage in Continuous Financial Markets](https://arxiv.org/abs/1809.09588) -- arXiv, 2018-09-25: Derives integral tests for the existence and absence of arbitrage in continuous financial markets with one risky asset.

### new:arbitrage_free_modeling (1 item(s))

- [Arbitrage-free modeling under Knightian Uncertainty](https://arxiv.org/abs/1909.04602) -- arXiv, 2019-09-10: Studies the Fundamental Theorem of Asset Pricing under Knightian uncertainty with a functional analytic approach.

### new:arbitrage_hedging (1 item(s))

- [Free Lunches with Vanishing Risks Most Likely Exist](https://arxiv.org/abs/2508.07108) -- arXiv, 2025-08-09: Argues that free lunches with vanishing risk exist in real markets, demonstrating a dynamic hedging strategy for extreme-maturity zero-coupon bonds.

### new:asset_bubble_modeling (1 item(s))

- [Viscosity Supersolution Barriers to a Non-local Free Boundary Problem](https://arxiv.org/abs/2609.02381) -- arXiv, 2026-09-02: Analyzes viscosity supersolution barriers for a non-local free boundary problem modeling speculative asset bubbles with Lévy processes.

### new:asset_price_bubble_model (1 item(s))

- [Supplement Liquidity based modeling of asset price bubbles via random matching](https://arxiv.org/abs/2311.15793) -- arXiv, 2023-11-27: Supplement proving theorems for a liquidity-based model of asset price bubbles via random matching.

### new:asset_pricing_bubbles (2 item(s))

- [Optional projection under equivalent local martingale measures](https://arxiv.org/abs/2003.09940) -- arXiv, 2020-03-22: A theoretical study of optional projections of strict local martingales to understand asset price bubbles and arbitrage opportunities.
- [Asset Price Bubbles in market models with proportional transaction costs](https://arxiv.org/abs/1911.10149) -- arXiv, 2019-11-22: Studies asset price bubbles in market models with proportional transaction costs, defining fundamental value via super-replication.

### new:asymmetric_capm (1 item(s))

- [An Asymmetric Capital Asset Pricing Model](https://arxiv.org/abs/2404.14137) -- arXiv, 2024-04-22: Proposes an asymmetric CAPM that treats upside and downside market risk differently, applied to Apple stock.

### new:auction_market_microstructure (1 item(s))

- [Optimal Rebate Design: Incentives, Competition and Efficiency in Auction Markets](https://arxiv.org/abs/2501.12591) -- arXiv, 2025-01-22: A theoretical model for designing rebate policies in auction markets with competing market makers.

### new:axiom_of_choice_trading (1 item(s))

- [Getting rich quick with the Axiom of Choice](https://arxiv.org/abs/1604.00596) -- arXiv, 2016-04-03: Presents theoretical get-rich-quick trading schemes based on the Axiom of Choice for continuous or infinite-variation price paths.

### new:behavioral_experiment (1 item(s))

- [Do investors trade too much? A laboratory experiment](https://arxiv.org/abs/1512.03743) -- arXiv, 2015-12-11: Laboratory experiment showing subjects trade too much, harming wealth due to market impact.

### new:behavioral_market_theory (1 item(s))

- [Financial markets as a Le Bonian crowd during boom-and-bust episodes: A complementary theoretical framework in behavioural finance](https://arxiv.org/abs/2510.23175) -- arXiv, 2025-10-27: Proposes a theoretical framework interpreting financial markets as a Le Bonian crowd during boom-bust episodes.

### new:behavioral_trading_models (1 item(s))

- [Speculative Trading, Prospect Theory and Transaction Costs](https://arxiv.org/abs/1911.10106) -- arXiv, 2019-11-22: Characterizes optimal trading strategies for a prospect-theory agent with transaction costs, including buy-and-hold and buy-low-sell-high.

### new:belief_knowledge_jumps (1 item(s))

- [A Framework for Analyzing Stochastic Jumps in Finance based on Belief and Knowledge](https://arxiv.org/abs/1512.00227) -- arXiv, 2015-12-01: Introduces a formal language to analyze stochastic jumps in finance based on belief and knowledge.

### new:benford_digit_anomaly (1 item(s))

- [Benford's laws tests on S&P500 daily closing values and the corresponding daily log-returns both point to huge non-conformity](https://arxiv.org/abs/2104.07962) -- arXiv, 2021-04-16: Tests Benford's law on S&P500 daily closing values and log returns, finding huge non-conformity.

### new:beta_estimation_methodology (1 item(s))

- [Economics, Mathematics, & Common Sense](http://alphamaximus.com/beta/2015/08/31/estimating-beta-log-or-linear.html) -- Alphamaximus, 2015-09-05: Argues that beta estimation should use log returns rather than percentage returns, a methodological point.

### new:binomial_model_no_short (1 item(s))

- [Deviations from Normality in a Financial Model without Short-selling](https://arxiv.org/abs/2505.18723) -- arXiv, 2025-05-24: Presents a binomial asset price model with bulls and bears interacting with a market maker under short-selling bounds, deriving moment formulas and skewness/kurtosis modeling.

### new:black_scholes_solution_method (1 item(s))

- [On a method of solving the Black-Scholes Equation](https://arxiv.org/abs/1504.03074) -- arXiv, 2015-04-13: Proposes a different method for solving a simplified Black-Scholes equation.

### new:bond_illiquidity_pricing (1 item(s))

- [A closed formula for illiquid corporate bonds and an application to the European market](https://arxiv.org/abs/1901.06855) -- arXiv, 2019-01-21: Derives a closed-form option-based formula for pricing illiquidity in corporate bonds, applied to the European market.

### new:bond_indifference_pricing (1 item(s))

- [Bond indifference prices and indifference yield curves](https://arxiv.org/abs/2007.09201) -- arXiv, 2020-07-17: Derives indifference prices for zero-coupon bonds under stochastic interest rates and exponential or power utility.

### new:bond_pricing_formula (1 item(s))

- [A closed-form formula for pricing bonds between coupon payments](https://arxiv.org/abs/1801.06028) -- arXiv, 2018-01-18: Derives closed-form formulas for bond pricing between coupon payments, applicable to Treasury and Street methods.

### new:boundary_risk_management (1 item(s))

- [Boundary-Induced Apparent Risk Aversion in Nonergodic Multiplicative Growth](https://arxiv.org/abs/2607.28230) -- arXiv, 2026-07-30: Studies optimal exposure in multiplicative growth with absorbing boundaries, showing reduced Kelly fractions near boundaries.

### new:branching_process_model (1 item(s))

- [Stock Prices as Janardan Galton Watson Process](https://arxiv.org/abs/2208.08496) -- arXiv, 2022-08-17: Proposes a branching process model for stock prices, a novel theoretical approach.

### new:brokerage_fee_design (1 item(s))

- [Optimal contract design via relaxation: application to the problem of brokerage fee for a client with private signal](https://arxiv.org/abs/2307.07010) -- arXiv, 2023-07-13: Develops a method for optimal contract design applied to brokerage fees with information asymmetry.

### new:bubble_detection (1 item(s))

- [Bubbles in discrete time models](https://arxiv.org/abs/2104.12740) -- arXiv, 2021-04-26: Introduces a new definition of speculative bubbles in discrete-time models with probabilistic characterizations and analytic conditions.

### new:bubble_riding_model (1 item(s))

- [Optimal Bubble Riding with Price-dependent Entry: a Mean Field Game of Controls with Common Noise](https://arxiv.org/abs/2307.11340) -- arXiv, 2023-07-21: Extends a mean field game model for optimal bubble riding with price-dependent entry times.

### new:categorical_pricing_model (1 item(s))

- [A Binomial Asset Pricing Model in a Categorical Setting](https://arxiv.org/abs/1905.01894) -- arXiv, 2019-05-06: Develops a binomial asset pricing model in a categorical setting with generalized filtrations to represent information forgetting.

### new:causal_interaction_indicator (1 item(s))

- [A causal interactions indicator between two time series using extreme variations in the first eigenvalue of lagged correlation matrices](https://arxiv.org/abs/2307.04953) -- arXiv, 2023-07-11: Presents a method to identify causal interactions between time series using eigenvalue variability.

### new:causal_network_forecasting (1 item(s))

- [Hierarchical Representations for Evolving Acyclic Vector Autoregressions (HEAVe)](https://arxiv.org/abs/2505.12806) -- arXiv, 2025-05-19: A method for fitting acyclic vector autoregressions to time series systems to identify causal networks.

### new:charting_technique (1 item(s))

- [Ehlers Loops](https://financial-hacker.com/ehlers-loops/) -- Financial Hacker, 2022-06-14: Introduces Ehlers Loops, a novel charting method for price over time or momentum, as proposed in TASC articles.

### new:climate_risk_credit (1 item(s))

- [Physical Climate Risk in Asset Management](https://arxiv.org/abs/2504.19307) -- arXiv, 2025-04-27: A framework to quantify physical climate risk in asset management using a Vasicek credit risk model with climate-induced jumps.

### new:commodity_extraction_optimization (1 item(s))

- [On an Optimal Extraction Problem with Regime Switching](https://arxiv.org/abs/1602.06765) -- arXiv, 2016-02-22: Studies an optimal extraction problem for an exhaustible commodity with regime switching in spot price volatility.

### new:commodity_futures_basis (1 item(s))

- [Understanding the Non-Convergence of Agricultural Futures via Stochastic Storage Costs and Timing Options](https://arxiv.org/abs/1610.09403) -- arXiv, 2016-10-28: A model explaining non-convergence in agricultural futures via timing options and stochastic storage costs.

### new:compute_futures_pricing (1 item(s))

- [(Early) AI Compute Asset Pricing](https://arxiv.org/abs/2607.12156) -- arXiv, 2026-07-13: Presents an asset-pricing framework for compute futures, linking compute rental markets to a new tradable asset class.

### new:convertible_bond_pricing (1 item(s))

- [Valuation of the Convertible Bonds under Penalty TF model using Finite Element Method](https://arxiv.org/abs/2301.10734) -- arXiv, 2023-01-25: Solves convertible bond pricing using finite element methods with penalty TF model.

### new:copula_risk_modeling (1 item(s))

- [New copulas based on general partitions-of-unity and their applications to risk management (part II)](https://arxiv.org/abs/1709.07682) -- arXiv, 2017-09-22: Introduces new copulas based on partitions-of-unity for fitting asymmetric data in risk management.

### new:corporate_bond_pricing (1 item(s))

- [Double free boundary problem for defaultable corporate bond with credit rating migration risks and their asymptotic behaviors](https://arxiv.org/abs/2301.10898) -- arXiv, 2023-01-26: Presents a pricing model for defaultable corporate bonds with credit rating migration risk, focusing on mathematical properties.

### new:corporate_bond_similarity (1 item(s))

- [Supervised Similarity for High-Yield Corporate Bonds with Quantum Cognition Machine Learning](https://arxiv.org/abs/2502.01495) -- arXiv, 2025-02-03: Applies quantum cognition machine learning to distance metric learning for corporate bonds, useful for trading illiquid bonds.

### new:correlation_coefficient (1 item(s))

- [Correlation and correlation structure (5)     a new coefficient of correlation](https://eranraviv.com/correlation-and-correlation-structure-5-a-new-coefficient-correlation/) -- Eran Raviv, 2021-02-27: Introduces a new coefficient of correlation to quantify dependence between variables beyond linear correlation.

### new:correlation_extension (1 item(s))

- [The extension of Pearson correlation coefficient, measuring noise, and selecting features](https://arxiv.org/abs/2402.00543) -- arXiv, 2024-02-01: Proposes an extension of Pearson correlation coefficient for multi-asset risk assessment.

### new:correlation_network_analysis (1 item(s))

- [A perspective on correlation-based financial networks and entropy measures](https://arxiv.org/abs/2004.09448) -- arXiv, 2020-04-20: This review examines correlation-based financial networks and entropy measures, focusing on their evolution during market crashes and bubbles.

### new:correlation_network_filtering (1 item(s))

- [Minimum spanning tree filtering of correlations for varying time scales and size of fluctuations](https://arxiv.org/abs/1610.08416) -- arXiv, 2016-10-19: Introduces q-dependent minimum spanning trees to filter correlations at different fluctuation amplitudes and time scales, applied to stock market data.

### new:crash_hazard_model (1 item(s))

- [Micro-foundation using percolation theory of the finite-time singular behavior of the crash hazard rate in a class of rational expectation bubbles](https://arxiv.org/abs/1601.07707) -- arXiv, 2016-01-28: Presents a percolation-based micro-foundation for crash hazard rates in rational expectation bubbles.

### new:credit_risk_leverage (1 item(s))

- [Time Reversal and Last Passage Time of Diffusions with Applications to Credit Risk Management](https://arxiv.org/abs/1701.04565) -- arXiv, 2017-01-17: Develops a risk management framework for companies based on leverage process and last passage time, applicable to credit risk.

### new:credit_risk_models (2 item(s))

- [Linear Credit Risk Models](https://arxiv.org/abs/1605.07419) -- arXiv, 2016-05-24: A new class of credit risk models for pricing defaultable bonds and CDS.
- [A martingale representation theorem and valuation of defaultable securities](https://arxiv.org/abs/1510.05858) -- arXiv, 2015-10-20: Develops a martingale representation theorem for valuing defaultable securities under expanded information flows.

### new:cross_asset_correlation_networks (1 item(s))

- [A Look at Financial Dependencies by Means of Econophysics and Financial Economics](https://arxiv.org/abs/2302.08208) -- arXiv, 2023-02-16: A review of financial dependencies using econophysics and financial economics, focusing on correlation networks and information filtering.

### new:cross_impact_derivatives (1 item(s))

- [Cross impact in derivative markets](https://arxiv.org/abs/2102.02834) -- arXiv, 2021-02-04: Proposes a cross-impact model for derivatives markets, using E-Mini futures and options, focusing on tractable estimation.

### new:cross_stock_information_flow (1 item(s))

- [Emerging interdependence between stock values during financial crashes](https://arxiv.org/abs/1611.02549) -- arXiv, 2016-11-08: Uses information theory to detect emerging interdependencies between FTSE 100 stocks during financial crashes.

### new:decision_theory_choice (1 item(s))

- [The Role of Time in Making Risky Decisions and the Function of Choice](https://arxiv.org/abs/1512.08792) -- arXiv, 2015-12-27: Discusses the role of time and number of plays in risky decisions, comparing mathematical expectations with awards in lotteries and St. Petersburg paradox.

### new:default_bond_pricing (1 item(s))

- [PDE models for the valuation of a non callable defaultable coupon bond under an extended JDCEV model](https://arxiv.org/abs/1905.01099) -- arXiv, 2019-05-03: Presents PDE models for valuing non-callable defaultable coupon bonds under an extended JDCEV model.

### new:default_cascade_networks (1 item(s))

- [Particle Systems with Local Interactions via Hitting Times and Cascades on Graphs](https://arxiv.org/abs/2505.18448) -- arXiv, 2025-05-24: Develops a particle system model for default cascades in sparse financial networks with hitting-time local interactions and singular interactions.

### new:derivatives_pricing_signature (1 item(s))

- [Numerical method for model-free pricing of exotic derivatives using rough path signatures](https://arxiv.org/abs/1905.01720) -- arXiv, 2019-05-05: Proposes a model-free method for pricing exotic derivatives using rough path signatures and market prices of other options.

### new:derivatives_pricing_theory (1 item(s))

- [A conditional version of the second fundamental theorem of asset pricing in discrete time](https://arxiv.org/abs/2102.13574) -- arXiv, 2021-02-26: Develops a conditional version of the second fundamental theorem of asset pricing in discrete time, focusing on pricing and hedging theory.

### new:derivatives_pricing_xva (1 item(s))

- [Efficient Computation of Various Valuation Adjustments Under Local Lévy Models](https://arxiv.org/abs/1905.01706) -- arXiv, 2019-05-05: Develops a Fourier-based numerical method for pricing Bermudan derivatives with valuation adjustments under local Lévy models.

### new:deterministic_price_law (1 item(s))

- [The Evolution of Security Prices Is Not Stochastic but Governed by a Physicomathematical Law](https://arxiv.org/abs/1807.10114) -- arXiv, 2018-07-01: This paper argues that security price evolution is deterministic and governed by a physico-mathematical law, rather than stochastic.

### new:detrending_method (1 item(s))

- [A method for de-trending asset prices](https://web.archive.org/web/20221007213558/http://www.sr-sv.com/a-method-for-de-trending-asset-prices/) -- SR SV, 2019-11-05: Proposes a method for de-trending non-stationary asset prices.

### new:dimension_reduction_distance (1 item(s))

- [The Perfect Marriage and Much More: Combining Dimension Reduction, Distance Measures and Covariance](https://arxiv.org/abs/1603.09060) -- arXiv, 2016-03-30: A methodology combining Bhattacharyya distance and Johnson-Lindenstrauss lemma for comparing distributions, applicable to markets and securities.

### new:discount_curve_modeling (1 item(s))

- [Reproducing kernel Hilbert space methods for modelling the discount curve](https://arxiv.org/abs/2506.03342) -- arXiv, 2025-06-03: Presents reproducing kernel Hilbert space methods for modeling the discount curve in the HJM framework.

### new:dividend_policy_optimization (1 item(s))

- [Equilibrium Policy on Dividend and Capital Injection under Time-inconsistent Preferences](https://arxiv.org/abs/2505.23511) -- arXiv, 2025-05-29: A theoretical study of optimal dividend and capital injection policies under time-inconsistent preferences, with closed-form solutions for exponential discounting.

### new:entropy_regime_test (1 item(s))

- [Variance of entropy for testing time-varying regimes with an application to meme stocks](https://arxiv.org/abs/2211.05415) -- arXiv, 2022-11-10: A hypothesis testing procedure is proposed to test for constant Shannon entropy in time series, applied to meme stocks to detect regime changes.

### new:environmental_cva (1 item(s))

- [Environmental CVA with K-Robust Wrong-Way Risk](https://arxiv.org/abs/2603.23842) -- arXiv, 2026-03-25: Proposes an environmental valuation adjustment framework for CVA with scenario-to-credit translation and robust wrong-way risk bounds.

### new:environmental_index_market (1 item(s))

- [The Financial Market of Environmental Indices](https://arxiv.org/abs/2308.15661) -- arXiv, 2023-08-29: Proposes a global financial market for environmental indices, monetizing them as dollar-denominated assets for institutional investors.

### new:equity_linked_insurance_pricing (1 item(s))

- [Pricing equity-linked life insurance contracts with multiple risk factors by neural networks](https://arxiv.org/abs/2007.08804) -- arXiv, 2020-07-17: Prices equity-linked life insurance contracts with multiple risk factors using neural networks and local variance hedging.

### new:excel_models (1 item(s))

- [Flexing VBA For Quants (And Everyone Else)](https://web.archive.org/web/20210411211156/http://indexswingtrader.blogspot.com/2016/10/flexing-vba-for-quants-and-everyone-else.html) -- TrendXplorer, 2016-10-24: Tutorial on implementing Protective Asset Allocation and Global Protective Momentum models in Excel using VBA.

### new:execution_algo (4 item(s))

- [Can Large Language Models Execute Parent Orders?](https://arxiv.org/abs/2607.28410) -- arXiv, 2026-07-30: Introduces PACE, an LLM-based hierarchical framework for parent-order execution to reduce execution costs.
- [Optimal Execution with Passive Market Impact](https://arxiv.org/abs/2607.28323) -- arXiv, 2026-07-30: Derives a mesoscopic model for optimal execution with limit orders and passive market impact.
- [Optimizing Execution Cost Using Stochastic Control](https://arxiv.org/abs/1909.10762) -- arXiv, 2019-09-24: Proposes an optimal stock execution strategy using stochastic control theory.
- [Mechanics of good trade execution in the framework of linear temporary market impact](https://arxiv.org/abs/1909.10464) -- arXiv, 2019-09-23: Constructs dynamic trade execution strategies under linear temporary market impact.

### new:execution_algorithms (1 item(s))

- [Approximately optimal trade execution strategies under fast mean-reversion](https://arxiv.org/abs/2307.07024) -- arXiv, 2023-07-13: Proposes optimal trade execution strategies under uncertain volatility and liquidity.

### new:expert_opinion_filter (1 item(s))

- [Diffusion Approximations for Expert Opinions in a Financial Market with Gaussian Drift](https://arxiv.org/abs/1807.00568) -- arXiv, 2018-07-02: This paper analyzes the asymptotic behavior of a filter for estimating an unobservable drift in a financial market with expert opinions.

### new:fair_decision_risk_measures (1 item(s))

- [Marginal Fairness: Fair Decision-Making under Risk Measures](https://arxiv.org/abs/2505.18895) -- arXiv, 2025-05-24: Introduces marginal fairness for decision-making under generalized distortion risk measures, ensuring insensitivity to protected attribute perturbations.

### new:fermat_torricelli_risk (1 item(s))

- [Using Fermat-Torricelli points in assessing investment risks](https://arxiv.org/abs/2408.09267) -- arXiv, 2024-08-17: Using Fermat-Torricelli points to smooth numerical series and assess investment risks.

### new:financial_network_causality (1 item(s))

- [Enhancing Causal Discovery in Financial Networks with Piecewise Quantile Regression](https://arxiv.org/abs/2408.12210) -- arXiv, 2024-08-22: Introduces piecewise quantile regression for causal discovery in financial networks from price series.

### new:financial_network_reconstruction (1 item(s))

- [Enhanced capital-asset pricing model for the reconstruction of bipartite financial networks](https://arxiv.org/abs/1606.07684) -- arXiv, 2016-06-24: Proposes a method to reconstruct bipartite financial networks from partial information.

### new:financial_structure_modeling (1 item(s))

- [A Computational Framework for Financial Structures](https://arxiv.org/abs/2602.14378) -- arXiv, 2026-02-16: Develops a computational framework for formalizing financial structures as structured allocation systems.

### new:forward_performance_criteria (1 item(s))

- [Temporal and Spatial Turnpike-Type Results Under Forward Time-Monotone Performance Criteria](https://arxiv.org/abs/1702.05649) -- arXiv, 2017-02-18: Presents turnpike-type results for risk tolerance under forward time-monotone performance criteria in incomplete markets.

### new:forward_performance_incomplete_markets (1 item(s))

- [Asymptotic analysis of forward performance processes in incomplete markets and their ill-posed HJB equations](https://arxiv.org/abs/1504.03209) -- arXiv, 2015-04-13: Provides asymptotic analysis of forward performance processes in incomplete markets with slow and fast factors.

### new:fourier_risk_measure (1 item(s))

- [A new measure of risk using Fourier analysis](https://arxiv.org/abs/2408.10279) -- arXiv, 2024-08-18: Proposes a Fourier analysis-based risk measure for financial products, correcting flaws in previous attempts.

### new:fractal_market_analysis (1 item(s))

- [The coastline paradox and the fractal dimension of markets](https://www.quanttrader.com/index.php/the-coastline-paradox-and-the-fractal-dimension-of-markets/KahlerPhilipp2021) -- Philipp Kahler, 2021-02-17: Discusses the fractal nature of market data, comparing it to coastlines and suggesting scale-invariant patterns.

### new:geometric_arbitrage (1 item(s))

- [Can You hear the Shape of a Market? Geometric Arbitrage and Spectral Theory](https://arxiv.org/abs/1509.03264) -- arXiv, 2015-09-02: Presents a geometric theory of arbitrage using stochastic principal fibre bundles.

### new:geometric_pattern_detection (1 item(s))

- [Quantitative Geometric Market Structuralism: A Framework for Detecting Structural Endpoints in Financial Markets](https://arxiv.org/abs/2511.16319) -- arXiv, 2025-11-20: Introduces a hybrid geometric pattern recognition and quantitative modeling framework to identify structural endpoints in market movements, with proprietary validation.

### new:grid_trading_ml (1 item(s))

- [Newly Developed Flexible Grid Trading Model Combined ANN and SSO algorithm](https://arxiv.org/abs/2211.12839) -- arXiv, 2022-09-05: A grid trading model combined with ANN and SSO algorithm for automated trading.

### new:hawkes_process_scaling (1 item(s))

- [Rough fractional diffusions as scaling limits of nearly unstable heavy tailed Hawkes processes](https://arxiv.org/abs/1504.03100) -- arXiv, 2015-04-13: Shows that nearly unstable heavy-tailed Hawkes processes converge to fractional CIR processes, explaining persistence.

### new:hazard_rate_filtering (1 item(s))

- [Filtering in a hazard rate change-point model with financial and life-insurance applications](https://arxiv.org/abs/2505.13185) -- arXiv, 2025-05-19: A filtering framework for estimating hazard rates with unobservable change-points, applicable to default intensity.

### new:hedging_decomposition (1 item(s))

- [Stability and asymptotic analysis of the Föllmer-Schweizer decomposition on a finite probability space](https://arxiv.org/abs/2002.03286) -- arXiv, 2020-02-09: The paper analyzes the stability and asymptotic behavior of the Follmer-Schweizer decomposition for hedging in binomial and trinomial models.

### new:homeownership_wealth (1 item(s))

- [Homeownership as Life Cycle Goldmine: Evidence from Macrohistory](https://arxiv.org/abs/2507.17624) -- arXiv, 2025-07-23: Simulates lifecycle wealth and welfare gains from homeownership versus renting and investing in financial assets.

### new:hurst_exponent_analysis (1 item(s))

- [Demystifying the Hurst Exponent     Part 1](https://web.archive.org/web/20220703113611/http://robotwealth.com/demystifying-the-hurst-exponent-part-1/) -- Robot Wealth, 2016-11-01: Introduces the Hurst exponent for analyzing mean-reverting versus trending time series.

### new:hurst_exponent_market_selection (1 item(s))

- [Find Your Best Market to Trade With the Hurst Exponent](https://raposa.trade/blog/find-your-best-market-to-trade-with-the-hurst-exponent/) -- Raposa Trade, 2022-04-12: Discusses using the Hurst exponent to identify the best market to trade.

### new:hyperbolic_diffusion_model (1 item(s))

- [Wild Randomness, and the application of Hyperbolic Diffusion in Financial Modelling](https://arxiv.org/abs/2101.04604) -- arXiv, 2021-01-12: Constructs martingale processes with Cauchy-distributed margins for financial modeling, a theoretical contribution.

### new:illiquid_stock_pricing (1 item(s))

- [Modelling Illiquid Stocks Using Quantum Stochastic Calculus](https://arxiv.org/abs/2302.05243) -- arXiv, 2023-02-10: Extends Black-Scholes to model illiquid stocks via quantum stochastic calculus, capturing bid-offer spread widening.

### new:index_tracking_derivatives (1 item(s))

- [Dynamic Index Tracking and Risk Exposure Control Using Derivatives](https://arxiv.org/abs/1705.10454) -- arXiv, 2017-05-30: Develops a methodology for dynamic index tracking and risk exposure control using derivatives.

### new:insider_trading_game_theory (1 item(s))

- [An Infinite-Dimensional Insider Trading Game](https://arxiv.org/abs/2602.21125) -- arXiv, 2026-02-24: A theoretical generalization of Kyle's insider trading model to infinite-dimensional asset spaces, deriving equilibrium trading strategies and price impact.

### new:insider_trading_microstructure (1 item(s))

- [Equilibrium price and optimal insider trading strategy under stochastic liquidity with long memory](https://arxiv.org/abs/1901.00345) -- arXiv, 2019-01-02: Extends the Kyle insider trading model with stochastic liquidity and long memory, deriving optimal insider strategies and price impact.

### new:intrinsic_entropy_indicator (1 item(s))

- [An Intrinsic Entropy Model for Exchange-Traded Securities](https://arxiv.org/abs/2205.01386) -- arXiv, 2022-05-03: Introduces an intrinsic entropy model using stock exchange trading data to gauge investor interest in exchange-traded securities.

### new:intrinsic_entropy_volatility (1 item(s))

- [A Volatility Estimator of Stock Market Indices Based on the Intrinsic Entropy Model](https://arxiv.org/abs/2205.01370) -- arXiv, 2022-05-03: Presents an intrinsic entropy model as a substitute for estimating volatility of stock market indices using traded volume data.

### new:investor_behavior (1 item(s))

- [Impact of Investing Characteristics on Financial Performance of Individual Investors: An Exploratory Study](https://arxiv.org/abs/2311.00384) -- arXiv, 2023-11-01: Exploratory study linking individual investor characteristics to excess returns in an equity market.

### new:lattice_gas_market_model (1 item(s))

- [Financial Markets and the Phase Transition between Water and Steam](https://arxiv.org/abs/2107.03857) -- arXiv, 2021-07-08: Presents a lattice gas model of financial markets, equivalent to the Ising model, to explain trends and reversion, but provides no empirical backtest.

### new:levy_flight_model (1 item(s))

- [Levy flights. Foraging in a finance blog](http://quantdare.com/2016/11/levy-flights/) -- Quant Dare, 2016-11-17: Introduces Levy flights as a mathematical model for financial market behavior.

### new:life_contingent_pricing (1 item(s))

- [Dynamic Asset Pricing Theory for Life Contingent Risks](https://arxiv.org/abs/2503.21256) -- arXiv, 2025-03-27: Develops dynamic asset pricing theory for life-contingent assets, revisiting the Fundamental Theorem of Asset Pricing and martingale conditions.

### new:liquidity_model (1 item(s))

- [A String Model of Liquidity in Financial Markets](https://arxiv.org/abs/1608.05900) -- arXiv, 2016-08-21: A theoretical model of liquidity using order book net demand surfaces, proving no-arbitrage conditions.

### new:long_term_median_model (1 item(s))

- [A long-term alternative formula for a stochastic stock price model](https://arxiv.org/abs/1904.04422) -- arXiv, 2019-04-09: Proposes a long-term alternative formula for stock price variation using median instead of mean in geometric Brownian motion.

### new:market_arbitrage_construction (1 item(s))

- [Volatility and Arbitrage](https://arxiv.org/abs/1608.06121) -- arXiv, 2016-08-22: Theoretical paper showing strong arbitrage relative to the market when total relative variation grows at a bounded-away-from-zero rate.

### new:market_chaos_index (1 item(s))

- [Theory and Applications of Financial Chaos Index](https://arxiv.org/abs/2101.02288) -- arXiv, 2021-01-05: A paper introducing a new stock market index based on tensor embeddings to capture market chaos and volatility.

### new:market_dynamics_theory (1 item(s))

- [Information-minimizing stationary financial market dynamics](https://arxiv.org/abs/2507.18395) -- arXiv, 2025-07-24: Derives financial market dynamics from information-theoretic principles, modeling the growth optimal portfolio and risk-neutral measures.

### new:market_ecology (1 item(s))

- [How Market Ecology Explains Market Malfunction](https://arxiv.org/abs/2009.09454) -- arXiv, 2020-09-20: Uses an ecological framework to model market dynamics with value, trend, and noise traders.

### new:market_impact_capacity (1 item(s))

- [Uniform Inference and Certified Capacity at a Reflexive Stability Boundary](https://arxiv.org/abs/2609.02535) -- arXiv, 2026-09-02: Develops uniform inference and certified capacity decisions for an estimated financial stability boundary with conditional risk and cross-impact.

### new:market_impact_equilibrium (1 item(s))

- [Mean-field equilibrium of heterogeneous agents under market impact](https://arxiv.org/abs/2609.03115) -- arXiv, 2026-09-02: Introduces a linear mean-field equilibrium model of heterogeneous agents with market impact and common predictable signals.

### new:market_impact_game (1 item(s))

- [Nash equilibrium for risk-averse investors in a market impact game with transient price impact](https://arxiv.org/abs/1807.03813) -- arXiv, 2018-07-10: Analyzes Nash equilibria for risk-averse agents in a market impact game with transient price impact.

### new:market_impact_manipulation (1 item(s))

- [Price manipulation in nonlinear transient impact models: rigidity before memory and complete positivity after memory](https://arxiv.org/abs/2609.02447) -- arXiv, 2026-09-02: Classifies price manipulation criteria in nonlinear transient impact models based on the order of composition of nonlinearity and memory kernel.

### new:market_impact_model (1 item(s))

- [Impact is not just volatility](https://arxiv.org/abs/1905.04569) -- arXiv, 2019-05-11: Argues market impact should not be confused with volatility and provides a scaling argument to rationalize empirical findings.

### new:market_impact_risk (1 item(s))

- [To VaR, or Not to VaR, That is the Question](https://arxiv.org/abs/2101.08559) -- arXiv, 2021-01-21: Introduces market-based probabilities of price and return that account for trade volume randomness, affecting VaR assessments.

### new:market_manipulation_impact (1 item(s))

- [Celebrating Three Decades of Worldwide Stock Market Manipulation](https://arxiv.org/abs/1912.01708) -- arXiv, 2019-11-20: Reflects on decades of stock market manipulation, discussing market impact and price movement strategies.

### new:market_microstructure (1 item(s))

- [AHEAD : Ad-Hoc Electronic Auction Design](https://arxiv.org/abs/2010.02827) -- arXiv, 2020-10-06: Proposes a new ad-hoc electronic auction design for financial markets and analyzes its equilibrium properties.

### new:market_microstructure_agent_model (1 item(s))

- [Dynamics of the Price Behavior in Stock Market: A Statistical Physics Approach](https://arxiv.org/abs/1912.11665) -- arXiv, 2019-12-25: Uses statistical physics to model stock market dynamics with agents as spins and a critical temperature for market disorder.

### new:market_microstructure_flow (1 item(s))

- [Market Dynamics. On A Muse Of Cash Flow And Liquidity Deficit](https://arxiv.org/abs/1709.06759) -- arXiv, 2017-09-20: A theoretical paper on market dynamics using execution flow and 'impact from the future' to extract directional information.

### new:market_microstructure_heuristics (1 item(s))

- [Heuristics in experiments with infinitely large strategy spaces](https://arxiv.org/abs/2005.02337) -- arXiv, 2020-05-05: Introduces a methodology to detect convergence to Nash equilibria in repeated games, applying it to financial market experiments with a predictive measure ΔD.

### new:market_microstructure_model (1 item(s))

- [Modelling Financial Markets by Self-Organized Criticality](https://arxiv.org/abs/1507.04298) -- arXiv, 2015-07-15: A self-organized criticality model with chartists and fundamentalists reproduces stylized facts of financial markets.

### new:market_microstructure_models (1 item(s))

- [From Disequilibrium Markets to Equilibrium](https://arxiv.org/abs/1912.09679) -- arXiv, 2019-12-20: Studies the transition from disequilibrium to equilibrium in financial market models using asymptotic analysis and numerical examples.

### new:market_microstructure_overpricing (1 item(s))

- [The Invisible Handshake: Persistent Overpricing by Adaptive Market Agents](https://arxiv.org/abs/2510.15995) -- arXiv, 2025-10-14: Theoretical study of persistent overpricing in a market maker-taker game.

### new:market_microstructure_rank_dynamics (1 item(s))

- [Traveling Waves in Equity Markets with Rank-Based Entry and Exit](https://arxiv.org/abs/2608.27156) -- arXiv, 2026-08-27: A theoretical model of equity market capital distribution dynamics with rank-based entry/exit, calibrated on CRSP data.

### new:market_microstructure_stable_law (1 item(s))

- [Universal Lévy's stable law of stock market and its characterization](https://arxiv.org/abs/1709.06279) -- arXiv, 2017-09-19: A paper characterizing stock market price fluctuations using Lévy's stable distribution, finding universal parameters in long term but instability in short term.

### new:market_microstructure_theory (3 item(s))

- [Market Dynamics of Information Avalanches](https://arxiv.org/abs/2603.00361) -- arXiv, 2026-02-27: Models financial markets as a sandpile of information avalanches linking scaling laws to price volatility and Sharpe ratio constraints.
- [The Intrinsic Instability of Financial Markets](https://arxiv.org/abs/1508.02203) -- arXiv, 2015-08-10: A theoretical framework explaining financial price fluctuations via multiplicative random growth and speculative feedback.
- [Mathematics of Market Microstructure under Asymmetric Information](https://arxiv.org/abs/1809.03885) -- arXiv, 2018-09-09: Lecture notes on market microstructure under asymmetric information, covering the Kyle model and related mathematical topics.

### new:market_microstructure_utility (1 item(s))

- [On the utility problem in a market where price impact is transient](https://arxiv.org/abs/2511.12093) -- arXiv, 2025-11-15: A theoretical study on utility maximization in a market with transient price impact, proving existence of solutions under relaxed conditions.

### new:market_microstructure_variance (1 item(s))

- [Market-Based Variance of Market Portfolio and of Entire Market](https://arxiv.org/abs/2510.13790) -- arXiv, 2025-10-15: Theoretical framework for market-based variance of trades and market portfolio.

### new:market_model_axioms (1 item(s))

- [Financial market models in discrete time beyond the concave case](https://arxiv.org/abs/1512.01758) -- arXiv, 2015-12-06: Proposes a general axiomatic framework for discrete-time financial market models without concavity assumptions.

### new:market_regularities (1 item(s))

- [Regularities in stock markets](https://arxiv.org/abs/1907.00371) -- arXiv, 2019-06-30: Studies statistical regularities in stock indices from six countries, including growth patterns and volatility behavior.

### new:market_structure_equilibrium (1 item(s))

- [Market shape formation, statistical equilibrium and neutral evolution theory](https://arxiv.org/abs/1506.07163) -- arXiv, 2015-06-23: Uses population genetics and exchangeability to model equity market shape formation and statistical equilibrium.

### new:martingale_optimal_transport (2 item(s))

- [Geometric Martingale Benamou-Brenier transport and geometric Bass martingales](https://arxiv.org/abs/2406.04016) -- arXiv, 2024-06-06: Introduces geometric Bass martingales as solutions to a martingale version of optimal transport, extending prior arithmetic results.
- [Computational Methods for Martingale Optimal Transport problems](https://arxiv.org/abs/1710.07911) -- arXiv, 2017-10-22: Develops numerical methods for martingale optimal transport problems using linear programming discretization and relaxation of the martingale constraint.

### new:martingale_pricing_structure (1 item(s))

- [Admissible Information Structures and the Non-Existence of Global Martingale Pricing](https://arxiv.org/abs/2601.12541) -- arXiv, 2026-01-18: A theoretical paper on the existence of a single admissible information structure for martingale pricing across asset classes.

### new:mean_field_game_ranking (1 item(s))

- [A rank based mean field game in the strong formulation](https://arxiv.org/abs/1603.06312) -- arXiv, 2016-03-21: Solves a rank-based mean field game with common noise, providing an approximate Nash equilibrium for finite player games.

### new:microstructure_model (1 item(s))

- [From quantum mechanics to finance: Microfoundations for jumps, spikes and high volatility phases in diffusion price processes](https://arxiv.org/abs/1609.05286) -- arXiv, 2016-09-17: Presents a microscopic agent-based model that generates jumps, spikes, and high volatility in price processes, with convergence to Itô-diffusion in the large market limit.

### new:model_free_quadratic_variation (1 item(s))

- [On the quadratic variation of the model-free price paths with jumps](https://arxiv.org/abs/1710.07894) -- arXiv, 2017-10-22: Proves that model-free typical price paths with restricted downward jumps have partition-independent quadratic variation and defines quasi-explicit quantities for it.

### new:model_independent_arbitrage (1 item(s))

- [Arbitrage and Hedging in model-independent markets with frictions](https://arxiv.org/abs/1512.01488) -- arXiv, 2015-12-04: Provides fundamental theorems for model-independent markets with transaction costs.

### new:model_robustness_hedging (1 item(s))

- [Adapted Wasserstein Distances and Stability in Mathematical Finance](https://arxiv.org/abs/1901.07450) -- arXiv, 2019-01-22: Examines stability of hedging and pricing under model uncertainty using adapted Wasserstein distances, showing standard distances may be inadequate.

### new:model_uncertainty_pricing (1 item(s))

- [Asset pricing under model uncertainty with discrete time and states](https://arxiv.org/abs/2408.13048) -- arXiv, 2024-08-23: Theoretical paper on asset pricing under model uncertainty with discrete time and states, focusing on no-arbitrage conditions with short sales prohibitions.

### new:monty_hall_index_signal (1 item(s))

- [Let s make a deal : from TV shows to identifying trends](https://web.archive.org/web/20201029195547/http://quantdare.com/2016/03/lets-make-a-deal-monty-hall-problem/) -- Quant Dare, 2016-03-18: Explores applying the Monty Hall problem concept to identify trends in a stock index context.

### new:multi_asset_bubble_model (1 item(s))

- [Multi-Asset Bubbles Equilibrium Price Dynamics](https://arxiv.org/abs/2206.01468) -- arXiv, 2022-06-03: Theoretical model of price bubbles and crashes in a two-asset equilibrium with factor and investment strategies.

### new:multifractal_spectrum_estimation (1 item(s))

- [Techniques for multifractal spectrum estimation in financial time series](https://arxiv.org/abs/1610.07028) -- arXiv, 2016-10-22: Compares techniques for estimating multifractal spectra in financial time series, applied to daily and high-frequency data.

### new:multifractal_time_series (1 item(s))

- [The new face of multifractality: Multi-branchedness and the phase transitions in time series of mean inter-event times](https://arxiv.org/abs/1809.02674) -- arXiv, 2018-09-07: Introduces a modified multifractal analysis for inter-event time series, focusing on multi-branchedness and phase transitions.

### new:multilevel_monte_carlo_exit_times (1 item(s))

- [Multilevel estimation of expected exit times and other functionals of stopped diffusions](https://arxiv.org/abs/1710.07492) -- arXiv, 2017-10-20: Proposes a multilevel Monte Carlo method for estimating mean exit times of Brownian diffusions with improved complexity bounds.

### new:network_market_instability (1 item(s))

- [Network geometry and market instability](https://arxiv.org/abs/2009.12335) -- arXiv, 2020-09-25: Uses network geometry and higher-order interactions among stocks to analyze market instability.

### new:nonlinear_black_scholes (1 item(s))

- [Symmetry reduction and exact solutions of the non-linear Black--Scholes equation](https://arxiv.org/abs/1512.06151) -- arXiv, 2015-11-30: Studies symmetry reduction and exact solutions of a non-linear Black-Scholes equation.

### new:numeraire_perturbation_pricing (1 item(s))

- [Fair pricing and hedging under small perturbations of the numéraire on a finite probability space](https://arxiv.org/abs/2208.09898) -- arXiv, 2022-08-21: Analyzes fair pricing and hedging under small perturbations of the numeraire, showing stability for replicable claims.

### new:numerical_methods (1 item(s))

- [Efficient inverse $Z$-transform and Wiener-Hopf factorization](https://arxiv.org/abs/2404.19290) -- arXiv, 2024-04-30: Presents efficient numerical methods for Z-transform inversion and Wiener-Hopf factorization with applications to moments and causal filters. -- reported: Precision E-14 in microseconds, E-11 in milliseconds

### new:optimal_dividend_policy (1 item(s))

- [The dividend problem with a finite horizon](https://arxiv.org/abs/1609.01655) -- arXiv, 2016-09-06: Characterizes the value function of the optimal dividend problem with finite horizon as a classical solution of a Hamilton-Jacobi-Bellman equation.

### new:optimal_execution (6 item(s))

- [Some Computations for Optimal Execution with Monotone Strategies](https://arxiv.org/abs/2411.10726) -- arXiv, 2024-11-16: Theoretical characterization of optimal execution with monotone strategies in a Black-Scholes model with linear price impact.
- [On regularized optimal execution problems and their singular limits](https://arxiv.org/abs/2101.02731) -- arXiv, 2021-01-07: A theoretical paper on optimal portfolio execution with uncertain volatility and liquidity, using a power-law price impact model.
- [Optimal Trade Execution with Instantaneous Price Impact and Stochastic Resilience](https://arxiv.org/abs/1611.03435) -- arXiv, 2016-11-10: Studies optimal trade execution with price impact and stochastic resilience using BSDEs.
- [Optimal liquidation trajectories for the Almgren-Chriss model with Levy processes](https://arxiv.org/abs/2002.03376) -- arXiv, 2020-02-09: The paper solves an optimal liquidation problem in the Almgren-Chriss framework with Levy processes and general temporary price impact functions.
- [Static vs adapted optimal execution strategies in two benchmark trading models](https://arxiv.org/abs/1609.05523) -- arXiv, 2016-09-18: Compares static vs adaptive optimal execution strategies in two benchmark trading models, focusing on cost and risk minimization.
- [Theoretical and Numerical Analysis of an Optimal Execution Problem with Uncertain Market Impact](https://arxiv.org/abs/1506.02789) -- arXiv, 2015-06-09: A theoretical analysis of an optimal execution problem with uncertain market impact, showing that noise in impact leads to underestimation of costs.

### new:optimal_execution_impact (1 item(s))

- [Optimal Trading under Instantaneous and Persistent Price Impact, Predictable Returns and Multiscale Stochastic Volatility](https://arxiv.org/abs/2507.17162) -- arXiv, 2025-07-23: Extends optimal trading theory to include predictable returns, price impact, and multiscale stochastic volatility.

### new:optimal_execution_signature (1 item(s))

- [Optimal execution with rough path signatures](https://arxiv.org/abs/1905.00728) -- arXiv, 2019-05-02: Uses rough path signatures to approximate optimal execution strategies, providing numerical evidence of accuracy.

### new:optimal_execution_theory (2 item(s))

- [Universal trading under proportional transaction costs](https://arxiv.org/abs/1603.06558) -- arXiv, 2016-03-21: Presents a universal law for optimal trading under proportional transaction costs, applied to trading algorithm design.
- [Optimal Liquidation under Stochastic Liquidity](https://arxiv.org/abs/1603.06498) -- arXiv, 2016-03-21: Solves an optimal liquidation problem with stochastic liquidity and transient price impact.

### new:optimal_investment_theory (1 item(s))

- [An Explicit Solution for the Problem of Optimal Investment with Random Endowment](https://arxiv.org/abs/2506.20506) -- arXiv, 2025-06-25: Derives an explicit solution for optimal investment with random endowment in a Black-Scholes market.

### new:optimal_liquidation (1 item(s))

- [Liquidity Stress Testing using Optimal Portfolio Liquidation](https://arxiv.org/abs/2102.02877) -- arXiv, 2021-02-04: Builds an optimal portfolio liquidation model for OTC markets, focusing on corporate bonds, to minimize trading costs via liquidation time choice.

### new:optimal_stopping_algorithm (1 item(s))

- [Semi-tractability of optimal stopping problems via a weighted stochastic mesh algorithm](https://arxiv.org/abs/1906.09431) -- arXiv, 2019-06-22: Introduces a weighted stochastic mesh algorithm for optimal stopping problems with complexity bounds.

### new:optimal_stopping_foresight (1 item(s))

- [The value of foresight](https://arxiv.org/abs/1601.05872) -- arXiv, 2016-01-22: Studies the value of foresight in optimal stopping for selling a stock, providing bounds on the improvement.

### new:optimal_stopping_trading (1 item(s))

- [A class of recursive optimal stopping problems with applications to stock trading](https://arxiv.org/abs/1905.02650) -- arXiv, 2019-05-07: Solves a class of recursive optimal stopping problems and applies it to stock trading across two market venues.

### new:option_price_consistency (1 item(s))

- [Consistency of option prices under bid-ask spreads](https://arxiv.org/abs/1608.05585) -- arXiv, 2016-08-19: Theoretical study on when option prices are consistent with a market model under bid-ask spreads.

### new:order_execution (1 item(s))

- [Leveraging IS and TC: Optimal order execution subject to reference strategies](https://arxiv.org/abs/2401.03305) -- arXiv, 2024-01-06: Formulates optimal order execution for broker-dealers under a reference strategy benchmark in the Almgren-Chriss framework.

### new:order_flow_memory (1 item(s))

- [Switching Frictions, Heterogeneous Trading Horizons, and Long-Memory Order Flow](https://arxiv.org/abs/2609.02525) -- arXiv, 2026-09-02: Explains long-memory order flow through switching frictions and heterogeneous trading horizons, linking representation-spell durations to flow covariance decay.

### new:outlier_detection (1 item(s))

- [Non-parametric cumulants approach for outlier detection of multivariate financial data](https://arxiv.org/abs/2305.10911) -- arXiv, 2023-05-18: Proposes a non-parametric cumulant-based method for outlier detection in multivariate financial data.

### new:path_signature_risk (1 item(s))

- [The Geometry of Risk: Path-Dependent Regulation and Anticipatory Hedging via the SigSwap](https://arxiv.org/abs/2603.24154) -- arXiv, 2026-03-25: Introduces a path-signature-based framework for decomposing path-dependent financial risk into linear factors.

### new:pathwise_integral (1 item(s))

- [Purely pathwise probability-free Ito integral](https://arxiv.org/abs/1512.01698) -- arXiv, 2015-12-05: Develops purely pathwise constructions of the Ito integral without probabilistic assumptions.

### new:periodic_signal_detection (1 item(s))

- [Structure Function: Forgotten Detection Tool for Periodic Signals](https://quantatrisk.com/2023/07/07/structure-function-periodic-signals/) -- Quant at Risk, 2023-07-08: Discusses using structure function for detecting periodic signals in time series, with finance applications.

### new:perpetual_futures (1 item(s))

- [Perpetual Futures for Stocks: The SpaceX Pre-IPO Market](https://arxiv.org/abs/2609.05433) -- arXiv, 2026-06-22: Analyzes perpetual futures for stocks, including the SpaceX pre-IPO market, with a no-arbitrage pricing result.

### new:podcast_review (1 item(s))

- [Podcast: 2017 roundup: the year in review](https://web.archive.org/web/20210516090657/http://bettersystemtrader.com/138-2017-roundup/) -- Better System Trader, 2017-12-27: A podcast episode reviewing the year 2017 and special guests.

### new:polynomial_term_structure_models (1 item(s))

- [Polynomial term structure models](https://arxiv.org/abs/1504.03238) -- arXiv, 2015-04-13: Classifies polynomial term structure models and characterizes feasible parameters.

### new:position_sizing_kelly (1 item(s))

- [Kelly Criterion: From a Simple Random Walk to Lévy Processes](https://arxiv.org/abs/2002.03448) -- arXiv, 2020-02-09: The paper generalizes the Kelly criterion to more general return models and continuous-time limits.

### new:prediction_market_signal (1 item(s))

- [Prediction Markets as Bayesian Inverse Problems: Uncertainty Quantification, Identifiability, and Information Gain from Price-Volume Histories under Latent Types](https://arxiv.org/abs/2601.18815) -- arXiv, 2026-01-22: Formulates prediction markets as Bayesian inverse problems to infer outcomes from price-volume histories.

### new:price_displacement_physics (1 item(s))

- [The Action Principle in Market Mechanics](https://arxiv.org/abs/1705.09965) -- arXiv, 2017-05-28: Theorizes that asset price displacements follow physical laws, modeled as a harmonic oscillator with constraints.

### new:price_impact_equilibrium (1 item(s))

- [Endogenous inverse demand functions](https://arxiv.org/abs/2012.08002) -- arXiv, 2020-12-14: Presents an equilibrium formulation for price impacts in a fire sale, generalizing the Esscher premium.

### new:price_impact_modeling (1 item(s))

- [Stability for gains from large investors' strategies in M1/J1 topologies](https://arxiv.org/abs/1701.02167) -- arXiv, 2017-01-09: Proves continuity properties for large investor strategies in illiquid markets, relevant to price impact modeling.

### new:price_impact_portfolio_theory (1 item(s))

- [Stochastic portfolio theory with price impact](https://arxiv.org/abs/2506.07993) -- arXiv, 2025-06-09: Extends stochastic portfolio theory to include nonlinear price impact and derives master formulas for trading strategies in high-dimensional markets.

### new:price_smoothing (1 item(s))

- [A “New” Way to Smooth Price](https://web.archive.org/web/20250215080941/http://dekalogblog.blogspot.com/2024/12/a-new-way-to-smooth-price.html) -- Dekalog Blog, 2024-12-31: Introduces a new price smoothing method that projects a 5-bar rolling linear fit 3 bars into the future.

### new:prices_convolution (1 item(s))

- [Prices Convolution, A Practical Approach](https://quantdare.wordpress.com/2015/06/17/prices-convolution-a-practical-approach/) -- Quant Dare, 2015-07-07: Introduces a practical approach to applying convolution to price data.

### new:principal_agent_contracts (1 item(s))

- [Analysis of the Risk-Sharing Principal-Agent problem through the Reverse-H{ö}lder inequality](https://arxiv.org/abs/1809.07040) -- arXiv, 2018-09-19: Provides a framework for solving the risk-sharing principal-agent problem under CARA utilities.

### new:probability_distortion_expectations (1 item(s))

- [Time-consistent conditional expectation under probability distortion](https://arxiv.org/abs/1809.08262) -- arXiv, 2018-09-21: Introduces a time-consistent conditional expectation under probability distortion, addressing time-inconsistency issues.

### new:quantum_model (1 item(s))

- [Potential in the Schrodinger equation: estimation from empirical data](https://arxiv.org/abs/2004.06626) -- arXiv, 2020-03-17: Describes a method to estimate the potential in a Schrodinger equation model for stock price distributions.

### new:quantum_portfolio_modeling (1 item(s))

- [Quantum Gates and Quantum Circuits of Stock Portfolio](https://arxiv.org/abs/1507.02310) -- arXiv, 2015-06-27: Proposes a quantum computation model for stock portfolio price time series using Ising anyons and quantum gates.

### new:quantum_price_formation (1 item(s))

- [Quantum theory of securities price formation in financial markets](https://arxiv.org/abs/1605.04948) -- arXiv, 2016-04-12: A theoretical framework for securities price formation based on quantum principles, describing return distributions as speckle patterns.

### new:quantum_price_model (1 item(s))

- [Quantum model for price forecasting in financial markets](https://arxiv.org/abs/1902.10502) -- arXiv, 2019-01-30: Proposes a quantum model for stock price probability distributions, claiming to explain technical analysis rules.

### new:quantum_pricing_theory (1 item(s))

- [Quantum-Theoretical Re-interpretation of Pricing Theory](https://arxiv.org/abs/2510.06287) -- arXiv, 2025-10-07: Proposes a quantum-theoretical re-interpretation of pricing theory using observable price transitions and Lindblad semigroups.

### new:quantum_risk_estimation (1 item(s))

- [Exploring Quantum-Enhanced Estimation of Financial Risk Metrics with Quantum RNG](https://arxiv.org/abs/2502.02125) -- arXiv, 2025-02-04: Explores quantum-enhanced Monte Carlo methods using quantum random number generation for estimating VaR and CVaR risk metrics.

### new:random_time_forward_start_options (1 item(s))

- [Random Time Forward Starting Options](https://arxiv.org/abs/1504.03552) -- arXiv, 2015-04-14: Introduces random time forward-starting options and derives arbitrage-free prices under certain conditions.

### new:rank_based_market_models (1 item(s))

- [A Rank-Based Approach to Zipf's Law](https://arxiv.org/abs/1602.08533) -- arXiv, 2016-02-27: Presents rank-based conditions for an Atlas model to follow Zipf's law, providing dynamics of power-law systems.

### new:rank_volatility_stabilized_models (1 item(s))

- [Calibrated rank volatility stabilized models for large equity markets](https://arxiv.org/abs/2403.04674) -- arXiv, 2024-03-07: Introduces rank volatility stabilized models for large equity markets, calibrated to 16 years of CRSP data, with theoretical and empirical analysis.

### new:rational_bubble_theory (1 item(s))

- [Rational Bubbles Attached to Real Assets](https://arxiv.org/abs/2410.17425) -- arXiv, 2024-10-22: A theoretical paper on rational bubbles attached to real assets, discussing conditions for bubble emergence and long-run behavior.

### new:real_estate_crisis (1 item(s))

- [Crisis' Heritage Management - New Business Opportunities Out of the Financial Collapse](https://arxiv.org/abs/1612.08689) -- arXiv, 2016-12-27: Discusses business opportunities in commercial real estate management after financial crises.

### new:relative_arbitrage_theory (1 item(s))

- [Variations on an example of Karatzas and Ruf](https://arxiv.org/abs/1512.02478) -- arXiv, 2015-12-08: Studies markets with positive continuous semimartingales and conditions for relative arbitrage, a theoretical finance piece.

### new:relative_growth_optimal (1 item(s))

- [Relative growth optimal strategies in an asset market game](https://arxiv.org/abs/1908.01171) -- arXiv, 2019-08-03: Proves existence and uniqueness of a relative growth optimal strategy in a game-theoretic asset market model.

### new:repo_convexity (1 item(s))

- [Repo convexity](https://arxiv.org/abs/1905.03316) -- arXiv, 2019-05-08: Explains the basis between repo and bond discounting as a convexity effect and derives expressions for interpolating repo rates.

### new:research_compilation (1 item(s))

- [Research Compendium 2017](https://web.archive.org/web/20210516090657/https://www.factorresearch.com/research-compendium-2017) -- Factor Research, 2017-12-27: A compendium of 34 research papers published on FactorResearch in 2017.

### new:research_review_compilation (1 item(s))

- [Best of Research Review 2017](https://web.archive.org/web/20220525195148/http://www.capitalspectator.com/best-of-research-review-2017/) -- Capital Spectator, 2017-12-30: A review of five economic and financial research papers from 2017.

### new:return_distribution_model (1 item(s))

- [An explanation for the distribution characteristics of stock returns](https://arxiv.org/abs/2312.02472) -- arXiv, 2023-12-05: Proposes a model explaining non-normal stock return distributions via market overreaction or underreaction to information.

### new:return_distribution_modeling (1 item(s))

- [Characterizing asymmetric and bimodal long-term financial return distributions through quantum walks](https://arxiv.org/abs/2505.13019) -- arXiv, 2025-05-19: A study using quantum walks to model asymmetric and bimodal long-term return distributions.

### new:risk_estimation (1 item(s))

- [Optimal nonparametric estimation of the expected shortfall risk](https://arxiv.org/abs/2405.00357) -- arXiv, 2024-05-01: Proposes a novel nonparametric estimator for expected shortfall with optimal statistical properties for heavy-tailed distributions.

### new:risk_measure (2 item(s))

- [Semi-parametric Realized Nonlinear Conditional Autoregressive Expectile and Expected Shortfall](https://arxiv.org/abs/1906.09961) -- arXiv, 2019-06-21: Develops a semi-parametric realized nonlinear conditional autoregressive expectile and expected shortfall model for VaR and ES forecasting.
- [Lambda Expected Shortfall](https://arxiv.org/abs/2512.23139) -- arXiv, 2025-12-29: Introduces Lambda Expected Shortfall as a generalization of ES, a theoretical risk measure with no empirical trading application.

### new:risk_measure_adjusted_es (1 item(s))

- [Adjusted Expected Shortfall](https://arxiv.org/abs/2007.08829) -- arXiv, 2020-07-17: Introduces a class of convex risk measures refining Expected Shortfall by controlling tail losses at multiple probability levels.

### new:risk_measure_dispersion (1 item(s))

- [Tail Structure and the Ordering of the Standard Deviation and Gini Mean Difference](https://arxiv.org/abs/2601.12414) -- arXiv, 2026-01-18: A theoretical paper on the ordering of standard deviation and Gini mean difference based on tail behavior.

### new:risk_measure_elicitability (1 item(s))

- [Elicitability of Return Risk Measures](https://arxiv.org/abs/2302.13070) -- arXiv, 2023-02-25: Analyzes the elicitability properties of return risk measures, providing dual representations and axiomatic characterizations, but no empirical application.

### new:risk_measure_expectile (1 item(s))

- [Relative Bound and Asymptotic Comparison of Expectile with Respect to Expected Shortfall](https://arxiv.org/abs/1906.09729) -- arXiv, 2019-06-24: Theoretical study of the relationship between expectile and expected shortfall as tail risk measures.

### new:risk_measure_framework (3 item(s))

- [Fair Volatility: A Framework for Reconceptualizing Financial Risk](https://arxiv.org/abs/2509.18837) -- arXiv, 2025-09-23: A theoretical framework proposing a new volatility measure to better capture financial risk.
- [Divergence Based Quadrangle and Applications](https://arxiv.org/abs/2306.16525) -- arXiv, 2023-06-28: Introduces a novel framework for risk assessment and decision-making under uncertainty, extending the traditional Risk Quadrangle with phi-divergence.
- [Expectile Quadrangle and Applications](https://arxiv.org/abs/2306.16351) -- arXiv, 2023-06-28: Explores the expectile risk measure within the Fundamental Risk Quadrangle theory, connecting it to error, regret, risk, and deviation functions.

### new:risk_measure_learning (1 item(s))

- [Statistical Learning of Value-at-Risk and Expected Shortfall](https://arxiv.org/abs/2209.06476) -- arXiv, 2022-09-14: Develops a non-asymptotic convergence analysis for learning conditional VaR and ES using neural networks, with a Monte Carlo procedure to estimate distances to ground truth.

### new:risk_sharing_theory (1 item(s))

- [A General Theory of Risk Sharing](https://arxiv.org/abs/2505.19276) -- arXiv, 2025-05-25: Introduces a general theory of risk sharing with a continuum of agents and heterogeneous risk preferences, deriving dual representations and acceptance set characterizations.

### new:robust_arbitrage (1 item(s))

- [Distributionally Robust Profit Opportunities](https://arxiv.org/abs/2006.11279) -- arXiv, 2020-06-18: A theoretical paper on distributionally robust profit opportunities in financial markets, applicable to US equities but not a specific strategy.

### new:robust_arbitrage_conditions (1 item(s))

- [Robust Arbitrage Conditions for Financial Markets](https://arxiv.org/abs/2004.09432) -- arXiv, 2020-04-20: This paper derives robust arbitrage conditions under distributional uncertainty using Wasserstein distance, introducing a statistical arbitrage relaxation.

### new:robust_control_bsde (1 item(s))

- [Robust control problems of BSDEs coupled with value functions](https://arxiv.org/abs/2208.10735) -- arXiv, 2022-08-23: Develops robust control theory for BSDEs with ambiguity and applies it to optimal investment problems.

### new:robust_derivative_pricing (1 item(s))

- [Pathwise super-replication via Vovk's outer measure](https://arxiv.org/abs/1504.03644) -- arXiv, 2015-04-14: Establishes a model-independent super-replication theorem for derivatives using Vovk's outer measure.

### new:robust_forward_preferences (1 item(s))

- [Optimal investment and consumption with forward preferences and uncertain parameters](https://arxiv.org/abs/1807.01186) -- arXiv, 2018-07-03: This paper studies robust forward investment and consumption preferences in an incomplete market with portfolio constraints.

### new:robust_hedging (2 item(s))

- [The robust superreplication problem: a dynamic approach](https://arxiv.org/abs/1812.11201) -- arXiv, 2018-12-28: Develops a dynamic programming approach for robust superreplication and optimal investment under model uncertainty.
- [Efficient hedging under ambiguity in continuous time](https://arxiv.org/abs/1812.10876) -- arXiv, 2018-12-28: Derives duality results for efficient hedging with acceptable shortfall risk in continuous-time model uncertainty.

### new:robust_utility_maximization (1 item(s))

- [Duality Theory for Robust Utility Maximisation](https://arxiv.org/abs/2007.08376) -- arXiv, 2020-07-16: Presents a duality theory for robust utility maximisation in continuous time with bipolar relations.

### new:robust_utility_optimization (1 item(s))

- [Robust Utility Maximization with Drift and Volatility Uncertainty](https://arxiv.org/abs/1909.05335) -- arXiv, 2019-09-11: Provides explicit solutions for robust utility maximization under drift and volatility uncertainty in a complete market.

### new:rough_volatility_model (1 item(s))

- [Small-time, large-time and $H\to 0$ asymptotics for the Rough Heston model](https://arxiv.org/abs/1906.09034) -- arXiv, 2019-06-21: Analyzes asymptotic behavior of the Rough Heston model for option pricing and smile dynamics.

### new:rough_volatility_modeling (1 item(s))

- [Multiscaling in the Rough Bergomi Model: A Tale of Tails](https://arxiv.org/abs/2601.11305) -- arXiv, 2026-01-16: A theoretical study of multiscaling in the rough Bergomi model and its implications for risk and option pricing.

### new:rough_volatility_regularity (1 item(s))

- [A regularity structure for rough volatility](https://arxiv.org/abs/1710.07481) -- arXiv, 2017-10-20: Shows that Hairer's regularity structures can be applied to rough volatility models, capturing stylized facts of the implied volatility surface.

### new:ruin_probability_insurance (1 item(s))

- [Ruin probabilities for two collaborating insurance companies](https://arxiv.org/abs/1804.06598) -- arXiv, 2018-04-18: Derives ruin probability formulas for two collaborating insurance companies using Lévy processes.

### new:scenario_generator_calibration (1 item(s))

- [Consistent Calibration of Economic Scenario Generators: The Case for Conditional Simulation](https://arxiv.org/abs/2004.09042) -- arXiv, 2020-04-20: This paper introduces a framework for consistently calibrating economic scenario generators to forward information for risk management and asset allocation.

### new:share_repurchase_hedging (1 item(s))

- [Optimal strategy and deep hedging for share repurchase programs](https://arxiv.org/abs/2601.18686) -- arXiv, 2026-01-26: Develops a machine-learning framework for hedging share repurchase programs.

### new:short_selling_theory (1 item(s))

- [Shorting in Speculative Markets](https://arxiv.org/abs/1705.05882) -- arXiv, 2017-05-16: A theoretical model of shorting in speculative markets with heterogeneous beliefs and costs-of-carry.

### new:short_term_risk_indices (1 item(s))

- [Short-Term Investments and Indices of Risk](https://arxiv.org/abs/2005.06576) -- arXiv, 2020-05-13: Theoretical study of risk indices for short-term investments in risky assets with continuous returns.

### new:signed_optimal_transport (1 item(s))

- [Conservation of Short-term Flows: Signed Optimal Transport](https://arxiv.org/abs/2608.17363) -- arXiv, 2026-08-18: A theoretical framework for signed optimal transport with applications to flow conservation.

### new:sofr_term_structure (1 item(s))

- [Statistical modeling of SOFR term structure](https://arxiv.org/abs/2508.02691) -- arXiv, 2025-07-23: Develops a statistical term structure model for SOFR derivatives, incorporating macroeconomic factors and jumps.

### new:statistical_economics_theory (1 item(s))

- [Stock market's physical properties description based on Stokes law](https://arxiv.org/abs/2103.00721) -- arXiv, 2021-03-01: Describes stock market behavior as a physical fluid system using Stokes law.

### new:statistical_finance_theory (1 item(s))

- [Statistical mechanics and Bayesian Inference addressed to the Osborne Paradox](https://arxiv.org/abs/2103.00788) -- arXiv, 2021-03-01: Applies statistical mechanics and Bayesian inference to explain the Osborne Paradox in stock market motion.

### new:stochastic_control_numerics (1 item(s))

- [$ε$-Monotone Fourier Methods for Optimal Stochastic Control in Finance](https://arxiv.org/abs/1710.08450) -- arXiv, 2017-10-23: Develops epsilon-monotone Fourier methods for solving optimal stochastic control problems in finance with discrete-time controls.

### new:stochastic_control_simulation (1 item(s))

- [A Backward Simulation Method for Stochastic Optimal Control Problems](https://arxiv.org/abs/1901.06715) -- arXiv, 2019-01-20: Generalizes a least-squares Monte Carlo algorithm for solving stochastic optimal control problems, applicable to financial decision-making.

### new:stochastic_dominance_framework (1 item(s))

- [Geometric Formalization of First-Order Stochastic Dominance in $N$ Dimensions: A Tractable Path to Multi-Dimensional Economic Decision Analysis](https://arxiv.org/abs/2505.12840) -- arXiv, 2025-05-19: A geometric framework for multi-dimensional first-order stochastic dominance formalized in Lean 4.

### new:stochastic_dominance_orders (1 item(s))

- [Distorted stochastic dominance: a generalized family of stochastic orders](https://arxiv.org/abs/1909.04767) -- arXiv, 2019-09-10: Studies a generalized family of stochastic orders based on distortion functions for representing risk preferences.

### new:stochastic_path_probability (1 item(s))

- [Path probability of stochastic motion: A functional approach](https://arxiv.org/abs/1602.04363) -- arXiv, 2016-02-13: Derives a general formula for path probability distributions of stochastic motion and applies it to stock price dynamics.

### new:stochastic_portfolio_theory (2 item(s))

- [Random concave functions](https://arxiv.org/abs/1910.13668) -- arXiv, 2019-10-30: Constructs probability measures on spaces of concave functions for stochastic portfolio theory applications.
- [Topics in Stochastic Portfolio Theory](https://arxiv.org/abs/1504.02988) -- arXiv, 2015-04-12: Provides an overview of Stochastic Portfolio Theory, an updated survey of the field.

### new:stochastic_process_modeling (1 item(s))

- [On Time-subordinated Brownian Motion Processes for Financial Markets](https://arxiv.org/abs/2510.14108) -- arXiv, 2025-10-15: Theoretical development of time-subordinated Brownian motion models for financial markets.

### new:stochastic_process_theory (1 item(s))

- [Common Decomposition of Correlated Brownian Motions and its Financial Applications](https://arxiv.org/abs/1907.03295) -- arXiv, 2019-07-07: Develops a theory for decomposing correlated Brownian motions with potential financial applications.

### new:stock_loan_redemption (1 item(s))

- [Optimal redeeming strategy of stock loans under drift uncertainty](https://arxiv.org/abs/1901.06680) -- arXiv, 2019-01-20: Analyzes optimal redeeming strategies for stock loans under drift uncertainty using Hamilton-Jacobi-Bellman equations.

### new:stock_network_analysis (1 item(s))

- [Nonlinearity in stock networks](https://arxiv.org/abs/1804.10264) -- arXiv, 2018-04-26: A study characterizing nonlinearity in stock networks using mutual information, potentially useful for signal construction.

### new:stock_price_time_function (1 item(s))

- [The Time Function of Stock Price](https://arxiv.org/abs/2008.11806) -- arXiv, 2020-08-11: Proposes a mathematical model of stock price as integral white noise to derive its time function and predictability.

### new:structured_products_ira (1 item(s))

- [A Modeling Approach of Return and Volatility of Structured Investment Products with Caps and Floors](https://arxiv.org/abs/2311.06282) -- arXiv, 2023-10-28: Proposes a parametric model for the return and volatility of Puerto Rico stock market IRAs, structured products with caps and floors.

### new:superhedging_duality_frictions (1 item(s))

- [On the quasi-sure superhedging duality with frictions](https://arxiv.org/abs/1809.07516) -- arXiv, 2018-09-20: Proves superhedging duality for discrete-time markets with transaction costs under model uncertainty.

### new:supply_demand_wavefunction (1 item(s))

- [Market Dynamics. On Supply and Demand Concepts](https://arxiv.org/abs/1602.04423) -- arXiv, 2016-02-14: Proposes a theoretical framework where market supply and demand are always matched, with price dynamics described by a wavefunction probability distribution.

### new:supply_network_risk (1 item(s))

- [Quantifying firm-level economic systemic risk from nation-wide supply networks](https://arxiv.org/abs/2104.07260) -- arXiv, 2021-04-15: Quantifies firm-level economic systemic risk from nation-wide supply networks, using fine-grained data.

### new:symmetry_finance (1 item(s))

- [Symmetry and financial Markets](https://arxiv.org/abs/2007.08475) -- arXiv, 2020-07-16: Explores the concept of symmetry in financial markets, particularly in decision-making and game theory.

### new:systemic_risk_contagion (1 item(s))

- [Financial Contagion Networks as Annealing-Ready Ising Systems Cascades, Bailout Optimization, and Susceptibility](https://arxiv.org/abs/2609.17415) -- arXiv, 2026-07-09: Develops a QUBO/Ising optimization framework for financial contagion cascades and bailout optimization.

### new:systemic_risk_measures (1 item(s))

- [Making heads or tails of systemic risk measures](https://arxiv.org/abs/2206.02582) -- arXiv, 2022-06-06: Theoretical paper representing systemic risk measures in terms of univariate risk measures and copulas, with a new CoES estimator.

### new:systemic_risk_modeling (1 item(s))

- [Systemic Risk and Heterogeneous Mean Field Type Interbank Network](https://arxiv.org/abs/1907.03082) -- arXiv, 2019-07-06: Models systemic risk in heterogeneous interbank networks using mean field type coupled diffusions.

### new:systemic_risk_network (1 item(s))

- [How connected is too connected? Impact of network topology on systemic risk and collapse of complex economic systems](https://arxiv.org/abs/1912.09814) -- arXiv, 2019-12-20: Proposes a model to study how network connectivity affects systemic risk and collapse in economic systems.

### new:tail_dependence_measures (1 item(s))

- [Comparing and quantifying tail dependence](https://arxiv.org/abs/2208.10319) -- arXiv, 2022-08-22: Introduces a new stochastic order for tail dependence and applies it to S&P 500 stocks and indices.

### new:tail_risk_measure (1 item(s))

- [Measuring Tail Risks](https://arxiv.org/abs/2209.07092) -- arXiv, 2022-09-15: Proposes a new tail risk measure (MPMR) based on the most probable maximum size of risk events, derived analytically for several distributions.

### new:tax_aware_trading (1 item(s))

- [Foundations for Wash Sales](https://arxiv.org/abs/1511.03704) -- arXiv, 2015-11-11: A theoretical paper modeling wash sale rules and their tax implications, relevant to tax-aware trading strategies.

### new:tda_turbulence_index (1 item(s))

- [A persistent-homology-based turbulence index & some applications of TDA on financial markets](https://arxiv.org/abs/2203.05603) -- arXiv, 2022-03-10: Proposes a turbulence index based on persistent homology and reviews TDA applications in financial markets.

### new:tech_ranking_investment (1 item(s))

- [TechRank](https://arxiv.org/abs/2210.07824) -- arXiv, 2022-10-14: Presents TechRank, a recursive algorithm to rank companies and technologies for investor portfolio design.

### new:temporal_clustering (1 item(s))

- [A Temporal Clustering Function](https://web.archive.org/web/20201101005715/http://dekalogblog.blogspot.com/2020/10/a-temporal-clustering-function.html) -- Dekalog Blog, 2020-10-21: Describes a temporal clustering function, possibly for market cycle analysis, but details are sparse.

### new:term_structure_modeling (2 item(s))

- [An alternative approach on the existence of affine realizations for HJM term structure models](https://arxiv.org/abs/1907.03256) -- arXiv, 2019-07-07: Proposes an alternative approach for affine realizations in HJM interest rate models.
- [Existence of affine realizations for Lévy term structure models](https://arxiv.org/abs/1907.02363) -- arXiv, 2019-07-04: Investigates affine realizations for term structure models driven by Lévy processes.

### new:time_inconsistent_stopping (1 item(s))

- [Failure of Smooth Pasting Principle and Nonexistence of Equilibrium Stopping Rules under Time-Inconsistency](https://arxiv.org/abs/1807.01785) -- arXiv, 2018-07-04: This paper analyzes time-inconsistent optimal stopping problems, showing the smooth pasting principle may fail under non-constant time preference rates.

### new:time_scale_analysis (1 item(s))

- [Identification of short-term and long-term time scales in stock markets and effect of structural break](https://arxiv.org/abs/1907.03009) -- arXiv, 2019-07-01: Analyzes short-term and long-term time scales in stock markets using empirical mode decomposition and Hurst exponent, with structural break identification.

### new:time_series_analysis (1 item(s))

- [Multifractal Flexibly Detrended Fluctuation Analysis](https://arxiv.org/abs/1510.05115) -- arXiv, 2015-10-17: Proposes a multifractal detrended fluctuation analysis variant with flexible polynomial detrending degree.

### new:time_series_clustering (1 item(s))

- [On clustering financial time series: a need for distances between dependent random variables](https://arxiv.org/abs/1603.07822) -- arXiv, 2016-03-25: Discusses clustering of financial time series, emphasizing the need for distances between dependent random variables.

### new:time_series_extrema (1 item(s))

- [Nonparametric Extrema Analysis in Time Series for Envelope Extraction, Peak Detection and Clustering](https://arxiv.org/abs/2109.02082) -- arXiv, 2021-09-05: Proposes a nonparametric method for envelope extraction, peak detection, and clustering in time series, with potential financial applications.

### new:time_series_regime_detection (1 item(s))

- [The use of scaling properties to detect relevant changes in financial time series: a new visual warning tool](https://arxiv.org/abs/2010.08890) -- arXiv, 2020-10-18: Introduces a visual tool using time-dependent Hurst exponents to detect critical changes in financial time series.

### new:timescale_separation (1 item(s))

- [Fast Times, Slow Times: Timescale Separation in Financial Timeseries Data](https://arxiv.org/abs/2601.11201) -- arXiv, 2026-01-16: A method for separating fast and slow components in financial time series using variance and tail stationarity criteria.

### new:topological_data_analysis_bubbles (1 item(s))

- [Why Topological Data Analysis Detects Financial Bubbles?](https://arxiv.org/abs/2304.06877) -- arXiv, 2023-04-14: A heuristic argument that Topological Data Analysis can detect financial bubbles via the LPPLS model.

### new:topological_price_analysis (1 item(s))

- [A Topological Approach to Scaling in Financial Data](https://arxiv.org/abs/1710.08860) -- arXiv, 2017-10-24: Introduces a topological method to decompose financial price series into total variation components to characterize scaling and fractal properties.

### new:topological_risk_measures (1 item(s))

- [Beyond VaR and CVaR: Topological Risk Measures in Financial Markets](https://arxiv.org/abs/2310.14604) -- arXiv, 2023-10-23: Introduces a topological risk measure (TVaRD) for equities portfolios using cohomology groups, tested on Apple, Microsoft, and Google daily returns. -- reported: Preliminary results, no numbers given

### new:tradable_signature_hedging (1 item(s))

- [Tradable Itô Signatures: A Model-Free, Interpretable Framework for Dynamic Hedging](https://arxiv.org/abs/2608.18120) -- arXiv, 2026-07-14: Proposes a framework for dynamic hedging using Itô signatures, where signature components are tradable via self-financing strategies.

### new:transaction_cost_arbitrage (1 item(s))

- [Fundamental Theorem of Asset Pricing under fixed and proportional transaction costs](https://arxiv.org/abs/1905.01859) -- arXiv, 2019-05-06: Extends the Fundamental Theorem of Asset Pricing to markets with fixed and proportional transaction costs, linking no-arbitrage to the existence of certain martingale measures.

### new:transaction_cost_equilibrium (1 item(s))

- [Asset Pricing with General Transaction Costs: Theory and Numerics](https://arxiv.org/abs/1905.05027) -- arXiv, 2019-05-13: Theoretical paper on risk-sharing equilibria with general transaction costs, showing equilibrium returns mean-revert around frictionless counterparts.

### new:transaction_cost_model (1 item(s))

- [Semimartingale price systems in models with transaction costs beyond efficient friction](https://arxiv.org/abs/2001.03190) -- arXiv, 2020-01-09: A theoretical paper unifying price models with and without transaction costs, focusing on no-arbitrage conditions.

### new:trend_symmetry_analysis (1 item(s))

- [A multi-scale symmetry analysis of uninterrupted trends returns of daily financial indices](https://arxiv.org/abs/1908.11204) -- arXiv, 2019-08-27: Presents a statistical symmetry analysis of daily financial index trends, potentially useful for market timing or regime detection.

### new:utility_pricing_illiquidity (1 item(s))

- [Efficient approximations for utility-based pricing](https://arxiv.org/abs/2105.08804) -- arXiv, 2021-05-18: A theoretical paper proposing efficient approximations for utility-based pricing under illiquidity, using the Lambert function.

### new:value_tracking_hypothesis (1 item(s))

- [Dynamics of Value-Tracking in Financial Markets](https://arxiv.org/abs/1903.09898) -- arXiv, 2019-03-23: Proposes a value-tracking hypothesis for market prices and a model showing how tracking errors can arise, but provides no empirical test.

### new:volatility_clustering_models (1 item(s))

- [Analysing Models for Volatility Clustering with Subordinated Processes: VGSA and Beyond](https://arxiv.org/abs/2507.17431) -- arXiv, 2025-07-23: Explores time-changed stochastic processes for modeling volatility clustering, extending classical jump frameworks.

### new:volatility_modeling (1 item(s))

- [The Zumbach effect under rough Heston](https://arxiv.org/abs/1809.02098) -- arXiv, 2018-09-06: Provides explicit computations of the Zumbach effect under rough Heston, showing consistency with empirical estimates.

### new:volatility_return_interval_model (1 item(s))

- [Stochastic model of financial markets reproducing scaling and memory in volatility return intervals](https://arxiv.org/abs/1507.05203) -- arXiv, 2015-07-18: A stochastic agent-based model reproduces scaling and memory in volatility return intervals for NYSE and FOREX markets.

### new:volume_price_distribution_modeling (1 item(s))

- [Stochastic modelling of non-stationary financial assets](https://arxiv.org/abs/1705.01145) -- arXiv, 2017-04-30: Models non-stationary volume-price distributions with log-normal parameters and Langevin equations.

### new:wavelet_signal_analysis (1 item(s))

- [Wavelet Analysis for Time Series Financial Signals via Element Analysis](https://arxiv.org/abs/2301.13255) -- arXiv, 2023-01-30: Proposes element analysis as a wavelet-based method to analyze financial time series signals.

### new:xva_pricing (1 item(s))

- [Approximate XVA for European claims](https://arxiv.org/abs/2007.07701) -- arXiv, 2020-07-15: Computes approximate XVA for European claims with default, funding, and collateralization using BSDEs.

## Totals

- items pulled: 26645
- items classified: 18350
- relevant: 9926
- parse errors: 240
- calls: 1835
- tokens: 8073906
