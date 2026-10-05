source: https://arxiv.org/pdf/physics/0507111
fetched_utc: 2026-10-04T18:50:41Z
bytes_raw: 295022

Financial Applications of Random Matrix Theory: Old Laces and New Pieces
                                                                                   Marc Potters∗ , Jean-Philippe Bouchaud†,∗ and Laurent Laloux∗
                                                                                             ∗
                                                                                             Science & Finance, Capital Fund Management,
                                                                                                6 Bd Haussmann, 75009 Paris France
                                                                                        †
                                                                                          Commissariat à l’Energie Atomique, Orme des Merisiers
                                                                                                 91191 Gif-sur-Yvette cedex, France

                                                                        This contribution to the proceedings of the Cracow meeting on ‘Applications of Random Matrix
arXiv:physics/0507111v1 [physics.data-an] 14 Jul 2005




                                                                     Theory’ summarizes a series of studies, some old and others more recent on financial applications
                                                                     of Random Matrix Theory (RMT). We first review some early results in that field, with particu-
                                                                     lar emphasis on the applications of correlation cleaning to portfolio optimisation, and discuss the
                                                                     extension of the Marčenko-Pastur (MP) distribution to a non trivial ‘true’ underlying correlation
                                                                     matrix. We then present new results concerning different problems that arise in a financial con-
                                                                     text: (a) the generalisation of the MP result to the case of an empirical correlation matrix (ECM)
                                                                     constructed using exponential moving averages, for which we give a new elegant derivation (b) the
                                                                     specific dynamics of the ‘market’ eigenvalue and its associated eigenvector, which defines an interest-
                                                                     ing Ornstein-Uhlenbeck process on the unit sphere and (c) the problem of the dependence of ECM’s
                                                                     on the observation frequency of the returns and its interpretation in terms of lagged cross-influences.


                                                                                            I.   PORTFOLIO THEORY: BASIC RESULTS

                                                          Suppose one builds a portfolio of N assets with weight wi on the ith asset. The (daily) variance of the portfolio
                                                        return is given by:
                                                                                                           X
                                                                                                     R2 =      wi σi Cij σj wj ,                                        (1)
                                                                                                                    ij


                                                        where σi2 is the (daily) variance of asset
                                                                                                 P i and Cij is the correlation matrix. If one has predicted gains gi , then the
                                                        expected gain of the portfolio is G = wi gi .
                                                           In order to measure and optimize the risk of this portfolio, one therefore has to come up with a reliable estimate of
                                                        the correlation matrix Cij . This is difficult in general [1, 2] since one has to determine of the order of N 2 /2 coefficients
                                                        out of N time series of length T , and in general T is not much larger than N (for example, 4 years of data give 1000
                                                        daily returns, and the typical size of a portfolio is several hundred stocks.) We will denote, in the following, q = N/T ;
                                                        an accurate determination of the true correlation matrix will require q ≪ 1. If rti is the daily return of stock i at time
                                                        t, the empirical variance of each stock is:
                                                                                                                           T
                                                                                                                         1 X i 2
                                                                                                              σi2 =          rt ,                                                  (2)
                                                                                                                         T t

                                                        and can be assumed for simplicity to be perfectly known (its relative mean square-error is (2 + κ)/T , where κ is the
                                                        kurtosis of the stock, known to be typically κ ≈ 3). In the above definition, we have, as usual, neglected the daily
                                                        mean return, small compared to daily fluctuations. The empirical correlation matrix is obtained as:
                                                                                                                T
                                                                                                             1 X i j
                                                                                                     Eij =       xx ;          xit ≡ rti /σi .                                     (3)
                                                                                                             T t t t

                                                        If T < N , E has rank T < N , and has N − T zero eigenvalues. Assume there is a “true” correlation matrix C
                                                        from which past and future xit are drawn. The risk of a portfolio constructed independently of the past realized xit is
                                                        faithfully measured by:
                                                                                                     1X         D       E
                                                                                                           wi σi xit xjt wj σj ≈
                                                                                                                                 X
                                                                                             2
                                                                                            RE =                                    wi σi Cij σj wj .                              (4)
                                                                                                     T ijt                       ij

                                                        Because the portfolio is not constructed using E, this estimate is unbiased and the relative mean square-error is small
                                                        (∼ 1/T ). Otherwise, the w’s would depend on the observed x’s and, as we show now, the result can be very different.
                                                          Problems indeed arise when one wants to estimate the risk of an optimized portfolio, resulting from a Markowitz
                                                        optimization scheme, which gives the portfolio with maximum expected return for a given risk or equivalently, the
                                                                                                                       2

minimum risk for a given return (G):
                                                            P      −1
                                                               j Cij gj /σj
                                              wi σi = G P             −1                                             (5)
                                                           ij gi /σi Cij gj /σj

From now on, we drop σi (which can always be absorbed in gi and wi ). In matrix notation, one has:

                                                                C−1 g
                                                   wC = G                                                            (6)
                                                             gT C−1 g
The question is to estimate the risk of this optimized portfolio, and in particular to understand the biases of different
possible estimates. We define the following three quantities:
   • The “In-sample” risk, corresponding to the risk of the optimal portfolio over the period used to construct it:

                                                   2     T                 G2
                                                  Rin = wE EwE =                                                     (7)
                                                                        gT E−1 g

   • The “true” minimal risk, which is the risk of the optimized portfolio in the ideal world where C would be
     perfectly known:

                                                  2       T                 G2
                                                 Rtrue = wC CwC =                                                    (8)
                                                                         gT C−1 g

   • The “Out-of-sample” risk which is the risk of the portfolio constructed using E, but observed on the next period
     of time:

                                               2      T                 gT E−1 CE−1 g
                                              Rout = wE CwE = G2                                                     (9)
                                                                         (gT E−1 g)2

From the remark above, the result is expected to be the same (on average) computed with C or with E′ , the ECM
corresponding to the second time period. Since E is a noisy estimator of C such that hEi = C, one can use a convexity
argument for the inverse of positive definite matrices to show that in general:

                                                 hgT E−1 gi ≥ gT C−1 g                                              (10)

Hence for large matrices, for which the result is self-averaging:
                                                        2     2
                                                       Rin ≤ Rtrue .                                                (11)

By optimality, one clearly has that:
                                                        2       2
                                                       Rtrue ≤ Rout .                                               (12)

These results show that the out-of-sample risk of an optimized portfolio is larger (and in practice, much larger, see
Fig 1) than the in-sample risk, which itself is an underestimate of the true minimal risk. This is a general situation:
using past returns to optimize a strategy always leads to over-optimistic results because the optimization adapts to
the particular realization of the noise, and is unstable in time. In the case where the true correlation matrix is C = 1,
one can show that [3]:

                              2        G2                  2     2
                                                                         p         2
                             Rtrue =             and      Rin = Rtrue     1 − q = Rout (1 − q)                      (13)
                                       gT g
Only in the limit q → 0 will these quantities coincide, which is expected since in this case the measurement noise
disappears. In the other limit q → 1, the in-sample risk becomes zero since it becomes possible to find eigenvectors
(portfolios) with zero eigenvalues (risk), simply due to the lack of data.
                                                                                                                         3




                                              150




                                     Return
                                              100




                                               50                                Raw in-sample
                                                                                 Cleaned in-sample
                                                                                 Cleaned out-of-sample
                                                                                 Raw out-of-sample

                                                0
                                                    0            10                   20                 30
                                                                         Risk



FIG. 1: In sample (left curves) and out of sample (right curves) portfolio risk along the optimal curve in the risk return
plane. Red lines are with the raw empirical matrix, blue lines with the cleaned matrix using RMT, showing how the risk
underestimation can be reduced by matrix cleaning. From [4].


                                              II.        MATRIX CLEANING AND RMT

   How should one ‘clean’ the empirical correlation matrix to avoid, as much as possible, such biases in the estimation
of future risk? In order to get some general intuition on this problem, let us rewrite the Markowitz solution in terms
of the eigenvalues λk and eigenvectors Vik of the correlation matrix:
                                        X                         X
                                   wi ∝    λk−1 Vik Vjk gj ≡ gi +   (λ−1       k k
                                                                      k − 1)Vi Vj gj                               (14)
                                                    kj                           kj

The first term corresponds to the naive solution: one should invest proportionally to the expected gain (in units where
σi = 1). The correction term means that the weights of eigenvectors with λ > 1 are suppressed, whereas the weights
of eigenvectors with λ < 1 are enhanced. Potentially, the optimal Markowitz solution allocates a very large weight to
small eigenvalues, which may be entirely dominated by measurement noise and hence unstable. A very naive way to
avoid this is to go for the naive solution wi ∝ gi , but with the k ∗ largest eigenvectors projected out:
                                                            X
                                                wi ∝ gi −        Vik Vjk gj ,                                      (15)
                                                                      k≤k∗ ;j
                                                                                                                      √
so that the portfolio is market neutral (the largest eigenvector correspond to a collective market mode, Vi1 ≈ 1/ N )
and sector neutral (other large eigenvectors contain sector moves). Since most of the volatility is contained in the
market and sector modes, the above portfolio is already quite good in terms of risk. More elaborated ways aim at
retaining all eigenvalues and eigenvectors, but after having somehow cleaned them. A well known cleaning corresponds
to the so-called “shrinkage estimator”: the empirical matrix is shifted ‘closer’ to the identity matrix. This is a Bayesian
method that assumes that the prior empirical matrix is the identity, again only justified if the market mode has been
subtracted out. More explicitely:
                                  Ec = αE + (1 − α)1                     so       λkc = 1 + α(λk − 1),                (16)
where the subscript c corresponds to the cleaned objects. This method involves the parameter α which is undetermined,
but somehow related to the expected signal to noise ratio. If the signal is large, α → 1, and α → 0 if the noise is large.
Another   possible interpretation is through a constraint on the effective number of assets in the portfolio, defined as
( i wi2 )−1 [2]. Constraining this number to be large (ie imposing a minimal level of diversification) is equivalent to
 P
choosing α small.
  Another route is eigenvalue cleaning, first suggested in [1, 4], where one replaces all low lying eigenvalues with a
unique value, and keeps all the high eigenvalues corresponding to meaningful economical information (sectors):
                              λkc = 1 − δ                if   k > k∗ ,          λkc = λkE           if    k ≤ k∗ ,    (17)
where k ∗ is the number of meaningful number of sectors and δ is chosen such that the trace of the correlation matrix
is exactly preserved. How should k ∗ be chosen? The idea developed in [1, 4] is to use Random Matrix Theory to
                                                                                                                       4
                                                                                                               ∗
determine the theoretical edge of the ‘random’ part of the eigenvalue distribution, and to fix k ∗ such that λkE is close
to this edge.
   What is then the spectrum of a random correlation matrix? The answer is known in several cases, due to the work
of Marčenko and Pastur [5] and others [6, 7, 8]. We briefly recall the results and some elegant methods to derive them,
with special emphasis on the problem of the largest eigenvalue, which we expand on below. Consider an empirical
correlation matrix E of N assets using T data points, both very large, with q = N/T finite. Suppose that the true
correlations are given by hxit xjt′ i = Cij δtt′ . This defines the Wishart ensemble [9]. In order to find the eigenvalue
density, one introduces the resolvent:
                                                          1
                                                            Tr (zI − E)−1
                                                                         
                                                 G(z) =                                                             (18)
                                                          N
from which one gets:
                                                             1
                                                ρ(λ) = lim       ℑ (G(λ − iǫ)) .                                    (19)
                                                       ǫ→0 π

The simplest case is when C = I. Then, E is a sum of rotationally invariant matrices δEij t
                                                                                            = (xit xjt )/T . The trick
in that case is to consider the so-called Blue function, inverse of G, i.e. such that B(G(z)) = z. The quantity
R(x) = B(x) − 1/x is the ‘R-transform’ of G, and is known to be additive [5, 11, 12]. Since δEt has one eigenvalue
equal to q and N − 1 zero eigenvalues, one has:
                                                       
                                                                 N −1
                                                                        
                                                     1     1
                                           δGt (z) =           +                                                  (20)
                                                     N z−q          z

Inverting δGt (z) to first order in 1/N ,
                                            1      q                               1     1
                               δBt (x) =      +              −→        BE (x) =      +        ,                     (21)
                                            x N (1 − qx)                           x (1 − qx)
and finally
                                                                  p
                                                 (z + q − 1) −      (z + q − 1)2 − 4zq
                                      GE (z) =                                         ,                            (22)
                                                                   2zq
which finally reproduces the well known Marčenko-Pastur (MP) result:
                                                  p
                                                    4λq − (λ + q − 1)2
                                          ρ(λ) =                                                                    (23)
                                                          2πλq
  The case of a general C cannot be directly written as a sum of “Blue” functions, but one can get a solution using
the Replica trick or by summing planar diagrams, which gives the following relation between resolvents: [6, 7, 8]
                                                                                    z
                               zGE (z) = ZGC (Z)          where       Z=                       ,                    (24)
                                                                            1 + q(zGE (z) − 1)

from which one can easily obtain ρ(λ) numerically for any choice of C [8]. [In fact, this result can even be obtained
from the original Marčenko-Pastur paper by permuting the role of the appropriate matrices]. The above result does
however not apply when C has isolated eigenvalues, and only describes continuous parts of the spectrum. For example,
if one considers a matrix C with one large eigenvalue that is separated from the ‘Marčenko-Pastur sea’, the statistics
of this isolated eigenvalue has recently been shown to be Gaussian [13] (see also below), with a width ∼ T −1/2 , much
smaller than the uncertainty on the bulk eigenvalues (∼ q 1/2 ). A naive application of Eq. (24), on the other hand,
would give birth to a ‘mini-MP’ distribution around the top eigenvalue. This would be the exact result only if the
top eigenvalue of C had a degeneracy proportional to N .
   From the point of view of matrix cleaning, however, these results show that: (i) the expected edge of the bulk,
that determines k ∗ , obviously depends on the prior one has for C. The simplest case where C = I was investigated
in particular in [1, 10], with the results shown in Fig 2. Other choices are however possible and could lead to an
improved cleaning algorithm; (ii) the uncertainty on large eigenvalues is much less than that on the bulk eigenvalues,
meaning that the bulk needs a lot of shrinkage, but the bigger eigenvalues less so – at variance with the naive shrinkage
procedure explained above. An alternative route may consist in using the ‘power mapping’ method proposed by Guhr
[14] or clustering methods [15].
                                                                                                                                                  5

                                                6

                                                                                    6


                                                                                    4




                                                                             ρ(λ)
                                                4                                                                Market
                                                                                    2




                                         ρ(λ)
                                                                                    0
                                                                                        0       20               40           60
                                                                                                         λ

                                                2




                                                0
                                                    0              1                        2                             3
                                                                                        λ



FIG. 2: Empirical eigenvalue density for 406 stocks from the S&P 500, and fit using the MP distribution. Note (i) the presence
of one very large eigenvalue, corresponding to the market mode (see section IV) and (ii) the MP fit reveals systematic deviations,
suggesting a non trivial structure of the true correlation matrix, even after sector modes have been accounted for (see [8, 16]).


                              III.     EWMA EMPIRICAL CORRELATION MATRICES

 Consider now the case where C = I but where the Empirical matrix is computed using an exponentially weighted
moving average (EWMA). More precisely:
                                                                       t−1
                                                                       X                             ′       ′        ′
                                                         Eij = ǫ             (1 − ǫ)t−t xti xtj                                                 (25)
                                                                   t′ =−∞

with ǫ = 1/T . Such an estimate is standard practice in finance. Now, as an ensemble Eij satisfies Eij = (1 − ǫ)Eij +
ǫxti xtj . We again invert the resolvent of δEt to find the elementary R-function,

                                                        1                                                                      q
                                      δBt (x) =           + Rt (x)           with               Rt (x) =                                        (26)
                                                        x                                                                 N (1 − qx)

Using the scaling properties of G(z) we find for R(x):

                                                              RaC (x) = aRC (ax).                                                               (27)

This allows one to write:
                                                                                                                                        q
                         RE (x) = R(1−ǫ)E (x) + Rt (x) = (1 − q/N )RE ((1 − q/N )x) +                                                           (28)
                                                                                                                                   N (1 − qx)

To first order in 1/N , one now gets:

                                                                 q                   log(1 − qx)
                                     R(x) + xR′ (x) +                = 0 −→ R(x) = −             .                                              (29)
                                                              1 − qx                     qx
Going back to the resolvent to find the density, we finally get the result first obtained in [17]:
                                        1
                              ρ(λ) =      ℑG(λ)             where G(λ) solves                        λqG = q − log(1 − qG)                      (30)
                                        π
This solution is compared to the standard MP distribution in Fig 3.
  Another nice properties of Blue functions is that they can be used to find the edges of the eigenvalue spectrum
(λ± ). One has:[12]

                                                    λ± = B(x± )          where                   B ′ (x± ) = 0                                  (31)
                                                                                                                           6

                                             1.2
                                                                                         exp Q=2
                                                                                         std Q=3.45

                                              1



                                             0.8




                                      ρ(λ)
                                             0.6



                                             0.4



                                             0.2



                                              0
                                               0     0.5        1       1.5         2   2.5           3
                                                                         λ




FIG. 3: Spectrum of the exponentially weighted random matrix with q ≡ N ǫ = 1/2 and the spectrum of the standard Wishart
random matrix with q ≡ N/T = 1/3.45, chosen to have the same upper edge. From [17].


In the case at hand, by evaluating B(x) when B ′ (x) = 0 we can write directly an equation whose solutions are the
spectrum edges (λ± )

                                                           λ± = log(λ± ) + q + 1                                        (32)

When q is zero, the spectrum is a δ in 1 as expected. But as the noise increases (or the characteristic time decreases)
the lower edge approach zero very quickly as λ− ∼ exp(−q). Although there are no exact zero eigenvalues for EWMA
matrices, the smallest eigenvalue is very close to zero.


                    IV.   DYNAMICS OF THE TOP EIGENVALUE AND EIGENVECTOR

  As mentioned above, it is well known that financial covariance matrices are such that the largest eigenvalue is well
separated from the ‘bulk’, where all other eigenvalues reside. The financial interpretation of this large eigenvalue is
the so-called ‘market mode’: in a first approximation, all stocks move together, up or down. One can state this more
precisely in the context of the one factor model, where the ith stock return at time t is written as:

                                                              rti = βi φt + εit ,                                       (33)

where the market mode φt is common to all stocks through their market exposure β i and the εit are idiosyncratic
noises, uncorrelated from stock to stock. Within such a model, the covariance matrix reads:

                                                       Cij = βi βj σφ2 + σi2 δij .                                      (34)

When all σi ’s are equal, this matrix is easily diagonalized; for N stocks, its largest eigenvalue is Λ0 = ( j βj2 )σφ2 + σ 2
                                                                                                            P

and is of order N , and all the other N − 1 eigenvalues Λα are equal to σ 2 . The largest eigenvalue corresponds to the
eigenvector βi . More generally, the largest eigenvalue Λ0 , normalized by the average square volatility of the stocks,
can be seen as a proxy for the average interstock correlation.
   A natural question, of great importance for portfolio management, or dispersion trading (option strategies based
on the implied average correlation between stocks), is whether Λ0 and the β’s are stable in time. Of course, the
largest eigenvalue and eigenvector of the empirical correlation matrix will be, as discussed at length above, affected
by measurement noise. Can one make predictions about the fluctuations of both the largest eigenvalue and the
corresponding eigenvector induced by measurement noise? This would help separating a true evolution in time of the
average stock correlation and of the market exposure of each stock from one simply related to measurement noise.
We shall see that such a decomposition seems indeed possible in the limit where Λ0 ≫ Λα .
   We will assume, as in the previous section, that the covariance matrix is measured through an exponential moving
average of the returns. This means that the matrix E evolves in time as:

                                                   Eij,t = (1 − ǫ)Eij,t−1 + ǫrti rtj .                                  (35)
                                                                                                                           7

The true covariance matrix Cij = hri rj i is assumed to be time independent – this will give us our benchmark
hypothesis – with its largest eigenvalue Λ0 associated to the normalized eigenvector Ψ0 . In this section we deal with
covariance matrices instead of correlation matrices for simplicity, but most results should carry over to this latter case
as well.
  Denoting as λ0t the largest eigenvalue of Et associated to ψ0t , standard perturbation theory, valid for ǫ ≪ 1, gives:

                               λ0t = (1 − ǫ)λ0t−1 + ǫhψ0t−1 |C|ψ0t−1 i + ǫhψ0t−1 |ηt |ψ0t−1 i,                          (36)

with ηij = ri rj − hri rj i. We will suppose for simplicity that the returns are Gaussian, yielding:

                                                  hηij ηkℓ i = Cik Cjℓ + Ciℓ Cjk .                                      (37)

In the limit where Λ0 becomes much larger than all other eigenvectors, the above equation simplifies to:

                                        λ0t ≈ (1 − ǫ)λ0t−1 + ǫ cos2 θt−1 Λ0 [1 + ξt ] ,                                 (38)

where cos θt ≡ hψ0t |Ψ0 i and ξt is a random noise term of mean zero and variance equal to 2. This noise becomes
Gaussian in the limit of large matrices, leading to a Langevin equation for λ0 :
                                            dλ0
                                                = ǫ(cos2 θΛ0 − λ0 ) + ǫ cos2 θξt .                                      (39)
                                             dt
We have neglected in the above equation a deterministic term equal to ǫ sin2 θΛ1 , which will turn out to be a factor
(Λ1 /Λ0 )2 smaller than the terms retained in Eq. (38).
  We now need to work out an equation for the projection of the instantaneous eigenvector ψ0t on the true eigenvector
Ψ0 . This can again be done using perturbation theory, which gives, in braket notation:
                                                      X hψαt−1 |rt rt |ψ0t−1 i
                             |ψ0t i = |ψ0t−1 i + ǫ                               |ψαt−1 i
                                                             λ0t−1 − λαt−1
                                                      α6=0
                                                      rt rt |ψ0t−1 i    hψ0t−1 |rt rt |ψ0t−1 i
                                    ≈ |ψ0t−1 i + ǫ                   −ǫ                        |ψ0t−1 i,                (40)
                                                          λ0t−1               λ0t−1
where we have used the fact that the basis of eigenvectors is complete. It is clear by inspection that the correction
term is orthogonal to |ψ0t−1 i, so that |ψ0t i is still, to first order in ǫ, normalized. Let us now decompose the matrix
rt rt into its average part C and the fluctuations η, and first focus on the former contribution. Projecting the above
equation on < Ψ0 | leads to the deterministic part of the evolution equation for cos θt :
                                                                     Λ0                  Λ0
                                  cos θt ≈ cos θt−1 + ǫ cos θt−1          − ǫ cos3 θt−1       ,                         (41)
                                                                    λ0t−1               λ0t−1

where we have neglected the contribution of the small eigenvalues compared to Λ0 , which is again a factor (Λ1 /Λ0 )2
smaller. In the continuous time limit ǫ → 0, this equation can be rewritten as:
                                                       dθ    ǫΛ0
                                                          =−      sin 2θ,                                               (42)
                                                       dt    2λ0t
and describes a convergence of the angle θ towards 0 or π – clearly, Ψ0 and −Ψ0 are equivalent. It is the noise term
η that will randomly push the instantaneous eigenvector away from its ideal position, and gives to θ a non-trivial
probability distribution. Our task is therefore to compute the statistics of the noise, which again becomes Gaussian
for large matrices, so that we only need to compute its variance. Writing |ψ0t i = cos θt |Ψ0 i + sin θt |Ψ1t i, where |Ψ1t i
is in the degenerate eigenspace corresponding to small eigenvalues Λ1 , and using Eq. (37), we find that the noise term
ζt to be added to Eq. (42) is given by:

                                                ǫ2  2
                                     hζt2 i ≈       2Λ0 cos2 θt sin2 θt + Λ0 Λ1 cos2 2θt ,
                                                                                        
                                                 2                                                                      (43)
                                                λ0t
where we have kept the second term because it becomes the dominant source of noise when θ → 0, but neglected
a term in Λ21 . The eigenvector ψ0 therefore undergoes an Ornstein-Uhlenbeck like motion on the unit sphere. One
should also note that the two sources of noise ξt and ζt are not independent. Rather, one has, neglecting Λ21 terms:

                                          2hξt ζt i ≈ Λ0 cos2 θt sin 2θt − Λ1 sin 4θt                                   (44)
                                                                                                                                 8

                                    0.2




                                    0.1




                                                                  Ornstein−Uhlenbeck
                                                                  Log(Variogram cos(θ))
                                                                  Variogram λ0



                                     0
                                          0         100               200            300          400
                                                                       τ




FIG. 4: Variogram of the top eigenvalue of the correlation matrix λ0 (top curve) and (log)-variogram of the top eigenvector,
ln hhψ0t+τ |ψ0t ii, as a function of the time lag τ , for US stocks, and for an exponential moving average parameter ǫ = 1/30 days.
We show for comparison (bottom curve) the Ornstein-Uhlenbeck behaviour expected for both quantities in the case of a time
independent underlying correlation structure.


In the continuous time limit, we therefore have two coupled Langevin equations for the top eigenvalue λ0t and the
deflection angle θt . In the limit Λ1 ≪ Λ0 , the stationary solution for the angle can be computed to be:
                                                          "                  Λ1
                                                                                          #1/4ǫ
                                                              1 + cos 2θ(1 − Λ  )
                                              P (θ) = N                       0
                                                                                                                              (45)
                                                              1 − cos 2θ(1 − Λ
                                                                             Λ0 )
                                                                              1




As expected, this distribution is invariant when θ → π − θ, since −Ψ0 is also a top eigenvector. In the limit Λ1 ≪ Λ0 ,
one sees that the distribution becomes peaked around θ = 0 and π. For small θ, the distribution becomes Gaussian:
                                                                         !
                                                      1             θ2
                                            P (θ) ≈ q       exp − Λ1 ,                                            (46)
                                                     2πǫ Λ1        2ǫ Λ0
                                                                 Λ0


leading to hcos2 θi ≈ 1−ǫΛ1/2Λ0 The angle θ is less and less fluctuating as ǫ → 0 (as expected) but also as Λ1 /Λ0 → 0:
a large separation of eigenvalues leads to a well determined top eigenvector. In this limit, the distribution of λ0 also
becomes Gaussian (as expected from general results [13]) and one finds, to leading order:

                                              hλ0 i ≈ Λ0 − ǫΛ1 /2;          h(δλ0 )2 i ≈ ǫ.                                   (47)

Therefore, we have shown that in the limit of large averaging time and one large top eigenvalue (a situation approx-
imately realized for financial markets), the deviation from the true top eigenvalue δλ0 and the deviation angle θ are
independent Gaussian variables (the correlation between them indeed becomes zero as can be seen using Eq. (44) in
that limit, both following Ornstein-Uhlenbeck processes.
  From these results one directly obtains the variogram of the top eigenvalue as:

                                              h[λt+τ − λt ]2 i = 2ǫ (1 − exp(−ǫτ )) .                                         (48)

This is the result expected in the absence of a ‘true’ dynamical evolution of the structure of the matrix. From Fig.
4, one sees that there is clearly an additional contribution, hinting at a real evolution of the strength of the average
correlation with time. One can also work out the average overlap of the top eigenvector with itself as a function of
time lag, E(hψ0t+τ |ψ0t i). Writing again |ψ0t i = cos θt |Ψ0 i + sin θt |Ψ1t i, one sees that an equation for the evolution of
the transverse component |Ψ1t i is a priori also needed. It is easy to show, following the same method as above, that
the evolution of the angle φt made by the component with a fixed direction is a free diffusion with a noise term of
order ǫΛ1 /Λ0 . Therefore, on the time scale ǫ−1 over which θt evolves, |Ψ1t i can be considered to be quasi-constant,
                                                                                                                             9

leading to:
                                                                                        Λ1
                                hhψ0t+τ |ψ0t ii ≈ E(cos(θt − θt+τ )) ≈ 1 − ǫ               (1 − exp(−ǫτ )).               (49)
                                                                                        Λ0
Any significant deviation from the above law would, again, indicate a true evolution of the market structure. Again,
Fig. 4, provides some evidence of such an evolution, although weaker than that of the top eigenvalue λ0 .


                         V.     FREQUENCY DEPENDENT CORRELATION MATRICES

  The very definition of the correlation matrix a priori depends on the time scale over which returns are measured.
The return on time τ for stock i is defined as: ri,τ (t) = ln pi (t + τ ) − ln pi (t), where pi (t) is the price at time t. The
correlation matrix is then defined as:
                                                                    hri,τ (t)rj,τ (t)ic
                                                       Cij (τ ) =                                                         (50)
                                                                           σi σj
A relatively well known effect is that the average inter-stock correlation grows with the observation time scale – this
is the so-called Epps effect [18, 19]. For example, for a collection of stocks from the FTSE index, one finds, in the
period 1994-2003:

                              hCi6=j (5′ )i ≈ 0.06;         hCi6=j (1h)i ≈ 0.19;              hCi6=j (1d)i ≈ 0.29         (51)

Besides the change of the average correlation level, there is also a change of structure of the correlation matrix: the
full eigenvalue distribution distribution changes with τ . A trivial effect is that by increasing the observation frequency
one also increases the number of observations; the parameter q defined above decreases and the noise band is expected
to shrink. This, at first sight, appears to be a nice way to get rid of the observation noise in the correlation matrix
(see [20] for a related discussion). Unfortunately, the problem (or the interesting effect, depending on the standpoint)
is that this is accompanied by a true modification of the correlations, for which we will provide a model below. In
particular one observes the emergence of a larger number of eigenvalues leaking out from the bulk of the eigenvalue
spectrum (and corresponding to ‘sectors’) as the time scale τ increases. This effect was also noted by Mantegna [21]:
the structure of the minimal spanning tree constructed from the correlation matrix evolves from a ‘star like’ structure
for small τ ’s (several minutes), meaning that only the market mode is present, to a fully diversified tree at the scale
of a day. Pictorially, the market appears as an embryo which progressively forms and differentiates with time.
   The aim of this section is to introduce a simple model of lagged cross-influences that allows one to rationalize the
mechanism leading to such an evolution of the correlation matrix. Suppose that the return of stock i at time t is
influenced in a causal way by return of stock j at all previous times t′ < t. The most general linear model for this
reads:
                                          XZ t
                      ri,1 (t) = ξi (t) +      dt′ Kij (t − t′ )rj,1 (t′ ) hξi (t)ξj (t′ )i = Di δij δ(t − t′ )        (52)
                                          j    −∞


Here τ = 1 is the shortest time scale – say a few seconds. The kernel Kij is in general non-symmetric and describes
how the return of stock j affects, on average, that of stock i a certain time later. We will define the lagged correlation
Cij (t − t′ ) by:

                                                      Cij (t − t′ ) = hri,1 (t)rj,1 (t′ )i.                               (53)

This matrix is, for t 6= t′ , not symmetric; however, one has obviously Cij (t − t′ ) = Cji (t′ − t). These lagged correlations
were already studied in [22]. Going to Fourier space, one finds the Fourier transform of the covariance matrix
Cij (ω) = Cji (−ω):
                                                 X
                                       Cij (ω) =   (1 − K(ω))−1                 −1
                                                               ik (1 − K(−ω))jk Dk                                         (54)
                                                        k

where K(ω) is the Fourier transform of K(τ ) with by convention K(τ < 0) = 0. When cross-correlations are small,
which is justified provided the ri,1 (t) corresponds to residual returns, where the market has been subtracted, the
relation between Cij and Kij becomes quite simple and reads, for τ > 0:

                                                            Cij (τ ) = Dj Kij (τ ).                                       (55)
                                                                                                                               10

                                                0




                                   K11(E)
                                            −0.05
                                                                     Data
                                                                     Fit with 2 time scales




                                             −0.1
                                                     0   0.2   0.4         0.6                0.8      1
                                                                     E




FIG. 5: Typical self-influence kernel Kii (E) in Laplace space and fit with the Laplace transforms of the sum of two exponentials.

                                             0.075




                                             0.025
                                  K1j(E)




                                            −0.025
                                                                                  Data 12
                                                                                  Data 13
                                                                                  Data 14
                                                                                  Fits 2 time scales


                                            −0.075
                                                     0   0.2   0.4          0.6               0.8      1
                                                                     E




FIG. 6: Typical cross-influence kernels Kij (E) for three pairs of stocks, and fit with the Laplace transforms of the sum of two
exponentials. Note that the influence amplitudes have different signs, even for the same pair of stock, depending on the time
scale.


This equation allows one, in principle, to determine Kij (τ ) from the empirical observation of the lagged correlation
                                                                                        0 −Γij τ                   0
matrix. Suppose for simplicity that the influence kernel takes the form Kij (τ ) = Kij   e       , then Kij (ω) = Kij /(iω +
Γij ). In this model, the primary object is the influence matrix K which has a much richer structure than the correlation
matrix: each element defines an influence strength K 0 and an synchronisation time Γ−1 . In fact, as shown in Figs.
5 and 6, fitting the empirical data requires that Kij is parameterized by a sum of at least two exponentials, one
corresponding to a time scale of minutes, and a second one of hours; sometimes the influence strength corresponding
to these two time scales have opposite signs. Pooling together the parameters corresponding to different pairs of
stocks, we find, as might have been expected, that strongly coupled stocks (large K 0 ) have short synchronisation
times Γ−1 .
  Coming back to the observation that the correlation matrix is frequency dependent, one should note that the scale
dependent correlation matrix Cij (τ ) is related to Cij (ω) by:
                                                                  Z
                                       Cij (τ ) = hri,τ rj,τ ic =   dω S 2 (ωτ )Cij (ω)                                 (56)
                                                                                                                         11

where S(.) is the form factor (i.e. Fourier transform of the window used to define returns on scale τ , for example a
flat window in the simplest case). Therefore, for τ small one finds that residuals are uncorrelated (i.e. the correlation
matrix has no structure beyond the market mode):

                                                   Cij (τ → 0) ≈ Di δij ,                                              (57)

whereas on long time scales the full correlation develops as:
                                                       Z ∞
                               Cij (τ → ∞) ≈ Di δij +       dτ [Dj Kij (τ ) + Di Kji (τ )] .                           (58)
                                                           0

The emergence of correlation structure therefore reveals the lagged cross-influences in the market. Note that on long
time scales, small K 0 ’s can be counterbalanced by large synchronisation times Γ−1 , and lead to significant correlations
between ‘weakly coupled’ stocks.
  We believe that a more systematic empirical study of the influence matrix Kij and the way it should be cleaned,
in the spirit of the discussion in section II, is worth investigating in details.
   We want to thank Pedro Fonseca and Boris Schlittgen for many discussions on the issues addressed in sections IV and V,
and Szilard Pafka and Imre Kondor for sharing the results on the EWMA matrices given in section III. We also thank Gérard
Ben Arous and Jack Silverstein for several clarifying discussions. We also thank the organisers of the meeting in Cracow for
inviting us and for making the conference a success.




 [1] L. Laloux, P. Cizeau, J.-P. Bouchaud and M. Potters, Phys. Rev. Lett. 83, 1467 (1999); L. Laloux, P. Cizeau, J.-P.
     Bouchaud and M. Potters, Risk 12, No. 3, 69 (1999).
 [2] J.-P. Bouchaud and M. Potters, Theory of Financial Risk and Derivative Pricing (Cambridge University Press, 2003).
 [3] S. Pafka, I. Kondor, Physica A319 487 (2003) and cond-mat/0305475
 [4] L. Laloux, P. Cizeau, J.-P. Bouchaud and M. Potters, Int. J. Theor. Appl. Finance 3, 391 (2000).
 [5] V. A. Marčenko and L. A. Pastur, Math. USSR-Sb, 1, 457-483 (1967).
 [6] J. W. Silverstein and Z. D. Bai, Journal of Multivariate Analysis, 54 175 (1995).
 [7] A. N. Sengupta and P. Mitra, Phys. Rev. E 80, 3389 (1999).
 [8] Z. Burda, A. Görlich, A. Jarosz and J. Jurkiewicz, Physica A, 343, 295-310 (2004).
 [9] J. Wishart, Biometrika, A20 32 (1928).
[10] V. Plerou, P. Gopikrishnan, B. Rosenow, L. N. Amaral, H. E. Stanley, Phys. Rev. Lett. 83, 1471 (1999).
[11] D. V. Voiculescu, K. J. Dykema, A. Nica, Free Random Variables, AMS, Providence, RI (1992).
[12] A. Zee, Nuclear Physics B 474, 726 (1996)
[13] J. Baik, G. Ben Arous, and S. Peche, Phase transition of the largest eigenvalue for non-null complex sample covariance
     matrices, http://xxx.lanl.gov/abs/math.PR/0403022, to appear in Ann. Prob, and these proceedings
[14] T. Guhr, B. Kalber, J. Phys. A 36, 3009 (2003), and these proceedings.
[15] F. Lillo, R. Mantegna, Cluster analysis for portfolio optimisation, these proceedings, and physics/0507006.
[16] M. Potters, J. P. Bouchaud, Embedded sector ansatz for the true correlation matrix in stock markets, in preparation.
[17] S. Pafka, I. Kondor, M. Potters, Exponential weighting and Random Matrix Theory based filtering of financial covariance
     matrices, cond-mat/0402573, to appear in Quantitative Finance.
[18] T. Epps, Comovement of stock prices in the very short run, J. Am. Stat. Assoc. 74, 291 (1979)
[19] R. Reno, Int. Journ. Th. Appl. Fin, 6, 87 (2003)
[20] O. Precup, G. Iori, A comparison of high frequency cross correlation measures, preprint.
[21] G. Bonanno, N. Vandewalle and R. N. Mantegna, Physical Review E62 R7615-R7618 (2001)
[22] L. Kullman, J. Kertesz, T. Kaski, Phys. Rev. E66 026125 (2002)
         150
Return




         100




         50




          0
               0   10          20   30
                        Risk
       6

                          6


                          4
                   ρ(λ)




       4                                       Market
                          2
ρ(λ)




                          0
                              0       20       40           60
                                           λ

       2




       0
           0   1                  2                     3
                              λ
                             0
                         10

                                                      Data
                                                            1/2
                                                      y=1/x

                          −1
                        10
Correlation amplitude




                          −2
                        10




                          −3
                        10




                          −4
                        10
                                 1            10                  100
                                     Time scale (minutes)
                   FTSE
       6
                        4




                        2

       4

                        0
                            0       5      10       15
ρ(λ)




                                1 day (<ρ>=0.29)
       2                        1 hour (<ρ>=0.19)
                                5 min (<ρ>=0.06)




       0
           0   1                2                        3
                    λ
                                BMY PNU        T
                             BAX         AIT
                                     MRK        GTE
                                  JNJ        BEL
                      AVP                         SO
                            CL
                                  PG              ETR
                                            AEP   UCM
                     BA IFF    KO    CPB

             RTNB             PEP
                        UTX
              ROK                                  HNZ
 HRS
       TXN HWPHON               VO CEN
                              GD       MO           MOB            CHV    ARC   OXY
 NSM                  MKG BDK            NT
            INTC MSFT                            XON
                                     GE                             HM
 IBM CSCO                  RAL           FDX                        BHI
                                        DIS   DAL SLB
 UIS      SUNW                                                      HAL
                   LTD          MCDBNI            CGP
ORCL     S     MAY                        NSC
     CSC                WMT                       WMB
                                          COL
           TOY      KM           AIG
                           CI
                 BS    GM                 FLR
                            F       AXP
                          XRX             TAN
                                      MER
                         TEK                 BC
                                            WFC
                         JPM          BAC         MMM AA
                                                              WY     CHA    BCC
                         AGC
                                            DD           IP
                                ONE
                                                  DOW
                                USB                      MTC EK     PRD
                                        ETR              SO
                                              AEP
                                                              UCM

                                        BNI            AIT           GTE

                                                              BEL
                         BCC     CHA         WY                            BHI          HAL
                                                       NSC
                                       IP                                        SLB

 NSM TXN                                                                                USB
                  UIS

                                                                                              JPM
                                                                                                           FLR

                  IBM
         INTC
                                                                                                     MER
 ORCL                                                               GE                  BAC
                                 AIG
                                                                                                           AXP
                        CI                                                        ONE          WFC

  CSCO            HWP
           MSFT                        GM                                         JNJ

SUNW
                             F                                             PG                 MRK
                                                  KO
                                                                XON
                                                                                                     BMY
                                                  CHV           MOB
                                       PEP                                       CL




                                                       HM           ARC