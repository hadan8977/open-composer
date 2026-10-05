source: https://nber.org/system/files/working_papers/w33012/w33012.pdf
fetched_utc: 2026-10-04T18:39:04Z
bytes_raw: 6290405

NBER WORKING PAPER SERIES




    APT OR “AIPT”? THE SURPRISING DOMINANCE OF LARGE FACTOR MODELS

                                        Antoine Didisheim
                                        Shikun (Barry) Ke
                                         Bryan T. Kelly
                                        Semyon Malamud

                                       Working Paper 33012
                               http://www.nber.org/papers/w33012


                      NATIONAL BUREAU OF ECONOMIC RESEARCH
                                1050 Massachusetts Avenue
                                  Cambridge, MA 02138
                           September 2024, Revised August 2025



A previously circulated version of this article was titled “Complexity in Factor Pricing Models.”
Antoine Didisheim is at the University of Melbourne. Shikun Ke is at Yale School of
Management. Bryan Kelly is at Yale School of Management, AQR Capital Management, and
NBER; www.bryankellyacademic.org. Semyon Malamud is at Swiss Finance Institute, EPFL, and
CEPR, and is a consultant to AQR. We are grateful for helpful comments from Federico Baldi-
Lanfranchi, John Campbell, Mike Chernov, Xavier Gabaix, Martin Lettau, Stefan Nagel,
Mohammad Pourmohammadi, Seth Pruitt, Mirela Sandulescu, Paul Schneider, Fabio Trojani, Neng
Wang, and participants at many seminars and conferences. Semyon Malamud gratefully
acknowledges the financial support of the Swiss Finance Institute and the Swiss National Science
Foundation, Grant 100018 192692. AQR Capital Management is a global investment management
firm that may or may not apply similar investment techniques or methods of analysis as described
herein. The views expressed here are those of the authors and not necessarily those of AQR or the
National Bureau of Economic Research.

NBER working papers are circulated for discussion and comment purposes. They have not been
peer-reviewed or been subject to the review by the NBER Board of Directors that accompanies
official NBER publications.

© 2024 by Antoine Didisheim, Shikun (Barry) Ke, Bryan T. Kelly, and Semyon Malamud. All
rights reserved. Short sections of text, not to exceed two paragraphs, may be quoted without explicit
permission provided that full credit, including © notice, is given to the source.
APT or “AIPT”? The Surprising Dominance of Large Factor Models
Antoine Didisheim, Shikun (Barry) Ke, Bryan T. Kelly, and Semyon Malamud
NBER Working Paper No. 33012
September 2024, Revised August 2025
JEL No. C1, C40, C45, C55, G1, G11, G12, G14, G17

                                          ABSTRACT

We introduce artificial intelligence pricing theory (AIPT). In contrast with the APT’s foundational
assumption of a low dimensional factor structure in returns, the AIPT conjectures that returns are
driven by a large number of factors. We first verify this conjecture empirically and show that
complex nonlinear models with an exorbitant number of factors (many more than the number of
training observations or base assets) are far more successful in describing the out-of-sample
behavior of asset returns than simpler benchmark models. Economically, we show that complex
models are more than twice as sensitive to long-run macroeconomic activity than simpler
benchmarks. Finally, we theoretically characterize the behavior of large factor pricing models, from
which we show that the AIPT’s “many factors” conjecture faithfully explains our empirical
findings, while the APT’s “few factors” conjecture is contradicted by the data.


Antoine Didisheim                                Bryan T. Kelly
Department of Finance, University                Yale University
    of Lausanne                                  and NBER
Department of Finance                            bryan.kelly@yale.edu
antoine.didisheim@unimelb.edu.au
                                                 Semyon Malamud
Shikun (Barry) Ke                                Swiss Finance Institute
Yale University                                  semyon.malamud@epfl.ch
Yale School of Management
barry.ke@yale.edu
1        Introduction

Ross’s (1976) APT conjectures that a small number of common factors govern the joint
variation of returns. This premise, combined with no-arbitrage arguments, delivers the
prediction that assets’ expected returns are determined by exposures to a few common
factors. Most empirical investigations of the risk-return tradeoff in the past fifty years have
occurred within the confines of the APT’s assumption—small linear factor models.
        In this paper, we consider a different conjecture: that asset pricing models with an
exorbitant number of factors are better suited to describe the behavior of asset returns. Our
conjecture is rooted in the burgeoning theory of artificial intelligence, which suggests that
“complex” statistical models, those with many more parameters (P ) than available training
observations (T ), tend to achieve better out-of-sample success than smaller models.1 Given
its origins, we refer to this conjecture as artificial intelligence pricing theory, or AIPT, to
contrast it with the parsimony assumption at the heart of the APT.
        One reason for the APT’s position as a cornerstone of empirical asset pricing is the
convenience of working with small linear factor models. The most obvious convenience
stems from the tractability of estimating small models. More subtle is the convenience of
comparing small models. The APT sets up conditions necessary for comparing models based
on in-sample test statistics (namely, that the number of parameters is small compared to the
number of training observations). Large factor models, on the other hand, are admittedly
inconvenient. With so many parameters, they can be costly to train, and due to their high
    1
    See, among others, Hastie et al. (2019), Bartlett et al. (2020), and Kelly et al. (2024b). Following these
papers, we define model complexity as the ratio of factor dimension to the number of training observations
c = P/T . Our theoretical derivations rely crucially on the ratio c, hence our focus on this definition of
complexity. The statistics literature proposes and analyzes other measures of model complexity as well, each
capturing somewhat different qualities. As noted by Bartlett et al. (2020): “The classical perspective in
statistical learning theory is that there should be a tradeoff between the fit to the training data and the
complexity of the prediction rule. Whether complexity is measured in terms of the number of parameters,
the number of nonzero parameters in a high-dimensional setting, the number of neighbors averaged in a
nearest neighbor estimator, the scale of an estimate in a reproducing kernel Hilbert space, or the bandwidth
of a kernel smoother, this tradeoff has been ubiquitous in statistical learning theory.”



                                                      2
statistical complexity, standard in-sample asset pricing tests are not applicable. Instead,
they require out-of-sample model performance comparisons.
      We show that, despite their inconveniences, large factor models are far better at pricing
assets than the standard low-dimensional factor models in the literature. In the first half
of this paper, we present extensive empirical evidence that challenges the APT parsimony
conjecture and favors the complexity conjecture of AIPT. In the second half of the paper
we develop a statistical theory that characterizes the behavior of complex factor models and
rationalizes their surprising dominance in pricing assets.


1.1     Empirical Behavior of Large Factor Models

Our central empirical finding is that the out-of-sample performance of factor pricing models
is increasing in the number of factors. We focus on two metrics of model performance— the
Sharpe ratio of the tangency portfolio among factors and the magnitude of pricing errors
among test assets.
      Our analysis gradually increases the number of factors while holding the underlying
information set fixed. The information set includes 130 well-known characteristics that
predict the cross-section of US stocks. To vary the number of pricing factors, we use a
neural network to generate new stock characteristics—up to hundreds of thousands—that are
nonlinear transformations of the original 130 variables. For each nonlinear characteristic, we
build the corresponding factor (using a standard characteristic-managed portfolio approach).
Training the factor model amounts to building the stochastic discount factor (SDF) as the
tangency portfolio of factors (using ridge shrinkage where applicable). We then track the
complex SDF’s performance out-of-sample, presenting our main empirical results in the
form of “VoC curves” (Kelly et al., 2024b, KMZ henceforth) that plot performance as a
function of the number of factors. These curves document a “virtue of complexity” in factor
pricing models, with out-of-sample Sharpe ratios increasing and pricing errors decreasing



                                                3
as we expand the number of factors. The complex SDF performs well even when—in fact,
especially when—P far exceeds T .
      Large factor models outperform well-known, low-dimensional factor models from the
literature by a wide margin. For example, the largest model we consider (with 360,000
factors, or a complexity ratio of 1,000 given our 360-month rolling training window) reduces
pricing errors by 54.8% relative to the six-factor Fama and French (2015) model (including
momentum) and by 50.4% relative to the five-factor Hou et al. (2021) model. Meanwhile,
our largest factor model produces an out-of-sample tangency Sharpe ratio of 3.7, compared
to 0.8 and 1.2 for the aforementioned benchmarks, respectively.2
      Improvements in SDF measurement achieved by large factor models offer a window into
the economic nature of the unobservable “true” SDF. We argue that the higher an SDF’s out-
of-sample Sharpe ratio, the better it reflects the drivers of investors’ intertemporal marginal
rate of substitution, and thus the better it should reflect expectations of future economic
conditions. In other words, portfolio efficiency and informational efficiency go hand-in-hand.
      We estimate a macroeconomic vector autoregression and find that the complex SDF is an
unusually strong forecaster of macroeconomic conditions as far as three years into the future.
For example, a positive one standard deviation annual return to the complex SDF predicts a
roughly 3% rise in industrial production over three years and a reduction in macroeconomic
uncertainty of about 7.5% over two years. A positive SDF return also predict significant
increases in employment, consumption, consumer sentiment, and housing over horizons of
up to three years, and it predicts a decrease in credit spreads and inflation.
      The asset pricing benefits of complexity and nonlinearity accrue even when the condition-
ing information set is relatively small. For example, we construct a “nonlinear Fama-French
model” using a large set of nonlinear factors derived from only five characteristics: size, value,
investment, profitability, and momentum, rather than the full set of 130 characteristics in our
main analysis. The added complexity more than doubles the out-of-sample tangency Sharpe
  2
      We study a number of additional benchmark models as well.


                                                   4
ratio relative to the baseline Fama-French model. The same result obtains for complex
nonlinear versions of other benchmark models in the literature.
      The insights of Kozak et al. (2020) suggest that a successful asset pricing model may not
require many factors because the returns of most anomaly factors are adequately explained
by a small number of their principal components. This begs the question: Can our complex
pricing model be compressed to achieve similar performance with potentially many fewer
parameters?      Evidently, the answer is no.       We consider replacing the large number of
factors in our complex model with a smaller number of their principal components and
find that dimension reduction significantly impairs out-of-sample performance relative to
the full complex model.
      Lastly, we conduct a variety of robustness analyses that consider different input char-
acteristics, various subsets of the stock universe, different training windows, and so forth.
Every robustness test reinforces our main findings. In summary, we establish the empirical
fact that large factor models are better at pricing assets than existing parsimonious models.


1.2     Theoretical Findings

In order to understand our empirical findings, we develop a statistical theory of large factor
pricing models. Consider the following interpretation of a large factor model from the asset
pricing theory perspective of an SDF. A conditional SDF can be represented as a tradable
portfolio of risky assets:


        Mt+1 = 1 − w(Zt )′ Rt+1 .                                                           (1)


Rt+1 contains excess returns of risky assets, and w(Zt ) are the SDF’s weights on those
assets. The weights are determined by variables Zt that span the time t information set.
Without further guidance about the functional form of w, a machine learning-based empirical
approach would approximate the SDF with a nonparametric model such as a shallow neural

                                                5
                      PP
network: w(Zt ) ≈         p=1 λp Sp (Zt ), where each Sp (Zt ) is some nonlinear basis function of Zt .

Thus, a neural network SDF delivers a linear factor pricing model,

                      X
         Mt+1 ≈ 1 −       λp Fp,t+1 ,                                                                   (2)
                      p


where each “factor” Fp,t+1 is a characteristic-managed portfolio that uses the transformed
“characteristics” Sp (Zt ) as portfolio weights, and λ = (λ1 , ..., λP ) are parameters to be
estimated.
       This formulation captures the tension in machine learning asset pricing models. On the
one hand, the more terms in the nonparametric representation of w (and thus the larger
the number of factors), the better the model can approximate the true SDF. But as we
improve the approximation, we simultaneously increase the number of parameters that must
be estimated, so when P becomes large, the estimated model may be unstable and suffer
out-of-sample. Our theory makes it possible to understand (and quantitatively characterize)
this cost/benefit tradeoff in large factor models. This is non-trivial and requires our novel
random matrix theory (RMT) results that allow us to tackle the “three infinities” problem
(when the number of assets, observations, and parameters are simultaneously large).3
       On the cost side of the tradeoff is a phenomenon we refer to as “limits to learning.”
In low complexity settings—with many more observations than parameters to estimate—
the law of large numbers kicks in, and appropriate estimators can recover the true model.4
Traditional econometric theory deals with estimator behavior in this data-rich environment.
By contrast, in high-complexity settings, the number of factors is large relative to the number
of observations. Thus, the law of large numbers breaks down. Even correctly specified
estimators fail to converge on the true model because there is not enough data to go around.
The first key aspect of our theory is an explicit characterization of the limits to the learning
   3
    Established RMT results (e.g., those from Hastie et al., 2019) are insufficient in our context.
   4
    I.e., if the model is correctly specified. If the model is mis-specified, estimators recover the nearest
“pseudo-true” parameters (e.g. White, 1996).


                                                     6
effect. We prove that data limitations impose an unavoidable implicit shrinkage of the model,
which depresses the model’s expressive power. Complexity induces bias through its implicit
shrinkage. But on the benefit side of the tradeoff, complexity also reduces specification bias.
More factors lead to a more accurate approximation of the true SDF. Our main theoretical
result shows that which effect dominates depends on the eigenvalue distribution of the factors.
When there is a concentrated eigenvalue distribution and thus a few dominant factors, asset
pricing model performance tops out after adding only a few factors, and there is no virtue
of complexity—a counterfactual prediction in light of our empirical findings.
       However, when the underlying factor structure is not too concentrated—that is, when the
data-generating process aligns with the AIPT conjecture—a virtue of complexity emerges
that closely mimics the patterns we find in the data. Our theory rationalizes our surprising
empirical facts, demonstrating that even if arbitrage is absent and an SDF exists, it is
possible to continually find new empirical “risk” factors that are unpriced by others and that
adding these factors to the pricing model continually improves its out-of-sample performance.
The theory also helps rationalize the prominence of “anomaly” portfolios in empirical asset
pricing. The abundance of anomalies (the so-called “factor zoo”) is not a puzzle to be solved
or evidence of a corrupt research process.5 Instead, it is the theoretically expected outcome
in a complex asset pricing environment because data limitations hamper our ability to learn
the true nature of markets. In fact, our theory argues that the extant factor zoo is too small
and that an SDF model can be beneficially expanded to incorporate a teeming Noah’s ark
of factors by transforming raw asset characteristics into a wide variety of nonlinear signals
(buttressed by appropriate shrinkage). Such a large factor set improves the out-of-sample
SDF Sharpe ratio and reduces out-of-sample pricing errors.
   5
     Jensen et al. (2023) reach a similar conclusion based on the rationale that the risk-return trade-off is
difficult to measure and complexity manifests as an inability to find a single silver-bullet characteristic that
pins down expected returns. Instead, researchers gradually expand and refine the set of noisy signals and
conclude “a more positive take on the factor zoo is not as a collective exercise in data mining and false
discovery, but rather as a natural outcome of a decentralized effort in which researchers make contributions
that are correlated with, but incrementally improve on, the body of knowledge.”



                                                       7
1.3      Literature Review

This paper is related to an emergent literature that shows machine learning asset pricing
models achieve higher out-of-sample Sharpe ratios and smaller pricing errors than their
parsimonious predecessors. Examples include Kozak et al. (2020), Gu et al. (2020a), Chen
et al. (2023), Bryzgalova et al. (2020), Cong et al. (2022), Fan et al. (2022) and Preite
et al. (2022), among others. It also relates to machine learning methods for analyzing
factor models, including Connor et al. (2012), Fan et al. (2016), Kelly et al. (2020), Lettau
and Pelger (2020), Giglio and Xiu (2021), Giglio et al. (2022), and He et al. (2023) (see
Kelly and Xiu (2023) and Rapach and Zhou (2020) for more complete survey treatments of
these topics). We extend this literature with detailed documentation of the counterintuitive
phenomenon that out-of-sample asset pricing model performance appears to improve with
ever richer model specifications.
       An understanding of this surprising empirical phenomenon is only beginning to take
shape. KMZ theoretically analyze machine learning models for return prediction. We
extend this work in a number of ways, including reorienting the statistical objective around
minimizing pricing errors and maximizing SDF Sharpe ratios, and by moving from a single
asset to a cross-section of assets.6 Together with Martin and Nagel (2021), Da et al. (2022),
Fan et al. (2022), and KMZ, our paper belongs to an emergent literature analyzing “limits to
learning” in high-dimensional asset pricing models. Our paper also relates to the theoretical
   6
     From a technical standpoint, we overcome a number of new theoretical hurdles relative to KMZ. In time
series regressions of KMZ, the random matrix behavior of time series signal covariances dictates the market
timing strategies. In the panel problem, behavior is determined not just by time series covariances but also by
the covariance of signals across assets. While standard random matrix theory in KMZ requires dealing with
double limits (number of observations and number of parameters), our analysis requires the development
of a non-trivial theoretical extension to deal with a third limiting dimension—the number of base assets.
This contrasts with recent results of Martin and Nagel (2021), who lack the time dimension and assume
that all stock characteristics are constant. Such an assumption implies that factors (characteristics-managed
portfolios) are, in fact, static portfolios of stocks. In particular, the number of factors in their setting is
always smaller than the number of stocks. Importantly, we also remove the equal ex-ante predictive power
assumption of KMZ and allow for a generic distribution of risk premia across factors.




                                                      8
machine learning literature on topics surrounding “double descent” and “benign overfit” (e.g.
Spigler et al., 2019; Hastie et al., 2019; Belkin et al., 2020; Bartlett et al., 2020).
       A related empirical literature analyzes the association between asset returns and future
macroeconomic conditions. Parker and Julliard (2005) and Croce et al. (2023) show that
stock returns covary with future consumption growth.7 Bryzgalova et al. (Forthcoming) and
Dew-Becker and Giglio (2016) use returns to identify the role of long-lived consumption risks
for pricing assets. Backus et al. (2007) show that equity returns lead GDP growth by a few
quarters. We add to this literature in a number of ways. First, our complex SDF forecasts
future not just consumption and output, but a wide range of macroeconomic activity and
conditions. The macro predictability arising from our model is larger in magnitude than
that of benchmark factor models in the literature. A particularly important new finding is
our complex SDF’s strong predictability for macroeconomic uncertainty, giving credence to
popular consumption-based asset pricing models with stochastic macroeconomic volatility
(e.g. Bansal and Yaron, 2004; Campbell et al., 2018). In contrast, none of the standard
benchmarks demonstrate any ability predict macroeconomic uncertainty.8
       Through its coupling with the literature on factor pricing models, our work also relates
to the empirical literature surrounding the “factor zoo” and factor replicability, including
Harvey et al. (2016), McLean and Pontiff (2016), Hou et al. (2020), Feng et al. (2020),
Jensen et al. (2023), and Chen and Zimmermann (2021). Our theory helps rationalize the
continued discovery of factors that are unspanned by simpler precedent models. Relatedly,
the demonstrated success of machine learning models in predicting the cross-section of
returns such as Chinco et al. (2019), Han et al. (2019), Freyberger et al. (2020), Rapach
and Zhou (2020), Gu et al. (2020b), Avramov et al. (2023), and Guijarro-Ordonez et al.
(2021), is additional evidence of the virtue of complexity in financial markets research.
       The remainder of the paper proceeds by introducing our empirical design in Section 2
   7
    Chernov et al. (2023) demonstrate that currency returns are also predictive of future consumption.
   8
    Relatedly, Bryzgalova et al. (Forthcoming) point out that consumption volatility shocks are conspicuously
absent from their estimation of the risk-return tradeoff.


                                                     9
and our empirical findings in Section 3. Section 4 presents our theoretical analysis of large
factor models, and Section 5 concludes.


2        Empirical Framework

We now present the details of our empirical framework for large factor pricing models and
their associated SDF representations.


2.1       Background: Factor Models and the SDF

Hansen and Richard (1987) show that a true SDF, if one exists, is representable as a tradable
portfolio of risky assets as introduced in Equation (1).
        A factor pricing model is equivalent to an SDF that is linear in the factors. We can,
therefore, analyze and compare asset pricing factor models as competing SDF specifications.
Motivated by the APT and the principle of parsimony,9 the literature has primarily
investigated (1) with tightly constrained factor specifications of the SDF weight function
w(Zt ). A leading example is the Fama and French (1993) model, which restricts Mt+1 to be
a three-parameter model:


          wiFF = c1 MKTi + c2 SIZEi + c3 VALUEi ,


where the weight of asset i in the Fama-French SDF (wiFF ) depends only on the stock’s
weight in the market portfolio (MKTi ) and on researcher-dictated functions of the stock’s
size and book-to-market ratio (SIZEi and VALUEi ).
        The Fama-French SDF portfolio can equivalently (and more familiarly) be viewed as a
    9
    See, e.g., Tukey (1961) and Box and Jenkins (1970). Economic theory also motivates functional
restrictions on the SDF (e.g. Hansen and Singleton, 1982). However, restrictions derived from economic
theory have had limited success to date in pricing cross-sections of assets such as stocks, bonds, and
derivatives. The Fama-French SDF and many other factor models in the literature are motivated by empirical
“anomalies” vis-a-vis the CAPM and not by a particular economic theory.



                                                   10
linear combination of three factors. The factors are portfolios whose individual stock weights
are given by MKTi , SIZEi , and VALUEi , respectively. The SDF combines these factors with
three parameters, c1 , c2 , and c3 , corresponding to the Sharpe ratio maximizing combination
of the factors. These are the only three parameters that must be estimated in the Fama-
French SDF, resulting in an extraordinarily parsimonious asset pricing model. Thus, the
Fama-French model is a special case of (1) where


        w(ZtF F ) = ZtF F λF F .


The conditioning set is ZtF F , which has D = 3 columns containing stocks’ Fama-French
characteristics, and the weight function is linear in parameters λF F = (c1 , c2 , c3 )′ . In this
case, the SDF is

                          ′        ′
        MtFF = 1 − λF F ZtF F Rt+1 ,


                                       ′
where we recognize that ZtF F Rt+1 is a vector of time t returns on the three Fama-French
factors and 1 − MtFF is their mean-variance efficient combination.


2.2     Designing A Large Factor Model

The Fama-French model achieves its parsimony from rigid assumptions on the SDF weighting
function—discarding all but a few conditioning variables and making detailed choices for the
functional form that maps the selected variables into SDF weights.
      The AIPT takes a different approach, founded on the philosophy of machine learning,
and explores the benefits of flexible models that accommodate many potential conditioning
variables and diverse functional forms. In our analysis, Zt is an Nt × D matrix that collects
a large number of D conditioning variables for each risky asset. We derive a complex
factor pricing model by replacing detailed specification choices with a generic nonparametric


                                               11
approximation to the unknown SDF:

                 P
                 X
      w(Zt ) ≈         λp Sp (Zt ) = St λ,                                                     (3)
                 p=1



where each Sp (Zt ) is an Nt ×1 nonlinear basis function of the input data Zt and λp is a scalar
basis coefficient. This basis expansion explores the space of potential shapes for w(Zt ), then
combines these building blocks with coefficients (λp ) that best reconstruct the unknown
function w(Zt ). Collecting the P basis terms into an Nt × P matrix of characteristics
St = [S1,t , ..., SP,t ], and collecting parameters λ = [λ1 , ..., λP ]′ , we arrive at St λ as the
nonparametric approximation to the true SDF weighting function. The larger is P , the
broader the set of nonlinearities considered, the larger the number of model parameters, and
the more flexible the approximation.
   The nonparametric approximation in (3) takes the same basic form as the Fama-French
SDF with St in place of ZtF F . The basis terms Sp (Zt ) merely transform conditioning variables
into a large number of new nonlinear asset “characteristics” analogous to those underpinning
the Fama-French model. Substituting the approximation in (3) into the SDF definition (1),
we arrive at


      Mt+1 ≈ 1 − λ′ St′ Rt+1 = 1 − λ′ Ft+1 = 1 − Rt+1
                                                  M
                                                      .                                        (4)


                                                                        M
In other words, like the Fama-French model, the SDF portfolio (denoted Rt+1 = λ′ Ft+1 ) is a
linear combination of factor portfolios,


      Ft+1 = St′ Rt+1 .                                                                        (5)


Each factor Fp,t+1 = Sp (Zt )′ Rt+1 is a characteristic-managed portfolio of risky assets that
uses the nonlinear asset “characteristic” Sp (Zt ) as the vector of portfolio weights, and again λ



                                                12
is the mean-variance efficient combination of factors.10 The difference vis-a-vis Fama-French
(and other parsimonious models) is that the factors in (4) make flexible and nonlinear use
of conditioning data, and there are a large number P of these factors.


2.3      Random Fourier Factors

To operationalize this large factor model approximation of the SDF, our empirical approach
adapts the method of random Fourier features, or RFF (Rahimi and Recht, 2007).11 While
(Rahimi and Recht, 2007) propose RFF for predictive regression, our approach embeds RFF
in an SDF. The nonlinear basis functions in this method are trigonometric transformations
of the original signals Zt :


 [S2p−1,t S2p,t ] ∈ RNt ×2 = [sin(γZt ωp ), cos(γZt ωp )]′ ,    ωp ∼ i.i.d. N (0, I),     p = 1, ..., P/2. (6)


Each RFF basis function forms a random linear combination (ωp ) of the raw characteristics
Zt , then feeds this through sine and cosine activation functions.12 The transformation is
applied stock-by-stock, converting stock i’s characteristics into new nonlinear characteristics
that include not just transformations of each individual characteristic but general multi-way
interactive effects involving all characteristics for stock i.
       Upon closer inspection, we see that the SDF in (4) is, in fact, a two-layer neural
network with input parameters given by ωp , output parameters given by λ, and trigonometric
activation neurons (see Figure 1). In a typical neural network, both the input and output
parameters are estimated using computationally costly numerical methods. The fascinating
insight of (Rahimi and Recht, 2007) is that, by using randomization to fix the input
  10
     Because the size of the cross-section varies over time, our empirical analysis in fact scales the factors as
          −1/2 ′
Ft+1 = Nt      St Rt+1 to maintain a relatively consistent scale of factor returns over time.
  11
     In Section 3.8 we demonstrate the robustness of our findings to other complex model specifications.
  12
     The parameter γ controls the Gaussian kernel bandwidth in generating random Fourier features.
Following Kelly et al. (2022), we randomly chose γ from the grid [0.5, 0.6, 0.7, 0.8, 0.9, 1.0] for each ωi that
we generate. This embeds varying degrees of nonlinearity in the generated feature set St .



                                                       13
                                                                                    ′ λ
                                                                            wi,t =Si,t
                                                                      nh                        ioP
                                                                             ′ ω ), cos(γZ ′ ω )
                                                                Si,t = sin(γZi,t  p       i,t p
                                                                                                       p=1
                                                                                 Zi,t

              Figure 1: Neural Network Representation of Random Fourier Factors
Note. Illustration of nonlinear mapping from stock i’s characteristics Zi,t into hidden layer neurons Si,t
and then into the conditional SDF weight wi,t during the construction of random Fourier factors.



parameters and only estimating the output parameters, random features regression can build
nonparametric approximations in a computationally efficient manner.13 Building on this
insight, our SDF model is estimable in closed form using only least squares regression (as
discussed below).
       RFF is an ideal tool for our analysis because, from a fixed input data set Zt we can create
asset pricing models with any desired factor dimension, P . For a low-dimensional model of,
say, P = 2, one generates a single pair of RFFs. For a high-dimensional model of, say,
P = 10,000, one can instead draw many random weight vectors ωp , p = 1, ..., 5,000. This
gives us the ability to evaluate how asset pricing models are impacted by varying the number
of factors while holding the set of conditioning variables fixed. It is important to emphasize
that in our analysis, factor proliferation arises not from expanding the set of input data Zt
(which may or may not be low-dimensional) but instead from generating many nonlinear
basis transformations of Zt .


2.4      Estimator

The SDF coefficient vector λ represents the mean-variance efficient portfolio of factors. Note
that the factor representation of the conditional SDF in essence produces an equivalent
unconditional SDF. This allows us to estimate λ as the sample Markowitz portfolio of factors:
  13
     Indeed, RFF is a special case of kernel regression. For applications of kernel regression in asset pricing
settings, see Kozak (2020) and Kelly et al. (2024a).




                                                      14
                                    
                  ′      1  ′ 2
      arg max Ê[λ Ft ] − Ê (λ Ft )   = Ê[Ft Ft′ ]−1 Ê[Ft ]                              (7)
           λ             2

where Ê denotes the training sample mean. We denote the corresponding estimated SDF
and SDF portfolio as


      M̂t = 1 − R̂tM   and    R̂tM = λ̂′ Ft .                                               (8)


   The AIPT explores large factor models in which the dimension of λ may exceed the
number of time series observations, i.e., P > T . In this case, Ê[Ft Ft′ ]−1 is rank-deficient,
which we resolve by introducing a ridge penalty in the Markowitz problem:

                                                                    −1
                                 1  ′ 2
                          ′
      λ̂(z) = arg max Ê[λ Ft ] − Ê (λ Ft ) − zλ λ = zI + Ê[Ft Ft′ ]
                                                 ′
                                                                           Ê[Ft ]          (9)
                   λ             2

where z is the ridge parameter.
   Kozak et al. (2020) point out that we can also interpret λ̂(z) in terms of “pricing errors.”
Since the factors Ft are tradable assets, the true SDF Mt prices these factors with zero error
due to the marginal investor’s first-order optimality condition:


      E[Mt Ft ] = 0.                                                                       (10)


Hansen and Jagannathan (1997) suggest a statistic for comparing the efficacy of SDF
models in terms of their pricing error magnitudes. For a candidate SDF M̃t , The Hansen-
Jagannathan distance (HJD) is a weighted sum of squared pricing errors for the set of test




                                                15
assets Ft :14


         DHJ = E[M̃t Ft ]′ E[Ft Ft′ ]−1 E[M̃t Ft ].                                                    (11)


Substituting the SDF approximation model (4) for M̃ in the HJD and adding a ridge penalty
to handle rank deficiency when P > T , we have

                        n                                                              o
         λ̂(z) = arg min Ê[(1 − λ′ Ft )Ft ]′ Ê[Ft Ft′ ]−1 Ê[(1 − λ′ Ft )Ft ] + zλ′ λ .              (12)
                       λ



In other words, λ̂(z) is also the regularized SDF estimator that minimizes pricing error (we
discuss HJD in further detail in Section 2.6).


2.5      Data and Training

To make the conclusions from this analysis as easy to digest as possible, we perform our
analysis in a conventional setting with conventional data. We use a comprehensive and
standardized sample of monthly US stock returns and 153 stock characteristics from 1963 to
2023, compiled by Jensen et al. (2023) (JKP henceforth).15 As in JKP, our universe includes
NYSE/AMEX/NASDAQ securities with CRSP share code 10, 11, or 12, excluding “nano”
stocks (i.e., stocks with market capitalization below the first percentile of NYSE stocks).
       Some of the JKP characteristics have low coverage, especially in the early parts of the
sample. To ensure that characteristic composition is fairly homogeneous over time and to
avoid purging a large number of stock-month observations due to missing data, we reduce
the 153 characteristics to a smaller set of D = 130 characteristics with the fewest missing
values. We drop stock-month observations for which more than 30% of the 130 characteristic
values are missing and use Nt to denote the number of the remaining stock observations at
time t. Next, we cross-sectionally rank-standardize each characteristic and map it to the
  14
       We discuss some attractive properties of the HJD in the following sections.
  15
       To access the stock-level characteristic data and associated documentation, refer to jkpfactors.com.


                                                       16
[−0.5, 0.5] interval, following Gu et al. (2020b). Ultimately, we obtain an Nt × D matrix of
conditioning characteristics Zt in each month.
       In our empirical analyses, we study SDF performance as we vary two aspects of the model:
the number of factors P and ridge penalty z. For each model of a given size and shrinkage,
we conduct a rolling out-of-sample model performance analysis. Starting in January 1993, in
each month t, we use the most recent 360 months of data to estimate the ridge SDF parameter
in (9).16 We then track the out-of-sample SDF portfolio return in the subsequent month.
From the sequence of monthly out-of-sample SDF realizations, we calculate out-of-sample
SDF performance metrics.


2.6      Performance Metrics

We evaluate our SDF models with two standard out-of-sample performance metrics. A true
SDF is the mean-variance efficient portfolio of risky assets. Thus, our first performance
metric is the SDF portfolio Sharpe ratio. For a candidate SDF M̃t = 1 − R̃tM , the annualized
out-of-sample Sharpe ratio is

               √        ÊOS [R̃tM ]
         SR
         c =       12
                        σ̂OS (R̃tM )

where ÊOS and σ̂OS denote sample average and standard deviation among the TOS out-of-
sample observations (to differentiate versus the notation Ê and T used for training samples).
Since the SDF is constructed from excess returns on risky assets, the numerator need not be
adjusted for the risk-free rate.
       Our second performance metric is the pricing error for a large set of test assets. The test
assets in our main analysis are the 153 JKP anomaly factors constructed by those authors
  16
    The stochastic nature of RFF means that there is inherent variability in the estimated SDF model when
P is small. To mitigate this variability, we repeat the RFF-based estimation 20 times with different random
seeds and report average performance metrics across seeds. This has little qualitative effect on the plots
shown. See KMZ for further discussion of this point.



                                                    17
and downloadable at jkpfactors.com (robustness analyses report pricing errors for other
test asset sets as well). To aggregate test asset pricing errors into a single metric, we calculate
the normalized sum of squared pricing errors according to the Hansen-Jagannathan distance
(HJD) referenced in Section 2.4. For a set of test asset returns RtT , the out-of-sample HJD
is

                            h       i′  h      i+     h       i
                 HJ               T       T T′              T
            D̂        = ÊOS M̃t Rt ÊOS Rt Rt    ÊOS M̃t Rt ,                                            (13)


                                                                                                              ′
where + is the Moore-Penrose quasi-inverse (necessary due to the degeneracy of ÊOS [RtT RtT ]
when P > TOS ).
          The HJD has a number of attractive model comparison properties.17 It averages pricing
errors among test assets using a common weighting matrix for all candidate models of
Mt . This is important because it puts all models on equal footing for comparison, unlike
other alpha or GMM-based comparisons. The weighting matrix is economically motivated
since it gives the HJD a clear interpretation as the pricing error of the portfolio of test
assets that is most mispriced by each model. Furthermore, the HJD is scale invariant.18
While typically used for in-sample comparison, the HJD easily generalizes for out-of-sample
evaluation because it avoids the need to estimate out-of-sample time series alphas and betas
for each test asset. Finally, because our theoretical derivations explicitly characterize the
expected out-of-sample HJD for complex SDF models, the empirical HJD can be directly
compared to theoretical predictions.
     17
      In addition to Hansen and Jagannathan (1997), the literature including Kan and Robotti (2009), Chen
and Ludvigson (2009), and Kelly and Xiu (2023) further advocates HJD as a pricing error metric.
   18
      Differences in volatilities among factors can skew test statistics like average absolute alpha or the GRS
statistic, and as a result, the volatility scaling choice for test assets can lead to different conclusions. HJD
is invariant to changes in test asset volatility.




                                                      18
2.7      Benchmark Models

We provide reference points for our analysis by comparing large factor model performance
to five benchmark factor pricing models in the literature:19

FF6: This is a six-factor model that includes the five factors of Fama and French (2015) plus
         their UMD momentum.

 SY: This is a four-factor model that includes the “mispricing” factors of Stambaugh and
         Yuan (2017).

HXZ: This is a five-factor model that includes the q-factor model specification of Hou et al.
         (2015) augmented to include the expected growth factor of Hou et al. (2021).

DHS: This is a three-factor model that includes the long-horizon and short-horizon behavioral
         factors of Daniel et al. (2020).

 BS: This is a composite model that selects factors from the literature based on the Bayesian
         methodology of Barillas and Shanken (2018). Its six factors include the market factor,
         the investment and profitability factors from Hou et al. (2015), the size and momentum
         factors from Fama and French (2015), and the value factor (HMLm ) from Asness et al.
         (2013).

       To compare models, we use the SDF corresponding to each of these factor pricing models,
which requires estimating the Markowitz portfolio of factors in each model. We do this in
rolling 360-month training windows and track benchmark performance out-of-sample. In
other words, we use the same training/evaluation design for the benchmarks that we use for
our large factor pricing models.20
  19
    All benchmark factor data are conveniently available from the respective authors’ websites.
  20
    When building the Markowitz portfolio for each benchmark model, we do not use ridge shrinkage because
the number of assets is far smaller than the number of time series observations. Even with infeasible (ex-
post optimal) ridge shrinkage, we find the out-of-sample SDF performance of benchmark models changes
negligibly.


                                                   19
3      Empirical Results

3.1     The Virtue of Complexity in Factor Pricing Models

Our central empirical finding is that factor model performance is increasing in the number of
factors. We illustrate this virtue of complexity by plotting out-of-sample model performance
as a function of the number of model parameters (which, in our setting, corresponds to
the number of factors). KMZ refer to such plots as “VoC curves.” Each curve applies
a different ridge penalty z = 10−5 , 10−3 , 10−1 , 1, or 10. Along each curve, we vary the
complexity—i.e., the number of factors—in our SDF model. We consider specifications with
P = 36, ..., 360,000 random Fourier factors, corresponding to c = 0.1, ..., 1,000. The VoC
curves in Figure 2 show four out-of-sample properties of each SDF specification: expected
return (Panel A), volatility (Panel B), Sharpe ratio (Panel C), and pricing error (Panel D).
      We find the following main patterns associated with model complexity. As we increase
the number of factors, i) the average SDF return rises, ii) SDF volatility rises, iii) the SDF
return increases faster than volatility, resulting in a rising SDF Sharpe ratio, iv) pricing
errors decline, and v) performance gains accrue more quickly with less ridge shrinkage. The
exceptions to these patterns occur when ridge shrinkage is small, and complexity is close to
one, in which case we see a spike in out-of-sample SDF volatility that induces an abrupt dip
in the Sharpe ratio and a spike in pricing error. This “double ascent” in Sharpe ratio and
“double descent” in pricing error is reminiscent of previously documented phenomena in the
machine learning literature (e.g. Hastie et al., 2019; Bartlett et al., 2020).
      Quantitatively, the differences in out-of-sample performance for high and low-complexity
models are dramatic despite the fact that both model types use identical data inputs and
differ only in the richness of their parameterizations. High-complexity models with light
shrinkage earn out-of-sample Sharpe ratios near 3.7, roughly 2.6 times larger than the Sharpe
ratios of low-complexity models with c < 1. Likewise, large factor models are much better


                                               20
            Panel A: Expected Return                         Panel B: Standard Deviation




              Panel C: Sharpe Ratio                              Panel D: Pricing Error




              Figure 2: Out-of-sample Performance of Complex Factor Models
Note. Realized out-of-sample SDF portfolio average return, standard deviation, Sharpe ratio, and pricing
error (HJD). The horizontal axis shows model complexity c = P/T , with P ranging from 36 to 360,000
and T = 360 months. Factors underlying the SDF are characteristic-managed portfolios constructed with
random Fourier features derived from JKP stock characteristics. The test assets in Panel D are 153 anomaly
factors from JKP.


positioned to price our demanding test assets (153 anomaly portfolios collected from decades
of finance research). Pricing errors for low-complexity models are more than twice as large
as those for high-complexity models (0.54 vs 0.22).




                                                   21
              Panel A: Sharpe Ratio                           Panel B: Cumulative Return




                                        Panel C: Pricing Error




      Figure 3: Performance Comparison of Complex and Benchmark Factor Models
Note. This figure reports the out-of-sample performance of SDF portfolios corresponding to various factor
pricing models, including the complex model (P = 360, 000 and z = 10−5 ) as well as the simple benchmark
models FF6, HXZ, SY, DHS, and BS. Panel A shows the out-of-sample Sharpe ratio for each model’s factor
Markowitz portfolio. Panel B shows the simple cumulative sum of out-of-sample returns for each model’s
factor Markowitz portfolio (we have standardized out-of-sample returns to 10% annualized volatility for all
models in order to facilitate comparison in this panel). Panel C shows pricing errors (HJD) for four sets
of test assets, including are the 360,000 random Fourier factors underlying the large factor model (denoted
“complex”), the 153 JKP factors, the 13 JKP aggregate theme factors, and the 25 Fama-French size and
book-to-market portfolios. Benchmark data sets are available for different sample periods, so we report
statistics on the intersection of their out-of-sample ranges, which is from August 2002 to December 2016.




                                                    22
3.2      Comparison With Benchmarks

In Figure 2, we compare large and small variants of factor models using random Fourier
factors. However, the conclusion that large factor models outperform simple models is not
specific to the nonparametric framework in Figure 2.
       Figure 3 compares the high complexity factor model (P = 360, 000 and z = 10−5 ) to
five of the leading factor models in the literature: FF6, HXZ, SY, DHS, and BS. Panel A
reports the out-of-sample Sharpe ratio for each model’s SDF portfolio, Panel B shows the
corresponding cumulative return plot, and Panel C reports out-of-sample pricing errors.21
       Panel A shows that the benchmark factor models are all roughly on par with each other in
terms of Sharpe ratio, while the complex model rather dramatically outperforms every simple
model. Its Sharpe ratio is around 3-6 times higher than the benchmarks. The cumulative
returns in Panel B show that the portfolio performance comparison is not driven by any
particular subsample and that the complex model does not exhibit any periods of unusually
turbulent behavior.
       Panel C shows that the large factor model also dominates in terms of pricing error.
When the 153 JKP factors are test assets, HJD for the benchmark models hovers around
0.9, roughly twice that of the large factor model. This finding is not specific to this set of
test assets. When the test assets are the 360,000 random Fourier factors themselves, the
HJD hovers around 0.95 for benchmark models, again roughly twice the HJD of the complex
factor model. Third, we study the JKP theme factors, which collect the individual anomaly
factors into 13 aggregate theme portfolios. The benchmark HJD for this test set is around
0.2, which is roughly four times larger than the complex model HJD. Finally, we use the
classic Fama-French 25 size and value portfolios. This test set has been the target for pricing
models for forty years, and one can argue that benchmark models have been honed to price
  21
    Figure 3 shows small differences in performance metrics for the high complexity factor model compared
to Figure 2. This is because Figure 3 is restricted to a shorter time sample in which data is available for all
benchmark models.



                                                      23
Table 1: Performance Comparison of Complex and Benchmark Factor Models
This table reports a comparison of out-of-sample SDF portfolio performance for various factor pricing models,
including the complex model (P = 360, 000 and z = 10−5 ) as well as the simple benchmark models FF6,
HXZ, SY, DHS, and BS. The first two rows show the annualized percentage alpha and associated t statistic of
the complex SDF portfolios versus each benchmark SDF portfolio. The next two rows show each benchmark
SDF portfolio’s alpha and t statistic versus the complex model. The last two rows show the ex-post tangency
portfolio weights combining the SDF portfolios of all models with and without a non-negativity constraint
(and constraining weights to sum to one). To facilitate alpha comparisons, out-of-sample SDF portfolio
returns for all models are rescaled to have 10% annualized volatility. Benchmark data sets are available for
different sample periods, so we report statistics on the intersection of their out-of-sample ranges, which is
from August 2002 to December 2016.
                                                                    LHS
                                    FF6        SY             HXZ      DHS          BS        Complex
    Complex Alpha                   42.8       40.7           39.4     43.5        44.4          –
      vs. Benchmark                (13.9)     (13.6)         (13.0)   (13.7)      (13.8)         –
    Benchmark Alpha                 -2.8        -4.3          -2.3     1.50        3.90           –
      vs. Complex                  (-0.7)      (-1.2)        (-0.6)   (0.40)      (1.00)          –
    Tangency Weights
      Unconstrained                -0.44       -0.24         -0.01     0.12        0.56          1.01
      Non-negative                  0.00       0.00          0.00      0.01        0.09          0.90



test assets like these. Even in this case, benchmark models deliver an out-of-sample pricing
error of around 0.2, roughly three times larger than those from the complex pricing model.
    Table 1 extends the benchmark comparison by reporting pairwise alphas between SDF
portfolios of the large factor pricing model and each of the benchmark models. For this,
we use the out-of-sample SDF portfolios but renormalize them ex post to a 10% annualized
volatility to make alphas comparable for all models (unlike HJD, alphas lack scale invariance,
so volatility scaling is helpful for comparison). The complex model produces a large and
highly significant alpha versus all benchmarks, ranging from 39.4% to 44.4% per annum.
The reverse is not true. Benchmark models all have small and statistically insignificant
alphas versus the complex model. Finally, we estimate the “meta”-Markowitz portfolio that
combines SDF portfolios of all individual models. The complex model dominates the meta



                                                        24
                       Figure 4: Complex Versions of Benchmark Models
Note. The figure reports out-of-sample Sharpe ratios of simple benchmark models compared to their
nonlinear, high-complexity counterparts. For each benchmark model we construct its high complexity SDF
with random Fourier factors derived from the characteristics underlying that model: size, value, investment,
profitability, and momentum for FF6; size and two mispricing measures (MGMT and PERF) for SY; size,
investment, profitability and expected growth for HXZ; size, PEAD, and two measures of issuance (CSI and
NSI) for DHS; and asset growth, profitability, size, value and momentum for BS. Complex versions of each
benchmark use P = 360, 000 factors (c = 1000) and shrinkage of z = 10−5 , 10−3 , 10−1 or 1.



portfolio, receiving a weight of 101% in the unconstrained portfolio and a weight of 90% in
the portfolio that constrains weights on individual models to be non-negative.


3.3    The Nonlinear Fama-French Model

In the preceding analysis, we compare high complexity factor models derived from 130 JKP
characteristics to the FF6 model and other benchmarks that are low complexity models
derived from a small set of characteristics. Naturally, one may wonder about the benefits of
complexity when we restrict the raw data inputs to match those used by a given benchmark


                                                    25
model. To investigate this, we construct complex SDFs using random features derived from
only the characteristics that underly each benchmark. For example, in the case of FF6, we
construct a complex factor model with a large number of nonlinear factors derived from the
size, value, investment, profitability, and momentum characteristics.
      Figure 4 reports the out-of-sample Sharpe ratio of high complexity variations of each
benchmark model using P = 360,000 (c = 1,000) random Fourier factors and ridge shrinkage
of z = 10−5 , 10−3 , 10−1 or 1. The original formulation of the FF6 model has an out-of-
sample Sharpe ratio of 0.74, while its high complexity version ranges from 1.93 to 2.50
depending on the degree of shrinkage. All benchmarks show the same pattern—if we hold
the stock characteristics of each simple model fixed but enrich the model specification to
incorporate highly parameterized nonlinear transformations of those characteristics, the out-
of-sample performance of the benchmarks improves by a factor of 1.4 to 3.6, depending on
the benchmark and the amount of shrinkage.
      The conclusion is that the benefits of large factor models accrue even when starting from
a small conditioning information set. Complexity may be applied to any set of conditioning
variables to more flexibly reflect patterns in the underlying return-generating process.


3.4     Macroeconomics of the Complex SDF

What is responsible for the high degree of mean-variance efficiency of the complex SDF
portfolio relative to benchmarks?      At a statistical level, the answer is straightforward:
The complex SDF model more successfully optimizes the maximum Sharpe ratio objective,
indicating that it estimates the “true” efficient portfolio with greater accuracy than the
benchmarks.
      At an economic level, this improved measurement can help us better ascertain the
economic nature of the “true” SDF. In equilibrium asset pricing models, an SDF reflects
investors’ intertemporal marginal rate of substitution (IMRS), which is shaped by investors’



                                               26
information and expectations about future macroeconomic conditions. As shown by Hansen
and Jagannathan (1991), the mean-variance efficient portfolio is a projection of the IMRS
onto the space of traded assets, resulting in a so-called “tradable” SDF like those studied
above. If, as econometricians, we achieve a more efficient tradable SDF, then we are more
successfully honing in on information and expectations about future economic conditions
that investors are collectively impounding into current prices and that govern investors’
IMRS. As articulated by Fama (1990) in his study of market returns and the macroeconomy,

        “the general hypothesis ... is that information about the production of a given
        period is spread across preceding periods and so affects the stock returns of
        preceding periods.”

We extend Fama (1990)’s hypothesis to the modern setting of SDF returns. If a complex SDF
achieves superior mean-variance efficiency relative to benchmarks, it should better reflect
investors’ IMRS, and it should in turn be a stronger predictor of future economic conditions.
Or, stated more simply, portfolio efficiency and informational efficiency go hand-in-hand.
      To pursue this hypothesis, we compare candidate SDFs in their ability to predict
macroeconomic activity. Let yt be a vector containing various measures of macro activity and
conditions in log levels at the monthly frequency. In our baseline specification, y includes
10 variables: industrial production, macroeconomic uncertainty, the Federal Funds rate,
employment, consumer sentiment from the Michigan survey, CPI, housing starts, the Baa-
Aaa yield spread, oil prices, and the trade-weighted dollar exchange rate index.22
      The goal of our prediction analysis is to understand the extent to which information
realized in SDF portfolio returns reflects expectations of future macroeconomic conditions.
To accomplish this, we estimate impulse response functions using the method of local
 22
    Nine of these variables are from the FRED-MD database and correspond to FRED identifiers IND-
PRO, FEDFUNDS, PAYEMS, UMCSENTx, CPIAUCSL, HOUST, AAA and BAA, OILPRICEx, TWEX-
AFEGSMTHx. The only variable not from FRED-MD is the macroeconomic uncertainty index (h = 1
variant) from Jurado et al. (2015).



                                               27
                    Figure 5: Macroeconomic Impulse Response Functions
Note. This figure reports SDF impulse responses estimated from equation (14). Dependent variables are
shown in each figure title, and the impulse is a positive one standard deviation return to each SDF (the
complex SDF in blue and the FF6 SDF in red). Shaded regions are pointwise 90% confidence intervals based
on Newey-West standard errors with five lags.


projections (Jordà, 2005) using the “long difference” form (Jordà and Taylor, 2025):

                                   11
                                                !            2
                                   X                         X
                                          M
      yt+h − yt = ah + bSDF,h            Rt−j       /σ M +         bj,h yt−j + et+h ,   h = 1, ..., 36.   (14)
                                   j=0                       j=0


The regression coefficient bSDF,h directly estimates, for each element of y, the expected
h-period-ahead cumulative response (in percentage changes) to a positive one standard
deviation realization of the annual SDF return, while controlling for predictive information




                                                      28
in y’s own lags.23 We use a 12-month SDF return to accumulate information over a longer
interval and reduce noise in the regressor.24 We estimate regression (14) over the full out-of-
sample period 1993-2023 using realized returns for the complex SDF and each benchmark.
    Figure 5 reports the estimated impulse responses for the complex SDF. To provide a
frame of reference Figure 5 also reports results for the FF6 SDF, which is representative
of results for the other benchmarks. (Results for the full set of benchmarks are shown in
Appendix L.)
    The key conclusion from this analysis is that the complex SDF has strong predictive
power for macroeconomic conditions, particularly at long horizons of two years or more. A
positive one-standard-deviation annual return to the complex SDF predicts a roughly 3%
(and highly significant) increase in industrial production over three years. It predicts a
reduction in macroeconomic uncertainty of about 7.5% over two years. It predicts large and
highly significant increases in employment (1.25%), consumer sentiment (9%), housing (9%),
and the dollar (2.5%) over three years. A positive complex SDF return predicts a reduction
in credit spreads of 0.08% over two years, which is a roughly 8% decrease in the credit
spread relative to its long-term average level of 0.95%. Finally, we see a positive interest
rate response of roughly 0.4% over 1.5 years (versus an average interest rate level of 2.5% in
our sample) and a negative response in CPI of 1% over three years.
    In Appendix Figures IA.2 and IA.3, we repeat this analysis replacing the last variable in
y (Dollar index) with consumption. In this specification, we see that a positive one standard
deviation in the complex SDF return predicts a significant 0.7% increase in consumption
over three years. The remaining impulse responses are quantitatively unaffected, with the
  23
     Among these ten variables, there are two that we use in levels without taking logs, these are the Federal
Funds rate and the Baa-Aaa credit spread, which are already reported in annualized percentages. In this
case, the bSDF,h coefficient describes the expected simple (not log) change in the corresponding
                                                                                          P       variable.
                                                                                                       
  24                                                                                          11    M        M
     For this analysis, the annual SDF return is defined in standard deviation units,         j=0 t−j /σ ,
                                                                                                  R
where σ M is the sample standard deviation of on the rolling annual return.




                                                     29
               Figure 6: SDF Returns and Future Macroeconomic Outcomes
Note. This figure reports the R2 from a regression of SDF returns on future macroeconomic outcomes per
equation (15).



exception that the response of the credit spread drops more quickly, bottoming out after
nine months rather than two years.
   The results in Figure 5 illustrate the strength with which the complex SDF predicts a
variety of macroeconomic conditions. But how much of the SDF’s behavior can be attributed
to the market’s assimilation of information about future economic fundamentals collectively?
We devise an answer to this question by running a somewhat unconventional regression of
returns in month t on future realizations for all of the macroeconomic variables in y:


      RtM = ah + b′h (yt+h − yt ) + et ,   h = 1, ..., 36.                                       (15)


The R2 of this regression describes the fraction of SDF return variation that is attributable
to information about future macroeconomic conditions over horizons h = 1 to 36 months
ahead. Figure 6 plots the resulting R2 for the complex SDF and the FF6 benchmark SDF.

                                                   30
       The complex SDF is predominantly driven by information about the macroeconomy
over long horizons. Cumulative macroeconomic realizations over the subsequent three years
explain 25% of the variation in complex SDF returns. This drops to around 5% if we restrict
to economic realizations over the next year. In contrast, only about 5% of the benchmark
SDF return is explained by future macroeconomic factors, regardless of the horizon we look
at.25
       In summary, positive SDF returns predict rising production, employment, sentiment,
and housing; they predict decreasing risk, credit spreads, and inflation.                Our impulse
responses control for lags of y, implying that this predictive information in the complex
SDF is not spanned by standard macro variables. Meanwhile, the benchmark SDF shows
either little significant predictive power for macro variables, or the sign of the prediction is
counterintuitive (as in the case of employment).
       The long-horizon impulse responses in Figure 5 are directionally consistent with equilib-
rium models incorporating recursive preferences and long-run risk, such as Bansal and Yaron
(2004) and Campbell et al. (2018). In these models, the SDF reflects investors’ expectations
about future output uncertainty over the long run. Empirically, long-run risks are notoriously
difficult to estimate and researchers continue to debate the reliability of proposed proxies (see
e.g. Liu and Matthies, 2022, 2024; Maio, 2024). Our complex SDF provides new empirical
evidence of the long-run risk mechanism in equity market prices.
       Our empirical findings about the joint cyclical variation in uncertainty, production,
interest rates, and credit spreads are consistent with the equilibrium models of Gilchrist
and Zakrajšek (2011); Gilchrist et al. (2014); Christiano et al. (2014). Their focus relates
to the empirical fact that credit spreads and risk predict economic conditions (Gilchrist
and Zakrajšek, 2012; Gilchrist et al., 2009). Importantly, since we control for lags of y,
  25
    Appendix L shows the same R2 plot for all benchmark models. The patterns for all benchmarks are
broadly similar to FF6. DHS is an exception in that it captures more information about future short-term
macroeconomic phenomena than the other SDFs.




                                                  31
our analysis indicates that the complex SDF incorporates differential information about the
macroeconomy above and beyond the information in prevailing credit spreads and risk.
       Finally, our conclusions from the macroeconomic analysis above are robust to a variety of
alternative design choices in the analysis of (14), including changing the constituent variable
in y, changing the frequency of SDF return, and changing the number of y lags. These
results are reported in Appendix L.


3.5      SDF Complexity or SDF Sparsity?

A recent line of financial machine learning research suggests that it is possible to estimate a
successful factor pricing model through the imposition of sparsity.26 The evidence indicates
that an SDF model with a small number of factors can successfully price a wide variety of
test assets. This is exemplified by Kozak et al. (2018), who study a collection of difficult-to-
price anomaly portfolios that serve as their test assets. They then show that a simple linear
SDF—comprised of just a few principal components of the anomaly portfolios—is powerful
for pricing their entire anomaly cross-section.
       The notion of SDF sparsity appears at odds with the benefits of complexity that
we document above. While our results thus far demonstrate that a complex model can
identify efficacious nonlinear pricing factors, is it possible that we also introduce unnecessary
redundancy by using many thousands of factors? We investigate this possibility now.
       In Figure 2, each point on each curve is a model with a particular number of factors, P ,
and a particular shrinkage parameter, z. To investigate the potential benefits of sparsity,
we replace the P -factors in each model of Figure 2 with a small number K of principal
components derived from those P factors. We then re-estimate the SDF coefficients on the
K components and track the resulting out-of-sample factor model performance.
       Figure 7 reports the results. In the left column, we consider a K = 5 component
  26
    This includes Gagliardini et al. (2016), Kelly et al. (2020), Kozak et al. (2020), Lettau and Pelger (2020),
and Giglio and Xiu (2021), among others.



                                                      32
                      K=5                                                K = 25




           Figure 7: The Effect of Sparsity on Out-of-sample SDF Performance
Note. Realized out-of-sample SDF Sharpe ratio (top row) and pricing error (HJD, bottom row) for complex
models with dimension reduction to K = 5 (left column) and K = 25 (right column) principal components.
The horizontal axis shows model complexity c = P/T with P ranging from 36 to 360,000 and T = 360
months. For ease of reference, “Complex Model” shows performance of the highest complexity model (P =
360,000, z = 10−5 ) from Figure 2 without dimension reduction.



dimension reduction of each complex factor model (corresponding to the K used in some
model specifications of Kozak et al., 2018; Kelly et al., 2020). The Sharpe ratio (top panel)
of the dimension-reduced SDF is roughly 1.3, compared to 3.7 for the full complexity model.
Likewise, pricing errors (bottom panel) are 0.57 for the K = 5 SDF versus 0.22 for the full
complexity model. In other words, imposing sparsity on the SDF via dimension reduction
inhibits SDF performance relative to the unreduced, high-complexity counterpart.
   Kozak et al. (2018) consider larger numbers of principal components as well. The right

                                                  33
               Figure 8: The Effect of Sparsity on Out-of-sample SDF Performance
Note. Realized out-of-sample SDF Sharpe ratio (top row) and pricing error (HJD, bottom row) for complex
models with dimension reduction to K = 5, ..., 360 principal components (x-axis).



column of Figure 7 shows that increasing model complexity by using K = 25 rather than
K = 5 principal components leads to a large improvement in out-of-sample performance.
But even in this case, the Sharpe ratio remains well below that of the full complexity model
(3.7 vs 2.9), and the pricing error remains 41% higher (0.31 vs 0.22).
       Two properties of high-dimensional models drive this effect. First, even if the true
(unobservable) factor covariance matrix has a few large eigenvalues and, hence, a strong
factor structure, the factors become difficult to detect when complexity is high.27 Second
and more surprisingly, even low-variance components have a significant Sharpe ratio, so
excluding them leads to a large drop in out-of-sample SDF performance. This fact is
illustrated in Figure 8. In this analysis, we hold the number of factors in the underlying model
fixed at P = 360, 000, but vary the number of components extracted from the model from
K = 5, 10, ..., 360. Adding low variance components typically helps, and never hurts, out-
of-sample factor model performance. Based on this analysis, the AIPT’s large factor model
conjecture appears better suited for describing market behavior than does the parsimony
conjecture of the APT.
  27
       See, e.g., Lettau and Pelger (2020).




                                                  34
                 Panel A: Mega                                  Panel B: Large




                 Panel C: Small                                 Panel D: Micro




      Figure 9: Out-of-sample Sharpe Ratios of Complex SDF Models By Size Group
Note. Realized out-of-sample SDF Sharpe ratio for SDFs estimated from subsamples based on market
capitalization.



3.6   Sensitivity to Liquidity

A Sharpe ratio of 3.7 for the high-complexity SDF model suggests that the model is exploiting
inefficiencies associated with illiquidity. To understand the role of complexity in factor pricing
models while abstracting from the question of asset liquidity, we conduct our empirical
analysis separately for different market capitalization groups. We study four size groups




                                               35
                 Panel A: Mega                                Panel B: Large




                 Panel C: Small                               Panel D: Micro




    Figure 10: Out-of-sample Pricing Errors of Complex SDF Models By Size Group
Note. Realized out-of-sample SDF pricing error (HJD) for SDFs estimated from subsamples based on
market capitalization.


from JKP: mega (largest 20% of stocks based on NYSE breakpoints each period), large
(between 80% and 50%), small (between 50% and 20%), and micro (between 20% and 1%).
   Figure 9 plots out-of-sample Sharpe ratios for SDFs estimated separately within each
size group, while Figure 10 plots pricing errors. The central conclusion from these figures is
that the virtue of complexity arises in all stock size groups. In terms of magnitude, Figure 9
indeed suggests that the SDF Sharpe ratios in Figure 2 are heavily influenced by microcap
stocks. Yet the SDF Sharpe ratios based on mega or large stocks are on the order of 1.6 and

                                              36
             T = 12                            T = 60                            T = 120




      Figure 11: The Effect of Training Sample Size on Out-of-sample SDF Performance
Note. Realized out-of-sample SDF Sharpe ratio (top row) and pricing error (bottom row) training windows
of T = 12, 60, and 120 months.


1.8, respectively. In other words, a complex factor model derived from mega stocks alone
(roughly the 400 largest stocks in the US) produces an out-of-sample SDF Sharpe ratio well
in excess of the FF6 model’s Sharpe ratio of 0.74 (which uses the full cross-section of stocks).
In summary, the patterns documented in our main analysis (Figure 2) do not appear to be
driven by illiquidity and limits-to-arbitrage among the underlying assets. Instead, these
findings suggest that models with a large number of factors are generally better suited to
price assets in the cross-section, regardless of their liquidity.


3.7     Sensitivity to Sample Size

Our main analysis demonstrates the virtue of complexity when estimation is conducted in a
rolling 360-month training sample. However, the benefits of complexity can accrue in smaller




                                                  37
training samples. In Figure 11, we plot VoC curves for training samples of T = 12, 60 and
120 months.
      We find identical patterns in complex factor model behavior in training windows as short
as a single year. Complex model performance weakens in shorter training windows as the
training process has less information to learn from. The out-of-sample Sharpe ratio for our
highest complexity factor model is 1.9, 2.9, 3.3, and 3.7 for T = 12, 60, 120, and 360 months,
respectively. Likewise, pricing errors reduce from roughly 0.45 for T = 12 months to 0.22 for
T = 360. In appendix Figure IA.9 we compare against simple benchmark SDFs that are also
estimated in T = 12 month training windows. In this case, the complex model has a smaller
margin of improvement over the benchmarks, since their small numbers of parameters make
the simple benchmark SDFs resilient to estimation in fairly short samples. The complex
Sharpe ratio is 1.9 versus 1.1 for the best simple benchmark (compared to the T = 360 case
where the complex Sharpe ratio is 3.7 versus 1.2 for the best simple benchmark).
      Finally, we show in appendix Figure IA.10 that the decay in empirical model performance
from reducing the sample from T = 360 to T = 12 matches the theoretically expected decay
from using small samples. In particular, we simulate data from the our theoretical model
calibration in Section 4.7.1. When we reduce the simulated sample size from T = 360 to T =
12, the decline in simulated out-of-sample Sharpe ratio is quantitatively consistent with our
empirical results. Theorem 3 below demonstrates that this decline is explicitly determined
by the joint distribution of factor risk premia and the eigenvalues of their covariance matrix.
See also Kelly and Malamud (2025) for an analogous result in the (simpler) single-asset case.


3.8     Sensitivity to Activation Functions

Our main empirical model uses random features built from sine and cosine activation
functions following Rahimi and Recht (2007).         There are, however, a wide variety of




                                               38
                                             Sharpe Ratio
                         tanh                                              ReLU




                                             Pricing Error
                         tanh                                              ReLU




       Figure 12: Complex SDF Performance With Alternative Activation Function
Note. This figure repeats the analysis of Figure 2 using either hyperbolic tangent activation (left column)
or rectified linear unit activation (right column). Performance is measured as out-of-sample Sharpe ratio
(top row) and pricing error (bottom row).



alternative activation functions used in the machine learning literature. In this section we
examine the sensitivity of our results to this choice.
    Other than the activation function, we hold all design choices from our main analysis in
Figure 2 fixed. Specifically, we set T = 360, we draw random weights {ωp }Pp=1 ∼ i.i.d. N (0, I),


                                                    39
and we use the same grid of bandwidth parameters γ. We replace the sine/cosine activations
in Equation (6) with two of the most common activation functions in the literature,
hyperbolic tangent (“tanh”) and rectified linear unit (“ReLU”). Random features with
these activations are


       (tanh)       eγZt ωp − e−γZt ωp          (ReLU)
     Sp,t       =                        and   Sp,t        = max[0, γZt ωp ].
                    eγZt ωp + e−γZt ωp

   Figure 12 shows tanh and ReLU model performance in terms of out-of-sample Sharpe
ratio (top panels) and pricing errors (bottom panels), and are directly comparable to the
results for the sine/cosine model in Figure 2. We see that the high complexity tanh and
ReLU models achieve Sharpe ratios of roughly 3.0 to 3.5 and pricing errors of 0.25 to 0.30,
slightly below but broadly in line with the performance of the main sine/cosine specification,
and far in excess of benchmark model performance.
   Why does the choice of activation function influence out-of-sample performance? Our
analytical characterization in Theorem 3 indicates that the construction of random features
affects Sharpe Ratios by shaping the alignment between factor risk premia and the eigenvalue
distribution of their covariance matrix. This alignment, in turn, is governed by the capacity
of non-linear factors to escape linearity and capture genuine non-linear relationships when
the sample size T is small. These trade-offs between limited sample size and non-linear
representation have been widely studied in prediction contexts and are known to depend on
the smoothness of the activation function; see Karoui (2010), Cheng and Singer (2013), and
Do and Vu (2013). Extending this understanding to the SDF setting remains an important
avenue for future research.




                                                      40
4     AIPT: Theoretical Underpinnings of Complex Factor Models

This section presents artificial intelligence pricing theory. We first present assumptions that
formalize the AIPT’s core conjecture—that asset prices are determined by a high-dimensional
factor structure. From these assumptions, we derive a statistical theory of large factor pricing
models. Lastly, we show that the empirical behavior of factor pricing models in Section 3
bears a strikingly close correspondence to theoretically predicted behaviors of the AIPT.


4.1   Assets and Conditioning Information

Our theory begins with the following two assumptions:

Assumption 1 There exist loadings St ∈ RN ×P , latent factors Fet+1 , and idiosyncratic
shocks εt+1 such that returns Rt+1 ∈ RN satisfy


      Rt+1 = St F̃t+1 + εt+1 ,                                                                     (16)


                  1/2
where εt+1 = Σε,t ε̃t+1 with E[εi,t ] being i.i.d. with E[εi,t ] = 0, E[ε2i,t ] = 1, E[ε4i,t ] < ∞.
The latent factors satisfy Et [F̃t+1 ] = ν, and the conditional covariance matrix ΣF,t               =
             ′                                                                             1/2
Et [F̃t+1 F̃t+1 ] − νν ′ satisfies tr(ΣF,t ) = O(1). We also assume that ν = P −1/2 Σν ν̂, where
ν̂ = (ν̂i )Pi=1 ∈ RP is such that ν̂i are independent across i and E[ν̂i ] = 0, E[ν̂i2 ] = 1, E[ν̂i4 ] ≤
K for some K > 0, and are independent of all other variables; ∥Σν ∥ = O(1) as P → ∞.

Assumption 2 We have St = Σ1/2 Xt Ψ1/2 for some positive definite matrices Σ, Ψ; here,
                                                       2
the random variables Xi,k,t satisfy E[Xi,k,t ] = 0, E[Xi,k,t ] = 1, and Xi,k,t are independent
       8
and E[Xi,k,t ] < ∞. In the limit as N, P → ∞, both Σ and Ψ stay uniformly bounded,
tr(Σ) is uniformly bounded, and limN →∞ tr(Σ2 )/(tr(Σ))2 = 0. Without loss of generality,
everywhere in the sequel we assume Σ is normalized so that tr(Σ) = 1.




                                                  41
       Factor pricing models summarize the risk-return tradeoff among N risky assets in the
economy. To this end, Assumption 1 describes the dependence structure of assets and
expected returns. It is a standard conditional factor structure that allows for an arbitrary
number of factors P .28            Assumption 1 defines the relevant conditioning information in
this economy, which amounts to the conditional factor loadings in the N × P matrix
St .    We refer to St as “characteristics” or “signals” in connection with the empirical
asset pricing literature.29          The P -vector of factor risk prices, denoted ν, together with
the conditional loadings determine asset expected returns.30 Internet Appendix B further
discusses Assumption 1 as a generic statistical specification arising in the context of machine
learning factor pricing models.
       Next, our theoretical derivations require assumptions about the covariance structure of
the signals St . By Assumption 2,


         E[St′ St ] = tr(Σ)Ψ ∈ RP ×P         and E[St St′ ] = tr(Ψ)Σ ∈ RN ×N ,                         (17)


thus the matrix Ψ captures the covariance of signals across factors and Σ captures their
covariance across assets. The assumption of bounded tr(Σ) is a no-arbitrage condition to
ensure that the predictable variation in returns stays bounded. The last two limits in
Assumption 2 ensure that characteristic-managed portfolios offer a meaningful amount of
diversification across stocks.31
  28
     The assumption tr(ΣF,t ) = O(1) as P → ∞ is the mathematical formalization of the idea of a factor
structure. For example, if ΣF has a finite rank K with bounded eigenvalues, then this condition is trivially
satisfied. The assumption of constant conditional factor premia is without loss of generality since dynamic
premia can be subsumed by St .
  29
     One can think of the loadings as some function of other underlying conditioning characteristics, or the
characteristics could be loadings themselves as in the BARRA model popular among industry professionals.
                              1/2
  30
     The scaling ν = P −1/2 Σν ν̂ with P −1/2 is optimal and ensures that the vector of risk premia neither
vanish nor explode for large P : E[∥ν∥2 ] = P −1 tr(Σν ) = O(1).
  31
     For example, suppose that rank(Σ) = 1, so that Σ1/2 = ππ ′ for some π ∈ RN . Then, St = ππ ′ Xt Ψ1/2
and therefore all factors are given by

         Ft+1 = Ψ1/2 Xt′ π(π ′ Rt+1 ) ,                                                                (18)



                                                    42
4.2     Characteristic-managed Portfolios

From the equivalence of the conditional SDF and the mean-variance efficient portfolio


                                              ′
        M̃t+1 = 1 − πt′ Rt+1 , πt = Et [Rt+1 Rt+1 ]−1 Et [Rt+1 ] ,                                            (19)


Assumption 1 implies the following SDF representation.

Proposition 1 Let ΣF,ε,t = Et [Fet+1 ε′t+1 ]. A conditional stochastic discount factor is


        M̃t+1 = 1 − w̃(St )′ Rt+1 ,                                                                           (20)


where


        w̃(St ) = Σ−1
                   t µt                                                                                       (21)


is the conditional mean-variance efficient portfolio with


        Σt = St (ΣF,t + νν ′ )St′ + St ΣF,ε,t + Σ′F,ε,t St′ + Σε,t
                                                                                                              (22)
        µt = St ν

and


        Et [Ri,t+1 M̃t+1 ] = 0, i = 1, · · · , N .                                                            (23)


The SDF in (20) is stated as a conditional portfolio of the basic risky assets, R, as discussed
in the empirical framework of Section 2. Estimating the conditional mean-variance portfolio
implying that all factor returns are proportional to returns on a single portfolio, π ′ Rt+1 , with no idiosyncratic
return. Assumption 2 ensures that such pathological situations cannot occur.




                                                        43
of basic assets is challenging. Not only does it require estimates of means and covariances
for a large number of assets, but it also requires these moments in conditional terms.
       To avoid the difficult task of modeling the conditional distribution of basic assets, it is
common in the empirical literature to instead study characteristic-managed portfolios, or
“factors,”32


         Ft+1 = St′ Rt+1 .                                                                               (24)


The conjecture is that by studying the unconditional properties of factors, we can learn about
the conditional properties of asset markets. For example, Kozak et al. (2020) approximate
the conditional SDF using the unconditional mean-variance efficient portfolio of managed
portfolios.33 Yet it is easy to see that the mean-variance portfolio of Ft ,


                      ′
         λ = E[Ft+1 Ft+1 ]−1 E[Ft+1 ]                                                                    (25)


is generally different from the conditionally efficient portfolio of basic assets that determines
the true SDF in (20).
       We prove in Proposition 2 that when the number of factors is large, the conjecture
indeed holds, and the unconditional optimal portfolio of factors coincides with the true
conditional SDF. While somewhat technical, the logic for this result is straightforward.
Factors interact base asset returns with conditioning characteristics, and, in the large P
limit, these interactions encode all available conditioning information. Therefore, we can rely
on unconditional properties of factors to capture the conditional properties of the underlying
assets.34

  32
     The literature often refers to the managed portfolios Ft as “factors,” and we adhere to this slight abuse
of nomenclature when the difference between Ft and the true factors F̃t is clear.
  33
     Relatedly, Kozak and Nagel (2023), Filipovic and Schneider (2024), and Chernov et al. (2025) discuss
conditions under which managed portfolios “span” the conditional SDF.
  34
     See Internet Appendix E for technical details.


                                                     44
Proposition 2 (Characteristic-Managed Portfolios Span the SDF) Let


         Mt+1 = 1 − λ′ Ft+1 = 1 − w(St )′ Rt+1 , with w(St ) = St λ ,                                     (26)


be the factor approximation for the SDF with λ given by (25). Suppose that Σε,t = Σ̃ε,t + σε2 I,
where limN →∞ tr(ΣΣ̃ε,t ) = 0 and σε2 ∈ R+ . Then, the difference Mt+1 − M̃t+1 converges to
zero in L1 and the Sharpe ratio of w(St )′ Rt+1 converges to that of w̃(St )′ Rt+1 as N, P → ∞.

       Proposition 2 implies that, when N, P are large enough,35


         λ′ Ft+1 = λ′ St′ Rt+1 ≈ ν ′ St′ Σ−1
                                          t Rt+1 .                                                        (27)


Thus, the surprising and very convenient implication of Proposition 2 is that model
complexity, in fact, simplifies asset pricing. Much like continuous time limits simplify a
variety of asset pricing calculations, large factor limits reduce conditional SDF modeling to
an unconditional problem. Therefore, in the remaining theoretical development, we leave
behind the base assets Rt and work directly with managed portfolios, Ft .36


4.3      Large Models as Approximations

As the George Box adage goes, “All models are wrong, but some are useful.” In reality,
the true data-generating process is unknown to the researcher. A core premise of modern
  35
     As noted by Chernov et al. (2025), the omission of Σ−1t   in the construction of Ft+1 introduces unhedged
components, resulting in an efficiency wedge between the factor portfolio and the conditionally efficient
portfolio. However, Proposition 2 shows that this wedge becomes asymptotically negligible.
  36
     Relatedly, Assumptions 1 and 2 govern the properties of Rt , which serves two purposes. First, the
assumptions ensure that characteristic-managed portfolios span the SDF in the high-complexity limit, per
Proposition 2. Second, they imply that characteristic-managed portfolios satisfy the technical conditions of
random matrix theory (see Theorem 4 in the Internet Appendix). Once these conditions are established, the
origin of factors is no longer relevant, and the theory can treat them in the abstract when proving our main
result in Theorem 3. Formally, the idea that conditionally efficient portfolio of stocks can be represented as
an unconditional portfolio of a rich enough set of nonlinear managed portfolios is discussed in (Hansen and
Richard, 1987). In general, portfolio weights for each asset depend on the entire set of conditioning variables
(e.g., characteristics of all assets). By contrast, Proposition 2 implies that we can restrict our attention to
portfolio weights that depend only on own asset characteristics.


                                                      45
artificial intelligence (and nonparametric statistics more broadly) is that large models are
useful because they provide flexible approximations of the unknown truth. However, while
added complexity brings better approximations, it also brings the usual statistical challenges
of heavy parameterization in the face of limited data.
      In this section, we design a framework to understand the out-of-sample behavior of factor
pricing models as we gradually expand their parameterization. To embed this investigation
in our theoretical environment, we consider a true SDF with a large number of factors,
P ∗ . We then consider an empirical model that approximates the SDF with only a fraction
q = PP∗ ≤ 1 of those factors.

Assumption 3 A misspecified empirical model of size P < P ∗ (q = PP∗ ) uses a subset of
factors, Ft+1 (q) = (Fi,t+1 )Pi=1 with covariance matrix E[Ft (q)Ft (q)′ ] ∈ RP ×P .

We are interested in characterizing out-of-sample factor model behavior as we expand the
subset of factors from P = 1, ..., P ∗ , gradually reducing the degree of misspecification in the
approximating model (when P1 = P the model is correctly specified) while increasing the
number of parameters that must be estimated.
      Our theoretical derivations are based on large P limits. The number of factors in the true,
unattainable factor model is P ∗ → ∞. We conceptualize the AIPT as a rich but nevertheless
imperfect empirical model with P → ∞ and q ≤ 1. We now develop the limiting behavior
of large empirical factor models using random matrix theory.


4.4     Feasible and Infeasible SDF Estimators

Proposition 2 directly motivates our empirical approximation to the SDF in equation (4) and
the ridge estimator in equations (9) and (12). Following Assumption 3, the ridge estimator
has access to a fraction q of the factors in the true model. Given a training sample of size
T , the empirical model has complexity c = P/T . We define the ridge SDF estimator for an



                                                 46
empirical model of complexity c and specification q as


      λ̂(z; q; c) = (zI + Ê[Ft (q)Ft (q)′ ])−1 Ê[Ft (q)]                                    (28)


with corresponding portfolio return and SDF of


      R̂TM+1 (z; q; c) = λ̂(z; q; c)′ FT +1 (q),   M̂T +1 (z; q; c) = 1 − R̂TM+1 (z; q; c),


where Ê denotes sample average over the T training observations.
   It will be useful to contrast λ̂(z; q; c) with the infeasible ridge SDF estimator


      λ(z; q) = (zI + E[F (q)F (q)′ ])−1 E[F (q)]                                             (29)


and its return and SDF


      RTM+1 (z; q) = λ(z; q)′ FT +1 (q),      MT +1 (z; q) = 1 − RTM+1 (z; q).                (30)


This estimator is infeasible because it relies on the population mean and covariance of factors
rather than their sample counterparts. The special case λ = λ(0, 1) corresponds to the true
SDF in (26). Naturally, as z increases from zero or as q decreases from one, the Sharpe ratio
of RTM+1 (z) declines. The portfolio λ(z; q) is an intermediate object between the true SDF
λ(0, 1) and the feasible estimator λ̂(z; q; c).
   A remarkable aspect of the theoretical results below is that we can fully characterize the
properties of λ̂(z; q; c) in terms of the infeasible estimator λ(z; q). Our analysis focuses on
the key properties that summarize the theoretical behavior of a factor-based SDF: its mean
and variance (which in turn dictate its Sharpe ratio and pricing errors). Because they are
central to our derivation below, we give special notation to these properties for the infeasible




                                                     47
ridge SDF:


        E(z; q) ≡ E[RTM+1 (z; q)],      V(z; q) ≡ Var[RTM+1 (z; q)].                           (31)


4.5     The Ridge SDF and Random Matrix Theory

It is perhaps easiest to understand our large P theory for factor model behavior through the
calibrations in Section 4.7, and readers interested in a non-technical discussion of the theory
may proceed there directly. For interested readers, this section provides a brief overview of
the random matrix theory concepts behind our analysis, and Section 4.6 gives a detailed
presentation of our main result.
      The central challenge to understanding λ̂(z; q; c) is the P ×P matrix Ê[Ft (q)Ft (q)′ ] whose
dimension grows with the number of factors. The limiting properties of this object require
the apparatus of random matrix theory (RMT).
      One technical insight in our analysis is that incorporating ridge regularization in the
SDF estimation problem allows us to extend core RMT results, such as the Marčenko and
Pastur (1967) theorem, to asset pricing analysis. We derive the necessary extensions of
Marčenko and Pastur (1967) to describe expected out-of-sample SDF behavior in terms of
three objects: the eigenvalue distribution of the factor population covariance matrix, E[F F ′ ],
the number of parameters per training observation (i.e., complexity, c), and the extent of
model misspecification (governed by q). Recall that our factors are defined as Ft+1 = St′ Rt+1 ,
with signals and returns satisfy Assumption 1 and 2. As we show in the Internet Appendix,
the only properties of the data-generating process that matter for portfolio performance in
the high complexity limit are Ψ and ν. Let Ψ(q) = Ψ[1 : P, 1 : P ] be the Ψ sub-matrix
corresponding to the first P signals.
      We need the following regularity condition on the covariance matrix of factors.

Assumption 4 In the limit as P → ∞, the eigenvalue distribution of Ψ(q) converges to a


                                                 48
limit distribution supported on a bounded interval. Furthermore, limP →∞ P −1 tr(Σν [1 : P, 1 :
P ]Ψ(q)k ) exists for each k ∈ N. Furthermore, in addition to Assumptions 1 and 2, we have
                                                                                      1/2
E[ε̃3i,t ] = E[Xi,j,t
                3
                      ] = 0 for all i, j, and the latent factors satisfy F̃t = ν + ΣF,t X̃t , where
X̃t = (X̃i,t )Pi=1 with X̃i,t being i.i.d. with E[X̃i,t ] = 0, E[X̃i,t
                                                                   2
                                                                       ] = 1.

    The first part of Assumption 4 ensures that the joint structure of signal covariance and
risk premia are well-behaved in the P → ∞ limit. The second part of the assumption ensures
that the covariance of latent factors fully captures their dependency structure (e.g., this is
always the case when Ft are normally distributed).
    The central object that dictates the behavior of large factor models is the eigenvalue
distribution of the factor covariance matrix, which our derivations represent as a Stieltjes
transform. This transform for the eigenvalue distribution of E[Ft (q)Ft (q)′ ] in the large P
limit is denoted

                           1
                             tr (E[Ft (q)Ft (q)′ ] + zI)−1 ,
                                                          
      m(−z; q) = lim                                                                           (32)
                      P →∞ P



and, similarly, the infeasible moments (31) converge to well-defined limits


      E(z; q) , V(z; q) .


We denote the limiting eigenvalue distribution of Ê[Ft (q)Ft (q)′ ] as

                                                         −1 
                               1                        ′
      m(−z; q; c) =        lim   tr zI + Ê[Ft (q)Ft (q) ]                                     (33)
                          P →∞ P
                         P/T →c
                         P/P ∗ →q


The main challenge of the AIPT is that when the factor model is heavily parameterized
(c > 0), Ê[Ft (q)Ft (q)′ ] converges not to E[F (q)F (q)′ ] but to a distortion of it. In Theorem 4
in Internet Appendix D, we apply an extension of the Marčenko and Pastur (1967) theorem
due to Bai and Zhou (2008) to our asset pricing environment in order to establish the explicit

                                                    49
mapping between Ê[Ft (q)Ft (q)′ ] and E[Ft Ft′ ]. Namely,

                                                                                      
                              1                                    z
         m(z; q; c) =                        m                                    ;q       .            (34)
                      1 − c − c z m(z; q; c)               1 − c − c z m(z; q; c)

The nonlinear master equation in (34) has a unique positive solution m(z; c; q) for any z < 0.
This solution is a function of only m(z; q) and c. Thus, equation (34) links m(−z; q; c) in
(33) to m(−z; q) in (32). When complexity is low and misspecification is small, i.e., when
c ≈ 0 and q ≈ 1, (34) implies m(z; q; c) ≈ m(z; q), as predicted by the standard law of
large numbers. However, for c > 0, the empirical Stieltjes transform and the “true” Stieltjes
transform decouple in a deterministic manner. When complexity is high (e.g., c > 1), large
parts of information about m(z) are lost in finite samples even in the correctly specified
(q = 1) case, and this information loss is, of course, further exacerbated by misspecification.
       The last object we need to introduce is the particular formulation of the HJD that we use
to characterize pricing errors. In the high complexity regime, the exact details of computing
the out-of-sample HJD are important. We assume that the data sample is split into two sets:
in-sample data indexed as t ∈ [1, T ] and out-of-sample data indexed as t ∈ (T + 1, T + TOS ],
where TOS is the number of out-of-sample periods. For simplicity, we focus our theoretical
analysis on the case in which the test assets are the factors Ft (q) used to estimate the SDF.37
We thus define the out-of-sample HJD as


          HJ
         DOS (z; q; c) = EOS (z; q; c)′ BOS
                                         +
                                            EOS (z; q; c) ,


Where EOS (z; q; c) =          1
                                    P
                              TOS     t∈(T,T +TOS ] Ft (q)M̂t (z; q; c) is the out-of-sample pricing error
                             1                                ′
                                  P
vector and BOS =            TOS     t∈(T,T +TOS ] Ft (q)Ft (q)    is the out-of-sample test asset second
moment.
  37
    The pricing error properties of the SDF are particularly tractable to derive when the test assets are the
P factors Ft (q), but this point can be generalized this at the cost of further notation and derivations.




                                                       50
4.6      The Theoretical Behavior of Large Factor Models

Characterizing the behavior of factor portfolios in high dimensions requires tools from RMT.
Established RMT results (see, e.g. Hastie et al., 2019) apply to a setting with P, T → ∞
and are based on assumptions of independence of higher moments of the underlying high-
dimensional variables. However, these assumptions are violated in our setting because factors
Ft+1 = St′ Rt+1 exhibit highly complex non-linear dependencies. This makes our setting
significantly more complex and requires developing novel mathematical tools for dealing
simultaneously with three infinities: N, T, P → ∞. We develop these tools in the Internet
Appendix. They allow us to prove our main theoretical result below. One striking implication
of this result is the fact that the rate at which N → ∞ is irrelevant: The only thing that
matters for the asymptotic behavior is complexity c = lim P/T. The relative rate at which
N goes to infinity versus P, T has no impact on the asymptotics.38
       We now state our main theoretical result, which describes the expected out-of-sample
properties of large factor models.

Theorem 3 In the limit as N, P, T → ∞, P/T → c, P/P ∗ → q, the expected out-of-sample
moments of the ridge SDF portfolio satisfy


          lim E[R̂TM+1 (z; q; c)] = E Z ∗ (z; q; c); q where
                                                      
  i.
                                                                                c(1 − m(−z; c; q)z)
          Z ∗ (z; q; c) = z 1 + ξ(z; q; c) ∈ (z, z + c) and ξ(z; q; c) =
                                          
                                                                                                     ,
                                                                             1 − c(1 − m(−z; c; q)z)
          lim Var[R̂TM+1 (z; q; c)] = V Z ∗ (z; q; c); q + G(z; q; c) R Z ∗ (z; q; c); q where
                                                                                       
 ii.

          G(z; q; c) = (zξ(z; q; c))′ ∈ (0, cz −2 ], R(z; q) ≡ (1 − E(z; q))2 + V(z; q)
                                                                                              2
              Var[R̂TM+1 (z; q; c)]                                            1 − E(Z ∗ ; q)
                                                                             
                                                         1
iii.      lim                       = (1 + G(z; q; c)) 2 ∗      + G(z; q; c)                     ,
              E[R̂TM+1 (z; q; c)]2                    S (Z ; q)                  E(Z ∗ ; q)
          where S 2 (z; q) = E 2 (z; q)/V(z; q)
                                       ′
iv.              HJ
          lim E[DOS (z; q; P ; T ) − F̄OS  +
                                          BOS F̄OS ] = −1 + (1 + G(z; q))R(Z ∗ (z; q; c); q) .
  38
    In fact, as we show in the Internet Appendix, the finite-N error is controlled solely by tr(Σ2 )/ tr(Σ)2 ,
the Herfindahl index of the eigenvalues of Σ.


                                                     51
The central theme in Theorem 3 is that the large number of factors relative to the number of
training observations limits the estimator’s ability to learn the true parameters. When c > 0,
there are too many parameters and too few data points for the estimator to converge to its
population counterpart. This failure to fully hone in on the truth results in an asymptotic
wedge between the out-of-sample performance of the trained model and that of the true
model. We refer to this as “limits to learning.” Perhaps surprisingly, Theorem 3 shows that
we can explicitly quantify the effects of limits to learning using only knowledge of the factors’
sample covariance in the training data.
    Limits to learning manifest in two ways—implicit shrinkage and complexity risk—which
impact the SDF’s out-of-sample properties. We describe these properties now.


4.6.1     Expected Return

Part i. of Theorem 3 describes how complexity inhibits the expected return of the SDF
portfolio. It describes the expected return in terms of the infeasible ridge portfolio’s return.
The key to this is the function Z ∗ (z; q; c), which is the “implicit shrinkage” of the feasible
estimator.     Z ∗ is monotone increasing in c.             In other words, high complexity imposes
additional shrinkage on the SDF, above and beyond the explicit ridge shrinkage z.39
    If the model is correctly specified (q = 1) and with a complexity of zero, then
Z ∗ (z; 0; 1) = z and the feasible SDF’s expected return converges to the infeasible expected
             h         i
return, E λ̂(z) RT +1 → E[λ(z)′ RT +1 ] = E(z). But holding z fixed, a rise in complexity to
                  ′


c > 0 induces additional bias in the estimator and drives down the expected return of the
SDF portfolio. By how much? By the same amount that the expected return drops when
the infeasible portfolio’s shrinkage rises from z to Z ∗ (z; 1; c). In other words, the challenge
of learning in a complex setting is equivalent to knowing the true factor moments but being
   39
      Complexity generates this additional implicit shrinkage in an intuitive way. Holding z fixed, if we increase
P , we cannot raise ∥λ∥2 further due to the ridge penalty. By adding more parameters, we can only continue
to satisfy the ridge constraint by shrinking the λ̂ vector further.




                                                       52
forced to use an unduly large shrinkage. Remarkably, Z ∗ (z; 1; c) is available in closed form
thanks to the expression for ξ(z; q; c) from RMT.
   The monotonicity of Z ∗ (z; q; c) in z means that out-of-sample expected returns are highest
with minimal shrinkage. But even in the ridgeless limit when z → 0, Theorem 3 shows there
are limits to learning. In particular, there is an unavoidable reduction in expected return
because Z ∗ (z; q; c) is uniformly bounded away from zero in the high complexity regime
(c > 1).
   Thus, limits to learning hold even if the model is correctly specified. But this case
is unrealistic; we can’t ever expect to achieve an empirical model that nests all relevant
conditioning information or uses that information in its proper nonlinear form. Furthermore,
under correct specification, comparative statics for complexity change both the empirical and
the true model as we vary c. Thus, these theoretical comparative statics cannot be taken to
data.
   The empirically relevant comparative statics must consider a single true DGP, in essence
fixing the set of true factors and varying the number of those factors that the empirical
model has access to. We can conceptualize these comparative statics by varying q. When
the model is misspecified (q < 1), expected returns are hindered further because the model
relies on incomplete information. But the effect of q is subtle. Holding T fixed, a higher q
has two opposing effects on the expected SDF return. First, larger q means that there are
more empirical factors, so c rises as well, which exacerbates the limits to learning. However,
higher q also reduces specification bias and, therefore, improves the approximation power
of the model. This shows up as a smaller implicit shrinkage, Z ∗ . Which effect dominates
depends on the eigenvalue distribution of the factors. As we will see in the calibration below,
when there is a concentrated eigenvalue distribution and thus a few dominant factors—as
in the assumptions of the APT—the cost of complexity (i.e., more severe limits to learning)
dominates the approximation benefits and high complexity may hurt expected SDF returns



                                              53
on net. But when the eigenvalue distribution is dispersed, and there are many relevant
factors—i.e., under the conditions of the AIPT—approximation gains dominate, and high
complexity leads to better out-of-sample SDF returns.


4.6.2    Variance

Part ii. of Theorem 3 regards the variance of the ridge SDF portfolio. On the right side of
(35), the first term relates to the implicit shrinkage effect discussed above. In the large P
limit, the feasible SDF portfolio with parameter z has the same volatility as the infeasible
portfolio with a larger ridge parameter Z ∗ (z; q; c) > z. Due to this implicit shrinkage and
the monotonicity of Z ∗ in c, SDF portfolio variance decreases with model complexity when
c > 1.
   While the first term in (35) reflects the implicit shrinkage in large factor models, the
second term represents a different phenomenon that we call “complexity risk.” Complexity
risk can be thought of as sampling variation that exists even in the large T limit. It is a pure-
variance effect governed by the function G(z; q; c), independent of expected factor returns,
and only depends on the eigenvalue distribution of E[Ft (q)Ft (q)′ ]. For a simple model, c = 0,
there are infinitely more observations than parameters, so the SDF estimator converges
to a non-random limit, thus G(z; q; 0) = 0, and there is no complexity risk. However,
when c > 0, sampling variation survives even in the large T limit because the number of
parameters is too large to be accurately informed by the data. Complexity risk is a second-
moment manifestation of limits to learning. The behavior of SDF portfolio variance is driven
primarily by c and is relatively insensitive to the extent of model misspecification, q.


4.6.3    Sharpe Ratio and Pricing Error

Part iii. of Theorem 3 describes the SDF portfolio’s limiting Sharpe ratio. First, focusing
on the effect of complexity, consider the correct specification case, q = 1. Building on



                                               54
i. and ii., a rise in complexity unambiguously decreases the expected SDF return due to
implicit shrinkage. The effect on the variance is mixed—implicit shrinkage lowers variance,
but complexity risk raises it. The net effect of complexity is an unambiguous decrease in the
Sharpe ratio in the correctly specified setting.
   As emphasized above, while the q = 1 case is helpful for developing intuition around com-
plexity effects, our real interest lies in understanding SDF Sharpe ratios in the misspecified
setting. In this case, the effect of complexity on the Sharpe ratio is ambiguous and depends
on the eigenvalue distribution of the factor covariance. When eigenvalues are concentrated,
complexity has a small net effect on SDF Sharpe, and can potentially reduce it. However,
when the eigenvalue distribution is relatively flat, the Sharpe ratio tends to increase with
complexity, and the gains from complexity are potentially large.
   In the high complexity limit, pricing error is the mirror image of Sharpe ratio. When
conditions are such that Sharpe ratio increases with complexity, it is also the case that
pricing errors are reduced by complexity.
   In summary, Theorem 3 characterizes the subtle mechanisms through which complexity
determines a model’s out-of-sample performance. Complexity introduces a tradeoff between
the quality of a model’s approximation for the unknown truth on the one hand versus limits
to learning (implicit shrinkage and complexity risk) on the other. In terms of the effect on the
SDF expected return, a larger model reduces specification bias, which raises expected returns,
but it also induces additional implicit shrinkage, which lowers returns. While complexity’s
implicit shrinkage has a dampening effect on SDF volatility, it at the same time raises
volatility by producing a sampling variation (i.e., complexity risk) that survives in the large
T limit. When the marginal approximation benefits are large relative to the loss due to
limits to learning, we find that the complexity raises the out-of-sample SDF Sharpe ratio
and reduces pricing errors. Under these conditions, there is a virtue of complexity, and large
factor models dominate simple, parsimonious models. Theorem 3 shows that the eigenvalue



                                              55
distribution among factors is critical for determining whether complexity is a virtue or a
vice.


4.7       Illustrating the Theory

Theorem 3 derives foundational results for understanding the role of complexity in factor
pricing models. However, the analytical expressions are dense and can be difficult to parse.
In this section, we attempt to bring Theorem 3 to life by visualizing the role of complexity
in different data environments. We present two calibrations of our theory: one is an AIPT
model with hundreds of common factors, and the other is an APT model with only a few
common factors.


4.7.1       Calibration 1: The AIPT

As emphasized in the theory discussion above, the eigenvalue distribution of E[F F ′ ] is a
critical driver of out-of-sample SDF behavior. Our calibrations assume that the eigenvalue
distribution of E[F F ′ ] is diagonal with eigenvalues

                         ∗
         η = {1/pα }Pp=1 , α ≥ 0.                                                        (35)


The larger the calibrated parameter, α, the more concentrated the eigenvalue distribution,
and the fewer prominent components there are among the factor portfolios F . The AIPT
and APT calibrations differ in only their choice of α.
       The AIPT calibration sets α = 0.5. The concept of “effective rank” is a useful means of
interpreting the α parameter. Defined as40


         EffRank(E[F F ′ ]) = (tr E[F F ′ ])2 / tr(E[F F ′ ]2 ),
  40
       See, e.g., Bartlett et al. (2020).




                                                       56
           Panel A: Expected Return                           Panel B: Variance




             Panel C: Sharpe Ratio                          Panel D: Pricing Error




     Figure 13: Out-of-sample Behavior of Large Factor Models in AIPT Calibration
Note. Limiting out-of-sample mean, variance, Sharpe ratio, and pricing error (HJD) of the SDF as a
                                                                                         ∗
function of c and z from Theorem 3 with eigenvalues of E[F F ′ ] given by η = {1/p0.5 }P
                                                                                       p=1 .




effective rank quantifies the number of dominant principal components among the factors.
With α = 0.5, the effective rank of E[F F ′ ] in our AIPT calibration is roughly 500, capturing
the spirit of the AIPT conjecture that the underlying DGP possesses a large number of
distinct factors.
   The remaining calibration choices do not vary across AIPT and APT calibrations. The




                                               57
vector of mean returns behaves according to

                                         
                           1        1+β
                                        
      E[F ] ∼ N       0, κ ∗ diag η         .
                          P

The β parameter controls the degree of alignment between (squared) factor means and
variances. We use β = 1.5, implying that higher variance factors have higher squared
Sharpe ratios, as in the economic prior advocated by KNS. The κ parameter controls the
overall magnitude of the factor Sharpe ratios, and we set κ = 400 to match the magnitude
of SDF Sharpe ratio in AIPT calibration with the empirical results in Figure 2. In terms
of dimensionality, our calibration assumes T = 360 training observations (as in our data
analysis) and a true model complexity of P ∗ /T to 10. We use Theorem 3 to draw theoretical
VoC curves by gradually increasing the fraction of observable factors in the empirical model
(q = P/P ∗ ) from 0 to 1, thus varying empirical complexity c = P/T from 0 to 10. These
illustrations are the direct theoretical counterparts to the empirical VoC curves presented in
Section 3.
   Figure 13 plots the AIPT calibration results. Each curve corresponds to a different choice
of ridge penalty z, and each point on a curve corresponds to a different number of factors
P . The four panels show how complexity (on the x-axis) affects the expected out-of-sample
mean, variance, and Sharpe of the SDF portfolio and the SDF’s expected out-of-sample
pricing errors.
   Panel A shows that the out-of-sample expected return of the SDF portfolio is increasing
in model complexity. The intuition for this result is that higher model complexity allows the
SDF model to approximate the unknown true SDF more accurately. As the approximation
improves and specification error shrinks, the estimated SDF is able to achieve a higher
expected portfolio return. When the true DGP has many factors, the gains from better
approximation overwhelm performance loss due to limits to learning. This is true for all
ridge penalty levels and throughout the full range of complexity. Expected return curves are


                                                58
flatter with higher explicit ridge shrinkage, z. This is because more shrinkage increases the
estimator’s bias, reducing the approximating power of the SDF, which eats into its returns.
      In Panel B, we see that SDF volatility is highly sensitive to model complexity. When c
approaches unity, the variance of the low z SDFs spikes. The logic for this behavior follows
from arguments in KMZ. As c → 1, the unregularized sample covariance matrix of factors
becomes unstable, which causes the unregularized estimator to explode. Intuitively, when
c = 1, the number of model parameters equals the number of time series observations, so
there is an SDF estimate with an infinite in-sample Sharpe ratio. Without regularization, this
estimator badly overfits the training data and produces disastrous out-of-sample behavior.
      When c ≫ 1, the ridge SDF estimator experiences implicit shrinkage due to complexity,
which reduces SDF volatility. As the other curves in Panel B show, SDF volatility can also
be controlled by raising the explicit ridge shrinkage, z. This is the low variance benefit of
the shrinkage-induced bias.
      The out-of-sample SDF Sharpe ratio is shown in Panel C. The ridgeless SDF estimator
demonstrates “double ascent,” in analogy to the “double descent” MSE phenomenon studied
in statistics literature.41 At low complexity (c ≪ 1), the Sharpe ratio rises with complexity
as larger models show improved approximation power benefits. But near c = 1, the Sharpe
ratio collapses to zero due to the explosion in SDF variance. Finally, at high complexity
(c ≫ 1), variance comes under control, and the benefits of improved approximation again
dominate and lead to an increasing Sharpe ratio. Panel C also demonstrates that, with
appropriate explicit shrinkage z, the complex SDF estimator exhibits “permanent ascent”
with an increasing Sharpe ratio throughout the full range of complexity.
      Finally, Panel D illustrates the behavior of out-of-sample SDF pricing errors (HJD) as
a function of complexity. Pricing errors in Panel D are a mirror image of the patterns for
the Sharpe ratio in Panel C. The more complex the SDF, the better its ability to price
assets out-of-sample. As long as the number of true factors (P ) is large, these pricing errors
 41
      See, for example, Spigler et al. (2019); Belkin et al. (2018, 2019, 2020); Bartlett et al. (2020).


                                                        59
never go to zero, even for very high-complexity empirical models. Higher complexity means
the empirical SDF includes more true factors, improving its pricing ability. But at the same
time, higher complexity also means more stringent limits to learning, so out-of-sample pricing
errors are bounded away from zero (this is true even for high complexity models that are
correctly specified).
       The most important point regarding Figure 13 is that it closely matches the qualitative
patterns in the data, as documented in Figure 2. The out-of-sample expected return and
Sharpe ratio of the ridge SDF are gradually increasing in complexity while pricing errors are
decreasing.


4.7.2      Calibration 2: The APT

To contrast with the AIPT in the previous calibration, we change the DGP assumption so
that the cross-section of returns is dominated by only a few distinct factors, thus embodying
the APT conjecture. We accomplish this by setting the eigenvalue distribution parameter
α in (35) at α = 2.0, which implies an effective rank of approximately 2.5. In this case,
the cross-section of returns is dominated by only a few distinct factors, thus embodying the
APT conjecture.
       Figure 14 plots the APT calibration results. The main conclusion from this figure is that
there are no benefits to complexity when the eigenvalue distribution is highly concentrated.
When the ridge penalty is small (e.g., z ≤ 10−5 ), high-complexity models have lower Sharpe
ratios and larger pricing errors than models with complexity near zero. The fact that peak
SDF performance is reached with c ≪ 1 is at odds with the patterns in Figure 2, where
performance peaks at c ≫ 1 regardless of the value of z.42
  42
    Interestingly, while there are no gains to using large factor models in the APT calibration, there is
surprisingly also no cost as long as moderate ridge shrinkage is used. This is because the overfit costs
of adding additional (mostly redundant) parameters are offset by the implicit shrinkage that comes with
complexity.




                                                   60
           Panel A: Expected Return                           Panel B: Variance




             Panel C: Sharpe Ratio                          Panel D: Pricing Error




     Figure 14: Out-of-sample Behavior of Large Factor Models in APT Calibration
Note. Limiting out-of-sample mean, variance, Sharpe ratio, and pricing error (HJD) of the SDF as a
                                                                                       ∗
function of c and z from Theorem 3 with eigenvalues of E[F F ′ ] given by η = {1/p2 }P
                                                                                     p=1 .




   In summary, while the AIPT conjecture aligns closely with the evidence in Figure 2, the
APT appears counterfactual.




                                               61
4.7.3   Covariance Matrices For Discriminating Between APT and AIPT

The preceding calibrations compare the APT and AIPT to real-world data in terms of
empirical asset pricing properties such as the Sharpe ratio. We can also compare APT and
AIPT based on their predictions for the sample covariance matrix of factors.
   Both DGPs assume a particular structure for the eigenvalue distribution of the true
factor covariance matrix—either concentrated in a few dominant components in the case of
the APT or distributed across a large number of components per the AIPT. One important
consideration is that, in high-complexity environments, the sample covariance of factors
will deviate markedly from the true covariance. This means we should not evaluate models
based on how closely a model’s true eigenvalue distribution aligns with empirical eigenvalues.
Instead, we must compare the expected sample eigenvalue distribution under each model
assumption to the empirical distribution. Fortunately, we can use random matrix theory
to make precise predictions for the expected sample eigenvalue distributions implied by the
APT and AIPT models, and these predictions can then be compared directly to the empirical
eigenvalue distribution.
   The results of this comparison are shown in Figure 15. The calibrations are the same
as those used in the preceding sections. We show the true eigenvalue distributions in our
AIPT (dotted red line) and APT (dotted blue line) calibrations. Next, the solid red and
blue lines show the expected sample eigenvalue distributions implied by RMT for each model
for the calibrated high complexity sample (i.e., with T = 360 observations and P = 3,600
factors). In high-complexity settings, sample covariances are unavoidably polluted by noise.
The RMT curves demonstrate how this noise obscures the true eigenvalue distribution and
causes the sample eigenvalues from the two models to move toward one another.
   Finally, the solid black line shows the realized empirical eigenvalue distribution in our
empirical model with the same number of factors and observations. The main conclusion




                                             62
              Figure 15: APT, AIPT, and Empirical Eigenvalue Distributions
Note. The figure shows eigenvalue distributions for the factor covariance matrix in our calibrations and
in the data. The dotted red and blue lines show the true eigenvalue distributions in our AIPT (α = 0.5)
and APT (α = 2.0) calibrations, respectively. The solid red and blue lines show the corresponding expected
sample eigenvalue distributions for each model implied by RMT for the calibrated high complexity sample
(i.e., with T = 360 observations and P = 3,600 factors). The solid black line shows the sample eigenvalue
distribution in our empirical analysis with T = 360 and P = 3,600.


from this plot is that the AIPT provides a better match to the data not just in terms of
Sharpe ratios and pricing errors but also in terms of the covariance structure among factors.


5    Conclusion

In this paper, we show that the out-of-sample performance of factor pricing models is
increasing in terms of the number of factors. Larger models achieve higher risk-adjusted
returns and lower pricing errors than smaller models, including standard low-dimensional
factor models in the literature. Our novel machine learning empirical design allows us to
compare models with varying degrees of statistical complexity while holding the raw data

                                                   63
inputs fixed. More heavily parameterized models outperform simpler models because they
afford a better approximation to the unknown data-generating process. The cost of these
parameters is higher out-of-sample model volatility, but this cost is more than justified by
the gains in expected returns from using rich parameterizations.
   We then develop a theory of machine learning SDF estimators founded on the concept
of statistical model complexity. Among our key theoretical findings is the virtue of asset
pricing model complexity: In essence, the out-of-sample performance of factor pricing models
generally improves with the number of factors. This result holds as long as the covariance
matrix of factors is not too concentrated. We also characterize the limits to learning that arise
from the application of highly parameterized prediction models amid relative data scarcity.
While heavy parameterization precludes consistent estimation of the SDF, the virtue of
complexity arises from the improved approximation power of complex models, overwhelming
the countervailing effect of limits to learning. The empirical patterns that we document bear
a strikingly close resemblance to the predictions of our theory. Meanwhile, the theoretical
predictions of the APT are contradicted by our empirical evidence.




                                               64
References


Asness, Clifford S, Tobias J Moskowitz, and Lasse Heje Pedersen, “Value and
   momentum everywhere,” The Journal of Finance, 2013, 68 (3), 929–985.

Avramov, Doron, Si Cheng, and Lior Metzker, “Machine learning vs. economic
   restrictions: Evidence from stock return predictability,” Management Science, 2023,
   69 (5), 2587–2619.

Backus, David, Bryan Routledge, and Stanley Zin, “Asset prices in business cycle
   analysis,” Unpublished manuscript, New York University, 2007.

Bai, Zhi-Dong and Jack W Silverstein, “No eigenvalues outside the support of the
   limiting spectral distribution of large-dimensional sample covariance matrices,” The
   Annals of Probability, 1998, 26 (1), 316–345.

Bai, Zhidong and Wang Zhou, “Large sample covariance matrices without independence
   structures in columns,” Statistica Sinica, 2008, pp. 425–442.

Bansal, Ravi and Amir Yaron, “Risks for the long run: A potential resolution of asset
   pricing puzzles,” The journal of Finance, 2004, 59 (4), 1481–1509.

Barillas, Francisco and Jay Shanken, “Comparing asset pricing models,” The Journal
   of Finance, 2018, 73 (2), 715–754.

Bartlett, Peter L, Philip M Long, Gábor Lugosi, and Alexander Tsigler, “Benign
   overfitting in linear regression,” Proceedings of the National Academy of Sciences, 2020,
   117 (48), 30063–30070.

Belkin, M, D Hsu, S Ma, and S Mandal, “Reconciling modern machine learning and
   the bias-variance trade-off. arXiv e-prints,” 2018.

Belkin, Mikhail, Alexander Rakhlin, and Alexandre B Tsybakov, “Does data
   interpolation contradict statistical optimality?,” in “The 22nd International Conference
   on Artificial Intelligence and Statistics” PMLR 2019, pp. 1611–1619.

                                            65
   , Daniel Hsu, and Ji Xu, “Two models of double descent for weak features,” SIAM
   Journal on Mathematics of Data Science, 2020, 2 (4), 1167–1180.
Box, George EP and Gwilym Jenkins, Time Series Analysis: Forecasting and Control,
   San Francisco: Holden-Day, 1970.
Bryzgalova, Svetlana, Jiantao Huang, and Christian Julliard, “Consumption in
   asset returns,” The Journal of Finance, Forthcoming.
   , Markus Pelger, and Jason Zhu, “Forest through the trees: Building cross-sections
   of stock returns,” Available at SSRN 3493458, 2020.
Campbell, John Y, Stefano Giglio, Christopher Polk, and Robert Turley, “An
   intertemporal CAPM with stochastic volatility,” Journal of Financial Economics, 2018,
   128 (2), 207–233.
Chen, Andrew Y and Tom Zimmermann, “Open source cross-sectional asset pricing,”
   Critical Finance Review, Forthcoming, 2021.
Chen, Luyang, Markus Pelger, and Jason Zhu, “Deep learning in asset pricing,”
   Management Science, 2023.
Chen, Xiaohong and Sydney C Ludvigson, “Land of addicts? an empirical investi-
   gation of habit-based asset pricing models,” Journal of Applied Econometrics, 2009, 24
   (7), 1057–1093.
Cheng, Xiuyuan and Amit Singer, “The spectrum of random inner-product kernel
   matrices,” Random Matrices: Theory and Applications, 2013, 2 (04), 1350010.
Chernov, Mikhail, Magnus Dahlquist, and Lars A Lochstoer, “Unpriced Risks: Re-
   thinking Cross-Sectional Asset Pricing,” Technical Report, National Bureau of Economic
   Research 2025.
   ,     , and Lars Lochstoer, “Pricing currency risks,” The Journal of Finance, 2023,
   78 (2), 693–730.
Chinco, Alex, Adam D Clark-Joseph, and Mao Ye, “Sparse signals in the cross-section
   of returns,” The Journal of Finance, 2019, 74 (1), 449–492.

                                           66
Christiano, Lawrence J, Roberto Motto, and Massimo Rostagno, “Risk shocks,”
   American Economic Review, 2014, 104 (1), 27–65.

Cong, Lin William, Guanhao Feng, Jingyu He, and Xin He, “Growing the efficient
   frontier on panel trees,” NBER Working Paper, 2022, (w30805).

Connor, Gregory, Matthias Hagmann, and Oliver Linton, “Efficient semiparametric
   estimation of the Fama–French model and extensions,” Econometrica, 2012, 80 (2),
   713–754.

Croce, Mariano M, Tatyana Marchuk, and Christian Schlag, “The leading pre-
   mium,” The Review of Financial Studies, 2023, 36 (8), 2997–3033.

Da, Rui, Stefan Nagel, and Dacheng Xiu, “The Statistical Limit of Arbitrage,”
   Technical Report, Technical Report, Chicago Booth 2022.

Daniel, Kent, David Hirshleifer, and Lin Sun, “Short-and long-horizon behavioral
   factors,” The review of financial studies, 2020, 33 (4), 1673–1736.

Dew-Becker, Ian and Stefano Giglio, “Asset pricing in the frequency domain: theory
   and empirics,” The Review of Financial Studies, 2016, 29 (8), 2029–2068.

Do, Yen and Van Vu, “The spectrum of random kernel matrices: universality results for
   rough and varying kernels,” Random Matrices: Theory and Applications, 2013, 2 (03),
   1350005.

Fama, Eugene F, “Stock returns, expected returns, and real activity,” The journal of
   finance, 1990, 45 (4), 1089–1108.

    and Kenneth R French, “Common risk factors in the returns on stocks and bonds,”
   Journal of financial economics, 1993, 33 (1), 3–56.

    and       , “A five-factor asset pricing model,” Journal of financial economics, 2015,
   116 (1), 1–22.

Fan, Jianqing, Yuan Liao, and Weichen Wang, “Projected principal component
   analysis in factor models,” Annals of statistics, 2016, 44 (1), 219.

                                             67
   , Zheng Tracy Ke, Yuan Liao, and Andreas Neuhierl, “Structural Deep Learning
   in Conditional Asset Pricing,” Available at SSRN 4117882, 2022.

Feng, Guanhao, Stefano Giglio, and Dacheng Xiu, “Taming the factor zoo: A test of
   new factors,” The Journal of Finance, 2020, 75 (3), 1327–1370.

Filipovic, Damir and Paul Schneider, “Fundamental properties of linear factor models,”
   arXiv preprint arXiv:2409.02521, 2024.

Freyberger, Joachim, Andreas Neuhierl, and Michael Weber, “Dissecting charac-
   teristics nonparametrically,” The Review of Financial Studies, 2020, 33 (5), 2326–2377.

Gagliardini, Patrick, Elisa Ossola, and Olivier Scaillet, “Time-varying risk premium
   in large cross-sectional equity data sets,” Econometrica, 2016, 84 (3), 985–1046.

Giglio, Stefano and Dacheng Xiu, “Asset pricing with omitted factors,” Journal of
   Political Economy, 2021, 129 (7), 1947–1990.

   , Bryan Kelly, and Dacheng Xiu, “Factor models, machine learning, and asset
   pricing,” Annual Review of Financial Economics, 2022, 14, 337–368.

Gilchrist, Simon and Egon Zakrajšek, “Monetary policy and credit supply shocks,”
   IMF Economic Review, 2011, 59 (2), 195–232.

    and      , “Credit spreads and business cycle fluctuations,” American economic review,
   2012, 102 (4), 1692–1720.

   , Jae W Sim, and Egon Zakrajšek, “Uncertainty, financial frictions, and investment
   dynamics,” Technical Report, National Bureau of Economic Research 2014.

   , Vladimir Yankov, and Egon Zakrajšek, “Credit market shocks and economic
   fluctuations: Evidence from corporate bond and stock markets,” Journal of monetary
   Economics, 2009, 56 (4), 471–493.

Gu, Shihao, Bryan Kelly, and Dacheng Xiu, “Autoencoder Asset Pricing Models,”
   Journal of Econometrics, 2020.



                                            68
   ,         , and      , “Empirical asset pricing via machine learning,” The Review of
   Financial Studies, 2020, 33 (5), 2223–2273.
Guijarro-Ordonez, Jorge, Markus Pelger, and Greg Zanotti, “Deep learning statis-
   tical arbitrage,” arXiv preprint arXiv:2106.04028, 2021.
Han, Yufeng, Ai He, David Rapach, and Guofu Zhou, “Expected stock returns and
   firm characteristics: E-LASSO, assessment, and implications,” SSRN, 2019.
Hansen, Lars Peter and Kenneth J Singleton, “Generalized instrumental variables
   estimation of nonlinear rational expectations models,” Econometrica: Journal of the
   Econometric Society, 1982, pp. 1269–1286.
       and Ravi Jagannathan, “Implications of security market data for models of dynamic
   economies,” Journal of political economy, 1991, 99 (2), 225–262.
       and      , “Assessing specification errors in stochastic discount factor models,” The
   Journal of Finance, 1997, 52 (2), 557–590.
       and Scott F Richard, “The role of conditioning information in deducing testable
   restrictions implied by dynamic asset pricing models,” Econometrica: Journal of the
   Econometric Society, 1987, pp. 587–613.
Harvey, Campbell R, Yan Liu, and Heqing Zhu, “. . . and the cross-section of expected
   returns,” The Review of Financial Studies, 2016, 29 (1), 5–68.
Hastie, Trevor, Andrea Montanari, Saharon Rosset, and Ryan J Tibshirani,
   “Surprises in high-dimensional ridgeless least squares interpolation,” arXiv preprint
   arXiv:1903.08560, 2019.
He, Ai, Dashan Huang, Jiaen Li, and Guofu Zhou, “Shrinking factor dimension: A
   reduced-rank approach,” Management science, 2023, 69 (9), 5501–5522.
Hornik, Kurt, Maxwell Stinchcombe, and Halbert White, “Multilayer feedforward
   networks are universal approximators,” Neural networks, 1989, 2 (5), 359–366.
Hou, Kewei, Chen Xue, and Lu Zhang, “Digesting anomalies: An investment ap-
   proach,” The Review of Financial Studies, 2015, 28 (3), 650–705.

                                             69
   ,       , and     , “Replicating anomalies,” The Review of Financial Studies, 2020, 33
   (5), 2019–2133.

   , Haitao Mo, Chen Xue, and Lu Zhang, “An augmented q-factor model with
   expected growth,” Review of Finance, 2021, 25 (1), 1–41.

Jensen, Theis Ingerslev, Bryan Kelly, and Lasse Heje Pedersen, “Is there a
   replication crisis in finance?,” The Journal of Finance, 2023, 78 (5), 2465–2518.

Jordà, Òscar, “Estimation and inference of impulse responses by local projections,”
   American economic review, 2005, 95 (1), 161–182.

       and Alan M Taylor, “Local projections,” Journal of Economic Literature, 2025, 63
   (1), 59–110.

Jurado, Kyle, Sydney C Ludvigson, and Serena Ng, “Measuring uncertainty,”
   American Economic Review, 2015, 105 (3), 1177–1216.

Kan, Raymond and Cesare Robotti, “Model comparison using the Hansen-Jagannathan
   distance,” The Review of Financial Studies, 2009, 22 (9), 3449–3490.

Karoui, Noureddine El, “The spectrum of kernel random matrices,” The Annals of
   Statistics, 2010, 38 (1), 1–50.

Kelly, Bryan and Dacheng Xiu, “Financial machine learning,” Foundations and
   Trends® in Finance, 2023, 13 (3-4), 205–363.

   , Boris Kuznetsov, Semyon Malamud, and Teng Andrea Xu, “Large (and Deep)
   Factor Models,” arXiv preprint arXiv:2402.06635, 2024.

   , Semyon Malamud, and Kangying Zhou, “The virtue of complexity in return
   prediction,” The Journal of Finance, 2024, 79 (1), 459–503.

   , Seth Pruitt, and Yinan Su, “Characteristics are Covariances: A Unified Model of
   Risk and Return,” Journal of Financial Economics, 2020.

Kelly, Bryan T and Semyon Malamud, “Understanding The Virtue of Complexity,”
   Available at SSRN 5346842, 2025.

                                           70
    ,         , and Kangying Zhou, “The virtue of complexity everywhere,” Available at
    SSRN, 2022.

Kozak, Serhiy, “Kernel trick for the cross-section,” Available at SSRN 3307895, 2020.

        and Stefan Nagel, “When do cross-sectional asset pricing factors span the stochastic
    discount factor?,” Technical Report, National Bureau of Economic Research 2023.

    ,         , and Shrihari Santosh, “Interpreting Factor Models,” The Journal of Finance,
    2018, 73 (3), 1183–1223.

    ,         , and     , “Shrinking the cross-section,” Journal of Financial Economics, 2020,
    135 (2), 271–292.

Lettau, Martin and Markus Pelger, “Factors that fit the time series and cross-section
    of stock returns,” The Review of Financial Studies, 2020, 33 (5), 2274–2325.

Liu, Yukun and Ben Matthies, “Long-Run Risk: Is It There?,” The Journal of Finance,
    2022, 77 (3), 1587–1633.

        and      , “Is Long Run Risk Really Priced? A Reply,” A Reply (April 22, 2024), 2024.

Maio, Paulo, “Is Long-Run Risk Really Priced? Revisiting Liu and Matthies (2022),” The
    Journal of Finance, 2024, 79 (4), 2885–2900.

Marčenko, Vladimir A and Leonid Andreevich Pastur, “Distribution of eigenvalues
    for some sets of random matrices,” Mathematics of the USSR-Sbornik, 1967, 1 (4), 457.

Martin, Ian WR and Stefan Nagel, “Market efficiency in the age of big data,” Journal
    of Financial Economics, 2021.

McLean, R David and Jeffrey Pontiff, “Does academic research destroy stock return
    predictability?,” The Journal of Finance, 2016, 71 (1), 5–32.

Parker, Jonathan A and Christian Julliard, “Consumption risk and the cross section
    of expected returns,” Journal of Political Economy, 2005, 113 (1), 185–222.

Preite, Massimo Dello, Raman Uppal, Paolo Zaffaroni, and Irina Zviadadze,
    “What is Missing in Asset-Pricing Factor Models?,” 2022.

                                               71
Rahimi, Ali and Benjamin Recht, “Random Features for Large-Scale Kernel Machines.,”
    in “NIPS,” Vol. 3 Citeseer 2007, p. 5.

Rapach, David E and Guofu Zhou, “Time-series and cross-sectional stock return
    forecasting: New machine learning methods,” Machine learning for asset management:
    New developments and financial applications, 2020, pp. 1–33.

Ross, Stephen A., “The Arbitrage Theory of Capital Asset Pricing,” Journal of Economic
    Theory, 1976, 13, 341–360.

Santos, Tano and Pietro Veronesi, “Conditional betas,” 2004.

Spigler, Stefano, Mario Geiger, Stéphane d’Ascoli, Levent Sagun, Giulio Biroli,
    and Matthieu Wyart, “A jamming transition from under-to over-parametrization
    affects generalization in deep learning,” Journal of Physics A: Mathematical and Theo-
    retical, 2019, 52 (47), 474001.

Stambaugh, Robert F and Yu Yuan, “Mispricing factors,” The review of financial
    studies, 2017, 30 (4), 1270–1315.

Tukey, John W, “Discussion, emphasizing the connection between analysis of variance and
    spectrum analysis,” Technometrics, 1961, 3 (2), 191–219.

White, Halbert, Estimation, inference and specification analysis number 22, Cambridge
    university press, 1996.




                                             72
Internet Appendix

A     Road Map

The Appendix is organized as follows:


    • Section B provides a Neural Network interpretation of the AIPT environment.

    • Section C reports some useful properties of the infeasible portfolio.

    • Section D presents some auxiliary results that we use in all of our proofs.

    • Section E provides a proof of Proposition 2: The fact that, in the high complexity
      limit, characteristic-managed portfolios span the SDF.

    • Section F provides some preliminaries on Random Matrix Theory, paving the road for
      all of our subsequent theoretical analyses. It provides a roadmap for the subsequent
      appendices and explains how this requires developing non-trivial arguments accounting
      for the complex dependency structure among factors Ft+1 = St′ Rt+1 that make classic
      results (such as, e.g., those from Hastie et al. (2019)) inapplicable to our setting.

    • Section G provides the proof of one of the most important and technically challenging
      results in our paper: Lemma 11. This Lemma is the key ingredient to the proof of all
      Random Matrix Theory results. It establishes the striking result that the asymptotic
      limit as P, T, N → ∞ is independent of the rate as which N → ∞. In fact, the rate of
      convergence to this limit is controlled solely by tr(Σ2 ).

    • Section H develops mathematical techniques for computing RMT quantities arising in
      AIPT.

    • Section I computes lim E[R̂TM+1 (z; q; c)], proving item i. of Theorem 3.


                                               73
    • Section J computes lim E[(R̂TM+1 (z; q; c))2 ], proving item ii. of Theorem 3.

    • Section K computing the limit of HJD distance, proving item iv. of Theorem 3.


B     Neural Network Interpretation of the AIPT Environment

The structure of returns in Assumption 1 has a clear machine-learning interpretation.
Imagine for a moment that returns on asset i are generated by a low-dimensional factor
model like those common in economic theory,43


      Ri,t+1 = β(Xi,t )′ Gt+1 + ui,t+1 ,                                                       (36)


where Xi,t is a vector of J conditioning variables that determines i’s conditional betas on a
small number K of latent factors, Gt+1 . If one has no knowledge of the specific functional
form for the conditional beta function, one can use a machine learning model to approximate
it. For example, a shallow neural network could replace the K × 1 vector β(Xi,t ) with the
approximation

                   P
                   X
      β(Xi,t ) ≈         ξp Si,t,p = |{z}
                                      Ξ Si,t ,                                                 (37)
                   p=1
                                          |{z}
                                    K×P P ×1



where


      Si,t = A(ΩXi,t ) = (A(ωp′ Xi,t ))Pp=1 .                                                  (38)


The neural network model approximates the unknown beta function with a linear combina-
tion of “generated conditioning variables” denoted Si,t,p . Specifically, each Si,t,p is a basis
function that captures nonlinear predictive information in the raw conditioning variables
  43
     Santos and Veronesi (2004) is an example asset pricing theory that generates a conditional beta
formulation along these lines.


                                                 74
Xi,t . To build the basis functions, the neural network first generates a J × P matrix
Ω = (ωp )Pp=1 of weights with rows ωp to combine the elements of Xi,t into P different linear
combinations of ΩXi,t ∈ RP . Next, these linear combinations are transformed by a nonlinear
activation function A(x), so that we end up with nonlinear features Si,t = A(ΩXi,t ) ∈ RP .
Then, equation (37) collects the P basis terms into a weighted sum in order to approximate
β(Xi,t ). The K ×1 vectors ξp determine how each nonlinear basis term best contributes to the
approximation of each of the K betas. We can write this sum in a matrix form by collecting
the basis terms into a P × 1 vector Si,t and the weights into the K × P matrix Ξ. Universal
approximation theory, such as Hornik et al. (1989), ensures that the formulation in (37) can
accurately approximate the true conditional beta function under regularity conditions.44
       To tie this back to Assumption 1, we may stack assets’ beta coefficients into an N × K
matrix and substitute (37) into (36) to deliver


         Rt+1 ≈ St F̃t+1 + ut+1 , with
                                                                                                (39)
         F̃t+1 = Ξ′ Gt+1 , ν = E[F̃t+1 ] = Ξ′ E[Gt+1 ] .

The key point of this neural network example is that, while Assumption 1 treats the factor
loadings St as known and potentially high-dimensional, we interpret it as a generic statistical
specification that arises from machine learning approximations to an unknown (and likely
low-dimensional) factor pricing model.


C       Properties of the Infeasible Portfolio

Let λ = E[F F ′ ]−1 E[F ] . By a direct calculation,45

                                         1
         λ = E[F F ′ ]−1 E[F ] =                Var[F ]−1 E[F ] ,                               (40)
                                    1 + M axSR2
  44
     The approximating structure in (37) is analyzed by Gu et al. (2020a) and is a semi-nonparametric
extension of the IPCA model in Kelly et al. (2020).
  45
     See the Sherman-Morrison formula (98).


                                                   75
where Var[F ] is the covariance matrix of factors, and where we have defined


      M axSR2 = E[F ]′ Var[F ]−1 E[F ]                                                  (41)


to be the maximal achievable unconditional squared Sharpe ratio. Most existing papers
perform their analysis assuming that the population moments of the factors are directly
observable and, hence, so is the vector of factor risk premia, λ. The corresponding portfolio
satisfies

                                                                     M axSR2
      E[λ′ Ft+1 ] = E[(λ′ Ft+1 )2 ] = E[F ]′ E[F F ′ ]−1 E[F ] =               .        (42)
                                                                   1 + M axSR2

It will be instructive for our subsequent analysis to decompose the maximal Sharpe ratio
into the contributions coming from the factor principal components. Given the eigenvalue
decomposition Var[F ] = U diag(µ)U ′ , we can define P Ci to be the i-th column of U ′ F . In
the sequel, we will use


      θ = U ′ E[F ]                                                                     (43)


to denote the vector of mean returns of the PCs. Then, we can rewrite the maximal Sharpe
ratio (41) as

                      X θ2         X
                           i
      M axSR2 =                =       (SR(P Ci ))2 .                                   (44)
                      i
                          µi       i


We will now use this representation to understand the effect of ridge shrinkage on the
performance of the infeasible efficient portfolio,


       inf eas
      Rt+1     (z) = E[F ]′ (zI + Var[F ])−1 Ft+1 .                                     (45)




                                                  76
We call this portfolio infeasible because, in the big data regime, when P > T, neither
E[F ] ∈ RP nor E[F F ′ ] ∈ RP ×P can be efficiently estimated from only T observations. By
               inf eas
construction, Rt+1     (0) = λ′ Ft+1 achieves the M axSR, and

                                                                       A(z)
      E(z) = E[Rinf eas (z)] = E[F ]′ (zI + E[F F ′ ])−1 E[F ] =              ,      (46)
                                                                     1 + A(z)

where we have defined


      A(z) = E[F ]′ (zI + Var[F ])−1 E[F ]
         X                 µi
      =     (SR(P Ci ))2
                         µi + z                                                      (47)
          i
         X                   1         X
      =     (SR(P Ci ))2           ≈         (SR(P Ci ))2
          i
                         1 +  z/µi    i:µ >z           i




and

                   X                 1
      A′ (z) = −           θi2             .                                         (48)
                   i
                                 (µi + z)2


The function A(z) will be important in understanding ridge-regularization in the high-
complexity case. It turns out that the risk of the efficient portfolio can be expressed in
terms of the derivative of A(z) : Defining

                                                           2
             ′
                   X
                                          2          µi
      (zA(z)) =            (SR(P Ci ))                           ,                   (49)
                       i
                                                   µi + z

a somewhat tedious calculation implies that

                                             (zA(z))′
      V(z) = Var[Rinf eas (z)] =                       .                             (50)
                                           (1 + A(z))2




                                                             77
and


E[(Rinf eas (z))2 ]
        1                                           1
 =           2
               E[(E[F ]′ (zI + Ψ)−1 Ft )2 ] =              E[E[F ]′ (zI + Ψ)−1 Ft Ft′ (zI + Ψ)−1 E[F ]]
   (1 + A(z))                                  (1 + A(z))2
       1
=             E[E[F ]′ (zI + Ψ)−1 Ft Ft′ (zI + Ψ)−1 E[F ]]
  (1 + A(z))2
= E[F ]′ (zI + Ψ)−1 Ψ(zI + Ψ)−1 E[F ] + E(z)2
                                               2
        1      X
                    2         −2         A(z)
=                  θ (z + µi ) µi +
  (1 + A(z))2 i i                      1 + A(z)
  A(z) + zA′ (z) + A2 (z)
=
       (1 + A(z))2
  (A(z) + zA′ (z))(1 + A(z)) − zA(z)A′ (z)
=
                 (1 + A(z))2
                
   d     zA(z)
=                   .
   dz 1 + A(z)
                                                                                            (51)


Since the weights µiµ+z
                     i
                        are monotone increasing in µi , we see that all that the ridge shrinkage
does it re-weights principal components, giving a larger weight to higher-variance PCs. The
following is a simple but important observation, implying that ridge shrinkage is always
detrimental to performance.

Lemma 1 The Sharpe ratio SRinf easible (z) = SR(Rinf easible (z)) is monotone decreasing in
z.


D     Auxilliary Results

D.1     Concentration of Quadratic Forms

Roadmap: A key technical result in many RMT proofs is the concentration of quadratic
forms. Heuristically, it can be stated as follows: When Xi,t are i.i.d. with mean zero and


                                              78
unit variance, then E[Xt Xt′ ] = I and, hence,


  P −1 Xt′ CXt = P −1 tr(CXt Xt′ )                   ≈
                                                    |{z}               P −1 tr(CE[Xt Xt′ ]) = P −1 tr(C)
                                        law of large numbers as P →∞
                                                                                                         (52)


for any bounded matrix C. The next Lemma formalizes this intuition and characterizes the
speed of convergence of Xt′ CXt to tr(C). This lemma is a key element to many of our
proofs below.

Lemma 2 (Lemma 2.7 in (Bai and Silverstein, 1998)) Suppose that Xi,t are i.i.d.
with mean zero and unit variance. Let C a P × P matrix. Then, for any p ≥ 2, there
exists a constant Kp > 0 such that


                               p
      E[|Xt′ CXt − tr(C)| ] ≤ Kp ((E[|X1,1 |4 ] tr(CC ′ ))p/2 + E[|X1,1 |2p ] tr((CC ′ )p/2 )).          (53)


In particular,


                           p
    E[|Xt′ CXt − tr(C)| ] ≤ Kp (P p/2 (E[|X1,1 |4 ]∥C∥2 )p/2 + E[|X1,1 |2p ]P ∥C∥p ) ≤ K̃∥C∥p P p/2 .

                                                                                                         (54)


    Interestingly enough, this concentration result can be established under weaker conditions
than independence. We will need the following definition.

Definition 1 (Strongly uncorrelated variables) We say that fi , i = 1, · · · , K are
strongly uncorrelated if E[fi1 ] = E[fi1 fi2 ] = 0 for all i1 ̸= i2 , E[fi1 fi2 fi3 ] = 0 for any i1 , i2 , i3
and E[fi1 fi2 fi3 fi4 ] = 0 unless the set {i1 , i2 , i3 , i4 } contains exactly two different elements.
Furthemore, E[fi2 fj2 ] = E[fi2 ]E[fj2 ] for i ̸= j.

    The following is true.

                                                       79
Lemma 3 [Weak Concentration of Quadratic forms] Suppose that X = (Xi )Pi=1 with Xi
being strongly uncorrelated according to Definition 1. Suppose also that E[Xi2 ] = 1, E[Xi4 ] ≤
k, and let AP be random matrices independent of X and such that ∥AP ∥2 = o(1). Let also


       Yt = Xt′ AP Xt .                                                                   (55)


Then,


       (1) Yt = tr(AP Xt Xt′ )                                                            (56)

       (2) lim E[(Yt − tr(AP ))2 |AP ] = 0                                                (57)
           P →∞



In particular, If AP = BP /P where ∥BP ∥ ≤ K, we have ∥AP ∥22 ≤ P ∥BP ∥2 /P 2 and hence


        lim E[(Xt′ BP Xt − tr(BP ))2 |BP ]/P 2 = 0 .                                      (58)
       P →∞



Proof of Lemma 3.
(1):


       Xt′ AXt ∈ R ⇒ Xt′ AXt = tr(Xt′ AXt )

        tr(AB) = tr(BA) ⇒ tr(Xt′ AXt ) = tr(AXt Xt′ )




(2): Define Yt = Xt′ AP Xt . We have


       E[Yt ] = E[tr(AP (Xt Xt′ ))|AP ] = tr(AP E[Xt Xt′ ]) = tr(AP ) ,




                                                 80
and hence


      E[(Yt − tr(AP ))2 |AP ] = Var[Yt |AP ] = E[Yt2 |AP ] − E[Yt |AP ]2                          (59)


and hence it suffices to prove that


      E[Yt2 |AP ] − (tr(AP ))2 → 0                                                                (60)


For simplicity, we assume from now on that AP is deterministic, and write AP = (Ai,j )Pi,j=1 .
We also assume that A is symmetric. Then,

              X
      Yt =          Xi Xj Ai,j                                                                    (61)
              i,j


and therefore

                    X
      Yt2 =                    Xi1 Xj1 Ai1 ,j1 Ai2 ,j2 Xi2 Xj2                                    (62)
              i1 ,j1 ,i2 ,j2



Now, among all fourth-order moments, E[Xi1 Xj1 Xi2 Xj2 ], the only non-zero moments are
those where either all are identical, i1 = i2 = i3 = i4 , or when there are exactly two identical
pairs. The latter can happen in exactly 3 ways. First, (i1 = i2 , j1 = j2 ), (i1 = j2 , j1 = i2 )
give rise to the terms A2i1 ,j1 because, by assumption, A is symmetric, so that Ai1 ,j1 = Aj1 ,i1 .
Second, (i1 = j1 , i2 = j2 ) gives rise to Ai,i Aj,j . Note also that E[Xi2 Xj2 ] = E[Xi2 ]E[Xj2 ] = 1.




                                                                 81
Thus,

                            X
        E[Yt2 ] =                         Ai1 ,j1 Ai2 ,j2 E[Xi1 Xj1 Xi2 Xj2 ]
                         i1 ,j1 ,i2 ,j2
             X                              X
        =            A2i,i E[Xi4 ] +                  (2A2i,j + Ai,i Aj,j )
             i                             i,j,i̸=j
             X                               X                         X                X
        =            A2i,i E[Xi4 ] +                   2A2i,j −                A2i,i + (  Ai,i )2                           (63)
                 i                          i,j,i̸=j                   i                   i
             X                                X                  X                   X              X
        =            A2i,i E[Xi4 ] − 2                 A2i,i +         2A2i,j −            A2i,i + (  Ai,i )2
                 i                               i               i,j                   i             i
             X
        =            A2i,i (E[Xi4 ] − 3) + 2∥A∥22 + (tr(A))2
                 i


Thus, since E[Yt ] = tr(A), we have

                                                                       X
   E[Yt2 ] − tr(A)2 = E[Yt2 ] − E[Yt ]2 =                                      A2i,i (E[Xi4 ] − 3) + 2∥A∥22 ≤ (k − 1)∥A∥22 . (64)
                                                                           i


because

        X                  X
             A2i,i ≤               A2i,j = ∥A∥22 ,                                                                          (65)
         i                   i,j


The proof is complete.                                                                                                         □


D.2     Convergence of Expectations

Roadmap: In many of the proofs below, we would like to use the following intuitive
argument: If YP − E[YP ] → 0, then


        E[ZP YP ] ≈ E[ZP E[YP ]] = E[ZP ]E[YP ].


The next two lemmas make this intuition rigorous.



                                                                               82
Lemma 4 Suppose that Y = YP is such that YP − E[YP ] → 0 in L2 , and YP ≥ 0. Then,


     E[X/(1 + Y )] − E[X]/(1 + E[Y ]) → 0                                                         (66)


if E[|X|2 ] is uniformly bounded.


Proof of Lemma 4. We have

                                                          X(Y − E[Y ])
     |E[X/(1 + Y )] − E[X]/(1 + E[Y ])| = |E[                              ]|
                                                       (1 + Y )(1 + E[Y ])
               |X||(Y − E[Y ])|                                                                   (67)
      ≤ E[                        ] ≤ E[|X||Y − E[Y ]|]
              (1 + Y )(1 + E[Y ])
       ≤ E[X 2 ]1/2 Var[Y ]1/2 .

                                                                                                    □


Lemma 5 Suppose that Y (j) ≥ 0, j = 1, · · · , J, are such that Var[Y (j)] ≤ KP −1 and
E[Yj ] are bounded. Then,

                      X                             E[X]
     |E[                             ] −                                 | ≤ K(J)P −1/2 E[X 2 ]1/2 (68)
           (1 + Y1 ) · · · (1 + YJ )     (1 + E[Y1 ]) · · · (1 + E[YJ ])

for some K(J) > 0.


Proof of Lemma 5. Let Y be such that


     1 + YJ = (1 + Y1 ) · · · (1 + YJ ) .                                                         (69)


Let also


     1 + ZJ = (1 + E[Y1 ]) · · · (1 + E[YJ ]) .                                                   (70)




                                                  83
Then,


                 X                  E[X]             Y −Z
|E[                             ] −      | = |E[                 X]| ≤ E[(Y − Z)2 /(1 + Y )2 ]1/2 E[X 2 ]1/2 .
      (1 + Y1 ) · · · (1 + YJ )     1+Z          (1 + Y )(1 + Z)
                                                                                               (71)


We now prove by induction in J that E[(Y − ZJ )2 /(1 + YJ )2 ] ≤ κ(J)P −1 . We have


 (1+Y1 ) · · · (1+YJ ) = (1+E[Y1 ])(1+Y2 ) · · · (1+YJ ) + (Y1 −E[Y1 ])(1+Y2 ) · · · (1+YJ ) . (72)


Thus, defining ZJ = (1 + E[Y1 ]) · · · (1 + E[YJ ]) − 1, ZJ−1 = (1 + E[Y2 ]) · · · (1 + E[YJ ]) − 1,
we get


        YJ − ZJ = (1 + E[Y1 ])(YJ−1 − ZJ−1 ) + (Y1 − E[Y1 ])YJ−1 .                             (73)


Hence, since 1 ≤ YJ−1 ≤ YJ , we get


      E[(YJ − ZJ )2 /(1 + Y )2 ] ≤ 2 E[(1 + E[Y1 ])2 (YJ−1 − ZJ−1 )2 /(1 + YJ )2 ]

      + E[(Y1 − E[Y1 ])2 YJ−1
                          2
                              /(1 + YJ )2 ]

       ≤ 2(1 + E[Y1 ])2 κ(J − 1)P −1 + E[(Y1 − E[Y1 ])2 ] ≤ (2(1 + E[Y1 ])2 κ(J − 1) + K)P −1
                                                                                               (74)


and thus we have proved the induction step.
                                                                                                  □


D.3      Computing Moments

Roadmap: In this section, we derive analytical expressions for high-order moments of many
quantities appearing in our calculations.



                                                  84
    We will need the following lemma, whose proof follows by direct calculation.

Lemma 6 Suppose that Xt ∈ RN ×P is a matrix with i.i.d. elements satisfying E[Xi,k Xj,l ] =
δ(i,k),(j,l) . Then,


       E[Xt′ ΣXt ] = tr(Σ) IP ×P .


Lemma 7 Let A be a symmetric matrix. Then, we have


       E[St′ St ASt′ St ] = ((tr Σ)2 + tr(Σ2 ))ΨAΨ + tr(Σ2 ) tr(ΨA)Ψ
                                                                                        (75)
                        1/2                    1/2    1/2      1/2
        + tr(Σ ◦ Σ) Ψ         (κ − 3) diag(Ψ         AΨ     )Ψ


where diag(Ψ1/2 AΨ1/2 ) is the diagonal matrix with diagonal coinciding with that of
diag(Ψ1/2 AΨ1/2 ), and Σ ◦ Σ is the elementwise product of Σ with itself.


Proof. Substituting St = Σ1/2 Xt Ψ1/2 , we get


       E[St′ St ASt′ St ] = E[St′ St ASt′ St ] = Ψ1/2 E[Xt′ ΣXt ÃXt′ ΣXt ]Ψ1/2 ,       (76)


where Ã = Ψ1/2 AΨ1/2 . Thus, it suffices to consider the case Ψ = I and just compute


       E[Xt′ ΣXt ÃXt′ ΣXt ] ,                                                          (77)


in which case the desired identity takes the form


       E[Xt′ ΣXt AXt′ ΣXt ] = ((tr Σ)2 + tr(Σ2 ))A + tr(Σ2 ) tr(A)I
                                                                                        (78)
        + tr(Σ ◦ Σ) (κ − 3) diag(A) .

Further, it suffices to prove the result for rank-one matrices because any symmetric matrix



                                                          85
A can be written as

              X
      A =            λi βi βi′
                i


Thus, suppose that A = ββ ′ . Then,


      E[X ′ ΣXββ ′ X ′ ΣX]j,k
               X                                                                                                   (79)
      = E[              Xi1 ,j Σi1 ,i2 Xi2 ,i3 βi3 βi4 Xi5 ,i4 Σi5 ,i6 Xi6 ,k ] .
              i1 ,i2 ,i3 ,i4 ,i5 ,i6


By assumption, all elements of X are i.i.d. and have mean zero. Thus, the only non-zero
terms come from two identical pairs or when all terms are identical. For two identical pairs,
they are determined by what coincides with (i1 , j). These are the posibilities: (i1 , j) = (i2 , i3 )
or (i1 , j) = (i5 , i4 ) or (i1 , j) = (i6 , k). The latter can only happen when j = k.


   • Suppose first that j ̸= k. Then,

                         X
             E[                            Xi1 ,j Σi1 ,i2 Xi2 ,i3 βi3 βi4 Xi5 ,i4 Σi5 ,i6 Xi6 ,k ]
                  i1 ,i2 ,i3 ,i4 ,i5 ,i6
                                       X
              = E[                                       Xi1 ,j Σi1 ,i2 Xi2 ,i3 βi3 βi4 Xi5 ,i4 Σi5 ,i6 Xi6 ,k ]
                          i1 =i2 ,j=i3 ,i5 =i6 ,i4 =k                                                              (80)
                                       X
              + E[                                       Xi1 ,j Σi1 ,i2 Xi2 ,i3 βi3 βi4 Xi5 ,i4 Σi5 ,i6 Xi6 ,k ]
                         i1 =i5 ,j=i4 ,i2 =i6 ,i3 =k

              = (tr(Σ)2 + tr(Σ2 ))βj βk = (tr(Σ)2 + tr(Σ2 ))Aj,k .




                                                                         86
• When j = k, we get

                   X
       E[                             Xi1 ,j Σi1 ,i2 Xi2 ,i3 βi3 βi4 Xi5 ,i4 Σi5 ,i6 Xi6 ,j ]
            i1 ,i2 ,i3 ,i4 ,i5 ,i6
                           X
       = E[                              Xi21 ,j Σi1 ,i2 Xi2 ,i3 βi3 βi4 Xi5 ,i4 Σi5 ,i1 ]
                    i1 ,i2 ,i3 ,i4 ,i5
                             X
       + E[                                       Xi1 ,j Σi1 ,i2 Xi2 ,i3 βi3 βi4 Xi5 ,i4 Σi5 ,i6 Xi6 ,j ]
                   i1 ,i2 ,i3 ,i4 ,i5 ,i6 ̸=i1
                     X
       = E[                      Xi21 ,j Σi1 ,i2 Xi22 ,i3 βi23 Σi2 ,i1 ]
                    i1 ,i2 ,i3
                             X
       + E[                                       Xi1 ,j Σi1 ,i2 Xi2 ,i3 βi3 βi4 Xi5 ,i4 Σi5 ,i6 Xi6 ,j ]
                   i1 ,i2 ,i3 ,i4 ,i5 ,i6 ̸=i1
                            X                                  X
       = tr(Σ2 )                       βi2 + (κ − 1)                     Σ2i,i βj2
                                 i                                  i
                             X
       + E[                                       Xi1 ,j Σi1 ,i2 Xi2 ,i3 βi3 βi4 Xi5 ,i4 Σi5 ,i6 Xi6 ,j ]
                   i1 ,i2 ,i3 ,i4 ,i5 ,i6 ̸=i1
                            X                                 X
       = tr(Σ2 )                       βi2 + (κ − 1)                    Σ2i,i βj2
                                 i                              i
                                      X                                                                             (81)
       + E[                                               Xi1 ,j Σi1 ,i2 Xi2 ,i3 βi3 βi4 Xi5 ,i4 Σi5 ,i6 Xi6 ,j ]
                   i1 =i2 ,i3 =j,i4 =j,i5 =i6 ̸=i1
                                      X
       + E[                                               Xi1 ,j Σi1 ,i2 Xi2 ,i3 βi3 βi4 Xi5 ,i4 Σi5 ,i6 Xi6 ,j ]
                   i1 =i5 ,i3 =j,i4 =j,i2 =i6 ̸=i1
                            X                                 X
       = tr(Σ2 )                       βi2 + (κ − 1)                    Σ2i,i βj2
                                 i                              i
                    X
       + βj2                Σi1 ,i1 (tr(Σ) − Σi1 ,i1 )
                      i1
                    XX
       + βj2                           Σ2i1 ,i2
                      i1 i2 ̸=i1
                            X                                 X
       = tr(Σ2 )                       βi2 + (κ − 3)                    Σ2i,i βj2 + βj2 (tr(Σ))2
                                 i                              i
             XX
       + βj2  ( Σ2i1 ,i2 − Σ2i1 ,i1 )
                      i1         i2
                            X                                 X
       = tr(Σ2 )                       βi2 + (κ − 3)                    Σ2i,i βj2 + βj2 ((tr(Σ))2 + tr(Σ2 ))
                                 i                              i



                                                                          87
      Since j = k, the latter can be rewritten as


            tr(Σ2 ) tr(A)δj,k + (κ − 3) tr(Σ ◦ Σ)Aj,k + ((tr(Σ))2 + tr(Σ2 ))Aj,k .   (82)


                                                                                       □

Lemma 8 We have


      E[εZ ′ ε] = E[Σε,t Z]


and


      E[ε′ Zε′ ] = E[Z ′ Σε,t ]


for any random vector Z independent of ε, Σε . Furthermore,


      E[ε′ Aε] = tr(AΣε,t )


for any matrix A. Furthermore, for any matrix B independent of ε, Σε , we have

                       X
      E[(ε′ Bε)2 ] =          2
                            B̃i,i (κε − 3) + 2 tr(B̃ 2 ) + (tr(B̃))2                 (83)
                        i


                 1/2               1/2
where B̃ = 0.5Σε,t (B + B ′ )Σε,t , and


                            1/2                                           1/2
      E[εt ε′t Bεt ε′t ] = Σε,t (2B̃ + diag((κε − 3) diag(B̃) + tr(B̃)))Σε,t .


Proof. We have

                            X                 X
      E[εZ ′ ε]i,j = E[εi         Zj εj ] =       E[Σε,i,j Zj ]
                             j                j


                                                     88
and the first claim follows. The second claim follows because


       E[ε′ Zε′ ] = E[εZ ′ ε]′ .


For the third claim, we have


       E[ε′ Aε] = tr E[ε′ Aε] = tr E[Aεε′ ] = E[tr(AΣε,t )] ,                            (84)


while (83) follows from (63). For the last claim, we make the observation that, for any matrix
B,


       ε′ Bε = 0.5ε′ (B + B ′ )ε.


Indentity (83) follows (63).
     For brevity, we omit the t subindex below. Next,


       E[εε′ Bεε′ ] = E[Σ1/2   ′ 1/2 1/2 ′ 1/2
                         ε ε̃ε̃ Σε BΣε ε̃ε̃ Σε ] .                                       (85)


Define


       B̂ = Σ1/2 1/2
             ε BΣε .                                                                     (86)


     For j ̸= k, we have


       E[ε̃ε̃′ B̃ ε̃ε̃′ ]j,k
                     X                                                                   (87)
       = E[ε̃j               ε̃i1 ε̃i2 B̂i1 ,i2 ε̃k ] = B̂j,k + B̂k,j ,
                    i1 ,i2




                                                                  89
while, for j = k, we have


        E[ε̃ε̃′ B̂ ε̃ε̃′ ]j,j
                      X
        = E[ε̃2j              ε̃i1 ε̃i2 B̂i1 ,i2 ]
                       i1 ,i2
                                                                                             (88)
                                  X
          = κε B̂j,j +                    B̂i,i = (κε − 1)B̂j,j + tr(B̂) .
                                   i̸=j


                                                                                                □


D.4      Moments of Managed Portfolios

Recall that


        Ft+1 = St′ Rt+1                                                                      (89)


Lemma 9 (Expected Factor Moments) Let Σ∗F,t = ΣF,t + νν ′ . Suppose a normalization
                                       4                                            3
tr(Σ) = 1 and let σ∗ = tr(ΣΣε ) and E[Xi,k ] = κ for all i, k. Suppose also that E[Xi,k ] = 0.
We have


        E[St′ Σε St ] = tr(ΣΣε )Ψ


and

               ′
      E[Ft+1 Ft+1 ] = ((tr Σ)2 + tr(Σ2 ))ΨE[Σ∗F,t ]Ψ
                                                                                                
      + tr(Σ ◦ Σ)Ψ1/2 (κ − 3) diag(Ψ1/2 E[Σ∗F,t ]Ψ1/2 )Ψ1/2 + Ψ tr(ΣΣε ) + tr(ΨE[Σ∗F,t ]) tr(Σ2 )
                                                                                             (90)




                                                                90
Thus,


                  ′
        ∥E[Ft+1 Ft+1 ] − (ΨE[Σ∗F,t ]Ψ + σ∗ Ψ)∥ → 0                                                                (91)


when P → ∞.


Proof of Lemma 9. We abuse the notation and use ΣF to denote E[Σ∗F,t ].
   Recall that, under the normalization tr(Σ) = 1, by Assumption 2, tr(Σ2 ) → 0 and
tr(Σ ◦ Σ) = i Σ2i,i ≤ i,j Σ2i,j = tr(Σ2 ) → 0. Let ΣF,ε,t = Et [Feε′ ].
           P         P


                 ′
        E[Ft+1 Ft+1 ] = E[St′ (St Fe + ε)(St Fe + ε)′ St ]
                                                                                                                  (92)
        =   E[St′ St ΣF,ε,t St ]   +   E[St′ Σ′F,ε,t St′ St ]   +    E[St′ St ΣF St′ St ]   +   E[St′ Σε St ] ,

                                                            3
Then, the cubic terms all vanish because, by assumption, E[Xi,j,t ] = 0, and


E[St′ Σε St ] = E[Ψ1/2 Xt′ Σ1/2 Σε Σ1/2 Xt Ψ1/2 ] = Ψ1/2 E[Xt′ Σ1/2 Σε Σ1/2 Xt ]Ψ1/2 = Ψ tr(ΣΣε ) = Ψσ∗ ,


while Lemma 7 implies that


        E[St′ (St Fe + ε)(St Fe + ε)′ St ]

        = ((tr Σ)2 + tr(Σ2 ))ΨΣF Ψ                                                                                (93)

        + tr(Σ ◦ Σ)Ψ1/2 (κ − 3) diag(Ψ1/2 ΣF Ψ1/2 )Ψ1/2 + Ψ + tr(ΨΣF ) tr(Σ2 )


The claim how follows because tr(Σ ◦ Σ) and tr(Σ2 ) converge to zero, and Ψ is uniformly
bounded when P → ∞ by assumption. The proof of Lemma 9 is complete.
                                                                                                                    □




                                                                91
E     Proof of Propositions 1 and 2: Characteristic-managed Portfo-

      lios and the Conditional SDF

Proof of Proposition 1. We have


                     ′
      πt = Et [Rt+1 Rt+1 ]−1 Et [Rt+1 ] .                                                  (94)


By assumption,


      Rt+1 = St F̃t+1 + εt+1                                                               (95)


and, hence,


      Et [Rt+1 ] = St Et [F̃t+1 ] = St ν                                                   (96)


whereas

                ′
      Et [Rt+1 Rt+1 ] = Et [(St F̃t+1 + εt+1 )(St F̃t+1 + εt+1 )′ ]
                         ′
       = St Et [F̃t+1 F̃t+1 ]St′ + St ΣF,ε,t + Σ′F,ε,t St′ + Σε,t                          (97)

       = St (ΣF,t + νν ′ )St′ + St ΣF,ε,t + Σ′F,ε,t St′ + Σε,t ,

and the claim follows. The proof is complete.                                                 □


    We will frequently be using the Sherman-Morrison formula


    (A + xx′ )−1 = A−1 − A−1 xx′ A−1 /(1 + x′ A−1 x), (A + xx′ )−1 x = A−1 x/(1 + x′ A−1 x) (98)


for any matrix A ∈ RP ×P and any vector x ∈ RP .




                                                      92
Lemma 10 Let A, B be two positive definite, symmetric matrices. Then,


      (A + B)−1 = B −1 − (A + B)−1 AB −1 ,                                              (99)


and


      (A + B)−1 AB −1 ≤ B −1 AB −1                                                     (100)


in the sense of positive semi-definite order. Furthermore, if A ≤ A1 , then


      (A + B)−1 AB −1 ≤ (A1 + B)−1 A1 B −1                                             (101)


Proof of Lemma 10. Let Â = B −1/2 AB −1/2 . Then, we have


      (A + B)−1 AB −1 = B −1/2 (Â + I)−1 ÂB −1/2 ≤ B −1/2 ÂB −1/2 = B −1 AB −1 .    (102)


The last claim follows from the matrix monotonicity of (Â + I)−1 Â in Â : Indeed,


      (Â + I)−1 Â ≤ (Â1 + I)−1 Â1                                                  (103)


implies


      B −1/2 (Â + I)−1 ÂB −1/2 ≤ B −1/2 (Â1 + I)−1 Â1 B −1/2                       (104)


which is equivalent to (101).                                                             □


Proof of Proposition 2. Let Σ∗F,t = ΣF,t + νν ′ . Let also


      b t = St ΣF,ε,t + Σ′ S ′ + St ΣF S ′
      Σ                                                                                (105)
                         F,ε,t t        t




                                                 93
Recall that, by Proposition 1,


                 b t + Σε,t )−1 St ν
      w̃(St ) = (Σ                                                                        (106)


is the conditionally efficient portfolio with the return


       ′              ′    b t + Σε,t )−1 St ν .
      Rt+1 w̃(St ) = Rt+1 (Σ                                                              (107)


For simplicity, in the sequel omit the t subindex for ΣF , Σ∗F , Σ,
                                                                 b Σε . Hence, defining


            b + Σε )−1 = Σ−1
      Qt = (Σ             ε
                                b + Σε )−1 ΣΣ
                             − (Σ          b −1 ,                                         (108)
                                             ε



and noting that, by the Sherman-Morrison formula,


       b + St νν ′ S ′ + Σε )−1 = Qt − Qt St νν ′ S ′ Qt (1 + ν ′ S ′ Qt St ν)−1 .
      (Σ                                                                                  (109)
                    t                              t               t



Then,

         ′
      E[Rt+1 w̃(St )]

        = E[ν ′ St′ (Σ
                     b + νν ′ + Σε )−1 St ν]

        = E[ν ′ St′ (St νν ′ St′ + Σ
                                   b + Σε )−1 St ν]
                                                                                          (110)
        = E[ν ′ St′ ((St ν)(St ν)′ + (Σ
                                      b + Σε ))−1 St ν]

         = E[ν ′ St′ (Qt − Qt St νν ′ St′ Qt (1 + ν ′ St′ Qt St ν)−1 )St ν]
        |{z}
        (109)

        = E[Zt − Zt2 (1 + Zt )−1 ] = E[Zt /(1 + Zt )] ,

where we have defined


      Zt = ν ′ St′ Qt St ν = ν ′ St′ Σ−1
                                      ε St ν − q ,                                        (111)

                                                       94
with


       q = ν ′ St′ Σ−1        ′ ′
                    ε St ν − ν St Qt St ν .                                        (112)


Now, for any δ > 0, we have


       Vart [δ −1 St Fet+1 − δεt+1 ] ≥ 0


and, hence,


       St Σf,ε + Σ′f,ε St′ ≤ δ −2 St ΣF St′ + δ 2 Σε                               (113)


so that


       b ≤ (1 + δ −2 )St ΣF S ′ + δ 2 Σε
       Σ                                                                           (114)
                             t



By Lemma 10,


        b + Σε )−1 ΣΣ
       (Σ          b −1 ≤ Σ−1 ((1 + δ −2 )St ΣF S ′ + δ 2 Σε )Σ−1                  (115)
                     ε     ε                     t             ε



and hence


       0 ≤ q ≤ ν ′ St′ Σ−1       −2       ′    2     −1
                        ε ((1 + δ )St ΣF St + δ Σε )Σε St ν .                      (116)


Our goal is to show that limN,P →∞ q = 0 in L1 . To this end, we show below that


       lim E[ν ′ St′ Σ−1       ′ −1
                      ε St ΣF St Σε St ν] = 0,                                     (117)




                                                       95
while


        E[ν ′ St′ Σ−1
                   ε St ν] ≤ K                                                           (118)


is uniformly bounded. As a result,


        lim sup q ≤ δ 2 K                                                                (119)


and the desired claim follows because δ > 0 is arbitrary.
   For simplicity, we will assume that Xi,k,t all have the same fourth moment κ (otherwise,
the identity needs to be replaced by an inequality). Then, we have that, by Lemma 7,


        E[ν ′ St′ Σ−1     ′ −1
                   ε St ASt Σε St ν] = ν
                                         ′
                                           ((tr Σ̂)2 + tr(Σ̂2 ))ΨAΨ + tr(Σ̂2 ) tr(ΨA)Ψ
                                                              !
        + tr(Σ̂2 ) (κ − 3)Ψ1/2 diag(Ψ1/2 AΨ1/2 )Ψ1/2 ν
                                                                                         (120)
                               tr(Σ̂2 )            tr(Σ̂2 )
        = (tr Σ̂)2 ν ′ (1 +               )ΨAΨ +              tr(ΨA)Ψ
                               (tr Σ̂)2            (tr Σ̂)2
                                                                  !
            tr(Σ̂ ◦ Σ̂)
        +                 (κ − 3)Ψ1/2 diag(Ψ1/2 AΨ1/2 )Ψ1/2 ν
             (tr Σ̂)2

with


        A = ΣF                                                                           (121)


and


        Σ̂ = Σ1/2 Σ−1
                   ε Σ
                      1/2
                          .                                                              (122)


Recall, that, by assumption, Σε,t = Σ̃ε,t + σε2 I. For simplicity, we assume the normalization


                                                       96
σε2 = 1. Then, Σ−1
                ε = I − Σ̃ε,t (I + Σ̃ε,t )
                                           −1
                                              and, hence


       tr(Σ̂) = tr(Σ1/2 Σ−1
                         ε Σ
                            1/2
                                ) = tr(Σ) − tr(Σ1/2 Σ̃ε,t (I + Σ̃ε,t )−1 Σ1/2 )           (123)


Now,


       Σ1/2 Σ̃ε,t (I + Σ̃ε,t )−1 Σ1/2 ≤ Σ1/2 Σ̃ε,t Σ1/2


and, hence,


       tr(Σ1/2 Σ̃ε,t (I + Σ̃ε,t )−1 Σ1/2 ) ≤ tr(Σ1/2 Σ̃ε,t Σ1/2 ) = tr(ΣΣ̃ε,t ) → 0

                                                                                      2
by assumption. Thus, we can assume that Σε = I and, by Assumption 2, tr(Σ̂ (tr
                                                                            )+tr(Σ̂◦Σ̂)
                                                                               Σ̂)2
                                                                                        →0
and, since ν and Ψ and A and tr(Σ̂) are uniformly bounded, we get that


       E[ν ′ St′ Σ−1     ′ −1                2 ′
                  ε St ASt Σε St ν] ≈ (tr Σ̂) ν ΨAΨν .
                                                                                          (124)


Since, by Assumption 1, tr(A) is uniformly bounded, we also get that tr(ΨAΨ) ≤ ∥Ψ∥2 tr(A)
is uniformly bounded and, hence,


       E[ν ′ ΨAΨν] = E[tr(ΨAΨνν ′ )] = P −1 tr(ΨAΨΣν ) → 0 .                              (125)


Thus, E[qt ] → 0 and hence qt → 0 in probability. Now,


       E[ν ′ St′ Σ−1               ′
                  ε St ν] = tr(Σ̂)ν Ψν
                                                                                          (126)




                                                     97
whereas, by Lemma 7,


      E[(ν ′ St′ Σ−1     2       ′ ′ −1      ′ ′ −1
                  ε St ν) ] = E[ν St Σε St νν St Σε St ν]


      = ν ′ ((tr Σ̂)2 + tr(Σ̂2 ))Ψνν ′ Ψ + tr(Σ̂2 ) tr(Ψνν ′ )Ψ
                                                                                        (127)
                                                            !
      + tr(Σ̂ ◦ Σ̂) (κ − 3)Ψ1/2 diag(Ψ1/2 νν ′ Ψ1/2 )Ψ1/2 ν


and the same argument as in (120) implies that


      E[(ν ′ St′ Σ−1     2          2 ′    2
                  ε St ν) ] ≈ tr(Σ̂) (ν Ψν) .                                           (128)


Thus, Var[ν ′ St′ Σ−1                       ′ ′ −1               ′
                   ε St ν] → 0 and, hence, ν St Σε St ν → tr(Σ̂)ν Ψν in probability.

   As a result, Zt − tr(Σ̂)ν ′ Ψν → 0 is probability, and hence

        Zt       tr(Σ̂)ν ′ Ψν
             −                  → 0                                                     (129)
      1 + Zt   1 + tr(Σ̂)ν ′ Ψν

in probability, and the dominated convergence theorem implies that the same holds in
expectation. Similarly, for the second moment, we have


      E[(πtM V )′ Rt+1 Rt+1
                        ′
                            πtM V ]

      = E[λ′ St′ (St (ΣF )St′ + Σε )−1 (St (ΣF )St′ + Σε )(St (ΣF )St′ + Σε )−1 St λ]   (130)
                                         ′
           ′                      tr(Σ̂)ν Ψν
      = E[Rt+1 πtM V ] →                           .
                                1 + tr(Σ̂)ν ′ Ψν




                                                       98
Now, for the factor portfolios, we have


      E[Ft ] = E[St′ Rt+1 ] = E[St′ (St Fet+1 + εt+1 )]

        = E[St′ St Fet+1 ] = E[Ψ1/2 Xt′ ΣXt Ψ1/2 Fet+1 ]

        = E[Ψ1/2 Xt′ ΣXt Ψ1/2 ]ν                                                                  (131)

        = tr(Σ) E[Ψ1/2 Ψ1/2 ]ν

        = tr(Σ) Ψν ,


and, again by Lemma 7 and the same argument as in (120), we have


     E[Ft Ft′ ] = E[St′ (St Fet+1 + εt+1 )(St Fet+1 + εt+1 )′ St ] = E[St′ (Σ
                                                                            b + νν ′ + Σε )St ]
                                                                                                  (132)
     ≈ tr(ΣΣε )Ψ +        tr(Σ) Ψνν Ψ + E[St′ ΣS
                                2     ′       b t] .

                                                                           3
(Note that we cannot apply Lemma 9 directly because we are not assuming E[Xj,k,t ]=0
here. In particular, our Σ
                         b contains ΣF,ε .) Our goal is to show that the contribution of

A = E[St′ ΣS
          b t ] is negligible. Then, defining


      Q = (tr(ΣΣε )Ψ + A)−1 ,                                                                     (133)


we get that the efficient portfolio of factors is given by


      πF = (tr(ΣΣε )Ψ + tr(Σ)2 Ψνν ′ Ψ + A)−1 Ψν

        = (tr(ΣΣε )Ψ + tr(Σ)2 Ψνν ′ Ψ + A)−1 Ψν                                                   (134)
               1
         =
        |{z} 1 + Z QΨν ,
        (98)


where


      Z = tr(Σ)2 ν ′ ΨQΨν .                                                                       (135)


                                                   99
By the same argument as above,


        ν ′ (ΨQΨ − Ψ(tr(ΣΣε )Ψ)−1 Ψ)ν → 0                                                  (136)


because ΣF has a bounded trace and we can bound A by a combination of (1 + δ 2 )ΣF + δ 2 Σε
with an arbitrarily small δ. Thus,

                tr(Σ)2 ′
        Z ≈             ν Ψν                                                               (137)
               tr(ΣΣε )

and

                                1           Z
        E[πF′ Ft+1 ] = E[ν ′       ΨQΨν] ≈     ,                                           (138)
                               1+Z         1+Z

while


        E[πF′ Ft+1 Ft+1
                     ′
                        πF ] = E[πF′ Ft+1 ] ,                                              (139)


and the proof is complete because

                              tr(Σ)2 ′
        tr(ΣΣ−1  ′
             ε )ν Ψν =                ν Ψν                                                 (140)
                             tr(ΣΣε )

when Σε = I.
   Finally, the fact that E[(πF′ Ft+1 −Rt+1
                                        ′
                                            w̃(St ))2 ] → 0 follows because, otherwise, one could
construct a better-diversified portfolio by combining the two, which is impossible. Namely,
we know that


           ′                   ′                    ′              ′
        E[Rt+1 w̃(St ) − 0.5((Rt+1 w̃(St ))2 ] ≥ E[Rt+1 bt − 0.5((Rt+1 b2t ]               (141)


for any portfolio policy bt because w̃(St ) is optimal for the agent with quadratic utility. Let

                                                  100
bt = w̃(St ) + εSt πF . Then,


               ′              ′
        max E[Rt+1 bt − 0.5((Rt+1 bt ) 2 ]                                                        (142)
            ε



is achieved with

            E[πF′ Ft+1 ] − E[πF′ Ft+1 Rt+1
                                         ′
                                           w̃(St )]
        ε =                                         .                                             (143)
                      