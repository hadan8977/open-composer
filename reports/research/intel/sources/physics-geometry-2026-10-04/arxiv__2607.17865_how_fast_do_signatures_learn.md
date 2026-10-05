source: https://arxiv.org/pdf/2607.17865
fetched_utc: 2026-10-04T18:44:59Z
bytes_raw: 580551

How Fast Do Signatures Learn?
                                                 Statistical Theory and Applications for Path Regression

                                                         Blanka Horvath1,4∗, Wen Su1†, Wu Su2‡, Binnan Wang3§, Ruixun Zhang3,5¶

                                                                           1
                                                                               Mathematical Institute, University of Oxford, UK
                                                                          2
                                                                              Center for Data Science, Peking University, China
arXiv:2607.17865v2 [math.ST] 22 Aug 2026




                                                                 3
                                                                     School of Mathematical Sciences, Peking University, China
                                                                              4
                                                                                  Oxford Man Institute, University of Oxford, UK
                                                                     5
                                                                         Center for Statistical Science, Peking University, China


                                                                                               August 25, 2026


                                           Abstract: Many modern statistical learning and prediction problems involve path-valued covariates—
                                           data that evolve over time—for which path signatures have become a canonical feature represen-
                                           tation. Their use is justiﬁed by a universal approximation theorem, but this is an existence result:
                                           it guarantees that a ﬁnite-level signature can approximate any continuous path functional, without
                                           quantifying how fast the approximation error decreases as the truncation level grows. This paper
                                           develops approximation and statistical theory for signature-based path regression. We establish a
                                           minimax-optimal L2 approximation rate for smooth functionals of Itô diﬀusions and then propa-
                                           gate the truncation error through three statistical learning procedures—Signature-OLS, Signature-
                                           LASSO, and Signature-Logistic—to establish their consistency. Three real-data applications show
                                           that signatures provide informative ﬁnite-dimensional representations of path-valued covariates and
                                           can improve prediction relative to handcrafted features, in the context of ﬁnance—foreign exchange
                                           realized volatility forecasting from intraday price paths; energy—battery end-of-life prediction from
                                           early diagnostic current–voltage pulse paths; and medicine—epileptic seizure detection from short
                                           electroencephalogram windows.

                                           Keywords: Path regression, Path signature, Statistical learning, Universal approximation, Func-
                                           tional Data
                                             ∗
                                               Email: blanka.horvath@maths.ox.ac.uk
                                             †
                                               Email: wen.su@maths.ox.ac.uk
                                             ‡
                                               Email: wusu@stu.pku.edu.cn
                                             §
                                               Email: wangbinnan@stu.pku.edu.cn
                                             ¶
                                               Email: zhangruixun@pku.edu.cn


                                                                                                       1
1 Introduction

Many modern statistical learning and prediction problems involve information that evolves over
time. Foreign exchange realized volatility forecasting, battery end-of-life prediction, epileptic seizure
detection, and other complex dynamic problems often include path-valued covariates. In these
settings, the response may depend not only on the terminal state of the trajectory, but also on the
path by which that state is reached, including the timing of changes, local ﬂuctuations, cumulative
variation, and ordered interactions among multiple coordinates. We refer to regression with such
path-valued covariates as path regression.

   Path-valued covariates are inherently inﬁnite-dimensional and therefore diﬃcult to analyze di-
rectly. A natural approach is to transform the path into ﬁnite-dimensional features. Handcrafted
summaries can be eﬀective in speciﬁc domains, but they are often problem-dependent and may
fail to capture important pathwise interactions. Classical functional data methods provide general
basis expansions, but they do not automatically encode the noncommutative temporal order of a
trajectory. The path signature, introduced by Chen (1957) and developed in rough path theory
(Lyons, 1998; Friz and Victoir, 2010), oﬀers a canonical hierarchy of ordered path features through
iterated integrals. Its lower levels record path increments, while higher levels describe ordered
interactions across time and coordinates. The seminal universal approximation theorem for signa-
tures states that any continuous functional of a path can be approximated by a linear functional
of its signature. This universal approximation property provides the main theoretical justiﬁcation
for using truncated signatures in path regression (Király and Oberhauser, 2019; Fermanian, 2022;
Chevyrev and Kormilitzin, 2025; Guo et al., 2025).

   One major theoretical gap in the signature-based statistical learning framework is that the clas-
sical universal approximation theorem alone is not suﬃcient to ensure consistency. It is qualitative:
it ensures approximation as the truncation order increases, but does not quantify how fast the
approximation error decreases. Once truncated signatures are used in regression, this missing rate
becomes crucial.

   This paper develops the approximation error rate for truncated signatures and propagates it
through three widely used path regression frameworks. First, focusing on a class of smooth func-
tionals of Itô diﬀusions, we prove that the minimax-optimal squared approximation error is of order
K −2γ , where K is the truncation level and γ characterizes the smoothness of the functional. We



                                                   2
then use this rate to analyze ordinary least squares (OLS), least absolute shrinkage and selection
operator (LASSO), and logistic regression based on truncated signatures for path-valued data, and
illustrate the resulting framework in three real-data prediction problems. In this sense, the pa-
per provides a quantitative foundation for signature-based path regression and demonstrates its
eﬀectiveness in real-data applications.

   Our contribution is threefold. First, the established approximation rates ﬁll the current gap in
the signature-based learning framework. We begin with Brownian motion as a benchmark to show
how signatures play the role of polynomials on path space. We then establish the main approxi-
mation result for a class of smooth coeﬃcient functionals of Itô diﬀusions generated through time
and Stratonovich integrals. We further derive a matching lower bound, showing that the resulting
rate is optimal over the corresponding smoothness class. Second, we develop statistical theory
for regression with truncated signature features. Using the established approximation bounds, we
derive consistency results for OLS, LASSO, and logistic regression. Our analysis also provides a
general template for studying the same approximation–estimation tradeoﬀ in other statistical learn-
ing methods based on signatures. Third, we illustrate the framework through simulations and three
prediction problems with path-valued covariates: foreign exchange realized volatility forecasting,
battery end-of-life prediction, and electroencephalogram (EEG) seizure detection. The simulations
verify the theoretical results while the empirical studies demonstrate improvements over methods
based on handcrafted features.


Related Literature.   This paper is related to several strands of literature. The ﬁrst strand concerns
the mathematical foundations of signatures. Signatures originate from Chen’s theory of iterated
integrals (Chen, 1957) and became a central object in rough path theory after Lyons (1998). Their
injectivity and law-characterization properties have been studied in Hambly and Lyons (2010),
Boedihardjo et al. (2016), and Chevyrev and Lyons (2016). A key reason signatures are useful for
statistics and machine learning is their universal approximation property: after time augmentation,
linear functionals of signatures can approximate a large class of continuous path functionals. This
property turns nonlinear path dependence into linear learning on a structured hierarchy of iterated-
integral features. However, the usual universal approximation theorem is qualitative. It guarantees
the existence of accurate ﬁnite-level approximations, but does not quantify how the truncation level
controls the approximation error.



                                                  3
   The second strand concerns signature-based learning methods. Signatures have been used as
features for stream regression (Levin et al., 2013), kernel methods (Király and Oberhauser, 2019),
deep learning architectures (Kidger et al., 2019), neural rough diﬀerential equations (Morrill et al.,
2021), and moment-based inference for laws of stochastic processes (Chevyrev and Oberhauser,
2022). They have also been applied in a range of path-valued prediction problems, including
nonparametric pricing and hedging (Lyons et al., 2020), model calibration (Cuchiero et al., 2023),
path-dependent option pricing (Bayraktar et al., 2024), and optimal stopping (Bayer et al., 2025).
Related path-based prediction tasks also arise in atmospheric prediction (Fujita et al., 2024), battery
prognostics (Severson et al., 2019; Attia et al., 2020; Ibraheem et al., 2025), and EEG seizure
detection (Shoeb and Guttag, 2010). These studies show that signature features can be eﬀective
in practice. Our paper studies the statistical question behind these applications: when a path
functional is approximated by a truncated signature representation, under what conditions does
the resulting estimator remain statistically consistent?

   The paper is also related to the literature on functional data regression. A common approach
in this literature is to represent functional covariates through the leading eigenfunctions of their
covariance operator and regress the response on the resulting functional principal component scores
(Dauxois et al., 1982; Cardot et al., 1999; Ramsay and Silverman, 2005; Hall and Horowitz, 2007).
Unlike functional principal component regression, signatures are organized by iterated-integral or-
der and capture nonlinear ordered interactions across time and coordinates. Fermanian (2022)
studied truncated signatures in functional linear regression and showed that they are competitive
with traditional functional linear methods, particularly when the functional covariates are high-
dimensional.

   The statistical frameworks most closely related to ours are those developed in the seminal works
of Fermanian (2022) and Guo et al. (2025). Fermanian (2022) studied functional linear regression
using truncated signatures, while Guo et al. (2025) established LASSO consistency for signature
regression under sparse ﬁnite-level representations. Our contribution diﬀers from these works in
three main ways. First, we derive an L2 approximation rate for truncated signatures, whereas these
studies treat the truncated signature model as exact and do not model the ﬁnite-level approximation
error. Second, Fermanian (2022) studied path functionals of bounded-variation paths, and Guo
et al. (2025) studied Brownian motion and discussed the Ornstein–Uhlenbeck (OU) process. In
contrast, this paper studies path functionals of general Itô diﬀusions and identiﬁes smoothness



                                                  4
conditions under which quantitative signature approximation rates can be obtained. Third, this
paper develops Signature-OLS, Signature-LASSO, and Signature-Logistic frameworks. The general
strategy of balancing truncation error and statistical error can also be adapted to other statistical
learning methods based on truncated signature features.


   The rest of the paper is organized as follows. Section 2 reviews the deﬁnitions and basic prop-
erties of signatures, the universal approximation theorem, and the signature-based path regres-
sion. Section 3 develops L2 approximation rates for smooth coeﬃcient functionals of Itô diﬀusions.
Section 4 establishes the statistical theory for Signature-OLS, Signature-LASSO, and Signature-
Logistic regression. Section 5 reports Monte Carlo simulation results, and Section 6 presents three
real-data applications: foreign exchange realized volatility forecasting, battery end-of-life predic-
tion, and EEG seizure detection. Section 7 concludes. The appendices contain technical proofs and
additional numerical details.


Notation: For a vector v, kvk, kvk1 , and kvk∞ denote the Euclidean, ℓ1 , and maximum norms,
respectively. For a matrix A, A⊤ denotes its transpose, kAk denotes the operator norm, kAk∞
denotes the maximum absolute row-sum norm, and kAkF denotes the Frobenius norm. When A
is symmetric, λmin (A) and λmax (A) denote its smallest and largest eigenvalues, respectively. We
write A  0 if A is positive semideﬁnite, and write Id for the d-dimensional identity matrix. For a
set A, Ac denotes its complement and |A| denotes its cardinality. For a path X = {Xt }t∈[0,T ] , FTX
denotes the sigma-ﬁeld generated by the path up to time T . For a domain D, H γ (D) = W γ,2 (D)
denotes the usual L2 -Sobolev space of order γ. We write W γ,∞ (D) for the Sobolev space whose
derivatives up to order γ are uniformly bounded. For sequences an and bn , an = O(bn ), an = o(bn ),
and an  bn have their usual asymptotic meanings. The notation OP (·) and oP (·) denotes stochastic
           d
order, and −
           → denotes convergence in distribution.



2 Preliminaries

This section reviews the signature transform used throughout the paper. Further background on
signatures can be found in Bayer et al. (2026).




                                                  5
2.1 Signature
                                                                                                         ⊤
Let {Xt }t∈[0,T ] be an Rd -valued continuous stochastic process, written as Xt = Xt1 , Xt2 , . . . , Xtd .
                                                                                          Rt
For each i ∈ {1, 2, . . . , d}, the ﬁrst-level signature component is deﬁned by S(X)i0,t = 0 dXsi = Xti −
X0i , which is the increment of the i-th coordinate. For 1 ≤ i, j ≤ d, we deﬁne second-level signature
             Rt                  R
S(X)i,j                    j                      j
       0,t = 0 S(X)0,s dXs = 0<r<s<t dXr dXs . More generally, for any 1 ≤ i1 , . . . , ik ≤ d, we
                      i                      i


deﬁne the k-fold iterated integral

                                                            Z
                                        S(X)i0,t
                                              1 ,...,ik
                                                        =                         dXti11 · · · dXtikk .         (1)
                                                                0<t1 <···<tk <t


            i1 ,...,ik
We call S(X)0,t        a k-th level signature component. When the starting time is 0, we write
S(X)it1 ,...,ik for S(X)i0,t
                          1 ,...,ik
                                    .

Deﬁnition 1 (Signature) The signature of X over [0, T ] is the collection of all iterated integrals:
                                                                                    
S(X)T = 1, S(X)1T , . . . , S(X)dT , S(X)1,1
                                         T   , . . . , S(X) d,d
                                                            T   , S(X) 1,1,1
                                                                       T     , . . .   , where the level-0 term equals
1 by convention.


    The signature can be deﬁned using either Itô or Stratonovich iterated integrals, depending on the
application. Throughout this paper, since the Stratonovich signature satisﬁes the shuﬄe identity
and is more widely used, we use it unless otherwise stated. Since S(X)T is inﬁnite-dimensional,
one often works with the truncated signature S(X)≤K
                                                 T , deﬁned to be all signature components with
                                                                   ct = (t, X ⊤ )⊤ is usually used,
levels not exceeding K. Also, the signature of time-augmented path X         t

which removes the ambiguity caused by time reparametrization.

    The signature is rich in representing path information. For bounded-variation paths or contin-
uous semimartingales X and Y starting at the same initial value x0 , one has


                                  c T = S(Yb )T
                                S(X)                            ⇔      Xt = Yt , 0 ≤ t ≤ T, a.s.                (2)


This property is often referred to as the uniqueness of signature; see Hambly and Lyons (2010)
and Lemma 2.6 of Cuchiero et al. (2023) for related statements. Hence, the full signature of the
time-augmented path preserves the information of the whole path.




                                                                      6
2.2 Universal Approximation

We next recall the signature universal approximation theorem. It states that, on compact sets of
time-augmented paths, every continuous path functional can be uniformly approximated by a ﬁnite
linear combination of signature coordinates. Speciﬁcally, for any compact set C of time-augmented
paths, any continuous functional f : C → R, and any ϵ > 0, there exists ℓ with only ﬁnitely many
nonzero coordinates such that

                                             D        E
                                          c − ℓ, S(X)
                                   sup f (X)       c T ≤ ϵ.                                      (3)
                                   c
                                   X∈C


Thus, linear functionals of the full time-augmented signature form a rich class of functions on path
space. In this sense, signature coordinates play the role of monomials for path-valued inputs; see,
for example, Hambly and Lyons (2010), Proposition A.6 of Kidger et al. (2019), and Theorem 2.12
of Bayraktar et al. (2024).

     Motivated by the universal approximation theorem, signatures are widely used in path regres-
sion. We use signature-based linear regression as a leading example. Let Z be a scalar response
variable and let FTX := σ(Xt : 0 ≤ t ≤ T ) be the sigma-ﬁeld generated by the path X up to time
                                                                                 c where f0 is an
T . We write the conditional mean of Z given the path as Y := E[Z | FTX ] = f0 (X),
                                                                     
                                 c is shorthand for f0 (X
unknown path functional and f0 (X)                       ct )t∈[0,T ] . Equivalently,


                                          c + ε,
                                  Z = f0 (X)             E[ε | FTX ] = 0.                        (4)


The case Z ∈ FTX corresponds to the path-determined setting, where ε = 0.

                                            c ∈ RdK denote the vector collecting all (or a subset of
     For a ﬁxed truncation level K, let sK (X)
                                              c ≤K . The best linear approximation is then deﬁned
all) coordinates of the truncated signature S(X) T

by                                                                             
                                                                            2
                          L0K := arg     min E           c − sK (X)
                                                     f0 (X)      c ⊤ LK             .            (5)
                                       LK ∈RdK


The corresponding projection residual is ξK   0      0
                                                       c − sK (X)
                                          X (f ) := f (X)      c ⊤ L0K . Thus, the regression

model can be decomposed as


                                          c ⊤ L0K + ξ X (f0 ) + ε.
                                  Z = sK (X)                                                     (6)
                                                     K




                                                     7
This decomposition, motivated by the universal approximation theorem, separates the population
approximation problem from the ﬁnite-sample estimation problem. However, the traditional uni-
versal approximation theorem is qualitative: it guarantees approximation but does not quantify
          X (f ) decays as K increases.
how fast ξK   0

Remark . Related approximation rates can be derived from stochastic Taylor expansions by ﬁxing
K and considering the short-time regime T → 0; see Cuchiero et al. (2023). In contrast, we ﬁx T
and quantify the approximation error as K → ∞.



3 Signature Approximation of Path Functionals

3.1 A Motivating Example: Signature-Chaos Relation

The universal approximation theorem explains why signatures can approximate path functionals,
but it is not suﬃcient for statistical analysis by itself. For statistical learning, one needs to quantify
                                            X (f ) decays as the truncation level K increases. This
how the ﬁnite-level approximation residual ξK   0

section studies this approximation error in L2 .

   We begin with Brownian motion as a benchmark case. Since signature coordinates play the role
of monomials on path space, the Brownian setting gives the cleanest way to see what ﬁnite-level
signatures are doing. In this case, the Wiener–Itô chaos expansion decomposes a square-integrable
path functional into deterministic kernels, while time-augmented signature coordinates generate
polynomial approximations to these kernels.

                                                            bt = (t, Bt ). For k ≥ 1, let
   Let B = {Bt }0≤t≤T be a standard Brownian motion and let B
∆k (0, T ) := {0 < t1 < · · · < tk < T }. For any Y ∈ L2 (FTB ), it is well known that Y admits
                                      P∞
a Wiener–Itô chaos expansion Y =        k=0 Ik (hk ), where I0 (h0 ) = E[Y ], and, for k ≥ 1, hk ∈

L2 (∆k (0, T )) and
                                          Z
                            Ik (hk ) :=                   hk (t1 , . . . , tk ) dBt1 · · · dBtk .     (7)
                                              ∆k (0,T )

In Appendix A, we show that the level-K time-augmented Brownian signature approximates Y by
approximating each low-order chaos kernel hk with polynomials. Thus, the approximation error is
governed by the polynomial approximation error for the low-order kernels, which is controlled by
the regularity of the kernels {hk } through classical polynomial approximation theory.

   The Brownian case is useful as a transparent benchmark, but most observed paths in applica-


                                                               8
tions are not Brownian motion itself. They may exhibit drift, mean reversion, volatility structure,
or other dynamics. We therefore turn next to observable Itô diﬀusions and deﬁne a smooth class
of path functionals for which explicit signature approximation rates can be obtained.


3.2 Smooth Functionals of Itô Diﬀusions

Itô diﬀusions provide a ﬂexible and widely used model for observed continuous-time paths in physics,
economics, and ﬁnance (Aı̈t-Sahalia, 2002). We focus on a tractable class of path functionals gener-
ated by smooth coeﬃcient functions evaluated along the time-augmented diﬀusion path. Although
this class is narrower than the class of all continuous path functionals, it is broad enough to cover
many time-averaged and accumulated path-dependent quantities that arise in applications.

   Let X = {Xt }0≤t≤T be a d-dimensional Itô diﬀusion satisfying


                           dXt = b(t, Xt ) dt + σ(t, Xt ) dBt ,            X0 = x0 ,                  (8)


where B = {Bt }0≤t≤T is a q-dimensional standard Brownian motion. Let D := [0, T ] × Rd . We
assume that b : D → Rd and σ : D → Rd×q are globally Lipschitz and uniformly bounded, i.e.,
kb(t, x)k + kσ(t, x)kF ≤ R, (t, x) ∈ D, for some ﬁnite constant R.

                                 ct = (t, X ⊤ )⊤ . We write X
   Deﬁne the time-augmented path X                                      bta = Xta for a = 1, . . . , d.
                                                            bt0 = t and X
                                           t

We consider path functionals of the form

                                                d Z T
                                                X
                               Y = Fh (X) :=                                 bta ,
                                                              ha (t, Xt ) ◦ dX                        (9)
                                                a=0       0


                                                                                     b 0 = dt, and ◦dX
where h = (h0 , . . . , hd ) is a collection of deterministic coeﬃcient functions, ◦dX               ba =
                                                                                       t               t
                                                                               R 1
◦dXta for a = 1, . . . , d. The standard functional linear regression target 0 β(t)Xt dt is also a special
case of this.

   This formulation is closely related to the functional Itô calculus literature, which studies smooth
non-anticipative functionals of semimartingale paths through horizontal and vertical derivatives
(Cont and Fournié, 2010, 2013; Dupire, 2019). Our class is more concrete: the functional is built
from smooth coeﬃcient functions evaluated along the observed diﬀusion path. This structure is
restrictive enough to allow explicit signature approximation rates, while retaining the accumulated
and path-dependent quantities that are common in applications.


                                                      9
   Let γ ∈ N+ . We deﬁne the mixed smoothness norm

                    X
                    γ     X                                      X
                                                                 d X
                                                                   γ       X
         Hγ (h) =                 sup      ∂tℓ ∂xα h0 (t, x) +                     sup      ∂tℓ ∂xα ha (t, x) .   (10)
                    ℓ=0 |α|≤2γ+1 (t,x)∈D                         a=1 ℓ=0 |α|≤2γ+2 (t,x)∈D


Deﬁnition 2 Deﬁne the smooth diﬀusion-functional class Uγ,R as the collection of pairs (X, h) such
that: (i) X solves Equation 8 with globally Lipschitz and bounded coeﬃcients with sup {kb(t, x)k + kσ(t, x)kF } ≤
                                                                                                  (t,x)∈D
R; and (ii) h is smooth and satisﬁes Hγ (h) ≤ R.


Remark . The smoothness condition is anisotropic. The time direction requires γ derivatives, while
the state direction requires additional smoothness. The coeﬃcient of the time channel h0 requires
2γ +1 spatial derivatives, whereas each spatial channel ha , a ≥ 1, requires 2γ +2 spatial derivatives.
The additional spatial derivative for the spatial channels is used to control the Stratonovich–Itô
correction. We use the same R to bound the SDE coeﬃcients and the functional smoothness norm
for simplicity.


3.3 Signature Approximation Rate

Theorem 1 Suppose (X, h) ∈ Uγ,R , and let Y = Fh (X). Then, for every K ≥ 2,


                               E|ξK
                                  X
                                    (Y )|2 ≤ C Hγ (h)2 K −2γ = O(K −2γ ),                                         (11)


where C > 0 does not depend on K. Moreover,                  sup         X (F (X))|2  K −2γ .
                                                                      E|ξK   h
                                                        (X,h)∈Uγ,R


   Theorem 1 is the main approximation result of this section. It turns the qualitative signature
universal approximation theorem into a quantitative statement for a class of diﬀusion-driven path
functionals. Under γ-th order smoothness, the upper bound of the squared ﬁnite-level signature
bias is of order K −2γ , and this order is sharp over Uγ,R . Thus the truncation level K plays the same
role as a polynomial degree in classical nonparametric approximation: smoother functionals admit
faster approximation, while the dependence on K cannot be uniformly improved without imposing
stronger regularity.
                                                                               X (Y )|2 = O(K −Q )
   In summary, the result yields an approximation bound of the generic form E|ξK
for a positive exponent Q determined by the regularity of the target path functional. For the smooth
diﬀusion-functional class above, Q = 2γ. This polynomial-rate bound is the key population input


                                                        10
for the statistical analysis in the next section. When stronger regularity is available, Appendix A.4
shows that analytic coeﬃcient functions lead to exponential signature approximation rate O(ρ−2K )
for some ρ.



4 Statistical Theory for Path Regression via Signature

This section develops limit theory for three ﬁnite-level signature learning procedures: Signature-
OLS, Signature-LASSO, and Signature-Logistic. The approximation results in Section 3 provide
the population input for this analysis. Our goal is to show how the ﬁnite-level approximation
residual aﬀects statistical estimation. Throughout this section, we continue to work with the case
          c = Fh (X) for (X, h) ∈ Uγ,R .
where f0 (X)

      In all three frameworks, the key issue is the approximation-estimation tradeoﬀ induced by the
truncation level K, which is summarized in Table 1.

             Table 1: Approximation-estimation tradeoﬀ induced by the truncation level K.

              Truncation level              Estimation side                    Approximation side
                                                                          −Q
                     K↑                dK ↑, statistical error ↑        K    ↓, approximation error ↓
                     K↓                dK ↓, statistical error ↓        K −Q ↑, approximation error ↑




4.1 Signature-OLS: Path Regression Consistency

                                                                           c where X
We ﬁrst recall the signature OLS procedure. Suppose Y := E[Z | FTX ] = f0 (X),     c :=
 ct )t∈[0,T ] is the time-augmented path, and write ε := Z −f0 (X).
(X                                                              c For Signature-OLS, let sK (X)
                                                                                             c ∈
                        c ≤K , obtained by deleting exact linear redundancies. Deﬁne the best
RdK be a subvector of S(X) 0,T

linear coeﬃcient and its approximation residual by
                                                                                       
                                                                                    2
                               L0K := arg      min E            c − sK (X)
                                                            f0 (X)      c ⊤ LK              ,
                                             LK ∈RdK                                                           (12)
                                X
                               ξK              c − sK (X)
                                  (f0 ) := f0 (X)      c ⊤ L0K .


Then Z = sK (X)                                            c ⊤ L0K is the L2 -projection of f0 (X)
             c ⊤ L0K + ξ X (f0 ) + ε. By construction, sK (X)                                   c
                        K
                                                          c X (f0 )] = 0.
onto the level-K signature approximation space, and E[sK (X)ξ K

                                                                                                  c1 , . . . , X
      Suppose that {(Zi , Xi )}ni=1 are independent and identically distributed,1 and let Xn := σ(X            cn ).
  1
      This might be extended to blocks of strong mixing processes; see, for example, Lucchese et al. (2025).


                                                            11
Collect the responses, features, approximation residuals, and regression errors as


                   Z := (Z1 , . . . , Zn )⊤ ,                             c1 ), . . . , sK (X
                                                                S := (sK (X                 cn ))⊤ ,
                           X1
                   ξK := (ξK                  Xn
                              (f0 ), . . . , ξK  (f0 ))⊤ , ε := (ε1 , . . . , εn )⊤ ,                  (13)

                   Z = SL0K + ξK + ε.

                                                            b K = (S⊤ S)−1 S⊤ Z, and its prediction
Whenever S⊤ S is invertible, the Signature-OLS estimator is L
                     xt )t∈[0,T ] is fbK (b
               b := (b
at a ﬁxed path x                          x) = sK (b   bK .
                                                   x)⊤ L

Assumption 1 (i) We assume                  c K (X)
                              ΣK := E[sK (X)s       c ⊤ ] is positive deﬁnite for every K, and
   n                    o2 
          c ⊤ Σ−1 sK (X)
                      c                                                    X (f )}2 ] = O(K −Q ).
nE                            → 0. (ii) There exists Q > 0 such that E[{ξK
1
      sK (X)   K                                                               0

(iii) Conditional on Xn , the errors are independent, and almost surely, E[εi | Xn ] = 0, E[ε2i | Xn ] =
σ 2 > 0, and max E[|εi |4 | Xn ] ≤ Cε < ∞.
             1≤i≤n


Remark . Condition (i) ensures that the least-squares coeﬃcient is uniquely deﬁned for every
ﬁnite K. By contrast, the subsequent
                                  n LASSO theory does    not require the full Gram matrix to
                                                      o2 
be nonsingular. The condition n1 E sK (X)          c
                                       c ⊤ Σ−1 sK (X)      → 0 requires the sample size to be
                                            K

large enough to assure consistency. This rate condition also implies d2K /n → 0. The exponent Q
in condition (ii) reﬂects the smoothness of the target functional, while condition (iii) is standard in
regression analysis.

                                 b := (b
   For pointwise prediction, let x     xt )t∈[0,T ] be a deterministic time-augmented test path in the
                                                                 x)⊤ Σ−1
domain of f0 that has a well-deﬁned signature. We assume c ≤ sK (b          x) ≤ CdK for some
                                                                      K sK (b
                x (f )|2 = O(K −Q ). This condition is imposed because we restrict attention to the
c, C > 0, and |ξK   0

probability space of the sample and do not wish to treat the test path as random. If the test path is
drawn from the same distribution as the sample paths, these rate conditions hold with probability
approaching one.

                                    b be a test path satisfying the preceding conditions. Under
Theorem 2 Let K = K(n) → ∞, and let x
Assumption 1, the following statements hold.
                                                2                       
(i) If dK /K Q → 0, then fbK (b
                              x) − f0 (b
                                       x)           = OP       dK   dK
                                                                n + KQ       = oP (1).
                              √
                           n{fbK (b
                                  x)−f0 (b
                                         x)}   d
(ii) If n/K Q → 0, then {s (b ⊤ −1      x)}1/2
                                               −
                                               → N (0, σ 2 ).
                          K x) ΣK sK (b



Remark . Generally, Assumption 1 needs d2K /n → 0, which is relatively mild: it requires the sample
size n to be large enough relative to the number of parameters being estimated. This condition

                                                           12
ensures that the sample Gram matrix S⊤ S/n concentrates around its population counterpart ΣK
and remains invertible with high probability. The condition dK /K Q → 0 makes the approximation
contribution vanish, while the stronger condition n/K Q → 0 in part (ii) makes it negligible on the
standard-error scale.

                         c is chosen to be a retained signature vector. Speciﬁcally, if all time-
   We illustrate why sK (X)
augmented signature coordinates up to level K are included, then the dictionary dimension grows
exponentially, dK  (d + 1)K .            Under the polynomial approximation rate O(K −Q ), one has
dK /K Q → ∞ for every ﬁnite Q, so the consistency condition dK /K Q → 0 cannot hold. There
are two natural ways to address this dimensional limitation:
1. Analytic approximation. For analytic coeﬃcient functionals, Appendix A.4 gives an approxi-
mation error of O(ρ−2K ), where ρ is related to the analytic radius, and in the case ρ > d + 1,
                2                      
fbK (b
                            K    (d+1)K
              x) = OP (d+1)
     x) − f0 (b           n   +    ρ2K
                                          . Balancing the two terms gives the rate-optimal choice
K  2log n                                               log n
      log ρ . Since ρ is unknown, one may search K < 2 log(d+1) .

2. Signature selection. A more practical approach is to apply OLS to a post-selection subset of
signature coordinates. The Signature-LASSO procedure introduced below provides such a feature-
selection mechanism. This approach can reduce the retained dimension to dK  n, although an
explicit optimal choice of K(n) is more diﬃcult to derive because the selected feature dimension is
data-dependent.


4.2 Signature-LASSO: Sparse Recovery

In many applications, a path functional may depend only on a small subset of signature coordinates.
This motivates Signature-LASSO, which selects relevant terms from a large signature dictionary.
The following OU example illustrates how such sparsity may arise.

Example 1 Suppose Y satisﬁes the OU SDE dYt = −θYt dt + σ dBt . Then Yt admits a sparse rep-
resentation in terms of the signature of the time-augmented Brownian path. Let Xt = (Xt0 , Xt1 ) =
(t, Bt ). A third-order truncation yields

                                    Z t
                          −θt
              Yt = Y0 e         +  σe−θ(t−s) dBs
                                0
                                      Z t                 
                         −θt      −θt               θ 2 s2                                     (14)
                  ≈ Y0 e     + σe          1 + θs +          dBs
                                       0              2
                  = Y0 e−θt S(X)∅t + σe−θt S(X)1t + θσe−θt S(X)0,1  2
                                                               t + θ σe
                                                                        −θt
                                                                            S(X)t0,0,1 .


                                                     13
Thus, in this third-order approximation, only the signature coordinates indexed by ∅, 1, (0, 1), and
(0, 0, 1) enter the representation.


   The example suggests that the population representation may be sparse. Throughout this
subsection, sK can be the full truncated signature dictionary and need not coincide with the
retained vector used for Signature-OLS. But for each K, we suppose the population coeﬃcient
vector L0K ∈ RdK is sparse. Speciﬁcally, let A0 := supp(L0K ) and qK := |A0 |, where 1 ≤ qK  dK .
The Signature-LASSO estimator is deﬁned as
                                                                                                 
                                               1                              X
                                                                               dK                 
                        b K ∈ arg min
                        L                            kZ − SLk2 + λn                   wKj |Lj |         ,        (15)
                                      L∈RdK    2n                                                
                                                                                j=1

                                                                                                 p
where, if the j-th coordinate is indexed by the word Ij , we set kj := |Ij | and wKj := T kj /2 / kj !. By
Lemma A.3, wKj is the deterministic time-and-factorial factor in the uniform moment bound, with
  p
1/ kj ! reﬂecting factorial decay across signature levels. Let sK have coordinates sKj := sKj /wKj .
Since sKj = wKj sKj , the original and rescaled dictionaries span the same linear space.

   Deﬁne the (weighted) population Gram matrix and its active–inactive partition by
                                                                                                       
                                h                      i            (ΓK )A0 A0        (ΓK )   A0 Ac0
                                  c K (X)
                      ΓK := E sK (X)s  c⊤ =                                                            .       (16)
                                                                    (ΓK )   Ac0 A0    (ΓK )   Ac0 Ac0



Assumption 2 (i) The active block (ΓK )A0 A0 is positive deﬁnite for every K, and sup (ΓK )−1
                                                                                           A0 A0                      <
                                                                                                             K    ∞

∞, sup (ΓK )Ac0 A0 (ΓK )−1
                        A0 A0      < 1. (ii) For some Q > 0, E[{ξK  X (f )}2 ] = O(K −Q ). (iii) Con-
                                                                        0
     K                        ∞
ditional on Xn , the errors {εi }ni=1 are independent and satisfy, almost surely, E[εi | Xn ] = 0 and
E[exp(tεi ) | Xn ] ≤ exp(σ02 t2 /2) for every t ∈ R and i = 1, . . . , n, where σ0 > 0 is independent of n
and K.


Remark . Condition (i) combines a uniform inverse bound for the weighted active Gram matrix
with the classical irrepresentable condition, a standard suﬃcient condition for support recovery
(Zhao and Yu, 2006; Wainwright, 2009). It does not require the full Gram matrix to be nonsin-
gular. Condition (ii) connects the sparse population representation to the approximation theory
in Section 3, while condition (iii) provides the conditional sub-Gaussian error bound used in the
high-dimensional analysis.



                                                           14
                                 b be a deterministic time-augmented test path and we assume that
   For pointwise prediction, let x
       x)⊤ (ΣK )−1
sK,A0 (b        A0 A0 sK,A0 (b
                                             x (f )|2 = O(K −Q ).
                             x) = O(1) and |ξK   0


Theorem 3 Under the preceding i.i.d. sampling setup, let K = K(n) → ∞ and dK → ∞, and
suppose that Assumption 2 holds. For a suﬃciently large ﬁxed constant C > 0 depending only on
R and T , suppose that
                                      (r                   )
                                    log(edK ) {log(edK )}K
                         qK (CK)  K
                                             +               → 0,
                                        n           n
                                        (r                        )                                           (17)
                              √            log(edK ) {log(edK )}K
                         λn  qK (CK) K
                                                    +               ,
                                               n           n

where λn is chosen at the displayed order with a suﬃciently large ﬁxed leading constant. Then the
solution of Equation 15 is unique with probability approaching one, and the following statements
hold.
           b K ) ⊆ A0 } → 1.
(i) P{supp(L
                                                    nP                               o1/2         √
              b K,j − L0K,j | = OP (λn ), and
(ii) max wKj |L                                          dK       b
                                                         j=1 wKj (LK,j − L0K,j )
                                                              2                  2          = OP ( qK λn ).
    1≤j≤dK
                                          2                     
                    b, fbK (b
(iii) For test path x       x) − f0 (b
                                     x)       = OP qK λ2n + K −Q = oP (1).
                                                                       b K ) = sign(L0K )} → 1.
(iv) If min wKj |L0K,j | > Cβ λn for suﬃciently large Cβ , then P{sign(L
        j∈A0

                                              √
Remark . In contrast to the OLS condition dK / n → 0, the LASSO rate condition is driven by
the active-set size qK , with the ambient dimension entering only through log(edK ). In particular,
    √                 p                                                            √
qK / n ≤ qK (CK)K log(edK )/n → 0. At the stated penalty level, λn = o(1), qK λn = o(1).
The beta-min condition is imposed on the coeﬃcients in the rescaled coordinates. Notably, the
exponent Q does not enter the weighted estimation rates for L0K , so unlike the OLS case, a
polynomial approximation rate does not by itself preclude LASSO selection consistency even when
we include all truncated signature coordinates.


4.3 Signature-Logistic: Classiﬁcation Consistency

We now consider a binary response Z ∈ {0, 1} and suppose that


                                    c = Λ{f0 (X)},
                                              c                              1
                          P(Z = 1 | X)                          Λ(u) :=           .                           (18)
                                                                          1 + e−u




                                                      15
         c is the conditional log-odds. We use the same ﬁnite-dimensional setting and notation
Here f0 (X)
as in the Signature-OLS analysis. Conditional on Xn , the responses are independent and satisfy
                    ci )}. Whenever a ﬁnite minimizer exists, deﬁne the Signature-Logistic estimator
E[Zi | Xn ] = Λ{f0 (X
by
                    b K = arg min Ln (L),
                    L
                                L∈RdK
                                   n h        n
                                1 X                               o               i             (19)
                    Ln (L) :=                              ci )⊤ L − Zi sK (X
                                           log 1 + exp sK (X                ci )⊤ L .
                                n
                                    i=1


                            c K (X)
     Recall that ΣK = E[sK (X)s  c ⊤ ], and deﬁne the population logistic Hessian by

                            h            h                i            i
                                   c ⊤ L} 1 − Λ{sK (X)
                 HK (L) := E Λ{sK (X)               c ⊤ L} sK (X)s
                                                               c K (X)
                                                                    c⊤ .                         (20)

                                                             n                   o2 
                                                                  c ⊤ Σ−1 sK (X)
Assumption 3 (i) ΣK is positive deﬁnite for every K, and n1 E sK (X)           c       → 0. (ii)
                                                                        K
                                                    n                   o
                                                       −1/2        −1/2
The population Hessian satisﬁes       inf       λmin ΣK HK (L)ΣK          ≥ c for some r, c > 0.
                                           1/2
                                          ΣK (L−L0K ) ≤r
                                                      X (f )}2 ] = O(K −Q ).
(iii) The population approximation error satisﬁes E[{ξK   0


Remark . Condition (i) is the relative Gram condition used in the Signature-OLS analysis and
implies d2K /n → 0. Condition (ii) imposes local population curvature in the same Gram geometry
and is therefore invariant to the scale of the signature coordinates. As before, Q in condition (iii)
reﬂects the smoothness of f0 .

     For pointwise prediction, we use the same deterministic test-path setting as in the Signature-
                              b satisfying those conditions, deﬁne fbK (b
OLS analysis. For a test path x                                                       bK .
                                                                                  x)⊤ L
                                                                        x) := sK (b

                                    b satisfy the preceding test-path conditions. Suppose
Theorem 4 Let K = K(n) → ∞, and let x
that Assumption 3 holds and dK /K Q → 0. Then Ln admits a ﬁnite and unique minimizer with
probability approaching one, and
                                                            r       !
                             1/2 b                      dK
                            ΣK ( L K − L0K )   = OP         + K −Q/2 ,
                                                         n
                                                        √                                      (21)
                            b                      dK      dK
                                x) − f0 (b
                            fK (b        x) = OP   √  +         = oP (1).
                                                     n K Q/2

Remark . Since Λ is Lipschitz, the same rate holds for the conditional success probability.

                                                                                   X (f )|2 = O(K −Q )
     Overall, the three results in this section show how the approximation rate E|ξK   0


                                                       16
connects signature approximation with statistical learning. The same idea can also be extended to
other signature-based learning procedures, such as ridge regression and elastic-net regularization.



5 Simulation Study

This section veriﬁes the theory in controlled settings where the true target functional is known.
Across three designs, we examine population approximation, the approximation–estimation tradeoﬀ
that governs the choice of truncation level, and sparse recovery under Signature-LASSO. All imple-
mentation details, including the data-generating processes, tuning choices, and evaluation metrics,
are collected in Appendix C.1.


Population approximation.                                            The ﬁrst experiment constructs coeﬃcient functionals with prescribed
smoothness orders γ ∈ {1, 2} under Brownian motion and an OU diﬀusion. Figure 1 shows that
the projection error decreases as the signature depth K increases. The smoother target, indexed
by γ = 2, is approximated faster than the rougher target, indexed by γ = 1, in both benchmarks.
Overall, as the truncation order K increases, the approximation error converges to 0 quickly.

                                                   (a) Brownian path functional                                                                                (b) OU path functional
                                                                                                                                     −1.0

                              −1.5                                                                                                   −1.5
  log10 test projection MSE




                                                                                                         log10 test projection MSE




                              −2.0                                                                                                   −2.0

                              −2.5                                                                                                   −2.5

                              −3.0                                                                                                   −3.0

                              −3.5                                                                                                   −3.5


                              −4.0       γ=1                                                                                         −4.0       γ=1
                                         γ=2                                                                                                    γ=2
                              −4.5       theory K −2γ                                                                                −4.5       theory K −2γ


                                     2                  3        4        5      6      7   8   9                                           2                  3        4        5      6      7   8   9
                                                   full signature depth K (log scale)                                                                     full signature depth K (log scale)



Figure 1: Population signature approximation under Brownian motion (a) and OU diﬀusion (b).
Dashed lines show K −2γ reference rates.



OLS and logistic regression.                                          The second experiment uses the smooth Brownian functional from the
ﬁrst design as the latent signal. We generate a continuous response by adding Gaussian noise to the
functional value and a binary response by applying a logistic link to the same latent signal. We then


                                                                                                    17
ﬁt Signature-OLS and Signature-Logistic across a range of truncation depths. Figure 2 illustrates
the ﬁnite-sample approximation–estimation tradeoﬀ. Small truncation levels are stable but underﬁt,
whereas deeper signatures reduce approximation bias at the cost of estimating more coeﬃcients.
In the one-dimensional time-augmented case, the full nonconstant dictionary has dK = 2K+1 − 2
coordinates, so K = 8 already corresponds to 510 regressors. In both experiments, an intermediate
depth gives the best ﬁnite-sample balance.

                                         (a) OLS prediction                                                                         (b) Logistic excess error
                                                              K = 2, dK = 6                                          0.14
                     100
                                                              K = 4, dK = 30
                                                                                                                     0.12
                                                              K = 6, dK = 126




                                                                                       excess classification error
                                                              K = 8, dK = 510
                                                                                                                     0.10
   prediction RMSE




                                                                                                                     0.08


                                                                                                                     0.06
                     10−1

                                                                                                                     0.04


                                                                                                                     0.02


                                                                                                                     0.00
                            500   1000        2000            5000        10000                                             500   1000      2000            5000   10000
                                           sample size n                                                                                 sample size n



Figure 2: Finite-sample signature regression: OLS (a) and logistic regression (b). Shaded bands
are 95% Monte Carlo intervals.



Signature-LASSO.                         The third experiment is motivated by the sparse OU structure in Example 1.
We generate responses from an OU-driven integral target whose ﬁnite-level signature expansion is
concentrated on the OU-relevant family (1), (0, 1), (0, 0, 1), . . .. This design creates a setting in which
the full signature dictionary is large, but the relevant signal is carried by a small structured subset
of coordinates. Figure 3 reports prediction and selection performance. The test error decreases
with the sample size, and deeper signatures become useful once there is enough data to estimate
the enlarged dictionary. Precision for the OU-relevant family also improves with the sample size,
but selection becomes harder at larger K because the dictionary expands rapidly and higher-order
OU coordinates carry weaker signal. Thus the appropriate interpretation is recovery of a ﬁnite-level
OU-relevant family, rather than exact support recovery of an inﬁnite integral functional.




                                                                                  18
                               (a) Out-of-sample prediction error                                                                 (b) Support recovery
             101                                                                                           1.0
                                                                             K=3
                                                                             K=4
                                                                             K=5                           0.8
                                                                             K=6




                                                                                          Precision rate
             100
  Test MSE




                                                                                                           0.6



                                                                                                           0.4
                                                                                                                                                                      K=3
             10−1
                                                                                                                                                                      K=4
                                                                                                           0.2
                                                                                                                                                                      K=5
                                                                                                                                                                      K=6
                                                                                                           0.0
                    50   100       200            500       100
                                                                  0
                                                                      200
                                                                         0
                                                                              500
                                                                                 0                               50   100   200            500       100
                                                                                                                                                           0
                                                                                                                                                               200
                                                                                                                                                                  0
                                                                                                                                                                       500
                                                                                                                                                                          0

                                         Training sample size n                                                                   Training sample size n



Figure 3: Signature-LASSO under the OU target: prediction error (a) and selection precision rate
(b). Results are averaged over 100 independent replications.


6 Real Data Applications

This section illustrates the ﬁnite-level signature framework in three applications that match the
statistical regimes studied above: path regression, high-dimensional sparse regression, and binary
classiﬁcation. We apply the framework to forecasting foreign exchange realized volatility from intra-
day price paths, predicting battery end of life from short diagnostic pulse trajectories, and detecting
epileptic seizures from multichannel EEG windows. This section presents the empirical design and
the evidence needed to interpret the main ﬁndings; full data construction, implementation details,
and sensitivity analysis are reported in Appendix C.


6.1 Foreign Exchange Realized Volatility Forecasting

We ﬁrst apply signature regression to forecast next-day realized volatility in foreign exchange mar-
kets. We use one-minute mid-price series for 12 major U.S. dollar currency pairs from the HistData
                                                                                        P 2 1/2
database over 2013–2023. If rt,j is the j-th intraday log return on day t, then RVt = ( j rt,j ) ,
and the response is Zt+1 = log RVt+1 . Each currency-pair sample was split chronologically, with
the ﬁrst 80% for estimation and the last 20% for out-of-sample evaluation.

      For each day, we form a cumulative-return path and apply a time-augmented lead–lag trans-
formation, which preserves temporal order while encoding quadratic-variation information. We
compute its depth-3 signature and concatenate the signatures from the most recent 22 trading
days, producing 858 candidate features. Estimation then proceeded in two steps: a ﬁve-fold cross-
validated Signature-LASSO selected coordinates on the training sample, and Signature-OLS was


                                                                                     19
reﬁtted on the selected coordinates. This speciﬁcation was compared with a naive forecast, AR(1),
and four HAR-family models based on realized volatility, semivariance, and jump summaries. The
complete protocol and pair-level feature-selection results are reported in Appendix C.2.

                                              (a) Cross-pair normalized error                                                                (b) Pairwise gain over strongest baseline
                        1.7                                                                                            USDCAD
                                                                                                                       USDDKK
                        1.6
RMSE / Signature RMSE




                                                                                                                        USDEUR
                        1.5                                                                                            USDMXN
                                                                                                                       USDCHF
                        1.4
                                                                                                                        USDSEK
                        1.3                                                                                            USDHUF
                                                                                                                       USDNZD
                        1.2                                                                                             USDGBP
                                                                                                                        USDSGD
                        1.1
                                                                                                                       USDCZK
                        1.0                                                                                             USDPLN                                                average reduction 7.9%

                                                                                                                                 0.0   2.5   5.0     7.5    10.0    12.5    15.0    17.5    20.0
                                ive     (1)        RV        RS            -J        CJ                    LS
                              Na      AR        R-        R-          -  RV       R-                     -O
                                                        HA           R          HA                    re                                      RMSE reduction vs best non-Signature (%)
                                              HA                  HA                            atu
                                                                                             n
                                                                                          Sig




Figure 4: Relative root mean squared error (RMSE) performance across currency pairs. Panel (a)
reports each benchmark’s RMSE relative to Signature-OLS; the dashed line marks parity. Panel
(b) reports the percentage RMSE reduction of Signature-OLS relative to the best non-signature
baseline for each pair.


                         Figure 4 shows that Signature-OLS has lower RMSE than every competing benchmark for all
12 pairs and reduces RMSE by 7.9%, on average, relative to the best non-signature model. The
improvement is therefore not driven by one currency or one unusually weak comparator.

Table 2: Cross-pair summary of out-of-sample FX forecasting performance. RMSE and MAE
denote root mean squared error and mean absolute error for log realized volatility; Roos  2   denotes
                     2
the out-of-sample R ; and QLIKE denotes quasi-likelihood loss on the variance scale. Entries are
averages across the 12 currency pairs, and the last four columns count pairwise wins; arrows indicate
the preferred direction.

                                                                          Cross-pair average                                                       Number of pairwise wins
                Method                               RMSE ↓                MAE ↓                        2
                                                                                                       Roos ↑            QLIKE ↓             RMSE          MAE              2
                                                                                                                                                                           Roos          QLIKE
                Signature-OLS                            0.749                  0.565                          0.361         -9.375                 12             11         12                   7
                HAR-RS                                   0.820                  0.612                          0.237         -9.360                  0              0          0                   3
                HAR-RV-J                                 0.817                  0.617                          0.243         -9.352                  0              0          0                   0
                HAR-RV                                   0.827                  0.611                          0.224         -9.362                  0              1          0                   2
                HAR-CJ                                   0.830                  0.615                          0.218         -9.344                  0              0          0                   0
                AR(1)                                    0.891                  0.685                          0.106         -9.260                  0              0          0                   0
                Naive                                    1.076                  0.792                         -0.306         -8.891                  0              0          0                   0


                         The selected features, reported in Appendix C.2, are dominated by higher-order lead–lag terms
and display a multi-horizon pattern across recent trading days. This suggests that the gains reﬂect
both multi-horizon dependence and intraday temporal order and lead–lag interactions that scalar


                                                                                                                   20
volatility summaries discard.


6.2 Battery End-of-Life Prediction

We next study early prediction of battery end-of-life (EOL) from short diagnostic pulse paths
using the Argonne Cell Analysis, Modeling, and Prototyping lithium-ion dataset (Paulson et al.,
2022). Following Ibraheem et al. (2025), we retain the ﬁrst usable 120-second Hybrid Pulse Power
Characterization (HPPC) pulse from each cell and deﬁne EOL as the ﬁrst cycle at which discharge
capacity falls to 80% of its initial value. After preprocessing and chemistry ﬁltering, the sample
contained 241 cells: 166 for training and 75 for testing.

   For cell j, the path contained time, current, voltage, and the temporal derivatives of current
and voltage. The main depth-3 signature therefore had 155 non-constant coordinates. We compare
this representation with 21 handcrafted summaries computed from the same pulse and apply OLS,
ridge, and LASSO to both feature sets. Holding the learner ﬁxed across representations allowed
us to separate the value of the path representation from the eﬀect of regularization. Full feature
deﬁnitions, split diagnostics, and sensitivity analyses are reported in Appendix C.3.

   Table 3 reports the training and test performance of the six feature–estimator combinations. The
results reveal a clear tradeoﬀ between representation richness and estimation stability. Signature-
OLS achieves an almost perfect in-sample ﬁt, substantially outperforming Handcrafted-OLS and
showing that signature features capture detailed variation in the HPPC pulse path. However, its
poor test performance reveals severe overﬁtting, while Signature-Ridge substantially reduces this
instability but performs similarly to Handcrafted-Ridge. Among the six speciﬁcations, Signature-
LASSO achieves the best out-of-sample accuracy, with test MAE 188.9, test RMSE 331.9, and test
R2 = 0.529. Relative to Handcrafted-LASSO, it reduces test MAE by 39.1% and test RMSE by
27.7%. This pattern is consistent with the sparse-regression message in Section 4: the signature
dictionary can be highly informative, but regularization is essential for stable estimation when the
feature dimension is large relative to the sample size.

   Figure 5 complements Table 3 by plotting observed versus predicted EOL for the six linear
speciﬁcations. Each panel compares ﬁtted values against the 45◦ reference line, with training and
test observations shown separately. The ﬁgure highlights the main pattern in the table: Signature-
OLS ﬁts the training sample extremely well but does not generalize, whereas Signature-LASSO
gives the closest test-set predictions to the 45◦ line.

                                                   21
Table 3: Training and test performance of signature and handcrafted features. MAE and RMSE
denote mean absolute error and root mean squared error, both measured in cycles; R2 denotes the
coeﬃcient of determination.

          Feature set                                 Method                        Training set                                Test set
                                                                                                          2
                                                                        MAE              RMSE            R             MAE      RMSE            R2
                                                      OLS               14.4              29.5          0.997          616.9    917.8         -2.599
          Signature                                   Ridge             290.1            443.7          0.409          314.1    463.1          0.084
                                                      LASSO             121.3            210.0          0.868          188.9    331.9          0.529
                                                      OLS               219.1            303.8          0.723          358.4    638.1         -0.740
          Handcrafted                                 Ridge             354.7            545.6          0.107          316.2    464.2          0.079
                                                      LASSO             349.5            539.3          0.127          310.4    459.2          0.099


                                                  Linear Regression                              Ridge                              Lasso
              Predicted EOL (cycle)




                                      2000
Handcrafted




                                      1500

                                      1000

                                       500

                                        0
              Predicted EOL (cycle)




                                      2000
Signature




                                      1500

                                      1000

                                       500

                                        0
                                             0          1000           2000         0            1000           2000       0        1000           2000
                                                    True EOL (cycle)                       True EOL (cycle)                     True EOL (cycle)

                                                                              Chemistry
                                             Li1.2Ni0.3Mn0.6O2                  5Vspinel          NMC532               NMC811       Train
                                             Li1.35Ni0.33Mn0.67O2.35            HE5050            NMC622                            Test



                         Figure 5: Observed versus predicted battery EOL for the six main linear speciﬁcations.


          The contrast between Signature-OLS and Signature-LASSO is the substantive result: the pulse
path is informative, but the useful information is sparse relative to the full signature dictionary.
Sensitivity analyses in Appendix C.3 show that prediction improves through K = 3 and then
deteriorates as the dictionary expands, and that substantial predictive signal is already present
in the early part of the retained pulse. These diagnostics support the approximation–estimation
tradeoﬀ developed in Section 4, while the modest sample size cautions against interpreting the
selected coordinates as stable electrochemical mechanisms.


                                                                                            22
6.3 Epileptic Seizure Detection

We ﬁnally consider epileptic seizure detection from three-second multichannel EEG windows using
the CHB-MIT scalp EEG database (Shoeb and Guttag, 2010). A window was labeled positive if
it overlapped an annotated seizure interval. For each patient, we augment the EEG channels with
time and temporal derivatives and compute a depth-2 signature; depending on channel availability,
this produced 1,406–4,032 coordinates. We ﬁt a logistic regression classiﬁer (LR) with balanced
class weights and compare it with logistic regression and random forest (RF) based on line length,
nonlinear energy, and Shannon entropy features. The modeled cohort contained 22 subjects, and
seizure windows accounted for only 0.338% of all retained windows. We therefore use patient-speciﬁc
stratiﬁed 25%/75% train–test splits and averaged metrics across patients rather than pooling all
windows. The classiﬁcation threshold for Signature + LR was ﬁxed at 0.10 using the threshold
analysis in Appendix C.4. This threshold aﬀected only the conversion of ﬁtted probabilities to
labels; AUC remains threshold-free. Complete cohort construction, feature dimensions, metric
deﬁnitions, threshold sensitivity, and patient-level results are reported in Appendix C.4.

   Because the positive class is exceptionally rare, raw accuracy can be misleading: a classiﬁer can
attain high accuracy by predicting almost every window as non-seizure. We therefore emphasized
sensitivity and balanced accuracy, which give the seizure class meaningful weight, and use AUC
as a threshold-free ranking diagnostic. The literature rows in Table 4 provide context under their
reported 25% or 50% training rates; only the last three rows form a controlled comparison under
our common patient-speciﬁc 25% training protocol.

Table 4: Seizure detection performance under diﬀerent training rates (TR). ACC, B-ACC, SENS,
SPEC, and AUC denote accuracy, balanced accuracy, sensitivity, speciﬁcity, and area under the
receiver operating characteristic curve, respectively; LR and RF denote logistic regression and
random forest. Performance metrics are percentages. Literature rows use their reported protocols;
our rows report patient means with patient-level standard deviations in parentheses. Bold entries
identify the best result among our three implementations.

  Method                      TR                             Performance Metric
                                         ACC           B-ACC          SENS         SPEC          AUC
  Zabihi et al. (2016)        50%         94.7            92.0         89.1         94.8             –
  Selvakumari et al. (2019)   50%         95.6            96.1         95.7         96.6             –
  Zabihi et al. (2020)        25%         95.1            93.2         91.2         95.2          93.0
  Kiranyaz et al. (2014)      25%            –            91.9         89.0         94.7             –
  Handcrafted + LR            25%   88.2 (16.0)    89.4 (8.0)     90.8 (8.3)   88.1 (16.2)   95.9 (3.8)
  Handcrafted + RF            25%    99.7 (0.4)   82.1 (10.1)    64.4 (20.3)    99.8 (0.2)   96.8 (3.9)
  Signature + LR              25%    97.5 (2.6)    95.8 (4.0)     94.1 (7.6)    97.5 (2.6)   98.6 (1.9)




                                                  23
                        (a) Mean Balanced Accuracy Across Thresholds                                        (b) Cross-Subject Mean ROC Curves                                           (c) Subject-Wise Balanced Accuracy
                        100                                                                     1.0                                                                               100
                         95

                         90                                                                     0.8                                                                                90
Balanced accuracy (%)




                                                                                                                                                             Signature (LR) (%)
                                                                           True positive rate
                         85
                                                                                                0.6
                         80                                                                                                                                                        80

                         75
                                                                                                0.4
                         70                                                                                                                                                        70

                         65                                                                     0.2
                         60                                                                                                                                                        60
                                                                                                                                                                                               Signature wins in 22/22 subjects
                         55                                                                     0.0
                              0.0   0.1     0.2      0.3       0.4   0.5                              0.0       0.2      0.4      0.6       0.8        1.0                               60       70       80         90      100
                                          Decision threshold                                                          False positive rate                                                      Handcrafted (RF) (%)

                                                                           Handcrafted (LR)                            Handcrafted (RF)           Signature (LR)



Figure 6: Diagnostic results for seizure detection. Panel (a) reports patient-averaged balanced ac-
curacy across decision thresholds. Panel (b) reports cross-subject mean receiver operating charac-
teristic (ROC) curves with ±1 standard-deviation bands. Panel (c) compares subject-wise balanced
accuracy for the handcrafted random-forest classiﬁer and Signature + LR at threshold 0.10.


                        Among our implementations, Handcrafted + RF has the highest accuracy and speciﬁcity, but its
sensitivity is only 64.4, meaning that its apparently excellent accuracy is obtained by missing many
seizure windows. Signature + LR instead attains balanced accuracy 95.8, sensitivity 94.1, speciﬁcity
97.5, and AUC 98.6. It improves sensitivity over the random forest by 29.7 percentage points while
preserving high speciﬁcity. The external rows suggest that this performance is competitive with
published CHB-MIT results.

                        Figure 6 shows that the main conclusion is not an artifact of a single aggregate score. The
signature classiﬁer reaches its maximum balanced accuracy at the reported threshold 0.10 and
remains strong over a broader threshold range than the random forest. Its mean ROC curve is also
highest, and its balanced accuracy exceeds that of Handcrafted + RF for every modeled subject.
The patient-level result is important because cohort-level pooling would allow subjects with more
windows to dominate the comparison.


                        Across the three applications, the empirical ﬁndings are consistent with the theoretical mes-
sage of the paper. Truncated signatures provide rich ﬁnite-dimensional representations of path-
valued covariates, but their practical performance depends on matching the learning procedure to
the statistical regime. Signature-OLS is eﬀective when the selected feature dimension is stable;
Signature-LASSO is useful when the signature dictionary is rich, but the eﬀective representation is
sparse, and Signature-Logistic extends the same idea to binary-response decisions. These examples
suggest that the proposed framework can serve as a practical guide for applying signatures to path


                                                                                                                         24
regression problems.



7 Conclusion

This paper develops approximation and statistical theory for signature-based path regression. On
the approximation side, we establish L2 rates for truncated signatures. For Itô diﬀusions, we prove
a minimax-optimal rate of order K −2γ for a structured class of smooth coeﬃcient functionals.
Thus, the ﬁnite-level approximation error is explicitly governed by the regularity of the target path
functional. On the statistical side, we study three procedures built on truncated signature features:
Signature-OLS, Signature-LASSO, and Signature-Logistic. This extends the existing statistical
literature on signature regression (Fermanian, 2022; Guo et al., 2025) by explicitly carrying the
truncation residual through the estimation theory. Across three real-data applications, signatures
provide informative ﬁnite-dimensional representations of ordered path data and often improve upon
handcrafted feature representations.

   Several directions remain open. First, the approximation theory could be extended to more
general path functionals, including barriers, stopping rules, occupation times, and other nonsmooth
path-dependent quantities. Such objects arise naturally in simulation-based pricing and optimal
stopping (Longstaﬀ and Schwartz, 2001). Second, because the number of signature coordinates
grows quickly with the path dimension and truncation level, sharper theory is needed for structured,
selected, and sparsiﬁed signature dictionaries. Third, extending the statistical analysis to dependent
samples, alternative losses, adaptive feature selection, and other decision-oriented objectives would
further broaden the role of signatures in path-valued prediction and analytics. Related starting
points include weakly dependent functional data and high-dimensional generalized linear models
(Hörmann and Kokoszka, 2010; van de Geer, 2008).


Acknowledgements. The authors thank Terry Lyons, Rama Cont, Jan Obloj, and Zhuangyan Li
for their helpful comments. We are also grateful to the DataSig group and the Oxford Math-
ematical and Computational Finance group for organizing seminars where this paper was pre-
sented, and to all participants for their feedback. Blanka Horvath acknowledges ﬁnancial support
from UKRI1010: High order mathematical and computational infrastructure for streamed data
that enhance contemporary generative and large language models. Wen Su acknowledges ﬁnan-
cial support from the EPSRC Centre for Doctoral Training in Mathematics of Random Systems


                                                 25
(EP/S023925/1). Ruixun Zhang acknowledges ﬁnancial support from the National Natural Science
Foundation of China (72342004,12271013), the Scientiﬁc Research Innovation Capability Support
Project for Young Faculty (SRICSPYF-ZY2025170), and the National Key R&D Program of China
(2022YFA1007900).



References

T. G. Andersen, T. Bollerslev, F. X. Diebold, and P. Labys. The distribution of realized exchange
  rate volatility. J. Am. Stat. Assoc., 96(453):42–55, 2001. doi: 10.1198/016214501750332965.

T. G. Andersen, T. Bollerslev, F. X. Diebold, and P. Labys. Modeling and forecasting realized
  volatility. Econometrica, 71(2):579–625, 2003. doi: 10.1111/1468-0262.00418.

T. G. Andersen, T. Bollerslev, and F. X. Diebold. Roughing it up: Including jump components in
  the measurement, modeling, and forecasting of return volatility. Rev. Econ. Stat., 89(4):701–720,
  2007. doi: 10.1162/rest.89.4.701.

P. M. Attia, A. Grover, N. Jin, K. A. Severson, T. M. Markov, Y.-H. Liao, M. H. Chen, B. Cheong,
  N. Perkins, Z. Yang, P. K. Herring, M. Aykol, S. J. Harris, R. D. Braatz, S. Ermon, and W. C.
  Chueh. Closed-loop optimization of fast-charging protocols for batteries with machine learning.
  Nature, 578:397–402, 2020. doi: 10.1038/s41586-020-1994-5.

Y. Aı̈t-Sahalia. Maximum likelihood estimation of discretely sampled diﬀusions: a closedform
  approximation approach. Econometrica, 70(1):223–262, 2002. doi: 10.1111/1468-0262.00274.

O. E. Barndorﬀ-Nielsen and N. Shephard. Econometric analysis of realised volatility and its use in
  estimating stochastic volatility models. J. R. Stat. Soc. Ser. B Stat. Methodol., 64(2):253–280,
  2002. doi: 10.1111/1467-9868.00336.

O. E. Barndorﬀ-Nielsen and N. Shephard. Power and bipower variation with stochastic volatility
  and jumps. J. Financ. Econom., 2(1):1–37, 2004. doi: 10.1093/jjﬁnec/nbh001.

C. Bayer, L. Pelizzari, and J. Schoenmakers. Primal and dual optimal stopping with signatures.
  Finance Stochastics, 29:981–1014, 2025. doi: 10.1007/s00780-025-00570-8.

C. Bayer, G. dos Reis, B. Horvath, and H. Oberhauser, editors. Signature Methods in Finance: An



                                                26
  Introduction with Computational Applications. Springer Finance Lecture Notes. Springer, 2026.
  doi: 10.1007/978-3-031-97239-3.

E. Bayraktar, Q. Feng, and Z. Zhang.       Deep signature algorithm for multidimensional path-
  dependent options. SIAM J. Financial Math., 15(1):194–214, 2024. doi: 10.1137/23M1571563.

L. Beutel and H. H. Gonska. Quantitative inheritance properties for simultaneous approximation by
  tensor product operators. Numerical Algorithms, 33:83–92, 2003. doi: 10.1023/A:1025539316792.

H. Boedihardjo, X. Geng, T. Lyons, and D. Yang. The signature of a rough path: Uniqueness.
  Adv. Math., 293:720–737, 2016. doi: 10.1016/j.aim.2016.02.011.

H. Cardot, F. Ferraty, and P. Sarda. Functional linear model. Stat. Probab. Lett., 45(1):11–22,
  1999. doi: 10.1016/S0167-7152(99)00036-X.

K.-T. Chen. Integration of paths, geometric invariants and a generalized baker-hausdorﬀ formula.
  Ann. Math., 65(1):163–178, 1957. doi: 10.2307/1969671.

I. Chevyrev and A. Kormilitzin. A primer on the signature method in machine learning. In
  Signature Methods in Finance: An Introduction with Computational Applications, pages 3–64.
  Springer Nature Switzerland Cham, 2025.

I. Chevyrev and T. Lyons. Characteristic functions of measures on geometric rough paths. Ann.
  Probab., 44(6):4049–4082, 2016. doi: 10.1214/15-AOP1068.

I. Chevyrev and H. Oberhauser. Signature moments to characterize laws of stochastic processes.
  J. Mach. Learn. Res., 23(176):1–42, 2022. doi: 10.48550/arXiv.1810.10971.

R. Cont and D.-A. Fournié. Change of variable formulas for non-anticipative functionals on path
  space. J. Funct. Anal., 259(4):1043–1072, 2010. doi: 10.1016/j.jfa.2010.04.017.

R. Cont and D.-A. Fournié. Functional itô calculus and stochastic integral representation of mar-
  tingales. Ann. Probab., 41(1):109–133, 2013. doi: 10.1214/11-AOP721.

F. Corsi. A simple approximate long-memory model of realized volatility. J. Financ. Econom., 7
  (2):174–196, 2009. doi: 10.1093/jjﬁnec/nbp001.

C. Cuchiero, G. Gazzani, and S. Svaluto-Ferro. Signature-based models: Theory and calibration.
  SIAM J. Financial Math., 14(3):910–957, 2023. doi: 10.1137/22M1512338.

                                                27
J. Dauxois, A. Pousse, and Y. Romain. Asymptotic theory for the principal component analysis of
  a vector random function: Some applications to statistical inference. J. Multivar. Anal., 12(1):
  136–154, 1982. doi: 10.1016/0047-259X(82)90088-4.

B. Dupire. Functional itô calculus. Quant. Finance, 19(5):721–729, 2019. doi: 10.1080/14697688.
  2019.1575974.

A. Fermanian. Functional linear regression with truncated signatures. J. Multivar. Anal., 192:
  105031, 2022. doi: 10.1016/j.jmva.2022.105031.

P. K. Friz and N. B. Victoir. Multidimensional Stochastic Processes as Rough Paths: Theory and
  Applications. Cambridge University Press, 2010. doi: 10.1017/CBO9780511845079.

M. Fujita, N. Sugiura, and S. Kouketsu. Prediction of atmospheric proﬁles with machine learning
  using the signature method. Geophys. Res. Lett., 51(6), 2024. doi: 10.1029/2023GL106403.

X. Guo, B. Wang, R. Zhang, and C. Zhao. On consistency of signature using lasso. Oper. Res., 73
  (5):2530–2549, 2025. doi: 10.1287/opre.2024.1133.

P. Hall and J. L. Horowitz. Methodology and convergence rates for functional linear regression.
  Ann. Stat., 35(1):70–91, 2007. doi: 10.1214/009053606000000957.

B. Hambly and T. Lyons. Uniqueness for the signature of a path of bounded variation and the
  reduced path group. Ann. Math., 171(1):109–167, 2010. doi: 10.4007/annals.2010.171.109.

S. Hörmann and P. Kokoszka. Weakly dependent functional data. Ann. Stat., 38(3):1845–1884,
  2010. doi: 10.1214/09-AOS768.

R. Ibraheem, P. Dechent, and G. dos Reis. Path signature-based life prognostics of li-ion battery
  using pulse test data. Appl. Energy, 378:124820, 2025. doi: 10.1016/j.apenergy.2024.124820.

P. Kidger, P. Bonnier, I. Perez Arribas, C. Salvi, and T. Lyons. Deep signature transforms. In
  Advances in Neural Information Processing Systems, volume 32, pages 3099–3109, 2019.

F. J. Király and H. Oberhauser. Kernels for sequentially ordered data. J. Mach. Learn. Res., 20
  (31):1–45, 2019. doi: 10.5555/3322706.3361972.

S. Kiranyaz, T. Ince, M. Zabihi, and D. Ince. Automated patient-speciﬁc classiﬁcation of long-term
  electroencephalography. J. Biomed. Inform., 49:16–31, 2014. doi: 10.1016/j.jbi.2014.02.005.

                                               28
D. Levin, T. Lyons, and H. Ni. Learning from the past, predicting the statistics for the future,
  learning an evolving system. arXiv preprint arXiv:1309.0260, 2013. doi: 10.48550/arXiv.1309.
  0260.

F. A. Longstaﬀ and E. S. Schwartz. Valuing american options by simulation: A simple least-squares
  approach. The Review of Financial Studies, 14(1):113–147, 2001. doi: 10.1093/rfs/14.1.113.

L. Lucchese, M. S. Pakkanen, and A. E. D. Veraart. Learning with expected signatures: Theory
  and applications. In Proceedings of the 42nd International Conference on Machine Learning,
  pages 40995–41055, 2025.

T. Lyons, S. Nejad, and I. Perez Arribas. Non-parametric pricing and hedging of exotic derivatives.
  Appl. Math. Finance, 27(6):457–494, 2020. doi: 10.1080/1350486X.2021.1891555.

T. J. Lyons. Diﬀerential equations driven by rough signals. Rev. Mat. Iberoam., 14(2):215–310,
  1998. doi: 10.4171/RMI/240.

J. Morrill, C. Salvi, P. Kidger, and J. Foster. Neural rough diﬀerential equations for long time series.
  In Proceedings of the 38th International Conference on Machine Learning, pages 7829–7838, 2021.
  doi: 10.48550/arXiv.2009.08295.

A. J. Patton. Volatility forecast comparison using imperfect volatility proxies. J. Econom., 160(1):
  246–256, 2011. doi: 10.1016/j.jeconom.2010.03.034.

A. J. Patton and K. Sheppard. Good volatility, bad volatility: Signed jumps and the persistence
  of volatility. Rev. Econ. Stat., 97(3):683–697, 2015. doi: 10.1162/REST a 00503.

N. H. Paulson, J. Kubal, L. Ward, S. Saxena, W. Lu, and S. J. Babinec. Feature engineering for
  machine learning enabled early prediction of battery lifetime. J. Power Sources, 527:231127,
  2022. doi: 10.1016/j.jpowsour.2022.231127.

J. O. Ramsay and B. W. Silverman. Functional Data Analysis. Springer Series in Statistics.
  Springer, New York, 2 edition, 2005. doi: 10.1007/b98888.

Y.-F. Ren. On the Burkholder–Davis–Gundy inequalities for continuous martingales. Statistics &
  Probability Letters, 78(17):3034–3039, 2008.




                                                  29
R. S. Selvakumari, M. Mahalakshmi, and P. Prashalee. Patient-Speciﬁc Seizure Detection Method
  using Hybrid Classiﬁer with Optimized Electrodes. J. Medical Syst., 43(5):121, 2019. doi: 10.
  1007/s10916-019-1234-4.

K. A. Severson, P. M. Attia, N. Jin, N. Perkins, B. Jiang, Z. Yang, M. H. Chen, M. Aykol, P. K.
  Herring, D. Fraggedakis, M. Z. Bazant, S. J. Harris, W. C. Chueh, and R. D. Braatz. Data-driven
  prediction of battery cycle life before capacity degradation. Nat. Energy, 4(5):383–391, 2019. doi:
  10.1038/s41560-019-0356-8.

A. H. Shoeb and J. V. Guttag. Application of machine learning to epileptic seizure detection. In
  Proceedings of the 27th International Conference on Machine Learning, pages 975–982, 2010. doi:
  10.5555/3104322.3104446.

S. A. van de Geer. High-dimensional generalized linear models and the lasso. Ann. Stat., 36(2):
  614–645, 2008. doi: 10.1214/009053607000000929.

M. J. Wainwright. Sharp thresholds for high-dimensional and noisy sparsity recovery using ℓ1 -
  constrained quadratic programming. IEEE Transactions on Information Theory, 55(5):2183–
  2202, 2009. doi: 10.1109/TIT.2009.2016018.

H. Wang and L. Zhang. Analysis of multivariate Gegenbauer approximation in the hypercube. Adv.
  Comput. Math., 46:53, 2020. doi: 10.1007/s10444-020-09792-0.

M. Zabihi, S. Kiranyaz, A. B. Rad, A. K. Katsaggelos, M. Gabbouj, and T. Ince. Analysis of High-
  Dimensional Phase Space via Poincaré Section for Patient-Speciﬁc Seizure Detection. IEEE
  Trans. Neural Syst. Rehabil. Eng., 24(3):386–398, 2016. doi: 10.1109/TNSRE.2015.2505238.

M. Zabihi, S. Kiranyaz, V. Jäntti, T. Lipping, and M. Gabbouj. Patient-speciﬁc seizure detection
  using nonlinear dynamics and nullclines. IEEE J. Biomed. Health Inform., 24(2):543–555, 2020.
  doi: 10.1109/JBHI.2019.2906400.

H. Zhang and S. X. Chen. Concentration inequalities for statistical inference. Commun. Math.
  Res., 37(1):1–85, 2021. doi: 10.4208/cmr.2020-0041.

P. Zhao and B. Yu. On model selection consistency of lasso. J. Mach. Learn. Res., 7:2541–2563,
  2006. doi: 10.5555/1248547.1248637.




                                                 30
                            Supplementary Appendices



Appendix Contents

A Theoretical Details for Section 3                                                                A-1

   A.1 Technical Lemmas . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . A-2

   A.2 Signature-Chaos Relation and Brownian Signature Approximation Rate . . . . . . . A-3

   A.3 Proof of Theorem 1 . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . A-6

   A.4 Exponential Rates for Analytic Coeﬃcient Functionals . . . . . . . . . . . . . . . . . A-11


B Theoretical Details for Section 4                                                              A-18

   B.1 Technical Lemmas . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . A-18

   B.2 Proof of Theorem 2 . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . A-22

   B.3 Proof of Theorem 3 . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . A-24

   B.4 Proof of Theorem 4 . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . A-29


C Additional Experimental Details                                                                A-32

   C.1 Simulation Details . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . A-32

   C.2 Foreign Exchange Case Study . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . A-35

   C.3 Battery End-of-Life Case Study . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . A-40

   C.4 Seizure Detection Case Study . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . A-43



A Theoretical Details for Section 3

This appendix proves the approximation results in Section 3. We use SK (X) to be the space
                                  c up to order K.
spanned by the signature terms of X




                                                 A-1
A.1 Technical Lemmas

We ﬁrst record the ﬁnite-level equivalence between Itô and Stratonovich Brownian signature spans.
The point is that, for Brownian motion, converting between Itô and Stratonovich iterated integrals
only introduces lower-level correction terms. Hence the two ﬁnite collections of coordinates carry
the same linear information at any ﬁxed truncation level.

Lemma A.1 Let B = {Bt }0≤t≤T be a d-dimensional standard Brownian motion and let B        bt =
                                  n                       o      n                        o
                                     b I,Str : 0 ≤ |I| ≤ K = span S(B)
(t, Bt⊤ )⊤ . For every K ≥ 0, span S(B)                             b I,Itô : 0 ≤ |I| ≤ K .
                                        T                              T


Proof . We work on the alphabet {0, 1, . . . , d}, where the 0 denotes the time coordinate and the
letters 1, . . . , d denote the Brownian coordinates. For a word I = (i1 , . . . , iℓ ), the correspond-
                                                                              b i1 , . . . , dB
ing iterated integral is formed by integrating successively with respect to d B               b iℓ . The

Itô–Stratonovich correction formula converts each Stratonovich diﬀerential into an Itô diﬀerential
plus quadratic-variation corrections. When this conversion is applied repeatedly inside an iter-
ated integral, each correction replaces two adjacent Brownian diﬀerentials by a quadratic-variation
diﬀerential.

   For the time-augmented Brownian path, the only non-zero quadratic covariations are


                                  ba, B
                                d[B   b b ]t = 1{a = b, 1 ≤ a ≤ d} dt,                            (A.1)


        b0, B
while d[B   b a ]t = 0 for all 0 ≤ a ≤ d. Therefore, each non-zero correction term can only arise

from a pair of identical Brownian letters, and the correction replaces this pair by a single time
diﬀerential. In particular, every correction term has strictly smaller word length than the original
word.

   Consequently, repeated application of the Itô–Stratonovich correction formula gives a triangular
relation between the two coordinate systems. More precisely, for every word I with |I| ≤ K,

                                                         X
                               b I,Str = S(B)
                             S(B)          b I,Itô +                    b J,Itô ,
                                                                  cI,J S(B)                       (A.2)
                                  T           T                             T
                                                        |J|<|I|


where the coeﬃcients cI,J are deterministic. The leading term is the Itô iterated integral with the
same word I, and all remaining terms have strictly smaller length.

   Now order all words with |I| ≤ K by nondecreasing length, and choose any ﬁxed order inside


                                                  A-2
each level. With respect to this ordered list of coordinates, Equation A.2 shows that the linear map
from the level-≤ K Itô signature coordinates to the level-≤ K Stratonovich signature coordinates
is represented by a deterministic lower-triangular matrix whose diagonal entries are equal to one.
Such a matrix is invertible. Hence every level-≤ K Stratonovich coordinate is a linear combination
of level-≤ K Itô coordinates and, conversely, every level-≤ K Itô coordinate is a linear combination
of level-≤ K Stratonovich coordinates. Thus the two families of coordinates span the same ﬁnite-
dimensional linear space.                                                                                                                □


A.2 Signature-Chaos Relation and Brownian Signature Approximation Rate

We now establish the full signature-chaos relation and the error rate of using Brownian signature
to approximate Brownian functional. We state the results in the multidimensional version. Let
B = {Bt }0≤t≤T , with Bt = (Bt1 , . . . , Btd )⊤ , be a standard d-dimensional Brownian motion. The
main diﬀerence from the one-dimensional case is that a k-th chaos kernel now has dk component
functions, one for each ordered sequence of Brownian component labels.
                                                                                                          P∞
   For any Y ∈ L2 (FTB ), write its Wiener–Itô chaos expansion as Y =                                        k=0 Ik (hk ), where I0 (h0 ) =

E[Y ], and for k ≥ 1,
                                                                                                          k
                                  hk = (hik1 ,...,ik )1≤i1 ,...,ik ≤d ∈ L2 (∆k (0, T ); Rd )                                          (A.3)
                         P            R              i1 ,...,ik
where Ik (hk ) :=                         ∆k (0,T ) hk          (t1 , . . . , tk ) dBti11 · · · dBtikk . The corresponding norm is
                    1≤i1 ,...,ik ≤d

                                                                     X
                               khk k2L2 (∆ (0,T );Rdk ) :=                        khik1 ,...,ik k2L2 (∆k (0,T )) .                    (A.4)
                                               k
                                                                1≤i1 ,...,ik ≤d


In the multidimensional case, the k-th chaos space is

                                      n                               k
                                                                        o
                                 Ck := Ik (h) : h ∈ L2 (∆k (0, T ); Rd ) , k ≥ 1.                                                     (A.5)


   The following lemma shows that signature space is a polynomial subspace of the chaos space.
                          k
Here Pr (∆k (0, T ); Rd ) denotes the space of vector-valued polynomial kernels whose components
have total degree at most r. And for k = 0, we use the convention that C0 = R, I0 (c) = c, and
Pr (∆0 (0, T ); R) = R.
                                                    n                                 k
                                                                                        o
Lemma A.2 For every 0 ≤ k ≤ K, one has SK (B) ∩ Ck = Ik (p) : p ∈ PK−k (∆k (0, T ); Rd ) .



                                                                   A-3
Proof . By Lemma A.1, it is enough to work with the Itô signature. For k ≥ 1, ﬁx a word
I = (i1 , . . . , iℓ ) ∈ {0, 1, . . . , d}ℓ with ℓ ≤ K. Suppose that I contains exactly k nonzero letters,
denoted by j1 , . . . , jk ∈ {1, . . . , d} in their order of appearance. Let q0 , . . . , qk be the numbers of
zeros before the ﬁrst nonzero letter, between consecutive nonzero letters, and after the last nonzero
letter. Then q0 + · · · + qk = ℓ − k.

     After the k Brownian integration times are ﬁxed, the zero letters are integrated out over the
gaps between those times, exactly as in the one-dimensional proof. Therefore, the corresponding
Itô signature coordinate can be written as

                                                           Z
                                        b I,Itô =
                                      S(B)                                 pI (t1 , . . . , tk ) dBtj11 · · · dBtjkk ,          (A.6)
                                           T
                                                               ∆k (0,T )

                                 q
                                                           (tk −tk−1 )qk−1 (T −tk )qk
where pI (t1 , . . . , tk ) = q10 ! (t2 −t
                                t 0        1)
                                                q1
                                        q1 !         ···        qk−1 !        qk !    .         Thus this coordinate belongs to the k-
th chaos and has a vector-valued polynomial kernel whose only nonzero component is indexed by
(j1 , . . . , jk ), with total degree ℓ − k ≤ K − k.
                                                                               k
     Conversely, take any p ∈ PK−k (∆k (0, T ); Rd ). It is enough to consider one component and
one monomial, because the vector-valued polynomial space is spanned by such componentwise
monomials. Fix a component (j1 , . . . , jk ) and introduce the gap variables y0 = t1 , yr = tr+1 − tr for
1 ≤ r ≤ k − 1, and yk = T − tk . Every polynomial in (t1 , . . . , tk ) of degree at most K − k is a linear
combination of monomials y0q0 · · · ykqk with q0 + · · · + qk ≤ K − k. Such a monomial is generated, up
to a deterministic nonzero constant, by the word


                                          (0, . . . , 0, j1 , 0, . . . , 0, j2 , . . . , jk , 0, . . . , 0),                    (A.7)
                                           | {z }             | {z }                          | {z }
                                                 q0                   q1                              qk


whose length is at most K. Hence every vector-valued polynomial kernel of degree at most K − k
is generated by level-K time-augmented Brownian signature coordinates.

     Finally, if a ﬁnite linear combination of level-K signature coordinates lies in Ck , then all its
chaos components of orders diﬀerent from k vanish by the orthogonality of Wiener chaoses. Its
k-th chaos component is therefore generated by words with exactly k nonzero letters, and hence by
vector-valued polynomial kernels of degree at most K − k. This gives the result.                                                    □
                                                                                          B (Y ) :=
     By Lemma A.2 and the orthogonality of diﬀerent Wiener chaoses, the level-K residual ξK




                                                                             A-4
Y − ProjSK (B) Y satisﬁes

                                 X                                    X
                                                                      K
               E|ξK
                  B
                    (Y )|2 =           khk k2L2 (∆ (0,T );Rdk ) +               inf     khk − pk2L2 (∆ (0,T );Rdk ) .            (A.8)
                                                  k                           p∈PK−k                    k
                                k>K                                   k=0


   For k ≥ 1, deﬁne the normalized kernel
                                              
                                              
                                              khk k−1                        hk ,    if hk 6= 0,
                                     e k :=
                                     h                  L2 (∆k (0,T );Rdk )
                                                                                                                                 (A.9)
                                              
                                              0,                                     if hk = 0.

                                                                                           P∞
Theorem A.1 Let Y ∈ L2 (FTB ) admit the chaos expansion Y =                                   k=0 Ik (hk ).   Assume that there
exist constants m ∈ N+ , ϵ > 0, and γ > 1/2 such that, for k ≥ 1, khk k2 2                                                = O{(1 +
                                                                                                     L (∆k (0,T );Rdk )
                   e kk γ
k)−(m+1+ϵ) }, and kh                      = O(ak ), where the constants in vector-valued polynomial
                       H (∆k (0,T );Rdk )
                                                                        P
approximation on ∆k (0, T ) are absorbed into ak , and {ak }k≥1 satisﬁes k≥1 a2k (1+k)−(m+1+ϵ) < ∞.
Let AK := max1≤k≤K ak . Then

                                                                         
                               E|ξK
                                  B
                                    (Y )|2 = O K −2γ + (A2K + K)K −(m+1+ϵ) .                                                    (A.10)


Proof . By Equation A.8, it suﬃces to control the chaos tail and the polynomial approximation
error. The tail condition gives

                                 X                                              
                                       khk k2L2 (∆ (0,T );Rdk ) = O (K + 1)−(m+ϵ) .                                             (A.11)
                                                    k
                                 k>K


                                         e k , polynomial approximation on the simplex gives
Then, since hk = khk kL2 (∆ (0,T );Rdk ) h                                                                                inf    khk −
                                 k                                                                                      p∈PK−k
pk2 2                  ≤ Ckhk k2 2                a2 (K − k + 1)−2γ . Therefore,
  L (∆k (0,T );Rdk )            L (∆k (0,T );Rdk ) k


        X
        K                                                      X
                                                               K
                inf      khk − pk2L2 (∆ (0,T );Rdk ) ≤ C             (1 + k)−(m+1+ϵ) a2k (K − k + 1)−2γ .                       (A.12)
              p∈PK−k                     k
        k=0                                                    k=1


Splitting the last sum into 1 ≤ k ≤ K/2 and K/2 < k ≤ K, the ﬁrst part is O(K −2γ ) by the
summability assumption, while the second part is O(A2K K −(m+1+ϵ) ) because γ > 1/2. Combining
these estimates with Equation A.11 gives Equation A.10.                                                                             □




                                                                A-5
A.3 Proof of Theorem 1

Proof . We split the proof into ﬁve steps. The ﬁrst step localizes the diﬀusion path and constructs
polynomial approximations on a compact set. The second step shows that the resulting polynomial
coeﬃcient functional is a ﬁnite-level signature functional. The third step controls the error on the
localization event. The fourth step controls the tail event using the boundedness of the diﬀusion
coeﬃcients. The last step veriﬁes the sharpness claim by reducing to the Brownian benchmark.

Step 1: localization and polynomial approximation. Choose a constant β such that 12 < β <
      γ                                  γ     γ+1
1 − 2γ+1 . Such a β exists because 1 − 2γ+1 = 2γ+1 > 12 . Let


                      mK := K β ,   RT := sup kXt k∞ ,                AK := {RT ≤ mK }.        (A.13)
                                              0≤t≤T


We ﬁrst consider K suﬃciently large that mK ≥ kx0 k∞ ; the ﬁnitely many remaining values are
handled at the end.

   On the localization event AK , the path stays in DK := [0, T ] × [−mK , mK ]d . We ﬁrst note that
the boundedness of b and σ gives a sub-Gaussian tail bound for RT . Indeed,

                                       Z t                    Z t
                          X t = x0 +         b(u, Xu ) du +           σ(u, Xu ) dBu .          (A.14)
                                        0                         0


Since b is uniformly bounded,

                                                            Z t
                         RT ≤ kx0 k∞ + RT + sup                   σ(u, Xu ) dBu           .    (A.15)
                                                  0≤t≤T       0                       ∞


For each coordinate of the martingale term, the quadratic variation is bounded by R2 T . The
exponential martingale inequality and a union bound imply that there exist constants C, c > 0 such
that
                           P(AcK ) = P(RT > mK ) ≤ Ce−cmK = Ce−cK .
                                                                      2          2β
                                                                                               (A.16)

The same tail bound implies the moment estimate ERTp ≤ C p pp/2 , for p ≥ 1.

   We now approximate h0 , . . . , hd on the compact rectangle DK . Rescale this rectangle to [0, 1] ×
[−1, 1]d by setting feK (u, y) := f (T u, mK y). The standard Jackson approximation theorem (Beutel
and Gonska, 2003) on the ﬁxed rectangle gives polynomial approximants in terms of the derivatives
of feK . Time derivatives only produce powers of T , while spatial derivatives of order r produce the


                                                      A-6
scaling factor mrK . For h0 , there exists a polynomial p0,K in (t, x), of total degree at most K − 1,
such that
                                             n                      o
                     kh0 − p0,K kL∞ (DK ) ≤ C K −γ + m2γ+1
                                                      K    K −(2γ+1) Hγ (h).                     (A.17)

For a = 1, . . . , d, applying the same approximation argument simultaneously to ha and its ﬁrst
spatial derivatives gives a polynomial pa,K , of total degree at most K − 1, such that


                           kha − pa,K kL∞ (DK ) + k∇x ha − ∇x pa,K kL∞ (DK )
                                     n                        o                                  (A.18)
                                ≤ C K −γ + m2γ+1 K  K −(2γ+1) Hγ (h).


                        2γ+1 −(2γ+1)
   By the choice of β, mK   K        = K −(2γ+1)(1−β) = o(K −γ ). Therefore, K −γ +m2γ+1
                                                                                    K    K −(2γ+1) ≤
CK −γ . Let δa,K := ha − pa,K for a = 0, · · · , d and deﬁne

                                            d Z T
                                            X
                                    YK :=                                b a.
                                                        pa,K (t, Xt ) ◦ dX                       (A.19)
                                                                           t
                                            a=0     0



Step 2: polynomial coeﬃcient functionals are ﬁnite-level signature functionals. We show that
YK ∈ SK (X). Fix a ∈ {0, . . . , d}. Since pa,K is a polynomial in (t, x) of total degree at most K − 1,
and since X0 = x0 is deterministic, each monomial in pa,K (t, Xt ) can be written as a polynomial
                                                               D            E
                                                 c Indeed, t = e0 , S(X)
in the ﬁrst-level preﬁx signature coordinates of X.                    c 0,t , and

                                           D            E
                                                   c 0,t ,
                                Xtb = xb0 + eb , S(X)              b = 1, . . . , d.             (A.20)


By the shuﬄe identity, every product of such preﬁx signature coordinates can be rewritten as a
                                                                                LK−1 d+1 ⊗r
linear functional of the preﬁx signature. Hence, writing T (K−1) (Rd+1 ) :=       r=0 (R    ) , there
                                                       D              E
                                                                 c 0,t . Using the recursive deﬁnition
exists qa,K ∈ T (K−1) (Rd+1 ) such that pa,K (t, Xt ) = qa,K , S(X)
of the Stratonovich signature,

                           Z T                         D                   E
                                 pa,K (t, Xt ) ◦ dX                   c 0,T .
                                                  b a = qa,K ⊗ ea , S(X)                         (A.21)
                                                    t
                            0


The tensor qa,K ⊗ ea has level at most K. Summing over a = 0, . . . , d, we obtain YK ∈ SK (X).
Therefore,
                          E|ξK
                             X
                               (Y )|2 =       inf       E|Y − Z|2 ≤ E|Y − YK |2 .                (A.22)
                                            Z∈SK (X)




                                                        A-7
Step 3: error on the localization event. We split

                                                              
               E|Y − YK |2 = E |Y − YK |2 1AK + E |Y − YK |2 1AcK =: IK
                                                                      loc    tail
                                                                          + IK    .                                      (A.23)


On AK , the path stays in the localization box. For the time channel, one has
                    "Z                             2
                                                                #
                             T
                E                δ0,K (t, Xt ) dt 1AK ≤ T 2 kδ0,K k2L∞ (DK ) ≤ CK −2γ Hγ (h)2 .                          (A.24)
                         0



   For a = 1, . . . , d, the Stratonovich–Itô conversion gives

                Z T                                        Z T
                                                                                     1
                       δa,K (t, Xt ) ◦ dXta =                    δa,K (t, Xt ) dXta + [δa,K (·, X· ), X a ]T .           (A.25)
                   0                                        0                        2

Let ηK := inf{t ∈ [0, T ] : kXt k∞ > mK } ∧ T , where inf ∅ = ∞. By continuity, the stopped path
remains in DK , and ηK = T on AK . After decomposing dXta into its drift and martingale parts,
Cauchy–Schwarz and Itô isometry give
                   "Z                                  2
                                                                     #           Z ηK
                            T                                                                                2
               E                δa,K (t, Xt ) dXta         1A K ≤ E                     δa,K (t, Xt ) dXta
                        0                                                         0                                      (A.26)
                                                                         ≤ Ckδa,K k2L∞ (DK ) ≤ CK −2γ Hγ (h)2 .


   For the quadratic covariation term, only spatial derivatives contribute:

                                                                Z TX
                                                                   d
                                               a
                                [δa,K (·, X· ), X ]T =                         ∂xr δa,K (t, Xt ) d[X r , X a ]t .        (A.27)
                                                                 0       r=1

                                   Pq
Moreover, d[X r , X a ]t =           ℓ=1 σrℓ (t, Xt )σaℓ (t, Xt ) dt. Therefore, by boundedness of σ, and Equa-

tion A.18, one has
                                    h                              i
                                   E |[δa,K (·, X· ), X a ]T |2 1AK ≤ CK −2γ Hγ (h)2 .                                   (A.28)

                                                                                                                    Pd        2
Combining Equation A.24, Equation A.25, Equation A.26, and Equation A.28, and using                                  a=0 za       ≤
       P
(d + 1) da=0 |za |2 , yields
                                                    loc
                                                   IK   ≤ CK −2γ Hγ (h)2 .                                               (A.29)

                                           tail . Since h , . . . , h and ∇ h , . . . , ∇ h are bounded
Step 4: tail error. It remains to control IK             0           d     x 1           x d

by Hγ (h), boundedness of b and σ, the Stratonovich–Itô conversion, and the Burkholder–Davis–


                                                                         A-8
                                   1/2
Gundy inequality give E|Y |4              ≤ CHγ (h)2 and

                                             1/2
                                                    P(AcK )1/2 ≤ CHγ (h)2 e−cK ,
                                                                              2β
                         E |Y |2 1AcK ≤ E|Y |4                                                     (A.30)


where the last inequality follows from Equation A.16.

   We now bound YK on the tail. From Equation A.17 and Equation A.18,


                        max kpa,K kL∞ (DK ) + max k∇x pa,K kL∞ (DK ) ≤ CHγ (h).                    (A.31)
                        0≤a≤d                       1≤a≤d


After rescaling the localization box to the unit box, a tensor-product Chebyshev expansion and the
fact that pa,K has total degree at most K − 1 imply that, for all (t, x) ∈ D,


                                max |pa,K (t, x)| + max k∇x pa,K (t, x)k
                               0≤a≤d                 1≤a≤d
                                                                                 K               (A.32)
                                                                   kxk∞
                                       ≤ CHγ (h) exp(CK log K) 1 +                     .
                                                                    mK

Using Equation A.32, boundedness of b, σ, the Stratonovich–Itô conversion, and BDG,

                                                                    "        #1/2
                                   
                                  4 1/2                                   RT 4K
                         E|YK |           ≤ CHγ (h) e2 CK log K
                                                                     E 1+           .              (A.33)
                                                                          mK

By log(1 + u) ≤ u and the sub-Gaussian moment estimate above,

                                         4K                                           
                              RT                              4KRT                K2
                         E 1+                   ≤ E exp                  ≤ C exp C 2           .   (A.34)
                              mK                               mK                 mK

               1/2                                  
                                                  K2
Thus E|YK |4          ≤ CHγ (h)2 exp CK log K + C m 2   . By Cauchy–Schwarz and Equation A.16,
                                                                K


                                                1/2
                          E |YK |2 1AcK ≤ E|YK |4      P(AcK )1/2
                                                                                                 (A.35)
                             ≤ CHγ (h)2 exp CK log K + CK 2−2β − cK 2β .


Since β > 1/2, the negative term K 2β dominates both K log K and K 2−2β . Therefore,

                                                    
                                        E |YK |2 1AcK = o(K −2γ )Hγ (h)2 .                         (A.36)


Using |Y − YK |2 ≤ 2|Y |2 + 2|YK |2 , the preceding bound for Y , and Equation A.36, we obtain IK
                                                                                                tail =




                                                          A-9
o(K −2γ )Hγ (h)2 . Combining this with the decomposition above, Equation A.22, and Equation A.29
         X (Y )|2 ≤ CK −2γ H (h)2 for all suﬃciently large K. Increasing C covers the ﬁnitely many
gives E|ξK                  γ

remaining values K ≥ 2.

Step 5: sharpness. It remains to establish the pair-class minimax lower bound. For the ﬁxed
                                                                                (m)
dimensions d, q ≥ 1, initial value x0 , and class radius R > 0, let e1                denote the ﬁrst canonical
basis vector of Rm , and take b = 0 and σ = Re1 (e1 )⊤ .
                                              (d) (q)                                           (d)
                                                                       Then Xt = x0 + Re1 Bt1 , and this
diﬀusion satisﬁes the coeﬃcient bound deﬁning Uγ,R .
                                                                                    P
   Consider h1 (t, x) = g(t) and ha = 0 for a 6= 1, where g ∈ C ∞ ([0, T ]) satisﬁes γℓ=0 kg (ℓ) kL∞ (0,T ) ≤
                                               P
R. Since g does not depend on x, Hγ (h) = γℓ=0 kg (ℓ) kL∞ (0,T ) ≤ R, so every such pair belongs to
                              RT
Uγ,R . Moreover, Fh (X) = R 0 g(t) dBt1 .

   The deterministic initial translation does not aﬀect the signature, the constant spatial coordi-
nates contribute no signature information, and every nonzero signature coordinate containing m
occurrences of the ﬁrst spatial letter is multiplied by Rm . Since R > 0, these rescalings do not
change the signature span, and hence SK (X) = SK (B 1 ). Therefore, applying Lemma A.2 to the
ﬁrst Wiener chaos gives

                           h           2i
                          E ξK
                             X
                               Fh (X)      = R2           inf        kg − pk2L2 (0,T ) .                (A.37)
                                                     p∈PK−1 (0,T )



   We next establish the required polynomial approximation lower bound within this smooth
subclass. Fix a nonzero function ψ ∈ Cc∞ (0, 1), extended by zero outside (0, 1), and set T :=
                                     Pγ
                                       ℓ=0 kψ kL∞ (R) . For j = 1, . . . , 2K, deﬁne ϕj,K (t) :=
min{T, 1}, δK := T /(2K), and Aγ :=            (ℓ)


RA−1        γ
     γ δK ψ((t − (j − 1)δK )/δK ). These functions have disjoint supports. Thus, for every ε =
                                                      P                         ∞
(ε1 , . . . , ε2K ) ∈ {−1, 1}2K , the function gε,K := 2K
                                                        j=1 εj ϕj,K belongs to C ([0, T ]) and satisﬁes
Pγ            (ℓ)
   ℓ=0 kgε,K kL∞ (0,T ) ≤ R.

   Let ΠK be the L2 (0, T )-orthogonal projection onto PK−1 (0, T ), and let bK := kϕj,K k2L2 (0,T ) =
                                        √
R2 A−2 2γ+1
    γ δK    kψk2L2 (0,1) . Since {ϕj,K / bK }2K
                                             j=1 is an orthonormal family and dim PK−1 (0, T ) = K,




                                                   A-10
Rademacher averaging and Bessel’s inequality yield
                                                                                                                     
                  sup                 inf         kg − pk2L2 (0,T ) ≥ Eε           inf         kgε,K − pk2L2 (0,T )
             g∈C ∞ ([0,T ])       p∈PK−1 (0,T )                                p∈PK−1 (0,T )
         Pγ
          ℓ=0 ∥g (ℓ) ∥ ∞
                      L (0,T ) ≤R

                                                                      X
                                                                      2K
                                                                                                                          (A.38)
                                                                  =         k(I − ΠK )ϕj,K k2L2 (0,T )
                                                                      j=1

                                                                  ≥ KbK = cγ,T R2 K −2γ ,

                                       2γ+1 −(2γ+1)
where cγ,T := A−2
               γ kψkL2 (0,1) T
                    2                      2        > 0.

    Combining Equation A.37 and Equation A.38 gives sup(X,h)∈Uγ,R E|ξK
                                                                     X (F (X))|2 ≥ c      4 −2γ .
                                                                         h           γ,T R K

Since the upper bound established above is uniform over Uγ,R , with a constant depending only on
                                                         X (F (X))|2  K −2γ . This proves Theorem 1.
T, d, q, x0 , γ, and R, it follows that sup(X,h)∈Uγ,R E|ξK   h

□


A.4 Exponential Rates for Analytic Coeﬃcient Functionals

We now give an analytic analogue of Theorem 1. Because the state space is unbounded, ordinary
analyticity on a ﬁxed complex neighborhood is not suﬃcient for a geometric rate on the expanding
localization boxes used below. We instead impose analyticity on a ﬁxed complex neighborhood of
the time interval and a controlled entire extension in the state variables. Throughout this subsec-
tion, T , d, q, and the deterministic initial value x0 are ﬁxed, and SK (X) denotes the span of all
time-augmented signature coordinates through level K. The result below concerns approximation
by this full space; it does not automatically apply to an arbitrary selected subset of signature
coordinates.

    For r > 1, let Er denote the ﬁlled closed Bernstein ellipse for [−1, 1] with parameter r, and
     [0,1]
let Er       := {(1 + z)/2 : z ∈ Er } be its aﬃne image corresponding to [0, 1]. For ρ0 > 1, τ > 0,
and R > 0, deﬁne Uρan
                    0 ,τ,R
                           as the collection of pairs (X, h) satisfying the following conditions. The
process X solves Equation 8 from x0 , where b and σ are globally Lipschitz and sup(t,x)∈D {kb(t, x)k+
kσ(t, x)kF } ≤ R. Each ha is real-valued on D, and ha (T ·, ·) admits a jointly holomorphic extension
                                                                  [0,1]
to Vρ0 × Cd , where Vρ0 is an open set containing Eρ0 , such that


                                       max        sup e−τ ∥ Im z∥1 |ha (T z0 , z)| ≤ R.                                   (A.39)
                                      0≤a≤d          [0,1]
                                              z0 ∈Eρ0
                                                z∈Cd


                                                              A-11
The condition is asymmetric in time and state because the time interval remains ﬁxed whereas the
state-space localization box expands with K. On the real state space it gives |ha (t, x)| ≤ R. Cauchy
estimates on smaller product neighborhoods show that, for every ﬁxed γ, Hγ (h) ≤ Cγ,ρ0 ,τ,d,T R;
hence, after changing the class bound by a ﬁxed multiplicative constant, these coeﬃcients also
satisfy the smoothness conditions above. The coeﬃcient condition is nondegenerate. For example, it
contains ha (t, x) = ga (t) sin(θa⊤ x) and ha (t, x) = ga (t) cos(θa⊤ x) when ga (T ·) is holomorphic on Vρ0 ,
is real-valued on [0, 1], and satisﬁes supz ∈E [0,1] |ga (T z0 )| ≤ R, while θa ∈ Rd and kθa k∞ ≤ τ . It also
                                               0   ρ0

contains ﬁnite real sine–cosine combinations whose time coeﬃcients satisfy the same holomorphy
and reality conditions, whose frequencies satisfy the same bound, and whose coeﬃcient-weighted
time envelopes sum to at most R.

Proposition A.1 Suppose (X, h) ∈ Uρan
                                    0 ,τ,R
                                           . Then, for every 1 < ρ < ρ0 , there exists a constant
Cρ > 0, depending only on T, d, q, x0 , R, ρ0 , ρ, and τ , such that, for every K ≥ 2,


                                    inf       E |Fh (X) − Z|2 ≤ Cρ R2 ρ−2K .                          (A.40)
                                 Z∈SK (X)



   The strict inequality ρ < ρ0 allows the subexponential factor generated by localization to be
absorbed into the geometric rate; no boundary rate at ρ = ρ0 is claimed.

Proof . Set ρ̄ := (ρ + ρ0 )/2 and β := 3/4, so that 1 < ρ < ρ̄ < ρ0 . Throughout the proof, C, c, and
similarly subscripted constants may change from line to line and may depend on T, d, q, x0 , R, ρ0 , ρ,
and τ , but not on K or on the particular pair (X, h) in the class. Set


       mK := 1 + kx0 k∞ + K β ,           XT∗ := sup kXt k∞ ,            AK := {XT∗ ≤ mK },
                                                    0≤t≤T
                                                                                                      (A.41)
       DK := [0, T ] × [−2mK , 2mK ] ,    d
                                                   ηK := inf {t ∈ [0, T ] : kXt k∞ ≥ 2mK } ∧ T,

                                                        Pq     Rt
where inf ∅ := ∞. For j = 1, . . . , d, let Mtj :=                               ℓ
                                                            ℓ=1 0 σjℓ (u, Xu ) dBu . Then



                      XT∗ ≤ kx0 k∞ + RT + max sup |Mtj |,                  hM j iT ≤ R2 T.            (A.42)
                                                   1≤j≤d 0≤t≤T


The exponential martingale inequality and a union bound therefore imply that there exist constants
C, c, C0 > 0 such that, for every r, s ≥ 0,


              P(XT∗ > r) ≤ C exp{−c(r − C0 )2+ },              E exp(sXT∗ ) ≤ C exp{C(s + s2 )}.      (A.43)


                                                        A-12
The second bound follows by integrating the ﬁrst tail bound. Since mK = O(K β ) and mK − C0 ≥
cK β for all suﬃciently large K, enlarging the prefactor to cover the remaining values gives


                                 P(AcK ) = P(XT∗ > mK ) ≤ C exp(−cK 2β ).                                          (A.44)


   For a = 0, . . . , d, deﬁne e
                               ha,K (u, y) := ha (T u, 2mK y) on D0 := [0, 1] × [−1, 1]d , using the same
                                                                              [0,1]
notation for its holomorphic extension. Since ρ̄ < ρ0 , Eρ̄                           ⊂ Vρ0 . Moreover, the maximum
absolute imaginary part on Eρ̄ is (ρ̄ − ρ̄−1 )/2, and hence k Im(2mK z)k1 ≤ d(ρ̄ − ρ̄−1 )mK for z ∈ Eρ̄d .
Therefore, Equation A.39 gives


                          max      sup |e
                                        ha,K (z0 , z)| ≤ R exp{dτ (ρ̄ − ρ̄−1 )mK }.                                (A.45)
                         0≤a≤d        [0,1]
                                 z0 ∈Eρ̄
                                   z∈Eρ̄d


                                                                         Qd
                              0 , let Tν (u, y) := Tν0 (2u − 1)
For ν = (ν0 , . . . , νd ) ∈ Nd+1                                             r=1 Tνr (yr ).   Writing ca,K,ν for the cor-
responding tensor-product Chebyshev coeﬃcient, the product-polyellipse coeﬃcient bound (Wang
and Zhang, 2020, Corollary 3.2) and Equation A.45 give

                                                   X
                              e
                              ha,K (u, y) =               ca,K,ν Tν (u, y),
                                                 ν∈Nd+1
                                                    0
                                                    X
                              pea,K (u, y) :=                 ca,K,ν Tν (u, y),                                    (A.46)
                                                  |ν|1 ≤K−1

                                  |ca,K,ν | ≤ CR exp{dτ (ρ̄ − ρ̄−1 )mK }ρ̄−|ν|1 .

The polynomial pea,K has total degree at most K − 1, rather than tensor degree at most K − 1.
                                                                                      
Since |Tj | ≤ 1 on [−1, 1] and the number of multi-indices satisfying |ν|1 = j is j+d
                                                                                   d , summing

Equation A.46 over j ≥ K bounds the value tail by CRK d exp{dτ (ρ̄ − ρ̄−1 )mK }ρ̄−K . Moreover,
kTν′ r kL∞ ([−1,1]) = νr2 , so the same coeﬃcient bound shows that each diﬀerentiated series converges
uniformly absolutely on D0 . Termwise diﬀerentiation is therefore valid and gives the same tail
bound with K d replaced by K d+2 for each state derivative. Consequently,


                     max ke
                          ha,K − pea,K kL∞ (D0 ) + max k∇y e
                                                           ha,K − ∇y pea,K kL∞ (D0 )
                    0≤a≤d                                  1≤a≤d
                                                                                                                   (A.47)
                                                              −1             −K             −K
                          ≤ CRK     d+2
                                            exp{dτ (ρ̄ − ρ̄        )mK }ρ̄        ≤ Cρ Rρ        .


The last inequality follows from mK = O(K β ), β < 1, and ρ < ρ̄, since the polynomial and


                                                          A-13
subexponential factors are absorbed by (ρ̄/ρ)K .

    Returning to the original variables, deﬁne
                                                                   
                                                         t   x
                              pa,K (t, x) := pea,K         ,            ,   a = 0, . . . , d.              (A.48)
                                                         T 2mK

The map (t, x) 7→ (t/T, x/(2mK )) sends DK onto D0 and does not increase total degree, so each pa,K
has total degree at most K −1. Moreover, for (t, x) ∈ DK , the chain rule gives ∇x (ha −pa,K )(t, x) =
(2mK )−1 (∇y e
             ha,K − ∇y pea,K )(t/T, x/(2mK )). Since mK ≥ 1, Equation A.47 therefore yields


                max kha − pa,K kL∞ (DK ) + max k∇x ha − ∇x pa,K kL∞ (DK ) ≤ Cρ Rρ−K .                      (A.49)
               0≤a≤d                              1≤a≤d



    Let δa,K := ha − pa,K and deﬁne

                                                 d Z T
                                                 X
                                         YK :=                                b a.
                                                             pa,K (t, Xt ) ◦ dX                            (A.50)
                                                                                t
                                                 a=0     0


Let e0 , . . . , ed denote the canonical basis of Rd+1 , and ﬁx a ∈ {0, . . . , d}. Since pa,K has total degree
at most K − 1 and X0 = x0 is deterministic, its evaluation at (t, Xt ) is a polynomial of degree at
                                                            c Indeed,
most K − 1 in the ﬁrst-level preﬁx signature coordinates of X.

                      D            E                        D            E
                              c 0,t ,
                   t = e0 , S(X)                                    c 0,t ,
                                                 Xtb = xb0 + eb , S(X)                 b = 1, . . . , d.   (A.51)


The deterministic constants xb0 are represented by the level-zero signature coordinate. By the
                                          L        d+1 )⊗r , there exists a deterministic tensor q
shuﬄe identity, writing T (K−1) (Rd+1 ) := K−1
                                            r=0 (R                                                 a,K ∈

T (K−1) (Rd+1 ) such that the recursive deﬁnition of the Stratonovich signature gives

                                                  D               E
                                                             c 0,t ,
                                   pa,K (t, Xt ) = qa,K , S(X)
                                   Z T                        D                   E                        (A.52)
                        and             pa,K (t, Xt ) ◦ dX                   c 0,T .
                                                         bta = qa,K ⊗ ea , S(X)
                                     0


Every homogeneous component of qa,K ⊗ ea has level at most K. The same identity covers a = 0,
            b 0 = dt and the appended letter is the time letter e0 . Summing over a = 0, . . . , d
for which ◦dX t

therefore shows that YK ∈ SK (X), and hence


                                  inf     E |Fh (X) − Z|2 ≤ E |Fh (X) − YK |2 .                            (A.53)
                               Z∈SK (X)


                                                             A-14
   We ﬁrst control the last error on AK . Since X has continuous paths, ηK is a stopping time,
(t, Xt ) ∈ DK for every t ≤ ηK , including the exit point, and AK ⊆ {ηK = T }. Therefore,

                                            
                       E |Fh (X) − YK |2 1AK
                                  Z ηK                             d Z ηK
                                                                   X
                                                                                                      2            (A.54)
                          ≤E             δ0,K (t, Xt ) dt +                    δa,K (t, Xt ) ◦ dXta       .
                                   0                               a=1    0


Joint holomorphy of ha and polynomiality of pa,K ensure that δa,K is suﬃciently smooth for the
Stratonovich–Itô conversion. For a = 1, . . . , d, it gives
               Z ηK                             Z ηK
                      δa,K (t, Xt ) ◦ dXta =             δa,K (t, Xt )ba (t, Xt ) dt
                0                                0
                                                     q Z ηK
                                                     X
                                                +                   δa,K (t, Xt )σaℓ (t, Xt ) dBtℓ                 (A.55)
                                                     ℓ=1       0
                                                         Z ηK X
                                                              d
                                                     1
                                                +                        ∂xr δa,K (t, Xt )(σσ ⊤ )ra (t, Xt ) dt.
                                                     2     0       r=1


Only spatial derivatives enter the quadratic-covariation correction, so no approximation bound for
the time derivative is required. Set εK := max0≤a≤d kδa,K kL∞ (DK ) + max1≤a≤d k∇x δa,K kL∞ (DK ) .
Then Equation A.49 gives εK ≤ Cρ Rρ−K . Cauchy–Schwarz for the ﬁnite-variation terms and Itô
isometry for the stopped martingale term yield

                                          
                      E |Fh (X) − YK |2 1AK ≤ C(1 + R2 + R4 )ε2K ≤ Cρ R2 ρ−2K .                                    (A.56)


Here the ﬁxed factor 1 + R2 + R4 is absorbed into Cρ , which is allowed to depend on the class
bound R. The stopping argument is needed because AK depends on the entire path and therefore
cannot be inserted directly into an Itô isometry.

   It remains to control the complement of AK . On the real state space, Equation A.39 gives
max0≤a≤d |ha (t, x)| ≤ R. Moreover, ﬁxing a state coordinate r and applying the Cauchy integral
formula on the unit circle in that coordinate gives max0≤a≤d |∂xr ha (t, x)| ≤ eτ R, uniformly over
(t, x) ∈ D. The Stratonovich–Itô decomposition in Equation A.55, now applied on [0, T ] to ha ,
together with boundedness of b and σ and the Burkholder–Davis–Gundy inequality, therefore
yields
                                              1/2                                2
                                 E|Fh (X)|4          ≤ C R + R2 + R3                   ≤ CR2 .                     (A.57)



                                                               A-15
In the last inequality, the ﬁxed factor (1 + R + R2 )2 is absorbed into C, which is allowed to depend
on the class bound R. Hence, by Cauchy–Schwarz and Equation A.44,

                                                           1/2
                                E |Fh (X)|2 1AcK ≤ E|Fh (X)|4     P(AcK )1/2
                                                                                                                        (A.58)
                                                                                                2 −2K
                                                             ≤ CR exp(−cK ) = o R ρ
                                                                   2               2β
                                                                                                            .


The last equality follows because β = 3/4, and hence K 2β = K 3/2 dominates K.

   To control YK , ﬁrst note from Equation A.49 and the real-axis bound on ha that max0≤a≤d kpa,K kL∞ (DK ) ≤
CR. After transforming the time coordinate by z0 = 2u − 1, the tensor-product Chebyshev coeﬃ-
cient formula therefore gives |ca,K,ν | ≤ 2d+1 ke
                                                pa,K kL∞ (D0 ) ≤ CR whenever |ν|1 ≤ K − 1. Moreover,
for every real y, |Tj (y)| ≤ (1 + 2|y|)j and |Tj′ (y)| ≤ j 2 (1 + 2|y|)j . Since #{ν ∈ Nd+1
                                                                                         0   : |ν|1 ≤
                         d+1 , while the chain rule contributes the factor (2m )−1 ν 2 ≤ K 2 to each
K − 1} = K+dd+1 ≤ CK                                                             K    r

spatial derivative, summing over the retained multi-indices yields, uniformly over t ∈ [0, T ] and
x ∈ Rd ,                                                                                                       K
                                                                                                       kxk∞
                    max |pa,K (t, x)| + max k∇x pa,K (t, x)k ≤ CRK                        d+3
                                                                                                    1+               .   (A.59)
                   0≤a≤d                       1≤a≤d                                                    mK

   Applying the Stratonovich–Itô conversion to Equation A.50 gives

                                    Z T                                d Z T
                                                                       X
                            YK =          p0,K (t, Xt ) dt +                     pa,K (t, Xt )ba (t, Xt ) dt
                                     0                                 a=1   0
                                         q Z T
                                                       ( d                                 )
                                         X              X
                                    +                          pa,K (t, Xt )σaℓ (t, Xt ) dBtℓ                            (A.60)
                                         ℓ=1       0     a=1
                                                       Z T
                                      1 X
                                               d
                                    +                        ∂xr pa,K (t, Xt )(σσ ⊤ )ra (t, Xt ) dt.
                                      2
                                          a,r=1 0


Consequently, Equation A.59, Cauchy–Schwarz for the ﬁnite-variation terms, and the Burkholder–
Davis–Gundy inequality imply

                                                                          (        )1/2
                       4 1/2                                                   XT∗ 4K
               E|YK |           ≤ CR (1 + R + R ) K
                                     2                       2 2   2d+6
                                                                           E 1+           ,
                                                                                mK
           (        )1/2              1/2
                 XT∗ 4K             4KXT∗                                                                                (A.61)
            E 1+          ≤ E exp
                 mK                  mK
                                                             
                                      K     K2
                          ≤ C exp C       + 2      ≤ C exp CK 2−2β .
                                      mK    mK



                                                                    A-16
Since the ﬁxed factor (1 + R + R2 )2 may be absorbed into the class constant, it follows that

                                                                            
                                                1/2
                                      E|YK |4         ≤ CR2 K 2d+6 exp CK 2−2β .              (A.62)


    Combining Equation A.62 with Equation A.44 and applying Cauchy–Schwarz gives

                                          1/2
                    E |YK |2 1AcK ≤ E|YK |4      P(AcK )1/2
                                                   n               o
                                  ≤ CR2 K 2d+6 exp CK 2−2β − cK 2β                            (A.63)
                                                   n              o           
                                  = CR2 K 2d+6 exp CK 1/2 − cK 3/2 = o R2 ρ−2K .


Indeed, after division by ρ−2K , the exponent acquires only the additional linear term 2K log ρ,
which is dominated by −cK 3/2 . Finally, using |u − v|2 ≤ 2|u|2 + 2|v|2 , together with Equation A.58
and Equation A.63, yields

                                                                         
        E |Fh (X) − YK |2 1AcK ≤ 2E |Fh (X)|2 1AcK + 2E |YK |2 1AcK = o R2 ρ−2K .             (A.64)


    Combining Equation A.53, Equation A.56, and Equation A.64, and enlarging Cρ if necessary,
there exists an integer K0 ≥ 2, depending only on the ﬁxed class parameters, such that, uniformly
over (X, h) ∈ Uρan
                 0 ,τ,R
                        ,


            inf     E |Fh (X) − Z|2 ≤ E |Fh (X) − YK |2
         Z∈SK (X)
                                                                                          (A.65)
                                         = E |Fh (X) − YK |2 1AK + E |Fh (X) − YK |2 1AcK

                                         ≤ Cρ R2 ρ−2K

for every K ≥ K0 .

    For the ﬁnitely many integers 2 ≤ K < K0 , since 0 ∈ SK (X), Equation A.57 gives

                                                                            1/2
                            inf    E |Fh (X) − Z|2 ≤ E|Fh (X)|2 ≤ E|Fh (X)|4
                        Z∈SK (X)
                                                                                              (A.66)
                                                                     2 2(K0 −1) −2K
                                                         ≤ CR ≤ CR ρ
                                                               2
                                                                              ρ       .

Increasing Cρ once more therefore proves Equation A.40 for every K ≥ 2.                            □




                                                           A-17
B Theoretical Details for Section 4

This appendix proves the statistical results in Section 4. Throughout the appendix, we maintain
the standing assumption that the underlying path is an Itô diﬀusion satisfying the conditions in
Section 3, and that the target variable Y is generated from the pair (X, h) ∈ Uγ,R .


B.1 Technical Lemmas

We ﬁrst prove several technical lemmas. The next two lemmas establish moment and sub-Weibull
tail bounds for individual signature coordinates. We ﬁrst introduce the ψκ -functional used to state
the tail result. Since the exponent appearing below may be smaller than one, we refer to it as a
sub-Weibull functional rather than an Orlicz norm. For κ > 0, deﬁne
                                                                    κ      
                                                                |Y |
                          kY kψκ := inf A > 0 : E exp                         ≤2 .            (A.67)
                                                                 A

A random variable Y is called sub-Weibull with tail parameter κ if kY kψκ < ∞; see (Zhang and
Chen, 2021, Section 6.1). Whenever 0 < kY kψκ < ∞, Markov’s inequality and Equation A.67 give
                                                             κ 
                                                        x
                         P(|Y | > x) ≤ 2 exp −                         ,      x > 0.          (A.68)
                                                      kY kψκ


   Before stating the lemma, we recall an Lp form of the Burkholder–Davis–Gundy inequality
for continuous martingales; see Ren (2008). For p ≥ 2, write kY kp = (E|Y |p )1/p . There exists a
universal constant CBDG > 0 such that, for every p ≥ 2, t ∈ [0, T ], and every Rq -valued predictable
process H for which the right-hand side is ﬁnite,

                         Z t                             Z t                 1/2
                                                  √
                               Hu⊤ dBu       ≤ CBDG p           kHu k22 du               .    (A.69)
                          0              p                 0
                                                                                     p


   We ﬁrst establish a weighted moment bound directly from the bounded-coeﬃcient diﬀusion
structure.

Lemma A.3 Let X satisfy Equation 8, and suppose that kb(t, x)k + kσ(t, x)kF ≤ R uniformly
                          n           √               o
in (t, x). Deﬁne Csig := 4 1 + (1 + R) T + CBDG R + R . Then, for every p ≥ 2, k ≥ 1,




                                                  A-18
I ∈ {0, . . . , d}k , and t ∈ [0, T ], we have

                                                                      √
                                          cI                     (Csig p)k tk/2
                                        S(X) 0,t               ≤      √         ,                      k = |I|.                         (A.70)
                                                             p          k!

                                     c J , with S ∅ ≡ 1. For p ≥ 2, deﬁne
Proof . For a word J, write StJ := S(X) 0,t      t



                          F0,p (t) := 1,                     Fk,p (t) :=             max         kStJ kp ,         k ≥ 1.               (A.71)
                                                                                  J∈{0,...,d}k


Let I = (i1 , . . . , ik ) and I ′ = (i1 , . . . , ik−1 ). The recursive deﬁnition of the Stratonovich signature
           Rt ′                                             R
gives StI = 0 SuI ◦ dX     buik . If ik = 0, then StI = t SuI ′ du. If ik = a ∈ {1, . . . , d}, the Stratonovich–Itô
                                                              0

conversion gives

                         Z t                                        q Z t
                                  ′
                                                                    X                ′                              1 h I′ ai
                 StI =         SuI ba (u, Xu ) du +                               SuI σaℓ (u, Xu ) dBuℓ +              S ,X     .       (A.72)
                          0                                               0                                         2         t
                                                                    ℓ=1

                                                                                                                                    ′
When k ≥ 2 and I ′ = (I ′′ , r) for some r ∈ {1, . . . , d}, the local martingale part of S I is generated
      ′′
by SuI σr· (u, Xu ). Therefore,

                                    h                i                  X
                                                                        q
                                        I′       a                 ′′
                                d S ,X                       = SuI            σrℓ (u, Xu )σaℓ (u, Xu ) du.                              (A.73)
                                                         u
                                                                        ℓ=1


The quadratic covariation is zero when I ′ = ∅ or the last letter of I ′ is the time channel.

    The coeﬃcient bound implies

                                                                                           X
                                                                                           q
                 |ba (t, x)| ≤ R,                kσa· (t, x)k2 ≤ R,                               σrℓ (t, x)σaℓ (t, x) ≤ R2 .           (A.74)
                                                                                           ℓ=1


Moreover, since p/2 ≥ 1, Minkowski’s inequality gives, for every progressively measurable scalar
process Z,
                          Z t                    1/2 2                  Z t
                                    |Zu | du 2
                                                                    =             |Zu |2 du
                                0                                             0                  p/2
                                                                p                                                                       (A.75)
                                                                        Z t                              Z t
                                                                    ≤             |Zu |2 p/2 du =                kZu k2p du.
                                                                          0                                  0

Consequently, Minkowski’s inequality and Equation A.69, together with an enlargement of max{1, R}




                                                                          A-19
to 1 + R, imply

                                    Z t                                  Z t                   1/2
                                                                    √
                Fk,p (t) ≤ (1 + R)   Fk−1,p (u) du + CBDG R p                              2
                                                                                Fk−1,p (u) du
                                   0                                        0
                                 Z                                                                     (A.76)
                              R2 t
                            +       Fk−2,p (u) du,
                               2 0

where the ﬁnal term is absent when k = 1. Then, set

                                                                 √
                                                            (Csig p)k tk/2
                         G0,p (t) := 1,         Gk,p (t) :=      √         ,       k ≥ 1.              (A.77)
                                                                   k!

The assertion is immediate at t = 0. Suppose inductively that Fj,p (u) ≤ Gj,p (u) for every j < k
and u ∈ [0, T ]. For t > 0, direct calculation gives

                           Z t                                 √
                                                             2 kt
                               Gk−1,p (u) du = Gk,p (t)            √ ,
                            0                           (k + 1)Csig p
                           Z t                1/2
                                           2            Gk,p (t)
                                 Gk−1,p (u) du       =       √ ,                                       (A.78)
                               0                        Csig p
                           Z t                                 r
                                                          2      k−1
                               Gk−2,p (u) du = Gk,p (t) 2            ,            k ≥ 2.
                            0                           Csig p    k

Substitution into Equation A.76 yields
                                          (            √                    r     )
                                               2(1 + R) kt   CBDG R   R2      k−1
                    Fk,p (t) ≤ Gk,p (t)                  √ +        + 2             ,                  (A.79)
                                              (k + 1)Csig p   Csig   Csig p    k

                                               √
where the ﬁnal term is zero when k = 1. Since 2 k/(k + 1) ≤ 1, p ≥ 2, and t ≤ T , the expression
in braces is bounded above by
                                        √
                                 (1 + R) T + CBDG R   R2  1  1
                                                    + 2 ≤ +    < 1.                                    (A.80)
                                         Csig        Csig 4 16

Induction therefore gives Fk,p (t) ≤ Gk,p (t) for every k ≥ 1, which proves Equation A.70.                 □

    The factorial moment bound yields a sub-Weibull bound for each signature coordinate.

                                                          √     n       √ o
Lemma A.4 Under the conditions of Lemma A.3, deﬁne Mψ := 4 e max 1, Csig T . Then, for
every k ≥ 1 and I ∈ {0, . . . , d}k ,


                                          c I − ES(X)
                                        S(X)       cI                   ≤ Mψk .                        (A.81)
                                             0,T      0,T
                                                                 ψ2/k


                                                       A-20
Consequently, for every x > 0,
                                                                            !2/k 
                                                                        x      
                     P       S(X)       c I > x ≤ 2 exp
                               c I − ES(X)                             −              .      (A.82)
                                  0,T      0,T
                                                                          Mψk   


Thus, every centered signature coordinate of word length k is sub-Weibull of order 2/k.


Proof . Fix k ≥ 1 and I ∈ {0, . . . , d}k , and write

                                                                    n       √ o
                              c I − ES(X)
                      ZI := S(X)       cI ,                 A := max 1, Csig T .             (A.83)
                                 0,T      0,T



For every integer m ≥ 1, the triangle inequality, Jensen’s inequality, and Equation A.70 give

                                              cI
                               kZI k2m ≤ 2 S(X)  0,T
                                                     2m
                                               √                                             (A.84)
                                         2(Csig 2m) T k/2
                                                     k
                                                            2Ak (2m)k/2
                                       ≤        √         ≤     √       .
                                                  k!              k!

Since 2m/k ≤ 2m, Lyapunov’s inequality yields

                                                         1/k          2m/k
                                 E|ZI |2m/k ≤ E|ZI |2m          = kZI k2m .                  (A.85)

            √
Using Mψ = 4 e A, monotone convergence and Equation A.84–Equation A.85 give
                                          ! 
                                      |Z | 2/k        X∞
                                                            E|ZI |2m/k
                                         I
                               E exp              = 1 +                ,                     (A.86)
                                      Mψk                  m!Mψ2m
                                                        m=1


and
                         E|ZI |2m/k    22m/k (2m)m       1  m m
                                    ≤                  ≤          ≤ 2−m .                    (A.87)
                          m!Mψ2m      m!(16e)m (k!)m/k   m! 2e

Here, the last two inequalities use 22m/k ≤ 4m , k! ≥ 1, and m! ≥ (m/e)m . It follows that
                                           ! 
                                       |Z | 2/k        X∞
                                                             2−m = 2.
                                          I
                                E exp              ≤ 1 +                                     (A.88)
                                       Mψk      
                                                         m=1


Therefore, the deﬁnition in Equation A.67 gives Equation A.81. Finally, Markov’s inequality implies




                                                  A-21
that, for every x > 0,
                                                     !2/k        ! 
                                                   x         |Z | 2/k 
                                                                  I
                       P(|ZI | > x) ≤ exp −             E exp
                                              k
                                              Mψ              Mψk      
                                                  !2/k                                  (A.89)
                                               x       
                                    ≤ 2 exp −             ,
                                              Mψk      


which proves Equation A.82.                                                                    □


B.2 Proof of Theorem 2

Proof . (i) We ﬁrst establish relative concentration of the sample Gram matrix. Write si :=
     ci ), let ui := Σ−1/2
sK ( X                 K     si , and let U be the matrix with rows u⊤
                                                                     i . Then


                           b K := 1 U⊤ U = Σ−1/2 Σ
                           G                     b K Σ−1/2 ,       b K := 1 S⊤ S,
                                                                   Σ                      (A.90)
                                            K         K
                                  n                                       n

and E[ui u⊤
          i ] = IdK . Independence gives

                               h             i      h               i
                                 b K − Id k2 = 1 E kui u⊤ − Id k2
                              E kG       K F              i     K F
                                                 n                                        (A.91)
                                                 1
                                               =    Ekui k4 − dK = o(1).
                                                 n

        b K − Id kop = oP (1). In particular, G
Hence, kG                                     b K , and therefore Σ
                                                                  b K , is positive deﬁnite with
                K

probability approaching one. We work on this event and deﬁne inverse-based quantities arbitrarily
on its complement.
                     −1/2
   Let uK (b
           x) := ΣK         sK (b
                                x), write vK := vK (b
                                                    x), and set


                              vbK
                                2
                                  := sK (b   b −1 sK (b
                                         x)⊤ Σ        x) = uK (b   b −1 uK (b
                                                               x)⊤ G        x).           (A.92)
                                               K                     K



By Equation A.91 and the inverse perturbation bound,

                                    vbK
                                      2
                                               b −1
                                    vK2 − 1 ≤ kGK − IdK kop = oP (1).                     (A.93)


Let e0 select the retained intercept. Since e⊤     x) = 1 and e⊤
                                             0 sK (b           0 ΣK e0 = 1, the Cauchy–Schwarz
                                                                        P
inequality gives 1 ≤ (e⊤         2    2                 bK /vK −
                       0 ΣK e0 )vK = vK . Consequently, v      → 1, vbK               bK
                                                                      2 = O (d ), and v
                                                                           P K
                                                                                        2 is




                                                    A-22
bounded away from zero with probability approaching one.

   The same relative moment condition controls the maximal sample leverage. On the event
 b K − Id kop ≤ 1/2,
kG       K
                                                    1 ⊤ b −1    2
                                   s⊤   ⊤ −1
                                    i (S S) si =      ui GK ui ≤ kui k2 .                          (A.94)
                                                    n           n

Thus, for every δ > 0, the union bound and Markov’s inequality give
                                                                                   
                                                                                   δn
                     P        max s⊤   ⊤ −1
                                   i (S S) si > δ           ≤ o(1) + nP kui k >     2
                             1≤i≤n                                                  2
                                                                                                   (A.95)
                                                                     4Ekui k 4
                                                            ≤ o(1) +           = o(1).
                                                                       δ2n

   Using Equation 13, decompose the prediction error as


             fbK (b
                  x) − f0 (b        x)⊤ (S⊤ S)−1 S⊤ ε + sK (b
                           x) = sK (b                       x)⊤ (S⊤ S)−1 S⊤ ξK − ξK
                                                                                  x
                                                                                    (f0 )
                                                                                                   (A.96)
                                =: I1 + I2 + I3 .


By Assumption 1(ii), E[n−1 kξK k2 ] = O(K −Q ), and hence n−1 kξK k2 = OP (K −Q ) by Markov’s
inequality. Since S(S⊤ S)−1 S⊤ is an orthogonal projector, conditional Chebyshev’s inequality and
Cauchy–Schwarz give

                                         2
                                                                                   
                                     σ                                         dK
                      E[I12 | Xn ] =         vbK
                                               2
                                                    =⇒          I12 = OP                ,
                                       n                                        n
                                                                                                 (A.97)
                           vb2 ⊤                  vb2              dK
                      I22 ≤ K ξK S(S⊤ S)−1 S⊤ ξK ≤ K kξK k2 = OP    Q
                                                                        ,
                               n                               n                        K

                                          2
and I32 = O(K −Q ). Moreover, d2K = Ekui k2 ≤ Ekui k4 , so one has d2K /n → 0. Since (I1 + I2 +
I3 )2 ≤ 3(I12 + I22 + I32 ), the preceding bounds and dK /K Q → 0 prove part (i).

   (ii) Deﬁne the Xn -measurable weights

                                     b −1 si        √
                               x)⊤ Σ                 n I1 X                    X
                                                                   n           n
                           sK (b
                    wni :=     √       K
                                             ,           =  wni εi ,                     2
                                                                                        wni = 1,
                                 n vbK              vbK
                                                                i=1             i=1                (A.98)
                           2
                      max wni ≤ max s⊤    ⊤ −1
                                      i (S S) si = oP (1).
                     1≤i≤n      1≤i≤n


Conditional on Xn , the weights are ﬁxed and the errors are independent, centered, and have variance




                                                    A-23
σ 2 . Hence, their conditional Lyapunov ratio satisﬁes
                                                                       X
                      1 X                        Cε
                         n                                               n
                           E |w ni ε i | 4
                                           | X n  ≤ 4             2
                                                             max wni             2
                                                                                wni = oP (1).        (A.99)
                      σ4                           σ         1≤i≤n
                          i=1                                             i=1


Every subsequence therefore contains a further subsequence along which this Lyapunov ratio con-
verges to zero almost surely. Conditional Lindeberg–Feller then gives almost-sure convergence of
the conditional characteristic function along this further subsequence to exp(−σ 2 t2 /2). Hence,
the conditional characteristic functions converge to this limit in probability along the original se-
quence and, since they are uniformly bounded, also in L1 . Taking expectations and applying Lévy’s
                          √          d
continuity theorem yields n I1 /bvK −
                                    → N (0, σ 2 ).

   Finally, the projection bound above and the fact that vbK
                                                           2 is bounded away from zero with


probability approaching one give

                          nI22                  n                  nI32        n 
                               ≤ kξ K k2
                                         = O P       ,                    = O P       .             (A.100)
                          vbK
                            2                   KQ                   vbK
                                                                       2         KQ

                                √                             √
Hence, n/K Q → 0 implies            n I2 /b
                                          vK = oP (1) and         n I3 /b
                                                                        vK = oP (1). Combining these bounds
                                                                                P
with Equation A.96, the central limit theorem above, and vbK /vK −
                                                                 → 1, we obtain

           √                               √          √        √     
               n{fbK (b
                      x) − f0 (b
                               x)}   vbK        n I1     n I2     n I3 d
                                   =                 +        +         −
                                                                        → N (0, σ 2 ),              (A.101)
                      vK             vK        vbK      vbK      vbK

which proves part (ii).                                                                                    □


B.3 Proof of Theorem 3
                                                                            p
Proof . Let DK := diag(wK1 , . . . , wKdK ), where T > 0 and wKj = T kj /2 / kj !, and write sK :=
 −1
DK              −1
    sK , S := SDK  , ΓK := E[sK (X)s  c ⊤ ], β0K := DK L0K , and βbK := DK L
                                 c K (X)                                   b K . Since DK is

nonsingular, the weighted LASSO problem is equivalent to
                                                                          
                                                       1
                                βbK ∈ arg min            kZ − Sβk + λn kβk1 .
                                                                 2
                                                                                                    (A.102)
                                          β∈RdK       2n

This transformation preserves supports and signs. It also preserves the population normal equation,
         c X (f0 )] = 0.
so E[sK (X)ξ K

                                                                     ci ), and let kj ∈ {0, . . . , K} be the
   For j = 1, . . . , dK , let sij denote the j-th coordinate of sK (X


                                                       A-24
length of the corresponding signature word. For kj = 0, sij = 1. For kj ≥ 1, Lemma A.3 and the
deﬁnition of wKj give
                                                    √
                                     ksij kp ≤ (Csig p)kj ,        p ≥ 2.                       (A.103)

Fix coordinates j, m, and set r := kj + km . When r = 0, the centered product is identically zero.
For r ≥ 1, Hölder’s inequality and Equation A.103 give


                               ksij sim − E(sij sim )kp ≤ C r pr/2 ,    p ≥ 2,                  (A.104)


where C > 0 depends only on R and T .

   The moment-to-ψ argument used in the proof of Lemma A.4 shows that kW kp ≤ Br pr/2 implies
kW kψ2/r ≤ Dr Br for a universal constant D. Thus, the centered product in Equation A.104
has ψ2/r -functional bounded by C r . For r = 1, 2, the usual sub-Gaussian and sub-exponential
inequalities apply. Since the observations are i.i.d., for r ≥ 3, applying (Zhang and Chen, 2021,
Corollary 6.4) with tail parameter 2/r and equal weights 1/n gives, after enlarging C,
                                                                  (r              )!
                    1X
                        n
                                                                       t   tr/2
                P      {sij sim − E(sij sim )} > (Cr)r/2                 +             ≤ 2e−t   (A.105)
                    n                                                  n    n
                        i=1


for every t ≥ 1. Indeed, the concentration constant in that result satisﬁes C(2/r)4r/2 ≤ (Cr)r/2 ;
the same upper bound also absorbs the coeﬃcient of the square-root term.
                          q                           
                              log(edK )   {log(edK )}K
    Deﬁne ∆nK := (CK)K            n     +       n        , where C > 0 is a suﬃciently large ﬁxed
constant. The rate and penalty conditions in Theorem 3 are equivalently qK ∆nK → 0 and λn 
√
  qK ∆nK , with a suﬃciently large leading constant in the latter relation. Write k · kmax for the
entrywise maximum norm. Taking t = A log(edK ) in Equation A.105 for a suﬃciently large ﬁxed
A, using r ≤ 2K, and applying a union bound over all pairs of coordinates yield


                              b K − ΓK
                              Γ                 = OP (∆nK ),       b K := 1 S⊤ S.
                                                                   Γ                            (A.106)
                                          max                             n

Since dK → ∞, the constants can be chosen so that the event on which the left-hand side is bounded
by a ﬁxed multiple of ∆nK has probability approaching one.

   We next transfer the population design conditions to the sample. Write A := (ΓK )A0 A0 ,
b := (Γ
A                                          b deﬁned analogously. By Assumption 2(i), there exist
      b K )A A , and B := (ΓK )Ac A , with B
            0 0                 0 0




                                                     A-25
proof constants CΓ < ∞ and η ∈ (0, 1] such that kA−1 k∞ ≤ CΓ and kBA−1 k∞ ≤ 1 − η uniformly
in K. By Equation A.106,


                       b − A)A−1
                      (A                              b K − ΓK
                                                 ≤ qK Γ                            kA−1 k∞ = oP (1).            (A.107)
                                            ∞                                max


                                                                           b is nonsingular and
The inverse perturbation identity and Assumption 2(i) therefore imply that A
 b−1 k∞ ≤ 2CΓ on an event whose probability tends to one. Since A
kA                                                              b is a sample Gram matrix and

hence positive semideﬁnite, it is positive deﬁnite on this event. Furthermore,
                     n                      o
       bA
       B b−1 − BA−1 = (B
                       b − B) − BA−1 (A
                                      b − A) Ab−1 ,
                                                                                                               (A.108)
        bA
        B b−1 − BA−1          ≤ 1 + kBA           −1
                                                       k∞ q K          b K − ΓK
                                                                       Γ                    b−1 k∞ = oP (1).
                                                                                           kA
                         ∞                                                           max


Consequently, with probability approaching one,


                     b K )−1                                    b K ) Ac A ( Γ
                                                                             b K )−1                η
                    (Γ    A0 A0           ≤ 2CΓ ,              (Γ      0 0        A0 A0          ≤1− .          (A.109)
                                      ∞                                                        ∞    2


   We now control the eﬀective score. Since S is Xn -measurable, conditional independence and
Assumption 2(iii) imply, for every j and t ∈ R,
                          "       (                    )           #           (                 )
                                      tX                                           σ02 t2 X 2
                                            n                                              n
                        E exp            sij εi                Xn ≤ exp                    sij       .          (A.110)
                                      n                                            2n2
                                           i=1                                          i=1

                                                                       P
By Equation A.103 and Equation A.106, maxj n−1                                2
                                                                           i sij = OP (C
                                                                                         2K ). The preceding conditional


moment-generating-function bound and a union bound over j therefore give
                                                               r               !
                        1  ⊤                               K       log(edK )
                          S ε   = OP                   C                            = OP (∆nK ).                (A.111)
                        n     ∞                                        n


                                                                 c with Yi := f0 (X
   The bound kA−1 k∞ ≤ CΓ implies λmin (A) ≥ CΓ−1 . Let Y := f0 (X),              ci ). The

population normal equation and E(Y 2 ) ≤ C give

                                                          h                         i
                    CΓ−1 kβ0K k22 ≤ β0K,A
                                     ⊤
                                            Aβ 0K,A   = E   Y s K,A   ( c ⊤ β0K,A
                                                                        X)
                                          0         0               0             0
                                                n                   o1/2                                        (A.112)
                                                    ⊤
                                  ≤ {E(Y 2 )}1/2 β0K,A  0
                                                          Aβ  0K,A0       .

                                      √
Hence, kβ0K k2 = O(1) and kβ0K k1 = O( qK ).


                                                           A-26
   The Stratonovich–Itô conversion expresses Y as bounded ﬁnite-variation terms plus an Itô in-
tegral with a uniformly bounded integrand; the Burkholder–Davis–Gundy inequality therefore gives
          √
kY kp ≤ C p for every p ≥ 2. Thus, by Equation A.103 and Hölder’s inequality, ksij Yi − E(sij Yi )kp ≤
C kj +1 p(kj +1)/2 . Since kj +1 ≤ K +1 ≤