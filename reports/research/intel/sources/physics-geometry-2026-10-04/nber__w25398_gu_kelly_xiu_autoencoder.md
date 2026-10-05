source: https://www.nber.org/papers/w25398.pdf
fetched_utc: 2026-10-04T18:39:07Z
bytes_raw: 2387285

NBER WORKING PAPER SERIES



                 EMPIRICAL ASSET PRICING VIA MACHINE LEARNING

                                            Shihao Gu
                                           Bryan Kelly
                                           Dacheng Xiu

                                       Working Paper 25398
                               http://www.nber.org/papers/w25398


                     NATIONAL BUREAU OF ECONOMIC RESEARCH
                              1050 Massachusetts Avenue
                                Cambridge, MA 02134
                         December 2018, Revised September 2019

We benefitted from discussions with Joseph Babcock, Si Chen (Discussant), Rob Engle, Andrea
Frazzini, Amit Goyal (Discussant), Lasse Pedersen, Lin Peng (Discussant), Alberto Rossi
(Discussant), Guofu Zhou (Discussant), and seminar and conference participants at Erasmus
School of Economics, NYU, Northwestern, Imperial College, National University of Singapore,
UIBE, Nanjing University, Tsinghua PBC School of Finance, Fannie Mae, U.S. Securities and
Exchange Commission, City University of Hong Kong, Shenzhen Finance Institute at CUHK,
NBER Summer Institute, New Methods for the Cross Section of Returns Conference, Chicago
Quantitative Alliance Conference, Norwegian Financial Research Conference, EFA, China
International Conference in Finance, 10th World Congress of the Bachelier Finance Society,
Financial Engineering and Risk Management International Symposium, Toulouse Financial
Econometrics Conference, Chicago Conference on New Aspects of Statistics, Financial
Econometrics, and Data Science, Tsinghua Workshop on Big Data and Internet Economics, Q
group, IQ-KAP Research Prize Symposium, Wolfe Re- search, INQUIRE UK, Australasian
Finance and Banking Conference, Goldman Sachs Global Alternative Risk Premia Conference,
AFA, and Swiss Finance Institute. We gratefully acknowledge the computing support from the
Research Computing Center at the University of Chicago. The views expressed herein are those
of the authors and do not necessarily reflect the views of the National Bureau of Economic
Research.

At least one co-author has disclosed a financial relationship of potential relevance for this
research. Further information is available online at http://www.nber.org/papers/w25398.ack

NBER working papers are circulated for discussion and comment purposes. They have not been
peer-reviewed or been subject to the review by the NBER Board of Directors that accompanies
official NBER publications.

© 2018 by Shihao Gu, Bryan Kelly, and Dacheng Xiu. All rights reserved. Short sections of text,
not to exceed two paragraphs, may be quoted without explicit permission provided that full
credit, including © notice, is given to the source.
Empirical Asset Pricing via Machine Learning
Shihao Gu, Bryan Kelly, and Dacheng Xiu
NBER Working Paper No. 25398
December 2018, Revised September 2019
JEL No. C45,C55,C58,G11,G12

                                         ABSTRACT

We perform a comparative analysis of machine learning methods for the canonical problem of
empirical asset pricing: measuring asset risk premia. We demonstrate large economic gains to
investors using machine learning forecasts, in some cases doubling the performance of leading
regression-based strategies from the literature. We identify the best performing methods (trees
and neural networks) and trace their predictive gains to allowance of nonlinear predictor
interactions that are missed by other methods. All methods agree on the same set of dominant
predictive signals which includes variations on momentum, liquidity, and volatility. Improved
risk premium measurement through machine learning simplifies the investigation into economic
mechanisms of asset pricing and highlights the value of machine learning in financial innovation.


Shihao Gu                                                 Dacheng Xiu
University of Chicago Booth School of Business            Booth School of Business
5807 S. Woodlawn                                          University of Chicago
Chicago, IL 60637                                         5807 South Woodlaswn Avenue
shihaogu@chicagobooth.edu                                 Chicago, IL 60637
                                                          dachxiu@chicagobooth.edu
Bryan Kelly
Yale School of Management
165 Whitney Ave.
New Haven, CT 06511
and NBER
bryan.kelly@yale.edu
1       Introduction
In this article, we conduct a comparative analysis of machine learning methods for finance. We do
so in the context of perhaps the most widely studied problem in finance, that of measuring equity
risk premia.

1.1     Primary Contributions
Our primary contributions are two-fold. First, we provide a new set of benchmarks for the predictive
accuracy of machine learning methods in measuring risk premia of the aggregate market and indi-
vidual stocks. This accuracy is summarized two ways. The first is a high out-of-sample predictive
R2 relative to preceding literature that is robust across a variety of machine learning specifications.
Second, and more importantly, we demonstrate the large economic gains to investors using machine
learning forecasts. A portfolio strategy that times the S&P 500 with neural network forecasts enjoys
an annualized out-of-sample Sharpe ratio of 0.77, versus the 0.51 Sharpe ratio of a buy-and-hold
investor. And a value-weighted long-short decile spread strategy that takes positions based on stock-
level neural network forecasts earns an annualized out-of-sample Sharpe ratio of 1.35, more than
doubling the performance of a leading regression-based strategy from the literature.
    Return prediction is economically meaningful. The fundamental goal of asset pricing is to un-
derstand the behavior of risk premia.1 If expected returns were perfectly observed, we would still
need theories to explain their behavior and empirical analysis to test those theories. But risk premia
are notoriously difficult to measure—market efficiency forces return variation to be dominated by
unforecastable news that obscures risk premia. Our research highlights gains that can be achieved
in prediction and identifies the most informative predictor variables. This helps resolve the prob-
lem of risk premium measurement, which then facilitates more reliable investigation into economic
mechanisms of asset pricing.
    Second, we synthesize the empirical asset pricing literature with the field of machine learning.
Relative to traditional empirical methods in asset pricing, machine learning accommodates a far
more expansive list of potential predictor variables and richer specifications of functional form. It is
this flexibility that allows us to push the frontier of risk premium measurement. Interest in machine
learning methods for finance has grown tremendously in both academia and industry. This article
provides a comparative overview of machine learning methods applied to the two canonical problems
of empirical asset pricing: predicting returns in the cross section and time series. Our view is that the
best way for researchers to understand the usefulness of machine learning in the field of asset pricing
is to apply and compare the performance of each of its methods in familiar empirical problems.
    1
      Our focus is on measuring conditional expected stock returns in excess of the risk-free rate. Academic finance
traditionally refers to this quantity as the “risk premium” due to its close connection with equilibrium compensation for
bearing equity investment risk. We use the terms “expected return” and “risk premium” interchangeably. One may be
interested in potentially distinguishing among different components of expected returns such as those due to systematic
risk compensation, idiosyncratic risk compensation, or even due to mispricing. For machine learning approaches to this
problem, see Gu et al. (2019) and Kelly et al. (2019).




                                                           2
1.2    What is Machine Learning?
The definition of “machine learning” is inchoate and is often context specific. We use the term to
describe (i) a diverse collection of high-dimensional models for statistical prediction, combined with
(ii) so-called “regularization” methods for model selection and mitigation of overfit, and (iii) efficient
algorithms for searching among a vast number of potential model specifications.
    The high-dimensional nature of machine learning methods (element (i) of this definition) enhances
their flexibility relative to more traditional econometric prediction techniques. This flexibility brings
hope of better approximating the unknown and likely complex data generating process underlying
equity risk premia. With enhanced flexibility, however, comes a higher propensity of overfitting
the data. Element (ii) of our machine learning definition describes refinements in implementation
that emphasize stable out-of-sample performance to explicitly guard against overfit. Finally, with
many predictors it becomes infeasible to exhaustively traverse and compare all model permutations.
Element (iii) describes clever machine learning tools designed to approximate an optimal specification
with manageable computational cost.

1.3    Why Apply Machine Learning to Asset Pricing?
A number of aspects of empirical asset pricing make it a particularly attractive field for analysis with
machine learning methods.
    1) Two main research agendas have monopolized modern empirical asset pricing research. The
first seeks to describe and understand differences in expected returns across assets. The second
focuses on dynamics of the aggregate market equity risk premium. Measurement of an asset’s risk
premium is fundamentally a problem of prediction—the risk premium is the conditional expectation
of a future realized excess return. Machine learning, whose methods are largely specialized for
prediction tasks, is thus ideally suited to the problem of risk premium measurement.
    2) The collection of candidate conditioning variables for the risk premium is large. The profession
has accumulated a staggering list of predictors that various researchers have argued possess forecast-
ing power for returns. The number of stock-level predictive characteristics reported in the literature
numbers in the hundreds and macroeconomic predictors of the aggregate market number in the
dozens.2 Additionally, predictors are often close cousins and highly correlated. Traditional predic-
tion methods break down when the predictor count approaches the observation count or predictors
are highly correlated. With an emphasis on variable selection and dimension reduction techniques,
machine learning is well suited for such challenging prediction problems by reducing degrees of free-
dom and condensing redundant variation among predictors.
    3) Further complicating the problem is ambiguity regarding functional forms through which the
high-dimensional predictor set enter into risk premia. Should they enter linearly? If nonlinearities
   2
     Green et al. (2013) count 330 stock-level predictive signals in published or circulated drafts. Harvey et al. (2016)
study 316 “factors,” which include firm characteristics and common factors, for describing stock return behavior. They
note that this is only a subset of those studied in the literature. Welch and Goyal (2008) analyze nearly 20 predictors
for the aggregate market return. In both stock and aggregate return predictions, there presumably exists a much larger
set of predictors that were tested but failed to predict returns and were thus never reported.



                                                           3
are needed, which form should they take? Must we consider interactions among predictors? Such
questions rapidly proliferate the set of potential model specifications. The theoretical literature offers
little guidance for winnowing the list of conditioning variables and functional forms. Three aspects
of machine learning make it well suited for problems of ambiguous functional form. The first is its
diversity. As a suite of dissimilar methods it casts a wide net in its specification search. Second, with
methods ranging from generalized linear models to regression trees and neural networks, machine
learning is explicitly designed to approximate complex nonlinear associations. Third, parameter
penalization and conservative model selection criteria complement the breadth of functional forms
spanned by these methods in order to avoid overfit biases and false discovery.

1.4    What Specific Machine Learning Methods Do We Study?
We select a set of candidate models that are potentially well suited to address the three empirical
challenges outlined above. They constitute the canon of methods one would encounter in a graduate
level machine learning textbook.3 This includes linear regression, generalized linear models with pe-
nalization, dimension reduction via principal components regression (PCR) and partial least squares
(PLS), regression trees (including boosted trees and random forests), and neural networks. This is
not an exhaustive analysis of all methods. For example, we exclude support vector machines as these
share an equivalence with other methods that we study4 and are primarily used for classification
problems. Nonetheless, our list is designed to be representative of predictive analytics tools from
various branches of the machine learning toolkit.

1.5    Main Empirical Findings
We conduct a large scale empirical analysis, investigating nearly 30,000 individual stocks over 60
years from 1957 to 2016. Our predictor set includes 94 characteristics for each stock, interactions
of each characteristic with eight aggregate time series variables, and 74 industry sector dummy
variables, totaling more than 900 baseline signals. Some of our methods expand this predictor set
much further by including nonlinear transformations and interactions of the baseline signals. We
establish the following empirical facts about machine learning for return prediction.
    Machine learning shows great promise for empirical asset pricing. At the broadest level, our
main empirical finding is that machine learning as a whole has the potential to improve our empirical
understanding of expected asset returns. It digests our predictor data set, which is massive from
the perspective of the existing literature, into a return forecasting model that dominates traditional
approaches. The immediate implication is that machine learning aids in solving practical investments
problems such as market timing, portfolio choice, and risk management, justifying its role in the
business architecture of the fintech industry.
    Consider as a benchmark a panel regression of individual stock returns onto three lagged stock-
level characteristics: size, book-to-market, and momentum. This benchmark has a number of attrac-
   3
     See, for example, Hastie et al. (2009).
   4
     See, for example, Jaggi (2013) and Hastie et al. (2009), who discuss the equivalence of support vector machines
with the lasso. For an application of the kernel trick to the cross section of returns, see Kozak (2019).


                                                         4
tive features. It is parsimonious and simple, and comparing against this benchmark is conservative
because it is highly selected (the characteristics it includes are routinely demonstrated to be among
the most robust return predictors). Lewellen (2015) demonstrates that this model performs about
as well as larger and more complex stock prediction models studied in the literature.
   In our sample, which is longer and wider (more observations in terms of both dates and stocks)
than that studied in Lewellen (2015), the out-of-sample R2 from the benchmark model is 0.16% per
month for the panel of individual stock returns. When we expand the OLS panel model to include
our set of 900+ predictors, predictability vanishes immediately—the R2 drops deeply into negative
territory. This is not surprising. With so many parameters to estimate, efficiency of OLS regression
deteriorates precipitously and therefore produces forecasts that are highly unstable out-of-sample.
This failure of OLS leads us to our next empirical fact.
   Vast predictor sets are viable for linear prediction when either penalization or dimension reduction
is used. Our first evidence that the machine learning toolkit aids in return prediction emerges
from the fact that the “elastic net,” which uses parameter shrinkage and variable selection to limit
the regression’s degrees of freedom, solves the OLS inefficiency problem. In the 900+ predictor
regression, elastic net pulls the out-of-sample R2 into positive territory at 0.11% per month. Principal
components regression (PCR) and partial least squares (PLS), which reduce the dimension of the
predictor set to a few linear combinations of predictors, further raise the out-of-sample R2 to 0.26%
and 0.27%, respectively. This is in spite of the presence of many likely “fluke” predictors that
contribute pure noise to the large model. In other words, the high-dimensional predictor set in a
simple linear specification is at least competitive with the status quo low-dimensional model, as long
as over-parameterization can be controlled.
   Allowing for nonlinearities substantially improves predictions. Next, we expand the model to
accommodate nonlinear predictive relationships via generalized linear models, regression trees, and
neural networks. We find that trees and neural networks unambiguously improve return prediction
with monthly stock-level R2 ’s between 0.33% and 0.40%. But the generalized linear model, which
introduces nonlinearity via spline functions of each individual baseline predictor (but with no predic-
tor interactions), fails to robustly outperform the linear specification. This suggests that allowing for
(potentially complex) interactions among the baseline predictors is a crucial aspect of nonlinearities
in the expected return function. As part of our analysis, we discuss why generalized linear models
are comparatively poorly suited for capturing predictor interactions.
   Shallow learning outperforms deeper learning. When we consider a range of neural networks
from very shallow (a single hidden layer) to deeper networks (up to five hidden layers), we find that
neural network performance peaks at three hidden layers then declines as more layers are added.
Likewise, the boosted tree and random forest algorithms tend to select trees with few “leaves” (on
average less than six leaves) in our analysis. This is likely an artifact of the relatively small amount
of data and tiny signal-to-noise ratio for our return prediction problem, in comparison to the kinds
of non-financial settings in which deep learning thrives thanks to astronomical datasets and strong
signals (such as computer vision).
   The distance between nonlinear methods and the benchmark widens when predicting portfolio


                                                   5
returns. We build bottom-up portfolio-level return forecasts from the stock-level forecasts produced
by our models. Consider, for example, bottom-up forecasts of the S&P 500 portfolio return. By
aggregating stock-level forecasts from the benchmark three-characteristic OLS model, we find a
monthly S&P 500 predictive R2 of −0.22%. The bottom-up S&P 500 forecast from the generalized
linear model, in contrast, delivers an R2 of 0.71%. Trees and neural networks improve upon this
further, generating monthly out-of-sample R2 ’s between 1.08% to 1.80% per month. The same
pattern emerges for forecasting a variety of characteristic factor portfolios, such as those formed on
the basis of size, value, investment, profitability, and momentum. In particular, a neural network with
three layers produces a positive out-of-sample predictive R2 for every factor portfolio we consider.
   More pronounced predictive power at the portfolio level versus the stock level is driven by the
fact that individual stock returns behave erratically for some of the smallest and least liquid stocks
in our sample. Aggregating into portfolios averages out much of the unpredictable stock-level noise
and boosts the signal strength, which helps in detecting the predictive gains from machine learning.
   The economic gains from machine learning forecasts are large. Our tests show clear statistical
rejections of the OLS benchmark and other linear models in favor of nonlinear machine learning
tools. The evidence for economic gains from machine learning forecasts—in the form of portfolio
Sharpe ratios—are likewise impressive. For example, an investor who times the S&P 500 based on
bottom-up neural network forecasts enjoys a 26 percentage point increase in annualized out-of-sample
Sharpe ratio, to 0.77, relative to the 0.51 Sharpe ratio of a buy-and-hold investor. And when we
form a long-short decile spread directly sorted on stock return predictions from a neural network, the
strategy earns an annualized out-of-sample Sharpe ratio of 1.35 (value-weighted) and 2.45 (equal-
weighted). In contrast, an analogous long-short strategy using forecasts from the benchmark OLS
model delivers Sharpe ratios of 0.61 and 0.83, respectively.
   The most successful predictors are price trends, liquidity, and volatility. All of the methods we
study produce a very similar ranking of the most informative stock-level predictors, which fall into
three main categories. First, and most informative of all, are price trend variables including stock
momentum, industry momentum, and short-term reversal. Next are liquidity variables including
market value, dollar volume, and bid-ask spread. Finally, return volatility, idiosyncratic volatility,
market beta, and beta squared are also among the leading predictors in all models we consider.
   Better understanding our machine learning findings through simulation. In Appendix A we per-
form Monte Carlo simulations that support the above interpretations of our analysis. We apply
machine learning to simulated data from two different data generating processes. Both produce data
from a high dimensional predictor set. But in one, individual predictors enter only linearly and ad-
ditively, while in the other predictors can enter through nonlinear transformations and via pairwise
interactions. When we apply our machine learning repertoire to the simulated datasets, we find that
linear and generalized linear methods dominate in the linear and uninteracted setting, yet tree-based
methods and neural networks significantly outperform in the nonlinear and interactive setting.




                                                  6
1.6     What Machine Learning Cannot Do
Machine learning has great potential for improving risk premium measurement, which is funda-
mentally a problem of prediction. It amounts to best approximating the conditional expectation
E(ri,t+1 |Ft ), where ri,t+1 is an asset’s return in excess of the risk-free rate, and Ft is the true and
unobservable information set of market participants. This is a domain in which machine learning
algorithms excel.
    But these improved predictions are only measurements. The measurements do not tell us about
economic mechanisms or equilibria. Machine learning methods on their own do not identify deep
fundamental associations among asset prices and conditioning variables. When the objective is to
understand economic mechanisms, machine learning may still be useful. It requires the economist to
add structure—to build a hypothesized mechanism into the estimation problem—and decide how to
introduce a machine learning algorithm subject to this structure. A nascent literature has begun to
make progress marrying machine learning with equilibrium asset pricing (for example, Kelly et al.,
2019; Feng et al., 2019), and this remains an exciting direction for future research.

1.7     Literature
Our work extends the empirical literature on stock return prediction, which comes in two basic
strands. The first strand models differences in expected returns across stocks as a function of stock-
level characteristics, and is exemplified by Fama and French (2008) and Lewellen (2015). The typical
approach in this literature runs cross-sectional regressions5 of future stock returns on a few lagged
stock characteristics. The second strand forecasts the time series of returns and is surveyed by
Koijen and Nieuwerburgh (2011) and Rapach and Zhou (2013). This literature typically conducts
time series regressions of broad aggregate portfolio returns on a small number of macroeconomic
predictor variables.
    These traditional methods have potentially severe limitations that more advanced statistical tools
in machine learning can help overcome. Most important is that regressions and portfolio sorts are
ill-suited to handle the large numbers of predictor variables that the literature has accumulated over
five decades. The challenge is how to assess the incremental predictive content of a newly proposed
predictor while jointly controlling for the gamut of extant signals (or, relatedly, handling the multiple
comparisons and false discovery problem). Our primary contribution is to demonstrate potent return
predictability that is harnessable from the large collection of existing variables when machine learning
methods are used.
    Machine learning methods have appeared sporadically in the asset pricing literature. Rapach
et al. (2013) apply lasso to predict global equity market returns using lagged returns of all countries.
Several papers apply neural-networks to forecast derivatives prices (Hutchinson et al., 1994; Yao
et al., 2000, among others). Khandani et al. (2010) and Butaru et al. (2016) use regression trees
to predict consumer credit card delinquencies and defaults. Sirignano et al. (2016) estimate a deep
   5
     In addition to least squares regression, the literature often sorts assets into portfolios on the basis of characteristics
and studies portfolio averages—a form of nonparametric regression.



                                                              7
neural network for mortgage prepayment, delinquency, and foreclosure. Heaton et al. (2016) develop
a neural network for portfolio selection.
    Recently, variations of machine learning methods have been used to study the cross section of
stock returns. Harvey and Liu (2016) study the multiple comparisons problem using a bootstrap
procedure. Giglio and Xiu (2016) and Kelly et al. (2019) use dimension reduction methods to estimate
and test factor pricing models. Moritz and Zimmermann (2016) apply tree-based models to portfolio
sorting. Kozak et al. (2019) and Freyberger et al. (2019) use shrinkage and selection methods to,
respectively, approximate a stochastic discount factor and a nonlinear function for expected returns.
The focus of our paper is to simultaneously explore a wide range of machine learning methods to
study the behavior of expected stock returns, with a particular emphasis on comparative analysis
among methods.


2    Methodology
This section describes the collection of machine learning methods that we use in our analysis. In
each subsection we introduce a new method and describe it in terms of its three fundamental ele-
ments. First is the statistical model describing a method’s general functional form for risk premium
predictions. The second is an objective function for estimating model parameters. All of our esti-
mates share the basic objective of minimizing mean squared predictions error (MSE). Regularization
is introduced through variations on the MSE objective, such as adding parameterization penalties
and robustification against outliers. These modifications are designed to avoid problems with overfit
and improve models’ out-of-sample predictive performance. Finally, even with a small number of
predictors, the set of model permutations expands rapidly when one considers nonlinear predictor
transformations. This proliferation is compounded in our already high dimension predictor set. The
third element in each subsection describes computational algorithms for efficiently identifying the
optimal specification among the permutations encompassed by a given method.
    As we present each method, we aim to provide a sufficiently in-depth description of the statistical
model so that a reader having no machine learning background can understand the basic model
structure without needing to consult outside sources. At the same time, when discussing the com-
putational methods for estimating each model, we are deliberately terse. There are many variants of
each algorithm, and each has its own subtle technical nuances. To avoid bogging down the reader
with programming details, we describe our specific implementation choices in Appendix B and refer
readers to original sources for further background. We also summarize the literature on statistical
properties of each estimator in Appendix C.
    In its most general form, we describe an asset’s excess return as an additive prediction error
model:
                                      ri,t+1 = Et (ri,t+1 ) + i,t+1 ,                             (1)

where
                                            Et (ri,t+1 ) = g ? (zi,t ).                            (2)


                                                        8
Stocks are indexed as i = 1, ..., Nt and months by t = 1, ..., T . For ease of presentation, we assume
a balanced panel of stocks, and defer the discussion on missing data to Section 3.1. Our objective is
to isolate a representation of Et (ri,t+1 ) as a function of predictor variables that maximizes the out-
of-sample explanatory power for realized ri,t+1 . We denote those predictors as the P -dimensional
vector zi,t , and assume the conditional expected return g ? (·) is a flexible function of these predictors.
    Despite its flexibility, this framework imposes some important restrictions. The g ? (·) function
depends neither on i nor t. By maintaining the same form over time and across different stocks, the
model leverages information from the entire panel which lends stability to estimates of risk premia
for any individual asset. This is in contrast to standard asset pricing approaches that re-estimate a
cross-sectional model each time period, or that independently estimate time series models for each
stock. Also, g ? (·) depends on z only through zi,t . This means our prediction does not use information
from the history prior to t, or from individual stocks other than the ith .

2.1    Sample Splitting and Tuning via Validation
Important preliminary steps (prior to discussing specific models and regularization approaches) are
to understand how we design disjoint sub-samples for estimation and testing and to introduce the
notion of “hyperparameter tuning.”
    The regularization procedures discussed below, which are machine learning’s primary defense
against overfitting, rely on a choice of hyperparameters (or, synonymously, “tuning parameters”).
These are critical to the performance of machine learning methods as they control model complexity.
Hyperparameters include, for example, the penalization parameters in lasso and elastic net, the
number of iterated trees in boosting, the number of random trees in a forest, and the depth of
the trees. In most cases, there is little theoretical guidance for how to “tune” hyperparameters for
optimized out-of-sample performance.6
    We follow the most common approach in the literature and select tuning parameters adaptively
from the data in a validation sample. In particular, we divide our sample into three disjoint time
periods that maintain the temporal ordering of the data. The first, or “training,” subsample is used
to estimate the model subject to a specific set of tuning parameter values.
    The second, or “validation,” sample is used for tuning the hyperparameters. We construct fore-
casts for data points in the validation sample based on the estimated model from the training sample.
Next, we calculate the objective function based on forecast errors from the validation sample, and iter-
atively search for hyperparameters that optimize the validation objective (at each step re-estimating
the model from the training data subject to the prevailing hyperparameter values).
    Tuning parameters are chosen from the validation sample taking into account estimated param-
eters, but the parameters are estimated from the training data alone. The idea of validation is to
simulate an out-of-sample test of the model. Hyperparameter tuning amounts to searching for a
degree of model complexity that tends to produce reliable out-of-sample performance. The valida-
tion sample fits are of course not truly out-of-sample because they are used for tuning, which is in
    6
      In machine learning, a “hyperparameter” governs the extent of estimator regularization. This usage is related to,
but different from, its meaning in Bayesian statistics as a parameter of a prior distribution.


                                                          9
turn an input to the estimation. Thus the third, or “testing,” subsample, which is used for neither
estimation nor tuning, is truly out-of-sample and thus is used to evaluate a method’s predictive
performance. Further details of our sample splitting scheme are provided in Appendix D, and a
summary of hyperparameter tuning schemes for each model is provided in Appendix E.

2.2     Simple Linear
We begin our model description with the least complex method in our analysis, the simple linear
predictive regression model estimated via ordinary least squares (OLS). While we expect this to
perform poorly in our high dimension problem, we use it as a reference point for emphasizing the
distinctive features of more sophisticated methods.
   Model. The simple linear model imposes that conditional expectations g ? (·) can be approxi-
mated by a linear function of the raw predictor variables and the parameter vector, θ,

                                                          0
                                           g(zi,t ; θ) = zi,t θ.                                   (3)

This model imposes a simple regression specification and does not allow for nonlinear effects or
interactions between predictors.
   Objective Function and Computational Algorithm. Our baseline estimation of the simple
linear model uses a standard least squares, or “l2 ”, objective function:

                                             N   T
                                         1 XX
                               L(θ) =         (ri,t+1 − g(zi,t ; θ))2 .                            (4)
                                        NT
                                            i=1 t=1

Minimizing L(θ) yields the pooled OLS estimator. The convenience of the baseline l2 objective func-
tion is that it offers analytical estimates and thus avoids sophisticated optimization and computation.

2.2.1    Extension: Robust Objective Functions

In some cases it is possible to improve predictive performance by replacing equation (4) with a
weighted least squares objective such as

                                            N    T
                                      1 XX
                            LW (θ) =       wi,t (ri,t+1 − g(zi,t ; θ))2 .                          (5)
                                     NT
                                           i=1 t=1

This allows the econometrician to tilt estimates towards observations that are more statistically or
economically informative. For example, one variation that we consider sets wi,t inversely proportional
to the number of stocks at time t. This imposes that every month has the same contribution to
the model regardless of how many stocks are available that month. This also amounts to equally
weighting the squared loss of all stocks available at time t. Another variation that we consider sets
wi,t proportional to the equity market value of stock i at time t. This value weighted loss function
underweights small stocks in favor of large stocks, and is motivated by the economic rational that



                                                     10
small stocks represent a large fraction of the traded universe by count while constituting a tiny
fraction of aggregate market capitalization.7
    Heavy tails are a well known attribute of financial returns and stock-level predictor variables.
Convexity of the least squares objective (4) places extreme emphasis on large errors, thus outliers
can undermine the stability of OLS-based predictions. The statistics literature, long aware of this
problem, has developed modified least squares objective functions that tend to produce more stable
forecasts than OLS in the presence of extreme observations.8 In the machine learning literature,
a common choice for counteracting the deleterious effect of heavy-tailed observations is the Huber
robust objective function, defined as

                                                    N      T
                                             1 XX
                                 LH (θ) =         H (ri,t+1 − g(zi,t ; θ), ξ) ,                                      (6)
                                            NT
                                                  i=1 t=1

where                                           (
                                                    x2 ,                if   |x| ≤ ξ;
                                   H(x; ξ) =                        2
                                                                                        .
                                                    2ξ|x| − ξ ,         if   |x| > ξ.

The Huber loss, H(·), is a hybrid of squared loss for relatively small errors and absolute loss for
relatively large errors, where the combination is controlled by a tuning parameter, ξ, that can be
optimized adaptively from the data.9
    While this detour introduces robust objective functions in the context of the simple linear model,
they are easily applicable in almost all of the methods that we study. In our empirical analysis we
study the predictive benefits of robust loss functions in multiple machine learning methods.

2.3     Penalized Linear
The simple linear model is bound to fail in the presence of many predictors. When the number
of predictors P approaches the number of observations T , the linear model becomes inefficient or
even inconsistent.10 It begins to overfit noise rather than extracting signal. This is particularly
troublesome for the problem of return prediction where the signal-to-noise ratio is notoriously low.
    Crucial for avoiding overfit is reducing the number of estimated parameters. The most common
machine learning device for imposing parameter parsimony is to append a penalty to the objective
function in order to favor more parsimonious specifications. This “regularization” of the estimation
problem mechanically deteriorates a model’s in-sample performance in hopes that it improves its
stability out-of-sample. This will be the case when penalization manages to reduce the model’s fit
   7
      As of Fama and French (2008), the smallest 20% of stocks comprise only 3% of aggregate market capitalization.
An example of a statistically motivated weighting scheme uses wi,t inversely proportional to an observation’s estimated
error variance, a choice that potentially improves prediction efficiency in the spirit of generalized least squares.
    8
      Classical analyses include Box (1953), Tukey (1960), and Huber (1964).
    9
      OLS is a special case of the (6) with ξ = ∞. While most theoretical analysis in high-dimensional statistics assume
that data have sub-Gaussian or sub-exponential tails, Fan et al. (2017) provide a theoretical justification of using this
loss function in the high-dimensional setting as well as a procedure to determine the hyperparameter.
   10
      We deliberately compare P with T , instead of with N T , because stock returns share strong cross-sectional depen-
dence, limiting the incremental information contained in new cross-section observations.



                                                               11
of noise while preserving its fit of the signal.
   Objective Function and Computational Algorithm. The statistical model for our penalized
linear model is the same as the simple linear model in equation (3). That is, it continues to consider
only the baseline, untransformed predictors. Penalized methods differ by appending a penalty to the
original loss function:

                                         L(θ; ·) =L(θ) + φ(θ; ·).                                   (7)

There are several choices for the penalty function φ(θ; ·). We focus on the popular “elastic net”
penalty, which takes the form

                                                       P               P
                                                       X            1 X 2
                               φ(θ; λ, ρ) = λ(1 − ρ)         |θj | + λρ θj .                        (8)
                                                                    2
                                                       j=1            j=1


The elastic net involves two non-negative hyperparameters, λ and ρ, and includes two well known
regularizers as special cases. The ρ = 0 case corresponds to the lasso and uses an absolute value,
or “l1 ”, parameter penalization. The fortunate geometry of the lasso sets coefficients on a subset
of covariates to exactly zero. In this sense, the lasso imposes sparsity on the specification and can
thus be thought of as a variable selection method. The ρ = 1 case corresponds to ridge regression,
which uses an l2 parameter penalization, that draws all coefficient estimates closer to zero but does
not impose exact zeros anywhere. In this sense, ridge is a shrinkage method that helps prevent
coefficients from becoming unduly large in magnitude. For intermediate values of ρ, the elastic net
encourages simple models through both shrinkage and selection.
   We adaptively optimize the tuning parameters, λ and ρ, using the validation sample. Our imple-
mentation of penalized regression uses the accelerated proximal gradient algorithm and accommo-
dates both least squares and Huber objective functions (see Appendix B.1 for more detail).

2.4   Dimension Reduction: PCR and PLS
Penalized linear models use shrinkage and variable selection to manage high dimensionality by forcing
the coefficients on most regressors near or exactly to zero. This can produce suboptimal forecasts
when predictors are highly correlated. A simple example of this problem is a case in which all of the
predictors are equal to the forecast target plus an iid noise term. In this situation, choosing a subset
of predictors via lasso penalty is inferior to taking a simple average of the predictors and using this
as the sole predictor in a univariate regression.
   The idea of predictor averaging, as opposed to predictor selection, is the essence of dimension
reduction. Forming linear combinations of predictors helps reduce noise to better isolate the signal in
predictors, and also helps de-correlate otherwise highly dependent predictors. Two classic dimension
reduction techniques are principal components regression (PCR) and partial least squares (PLS).
   PCR consists of a two-step procedure. In the first step, principal components analysis (PCA)
combines regressors into a small set of linear combinations that best preserve the covariance structure


                                                    12
among the predictors. In the second step, a few leading components are used in standard predictive
regression. That is, PCR regularizes the prediction problem by zeroing out coefficients on low
variance components.
    A drawback of PCR is that it fails to incorporate the ultimate statistical objective—forecasting
returns—in the dimension reduction step. PCA condenses data into components based on the covari-
ation among the predictors. This happens prior to the forecasting step and without consideration of
how predictors associate with future returns.
    In contrast, partial least squares performs dimension reduction by directly exploiting covariation
of predictors with the forecast target.11 PLS regression proceeds as follows. For each predictor j,
estimate its univariate return prediction coefficient via OLS. This coefficient, denoted ϕj , reflects the
“partial” sensitivity of returns to each predictor j. Next, average all predictors into a single aggregate
component with weights proportional to ϕj , placing the highest weight on the strongest univariate
predictors, and the least weight on the weakest. In this way, PLS performs its dimension reduction
with the ultimate forecasting objective in mind. To form more than one predictive component, the
target and all predictors are orthogonalized with respect to previously constructed components, and
the above procedure is repeated on the orthogonalized dataset. This is iterated until the desired
number of PLS components is reached.
    Model. Our implementation of PCR and PLS begins from the vectorized version of the linear
                                                                                         0 θ+
model in equations (1)–(3). In particular, we reorganize the linear regression ri,t+1 = zi,t   i,t+1 as


                                                        R = Zθ + E,                                                          (9)

where R is the N T × 1 vector of ri,t+1 , Z is the N T × P matrix of stacked predictors zi,t , and E is
a N T × 1 vector of residuals i,t+1 .
    PCR and PLS take the same general approach to reducing the dimensionality. They both con-
dense the set of predictors from dimension P to a much smaller number of K linear combinations of
predictors. Thus, the forecasting model for both methods is written as

                                                   R = (ZΩK )θK + Ẽ.                                                      (10)

ΩK is P × K matrix with columns w1 , w2 , . . . , wK . Each wj is the set of linear combination weights
used to create the j th predictive components, thus ZΩK is the dimension-reduced version of the
original predictor set. Likewise, the predictive coefficient θK is now a K × 1 vector rather than P × 1.
    Objective Function and Computational Algorithm. PCR chooses the combination weights
ΩK recursively. The j th linear combination solves12

           wj = arg max Var(Zw),            s.t. w0 w = 1,          Cov(Zw, Zwl ) = 0,        l = 1, 2, . . . , j − 1.     (11)
                         w
   11
      See Kelly and Pruitt (2013, 2015) for asymptotic theory of PLS regression and its application to forecasting risk
premia in financial markets.
   12
      For two vectors a and b, we denote Cov(a, b) := (a − ā)| (b − b̄), where ā is the average of all entries of a. Naturally,
we define Var(a) := Cov(a, a).



                                                               13
Intuitively, PCR seeks the K linear combinations of Z that most faithfully mimic the full predictor
set. The objective illustrates that the choice of components is not based on the forecasting objective
at all. Instead, the emphasis of PCR is on finding components that retain the most possible common
variation within the predictor set. The well known solution for (11) computes ΩK via singular value
decomposition of Z, and therefore the PCR algorithm is extremely efficient from a computational
standpoint.
   In contrast to PCR, the PLS objective seeks K linear combinations of Z that have maximal
predictive association with the forecast target. The weights used to construct j th PLS component
solve

       wj = arg max Cov2 (R, Zw),           s.t. w0 w = 1,          Cov(Zw, Zwl ) = 0,          l = 1, 2, . . . , j − 1.   (12)
                   w

This objective highlights the main distinction between PCR and PLS. PLS is willing to sacrifice how
accurately ZΩK approximates Z in order to find components with more potent return predictability.
The problem in (12) can be efficiently solved using a number of similar routines, the most prominent
being the SIMPLS algorithm of de Jong (1993).
   Finally, given a solution for ΩK , θK is estimated in both PCR and PLS via OLS regression of
R on ZΩK . For both models, K is a hyperparameter that can be determined adaptively from the
validation sample.

2.5      Generalized Linear
Linear models are popular in practice, in part because they can be thought of as a first-order approxi-
mation to the data generating process.13 When the “true” model is complex and nonlinear, restricting
the functional form to be linear introduces approximation error due to model misspecification. Let
g ? (zi,t ) denote the true model and g(zi,t ; θ) the functional form specified by the econometrician. And
let g(zi,t ; bθ) and rbi,t+1 denote the fitted model and its ensuing return forecast. We can decompose a
model’s forecast error as:

              ri,t+1 − rbi,t+1 = g ? (zi,t ) − g(zi,t ; θ) +        g(zi,t ; θ) − g(zi,t ; b
                                                                                           θ)   +        i,t+1     .
                                 |           {z          }          |           {z          }            | {z }
                                approximation error                   estimation error              intrinsic error

Intrinsic error is irreducible; it is the genuinely unpredictable component of returns associated with
news arrival and other sources of randomness in financial markets. Estimation error, which arises
due to sampling variation, is determined by the data. It is potentially reducible by adding new
observations, though this may not be under the econometrician’s control. Approximation error
is directly controlled by the econometrician, and is potentially reducible by incorporating more
flexible specifications that improve the model’s ability to approximate the true model. But additional
flexibility raises the risk of overfitting and destabilizing the model out-of-sample. In this and the
following subsections, we introduce nonparametric models of g(·) with increasing degrees of flexibility,
  13
       See White (1980) for a discussion of limitations of linear models as first-order approximations.



                                                               14
each complemented by regularization methods to mitigate overfit.
    Model. The first and most straightforward nonparametric approach that we consider is the
generalized linear model. It introduces nonlinear transformations of the original predictors as new
additive terms in an otherwise linear model. Generalized linear models are thus the closest nonlinear
counterparts to the linear approaches in Sections 2.2 and 2.3.
    The model we study adapts the simple linear form by adding a K-term spline series expansion
of the predictors
                                                              P
                                                              X
                                            g(z; θ, p(·)) =         p(zj )0 θj ,                                    (13)
                                                              j=1

where p(·) = (p1 (·), p2 (·), . . . , pK (·))0 is a vector of basis functions, and the parameters are now a
K × N matrix θ = (θ1 , θ2 , . . . , θN ). There are many potential choices for spline functions. We adopt
a spline series of order two: 1, z, (z − c1 )2 , (z − c2 )2 , . . . , (z − cK−2 )2 , where c1 , c2 , . . . cK−2 are
                                                                                  

knots.
    Objective Function and Computational Algorithm. Because higher order terms enter
additively, forecasting with the generalized linear model can be approached with the same estimation
tools as in Section 2.2. In particular, our analysis uses a least squares objective function, both with
and without the Huber robustness modification. Because series expansion quickly multiplies the
number of model parameters, we use penalization to control degrees of freedom. Our choice of
penalization function is specialized for the spline expansion setting and is known as the group lasso.
It takes the form                                                              !1/2
                                                          P
                                                          X K
                                                            X
                                        φ(θ; λ, K) = λ                 θ2j,k          .                             (14)
                                                          j=1   k=1

As its name suggests, the group lasso selects either all K spline terms associated with a given
characteristic or none of them. We embed this penalty in the general objective of equation (7).
Group lasso accommodates either least squares or robust Huber objective, and it uses the same
accelerated proximal gradient descent as the elastic net. It has two tuning parameters, λ and K.14

2.6      Boosted Regression Trees and Random Forests
The model in (13) captures individual predictors’ nonlinear impact on expected returns, but does not
account for interactions among predictors. One way to add interactions is to expand the generalized
model to include multivariate functions of predictors. While expanding univariate predictors with
K basis functions multiplies the number of parameters by a factor of K, multi-way interactions
increase the parameterization combinatorially. Without a priori assumptions for which interactions
to include, the generalized linear model becomes computationally infeasible.15
   14
      For additional details, see Appendix B.1. A similar model in the return prediction context is Freyberger et al.
(2019).
   15
      Parameter penalization does not solve the difficulty of estimating linear models when the number of predictors is
exponentially larger than the number of observations. Instead, one must turn to heuristic optimization algorithms such
as stepwise regression (sequentially adding/dropping variables until some stopping rule is satisfied), variable screening
(retaining predictors whose univariate correlations with the prediction target exceed a certain value), or others.



                                                           15
                                            Figure 1: Regression Tree Example
                                                                                            1
                                     Size
                                     <0.5
                              True          False
                                                                                                                Category 3
               Value                                Category
              Value>0.4
                <0.3                                    3
                                                                                    Size   0.5
       True               False




   Category               Category                                                               Category 1             Category 2
       1                      2



                                                                                            0             0.3       Value            1



Note: This figure presents the diagrams of a regression tree (left) and its equivalent representation (right) in
the space of two characteristics (size and value). The terminal nodes of the tree are colored in blue, yellow,
and red, respectively. Based on their values of these two characteristics, the sample of individual stocks is
divided into three categories.


   As an alternative, regression trees have become a popular machine learning approach for incor-
porating multi-way predictor interactions. Unlike linear models, trees are fully nonparametric and
possess a logic that departs markedly from traditional regressions. At a basic level, trees are de-
signed to find groups of observations that behave similarly to each. A tree “grows” in a sequence
of steps. At each step, a new “branch” sorts the data leftover from the preceding step into bins
based on one of the predictor variables. This sequential branching slices the space of predictors into
rectangular partitions, and approximates the unknown function g ? (·) with the average value of the
outcome variable within each partition.
   Figure 1 shows an example with two predictors, “size” and “b/m.” The left panel describes how
the tree assigns each observation to a partition based on its predictor values. First, observations are
sorted on size. Those above the breakpoint of 0.5 are assigned to Category 3. Those with small size
are then further sorted by b/m. Observations with small size and b/m below 0.3 are assigned to
Category 1, while those with b/m above 0.3 go into Category 2. Finally, forecasts for observations in
each partition are defined as the simple average of the outcome variable’s value among observations
in that partition.
   Model. More formally, the prediction of a tree, T , with K “leaves” (terminal nodes), and depth
L, can be written as

                                                                  K
                                                                  X
                                            g(zi,t ; θ, K, L) =         θk 1{zi,t ∈Ck (L)} ,                                         (15)
                                                                  k=1

where Ck (L) is one of the K partitions of the data. Each partition is a product of up to L indicator
functions of the predictors. The constant associated with partition k (denoted θk ) is defined to be



                                                                  16
the sample average of outcomes within the partition.16 In the example of Figure 1, the prediction
equation is

        g(zi,t ; θ, 3, 2) = θ1 1{sizei,t <0.5} 1{b/mi,t <0.3} + θ2 1{sizei,t <0.5} 1{b/mi,t ≥0.3} + θ3 1{sizei,t ≥0.5} .

    Objective Function and Computational Algorithm. To grow a tree is to find bins that best
discriminate among the potential outcomes. The specific predictor variable upon which a branch
is based, and the specific value where the branch is split, is chosen to minimize forecast error.
The expanse of potential tree structures, however, precludes exact optimization. The literature has
developed a set of sophisticated optimization heuristics to quickly converge on approximately optimal
trees. We follow the algorithm of Breiman et al. (1984), which we describe in detail in Appendix
B.2. The basic idea is to myopically optimize forecast error at the start of each branch. At each
new level, we choose a sorting variable from the set of predictors and the split value to maximize the
discrepancy among average outcomes in each bin.17 The loss associated with the forecast error for
a branch C is often called “impurity,” which describes how similarly observations behave on either
side of the split. We choose the most popular l2 impurity for each branch of the tree:

                                                         1 X
                                           H(θ, C) =         (ri,t+1 − θ)2 ,                                               (16)
                                                        |C|
                                                             zi,t ∈C


where |C| denotes the number of observations in set C. Given C, it is clear that the optimal choice of
        1 P
θ: θ = |C|  zi,t ∈C ri,t+1 . The procedure is equivalent to finding the branch C that locally minimizes
the impurity. Branching halts when the number of leaves or the depth of the tree reach a pre-specified
threshold that can be selected adaptively using a validation sample.
    Among the advantages of a tree model are that it is invariant to monotonic transformations of
predictors, that it naturally accommodates categorical and numerical data in the same model, that
it can approximate potentially severe nonlinearities, and that a tree of depth L can capture (L − 1)-
way interactions. Their flexibility is also their limitation. Trees are among the prediction methods
most prone to overfit, and therefore must be heavily regularized. In our analysis, we consider two
“ensemble” tree regularizers that combine forecasts from many different trees into a single forecast.18
    Boosting. The first regularization method is “boosting,” which recursively combines forecasts
from many over-simplified trees.19 Shallow trees on their own are “weak learners” with minuscule
predictive power. The theory behind boosting suggests that many weak learners may, as an ensemble,
comprise a single “strong learner” with greater stability than a single complex tree.
   16
       We focus on recursive binary trees for their relative simplicity. Breiman et al. (1984) discuss more complex tree
structures.
    17
       Because splits are chosen without consideration of future potential branches, it is possible to myopically bypass
an inferior branch that would have led to a future branch with an ultimately superior reduction in forecast error.
    18
       The literature also considers a number of other approaches to tree regularization such as early stopping and post-
pruning, both of which are designed to reduce overfit in a single large tree. Ensemble methods demonstrate more
reliable performance and are scalable for very large datasets, leading to their increased popularity in recent literature.
    19
       Boosting is originally described in Schapire (1990) and Freund (1995) for classification problems to improve the
performance of a set of weak learners. Friedman et al. (2000a) and Friedman (2001) extend boosting to contexts beyond
classification, eventually leading to the gradient boosted regression tree.


                                                              17
   The details of our boosting procedure, typically referred to as gradient boosted regression trees
(GBRT), are described in Algorithm 4 of Appendix B.2. It starts by fitting a shallow tree (e.g., with
depth L = 1). This over-simplified tree is sure to be a weak predictor with large bias in the training
sample. Next, a second simple tree (with the same shallow depth L) is used to fit the prediction
residuals from the first tree. Forecasts from these two trees are added together to form an ensemble
prediction of the outcome, but the forecast component from the second tree is shrunken by a factor
ν ∈ (0, 1) to help prevent the model from overfitting the residuals. At each new step b, a shallow tree
is fitted to the residuals from the model with b−1 trees, and its residual forecast is added to the total
with a shrinkage weight of ν. This is iterated until there are a total of B trees in the ensemble. The
final output is therefore an additive model of shallow trees with three tuning parameters (L, ν, B)
which we adaptively choose in the validation step.
   Random Forest. Like boosting, a random forest is an ensemble method that combines forecasts
from many different trees. It is a variation on a more general procedure known as bootstrap aggrega-
tion, or “bagging” (Breiman, 2001). The baseline tree bagging procedure draws B different bootstrap
samples of the data, fits a separate regression tree to each, then averages their forecasts. Trees for
individual bootstrap samples tend to be deep and overfit, making their individual predictions in-
efficiently variable. Averaging over multiple predictions reduces this variation, thus stabilizing the
trees’ predictive performance.
   Random forests use a variation on bagging designed to reduce the correlation among trees in
different bootstrap samples. If, for example, firm size is the dominant return predictor in the data,
then most of the bagged trees will have low-level splits on size resulting in substantial correlation
among their ultimate predictions. The forest method de-correlates trees using a method known as
“dropout,” which considers only a randomly drawn subset of predictors for splitting at each potential
branch. Doing so ensures that, in the example, early branches for at least a few trees will split on
characteristics other than firm size. This lowers the average correlation among predictions to further
improve the variance reduction relative to standard bagging. Depth L of the trees and number
of bootstrap samples B are the tuning parameters optimized via validation. Precise details of our
random forest implementation are described in Algorithm 3 of the appendix.

2.7   Neural Networks
The final nonlinear method that we analyze is the artificial neural network. Arguably the most
powerful modeling device in machine learning, neural networks have theoretical underpinnings as
“universal approximators” for any smooth predictive association (Hornik et al., 1989; Cybenko,
1989). They are the currently preferred approach for complex machine learning problems such as
computer vision, natural language processing, and automated game-playing (such as chess and go).
Their flexibility draws from the ability to entwine many telescoping layers of nonlinear predictor
interactions, earning the synonym “deep learning.” At the same time, their complexity ranks neural
networks among the least transparent, least interpretable, and most highly parameterized machine
learning tools.


                                                   18
                                        Figure 2: Neural Networks

  Output Layer                                          Output Layer




                                                        Hidden Layer        f      f     f      f      f




  Input Layer                                           Input Layer




Note: This figure provides diagrams of two simple neural networks with (right) or without (left) a hidden layer.
Pink circles denote the input layer and dark red circles denote the output layer. Each arrow is associated
with a weight parameter. In the network with a hidden layer, a nonlinear activation function f transforms
the inputs before passing them on to the output.


   Model. We focus our analysis on traditional “feed-forward” networks. These consist of an “input
layer” of raw predictors, one or more “hidden layers” that interact and nonlinearly transform the
predictors, and an “output layer” that aggregates hidden layers into an ultimate outcome prediction.
Analogous to axons in a biological brain, layers of the networks represent groups of “neurons” with
each layer connected by “synapses” that transmit signals among neurons of different layers. Figure
2 shows two illustrative examples.
   The number of units in the input layer is equal to the dimension of the predictors, which we
set to four in this example (denoted z1 , ..., z4 ). The left panel shows the simplest possible network
that has no hidden layers. Each of the predictor signals is amplified or attenuated according to
a five-dimensional parameter vector, θ, that includes an intercept and one weight parameter per
predictor. The output layer aggregates the weighted signals into the forecast θ0 + 4k=1 zk θk ; that
                                                                                  P

is, the simplest neural network is a linear regression model.
   The model incorporates more flexible predictive associations by adding hidden layers between
the inputs and output. The right panel of Figure 2 shows an example with one hidden layer that
contains five neurons. Each neuron draws information linearly from all of the input units, just as in
the simple network on the left. Then, each neuron applies a nonlinear “activation function” f to its
aggregated signal before sending its output to the next layer.
                                                             For example, thesecond neuron in the
                                                    (1)        (0) P4       (0)
hidden layer transforms inputs into an output as x2 = f θ2,0 + j=1 zj θ2,j . Lastly, the results
from each neuron are linearly aggregated into an ultimate output forecast:

                                                           5
                                                   (1)            (1) (1)
                                                           X
                                        g(z; θ) = θ0 +           xj θ j .
                                                           j=1


Thus, in this example, there are a total of 31= (4 + 1) × 5 + 6 parameters (five parameters to reach


                                                      19
each neuron and six weights to aggregate the neurons into a single output).
    There are many choices to make when structuring a neural network, including the number of
hidden layers, the number of neurons in each layer, and which units are connected. Despite the
aforementioned “universal approximation” result that suggests the sufficiency of a single hidden
layer, recent literature has shown that deeper networks can often achieve the same accuracy with
substantially fewer parameters.20
    On the other hand, in small data sets simple networks with only a few layers and nodes often
perform best. Training a very deep neural network is challenging because it typically involves a
large number of parameters, because the objective function is highly non-convex, and because the
recursive calculation of derivatives (known as “back-propagation”) is prone to exploding or vanishing
gradients.
    Selecting a successful network architecture by cross-validation is in general a difficult task. It
is unrealistic and unnecessary to find the optimal network by searching over uncountably many
architectures. Instead, we fix a variety of network architectures ex ante and estimate each of these.
What we hope to achieve is reasonably lower bound on the performance of machine learning methods.
    We consider architectures with up to five hidden layers. Our shallowest neural network has a
single hidden layer of 32 neurons, which we denoted NN1. Next, NN2 has two hidden layers with 32
and 16 neurons, respectively; NN3 has three hidden layers with 32, 16, and 8 neurons, respectively;
NN4 has four hidden layers with 32, 16, 8, 4 neurons, respectively; and NN5 has five hidden layers
with 32, 16, 8, 4, and 2 neurons, respectively. We choose the number of neurons in each layer
according to the geometric pyramid rule (see Masters, 1993). All architectures are fully connected
so each unit receives an input from all units in the layer below. By comparing the performance of
NN1 through NN5, we can infer the trade-offs of network depth in the return forecasting problem.21
    There are many potential choices for the nonlinear activation function (such as sigmoid, hy-
perbolic, softmax, etc.). We use the same activation function at all nodes, and choose a popular
functional form in recent literature known as the rectified linear unit (ReLU), defined as22
                                                     
                                                     0           if x < 0
                                           ReLU(x) =
                                                     x          otherwise,

which encourages sparsity in the number of active neurons, and allows for faster derivative evaluation.
    Our neural network model has the following general formula. Let K (l) denote the number of
                                                                                                 (l)
neurons in each layer l = 1, ..., L. Define the output of neuron k in layer l as xk . Next, define the
                                                                                 (l)                   (l)    (l)
vector of outputs for this layer (augmented to include a constant, x0 ) as x(l) = (1, x1 , ..., xK (l) )0 . To
initialize the network, similarly define the input layer using the raw predictors, x(0) = (1, z1 , ..., zN )0 .
   20
      Eldan and Shamir (2016) formally demonstrate that depth—even if increased by one layer—can be exponentially
more valuable than increasing width in standard feed-forward neural networks. Ever since the seminal work by Hinton
et al. (2006), the machine learning community has experimented and adopted deeper (and wider) networks, with as
many as 152 layers for image recognition, e.g., He et al. (2016a).
   21
      We confine the choices of architectures to a small set of five based on our limited sample size (compared to typical
neural network applications).
   22
      See, e.g., Jarrett et al. (2009), Nair and Hinton (2010), and Glorot et al. (2011).


                                                           20
The recursive output formula for the neural network at each neuron in layer l > 0 is then
                                                         0 (l−1)
                                                                  
                                           (l)
                                          xk = ReLU x(l−1) θk       ,                                           (17)

with final output

                                                               0
                                             g(z; θ) = x(L−1) θ(L−1) .                                          (18)

The number of weight parameters in each hidden layer l is K (l) (1 + K (l−1) ), plus another 1 + K (L−1)
weights for the output layer.
    Objective Function and Computational Algorithm. We estimate the neural network
weight parameters by minimizing the penalized l2 objective function of prediction errors. Unlike
tree-based algorithms that require “greedy” optimization, training a neural network, in principle,
allows for joint updates of all model parameters at each step of the optimization—a substantial
advantage of neural networks over trees. However, the high degree of nonlinearity and nonconvexity
in neural networks, together with their rich parameterization, make brute force optimization highly
computationally intensive (often to the point of infeasibility). A common solution uses stochas-
tic gradient descent (SGD) to train a neural network. Unlike standard descent that uses the entire
training sample to evaluate the gradient at each iteration of the optimization, SGD evaluates the gra-
dient from a small random subset of the data. This approximation sacrifices accuracy for enormous
acceleration of the optimization routine.
    For the same reasons described above (severe nonlinearity and heavy parameterization), regular-
ization of neural networks requires more care than the methods discussed above. In addition to l1
penalization of the weight parameters, we simultaneously employ four other regularization techniques
in our estimation: learning rate shrinkage, early stopping, batch normalization, and ensembles.
    A critical tuning parameter in SGD is the learning rate, which controls the step size of the
descent. It is necessary to shrink the learning rate toward zero as the gradient approaches zero,
otherwise noise in the calculation of the gradient begins to dominate its directional signal. We adopt
the “learning rate shrinkage” algorithm of Kingma and Ba (2014) to adaptively control the learning
rate (described further in Algorithm 5 of the Appendix B.3).23
    Next, “early stopping” is a general machine learning regularization tool. It begins from an initial
parameter guess that imposes parsimonious parameterization (for example, setting all θ values close
to zero). In each step of the optimization algorithm, the parameter guesses are gradually updated to
reduce prediction errors in the training sample. At each new guess, predictions are also constructed
for the validation sample, and the optimization is terminated when the validation sample errors begin
to increase. This typically occurs before the prediction errors are minimized in the training sample,
hence the name early stopping (see Algorithm 6). By ending the parameter search early, parameters
are shrunken toward the initial guess. It is a popular substitute to l2 penalization of θ parameters
  23
     Relatedly, random subsetting at each SGD iteration adds noise to the optimization procedure, which itself serves
as a form of regularization. See, Wilson and Martinez (2003).




                                                         21
because it achieves regularization at a much lower computational cost.24 Early stopping can be used
alone, or together with l1 -regularization as we do in this paper.
    “Batch normalization” (Ioffe and Szegedy, 2015) is a simple technique for controlling the variabil-
ity of predictors across different regions of the network and across different datasets. It is motivated
by the phenomenon of internal covariate shift in which inputs of hidden layers follow different distri-
butions than their counterparts in the validation sample. This issue is constantly encountered when
fitting deep neural networks that involve many parameters and rather complex structures. For each
hidden unit in each training step (a “batch”), the algorithm cross-sectionally de-means and variance
standardizes the batch inputs to restore the representation power of the unit.
    Finally, we adopt an ensemble approach in training our neural networks (see also Hansen and
Salamon, 1990; Dietterich, 2000). In particular, we use multiple random seeds to initialize neural
network estimation and construct predictions by averaging forecasts from all networks. This reduces
prediction variance because the stochastic nature of the optimization can cause different seeds to
produce different forecasts.25

2.8    Performance Evaluation
To assess predictive performance for individual excess stock return forecasts, we calculate the out-
of-sample R2 as
                                                                                     2
                                                   P
                                      2               (i,t)∈T3 (ri,t+1 − rbi,t+1 )
                                     Roos =1−             P            2                 ,                        (19)
                                                             (i,t)∈T3 ri,t+1

where T3 indicates that fits are only assessed on the testing subsample, whose data never enter into
                             2
model estimation or tuning. Roos pools prediction errors across firms and over time into a grand
panel-level assessment of each model.
    A subtle but important aspect of our R2 metric is that the denominator is the sum of squared
excess returns without demeaning. In many out-of-sample forecasting applications, predictions are
compared against historical mean returns. While this approach is sensible for the aggregate index or
long-short portfolios, for example, it is flawed when it comes to analyzing individual stock returns.
Predicting future excess stock returns with historical averages typically underperforms a naive fore-
cast of zero by a large margin. That is, the historical mean stock return is so noisy that it artificially
lowers the bar for “good” forecasting performance. We avoid this pitfall by benchmarking our R2
against a forecast value of zero. To give an indication of the importance of this choice, when we
benchmark model predictions against historical mean stock returns, the out-of-sample monthly R2
of all methods rises by roughly three percentage points.
  24
      Early stopping bears a comparatively low computation cost because it only partially optimizes, while the l2 -
regularization, or more generally elastic net, search across tuning parameters and fully optimizes the model subject to
each tuning parameter guess. As usual, elastic net’s l1 -penalty component encourages neurons to connect to limited
number of other neurons, while its l2 -penalty component shrinks the weight parameters toward zero (a feature known
in the neural net literature as “weight-decay”). In certain circumstances, early stopping and weight-decay are shown
to be equivalent. See, e.g., Bishop (1995) and Goodfellow et al. (2016).
   25
      Estimation with different seeds can run independently in parallel which limits incremental computing time.



                                                          22
       To make pairwise comparisons of methods, we use the Diebold and Mariano (1995) test for
differences in out-of-sample predictive accuracy between two models.26 While time series dependence
in returns is sufficiently weak, it is unlikely that the conditions of weak error dependence underlying
the Diebold-Mariano test apply to our stock-level analysis due of potentially strong dependence in
the cross section. We adapt Diebold-Mariano to our setting by comparing the cross-sectional average
of prediction errors from each model, instead of comparing errors among individual returns. More
precisely, to test the forecast performance of method (1) versus (2), we define the test statistic
DM12 = d¯12 /bσ ¯ , where
                     d12

                                                     n3                    2 
                                               1     X       (1)
                                                                  2 
                                                                       (2)
                                d12,t+1 =                  ebi,t+1 − ebi,t+1      ,                               (20)
                                            n3,t+1
                                                     i=1

 (1)           (2)
ebi,t+1 and ebi,t+1 denote the prediction error for stock return i at time t using each method, and
n3,t+1 is the number of stocks in the testing sample (year t + 1). Then d¯12 and σ   b ¯ denote the  d12
mean and Newey-West standard error of d12,t over the testing sample. This modified Diebold-
Mariano test statistic, which is now based on a single time series d12,t+1 of error differences with
little autocorrelation, is more likely to satisfy the mild regularity conditions needed for asymptotic
normality and in turn provide appropriate p-values for our model comparison tests.

2.9      Variable Importance and Marginal Relationships
Our goal in interpreting machine learning models is modest. We aim to identify covariates that have
an important influence on the cross-section of expected returns while simultaneously controlling for
the many other predictors in the system.
       We discover influential covariates by ranking them according to a notion of variable importance,
which we denote as VIj for the j th input variable. We consider two different notions of importance.
The first is the reduction in panel predictive R2 from setting all values of predictor j to zero, while
holding the remaining model estimates fixed (used, for example, in the context of dimension reduction
by Kelly et al., 2019). The second, proposed in the neural networks literature by Dimopoulos et al.
(1995), is the sum of squared partial derivatives (SSD) of the model to each input variable j, which
summarizes the sensitivity of model fits to changes in that variable.27
       As part of our analysis, we also trace out the marginal relationship between expected returns
   26
      As emphasize by Diebold (2015), the model-free nature of the Diebold-Mariano test means that it should be
interpreted as a comparison of forecasts, and not as a comparison of “fully articulated econometric models.”
   27
      In particular, SSD defines the j th variable importance as
                                                                            !2
                                                      X     ∂g(z; θ)
                                            SSDj =                             ,
                                                     i,t∈T
                                                               ∂zj   z=zi,t
                                                       1


where, with a slight abuse of notation, zj in the denominator of the derivative denotes the j th element of the vector
of input variables. We measure SSD within the training set, T1 . Note that due to non-differentiabilities in tree-based
models, the Dimopoulos et al. (1995) method is not applicable. Therefore, when we conduct this second variable
importance analysis, we measure variable importance for random forests and boosted trees using mean decrease in
impurity (see, e.g., Friedman, 2001).



                                                           23
and each characteristic. Despite obvious limitations, such a plot is an effective tool for visualizing
the first-order impact of covariates in a machine learning model.


3        An Empirical Study of US Equities
3.1      Data and Over-arching Model
We obtain monthly total individual equity returns from CRSP for all firms listed in the NYSE,
AMEX, and NASDAQ. Our sample begins in March 1957 (the start date of the S&P 500) and ends
in December 2016, totaling 60 years. The number of stocks in our sample is almost 30,000, with
the average number of stocks per month exceeding 6,200.28 We also obtain the Treasury-bill rate to
proxy for the risk-free rate from which we calculate individual excess returns.
     In addition, we build a large collection of stock-level predictive characteristics based on the cross
section of stock returns literature. These include 94 characteristics29 (61 of which are updated
annually, 13 updated quarterly, and 20 updated monthly). In addition, we include 74 industry
dummies corresponding to the first two digits of Standard Industrial Classification (SIC) codes. We
provide the details of these characteristics in Table A.6.30
     We also construct eight macroeconomic predictors following the variable definitions detailed in
Welch and Goyal (2008), including dividend-price ratio (dp), earnings-price ratio (ep), book-to-
market ratio (bm), net equity expansion (ntis), Treasury-bill rate (tbl), term spread (tms), default
spread (dfy), and stock variance (svar).31
     All of the machine learning methods we consider are designed to approximate the over-arching
empirical model Et (ri,t+1 ) = g ? (zi,t ) defined in equation (2). Throughout our analysis we define the
baseline set of stock-level covariates zi,t as

                                                 zi,t = xt ⊗ ci,t ,                                                 (21)
    28
       We include stocks with prices below $5, share codes beyond 10 and 11, and financial firms. There are at least
three important reasons why we select the largest possible pool of assets. First, these commonly used filters remove
certain stocks that are components of the S&P 500 index, and we find it clearly problematic to exclude such important
stocks from an asset pricing analysis. Moreover, because we aggregate individual stock return predictions to predict
the index, we cannot omit such stocks. Second, our results are less prone to sample selection or data snooping biases
that the literature, e.g. Lo and MacKinlay (1990), cautions against. Third, using a larger sample helps avoid overfitting
by increasing the ratio of observation count to parameter count. That said, our results are qualitatively identical and
quantitively unchanged if we filter out these firms.
    29
       We cross-sectionally rank all stock characteristics period-by-period and map these ranks into the [-1,1] interval
following Kelly et al. (2019) and Freyberger et al. (2019).
    30
       The 94 predictive characteristics are based on Green et al. (2017), and we adapt the SAS code available from
Jeremiah Green’s website and extend the sample period back to 1957. Our data construction differs by adhering more
closely to variable definitions in original papers. For example, we construct book-equity and operating profitability
following Fama and French (2015). Most of these characteristics are released to the public with a delay. To avoid the
forward-looking bias, we assume that monthly characteristics are delayed by at most 1 month, quarterly with at least
4 months lag, and annual with at least 6 months lag. Therefore, in order to predict returns at month t + 1, we use
most recent monthly characteristics at the end of month t, most recent quarterly data by end t − 4, and most recent
annual data by end t − 6. Another issue is missing characteristics, which we replace with the cross-sectional median at
each month for each stock, respectively.
    31
       The monthly data are available from Amit Goyal’s website.




                                                           24
where ci,t is a Pc × 1 matrix of characteristics for each stock i, and xt is a Px × 1 vector of macroe-
conomic predictors (and are thus common to all stocks, including a constant). Thus, zi,t is a P × 1
vector of features for predicting individual stock returns (with P = Pc Px ) and includes interac-
tions between stock-level characteristics and macroeconomic state variables. The total number of
covariates is 94 × (8 + 1) + 74 = 920.
   The over-arching model specified by (2) and (21) nests many models proposed in the literature
(Rosenberg, 1974; Harvey and Ferson, 1999, among others). The motivating example for this model
structure is the standard beta-pricing representation of the asset pricing conditional Euler equation,

                                                      Et (ri,t+1 ) = β 0i,t λt .                                      (22)

The structure of our feature set in (21) allows for purely stock-level information to enter expected
returns via ci,t in analogy with the risk exposure function β i,t , and also allows aggregate economic
conditions to enter in analogy with the dynamic risk premium λt . In particular, if β i,t = θ1 ci,t , and
λt = θ2 xt , for some constant parameter matrices θ1 (K × Pc ) and θ2 (K × Px ), then the beta-pricing
model in (22) becomes

                   g ? (zi,t ) = Et (ri,t+1 ) = β 0i,t λt = c0i,t θ01 θ2 xt = (xt ⊗ ci,t )0 vec(θ01 θ2 ) =: zi,t
                                                                                                             0
                                                                                                                 θ,   (23)

where θ = vec(θ01 θ2 ). The over-arching model is more general than this example because g ? (·) is
not restricted to be a linear function. Considering nonlinear g ? (·) formulations, for example via
generalized linear models or neural networks, essentially expands the feature set to include a variety
of functional transformations of the baseline zi,t predictor set.
   We divide the 60 years of data into 18 years of training sample (1957 - 1974), 12 years of validation
sample (1975 - 1986), and the remaining 30 years (1987 - 2016) for out-of-sample testing. Because
machine learning algorithms are computationally intensive, we avoid recursively refitting models each
month. Instead, we refit once every year as most of our signals are updated once per year. Each time
we refit, we increase the training sample by one year. We maintain the same size of the validation
sample, but roll it forward to include the most recent twelve months.32

3.2      The Cross Section of Individual Stocks
Table 1 presents the comparison of machine learning techniques in terms of their out-of-sample
predictive R2 . We compare thirteen models in total, including OLS with all covariates, OLS-3
(which pre-selects size, book-to-market, and momentum as the only covariates), PLS, PCR, elastic
net (ENet), generalized linear model with group lasso (GLM), random forest (RF), gradient boosted
regression trees (GBRT), and neural network architectures with one to five layers (NN1,...,NN5).
For OLS, ENet, GLM, and GBRT, we present their robust versions using Huber loss, which perform
better than the version without.
                                     2 for the entire pooled sample. The OLS model using all 920
   The first row of Table 1 reports Roos
  32
       Note that we do not use cross-validation in order to maintain the temporal ordering of the data.


                                                                 25
                                                                                          2 )
           Table 1: Monthly Out-of-sample Stock-level Prediction Performance (Percentage Roos


                    OLS        OLS-3    PLS      PCR     ENet     GLM     RF       GBRT   NN1    NN2    NN3    NN4    NN5
                    +H          +H                        +H       +H               +H

 All                -3.46      0.16      0.27     0.26   0.11      0.19   0.33     0.34   0.33   0.39   0.40   0.39   0.36
 Top 1000          -11.28      0.31     -0.14     0.06   0.25      0.14   0.63     0.52   0.49   0.62   0.70   0.67   0.64
 Bottom 1000        -1.30      0.17     0.42      0.34   0.20      0.30   0.35     0.32   0.38   0.46   0.45   0.47   0.42
         0.8
                All
                Top
                Bottom
         0.6



         0.4
  Roos
   2




         0.2



            0



         -0.2
                  O



                              PL



                                       PC



                                                EN



                                                         G



                                                                  RF



                                                                          G



                                                                                   N



                                                                                          N



                                                                                                 N



                                                                                                        N



                                                                                                               N
                   LS




                                                         LM




                                                                          BR



                                                                                   N



                                                                                          N



                                                                                                 N



                                                                                                        N



                                                                                                                N
                              S



                                       R



                                                  et




                                                                                    1



                                                                                          2



                                                                                                  3



                                                                                                         4



                                                                                                                 5
                     -3




                                                  +H




                                                                              T+
                                                             +H
                         +H




                                                                              H




                                         2
Note: In this table, we report monthly Roos for the entire panel of stocks using OLS with all variables (OLS), OLS using
only size, book-to-market, and momentum (OLS-3), PLS, PCR, elastic net (ENet), generalize linear model (GLM),
random forest (RF), gradient boosted regression trees (GBRT), and neural networks with one to five layers (NN1–NN5).
                                                                                     2
“+H” indicates the use of Huber loss instead of the l2 loss. We also report these Roos   within subsamples that include
only the top 1,000 stocks or bottom 1,000 stocks by market value. The lower panel provides a visual comparison of the
  2
Roos statistics in the table (omitting OLS due to its large negative values).


                      2 of −3.46%, indicating it is handily dominated by applying a naive forecast
features produces an Roos
of zero to all stocks in all months. This may be unsurprising as the lack of regularization leaves OLS
highly susceptible to in-sample overfit. However, restricting OLS to a sparse parameterization, either
by forcing the model to include only three covariates (size, value, and momentum), or by penalizing
the specification with the elastic net—generates a substantial improvement over the full OLS model
  2 of 0.16% and 0.11% respectively). Figure 3 summarizes the complexity of each model at each
(Roos
re-estimation date. The upper left panel shows the number of features to which elastic net assigns
a non-zero loading. In the first ten years of the test sample, the model typically chooses fewer than
five features. After 2000, the number of selected features rises and hovers between 20 and 40.
     Regularizing the linear model via dimension reduction improves predictions even further. By
forming a few linear combinations of predictors, PLS and especially PCR, raise the out-of-sample
R2 to 0.27% and 0.26%, respectively. Figure 3 shows that PCR typically uses 20 to 40 components
in its forecasts. PLS, on the other hand, fails to find a single reliable component for much of the
early sample, but eventually settles on three to six components. The improvement of dimension

                                                                  26
                                              Figure 3: Time-varying Model Complexity


                                            ENet+H                                                              PCR
                      60                                                                100

                      40




                                                                           # of Comp.
         # of Char.




                                                                                         50
                      20

                       0                                                                  0
                      1985    1990   1995   2000 2005       2010   2015                  1985   1990   1995    2000 2005     2010   2015
                                             PLS                                                              GLM+H
                      10                                                                100
         # of Comp.




                                                                           # of Char.
                          5                                                              50


                       0                                                                  0
                      1985    1990   1995   2000     2005   2010   2015                  1985   1990   1995    2000 2005     2010   2015
                                              RF                                                              GBRT+H
                          6                                                             100

                          4
             Tree Depth




                                                                           # of Char.
                                                                                         50
                          2

                       0                                                                  0
                      1985    1990   1995   2000     2005   2010   2015                  1985   1990   1995    2000   2005   2010   2015




Note: This figure demonstrates the model complexity for elastic net (ENet), PCR, PLS, generalized linear model with
group lasso (GLM), random forest (RF) and gradient boosted regression trees (GBRT) in each training sample of
our 30-year recursive out-of-sample analysis. For ENet and GLM we report the number of features selected to have
non-zero coefficients; for PCR and PLS we report the number of selected components; for RF we report the average
tree depth; and for GBRT we report the number of distinct characteristics entering into the trees.


reduction over variable selection via elastic net suggests that characteristics are partially redundant
and fundamentally noisy signals. Combining them into low-dimension components averages out noise
to better reveal their correlated signals.
    The generalized linear model with group lasso penalty fails to improve on the performance of
                        2 of 0.19%). The fact that this method uses spline functions of individual
purely linear methods (Roos
features, but includes no interaction among features, suggests that univariate expansions provide
little incremental information beyond the linear model. Though it tends to select more features than
elastic net, those additional features do not translate into incremental performance.
    Boosted trees and random forests are competitive with PCR, producing fits of 0.34% and 0.33%,
respectively. Random forests generally estimate shallow trees, with one to five layers on average.
To quantify the complexity of GBRT, we report the number of features used in the boosted tree
ensemble at each re-estimation point. In the beginning of the sample GBRT uses around 30 features
to partition outcomes, with this number increasing to 50 later in the sample.
    Neural networks are the best performing nonlinear method, and the best predictor overall. The
 2 is 0.33% for NN1 and peaks at 0.40% for NN3. These results point to the value of incorporating
Roos
complex predictor interactions, which are embedded in tree and neural network models but that are


                                                                          27
                                                                                           2 )
             Table 2: Annual Out-of-sample Stock-level Prediction Performance (Percentage Roos


                 OLS         OLS-3   PLS    PCR    ENet     GLM    RF         GBRT   NN1    NN2    NN3    NN4    NN5
                 +H           +H                    +H       +H                +H

 All            -34.86       2.50    2.93   3.08   1.78     2.60   3.28       3.09   2.64   2.70   3.40   3.60   2.79
 Top            -54.86       2.48    1.84   1.64   1.90     1.82   4.80       4.07   2.77   4.24   4.73   4.91   4.86
 Bottom         -19.22       4.88    5.36   5.44   3.94     5.00   5.08       4.61   4.37   3.72   5.17   5.01   3.58
         6
               All
               Top
         5     Bottom



         4
  Roos




         3
   2




         2


         1


         0
                 O



                             PL



                                     PC



                                            EN



                                                   G



                                                            RF



                                                                   G



                                                                              N



                                                                                     N



                                                                                            N



                                                                                                   N



                                                                                                          N
                  LS




                                                   LM




                                                                   BR



                                                                               N



                                                                                     N



                                                                                            N



                                                                                                    N



                                                                                                           N
                              S



                                     R



                                              et




                                                                               1



                                                                                      2



                                                                                             3



                                                                                                     4



                                                                                                            5
                    -3




                                              +H




                                                                       T+
                                                       +H
                        +H




                                                                          H




                                 2
Note: Annual return forecasting Roos (see Table 1 notes).


missed by other techniques. The results also show that in the monthly return setting, the benefits
of “deep” learning are limited, as four and five layer models fail to improve over NN3.33
     The second and third rows of Table 1 break out predictability for large stocks (the top 1,000 stocks
by market equity each month) and small stocks (the bottom 1,000 each month). This is based on the
full estimated model (using all stocks), but focuses on fits among the two subsamples. The baseline
patterns that OLS fares poorly, regularized linear models are an improvement, and nonlinear models
dominate carries over into subsamples. Tree methods and neural networks are especially successful
                          2
among large stocks, with Roos ranging from 0.52% to 0.70%. This dichotomy provides reassurance
that machine learning is not merely picking up small scale inefficiencies driven by illiquidity.34
     Table 2 conducts our analysis at the annual horizon. The comparative performance across dif-
                                                                                   2
ferent methods is similar to the monthly results shown in Table 1, but the annual Roos is nearly
an order of magnitude larger. Their success in forecasting annual returns likewise illustrates that
  33
      Because we hold the five neural networks architectures fixed and simply compare across them, we do not describe
their estimated complexity in Figure 3.
   34
      As an aside, it is useful to know that there is a roughly 3% inflation in out-of-sample R2 s if performance is
benchmarked against historical averages. For OLS-3, the R2 relative to the historical mean forecast is 3.74% per
month! Evidently, the historical mean is such a noisy forecaster that it is easily beaten by a fixed excess return
forecasts of zero.



                                                             28
      Table 3: Comparison of Monthly Out-of-Sample Prediction using Diebold-Mariano Tests

               OLS-3      PLS      PCR      ENet      GLM       RF      GBRT       NN1       NN2      NN3       NN4      NN5
                +H                           +H        +H                +H
OLS+H          3.26∗     3.29∗    3.35∗     3.29∗    3.28∗     3.29∗     3.26∗     3.34∗    3.40∗     3.38∗    3.37∗     3.38∗
OLS-3+H                   1.42    1.87      -0.27     0.62     1.64       1.28      1.25    2.13      2.13     2.36      2.11
PLS                               -0.19     -1.18    -1.47      0.87      0.67      0.63     1.32      1.37    1.66       1.08
PCR                                         -1.10    -1.37      0.85      0.75      0.58     1.17      1.19     1.34      1.00
ENet+H                                                0.64     1.90       1.40     1.73     1.97      2.07     1.98      1.85
GLM+H                                                          1.76       1.22      1.29    2.28      2.17     2.68∗     2.37
RF                                                                        0.07     -0.03     0.31      0.37     0.34      0.00
GBRT+H                                                                             -0.06     0.16      0.21     0.17     -0.04
NN1                                                                                          0.56      0.59     0.45      0.04
NN2                                                                                                    0.32    -0.03     -0.88
NN3                                                                                                            -0.32     -0.92
NN4                                                                                                                      -1.04

Note: This table reports pairwise Diebold-Mariano test statistics comparing the out-of-sample stock-level prediction
performance among thirteen models. Positive numbers indicate the column model outperforms the row model. Bold
font indicates the difference is significant at 5% level or better for individual tests, while an asterisk indicates significance
at the 5% level for 12-way comparisons via our conservative Bonferroni adjustment.


machine learning models are able to isolate risk premia that persist over business cycle frequencies
and are not merely capturing short-lived inefficiencies.
    While Table 1 offers a quantitative comparison of models’ predictive performance, Table 3 assesses
the statistical significance of differences among models at the monthly frequency. It reports Diebold-
Mariano test statistics for pairwise comparisons of a column model versus a row model. Diebold-
Mariano statistics are distributed N (0, 1) under the null of no difference between models, thus the test
statistic magnitudes map to p-values in the same way as regression t-statistics. Our sign convention
is that a positive statistic indicates the column model outperforms the row model. Bold numbers
denote significance at the 5% level for each individual test.
    The first conclusion from Table 3 is that constrained linear models—including restricting OLS
to only use three predictors, reducing dimension via PLS or PCA, and penalizing via elastic net—
produce statistically significant improvements over the unconstrained OLS model. Second, we see
little difference in the performance of penalized linear methods and dimension reduction methods.
Third, we find that tree-based methods uniformly improve over linear models, but the improvements
are at best marginally significant. Neural networks are the only models that produce large and
significant statistical improvements over linear and generalized linear models. They also improve
over tree models, but the difference is not statistically significant.
    Table 3 makes multiple comparisons. We highlight how inference changes under a conservative
Bonferroni multiple comparisons correction that divides the significance level by the number of
comparisons.35 For a significance level of 5% amid 12 model comparisons, the adjusted one-sided
   35
      Multiple comparisons are a concern when the researcher conducts many hypotheses tests and draws conclusions
based on only those that are significant. This distorts the size of tests through a selection bias. This is not how we
present our results—we report t-statistics for every comparison we consider—yet we report adjusted inference to err
on the side of caution. We also note that false discoveries in multiple comparisons should be randomly distributed.



                                                               29
critical value in our setting is 2.64. In the table, tests that exceed this conservative threshold
are accompanied by an asterisk. The main difference with a Bonferroni adjustment is that neural
networks become only marginally significant over penalized linear models.

3.3    Which Covariates Matter?
We now investigate the relative importance of individual covariates for the performance of each model
using the importance measures described in Section 2.9. To begin, for each method, we calculate the
reduction in R2 from setting all values of a given predictor to zero within each training sample, and
average these into a single importance measure for each predictor. Figure 4 reports the resulting
importances of the top 20 stock-level characteristics for each method. Variable importances within a
model are normalized to sum to one, giving them the interpretation of relative importance for that
particular model.
    Figure 5 reports overall rankings of characteristics for all models. We rank the importance of
each characteristic for each method, then sum their ranks. Characteristics are ordered so that the
highest total ranks are on top and the lowest ranking characteristics are at the bottom. The color
gradient within each column shows the model-specific ranking of characteristics from least to most
important (lightest to darkest).36
    Figures 4 and 5 demonstrate that models are generally in close agreement regarding the most
influential stock-level predictors, which can be grouped into four categories. The first are based
on recent price trends, including five of the top seven variables in Figure 5: short-term reversal
(mom1m), stock momentum (mom12m), momentum change (chmom), industry momentum (ind-
mom), recent maximum return (maxret), and long-term reversal (mom36m). Next are liquidity
variables, including turnover and turnover volatility (turn, std turn), log market equity (mvel1),
dollar volume (dolvol), Amihud illiquidity (ill), number of zero trading days (zerotrade), and bid-
ask spread (baspread). Risk measures constitute the third influential group, including total and
idiosyncratic return volatility (retvol, idiovol), market beta (beta), and beta-squared (betasq). The
last group includes valuation ratios and fundamental signals, such as earnings-to-price (ep), sales-to-
price (sp), asset growth (agr), and number of recent earnings increases (nincr). Figure 4 shows that
characteristic importance magnitudes for penalized linear models and dimension reduction models
are highly skewed toward momentum and reversal. Trees and neural networks are more democratic,
drawing predictive information from a broader set of characteristics.
    We find that our second measure of variable importance, SSD from Dimopoulos et al. (1995),
produces very similar results to the simpler R2 measure. Within each model, we calculate the Pearson
correlation between relative importances from SSD and the R2 measure. These correlations range
from 84.0% on the low end (NN1) to 97.7% on the high end (random forest). That is, the two
The statistically significant t-statistics in our analyses do not appear random, but instead follow a pattern in which
nonlinear models outperform linear ones.
   36
      Figure 5 is based on the average rank over 30 recursing training samples. Figure A.1 presents the ranks for each of
the recursing sample, respectively. The rank of important characteristics (top third of the covariates) are remarkably
stable over time. This is true for all models, though we show results for one representative model (NN3) in the interest
of space.


                                                           30
                                                 Figure 4: Variable Importance By Model
                                         PLS                                                                         PCR
     mom1m                                                                           mom1m
      chmom                                                                           chmom
     indmom                                                                         mom12m
    mom12m                                                                           indmom
     std_turn                                                                          maxret
       maxret                                                                               sp
          turn                                                                          mvel1
            sp                                                                        chcsho
     mom6m                                                                            rd_mve
        mvel1                                                                              agr
            ep                                                                          invest
        dolvol                                                                              ep
      rd_mve                                                                         mom6m
           agr                                                                         cashpr
       cashpr                                                                             depr
         nincr                                                                             bm
      chcsho                                                                                lgr
        retvol                                                                           chinv
    operprof                                                                            bm_ia
           lev                                                                      mom36m
                  0.0         0.1                 0.2             0.3                             0.0              0.1            0.2                  0.3
                                   ENet+H                                                                          GLM+H
     mom1m                                                                            mom1m
    mom12m                                                                           mom12m
     indmom                                                                            indmom
            agr                                                                           mvel1
        dolvol                                                                           maxret
      rd_mve                                                                            rd_mve
        invest                                                                               agr
      chcsho                                                                              invest
             sp                                                                                ill
     std_turn                                                                           chcsho
             ps                                                                          cashpr
          nincr                                                                           dolvol
      chmom                                                                             chmom
         chinv                                                                              turn
           turn                                                                               ep
             ep                                                                               lgr
        mvel1                                                                              chinv
         retvol                                                                             sic2
     mom6m                                                                          securedind
    mom36m                                                                           mom36m
                  0.0              0.2                  0.4              0.6                         0.0    0.1          0.2      0.3          0.4           0.5
                                         RF                                                                       GBRT+H
      mom1m                                                                                   dy
              dy                                                                      mom1m
          mvel1                                                                     securedind
         maxret                                                                      mom12m
       indmom                                                                            maxret
    securedind                                                                             nincr
           nincr                                                                          retvol
          retvol                                                                       indmom
        chmom                                                                             mvel1
     mom12m                                                                             chmom
     baspread                                                                           convind
      mom6m                                                                                   sp
        convind                                                                          idiovol
         idiovol                                                                     baspread
              sp                                                                      mom6m
           beta                                                                            beta
         betasq                                                                             age
               ill                                                                   mom36m
          dolvol                                                                            turn
     mom36m                                                                             rd_mve
                     0.00                0.05                  0.10                                  0.00   0.05         0.10     0.15          0.20
                                         NN2                                                                         NN3
      mom1m                                                                           mom1m
          mvel1                                                                           mvel1
          retvol                                                                          retvol
        chmom                                                                            maxret
         maxret                                                                         chmom
          dolvol                                                                          dolvol
            turn                                                                            turn
     mom12m                                                                              idiovol
      mom6m                                                                           mom6m
     baspread                                                                        baspread
               ill                                                                   mom12m
         idiovol                                                                               ill
      std_turn                                                                        std_turn
       indmom                                                                          indmom
           nincr                                                                           nincr
     zerotrade                                                                       zerotrade
    securedind                                                                       mom36m
     mom36m                                                                         securedind
              sp                                                                              sp
         betasq                                                                            beta
                     0.00   0.05          0.10          0.15      0.20                               0.00   0.05           0.10         0.15         0.20


Note: Variable importance for the top 20 most influential variables in each model. Variable importance is an average
over all training samples. Variable importances within each model are normalized to sum to one.



                                                                               31
                                             Figure 5: Characteristic Importance
              mom1m
                  mvel1
            mom12m
               chmom
                maxret
              indmom
                   retvol
                  dolvol
                        sp
                     turn
                      agr
                    nincr
               rd_mve
              std_turn
              mom6m
            mom36m
                        ep
                chcsho
         securedind
                 idiovol
            baspread
                          ill
                     age
               convind
                         rd
                    depr
                    beta
                betasq
                cashpr
                        ps
            zerotrade
                        dy
                orgcap
                      bm
                        lgr
            cashdebt
                   chinv
                  invest
                       lev
             operprof
                 bm_ia
                saleinv
                      egr
                      cfp
               rd_sale
                      sgr
                    roaq
                     roic
                     sic2
               mve_ia
                      ms
                   quick
                     herf
                     hire
          pricedelay
               salerec
                  roavol
                    roeq
                grcapx
                  currat
                    cash
          std_dolvol
                      acc
                  cfp_ia
                grltnoa
                    gma
                 pctacc
                absacc
             salecash
              secured
              pchdepr
                    tang
         pchcapx_ia
             chempia
                      ear
    pchsale_pchinvt
          pchsaleinv
                     chtx
               chpmia
               chatoia
                         tb
                 aeavol
                    rsup
     pchgm_pchsale
   pchsale_pchxsga
                cinvest
             pchquick
    pchsale_pchrect
           realestate
            pchcurrat
                 stdacc
                    stdcf
                      divi
                     divo
                       sin
                                PLS   PCR   ENet+H   GLM+H   RF    GBRT+H   NN1   NN2   NN3     NN4      NN5


Note: Rankings of 94 stock-level characteristics and the industry dummy (sic2) in terms of overall model contribution.
Characteristics are ordered based on the sum of their ranks over all models, with the most influential characteristics on
top and least influential on bottom. Columns correspond to individual models, and color gradients within each column
indicate the most influential (dark blue) to least influential (white) variables.



                                                                  32
                         Table 4: Variable Importance for Macroeconomic Predictors

         PLS     PCR       ENet+H     GLM+H         RF         GBRT+H    NN1           NN2     NN3     NN4       NN5
dp      12.52    14.12         2.49       4.54     5.80           6.05   15.57         17.58   14.84   13.95     13.15
ep      12.25    13.52         3.27       7.37     6.27           2.85    8.86          8.09    7.34    6.54      6.47
bm      14.21    14.83        33.95      43.46    10.94          12.49   28.57         27.18   27.92   26.95     27.90
ntis    11.25     9.10         1.30       4.89    13.02          13.79   18.37         19.26   20.15   19.59     18.68
tbl     14.02    15.29        13.29       7.90    11.98          19.49   17.18         16.40   17.76   20.99     21.06
tms     11.35    10.66         0.31       5.87    16.81          15.27   10.79         10.59   10.91   10.38     10.33
dfy     17.17    15.68        42.13      24.10    24.37          22.93    0.09          0.06    0.06    0.04      0.12
svar     7.22     6.80         3.26       1.87    10.82           7.13    0.57          0.85    1.02    1.57      2.29
 0.6
                                                                                                               PLS
                                                                                                               PCR
 0.5                                                                                                           ENet+H
                                                                                                               GLM+H
                                                                                                               RF
                                                                                                               GBRT+H
 0.4
                                                                                                               NN1
                                                                                                               NN2
                                                                                                               NN3
 0.3                                                                                                           NN4
                                                                                                               NN5


 0.2


 0.1


   0
                dp            ep         bm          ntis          tbl           tms           dfy        svar

Note: Variable importance for eight macroeconomic variables in each model. Variable importance is an average over
all training samples. Variable importances within each model are normalized to sum to one. The lower panel provides
a complementary visual comparison of macroeconomic variable importances.


methods provide a highly consistent summary of which variables are most influential for forecast
accuracy. The full set of SSD results are shown in appendix Figure A.2.
    For robustness, we re-run our analysis with an augmented set of characteristics that include five
placebo “characteristics.” They are simulated according to the data generating process (A.1) in
Appendix A. The parameters are calibrated to have similar behavior as our characteristics dataset
but are independent of future returns by construction. Figure A.3 in Appendix F presents the variable
importance plot (based on R2 ) with five noise characteristics highlighted. The table confirms that the
most influential characteristics that we identify in our main analysis are unaffected by the presence of
irrelevant characteristics. Noise variables appear among the least informative characteristics, along
with sin stocks, dividend initiation/omission, cashflow volatility, and other accounting variables.
    Table 4 shows the R2 -based importance measure for each macroeconomic predictor variable (again
normalized to sum to one within a given model). All models agree that the aggregate book-to-market
ratio is a critical predictor, whereas market volatility has little role in any model. PLS and PCR
place similar weights on all other predictors, potentially because these variables are highly correlated.
Linear and generalized linear models strongly favor bond market variables including the default

                                                          33
spread and treasury rate. Nonlinear methods (trees and neural networks) place great emphasis on
exactly those predictors ignored by linear methods, such as term spreads and issuance activity.
   Many accounting characteristics are not available at the monthly frequency, which might explain
their low importance in Figure 5. To investigate this, appendix Figure A.6 presents the rank of
variables based on the annual return forecasts. Price trend variables become less important compared
to the liquidity and risk measures, although they are still quite influential. The characteristics that
were ranked in the bottom half of predictors at the monthly horizon remain largely unimportant at
the annual horizon. The exception is industry (sic2) which shows substantial predictive power at the
annual frequency.

3.3.1    Marginal Association Between Characteristics and Expected Returns

Figure 6 traces out the model-implied marginal impact of individual characteristics on expected
excess returns. Our data transformation normalizes characteristics to the (-1,1) interval, and holds
all other variables fixed at their median value of zero. We choose four illustrative characteristics
for the figure, including size (mvel1), momentum (mom12m), stock volatility (retvol), and accruals
(acc).
   First, Figure 6 illustrates that machine learning methods identify patterns similar to some well
known empirical phenomena. For example, expected stock returns are decreasing in size, increasing
in past one-year return, and decreasing in stock volatility. And it is interesting to see that all
methods agree on a nearly exact zero relationship between accruals and future returns. Second, the
(penalized) linear model finds no predictive association between returns and either size or volatility,
while trees and neural networks find large sensitivity of expected returns to both of these variables.
For example, a firm that drops from median size to the 20th percentile of the size distribution
experiences an increase in its annualized expected return of roughly 2.4% (0.002×12×100), and a
firm whose volatility rises from median to 80th percentile experiences a decrease of around 3.0% per
year, according to NN3, and these methods detect nonlinear predictive associations. The inability
of linear models to capture nonlinearities can lead them to prefer a zero association, and this can in
part explain the divergence in the performance of linear and nonlinear methods.

3.3.2    Interaction Effects

The favorable performance of trees and neural networks indicates a benefit to allowing for potentially
complex interactions among predictors. Machine learning models are often referred to as “black
boxes.” This is in some sense a misnomer, as the models are readily inspectable. They are, however,
complex, and this is the source of both their power and their opacity. Any exploration of interaction
effect is vexed by vast possibilities for identity and functional forms for interacting predictors. In
this section, we present a handful of interaction results to help illustrate the inner workings of one
black box method, the NN3 model.
   As a first example, we examine a set of pairwise interaction effects in NN3. Figure 7 reports how
expected returns vary as we simultaneously vary values of a pair of characteristics over their support


                                                  34
                     Figure 6: Marginal Association Between Expected Returns and Characteristics
            ×10 -3                                                                           ×10 -3
        4                                                                                4
                                                                       ENet+H
                                                                       GLM+H
                                                                       RF
                                                                       GBRT+H
                                                                       NN3

        0                                                                                0




    -4                                                                                   -4
      -1        -0.8   -0.6   -0.4   -0.2     0      0.2   0.4   0.6    0.8     1          -1    -0.8   -0.6   -0.4   -0.2   0   0.2     0.4   0.6   0.8   1
                                            mvel1                                                                         mom12m
            ×10 -3                                                                           ×10 -3
        4                                                                                4




        0                                                                                0




    -4                                                                                   -4
      -1        -0.8   -0.6   -0.4   -0.2      0     0.2   0.4   0.6    0.8     1          -1    -0.8   -0.6   -0.4   -0.2    0    0.2   0.4   0.6   0.8   1
                                            retvol                                                                           acc


Note: Sensitivity of expected monthly percentage returns (vertical axis) to individual characteristics (holding all other
covariates fixed at their median values).


[-1,1], while holding all other variables fixed at their median value of zero. We show interactions of
stock size (mvel1) with four other predictors: short-term reversal (mom1m), momentum (mom12m),
and total and idiosyncratic volatility (retvol and idiovol, respectively).
    The upper-left figure shows that the short-term reversal effect is strongest and is essentially
linear among small stocks (blue line). Among large stocks (green line), reversal is concave, occurring
primarily when the prior month return is positive. The upper-right figure shows the momentum
effect, which is most pronounced among large stocks for the NN3 model.37 Likewise, on the lower-
left, we see that the low volatility anomaly is also strongest among large stocks. For small stocks, the
volatility effect is hump-shaped. Finally, the lower-right shows that NN3 estimates no interaction
effect between size and accruals—the size lines are simply vertical shifts of the univariate accruals
curve.
    Figure 8 illustrates interactions between stock-level characteristics and macroeconomic indicator
variables. It shows, for example, that the size effect is more pronounced when aggregate valuations
are low (bm is high) and when equity issuance (ntis) is low, while the low volatility anomaly is
especially strong in high valuation and high issuance environments. Appendix Figure A.4 shows
the 100 most important interactions of stock characteristics with macroeconomic indicators for each
machine learning model. The most influential features come from interacting a stock’s recent price
   37
     Note that conclusions from our model can diverge from results in the literature because we jointly model hundreds
of predictor variables, which can lead to new conclusions regarding marginal effects, interaction effects, and so on.


                                                                                    35
                            Figure 7: Expected Returns and Characteristic Interactions (NN3)
      0.6                                                                                 0.6
                                                                    mvel1=-1
                                                                    mvel1=-0.5
                                                                    mvel1=0
                                                                    mvel1=0.5
                                                                    mvel1=1


         0                                                                                   0




      -0.6                                                                                -0.6
             -1   -0.8   -0.6   -0.4   -0.2      0  0.2       0.4   0.6   0.8    1               -1   -0.8   -0.6   -0.4   -0.2  0   0.2      0.4   0.6   0.8   1
                                              mom1m                                                                           mom12m
      0.6                                                                                 0.6




         0                                                                                   0




      -0.6                                                                                -0.6
             -1   -0.8   -0.6   -0.4   -0.2       0     0.2   0.4   0.6   0.8    1               -1   -0.8   -0.6   -0.4   -0.2    0    0.2   0.4   0.6   0.8   1
                                               retvol                                                                             acc


Note: Sensitivity of expected monthly percentage returns (vertical axis) to interactions effects for mvel1 with mom1m,
mom12m, retvol, and acc in model NN3 (holding all other covariates fixed at their median values).


trends (e.g., momentum, short-term reversal, or industry momentum) with aggregate asset price
levels (e.g., valuation ratios of the aggregate stock market or Treasury bill rates). Furthermore, the
dominant macroeconomic interactions are stable over time, as illustrated in appendix Figure A.5.

3.4          Portfolio Forecasts
So far we have analyzed predictability of individual stock returns. Next, we compare forecasting
performance of machine learning methods for aggregate portfolio returns. There are a number of
benefits to analyzing portfolio-level forecasts.
    First, because all of our models are optimized for stock-level forecasts, portfolio forecasts provide
an additional indirect evaluation of the model and its robustness. Second, aggregate portfolios
tend to be of broader economic interest because they represent the risky-asset savings vehicles most
commonly held by investors (via mutual funds, ETFs, and hedge funds). We study value-weight
portfolios to assess the extent to which a model’s predictive performance thrives in the most valuable
(and most economically important) assets in the economy. Third, the distribution of portfolio returns
is sensitive to dependence among stock returns, with the implication that a good stock-level prediction
model is not guaranteed to produce accurate portfolio-level forecasts. Bottom-up portfolio forecasts
allow us to evaluate a model’s ability to transport its asset predictions, which occur at the finest


                                                                                     36
   Figure 8: Expected Returns and Characteristic/Macroeconomic Variable Interactions (NN3)
     0.5                                                                                 0.5
                                                            bm=Quantile 10%                                                                     ntis=Quantile 10%
                                                            bm=Quantile 30%                                                                     ntis=Quantile 30%
                                                            bm=Quantile 50%                                                                     ntis=Quantile 50%
                                                            bm=Quantile 70%                                                                     ntis=Quantile 70%
                                                            bm=Quantile 90%                                                                     ntis=Quantile 90%


        0                                                                                   0




    -0.5                                                                                 -0.5
           -1    -0.8   -0.6   -0.4   -0.2     0   0.2      0.4   0.6   0.8    1                -1   -0.8   -0.6   -0.4   -0.2     0   0.2      0.4    0.6    0.8   1
                                             mvel1                                                                               mvel1
     0.5
                                                            bm=Quantile 10%              0.5
                                                            bm=Quantile 30%                                                                     ntis=Quantile 10%
                                                            bm=Quantile 50%                                                                     ntis=Quantile 30%
                                                            bm=Quantile 70%                                                                     ntis=Quantile 50%
                                                            bm=Quantile 90%                                                                     ntis=Quantile 70%
                                                                                                                                                ntis=Quantile 90%

        0                                                                                   0




    -0.5                                                                                 -0.5
           -1    -0.8   -0.6   -0.4   -0.2      0     0.2   0.4   0.6   0.8    1                -1   -0.8   -0.6   -0.4   -0.2      0     0.2   0.4    0.6    0.8   1
                                             retvol                                                                              retvol


Note: Sensitivity of expected monthly percentage returns (vertical axis) to interactions effects for mvel1 and retvol
with bm and ntis in model NN3 (holding all other covariates fixed at their median values).


asset level, into broader investment contexts. Last but not least, the portfolio results are one step
further “out-of-sample” in that the optimization routine does not directly account for the predictive
performance of the portfolios.
    Our assessment of forecast performance up to this point has been entirely statistical, relying on
comparisons of predictive R2 . The final advantage of analyzing predictability at the portfolio level
is that we can assess the economic contribution of each method via its contribution to risk-adjusted
portfolio return performance.

3.4.1           Pre-specified Portfolios

We build bottom-up forecasts by aggregating individual stock return predictions into portfolios.
                                                     p
Given the weight of stock i in portfolio p (denoted wi,t ) and given a model-based out-of-sample
forecast for stock i (denoted rbi,t+1 ), we construct the portfolio return forecast as

                                                                              n
                                                                    p                p
                                                                              X
                                                                  rbt+1 =           wi,t × rbi,t+1 .
                                                                              i=1

This bottom-up approach works for any target portfolio whose weights are known a priori.
    We form bottom-up forecasts for 30 of the most well known portfolios in the empirical finance


                                                                                    37
                      Table 5: Monthly Portfolio-level Out-of-Sample Predictive R2
                       OLS-3     PLS    PCR     ENet    GLM      RF     GBRT      NN1     NN2     NN3    NN4     NN5
                        +H                       +H      +H              +H
                                          Panel A: Common Factor Portfolios
 S&P 500                -0.22   -0.86   -1.55   0.75   0.71   1.37     1.40        1.08   1.13    1.80    1.63   1.17
 SMB                    0.81     2.09   0.39     1.72  2.36   0.57     0.35        1.40   1.16    1.31    1.20   1.27
 HML                    0.66     0.50   1.21     0.46  0.84   0.98     0.21       1.22    1.31    1.06    1.25   1.24
 RMW                    -2.35    1.19    0.41   -1.07 -0.06 -0.54     -0.92        0.68    0.47   0.84    0.53   0.54
 CMA                    0.80    -0.44   0.03    -1.07 1.24   -0.11    -1.04        1.88   1.60    1.06    1.84   1.31
 UMD                    -0.90   -1.09   -0.47   0.47  -0.37   1.37    -0.25       -0.56   -0.26   0.19    0.27   0.35

                                     Panel B: Sub-components of Factor Portfolios
 Big Value               0.10    0.00   -0.33   0.25   0.59    1.31    1.06     0.85      0.87    1.46    1.21   0.99
 Big Growth             -0.33   -1.26 -1.62     0.70   0.51    1.32    1.19     1.00      1.10    1.50    1.24   1.11
 Big Neutral            -0.17   -1.09 -1.51     0.80   0.36    1.31    1.28     1.43      1.24    1.70    1.81   1.40
 Small Value             0.30    1.66    1.05   0.64   0.85    1.24    0.52     1.59      1.37    1.54    1.40   1.30
 Small Growth           -0.16    0.14   -0.18 -0.33   -0.12    0.71    1.24     0.05      0.42    0.48    0.41   0.50
 Small Neutral          -0.27    0.60    0.19   0.21   0.28    0.88    0.36     0.58      0.62    0.70    0.58   0.68

 Big Conservative       -0.57   -0.10   -1.06    1.02    0.46    1.11     0.55    1.15    1.13    1.59    1.37   1.07
 Big Aggressive         0.20    -0.80   -1.15    0.30    0.67    1.75     2.00    1.33    1.51    1.78    1.55   1.42
 Big Neutral            -0.29   -1.75   -1.96    0.83    0.48    1.13     0.77    0.85    0.85    1.51    1.45   1.16
 Small Conservative     -0.05   1.17     0.71   -0.02    0.34    0.96     0.56    0.82    0.87    0.96    0.90   0.83
 Small Aggressive       -0.10   0.51    0.01    -0.09    0.14    1.00     1.46    0.34    0.64    0.75    0.62   0.71
 Small Neutral          -0.30   0.45     0.12    0.42    0.35    0.76    -0.01    0.70    0.69    0.83    0.66   0.72

 Big Robust             -1.02   -1.08   -2.06   0.55     0.35    1.10    0.33     0.74    0.79    1.28    1.03   0.74
 Big Weak               -0.12    1.42    1.07    0.89     1.10   1.33    1.77     1.79    1.79    2.05    1.66   1.60
 Big Neutral             0.86   -1.22   -1.26    0.41     0.13   1.10    0.91     0.84    0.94    1.19    1.15   0.99
 Small Robust           -0.71    0.35   -0.38   -0.04    -0.42   0.70    0.19     0.24    0.50    0.63    0.53   0.55
 Small Weak              0.05    1.06    0.59   -0.13     0.44   1.05     1.42    0.71    0.92    0.99    0.90   0.89
 Small Neutral          -0.51    0.07   -0.47   -0.33    -0.32   0.60    -0.08    0.10    0.25    0.38    0.32   0.41

 Big Up                  0.20   -0.25   -1.24   0.66      1.17   1.18     0.90    0.80    0.76    1.13    1.12   0.93
 Big Down               -1.54   -1.63   -1.55   0.44     -0.33   1.14    0.71     0.36    0.70    1.07    0.90   0.84
 Big Medium             -0.04   -1.51   -1.94   0.81     -0.08   1.57    1.80     1.29    1.32    1.71    1.55   1.23
 Small Up                0.07    0.78    0.56   -0.07     0.25   0.62    -0.03    0.06    0.07    0.21    0.19   0.25
 Small Down             -0.21   0.15    -0.20   0.15     -0.01   1.51    1.38     0.74    0.82    1.02    0.91   0.96
 Small Medium            0.07   0.82    0.20    0.59      0.37   1.22    1.06     1.09    1.09    1.18    1.00   1.03


Note: In this table, we report the out-of-sample predictive R2 s for 30 portfolios using OLS with size, book-to-market,
and momentum, OLS-3, PLS, PCR, elastic net (ENet), generalized linear model with group lasso (GLM), random forest
(RF), gradient boosted regression trees (GBRT), and five architectures of neural networks (NN1,...,NN5), respectively.
“+H” indicates the use of Huber loss instead of the l2 loss. The six portfolios in Panel A are the S&P 500 index and the
Fama-French SMB, HML, CMA, RMW, and UMD factors. The 24 portfolios in Panel B are 3 × 2 size double-sorted
portfolios used in the construction of the Fama-French value, investment, profitability, and momentum factors.


literature, including the S&P 500, the Fama-French size, value, profitability, investment, and momen-
tum factor portfolios (SMB, HML, RMW, CMA, and UMD, respectively), and sub-components of
these Fama-French portfolios, including six size and value portfolios, six size and investment portfo-
lios, six size and profitability portfolios, and six size and momentum portfolios. The sub-component
portfolios are long-only and therefore have substantial overlap with the market index, while SMB,
HML, RMW, CMA, and UMD are zero-net-investment long-short portfolios that are in large part


                                                          38
                              Table 6: Market Timing Sharpe Ratio Gains
                      OLS-3   PLS     PCR     ENet    GLM     RF     GBRT     NN1     NN2     NN3     NN4     NN5
                       +H                      +H      +H             +H
                                         Panel A: Common Factor Portfolios
 S&P 500              0.07     0.05   -0.06     0.12  0.19  0.18     0.19     0.22     0.20    0.26   0.22     0.19
 SMB                  0.06    0.17     0.09     0.24  0.26  0.00    -0.07     0.21     0.18    0.15   0.09    0.11
 HML                  0.00    0.01     0.04    -0.03 -0.02  0.04     0.02     0.04    0.06     0.04   0.02     0.01
 RMW                  0.00    -0.01   -0.06 -0.19    -0.13 -0.11    -0.01     -0.03   -0.09    0.01    0.01   -0.07
 CMA                  0.02    0.02       0     -0.09 -0.05  0.08    -0.01     0.00     0.01    0.05   0.04    0.06
 UMD                  0.01    -0.06   -0.02 -0.02    -0.07 -0.04    -0.07     -0.04   -0.08   -0.04   -0.10   -0.01

                                    Panel B: Sub-components of Factor Portfolios
 Big Value            -0.01    0.06   -0.03    0.09   0.06   0.09     0.08     0.11   0.11    0.13    0.10    0.11
 Big Growth            0.08   -0.01 -0.08      0.10   0.17   0.20     0.21     0.22   0.20    0.26    0.22    0.21
 Big Neutral           0.06    0.03   -0.06    0.11   0.16   0.13     0.17     0.23   0.21    0.23    0.23    0.21
 Small Value          -0.04    0.15    0.09    0.01   0.08   0.07     0.08     0.11   0.11    0.10    0.11    0.13
 Small Growth          0.00   0.03    -0.06 -0.03    -0.05   0.04     0.05     0.02   0.03    0.03    0.02    0.02
 Small Neutral         0.02    0.09    0.05    0.03   0.04   0.11     0.11     0.09   0.08    0.10    0.09    0.11

 Big Conservative     0.08     0.02   -0.04   0.08     0.15   0.09    0.13    0.17    0.14    0.19    0.16    0.14
 Big Aggressive       0.08    -0.01   -0.11    0.01    0.13   0.22    0.18    0.21    0.19    0.23    0.20    0.20
 Big Neutral          0.04    -0.01   -0.08   0.09     0.11   0.09    0.11    0.13    0.12    0.18    0.18    0.16
 Small Conservative   0.04     0.17    0.12   0.02    0.05    0.17    0.15    0.11    0.11    0.14    0.13    0.15
 Small Aggressive     0.01     0.05   -0.06   -0.05   -0.03   0.08    0.06    0.02    0.05    0.06    0.04    0.05
 Small Neutral        0.01     0.06    0.03   0.01    0.04    0.08    0.09    0.07    0.06    0.08    0.07    0.09

 Big Robust            0.10   0.07    -0.07   0.11    0.18    0.17    0.18    0.18    0.16    0.22    0.19    0.16
 Big Weak              0.05   0.12     0.05    0.09    0.12   0.21    0.17    0.22    0.20    0.21    0.18    0.19
 Big Neutral           0.09   0.00    -0.04    0.09    0.20   0.19    0.17    0.22    0.21    0.24    0.21    0.20
 Small Robust          0.09   0.04    -0.03   0.00    0.00    0.10    0.07    0.04    0.05    0.08    0.08    0.08
 Small Weak           -0.03   0.09    0.00    -0.03   -0.02   0.07    0.07    0.06    0.06    0.06    0.05    0.06
 Small Neutral        0.04    0.04    -0.03    0.00    0.01   0.11    0.09    0.04    0.04    0.07    0.07    0.08

 Big Up               0.10    0.05    -0.06    0.10    0.21   0.16    0.14    0.17    0.14    0.17    0.18    0.17
 Big Down             -0.02   0.09    -0.08   -0.02   0.02    0.08    0.10    0.10    0.07    0.12    0.11    0.09
 Big Medium           -0.01   0.04    -0.06   0.14     0.09   0.17    0.20    0.22    0.21    0.25    0.22    0.19
 Small Up             0.08    0.13     0.10    0.05    0.07   0.16    0.12    0.07    0.06    0.08    0.07    0.10
 Small Down           -0.14   0.04    -0.05   -0.09   -0.05   0.06    0.04    0.01    0.01    0.02    0.01    0.01
 Small Medium         0.05    0.11    0.07    0.08    0.09    0.13    0.15    0.13    0.12    0.14    0.13    0.15


Note: Improvement in annualized Sharpe ratio (SR∗ − SR). We compute the SR∗ by weighting the portfolios based
on a market timing strategy Campbell and Thompson (2007). Cases with Sharpe ratio deterioration are omitted.


purged of market exposure. In all cases, we create the portfolios ourselves using CRSP market eq-
uity value weights. Our portfolio construction differs slightly from the actual S&P 500 index and
the characteristic-based Fama-French portfolios (Fama and French, 1993, 2015), but has the virtue
that we can exactly track the ex ante portfolio weights of each.38
   Table 5 reports the monthly out-of-sample R2 over our 30-year testing sample. Regularized linear
methods fail to outperform naive constant forecasts of the S&P 500. In contrast, all nonlinear models
have substantial positive predictive performance. The one month out-of-sample R2 is 0.71% for the
  38
     Our replication of S&P500 returns has a correlation with the actual index of more than 0.99. For the other
portfolios (SMB, HML, RMW, CMA, UMD), the return correlations between our replication and the version from Ken
French’s website are 0.99, 0.97, 0.95, 0.99, 0.96, respectively.


                                                       39
generalized linear model and reaches as high as 1.80% for the three-layer neural network. As a
benchmark for comparison, nearly all of the macroeconomic return predictor variables in the survey
of Welch and Goyal (2008) fail to produce a positive out-of-sample forecast R2 . Kelly and Pruitt
(2013) find that PLS delivers an out-of-sample forecasting R2 around 1% per month for the aggregate
market index, though their forecasts directly target the market return as opposed to being bottom-
up forecasts. And the most well-studied portfolio predictors, such as the aggregate price-dividend
ratio, typically produce an in-sample predictive R2 of around 1% per month (e.g., Cochrane, 2007),
smaller than what we find out-of-sample.
   The patterns in S&P 500 forecasting performance across models carry over to long-only characteristic-
sorted portfolios (rows 2–25) and long-short factor portfolios (SMB, HML, RMW, CMA, and UMD).
                                                     2 for every portfolio analyzed, with NN3
Nonlinear methods excel. NN3–NN5 produce a positive Roos
                                                 2 for all but UMD (which is by and large the
dominating. NN1 and NN2 also produce a positive Roos
                                                             2 is positive for 22 out of 30 portfolios.
hardest strategy to forecast). The generalized linear model Roos
Linear methods, on the other hand, are on balance unreliable for bottom-up portfolio return fore-
casting, though their performance tends to be better for “big” portfolios compared to “small.” For
select long-short factor portfolios (e.g., SMB), constrained linear methods such as PLS perform com-
paratively well (consistent with the findings of Kelly and Pruitt, 2013). In short, machine learning
methods, and nonlinear methods in particular, produce unusually powerful out-of-sample portfolio
predictions.
   We next assess the economic magnitudes of portfolio predictability. Campbell and Thompson
(2008) show that small improvements in R2 can map into large utility gains for a mean-variance
investor. They show that the Sharpe ratio (SR∗ ) earned by an active investor exploiting predictive
information (summarized as a predictive R2 ) improves over the Sharpe ratio (SR) earned by a
buy-and-hold investor according to
                                                r
                                            ∗       SR2 + R2
                                        SR =                 .
                                                     1 − R2
                                                 2
We use this formula to translate the predictive Roos of Table 5 (along with the full-sample Sharpe
ratio of each portfolio) into an improvement in annualized Sharpe ratio, SR∗ − SR, for an investor
exploiting machine learning predictions for portfolio timing. The results are presented in appendix
Table A.7. For example, the buy-and-hold Sharpe ratio of the S&P 500, which is 0.51 in our 30-year
out-of-sample period, can be improved to 0.71 by a market-timer exploiting forecasts from the NN3
model. For characteristic-based portfolios, nonlinear machine learning methods help improve Sharpe
ratios by anywhere from a few percentage points to over 24 percentage points.
   Campbell and Thompson (2008) also propose evaluating the economic magnitude of portfolio
predictability with a market timing trading strategy. We follow their out-of-sample trading strategy
exactly, scaling up/down positions each month as expected returns rise/fall, while imposing a maxi-
mum leverage constraint of 50% and excluding short sales for long-only portfolios (we do not impose
these constraints for long-short factor portfolios). Table 6 reports the annualized Sharpe ratio gains
(relative to a buy-and-hold strategy) for timing strategies based on machine learning forecasts. Con-

                                                  40
sistent with our other results, the strongest and most consistent trading strategies are those based on
nonlinear models, with neural networks the best overall. In the case of NN3, the Sharpe ratio from
timing the S&P 500 index 0.77, or 26 percentage points higher than a buy-and-hold position. Long-
short factor portfolios are harder to time than the S&P 500 and the other 24 long-only portfolios,
and all methods fail to outperform the static UMD strategy.
   As a robustness test, we also analyze bottom-up predictions for annual rather than monthly
returns. The comparative patterns in predictive performance across methods is the same in annual
and monthly data. Appendix Table A.8 demonstrates the superiority of nonlinear methods, and in
particular neural networks. NN3 continues to dominate for the market portfolio, achieving an annual
 2 of 15.7%.
Roos

3.4.2   Machine Learning Portfolios

Next, rather than assessing forecast performance among pre-specified portfolios, we design a new set
of portfolios to directly exploit machine learning forecasts. At the end of each month, we calculate
one-month-ahead out-of-sample stock return predictions for each method. We then sort stocks into
deciles based on each model’s forecasts. We reconstitute portfolios each month using value weights.
Finally, we construct a zero-net-investment portfolio that buys the highest expected return stocks
(decile 10) and sells the lowest (decile 1).
   Table 7 reports results. Out-of-sample portfolio performance aligns very closely with results on
machine learning forecast accuracy reported earlier. Realized returns generally increase monotoni-
cally with machine learning forecasts from every method (with occasional exceptions, such as decile
8 of NN1). Neural network models again dominate linear models and tree-based approaches. In
particular, for all but the most extreme deciles, the quantitative match between predicted returns
and average realized returns using neural networks is extraordinarily close. The best 10–1 strategy
comes from NN4, which returns on average 2.3% per month (27.1% on an annualized basis). Its
monthly volatility is 5.8% (20.1% annualized), amounting to an annualized out-of-sample Sharpe
ratio of 1.35.
   While value-weight portfolios are less sensitive to trading cost considerations, it is perhaps more
natural to study equal weights in our analysis because our statistical objective functions minimize
equally weighted forecast errors. Appendix Table A.9 reports the performance of machine learning
portfolios using an equal-weight formation. The qualitative conclusions of this table are identical
to those of Table 7, but the Sharpe ratios are substantially higher. For example, the long-short
decile spread portfolio based on the NN4 model earns an annualized Sharpe ratio of 2.45 with equal
weighting. To identify the extent to which equal-weight results are driven by micro-cap stocks, Table
A.10 reports equal-weight portfolio results excluding stocks that fall below the 20th percentile of the
NYSE size distribution. In this case, the NN4 long-short decile spread earns a Sharpe ratio of 1.69.
   As recommended by Lewellen (2015), the OLS-3 model is an especially parsimonious and robust
benchmark model. He also recommends somewhat larger OLS benchmark models with either seven
or 15 predictors, which we report in appendix Table A.11. The larger OLS models improve over



                                                  41
                            Table 7: Performance of Machine Learning Portfolios
                      OLS-3+H                                   PLS                               PCR
            Pred    Avg       Std    SR          Pred    Avg          Std    SR       Pred    Avg          Std    SR
Low(L)      -0.17   0.40      5.90   0.24        -0.83   0.29         5.31   0.19     -0.68   0.03         5.98   0.02
2            0.17   0.58      4.65   0.43        -0.21   0.55         4.96   0.38     -0.11   0.42         5.25   0.28
3            0.35   0.60      4.43   0.47         0.12   0.64         4.63   0.48      0.19   0.53         4.94   0.37
4            0.49   0.71      4.32   0.57         0.38   0.78         4.30   0.63      0.42   0.68         4.64   0.51
5            0.62   0.79      4.57   0.60         0.61   0.77         4.53   0.59      0.62   0.81         4.66   0.60
6            0.75   0.92      5.03   0.63         0.84   0.88         4.78   0.64      0.81   0.81         4.58   0.61
7            0.88   0.85      5.18   0.57         1.06   0.92         4.89   0.65      1.01   0.87         4.72   0.64
8            1.02   0.86      5.29   0.56         1.32   0.92         5.14   0.62      1.23   1.01         4.77   0.73
9            1.21   1.18      5.47   0.75         1.66   1.15         5.24   0.76      1.52   1.20         4.88   0.86
High(H)      1.51   1.34      5.88   0.79         2.25   1.30         5.85   0.77      2.02   1.25         5.60   0.77
H-L         1.67    0.94      5.33   0.61        3.09    1.02         4.88   0.72     2.70    1.22         4.82   0.88
                      ENet+H                               GLM+H                                      RF
            Pred    Avg       Std    SR          Pred    Avg          Std    SR       Pred    Avg          Std    SR
Low(L)      -0.04   0.24      5.44   0.15        -0.47   0.08         5.65   0.05     0.29    -0.09        6.00   -0.05
2            0.27   0.56      4.84   0.40         0.01   0.49         4.80   0.35     0.44     0.38        5.02    0.27
3            0.44   0.53      4.50   0.40         0.29   0.65         4.52   0.50     0.53     0.64        4.70    0.48
4            0.59   0.72      4.11   0.61         0.50   0.72         4.59   0.55     0.60     0.60        4.56    0.46
5            0.73   0.72      4.42   0.57         0.68   0.70         4.55   0.53     0.67     0.57        4.51    0.44
6            0.87   0.85      4.60   0.64         0.84   0.84         4.53   0.65     0.73     0.64        4.54    0.49
7            1.01   0.87      4.75   0.64         1.00   0.86         4.82   0.62     0.80     0.67        4.65    0.50
8            1.16   0.88      5.20   0.59         1.18   0.87         5.18   0.58     0.87     1.00        4.91    0.71
9            1.36   0.80      5.61   0.50         1.40   1.04         5.44   0.66     0.96     1.23        5.59    0.76
High(H)      1.66   0.84      6.76   0.43         1.81   1.14         6.33   0.62     1.12    1.53         7.27   0.73
H-L         1.70    0.60      5.37   0.39        2.27    1.06         4.79   0.76     0.83    1.62         5.75   0.98
                      GBRT+H                                  NN1                                 NN2
            Pred    Avg       Std    SR          Pred    Avg          Std    SR       Pred    Avg          Std    SR
Low(L)      -0.45   0.18      5.60   0.11        -0.38   -0.29        7.02   -0.14    -0.23   -0.54        7.83   -0.24
2           -0.16   0.49      4.93   0.35        0.16    0.41         5.89   0.24     0.21    0.36         6.08   0.20
3            0.02   0.59      4.75   0.43         0.44    0.51        5.07    0.35     0.44   0.65         5.07    0.44
4            0.17   0.63      4.68   0.46         0.64    0.70        4.56    0.53     0.59   0.73         4.53    0.56
5            0.34   0.57      4.70   0.42         0.80    0.77        4.37    0.61     0.72   0.81         4.38    0.64
6            0.46   0.77      4.48   0.59         0.95    0.78        4.39    0.62     0.84   0.84         4.51    0.65
7            0.59   0.52      4.73   0.38         1.11    0.81        4.40    0.64     0.97   0.95         4.61    0.71
8            0.72   0.72      4.92   0.51         1.31    0.75        4.86    0.54     1.13   0.93         5.09    0.63
9            0.88   0.99      5.19   0.66         1.58    0.96        5.22    0.64     1.37   1.04         5.69    0.63
High(H)      1.11   1.17      5.88   0.69         2.19   1.52         6.79   0.77     1.99    1.38         6.98    0.69
H-L         1.56    0.99      4.22   0.81        2.57    1.81         5.34   1.17     2.22    1.92         5.75   1.16
                        NN3                                   NN4                                 NN5
            Pred    Avg       Std    SR          Pred    Avg          Std    SR       Pred    Avg          Std    SR
Low(L)      -0.03   -0.43     7.73   -0.19       -0.12   -0.52        7.69   -0.23    -0.23   -0.51        7.69   -0.23
2            0.34    0.30     6.38    0.16        0.30    0.33        6.16    0.19     0.23    0.31        6.10    0.17
3            0.51    0.57     5.27    0.37        0.50    0.42        5.18    0.28     0.45    0.54        5.02    0.37
4            0.63    0.66     4.69    0.49        0.62    0.60        4.51    0.46     0.60    0.67        4.47    0.52
5            0.71    0.69     4.41    0.55        0.72    0.69        4.26    0.56     0.73    0.77        4.32    0.62
6            0.79    0.76     4.46    0.59        0.81    0.84        4.46    0.65     0.85    0.86        4.35    0.68
7            0.88    0.99     4.77    0.72        0.90    0.93        4.56    0.70     0.96    0.88        4.76    0.64
8            1.00    1.09     5.47    0.69        1.03    1.08        5.13    0.73     1.11    0.94        5.17    0.63
9            1.21    1.25     5.94    0.73        1.23    1.26        5.93    0.74     1.34    1.02        6.02    0.58
High(H)      1.83    1.69     7.29   0.80        1.89    1.75         7.51    0.81     1.99   1.46         7.40   0.68
H-L         1.86    2.12      6.13   1.20        2.01    2.26         5.80   1.35     2.22    1.97         5.93   1.15


Note: In this table, we report the performance of prediction-sorted portfolios over the 30-year out-of-sample testing
period. All stocks are sorted into deciles based on their predicted returns for the next month. Column “Pred”, “Avg”,
“Std”, and “SR” provide the predicted monthly returns for each decile, the average realized monthly returns, their
standard deviations, and Sharpe ratios, respectively. All portfolios are value weighted.


                                                         42
 Table 8: Drawdowns, Turnover, and Risk-adjusted Performance of Machine Learning Portfolios

                 OLS-3    PLS      PCR       ENet    GLM         RF     GBRT     NN1     NN2     NN3      NN4      NN5
                  +H                          +H      +H                 +H

                                                 Drawdowns and Turnover (Value Weighted)
Max DD(%)         69.60    41.13    42.17    60.71   37.09   52.27   48.75     61.60   55.29     30.84    51.78     57.52
Max 1M Loss(%)    24.72    27.40    18.38    27.40   15.61   26.21   21.83     18.59   37.02     30.84     33.03    38.95
Turnover(%)       58.20   110.87   125.86    151.59 145.26 133.87 143.53 121.02 122.46           123.50   126.81   125.37

                                                Drawdowns and Turnover (Equally Weighted)
Max DD(%)         84.74    32.35    31.39    33.70   21.01   46.42   37.19     18.25   25.81     17.34    14.72     21.78
Max 1M Loss(%)    37.94    32.35    22.33    32.35   15.74   34.63   22.34     12.79   25.81     12.50     9.01     21.78
Turnover(%)       57.24   104.47   118.07    142.78 137.97 120.29 134.24 112.35 112.43           113.76   114.17   114.34

                                                 Risk-adjusted Performance (Value Weighted)
Mean Ret.         0.94     1.02     1.22      0.60     1.06     1.62    0.99      1.81    1.92    1.97     2.26     2.12
FF5+Mom α          0.39    0.24     0.62     -0.23      0.38     1.20    0.66     1.20    1.33   1.52      1.76     1.43
t-stats           2.76    1.09     2.89      -0.89     1.68     3.95    3.11      4.68    4.74    4.92     6.00     4.71
R2                78.60   34.95    39.11     28.04     30.78    13.43   20.68    27.67   25.81   20.84    20.47    18.23
IR                 0.54    0.21     0.57     -0.17      0.33     0.77    0.61     0.92    0.93    0.96     1.18     0.92

                                                Risk-adjusted Performance (Equally Weighted)
Mean Ret.         1.34     2.08     2.45     2.11      2.31     2.38    2.14      2.91    3.31   3.27      3.33     3.09
FF5+Mom α          0.83    1.40     1.95     1.32      1.79     1.88     1.87     2.60    3.07   3.02     3.08      2.78
t(α)               6.64    5.90     9.92      4.77     8.09     6.66     8.19    10.51   11.66   11.70    12.28    10.68
R2                84.26   26.27    40.50     20.89    21.25    19.91    11.19    13.98   10.60   9.63     11.57    14.54
IR                 1.30    1.15     1.94     0.93      1.58     1.30     1.60     2.06    2.28    2.29     2.40     2.09


Note: The top two panels report a value-weight and equal-weight portfolio maximum drawdown (“Max DD”), most
extreme negative monthly return (“Max 1M Loss”), and average monthly percentage change in holdings (“Turnover”).
The bottom panel report average monthly returns in percent as well as alphas, information ratios (IR), and R2 with
respect to the Fama-French five-factor model augmented to include the momentum factor.


OLS-3, but are nonetheless handily outperformed by tree-based models and neural networks.
    The top panel of Table 8 reports drawdowns, portfolio turnover, and risk-adjusted performance
of 10–1 spread portfolios from each machine learning model, for both value and equally weighted
strategies. We define maximum drawdown of a strategy as

                                            MaxDD =        max        (Yt1 − Yt2 )
                                                        0≤t1 ≤t2 ≤T


where Yt is the cumulative log return from date 0 through t.
    Not only do neural network portfolios have higher Sharpe ratios than alternatives, they also have
comparatively small drawdowns, particularly for equal-weight portfolios. The maximum drawdown
experienced for the NN4 strategy is 51.8% and 14.7% for value and equal weights, respectively. In
contrast, the maximum drawdown for OLS-3 are 69.6% and 84.7%, respectively. Equal-weight neural
network strategies also experience the most mild one-month losses. For example, for NN4, the worst
one-month performance is a −9.01% return, which is the least extreme monthly loss among all models
with either weighting scheme.


                                                            43
   We define the strategy’s average monthly turnover as

                                        T
                                                                                         !
                                      1X X           wi,t (1 + ri,t+1 )
                           Turnover =      wi,t+1 − P                                        ,
                                      T              j wj,t (1 + rj,t+1 )
                                             t=1     i

where wi,t is the weight of stock i in the portfolio at time t. For NN1 through NN5, turnover is
consistently between 110% and 130% per month, and turnover for tree-based methods and penalized
regression is slightly higher. As a frame of reference, the monthly turnover of a short-term reversal
decile spread is 172.6% per month while for a size decile spread it is 22.9%. Given the large role of
price trend predictors selected by all machine learning approaches, it is perhaps unsurprising that
their outperformance is accomplished with comparatively high portfolio turnover.
   The bottom panel of Table 8 reports risk-adjusted performance of machine learning portfolios
based on factor pricing models. In a linear factor model, the tangency portfolio of the factors
themselves represents the maximum Sharpe ratio portfolio in the economy. Any portfolio with a
higher Sharpe ratio than the factor tangency portfolio possesses alpha with respect to the model.
From prior work, the out-of-sample factor tangency portfolios of the Fama-French three and five-
factor models have Sharpe ratios of roughly 0.8 and 1.3, respectively (Kelly et al., 2019). It is
unsurprising then that portfolios formed on the basis of machine learning forecasts earn large and
significant alphas versus these models. A six-factor model (that appends a momentum factor to
the Fama-French five-factor model) explains as much as 40% of the average return for strategies
based on linear models, but explains only about 10% to 30% of variation in neural network-based
portfolios. As a result, neural networks have information ratios ranging from 0.9 to 2.4 depending
on the number of layers and the portfolio weighting scheme. Test statistics for the associated alphas
are highly significant for both tree models and all neural network models.
   The results of Table 8 are visually summarized in Figure 9, which reports cumulative performance
for the long and short sides for select strategies, along with the cumulative market excess return as
a benchmark. NN4 dominates the other models by a large margin in both directions. Interestingly,
the short side of all portfolios is essentially flat in the post-2000 sample.39
   Finally, we consider two meta-strategies that combine forecasts of all machine learning portfolios.
The first is a simple equally weighted average of decile long-short portfolios from our 11 machine
learning methods. This achieves a stock-level predictive R2 of 0.43% per month and an equally
weighted decile spread Sharpe ratio of 2.49, both of which are higher than any single method on its
own. The value weighted decile spread Sharpe ratio is 1.33, which is slightly lower than that for the
NN4 model.
   The second meta-strategy rotates among machine learning methods by selecting the best machine
learning model for each one-year test sample based on the predictive R2 during the corresponding val-
idation sample. Over our 30-year out-of-sample period, this method selects NN3 11 times, NN1 seven
times, GBRT six times, NN2 five times, and NN4 one time. This method delivers the highest overall
panel R2 (0.45%), but underperforms the standalone NN4 model in terms of decile spread Sharpe
  39
       The corresponding plot of cumulative returns for equal-weight strategies is shown in appendix Figure A.7.



                                                           44
                                  Figure 9: Cumulative Return of Machine Learning Portfolios

                        OLS-3+H   PLS     PCR   ENet+H   GLM+H   RF     GBRT+H    NN4   SP500-Rf   solid = long   dash = short
                 6

                 5

                 4

                 3
Long Position




                 2

                 1

                 0

                 1
Short Position




                 2

                 3

           4
          1987          1990       1993         1996     1999         2002       2005      2008         2011            2014     2016

Note: Cumulative log returns of portfolios sorted on out-of-sample machine learning return forecasts. The solid and
dash lines represent long (top decile) and short (bottom decile) positions, respectively. The shaded periods show NBER
recession dates. All portfolios are value weighted.


ratio (2.42 and 1.23 with equal and value weights, respectively). Interestingly, the meta-strategy’s
predictive R2 gain is statistically insignificant relative to the best standalone neural network models.


4                    Conclusion
Using the empirical context of return prediction as a proving ground, we perform a comparative
analysis of methods in the machine learning repertoire. At the highest level, our findings demonstrate
that machine learning methods can help improve our empirical understanding of asset prices. Neural
networks and, to a lesser extent, regression trees, are the best performing methods. We track down
the source of their predictive advantage to accommodation of nonlinear interactions that are missed
by other methods. We also find that “shallow” learning outperforms “deep” learning, which differs
from the typical conclusion in other fields such as computer vision or bioinformatics, and is likely due
to the comparative dearth of data and low signal-to-noise ratio in asset pricing problems. Machine
learning methods are most valuable for forecasting larger and more liquid stock returns and portfolios.
Lastly, we find that all methods agree on a fairly small set of dominant predictive signals, the most
powerful predictors being associated with price trends including return reversal and momentum. The
next most powerful predictors are measures of stock liquidity, stock volatility, and valuation ratios.
                 The overall success of machine learning algorithms for return prediction brings promise for both
economic modeling and for practical aspects of portfolio choice. With better measurement through
machine learning, risk premia are less shrouded in approximation and estimation error, thus the
challenge of identifying reliable economic mechanisms behind asset pricing phenomena becomes less


                                                                      45
steep. Finally, our findings help justify the growing role of machine learning throughout the archi-
tecture of the burgeoning fintech industry.


References
Bach, Francis R., 2008, Consistency of the group lasso and multiple kernel learning, Journal of
  Machine Learning Research 9, 1179–1225.

Bai, Jushan, and Serena Ng, 2002, Determining the number of factors in approximate factor models,
  Econometrica 70, 191–221.

Bai, Jushan, and Serena Ng, 2013, Principal components estimation and identification of static
  factors, Journal of Econometrics 176, 18–29.

Bai, Zhidong, 1999, Methodologies in spectral analysis of large dimensional random matrices: A
  review, Statistica Sinica 9, 611–677.

Biau, Gérard, 2012, Analysis of a random forests model, Journal of Machine Learning Research 13,
  1063–1095.

Bickel, Peter J, Ya’acov Ritov, and Alexandre B Tsybakov, 2009, Simultaneous analysis of Lasso
  and Dantzig selector, Annals of Statistics 37, 1705–1732.

Bishop, Christopher M., 1995, Neural Networks for Pattern Recognition (Oxford University Press).

Box, G. E. P., 1953, Non-normality and tests on variances, Biometrika 40, 318–335.

Breiman, Leo, 2001, Random forests, Machine learning 45, 5–32.

Breiman, Leo, Jerome Friedman, Charles J Stone, and Richard A Olshen, 1984, Classification and
  regression trees (CRC press).

Bühlmann, Peter, and Torsten Hothorn, 2007, Boosting Algorithms: Regularization, Prediction and
  Model Fitting, Statistical Science 22, 477–505.

Bühlmann, Peter, and Bin Yu, 2003, Boosting with the l2 loss, Journal of the American Statistical
  Association 98, 324–339.

Butaru, Florentin, Qingqing Chen, Brian Clark, Sanmay Das, Andrew W Lo, and Akhtar Siddique,
  2016, Risk and risk management in the credit card industry, Journal of Banking & Finance 72,
  218–239.

Campbell, John Y., and S. B. Thompson, 2008, Predicting excess stock returns out of sample: Can
  anyting beat the historical average?, Review of Financial Studies 21, 1509–1531.

Campbell, John Y, and Samuel B Thompson, 2007, Predicting excess stock returns out of sample:
  Can anything beat the historical average?, The Review of Financial Studies 21, 1509–1531.

Chen, Tianqi, and Carlos Guestrin, 2016, Xgboost: A scalable tree boosting system, in Proceedings
  of the 22Nd ACM SIGKDD International Conference on Knowledge Discovery and Data Mining,
  KDD ’16, 785–794 (ACM, New York, NY, USA).




                                                46
Chizat, Lénaı̈c, and Francis Bach, 2018, On the global convergence of gradient descent for over-
  parameterized models using optimal transport, in Proceedings of the 32Nd International Confer-
  ence on Neural Information Processing Systems, NIPS’18, 3040–3050 (Curran Associates Inc.,
  USA).

Cochrane, John H, 2007, The dog that did not bark: A defense of return predictability, The Review
  of Financial Studies 21, 1533–1575.

Cybenko, George, 1989, Approximation by superpositions of a sigmoidal function, Mathematics of
  control, signals and systems 2, 303–314.

Daubechies, I, M Defrise, and C De Mol, 2004, An iterative thresholding algorithm for linear inverse
 problems with a sparsity constraint, Communications on Pure and Applied Mathematics 57, 1413–
 1457.

de Jong, Sijmen, 1993, Simpls: An alternative approach to partial least squares regression, Chemo-
  metrics and Intelligent Laboratory Systems 18, 251 – 263.

Diebold, Francis X., 2015, Comparing predictive accuracy, twenty years later: A personal perspective
  on the use and abuse of diebold-mariano tests, Journal of Business & Economic Statistics 33, 1–9.

Diebold, Francis X., and Roberto S. Mariano, 1995, Comparing predictive accuracy, Journal of
  Business & Economic Statistics 13, 134–144.

Dietterich, Thomas G, 2000, Ensemble methods in machine learning, in International workshop on
  multiple classifier systems, 1–15, Springer.

Dimopoulos, Yannis, Paul Bourret, and Sovan Lek, 1995, Use of some sensitivity criteria for choosing
  networks with good generalization ability, Neural Processing Letters 2, 1–4.

Eldan, Ronen, and Ohad Shamir, 2016, The power of depth for feedforward neural networks, in
  Vitaly Feldman, Alexander Rakhlin, and Ohad Shamir, eds., 29th Annual Conference on Learning
  Theory, volume 49 of Proceedings of Machine Learning Research, 907–940 (PMLR, Columbia
  University, New York, New York, USA).

Fama, Eugene F, and Kenneth R French, 1993, Common risk factors in the returns on stocks and
  bonds, Journal of financial economics 33, 3–56.

Fama, Eugene F, and Kenneth R French, 2008, Dissecting anomalies, The Journal of Finance 63,
  1653–1678.

Fama, Eugene F., and Kenneth R. French, 2015, A five-factor asset pricing model, Journal of Fi-
  nancial Economics 116, 1–22.

Fan, Jianqing, Quefeng Li, and Yuyan Wang, 2017, Estimation of high dimensional mean regression
  in the absence of symmetry and light tail assumptions, Journal of the Royal Statistical Society, B
  79, 247–265.

Fan, Jianqing, Cong Ma, and Yiqiao Zhong, 2019, A selective overview of deep learning, Technical
  report, Princeton University.

Feng, Guanhao, Stefano Giglio, and Dacheng Xiu, 2019, Taming the factor zoo: A test of new factors,
  Journal of Finance, forthcoming .


                                                47
Freund, Yoav, 1995, Boosting a weak learning algorithm by majority, Information and Computation
  121, 256–285.

Freyberger, Joachim, Andreas Neuhierl, and Michael Weber, 2019, Dissecting characteristics non-
  parametrically, Review of Financial Studies, forthcoming .

Friedman, Jerome, Trevor Hastie, Holger Höfling, Robert Tibshirani, et al., 2007, Pathwise coordi-
  nate optimization, The Annals of Applied Statistics 1, 302–332.

Friedman, Jerome, Trevor Hastie, and Robert Tibshirani, 2000a, Additive logistic regression: A
  statistical view of boosting, Annals of Statistics 28, 337–374.

Friedman, Jerome, Trevor Hastie, and Robert Tibshirani, 2000b, Additive logistic regression: a
  statistical view of boosting (with discussion and a rejoinder by the authors), Annals of Statistics
  28, 337–407.

Friedman, Jerome H, 2001, Greedy function approximation: a gradient boosting machine, Annals of
  statistics 1189–1232.

Giglio, Stefano W, and Dacheng Xiu, 2016, Asset pricing with omitted factors, Technical report,
  University of Chicago.

Glorot, Xavier, Antoine Bordes, 