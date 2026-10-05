source: https://arxiv.org/pdf/2110.11848
fetched_utc: 2026-10-04T18:39:01Z
bytes_raw: 15342307

CLUSTERING MARKET REGIMES USING THE WASSERSTEIN
                                                                     DISTANCE

                                                                    B. HORVATH1,3,4 , Z. ISSA1 , AND A. MUGURUZA2




                                                   Abstract. The problem of rapid and automated detection of distinct market regimes
                                                   is a topic of great interest to financial mathematicians and practitioners alike. In this
                                                   paper, we outline an unsupervised learning algorithm for clustering financial time-series
                                                   into a suitable number of temporal segments (market regimes). As a special case of the
                                                   above, we develop a robust algorithm that automates the process of classifying mar-
arXiv:2110.11848v1 [q-fin.CP] 22 Oct 2021




                                                   ket regimes. The method is robust in the sense that it does not depend on modelling
                                                   assumptions of the underlying time series as our experiments with real datasets show.
                                                   This method – dubbed the Wasserstein k-means algorithm – frames such a problem
                                                   as one on the space of probability measures with finite pth moment, in terms of the
                                                   p-Wasserstein distance between (empirical) distributions. We compare our WK-means
                                                   approach with a more traditional clustering algorithms by studying the so-called max-
                                                   imum mean discrepancy scores between, and within clusters. In both cases it is shown
                                                   that the WK-means algorithm vastly outperforms all considered competitor approaches.
                                                   We demonstrate the performance of all approaches both in a controlled environment on
                                                   synthetic data, and on real data.


                                                                                        Contents
                                              1. Introduction                                                                                  2
                                              1.1. The market regime clustering problem                                                        3
                                              1.2. Motivation for using Wp                                                                      4
                                              1.3. Problem setting and notation                                                                 5
                                              1.4. The k-means algorithm                                                                        6
                                              1.5. The maximum mean discrepancy                                                                 7
                                              2. k-means on the space of distributions                                                         8
                                              3. Methodology and numerical results                                                             11
                                              3.1. Alternative clustering algorithms as benchmarks                                             11
                                              3.2. Validation on real data                                                                     13
                                              3.3. Validation on synthetic data                                                                18
                                              3.4. Selection of hyperparameters                                                                25
                                              4. Conclusion                                                                                    27
                                              Appendix A. The k-means algorithm                                                                29
                                              Appendix B. The maximum mean discrepancy                                                         30
                                              Appendix C. The Wasserstein distance                                                             33
                                              1
                                                King’s College, London, zacharia.issa@kcl.ac.uk. 2 Imperial College London and Kaiju
                                            Capital Management, aitor.muguruza-gonzalez@kcm.vg. 3 TU Munich, blanka.horvath@tum.de.
                                            4
                                              Alan Turing Institute.
                                               Date: October 25, 2021.
                                                                                              1
           CLUSTERING MARKET REGIMES USING THE WASSERSTEIN DISTANCE                         2

  References                                                                              35




                                   1.   Introduction
Time series data derived from asset returns are known to exhibit certain properties,
termed stylised facts, that are ubiquitous across asset classes. For example, it is well-
understood that return series are non-stationary in the strong sense, and exhibit volatility
clustering (for a full recount, see [Con01]). In particular, understanding the heteroskedas-
tic nature of financial time series data is relevant for market practitioners. An observed
sequence of asset returns (or, for multiple assets, a tuple of sequences) exhibits periods
of similar behaviour, followed by potentially distinct periods that indicate a significantly
different underlying distribution. Such periods are often referred to as market regimes.
Our interest in swiftly and accurately detecting changes in market regimes is motivated
by a multitude of financial applications (both classical and modern): Most naturally,
an accurate detection of shifts in market behaviour is tantamount for making optimised
investment decisions or trading strategies. But also within the arena of recent, deep
learning-based methods for pricing hedging and market generation [HMT19, BHL+ 20],
the detection of significant shifts in market behaviour is a central tool for their model
governance, since it serves as an indicator for the need to retrain the ML-model. Hence-
forth, we call the task of finding an effective way of grouping different regimes the market
regime clustering problem (MRCP).
In this paper, we propose a methodology to classify segments of the historical evolution
of market returns into distinct regimes. We do so by devising a modified, versatile version
of the classical k-means clustering algorithm to group distributions of asset returns into
regimes, which exhibit a higher degree of homogeneity. The way modify the classical
algorithm is twofold: Firstly, by a shift of perspective, we consider the clustering problem
as one on the space of distributions with finite pth moment, as opposed to one on Euclidean
space. Secondly, our choice of metric on this space is the pth Wasserstein distance, and we
aggregate nearest neighbours using the associated Wasserstein barycenter. We motivate
why the Wasserstein distance is the natural choice for this particular problem in Section
1.2. Accordingly in later sections we also present different numerical setups to demonstrate
how to navigate how reactive/robust the algorithm is on different datasets. The latter
will depend on the precise application at hand and the modellers appetite for more swift
or more robust indicators.
We benchmark our results with two alternative approaches. The first applies the classical
k-means algorithm to the first p moments associated to each segment of market returns.
The second is a more classical approach: We implement a version of the hidden Markov
model (HMM) using appropriate modifications to make results comparable to ours. We
test each algorithm both on real and synthetic data. The success of the unsupervised
learning algorithms in the real data setting is evaluated using a marginal maximum mean
discrepancy (MMD) metric, a metric arising from a powerful two-sample test which has
experienced a notable rise in popularity in recent machine learning literature. Overall,
we show that our data-driven and non-parametric methodology accurately partitions
financial return series into distinct clusters which are both distinct from each other whilst
remaining internally self-similar, relative to a more naive approach based on moments or
HMMs, which we verify on synthetic parametric data as well as on historical time series,
            CLUSTERING MARKET REGIMES USING THE WASSERSTEIN DISTANCE                          3

where our algorithm correctly identifies all (now historically known) periods of unusual
market activity as they arise.

1.1. The market regime clustering problem. Let us start by giving an overview
of related literature and existing insights on the MRCP. Recall that the MRCP is defined
as the task of classifying segments of return series (ri )i≥0 , where
                                 ri = (ri1 , . . . , rin ) for n ∈ N.
Any vector ri ∈ Rn can be associated to an empirical measure δri = n1 nj=1 δrj for i ≥ 0
                                                                         P
                                                                                 i
with n atoms. Thus, the problem of classifying market regimes is equivalent to assigning
labels to probability measures µ ∈ Pp (R), where Pp (R) is the set of probability measures
on R with finite pth moment.
Historically, approaches to solving the MRCP vary depending on their applications: for
instance, a modeller may be interested in regime classification over different time scales:
from microseconds, to months or years. Further variations may come according to the
modeller’s choice of framing the problem; for example, one may wish to segment regimes
via change points detection methods, which are place (as the name sugests) emphasis
on change-points rather than on the regimes themselves (see [NHZ16] for an overview).
Another example is the more general outlier detection problem [CFLA20, KSH20], which
is a special one-class case of the MRCP. Those studying such a problem are often more
interested in identifying anomalous datum, as opposed to characterising the distribution
µ ∈ P(R) such datum are generated from.
Some of the early attempts at analysing financial return series to extract regime switching
signals fall under the umbrella of technical analysis, where signals such as temporal moving
average crossovers and support level breaches are used as indicators for a regime change for
a particular financial asset or a collection of assets, see Achelis [Ach01] for a comprehensive
guide. More rigorous statistical analyses of financial time series have also been employed
to detect regime changes. A classical approach is performing dynamic PCA on inter-asset
covariance matrices, see Pelletier [Pel06] for an example on high-dimensional synthetic
Markovian asset price paths.
Another classical approach to the MRCP is via Markovian switching models and HMMs.
To the author’s knowledge, this technique was introduced in the work of Hamilton
[Ham89], in which the state term signifying the regime is given by an AR(1) process. For
a more detailed history of the Markov switching model, we refer the reader to [Kua02]
and to [LR09], [Gui11] for their use in empirical finance. The hidden Markov model ap-
proach is not altogether model-free as it makes two main assumptions: first, the latent
state variable specifying the current regime is Markovian, and secondly, that the likeli-
hood of observing a return given the latent state variable is given by some parametric
distribution, often Gaussian. Other approaches include agent-based models as shown in
Lux and Marchesi [LM00], Bayesian approaches as seen in Maheu, Thomas and Song
[MMS12], or more data-driven approaches as seen in Lahmiri [Lah16].
Previous work on the problem of clustering families of distributions via non-parametric
unsupervised learning approaches has been found in Nielson, Nock and Amari [NNA14],
where a modification of the classical kmeans algorithm is used to cluster histograms via
mixed α-divergences. An approach to empirical distribution clustering via k-means is
also given in Henderson, Gallagher and Eliassi-Rad [HGER15] in a non-financial context.
Other works have utilised the Wasserstein distance for clustering problems, see for in-
stance [LW08, YWWL17], where in the latter distributions are represented as weight-mass
             CLUSTERING MARKET REGIMES USING THE WASSERSTEIN DISTANCE                                     4

pairs, and clustering is considered in the context of images and documents, or [MZGW18]
for an approach using variational optimal transport. Such approaches are similar to the
work in this paper as they often employ classic unsupervised learning algorithms with
some modification that allows them to handle distributional datum. Our approach seeks
to meld the financial regime-switching and clustering worlds together in an attempt to
provide a robust, non-parametric approach to a posteriori market regime clustering.
1.2. Motivation for using Wp . In this section, we motivate our perspective on the
clustering problem and the choice of the Wasserstein metric (14) for this purpose, which
has recently seen a swift rise in artificial intelligence and machine learning, see for instance
[NSW+ 20].
Given that our clustering problem is defined over the space of probability measures Pp (R),
there exist many candidate one could employ: classical choices include the Kolmogorov-
Smirnov statistic or the Kullback-Leibler (KL)-divergence. We argue that either of these
choices are inadequate for the given problem statement. It is well known that the Kolmogorov-
Smirnov statistic lacks the sensitivity required to distinguish between elements of the
clustering set (see [MS83]). The KL-divergence has been employed in the literature as a
distance function within a clustering algorithm see [ABS08] for a k-medians implementa-
tion with generalised Bregman divergences, and [NNA14] for general α-divergences. We
note that our clustering problem is over empirical measures and thus requires an estima-
tion of the probability density function associated to each measure if the KL-divergence
is to be employed. Barycenters with respect to the symmetrized and non-symmetrized
versions of the KL-divergence have been shown to exist ([Vel02]), and [NN09] for more
general Bregman divergences), however these rely on algorithmic derivations. We argue
that our approach is much simpler, elegant and scalable when compared to the alterna-
tives.
The Wasserstein distance is a natural choice for comparing distributions of points on a
metric space (X, d). The distance function d appears in the expression (14) characterising
the distance and furthermore, the Wasserstein distance metrizes weak convergence1. Thus,
measures that are close in the Wasserstein sense are also close in the classical narrow sense
as well.
In our examples we focus on the univariate case d = 1, since computing the Wasserstein
distance in between empirical measures is particularly tractable, though a multivariate
characterisation of our results is also possible (see next paragraph). From Proposition 2.5,
the algorithm to compute the p-Wasserstein distance between two empirical measures
with N atoms is O(N log N ). It is important to note that other comparative distances
share this property. However, the Wasserstein distance also has a natural aggregator
candidate in the Wasserstein barycenter, which is fast to calculate in the case where
d = 1. Other comparative distances either do not have a natural candidate for aggregation
(Kolmogorov-Smirnov) or a canonical aggregator which is tractable to calculate (KL-
divergence).
In the case where d > 1, the Wasserstein distance is also viable as a choice of metric
on Pp (Rd ). Although Wp has shown to be an effective tool to tackle the curse of dimen-
sionality associated to sequences on R, it becomes computationally too demanding to
solve when extending to higher-dimensional data ([RPDB11], Section 2.2). Recently, the
sliced Wasserstein distance Wp as seen in [RPDB11], [BRPP15] and [KNS+ 19] has been
1A sequence (µ )
                 n n≥1 ⊂ Pp (X) converges weakly to µ ∈ Pp (X) iff Wp (µn , µ) → 0 as n → ∞. Moreover,
if (X, d) is a Polish space, then (Pp (X), Wp ) is also Polish (see [AG13], Theorem 2.6 for the case p = 2).
             CLUSTERING MARKET REGIMES USING THE WASSERSTEIN DISTANCE                           5

employed to extend the Wp to Rd . It does this by projecting distributions µ, ν ∈ Pp (Rd )
onto R via points on the unit sphere in Rd , and returns the expected one-dimensional
Wasserstein distance of such projections. This turns the complex problem of calculating
Wp (µ, ν) into an O(M N log N ) operation, where M is the number of points taken. Re-
cently, Bayraktar and Guo [BG21] showed that the max sliced Wasserstein metric W p is
strongly equivalent to the classical Wasserstein distance in the cases p = 1, 2.2

1.3. Problem setting and notation. We begin by giving an overview of the problem
setting. First, we introduce the notion of a data stream.

Definition 1.1 (Set of data streams, [BKA+ 19], Definition 2.1). Let X be a non-empty
set. The set of streams of data S over X is given by
(1)                       S(X ) = {x = (x1 , . . . , xn ) : xi ∈ X , n ∈ N}.

In this paper, we take X = R and fix N ∈ N. In the context of the MRCP, elements
S = (s0 , . . . , sN ) ∈ S(R) will be price paths associated to a financial asset.
Given S ∈ S(R), we define the vector of log-returns rS associated to S by
(2)                     riS = log(si+1 ) − log(si )           for 0 ≤ i ≤ N − 1,
      S
so r ∈ S(R). We use the following expression to highlight that we may to wish partition
the original stream of data (2) into potentially overlapping segments equal length.

Definition 1.2 (Stream lift, [BKA+ 19], Section 3.3). Let S(X ) be a space of streams
over a non-empty set X . Let V be another non-empty set, and let v ≥ 1. We call a
function
                             ` = (`1 , . . . , `v ) : S(X ) → S(S(V))
a lift from the space of streams to the space of streams of segments over V.

Thus, for x ∈ S(R) and h1 , h2 ∈ N with h1 > h2 , we define a lift ` := `h1 ,h2 from S(R) to
S(S(R)) via
(3)              `i (x) = (x1+h2 (i−1) , . . . , x1+h1 +h2 (i−1) )   for i = 1, . . . , M,
where M := b h1N−h2
                    c is the maximum number of partitions with length h1 that can be
extracted from x ∈ S(R) with sliding window offset parameter h2 . We obtain the stream
of segments by applying ` to rS .
Finally, as stated in the introduction, the main idea of this paper is to lift the regime
clustering problem from one on Euclidean space to one on the space of probability dis-
tributions with finite pth moment with p > 1. This requires defining a family of measures
via the map `(rS ).

Definition 1.3 (Empirical measure, [GBC16], Section 3.9.5). Let x ∈ S(R) such that
x = (x1 , . . . , xN ) for N ∈ N. Furthermore, let
                                             Qj : S(R) → R
be the function which extracts the j th order statistic of x, for j = 1, . . . , N . Then, the
cumulative distribution function of the empirical measure µ ∈ Pp (R) associated to x is

2The authors would like to thank Claude Martini and Frédéric Patras for informing us of this.
             CLUSTERING MARKET REGIMES USING THE WASSERSTEIN DISTANCE                            6

defined as
                                                      N
                                x           1 X
(4)                           µ ((−∞, x]) =       χ{Qi (x)≤x} (x),
                                            N i=1
where χ : R → [0, 1] is the indicator function.

Thus, we can associate to each segment of data ri ∈ `(rS ) the empirical measure µi for
i = 1, . . . , M . This gives us a family of measures
(5)                  K = {(µ1 , . . . , µM ) : µi ∈ Pp (R) for i = 1, . . . , M } .
It is this family K which will be the subject of our clustering algorithm.
1.4. The k-means algorithm. Suppose X = {(x1 , . . . , xN ) : xi ∈ V } ∈ S(V ) is
a stream of data over a normed vector space (V, k·kV ). We further assume that each
xi = (xi1 , . . . , xid ) has been standardised coordinate-wise, that is,
(6)           E[{xij }1≤i≤N ] = 0 and Var({xij }1≤i≤N ) = 1            for j = 1, . . . , d.
The k-means clustering algorithm is a unsupervised vector quantization method which
assigns elements of X to k distinct clusters. Each of these clusters are defined by central
elements x := {xj }j=1,...,k called centroids, which are initially sampled from X.
At each step n ∈ N of the algorithm, one first calculates the nearest neighbours
                                                              
                         n                             n−1
(7)                     Cl := xi ∈ X : arg min d(xi , xj ) = l
                                                j=1,...,k

associated to each xn−1
                    j   for j = 1, . . . , k, where d : V × V      → [0, +∞) is the metric induced
by the norm on V .

Remark 1.4. Classically, one chooses (V, k·kV ) = (Rd , k·kRd ), but we note here that any
normed vector space could be chosen.

Each set Cln is then aggregated into a new centroid xnl for l = 1, . . . , k via a function
α : 2V → V , so
                            xnl := α(Cln ) for l = 1, . . . , k.
For a given a tolerance level ε > 0 and a loss function l : V k ×V k → [0, +∞), the k-means
algorithm terminates at step n ∈ N if the stopping condition
                                           l(xn , xn−1 ) < ε
is satisfied. The algorithm outputs the final clusters C ∗ = {Cln }l=1,...,k and the k quantiza-
tions xn = {xnl }l=1,...,k . We conclude this section with the assumptions associated to the
k-means algorithm that, if satisfied, will result in uniform and isotropic clustering of a
data set X.

Proposition 1.5 ([KMN+ 02]). Given data X, the k-means algorithm produces k suitable
clusters if the following is true:
      1. There exist k natural clusters in the data X.
      2. Each cluster within X is of roughly equal size.
      3. Within-cluster variation (cf. Definition A.2) is uniform. That is, for δ2 > 0 small
         we have that
                  WC(Ci ) − WC(Cj )| < δ2            for i, j = 1, . . . , k and i 6= j,
             CLUSTERING MARKET REGIMES USING THE WASSERSTEIN DISTANCE                              7

      4. Clusters are spherical in shape, so we expect the nearest neighbours Cj to the j th
         centroid xj to be contained within a ball B(xj , δ) where δ > 0 is uniform across all
         clusters j = 1, . . . , k.
If conditions (1)-(4) are satisfied, then optimal clusterings C ∗ will be suitable.

Counterexamples to suitability include forcing k clusters on data with fewer than k natural
clusters available. Another classical example is the problem of clustering concentric data
X ⊂ R2 , which violates assumption (4) in Proposition 1.5. We note that do exist other
clustering algorithms which do not share the drawbacks of k-means, in that they do not
make assumptions regarding the number or shape of the clusters (hierarchical clustering),
nor do they enforce that data points xi belong to one individual cluster (fuzzy c-means
clustering, see for instance [CDB86]). Exploring other clustering algorithms for the MRCP
is a topic for future research.

1.5. The maximum mean discrepancy. Evaluating derived k-means clusters on
a stream of data S(X ) is typically done by evaluating the final total cluster variation
TC(C ∗ ) or inertia (cf. Definition A.3). Here, C ∗ are the final clusters obtained from a
given run of the k-means algorithm. Naturally the value of TC(C ∗ ) is dependent on the
normed vector space (V1 , k·kV1 ) one decides to cluster the steam of data X on (assuming
it is feasible, a natural choice may be V1 = X ). Of course one could make a different
choice (V2 , k·kV2 ) by transforming sets of datum A ⊂ S(X ), see Section 3.1. Since the
total cluster variation depends on V , one cannot use it in evaluation between clusterings
on different choices of V .
In this section, we outline an integrable probability metric on the space of distributions
called the maximum mean discrepancy (MMD), which will be used as part of a robust
methodology for confirming goodness-of-fit of clustered market regimes. The MMD has
been shown to be a robust estimator under both dependence and presence of outliers
[CAA21] and has been employed frequently in the quantitative finance and machine
learning literature, see [BHL+ 20], [ACADF20], [BBDG19].
We provide a brief introduction here and refer the reader to the literature [GBR+ 12],
[GBR+ 07], [GFHS09] for further details. We begin by introducing the following.

Problem 1.6 (Two-sample test, [GBR+ 12], Problem 1). Let (X , d) be a metric space.
Suppose X and Y are independent random variables defined on X . Suppose that X# P = µ
and Y# P = ν, where µ, ν ∈ P(X ) are Borel. If we draw samples x = (x1 , . . . , xn ) and
y = (y1 , . . . , ym ) where xi ∼ µ for i = 1, . . . , n and yj ∼ ν for j = 1, . . . , m, when can we
determine if µ 6= ν? That is, we wish to implement a test for the two-sample problem
(8)                              H0 : µ = ν against H1 : µ 6= ν.

We introduce the following test statistic associated to Problem 1.6.

Definition 1.7 (Maximum mean discrepancy, [GBR+ 12], Definition 2). Let F be a class
of functions f : X → R and let µ, ν be defined as in Problem 1.6. Then, the maximum
mean discrepancy (MMD) between µ and ν is defined as
                                                              !
(9)                     MMD[F, µ, ν] := sup Eµ [f (x)] − Eν [f (y)] .
                                            f ∈F
                CLUSTERING MARKET REGIMES USING THE WASSERSTEIN DISTANCE                        8

If x = (x1 , . . . , xn ) and y = (y1 , . . . , ym ) are samples where xi ∼ µ and yj ∼ ν, then a
biased empirical estimate of the MMD is given by
                                                    " n                 m
                                                                                   #
                                                      1X             1 X
(10)                     MMDb [F, x, y] := sup             f (xi ) −       f (yj )
                                                f ∈F n i=1           m j=1

Clearly, the value of the MMD between two measures is determined by the function
class F one decides to calculate the supremum in (9) over; in particular, it is not even
guaranteed to be a metric. Often the MMD is employed in the context of studying mean
differences between datum in a typically higher-dimensional feature space. This motivates
the use of kernel methods to define F, which is often chosen to be the unit ball in a
reproducing kernel Hilbert space (RKHS) (H, κ), where κ : X × X → R is the associated
reproducing kernel. That the MMD is a metric depends on the associated kernel κ being
universal (cf. Definition B.3) if X is compact. If X is non-compact, the following property
is enough to guarantee that this is the case.

Definition 1.8 (Characteristic kernel, [FGSS09], Section 2). Let X be a non-empty set.
A kernel κ on X is called characteristic if the mean mapping
(11)                                  µ 7→ EX∼µ [κ(·, X)]
is injective.

The Gaussian kernel
(12)             κG : Rd × Rd → [0, +∞),       κG (x, y) = exp(− kx − yk2Rd /2σ 2 )
is characteristic to the set of Borel measures on X and indeed makes the MMD a metric
on P(X ). For more details we refer the reader to Theorem 2 in [FGSS07] or to Appendix
B, Theorem B.4 for more details.
We will use the MMD with F = (H, κG ) to validate how effective a given clustering
algorithm is in the case that we are unable to infer true regime labels, i.e., when we are
working with real data. A key notion to define how similar a collection of samples are to
each other is the following.

Definition 1.9 (Within-cluster self-similarity (homogeneity)). Let X ∈ S(X ) be a
stream of data with N observations. Let F be the unit ball in a universal RKHS H.
For n, m ∈ N, we define the self-similarity score associated to X to be
                     Sim(X) = Median (MMD2b [F, xi , yi ])1≤i≤n ,
                                                                 
(13)
where xi = (xi1 , . . . , xim ) and yi = (y1i , . . . , ym
                                                         i
                                                           ) are samples drawn pairwise from X for
i = 1, . . . , n.

Remark 1.10. The true self-similarity score is obtained by calculating the biased MMD
(53) for all unique combinations
                              of pairwise samples. For computational reasons, we often
                           N
calculate (13) from n << 2 iterations.

                       2.   k-means on the space of distributions
In this section, we outline our modification to the k-means algorithm which allows us to
cluster the set (5) directly on the space of probability measures with finite pth moment.
Central to this paper is the following distance metric on Pp (R).
           CLUSTERING MARKET REGIMES USING THE WASSERSTEIN DISTANCE                        9

Definition 2.1 (p-Wasserstein distance, [AGS05]). Suppose (X, d) is a separable Radon
space. The p-th Wasserstein distance between measures µ, ν ∈ Pp (X) is defined by
                                       ˆ                      
                      p                              p
(14)               Wp (µ, ν) := min           d(x, y) P(dx, dy) ,
                                  P∈Π(µ,ν)         X×X
where
          Π(µ, ν) := {P ∈ P(X × X) : P(A × X) = µ(A), P(X × B) = ν(B)}
is the set of transport plans between µ and ν.

The p-Wasserstein distance (14) is the solution to the Kantorovich-type optimal trans-
portation problem between measures µ and ν for the cost function c(x, y) = d(x, y)p .
For our applications, existence of an optimal plan P∗ ∈ Π(µ, ν) realising the Wasser-
stein distance between measures µ, ν ∈ P(R) is guaranteed by continuity of the metric
d(x, y) = |x − y|p and the fact that µ, ν will be empirical measures and thus posses
compact support. We refer the reader to [San15] for further details.

Remark 2.2 (Relationship to the MMD). The Wasserstein distance (14), via its equivalent
dual formulation, is a special case of an integral probability metric (see, for instance,
[WGX21], Definition 1). In the case where p = 1, the dual representation is given by
                                             ˆ              
(15)                     W1 (µ, ν) = sup          f d(µ − ν) ,
                                       f ∈Lip1 (X)       X

where Lip1 (X) denotes the space of continuous R-functions over X with Lipschitz con-
stant L ≤ 1. Since µ, ν are probability measures, we can write (15) as
                       W1 (µ, ν) =     sup        {Eµ [f (x)] − Eν [f (y)]} .
                                     kf kLip ≤1
                                           1

Thus W1 (µ, ν) is an integrable probability metric over the function class F, which is given
by the unit ball in the space of functions
                  Lip(X) = {f : X → R : f continuous, kf kLip < +∞},
where
                                                    |f (x) − f (y)|
                               kf kLip = sup                        .
                                               x6=y     d(x, y)

In what follows, we choose the p-Wasserstein distance to be our metric on Pp (R). As
explained in Section 1.2, this distance is natural and tractable to use on the space of
probability measures.
Our next decision we need to make is how we aggregate nearest neighbours Cl into central
elements µl ∈ Pp (R) for l = 1, . . . , k. One of the advantages of choosing the Wasserstein
distance Wp to be the metric we apply on our clustering space is the existence of the
following, which gives a natural way to “average” a family of measures under Wp .

Definition 2.3 (Wasserstein barycenter). Suppose (X, d) is a separable Radon space
and let K = {µi }i≥1 ⊂ P(X) be a family of Radon measures. Define the p-Wasserstein
barycenter µ of K to be
                                         X
(16)                        µ = arg min     Wp (µi , ν).
                                      ν∈P(X) µ ∈K
                                                    i
            CLUSTERING MARKET REGIMES USING THE WASSERSTEIN DISTANCE                         10

Remark 2.4. If {µi }i≥1 are a family of measures associated to a cluster Cl , l = 1, . . . , k,
then the Wasserstein barycenter (16) is the measure µ ∈ Pp (R) which minimises the
within-cluster variation WC(Cl ) from Definition A.2.

Since the k-means algorithm requires repeated evaluations of elements on clustering space
under the given metric, tractability of the non-linear optimisation (14) becomes relevant.
In the case where measures µ, ν ∈ P(R) are absolutely continuous, there exist a closed-
form solution to (14).

Proposition 2.5 ([KNS+ 19], Equation (3)). Suppose µ, ν ∈ Pp (Rd ) and let d = 1.
Moreover, suppose that µ, ν are absolutely continuous with respect to the Lebesgue measure
on R. Then, the p-Wasserstein distance W1 (µ, ν) is given by

                                     ˆ 1                               1/p
(17)                   Wp (µ, ν) =          |Fµ−1 (z) − Fν−1 (z)|p dz          ,
                                       0
where the quantile function Fµ−1 : [0, 1) → R is defined as
(18)                            Fµ−1 (z) = inf{x : Fµ (x) > z}.

Proof. A consequence of the fact that the (unique) optimal transport map pushing µ onto
ν is given by T (x) = (Fν−1 ◦ Fµ )(x), and applying a change of variables.           

In what follows, we assume that µ, ν are empirical measures with equal numbers of atoms
N ∈ N (this will be the case in our experimental setup). Recalling Definition 1.3, we may
write them as
                               N                                  N
                           1 X                                1 X
(19)        µ((−∞, x]) =          χα ≤x (x),   ν((−∞, x]) =         χβ ≤x (x)
                           N i=1 i                            N i=1 i
where (αi )1≤i≤N and (βi )1≤i≤N are increasing sequences corresponding to the atoms of
µ and ν. We wish to use (17) to obtain a closed-form expression for the Wasserstein
distance between the two measures. Thus, we must consider the well-posedness of (18):
every empirical measure on R is Radon, and thus one can associate to µ (ν) a right-
continuous function of finite variation At : R → [0, 1] given by At = µ ((−∞, t)) ([RY04],
Theorem 4.3). The function At possesses a right-continuous inverse which is nothing but
the quantile function from (18), which (in the case of µ) can be written as

                                                          
                                              i−1 i
(20)            Fµ−1 (z) = αi     for all z ∈    ,             ,    i = 1, . . . , N.
                                               N N

Moreover Fµ−1 (z) = 0 for all z < α1 . Applying (20) to (17), the Wasserstein distance
between the empirical measures µ and ν is given by
                                   N ˆ i
                                   X    N
                      Wp (µ, ν)p =         |Fµ−1 (z) − Fν−1 (z)|p dz
                                                i−1
                                      i=1        N
                                            N
                                     1 X
(21)                               =       |αi − βi |p .
                                     N i=1
           CLUSTERING MARKET REGIMES USING THE WASSERSTEIN DISTANCE                     11

Thus, calculating the Wasserstein distance between two empirical measures can be done
in linear time, assuming the atoms of each measure are already sorted ascending. If not,
calculating (21) is an O(N log N ) operation, where N is the number of atoms. This
representation also makes calculating the Wasserstein barycenter (16) simple in the case
where p = 1 and some assumptions are made on the number of atoms present in each
measure.

Proposition 2.6 (Wasserstein barycenter, empirical measures). Suppose that {µi }1≤i≤M
are a family of empirical probability measures, each with N atoms (αji )1≤j≤N ⊂ RN . Let
                     aj = Median(αj1 , . . . , αjM )        for j = 1, . . . , N.
Then, the cumulative distribution function of the Wasserstein barycenter µ ∈ P1 (R) over
{µi }1≤i≤M with respect to the 1-Wasserstein distance is given by
                                                       N
                                            1 X
(22)                          µ ((−∞, x]) =      χa ≤x (x).
                                            N i=1 i
Moreover, µ is not necessarily unique.

Proof. See Appendix C.1.                                                                

The last specification we need to make is regarding the loss function. We do this in the
natural way by replacing the squared Euclidean distance in standard k-means by the
p-Wasserstein distance. Let µn = (µni )1≤i≤k be the centroids obtained after step n of
the Wasserstein k-means algorithm. Therefore, our loss function l : Pp (R)k × Pp (R)k →
[0, +∞) is given by
                                                k
                                                X
(23)                          l(µn−1 , µn ) =         Wp (µin−1 , µni ).
                                                i=1
Our stopping rule is unchanged; that is, for a given ε > 0 we terminate the algorithm at
step n if l(µn−1 , µn ) < ε. We give a full statement of the algorithm with the following.

Definition 2.7 (WK-means algorithm). Let K ⊂ Pp (R) be a family of measures with
finite pth moment. We refer to the k-means clustering algorithm on (Pp (R), Wp ), with
aggregation method given by the Wasserstein barycenter from Definition 2.3 and loss
function given by (23) as the Wasserstein k-means algorithm, or WK-means.

We summarize with Algorithm 1.

                    3.   Methodology and numerical results
In this section, we cover the methods used to test the WK-means algorithm on stock data.
Initially, we test both algorithms on real data. Validation of each clustering algorithm
was conducted using the MMD test statistic (10). Finally, we tested both algorithms on
synthetic data generated via two different models: one where the associated log-returns
were distributed normally, and another where they were not.

3.1. Alternative clustering algorithms as benchmarks. I this section we seek
to benchmark our approach via two alternative algorithms. In this section, we briefly
introduce these methods.
            CLUSTERING MARKET REGIMES USING THE WASSERSTEIN DISTANCE                           12


 Algorithm 1: WK-means algorithm
  Result: k centroids
  calculate `(rS ) given S;
  define family of empirical distributions K = {µj }1≤j≤M ;
  initialise centroids µi , i = 1, . . . , k by sampling k times from K;
  while loss_function > tolerance do
      foreach µj do
         assign closest centroid wrt Wp to cluster Cl , l = 1, . . . , k;
      end
      update centroid i as the Wasserstein barycenter relative to Cl ;
      calculate loss_function;
  end


3.1.1. k-means with statistical moments. A natural and more classical approach to clus-
tering regimes may involve studying the first p ∈ N raw moments associated to each
measure µ ∈ K. With this in mind, consider the image of K from (5) under the function

                                                   ˆ          
                                  p            1         n
(24)                            ϕ (µ) =                 x µ(dx)            ,
                                               n!   R              1≤n≤p

which is the truncated unstandardised pth -moment map. As each µ ∈ K is a sum of Dirac
masses, each element of ϕp (µ) is finite. Thus, for a given p > 1 we obtain
(25)         ϕp (K) = {(ϕp (µ1 ), . . . , ϕp (µM )) : ϕp (µi ) ∈ Rp for i = 1, . . . , M } .

After standardising each element of ϕp (K) component-wise (cf. Remark 3.2), we obtain
a clustering set on Rp , which we can apply the standard k-means algorithm to. This
motivates the following definition.

Definition 3.1 (Moment k-means). Let K ⊂ Pp (R) be a family of measures. For p ≥ 1,
associate to each µi ∈ K the Rp -vector ϕp (µi ) for i = 1, . . . , M , where ϕp : Pp (R) → Rp
is the p-moment map from (24).
Then, moment k-means algorithm, or MK-means, is given by applying Algorithm 2 to
the stream of data ϕp (K) from (25). See Appendix A for more details.

Remark 3.2 (Magnitude of moments). The function ϕp defined in (24) outputs the first p
raw moments associated to a measure µ ∈ Pp (R). Often, moments that appear earlier in
the sequence (ϕp (µ)i )1≤i≤p will be of significantly larger magnitude than those that appear
later. In order for the k-means algorithm to not place undue emphasis on these moments,
it is critical that each slice {ϕp (µi )j }1≤i≤M is standardised according to equation (6) for
1 ≤ j ≤ p.

3.1.2. Hidden Markov model. As mentioned in Section 1.1, a more classical approach
to market regime clustering involves fitting a hidden Markov model (HMM) to observed
time series data x ∈ S(R), that there exist k ∈ N hidden latent states {1, . . . , k} which
govern the dynamics of x. The transition between the latent states is assumed Markovian,
and although they are not directly observable they are represented by a transition density
f (x | zl , θl ) where zl is the given latent state and θl are parameters associated to the state,
            CLUSTERING MARKET REGIMES USING THE WASSERSTEIN DISTANCE                        13

for l = 1, . . . , k, and the most common choice of likelihood is a Gaussian one. We refer
the reader to [DVR15] for more details.
As another point of comparison to our approach, we fit a Gaussian HMM in both our real
and synthetic data experiments. A main point of difference here is that the HMM does
not cluster sets of returns: instead, it associates returns at time t to a given latent state.
We thus can derive accuracy statistics in the case where we run the HMM over synthetic
data, but for real data our validation method using the MMD is not possible.

3.2. Validation on real data. In this section, we give results from each algorithm on
real data.

3.2.1. Data and hyperparameters. We begin by testing both algorithms on market data.
In particular, we use one-hourly log-returns rS ∈ S(R) associated to the SPY index from
2005-01-03 to 2020-12-31. Recalling Definition 1.2 and (3), we set the hyper-parameters
(h1 , h2 ) = (35, 28). This roughly partitions the time-series into weeks, with adjacent
partitions within one day of each other. We defer discussions regarding choices of hyper-
parameters to Section 3.4.
Regarding the number of clusters, we set k = 2. Primarily, this is for simplicity as it
makes comparisons between each methods simpler. Moreover, it also reflects a stylised
fact regarding financial markets, being that market returns can be roughly apportioned
into bull and bear cycles. We note that other values of k do have financial interpretations
- for instance, see Maheu, McCurdy and Song [MMS12].
We ran the two algorithms over the lifted steam of data `(rS ). For each algorithm, we
obtained centroids {µi }i=1,2 and the nearest neighbours {Cl }l=1,2 with Cl ⊂ Pp (R) being
the nearest neighbours corresponding to the lth centroid. In order to display our results,
we primarily use two plots. The first is the projection of each distribution µ ∈ K onto R2
via the map
                                     fp : Pp (R) → R2 ,
                                       p               
                                  µ 7→     Var(µ), E[µ] ,
that is, a scatter plot of each measure in mean-variance space. We colour these points
according to their centroid membership. Points coloured green correspond to the cluster
with lower variance than those coloured red. The second plot we make use of is a time-
series plot of stock values S, where each partition has been coloured corresponding to its
centroid membership. Given that the empirical distributions overlap, a given timestamp
may be classified into multiple clusters. Thus, we colour these points according to their
average centroid memberships. In the case of k = 2 with the hyperparameters (h1 , h2 ) =
(35, 28), a single return riS can potentially belong to 5 different empirical measures. Thus,
there are 6 total potential centroid membership combinations that it can have, and we
colour these sections of the price path accordingly.

3.2.2. Algorithm results. We first present the results of running either algorithm over
hourly SPY data. Figure 1 gives the scatter plots of each empirical measure µ ∈ K
coloured according to its cluster membership. The centroids are marked by crosses and
coloured accordingly.
From Figure 1b, we see that the WK-means classifications are much less susceptible to
outlier distributions than the MK-means algorithm. We also note that the Wasserstein
approach demarcates distributions µ ∈ K by variance, which one naturally expects in a
           CLUSTERING MARKET REGIMES USING THE WASSERSTEIN DISTANCE                        14




                (a) MK-means.                                 (b) WK-means.

       Figure 1. Plots of MK-means and WK-means clusters in mean-variance space.

financial market setting. Although Figure 1a appears to do the same, it is hard to state
this definitively as the clustering algorithm seems to primarily group outlier distributions.
This is made apparent in the graphs presented in Figure 2, where we have associated to
each µ ∈ K the partition of S ∈ S(R) it is generated from.




                (a) MK-means.                                 (b) WK-means.




                                  (c) Hidden Markov model.

                 Figure 2. Historical cluster colouring on SPY price path.

Figures 2a and 2b show that both algorithms are able to separately classify periods of
returns associated to the global financial crisis and the more recent market instability
due to the coronavirus pandemic. However, only the WK-means algorithm is able to
distinguish between more subtle periods of stock market volatility: the beginning of the
Eurozone/Greek debt crisis in 2010, the S&P US credit-rating downgrade in 2011, and
            CLUSTERING MARKET REGIMES USING THE WASSERSTEIN DISTANCE                           15

the 2015/16 Chinese stock market crash were tagged as periods of regime change only
by the WK-means algorithm. Note that we can include an example of a Hidden Markov
model run with this plot, in Figure 2c. We note that the results from this approach seem
to sit somewhere between the Wasserstein and moment algorithms.

3.2.3. Validation methods. In order to compare clusterings obtained from both algo-
rithms, we use the marginal MMD test introduced in Section 1.5. The two methods
of evaluation we consider are applied both between and within clusters C = {Cl }l=1,2 .
Moreover, both methods of evaluation are similar, in that they involve bootstrapping the
distribution of MMD2b between two sets of samples.
More generally, the definition of an optimal clustering over a set of data X is not well-
defined, and in the case of financial data, this is certainly true. Heuristically, we would like
individual clusters to contain objects that are similar to each other whilst being distinct
from objects in other clusters. We note that there do already exist several indexes used
to evaluate the result of a given k-means clustering, which we recall here.

Definition 3.3 (Davies-Bouldin index, [DB79]). Suppose (V, k·kV ) is a normed vector
space. Let {(xl , Cl )}kl=1 be k centroids and clusters over X ∈ S(X ), obtained by applying
the k-means algorithm characterised by the functions
                                          ϕ : X → V,
                                          a : 2V → V, and
                                   l : V K × V k → [0, +∞).
Suppose d : V × V → [0, +∞) is the metric induced by the norm on V . Let
                                      1 X
                                dl =           d(x, xl )
                                     |Cl | x∈C
                                                        l

be the average distance of cluster elements x ∈ Cl to the central element xl for l = 1, . . . , k.
Then, the Davies-Bouldin index is given by
                                           1X     k
                             
                                       k                      di + dj
(26)                    DB {(xl , Cl )}l=1 =          max                 .
                                               k i=1   j6 = i d(xi , xj )
Lower values of (26) are indicative of a better clustering.

Definition 3.4 (Dunn index, [Dun74]). With the same notation as Definition 3.3, define
                                      dij =     min d(x, y)
                                              x∈Ci ,y∈Cj

to be the smallest distance between elements of each cluster. Also define
                                        dl = max d(x, y)
                                               x,y∈Cl

to be the largest intra-cluster distance between all clusters {Cl }1≤l≤k . Then, the Dunn
index is given by
                                             min1≤i,j≤k d
                                          k                ij
(27)                        D {(xl , Cl )}l=1 =               .
                                                max1≤l≤k dl
Larger values of (3.4) are indicative of a better clustering.
            CLUSTERING MARKET REGIMES USING THE WASSERSTEIN DISTANCE                             16

Definition 3.5 (Silhouette coefficient, [Rou87]). With the same notation as Definition
3.3, define
                                           1 X
                              bi = min              d(xi , y),
                                     i6=j |Cj |
                                                y∈C      j

and
                                              1 X
                                      ai =             d(xi , y).
                                             |Ci | y∈C
                                                     i

for any xi ∈ Cl , l = 1, . . . , k. Then, the Silhouette coefficient of the point xi is given by
                                                   b i − ai
(28)                                      S(i) =                .
                                                  max(ai , bi )
From (28), we can see that −1 ≤ S(i) ≤ 1. Higher values of S(i) mean that the point xi
was appropriately allocated to cluster Cl .

Remark 3.6. It is often computationally expensive to calculate the (28) for every point
x. Thus, we often use an estimate from fewer samples.
For 0 < α ≤ 1, define λl = bα |Cl |c and let (nlk )λk=1        l
                                                                    be an increasing sub-sequence of
{1, . . . , |Cl |}, for l = 1, . . . , k. Then, the α-average Silhouette coefficient S α is given by
                                                   k       λl
                                                                     !
                                                1X 1 X
(29)                                      Sα =                S(nlk ) .
                                                k l=1 λl k=1

The indexes from Definitions 3.3, 3.4 and 3.5 are often used to evaluate clusters derived
from a standard k-means algorithm for different values of k. We will see that using them to
compare clusterings between the MK- and WK-means approaches (for the same value of k)
does not capture how appropriate clusterings are in reference to the MRCP. Firstly, such
indexes are not agnostic to the choice of (V, k·kV ) and are thus not comparable between
algorithms. Secondly, a more appropriate validation method for the MRCP would be
between regimes µ ∈ S (Pp (R)), as opposed to elements of the clustering space ϕ(µ) ∈ V .
Thus, as an integrable probability metric, the MMD is a more suitable choice to be used
to evaluate the appropriateness of either clustering algorithm. Nevertheless we will report
the values of these metrics for completeness.
For our between-cluster evaluation, we proceed as follows. Given sets C1 , C2 obtained via
either the moment- or WK-means clustering algorithm, draw n ∈ N pairwise samples
(µi , νi ) ∈ C1 × C2 for i = 1, . . . , n. We represent each empirical measure µi , νi ∈ Pp (R) by
its corresponding vector of log-returns xi , yi ∈ S(R). We then evaluate the test statistic
(53) where we choose k : Rd × Rd → [0, +∞) to be the Gaussian kernel (48) with σ = 0.1.
We then compare the associated distribution of the MMD between the two histograms
generated from the moment- and WK-means methods by reporting the similarity score
from Definition 1.9.
Within-cluster evaluation is performed much in the same way as the between-cluster
case: for either algorithm, and for each cluster Cl , l = 1, 2 we draw n ∈ N pairwise
samples (µ1i , µ2i ) ∈ Cl × Cl and evaluate the biased MMD (53). We report the similarity
score associated to the empirical distribution of each within-cluster MMD and plot the
resulting histograms.
3.2.4. Cluster validation via the marginal MMD. Recall from Section 1 that we stated
that a clustering algorithm was successful if the self-similarity and distinctness of derived
clusters were appropriately traded off against each other. In this section, we give the scores
           CLUSTERING MARKET REGIMES USING THE WASSERSTEIN DISTANCE                        17


                    Algorithm Davies-Bouldin           Dunn        Sα
                    Wasserstein        1.1075       7.3 × 10−3 0.5093
                      Moment           0.8604       9.2 × 10−3 0.8008

       Table 1. Scores for MK- and WK-means algorithms using traditional k-means
       index evaluation methods, typical run.

of each clustering algorithm on the SPY data with references to the indexes introduced
in Definitions 3.3, 3.4, and 3.5. In particular, we report the average silhouette coefficient
S α with α = 0.2. Results are given in Table 1.
As noted in Section 3.2.3, scores associated to the first two indexes are not invariant under
the choice of (V, k·kV ) and thus do not represent a like-for-like comparison. Yet we note
that the average Silhouette coefficient S α remains higher for the MK-means method than
the WK-means, implying that (under the more traditional method of cluster validation)
regimes clustered via the former belong to more appropriate clusters than the latter.
As outlined in Section 3.2.3, we applied our within- and between-cluster validation via
the marginal MMD from Definition 1.7 by sampling n = 1000000 times from each cluster
C1 , C2 obtained from either method, and calculating the biased MMD (10). We order
samples from clusters in ascending order to ensure like-for-like comparison between sample
elements. Figure 3 shows two empirical distributions of the biased MMD between elements
in the two clusters formed from the WK- and MK-means method.




       Figure 3. Histograms of between-cluster MMD approximation, Wasserstein vs
       moments method.

Figure 3, shows that the clusters obtained via the WK-means method are significantly
more similar to each other than those obtained from the MK-means method. However,
one cannot then conclude that the latter method provides a better clustering result if
the disparity within groups is due to one cluster being composed primarily of outlier
elements. Figure 4 gives the empirical distribution of the within-cluster MMD for each
algorithm. These histograms were derived by calculating the biased MMD test statistic
via the sub-sampling technique from Definition 1.9, with n = 100000.
Both Figure 4 and the self-similarity scores in Table 2 show that the clusters obtained
via the WK-means algorithm are significantly more self-similar than those obtained from
the MK-means algorithm.
           CLUSTERING MARKET REGIMES USING THE WASSERSTEIN DISTANCE                       18




       Figure 4. Histograms of within-cluster MMD approximation, Wasserstein vs
       moments method.


                               Algorithm            C1         C2
                               Wasserstein 0.0395 0.2304
                                 Moment          0.0631 1.1961

              Table 2. Self-similarity scores, WK- and MK-means algorithms.


3.3. Validation on synthetic data. Evaluating a given clustering algorithm on real
market data is difficult for multiple reasons. One is that it is not possible to infer the
underlying probabilistic structure associated to the stream of log-returns rS that a clus-
tering algorithm is run over, and thus one cannot say with any certainty what constitutes
a “correct” clustering. A corollary to this is that it is impossible to know exactly at what
point a regime change occurs when studying real market data.
Therefore, we evaluated both clustering algorithms on synthetic market data, where we
specify beforehand at what times regime changes occur. Because we knew both the un-
derlying probabilistic structure and the regime change periods a priori, we could further
evaluate both how accurately either algorithm is classifying sequences of returns into
regimes, and how closely the centroids {µl }l=1,2 of each cluster correspond to the true
distributions {Pl }l=1,2 associated to the synthetic data.
The methodology is as follows. For a given time interval [0, T ] with T ∈ N, we define
a mesh so that each time increment roughly represents one market hour. That is, with
n := 252 × 7, we set                                              
                                   i−1 i
                         ∆=                ,   : i = 1, 2, . . . , nT .
                                      n n
Next, we define the number of regime changes r ∈ N we wish to observe. We specify their
starting points and lengths by (si , li ) ∈ N × N for i = 1, . . . , r, with
                                   0 ≤ s0 < sr + lr ≤ nT,
and
                        si + li + 2 < si+1 ,  for i = 1, . . . , r − 1.
Each li can be a constant or a random variable. We thus obtain the set of disjoint intervals
(30)                          R = {[si , si + li ] : i = 1, . . . , r}
            CLUSTERING MARKET REGIMES USING THE WASSERSTEIN DISTANCE                            19

and their associated complements N = ∆ \ R which partition the interval ∆ into two
sets. Intervals in R will correspond to times where we observe a regime change in our
synthetic data, which will start at si and end at si + li for i = 1, . . . , r.
Once we have run a classification algorithm over a synthetic price path, we consider three
measures of accuracy: total accuracy, accuracy during the standard regime (regime-off)
and accuracy during the regime change (regime-on). This is calculated in the following
way: for i = 1, . . . , N − 1, associate to each log-return riS the empirical measures Mi =
{µj(i) , . . . , µj(i)+v } it was a member of. With our chosen hyperparameters and k = 2, one
has that v ∈ [1, 5] and j ∈ N is the first measure that riS is a member of. Note that if the
overlap hyperparameter h2 = 0 then v = 1. We then calculate which cluster each µ ∈ Mi
is associated to, which gives us our predicted labels y i = {k 1 , . . . , k v }. We then aggregate
these labels into the row vector
                                    v
                                                   !k
                              i    X
                           Y =        χ{x=l} (k j )     for i = 1, . . . , N − 1,
                             j=1              l=1

where k = 2 is the number of clusters. In what follows we assume the assignment k = 1
corresponds to the standard regime and k = 2 the regime change. We then have the
following definitions.

Definition 3.7. With the notation above, for a given vector of log-returns rS ∈ S(R)
and cluster assignments C = {Cl }kl=1 , the regime-off accuracy score (ROFS) is given by
                                                 P            i
                                    S                riS ∈N Y 1
(31)                      ROFS(r , C) = P               P          i .
                                                rS ∈N
                                                    i      k=1,2 Y k

Similarly, the regime-on accuracy score (RONS) is given by
                                             P           i
                                                r S ∈R Y 2
(32)                       RONS(rS , C) = P      i
                                                  P          i .
                                             S
                                            r ∈R           Y
                                                     k=1,2 k
                                                    i

Finally, total accuracy (TA) is given by
                                       P               i   P           i
                                              riS ∈N Y 1 +    riS ∈R Y 2
(33)                        TA(rS , C) =       PN −1 P             i     .
                                                   i=1    k=1,2 kY

3.3.1. Geometric Brownian motion. In this section, we discuss how we tested both clus-
tering algorithms on synthetic stock data which was modelled as a geometric Brownian
motion. Let M(Θ) be a family of models indexed by a parameter set Θ ⊂ Rd . Initially, we
chose M(Θ) = gBm(µ, σ). We then specified two parameter combinations θbull = (µ1 , σ1 )
and θbear = (µ2 , σ2 ), corresponding to two market regimes.
We then construct a geometric Brownian motion with associated parameters θbear over
intervals [si , si + li ] ∈ R for i = 1, . . . , r, and with parameters θbull elsewhere. We then
run both clustering algorithms on the synthetic data and are returned the clusters with
associated centroids as output. Since
                         ln St ∼ Normal (µ − σ 2 /2)t, σ 2 t
                                                            
(34)                                                             for all t ≥ 0,
the true measures {Pl }l=1,2 are given by
(35)                  Pl = Normal((µl − σl2 /2)dt, σl2 dt)         for l = 1, 2,
           CLUSTERING MARKET REGIMES USING THE WASSERSTEIN DISTANCE                           20

where dt = 1/n is the mesh size. Due to the Gaussianity of the distribution of the true
log-returns, it suffices to check the mean and variance of the centroid measures µl to
gauge how close they are to the true measures Pl for l = 1, 2.
We begin by testing on geometric Brownian motion paths with
                                 θbull = (0.02, 0.2),    and
                                 θbear = (−0.02, 0.3).
We simulate a path over T = 20 years with r = 10 regime changes, and randomly chose
each si for i = 1, . . . , 10 and fixed li = 0.5 × 252 × 7. This choice corresponds to regime
changes persisting for approximately half a year. Our mesh grid is thus given by
                                                                           
                                i−1 i
                      ∆=              ,       : i = 1, 2, . . . , 252 × 7 × 20 .
                                1764 1764
When a regime change occurs, the gBm parameters shift from θbull to θbear . Figure 5
shows an example of such a gBm path, with the regime change periods highlighted in
red. Figure 5b gives the log-returns associated to Figure 5a, again with the regime changes
highlighted in red.




   (a) gBm path, regime changes highlighted.             (b) Associated log returns.

       Figure 5. A synthetic geometric Brownian motion path, and associated log
       returns.

We ran all three clustering algorithms on the same simulated path data. As seen from
Figure 6 and Figure 7, both algorithms perform well - they are able to accurately capture
both the regime changes and ends. We give a summary of the accuracy scores of each
algorithm in Table 3 for a total of n = 50 runs.

  Algorithm            Total             Regime-on         Regime-off           Runtime
  Wasserstein    90.60% ± 5.81%      87.24% ± 4.11%      91.72% ± 6.46%       0.87s ± 0.16s
    Moment       93.23% ± 0.41%       74.83% ± 1.57%     99.38% ± 0.1%        1.06s ± 0.16s
     HMM         58.16% ± 7.11%       41.51% ± 7.43%     63.72% ± 11.94% 0.58s ± 0.36s

         Table 3. Accuracy scores with 95% CI, gBm synthetic path, n = 50 runs.

It is interesting to note that, even in the Gaussian case, the WK-means algorithm does
a better job of picking up regime changes than the standard approach. By comparison,
the HMM tends to fail to detect the changes in regime at this fixed level of difference in
           CLUSTERING MARKET REGIMES USING THE WASSERSTEIN DISTANCE                     21

parameter space and thus cannot determine regime change times at this level of gran-
ularity between the two models. We provide the plots of the clustering algorithms in
mean-variance space and the historical colouring plots in Figures 6 and 7.




               (a) MK-means.                                 (b) WK-means.

      Figure 6. Plots of clusters in mean-variance space, synthetic gBm, example run.




               (a) MK-means.                                 (b) WK-means.




                                 (c) Hidden Markov model.

         Figure 7. Historical cluster colouring plot, synthetic gBm, example run.

We conclude this section by comparing the centroids obtained from either algorithm to
the true measures. In this example, the distribution of the log-returns corresponding to
either regime is given by
                 Pθbull = Normal(−1.97 × 10−21 , 2.27 × 10−05 ),      and
                 Pθbear = Normal(−3.68 × 10−05 , 5.1 × 10−05 ).
              CLUSTERING MARKET REGIMES USING THE WASSERSTEIN DISTANCE                                22

Since the distribution of log-returns in this model are Gaussian, we study the mean and
variance of our obtained centroids and compare these to the true vales.

Figure 8 summarizes our findings. In the first row, we display the histogram of the parti-
tion means {E[µi ]}1≤i≤M along with solid lines representing the true means E[Pθbull ] and
E[Pθbear ]. In Figures 8a and 8b, the dashed lines represent the bull and bear centroid
means corresponding to the MK-means and WK-means algorithms respectively. In the
second row, we repeat the same procedure with the variances {Var(µi )}1≤i≤M , their true
values, and in Figures 8c and 8d the centroid variances corresponding to the MK-means
and WK-means algorithms respectively.




       (a) Distribution of {E[µi ]}i≥0 , moment.    (b) Distribution of {E[µi ]}i≥0 , Wasserstein.




   (c) Distribution of {Var(µi )}i≥0 , moment.     (d) Distribution of {Var(µi )}i≥0 , Wasserstein.

         Figure 8. Approximations of mean and variance of true measures Pi , i = 1, 2
         by centroids of moments- and WK-means algorithms, gBm run.


We see that the centroids derived from either algorithm perform well as estimators for
the true centroids. We note that it is not altogether unsurprising that the Wasserstein
algorithm does not significantly outperform the moments-based method here: since we are
working under the assumption that distributions of log-returns under the “true” model
are completely determined by their mean and variance.


3.3.2. Merton jump diffusion. In this section, we outline a separate model used to gen-
erate synthetic data where the associated log-returns are non-Gaussian. In particular, we
model stock prices by a Merton jump diffusion, which is given by the solution S to the
stochastic differential equation
(36)                      dSt = µSt dt + σSt dWt + St− dJt      for t ≥ 0,
            CLUSTERING MARKET REGIMES USING THE WASSERSTEIN DISTANCE                          23

where
                                                  Nt
                                                  X
                                           Jt =         Vj − 1.
                                                  j=1
Here, Nt ∼ Po(λt) is a Poisson random variable, and ln(1 + Vj ) ∼ Normal(γ, δ 2 ). Our
model space M(Θ) is given by
(37)                     M(Θ) = MJD(µ, σ, λ, γ, δ)                 for Θ ⊂ R5 .
The solution to (36) is given by
                                                             Nt
                                                             Y
(38)                              St = F (0, t)E(σWt )             Vj ,
                                                             j=1

where F (0, t) = S0 exp(µt), and E : R → [0, +∞) is the Doléans-Dade stochastic expo-
nential. Let RtM = ln(St+dt ) − ln(St ) be the log-return associated to a realisation of (38)
at a time t ∈ [0, T ] on a mesh with grid size dt. Then, [Syn08] gives that
                            E[RtM ] = (µ − σ 2 /2) + λγ dt,
                                                       
(39)                                                            and
(40)                     Var(RtM ) = (σ 2 + λ(δ 2 + γ 2 ))dt,
and we will use these quantities to check the suitability of the centroids from either
algorithm to the true measures.

To test either algorithm on synthetic data as generated from (37), we apply the same
methodology as outlined in Section 3.3. That is, we define two sets of parameters θbear , θbull
and a partition ∆ with regime changes [si , si + li ] ∈ R for i = 1, . . . , r, where R is given
by (30). We then run both clustering algorithms over a Merton jump diffusion with
parameters θbear over intervals in R and parameters θbull elsewhere. In regime switch
dynamics are given by the parameter choices
                          θbull = (0.05, 0.2, 5, 0.02, 0.0125),            and
                         θbear = (−0.05, 0.4, 10, −0.04, 0.1).
We again set r = 10 and li = 252 × 7 × 0.5 for i = 1, . . . , 10. When a regime change occurs
we shift the parameters of the Merton jump diffusion from θbull to θbear , and revert them
back when the regime change ends. Figure 9 gives an example path and the associated
log-returns, with the periods of regime change highlighted in red.




         (a) Merton jump diffusion path.                                  (b) Log returns.

        Figure 9. An iteration of a Merton jump diffusion path ω → StJ and the asso-
        ciated log-returns, regime changes highlighted.
           CLUSTERING MARKET REGIMES USING THE WASSERSTEIN DISTANCE                       24

For the example path presented in Figure 9a, we present plots from all three algorithms
where applicable. Figure 10 gives the projection of the derived clusters for the moment-
and WK-means algorithm. Here, one can see that the MK-means approach fails to discern
between the two market regimes as it is not robust enough to adjust for outlier return
series in the bear regime. By comparison, the Wasserstein approach is relatively robust
to these outliers, and is able to correctly identify the two different regimes with their
associated distributions.




                (a) MK-means.                                (b) WK-means.

       Figure 10. Outputs of clustering algorithms in mean-variance space, Merton
       jump diffusion, example run.

Figure 11 shows the WK-means clusters in skew-kurtosis space. We see here that the
algorithm correctly identifies several distributions exhibiting positive skew as belonging
to the bull regime. Furthermore, the algorithm is also able to discern between these dis-
tributions and those belonging to the bear regime, which are significantly more positively
skewed.




       Figure 11. Clustered empirical Merton distributions in skew-kurtosis space,
       WK-means, example run.

We summarize the results for n = 50 runs with the parameters (θbull , θbear ). It is clear
that both the MK-means and HMM approach are unable to discern between periods of
regime change and normalcy. As expected, the Wasserstein approach does not fare as well
as the Gaussian case, although the difference is negligible. Note that the high accuracy
in the regime-on case for the HMM is due to the fact that it never identifies the alternate
regime and places all points into the first category. For the path in Figure 9a, we give the
           CLUSTERING MARKET REGIMES USING THE WASSERSTEIN DISTANCE                          25

historical colouring plot associated to a run of all three algorithms in Figure 12, which
highlights the numerical results obtained from the table.

   Algorithm           Total            Regime-on            Regime-off        Runtime
   Wasserstein 91.28% ± 4.08% 86.87% ± 3.1%              92.76% ± 4.43%      1.11s ± 0.25s
     Moment       66.64% ± 3.42%     27.25% ± 8.73%      79.79% ± 7.40%      1.71s ± 0.28s
      HMM         75.05% ± 0.01%      0.66% ± 0.04%     99.87% ± 0.01% 0.66s ± 0.04s

        Table 4. Accuracy scores with 95% CI, Merton synthetic path, n = 50 runs.




                (a) MK-means.                                  (b) WK-means.




                                  (c) Hidden Markov model.

       Figure 12. Historical cluster colouring on synthetic Merton jump diffusion price
       path, example runs.

As we did with the geometric Brownian motion example, we conclude the results section
with a comparison between the mean and variance of the centroids obtained from either
algorithm, and those associated to the true distributions as given by equations (39) and
(40). As expected, from Figures 13a and 13c it is clear that the MK-means centroids do
a poor job of approximating the true measures associated to the bull and bear regimes.
We compare this to Figures 13b and 13d, where the mean and variance of the WK-means
centroids are much closer to the theoretical counterparts.
3.4. Selection of hyperparameters. In this section we give a brief discussion re-
garding how the choice of hyperparameters (h1 , h2 ) affects the results of the WK-means
algorithm. We begin with a discussion to the first hyperparameter h1 , which corresponds
to the number of returns that form each empirical distribution within the clustering al-
gorithm. Classically one would like to take as large a value of h1 as is feasibly possible in
           CLUSTERING MARKET REGIMES USING THE WASSERSTEIN DISTANCE                                  26




   (a) Distribution of {E[µi ]}i≥0 , MK-means.     (b) Distribution of {E[µi ]}i≥0 , WK-means.




  (c) Distribution of {Var(µi )}i≥0 , MK-means.   (d) Distribution of {Var(µi )}i≥0 , Wasserstein.

       Figure 13. Approximations of mean and variance of true measures by centroids
       of moments- and WK-means algorithms.


order to best approximate empirically the true data-generating measure. In the regime
clustering context, however, this is not always ideal: choosing h1 to be too large can mean
that regime changes are not captured, or (in a live data setting) the detection of such
changes are lagged. However, certainly if h1 is chosen too small spurious classifications
dominated by noise will be made. Thus we believe that the choice of window length hy-
perparameter is more an art than a science and strongly depends on the application in
mind.
Regarding the overlap hyperparameter h2 : heuristically, a larger value of overlap param-
eter (relative to h1 ) can be thought of in two ways. Mechanically it is a way of increasing
the number of samples used in the clustering algorithm, which may be necessary in a
low-data environment. Heuristically, by increasing the clustering set with measures that
are very similar to each other, one is indirectly making a statement about how represen-
tative the observed sequence of log-returns (and thus clustering set measures) relative to
what one might deem “standard” conditions. This phenomena can be seen in the simple
case when one clusters on S&P 500 data before and after the GFC: for k = 2 and with
h2 = 0, one would expect that the outlier centroid µ2 moves significantly faster to its new
position than µ1 , whereas if h2 is closer to h1 , one expects the centroids to not initially
change as much during the onset of the GFC, since new observations are less constituent
relative to the corpus of measures preceding them.
We note however that in general the overlap hyperparameter does not have too large an
effect on centroids obtained (and, thus, clusters) assuming that one is not operating in
too low a data environment, and h1 is suitably chosen. We present the results of clustering
            CLUSTERING MARKET REGIMES USING THE WASSERSTEIN DISTANCE                               27

on SPY for the hyperparameter choice h1 = (35, 28), the choice we made in Section 3.2,
and h2 = (35, 0) in Figure 14. Here, one can see that the obtained centroids from either
algorithm do not change drastically in spite of the lower data density.




(a) Mean-variance plot of clusters and centroids,(b) Mean-variance plot of clusters and centroids,
h1 = (35, 28).                                   h2 = (35, 0).




    (c) Historical backtest plot, h1 = (35, 28).     (d) Historical backtest plot, h2 = (35, 0).

       Figure 14. WK-means results with h1 and h2 hyperparameter choices, SPY
       price path.

Indeed a simple Kolmogorov-Smirnov two-sample test between the first centroids (µh1 1 , µh1 2 )
returns a test statistic score of 0.02857 with an associated p-value of 1.0, and the second
set of centroids (µh2 1 , µh2 2 ) yields the same score and p-value.
Finally, we test the effect of changing the window length parameter h1 . As stated in the
beginning of the section, there exist many incorrect choices for h1 in practice (too small, or
too large), but reasonable choices will tend to give robust results. To show this, we chose a
sequence of window lengths H1 = (7+7i)1i=1 0 and set the overlap parameter h2 = b3h1 /4c.
We then ran the regime-switching experiment from Section 3.3 with the same switching
dynamics as in Section 3.3.2, repeating the experiment 30 times for each hyperparameter
choice. In particular, regime changes in this setting lasted for half a year, which amounts
to 882 time steps given our year mesh, which means that only an unreasonably large
rolling window would miss the given regime change. Figure 15 gives the various accuracy
results (total, regime-on, and regime-off) for the window length parameters given by H1 .
Past a certain threshold, the window length size does not matter and the model’s accuracy
converges.
                                         4.    Conclusion
In this paper, we have shown that a slight modification to the k-means algorithm does an
excellent job at classifying partitions of market returns into regimes. We have verified this
           CLUSTERING MARKET REGIMES USING THE WASSERSTEIN DISTANCE                     28




                Figure 15. The effect of increasing h1 on accuracy scores.

on both real data by comparing to known periods of market instability, and on synthetic
data where we explicitly determine when the regime changes occur. We have compared
this approach to a more standard moments-based algorithm which did not perform as well
when returns were non-Gaussian, and a more classical approach using a hidden Markov
model, which failed to accurately discern between regimes in the synthetic case. We also
showed that clusters obtained via the Wasserstein approach are more self-similar than
those derived from the moment-based method.
Future research would include employing other clustering algorithms rather than the stan-
dard k-means approach; for instance, fuzzy and hierarchical clustering methods. Further
study into the robustness of the derived clusters under the choice of hyperparameters
(that is, partitioning of the underlying time series) would also be relevant to understand
how stable derived clusters are. We also note that there exist methodologies for deter-
mining the optimal number of clusters k to be used. Finally, a more analytic and rigorous
study of the weak convergence of derived centroids to the true measures (in the synthetic
data case) would also be of interest.
            CLUSTERING MARKET REGIMES USING THE WASSERSTEIN DISTANCE                             29

                        Appendix A.         The k-means algorithm
In this section, we outline some of the notation used in the paper, along with some
standard results regarding the classical k-means algorithm.

Recall that X ∈ S(V ) is a stream of data over a normed vector space (V, k·kV ).

Definition A.1 (Set of clusterings over X). We write
                         (                       n
                                                              )
                                                [
                C(X) = {Ci }0≤i≥n : Ci ∩ Cj = ∅, Ci = X, n ∈ N
                                                           i=1

to be the set of all possible (disjoint) clusterings over X.

The k-means algorithm returns an element C ∗ ∈ C(X) which is locally optimal with
respect to the induced metric d : V × V → [0, +∞) on V .

Before continuing with a more detailed explanation of the k-means algorithm, we intro-
duce the following definitions.

Definition A.2 (Within-cluster variation). Let k ∈ N and let X ∈ S(V ) be a steam
of data over a normed vector space V . Suppose C ⊂ C(X) are disjoint clusters over X.
Associate to each Cl its centroid xl for l = 1, . . . , k. Then, for a given Cl , the within-cluster
variation is defined as
                                   X
(41)                   WC(Cl ) =       kx − xl k2V         for l = 1, . . . , k.
                                     x∈Cl



Definition A.3 (Total-cluster variation). With the notation of Definition A.2, define
                                                k
                                                X
(42)                                  TC(C) =          WC(Cl )
                                                 i=1

to be the total-cluster variation corresponding to a clustering C ∈ C(X) on the normed
vector space (V, k·kV ).

Recall that {Cln } ∈ C(X) denotes an intermediate disjoint clustering of the set X at step
n ∈ N. The k-means algorithm first assigns nearest neighbours via (7) with respect to
V . The next step in the algorithm is to update the centroids via an aggregation function
α : 2V → V which gives a central element xl ∈ V from the set of nearest neighbours Cl
for l = 1, . . . , k. In the classical k-means on Rd , this function is given by
                                                            !
                                                1 X
(43)                                 α(Cl ) =            xj     .
                                               |Cl | x∈C
                                                       l    1≤j≤d

Here, |C| denotes the cardinality of the set C. Note that other choices of (V, k·kV ) neces-
sitate different aggregation methods depending on the structure of V .

Continuing, the algorithm then updates the centroids via the function α:
                                xnl = a(Cln )    for l = 1, . . . , k.
The new centroids xn are then compared to xn−1 via the following stopping rule.
           CLUSTERING MARKET REGIMES USING THE WASSERSTEIN DISTANCE                      30

Definition A.4 (k-means stopping rule). Suppose (V, k·kV ) is a normed vector space.
For fixed k ∈ N, consider a loss function l : V k × V k → R+ given by
                                            k
                                            X
(44)                            l(x, y) =         kxi − yi kV ,
                                            i=1
For a tolerance level ε > 0, the stopping rule corresponding to the standard k-means
algorithm is given by
(45)                                 l(xn−1 , xn ) < ε,
where n ∈ N denotes the step of the algorithm, and we take V = Rd .

Remark A.5. Various algorithms which attempt to find the optimal number of clusters k
that should be used to separate data X consider (41) as the loss to be minimised over all
possible clusterings. We will not cover these algorithms in this paper (see, for instance
[RT99]), and their applications to the MRCP are topics for future research.

A given run of the k-means algorithm is characterised by the 2-tuple of centroids and
nearest neighbour assignments (xl , Cl )1≤l≤k . We conclude this section with the following
proposition.

Proposition A.6. The k-means algorithm converges in finitely many steps to a local
minima.

Proof. Finiteness is guaranteed since the number of possible partitions of datum X is
at most k N . Thus, the function TC : C(X) → [0, +∞] necessarily achieves a global
minimum. Therefore, the sequence (TC(C n ))n≥1 is non-increasing (by definition of the
k-means update step (7)) and bounded from below, which guarantees convergence to a
local minima.                                                                       

Finally, we summarise Section 1.4 and Appendix A with Algorithm 2.

 Algorithm 2: Standard k-means algorithm
  Result: k centroids
  initialise centroids by sampling k times from X;
  while loss_function > tolerance do
      foreach xi do
         assign closest centroid wrt Euclidean distance;
      end
      update centroids;
      calculate loss_function;
  end

                 Appendix B.      The maximum mean discrepancy
In this section, we include extra details regarding the derivation of the MMD from Def-
inition 1.7. In particular we show how one can show the MMD can be employed as a
metric on the space of probability measures.

Definition B.1 (Reproducing kernel Hilbert space, [Aro50], Section 1.1). Suppose X is
a non-empty set, and let (H, h·, ·iH ) be a Hilbert space of functions f : X → R. We call
a positive definite function k : X × X → R a reproducing kernel of H if
            CLUSTERING MARKET REGIMES USING THE WASSERSTEIN DISTANCE                           31

    (i) For all x ∈ X , we have that k(·, x) ∈ H, and
   (ii) For all x ∈ X and f ∈ H, one has that
(46)                                 f (x) = hf (·), k(·, x)iH ,
        referred to as the reproducing property.
We call the Hilbert space H associated to k a reproducing kernel Hilbert space (RKHS).

We can associate to each RKHS H the canonical feature map given by φ(x) = k(·, x). We
thus have that
              k(x, y) = hk(·, x), k(·, y)iH = hφ(x), φ(y)iH        for all x, y ∈ X ,

by the reproducing property from Definition B.1. Directly from the definition of a RKHS
H, we have the following equivalent definition.

Definition B.2 ([BTA11], Theorem 1). Suppose H is a Hilbert space. Define δx : H → R
to be the evaluation map. Then, H is a RKHS if and only if δx is continuous.

Proof. Suppose that H is a RKHS. Denote by H0 as the dual of H. One has that
                         |δx (f )| = |f (x)| = |hf, k(·, x)iH |
                                                                      1/2
                                            ≤ kf kH hk(·, x), k(·, x)iH
                                              p
(47)                                        = k(x, x) kf kH ,
                                                                              p
so in particular the linear operator δx is bounded with operator norm equal to k(x, x),
which is well-defined by positive definiteness of k. Since the upperpbound in (47) is
achieved by f = k(·, x), δx is bounded with operator norm kδx kH0 = k(x, x). Since δx
is bounded, it is continuous.
Now suppose that δx is bounded, so δx ∈ H0 . By the Riesz representation theorem, there
exists an element fδx ∈ H such that δx (f ) = hf, fδx iH . Define k(x, x0 ) := fδx (x0 ). We then
have that δx (f ) = f (x) = hf, k(·, x)iH and k(·, x) ∈ H by construction. Thus, properties
(1) and (2) are satisfied in Definition B.1, so H is a RKHS.                                   

In what follows, we will choose our function class F from Definition 1.7 to be the unit
ball in a RKHS H with associated reproducing kernel
                    k(x, y) = exp (2σ)−2 kx − yk2Rd
                                                    
(48)                                                     for σ > 0,
called the Gaussian kernel. Importantly, such a RKHS has the following property, as
shown in Steinwart [Ste01].

Definition B.3 (Steinwart [Ste01], Definition 4). Let (X , d) be a compact metric space.
Suppose H is a RKHS with associated reproducing kernel k : X × X → R. We call H
universal if
    (i) k(·, ·) is continuous, and
   (ii) H is dense in Cb (X ), the space of bounded continuous functions on X , with respect
        to the supremum norm k·k∞ .

This choice of RKHS ensures that the MMD is metric on the space of Borel probability
measures, which allows us to conclude the following.
            CLUSTERING MARKET REGIMES USING THE WASSERSTEIN DISTANCE                           32

Theorem B.4 ([GBR+ 12], Theorem 5). Let F be the unit ball of a universal RKHS H
comprised of R-functions on a compact space X . Suppose µ, ν ∈ P(X ) are Borel. Then
MMD[F, µ, ν] = 0 if and only if µ = ν.

Proof. For µ ∈ P(X ), consider the linear functional Tµ : F → R given by Tµ (f ) = Eµ [f ].
We have that
                                                                             p
       |Tµ (f )| = |Eµ [f (x)]| ≤ Eµ [|f (x)|] = Eµ [|hf, k(·, x)iH |] ≤ Eµ [ k(x, x)] kf kH ,
                                                                          p
so in particular Tµ is continuous if k(·, ·) is measurable and Eµ [ k(x, x)] < +∞. By the
Riesz representation theorem, there exists a mµ ∈ H such that Tµ (f ) = hf, mµ iH . In
particular,
                        mµ (x) = hmµ , k(·, x)iH = Eµ [k(·, x)] = Eµ [φ(x)].
We call mµ the mean embedding of µ in H. From (9), we have that
                                                                 2
                 MMD2 [F, µ, ν] = sup Eµ [f (x)] − Eν [f (y)]
                                    f ∈F
                                                                         2
                                 = sup hf, mµ iH − hf, mν iH
                                    f ∈F
                                                                    2
(49)                             = sup             hmµ − mν , f iH        = kmµ − mν k2H .
                                    kf kH ≤1

Here, we have used the fact that F is a unit ball in H. Suppose that µ = ν. By (49), this
implies MMD[F, µ, ν] = 0.
Now suppose that µ = ν. By universality of H, for any ε > 0 and f ∈ Cb (X ) there exists
a g ∈ H such that
                                                      ε
(50)                                     kf − gk∞ < .
                                                      2
Then, we have that
                                                                                ε     ε
(51) Eµ [f ] − Eν [f ] ≤ Eµ [f ] − Eµ [g] + Eµ [g] − Eν [g] + Eν [g] − Eν [f ] < + 0 + = ε,
                                                                                2     2
where we have used the fact that for measures µ and ν, (50) gives that
                                                          
                        E[f ] − E[g] ≤ E f (x) − g(x) ≤ kf − gk∞ ,
and
                            |Eµ [g] − Eν [g]| = |hg, mµ − mν iH | = 0
since we assumed MMD[F, µ, ν] = 0. Thus µ = ν as (51) holds for all f ∈ Cb (X ).               

Remark B.5. Suppose (X, Σ) is a general measurable space (and not necessarily compact).
Recalling Definition (1.8), if a kernel k associated to the RKHS H is characteristic, so
the mapping
                              P(X ) 3 µ 7→ EX∼µ [k(·, X)] ∈ R
is injective, then one can conclude Theorem B.4 via equation (49).

Using the definition of the mean embedding, the fact that mµ (t) = Ex∼µ [k(t, x)], and the
reproducing property of F, we can write (49) as
(52)     MMD2 [F, µ, ν] = Ex,x0 ∼µ [k(x, x0 )] − 2Ex∼µ,y∼ν [k(x, y)] + Ey,y0 ∼ν [k(y, y 0 )]
since, for example,
                        hmµ , mµ iH = Ex∼µ [mµ (x)] = Ex,x0 ∼µ [k(x, x0 )].
            CLUSTERING MARKET REGIMES USING THE WASSERSTEIN DISTANCE                                   33

Given samples x = (x1 , . . . , xn ) and y = (y1 , . . . , ym ), a biased empirical estimate of (52)
is given by
                            "        n                      m,n                    m
                                                                                                #1
                                                                                                 2
                                1 X                     2 X                   1 X
(53)     MMDb [F, x, y] =               k(x i , xj ) −           k(x  ,
                                                                     i jy ) +          k(y ,
                                                                                          i jy )   .
                               n2 i,j=1                mn i,j=1               m2 i,j=1
We will use the test statistic (53) to evaluate the success of a given clustering algorithm.


                       Appendix C.                The Wasserstein distance
In this section, we include proofs of results regarding the Wasserstein distance.

Proposition C.1 (Wasserstein barycenter, empirical measures). Suppose that {µi }1≤i≤M
are a family of empirical probability measures, each with N atoms αi1 , . . . , αiN for i =
1, . . . , M . Let
                     aj = Median(α1j , . . . , αM
                                                j
                                                  ) for j = 1, . . . , N.
Then, the cumulative distribution function of the Wasserstein barycenter µ ∈ Pp (R) over
{µi }1≤i≤M with respect to the 1-Wasserstein distance is given by
                                                                  N
                                                     1 X
(54)                                   µ ((−∞, x]) =      χa ≤x (x).
                                                     N i=1 i
Moreover, µ is not necessarily unique.

Remark C.2 (p > 1). When p > 1, the proof follows in a similar manner. One will arrive
at
                            aj = Mean(α1j , . . . , αM
                                                     j
                                                       ).


Proof. Assume that N = 1, so each measure µi is comprised of only one atom αi for
i = 1, . . . , M . WLOG we can also assume that the sequence (αi )M
                                                                  i=1 is non-decreasing. By
convexity of the function φa (x) = |x − a| for a ∈ R, the Wasserstein barycenter will also
have N = 1 atoms. Then, by (21) the problem of finding the barycenter µ is equivalent
to the optimisation
                                M
                                X                           M
                                                            X                         M
                                                                                      X
(55)                  inf             W1 (µi , ν) = inf           |a − αi | = inf           φαi (a).
                   ν∈P1 (R)                           a∈R                       a∈R
                                i=1                         i=1                       i=1
                  ∗
The minimiser a ∈ R to the right-hand side of (55) is obtained by solving df /dx(x) = 0
over R, where
                 f (x) = |x − α1 | + · · · + |x − αM | = φα1 (x) + · · · + φαM (x).
Since
                            dφαi
                                 (x) = sgn(x − αi )                   for i = 1, . . . , M,
                             dx
we have that
                                            M
                                            X
                            ∗
(56)                    a = arg inf               |a − αi | = Median(α1 , . . . , αM ).
                                      a∈R
                                            i=1

In particular, if M mod 1 = 0, then a∗ ∈ [αM/2 , αM/2+1 ). If M mod 2 = 1, then the
(unique) optimizer is given by a∗ = αK where K = bM/2c + 1. Setting a = a∗ gives (54).
           CLUSTERING MARKET REGIMES USING THE WASSERSTEIN DISTANCE                                    34

If N > 1, then the problem of finding the Wasserstein barycenter is equivalent to
                                M
                                X                                          M X
                                                                           X N
                      inf             W1 (µi , ν) =         inf                        |aj − αij |.
                   ν∈P1 (R))                          (a1 ,...,aN   )∈RN
                                i=1                                        i=1 j=1

Interchanging the order of summation, we see that
                                     M X
                                       N                       N                 M
                                                                                                 !
                                     X                         X                 X
                      inf                      |ai − αij | =               inf         |aj − αij | .
                (a1 ,...,aN   )∈RN                                     aj ∈R
                                     i=1 j=1                   j=1               i=1

By applying (56) to each summation over M , we obtain the desired result (54).                         
             CLUSTERING MARKET REGIMES USING THE WASSERSTEIN DISTANCE                              35

                                           References
[ABS08]   M. Ackermann, J. Blömer, and C. Sohler. Clustering for metric and non-metric distance
          measures. volume 6, pages 799–808, 01 2008. doi:10.1145/1347082.1347170.
[ACADF20] P. Alquier, B.-E. Chérief-Abdellatif, A. Derumigny, and J.-D. Fermanian. Estimation of
          copulas via maximum mean discrepancy, 2020, 2010.00408.
[Ach01]   S. B. Achelis. Technical analysis from a to z, 2001.
[AG13]    L. Ambrosio and N. Gigli. A user’s guide to optimal transport. In Modelling and optimisation
          of flows on networks, pages 1–155. Springer, 2013.
[AGS05]   L. Ambrosio, N. Gigli, and G. Savare. Gradient Flows: In Metric Spaces and in the Space of
          Probability Measures. Lectures in Mathematics. ETH Zürich. Birkhäuser Basel, 2005. URL
          https://books.google.co.uk/books?id=HZqhWIq1-jgC.
[Aro50]   N. Aronszajn. Theory of reproducing kernels. Transactions of the American mathematical
          society, 68(3):337–404, 1950.
[BBDG19] F.-X. Briol, A. Barp, A. B. Duncan, and M. Girolami. Statistical inference for generative
          models with maximum mean discrepancy, 2019, 1906.05944.
[BG21]    E. Bayraktar and G. Guoï. Strong equivalence between metrics of wasserstein type. Elec-
          tronic Communications in Probability, 26:1–13, 2021.
[BHL+ 20] H. Buehler, B. Horvath, T. Lyons, I. Perez Arribas, and B. Wood. A data-driven market
          simulator for small data environments. Available at SSRN 3632431, 2020.
[BKA+ 19] P. Bonnier, P. Kidger, I. P. Arribas, C. Salvi, and T. J. Lyons. Deep signatures. CoRR,
          abs/1905.08494, 2019, 1905.08494. URL http://arxiv.org/abs/1905.08494.
[BRPP15] N. Bonneel, J. Rabin, G. Peyré, and H. Pfister. Sliced and radon wasserstein barycenters of
          measures. Journal of Mathematical Imaging and Vision, 51(1):22–45, 2015.
[BTA11]   A. Berlinet and C. Thomas-Agnan. Reproducing Kernel Hilbert Spaces in Probabil-
          ity and Statistics. Springer US, 2011. URL https://books.google.co.uk/books?id=
          bX3TBwAAQBAJ.
[CAA21]   B.-E. Chérief-Abdellatif and P. Alquier. Finite sample properties of parametric mmd esti-
          mation: robustness to misspecification and dependence, 2021, 1912.05737.
[CDB86]   R. L. Cannon, J. V. Dave, and J. C. Bezdek. Efficient implementation of the fuzzy c-
          means clustering algorithms. IEEE transactions on pattern analysis and machine intelli-
          gence, (2):248–255, 1986.
[CFLA20] T. Cochrane, P. Foster, T. Lyons, and I. P. Arribas. Anomaly detection on streamed data.
          arXiv preprint arXiv:2006.03487, 2020.
[Con01]   R. Cont. Empirical properties of asset returns: stylized facts and statistical issues. 2001.
[DB79]    D. L. Davies and D. W. Bouldin. A cluster separation measure. IEEE Trans-
          actions on Pattern Analysis and Machine Intelligence, PAMI-1(2):224–227, 1979.
          doi:10.1109/TPAMI.1979.4766909.
[Dun74]   J. C. Dunn. Well-separated clusters and optimal fuzzy partitions. Journal
          of    Cybernetics,    4(1):95–104,    1974,    https://doi.org/10.1080/01969727408546059.
          doi:10.1080/01969727408546059.
[DVR15]   J. G. Dias, J. K. Vermunt, and S. Ramos. Clustering financial time series: New insights from
          an extended hidden markov model. European Journal of Operational Research, 243(3):852–
          864, 2015.
[FGSS07]  K. Fukumizu, A. Gretton, X. Sun, and B. Schölkopf. Kernel measures of conditional depen-
          dence. In NIPS, volume 20, pages 489–496, 2007.
[FGSS09]  K. Fukumizu, A. Gretton, B. Schölkopf, and B. K. Sriperumbudur. Characteristic ker-
          nels on groups and semigroups. In D. Koller, D. Schuurmans, Y. Bengio, and L. Bot-
          tou, editors, Advances in Neural Information Processing Systems, volume 21. Cur-
          ran Associates, Inc., 2009. URL https://proceedings.neurips.cc/paper/2008/file/
          d07e70efcfab08731a97e7b91be644de-Paper.pdf.
[GBC16]   I. Goodfellow, Y. Bengio, and A. Courville. Deep Learning. The MIT Press, 2016.
[GBR+ 07] A. Gretton, K. Borgwardt, M. Rasch, B. Schölkopf, and A. J. Smola. A kernel method for
          the two-sample-problem. In B. Schölkopf, J. C. Platt, and T. Hoffman, editors, Advances
          in Neural Information Processing Systems 19, pages 513–520. MIT Press, 2007. URL http:
          //papers.nips.cc/paper/3110-a-kernel-method-for-the-two-sample-problem.pdf.
[GBR+ 12] A. Gretton, K. M. Borgwardt, M. J. Rasch, B. Schölkopf, and A. Smola. A kernel two-sample
          test. Journal of Machine Learning Research, 13(Mar):723–773, 2012.
             CLUSTERING MARKET REGIMES USING THE WASSERSTEIN DISTANCE                              36

[GFHS09]  A. Gretton, K. Fukumizu, Z. Harchaoui, and B. K. Sriperumbudur. A fast, consis-
          tent kernel two-sample test. In Y. Bengio, D. Schuurmans, J. D. Lafferty, C. K. I.
          Williams, and A. Culotta, editors, Advances in Neural Information Processing Systems
          22, pages 673–681. Curran Associates, Inc., 2009. URL http://papers.nips.cc/paper/
          3738-a-fast-consistent-kernel-two-sample-test.pdf.
[Gui11]   M. Guidolin. Markov switching models in empirical finance. In Missing data methods: Time-
          series methods and applications. Emerald Group Publishing Limited, 2011.
[Ham89]   J. D. Hamilton. A new approach to the economic analysis of nonstationary time series and
          the business cycle. Econometrica: Journal of the econometric society, pages 357–384, 1989.
[HGER15] K. Henderson, B. Gallagher, and T. Eliassi-Rad. Ep-means: An efficient nonparametric
          clustering of empirical probability distributions. In Proceedings of the 30th Annual ACM
          Symposium on Applied Computing, pages 893–900, 2015.
[HMT19]   B. Horvath, A. Muguruza, and M. Tomas. Deep learning volatility. Available at SSRN
          3322085, 2019.
[KMN+ 02] T. Kanungo, D. M. Mount, N. S. Netanyahu, C. D. Piatko, R. Silverman, and A. Y. Wu.
          An efficient k-means clustering algorithm: Analysis and implementation. IEEE transactions
          on pattern analysis and machine intelligence, 24(7):881–892, 2002.
[KNS+ 19] S. Kolouri, K. Nadjahi, U. Simsekli, R. Badeau, and G. K. Rohde. Generalized sliced wasser-
          stein distances. arXiv preprint arXiv:1902.00434, 2019.
[KSH20]   A. Kondratyev, C. Schwarz, and B. Horvath. Data anonymisation, outlier detection and
          fighting overfitting with restricted boltzmann machines. Outlier Detection and Fighting
          Overfitting with Restricted Boltzmann Machines (January 27, 2020), 2020.
[Kua02]   C.-M. Kuan. Lecture on the markov switching model. Institute of Economics Academia
          Sinica, 8(15):1–30, 2002.
[Lah16]   S. Lahmiri. Clustering of casablanca stock market based on hurst exponent estimates. Phys-
          ica A: Statistical Mechanics and its Applications, 456:310–318, 2016.
[LM00]    T. Lux and M. Marchesi. Volatility clustering in financial markets: a microsimulation of
          interacting agents. International journal of theoretical and applied finance, 3(04):675–702,
          2000.
[LR09]    T. Lange and A. Rahbek. An introduction to regime switching time series models. In Hand-
          book of Financial Time Series, pages 871–887. Springer, 2009.
[LW08]    J. Li and J. Z. Wang. Real-time computerized annotation of pictures. IEEE transactions
          on pattern analysis and machine intelligence, 30(6):985–1002, 2008.
[MMS12]   J. Maheu, T. McCurdy, and Y. Song. Components of bull and bear markets: Bull cor-
          rections and bear rallies. Journal of Business and Economic Statistics, 30, 07 2012.
          doi:10.2139/ssrn.1939486.
[MS83]    D. M. Mason and J. H. Schuenemeyer. A modified kolmogorov-smirnov test sensitive to tail
          alternatives. The annals of Statistics, pages 933–946, 1983.
[MZGW18] L. Mi, W. Zhang, X. Gu, and Y. Wang. Variational wasserstein clustering. In Proceedings
          of the European Conference on Computer Vision (ECCV), pages 322–337, 2018.
[NHZ16]   Y. S. Niu, N. Hao, and H. Zhang. Multiple change-point detection: a selective overview.
          Statistical Science, pages 611–623, 2016.
[NN09]    F. Nielsen and R. Nock. Sided and symmetrized bregman centroids. IEEE transactions on
          Information Theory, 55(6):2882–2904, 2009.
[NNA14]   F. Nielsen, R. Nock, and S.-i. Amari. On clustering histograms with k-means by using mixed
          α-divergences. Entropy, 16(6):3273–3301, 2014.
[NSW+ 20] H. Ni, L. Szpruch, M. Wiese, S. Liao, and B. Xiao. Conditional sig-wasserstein gans for time
          series generation, 2020, 2006.05421.
[Pel06]   D. Pelletier. Regime switching for dynamic correlations. Journal of Econometrics, 131(1):445
          – 473, 2006. doi:https://doi.org/10.1016/j.jeconom.2005.01.013.
[Rou87]   P. J. Rousseeuw. Silhouettes: A graphical aid to the interpretation and validation of
          cluster analysis. Journal of Computational and Applied Mathematics, 20:53–65, 1987.
          doi:https://doi.org/10.1016/0377-0427(87)90125-7.
[RPDB11] J. Rabin, G. Peyré, J. Delon, and M. Bernot. Wasserstein barycenter and its application
          to texture mixing. In International Conference on Scale Space and Variational Methods in
          Computer Vision, pages 435–446. Springer, 2011.
[RT99]    S. Ray and R. H. Turi. Determination of number of clusters in k-means clustering and
          application in colour image segmentation. In Proceedings of the 4th international conference
            CLUSTERING MARKET REGIMES USING THE WASSERSTEIN DISTANCE                              37

         on advances in pattern recognition and digital techniques, pages 137–143. Calcutta, India,
         1999.
[RY04]   D. Revuz and M. Yor. Continuous Martingales and Brownian Motion. Grundlehren der
         mathematischen Wissenschaften. Springer Berlin Heidelberg, 2004. URL https://books.
         google.co.uk/books?id=1ml95FLM5koC.
[San15]  F. Santambrogio. Optimal Transport for Applied Mathematicians. Calculus of Variations,
         PDEs and Modeling. 2015.
[Ste01]  I. Steinwart. On the influence of the kernel on the consistency of support vector machines.
         Journal of machine learning research, 2(Nov):67–93, 2001.
[Syn08]  D. Synowiec. Jump-diffusion models with constant parameters for financial log-return
         processes. Computers and Mathematics with Applications, 56(8):2120 – 2127, 2008.
         doi:https://doi.org/10.1016/j.camwa.2008.02.051.
[Vel02]  R. Veldhuis. The centroid of the symmetrical kullback-leibler distance. IEEE signal process-
         ing letters, 9(3):96–99, 2002.
[WGX21]  J. Wang, R. Gao, and Y. Xie. Two-sample test using projected wasserstein distance: Break-
         ing the curse of dimensionality, 2021, 2010.11970.
[YWWL17] J. Ye, P. Wu, J. Z. Wang, and J. Li. Fast discrete distribution clustering using wasserstein
         barycenter with sparse support. IEEE Transactions on Signal Processing, 65(9):2317–2332,
         2017.