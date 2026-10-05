source: https://www.lehigh.edu/~xuy219/research/COWY.pdf
fetched_utc: 2026-10-04T18:36:32Z
bytes_raw: 974329

Journal of Financial Economics 138 (2020) 95–117



                                                        Contents lists available at ScienceDirect


                                               Journal of Financial Economics
                                                  journal homepage: www.elsevier.com/locate/jfec




On the performance of volatility-managed portfoliosR
Scott Cederburg a, Michael S. O’Doherty b,∗, Feifei Wang c, Xuemin (Sterling) Yan d
a
  Eller College of Management, University of Arizona, McClelland Hall, Room 315R, Tucson, AZ 85721, USA
b
  University of Missouri, Trulaske College of Business, 401C Cornell Hall, Columbia, MO 65211, United States
c
  Farmer School of Business, Miami University, 2064 FSB, Oxford, OH 45056, USA
d
  College of Business, Lehigh University, 471 Rauch Business Center, Bethlehem, PA 18015, USA




a r t i c l e          i n f o                         a b s t r a c t

Article history:                                       Using a comprehensive set of 103 equity strategies, we analyze the value of volatility-
Received 19 November 2018                              managed portfolios for real-time investors. Volatility-managed portfolios do not system-
Revised 15 March 2019
                                                       atically outperform their corresponding unmanaged portfolios in direct comparisons. Con-
Accepted 17 March 2019
                                                       sistent with Moreira and Muir (2017), volatility-managed portfolios tend to exhibit signif-
Available online 1 May 2020
                                                       icantly positive alphas in spanning regressions. However, the trading strategies implied by
JEL classiﬁcation:                                     these regressions are not implementable in real time, and reasonable out-of-sample ver-
G10                                                    sions generally earn lower certainty equivalent returns and Sharpe ratios than do simple
G11                                                    investments in the original, unmanaged portfolios. This poor out-of-sample performance
G12                                                    for volatility-managed portfolios stems primarily from structural instability in the under-
                                                       lying spanning regressions.
Keywords:
Volatility-managed portfolios                                                                                     © 2020 Elsevier B.V. All rights reserved.
Portfolio choice




1. Introduction                                                                      positions in the underlying factors when volatility was
                                                                                     recently high and more aggressively levered positions
   Recent studies show strong empirical performance for                              following periods of low volatility. Although each of the
volatility-managed versions of popular trading strategies,                           papers noted above examines an individual volatility-
including the market (Ang, 2014; Moreira and Muir, 2019),                            scaled strategy, Moreira and Muir (2017) ﬁnd that the
momentum (Barroso and Santa-Clara, 2015; Daniel and                                  empirical success of volatility management is a pervasive
Moskowitz, 2016), betting-against-beta (Barroso and Maio,                            phenomenon. They show that volatility-scaled strategies
2018), and ﬁnancial distress (Eisdorfer and Misirli, 2020)                           earn systematically positive alphas across a wide range of
factors.1 These portfolios are characterized by conservative                         asset pricing factors, and these alphas imply pronounced
                                                                                     increases in Sharpe ratios and large utility gains for mean-
                                                                                     variance investors. Taken as a whole, existing studies leave
 R
    We thank Jessica Wachter (the referee), Andrew Detzel, Chris Lam-                readers with the impression that volatility-managed equity
oureux, Jonathan Lewellen, Hai Lin, Rick Sias, Neal Stoughton, Mitch
                                                                                     strategies routinely lead to improved performance. The
Towner, and seminar participants at the 2017 Wellington Finance Sum-
mit, the 2018 Northern Finance Association, Iowa State University, North             ﬁndings have important implications for investors, have
Carolina State University, and the University of Arizona for helpful com-
ments and suggestions.
  ∗
    Corresponding author.
    E-mail addresses: cederburg@email.arizona.edu (S. Cederburg),                    ing is also used in the time-series momentum literature (e.g., Moskowitz
odohertym@missouri.edu (M.S. O’Doherty), wangf10@miamioh.edu (F.                     et al., 2012; Baltas and Kosowski, 2017). Kirby and Ostdiek (2012) consider
Wang), xuy219@lehigh.edu (X. Yan).                                                   volatility-timing strategies for portfolio allocations across multiple stock
  1
    Also see related work on volatility-managed currency strategies by               portfolios. Much of this recent work follows from Fleming et al. (2001,
Daniel et al. (2017) and Maurer et al. (2018). Grobys et al. (2018) examine          2003), who demonstrate large economic beneﬁts from volatility timing
the properties of risk-managed industry momentum, and volatility scal-               for short-horizon investors allocating across several asset classes.

https://doi.org/10.1016/j.jﬁneco.2020.04.015
0304-405X/© 2020 Elsevier B.V. All rights reserved.
96                             S. Cederburg, M.S. O’Doherty and F. Wang et al. / Journal of Financial Economics 138 (2020) 95–117


received considerable attention in the ﬁnancial press, and                          (e.g., Kozak et al., 2020). We therefore augment Moreira
have also had an impact on industry applications.2                                  and Muir’s (2017) sample with a set of volatility-scaled
    In this paper, we assess whether volatility management                          portfolios formed on 94 anomaly variables from Hou et al.
is systematically advantageous for investors and place                              (2015) and McLean and Pontiff (2016). Our combined
speciﬁc emphasis on real-time implementation. We con-                               sample of 103 trading strategies allows for a substantially
tribute to the literature in three primary ways. First, based                       broader assessment of the merits of volatility management.
on a substantially broader sample of 103 equity trading                                 Most prior studies (e.g. Barroso and Santa-Clara, 2015;
strategies, we ﬁnd no statistical or economic evidence that                         Daniel and Moskowitz, 2016; Barroso and Maio, 2018; Eis-
volatility-managed portfolios systematically earn higher                            dorfer and Misirli, 2020) assess the value of volatility man-
Sharpe ratios than their unmanaged counterparts do. Sec-                            agement by directly comparing the Sharpe ratios earned by
ond, despite this mixed evidence from direct performance                            scaled strategies similar to those in Eq. (1) with the Sharpe
comparisons, we conﬁrm that Moreira and Muir’s (2017))                              ratios earned by the corresponding unscaled strategies. We
ﬁnding of systematically positive spanning regressions                              follow this approach and ﬁnd no systematic evidence that
alphas for volatility-managed portfolios also holds in                              volatility-managed portfolios outperform their unmanaged
our extended sample. The trading strategies implied by                              versions. Volatility scaling generates a higher Sharpe ratio
the spanning regressions are not implementable in real                              for ﬁve of the nine equity factors examined by Moreira
time, however, as they require investors to combine the                             and Muir (2017). In the more comprehensive sample of
volatility-scaled and unscaled versions of a given port-                            103 equity portfolios, the volatility-managed versions
folio using ex post optimal weights (e.g., Gibbons et al.,                          outperform in 53 cases, whereas the original versions
1989). We explore an array of reasonable out-of-sample                              outperform in 50 cases. We also ﬁnd that only eight
versions of these “combination” strategies and ﬁnd that                             strategies in the broad sample yield statistically signiﬁcant
they typically underperform simple investments in the                               Sharpe ratio differences in favor of volatility management.
original, unscaled portfolios. Third, we examine why the                            These cases are concentrated among momentum-related
in-sample alphas for volatility-managed portfolios do not                           strategies, in accord with the conclusions from Barroso
readily translate into out-of-sample gains for investors. We                        and Santa-Clara (2015) and Daniel and Moskowitz (2016).
provide evidence that this result is driven by substantial                              These initial tests suggest that stand-alone invest-
structural instability in the underlying spanning regres-                           ments in volatility-managed portfolios do not systemat-
sions for these strategies. Overall, our ﬁndings suggest                            ically improve investment outcomes. Moreira and Muir’s
a more tempered interpretation of the practical value of                            (2017) broad evidence on the value of volatility man-
volatility-managed portfolios relative to prior literature.                         agement, however, is not based on direct performance
    Our empirical tests evaluate the performance of                                 comparisons of scaled and unscaled factors. For each
volatility-managed versions of various trading strategies.                          factor, they instead estimate the following spanning re-
Each of the managed portfolios is constructed as                                    gression using time-series data on monthly strategy excess
            c∗                                                                      returns:
fσ ,t =          ft ,                                                     (1)
          σˆ t−1
              2
                                                                                    fσ ,t = α + β ft + εt .                                   (2)
where ft is the original, unscaled portfolio’s excess return                        Moreira and Muir (2017) ﬁnd that, with the exception of
in month t; σˆ t−1
                2  is the realized variance of daily portfolio                      the size factor, each of their volatility-managed portfolios
returns in month t − 1; and c∗ is a constant chosen such                            yields a positive regression intercept, and almost all of
that fσ ,t and ft have the same full-sample variance. We                            the estimates are statistically and economically signiﬁcant.
consider the nine volatility-managed equity factors from                            They also conﬁrm that the volatility-managed portfolios
Moreira and Muir (2017) and report detailed results for                             continue to exhibit large alphas when the Fama and
these factors in the paper.3 Although this set of strate-                           French (1993) factors are included in Eq. (2) as additional
gies provides a reasonable representation of factors from                           controls. They interpret the results as strong evidence
leading asset pricing models, recent studies suggest that                           in favor of volatility management and highlight that the
a much larger number of characteristics is needed to                                positive alphas are synonymous with increased Sharpe
summarize both covariance risk (e.g., Kelly et al., 2019)                           ratios and utility gains for mean-variance investors.
and cross-sectional variation in expected stock returns                                 We reproduce Moreira and Muir’s (2017) in-sample
                                                                                    spanning regression results for the nine equity factors and
  2
    Representative examples of recent press coverage include “Re-                   show that they extend to our broader sample of equity
assessing the classic risk-return tradeoff,” The Financial Times, March 9,          strategies. In particular, 77 out of the 103 volatility-scaled
2016 and “When markets get scary, panicking is smart,” CNBC, March 23,              portfolios earn positive alphas in spanning tests, with 23
2016. For an example of volatility management in practice, BlackRock of-            signiﬁcantly positive estimates compared with just 3 sig-
fers the following description of the investment strategy for its Managed
                                                                                    niﬁcantly negative ones. Spanning regressions that control
Volatility V.I. Fund: “In periods of heightened volatility, the portfolio will
de-risk into less volatile assets like ﬁxed income and cash and re-risk             for exposure to the market, size, and value factors produce
when market turbulence subsides.”                                                   70 positive intercepts. These ﬁndings offer a conﬁrmation
  3
    The equity factors in Moreira and Muir (2017) include the market,               of the potential economic gains from volatility-managed
size, and value factors from the Fama and French (1993) three-factor                portfolios.
model, the momentum factor from the Carhart (1997) four-factor model,
the proﬁtability and investment factors from both the Fama and French
                                                                                        The investment implication of a positive spanning
(1993) ﬁve-factor model and the Hou et al. (2015) q-factor model, and               regression intercept is that the optimal ex post combi-
Frazzini and Pedersen’s (2014) betting-against-beta factor.                         nation of scaled and unscaled portfolios (with positive
                        S. Cederburg, M.S. O’Doherty and F. Wang et al. / Journal of Financial Economics 138 (2020) 95–117                                   97


weight on the scaled portfolio) expands the mean-variance                    This combination strategy also leads to a reduction in CER.
frontier relative to the unscaled portfolio (e.g., Gibbons                   There are some positive ﬁndings on the out-of-sample
et al., 1989). That is, the increased Sharpe ratios and                      value of volatility management, as scaled versions of
utility gains referenced in Moreira and Muir (2017) are                      the momentum (MOM), proﬁtability (ROE), and betting-
earned by combinations of two strategies rather than                         against-beta (BAB) factors contribute to large utility gains
by the volatility-managed portfolios themselves. This                        for mean-variance investors. Nevertheless, there is little
interpretation highlights a concern with Moreira and                         statistical or economic evidence for the remaining six
Muir’s (2017) spanning regression evidence in terms of                       factors that incorporating volatility management improves
its implications for real-time investors. Moreira and Muir                   real-time portfolio outcomes.
(2017) acknowledge the importance of out-of-sample                               The extended sample of 103 trading strategies provides
applications by emphasizing that their volatility-managed                    our most comprehensive and convincing evidence on the
strategies are “easy to implement in real time.” Although                    poor out-of-sample performance of combination strategies.
a volatility-managed portfolio constructed according to                      In our base case design, the real-time combination of
Eq. (1) is straightforward to construct in real time, the                    volatility-managed and original portfolios earns a lower
investment strategy implied by Eq. (2) is not. Because the                   CER relative to the original portfolio in 72 of 103 cases. We
optimal weighting of scaled and unscaled portfolios de-                      consider a wide range of robustness checks by iterating
pends on in-sample return moments, the required strategy                     through alternative design features, including minimum
is not known prior to the end of the sample.                                 window lengths of historical data used to form portfolio
    A natural question is whether real-time investors can                    weights, expanding versus rolling training samples, in-
capture the economic gains implied by the spanning                           vestor risk aversion parameters, and leverage constraints
regressions. We conduct an extensive analysis of the                         on portfolio positions. We also study the impact of aug-
out-of-sample performance of combinations of volatility-                     menting the investment opportunity set with the three
managed and original portfolios. We adopt the standard                       Fama and French (1993) factors. None of these reasonable
approach of using a training sample of historical data to                    modiﬁcations tilts the results in favor of the combination
estimate optimal allocations to the scaled and unscaled                      strategies.
versions of a given strategy. Prior literature suggests that                     Finally, we explore the economic underpinnings of our
estimation risk is a key issue in the out-of-sample, mean-                   results. We do so by comparing the out-of-sample per-
variance portfolio choice problem associated with Eq.                        formance of the combination strategies that incorporate
(2) (e.g., Black and Litterman, 1992; Green and Holliﬁeld,                   volatility-managed portfolios with the out-of-sample per-
1992; Jagannathan and Ma, 2003; DeMiguel et al., 2009a;                      formance of traditional anomaly strategies. We ﬁnd that
2009b). In practice, estimated portfolio weights are often                   translating alpha into real-time performance is challenging
unstable, and real-time portfolios often underperform                        in general, but out-of-sample performance degradation is
considerably relative to their in-sample optimal counter-                    noticeably more severe in the volatility-managed portfolios
parts. There is ex ante reason for optimism in the current                   setting. We also provide statistical evidence that the more
context, however, given the strong in-sample results and                     tenuous link between in-sample alpha and out-of-sample
DeMiguel et al.’s (2009b) evidence that out-of-sample                        performance in the volatility-managed portfolios setting
performance degradation is less severe when the number                       is attributable to a propensity for structural breaks in the
of test assets is small.                                                     spanning regressions for the volatility-managed portfolios.
    Our out-of-sample tests focus on quantifying the eco-                    Simply put, the spanning regression parameters that real-
nomic impact of including a volatility-managed portfolio                     time investors estimate from past data often fail to provide
in the investment opportunity set. We compare the Sharpe                     a reliable indication of the future performance of volatility-
ratio and certainty equivalent return (CER) for two real-                    managed portfolios relative to their unscaled versions.
time strategies: (i) a strategy that allocates between a                         We contribute to the literature on volatility man-
given volatility-managed portfolio, its corresponding orig-                  agement by offering a complementary viewpoint to the
inal portfolio, and a risk-free security and (ii) a strategy                 one presented in Moreira and Muir (2017). Their study
constrained to invest only in the original portfolio and the                 provides important insights on the dynamics of the condi-
risk-free asset. The baseline results correspond to a mean-                  tional risk-return relation, and their in-sample analysis is
variance investor with a risk aversion coeﬃcient of ﬁve                      valuable to researchers attempting to map the data to an
and also feature a leverage constraint of ﬁve on portfolio                   asset pricing model in the rational expectations framework
positions. Our design choices to include a risk-free security                (i.e., Inoue and Kilian, 2004).4 Such an approach inherently
and a leverage constraint are favorable to real-time in-
vestors, as these features reduce estimation risk associated
                                                                                4
                                                                                  An important contribution of Moreira and Muir (2017) is to demon-
with extreme positions (e.g., Kirby and Ostdiek, 2012).
                                                                             strate that several leading macroﬁnance models are unable to generate
    In contrast to the impressive in-sample results for the                  the large, positive estimate of the spanning regression alpha for the mar-
nine equity factors studied by Moreira and Muir (2017),                      ket portfolio. In the Internet Appendix, we complement their diagnos-
volatility management often harms real-time performance.                     tic by introducing a decomposition of spanning regression alpha into a
The out-of-sample strategy combining the volatility-                         component that measures the relation between lagged volatility and re-
                                                                             turn, (1 + f¯t2 /σˆ f2 )cov(c∗ /σˆ t−1
                                                                                                                 2
                                                                                                                    , ft ), and a component that measures the
managed market portfolio and the unmanaged market
                                                                             relation between lagged and current volatility, −( f¯t /σˆ 2 )cov(c∗ /σˆ 2 , f 2 ).
portfolio, for example, earns an annualized Sharpe ratio                                                                                   f           t−1   t
                                                                             We decompose the market factor’s annualized spanning regression al-
of 0.42 compared with 0.46 for the strategy that limits its                  pha of 4.63% and ﬁnd that the ﬁrst and second components contribute
risky investment set to the unmanaged market portfolio.                      −0.24% and 4.87%, respectively. This diagnostic indicates that an asset
98                           S. Cederburg, M.S. O’Doherty and F. Wang et al. / Journal of Financial Economics 138 (2020) 95–117


assumes that investors know more than the econometri-                             anomaly, we construct a value-weighted hedge portfolio
cian does about the true data generating process. From                            that takes a long (short) position in the decile of stocks
a practical investment perspective, their results speak                           predicted to outperform (underperform) based on prior
to the potential economic beneﬁts of volatility-managed                           literature. We use the CRSP daily (monthly) ﬁle to con-
portfolios. Our ﬁndings suggest that the in-sample alphas                         struct the daily (monthly) return series for each anomaly.
and utility gains do not readily translate into enhanced                          The Appendix provides additional detail on our sample
portfolio outcomes for investors who must learn about                             selection and portfolio formation procedures.
volatility-managed portfolios from prior data.                                        The combined sample consists of 103 equity trading
   The remainder of the paper is organized as follows.                            strategies (i.e., 9 factors and 94 anomaly portfolios). Many
Section 2 describes the data and introduces volatility-                           of the strategies are based on related characteristics, and
managed portfolios. Section 3 compares volatility-managed                         we group them into the following eight categories based
and original strategies. Section 4 contains our empirical                         on the classiﬁcation scheme in Hou et al. (2015): accruals,
tests on real-time strategies that combine volatility-                            intangibles, investment, market, momentum, proﬁtability,
managed portfolios with their unscaled versions, and                              trading, and value.
Section 5 concludes. The Appendix presents additional
detail on data construction, and the Internet Appendix                            2.2. Construction of volatility-managed portfolios
reports supplementary results.
                                                                                      For a given asset pricing factor or anomaly portfolio, let
2. Data                                                                           ft be the buy-and-hold excess portfolio return in month
                                                                                  t. We follow Moreira and Muir (2017) and construct the
   Section 2.1 introduces the data on trading strategies                          corresponding volatility-managed portfolio return as
used in our empirical tests, and Section 2.2 discusses the                                    c∗
                                                                                  fσ ,t =          ft ,                                                  (3)
construction of volatility-managed portfolios.                                              σˆ t−1
                                                                                                2


2.1. Data description                                                             where c∗ is a constant and σˆ t−12   is the realized variance
                                                                                  of daily returns during the month preceding the portfolio
    We ﬁrst consider the nine equity factors examined by                          formation date. The managed portfolio is a scaled version
Moreira and Muir (2017). We collect daily and monthly                             of the original strategy, with investment positions propor-
data on factor excess returns for the market (MKT), size                          tional to the inverse of lagged variance. Let j = 1, . . . , Jt
                                                                                                                     j
(SMB), and value (HML) factors from the Fama and French                           index days in month t, and let ft be the excess return for
(1993) three-factor model, a momentum factor (MOM),                               a given portfolio on day j of month t. We compute realized
the proﬁtability (RMW) and investment (CMA) factors from                          variance in month t as
                                                                                            22   j 2
                                                                                                 Jt
the Fama and French (1993) ﬁve-factor model, the prof-
itability (ROE) and investment (IA) factors from the Hou                          σˆ t2 =         ft .                                                   (4)
                                                                                            Jt
et al. (2015) q-factor model, and Frazzini and Pedersen’s                                       j=1

(2014) betting-against-beta factor (BAB).5 , 6                                    Given the full time series of ft and σˆ t−1
                                                                                                                           2 , we select the scal-

    We augment the ﬁrst group of test portfolios with a                           ing parameter, c∗ , such that ft and fσ ,t have the same un-
second group covering a broader set of trading strategies                         conditional volatility. The scaling parameter is not known
based on established asset pricing anomalies. We start                            to an investor in real time, but we note that some perfor-
with the lists of anomaly variables reported in Hou et al.                        mance measures (e.g., Sharpe ratios and appraisal ratios)
(2015) and McLean and Pontiff (2016). We then restrict                            are invariant to the choice of c∗ .7 In our applications, ft al-
our analysis to strategies that are based on a single,                            ways represents the excess return for a zero-cost portfolio.
continuous sorting variable and can be constructed using                          As such, the dynamic investment position in the underly-
the Center for Research in Security Prices (CRSP) Monthly                         ing portfolio, c∗ /σˆ t−1
                                                                                                         2 , is a measure of the leverage required

and Daily Stock Files, the Compustat Fundamentals Annual                          to invest in the volatility-managed portfolio in month t.
and Quarterly Files, and the Institutional Brokers Estimate
System (IBES) database. This process identiﬁes 94 anomaly                         3. Direct comparisons
variables, which we summarize in Table A1. For each
                                                                                     Several prior studies argue that volatility-managed
                                                                                  versions of popular trading strategies exhibit impressive
pricing model must produce much more volatility in market return vari-
ance compared with traditional macroﬁnance models to match the sam-
ple moments from the data. Our decomposition complements the span-                  7
                                                                                      Several studies differ from Eqs. (3) and (4) in their construction of
ning regression alpha proposed by Moreira and Muir (2017) by providing            volatility-managed trading strategies. These differences include scaling by
additional guidance on model features that could reproduce this alpha.            realized standard deviation rather than by realized variance (e.g., Barroso
  5
    Data on MKT, SMB, HML, MOM, RMW, and CMA are from Ken-                        and Santa-Clara, 2015; Barroso and Maio, 2018), using a parametric model
neth French’s website at http://mba.tuck.dartmouth.edu/pages/faculty/             to estimate volatility (e.g., Daniel and Moskowitz, 2016; Moreira and Muir,
ken.french/. Data on BAB are from Andrea Frazzini’s website at http:              2017), using longer intervals to estimate lagged realized volatility (e.g.,
//people.stern.nyu.edu/afrazzin/. We thank Kenneth French and Andrea              Barroso and Santa-Clara, 2015; Daniel and Moskowitz, 2016), scaling by
Frazzini for making these data available. We thank Lu Zhang for sharing           market volatility rather than by factor-speciﬁc volatility (e.g., Eisdorfer
the data on ROE and IA.                                                           and Misirli, 2020), and selecting c∗ to achieve a target level of strategy
  6
    Moreira and Muir (2017) also examine a currency carry strategy. We            risk rather than to match the standard deviation of the original factor.
omit this portfolio from our set of test assets given our focus on equity         Daniel and Moskowitz (2016) also incorporate information on the condi-
strategies.                                                                       tional factor mean in specifying their dynamic momentum strategy.
                                S. Cederburg, M.S. O’Doherty and F. Wang et al. / Journal of Financial Economics 138 (2020) 95–117                                                                           99


Table 1
Volatility-managed and original factors.
The table compares the performance of volatility-managed and original versions of nine equity factors. The factors are the market (MKT), size (SMB),
and value (HML) factors from the Fama and French (1993) three-factor model, a momentum factor (MOM), the proﬁtability (RMW) and investment (CMA)
factors from the Fama and French (2015) ﬁve-factor model, the proﬁtability (ROE) and investment (IA) factors from the Hou et al. (2015) q-factor model,
and Frazzini and Pedersen’s (2014) betting-against-beta factor (BAB). For a given factor, the volatility-managed factor return in month t is f σ ,t = (c∗ /σˆ t−1
                                                                                                                                                               2
                                                                                                                                                                  ) ft ,
where ft is the monthly return for the original factor, σˆ t−1
                                                            2
                                                               is the realized variance of daily factor returns in month t − 1, and c∗ is a constant chosen so that
ft and fσ ,t have the same unconditional standard deviation over the full sample period. We present the mean return, standard deviation, and annualized
Sharpe ratio for each original (volatility-managed) factor in Panel A (Panel B). The means and standard deviations are reported in percentage per year. Panel
C shows the difference between the Sharpe ratio of the volatility-managed factor and that of the original factor, and the ﬁgures in brackets are p-values
from Jobson and Korkie (1981) tests. Panel D reports the correlation between each original factor and the corresponding volatility-managed factor and the
1st, 50th, and 99th percentiles of the time-series distribution of the scaled factor’s implied weight in the original factor. The sample period starts in August
1926 for MKT, SMB, and HML; January 1927 for MOM; August 1963 for RMW and CMA; February 1967 for ROE and IA; and February 1931 for BAB. The
sample periods end in December 2016.

                                                                                                                      Factor

                                                        MKT          SMB          HML               MOM                RMW                 CMA                ROE                  IA                BAB
                                                        (1)           (2)          (3)               (4)                (5)                 (6)               (7)                 (8)                (9)

                                                       Panel A: Performance measures for original factors

  Mean                                                  7.80         2.57          4.84             7.94                2.92                3.72              6.52                4.99              8.23
  Standard deviation                                   18.61        11.12         12.14            16.39                7.71                6.97              8.83                6.48             10.71
  Sharpe ratio                                          0.42         0.23          0.40             0.48                0.38                0.53              0.74                0.77              0.77

                                                 Panel B: Performance measures for volatility-managed factors

  Mean                                                  9.55         0.86          4.64            16.17                3.94                2.79              9.39                4.69             10.81
  Standard deviation                                   18.61        11.12         12.14            16.39                7.71                6.97              8.83                6.48             10.71
  Sharpe ratio                                          0.51         0.08          0.38             0.99                0.51                0.40              1.06                0.72              1.01

                                                                 Panel C: Performance comparisons

  Sharpe ratio difference                                0.09       −0.15        −0.02               0.50               0.13             −0.13                0.32             −0.05                 0.24
                                                        [0.30]       [0.09]       [0.86]            [0.00]             [0.29]             [0.23]             [0.01]             [0.68]              [0.01]

                                                        Panel D: Properties of volatility-managed factors

  Correlation with original factor                      0.63          0.63         0.57               0.48              0.59                0.68              0.68                0.70               0.62
  P01 (c∗ /σˆ t−1
               2
                  )                                     0.04          0.03         0.04               0.04              0.04                0.06              0.06                0.06               0.04
  P50 (c∗ /σˆ t−1
               2
                  )                                     0.96          0.81         1.02               1.01              1.11                0.97              1.08                0.96               1.00
  P99 (c /σˆ t−1 )
        ∗      2
                                                        6.47          5.07         5.89               8.64              5.02                4.56              4.73                4.45               5.09




performance. The empirical tests in these studies typically                               and original versions of each factor earn positive av-
highlight that the volatility-managed version of a given                                  erage returns, but neither version yields systematically
portfolio directly outperforms its corresponding unman-                                   superior performance across the factors. In ﬁve cases the
aged portfolio. For example, Barroso and Santa-Clara                                      volatility-managed factor earns a higher average return
(2015) and Daniel and Moskowitz (2016) compare Sharpe                                     and Sharpe ratio than the original strategy does, whereas
ratios and cumulative returns for scaled and unscaled                                     the original factor outperforms in the remaining four
versions of the momentum factor. Barroso and Maio                                         cases. Three of the nine differences are signiﬁcantly pos-
(2018) and Eisdorfer and Misirli (2020) present similar                                   itive, as the volatility-managed versions of MOM, ROE,
evidence for the betting-against-beta and ﬁnancial distress                               and BAB achieve Sharpe ratio gains by outperforming the
strategies, respectively. We adopt this focus on direct                                   original factors by 8.23%, 2.86%, and 2.58% per year, re-
performance comparisons in this section and contribute                                    spectively (recall that the volatility-managed and original
to the literature by assessing a much broader set of                                      versions of each strategy have the same standard deviation
volatility-managed portfolios.                                                            by construction). The ﬁndings are consistent with prior
    We begin our analysis by presenting detailed results on                               literature on the beneﬁts of volatility management for the
direct performance comparisons for the nine equity factors                                momentum (Barroso and Santa-Clara, 2015; Daniel and
in Table 1. Panel A (Panel B) reports mean excess returns,                                Moskowitz, 2016) and betting-against-beta (Barroso and
standard deviations, and Sharpe ratios for the original                                   Maio, 2018) strategies. Based on these prior studies, the
(volatility-managed) factors, and Panel C shows the Sharpe                                signiﬁcant result for volatility-managed ROE is perhaps
ratio differences between the volatility-managed and                                      also unsurprising, given the original factor’s relatively high
original factors. To determine whether each difference is
statistically signiﬁcant, we follow the approach proposed
by Jobson and Korkie (1981).8 Both the volatility-managed                                 covariance between excess returns for the two portfolios. To test the
                                                                                          null hypothesis of equal Sharpe ratios for portfolios i and j, we com-
                                                                                          pute the following Jobson and Korkie (1981) test statistic, which is
                                                                                                                                                  σˆ μˆ i −σˆ i μˆ j
                                                                                          asymptotically distributed as a standard normal: zˆJK = j √                , where
  8
    Let μ
        ˆ i and σˆ i be the mean and standard deviation of excess re-                                                                                                                              θˆ

turns for portfolio i over a period of length T. Similarly, μ
                                                            ˆ j and σˆ j                  θˆ = T1 2σˆ i2 σˆ j2 − 2σˆ i σˆ j σˆ i, j + 12 μˆ 2i σˆ j2 + 12 μˆ 2j σˆ i2 − μσˆˆ ii μσˆˆ jj σˆ i,2j . The test incor-
are the mean and standard deviation for portfolio j, and σˆ i, j is the                   porates the correction noted by Memmel (2003).
100                               S. Cederburg, M.S. O’Doherty and F. Wang et al. / Journal of Financial Economics 138 (2020) 95–117


Table 2                                                                                that are positive or negative and the number of these
Summary of volatility-managed and original portfolios: broad sample.
                                                                                       differences that are statistically signiﬁcant at the 5%
The table summarizes results for direct comparisons of volatility-managed
and original versions of 103 trading strategies. For a given factor or                 level.10 Panel B separates the results for the 9 factors and
anomaly portfolio, the volatility-managed strategy return in month t is                94 anomaly portfolios, and Panel C displays the corre-
 f σ ,t = (c∗ /σˆ t−1
                   2
                      ) ft , where ft is the monthly return for the original portfo-   sponding ﬁgures for each strategy type. As in Table 1,
lio, σˆ t−1
         2
             is the realized variance of daily portfolio returns in month t − 1,       positive (negative) differences indicate outperformance
and c∗ is a constant chosen so that ft and fσ ,t have the same unconditional
                                                                                       (underperformance) for the volatility-scaled versions.
standard deviation over the full sample period. In each case, we compute
the difference between the Sharpe ratio of the volatility-managed portfo-                  The results in Table 2 suggest that volatility-managed
lio and that of the original portfolio. Panel A reports results for the full set       portfolios do not systematically outperform their original
of 103 trading strategies. Panel B presents separate results for the 9 fac-            counterparts. In Panel A, volatility management leads to
tors and the 94 anomaly portfolios. Panel C breaks the results down by
                                                                                       improved and worsened performance at roughly the same
trading strategy type. For each set of comparisons, the table presents the
number of Sharpe ratio differences that are positive, positive and signiﬁ-
                                                                                       frequency. The performance differences across the 103
cant at the 5% level, negative, and negative and signiﬁcant at the 5% level.           trading strategies include 53 positive and 50 negative val-
We assess statistical signiﬁcance of the Sharpe ratio differences using the            ues, and few of the differences are statistically signiﬁcant.
Jobson and Korkie (1981) approach.                                                         Panel C reveals that the majority of the signiﬁcantly
                                              Sharpe ratio difference                  positive Sharpe ratio differences are attributable to the
                                                                                       nine momentum strategies. Volatility management im-
  Sample                      Total    SR > 0 [Signif.]      SR < 0 [Signif.]
  (1)                          (2)             (3)                    (4)              proves performance for every momentum strategy, and
                                                                                       ﬁve of the nine performance differences are statistically
                          Panel A: Combined sample
                                                                                       signiﬁcant at the 5% level. The ﬁndings are consistent with
  All trading strategies      103            53 [8]                 50 [4]             the impressive performance of volatility-managed momen-
                             Panel B: By category                                      tum portfolios demonstrated by Barroso and Santa-Clara
                                                                                       (2015) and Daniel and Moskowitz (2016). Barroso and
  Factors                       9             5 [3]                  4 [0]
  Anomaly portfolios           94            48 [5]                 46 [4]             Santa-Clara (2015) notably ﬁnd that managing the risk of
                                                                                       momentum is robust to using alternative windows (i.e.,
                      Panel C: By trading strategy type
                                                                                       one, three, or six months) to estimate realized volatility.
  Accruals                     10             4 [0]                  6 [0]             We complement this result by showing that the perfor-
  Intangibles                  10             3 [0]                  7 [0]
                                                                                       mance of volatility-managed momentum is also robust to
  Investment                   11             3 [0]                  8 [1]
  Market                        1             1 [0]                  0 [0]
                                                                                       several alternative deﬁnitions of the momentum strategy
  Momentum                      9             9 [5]                  0 [0]             itself.
  Proﬁtability                 22            15 [1]                  7 [1]                 Outside of the momentum group, the volatility-
  Trading                      21            11 [1]                 10 [1]             managed versions of just three strategies exhibit statisti-
  Value                        19             7 [1]                 12 [1]
                                                                                       cally signiﬁcant outperformance: ROE, BAB, and Loughran
                                                                                       and Wellman’s (2012) enterprise multiple. We also ﬁnd
                                                                                       that volatility scaling results in signiﬁcantly lower Sharpe
correlation with MOM and BAB.9 Aside from MOM, ROE,                                    ratios for four portfolios. This group includes growth in
and BAB, the remaining six factors exhibit differences in                              book equity (Lockwood and Prombutr, 2010), change in
Sharpe ratios that are insigniﬁcant at the 5% level and aver-                          sales less change in inventory (Abarbanell and Bushee,
age return differentials between −1.71% and 1.74% per year.                            1998), 1/share price (Miller and Scholes, 1982), and
    Panel D of Table 1 shows that the correlation coef-                                long-term reversal (De Bondt and Thaler, 1985).
ﬁcients for excess returns for the scaled and unscaled                                     To interpret the broad-based results in Table 2, we
strategies range from 0.48 to 0.70. Panel D also high-                                 compare the total number of positive Sharpe ratio differ-
lights that investing in volatility-scaled portfolios requires                         ences in the data with the number that would be expected
aggressively altering exposures to the underlying factors                              under reasonable assumptions about the data generating
over time. Although the median investment position for                                 process. The performance of a given volatility-managed
each of the dynamic portfolios is around one, the 99th                                 portfolio is driven by two factors: (i) the relation between
percentile of required leverage exceeds 400% in each case                              lagged volatility and future volatility and (ii) the relation
and reaches as high as 864% for the momentum strategy.                                 between lagged volatility and future expected return.
    To offer a more comprehensive view on the perfor-                                  Volatility management is likely to be successful if volatility
mance of volatility-managed portfolios, we examine the                                 is persistent and the risk-return relation is ﬂat. In this
expanded set of 103 equity trading strategies. Table 2 pro-                            scenario, a portfolio’s conditional Sharpe ratio is negatively
vides a summary of the Sharpe ratio differences between                                associated with its lagged volatility, and investors can
the volatility-managed and original strategies. Many of                                capitalize on these dynamics in the conditional risk-return
the portfolios are formed on related characteristics, so                               trade-off by taking more aggressive investment positions
we classify them into strategy types relating to accruals,                             following low-volatility periods. If lagged volatility is
intangibles, investment, market, momentum, proﬁtability,                               negatively related to average return for a given strategy,
trading, and value. Across all 103 strategies, Panel A of                              volatility management becomes even more attractive. A
Table 2 reports the number of Sharpe ratio differences

                                                                                        10
                                                                                           We present detailed results on performance comparisons for the in-
  9
      The correlation coeﬃcient between ROE and MOM (BAB) is 0.50 (0.26).              dividual factors and anomaly portfolios in the Internet Appendix.
                               S. Cederburg, M.S. O’Doherty and F. Wang et al. / Journal of Financial Economics 138 (2020) 95–117                      101


positive risk-return trade-off, in contrast, makes volatility                       itive and negative performance differences in Table 2 are
management less effective.                                                          in line with this second null hypothesis. We compute
    We examine the performance of volatility-managed                                the two-tailed p-value for the number of positive Sharpe
portfolios relative to the null hypothesis that each of the                         ratio differences relative to the binomial distribution
103 original portfolios exhibits persistence in conditional                         under the null that the volatility-managed and original
volatility but zero correlation between lagged volatility                           versions of each of the 103 portfolios are equally likely to
and future expected return. This null reﬂects both the                              outperform the other. The p-value of 0.84 indicates that
overwhelming evidence of volatility clustering in asset                             a null hypothesis of equal performance is not rejected.
returns (e.g., Engle, 2004) and the lack of conclusive                              These ﬁndings are in accord with the general conclusion
evidence on the relation between conditional variance                               that volatility-managed strategies do not systematically
and average return for the strategies of interest.11 The                            outperform the corresponding original strategies.
test of this hypothesis allows us to use the performance
of volatility-managed portfolios to assess the risk-return                          4. Combination strategies
trade-off in our broad sample.
    To evaluate the performance of volatility-managed                                   Whereas the results in Section 3 provide evidence that
portfolios relative to the expectation under this null                              volatility-managed portfolios do not systematically outper-
hypothesis, we develop a bootstrap analysis that is de-                             form original portfolios, Moreira and Muir’s (2017) span-
scribed in detail in the Internet Appendix. This procedure                          ning regression tests suggest that volatility-scaled port-
generates bootstrap samples that (i) preserve for each                              folios are potentially more valuable when used in com-
strategy the empirical relation between the inverse of                              bination with their original counterparts rather than as
lagged variance and the variance of the realized strategy                           stand-alone investments. In Sections 4.1 and 4.2, we note
return and (ii) have, on average, no predictive relation                            the differences between direct performance comparisons
between lagged variance and return. We generate 10 0,0 0 0                          and spanning tests and highlight the portfolio implications
bootstrap samples under the null hypothesis, run 103                                of Moreira and Muir’s (2017) spanning regression approach
direct performance comparisons in each bootstrap sample,                            to evaluating volatility-managed portfolios. These sections
and count the number of positive performance differences.                           also show that the trading strategies implied by spanning
We then compare the number of positive differences                                  regressions are not available to real-time investors. Given
in the data to the bootstrap distribution under the null                            this limitation, we turn to a comprehensive analysis of the
hypothesis to assess statistical signiﬁcance.                                       out-of-sample performance of combination strategies that
    Fig. 1 shows the bootstrap distribution of the number                           incorporate volatility management in Section 4.3.
of positive Sharpe ratio differences. As expected, volatility
management is an attractive strategy under the null hy-                             4.1. Spanning regressions
pothesis of persistent volatility but no risk-return relation.
Across the bootstrap samples, the average number of pos-                               Moreira and Muir’s (2017) evidence on the success of
itive Sharpe ratio differences is 66 out of 103. In contrast,                       volatility-managed portfolios follows from the spanning
the 53 observed positive Sharpe ratio differences in the                            regression approach. They evaluate volatility-managed
data are considerably fewer than what would be expected                             factors by estimating time-series regressions of the form
under this null. The two-tailed bootstrap p-value of 0.01
                                                                                    fσ ,t = α + β ft + εt .                                            (5)
indicates that the null hypothesis of persistent volatility
but no risk-return relation is rejected. As noted above, a                          Their tests focus on α , which they estimate to be positive,
positive risk-return relation for a given strategy works to                         economically large, and statistically signiﬁcant for a wide
degrade the performance of a given volatility-managed                               range of popular asset pricing factors.12 Moreira and Muir
portfolio such that the data indicate that the risk-return                          (2017) further emphasize that positive alphas are synony-
relations tend to be positive across the broad set of 103                           mous with increased Sharpe ratios relative to the original
strategies.                                                                         factors and pronounced utility gains for mean-variance
    We also consider a second null hypothesis that the                              investors. In this section, we consider the portfolio proper-
expected Sharpe ratios for the volatility-managed and orig-                         ties associated with the spanning regressions and develop
inal versions of each strategy are equal. The corresponding                         intuition for why the in-sample results do not readily
test provides insight on the practical question of whether                          extend to real-time investment settings.
or not investors should generally favor volatility-managed                              We note that a positive alpha in regression (5) is a
portfolios over original portfolios. The frequencies of pos-                        lower bar for declaring success of a given managed strat-
                                                                                    egy relative to a positive Sharpe ratio difference in a direct
                                                                                    comparison (e.g., Section 3). We demonstrate this point
 11
    Several studies examine the relation between the expected return
                                                                                    formally in the Internet Appendix. In particular, consider
and conditional variance of the market portfolio. In early work, for ex-
ample, Campbell (1987) ﬁnds a negative relation, whereas French et al.              the case in which both the managed and unmanaged
(1987) ﬁnd an insigniﬁcant or positive relation. Subsequent papers also             versions of a given strategy earn positive average returns
produce mixed evidence on the sign of the risk-return trade-off for the             (i.e., f¯σ ,t > 0 and f¯t > 0). Because fσ ,t and ft have identical
market, with the results being sensitive to the sample period, the method
for estimating conditional volatility, and the time-series approach to relat-
                                                                                     12
ing conditional variance and return. There is considerably less published               Moreira and Muir also demonstrate that volatility-managed strate-
evidence on the nature of the risk-return trade-off for other factors and           gies earn positive alphas when unscaled versions of the Fama and French
anomaly portfolios.                                                                 (1993) three factors are included in Eq. (5) as additional controls.
102                           S. Cederburg, M.S. O’Doherty and F. Wang et al. / Journal of Financial Economics 138 (2020) 95–117




Fig. 1. Bootstrap distribution. The ﬁgure shows the bootstrap distribution of the number of positive Sharpe ratio differences across the 103 strategies
under the null hypothesis of persistence in volatility with no risk-return relation. The bootstrap procedure is described in the Internet Appendix, and the
histogram shows the distribution for 10 0,0 0 0 bootstrap samples. The vertical dotted line indicates that 53 of 103 comparisons produce positive performance
differences in the data.



full sample volatility by construction, the scaled portfolio                       is the solution to the following problem:
achieves a higher Sharpe ratio as long as f¯σ ,t > f¯t . The                                                                     γ
requirement for a positive spanning test alpha, however,                           max U (a ) = a μ
                                                                                                   ˆ −                                  a ˆ a,          (6)
                                                                                       a                                            2
is f¯σ ,t > ρˆ f¯t , where ρˆ is the unconditional correlation
between the scaled and unscaled factors.13 As shown in                             where μ ˆ = [ f¯σ ,t f¯t ] is the 2 × 1 vector of mean excess
Table 1, these correlations range from 0.48 to 0.70 for the                        returns, ˆ is the 2 × 2 variance–covariance matrix, and
equity strategies examined by Moreira and Muir (2017).14                           γ is the investor’s risk aversion parameter. In this setup,
Volatility scaling could, therefore, lead to a 30% or larger                       the investor implicitly has access to a risk-free security.
drop in Sharpe ratio and at the same time produce a                                The vector of optimal portfolio weights is given by
positive spanning regression intercept.
                                                                                            
                                                                                             x∗σ                1 ˆ −1
    A positive alpha in Eq. (5) does indicate that the                             a=                      =                   μˆ ,                      (7)
                                                                                             x∗                γ
optimal ex post combination of scaled and unscaled fac-
tors (with positive weight on the scaled factor) expands                           and the vector of optimal relative weights in the two risky
the mean-variance frontier relative to the original factor                         assets is
(e.g., Gibbons et al., 1989). This point follows from the                                   
                                                                                       w∗σ                     ˆ −1 μ
                                                                                                                    ˆ
well-known link between spanning tests and portfolio                                             =                              ,                        (8)
                                                                                       w∗              |   1 ˆ −1 ˆ   μ|
optimization under mean-variance utility. Consider a                                                        2
mean-variance investor who allocates between excess re-                            where 12 is a 2 × 1 vector of ones. The weights in the
turns fσ ,t and ft . Given the sample moments for fσ ,t and ft ,                   two risky assets depend on the investor’s risk aversion but
the investor’s ex post optimal vector of ﬁxed allocations to                       the relative allocations across the two assets do not. Given
the volatility-managed and original factors, a = [x∗σ x∗ ] ,                      that the scaled and unscaled factors have the same full
                                                                                   sample standard deviation, the covariance matrix is
                                                                                                                      
                                                                                   ˆ = σˆ 2 1                    ρˆ
 13
    We also show in the Internet Appendix that ρˆ = βˆ , where βˆ is the                  f ρ                              ,                             (9)
estimate of the slope coeﬃcient from the univariate spanning regression
                                                                                            ˆ                      1
in Eq. (5).
 14
    The correlations for the broader sample of 103 strategies are between
                                                                                   where σˆ f2 is the unconditional variance of factor returns.
0.48 and 0.80 (see Internet Appendix).                                             The ex post optimal allocation to the volatility-managed
                                    S. Cederburg, M.S. O’Doherty and F. Wang et al. / Journal of Financial Economics 138 (2020) 95–117                            103


portfolio is then proportional to the spanning regression                                in portfolio performance are based on ex post results, how-
alpha,                                                                                   ever, which potentially overstate the value of volatility
                                                                                         management in practice. An investor could only achieve
                    αˆ
x∗σ =                         .                                            (10)          the utility gains by combining the scaled and unscaled
         γ σ (1 − ρˆ 2 )
            ˆ f2                                                                         versions of a particular factor using weights that are un-
The optimal strategy assigns positive weight to the                                      known prior to observing the full sample of factor returns.
volatility-managed portfolio if and only if this portfolio                               As such, these types of strategies are not implementable
earns a positive spanning regression alpha.                                              in real time. We empirically demonstrate the link between
   We combine the optimal investment policy in Eq.                                       Moreira and Muir’s (2017) in-sample regression results and
(7) with the deﬁnition of the volatility-managed portfolio                               optimal portfolio choice in the following section.
in Eq. (3) to generate the dynamic investment rule
                                                                                         4.2. In-sample tests
                    c∗
yt∗ = x∗σ                  + x∗ .                                          (11)              Table 3 reproduces Moreira and Muir’s (2017) spanning
                  σˆ t−1
                      2
                                                                                         tests for the nine volatility-managed equity factors. Panel
The investor’s ex post optimal policy allocates a static                                 A reports estimates from unconditional regressions of
weight x∗σ to the volatility-managed factor and a static                                 monthly volatility-managed portfolio returns on original
weight x∗ to the original factor. This policy is equivalent to                           portfolio returns following Eq. (5). The volatility-managed
dynamically adjusting the position (i.e., yt∗ ) in the original                          alpha is annualized by multiplying the monthly esti-
factor according to Eq. (11). We denote the Sharpe ratio                                 mate by 12, and the appraisal ratio for the regression     is
                                                                                                                                             √
earned by this combination strategy as SR(yt∗ ).                                         annualized by multiplying the monthly ﬁgure by 12.
   Moreira and Muir (2017) link their spanning test results                                  The results in Panel A.1 of Table 3 provide strong
to appraisal ratios and utility gains for investors. These                               empirical support for the in-sample beneﬁts of volatility-
types of metrics can be interpreted in the context of                                    managed portfolios. We conﬁrm Moreira and Muir’s
mean-variance portfolio choice. The appraisal ratio for a                                (2017) ﬁnding that the volatility-managed factors often
given scaled strategy is                                                                 generate positive alphas relative to the original factors.
                                                                                         In particular, the volatility-managed MKT, MOM, RMW,
          αˆ
AR =          ,                                                            (12)          ROE, and BAB portfolios have positive and statistically
         σˆ ε                                                                            signiﬁcant alphas at the 1% level, and the managed IA and
where αˆ is the intercept and σˆ ε is the standard error                                 HML alphas are signiﬁcant at the 10% level. Several of the
of the regression in Eq. (5). The squared appraisal ratio                                performance estimates are large in economic magnitude,
reﬂects the extent to which volatility management can be                                 with the volatility-managed momentum alpha of 12.39%
used to increase the slope of the mean-variance frontier                                 per year standing out as particularly striking.17
(e.g., Gibbons et al., 1989):                                                                The large appraisal ratios in Table 3 indicate that
                                                                                         volatility management expands the ex post mean-variance
AR2 = SR(yt∗ )2 − SR(z∗ )2 ,                                               (13)
                                                                                         frontier relative to the original factors, a conclusion that
where       SR(z∗ )
                is the Sharpe ratio earned by a mean-                                    follows from Eqs. (12) and (13). Building on this point,
variance investor who does not have access to the                                        Moreira and Muir (2017) accentuate the large associated
volatility-managed portfolio.15 Similarly, we quantify the                               lifetime utility gains for investors timing volatility. The
in-sample utility gains from volatility management by                                    portfolio strategies required to achieve these beneﬁts,
comparing the CER for the investor who optimizes accord-                                 however, are not implementable for real-time investors.
ing to Eq. (6) with that of the investor who is constrained                              Taking the market factor as an example, the volatility-
to invest in the original factor. We solve for the in-sample                             managed alpha of 4.63% per year and associated appraisal
CER difference analytically as                                                           ratio of 0.32 suggest large potential gains for investors.
                                                                                         Panel A.2 of Table 3 highlights that, to attain these port-
              SR(yt∗ )2 − SR(z∗ )2
CER =                             .                                       (14)          folio results, an investor must know the scaling parameter
                       2γ                                                                for the volatility-managed market factor and, more impor-
   Based on Eq. (13), Moreira and Muir (2017) note that                                  tant, the optimal risky portfolio mixes a 72% weight in the
positive alphas in Eq. (5) indicate that volatility manage-                              volatility-scaled market factor with a 28% weight in the
ment increases Sharpe ratios relative to the original factors.                           original market factor. As shown in Panel A.3, this strategy
They also use a relation similar to Eq. (14) as the basis for                            generates a Sharpe ratio of 0.53 compared with 0.42 for
their conclusion that volatility timing leads to large utility                           the market portfolio. An investor with γ = 5 has a CER of
gains for mean-variance investors.16 These improvements                                  2.79% for the ex post optimal combination strategy versus
                                                                                         only 1.76% for the original factor.
 15
      The investor without access to the volatility-managed factor optimally
                                                                                           17
                     ¯                                                                        The positive unconditional alphas in Table 3 can also be understood
invests z∗ = γ1 σˆft2 in the unscaled factor and earns a squared Sharpe ratio
                      f                                                                  in the context of the volatility-timing effects discussed in Lewellen and
equal to that of the unscaled factor.                                                    Nagel (2006) and Boguth et al. (2011). In particular, the conditional alpha
 16
    To quantify the economic impact of incorporating a given volatility-                 for a given volatility-managed portfolio is, by construction, equal to zero.
managed portfolio into the investment opportunity set, Moreira and Muir                  The corresponding unconditional alpha, however, is likely to be positive
(2017) focus on the “percentage utility gain” rather than on the CER dif-                if the managed portfolio’s conditional factor exposure, c∗ /σˆ t−1
                                                                                                                                                         2
                                                                                                                                                            , covaries
                                          SR (yt∗ )2 −SR (z∗ )2
ference. Their measure is U (% ) =             SR (z∗ )2
                                                                .                        negatively with the conditional volatility of the unscaled factor.
104                            S. Cederburg, M.S. O’Doherty and F. Wang et al. / Journal of Financial Economics 138 (2020) 95–117


Table 3
Spanning regressions.
Panel A.1 reports results from univariate spanning regressions of volatility-managed factor returns on the corresponding original factor returns. The span-
ning regressions are given by f σ ,t = α + β ft + εt , where fσ ,t (ft ) is the monthly return for the volatility-managed (original) factor. The estimates of α are
reported in percentage per year, and the numbers in parentheses are t-statistics based on White (1980) standard errors. For each regression, R2 is the
adjusted R2 value, and the appraisal ratio is computed as the ratio of alpha to root mean square error. Panel A.2 presents the scaling parameter (c∗ ) for
the volatility-managed factor, the ex post optimal total weight in risky assets (x∗σ + x∗ ), and the ex post optimal relative weights in the volatility-managed
(w∗σ ) and original factors (w∗ ). The vector of portfolio weights is [x∗σ x∗ ] = (1/γ ) ˆ −1 μ  ˆ , where γ is the risk aversion parameter, ˆ is the 2 × 2
variance–covariance matrix of fσ ,t and ft , and μ ˆ is the 2 × 1 vector of mean excess returns for fσ ,t and ft . The vector of relative weights is computed as
[w∗σ w∗ ] = [x∗σ x∗ ] /|x∗σ + x∗ |. For each factor, Panel A.3 shows annualized Sharpe ratios and certainty equivalent returns (CERs). The “original factor”
results correspond to the ex post optimal combination of original factor and risk-free asset, and the “combination strategy” results correspond to the ex
post optimal combination of original factor, volatility-managed factor, and risk-free asset. The results in Panels A.2 and A.3 are for γ = 5. Panel B adds the
Fama and French (1993) three factors as controls in the spanning regressions.

                                                                                                     Factor

                                                 MKT           SMB          HML         MOM         RMW           CMA           ROE           IA          BAB
                                                 (1)            (2)          (3)         (4)         (5)           (6)          (7)          (8)          (9)

                                                                Panel A: Univariate regressions

  Panel A.1: Regression results
  Alpha, α (%)                                    4.63        −0.76         1.87       12.39         2.23         0.26          4.97         1.18          5.74
                                                 (3.08)      (−0.87)       (1.88)      (7.31)       (2.57)       (0.39)        (5.10)       (1.83)        (5.97)
  Beta, β                                         0.63          0.63        0.57        0.48         0.59         0.68          0.68         0.70          0.62
                                                (11.32)        (7.75)      (7.65)      (7.13)       (7.10)      (13.82)       (11.12)      (13.59)       (12.97)
  R2                                              0.40          0.40        0.33        0.23         0.34         0.46          0.46         0.50          0.38
  Appraisal ratio, AR                             0.32        −0.09         0.19        0.86         0.36         0.05          0.77         0.26          0.68
  Panel A.2: Ex post optimization parameters
  Scaling parameter, c∗                      10.33              2.63        2.95         4.60        1.48         1.53          2.06         1.64          3.20
  Risky allocation, x∗σ + x∗                  0.61              0.34        0.82         1.22        1.45         1.60          2.44         0.70          2.05
  Relative factor weights
    Vol-managed factor, w∗σ                   0.72            −0.60         0.46         0.98        0.79          0.12         0.97         0.41          0.78
    Original factor, w∗                       0.28             1.60         0.54         0.02        0.21          0.88         0.03         0.59          0.22
  Panel A.3: Portfolio performance measures
  Sharpe ratio
    Original factor                               0.42          0.23        0.40         0.48        0.38          0.53         0.74         0.77          0.77
    Combination strategy                          0.53          0.25        0.44         0.99        0.52          0.54         1.06         0.81          1.03
    Difference                                    0.11          0.02        0.04         0.50        0.14          0.00         0.32         0.04          0.26
  CER (%)
    Original factor                               1.76          0.53        1.59         2.35        1.44         2.85          5.46         5.92         5.90
    Combination strategy                          2.79          0.61        1.94         9.74        2.71         2.88         11.32         6.57        10.52
    Difference                                    1.03          0.08        0.35         7.39        1.27         0.03          5.86         0.65         4.63

                                           Panel B: Additional controls for Fama and French (1993) three factors

  Alpha, α (%)                                    5.24        −0.56         2.52       10.28         3.02        −0.19          5.51         0.66          5.45
                                                 (3.49)      (−0.65)       (2.52)      (6.56)       (3.49)      (−0.28)        (5.52)       (1.01)        (5.72)
  R2                                              0.41         0.40         0.35        0.26         0.43         0.47          0.49         0.51          0.39
  Appraisal ratio, AR                             0.37        −0.07         0.26        0.73         0.72        −0.04          0.88         0.15          0.65




    Panel A.2 of Table 3 indicates that, with the excep-                             to the volatility-scaled factor. The relative weight for the
tion of SMB, the ex post optimal combinations feature                                volatility-managed factor ranges from −60% for SMB to
a positive allocation to the volatility-managed factor.                              98% for MOM, suggesting that there is no obvious ﬁxed
The positive weights follow from the positive spanning                               trading rule across factors. Finally, the total ex post allo-
test alphas for these factors in Panel A.1 in accord with                            cation to the risky asset combination portfolio also differs
Eq. (10).18 Across the nine combination strategies, there                            markedly across the factors. This allocation ranges from
is substantial discrepancy in the optimal weight assigned                            34% for SMB to 244% for ROE.
                                                                                        Panel A.3 of Table 3 conﬁrms that almost all combi-
                                                                                     nation strategies exhibit strong in-sample performance
                                                                                     gains relative to the original factors. The most impressive
  18
     Panel A.2 of Table 3 also shows that the original version of each fac-          Sharpe ratio improvements correspond to the MOM (0.99
tor receives a positive allocation in the ex post optimal combination strat-         for ex post optimal combination portfolio versus 0.48 for
egy. These results suggest that “reverse” spanning tests that regress orig-          original), ROE (1.06 versus 0.74), and BAB (1.03 versus 0.77)
inal factors on their volatility-managed versions should generate a simi-
                                                                                     factors. The CER results also indicate large utility gains for
lar level of support for the unscaled factors as we observe for the scaled
factors in Table 3. We conﬁrm this intuition in the Internet Appendix.               several of the combination portfolios. The ex post MOM
Reverse regressions produce positive intercepts for the original factors in          combination strategy, in particular, boasts a CER of 9.74%
all nine cases, and four of the estimates are signiﬁcant at the 5% level.            per year compared with just 2.35% for the original MOM
The results highlight that spanning tests are unsuitable for identifying
                                                                                     factor. Overall, the results are consistent with Moreira and
whether the original or volatility-managed version of a given strategy is
superior.
                                                                                     Muir’s (2017) ﬁnding that incorporating volatility-managed
                           S. Cederburg, M.S. O’Doherty and F. Wang et al. / Journal of Financial Economics 138 (2020) 95–117                    105


              Table 4
              Summary of spanning regressions: broad sample.
              The table summarizes results from spanning regressions for 103 trading strategies. The spanning regressions are given
              by f σ ,t = α + β ft + εt , where fσ ,t (ft ) is the monthly return for the volatility-managed (original) anomaly portfolio. The
              results in columns (3) and (4) correspond to univariate spanning regressions, and those in columns (5) and (6) are for
              regressions that add the Fama and French (1993) three factors as controls. Panel A reports results for the full set of
              103 trading strategies. Panel B presents separate results for the 9 factors and the 94 anomaly portfolios. Panel C breaks
              the results down by trading strategy type. For each set of regressions, the table reports the number of alphas that
              are positive, positive and signiﬁcant at the 5% level, negative, and negative and signiﬁcant at the 5% level. We assess
              statistical signiﬁcance of the alpha estimates using White (1980) standard errors.

                                                                                                           Additional controls for
                                                                Univariate regressions                  Fama and French (1993) factors

                Sample                       Total       α > 0 [Signif.]       α < 0 [Signif.]        α > 0 [Signif.]       α < 0 [Signif.]
                (1)                           (2)              (3)                    (4)                   (5)                   (6)

                                                               Panel A: Combined sample

                All trading strategies        103            77 [23]                26 [3]                70 [21]               33 [3]

                                                                  Panel B: By category

                Factors                         9              8 [5]                 1 [0]                  7 [6]                2 [0]
                Anomaly portfolios             94            69 [18]                25 [3]                63 [15]               31 [3]

                                                           Panel C: By trading strategy type

                Accruals                       10               8 [3]                2 [0]                  6 [0]                4 [0]
                Intangibles                    10               6 [1]                4 [0]                  5 [0]                5 [0]
                Investment                     11               7 [1]                4 [1]                  5 [1]                6 [1]
                Market                          1               1 [1]                0 [0]                  1 [1]                0 [0]
                Momentum                        9               9 [9]                0 [0]                  9 [9]                0 [0]
                Proﬁtability                   22              19 [2]                3 [0]                 19 [4]                3 [0]
                Trading                        21              14 [4]                7 [1]                 14 [4]                7 [2]
                Value                          19              13 [2]                6 [1]                 11 [2]                8 [0]




factors into the in-sample portfolio choice problem leads                         therefore examine their out-of-sample counterparts to
to substantial gains for investors.                                               assess the value of volatility management for real-time,
    Panel B of Table 3 shows that the general conclu-                             mean-variance investors. When investors are required to
sions are robust to including the three Fama and French                           form trading strategies based on information available at
(1993) factors in the spanning tests as additional con-                           the time, observed performance may differ from the ex
trols. The spanning regression alphas are positive and                            post result for at least two reasons. First, if the conditional
statistically signiﬁcant at the 1% level for the MKT, HML,                        risk-return trade-off for a given factor is unstable over
MOM, RMW, ROE, and BAB factors. The tests indicate that                           time, past data are less likely to be informative about the
volatility-managed factors remain important for investors                         future potential for volatility management. Along these
who form ex post optimal portfolios with an investment                            lines, Whitelaw (1994), Harvey (2001), Brandt and Kang
opportunity set augmented to include the MKT, SMB, and                            (2004), Ludvigson and Ng (2007), and Lettau and Ludvig-
HML factors.                                                                      son (2010) provide evidence of instability in the risk-return
    We also present new evidence on the in-sample ben-                            relation for the market factor. Second, estimation risk is
eﬁts of volatility management by applying the tests in                            a key concern in the real-time portfolio choice problem
Table 3 to the combined sample of 103 trading strategies.                         implied by Eq. (5), as weights are often unstable and the
The results are summarized in Table 4, with detailed                              corresponding optimal portfolios tend to perform poorly
results available in the Internet Appendix. We ﬁnd that 77                        out of sample (e.g., Black and Litterman, 1992; Green and
of the 103 scaled portfolios earn positive alphas in univari-                     Holliﬁeld, 1992; Jagannathan and Ma, 2003; DeMiguel
ate spanning tests and, accordingly, are assigned positive                        et al., 2009a; 2009b).
weights in the ex post optimal combination portfolios.                                Given these concerns, we examine whether in-
Twenty-three of the positive estimates are statistically                          vestors would have beneﬁted from volatility man-
signiﬁcant at the 5% level. The regression speciﬁcation                           agement based on information available in real time.
that adds the Fama and French (1993) controls produces                            Section 4.3.1 details the design of our out-of-sample tests,
70 positive alphas, 21 of which are statistically signiﬁcant.                     and Section 4.3.2 presents the corresponding results.
The broad-based results from Table 4 provide additional                           Section 4.3.3 discusses the underlying economic drivers of
support for Moreira and Muir’s (2017) general conclusions                         the differences between our in-sample and out-of-sample
on the in-sample value of volatility management.                                  evidence.

4.3. Out-of-sample tests                                                          4.3.1. Out-of-sample strategy design
                                                                                      We adopt a standard real-time portfolio choice de-
   The trading strategies suggested by the in-sample                              sign. We start with a sample of T monthly excess return
spanning tests are not implementable in real time. We                             observations for a given factor or anomaly portfolio.
106                           S. Cederburg, M.S. O’Doherty and F. Wang et al. / Journal of Financial Economics 138 (2020) 95–117


Table 5
Real-time combination strategies.
The table reports results for portfolio strategies that combine original factors and volatility-managed factors. We specify an initial training period length of
K = 120 months and use an expanding-window design for the out-of-sample tests. The out-of-sample period runs from month K + 1 to month T, where T
is the total number of sample months for a given factor. In Panel A, the “combination strategy (real time)” results correspond to the real-time combination
of original factor, volatility-managed factor, and risk-free asset, and the “combination strategy (ex post optimal)” results correspond to the ex post optimal
combination of these assets over the out-of-sample period. The “original factor (real time)” results correspond to the real-time combination of original
factor and risk-free asset. The strategies in Panel B include the Fama and French (1993) factors in the investment opportunity set. For each strategy, the
table shows the annualized Sharpe ratio and certainty equivalent return (CER) in percentage per year over the out-of-sample period. The ﬁgures in brackets
are p-values for the Sharpe ratio and CER differences. The p-values are computed following the approaches in Jobson and Korkie (1981) and DeMiguel et al.
(2009b), respectively. We use a risk aversion parameter of γ = 5 and impose a leverage constraint that the sum of absolute weights on the risky factors is
less than or equal to ﬁve.

                                                                                                           Factor

                                                                MKT        SMB        HML       MOM        RMW        CMA          ROE          IA      BAB
                                                                (1)         (2)        (3)       (4)        (5)        (6)         (7)         (8)      (9)

                                                         Panel A: Real-time combination strategies

  Sharpe ratio
    [S1] Combination strategy (real time)                        0.42       0.14      0.38       0.92       0.44       0.52          1.13      0.70      1.09
    [S2] Original factor (real time)                             0.46       0.19      0.43       0.49       0.31       0.56          0.78      0.68      0.79
    Difference, [S1]–[S2]                                      −0.04      −0.06     −0.06        0.44       0.13     −0.03           0.36      0.02      0.30
                                                                [0.64]     [0.37]    [0.41]     [0.00]     [0.53]     [0.20]        [0.00]    [0.74]    [0.00]
      [S3] Combination strategy (ex post optimal)                0.53       0.26      0.50       0.99       0.58       0.64          1.21      0.73      1.11
      Difference, [S1]–[S3]                                    −0.11      −0.12     −0.12      −0.07      −0.14      −0.11         −0.07     −0.03     −0.02
                                                                [0.01]     [0.14]    [0.08]     [0.07]     [0.37]     [0.00]        [0.20]    [0.41]    [0.78]
  CER (%)
    [S1] Combination strategy (real time)                        1.56       0.00      1.41       8.47       1.96       2.74        12.25       4.19    10.88
    [S2] Original factor (real time)                             1.75       0.38      1.61       2.29       0.91       3.09          5.44      3.68      6.23
    Difference, [S1]–[S2]                                      −0.19      −0.37     −0.20        6.18       1.04     −0.35           6.81      0.51      4.65
                                                                [0.83]     [0.27]    [0.73]     [0.00]     [0.57]     [0.21]        [0.00]    [0.60]    [0.00]
      [S3] Combination strategy (ex post optimal)                2.79       0.67      2.47       9.87       3.42       4.04        14.55       5.36    12.34
      Difference, [S1]–[S3]                                    −1.23      −0.66     −1.06      −1.40      −1.46      −1.30         −2.30     −1.17     −1.46
                                                                [0.01]     [0.13]    [0.10]     [0.07]     [0.39]     [0.03]        [0.15]    [0.25]    [0.30]

                                Panel B: Real-time combination strategies including Fama and French (1993) three factors

  Sharpe ratio
    [S1] Combination strategy (real time)                        0.51       0.50      0.53       1.14       0.83       0.77          1.30      0.94      1.19
    [S2] Original factor + FF3 (real time)                       0.61       0.61      0.61       0.94       0.85       0.80          1.23      0.97      0.98
    Difference, [S1] and [S2]                                  −0.11      −0.11     −0.08        0.20     −0.02      −0.03           0.07    −0.03       0.20
                                                                [0.22]     [0.03]    [0.31]     [0.00]     [0.85]     [0.12]        [0.23]    [0.10]    [0.00]
      [S3] Combination strategy (ex post optimal)                0.72       0.71      0.71       1.28       1.11       0.98          1.63      1.09      1.38
      Difference, [S1]–[S3]                                    −0.22      −0.21     −0.18      −0.14      −0.28      −0.21         −0.33     −0.15     −0.20
                                                                [0.00]     [0.01]    [0.03]     [0.01]     [0.00]     [0.01]        [0.00]    [0.01]    [0.00]
  CER (%)
    [S1] Combination strategy (real time)                        2.51       2.13      2.72     12.88        6.43       5.54     16.25          8.73    13.70
    [S2] Original factor + FF3 (real time)                       2.52       2.52      2.52       8.75       6.63       6.07     14.88          9.33      9.66
    Difference, [S1] and [S2]                                  −0.02      −0.40       0.20       4.13     −0.19      −0.53       1.38        −0.60       4.04
                                                                [0.99]     [0.21]    [0.77]     [0.00]     [0.92]     [0.13]    [0.25]        [0.11]    [0.00]
      [S3] Combination strategy (ex post optimal)                5.21       5.05      5.09     16.39      12.33        9.60     26.53        11.79     19.11
      Difference, [S1]–[S3]                                    −2.71      −2.93     −2.37      −3.51      −5.89      −4.06     −10.28        −3.06     −5.42
                                                                [0.00]     [0.02]    [0.04]     [0.02]     [0.00]     [0.01]    [0.00]        [0.01]    [0.00]




We use the ﬁrst K months as the initial training period                                 We acknowledge that readers can reasonably disagree
and evaluate portfolio performance over the subsequent                              on the preferred design choices. For example, although
out-of-sample period of T − K months. For our base case                             a longer initial training period would reduce test power,
results, we specify an initial training sample of K = 120                           such a design would result in more precise parameter es-
months and employ an expanding-window approach to                                   timates early in the out-of-sample period. Rolling-window
estimate the relevant portfolio parameters. Our choice                              estimation could also be preferable to expanding-window
of initial training sample length allows for a relatively                           estimation if the likelihood and magnitude of structural
long out-of-sample evaluation period for each strategy,                             breaks in the data generating process are large (e.g.,
which alleviates the well-known concern with low power                              Pesaran and Timmermann, 2002; Rossi, 2013). Ex ante,
in out-of-sample tests (e.g., Inoue and Kilian, 2004). The                          it is challenging to identify which design choices are
expanding-window speciﬁcation also mitigates estimation                             most appropriate. As such, we conduct an extensive set of
risk throughout the evaluation period, as investors are                             robustness checks to conﬁrm that our conclusions are not
able to make full use of past data in estimating return                             sensitive to the speciﬁed training sample length or type.
moments.                                                                                As suggested by Eq. (11), a real-time investor needs es-
                                                                                    timates of the scaling parameter for the volatility-managed
                                            S. Cederburg, M.S. O’Doherty and F. Wang et al. / Journal of Financial Economics 138 (2020) 95–117                                        107


factor and the weights to assign to the volatility-managed                                       also calculate out-of-sample CER gains from having access
and original factors in the optimal combination strategy. At                                     to the volatility-scaled factor as
the beginning of each month t in the out-of-sample period,                                                   γ            γ 
we ﬁrst compute the real-time scaling parameter, ct , as the                                     CER = μˆ i − σˆ i2 − μˆ j − σˆ j2 .                                               (18)
                                                                                                                         2                         2
constant that allows the original and volatility-managed
                                                                                                 We evaluate statistical signiﬁcance of the CER difference
factors to have the same variance over the training pe-
                                                                                                 using the method outlined by DeMiguel et al. (2009b).19
riod preceding month t. We then estimate the vector of
mean excess returns (μ   ˆ t ) and the covariance matrix ( ˆ t )
                                                                                                 4.3.2. Out-of-sample results
from the training period and construct portfolio weights
                                                                                                     Panel A of Table 5 shows results from out-of-sample
according to
                                                                                               tests for the nine factors. We compare the performance
    xσ ,t           1 ˆ −1                                                                       of the real-time combination strategy and that of the
                =                μˆ t .                                            (15)
     xt             γ        t                                                                   real-time strategy that excludes the volatility-managed
                                                                                                 portfolio. As a benchmark, we also present the perfor-
The investment position in the original factor is given by
                                                                                                 mance of the ex post optimal combination portfolio. The
the real-time version of Eq. (11):
                                                                                                 Sharpe ratios and CERs of the strategies in Table 5 are
                        ct                                                                       calculated over the out-of-sample evaluation period from
yt = xσ ,t                         + xt .                                          (16)
                    σˆ t−1
                        2                                                                        month K + 1 to month T.
                                                                                                     For the base case design in Panel A, the combination
We construct the portfolio excess return for month t as                                          portfolios outperform the original factors in ﬁve of the
yt ft , and the outcome of this approach is a time series of                                     nine cases. The differences in Sharpe ratios and CERs are
T − K monthly excess returns.                                                                    positive for the MOM, RMW, ROE, IA, and BAB factors and
      Before proceeding, we note that the magnitude of                                           negative for the MKT, SMB, HML, and CMA factors. The
the investment position in a given real-time strategy                                            improvements for the MOM, ROE, and BAB factors are
(i.e., |yt |) is a measure of leverage. The out-of-sample                                        statistically signiﬁcant at the 1% level. Across the remain-
approach to estimating these positions leads to strategies                                       ing six strategies, the Sharpe ratio and CER differences
that require extreme leverage for at least two reasons.                                          are insigniﬁcant, with the CER differences ranging from
First, volatility-managed portfolios, by nature, call for                                        −0.37% (SMB) to 1.04% (RMW) per year.
the use of substantial leverage to gain aggressive factor                                            The market factor is an interesting case, as Moreira and
exposures following periods of low volatility. Second,                                           Muir (2017, p. 1618) point out that “this strategy would
sample-based mean-variance optimization often leads to                                           have been easily available to the average investor in real
extreme values for estimates of portfolio weights [i.e., Eq.                                     time.” Achieving the gains from volatility management in
(15)], particularly when the training period is short (e.g.,                                     an out-of-sample setting turns out to be diﬃcult, however,
DeMiguel et al., 20 09a; 20 09b). For our base case, we                                          as the combination strategy underperforms relative to the
impose a leverage constraint of |yt | ≤ 5. This design choice                                    original market portfolio based on Sharpe ratio (0.42 ver-
reﬂects our desire to maintain the spirit of volatility-                                         sus 0.46) and CER (1.56% versus 1.75% per year).20 In the
managed strategies while simultaneously guarding against                                         Internet Appendix, we demonstrate why the out-of-sample
our results being driven by extreme outliers. We also                                            combination strategy for the market portfolio performs
conﬁrm that our conclusions are robust to imposing                                               poorly. In particular, we show that the strong in-sample
leverage constraints as low as one, as well as allowing for                                      performance for volatility-scaled MKT is concentrated in
unconstrained investment positions.                                                              the period surrounding the Great Depression, which occurs
      In evaluating the performance of the real-time com-                                        early in the sample. Out-of-sample investors adopting the
bination portfolios, we focus on whether or not these                                            combination strategy tend to favor the volatility-managed
strategies lead to improved investment outcomes relative                                         version of the market factor based on its strong early
to the original factors. This focus is intentionally practical,                                  sample performance. These investors experience unfavor-
as the out-of-sample tests are not directly informative                                          able investment results, however, because the scaled MKT
about the underlying risk-return trade-off for the strate-
gies of interest. Let μˆ i and σˆ i be the mean and standard
                                                                                                  19
                                                                                                     To test the null hypothesis of equal CERs for strategies i and j,
deviation of excess returns for the strategy that invests
                                                                                                 we compute the following test statistic, which is asymptotically dis-
in the volatility-managed portfolio, original portfolio, and                                                                            (μˆ i − γ2 σˆ i2 )√−(μˆ j − γ2 σˆ j2 ) , where θˆ =
                                                                                                 tributed as a standard normal: zˆDGU =
risk-free asset (i.e., the real-time combination strategy)                                           ⎛                                   ⎡                                   ⎤⎡         ⎤⎞
                                                                                                                                                                 θˆ
over the out-of-sample period of length T − K. Similarly,                                                                                 σˆ i2     σˆ i, j     0          0         1
                                                                                                      ⎜                               ⎢σˆ i, j    σˆ j2       0          0 ⎥⎢ −1 ⎥⎟
μˆ j and σˆ j are the mean and standard deviation of excess                                        1 ⎜
                                                                                                 T −K ⎝ 1      −1       −γ / 2     γ /2 ⎢
                                                                                                                                        ⎣0                                    2 ⎦⎣
                                                                                                                                                                                  ⎥       ⎦⎟.
                                                                                                                                                       0      2σˆ i4     2σˆ i, j   −γ / 2 ⎠
returns for the real-time strategy that invests in the orig-                                                                                 0         0      2σˆ i,2j   2σˆ j4     γ /2
inal portfolio and risk-free asset, and σˆ i, j is the covariance                                 20
                                                                                                      The real-time analysis for the market factor is similar in spirit to
between excess returns for the two strategies. We compute                                        Johannes et al.’s (2014) comparison of the out-of-sample performance
the Sharpe ratio difference as                                                                   of a “stochastic variance-constant mean” model with that of a “con-
                                                                                                 stant variance-constant mean” model. They adopt a Bayesian learning ap-
                μˆ i μˆ j
SR =               −                                                              (17)          proach to optimal allocation that accounts for parameter uncertainty and
                σˆ i σˆ j                                                                        ﬁnd that the model speciﬁcation with stochastic volatility leads to bet-
                                                                                                 ter Sharpe ratios and CERs. Consistent with our evidence on the market
and assess whether the difference is statistically signiﬁcant                                    factor in Table 5, however, the performance differences tend to be statis-
using the test proposed by Jobson and Korkie (1981). We                                          tically insigniﬁcant.
108                     S. Cederburg, M.S. O’Doherty and F. Wang et al. / Journal of Financial Economics 138 (2020) 95–117


factor underperforms the original MKT factor after the ﬁrst                      To assess whether our conclusions for the nine factors
ten years of the sample.                                                     generalize, we turn to the broader sample of 103 trad-
    Table 5 also compares Sharpe ratios and CERs for the                     ing strategies. Table 6 summarizes the results for out-of-
real-time combination strategies and the ex post optimal                     sample tests using our base case design with an expanding,
combination strategies. These results provide insights into                  ten-year training sample, a leverage constraint of |yt | ≤ 5,
how much the real-time portfolio formation approach                          and a risk aversion parameter of γ = 5. We report in Panel
leads to a deterioration in performance relative to the                      A.1 the number of positive and negative differences in
in-sample exercise. All nine of the Sharpe ratio and CER                     Sharpe ratios and CERs. As in Table 5, a positive perfor-
differences are negative, and four of the differences for                    mance difference indicates that the real-time combination
each of the two measures are statistically signiﬁcant at the                 strategy earns a higher Sharpe ratio or CER than the alter-
10% level.                                                                   native strategy does. We also show the number of signiﬁ-
    Moreira and Muir (2017) provide evidence that                            cant differences at the 5% level. Panel A.2 presents separate
volatility-managed factors also tend to produce pos-                         results for the 9 factors and 94 anomaly portfolios, and
itive alphas in spanning regressions that include the                        Panel A.3 breaks the results down by trading strategy type.
original factors as well as the MKT, SMB, and HML factors                        The evidence in Panel A of Table 6 suggests that the
from the Fama and French (1993) three-factor model. The                      real-time combination strategies tend to underperform the
interpretation of a positive alpha from this test is that an                 real-time strategies that exclude the volatility-managed
investor who holds the ex post optimal combination of the                    portfolios. Only 45 of the 103 combination portfolios
benchmark factors increases her Sharpe ratio by adding                       outperform the original portfolios based on Sharpe ratio.
a positive position in the volatility-managed factor. From                   Just 31 outperform based on CER. Further, the number
an economic perspective, including the Fama and French                       of signiﬁcantly positive CER differences (seven) exactly
(1993) factors as controls likely provides a better charac-                  matches the number of signiﬁcantly negative ones. All
terization of the investment opportunity set for investors                   but one of the 103 real-time combination strategies ex-
sophisticated enough to consider volatility-managed                          hibit underperformance relative to the ex post optimal
strategies. As in the univariate spanning tests, however,                    strategies based on Sharpe ratio, and all 103 underperform
the implied optimal strategies are not implementable in                      based on CER.21 A large proportion of the performance
real time. Optimizing across a larger set of assets may also                 differences relative to the ex post optimal strategies are
exacerbate estimation risk.                                                  statistically signiﬁcant (39 out of 103 based on Sharpe
    We examine the real-time performance of strategies                       ratio and 41 out of 103 based on CER).
that include the Fama and French (1993) three factors                            Panel B presents results for real-time trading strategies
in Panel B of Table 5. We report Sharpe ratios and CERs                      based on an investment opportunity set that includes
for real-time strategies that either exclude or include the                  the Fama and French (1993) factors. The conclusions are
volatility-managed factor. The results indicate that incor-                  similar to those in Panel A. The real-time strategies that in-
porating volatility-managed strategies into the portfolio                    clude volatility-managed portfolios outperform those that
choice problem is often harmful to investors with the ex-                    exclude them in just 32 out of 103 cases based on either
tended investment opportunity set. Based on Sharpe ratio                     Sharpe ratio or CER. The number of signiﬁcantly positive
comparisons the strategies that include volatility-managed                   results is also small in each case (two for Sharpe ratio and
portfolios underperform for six of the nine factors. The                     three for CER). The majority of the real-time combination
MOM and BAB factors produce signiﬁcantly positive Sharpe                     strategies also exhibit statistically signiﬁcant underperfor-
ratio differences, but the volatility-managed SMB and IA                     mance relative to their ex post optimal versions.
factors signiﬁcantly hurt performance. The nine factors                          Table 7 summarizes results for robustness tests that
produce four positive and ﬁve negative CER differences,                      modify the base case out-of-sample design. For each
indicating that volatility timing does not systematically                    design and performance measure, we report the number
improve performance for investors with access to the                         of positive and negative differences for the real-time
Fama and French (1993) three factors. For both the Sharpe                    strategies and the number of these differences that are
ratio and CER comparisons, all nine of the real-time                         statistically signiﬁcant at the 5% level. We also report the
combination strategies exhibit statistically signiﬁcant un-                  p-value from a binomial test of the null hypothesis that
derperformance at the 5% level relative to the ex post                       positive and negative performance differences are equally
optimal combination strategies.                                              likely. The ﬁrst row in Panel A of Table 7 repeats the
    In summary, Table 5 shows that volatility management                     results from our base case design in Panel A of Table 6.
has potential beneﬁts for real-time investors in some                        The remaining rows in this panel display robustness re-
factors, but the gains are not systematic and are much less                  sults pertaining to the training sample type, risk aversion
impressive than the corresponding in-sample results. These                   parameter, training sample length, and leverage con-
initial results indicate that real-time implementation issues                straint. None of the alternative speciﬁcations meaningfully
degrade portfolio performance in the volatility-managed                      improves performance relative to the base case.
portfolios setting. Panel B of Table 5 also highlights that,
relative to the results in Panel A with the investment
universe restricted to a single factor, volatility-managed                     21
                                                                                  The ex post optimal strategy is based on a ﬁxed scaling parameter for
portfolios are even less useful to investors with access to
                                                                             the volatility-managed portfolio and ﬁxed portfolio weights such that it
market, size, and value strategies.                                          is possible for a real-time strategy with time-varying portfolio weights to
                                                                             outperform the ex post optimal strategy.
                              S. Cederburg, M.S. O’Doherty and F. Wang et al. / Journal of Financial Economics 138 (2020) 95–117                            109




Table 6
Summary of real-time combination strategies: broad sample.
The table summarizes results for real-time strategies that combine original and volatility-managed versions of 103 trading strategies. For each factor or
anomaly portfolio, we compute the Sharpe ratio and certainty equivalent return (CER) for (i) the real-time strategy that combines the original portfolio,
the volatility-managed portfolio, and the risk-free asset (“combination strategy (real time)”), (ii) the real-time strategy that combines the original portfolio
and the risk-free asset (“original factor (real time)”), and (iii) the ex post optimal strategy that combines the original portfolio, the volatility-managed
portfolio, and the risk-free asset (“combination strategy (ex post optimal)”). Columns (3) and (4) in Panel A summarize the Sharpe ratio differences for
these strategies, and columns (5) and (6) summarize the CER differences. Panel B summarizes the Sharpe ratio and CER differences for analogous strategies
that include the Fama and French (1993) factors. A positive Sharpe ratio or CER difference indicates outperformance for the real-time combination strategy.
The out-of-sample tests are based on a ten-year training period and an expanding-window design. We use a risk aversion parameter of γ = 5 and impose
a leverage constraint that the sum of absolute weights on the risky assets is less than or equal to ﬁve. Panels A.1 and B.1 report results for the full set
of 103 trading strategies. Panels A.2 and B.2 present separate results for the 9 factors and the 94 anomaly portfolios. Panels A.3 and B.3 break the results
down by trading strategy type. For each set of comparisons, the table reports the number of differences that are positive (+), positive and signiﬁcant at the
5% level (in brackets), negative (−), and negative and signiﬁcant at the 5% level (in brackets). We assess statistical signiﬁcance of the Sharpe ratio and CER
differences using the approaches in Jobson and Korkie (1981) and DeMiguel et al. (2009b), respectively.

                                                          Panel A: Real-time combination strategies

                                                                Sharpe ratio difference:                                   CER difference:
                                                          Combination strategy (real time) versus               Combination strategy (real time) versus

                                                        Original factor         Combination strategy           Original factor         Combination strategy
                                                         (real time)              (ex post optimal)             (real time)              (ex post optimal)

                                                             SR                        SR                         CER                       CER
  Sample                                Total                +/−                         +/−                         + /−                       + /−
  (1)                                    (2)                 (3)                         (4)                         (5)                        (6)

  Panel A.1: Combined sample
  All trading strategies                103            45 [8] / 58 [2]            1 [0] / 102 [39]            31 [7] / 72 [7]            0 [0] / 103 [41]
  Panel A.2: By category
  Factors                                 9             5 [3] / 4 [0]             0 [0] / 9 [2]                5 [3] / 4 [0]             0 [0] / 9 [2]
  Anomaly portfolios                     94            40 [5] / 54 [2]            1 [0] / 93 [37]             26 [4] / 68 [7]            0 [0] / 94 [39]
  Panel A.3: By trading strategy type
  Accruals                               10             3 [0] / 7 [1]             0 [0] / 10 [5]                3 [0] / 7 [2]            0 [0] / 10 [4]
  Intangibles                            10             4 [0] / 6 [0]             0 [0] / 10 [0]                1 [0] / 9 [1]            0 [0] / 10 [4]
  Investment                             11             5 [0] / 6 [0]             0 [0] / 11 [6]                5 [0] / 6 [0]            0 [0] / 11 [5]
  Market                                  1             0 [0] / 1 [0]             0 [0] / 1 [1]                 0 [0] / 1 [0]            0 [0] / 1 [1]
  Momentum                                9             8 [4] / 1 [0]             0 [0] / 9 [5]                 8 [5] / 1 [0]            0 [0] / 9 [5]
  Proﬁtability                           22            10 [1] / 12 [0]            1 [0] / 21 [7]                6 [1] / 16 [1]           0 [0] / 22 [5]
  Trading                                21            10 [1] / 11 [1]            0 [0] / 21 [6]                6 [1] / 15 [1]           0 [0] / 21 [8]
  Value                                  19             5 [2] / 14 [0]            0 [0] / 19 [9]                2 [0] / 17 [2]           0 [0] / 19 [9]

                                Panel B: Real-time combination strategies including Fama and French (1993) three factors

                                                               Sharpe ratio difference:                                   CER difference:
                                                         Combination strategy (real time) versus               Combination strategy (real time) versus

                                                     Original factor+FF3       Combination strategy          Original factor+FF3       Combination strategy
                                                         (real time)             (ex post optimal)               (real time)             (ex post optimal)

                                                             SR                        SR                         CER                       CER
  Sample                                Total                +/−                         +/−                         +/−                        +/−
  (1)                                    (2)                 (3)                         (4)                         (5)                        (6)

  Panel B.1: Combined sample
  All trading strategies                103            32 [2] / 71 [13]           0 [0] / 103 [77]            32 [3] / 71 [10]           0 [0] / 103 [92]
  Panel B.2: By category
  Factors                                 9             3 [2] / 6 [1]             0 [0] / 9 [9]                4 [2] / 5 [0]             0 [0] / 9 [9]
  Anomaly portfolios                     94            29 [0] / 65 [12]           0 [0] / 94 [68]             28 [1] / 66 [10]           0 [0] / 94 [83]
  Panel B.3: By trading strategy type
  Accruals                               10             3 [0] / 7 [1]             0 [0] / 10 [8]                3 [0] / 7 [1]            0 [0] / 10 [8]
  Intangibles                            10             1 [0] / 9 [1]             0 [0] / 10 [5]                1 [0] / 9 [1]            0 [0] / 10 [9]
  Investment                             11             3 [0] / 8 [1]             0 [0] / 11 [10]               3 [0] / 8 [1]            0 [0] / 11 [10]
  Market                                  1             0 [0] / 1 [0]             0 [0] / 1 [1]                 0 [0] / 1 [0]            0 [0] / 1 [1]
  Momentum                                9             8 [1] / 1 [0]             0 [0] / 9 [9]                 7 [2] / 2 [0]            0 [0] / 9 [9]
  Proﬁtability                           22             8 [0] / 14 [2]            0 [0] / 22 [14]               9 [0] / 13 [2]           0 [0] / 22 [18]
  Trading                                21             6 [1] / 15 [5]            0 [0] / 21 [21]               5 [1] / 16 [3]           0 [0] / 21 [21]
  Value                                  19             3 [0] / 16 [3]            0 [0] / 19 [9]                4 [0] / 15 [2]           0 [0] / 19 [16]
110                            S. Cederburg, M.S. O’Doherty and F. Wang et al. / Journal of Financial Economics 138 (2020) 95–117


Table 7
Summary of real-time combination strategies: robustness tests.
The table summarizes robustness tests for real-time strategies that combine original and volatility-managed versions of 103 trading strategies. For each
portfolio, we compute the Sharpe ratio and certainty equivalent return (CER) for (i) the real-time strategy that combines the original portfolio, the volatility-
managed portfolio, and the risk-free asset and (ii) the real-time strategy that combines the original portfolio and the risk-free asset. Column (2) in Panel
A summarizes the Sharpe ratio differences for these strategies, and column (4) summarizes the CER differences. Panel B summarizes the Sharpe ratio
and CER differences for analogous strategies that include the Fama and French (1993) factors. For each set of comparisons, the table reports the number of
differences that are positive (+), positive and signiﬁcant at the 5% level (in brackets), negative (−), and negative and signiﬁcant at the 5% level (in brackets).
A positive Sharpe ratio or CER difference indicates outperformance for the real-time combination strategy that includes the volatility-managed portfolio.
We assess statistical signiﬁcance of the Sharpe ratio and CER differences using the approaches in Jobson and Korkie (1981) and DeMiguel et al. (2009b),
respectively. For each set of comparisons, we also present the two-tailed p-value from a binomial distribution test of the null hypothesis that each of the
differences is equally likely to be positive or negative. The ﬁrst row in each panel summarizes results from the base case design in Table 6. This design is
characterized by (i) an expanding-window training sample, (ii) an initial training sample length of K = 120 months, (iii) a risk aversion parameter of γ = 5,
and (iv) a leverage constraint of L ≤ 5. The subsequent rows in each panel are based on modiﬁed designs as described in the table.

                                                                               Sharpe ratio difference:                                CER difference:
                                                                                     (N = 103)                                           (N = 103)

                                                                              SR                    Binomial                  CER                      Binomial
  Description                                                                 +/−                     p-value                   + /−                      p-value
  (1)                                                                         (2)                       (3)                     (4)                         (5)

                                                          Panel A: Real-time combination strategies

  Base case design                                                       45 [8] / 58 [2]               0.237              31 [7] / 72 [7]                 0.000
  Rolling-window training sample                                         49 [2] / 54 [1]               0.694              17 [1] / 86 [19]                0.000
  Risk aversion, γ = 2                                                   48 [9] / 55 [2]               0.555              35 [8] / 68 [7]                 0.001
  Risk aversion, γ = 10                                                  45 [8] / 58 [2]               0.237              31 [7] / 72 [7]                 0.000
  Initial training sample length, K = 240                                45 [9] / 58 [10]              0.237              36 [8] / 67 [11]                0.003
  Initial training sample length, K = 360                                40 [9] / 63 [6]               0.030              31 [8] / 72 [8]                 0.000
  Leverage constraint, L ≤ 1.0                                          49 [10] / 54 [2]               0.694              38 [4] / 65 [5]                 0.010
  Leverage constraint, L ≤ 1.5                                          47 [10] / 56 [3]               0.431              38 [7] / 65 [7]                 0.010
  Leverage constraint, L ≤ ∞                                             45 [8] / 58 [2]               0.237              31 [7] / 72 [7]                 0.000

                                Panel B: Real-time combination strategies including Fama and French (1993) three factors

  Base case design                                                      32 [2] / 71 [13]               0.000              32 [3] / 71 [10]                0.000
  Rolling-window training sample                                        32 [0] / 71 [8]                0.000              20 [0] / 83 [16]                0.000
  Risk aversion, γ = 2                                                  22 [3] / 81 [13]               0.000              24 [3] / 79 [10]                0.000
  Risk aversion, γ = 10                                                 31 [3] / 72 [12]               0.000              32 [3] / 71 [10]                0.000
  Initial training sample length, K = 240                               31 [6] / 72 [11]               0.000              35 [9] / 68 [10]                0.001
  Initial training sample length, K = 360                               30 [6] / 73 [9]                0.000              28 [7] / 75 [9]                 0.000
  Leverage constraint, L ≤ 1.0                                          22 [2] / 81 [11]               0.000              27 [3] / 76 [12]                0.000
  Leverage constraint, L ≤ 1.5                                          21 [3] / 82 [13]               0.000              26 [2] / 77 [9]                 0.000
  Leverage constraint, L ≤ ∞                                            31 [3] / 72 [12]               0.000              32 [3] / 71 [11]                0.000



    The robustness design with rolling-window parameter                              |yt | ≤ 1.5 as well as an unconstrained speciﬁcation, but
estimation leads to a slightly larger number of positive                             the performance of the combination strategies does not
Sharpe ratio differences but a substantially smaller num-                            systematically improve for these cases.
ber of positive CER differences. Using a lower (γ = 2) or                                 In summary, our main conclusions from Panel A of
higher (γ = 10) risk aversion parameter leads to almost                              Table 6 continue to hold across the robustness results in
identical results to the base case with γ = 5.                                       Panel A of Table 7. Incorporating volatility-managed port-
    One potential concern with the ten-year training sam-                            folios into the real-time portfolio decision tends to harm
ple in our base case is the relatively small number of                               performance. More than half of the Sharpe ratio and CER
observations used to estimate portfolio positions early in                           differences are negative under each speciﬁcation. The CER
the out-of-sample period. We therefore consider speciﬁca-                            results, in particular, generate strong statistical evidence
tions with 20-year (K = 240) and 30-year (K = 360) initial                           against using volatility-managed portfolios in real-time
estimation periods. These designs produce roughly the                                applications. All nine of the binomial p-values for the CER
same number of positive Sharpe ratio and CER differences                             differences produce statistical rejections of the null hy-
that the base case does. If anything, these robustness                               pothesis of equal performance at the 5% signiﬁcance level.
results are less favorable for volatility management, as the                              Finally, Panel B of Table 7 summarizes our robustness
number of signiﬁcantly negative performance differences                              tests for speciﬁcations that include the Fama and French
is much higher in the K = 240 case.                                                  (1993) three factors. Each of the robustness speciﬁcations
    The ﬁnal three rows in Panel A of Table 7 detail the                             produces similar evidence against volatility management,
impact of alternative leverage constraints. Imposing a                               and all 18 binomial p-values reject the null hypothesis of
leverage constraint could either improve performance if                              equal performance differences at the 1% level. Overall, our
real-time investors avoid taking extreme positions or hurt                           ﬁndings in this section indicate that attempting to use
performance if the constraint prevents investors from                                volatility management in real time tends to degrade per-
capitalizing on the information content in lagged volatility.                        formance relative to constraining the investment universe
We consider tighter leverage constraints of |yt | ≤ 1.0 and                          to the original factors and anomaly portfolios.
                              S. Cederburg, M.S. O’Doherty and F. Wang et al. / Journal of Financial Economics 138 (2020) 95–117                             111


Table 8
Comparison of volatility-managed strategies with traditional anomaly strategies: broad sample.
Panel A summarizes results on the performance of volatility-managed versions of 103 trading strategies. The spanning regression tests are described in
Table 4, and the tests for Sharpe ratio differences and certainty equivalent return (CER) differences are described in Table 6. Panel B summarizes results from
analogous tests for 102 anomaly-based trading strategies. The in-sample tests are CAPM regressions and Fama and French (1993) three-factor regressions.
For each set of regressions, the table reports the number of alphas that are positive (+), positive and signiﬁcant at the 5% level (in brackets), negative
(−), and negative and signiﬁcant at the 5% level (in brackets). We assess statistical signiﬁcance of the alpha estimates using White (1980) standard errors.
For the out-of-sample tests for a given anomaly portfolio, we compute the Sharpe ratio and CER for (i) the real-time strategy that combines the anomaly
portfolio, the market portfolio, and the risk-free asset and (ii) the real-time strategy that combines the market portfolio and the risk-free asset. We also
compute Sharpe ratios and CERs for analogous strategies that include the Fama and French (1993) factors. Column (5) in Panel B summarizes the Sharpe
ratio differences for these strategies, and column (7) summarizes the CER differences. A positive Sharpe ratio or CER difference indicates outperformance
for the real-time strategy that includes the anomaly portfolio. The out-of-sample tests are based on a ten-year training period and an expanding-window
design. We use a risk aversion parameter of γ = 5 and impose a leverage constraint that the sum of absolute weights on the risky assets is less than or
equal to ﬁve. For each set of comparisons, the table reports the number of differences that are positive (+), positive and signiﬁcant at the 5% level (in
brackets), negative (−), and negative and signiﬁcant at the 5% level (in brackets). We assess statistical signiﬁcance of the Sharpe ratio and CER differences
using the approaches in Jobson and Korkie (1981) and DeMiguel et al. (2009b), respectively. For each set of comparisons, we also present the two-tailed
p-value from a binomial distribution test of the null hypothesis that each of the performance measures is equally likely to be positive or negative.

                                                                      Alpha:                   Sharpe ratio difference:              CER difference:

                                                                α              Binomial           SR            Binomial           CER           Binomial
  Description                                  Total           + /−             p-value           + /−            p-value           +/−             p-value
  (1)                                           (2)            (3)                (4)             (5)               (6)             (7)               (8)

                                                               Panel A: Spanning regressions

  Spanning regressions                          103      77 [23] / 26 [3]       0.000       45 [8] / 58 [2]       0.237       31 [7] / 72 [7]        0.000
  Spanning regressions with FF3 controls        103      70 [21] / 33 [3]       0.000       32 [2] / 71 [13]      0.000       32 [3] / 71 [10]       0.000

                                                               Panel B: Anomaly regressions

  CAPM regressions                              102      93 [73] / 9 [3]        0.000       75 [19] / 27 [1]      0.000       68 [18] / 34 [1]       0.001
  FF3 regressions                               100      81 [60] / 19 [5]       0.000       66 [18] / 34 [1]      0.002       55 [19] / 45 [1]       0.368




4.3.3. Explanations for poor out-of-sample performance                             A large proportion of these in-sample alpha estimates
    The tests in Section 4.3.2 suggest that, in the volatility-                    are statistically signiﬁcant. A positive alpha relative to
managed portfolios setting, strong in-sample performance                           a given factor model implies that the ex post optimal
metrics often fail to translate into real-time gains for in-                       combination of anomaly portfolio and benchmark factors
vestors. Based on this evidence, it is natural to explore the                      expands the mean-variance frontier relative to the ex post
economic drivers of these results and examine whether                              optimal combination of the benchmark factors. As with the
or not our ﬁndings generalize to more familiar investment                          volatility-managed portfolios setting, however, real-time
settings. As a starting point for this analysis, we compare                        investors must construct their portfolios using prior data.
the performance of the combination strategies based on                             For each anomaly portfolio and benchmark model, we
volatility-managed portfolios with the performance of                              conduct an out-of-sample exercise that compares the per-
traditional anomaly strategies.                                                    formance of two strategies: (i) the real-time strategy that
    Panel A of Table 8 reproduces the main results from                            combines the anomaly portfolio, the benchmark factors,
Tables 4 and 6 on the in-sample and out-of-sample perfor-                          and the risk-free asset and (ii) the real-time strategy that
mance of combination strategies. As described above, these                         combines the benchmark factors and the risk-free asset.
tests focus on the value of including a volatility-managed                         The out-of-sample design parameters are identical to those
version of a given portfolio in the investment opportunity                         introduced in Section 4.3.1.
set. In the broad sample of 103 trading strategies, positive                           Although we do see out-of-sample performance degra-
spanning regression alphas are common, but real-time                               dation in Panel B of Table 8, the effects are much less acute
investors typically earn lower Sharpe ratios and CERs                              relative to those seen for the volatility-managed portfolios
under the expanded investment opportunity set.                                     in Panel A. Adding an anomaly portfolio to the CAPM mar-
    Panel B of Table 8 shows results from analogous                                ket factor in real time, for example, leads to a Sharpe ratio
tests for traditional anomaly strategies. Studies showing                          improvement in 75 out of 102 cases and a CER improve-
cross-sectional anomalies routinely emphasize the alphas                           ment in 68 out of 102 cases. Real-time performance rela-
earned by these strategies relative to popular asset pricing                       tive to the Fama and French (1993) three-factor benchmark
models such as the Capital Asset Pricing Model (CAPM)                              is less impressive, with positive Sharpe ratio differences for
or Fama and French (1993) three-factor model. We repli-                            66 out of 100 strategies and positive CER differences for 55
cate these types of tests in our broad sample and ﬁnd                              out of 100 strategies. Nonetheless, these results indicate
that 93 out of 102 portfolios earn positive CAPM alphas,                           that real-time anomaly strategies fare substantially better
and 81 out of 100 earn positive three-factor alphas.22                             compared with real-time volatility-managed strategies.
                                                                                       The results in Table 8 provide a useful backdrop
                                                                                   to examine why the statistical support for out-of-
 22
    The total number of strategies considered in Panel B is less than 103          sample combination strategies is particularly weak in
because we exclude the benchmark factors from the analysis for each                the volatility-managed portfolios setting. We consider
model.
112                           S. Cederburg, M.S. O’Doherty and F. Wang et al. / Journal of Financial Economics 138 (2020) 95–117


Table 9
Summary of multiple structural break tests for spanning regressions and anomaly regressions: broad sample.
Panel A summarizes results from structural break tests in spanning regressions of volatility-managed anomaly portfolio returns on original anomaly port-
folio returns. We consider univariate spanning regressions and spanning regressions with additional controls for the Fama and French (1993) three factors.
The tests follow Bai and Perron (1998, 2003) and allow for an unknown number of structural breaks. Column (2) reports the total number of volatility-
managed strategies considered. For each set of regressions, columns (3)–(7) present the frequency distribution for the number of identiﬁed breaks (Nb ), and
column (8) reports the mean number of breaks (N̄b ). Panel B summarizes results from structural break tests in regressions of traditional anomaly portfolio
returns on factor returns. We consider CAPM and Fama and French (1993) three-factor regressions.

                                                                                  Frequency distribution for breaks

 Description                                       Total        Nb = 0          Nb = 1         Nb = 2          Nb = 3         Nb ≥ 4           N̄b
 (1)                                                (2)          (3)             (4)            (5)             (6)             (7)            (8)

                                                                                   Panel A: Spanning regressions

  Spanning regressions                             103             0              10             52             34                 7          2.37
  Spanning regressions with FF3 controls           103             1               8             53             35                 6          2.37

                                                                                   Panel B: Anomaly regressions

  CAPM regressions                                 102            15              38             39              9                 1          1.44
  FF3 regressions                                  100            10              25             36             21                 8          1.92



three potential explanations: (i) estimation risk in the                           the evaluation period is shorter (e.g., Inoue and Kilian,
out-of-sample portfolio choice exercise, (ii) low power in                         2004). Our focus on assessing the value of volatility
the out-of-sample tests, and (iii) structural instability in                       management for real-time investors necessitates the use
the conditional risk-return trade-off for the various factors                      of out-of-sample tests. Low power also does not seem to
and anomaly portfolios.                                                            be a satisfactory explanation for our results. If volatility
    A known concern with out-of-sample portfolio opti-                             management is systematically beneﬁcial to investors, then
mization is estimation risk. DeMiguel et al. (2009b), for                          we should see a majority of performance differences that
example, note that optimal portfolios constructed from                             are positive in Tables 6 and 7. Low power might be an
sample moments often exhibit extreme weights that                                  explanation for why an individual result is statistically
ﬂuctuate dramatically over time. Intuitively, it can be                            insigniﬁcant, but it does not account for why most of the
diﬃcult to reliably estimate asset return moments with                             performance differences have the wrong sign.
short training periods, and these moments are the key                                 A more plausible economic explanation for the poor
determinants of portfolio weights [e.g., Eq. (15)]. Although                       out-of-sample performance for the combination strate-
estimation error is always a challenge with real-time                              gies is structural instability in the spanning regression
portfolio choice applications, we are skeptical that it                            parameters from Eq. (5) and the implied optimal weights.
fully accounts for our results for a variety of reasons.                           We investigate this issue formally using Bai and Perron
First, our empirical design incorporates several features                          (1998, 2003) structural break tests. Table 9 summarizes
intended to mitigate estimation risk, including a leverage                         results from these tests for the spanning regressions and
constraint on portfolio positions, a risk-free asset in the                        the traditional anomaly regressions.23 In Panel A, we
investment opportunity set (Kirby and Ostdiek, 2012),                              ﬁnd strong statistical evidence of structural breaks in the
and expanding-window parameter estimation. Second,                                 spanning tests for the 103 volatility-managed portfolios.
DeMiguel et al. (2009b) emphasize that estimation risk is                          For the univariate spanning regressions, none of the tests
less problematic in applications, like ours, in which the                          suggests zero breaks, and 41 out of 103 tests identify
number of test assets is small. Third, our main results                            three or more breaks. The average number of breaks is
are based on comparisons of real-time strategies that                              2.37 for both the univariate spanning regressions and
include volatility-managed portfolios in the investment                            the spanning regressions that control for the Fama and
opportunity set with those that exclude volatility-managed                         French (1993) factors. In contrast, structural breaks are less
portfolios from the investment opportunity set. Thus, both                         common in the standard time-series anomaly regressions
the combination strategy and the benchmark suffer from                             in Panel B. In the CAPM regressions, for example, 53 out
estimation risk, and it is not obvious why one of the two                          of 102 strategies have one break or less, and the average
would be more adversely impacted. Fourth, if estimation                            number of breaks is 1.44. From an economic perspective,
risk is the primary explanation of the poor performance                            structural breaks are direct evidence of instability in
of the combination strategies, then we should see more                             the underlying regression parameters and the associated
favorable results under speciﬁcations with longer training                         optimal portfolio weights [e.g., Eq. (10)]. In the volatility-
samples. Table 7 reveals, however, that lengthening the                            managed portfolios setting, the prevalence of breaks often
initial training sample has little impact on our conclusions.                      works to the detriment of real-time investors who rely on
Finally, Panel B of Table 8 provides direct evidence that                          past data in portfolio construction.
in-sample alphas do translate into improved real-time
performance measures much more frequently outside of
the volatility-managed portfolios setting.                                          23
                                                                                       The Internet Appendix provides additional information on the design
    Another common concern with out-of-sample tests is                             of these tests and presents detailed results from structural break tests for
that they lack power relative to in-sample tests because                           the nine equity factors.
                              S. Cederburg, M.S. O’Doherty and F. Wang et al. / Journal of Financial Economics 138 (2020) 95–117                           113


5. Conclusion                                                                      The Sharpe ratios and CERs for the out-of-sample com-
                                                                                   bination portfolios are dramatically less impressive than
    Recent literature suggests that investors can enhance                          those earned by their in-sample versions. Moreover, the
Sharpe ratios and lifetime utility by adopting simple trad-                        real-time combination strategies routinely underperform
ing rules that scale positions in popular equity portfolios                        simpler strategies constrained to invest in the original,
by lagged variance. The trading strategies implied by these                        unscaled portfolios.
studies typically take one of two forms: direct investments
in volatility-managed portfolios or combination portfolios                         Appendix A
that invest in both the volatility-managed version and the
original version of an underlying strategy. We show that                               This appendix provides details on the construction of
neither of these methods suggests a pervasive link be-                             the anomaly portfolios used in our empirical tests.
tween volatility management and improved performance                                   As described in Section 2.1, we examine 94 anomaly
for real-time investors.                                                           variables from Hou et al. (2015) and McLean and Pontiff
    Direct investments in volatility-scaled strategies are                         (2016). Our list of ﬁrm characteristics includes vari-
straightforward to implement in real time, and studies fol-                        ables from these studies that are continuous and can
lowing this approach offer compelling empirical evidence                           be constructed from CRSP, Compustat, and IBES data.
that these dynamic portfolios are superior to their static                         We exclude predictors that are based on industry-level
versions. The evidence is isolated to a handful of strategies                      variables. Table A1 presents a brief description of the ﬁrm
(e.g., the market, momentum, and betting-against-beta                              characteristics and notes the original study documenting
factors), however, making it diﬃcult to draw broad con-                            each corresponding anomaly. We construct the anomaly
clusions. We ﬁll this gap by conducting a comprehensive                            variables following the descriptions provided by Hou et al.
empirical investigation of volatility-managed portfolios.                          (2015) and McLean and Pontiff (2016), and column (4) of
Across a broad sample of 103 equity portfolios, volatility                         Table A1 gives the relevant sources (i.e., “HXZ” or “MP”).
management degrades and improves performance at about                                  The sample includes NYSE, Amex, and Nasdaq ordinary
the same frequency. From a practical perspective, the re-                          common stocks with return data available on the CRSP
sults suggest that direct investments in volatility-managed                        monthly and daily stock ﬁles for the period from July
portfolios are not a panacea of improved performance.                              1926 to December 2016. When a ﬁrm is delisted from an
From an economic perspective, the roughly equal split                              exchange during a given month, we replace any missing
between positive and negative performance differences is                           returns with the delisting returns provided by CRSP. For
suggestive of a generally positive risk-return trade-off for                       a given anomaly variable, we sort ﬁrms periodically into
the individual factors and anomaly portfolios.                                     ten groups and construct value-weighted portfolios. Our
    Combination strategies that incorporate volatility                             tests focus on the corresponding hedge portfolio that
management, in contrast, exhibit systematically strong in-                         takes a long (short) position in the decile of stocks that
sample performance. On this point, we extend Moreira and                           is expected to outperform (underperform) based on prior
Muir’s (2017) spanning regression analysis to our broader                          literature.
set of 103 equity strategies and show that these portfolios                            The portfolios exclude ﬁnancial stocks (SIC codes
tend to exhibit positive alphas. We also demonstrate, how-                         60 0 0–6999) and ﬁrms with market capitalization below
ever, that structural instability in the spanning regression                       the ﬁrst NYSE decile or share price less than $5 at the
parameters limits the appeal of this approach to investors                         portfolio formation date. To ensure that accounting data
conditioning their portfolios on real-time information.                            are known prior to the returns they are used to forecast,


Table A1
Anomaly variables.
The table summarizes the ﬁrm characteristics used to construct the long-short anomaly decile portfolios in the paper. The panels of the table are organized
by anomaly type (i.e., accruals, intangibles, investment, momentum, proﬁtability, trading, and value). For each characteristic, we provide a symbol and brief
description and note the original study documenting the corresponding anomaly. We construct the anomaly variables following the descriptions provided
by Hou et al. (2015) and McLean and Pontiff (2016) and the relevant source (i.e., “HXZ” or “MP”) for a given anomaly is listed in the table. For each anomaly
variable, the table also reports the start of the sample period for portfolio returns and the number of monthly return observations.

  Anomaly     Description                                                      Original study                               Source    Start        Number
  (1)         (2)                                                              (3)                                          (4)       (5)          (6)

                                                                     Panel A: Accruals

  IvC         Inventory changes                                                Thomas and Zhang (2002)                      HXZ       1963:08        641
  IvG         Inventory growth                                                 Belo and Lin (2012)                          HXZ       1963:08        641
  NOA         Net operating assets                                             Hirshleifer et al. (2004)                    HXZ       1963:08        641
  OA          Operating accruals                                               Sloan (1996)                                 HXZ       1963:08        641
  POA         Percent operating accruals                                       Hafzalla et al. (2011)                       HXZ       1963:08        641
  PTA         Percent total accruals                                           Hafzalla et al. (2011)                       HXZ       1963:08        641
  TA          Total accruals                                                   Richardson et al. (2005)                     HXZ       1963:08        641
  NCO        Changes in net noncurrent operating assets                       Soliman (2008)                               MP        1963:08        641
  NWC        Changes in net noncash working capital                           Soliman (2008)                               MP        1963:08        641
  NoaG        Growth in net operating assets minus accruals                    Fairﬁeld et al. (2003)                       MP        1963:08        641
                                                                                                                                     (continued on next page)
114                          S. Cederburg, M.S. O’Doherty and F. Wang et al. / Journal of Financial Economics 138 (2020) 95–117




Table A1 (continued)

 Anomaly      Description                                                     Original study                               Source    Start        Number
 (1)          (2)                                                             (3)                                          (4)       (5)          (6)

                                                                   Panel B: Intangibles

 AccQ         Accrual quality                                                 Francis et al. (2005)                        HXZ       1966:08        605
 AD/M         Advertisement expense-to-market                                 Chan et al. (2001)                           HXZ       1974:08        509
 BC           Brand capital investment rate                                   Belo et al. (2014b)                          HXZ       1980:08        437
 H/N          Hiring rate                                                     Belo et al. (2014a)                          HXZ       1963:08        641
 OC/A         Organizational capital-to-assets                                Eisfeldt and Papanikolaou (2013)             HXZ       1963:08        641
 OL           Operating leverage                                              Novy-Marx (2011)                             HXZ       1963:08        641
 RC/A         R&D capital-to-assets                                           Li (2011)                                    HXZ       1980:08        437
 RD/M         R&D-to-market                                                   Chan et al. (2001)                           HXZ       1976:08        485
 RD/S         R&D-to-sales                                                    Chan et al. (2001)                           HXZ       1976:08        485
 Age          Firm age                                                        Barry and Brown (1984)                       MP        1963:08        641

                                                                   Panel C: Investment

 PI/A        Changes in PP&E plus changes in inventory                       Lyandres et al. (2008)                       HXZ       1963:08        641
 ACI          Abnormal corporate investment                                   Titman et al. (2004)                         HXZ       1966:08        605
 CEI          Composite issuance                                              Daniel and Titman (2006)                     HXZ       1931:08       1025
 I/A          Investment-to-assets                                            Cooper et al. (2008)                         HXZ       1963:08        641
 IG           Investment growth                                               Xing (2008)                                  HXZ       1963:08        641
 NSI          Net stock issues                                                Pontiff and Woodgate (2008)                  HXZ       1963:08        641
 NXF          Net external ﬁnancing                                           Bradshaw et al. (2006)                       HXZ       1974:08        509
 BeG          Growth in book equity                                           Lockwood and Prombutr (2010)                 MP        1963:08        641
 I-ADJ        Industry-adjusted growth in investment                          Abarbanell and Bushee (1998)                 MP        1965:08        617

                                                                   Panel D: Momentum

 Abr-1        Abnormal stock returns around earnings announcements            Chan et al. (1996)                           HXZ       1974:08        509
 R11-1        Price momentum (11-month prior returns)                         Fama and French (1996)                       HXZ       1927:08       1073
 R6-1         Price momentum (6-month prior returns)                          Jegadeesh and Titman (1993)                  HXZ       1926:09       1084
 RE-1         Revisions in analysts’ earnings forecasts                       Chan et al. (1996)                           HXZ       1976:08        485
 SUE-1        Earnings surprise                                               Foster et al. (1984)                         HXZ       1976:08        485
 R6-Lag       Lagged momentum                                                 Novy-Marx (2012)                             MP        1927:08       1073
 Season       Seasonality                                                     Heston and Sadka (2008)                      MP        1946:08        845
 W52          52-week high                                                    George and Hwang (2004)                      MP        1927:08       1073

                                                                   Panel E: Proﬁtability

 ATO          Asset turnover                                                  Soliman (2008)                               HXZ       1963:08        641
 CTO          Capital turnover                                                Haugen and Baker (1996)                      HXZ       1963:08        641
 F            F-score                                                         Piotroski (2000)                             HXZ       1974:08        509
 FP           Failure probability                                             Campbell et al. (2008)                       HXZ       1976:08        485
 GP/A         Gross proﬁtability-to-assets                                    Novy-Marx (2013)                             HXZ       1963:08        641
 O            O-score                                                         Dichev (1998)                                HXZ       1963:08        641
 PM           Proﬁt margin                                                    Soliman (2008)                               HXZ       1963:08        641
 RNA          Return on net operating assets                                  Soliman (2008)                               HXZ       1963:08        641
 ROA          Return on assets                                                Balakrishnan et al. (2010)                   HXZ       1974:08        509
 ROE-HB       Return on equity                                                Haugen and Baker (1996)                      HXZ       1974:08        509
 RS           Revenue surprise                                                Jegadeesh and Livnat (2006)                  HXZ       1976:08        485
 TES          Tax expense surprise                                            Thomas and Zhang (2011)                      HXZ       1976:08        485
 TI/BI        Taxable income-to-book income                                   Green et al. (2017)                          HXZ       1963:08        641
 ATO         Change in asset turnover                                        Soliman (2008)                               MP        1963:08        641
 PM          Change in proﬁt margin                                          Soliman (2008)                               MP        1963:08        641
 E-con        Earnings consistency                                            Alwathainani (2009)                          MP        1971:08        545
 S/IV         Change in sales minus change in inventory                       Abarbanell and Bushee (1998)                 MP        1963:08        641
 S/P          Sales-to-price                                                  Barbee, Jr. et al. (1996)                    MP        1963:08        641
 S/SG&A       Change in sales minus change in SG&A                            Abarbanell and Bushee (1998)                 MP        1963:08        641
 Z            Z-score                                                         Dichev (1998)                                MP        1963:08        641

                                                                     Panel F: Trading

 β -D         Dimson’s beta (daily data)                                      Dimson (1979)                                HXZ       1926:09      1084
 β -FP        Frazzini and Pedersen’s beta                                    Frazzini and Pedersen (2014)                 HXZ       1931:08      1025
 1/P          1/share price                                                   Miller and Scholes (1982)                    HXZ       1926:08      1085
 Disp         Dispersion of analysts’ earnings forecasts                      Diether et al. (2002)                        HXZ       1976:08       485
 Dvol         Dollar trading volume                                           Brennan et al. (1998)                        HXZ       1926:08      1085
 Illiq        Illiquidity as absolute return-to-volume                        Amihud (2002)                                HXZ       1926:08      1085
 Ivol         Idiosyncratic volatility                                        Ang et al. (2006)                            HXZ       1926:09      1084
 MDR          Maximum daily return                                            Bali et al. (2011)                           HXZ       1926:09      1084
                                                                                                                                    (continued on next page)
                             S. Cederburg, M.S. O’Doherty and F. Wang et al. / Journal of Financial Economics 138 (2020) 95–117                                115


Table A1 (continued)

 Anomaly      Description                                                     Original study                                  Source     Start         Number
 (1)          (2)                                                             (3)                                             (4)        (5)           (6)

 ME           Market equity                                                   Banz (1981)                                     HXZ        1926:08        1085
 S-Rev        Short-term reversal                                             Jegadeesh (1990)                                HXZ        1926:08        1085
 Svol         Systematic volatility                                           Ang et al. (2006)                               HXZ        1986:08         365
 Turn         Share turnover                                                  Datar et al. (1998)                             HXZ        1926:08        1085
 Tvol         Total volatility                                                Ang et al. (2006)                               HXZ        1926:09        1084
 β -M         Fama and MacBeth’s beta (monthly data)                          Fama and MacBeth (1973)                         MP         1931:08        1025
 σ (Dvol)     Dollar volume volatility                                        Chordia et al. (2001)                           MP         1929:08        1049
 B-A          Bid-ask spread                                                  Amihud and Mendelson (1986)                     MP         1963:08         641
 Short        Short interest                                                  Dechow et al. (2001)                            MP         1973:08         521
 Skew         Coskewness                                                      Harvey and Siddique (2000)                      MP         1931:08        1025
 Vol-T        Volume trend                                                    Haugen and Baker (1996)                         MP         1931:08        1025

                                                                      Panel G: Value

 A/ME         Market leverage                                                 Bhandari (1988)                                 HXZ        1963:08         641
 B/M          Book-to-market equity                                           Rosenberg et al. (1985)                         HXZ        1963:08         641
 CF/P         Cash ﬂow-to-price                                               Lakonishok et al. (1994)                        HXZ        1963:08         641
 D/P          Dividend yield                                                  Litzenberger and Ramaswamy (1979)               HXZ        1927:08        1073
 Dur          Equity duration                                                 Dechow et al. (2004)                            HXZ        1963:08         641
 E/P          Earnings-to-price                                               Basu (1983)                                     HXZ        1963:08         641
 EF/P         Analysts’ earnings forecasts-to-price                           Elgers et al. (2001)                            HXZ        1976:08         485
 LTG          Long-term growth forecasts of analysts                          La Porta (1996)                                 HXZ        1982:08         413
 NO/P         Net payout yield                                                Boudoukh et al. (2007)                          HXZ        1974:08         509
 O/P          Payout yield                                                    Boudoukh et al. (2007)                          HXZ        1974:08         509
 Rev          Long-term reversal                                              De Bondt and Thaler (1985)                      HXZ        1931:08        1025
 SG           Sales growth                                                    Lakonishok et al. (1994)                        HXZ        1967:08         593
 An-V         Analyst value                                                   Frankel and Lee (1998)                          MP         1976:08         485
 σ (CF)       Cash ﬂow variance                                               Haugen and Baker (1996)                         MP         1978:08         461
 B/P-E        Enterprise component of book-to-price                           Penman et al. (2007)                            MP         1984:08         389
 B/P-Lev      Leverage component of book-to-price                             Penman et al. (2007)                            MP         1984:08         389
 Enter        Enterprise multiple                                             Loughran and Wellman (2012)                     MP         1963:08         641
 Pension      Pension funding status                                          Franzoni and Marin (2006)                       MP         1981:08         425




we lag annual Compustat data by six months and assume                             Ang, A., Hodrick, R.J., Xing, Y., Zhang, X., 2006. The cross-section of volatil-
quarterly Compustat data are known after the report date                               ity and expected returns. J. Financ. 61, 259–299.
                                                                                  Bai, J., Perron, P., 1998. Estimating and testing linear models with multiple
of quarterly earnings. For the strategies based on annual                              structural changes. Econometrica 66, 47–78.
Compustat data, the decile portfolios are rebalanced annu-                        Bai, J., Perron, P., 2003. Computation and analysis of multiple structural
ally at the beginning of July. The other trading strategies                            change models. J. Appl. Econom. 18, 1–22.
                                                                                  Balakrishnan, K., Bartov, E., Faurel, L., 2010. Post loss/proﬁt announcement
are rebalanced monthly.                                                                drift. J. Account. Econ. 50, 20–41.
    There are some exceptions to the variable selection and                       Bali, T.G., Cakici, N., Whitelaw, R.F., 2011. Maxing out: stocks as lotter-
portfolio formation rules described above. The composite                               ies and the cross-section of expected returns. J. Financ. Econ. 99,
                                                                                       427–446.
issuance variable, CEI, in Panel C of Table A1 is constructed
                                                                                  Baltas, N., Kosowski, R.L., 2017. Demystifying Time-Series Momentum
from CRSP data, but we rebalance the corresponding                                     Strategies: Volatility Estimators, Trading Rules, and Pairwise Correla-
anomaly portfolios annually. The short interest variable,                              tions. Unpublished working paper. Imperial College Business School.
                                                                                  Banz, R.W., 1981. The relationship between return and market value of
Short, in Panel F is constructed from the Compustat
                                                                                       common stocks. J. Financ. Econ. 9, 3–18.
Supplemental Short Interest File. The pension funding                             Barbee Jr., W.C., Mukherji, S., Raines, G.A., 1996. Do sales-price and
status variable, Pension, in Panel G is constructed from the                           debt-equity explain stock returns better than book-market and ﬁrm
Compustat Pension Annual File.                                                         size? Financ. Anal. J. 52, 56–60.
                                                                                  Barroso, P., Maio, P., 2018. Managing the Risk of The “Betting-Against-
    The sample period for a given anomaly portfolio is                                 Beta” Anomaly: Does it Pay to Bet Against Beta? Unpublished working
determined by data availability for the corresponding                                  paper. University of New South Wales.
sorting variable.                                                                 Barroso, P., Santa-Clara, P., 2015. Momentum has its moments. J. Financ.
                                                                                       Econ. 116, 111–120.
                                                                                  Barry, C.B., Brown, S.J., 1984. Differential information and the small ﬁrm
                                                                                       effect. J. Financ. Econ. 13, 283–294.
References                                                                        Basu, S., 1983. The relationship between earnings’ yield, market value and
                                                                                       return for NYSE common stocks: further evidence. J. Financ. Econ. 12,
Abarbanell, J.S., Bushee, B.J., 1998. Abnormal returns to a fundamental                129–156.
   analysis strategy. Account. Rev. 73, 19–45.                                    Belo, F., Lin, X., 2012. The inventory growth spread. Rev. Financ. Stud. 25,
Alwathainani, A.M., 2009. Consistency of ﬁrms’ past ﬁnancial performance               278–313.
   measures and future returns. Br. Account. Rev. 41, 184–196.                    Belo, F., Lin, X., Bazdresch, S., 2014. Labor hiring, investment, and
Amihud, Y., 2002. Illiquidity and stock returns: cross-section and                     stock return predictability in the cross section. J. Polit. Econ. 122,
   time-series effects. J. Financ. Mark. 5, 31–56.                                     129–177.
Amihud, Y., Mendelson, H., 1986. Asset pricing and the bid-ask spread. J.         Belo, F., Lin, X., Vitorino, M.A., 2014. Brand capital and ﬁrm value. Rev.
   Financ. Econ. 17, 223–249.                                                          Econ. Dyn. 17, 150–169.
Ang, A., 2014. Asset Management: A Systematic Approach to Factor Invest-          Bhandari, L.C., 1988. Debt/equity ratio and expected common stock re-
   ing. Oxford University Press, Oxford, United Kingdom.                               turns: empirical evidence. J. Financ. 43, 507–528.
116                             S. Cederburg, M.S. O’Doherty and F. Wang et al. / Journal of Financial Economics 138 (2020) 95–117


Black, F., Litterman, R., 1992. Global portfolio optimization. Financ. Anal. J.      Fleming, J., Kirby, C., Ostdiek, B., 2003. The economic value of volatility
    48, 28–43.                                                                            timing using “realized” volatility. J. Financ. Econ. 67, 473–509.
Boguth, O., Carlson, M., Fisher, A., Simutin, M., 2011. Conditional risk and         Foster, G., Olsen, C., Shevlin, T., 1984. Earnings releases, anomalies, and
    performance evaluation: volatility timing, overconditioning, and new                  the behavior of security returns. Account. Rev. 59, 574–603.
    estimates of momentum alphas. J. Financ. Econ. 102, 363–389.                     Francis, J., LaFond, R., Olsson, P., Schipper, K., 2005. The market pricing of
Boudoukh, J., Michaely, R., Richardson, M., Roberts, M.R., 2007. On the im-               accruals quality. J. Account. Econ. 39, 295–327.
    portance of measuring payout yield: implications for empirical asset             Frankel, R., Lee, C.M., 1998. Accounting valuation, market expectation, and
    pricing. J. Financ. 62, 877–915.                                                      cross-sectional stock returns. J. Account. Econ. 25, 283–319.
Bradshaw, M.T., Richardson, S.A., Sloan, R.G., 2006. The relation between            Franzoni, F., Marin, J.M., 2006. Pension plan funding and stock market ef-
    corporate ﬁnancing activities, analysts forecasts and stock returns. J.               ﬁciency. Journal of Finance 61, 921–956.
    Account. Econ. 42, 53–85.                                                        Frazzini, A., Pedersen, L.H., 2014. Betting against beta. J. Financ. Econ. 111,
Brandt, M.W., Kang, Q., 2004. On the relationship between the conditional                 1–25.
    mean and volatility of stock returns: a latent VAR approach. J. Financ.          French, K.R., Schwert, G.W., Stambaugh, R.F., 1987. Expected stock returns
    Econ. 72, 217–257.                                                                    and volatility. J. Financ. Econ. 19, 3–29.
Brennan, M.J., Chordia, T., Subrahmanyam, A., 1998. Alternative factor               George, T.J., Hwang, C.-Y., 2004. The 52-week high and momentum invest-
    speciﬁcations, security characteristics, and the cross-section of ex-                 ing. J. Financ. 59, 2145–2176.
    pected stock returns. J. Financ. Econ. 49, 345–373.                              Gibbons, M.R., Ross, S.A., Shanken, J., 1989. A test of the eﬃciency of a
Campbell, J.Y., 1987. Stock returns and the term structure. J. Financ. Econ.              given portfolio. Econometrica 87, 1121–1152.
    18, 373–399.                                                                     Green, J., Hand, J.R.M., Zhang, X.F., 2017. The characteristics that provide
Campbell, J.Y., Hilscher, J., Szilagyi, J., 2008. In search of distress risk. J.          independent information about average US monthly stock returns.
    Financ. 63, 2899–2939.                                                                Rev. Financ. Stud. 30, 4389–4436.
Carhart, M.M., 1997. On persistence in mutual fund performance. J. Financ.           Green, R.C., Holliﬁeld, B., 1992. When will mean-variance eﬃcient portfo-
    52, 57–82.                                                                            lios be well diversiﬁed? J. Financ. 47, 1785–1809.
Chan, L.K., Jegadeesh, N., Lakonishok, J., 1996. Momentum strategies. J. Fi-         Grobys, K., Ruotsalainen, J., Äijö, J., 2018. Risk-managed industry momen-
    nanc. 51, 1681–1713.                                                                  tum and momentum crashes. Quant. Financ. 18, 1715–1733.
Chan, L.K., Lakonishok, J., Sougiannis, T., 2001. The stock market valuation         Hafzalla, N., Lundholm, R., Van Winkle, M.E., 2011. Percent accruals. Ac-
    of research and development expenditures. J. Financ. 56, 2431–2456.                   count. Rev. 86, 209–236.
Chordia, T., Subrahmanyam, A., Anshuman, R.V., 2001. Trading activity and            Harvey, C.R., 2001. The speciﬁcation of conditional expectations. J. Empir.
    expected stock returns. J. Financ. Econ. 59, 3–32.                                    Financ. 8, 573–637.
Cooper, M.J., Gulen, H., Schill, M.J., 2008. Asset growth and the cross-sec-         Harvey, C.R., Siddique, A., 20 0 0. Conditional skewness in asset pricing
    tion of stock returns. J. Financ. 63, 1609–1651.                          