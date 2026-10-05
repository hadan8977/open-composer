source: https://arxiv.org/pdf/1610.00332
fetched_utc: 2026-10-04T18:36:17Z
bytes_raw: 1101438

Decoupling the short- and long-term behavior of stochastic
                                                                                             volatility

                                                             Mikkel Bennedsen∗             Asger Lunde†            Mikko S. Pakkanen‡
arXiv:1610.00332v3 [q-fin.ST] 5 Jan 2021




                                                                                          January 6, 2021



                                                                                               Abstract

                                                      We introduce a new class of continuous-time models of the stochastic volatility of asset prices.
                                                   The models can simultaneously incorporate roughness and slowly decaying autocorrelations,
                                                   including proper long memory, which are two stylized facts often found in volatility data. Our
                                                   prime model is based on the so-called Brownian semistationary process and we derive a number
                                                   of theoretical properties of this process, relevant to volatility modeling. Applying the models to
                                                   realized volatility measures covering a vast panel of assets, we find evidence consistent with the
                                                   hypothesis that time series of realized measures of volatility are both rough and very persistent.
                                                   Lastly, we illustrate the utility of the models in an extensive forecasting study; we find that the
                                                   models proposed in this paper outperform a wide array of benchmarks considerably, indicating
                                                   that it pays off to exploit both roughness and persistence in volatility forecasting.

                                           Keywords: Stochastic volatility; high-frequency data; rough volatility; persistence; long memory;
                                           forecasting; Brownian semistationary process.

                                           JEL Classification: C22, C51, C53, C58, G17

                                           MSC 2010 Classification: 60G10, 60G15, 60G17, 60G22, 62M09, 62M10, 91G70
                                             ∗
                                                 Department of Economics and Business Economics and CREATES, Aarhus University, Fuglesangs Allé 4, 8210
                                           Aarhus V, Denmark. E-mail: mbennedsen@econ.au.dk.
                                             †
                                               Department of Economics and Business Economics and CREATES, Aarhus University, Fuglesangs Allé 4, 8210
                                           Aarhus V, Denmark. E-mail: alunde@econ.au.dk.
                                             ‡
                                               Department of Mathematics, Imperial College London, South Kensington Campus, London SW7 2AZ, UK and
                                           CREATES, Aarhus University, Denmark. E-mail: m.pakkanen@imperial.ac.uk.




                                                                                                   1
1    Introduction
A large body of literature in financial econometrics has found that the volatility of asset prices, or
realized measures thereof, is persistent, in the sense that its autocorrelation function decays very
slowly (e.g. Ding et al., 1993; Baillie, 1996; Cont, 2001; Andersen et al., 2001, 2003; Baillie et al.,
2019). For this reason, it has become popular to employ stochastic volatility models that enjoy the
long memory property, meaning that their autocorrelation function is not integrable (e.g. Poon and
Granger, 2003; Fleming and Kirby, 2011). The empirical evidence of persistence inspired Comte
and Renault (1996) to introduce the fractional stochastic volatility (FSV) model, which is based
on a fractional Ornstein–Uhlenbeck process, driven by a fractional Brownian motion (fBm) with
Hurst parameter H > 1/2, resulting in a continuous-time model of stochastic volatility with the
long memory property.
    Recently, there has been considerable interest in rough models of volatility. This is due to
both theoretical developments in implied volatility modeling (Alòs et al., 2007; Fukasawa, 2017)
as well as empirical evidence based on realized volatility (Gatheral et al., 2018). An important
contribution to this literature is the model suggested by Gatheral et al. (2018), which is inspired
by FSV model of Comte and Renault (1996). While the FSV model of Comte and Renault (1996)
uses an fBm with Hurst index H > 1/2, giving rise to long memory, Gatheral et al. (2018), by
contrast, switch to an fBm with H < 1/2 to allow for roughness. They therefore term their model
the rough fractional stochastic volatility (RFSV) model.
    When designing a realistic model of volatility, it is important to be aware of the shortcoming,
stressed by Gneiting and Schlather (2004), of self-similar processes, such as the fBm, whereby their
roughness is inseparable from their long term behavior. A work-around to this limitation is to use
fBm as a driver of a stochastic differential equation (SDE), as in the fractional Ornstein-Uhlenbeck
process used in the FSV and RFSV models. Setting aside the intricacies of working with SDEs
driven by fBm, this approach does not make it easy to specify the long-term behavior of the process
independent of roughness, however. A case in point, the Hurst index H still controls the rate of
decay of the autocorrelation function of the fractional Ornstein-Uhlenbeck process in the rough
regime H ∈ 0, 12 .
                

    The first contribution this paper is to introduce a class of continuous-time models of volatility
incorporating both roughness (irregular behavior at short time scales) and persistence (strong
dependence at longer time scales). In particular, we advocate the use of Brownian semistationary
(BSS) processes (Barndorff-Nielsen and Schmiegel, 2007, 2009) as models of logarithmic volatility.
As we will show, these processes are flexible in the sense that they allow for decoupling of the
fine properties (roughness) from the long-term behavior (memory/persistence). Indeed, we show
that BSS processes, under suitable specifications, can accommodate both bona fide long memory
(i.e., non-integrable autocorrelations) and short memory (exponentially decaying autocorrelations),
while the degree of roughness is specified independently. Under rather general conditions, BSS



                                                  2
processes are stationary, and they allow for easy inclusion of non-Gaussianity and the leverage
effect. In spite of their generality, the suggested models are simple, in terms of their mathematical
structure, and parsimonious, relying on only two parameters controlling short- and long-term
behavior, respectively. Moreover, as we demonstrate below, the models are easy to estimate,
simulate, and forecast.
       The second contribution of the paper is to develop an estimation procedure for the parameters
of the proposed models. Since the stochastic volatility process of an asset price is unobservable, any
estimation procedure needs to be based on indirect measures of volatility, which might constitute
(very) noisy measurement of the true underlying process. This engenders a measurement-error
problem, which can bias estimates of the model parameters, especially estimates of the roughness
index (Bennedsen, 2020). We propose noise-robust estimators of all parameters in the proposed
models. Our robust estimator of the roughness index is novel and relies on a non-linear least squares
(NLLS) regression. To our knowledge, this is first time such a robust estimator has been considered
in a study of rough volatility.1 In a simulation study, we inspect the finite sample properties of the
robust estimator of the roughness index and compare with those of a basic (non-robust) estimator.
We find that the basic estimator, which does not take measurement noise into account, can become
severely biased when the data are noisy, while our novel NLLS-based estimator can significantly
alleviate this bias.
       Whereas the first two contributions of the paper are methodological, the third is empirical. We
apply our modelling framework to the study of data on the E-mini S&P 500 futures contract at
a wide range of intraday time scales, ranging from ten minutes to one day. To our knowledge,
this is the first time the roughness properties of intraday volatility have been studied, a surprising
fact given that roughness is inherently a fine scale property and is thus most accurately studied
at small scales. We also study the roughness and persistence of daily realized volatility measures
of close to 2 000 individual equities. Our empirical findings indicate that both intraday and daily
volatility measures display high degrees of roughness and high degrees of persistence, including
possible long memory, thus indicating that our proposed theoretical models could potentially be
useful as models of stochastic volatility.
       Lastly, to examine the practical usefulness of the suggested volatility models, we conduct an
extensive forecasting study. We find that our proposed models outperform a wide array of bench-
mark models, especially at intraday time scales. This indicates that it is important to carefully
model both small- and large-scale behavior of stochastic volatility in forecasting and, therefore,
that models that decouple the behavior at these scales can be useful in practice.
       The rest of the paper is structured as follows. Section 2 defines the concepts of roughness and
persistence, in the context of this paper, through the autocorrelation of a stochastic process. The
   1
       Concurrently with the writing of the present version of this paper, Fukasawa et al. (2019) have developed a
quasi-likelihood approach to estimation of rough volatility models, which also seeks to take account of the noise
induced by using a realized volatility measure in place of the latent volatility process.



                                                           3
section then introduces a class of stochastic volatility models, based on BSS processes, that are able
to parsimoniously incorporate roughness and high persistence, including long memory, simultane-
ously. Section 3 describes the estimation procedure and presents the novel noise-robust estimator
of the roughness parameter. Section 4 contains a number of simulation studies, investigating the
finite sample properties of the proposed estimator. Section 5 is empirical and estimates the various
models using realized volatility data. Section 6 presents a forecasting study, where we compare our
new models to existing volatility forecasting models. Lastly, Section 7 concludes. Some further
details and proofs of the technical results are given in an Appendix. A Web Appendix, containing
further simulation experiments is available online.


2        Models of stochastic volatility that decouple short- and long-
         term behavior
Let X = (Xt )t∈R be a stationary continuous stochastic process, defined on a probability space
(Ω, F, P), satisfying the usual conditions. Define ρ as the autocorrelation function (ACF) of X, i.e.

          ρ(h) := Corr(Xt+h , Xt ),       h ∈ R.

        We say that X is rough if its ACF adheres to the asymptotic relationship

          1 − ρ(h) ∼ c|h|2α+1 ,     |h| → 0,                                                                  (2.1)

for a constant c > 0 and some α ∈ − 12 , 21 .2 We call α the roughness index of X. For stationary
                                           

Gaussian processes, the relationship (2.1) implies that the process X has a modification with locally
φ-Hölder continuous trajectories for any φ ∈ (0, α + 1/2) (e.g. Bennedsen, 2020, Proposition 2.1).
For completeness, we recall here that a function x : R → R is locally φ-Hölder continuous for
φ ∈ (0, 1] if for any compact interval I ⊂ R there is a constant cI > 0 such that

          |x(s) − x(t)| ≤ cI |s − t|φ ,    s, t ∈ I.

Thus, the index α can be seen as a measure of roughness, with small values indicating more rough-
ness. It is worth recalling here that a standard Brownian motion has locally φ-Hölder continuous
trajectories for any φ ∈ (0, 1/2). Thus, negative values of α suggest trajectories rougher than those
of a standard Brownian motion.
        Rough models of volatility are consistent with some empirically observed features of implied
volatility surfaces (Gatheral, 2006). In particular, as shown in Alòs et al. (2007) and Fukasawa
(2017), such models can accurately capture the short-time behavior of the at-the-money volatility
    2
        Here and below “∼” indicates that the ratio between the left- and right-hand side tends to one — when the
constant in this relationship is immaterial, we will denote it by the generic c, which may vary from from formula to
another.


                                                         4
skew, which conventional local/stochastic volatility models based on Itô diffusions fail to capture.
To model the roughness of volatility, earlier studies have mainly relied on the “canonical” rough
process, the fractional Brownian motion (fBm) with Hurst index H ∈ (0, 1/2). For the fBm, the
simple relationship H = α + 1/2 holds, which means that H < 1/2 implies roughness.
   That volatility is very persistent has long been a well-established fact (e.g., Bollerslev and
Wright, 2000; Andersen et al., 2003). A large body of literature has therefore focused on modeling
(log) volatility using persistent models, i.e., volatility models whose autocorrelations decay at a
slow polynomial rate:

      ρ(h) ∼ c|h|−β ,      |h| → ∞,                                                               (2.2)

for a constant c > 0 and some β ∈ (0, ∞). When β ∈ (0, 1), the correlation function ρ is not
                    R∞
integrable, that is, 0 |ρ(h)|dh = ∞, and we say that X has the long memory property. Models
of log volatility that are able to reproduce the long memory property have been traditionally built
using an fBm with Hurst index H = 1 − β/2 ∈ (1/2, 1) as driving noise; see, e.g., Comte and
Renault (1996), Comte (1996), Comte and Renault (1998), and Comte et al. (2012) for literature
on continuous-time volatility models with long memory.
   The fBm is stationary only in terms of increments. While for small H < 1/2, the process
has highly anti-persistent increments, rendering its trajectories seemingly stationary at moderately
long time scales, the formal lack of stationarity of levels is a nuisance when we would like to talk
about long-term properties of volatility like (2.2). The remedy, proposed by Comte and Renault
(1996, 1998) is to construct a volatility model from a fractional Ornstein-Uhlenbeck process, i.e.,
an Ornstein-Uhlenbeck process driven by an fBm (Cheridito et al., 2003) with Hurst index H. The
choice H > 1/2 advocated by Comte and Renault (1996, 1998) gives rise to a model with long
memory, the fractional stochastic volatility (FSV) model, while the choice H < 1/2, championed
recently by Gatheral et al. (2018), results in a model with rough trajectories, the rough fractional
stochastic volatility (RFSV) model.
   The theory of fractional Ornstein-Uhlenbeck processes, Theorem 2.3 of Cheridito et al. (2003) to
be specific, tells us that the processes have an autocorrelation function that decays at a polynomial
rate with exponent β = 2 − 2H. Thus, for H < 1/2 the process loses the long memory property, as
formalized above, while it is still undoubtedly persistent. However, letting the parameter H govern
both the roughness and long-term behaviour of the process via α = H + 1/2 and β = 2 − 2H,
respectively, appears to have neither theoretical nor empirical motivation in the context of volatility
modeling. This prompts us look for processes X for which we can specify the roughness index α
independently of the memory parameter β, or vice versa, or even replace polynomial decay of
autocorrelations with exponential decay without affecting roughness. Given a process X with such
qualities, we then define our general model for the spot volatility process σt as

      σt = ξ exp (Xt ) ,    t ≥ 0,                                                                (2.3)

where ξ > 0 is a free parameter.

                                                  5
2.1     Models for log volatility

We entertain two main candidates for X: the Cauchy process and the so-called Brownian semis-
tationary process. Common to the two processes is that they, in the setting we consider here,
both have two parameters, controlling the short- and long-term behavior, respectively. Thus, the
number of parameters is, in either case, no higher than in the RFSV model (Gatheral et al., 2018,
Sect. 3.1). We will see that the Brownian semistationary process, in particular, is ideally suited to
volatility modeling


2.1.1     The Cauchy process

A flexible Gaussian process that decouples the short- and long-term behavior can be obtained by
using the Cauchy class of autocorrelation functions (Gneiting and Schlather, 2004). The result-
ing Cauchy process is a centered, stationary Gaussian process G = (Gt )t∈R with autocorrelation
function
                             −     β
        ρ(h) = 1 + |h|2α+1        2α+1
                                         ,   h ∈ R,

where α ∈ − 21 , 12 and β > 0. In particular, the process G satisfies (2.1) and (2.2).
                   

   However, the main limitation of this process, from a modeling point of view, is its inherent
Gaussianity. Yet it is possible to go beyond Gaussianity by volatility modulation, that is, by
specifying a process
            Z t
      Xt =      vs dGs ,   t ≥ 0,                                                                (2.4)
              0

using the Cauchy process G and some additional process v = (vt )t∈R that models the volatility
of volatility. Under suitable assumptions, X will inherit the roughness properties of G, see, e.g.,
Barndorff-Nielsen et al. (2009, Example 3). It is worth stressing that since G is typically a non-
semimartingale — and with parameter values relevant to rough volatility modeling it indeed is —
the stochastic integral in (2.4) cannot be defined as an Itô integral, but pathwise Young integration
(Dudley and Norvais̆a, 2011) needs to be used, which requires some additional assumptions on the
roughness of v. In the case where the Cauchy process G is rough, these assumptions become rather
restrictive, unfortunately — for example, v cannot be a semimartingale (with non-zero quadratic
variation).
   In sum, the Cauchy class provides a convenient model that decouples roughness and memory
properties. Since the Cauchy class is characterized by a closed-form ACF, it is very easy to work
with. Moreover, as we will see in the forecasting experiment below, volatility forecasts derived
using a Cauchy class model perform rather well. However, this class of models is not easy to
extend beyond Gaussianity, which limits its applicability as a model of log volatility. Next, we
propose a different modeling framework, which easily accommodates non-Gaussianity.


                                                      6
2.1.2       The Brownian semistationary process

A stochastic process that is able to capture all of our desiderata, consisting of roughness, strong
persistence, stationarity, and non-Gaussianity is the Brownian semistationary process (BSS), which
was introduced in Barndorff-Nielsen and Schmiegel (2007, 2009). This process is defined via the
moving-average representation
          Z t
     Xt =      g(t − s)vs dWs ,          t ≥ 0,                                                                  (2.5)
                 −∞

where W = (Wt )t∈R is a standard Brownian motion defined on R, g : (0, ∞) → R is a square-
integrable kernel function, and v = (vt )t∈R is an adapted, covariance-stationary volatility (of volatil-
ity) process. Note that when v is deterministic, X is Gaussian, while a stochastic v makes X
non-Gaussian. In particular, when v is independent of W , we have
                      Z ∞               
                                 2 2
     Xt |(vs )s≤t ∼ N 0,     g(x) vt−x dx ,
                                 0

showing that the marginal distribution of Xt is a normal mean-variance mixture with conditional
variance governed by v and g. It is shown in Barndorff-Nielsen et al. (2013) that when g is given
by the so-called gamma kernel (Example 2.2 below), we can choose the normal-inverse Gaussian
(NIG) distribution as the marginal distribution of X.3
       Under the assumptions given above, the process X is already well-defined and covariance-
stationary. For stationarity, integration from −∞ in (2.5) is crucial. We will now introduce
additional assumptions concerning the properties of the kernel function g, which enable us to
derive some theoretical results on X.

 (A1) For some α ∈ (−1/2, 1/2) \ {0},

                 g(x) = xα L0 (x),     x ∈ (0, 1],                                                               (2.6)

          where the function L0 is continuously differentiable, bounded away from zero, and slowly
          varying function at zero in the sense that limx↓0 LL00(tx)                  4
                                                                (x) = 1 for all t > 0. Furthermore, the
          derivative L00 of L0 satisfies

                 |L00 (x)| ≤ C(1 + x−1 ),    x ∈ (0, 1],

          for some constant C > 0.

 (A2) The function g is continuously differentiable with derivative g 0 that is ultimately monotonic
                   R∞
      and satisfies 1 g 0 (x)2 dx < ∞.
   3
       In an earlier version of this paper (https://arxiv.org/abs/1610.00332v2), we showed that the NIG distribution
appears to fit the empirical distribution of log volatility very well, especially at intraday time scales. This is an
encouraging property of the BSS framework, and using this as a guide to specify a model for volatility of volatility
is a promising approach, but beyond the scope of the present study.
    4
      We refer to Bingham et al. (1989) for an extensive treatment of slowly varying (and regularly varying) functions.


                                                           7
 (A3) For some λ ≥ 0 and γ ∈ R, such that γ > 1/2 when λ = 0,

               g(x) = e−λx x−γ L1 (x),   x ∈ (1, ∞),                                                (2.7)

        where L1 is slowly varying at infinity and bounded away from zero and ∞ on any finite
        interval.

     Assumptions (A1) and (A3) refine the earlier standing assumption that g is square-integrable.
Indeed, in the case λ = 0, a simple application of the so-called Potter bounds (Bingham et al., 1989,
Theorem 1.5.6(ii)) shows that α > −1/2 and γ > 1/2 are sufficient conditions for g to be square
integrable under the specifications (2.6) and (2.7). Similarly, in the case λ > 0, the conditions
α > −1/2 and γ ∈ R, under (2.6) and (2.7), suffice for square integrability. The assumptions (A1),
(A2), and (A3) are similar to those used in Bennedsen et al. (2017), the only difference being that
(A3) is slightly more specific compared to the corresponding assumption in that paper.
     The following proposition shows that under assumptions (A1) and (A2), the BSS process X,
defined by (2.5), has α as its roughness index in the sense of Equation (2.1). The result is a
straightforward adaptation of Proposition 2.1 in Bennedsen et al. (2017) and we refer to that
paper for a proof. Below, and in what follows, we denote by ρX the autocorrelation function of X.

Proposition 2.1. If the kernel function g satisfies (A1) and (A2), then
                     1
                           R∞                 2 !
                   2α+1 + 0     (x + 1)α − xα dx
    1 − ρX (h) ∼            R∞
                                     2
                                                     L0 (|h|)2 |h|2α+1 , |h| ↓ 0.
                              0 g(x) dx

     The tail behavior of the kernel function g at infinity, as specified by (A3), controls the long-term
memory properties of X. We consider first the case λ = 0, where the exponential damping factor
in (2.7) disappears. In this case, the parameter γ controls the asymptotic memory properties of
the BSS process X.
                                                                                            R1
Proposition 2.2. Suppose that the kernel function g satisfies (A3), with λ = 0, and          0 g(x)dx <
∞.

     (i) If γ ∈ (1, ∞), then
                          R∞          
                              g(x)dx
               ρX (h) ∼ R ∞ 0
                                  2 dx
                                         L1 (|h|)|h|−γ ,       |h| → ∞.
                           0  g(x)

  (ii) If γ ∈ (1/2, 1), then
                       R ∞
                                x−γ (1 + x)−γ dx
                                                   
               ρX (h) ∼     0   R∞
                                        2
                                                       L1 (|h|)2 |h|1−2γ ,   |h| → ∞.
                                 0 g(x) dx


Remark 2.1. In the critical case γ = 1, the asymptotic behavior of ρX is indeterminate under (A3),
and would require additional assumptions on the slowly varying function L1 .

                                                          8
Remark 2.2. It follows from Proposition 2.2 that if the kernel function g satisfies (A3) with λ = 0,
the resulting BSS process will — up to a slowly varying factor — have an autocorrelation function
which decays polynomially as h → ∞. Indeed, letting the rate of polynomial decay be denoted by
β as in (2.2), we see that γ = β when γ > 1, while β = 2γ − 1 when γ ∈ (1/2, 1). From this it also
follows that if γ ∈ (1/2, 1), then
      Z ∞
           ρX (h)dh = ∞,
          0

i.e., X has the long memory property.
   In contrast to the case λ = 0, the assumption (A3) with λ > 0 allows for models where
autocorrelations decay to zero exponentially fast, leading to short memory, as shown in the following
result.

Proposition 2.3. Suppose that the kernel function g satisfies (A3) with λ > 0 and γ ∈ R, such
    R1
that 0 g(x)dx < ∞. Then
               R∞       −λx dx
                               !
                0R g(x)e
     ρX (h) ∼      ∞     2 dx
                                 e−λ|h| |h|−γ L1 (|h|), |h| → ∞.
                  0  g(x)
                                                                                  R1
Remark 2.3. Assumption (A1) is a sufficient condition for the requirement that     0 g(x)dx < ∞ in
Propositions 2.2 and 2.3.
   An example of a kernel function that satisfies (A1), (A2), and (A3), which will be important
for us later on, is the power law kernel.

Example 2.1 (Power law kernel). Let g be the power law kernel
                                                                 
                                                1 1             1
    g(x) = xα (1 + x)−γ−α ,  x > 0,     α∈ − ,        , γ∈        ,∞ .                          (2.8)
                                                2 2             2

Bennedsen et al. (2017, Example 2.2) show that this kernel function indeed satisfies (A1), (A2),
and (A3). In particular, with this kernel function, the BSS process X has roughness index α and
memory properties controlled by γ, as expounded in Proposition 2.2. In the following, we will refer
to the BSS process with the power law kernel as the Power-BSS process.

   Later we will need the correlation structure of the Power-BSS process. By covariance-station-
arity of v, the autocovariance function of the general BSS process (2.5) is
                                         Z ∞
                                     2
      cX (h) := Cov(Xt , Xt+h ) = E[v0 ]     g(x)g(x + |h|)dx, h ∈ R.                           (2.9)
                                            0

From this we deduce that when g is given as in (2.8) we have
                                   Z ∞
     cX (0) := V ar(Xt ) = E[v02 ]     x2α (1 + x)−2γ−2α dx
                                     0

                         = E[v02 ]B(2α + 1, 2γ − 1),

                                                  9
                    R 1 x−1                R∞
where B(x, y) =      0 t    (1 − t)y−1 dt = 0 tx−1 (1 + t)−x−y dt is the beta function (e.g., Gradshteyn
and Ryzhik, 2007, formula 8.380.3). To calculate the correlation function ρX (h) = cX (h)/cX (0)
we resort to numerical integration of (2.9). Note that ρX does not depend on E[v02 ].
   Another example of a kernel function that satisfies equations (A1), (A2), and (A3), which will
also be important in the sequel, is the gamma kernel.

Example 2.2 (Gamma kernel). Let g be the gamma kernel
                                          
                                       1 1
    g(x) = xα e−λx , x > 0,    α∈ − ,        , λ ∈ (0, ∞) ,
                                       2 2
which satisfies (A1), (A2), and (A3), as shown in Bennedsen et al. (2017, Example 2.1). With this
kernel function, the process X has roughness index α and memory properties controlled by λ, as
per Proposition 2.3. In the following, we will call the BSS process with the gamma kernel the
Gamma-BSS process.

   We will also need the correlation structure of the Gamma-BSS process. We easily find
                                 Z ∞
                             2
    cX (0) := V ar(Xt ) = E[v0 ]     x2α e−2λ dx
                                     0

                           = E[v02 ](2λ)−2α−1 Γ(2α + 1),
               R∞
where Γ(a) =    0    xa−1 e−x dx is the gamma function. For general h ∈ R, we have the autocovariance
function, using Gradshteyn and Ryzhik (2007, formula 3.383.8),
                                                 α+1/2
                                     2 Γ(α + 1)  |h|
      cX (h) := Cov(Xt+h , Xt ) = E[v0 ] √               Kα+1/2 (λ|h|),
                                           π     2λ
where Kν (x) is the modified Bessel function of the third kind with index ν, evaluated at x (see
e.g., Gradshteyn and Ryzhik, 2007, section 8.4), and the autocorrelation function can be computed
using the identity ρX (h) = cX (h)/cX (0). We note that cX is the Matérn covariance function
(Matérn, 1960; Handcock and Stein, 1993), which is widely used in many areas of statistics, e.g.,
spatial statistics, geostatistics, and machine learning.
Remark 2.4. These two examples of kernel functions exemplify the theoretical distinction between
long and short memory. In particular, by Proposition 2.3, the Gamma-BSS process adheres to

      ρX (h) ∼ c · e−λh hα ,   h → ∞,

i.e., it has short memory, while the Power-BSS process will have polynomially decaying ACF and,
in particular, the long memory property when γ < 1, cf. Remark 2.2. Although, theoretically, the
Gamma-BSS process has short memory, by selecting very small values of λ, it is possible to specify
processes with a very high degree of persistence, mimicking long memory on finite time intervals.
Empirically, these two BSS models allow us to assess if there is any gain from using a model with
bona fide long memory, as opposed to a highly persistent model with (formally) short memory, in
particular in terms of forecasting accuracy.

                                                    10
Remark 2.5. Thanks to the moving average representation derived by Barndorff-Nielsen and Basse-
O’Connor (2011), the fractional Ornstein-Uhlenbeck process is a special case of the BSS process
(2.5), whereby the FSV and RFSV models are special cases of the general model formulated in this
section. That said, we do not analyze these models for this viewpoint in the current paper due to
their limitations discussed earlier.


2.2   Implications for volatility

The following results show that when log volatility is a BSS process, the roughness and memory
properties will carry over to the volatility process itself. A result related to Theorem 2.1(i) below
was given in Comte and Renault (1998) in the case where X is an fBm. Our results here are stated
for a Gaussian BSS process, i.e., when vt = v > 0 is constant for all t, but we conjecture that the
results hold also for more general BSS processes, under suitable assumptions.
   Let σ = (σt )t≥0 be as in (2.3) and

      ρ(h) = Corr(σt+h , σt ),   h ∈ R.

The first part of the following theorem shows that σ inherits the roughness properties of the BSS
process X. The second part shows that the same is true of the long-term memory properties.

Theorem 2.1. Let σ be given by (2.3) where X is a BSS process satisfying (A1), (A2), and (A3),
with vt = v > 0 for all t. Then,

  (i) as |h| → 0,

            1 − ρ(h) ∼ c|h|2α+1 L0 (|h|).

 (ii) as |h| → ∞,

            ρ(h) ∼ c · ρX (h).


2.3   Simulation of the stochastic volatility model

Fast and efficient simulation of a stochastic volatility model is advantageous for a number of
reasons. For instance, one might wish to conduct simulation experiments to assess the properties
of the model, or one might wish to price derivatives by Monte Carlo simulation. We discuss here
briefly how our model can be simulated rather easily and efficiently. Numerically efficient simulation
methods for rough volatility models, such as the ones considered in this paper, should not be taken
for granted, however. Rough volatility models are typically non-Markovian, depending on the
entire history of the process, which makes conventional recursive simulation methods inapplicable.
What is more, the possibility of non-Gaussianity of the BSS process poses further problems, as this

                                                 11
rules out simulation methods based on Gaussianity, such as Cholesky factorization and circulant
embedding methods (e.g., Asmussen and Glynn, 2007, Chapter XI).
        The model to be simulated is
                     Z t
                                   1 t 2
                                     Z     
         St = S0 exp      σs dBs −     σ ds ,
                       0           2 0 s
          σt = ξ exp (Xt ),

where S0 > 0, ξ > 0, B is a Brownian motion, and X is one of our candidate models for log
volatility, presented in Section 2. We can simulate S on a grid using Riemann-sum approximations
of the integrals. To this end, we need to first simulate B and σ on the same grid, which boils down
to simulating B and X. As we typically want to make these processes correlated, to capture the
leverage effect, it is necessary to simulate B and X jointly.
        When X is Gaussian, for instance a Cauchy process or a BSS process with constant volatility,
it can be simulated exactly using, e.g., a Cholesky factorization of the covariance matrix of the
observations (Asmussen and Glynn, 2007, pp. 311–314). One can additionally compute the co-
variance structure of the Gaussian bivariate process (B, X) and simulate B and X jointly, and in
this way account for correlation between the two processes. This was the approach taken in Bayer
et al. (2016). However, as the authors also note, the Cholesky factorization is computationally
expensive and can become even infeasible if the number of observations to be simulated is large.
Instead, we recommend using the circulant embedding method (Asmussen and Glynn, 2007, pp.
314–316) in the Gaussian case or the hybrid scheme of Bennedsen et al. (2017) in the general case.
The hybrid scheme is tailor-made for BSS processes and its advantages are that (i) simulation is
fast and in most cases accurate5 (although approximate), (ii) it allows for non-Gaussianity of X
through volatility (of volatility) modulation, and (iii) inclusion of leverage, i.e., correlation between
X and B, is straightforward.
        We refer to Bennedsen et al. (2017) for an exposition of the hybrid scheme for the BSS process
X, defined by (2.5), under assumptions (A1), (A2), and (A3). The authors explain in the paper
(Bennedsen et al., 2017, Section 3.1) how to incorporate correlation between v and W , while the
same procedure can be used to introduce correlation between W and B or, indeed, between W , B,
and v.


3        Estimation of the models
We propose a two-step estimation procedure for the models of Section 2. First, we estimate
the roughness parameter α semiparametrically using the scaling relationship (2.1) and then the
remaining parameters are estimated using a parametric method-of-moments approach.
    5
        The hybrid scheme requires truncating the integral representation (2.5) “near” infinity. If the kernel function
has extremely slow decay, this truncation may lead to some loss of accuracy, with regards to the memory properties
of the process.


                                                            12
   We consider two different estimators of α, details of which are given in Section 3.1. The first
estimator is well-known in the literature (e.g., Constantine and Hall, 1994; Gneiting et al., 2012)
and relies on a simple OLS regression. The second estimator is novel; it relies on a non-linear
least squares (NLLS) regression and is constructed so that it is robust to measurement noise in the
observations. This latter feature is important in the context of this paper, where, when we apply
the methods to real data, we do not have access to the spot variance process but only to a noisy
estimate thereof. Section 3.2 briefly reviews the second method-of-moments step of our proposed
estimation approach, which can also be conducted in a noise-robust way.


3.1   Estimating the roughness parameter of log volatility

The estimation of the roughness parameter α from observations of the log-variance process Xt =
log σt2 is well-understood. A particularly simple, and much-used, estimator can be constructed as
follows. Equation (2.1) implies that the second order variogram γ2 (·) satisfies

      γ2 (h) := E[(log σt+h − log σt )2 ] ∼ c|h|2α+1 ,        |h| → 0,

for a constant c > 0. This motivates running the ordinary least squares (OLS) regression

      log γ̂2 (k) = a0 + a1 log k + k ,    k = 1, 2, . . . , m,                                   (3.1)

where m ∈ N is a bandwidth parameter, k is an error term, and
                       n−k
                 1 X
      γ̂2 (k) =      | log σ(i+k)∆ − log σi∆ |2
                n−k
                       i=1

is the empirical variogram corresponding to γ2 (k∆). The OLS estimator of α is thus α̂ = α̂OLS =
(â1 − 1)/2, where â1 is the OLS estimator of a1 from the regression (3.1). We will henceforth refer
to this estimator of α as the OLS estimator . Following Bennedsen (2020), we choose a small value
for the bandwidth and set m = 6.
   Unfortunately, in reality we do not have access to the latent volatility process log σt . Instead,
the available data are estimates of log volatility, log σ̂t , see Section 5 below for further details. It
is reasonable to ask whether it is possible to accurately estimate the roughness index of the latent
log volatility process log σt using log σ̂k . As we will see, this concern is legitimate as the OLS
estimator of α can be severely biased in the presence of measurement noise, which may arise from
using log σ̂t in place of log σt . To alleviate this possible bias, we formulate an estimator that is
robust to additive noise in the observations. To fix ideas, suppose that the observations are related
to the latent process through

      log σ̂k = log σk∆ + uk ,                                                                     (3.2)

where uk is a noise term. If the noise terms are iid with zero mean and uk is independent of log σk∆ ,
we have

      γ2∗ (h) := E[(log σ̂t+h − log σ̂t )2 ] = 2σu2 + γ2 (h),                                      (3.3)

                                                         13
where γ2 (·) is the second-order variogram of the latent process log σt and σu2 is the variance of uk .
When σu2 > 0, log γ ∗ (h) is not linear in log h, and the OLS regression (3.1) can not be expected
to yield a consistent estimate of α (Bennedsen, 2020, Proposition 3.3). Instead, (3.3) motivates a
non-linear least least squares (NLLS) regression:

       γ̂2∗ (k) = b0 + b1 (k∆)2α+1 + k ,            k = 1, 2, . . . , m,

where m ∈ N is a bandwidth parameter, k is an error term, and
                           n−k
                     1 X
       γ̂2∗ (k) =        | log σ̂(i+k)∆ − log σ̂i∆ |2
                    n−k
                           i=1

is the empirical variogram corresponding to γ2∗ (k∆). We refer to this estimator as the NLLS
estimator in the sequel. The following result shows that the NLLS estimator is asymptotically
consistent. The proof is given in Appendix B.

Theorem 3.1. Let X be a square-integrable continuous process with stationary increments and
variogram

       γ2 (h) = E[|Xt+h − Xt |2 ] = c0 h2α0 +1 ,             h > 0,

with constant c0 > 0 and roughness parameter α0 ∈ (−1/2, 1/2). Fix ∆ > 0 and let

       Zi∆ = Xi∆ + ui ,          i = 1, . . . , n,

be equidistant observations such that u = {ui }ni=1 is a zero-mean iid sequence, independent of X,
with finite V ar(u1 ) = σu2 ≥ 0. Denote by γ2∗ (h) the variogram of Z and let Θ be a compact subset
of R+ × R+ × (−1/2, 1/2) such that (2σu2 , c0 , α0 ) is in the interior of Θ. Finally, define the NLLS
estimator of θ := (a, c, α) as
                                       m
                                       X                                       2
       θ̂ = (â, ĉ, α̂) := arg inf          γ̂2∗ (k, ∆) − a − c(k∆)2α+1            ,
                                 θ∈Θ
                                       k=1

with a fixed bandwidth m ≥ 3, and
                                 n−k
                         1 X
       γ̂2∗ (k, ∆) :=        |Z(j+k)∆ − Zj∆ |2 ,                 k = 1, 2, . . . , m.
                        n−k
                                 j=1

Then

       (â, ĉ, α̂) → (2σu2 , c0 , α0 )   in probability,       as    n → ∞.

Remark 3.1. The assumption that

       γ2 (h) = c0 h2α0 +1 ,       h > 0,


                                                                 14
in Theorem 3.1 is somewhat idealized and does not cover many models of interest. For instance,
in this paper we mostly work with models such that

         γ2 (h) = h2α0 +1 L(h),   h > 0,

where the function L is slowly varying at zero, which we recall means that limx→0 L(tx)
                                                                                  L(x) = 1 for all
t > 0. It is possible that the presence of the function L could bias the NLLS estimates. However,
we conjecture that such bias should typically be small, since, by the properties of slowly varying
functions (e.g., Bingham et al., 1989), it is possible to find positive constants C1 and C2 such that
for all  > 0 and h sufficiently small,

         C1 h2α0 +1+ ≤ γ2 (h) ≤ C2 h2α0 +1− ,                                                           (3.4)

indicating that any potential bias in the estimate of α0 can be made arbitrarily small by setting ∆
and m small enough.6 Developing an asymptotic result for the NLLS estimators under these more
general assumptions is beyond the scope of the present paper. However, as we will see below in
the simulation studies of Section 4, we find that the presence of the function L has only negligible
impact on the NLLS estimates of α0 in settings relevant to the one considered in this paper.
       How to choose the bandwidth m optimally for the NLLS estimator is an open problem, which
is beyond the scope of this paper. Instead, in Section 4.1, we use simulations to guide the choice
of bandwidth in practice.


3.2       Parametric estimation of the remaining parameters by the method of mo-
          ments

Let X be a zero-mean stochastic process with unit variance, satisfying assumptions (A1)–(A3).
Consider the model of log-volatility

         log σt = µ + νXt ,

for constants µ = log ξ ∈ R and ν > 0. Clearly, µ and ν can be estimated by the sample mean
and sample standard deviation of log σt , respectively, while the roughness parameter α of X can
be estimated using either the OLS or the NLLS estimator discussed above, applied to log σt .
       The remaining parameters of the model in the vector θ depend on the particular choice of
parametric specification of X. For instance, if X is the Cauchy process introduced in Section
2.1.1 then θ = β, while if X is the Power-BSS process of Example 2.1 then θ = γ, and if X
is the Gamma-BSS process of Example 2.2 then θ = λ. We propose to estimate θ by fitting
the empirically estimated autocorrelation function of log σt to the autocorrelation implied by the
parametric model for X, given the first-step estimate of α. Let the empirical autocorrelation of
   6
       In fact, in the context of the Gamma-BSS and Power-BSS models the function L is actually bounded near the
origin so (3.4) holds with  = 0 then.


                                                        15
the data be denoted by ρ̂(h) and the parametric autocorrelation function implied by the model for
X be denoted by ρ(h; α, θ). We can now define the estimator of θ as
                       H
                       X
        θ̂ = arg min         (ρ̂(h) − ρ(h; α̂; θ))2 ,
                   θ
                       i=1

for some H ≥ 2, where α̂ is the first-step estimator of α, obtained by either the OLS or NLLS
approach discussed in Section 3.1.
    A noise-robust alternative to the estimator θ̂ can be constructed in a straightforward manner.
Indeed, according to the model for the noisy observations (3.2), we can write
                                                    Cov(log σ(k+h)∆ + uk+h , log σk∆ + uk )
        ρ∗ (h) := Corr(log σ̂k+h , log σ̂k ) =
                                                              V ar(log σk∆ + uk )
                                                    Cov(log σ(k+h)∆ , log σk∆ )
                                                  =
                                                    V ar(log σk∆ ) + V ar(uk )
                                                  = C · ρ(h),
                                           2
where ρ(h) := Corr(σt+∆h , σt ), C = (1 + γnoise )−1 is a constant, and the noise-to-signal ratio γnoise
is given by

         2          V ar(uk )
        γnoise =                 .
                   V ar(log σt )
Therefore, the logarithm of the correlation function of the noisy observations log σ̂i , i = 1, . . . , n,
obeys

        log ρ∗ (h) = c + log ρ(h),

where c = log C is a constant. In conclusion, we can estimate θ in a noise-robust manner by θ̂∗
from the non-linear least squares regression
                                H
                                X
            ∗
        (ĉ, θ̂ ) = arg min           (log ρ̂(h) − c − log ρ(h; α̂; θ))2 ,
                        (c,θ)
                                i=1

where α̂ is the first-step noise-robust NLLS estimator of α, developed in Section 3.1.


4    Simulation studies
The aim of this section is to investigate the finite sample properties of the estimation procedure
proposed in the previous section. The Web Appendix contains more extensive simulation results.
    Section 4.1 presents results from a small simulation study, which facilitates the choice of band-
width parameter m for the NLLS estimator of α. A brief comparison with the OLS estimator
is included. Section 4.2 contains a more in-depth comparison of the performance of the OLS and
NLLS estimators when applied to more realistic data. Section 4.3 briefly investigates the properties
of the method-of-moments estimator of the remaining parameters, presented in Section 3.2.

                                                               16
4.1    The influence of the bandwidth parameter m on the NLLS estimator

To assess the effect of the bandwidth parameter m for the NLLS estimator, we conduct a small
simulation study. Consider the model
                  α+1/2
      Yt = µ + Bt         + κt ,   t ≥ 0,

where µ = log ξ ∈ R, κ ≥ 0, and B α+1/2 is a fractional Brownian motion with Hurst index
H = α + 1/2, with α ∈ (−1/2, 1/2), independent of the iid error terms t ∼ N (0, 1), t ≥ 0. Thus,
Yt satisfies the assumptions underlying Theorem 3.1. We set µ = 0, α ∈ {−0.4, −0.2, 0, 0.2} and
simulate n observations of Yi∆ with ∆ = 0.10 for i = 1, 2, . . . , n. We generate 500 Monte Carlo
replications of Yt and use the NLLS estimator to estimate α for various values of the bandwidth
parameter m, the true roughness index α, and for the noise variance κ. From these 500 simulated
instances, we record the “optimal” value of the bandwidth parameter m∗ , i.e., the value of m that
minimizes the mean squared error of the estimates of α over the 500 simulations. The results for
n ∈ {1000, 2000}, m ∈ {3, 4, . . . , 50}, and κ ∈ {0, 0.1, 0.2, 0.3, 0.4, 0.5} are shown in Figure 1.
   It is clear that, as the noise level κ increases, so does the optimal bandwidth. Likewise, the
                                         α+1/2
rougher the underlying process Bt                is, i.e., the lower α is, the larger the optimal bandwidth
m∗ . Going from n = 1 000 to n = 2 000 does not seem to have a large effect on m∗ . For relevant
values of α, i.e., α ≤ 0, the optimal bandwidth seems to be roughly between m∗ = 10 and m∗ = 20,
although for values of α very close to −0.50, m∗ might be even larger.
   The NLLS estimator can be quite sensitive to the numerical optimization procedure employed.
This, together with the uncertainty over the precise value of m∗ in practical applications, prompts
us to suggest to average the estimates coming from several values of the bandwidth parameter
m. (Alternatively, one could take the median of the estimates instead of the mean.) Given the
admittedly somewhat rudimentary simulation study of this section, we recommend averaging over
the 11 estimates obtained from setting m = 10, 11, . . . , 20. We have found that this strategy works
quite well in practice, but we stress again that a more systematic way of choosing m would be
preferable. This, however, is beyond the scope of the present article and is left for future work.
   To illustrate the performance of this strategy, and compare with the OLS estimator, Figure
2 plots the bias of the proposed NLLS estimator, i.e., the average of the NLLS estimates from
m = 10, . . . , 20, as well as the bias of the OLS estimator, in the same simulation study used to
construct Figure 1. It is clear that that the OLS estimator is very biased for κ > 0, while the
NLLS estimator seems to alleviate the bias to a great extent. The next section further examines
the properties of the two estimators in a more realistic setting.


4.2    Estimating the roughness index of a noisy time series

Consider now the model

      Yt = µ + νXt + κt ,      t ≥ 0,

                                                        17
                         n = 1000                                                           n = 2000
       50                                                         50
                                                                                   = 0.2
       40                                                         40               =0
                                                                                   = -0.2
                                                                                   = -0.4
       30                                                         30
 m*




                                                            m*
       20                                                         20

       10                                                         10

         0                                                          0
             0    0.1   0.2     0.3    0.4     0.5                      0    0.1        0.2       0.3   0.4   0.5



Figure 1: Determining the optimal (with respect to mean squared error) bandwidth m∗ for the NLLS
estimator using simulations. The simulation setup is described in Section 4.1.
                         n = 1000                                                           n = 2000

         0                                                          0


       -0.2                                                       -0.2
Bias




                                                           Bias




       -0.4                                                       -0.4


       -0.6                                                       -0.6
              0   0.1   0.2     0.3     0.4     0.5                      0   0.1        0.2       0.3   0.4   0.5



Figure 2: Biases of the NLLS (solid lines) and OLS (dashed lines) estimators in the simulation
study of Section 4.1. The NLLS estimator is the average of individual NLLS estimators with
bandwidths m = 10, 11, . . . , 20, while the OLS estimator uses m = 6.


where µ = log ξ ∈ R, ν, κ > 0, X is a zero-mean stochastic process with unit variance satisfying
assumptions (A1)–(A3), and t ∼ N (0, 1), t ≥ 0, are iid error terms. The term ut = κt represents
the measurement noise perturbing the observations of the latent process Yt∗ = µ + νXt . The
relevant noise-to-signal ratio is denoted by s = V ar(ut )/V ar(Yt∗ ) = κ/ν.
                                                p

       Using this setup, we want to assess the finite sample properties of the two estimators of α when
X is the Gamma-BSS process of Example 2.2, sampled at daily or higher frequency. Note that,
strictly speaking, this process does not satisfy the assumptions behind Theorem 3.1, cf. Remark
3.1. We set λ = 0.02, µ = 1, ν = 1 and simulate n = 1 000 observations with sampling frequency
∆ > 0, mimicking n observations of log volatility data, observed 1/∆ times per day. We vary the
noise-to-signal ratio s ∈ {0, 0.1, 0.2, 0.3, 0.4, 0.5} by changing the standard deviation of the noise

                                                      18
κ ∈ {0, 0.1, 0.2, 0.3, 0.4, 0.5}. Two values of α are considered, namely α = 0 and α = −0.35, which
are particularly interesting for the purposes of this paper: α = 0 corresponds to the “standard”
semimartingale framework, while α = −0.35 is a value often found when estimating the roughness
index of realized volatility measures, see, e.g., Gatheral et al. (2018) and Section 5 below. Two
values are also considered for the sampling frequency, namely ∆ = 1 and ∆ = 0.1. The first value
corresponds to daily observations, while the second value corresponds to intraday observations
(roughly hourly) of realized log volatility. The value for the mean reversion parameter, λ = 0.02,
corresponds to what we estimate on the S&P 500 data in Section 5.1 below. We performed similar
simulations for different values of α, λ, and ∆, and found very similar results, which are presented
in the Web Appendix.
       We simulate 500 instances of Yt and estimate the roughness index α using both the OLS and
the NLLS estimator. Table 1 reports the mean, median, and standard deviation (SD) of the 500
estimates of α coming from each of the two estimators. As remarked above, we consider α = 0
(Panels A and C) and α = −0.35 (Panels B and D), as well as ∆ = 1 (Panels A and B) and ∆ = 0.1
(Panels C and D). Several things can be learned from the results. Firstly, the NLLS estimator
is more dispersed than the OLS estimator, as evidenced by the larger standard deviation of the
estimates coming from the NLLS estimator. Secondly, the OLS estimator quickly becomes biased
when the noise-to-signal ratio s increases. The NLLS estimator, however, is able to alleviate this
bias to a great extent. This is especially clear in the case of α = 0, where the OLS estimator is very
biased, while the NLLS estimator is much more accurate. When sampling infrequently, i.e., when
∆ = 1, the NLLS estimator is slightly downwards biased, however, due to the mean reversion in
the process, cf. Panel A of Table 1. This is evidence of the fact, that when the sampling frequency
is low, mean reversion can resemble roughness. At the mean reversion levels relevant to this paper,
i.e., for very persistent processes, the bias is small, however.7 We refer the interested reader to the
Web Appendix, where this behavior is studied in more detail.


4.3       Estimating the remaining parameters using the method of moments

Table 2 presents the estimation results using the moment-based estimator of λ given in Section 3.2.
For brevity, we only report the results for ∆ = 1, as the results for ∆ = 0.1 are similar and can
be found in the Web Appendix. The simulation procedure is identical to the one used in Section
4.2 to study the estimators of α, i.e., X is a Gamma-BSS process with λ = 0.02. Panels A and B
of Table 2 contain the results for α = 0 and α = −0.35, respectively. Mean, median and standard
deviation are reported using both the ordinary estimator θ̂ = λ̂ and the robust estimator θ̂∗ = λ̂∗ ,
cf. Section 3.2.
   7
       Abi Jaber and El Euch (2019) show that rough models can be approximated by a mixture of standard models
with varying degrees of mean reversion, including components with arbitrarily fast mean reversion. However, such
models are arguably less parsimonious and flexible than the rough models proposed in this paper.




                                                       19
                                Table 1: Monte Carlo simulation results
  Panel A: α = 0, ∆ = 1
                s=                0         0.1          0.2         0.3          0.4          0.5

 OLS            Mean            −0.01      −0.10        −0.24       −0.33        −0.38        −0.42
                Median          −0.01      −0.10        −0.24       −0.33        −0.38        −0.42
                SD              0.02        0.02        0.02         0.02        0.02          0.01

 NLLS           Mean            −0.04      −0.07        −0.08       −0.07        −0.07        −0.06
                Median          −0.04      −0.07        −0.08       −0.07        −0.07        −0.07
                SD              0.04        0.04        0.06         0.07        0.08          0.09

  Panel B: α = −0.35, ∆ = 1
                s=                0         0.1          0.2         0.3          0.4          0.5

 OLS            Mean            −0.35      −0.35        −0.37       −0.38        −0.40        −0.41
                Median          −0.35      −0.35        −0.37       −0.38        −0.40        −0.41
                SD              0.02        0.02        0.02         0.02        0.02          0.02

 NLLS           Mean            −0.33      −0.33        −0.33       −0.33        −0.33        −0.33
                Median          −0.34      −0.34        −0.35       −0.35        −0.36        −0.36
                SD              0.05        0.05        0.05         0.06        0.07          0.08

  Panel C: α = 0, ∆ = 0.1
                s=                0         0.1          0.2         0.3          0.4          0.5

 OLS            Mean            −0.00      −0.33        −0.44       −0.47        −0.48        −0.49
                Median          −0.00      −0.33        −0.44       −0.47        −0.48        −0.49
                SD              0.02        0.02        0.01         0.01        0.01          0.01

 NLLS           Mean            0.00       −0.01        −0.01        0.01        0.02          0.02
                Median          0.00       −0.01        −0.01       −0.00        0.02          0.05
                SD              0.05        0.07        0.11         0.18        0.24          0.28

  Panel D: α = −0.35, ∆ = 0.1
                s=                0         0.1          0.2         0.3          0.4          0.5

 OLS            Mean            −0.35      −0.36        −0.38       −0.40        −0.42        −0.44
                Median          −0.35      −0.36        −0.38       −0.40        −0.42        −0.43
                SD              0.02        0.02        0.02         0.02        0.01          0.01

 NLLS           Mean            −0.32      −0.32        −0.32       −0.33        −0.32        −0.32
                Median          −0.33      −0.34        −0.34       −0.35        −0.34        −0.34
                SD              0.05        0.06        0.06         0.07        0.09          0.10


Monte Carlo simulation study of the OLS and NLLS estimators of α. DGP: Gamma-BSS with λ = 0.02. Also
µ = 1, ν = 1, n = 1 000, T = n∆. Number of Monte Carlo simulations: 500.




                                                   20
                                    Table 2: Monte Carlo simulation results
    Panel A: α = 0, ∆ = 1
                     s=                   0         0.1         0.2           0.3     0.4           0.5

 Standard            Mean                0.02       0.02        0.02          0.02    0.02         0.02
                     Median              0.02       0.02        0.02          0.02    0.02         0.02
                     SD                  0.01       0.01        0.01          0.01    0.01         0.01

 Robust              Mean                0.02       0.02        0.02          0.02    0.02         0.02
                     Median              0.02       0.02        0.02          0.02    0.02         0.02
                     SD                  0.01       0.01        0.01          0.01    0.01         0.01

    Panel B: α = −0.35, ∆ = 1
                     s=                   0         0.1         0.2           0.3     0.4           0.5

 Standard            Mean                0.03       0.03        0.03          0.03    0.03         0.03
                     Median              0.03       0.03        0.03          0.03    0.02         0.02
                     SD                  0.02       0.02        0.02          0.02    0.02         0.03

 Robust              Mean                0.03       0.03        0.03          0.03    0.02         0.02
                     Median              0.03       0.03        0.02          0.02    0.02         0.02
                     SD                  0.01       0.02        0.02          0.02    0.02         0.02


Monte Carlo simulation study of the estimators of λ, see Section 3.2. DGP: Gamma-BSS with λ = 0.02. Also
µ = 1, ν = 1, n = 1 000, T = n∆. Number of Monte Carlo simulations: 500.


5      Application to realized volatility data
We employ a general model for high-frequency asset returns, where the efficient log price Y =
(Yt )t≥0 of the asset follows an Itô semimartingale

        dYt = µt dt + σt dBt + dJt ,       t ≥ 0,                                                 (5.1)

specified using standard Brownian motion B = (Bt )t≥0 , drift process µ = (µt )t≥0 , jump process
J = (Jt )t≥0 and volatility process σ = (σt )t≥0 , satisfying the usual assumptions of adaptedness
and local boundedness. Since we sample prices at high frequency, we follow the standard practice
of high-frequency financial econometrics by treating the data as noisy observations of the efficient
log price Y , contaminated by market microstructure noise,

        log St = Yt + Ut ,      t ≥ 0,

where U = (Ut )t≥0 is a microstructure noise process.
     Since our focus will be on the volatility process σ, we do not go into much detail regarding
the jump process J or the noise process U . We impose only mild standard assumptions on these
processes, such that the jump- and noise-robust estimator of the volatility process, explained below,
will be consistent. Sufficient, but not necessary, conditions for this are, e.g., that the jump term is
given by a compound Poisson process and the noise terms are iid with zero-mean and finite fourth
moment, and independent of the efficient price Y (Christensen et al., 2014, Proposition 1). Also,

                                                           21
in the context of high-frequency returns, the drift process µ is empirically negligible, and will be
ignored from now on. The following sections will explain the data we use for S, how we estimate
the latent volatility process σ, and the subsequent empirical findings on this process.
   We seek to extract the realized spot volatility process (σt )t∈[0,T ] , for some time horizon T > 0,
from high-frequency observations of the asset price S. As σ is not directly observable, we need
to construct a proxy for it. In particular, in this section, we are interested in assessing intraday
variation of volatility. This should be contrasted with, e.g., Gatheral et al. (2018), who consider
volatility proxies computed at daily frequency.
   To this end, we first specify a step size ∆ > 0 such that T = n∆ for some large n ∈ N. Then
we aim to estimate the integrated variance (IV),
                Z t
      IVt∆ :=          σs2 ds,   t = ∆, 2∆, . . . , n∆.
                 t−∆

Estimators of IV have been extensively studied, prominent examples being realized variance (An-
dersen et al., 2001; Barndorff-Nielsen and Shephard, 2002), realized kernels (Barndorff-Nielsen
et al., 2008), two-scale estimators (Zhang et al., 2005), and pre-averaging methods (Jacod et al.,
2009). Except for the first, these methods are robust to market microstructure effects, which is
crucial when using prices sampled at higher frequencies (e.g., Hansen and Lunde, 2006). Further,
as we will see below, the pre-averaging methods can be adapted in a straightforward manner to
handle jumps in the price process, which is our main reason for choosing this particular approach.
   By letting ∆ be sufficiently small, so that variation in the level of volatility in each time interval
of size ∆ is small, we can use the proxy
                      ∆
      σ̂t2 = ∆−1 IV
                 ct ,       t = ∆, 2∆, . . . , n∆,                                                 (5.2)

          ∆
where IV
      c is an estimate of IV derived from one of the methods mentioned. A priori, we do not
         t
want to fix any specific value of the step size ∆ to sample volatility, as the choice of this parameter
would vary from application to another, and as there is no canonical choice when ∆ is less than a
day. For this reason, we perform the subsequent analyses for various values of ∆ and, as we shall
see, our empirical findings are similar for essentially all intraday, as well as daily, time scales.
   The proxy (5.2) can be seen as a (finite difference) time derivative of the estimate of IV. We
assume that these data can be described by a model of the kind considered in the simulation study
above, i.e.,

      log σ̂k∆ = µ + νXk∆ + κk ,         k = 1, 2, . . . , n,

where k ∼ N (0, 1) is a term that captures the measurement error arising from the use of log σ̂k ,
as given in (5.2), in place of the true log volatility process log σk∆ = µ + νXk∆ . Related estimators
of spot volatility have been suggested in the literature; see, e.g., Kristensen (2010), Bos et al.
(2012), and Zu and Boswijk (2014). In this paper we will restrict attention to (5.2) where we

                                                          22
estimate IV using the so-called pre-averaged bipower variation measure, developed in Jacod et al.
(2009). In what follows, this measure will be denoted by BVt∆,∗ ; its implementation is briefly
reviewed in Appendix A. The statistic BV ∆∗ is robust to both jumps (J) and market microstructure
noise (U ), which is why we choose to use this particular measure of IV. We have also conducted
analogous analyses using the so-called pre-averaged realized variance RV ∆∗ (see Appendix A for
the definition), obtaining results that consistent with those in the present paper.8
       Lastly, we ask what a realistic signal-to-noise ratio s is in the data studied here. The answer
to this question is important, since it will allow us to judge whether we can rely on the promising
simulation results of Section 4 and, with reasonable confidence, rely upon the estimates coming
from our various estimators. To work out a rough estimate of s, note that the related spot volatility
estimator of Kristensen (2010) adheres to (Kristensen, 2010, Theorem 3)

         σ̂t2 = σt2 + ηt ,   ηt ∼ M N (0, 2Kσt4 /n),

where M N denotes a mixed normal distribution, indicating that ηt is normally distributed, condi-
tional on σt , while n is the number of observations used to compute the estimate σ̂t2 . The constant
K is related to the kernel function used in the estimator of Kristensen (2010). For instance, K = 0.6
for the so-called Epanechnikov kernel and K = 0.5 for the uniform kernel. This implies that, in
this setup,
              p
         s=    2K/(n∆).

   Assuming K ≈ 1, then, using these rough calculations, for daily IV (∆ = 1 day) with prices
                                                          p
sampled every 5 minutes (n = 6.5 · 60/5 = 78) we get s = 2/(78 · 1) = 0.16, while for hourly
                                                                   p
IV (∆ = 65 minutes) with prices sampled every minute we have s = 2/(65/6.5) = 0.45. These
calculations ignore the possible presence of measurement noise, which should increase the noise-
to-signal ratio. On the other hand, we use tick-by-tick data, so n will be large in our applications.
This suggests that s ∈ [0, 0.5] is a plausible range of values for the noise-to-signal ratio in our
data, at least for ∆ ≥ 30 minutes, say. (For smaller ∆, say 10 or 15 minutes, the noise-to-
signal ratio could be even higher than 0.5.) We conclude that the simulation results of Section
4 should give a reasonable idea of how the estimators will behave when applied to our data. In
particular, the OLS estimator is prone to being downwards biased, especially if the true value of
the roughness parameter α is close to 0, while the NLLS estimators should be able to alleviate this
bias significantly.
   8
       We have also carried out the analyses using the realized kernel estimator of Barndorff-Nielsen et al. (2008),
obtaining similar results. The details can be found in the first version of this paper, available at: https://arxiv.
org/1610.00332v1.




                                                          23
5.1          Application to the S&P500 E-mini futures contract

We analyze tick-by-tick transaction data on the front month E-mini S&P 500 futures contract,
traded on the CME Globex electronic trading platform, from January 2, 2011 until December 31,
2014 excluding weekends and holidays. After removing days which were not full trading days we
arrive at a total of 996 days in our sample. As we are interested in assessing volatility at intraday
time scales, we rely on there being a lot of trading activity on the underlying asset. For this reason
we restrict our attention to the period of the day when most trading is taking place; this is when
the cash equity market is open, from 9.30 a.m. until 4 p.m. Eastern Time (ET).
          It is well-known that intraday volatility displays significant seasonality (e.g., Andersen and
Bollerslev, 1997, 1998). In particular, the “U-shape” is ubiquitous, where volatility is high at the
opening and at the close of the market, while being lower around midday. (See, e.g., Andersen
et al., 2016, Figure 1.) When ∆ < 1 day, it is therefore important to control for this seasonality
before performing any further analyses as subsequent estimates could be affected if one does not
take this into account (Rossi and Fantazzini, 2015). We use a multiplicative decomposition

            σt = σts σ̃t ,   t ≥ 0,

where σ s is the seasonal component and σ̃ is the deseasonalized stochastic process we are interested
in. To estimate σ s we use the flexible Fourier form (FFF) approach of Andersen and Bollerslev
(1997, 1998). We then estimate σ̃t2 by

            σ̃       c∆
            c2 = ∆−1 IV    [ s 2    −1  ∆∗ [s 2
                        t /(σt ) = ∆ BVt /(σt ) ,            t = ∆, 2∆, . . . , n∆,
               t


and will from now on be working with these de-seasonalized data when ∆ < 1 day. Further, we
abuse notation slightly and will write σ even though we actually refer to the de-seasonalized process
σ̃.
          An earlier version of this paper contains an in-depth analysis of the dynamic properties of
the de-seasonalized E-mini S&P 500 log volatility data.9 The main findings are that: (i) The log
volatility process appears to be approximately stationary for all values of ∆; (ii) semiparametric
estimates of the long-term decay rate of the autocorrelations of log volatility show evidence of very
slowly decaying autocorrelations; and (iii) the empirical probability distribution of log volatility
appears to deviate noticeably from the Gaussian distribution, especially for log volatility measured
at intraday horizons, i.e. for ∆ < 1 day. Indeed, the Normal Inverse Gaussian distribution (e.g.,
Barndorff-Nielsen, 1997) provides a good fit for these empirical probability distributions.
          Panel A of Table 3 reports the estimates of α, β, and λ for the different models proposed in
Section 2, using the data on log volatility of the E-mini S&P 500 futures contracts, extracted as
explained above. We used H = dn1/3 e lags in the ACF for the method-of-moments estimation
      9
          Available at https://arxiv.org/abs/1610.00332v2. Detailed results are also available from the authors upon
request.



                                                           24
procedure. While this choice may seem somewhat arbitrary, the results are robust to alternative
choices. We find that both the OLS and NLLS estimators of α indicate that the realized measures
of log-volatility are rough with α̂ ∈ [−0.3, −0.40]. The estimates of α are slightly lower for the
smaller values of ∆, possibly due to the idea that the data here can be expected to exhibit higher
levels of noise, in relative terms, as discussed above. The estimates of the memory parameters are
very low in all cases, Indeed, when estimating the Cauchy and Power-BSS models, we find that
β < 1, which suggests that the data generating process might possess the long memory property.
The exponential decay parameter λ of the Gamma-BSS process is also estimated to be a very low
value, on the order of 0.01. Estimates of the memory parameters appear to be insensitive to the
value of ∆ and to whether or not a noise-robust estimation procedure is used. (In Table 3, an
asterisk denotes a noise-robust estimate.) In conclusion, it appears that the realized measures of
the log volatility of the E-mini S&P 500 futures data studied in this section are rough and exhibit
a high degree of persistence.
       Although we have sought to alleviate the detrimental effects of measurement error by using
estimators which are (theoretically) robust to noise, the conclusions of course come with the caveat
that the true stochastic volatility is unobserved. Hence, strictly speaking, the above conclusions
about the nature of volatility can only be drawn insofar the realized measure σt is concerned.
Nevertheless, the simulation results of Section 4.2, see Table 1, seem to indicate that if the true
value of the roughness index were α = 0, the OLS estimator would be severely biased, but the
NLLS estimator would not. Hence, even though the noisy nature of the data makes it impossible
to pinpoint the exact value of α for the underlying latent volatility process, it is, according to the
simulation results, somewhat implausible that the true value of α would be α = 0.10
       Panels B and C of Table 3 report the results from similar analyses, but now using (non-
logarithmic) volatility and variance as the data, respectively.11 The estimates of the parameters
obtained from the volatility (Panel B) and variance (Panel C) time series are very similar to those
of the log-volatility time series (Panel A). Overall, it appears that volatility and variance largely
inherit the roughness and memory properties of log volatility, as suggested by Theorem 2.1.
  10
       This conclusion, of course, has its intrinsic caveats. That is, it is predicated on certain fundamental assumptions,
such as the efficient log price process being given by (5.1), the noise-to-signal ratio s not being excessively large, log
volatility not being subject to jumps or structural breaks, etc.
  11
     For the variance time series (Panel C), we excluded the three largest observations from the data before performing
                                                                                                             ∗
the analysis, since these observations were so extreme that the estimates of the parameters, in particular α̂N LLS

appeared to be unstable. These three large observations, or “outliers”, all occur in 2011, i.e. in the first year of the
sample. We conducted the analysis with both three observations and the entire year 2011 removed, obtaining similar
results. To keep the results as comparable as possible to those for volatility and log volatility, we report them using
the former approach which removes far fewer observations. The results using the latter approach are available upon
request.




                                                             25
                             Table 3: Estimation results: E-mini S&P500 futures data
 Panel A: Log-volatility
∆                    α̂OLS        α̂∗N LLS    β̂Cau          ∗
                                                           β̂Cau       β̂pBSS          ∗
                                                                                     β̂pBSS        λ̂gBSS        λ̂∗gBSS

10 minutes           −0.38         −0.38       0.17        0.18          0.31         0.26          0.03          0.02
15 minutes           −0.35         −0.37       0.18        0.18          0.02         0.26          0.04          0.03
30 minutes           −0.31         −0.35       0.18        0.18          0.02         0.31          0.03          0.03
65 minutes           −0.30         −0.35       0.18        0.18          0.30         0.31          0.02          0.02
130 minutes          −0.32         −0.35       0.00        0.17          0.29         0.30          0.02          0.02
1 day                −0.30         −0.33       0.00        0.18          0.32         0.34          0.02          0.02

 Panel B: Volatility
∆                    α̂OLS        α̂∗N LLS    β̂Cau          ∗
                                                           β̂Cau       β̂pBSS          ∗
                                                                                     β̂pBSS        λ̂gBSS        λ̂∗gBSS

10 minutes           −0.33         −0.35       0.21        0.21          0.02         0.29          0.06          0.03
15 minutes           −0.32         −0.36       0.19        0.19          0.02         0.21          0.04          0.02
30 minutes           −0.29         −0.38       0.00        0.15          0.23         0.23          0.02          0.01
65 minutes           −0.35         −0.36       0.00        0.16          0.26         0.27          0.02          0.02
130 minutes          −0.35         −0.28       0.22        0.23          0.47         0.48          0.04          0.03
1 day                −0.23         −0.31       0.00        0.19          0.33         0.35          0.02          0.02

 Panel C: Variance
∆                    α̂OLS        α̂∗N LLS    β̂Cau          ∗
                                                           β̂Cau       β̂pBSS          ∗
                                                                                     β̂pBSS        λ̂gBSS        λ̂∗gBSS

10 minutes           −0.37         −0.38       0.26        0.27          0.73         0.43          0.11          0.06
15 minutes           −0.35         −0.37       0.23        0.23          0.50         0.27          0.07          0.03
30 minutes           −0.33         −0.39       0.00        0.16          0.26         0.26          0.02          0.02
65 minutes           −0.36         −0.36       0.20        0.21          0.38         0.38          0.03          0.03
130 minutes          −0.34         −0.35       0.00        0.20          0.36         0.38          0.02          0.02
1 day                −0.35         −0.37       0.00        0.16          0.25         0.26          0.01          0.01


Estimates of α using the OLS and NLLS estimators, as well as method-of-moments estimates obtained by matching
the empirical ACF with the theoretical ACF in our three parametric models, the Cauchy, the Power- and Gamma-
BSS models. We used H = dn1/3 e lags to estimate the memory parameters λBSS , βBSS , and βCauchy . The estimate
of βBSS is calculated from the estimate of method-of-moments estimate of γ of the Power-BSS process; that is, when
γ̂ > 1, set β̂BSS = γ̂, otherwise set β̂BSS = 2γ̂ − 1. Asterisks denote noise-robust estimates. The volatility series in
Panels A–C are extracted from E-mini S&P500 futures data over the period 2011–2014 using the methods described
in the main text (regarding Panel C, see also footnote 11).




                                                          26
5.1.1      Does roughness change over time?

One may wonder whether the degree of roughness of volatility changes over time. This very question
was also studied by Gatheral et al. (2018), who divided their volatility data into two parts and
found tentative evidence that volatility was less rough during a period that overlapped with the
financial turmoil of 2008 and 2011.
       Our methodology and data allow us to investigate this question more precisely and system-
atically. To this end, we still use transaction data on E-mini S&P 500, but now over a longer
period from January 3, 2005 until December 31, 2014. Figure 3 provides results of rolling-window
estimation of α using the NLLS estimator when the volatility is proxy is constructed using ∆ = 65
minutes. The window length is 900 observations, corresponding to roughly 150 days. We have also
experimented with different window sizes and different values of ∆, but the results are rather con-
sistent with those presented here. Figure 3 additionally displays the overall median over the entire
period, as well as a smoothed time series of the estimates. The figure shows that α does indeed
appear to vary in time. In particular, we observe two peaks of “smoothness”, in the smoothed
estimates, that both seem to coincide with periods of market distress. The first large and long
period of smoothness occurs during the financial crisis of 2007–2008, while the second, somewhat
shorter and less extreme, period of smoothness takes place during 2011, at the nadir of the Greek
debt crisis.
       While it seems imprudent to draw any definite conclusions from a single time series, the findings
presented here, together with the empirical evidence of Gatheral et al. (2018), seem to indicate that
volatility exhibits less roughness during periods of market turmoil, possibly due to more sustained
trading activity occurring in such times. We investigate this further using a large panel of equities
in Section 5.2.1 below.


5.2       Application to individual equities

Our goal here is to study whether the findings above are only valid for the E-mini S&P 500 futures
contract, or whether they hold true more generally. We therefore study volatility data on a large
number of US equities. The data consist of daily pre-averaged bipower variation measures (i.e.,
BV ∆∗ with ∆ = 1 day), computed using transaction prices obtained from the Trades and Quotes
(TAQ) database.
       The data set at our disposal runs from January 4, 1993 to December 31, 2013, while the data
on some assets may cover this period only partially. In total there are 10 744 assets in the sample,
classified into ten industry sectors according to the Global Industry Classification Standard.12
Since the charactistics of US equities markets have arguably evolved substantially during the past
three decades through the decimalization of prices, electronification of trading and proliferation of
competing trading venues, we only work with the data over the period from January 2, 2003 to
  12
       See: https://msci.com/gics



                                                    27
   -0.15

                                                                                               (estimate)
       -0.2                                                                                   Smooth
                                                                                              Median = -0.36
   -0.25


       -0.3


   -0.35


       -0.4


   -0.45
              2006       2007      2008       2009       2010       2011       2012       2013       2014       2015



Figure 3: Rolling-window NLLS estimates of α. The volatility proxy is computed using ∆ = 65
minutes and the smoothed version is a simple moving average filter using 75 observations on both
sides of the particular estimate.

December 31, 2013, striving for relevance in the present day and beyond. Additionally, to ensure
the reliability of the volatility estimates, we retain only the most liquid assets. Here, a liquid asset
is characterized by the following subjective criteria.

   (a) The asset is traded on at least 400 days.

   (b) The maximum number of days when the asset is not traded (on average) every 5 minutes is
          19.

   (c) The estimate BV ∗ of IV is strictly positive on every day.13

After discarding the assets that do not fulfil these criteria, we are left with 1 944 liquid assets for
our analysis.14
       The estimates of the roughness parameter α of volatility, using the noise-robust NLLS estimator,
for the assets in the sample are summarized in a box plot in Figure 4. A few features of this plot
are worth highlighting. Firstly, the estimates of α are practically all negative, mostly in the range
(−0.45, −0.3), indicating pronounced roughness. Secondly, there does not seem to be significant
systematic differences in the roughness estimates across sectors.
       Turning now to persistence properties, Figure 5 contains box plots of the estimates of β, here
                                        ∗
using the robust parametric estimator β̂Cauchy , based on the Cauchy model. We have obtained
  13
       Although IV is by definition never negative, BV ∗ can become negative due to the bias correction term appearing
in its definition, see Appendix A.
  14
     In an earlier version of this paper, available at: https://arxiv.org/1610.00332v1, we have employed the realized
kernel estimator of Barndorff-Nielsen et al. (2008), which is guaranteed to be non-negative, enabling us to analyze
5 071 assets. The results therein are very similar to those in the present paper.


                                                           28
              Energy
            Materials
          Industrials
  Consumer Discret.
  Consumer Staples
         Health Care
           Financials
   Information Tech.
Telecommunications
              Utilities
        Not Available
                     All
                      -0.5       -0.4       -0.3              -0.2         -0.1         0    0.1   0.2



                                                           ∗
                                  Figure 4: Box plot for α̂N LLS by sector.


              Energy
            Materials
          Industrials
  Consumer Discret.
  Consumer Staples
         Health Care
           Financials
   Information Tech.
Telecommunications
              Utilities
        Not Available
                     All
                           0        0.1            0.2               0.3          0.4       0.5    0.6



                                               ∗
                      Figure 5: Box plot for β̂Cauchy by sector. Bandwidth H = dn1/3 e.

                                      ∗
similar results using the estimator β̂BSS derived from the Power-BSS process but for brevity these
results are omitted. Again, our analysis confirms the findings seen earlier with the E-mini S&P 500
volatility data. Indeed, the estimates show that log volatility is very persistent, with estimates of
β predominantly in the interval (0, 0.4). In particular, there is compelling evidence of very strong
persistence in volatility.
                                                                         ∗
    The above analysis was conducted using the noise-robust estimators α̂N           ∗
                                                                           LLS and β̂Cauchy . For
completeness, we present the analogous results using the non-noise-robust estimators α̂OLS and
β̂Cauchy in the Web Appendix. The findings using these estimators are very similar to those shown
in Figures 4 and 5.
    In summary, we find that roughness and persistence of log volatility extends to the level of
individual equities. By and large, they appear to be universal properties of the (logarithm of)
realized measures of volatility of equities. (Again with the caveat that these conclusions can,
strictly speaking, only be made about the observable quantities, i.e., the realized measures, and


                                                         29
   0.2
   0.1
     0
  -0.1
  -0.2
  -0.3
  -0.4
  -0.5
         6             8            10              12           14             16             18



            ∗
Figure 6: α̂N LLS as a function of average log(mean daily volume). The crosses correspond to
individual assets in the data set. The line has been fitted by OLS.


not about the latent spot volatility process itself.)


5.2.1        Roughness and liquidity

Figure 3 examined the evolution of estimates of the roughness parameter α, obtained from the
E-mini S&P 500 volatility data, over time. The degree of roughness appears to be variable in time
and less rough periods seem to be concordant with periods of market turmoil. Given these findings
on time-varying roughness, we conjecture that there is a connection between how actively an asset
is traded and how rough its volatility is. In particular, we expect the volatility of a highly liquid
asset to be smoother than the volatility of a less liquid asset. To briefly explore this idea, Figure
6 plots the noise-robust NLLS estimates of α against a measure of liquidity, the logarithm of the
average daily volume. The fitted line indicates an increasing pattern (the slope is 0.0091 with a
standard deviation of 0.001), lending support to the conjecture. While a compelling explanation
for this finding remains to be discovered in future work, it is plausible that market microstructure
is at play here. In fact, Jaisson and Rosenbaum (2016) and El Euch et al. (2018) have recently
developed a theoretical framework in which trade execution algorithms that split large trades, that
is, parent orders (or metaorders) into schedules of multiple smaller child orders can give rise to
rough volatility on aggregate. It is also worth mentioning the recent paper by Glasserman and
He (2019), where they demonstrate, influenced by an earlier version of the present paper, that
a factor investment strategy that uses roughness of volatility as a factor, has had very favorable
performance during the recent years.




                                                  30
6         Application to volatility forecasting
In this section we apply the BSS and Cauchy models to forecast intraday volatility of the E-
mini S&P 500 futures contract, comparing the results with a number of benchmark models. The
benchmark models can roughly be divided into three categories:
     (i) standard models,

     (ii) highly persistent models (possibly with long memory),

    (iii) rough volatility models.
The category (i) consists of the random walk (RW), autoregressive models (AR) and an ARMA(1, 1)
model; (ii) of the (log) heterogeneous autoregressive (log-HAR) model of Corsi (2009) as well as
two ARFIMA models; (iii) contains only the rough fractional stochastic volatility (RFSV) model
of Gatheral et al. (2018). As for the models suggested in this paper, we consider the Cauchy
process and the Power-BSS and Gamma-BSS models. As discussed above, these three processes
all decouple long- and short-term behavioral characteristics, so with suitable parameter values,
they can be seen as members of both (ii) and (iii).15
         The ARMA and ARFIMA models have been estimated by maximum likelihood.16 The AR
models, as well as the log-HAR model, have been estimated by OLS. We apply an intraday adap-
tation of the standard log-HAR model. The time periods used in constructing the HAR regressors
are still one day, one week, and one month, respectively, but the regressors need to be adapted to
the step size ∆, which may now be less than a day. More precisely, our log-HAR regression is
                                                                             
              ∆∗
                    = a0 + a1 log BVt∆∗ + a2 log BVt∆∗,day + a3 log BVt∆∗,week
                                       
      log BVt+∆h                                                                           (6.1)
                                        
                    + a4 log BVt∆∗,month + t+∆h ,

where
                             q−1
                      1
           BVt∆∗,x :=
                             X
                                      ∆∗
                                   BVt−k∆ ,   x = day, week, month,
                         q
                             k=0
and q is an integer such that q∆ = x. For instance, when ∆ = 65 minutes then q = 6 for x = day
(6 periods of 65 minutes during a trading day) whereas q = 30 for x = week (5 trading days, each
consisting of 6 periods, in a week).17
    15
         While the BSS models are initially defined in continuous time for the log volatility process Xt = log(σt /ξ),
t ≥ 0, cf. equation (2.3), we can apply them, or rather their correlation structure, here in discrete time to forecast
                                                                                   c∆
IV via its estimate BV ∆∗ , as motivated by the approximation of σt by σ̂t2 = ∆−1 IV  t , cf. equation (5.2).
    16
         The ARMA model has been estimated and forecasted using the MFE toolbox of Kevin Sheppard, see: https:
//www.kevinsheppard.com. The ARFIMA models has been estimated and forecasted using the MATLAB package
“ARFIMA(p,d,q) estimator” available from MATLAB Central.
  17
     Although not indicated here, in the variables entering the log-HAR model, all pre-averaged estimates of integrated
variance are de-seasonalized when we estimate and forecast the model for ∆ < 1 day. The seasonal factor is re-
introduced after estimation and forecasting.


                                                            31
       The estimate of the Hurst index H in the RFSV model is derived via Ĥ = α̂OLS + 0.5, and for
the Cauchy and BSS processes we use the parametric estimates of β, γ, and λ along with α̂OLS .
Forecasting the AR and log-HAR models is standard. To forecast the RFSV model, we use the
the following approximation (cf. Gatheral et al., 2018, equation (5.1))

                2
                       
         E log σt+h∆ Ft
                                                  Z t
                           cos(Hπ)                             log σs2
                       ≈           (h∆)H+1/2                            H+1/2
                                                                                 ds
                              π                   −∞ (t − s + h∆)(t − s)
                                                  ∞ Z t−(j−1)∆
                           cos(Hπ)                X                      log σ 2   s
                       =           (h∆)H+1/2                                                    ds
                              π
                                                  j=1    t−j∆      (t − s + h∆)(t − s)H+1/2
                                                   ∞                  Z t−(j−1)∆
                           cos(Hπ)                X                                          1
                       ≈           (h∆)H+1/2                 2
                                                        log σt−(j−1)∆                                      ds,
                              π
                                                  j=1                   t−j∆      (t − s + h∆)(t − s)H+1/2

where Ft is the information set (σ-algebra) generated by the fBm driving the model up to time t.
The integrals are approximated by Riemann sums.
       To forecast the Cauchy and BSS processes we rely on the elementary result that for a zero-
mean Gaussian random vector (xt+h , xt , xt−1 , . . . , xt−m )T the distribution of xt+h conditionally on
(xt , xt−1 , . . . , xt−m )T = a ∈ Rm+1 is

        xt+h | (xt , xt−1 , . . . , xt−m )T = a ∼ N (µ, ξ 2 ),
                 


where

         µ = Γ12 Γ−1
                  22 a,

with Γ22 being the correlation matrix of the vector (xt , xt−1 , . . . , xt−m )T , and

         Γ12 := (Corr(xt+h , xt ), Corr(xt+h , xt−1 ), . . . , Corr(xt+h , xt−m )) .

       Since the processes we consider here are stationary, the variance ξ 2 of the conditional distribu-
tion is

         ξ 2 = V ar(xt ) 1 − Γ12 Γ−1
                                        
                                  22 Γ21 ,

where Γ21 = ΓT12 .
       To implement this procedure for the Cauchy and BSS models, we assume Gaussianity of the
process and use these results, where the correlation matrices and vectors above are calculated
from the theoretical correlation structure of the process in question, implied by the estimated
parameters. When forecasting log volatility, only the conditional mean µ needs to be calculated.
However, as we will argue in the next section, the conditional variance term ξ 2 will be important
in forecasting (non-logarithmic) volatility. These results rely on X having mean zero, so in our
forecasting experiment we de-mean the data before conducting the experiment.18
  18
       In our model for volatility, this de-meaning essentially means removing the term log ξ = µ, cf. equation (2.3).
We reintroduce this term after forecasting X.


                                                            32
6.1     Forecasting intraday integrated variance

The previous section lays out methods of forecasting log volatility or, equivalently, the process X,
cf. equation (2.3). However, it is in practice more relevant to forecast non-logarithmic volatility.
Before presenting the forecasting results for this quantity, we briefly explain our approach.
   As we are now interested in E[exp(Xt+∆ )|Ft ], instead of exp(E[Xt+∆ |Ft ]), it is worth reminding
that it is a flawed strategy to simply forecast log volatility as above and then exponentiate the
forecast. Indeed, by Jensen’s inequality we know this approach to be biased. However, we can
often correct the exponentiated forecasts following a simple approach. For the BSS and Cauchy
models we follow the strategy of the preceding section. That is, if we again assume Gaussianity,
we have
                                                             
                                              1
        E[exp(Xt+∆ )|Ft ] = exp E[Xt+∆ |Ft ] + V ar[Xt+∆ |Ft ] .                                  (6.2)
                                              2

We will then approximate the former term in the exponential function by µ and the latter by 12 ξ 2 .
Note that ξ 2 depends on the (stationary) variance of the process, V ar(xt ); this factor we simply
estimate from the (unconditional) variance of the time series being forecasted.
   As for the other models, Gatheral et al. (2018) proposed a similar correction to their RFSV
model (see Gatheral et al., 2018, Section 5.2), which we use in the following. As the log-HAR model
is estimated by OLS using the log BV ∆∗ data, cf. equation (6.1), we exponentiate these estimates
and make a correction similar to (6.2), where the variance factor is estimated as the variance of
the error term in the OLS regression (6.1). The remaining models are estimated directly using the
raw (de-seasonalized) BV ∆∗ data, so no correction is needed.


6.1.1     Forecast setup

We use the methodology described above to forecast integrated variance, as this is most often the
object of interest in applications. Since integrated variance is not actually observable, as a feasible
forecast object (FO) we use
                        h
                        X                Z t+h∆
                                 ∆∗
        FOt (∆, h) :=         BVt+k∆ ≈            σs2 ds,    h = 1, 2, 5, 10, 20,                 (6.3)
                        k=1                t


where BVt∆∗ is the estimated value of integrated variance using the pre-averaged bipower variation
estimator, cf. Section 5.
                                                                        c2
   To forecast the FO in (6.3), we compute the h individual components, σ  t+k∆|t , k = 1, . . . , h,
multiply by ∆ and the seasonal component, and sum them up:
                       h
                       X
                              c2         s
                                              2
        FO
        c t (∆, h) =          σ  t+k∆|t σt+k∆    ∆,
                        k=1




                                                            33
where σts is the (deterministic) seasonal component of volatility we extracted in the preliminary
                                                     c2
step of our analysis, as explained in Section 5, and σ     is the forecast of volatility, as detailed
                                                               t+k∆|t
above.19
       In the forecasting experiments we consider various step sizes ∆, ranging from 15 minutes to
1 day, and various forecast horizons h ∈ {1, 2, 5, 10, 20}. We start the estimation after an initial
period of m ∈ N time steps and compare the performance of the forecasts using two different loss
functions:

       • Mean Squared Error (MSE):
                                          Pn−h c                      2
                              1
               MSE(∆, h) = n−h−m+1         t=m FOt (∆, h) − FOt (∆, h) ,

       • “Quasi-likelihood” (QLIKE):
                                1           Pn−h                              
                                                         c t (∆, h) + FOt (∆,h) .
               QLIKE(∆, h) = n−h−m+1           t=m   log FO           c FOt (∆,h)

       As discussed in Section 5, the the pre-averaged estimate BV ∆∗ , our FO, is a noisy estimate of
integrated variance, but Patton (2011) shows that the MSE and QLIKE loss functions still yield
consistent rankings of the forecasting models even for integrated variance, in spite of the noisy
estimates used to evaluate the loss functions. We calculate MSE, QLIKE, and also the model
confidence set (MCS) of Hansen et al. (2011), which is a procedure to construct a “set of best
models” with a certain probability, as measured by the specific loss function in question, avoiding
the problems that arise from doing multiple comparisons by pairwise tests. For instance, the best
model is contained in the 90% MCS — when understood as a random set — with 90% probability.
       We set up our forecasting experiment so that it is realistic and mirrors the situation a prac-
titioner would face if they were to forecast intraday volatility. At time t, we use only the data
observed so far to estimate the models and forecast h steps ahead, for h = 1, 2, 5, 10, 20. We then
move one step forward in time, to t + ∆, re-estimate the models, to allow for time variation in the
parameters, and compute new forecasts h steps ahead. In re-estimation, we used a rolling window
of 200 observations. While this window length is somewhat arbitrary, brief experimentation with
other window lengths suggests that our results are not particularly dependent on this choice. We
note that, since this forecasting exercise entails that the parameters of the various models need to
be re-estimated many times, we found it infeasible to use the NLLS estimator of α here, and we
therefore use the OLS estimator instead. As shown in Table 3, these two estimators often yield
similar estimates when applied to this data set, so we expect the OLS estimator to be adequate
for the purposes of this forecasting exercise.
       We assess the forecasting performance of the different models over two time periods using the
E-mini S&P 500 data set. First we forecast over a long out-of-sample period from from January 3,
  19
       To keep the procedure realistic, in the out-of-sample experiment discussed below, the seasonal component is
estimated in a non-anticipative fashion, using only the observations that would be available at the time when the
forecast is produced.


                                                         34
2005 to December 31, 2014, using the the entire data set at our disposal (cf. Section 5.1.1, where
we presented evidence of the roughness parameter varying in time). This period contains a couple
of abrupt market crashes (e.g., the bankruptcy of Lehman Brothers on September 15, 2008 and
the Flash Crash on May 6, 2010), precipitated by circumstances that would have been hard to
predict by virtually any model based on historical volatility data only. We observed that failing
to forecast the volatility bursts during such episodes leads to disproportionately large losses with
both MSE and QLIKE, and especially with MSE, these individual losses can represent a significant
proportion of the total loss. This phenomenon also affects the MCS procedure, which would not
be very selective over this long out-of-sample period. For this reason, we also experiment with
another, shorter out-of-sample period from from January 2, 2013 to December 31, 2014. Volatility
over this period is less pronounced, exemplifying “non-stressed” market conditions.


6.1.2     Results of out-of-sample forecasting experiment

Figure 7 plots the cumulative QLIKE losses for select models in the case of forecasting intraday
(∆ = 15 minutes) integrated variance over the long out-of-sample period from 2005 to 2014. We
employ the QLIKE loss function since it is less prone to exaggerating the impact of large forecast
errors than MSE (Patton, 2011). We present our results on the cumulative losses relative to those
arising when the Gamma-BSS model is used. More precisely, the graphs present, as a function of
time t,
                                                  bt/∆c
                                                   X
        Cumulative QLIKE (vs. Gamma-BSS)xt :=             (QLIKE(x)k − QLIKE(Gamma-BSS)k ) ,
                                                   k=1

where x ∈ {HAR, RFSV, Cauchy, Power-BSS} denotes the model being compared to the Gamma-
BSS model, and QLIKE(x)k stands for the k’th loss using model x. With this definition, positive
numbers indicate that the model performs worse than the Gamma-BSS model and vice versa for
negative numbers.
   We observe that both the Gamma-BSS and especially the Power-BSS models perform well
over the entire period. Interestingly, as the forecasting horizon h is increased, the Cauchy model
performs better relative to the Gamma-BSS model, suggesting that the long memory property of
the Cauchy model, which is absent from the Gamma-BSS model, becomes relevant.
   Turning now to the shorter out-of-sample period from January 2, 2013 to December 31, 2014
that represents calm market conditions, we present more detailed forecasting results for ∆ =
15, 30, 65 minutes and ∆ = 1 day in Tables 4 and 5. There, a boldface number identifies the model
with the smallest loss, while light grey background highlights the models in the 90% MCS and dark
grey background those in the 75% MCS. The models proposed in this paper generally outperform
the benchmarks over this period. Indeed, in most cases either the Cauchy or the Power-BSS
model has the lowest MSE and QLIKE losses. Further, these two models are very often in the
75% MCS. These findings are most convincing for the intraday values of ∆, while, interestingly,

                                                35
                                                                       h=1                                                                          h=5
                                                 300                                                                               300
             Cumulative QLIK E (vs. Gamma-BSS)




                                                                                               Cumulative QLIK E (vs. Gamma-BSS)
                                                           HAR
                                                 250       RFSV
                                                           Cauchy
                                                           Power-BSS
                                                                                                                                   200
                                                 200

                                                 150
                                                                                                                                   100
                                                 100

                                                  50
                                                                                                                                     0
                                                   0

                                                  -50                                                                              -100
                                                    2005    2007       2010     2012   2015                                           2005   2007   2010     2012   2015



                                                                       h = 10                                                                       h = 20
                                                 500                                                                               800
Cumulative QLIK E (vs. Gamma-BSS)




                                                                                               Cumulative QLIK E (vs. Gamma-BSS)

                                                 400                                                                               600
                                                 300
                                                                                                                                   400
                                                 200
                                                                                                                                   200
                                                 100
                                                                                                                                     0
                                                   0

                                                 -100                                                                              -200

                                                 -200                                                                              -400
                                                    2005    2007       2010     2012   2015                                           2005   2007   2010     2012   2015


Figure 7: Cumulative QLIKE forecast errors through time. Here, h is the forecast horizon (i.e.,
volatility is forecasted over a time interval of length h∆) and ∆ = 15 minutes.


RFSV turns out to be the best performing model when ∆ = 1 day. (Unfortunately, the MCS is not
very selective in this case, at least when using MSE as the loss function.) This result agrees with
Gatheral et al. (2018), where the authors demonstrated that the RFSV model can outperform a
range of benchmark models when forecasting daily integrated variance one step ahead.
                                                 We remark on the perhaps surprising observation that including a long memory component
seems to also improve short term forecasts. Further research into the reasons for this would be
interesting and valuable. All in all, the results presented in this section suggest that it is in general
advantageous to exploit the roughness of volatility in forecasting, and at intraday time scales,
careful modeling of persistence can further improve the quality of forecasts.




                                                                                              36
                                                Table 4: Out-of-sample forecasting of intraday integrated variance
        Panel A: ∆ = 15 minutes

                                          h=1                        h=2                          h=5                        h = 10                  h = 20

                                  MSE       QLIKE            MSE       QLIKE             MSE        QLIKE             MSE         QLIKE           MSE      QLIKE
                                  ×1011                      ×1011                       ×1010                       ×109                        ×108

       RW                         0.229     −12.883          0.733     −12.153           0.471      −11.147          0.245       −10.355         0.102     −9.553
       AR5                        0.178     −12.928          0.472     −12.214           0.220      −11.252          0.079       −10.509         0.027     −9.754
       AR10                       0.187     −12.931          0.494     −12.217           0.226      −11.257          0.077       −10.514         0.027     −9.760
       ARMA(1,1)                  0.159     −12.932          0.433     −12.217           0.203      −11.255          0.074       −10.509         0.027     −9.748
       log-HAR3                   0.149     −12.941          0.408     −12.225           0.198      −11.260          0.079       −10.512         0.038     −9.745
       ARFIMA(0, d, 0)            0.145     −12.937          0.393     −12.222           0.176      −11.262          0.059       −10.522         0.021     −9.772
       RFSV                       0.145     −12.947          0.384     −12.232           0.170      −11.268          0.057       −10.525         0.020     −9.774
       Cauchy                     0.143     −12.948          0.382     −12.234           0.164      −11.274          0.053       −10.533         0.019    −9.783
       Power-BSS                  0.142     −12.950          0.377    −12.235            0.163     −11.274           0.053       −10.533         0.019     −9.783
       Gamma-BSS                  0.142     −12.949          0.377     −12.234           0.164      −11.273          0.054       −10.531         0.019     −9.780

        Panel B: ∆ = 30 minutes
37




                                          h=1                        h=2                          h=5                         h = 10                 h = 20

                                  MSE        QLIKE            MSE      QLIKE              MSE       QLIKE             MSE         QLIKE          MSE       QLIKE
                                  ×1011                      ×1010                        ×109                        ×109                       ×108

       RW                         0.596     −12.181          0.220     −11.435            0.170     −10.404           0.612       −9.617         0.264     −8.874
       AR5                        0.500     −12.213          0.154     −11.490            0.074     −10.512           0.259       −9.758         0.113     −9.037
       AR10                       0.501     −12.214          0.151     −11.491            0.073     −10.513           0.262       −9.761         0.117     −9.043
       ARMA(1,1)                  0.459     −12.215          0.142     −11.492            0.073     −10.511           0.261       −9.753         0.119     −9.023
       log-HAR3                   0.433     −12.227          0.131     −11.501            0.070     −10.517           0.300       −9.762         0.160     −9.032
       ARFIMA(0, d, 0)            0.432     −12.222          0.129     −11.498            0.062     −10.522           0.218       −9.772         0.088     −9.055
       RFSV                       0.438     −12.230          0.128     −11.504            0.060     −10.523           0.206       −9.772         0.089     −9.059
       Cauchy                     0.418     −12.229          0.122     −11.506            0.057     −10.530           0.199       −9.781         0.080    −9.067
       Power-BSS                  0.416     −12.231          0.122     −11.506            0.057     −10.529           0.199       −9.780         0.081     −9.065
       Gamma-BSS                  0.418     −12.230          0.124     −11.504            0.059     −10.526           0.205       −9.776         0.085     −9.059


     Out-of-sample Mean Squared Forecast Error (MSE) and QLIKE for all models considered in the paper. Forecasting period: January 2, 2013, to December 31,

     2014. Bold numbers indicate the model with the smallest forecast error (column-wise). The forecast object is the sum of realized kernels (6.3), approximating

     integrated variance, as explained in the text. We vary the step size ∆ and the forecast horizon h. Grey cells indicate models which are in the Model Confidence

     Set (column-wise); the dark grey denotes the 75% MCS, while the light grey denotes the 90% MCS. The MCS uses a block bootstrap method with 25 000 bootstrap

     replications and a block length of 6 time steps.
                                                 Table 5: Out-of-sample forecasting of intraday integrated variance
        Panel A: ∆ = 65 minutes

                                           h=1                        h=2                         h=5                         h = 10                 h = 20

                                   MSE       QLIKE             MSE          QLIKE         MSE          QLIKE          MSE         QLIKE          MSE       QLIKE
                                  ×1010                       ×109                        ×109                        ×108                       ×107

       RW                         0.314      −11.355          0.147     −10.579           0.675        −9.557         0.297       −8.822         0.127     −8.079
       AR5                        0.237      −11.389          0.074     −10.648           0.367        −9.659         0.158       −8.947         0.078     −8.226
       AR10                       0.247      −11.337          0.076     −10.615           0.378        −9.661         0.178       −8.949         0.093     −8.226
       ARMA(1,1)                  0.221      −11.390          0.071     −10.649           0.347        −9.656         0.154       −8.935         0.078     −8.206
       log-HAR3                   0.207      −11.404          0.067     −10.657           0.370        −9.662         0.178       −8.938         0.104     −8.189
       ARFIMA(0, d, 0)            0.205      −11.397          0.063     −10.658           0.302        −9.673         0.116       −8.960         0.047     −8.240
       RFSV                       0.201      −11.409          0.062     −10.664           0.281        −9.676         0.109       −8.966         0.047    −8.250
       Cauchy                     0.199      −11.406          0.059     −10.668           0.285     −9.683            0.108       −8.970         0.043     −8.248
       Power-BSS                  0.195      −11.409          0.058     −10.668           0.279        −9.682        0.107        −8.970         0.044     −8.247
       Gamma-BSS                  0.197      −11.407          0.059     −10.665           0.282        −9.679         0.109       −8.967         0.046     −8.242

        Panel B: ∆ = 1 day
38




                                           h=1                        h=2                        h=5                         h = 10                  h = 20

                                   MSE       QLIKE            MSE       QLIKE            MSE       QLIKE             MSE         QLIKE           MSE       QLIKE
                                   ×109                       ×108                       ×107                        ×106                        ×105

       RW                          0.614     −9.491           0.253     −8.783           0.170     −7.818            0.076        −7.045         0.035     −6.218
       AR5                         0.717     −9.531           0.326     −8.826           0.179     −7.882            0.053        −7.146         0.013     −6.405
       AR10                        0.729     −8.717           0.338     −7.976           0.185     −7.876            0.055        −7.142         0.014     −6.403
       ARMA(1,1)                   0.621     −9.537           0.266     −8.831           0.232     −7.883            0.189        −7.146         0.496     −6.400
       log-HAR3                    0.506     −9.543           0.179     −8.838           0.096     −7.890            0.034        −7.154         0.011     −6.403
       ARFIMA(0, d, 0)             0.542     −9.537           0.191     −8.830           0.104     −7.881            0.038        −7.144         0.013     −6.395
       RFSV                       0.493      −9.546           0.171     −8.843           0.091     −7.898            0.034       −7.160          0.014     −6.402
       Cauchy                      0.579     −9.537           0.195     −8.831           0.098     −7.884            0.034        −7.151         0.011     −6.401
       Power-BSS                   0.545     −9.543           0.186     −8.837           0.095     −7.889            0.033        −7.154         0.011     −6.405
       Gamma-BSS                   0.513     −9.547           0.176     −8.842           0.091     −7.895            0.032        −7.159         0.010    −6.412


     Out-of-sample Mean Squared Forecast Error (MSE) and QLIKE for all models considered in the paper. Forecasting period: January 2, 2013, to December 31,

     2014. Bold numbers indicate the model with the smallest forecast error (column-wise). The forecast object is the sum of realized kernels (6.3), approximating

     integrated variance, as explained in the text. We vary the step size ∆ and the forecast horizon h. Grey cells indicate models which are in the Model Confidence

     Set (column-wise); the dark grey denotes the 75% MCS, while the light grey denotes the 90% MCS. The MCS uses a block bootstrap method with 25 000 bootstrap

     replications and a block length of 6 time steps.
7    Conclusions
This paper has presented stochastic models that are able to simultaneously capture roughness and
persistence, which are two key empirical features found in realized volatility data. In particular,
when modeling log volatility, we advocate using a stochastic process that decouples short- and
long-term behavior. The Brownian semistationary process is a flexible and parsimonious example
of such a process; since it also allows for easy inclusion of non-Gaussianity and the leverage effect,
we argue that the Brownian semistationary process is a particularly good candidate model for
stochastic log volatility.
    Using our proposed two-step estimation approach, we have also presented a thorough investiga-
tion of the empirical characteristics of the volatility of the E-mini S&P 500 futures contract, both
at daily and shorter time scales. We find that realized measures of volatility of this contract are
indeed rough but also highly persistent. Moreover, by also looking at realized volatility data on
almost two thousand individual US equities, we corroborated these findings, suggesting that both
roughness and strong persistence are universal features of these types of data.
    It is important to note that, since realized measures are noisy estimates of integrated variance,
from which working out spot volatility is a numerically ill-posed problem, our findings need not
imply that the elusive spot volatility process is actually rough or persistent. However, we have
demonstrated extensively that models that incorporate these two characteristics are overwhelm-
ingly consistent with the observable statistical features of high-frequency volatility. We have also
shown that these models are capable of producing competitive volatility forecasts at daily and
shorter time scales. Therefore, irrespective of whether one accepts that volatility is actually rough,
we believe that ideas and models stemming from rough volatility offer a valuable alternative view-
point to volatility modelling, and a useful set of actionable tools, complementing the existing
models based on jumps and conventional stochastic volatility.


Acknowledgements
Previous versions of this work have been presented at the 9th Annual SoFiE Conference in Hong
Kong in June 2016, at the ICMS workshop At the Frontiers of Quantitative Finance in Edinburgh
in June 2016, at the 9th Bachelier World Congress in New York in July 2016, at the New Devel-
opments in Measuring & Forecasting Financial Volatility conference at Duke University, Durham,
NC in September 2016, at the 5th Imperial–ETH Workshop on Mathematical Finance in London
in March 2017, and at the Barcelona GSE Summer Forum workshop Fractional Brownian Motion
and Rough Models in Barcelona in June 2017; and we thank the audiences for stimulating com-
ments and questions. We also thank Jim Gatheral, Sherry Jiang, Mark Podolskij, Roberto Renò,
Peter Tankov, Erik Vogt, as well as two anonymous referees, and the Editor, Fabio Trojani, for
helpful remarks. Our research has been partially supported by CREATES (DNRF78), funded by


                                                 39
the Danish National Research Foundation, by Aarhus University Research Foundation (project
“Stochastic and Econometric Analysis of Commodity Markets”), and by the Academy of Finland
(project 258042).


References
Abi Jaber, E. and O. El Euch (2019). Multifactor approximation of rough volatility models. SIAM Journal
  on Financial Mathematics 10 (2), 309–349.

Alòs, E., J. A. León, and J. Vives (2007). On the short-time behavior of the implied volatility for jump-
  diffusion models with stochastic volatility. Finance and Stochastics 11 (4), 571–589.

Andersen, T. G. and T. Bollerslev (1997). Intraday periodicity and volatility persistence in financial markets.
  Journal of Empirical Finance 4 (2–3), 115–158.

Andersen, T. G. and T. Bollerslev (1998). DM-dollar volatility: Intraday activity patterns, macroeconomic
  announcements and longer run dependencies. Journal of Finance 53 (1), 219–265.

Andersen, T. G., T. Bollerslev, F. X. Diebold, and P. Labys (2001). The distribution of realized exchange
  rate volatility. Journal of the American Statistical Association 96 (453), 42–55.

Andersen, T. G., T. Bollerslev, F. X. Diebold, and P. Labys (2003). Modeling and forecasting realized
  volatility. Econometrica 71 (2), 579–625.

Andersen, T. G., O. Bondarenko, A. S. Kyle, and A. A. Obizhaeva (2016). Intraday trading invariance in
  the E-mini S&P 500 futures market. Working paper, available at: http://ssrn.com/abstract=2693810.

Asmussen, S. and P. W. Glynn (2007). Stochastic simulation: algorithms and analysis. New York: Springer.

Baillie, R. T. (1996). Long memory processes and fractional integration in econometrics. Journal of Econo-
  metrics 73 (1), 5–59.

Baillie, R. T., F. Calonaci, D. Cho, and S. Rho (2019). Long memory, realized volatility and heterogeneous
  autoregressive models. Journal of Time Series Analysis 40 (4), 609–628.

Barndorff-Nielsen, O. E. (1997). Normal inverse Gaussian distributions and stochastic volatility modelling.
  Scandinavian Journal of Statistics 24 (1), 1–13.

Barndorff-Nielsen, O. E. and A. Basse-O’Connor (2011).                Quasi Ornstein-Uhlenbeck processes.
  Bernoulli 17 (3), 916–941.

Barndorff-Nielsen, O. E., F. E. Benth, and A. E. D. Veraart (2013). Modelling energy spot prices by volatility
  modulated Lévy-driven Volterra processes. Bernoulli 19 (3), 803–845.




                                                      40
Barndorff-Nielsen, O. E., J. M. Corcuera, and M. Podolskij (2009). Power variation for Gaussian processes
  with stationary increments. Stochastic Processes and their Applications 119 (6), 1845–1865.

Barndorff-Nielsen, O. E., P. R. Hansen, A. Lunde, and N. Shephard (2008). Designing realized kernels to
  measure the ex post variation of equity prices in the presence of noise. Econometrica 76 (8), 1481–1536.

Barndorff-Nielsen, O. E. and J. Schmiegel (2007). Ambit processes: with applications to turbulence and
  tumour growth. In Stochastic analysis and applications, Volume 2 of Abel Symp., pp. 93–124. Berlin:
  Springer.

Barndorff-Nielsen, O. E. and J. Schmiegel (2009).         Brownian semistationary processes and volatil-
  ity/intermittency. In Advanced financial modelling, Volume 8 of Radon Series on Computational and
  Applied Mathematics, pp. 1–25. Berlin: Walter de Gruyter.

Barndorff-Nielsen, O. E. and N. Shephard (2002). Econometric analysis of realized volatility and its use in
  estimating stochastic volatility models. Journal of the Royal Statistical Society, Series B 64 (2), 253–280.

Barndorff-Nielsen, O. E. and N. Shephard (2004). Power and bipower variation with stochastic volatility
  and jumps. Journal of Financial Econometrics 1 (2), 1–48.

Bayer, C., K. Friz, and J. Gatheral (2016). Pricing under rough volatility. Quantitative Finance 16 (6),
  887–904.

Bennedsen, M. (2020). Semiparametric inference on the fractal index of Gaussian and conditionally Gaussian
  time series data. Econometric Reviews 39 (9), 875–903.

Bennedsen, M., A. Lunde, and M. S. Pakkanen (2017). Hybrid scheme for Brownian semistationary processes.
  Finance and Stochastics 21 (4), 931–965.

Bingham, N. H., C. M. Goldie, and J. L. Teugels (1989). Regular variation. Cambridge: Cambridge
  University Press.

Bollerslev, T. and J. H. Wright (2000). Semiparametric estimation of long-memory volatility dependencies:
  The role of high-frequency data. Journal of Econometrics 98 (1), 81–106.

Bos, C. S., P. Janus, and S. J. Koopman (2012). Spot variance path estimation and its application to
  high-frequency jump-testing. Journal of Financial Econometrics 10 (2), 356–389.

Cheridito, P., H. Kawaguchi, and M. Maejima (2003). Fractional Ornstein-Uhlenbeck processes. Electronic
  Journal of Probability 8, paper no. 3, 14 pp.

Christensen, K., R. C. A. Oomen, and M. Podolskij (2014). Fact or friction: Jumps at ultra high frequency.
  Journal of Financial Economics 114 (3), 576–599.

Comte, F. (1996). Simulation and estimation of long memory continuous time models. Journal of Time
  Series Analysis 17 (1), 19–36.


                                                     41
Comte, F., L. Coutin, and E. Renault (2012). Affine fractional stochastic volatility models. Annals of
  Finance 8 (3), 337–378.

Comte, F. and E. Renault (1996). Long memory continuous time models. Journal of Econometrics 73 (1),
  101–149.

Comte, F. and E. Renault (1998). Long memory in continuous-time stochastic volatility models. Mathe-
  matical Finance 8 (4), 291–323.

Constantine, A. G. and P. Hall (1994). Characterizing surface smoothness via estimation of effective fractal
  dimension. Journal of the Royal Statistical Society: Series B 56 (1), 97–113.

Cont, R. (2001). Empirical properties of asset returns: stylized facts and statistical issues. Quantitative
  Finance 1, 223–236.

Corsi, F. (2009). A simple approximate long-memory model of realized volatility. Journal of Financial
  Econometrics 7 (2), 174–196.

Ding, Z., C. W. J. Granger, and R. F. Engle (1993). A long memory property of stock market returns and
  a new model. Journal of Empirical Finance 1 (1), 83–106.

Dudley, R. M. and R. Norvais̆a (2011). Concrete functional calculus. New York: Springer.

El Euch, O., M. Fukasawa, and M. Rosenbaum (2018). The microstructural foundations of leverage effect
  and rough volatility. Finance and Stochastics 22 (2), 241–280.

Fleming, J. and C. Kirby (2011). Long memory in volatility and trading volume. Journal of Banking &
  Finance 35 (7), 1714–1726.

Fukasawa, M. (2017). Short-time at-the-money skew and rough fractional volatility. Quantitative Fi-
  nance 17 (2), 189–198.

Fukasawa, M., T. Takabatake, and R. Westphal (2019). Is volatility rough? Working paper, available at:
  https://arxiv.org/abs/1905.04852.

Gatheral, J. (2006). The volatility surface. Hoboken: Wiley.

Gatheral, J., T. Jaisson, and M. Rosenbaum (2018). Volatility is rough. Quantitative Finance 18 (6),
  933–949.

Glasserman, P. and P. He (2019). Buy rough, sell smooth. Quantitative Finance 20 (3), 363–378.

Gneiting, T. and M. Schlather (2004). Stochastic models that separate fractal dimension and the Hurst
  effect. SIAM Review 46 (2), 269–282.

Gneiting, T., H. Sevcikova, and D. B. Percival (2012). Estimators of Fractal Dimension: Assessing the
  Roughness of Time Series and Spatial Data. Statistical Science 27 (2), 247–277.


                                                    42
Gradshteyn, I. S. and I. M. Ryzhik (2007). Table of integrals, series, and products (Seventh ed.). Amsterdam:
  Academic Press.

Handcock, M. S. and M. L. Stein (1993). A Bayesian analysis of kriging. Technometrics 35 (4), 403–410.

Hansen, P. R. and A. Lunde (2006). Realized variance and market microstructure noise. Journal of Business
  and Economic Statistics 24 (2), 127–161.

Hansen, P. R., A. Lunde, and J. M. Nason (2011). The model confidence set. Econometrica 79 (2), 453–497.

Jacod, J., Y. Li, P. A. Mykland, M. Podolskij, and M. Vetter (2009). Microstructure noise in the continuous
  case: The pre-averaging approach. Stochastic Processes and their Applications 119 (7), 2249–2276.

Jaisson, T. and M. Rosenbaum (2016). Rough fractional diffusions as scaling limits of nearly unstable heavy
  tailed Hawkes processes. The Annals of Applied Probability 26 (5), 2860–2882.

Kristensen, D. (2010). Nonparametric filtering of the realized spot volatility: a kernel-based approach.
  Econometric Theory 23 (1), 60–93.

Matérn, B. (1960). Spatial variation: stochastic models and their application to some problems in forest
  surveys and other sampling investigations. Meddelanden från Statens Skogsforskningsinstitut, Band 49,
  Nr. 5, Stockholm.

Oomen, R. C. A. (2006). Comment on 2005 JBES invited address “Realized variance and market microstruc-
  ture noise” by Peter R. Hansen and Asger Lunde. Journal of Business and Economic Statistics 2 (24),
  195–202.

Patton, A. (2011). Volatility forecast comparison using imperfect volatility proxies. Journal of Economet-
  rics 160 (1), 246–256.

Poon, S.-H. and C. W. Granger (2003). Forecasting volatility in financial markets: A review. Journal of
  Economic Literature 41 (2), 478–539.

Rossi, E. and D. Fantazzini (2015). Long memory and periodicity in intraday volatility. Journal of Financial
  Econometrics 13 (4), 922–961.

Zhang, L., P. A. Mykland, and Y. Aı̈t-Sahalia (2005). A tale of two time scales: Determining integrated
  volatility with noisy high-frequency data. Journal of the American Statistical Association 100 (472),
  1394–1411.

Zu, Y. and H. P. Boswijk (2014). Estimating spot volatility with high-frequency financial data. Journal of
  Econometrics 181 (2), 117–135.




                                                     43
A        Pre-averaged measures of integrated variance
This section follows the methodology in Christensen et al. (2014) closely. Suppose we want to
estimate IV in some interval [(i−1)∆, i∆] for i ≥ 1 and we have N +1 observations, Z0 , Z1 , . . . , ZN ,
where Zi = log Sti , of the log price process Z = log S in this interval. We define the pre-averaged
log returns,
                                             
                    K−1          K/2−1
          ∗     1   X             X
         rj,K =        Z(j+k) −       Z(j+k)  ,                  j = 0, 1, . . . , N − K,
                K
                       k=K/2              k=0

                                                                                √
where K ≥ 2 is even. For the asymptotics to work, it is required that K = θ N + o N −1/4 ,
                                                                                                 
                                                     √        √
and in our implementation we set θ = 1 and K = b N c if b N c is an even number and K =
 √
b N c + 1 otherwise.20 Here, bxc means the largest integer smaller than, or equal to, x ∈ R. Using
these pre-averaged returns, we suggest the following estimators of IV, which are robust to market
microstructure noise:
                                        N −K+1
                       N       1          X
                                                   ∗           ω̂ 2
         RVt∆∗ =                                 |rj,K |2 −         ,
                    N − K + 2 KψK                             θ2 ψK
                                          j=0
                                            N −2K+1
                        N       1 π           X
                                                        ∗      ∗              ω̂ 2
         BVt∆∗ =                                      |rj,K ||rj+K,K |−            ,                           (A.1)
                    N − 2K + 2 KψK 2                                         θ2 ψK
                                                j=0

                                                                                  2
where ψK := (1 + 2K −2 )/12 and t ∈ [(i − 1)∆, i∆]. The term θ2ω̂ψK is a bias-correction, where ω̂ 2 is
an estimate of the variance of the microstructure noise process U . We use the estimator of Oomen
(2006):
                             N
           2          1 X
         ω̂AC =−          ri ri−1 ,
                    N −1
                            j=2


where ri = Zi − Zi−1 is the i-th log return. The statistics RV ∆∗ and BV ∆∗ are the pre-averaged
analogs of the realized variance (Andersen et al., 2001) and bipower variation (Barndorff-Nielsen
and Shephard, 2004) estimators of IV, respectively. While both estimators are robust to market
microstructure noise, only BV ∆∗ is also robust to jumps in the price process. This is the main
reason we use the BV ∆∗ estimate of IV in this paper.
  20
       Setting the tuning parameter θ equal to 1 was found to work well for data similar to ours in Christensen et al.
(2014). We drew the same conclusion from both simulated data mimicking our setup, as well from the actual data
analyzed later in the paper.




                                                              44
B     Mathematical proofs

B.1     Proofs of Propositions 2.2 and 2.3

Recall first that we can write
                R∞
                    g(x)g(x + |h|)dx
     ρX (h) = 0 R ∞         2
                                     ,           h ∈ R.
                      0 g(x) dx

Proof of Proposition 2.2. (i) We may assume that h > 1, since we let h → ∞. By the assumption
(A3), we may write
      Z ∞                  Z ∞
          g(x)g(x + h)dx =     g(x)(x + h)−γ L1 (x + h)dx
       0                    0
                                      Z ∞
                            −γ                            L1 (x + h)
                         = h L1 (h)       g(x)(x/h + 1)−γ            dx
                                       0                     L(h)
                                      Z ∞
                                                          L1 (h(x/h + 1))
                         = h−γ L1 (h)     g(x)(x/h + 1)−γ                 dx
                                       0                        L(h)
                                      Z ∞
                            −γ
                         ∼ h L1 (h)       g(x)dx, h → ∞,
                                                 0

using the properties of slowly varying functions and where we applied the dominated convergence
theorem, which is valid since for all  > 0 and large enough h,
             L1 ((x/h + 1)h)
      g(x)                   < g(x)(1 + ),          x ∈ (0, ∞),
                  L1 (h)
which is integrable over (0, 1) by assumption and over [1, ∞) since γ > 1.
    (ii) Let first
       Z ∞                   Z 1
            g(x)g(x + h)dx =     g(x)(x + h)−γ L1 (x + h)dx
         0                    0
                                Z ∞
                             +      x−γ (x + h)−γ L1 (x)L1 (x + h)dx
                                      1

                               =:I1,h + I2,h ,

where
               Z 1
      I1,h =          g(x)(x + h)−γ L1 (x + h)dx,
               Z0 ∞
      I2,h =          x−γ (x + h)−γ L1 (x)L1 (x + h)dx.
                1

We may write
                      Z ∞
                 −γ
                               x −γ
      I2,h = h     x−γ 1 +            L1 (x)L1 (x + h)dx
                1               h
                           Z ∞
            −2γ+1                              L1 (hy) L1 (h(1 + y))
          =h      L1 (h) 2
                                y −γ (1 + y)−γ                       dy,
                            1/h                 L1 (h)     L1 (h)
                                |                 {z               }
                                                      =:kh (y)


                                                          45
where the second equality follows by substituting y = x/h. Fix now δ ∈ (0, 1 − γ) ⊂ (0, 1/2). By
the Potter bounds (Bingham et al., 1989, Theorem 1.5.6(ii)), under (A3) there exists a constant
Cδ > 0 such that
      L1 (hy)
              ≤ Cδ max{y −δ , y δ },   y > 1/h,       h > 1.
      L1 (h)
Accordingly, we find a dominant for kh , given by
                      
                      Cδ y −γ−δ (1 + y)−γ+δ , y ∈ (0, 1],
                      
     kh (y) ≤ k(y) :=
                      Cδ y −2(γ−δ) ,
                      
                                                y ∈ (1, ∞),

for any h > 1. Note that the dominant k is integrable on (0, 1], since −γ − δ > −γ − (1 − γ) = −1,
as well as on (1, ∞), since −2(γ − δ) < −1. Applying the dominated convergence theorem, we get
                             Z ∞
              −2γ+1
      I2,h ∼ h      L1 (h) 2
                                 y −γ (1 + y)−γ dy, h → ∞.
                              0

Moreover, the asymptotic estimate I1,h ∼ ch−γ L1 (h), as h → ∞, can be deduced using the same
strategy as in (i). Observing that −γ < −2γ+1 when γ < 1, we deduce that I1,h = o h−2γ+1 L1 (h)2
                                                                                                 

as h → ∞, so the assertion follows.

Proof of Proposition 2.3. As in the proof of Proposition 2.2, we take h > 1 and write
     Z ∞                    Z ∞
          g(x)g(x + h)dx =       g(x)(x + h)−γ e−λ(x+h) L1 (x + h)dx
       0                      0
                                            Z ∞
                                                                     L1 (x + h)
                          = e−λh h−γ L1 (h)     g(x)(x/h + 1)−γ e−λx            dx
                                             0                          L(h)
                                            Z ∞
                             −λh −γ
                          ∼e     h L1 (h)       g(x)e−λx dx,
                                                  0

where we used the dominated convergence theorem, which can be justified in the same manner as
in the proof of Proposition 2.2.


B.2    Proof of Theorem 2.1

We first recall an elementary result that we will need below. Namely, as x ↓ 0,
      ∞
      X xk
                 = o(x).                                                                      (B.1)
            k!
      k=2

This result is easy to prove by examining the Taylor expansion of the exponential function and
applying l’Hôpital’s rule.

Proof of Theorem 2.1. (i) Suppose w.l.o.g. that ξ = 1. Since σ is covariance-stationary, it suffices
to study
                                  Cov(σt , σt+h )
      ρ(h) = Corr(σt , σt+h ) =                   ,   h ≥ 0.
                                    V ar(σ0 )

                                                      46
We get using the definition (2.3) of σ

      Cov(σt , σt+h ) = E[σt σt+h ] − E[σ0 ]2

                     = E[exp(Xt + Xt+h )] − E[exp(X0 )]2 .

Now, by the fact that X is a zero-mean Gaussian process we get, using the moment generating
function of the Gaussian distribution,
                                                    
                                  1
      E[exp(Xt + Xt+h )] = exp      V ar(Xt + Xt+h )
                                  2
                           = exp (V ar(X0 ) + cov(X0 , Xt+h ))

                           = exp (γX (0) + γX (h)) ,

and
                                     
                              1
      E[exp(X0 )] = exp         γX (0) ,
                              2

where we write γX (h) for Cov(Xh , X0 ) = E[Xh X0 ]. Putting this together, we arrive at

               exp(γX (h)) − 1
      ρ(h) =                   .
                exp(γ(0)) − 1
Now, using generic positive constants C, C1 , C2 that may vary from line to line,
                  exp(γX (0)) − 1 − (exp(γX (h)) − 1)
      1 − ρ(h) =
                             exp(γ(0)) − 1
                  exp(γX (0)) − exp(γX (h))
                =
                       exp(γ(0)) − 1
                = C [1 − exp(γX (h) − γX (0))]

                = C [1 − exp(−γX (0)(1 − ρX (h)))]
                                           ∞
                                           X (−γX (0)(1 − ρX (h)))k
                = C1 (1 − ρX (h)) + C2
                                                         k!
                                           k=2

                ∼ C|h|2α+1 L0 (h),

by the assumption on 1 − ρX (h) and the asymptotic result (B.1). (On the penultimate line, we
Taylor expanded the exponential.) This concludes the proof of (i).
   (ii) Suppose w.l.o.g. that ξ = 1. Using the same approach as in part (i), we get by Taylor
expansion:
               exp(γX (h)) − 1
      ρ(h) =
                exp(γ(0)) − 1
                              ∞
                              X γX (h)k
             = C1 γX (h) + C2
                                  k!
                               k=2


                                                    47
                                       ∞
                                       X γX (h)k
            = C1 γX (0)ρX (h) + C2
                                              k!
                                       k=2

            ∼ CρX (h),    h → ∞,

where we have finally applied (B.1).


B.3    Proof of Theorem 3.1

Proof of Theorem 3.1. Let
                                 m
                                 X                                  2
      Qn (θ) = Qn (a, b, α) :=          γ̂2∗ (k∆) − a − b(k∆)2α+1        ,
                                 k=1

and
                               m
                               X                                             2
      Q(θ) = Q(a, b, α) :=           a0 + b0 (k∆)2α0 +1 − a − b(k∆)2α+1           ,
                               k=1

where a0 := 2σu2 . Since, by the assumptions on X and Z, γ̂2∗ (k∆) is a consistent estimator of
a0 + b0 (k∆)2α0 +1 , it is not hard to show that

      sup |Qn (θ) − Q(θ)| → 0,         n → ∞.                                                   (B.2)
      θ∈Θ

Because m ≥ 3, θ0 := (a0 , b0 , α0 ) is the unique minimizer of Q(θ) (in fact Q(θ0 ) = 0), the rest of
the proof therefore follows standard arguments, which we give here for completeness.
   Let  > 0. For n sufficiently large, we have, because of the uniform convergence (B.2), that

      |Q(θ̂) − Qn (θ̂)| < .

Using first that Q(θ0 ) = 0, then that θ̂ minimizes Qn (θ), and finally the uniform convergence (B.2)
again, it holds that

      |Qn (θ̂) − Q(θ0 )| = Qn (θ̂) ≤ Qn (θ0 ) < ,

for n sufficiently large. Let B be an open neighborhood of θ0 . Now,

      P(θ̂ ∈ B c ∩ Θ) ≤ P(|Q(θ̂) − Q(θ0 )| > 0)

                       ≤ P(|Q(θ̂) − Qn (θ̂)| + |Qn (θ̂) − Q(θ0 )| > 0)

                       → 0,     n → ∞,

by the results above, since  > 0 was arbitrary.




                                                      48