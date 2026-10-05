source: https://arxiv.org/pdf/2505.02678
fetched_utc: 2026-10-04T18:36:22Z
bytes_raw: 1574256

A Nested Factor Model for Equity Markets: Reconciling
                                             Multifractal Stock Returns and Rough Index Volatilities
                                                Othmane Zarhali1 , Cecilia Aubrun2,3 , Emmanuel Bacry1 , Jean-Philippe Bouchaud2,4,5 , and
                                                                                 Jean-François Muzy6
arXiv:2505.02678v4 [q-fin.ST] 25 Jun 2026




                                            1
                                              Ceremade, CNRS-UMR 7534, Université Paris-Dauphine PSL, Place du Maréchal de Lattre
                                                                            de Tassigny, 75016 Paris, France
                                             2
                                               Chair of Econophysics and Complex Systems, École polytechnique, 91128 Palaiseau Cedex,
                                                                                         France
                                                  3
                                                    LadHyX UMR CNRS 7646, École polytechnique, 91128 Palaiseau Cedex, France
                                                        4
                                                          Capital Fund Management, 23 Rue de l’Université, 75007 Paris, France
                                                             5
                                                               Académie des Sciences, 23 Quai de Conti, 75006 Paris, France
                                                       6
                                                         SPE CNRS-UMR 6134, Université de Corse BP 52, 20250 Corte, France



                                                                                               Abstract
                                                       The Nested factor model was introduced by Chicheportiche et al. in [27] to represent non-linear
                                                   correlations between stocks. Stock returns are explained by a standard factor model, but the (log)-
                                                   volatilities of factors and residuals are themselves decomposed into factor modes, with a common
                                                   dominant volatility mode affecting both market and sector factors but also residuals. Here, we
                                                   consider the case of a single factor where the only dominant log-volatility mode is rough, with a
                                                   Hurst exponent H ≃ 0.11 and the log-volatility residuals are “super-rough” or “multifractal”, with
                                                   H ≃ 0. We demonstrate that such a construction naturally accounts for the somewhat surprising
                                                   stylized fact reported by Wu et al. in [26], where it has been observed that the Hurst exponents of
                                                   stock indexes are large compared to those of individual stocks. We propose a statistical procedure
                                                   to estimate the Hurst factor exponent from the stock returns dynamics together with theoretical
                                                   guarantees of its consistency. We demonstrate the effectiveness of our approach through numerical
                                                   experiments and apply it to daily stock data from the S&P500 index. The estimated roughness
                                                   exponents for both the factor and idiosyncratic components validate the assumptions underlying
                                                   our model.

                                            Keywords: Nested factor model, Log S-fBM model, Hurst exponent, small intermittency approxima-
                                            tion


                                            1     Introduction
                                            Volatility modelling has greatly evolved since the Bachelier model in 1900 [35], where prices follow
                                            a Brownian motion with constant volatility. It has long been recognized that such a model fails to
                                            capture the salient features that justify the very existence of option markets. Indeed, volatility being
                                            fluctuating and uncertain, volatility bets become relevant. Furthermore, price jumps and fat tails


                                                                                                   1
prevent perfect hedging strategies, so that option markets are non-redundant and allow real risk to be
exchanged between participants.
    In addition, volatility fluctuations have special statistical properties, as volatility clustering. As
noted long ago by Mandelbrot [3], large price changes of either sign tend to be followed by large price
changes, and small price changes tend to be followed by small price changes. Interestingly, one observes
periods of high (/low) volatilities at all frequencies, from minutes to years. Such a remarkable “long-
memory” phenomenon calls for models with specific mathematical properties.
    One family of such models that has become extremely popular in the last 25 years assumes that
the log-volatility process is a fractional (Gaussian) Brownian motion B H , characterized by a Hurst
exponent H ∈ (0, 1) that describes the “roughness” of its trajectory through

                                      E (BtH − BsH )2 = (t − s)2H .                                     (1)
                                                       


The case H = 12 corresponds to the classic Brownian motion. Models with H < 12 corresponds to
“rough” log-volatility dynamics, whereas H > 12 corresponds to log-volatilities smoother than Brownian
motion. For instance, pioneering work by Comte and Renaud in 1998 [31] proposed a smooth volatility
process with H > 21 to account for the long-range memory of volatility. At the other extreme, two of
us (E.B. and J.-F. M.) introduced in 2000 the Multifractal Random Walk (MRW) model [23, 24, 29],
which formally corresponds to H −    → 0+ . Later, this multifractal regime was also observed in real data
[13, 15, 25, 29, 30], as clarified recently in [26] (more on this later, and see also [4]).
    Rough volatility modelling has gathered considerable momentum since 2016, after the seminal paper
of Gatheral et al. [25], followed by a flurry of papers in which new mathematical tools are developed to
price options within such a framework [6, 10, 11, 12, 25]. At variance with the “multifractal” H →  − 0+
MRW model, Gatheral et al. found that the roughness index H of the log-volatility of major stock
indexes (such as the S&P500 and the DAX) is around 0.14 (see also [9]).
    On the other hand, factor models in asset pricing have been central to the empirical investigation of
risk premia and portfolio returns. The canonical framework, the Capital Asset Pricing Model (CAPM)
of [36] and [37], posits a single market factor as the driver of expected returns. However, empirical
evidence soon revealed systematic deviations from CAPM predictions, motivating the development of
multifactor models such as the Fama-French three-factor model (see [38]). Beyond these linear speci-
fications, modern approaches exploit large panels of test assets and apply statistical methods such as
principal component analysis and sparse estimation to extract latent risk factors [41, 42]. More recent
advances integrate economic theory with machine learning techniques to improve factor selection and
to address the proliferation of proposed anomalies (see for instance [43]).

    Seeking to build a unifying framework that conciliates the observed (small) Hurst exponent of order
H ∼ 0.1 with the asymptotic behavior where H −       → 0+ , P. Wu, E. Bacry and J.-F Muzy introduced in
2022 the logarithmic Stationary fractional Brownian Motion (Log S-fBM) [26] (see also [18, 20, 21] for
alternative approaches). Calibrating their model on real world data led to intriguing results. While the
roughness index of stock indexes is compatible with the values reported by Gatheral et al. (H ≈ 0.1),
individual stocks exhibit significantly greater roughness (H ≈ 0) as illustrated in Figure 1 (see also
Figure 10 of [26]).
    Such a result is puzzling and at first sight paradoxical, since a stock index is nothing but the average
of individual stocks – how can the volatility of the latter be smoother than that of all its constituents?
This observation is the motivation for the present paper, where we revisit the “Nested Factor Model”
(NFM) of R. Chicheportiche and one of us (J.-P.B) [27] and show that such a framework indeed allows
us to reconcile all empirical findings.
    In a nutshell, our basic intuition is that the roughness exhibited of a composite signal, composed of
several signals with varying degrees of roughness, tends to be dominated by the roughest component.


                                                     2
                                                                             indices
                Count   10   2                                               stocks




                        101




                        100
                                 0.00   0.05        0.10       0.15                0.20
                                            Hurst exponent (H)

 Figure 1: Hurst exponents estimation of 503 stocks and 49 indexes using the calibration method of
      Wu et al. [26] on daily Garman-Klass estimation of the log-volatility from 2013 to 2023.


Consequently, the empirical observations of Figure 1, suggests that the “multifractal” volatility contri-
butions to individual stocks should nearly disappear when averaging over single stocks and only leave
the common, smoother volatility contribution to emerge at the index level. The rougher component,
characterized by H ≈ 0, is thus expected to be associated with the idiosyncratic dynamics of individual
stocks.
    Factor models offer a natural framework for investigating such a hypothesis. Indeed, thinking of
stock returns as the sum of a factor component (common to all stocks) and an idiosyncratic component
(specific to each stock), it is clear that if the idiosyncratic component is rougher than the factor
component, it will dominate at the stock level and disappear at the index level. However, things
turn out to be a little more complex since it has been shown in several previous studies that the
volatility of the idiosyncratic component is strongly correlated with the volatility of the index, see
[1, 7, 28]. This is precisely the motivation for the Nested factor model (NFM) proposed in [27], which
accurately captures the anomalous copula structure between pairs of stocks, that reflects the existence
of a common volatility mode in their idiosyncratic component.
    The outline of the article is as follows. Section 2 presents the models we are interested in, i.e.
the Log S-fBM and the Nested Factor model. Section 2.3 introduces our framework which couples
the NFM with SfBM as log-volatility modes, and that we thereafter call the Nested Log S-fBM factor
model (N-SfFM). The rest of the paper aims at verifying that the N-SfFM replicates the empirical
findings of Wu et al. exposed in Fig. 1. We intend to do so analytically, numerically and on real data.
Specifically, Section 4 determines the limits of the different regimes by specifying conditions on the
model parameters. Finally, Section 6 presents our numerical experiments, while Section 7 summarizes
our empirical results.




                                                   3
2       Theoretical Backdrop
2.1     The log Stationary fractional Brownian Motion
In this Section, we outline the main characteristics of the Log S-fBM model introduced in [26] as a
consistent interpolation between rough models with 0 < H < 12 and the “multifractal” MRW, that
corresponds to H →− 0+ . For more comprehensive details, we refer the reader to [26].
    For any Hurst exponent 0 < H < 12 , the Stationary fractional Brownian Motion (S-fBM) (ωH,T (t))t
is a stationary Gaussian process1 defined by its covariance function:
                                                         ( 2
                                                          ν
                                                             1 − ( Tτ )2H , when |τ | < T
                                                                         
             CωH,T (τ ) = cov(ωH,T (t), ωH,T (t + τ )) =   2                                      (2)
                                                          0 otherwise

where ν is a dimensionless parameter that controls the amplitude of the process, and T is the time
range of correlations. The mean value of ωH,T is chosen such a way that:
                                                   
                                         E eωH,T (t) = 1 .                                      (3)

The Log S-fBM random measure (MH,T (t))t is then defined as:

                                            dMH,T (t) = exp(ωH,T (t))dt.                                                (4)

Wu et al. primarily demonstrate that as H goes to 0 and ν tends toward infinity while keeping fixed
the so-called dimensionless intermittency coefficient:

                                                  λ2 = H(1 − 2H)ν 2 ,                                                   (5)

the Log S-fBM (MH,T (t))t converges toward a Multifractal Random Measure (MRM) (that will be
consequently noted M0,T ) previously introduced in [23, 24, 29, 30]. Even though a vanishing Hurst
exponent leads to an ill defined S-fBM process because of the exploding variance (see Eq. (2) and
Eq. (5), the limit (in the weak sense) when the Hurst vanishes is in the level of the Log S-fBM random
measure (Eq. (4)) that converges toward M0,T .
   The MRM is classically defined as the limit measure:

                                           dM0,T (t) = lim exp(ω̃l,T (t))dt                                             (6)
                                                         l→0+

where ω̃l,T is a stationary Gaussian process, whose mean is chosen such that E(eω̃l,T (t) ) = 1, and whose
covariance is given by:

                                                          −λ (ln(l/T ) − 1 + τ /l), when |τ | < l
                                                            2
                                                         
           Cω̃l,T (τ ) = cov(ω̃l,T (t), ω̃l,T (t + τ )) = −λ2 ln(τ /T ), when l < |τ | < T         .   (7)
                                                           0 otherwise
                                                         
                                                         

    Hence, this framework harmonizes the cases H > 0 and H →   − 0.
    Wu et al. complete their model by proposing financial price dynamics to be described with the Log
S-fBM, such that return of an asset dxt writes:2
                                             r
                                                 dMH,T (t)
                                       dxt =               dBt
                                                    dt
    1
     Notice that all the framework introduced in this work can be naturally extended to a wide class of infinitely divisible
laws along the same line as discussed in [22, 23, 26].
   2
     Let us note that this equation can be problematic when H → 0. In that case, the process is defined through a
subordination of the Brownian motion B.


                                                             4
    where (MH,T (t))t≥0 is a Log S-fBM measure and (Bt )t is a standard Brownian motion.
    Within this framework, Wu et al. introduced two Generalized Methods of Moments to calibrate
the Log S-fBM on empirical data. These methods rely on estimating the autocovariance of dMH,T or
ln (dMH,T ), for a fixed set of lags (see [26], Proposition 6). By applying their calibration method to
daily volatility Garman-Klass estimates, results displayed in Figure 1 were obtained (see also Figure 10
in [26]). Notably, the discrepancy in the order of magnitude between the Hurst exponents of indexes
(in black) and individual stocks (in blue) is striking. Indeed, as noted in the introduction above, stock
log-volatilities are rougher (H ≈ 0) than that of indexes (H ≈ 0.1). Empirical observations suggest
that the correlation scale T is quite large (see as a support the experiments of Figures 8 and 9 in [2]).
As highlighted in [26], when the total sample size L is smaller than T , the statistical properties of the
Log S-fBM are indistinguishable from those observed when T = L. Therefore, in what follows, we
assume that T corresponds to the full sample size, typically spanning a few years.

2.2     The Nested Factor Model
Introduced in [27], the Nested Factor model (NFM) seeks to replicate the dynamics of stocks returns and
their interplay with market dynamics. The development of this model stemmed from the observation
that joint distribution of stock returns is not elliptical [28].
    In this context, we define the Nested Factor Model with a single factor (M = 1) and a single
volatility mode. The extension to M factors is outlined in Appendix A. This model is applied to the
returns, dxit of stock i at time t as follows:
                                                       Ω
                                              dft = e 2t dWt0 ,
                 dxt = βi dft + dϵt with
                   i              i
                                                           ω̃ti
                                                                   and ω̃ i := γi Ω + ω i .          (8)
                                              i
                                               dϵt = σi e 2 dBti ,
where

   • The time series ft represents the market itself, and (dft )t can be accurately proxied by the returns
     of the S&P500 index.
   • Parameters βi s represent the exposure of stock i to the market factor df ;
   • The time series (dϵit )i represent the residuals of each stock returns, i.e. the portion of the stock
     returns not accounted for by market movements. These residuals are uncorrelated with the
     market;
   • Ωt is the log-volatility stochastic factor involved in the dynamics of both the market factor (ft )t>0
     and the residuals (ϵit )i . We will choose to shift Ωt such that the volatility of the market is equal
     to unity, i.e, E[exp(Ωt )] = 1,.
   • ωti is the stochastic idiosyncratic log-volatility of residual returns dϵi . Without loss of generality,
     we consider the mean of ωti such that the volatility of the residual is directly σi , i.e, E[exp(γi Ωt +
     ωti )] = 1.
   • Parameters γi s represent the exposure of the log-volatility of stock i to the log-volatility of the
     index. The γs are thus equivalent, in volatility space, to the usual factor model βs for returns.
   • Finally, Wt0 and Bti are standard Brownian motions, all independent with one another.

   Drawing from this approach, we build in the next Section a Nested Log S-fBM one-factor model in
which the market volatility and the idioyncratic volatilities are all Log S-fBM.




                                                     5
2.3    Definition of the N-SfFM: A Nested Factor Model with S-fBM log-volatilities
We introduce the Nested factor model incorporating S-fBM processes as log-volatilities. For the sake
of tractability and parcimony, we limit ourselves to the one-factor case, M = 1, but our framework can
be readily generalized to M > 1 (see Appendix A). The idea is simply to complement the definition of
the 1-factor NFM, Eq. (8) above, with the following extra specifications:

    • Ωt is a S-fBM process of intermittency λ2 , Hurst exponent H ∈ (0, 1/2) and decorrelation pa-
      rameter T > 0;

    • For any i ∈ J1, N K, ωti is a S-fBM process of intermittency λ2i , Hurst exponent Hi ∈ (0, 1/2) and
      the same decorrelation parameter T .

We further assume that the market volatility mode Ωt and the idiosyncratic modes ωti i∈J1,N K are
                                                                                                

all mutually independent. Furthermore, we suppose that the volatility modes are independent from
the driving Brownian motions enabling no leverage effect which will be the object of future works.
The Nested Log S-fBM factor model (N-SfFM) is thus defined similarly to the original version of
Chicheportiche et al. in [27]; the specificity of the present version is that we consider a S-fBM dynamic
for the log-volatility modes in order to encode the roughness of their sample paths. Note that the
correlation of the factor volatility mode and the residual log-volatility ω̃ i is parameterized by the
multiplicative terms (γi )i∈J1,N K as we have:

                                                     Cov Ωt , ω̃ti = γi Var (Ωt ) ,                           (9)
                                                                  
                          ∀i ∈ J1, N K,    ∀t ≥ 0,

    As evoked in Section 2.1, we will leverage the small intermittency approximation, introduced in
[26] initially used in the Log S-fBM calibration procedure, in the context of the log N-SfFM. Using
the small intermittency approximation tool, we will show that under mild conditions on the exposure
vectors (βi )i∈J1,N K and (γi )i∈J1,N K , observing the log-volatility of single stocks is equivalent to observing
the log-volatility of the residuals, and observing the log-volatility of the index is equivalent to observing
the log-volatility of the market factor. In other words, the residuals reflect the roughness of the single
stock and the factor the roughness of the index.


3     The small intermittency approximations
The small intermittency approximation is a tool initiated by Bacry et al. in [32] in order to study the
scaling properties of the multifractal random walk model (see [24] and [29]) and also used by Wu et al.
in [26]. It consists in deriving an approximation of the generalized moments of the multifractal random
measures in terms of the generalized moments of integrated processes of the type of Eq. (52) when the
dimensionless intermittency parameter λ2 , defined in Eq. (5), goes to 0. Given that empirical values
of λ2 estimated from market data (see e.g. [26]) are around λ2 ≃ 0.05, this approximation is shown to
be accurate (more details are provided in Appendix C.1). The small intermittency approximation is
relevant because none of the underlying S-fBM processes in Eq. (8) are directly observable, as was also
the case in [26]. Indeed, Wu et al. derived a small intermittency approximation of the autocovariance
function of the log-multifractal random measure as well as the log-quadratic variation of a Log S-fBM
process – see Proposition 5 in [26].
Here, we leverage the small intermittency approximation to derive a closed-form expression of the vari-
ance of the log volatility increments of a sum of multiple Log S-fBM processes, from which a similar
result is derived in the case of our model in Eq. (8) and that will be used extensively in the following
Section.



                                                        6
For this sake, we consider d Log S-fBM models:
                                                                   ωi
                                                          (
                                                           dY i = e 2t dB i
                                            ∀ i ∈ J1, dK,    t           t ,                     (10)
                                                           Y0i = y0i

where ωti , i ∈ J1, dK are   d independent S-fBM processes, each of which with respective parameters
                        

λi , Hi , T , B , i ∈ J1, dK is a d-dimensional Brownian motion (of independent entries) independent
                i

from (ωti , i ∈ J1, dK) and y0i , i = 1, . . . , d are constant values.
     In what follows, the intermittency vector will be denoted as Λ :
                                                               λ1
                                                             
                                                             λ2 
                                                        Λ= .                                   (11)
                                                             
                                                             .. 
                                                               λd
    We introduce the weighted averaged S-fBM process ωt and the weighted averaged process (Yt )t as
follows:
                                      (
                                        ω(t) = di=1 ai ωti
                                               P
                                                           ,                                  (12)
                                        Yt := di=1 bi Yti
                                              P

where (ai )i∈J1,dK and (bi )i∈J1,dK are tuples from R∗d .

Along the same line as definition (4), for an arbitrary interval K ⊂ R+ such that |K| ≤ T , the
volatility measure built from exp(ωt ) is denoted as M , i.e,
                                                          Z
                                   ∀I ⊂ K, M (I) := eω(t) dt .                             (13)
                                                                      I

   We introduce as well the quadratic variation of Y of Eq. (12) obtained as the quadratic weighted
sum of Y i ’s volatility measures:
                                                                d
                                                                X
                                           ∀I ⊂ K,    Σ(I) :=             b2i M i (I),           (14)
                                                                    i=1
                   i
                        
where M i (I) = I eωu du               .
               R
                             i∈J1,dK
We introduce the respective volatility measures over a period of length ∆:
                                          (
                                            M∆ (t) := M ([t, t + ∆])
                               ∀t ≥ 0,                                .                          (15)
                                            Σ∆ (t) := Σ([t, t + ∆])

For any τ > 0, we define W (τ, ∆, Λ) as the variance of ln (M∆ (τ )) − ln (M∆ (0)) representing the
log-volatility increment of the volatility measure of Eq. (13) during a period of length ∆:
                                               h                          i
                             W (τ, ∆, Λ) = Var ln (M∆ (τ )) − ln (M∆ (0)) .                    (16)

In the same way, the variance of the random variable ln (Σ∆ (τ )) − ln (Σ∆ (0)), which represents the
log volatility increment of the aggregated process X during a period of length ∆, is a function of the
parameters τ , ∆ and Λ. So, we will denote it V (τ, ∆, Λ):
                                               h                          i
                              V (τ, ∆, Λ) = Var ln (Σ∆ (τ )) − ln (Σ∆ (0)) .                      (17)

                                                           7
     In what follows we will consider the limit of small intermittency and for that purpose we denote as
respectively V (τ, ∆, Λ) and W (τ, ∆, Λ) the first order approximation of V (τ, ∆, Λ) and W (τ, ∆, Λ),
i.e.,:

                                 W (τ, ∆, Λ) = W (τ, ∆, Λ) + o ∥Λ∥2                                 (18)
                                                                         
                                                                      2
                                                                                                    (19)
                                                                        
                                  V (τ, ∆, Λ) = V (τ, ∆, Λ) + o ∥Λ∥ .

In Appendix D, we prove the following result:

Theorem 1 For any (τ, ∆) ∈ K, the small intermittency variances can be expressed as follows:
                                                      d                τ 2Hl                
                                                      X                                    ∆
                               (a)   W (τ, ∆, Λ) =          a2l λ2l              gHl               .   (20)
                                                                       T                   τ
                                                      l=1
                                                       d               τ 2Hl                
                                                      X                                    ∆
                               (b)   V (τ, ∆, Λ) =          b4l λ2l              gHl               .   (21)
                                                                       T                   τ
                                                      l=1

where for any H ∈]0, 12 [:

                                         |1 + z|2H+2 − 2|z|2H+2 + |1 − z|2H+2 − 2
                             gH (z) :=                                            .                    (22)
                                                 z 2 H(1 − (2H)2 )(2H + 2)

Let us notice that we have, for any 0 < z < 1, when H → 0:

                              (z + 1)2 ln(z + 1) + (−1 + z)2 ln(1 − z) − 2z 2 ln(z)
                 gH (z) =                                                           + O(H)             (23)
                                                       z2
while, for any 0 < H < 1/2, when z → 0:
                                                        1
                                         gH (z) =             + O(z 2H )                               (24)
                                                    H(1 − 2H)

meaning that if we additionally have H → 0, the equivalence holds:
                                                                 1
                                                    gH (z) ∼                                           (25)
                                                                 H

4    Dominant Hurst Exponents & Conditions on Model Parameters
In order to account for the empirical findings of [26] within the N-SfBM, one should be in a situation
where the factor log-volatility has a larger Hurst exponent (i.e. H ∼ 0.11) than the log-volatility of
single stocks that is observed to be close to Hi = 0 (see Figure 1). Now, as per Eq. (8), the stock
returns are explained by the market factor contribution as well as the residual contribution. Hence the
roughness of the single stocks should predominantly be explained by the roughness of the residuals.
    In the light of Ref. [26], this suggests that the Hurst exponent  of the factor’s log-volatility should
be higher than the one of the residual log-volatilities ω̃ i∈J1,N K (ω̃ i := γi Ω + ω i ). In the following,
                                                            i
                                                              

we will derive conditions on (γi )i∈J1,N K as well as on the exposure vector (βi )i∈J1,N K such that this is
the case. All arguments developed below are based on estimation of the Hurst parameter based on the
small intermittency approximation within the identification approach detailed in Appendix E.




                                                         8
4.1      Hurst exponent of the residual volatility – Condition on γi
For any i ∈ J1, N K, Ω and ω i being (independent) Gaussian processes, ω̃ i is a Gaussian process too.
We consider the volatility measure associated with the process ω̃ i for a given i ∈ J1, N K:
                                                         Z
                                                             i
                                    ∀I ⊂ K, M (I) := eω̃ (t) dt
                                               f i
                                                                                                    (26)
                                                                                I

and for any (t, ∆) ∈ R2+ , we denote similarly to Eq. (57) the variance measure over a period of length
∆:

                                        ∀t ≥ 0,          fi (t) := M
                                                         M ∆
                                                                   fi ([t, t + ∆]) .                                                        (27)

Indeed, ω̃ i is a linear combination of two independent S-fBM processes for any i ∈ J1, N K. Thanks to
the point (a) of Theorem 1, W  fi (τ, ∆, Λi ), the small intermittency approximation of the variance of the
                                                                                                       
log-volatility increments of the residuals during a period of length ∆ denoted ln M fi (τ ) −ln M
                                                                                      ∆
                                                                                                   fi (0)
                                                                                                     ∆
(see the definition in Eq. (18)) can be expressed as follows:

                                                     τ 2H                                                   
                        fi (τ, ∆, Λi ) = γ 2 λ2                         ∆                τ 2Hi             ∆
                        W                 i                   gH                + λ2i              gHi               ,
                                                     T                  τ                T                   τ

where:
                                                   
                                               λ
   • Λi is the intermittency vector
                                               λi
   • gH (z) defined in Eq. (22)
                                                                                                    τ 2H
      According to the
                    approach advocated
                                       in Appendix E, if the γi λ
                                                               2 2                                                       ∆
                                                                                                                                 contribution to
                                                                                                                            
                                                                                                  T    gH              τ
the variance of ln        i (τ )
                        M̃∆− ln            was dominant, the residual volatility would have the Hurst
                                           i (0)
                                         M̃∆
exponent as that of the market factor, which contradicts the findings of [26]. As a result, γi should be
such that:3
                                        λ2i  τ 2Hi −2H
                                                                 
                                                                 ∆
                                   2
                                  γi ≪ 2                 rHi ,H                                     (28)
                                        λ T                      τ
where we have denoted
                                                                    gHi (z)
                                                    rHi ,H (z) =            .                                                               (29)
                                                                    gH (z)
    If we refer to the estimates in [26], we can furthermore assume that λi ≃ λ, H ≃ 0.1 ≫ Hi ≃ 0. In
this case, using expression (22), that, one can show that, ∀z < 1 r0,H ≥ 1. It results that a sufficient
for condition (28) to hold is that:
                                                     H
                                                      T
                                               γi ≪        .
                                                      τ
which holds, in the range τ ≪ T , provided

                                                             γi ≤ 1 .                                                                       (30)

    From the empirical results of [27], we know that γi < 0.5 for all stocks so that, according to previous
criterion, the residual volatility roughness is dominated by Hi for any τ ≪ T .
  3
      Note: throughout the following heuristic discussion, a ≪ b means that b is more than – say – 10 times a.



                                                                9
4.2    Hurst exponents of single stocks – Upper bound on βi
Let us now exhibit an upper bound condition on the exposure coefficient βi in order for the Hurst
exponent of the idiosyncratic residual volatility mode to represent the one of stock i. Again, our
discussion will rely on the identification approach detailed in Appendix E.
    Indeed, any dxi is in the same configuration as in the Section 3. Under the condition (30), we
can therefore use point (b) of Theorem 1 to obtain the following   expression
                                                                           of Vi (τ, ∆, Λi ), the small
intermittency approximation of the variance of ln M∆ (τ ) − ln M∆ (0) the log-quadratic variation
                                                        i             i
                                                             

increment of xi during a period of length ∆:
                                                                            
                                      4 2 τ          ∆         4 2 τ          ∆
                                           2H                    2Hi
                    Vi (τ, ∆, Λi ) = βi λ       gH        + σi λi        gHi       .
                                           T         τ             T          τ

   Using the same arguments of the one in Section 4.1, the idiosyncratic volatility mode is dominated
by the second term of Eq. (31) provided:

                                      σi4 λ2i  τ 2Hi −2H
                                                                   
                                                                   ∆
                                 4
                                βi ≪ 2                     rHi ,H                                (31)
                                       λ        T                  τ

where rHi ,H (z) is defined in (29). Along the same line as for Eq. (28), given the empirical values of
H, Hi , λ, λi , (31) holds in the range τ ≪ T if:

                                                       |βi | ≤ σi                                         (32)

    This condition appears to be empirically valid since the idiosyncratic contribution to volatility σi is
around 2 while factor exposure βi appear to be in the range (0.5 − 1.5) (see e.g. [5] as well as Appendix
H in particular Figure 11, 12 and 13), with some exceptions: high-beta stocks with low idiosyncratic
volatilities will presumably look more like the index, as indeed expected.

4.3    Hurst exponent of sub-indexes
Let us consider sub-indexes It , constructed from a subset of size Ns of stocks xit with weights (wi )i∈J1,Ns K ∈
R∗Ns :
                                              Ns
                                              X                     Ns
                                                                    X
                                       It =         wi xit ,                wi = 1.                       (33)
                                              i=1                   i=1

Note that when Ns = N , the total number of stocks in an index, It is simply the market mode ft . The
sub-index evolution is given by:
                                                                 Ns
                                                                 X
                                          dIt = βdft +                 wi deit ,                          (34)
                                                                 i=1

where we have denoted β the mean value of βi :
                                                          Ns
                                                          X
                                                β :=             wi β i .                                 (35)
                                                           i=1

    In Eq. (34) we are in the same configuration as in Section 3. Conducting similar computations
as previously, under individual condition (30), the small intermittency approximation of the variance


                                                           10
of ln M∆I (τ ) − ln M I (0) (the log-quadratic variation of the sub-index process I during a period of
                          
                     ∆
length ∆) reads:
                                          τ 2H                          Ns                                            
                                    4                           ∆           X                      τ 2Hi             ∆
                V (τ, ∆, Λ) = β λ2                   gH                 +           wi4 σi4 λ2i              gHi               .   (36)
                                                 T              τ                                  T                   τ
                                                                            i=1

   Under the same approach as before, we can see that the Hurst exponent of the sub-index I in
Eq. (33) can be approximated with the Hurst exponent of the factor H if the first term of the previous
sum dominates, namely:
                                  Ns
                                      wi4 σi4 λ2i  τ 2(Hi −H)
                                                                        
                             4   X                                      ∆
                            β ≫            2
                                                                rHi ,H     .                      (37)
                                         λ          T                   τ
                                             i=1

In the case when Hi → 0 (as suggested by the empirical findings of [26]), a, Hi → 0) one can show
that (the proof is in Appendix F):

                                    ∀z ∈]0, 1[,        r0,H (z) ≤ CH (3 − 2 ln(z)) ,                                               (38)

with CH = H(1−2H)(1+2H)(1+H)
               2(22H −1)
                             . In that situation, provided λi ≃ λ, previous inequality holds if:
                                                2H  3 2 
                                             4  T      e τ
                                        β ≫ CH      ln       w3 σ 4 ,                                                              (39)
                                                τ       ∆2
where
                                                                    Ns
                                                                    X
                                                     w3 σ 4 =             wi4 σi4
                                                                    i=1

represents the average value of wi3 σi4 , weighted by wi . For the sake of simplicity, one can consider that
σi ≃ 2 and wi = 1/Ns which gives
                                                                          16
                                                           w3 σ 4 =
                                                                          Ns3
leading to the condition:
                                                    2H   3 2  31
                                         4         T 3 1     e τ
                                        β Ns ≫ DH
                                         3             3
                                                          ln                                                                       (40)
                                                   τ          ∆2
with DH = 16CH .
   Given that ∆ < τ < T , for ∆ = 1 trading day and T ≈ 5.103 ∆ corresponding roughly an overall
sample size T of 10 years, with H = 0.1, one has:
                                    2H  3 2  13
                                T      3    e T                                              1/3
                                         ln           ≃5                        and        DH ≃ 1.8 .
                                ∆            ∆2

It results that condition (40) holds provided
                                                            4
                                                       β 3 Ns ≫ 10 .                                                               (41)

The latter condition can be understood from two perspectives: for relatively small β-exposures, one
needs to have a large basket of single stocks to reach the regime where the regularity of the index is
encoded in the regularity of the factor’s sample paths. If on the contrary the basket of single stocks is
of relatively small size Ns , those single stocks would better have a high exposure to the factor so that
the factor represents well the overall index dynamics (corresponding to Ns = N ).


                                                                11
   That being said, for a fixed Ns , and given condition Eq. (32) from the previous Section, a sufficient
condition for any i ∈ J1, Ns K on each exposure value summarized as
                                                     3
                                                 10       4
                                                              ≪ |βi | ≪ σi .                              (42)
                                                 Ns

   In the next Sections, we give some results concerning the empirical estimation of the N-SfFM, then
present numerical experiments confirming the theoretical estimates made in this Section. We will then
turn to an empirical validation of our scenario.


5    Calibration Method
This section describes the calibration procedure we use in order to estimate respectively the Hurst
exponent of the factor H and the Hurst exponents of the idiosyncratic modes Hi . We establish an
asymptotic formula, when the number of single stocks Ns goes to infinity, of the estimated factor
quadratic variation in terms of the assets quadratic variations and the exposure vector β that is nec-
essary to estimate its Hurst exponent via the general method of moments (GMM) (see [13]) used by
Wu et al. (in practice, we consider moments of second order: autocovariance functions, following the
approach described in Section 4 in [26]), which is applied in Section 6.

    Our calibration method is decomposed in the following steps:

Step 1 consists in estimating the exposure vector β. Utilizing the estimation approach proposed by
Chicheportiche et al. in [27], we aim to determine β so that ββ ⊤ serves as an approximation to the
covariance matrix of the asset returns (dxit )i∈J1,Ns K , represented by XX ⊤ :
                                                 
                               β̂ = arg min E XX ⊤ − ββ ⊤                                      ,          (43)
                                     β∈RNs                                      off diagonal


where ||.||off diagonal is the off-diagonal Frobenius norm.
The use of the off-diagonal Frobenius norm was already proposed by Chicheportiche et al. in [27] for
calibrating the exposure vector β. Its use here is for calibrating the exposure vector focusing on the
asset covariations.
Thanks to the formulation of the model in Eq. (8), the correlation between the residual volatility modes
does not play any role since the residual driving Brownian motions are independent.

Step 2 aims at identifying a proxy for the factor quadratic variation, denoted as ⟨f ⟩t . This component
is crucial for estimating the factor Hurst exponent H. Our approach utilizes Eq. (44) as presented in
the following result.

Proposition 1 We consider Ns ∈ N∗ . If β has independent and identically distributed entries such
that:

                                ∀i ∈ J1, Ns K, E βi4 < ∞
                                                     


and independent of (ϵi )i∈J1,Ns K , the following claim holds :

                                                                         Ns
                                        D E                         1    X
                         ∀I ⊂ K,         fˆ           ∼       PNs               βi2 xi I ,         a.s,   (44)
                                              I Ns →∞                   4
                                                                   i=1 βi i=1


                                                              12
where fˆ is defined as:

                                  ∀t ∈ K,    fbt := arg min ||Xt − βf || ,                            (45)
                                                     f ∈R


where ||.|| is the L2 norm in RNs .

The proof is given in Appendix G.



    It is noteworthy that Eq. (44) allows for the direct estimation of the factor quadratic variation
using the quadratic variations of asset returns. Consequently, in practical applications, the volatility
of the factor can be directly inferred from the volatility of individual stocks by employing a daily
volatility estimator based on high-frequency (intraday) data, such as the Garman-Klass estimator (see
Eq. (47)). This approach is contingent upon having a sufficiently large number of stocks in the sample,
as illustrated in our empirical study in Section 7.



    The log-quadratic variation of returns serves as the principal input for the Generalized Method of
Moments (GMM) introduced in [26] and employed to estimate the roughness, specifically the Hurst
exponent, of a given time series based on the small intermittency approximation of covariance of log
volatilities. As explained in Appendix C.2, the bias on the estimated parameters is mitigated in such
limit. The GMM operates under the assumption that log-volatility follows a Gaussian process. There-
fore, it is prudent, prior to estimating roughness, to address the pronounced skewness apparent in the
underlying time series. This skewness results from the logarithmic transformation, which tends to am-
plify the effects of lower return values. Such skewness subsequently propagates into the log-volatility
(and, by extension, the log-quadratic variation) components, thereby contravening the Gaussian as-
sumption inherent in the SfBM model and adversely impacting the estimation of the Hurst exponent,
particularly when using daily data. To comply with this assumption, we undertake a “Gaussianisation”
procedure as a pre-processing step in order to rectify the empirically determined log-quadratic varia-
tions that are distorted by measurement noise. The applied methodology is detailed in Appendix H.1.



    Hereafter, we consider as the estimated time series of (Ωt )t the gaussianized version of ln (⟨f ⟩t ) −
E (ln (⟨f ⟩t )).
Step 3 leverages the GMM introduced in [26] to estimate H and λ2 from the time series of (Ωt )t
derived in the previous step.
Step 4 deduces the estimated quadratic variations of the residual processes ϵi t i∈J1,N K through the
                                                                                
                                                                                       s
identity:

                                      d xi t = βi2 d ⟨f ⟩t + d ϵi t .                                 (46)

Step 5 aims at estimating the Hurst exponents Hi of the idiosyncratic log-volatility of individual
stocks. The process involves the following steps:

   • The time series ω̃ti i∈J1,Ns K are approximated using the gaussianized versions of ln ϵi t −
                                                                                              

     E ln ϵi t , as derived in Step 4;
               



                                                    13
    • Eq. (8) enables the estimation of the time series of the idiosyncratic modes, ωti i∈J1,Ns K , by
                                                                                               

      regressing the time series ω̃ i i∈J1,Ns K against Ωt , derived in Step 1;
                                       

    • Finally, the series ωti i∈J1,Ns K serve as the input for the GMM to estimate the corresponding Hurst
                             

      exponents Hi as well as the parameters λ2i for all i ∈ J1, Ns K.


6     Numerical Experiments
This Section is devoted to numerical experiments. First, we present numerical evidence that the N-
SfFM indeed reproduces the stylized facts discussed in Sections 4.1 and 4.2. More precisely, the Hurst
exponent of the factor is expected to be the one of the index (constructed as in Eq. (33) with equal
weights) and the Hurst exponent of the the single stocks is the one of the idiosyncratic residual modes.
The formulation of Eq. (8) allows a correlation between the volatility modes of the factor the residu-
als, which is one of the purposes of the Nested Factor Model of Chicheportiche et al. in [27]. Then,
we demonstrate that the roughness of the index is indeed encoded in the roughness of the factor.
Finally by using the calibration method detailed in Section 5, we evaluate how robust the estimate
of the Hurst exponent H of the factor as well as the Hurst exponents of the idiosyncratic modes Hi are.

    In order to show that the N-SfBM reproduces the non-intuitive behaviour announced earlier, we
generate the model with N synthetic asset return trajectories xit of total length L following the dy-
namics specified by Eq. (8), as well as the index trajectories obtained as the average path over different
N assets with s = 28 simulated data points of the asset returns between the time n∆ and (n + 1)∆
for n = 0, ..., L − 1. The model parameters are specified accordingly.
To choose realistic values for βi and σi , one can use the empirical distributions of these coefficients
from the asset returns of stocks that constitutes the S&P500. This is documented in Appendix H.2
where the vector β is calibrated using close-to-close returns of an arbitrary bench of S&P500 stocks
using Eq. (43) and the vector σ is identified using the variance of the residuals obtained using the
same bench of stocks. As a result, the distribution of the components of β and σ can be fitted as a
beta-distribution whose density is of the form xa−1 (1−x)b−1 . In order to respect the feasible conditions
of Section 4, we choose to fix σi = 1 for all i ∈ J1, N K.

We present in Figure 2 the empirical distributions of the Hurst exponents of the single stocks ver-
sus the empirical distribution of the index Hurst exponent generated as described earlier.




                                                     14
               25

               20

               15
          Count




               10

                  5

                  0
                  0.00           0.05          0.10               0.15             0.20
                                          Hurst exponent
 Figure 2: We construct the empirical distribution through a 50 sized sample of the estimated Hurst
   exponents of N = 100 synthetic single stocks (blue) together with the one of the index (black)
  defined as the empirical mean of the simulated stocks. β entries are considered independent and
identically distributed drawn from a beta-distribution of parameters a = 9.6 and b = 5.6. The model
  parameters are fixed as follows: H = 0.11, λ = λi = 0.05, Hi = 0.01 and σi = 1 for all i ∈ J1, N K,
                        L = 214 , T = 212 , s = 28 and γi = 0.2 for all i ∈ J1, N K.

   We observe that the Hurst exponent distribution of the index is centered on the theoretical Hurst
exponent H = 0.11 of the factor, and the empirical distribution of the single assets Hurst exponents
produces mainly values around 0.01 which resembles Figure 1.

In Figure 3 , we evaluate the discrepancy between the empirical distribution of the Hurst exponent
of the index denoted HI and the Hurst exponent of the factor H. The latter index is constructed
similarly as in the experiment of Figure 2. One can see that the estimated Hurst exponent of the index
corresponds (within 95% confidence interval) to the Hurst exponent of the factor. This means that the
roughness of the index is captured by the roughness of the factor in the N-SfFM dynamic as expected
from the condition of Eq. (42).




                                                 15
                            Mean Hurst exponent
              0.16

              0.14

              0.12
         HI




              0.10

              0.08
                     0.08                          0.12                          0.16
                                                    H
  Figure 3: For each value of H, we construct a 20 sized sample of the estimated Hurst exponents of
 the empirical index HI constructed with N = 200 synthetic single stocks and we plot its mean value
together with the 95% confidence interval (purple) as well as the dashed line that corresponds to the
     first bisector. β entries are considered independent and identically distributed drawn from a
   beta-distribution of parameters a = 9.6 and b = 5.6. The model parameters are fixed as follows:
    λ2 = λ2i = 0.001, σi = 1, Hi = 0.01 for all i ∈ J1, N K, T = L = 215 , s = 28 and γi = 0.01 for all
                                                i ∈ J1, N K.

    In Figure 4, we evaluate the estimation bias of HI and H through its empirical distribution and
deviation around a chosen theoretical value of the factor Hurst exponent H = 0.08 or H = 0.11, as
N goes to infinity. For each value of N , we generate a sample of 20 batches of synthetic stock returns
which enables to obtain a sample of 20 estimates of HI and H. Then we plot the associated mean
values with the 95% confidence interval in comparison with the theoretical value of H. As N increases,
we see that the estimated Hurst exponent of the index converges to the chosen theoretical values of
the Hurst exponents of the factor. Furthermore, for small values of N the index roughness is close to
the one of a single stock as there is no sufficient number of assets to offset the effect of the residuals.
As N grows, one can see that estimated Hurst exponent of the index converges to the theoretical value
of the factor Hurst exponent H. For small values of H one can see that a higher number of assets is
needed to reach the previous regime because of the exposure of single stocks to the factor. Similarly via
applying the calibration algorithm, we see that, as N grows, the estimated Hurst exponent of the factor
also reaches the chosen theoretical values. Furthermore, we do observe a continuum of effective Hurst
exponents for the dominant factor as N increases: for small N values, the dominant factor behaves as
a single stock with H ≪ 0.11 (see Proposition 2 in [26]); larger N leads to a better defined factor with
a Hurst exponent approaching its theoretical value. It is interesting to notice a small bias between the
estimated Hurst exponent of the index and the factor on one side and between the estimated Hurst
exponent of the factor and its corresponding theoretical value on the other side which may come from
the error in proxying the quadratic variation of the factor (see step 2 of the calibration method in
Section 5). This will be the object of a future study.




                                                    16
                                                                                     0.12
                  0.08
                                                                                     0.10
Hurst exponents




                                                                   Hurst exponents
                  0.06
                                                                                     0.08
                  0.04
                                         Theoretical H =0.08                         0.06                   Theoretical H =0.11
                  0.02                   Estimated HI                                                       Estimated HI
                                         Estimated H                                 0.04                   Estimated H
                  0.00
                         2   4 8 16 32 64 128 256                                           2   4 8 16 32 64 128 256
                               Number of assets (N)                                               Number of assets (N)
       Figure 4: Using synthetic data for different index sizes N , we plot the mean value and the associated
          95% confidence interval from a sample of 20 copies of the Hurst exponent of the empirical index
         estimates in (brown) and the estimated Hurst exponent of the factor (green) together with error
        bars compared with the theoretical factor Hurst exponent H = 0.08 (left) and H = 0.11 (right) (in
        horizontal black line). β entries are considered to be independent and identically distributed drawn
       from a beta-distribution of parameters a = 9.6 and b = 5.6, λ2 = λ2i = 0.001, σi = 1, Hi = 0.01 for all
                           i ∈ J1, N K, T = L = 215 , s = 28 and γi = 0.01 for all i ∈ J1, N K.

           Finally, we evaluate in Figure 5 the goodness of the estimation of the idiosyncratic Hurst exponents.
       Thanks to synthetically generated data with N = 300, we apply the calibration method to estimate
       the idiosyncratic Hurst exponents and compare them with the theoretical values. Here we simulate
       using the same Hurst exponents for all the idiosyncratic modes. One can see that the estimated Hurst
       exponents of the idiosyncratic modes lie around the chosen theoretical values: Hi = 0.03 and Hi = 0.07,
       which demonstrates a good calibration.



                  20.0                              Hi = 0.03                         25                               Hi = 0.07
                  17.5                                                                20
                  15.0
                  12.5                                                                15
  Count




                                                                            Count




                  10.0
                   7.5                                                                10
                   5.0                                                                 5
                   2.5
                   0.00.00    0.05     0.10      0.15       0.20                       0
                                                                                       0.00      0.05     0.10      0.15       0.20
                                        Hi                                                                 Hi
       Figure 5: Calibration of the Hurst exponents Hi using synthetically generated data for N = 300 with
           the following parameters: H = 0.1, β entries are considered to be independent and identically
       distributed drawn from a beta-distribution of parameters a = 9.6 and b = 5.6, λ2 = λ2i = 0.01, σi = 1,
        Hi = 0.03 (Left) and Hi = 0.07 (Right) for all i ∈ J1, N K, T = L = 215 , s = 28 and γi = 0.1 for all
                                                     i ∈ J1, N K.




                                                                   17
7     Empirical Results
This section presents the results of the model calibration using empirical data. We use historical daily
open, high, low, and close price time-series of S&P500 stocks from YahooFinance and implement the
calibration method detailed in Section 5.

    The estimation of the roughness of each log-volatility component the N-SfFM seeks to corroborate
that the roughness inherent to the log-volatility of individual stocks predominantly stems from the
residual log-volatility of the idiosyncratic components of stock returns. This idiosyncratic roughness
vanishes when averaging stock returns to reconstruct index trajectories, whose roughness is then driven
by the log-volatility factor roughness. Hence, for the N-SfFM to align with the empirical results of Wu
et al. (see Figure 1), we expect to find log-volatility components with the following Hurst exponents:
H ≈ HI ≳ 0.1 and for all stocks i, Hi ≈ 0.

    The first part of this section focuses on estimating the log-volatility factor roughness, confirming
it aligns with that of the S&P500 index, while the subsequent part addresses the estimation of the
roughness of the idiosyncratic components.

7.1   Estimating the factor roughness using daily market data
As noted in Section 5, calculating the factor volatility directly from the daily volatility of the assets,
as outlined in Eq. (44), allows for the use of a volatility estimator with desirable characteristics, such
as those related to log-volatility increment distribution and scale invariance properties [33, 34]. An
example of such an estimator is the Garman-Klass (GK) daily volatility estimator:

                                          High                           Close
                                                                            
                                 1
                           2
                         σ̂GK = log2             − (2 log(2) − 1) log2           ,                    (47)
                                 2        Low                            Open

where High, Low, Open, Close stand respectively for the high, low, open, and close quotes over one day.

Using daily market data spanning from January 1, 2016, to January 1, 2020, we randomly selected
20 combinations of Ns stocks from the S&P500 index, with Ns taking values from the set 2k k∈J1,8K .
                                                                                                

For each of these 20 combinations with a given Ns number of stocks, we estimate the daily volatility
of the factor, derived from the GK estimator of the stocks volatility through Eq. (44). Each of these
20 estimated factor volatilities, for a given Ns , then serves as an input in the Generalized Method of
Moments (GMM), as introduced in [26], to estimate the Hurst exponent of the factor, H. We com-
pute the mean value of the Hurst exponent for the factor throughj20 trials,
                                                                          k with each trial performed
                                                                        k
with varying GMM time lags. These time lags are structured as 2 4                  where the length Q is
                                                                           k∈J0,QK
derived from a uniform distribution U ([28, 40]). As a result, we obtain 20 mean value estimations of
the factor Hurst exponent H (the mean value is computed from the 20-sized sample of the estimated
H that corresponds to each value of Q) for each value of Ns . These estimations are compared with
the Hurst exponent of the S&P500 index, estimated using the GMM on the S&P500 Garman-Klass
estimator. Results are summarized in Figure 6.




                                                   18
                               0.18
                                          Mean Hurst exponent
                               0.16       H = 0.13

                               0.14
          Hurst exponent (H)




                               0.12
                               0.10
                               0.08
                               0.06
                               0.04
                               0.02
                                      2       4       8   16       32      64   128   256
                                                      Number of assets (N < )
Figure 6: We plot using the S&P500 market data for each asset number Ns the mean value and the
95% confidence interval of the Hurst exponent of the factor across multiple GMM time lag lengths
   via blue error bars, which we compare to the measured Hurst exponent of the S&P500 index
                        H ≃ 0.13, represented by the horizontal black line.

    First, it should be noted that we retrieve the order of magnitude of the S&P500 roughness
(HI ≳ 0.1) observed in previous works [25, 26]. More importantly, Figure 6 supports the numeri-
cal experiments that demonstrate that the roughness of the factor reflects that of the S&P500 index as
Ns increases. This further corroborates the idea that the roughness of indices stems from a common
volatility component (Ωt ) shared among individual stock dynamics. It also suggests that the “very
rough” nature of individual stock volatility (Hi ≈ 0) is likely attributable to their idiosyncratic com-
ponent. An empirical investigation into the roughness of these components is provided in the next
section.
    Note also that Figure 6 reveals that the effective Hurst exponent varies continuously as Ns grows,
from the multifractal behaviour characteristic of single stocks (Hi ≈ 0) to a rough behavior similar to
that of indices (HI ≈ 0.13).

7.2   Estimation of the roughness of idiosyncratic components
We now undertake the calibration of the N-SfFM, as introduced in Section 5 and validated in Section 6,
to estimate the roughness of the idiosyncratic components of stock volatility, denoted (ω i )i∈J1,243K .
The calibration is applied to empirical daily data from YahooFinance spanning from 01/01/1994 to
01/01/2026 for 243 US stocks that are constituents of the S&P500 throughout the entire period.

   To mitigate uncertainties and noise inherent to both the calibration process and the data, one
can exploit the fact that the roughness of S&P500 volatility has already been established in Ref.[25].
This amounts to identifying the estimated daily factor volatility, Ωt , to the one of the S&P500 in-

                                                                19
dex, approximated by the Garman-Klass estimator. It should be noted that the Ω time series derived
after Step 3 of our calibration is 80% correlated with the Garman-Klass estimator of the S&P500 index.

    Consequently, we employ two calibration approaches: the first involves estimating the factor log-
volatility using the complete calibration method, while the second bypasses the second step of the
calibration method by directly using the Garman-Klass estimate of the S&P 500 log-volatility as the
factor log-volatility. As an illustration, several time series of the idiosyncratic volatility component
obtained through our calibration, denoted ωti , are displayed in Figure 7.

    4
                      MO                         4
                                                                  AMAT                        4
                                                                                                               HBAN

    2                                            2                                            2

    0                                            0                                            0
t




                                             t




                                                                                          t
i




                                             i




                                                                                          i
    2                                            2                                            2

    4                                            4                                            4
        1995 2000 2005 2010 2015 2020 2025           1995 2000 2005 2010 2015 2020 2025           1995 2000 2005 2010 2015 2020 2025

    4
                      VLO                        4
                                                                   SPG                        4
                                                                                                                ADI

    2                                            2                                            2

    0                                            0                                            0
t




                                             t




                                                                                          t
i




                                             i




                                                                                          i




    2                                            2                                            2

    4                                            4                                            4
        1995 2000 2005 2010 2015 2020 2025           1995 2000 2005 2010 2015 2020 2025           1995 2000 2005 2010 2015 2020 2025

    4
                     AMGN                        4
                                                                  LRCX                        4
                                                                                                                AEP

    2                                            2                                            2

    0                                            0                                            0
t




                                             t




                                                                                          t
i




                                             i




                                                                                          i




    2                                            2                                            2

    4                                            4                                            4
        1995 2000 2005 2010 2015 2020 2025           1995 2000 2005 2010 2015 2020 2025           1995 2000 2005 2010 2015 2020 2025

  Figure 7: Idiosyncratic time series as estimated from market data of randomly selected S&P500
      single stocks. The complete nomenclature of the asset tokens is specified in Appendix I.

    Using the calibrated time series ωti as inputs for the Generalized Method of Moments (GMM) of
[26], for all stocks, as outlined in the final step of the calibration Section 5, allows for the estimation
of the idiosyncratic Hurst exponent for each stock. The resulting values are aggregated into empirical
distributions, which are presented Figure 8.
    As expected, the results obtained from the full calibration method, depicted in Figure 8a, and those
obtained sourcing the S&P500 volatility as the volatility factor, shown in Figure 8b, are quite compa-


                                                                 20
                                                                        30
        30
                                                                        25
                                                                        20
        20
Count




                                                                Count
                                                                        15
        10                                                              10
                                                                         5
        0                                                               0
        0.00      0.02    0.04        0.06   0.08   0.10                0.00    0.02    0.04        0.06   0.08   0.10
                                 Hi                                                            Hi
              (a) Deriving Ωt from steps 1 and 2                         (b) Sourcing Ωt as the S&P500 volatility

        Figure 8: Estimated Hurst exponents Hi from the estimated idiosyncratic time series of all the
                selected S&P500 single stocks. Note that most of the Hi are very close to zero.


rable. More importantly, Figure 8 illustrates that the Hurst exponents of the idiosyncratic volatility
components, denoted Hi , are predominantly clustered around H ≃ 0. This demonstrates that the
idiosyncratic volatility of individual stocks exhibits very high roughness compatible with a multifractal
behavior (Hi = 0). It is noteworthy that such estimated values are not statistically distinguishable
from those obtained for strictly vanishing Hurst exponent (H = 0). Numerical experiments using a
genuine Multifractal Random Walk (MRW) path with H = 0 and a sample size comparable to our
empirical S&P 500 time series (approximately 3 × 103 data points; see Table 1 in [26]) reveal that mean
value and the confidence interval are of the same order of magnitude as those observed in Figure 8
where the means and standard deviations are of comparable magnitude (0.01 and 0.02 in Figure 8a;
0.02 and 0.03 in Figure 8b). Let us mention that a small subset of idiosyncratic residuals exhibits
higher Hurst exponents (Hi ≳ 0.1). These outliers are omitted from Figure 8a and 8b for visualiza-
tion purposes. While this discrepancy may arise from empirical data noise, it could also indicate that
certain stocks inherently possess smoother volatility profiles.
    Combined with the results from the previous section, these findings substantiate our hypothesis:
the roughness of individual stocks is driven by the multifractal idiosyncratic component. When single-
stock trajectories are averaged to form the market index, this idiosyncratic contribution washes out,
leaving only the less rough, common volatility component (the log-volatility factor) observable.


8            Conclusion and Prospects
Let us summarize our main results. This paper primarily aimed to demonstrate that the Nested
Factor Model, incorporating Stationary fractional Brownian motions as log-volatilities, reproduces the
somewhat surprising empirical findings of Wu et al. [26]. Our framework was constructed on the
intuition that the roughness of the combination of two signals with differing levels of roughness is
dominated by the roughest signal. Hence, observing that Hurst exponents of single stocks are lower
than those of indexes, we conjectured that their roughness originates from the idiosyncratic components
of the stock dynamics, which average out in the dynamics of the indexes.
    The theoretical investigation of such a framework, leveraging the small intermittency approxima-
tion, allowed us to determine the regimes where such intuition holds, i.e. when the roughness of the
idiosyncratic component is reflected in the individual trajectories of stocks. By simulating the pro-
posed framework within these relevant regimes, we generated synthetic time series that match the


                                                           21
empirical roughness observed in both stocks and indexes. Hence, we demonstrated that in addition to
the enticing features of the Nested Factor Model established by Chicheportiche et al. [27], the N-SfFM
also naturally accounts for different levels of roughness between stocks and indexes.
    For greater simplicity and tractability, we limited the N-SfFM to its one-factor version, with no
residual factor volatility. A natural extension of this work would be to investigate how our framework
performs when incorporating additional factors, each with its own residual volatility modes, as origi-
nally introduced in [27]. These additional factors could represent different industry sectors, allowing
one to investigate whether some industries exhibit particularly rough components. Accounting for the
leverage and Zumbach effects is also an interesting direction to pursue.




   Acknowledgment: This work has received support from the French government, managed by the
National Research Agency (ANR), under the "France 2030" program with reference "ANR-23-IACL-
0008.

                                                  22
References
 [1] Allez, R. and Bouchaud, J.-P. (2011). Individual and collective stock dynamics: intra-day season-
     alities. New Journal of Physics, 13(2), 025010.

 [2] Muzy, J.-F., Baïle, R., & Bacry, E. (2013). Random cascade model in the limit of infinite integral
     scale as the exponential of a nonstationary 1/f noise. Application to volatility fluctuations in
     stock markets. Physical Review E, 87(4), 042813. https://doi.org/10.1103/PhysRevE.87.042813

 [3] Mandelbrot, B. (1967). The variation of certain speculative prices. The Journal of Business,
     393–413.

 [4] Neuman, E. and Rosenbaum, M. (2018). Fractional Brownian motion with zero Hurst parameter:
     a rough volatility viewpoint.Electron. Commun. Probab, 23 1–12.

 [5] Garnier-Brun, J., Benzaquen, M., Ciliberti, S., and Bouchaud, J.-P. (2021). A new spin on optimal
     portfolios and ecological equilibria. Journal of Statistical Mechanics: Theory and Experiment,
     2021(9), 093408.

 [6] Bayer, C., Friz, P. K., Fukasawa, M., Gatheral, J., Jacquier, A., and Rosenbaum, M. (2023).
     Rough volatility. SIAM.

 [7] Cizeau, P., Potters, M., and Bouchaud, J.-P. (2001). Correlation structure of extreme stock returns.
     Quantitative Finance, 217–222.

 [8] Lillo, F. and Mantegna, R. N. (2000). Symmetry alteration of ensemble return distribution in
     crash and rally days of financial markets. The European Physical Journal B, 15, 603–606.

 [9] Bennedsen, M., Lunde, A., and Pakkanen, M. S. (2022). Decoupling the short-and long-term
     behavior of stochastic volatility. Journal of Financial Econometrics, 20(5), 961–1006.

[10] Bayer, C., Friz, P., and Gatheral, J. (2016). Pricing under rough volatility. Quantitative Finance,
     16(6), 887–904.

[11] Fukasawa, M. (2021). Volatility has to be rough. Quantitative Finance, 21(1), 1–8.

[12] Livieri, G., Mouti, S., Pallavicini, A., and Rosenbaum, M. (2018). Rough volatility: evidence from
     option prices. IISE Transactions, 50(9), 767–776.

[13] Bolko, A. E., Christensen, K., Veliyev, B., and Pakkanen, M. (2023). Roughness in spot variance?
     A GMM approach for estimation of fractional log-normal stochastic volatility models using realized
     measures. Journal of Econometrics, 745–778.

[14] Wick, G. C. (1950). The evaluation of the collision matrix. Physical Review, 80:268–272.

[15] Fukasawa, M., Takabatake, T., and Westphal, R. (2019). Consistent estimation for fractional
     stochastic volatility model under high-frequency asymptotics Mathematical finance, 32(4):1086—
     1132.

[16] Ghashghaie, S., Breymann, W., Peinke, J., Talkner, P., and Dodge, Y. (1996). Turbulent cascades
     in foreign exchange markets. Nature, 381(6585), 767–770.

[17] Mandelbrot, B. B., Fisher, A. J., and Calvet, L. E. (1997). A multifractal model of asset returns.
     Cowles Foundation Discussion Paper.


                                                   23
[18] Forde, M., Fukasawa, M., Gerhold, S., and Smith, B. (2022). The Riemann–Liouville field and its
     GMC as H→0, and skew flattening for the rough Bergomi model. Statistics & Probability Letters,
     181, 109265.

[19] Armstrong, T. B., and Kolesár, M. (2021). Sensitivity analysis using approximate moment condi-
     tion models. Quantitative Economics, 12, 77–108.

[20] Fyodorov, Y. V., Khoruzhenko, B. A., and Simm, N. J. (2016). Fractional Brownian motion with
     Hurst index H=0 and the Gaussian unitary ensemble.The Annals of Probability, 44(4), 2980—
     3031.

[21] Hager, P. and Neuman, E. (2022). The multiplicative chaos of H=0 fractional Brownian fields.
     The Annals of Applied Probability, 32(3), 2139–2179.

[22] Bacry, E. and Muzy, J.-F. (2003). Log-infinitely divisible multifractal processes. Communications
     in Mathematical Physics, 236, 449–475.

[23] Muzy, J.-F. and Bacry, E. (2002). Multifractal stationary random measures and multifractal ran-
     dom walks with log infinitely divisible scaling laws. Physical Review E, 66(5), 056121.

[24] Bacry, E., Delour, J., and Muzy, J.-F. (2001). Multifractal random walk. Physical Review E, 64(2),
     026103.

[25] Gatheral, J., Jaisson, T., and Rosenbaum, M. (2018). Volatility is rough. Quantitative Finance,
     18(6), 933–949.

[26] Wu, P., Muzy, J.-F., and Bacry, E. (2022). From rough to multifractal volatility: The Log S-fBM
     model. Physica A, 604, 127919.

[27] Chicheportiche, R. and Bouchaud, J.-P. (2015). A nested factor model for non-linear dependencies
     in stock returns. Quantitative Finance, 15(11), 1789–1804.

[28] Chicheportiche, R. and Bouchaud, J.-P. (2012). The joint distribution of stock returns is not
     elliptical. International Journal of Theoretical and Applied Finance, 15(03), 1250019.

[29] Muzy, J.-F., Delour, J., and Bacry, E. (2000). Modelling fluctuations of financial time series: from
     cascade process to stochastic volatility model. The European Physical Journal B, 17, 537–548.

[30] Bacry, E., Delour, J., and Muzy, J.-F. (2001). Modelling financial time series using multifractal
     random walks. Physica A, 299(1–2), 84–92.

[31] Comte, F. and Renault, E. (1998). Long memory in continuous-time stochastic volatility models.
     Mathematical Finance, 8(4), 291–323.

[32] Bacry, E., Kozhemyak, A., and Muzy, J.-F. (2013). Log-Normal continuous cascades: aggregation
     properties and estimation. Application to financial time-series. Quantitative finance, 13(5), 795–
     818.

[33] Mouti, S. (2023). Rough volatility: evidence from range volatility estimators. arXiv preprint
     arXiv:2312.01426.

[34] Garman, M. B. and Klass, M. J. (1980). On the Estimation of Security Price Volatility from
     Historical Data. The Journal of Business, 67–78.



                                                   24
[35] Bachelier, L. (1900). Théorie de la spéculation. Annales scientifiques de l’École normale supérieure,
     17, 21–86.

[36] Sharpe, W. F. (1964). Capital Asset Prices: A Theory of Market Equilibrium under Conditions
     of Risk. The Journal of Finance, 19(3), 425–442.

[37] Lintner, J. (1965). The Valuation of Risk Assets and the Selection of Risky Investments in Stock
     Portfolios and Capital Budgets. The Review of Economics and Statistics, 47(1), 13–37.

[38] Fama, E. F., & French, K. R. (1993). Common Risk Factors in the Returns on Stocks and Bonds.
     Journal of Financial Economics, 33(1), 3–56.

[39] Carhart, M. M. (1997). On Persistence in Mutual Fund Performance. The Journal of Finance,
     52(1), 57–82.

[40] Fama, E. F., & French, K. R. (2015). A Five-Factor Asset Pricing Model. Journal of Financial
     Economics, 116(1), 1–22.

[41] Connor, G., & Korajczyk, R. A. (1988). Risk and Return in an Equilibrium APT: Application of
     a New Test Methodology. Journal of Financial Economics, 21(2), 255–289.

[42] Bai, J., & Ng, S. (2002). Determining the Number of Factors in Approximate Factor Models.
     Econometrica, 70(1), 191–221.

[43] Harvey, C. R., Liu, Y., & Zhu, H. (2016). . . . and the Cross-Section of Expected Returns. The
     Review of Financial Studies, 29(1), 5–68.

[44] Hansen, L. P. (1982). Large sample properties of generalized method of moments estimators.
     Econometrica, 50(4), 1029–1054.

[45] Hall, A. R., and Inoue, A. (2003). The large sample behaviour of the generalized method of
     moments estimator in misspecified models. Journal of Econometrics, 114, 361–394.

[46] Hall, A. R. (2005). Generalized Method of Moments. Oxford University Press.

[47] Newey, W. K., and McFadden, D. (1994). Large sample estimation and hypothesis testing. In R.
     F. Engle and D. L. McFadden (Eds.), Handbook of Econometrics, Vol. IV, 2111–2245. Elsevier.

[48] Andrews, I., Gentzkow, M., and Shapiro, J. M. (2017). Measuring the sensitivity of parameter
     estimates to estimation moments. Quarterly Journal of Economics, 132(4), 1553–1592.




                                                   25
Appendices

A      The M-factor Nested Factor model
                                                                                   k
                                                                                       
                              M −1                              df k = exp Fk Ωt +rt dW k ,
                              X                                    t            2          t
                     dxit =          βki dftk + deit   with                        i
                                                                                                          (48)
                                                                dei = exp Ai Ωt +ωt dB i ,
                              k=0                                  t           2         t

    where

    • the M time series (ftk )k∈J0,M −1K,t>0 are the factors, serving as “benchmarks" derived from the
      market. The series f represents the market itself, and (dft )t are frequently materialized as the
      returns of the S&P500 index. Conversely, for k > 0, dftk may depict returns from a specific
      industrial sector. These time series (ftk )k∈J0,M −1K,t>0 are uncorrelated;
    • βki represents the exposure of asset i to a factor df k ;
    • the time series (deit )i represent the residuals of each asset’s returns, signifying the portion of the
      asset’s returns not accounted for by market movements. These residuals are uncorrelated with
      the factors and are idiosyncratic to the asset itself;
    • Ωt is the log-volatility stochastic factor involved in the dynamics of both the factors (ftk )k∈J0,M −1K,t>0
      and the residuals (eit )i . rtk denotes the stochastic idiosyncratic log-volatility of factor f k , while
      ωti is the stochastic idiosyncratic log-volatility of residual ei ;
    • parameters γi ’s and Fk ’s quantify the contribution of each factor volatility mode. As discussed
      in[27], they can be estimated using correlation functions (denoted C f f and C rr in [27], note that,
      their dominant eigenvector provide a reliable initial estimate);
    • finally, Wtk and Bti are Brownian motions, all independent with each other.


B     The Log S-fBM model
In this Appendix, we will use the same notations as in [26].

The Log S-fBM model is a stochastic volatility model defined introduced in [26] whose dynamic is:
                                      (          ωH,T (t)
                                        dXt = e 2 dBt
                                                           ,                                   (49)
                                        X0 = x0

    where:

    • ωH,T (.) is the S-fBM process, a stationary Gaussian process with the following autocovariance
      function in Eq 2, and mean:
                                                         λ2
                                           µH,T = −             ;                               (50)
                                                    4H(1 − 2H)

    • B is a standard Brownian motion independent of ωH,T ;

    • λ > 0, H ∈]0, 1], and T > 0 are respectively the intermittency parameter, the Hurst exponent
      and the decorrelation parameter.




                                                              26
By construction, for any τ > 0, the S-fBM increment process (δτ ωH,T (t) := ωH,T (t +τ ) − ωH,T (t))t is
a stationary Gaussian process, centered and with variance v (τ, H) = E |δτ ωH,T (t)|2 expressed as:
                                                              τ 2H
                                         v (τ, ν, H) = ν 2             ,                                         (51)
                                                              T
                 2
where ν 2 = H(1−2H)
               λ
                    , which is a simple way to parametrize the S-fBM variance:

                                                                       ν2
                                      ∀t ≥ 0,     Var (ωH,T (t)) =        .
                                                                       2
For any interval K ⊂ R+ of length |K| such that |K| ≤ T and any sub-interval I ⊂ K, let us introduce
the integrated process:
                                           Z
                                         1
                                 Υ(I) :=      (ωH,T (u) − µH,T ) du,                            (52)
                                         λ I
and, for any t > 0 and 0 < ∆ ≤ T ,

                                          Υ∆ (t) := Υ([t, t + ∆]).                                               (53)

   In [26] it is established that:
Proposition 2 The process Υ∆ is a stationary centered Gaussian process, with the following covari-
ance structure:


                                                          ∆2            τ 2H                 
                                                                                            ∆
              ∀(t, s) ∈ R2+ ,   Cov (Υ∆ (t), Υ∆ (s)) =            − ∆2         g̃H                  ,
                                                       2H(1 − 2H)        T                  τ
                                                                                                                 (54)
                                       2H+2      2H+2
where τ = |t − s| and g̃H (z) := |1+z|      +|1−z|    −2
                                  2Hz 2 (1−(2H)2 )(2H+2)
                                                         .

Proof We fix ∆ > 0.
By definition, (ωH,T (t) − µH,T )t is a centered Gaussian process. Consequently, ΩH,T,∆ is a centered
Gaussian process too.

We suppose that t > s as they play symmetric roles.
We have:
                                       Z t+∆ Z s+∆
                                     1
              Cov (Υ∆ (t), Υ∆ (s)) = 2              Cov (ωH,T,∆ (t), ωH,T,∆ (s)) dudv
                                     λ t       s

By definition, we have :
      Z t+∆ Z s+∆                                                  Z t+∆ Z s+∆                         2H !
 1                                                        1                                |u − v|
                     Cov (ωH,T (t), ωH,T (s)) dudv =                              1−                            dudv
 λ2    t     s                                       2H(1 − 2H)        t      s               T

After some algebra, one has:
           Z t+∆ Z s+∆
         1                                                  ∆2             |τ + ∆|2H+2 − τ 2H+2
                        Cov  (ωH,T (t), ωH,T (s)) dudv =             −
        λ2 t       s                                     2H(1 − 2H) 2HT 2H (1 − (2H)2 )(2H + 2)
                        Z s+∆                                 Z t+∆                            
             1                               2H                                  2H
  −                             |u − s − ∆| (u − s − ∆)du +           |u − s − ∆| (u − s − ∆)du
    2HT 2H (1 − (2H)2 )   t                                      s+∆


                                                     27
By integrating the remaining term, we obtain:
     Z t+∆ Z s+∆
1                                                       ∆2        |τ + ∆|2H+2 − τ 2H+2 + |τ − ∆|2H+2 − τ 2H+2
                   Cov (ωH,T (t), ωH,T (s)) dudv =              −
λ2    t      s                                       2H(1 − 2H)           2HT 2H (1 − (2H)2 )(2H + 2)

Which leads to:
   Z t+∆ Z s+∆
 1                                                 ∆2        |τ + ∆|2H+2 − 2τ 2H+2 + |τ − ∆|2H+2
                Cov (ωH,T (t), ωH,T (s)) dudv =            −
λ2 t      s                                     2H(1 − 2H)       2HT 2H (1 − (2H)2 )(2H + 2)

     Thus, Υ∆ (.) is a stationary Gaussian process with the claimed autocovariance structure.
                                                                                                                  ■

                                                                                              
                                                                        Υ([0,∆]) Υ([τ,τ +∆])
Remark 1 We can derive the autocovariance CΥ (∆, τ ) := Cov                ∆    ,     ∆            for any ∆ > 0 as
follows:
                                                                                 
                                                 1        τ 2H              ∆
                               CΥ (∆, τ ) =            −         g̃H                                           (55)
                                            2H(1 − 2H)     T                  τ

C         The small intermittency approximation and intermittency bias es-
          timation
In this section, we first assess the accuracy of the small intermittency approximation used to compute
the covariance of the S-fBM. We then demonstrate how this approximation of the moments allows one
to control the bias in GMM estimation.

C.1       Accuracy of the small intermittency approximation
In the sequel, let K ⊂ R+ be an interval such that |K| ≤ T .

We consider the Multifractal random measure associated to the Log S-fBM model (49) as defined
in Eq . (4):
                                                    Z
                               ∀I ⊂ K, MH,T (I) := eωH,T (u) du.                         (56)
                                                              I

It can be seen as its integrated volatility over I. As well as its integrated counterpart over a period of
length ∆:

                                   ∀t ≥ 0,    M∆ (t) := MH,T ([t, t + ∆]).                                     (57)

    This appendix showcases the consistency of considering the small intermittency approximation up
to the order one in λ2 as used in the Log S-fBM calibration method of Wu et al. in Section 4 in [26].
Our goal is to control the error, in the small intermittency limit of the first order approximation for
any arbitrary I, J in K:

                                                                  λ2
                                                                Z                               
          MH,T (I)        MH,T (J)                                                1          1
Cov ln               , ln              ≃ λ2 Cov (Υ(I), Υ(J)) =            Cov       ωH,T (t), ωH,T (s)) dtds
             |I|             |J|                                |I||J| I×J        λ          λ
                                                                                                     (58)


                                                       28
where Υ(I) is defined in (52) in previous Appendix. We consider the case I = [0, ∆] and J = [τ, τ + ∆].
One has:
                     1  M∆ (t)  1  λ Υ∆ (t) 1 t+∆ ωH,T (u)−λ Υ∆ (t) 
                                                     Z
                       ln            = ln e ∆              e           ∆   du
                     λ        ∆        λ           ∆ t
                                       Υ∆ (t) 1  1 t+∆ ωH,T (u)−λ Υ∆ (t) 
                                                       Z
                                     =       + ln            e            ∆  du
                                         ∆     λ     ∆ t
We perform the second order series expansion of the latter quantity. We refer the reader to Kozhemyak
et al. [32] for the technical details and assumptions . Using the same notation as in Notation 2 in [32],
we have to the first order in λ:
                                                                     Υ∆ (t) 2
                                                        Z t+∆             
                         1  M∆ (t)  λ2 Υ∆ (t)       λ
                           ln            ≃         +            zu −          du
                         λ        ∆           ∆      2∆ t              ∆
                                                        Z t+∆
                                                                        Υ∆ (t)2
                                                                                
                                         λ2 Υ∆ (t)    λ          2
                                         ≃         +            zu du −
                                              ∆      2∆    t               ∆
                      ωH,T (u)−µH,T
where we set zu =            λ      .
Let                                                Z t+∆
                                                                      Υ∆ (t)2
                                        Θ∆ (t) =           zu2 du −
                                                    t                   ∆
and the associated autocovariance function:
                                        C(τ ) = Cov (Θ∆ (t), Θ∆ (t + τ )) .
If one uses previous expression, one has using Wick’s theorem (see [14]),
                                               Υ (t)              
                                                 ∆
                                ∀τ ≥ 0, Cov           , Θ∆ (t + τ ) = 0
                                                 ∆
    and it results that:
                                                                                λ2
                                                                        
            1  M∆ (t)  1  M∆ (t + τ )               Υ∆ (t) Υ∆ (t + τ )
     Cov                                       = Cov                                C(τ ) + o λ2
                                                                                                 
              ln         , ln                                  ,             +    2
            λ        ∆     λ         ∆                    ∆          ∆         4∆
In order to assess the small intermittency approximation quality one may estimate the following ratio:

                                                     λ2 C(τ )
                                        R(τ ) =
                                              4 Cov (Υ∆ (0), Υ∆ (τ ))
For the sake of simplicity, we consider the case H = 0 and τ = 0, where the analytical computation
can be carried out explicitly. In that case, one has
                          Z ∆                                        Z ∆
                                                  Υ∆ (0)2                         Υ∆ (0)2
                                                                                       
                                  2                                         2
              C(0) = Var         zu du + Var                − 2 Cov        zu du,
                              0                      ∆                  0           ∆
Thanks to Wicks theorem, it can be shown that previous expression reduces to
                                            C(0) = V1 + 2V22 − 2V3
with
         Z ∆                                                
                       T                      T            T
V1 = 4         (∆ − s) ln2   ds = ∆2 2 ln2         + 6 ln       +7
       0               s                      ∆            ∆
       Z ∆                                    
     2                 T                  T      3
V2 =       (∆ − s) ln       ds = ∆ ln          +
     ∆ 0               s                  ∆      2
       Z ∆Z ∆Z ∆ 
                                                                                      17 π 2
                                                                                     
     2                     T            T                    2     2  T          T
V3 =                ln           ln            ds du dv = ∆ 2 ln         + 6 ln     +   −      .
     ∆ 0 0 0            |s − v|      |s − u|                          ∆          ∆    3   9

                                                        29
This leads to the final expression for C(0):

                                             1 2π 2
                                                   
                                   C(0) =      +      ∆2 ≈ 2.36 ∆2
                                             6   9

Since
                                              Var (Υ∆ ) = V2 ,
for T = 5000 and ∆ = 1, V2 ≈ 10, and we finally estimate, when λ2 = 0.05,

                                            R(0) ≈ 0.003 = 0.3%

which is rather small. The exact computation of R(τ ) for other values of H and for any lag τ is
trickier. As illustrated in Figure 9, for any H, C(τ ) ≈ 0 when τ ≥ ∆. Moreover, one can see that
that R(τ ) decreases asH increases,
                                      as estimated
                                                        previously,
                                                                   is
                                                                      the worst case.    Therefore, the error
                               M∆ (t)           M∆ (t+τ )               Υ∆ (t) Υ∆ (t+τ )
by approximating Cov λ ln 1
                                 ∆
                                         1
                                       , λ ln     ∆          by Cov      ∆ ,      ∆       appears to be smaller
than 0.3 %.

                                                                                          H=0
                         0.25                                                             H = 0.05
                                                                                          H = 0.1

                         0.20
           R( ) (in %)




                         0.15


                         0.10


                         0.05


                         0.00
                                0   5              10             15             20              25



Figure 9: Numerical estimation of R(τ ) for H = 0, 0.05 and 0.1 for λ2 = 0.05, T = 5. 103 and ∆ = 1.
                       One can see that as soon as τ ≥ 2, R(τ ) is negligible.

    In Figure 9, we followed for the case H = 0 the simulation method explained in [32] with an
arbitrary small cut-off scale ℓ (see Eq. (7)). For strictly positive Hurst exponents, the simulation
method is similar to what has been performed in Section 6 as well as the numerical experiments of
[26].

C.2     The bias of the estimated intermittency coefficient
The GMM methodology employed to estimate the log-S-fBm parameters follows the framework orig-
inally proposed in [26]. For a sequence of time lags T ⊂ Nq , the estimator is constructed from the
empirical moments:                                              
                             KN (θ) = Ĉlog (k∆) − λ2 CΥ (∆, k∆)      ,
                                                                         k∈T


                                                        30
where Ĉlog is the empirical covariance function of the log-increments and CΥ is the analytical counter-
part derived under the small intermittency approximation as discussed previously.
   In this setting, the standard correctly specified moment condition E[KN (θ0 )] = 0 is replaced by a
population moment K(θ) = E[KN (θ)] that satisfies:
                                      K(θ0 ) = g(θ0 ),       where ∥g(θ0 )∥ = o(λ20 ).               (59)
This formulation aligns with the “non-local” misspecification framework discussed in [45, 46], where
the expected empirical moments depend systematically on the parameters. This is distinct from the
“local” misspecification analyzed by [19], which assumes the moment conditions vanish as N → ∞.
    The GMM estimator θ̂N is defined as the minimizer of the sample objective function:
                                             QN (θ) = KN (θ)′ WN KN (θ),
                                                                                         p
where {WN } is a sequence of positive definite weighting matrices such that WN →
                                                                               − W for some positive
definite matrix W . Under standard regularity conditions [44, 46], θ̂N converges in probability to the
pseudo-true parameter θ∗ :
                                 θ∗ = arg min Q(θ),      where Q(θ) = K(θ)′ W K(θ).
                                           θ∈Θ

     To control the asymptotic bias, we analyze the population first-order condition D(θ∗ )′ W K(θ∗ ) = 0,
where D(θ) = ∂K(θ)∂θ′ denotes Jacobian matrix. Assuming D(θ0 ) has full column rank, we perform a
first-order Taylor expansion of K(θ∗ ) around the true parameter θ0 :
                                           K(θ∗ ) = K(θ0 ) + D(θ̄)(θ∗ − θ0 ),
where θ̄ lies on the line segment connecting θ∗ and θ0 . Substituting K(θ0 ) = g(θ0 ) and the expansion
into the first-order condition, we obtain:
                                    θ∗ − θ0 = −(D(θ∗ )′ W D(θ̄))−1 D(θ∗ )′ W g(θ0 ).                 (60)
Notice that the same kind of computation was undertaken in the context of sensitivity analysis of the
GMM estimates in [48]. By the continuity of D(θ) and the consistency of the approximation, (60)
implies ∥θ∗ − θ0 ∥ = O(∥g(θ0 )∥). Leveraging the approximation bound from (59), we conclude:

                                                 λ̂2N −−−−→ λ20 + o(λ20 ).                           (61)
                                                         P
                                                      N →∞
This confirms that the estimator remains asymptotically valid within the small-intermittency regime,
as the approximation error is dominated by the magnitude of the intermittency parameter itself.


D     Proof of Theorem 1
This Section is devoted to the proof of Theorem 1 using the notations of Section 3.

We consider here any sub-intervals (I, J) ⊂ K 2 . We introduce the following notations:
                                                                          
                                          log                  Σ(I)       Σ(J)
                                       C     (I, J) := E   ln        ln
                                       Σ                   |I|   |J| 
                                      
                                      
                                        C (I, J) := E ln M|I|(I) ln M|J|
                                          log                                (J)
                                                                  
                                       Ci (I, J) := E Υi (I) Υi (J) , i ∈ J1, dK
                                      
                                      
                                                           |I| |J|

where Υi (I) := λ1i           ωui − µi du.
                      R               
                          I

    Beforehand, we need this intermediary result.

                                                               31
Lemma 1 For any sub intervals I and J of K, the following approximations holds:
     a)
                                                                d
                                                                X                                              
                        C   log
                                  (I, J) − C   log
                                                     (I, I) =         a2i λ2i (Ci (I, J) − Ci (I, I)) + o ||Λ||2 ,   (62)
                                                                i=1

     b)
                                                                d                                              
                        CΣlog (I, J) − CΣlog (I, I) =
                                                                X
                                                                      b4i λ2i (Ci (I, J) − Ci (I, I)) + o ||Λ||2 ,   (63)
                                                                i=1

      where ||.|| is the L2 norm in Rd and the tuples (ai )i∈J1,dK and (bi )i∈J1,dK are defined in the Section
3.
      Proof
     a) By straightforward computations, we have for any subintervals I and J of K of length T :
                                                                                
                  M (I)        M (J)               M (I) M (J)         M (I)        M (J)
             E          −1           −1     =E                   −E            −E            + 1.
                    |I|         |J|                 |I|   |J|            |I|          |J|
          By construction, ω is a gaussian process. Thus, using Fubini’s Theorem, we have:


                                                         (a2i −ai )νi2
                                             
                         E M (I) = E M (J) = e di=1
                                                     P
                                                              4
                             |I|           |J|
                                                               2
                                                             ν a2 −a
                                                                                                 .
                         E M (I) M (J) = 1 R R e di=1 i ( i2 i ) + di=1 a2i Cov(ωti ,ωsi ) dtds
                                                    P               P
                             |I|   |J|      |I||J| I J

          As a result, we obtain:
                                              d                 d
                                                 a2i − ai νi2 X a2i λ2i
                                                                   Z                      
               M (I)         M (J)           X                                          1 i 1 i
          E           −1           −1    =1+                 +                  Cov      ω , ω ) dtds
                 |I|           |J|                    2            |I| |J| I×J         λi t λi s
                                             i=1               i=1
                                                                        d
                                                                           a2i − ai νi2
                                                                                                    
                                                                      X
                                                               −2 −                     + 1 + o ||Λ||2 .
                                                                                2
                                                                                              i=1

          After some algebra, this leads to:
                                                 d
                                                    a2i λ2i
                                          X           Z                 
                   M (I)         M (J)                               1 i 1 i                  
              E          −1             −1     =               Cov      ωt , ωs dtds + o ||Λ||2 ,
                    |I|            |J|             |I| |J| I×J       λi     λi
                                                                i=1

          Using Proposition C.1 in [32], we have:
                                             Xd                         
                             M (I)        M (J)                  Υl (I) Υl (J)            
                     E ln             ln          =    2 2
                                                      al λ l E                   + o ||Λ||2 .
                              |I|           |J|                   |I|    |J|
                                                                        l=1

          In particular, we have:
                                           Xd                          
                              M (I)     M (I)                   Υl (I) Υl (I)            
                      E ln           ln         =   a2l λ2l E                   + o ||Λ||2 ,
                                |I|      |I|                     |I|    |I|
                                                                        l=1

          which leads to the desired result by substracting the two previous equalities.


                                                                       32
b) Given two arbitrary sub-intervals I and J of K, we have
                                              X
                               Σ (I) Σ (J) =       b2l b2s M l (I) M s (J) .
                                                            1≤l,s≤d


   For any (l, s) ∈ J1, dK2 , we have:


                                          M l (I) M s (J)
                                                                   Z
                                                                          dxdy  ωxl +ωys 
                                  E                              =               E e        .
                                           |I|     |J|                I×J |I||J|


   We have for any (x, y) ∈ I × I:
                                                  1 P
                               l s
                            E eωx +ωy = eµl +µl + 2 (s,l)∈{l,s} λs λl ρs,l (|x−y|) ,

   where:
                                                                                           
                                                                                  τ Hi +Hj
                                                      1
                                                                                                 if i=j
                                                                                    
                                        
                                            (Hi +Hj )(1−Hi −Hj )         1−       T
                          ρi,j (τ ) =                                                                        .
                                        0                                                       otherwise

   Which gives after some algebra:
                                                      
                               E ewHl ,T (x)+wHs ,T (y) = eλl λs ρl,s (|x−y|) .

   By denoting the functional:
                                                 ψ : (λl , λs ) 7→ eλl λs ρl,s (|x−y|) ,
   we perform a first order Taylor expansion:
                                     D             E 1D                     E         
             ψ (λl , λs ) = ψ(0R2 ) + ∇λd =0R2 ψ, λ +   Hess (ψ) |λ=0R2 λ, λ + o ||λ||2 ,
                                                      2
   Where                                                                     
                                                                         λl
                                                            λ=
                                                                         λs
   and Hess (.) is the Hessian operator.

   We get:
                                                                                                    
                                                                                                 2
                                  ψ (λl , λs ) = 1 + λl λs ρl,s (|x − y|) + o ||λ||                      .

   Thus, we conclude that:

                                                               
                      
                          M l (I) M s (J)
                                                  1 + o ||λ||2            if l ̸= s
                  E                              =                                           .
                            |I|     |J|            1 + λ2 E Υl (I) Υl (J) + o ||λ||2   if l = s
                                                         l     |I|   |J|




                                                               33
     As a result, we obtain:
                                        d                                                  
                    Σ (I) Σ (J)           X                                Υl (I) Υl (J)                   X                           
            E                         =         b4l       1 + λ2l E                                  +                b2l b2s + o ||Λ||2 ,
                     |I| |J|                                                |I|    |J|
                                          l=1                                                            1≤l̸=s≤d


     which can be rewritten as:
                                                d                                                d
                                                                                                                 !2
                            Σ (I) Σ (J)           X                       Υl (I) Υl (J)              X                         
                    E                         =           b4l λ2l E                              +         b2l        + o ||Λ||2 .
                             |I| |J|                                       |I|    |J|
                                                  l=1                                                l=1

     Thus, we obtain:
                                                            d                                                 d
                                                                                                                                     !2        d
                    Σ (I)             Σ (J)                       X                        Υl (I) Υl (J)              X                        X
           E              −1                −1                =            b4l λ2l E                           +               b2l        −2              b2l
                     |I|               |J|                                                  |I|    |J|
                                                                  l=1                                                 l=1                       l=1
                                                                                                                                         
                                                                                                                         +1 + o ||Λ||2 .

     Using the Proposition C.1 in [32], we have:
                                 Xd                                                                        d
                                                                                                                               !2             d
                    Σ (I)     Σ (J)        4 2      Υl (I) Υl (J)                                                  X                          X
               E ln        ln         =   bl λl E                   +                                                    b2l          −2            b2l
                     |I|       |J|                   |I|    |J|
                                                                l=1                                                l=1                        l=1
                                                                                                                                     
                                                                                                                      +1 + o ||Λ||2 .

     In particular, we have:
                                 Xd                                                                        d
                                                                                                                               !2             d
                    Σ (I)     Σ (I)        4 2      Υl (I) Υl (I)                                                  X                          X
               E ln        ln         =   bl λl E                   +                                                    b2l          −2            b2l
                     |I|       |I|                   |I|    |I|
                                                                l=1                                                l=1                        l=1
                                                                                                                                    
                                                                                                                      +1 + o ||Λ||2 ,

     which leads to the desired result by substracting the two previous equalities again.


                                                                                                                                                                       ■
   Now, we proceed to the proof of Theorem 1. We denote:
                            (
                              C log (∆, τ ) := C log ([0, ∆], [τ, τ + ∆])
                                                                                                                                                                (64)
                                          CΣlog (∆, τ ) := CΣlog ([0, ∆], [τ, τ + ∆])

   and for any i ∈ J1, dK:

                                              Ci (∆, τ ) := Ci ([0, ∆], [τ, τ + ∆]).                                                                            (65)

We denote as well for any t ≥ 0: M∆ (t) := M ([t, t + ∆]).

  a) After some algebra, one has:
                                                                                          
                                                                                M∆ (τ )
                                  W (τ, ∆, Λ) = 2var ln                                          − 2C log (∆, τ ) .
                                                                                 ∆

                                                                          34
   Consequently, we get using Theorem 1:
                                            d
                                            X 2a2 λ2                                               
                     W (τ, ∆, Λ) =                      i   i
                                                                 (Ci (∆, 0) − Ci (∆, τ )) + o ||Λ||2 .
                                                    ∆2
                                             i=1

   After some algebra, we obtain:
                       d
                       X               |τ + ∆|2Hl +2 − 2τ 2Hl +2 + |τ − ∆|2Hl +2 − 2|∆|2Hl +2     
                                                                                                         2
                                                                                                           
       W (τ, ∆, Λ) =         a2l λ2l                                                          + o   ||Λ||    .
                                                ∆2 Hl T 2Hl (1 − (2Hl )2 )(2Hl + 2)
                       l=1


   Consequently, we get:
                                               d                   τ 2Hl                     
                                               X                                            ∆                
                         W (τ, ∆, Λ) =                  a2l λ2l                   gHl               + o ||Λ||2 ,
                                                                      T                     τ
                                                  l=1

   where the function gH (.) is defined in (22).

   This leads to:
                                                                d                τ 2Hl                   
                                                                X                                       ∆
                                       W (τ, ∆, Λ) =                  a2l λ2l               gHl                 .
                                                                                  T                     τ
                                                                l=1


b) This part is analogous to the previous one. We have:
                                                        
                                                  Σ∆ (τ )        log
                          V (τ, ∆, Λ) = 2var ln              − 2CX   (∆, τ ) .
                                                    ∆

   Consequently, we get using Theorem 1:
                                            d
                                            X 2b4 λ2                                              
                       V (τ, ∆, Λ) =                    i   i
                                                                (Ci (∆, 0) − Ci (∆, τ )) + o ||Λ||2 .
                                                    ∆2
                                            i=1

   After some algebra, we obtain:
                                               d                   τ 2Hl                     
                                               X                                            ∆                
                         V (τ, ∆, Λ) =                  b4l λ2l                   gHl               + o ||Λ||2 ,
                                                                      T                     τ
                                               l=1

   where the function gH (z) is defined in (22).

   This leads to:
                                                            d                    τ 2Hl                   
                                                            X                                           ∆
                                       V (τ, ∆, Λ) =                  b4l λ2l               gHl                 .
                                                                                 T                      τ
                                                                l=1


                                                                                                                    ■




                                                                  35
E     Hurst exponent estimation from moment scaling
In order to measure the Hurst exponent HX associated with some given process X(t) we can refer to
the method used in [25] that simply consists in estimating the scaling exponent of various moment
of the increments of the process δτ X(t) = X(t + τ ) − X(t). In the case when X(t) = ln Σ∆ (t), the
increment process is simply δτ ln Σ∆ (t) = ln Σ∆ (t + τ ) − ln Σ∆ (t). We have seen that, at the first order
in ||Λ||2 , its moments m(q, τ, ∆) = E (|δτ ln Σ∆ (t)|q ) correspond to the moments a Gaussian process
and therefore one has:
                                                                
                                                − 21 2q        1               q
                          m(q, τ, ∆) = π 2 Γ q +                   V (τ, ∆, Λ) 2 ,                      (66)
                                      ||Λ||2 ≪1                2

                                                           +∞
where V (τ, ∆, Λ) is defined in Section 3 and Γ (x) =           sx−1 e−s ds, x > 0 while               indicates that
                                                           R
                                                                                              =
                                                           0                               ||Λ||2 ≪1
equality holds in the first order when ||Λ||2 → 0).

There, if As there exists a constant C > 0 such that:

                                            V (τ, ∆, Λ) = Cτ 2HX ,

HX can be identified from the slope of the linear regression of ln (m(q, τ, ∆)) against ln(τ ).

Besides, if for any l ∈ J1, dK, Hl ̸= 0, we have the following Taylor expansion:
                                                      1
                                                              + o z 2Hl                                         (67)
                                                                        
                                    gHl (z) =
                                                Hl (1 − 2Hl )

    Consequently, if one supposes for instance that:
                              (
                                ∃c > 0, ∀i ∈ J1, dK such that b2i λi = c,
                                  H1 ≪ H2 ≪ · · · ≪ Hd

    The Eq. (21) can be simplified as follows in the high frequency limit (∆ ≪ τ ):

                                                           τ 2H1
                                       V (τ, ∆, Λ) ≈                 .
                                                       H1 (1 − 2H1 )

Leading to:
                                                 HX ≈ H1 .
    The latter result infers that in the high frequency limit, we observe only the regularity of the pro-
cess X i with the smallest Hurst exponent through the aggregated process X.




F    Proof of Eq. (38)
By definition, one has for any z ∈]0, 1[:
                                                           (z+1)2 ln(z+1)+(−1+z)2 ln(1−z)−2z 2 ln(z)
                         g0 (z)                                               z2
              r0,H (z) =        = H(1 − (2H)2 )(2H + 2)       |1+z|2H+2 −2|z|2H+2 +|1−z|2H+2 −2
                                                                                                     .
                         gH (z)                                                 2
                                                                              z


                                                      36
                                    2H+2 −2|z|2H+2 +|1−z|2H+2 −2
For any H ∈ 0, 12 , hH : z 7→ |1+z|                              is a decreasing function in ]0, 1[. As a
                
                                               z2
result:

                               ∀z ∈]0, 1[,      hH (z) > hH (1) = 4(22H − 1)

On the other hand, one has:
                                                                           2       3
                                                (
                                                    ln (1 + z) ≤ z − z2 + z3
                              ∀z ∈]0, 1[,                                      2       3
                                                    ln (1 − z) ≤ −z − z2 − z3

For any z ∈]0, 1[, one has after some algebra:

                                                    z2
                                 g0 (z) ≤ 3 −          − 2 ln(z) ≤ 3 − 2 ln(z)
                                                    2
Consequently, the following holds:

                                       H(1 − 2H)(1 + 2H)(H + 1)
                          r0,H (z) ≤                            (3 − 2 ln(z))
                                              2(22H − 1)

Which ends the proof.
                                                                                                            ■


G     Proof of Proposition 1
Let us define the increment operator δτ acting on an arbitrary stochastic process xt as follows:

                                      ∀(τ, t) ∈ K 2 ,     δτ xt := xt+τ − xt .

Starting from the N-SfFM in Eq. (8), we have for any τ ∈ K:

                                  ∀i ∈ J1, Ns K,        δτ xit = βi δτ ft + δτ eit ,                 (68)

where:
                                                R t+τ i
                                              i
                                         δτ xt = t dxs
                                         
                                         
                                                R t+τ Ωs
                                          δτ ft = t e 2 dWs             .
                                                                i
                                         δ ei = R t+τ e γi Ωs2+ωs dB i
                                         
                                         
                                           τ t    t                  s

We consider the two optimal least square solutions:
                                      
                                       δd
                                         τ f t := arg min ||δτ Xt − βf ||
                                                     f ∈R
                           ∀t ∈ K,                                         ,                         (69)
                                       fbt := arg min ||Xt − βf ||
                                      
                                                         f ∈R


where ||.|| is the L2 norm in RNs .

It is straightforward to see that the ordinary least squares solutions of Eq. (45) are linked as follows.

                                                    δd
                                                     τ f t = δτ ft .
                                                                b                                    (70)


                                                          37
We have timewise the following ordinary least square solution:
                                                                                            PN
                                                                                                 i=1   βi δτ xit
                                                          ∀t ∈ K,                δd
                                                                                  τft =            N
                                                                                                                       .
                                                                                                           2
                                                                                                 P
                                                                                                      i=1 βi

For the sake of simplicity, we denote: h := PN1                                   2    .
                                                                             i=1 βi


As a result, we obtain:
                                                                             N                          ′             ′′
                                                            2    2
                                                                             X
                                                         δd
                                                          τft = h                      βk′ βk′′ δτ xkt δτ xkt .
                                                                          k′ ,k′′ =1

Given that for any i ∈ J1, N K,                      δτ xit = βi δτ ft + δτ eit , we have:
                      N                              ′   2          N                                         ′                   ′′ 
            2         X                                             X                     
         δd
          τft =               h2 βk2′       δτ xkt            +                 h2 βk′ βk′′ βk′ δτ ft + δτ ekt    βk′′ δτ ft + δτ ekt .
                      k′ =1                                       k′ ̸=k′′ =1

We obtain:
                                                                                                                                                 
                                                                    N                        ′   2                N
                                                    2               X                                             X                         2
                                                 δd
                                                  τft =                    h2 βk2′ δτ xkt             +                       h2 βk′ βk′′         (δτ ft )2
                                                                     ′
                                                                    k =1                                        k′ ̸=k′′ =1
           N
           X                                             ′′
                                                                   N
                                                                   X                                        ′
                                                                                                                           N
                                                                                                                           X                          ′    ′′
                      h2 βk2′ βk′′ δτ ft δτ ekt +                            h2 βk′ βk2′′ δτ ft δτ ekt +                         h2 βk′ βk′′ δτ ekt δτ ekt .
        k′ ̸=k′′ =1                                           k′ ̸=k′′ =1                                          k′ ̸=k′′ =1

    As the previous equality is valid for any t and τ , considering a subdivision (tk )k∈J1,nK with time
step θ := tn −t
             n
               0
                 of an arbitrary sub interval I ⊂ K.

By definition, we have:
                                                    
                                                      Pn               2
                                                                               P
                                                    
                                                      l=1   δtl xitl−1 −−−→ xi I
                                                                              θ→0
                                                    
                                                    
                                                    
                                                     Pn                2 P
                                                       l=1 δtl ftl−1       −−−→ ⟨f ⟩I
                                                    
                                                    
                                                  2                          θ→0
                                 ∀(i, j) ∈ J1, N K , P                                                                                 .
                                                       n                   i       P
                                                          δ   f      δ  e       −−−→ f, ei I
                                                     l=1 tl tl−1 tl tl−1 θ→0
                                                    
                                                    
                                                    
                                                     nl=1 δtl eit δtl ejt −−P−→ ei , ej
                                                    
                                                     P
                                                                  l−1       l−1              I                  θ→0

   Given that B and B j are independent from B i for any i ̸= j ∈ J1, N K2 , we have that:

                                        ∀i ̸= j ∈ J1, N K,                        f, ei I = 0,                  ei , ej I = 0.

This means that
             D ′ Ethe right
                       P hand side of the previous         equation converges in probability as θ → 0 to:
PN                         N                      2
  k′ =1
         2 2
        h βk′ xk    +      k′ ̸=k′′ =1
                                        2
                                       h βk′ βk′′     ⟨f ⟩I .
                         I

On the other hand, we have using Eq. (70):
                                                              n 
                                                              X                       2       D E
                                                                                           −−−→ fˆ ,
                                                                                             P
                                                                         δd
                                                                          tl f tl−1
                                                                                           θ→0              I
                                                              l=1


                                                                                      38
and by the almost sure uniqueness of the limit in probability, we conclude that:

                                                                                                        
                          D E   N        D ′E    N
                                X                X                                                  2
                           fb =   h2 βk2′ xk  +                                    h2 βk′ βk′′           ⟨f ⟩ .
                                                                                                              I          (71)
                                 I   ′
                                                            I         ′    ′′
                                     k =1                          k ̸=k =1

On the other hand, starting from this identity:
                                                                                    N
                                                                                    X
                                     ∀(t, τ ) ∈ R2+ ,       δd
                                                             τ f t = δτ ft +               pi δτ eit .
                                                                                     i=1

where pi = PβNi σi 2 for i ∈ J1, N K.
               i=1 βi
Using the same convergence in probability arguments, we end up with:
                                         D E          N
                                                      X
                                          ˆ
                                          f = ⟨f ⟩I +   p2i ei I ,                         a.s.
                                             I
                                                                i=1

Using the strong law of large numbers, we have that:
                                   D E
                                     fˆ = ⟨f ⟩I + o                             (1) , a.s.
                                                  I               N →∞

    By injecting the latter in Eq. (71), we obtain after some algebra that:
                                                                                    N
                        D E                             1                           X          D ′E
                         fˆ     ∼            P                               2
                                                                                           βk2′ xk  ,             a.s,
                              I N →∞ h−2 −        N                                                       I
                                                  k′ ̸=k′′ =1
                                                                βk′ βk′′             ′
                                                                                    k =1

from which the claimed result derives.
                                                                                                       ■
We dedicate the end of this appendix in discussing Eq. (44). Quantitatively speaking, the assumption
over the exposure vector β in Proposition 1 can be restricted to considering its entries with absolute
continuous entries with respect to the Lebesgue measure as no entry of β in that case will charge an
atom, in particular 0. Thus, the denominator in Eq. (44) will almost surely not vanish.



H     Numerical Miscellanea
H.1      Gaussian trick
We consider a noisy Gaussian random variable:

                                                        Y = X + ϵ,

where X ∼ N (0, 1) and ϵ a random noise.


    To better reconstruct the distribution of X from Y , we consider X̃ as a proxy of X defined as
follows:

                                                  X̃ := F −1 (Fy (Y )) ,                                                 (72)

where:

                                                                39
                                  2
                        − t2
                    Rx
   • F (x) = √12π   −∞ e     dt the distribution function of a standard Gaussian random variable;

   • Fy (x) = P (Y ≤ x) the distribution function of Y .

Here is an example of such a reconstruction using the empirical distribution function of Y as a proxy
of Fy .

                               0.40                                           X
                               0.35                                           Y
                               0.30                                           X
                               0.25
                     Density




                               0.20
                               0.15
                               0.10
                               0.05
                               0.00
                                      4     2          0        2         4
                                                       x
  Figure 10: The true Gaussian density X (green), the perturbated Gaussian Y (orange) and the
 Gaussianized random variable’s density X̃ (blue), for both of which, we perform a Gaussian kernel
density estimator. Here we considered a sample of 104 drawn from N (0, 1) as X and a noise ϵ drawn
                                          from N (0, 0.7).


H.2    Empirical distributions of β and σ entries
Using empirical daily data from YahooFinance as in Section 7.2 spanning from 01/01/1994 to 01/01/2026
for 243 US stocks of the S&P500 throughout the entire period, we find that a leptokurtic distribution
fits well the observed histogram of the empirical distribution of the exposures. The latter exposures
are calibrated following Step 1 in Section 5 (see Eq. (43)).




                                                  40
                                                  Distribution of Exposures
                           5         Distribution
                                     Fitted Beta Distribution
                                       =13.29, =10.77
                           4

                           3
                 Density




                           2

                           1

                           0   0.2          0.3        0.4           0.5      0.6     0.7
                                                                 x
     Figure 11: The empirical distribution of the β entries (blue) together with the fitted beta
                                         distribution (red).

    On the other hand, to build intuition for the empirical distributions of σ entries, we conduct a
similar analysis by regressing the asset returns of the S&P500 stocks spanning the same period and
retrieve the calibrated entries of σ via Eq. (46) through their identification as the square root of the
variance of the residuals. It turns out that they also fit a leptokurtic distribution.


                                                       Distribution of
                           8         Distribution
                                     Fitted Beta Distribution
                           7           =25.17, =5.40
                           6
                           5
                 Density




                           4
                           3
                           2
                           1
                           0     0.70         0.75      0.80         0.85   0.90    0.95
                                                                 x
     Figure 12: The empirical distribution of the σ entries (blue) together with the fitted beta
                                         distribution (red).

   The following figure displays the empirical distribution of the ratio’s entries of βσ across all the

                                                                41
considered assets. This aims to better illustrate empirically the condition of Eq. (32).


                                                Distribution of
                        25

                        20

                        15
                Count




                        10

                        5

                        0    0.2        0.4        0.6             0.8       1.0
                                                         x

                        Figure 13: The empirical distribution of the βσ entries (blue).

   The latter figure shows values of the ratio being mainly concentrated around (0.4 − 0.9), meaning
that the condition of Eq. (32) is widely satisfied for the considered single stocks of the S&P500. The
few exceptions we observe where the ratio σβii exceeds 1 correspond likely to stocks having a behavior
similar to an index as emphasized in Section 4.2.


I   Yahoo Finance S&P500 asset nomenclature of Figure 7

                         Ticker    Company Name                   Sector
                          MO       Altria Group                   Consumer Staples
                         AMAT      Applied Materials              Information Technology
                         HBAN      Huntington Bancshares          Financials
                          VLO      Valero Energy                  Energy
                          SPG      Simon Property Group           Real Estate
                          ADI      Analog Devices                 Information Technology
                         AMGN      Amgen                          Health Care
                         LRCX      Lam Research                   Information Technology
                          AEP      American Electric Power        Utilities




                                                      42