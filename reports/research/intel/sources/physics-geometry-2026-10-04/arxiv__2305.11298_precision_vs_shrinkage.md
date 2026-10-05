source: https://arxiv.org/pdf/2305.11298
fetched_utc: 2026-10-04T18:37:33Z
bytes_raw: 593167

Precision versus Shrinkage: A Comparative
                                            Analysis of Covariance Estimation Methods for
arXiv:2305.11298v1 [q-fin.CP] 9 May 2023




                                                         Portfolio Allocation
                                                                Sumanjay Dutta1 and Shashi Jain1
                                            1
                                                Department of Management Studies, Indian Institute of Science


                                                                                  Abstract
                                                      In this paper, we perform a comprehensive study of different covariance
                                                  and precision matrix estimation methods in the context of minimum vari-
                                                  ance portfolio allocation. The set of models studied by us can be broadly
                                                  categorized as: Gaussian Graphical Model (GGM) based methods, Shrink-
                                                  age Methods, Thresholding and Random Matrix Theory (RMT) based
                                                  methods. Among these, GGM methods estimate the precision matrix di-
                                                  rectly while the other approaches estimate the covariance matrix. We
                                                  perform a synthetic experiment to study the network learning and sam-
                                                  ple complexity performance of GGM methods. Thereafter, we compare
                                                  all the covariance and precision matrix estimation methods in terms of
                                                  their predictive ability for daily, weekly and monthly horizons. We con-
                                                  sider portfolio risk as an indicator of estimation error and employ it as a
                                                  loss function for comparison of the methods under consideration. We find
                                                  that GGM methods outperform shrinkage and other approaches. Our
                                                  observations for the performance of GGM methods are consistent with
                                                  the synthetic experiment. We also propose a new criterion for the hyper-
                                                  parameter tuning of GGM methods. Our tuning approach outperforms
                                                  the existing methodology in the synthetic setup. We further perform
                                                  an empirical experiment where we study the properties of the estimated
                                                  precision matrix. The properties of the estimated precision matrices cal-
                                                  culated using our tuning approach are in agreement with the algorithm
                                                  performances observed in the synthetic experiment and the empirical ex-
                                                  periment for predictive ability performance comparison. Apart from this,
                                                  we perform another synthetic experiment which demonstrates the direct
                                                  relation between estimation error of the precision matrix and portfolio
                                                  risk.
                                              Keywords - Minimum Variance Portfolio, Gaussian Graphical Models, Shrink-
                                           age, Thresholding, Random Matrix Theory, precision matrix estimation, low
                                           sample regime, test for superior predictive ability




                                                                                      1
1     Introduction
The estimation of the covariance matrix of stock returns constitutes a crucial
aspect of the portfolio allocation process. Conventionally, this involves compil-
ing a historical data set of stock returns and computing the sample covariance
matrix. However, it has been observed that this technique poses challenges in
terms of accurate estimation. Specifically, when the number of stocks being eval-
uated exceeds the available historical return observations, the sample covariance
matrix is prone to substantial estimation errors, which can have a dispropor-
tionate impact on the entries with high correlations. Consequently, pairs with
extreme entries may not accurately reflect the underlying relationships among
the stocks, but rather reflect the high levels of errors associated with their
estimation. Invariably, the mean-variance optimization algorithm tends to pri-
oritize the coefficients with the highest levels of estimation error and allocate its
largest investments accordingly. The reason for this is that coefficients with the
highest estimation error often have more extreme values, and as a result, they
are given higher weights by the mean-variance optimization algorithm, leading
to larger investments being allocated to them, even though they may not be
reliable. The critiques related to estimation noise can be categorized into two
key components:
    1. the estimate of the sample covariance matrix, and
    2. the inverse of the sample covariance matrix, also called the Precision Ma-
       trix.

The first problem is tackled by different methods broadly centred around three
approaches: a) Shrinkage, b) Thresholding and c) Random Matrix Theory (RMT)
Methods. Shrinkage tends to pull the most extreme coefficients towards more
central values, thereby systematically reducing estimation error where it matters
most. It requires three elements: An estimator with no structure, an estima-
tor with a lot of structure, and a shrinkage constant. The estimator without
structure is generally quite obvious, given the context. For us it is the sam-
ple covariance matrix. Statistically, the challenge is to know the structured
estimator and the optimal shrinkage constant.
    The utilization of shrinkage methods for portfolio selection was initially ex-
plored by Frost and Savarino [1986] and Jorion [1986]. However, their specific
techniques for shrinkage were unable to handle cases where the number of assets
surpassed the quantity of historical return observations, a common occurrence
in practical applications. Much of the foundations for the Shrinkage approach
for covariance estimation has been laid out by Ledoit and Wolf (Ledoit and
Wolf [2004a], Ledoit and Wolf [2004b]), Schäfer and Strimmer [2005] and Chen
et al. [2010] have suggested other shrinkage techniques which can be used to get
cleaner covariance matrix estimates. Jagannathan and Ma [2003] proved that
mean-variance optimizers are already implicitly applying some form of shrink-
age to the sample covariance matrix when short sales are ruled out, and this
improves the stability of the weights.


                                         2
    Thresholding involves setting small values in the sample covariance matrix
to zero, effectively shrinking the matrix towards a simpler structure with fewer
parameters. The threshold value is usually chosen based on a statistical crite-
rion, such as the universal threshold or the adaptive threshold.The idea behind
thresholding is that small values in the sample covariance matrix may be due to
noise or sampling error, and are not reflective of the true underlying covariance
structure. By setting these values to zero, the estimate becomes more stable
and accurate, particularly in high-dimensional settings. Donoho et al. [1995],
Bickel and Levina [2008] and Cai and Liu [2011] have proposed thresholding
techniques that estimate the covariance matrix.
    Another approach, which comes from Random Matrix Theory (RMT) at-
tempts to clean the measurement noise in the covariance and correlation ma-
trices. RMT is used in the study of correlation matrices through identification
of the eigenvalue distribution of large correlation matrices. The eigenvalues of
a correlation matrix are related to the principal components of the data, which
capture the major sources of variation in the dataset. RMT provides a the-
oretical framework for understanding the behavior of the eigenvalues of large
random correlation matrices. By analysing the empirical eigenvalue distribution
of a correlation matrix, RMT methods can identify the presence of significant
correlations between variables. Bun et al. [2017] discuss several RMT meth-
ods and analytical techniques (see Bun and Knowles [2018], Ledoit and Péché
[2011]). They also empirically establish the efficacy of the Rotationally Invariant
Estimator (RIE) method (see Bun et al. [2016]). These RMT methods provide
cleaned correlation matrices, which can then used to derive both the covariance
and precision matrices.
    To circumvent the second critique, it is possible to estimate the precision
matrix directly, rather than inverting the covariance matrix. Thus, a need for
alternative techniques of precision matrix estimation arises which may reduce
the estimation error and provide better out-of-sample performance. Gaussian
Graphical Model (GGM) based techniques have been proposed to estimate the
precision matrix directly. GGM methods were shown to provide consistent
estimates of the precision matrix. Friedman et al. [2008], (Cai et al. [2011]
and Meinshausen and Bühlmann [2006]) propose GGM methods which provide
Sparse and consistent estimates of the Precision Matrix. Millington and Niran-
jan [2017] conducted an empirical study that applies Graphical Lasso for the
estimation of covariance for the portfolio allocation. Their empirical findings
suggest that portfolios that use Graphical Lasso for covariance estimation yield
higher returns and have lower risk compared to the empirical covariance ma-
trix. Torri et al. [2019] propose a data-driven portfolio framework based on
two regularization methods, the Graphical Lasso (Glasso) and tlasso, that pro-
vide sparse estimates of the precision matrix by penalizing its L1 -norm. Callot
et al. [2021] use the nodewise-regression method of Meinshausen and Bühlmann
[2006] to establish consistency of the estimated variance, weights and risk of
high-dimensional financial portfolio. Their empirical application demonstrates
that the precision matrix estimator based on the nodewise-regression outper-
forms the principal orthogonal complement thresholding estimator (POET) of


                                        3
Fan et al. [2013] and linear shrinkage estimator of Ledoit and Wolf [2004b].
    The estimation methods compared in this study have been broadly classified
in figure1:

                                   Estimation
                                  Methods for
                                  Low-Sample
                                    Regimes
                                                      Estimate the
            Estimate the
                                                     Inverse Covari-
          Covariance Matrix
                                                       ance Matrix
               Shrinkage                                GGM Methods

               Thresholding

               Random Ma-
               trix Theory

                Figure 1: Classification of Estimation Methods

    We study a wide class of methods in this paper in terms of their predictive
ability for the minimum variance portfolio allocation problem. This raises the
question of providing a statistical procedure that delivers the best performing
methods with respect to a given criterion. Sometimes it is not trivial to assess
which model clearly outperforms each other. This problem is relevant from
an empirical point of view especially when the set of competing alternatives is
large, as in our context. Recently, a lot of effort has been devoted to develop
new testing procedures being able to deliver the best fitting models, see e.g. the
Reality Check (RC) of White [2000], the Stepwise Multiple Testing procedure
of Romano and Wolf [2005] and the Superior Predictive Ability (SPA) test of
Hansen [2005]. Jain and Jain [2019] use the SPA test to assess whether the
machine learning based portfolio allocation models outperform the traditional
risk based portfolios. The portfolio variance is directly proportional to the
estimation error and can be used as a loss function to compare models. We
compare these losses to rank the performance of the competing methods using
the Model Confidence Set (MCS) Procedure proposed by Hansen et al. [2011],
which consists on a sequence of tests which permits to construct a set of superior
models, where the null hypothesis of Equal Predictive Ability (EPA) is not
rejected at a certain confidence level.
    We address the following problems in this paper:
   • We first study the performance of the GGM methods in terms of structure
     recovery and sample complexity in a synthetic setup. We control the
     behaviour of the data by imposing a Multivariate Gaussian structure. The
     question we therefore address is: Do GGM methods exhibit a relationship


                                        4
     between sample complexity for network learning and the predictive ability
     for portfolio allocation ?
   • Second, we study the properties of the estimated precision matrices re-
     covered using GGM methods. This give us insights about the sparsity,
     error sensitivity and network properties of the estimates. We find that
     stock returns exhibit an important network property, which makes them
     suitable for direct precision matrix estimation through GGM methods.
   • Third, we perform an empirical study which compares the four broad
     classes of estimation methods mentioned earlier in terms of the minimum
     variance portfolio allocation problem. Predictive ability is directly associ-
     ated with the measurement errors of the estimated covariance and preci-
     sion matrices. Therefore, we analyse if it possible to rank these methods in
     terms of predictive ability. This also provides us a view of how the estima-
     tion errors associated with these methods impact the portfolio allocation
     process. We employ the MCS procedure to rank the methods. For this,
     we use the daily and intra-day returns data of the constituent stocks of the
     Nifty500 index, which is a representative of the top 500 stocks (by market
     capitalization) listed at the National Stock Exchange (NSE), India.
   • Apart from this, we also compare the best performing precision and co-
     variance matrix estimation methods in another synthetic setup where we
     demonstrate the connection between precision matrix estimation error and
     predictive ability.
   • We also study the impact of the choice of criterion for parameter tuning
     on the performance of GGM methods for portfolio allocation. We propose
     Portfolio variance as the objective function to be minimized as opposed
     to the approach suggested by Kelner et al. [2020] for hyperparameter se-
     lection. This criterion is used in both the synthetic and empirical setups
     and has important implications for the observations recorded.
   • The literature on GGM methods uses the finite grid parameter choice
     approach to estimate the precision matrix. This makes the performance
     of the methods dependent on a rather arbitrary choice of grids. In or-
     der to address this problem, we propose a novel procedure of parameter
     choice based on the Nelder-Mead Optimization method, which allows us
     to extended our choice of parameters from a finite sized discrete grid to a
     global continuous grid thus allowing for a wider choice of parameters for
     estimation.

    Observations from our empirical experiments suggested that GGM methods
clearly outperform the covariance matrix estimation methods. We also rank
the covariance matrix estimation methods separately and find that Non-linear
shrinkage approach performs better than linear shrinkage methods. Overall,
shrinkage methods also outperform the thresholding approach. The RMT based



                                        5
method is comparable with some shrinkage methods. Apart from this, our tun-
ing approach provides better algorithm performance in terms of sample com-
plexity for network learning for GGM methods. This is also substantiated by
the empirical experiment, where our tuning approach yields the best performing
methods. Our second synthetic experiment also suggests that precision matrix
estimation error is directly linked with predictive ability. That is, the higher
the estimation error, the lower the predictive ability.
    The paper is organized into the following sections: Section 2 gives a brief
description of the methods under discussion. It also discusses the hyperparame-
ter tuning procedures used for these methods. Section 3 discusses the statistical
testing procedures employed for comparing these methods in terms of predictive
ability. Section 4 discusses the design and results for the synthetic experiment.
Section 5 presents the design for our empirical analyses. Section 6 presents and
discusses the results observed from our empirical analyses. Section 7 discusses
the conclusions from our experiments. The Appendices A and B discuss the
issue of covariance matrix estimation error using spectral decomposition and
the Nelder-Mead style approach for grid extension respectively. Appendix C
lists all models considered for analysis in this paper.


2    Precision and Covariance Matrix Estimation
     Methods
Since the seminal work of Markowitz [1952], the idea of the minimization of risk
through portfolio diversification has become central to portfolio theory. The
idea behind this portfolio allocation model is simple: One needs to estimate the
covariance matrix from the returns of the individual components of the portfo-
lio and thus derive an analytical solution via a simple quadratic optimization
problem. This is possibly among the key factors behind the widespread usage
of the Markowitz framework, which is stated below:

                              minimize w> Σw
                                 w                                           (1)
                              subject to 1> w = 1,
where Σ represents the n×n true covariance matrix, w is the n×1 vector of asset
weights and 1 denotes a n × 1 unit vector. Asset returns are used to compute
the covariance matrix. The analytical solution for the optimization problem is
as follows:
                                        Σ−1 1
                               wM V = > −1                                  (2)
                                       1 Σ 1
where wM V is the vector of weights of the global minimum variance portfolio.
In order to obtain the weights, an estimate Σ̂ has to be computed (since Σ is
unknown):
                                        Σ̂−1 1
                               ŵM V =                                      (3)
                                       1> Σ̂−1 1


                                       6
As discussed before, computation of the sample covariance and its inverse is
prone to estimation errors. Meucci [2005] shows that this approach leads to
portfolio weights with poor out-of-sample properties. In this paper, we use
shrinkage, thresholding and Random Matrix methods to supply Σ̂. GGM meth-
ods, on the other hand, are used to estimate Σ̂−1 . We compare these two strands
of estimation in terms of their error reduction efficiency while solving the global
minimum variance portfolio allocation problem.

2.1    Gaussian Graphical Models
The literature on precision matrix estimation for the low sample regime has
made use of GGM methods for avoiding an inversion of the covariance ma-
trix. This helps in circumventing the estimation losses associated with such an
inversion. A GGM in n dimensions is a probability distribution with density
                               1
                                        exp −(x − µ)T Σ−1 (x − µ)/2
                                                                   
             p(X = x) = p
                            (2π)n |Σ|

where µ is the mean and Σ is the covariance matrix. The important point is
that their conditional independence structure is encoded by Θ = Σ−1 . We can
associate a graph to Θ which connects two nodes i, j when Θij 6= 0. Now
each node i only interacts directly with its neighbors in the sense that Xi is
conditionally independent of every other node in the graphical model given its
neighbors (Xj )i∼j . This means that there is a directly connection between
learning the network structure and the estimation error of the precision matrix.
We study this link more closely in our synthetic and empirical experiments.
In the context of portfolio optimization, X denotes the returns matrix of the
correlated assets.
    GGM methods for precision matrix estimation can be categorized into two
approaches. The first approach for using GGM methods to estimate the pre-
cision matrix focuses on constraining the L1 norm, where the goal is to learn
the sparsity pattern of Θ assuming some sort of lower bound on the strength
of non-zero interactions. This is a natural objective because once the sparsity
pattern is known, estimating the entries of Θ is straightforward (e.g. one can
use ordinary least squares). Glasso, Clime and MB (discussed in 2.1.1, 2.1.3
and 2.1.2) belong to this category.
    While the literature concerning the first approach shows that sparse GGMs
can be estimated when the number of samples is logarithmic in the dimension,
there is an important caveat in their guarantees. They need to assume that Θ
is in some sense well-conditioned. In response to this, the second approach was
proposed by Kelner et al. [2020]. This was motivated by Misra et al. [2020] who
studied the question of how many samples are needed information-theoretically
to learn sparse GGMs in the ill-conditioned case. Kelner et al. [2020] show
that relying on minimizing the conditional variance per node for estimating the
precision matrix leads to better sample complexity (that is, these algorithms
learn the partial correlation structure of the network with lesser number of


                                          7
samples) and higher sparsity. Kelner et al. [2020] propose the Greedy Prune and
HybridMB, which use this approach. Greedy Prune and HybridMB study two
important classes of GGMs respectively, viz. Attractive and Walk-Summable
models. A GGM is called attractive if Θij ≤ 0 for all i 6= j.
On the other hand, walk-summable matrices are defined as follows: Θ is walk-
summable if making all off-diagonal entries of Θ negative preserves the fact
that Θ is positive definite. All attractive GGMs are walk-summable, as are
other important classes of GGMs like pairwise normalizable and non-frustrated
models (Malioutov et al. [2006]). The GGM methods are summarily classified
below in figure 2 :

                                    Gaussian
                                    Graphical
                                     Models
                                                     Minimize Con-
            Constrain the
                                                     ditional Vari-
              L1 norm
                                                     ance per node
               Glasso                                      Greedy Prune

               Clime                                       HybridMB

               MB

            Figure 2: Classification of Gaussian Graphical Models

We provide a brief description of the GGM methods employed in our analyses:

2.1.1   Graphical Lasso (Glasso)
Suppose we have N multivariate normal observations of dimension p, with mean
µ and covariance Σ. Following Friedman et al. [2008], let Θ = Σ−1 and let Σ̂
be the sample covariance matrix, the problem is to maximize the log-likelihood

                            log detΘ − tr(Σ̂Θ) − ρ||Θ||1

over non-negative definite matrices Θ Here tr denotes the trace and ||Θ||1 is the
L1 norm- the sum of the absolute values of the elements of Σ−1 . This expression
is the Gaussian log-likelihood of the data, partially maximized with respect to
the mean parameter µ. Since we are interested in settings where the number of
samples is much smaller than the dimension, Σ̂ is a somewhat crude approxi-
mation to the true covariance. However, it is a good estimate when restricted
to sparse directions.
Awoye [2016] used Glasso (Friedman et al. [2008]) to estimate a sparse co-
variance matrix for the Markowitz mean-variance portfolio problem to improve
covariance estimation in terms of lower realized portfolio risk.


                                         8
2.1.2   Meinhausen-Bühlman
Meinshausen and Bühlmann [2006] show that neighborhood selection with the
Lasso is a computationally attractive alternative to standard covariance selec-
tion for sparse high-dimensional graphs. Their method estimates an unknown
precision matrix using the idea of projections to approximately invert the sample
covariance matrix. For each j = 1, ..., p they define the vector γ = {γj,k , j 6= k}
as follows:
                        γj := min  p−1
                                       E||Xj − X−jγ ||22 /n
                                γ∈R

and denote ηj := Xj − X−jγ and the noise level by τj2 = EηjT ηj /n. For the
column vector defined as: Γj := (−γj,1 , . . . , −γj,j−1 , 1, −γj,j+1 , −γj,p )T , they
show that
                  Θ0 = (Θ01 , . . . , Θpp ) = (Γ1 /τ12 , . . . , Γp /τ1p )
where Θ0j is the j-th column of Θ0 . Hence the precision matrix Θ0 may be recov-
ered from the partial correlations γj,k and from the noise level τj2 . Callot et al.
[2021] use the nodewise-regression method of Meinshausen and Bühlmann [2006]
to establish consistency of the estimated variance, weights and risk of high-
dimensional financial portfolio. Their empirical application demonstrates that
the precision matrix estimator based on the nodewise-regression outperforms
the principal orthogonal complement thresholding estimator (POET) (Fan et al.
[2013]) and linear shrinkage (Ledoit and Wolf (2004)Ledoit and Wolf [2004b]).

2.1.3   Clime
Another popular approach is the Clime estimator Cai et al. [2011] which solves
the following linear program

                          min||Θ||1 s.t. |Σn Θ − I|∞ ≤ λn

The analysis of Clime assumes a bound M on the maximum L1 -norm of any
row of the inverse covariance (given that the Xi ’s are standardized to unit
variance). This is also a type of condition number assumption, although of a
different nature than RE Kelner et al. [2020] and Friedman et al. [2008]. Cai
et al. [2020] use Clime to develop a consistent estimator of the minimum variance
for high-dimensional global minimum-variance portfolio.

2.1.4   Greedy Prune
Kelner et al. [2020] introduce the the following algorithm and show that it
succeeds in learning the graph structure of attractive GGMs. This algorithm,
called Greedy Prune, does the following to learn the neighborhood of node i:
   1. Set S = ∅ (S is the set of nodes not containing all neighbors of i) and let
      ν > 0 be a thresholding parameter.
   2. (Greedy/ step) Repeat the following T times: set j to be the the minimizer
      of V ar(Xi |XS , Xj ) and add j to S.


                                          9
  3. (Pruning step) For each j ∈ S: if V ˆar(Xi |XS ) > (1 − ν)V ˆar(Xi |XS {j} ),
     remove j from S.
  4. Return S as the neighborhood of node i.
where V ˆar indicates the variance is estimated from sample, using Ordinary
Least Squares.

2.1.5   Hybrid MB
The HybridMB algorithm (see Kelner et al. [2020] aims at learning walk-summable
GGMs. This algorithm does the following to learn the neighborhood of node i:
  1. (Greedy step) Set j to be the minimizer of V ˆar (Xi |Xj ).
  2. (Lasso with implicit weak preconditioning) Solve for w, a in
                                                                 2 
                                    X               Xk
               min      Ê Xi −          wk q              − aXj  
                                                                     
            w,a:||w||≤λ
                                   k∈{i,j}
                                    /           V ˆar(Xk |Xj

  3. (Pruning step) We perform a pruning step similar to Greedy Prune to zero
     out some of the entries of w, and to test if j is an actual neighbor.
  4. Return j (if it passed the test) and the remaining support of w as the
     neighborhood of i.

2.2     Shrinkage Methods
Suppose we have a sample of n iid random vectors in p dimensions, with an
expected value of zero. The p×p covariance matrix can be estimated by the usual
sample covariance matrix (SCM). From eigenvalue decomposition, we know that
Σ = U ΛU 0 , with U being orthogonal. Λ is a diagonal matrix containing the
eigenvalues of the covariance matrix. In particular, we see that the covariance
matrix is invertible if and only if all eigenvalues are different from zero, or in
other words, if the rank of the matrix is p.
    However in the above covariance matrix, we have p ∗ (p − 1)/2 elements to
estimate. p ∗ (p − 1) is the number of ways to choose two elements out of p, and
then we divide by 2 because the matrix is symmetric. This becomes a problem
if n is not much larger than p! This is observed when p > n occurs. In this case,
it can be shown that the SCM has a rank of at most n < p. In particular, even
if the true covariance matrix is invertible (having all eigenvalues larger than
zero), the SCM will have p − n zero eigenvalues and thus never be invertible.
This might be extreme as an extreme case, but even for a case like p = n/2, the
estimation error of the SCM can be substantial.


Linear Shrinkage Methods


                                       10
An arguably simple idea that has led to a myriad of research and applications
is to just take a linear combination of SCM and the identity matrix:

                                  Σ̂ = (1 − a)Ŝ + aI

The shrinkage constant a can be chosen according to theoretical considera-
tions. The different approaches to Linear Shrinkage vary in their methodology
for choosing a. The Ledoit Wolf Linear Shrinkage estimator, Rao-Blackwell
Ledoit Wolf estimator, Bodnar’s Shrinkage estimator and Oracle Approaching
approaches (see 2.2.1, 2.2.2, 2.2.4 and 2.2.3) belong to this class.

Nonlinear Shrinkage Methods:
Nonlinear shrinkage derives an asymptotic estimator in a much larger class (that
need not be just a linear function of the SCM). In particular, it solves the prob-
lem
                               arg min l(Σ̂, Û ΛÛ 0 )
                                      Λ

where l is some loss function.We are looking for the choice of (shrunken) eigen-
values that brings the resulting matrix as close as possible to the true covariance
matrix if we are only allowed to use the eigenvectors of the SCM. As we have
seen before linear shrinkage is a special case of this because we also only change
the eigenvalues there. However, now the way we determine Lambda is not con-
strained to be linear, offering much more flexibility.We include the Analytical
Non-Linear Shrinkage Estimator (see 2.2.5) proposed by Ledoit and Wolf [2020]
in our study. We present a summarized classification of the Shrinkage Approach
in figure 3:

                                     Shrinkage
                                     Estimators

                                                        Nonlinear
               Linear Shrinkage
                                                        Shrinkage
                   Ledoit Wolf                          Ledoit Wolf
                   Linear                               Nonlinear
                   Rao-Blackwell
                   Ledoit Wolf

                   Bodnar Linear

                   Oracle Ap-
                   proaching

                Figure 3: Classification of Shrinkage Estimators




                                          11
2.2.1   Ledoit Wolf Linear Shrinkage Estimator
Ledoit and Wolf (2004) Ledoit and Wolf [2004b] proposed a linear shrinkage
strategy (LWL) to estimate covariance matrix with an application to portfolio
optimization. An optimal covariance is written as a convex combination as
follows,
                            Σ̂ = δ F̂ + (1 − δ)S
where δ ∈ (0, 1) is a control parameter/weight, Ŝ an empirical covariance ma-
trix, and F̂ a target matrix. This paper introduces an estimator that is both
well-conditioned and more accurate than the sample covariance matrix asymp-
totically. This estimator is distribution-free and has a simple explicit formula
that is easy to compute and interpret. It is the asymptotically optimal convex
linear combination of the sample covariance matrix with the identity matrix.

2.2.2   Rao-Blackwell Ledoit Wolf Estimator
Chen et al. [2010] (RBLW) address covariance estimation in the sense of mini-
mum mean-squared error (MMSE) for Gaussian samples. Specifically, we con-
sider shrinkage methods which are suitable for high dimensional problems with
a small number of samples (large p small n). They modify the Ledoit-Wolf (LW)
method by conditioning on a sufficient statistic. By the Rao-Blackwell theorem,
this yields the new estimator. This approach estimates covariance matrix by
minimizing mean squared error with the following formula,

                              Σ̂ = ρF̂ + (1 − ρ)Ŝ

where ρ ∈ (0, 1) a control parameter/weight, Ŝ an empirical covariance ma-
trix, and F̂ a target matrix. It is proposed to use a structured estimate
F̂ = T r(Ŝ/p).Ip×p where Ip×p is an identity matrix of dimension p.

2.2.3   Oracle Approaching Shrinkage Estimator
Chen et al. [2010] propose an iterative approach (OA) which approximates the
clairvoyant shrinkage estimator. Convergence of this iterative method is estab-
lished and a closed form expression for the limit is determined. The authors
estimate the covariance matrix by iteratively approximating the shrinkage with

                              Σ̂ = ρF̂ + (1 − ρ)Ŝ

where ρ ∈ (0, 1) is a control parameter/weight, Ŝ is an empirical covariance
matrix, and F̂ a target matrix. It is proposed to use a structured estimate
F̂ = T r(Ŝ/p).Ip×p where Ip×p is an identity matrix of dimension p.

2.2.4   Bodnar’s Linear Estimator
In this paper Bodnar et al. [2014] extend the work of Ledoit and Wolf [2004b]
by constructing a more general linear shrinkage estimator (BDL) for a large


                                      12
dimensional covariance matrix. The target matrix here is considered to be
an arbitrary symmetric positive definite matrix with uniformly bounded trace
norm. The shrinkage estimator is given by
                                ˆ
                              ΣOLSE = α̂Sn + β̂Σ0

where α̂ and β̂ are the estimated shrinkage intensities. The recent results from
the random matrix theory allow them to find the asymptotic deterministic equiv-
alents of the optimal shrinkage intensities and estimate them consistently. The
developed distribution-free estimators obey almost surely the smallest Frobenius
loss over all linear shrinkage estimators for the covariance matrix.

2.2.5   Ledoit Wolf Analytical Non-linear Estimator
Ledoit and Wolf [2020] provide an analytical formula for optimal nonlinear
shrinkage (LWNL) of large-dimensional covariance matrices. It is achieved by
identifying and mathematically exploiting a deep connection between nonlinear
shrinkage and non-parametric estimation of the Hilbert transform of the sample
spectral density.The nonlinear shrinkage estimator of the covariance matrix is
the one minimizes the minimum variance: loss function

                             T r(Σ̂−1     −1
                                   n Σn Σ̂n )/p            1
                    LM
                     n
                       V
                         =                        −
                               [T r(Σ̂−1 )/p]2        T r(Σ̂−1 )/p

where Tr(·) denotes the trace of a square matrix, Σn represents the estimated
covariance matrix and LM  n
                            V
                              represents the true variance of the linear combina-
tion of the original variables that has the minimum estimated variance, under
a generic linear constraint, after suitable normalization. They also show that
their method is faster than previous nonlinear shrinkage methods, which were
numerical.

2.3     Thresholding Estimators
Bickel and Levina [2008] proposed thresholding of the sample covariance matrix
Σ and obtained rates of convergence for the thresholding estimators. This ap-
proach is similar to the Shrinkage Approach (which relies on regularization of
the Covariance Matrix) except for the fact that it specifically deals with band-
able matrices, where the entries of the matrix decay as they move away from
the diagonal. Similar approaches have been used by Antoniadis and Fan [2001]
and Cai and Liu [2011]. We discuss some of these thresholding methods below.

2.3.1   Hard Thresholding Estimator
Bickel and Levina [2008] proposed a sparse covariance estimation technique
(HT) to apply thresholding on off-diagonal elements of the sample covariance
matrix. The entry of sample covariance matrix Si,j = 0 if |Si,j | ≤ τ where τ is a
thresholding value). If the thresholding value is rather a vector of regularization


                                        13
parameters, it applies cross-validation scheme to select an optimal value. They
also discuss an intuitive resampling scheme for threshold selection and prove a
general cross-validation result that justifies this approach.

2.3.2   Soft Thresholding Estimator
Antoniadis and Fan [2001] propose the Soft Thresholding method (ST) for co-
variance estimation takes off-diagonal elements z of sample covariance matrix
and applies
                           hτ (z) = sgn(z)(|z| − τ )+
where sgn(z) is a sign of the value z, and (x)+ = max(x, 0). If thr is rather a
vector of regularization parameters, it applies cross-validation scheme to select
an optimal value.

2.3.3   Adaptive Thresholding
Cai and Liu [2011] proposed an adaptive variant (AT) of Bickel and Levina
(2008). The idea of adaptive thresholding is to apply thresholding technique on
correlation matrix in that it becomes adaptive in terms of each variable. The
adaptive estimator is Σ̂∗ (σ̂ij
                             ∗
                                )p×p where
                                   ∗
                                 σ̂ij = sλij (σ̂ij )

where sλ (z) is a general thresholding function similar to those used in Cai and
Liu [2011].

2.4     Random Matrix Theory Methods
RMT methods aim at distinguishing signal from noise, i.e. eigenvectors and
eigenvalues of the correlation matrix containing real information (which one
would like to include for risk control), from those which are devoid of any useful
information and are unstable. From this point of view, it is interesting to
compare the properties of an empirical correlation matrix C to a null hypothesis
purely random matrix as one could obtain from a finite time series of strictly
independent assets. Deviations from the random matrix case might then suggest
the presence of true information. This approach is then used to clean and
estimate large correlation matrices. We discuss one such approach suggested by
Bun et al. [2016] below.

2.4.1   Rotationally Invariant Estimators
Bun et al. [2016] propose an estimator Γ(M ) of the true signal C which depends
on the dataset M , where M is the estimated correlation matrix. The true
matrix C is unknown and there are no particular insights on its components (the
eigenvectors). Therefore they construct their estimator Γ(M ) in a rotationally
invariant way from the noisy observation M that they have. In simple terms,
this means that there is no privileged direction in the N-dimensional space that


                                        14
would allow one to bias the eigenvectors of the estimator Γ(M ) in some special
directions. More formally, the estimator construction must obey

                                ΩΓ(M )Ω0 = Γ(ΩM Ω0 )

for any rotation matrix Ω. Any estimator satisfying the above equation is re-
ferred as a Rotational Invariant Estimator (RIE). The best estimator is the
solution of the following minimization problem

                        Γ(M ) = arg min ||C − Γ(M )||
                                       RIΓ(M )


considered over the set of all possible RI estimators Γ(M ). Based on this prob-
lem, they propose an Oracle estimator for large correlation matrices (Bun et al.
[2017]) which, in the large N limit, and for a large class of problems, can be ex-
pressed in terms of the (observable) limiting spectral density (LSD) of M only.
This cleaned correlation matrix can then be used to estimate the covariance
matrix and its inverse. Bun et al. [2017] also show its application in portfolio
allocation and Principal Components Analysis.


2.5     Hyperparameter Tuning for GGM Methods
All the GGM methods we discuss in this paper estimate the precision matrix
based on the choice of parameters. The choice of parameters determines the
sparsity pattern and other properties of the estimated precision matrix. We
employ the Grid search approach to tune the parameters involves defining a set
of values for each parameter and testing all possible combinations. All the GGM
methods except Greedy Prune are single parameter methods where the param-
eters can assume continuous values. Greedy Prune is a two-parameter method,
where one parameter can assume continuous values and the other parameter
can assume only discrete values.

2.5.1   Crossvalidation Method I (CV1)
From a grid of parameters, we choose (using 5-fold crossvalidation) that param-
eter which minimizes the portfolio variance. The chosen parameter estimates
the precision matrix, which is then sued to compute the portfolio variance.
                                           mholdout
                                   1        X
                    E(σ 2 ) =                         var(X.wmin )
                                mholdout
                                             k=1

where wmin denotes the minimum variance portfolio weights. In our study, both
the cross-validations are performed on the matrix of returns, which then yields
the parameter with the least cross-validation error.




                                           15
2.5.2   Crossvalidation Method II (CV2)
We selected parameters using a 5-fold crossvalidation with the following least-
squares style crossvalidation objective, after standardizing the coordinates to
each having empirical variance 1 and mean 0:
                              n mholdout
                        1     X  X             (k)
                                                         X Θ̂ij + Θ̂ji    (k)
          E(Θ̂) =                          (Xi       +                   Xi )2
                    nmholdout i=1
                                    k=1                  j6=i
                                                                2Θˆii

The true Θ minimizes this objective as mholdout → ∞, making it equal to
the sum of conditional variances; when the initial variances are set to 1, this
objective simply measures the average amount of variance reduction achieved
over the coordinates.
    We treat the cross-validation objective functions discussed in 2.5.1 and 2.5.2
as the functions to be optimized. Since we do not know the gradient behaviour
of these functions, We use a grid ranging from (0, ∞) as the range over which
a Nelder-Mead Optimization exercise is performed. This extension of the grid-
choice accounts for both local and global extrema, which makes it possible to
remove the bias in model performance due to a limited grid size.

2.6     Hyperparameter Tuning of Shrinkage and Threshold-
        ing Methods
The estimation problem for shrinkage estimators involves the choice of shrinkage
constant, which determines the weightage of the sample covariance matrix and
the target matrix in the shrinkage estimate.
   • The Ledoit Wolf linear estimator (LWL) arrives at the optimal shrinkage
     constant (or the shrinkage parameter) by considered a general asymptotics
     framework where the dimension size p is allowed to tend to infinity as the
     sample size tends to infinity. The optimal shrinkage constant then tends to
     a limiting constant. This estimated optimal shrinkage constant is chosen
     as the parameter for LWL.

   • The RBLW approach provides an analytical formula, by applying the Rao-
     Blackwell theorem to the LWL method. Using several nontrivial Haar
     integral computations, it obtains a simple closed form solution. On the
     other hand, the OAS method provides an iterative method to calculate the
     optimal shrinkage intensities.Beginning with an initial naive choice, each
     iteration is defined as the oracle solution when the unknown covariance is
     replaced by its estimate obtained in the previous iteration.
   • The generalized linear shrinkage estimator (BDL) uses results from RMT
     to derive asymptotic deterministic equivalents of the optimal shrinkage
     intensities.




                                          16
    • The analytical nonlinear estimator (LWNL)follows a similar asymptotic
      methodology like Ledoit and Wolf [2004b] to estimate the optimal shrink-
      age parameter athough it adapts the selection criteria of the parameter to
      the portfolio variance and sharpe ratio estimators.
The Hard Thresholding Estimator uses a five-fold cross validation approach to
select the threshold based on an objective function which aims to reduce the
estimation error of the covariance matrix. The Soft and Adaptive Thresholding
methods follow a similar approach of hyperparameter selection. We employ the
above methods of hyperparameter selection for the corresponding shrinkage and
thresholding estimators to estimate the covariance matrix.


3     Statistical Testing Procedures for Predictive
      Ability
The availability of several alternative model specifications being able to ad-
equately describe the unobserved data generating process (DGP) opens the
question of selecting the best fitting model according to a given optimality crite-
rion. In our study we want to address two questions: First, We try to evaluate
whether a particular method can be chosen as a benchmark method, by evaluat-
ing whether is significantly outperformed by other methods. Second, we try to
find if it also possible to provide a relative ranking of these competing methods.
We perform a series of rejections of the competing methods till we reach a small
set of methods which cannot be pruned any further. We use two approaches
suggested by Hansen [2005] and Hansen et al. [2011] correspondingly to address
these questions.

Test for Superior Predictive Ability (SPA):
Let k = 0, ..., l be the models being considered, with k = 0 being the chosen
benchmark model and k = 1, . . . , l are the models the benchmark is being com-
pared against. Each model leads to a sequence of daily losses,L,t , t = 1, . . . , n.
The relative performance variables are defined as

                    Xk,t = L0,t − Lk,t , k = 1, . . . , l t = 1, ..., n

Let Xt = (X1,t , . . . , Xl,t )0 be a vector of relative performances and if µ = E(Xt ),
the null hypothesis is
                                         H0 : µ ≤ 0
that is, the benchmark model is not inferior to any of the alternative models
when the objective is to minimize the expectation of the loss function consid-
ered. For a number of competing models and a model chosen ex-ante as the
benchmark model, it tells whether the chosen model has been rightly consid-
ered as a benchmark model. in this context, it is important to note that we
use the Portfolio Variance as the loss function for comparing the benchmark
model against other models. To estimate the distribution of the test statistic


                                            17
used for the SPA test, we use the stationary bootstrap procedure of Politis and
Romano [1994]. This also requires testing for the stationarity of the data. We
perform the Augemented Dickey Fuller (ADF) and the Kwiatkowski-Phillips-
Schmidt-Shin (KPSS) tests for detecting stationarity. We find that the data
(both daily and intra-day) is stationary. This makes our data suitable for us-
ing SPA and the Model Confidence Set Procedure. In our study, we use this
to arrive at an acceptable level of certainty about the performance rankings
of Glasso and Greedy Prune. On the other hand, while this test can give in-
sights about the choice of benchmark models, we are still interested in finding
a reliable performance ranking when there are a large number of models present.

Model Confidence Set Procedure:
Hansen’s Model Confidence Set (MCS) procedure consists of a sequence of statis-
tic tests which permits to construct a set of Superior Set Models (SSM), where
the null hypothesis of Equal Predictive Ability (EPA) is not rejected at a certain
confidence level. The EPA test statistic is calculated for an arbitrary loss func-
tion that satisfies general weak stationarity conditions. Formally, let Yt be the
observation at time t and Yˆi,t the output of model i at time t, the loss function
li,t ,t associated to the i–th model is defined as:

                                     li,t = l(Yt , Yˆi,t )                      (4)

    d measures the difference between the output Yˆi,t and the a posteriori reali-
                                                  2
sation Yt . In our study, the portfolio variance σi,t is used as loss function. Thus
  2
σi,t represents the model output Yi,t in this case. Jain and Jain [2019] show
that the portfolio variance can also be used as a loss function. In our case, we
only rely on the estimate Yˆi,t (portfolio variance, in our case) for the loss func-
tion. This is because the estimated portfolio variance is directly related to the
estimated error and variance itself being an estimated quantity, there cannot be
any a postetiori realization for it.
    We now briefly describe how the MCS procedure is performed. It begins
with an initial set of models M̂ 0 of dimension m accounting for all the model
specifications described for a given confidence level 1 − α, a smaller set, the
                                  ∗
superior set of models, SSM, M̂1−α     of dimension m∗ ≤ m. The best scenario is
when the final set comprises of a single model, i.e. m∗ = 1. Formally, let dij,t
denotes the loss differential between models i and j:

                  dij,t = li,t − lj,t , i, j = 1, . . . , m, t = 1, . . . , n   (5)

   and let                                  X
                     di,t = (m − 1)−1             dij,t , i = 1, . . . , m      (6)
                                           j∈M

be the simple loss of model i relative to any other model j at time t. The EPA
hypothesis for a given set of models M can be formulated in two alternative




                                             18
ways:

                          H0,M : ci,j = 0,        i, j = 1, 2, ..., m
                         HA,M : ci,j 6= 0,        i, j = 1, 2, ..., m                      (7)

or

                            H0,M : ci. = 0,       i = 1, 2, ..., m
                           HA,M : ci. 6= 0,       i = 1, 2, ..., m                         (8)

   where cij = E(dij ) and ci. = E(di. ) are assumed to be finite and not time de-
pendent. According to Hansen et al. (2011), in order to test the two hypothesis
above, the following two statistics are constructed:

                           d¯ij                   d¯i,.
               tij = q               andti. = q             for i, j ∈ M                   (9)
                         V ˆar(dij )           V ˆar(di,. )

    where d¯i,. = (m − 1)−1 j∈M d¯ij is the simple loss of the i-th model relative
                                 P
                                                                             Pm
to the averages losses across models in the set M , and d¯ij = (m−1)−1 t=1 dij,t
measures the relative sample loss between the i–th and j–th models, while
V ˆar(d¯i,. ) and V ˆar(d¯i,j ) are bootstrapped estimates of var(d¯i,. ) and var(d¯i,j )
respectively. To calculate the bootstrapped variances V ˆar(d¯i,. ), we perform a
block–bootstrap procedure of 5000 resamples, where the block length p is the
max number of significant parameters obtained by fitting an AR(p) process on
all the dij terms. The first t–statistic tij is used in the well known test for
comparing two forecasts (e.g. Diebold and Mariano [2002] and West [1996]),
while the second one is used in Hansen [2005] and Hansen et al. [2011]. As
discussed The two EPA null hypothesis presented in equations 7 and 8 map
naturally into the two test statistics:

                     TR,M = max |tij | and Tmax,M = max ti.                               (10)
                                   i,j∈M                        i∈M

where tij and ti. are defined in equation9. The test statistics defined in equation
10 can be used in order to test the hypothesis discussed above. Sequential testing
procedures eliminate the worst model at each step, until the hypothesis of equal
predictive ability (EPA) is accepted for all the models belonging to the SSM.
The test statistics used as an elimination criteria for the worst model are defined
below:
                                  d¯i,.                                   d¯ij
         emax,M = max                      and eR,M = max{ sup q                      }
                     i∈M V ˆ
                           ar(di,. )                        i    j∈M
                                                                        V ˆar(dij )

respectively.
    Summarizing, the MCS procedure to obtain the SSM, consists of the follow-
ing steps:


                                             19
    • Set M = M0
    • Test for EPA–hypothesis: if EPA is accepted terminate the algorithm and
            ∗
      set M1−α  = M ,otherwise use the elimination rules defined in equations to
      determine the worst model.
    • Remove the worst model, and go to step 2.
The choice of α determines the number of models chosen as superior. If the data
is informative enough, the test returns only a single model as a superior model.
In our analyses, we see that among a large class of models that we deal with,
some of the algorithms are categorized as superior and some as inferior and for
the superior set of models, the MCS method gives a ranking based on superior
predictive ability. Thus, models classified as inferior suggest that the estimation
error encountered while using them leads to relatively inferior predictive ability.
In other words, the test helps us to determine methods which show lesser error
in covariance or precision matrix estimation, which further translates into lower
portfolio variance.


4     Synthetic Experiment - Design and Results
We analyse the performance of the algorithms in terms of structure recovery
and sample complexity. That is, we try to estimate the number of samples re-
quired for correctly estimating the nodes of a GGM network. The idea of correct
estimation is given by the samples needed to approximately recover true edge
                                                |Θˆ |
structure after thresholding using the test √ ˆij ˆ > κ/2 , where κ is the κ
                                                Θii Θjj
for the true precision matrix (see Kelner et al. [2020] for a detailed discussion).
Apart from portfolio variance (which doubles up as loss function as discussed
in the following sections), this approach also indicates the estimation accuracy
of the GGMs under consideration. The lesser the number samples required, the
more accurate is the method.
We consider a simple attractive GGM (with paths and cliques) and show that
Greedy Prune and HybridMB always perform well compared to previous meth-
ods and sometimes outperform them considerably. We set d, the maximum
clique size (the maximum number of mutually interconnected nodes that a graph
can have), as 5, such that n/2 (where n represents the number of nodes or dimen-
sions) is a multiple of d. Let B be a standard Brownian motion in 1 dimension,
and let be the values of the B at equally spaced points in the interval [1/2, 3/2]
be given by:
                                   X1 , ..., Xn/2
that is,
                 X1 = B(1/2), X2 = B((1/2) + 1/(n − 1)), . . .
Equivalently, let the covariance matrix of this block be Cov(Xi , Xj ) = 1/2 +
min(i, j)/n, or take the Laplacian of the path and add the appropriate constant
to the top-left entry. Let the variables Xn/2+1 , . . . , Xn be independent of the


                                        20
Brownian motion, and let their precision matrix be block-diagonal with d × d
blocks of the form Θ1 where Θ1 is a rescaling of Θ0 so that the coordinates
have unit variance, and Θ0 = I − (ρ/d) 11~ T where ρ ∈ (0, 1). ρ represents the
edge strength of the graph, Trials and hyperparameter selection was performed
to minimize the number of incorrect edges (with error of at most 0.25 incorrect
edges per node). We compare Greedy Prune and HybridMB with Glasso, MB
and Clime. Figure 4 depicts the behaviour of the algorithms when both the




                               (a) d = 5, ρ = 0.95




                               (b) d = 5, ρ = 0.95

Figure 4: Synthetic Experiment: Number of samples needed to achieve error
of at most 0.25 incorrect edges per node after thresholding: For Figures 1 a)
and 1 b), CV1 and CV2 respectively were used for tuning the parameters of the
algorithms.

cross-validation schemes CV1 and CV2 are used for estimating the precision
matrix respectively. d = 5 represents the maximum clique size of the graph.
ρ = 0.95 denotes the edge strength of the graph.
    We find that the Greedy Prune requires higher number of samples to esti-
mate the nodes correctly compared to Glasso, but its sample requirements start
catching up with Glasso as the number of nodes increases. What this means is
that the sample complexity of Greedy Prune becomes better with the increase
in the dimension size. Clime on the other hand, requires a much higher num-
ber of samples compared to all other algorithms. This holds true for the both
the crossvalidation methods. The question that arises here is whether this also
reflects in the precision matrix estimation error for Clime. This is answered in


                                       21
section 6.2. HybridMB shows better sample complexity than Greedy Prune for
lower number of nodes, but as the number of nodes increases, HybridMB shows
a requirement of higher number of samples. This behaviour is observed till the
number of nodes remains MB successfully achieved similar sample complexity
to our proposed methods, despite the fact that this setup is again well outside
of the regime where its theoretical guarantees are good. We see the sample
complexity of Greedy Prune scales like O(log(n)). The results also suggest that
the first cross-validation method (CV1) leads to lesser samples being required
for node recovery compared to CV2.. Thus this experiment suggests the use
of the minimum variance cross-validation scheme for node recovery or precision
matrix estimation in the low sample regime. The difference in the predictive
performance of CV1 and CV2 is further studied in the following sections.
    We have already seen that Greedy Prune requires a similar number of sam-
ples compared to Glasso in order to attain a similar level of structure recovery
when the number of dimensions approaches 500. This might mean that Greedy
Prune performs almost as well as Glasso in terms of accurate estimation of the
precision matrix when the dimension size increases. To probe further, we per-
formed an empirical experiment. We use the daily and intra-day returns of the
constituent stocks of the Nifty500 index. We vary our sample sizes from 150 to
500 (with intervals of 50).The algorithms are applied using CV1. We computed
the average out-of-sample portfolio variance (computed over rolling windows).
In Figure 5 till 250 samples, Glasso outperforms Greedy. After the number of




 Figure 5: Out-of-Sample Variance Comparison for Glasso and Greedy Prune

samples approaches 250, Greedy starts outperforming Glasso. Thus, an increase
in sample size, helps Greedy Prune attain an advantage (in terms of predictive
ability) over Glasso. It is also important to note that a similar exercise per-
formed for a dimension size of less than 50, Greedy Prune breaks down. This
suggests that scaling up a high-dimensional problem improves the estimation
ability of Greedy Prune. Also, when the dimension size is fixed, the increase
in the number of samples also helps Greedy Prune to attain better estimation
accuracy.
    From the figure, it can be observed that Greedy Prune starts outperforming


                                      22
Glasso when the number of samples increase. The above experiment has been
performed using the first cross-validation scheme (CV1).


5    Empirical Experiments: Data and Methodol-
     ogy
To study how the algorithms discussed in section 5 perform in terms of supe-
rior predictive ability in the context of the Global Minimum Variance portfolio,
we use the Intra-Day and Daily Closing prices of the constituent stocks of the
Nifty500 Index. We consider the time period from January 2015 to December
2022 (1724 days). The stock prices are use to compute the log-returns, which
in turn are used in the portfolio optimization problem. In particular, we are
interested in computing the portfolio variance using the inverse covariance ma-
trices estimated using the techniques discussed above. This portfolio variance,
as discussed by Jain and Jain [2019], can be used as an indicator of estima-
tion error. That is, the higher the error in estimating the precision matrix, the
more the portfolio variance. The properties (such as sparsity, condition number,
etc.) of the precision matrix estimated using a given algorithm depends on the
choice of the tuning parameter. The parameter is chosen using two five-fold
cross validation methods, discussed in 2.5.1 and 2.5.2.We consider three cases
for portfolio rebalancing: (a) Daily h = 1, (b) weekly h = 5, and (c) monthly
h = 20. Further, we divide the daily estimation horizon into two periods: (a)
Normal (2016-19) and (b) Stress (2020-2022). These two periods are considered
to see whether the Covid-19 induced economic crisis impacts the correlation
structure of the assets. This would then be possibly reflected in the relative
performances of the algorithms.
    We further perform an out-of-sample test to compare algorithm performance.
For the out-of-sample test procedure, we use our set of algorithms to estimate
the precision matrix for daily returns up until time t. We then use the intra-day
returns matrix (of the t + 1th day) to compute the portfolio variance.

                             0, 1, . . . , t        1, . . . , n
                             | {z }                 | {z }
                            training data t+1 - test data

Thus, for a training window depicted above and data X, we estimate the covari-
ance and precision matrices for all the competing methods, which finally yield
us wmin,k,t the minimum variance portfolio weights for a given method k till
period t. Using the intra-day returns (X 0 for the next day we finally estimate
the portfolio variance:
                           σmin,k,t+1 = X 0 .wmin,k,t
For 500 stocks, we use a one-period overlapping rolling window of 150 days (this
is the sample size), for daily horizon out-of-sample tests.
    To obtain the weekly t+5 and monthly t+20 returns, we use the iterated sum
of daily returns. 5 days of daily returns are summed up to get the weekly returns.
20 days of daily returns are summed up to get the monthly returns.For the


                                               23
weekly and monthly forecasting horizons, we use a rolling window of 100 weeks
and 50 months respectively. This rolling window is use to calculate the optimal
weights. We then use the next 5 and 20 days daily returns correspondingly to
calculate the portfolio variances for the weekly and monthly horizons. Similarly,
20 days of daily returns are used to arrive at the monthly returns. Proceeding
in this manner, we get a time series of losses for each method. This is then
ready to be used for the SPA and MCS tests.


6     Results for the Empirical Experiments
6.1     Properties of Estimated Precision Matrices
In this empirical experiment, we compare the summary statistics of the pre-
cision matrices (Θ̂ ) estimated using CV1 and CV2 for the Daily estimation
Horizon (150 days, 500 stocks). The estimation process used here is In-Sample,
that is the data used for tuning the hyperparameters is also used for calculating
the portfolio variance. These statistics give us an idea of the sparsity pattern,
recovery error and other properties of the estimated precision matrix. In Tables
1 and 2, the last 4 columns give summary statistics for the final recovered Θ
using 5-fold CV on Nifty500 daily returns. The variables defined in the columns
are as follows:


    • Non-Zeros indicate the sparsity of the estimated precision matrix. Higher
      number of non-zero items indicate higher sparsity.

    • Cross-Validation Error indicates two things here. CV1 Error denotes the
      error incurred while selecting parameters according to the minimum vari-
      ance of the portfolio. CV2 Error denotes the error incurred while selecting
      parameters by minimizing the variance per node.
    • Condition Number is a measure of the sensitivity of a matrix to changes
      in its inputs. Here, a high condition number indicates that the matrix is
      ill-conditioned and that small changes in the input data can lead to large
      changes in the output. This can make the estimated precision matrix
      numerically unstable and result in inaccurate estimates.

    • The walk-summable relative error is ∆W S := ||Θ̃− Θ̂||F
                                                    ||Θ̂||
                                                              , where Θ̂ is the
                                                                     F

      closest walk-summable matrix to Θ̃ in Frobenius norm. It indicates how
      close the estimated precision matrix to the theoretical walk-summable
      matrix. 1 .
   In table 1, we find that the all the estimated precision matrices are walk-
summable. This essentially means the empirical joint distribution of the cross
   1 More details on testing for the walk-summability of an estimated precision matrix can be

found in Kelner et al. [2020]



                                             24
    Method             CV1 Error     Non-zeros    Condition No.     Delta WS
    Glasso1            0.73          5.7E+4       41.62             6.15E-15
    Clime1             0.87          2.3E+4       5.37              8.49E-15
    Greedy Prune1      0.97          1.1E+4       16.02             1.38E-15
    MB1                0.78          3.4E+4       8.52              6.18E-15
    HybridMB1          0.94          3.1E+4       37.82             1.72E-14

Table 1: Results for precision matrix selected via 5-fold CV1 on Nifty500 con-
stituents


section of returns follows the assumption of walk-summability. This is interest-
ing in the sense that it makes this data particularly suitable for applying GGM
methods. We also see from the first 2 columns of the table, Graphical Lasso
achieved the greatest amount of variance reduction but returned the densest es-
timate for Θ, MB and HybridMB had slightly less portfolio variance reduction,
Greedy Prune had the sparsest estimate but least variance reduction. We also
see that the Greedy Prune, Clime, MB return the lowest condition numbers,
thus indicating better stability of the estimates. Glasso1 and HybridMB have
large condition numbers.

    Method             CV2 Error     Non-zeros    Condition No.     Delta WS
    Glasso2            0.92          5.8E+4       47.56             7.15E-15
    Clime2             1.01          2.5E+4       19.32             8.19E-15
    Greedy Prune2      1.11          1.8E+4       34.42             3.16E-15
    MB2                0.96          4.1E+4       21.69             6.72E-15
    HybridMB2          1.08          3.1E+4       41.85             3.87E-14

Table 2: Results for precision matrix selected via 5-fold CV2 on the Nifty500
constituents

    We observe similar results for CV2 in table 2. In comparison with CV2,
CV1 returns sparser Θ estimates. The condition numbers of the precision ma-
trices estimated using CV2 is higher, which indicates greater sensitivity to noise.
The last column again shows that that walk-summability is observed for all the
methods under consideration. This further supports the observations in the pre-
vious table and provides a case for using GGM methods to study historical stock
returns. A pattern clearly observed between CV1 and CV2 is the possibility of
encountering higher noise in estimated precision matrices calculated using CV2.
The question that follows is: Does it have an implication on portfolio allocation
as well ? We look at this question in more details while studying GGM methods
along with other models in the subsection that follows.




                                        25
6.2     Model Comparison for the Minimum Variance Port-
        folio
As mentioned previously, we perform an empirical experiment 2 to compare the
predictive performance of all the covariance and precision matrix estimation
approaches discussed earlier in the context of Markowitz’s portfolio allocation
model. We perform this experiment to see whether estimation errors encoun-
tered while computing the inverse covariance matrix is related to the out-of-
sample predictive ability of the algorithms under consideration. We divided our
analyses into three estimation horizons: Daily, Weekly and Monthly. We com-
pare the competing methods using MCS. Apart from this, we also consider the
equally weighted portfolio (EWP) allocation scheme. The GGM algorithms are
compared using using two cross-validation methods. Thus, we have 10 GGM
methods 3 (5 models tuned in two different ways), 5 Shrinkage methods, 3
Thresholding methods (listed in 2), the RIE estimator (based on RMT) and
the EWP model for our comparison. Thus, we have 20 models in total, which
makes the setup well suited for using the MCS procedure.
    As mentioned previously, the Model Confidence Set procedure (MCS) begins
with rejecting the inferior set of models and thereafter ranks the superior set of
models. There are two ranking schemes as mentioned in Section 3. The models
are then ranked according to their predictive ability. As mentioned earlier, MCS
assumes EPA as a null hypothesis. The results for the three estimation horizons
are presented below:

6.2.1    Comparison of Methods for the Daily Estimation Horizon
As mentioned before, we consider a rolling window of 150 days (for 500 stocks)
for out-of-sample tests. We find that for the normal period (2015-19), the algo-

        Model        RankM       vM       M CSM       RankR       vR       M CSR
        Greedy1      1           -1.51    1           3           0.19     1
        HMB1         2           -1.32    1           2           0.07     0.99
        Glasso1      3           -0.36    1           1           -0.09    0.99
        MB1          4           0.79     0.6         4           1.53     0.97
        Clime1       5           1.98     0.5         5           3.12     0.91

Table 3: Out-of-Sample MCS test for Daily Estimation Horizon (Normal Period)

rithms which use conditional variance minimizing cross-validation method are
rejected and form the inferior set of models. Along with them, the covariance
matrix estimation methods are rejected as well. This also includes the EWP.
Among the superior set of models, we find that Greedy Prune, HybridMB and
   2 Data and Code for this and some other experiments in this paper are available at: Codes

for Min-Variance Portfolio Study
   3 Algorithms tuned using CV1 are denote as Glasso1, Clime1, MB1, Greedy1 and Hy-

bridMB1. Algorithms tuned using CV2 are denote as Glasso2, Clime2, MB2, Greedy2 and
HybridMB2


                                            26
Glasso perform the best.
The subscripts M and R refer to the elimination rules associated with the test
statistics defined in equation 9. The first test statistic is associated with dˆij ,
measures the sample loss differential between models i and j. The second statis-
tic is associated with dˆi , which is a contrast of model i’s sample loss to that
of the average across all models. If for example, the second test statistic in
9 is used, then the elimination rule is chosen such that it removes the model
that contributes most to the test statistic among the models with a sample per-
formance that is worse than the average across models. Thus, Clime which is
ranked 5th according to this rule, has the largest standardized excess loss, rel-
ative to the average across all models in M. In comparison Glasso, HybridMB
and Greedy Prune have the lowest losses. The explanation for the rankings
based on the second elimination rule is similar.
    To see how the covariance estimation methods perform among themselves,
we perform a similar experiment We present the performance ranking of Shrink-
age, Thresholding and RMT Methods below: In table 4, we find that LWNL

        Model     RankM      vM       M CSM      RankR     vR       M CSR
        LWNL      1          -1.40    1          1         -0.21    1
        BDL       2          -1.25    1          2         -0.05    0.95
        LWL       3          0.52     1          3         0.08     0.87
        RBLW      4          0.63     0.69       4         1.29     0.81
        RIE       5          0.82     0.55       5         3.09     0.70

Table 4: Out-of-Sample MCS Test for Daily Estimation Horizon (Normal Pe-
riod) - for Covariance Estimation Methods

performs the best among all other models, followed by the linear shrinkage
methods and the RIE. The thresholding methods are again classified as inferior
models. This means that thresholding methods are clearly outperformed by
shrinkage methods. We again compare all the methods for the stress period:

       Model       RankM      vM      M CSM       RankR     vR      M CSR
       Greedy1     1          -2.42   1           3         -1.51   1
       HMB1        2          -1.83   1           2         -0.45   0.99
       Glasso1     3          -1.25   1           1         -0.41   0.95
       MB1         4          0.65    0.49        4         1.22    0.85
       Clime1      5          1.79    0.39        5         2.05    0.82

Table 5: Out-of-sample MCS test for Daily Estimation Horizon (Stress period)

For the Stress period (table 5), we find a similar ranking of the algorithms.
Glasso, Greedy Prune and HybridMB are the best performers. Algorithms us-
ing the conditional variance minimizing cross-validation form the inferior set
of models. While periods of economic and financial stress have been shown to
indicate positive multicollinearity and high volatility, our stress-period (2020-


                                        27
22) does not indicate any impact on the relative performance of the algorithms.
The covariance estimation methods are again classified as inferior models. Their
rankings are the same as that for the normal period. This indicates that the
stress period did not have an impact on the relative performances of the co-
variance matrix estimation methods as well. Shrinkage and RMT methods also
continue to outperform thresholding approach. Among shrinkage methods, con-
tinuous to outperform linear shrinkage estimators. The next question that arises
is related to the relative performance of all the methods for longer forecasting
horizons, viz. weekly and monthly.

6.2.2    Comparison of Methods for the Weekly Estimation Horizon
In this section, we present the results for the weekly portfolio estimation hori-
zon. We consider the same portfolio set (500 stocks) and an estimation window
of 100 weeks. Table 6 presents the Out-of-Sample test for the weekly forecast-

        Model      RankM     vM      M CSM      RankR     vR      M CSR
        Greedy1    1         -2.19   1          3         -0.52   1
        HMB1       2         -2.01   1          2         -0.39   0.99
        Glasso1    3         -1.92   0.91       1         -0.14   0.95
        MB1        4         -0.47   0.85       4         0.95    0.91
        Clime1     5         0.54    0.83       5         2.42    0.75

        Table 6: Out-of-Sample MCS Test for Weekly Estimation Horizon

ing horizon. We find that the ranking of the algorithms remains the same.
Also, the portfolio minimizing crossvalidation approach still outperforms the
conditional variance minimizing crossvalidation scheme (which is classified as
inferior). Similar to the previous case (daily), we find that EWP and the co-
variance estimation methods are categorized as inferior models. We perform the
MCS test again for the covariance estimation methods, the results for which are
given below In table 7, we see that LWNL outperforms other methods, followed

         Model    RankM     vM       M CSM     RankR     vR       M CSR
         LWNL     1         -2.34    1         1         -0.82    1
         BDL      2         -1.87    1         2         -0.35    0.99
         LW       3         -1.45    1         3         -0.11    0.99
         RIE      4         0.42     0.97      4         0.05     0.95
         RBLW     5         0.48     0.81      5         1.85     0.92

Table 7: Out-of-Sample MCS Test for Weekly Estimation Horizon - for Covari-
ance Matrix Estimation Methods

by BDL, LW, RIE and RBLW. Thresholding methods are further classified as
relatively inferior models.



                                       28
6.2.3     Comparison of Methods for the Monthly Estimation Horizon
In this section, the results for the monthly estimation horizon. Table 8 presents

         Model       RankM       vM       M CSM        RankR   vR      M CSR
         Greedy1     1           -1.64    1            3       0.02    0.97
         HMB1        2           -1.42    1            2       -0.22   0.99
         Glasso1     3           -0.12    1            1       -0.47   1
         MB1         4           0.31     0.53         4       1.48    0.61
         Clime1      5           0.70     0.39         5       3.12    0.12

        Table 8: Out-of-Sample MCS Test for Monthly Estimation Horizon

Out-of-Sample test for the monthly forecasting horizon. We find that the rank-
ing of the algorithms remains the same. Also, the GGM using portfolio minimiz-
ing cross-validation method still outperforms the conditional variance minimiz-
ing cross-validation scheme. Similar to the previous cases, we find that EWP,
GGMs implemented using the CV2 scheme and covariance matrix estimation
methods are classified as inferior models. The rankings of the covariance matrix
estimation methods are similar to the weekly estimation horizon with no par-
ticular change in the ordering of performance. Thresholding methods continue
to be classified as inferior models.
     Our results for all the three forecasting horizons suggest that there is a con-
flict in the performance rankings of Glasso1 and Greedy Prune1 when different
test statistics are used. This could possibly occur due to the choice of the test
statistics. Hence we employ the SPA test of Hansen [2005] to see whether the
performance of Glasso1 and Greedy Prune1 remains similar and whether it is
just the choice of the test statistic that contributes to the conflict in rankings.

6.2.4     Assessing the performance of Glasso and Greedy Prune
We choose the same set of methods as the one used in our empirical experiments
for comparison. Glasso1 and Greedy Prune1 are chosen as the benchmark mod-
els for testing the null hypothesis. The results for the daily estimation horizon
(normal period) are shown below: We find that both Glasso1 and Greedy1 can

                                   Model          p-value
                                   Glasso1        0.953
                                   Greedy1        0.974

Table 9: Out-of-Sample SPA test for Daily Estimation Horizon - Normal period

be chosen as benchmark models. Thus, both can be said to have comparable
levels of predictive ability and this tells us that the anomaly in the rankings
for the MCS test was possibly only due to the choice of the test statistics. The
observations are similar for weekly and monthly estimation horizons 4 .
  4 Results are available with authors on request.




                                             29
6.2.5    Estimation accuracy and Predictive Ability
Our analysis involving the GGMs, EWP and the Covariance estimation meth-
ods in the previous sections shows that the GGMs implemented using the CV1
scheme outperform all other methods. Also, none of the Shrinkage, Thresholding
and Random Matrix-based methods make it to the Superior set of models. One
possible hypothesis for this is that the precision matrices obtained by inverting
the estimated covariance matrices from Shrinkage, Thresholding and Random
Matrix-based Methods are noisier when compare to the ones directly obtained
from GGM methods. In order to probe into the possible reasons for such em-
pirical observations, we perform a synthetic experiment. We generate synthetic
data from a multivariate normal distribution where the underlying True Covari-
ance matrix comes is calculated using the Nifty-500 dataset for daily returns
using a sample size of 500. For 1000 repetitions, we estimate the precision ma-
trices using four methods: Greedy Prune, Glasso, LWNL and BDL (the sample
size is 150). The Frobenius (L2 ) norm of the difference between the true preci-
sion matrix and the estimated precision matrices is computed. The results are
presented below: The Parentheses in table 10 refer to the standard error of the

                      Model      Average Frobenius Error
                      Greedy1    9.9E+4 (11.2)
                      Glasso1    10.6E+4 (20.9)
                      LWNL       22.8E+4 (21.4)
                      BDL        23.E+4 (19.1)

Table 10: Frobenius Error for the best performing GGM and Shrinkage Methods

L2 distance between the true and the estimated precision matrices calculated
for 1000 samples. Greedy1 yields lesser error and is the most stable among all
algorithms. It is followed by Glasso1, LWNL and BDL methods in terms of
error reduction and stability.


7       Conclusion
In this paper, we compare methods estimating the covariance and precision
matrices on the basis of the estimation accuracy of the covariance and precision
matrices and its implications on portfolio allocation. Our synthetic experiments
show that the performance of the GGM algorithms is similar to that reported
in Kelner et al. [2020]. MB, Greedy Prune and HybridMB show better sample
complexity among GGMs. We also find that cross-validation scheme proposed
by us (CV1, see 2.5.1) for tuning GGM methods recovers the nodes with fewer
number of samples compared with 2.5.2. This experiment on network learning
also has implications for precision matrix. This is because the precision matrix
reveals information about the network structure of a multivariate model. Hence,
the extent of network learning should also be related to the estimation error
for the precision matrix. The first empirical analysis studies the properties of


                                       30
the estimated precision matrices yielded by GGM methods. We see that CV1
yields sparser,ess erroneous and less sensitive estimates of the precision matrix
compared to CV2. In the second empirical experiment, we compare all the
methods in the context of Markowitz’s minimum variance portfolio optimization
model. We introduce portfolio variance as the loss function and employ the
MCS test to compare different algorithms. We tune the GGM methods using
both the schemes and find that CV1 enables superior predictive performance
of the algorithms, compared to the CV2. GGM methods tuned using CV1 also
outperform the covariance matrix estimation methods. Among the superior set
of methods, Greedy, Prune, HybridMB and Glasso outperform MB and Clime.
Among the covariance matrix estimation methods, we find LWNL to outperform
the linear shrinkage estimators. Thresholding methods are clearly outperform
by the shrinkage approach. RIE also performs better than the Thresholding
methods. These observations generally hold true for all the forecasting horizons.
We also saw that the Covid-19 pandemic did not impact the relaive performance
of the algorithms.
    We find that for the two different test statistics, Glasso1 and Greedy Prune1
perform similarly well when the MCS test is used. we use the SPA test to find
out whether both of them can be used as benchmark models. It is observed
that both of them can be used as benchmark models and the change in the rank
ordering of their relative performance (using MCS test) can be attributed to
the test statistics under consideration. The comparison between GGMs and the
best performing covariance estimation methods using a synthetic experiment
also shows that estimation error for the precision matrix is indeed related to
the performance rankings observed for the portfolio allocation problem. The
paper also proposes a novel method of hyperparameter selection, which enables
comparison of GGM methods using continuous grids.


References
Anestis Antoniadis and Jianqing Fan. Regularization of wavelet approximations.
 Journal of the American Statistical Association, 96(455):939–967, 2001.
Oluwatoyin Abimbola Awoye. Markowitz minimum variance portfolio optimiza-
  tion using new machine learning methods. PhD thesis, (UCL) University
  College London, 2016.
Peter J Bickel and Elizaveta Levina. Covariance regularization by thresholding.
  The Annals of statistics, 36(6):2577–2604, 2008.
Taras Bodnar, Arjun K Gupta, and Nestor Parolya. On the strong convergence
  of the optimal linear shrinkage estimator for large dimensional covariance
  matrix. Journal of Multivariate Analysis, 132:215–228, 2014.
Joël Bun and A Knowles. An optimal rotational invariant estimator for general
  covariance matrices: The outliers. Preprint, 2018.


                                       31
Joël Bun, Romain Allez, Jean-Philippe Bouchaud, and Marc Potters. Rota-
  tional invariant estimator for general noisy matrices. IEEE Transactions on
  Information Theory, 62(12):7475–7490, 2016.
Joël Bun, Jean-Philippe Bouchaud, and Marc Potters. Cleaning large correlation
  matrices: tools from random matrix theory. Physics Reports, 666:1–109, 2017.

T Tony Cai, Jianchang Hu, Yingying Li, and Xinghua Zheng. High-dimensional
  minimum variance portfolio estimation based on high-frequency data. Journal
  of Econometrics, 214(2):482–494, 2020.
Tony Cai and Weidong Liu. Adaptive thresholding for sparse covariance matrix
  estimation. Journal of the American Statistical Association, 106(494):672–
  684, 2011.
Tony Cai, Weidong Liu, and Xi Luo. A constrained `1 minimization approach
  to sparse precision matrix estimation. Journal of the American Statistical
  Association, 106(494):594–607, 2011.

Laurent Callot, Mehmet Caner, A Özlem Önder, and Esra Ulaşan. A nodewise
  regression approach to estimating large portfolios. Journal of Business &
  Economic Statistics, 39(2):520–531, 2021.
Yilun Chen, Ami Wiesel, Yonina C Eldar, and Alfred O Hero. Shrinkage algo-
  rithms for mmse covariance estimation. IEEE Transactions on Signal Pro-
  cessing, 58(10):5016–5029, 2010.
Francis X Diebold and Robert S Mariano. Comparing predictive accuracy. Jour-
  nal of Business & economic statistics, 20(1):134–144, 2002.
David L Donoho, Iain M Johnstone, Gérard Kerkyacharian, and Dominique
  Picard. Wavelet shrinkage: asymptopia? Journal of the Royal Statistical
  Society: Series B (Methodological), 57(2):301–337, 1995.
Jianqing Fan, Yuan Liao, and Martina Mincheva. Large covariance estima-
  tion by thresholding principal orthogonal complements. Journal of the Royal
  Statistical Society: Series B (Statistical Methodology), 75(4):603–680, 2013.

Jerome Friedman, Trevor Hastie, and Robert Tibshirani. Sparse inverse covari-
  ance estimation with the graphical lasso. Biostatistics, 9(3):432–441, 2008.
Peter A Frost and James E Savarino. An empirical bayes approach to efficient
  portfolio selection. Journal of Financial and Quantitative Analysis, 21(3):
  293–305, 1986.

Peter R Hansen, Asger Lunde, and James M Nason. The model confidence set.
  Econometrica, 79(2):453–497, 2011.
Peter Reinhard Hansen. A test for superior predictive ability. Journal of Busi-
  ness & Economic Statistics, 23(4):365–380, 2005.


                                      32
Ravi Jagannathan and Tongshu Ma. Risk reduction in large portfolios: Why
  imposing the wrong constraints helps. The Journal of Finance, 58(4):1651–
  1683, 2003.
Prayut Jain and Shashi Jain. Can machine learning-based portfolios outper-
  form traditional risk-based portfolios? the need to account for covariance
  misspecification. Risks, 7(3):74, 2019.
Philippe Jorion. Bayes-stein estimation for portfolio analysis. Journal of Fi-
  nancial and Quantitative analysis, 21(3):279–292, 1986.
Jonathan Kelner, Frederic Koehler, Raghu Meka, and Ankur Moitra. Learning
  some popular gaussian graphical models without condition number bounds.
  Advances in Neural Information Processing Systems, 33:10986–10998, 2020.
Olivier Ledoit and Sandrine Péché. Eigenvectors of some large sample covariance
  matrix ensembles. Probability Theory and Related Fields, 151(1-2):233–264,
  2011.

Olivier Ledoit and Michael Wolf. Honey, i shrunk the sample covariance matrix.
  The Journal of Portfolio Management, 30(4):110–119, 2004a.
Olivier Ledoit and Michael Wolf. A well-conditioned estimator for large-
  dimensional covariance matrices. Journal of multivariate analysis, 88(2):365–
  411, 2004b.

Olivier Ledoit and Michael Wolf. Analytical nonlinear shrinkage of large-
  dimensional covariance matrices. The Annals of Statistics, 48(5):3043–3065,
  2020.
Dmitry M Malioutov, Jason K Johnson, and Alan S Willsky. Walk-sums and
 belief propagation in gaussian graphical models. The Journal of Machine
 Learning Research, 7:2031–2064, 2006.
Harry Markowitz. Portfolio selection. The Journal of Finance, 7(1):77–91, 1952.
  ISSN 00221082, 15406261. URL http://www.jstor.org/stable/2975974.
Nicolai Meinshausen and Peter Bühlmann. High-dimensional graphs and vari-
  able selection with the lasso. The annals of statistics, 34(3):1436–1462, 2006.
Attilio Meucci. Risk and asset allocation, volume 1. Springer, 2005.
Tristan Millington and Mahesan Niranjan. Robust portfolio risk minimization
  using the graphical lasso. In International Conference on Neural Information
  Processing, pages 863–872. Springer, 2017.

Sidhant Misra, Marc Vuffray, and Andrey Y Lokhov. Information theoretic
  optimal learning of gaussian graphical models. In Conference on Learning
  Theory, pages 2888–2909. PMLR, 2020.



                                       33
Dimitris N Politis and Joseph P Romano. The stationary bootstrap. Journal
  of the American Statistical association, 89(428):1303–1313, 1994.
Joseph P Romano and Michael Wolf. Stepwise multiple testing as formalized
  data snooping. Econometrica, 73(4):1237–1282, 2005.

Juliane Schäfer and Korbinian Strimmer. A shrinkage approach to large-scale
  covariance matrix estimation and implications for functional genomics. Sta-
  tistical applications in genetics and molecular biology, 4(1), 2005.
Gabriele Torri, Rosella Giacometti, and Sandra Paterlini. Sparse precision ma-
 trices for minimum variance portfolios. Computational Management Science,
 16(3):375–400, 2019.
Kenneth D West. Asymptotic inference about predictive ability. Econometrica:
  Journal of the Econometric Society, pages 1067–1084, 1996.
Halbert White. A reality check for data snooping. Econometrica, 68(5):1097–
  1126, 2000.



A      Appendix 1: Analyzing the Precision Matrix
       using Spectral Decomposition
In the context of the input estimates for the Markowitz portfolio allocation, an
important critique is related to the usage of the sample covariance estimates.
The second shortcoming is related to the role of the inverse covariance matrix
Θ ≡ Σ−1 , in the solution of the optimization problem. The accuracy of the
precision matrix estimate directly affects the accuracy of the estimation of the
weights. The relationship between the two matrices can be explicitly studied
using spectral decomposition. The eigenvector decomposition of the covariance
matrix can be expressed as Σ = V ΛV, where V is the matrix of eigenvectors with
V −1 = V 0 and Λ = diag(λ1 , . . . , λn ) with λ1 ≥ · · · ≥ λn is the diagonal matrix
of the eigenvalues sorted in decreasing order on the main diagonal. Analogously,
the eigendecomposition of the precision matrix is such that Θ = U ∆U 0 , where
∆ = diag(δ1 , . . . , δn ) with δ1 ≤ · · · ≤ δn . By inverting the covariance matrix,
we have

                                  Σ−1 = V Λ−1 V 0
   It follows that U = V and ∆ = Λ−1 with the ith element δi = λ1i ,that is,
the eigenvectors of the precision matrix are the same as those of the covariance
matrix and the eigenvalues are the reciprocal of those of the covariance matrix.
This shows how errors encountered in estimating the covariance matrix can also
impact the inverse of the estimated covariance matrix.




                                         34
B     Appendix 2: Extending Grid Size using Nelder
      Mead Optimization
The Graphical Lasso and other techniques are based on regularization tech-
niques such as Lasso which make parameter choice from a finite sized grid. The
Greedy Prune and HybridMB algorithms use two (one discrete and one continu-
ous) and one parameters respectively. The literature on GGMs does not discuss
the impact of parameter choice on the behaviour of the extrema (both local
and global) of the objective functions. This makes comparison of algorithms
heavily dependent on the choice of the range and size of the grids. Thus, there
is a scope for addressing the possibility of the usage of a finite sized grids. We
employ the Nelder Mead optimization method to address this issue. Current
literature does not discuss the behaviour of the objective function over a range
of grid values. Thus nothing can be inferred theoretically or empirically about
the possibility of convexity, continuity, etc. The method does not require any
derivative information, which makes it suitable for problems with non-smooth
functions. It is widely used to solve parameter estimation and similar statistical
problems, where the function values are uncertain or subject to noise. It can
also be used for problems with discontinuous functions, which occur frequently
in statistics and experimental mathematics.


C     Appendix 3: List of Models
Table 11 presents a list of the models studied in this paper.




                                       35
Model                    Class                    Reference
Glasso                   GGM                      Friedman et al. [2008]
MB                       GGM                      Meinshausen          and
                                                  Bühlmann [2006]
Clime                    GGM                      Cai et al. [2011]
Greedy Prune             GGM                      Kelner et al. [2020]
HybridMB                 GGM                      Kelner et al. [2020]
Ledoit Wolf Linear       Shrinkage                Ledoit and Wolf [2004b]
Rao Blackwell Ledoit     Shrinkage                Chen et al. [2010]
Wolf
Oracle Approaching       Shrinkage                Chen et al. [2010]
Bodnar Linear            Shrinkage                Bodnar et al. [2014]
Ledoit Wolf Non Linear   Shrinkage                Ledoit and Wolf [2020]
Soft                     Thresholding             Antoniadis and Fan
                                                  [2001]
Hard                     Thresholding             Chen et al. [2010]
Adaptive                 Thresholding             Cai and Liu [2011]
Rotationally Invariant   Random Matrix Theory     Bun et al. [2016]
Estimator

                Table 11: List of Estimation Techniques




                                     36