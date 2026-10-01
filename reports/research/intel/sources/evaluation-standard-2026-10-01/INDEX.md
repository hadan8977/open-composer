# 评判标准 v2 的来源存档（2026-10-01）

本页 2026-10-01 18:17 UTC 由交互会话主审（Opus）写。下表 8 份原文都在本页写成前、同一会话内下载：PDF 在 `pdf/`，文本由 `pdftotext -layout` 转换，同名 `.txt`。sha256 只记前 16 位，完整值可对 `pdf/` 重算。

检索词：
- "Bailey López de Prado The Sharpe Ratio Efficient Frontier probabilistic Sharpe ratio minimum track record length pdf"
- "Harvey Liu 2015 Backtesting Journal of Portfolio Management haircut Sharpe ratio multiple testing pdf"
- "Kaminski Lo When do stop-loss rules stop losses pdf"
- "Lo 2002 The Statistics of Sharpe Ratios Financial Analysts Journal pdf autocorrelation standard error"

DSR、PBO、Magdon-Ismail 三份是从作者主页直接下载的已知地址。

| 文件 | 来源 | sha256 前 16 位 | 关键原话 | 口径和适用边界 |
|---|---|---|---|---|
| `bailey_ldp_2012_sharpe_frontier_psr_mintrl` | davidhbailey.com/dhbpapers/sharpe-frontier.pdf（Journal of Risk 15(2)） | 7a756315dc645e34 | "if a track record is shorter than MinTRL, we do not have enough confidence that the observed [SR] is above the designated threshold" | PSR、最短业绩长度；考虑非正态，假设收益独立同分布 |
| `bailey_ldp_2014_deflated_sharpe` | davidhbailey.com/dhbpapers/deflated-sharpe.pdf（JPM 40(5)） | ca4a1e834a2954b8 | "The Deflated Sharpe Ratio (DSR) corrects for two leading sources of performance inflation: Selection bias under multiple testing and non-Normally distributed returns." | 多重检验下的夏普校正；需要有效试验数和试验间夏普方差 |
| `bailey_borwein_ldp_zhu_pbo` | davidhbailey.com/dhbpapers/backtest-prob.pdf（J. Computational Finance） | d8bfbadaaedb430d | "the probability of backtest overfitting (PBO) is then evaluated as the conditional probability that this strategy underperforms the median OOS while remaining optimal IS" | 组合对称交叉验证；仓库已有实现 `campaign_statistics.cscv_probability_backtest_overfitting` |
| `harvey_liu_2015_backtesting` | people.duke.edu/~charvey/Research/Published_Papers/P120_Backtesting.PDF（JPM 42(1)）；CME 的镜像返回非 PDF | b32ec2e9e08d2450 | "The 50% haircut is only a rule of thumb. Our article's goal is to develop an analytical way to determine the haircut's magnitude." | 按检验次数给夏普打折；与 DSR 思路一致，v2 用 DSR |
| `kaminski_lo_2014_stop_loss` | smallake.kr 镜像（Journal of Financial Markets 18）；MIT 仓库返回的是 HTML | 4b5265a569e0f1be | "These results suggest that stop-loss rules may exploit conditional momentum effects" | 收益接近随机游走时止损降低期望收益；收益有持续性或状态切换时止损可能增值 |
| `lo_2002_statistics_of_sharpe` | traders.studentorg.berkeley.edu 镜像（FAJ 58(4)） | 2042a6992ca93c63 | 独立同分布下 SE(SR) ≈ √((1 + ½SR²)/T)（第 196 行附近） | 夏普的标准误、自相关修正；v2 的短窗口亏损概率按此计算 |
| `magdon_ismail_2004_max_drawdown` | cs.rpi.edu/~magdon/ps/journal/drawdown_journal.pdf（J. Applied Probability 41） | 11180eaaab27d767 | "The asymptotic behavior is logarithmic for µ > 0, linear for µ < 0 and square root for µ = 0." | 布朗运动的最大回撤分布；v2 的前向回撤阈值按模拟分位设定 |
| `twosigma_sharpe_estimation_ci` | twosigma.com/wp-content/uploads/sharpe-tr-1.pdf | 868b2b58045b8efb | 标题 "Sharpe Ratio: Estimation, Confidence Intervals, and Hypothesis Testing" | 业界对夏普点估计、置信区间、假设检验的说明 |

已有存档（不重复下载）：
- Jensen–Kelly–Pedersen 2023 JF：`reports/research/intel/sources/pro-equity-2026-10-01/evidence/10_jensen_kelly_pedersen_replication_crisis_JF2023.txt`。
- 发表后衰减（McLean–Pontiff −58%，JKP −47%）的摘录：`reports/research/intel/pro-equity-evidence-2026-10-01.md`。
- HFR 和 BarclayHedge 市场中性指数：同目录下的 `A_hfr_hfrx_equity_market_neutral.txt`、`A_barclayhedge_equity_market_neutral.txt`。

版权说明：PDF 只作个人研究存档，不外发。
