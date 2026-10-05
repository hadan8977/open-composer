source: https://arxiv.org/pdf/cond-mat/0005400
fetched_utc: 2026-10-04T18:41:59Z
bytes_raw: 466737

Modelling fluctuations of financial time series: from cascade process
                                                          to stochastic volatility model
arXiv:cond-mat/0005400v1 24 May 2000




                                                                 J.F. Muzy1 , J. Delour1 and E. Bacry2
                                               1
                                                 Centre de Recherche Paul Pascal, Avenue Schweitzer 33600 Pessac, France
                                       2
                                         Centre de Mathématiques appliquées, Ecole Polytechnique, 91128 Palaiseau Cedex, France

                                                                                       November 5, 2018


                                                                                             Abstract

                                                  In this paper, we provide a simple, “generic” interpretation of multifractal scaling laws and
                                              multiplicative cascade process paradigms in terms of volatility correlations. We show that in
                                              this context 1/f power spectra, as recently observed in Ref. [20], naturally emerge. We then
                                              propose a simple solvable “stochastic volatility” model for return fluctuations. This model is able
                                              to reproduce most of recent empirical findings concerning financial time series: no correlation
                                              between price variations, long-range volatility correlations and multifractal statistics. Moreover,
                                              its extension to a multivariate context, in order to model portfolio behavior, is very natural.
                                              Comparisons to real data and other models proposed elsewhere are provided.


                                              1     Introduction
                                              As shown by most recent empirical studies on huge amount of data, the market price changes
                                              are characterized by several “universal” features [1, 2]: price increments are not correlated,
                                              volatilities are strongly (power-law) correlated and price increment probability density function
                                              (pdf) shapes depend on the time scale. From quasi Gaussian at rather large time scales, these
                                              pdf are characterized by fat tails at fine scales. Many authors in the recently emerged field
                                              of “econophysics” [1, 2, 3] as well as in classical empirical finance, aim at proposing simple,
                                              discrete or continuous time models that are able to account for these observations. Among all
                                              the proposed models, one can distinguish several streams, from the simplest Brownian process,
                                              that constitutes the main tool used by practitians, to the class of “heteroskedastic” nonlinear
                                              processes as proposed in Refs. [6, 7]. To account for the letpokurtic nature of the small scale
                                              pdf, Mandelbrot [4] and Fama [5] proposed the Levy stable paradigm that has been recently
                                              improved in the “truncated Levy” version [8, 1, 2]. More recently, an interesting comparison
                                              between market price variations and the fluctuations of the fluid velocity field in fully developed
                                              turbulence has been suggested [9]. Besides the real pertinence of such an analogy that has been
                                              widely commented [11, 12, 2], this work opens the door to another important paradigm to model
                                              financial time series, namely multifractal processes. The multifractal processes1 , and the deeply
                                              connected mathematics of large deviations and multiplicative cascades, are well known to be
                                              useful to describe the intermittent nature of fully developed turbulence [21]. Recent empirical
                                        1
                                            people sometimes refer to “multi-affine” processes or processes that display “multi-scaling”



                                                                                                 1
       findings [10, 13, 15, 16] suggest that in finance, this framework is also likely to be pertinent as
       far as the time scale dependence of the statistical properties of price variations is concerned.
           Our purpose in this paper is twofold. First, we make a brief review of multifractals in order
       to specify what is a multifractal process. We try to provide several complementary points of view
       and to understand what are the main ingredients for “multi-scaling”. We also comment about
       the criticisms raised by several authors about multifractality in finance. Our second goal is to
       propose a simple multifractal “stochastic volatility” model that captures very well all the above
       mentionned features of financial fluctuations. This model, that has been originally introduced in
       Ref. [18], is compared to real data and some models proposed elsewhere. We discuss its possible
       multivariate extension in order to use it in management applications. The paper is organized
       as follows. The review on multifractal processes is made in section 2. We introduce notations,
       the related notions of multi-scaling, scale-invariance, cascade process and self-similarity kernel.
       We illustrate our purpose using empirical estimates for some high frequency financial data. In
       section 3 we review some findings of Ref. [10] concerning the magnitude correlations for cascade
       models and suggest a link with 1/f processes as recently observed in financial time series. In
       section 4 we introduce the multifractal random walk defined in Ref. [18] as a stochastic volatility
       model. We discuss its main properties and propose a natural multivariate generalization. Our
       discussion is illustrated by numerical simulations. In section 5 we propose estimators for the
       few parameters of our model and compute them for some intraday and daily time series. In
       section 6 we discuss some related works about multifractality in finance. Conclusions and some
       prospects are reported in section 7.


       2     Multifractal processes and cascade models
       In this section we briefly discuss the related notions of multifractality and multiplicative cas-
       cade. Most of the ideas and concepts that we recall below have been introduced in the field
       of fully developed turbulence where people aim at accounting for the so-called “intermittency
       phenomenon” (for a review of this subject see e.g., [21]).

       2.1    Multifractality of financial time series
       Let us consider the variations of a stochastic process X(t) at a time scale l. For that purpose,
       one can consider the increments of the process, δl X(t) = X(t + l) − X(t) or more generally its
       wavelet transform [22, 23, 24]
                                                      Z  ′   
                                                   −1    t −t
                                      T (t, l) = l     ψ        X(t′ )dt′
                                                            l
       where ψ(t) is the so-called analyzing wavelet, i.e, a function well localized in both Fourier and
       direct spaces2 . Let us denote M (q, l) the order q absolute moment of δl B(t) or T (t, l), (in this
       paper E(.) will be used for the mathematical expectation and we will always suppose that the
       considered processes has stationary increments)

                                               M (q, l) = E(|δl X(t)|q ) .                                    (1)

       We will say that the process is scale-invariant, if the scale behavior of the absolute moment
       M (q, l) is a power law. Let us call ζq the exponent of this power law, i.e.,

                                                   M (q, l) ∼ Cq lζq ,                                        (2)
   2
    One nice property of wavelet transform is that it can be inverted, i.e., one can recover the original signal from its
wavelet coefficients. Another interesting feature is that there exist orthonormal wavelet bases. Such bases are very
useful for signal synthesis and modelling, as it is illustrated for cascade processes in Ref. [33]


                                                           2
Figure 1: Multifractal Analysis of the intraday future S&P500 index over the period
1988-1999. (a) Plot of the original index time-series. The analyzed time-series is the detrended
and de-seasonalized logarithm of this series. (b) Log-log plots of M (q, l) versus l for q = 1, 2, 3, 4, 5.
The time scales l range from 10 minutes to 1 year. (c) log2 (M (q, l)/M (1, l)q ) for q = 2, 3, 4, 5. Such
plots should be horizontal for a process that is not multifractal. (d) ζq spectrum for the S&P 500
fluctuations. The plot in the inset is the parabolic nonlinear part of ζq .




                                                    3
       where Cq is a prefactor that will be interpreted below. The process is called monofractal if
       ζq is a linear fonction of q and multifractal if ζq is nonlinear. Note that, from the concavity
       of the moments of a random variable, it is easy to show that ζq , as defined from the scaling
       behavior (2) in the limit l → 0+ , is necessarily a convex fonction of q. The same argument leads
       to the conclusion that such scaling behavior with a nonlinear ζq cannot hold for all scales l.
       Thus, for a multifractal process there exists at least one characteristic time T (hereafter referred
       to as the integral time) above which the behavior (2) is no longer valid. Multifractality has
       been introduced in the context of fully developed turbulence in order to describe the spatial
       fluctuations of the fluid velocity at very high Reynolds number [21]. As suggested by recent
       studies [9, 10, 13, 15, 16], multifractality is likely to be a pertinent concept to account for the
       prices fluctuations in financial time-series. This is illustrated in Fig. 1 where the ζq function
       is estimated for the future S&P500 index over the period 1988-1999. The original intraday
       time-series has been sampled at a 10 mn rate (Fig. 1(a)) in order to obtain equi-sampled data.
       We consider the associated continuously compounded return time-series, (i.e., the logarithm of
       the index value) that has been detrended and de-seasonalized3. The ζq spectrum in Fig. 1(c)
       is obtained using linear regression fit of “log-log” representations of the behavior of the q-th
       order moment versus the time scale as illustrated in Fig. 1(b). In this figure, the scales span an
       interval from 10 minutes to approximately 1 year. Moment estimates at larger time scales are
       very poor because of the finite size of the overall record. From the linear behavior of such curves,
       one clearly sees that the scale-invariance hypothesis is satisfied over around 3 decades. In Fig.
                                   M(q,l)
       1(b) we have plotted log2 M(1,l) q versus log2 (l). The fact that such plots are not constant reflects

       the nonlinearity the ζq spectrum. The future S&P500 can thus be considered, at least at this
       description level, as a multifractal signal. Let us notice that we have computed, in Fig. 1(d), the
       ζq values for q-th order moments that include negative values of q. This can be achieved using
       a wavelet based technique that has been introduced in Refs. [25, 26, 27, 28]. This spectrum
       turns out to be well fitted by a parabolic shape ζq = 0.53q − 0.015q 2. The non linear parabolic
       component of ζq has been plotted in the inset of Fig. 1(d).

       2.2 Multifractal processes, self-similar processes and multiplicative
       cascades.
       Multifractality (in the sense defined above) is a notion that is often related to an underlying
       multiplicative cascading process. In the context of deterministic functions the situation is rather
       clear since the analyticity of the ζq spectrum is deeply connected to the self-similarity properties
       of the function [26, 27, 28, 29]. Roughly speaking, a function is self-similar if it can be written as
       a multiplicative cascade in an appropriate space-scale (or time-scale) representation [27, 26, 29].
       In that context, the so-called multifractal formalism is valid, i.e., one can relate the ζq spectrum
       to the D(h) singularity spectrum that provides information about the statistical distribution
       of singularity (Hölder) exponents h. The things are somehow more complex for stochastic
       processes. One of the goals of this paper is to provide some simple elements about this subject.
           In the mathematical literature, a process X(t) is called self-similar of exponent H if ∀λ > 0,
       λ−H X(λt) is the same process as X(t). According to this definition, the Brownian motion is
       self-similar with an exponent H = 1/2. This definition is however too restrictive for our purpose
       since it excludes multifractal processes. Indeed, let us consider Pl (δX) the probability density
       function (pdf) of δl X(t)4 . If X(t) is self-similar with an exponent H, then it is easy to prove
   3
     The amplitude of the return variations in each intraday period is normalized according to the estimated U-shaped
intraday r.m.s.
   4
     Note that from stationarity of the increments, the law of δl X(t) is the same as the law of X(l) if one assumes
that X(0) = 0.




                                                         4
      that
                                            Pl (δX) = λH Pλl (λH δX) .                                    (3)
      Then, the moments at scale l and L = λl are related by
                                                       qH
                                                        l
                                        M (q, l) = Cq        ,                                            (4)
                                                        L

      with Cq = M (q, L). Thus one has a “monofractal” process with ζq = qH. In order to account for
      multifractality, one has to generalize this classical definition of self-similarity. This can be done
      by introducing a weaker notion, as originally proposed in the field of fully developed turbulence
      by B. Castaing and co-authors [31]. According to Castaing’s definition of self-similarity, a
      process is self-similar if the increment pdf’s at scales l and L = λl (λ > 1) are related by the
      relationship [31, 32]:                  Z
                                    Pl (δX) =     Gl,L (u)e−u PL (e−u δX)du ,                             (5)

      where the self-similarity kernel Gl,L depends only on l/L. Let us note that this definition
      generalizes Eq. (3) that corresponds to the “trivial” case Gl,L (u) = δ(u − H ln(l/L)). This
      equation basically states that the pdf Pl can be obtained through a “geometrical convolution”
      between the kernel Gl,L and the pdf PL . A simple argument shows that the logarithm of the
      Fourier transform of the kernel Gl,L can be written as Fl,L (k) = ln Ĝl,L (k) = F (k) ln(l/L) 5 .
      Thus, from Eq. (5), one can easily show that the q order absolute moments at scales l and L
      are related by:
                                                                       F (−iq)
                                                                       l
                            M (q, l) = Ĝl,L (−iq)M (q, L) = M (q, L)            ,                  (6)
                                                                       L
      and then Cq = M (q, L) and ζq = F (−iq). A nonlinear ζq spectrum implies that F is nonlinear
      and thus that G is different from a Dirac delta function6 . For example, the simplest non linear
      case is the so-called log-normal model that corresponds to a parabolic ζq function and thus to
      a function G that is Gaussian.
          The equation (5) can be interpreted as follows: the pdf at scale l, Pl is written as a weighted
      superposition of the rescaled versions of the pdf at scale L, PL , the self-similarity kernel Gl,L
      being the associated distribution of weights. In the case of a monofractal process as described
      by Eq. (3), a single value of u is sufficient in the equation (5) since Pl and PL have the same
      shape and differ only by the scale factor e−u = (l/L)H = λH . This explains the Dirac function
      for the kernel G. This situation can be easily generalized by considering other shapes for the
      kernel Gl,L . In that case, the shapes of the pdf Pl across scales are no longer the same: when
      going to small scales, fat tails emerge and the pdf become strongly leptokurtic (see Refs. [9, 31]
      or Fig. 4).
          Let us now make the link with multiplicative cascades. This can be easily done if one consider
      discrete scales ln = 2−n L. Let us suppose that the local variation of the process δln X at scale
      ln is obtained from the variation at scale L as
                                                       n
                                                             !
                                                      Y
                                         δln X(t) =       Wi δL X(t)                                  (7)
                                                        i=1

      where Wi are i.i.d. random positive factors. This is the cascade paradigm. Realizations of such
      processes can be constructed using orthonormal wavelet bases as discussed in Ref. [33]. If one
   5
     It essentially results from the fact that Gl,L depends only on l/L and satisfies the semi-group composition law
Gl1 ,l3 = Gl1 ,l2 ∗ Gl2 ,l3 where l1 ≤ l2 ≤ l3 and ∗ is the convolution product [31, 32].
   6
     Note that from the above mentionned semi-group property, the Levy theorem [30] implies that G is necessarily
an infinitely divisible law


                                                         5
defines the magnitude ω(t, l) at time t and scale l as the logarithm of “local volatility” [10]:
                                                 1
                                     ω(t, l) =     ln(|δl X(t)|2 ),                                (8)
                                                 2
then the previous cascade equation becomes a simple random walk equation, at fixed time t,
versus the logarithm of scales:

                                ω(t, ln+1 ) = ω(t, ln ) + ln(Wn+1 ) .

If the noise ln Wi is normal N (µ, λ2 ), the pdf of ω, Pl (ω), thus satisfies a simple diffusion
equation with a Gaussian kernel:

                               Pln (ω) = N (µ, λ2 )∗n ∗ pL (ω)
                                                           
                                                                                             (9)

where ∗ is the convolution product. Going back to the original variable δX, the previous
equation corresponds exactly to Castaing’s formulation of self-similarity (5) with the log-normal
propagator:
                              Gln ,L = N (µ, λ2 )∗n = N (nµ, nλ2 ) .
Conversely, let us consider a process that satisfies Castaing’s equation with a normal kernel G.
This means that one can write,
                                       δl X(t) ≡ W δ2l X(t)                                 (10)
where ≡ means the equality in law of the two random variables and W is a log-normal random
variable which mean µ and variance λ2 do not depend on l. By iterating this equation n times,
one thus recover, at least heuristically, the cascade equation (7). Thus, the cascade picture across
scales, constitutes a kind of paradigm of non-trivial self-similar processes. As explained in Ref.
[18], the problem with such processes is that they involve representations (e.g., orthonormal
wavelet bases) that are constructed on a discrete set of scales (e.g., dyadic scales ln = 2−n ) and
in turn cannot be invariant under continuous scale dilations.


3    Magnitude correlations and 1/f spectra
We have seen in the previous section that multifractality can be interpreted as a diffusion of
the magnitude of the variations of the return from large time scales to small time scales. In the
financial framework, magnitudes at all scales are nothing but a logarithmic representation of
local volatilities. In this section we would like to address the problem of volatility correlations.
The “heteroskedastic” nature of financial time-series is now a well established empirical fact.
Volatility possesses long-range positive correlations: periods of strong activity alternate with
quiet periods. A lot of models have been proposed to account for this phenomenon from the
famous GARCH models to various stochastic volatility models. Let us proceed with the multi-
fractal and cascade picture and study what kind of correlations are associated to these models.
This problem has already been considered by Arneodo, Muzy and Sornette in Ref. [10] (see
also Refs [33, 34]). These authors have shown that a log-normal cascade model on the dyadic
tree associated to the orthonormal wavelet representation leads naturally to magnitude corre-
lation functions Cω (l, τ ) = Cov(ω(t, τ ), ω(t + l, τ )) that behave as −λ2 ln(l/T ) for T > l > τ .
This behavior has been shown to provide good fits of the empirical estimates of the correlation
functions from real data [10]. In Fig. 2 is reported the magnitude correlation function Cω (l, τ )
(we choose τ = 10 min) of the S&P500 time series studied in Fig. 1. One can see that, when
plotted versus the logarithm of the time lag, ln(l), the correlation function decreases linearly
with a slope λ2 ≃ 0.025. The intercept of such straight line provides an estimator of the integral
time T that is, in our case, approximately T ≃ 3 years (note that because we get an estimate


                                                   6
Figure 2: Magnitude correlation function of the S&P 500 future. (a) Cω (l, τ ) versus l for
τ = 10 min. The solid line represents a fit according to the cascade model logarithmic expression.
(b) Cω (l, τ ) versus ln(l). The cascade model predicts a linear behavior that crosses the y-axis at
ln(l) = ln(T ). The small scale cross-over is due to the smoothing window used to estimate the local
magnitude ω(t, τ ).




                                                 7
of ln(T ) the error on the value of T is very large). We have checked that those results are
stable when changing the reference time τ for return calculation. As it will be illustrated in
section 5, for various financial time series, the “cascade ansatz” is very pertinent to describe the
volatility correlations. Let us notice that the very slow (logarithmic) decrease of the correlation
functions for time lags below the integral time T , is reminiscent of the ultrametric nature of
the tree naturally associated to the time-scale (or time-frequency) representation [10, 33, 34].
Moreover, let us remark that, as far as power spectrum is concerned, Gaussian processes with
such correlation functions can be seen as “1/f ” processes. Indeed, if the correlation function is
given by the above expression, the power spectrum can be shown to reduce to
                                                  Z Tf
                                            2 −1
                                 S(f ) = 2λ f          x−1 sin(x)dx .                           (11)
                                                  0

In the high frequency limit f → +∞, we then have S(f ) ∼ λ2 πf −1 . Another intuitive way
to understand this property, comes from the fact that the logarithmic decay of the correlation
function can be understood as the limit H → 0 in the power-law correlation function k −2H of a
fractional gaussian noise of exponent H. This property will be explicitely used in the discussion
of section 6.3. Let us finally remark that 1/f spectra have been observed in a wide range
of applications [35]. Recently, Bonanno et al. [20] suggested the possible pertinence of such
processes to account for the fluctuations of the number of trades of different stocks.


4     A simple solvable multifractal model
As emphasized previously, multiplicative cascade models represent the paradigm of multifrac-
tal processes in that they contain the main ingredient leading to multifractality, i.e, the scale
evolution of the magnitudes, from coarse to fine scales, is a random walk. Besides the problems
of continuous scale invariance and stationarity of standard hierarchical constructions of such
processes, they cannot be formulated using a stochastic evolution equation as one would expect
for a model for financial time series. In this section we propose a “stochastic volatility” model
that has been introduced in Ref. [18], that does not possess any of these drawbacks: it has
stationary increments, it has log-normal multifractal properties and is invariant under contin-
uous dilations. The key idea underlying this model is that the stochastic volatility possesses,
as for cascading processes, a “1/f ” spectrum, or, more precisely, a correlation function with a
logarithmic behavior.

4.1    The multifractal random walk
Let us briefly recall the construction of the multifractal random walk (MRW) proposed in [18].
A discretized version of the model X∆t (using a time discretization step ∆t) is built by adding
up t/∆t random variables :
                                                t/∆t
                                                X
                                      X∆t (t) =      δX∆t [k],
                                                  k=1
where the process {δX∆t [k]}k is a noise whose variance is stochastic, i.e.,
                                     δX∆t [k] = ǫ∆t [k]eω∆t [k] ,                              (12)
where ω∆t [k] is the logarithm of the stochastic variance. More specifically, we will choose ǫ∆t to
be a gaussian white noise independent of ω and of variance σ 2 ∆t. The choice for the process ω∆t
introduced in [18], is dictated by the cascade picture. It corresponds to a gaussian stationary
process whose covariance can be written
                              Cov(ω∆t [k], ω∆t [l]) = λ2 ln ρ∆t [|k − l|]

                                                  8
where ρ∆t is chosen in order to mimic the correlation structure observed in cascade models with
an integral time T :                     T
                                      (|k|+1)∆t  for |k| ≤ T /∆t − 1
                          ρ∆t [k] =
                                      1          otherwise
Hereafter, we will refer to the process ω(t) as the “magnitude process”. In order the variance of
X∆t (t) to converge when ∆t → 0, one must choose the mean of the process ω∆t such that [18]

                          E (ω∆t [k]) = −Var (ω∆t [k]) = −λ2 ln(T /∆t),

for which we find Var(X∆t (t)) = σ 2 t. Let us review the multifractal properties of MRW.

4.2    ζq spectrum: computation of the moments
The qth-order moment of the increments of the MRW can be computed. Since, by construction,
the increments of the model are stationary, the law of X∆t (t + l) − X∆t (t) does not depend on t
and is the same law as X∆t (l). In Ref. [18], it is proven that the moments of X(l) ≡ X∆t→0+ (l)
can be expressed as

                                  σ 2p (2p)! l
                                            Z            Z l     Y                2
                    E(X(l)2p ) =      p
                                                du 1 ...     dup     ρ(ui − uj )4λ ,         (13)
                                     2 p!    0            0      i<j

where ρ is defined by                       
                                                T /|t| for |t| ≤ T
                                   ρ(t) =                          .
                                                1      otherwise
Using this expression in the above integral, a straightforward scaling argument leads to
                                                p−2p(p−1)λ2
                                                l
                               M (2p, l) = K2p                ,                                     (14)
                                                T
where we have denoted the prefactor
                                                Z 1             Z 1         Y                 2
                            p 2p
                   K2p = T σ (2p − 1)!!               du1 ...         dup         |ui − uj |−4λ .   (15)
                                                 0               0          i<j

Note that K2p is nothing but the moment of order 2p of the random variable X(T ) or equivalently
of δT X(t). From the above expression, we thus obtain

                                      ζ2p = p − 2p(p − 1)λ2

and by analytical continuation, the corresponding full ζq spectrum is thus the parabola

                                     ζq = (q − q(q − 2)λ2 )/2 .                                     (16)

Let us remark that one can show that Kq = +∞ if ζq < 0 (i.e., q > 2 + 1/λ2 ) and thus the
pdf of δl X(t) have fat tails [18]. In order to control the order of the first divergent moment
(without changing λ), one could simply choose for the ǫ∆t ’s a law with fat tails. Indeed, the
prefactor σ 2p (2p − 1)!! in Eq. (15) comes directly from the fact that the ǫ∆t ’s have been chosen
to be Gaussian. Using instead fat tail laws (e.g., t-student laws) would allow us to control the
divergence of this prefactor.
    In Fig. 3 we have estimated the scaling behavior of the absolute moments M (q, l) for a
discrete simulation of a MRW (Fig. 3(a)). In order to simulate the sampling of a time continuous
MRW, we have generated a discretized MRW using ∆t << 1 and then subsampled it at the

                                                        9
sample period 1. Using this procedure, we have generated a 217 long time-series using the
parameters ∆t = 1/16, T = 215 , σ 2 = 1 and λ2 = 0.03. In Fig. 2(b), we have plotted, in double
logarithmic representation M (q, l) versus l for different values of q. In these representations, the
linear behavior of each moment indicates that the scaling hypothesis is verified. The estimation
of ζq (made by estimating the slope of each of such curve) is reported in Fig 2(c). As expected
this spectrum is a parabola that is in very good agreement with expression (16).
    It is clear that the same power law scaling does not stand when l goes to +∞. Since ρ(l) = 1
for large l (as compared to T ), we get

                                                 σ 2p (2p)! l
                                                           Z           Z l
                           E(X(l)2p ) ∼l>>T                   du 1 ...     dup
                                                    2p p!   0           0
                                         ∼      Clp

Thus, there is a cross-over from the parabolic multifractal behavior at time scales l ≤ T which
is described by Eq. (16) to the Brownian-like behavior at larger time scales (l >> T )

                                              ζq = q/2 .

    In Eq. (6), we have shown that there exists a deep link between the self-similarity kernel
and the ζq spectrum. This suggests that the probability distribution functions of our model
satisfy Castaing’s equation when going from large to small time scales with a gaussian kernel
Gl,T . Thus, as far as the increment pdf at different time scales are concerned, they will satisfy
an evolution equation from “quasi-Gaussian” at very large scale (l >> T ) to fat tailed pdf’s at
small scales. This transformation of the pdf’s is illustrated in Fig. 4(a) where are plotted, in
logarithmic scale, the standardized pdf’s (the variance has been set to one) for different time
scales in the range [1, 4T ]. The pdf’s have been estimated for 500 realizations of size 217 of MRW
with parameters λ2 = 0.03 and T = 213 . In solid line, we have superimposed the Castaing’s
transformation obtained from the coarse scale pdf (at scale T ) using the appropriate normal
self-similarity kernel. If Fig. 4(b) we have reproduced similar analysis for the S&P500 future
variations. Besides statistical convergence limitations, one can observe the same features as in
Fig. 4(a).

4.3     Volatility and magnitude correlation functions
4.3.1    Volatility correlation functions
As recalled in the introduction, increments of financial time series are well known to be uncorre-
lated (for time lags large enough) while their amplitude (“local volatilities”) possesses power-law
correlations. Let us show that our model satisfies these two properties at all time scales smaller
than the “integral time” T . By construction, the increment correlation function,

                        h(X∆t (t + τ ) − X∆t (t))(X∆t (t1 + τ1 ) − X∆t (t1 ))i

(∀ |t1 − t| > τ ), is zero in our model. Let us study the correlation function of the squared
increments. Since the increments are stationary, we can choose arbitrarily t1 = 0. Thus we need
to compute, in the limit ∆t → 0, the following correlation function, that corresponds to a lag l
between increments of size τ

                           C(l, τ ) = h(X∆t (l + τ ) − X∆t (l))2 X∆t (τ )2 i.                   (17)

From the results of Ref. [18] and in the case 0 ≤ l < T , 0 ≤ τ + l < T , we get,
                                         Z l+τ    Z τ
                                                                  2
                          C(l, τ ) = σ 4       du     dvρ(u − v)4λ .
                                          l         0


                                                  10
Figure 3: Multifractal Analysis of a MRW sample. (a) Plot of a sample time serie of length
217 . The sampling size and the trend amplitude have been chosen arbitrarily to be compared to
fig 1(a). (b) Log-log plots of M (q, l) versus l for q = 1, 2, 3, 4, 5. The time scales l range from few
minutes to one year. (c) ζq spectrum estimation (dots) and comparison to prediction as given by
Eq. (16) (solid line).




                                                  11
Figure 4: Continuous deformation of increment pdf ’s across scales. (a) MRW Model.
Standardized pdf’s (in logarithmic scale) of δl X(t) for 5 different time scales (from top to bottom),
l = 16, 128, 2048, 8192, 32768. These pdf’s have been estimated on 500 MRW realizations of 217
sampled points with λ2 = 0.03, ∆t = 1/16 and T = 8192. One can see the continuous deforma-
tion and the appearance of fat tails when going from large to fine scales. In solid line, we have
superimposed the deformation of the large scale pdf using Castaing’s equation (5) with the normal
self-similarity kernel. This provides an excellent fit of the data. (b) S&P 500 future. Standardized
pdf’s at scales (from top to bottom) l = 10, 40, 160 min, 1 day, 1 week and one month. As in Fig.
(a) the scale is logarithmic and plots have been arbitrarily shifted along vertical axis for illustration
purpose. Notwithstanding the small size of the statistical sample (as compared to (a)), one clearly
sees the same phenomenon as for the MRW. The fact the Castaing’s equation (5) allows one to
describe the pdf’s deformation across time scales of financial assets has originally been reported in
Ref. [9] where similar plots for FX rates can be found.




                                                   12
A direct computation shows that
                                     R l+τ     Rτ             2

                                      l
                                             du 0 dv|u − v]−4λ =
                              1                  2−4λ2               2        2
                       (1−4λ2 )(2−4λ2 ) ((l + τ )      + (l − τ )2−4λ − 2l2−4λ ),

and consequently
                                                     2                 2     2
                        C(l, τ ) = K(|l + τ |2−4λ + |l − τ |2−4λ − 2|l|2−4λ )                 (18)
where                                                          2
                                                    σ 4 T 4λ
                                      K=                           .
                                              (1 − 4λ2 )(2 − 4λ2 )
Let us note that in the usual case 0 ≤ τ << l, one gets
                                                       −4λ2
                                                       l 4 2
                                       C(l, τ ) ≃ σ τ                                         (19)
                                                       T

i.e., for fixed τ , the volatility correlation function scales as

                                               C(l) ∼ l−2ν                                    (20)

with ν = 2λ2 . From the estimates λ2 ≃ 0.025 − 0.05 for financial assets (see section 5), one thus
obtains ν ≃ 0.05 − 0.1, values very close to the ones observed empirically in many works.

4.3.2    Power of returns and magnitude correlation functions
Let us now show that magnitude correlation functions behave as expected, i.e, decrease very
slowly as a logarithmic behavior.
   For that purpose, the previous computation of the correlation function can be extended to
the power of returns |X∆t (l+τ )−X∆t (τ )|p . Several empirical works have concerned the study of
such “generalized volatilities” and people often noticed variations of amplitude of the correlation
and of the power-law exponent νp when varying the order p [37]. In Ref. [18], it is shown that
the quantity,
                          Cp (l, τ ) = h|X∆t (l + τ ) − X∆t (l)|p |X∆t (τ )|p i ,              (21)
behaves, when τ is small enough, as
                                                      τ 2ζp  l −λ2 p2
                                  Cp (l, τ ) ∼ Kp2                                            (22)
                                                         T         T

where the constant Kp has been defined previously. Using analytical continuation of the behavior
of Cp in the limit p = ǫ → 0, we can obtain, from previous expression, the behavior of the
magnitude correlation function Cω (l, τ ):

                                                                           l
                         Cω (l, τ ) ≃ ǫ−2 Cǫ (l, τ ) − M (ǫ, τ )2 ∼ −λ2 ln( ) .
                                                                 
                                                                                              (23)
                                                                           T
The magnitude correlation function, for τ small enough, has thus the same behavior as the
correlation function of the underlying magnitude process ω∆t . This result is checked in Fig. 4
where we have plotted the magnitude correlation function for τ = 32∆t as a function of ln(l).
This correlation function has been estimated using a single realization of the process of 217
sampled points, i.e, 16 integral scales. The linear behavior we obtain is exactly the same one
as predicted from Eq. (23) and Fig. 2. Measures of the slope and the intercept of such straight
line provide a good estimate of respectively λ2 and T .

                                                         13
Figure 5: Magnitude correlation function of the model. The correlation function has been
estimated on 16 integral scales (see text). In continuous line we have superimposed the correlation
function of the magnitude process ω∆t that is involved in the stochastic volatility.


     4.4    Extension to a multivariate process
     In order to account for the fluctuations of financial portfolios and to consider management
     applications of our approach, it is important to build a multivariate, i.e. a vector valued,
     version of the previous multifractal random walk. Since only gaussian random variables are
     involved in the construction of section 4, this generalization can be done by considering two
     uncorrelated gaussian random vectors ǫ∆t (t) and ω∆t (t) whose covariance matrices are denoted
     respectively Σ and Λ. Hereafter, we will refer to these matrices as respectively the “Markowitz
     matrix” Σ and the “multifractal matrix” Λ. One can then define the multivariate multifractal
     random walk (MMRW) X(t) ~    as:

                                       Xi (t + ∆t) − Xi (t) = ǫi (t)eωi (t) ,                        (24)

     with Cov(ǫi (t), ǫj (t + τ )) = δ(τ )Σij and Cov(ωi (t), ωj (t + τ )) = Λij ln(Tij /|∆t + |τ |) (note
     that the previously defined coefficients σ 2 and λ2 for an asset i correspond respectively to the
     diagonal elements Σii and Λii ). Let us briefly review some of the properties of this model,
     postponing its detailed analysis to a forthcoming publication [17]. A quantity that will be of
     central interest is the k-point joint moment of order q1 , q2 , ..., qk that can be defined as:

                              Mi1 ,...,ik (q1 , ..., qk ) = E (|Xi1 (l)|q1 ...|Xik (l)|qk ) .        (25)

     When k = 2, by denoting i1 = i, i2 = j, q1 = p and q2 = q, let us define the joint scaling
     exponent spectrum as:
                                 Mi,j (p, q) = Ci,j (p, q)lζi,j (p,q) .                    (26)
     This spectrum can be computed analytically. If the matrix Σ is diagonal (the ǫi ’s are uncorre-
     lated), a straightforward calculation shows that the scaling exponent ζi,j (p, q) is the following:

                                       ζij (p, q) = ζi (p) + ζj (q) − Λij pq ,                       (27)

     where ζi (q) is the ζq spectrum for the component Xi (t). Thus, for uncorrelated ωi ’s, one has
     ζij (p, q) = ζi (p) + ζj (q) while for the extreme case ωi = ωj , the exponent becomes ζij (p, q) =
     ζi (p + q) = ζj (p + q). The computation of the scaling exponent is trickier for general Markowitz

                                                           14
and multifractal matrices. Under some mild conditions that are necessary for the existence of
a non trivial limit ∆t → 0+ , one can show that the previous scaling law remains valid even for
non diagonal matrix Σ [17].
    In order to define a simple way to get an estimate of the multifractal covariance coefficient
Λij , let us define the moment ratio:

                                           E(|Xi (l)|q |Xj (l)|q )
                           Rij (q, l) =                              ∼ lκij (q)                (28)
                                          E(|Xi (l)|q )E(|Xj (l)|q )

From Eq. (27), the value of κij (q) is simply

                                           κij (q) = −Λij q 2 .                                (29)

Thus, the non-diagonal element in the multifractal matrix Λ corrresponds to the nonlinear
behavior of the exponent spectrum κ(q) of the moment ratio R. Along the same line as for the
computation of the magnitude auto-correlation in previous section, one can get the correlation
function of magnitudes ωi (t, l) and ωj (t, l) from the limit q → 0 of Rij (q, l):

                             Cov(ωi (t, l), ωj (t, l)) ∼ −Λij ln(l) + C ,                      (30)

where C is a constant related to Tij [17]. Thus the scale behavior of the magnitude covariance
provides an estimate of the multifractal correlation coefficient Λij . This is the generalization of
the classical result in multifractal analysis that relates the intermittency coefficient λ2 = Λii to
the scale behavior of the variance of the magnitude.
   Let us remark that the covariance of the variations of the assets i and j can be obtained by
a direct calculation:
                                                        1
                            Cov(Xi (l), Xj (l)) = Σij e 2 (Λii +Λjj −2Λij ) l .                 (31)
This covariance between Xi (t) and Xj (t) thus depends not only on Σ, the “Markowitz” co-
variance matrix, but also on the multifractal matrix Λ. This expression, allows us to get an
estimate of the value of Σij once the values of Λ are known.
    Finally, let us mention that the idea of “multivariate multifractality” has been recently intro-
duced in Ref. [19] where the authors propose a phenomenological generalization of Castaing’s
equation to the multivariate setting. Evidences that financial assets are characterized by non
trivial multifractal matrices are also provided. We are currently working to obtain further em-
pirical evidences towards such conclusions. Moreover, a precise link between the present model
and the extended Castaing’s approach of Ref. [19] is under progress.


5    Parameter estimation for real financial data
We have seen that the MRW is characterized mainly by 3 parameters: σ 2 , the white noise
variance, T the integral scale and λ2 the magnitude variance. We have shown that this model
is able to reproduce all the main features of the future S&P 500 time series. Natural estimators
of those parameters can be defined from the results of previous section. The parameter λ2
can be obtained from the shape of the ζq spectrum that is itself estimated using the scaling
behavior of the absolute moments M (q, l). This parameter can also be estimated thanks to the
magnitude correlation function Cω (l, τ ) that behaves as −λ2 ln(l/T ). From the intercept of such
correlation function as a function of ln(l), we can define an estimator of the integral scale T .
Finally, the parameter σ 2 can be obtained using the classical relationship Var(δl X∆t (t)) = σ 2 l.
In this section, we report estimates of the multifractal parameters λ2 and T for some financial
time series. We do not have the ambition to provide fine estimates of those parameters. Our
aim is rather to get an idea of realistical values of the parameters of the model for real assets. A


                                                    15
                               Series          Size    λ2         T
                          Future S&P500       7.104   0.025    3 years
                         Future JY/USD        7.104   0.02    6 months
                           Future Nikkei      7.104   0.02    6 months
                         Future FTSE100       7.104   0.02      1 year
                          S&P500 index        6.103   0.024    3 years
                           French index       6.103   0.029    2 years
                           Italian index      6.103   0.029    2 years
                         Canadian index       6.103   0.024    3 years
                          German index        6.103   0.027    3 years
                             UK index         6.103   0.026    6 years
                         hong-kong index      6.103   0.05     3 years

          Table 1: Multifractal paramater estimates for various assets


precise discussion of the properties of various estimators from a statistical point of view is out
of the scope of this paper and will be addressed in a forthcoming publication. Note that similar
empirical study has already been performed in Ref. [19]. We have studied some high frequency
future time series that are sampled at a 10 min rate over the 7 years period from 1991 to 1997.
We have also processed a set of daily index values for 8 different countries over the period from
1973 to 1997. The results are reported in table 1.
    We remark that the values of the multifractal parameter λ2 are all very close to 2.5 10−2
(excepted for the hong-kong index). The integral time T values are centered around 3 years but
with a large spread. Let us notice that we get an estimate of ln(T ) and thus the error on the
estimate of T can be very large. We do not report here the values of the errors and confidence
intervals for the proposed estimators that will be studied elsewhere.


6     Discussion about other approaches and findings
In this section, we make some comments about related studies that concern multifractals and
finance.

6.1    Turbulence and finance
The analogy between turbulence and finance has been originally proposed by Ghashghaie et
al. [9]. These authors proposed to describe the pdf’s of FX price changes at different time
scales in the same way physicists describe the pdf’s of velocity variations at different space
separations in fully developed turbulence. This approach naturally leads to the notions of
cascading process, Castaing’s formula and multifractality as described in section 2. This work
suggests that the key mechanism at the origin of these observations, is an information cascade
according to which short-term traders are influenced by long-term traders. This cascade is the
analog of the Richardson’s kinetic energy cascade in turbulence where small eddies result from
the breakdown of larger ones and so on [21]. If the observations reported in Ref. [10] strongly
support this point of view, its quantitative understanding in terms of “microscopic” mechanisms
remains an open question. In this section we would like to comment about some criticisms that
have been raised about the analogy between turbulence and finance. The first one concerns
the power spectrum behavior in both situations [11, 12, 2]. In turbulence, Kolmogorov theory
predicts a k −5/3 power spectrum that is confirmed in experimental situations. In finance, since


                                               16
price fluctuations are almost uncorrelated, they are characterized by a k −2 spectrum. For a
general multifractal process, the exponent β of the power spectrum behavior can be shown to
be related [27, 28] to the value of ζ2 : β = 1 + ζ2 . Thus, from the cascading process point of view,
nothing prevents the exponent β from being equal to the exponent of the Brownian motion, i.e.,
β = 2. In other words, as examplified by the MRW, a cascading process can have uncorrelated
increments. We could also remark, that in turbulence β = 5/3 has a dimensional origin, i.e., it
is the exponent of the spatial spectrum of velocity fluctuations within an Eulerian description.
If one adopts a Lagrangian description and one is interested by temporal fluctuations of a fluid
particle velocity, then the dimensional value of the power spectrum exponent is β = 2. Thus
the value of this exponent is not a pertinent argument to reject the analogy with turbulence.
Another difference that has been raised in [2] concerns the behavior of the probability of return
to origin Pl (0) that has been shown to possess a scaling regime in finance while its behavior
is more complex for a turbulent velocity field. First of all, let us point out that whatever the
quantity studied (probability of return or absolute moments), it is well known that there is no
observed well-defined scaling regime in turbulence: the classical “log-log” plots always display
some curvature across scales. This curvature is Reynolds number dependent and several studies
suggest that it vanishes, i.e. the field is scale-invariant, only in the limit of infinite Reynolds
number [21, 31, 39]. However, within the cascade paradigm and using Castaing’s equation, the
scaling behavior of the probability of return to origin is easy to show. Indeed, by setting δX = 0
in (5), one obtains, from the definition of ζq and the self-similarity kernel:
                                                                            ζ−1
                                                                            l
                                          Z
                                                          −u
                        Pl (0) = PT (0)       Gl,T (u)e        du = PT (0)        .             (32)
                                                                            T

The exponent for the probability of return to origin is thus simply ζ−1 . For the log-normal
stochastic volatility model introduced in section 4, we thus get
                                                            1+3λ2
                                              Pl (0) ∼ l−     2     .                           (33)

To conclude, neither the power spectrum exponent, nor the scaling behavior of the probability
of return to origin can be used as argument against the existence of a cascading process at the
origin of the fluctuations of financial time series.

6.2    Subordinated processes. Multifractal time
Subordinated processes are Markov processes in a time variable µ(t) that is itself an (increasing)
random process [30]. Such processes have been introduced in finance by Mandelbrot and Taylor
[36] to account for the existence of Levy stable laws as the result of a Brownian motion in
some stochastic time. Today, the idea of modelling financial return fluctuations as a Brownian
motion in a “fractal time, “trading time” or “financial time” can be found in many approaches.
In Refs. [13, 14], the multifractal nature of these fluctuations has been modelled by a (fractional)
Brownian motion subordinated with a multifractal stochastic measure. In this section, without
any concern for rigor, we would like to make a link between our stochastic volatility approach and
the multifractal time approach of Mandelbrot and co-authors. Let us first remark that if we drop
the noise ǫ in Eq. (12) and keep only the stochastic volatility σ(t), we can construct a stochastic
measure µ(dt) that satisfies µ(dt) = eω(t) dt. Using exactly the same kind of computation as in
section 4, one can show that this measure is stationary and its multifractal spectrum τ (q) is

                                              τ (q) = ζ2q − 1 ,                                 (34)

as usually defined by
                                          hµ([0, t])q i ∼ tτ (q)+1 .                            (35)

                                                     17
Let us note that the existence and the construction of such a measure that is stationary and
possesses a continuous scale invariance, was at the heart of the construction in Refs. [13, 14]
and was still an open problem. According to these studies, one can thus construct a multifractal
process by simply considering the subordinated process S(t) = B(µ([0, t])) where B(t) is the
standard Brownian motion. The ζq spectrum of such process would be exactly the same as
the stochastic volatility process defined in section 4. This is not so surprising since, formally,
a differential form for the process S(t) would be dS = dµ    dt dB(µ(t)). If one assumes that a
white noise that is subordinated remains a white noise, one thus obtains dS = eω(t) dB(t) that
is the equation that defines the MRW of section 4. The questions of well-definiteness of this
construction, its statistical properties and the precise mathematical justification of such results,
will be addressed in a forthcoming work.

6.3    Some remarks about Bouchaud, Potters and Meyer’s model
Besides multifractal and cascade pictures, our present approach has been inspired by a recent
paper by Bouchaud, Potters and Meyer [38]. These authors have proposed a model that is very
similar to ours: the stochastic volatility σ(t) instead of being log-normal (eω(t) ) is a normal (ω(t))
random process with long-range (power-law) correlations. By a simple analytical computation,
they have shown that the q-order cumulants of such a process satisfy a simple scaling behavior
but the moments display apparent multiscaling caused by a “competition” between the different
cumulant behavior on a finite scale range. They thus conclude that a distinction between
multifractality and such “apparent multifractality” is a difficult task for finite size time series. As
far as multifractal analysis and modelling of financial time series are concerned, this work is very
interesting and the previous assertion is undoubtedly difficult to infirm. However, let us remark
that in order to illustrate their purpose, Bouchaud et al. choose a “stochastic volatility” σ(t) =
eω(t) instead of their “monofractal” model σ(t) = |ω(t)|. The reason invoked by the authors is
that the log-normal is “a more realistic time series as compared with real data...without changing
the feature of the above model, i.e. the very slow decay of the volatility correlations”. They thus
claim that the scaling features of both models are the same and thus that the multifractality
observed for the simulations of the “log-normal” volatility model is only apparent as predicted
by their theory for the “normal” volatility model. The results reported in section 4 can be used
to show that this interpretation is not correct. Let us indeed reconsider both results of Ref.
[38] and section 4. According to the “normal” volatility model, the moment of order q = 2p is
written in terms of cumulants and behaves as [38]:

                       M (2p, l = N ∆t) = A2p,0 N (1−ν)p + ... + A2,..,2 N p                      (36)

where the constants Aq1 ,..,qk depend only qi , λ2 the variance of ω and ν the exponent for the
correlation function of ω: Cω (l) ∼ l−ν . According to this equation, if N is small enough,
M (2p, l) ∼ l(1−ν)p while, for N very large, M (2p, l) ∼ lp . The transition scale N ∗ (q = 2p) above
which the scaling exponent is ζq = q/2 can be estimated if we define it as the scale where the
contribution to the moment of order q of the cumulant of order 4 and 2 are equal. Using the
expression in Ref. [38] for second and fourth cumulants, C2 and C4 , we can show that at scale
N ∗ (q = 2p), we have (2p − 1)!!C2p ≃ p(p − 1)(2p − 1)!!C2p−2 C4 /6. From the value of C4 , we
obtain (q > 1):
                                                                             1
                                                              +∞
                                                                          ! 2ν
                                                              X
                          ∗                       2 2(ν−1)         2(ν−1)
                       N (q = 2p) = p(p − 1)ν 2                  m                               (37)
                                                             m=1

This function only depends on q and ν and is increasing as q → +∞. Thus, the larger the q value,
the wider the range of scales on which apparent multifractality exists. However, a numerical
computation of the values of N ∗ for ν = 0.2 shows that the value N ∗ ≃ 100 is reached only


                                                  18
       for the moment of order p = 15. The greatest moment value attained in practical situations is
       q ≃ 6, for which N ∗ < 1 ! That means that for all moments less that 10, the model of Bouchaud
       Potters and Meyer predicts the trivial spectrum ζq = q/2 without any cross-over phenomenon.
       For their numerical simulations, they have used a log-normal model. However, within the log-
       normal ansatz, the conclusions of Ref. [38] are questionnable since, when ν is small enough, this
       model is very close to the model introduced in section 4. Let us indeed consider as in [38] that
                                  12 −ν
       Cω (l) ∼ λ2 Γ(ν) cos( πν
                              2 )     l with ν very small7 . By expanding this expression, we obtain

                                                     λ2
                                          Cω (l) =      − λ2 ln(l) + O(ν ln(l)) .                          (38)
                                                     ν

       If we set T = eν
                          −1
                               , then for 1 ≤ l << T , this equation becomes

                                                     Cω (l) = λ2 ln(T /l)                                  (39)

       that is the same correlation function as introduced for the multifractal model in section 4. Let
       us notice that for ν = 0.1 we have T ≈ 2.104 , T ≈ 3.105 for ν = 0.08 and T ≈ 5.108 for ν = 0.05
       !. In this model T is increasing very fast as ν goes to zero. We can thus conclude, that the model
       numerically studied in Ref. [38] can be seen as multifractal from one point of view: whatever
       that scaling range [1, T ], there exists ν small enough (ν ≈ 1/ ln(T )) such that the model displays
       multiscaling with log-normal ζq spectrum in this scale range. According to these remarks, we
       thus think that the multifractal picture is more realistic to describe multiscaling in financial
       time series.


       7     Summary and prospects
       In this paper we have reviewed what are the main features of multifractal processes. We have
       shown that the Multifractal Random Walk is a very attractive alternative to classical cascade
       processes in the sense that it is stationary, continuously scale-invariant and formulated using a
       simple stochastic evolution equation. As a model for financial engineering, MRW are interesting
       for many reasons. First, as illustrated in details for the S&P 500 intraday time series, this model
       is able to reproduce the main empirical properties observed for financial time series. Moreover,
       as Brownian motion and other stable walks, it is a “scale-free” model in the sense that it does not
       have to fit a particular time-scale since it is scale-invariant. This kind of stability with respect
       to time “aggregation” is a serious advantage as compared to classical ARCH-like models which
       parameters strongly depend on the time-scale one is interested in. Moreover, as discussed in
       section 4.4, a simple multivariate formulation of MRW can be proposed. To our knowledge, it is
       the first example of an extension of the notions of multifractality to a vector field. The empirical
       results reported in Ref. [19] suggest that MMRW can be pertinent for portfolio theory. We are
       currently working on applications of MRW to classical problems of finance like management
       problems and option pricing theory.
           From a theoretical point of view, MRW can be seen as the simplest model that contains the
       main ingredients for multifractality. In that respect, it can be very helpful to elucidate, in many
       fields where multiscaling is observed, what are the generic mechanisms that are involved leading
       to “non-trivial” self-similarity properties. Various “microscopic” models, as proposed in finance
       or other fields, could be considered within this perspective. It could also be interesting to recast
       our approach within a field theoretical formulation involving some renormalization procedure.
   7
    Notice that there is no reason to consider the same value of ν for the normal and log-normal models. The results
of this paper suggest that, in finance, the value for the correlation exponent in the log-normal model is very close to
zero and significantly smaller than 0.2



                                                             19
From a mathematical point of view, this problem is deeply linked to the existence of a limit
stochastic process when the sampling time ∆t goes to zero. The convergence of the moments is
not sufficient to prove this non trivial assertion. Such a limit could be very useful to develop a
new stochastic calculus within which, for example, one could formulate the model of multifractal
time of Mandelbrot and co-authors very naturally (see section 6.2). Finally, in a forthcoming
work, we will discuss the generalization of such approach to other laws than the (log-)normal.

Acknowledgement
We acknowledge Matt Lee and Didier Sornette for the permission to use their financial data.
We are also very grateful to Alain Arneodo, Jean-Philippe Bouchaud and Didier Sornette for
interesting discussions and remarks.
    All the computations in this paper have been made using the free GNU licensed sofware
LastWave [40].


References
 [1] J.P. Bouchaud and M. Potters,Theory of financial risk: From statistical physics to risk
     management (Cambridge University Press, Cambridge, 1999).
 [2] R. Mantegna and H.E. Stanley, An introduction to econophysics (Cambridge University
     Press, Cambridge, 2000).
 [3] J.D. Farmer, Computing in Science & Engineering, Nov. 1999, 26. and references therein.
 [4] B.B. Mandelbrot, J. Business, 36 1963, 394.
 [5] E.F. Fama, J. Business, 38 1965, 34.
 [6] R.F. Engle,Econometrica, 50 1982, 987.
 [7] T. Bollersev, R.Y. Chous and K.F. Kroner, J. Econometrics, 52 1992, 5.
 [8] R.N. Mantegna and H.E. Stanley, Nature, 376 1995, 46.
 [9] S. Ghashghaie, W. Breymann, J. Peinke, P. Talkner and Y. Dodge, Nature, 381, 1996, 767.
[10] A. Arneodo, J.F. Muzy and D. Sornette, Eur. Phys. J. B, 2 1998, 277
[11] R.N. Mantegna and H.E. Stanley, Nature, 383 1996, 587.
[12] A. Arneodo, J.P. Bouchaud, R. Cont, J.F. Muzy, M. Potters and D. Sornette, Com-
     ment on “Turbulent cascades in Foreign exchange markets”, preprint cond-mat/9607120
     at xxx.lanl.gov .
[13] A. Fisher, L. Calvet and B.B. Mandelbrot, Multifractality of the deutschmark/us dollar
     exchange rate, Cowles Foundation Discussion Paper, 1997.
[14] B.B. Mandelbrot, Scientific American 280, 70 (1999).
[15] M.E. Brachet, E. Taflin and J.M. Tchéou scaling transformation and probability distribu-
     tions for financial time series, preprint cond-mat/9905169, 1999.
[16] F. Schmitt, D. Schwertzer and S. Levejoy, Multifractal analysis of Foreign Exchange data,
     preprint, Mc Gill University, Montreal 1999.
[17] E. Bacry, J. Delour and J.F. Muzy, in preparation.
[18] E. Bacry, J. Delour and J.F. Muzy, A multifractal random walk, Submitted to Phys. Rev.
     Lett. (April 2000).
[19] J.F. Muzy, D. Sornette, J. Delour and A. Arneodo, Hierarchical portfolio theory and inter-
     temporal stability, preprint (January 2000).


                                               20
[20] G.Bonanno, F. Lillo and R. Mantegna, Dynamics of the number of trades of financial
     securities, preprint cond-mat 991212006 at xxx.lanl.gov/.
[21] U. Frisch, Turbulence (Cambridge University Press, Cambridge, 1995).
[22] Y. Meyer, Ondelettes (Hermann, Paris, 1990).
[23] I. Daubechies, Ten lectures on wavelet (SIAM, Philadelphia, 1992).
[24] S. Mallat,A wavelet tour in signal processing (Academic Press, New-York, 1998).
[25] J.F. Muzy, E. Bacry and A. Arneodo, Phys. Rev. Lett. 67, 3515 (1991).
[26] E. Bacry, J.F. Muzy and A. Arneodo, J. Stat. Phys. 70, 635 (1993).
[27] J.F. Muzy, E. Bacry and A. Arneodo, Int. J. of Bif. and Chaos 4, 245 (1994).
[28] A. Arneodo, E. Bacry and J.F. Muzy, Physica A 213, 232 (1994).
[29] S. Jaffard, SIAM J. Math. Anal. 28, 944 (1997); SIAM J. Math. Anal. 28, 971 (1997).
[30] W. Feller, An introduction to probability theory and its applications, Vol 2. (John Wiley &
     Sons, New-York, 1971).
[31] B. Castaing, Y. Gagne and E. Hopfinger, Physica D 46, 177 (1990); B. Chabaud, A. Naert,
     J. Peinke, F. Chillà, B. Castaing and B. Hebral, Phys. Rev. Lett. 73, 3227 (1994).
[32] A. Arneodo, S. Roux and J.F. Muzy, J. Phys. II France 7, 363 (1997).
[33] A. Arneodo, E. Bacry and J.F. Muzy, J. Math. Phys. 39, 4163 (1998).
[34] A. Arneodo, E. Bacry, S. Manneville and J.F. Muzy, Phys. Rev. Lett 80, 708 (1998).
[35] M.B. Weissman, Rev. Mod. Physics 60, 537 (1992) and references therein.
[36] B.B. Mandelbrot and H.M. Taylor, Op. Research 15, 1057 (1967).
[37] Z. Ding and C.W.J. Granger, J. of Econometrics 73, 185 (1996).
[38] J.P. Bouchaud, M. Potters and M. Meyer, Eur. Phys. J. B 13, 595 (2000).
[39] A. Arneodo, S. Manneville and J.F. Muzy, Eur. Phys. J. B 1, 129 (1998).
[40] LastWave software freely available at
     http://wave.cmap.polytechnique.fr/soft/LastWave.




                                              21