source: https://arxiv.org/pdf/2602.00383
fetched_utc: 2026-10-04T18:37:28Z
bytes_raw: 642333

NULL-VALIDATED TOPOLOGICAL SIGNATURES OF
                                                      FINANCIAL MARKET DYNAMICS

                                                                        SAMUEL W. AKINGBADE


                                                   Abstract. Financial markets exhibit temporal organization that is not
                                                   fully captured by volatility measures or linear correlation structure.
                                                   We study a null-validated topological approach for quantifying finan-
                                                   cial market complexity using Bitcoin daily log returns and the S&P 500
                                                   index as examples of cryptocurrency and broad U.S. equity market dy-
                                                   namics. The analysis uses the L1 norm of the persistence landscapes
                                                   computed from sliding-window delay embeddings. This quantity co-
arXiv:2602.00383v2 [q-fin.ST] 31 Jul 2026




                                                   moves strongly with stochastic volatility during periods of market stress,
                                                   but the strength and form of this relationship vary over time and differ
                                                   between the two markets. Surrogate-based null models provide statis-
                                                   tical validation of these observations. Rejection of shuffle surrogates
                                                   rules out explanations based on marginal distributions alone, while de-
                                                   partures from phase randomized surrogates indicate sensitivity to non-
                                                   linear and phase-dependent temporal organization beyond linear cor-
                                                   relations. These results demonstrate that persistence landscape norms
                                                   provide complementary information about market dynamics across mar-
                                                   ket conditions.




                                                                            1. Introduction
                                               Understanding the complex temporal dynamics of financial markets re-
                                            mains a central challenge in financial mathematics, quantitative finance, and
                                            econometrics. Traditional tools such as volatility estimates and linear cor-
                                            relation measures provide essential but limited perspectives on market be-
                                            havior, particularly during periods of stress or structural change. Volatility,
                                            often modeled through stochastic processes, captures the scale of fluctuation
                                            but may fail to detect subtler dynamical features that reflect temporal or-
                                            ganization or higher order dependencies in return series. As a result, there
                                            is growing interest in methods that can extract richer information about
                                            the geometry and temporal structure of financial time series beyond con-
                                            ventional statistical summaries.
                                               In recent years, topological data analysis (TDA) has emerged as a promis-
                                            ing framework for studying the shape of complex data. TDA seeks to de-
                                            scribe intrinsic structural features that persist across multiple scales, lever-
                                            aging tools from algebraic topology to quantify connectivity and loops in
                                            point clouds or time series embeddings. At the heart of TDA is persistent
                                            homology, a method for tracking the birth and death of topological fea-
                                            tures such as connected components and cycles as a scale parameter varies,
                                                                                       1
2                             S. W. AKINGBADE

yielding descriptors like barcodes and persistence diagrams that summarize
data shape in a multiscale manner. Persistent homology has been applied
across diverse domains where structure matters, including the analysis of
complex biological and dynamical signals, due to its robustness to noise and
coordinate-free characterization of data geometry; see, for example, [1].
   In the context of time series, a common approach is to convert sequential
observations into a delay or sliding window embedding that reconstructs
the dynamics of the underlying process in a higher-dimensional space. This
method draws on ideas related to Takens’ embedding theorem [2] and has
been studied in both theoretical and applied settings; by embedding a signal
into a point cloud in a reconstructed state space, one can apply persistent
homology to detect recurrent geometric patterns such as loops and voids
that correspond to underlying dynamical phenomena [3]. Practical sum-
maries of these persistent features include persistence landscapes and their
norms, which are scalar functions that quantify the prominence of topolog-
ical features and enable statistical comparison across time.
   Application of these methods to financial time series has grown in recent
years. A major work by [4] used persistent homology to analyze major U.S.
stock indices, showing that persistence landscape norms increase before and
during market meltdowns, thereby providing a novel signal that goes be-
yond standard volatility measures. More recently, [5] offered a theoretical
explanation for this behavior by linking the growth of persistence landscape
norms to log-periodic power law singularity dynamics, which are commonly
used to model speculative bubbles and critical transitions. They showed
that when a financial time series follows such dynamics, its delay coordinate
embedding naturally exhibits structured oscillatory geometry, leading to the
emergence of persistent loop-like features in the reconstructed state space.
In a related line of work, [6] developed a topological framework for recog-
nizing critical transitions in cryptocurrency markets, including Bitcoin and
Ethereum, in the period leading up to the 2018 market crash. Additional
studies have applied topological methods to financial time series in a variety
of settings, including early warning detection, critical transitions, bubble
identification, sparse portfolio and structural analysis of market dynamics;
see, for example, [7, 8, 9, 10, 11, 12, 13].
   Subsequent research has applied topological methods to change point de-
tection in financial markets, demonstrating that persistent homology fea-
tures can align with major economic events and volatility regimes across
different stock markets [14]. Persistence landscape norms have been shown
to correlate with volatility and uncertainty in financial markets [15, 16],
however the dynamical origin of this signal and its dependence on temporal
ordering and nonlinear structure remain largely unexplored. These contri-
butions illustrate the potential of persistent homology to capture aspects
of market dynamics that are not fully accessible via conventional statistical
tools.
NULL-VALIDATED TOPOLOGICAL SIGNATURES OF FINANCIAL MARKET DYNAMICS
                                                                 3

    Despite these advances, several gaps remain in the rigorous validation and
interpretation of topological summaries in financial settings. In particular,
it is important to distinguish genuine temporal organization from artifacts of
marginal distributions or linear second-order dependence. Null models and
surrogate data provide a principled way to make this distinction by preserv-
ing selected statistical properties of a time series while disrupting others. In
financial time series analysis, [17] developed a surrogate-based significance
framework for detecting structural breaks associated with nonlinear causal
interactions, using resampled multivariate time series consistent with a null
model that preserves marginal and linear dependence properties. In the
context of topological data analysis, [18] studied null distributions for per-
sistent homology and showed that persistence diagrams arising from random
point clouds can exhibit universal distributional behavior after appropriate
normalization, providing a foundation for statistical hypothesis testing in
TDA. Another use of null model comparisons in a non-financial setting can
be found in [19]. These works highlight the importance of null-model com-
parisons for interpreting nonlinear and topological summaries.
    Addressing this need is especially relevant in markets characterized by
regime shifts, volatility clustering, and structural instability. Cryptocur-
rency markets provide one such setting and have been widely studied due to
their pronounced volatility, behavioral effects, and rapid structural changes [20,
21, 22]. Bitcoin, as the largest and most liquid cryptocurrency, provides a
natural example for examining these issues, while the S&P 500 index pro-
vides a broad U.S. equity-market comparison. Our work contributes to this
literature by introducing a null-validated topological analysis of Bitcoin log
returns and S&P 500 index returns that explicitly compares persistence-
landscape norms to surrogate ensembles designed to preserve specific statis-
tical properties of the series while selectively disrupting temporal ordering
or nonlinear and phase-dependent structure.
    In this study, we investigate the geometric and temporal structure of fi-
nancial return dynamics through a topological lens, treating the L1 norm of
the persistence landscapes computed from sliding window delay embeddings
as a quantitative summary of reconstructed state-space geometry. The anal-
ysis is carried out for Bitcoin daily log returns and for the S&P 500 index,
providing examples of cryptocurrency and broad U.S. equity-market dy-
namics. Rather than interpreting this quantity solely as a proxy for market
stress, we examine how it relates to and differs from established scale-based
models of market variability. To this end, a central contribution of this
work is a systematic comparison between the persistence landscape norm
and filtered stochastic volatility estimates, including an analysis of their
time varying association through rolling correlations. This comparison al-
lows us to characterize regimes in which topological structure and volatility
align, as well as regimes in which they decouple.
4                             S. W. AKINGBADE

   The second central contribution of this work is the incorporation of surrogate-
based null models to assess the statistical origin of the observed topologi-
cal signal. By employing both shuffle surrogates, which preserve the mar-
ginal distribution of returns while destroying temporal ordering, and phase-
randomized surrogates, which preserve linear second order structure while
removing nonlinear and phase-dependent dependencies, we disentangle the
respective roles of marginal effects, linear correlations, and higher order
temporal organization. This framework enables us to distinguish genuine
geometric structure in the reconstructed dynamics from artifacts induced
by distributional or linear properties of the time series.
   Our results show that while the persistence landscape norm co-moves
with stochastic volatility during periods of market stress, the dependence
between the two is not stationary and differs across markets. In Bitcoin,
the topology-volatility relationship is more unstable and exhibits a clearer
regime shift, whereas in the S&P 500 the coupling is more consistently pos-
itive but still time-varying. In both cases, surrogate null models show that
the observed topological signal cannot be explained solely by marginal re-
turn distributions or by linear second order dependence. Together, these
findings position the persistence landscape norm as a null-validated descrip-
tor of financial time series that is sensitive to volatility while also capturing
complementary information about temporal organization.
   The structure of the paper is as follows. Section 2 reviews the topolog-
ical framework, including persistent homology, persistence landscapes, and
their application to financial time series through sliding window and delay
embeddings. Section 3 compares the L1 norm of the persistence landscape
for Bitcoin log returns with filtered stochastic volatility and examines their
rolling correlation. Section 4 introduces surrogate-based null models for
statistical validation of the persistence landscape norm as a descriptor of
market dynamics beyond marginal distributional effects and linear second
order dependence. Section 5 applies the same framework to the S&P 500
index as a broad U.S. equity market example and compares the resulting
topology-volatility relationship and surrogate-null behavior with the Bitcoin
application. Conclusions and future directions are presented in Section 6.

                              2. Background
2.1. Persistent homology. In this section, we describe the topological
framework used throughout the paper, based on persistent homology. The
tool provides a multiscale characterization of the geometry of point clouds
derived from time series and allows us to extract robust numerical sum-
maries of their evolving structure via persistence landscapes. The mathe-
matical foundations of persistent homology and persistence landscapes are
well established; see, for example, [23, 24, 25, 26].

2.1.1. Persistent homology. It associates to a finite point cloud a family
of topological spaces indexed by a resolution parameter, and tracks the
NULL-VALIDATED TOPOLOGICAL SIGNATURES OF FINANCIAL MARKET DYNAMICS
                                                                 5

evolution of topological features, such as connected components and loops,
across scales. Persistence landscapes provide a functional representation of
this multiscale information in a Banach space, enabling numerical summaries
and statistical comparison. In this work, we ultimately summarize each
point cloud by a single scalar quantity given by the L1 norm of its persistence
landscape.
   Let
                        X “ tx0 , x1 , . . . , xm´1 u Ă RN
be a finite point cloud embedded in Euclidean space. To associate a topo-
logical space to X, we consider the Vietoris–Rips construction. For a fixed
resolution parameter t ą 0, the Vietoris–Rips simplicial complex V RpX, tq
is defined by including a k-simplex with vertices txi0 , . . . , xik u whenever the
pairwise distances between all vertices are strictly less than t, that is,
              dX pxij , xij 1 q ă t    for all xij , xij 1 P txi0 , . . . , xik u.
Intuitively, simplices are added whenever their vertices become indistin-
guishable at resolution t. As t increases, these complexes form a nested
sequence
                      V RpX, tq Ď V RpX, t1 q for t ă t1 ,
which constitutes a filtration of simplicial complexes.
   At each resolution level, we compute the simplicial homology groups
                                      Hn pV RpX, tqq
with coefficients in a fixed field, here taken to be Z2 . The generators of
these groups correspond to n-dimensional topological features: connected
components for n “ 0, loops for n “ 1, voids for n “ 2, and so forth.
In this work we restrict attention to one-dimensional homology, n “ 1, so
that the analysis focuses exclusively on loop-like geometric structures in the
embedded data.
  A filtration of simplicial complexes induces a corresponding sequence of
homology groups,
                 Hn pV RpX, tqq Ñ Hn pV RpX, t1 qq               for t ă t1 ,
via canonical homomorphisms induced by the inclusions in the filtration.
The resulting collection is called a persistence module. Persistence modules
are uniquely decomposable into a direct sum of interval modules up to per-
mutation [27]. The multiset of intervals in this decomposition is called the
barcode, and each interval represents the lifespan of a topological feature.
2.1.2. Persistence diagrams. A homology class α P Hn is said to be born at
scale bα if it first appears at t :“ bα and is not in the image of any class from
smaller scales. The class persists across intermediate resolutions and is said
to die at scale dα ą bα if its image becomes trivial at t :“ dα . Each such
class is therefore associated with a birth–death pair pbα , dα q, with finite
multiplicity determined by the number of classes sharing the same birth
and death values. The collection of all birth–death pairs arising from Hn is
6                               S. W. AKINGBADE

encoded in the persistence diagram Pn , which is a locally finite multiset of
points supported on U :“ tpt1 , t2 q P R2 : t1 ă t2 u together with points on the
diagonal δU :“ tpt, tq P R2 u counted with infinite multiplicity, representing
trivial features. The horizontal axis corresponds to birth values and the
vertical axis to death values.

2.1.3. Persistence landscapes. To obtain a functional representation suitable
for numerical analysis, we map persistence diagrams into a Banach space
using persistence landscapes.
   For each off-diagonal point pbα , dα q P Pn , we define the piecewise linear
function
                                  $              `   bα `dα
                                                            ‰
                                  &x ´ bα , x P `bα , 2 ˘,
                                  ’
(2.1)             fpbα ,dα q pxq “ dα ´ x, x P bα `d2 , dα ,
                                                      α
                                  ’
                                   0,       otherwise.
                                  %

Given a persistence diagram with finitely many off-diagonal points, the per-
sistence landscape is defined as the sequence of functions
(2.2)     λn “ pλn piqqiPN ,   λn piqpxq “ imax tfpbα ,dα q pxq | pbα , dα q P Pn u,
where imax denotes the i-th largest value among the indicated functions. If
the i-th largest value does not exist, λn piqpxq is set to zero. The resulting
object lies in the Banach space Lp pN ˆ Rq for any p ě 1.
   For a persistence landscape λn , the Lp norm is defined by
                  ˜              ¸1{p                                  ˙1{p
                    8
                    ÿ                               ˆż
                               p                                   p
(2.3) }λn }p “         }λn piq}p      , }λn piq}p “     |λn piqpxq| dx      .
                    i“1                                     R

In this work, we focus exclusively on the L1 norm. For finite persistence
diagrams, this norm admits the closed-form expression [24]
                                  1ÿ
(2.4)                    }λn }1 “     pdα ´ bα q2 .
                                  4 α
In practice, we compute a numerically approximated and truncated version
of this quantity by integrating the first imax landscape layers over a finite
grid of scale values.

2.2. Application to time series. We now describe how this framework is
applied to financial time series following [5, 6, 28].
   Let
                            Z “ tz0 , z1 , . . . , zN ´1 u
be a real valued time series of length N . Fix an embedding dimension m and
a time delay d ě 1. The delay-coordinate embedding produces a sequence
of vectors
                        xt “ pzt , zt`d , . . . , zt`pm´1qd q,
defined for all indices t such that the coordinates exist.
NULL-VALIDATED TOPOLOGICAL SIGNATURES OF FINANCIAL MARKET DYNAMICS
                                                                 7

2.2.1. Choice of embedding dimension and delay. The use of delay-coordinate
embeddings in this work is motivated by classical results from nonlinear dy-
namical systems theory, which establish conditions under which the geom-
etry of an underlying state space can be reconstructed from time-delayed
observations.
   A foundational result is Takens’ embedding theorem [2]. Consider a
discrete-time dynamical system xt`1 “ T pxt q evolving on a compact smooth
manifold M of dimension D, together with a smooth observation function
h : M Ñ R. Let tzt u be the scalar time series defined by zt “ hpxt q. For a
fixed delay d ě 1, define the delay-coordinate map
            Φ : M Ñ Rm ,         Φpxt q “ pzt , zt`d , . . . , zt`pm´1qd q.
Takens’ theorem states that, provided m ě 2D ` 1, it is a generic property
of the pair pT, hq that Φ is an embedding, i.e., a smooth injective map with
a smooth inverse onto its image. In this sense, the delay-coordinate vectors
provide a faithful geometric representation of the underlying state space.
   This result was subsequently generalized by [29], who showed that if the
dynamics admit a compact attractor A Ă M of finite fractal dimension D,
then an embedding of the attractor can be achieved for m ě 2D ` 1 under
the weaker assumption of prevalence rather than genericity. This extension
is particularly relevant in practical settings where the dynamics evolve on a
lower dimensional invariant set.
   In the present study, delay coordinate embeddings are employed not for
exact state-space reconstruction, but as a geometric representation from
which topological features can be extracted robustly via persistent homol-
ogy. Consequently, the embedding dimension m and delay τ are chosen
empirically to be sufficient for capturing loop-like geometric structure in the
delay embedding while remaining computationally tractable.
2.2.2. Topological summaries of Bitcoin log return dynamics. To detect tem-
poral variation in topological signal, we apply a sliding window of length w
to the sequence txt u, yielding a time-indexed family of point clouds
                        X t “ txt , xt`1 , . . . , xt`w´1 u.
   For each window X t , we compute the Vietoris–Rips filtration, extract the
one dimensional persistence diagram, construct the corresponding persis-
tence landscape, and evaluate the truncated L1 landscape norm.
   Bitcoin price data from January 1, 2020 to December 20, 2025 were ob-
tained from Yahoo Finance [30] and used to compute daily log returns shown
in Figure 1. The topological data analysis procedure described above is then
applied to the standardized Bitcoin log returns.
   The result is a scalar time series
                                   t ÞÑ }λt }1 ,
which quantifies the evolving prominence of loop-like geometric structure in
the embedded dynamics.
8                                                   S. W. AKINGBADE

                         0.2




                         0.0
    Daily log returns




                        −0.2




                        −0.4




                                 2020               2022              2024               2026
                                                             Date



                               Figure 1. Bitcoin daily log returns from January 1, 2020 to
                               December 20, 2025.

   We show the time evolution of the L1 norm of the persistence landscape
computed from sliding window delay embeddings of standardized Bitcoin
log returns in Figure 2, using an embedding dimension of 4, a delay of 2 and
a sliding window of length 50.
   The resulting series exhibits multiple intervals of elevated L1 values through-
out the sample, reflecting the recurrence of loop-like geometric structure in
the delay space across several distinct periods. These elevated intervals are
interspersed with lower activity regimes, indicating that the strength of the
topological signal varies over time rather than remaining uniformly high.
This temporal variability motivates examining whether the observed topo-
logical signal can be explained by conventional market descriptors such as
sentiment or volatility.



                        0.4




                        0.3
    L1 norm




                        0.2




                        0.1




                        0.0

                                 2020              2022               2024               2026
                                                             Date



                               Figure 2. L1 norm of the persistence landscape of Bitcoin
                               log returns for w “ 50, m “ 4, τ “ 2.
NULL-VALIDATED TOPOLOGICAL SIGNATURES OF FINANCIAL MARKET DYNAMICS
                                                                 9

            3. Bitcoin stochastic volatility comparison
3.1. Stochastic volatility model. We model the Bitcoin log return series
using a standard stochastic volatility (SV) specification, in which the latent
state corresponds to the log variance of returns. Let ht denote the latent
log variance at time t. The model is defined by the following two equations.

3.1.1. State (process) equation. The latent log variance follows a mean re-
verting AR(1) process,
                                                       iid
(3.1)          ht “ µ ` ϕpht´1 ´ µq ` ση ηt ,     ηt „ N p0, 1q.
where µ is the long run mean of the log variance, ϕ is the autoregressive
coefficient, and ση ą 0 governs the magnitude of stochastic shocks to the
latent log variance.
   We restrict ϕ P p0, 1q so that the latent log-variance process has a well-
defined stationary distribution. This assumption is not intended to assert
that the observed financial return series is globally stationary over the full
sample, especially during periods of market instability. Rather, the station-
ary stochastic volatility model is used as a parsimonious latent-volatility
benchmark against which the topological signal can be compared. Tempo-
rary volatility bursts and crash-related episodes are accommodated through
innovations ηt in the latent state and through the exponential mapping from
log variance to conditional volatility.

3.1.2. Observation (measurement) equation. Conditional on ht , returns are
Gaussian with zero mean and variance exppht q,
                           zt | ht „ N p0, exppht qq
   Under this formulation, exppht q represents the conditional variance of re-
turns and exppht {2q the conditional volatility. This specification corresponds
to the canonical discrete-time stochastic volatility model widely used in em-
pirical finance (e.g.,[31, 32, 33, 34, 35]).

3.2. Inference and parameter estimation. The SV model is cast as
a partially observed Markov process (state-space model) and fitted using
likelihood methods based on Monte Carlo sampling. Inference is carried
out within the pomp framework, which supports likelihood evaluation and
parameter estimation via simulation for nonlinear state-space models with
non Gaussian noise.
   To enforce parameter constraints during optimization, the model is repa-
rameterized internally so that ση is estimated on the log scale and ϕ on the
logit scale, ensuring ση ą 0 and ϕ P p0, 1q throughout estimation.
   Initial parameter values are chosen heuristically. In particular, the long
run mean µ is initialized using the logarithm of the empirical variance of
the return series, while the remaining parameters are set to plausible values
reflecting high persistence in financial volatility.
10                               S. W. AKINGBADE

   Model parameters θ “ pµ, ϕ, ση , h0 q are estimated by maximum likelihood
using iterated filtering (IF2), a simulation-based algorithm for partially ob-
served Markov processes [36, 37]. Iterated filtering repeatedly applies a
particle filter while perturbing parameters via a random walk with grad-
ually decreasing variance, allowing the algorithm to ascend the likelihood
surface of the state-space model.
   For robustness against local maxima and Monte Carlo variability, the
iterated filtering procedure was repeated 10 times from the same initial
parameter guess. For each replicate, the likelihood at the final parameter
estimate was evaluated 5 times using independent particle filters, and the
replicate likelihood was summarized using a log-mean-exp aggregation. The
parameter set associated with the highest aggregated likelihood was selected
as the final estimate θ̂.

3.3. Filtered latent volatility. Given the estimated parameters θ̂, we ap-
ply a particle filter to approximate the sequence of filtering distributions

                        ppht | z1:t ; θ̂q,     t “ 1, . . . , n.

The primary quantity of interest is the filtered posterior mean of the latent
log variance,
                               ĥt :“ Erht | z1:t ; θ̂s.
In practice, this expectation is approximated using the particle representa-
tion returned by the filter,
                                            Np
                                         1 ÿ piq
                                 ĥt «         h ,
                                         Np i“1 t

        piq
where ht denotes the i-th particle at time t after resampling.
   From the filtered log variance sequence tĥt u, we construct estimates of
the conditional variance and volatility as
                                         b          ˜ ¸
                                                      ĥt
(3.2)            V̂t “ exppĥt q,  σ̂t “ V̂t “ exp        .
                                                       2

The resulting series pĥt , V̂t , σ̂t q provides a time-resolved estimate of latent
stochastic volatility. Figure 3 displays the filtered volatility series over cal-
endar time, which serves as a latent volatility benchmark for subsequent
analysis.
   Having obtained a filtered estimate of latent stochastic volatility, we now
empirically compare its temporal evolution with the L1 norm of the persis-
tence landscape computed from sliding-window embeddings of Bitcoin log
returns.
NULL-VALIDATED TOPOLOGICAL SIGNATURES OF FINANCIAL MARKET DYNAMICS
                                                                11

         0.15




         0.10
    ^t
    σ




         0.05




         0.00
                2020             2022                2024               2026
                                          Date



           Figure 3. Filtered conditional volatility estimate σ̂t ob-
           tained from the stochastic volatility model of Bitcoin log re-
           turns.


3.4. Empirical comparison with topological signal. In Figure 4, we
present a standardized comparison between the L1 norm of the persistence
landscape computed from the Bitcoin log return series tzt u and the filtered
stochastic volatility estimate.
   In early 2020, the onset of the COVID-19 crisis is marked by an abrupt
and extreme surge in stochastic volatility. During this period, the topo-
logical signal rises as well, indicating that the large amplitude fluctuations
associated with the market crash are accompanied by pronounced geomet-
ric organization in the reconstructed return dynamics. This co-movement
persists throughout much of 2020–2021, a period characterized by repeated
volatility spikes and sustained market stress, during which both measures
remain elevated and closely aligned.
   Following these stress episodes, the series enter multiple phases of volatil-
ity compression. In mid 2020 and again in late 2020, the standardized
volatility drops to values near ´2, indicating unusually low volatility rel-
ative to its long-run mean. During these intervals, the topological signal
also declines below its mean, but typically not to the same extent as volatil-
ity. Furthermore, following the late 2021 to early 2022 decline in market
volatility, the stochastic volatility estimate remains suppressed, whereas the
topological signal continues to display intermittent bursts and sustained
deviations from baseline. This asymmetric relaxation suggests that while
fluctuation amplitude contracts rapidly after major shocks, geometric orga-
nization in return dynamics decays more gradually, retaining some structure
even as volatility becomes unusually subdued.
   A similar but more prolonged compression regime occurs in 2023. In
standardized units, stochastic volatility remains persistently suppressed for
an extended period, reaching values near ´2 and exhibiting relatively little
variation. Over the same interval, the topological signal is often negative
12                                         S. W. AKINGBADE

as well, but again does not compress as strongly and continues to display
intermittent excursions. This behavior indicates that periods of apparent
market calm, as measured by volatility, can still be associated with nontrivial
temporal organization in returns, though at a reduced level compared to
crisis periods.
   All these observations indicate two key features. First, during periods of
severe market stress, volatility and topological signal rise together reflect-
ing the joint presence of large fluctuations and strong geometric structure.
Second, outside these regimes, particularly during volatility compression
phases, the relationship becomes asymmetric: volatility often contracts more
strongly and more rapidly than the topological signal. This indicates that
the L1 norm is sensitive not only to fluctuation scale but also to the per-
sistence and organization of return dynamics, which can survive, albeit in
weakened form, during extended periods of low volatility.




                4
     z−score




                2




                0




               −2


                     2020                2022                 2024                2026
                                                   Date



                    Figure 4. Standardized comparison of the L1 norm of the
                    persistence landscape (blue) and filtered stochastic volatility
                    (red).

   To quantify the evolving relationship between topological signal and volatil-
ity, we examine the rolling correlation between the L1 norm and the filtered
stochastic volatility estimate over a 180-day horizon in Figure 5. At each
time point, the curve reports the linear association between topology and
volatility over the preceding six months, providing a time-resolved measure
of their dependence.
   During periods of heightened market stress, the rolling correlation at-
tains sustained positive values, indicating that increases in volatility are
accompanied by concurrent increases in topological signal. This behavior is
consistent with the co-movement observed in Figure 4 during crisis regimes,
where large-amplitude fluctuations and strong geometric organization arise
together.
NULL-VALIDATED TOPOLOGICAL SIGNATURES OF FINANCIAL MARKET DYNAMICS
                                                                13


                   0.8




                   0.4
    Correlation




                   0.0




                  −0.4
                           2020              2022               2024              2026
                                                      Date



                         Figure 5. Rolling correlation between the L1 norm and sto-
                         chastic volatility (180-day window).


   In contrast, following the subsequent contraction in volatility, the rolling
correlation undergoes a pronounced decline and becomes markedly unstable,
with extended intervals of weak or even negative association. Although the
correlation exhibits multiple local minima, changepoint detection using the
Pruned Exact Linear Time (PELT) algorithm identifies a single dominant
shift (indicated by the brown dashed line in Figure 5) in the mean level of
dependence. This transition separates an earlier regime characterized by
persistently strong coupling from a later regime in which the association
between topology and volatility is weaker and more variable.
   This behavior indicates that the dependence between topological signal
and volatility is not stationary over time. While the two measures align
closely during crisis periods, the topological signal may persist or exhibit
intermittent intensification even as volatility subsides. This further supports
the interpretation that the L1 norm captures aspects of return dynamics
beyond fluctuation scale alone, reflecting changes in temporal organization
that are not fully encoded by volatility.

3.5. Topological signal beyond volatility and sentiment. We perform
a residualization analysis to examine whether the Bitcoin topological signal
is fully explained by stochastic volatility and coarse sentiment variation.
Sentiment is measured using the Crypto Fear & Greed Index obtained via
the public API provided by alternative.me [38]. This index is a compos-
ite sentiment indicator scaled between 0 (Extreme Fear) and 100 (Extreme
Greed), designed to capture aggregate market sentiment by combining multi-
ple behavioral and market-based inputs, including price momentum, volatil-
ity, trading volume, and social media activity.
   In this analysis, the L1 norm of the persistence landscape computed from
delay embeddings of Bitcoin log returns is regressed on contemporaneous
14                                S. W. AKINGBADE




           1.0
           0.8
           0.6
     ACF

           0.4
           0.2
           0.0




                 0      5        10       15         20     25       30

                                               Lag



           Figure 6. ACF of the residual L1 norm of the persistence
           landscape computed from Bitcoin log return embeddings af-
           ter removing linear effects of stochastic volatility and senti-
           ment.


measures of volatility and sentiment. Specifically, we consider the linear
model


(3.3)                 L1 ptq “ β0 ` β1 σ t ` β2 F t ` β3 St ` εt ,
   where L1 ptq denotes the L1 norm summarizing the topological signal of the
log return dynamics, σ t is the rolling window mean of the filtered stochastic
volatility, F t is the
                    a rolling window mean of the Fear & Greed sentiment
index, and St :“ V arpFt´L`1:t q denotes the rolling window standard de-
viation of sentiment. The coefficients β0 , ..., β3 capture linear associations
between the topological summary and the covariates, while the residual term
εt represents the component of topological variation not explained by volatil-
ity or sentiment.
   The primary object of interest is the temporal dependence structure of
the residual series εt . Figure 6 displays the autocorrelation function (ACF)
of εt , which exhibits a slow decay with statistically significant correlations
persisting across many lags. This behavior is inconsistent with a white
noise residual and indicates that structured temporal organization remains
in the topological signal after removing linear effects of volatility and coarse
sentiment statistics.

                     4. Bitcoin surrogate null models
   Let tzt uN
            t“1 denote the standardized Bitcoin log return series. To de-
termine whether the L1 norm of the persistence landscape obtained from
NULL-VALIDATED TOPOLOGICAL SIGNATURES OF FINANCIAL MARKET DYNAMICS
                                                                15

sliding window delay embeddings of tzt u arise from genuine temporal struc-
ture, rather than effects attributable to the marginal distribution or linear
second-order dependence, we compare the resulting time series of persistence
landscape norms to those obtained from two classes of surrogate Bitcoin log
return processes. Each surrogate is transformed through the same embed-
ding and persistent homology pipeline, thereby inducing a null distribution
for the windowed persistence landscape norm defined in 2.1.
4.1. Shuffle (i.i.d.) surrogate. Let π be a random permutation of t1, . . . , N u
drawn uniformly from the symmetric group SN . The shuffle surrogate of the
observed series tzt uN
                     t“1 is defined by
(4.1)                         zts :“ zπptq ,        t “ 1, . . . , N.
This construction preserves the empirical marginal distribution of tzt u ex-
actly, but destroys all temporal ordering and hence all serial dependence.
In probabilistic terms, this surrogate corresponds to a null in which the
observed series is treated as exchangeable.
   For each realization j “ 1, . . . , Ns , we generate an independent permuta-
tion πj , compute the corresponding surrogate series zts,j , and apply Section
2.1 to obtain a surrogate topological time series.
4.2. FFT phase-randomized surrogate. The second null preserves sec-
ond order temporal structure while destroying nonlinear and phase depen-
dent features. Let z̃t “ zt ´ z̄ denote the demeaned series, and define its
discrete Fourier transform (DFT) by
                            Nÿ
                             ´1
(4.2)            Zk :“            z̃t e´2πikt{N ,       k “ 0, . . . , N ´ 1.
                            t“0

Write Zk “ |Zk |eiθk . A phase randomized surrogate is constructed by re-
placing the phases θk at positive frequencies with i.i.d. random variables
(4.3)                                 ϕk „ Unifp0, 2πq,
while retaining the magnitudes |Zk |, and enforcing conjugate symmetry so
that the inverse transform is real-valued. Concretely, for k “ 1, . . . , tpN ´
1q{2u, define
(4.4)                      Zkfft :“ |Zk |eiϕk ,        fft
                                                      ZN         fft
                                                          ´k :“ Zk ,

and set Z0fft :“ Z0 . If N is even, the Nyquist component k “ N {2 must
be real; one may set ZN  fft :“ Z
                            {2    N {2 (or equivalently randomize with a sign
change consistent with real-valuedness).
  The inverse DFT yields a surrogate demeaned series
                              N ´1
                           1 ÿ fft 2πikt{N
(4.5)          z̃tfft :“        Z e        ,               t “ 0, . . . , N ´ 1,
                           N k“0 k

to which the original mean z̄ is restored via ztfft “ z̃tfft ` z̄.
16                             S. W. AKINGBADE

   This procedure preserves the power spectrum (and hence the autoco-
variance function) asymptotically, while destroying higher-order temporal
dependencies and nonlinear phase relationships [39, 40]. As before, for each
realization j “ 1, . . . , Nfft , we apply 2.1 to obtain a surrogate topological
time series.

4.3. Pointwise null envelopes for persistence landscape norms. For
each sliding window and each null model, we generate a surrogate ensemble
of persistence landscape norms by applying the same embedding and topo-
logical pipeline described in Section 2.1 to surrogate versions of tzt u. These
surrogate values form an empirical sample from the null distribution of the
window-level statistic. In all experiments, null envelopes are estimated us-
ing 30 surrogate realizations per null model. The qualitative behavior of
the envelopes and exceedance patterns is robust to further increases in the
number of surrogate realizations.
   At each window, we summarize this null distribution by computing its
mean, as well as its 5th and 95th empirical percentiles. The interval de-
fined by these two percentiles constitutes a pointwise null envelope for the
persistence landscape norm at that window.
   This envelope provides a marginal comparison at each window index and
should not be interpreted as a simultaneous confidence band across time; in
particular, it does not control the family-wise error rate over all windows.

4.4. Exceedance statistics. We investigate deviations of the persistence
landscape norm from its surrogate-based null envelopes by examining ex-
ceedances across sliding windows. We restrict attention to windows for
which both the norm computed from the Bitcoin log return series and the
corresponding null quantiles are well defined.
   An exceedance below the null is recorded when the persistence landscape
norm falls below the lower (5th percentile) bound of the null envelope, while
an exceedance above the null is recorded when it exceeds the upper (95th
percentile) bound. We count the total number of such lower and upper
exceedances across all valid windows.
   Finally, we report the fractions of windows in which the persistence land-
scape norm lies below or above the null envelope, respectively. These frac-
tions provide a concise summary of how often the observed topological signal
deviates from that expected under the surrogate null models.
   The empirical behavior of these envelopes and the associated exceedance
frequencies are examined in Section 4.5 and summarized in Table 1.

4.5. Comparison with surrogate-based null envelopes.

4.5.1. Shuffle surrogate comparison. In Figure 7, we compare the observed
time series of L1 norm of the persistence landscape to pointwise null en-
velopes obtained from shuffle surrogates. Because shuffle surrogates pre-
serve the marginal distribution of returns but destroy all temporal ordering,
NULL-VALIDATED TOPOLOGICAL SIGNATURES OF FINANCIAL MARKET DYNAMICS
                                                                17




              0.4




              0.3
    L1 norm




              0.2




              0.1




              0.0

                    2020                2022                2024                2026
                                                  Date




                    Figure 7. Comparison of the observed L1 norm of the per-
                    sistence landscape for Bitcoin (blue) with pointwise null en-
                    velopes obtained from shuffle surrogates.


exceedances relative to this envelope indicate sensitivity of the windowed
norms to temporal dependence.
   The series frequently exceeds the upper bound of the shuffle null envelope,
particularly during pronounced volatility episodes in early 2021 and mid
2022, where the landscape norm rises well above what is expected under
random reordering of returns. These excursions indicate that the topological
signal captured by the sliding-window embeddings is not explained by the
empirical distribution of returns alone and depends critically on temporal
ordering.
   At the same time, there are periods, most notably during relatively calm
market regimes, where the norm of the persistence landscape falls within
or below the shuffle envelope, suggesting that during these intervals the
windowed topological signal is closer to that expected under weak or absent
temporal dependence.
   The exceedance rates confirm that a non-negligible fraction of windows
lie above the 95% shuffle envelope, with rejection frequencies well above the
nominal 5% level. This supports rejection of the hypothesis that the norm
of the persistence landscapes arises solely from the marginal distribution of
Bitcoin log returns.


4.5.2. FFT phase-randomized surrogate comparison. In Figure 8, we com-
pare the observed persistence landscape norm to null envelopes generated
by FFT phase randomized surrogates. These surrogates preserve the power
spectrum and hence linear second order temporal structure while destroying
nonlinear and phase-dependent dependencies.
   Relative to this more restrictive null, the norm exhibits a different pat-
tern. While occasional excursions above the FFT envelope occur, they are
18                                           S. W. AKINGBADE




               0.4




               0.3
     L1 norm




               0.2




               0.1




               0.0

                     2020                 2022                 2024                2026
                                                     Date




                     Figure 8. Comparison of the observed L1 norm of the per-
                     sistence landscape for Bitcoin (blue) with pointwise null en-
                     velopes generated by FFT phase-randomized surrogates.

markedly fewer and more localized than in the shuffle case. In many peri-
ods, particularly after 2022, the series lies persistently below the mean of
the FFT null ensemble, and often near the lower edge of the envelope.
   This behavior indicates that the norm of the persistent landscape is sen-
sitive to structure beyond linear correlation alone. The suppression of the
norm relative to the FFT null suggests that nonlinear temporal organization
present in tzt u constrains the geometry of the delay embedded point clouds
in a way that is not reproduced by phase randomized surrogates.
   Both of these results demonstrate that the L1 norm of the persistence
landscape derived from Bitcoin log returns exhibits temporal structure that
cannot be explained by either the marginal distribution alone or by linear
second-order temporal dependence. The shuffle surrogate analysis estab-
lishes sensitivity to temporal ordering, while the FFT phase randomized
analysis indicates structure beyond that captured by linear correlations.

     Null model           Below 5% Above 95% Outside envelope
     Shuffle               11.08%   14.55%       25.63%
     FFT phase-randomized  46.43%    2.91%       49.34%

                     Table 1. Pointwise exceedance rates of Bitcoin L1 norm of
                     the persistence landscape relative to surrogate null envelopes.


                              5. Application to the S&P 500 index
5.1. S&P 500 data and topological signal. To examine whether the
null-validated topological framework extends beyond cryptocurrency mar-
kets, we apply the same pipeline to the S&P 500 index. This provides a com-
plementary application to a broad and highly liquid equity market bench-
mark whose volatility structure differs substantially from Bitcoin. Whereas
NULL-VALIDATED TOPOLOGICAL SIGNATURES OF FINANCIAL MARKET DYNAMICS
                                                                19

                         0.10




    Daily log returns    0.05




                         0.00




                        −0.05




                        −0.10




                                2020             2022             2024        2026
                                                         Date



                                       Figure 9. S&P 500 daily log returns.

Bitcoin is characterized by larger and more frequent extreme fluctuations,
the S&P 500 exhibits more persistent volatility regimes associated with
macroeconomic and equity-market stress. This comparison allows us to as-
sess whether the persistence landscape norm captures market organization
in a conventional equity index as well as in a cryptocurrency market.
   Daily S&P 500 closing prices from January 1, 2020 to December 20, 2025
are obtained from Yahoo Finance [30] and used to compute close-to-close
trading-day log returns. Figure 9 shows the resulting daily log return series.
The largest return fluctuations occur during the early 2020 COVID-19 mar-
ket shock, with additional volatility episodes visible during 2022 and later
localized stress periods.
   For the topological analysis, the S&P 500 log return series was standard-
ized globally and then analyzed using the same parameters as in the Bitcoin
application: embedding dimension m “ 4, delay τ “ 2, sliding window
length w “ 50, one-dimensional persistent homology, and the L1 norm of
the persistence landscape. Figure 10 shows the resulting time series of the
norm of the persistence landscape.
5.2. Comparison with stochastic volatility. We next fit the same sto-
chastic volatility model described in Section 3 to the S&P 500 return series.
The filtered conditional volatility estimate exhibits a dominant spike during
the early 2020 market crash, followed by a lower but persistent elevated-
volatility regime during 2022. Compared with Bitcoin, the S&P 500 filtered
volatility is lower in magnitude and more regime-like, which is consistent
with the behavior of a broad equity index.
   Figure 11 compares the standardized L1 norm of the persistence land-
scape with the standardized filtered stochastic volatility estimate. The two
quantities co-move strongly during major equity-market stress periods, espe-
cially during the COVID-19 crash and the 2022 volatility regime. However,
their relationship is not one-to-one. The L1 signal displays sharper localized
20                                          S. W. AKINGBADE



               0.6




               0.4
     L1 norm




               0.2




               0.0

                        2020               2022                2024                2026
                                                     Date



                     Figure 10. L1 norm of the persistence landscape computed
                     from sliding-window delay embeddings of standardized S&P
                     500 log returns for w “ 50, m “ 4, τ “ 2.

               6




               4
     z−score




               2




               0




                      2020                2022                 2024                2026
                                                    Date



                     Figure 11. Standardized comparison of the L1 norm of the
                     persistence landscape (blue) and filtered stochastic volatility
                     (red) for S&P 500 log returns.

bursts, while the stochastic volatility estimate is smoother and more persis-
tent. This indicates that the topological signal is sensitive to volatility, but
not identical to the filtered volatility process.
   To quantify the time-varying association between topology and volatility,
we compute the rolling correlation between the norm of the persistence land-
scape and the filtered stochastic volatility estimate using a 180-day window.
The result is shown in Figure 12. The rolling correlation remains mostly pos-
itive throughout the sample, indicating a stronger overall coupling between
topology and volatility than observed in the Bitcoin application. Never-
theless, the correlation varies substantially over time, with periods of very
NULL-VALIDATED TOPOLOGICAL SIGNATURES OF FINANCIAL MARKET DYNAMICS
                                                                21

strong association interrupted by intervals of weaker dependence. In con-
trast to the Bitcoin case, no single dominant changepoint is detected in
the rolling correlation series under the selected penalty. Thus, the S&P
500 results indicate time-varying coupling without a single sharp transition
separating two persistent regimes.



                  0.75




                  0.50
    Correlation




                  0.25




                  0.00




                           2020                2022               2024                2026
                                                        Date



                         Figure 12. Rolling correlation between the L1 norm and
                         filtered stochastic volatility for the S&P 500 using a 180-day
                         window.



5.3. Surrogate null validation. Finally, we apply the same surrogate-
based null validation framework used in the Bitcoin analysis. For the shuffle
null, we randomly permute the standardized S&P 500 return series, thereby
preserving the empirical marginal distribution while destroying temporal or-
dering. Figure 13 compares the observed L1 norm with the pointwise null
envelope generated from shuffle surrogates. The observed topological sig-
nal frequently exceeds the upper shuffle envelope, particularly during early
2020 and 2022. These exceedances indicate that the observed topological
structure is not explained by the marginal distribution of returns alone and
depends on the temporal organization of the series.
   For the FFT phase-randomized null, the Fourier magnitudes are preserved
while the phases are randomized, preserving linear second-order structure
while disrupting nonlinear and phase-dependent temporal organization. Fig-
ure 14 shows that the observed L1 norm also departs substantially from this
null. In contrast to the shuffle case, the departures from the FFT null are
often below the surrogate envelope, indicating that the observed S&P 500
dynamics generate less loop-like geometry than many phase-randomized se-
ries with the same power spectrum. This behavior suggests that the real
temporal organization of S&P 500 returns constrains the geometry of the
delay embedding in a way that is not reproduced by phase randomization.
22                                              S. W. AKINGBADE



               0.6




               0.4
     L1 norm




               0.2




               0.0

                     2020                2022                     2024           2026
                                                       Date




                     Figure 13. Comparison of the observed L1 norm of the per-
                     sistence landscape for the S&P 500 (blue) with pointwise null
                     envelopes obtained from shuffle surrogates.

   Table 2 summarizes the pointwise exceedance rates of the observed L1
norm relative to the surrogate envelopes. The exceedance rates are above
the corresponding nominal pointwise levels for both null models, indicating
that the S&P 500 topological signal is not reducible to either marginal return
distributions or linear second-order dependence alone.
   Overall, the S&P 500 results show that the null-validated topological
signal is not specific to Bitcoin. The norm of the persistence landscape co-
moves with stochastic volatility during major equity market stress periods,
but its relationship with volatility remains time-varying, and the surrogate
analyses indicate departures from null models based on both the marginal
distribution and the linear spectrum.


               0.6




               0.4
     L1 norm




               0.2




               0.0

                     2020                2022                     2024           2026
                                                       Date




                     Figure 14. Comparison of the observed L1 norm of the per-
                     sistence landscape for the S&P 500 (blue) with pointwise null
                     envelopes generated by FFT phase-randomized surrogates.
NULL-VALIDATED TOPOLOGICAL SIGNATURES OF FINANCIAL MARKET DYNAMICS
                                                                23

   Null model           Below 5% Above 95% Outside envelope
   Shuffle               12.06%   22.33%       34.39%
   FFT phase-randomized  52.65%    6.00%       58.65%

       Table 2. Pointwise exceedance rates of the S&P 500 L1
       norm of the persistence landscape relative to surrogate null
       envelopes.


                              6. Conclusions
   We introduced a null-validated topological framework for quantifying fi-
nancial market complexity and applied it to Bitcoin daily log returns and
the S&P 500 index as examples of cryptocurrency and broad U.S. equity-
market dynamics. The analysis treats the L1 norm of the persistence land-
scape derived from sliding window delay embeddings as a scalar summary
of reconstructed state-space geometry. Across both markets, this quantity
is sensitive to periods of market stress, but it is not merely a restatement
of volatility. Instead, it provides a complementary descriptor of temporal
organization in financial return dynamics.
   Comparison with filtered stochastic volatility estimates shows that persistence-
landscape norms and volatility encode related but distinct information. Dur-
ing high stress regimes, the two quantities tend to co-move, reflecting the
joint presence of large fluctuations and pronounced geometric structure in
delay space. However, the strength and stability of this relationship differ
across markets. In Bitcoin, the topology-volatility coupling is more unsta-
ble and exhibits a clearer regime shift, with periods in which the topological
signal persists or fluctuates even as volatility contracts. In the S&P 500,
the coupling is more consistently positive, especially during the COVID-19
crash and the 2022 equity-market stress regime, but the relationship remains
time-varying and the topological signal displays localized bursts that are not
identical to the smoother filtered volatility process.
   For Bitcoin, the residual analysis further shows that temporal structure
remains in the topological signal after accounting for stochastic volatility and
coarse sentiment variation. This indicates that the norm of the persistence
landscape is not fully explained by conventional scale-based measures or by
broad sentiment effects. More generally, the rolling correlation analyses for
both Bitcoin and the S&P 500 show that the dependence between topology
and volatility is regime-dependent rather than fixed over time.
   Surrogate-based null models provide statistical validation of these obser-
vations. Rejection of shuffle surrogates demonstrates that the persistence-
landscape norm depends on temporal ordering and is not determined solely
by the marginal distribution of returns. Departures from FFT phase-randomized
surrogates further indicate sensitivity to nonlinear and phase dependent tem-
poral organization beyond linear second order structure. The S&P 500 ap-
plication confirms that these surrogate-null departures are not restricted to
24                                S. W. AKINGBADE

cryptocurrency data, while also showing that the direction and strength of
the departures can differ between the two markets. Thus, the framework
detects both common and market-specific forms of temporal organization.
   Overall, the results show that nontrivial geometric structure can persist
in financial returns even after accounting for volatility, and, in the Bitcoin
case, sentiment effects. The topological framework therefore offers a princi-
pled approach for detecting regime-dependent organization in financial time
series and for distinguishing topological structure arising from marginal dis-
tributions, linear dependence, and higher-order temporal dynamics.
   Several directions remain for future work. A systematic cross-asset study
involving additional equity indices, individual equities, fixed income instru-
ments, commodities, and foreign exchange markets would help clarify how
topology-volatility coupling varies across market structures and time scales.
From a methodological perspective, future work may incorporate more re-
strictive surrogate constructions, such as iterated amplitude adjusted Fourier
transform surrogates, to further disentangle nonlinear temporal structure
from linear dependence and marginal distribution effects. It would also
be useful to investigate the mechanisms driving pronounced peaks in per-
sistence landscape norms and to study whether these topological signatures
have predictive value for regime shifts, market stress, or changes in volatility
dynamics.

                               Data availability
   Bitcoin and S&P 500 price data used in this study are publicly available
from Yahoo Finance. The Crypto Fear & Greed Index data used in the
Bitcoin sentiment analysis are publicly available from alternative.me.

                   Declaration of competing interest
  The author declares that there are no known competing financial interests
or personal relationships that could have appeared to influence the work
reported in this paper.

                              Acknowledgement
     The author thanks Marian Gidea for helpful discussions.

                                   References
 [1] Tiago Pereira, Alex Carvalho, Lilo Wahl, and Jürgen Kurths. Persistent homology
     of time-dependent functional networks constructed from coupled time series. Chaos:
     An Interdisciplinary Journal of Nonlinear Science, 28(3):033103, 2018.
 [2] Floris Takens. Detecting strange attractors in turbulence. In David Rand and Lai-
     Sang Young, editors, Dynamical Systems and Turbulence, Warwick 1980, pages 366–
     381, Berlin, Heidelberg, 1981. Springer Berlin Heidelberg.
 [3] Jose A Perea and John Harer. Sliding windows and persistence: An application of
     topological methods to signal analysis. Foundations of Computational Mathematics,
     15(3):799–838, 2015.
NULL-VALIDATED TOPOLOGICAL SIGNATURES OF FINANCIAL MARKET DYNAMICS
                                                                25

 [4] Marian Gidea and Yuri Katz. Topological data analysis of financial time series: Land-
     scapes of crashes. Physica A: Statistical Mechanics and its Applications, 491:820–834,
     2018.
 [5] Samuel W. Akingbade, Marian Gidea, Matteo Manzi, and Vahid Nateghi. Why topo-
     logical data analysis detects financial bubbles? Communications in Nonlinear Science
     and Numerical Simulation, 2024.
 [6] Marian Gidea, Daniel Goldsmith, Yuri Katz, Pablo Roldan, and Yonah Shmalo. Topo-
     logical recognition of critical transitions in time series of cryptocurrencies. Physica
     A: Statistical Mechanics and its Applications, 548:123843, 2020.
 [7] Stelios Arvanitis and Michalis Detsis. Mild explocivity, persistent homology and cryp-
     tocurrencies’ bubbles: An empirical exercise. AIMS Mathematics, 9(1):896–917, 2024.
 [8] Mohd Sabri Ismail, Mohd Salmi Md Noorani, Munira Ismail, Fatimah Abdul Razak,
     and Mohd Almie Alias. Early warning signals of financial crises using persistent ho-
     mology. Physica A: Statistical Mechanics and its Applications, 586:126459, 2021.
 [9] Marian Gidea. Topological data analysis of critical transitions in financial networks.
     In International conference and school on network science, pages 47–59. Springer,
     2017.
[10] Anubha Goel, Puneet Pasricha, and Juho Kanniainen. Risk reduced sparse index
     tracking portfolio: A topological data analysis approach. Omega, 138:103432, 2026.
[11] Anubha Goel, Damir Filipović, and Puneet Pasricha. Sparse portfolio selection via
     topological data analysis based clustering. Quantitative Finance, 25(8):1261–1291,
     2025.
[12] Rodrigo Rivera-Castro, Polina Pilyugina, and Evgeny Burnaev. Topological data
     analysis for portfolio management of cryptocurrencies. In 2019 International Con-
     ference on Data Mining Workshops (ICDMW), pages 238–243. IEEE, 2019.
[13] P. Saengduean, S. Noisagool, and F. Chamchod. Topological data analysis for iden-
     tifying critical transitions in cryptocurrency time series. In 2020 IEEE International
     Conference on Industrial Engineering and Engineering Management (IEEM), pages
     933–938, 2020.
[14] Jian Yao, Jingyan Li, Jie Wu, Mengxi Yang, and Xiaoxi Wang. Change point detection
     in financial market using topological data analysis. Systems, 13(10):875, 2025.
[15] Simon Rudkin, Wanling Qiu, and Pawel Dlotko. Uncertainty, volatility and the per-
     sistence norms of financial time series. arXiv preprint arXiv:2110.00098, 2021.
[16] Hugo Gobato Souto. Topological tail dependence: Evidence from forecasting realized
     volatility. The Journal of Finance and Data Science, 9:100107, 2023.
[17] Akylas Fotiadis, Ioannis Vlachos, and Dimitris Kugiumtzis. Detecting nonlinear in-
     teractions in complex systems: Application in financial markets. Entropy, 25(2):370,
     2023.
[18] Omer Bobrowski and Primož Skraba. A universal null-distribution for topological
     data analysis. Scientific Reports, 13:12274, 2023.
[19] Bernadette J. Stolz, Heather A. Harrington, and Mason A. Porter. Persistent ho-
     mology of time-dependent functional networks constructed from coupled time series.
     Chaos: An Interdisciplinary Journal of Nonlinear Science, 27(4):047410, 2017.
[20] Brahim Gaies, Mohamed Sahbi Nakhli, Jean-Michel Sahut, and Denis Schweizer.
     Interactions between investors’ fear and greed sentiment and bitcoin prices. The North
     American Journal of Economics and Finance, 67:101924, 2023.
[21] Mengxi He, Lihua Shen, Yaojie Zhang, and Yi Zhang. Predicting cryptocurrency
     returns for real-world investments: A daily updated and accessible predictor. Finance
     Research Letters, 58:104406, 2023.
[22] Jying-Nan Wang, Hung-Chun Liu, and Yuan-Teng Hsu. A u-shaped relationship be-
     tween the crypto fear-greed index and the price synchronicity of cryptocurrencies.
     Finance Research Letters, 59:104763, 2024.
26                                  S. W. AKINGBADE

[23] Herbert Edelsbrunner and John L Harer. Computational topology: an introduction.
     American Mathematical Society, 2022.
[24] Peter Bubenik et al. Statistical topological data analysis using persistence landscapes.
     J. Mach. Learn. Res., 16(1):77–102, 2015.
[25] Peter Bubenik and Pawel Dlotko. A persistence landscapes toolbox for topological
     statistics. Journal of Symbolic Computation, 78:91–114, 2017.
[26] Peter Bubenik. The persistence landscape and some of its properties. In Nils A.
     Baas, Gunnar Carlsson, Gereon Quick, Markus Szymik, and Marius Thaule, editors,
     Topological Data Analysis: The Abel Symposium 2018, volume 15 of Abel Symposia,
     pages 97–117. Springer, Cham, 2020.
[27] Afra Zomorodian and Gunnar Carlsson. Computing persistent homology. Discrete &
     Computational Geometry, 33(2):249–274, 2005.
[28] Samuel W. Akingbade. Applications of dynamical systems in dissipative me-
     chanics and in topological data analysis. PhD thesis, Yeshiva University,
     https://hdl.handle.net/20.500.12202/10344, 2024.
[29] Sauer Tim, A Yorke James, and Casdagli Martin. Embedology. Journal of Statistical
     Physics, 65(3-4):579–616, 1991.
[30] Yahoo finance. https://finance.yahoo.com/. Accessed December, 2025.
[31] Stephen J. Taylor. Modelling Financial Time Series. John Wiley & Sons, Chichester,
     1986.
[32] Andrew C. Harvey, Esther Ruiz, and Neil Shephard. Multivariate stochastic variance
     models. Review of Economic Studies, 61(2):247–264, 1994.
[33] Sangjoon Kim, Neil Shephard, and Siddhartha Chib. Stochastic volatility: Likelihood
     inference and comparison with arch models. Review of Economic Studies, 65(3):361–
     393, 1998.
[34] Neil Shephard. Statistical aspects of arch and stochastic volatility. In D. R. Cox, D. V.
     Hinkley, and O. E. Barndorff-Nielsen, editors, Time Series Models in Econometrics,
     Finance and Other Fields, pages 1–67. Chapman & Hall, 1996.
[35] John Hull and Alan White. The pricing of options on assets with stochastic volatilities.
     The Journal of Finance, 42(2):281–300, 1987.
[36] Edward L. Ionides, Anindya Bhadra, Yves Atchadé, and Aaron A. King. Iterated
     filtering. Annals of Statistics, 39(3):1776–1802, 2011.
[37] Aaron A. King, Dao Nguyen, and Edward L. Ionides. Statistical inference for partially
     observed markov processes via the R package pomp. Journal of Statistical Software,
     69(12):1–43, 2016.
[38] Alternative.me. https://alternative.me/crypto/api/. Accessed December, 2025.
[39] Thomas Schreiber and Andreas Schmitz. Surrogate time series. Physica D: Nonlinear
     Phenomena, 142(3–4):346–382, 2000.
[40] James Theiler, Stephen Eubank, André Longtin, Bryan Galdrikian, and J. Doyne
     Farmer. Testing for nonlinearity in time series: The method of surrogate data. Physica
     D: Nonlinear Phenomena, 58(1–4):77–94, 1992.

     Department of Mathematics, University of Michigan, Ann Arbor, MI, USA.
     Email address: sakingba@umich.edu
     Email address: sakingba@mail.yu.edu (permanent)