source: https://www.uzh.ch/cmsssl/econ/dam/jcr:0feec5fa-5084-4580-a2d3-f96b8fee877c/nbab001.pdf
fetched_utc: 2026-10-04T18:37:41Z
bytes_raw: 874293

Journal of Financial Econometrics, 2023, Vol. 21, No. 1, 73–105
                                                                  doi: 10.1093/jjfinec/nbab001
                                     Advance Access Publication Date: 26 February 2021




                                                                                                        Downloaded from https://academic.oup.com/jfec/article/21/1/73/6151211 by University Library Zurich / Zentralbibliothek Zurich user on 23 May 2023
                                                                               Article



Risk Reduction and Efficiency Increase in
Large Portfolios: Gross-Exposure
Constraints and Shrinkage of the
Covariance Matrix*
Zhao Zhao1, Olivier Ledoit2 and Hui Jiang                                            3
1
 School of Economics, Huazhong University of Science and Technology, 2University of Zurich and
AlphaCrest Capital Management and 3School of Mathematics and Statistics, Huazhong University
of Science and Technology

Address correspondence to Hui Jiang, School of Mathematics and Statistics, Huazhong University of
Science and Technology, Wuhan, Hubei, China, or e-mail: jianghui@hust.edu.cn.
Received July 5, 2020; revised January 2, 2021; editorial decision January 6, 2021


Abstract
We investigate the effects of constraining gross-exposure and shrinking covariance
matrix in constructing large portfolios, both theoretically and empirically.
Considering a wide variety of setups that involve conditioning or not conditioning
the covariance matrix estimator on the recent past (multivariate GARCH),
smaller versus larger universe of stocks, alternative portfolio formation objectives
(global minimum variance versus exposure to profitable factors), and various
transaction cost assumptions, we find that a judiciously chosen shrinkage method
always outperforms an arbitrarily determined constraint on gross-exposure. We ex-
tend the mathematical connection between constraints on the gross-exposure and
shrinkage of the covariance matrix from static to dynamic, and provide a new ex-
planation for our finding from the perspective of degrees of freedom. In addition,
both simulation and empirical analysis show that the dynamic conditional
correlation-nonlinear shrinkage (DCC-NL) estimator results in risk reduction and effi-
ciency increase in large portfolios as long as a small amount of short position is
allowed, whereas imposing a constraint on gross-exposure often hurts a DCC-NL
portfolio.




 * We acknowledge the financial support from the National Natural Science Foundation of China
   (Grant Nos. 71803055, 11801197 and 72033002), and the Fundamental Research Funds for the
   Central Universities 2018KFYYXJJ040. We also thank Prof. Fabio Trojani (the Editor); two anonymous
   referees; and Prof. Michael Wolf, Prof. Yixiao Sun, and Dr. Gianluca De Nard for valuable comments
   and suggestions. Any errors are of authors.

C The Author(s) 2021. Published by Oxford University Press. All rights reserved.
V
For permissions, please email: journals.permissions@oup.com
74                                                         Journal of Financial Econometrics


Key words: DCC; gross-exposure constraint; large portfolios; mean–variance efficient; nonlinear




                                                                                                  Downloaded from https://academic.oup.com/jfec/article/21/1/73/6151211 by University Library Zurich / Zentralbibliothek Zurich user on 23 May 2023
shrinkage; risk reduction
JEL classification: C13, C58, G11




It is well established that using the sample covariance matrix is inappropriate in construct-
ing large unconstrained portfolios, which will lead to extreme positions and poor out-of-
sample performance. To improve the performance of portfolios, two different methods are
very popular. The first one is to constrain (e.g., Jagannathan and Ma, 2003; DeMiguel
et al., 2009a; Fan, Zhang, and Yu, 2012; Behr, Guettler, and Miebs, 2013; Li, 2015) or
shrink (e.g., Golosnoy and Okhrin, 2007; Frahm and Memmel, 2010; Tu and Zhou, 2011;
DeMiguel, Martin-Utrera, and Nogales, 2013; Bodnar, Parolya, and Schmid, 2018) the
portfolio weights directly, and the second is to use an improved estimator of covariance ma-
trix to constrain or shrink the portfolio weights indirectly (e.g., Ledoit and Wolf, 2003,
2017a; Fan, Fan, and Lv, 2008, Fan, Liao, and Mincheva, 2013; Engle, Ledoit, and Wolf,
2019; De Nard, Ledoit, and Wolf, 2020).
    There is a general perception that constraining the portfolio weights is a simple alterna-
tive to shrinking the covariance matrix. Studies share the same theoretical analysis on why
the two approaches are beneficial to large portfolios: the extreme sample covariances be-
tween stocks that lead to extreme weights are usually caused by estimation errors (see foot-
note 8 in DeMiguel et al., 2009b, for illustration); thus, imposing constraints on portfolio
weights or shrinking the sample covariances can reduce the sampling error and improve the
out-of-sample performance. Although some people may have read this connection as a con-
firmation that “shrinkage is not necessary,” it could equally be interpreted as saying that
shrinkage works because we (meaning the asset management and finance professors who
impose constraints on portfolio weights) have been effectively shrinking all along without
even knowing it.
    This paper aims at providing a comparative analysis of the two approaches and getting
the best of both worlds. In particular, we work in the realm of fully invested portfolios, that
is, portfolios whose weights sum up to one, which is the default choice for the bulk of the
asset management industry (as opposed to weights summing up to zero). Even though the
weights sum up to one, there is some leeway to take on short positions, and an interesting
question is how much. The major candidates are the strategy without any constraint on
gross-exposure, the so-called “150/50” strategy (meaning that for $100 million of capital,
the prime broker enables you to go $150 million long if you go $50 million short at the
same time, for a net exposure to the stock market of $100 million, which is exactly equal to
the capital invested), the “130/30” strategy, and the “100/0” strategy (no short sales are
allowed). For a more solid analysis, we consider a wide choice for the constraint on short
sales, with the gross-exposure constraint parameter continuously increasing from 1 (the
“100/0” strategy) to 16 (the “850/750” strategy). Moreover, at the same time, instead of
linearly shrinking the unconditional covariance matrix as the previous literature does, we
allow each of the eigenvalues of the sample covariance matrix to have its own shrinkage in-
tensity, optimally determined under large-dimensional asymptotics, while also incorporat-
ing multivariate GARCH effects.
Zhao et al. j Risk Reduction and Efficiency Increase                                                      75


    Our paper makes the following contributions to the literature that deals with risk reduc-




                                                                                                                Downloaded from https://academic.oup.com/jfec/article/21/1/73/6151211 by University Library Zurich / Zentralbibliothek Zurich user on 23 May 2023
tion and efficiency increase in large portfolios. First, we extend the mathematical equiva-
lency of constraining portfolio weights and shrinking the covariance matrix from the
conventional static framework to dynamic, where multivariate GARCH effects are incorpo-
rated. Second, we find that using the judiciously chosen shrunk covariance matrix always
outperforms the strategy of imposing an arbitrarily determined gross-exposure constraint.
We provide a new theoretical explanation from the perspective of degrees of freedom to
bridge the gap between theory and practice. Third, we reveal the best of both the shrinkage
estimator and the gross-exposure constraint, which can provide enlightenments to quantita-
tive investors and analysts. Moreover, we find that the nonlinear (NL) shrinkage of the co-
variance matrix improves a large portfolio as long as a small amount of short position is
allowed, but imposing a constraint on gross-exposure often hurts a covariance-shrunk
portfolio.
    If constraining weights and shrinking covariances are essentially equivalent, then why is
shrinkage still beneficial for portfolios with moderate gross-exposure constraints? The an-
swer is that constraining the gross-exposure has only one degree of freedom, that is, the
amount of gross-exposure permitted; whereas shrinkage of the NL kind—as utilized here—
has as many degrees of freedom as there are variables in the system, which is assumed to be
a large number, and these are individually optimized in an asymptotic sense as matrix di-
mension and sample size go to infinity together. Thus, the influence of shrinkage is fine-
tuned automatically, whereas gross-exposure constraint applies uniformly across the
board.1 The gross-exposure constraint, therefore, is redundant when the optimal shrinkage
is provided by the NL shrinkage method.
    Our Monte Carlo simulation and empirical analysis demonstrate the advantage of using
the NL shrinkage covariance matrix estimator over imposing the gross-exposure constraints
for a wide range of constrained portfolios. Additionally, we find that using the dynamic
conditional correlation (DCC) model improves the portfolio performance. Consequently,
the DCC-NL shrinkage (DCC-NL) portfolio is always preferred: as long as some short posi-
tions are allowed, which can be done in many fully invested funds as long as the prime bro-
ker allows it, the DCC-NL delivers the best performance. Our findings are stable in
simulations, where both normally distributed and t-distributed disturbance terms are con-
sidered, as well as in empirical exercises, where both the global minimum variance (GMV)
portfolios and the mean–variance efficient (MVE) portfolios exposed to profitable factors
are constructed.
    We know that since the groundbreaking work of Markowitz (1952), statistics and opti-
mization techniques have been used to develop diversified investment strategies that either
(i) minimize risk, subject to exposure to the stock market (the GMV portfolio) or (ii) are ef-
ficient in terms of risk-return trade-off (the MVE portfolio). The first type is a purer test of
the covariance matrix estimator and the optimization program used, whereas the second
one requires, in addition, a good predictive model for expected returns, which is notorious-
ly hard to obtain.



1 Behr, Guettler, and Miebs (2013) extend the arbitrarily chosen constraints on weights to flexible ex
  ante constraints that can better suit the data, but it is still infeasible to guarantee that all individual
  weights are optimally shrunk.
76                                                        Journal of Financial Econometrics


    During the past decades, on the one hand, various attempts have been made to reduce




                                                                                                 Downloaded from https://academic.oup.com/jfec/article/21/1/73/6151211 by University Library Zurich / Zentralbibliothek Zurich user on 23 May 2023
the estimation errors of the large-dimensional covariance matrix. Imposing the assumption
of a factor structure (e.g., Stock and Watson, 2002; Fan, Fan, and Lv, 2008; Bai and Li,
2012; Fan, Liao, and Mincheva, 2013) and shrinking the sample covariance matrix (Ledoit
and Wolf, 2003, 2004a, 2004b, 2012, 2015, 2020a) are two popular and effective ways.
The shrinkage method can also be used in a factor model to estimate the residual covariance
matrix (De Nard, Ledoit, and Wolf, 2020). On the other hand, a variety of methods have
been introduced in the literature to deal with the parameter uncertainty about expected
returns, including Bayesian approaches (e.g., Pástor, 2000; Wang, 2005; Pástor and
Stambaugh, 2009; Tu and Zhou, 2010; Bauder et al., 2020) and some other non-Bayesian
strategies (e.g., Goldfarb and Iyengar, 2003; Garlappi, Uppal, and Wang, 2007; Brandt,
Santa-Clara, and Valkanov, 2009; Branger, Lucivjanská, and Weissensteiner, 2019).
Moreover, hundreds of signals have been proposed to predict expected returns (see Hou,
Xue, and Zhang, 2015; Harvey, Liu, and Zhu, 2016; Green, Hand, and Zhang, 2017; and
the references therein). Given that the two strands of literature have attracted a large
amount of attention, we consider both exercises. Specifically, to construct the MVE port-
folios, we use the signal return-on-equity (ROE) as a proxy for the expected return, which
has been proven to have statistically significant explanatory power for cross-sectional
anomalies (Feng, Giglio, and Xiu, 2020). For robustness check, we consider the widely
used signal earnings-to-price (E/P) as an alternative proxy. We also consider different setups
for transaction costs.
    Our work is most closely related to the literature that attempts to provide a unified ana-
lysis framework for imposing constraints on weights and using advanced estimators for the
covariance matrix. Jagannathan and Ma (2003) find with the no-short-sale constraint in
place, GMV portfolios constructed based on the sample covariance matrix perform as well
as those constructed using the linear shrinkage estimator. However, if a shrinkage estimator
of the covariance matrix is used, the no-short-sale constraint would then hurt the out-of-
sample performance. They explain the similar performances and the “either-or” dichotomy
by the analogous mechanisms of constraining weights and shrinking covariances.
    DeMiguel et al. (2009a) and Brodie et al. (2009) use the ‘2 -norm or ‘1 -norm framework
to unify the shrinkage effects in weights and in covariance matrix. The ‘2 -norm constrained
portfolios, related to ridge regression which shrinks all regression coefficients toward zero
and does not produce any sparsity, correspond to the shrinkage estimators in Ledoit and
Wolf (2004b). The ‘1 -norm constrained portfolios, related to LASSO regression which
tends to give sparse weights, are equivalent to the short-sale-constrained portfolios in
Jagannathan and Ma (2003). Yen (2016) imposes both ‘1 -norm and ‘2 -norm penalties to
study portfolio optimization.
    Equivalent unconstrained regression representation for portfolio optimization has also
been investigated. Britten-Jones (1999) discusses the portfolio selection problem through an
artificial linear regression. On this basis, Fan, Zhang, and Yu (2012) and Li (2015) show
that constraining portfolio norms amounts to constraining estimation risks. In addition,
Ao, Li, and Zheng (2019) proposes a strategy MAXSER building upon a novel uncon-
strained regression representation and can simultaneously achieve mean–variance efficiency
and risk control. Furthermore, Callot et al. (2020) study the variance, weights, and risk of
large portfolios by using nodewise regression to directly estimate the inverse covariance
matrix.
Zhao et al. j Risk Reduction and Efficiency Increase                                       77


    Note that shrinkage estimators of the covariance matrix whose performances in portfolio




                                                                                                 Downloaded from https://academic.oup.com/jfec/article/21/1/73/6151211 by University Library Zurich / Zentralbibliothek Zurich user on 23 May 2023
selection have been compared with those constraining on portfolio weights are all linear, with
the shrinkage target being the Sharpe (1963)’s single index covariance matrix proposed by
Ledoit and Wolf (2003) (Jagannathan and Ma, 2003; DeMiguel et al., 2009a; Li, 2015), an
identity matrix proposed by Ledoit and Wolf (2004b) (DeMiguel et al., 2009a), or a
constant-correlation model proposed by Ledoit and Wolf (2004a) (Li, 2015). The estimation
is essentially equivalent to linearly shrinking the sample eigenvalues toward a more central-
ized set of eigenvalues by a unified shrinkage intensity. Ledoit and Wolf (2012, 2015) extend
the linear shrinkage of the sample eigenvalues to the NL transformation, and obtain the NL
estimator of the covariance matrix, which has been proven to have better out-of-sample per-
formance (Ledoit and Wolf, 2015, 2017a). Ledoit and Wolf (2020b) summarize that the lin-
ear shrinkage is simpler to understand and to implement, but the NL shrinkage is more
flexible and powerful. As the shrinkage mechanism is improved from a procedure with an ex-
ogenous target and a unified intensity to an endogenous optimization algorithm, it is import-
ant to compare its effect with that of imposing varying degrees of gross-exposure constraint.
    Further, Bollerslev, Patton, and Quaedvlieg (2018) argue that the shrinkage intensity
should be time-varying to consider the dynamic variation of the covariances. Consistent
with this idea, Engle, Ledoit, and Wolf (2019) propose the DCC-NL estimator of the co-
variance matrix, which uses the NL shrinkage estimator to replace the sample covariance
matrix in the “correlation targeting” maximum-likelihood estimation of the DCC model.
The DCC-NL estimator of the covariance matrix turns out to perform better than previous
estimators based on the conventional DCC model. Since the DCC model works in captur-
ing the conditional heteroscedasticity, we conjecture that the use of DCC model would also
help improve the out-of-sample performance of portfolios with gross-exposure constraints.
    The key differences between our work and the previous literature are embodied in the
following two aspects. First, we adopt the most advanced estimator for covariance matrix,
which not only applies the NL shrinkage procedure to account for the individual shrinkage
intensity, but also considers the dynamic variation of the covariances using the GARCH
model. Second, we focus on the improvement of DCC-NL over DCC when some certain
gross-exposure constraints are imposed. On this basis, we obtain new findings that the
DCC-NL estimator is always preferred and using the NL shrinkage estimator is superior to
imposing a gross-exposure constraint. Compared with imposing a gross-exposure con-
straint, using the NL shrinkage estimator has a larger degree of freedom, which gives
enough room for the benefits of the automatic optimization procedure.
    The rest of the paper is organized as follows. Section 1 provides the methodologies,
including the NL shrinkage estimator of the covariance matrix, its combination with the
DCC model, and our theoretical findings in constructing constrained GMV and MVE port-
folios. In Section 2, we use Monte Carlo simulations to verify our theoretical results. In
Section 3, we describe our data, report the results for out-of-sample performance of the
GMV and the MVE portfolios, and conduct robustness checks. Section 4 concludes.


1 Methodology
1.1 Shrinkage and DCC
It is widely known that the sample covariance matrix performs poorly out-of-sample in
large dimensions due to overfitting. Without imposing any additional structure on the data,
78                                                                         Journal of Financial Econometrics


shrinkage methods improve the estimation precision by rectifying the bias of the sample




                                                                                                               Downloaded from https://academic.oup.com/jfec/article/21/1/73/6151211 by University Library Zurich / Zentralbibliothek Zurich user on 23 May 2023
eigenvalues. The basic idea behind shrinkage methods is to pull the extreme sample eigen-
values toward the grand mean of all sample eigenvalues, since the smallest sample eigenval-
ues are biased downward and the largest ones upward. Ledoit and Wolf (2003, 2004a,
2004b) propose the linear shrinkage estimators, which are the first-order approximation
solutions to a NL optimization problem, as all sample eigenvalues adjust with the same
shrinkage intensity. The NL shrinkage estimators proposed by Ledoit and Wolf (2012,
2015) allow the sample eigenvalues to adjust with heterogeneous shrinkage intensities and
should generally perform better than the linear ones.
   To determine the optimal shrinkage intensity for every sample eigenvalue (in regard to a
particular loss function), Ledoit and Wolf (2015) discretize the famous Marcenko and
Pastur (1967) equation and construct the Quantized Eigenvalues Sampling Transform
(QuEST) function. By numerically inverting the QuEST function,2 the consistent estimators
for the population eigenvalues can be obtained. Specifically, let ðk1 ; . . . ; kN Þ denote a set of
eigenvalues of the N  N sample covariance matrix S, sorted in descending order, and
                                                                                                   0
ðu1 ; . . . ; uN Þ be the corresponding eigenvectors. Let QT;N ðtÞ :¼ ðq1T;N ðtÞ; . . . ; qN
                                                                                           T;N ðtÞÞ de-
note the QuEST function, which turns the set of population eigenvalues t :¼ ðt1 ; . . . ; tN Þ
into the set of sample eigenvalues. Thus, given the set of sample eigenvalues, the population
eigenvalues can be consistently estimated by inverting the QuEST function:
                                                 N                2
                                              1X
                              bs :¼ argmin           qiT;N ðtÞ  ki :                                  (1.1)
                                    t2½0;þ1ÞN
                                              N i¼1


     Then, the NL shrinkage estimator (denoted by NL) of the covariance matrix is

                                               X
                                               N
                                        ^ :¼
                                        R            kbi ðbsÞ  ui u0i :                               (1.2)
                                               i¼1

where kbi ðbsÞ for i ¼ 1; . . . ; N denote the shrunk eigenvalues based on bs. The basic idea of
this shrinkage formula is that

                                           kbi ðbsÞ  u0i Rui ;                                        (1.3)

where R represents the unconditional population covariance matrix. The approximation is
valid asymptotically as matrix dimension and sample size go to infinity together in the man-
ner detailed by Ledoit and Wolf (2015). Equations (1.2) and (1.3) are very similar to ki ¼
                    P
u0i Rui and S ¼ N                  0
                      i¼1 ki  ui ui : all we have done is replace the in-sample variance of a port-
folio whose weights are determined by eigenvector ui with the true variance of the same
portfolio. This is a substantial improvement because the fact that the eigenvectors
ðui Þi¼1;...;N are extracted from the same dataset as the eigenvalues ðki Þi¼1;...;N generates tre-
mendous over-fitting bias.
     In addition, to capture the volatility-clustering feature of asset returns, Engle (2002)
uses the DCC model to describe the time-varying structure in variances and covariances.
Let Rt :¼ ðrijt Þ denote the conditional covariance matrix of asset returns rt :¼ ðrit Þ (N-di-
                                                                                                1=2    1=2
mensional column vector) at time t, where t ¼ 1; . . . ; T. Let Dt :¼ diagðr11t . . . rNNt Þ


2 See Ledoit and Wolf (2017b) for the detailed implementation.
Zhao et al. j Risk Reduction and Efficiency Increase                                            79


denote the volatility matrix, Qt :¼ ðqijt Þ the pseudo-correlation matrix, and Pt :¼ ðqijt Þ the




                                                                                                      Downloaded from https://academic.oup.com/jfec/article/21/1/73/6151211 by University Library Zurich / Zentralbibliothek Zurich user on 23 May 2023
correlation matrix, satisfying
                                      1=2        1=2               1=2         1=2
                      Pt :¼ diagðq11t . . . qNNt ÞQt diagðq11t . . . qNNt Þ:                 (1.4)

   The DCC model is defined as

                                              Rt ¼ Dt Pt Dt :                                (1.5)

   A GARCH(1,1) model is used to describe the dynamic of every univariate volatility:

                          r2ii;t ¼ r2ii;0 ð1  ai  bi Þ þ ai r2i;t1 þ bi r2ii;t1 ;        (1.6)

and the pseudo-correlation matrix Qt is specified as

                           Qt ¼ Qð1  a  bÞ þ ast1 s0t1 þ bQt1 ;                         (1.7)

where ai, bi, a, and b are non-negative scalars satisfying ai þ bi < 1 for every i 2
f1; 2; . . . ; Ng and a þ b < 1. rii;0 is the long-run volatility of asset return for individual i,
st ¼ D1 t rt is the devolatilized return at time t, and Q is the long-run covariance matrix of st.
    By combining the NL shrinkage estimator of Q with the DCC model, Engle, Ledoit,
and Wolf (2019) propose the DCC-NL estimator of the covariance matrix. To avoid invert-
ing matrices with large dimensions, they also use the 2MSCLE method (Pakel et al., 2020)
in estimating the DCC model, which is the composite likelihood estimation bonding the in-
dividual likelihoods generated by 2  2 blocks of all contiguous pairs.
    To sum up, NL aims to improve the estimation precision of covariance matrix by
shrinking eigenvalues and thus reducing estimation errors. Meanwhile, DCC takes the con-
ditional heteroscedasticity into consideration by dynamic modeling. In view of these
strengths, the DCC-NL estimator is supposed to have better out-of-sample performance
than the DCC estimator, the NL estimator, and the sample covariance matrix (denoted by
S), especially in large dimensions.
    Even though our paper uses (in part) the DCC-NL method of Engle, Ledoit, and Wolf
(2019), our paper differs from theirs because they focus on the unconstrained case, whereas
we explore the interaction of the DCC-NL (among others) with gross exposure constraints.
This is more practically relevant because many investors face leverage constraints. At the
start of the investigation, we cannot know a priori whether the benefits of DCC-NL
observed by Engle, Ledoit, and Wolf (2019) carry over to the constrained case because
applying a gross book exposure constraint may already induce a sufficient of (implicit)
shrinkage to nullify the benefits of explicitly shrinking via DCC-NL or another shrinkage
method. This is the question that we need to answer.

1.2 Constructing GMV Portfolios with Gross-Exposure Constraints
Based on the estimator R ^ t of the time-varying covariance matrix Rt, constructing GMV
portfolios with the gross-exposure constraint is equivalent to the following minimization
problem given by

                                                    ^ t wt
                                          minwt w0t R
                                                        XN
                                                                                             (1.8)
                              subject to w0t 1 ¼ 1 and     jwi;t j  c:
                                                              i¼1
80                                                               Journal of Financial Econometrics

                   P
   The constraint N   i¼1 jwi;t j  c could be expressed as jjwt jj1  c. Note that c  1, and




                                                                                                             Downloaded from https://academic.oup.com/jfec/article/21/1/73/6151211 by University Library Zurich / Zentralbibliothek Zurich user on 23 May 2023
the constraint becomes weaker with the increase of c. When c ¼ 1, the constraint is equiva-
lent to the extreme situation considered in Jagannathan and Ma (2003) that no short sales
are allowed. c ¼ 1:6 corresponds to fully invested portfolios of the 130/30 type, and c ¼ 2
to 150/50. When c ¼ 1, the gross-exposure is unconstrained.
   Define the Lagrangian as

                                         ^ t wt  lðw0 1  1Þ  kðc  jjwt jj Þ;
                      Lðwt ; l; kÞ ¼ w0t R                                                          (1.9)
                                                     t                       1

                                 3
and let gt be the subgradient vector of jjwt jj1 . Then, for wi;t 6¼ 0, the i-th element of gt is
unique, that is, gi;t ¼ signðwi;t Þ; for wi;t ¼ 0; gi;t could be any values in ½1; 1.
   Consequently, the Karush–Kuhn–Tucker (KKT) conditions for the above gross-
exposure-constrained optimization problem (1.8) are
                                    8
                                    >
                                    >  2R^ w  l1 þ kg ¼ 0;
                                    >
                                    < t t                  t

                                       kðc  jjwt jj1 Þ ¼ 0; k  0;                       (1.10)
                                    >
                                    >
                                    >
                                    : jjw jj  c; w 1  1 ¼ 0;
                                                         0
                                          t 1            t


where 1 is the column vector of ones, and k and l are Lagrange multipliers. Denote a solu-
tion to Equation (1.10) by wt . The following result shows that constructing the gross-
exposure-constrained minimum variance portfolio from the DCC estimator is equivalent to
constructing a (unconstrained) minimum variance portfolio from a shrunk version of the
DCC estimator.

Theorem 1.


                                     
 i. Let R        ^ t þ 1 k g 10 þ 1g 0 , where g is the subgradient at w , and k is the
         ~ c;t ¼ R
                       2    t       t            t                           t
    Lagrange multiplier defined inEquation (1.10). Then, R                              ^ t is a
                                                          ~ c;t is positive definite if R
    positive definite DCC covariance matrix estimator.
ii. The partial constrained portfolio optimization problem (1.8) is equivalent to the opti-
    mization problem
                                                 ~ c;t wt
                                          min w0 R                                      (1.11)
                                                      t
                                            w0t 1¼1
                                           ~
     with the regularized covariance matrix ;t .
    It is noteworthy that the optimization problem (1.8) is solved by using the quadratic
programming algorithm (Tibshirani, 1996). Even though we do not compute the theoretical
regularized matrix R   ~ c;t in empirical analysis, the equivalence established in Theorem 1
could explain the relation between the two kinds of optimization problems. The Lagrange
multiplier k could be viewed as the parameter that controls the amount of shrinkage, which
illustrates the relation between R ~ c;t and the well-known shrinkage estimator of covariance
matrix.

3 We say that a vector g is a subgradient of f : Rn ! R at w0 2 dom f if for all w 2 dom f , f ðwÞ 
  f ðw0 Þ þ g> ðw  w0 Þ: If f is convex and differentiable, then its gradient at w0 is a subgradient. But
  a subgradient can exist even when f is not differentiable at w0 . A vector g is a subgradient of f at
  w0 if the affine function (of w) f ðw0 Þ þ g> ðw  w0 Þ is a global underestimator of f (Boyd, Boyd,
  and Vandenberghe, 2004).
Zhao et al. j Risk Reduction and Efficiency Increase                                          81


    It can easily be seen that the approach of imposing constraints on gross-exposure has




                                                                                                    Downloaded from https://academic.oup.com/jfec/article/21/1/73/6151211 by University Library Zurich / Zentralbibliothek Zurich user on 23 May 2023
only one degree of freedom: the Lagrange multiplier k (or, equivalently, the gross exposure
constraint c, as these two are in one-to-one correspondance, holding everything else equal).
It is not obvious how to choose this parameter optimally if the goal is to maximize covari-
ance matrix accuracy, but we will leave this issue aside for a moment. In contrast, the NL
shrinkage has N degrees of freedom kb1 ðbsÞ; . . . ; kc  sÞ, each one chosen optimally through an
                                                      N ðb
automatic procedure under large-dimensional asymptotics. This ability to “locally fine-
tune” is a huge advantage when population eigenvalues can be dispersed, clustered, or
otherwise unruly, which is the general case.
    This analysis provides a mathematical justification why the NL and DCC-NL can im-
prove gross-exposure-constrained strategies in spite of the well-known tendency for gross
exposure constraints to apply some shrinkage implicitly. Thus, the purpose of the empirical
analysis in Section 3.2.1 will be to verify that the usefulness of NL and DCC-NL—already
established in the unconstrained case by Ledoit and Wolf (2015) and Engle, Ledoit, and
Wolf (2019), respectively—carries over to the more realistic case of exposure-constrained
portfolios.

1.3 Constructing MVE Portfolios with Gross-Exposure Constraints
Given the estimator of the covariance matrix R^ t and the gross-exposure parameter c, the
MVE portfolio based on a return predictive signal mt :¼ ðm1t ; . . . ; mNt Þ0 is formulated as

                                                  ^ t wt
                                          min w0t R                                       (1.12)
                                           wt




                                     subject to w0t 1 ¼ 1 ;                               (1.13)



                                         w0t mt ¼ bt and                                  (1.14)



                                          X
                                          N
                                                jwi;t j  c;                              (1.15)
                                          i¼1

where bt is a selected target exposure to the signal mt . In our empirical study, bt is deter-
mined by the sorting portfolios. In particular,

                                         bt ¼ wQ0t mt ;                                   (1.16)

where wQt is the weight vector of quantile-based portfolios. Let fð1Þ; ð2Þ; . . . ; ðNÞg be the
permutation of f1; 2; . . . ; Ng that results in descending order of scores for the signal mt .
           ð1Þ              ðdÞ                 ðdþ1Þ             ðNÞ
Then, wQt ¼    ¼ wQt :¼ 1=d and wQt                ¼    ¼ wQt :¼ 0, where d is the largest
integer that is smaller than or equal to the ratio of portfolio size N to the number of quan-
tiles B. We consider quintiles (B ¼ 5) in our empirical analysis.
    Denote the solution to problem (1.12) as wb;t , then we could obtain the following the-
orem similar to Theorem 1.
82                                                         Journal of Financial Econometrics


Theorem 2. The partial constrained portfolio optimization problem (1.12) is equivalent




                                                                                                   Downloaded from https://academic.oup.com/jfec/article/21/1/73/6151211 by University Library Zurich / Zentralbibliothek Zurich user on 23 May 2023
to the optimization problem


                                                  ~ c;t wt
                                        minwt w0t R
                                                                                         (1.17)
                             subject to w0t 1 ¼ 1 and w0t mt ¼ bt :

                                                                                      
with the regularized covariance matrix R  ~ c;t . Here, R       ^ t þ 1 k g 10 þ 1g 0 ; g is the
                                                        ~ c;t ¼ R
                                                                      2    b;t     b;t   b;t
subgradient at wb;t , and k is the Lagrange multiplier.

   As in the GMV case of Section 1.2, we can see that the shrinkage implicit in gross-book-
exposure constraints has only one degree of freedom, so NL shrinkage enjoys a theoretical
advantage with its N degrees of freedom. This is even more so for DCC-NL, since it over-
lays a time-varying component that is missing in gross-book-exposure constraints. This pro-
vides theoretical justification for the empirical analysis of Section 3.2.2 that examines
whether the results of Ledoit and Wolf (2015) and Engle, Ledoit, and Wolf (2019), for NL
and DCC-NL, respectively, carry over from the unconstrained MVE portfolio to the
exposure-constrained MVE portfolio.


2 Monte Carlo Simulations
In the last section, we demonstrate that imposing the gross-exposure constraint on a port-
folio is equivalent to using the shrinkage estimator when the time-varying structure of the
covariance matrix is captured by the DCC model. In this section, we use Monte Carlo simu-
lations to quantify the finite sample performance of portfolios constructed using different
covariance matrix estimators and with varying levels of gross-exposure constraint. In par-
ticular, we want to study and compare the usefulness of the NL shrinkage estimation, the
DCC model, and the gross-exposure constraint in portfolio improvement and address the
following questions, among others. Is it better to use the NL shrinkage covariance matrix
estimator or the optimal gross-exposure constraint? Is it better to use a dynamic model
(with DCC) or a static model (without DCC)? Does the NL shrinkage improve over a pure
portfolio with a moderate gross-exposure constraint (for both the dynamic model and the
static model)? Last but not least, how do the NL shrinkage, the DCC model, and the gross-
exposure constraint affect the risk approximations?

2.1 Data Generating Process
To generate realistic simulations that match the empirical data, we first estimate the uncon-
ditional covariance matrix from the most liquid stocks (N ¼ 500, 1000) in the CRSP data-
base based on the NL shrinkage method using 5 years of daily data from 2010 to 2014.
This matrix will be regarded as the true unconditional covariance matrix.
                                                      1=2
    Second, we simulate the DCC time series rt ¼ Rt zt with disturbance terms zt drawn
from a multivariate standard normal distribution or a multivariate “Student” t-distribution
with five degrees of freedom. The conditional covariance matrix Rt is generated from
Equation (1.5) to Equation (1.7), with parameters ai ¼ 0:05 and bi ¼ 0:90 for all individual
stocks i ¼ 1; . . . ; N in Equation (1.6) and parameters a ¼ 0:05 and b ¼ 0:93 in Equation
(1.7). For each simulation, we thereby generate a T  N  N time-varying covariance ma-
trix and correspondingly a T  N matrix of simulated returns, where the time length T is
Zhao et al. j Risk Reduction and Efficiency Increase                                                 83


1250 and the portfolio size N is either 500 or 1000. We repeat each simulation for 100




                                                                                                           Downloaded from https://academic.oup.com/jfec/article/21/1/73/6151211 by University Library Zurich / Zentralbibliothek Zurich user on 23 May 2023
times.

2.2 Portfolio Improvement
We construct GMV portfolios [Equation (1.8)] based on four different covariance matrix
estimators, including the sample covariance matrix (S), the NL shrinkage estimator (NL)
proposed by Ledoit and Wolf (2015), the covariance matrix estimator based on DCC model
(Engle, 2002), and the DCC-NL estimator proposed by Engle, Ledoit, and Wolf (2019).
For each covariance matrix estimator, we allow a wide choice of the gross-exposure param-
eter c, ranging from 1 to 16, and we also entertain the situation where no constraint on
gross-exposure is imposed (c ¼ 1).
    In Table 1, we report the annualized actual risks of the empirical portfolio obtained by
Equation (2.1), the standard errors of weights and the total short positions of the empirical
portfolios constructed based on the four covariance matrix estimators, either without any
constraint on gross-exposure or with the optimal constraint on gross-exposure
(þconstraint*). All the results shown are for a typical simulated dataset, which has the me-
dian oracle risk among 100 simulations.
    We can see that purely using a NL shrinkage estimator of covariance matrix uniformly
dominates purely imposing an optimal constraint on gross-exposure, and using the DCC
model helps improve the performance in all cases. For example, when N ¼ 1000 and the
disturbance terms zt are generated from a multivariate standard normal distribution, impos-
ing gross-exposure constraint reduces the annualized actual risk of the empirical portfolio
from 6.63% to 4.11% at best, whereas using the NL covariance matrix estimator reduces
the risk to 3.92%, and DCC-NL reduces the risk to 3.69%. We also find that additionally
imposing an optimal constraint on the gross-exposure has no effect on the NL portfolio,
but it improves the performance of a pure DCC-NL portfolio.

Remark 3.1 (Determinants of the optimal constraint). The optimal constraint (with gross-
exposure parameter c ), which minimizes actual risk among portfolios with different
degrees of gross-exposure constraint, is unknown in practice. According to Equation (2.1),
the optimal constraint parameter c is determined by both the real covariance matrix Rt
and the estimated weights vector w   b t . Suppose the estimated weights vector is close to the
oracle one when the gross-exposure parameter c is around the oracle optimal parameter
                                                                        P
c orc . Then, c should be close to the oracle optimal parameter c orc ¼ N  i¼1 jwi;t j, where wi;t
                                                                        R1 1
denotes the i-th element of the optimal weights vector wt ¼ 10 Rt 1 1. Let R1        
                                                                               t ¼ ðrij;t Þ1  i;j  N ,
                                                                      t
                                               PN PN 
                PN PN                              j    r j
then 10 R1
         t 1¼      i¼1 j¼1 rij;t , and c
                                         orc
                                             ¼ Pi¼1
                                                 N PN
                                                      j¼1 ij;t
                                                          
                                                               . Given the positive definiteness of
                                                    i¼1   j¼1
                                                                rij;t
                                     P PN 
the inverse covariance matrix, N       i¼1   j¼1 rij;t is positive. Therefore, if many of the row
      PN 
sums j¼1 rij;t ði ¼ 1; . . . ; NÞ are negatively large, then both c orc and c will be large. For a
special case, if none of the row sums is negative, then c orc ¼ 1 and c will be close to 1.          h

    For a more comprehensive comparison, we present the annualized actual risks for the
four covariance matrix estimators with a continuously changing gross-exposure constraint
parameter c in Figures 1 and 2, for simulated data with zt Nð0; 1Þ and zt tð5Þ, respect-
ively. It is clear from the figures that using the DCC-NL covariance matrix achieves the
84                                                                   Journal of Financial Econometrics


Table 1 Actual risk of portfolio and standard deviation and total short position of weights




                                                                                                                  Downloaded from https://academic.oup.com/jfec/article/21/1/73/6151211 by University Library Zurich / Zentralbibliothek Zurich user on 23 May 2023
                              zt   Nð0; 1Þ                              zt    tð5Þ

                              C        Ract      StdW      ShortW       c         Ract     StdW       ShortW

Panel A: 500 stocks contained in the portfolio
S                          1         5.53      2.35         403.15      1         5.54      2.36       407.13
S þ constraint*             5.5      5.10      1.72         225.00      6.0       5.14      1.80       250.00
NL                         1         5.01      1.58         258.62      1         5.01      1.59       265.09
NL þ constraint*            5.9      5.01      1.53         245.00      5.9       5.01      1.54       245.00
DCC                        1         5.11      2.33         397.52      1         5.07      2.33       396.53
DCC þ constraint*           4.6      4.45      1.57         180.00      4.5       4.40      1.56       175.00
DCC-NL                     1         4.40      1.68         270.62      1         4.37      1.70       275.47
DCC-NL þ constraint*        4.9      4.32      1.48         195.00      4.8       4.27      1.48       190.00

Panel B: 1000 stocks contained in the portfolio
S                           1        6.63      1.92         701.15      1         6.48      1.91       698.72
S þ constraint*             5.0      4.11      0.87         200.00      5.1       4.04      0.88       205.00
NL                          1        3.92      0.74         245.30      1         3.84      0.75       250.86
NL þ constraint*            5.9      3.92      0.74         244.44      5.6       3.84      0.73       229.99
DCC                         1        6.43      1.84         665.61      1         6.24      1.85       673.41
DCC þ constraint*           4.4      3.91      0.82         169.98      4.4       3.84      0.82       169.98
DCC-NL                      1        3.69      0.79         252.52      1         3.65      0.80       256.07
DCC-NL þ constraint*        5.2      3.66      0.74         209.97      5.2       3.61      0.75       209.97

Notes: This table shows the simulation results for the empirical GMV portfolios constructed based on different
covariance matrix estimators, facing no gross-exposure constraint or with an optimal gross-exposure con-
straint (þconstraint*). All the results presented are the median values among 100 simulations. Panels A and B
show results for portfolios with 500 and 1000 stocks, respectively. The left panel and the right panel show
results for simulated data, where the disturbance terms are drawn from a multivariate standard normal distri-
bution and a multivariate t-distribution with five degrees of freedom, respectively. The covariance matrix is
estimated using the most recent 1250 daily returns based on four different methods, which are the sample co-
variance matrix (S), the NL shrinkage estimator (NL) (Ledoit and Wolf, 2015), the DCC estimator (Engle,
2002), and the DCC-NL estimator (Engle, Ledoit, and Wolf, 2019). The sum of the absolute weights should
not exceed the gross-exposure parameter c. c ¼ 1 means there is no constraint on the gross-exposure of the
portfolio, and the optimal c corresponds to the gross-exposure constraint where the portfolio has the minimum
annualized actual risk (Ract). The standard deviation of weights (StdW) and the total short position of weights
(ShortW) of the empirical portfolios are also reported. All the figures shown are in percentage.



minimum actual risks in all cases with different gross-exposure constraints. The gains from
NL shrinkage increase as the constraint c becomes less binding and the portfolio size N
becomes larger. The former is explained by Jagannathan and Ma (2003) that imposing con-
straints on portfolio weights has a shrinkage-like effect, and thus it hurts the performance
of the shrinkage estimator of covariance matrix. The latter is consistent with the finding of
Ledoit and Wolf (2017a) that the amount of improvement is more pronounced in large
dimensions. By contrast, the gains from DCC decrease as the constraint c becomes less
binding and the portfolio size N becomes larger. This is because without an effective con-
straint, the large errors generated in estimating the model impair the performance of DCC,
and the large portfolio size exacerbates the problem.
Zhao et al. j Risk Reduction and Efficiency Increase                                                                                 85


                                           N=500                                                              N=1000
                       11                                                                  11




                                                                                                                                          Downloaded from https://academic.oup.com/jfec/article/21/1/73/6151211 by University Library Zurich / Zentralbibliothek Zurich user on 23 May 2023
                                                        S                                                                   S
                       10                               NL                                 10                               NL
                                                        DCC                                                                 DCC
                                                        DCC-NL                                                              DCC-NL
                       9                                                                   9
 Annualized Risk (%)




                                                                     Annualized Risk (%)
                       8                                                                   8


                       7                                                                   7


                       6                                                                   6


                       5                                                                   5


                       4                                                                   4


                       3                                                                   3
                            1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16                              1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16
                                   Exposure Constraint ( )                                             Exposure Constraint ( )

Figure 1 Comparisons of the median annualized actual risks of the 100 simulated GMV portfolios con-
structed based on different covariance matrix estimators (S, NL, DCC, DCC-NL) and facing various
degrees of gross-exposure constraints (the intensity of the constraint declines with the increase of par-
ameter c). The disturbance terms of the simulated data are drawn from a multivariate standard normal
distribution.


                                           N=500                                                              N=1000
                       11                                                                  11
                                                        S                                                                   S
                       10                               NL                                 10                               NL
                                                        DCC                                                                 DCC
                                                        DCC-NL                                                              DCC-NL
                       9                                                                    9
 Annualized Risk (%)




                                                                     Annualized Risk (%)




                       8                                                                    8


                       7                                                                    7


                       6                                                                    6


                       5                                                                    5


                       4                                                                    4


                       3                                                                    3
                            1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16                              1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16
                                   Exposure Constraint ( )                                             Exposure Constraint ( )

Figure 2 Comparisons of the median annualized actual risks of the 100 simulated GMV portfolios con-
structed based on different covariance matrix estimators (S, NL, DCC, DCC-NL) and facing various
degrees of gross-exposure constraints (the intensity of the constraint declines with the increase of par-
ameter c). The disturbance terms of the simulated data are drawn from a multivariate t-distribution
with five degrees of freedom.
86                                                           Journal of Financial Econometrics


Remark 3.2 (The performance of DCC when T < N). Due to completeness, we also con-




                                                                                                      Downloaded from https://academic.oup.com/jfec/article/21/1/73/6151211 by University Library Zurich / Zentralbibliothek Zurich user on 23 May 2023
sidered the special case when the number of observations (T) is smaller than the number of
stocks (N). It is well-known that when T < N, the sample covariance matrix is not of full
rank, so its inverse will not exist. As the traditional DCC estimator relies on the sample co-
variance matrix, its inverse will not exist either. In this case, the advantage of using NL
shrinkage estimators is self-evident. To evaluate the performance of DCC, we compare the
results of NL and DCC-NL. The data generating process is the same as described in Section
2.1 except that we set T ¼ 500 and N ¼ 1000. In unreported results, we find that the benefit
of using DCC model is weakened by the large ratio of N/T. In particular, when the gross-
exposure is tight (c is small), DCC-NL still delivers smaller actual risks, but NL performs
better if no effective gross-exposure constraint is imposed. This finding indicates that in the
estimation of the DCC model the large-dimensional small sample size problem (N=T ¼ 2)
causes large approximation errors, which can be reduced by imposing tight gross-exposure
constraints. In this special case, it is advisable to use the pure NL method if no external
gross-exposure constraint is imposed, but DCC-NL is still preferred if a common external
gross-exposure (such as the “130/30” or the “150/50” requirement) is imposed.                h

    We also show the 10th, 50th, and 90th percentiles of Ract among the 100 simulations in
Figure 3 for N ¼ 500 and in Figure 4 for N ¼ 1000, both for simulated data with
zt Nð0; 1Þ.4 We can see that the sampling variation is always small. Moreover, the three
percentiles of Ract for DCC-NL estimator are more closer than those of the other three esti-
mators, indicating that the performance of DCC-NL estimator is more stable in portfolio
selection.
    The numbers in the columns StdW and ShortW of Table 1 indicate that both the shrink-
age estimator and the gross-exposure constraint largely reduce the standard deviations of
weights and the total short positions. By comparison, the shrinkage estimator reduces the
standard deviations of weights more remarkably and the gross-exposure constraint has a
more distinct effect on reducing the total short positions.
    To sum up, for varying gross-exposure constraints, it is always the DCC-NL estimator
that yields the lowest risks. Imposing moderate constraints on gross-exposure effectively
reduces the risks but is uniformly dominated by using the DCC-NL covariance matrix
estimator.

2.3 Risk Approximations
Following Fan, Zhang, and Yu (2012), besides Ract, we also computer the oracle risk
(denoted by Rorc) of the theoretical optimal portfolio and the empirical risk (denoted by
Remp) based on the estimated weights and estimated covariance matrix to analyze the risk
approximations. In particular, the three annualized risks are defined as follows:
                                          pﬃﬃﬃﬃﬃﬃﬃﬃ 0
                                   Ract ¼ 252 w    b t Rt w
                                                          b t:                       (2.1)




4 Since the results for simulated data with zt t ð5Þ are very similar with those for simulated data
  with zt Nð0; 1Þ, we do not report the details here for simplicity.
Zhao et al. j Risk Reduction and Efficiency Increase                                                                              87


                                            S                                                                  DCC




                                                                                                                                        Downloaded from https://academic.oup.com/jfec/article/21/1/73/6151211 by University Library Zurich / Zentralbibliothek Zurich user on 23 May 2023
                       10                                                                  10
                       9.5                              10%
                                                                                           9.5                              10%
                         9                                                                   9
 Annualized Risk (%)




                                                                     Annualized Risk (%)
                       8.5                              50%                                8.5                              50%
                         8                              90%                                  8                              90%
                       7.5                                                                 7.5
                         7                                                                   7
                       6.5                                                                 6.5
                         6                                                                   6
                       5.5                                                                 5.5
                         5                                                                   5
                       4.5                                                                 4.5
                         4                                                                   4
                       3.5                                                                 3.5
                         3                                                                   3
                             1 2 3 4 5 6 7 8 9 10111213141516                                    1 2 3 4 5 6 7 8 9 10111213141516
                                  Exposure Constraint ( )                                             Exposure Constraint ( )
                                           NL                                                                DCC-NL
                       10                                                                  10
                       9.5                              10%
                                                                                           9.5                              10%
                         9                                                                   9
 Annualized Risk (%)




                       8.5                              50%          Annualized Risk (%)   8.5                              50%
                         8                              90%                                  8                              90%
                       7.5                                                                 7.5
                         7                                                                   7
                       6.5                                                                 6.5
                         6                                                                   6
                       5.5                                                                 5.5
                         5                                                                   5
                       4.5                                                                 4.5
                         4                                                                   4
                       3.5                                                                 3.5
                         3                                                                   3
                             1 2 3 4 5 6 7 8 9 10111213141516                                    1 2 3 4 5 6 7 8 9 10111213141516
                                  Exposure Constraint ( )                                             Exposure Constraint ( )

Figure 3 Comparisons of the 10%, 50%, and 90% quantiles of the annualized actual risks of the 100
simulated GMV portfolios constructed. N ¼ 500, and the disturbance terms are drawn from a multivari-
ate standard normal distribution.


                                                               pﬃﬃﬃﬃﬃﬃﬃﬃ 0
                                                      Rorc ¼    252 wt Rt wt :                                                  (2.2)


                                                               pﬃﬃﬃﬃﬃﬃﬃﬃ 0
                                                     Remp ¼     252 w      ^ tw
                                                                        b tR  b t:                                              (2.3)

    Note that only the empirical risk is known, and the difference between Remp and Ract
reflects the estimation error in the covariance matrix.
    Figures 5 and 6 depict all three risks for N ¼ 500 and N ¼ 1000, respectively, both for
simulated data with zt Nð0; 1Þ. The curve of the oracle risk shared by the four graphs in
Figure 5 (or Figure 6) indicates that the theoretical risk decreases quickly with the increase
of the gross-exposure parameter c before c reaches 2, when the constraint forms the 150/50
strategy, which involves 150% long positions and 50% short positions. In fact, based on
the true covariance matrix, the GMV portfolios have c orc ¼ 5:758 for N ¼ 500 and c orc ¼
5:846 for N ¼ 1000, indicating oracle total short positions of 237.9% for N ¼ 500 and
242.3% for N ¼ 1000. When c > c orc , the oracle risk remains constant, and relaxing the
constraint reduces the empirical risk but increases the actual risk. The increase of the actual
risk is especially distinct when N ¼ 1000 and S or DCC covariance matrix estimator is
used.
88                                                                                                                 Journal of Financial Econometrics


                                                    S                                                                          DCC
                           10                                                                             10




                                                                                                                                                          Downloaded from https://academic.oup.com/jfec/article/21/1/73/6151211 by University Library Zurich / Zentralbibliothek Zurich user on 23 May 2023
                           9.5                                     10%
                                                                                                          9.5                                    10%
                             9                                                                              9
     Annualized Risk (%)




                                                                           Annualized Risk (%)
                           8.5                                     50%                                    8.5                                    50%
                             8                                     90%                                      8                                    90%
                           7.5                                                                            7.5
                             7                                                                              7
                           6.5                                                                            6.5
                             6                                                                              6
                           5.5                                                                            5.5
                             5                                                                              5
                           4.5                                                                            4.5
                             4                                                                              4
                           3.5                                                                            3.5
                             3                                                                              3
                                 1 2 3 4 5 6 7 8 9 10111213141516                                               1 2 3 4 5 6 7 8 9 10111213141516
                                       Exposure Constraint ( )                                                       Exposure Constraint ( )
                                                   NL                                                                        DCC-NL
                           10                                                                             10
                           9.5                                     10%
                                                                                                          9.5                                    10%
                             9                                                                              9
     Annualized Risk (%)




                                                                           Annualized Risk (%)
                           8.5                                     50%                                    8.5                                    50%
                             8                                     90%                                      8                                    90%
                           7.5                                                                            7.5
                             7                                                                              7
                           6.5                                                                            6.5
                             6                                                                              6
                           5.5                                                                            5.5
                             5                                                                              5
                           4.5                                                                            4.5
                             4                                                                              4
                           3.5                                                                            3.5
                             3                                                                              3
                                 1 2 3 4 5 6 7 8 9 10111213141516                                               1 2 3 4 5 6 7 8 9 10111213141516
                                       Exposure Constraint ( )                                                       Exposure Constraint ( )

Figure 4 This is similar to Figure 3 except N ¼ 1000.


                                                  S                                                                             DCC
                           10                                                                             10
     Annualized Risk (%)




                                                                                    Annualized Risk (%)




                                                          Actual Risk                                                                    Actual Risk
                                                          Oracle Risk                                                                    Oracle Risk
                                                          Empirical Risk                                                                 Empirical Risk

                            5                                                                              5




                            0                                                                              0
                                1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16                                         1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16
                                        Exposure Constraint ( )                                                        Exposure Constraint ( )
                                                 NL                                                                          DCC-NL
                           10                                                                             10
     Annualized Risk (%)




                                                                                    Annualized Risk (%)




                                                          Actual Risk                                                                    Actual Risk
                                                          Oracle Risk                                                                    Oracle Risk
                                                          Empirical Risk                                                                 Empirical Risk

                            5                                                                              5




                            0                                                                              0
                                1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16                                         1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16
                                        Exposure Constraint ( )                                                        Exposure Constraint ( )

Figure 5 Comparisons of the median annualized oracle risks, median annualized actual risks, and me-
dian annualized empirical risks of the 100 simulated GMV portfolios constructed based on different co-
variance matrix estimators (S, NL, DCC, DCC-NL) and facing various degrees of gross-exposure
constraints (the intensity of the constraint declines with the increase of parameter c). N ¼ 500, and the
disturbance terms are drawn from a multivariate standard normal distribution.
Zhao et al. j Risk Reduction and Efficiency Increase                                                                                               89


                                                S                                                                      DCC
                       10                                                                       10




                                                                                                                                                        Downloaded from https://academic.oup.com/jfec/article/21/1/73/6151211 by University Library Zurich / Zentralbibliothek Zurich user on 23 May 2023
 Annualized Risk (%)




                                                                          Annualized Risk (%)
                                        Actual Risk                                                              Actual Risk
                                        Oracle Risk                                                              Oracle Risk
                                        Empirical Risk                                                           Empirical Risk

                        5                                                                        5




                        0                                                                        0
                            1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16                                   1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16
                                    Exposure Constraint ( )                                                  Exposure Constraint ( )
                                             NL                                                                    DCC-NL
                       10                                                                       10
 Annualized Risk (%)




                                                                          Annualized Risk (%)
                                                         Actual Risk                                                              Actual Risk
                                                         Oracle Risk                                                              Oracle Risk
                                                         Empirical Risk                                                           Empirical Risk

                        5                                                                        5




                        0                                                                        0
                            1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16                                   1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16
                                    Exposure Constraint ( )                                                  Exposure Constraint ( )

Figure 6 This is similar to Figure 5 except N ¼ 1000.



    The three risks are high but nearly the same when c ¼ 1. With the increase of c, the dif-
ference between the actual risk and the empirical risk increases, suggesting that the estima-
tion of the covariance matrix becomes harder. If no-shrinkage-involved covariance matrix
estimator is used for constructing a large portfolio with N ¼ 1000, the curves of actual risks
start upward sloping when c > 4, making both the actual–empirical gap and the actual–or-
acle gap increase dramatically. The difference between the actual and the oracle risks shows
very similar properties to the actual–empirical gap, except that the former is much smaller
than the latter when DCC model is used, indicating the important role of DCC model in
estimating the optimal weights.
    Overall, the NL shrinkage reduces approximation errors of the covariance matrix and
improves the weights allocations when a relatively loose constraint is imposed, whereas the
DCC model improves portfolio allocations and thereby reduces the actual risks. By con-
trast, approximation errors reduce with the reinforcement of the gross-exposure constraint,
but a tight constraint impairs the portfolio performance as it results in too conservative
allocations.

2.4 Combining Shrinkage with Gross-Exposure Constraints
As a final lesson, there are circumstances where the gross-exposure constraint is externally
imposed: for example, by the regulatory authorities, by the financing conditions extended
by prime brokers, or by risk-management commitments advertized to fund investors in the
marketing materials at the initial asset-gathering stage. In such cases, Table 1 and Figures 1
and 2 show that there is still incremental benefit to using DCC-NL, even after the gross-
exposure constraint has already been imposed. Indeed, for every panel and every value of
the gross exposure constraint c:

1. the conditional covariance matrix (DCC) is better than the unconditional one (S);
90                                                            Journal of Financial Econometrics


2. the shrunk conditional covariance matrix (DCC-NL) is better than the plain one




                                                                                                        Downloaded from https://academic.oup.com/jfec/article/21/1/73/6151211 by University Library Zurich / Zentralbibliothek Zurich user on 23 May 2023
   (DCC).
   Here, we measure “better” as having lower standard deviation of the returns on the
GMV portfolio. Note, however, that the gains from shrinkage become monotonically
weaker as the gross exposure constraint c becomes more binding. This is because the gross-
exposure constraint applies a “brute-force” one-size-fits-all over-shrinkage that leaves little
room for the benefits of a locally adaptive optimal NL shrinkage formula to express
themselves.


3 Empirical Results
3.1 Data
We examine the effects of the gross-exposure constraint, the shrinkage estimation of covari-
ance matrix, and the use of DCC model to capture the heteroscedasticity on the out-of-
sample performance of the GMV portfolio and the MVE portfolio. We use the same
portfolio-construction rules as in Ledoit, Wolf, and Zhao (2019), except that we also im-
pose different levels of gross-exposure constraints on portfolio weights.
    Specifically, we focus on stocks traded on the NYSE, AMEX, and NASDAQ, with daily
return data for all the immediately preceding 1250 days as well as the upcoming 21 days,
and with correlations not exceeding 0.95.5 The daily return data we use, which cover the
period from January 1, 1980 to December 31, 2018, are from the Center for Research in
Security Prices (CRSP) database. The out-of-sample period is from January 8, 1986 to
December 31, 2018. We update the portfolios every 21 consecutive trading days, and thus
form 396 investment dates from January 8, 1986 to December 31, 2018. At every invest-
ment date h, the covariance matrix is estimated based on the most recent 1250 daily returns
(roughly equals 5 years).
    For both the GMV portfolio and the MVE portfolio, we consider two different portfolio
sizes N ¼ 500 and 1000. For a given combination (h, N), in the set of stocks that satisfy
the above conditions, we pick the largest N stocks (as measured by their market capitaliza-
tion on investment date h) as our investment universe.
    We also consider the four covariance matrix estimators: the sample covariance matrix
(S), the NL shrinkage estimator (NL) (Ledoit and Wolf, 2015), the covariance matrix esti-
mator based on DCC model (Engle, 2002), and the DCC-NL estimator (Engle, Ledoit, and
Wolf, 2019). To consider the effects of the gross-exposure constraint and the shrinkage co-
variance matrix estimator together, we establish portfolios with a varying gross-exposure
parameter c, based on each covariance matrix estimator for each portfolio type and port-
folio size.

3.2 Main Results
3.2.1 Results for GMV portfolios
Table 2 presents the out-of-sample performance measures of the GMV portfolios with a
varying gross-exposure parameter c ¼ 1, 2, 1.6, and 1 for each covariance matrix


5 The sample correlations are calculated based on the daily returns over the past 1250 days. We re-
  move the stock with the lower volume in a pair on the investment date if the correlation of the two
  exceeds 0.95.
Zhao et al. j Risk Reduction and Efficiency Increase                                                              91


Table 2 Out-of-sample performance, characteristics of weights, and average turnover of the




                                                                                                                         Downloaded from https://academic.oup.com/jfec/article/21/1/73/6151211 by University Library Zurich / Zentralbibliothek Zurich user on 23 May 2023
GMV portfolio

            ^
            R              AvR        StdR           IR        MinW        MaxW        StdW       ShortW       AvT

Panel A: 500 stocks contained in the portfolio
c¼1        S            10.23     10.78         0.95           6.23       10.27        1.73      255.14        6.50
           NL           10.63      9.75         1.09           2.85        4.90        1.00      140.21        2.35
           DCC          13.22     10.44         1.27           4.25       16.29        1.61      179.22        4.11
           DCC-NL       12.94      9.55***      1.35           2.24       14.86        1.27      109.56        2.04
c¼2        S            10.78      9.99         1.08           3.43        9.84        1.02       50.00        3.19
           NL           10.69      9.86         1.08           2.75        5.69        0.80       50.00        1.39
           DCC          12.22      9.82         1.24           2.72       17.97        1.30       49.97        2.88
           DCC-NL       12.38      9.52***      1.30           2.05       16.85        1.23       49.41        1.36
c ¼ 1:6    S            10.71     10.11         1.06           3.12       10.64        0.99       30.00        2.80
           NL           10.77     10.06         1.07           2.73        6.39        0.78       30.00        1.39
           DCC          12.02      9.78         1.23           2.42       19.29        1.32       30.00        2.76
           DCC-NL       12.24      9.59***      1.28           1.94       18.50        1.28       29.94        1.29
c¼1        S            10.67     11.34         0.94            0.00       12.99        1.02        0.00        2.36
           NL           10.97     11.34         0.97            0.00        8.20        0.80        0.00        0.36
           DCC          11.13     10.19         1.09            0.00       24.83        1.52        0.00        1.29
           DCC-NL       11.24     10.17         1.10            0.00       24.74        1.52        0.00        0.17
Panel B: 1000 stocks contained in the portfolio
c¼1        S            10.16     13.54         0.75           7.26        9.78        1.69      557.00       12.62
           NL           10.64      8.81         1.21           1.44        2.44        0.49      142.76        3.26
           DCC          10.28     10.51         0.98           4.44       19.60        1.36      335.99        7.42
           DCC-NL       11.26      8.16***      1.38           1.15       16.22        0.79       97.29        2.73
c¼2        S            10.78      9.27         1.16           2.39        8.41        0.62       50.00        3.56
           NL           10.67      9.13         1.17           1.64        3.30        0.41       50.00        1.69
           DCC          10.71      8.52         1.26           1.77       21.98        0.95       49.99        3.30
           DCC-NL       11.24      8.11***      1.39           1.13       18.71        0.83       49.60        1.66
c ¼ 1:6    S            10.95      9.37         1.17           2.07        9.15        0.62       30.00        2.96
           NL           10.92      9.41         1.16           1.76        3.80        0.42       30.00        1.65
           DCC          10.90      8.35         1.31           1.55       23.70        0.99       30.00        2.96
           DCC-NL       11.23      8.10***      1.39           1.09       21.15        0.90       29.98        1.48
c¼1        S            12.02     10.94         1.10            0.00       11.75        0.67        0.00        2.47
           NL           12.04     10.98         1.10            0.00        5.52        0.46        0.00        0.55
           DCC           9.96      8.62         1.16            0.00       31.73        1.24        0.00        1.42
           DCC-NL        9.66      8.53***      1.13            0.00       31.01        1.22        0.00        0.22

Notes: This table shows the out-of-sample results for the GMV portfolios constructed based on different covari-
ance matrix estimators and facing various degrees of gross-exposure constraints. The covariance matrix is esti-
mated using the most recent 1250 daily returns based on four different methods, which are the sample covariance
matrix (S), the NL shrinkage estimator (NL) (Ledoit and Wolf, 2015), the DCC estimator (Engle, 2002), and the
DCC-NL estimator (Engle, Ledoit, and Wolf, 2019). c is a gross-exposure parameter indicating the supremum of
the sum of the absolute weights. Therefore, c ¼ 1; 2; 1:6; 1 stands for an increasing restriction with the total short
position not exceeding 1; 50%; 30%; 0 of the total investment. We hold the portfolios for 21 days and record their
daily returns. We report their out-of-sample AvR, annualized standard deviations (StdR), and IRs. Four character-
istics of portfolio weights, including the minimum weight (MinW), the maximum weight (MaxW), the standard
deviation of weights (StdW), and the total short positions of weights (ShortW), and the average turnover (AvT) of
portfolios are also reported. All numbers shown are in percentage except those for IRs. Panel A and panel B show
results for portfolios with 500 and 1000 stocks, respectively. In the rows labeled DCC and DCC-NL, significant
outperformance of one of the two portfolios over the other in terms of StdR is denoted by asterisks: ***, **, and
* denote significance at the 0.01, 0.05, and 0.1 levels, respectively.
92                                                        Journal of Financial Econometrics


estimator. Specifically, we report the annualized average return (AvR), computed by the




                                                                                                 Downloaded from https://academic.oup.com/jfec/article/21/1/73/6151211 by University Library Zurich / Zentralbibliothek Zurich user on 23 May 2023
average out-of-sample returns multiply by 252, annualized standard deviations (StdR),
                                                                                    pﬃﬃﬃﬃﬃﬃﬃﬃ
computed by the standard deviation of the out-of-sample returns multiply by 252, and
Information Ratios (IRs), which is the ratio of AvR to StdR.
    On the one hand, DCC-NL performs the best among four covariance matrix estimators
considered in all cases with different gross-exposure constraints. Judging by the StdR of
GMV portfolios, the outperformance of DCC-NL is most remarkable when N ¼ 1000 and
no gross-exposure constraint is imposed: it reduces the out-of-sample standard deviation by
5.38 percentage points compared with the sample covariance matrix.
    As the gross-exposure constraint becomes more binding, the gains from shrinkage de-
cline. Nevertheless, the DCC-NL estimator is always preferred: it delivers the smallest out-
of-sample standard deviation even when an appropriate gross-exposure constraint is
imposed. We use the prewhitened HACPW method described in Ledoit and Wolf (2011) to
test if the outperformance of DCC-NL over DCC in terms of out-of-sample standard devi-
ation is significant in cases with different gross-exposure constraints. The results show that
the outperformance is always significant at the 0.01 level, except when no short position is
allowed.
    On the other hand, the moderate constraints with c ¼ 2 and c ¼ 1:6 outperform the ex-
treme no-short-sale constraint with c ¼ 1 and the no constraint with c ¼ 1 if no shrinkage
is used in the covariance matrix. For example, when N ¼ 1000, if the sample covariance
matrix is used, the 50% short-sale constraint (c ¼ 2) reduces the out-of-sample standard de-
viation by 4.27 and 1.67 percentage points compared with the no-constraint strategy and
the no-short-sale strategy, respectively. However, the effect of imposing a gross-exposure
constraint is limited and becomes insignificant if the NL shrinkage estimator is used.
    As expected, the combined effect of using DCC and imposing an appropriate gross-
exposure constraint is not as good as that of using the DCC-NL estimator. Specifically,
when N ¼ 1000, the GMV portfolio constructed using the DCC estimator with the con-
straint of c ¼ 1:6 has an annualized out-of-sample standard deviation of 8.35%, reducing
the 13.54% from using the sample covariance matrix by over 5 percentage points, but using
the DCC-NL estimator without any gross-exposure constraint generates a lower standard
deviation of 8.16%.
    Figure 7 reveals the change of the out-of-sample risks with the continuous increase of the
parameter c. The out-of-sample risks first decline and then increase for all portfolios con-
structed based on different covariance matrix estimators and for both cases with 500 and
1000 stocks. The optimal choice that corresponds to the lowest risk is around c ¼ 2 (the 150/
50 strategy) for portfolios with 500 stocks and around c ¼ 1:6 (the 130/30 strategy) for port-
folios with 1000 stocks, where in both cases the DCC-NL estimator is suggested.
    Taken together, the DCC-NL estimator achieves the best performance in all cases no
matter whether a gross-exposure constraint is imposed; imposing the 30–50% constraint
on gross-exposure also improves the portfolio performance, but is not as effective as using
the DCC-NL estimator. Thus, investors should use the DCC-NL estimator to improve the
portfolio performance rather than imposing an external gross-exposure constraint.

3.2.2 Results for MVE portfolios
Table 3 presents results for the MVE portfolios constructed based on the signal ROE,
which is a well-known profitability factor that can indicate the growth potential of a firm
Zhao et al. j Risk Reduction and Efficiency Increase                                                                                       93


                                          N=500                                                                 N=1000
                                                                                               11




                                                                                                                                                Downloaded from https://academic.oup.com/jfec/article/21/1/73/6151211 by University Library Zurich / Zentralbibliothek Zurich user on 23 May 2023
                       11.4                                 S                                                                      S
                                                            NL                                                                     NL
                       11.2                                 DCC                               10.5                                 DCC
                                                            DCCNL                                                                  DCCNL

                        11
                                                                                               10
                       10.8
 Annualized Risk (%)




                                                                        Annualized Risk (%)
                       10.6                                                                    9.5

                       10.4
                                                                                                9
                       10.2

                        10                                                                     8.5

                        9.8
                                                                                                8
                        9.6

                        9.4                                                                    7.5
                              1   2         3           4           5                                1   2         3           4           5
                                  Exposure Constraint ( )                                                Exposure Constraint ( )


Figure 7 Comparisons of the out-of-sample risks of the GMV portfolios constructed based on different
covariance matrix estimators (S, NL, DCC, DCC-NL) and facing various degrees of gross-exposure con-
straints (the intensity of the constraint declines with the increase of parameter c).




(Haugen and Baker, 1996) and has been proven to have statistically significant explanatory
power for cross-sectional anomalies (Hou, Xue, and Zhang, 2015; Feng, Giglio, and Xiu,
2020). We calculate ROE by the income before extraordinary divided by 1-quarter-lagged
book equity. The data are from the merged CRSP/Compustat database.
    Judging by the IRs and the corresponding significant test,6 the DCC-NL estimator still
performs the best among all covariance matrix estimators and its outperformance relative
to DCC is statistically significant when the gross-exposure constraint is not too tight. When
N ¼ 1000 and no constraint is imposed on weights, the MVE portfolio constructed using
the DCC-NL estimator has an IR of 1.79, almost double that from using the sample covari-
ance matrix. When no shrinkage is in the covariance matrix, the 130/30 and 150/50 strat-
egies outperform the strategy without any constraint on weights or with the extreme
no-short-sale constraint. In addition, directly using the NL shrinkage estimator excels
imposing the 30% or 50% short-sale constraint, both of which are superior to imposing
the no-short-sale constraint, whereas both are inferior to using the DCC-NL estimator
without any constraint.
    These findings again support our conjecture that imposing constraints on portfolio
weights has a shrinkage-like effect, no matter whether the DCC model is used for consider-
ing the dynamics in covariances and variances. But unlike the NL shrinkage technique, it is
difficult to achieve the optimal shrinkage level for the gross-exposure constraint with one
degree of freedom.



6 We use the prewhitened HACPW method described in Ledoit and Wolf (2008) to test if the outper-
  formance of DCC-NL over DCC in terms of out-of-sample IR is significant.
94                                                                    Journal of Financial Econometrics


Table 3 Out-of-sample performance, characteristics of weights, and average turnover of the




                                                                                                                     Downloaded from https://academic.oup.com/jfec/article/21/1/73/6151211 by University Library Zurich / Zentralbibliothek Zurich user on 23 May 2023
MVE portfolio constructed based on the ROE signal

            ^
            R             AvR        StdR      IR            MinW       MaxW        StdW      ShortW       AvT

Panel A: 500 stocks contained in the portfolio
c¼1        S            12.79     11.03    1.16              6.53       10.39       1.79      267.08       6.72
           NL           13.77     10.00    1.38              3.07        5.04       1.05      150.65       2.50
           DCC          15.36     10.73    1.43              4.69       16.35       1.68      195.82       4.27
           DCC-NL       15.27      9.78    1.56***           2.65       14.86       1.32      122.55       2.19
c¼2        S            12.97     10.23    1.27              3.73       10.15       1.07       50.00       2.67
           NL           13.32     10.22    1.30              3.00        6.17       0.86       50.00       1.12
           DCC          14.18     10.05    1.41              3.10       18.36       1.35       50.00       2.55
           DCC-NL       14.42      9.81    1.47**            2.48       17.41       1.29       50.00       1.20
c ¼ 1:6    S            12.63     10.56    1.20              3.38       11.06       1.06       30.00       2.35
           NL           12.98     10.57    1.23              3.00        7.11       0.85       30.00       1.14
           DCC          13.61     10.17    1.34              2.79       19.62       1.36       30.00       2.40
           DCC-NL       13.84     10.01    1.38**            2.39       19.09       1.33       30.00       1.13
c¼1        S            12.74     12.30    1.04               0.00       14.90       1.14        0.00       2.30
           NL           12.83     12.33    1.04               0.00       10.79       0.94        0.00       0.32
           DCC          12.14     11.41    1.06               0.00       22.75       1.47        0.00       1.14
           DCC-NL       12.08     11.41    1.06               0.00       22.68       1.47        0.00       0.15
Panel B: 1000 stocks contained in the portfolio
c¼1        S            13.05     13.82    0.94              7.57        9.80       1.73      571.36      12.88
           NL           14.57      9.02    1.62              1.55        2.48       0.51      151.45       3.39
           DCC          13.46     10.95    1.23              4.83       19.52       1.42      361.70       7.82
           DCC-NL       15.00      8.37    1.79***           1.45       16.67       0.83      110.62       2.89
c¼2        S            13.36      9.36    1.43              2.50        8.52       0.64       50.00       2.86
           NL           13.74      9.46    1.45              1.77        3.53       0.44       50.00       1.36
           DCC          14.12      8.59    1.64              1.98       21.72       0.96       50.00       2.69
           DCC-NL       14.34      8.33    1.72**            1.47       19.77       0.88       49.99       1.41
c ¼ 1:6    S            13.20      9.72    1.36              2.22        9.32       0.64       30.00       2.48
           NL           13.55      9.82    1.38              1.92        4.17       0.45       30.00       1.35
           DCC          13.75      8.61    1.60              1.81       23.19       0.99       30.00       2.54
           DCC-NL       13.73      8.45    1.62              1.45       22.04       0.95       30.00       1.25
c¼1        S            14.14     11.66    1.21               0.00       12.68       0.73        0.00       2.42
           NL           13.77     11.77    1.17               0.00        7.17       0.53        0.00       0.49
           DCC          12.03     10.06    1.20               0.00       25.05       1.07        0.00       1.24
           DCC-NL       11.95      9.97    1.20               0.00       24.97       1.07        0.00       0.17

Notes: This table shows the out-of-sample results for the MVE portfolios constructed based on the signal ROE,
using different covariance matrix estimators and facing various degrees of gross-exposure constraints. The covari-
ance matrix is estimated using the most recent 1250 daily returns based on four different methods, which are the
sample covariance matrix (S), the NL shrinkage estimator (NL) (Ledoit and Wolf, 2015), the DCC estimator
(Engle, 2002), and the DCC-NL estimator (Engle, Ledoit, and Wolf, 2019). c is a gross-exposure parameter indi-
cating the supremum of the sum of the absolute weights. Therefore, c ¼ 1; 2; 1:6; 1 stands for an increasing re-
striction with the total short position not exceeding 1; 50%; 30%; 0 of the total investment. We hold the
portfolios for 21 days and record their daily returns. We report their out-of-sample AvR, annualized standard
deviations (StdR), and IRs. Four characteristics of portfolio weights, including the minimum weight (MinW), the
maximum weight (MaxW), the standard deviation of weights (StdW), and the total short positions of weights
(ShortW), and the average turnover (AvT) of portfolios are also reported. All numbers shown are in percentage ex-
cept those for IRs. Panels A and B show results for portfolios with 500 and 1000 stocks, respectively. In the rows
labeled DCC and DCC-NL, significant outperformance of one of the two portfolios over the other in terms of IR
is denoted by asterisks: ***, **, and * denote significance at the 0.01, 0.05, and 0.1 levels, respectively.
Zhao et al. j Risk Reduction and Efficiency Increase                                         95


3.3 Portfolio Weights




                                                                                                   Downloaded from https://academic.oup.com/jfec/article/21/1/73/6151211 by University Library Zurich / Zentralbibliothek Zurich user on 23 May 2023
For each investment period, we compute the minimum weight (MinW), the maximum
weight (MaxW), the standard deviation of weights (StdW), and the total short positions in
weights (ShortW) across the N stocks of the portfolio. We present the average values over
the 396 investment dates from January 8, 1986 to December 31, 2018 for the four charac-
teristics of portfolio weights in Tables 2 and 3.
    We find that portfolios constructed based on the sample covariance matrix have the
smallest minimum weight and the largest total short position, whereas portfolios con-
structed based on the DCC estimator have the largest maximum weight, and portfolios con-
structed based on the NL estimator have the smallest maximum weight and the smallest
standard deviation in weights.
    If no gross-exposure constraint is in place, the total short positions are always large, es-
pecially when N is large and no shrinkage is used in the estimation of the covariance ma-
trix. For example, when N ¼ 1000, the total short position of GMV portfolio reaches
335.99% if the DCC estimator is used, and this number even comes up to 557.00 if the
sample covariance matrix is used. For MVE portfolios, the corresponding short positions
are even larger, with 361.70% for the DCC estimator and 571.36% for the sample covari-
ance matrix.
    Similar to imposing the gross-exposure constraints, using the NL shrinkage estimators
largely reduces the total short position and the turnover of portfolios. This should not be
surprising considering how the NL shrinkage method works in improving the estimation
precision of covariance matrix.

3.4 Robustness Checks
3.4.1 Alternative predictors
For robustness check, we consider the MVE portfolios with an alternative factor exposure.
Instead of using the signal ROE, now we focus on a factor that not only indicates growth
potential but also reflects price level. We follow Basu (1983) and use E/P, measured as in-
come before extraordinary divided by the market capitalization.
   Table 4 presents the results for the MVE portfolios constructed based on the E/P signal,
from which we draw similar conclusions to our main findings aforementioned. First, the
DCC-NL estimator still performs the best among all estimators we considered, though its
advantage over DCC is significant only when the constraint on gross-exposure is loose
enough. When N ¼ 1000 and no constraint on gross-exposure is imposed, the NL estimator
and the DCC-NL estimator increase the IR based on the sample covariance matrix by more
than 70% and 90%, respectively. The gains from NL shrinkage become weaker as the in-
tensity of the gross-exposure constraint increases and the size of the portfolio decreases.
Second, the moderate constraints with c ¼ 2 and c ¼ 1:6 lead to better out-of-sample per-
formance than no constraint or the extreme no-short-sale constraint when S or DCC is
used. Third, the effect of using the NL estimator is more remarkable than that of imposing
the 30% or 50% short-sale constraint. When N ¼ 1000, the use of NL estimator and the
50% short-sale constraint raise the IR of the portfolio constructed from 1.03 to 1.74 and
1.62, respectively.
96                                                                   Journal of Financial Econometrics


Table 4 Out-of-sample performance, characteristics of weights, and average turnover of the




                                                                                                                  Downloaded from https://academic.oup.com/jfec/article/21/1/73/6151211 by University Library Zurich / Zentralbibliothek Zurich user on 23 May 2023
MVE portfolio constructed based on the E/P signal

            ^
            R             AvR       StdR       IR           MinW       MaxW        StdW      ShortW       AvT

Panel A: 500 stocks contained in the portfolio
c¼1        S            13.86     10.89    1.27             6.46       10.49       1.77     263.44        6.73
           NL           14.64      9.90    1.48             3.06        5.36       1.04     148.22        2.47
           DCC          16.37     10.58    1.55             4.82       16.27       1.66     192.81        4.24
           DCC-NL       16.23      9.69    1.68***          2.67       14.67       1.30     120.38        2.16
c¼2        S            13.96     10.14    1.38             3.65       10.67       1.07      50.00        2.67
           NL           14.30     10.16    1.41             2.94        6.80       0.85      50.00        1.13
           DCC          15.52      9.91    1.57             3.13       18.23       1.34      50.00        2.55
           DCC-NL       15.49      9.72    1.59             2.47       17.16       1.27      50.00        1.20
c ¼ 1:6    S            14.07     10.46    1.35             3.31       11.76       1.06      30.00        2.36
           NL           14.46     10.51    1.38             2.91        7.97       0.86      30.00        1.15
           DCC          15.16     10.04    1.51             2.83       19.63       1.36      30.00        2.41
           DCC-NL       15.11      9.92    1.52             2.39       18.97       1.32      30.00        1.13
c¼1        S            15.50     12.66    1.22              0.00       16.42       1.20       0.00        2.34
           NL           15.61     12.80    1.22              0.00       12.52       1.00       0.00        0.32
           DCC          15.04     11.67    1.29              0.00       23.66       1.51       0.00        1.15
           DCC-NL       15.02     11.59    1.30              0.00       23.50       1.51       0.00        0.15
Panel B: 1000 stocks contained in the portfolio
c¼1        S            14.04     13.65    1.03             7.65       10.09       1.72     567.54       12.84
           NL           15.51      8.93    1.74             1.51        2.63       0.51     149.02        3.35
           DCC          14.74     10.77    1.37             5.04       19.48       1.40     355.07        7.71
           DCC-NL       15.94      8.27    1.93***          1.42       16.46       0.82     107.99        2.85
c¼2        S            15.02      9.28    1.62             2.50        9.03       0.64      50.00        2.87
           NL           15.13      9.40    1.61             1.76        3.78       0.43      50.00        1.38
           DCC          15.77      8.51    1.85             2.06       21.64       0.95      50.00        2.72
           DCC-NL       15.67      8.25    1.90             1.45       19.45       0.87      49.99        1.43
c ¼ 1:6    S            15.38      9.66    1.59             2.17        9.95       0.64      30.00        2.51
           NL           15.43      9.80    1.57             1.88        4.53       0.44      30.00        1.37
           DCC          15.42      8.53    1.81             1.81       23.19       0.99      30.00        2.56
           DCC-NL       15.31      8.36    1.83             1.41       21.81       0.94      30.00        1.26
c¼1        S            17.49     12.01    1.46              0.00       13.84       0.75       0.00        2.45
           NL           17.47     12.18    1.43              0.00        8.19       0.55       0.00        0.50
           DCC          15.12     10.27    1.47              0.00       26.05       1.10       0.00        1.28
           DCC-NL       14.98     10.18    1.47              0.00       25.70       1.10       0.00        0.17

Notes: This table is similar to Table 3 except that the MVE portfolios are constructed based on the E/P signal.



3.4.2 Transaction costs
Transaction costs are important issues in practical implementations (Mei, DeMiguel, and
Nogales, 2016; Mei and Nogales, 2018). In Table 5, we present results for the MVE port-
folios constructed based on the ROE signal, when the transaction costs are considered.
Referring to Avramovic and Mackintosh (2013) and Webster et al. (2015), we set the bid–
ask spread to be three or five basis-points to embody the transaction costs.
Zhao et al. j Risk Reduction and Efficiency Increase                                                        97


Table 5 Out-of-sample performance of the MVE portfolio constructed based on the ROE signal




                                                                                                                  Downloaded from https://academic.oup.com/jfec/article/21/1/73/6151211 by University Library Zurich / Zentralbibliothek Zurich user on 23 May 2023
with transaction costs considered

                              Spread ¼ 3 basis-points                    Spread ¼ 5 basis-points

             ^
             R                AvR          StdR          IR              AvR          StdR          IR

Panel A: 500 stocks contained in the portfolio
c¼1         S               10.37        11.04           0.94             8.75         11.07         0.79
            NL              10.45        10.03           1.04             8.23         10.10         0.82
            DCC             11.40        10.77           1.06             8.77         10.87         0.81
            DCC-NL          12.06          9.81          1.23***          9.92          9.88         1.00***
c¼2         S                9.59        10.26           0.93             7.33         10.33         0.71
            NL              10.49        10.23           1.03             8.61         10.28         0.84
            DCC             10.84        10.08           1.08             8.61         10.14         0.85
            DCC-NL          11.56          9.83          1.18***          9.66          9.88         0.98***
c ¼ 1:6     S                9.36        10.58           0.88             7.18         10.64         0.68
            NL              10.14        10.59           0.96             8.25         10.63         0.78
            DCC             10.32        10.20           1.01             8.13         10.26         0.79
            DCC-NL          11.01        10.03           1.10***          9.13         10.08         0.91***
c¼1         S                9.49        12.32           0.77             7.33         12.37         0.59
            NL              10.29        12.34           0.83             8.59         12.37         0.69
            DCC              9.30        11.43           0.81             7.41         11.47         0.65
            DCC-NL           9.60        11.42           0.84***          7.95         11.45         0.69***
Panel B: 1000 stocks contained in the portfolio
c¼1         S                8.75        11.07           0.79             5.31         13.97         0.38
            NL               8.23        10.10           0.82             4.81          9.40         0.51
            DCC              8.77        10.87           0.81             1.05         11.45         0.09
            DCC-NL           9.92          9.88          1.00***          5.54          8.75         0.63***
c¼2         S                7.33        10.33           0.71             3.91          9.69         0.40
            NL               8.61        10.28           0.84             5.19          9.72         0.53
            DCC              8.61        10.14           0.85             4.78          8.94         0.53
            DCC-NL           9.66          9.88          0.98***          5.76          8.64         0.67***
c ¼ 1:6     S                7.18        10.64           0.68             3.98         10.02         0.40
            NL               8.25        10.63           0.78             5.00         10.08         0.50
            DCC              8.13        10.26           0.79             4.49          8.96         0.50
            DCC-NL           9.13        10.08           0.91***          5.25          8.75         0.60***
c¼1         S                7.33        12.37           0.59             4.95         11.91         0.42
            NL               8.59        12.37           0.69             5.74         11.96         0.48
            DCC              7.41        11.47           0.65             3.55         10.30         0.34
            DCC-NL           7.95        11.45           0.69***          4.11         10.18         0.40***

Notes: This table shows the out-of-sample results for the MVE portfolios constructed based on the signal
ROE, using different covariance matrix estimators and facing various degrees of gross-exposure constraints
when transaction costs are considered. We report their out-of-sample AvR, annualized standard deviations
(StdR), and IRs. AvR and StdR are shown in percentage. Panels A and B show results for portfolios with 500
and 1000 stocks, respectively. The left and right panels show results under the assumptions of three basis-
points and five basis-points bid–ask spreads, respectively. In the rows labeled DCC and DCC-NL, significant
outperformance of one of the two portfolios over the other in terms of IR is denoted by asterisks: ***, **, and
* denote significance at the 0.01, 0.05, and 0.1 levels, respectively.
98                                                         Journal of Financial Econometrics


    Unsurprisingly, the IR becomes lower with the increase of transaction costs.




                                                                                                  Downloaded from https://academic.oup.com/jfec/article/21/1/73/6151211 by University Library Zurich / Zentralbibliothek Zurich user on 23 May 2023
Features suggested by the pattern of IRs are consistent with our main results. The DCC-NL
estimator generates the best out-of-sample performance among the four covariance
matrix estimators in all cases. The advantage of the DCC-NL estimator is most remarkable
when no gross-exposure constraint is imposed. When N ¼ 500 and the bid–ask spread
is three basis-points, using DCC-NL estimator increases the IR of using S estimator
from 0.94 to 1.23, if no constraint is imposed on gross-exposure. When constraints are
imposed, the DCC-NL estimator still helps increase the IR. Moreover, owing to the parsi-
mony of the shrinkage method in turnover, the advantage of the DCC-NL estimator over
the DCC (S) estimator becomes more significant and robust than when the transaction costs
are ignored.

3.5 Combining Shrinkage with Gross-Exposure Constraint in Practice
In the process of researching the comparison of gross-exposure constraint versus shrinkage,
it so happens that we have also gathered evidence as to whether there are any benefits from
combining both techniques. The question is: benefits to whom?
    With respect to a gross-exposure-constrained portfolio, upgrading from the sample co-
variance matrix to the DCC-NL estimator (while preserving the gross-exposure constraint)
yields benefits almost as across-the-board as in the Monte-Carlo simulations analyzed in
Section 2.4. The pattern identified earlier still holds: shrinkage has more room for improve-
ment if gross-exposure is less binding of a constraint.
    With respect to a pure DCC-NL portfolio, gradually tightening the gross-exposure con-
straint often hurts, but not always, and may even help at the beginning. Thus, there are cir-
cumstances where imposing c ¼ 2, which corresponds to a 150/50 portfolio, actually results
in better performance:

 • GMV portfolio, 500-stock universe.
 • GMV portfolio, 1000-stock universe.
 • ROE-optimized portfolio, 5-bp transaction cost, and 1000-stock universe.
   In most other cases, moving from an absence of gross-exposure constraint to a 150/50
portfolio generated very little loss. Thus, taking into account the practicalities of the prob-
lem, it seems that 150/50 is the “sweet spot” where short-sale does not start to hurt (much),
provided we have a good NL shrinkage estimator of the conditional covariance matrix such
as DCC-NL.


4 Conclusion
Constraints on portfolio weights are often used by quantitative investors. Besides the non-
negative constraint, strategies limiting the total short position to be at most 30% and 50%
of the portfolio value are prevalent in practice, that is, the so-called “130/30” strategy and
“150/50” strategy. Previous studies argue that using an advanced estimator for the covari-
ance matrix is unnecessary or even harmful in constructing GMV or MVE portfolios if
some certain constraints on weights are in place as the two different approaches reduce
portfolio risks in a similar way. This paper finds that the DCC-NL estimator, which consid-
ers both the dynamics and the estimation precision of the covariance matrix, is always pre-
ferred for a wide range of gross-exposure constraint parameters.
Zhao et al. j Risk Reduction and Efficiency Increase                                        99


    We extend the mathematical connection between imposing the gross-exposure con-




                                                                                                  Downloaded from https://academic.oup.com/jfec/article/21/1/73/6151211 by University Library Zurich / Zentralbibliothek Zurich user on 23 May 2023
straint and using the shrinkage estimator of the covariance matrix to a dynamic framework.
Despite the mathematical equivalence, the NL shrinkage method has at least two advan-
tages compared with the gross-exposure constraint: first, it has N degrees of freedom, leav-
ing enough room for the benefits of the optimization; second, it uses an automatic
procedure to achieve optimization and does not need any exogenous constraint parameter.
Thus, using the NL shrinkage estimator outperforms imposing a gross-exposure constraint.
Besides the above finding, we also demonstrate through Monte Carlo simulations that
upgrading from the sample covariance matrix to the DCC-NL estimator is beneficial, even
after the gross-exposure constraint has already been imposed. The good out-of-sample per-
formance of the DCC-NL estimator is attributed to both the use of a DCC model, which
captures the dynamic structure, and the introduction of an appropriate shrinkage, which
reduces estimation errors.
    Based on daily return data from stocks traded on the NYSE, AMEX, and NASDAQ, we
construct GMV portfolios and MVE portfolios exposed to return predictive signals for
portfolio sizes N ¼500 and 1000. The empirical results show that with respect to a gross-
exposure-constrained portfolio, using the DCC-NL estimator yields the best out-of-sample
performance in all cases, and the benefits of the shrinkage are significant if the gross-
exposure constraint is moderate and thus there is enough room for the benefits of the
shrinkage formula. In contrast, gradually tightening the gross-exposure constraint often
hurts a pure DCC-NL portfolio when c is smaller than 2, corresponding to the constraint
that allows 50% short positions at most. Though imposing an appropriate gross-exposure
constraint has a similar effect as using the NL shrinkage estimator in reducing risks, the lat-
ter always performs better. Taking into account the dynamic nature and upgrading to the
DCC-NL estimator improve the performance even further. In addition, both the NL shrink-
age and the gross-exposure constraint help reduce the standard deviation of weights and
the turnover of portfolios.
    In our main study, we use the ROE as a proxy for the expected return to construct the
MVE portfolio. As robustness checks, we consider the E/P as an alternative proxy and also
take the effect of transaction costs into account by assuming the bid–ask spread to be three
or five basis-points. Our findings turn out to be robust to both of these changes.


Appendix A
A. Theoretical Justifications
Proof of Theorem 1. (i) Note that the matrix R  ~ c;t is obviously symmetric and the solution
to problem (1.8) is denoted by wt . For any vector x,
                                                                          
                                          ^ t x þ 1 k x0 g 10 x þ x0 1g 0 x
                             ~ c;t x ¼ x0 R
                          x0 R                            t            t                 (A.1)
                                                  2
                                           ^ t x þ kðx0 g Þð10 xÞ:
                                      ¼ x0 R            t


                                                 ^ t w  l1 þ kg ¼ 0. Therefore,
Based on the KKT conditions in Equation (1.10), 2R    t         t
100                                                                   Journal of Financial Econometrics


                                                            ^ t w Þ þ lðx01Þ2 :
                              kðx0 gt Þð10 xÞ ¼ 2ðx0 1Þðx0 R                                      (A.2)
                                                                 t




                                                                                                           Downloaded from https://academic.oup.com/jfec/article/21/1/73/6151211 by University Library Zurich / Zentralbibliothek Zurich user on 23 May 2023
   Note that
                                           1
                                                 1 
                       ^ t w j ¼ jðx0 1Þ x0 R
            jðx0 1Þ x0 R                    ^2 R                      ^ t xÞ12 ðw 0 R
                                                  ^ 2 w j  jðx0 1Þðx0R             ^ t w Þ12 j;
                            t                 t     t t                          t       t


where the equality holds because of the positive definiteness of the DCC estimator R^ t , and
the inequality could be obtained by Cauchy–Schwarz inequality.
   In addition, because the DCC estimator R  ^ t is positive definite under some conditions,
we have

                          ^ t w ¼ 1 lw 0 1  1 kw 0 g ¼ 1 l  1 kjjw jj  1 l:
                 0 < wt 0 R    t
                                  2 t        2 t t 2          2     t 1
                                                                          2
   Hence,

                                                                    12
                               jðx0 1Þ x0 R                  ^ t xÞ12 1 l :
                                          ^ t w j  jx0 1jðx0R                                     (A.3)
                                               t
                                                                      2

   Combining (A.1)–(A.3), we have

                        ~ c;t x ¼ x0 R
                     x0 R                               ^ t w Þ þ lðx01Þ2
                                     ^ t x  2ðx0 1Þðx0 R
                                                              t
                                x R t x  2jðx 1Þðx R t wt Þj þ lðx01Þ2
                                   0^            0     0^
                                                                1                                (A.4)
                                                      ^ t xÞ12 1 l 2 þ lðx01Þ2
                                    ^ t x  2jx0 1jðx0R
                                x0 R                           2
                            ¼ ða  bÞ2 þ b2 ;
                                1
where a ¼ ðx0R^ t xÞ12 and b ¼ 1 l 2 jx0 1j.
                                 2
    Moreover, ða  bÞ2 þ b2 is always nonnegative and is zero if and only if a ¼ b and b ¼ 0
hold simultaneously. However, a ¼ ðx0R      ^ t xÞ12 > 0 because R
                                                                 ^ t is positive definite. Therefore,
                     0~                                                               ~ c;t .
for any vector x, x R c;t x > 0 holds. This indicates the positive definiteness of R

Proof of Theorem 1. (ii) First, the optimization problem (1.11) with equality constraint
could be solved through the Lagrange multiplier method. Construct the Lagrangian
                                                   ~ c;t wt  lc ðw0 1  1Þ;
                                 Lðwt ; lc Þ ¼ w0t R               t

                      opt
then the solution wt        to this minimization problem should satisfy

                                         (
                                                   opt
                                              ~ c;t wt  lc 1 ¼ 0;
                                             2R
                                              opt0
                                             wt 1  1 ¼ 0:

        ~ c;t is invertible, then the solution to this problem is given by
Because R

                                                         ~ 1 1
                                                         R
                                              wopt
                                                           c;t
                                               t   ¼       1
                                                                  :                                (A.5)
                                                       10 R
                                                          ~ 1
                                                            c;t

   By the Lagrange multiplier method, problem (1.8) is to minimize

                                          ^ t wt  lðw0 1  1Þ  kðc  jjwt jj Þ:
                       Lðwt ; l; kÞ ¼ w0t R           t                       1

   Based on the fact that gt 0 wt ¼ jjwt jj1 and KKT conditions in Equation (1.10), we have
Zhao et al. j Risk Reduction and Efficiency Increase                                           101


                                      ^ t w þ 1 kg 10 w þ 1 k1g 0 w
                            ~ c;t w ¼ R
                            R      t       t
                                              2 t      t       t   t




                                                                                                      Downloaded from https://academic.oup.com/jfec/article/21/1/73/6151211 by University Library Zurich / Zentralbibliothek Zurich user on 23 May 2023
                                                          2
                                             1        1
                                      ^ t w þ kg þ kjjw jj 1
                                     ¼R    t               t 1
                                             2 t 2
                                      1
                                     ¼ ðkc þ lÞ1:
                                      2
                                                                              1
   Hence, the solution to problem (1.8) wt ¼ 12 ðkc þ lÞR      ~ 1. Moreover, because of the
                                                                 c;t
constraint w0t 1 ¼ 1, solving for kc þ l yields kc þ l ¼ 0 ~21 . This fact indicates that
                                                                  1 R c;t 1
                                                           opt
                                                   wt ¼ wt :

   Therefore, it implies the equivalence of the partial constrained optimization problem and
the (unconstrained) optimization problem with regularized covariance matrix estimator.
Proof of Theorem 2. First, the optimization problem (1.17) with equality constraint could
be solved through the Lagrange multiplier method. Construct the Lagrangian
                                           ~ c;t wt  l1c ðw0 1  1Þ  l2c ðw0 mt  bt Þ;
                  Lðwt ; l1c ; l2c Þ ¼ w0t R                t                t

                      opt
then the solution wb;t to this minimization problem should satisfy

                                 (
                                      ~ c;t wopt  l1c 1  l2c mt ¼ 0;
                                     2R      b;t
                                      opt0                opt0
                                     wb;t 1  1 ¼ 0; wb;t mt  bt ¼ 0:

                                                   
            opt       ~ 1 1 þ l2c R
Therefore, wb;t ¼ l1c R                      ~ 1 1; mt Þð l1c Þ.
                                   ~ 1 mt ¼ R
                        c;t          c;t       c;t         l2c
  The above equations also imply that

                                     1       ~ 1 1 þ 1 l2c 10 R
                                                               ~ 1 mt ;
                                  1 ¼ l1c 10 R c;t               c;t
                                     2                2
                                     1     0 ~ 1     1        0 ~ 1
                                 bt ¼ l1c mt R c;t 1 þ l2c mt R c;t mt ;
                                     2                2
or
                                                                         
                                    1         1          ~ 1 ð1; mt Þ l1c :
                                             ¼ ð1; mt Þ0 R c;t
                                    bt        2                         l2c

     Solving for ðl1c ; l2c Þ0 yields
                                                                    
                                   l1c                 ~ 1 ð1; mt Þ 1 :
                                         ¼ 2½ð1; mt Þ0 R c;t
                                   l2c                                bt

     Therefore, the solution to this problem is given by
                                                                          
                            wopt ¼ R                       ~ 1 ð1; mt Þ 1 :
                                   ~ 1 ð1; mt Þ½ð1; mt Þ0 R                                  (A.6)
                             b;t     c;t                     c;t          bt

     By the Lagrange multiplier method, problem (1.12) is to minimize
                                                                                     
                                    ^ t wt  l1 w0 1  1  l2 w0 mt  bt  k c  jjwt jj :
          Lðwt ; l1 ; l2 ; kÞ ¼ w0t R            t             t                        1

     So, the KKT conditions are
102                                                                 Journal of Financial Econometrics

                           8
                           >   ^ t wt  l1 1  l2 mt þ kg ¼ 0;
                           < 2R                        t




                                                                                                        Downloaded from https://academic.oup.com/jfec/article/21/1/73/6151211 by University Library Zurich / Zentralbibliothek Zurich user on 23 May 2023
                             k c  jjwt jj1 ¼ 0; k  0;                                         (A.7)
                           >
                           : jjwt jj  c; w0 1  1 ¼ 0; w0 mt  bt ¼ 0:
                                    1         t            t


   Based on the fact that gb;t0 wb;t ¼ jjwb;t jj1 and KKT conditions in Equation (A.7), we
have

                      ~ c;t w ¼ R
                      R            ^ t w þ 1 kg 10 w þ 1 k1g 0 w
                             b;t        b;t
                                             2 b;t    b;t
                                                          2        b;t b;t

                                   ^         1       1
                                 ¼ R t wb;t þ kgb;t þ kjjwb;t jj1 1
                                             2       2
                                   1               1
                                 ¼ ðkc þ l1 Þ1 þ l2 mt :
                                   2               2

                                      1
                               ~ ½ðkc þ l1 Þ1 þ l2 mt . The constraints also imply that
It then follows that wb;t ¼ 12 R c;t

                                 1             ~ 1 1 þ 1 l2 10 R
                                                                ~ 1 mt ;
                              1 ¼ ðkc þ l1 Þ10 R c;t              c;t
                                 2                      2
                                 1                1    1
                                                ~ 1 þ l 2 m0 R   ~ 1
                             bt ¼ ðkc þ l1 Þm0t R c;t           t c;t mt ;
                                 2                      2
or
                                                                         
                                 1          1          ~ 1 ð1; mt Þ kc þ l1 :
                                           ¼ ð1; mt Þ0 R c;t
                                 bt         2                           l2

     Solving for ðkc þ l1 ; l2 Þ0 yields
                                                                      
                               kc þ l1                   ~ 1 ð1; mt Þ 1 :
                                           ¼ 2½ð1; mt Þ0 R
                                   l2                      c;t          bt

     Hence,
                                                                         
                           wb;t ¼ R                       ~ 1 ð1; mt Þ 1 :
                                  ~ 1 ð1; mt Þ½ð1; mt Þ0 R                                     (A.8)
                                    c;t                     c;t          bt
                                           opt
     We can then conclude that wb;t ¼ wb;t . This completes the proof.


References
Ao, M., Y. Li, and X. Zheng. 2019. Approaching Mean–Variance Efficiency for Large Portfolios.
  The Review of Financial Studies 32: 2890–2919.
Avramovic, A., and P. Mackintosh. 2013. Inside the NBBO: Pushing for wider—and narrower!—
  spreads. Trading strategy: Market commentary, Credit Suisse Research and Analytics.
Bai, J., and K. Li. 2012. Statistical Analysis of Factor Models of High Dimension. The Annals of
  Statistics 40: 436–465.
Basu, S. 1983. The Relationship between Earnings’ Yield, Market Value and Return for NYSE
  Common Stocks: Further Evidence. Journal of Financial Economics 12: 129–156.
Bauder, D., T. Bodnar, N. Parolya, and W. Schmid. 2020. Bayesian Mean–Variance Analysis:
  Optimal Portfolio Selection under Parameter Uncertainty. Quantitative Finance 1–22.
Behr, P., A. Guettler, and F. Miebs. 2013. On Portfolio Optimization: Imposing the Right
  Constraints. Journal of Banking & Finance 37: 1232–1242.
Zhao et al. j Risk Reduction and Efficiency Increase                                       103


Bodnar, T., N. Parolya, and W. Schmid. 2018. Estimation of the Global Minimum Variance




                                                                                                  Downloaded from https://academic.oup.com/jfec/article/21/1/73/6151211 by University Library Zurich / Zentralbibliothek Zurich user on 23 May 2023
  Portfolio in High Dimensions. European Journal of Operational Research 266: 371–390.
Bollerslev, T., A. J. Patton, and R. Quaedvlieg. 2018. Modeling and Forecasting (un)Reliable
  Realized Covariances for More Reliable Financial Decisions. Journal of Econometrics 207:
  71–91.
Boyd, S., S. P. Boyd, and L. Vandenberghe. 2004. Convex Optimization. Cambridge University
  Press.
Brandt, M. W., P. Santa-Clara, and R. Valkanov. 2009. Parametric Portfolio Policies: Exploiting
  Characteristics in the Cross-Section of Equity Returns. Review of Financial Studies 22:
  3411–3447.
Branger, N., K. Lucivjanská, and A. Weissensteiner. 2019. Optimal Granularity for Portfolio
  Choice. Journal of Empirical Finance 50: 125–146.
Britten-Jones, M. 1999. The Sampling Error in Estimates of Mean–Variance Efficient Portfolio
  Weights. The Journal of Finance 54: 655–671.
Brodie, J., I. Daubechies, C. De Mol, D. Giannone, and I. Loris. 2009. Sparse and Stable
  Markowitz Portfolios. Proceedings of the National Academy of Sciences of the United States of
  America 106: 12267–12272.
Callot, L., M. Caner, A. Ö. Önder, and E. Ulasan. 2020. A Nodewise Regression Approach to
  Estimating Large Portfolios. Journal of Business & Economic Statistics, forthcoming.
De Nard, G., O. Ledoit, and M. Wolf. 2020. Factor Models for Portfolio Selection in Large
  Dimensions: The Good, the Better and the Ugly. Journal of Financial Econometrics, forthcom-
  ing (https://doi.org/10.1093/jjfinec/nby033).
DeMiguel, V., L. Garlappi, F. J. Nogales, and R. Uppal. 2009a. A Generalized Approach to
  Portfolio Optimization: Improving Performance by Constraining Portfolio Norms.
  Management Science 55: 798–812.
DeMiguel, V., L. Garlappi, and R. Uppal. 2009b. Optimal versus Naive Diversification: How
  Inefficient is the 1/N Portfolio Strategy? Review of Financial Studies 22: 1915–1953.
DeMiguel, V., A. Martin-Utrera, and F. J. Nogales. 2013. Size Matters: Optimal Calibration of
  Shrinkage Estimators for Portfolio Selection. Journal of Banking & Finance 37: 3018–3034.
Engle, R. F. 2002. Dynamic Conditional Correlation: A Simple Class of Multivariate Generalized
  Autoregressive Conditional Heteroskedasticity Models. Journal of Business & Economic
  Statistics 20: 339–350.
Engle, R. F., O. Ledoit, and M. Wolf. 2019. Large Dynamic Covariance Matrices. Journal of
  Business & Economic Statistics 37: 363–375.
Fan, J., Y. Fan, and J. Lv. 2008. High Dimensional Covariance Matrix Estimation Using a Factor
  Model. Journal of Econometrics 147: 186–197.
Fan, J., Y. Liao, and M. Mincheva. 2013. Large Covariance Estimation by Thresholding Principal
  Orthogonal Complements. Journal of the Royal Statistical Society. Series B, Statistical
  Methodology 75.
Fan, J., J. Zhang, and K. Yu. 2012. Vast Portfolio Selection with Gross-Exposure Constraints.
  Journal of the American Statistical Association 107: 592–606.
Feng, G., S. Giglio, and D. Xiu. 2020. Taming the Factor Zoo: A Test of New Factors. The
  Journal of Finance, 75: 1327–1370.
Frahm, G., and C. Memmel. 2010. Dominating Estimators for Minimum-Variance Portfolios.
  Journal of Econometrics 159: 289–302.
Garlappi, L., R. Uppal, and T. Wang. 2007. Portfolio Selection with Parameter and Model
  Uncertainty: A Multi-Prior Approach. Review of Financial Studies 20: 41–81.
Goldfarb, D., and G. Iyengar. 2003. Robust Portfolio Selection Problems. Mathematics of
  Operations Research 28: 1–38.
104                                                         Journal of Financial Econometrics


Golosnoy, V., and Y. Okhrin. 2007. Multivariate Shrinkage for Optimal Portfolio Weights. The




                                                                                                     Downloaded from https://academic.oup.com/jfec/article/21/1/73/6151211 by University Library Zurich / Zentralbibliothek Zurich user on 23 May 2023
  European Journal of Finance 13: 441–458.
Green, J., J. R. M. Hand, and X. F. Zhang. 2017. The Characteristics that Provide Independent
  Information about Average U.S. Monthly Stock Returns. The Review of Financial Studies 30:
  4389–4436.
Harvey, C. R., Y. Liu, and H. Zhu. 2016. . . .. and the Cross-Section of Expected Returns. Review
  of Financial Studies 29: 5–68.
Haugen, R. A., and N. L. Baker. 1996. Commonality in the Determinants of Expected Stock
  Returns. Journal of Financial Economics 41: 401–439.
Hou, K., C. Xue, and L. Zhang. 2015. Digesting Anomalies: An Investment Approach. Review of
  Financial Studies 28: 650–705.
Jagannathan, R., and T. Ma. 2003. Risk Reduction in Large Portfolios: Why Imposing the Wrong
  Constraints Helps. The Journal of Finance 54: 1651–1684.
Ledoit, O., and M. Wolf. 2003. Improved Estimation of the Covariance Matrix of Stock Returns
  with an Application to Portfolio Selection. Journal of Empirical Finance 10: 603–621.
Ledoit, O., and M. Wolf. 2004a. Honey, I Shrunk the Sample Covariance Matrix. The Journal of
  Portfolio Management 30: 110–119.
Ledoit, O., and M. Wolf. 2004b. A Well-Conditioned Estimator for Large-Dimensional
  Covariance Matrices. Journal of Multivariate Analysis 88: 365–411.
Ledoit, O., and M. Wolf. 2008. Robust Performance Hypothesis Testing with the Sharpe Ratio.
  Journal of Empirical Finance 15: 850–859.
Ledoit, O., and M. Wolf. 2011. Robust Performances Hypothesis Testing with the Variance.
  Wilmott Magazine 2011: 86–89.
Ledoit, O., and M. Wolf. 2012. Nonlinear Shrinkage Estimation of Large-Dimensional
  Covariance Matrices. The Annals of Statistics 40: 1024–1060.
Ledoit, O., and M. Wolf. 2015. Spectrum Estimation: A Unified Framework for Covariance
  Matrix Estimation and PCA in Large Dimensions. Journal of Multivariate Analysis 139:
  360–384.
Ledoit, O., and M. Wolf. 2017a. Nonlinear Shrinkage of the Covariance Matrix for Portfolio
  Selection: Markowitz Meets Goldilocks. The Review of Financial Studies 30: 4349–4388.
Ledoit, O., and M. Wolf. 2017b. Numerical Implementation of the QuEST Function.
  Computational Statistics & Data Analysis 115: 199–223.
Ledoit, O., and M. Wolf. 2020a. Analytical Nonlinear Shrinkage of Large-Dimensional
  Covariance Matrices. Annals of Statistics, 48: 3043–3065.
Ledoit, O., and M. Wolf. 2020b. The Power of (Non-)Linear Shrinking: A Review and Guide to
  Covariance Matrix Estimation. Journal of Financial Econometrics, forthcoming (https://doi.
  org/10.1093/jjfinec/nbaa007).
Ledoit, O., M. Wolf, and Z. Zhao. 2019. Efficient Sorting: A More Powerful Test for
  Cross-Sectional Anomalies. Journal of Financial Econometrics 17: 645–686.
Li, J. 2015. Sparse and Stable Portfolio Selection with Parameter Uncertainty. Journal of Business
  & Economic Statistics 33: 381–392.
Marcenko, V. A., and L. A. Pastur. 1967. Distribution of Eigenvalues for Some Sets of Random
  Matrices. Mathematics of the USSR-Sbornik 1: 457–483.
Markowitz, H. 1952. Portfolio Selection. Journal of Finance 7: 77–91.
Mei, X., V. DeMiguel, and F. J. Nogales. 2016. Multiperiod Portfolio Optimization with Multiple
  Risky Assets and General Transaction Costs. Journal of Banking & Finance 69: 108–120.
Mei, X., and F. J. Nogales. 2018. Portfolio Selection with Proportional Transaction Costs and
  Predictability. Journal of Banking & Finance 94: 131–151.
Pakel, C., N. Shephard, K. Sheppard, and R. F. Engle. 2020. Fitting Vast Dimensional
  Time-Varying Covariance Models. Journal of Business & Economic Statistics, forthcoming.
Zhao et al. j Risk Reduction and Efficiency Increase                                          105


Pástor, L. 2000. Portfolio Selection and Asset Pricing Models. The Journal of Finance 55:




                                                                                                     Downloaded from https://academic.oup.com/jfec/article/21/1/73/6151211 by University Library Zurich / Zentralbibliothek Zurich user on 23 May 2023
  179–223.
Pástor, L., and R. F. Stambaugh. 2009. Predictive Systems: Living with Imperfect Predictors. The
  Journal of Finance 64: 1583–1628.
Sharpe, W. F. 1963. A Simplified Model for Portfolio Analysis. Management Science 9: 277–293.
Stock, J. H., and M. W. Watson. 2002. Forecasting Using Principal Components from a Large
  Number of Predictors. Journal of the American Statistical Association 97: 1167–1179.
Tibshirani, R. 1996. Regression Shrinkage and Selection via the Lasso: A Retrospective. Journal of
  the Royal Statistical Society 58: 267–288.
Tu, J., and G. Zhou. 2010. Incorporating Economic Objectives into Bayesian Priors: Portfolio
  Choice under Parameter Uncertainty. Journal of Financial and Quantitative Analysis 45:
  959–986.
Tu, J., and G. Zhou. 2011. Markowitz Meets Talmud: A Combination of Sophisticated and Naive
  Diversification Strategies. Journal of Financial Economics 99: 204–215.
Wang, Z. 2005. A Shrinkage Approach to Model Uncertainty and Asset Allocation. Review of
  Financial Studies 18: 673–705.
Webster, K., Y. Luo, M. A. Alvarez, J. Jussa, S. Wang, G. Rohal, A. Wang, D. Elledge, and G.
  Zhao. 2015. A Portfolio Manager’s Guidebook to Trade Execution: From Light Rays to Dark
  Pools. Deutsche Bank Markets Research. Quantitative Strategy: Signal Processing, Deutsche
  Bank Markets Research, New York, USA.
Yen, Y.-M. 2016. Sparse Weighted-Norm Minimum Variance Portfolios. Review of Finance 20:
  1259–1287.