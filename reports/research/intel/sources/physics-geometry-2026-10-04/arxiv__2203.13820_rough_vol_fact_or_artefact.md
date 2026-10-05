source: https://arxiv.org/pdf/2203.13820
fetched_utc: 2026-10-04T18:36:18Z
bytes_raw: 1077001

Rough volatility: fact or artefact?
                                                                                   Rama Cont
                                                                    Mathematical Institute, University of Oxford
                                                                                 Purba Das∗
                                                               Department of Mathematics, University of Michigan †
                                                                                          July 11, 2023
arXiv:2203.13820v3 [q-fin.ST] 10 Jul 2023




                                                                                             Abstract
                                                      We investigate the statistical evidence for the use of ‘rough’ fractional processes with Hurst
                                                  exponent H < 0.5 for modeling the volatility of financial assets, using a model-free approach.
                                                  We introduce a non-parametric method for estimating the roughness of a function based on
                                                  discrete sample, using the concept of normalized p-th variation along a sequence of partitions.
                                                  Detailed numerical experiments based on sample paths of fractional Brownian motion and
                                                  other fractional processes reveal good finite sample performance of our estimator for measur-
                                                  ing the roughness of sample paths of stochastic processes. We then apply this method to
                                                  estimate the roughness of realized volatility signals based on high-frequency observations. De-
                                                  tailed numerical experiments based on stochastic volatility models show that, even when the
                                                  instantaneous volatility has diffusive dynamics with the same roughness as Brownian motion,
                                                  the realized volatility exhibits rough behaviour corresponding to a Hurst exponent significantly
                                                  smaller than 0.5. Comparison of roughness estimates for realized and instantaneous volatility
                                                  in fractional volatility models with different values of Hurst exponent shows that, irrespective
                                                  of the roughness of the spot volatility process, realized volatility always exhibits ‘rough’ be-
                                                  haviour with an apparent Hurst index H    b < 0.5. These results suggest that the origin of the
                                                  roughness observed in realized volatility time-series lies in the estimation error rather than the
                                                  volatility process itself.

                                                Keywords— roughness, variation index, p-th variation, realized volatility, instantaneous volatility,
                                            fractional Brownian motion, Hurst exponent, high-frequency data




                                              ∗
                                                Email: purbadas@umich.edu
                                              †
                                                We thank Peter Friz, James-Michael Leahy, Mathieu Rosenbaum and Alexander Schied for helpful comments
                                            and discussions.


                                                                                                  1
Contents
1 Introduction                                                                                               3
  1.1 Fractional processes in finance: from long-range dependence to ‘rough volatility’ . . . . . .          3
  1.2 Contribution . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .   4

2 Measuring the roughness of a path                                                                           5
  2.1 p-th variation and roughness index of a path . . . . . . . . . . . . . . . . . . . . . . . . . .        5
  2.2 Normalized p-th variation . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .     6
  2.3 Estimating roughness from discrete observations . . . . . . . . . . . . . . . . . . . . . . . .         7
  2.4 Finite sample behaviour of the roughness estimator . . . . . . . . . . . . . . . . . . . . . . .        8

3 Spot volatility and realized volatility                                                                    12

4 Numerical experiments                                                                                    14
  4.1 Stochastic volatility diffusion models . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 14
  4.2 A fractional Ornstein-Uhlenbeck model . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 21

5 Application to high-frequency financial data                                                              24
  5.1 AAPL . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 24
  5.2 SP500 . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 24

6 Rough volatility ... or estimation error?                                                                  26




                                                      2
1         Introduction
1.1         Fractional processes in finance: from long-range dependence to
            ‘rough volatility’
Beginning with Mandelbrot and Van Ness (1968), fractional Brownian motion and fractional Gaussian
noise have been used as building blocks of stochastic models of various phenomena in physics, engineering
(Lévy-Véhel et al., 2005) and finance (Baillie et al., 1996; Bollerslev and Ole Mikkelsen, 1996; Comte
and Renault, 1998; Cont, 2007; Gatheral et al., 2018; Rogers, 1997; Willinger et al., 1999). Fractional
Brownian motion has two remarkable properties which have contributed towards its adoption as a building
block in stochastic models: first, its ability to model long-range dependence, as measured by the slow decay
∼ T 2H−2 of auto-correlation functions of increments, where 0 < H < 1 is the Hurst exponent; second, its
ability to generate trajectories which have varying levels of Hölder regularity (‘roughness’). The former
is a property that manifests itself over long time scales while the latter manifests itself over short time
scales and, in general, these two properties are unrelated. But in the case of fractional Brownian motion,
the two properties are linked through self-similarity and governed by the Hurst exponent 0 < H < 1:
for H > 1/2 one obtains long-range dependence in increments and trajectories smoother than Brownian
motion while for H < 1/2 one obtains ‘anti-correlated’ increments and trajectories rougher than Brownian
motion1 . Processes driven by fractional Gaussian noise with H < 1/2 are thus sometimes referred to as
‘rough processes’.
    In early applications to financial data (Baillie et al. (1996); Bollerslev and Ole Mikkelsen (1996); Comte
and Renault (1998); Willinger et al. (1999)), fractional processes were adopted in order to model long range
dependence effects in financial time series Cont (2005). More specifically, statistical evidence of volatility
clustering Cont (2007) - positive dependence of the amplitude of returns over long time scales - led to the
development of stochastic volatility models driven by fractional Brownian motion. A well-known example
of such a fractional stochastic volatility model is the one proposed by Comte and Renault (1998) who
modelled the dynamics of the (instantaneous) volatility σ(t) of an asset as:
                                   Y (t) = ln σ(t)      dY (t) = −γY (t)dt + θdB H (t)                       (1)
where B H is a fractional Brownian motion (fBM) with Hurst exponent H. This long-range dependence in
volatility is modelled by choosing 1 > H > 1/2 (Comte and Renault (1998); Bollerslev and Ole Mikkelsen
(1996); Breidt et al. (1998); Hurvich et al. (2005); Lahiri and Sen (2020)).
    A recent strand of literature, starting with Gatheral et al. (2018), has suggested the use of fractional
Brownian models with H < 1/2 for modelling volatility. Unlike previous studies based on auto-correlations
of various volatility estimators over long time scales (Baillie et al., 1996; Bollerslev and Ole Mikkelsen, 1996;
Cont, 2005), Gatheral et al. (2018) rely on the analysis of the behaviour of volatility estimators over short
intraday time scales in order to assess the ‘roughness’ of these signals and concluded that volatility is
‘rough’ i.e. has paths with a Hölder regularity which is strictly less than 1/2, suggest to use stochastic
models with sample paths rougher than Brownian motion.
    However, it has not been lost on experts working in this area that previous estimation results for
fractional models in the literature on long-range dependence in volatility, pointed towards Hurst exponents
H > 0.5 (and around 0.55) (Baillie et al., 1996; Comte and Renault, 1998; Lahiri and Sen, 2020)while
the recent ‘rough volatility’ literature indicates Hurst exponents much smaller than 0.5 and closer to 0.1.
Together with the well-known statistical issues plaguing the estimation of Hurst exponents (Beran, 1994;
Rogers, 2019), these conflicting results call for a critical examination of the empirical evidence for ‘rough
volatility’.
    Compounding this issue is the fact that (spot) volatility is not directly observed but estimated from
price series, with an inherent estimation error which has been the subject of many studies (Barndorff-
Nielsen and Shephard, 2002; Jacod and Protter, 2012; Lahiri and Sen, 2020). This estimation error is far
    1
        Incidentally, Hurst and Hölder happen to have the same initials, adding to the confusion...


                                                             3
from i.i.d.: it is known to possess path-dependent features (see Jacod and Protter (2012)). As a result,
measures of roughness for realized volatility indicators may be quite different from those of the underlying
‘spot volatility’. This is simply because the convergence of high-frequency volatility estimators in Lp
norms does not imply in any way their functional convergence in Hölder norms or other norms related to
roughness.
    As already pointed out by Rogers (1997), these two properties, namely the short-range behaviour
which determines the roughness of the path, and the long-range dependence property, can (and should) be
modeled through different mechanisms. Bennedsen et al. (2022) discuss several such approaches.
    The focus of the literature on parametric models based on fractional Brownian motion or fractional
Gaussian noise concentrates these two, very different, properties in a single parameter: the Hurst exponent
H (Bolko et al., 2022; Fukasawa et al., 2022; Gatheral et al., 2018). Such parametric approaches proceed
as follows: one estimates a parametric model for volatility dynamics based on some fractional Gaussian
driving noise with Hurst exponent 0 < H < 1 using a MLE (Fukasawa et al., 2022) or method of moments
(Bolko et al., 2022). Then, based on the estimated value of this parameter H, one concludes that “volatility
is rough” if Ĥ < 0.5.
    The validity of such approaches hinges on the assumption that the class of models used is well-specified.
As pointed out by Bennedsen et al. (2022), this is unlikely to be the case for SDEs driven by fractional
Gaussian noise if one wants to accommodate both (long-range) dependence properties and (short-range)
roughness properties.
    To avoid this caveat, we propose a model-free non-parametric method which focuses solely on the
roughness properties of sample paths. Although less ambitious in its scope -we only focus on roughness
properties rather than developing a full model for volatility dynamics- our approach is robust to the
specification errors and estimation biases which plague parametric methods.


1.2     Contribution
We address these questions in detail by re-examining the statistical evidence from high-frequency financial
data in an attempt to clarify whether the assertion that ‘volatility is rough’ (i.e. rougher than typical paths
of Brownian motion) is supported by empirical evidence. We investigate the statistical evidence for the
use of ‘rough’ fractional processes with Hurst exponent H < 0.5 for the modelling of volatility of financial
assets, using a non-parametric, model-free approach.
    We introduce a non-parametric method for estimating the roughness of a function/path based on
a (high-frequency) discrete sample, using the concept of normalized p-th variation along a sequence of
partitions, and discuss the consistency of our estimator in a pathwise setting. We investigate the finite
sample performance of our estimator for measuring the roughness of sample paths of stochastic processes
using detailed numerical experiments based on sample paths of fractional Brownian motion and other
fractional processes. We then apply this method to estimate the roughness of realized volatility signals
based on high-frequency observations. Through a detailed numerical experiment based on a stochastic
volatility model, we show that even when the instantaneous (spot) volatility has diffusive dynamics with
the same roughness as Brownian motion, the realized volatility exhibits rough behaviour corresponding to a
Hurst exponent significantly smaller than 0.5. Similar behavior is observed in financial data as well, which
suggests that the origin of the roughness observed in realized volatility time-series lie in the estimation error
rather than the volatility process itself. Comparison of roughness estimates for realized and instantaneous
volatility in fractional volatility models for different values of Hurst parameter H shows that whatever the
value of H for the (spot) volatility process, realized volatility always exhibits ‘rough’ behaviour.
    Our results are broadly consistent with the observations by Rogers (2019), but we pinpoint more
precisely the origin of the apparent ‘rough’ behaviour of volatility as being the estimation error inherent in
the estimation of realized volatility (sometimes known as microstructure noise). In particular, our results
question whether the empirical evidence presented from high-frequency volatility estimates supports the
‘rough volatility’ hypothesis.


                                                       4
2      Measuring the roughness of a path
Determining the roughness of realized volatility from a sample path plays a crucial role in model specifi-
cation Gatheral et al. (2018); Fukasawa et al. (2022). In practice, we observe only a single price path so
one is faced with the problem of determining the roughness of a process from a single price path sampled
at high frequency. We present in this section several concepts for measuring the roughness of a path and
discuss how they may be used to design estimators from high-frequency observations.


2.1      p-th variation and roughness index of a path
Consider a sequence of partitions π = (π n )n≥1 of [0, T ] where
                                                                          
                               π n = 0 = tn0 < tn1 < · · · < tnN (πn ) = T                                                    (2)

represents observation times ‘at frequency n’. We denote N (π n ) to be the number of intervals in the
partition π n . Denote respectively by |π n | = supi=1,··· ,N (πn ) |tni − tni−1 |, and π n = inf i=1,··· ,N (πn ) |tni − tni−1 |,
the size of the largest and the smallest interval of π n . In this paper, we will always assume
                                                                                        n→∞
                                           |π n | =         sup           |tni − tni−1 | → 0.
                                                      i=1,··· ,N (π n )

    The concept of p-th variation along a sequence of partitions π = (π n )n≥1 with 0 = tn0 < ... < tnk < ... <
tnN (πn ) = T is defined following Cont and Perkowski (2019):

Definition 1. (p-th variation along a sequence of partitions) x ∈ C 0 ([0, T ], R) has finite p-th variation
                                                                                                        (p)
along the sequence of partitions π = (π n , n ≥ 1) if there exists a continuous increasing function [x]π :
[0, T ] → R+ such that
                                                                       p n→∞
                                             X
                        ∀t ∈ [0, T ],               x(tnj+1 ) − x(tnj ) −→ [x](p)
                                                                              π (t).                     (3)
                                                 [tn   n      n
                                                   j ,tj+1 ]∈π :
                                                       tn
                                                        j ≤t


                                                                                                (p)
If this property holds, then the convergence in (3) is uniform. We call [x]π the p-th variation of x along the
sequence of partitions π. We denote Vπp ([0, T ], R) the set of all continuous paths with finite p-th variation
along π.
                                                            (p)
Remark 1. For x ∈ Vπp ([0, T ], R) we have [x]π (T ) < ∞. If
                                                                 p
                                       X
                                              x(tni+1 ) − x(tni ) → ∞
                                              π n ∩(a,b)

for all (a, b) ⊂ [0, T ] then we will write [x](p) (t) = ∞.

    To formalize the concept of roughness, we introduce the notion of variation index and roughness index
of a path:

Definition 2 (Variation index). The variation index of a path x along a partition sequence π is defined
as the smallest p ≥ 1 for which x has finite p-th variation along π:

                                        pπ (x) = inf {p ≥ 1 : x ∈ Vπp ([0, T ], R)} .

Definition 3 (Roughness index). The roughness index of a path x (along π) is defined as
                                                                             1
                                                           H π (x) =                .
                                                                           pπ (x)

                                                                     5
   When the underlying sequence of partitions is clear, we will omit π and denote these indices as p(x)
and H(x). A similar roughness index was introduced by Han and Schied (2021).
   For a (real-valued) stochastic process X : [0, T ]×Ω → R the roughness index pπ (X(., ω)) of each sample
path X(., ω) may be different in principle. Nevertheless there are many important classes of stochastic
processes which have an almost-sure roughness index. For example, the roughness index of fractional
Brownian motion (fBM) matches with the corresponding Hurst parameter/ Hölder exponent:

Example 1. Brownian motion B has variation index pπ (B) = 2 and roughness index H π (B) = 21 along
any refining partition sequence π or any partition π with |π n | log n → 0 Dudley (1973).
    Fractional Brownian motion B H has variation index pT (B H ) = H1 and roughness index H T = H along
the dyadic partition sequence T.

       In general, the existence of a variation index is not obvious. For further details see Cont and Das (2022)


2.2        Normalized p-th variation
It is not easy to use p-th variation directly on empirical data for estimating roughness based on discrete
observations, as this involves checking convergence to an unknown limit. We introduce a normalized version
of p-th variation which has better asymptotic properties Cont and Das (2022):

Definition 4 (Normalized p-th variation         along a sequence of partitions).  Let π be a sequence of partitions
of [0, T ] with mesh |π | → 0 and π = 0 = t1 < t2 < · · · < tN (πn ) = T . x ∈ Vπp ([0, T ], R) is said to have
                         n                n           n     n          n

normalized p-th variation along π if there exists a continuous function w(x, p, π) : [0, T ] → R such that:
                                                               p
                                            x tni+1 − x (tni )
                                                   
                               X                                                n→∞
               ∀t ∈ [0, T ],                (p) n         (p) n
                                                                  × tni+1 − tni −−−→ w(x, p, π)(t).               (4)
                             π n ∩[0,t] [x]π (ti+1 ) − [x]π (ti )

We denote Nπp ([0, T ], R) the class of all continuous functions for which the normalized p-th variation2
exists.

    The terminology is justified by the following result Cont and Das (2022) which shows that, for a large
class of functions with p−th variation, the normalized p-th variation exists and is linear:

Theorem 2.1. Let x ∈ Vπp ([0, T ], R) for some p > 1 where π be a sequence of partitions of [0, T ] with
vanishing mesh |π n | → 0. Furthermore, if the p-th variation is absolutely continuous then:

                            x ∈ Nπp ([0, T ], R)     and         ∀t ∈ [0, T ], w(x, p, π)(t) = t.

Proof. See Appendix.

    The following result shows that normalized p-th variation is a ‘sharp’ statistic: if a function has finite
p-th variation along a sequence of partitions π then for all q ̸= p the normalized p-th variation is either
infinite or zero.

Theorem 2.2. Let π be a sequence of partitions of [0, T ] with mesh |π n | → 0. Let x ∈ Vπp ([0, T ], R) with
   (p)
[x]π ∈ (0, ∞) for some p > 1.

  (i) For all t ∈ (0, T ] and for all q > p; w(x, q, π)(t) = ∞.

 (ii) For all t ∈ [0, T ] and for all q < p; w(x, q, π)(t) = 0

Proof. The proof is provided in Appendix.
   2
       For p = 2 we will call this quantity as ‘normalized quadratic variation’.


                                                             6
   In particular, Brownian motion almost surely has linear normalized quadratic variation.

Example 2 (Normalized quadratic variation for Brownian motion). Let B be a Wiener process on a
probability space (Ω, F, P), and (π n )n≥1 be a sequence of partitions of [0, T ] with |π n | log n → 0. Then:

                                                  P (w(B, 2, π)(t) = t) = 1.

Proof. The proof is provided in the Appendix.

Remark 2. In the above example, instead of taking any partition sequence with |π n | log n → 0, we can also
take any refining sequence of partitions. The proof is then different and uses the martingale convergence
theorem.
                                              Rt                                             RT
Example 3 (Stochastic integrals). Let X(t) = 0 σ(u)dBu where σ is an adapted process with 0 σ 2 (u)du <
∞. Then, for any refining partition sequence π with vanishing mesh,

                                                  P (w(X, 2, π)(t) = t) = 1.

Proof. This is an immediate consequence of Theorem 2.1.

Remark 3. In the statement of Example 3, we can replace the assumption of refining partitions with
partitions satisfying |π n | log(n) → 0.

Example 4 (Normalized p-th variation for fractional Brownian motion). Let B H be a fractional Brownian
motion with Hurst index H, on a probability space (Ω, F, P). B H has normalized p-th variation along the
dyadic partition T = (Tn )n≥1 for p = 1/H almost-surely:
                                                          
                                             H 1
                                     P w B , , T (t) = t = 1.
                                               H

Proof. The proof is a consequence of (Viitasaari, 2019, Proposition 4.1).


2.3     Estimating roughness from discrete observations
Given observations on a refining time partition π L , we define the ‘normalized p-th variation statistic’ which
is the discrete counterpart of the normalized p-th variation:
                                                                                  p
                                       X                   X(tK          K
                                                              i+1 ) − X(ti )
                                                                                                 tK      K
                                                                                                           
           W (L, K, π, p, t, X) :=                                                         p ×    i+1 − ti   .   (5)
                                                                       X(tL          L
                                                  P
                                     π K ∩[0,t]     π L ∩[tK   K
                                                           i ,ti+1 ]      j+1 ) − X(tj )

The definition of the statistic (5) involves two frequencies: a ‘block’ frequency K and a sampling frequency
L ≫ K. As the partition is refining, π K is a subpartition of π L . The denominator is estimated by grouping
                                                                           L
the sample of size L into K many groups, where each group contains K         consecutive data points.
    The statistic (5) converges to the normalized p-th variation (4) as the sampling frequency L and block
frequency increase:
                                  lim lim W (L, K, π, p, t, x) = w(x, p, π)(t).
                                K→∞ L→∞

It is thus natural to define roughness estimators for a discretely sampled signal in terms of (5).
     The variation index estimator pbL,K (X) associated with the signal sampled on π L is then obtained by
computing W (L, K, π, p, t, X) for different values of p and solving the following equation for pπL,K (X),

                                          W (L, K, π, pbπL,K (X), T, X) = T.                                     (6)

One can either fix a window length T or solve (6) in a least squares sense across several values of T .

                                                                  7
   An estimator for the roughness index is subsequently defined as:

                                             b π (X) =            1
                                             HL,K                      .                                      (7)
                                                            pbπL,K (X)

We will denote the roughness estimator (7) as H b L,K when the underline dataset and the corresponding
partition sequence are clear. Asymptotic properties of these estimators under high-frequency sampling are
studied in Cont and Das (2022).


2.4     Finite sample behaviour of the roughness estimator
                                                                         b π (X) using high-frequency
We will now study the finite sample behaviour of the roughness estimator HL,K
simulations of fractional Brownian motions. In the simulation examples unless mentioned otherwise we
will use a uniform partition sequence of [0, 1] with:
                                                               
                                       n           1  2
                                     π = 0 < < < ··· < 1 .
                                                   n  n

To assess the finite sample accuracy of the estimator we compare the roughness index estimator H             bπ
                                                                                                               L,K
with the underlying Hurst exponent H ∈ {0.1, 0.3, 0.5, 0.8}. For every simulated path we compute W (L =
300 × 300, K = 300, π, q, t = 1, X = B H ) for different values of q, in order to estimate H  b L,K . In figure 1,
                                                                                            H
                                                                                               
the black line is the value of log W (L = 300 × 300, K = 300, π, q = p, t = 1, X = B ) plotted against
roughness index 1/p in log-scale. The blue horizontal line represents the estimated roughness index H        b L,K
whereas the dotted horizontal line represents the Hurst parameter. Figure 2 shows the histograms of
the estimator H b π generated from 150 independent paths. We observe that for datasets with length
                  L,K
L = 300 × 300 our roughness estimator H       b L=300×300,K=300 has satisfactory accuracy. Table 1 provides
summary statistics for roughness index H  b of simulated fractional Brownian motions. Figure 3 represents a
similar plot for simulated fractional Brownian motion with Hurst parameter H = 0.1. In Figure 3, in left,
similar to Figure 1, log(W (L = 2000 × 2000, K = 2000, π, p, t = 1, X = B H )) is plotted against H = 1/p
and the right plot represents the histograms of the estimator H  b L=2000×2000,K=2000 . The summary statistics
for the esimator are provided in Table 2. To compute the estimator H    b L,K we have different possible choices
of K ≪ L. Figure 4 shows how the estimator H          π
                                                      L,K varies with K for fractional Brownian motion with
                                                    b
Hurst parameter H = 0.1. The black line represents the H    b L,K plotted against different values of K whereas
the blue vertical line represents
                          √       the value for L = 300 × 300, K = 300. We observe that when we vary K in
the neighbourhood K ≈ L the estimator performs reasonably well and is not very sensitive to the choice
of K in this vicinity.
    In summary, we observe that for realistic sample sizes and frequencies encountered in high-frequency      √
financial data, the estimator is quite accurate and not sensitive to the block size K in the range K ≈ L.



               H     Min.      Lower quartile     Median       Mean        Upper quartile    Max.
              0.1   0.0650        0.0920          0.1030       0.1009         0.1100        0.1440
              0.3   0.2730        0.2940          0.2980       0.2976         0.3020        0.3180
              0.5   0.4820        0.4940          0.4980       0.4978         0.5020        0.5140
              0.8   0.7570        0.7820          0.7900       0.7891         0.7940        0.8220


Table 1: Summary statistics for estimated roughness index H
                                                          b L,K for fractional Brownian motion
B H with L = 300 × 300, K = 300.

                                                        8
Figure 1: Log scale plot of the normalized p-variation statistic for fractional Brownian motion with
Hurst parameter H ∈ {0.1, 0.3, 0.5, 0.8}. The black solid line represents the log of normalized p-
th variation statistics plotted against H = 1/p. The blue vertical line represents H  b L,K using the
normalized p-th variation statistics (with L = 300 × 300, K = 300). The horizontal dotted line
represents the true Hurst parameter H.




        Hurst index H    Min.    Lower quartile    Median    Mean    Upper quartile   Max.
             0.1         0.086       0.096          0.099    0.099      0.103         0.117


Table 2: Summary statistics for estimated roughness index H
                                                          b L,K for fractional Brownian motion
B H with H = 0.1, L = 2000 × 2000, K = 2000.




                                                  9
Figure 2: Histogram of estimated roughness index H b L,K with L = 300 × 300, K = 300 gen-
erated from 150 independent simulations of fractional Brownian motion with Hurst parameter
H ∈ {0.1, 0.3, 0.5, 0.8}.




                                           10
Figure 3: Simulation results for fractional Brownian motion with Hurst parameter H = 0.1. Left:
The log of normalized p-th variation statistic is plotted against H = 1/p in black. The blue vertical
line represents the estimated roughness index H   b L,K (with L = 2000 × 2000, K = 2000), whereas
the dotted line represents the true value H = 0.1. Right: Histogram of estimated roughness
index Hb L,K generated by simulating n = 150 independent fractional Brownian paths with Hurst
parameter H = 0.1. The blue line represents a kernel estimator for the density.




                                                 11
Figure 4: The solid black line represents the estimated roughness index H
                                                                        b L=300×300,K plotted against
different values of K for a fractional Brownian motion with Hurst parameter H = 0.1.



3     Spot volatility and realized volatility
Contrary to prices of an asset which may be observed and sampled directly from market data, (spot)
volatility is not directly observable and as a consequence must be estimated from prices. Stochastic volatility
models represent the price of a financial asset as the solution of a stochastic differential equation driven
by a Brownian motion:
                                             dSt = σt St dBt + µt St dt                                     (8)
where the coefficient σt represents the instantaneous or ‘spot’ volatility. In general, σt is represented as a
random process itself driven by fractional processes.
     In a practical situation, the price St at time t, is usually observed over a non-uniform time grids of
[0, T ]:
                                                                           
                                 π n = 0 = tn0 < tn1 < · · · < tnN (πn ) = T .                             (9)

    In order to study high-frequency asymptotics of roughness estimators, we assume |π n | → 0 as n
increases; here the index n may be thought of as a ‘samplingfrequency’. An example to keep in mind
is the dyadic partition sequence: π n = tni = 2iTn , i = 0, · · · , 2n but none of the results below requires a
uniform grid.
    The spot volatility process σt may then be recovered from the quadratic variation of the log-price
X = log S along this particular grid:
                                                     d
                                             σt2 = [log S]π (t)                                            (10)
                                                    dt
where the quadratic variation [log S]π of the log-price

                                            X     S(tni+1 ) 2
                                                            
                         [log S]π (t) = lim    log      n)     = lim RVt (π n )2
                                       n→∞
                                            n
                                                    S(t i
                                                                n→∞
                                            π ∩[0,t]



                                                       12
is computed as a high-frequency limit of the realized variance (Barndorff-Nielsen and Shephard, 2002;
Andersen et al., 2003) along the sampling grid π n , defined as
                                X         S(tni+1 ) 2
                                                    
                         n 2
                                                           X                       2
                   RVt (π ) =          log      n      =        X(tni+1 ) − X(tni ) .            (11)
                                n
                                            S(ti )         n
                                π ∩[0,t]                        π ∩[0,t]

The realized volatility is defined as the square root of the realized variance.
Definition 5 (Realized volatility). The realized volatility of a price process S over time interval [t, t + δ]
sampled along the time partition π n is defined as:
                            s X                              2 p
                      n
            RVt,t+∆ (π ) =                X(tni+1 ) − X(tni ) = [X]πn (t + ∆) − [X]πn (t)                 (12)
                                π n ∩[t,t+∆]

where X = log S.
    If the price St follows a stochastic volatility model (8) with instantaneous volatility σt then real-
ized variance converges to the quadratic variation of log S (also called ‘integrated variance’) as sampling
frequency increases (Barndorff-Nielsen and Shephard, 2002; Jacod and Protter, 2012):
                                                                               s
                                   Z t                                            Z t+∆
                   n 2 P                2                   n   P  p
             RVt (π ) → IVt :=         σu du,     RVt,t+∆ (π ) →     IVt,t+∆ =          σu2 du.        (13)
                      n→∞            0                               n→∞              t

Along a single price path observed at high-frequency, we can compute the realized variance (12) and the
realized volatility RVt,t+δ (π n ) in (13) may be used as a practical indicator of volatility:
                                                              √
                                              RVt,t+∆ (π n ) ≃ ∆ σt .

    Several empirical studies have attempted to estimate the roughness of ‘realized volatility’ signals using
high-frequency data, i.e. Andersen et al. (2003); Barndorff-Nielsen and Shephard (2002); Cont and Mancini
(2011); Jacod and Protter (2012); Podolskij and Vetter (2009). A well-known reference is the study of
Gatheral et al. (2018) where the authors estimate the roughness index of S&P500 realized volatility by
performing the following logarithmic regression to :
                                                     n
                              1          (q)  1X
                 m(q, ∆) :=     [log RV ]πn =    | log(RVt+∆ ) − log(RVt )|q ≈ Cq ∆ξq .                    (14)
                              n               n
                                                    t=1

The coefficients ξq are also shown to behave linearly in q:

                                                      ξq ≈ q H
                                                             bR.

Regression of ξq on q yields an estimate H
                                         b R of Hurst/Hölder index, for which Gatheral et al. (2018) report
the value H
          b R = 0.13. Based on these observations, they propose a fractional SDE for (spot) volatility:

                                               d log σt2 = µt dt + ηdBtH .

As we see from Equation 14, the method used in Gantert (1994) actually uses p-th variation of the log(RV )
to calculate the roughness of the underlying volatility process. Figure 5 is a replication of the log-regression
model described above to estimate the roughness index of the volatility of 5-min S&P 500. However, in an
interesting simulation study using paths simulated from a Brownian OU volatility process, Rogers (2019)
showed that the scaling behavior claimed as evidence for ‘rough volatility’ is also observed in a Brownian
OU model over a range of time scales, and that estimators of the roughness index based on log-regression
of empirical p-th variation have poor accuracy.
    Similar evidence for the lack of accuracy of such estimators based on log-regression of p-th variation is
shown by Fukasawa et al. (2022).

                                                           13
Figure 5: Left: A reproduction of the log-regression method introduced by Gatheral et al. (2018)
using SPX 5-minute realized volatility from the Oxford-Man Institute’s Realized Library. Right:
Regression of ξq vs q: the estimated slope is H
                                              b R = 0.135.


4     Numerical experiments
We now compare various estimators of the roughness index for instantaneous volatility σt with those
obtained from realized volatility RVt,t+∆ (π n ) using price trajectories simulated from stochastic volatility
models with varying degrees of “roughness”.


4.1     Stochastic volatility diffusion models
Let us first consider the following stochastic volatility where volatility is simply (the modulus of) a Brownian
motion:

Example 5.

                                    dSt = σt St dBt , with   σt = |Wt |,                                   (15)

where B, W are two independent Brownian motions.

     Figure 6 represents a path of the instantaneous volatility σt and the realized volatility RVt (π L ) com-
puted as in Equation 12 by taking 300 consecutive data-points, which corresponds to a 5-minute moving
window. The right plot of Figure 6 represents the estimation error, which is defined as the difference of
instantaneous and realized volatility. The ACF of the estimation error shows a complex time-dependent
pattern which rules out IID behavior and indicates a complex dependence structure.
     The estimated roughness index of instantaneous and realized volatility are observed to be very different.
In the left graph of Figure 7 we plot log(W (K = 500, L = 500 × 500, π, p, t = 1, X = RV )) against
H = 1/p for the realized volatility. On the other hand, the right graph is the same plot with the same
set of parameters but for instantaneous volatility. The estimated roughness index for realized volatility
(Hb L=500×500,K=500 (RV ) = 0.27) is significantly smaller than the roughness index of the instantaneous

                                                      14
volatility (Hb L=500×500,K=500 (σ) = 0.49) suggesting rougher behaviour of realized volatility. As in our
simulation study we do not have any measurement errors, this roughness behaviour purely comes from
estimation error. In some studies it is assumed that the estimation error or the log-estimation error is
I.I.D. (see for example Fukasawa et al. (2022)) but as one can see from this diffusion example, both the
estimation error and the log-estimation error is far from I.I.D. and hence the assumptions put forth for
example in Fukasawa et al. (2022), is not very realistic for general diffusion models.
     The solid black lines in Figure 8 and Figure 9 respectively represent the estimated roughness index
Hb L=300×300,K plotted against different values of K for the realized and instantaneous volatility (model
15). The blue vertical line represents for K = 500, L = 500 × 500. From the figures, we can observe that
irrespective of the choice of K for the finite sample dataset of length L = 500 × 500, the realized volatility
is significantly rougher than the instantaneous volatility.
     We now compare our roughness estimator with the log-regression method suggested in Gatheral et al.
(2018) for the model 15. It turns out that even with the log-regression model, similar ‘rougher’ realized
volatility is observed even if the instantaneous volatility has Brownian diffusive behaviour. Figure 10 and
Figure 11 show that the realized volatility has a significant smaller roughness index than the instantaneous
volatility even with respect to the log regression method. In this example it is clear that the roughness
observed in realized volatility is attributable to the discretization error (‘estimation error’) and not the
roughness of the spot volatility process, which is Brownian.




Figure 6: Simulation model: σt = |Bt′ |, dSt = St σt dBt , where Bt and Bt′ are Brownian motions
independent of each other. Left: The red line represents instantaneous volatility σt whereas the
black line represents realized volatility RVt . Right: Corresponding estimation error for the left
simulated path.

   Next we consider a more realistic mean-reverting volatility model in which the volatility follows a
Brownian Ornstein–Uhlenbeck process:


                                                     15
Figure 7: Left: Estimated roughness index H   b L,K (via normalized p-variation statistic with L =
500 × 500, K = 500), for realized volatility derived from a Brownian diffusion model, shown in
Figure 6. Right: Estimated roughness index H    b L,K for instantaneous volatility of the same price
path.

Example 6 (OU-SV model).

                        dSt = St σt dBt ,    σ t = σ 0 e Yt ,   dYt = −γYt dt + θdBt′                    (16)

where Bt and Bt′ are two independent Brownian motions.

    In the simulation, we use σ0 = 1, Y0 = 0 and γ = θ = 1. The left plot of Figure 12 represents the realized
volatility (respectively instantaneous volatility) of the price process in black (respectively red) simulated
from the above stochastic volatility model 16. The middle plot of Figure 12 represents the corresponding
estimation error, which is the difference between the realized and the instantaneous volatility. Visually the
middle plot suggests the estimation error has a complicated dependence structure. But unlike the plot for
Example 5, the log error on the right plot of Figure 12 has an I.I.D. Gaussian structure (This is supported
by the theory provided in Fukasawa et al. (2022)).
    Now we compare the distribution of the estimator H     b L,K with (L = 300 × 300, K = 300) for realized
and instantaneous volatility across 2500 independent paths drawn from (16). The left plot in Figure 13
is the distribution of H b L,K for the realized volatility while the right plot corresponds to the same for
instantaneous volatility. The following table provides summary statistics for the estimator H      b L,K with
L = 300 × 300, K = 300 across 2500 independent sample paths for realized volatility and instantaneous
volatility respectively.




                                                         16
Figure 8: The solid black line represents the estimated roughness index H   b L,K via normalized p-th
variation statistic W (L = 500×500, K, π, q, t = 1, X = RV ) plotted against different values of K for
the realized volatility shown in Figure 6. The blue vertical line represents L = 500 × 500, K = 500
whereas the blue horizontal line represents H b = 0.273.




Figure 9: The solid black line represents the estimated roughness index H    b L,K via normalized p-th
variation statistic W (L = 500 × 500, K, π, q, t = 1, X = IV ) plotted against different values of K for
the instantaneous volatility shown in Figure 6. The blue vertical line represents L = 500 × 500, K =
500 whereas the blue horizontal line represents true Hurst parameter H = 0.5.




                                                  17
Figure 10: Left: Scaling analysis of instantaneous volatility of a simulated Brownian stochastic
volatility model (Example 5) using the same log-regression method introduced in Gatheral et al.
(2018). Right: regression coefficients ξq as a function of q. The estimated roughness index is
Hb R = 0.499.




Figure 11: Left: Scaling analysis of realized volatility of a simulated Brownian stochastic volatility
model (Example 5) using the same log-regression method introduced in Gatheral et al. (2018).
Right: regression coefficients ξq as a function of q. The estimated roughness index is Hb R = 0.342.




                                                 18
                                  Realized volatility   Instantaneous volatility
                       Min.             0.087                    0.528
                   1st Quantile         0.128                    0.552
                     Median             0.136                    0.556
                       Mean             0.137                    0.557
                   3rd Quantile         0.148                    0.563
                       Max.             0.181                    0.581


Table 3: Estimated roughness index H     b L,K , L = 300 × 300, K = 300 for realized volatility and
instantaneous volatility for the diffusion model (15) with H = 0.5.




Figure 12: Left: Realized volatility (in black) vs instantaneous volatility (red) for the OU price
model (16). Right: Estimation error.




                                                19
                                                         b L,K for (L = 300 × 300, K = 300) across
Figure 13: Distribution of the estimated roughness index H
2500 independent simulations for the OU-SV model (16) with roughness index H = 0.5. Left:
Realized volatility. Right: Instantaneous volatility.




                                               20
4.2     A fractional Ornstein-Uhlenbeck model
In both previous examples, instantaneous volatility follows a diffusive behaviour similar to Brownian motion
with H = 12 , yet the realized volatility exhibits ”rough” behaviour with an estimated roughness index
significantly smaller than 0.5.
    We now consider the more general case of a price process generated by a stochastic volatility model of
the type (1) where instantaneous volatility has a general roughness index H ∈ (0, 1) and explore how the
roughness index of the instantaneous volatility reflects on the roughness index of realized volatility and the
corresponding estimation error.

Example 7. [Fractional OU process] Consider the following price process, where the volatility is described
by a fractional Ornstein–Uhlenbeck process:

                       dSt = σt St dBt ,   σt = σ0 eYt ;        dYt = −γYt dt + θdBtH ,                   (17)

where γ = θ = σ0 = 1, B is a Brownian motion and B H fractional Brownian motion with Hurst index
H ∈ (0, 1).

   We compute the realized volatility and compare the estimated roughness index H    b L,K (with, L =
300 × 300, K = 300) of instantaneous and realized volatility in the following table.

                             H      Instantaneous volatility        Realized volatility
                            0.10             0.130                        0.190
                            0.20             0.215                        0.250
                            0.30             0.310                        0.258
                            0.40             0.413                        0.207
                            0.50             0.507                        0.130
                            0.60             0.601                        0.087
                            0.70             0.678                        0.061
                            0.80             0.756                        0.052

The corresponding pictures for price process, realized volatility and the instantaneous volatility from Model
17 with Hurst index H = {0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8} respectively are presented in Figure 14.
Visually we can observe that for smaller H, the instantaneous volatility is rougher than realized volatility
but as we increase H the realized volatility shows significantly rougher behaviour than the instantaneous
volatility. In Figure 15 for the simulated models in Figure 14, we plot the estimated roughness index
Hb L,K (RV ) and H  b L,K (σ) respectively in the red and blue line. Though the estimated roughness index
of instantaneous volatility (represented in blue line) gives an accurate estimate of Hurst index H, the
roughness index for realized volatility always stays below 0.3. In particular, when the instantaneous
volatility exhibits smoother behaviour (corresponding to H ≥ 0.5) the estimated roughness index of realized
volatility turns out to be a poor estimate for the Hurst index.
     Figure 16 shows the corresponding estimators H    b L,K (RV ) and Hb L,K (σ) for 100 independent simulated
price paths from (17). The bold black lines represent the mean across 100 independent simulations whereas
the dotted lines represent the corresponding 25% and 75% confidence intervals. For the price process (17),
no matter what the value of the Hurst exponent for instantaneous volatility, the roughness index of realized
volatility Hb L,K (RV ) is always estimated to be between 0 to 0.3.
     These examples illustrate our point: one cannot draw the conclusion that (spot) ‘volatility is rough’
i.e. reject the null hypothesis H(σ) = 1/2 just because realized volatility exhibits ‘rough’ behaviour with
Hb L,K (RV ) < 1 or H  b R < 1/2, even when these estimators exhibit values well below 1/2.
                2




                                                           21
Figure 14: Left: Simulated price path St of fractional OU model (Equation 17) with
H={0.05,0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8} respectively, Center: Realized volatility, Right: Instanta-
neous volatility.




                                                22
Figure 15: Estimated roughness index H    b L=300×300,K=300 for realized volatility and instantaneous
volatility from a high-frequency fractional-OU stochastic volatility model (Equation (17)), plotted
for price path generated with different values of H.




Figure 16: Estimated roughness index H      b L=300×300,K=300 for realized volatility and instantaneous
volatility for a high-frequency simulation of a fractional-OU stochastic volatility model (17), plotted
against different Hurst index H for 100 independent price paths.


                                                  23
5         Application to high-frequency financial data
Having extensively explored the performance of our roughness estimator H      b L,K based on the normalized
p-th variation statistic for spot and realized volatility on simulated price paths, we now apply it to high-
frequency financial time series.


5.1        AAPL
Figure 17 (left) shows the second-by-second record of AAPL stock price. The right graph of Figure 17 is
log(W (L = 1900 × 1900, K = 1900, π, p, t = 1, X)) plotted against Hurst parameter H = 1/p for ‘AAPL’
price.
    The left plot of Figure 18 represents 1-minute realized volatility of ‘AAPL’ in 2016. The right graph
of Figure 18 is log(W (L = 310 × 310, K = 310, π, p, t = 1, X = RV )) plotted against H = 1/p for the
1-min AAPL realized volatility. Fixing the value of L = 310 × 310, if we deviate the value of K a little,
then the estimated roughness index varies between 0.08 to 0.22. This is consistent with the results of
Gatheral et al. (2018) regarding realized volatility. But as our simulation study suggests, the roughness
index of realized volatility may be very different from that of spot volatility which is the quantity modelled
in continuous-time stochastic volatility models.


5.2        SP500
Several studies on rough volatility, including the original study Gatheral et al. (2018), are based on the
Oxford-Man Institute Realized Volatility dataset 3 . Figure 19 represents the plot of 5-minute realized
volatility of SP500. The X-axis represents date. The right graph of Figure 19 is log(W (L = 70 × 70, K =
70, π, p, t = 1, X = RV )) plotted against Hurst parameter H = 1/p for the 5-min Oxford-Man institute
realized volatility data. Fixing the value of L = 70 × 70, if we deviate the value of K a little, the estimated
roughness index H   b L,K varies between 0.05 to 0.25. This finding is again consistent with the findings in
Gatheral et al. (2018).
    Overall, the picture that emerges from SP500 and AAPL data is quite similar to the one observed in
simulations of diffusion-type stochastic volatility models discussed in Section 4.1. As observed in Section
2.4, these observations are fully compatible with a diffusion-type stochastic volatility model such as (16)
and one cannot reject the null hypothesis H(σ) = 1/2 just because realized volatility exhibits ‘rough’
behaviour with H  b L,K (RV ) < 1 or H
                                     b R < 1/2, even though these estimators exhibit values around 0.1.
                                 2




    3
        https://realized.oxford-man.ox.ac.uk/data


                                                      24
Figure 17: Left: price of AAPL 04/Jan/2016 - 11/May/2016 (90 days). Right:           Roughness
                b L,K (with L = 1400 × 1400, K = 1400) for AAPL stock price data.
index estimator H




Figure 18: Left: Plot of 1-min realized volatility of ‘AAPL’ (year 2016). Right: Estimated
                b L,K (with L = 310 × 310, K = 310) for the 1-min realized volatility (estimated
roughness index H
                b L,K ∈ [.08 − .22]).
roughness index H



                                              25
Figure 19: Left: S&P500 5-min realized volatility. Right:                                        b L,K ∈
                                                                       Estimated roughness index H
[.05 − .25] with L = 70 × 70, K = 70.



6     Rough volatility ... or estimation error?
Given the large literature on ‘rough volatility’ in quantitative finance, it is somewhat surprising that the
initial claim Gatheral et al. (2018) that one needs to model the spot volatility process using a ‘rough’
fractional noise with Hurst exponent H < 1/2 has not been examined more closely, especially given that
several follow-up studies (Fukasawa et al., 2022; Rogers, 2019) point to the fact that the observations in
Gatheral et al. (2018) may well be compatible with a Brownian diffusion model for volatility.
    Our detailed examples illustrate that, for stochastic-volatility diffusion models driven by Brownian
motion as described in Examples 5 and 6, the realized volatility has a roughness index H       L,K ≈ 0.3 so
                                                                                               [
exhibits an ‘apparent roughness’ which instantaneous volatility does not have, both in terms of normalized
p-th variation statistics and also in terms of the log- regression method used by Gatheral et al. (2018).
Clearly in these simulation examples this is entirely due to the discretization error or ‘estimation error’.
    These results suggest that one cannot hastily conclude that the roughness observed in realized volatility
is an indicator of similar behaviour in spot volatility, as implicitly assumed in the ‘rough volatility’ liter-
ature; the observations in high-frequency financial data are in fact compatible with a stochastic volatility
model drive by Brownian motion and the origin of this apparent roughness may very well lie in estimation
error rather than the noise process driving spot volatility.
    Also, as shown in Example 7, the rough behaviour of realized volatility does not lead us to reject the
hypothesis that the underlying spot volatility may be modeled with a Brownian diffusion model or even a
smoother model with long-range dependence and H > 1/2. This observation, together with “Occam’s ra-
zor”, pleads for the use of Markovian stochastic volatility models which seem compatible with the empirical
evidence but are far more tractable.
    We are thus drawn to concur with Rogers (2019) that “the notion that volatility is rough, that is,
governed by a fractional Brownian motion (with H < 1/2), is not an incontrovertible established fact;


                                                      26
simpler models explain the observations just as well.”


References
Andersen, T. G., Bollerslev, T., Diebold, F. X., and Labys, P. (2003). Modeling and forecasting realized
  volatility. Econometrica, 71(2):579–625.

Baillie, R. T., Bollerslev, T., and Mikkelsen, H. O. (1996). Fractionally integrated generalized autoregressive
  conditional heteroskedasticity. Journal of Econometrics, 74(1):3–30.

Barndorff-Nielsen, O. E. and Shephard, N. (2002). Econometric analysis of realized volatility and its use
  in estimating stochastic volatility models. Journal of the Royal Statistical Society: Series B (Statistical
  Methodology), 64(2):253–280.

Bennedsen, M., Lunde, A., and Pakkanen, M. S. (2022). Decoupling the short-and long-term behavior of
  stochastic volatility. Journal of Financial Econometrics, 20(5):961–1006.

Beran, J. (1994). Statistics for long-memory processes, volume 61 of Monographs on Statistics and Applied
  Probability. Chapman and Hall, New York.

Bolko, A. E., Christensen, K., Pakkanen, M. S., and Veliyev, B. (2022). A GMM approach to estimate the
  roughness of stochastic volatility. Journal of Econometrics, in press.

Bollerslev, T. and Ole Mikkelsen, H. (1996). Modeling and pricing long memory in stock market volatility.
  Journal of Econometrics, 73(1):151–184.

Breidt, F., Crato, N., and de Lima, P. (1998). The detection and estimation of long memory in stochastic
  volatility. Journal of Econometrics, 83(1):325–348.

Comte, F. and Renault, É. (1998). Long memory in continuous-time stochastic volatility models. Mathe-
  matical Finance, 8:291–323.

Cont, R. (2005). Long range dependence in financial markets. In Lévy-Véhel, J. and Lutton, E., editors,
  Fractals in Engineering, pages 159–179, London. Springer London.

Cont, R. (2007). Volatility clustering in financial markets: Empirical facts and agent-based models. In
  Teyssière, Gilles and Kirman, Alan P. (eds.): Long Memory in Economics, pages 289–309. Springer,
  Berlin, Heidelberg.

Cont, R. and Das, P. (2022). Measuring the roughness of a signal. Working Paper.

Cont, R. and Mancini, C. (2011).        Nonparametric tests for pathwise properties of semimartingales.
  Bernoulli, 17(2):781 – 813.

Cont, R. and Perkowski, N. (2019). Pathwise integration and change of variable formulas for continuous
  paths with arbitrary regularity. Transactions of the American Mathematical Society, 6:134–138.

Dudley, R. M. (1973). Sample functions of the gaussian process. Ann. Probab., 1(1):66–103.

Fukasawa, M., Takabatake, T., and Westphal, R. (2022). Consistent estimation for fractional stochastic
  volatility model under high-frequency asymptotics. Mathematical Finance, 32(4):1086–1132.

Gantert, N. (1994). Self-similarity of Brownian motion and a large deviation principle for random fields
  on a binary tree. Prob. Th. Rel. Fields, 98(1):7–20.

                                                      27
Gatheral, J., Jaisson, T., and Rosenbaum, M. (2018). Volatility is rough. Quantitative Finance, 18:933–949.
Han, X. and Schied, A. (2021). The hurst roughness exponent and its model-free estimation.
Hurvich, C. M., Moulines, E., and Soulier, P. (2005). Estimating long memory in volatility. Econometrica,
  73(4):1283–1328.
Jacod, J. and Protter, P. (2012). Discretization of processes, volume 67 of Stochastic Modelling and Applied
  Probability. Springer, Heidelberg.
Lahiri, A. and Sen, R. (2020). Fractional brownian markets with time-varying volatility and high-frequency
  data. Econometrics and Statistics, 16:91–107.
Lévy-Véhel, J., Lutton, E., and Tricot, C. (2005). Fractals in Engineering. Springer, Berlin.
Mandelbrot, B. B. and Van Ness, J. W. (1968). Fractional Brownian motions, fractional noises and
 applications. SIAM Review, 10(4):422–437.
Podolskij, M. and Vetter, M. (2009). Estimation of volatility functionals in the simultaneous presence of
  microstructure noise and jumps. Bernoulli, 15(3):634 – 658.
Rogers, L. (2019). Things we think we know. . https://www.skokholm.co.uk/wp-content/uploads/
  2019/11/TWTWKpaper.pdf.
Rogers, L. C. G. (1997). Arbitrage with fractional Brownian motion. Mathematical Finance, 7:95–105.
Viitasaari, L. (2019). Necessary and sufficient conditions for limit theorems for quadratic variations of
  gaussian sequences. Probab. Surveys, 16:62–98.
Willinger, W., Taqqu, M. S., and Teverovsky, V. (1999). Stock market prices and long-range dependence.
 Finance and stochastics, 3(1):1–13.


Proof of Theorem 2.2 (i).
We will prove the result for t = T , for general t the proof generalizes without further complication. Since
                                                                                           (q)
q > p and the function x has finite p-variation along π, the pathwise q-th variation [x]π (t) = 0 for all
                                                     (q)           (q)
t ∈ [0, T ]. Hence given any fixed h > 0 we have [x]π (t + h) − [x]π (t) = 0. Now given any M > 0 and any
n > 1, we will show that w(x, q, π)(t) > M . For fix n > 1 we have:
                                 for all tni ∈ π n ,            [x](q) n          (q) n
                                                                   π (ti+1 ) − [x]π (ti ) = 0.

Define the ‘unfeasible estimator’
                                                   X          |x(tni+1 ) − x(tni )|q
                           wn (x, q, π)(T ) =               (q)             (q)
                                                                                           × (tni+1 − tni ).
                                                    πn   [x]π (tni+1 ) − [x]π (tni )
Since x ∈ Vπp ([0, T ], R) for some p > 0, for fix large enough n, we have πn |x(tni+1 )−x(tni )|q ×(tni+1 −tni ) > 0.
                                                                          P
So we get the lower bound of wn (x, q, π) as follows.
                                         "                                 #
                                                          1                    X
             wn (x, q, π)(T ) ≥ min
                                n  n            (q)             (q)
                                                                                    |x(tni+1 ) − x(tni )|q × (tni+1 − tni )
                                ti ∈π        [x]π (tni+1 ) − [x]π (tni )       πn
                                   "                                                   #
                                                               1
                             ≥C                          (q)                (q)
                                                                                           = ∞ > M.
                                        maxtni ∈πn ([x]π (tni+1 ) − [x]π (tni ))
Since for all n > 1, wn (x, q, π)(t) = ∞ we can conclude the following:
                                        w(x, q, π)(t) = lim wn (x, q, π)(t) = ∞.
                                                               n→∞


                                                                   28
Proof of Theorem 2.2(ii).
We will prove the result for t = T , for general t the proof follows exactly the same way. Since the function
                                                                                                   (q)
x has finite p-variation along π and q < p from the assumption, the pathwise q -th variation [x]π (t) = ∞
                                                                (q)             (q)
for all t ∈ [0, T ]. Hence, given any fixed h > 0 we have [x]π (t + h) − [x]π (t) = ∞. Now given any ϵ > 0
                                                                              n
and any n > 1, we will show that w(x, q, π)(t) < ϵ by showing that w (x, q, π)(t) < ϵ for all large n. For
fix n > 1 we have:
                               for all tni ∈ π n , [x](q) n          (q) n
                                                      π (ti+1 ) − [x]π (ti ) = ∞. So,
                                                    X             |x(tni+1 ) − x(tni )|q
                           wn (x, q, π)(T ) =                  (q)             (q)
                                                                                               × (tni+1 − tni )
                                                     πn     [x]π (tni+1 ) − [x]π (tni )
                                          "                                      #
                                                 |x(tni+1 ) − x(tni )|q                  X
                               ≤ max
                                 n n             (q)             (q)
                                                                                     ×    (tni+1 − tni )
                                  ti ∈π       [x]π (tni+1 ) − [x]π (tni )                 πn
                                                             "                                   #
                                                                     |x(tni+1 ) − x(tni )|q
                                      ≤ T × max
                                            n n                      (q)                 (q)
                                                    ti ∈π         [x]π (tni+1 ) − [x]π (tni )
                                                             "                                                    #
                                                                                         1
                ≤ T × max
                      n n
                          |x(tni+1 ) − x(tni )|q ×                                (q)                (q)
                                                                                                                      = 0 < ϵ.
                       ti ∈π                                      mintni ∈πn ([x]π (tni+1 ) − [x]π (tni ))
Since for all n > 1, wn (x, q, π)(t) = 0;

                                      w(x, q, π)(t) = lim wn (x, q, π)(t) = 0.
                                                                   n→∞


Proof of Theorem 2.1
                                        d        (p)
For convenience, assume g(u) = du         [x]π (u). Since the p-th variation is strictly increasing we have
             1
supt∈[0,T ] g(u) < ∞. Since g(u) is continuous in a compact interval [0, T ], it is also bounded. So for
                          1
all t ∈ [0, T ], we have g(u) ∈ (0, ∞). So as a consequence of mean value theorem,

                                                    X              |x(tni+1 ) − x(tni )|p
                          wn (x, p, π)(t) =                   (p) n          (p) n
                                                                                                × (tni+1 − tni )
                                                π n ∩[0,t] [x]π (ti+1 ) − [x]π (ti )

                                                      X |x(tni+1 ) − x(tni )|p
                                                =                              ,
                                                      n
                                                               g(uni )
                                                    π ∩[0,t]

where uni ∈ [tni , tni+1 ] for all n ≥ 1 and for all i = 0, · · · , N (π n ) − 1. Finally, using properties of Riemann
integral we can conclude:
                                     X |x(tni+1 ) − x(tni )|p n→∞ Z t 1
                                                   n)         −−−→                d[x](p)
                                                                                      π (u)
                                    n
                                               g(u i                     0   g(u)
                               π ∩[0,t]

                                              Z t           (p)                  Z t
                                              d[x]π (u)/du
                                          =                du =                          du = t.
                                            0      g(u)                              0
Since the limit always exists we can conclude the proof.




                                                                      29
Proof of Example 2
Let B be a Wiener process on the canonical Wiener space (Ω, F, P), i.e Ω = C 0 ([0, T ], R), B(t, ω) = ω(t)
and P is the Wiener measure. Let π n = (0 = tn0 < tn1 < · · · < tnN (πn ) = T ) be a sequence of partitions of
[0, T ] satisfying |π n | log n → 0. Then the results of Dudley Dudley (1973) imply that
                                                                          !
                                                                      n→∞
                                       X
                                    P     |B(tni+1 ∧ t) − B(tni ∧ t)|2 → t = 1.
                                         πn

So if we set Ω0 = Ω ∩ Qπ ([0, T ], R) then P (Ω0 ) = 1 and any ω ∈ Ω0 satisfies [ω]π (t) = t. Now for any
ω ∈ Ω0 we also have the following:
                                                                                                 2
                                     n
                                                                X            ω(tni+1 ) − ω(tni )
           w(ω, 2, π)(t) = lim w (ω, 2, π)(t) = lim                                                    × (tni+1 − tni ).
                              n→∞                     n→∞                  [ω]π (tni+1 ) − [ω]π (tni )
                                                              π n ∩[0,t]

                  X (ω(tni+1 ) − ω(tni ))2                        X
                                                n      n
           = lim           n − tn )        × (t i+1 − ti ) =  lim   (ω(tni+1 ) − ω(tni ))2 = t.
              n→∞
                  n
                        (t i+1    i
                                                             n→∞
                                                                  n
                   π ∩[0,t]                                                      π ∩[0,t]

So for Brownian motion, normalized quadratic variation is almost surely equal to t.

Remark 4. From Lemma 2 we know that, for any partition sequence π with |π n | log(n) → 0, there exists
Ωπ ⊂ Ω with P(Ωπ ) = 1 such that:

                                    ∀ω ∈ Ωπ , ∀t ∈ [0, T ],         w(ω, 2, π)(t) = t.

We also have the following relation between quadratic variation and normalized-QV for Brownian paths in
the class Ωπ .
                             ∀ω ∈ Ωπ , ∀t ∈ [0, T ],   w(ω, 2, π)(t) = [ω]π (t).
i.e. the null set for quadratic variation and normalized-quadratic variation of Brownian motion are the
same.




                                                          30