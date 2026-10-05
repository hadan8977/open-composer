source: https://periodicos.fgv.br/rbfin/article/download/89848/84802/201368
fetched_utc: 2026-10-04T18:48:28Z
bytes_raw: 242797

Using hierarchical risk parity in the
 Brazilian market: An out-of-sample
 analysis

 Felipe Reis†
 Anderson Sobreira‡
 Carlos Trucíos*
 Boris Asrilhant**


      Abstract Portfolio allocation is an important tool for portfolio managers and investors
      interested in diversification as well as improvements in out-of-sample portfolio perfor-
      mance. Recently, new portfolio allocation strategies based on unsupervised machine
      learning have been proposed in the literature, with hierarchical risk parity being one
      of the most popular. This article uses assets from the Brazilian financial market to per-
      form an extensive out-of-sample comparison of hierarchical risk parity against widely-
      known, traditional portfolio allocation techniques. The results suggest that, in general,
      hierarchical risk parity does not report the best performance but, in some performance
      measures, performs equally well to other approaches. Overall, hierarchical risk parity
      outperforms the market index.
      Keywords: Asset allocation; Diversification; Machine Learning; Markowitz; Portfolio
      selection.
      JEL Code: C52, C58, G11.


 1.     Introduction

     Portfolio allocation plays an important role in finance for both portfolio
 managers and individual investors, offering a means to diversify investments
 and potentially improve the out-of-sample portfolio performance. Over the
 years, various approaches have been developed and proposed in the literature
 to address the challenge of allocating portfolios. These approaches range from
 simple methodologies, such as equally-weighted portfolios, to more complex
 ones, such as those proposed by Markowitz (1952), Qian (2005), Choueifaty
 and Coignard (2008), Maillard et al. (2010), Lopez de Prado (2016), among
 others.
   Submitted on August 5, 2023. Accepted on August 30, 2023. Published online in December
   2023. Editor in charge: Bruno Giovannetti.
 † Universidade Federal do Rio de Janeiro, Brazil: felipereis150@gmail.com
 ‡ Universidade Federal do Rio de Janeiro, Brazil: andersong.sobreira@gmail.com
 * Universidade Estadual de Campinas, Brazil: ctrucios@unicamp.br
** Universidade Federal do Rio de Janeiro, Brazil: boris@facc.ufrj.br




   Brazilian Review of Finance (Online), Rio de Janeiro, Vol. 21, No. 4, December 2023, pp. 81–103   ISSN 1679-0731, ISSN online 1984-5146
                             ©2023 Sociedade Brasileira de Finanças, under a Creative Commons Attribution 3.0 license
                                     Reis et al., 2023




    The easiest, fastest portfolio allocation strategy is the equally-weighted
technique, which does not require solving an optimization problem and al-
locates the same amount of wealth in each asset. This approach follows the
principle of not putting all eggs in one basket, and can be appropriate when
neither the risks nor the expected returns can be forecasted or when the esti-
mation error is large (De Carvalho et al., 2012; Pflug et al., 2012; Battaglia
and Leal, 2017).
    Another approach, the traditional, most widely-known portfolio alloca-
tion technique, was put forth by Markowitz (1952), which is nowadays called
as modern portfolio theory, mean-variance portfolio or even Markowitz port-
folio optimization. Markowitz portfolio optimization aims to build portfolios
that maximize the expected return for a given level of risk or, in case of its
dual problem, minimize risk for a given level of expected return (Meucci,
2007). This approach is broadly used for both academic and practitioners,
although, despite its widespread use, Markowitz portfolio optimization has
faced criticisms and limitations; see, for instance, Michaud (1989), Becker
et al. (2015), Huang and Yu (2020), and Oliveira et al. (2023) to quote only a
few.
    The main criticism of Markowitz portfolio optimization relies on the fact
that this approach needs to meet requirements that never hold in practice: the
true mean vector and the covariance matrix of asset returns should be known.
In empirical applications it is necessary to estimate them from data, implying
in some degree of estimation error which, as pointed out by Michaud (1989),
Chopra et al. (1993) and Chopra and Ziemba (1993), may affect the portfolio
weights obtained by the Markowitz portfolio optimization. This estimation
error yields to extreme and/or unrealistic portfolio weights, lack of diversi-
fication and poor out-of-sample performance (Michaud, 1989; Wolf, 2004;
Becker et al., 2015; Huang and Yu, 2020), which are undesirable features in
portfolio allocation.
    Alternatively, an approach that has drawn attention for both academic and
practitioners is the risk parity portfolio (Qian, 2005) in which, regardless the
portfolio risk measure, the marginal risk contribution to every asset in the
portfolio is set to be equal. One of the main characteristics of this strategy
refers to well-diversified portfolio weights. For instance, comparatively to the
Markowitz portfolio weights, which tend to be concentrated in a few assets,
risk parity portfolio weights tend to be spread out among all of them, yielding
to more diversified portfolios and limiting the impact of large losses from
individual assets (Chaves et al., 2011; Bai et al., 2016).
    Since the proposals of Markowitz (1959) and Qian (2005) popularized


82                   Brazilian Review of Finance (Online) 21(4), 2023
                     Using hierarchical risk parity in the Brazilian market




quantitative portfolio allocation techniques, several other portfolio allocation
strategies have been proposed in the literature, which also attracted the at-
tention of both academics and practitioners (De Carvalho et al., 2012; Ardia,
Bolliger, Boudt and Gagnon-Fleury, 2017; Nakagawa et al., 2018; du Plessis
and van Rensburg, 2020), such as the inverse-volatility weighted portfolio of
De Carvalho et al. (2012), the maximum decorrelation of Christoffersen et al.
(2012) and the maximum diversification of Choueifaty and Coignard (2008).
    Recently, Lopez de Prado (2016) proposed the hierarchical risk parity
(HRP) portfolio, a portfolio allocation strategy that avoids inverting the co-
variance matrix (minimizing the effect of estimation error) and relies on an
unsupervised machine learning problem (clusterization) rather than optimiza-
tion, to obtain the portfolio weights. This approach explores an earlier idea of
Simon (1962), who argued that complex systems, such as financial markets,
are usually organized in a hierarchical manner.
    HRP portfolios bring a new, innovative way to deal with portfolio allo-
cation. This procedure has been applied in different markets with encourag-
ing results (Burggraf, 2021; Nourahmadi and Sadeqi, 2022; Sen et al., 2021;
Sen and Dutta, 2022) but its effectiveness in the Brazilian market has not
been well established yet. In order to investigate its effectiveness, this study
performs an out-of-sample comparison of HRP portfolio against other well-
known portfolio allocation techniques using data from the Brazilian stock
market. Therefore, this study aims to assess whether HRP offers superior out-
of-sample portfolio performance compared to other approaches.
    This comparison contributes to the literature to a better understanding in
which situations HRP portfolios could be an interesting approach to be imple-
mented, as well as to evaluate its performance using real data. Additionally,
the results obtained provide portfolio managers and individual investors with
a comprehensive out-of-sample analysis to make a decision whether HRP is
worth to be applied in the Brazilian market.
    The remaining part of the paper is organized as follows. Section 2 presents
a brief review of empirical applications of portfolio allocation strategies in the
Brazilian market and also places this work in context. Section 3 describes the
portfolio allocation strategies implemented in this paper, with special empha-
sis on HRP. Section 4 describes the data set used and presents the out-of-
sample comparison. Finally, Section 5 points out the final considerations.

2.   Literature Review
    There are several papers in the literature addressing portfolio allocation
strategies in the Brazilian market. However, most of them are based on classi-


                      Brazilian Review of Finance (Online) 21(4), 2023         83
                                     Reis et al., 2023




cal portfolio allocation procedures and do not consider hierarchical risk par-
ity, which is the focus of this paper.
     Among the papers addressing portfolio allocation, Farias et al. (2006)
compares the minimum variance portfolio against the mean absolute devi-
ation (Konno and Yamazaki, 1991) and minimax (Young, 1998) strategies
in a daily data context and concludes that the minimax strategy usually per-
forms better than its competitors. Santos and Tessari (2012) using daily data
and considering mean-variance, minimum variance, equally-weighted portfo-
lios and the market index, compares the out-of-sample performance of those
strategies using different covariance matrix estimators, and concludes that,
in general, strategies based on optimization perform better than the equally-
weighted portfolios and the market index. Rubesam et al. (2013) and Caldeira
et al. (2013), both using daily data, compare several covariance matrix es-
timators into a minimum variance portfolio allocation problem, where the
former concludes that simplest covariance matrix estimators yields to bet-
ter out-of-sample performance and the latter concludes that the estimator of
Santos and Moura (2014) leads to better out-of-sample performance. Naibert
and Caldeira (2015), using daily data, compares the mean-variance and min-
imum variance portfolios with and without portfolio weights restrictions as
proposed by Fan et al. (2012), and the results evidence that restrictions can
be very useful to improve portfolio performance. Borges et al. (2015) and
Caldeira et al. (2017) compare the minimum variance portfolio using several
intraday covariance matrix estimators, concluding that covariance matrices
estimated using intraday data leads to substantial improvements in compari-
son with covariance matrices based on daily data. Bortoluzzo et al. (2018),
using daily data, compares risk parity against the minimum variance and
equally weighted portfolios, the results indicating that the minimum vari-
ance portfolio achieved the best performance in terms of risk. Oliveira et al.
(2023), using monthly data, compares Markowitz optimizations against their
re-sampling portfolio (Michaud and Michaud, 1998) alternatives and con-
cludes that re-sampling portfolio yields to better out-of-sample performance.
Numerous other works such as Iquiapaza et al. (2016), Leal and Campani
(2016), Souza et al. (2017), Maciel (2021), Pereira and Oliveira (2021) also
deal with portfolio selection in the Brazilian scenario but none of them used
HRP portfolios.
     The only works dealing with the use of HRP in the Brazilian market are
Duarte and De Castro (2020) and Freitas and Junior (2023). The former uses
daily data and compares HRP against minimum variance portfolio and the
market index, and the results indicate that although HRP outperforms the
minimum variance portfolio in terms of average portfolio returns, it is outper-


84                   Brazilian Review of Finance (Online) 21(4), 2023
                          Using hierarchical risk parity in the Brazilian market




 formed in terms of risk. The latter, also using daily data, concludes that HRP
 only outperforms the Brazilian market index (Ibovespa) in terms of Sharpe
 ratio.
     Therefore, the present work can be seen as complementary to the afore-
 mentioned ones. First, this comparison is based on monthly rather than on
 daily data. Monthly data implies in smaller transactions costs due to rebal-
 ancing frequency and, since monthly returns has no (or very weak) ARCH
 effects, simple covariance matrix estimators can be used.1 Second, beyond
 the equally-weighted and minimum variance portfolios, this comparison in-
 cludes a broad number of well-known portfolio allocation techniques, most
 of them were not considered in the previous comparisons. Third, this compar-
 ison considers other portfolio performance measures rather than the classical
 Sharpe ratio and annualized volatility. Additionally, when applicable, hypoth-
 esis testing is used to verify statistically significant differences, a procedure
 which is not performed in the previous works.

 3.    Portfolio allocation strategies

      Let Pi,t be the closing price of asset i at time t and let ri,t = 100 × (Pi,t −
 Pi,t−1 )/Pi,t be its corresponding simple return in percentage. Let rt = (r1,t , . . . ,
 rN,t ) and ω = (ω1 , · · · , ωN ) be a N-dimensional vector of returns and its cor-
 responding N-dimensional vector of portfolio weights, respectively. Then, the
 portfolio return at time t is given by

                            Rt = rt ω t′ = ω1 r1,t + · · · + ωN rN,t .

     In this section, six well-known methods to obtain ω = (ω1 , · · · , ωN ) will
 be briefly introduced, namely, the equally-weighted, minimum variance, risk
 parity, maximum diversification, maximum decorrelation and inverse-volatility
 portfolios. Additionally, the recently proposed HRP portfolio of Lopez de
 Prado (2016) is also described.

 3.1    Equally-weighted (EW) portfolio
     Also called naive or 1/N strategy, the equally-weighted portfolio is the
 simplest method to allocate wealth across assets. It is not grounded on com-
 plex calculations and no optimization problem is considered. For a set of N
1 The other two paper mentioned ignore the daily evolution of variances and covariances and use

 simple covariance matrix estimators. For a better comparison, simple covariance matrix estima-
 tors should be used with monthly data or multivariate volatility models should be used with daily
 data. In this paper, we address the former and left the latter as a future comparison.


                           Brazilian Review of Finance (Online) 21(4), 2023                    85
                                     Reis et al., 2023




assets, the portfolio weights are defined by

                        ωi = 1/N,          for i = 1, · · · , N.

    Despite its simplicity, this method is advocated by Duchin and Levy (2009),
DeMiguel et al. (2009), Malladi and Fabozzi (2017), among others, to outper-
form complex alternatives. However, recent studies reveal that this finding is
not always hold (see; for instance, Fugazza et al., 2015; Engle et al., 2019;
De Nard et al., 2021; Trucíos et al., 2023) and is usually outperformed by
other approaches. This method is the primary benchmark in empirical appli-
cations.

3.2   Minimum variance (MV) portfolio
    Markowitz optimization (Markowitz, 1952, 1959) yields to portfolios in
the efficient frontier. This approach, also known as mean-variance portfolio,
requires such input parameters as the mean vector and the covariance matrix.
As the mean vector is difficult to be estimated with some degree of accuracy
(Merton, 1980), a portfolio that only requires the covariance matrix as an
input parameter, called minimum variance portfolio, is then preferable. In
this portfolio allocation strategy, the weights are obtained by minimizing
                                                     N
                           ω ′,
                        ω Σω         subject to ∑ ωi = 1,
                                                    i=1

where Σ is the covariance matrix of asset returns. Often, due to investor pref-
erences and/or financial institution restrictions, no short-selling constraints
(ωi ⩾ 0 for i = 1, · · · , N) are included in the optimization problem.

3.3   Risk parity portfolio (RP)
    Advocated by Qian (2005, 2006, 2011, 2016), risk parity portfolios be-
came very popular and quickly adopted by portfolio managers due to its su-
perior performance in empirical data (Qian, 2013). This approach seeks port-
folios where marginal risk contribution of every asset in the portfolios are
equal. Consequently, assets with lower risk will have larger allocation than
assets with higher risk. Using the portfolio variance as a measure of risk, the
portfolio weights are obtained by minimizing
                                N
                                ∑ (%RCi − 1/N)2 ,
                               i=1


86                   Brazilian Review of Finance (Online) 21(4), 2023
                      Using hierarchical risk parity in the Brazilian market




where %RCi = ωi (Σω  ω ′ )i /ω  ω ′ is the percentage of variance contribution of
                             ω Σω
asset i to the entire portfolio and (Σω   ω ′ )i stands for the ith position of the
vector Σωω.′


3.4   Maximum diversification (MD) portfolio
    The maximum diversification (MD) portfolio allocation strategy intro-
duced by Choueifaty and Coignard (2008) and developed by Choueifaty et al.
(2013), also known as the most diversified portfolio, seeks portfolio weights
that maximize the diversification ratio D, which is calculated by the weighted
average of each volatility divided by the total portfolio volatility. Thus, the
portfolio weights are obtained by maximizing

               ω × (σ1 , · · · , σN )′                        N
         D=        √                   ,    subject to ∑ ω1 = 1 and ωi ⩾ 0.
                     ω Σω  ω′                                i=1

    Note that, in the extreme case of a portfolio of a single asset (mono-asset
portfolio), the diversification ratio is equal to one and, as a consequence, the
portfolio is poorly diversified.

3.5   Maximum decorrelation (MDE) portfolio
    Introduced by Christoffersen et al. (2012) and Goltz and Sivasubramanian
(2018), this portfolio allocation strategy is a particular case of the minimum
variance portfolio in which the covariance matrix Σ is replaced by the corre-
lation matrix ρ. Thus, portfolio weights are obtained by minimizing
                                                         N
                             ω ′,
                          ω ρω          subject to ∑ ωi = 1.
                                                        i=1

Usually similar to other portfolio allocation strategies, no short-selling con-
straints are also imposed in the optimization problem. This strategy explores
low correlations among assets.

3.6   Inverse-volatility weighted portfolio (IV)
    Proposed by De Carvalho et al. (2012), the inverse-volatility weighted
portfolio does not take covariances into account and allocates assets accord-
ingly to its proportion of inverse volatility over the volatility harmonic mean
of all assets considered, that is, the portfolio weights are obtained through
                            N             −1
                    ω=        ∑ 1/σ j            × (1/σ1 , · · · , 1/σN ).
                              j=1


                        Brazilian Review of Finance (Online) 21(4), 2023        87
                                         Reis et al., 2023




3.7    Hierarchical risk parity (HRP) portfolio
    Finally, HRP is a new, innovative portfolio allocation technique proposed
by Lopez de Prado (2016). This approach uses the information provided by
the covariance matrix without inverting it, being then an attractive alternative
in case the covariance matrix is numerically ill-conditioned. The procedure
can be summarized in the following steps:

     1. Let ρ = {ρi j }i, j=1,···N be the N × N correlation matrixpwith elements
        ρi j . Compute the matrix D = {di j }i, j=1,···N , where di j = 0.5 × (1 − ρi j ),
        is a measure of distance between assets i and j.

     2. Calculate
        q         the N × N matrix D̃ = {d˜i j }i, j=1,··· ,N with elements d˜i j =
           ∑Nk=1 (dki − dk j )2 (the Euclidean distance between columns i and j
        of matrix D) and apply the single linkage hierarchical clustering proce-
        dure using D̃ as distance matrix.

     3. Ordering the assets according to the dendrogram obtained by the clus-
        terization in the previous step.

     4. Denote by L = {L1 } = {C1 , · · · ,CN } the cluster with all (ordering) as-
        sets and by |L1 | its number of elements. Assign unity weights to all
        elements in L1 , i.e, ωi = 1 for i = 1, · · · , N.

     5. For each Li ∈ L such that |Li | > 1:
                                                                 (1)        (2)          (1)
          (a) Preserving the ordering, split Li into Li                and Li , such that Li ∪
               (2)            (1)
              Li = Li and |Li | = ⌊0.5|Li |⌋.
                                     (k)       (k)               (k)
          (b) For k = 1, 2, define Vi = ω (k) Σi ω (k)′ , where Σi is the covari-
                                               (k)
              ance matrix of the elements of Li and

                                                       1                          (k)
                            ω (k) =                        (k)
                                                                   × Diag(Σi )−1 .
                                      Trace(Diag(Σi )−1 )

                                             (1)
                                           Vi
          (c) Compute α = 1 −            (1)     (2)   and update the portfolio weights by
                                       Vi +Vi
              ω (1) = αω
                       ω (1) and ω (2) = (1 − α)ω
                                                ω (2) , respectively.
                      (1)     (2)
          (d) L = {Li , Li }


88                       Brazilian Review of Finance (Online) 21(4), 2023
                    Using hierarchical risk parity in the Brazilian market




4.    Empirical application

    The portfolio allocation strategies described in Section 3 were applied
to Brazilian financial assets and their out-of-sample portfolio performances
were compared. Analysis considered two different window sizes in a rolling
window scheme (T = 60 and T = 120, which correspond from five to ten
years of monthly data, respectively) as well as two out-of-sample periods (full
and before the COVID-19 pandemic) were considered. All analyses were per-
formed in R software (Team, 2022) using the packages RiskPortfolios and Hi-
erPortfolios of Ardia, Boudt and Gagnon-Fleury (2017) and Trucios (2021),
respectively. For reproduction purposes, the codes are freely available in the
GitHub repository https://github.com/felipereis150/Brazi
lianHRP

4.1    Data
    This study considered monthly returns spanning from January 2000 to
June 2022 of assets traded in the Brazilian stock market (B3) and listed in the
IBrX-100 index in July 2022. Series with missing values were excluded from
the analysis, ending up with 25 assets over 270 months. All stock price data
were downloaded from Economatica.
    Descriptive statistics for these assets returns are reported in Table 1 and
show that all returns have positive mean and kurtosis larger than 3, mini-
mum values between -27% and -55% and maximum values between 28% and
104%, approximately. The largest monthly return is reported by USIM5 (Usi-
nas Siderúrgicas de Minas Gerais - Usiminas) and the smallest one by LIGT3
(Light). USIM5 is √ also the most volatile asset with an annualized standard de-
viation of 59.3% ( 12 × 17.114) while VIVT3 (Telefônica Brasil) is the less
volatile asset with an annualized standard deviation of 26.5%, all but ABEV3
(Ambev) and SBSP3 (Companhia de Saneameno Básico do Estado de São
Paulo - SABESP) have positive skewness. The most correlated assets (0.972)
are PETR3 and PETR4 (Petrobras) and the less correlated ones (0.037) are
EGIE3 (Engie Brasil) and VALE3 (Vale).

4.2    Out-of-sample evaluation
   The out-of-sample portfolio performance was evaluated through economic
measures as seen in Santos and Tessari (2012), Lopez de Prado (2016), Gam-
bacciani and Paolella (2017), Trucíos et al. (2019), Oliveira et al. (2023),
among others. Specifically, following the financial econometric literature, six
well-known economic measures are used, briefly described as follows:


                     Brazilian Review of Finance (Online) 21(4), 2023        89
                                        Reis et al., 2023



                                        Table 1
     Descriptive statistics of monthly returns of 25 stocks in the Brazilian stock
                          market over the full sample period
                          Min.        Max.       Mean       Std.    Skew.   Kurt.
              ABEV3     −39.29       30.85        1.77       7.83   −0.27    6.28
              ALPA4     −38.94       44.65        2.50      11.06    0.05    4.16
              BBAS3     −40.18       47.54        2.14      11.98    0.17    4.56
              BBDC3     −31.03       35.73        1.69       9.67    0.40    3.62
              BBDC4     −31.93       30.43        1.69       9.83    0.19    3.42
              BRKM5     −35.96       57.67        1.79      13.42    0.57    4.05
              CMIG4     −36.18       54.05        1.63      10.63    0.37    5.54
              CPLE6     −33.74       28.68        1.41       9.96    0.01    3.24
              CSNA3     −50.23       83.78        2.56      15.85    0.52    5.28
              EGIE3     −29.66       56.18        2.19       9.40    1.47    9.45
              ELET3     −32.96       60.50        1.68      14.48    0.85    4.88
              ELET6     −40.25       44.48        1.69      12.99    0.42    4.20
              EMBR3     −43.77       39.14        1.01      11.64    0.07    5.04
              GGBR4     −40.53       84.70        2.03      13.18    0.84    8.38
              GOAU4     −45.06      100.83        1.91      14.08    1.07   11.91
              ITSA4     −26.86       31.47        1.72       8.68    0.03    3.50
              ITUB4     −27.81       36.10        1.61       9.12    0.08    3.92
              LIGT3     −55.51       52.56        0.31      13.53    0.44    5.26
              PETR3     −47.92       48.75        1.76      12.00    0.23    4.81
              PETR4     −44.79       62.45        1.72      11.93    0.39    5.84
              SBSP3     −34.93       37.68        1.52      10.50   −0.09    4.21
              TIMS3     −28.84       65.51        1.31      12.07    0.93    6.28
              USIM5     −45.16      104.54        2.17      17.11    1.19    9.22
              VALE3     −27.78       31.40        2.06      10.25    0.30    3.43
              VIVT3     −28.62       41.26        1.42       7.65    0.70    6.95


                                                           √
     • Annualized standard deviation (SD): is given by 12× σ̂ p , where σ̂ p
       is the sample standard deviation of the realized out-of-sample portfolio
       returns. The smaller the SD, the less risky the portfolio and, conse-
       quently, the better the portfolio performance.
                                                         √
     • Annualized Sharpe ratio (SR): is given by 12 × SR, where SR is
       the Sharpe ratio (Sharpe, 1975), a risk-adjusted performance measure
       defined by
                                           R̄ p − R̄ f
                                    SR =               ,
                                             σ̂ p− f
       where R̄ f is the average risk-free rate, R̄ p is the sample mean of the out-
       of-sample realized portfolio returns and σ̂ p− f is the estimated standard
       deviation of the realized out-of-sample excess returns. The higher the
       annualized SR, the better the portfolio performance.
                                                                       √
     • Annualized adjusted Sharpe ratio (ASR): is given by 12 × ASR,
       where ASR is the adjusted Sharpe ratio (Pézier and White, 2008), a
       risk-adjusted performance measure that penalizes the Sharpe ratio by


90                      Brazilian Review of Finance (Online) 21(4), 2023
               Using hierarchical risk parity in the Brazilian market




  negative skewness and an excess of kurtosis. It is given by
                        h    µ3      µ4 − 3  2 i
                ASR = SR 1 +     SR −         SR ,
                             6          24
  where µ3 and µ4 stand for the skewness and kurtosis of the out-of-
  sample portfolio returns. The higher the ASR, the better the portfolio
  performance.
                                             √
• Annualized Sortino ratio (SO): is given by 12×SO, where SO is the
  Sortino ratio (Sortino and Van Der Meer, 1991), another risk-adjusted
  performance measure. It is defined by

                                          R̄ p
                    SO = r                                 ,
                                  K
                                 ∑i=1 min(0, R p,i − MAR)2
                                                   K
  where K is the size of the out-of-sample period and MAR is the mini-
  mum accepted return, which is equal to the monthly risk-free rate. The
  higher the SO, the better the portfolio performance.

• Average portfolio turnover (TO): measures the impact of transaction
  costs on portfolio performance per rebalancing, on average. It is given
  by
                              1 K N
                      TO =        ∑ ∑ |ω̂i, j − ω̂i,+j |,
                            K − 1 i=2 j=1

           +
  where ω̂i−1 stands for the one-step-ahead portfolio weights obtained
  in the window i − 1 updated at time i before rebalancing to ω̂i . Lower
  values of TO indicate smaller impacts of transaction costs on portfolio
  performance.

• Sum of squared portfolio weights (SSPW): measures the diversifi-
  cation of the portfolio. The SSPW (Goetzmann and Kumar, 2008) is
  given by
                                  1 K N
                           SSPW = ∑ ∑ ω̂i,2 j ,
                                  K i=1 j=1

  where ω̂i, j stands for the one-step-ahead portfolio weights obtained in
  the window i for asset j. Lower values of SSPW indicate higher levels
  of diversification.


                Brazilian Review of Finance (Online) 21(4), 2023        91
                                           Reis et al., 2023




     In addition to the six measures described above, the bootstrap tests of
 Ledoit and Wolf (2008) and Ledoit and Wolf (2011) are used to verify whether
 the SR and the SD of HRP are statistically superior to the other methods, re-
 spectively. This article considered the value of the monthly risk-free rate as
 0.005, which is compatible with the monthly Brazilian interest rate (CDI, in
 Portuguese).2

 4.3    Results
     Results for the out-of-sample analysis are reported in Table 2. The top and
 bottom panels report the results considering window sizes of T = 60 and T =
 120 months, respectively. The left and right panels report the results for the
 full and before the COVID-19 pandemic out-of-sample periods, respectively.
 In addition to the portfolio allocation strategies described in Section 3, the
 out-of-sample performance of the Bovespa index was also included. Window
 sizes of T = 60 and T = 120 months yield to out-of-sample periods of 210
 and 150 months in the full out-of-sample case and 182 and 122 months in the
 out-of-sample period before the COVID-19 pandemic, respectively.
     Whichever the window size (T = 60 or T = 120) and the out-of-sample
 period considered (full or before the COVID-19 pandemic), the smallest SD is
 obtained by the MV portfolio strategy, closely followed by the HRP portfolio
 (for the full out-of-sample period) and by the MD portfolio (for the out-of-
 sample period before the COVID-19 pandemic). However, despite the differ-
 ences observed (in absolute values), when the equality of variances is testing
 between HRP against each one of the other strategies, the bootstrap test of
 Ledoit and Wolf (2011) only rejects the null when HRP is tested against MV
 in all scenarios (p-value = 0.0056 for T = 60 and 0.0004 for T = 120 in the
 full out-of-sample period and p-value = 0.0424 for T = 60 and 0.0038 for
 T = 120 in the out-of-sample period before the COVID-19 pandemic) and
 when HRP is testing against MDE for T = 120 in the out-of-sample period
 before the COVID-19 pandemic (p-value = 0.0220). In all other cases, the null
 is not rejected at 5% of significance, meaning that, except in the aforemen-
 tioned situations, no evidence of differences in the out-of-sample variance
 between HRP and its competitors is observed.
     In terms of SR, the highest and smallest values are obtained by the MDE
 portfolio allocation strategy and by the market index (IBOV), respectively.
 The equality of SR for HRP against each one of the other strategies is tested
 using the bootstrap test of Ledoit and Wolf (2008), which rejects the null
2 This value is quite conservative in the Brazilian scenario. Actually, a monthly risk-free rate of

 0.5% is smaller than the average monthly Brazilian interest rate in the period analyzed.


 92                        Brazilian Review of Finance (Online) 21(4), 2023
                           Using hierarchical risk parity in the Brazilian market




 when HRP is compared against IBOV in three out of the four scenarios (p-
 value = 0.0286 for T = 60 and 0.0420 for T = 120 in the full out-of-sample
 period and p-value = 0.0250 for T = 120 in the out-of-sample period before
 the COVID-19 pandemic). In all other cases, the null is not rejected at 5%
 of significance, indicating no evidence of differences in the SR between HRP
 and its competitors.
     With respect to the two other risk-adjusted performance measures, namely,
 ASR and SO, results are similar to the obtained for the SR. An important dif-
 ference is observed between the portfolio allocation strategies implemented
 concerning the impact of transaction costs in each one of them. Overall, HRP
 reports the highest average turnover, which means that this strategy is more
 impacted by transaction costs than all others. Additionally, although HRP
 does not report the worst performance in terms of diversification, it is always
 outperformed by the IV, RP, and EW portfolios.
     In general, if risk-adjusted performance measures are of primary impor-
 tance and transaction costs can be neglected, HRP performs as well as all
 other strategies.3 However, because of its larger values in absolute terms,
 MDE could be preferred. If either transaction cost or diversification measures
 cannot be neglected, HRP is not a preferable strategy due to its high aver-
 age turnover and SSPW. Conversely, if risk is of primary importance, MV
 portfolio should be preferred.
     Figure 1 displays the accumulated returns over the full out-of-sample pe-
 riod of all strategies implemented and reported in Table 4 when T = 120. Note
 the poor performance of IBOV in comparison to all other strategies and also
 note that all strategies suddenly drop in March 2020, when the World Health
 Organization declared the SARS-COVID-19 virus as a pandemic.
     A similar analysis considering only ordinary stocks and excluding high
 correlated assets of the same company was also performed.4 The results are
 reported in Table 3 and in general are similar to those obtained in Table 2,
 yielding to the same conclusions.

 5.   Conclusions

     This paper has empirically evaluated the recently proposed HRP portfolio
 allocation strategy for the Brazilian financial market. The out-of-sample per-
 formance was compared against six widely-known portfolio allocation strate-
3 For the SR, the bootstrap test of Ledoit and Wolf (2008) helps verify this. For the other two risk-

  adjusted measures, no bootstrap test is available to its use and one focused on the magnitude of
  the differences, which is almost similar to the obtained in the SR case.
4 The assets removed were BBDC4, ELET6, PETR4, ITSA4 and GGBR4.




                            Brazilian Review of Finance (Online) 21(4), 2023                      93
                                                    Reis et al., 2023



                                  Figure 1
Accumulated out-of-sample portfolio returns from to January 2010 to June 2022
                    200




                    150




                                                                                      EW
                    100                                                               HRP
Portfolio returns




                                                                                      Ibov
                                                                                      IV
                                                                                      MD
                                                                                      MDE
                                                                                      MV
                     50                                                               RP




                      0




                    −50
                          2010               2015                              2020
                                                        Date




gies, as well as the Bovespa index. The comparison considered six out-of-
sample performance measures and included different windows sizes and out-
of-sample periods, yielding to four scenarios.
     In terms of SD, the MV portfolio achieves the best performance and, ac-
cording to the test of Ledoit and Wolf (2011), outperforms HRP. The same
test does not reject the null of equality of variance of HRP against each one
of the other strategies.
     When the SR is of interest, HRP and several other strategies perform sta-
tistically equal, with no preference among them, except in case of transaction
cost or diversification are important, HRP is not the best option. Similar re-
sults are obtained when the two other risk-adjusted performance measures are
of interest.
     In general terms, while HRP is not the best strategy it is not a strategy
to be ruled out when portfolios of Brazilian assets are build, except possibly
when transaction costs are of crucial importance.
     Finally, clustering-based machine learning portfolio allocation strategies
are a new, innovative idea to deal with diversification. There are many con-
tributions to be developed in this direction, including other ouf-of-sample


94                               Brazilian Review of Finance (Online) 21(4), 2023
                    Using hierarchical risk parity in the Brazilian market




comparisons, the effect of covariance matrix misspecification on the portfolio
weights, among others. Some of these points are in the research agenda of the
third author.

Acknowledgments
    The third author acknowledges financial support from grant 2022/09122-
0, São Paulo Research Foundation (FAPESP) and Programa de Incentivo a
Novos Docentes da UNICAMP (PIND) grant 2525/23. All authors acknowl-
edge the computational support of the Center for Applied Research on Econo-
metrics, Finance, and Statistics (CAREFS), Brazil.

References
Ardia, D., Bolliger, G., Boudt, K. and Gagnon-Fleury, J.-P. (2017). The im-
  pact of covariance misspecification in risk-based portfolios, Annals of Op-
  erations Research 254: 1–16.

Ardia, D., Boudt, K. and Gagnon-Fleury, J.-P. (2017). Riskportfolios: Com-
  putation of risk-based portfolios in R, Journal of Open Source Software
  10(2).

Bai, X., Scheinberg, K. and Tutuncu, R. (2016). Least-squares approach to
  risk parity in portfolio selection, Quantitative Finance 16(3): 357–376.

Battaglia, T. K. and Leal, R. P. (2017). Equally weighted portfolios of ran-
  domly selected stocks and the individual investor, Latin American Business
  Review 18(1): 69–90.

Becker, F., Gürtler, M. and Hibbeln, M. (2015). Markowitz versus Michaud:
  Portfolio optimization strategies reconsidered, The European Journal of
  Finance 21(4): 269–291.

Borges, B., Caldeira, J. F. and Ziegelmann, F. A. (2015). Selection of min-
  imum variance portfolio using intraday data: An empirical comparison
  among different realized measures for bm&fbovespa data, Brazilian Re-
  view of Econometrics 35(1): 23–46.

Bortoluzzo, M. M., Bortoluzzo, A. B., Imamura, R. A., Melhado, T. T., De,
  R. D. C. M. L. et al. (2018). Comparação do desempenho de carteiras uti-
  lizando ds métodos paridade de risco, mínima variância e equal weighting:
  Um estudo no mercado brasileiro em períodos pré, durante e pós a crise de
  2008, Revista Evidenciaçao Contábil & Finanças 6(3): 37–53.


                     Brazilian Review of Finance (Online) 21(4), 2023        95
                                     Reis et al., 2023




Burggraf, T. (2021). Beyond risk parity–A machine learning-based hierar-
  chical risk parity approach on cryptocurrencies, Finance Research Letters
  38: 101523.
Caldeira, J. F., Moura, G. V. and Santos, A. A. (2013). Seleção de carteiras
  utilizando o modelo Fama-French-Carhart, Revista Brasileira de Economia
  67: 45–65.
Caldeira, J. F., Moura, G. V., Perlin, M. S. and Santos, A. A. (2017). Portfolio
  management using realized covariances: Evidence from Brazil, EconomiA
  18(3): 328–343.
Chaves, D., Hsu, J., Li, F. and Shakernia, O. (2011). Risk parity portfo-
  lio vs. other asset allocation heuristic portfolios, The Journal of Investing
  20(1): 108–118.
Chopra, V. K., Hensel, C. R. and Turner, A. L. (1993). Massaging mean-
  variance inputs: Returns from alternative global investment strategies in
  the 1980s, Management Science 39(7): 845–855.
Chopra, V. K. and Ziemba, W. T. (1993). The effect of errors in means, vari-
  ances, and covariances on optimal portfolio choice, The Journal of Portfo-
  lio Management 19(2): 6–11.
Choueifaty, Y., Froidure, T. and Reynier, J. (2013). Properties of the most
  diversified portfolio, Journal of Investment Strategies 2(2): 49–70.
Choueifaty, Y. and Coignard, Y. (2008). Toward maximum diversification,
  The Journal of Portfolio Management 35(1): 40–51.
Christoffersen, P., Errunza, V., Jacobs, K. and Langlois, H. (2012). Is the
  potential for international diversification disappearing? A dynamic copula
  approach, The Review of Financial Studies 25(12): 3711–3751.
De Carvalho, R. L., Lu, X. and Moulin, P. (2012). Demystifying equity risk-
  based strategies: A simple alpha plus beta description, The Journal of Port-
  folio Management 38(3): 56–70.
De Nard, G., Ledoit, O. and Wolf, M. (2021). Factor models for portfolio
  selection in large dimensions: The good, the better and the ugly, Journal of
  Financial Econometrics 19(2): 236–257.
DeMiguel, V., Garlappi, L. and Uppal, R. (2009). Optimal versus naive di-
  versification: How inefficient is the 1/N portfolio strategy?, The Review of
  Financial Studies 22(5): 1915–1953.


96                   Brazilian Review of Finance (Online) 21(4), 2023
                    Using hierarchical risk parity in the Brazilian market




du Plessis, H. and van Rensburg, P. (2020). Risk-based portfolio sensitivity
  to covariance estimation, Investment Analysts Journal 49(3): 243–268.

Duarte, F. G. and De Castro, L. N. (2020). A framework to perform asset
  allocation based on partitional clustering, IEEE Access 8: 110775–110788.

Duchin, R. and Levy, H. (2009). Markowitz versus the Talmudic portfolio
  diversification strategies, The Journal of Portfolio Management 35(2): 71–
  74.

Engle, R. F., Ledoit, O. and Wolf, M. (2019). Large dynamic covariance
  matrices, Journal of Business & Economic Statistics 37(2): 363–375.

Fan, J., Zhang, J. and Yu, K. (2012). Vast portfolio selection with gross-
  exposure constraints, Journal of the American Statistical Association
  107(498): 592–606.

Farias, C. A., Vieira, W. d. C. and Santos, M. L. d. (2006). Portfolio selection
  models: Comparative analysis and applications to the Brazilian stock mar-
  ket, Revista de Economia e Agronegocio/Brazilian Review of Economics
  and Agribusiness 4(822-2016-54112): 387–407.

Freitas, W. B. and Junior, J. R. B. (2023). Random walk through a stock
  network and predictive analysis for portfolio optimization, Expert Systems
  with Applications p. 119597.

Fugazza, C., Guidolin, M. and Nicodano, G. (2015). Equally weighted vs.
  long-run optimal portfolios, European Financial Management 21(4): 742–
  789.

Gambacciani, M. and Paolella, M. S. (2017). Robust normal mixtures for
  financial portfolio allocation, Econometrics and Statistics 3: 91–111.

Goetzmann, W. N. and Kumar, A. (2008). Equity portfolio diversification,
  Review of Finance 12(3): 433–463.

Goltz, F. and Sivasubramanian, S. (2018). Scientific beta maximum decorre-
  lation indices, Working Paper: ERI Scientific Beta Publication .

Huang, M. and Yu, S. (2020). A new procedure for resampled portfolio with
  shrinkaged covariance matrix, Journal of Applied Statistics 47(4): 642–
  652.


                     Brazilian Review of Finance (Online) 21(4), 2023        97
                                     Reis et al., 2023




Iquiapaza, R. A., Vaz, G. F. C. and Borges, S. L. (2016). Portfolio evaluation
  of volatility timing and reward to risk timing investment strategies: The
  Brazilian case, Revista de Finanças Aplicadas 7(2): 1–19.
Konno, H. and Yamazaki, H. (1991). Mean-absolute deviation portfolio op-
  timization model and its applications to Tokyo stock market, Management
  Science 37(5): 519–531.
Leal, R. P. C. and Campani, C. H. (2016). Valor-coppead indices, equally
  weighed and minimum variance portfolios, Brazilian Review of Finance
  14(1): 45–65.
Ledoit, O. and Wolf, M. (2008). Robust performance hypothesis testing with
  the Sharpe ratio, Journal of Empirical Finance 15(5): 850–859.
Ledoit, O. and Wolf, M. (2011). Robust performances hypothesis testing with
  the variance, Wilmott 2011(55): 86–89.
Lopez de Prado, M. (2016). Building diversified portfolios that outperform
  out-of-sample, Journal of Portfolio Management 42(4): 59–69.
Maciel, L. (2021). A new approach to portfolio management in the Brazil-
 ian equity market: Does assets efficiency level improve performance?, The
 Quarterly Review of Economics and Finance 81: 38–56.
Maillard, S., Roncalli, T. and Teïletche, J. (2010). The properties of equally
 weighted risk contribution portfolios, The Journal of Portfolio Manage-
 ment 36(4): 60–70.
Malladi, R. and Fabozzi, F. J. (2017). Equal-weighted strategy: Why it out-
 performs value-weighted strategies? theory and evidence, Journal of Asset
 Management 18: 188–208.
Markowitz, H. (1952). Portfolio selection, Journal of Finance 7(1): 77–91.
Markowitz, H. (1959). Portfolio selection: Efficient diversification of invest-
 ments, Vol. 16 of Cowles Foundation Monograph, 2 ed., Wiley, New York.
Merton, R. C. (1980). On estimating the expected return on the market: An
 exploratory investigation, Journal of Financial Economics 8(4): 323–361.
Meucci, A. (2007). Risk and asset allocation, first ed., Springer, New York.
Michaud, R. and Michaud, R. (1998). Efficient asset management: A practical
 guide to stock portfolio optimization and asset allocation, first ed., Harvard
 Business School Press, Boston.


98                   Brazilian Review of Finance (Online) 21(4), 2023
                    Using hierarchical risk parity in the Brazilian market




Michaud, R. O. (1989). The Markowitz optimization enigma: Is ‘optimized’
 optimal?, Financial Analysts Journal 45(1): 31–42.
Naibert, P. F. and Caldeira, J. F. (2015). Seleção de carteiras ótimas sob
  restrições nas normas dos vetores de alocação: Uma avaliação empírica
  com dados da BM&FBovespa, Brazilian Review of Finance 13(3): 504–
  543.
Nakagawa, K., Imamura, M. and Yoshida, K. (2018). Risk-based portfolios
  with large dynamic covariance matrices, International Journal of Financial
  Studies 6(2): 52.
Nourahmadi, M. and Sadeqi, H. (2022). A machine learning-based hierarchi-
  cal risk parity approach: A case study of portfolio consisting of stocks of
  the top 30 companies on the Tehran stock exchange, Financial Research
  Journal 24(2): 236–256.
Oliveira, A., Trucíos, C. and Valls Pereira, P. (2023). Does portfolio re-
  sampling really improve out-of-sample performance? Evidence from the
  Brazilian and US markets., Working Paper .
Pereira, P. L. V. and Oliveira, A. B. (2021). Estratégias de investimento em
  portfólios com estimativas de alta e baixa do mercado financeiro, Brazilian
  Review of Finance 19(4): 160–185.
Pflug, G. C., Pichler, A. and Wozabal, D. (2012). The 1/N investment strategy
   is optimal under high model ambiguity, Journal of Banking & Finance
   36(2): 410–417.
Pézier, J. and White, A. (2008). The relative merits of alternative investments
  in passive portfolios, The Journal of Alternative Investments 10(4): 37–49.
Qian, E. (2005). Risk parity portfolios: Efficient portfolios through true di-
  versification, Panagora Asset Management .
Qian, E. (2006). On the financial interpretation of risk contribution: Risk
  budgets do add up, Journal of Investment Management 4(4): 41–51.
Qian, E. (2011). Risk parity and diversification, The Journal of Investing
  20(1): 119–127.
Qian, E. (2013). Are risk-parity managers at risk parity?, The Journal of
  Portfolio Management 40(1): 20–26.
Qian, E. (2016). Risk parity fundamentals, CRC Press.


                     Brazilian Review of Finance (Online) 21(4), 2023        99
                                     Reis et al., 2023




Rubesam, A., Beltrame, A. L. et al. (2013). Minimum variance portfolios in
  the Brazilian equity market, Brazilian Review of Finance 11(1): 81–118.

Santos, A. A. and Moura, G. V. (2014). Dynamic factor multivariate GARCH
  model, Computational Statistics & Data Analysis 76: 606–617.

Santos, A. A. P. and Tessari, C. (2012). Técnicas quantitativas de otimização
  de carteiras aplicadas ao mercado de ações brasileiro, Brazilian Review of
  Finance 10(3): 369–393.

Sen, J. and Dutta, A. (2022). A comparative study of hierarchical risk par-
  ity portfolio and eigen portfolio on the NIFTY 50 stocks, Computational
  Intelligence and Data Analytics: Proceedings of ICCIDA 2022, Springer,
  pp. 443–460.

Sen, J., Mehtab, S., Dutta, A. and Mondal, S. (2021). Hierarchical risk parity
  and minimum variance portfolio design on NIFTY 50 stocks, 2021 Inter-
  national Conference on Decision Aid Sciences and Application (DASA),
  IEEE, pp. 668–675.

Sharpe, W. F. (1975). Adjusting for risk in portfolio performance measure-
  ment, The Journal of Portfolio Management 1(2): 29–34.

Simon, H. A. (1962). The architecture of complexity, Proceedings of the
  American Philosophical Society 106(6): 467–482.

Sortino, F. A. and Van Der Meer, R. (1991). Downside risk, Journal of Port-
  folio Management 17(4): 27.

Souza, L. C., Massardi, W. O., Pires, V. A. V. and Ciribeli, J. P. (2017).
  Otimização de carteira de investimentos: Um estudo com ativos do
  Ibovespa, Revista de Gestão, Finanças e Contabilidade 7(3): 201–213.

Team, R. C. (2022). R: A language and environment for statistical computing,
  R Foundation for Statistical Computing, Vienna, Austria.

Trucios, C. (2021). HierPortfolios: Hierarchical clustering-based portfolio
  allocation strategies. R package version 0.1.0.

Trucíos, C., Mazzeu, J. H., Hallin, M., Hotta, L. K., Valls Pereira, P. L. and
  Zevallos, M. (2023). Forecasting conditional covariance matrices in high-
  dimensional time series: A general dynamic factor approach, Journal of
  Business & Economic Statistics 41(1): 40–52.


100                  Brazilian Review of Finance (Online) 21(4), 2023
                   Using hierarchical risk parity in the Brazilian market




Trucíos, C., Zevallos, M., Hotta, L. K. and Santos, A. A. (2019). Covariance
  prediction in large portfolio allocation, Econometrics 7(2): 19.
Wolf, M. (2004). Resampling vs. shrinkage for benchmarked managers,
 Shrinkage for Benchmarked Managers (July 2004) .
Young, M. R. (1998). A minimax portfolio selection rule with linear pro-
  gramming solution, Management Science 44(5): 673–683.




                    Brazilian Review of Finance (Online) 21(4), 2023        101
102
                                                                                                                             Table 2
                                                                                                              Out-of-sample performance of portfolios
                                                                                                         Full out-of-sample period                          Out-of-sample period before COVID
                                                                               Method    SD       SR         ASR        SO           TO     SPPW     SD       SR      ASR        SO       TO       SPPW
                                                                               IBOV     23.24     0.19        0.19      0.26                        21.91     0.25     0.25      0.34
                                                                               EW       24.92     0.45        0.45      0.59         0.06    0.04   23.86     0.50     0.50      0.62     0.06       0.04
                                                                               MV       17.67     0.34        0.34      0.47         0.13    0.21   17.15     0.42     0.42      0.55     0.13       0.20
                                                                               RP       21.52     0.47        0.46      0.62         0.07    0.05   20.30     0.54     0.54      0.68     0.07       0.05
                                                                               MD       19.80     0.42        0.42      0.58         0.13    0.17   18.12     0.51     0.51      0.66     0.13       0.16




                                                                     T = 60
                                                                               MDE      21.75     0.49        0.48      0.65         0.14    0.14   19.70     0.58     0.58      0.72     0.14       0.14
                                                                               IV       22.85     0.44        0.44      0.58         0.06    0.04   21.85     0.50     0.51      0.63     0.06       0.04
                                                                               HRP      19.61     0.42        0.41      0.56         0.19    0.08   18.76     0.48     0.48      0.62     0.20       0.08
                                                                               IBOV     22.11   −0.03        −0.03     −0.04                        19.71     0.00     0.00      0.00
                                                                                                                                                                                                                               Reis et al., 2023




                                                                               EW       25.48    0.32         0.32      0.42         0.06    0.04   24.06     0.34     0.35      0.42     0.06       0.04
                                                                               MV       15.74    0.26         0.26      0.36         0.08    0.19   14.26     0.36     0.36      0.47     0.08       0.18
                                                                               RP       21.71    0.29         0.29      0.39         0.06    0.05   19.89     0.34     0.34      0.43     0.06       0.05
                                                                               MD       19.87    0.29         0.29      0.41         0.11    0.13   16.66     0.36     0.36      0.48     0.11       0.13




                                                                     T = 120
                                                                               MDE      21.84    0.36         0.35      0.48         0.11    0.12   18.53     0.42     0.42      0.53     0.11       0.12
                                                                               IV       23.32    0.29         0.29      0.39         0.06    0.04   21.93     0.34     0.34      0.42     0.06       0.04




Brazilian Review of Finance (Online) 21(4), 2023
                                                                               HRP      19.72    0.28         0.28      0.39         0.15    0.07   18.24     0.38     0.38      0.48     0.16       0.06
                                                   Portfolios were constructed using equal-weight, hierarchical risk parity and minimum variance portfolios. Full out-of-sample period (left panel) and out-of-sample period
                                                   before COVID-19 pandemic (right panel)
                                                                                                               Table 3
                                                              Out-of-sample performance of portfolios – ordinary stocks excluding same-company highly correlated assets
                                                                                                         Full out-of-sample period                          Out-of-sample period before COVID
                                                                               Method    SD       SR         ASR        SO           TO     SPPW     SD       SR      ASR        SO       TO       SPPW
                                                                               IBOV     23.24     0.19        0.19      0.26                        21.91     0.25     0.25      0.34
                                                                               EW       23.87     0.46        0.46      0.60         0.07    0.05   22.69     0.51     0.52      0.64     0.06       0.05
                                                                               MV       17.60     0.35        0.35      0.48         0.12    0.21   17.07     0.43     0.43      0.56     0.13       0.20
                                                                               RP       20.52     0.46        0.45      0.62         0.07    0.06   19.21     0.54     0.54      0.69     0.07       0.06
                                                                               MD       19.78     0.42        0.41      0.57         0.13    0.17   18.09     0.50     0.50      0.65     0.13       0.16




                                                                     T = 60
                                                                               MDE      21.74     0.48        0.47      0.64         0.13    0.14   19.68     0.57     0.57      0.71     0.13       0.14
                                                                               IV       21.58     0.45        0.44      0.59         0.06    0.06   20.50     0.52     0.52      0.65     0.06       0.06
                                                                               HRP      18.85     0.43        0.42      0.58         0.18    0.10   17.92     0.51     0.50      0.65     0.18       0.09
                                                                               IBOV     22.11   −0.03        −0.03     −0.04                        19.71     0.00     0.00      0.00
                                                                               EW       24.39    0.34         0.33      0.45         0.07    0.05   22.78     0.38     0.38      0.47     0.07       0.05
                                                                               MV       15.73    0.26         0.26      0.36         0.08    0.19   14.25     0.36     0.36      0.48     0.08       0.18
                                                                               RP       20.77    0.31         0.30      0.42         0.06    0.06   20.48     0.38     0.38      0.48     0.06       0.05
                                                                               MD       19.87    0.29         0.29      0.40         0.10    0.14   18.80     0.38     0.38      0.48     0.06       0.06




                                                                     T = 120
                                                                               MDE      21.85    0.35         0.35      0.47         0.10    0.12   16.66     0.36     0.36      0.47     0.10       0.13
                                                                               IV       21.99    0.32         0.32      0.43         0.06    0.05   18.54     0.41     0.41      0.52     0.10       0.12




Brazilian Review of Finance (Online) 21(4), 2023
                                                                                                                                                                                                                               Using hierarchical risk parity in the Brazilian market




                                                                               HRP      18.63    0.33         0.33      0.46         0.14    0.08   16.91     0.43     0.43      0.55     0.14       0.07
                                                   Portfolios were constructed using equal-weight, hierarchical risk parity and minimum variance portfolios. Full out-of-sample period (left panel) and out-of-sample period
                                                   before COVID-19 pandemic (right panel)




103