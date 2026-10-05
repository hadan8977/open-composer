source: https://www.garp.org/hubfs/Whitepapers/a1Z1W0000054xSXUAY.pdf
fetched_utc: 2026-10-04T18:43:15Z
bytes_raw: 377589

Risk-Managed Momentum:
                                     the Effect of Leverage Constraints

                                                       Federico Nucera1




Abstract

Risk-managed momentum allows investors to increase the Sharpe ratio of the momentum strategy and to reduce momentum
crashes. Yet, the improvement in the performance comes at the price of often assuming a levered position on plain momentum.
I show that leverage-constrained investors benefit from a risk-managed momentum strategy that scales the momentum
exposure with the past realized positive semi-variance of momentum returns rather than with the past realized variance.

Keywords:      Momentum, Variance decomposition, Performance

JEL: C58, G11, G12, G17




   1 LUISS Guido Carli University, Viale Romania, 32, 00197 Rome, Italy, Email: fnucera@luiss.it, Phone number: +390685795754.

I would like to thank Michael W. Brandt, Marianna Brunetti, Fabrizio Fiocchi, Giorgio Valente and Bjorn Uhl for helpful suggestions
and comments.


Preprint submitted to Elsevier                                                                                       July 25, 2017

                          Electronic copy available at: https://ssrn.com/abstract=3008530
1. Introduction


   Momentum is a celebrated investment strategy that invests in past winners and short-sells past losers. Generally,
momentum looks very attractive to investors because it provides them with a higher Sharpe ratio than other standard
investment factors (e.g., market, value and size) and, being negatively correlated with the market and the value
factors, it offers diversification benefits in a portfolio-choice problem. However, it is also well-known that the
attractiveness of momentum is mitigated by the big losses to which investors have been historically exposed due to
momentum crashes.

   By exploiting the predictability of momentum risk, a recent body of academic research (e.g., Barroso and Santa-
Clara, 2015, Moreira and Muir, 2017), has proposed risk-management techniques to reduce the shortcomings of
momentum. In particular, Barroso and Santa-Clara (2015) show that it is possible to improve dramatically the
Sharpe ratio of the momentum strategy and to reduce the related crash-risk by means of a simple scaling factor.
The scaling factor exploits the information contained in the forecast of the variance of momentum returns, which is
a proxy for momentum risk, and it can be used by the investors to tactically reduce their exposure to momentum
when they anticipate a momentum crash.

   The Barroso and Santa-Clara’s (2015) scaling factor operates as a weight applied to both the long and the short
leg of the momentum strategy and often takes a value lower than one. Yet, in some periods, it can take a value
higher than one. If this is the case, risk-managed momentum might face some limits in its practical implementation
as some investors may find it difficult to be overexposed to momentum. This is a serious concern because, as pointed
out by Asness et al. (2012), investors are often either leverage-constrained or leverage-adverse. Hence, in this paper,
I focus on the effects that leverage constraints have on the performance of risk-managed momentum strategies when
leverage is defined in terms of exposure to the plain momentum strategy.

   In particular, along with the benchmark risk-managed strategy proposed by Barroso and Santa-Clara (2015), I
consider two alternative risk-managed strategies. These strategies are based on the forecast of the negative semi-
variance and on the forecast of the positive semi-variance of momentum returns, respectively. In accordance with
Barroso and Santa-Clara (2015), a risk-managed momentum strategy that scales momentum returns on the basis
of the forecasted variance substantially improves upon the performance of plain momentum. However, when the
leverage constraint binds, I find that the strategy which scales momentum returns with a forecast of the positive
semi-variance produces higher Sharpe and appraisal ratios.


2. Data

   The empirical analysis is based on daily and monthly momentum decile portfolio returns available on the Kenneth
French’s website.2 Individual firms are value weighted in each decile. The daily returns are from November 3rd 1926
to December 30th 2016, and the monthly returns are from January 1927 to December 2016. Following a common

   2 http://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html




                                                          2

                       Electronic copy available at: https://ssrn.com/abstract=3008530
approach in the literature (e.g., Barroso and Santa-Clara, 2015, Daniel and Moskowitz, 2016), the building block
of my analysis is the standard winners-minus-losers (WML) momentum strategy which takes a long position in the
highest momentum decile portfolio (winners) and short-sells the lowest momentum decile (losers). From now on, I
refer to this trading strategy as plain momentum.


3. Methodology

   Following Barroso and Santa-Clara (2015), I first construct a risk-managed momentum strategy which exploits
the information contained in the forecasted variance of plain momentum returns. The forecasted variance represents
an estimate of momentum risk and is computed as the realized variance of plain momentum returns observed in
the previous six months, i.e.,
                                                           125
                                                           X
                                            2                     2
                                          σ̂W M L,t = 21         rW M L,dt−j /126                               (1)
                                                           j=0

where rW M L,d are daily returns of plain momentum.

   The forecasted variance at the end of month t − 1 is used to scale the monthly returns of plain momentum
obtained in month t, i.e.,
                                               var        var
                                              rW M L,t = wt · rW M L,t                                          (2)

       var
where rW M L,t defines the monthly returns of the risk-managed momentum strategy, rW M L,t are the monthly returns

of plain momentum, wtV AR is a scaling factor defined as

                                                                 c
                                                 wtvar =      2                                                 (3)
                                                            σ̂W M L,t−1


and c is a constant representing a target variance of 1.44%. This target variance corresponds to an annualized
volatility of 12% as in Barroso and Santa-Clara (2015). It is worth recalling that the value of c does not have
any impact on the Sharpe ratio of the scaled momentum strategy. Intuitively, the scaling factor represents a time-
varying weight in the long and short momentum decile portfolios that is different from one. By applying this weight
at the beginning of month t, the investor just increases (when wtvar > 1) or decreases (wtvar < 1) her momentum
exposure on the basis of a variance forecast made in month t − 1.

   Next, I construct two alternative risk-managed momentum strategies where the weights depend on a simple
                                           2
decomposition of the forecasted variance σ̂W M L,t . In particular, the variance forecast is decomposed as:


                                             2           2,−         2,+
                                           σ̂W M L,t = σ̂W M L,t + σ̂W M L,t                                    (4)


where
                                                           125
                                                           X
                                            2,−                 2,−
                                          σ̂W M L,t = 21       rW M L,dt−j /126                                 (5)
                                                           j=0




                                                             3

                       Electronic copy available at: https://ssrn.com/abstract=3008530
is the forecasted negative semi-variance based on negative plain momentum returns, while

                                                           125
                                                           X
                                            2,+                 2,+
                                          σ̂W M L,t = 21       rW M L,dt−j /126                                   (6)
                                                           j=0


is the forecasted positive semi-variance based on positive plain momentum returns.

   The intuition of using the forecasted semi-variances of momentum returns to adjust the exposure to momentum
is based on the possibility that momentum risk could be more predictable if momentum crashes systematically arise
following periods in which plain momentum returns have been persistently negative or positive. As a consequence,
I use the decomposition of the forecasted variance to construct the following weights:

                                                                 c−
                                                  wtvar− =     2,−                                                (7)
                                                             σ̂W M L,t−1


   and

                                                                 c+
                                                  wtvar+ =     2,+                                                (8)
                                                             σ̂W M L,t−1

   I set the negative (c− ) and the positive (c+ ) target semi-variances such as their weighted sum is equal to c. The
weights are given by the proportions of negative (53% of the observations) and positive (47% of the observations)
daily returns of plain momentum observed over the full-sample period. Hence, c− = c × 0.53 = 0.76% and
c+ = c × 0.47 = 0.68%.

   The monthly returns of these risk-managed momentum strategies are computed as:

                                                 var−       var−
                                                rW M Lt = w t    · rW M L,t                                       (9)


   and


                                                 var+      var+
                                                rW M Lt = wt    · rW M L,t                                       (10)


4. Results

   Figure 1 shows the evolution over time of the set of weights based on the forecasted variance (wtvar ), the
forecasted negative semi-variance (wtvar− ) and the forecasted positive semi-variance (wtvar+ ). In some periods, the
application of these weights would have forced the investor to take a sizable exposure to both the long and the short
leg of the plain momentum strategy. This holds true for the weights based on the forecasted negative semi-variance,
which look extremely volatile over the full-sample period, but also for the weights based on the forecasted variance
and on the forecasted positive semi-variance.

   Table 1 shows the weights’ average and the weights’ standard deviation along with selected percentiles of their
distribution for three different levels of leverage (exposure), namely: i) full leverage (exposure to plain momentum


                                                             4
can vary freely); ii) moderate leverage (exposure to plain momentum has to be ≤ 1.5); iii) no leverage (exposure
to plain momentum has be to ≤ 1). The descriptive statistics are based on the full-sample period. Although the
averages of the weights are lower than one, Table 1 confirms that risk-managed momentum comes at the price of
taking frequently a levered position on plain momentum. In particular, for all the strategies considered, a scaling
factor bigger or equal to one was required in more than 25% of the observations. As argued in the Introduction,
some investor could either be leverage-averse or leverage-constrained and the exposure required to implement the
risk-managed momentum strategies might not always be feasible despite this will certainly contribute to improve
the performance of plain momentum.

   The benefits of risk-managed momentum are evident from the inspection of Table 2 which compares the perfor-
mance of the three risk-managed momentum strategies. Confirming the findings in Barroso and Santa-Clara (2015)
and in Moreira and Muir (2017), Table 2 shows that when the leverage constraint does not bind, a risk-managed
momentum based on the forecasted variance outperforms plain momentum in terms of Sharpe ratio (1.08 vs 0.52).
Moreover, this strategy also exhibits a higher Sharpe ratio than the risk-managed momentum strategies based on
the forecasted semi-variances. However, the picture changes when leverage constraint binds. Indeed, in such a case,
the risk-managed momentum strategy based on the forecasted positive semi-variance outperforms the other two
risk-managed strategies both in terms of Sharpe and Appraisal ratios. In particular, when the investor can take
only limited leverage, the Sharpe ratio of the strategy based on the forecasted positive variance is slightly higher
than the Sharpe ratio of the strategy based on the forecasted variance (1.10 vs 1.08). The performance improvement
is more evident when the investor is fully leverage-constrained (1.07 vs 1.02). Table 3 confirms these findings also
for a shorter and more recent sample (from 1986 to 2016).




                                                         5
References

Asness, C. S., Frazzini, A., Pedersen, L. H., 2012. Leverage aversion and risk parity. Financial Analyst Journal 68, 47–59.

Barroso, P., Santa-Clara, P., 2015. Momentum has its moments. Journal of Financial Economics 116, 111–120.

Daniel, K., Moskowitz, T. J., 2016. Momentum crashes. Journal of Financial Economics 122, 221–247.

Moreira, A., Muir, T., 2017. Volatility-managed portfolios. Journal of Finance, forthcoming.

Treynor, J. L., Black, F., 1973. How to use security analysis to improve portfolio selection. Journal of Business 46, 66–86.




                                                              6
Figures:


                                                              Figure 1: Weights
The figure shows wtvar (black solid line), wtvar− (red dashed line) and wtvar+ (blue dotted line) for the period 1927:04-2016:12


                   10
                                                                                                                           wvar
                                                                                                                           wvar −
                    9
                                                                                                                           wvar +


                    8



                    7



                    6



                    5



                    4



                    3



                    2



                    1



                    0
                   1927        1937        1947        1957        1967       1977        1987        1997        2007            2017




                                                                          7
Tables:



                                      Table 1: Weights (descriptive statistics and percentiles)
This table presents the average (Average), the standard deviation (std) and the percentiles 50th (P50), 75th (P75), 90th (P90) and 99th (P99)
of the distribution of the weights associated to three risk-managed momentum strategies, namely: i) a risk-managed momentum that uses the
realized variance of the previous six months to scale the exposure to momentum (W M Lvar ), ii) a risk-managed momentum that uses the realized
negative semi-variance of the previous six months to scale the exposure to momentum (W M Lvar− ), iii) a risk-managed momentum that uses
the realized positive semi-variance of the previous six months to scale the exposure to momentum (W M Lvar+ ). Three leverage regimes are
considered: i) Full leverage (Full Lev), ii) leverage ≤ 1.5 (Lev 1.5), iii) no leverage (No Lev).
                                WMLvar                                   WMLvar−                                    WMLvar+
                   Full Lev     Lev 1.5       No Lev        Full Lev     Lev 1.5        No Lev         Full Lev     Lev 1.5        No Lev
      Average        0.93         0.78         0.65           1.16          0.83         0.67            0.85          0.74         0.63
      std            0.79         0.50         0.34           1.15          0.52         0.34            0.74          0.48         0.33
      P50            0.71         0.71         0.71           0.78          0.78         0.78            0.66          0.66         0.66
      P75            1.24         1.24         1.00           1.67          1.50         1.00            1.14          1.14         1.00
      P90            2.05         1.50         1.00           2.75          1.50         1.00            1.81          1.50         1.00
      P99            3.68         1.50         1.00           5.37          1.50         1.00            3.19          1.50         1.00




                                        Table 2: Returns’ descriptive statistics (full-sample)
This table presents descriptive statistics of different strategies based on momentum for the period 1927:04 to 2016:12. The strategies considered
are: i) plain momentum strategy (WML) , ii) a risk-managed momentum strategy that uses the realized variance of the previous six months
to scale the exposure to momentum (W M Lvar ), iii) a risk-managed momentum strategy that uses the realized negative semi-variance of the
previous six months to scale the exposure to momentum (W M Lvar− ), iv) a risk-managed momentum that uses the realized positive semi-
variance of the previous six months to scale the exposure to momentum (W M Lvar+ ). The mean, the standard deviation and the Sharpe ratio
are annualized. The column “Appraisal Ratio ”provides the annualized Treynor and Black (1973) appraisal ratio of the strategy in that row,
relative to the plain momentum strategy. Three leverage regimes are considered: i) Full leverage (Full Lev), ii) leverage ≤ 1.5 (Lev 1.5), iii) no
leverage (No Lev).
                        Maximum          Minimum        Mean       Standard       Kurtusis       Skeweness        Sharpe     Appraisal
                                                                   deviation                                       ratio       ratio
        Full Lev
        WML                   26.16        -77.02        14.11         27.15        17.43           -2.34          0.52
        WMLvar                39.90        -23.33        18.74         17.40         5.95           0.73           1.08         0.94
        WMLvar−               44.54        -58.61        23.63         24.61        10.27           0.23           0.96         0.81
        WMLvar+               35.71        -25.53        16.71         15.55         7.32           0.52           1.07         0.94
        Lev 1.5
        WML                   26.16        -77.02        14.11         27.15        17.43           -2.34          0.52
        WMLvar                22.01        -18.26        15.60         14.50         2.69           0.18           1.08         0.94
        WMLvar−               22.70        -28.01        16.42         16.45         4.35           0.00           1.00         0.85
        WMLvar+               19.76        -18.12        14.75         13.36         2.85           0.14           1.10         0.97
        No Lev
        WML                   26.16        -77.02        14.11         27.15        17.43           -2.34          0.52
        WMLvar                15.13        -15.82        12.37         12.16         2.20           -0.07          1.02         0.87
        WMLvar−               16.06        -18.67        12.53         12.94         2.89           -0.09          0.97         0.82
        WMLvar+               14.67        -12.89        12.17         11.35         1.64           -0.08          1.07         0.94




                                                                        8
                                        Table 3: Returns’ descriptive statistics (1986-2016)
This table presents descriptive statistics of different strategies based on momentum 1986:01 to 2016:12. The strategies considered are: i) plain
momentum strategy (WML) , ii) a risk-managed momentum strategy that uses the realized variance of the previous six months to scale the
exposure to momentum (W M Lvar ), iii) a risk-managed momentum strategy that uses the realized negative semi-variance of the previous six
months to scale the exposure to momentum (W M Lvar− ), iv) a risk-managed momentum that uses the realized positive semi-variance of the
previous six months to scale the exposure to momentum (W M Lvar+ ). The mean, the standard deviation and the Sharpe ratio are annualized.
The column “Appraisal Ratio ”provides the annualized Treynor and Black (1973) appraisal ratio of the strategy in that row, relative to the
plain momentum strategy. Three leverage regimes are considered: i) Full leverage (Full Lev), ii) leverage ≤ 1.5 (Lev 1.5), iii) no leverage (No
Lev).
                        Maximum         Minimum         Mean      Standard       Kurtusis      Skeweness       Sharpe      Appraisal
                                                                  deviation                                     ratio        ratio
        Full Lev
        WML                 26.16          -45.79       12.44        27.36          7.65          -1.46          0.45
        WMLvar              24.55          -11.11       15.54        14.14          4.68          1.25           1.10          1.00
        WMLvar−             37.31          -16.63       20.53        20.13          9.73          2.07           1.02          0.91
        WMLvar+             17.77           -8.08       13.36        11.84          2.87          0.91           1.13          1.03
        Lev 1.5
        WML                 26.16          -45.79       12.44        27.36          7.65          -1.46          0.45
        WMLvar              15.53          -11.11       13.35        12.32          2.63          0.80           1.08          0.98
        WMLvar−             22.70          -15.41       14.45        14.62          4.13          0.82           0.99          0.88
        WMLvar+             15.36           -8.08       12.16        10.88          2.51          0.81           1.12          1.02
        No Lev
        WML                 26.16          -45.79       12.44        27.36          7.65          -1.46          0.45
        WMLvar              15.13          -10.27       10.84        10.83          2.35          0.48           1.00          0.89
        WMLvar−             15.13          -10.27       10.94        11.89          2.26          0.34           0.92          0.80
        WMLvar+             11.35           -8.08       10.34         9.72          1.67           0.47          1.06          0.96




                                                                       9