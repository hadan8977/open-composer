source: https://arxiv.org/pdf/2601.03974
fetched_utc: 2026-10-04T18:44:04Z
bytes_raw: 1826833

Class of topological portfolios: Are they better
                                                        than classical portfolios?

                                                 Anubha Goel1 , Amita Sharma2*† , Juho Kanniainen1†
                                           1 Computing Sciences/Financial Computing and Data Analytics Group,
arXiv:2601.03974v1 [q-fin.PM] 7 Jan 2026




                                                                   Tampere University, Finland.
                                           2* Department of Mathematics, Netaji Subhas University of Technology,

                                                                                 India.


                                              *Corresponding author(s). E-mail(s): amita.sharma@nsut.ac.in;
                                            Contributing authors: anubha.goel@tuni.fi; juho.kanniainen@tuni.fi;
                                                † These authors contributed equally to this work.

                                                          Pre-Accepted in Financial Innovation


                                                                               Abstract
                                            Topological Data Analysis (TDA), an emerging field in investment sciences, har-
                                            nesses mathematical methods to extract data features based on shape, offering
                                            a promising alternative to classical portfolio selection methodologies. We uti-
                                            lize persistence landscapes, a type of summary statistics for persistent homology,
                                            to capture the topological variation of returns, blossoming a novel concept of
                                            “Topological Risk”. Our proposed topological risk then quantifies portfolio risk
                                            by tracking time-varying topological properties of assets through the Lp norm of
                                            the persistence landscape. Through optimization, we derive an optimal portfo-
                                            lio that minimizes this topological risk. Numerical experiments conducted using
                                            nearly a decade long S&P 500 data demonstrate the superior performance of
                                            our TDA-based portfolios in comparison to the seven popular portfolio optimiza-
                                            tion models and two benchmark portfolio strategies, the naive 1/N portfolio
                                            and the S&P 500 market index, in terms of excess mean return, and several
                                            financial ratios. The outcome remains consistent through out the computational
                                            analysis conducted for the varying size of holding and investment time horizon.
                                            These results underscore the potential of our TDA-based topological risk met-
                                            ric in providing a more comprehensive understanding of portfolio dynamics than


                                                                                    1
     traditional statistical measures. As such, it holds significant relevance for modern
     portfolio management practices.

     Keywords: Investment analysis, Topological Data Analysis, Topological Risk,
     Markowitz portfolio




1 Introduction
The Markowitz model or mean-variance model [1], which accounts for variance as
its underlying risk measure, relies heavily on moment estimation, often leading to
poor and unstable out-of-sample performance ([2], [3], [4], [5], [6]). Indeed, some prac-
titioners consider the concept of optimality proposed by modern portfolio theory
questionable within the volatile and non-stationary environment of financial security
returns [7]. The degradation in out-of-sample performance of mean-variance portfolios
due to estimation errors is so significant that it struggles to consistently outperform
even the simplest naive 1/N strategy, which allocates equal weights to all compo-
nents of the portfolio [8]. Further, if the covariance matrix of the asset returns is
rank-deficient, the mean-variance model does not have a unique solution. Even when
the number of assets is close to the number of observations, the sample covariance
matrix approaches a singularity and hence not a consistent estimator to the population
covariance matrix.
Several methods have been suggested to reduce estimation errors in the mean-variance
model. For instance, Bayesian and shrinkage techniques ([9], [10], [4], [5]) aim to
mitigate errors in estimating parameters. Some studies opt for a different approach
altogether, by excluding the mean return function from the model (known as the
global minimum variance model), thus eliminating mean estimation errors ([11], [12],
[13]) or imposing weight norm constraint [8]. Alternatively, researchers have explored
translating the mean-variance model into its robust version by defining uncertainty
sets for the mean vector and covariance matrix ([14], [15]). These sets encapsulate a
range of possible values for these parameters, making resulting models more resilient.
Despite their statistical underpinnings, all these approaches, whether directly or indi-
rectly, grapple with estimation errors. Moreover, as [16] argues, robust optimization
methods can lead to portfolios with inferior out-of-sample results.
This paper presents a novel approach to portfolio diversification that smartly avoids
model-based estimation errors, i.e., the estimation error linked to distributional
assumptions or statistical inputs like mean and covariance, by focusing on minimizing
the portfolio’s topological risk. Our approach holds significant potential in scenar-
ios characterized by a high degree of model uncertainty accompanied by substantial
estimation errors. Topological Data Analysis (TDA) is employed to process high-
dimensional complex data and produce a simplified, low-dimensional representation
that preserves critical topological attributes, such as shape and connectivity. This
allows for the extraction of quantitative homological features, reflecting the topological


                                              2
variability of returns. In this paper, to capture the topological variation of returns,
we utilize the norms of persistence landscapes, which are summary statistics for per-
sistent homology introduced by [17]. An advantage of using persistence landscape is
that it has a function form, and thus the theory of random variables can be applied
in vector spaces defined by it.
The basic idea of persistent homology is to connect points step-wise that are “rela-
tively close together” and thereby examining the homology of the resulting shape. The
number of connections added at each step depends on a subjective parameter, dictat-
ing the desirable closeness. Such network created at each step is called a simplicial
complex. The persistent diagram is a 2-dimensional graph of birth (appearance) and
death (disappearance) of a feature in the Euclidean plane where (b, d) = (birth, death).
Due to the incompleteness of the metric space induced by the persistent diagram, an
alternative topological summary called persistent landscape, is developed to convey
similar information as the persistence diagram. An important technical hallmark of
the persistent landscape is that it is a function and its function space forms a sepa-
rable Banach space, therefore, the theory of random variables can be well defined in
such space ([18], [17]). Furthermore, persistence landscape is a sequence of piecewise-
linear functions which makes them more computationally efficient in comparison to
the persistence barcodes (or diagrams) in analyzing the data ([18], [17]).
Staging the background of TDA, we intend to design an optimal portfolio via persistent
landscape to capture the insight of each asset return dynamic in a better way than
the traditional risk measures. We believe that as long as the portfolio selection process
depends on a statistical-based risk measure to capture uncertainty in asset’s return, be
it variance, mean-absolute deviation [19], or quantiles [20], it continues to suffer from
estimation error resulting in non-robust and unstable outcomes ([11], [21], [22] [23]).
Additionally, none of the individual risk measures can capture the hidden qualitative
properties of asset return time series data such as shape and structure. To achieve
reliability with respect to estimation error and feature extraction, we define a new
TDA-based risk measure of a portfolio named as “Topological Risk” that aims to track
the dynamic of topological properties for each asset. More precisely, the aim is to
dynamically monitor the topology of each asset and the risk of an asset is assessed
based on the changes in its topology over time.
Our scheme focuses on assessing and quantifying the topological risk of individual
assets, a critical factor in portfolio management. Specifically, we introduce the concept
of topological risk for each asset, defined as the squared error between its persistence
landscape norms and a reference point, the mean persistence landscape norm. Under
the vector space structure of the persistence landscape, its mean which is a point-
wise mean, is a well-defined function [17]. The method involves dividing each training
period into overlapping sub-windows and employing Takens embedding to convert
asset return data into a multivariate matrix. These matrices form input point clouds for
persistent homology analysis. For each asset and a sub-window, we extract topological
features using persistence diagrams and derive persistence landscapes, resulting in
a series of landscapes for each window. The topological risk for each asset is then
calculated as the variation of the persistence landscapes from the mean landscape,


                                           3
using the Lp norm. This comprehensive approach provides a nuanced understanding of
asset topological risk, enabling investors to make informed decisions regarding portfolio
composition and risk management strategies.
Upon calculating the topological risk Λi ≥ 0 of each asset i; i = 1, . . . , n, the topo-
logical risk of a portfolio w = (w1 , . . . , wn ) comprising n assets (where wi denotes
the proportion of total
                    Pn budget to be invested in i-th asset) is then quantified via a
quadratic function i=1 Λi wi2 . Therefore, for a polyhedron set of feasible portfolios,
minimizing the topological risk of a portfolio w is a convex program and attains its
global optimal solution. An empirical analysis to investigate the financial benefit of
the proposed scheme is carried on the sample data of daily closing prices of the con-
stituents from S&P 500 (U.S) with the sample period of nearly 10 years from December
10, 2012, to August 11, 2022. The S&P 500, a stock market index comprising 500
large-capitalization companies listed on US stock exchanges, serves as a global bench-
mark for the majority of economies. For the comparative analysis purpose, we consider
seven famous traditional portfolio optimization (PO) models, namely the global min-
imum variance model, the mean-variance model, the mean-value at risk model [24],
the mean-conditional value at risk model [25], the reward-risk PO model maximizing
Sharpe ratio [26], the reward-risk PO model maximizing STARR ratio [27], and the
reward-risk PO model maximizing Omega ratio [28] along with the two benchmark
portfolios, the 1/N naive portfolio [6] and the market index S&P 500.
We consider several financial ranking measures including excess mean return, standard
deviation, downside deviations, Sharpe ratio, Sortino ratio, STARR ratio, and Rachev
ratio to assess the performance of all considered models. Under the current setting,
we notice excel performance of the proposed scheme in comparison to all other mod-
els in almost all financial measures considered, showing the reliable outcomes when
our scheme is implemented in practice. Furthermore, our findings are consistent with
those presented in [8], wherein it is observed that the out-of-sample Sharpe ratio of the
sample-based mean-variance strategy is lower than that of the 1/N strategy. This sug-
gests that errors in estimating means and covariances negate the benefits of optimal
diversification compared to naive diversification. However, we have devised a strat-
egy that improves portfolio performance by incorporating topological risk associated
with each asset, rather than simply evenly distributing wealth among them (Naive
Strategy).
The main contributions of the paper are summarized as follows:

• Conceptual contribution: While the use of TDA in analyzing financial time series
  is not entirely novel, its application in portfolio construction remains a relatively
  underexplored area. Contributing to the growing literature on TDA in finance,
  we introduce the concept of Topological Risk for the first time—a risk measure
  that is entirely independent of traditional statistical metrics. We utilize persistence
  landscapes, a summary statistic derived from persistent homology, to capture the
  topological variation in asset returns. The proposed optimization model minimizes
  this topological risk and is formulated as a quadratic program, thus preserving
  computational efficiency.


                                           4
• Empirical contribution: We evaluate the performance of our proposed TDA-based
  model using nearly a decade of S&P 500 data. The financial benefits of the TDA
  approach are compared against seven classical PO models (ranging from mean-risk
  to return-reward ratio models), as well as two benchmark portfolios: the naive 1/N
  portfolio and the S&P 500 index. An extensive empirical analysis is conducted using
  a rolling window scheme with varying window sizes to assess robustness. Specifi-
  cally, we consider two in-sample periods (1 year and 2 years) and four out-of-sample
  horizons (1 month, 3 months, 6 months, and 1 year), resulting in a total of eight
  different evaluation settings. Across all scenarios, the TDA-based portfolios consis-
  tently outperform the benchmarks in terms of excess mean returns and risk-adjusted
  performance ratios, demonstrating the significance of TDA in modern portfolio
  management practices.

The rest of the paper is organized as follows: Section 2 presents the literature reviews;
Section 3 gives the basics of TDA tools; Section 4 explains the proposed scheme;
Section 5 and Section 6 respectively, explain the empirical analysis and robust analysis
of the computational study; and the paper concludes in Section 7.

2 Literature Review
The core of modern portfolio theory is to make an optimal trade-off between return
and risk, where return is generally estimated by the first order moment of underlying
distribution (mean return), risk can be defined by different measures in order to cap-
ture most of the uncertainty in the data. Statistical risk measures such as variance [1],
mean-absolute deviation [19], Gini mean difference [29], and central semi-deviations
[30], aim to deal with the deviations around mean return, whereas the tail risk mea-
sures namely, quantiles [31] and conditional-value-at-risk [32], focus on the risk of large
losses. One can choose the risk measure that matches with his objective of portfolio
or after a brief discussion with his portfolio manager.
Traditionally, while optimizing the trade-off between mean return and underlying risk
function in practice, the unknown model parameters (or distribution) are replaced by
their sample estimations (or some empirical distribution such as uniform distribution)
[33]. This results into unstable, and non-robust portfolio weights, for example, it is well
known that the simplest naive 1/N strategy outperforms the mean-variance portfolios
([8], [34], [35]). Further, the portfolio optimizers are often called as “error-maximizers”
[36], and the mean-variance model can produce extreme weights ([37], [8]). Though,
it is commonly believed that estimation errors due to mean terms are of much greater
significance than covariance terms ([11]; [38]) yet errors due to covariances can also
have hefty impact. As it is comparatively easier to estimate covariances than means,
the presence of heavy tails in distributions can result in substantial errors in the
covariance estimates too [39]. The estimation problem is even more severe for high-
dimensional data when the size of portfolio exceeds the sample size. In such case, the
sample covariance matrix is no longer a consistent estimator for the true population
matrix, causing deviation of traditional portfolio weights from the population ones



                                            5
[40]. Neverthless, the mean-variance PO model has a significant impact on academic
research and the financial industry as a whole [35].
In light of the inherent limitations of conventional PO frameworks, this work employs
Topological Data Analysis (TDA) to formulate a risk measure that not only eliminates
dependence on distributional assumptions but also effectively captures the dynamic
structure of asset returns, with robustness to noise. TDA is a set of mathematical tools
from algebraic topology for data visualization and feature extraction ([41], [42], [43],
[17], [44]). An excellent overview and literature on TDA may be referred to ([41], [42])
and a recent article on biomedicine by [45]. The applications of TDA are wide, rang-
ing from biomedical [45], signal processing [46], image recognition [47], neuroscience
[48], time series analysis [49] to social sciences [50]. TDA tools take high-dimensional
complex data as input and result in a simpler low-dimensional representation while
retaining significant topological features related to its shape and connectivity.
The two fundamental TDA methods are Persistent Homology and Mapper, where the
former is useful for generating quantitative representation of homological features such
as connected components or higher-dimensional holes whereas the latter constructs a
compact optical summary, suitable for exploratory data analysis.
As an application to persistent homology, work of classifying patients with chronic
obstructive pulmonary disease can be seen in [51], analyzing protein folding in [52] and
examining the epidemiology of specific diseases can be referred to [53]. Continuing with
the charm of TDA, it witnesses its wide range of applications in the shape analysis
([54]; [55]), sensor networks ([56]; [57]), dynamic systems and signal processing ([58]),
and amalgamation of machine learning tools with TDA [59].
Tasting a great success in the above several listed fields, TDA extends its beauty
in the area of time series analysis which was earlier relatively underdeveloped. In
particular, equipped with the notions of birth and death for features appearing and
disappearing, persistent homology is a more logical way to analyze time-changing
factors of data. Early research on applying persistent homology to time series analysis
includes ([60], [61], [62], [63]), with specific attention to financial time series seen in
([64], [65], [66], [67], [68], [69], [70], [71], [72]). However, applications in PO are much
less common, with only a few studies such as ([73], [74]) exploring this area. In the field
of financial time series analysis, an important class of applications of TDA concerns
critical transitions in financial time series, for instance, [67] develop a TDA-based
method to detect early signs for critical transitions in financial time series data. They
use persistent homology to investigate stocks during a period prior to the US financial
crisis of 2007-2008, and find the presence of early signs of the critical transition whereas
authors in [72] present a heuristic argument for the tendency of TDA to detect financial
bubbles. As an illustration, [72] use their proposed approach on a sample of positive
and negative bubbles in the Bitcoin historical price. [64] investigate the relationship
of TDA’s barcodes with the financial risk measures, such as growth rate, volatility,
and correlation coefficients over the time series data of NIKKEI 225 in 2014 and 2015.
Their results support the effectiveness of TDA as a risk measure, utilizing barcodes
to detect the rapid change in a short time.



                                             6
[75] demonstrate a link between persistence norms and uncertainty (observed and
unobserved uncertainty). Clues from the dynamic analysis of the persistence norm
and uncertainty relationship supports that the persistence norms provide a signal of
impending market crashes, therefore, persistence norms have potential as a further
tool in asset pricing. Next, the authors in [70] propose to combine persistent homology
with k-means clustering to detect early warning signals of the January 2018 digital
asset market crash, studying the movements of four major cryptocurrencies (Bitcoin,
Ethereum, Litecoin, and Ripple) whereas [66] apply TDA techniques to investigate
financial crashes for the two cryptocurrencies, Bitcoin and Ethereum for the same
duration of digital asset market crash, 2018. [66] demonstrate good early warning
signals before the crashes and show that the L1 and C1 -norms of persistent landscapes
peak before the occurrence of crashes. Continuing with studying the transitions in
digital market systems, [76] employ persistent homology method, based on the high-
frequency price data of the ten major cryptocurrencies, to study the evolution of the
topological structural features of the cryptocurrency system over time. [69] propose to
use persistent homology and time delay embedding for time series classification and
clustering. Their findings show that the topological features of the time series of stock
prices over different sectors are not same and have distinctive features that can be
make out effectively via TDA.
In the area of PO, [74] propose to use persistent homology with an application of
enhanced indexing, an investment strategy that seeks to outperform the benchmark
index. The proposed method executes in two stages: filtering of assets based on Lp
norms of the persistence landscapes values and thereafter, solving an optimization
problem to generate an optimal portfolio. The authors test the efficiency of the pro-
posed algorithm over ten data sets from financial markets across the globe and reported
favorable outcomes. Very recently, [73] utilize persistence homology to create a sparse
index tracking portfolio. They consider minimizing the objective function with the
weighted Elastic-Net terms and propose to learn its regularization coefficients using
Lp norms of persistence landscape for robust outcomes. They also verify their results
using a data set that covers 23 years of the S&P 500 index. Related studies are
also applied persistent homology to analyze market structure and improve portfo-
lio strategies. [77] construct a turbulence index by computing Wasserstein distances
between persistence diagrams at different time points to detect regime shifts in finan-
cial markets, and then use this index to inform portfolio allocation. [78] develop a
similar regime-detection framework based on the normed differences between persis-
tence landscapes over time, identifying periods of heightened topological change that
signal turbulent market conditions. While these studies are developed with reference
to specific benchmarks or regime-detection contexts, the current study introduces the
novel concept of topological risk to optimize portfolio in a more general context. We
employ persistence landscapes to capture the topological variation of asset’s returns,
giving parameter free risk measure. The study also extends to incorporate the effect
of cardinatility constraint in the proposed PO model minimizing topological risk. An
extensive empirical analysis over varying window size confirms the outperformance of
the proposed scheme in comparison to several well established PO models.



                                           7
3 Overview of Topological Data Analysis
Under the discrete time framework of total T scenarios, let ri (t) represents the return
of the i-th asset at time point t; t = 1, 2, . . . , T . Then the time series Xi = {ri (t)}Tt=1
of window size T represents a univariate time series for each i-th asset; i = 1, 2, . . . , n.
Since TDA works on point clouds and the one-dimensional time series like Xi , fails
to have point cloud representations ([65], [74]) in general, therefore, we first embed
the time series into its corresponding high-dimensional space (point clouds) using the
time-delay coordinate embedding or Takens’ embedding ([79]).
As a specimen, a time series X = {r1 , r2 , . . . , rT }, can be reconstructed in phase space
in time as follows:
                                                                            
                        R1                r1             r1+τ . . .  r1+(d−1)τ
                       R2              r2             r2+τ . . .  r2+(d−1)τ 
             R=               =                                             ,         (1)
                                                                            
                         ..                 ..               ..          ..
                         .                .                .           .    
                    RT −(d−1)τ      rT −(d−1)τ rT −(d−2)τ . . .         rT

where τ is the time delay, d is the dimension of reconstructed space (embedding
dimension), T − (d − 1)τ is the number of points (states) in the phase space where
each point in the space is represented by a row of the matrix R. So, conceptually,
the association between the time series and the constructed point clouds is known
as the Takens’ embedding. The Takens’ embedding has now become a useful tool to
connect a variety of time series with persistent homology by converting the former
into a meaningful depiction of the point cloud ([80], [81], [82]) while preserving the
topology during the process [79].
We then propose to obtain a simplicial complex for a given point cloud using the
Vietoris-Rips method. A simplicial complex, S, is a collection of finite sets (called
simplices) that satisfy two essential conditions: (i) Any face of a simplex from S is
also in S. In other words, if α ∈ S and β ⊂ α, then β ∈ S. Here, if k = |α| − 1, α is
called a k-simplex, and β ⊂ α is known as a face of α. (ii) The intersection of any two
simplices in S is either empty or shares faces. Vietoris-Rips complex is among some of
the popular procedures to construct a simplicial complex by connecting the pairs of
points (vertices) in a given point cloud that are sufficiently close as described by the
following definition:
Definition 1. The Vietoris-Rips complex of R with a parameter ϵ > 0 is defined to be
the simplicial complex denoted by Rϵ (X) satisfying {R1 , R2 , . . . , Rl } ∈ Rϵ (X) if and
only if Diam (R1 , R2 , . . . , Rl ) < ϵ where diam is the largest distance between any two
points in the set.
The general idea of this procedure is to connect points that are relatively close together
and then examine the homology of the resulting shape. A natural question is how
to select the value for ϵ in the Vietoris-Rips complex procedure while connecting the
points as it can greatly affect the topological features in the complex. For example,
for smaller values of ϵ we might see no edges whereas for large values, every point is
connected to every other point leaving just one connected component and therefore,


                                              8
has no topological features of interest in both of the cases. Thankfully, TDA provides
an efficient way for the right selection of ϵ by computing the shape of a point cloud
over its entire range and studying the topological structure as a function of ϵ rather
than taking any of its random value. Consequently, we get a sequence of Vietoris-
Rips simplicial complexes corresponding to different values of ϵ, named as Vietoris–
Rips filtration, and is denoted by {Rϵk (X)}k∈N , for a non-decreasing sequence {ϵk } ∈
R+ ∪ {0} with ϵ0 = 0. The intuition behind this procedure is that via a “discrete”
filtration of simplicial complexes associated with a finite number of parameters 0 <
ϵ1 < ϵ1 < . . . < ϵk , one can track the topological features (connected components,
holes, etc.) that persist throughout the filtration. To achieve the same, each topological
feature is given a ‘birth’ (appear) and ‘death’ value (disappear) during the filtration
process and the difference between the birth and death values represents the feature’s
persistence in the corresponding filtration. The topological features that persist over a
wider range of scales (ϵ) are considered the most significant and representative of the
shape of the point cloud. This process of tracking and analyzing the changes in the
topological features of complex data across multiple resolutions is known as persistence
homology (see [73] for a visual illustration of this process).
Once we obtain the Vietoris-Rips filtration, it is time to summarize the persistence
of topological features (or persistent homology). The two most common topological
summaries of the data are: persistent barcodes and the persistence diagram. The
persistence barcode contains horizontal lines, called bars, in which each bar begins
at some feature’s birth and ends at its death. The same information can also be
represented by the persistence diagram which is a graph in the Euclidean plane where
(b, d) = (birth, death). Mathematically, persistence diagram is a multi-set of points
in W × {0, 1, . . . , q − 1}, where W := {(b, d) ∈ R2 : d ≥ b ≥ 0} and each element
(b, d, f ) represents a homological feature of dimension f that appears at scale b during
a Vietoris–Rips filtration and disappears at scale d. Intuitively speaking, the feature
(b, d, f ) is a f -dimensional hole lasting for duration d − b, called persistence. Namely,
features with f = 0 correspond to connected components, f = 1 to loops or holes, and
f = 2 to voids.
In other words, a persistence diagram (or barcode) offers more than a traditional
summary statistic by showing not only the number of persistent features but also
when they appear and overlap along the filtered simplicial complex. Having said that,
the persistence diagram is of limited use when equipped with Wasserstein distance as
it forms an incomplete metric space and therefore, is not appropriate to apply tools
from statistics. An alternative topology summary called the persistence landscape,
proposed by [17], has a function form. Thus, the vector space structure can be used for
its underlying function space. Additionally, computations with a persistence landscape
are much faster than the persistence diagram, removing a second obstruction to the use
of topological methods in data analysis. The other methods to embed the persistence
diagrams are persistence image, or kernel-based methods such as persistence scale
space kernel, to name a few. One can refer to ([41], [65], [83]) for more description.
The persistence landscapes are sequences of piecewise-linear functions, defined on a re-
scaled birth-death coordinate with the peaks representing the significant topological


                                            9
features. Mathematically, with each birth-death pair p(a, b) ∈ D, where D is the
persistence diagram, a piece-wise linear function Λp : R → [0, ∞) is associated as
follows:
                                  
                                                   a+b
                                   t − a t ∈ [a, 2 ]
                                  
                                  
                          Λp (t) = b − t t ∈ [ a+b2 , b]
                                                                               (2)
                                  
                                  
                                  0        otherwise.


A persistence landscape of the birth-death pairs pi (ai , bi ), i = 1, . . . , m, is the sequence
of functions η : N × R → [0, ∞), as η(k, t) = ηk (t) where ηk (t) denotes the k-th largest
value of {Λpi (t), i = 1, . . . , m}. We set ηk (x) = 0 if the k-th largest value does not
exist; so, ηk (t) = 0 for k > m. The persistence landscapes form a subset of the Banach
space Lp (N × R) consisting of sequences η = (ηk )k∈N . This set has an obvious vector
space structure ([65]), and it becomes a Banach space when endowed with the norm


                                                ∞
                                                                  ! p1
                                                X
                                   ||η||p =           ||ηk ||pp          ,                   (3)
                                                k=1


where || · ||p is the Lp -norm. Further, it is shown in [17] that the persistence landscape
is stable with respect to the Lp norm for 1 ≤ p ≤ ∞.
Forming a separable Banach space, the mean of the landscape has a well-defined
function form as proposed by [17]. Formally, for a random variable Z defined on
some underlying probability space (Ω, F, P ), with corresponding persistence landscape
η, with values in the separable Banach space Lp (S); 1 ≤ p ≤ ∞, S = R i.e., for
w ∈ Ω, X(w) is the data and η(w) = η(X(w)) =: η is the corresponding topological
summary statistic. Further let X1 , . . . , XM be independent and identically distributed
random variables with corresponding persistence landscapes η 1 , . . . , η M . Then the
mean landscape η̄ is given by the following pointwise mean:


                                                      M
                                                1 X i
                                   η̄(k, t) =         η (k, t)                               (4)
                                                M i=1


and the norm of the mean landscape is as follows:


                                              ∞
                                                                     ! p1
                                              X
                                ||η̄||p =           ||η̄(k, t)||pp           ,               (5)
                                              k=1




                                                 10
where || · ||p is the Lp -norm.
With the above-mentioned crucial framework of TDA, we have now come to the point
to explain our proposed strategy particularly, incorporating the persistence landscape
to define the risk of a portfolio comprising assets with uncertain returns.

4 Proposed TDA-based Scheme
Persistence homology captures the shape of data across multiple resolutions. On apply-
ing a sliding window approach to a time series, resulting point cloud encodes the
dynamic behaviors of topological features such as connected components, cycles and
other structural changes. The stability of persistent homology of the point cloud under
small perturbations makes this approach suitable for analyzing financial time series.
The method can be used, for example, for detection of critical transitions (tipping
points). Persistence landscape, a summary statistics for persistent homology intro-
duced by [18], is a powerful tool to quantify “topological activities”, i.e., the behavior
of shape of data over time. For instance, higher fluctuations in time series often result
in more complex topological structures resulting in higher persistence norms. Further,
the higher the concentration (scattering) of the point cloud, and thus the more (less)
stable the returns over the subintervals from a topological point of view.
The amount of scatteredness among return observations over time can be thus effec-
tively quantified using Lp norm of persistence landscape called as TDA norm, with
its lower (higher) value corresponding to a higher concentration (scattering) of the
point cloud [73]. Therefore, the TDA norm can effectively track changes in the state
of stock return dynamics without using any prior distribution assumption. Moreover,
the persistence landscape 1 by definition involves no parameter and thus it is free from
parameter tuning and over-fitting risk [17]. The relevance of persistence norms as risk
indicators mentioned above is also supported by numerous empirical studies (see [84],
[65], [78], [66], [74], [73] ).
We now explain the procedure of calculating the topological risk contribution by
each asset followed by the necessary notation and optimization model minimizing the
topological risk of the portfolio.
Notation: Consider a set of n feasible assets A1 , A2 , . . . , An available for investment
                                                                                               ′
with uncertain respective future returns r1 , r2 , . . . , rn . Let w = (w1 , w2 , . . . , wn ) ∈ Rn
denotes a decision vector corresponding to portfolio allocation where wi denotes the
proportion of total budget to be investment in i-th asset i = 1, . . . , n. Asset topo-
logical risk: For a portfolio w consisting of n assets, the topological risk contribution
of the ith asset, where i = 1, . . . , n, is computed through the following steps:

• Given the return time series of the ith asset, denoted as Xi = ri (t)Tt=1 with a window
  size of T , the process of generating a sequence of persistence landscapes involves
  the following sequential steps:

  1
    Persistence landscape forms a Banach space and therefore, the theory of random variables can be applied
in such spaces which is a natural choice when dealing with the financial asset selection.



                                                    11
  (i) Obtain a set of point clouds by employing sub windowing technique and applying
      Takens embedding to each of the sub windows. We choose τ = 1 and d = 3
      following ([85], [78], [74], [86], [61]).
 (ii) Obtain Rips filtration corresponding to each point cloud.
(iii) Generate a persistence diagram based on the Rips filtration carried out in the
      previous step.
(iv) Finally transform the persistence diagrams to obtain persistence landscapes.
• We then obtain the corresponding series of persistence landscape p-norms for p =1
  from the persistence landscapes corresponding to each of the sub windows. The
  choice of p = 1 is motivated by ([87], [67], [74], [73]). Empirical validation for p = 1
  and p = 2 are generally found to yield similar results which is also consistent with
  our findings.
• The mean persistence landscape of ith asset and henceforth its norm is calculated
  using the equations (4) and (5), respectively. The mean persistence landscape serves
  as the reference persistence landscape and its norm, called as expected norm serves
  as the reference landscape norm.
• The asset topological risk for ith asset Λi ; i = 1 . . . , n, is then measured as the aver-
  age squared difference of its series of persistence landscape norm from its reference
  landscape norm2 .

Follow the detailed Algorithm 1 to get Λi ; i = 1, . . . , n.3 The topological risk is then
defined as follows:
Portfolio topological risk (PTR): For a portfolio allocation vector w =
                       ′
(w1 , w2 , . . . , wn ) ∈ Rn , its topological risk is defined as:

                                                    w′ Qw                                                     (6)


where Q = [Λi ]ni=1 is a diagonal matrix with ith diagonal entries corresponds to the
ith asset topological risk Λi ; i = 1, . . . , n, named as topological risk matrix. As by
definition Λi ≥ 0, ∀ i = 1, . . . , n, the topological risk matrix Q is a positive definite
matrix.
   2
     In this sequel, we define topological risk by quantifying the deviation of the norm of individual persistence
landscapes from the norm of the mean persistence landscape. This construction builds upon key properties
of persistence landscapes: they are stable under perturbations, admit a well-defined notion of expectation
in Banach space, and allow for direct computation of Lp norms. These properties collectively support
their use in defining a principled measure of variability across topological summaries. While our empirical
application centers on 0-dimensional persistence diagrams (H0 ), this is a modeling choice made for reasons
of interpretability and computational efficiency. Crucially, the definition of topological risk is not restricted
to H0 : it extends naturally to persistence landscapes derived from higher-dimensional features (e.g., H1 ,
H2 ). More broadly, the definition remains valid when applied to any suitable topological summary as long
as a meaningful notion of mean and deviation can be established akin to the approach outlined in this
context. The framework is thus broadly applicable, with the flexibility to incorporate richer topological
signals where appropriate.
   3
     Please refer to [73] for detailed algorithms on obtaining the Rips filtration (step 4), persistence diagrams
(step 5), and persistence landscapes (step 6).




                                                       12
      Algorithm 1: Algorithm to obtain the topological risk for all assets i = 1, . . . , n.
   Data: Time-series data Xi = {ri (t)}Tt=1 of M months, i.e., T = 21 × M , for a
           given constituent i ∈ {1, 2, . . . , n} of a portfolio w and a sequence of
           resolutions ϵ0 < ϵ1 < . . . < ϵN .
   Result: The series of deviation of the persistence landscape norm from the norm
             of mean persistence landscape
 1 Split time-series data into T overlapping sub-series of length T̃ days with a shift

    of h < T̃ days such that T = T −   T̃
                                      h + 1 (we use M = 12, T̃ = 126 and h = 21);
 2 for j = 0, 1, 2, . . . , T − 1 do

 3     Extract the sub-series {Ri,t }jh+  T̃
                                     t=jh+1 Apply Takens’ time-delay embedding with
                                                                                                                      (j)
           time delay τ and embedding dimension d to obtain point cloud Xi                                                  (we use
           τ = 1 and d = 3)

                                                            Ri,jh+1
                                                           . . . Ri,jh+1+(d−1)τ
                                                                               
                                                           Ri,jh+2
                                                           . . . Ri,jh+2+(d−1)τ 
                                    (j)
                                   Xi =                     .. ..       ..
                                                                               
                                                                                
                                                             .  .        .     
                                          Ri,jh+T̃ −(d−1)τ . . .     Ri,jh+T̃

                                                              (j)                                            (j)
 4        Compute Rips filtration {Rϵn (Xi )}n∈N for the point cloud Xi .
                                                                                                            (j)
 5        Compute persistence diagram DX (j) for the filtration {Rϵn (Xi )}n∈N .
                                                               i
                                                                   (j)
 6        Compute persistence landscape {ηi (k)} from the birth-death pairs
           {(bm , dm )}rm=1 corresponding to 0- dimensional components extracted from
           the persistence diagram DX (j) .
                                                        i
 7 end
 8 Compute the mean persistence landscapes {η i (k)} as follows:


                                                                         T −1
                                                                    1 X (j)
                                                      η i (k) =          η (k).
                                                                    T j=0 i

 9   Compute the corresponding p-norm (we use p = 1 and k = 1)

                     ∞
                                           ! p1                                 ∞
                                                                                                     ! p1
                                                                (j)                      (j)
                     X                                                          X
       ||η i ||p =         ||η i (k)||pp          , and      ||ηi ||p =               ||ηi (k)||pp          , j = 0, . . . , T − 1
 10                  k=1                                                        k=1

                      TX
                       −1                                    2
                                    (j)
11   Return Λi ←                 ||ηi ||p − ||η¯i n ||p            ,
                       j=0


                                                                                                                                n
                                                                                                                  ′
                                                                                                                                X
                                                                                                                            n
      For a polyhedron set of feasible portfolios W = {(w1 , w2 , . . . , wn ) ∈ R ;                                                  wi =
                                                                                                                                i=1
      1, wi ≥ 0} containing budget and no-short selling restrictions, the proposed optimiza-
      tion model minimizing the topological risk is then given by the following Quadratic
      program:                                13
                                     (TDA-PO) min wT Qw
                                         s.t. w∈W
The problem TDA-PO is a convex program and hence computationally efficient. For
a desired cardinality k of assets to select, an investor solves the following 0-1 form of
the proposed model:
                                    (TDA-IPO)            min wT Qw
                                                         n
                                                         X
                                                            zi = k
                                                         i=1
                                                0 ≤ wi ≤ zi ; zi ∈ {0, 1}, i = 1, 2, . . . , n.
Cardinality constraint allows an investor to enforce a specific number of stocks to
invest, avoiding both the cases of excessively diversified portfolios that may dilute
potential returns and under-diversified portfolios pertaining to higher market risk.
The proposed model TDA-PO (or TDA-IPO for cardinality condition) aims to min-
imize the topological deviation or instability of an asset’s persistence landscape
compared to its reference landscape as quantified by its norm. It is designed to cap-
ture the inherent topological properties of an asset’s behavior and quantify how far
its persistence landscapes deviate from the average landscape. A lower value of asset’s
topological risk indicates that its time-varied persistence landscape norms are closer
to the reference landscape norm, suggesting a more stable and predictable behavior.
Conversely, its higher value signifies a higher deviation from the reference landscape
norm, indicating potential topological instabilities or structural changes in the asset’s
behavior. By incorporating topological information, PTR provides additional insights
into an asset’s risk profile that might not be captured by traditional risk measures
based on statistical moments. Furthermore, by its definition, PTR is free from any
model-based estimation error and hence able to generate robust and stable out-of-
sample results which we also confirm numerically in our empirical section. Overall,
PTR can be a valuable risk measure in the context of portfolio management and asset
allocation.

4.1 Proposed Methodology
We now elucidate the methodology to carry out an empirical investigation of the
proposed study by detailing the sample data, sample period, rolling window scheme
and the seven benchmarked PO models considered for the comparative analysis.

4.1.1 Sample Data and Sample Period
The sample data contains daily closing prices of the S&P500 and its constituents over
a sample period spanning nearly 10 years from December 10, 2012, to August 11,
2022. The data is collected from Thomson Reuters Datastream 4 . Since the index’s
composition is time-varying, we follow the standard approach from the literature to
select the constituents. More precisely, we choose only those constituents for which the

 4
     Thomson Reuters Datastream is a licensed financial database and may require institutional access.



                                                    14
data is available for the whole period and drop the stocks with missing observations
from our analysis. This results in 462 constituents.
                                                                                 pc −pc
The daily return for i-th stock at t-th day is calculated as rit = itpc it−1 ; i =
                                                                                      it−1
1, . . . , n, t = 1, . . . , T, where pcjt and pcjt−1 are respectively, the closing prices at t-th
and (t − 1)-th day.

4.1.2 Rolling Window Scheme
To investigate the performance of all the portfolios, we utilize a rolling window
approach consisting of solving a sequence of problems, each taking into account an
in-sample period and an out-of-sample period, both of them measured in days. Each
optimal portfolio obtained by solving a model over the in-sample data is then eval-
uated in the corresponding out-of-sample data. The resulting out-of-sample return
is observed and recorded. The in-sample time horizon is then shifted ahead by the
number of weeks corresponding to the out-of-sample period to get the new in-sample
window, and the procedure is reiterated. We primarly employ a rolling window of 273
trading days (13 months) with an in-sample period of 252 trading days (12 months)
and an out-of-sample period of 21 trading days (one month) in line with [88, 89]. We
shift the window by 21 trading days (one month) at each rolling step, leading to a
total of 108 windows. To check the consistency of numerical outcomes from this win-
dow size setting, we re-investigate computational analysis for the varying window size
as briefly described in the section 6 under the heading of robust analysis.

4.1.3 Benchmarked PO Models for the Comparative Analysis
To check the efficacy of the proposed model TDA-PO, we compare its out-of-sample
results with the following seven famous traditional PO models from literature and two
benchmark portfolios, the naive 1/N portfolio and the benchmark index S&P 500:

1. Mean-variance (MP) model [1]
2. Global minimum variance model (GMV) [13]:
3. Mean-value at risk model (MVaR) [24]
4. Mean-conditional value at risk model (MCVaR) [25]
5. Sharpe model [26]
6. STARR model [27]
7. Omega model [90]

The mathematical detail of all the above seven benchmarked PO models is given in
the Appendix B. All the optimization problems including our proposed model (TDA-
PO) have been solved using R software with gurobi interface for integer programming
(see Appendix B for details on packages and libraries used).




                                               15
5 Results and Analysis
5.1 Descriptive Statistics
Table 1 presents the descriptive statistics for the benchmark index S&P 500 for the
considered period of 10 years from December 10, 2012, to August 11, 2022, con-
firming the typical stylized facts of financial time series, such as negative skewness
(asymmetry) and high kurtosis (heavy tails). Due to the large number of constituents,
presenting a complete table for descriptive statistics of each of the constituents is
impractical. Therefore, we show the histograms in Figures 1 summarizing the mean
return, the standard deviation, and the 0-dim landscape norm for all the 462 con-
stituents. The blue (black) line in each of the histograms represents the corresponding
mean (median) value of the statistic across all assets. The red line depicts the statistics
value corresponding to the Index S&P 500.

                                    Table 1 Descriptive statistics
                                    for the S&P500 index of 10
                                    years from December 10, 2012,
                                    to August 11, 2022

                                          Mean           4.31E-04
                                           Max            8.97E-02
                                           Min           -1.28E-01
                                         Std Dev          1.07E-02
                                         Skewness        -9.60E-01
                                         Kurtosis        1.92E+01
                                      10th percentile    -9.54E-03
                                      50th percentile    3.74E-04
                                      90th percentile    1.09E-02




5.2 Out-of-Sample Analysis
Table 25 records the out-of-sample results of the portfolios from the six models namely,
the proposed model TDA-PO and seven benchmarked PO models, GMV, MP, MVaR,
MCVaR, Sharpe, STARR, and Omega, and the two benchmark portfolio strategies, the
naive 1/N and the market index S&P 500, in terms of several performance measures
(see Appendix A) calculated over the out-of-sample period.
We summarize the observation from the Table 2 in below:

• Return performance in terms of EMR (Excess Mean Return): It is evi-
  dent from Table 2 that the proposed model, TDA-PO attains the highest value of
  mean return in comparison to all the other seven models and both the benchmark
  portfolio strategies. The model TDA-PO attains almost double mean return in com-
  parison to all the three variance-based models, i.e. GMV, MP, & Sharpe model, and

  5
    As we have a considerable number of windows for the considered data period, to provide comprehensive
details, we present the results based on the series created by concatenating the out-of-sample returns from
each optimal in-sample portfolio.



                                                    16
                                                                                           25
               20
      Assets




                                                                                Assets

                                                                                           15
               5 10




                                                                                           0 5
               0




                      −0.0005   0.0005                 0.0015                                    0.01       0.02    0.03    0.04   0.05

                                Mean returns                                                                  Standard Deviation




                                                  60
                                                  40
                                         Assets

                                                  20
                                                  0




                                                                0.005   0.010            0.015      0.020

                                                                  0−dim Landscape norm


Fig. 1 Mean returns, standard deviation, and 0-dim Landscape norm for all the constituents in the
period of study. The blue (black) line in each of the histograms represents the corresponding mean
(median) value of the statistic across all assets. The red line depicts the statistics value corresponding
to the Index


  the two tail-risk measure based models i.e. MVaR & MCVaR and from both the
  benchmark portfolio strategies. Interestingly, the proposed model TDA-PO which
  does not account for the mean return function explicitly, manages to get the high-
  est value of EMR in comparison to the all other PO models. The outperformance of
  the proposed model TDA-PO in terms of EMR shows its financial gains over other
  popular investment strategies.
  A key takeaway from these results is that TDA-PO structural advantage does not
  stem from chasing returns but rather from efficiently adapting to market dynamics.
  By constructing portfolios without imposing rigid return-based constraints, TDA-
  PO enhances return stability while mitigating reliance on historical mean return
  estimates, which are often unreliable in real-world investment settings.
• Risk analysis in terms of stdev, DD, VaR0.95 , CVaR0.95 , PTR: The risk
  measure standard deviation (stdev) captures the variation of portfolio return around
  its mean values while the other risk measures, DD, VaR0.95 , and CVaR0.95 focus
  on the downside risk performance of the model. On the other hands, PTR tells the
  presence of topological risk (or variation in the topological features over the time)
  in the out-of-sample returns. We can notice from Table 2 that the proposed model
  TDA-PO achieves less amount of risks in terms of risk measures (stdev, DD, VaR0.95 ,
  and CVaR0.95 ) in comparison to the STARR model, Omega model, and the naive
  1/N portfolio. While comparing with the variance-based models, i.e. the GMV, MP,


                                                                         17
Table 2 Comparison analysis: Out-of-sample performance matrices obtained over rolling window scheme from the eight optimiz
models and two benchmark portfolio strategies. The best values (second best values) are highlighted in bold (italics) for the rea
convenience. The ∗ is used to mark the significant values in the statistical tests for the Sharpe ratio at 90% confidence level for
TDA PO model vs others. Values highlighted in red represent performance metrics that are statistically inferior to those of the
portfolio at the 95% confidence level, with respect to risk measures: variance, VaR0.05 , and CVaR0.95 . Acronyms of the metrics
expanded and defined in the Appendix A. The Assets are averages of total assets with non-zero weights across different window

Metric        TDA PO           GMV            MP        Sharpe    STARR        Omega      MCVaR         MVaR         Naive       I
                                  In-sample period = 1 year, Out-of-Sample period = 1 month
EMR          6.330E-04    2.036E-04  2.343E-04 2.101E-04 4.658E-04 4.696E-04    2.693E-04 2.087E-04 3.601E-04 3.655
Min          -1.447E-01 -8.943E-02 -9.442E-02 -1.171E-01 -1.004E-01 -1.367E-01 -9.348E-02 -1.038E-01 -1.392E-01 -1.277
Stdev         1.143E-02 8.296E-03 8.348E-03    9.998E-03 1.234E-02 1.456E-02 9.169E-03 9.593E-03 1.154E-02 1.104
DD            8.433E-03 6.208E-03 6.230E-03    7.398E-03 9.064E-03 1.082E-02 6.785E-03 7.234E-03 8.584E-03 8.145
VaR0.95       1.565E-02 1.140E-02 1.143E-02    1.399E-02 1.809E-02 2.234E-02 1.298E-02 1.346E-02 1.640E-02 1.663
CVaR0.95      2.713E-02 2.014E-02 2.002E-02 2.421E-02 3.112E-02 3.680E-02 2.218E-02 2.365E-02 2.882E-02 2.796
SR           5.540E-02 2.454E-02* 2.806E-02* 2.101E-02* 3.775E-02 3.225E-02 2.937E-02* 2.175E-02* 3.119E-02* 3.310E
SVR0.95      4.044E-02    1.786E-02  2.050E-02 1.501E-02 2.575E-02 2.102E-02 2.075E-02 1.551E-02 2.196E-02 2.197
SCR0.95      2.333E-02    1.011E-02  1.170E-02 8.679E-03 1.497E-02 1.276E-02 1.214E-02 8.821E-03 1.249E-02 1.307
Sortino      7.506E-02    3.279E-02  3.760E-02 2.840E-02 5.139E-02 4.339E-02 3.970E-02 2.884E-02 4.195E-02 4.487
Rachev0.95   6.699E-04    3.454E-04  3.485E-04 5.016E-04 8.349E-04 1.175E-03 4.249E-04 4.556E-04 7.063E-04 6.529
Assets              168          35         35        61         13         14         39         34        462
PTR          5.682E-04    5.745E-04  5.787E-04 6.316E-04 5.897E-04 7.998E-04 6.084E-04 7.385E-04 5.708E-04 4.810E



  and Sharpe, and and the two tail-risk measure based models i.e. MVaR & MCVaR,
  the TDA-PO model generates only marginally high risk. The lowest (i.e., best) PTR
  is reported by the S&P 500 index and the second lowest is given by the TDA-PO
  model. In contrast, the highest (i.e., worst) PTR is observed for the Omega model.
  This indicates that TDA-PO does not aggressively sacrifice risk control for return
  maximization - a key advantage in real-world applications, where excessive risk
  exposure can lead to substantial drawdowns during adverse market conditions.
• Risk adjusted return performance in terms of Sharpe, Sortino, Sharpe-
  CVaR (SCR0.95 ), Sharpe-VaR (SVR0.95 ), and Rachev ratios: Financial ratio
  measures the overall performance of a portfolio by combining return and risk in one
  single formula. It gives risk-adjusted return (or return per unit) for the underlying
  risk measure. We notice that the model TDA-PO outperforms all other models
  in terms of all financial ratios (except that the STARR model generates the best
  Rachev ratio followed by the performance by TDA-PO), depicting that it generates
  a high level of return without making much comprise with the risk levels. Therefore,
  the proposed model ranks as the first choice among all rational investors.
  The main reason for having such good out-of-sample performance in all aspects is
  that the proposed model captures the time-varying market features in a much better
  way than the traditional PO models.
• Performance analysis against the naive 1/N strategy and the market
  index S&P 500: The naive 1/N strategy and the market index S&P 500 serve
  as important benchmarks in assessing whether the optimization-based investment
  strategies deliver superior performance. From 2, we observe that the proposed TDA-
  PO model does not only achieve almost double EMR value in comparison to both the




                                                   18
  benchmark strategies, 1/N and S&P 500, but also improves the values of all finan-
  cial ratios. This confirms that proposed TDA based strategy provides noteworthy
  advantages over passive allocation strategies.
  On the other hands, though the variance-based models i.e. GMV, MP, and Sharpe,
  generate relatively lesser values of risks than the 1/N and S&P 500, they fail
  to deliver competitive values for EMR and risk-adjusted returns, reinforcing the
  inefficiency of variance minimization without adaptive structural adjustments.

In short from Table 2, we conclude the best out-of-sample performance from the
model TDA-PO in comparison to several popular PO models. The proposed model
achieves first rank in terms of out-of-sample mean return and financial ratios such as
Sharpe, Sharpe-CVaR (SCR0.95 ), Sharpe-VaR (SVR0.95 ), Sortino, and Rachev ratios.
It shows that the TDA-based proposed model able to produce a good amount of return
without generating high risk resulting in the best risk-adjusted return performance.
These results underline the out-of-sample efficacy of TDA-based models in delivering
high returns while managing risk. Though, the model GMV generates least values of
risks, it also suffers with the least return, lesser than the simplest Naive 1/N and the
benchmark index. Therefore, our numerical findings recommend the GMV and MP
based portfolios only to risk-averse investors.
For pictorial illustration purposes, we report the growth of $1 investment adjusted
with the transaction cost (TC) at rate 0.3%6 (wealth graph) by all the models in
the Figure 2. Transaction costs, which mainly emerge during portfolio adjustments or
re-balancing, are crucial aspect in examining the performance of different portfolios
strategies and can influence decision-making ([91], [92]). To plot the wealth graph from
each model, we first concatenate their out-of-sample returns from each rolling window
to get a single return series and thereby, obtaining a single wealth graph. Plots of
these wealth graphs help us to illustrate the clear time-varying behavior from all the
models. Figure 2 depicts the dominance of the proposed model TDA-PO throughout
the considered period in terms of wealth. A sharp drop can be seen near the point of
April 2020, where the least and largest fallout is given by the PO models STARR and
Sharpe, respectively. The proposed model bypasses all portfolios by generating large
returns while saving an investor from the sharp fall.

  6
    The growth of $1 investment of the portfolio w on t-day is calculated as 1(1+Aw1 )(1+Aw2 ) . . . (1+Awt )
with Awt be the t-th adjusted return realization with TC of portfolio return Rw i.e. the cumulative return
for each model is calculated by subtracting the TC from the daily returns and then compounding these
adjusted returns over time. For each day t, the adjusted return is given by:
                                            ARwt = Rwt − T Cd
where the T Cd is the transaction cost at the rebalancing day d is computed as:
                                 (
                                   turnover × 0.0003 if d is the rebalancing day
                         T Cd =
                                   0                   otherwise

with turnover is defined as the sum of the absolute differences between the current (mth window) and
previous window (mth window):
                                          X
                               turnover =   |weightsm,i − weightsm−1,i |
                                             i




                                                     19
          Growth of $1


    2.5


    2.0


    1.5


    1.0


              2014                         2016                     2018                         2020                      2022


                      GMV       Index       MCVaR     MP     MVaR           Naive        Omega          Sharpe    STARR        TDA PO


                                                                     (a)


          Growth of $1
   3.0


   2.5


   2.0


   1.5


   1.0

             2014                         2016                  2018                             2020                     2022


              Index         Naive       TDA IPO_120   TDA IPO_150          TDA IPO_170       TDA IPO_200         TDA IPO_250      TDA PO


                                                                    (b)

Fig. 2 The wealth of the portfolio starting from $1 for (a) TDA-PO and the models under comparison
and for (b) the integer constraint TDA portfolios. The returns have been adjusted to account for a
transaction cost rate of 0.3%. The plot illustrates the performance of each model and the index vs
the TDA-based models over the given period.


Effect of cardinality in the model TDA-PO
Next, in order to see the effect of cardinality in the model TDA-PO, we propose to
check the numerical performance of the model TDA-IPO for five different values of
cardinality k = 120, 150, 170, 200, 250 in Table 3. Table 3 depicts that the TDA-based
model selects 168 assets when no cardinality is introduced (i.e. the model TDA-PO)
while it goes only up to 64 assets when k = 250. On comparing the out-of-sample
values for performance matrices, we find the best values of mean return and all the
financial ratios from the model TDA-PO in comparison to the portfolios generated



                                                                      20
by TDA-IPO for five different values of k. Nevertheless, irrespective of the values for
k in TDA-IPO, we observe the model generates higher values of mean and ratios in
comparison to all other traditional models as prescribed in Table 3, confirming that its
asset constraint does not significantly weaken its financial efficiency. Lastly, we view
the wealth graphs of TDA-IPO for all the five values of k = 120, 150, 170, 200, 250
along with the TDA-PO in Figure 2. As evident, the model TDA-PO produces higher
wealth throughout the period with the least return at TDA-IPO for k= 200.

  Table 3 Sensitivity analysis: Out-of-sample performance metrics for the model (TDA-IPO)
  for five different cardinality values, k= 120, 150, 170, 200 and 250. Acronyms of the metrics
  are expanded and defined in the Appendix A. The Assets are averages of total assets with
  non-zero weights across different windows.

                TDA PO       TDA IPO120 TDA IPO150 TDA IPO170 TDA IPO200 TDA IPO250
   EMR          6.330E-04      4.845E-04    5.078E-04     5.301E-04     4.787E-04     5.307E-04
   Min          -1.447E-01    -1.252E-01   -1.247E-01    -1.239E-01    -1.134E-01   -1.055E-01
   Stdev         1.143E-02     1.099E-02    1.102E-02     1.118E-02     1.103E-02    1.081E-02
   DD            8.433E-03     8.106E-03    8.078E-03     8.214E-03     8.134E-03    7.879E-03
   VaR0.95       1.565E-02     1.588E-02    1.614E-02     1.560E-02     1.554E-02    1.533E-02
   CVaR0.95      2.713E-02     2.668E-02    2.673E-02     2.724E-02     2.694E-02    2.625E-02
   SR           5.540E-02      4.410E-02    4.609E-02     4.741E-02     4.339E-02     4.910E-02
   SVR0.95      4.044E-02      3.050E-02    3.147E-02     3.397E-02     3.080E-02     3.462E-02
   SCR0.95      2.333E-02      1.816E-02    1.900E-02     1.946E-02     1.777E-02     2.022E-02
   Sortino      7.506E-02      5.977E-02    6.286E-02     6.453E-02     5.885E-02     6.735E-02
   Rachev0.95   6.699E-04      6.296E-04    6.338E-04     6.589E-04     6.428E-04     6.182E-04
   Assets              168            51           57            59            60            64
   PTR           5.682E-04     4.997E-04    5.084E-04     5.074E-04     5.018E-04     4.748E-04




5.3 Portfolio Stability
5.3.1 Portfolio Stability in terms of Turnover
Turnover is a key measure of portfolio stability and transaction costs, where lower
turnover values indicate reduced trading activity and greater cost efficiency. Figure 3
presents the turnover distribution across all considered PO models, highlighting the
efficiency of the proposed TDA-PO and TDA-IPO strategies. The length of each box-
plot depicts the variation of turnover ratios obtained over 108 windows in the span of
nearly 10 years from December 10, 2012, to August 11, 2022.
A key observation from Figure 3 is the stark contrast in turnover behavior across
traditional PO models. The Sharpe PO model exhibits the highest turnover among
all the models, as it aggressively reallocates assets in response to fluctuations in mean
returns or model parameters (mean and covariance terms) with the dominance of mean
returns. Since mean returns are notoriously unstable and subject to estimation error,
the Sharpe model reacts with frequent and often excessive rebalancing, leading to
high transaction costs. In contrast, the GMV and MP portfolios maintain significantly
lower turnover, as their allocations are primarily driven by risk minimization, which is
inherently more stable over time. The GMV portfolio, which optimizes for the lowest
portfolio volatility, exhibits the most stable allocation adjustments, while the MP
model, despite incorporating mean returns, still remains dominated by the risk term,
preventing drastic portfolio changes.


                                               21
                        Monthly Distribution of Turnover Ratio
                 1.00
                                                                                                                                      Model
                                                                                                                                         TDA PO
                                                                                                                                         GMV
                 0.75                                                                                                                    MP
                                                                                                                                         Sharpe
Turnover Ratio



                                                                                                                                         STARR
                                                                                                                                         Omega
                 0.50
                                                                                                                                         MCVaR
                                                                                                                                         MVaR
                                                                                                                                         TDA IPO_120
                                                                                                                                         TDA IPO_150
                 0.25
                                                                                                                                         TDA IPO_170
                                                                                                                                         TDA IPO_200
                                                                                                                                         TDA IPO_250
                 0.00
                                    P
                         PO


                               V




                                              pe


                                               R


                                                        a


                                                                R


                                                                           R


                                                                                     20


                                                                                                50


                                                                                                           70


                                                                                                                      00


                                                                                                                                 50
                                                    eg
                               M


                                   M




                                           AR




                                                             Va


                                                                        Va


                                                                                    _1


                                                                                               _1


                                                                                                          _1


                                                                                                                     _2


                                                                                                                                _2
                                           ar
                              G




                                                    m
                      A




                                                            C


                                                                    M
                                         ST
                                        Sh




                                                                                O


                                                                                           O


                                                                                                      O


                                                                                                                 O


                                                                                                                            O
                    TD




                                                   O


                                                            M




                                                                               IP


                                                                                          IP


                                                                                                     IP


                                                                                                                IP


                                                                                                                           IP
                                                                          A


                                                                                      A


                                                                                                 A


                                                                                                            A


                                                                                                                       A
                                                                        TD


                                                                                    TD


                                                                                               TD


                                                                                                          TD


                                                                                                                     TD
                                                                Model


Fig. 3 Monthly distribution of turnover ratio across thirteen portfolio optimization models. The
proposed TDA-PO model and its constrained variations (TDA-IPO with different asset limits k =
120, 150, 170, 200, 250) exhibit relatively lower turnover compared to benchmarked PO models such as
Sharpe, STARR, MVaR and Omega (except for the GMV, and MP models while having comparable
results with MCVaR model). The lower turnover suggests that TDA-based models generate stable
allocations with fewer rebalancing costs while maintaining strong performance.


The turnover distributions from GMV and MP, are entirely falling below to all other
turnover distributions which indicating of having very stable portfolios over the span
of 10 years, giving serious concern of not accomodating the new market information.
The TDA-PO model exhibits a lower median turnover ratio compared to the Sharpe,
STARR, & MVaR and comparable to Omega PO model, reflecting its ability to con-
struct robust and stable allocations that do not require frequent rebalancing. For the
TDA-IPO models, which introduce explicit constraints on the number of assets held,
the expected trend of decreasing turnover with increasing k (the asset constraint) is
not clearly visible in the figure. Instead, turnover distributions for different TDA-IPO
constraints remain relatively close to each other, suggesting that while restricting the
number of assets may fix diversification, it does not necessarily lead to significantly
lower turnover levels in the observed dataset.
Nonetheless, the TDA-IPO models maintain lower turnover compared to the high-
turnover strategies such as Sharpe, STARR, MVaR & Omega portfolios (and having
comparable results with MCVaR), while preserving strong risk-adjusted performance.
The ability to generate stable yet adaptive allocations with lower reliance on expected


                                                                          22
return estimation gives TDA-PO and TDA-IPO a distinct advantage over traditional
PO models. These results underline the financial viability of TDA-based models as
practical alternatives to standard portfolio optimization approaches, achieving an
optimal balance between return maximization, risk control, and cost efficiency.

5.3.2 Transaction Cost Sensitivity Analysis
We next investigate the sensitivity of portfolio performance to transaction costs, moti-
vated by the variation in turnover observed across different allocation strategies. As
shown in Figure 3, turnover levels differ significantly across models, with Sharpe and
STARR portfolios exhibiting the highest rebalancing intensity, TDA-PO demonstrat-
ing a more stable turnover profile while the GMV and MP being the ones with the
lowest turnover.
To quantify the implications of this variation, we conduct a stress-test analysis using
elevated transaction cost (TC) levels of 1%, 2%, 3%, 4%, and 5%. These values simulate
a range of trading frictions and allow us to assess the sensitivity of each strategy’s net
returns to rebalancing activity and the transaction costs. The resulting cumulative
wealth trajectories are reported in Figure 4, where returns have been adjusted for
proportional costs based on absolute portfolio weight changes at each step.
It is important to note that transaction costs are only incurred by strategies that
involve active rebalancing. The naive and S& P index portfolios, being static by con-
struction, are unaffected and are thus excluded from these plots for clarity. The results
reveal several key insights. First, while all actively rebalanced portfolios experience
reduced wealth as TC increase, the magnitude of performance degradation is strongly
aligned with portfolio turnover characteristics, as previously reported in Figure 3. For
instance, Sharpe portfolios, which exhibit the highest turnover, suffer the steepest
decline in cumulative return as transaction costs rise.
In contrast, the TDA-PO strategy, which maintains a moderate and stable turnover
profile, experiences a more gradual decline in performance. Even at high transac-
tion cost levels, TDA-PO consistently outperforms all other optimized portfolios and
maintains a clear edge over the static benchmark strategies.
Traditional models such as GMV and MP, which involve lower turnover, also exhibit
more gradual performance degradation, though they remain consistently outperformed
by TDA-PO across all transaction cost regimes. Notably, TDA-PO outperforms both
(GMV and MP) even under the highest tested transcation cost of 5%.
Importantly, the performance ranking across models is not uniformly preserved as
transaction costs rise. Rather, high-turnover strategies are disproportionately penal-
ized, causing models like Sharpe specially to fall below even the naive benchmark
at higher TC levels. Overall, the transaction cost sensitivity analysis confirms that
the advantages of the TDA-PO framework persist even under adverse implementation
scenarios.
Notably, it is further evident that the model TDA-PO, along with other TDA-IPO,
outperform all other PO models by generating the best cumulative return (adjusted


                                           23
      Growth of $1, TC = 0.1%                                                                                                                               Growth of $1, TC = 0.2%

                                                                                                                                                      3.0
  3
                                                                                                                                                      2.5

                                                                                                                                                      2.0
  2
                                                                                                                                                      1.5

  1                                                                                                                                                   1.0

         2014       2015        2016      2017      2018              2019          2020           2021            2022          2023                         2014       2015        2016       2017       2018          2019   2020      2021        2022      2023


           GMV              MCVaR         MP                   MVaR                 Omega                 Sharpe          STARR                                GMV              MCVaR            MP               MVaR          Omega            Sharpe      STARR

           TDA IPO_120      TDA IPO_150   TDA IPO_170          TDA IPO_200          TDA IPO_250           TDA PO                                               TDA IPO_120      TDA IPO_150      TDA IPO_170      TDA IPO_200   TDA IPO_250      TDA PO




                           (a) Transaction Cost = 0.1%                                                                                                                       (b) Transaction Cost = 0.2%


        Growth of $1, TC = 0.3%                                                                                                                             Growth of $1, TC = 0.4%
                                                                                                                                                      2.5
  2.5
                                                                                                                                                      2.0
  2.0
                                                                                                                                                      1.5
  1.5
                                                                                                                                                      1.0
  1.0

                                                                                                                                                      0.5
          2014       2015        2016     2017          2018          2019          2020           2021            2022          2023                         2014       2015        2016       2017       2018          2019   2020      2021        2022      2023


           GMV              MCVaR          MP                  MVaR                  Omega                Sharpe           STARR                               GMV              MCVaR            MP               MVaR          Omega            Sharpe      STARR

           TDA IPO_120      TDA IPO_150    TDA IPO_170         TDA IPO_200           TDA IPO_250          TDA PO                                               TDA IPO_120      TDA IPO_150      TDA IPO_170      TDA IPO_200   TDA IPO_250      TDA PO




                           (c) Transaction Cost = 0.3%                                                                                                                       (d) Transaction Cost = 0.4%


                                                                        Growth of $1, TC = 0.5%

                                                                  2.0


                                                                  1.5


                                                                  1.0


                                                                  0.5
                                                                             2014           2015          2016            2017          2018          2019       2020        2021        2022      2023


                                                                              GMV                   MCVaR                 MP                   MVaR              Omega              Sharpe      STARR

                                                                              TDA IPO_120           TDA IPO_150           TDA IPO_170          TDA IPO_200       TDA IPO_250        TDA PO




                                                                                               (e) Transaction Cost = 0.5%

Fig. 4 The wealth of the portfolio starting from $1 for the TDA-PO strategy and the benchmark
models. Returns have been adjusted for transaction costs at rates of 0.1% to 0.5%. Each plot shows
the comparative performance of the index, standard models, and TDA-based portfolios over the
investment horizon. The results demonstrate that while higher transaction costs reduce overall return
levels, the TDA-based portfolio maintains consistent relative performance and robustness across all
cost regimes.




                                                                                                                                         24
with turnover cost) pattern where the worst performance is generated by the Sharpe
model followed by the performance of MCVaR and MVaR models. This remains
valid for all the transaction cost values examined, confirming the consistent superior
performance of the proposed scheme.

5.3.3 Stability Analysis in terms of Out-of-Sample Versus
      In-Sample Findings

                                                                    Out−of−Sample                                                                      Out−of−Sample
                                                                    In−Sample                                                                          In−Sample
        0.000




                                                                                           0.000
 Mean




                                                                                    Mean
        −0.010




                                                                                           −0.010
                 0.00   0.01   0.02     0.03          0.04   0.05     0.06                          0.00   0.01   0.02     0.03          0.04   0.05     0.06
                                      Standard Deviation                                                                 Standard Deviation
                                         TDA_PO                                                                               GMV



                                                                    Out−of−Sample                                                                      Out−of−Sample
                                                                    In−Sample                                                                          In−Sample
        0.000




                                                                                           0.000
 Mean




                                                                                    Mean
        −0.010




                                                                                           −0.010
                 0.00   0.01   0.02     0.03          0.04   0.05     0.06                          0.00   0.01   0.02     0.03          0.04   0.05     0.06
                                      Standard Deviation                                                                 Standard Deviation
                                               MP                                                                            Sharpe



                                                                    Out−of−Sample                                                                      Out−of−Sample
                                                                    In−Sample                                                                          In−Sample
        0.000




                                                                                           0.000
 Mean




                                                                                    Mean
        −0.010




                                                                                           −0.010




                 0.00   0.01   0.02     0.03          0.04   0.05     0.06                          0.00   0.01   0.02     0.03          0.04   0.05     0.06
                                      Standard Deviation                                                                 Standard Deviation
                                          STARR                                                                              Omega



                                                                    Out−of−Sample                                                                      Out−of−Sample
                                                                    In−Sample                                                                          In−Sample
        0.000




                                                                                           0.000
 Mean




                                                                                    Mean
        −0.010




                                                                                           −0.010




                 0.00   0.01   0.02     0.03          0.04   0.05     0.06                          0.00   0.01   0.02     0.03          0.04   0.05     0.06
                                      Standard Deviation                                                                 Standard Deviation
                                          MCVaR                                                                               MVaR



                                                                    Out−of−Sample                                                                      Out−of−Sample
                                                                    In−Sample                                                                          In−Sample
        0.000




                                                                                           0.000
 Mean




                                                                                    Mean
        −0.010




                                                                                           −0.010




                 0.00   0.01   0.02     0.03          0.04   0.05     0.06                          0.00   0.01   0.02     0.03          0.04   0.05     0.06
                                      Standard Deviation                                                                 Standard Deviation
                                           Naive                                                                              Index




Fig. 5 Scatter plots of In-sample and Out-of-Sample values of mean and standard deviation for all
portfolios obtained from the TDA-PO model and the seven benchmark models.




                                                                        25
To check the stability of results from the models over different windows, we compare
their in-sample values of mean and standard deviation vis-a-vis their out-of-sample
values (see Figure 5). The in-sample and out-of-sample coordinates for (mean, standard
deviation) = (µ, σ) are respectively, shown by the circular and triangle shapes. We
notice from the Figure 5 that the in-sample cluster of (µ, σ) from the model TDA-
PO has comparatively closer connected points than any of the other models, with a
similar pattern in its out-of-sample cluster, showing the robustness of the model with
respect to the change of the data. Though the out-of-sample clusters of (µ, σ) for
variance-based PO models i.e. GMV, MP, and Sharpe, have closely connected points
but not in their respective in-sample clusters. Lastly, the PO models STARR, Omega,
MVaR and MVaR are found to be comparatively highly sensitive to the change of
data, specifically for high values of σ.
So in short, we conclude the best performance of the proposed TDA-based optimization
model than all the famous traditional PO models ranging from variance-based models
to the reward-risk-based Omega model. This perhaps shows that capturing topological
features of the assets presents a better feature selection than the traditional ways of
portfolio allocation.

5.3.4 Statistical Evaluation of Risk Metrics
Here, we aim to assess whether the proposed method TDA-PO and other models
incur statistically higher downside risk or volatility when compared to the 1/N equal-
weighted portfolio. For this purpose, we conduct formal hypothesis tests on three key
dimensions of risk: VaR0.95 , CVaR0.95 , and variance (σ 2 ) (See Appendix A for details).
The VaR0.95 and CVaR0.95 comparisons are implemented using large-sample z-tests
based on empirical quantiles and tail averages Variance comparisons are performed
using the standard F -test for equality of variances. Across all three tests, we evaluate
whether given model’s risk is statistically greater or worse than that of the 1/N naive
strategy. The values worse than the naive are highlighted in red in all the relevant
tables.
The results indicate that, at the 95% confidence level, none of the models—except
for Omega and STARR—exhibit statistically higher risk than the 1/N naive bench-
mark. Both Omega and STARR portfolios are found to be significantly riskier than
the naive allocation, not only at the 95% level but also at the 90% and 97% statistic
levels. These findings are consistent across the VaR0.95 , CVaR0.95 , and variance tests,
reinforcing the conclusion that these two strategies carry systematically higher down-
side exposure. In contrast, the TDA-PO portfolio does not exhibit statistically greater
risk than the naive benchmark under any of the risk measures considered. Its variants
with cardinality constraints also show the same behavior. This suggests that, although
the proposed strategy does not explicitly minimize classical risk metrics, it neverthe-
less maintains downside and volatility characteristics that are statistically comparable
to the naive benchmark.




                                           26
6 Robust analysis
In this section, to assess the robustness of the proposed TDA-PO model vis-a-vis
benchmarked PO models and benchmarked portfolio strategies, we extend our analysis
for varying window size in the rolling window scheme in the two directions: (1) Exten-
sion of out-of-sample (holding) period from 1 month to 3 months, 6 months, and 1
year (2) Extension of in-sample (training) period from 1 year to 2 years. This analysis
provides further insights into the robustness of the proposed TDA-PO and TDA-IPO
models, particularly in relation to risk-return dynamics, risk-adjusted efficiency, and
stability of portfolio allocation with respect to the change in window size.

6.1 Impact of out-of-sample period size
The results in Table 4 provide insights into the effects of increasing the holding period
for the cases of 3 months, 6 months, and 1 year on the performance metrics considered
in the study.

• Return performance in terms of EMR: The results from the Table 4
  demonstrate that TDA-PO consistently achieves the highest EMR across all the
  out-of-sample periods, reinforcing its ability to generate persistent return outperfor-
  mance relative to benchmarked PO models (GMV, MP, MCVaR, MVaR, Sharpe,
  Omega and STARR) and benchmarked portfolio strategies (1/N , and S&P 500
  market index). Interestingly, despite being constructed without directly optimizing
  mean return, TDA-PO consistently outperforms mean-return-based PO models, the
  result is consistent with the case of 1 month out-of-sample period (see Table 2).
  Similarly, TDA-IPO, which imposes an explicit constraint on the number of assets
  held (k = 50)7 , also delivers strong return performance. While the EMR for
  TDA-IPO is slightly lower than TDA-PO and Omega models due to diversifica-
  tion constraints, it remains competitive and significantly outperforms traditional
  mean-variance based models.
  However, as the out-of-sample period extends from 3 months to 1 year, we observe a
  gradual decline in EMR across all considered models. This phenomenon is expected
  in longer investment horizons, where market volatility, structural shifts, and macroe-
  conomic factors erode short-term return advantages. While TDA-PO maintains
  its return dominance, the performance gap between TDA-PO and variance-based
  models slightly narrows over longer periods.
• Risk Analysis in terms of stdev, DD, VaR0.95 , and CVaR0.95 : Similar to
  the results reported in the Table 2 for the case of out-of-sample of 1 month, risk
  levels at TDA-PO are only slightly higher than GMV, MP, MVaR, MCVaR and
  Sharpe while they remain significantly lower than those of STARR, Omega, and
  the naive 1/N portfolio. TDA-IPO exhibits a similar risk profile, but with slightly

  7
    In our previous analysis in the Section 5, where we considered asset constraints of k =
120, 150, 170, 200, 250, we observed that the average number of assets with non-zero weights across rolling
windows was approximately 50 for all cases of k. Additionally, the benchmark PO models, such as GMV,
MP, MVaR, MCVaR, STARR, and Omega, also exhibited an average asset count close to or below this
threshold. To ensure a fair and consistent comparison, we set k = 50, aligning our model with the empirical
characteristics of the competing strategies



                                                    27
Table 4 Robustness check: Out-of-sample performance matrices obtained over rolling window scheme from the nine
optimization models. The best values are highlighted in bold for the reader’s convenience and second best are italicized. The ∗
is used to mark the significant values in the statistical tests for the Sharpe ratio at 90% confidence level for the TDA-PO
model vs others. Values highlighted in red represent performance metrics that are statistically inferior to those of the naive
portfolio at the 95% confidence level, with respect to the risk measures: variance, VaR0.95 , and CVaR0.95 . The assets are
averages of total assets with non-zero weights across different windows.

 Metric        TDA PO      TDA IPO          GMV             MP       Sharpe     STARR         Omega      MCVaR         MVaR
                               In-sample period= 1 year, Out-of-sample period= 3 months
 EMR           5.90E-04     5.09E-04      2.05E-04     2.19E-04    2.51E-04     5.04E-04   5.14E-04     2.70E-04     2.97E-04
 Min           -1.45E-01   -1.05E-01    -8.94E-02    -9.44E-02    -1.65E-01    -1.15E-01   -1.33E-01   -9.35E-02    -1.04E-01
 Std Dev        1.15E-02    9.70E-03     8.42E-03     8.45E-03     1.09E-02     1.25E-02    1.46E-02    9.34E-03     9.74E-03
 DD             8.46E-03    7.15E-03     6.24E-03     6.27E-03     8.06E-03     9.27E-03    1.07E-02    6.91E-03     7.21E-03
 VaR0.95        1.61E-02    1.42E-02     1.14E-02     1.14E-02     1.47E-02     1.80E-02    2.25E-02    1.35E-02     1.41E-02
 CVaR0.95       2.76E-02    2.41E-02     2.04E-02     2.03E-02     2.57E-02     3.10E-02    3.64E-02    2.26E-02     2.39E-02
 SR            5.25E-02    5.13E-02      2.44E-02*    2.59E-02*   2.31E-02*     4.02E-02   3.53E-02*   2.89E-02*    3.05E-02*
 SVR0.95       3.65E-02    3.59E-02       1.80E-02     1.92E-02    1.71E-02     2.80E-02    2.29E-02    2.00E-02     2.10E-02
 SCR0.95       2.14E-02    2.11E-02       1.01E-02     1.08E-02    9.78E-03     1.63E-02    1.41E-02    1.20E-02     1.24E-02
 Sortino       6.97E-02    5.72E-02       3.28E-02     3.49E-02    3.12E-02     5.44E-02    4.80E-02    3.91E-02     4.12E-02
 Rachev0.95    1.65E-03    1.49E-03       3.61E-04     3.62E-04    5.76E-04     5.39E-04    1.16E-03    4.43E-04     4.89E-04
 PTR            3.75E-04    2.91E-04      2.46E-04     3.32E-04    1.55E-03     3.03E-04    4.14E-04    3.90E-04     4.00E-04
 Assets              173           50          34            34           55          14          15           36          35
 Turnover           1.72         1.46        0.89          0.91         1.86        1.82        1.75         1.26        1.43
                               In-sample period= 1 year, Out-of-sample period= 6 months
 EMR           5.65E-04     5.18E-04      1.85E-04     1.84E-04    1.01E-04     4.86E-04   5.39E-04     2.21E-04     2.89E-04
 Min           -1.11E-01   -1.05E-01    -8.94E-02    -9.44E-02    -1.37E-01    -9.99E-02   -1.33E-01   -9.35E-02    -1.04E-01
 Std Dev        1.13E-02    9.93E-03     8.52E-03     8.65E-03     1.13E-02     1.18E-02    1.39E-02    9.29E-03     9.80E-03
 DD             8.22E-03    7.39E-03     6.26E-03     6.41E-03     8.40E-03     8.66E-03    1.02E-02    6.89E-03     7.26E-03
 VaR0.95        1.70E-02    1.44E-02     1.18E-02     1.16E-02     1.54E-02     1.69E-02    2.04E-02    1.33E-02     1.42E-02
 CVaR0.95       2.79E-02    2.49E-02     2.05E-02     2.08E-02     2.77E-02     2.93E-02    3.45E-02    2.27E-02     2.40E-02
 SR            5.22E-02    4.99E-02      2.17E-02*    2.12E-02*   8.96E-03*     4.13E-02   3.87E-02*   2.38E-02*    2.95E-02*
 SVR0.95       3.59E-02    3.32E-02       1.57E-02     1.58E-02    6.55E-03     2.87E-02    2.64E-02    1.66E-02     2.04E-02
 SCR0.95       2.08E-02    2.02E-02       9.01E-03     8.83E-03    3.65E-03     1.66E-02    1.56E-02    9.75E-03     1.20E-02
 Sortino       5.76E-02    5.66E-02       2.95E-02     2.86E-02    1.20E-02     5.61E-02    5.27E-02    3.21E-02     3.98E-02
 Rachev0.95    1.97E-03    1.52E-03       3.72E-04     3.82E-04    6.53E-04     7.47E-04    1.05E-03    4.39E-04     4.84E-04
 PTR            3.21E-04    2.66E-04      2.63E-04     3.23E-04    1.16E-03     3.11E-04    4.20E-04    2.72E-04     2.94E-04
 Assets              191           50           32           32           57          15          15           45          35
 Turnover           1.51         1.54        1.23         1.26          1.87        1.82        1.73         1.59        1.56
                                In-sample period = 1 year, Out-of-sample period= 1 year
 EMR           4.96E-04     4.24E-04      1.39E-04     1.15E-04    1.63E-04    4.79E-04     4.72E-04    1.94E-04     2.15E-04
 Min           -1.39E-01   -1.45E-01    -1.15E-01    -1.07E-01    -1.39E-01    -1.27E-01   -1.33E-01   -1.23E-01    -1.30E-01
 Std Dev        1.19E-02    1.12E-02     9.47E-03     9.43E-03     1.12E-02     1.30E-02    1.48E-02    9.93E-03     1.06E-02
 DD             8.81E-03    8.34E-03     6.99E-03     7.00E-03     8.40E-03     9.52E-03    1.07E-02    7.45E-03     7.84E-03
 VaR0.95        1.80E-02    1.51E-02     1.27E-02     1.30E-02     1.59E-02     1.85E-02    2.19E-02    1.35E-02     1.51E-02
 CVaR0.95       2.92E-02    2.77E-02     2.26E-02     2.26E-02     2.80E-02     3.20E-02    3.59E-02    2.41E-02     2.59E-02
 SR            4.15E-02    3.79E-02      1.46E-02*    1.22E-02*   1.45E-02*     3.68E-02   3.18E-02*   1.95E-02*    2.03E-02*
 SVR0.95       2.80E-02    2.75E-02       1.09E-02     8.82E-03    1.03E-02     2.60E-02    2.15E-02    1.43E-02     1.43E-02
 SCR0.95       1.70E-02    1.53E-02       6.15E-03     5.07E-03    5.83E-03     1.50E-02    1.31E-02    8.03E-03     8.31E-03
 Sortino       5.88E-02    5.36E-02       1.98E-02     1.64E-02    1.94E-02     5.03E-02    4.40E-02    2.60E-02     2.74E-02
 Rachev0.95    1.35E-03    1.25E-03       4.47E-04     4.51E-04    6.59E-04     9.08E-04    1.17E-03    4.97E-04     5.74E-04
 PTR            3.68E-04    3.64E-04      3.77E-04     5.58E-04    1.61E-03     9.11E-04    9.82E-04    3.96E-04     4.56E-04
 Assets              204          50           32            32           60          14          15           38          36
 Turnover           1.63        1.43         1.66          1.65         1.93        1.95        1.97         1.87        1.87




                                                28
  reduced risk compared to TDA-PO. The risk analysis further reveals that as the
  holding period increases, overall portfolio risk also increases for most of the models,
  reflecting natural amplification of the market volatility over extended horizons. This
  is observed across all risk (i.e. stdev, DD, VaR0.95 , and CVaR0.95 ) metrics except
  PTR. Despite this upward trend in risk exposure, TDA-PO maintains a favorable
  risk profile.
  A particularly notable observation is that VaR0.95 and CVaR0.95 increase at a slower
  rate for TDA-PO and TDA-IPO compared to STARR and Omega as the holding
  period extends. This suggests that both TDA-based models exhibit better down-
  side risk containment over longer investment horizons, an essential characteristic
  for investors focused on capital preservation. We further conducted statistical tests
  and confirmed that the TDA-PO strategy does not exhibit significantly higher VaR,
  CVaR, or standard deviation compared to the naive benchmark at the 95% confi-
  dence level. In contrast, the Omega and STARR models were found to be statistically
  worse than the naive portfolio across most cases.
  In terms of topological risk i.e. PTR, the Sharpe model suffers with its highest
  values when second highest values given by the model Omega whereas TDA-IPO
  and GMV models (having similar values) delivered its lowest values. This is true
  for all the cases of out-of-sample period size. The values of PTR increased highly
  from the out-of-sample of 6 months to 1 year for the models MP, MCVaR, MVaR,
  STARR and Omega whereas it remains stable for the models, TDA-PO, TDA-IPO,
  GMV and Sharpe.
• Risk adjusted return performance: One of the most striking results from Table
  4 is that TDA-PO consistently ranks first in all risk-adjusted return metrics when
  the second rank achieved by the TDA-IPO. The superior Sharpe, Sortino, Rachev,
  Sharpe-CVaR (SCR0.95 ), and Sharpe-VaR (SVR0.95 ) ratios of TDA-PO reaffirm its
  efficiency in delivering higher consistent returns without substantially increasing risk
  exposure. Similarly, TDA-IPO exhibits strong risk-adjusted performance despite the
  imposed constraints on asset selection. While it does not always surpass TDA-PO
  in risk-adjusted metrics, it remains superior to variance-based models and naive
  diversification approaches. The constrained selection of assets in TDA-IPO leads
  to a more stable return-risk tradeoff, reducing excess volatility while still achieving
  strong Sharpe and Sortino ratios.
  Further, as the holding period increases, risk-adjusted ratios decline across all
  models, reflecting the diminishing return-to-risk efficiency over extended horizons.
• Turnover Effects: Turnover analysis reveals a clear inverse relationship between
  turnover and holding period. As expected, turnover rates decline as the holding
  period increases, reflecting lower trading frequency in longer investment win-
  dows. This aligns with the fundamental principle that shorter rebalancing periods
  require more frequent portfolio adjustments, whereas longer holding periods demand
  maintaining positions despite market fluctuations.
  From a cost-efficiency standpoint, TDA-PO and TDA-IPO exhibit lower turnover
  than Sharpe, STARR, Omega, MVaR, and MCVaR (except to MVaR & MCVaR
  over 3 months out-of-sample period) implying reduced transaction costs over
  time. However, turnover remains higher than GMV and MP, which are inherently



                                           29
  designed for low trading activity. This suggests that TDA-based models strike a bal-
  ance between flexibility and stability, ensuring responsiveness to market dynamics
  without excessive rebalancing costs.
• With the increased size of out-of-sample period to 3 months, 6 months and 1
  year, the performance of all the PO models including the proposed TDA-PO and
  TDA-IPO in comparison to the benchmarked strategies, 1/N and S&P 500, remain
  consistent with the case of out-of-sample period size of 1 month (see Table 2). That
  is, except the models, GMV, MP, MVaR, MCVaR, and Sharpe, all other PO models
  i.e. STARR, Omega, TDA- PO and TDA-IPO generate better outcomes in terms
  of EMR and all the financial ratios than the 1/N naive and S&P 500 market index
  portfolios. This confirms that systematic optimization provides tangible advantages
  over both of the benchmarked allocation strategies.

6.2 Impact of in-sample period size
In this section, we examine the impact of training window length on portfolio perfor-
mance by fixing its size to 2 years while varying the out-of-sample period to 1 month,
3 months, 6 months, and 1 year. The results, summarized in Table 5, demonstrate key
structural advantages of TDA-based models over conventional approaches.

• The results indicate that TDA-PO and TDA-IPO maintain strong (EMR) perfor-
  mance across all out-of-sample periods (TDA-PO produced slightly lower return
  than Omega model only for the case of out-of-sample of 1 month and 1 year), rein-
  forcing their ability to generate persistent return advantages over traditional PO
  models, specially the variance-based models i.e. GMV, MP, & Sharpe; the tail risk
  measure based PO models, MVaR & MCVaR, and the benchmark strategies (1/N
  and S&P 500 market index).
• An interesting observation is that, unlike in the case of in-sample period of 1
  year, TDA-IPO exhibits superior return stability compared to TDA-PO with the
  increased in-sample period size of 2 years, suggesting that the imposed asset con-
  straints help mitigate overfitting to short-term fluctuations. The constrained asset
  selection in TDA-IPO leads to more persistent return efficiency, confirming its
  superiority over TDA-PO model.
• The risk analysis (stdev, DD, VaR0.95 , and CVaR0.95 ) follows an expected pat-
  tern, with most of the models exhibiting increased risk exposure as the holding
  period extends. While variance-based and tail risk based models maintain the low-
  est absolute risk levels, they do so at the cost of significantly lower return potential
  as similar to all other cases. In contrast, TDA-PO and TDA-IPO achieve a more
  balanced risk-return tradeoff, controlling downside risk without overly restricting
  upside potential.
• In terms of topological risk, the 1/N strategy suffers with the highest values of
  PTR for all the cases when second highest values were generated by the model
  STARR (over out-of-sample period of 1 month and 6 months), Sharpe model (over
  out-of-sample period of 3 months), and Omega model (over out-of-sample period
  of 1 year). It can be easily seen that the PTR values remain very unstable for all
  the models over varied size of out-of-sample except for TDA-PO, Omega, MCVaR,


                                           30
Table 5 Robustness check: Out-of-sample performance matrices obtained over rolling window scheme from the nine
optimization models and two benchmark portfolio strategies. The best values are highlighted in bold for the reader’s
convenience and second best are italicized. The ∗ is used to mark the significant values in the statistical tests for the Sharpe
ratio at 90% confidence level for the TDA-PO model versus others. Values highlighted in red represent performance metrics
that are statistically inferior to those of the naive portfolio at the 95% confidence level, with respect to variance, VaR0.95 ,
and CVaR0.95 . The assets are averages of total assets with non-zero weights across different windows.

Metric      TDA PO TDA IPO            GMV        MP      Sharpe    STARR      Omega     MCVaR       MVaR       Naive      Index
                              In-sample period= 2 years, Out-of-Sample period= 1 month
EMR         5.02E-04 8.22E-04 2.23E-04 2.30E-04 1.65E-04 4.45E-04 5.33E-04         1.92E-04 1.29E-04 3.33E-04 3.51E-04
Min        -1.10E-01 -1.37E-01 -9.58E-02 -9.49E-02 -1.45E-01 -1.17E-01 -1.16E-01 -7.60E-02 -1.20E-01 -1.39E-01 -1.28E-01
Std Dev     1.20E-02 1.39E-02 8.76E-03 8.81E-03 1.10E-02 1.29E-02 1.57E-02 8.79E-0 3 1.00E-02 1.20E-02 1.15E-02
DD          9.07E-03 1.59E-02 6.47E-03 6.49E-03 8.36E-03 9.54E-03 1.15E-02 6.37E-03 7.49E-03 8.92E-03 8.46E-03
VaR0.95     1.80E-02 3.02E-02 1.16E-02 1.19E-02     1.50E-02 1.97E-02 2.60E-02 1.28E-02 1.35E-02 1.70E-02 1.74E-02
CVaR0.95    3.12E-02 3.55E-02 2.08E-02 2.10E-02     2.76E-02 3.21E-02 3.95E-02 2.13E-02 2.46E-02 3.01E-02 2.92E-02
SR         4.18E-02 5.90E-02 2.54E-02* 2.61E-02* 1.49E-02* 3.44E-02 3.39E-02 2.19E-02* 1.29E-02* 2.78E-02* 3.06E-02*
SVR0.95    2.79E-02 2.72E-02 1.92E-02 1.93E-02 1.10E-02 2.25E-02 2.05E-02 1.51E-02 9.54E-03 1.96E-02 2.01E-02
SCR0.95    1.61E-02 2.31E-02 1.07E-02 1.10E-02 5.96E-03 1.39E-02 1.35E-02 9.03E-03 5.26E-03 1.11E-02 1.20E-02
Sortino    4.73E-02 5.18E-02 3.44E-02 3.54E-02 1.97E-02 4.67E-02 4.65E-02 3.02E-02 1.73E-02 3.74E-02 4.15E-02
Rachev0.95 2.79E-03 3.41E-03 3.84E-04 3.90E-04 6.16E-04 8.84E-04 1.34E-03 4.08E-04 5.05E-04 7.68E-04 7.10E-04
PTR         4.19E-04 4.61E-04 3.83E-04 3.91E-04 1.06E-03 8.65E-04 7.01E-04 4.05E-04 5.64E-04 9.58E-04 6.17E-04
Assets            344        20          34       35          60        14         13         45        42        462         1
Turnover         0.58      0.75        0.28     0.30        1.87      0.96       0.68       0.57      1.01       0.00      0.00
                              In-sample period= 2 years, Out-of-Sample period= 3 months
EMR        6.82E-04 8.11E-04 2.25E-04 2.23E-04 3.69E-04 3.44E-04 5.95E-04 1.88E-04 1.33E-04 3.33E-04 3.51E-04
Min        -1.10E-01 -1.48E-01 -9.58E-02 -9.49E-02 -1.22E-01 -1.17E-01 -1.16E-01 -7.66E-02 -1.17E-01 -1.39E-01 -1.28E-01
Std Dev     1.25E-02 1.51E-02 8.92E-03 8.94E-03 1.11E-02 1.27E-02 1.61E-02 8.93E-03 9.92E-03 1.20E-02 1.15E-02
DD          9.05E-03 1.17E-02 6.59E-03 6.60E-03 8.13E-03 9.31E-03 1.16E-02 6.53E-03 7.39E-03 8.92E-03 8.46E-03
VaR0.95     1.83E-02 2.63E-02 1.18E-02 1.19E-02     1.52E-02 2.00E-02 2.67E-02 1.31E-02 1.43E-02 1.70E-02 1.74E-02
CVaR0.95    3.14E-02 4.03E-02 2.15E-02 2.15E-02     2.72E-02 3.08E-02 3.99E-02 2.17E-02 2.43E-02 3.01E-02 2.92E-02
SR        5.45E-02 5.37E-02 2.52E-02* 2.49E-02* 3.33E-02* 2.70E-02* 3.70E-02* 2.11E-02* 1.34E-02* 2.78E-02* 3.06E-02*
SVR0.95   3.73E-02 3.09E-02 1.91E-02 1.87E-02 2.43E-02 1.72E-02 2.23E-02 1.43E-02 9.29E-03 1.96E-02 2.01E-02
SCR0.95   2.17E-02 2.01E-02 1.05E-02 1.03E-02 1.36E-02 1.12E-02 1.49E-02 8.68E-03 5.47E-03 1.11E-02 1.20E-02
Sortino   5.22E-02 4.76E-02 3.41E-02 3.37E-02 4.54E-02 3.70E-02 5.11E-02 2.88E-02 1.80E-02 3.74E-02 4.15E-02
Rachev0.95 1.88E-03 3.85E-03 4.04E-04 4.09E-04 6.40E-04 8.48E-04 1.40E-03          4.19E-04 4.97E-04 7.68E-04 7.10E-04
PTR         4.17E-04 7.70E-04 4.83E-04 4.01E-04 8.97E-04 8.71E-04 6.98E-04 4.26E-04 5.65E-04 9.58E-04 6.17E-04
Assets            342        20          34       35          60        14         14        458        42        462         1
Turnover         1.24      1.16        0.53     0.56        1.90      1.33       1.08       0.86      1.25       0.00      0.00
                              In-sample period= 2 years, Out-of-Sample period= 6 months
EMR        6.90E-04 8.75E-04 2.00E-04 1.81E-04 7.47E-05 3.82E-04 6.56E-04 2.02E-04 1.88E-04 3.33E-04 3.51E-04
Min        -1.10E-01 -1.48E-01 -9.58E-02 -9.49E-02 -8.78E-02 -1.17E-01 -1.16E-01 -7.60E-02 -1.10E-01 -1.39E-01 -1.28E-01
Std Dev     1.30E-02 1.64E-02 8.98E-03 9.03E-03 1.08E-02 1.28E-02 1.57E-02 8.95E-03 9.94E-03 1.20E-02 1.15E-02
DD          9.23E-03 1.51E-02 6.64E-03 6.66E-03 8.03E-03 9.32E-03 1.12E-02 6.49E-03 7.39E-03 8.92E-03 8.46E-03
VaR0.95     1.91E-02 3.10E-02 1.19E-02 1.19E-02     1.61E-02 2.00E-02 2.57E-02 1.30E-02 1.42E-02 1.70E-02 1.74E-02
CVaR0.95    3.21E-02 3.18E-02 2.16E-02 2.16E-02     2.76E-02 3.12E-02 3.82E-02 2.16E-02 2.44E-02 3.01E-02 2.92E-02
SR        5.30E-02 5.33E-02 2.23E-02* 2.01E-02* 6.92E-03* 2.98E-02* 4.17E-02 2.26E-02* 1.89E-02* 2.78E-02* 3.06E-02*
SVR0.95   3.61E-02 2.82E-02 1.69E-02 1.52E-02 4.62E-03 1.91E-02 2.56E-02 1.55E-02 1.33E-02 1.96E-02 2.01E-02
SCR0.95   2.15E-02 2.75E-02 9.29E-03 8.37E-03 2.71E-03 1.22E-02 1.72E-02 9.36E-03 7.70E-03 1.11E-02 1.20E-02
Sortino   5.93E-02 5.94E-02 3.02E-02 2.72E-02 9.30E-03 4.09E-02 5.83E-02 3.11E-02 2.55E-02 3.74E-02 4.15E-02
Rachev0.95 1.99E-03 4.32E-03 4.07E-04 4.13E-04 6.16E-04 8.74E-04 1.35E-03          4.19E-04 5.09E-04 7.68E-04 7.10E-04
PTR         4.12E-04 4.88E-04 4.82E-04 4.01E-04 3.21E-04 8.70E-04 7.04E-04 4.02E-04 5.48E-04 9.58E-04 6.17E-04
Assets            339        16          35       35          60        14         14         47        42        462         1
Turnover         1.00      1.37        0.78     0.80        1.87      1.52       1.32       1.09      1.44       0.00      0.00
                                  In-sample period= 2 years, Out-of-Sample period= 1 year
EMR         6.12E-04 1.33E-03 1.74E-04 1.69E-04 2.04E-04 4.35E-04 6.46E-04        8.66E-05 1.75E-04 3.33E-04 3.51E-04
Min        -1.40E-01 -1.48E-01 -1.19E-01 -1.19E-01 -9.51E-02 -1.65E-01 -1.33E-01 -1.20E-01 -1.38E-01 -1.39E-01 -1.28E-01
Std Dev     1.40E-02 1.83E-02 9.86E-03 9.85E-03      1.11E-02 1.28E-02 1.54E-02 9.92E-03 1.04E-02 1.20E-02 1.15E-02
DD          9.99E-03 1.26E-02 7.33E-03 7.32E-03      8.08E-03 9.45E-03 1.11E-02 7.37E-03 7.83E-03 8.92E-03 8.46E-03
VaR0.95     2.11E-02 3.07E-02 1.28E-02 1.27E-02      1.55E-02 1.81E-02 2.53E-02 1.33E-02 1.46E-02 1.70E-02 1.74E-02
CVaR0.95    3.43E-02 3.84E-02 2.37E-02 2.36E-02      2.75E-02 3.05E-02 3.74E-02 2.41E-02 2.54E-02 3.01E-02 2.92E-02
SR         4.38E-02 7.27E-02 1.77E-02* 1.72E-02* 1.83E-02* 3.40E-02 4.19E-02 8.73E-03* 1.67E-02* 2.78E-02* 3.06E-02*
SVR0.95    2.90E-02 4.33E-02 1.36E-02 1.33E-02 1.32E-02 2.40E-02 2.56E-02 6.49E-03 1.19E-02 1.96E-02 2.01E-02
SCR0.95    1.78E-02 3.46E-02 7.36E-03 7.18E-03 31 7.41E-03 1.43E-02 1.73E-02 3.59E-03 6.86E-03 1.11E-02 1.20E-02
Sortino     5.41E-02 7.16E-02 2.37E-02 2.31E-02 2.52E-02 4.60E-02 5.82E-02        1.17E-02 2.23E-02 3.74E-02 4.15E-02
Rachev0.95 1.12E-03 4.75E-03 4.86E-04 4.85E-04 6.70E-04 8.32E-04 1.28E-03         5.03E-04 5.58E-04 7.68E-04 7.10E-04
PTR         4.19E-04 7.53E-04 6.02E-04 6.02E-04 4.03E-04 1.42E-03 9.10E-04 6.02E-04 6.88E-04 9.58E-04 6.17E-04
Assets           341         16          34       34          60        13         15         58        41        462         1
Turnover        1.21       1.43        1.23     1.22        1.95      1.76       1.69       1.47      1.61       0.00      0.00
  MVaR, 1/N and the S&P 500 index. However, among these models TDA-PO has
  the least values of PTR and it is true for all choices of the out-of-sample periods.
• Examining risk-adjusted return performance, TDA-PO and TDA-IPO sustain con-
  sistently higher Sharpe, Sortino, Rachev, Sharpe-CVaR (SCR0.95 ), and Sharpe-VaR
  (SVR0.95 ) ratios compared to traditional models irrespective of window size, reaf-
  firming their efficiency in translating risk into return over varying horizons. Despite
  an overall decline in risk-adjusted ratios as the out-of-sample period extends,
  TDA-based models retain their performance edge in terms of these financial ratios.
• In terms of turnover ratio, it has been decreased comparatively for all the models
  when the in-sample size increases from 1 year (see Table 4) to 2 years (see Table
  5), indicating the effect of information gained during the longer training period
  time on adjusting the portfolio. It can be easily seen that the TDA based port-
  folios always exhibit lesser turnover ratios compared to the Sharpe, MCVaR and
  STARR (and many times from Omega also), suggesting that they remain responsive
  to market changes without excessive trading costs. Meanwhile, TDA-IPO achieves
  lower turnover than TDA-PO, reinforcing its stability and cost-efficiency, making it
  a particularly attractive model for investors seeking lower trading frictions. Similar
  to the case of in-sample period of 1 year, here also the portfolios from the model
  GMV and MP attain lower values of turnover ratios. Further, the results show that
  turnover decreases as the out-of-sample period increases from 1 months to 1 year,
  reflecting a reduction in rebalancing frequency over longer investment horizons.
• Finally, in comparison to the 1/N and S&P 500 market index, all the PO models
  except the models, GMV, MP, MVaR, MCVaR and Sharpe, generate better out-
  comes in terms of EMR and all the financial ratios. This conclusion is consistence
  through out our empirical analysis irrespective to the change in out-of-sample or
  in-sample time period length.

Overall, the results confirm that TDA-PO and TDA-IPO provide robust and adapt-
able investment solutions across different investment horizons. TDA-PO remains the
preferred choice for investors prioritizing higher risk-adjusted returns and short-term
adaptability, while TDA-IPO emerges as a strong alternative for investors seeking
more stable, and cost-efficient portfolios over extended training horizons. The findings
underscore the strength of TDA-based optimization in overcoming limitations of tradi-
tional PO models, including much celebrated variance-based models, offering superior
performance and risk management across various market conditions.
Note: Why TDA-PO and TDA-IPO are financially strong choices?
The robustness analysis confirms that TDA-PO and TDA-IPO consistently outper-
form competing PO models and benchmarked 1/N and S&P 500 index, across varying
size of window size. Even as the holding period increases, TDA-PO maintains its supe-
rior EMR, risk-adjusted return profile, and downside risk control, positioning it as the
most efficient investment strategy. Despite minor trade-offs in turnover, TDA-based
models retain key advantages over reward-risk bases PO models, Sharpe, STARR, and
Omega, striking an optimal balance between high returns, controlled risk exposure,
and manageable trading costs.



                                           32
The financial strength of TDA-PO and TDA-IPO lies in their ability to generate
superior returns without direct reliance on expected return estimates, allowing them
to adapt dynamically to changing market conditions. This reduced estimation risk,
combined with robust risk control mechanisms and competitive risk-adjusted returns,
positions TDA-based models as a compelling choice for investors seeking stable, high-
performing, and adaptable portfolio solutions.
Our findings align closely with previous studies that have employed TDA in finan-
cial applications. [74] demonstrated the effectiveness of TDA in enhanced indexing,
showing that topological features extracted from persistence landscapes provide valu-
able insights into asset selection and portfolio construction. Similarly, [73] introduced
a TDA-based clustering framework for sparse portfolio selection, highlighting the
superior performance of TDA-driven methodologies over traditional correlation-based
approaches. Our results reinforce these conclusions, as we also observe that TDA-based
methods capture essential structural patterns in financial time series. Specifically,
our approach successfully identifies topological features reflecting market dynamics,
enhancing decision-making in financial applications.

7 Conclusion
With the growing applications of TDA in various domains of data analysis, its usage
in the area of portfolio optimization has recently been explored. In this paper, we
aim to utilize persistence homology, a fundamental tool of TDA, to construct an
estimation error-free risk measure named as “Topological Risk” to obtain robust,
reliable, and stable outcomes. The topological risk of a portfolio combines the dynamic
of topological properties for each asset, calling asset topological risk. The topological
risk for each asset is quantified as the squared error of the asset’s time series of Lp
norms of persistence landscapes from the norm of the mean persistence landscape. An
optimal portfolio is finally derived by minimizing the topological risk of a portfolio
over an admissible set of portfolios.
Numerical results over the sample data of S&P 500 (U.S) with the sample period of
nearly 10 years from December 10, 2012, to August 11, 2022, conclude overall best
out-of-sample performance from the model TDA-PO in comparison to seven well-
established PO models, namely global minimum variance, mean-variance, mean-CVaR,
mean-VaR, Sharpe, STARR, and Omega models, and the two benchmark portfolio
strategies, the equally weighted portfolio 1/N and the benchmark market index S&P
500. The TDA based portfolios achieve first rank in terms of EMR without generating
high risk, resulting in the best risk-adjusted returns (financial ratios) performance.
This finding remains consistent through out the empirical analysis considered for the
varying size of holding and investment time horizon. We also check the effect of cardi-
nality constraint in the proposed model (TDA-IPO) by considering the five different
values for cardinality. We found that irrespective of the values for k in TDA-IPO, it
generates higher values of mean return and ratios in comparison to all other tradi-
tional PO models. These results confirm the supremacy of the proposed TDA-based




                                           33
portfolios in delivering high returns while managing risk, when applied in investment
practice.
Having a young idea of using TDA in portfolio optimization, there is room for improve-
ment and refinement in the proposed TDA-based risk measure. For instance, while
utilizing the topological risk matrix represented by Q, we operate under the assump-
tion of zero cross-interaction among distinct assets, a scenario that may not align with
reality. Introducing cross-interaction into the model requires careful consideration, and
various methods can be employed for its calculation. One possible approach could be,
defining the covariance between the norms of the persistence landscapes associated
with two assets, but it is not trivial. Alternatively, exploring the computation of per-
sistence landscapes through point clouds derived from two-dimensional data for a pair
of assets presents itself as a promising avenue for further investigation, representing
the next challenge to address in our work.
Another important consideration for future work is the role of embedding parameters
in shaping topological summaries. In our study, we fixed the embedding dimension and
time delay to d = 3 and τ = 1, respectively, a choice guided by theoretical motivation
and consistency with prior TDA applications. While these values are not tuned, they
are sufficient to preserve short-term dynamics in financial time series. Exploring how
alternative embedding configurations affect the estimation of topological risk, partic-
ularly in models that account for interactions between assets, remains a promising
avenue for further investigation.

8 Declaration
• Ethics approval and consent to participate: NA
• Consent for publication: All data contain in the paper have the consent of all the
  authors to be published.
• Availability of data and material: The datasets used are available from the
  corresponding author on reasonable request.
• Competing interests: No competing interests.
• Funding: The corresponding author gratefully acknowledges the financial sup-
  port received under the Startup Research Grant (SRG) scheme, File Number:
  SRG/2022/001983, from the Anusandhan National Research Foundation (ANRF)
  (previously known as Science & Engineering Research Board (SERB)), Department
  of Science and Technology (DST), Government of India.
• Authors’ contributions: Anubha Goel contributes in conceptualization and design
  of the study, investigation, analysis and interpretation of results, writing—original
  draft, writing—review & editing. Amita Sharma endows in investigation, analy-
  sis, project administration, supervision, writing—original draft, writing—review &
  editing. Juho Kanniainen helps in investigation, resources, software, supervision,
  writing—review & editing. All author(s) read and approved the final manuscript
• Acknowledgements: The authors sincerely thank the Editor and the anonymous
  reviewers for their valuable comments and suggestions, which have considerably
  improved the presentation and quality of the paper.



                                           34
Appendix A                   Performance Mesaures
We use the following performance measures to analyze the out-of-sample performance
of the portfolios.

1. Excess Mean Return (EMR): Out-of-sample excess mean return measured by
      P    T
               R −r
   µ = t=1T t f , where Rt is the realization of portfolio return Rw at time point t,
   t = 1, . . . , T , where T is the total number of days in the out-of-sample period and
   rf is a risk free interest. Higher values of EMR are preferable.
2. Standard deviation (stdev): Out-of-sample stdev of portfolio returns computed
   as                                   s
                                           PT                  2
                                             t=1 (E(Rw ) − Rt )
                                   σ=                            .
                                                    T
   The lower values of stdev are preferable. We also test whether the out-of-sample
   Variance (σ 2 ) of portfolio p1 is statistically worse than portfolio p2 . We apply the
   one-sided F-test8 with the hypothesis H0 : σp21 − σp22 = 0 and Ha : σp21 − σp22 > 0.
3. Downside Deviation (DD): It accounts for all the negative returns over out-of-
   sample period and is quantified as:
                                        s
                                            PT                 2
                                              t=1 (min{Rt , 0})
                                                                      .
                                                        T

   The lower values of DD are preferable.
4. Value-at-risk (VaRα ) and Conditional Value-at-Risk (CVaRα ): VaRα is a
   popular quantile-based risk measure used to estimate the maximum potential loss
   in a portfolio over a specific time horizon, at a given confidence level α ∈ (0, 1)
   whereas CVaRα is a conditional expectation of portfolio losses more than VaRα .
   Arranging the out-of-sample losses from portfolio w in ascending order as
   Lw1 , Lw2 , . . . , LwT , VaR and CVaR at α are calculated as:

                                    VaRα (Lw ) = Lwk ,
                                                                  T
                                                         1     X
                                  CVaRα (Lw ) =                  Lwi
                                                     T (1 − α)
                                                                 i=k


   where k = ⌊T α⌋ + 1 and Lw = −Rw is portfolio loss. Here, ⌊·⌋ denotes the
   greatest integer function or the floor function. For a fixed value of α ∈ (0, 1),
   lower values of VaRα (Lw ) and CVaRα (Lw ) are preferable. Furthermore, we test
   whether the out-of-sample VaR and CVaR from portfolio p1 are statistically worse

   8
     Given two strategies s1 and s2 , with sample variances σ̂s2 and σ̂s2 computed over a common sample
                                                                  1      2
size n, we test the equality of variances using the F -statistic:

                                                        σ̂s2
                                                            2
                                               Fσ2 :=
                                                        σ̂s21
The corresponding p-value is evaluated against the F distribution with degrees of freedom (n − 1, n − 1).



                                                   35
   than those of portfolio p2 . We apply the one-sided test9 . with the hypothesis H0 :
   V aR(CV aR)p1 − V aR(CV aR)p2 = 0 and Ha : V aR(CV aR)p1 − V aR(CV aR)p2 >
   0.
5. Sharpe Ratio (SR): Sharpe ratio is defined as the ratio of excess mean return to
   its standard deviation, i.e.,
                                                      µ−rf
                                              SR=      σ ; µ > rf ,

   Furthermore, we test whether the out-of-sample Sharpe ratios of two portfolios
   p1 and p2 are statistically different. We apply the one-sided zSR test with the
   hypothesis H0 : SRp1 − SRp2 = 0 and Ha : SRp1 − SRp2 > 0.10
6. Sortino Ratio (Sortino): Sortino ratio takes risk below to the mean return (σ̄)
   instead of standard deviation in the Sharpe ratio and is given as,
                                                         µ−rf
                                           Sortino=       σ̄ ; µ > rf ,

   where                                  s
                                              PT                         2
                                                t=1 (min{Rt − E(Rw ), 0})
                                   σ̄ =
                                              T
   is the semi-standard deviation of Rw .
7. Sharpe-VaR Ratio (SVRα ): It is a Sharpe ratio when the standard deviation is
   being replaced by VaRα (Lw ) and is defined as:
                                            f µ−r
                              SVRα = V aRα (L w)
                                                 µ > rf , V aRα (Lw ) > 0.

  9
    Given a strategy s1 and a target portfolio s∗ , with y1 , . . . , yn as the return series of s1 sorted from
                   \ α , VaR
lowest to highest, CVaR    d α are their sample CVaR and VaR values over a sample period n and c
              \ p for the target portfolio. We evaluate the p-values by calculating the z-test statistic:
denoting the CVaR

                                    p                     
                                        n(1 − α) c − CVaR
                                                     \α
    zCVaRα := r                                    2               2 ,             where    VaR
                                                                                                d α := ynα
                       1
                             Pn
                    n(1−α)     i=nα+1     yi − CVaR
                                               \α           \ α − VaR
                                                       + α CVaR   dα

                                                                  n
                                                          1      X
                                          \ α :=
                                          CVaR                        yi
                                                      n(1 − α) i=nα+1

Given a strategy s1 and a target portfolio s∗ , with y1 , . . . , yn as the return series of s1 , and c denoting the
VaR
d p for the target portfolio, we evaluate the p-value using the large-sample z-test statistic:

                                                     #{yi : yi < c} − np
                                          zVaRp :=      p
                                                           np(1 − p)
where p is the target confidence level, and #{yi : yi < c} denotes the number of returns in the sample
below the target threshold c.
  10
     Given two portfolios p1 and p2 , with µp1 , µp2 , σp1 , σp2 , σp1 ,p2 as their sample means, standard
deviations, and the covariance of two strategies over a sample period n. The z-test statistic is
                                                σp2 µp1 − σp1 µp2
                                        zSR =          √          , with
                                                         Υ

                             1   2   2                               2           2
                       Υ=      2σp1 σp2 − 2σp1 σp2 σp1 ,p2 + 0.5µp1 σp + 0.5µp2 σp
                             n                                         2           1
                                                                     µp µp 2
                                                                  − 1 2 σp ,p .
                                                                                  
                                                                     σp1 σp2 1 2




                                                        36
 8. Sharpe-CVaR Ratio (SCRα ): It is a Sharpe ratio when the standard deviation
    is being replaced by CVaRα (Lw ) and is defined as:
                                             µ−r
                            SCRα = CV aRα f(Lw ) µ > rf , CV aRα (Lw ) > 0.
 9. Rachev ratio (Rachevα ): It is the ratio of expected tail returns to the expected
    tail losses and is given as:

                                              CVaRα (Rw )
                                        Rachevα =           .
                                             CVaRα (−Rw )
    Larger values are desirable of all the above-listed ratios.
10. Turnover Ratio (TR): It is the average of the absolute values of trades among
    the n assets over the investment period. It is defined as

                                               M −1 X
                                                    n
                                           1   X
                              Turnover =               |wj,t+1 − wj,t , |
                                         M − 1 t=1 j=1

    where M is the total number of windows. Smaller values of turnover ratio are
    beneficial as they imply lower transaction costs.

 Note: We report the values of VaRα , CVaRα , SVRα , SCRα , and Rachevα ratios for
 α = 0.95. For simplicity, we choose rf = 0 in the out-of-sample analysis.

 Appendix B                     Benchmarked portfolio optimization
                                models for the comparative analysis
 Basic
 Pn notation: Let the return of a portfolio w is given by a random variable Rw =
   i=1 ri wi where ri represents the random rate of return from ith asset ; i = 1, . . . , n.
 Further, portfolio mean return and variance respectively, are denoted by E(Rw ) =
                            Xn X n
 Pn                 ′
   i=1 µ i wi and w   Σw =         wi wk σik where µi = E(ri ); i = 1, . . . , n and σik =
                                   i=1 k=1
 cov(ri , rk ); i, k = 1, . . . , n.
 For STARR and Omega PO models, we assume a total of T number of scenarios/time
 points under the discrete time setting with each realization
                                                         Pn       rit of ri occurs with a uni-
 form probability pt = 1/T ; t = 1, . . . , T . Then yt = i=1 rit wi becomes tth realization
 of the portfolio return Rw , t = 1, . . . , T .

 • Mean-variance model: The famous mean-variance model by [1] is a quadratic
   program which quantifies the portfolio return and risk respectively, by mean and
   variance of the return distribution. For µ = (µ1 , . . . , µn ) and Σ = [σik ]ni,k=1 respec-
   tively, be the mean vector and covariance matrix, the mean-variance model is given
   as:

                                                     ′      ′
                                              min   w Σw − µ w


                                                    37
                                   subject to
                                   w∈W

  The mean-variance model can be solved efficiently using standard quadratic pro-
  gramming algorithms. As portfolio weights from mean-variance model tend to be
  highly sensitive to even very small changes in the mean returns, ignoring it com-
  pletely can be one of the remedy. We next consider global minimum variance PO
  model which inspired from this wisdom.
• Global minimum variance model : Global minimum variance model [13] gives
  us the portfolio with least variance, is free from mean return terms and there-
  fore, believe to generate more reliable out-of-sample results than the mean-variance
  model. The model is described in below:

                                                 ′
                                       min      w Σw
                                       subject to
                                       w∈W

  Just like the mean-variance model, this can also be solved efficiently using standard
  quadratic programming algorithms.
• Sharpe model: Sharpe ratio [26] is the classic reward-risk ratio, defined as the
  fraction of the mean return of a portfolio to its standard deviation. It is widely used
  due to its simplicity and intuitive appeal of considering the standard deviation as a
  risk function. An optimization model maximizing Sharpe ratio is given as:

                                                     ′
                                                 µw
                                     max     √
                                               w′ Σw
                                     subject to
                                     w∈W

  Since the numerator (mean return) of Sharpe ratio is linear and the denominator
  (standard deviation) is an increasing function of a quadratic form, the above pro-
  gram reduces to a quadratic programming problem which can be solved efficiently
  globally.
• STARR ratio: The STARR ratio [27] is a reward-risk ratio which replaces the
  standard deviation in the Sharpe ratio with a conditional value-at-risk at a given
  level of confidence α ∈ (0, 1), which is a coherent risk measure. An optimization
  model maximizing STARR ratio is given as:

                                                     ′
                                              µw
                                    max
                                           CV aRα (w)
                                   subject to


                                           38
                                         w ∈ W,

  where CV aRα (w) is the conditional value-at-risk of a portfolio w at a given level
  of confidence α ∈ (0, 1). The above reward-risk PO model is a linear fractional
  program under the discrete time setting and can be translated into an equivalent
  linear program which therefore, can be solved efficiently using any LP solver.
• Omega ratio: Omega ratio introduced by [90], is a fraction of upside deviation of
  a portfolio return relative to a constant threshold point to its downside deviation.
  Therefore, an optimal portfolio maximizing Omega ratio does not only exhibits
  minimal downside deviation but simultaneously maximal upside deviation from the
  given threshold point.
  For a given threshold L ∈ R, a PO model maximizing the Omega ratio is given in
  below:


                                                E(Rw − L)+
                                        max                 ,
                                                E(L − Rw )+
                                        subject to
                                        w ∈ W,

  where c+ = max{c, 0}. Under the discrete structure of portfolio return, the above
  model can be translated into an equivalent linear program under the condition that
  L < maxw∈W E(Rw ). The target value L in the Omega model is set as the average
  value of Index return.
• Mean-CVaR model: The mean-CVaR model [25] incorporates downside risk
  directly by penalizing the conditional value-at-risk (CVaR) of the portfolio loss dis-
  tribution at a given confidence level α ∈ (0, 1). The model under discrete scenarios
  seeks to maximize the expected return while penalizing CVaR as follows:
                                                    "                       T
                                                                                  #
                                                         1    X
                               max        µ⊤ w − ζ +              zt
                             w, ζ, zt                (1 − α)T t=1
                        subject to        zt ≥ −yt − ζ,          t = 1, . . . , T,
                                          zt ≥ 0,       t = 1, . . . , T,
                                          w ∈ W.

  Here, ζ ∈ R and zt ≥ 0 are auxiliary variables that linearize the CVaR term.
• Mean-VaR model: The mean-VaR model aims to optimize expected return while
  penalizing the value-at-risk (VaR) of the portfolio loss distribution at level α ∈
  (0, 1). VaR is defined as the α-quantile of the loss distribution. The corresponding
  optimization model is formulated as a mixed-integer linear program [24]:

                         max            µ⊤ w − η
                      w, η, ut , yt

                     subject to         ut ≥ −yt − η,         t = 1, . . . , T,


                                                   39
                                 0 ≤ ut ≤ M yt ,     t = 1, . . . , T,
                                 T
                                 X
                                        yt ≤ ⌈(1 − α)T ⌉,    yt ∈ {0, 1},
                                  t=1
                                 w ∈ W.

  Here, η ∈ R represents the VaR level, ut ≥ 0 are exceedance variables, M > 0 is a
  sufficiently large number and yt are binary variables indicating tail scenarios. We
  take λ = 1.
  For the computation purposes, we take value of the confidence level α = 0.95 in the
  models, Mean-CVaR, Mean-VaR, and STARR.

Mathematical Optimization Techniques for Portfolio Models

• We compute the TDA-PO, global minimum variance, and mean-variance portfolios
  using a Quadratic Programming approach, implemented via the quadprog package
  in R. Specifically, we use the solve.QP function, which employs the dual method of
  [93] to efficiently solve the convex quadratic optimization problem.
• To construct the Omega-optimal and mean-CVaR portfolios, we employ a Linear
  Programming approach using the ROI package in R. The optimization problem
  is solved via the GLPK solver, which by default utilizes the simplex method to
  efficiently determine the optimal portfolio weights while ensuring feasibility under
  the given constraints.
• For mean-VaR portfolios, we formulate the optimization as a Mixed-Integer Linear
  Program (MILP) and solve it using the CVXR interface with the Gurobi optimizer.
  The model incorporates binary variables and employs a big-M formulation to lin-
  earize the Value-at-Risk constraints. To control computational complexity, a time
  limit of 30 minutes is specified within the Gurobi solver parameters.
• For the Sharpe Ratio maximizing portfolio, we adopt a stochastic search-based opti-
  mization approach using the PortfolioAnalytics package in R. The optimization
  process follows a random search heuristic, where 5,000 randomly generated port-
  folios are evaluated based on their Sharpe Ratios. The portfolio with the highest
  Sharpe Ratio is selected, ensuring an optimal risk-return trade-off. This heuristic-
  based approach allows for an extensive exploration of the solution space without
  requiring explicit derivatives, making it particularly useful for complex portfolio
  allocation problems.
• To construct the STARR-optimal portfolio, we employ a convex optimization
  framework, also implemented via the PortfolioAnalytics package in R. The opti-
  mization problem is solved using the ROI solver, leveraging Linear Programming and
  Conic Optimization techniques to efficiently identify the asset weights that maximize
  the STARR ratio while maintaining feasibility under the imposed constraints.
• For TDA-IPO with integer constraint on the number of assets, we employ an Integer
  Programming approach. The problem is formulated as a Mixed-Integer Quadratic
  Program and solved using the Gurobi optimizer, which is well-suited for han-
  dling large-scale integer-constrained problems. Gurobi employs a Branch-and-Bound


                                            40
  framework with Quadratic Programming Relaxation, efficiently navigating the solu-
  tion space to find an optimal allocation while enforcing the desired cardinality
  constraints.

References
 [1] Markowitz, H.: Portfolio selection. Journal of Finance 7, 77–91 (1952) https:
     //doi.org/10.2307/2975974

 [2] Bonnans, J.F., Shapiro, A.: Perturbation analysis of optimization problems. New
     York: Springer-Verlag (2000)

 [3] Jagannathan, R., Ma, T.: Risk reduction in large portfolios: Why imposing wrong
     constraints helps. Journal of Finance 58, 1651–1684 (2003) https://doi.org/10.
     1111/1540-6261.00580

 [4] Ledoit, O., Wolf, M.: Improved estimation of the covariance matrix of stock
     returns with an application to portfolio selection. Journal of Empirical Finance
     10, 603–621 (2003) https://doi.org/10.1016/S0927-5398(03)00007-0

 [5] Ledoit, O., Wolf, M.: A well-conditioned estimator for large-dimensional covari-
     ance matrices. Journal of Multivariate Analysis 88(2), 365–411 (2004) https:
     //doi.org/10.1016/S0047-259X(03)00096-4

 [6] DeMiguel, V., Garlappi, L., Nogales, F.G., Uppal, R.: A generalized approach to
     portfolio optimization: Improving performance by constraining portfolio norms.
     Management Sciences 55(5), 798–812 (2009) https://doi.org/10.1287/mnsc.1080.
     0986

 [7] Kolm, P.N., Tütüncü, R., Fabozzi, F.J.: 60 years of portfolio optimization: Prac-
     tical challenges and current trends. European Journal of Operational Research
     234(2), 356–371 (2014)

 [8] DeMiguel, V., Garlappi, L., Uppal, R.: Optimal versus naive diversification: How
     inefficient is the 1/n portfolio strategy? The review of Financial studies 22(5),
     1915–1953 (2009)

 [9] Jobson, J.D., Korkie, R.M.: Putting markowitz theory to work. The Journal of
     Portfolio Management 7(4), 70–74 (1981)

[10] Jorion, P.: Bayesian and capm estimators of the means: Implications for portfolio
     selection. Journal of Banking and Finance 15, 717–727 (1991)

[11] Chopra, V.K., Ziemba, W.T.: The effect of errors in means, variances, and covari-
     ances on optimal portfolio choice. The Journal of Portfolio Management 19(2),
     6–11 (1993)




                                           41
[12] Husmann, S., Shivarova, A., Steinert, R.: Sparsity and stability for minimum-
     variance portfolios. Risk Management 24, 214–235 (2022) https://doi.org/10.
     1057/s41283-022-00091-0

[13] Clarke, R., Silva, H.D., Thorley, S.: Minimum variance portfolio composition.
     Journal of Portfolio Management 37, 31–45 (2010)

[14] Khodamoradi, T., Salahi, M., Najafi, A.R.: Cardinality-constrained portfolio opti-
     mization with short selling and risk-neutral interest rate. Decisions in Economics
     and Finance 44, 197–214 (2021) https://doi.org/10.1007/s10203-020-00293-9

[15] Lee, Y., Kim, M.J., Kim, J.H., Jang, J.R., Kim, W.C.: Sparse and robust portfolio
     selection via semi-definite relaxation. Journal of the Operational Research Society
     71(5), 687–699 (2020) https://doi.org/10.1080/01605682.2019.1581408

[16] Scherer, B.: Can robust portfolio optimisation help to build better portfolios?
     Journal of Asset Management 7, 374–387 (2007)

[17] Bubenik, P., et al.: Statistical topological data analysis using persistence land-
     scapes. J. Mach. Learn. Res. 16(1), 77–102 (2015)

[18] Bubenik, P.: The persistence landscape and some of its properties. arXiv preprint
     arXiv:1810.04963 (2018)

[19] Konno, H., Shirakawa, H., Yamazaki, H.: A mean-absolute deviation-skewness
     portfolio optimization model. Annals of Operations Research 45, 205–220 (1993)

[20] Bellini, F., Klar, B., Müller, A., Rosazza Gianin, E.: Generalized quantiles as risk
     measures. Insurance: Mathematics and Economics 54, 41–48 (2014)

[21] Ju, X., Pearson, N.D.: Using value-at-risk to control risk taking: how wrong can
     you be? Journal of risk 1, 5–36 (1998)

[22] Goldfarb, D., Iyengar, G.: Robust portfolio selection problems. Mathematics of
     Operations Research 28, 1–38 (2003)

[23] Moon, Y., Yao, T.: A robust mean absolute deviation model for portfolio
     optimization. Computers & Operations Research 38(9), 1251–1258 (2011)

[24] Lotfi, S., Zeniosn, S.A.: Equivalence of robust var and cvar optimization. Working
     papers, University of Pennsylvania, Wharton School, Weiss Center (2016). https:
     //EconPapers.repec.org/RePEc:ecl:upafin:16-03

[25] Rockafellar, R.T., Uryasev, S.: Optimization of conditional value-at risk. Journal
     of Risk 3, 21–41 (2000)

[26] Sharpe, W.F.: The sharpe ratio. Journal of Portfolio Management 21(1), 49–58
     (1994)


                                           42
[27] Martin, R.D., Rachev, S.T., Siboulet, F.: Phi-alpha optimal portfolios and
     extreme risk management. Wilmott Journal November, 70–83 (2003)

[28] Kapsos, M., Zymler, S., Christofides, N., Rustem, B.: Optimizing the omega ratio
     using linear programming. Journal of Computational Finance 17, 49–57 (2014)

[29] Yitzhaki, S.: Stochastic dominance, mean variance, and gini’s mean difference.
     The American Economic Review 72(1), 178–185 (1982)

[30] Ogryczak, W., Ruszczyński, A.: On consistency of stochastic dominance and
     mean- semideviations models. Mathematical Programming 89(2), 217–232 (2001)

[31] Linsmeier, T.J., Pearson, N.D.: Risk measurement: An introduction to value
     at risk. Technical report, Technical report 96-04, OFOR, University of Illinois,
     Urbana Champaign, IL (1996)

[32] Rockafellar, R.T., Uryasev, S.: Conditional value-at-risk for general loss distribu-
     tions. Journal of Banking and Finance 26(7), 1443–1471 (2002)

[33] Roman, D., Gautam, M.: Portfolio selection models: a review and new directions.
     Wilmott Journal 1, 69–85 (2009)

[34] Jobson, J., Korkie, B.: Putting markowitz theory to work. Journal of Portfolio
     Management 7, 70–74 (1981)

[35] Kolma, P.N., Tütüncüb, R., Fabozzic, F.J.: 60 years of portfolio optimiza-
     tion: Practical challenges and current trends. European Journal of Operational
     Research 234, 356–371 (2014)

[36] Michaud, R.O., Michaud, R.O.: Efficient asset management: A practical
     guide to stock portfolio optimization and asset allocation, pp. 2143–2151
     (2023). New York, NY, 2008; online edn, Oxford Academic, 31 Oct. 2023,
     https://doi.org/10.1093/oso/9780195331912.001.0001, accessed 14 Mar. 2025

[37] Black, F., Litterman, R.B.: Asset equilibrium: Combining investor views with
     market equilibrium. Journal of Fixed Income 1, 7–18 (1991)

[38] Best, M.J., Grauer, R.R.: On the sensitivity of mean-variance-efficient portfolios
     to changes in asset means: Some analytical and computational results. The Review
     of Financial Studies 4(2), 315–342 (2015)

[39] Martin, H.: Asset allocation and risk management. Lecture notes: IEOR E4602:
     Quantitative Risk Management (2009)

[40] Bodnar, T., Dette, H., Parolya, N.: Testing for independence of large dimensional
     vectors. The Annals of Statistics 47(5), 2977–3008 (2019)

[41] Carlsson, G.: Topology and data. Bulletin of the American Mathematical Society


                                           43
    46(2), 255–308 (2009)

[42] Carlsson, G.: Topological methods for data modelling. Nature Reviews Physics
     2(12), 697–708 (2020)

[43] Wasserman, L.: Topological data analysis. Annual Review of Statistics and Its
     Application 5, 501–532 (2018)

[44] Chazal, F., Michel, B.: An introduction to topological data analysis: fundamental
     and practical aspects for data scientists. arXiv preprint arXiv:1710.04019 (2017)

[45] Skaf, Y., Laubenbacher, R.: Topological data analysis in biomedicine: A review.
     Journal of Biomedical Informatics 130, 104082 (2022) https://doi.org/10.1016/j.
     jbi.2022.104082

[46] Wang, Y., Ombao, H., Chung, M.K.: Topological data analysis of single-trial
     electroencephalographic signals. The annals of applied statistics 12, 1506–1534
     (2018)

[47] Moraleda, R.R., Xiong, W., Valous, N.A., Halama, N.: Segmentation of biomedi-
     cal images based on a computational topology framework. Seminars in Immunol-
     ogy 48, 101432 (2020) https://doi.org/10.1016/j.smim.2020.101432 . The Tumor
     Microenvironment: prognostic and theranostic impact. Recent advances and
     trends

[48] Chung, M.K., Smith, A.D., Shiu, G.: Reviews: Topological distances and losses
     for brain networks. ArXiv abs/2102.08623 (2021)

[49] Ravishanker, N., Chen, R.: Topological data analysis (tda) for time series. ArXiv
     arXiv:1909.10604 (2019)

[50] Lum, P.Y., Singh, G., Lehman, A., Ishkanov, T., Vejdemo-Johansson, M., Ala-
     gappan, M., J., C., Carlsson, G.: Extracting insights from the shape of complex
     data using topology. Scientific reports 3, 1236 (2013)

[51] Belchi, F., Pirashvili, M., Conway, J., Bennett, M., Djukanovic, R., Brodzki, J.:
     Lung topology characteristics in patients with chronic obstructive pulmonary
     disease. Scientific reports 8, 5341 (2018)

[52] Ichinomiya, T., Obayashi, I., Hiraoka, Y.: Protein-folding analysis using features
     obtained by persistent homology. Scientific reports 118, 2926–2937 (2020)

[53] Lo, D., Park, B.: Modeling the spread of the zika virus using topological data
     analysis. Scientific reports 13, 1–12 (2018)

[54] Carlsson, G., Zomorodian, A., Collins, A., Guibas, L.: Persistence barcodes for
     shapes. International Journal of Shape Modeling 11, 149–188 (2005) https://doi.
     org/10.1145/1057432.1057449


                                          44
[55] Li, C., Ovsjanikov, M., Chazal, F.: Persistence-based structural recognition, 2003–
     2010 (2014)

[56] Silva, V.D., Ghrist, R.: Homological sensor networks. Notices Amer. Math. Soc,
     10–17 (2007)

[57] Adams, H., Carlsson, G.: Evasion paths in mobile sensor networks. The Interna-
     tional Journal of Robotics Research 34, 90–104 (2015)

[58] Perea, J.A., Harer, J.: Sliding windows and persistence: An application of topo-
     logical methods to signal analysis. Foundations of Computational Mathematics
     15, 799–838 (2015)

[59] Pun, C.S., Xia, K., Lee, S.X.: Persistent-Homology-based Machine Learning and
     Its Applications – A Survey

[60] Berwald, J., Gidea, M., Vejdemo-Johansson, M.: Automatic Recognition and
     Tagging of Topologically Different Regimes in Dynamical Systems

[61] Pereira, C.M.M., Mello, R.F.: Persistent homology for time series and spatial data
     clustering. Expert Systems with Applications 42(15-16), 6026–6038 (2015)

[62] Wu, C., Hargreaves, C.A.: Topological machine learning for multivariate time
     series. Journal of Experimental & Theoretical Artificial Intelligence 34(2), 311–
     326 (2022)

[63] Perea, J.A., Deckard, A., Haase, S.B., Harer, J.: Sw1pers: Sliding windows and
     1-persistence scoring; discovering periodicity in gene expression time series data.
     BMC bioinformatics 16(1), 1–12 (2015)

[64] Masamichi, S.: Can tda be a new risk measure? an application to finance of
     persistent homology (2016)

[65] Gidea, M., Katz, Y.: Topological data analysis of financial time series: Landscapes
     of crashes. Physica A: Statistical mechanics and its applications 491, 820–834
     (2018)

[66] Saengduean, P., Noisagool, S., Chamchod, F.: Topological data analysis for
     identifying critical transitions in cryptocurrency time series. In: 2020 IEEE Inter-
     national Conference on Industrial Engineering and Engineering Management
     (IEEM), pp. 933–938 (2020). IEEE

[67] Gidea, M.: Topological data analysis of critical transitions in financial networks.
     In: 3rd International Winter School and Conference on Network Science: NetSci-X
     2017 3, pp. 47–59 (2017). Springer

[68] Vandewalle, N., Brisbois, F., Tordoir, X., et al.: Non-random topology of stock
     markets. Quantitative Finance 1(3), 372–374 (2001)


                                           45
[69] Majumdar, S., Laha, A.K.: Clustering and classification of time series using
     topological data analysis with applications to finance. Expert Systems with
     Applications 162, 113868 (2020)

[70] Gidea, M., Goldsmith, D., Katz, Y., Roldan, P., Shmalo, Y.: Topological recogni-
     tion of critical transitions in time series of cryptocurrencies. Physica A: Statistical
     Mechanics and its Applications 548, 123843 (2020)

[71] Aromi, L.L., Katz, Y.A., Vives, J.: Topological features of multivariate distri-
     butions: Dependency on the covariance matrix. Communications in Nonlinear
     Science and Numerical Simulation 103, 105996 (2021)

[72] Akingbade, S.W., Gidea, M., Manzi, M., Nateghi, V.: Why topological data
     analysis detects financial bubbles? Communications in Nonlinear Science and
     Numerical Simulation 128, 107665 (2024) https://doi.org/10.1016/j.cnsns.2023.
     107665

[73] Goel, A., Pasricha, P., Kanniainen, J.: Risk reduced sparse index tracking
     portfolio: A topological data analysis approach. To appear in Omega (2023)

[74] Goel, A., Pasricha, P., Mehra, A.: Topological data analysis in investment
     decisions. Expert Systems with Applications 147, 113222 (2020)

[75] Rudkin, S., Qiu, W., Dlotko, P.: Uncertainty, volatility and the persistence norms
     of financial time series. Expert Systems with Applications 223, 119894 (2023)
     https://doi.org/10.1016/j.eswa.2023.119894

[76] Song, S., Li, H.: Can topological transitions in cryptocurrency systems serve as
     early warning signals for extreme fluctuations in traditional markets? Physica A:
     Statistical Mechanics and its Applications 657, 130194 (2025) https://doi.org/
     10.1016/j.physa.2024.130194

[77] Baitinger, E., Flegel, S.: The better turbulence index? forecasting adverse finan-
     cial markets regimes with persistent homology. Financial Markets and Portfolio
     Management 35(3), 277–308 (2021)

[78] Ruiz-Ortiz, M.A., Gómez-Larrañaga, J.C., Rodrı́guez-Viorato, J.: A persistent-
     homology-based turbulence index & some applications of tda on financial markets.
     arXiv preprint arXiv:2203.05603 (2022)

[79] Takens, F.: Detecting strange attractors in uid turbulence. Dynamical Systems
     and Turbulence 898, 366 (1981)

[80] Horak, J., Krlı́n, L., Raidl, A.: Deterministicky Chaos a Jeho Fyzikalni Aplikace.
     Academia, ??? (2003)

[81] Khasawneh, F.A., Munch, E.: Utilizing topological data analysis for studying



                                            46
     signals of time-delay systems. In: Time Delay Systems, pp. 93–106. Springer, ???
     (2017)

[82] Kim, K., Kim, J., Rinaldo, A.: Time series featurization via topological data
     analysis. arXiv preprint arXiv:1812.02987v2 (2019)

[83] Adams, H., Emerson, T., Kirby, M., Neville, R., Peterson, C., Shipman, P., Chep-
     ushtanova, S., Hanson, E., Motta, F., Ziegelmeier, L.: Persistence images: A stable
     vector representation of persistent homology. The Journal of Machine Learning
     Research 18(1), 218–252 (2017)

[84] Guo, H., Xia, S., An, Q., Zhang, X., Sun, W., Zhao, X.: Empirical study of finan-
     cial crises based on topological data analysis. Physica A: Statistical Mechanics
     and its Applications 558, 124956 (2020)

[85] Tran, H.V., McGregor, C., Kennedy, P.J.: Detecting stress from multivariate time
     series data using topological data analysis. In: Australasian Joint Conference on
     Artificial Intelligence, pp. 341–353 (2023). Springer

[86] Seversky, L.M., Davis, S., Berger, M.: On time-series topological data analy-
     sis: New data and opportunities. In: Proceedings of the IEEE Conference on
     Computer Vision and Pattern Recognition Workshops, pp. 59–67 (2016)

[87] Akingbade, S.W., Gidea, M., Manzi, M., Nateghi, V.: Why topological data
     analysis detects financial bubbles? Communications in Nonlinear Science and
     Numerical Simulation 128, 107665 (2024)

[88] Fastrich, B., Paterlini, S., Winker, P.: Cardinality versus q-norm constraints for
     index tracking. Quantitative Finance 14(11), 2019–2032 (2014)

[89] Goel, A., Filipović, D., Pasricha, P.: Sparse portfolio selection via topological data
     analysis based clustering. Quantitative Finance, 1–31 (2025)

[90] Mausser, H.E., Saunders, D., Seco, L.A.: Optimizing omega. (2006). https://api.
     semanticscholar.org/CorpusID:2235129

[91] Arnott, R.D., Wagner, W.H.: The measurement and control of trading costs.
     Financial Analysts Journal 46(6), 73–80 (1990)

[92] Yu, J.-R., Chiou, W.P., Hung, C.-H., Dong, W.-K., Chang, Y.-H.: Dynamic rebal-
     ancing portfolio models with analyses of investor sentiment. International Review
     of Economics & Finance 77, 1–13 (2022)

[93] Goldfarb, D., Idnani, A.: A numerically stable dual method for solving strictly
     convex quadratic programs. Mathematical programming 27(1), 1–33 (1983)




                                            47