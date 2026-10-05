source: https://arxiv.org/pdf/1610.08104
fetched_utc: 2026-10-04T18:50:40Z
bytes_raw: 7060149

Cleaning large Correlation Matrices: tools from Random Matrix
                                                                                      Theory

                                                                                                       Joël Bun
                                                                            Capital Fund Management, 23–25, rue de l’Université, 75 007 Paris
arXiv:1610.08104v1 [cond-mat.stat-mech] 25 Oct 2016




                                                                      LPTMS, CNRS, Univ. Paris-Sud, Université Paris-Saclay, 91405 Orsay, France

                                                                                       Jean-Philippe Bouchaud, Marc Potters
                                                                            Capital Fund Management, 23–25, rue de l’Université, 75 007 Paris




                                                      Abstract

                                                      This review covers recent results concerning the estimation of large covariance matrices using tools
                                                      from Random Matrix Theory (RMT). We introduce several RMT methods and analytical tech-
                                                      niques, such as the Replica formalism and Free Probability, with an emphasis on the Marčenko-
                                                      Pastur equation that provides information on the resolvent of multiplicatively corrupted noisy
                                                      matrices. Special care is devoted to the statistics of the eigenvectors of the empirical correlation
                                                      matrix, which turn out to be crucial for many applications. We show in particular how these re-
                                                      sults can be used to build consistent “Rotationally Invariant” estimators (RIE) for large correlation
                                                      matrices when there is no prior on the structure of the underlying process. The last part of this
                                                      review is dedicated to some real-world applications within financial markets as a case in point. We
                                                      establish empirically the efficacy of the RIE framework, which is found to be superior in this case
                                                      to all previously proposed methods. The case of additively (rather than multiplicatively) corrupted
                                                      noisy matrices is also dealt with in a special Appendix. Several open problems and interesting
                                                      technical developments are discussed throughout the paper.
                                                      Keywords: Random matrix theory, High dimensional statistics, Correlation matrix, Spectral
                                                      decomposition, Rotational invariant estimator



                                                      Contents


                                                      1   Introduction                                                                                         5
                                                          1.1 Motivations . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .    5
                                                          1.2 Historical survey . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .    7
                                                          1.3 Outline . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .   10


                                                         Email addresses: joel.bun@gmail.com (Joël Bun), jean-philippe.bouchaud@cfm.fr (Jean-Philippe
                                                      Bouchaud), marc.potters@cfm.fr (Marc Potters)


                                                      Preprint submitted to Physics Reports                                                      October 27, 2016
2   Random Matrix Theory: overview and analytical tools                                                   13
    2.1 RMT in a nutshell . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .       13
        2.1.1 Large dimensional random matrices . . . . . . . . . . . . . . . . . . . . . . .             13
        2.1.2 Various RMT transforms . . . . . . . . . . . . . . . . . . . . . . . . . . . . .            15
    2.2 Coulomb gas analogy . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .       19
        2.2.1 Stieltjes transform and potential function . . . . . . . . . . . . . . . . . . . .          19
        2.2.2 Wigner’s semicircle law . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .         22
        2.2.3 The Marčenko-Pastur law . . . . . . . . . . . . . . . . . . . . . . . . . . . . .          23
        2.2.4 Inverse Wishart matrix . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .          25
    2.3 Free probability . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .    27
        2.3.1 Freeness . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .      27
        2.3.2 Sums of free matrices . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .         28
        2.3.3 Products of free matrices . . . . . . . . . . . . . . . . . . . . . . . . . . . . .         30
    2.4 Replica analysis . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .    31
        2.4.1 Resolvent and the Replica trick . . . . . . . . . . . . . . . . . . . . . . . . . .         31
        2.4.2 Matrix multiplication using replicas . . . . . . . . . . . . . . . . . . . . . . .          33
        2.4.3 Free multiplication: replica saddle-point analysis . . . . . . . . . . . . . . . .          35

3   Spectrum of large empirical covariance matrices                                                       37
    3.1 Sample covariance matrices . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .        37
         3.1.1 Setting the stage . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .      37
         3.1.2 Zero-mean assumption . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .         39
         3.1.3 Distribution of the data entries . . . . . . . . . . . . . . . . . . . . . . . . . .       39
    3.2 Bulk statistics . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .   40
         3.2.1 Marčenko-Pastur equation . . . . . . . . . . . . . . . . . . . . . . . . . . . . .        40
         3.2.2 Spectral statistics of the sample covariance matrix . . . . . . . . . . . . . . .          41
         3.2.3 Dual representation and edges of the spectrum . . . . . . . . . . . . . . . . .            43
         3.2.4 Solving Marčenko-Pastur equation . . . . . . . . . . . . . . . . . . . . . . . .          44
    3.3 Edges and outliers statistics . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .     49
         3.3.1 The Tracy-Widom region . . . . . . . . . . . . . . . . . . . . . . . . . . . . .           49
         3.3.2 Outlier statistics . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .     51

4   Statistics of the eigenvectors                                                                        54
    4.1 Asymptotic eigenvectors deformation in the presence of noise . . . . . . . . . . . . .            55
          4.1.1 The bulk . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .      56
          4.1.2 Outliers . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .    58
          4.1.3 Derivation of the identity (4.12) . . . . . . . . . . . . . . . . . . . . . . . . .       60
    4.2 Overlaps between the eigenvectors of correlated sample covariance matrices . . . . .              62

5   Bayesian Random Matrix Theory                                                                         68
    5.1 Bayes optimal inference: some basic results . . . . . . . . . . . . . . . . . . . . . . .         68
        5.1.1 Posterior and joint probability distributions . . . . . . . . . . . . . . . . . . .         68
        5.1.2 Bayesian inference . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .        70
    5.2 Setting the Bayesian framework . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .        71
    5.3 Conjugate prior estimators . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .        71
    5.4 Rotational invariant prior estimators . . . . . . . . . . . . . . . . . . . . . . . . . . .       74

                                                     2
6   Optimal rotational invariant estimator for general covariance matrices                             78
    6.1 Oracle estimator . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .   78
    6.2 Explicit form of the optimal RIE . . . . . . . . . . . . . . . . . . . . . . . . . . . . .     79
        6.2.1 The bulk . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .     79
        6.2.2 Outliers . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .   79
    6.3 Some properties of the “cleaned” eigenvalues . . . . . . . . . . . . . . . . . . . . . .       81
    6.4 Some analytical examples . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .     84
        6.4.1 Null Hypothesis . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .      84
        6.4.2 Revisiting the linear shrinkage . . . . . . . . . . . . . . . . . . . . . . . . . .      84
    6.5 Optimal RIE at work . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .    86
    6.6 Extension to the free multiplicative model . . . . . . . . . . . . . . . . . . . . . . . .     88

7   Application: Markowitz portfolio theory and previous “cleaning” schemes                            91
    7.1 Markowitz optimal portfolio theory . . . . . . . . . . . . . . . . . . . . . . . . . . . . 91
         7.1.1 Predicted and realized risk . . . . . . . . . . . . . . . . . . . . . . . . . . . . 92
         7.1.2 The case of high-dimensional random predictors . . . . . . . . . . . . . . . . 93
         7.1.3 Out-of-sample risk minimization . . . . . . . . . . . . . . . . . . . . . . . . . 95
         7.1.4 Optimal in and out-of-sample risk for an Inverse Wishart prior . . . . . . . . 97
    7.2 A short review on previous cleaning schemes . . . . . . . . . . . . . . . . . . . . . . . 99
         7.2.1 Linear Shrinkage . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 100
         7.2.2 Eigenvalues clipping . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 101
         7.2.3 Eigenvalue substitution . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 102
    7.3 Factor models . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 105

8   Numerical Implementation and Empirical results                                                  108
    8.1 Finite N regularization of the optimal RIE (6.26) . . . . . . . . . . . . . . . . . . . . 108
        8.1.1 Why is there a problem for small-eigenvalues? . . . . . . . . . . . . . . . . . . 108
        8.1.2 Regularizing the empirical RIE (6.26) . . . . . . . . . . . . . . . . . . . . . . 109
        8.1.3 Quantized Eigenvalues Sampling Transform (QuEST) . . . . . . . . . . . . . 111
        8.1.4 Empirical studies . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 113
    8.2 Optimal RIE and out-of-sample risk for optimized portfolios . . . . . . . . . . . . . . 116
    8.3 Out-of-sample risk minimization . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 120
    8.4 Testing for stationarity assumption . . . . . . . . . . . . . . . . . . . . . . . . . . . . 123
        8.4.1 Synthetic data . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 124
        8.4.2 Financial data . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 124

9   Conclusion and perspectives                                                                       129
    9.1 Extension to more general models of covariance matrices . . . . . . . . . . . . . . . . 129
    9.2 Singular Value Decomposition . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 130
    9.3 Estimating the eigenvectors . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 132
    9.4 Cleaning recipe for q > 1 . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 132
    9.5 A Brownian Motion model for correlated Wishart matrices . . . . . . . . . . . . . . 133

10 References                                                                                          135


                                                    3
A      Harish-Chandra–Itzykson-Zuber integrals                                                    146
    A.1 Definitions and results . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 146
    A.2 Derivation of (A.5) in the Rank-1 case . . . . . . . . . . . . . . . . . . . . . . . . 147

B         Reminders on linear algebra                                                                 149
    B.1     Schur complement . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 149
    B.2     Matrix identities . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 149
    B.3     Resolvent identities . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 150

C         Self-consistent relation for Green’s function and Central Limit Theorem                     151
    C.1       Wigner matrices . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 151
    C.2       Sample covariance matrices . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 152

D      Additive noise model                                                                     155
    D.1 Gaussian external noise . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 155
        D.1.1 Schur complement arguments . . . . . . . . . . . . . . . . . . . . . . . . . . 155
        D.1.2 Dyson Brownian Motion . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 156
    D.2 Extension to an arbitrary rotational invariant noise . . . . . . . . . . . . . . . . 158
        D.2.1 An elementary derivation of the free addition formula . . . . . . . . . . . . 158
        D.2.2 Asymptotic resolvent of (D.1) . . . . . . . . . . . . . . . . . . . . . . . . . . 160
    D.3 Overlap and Optimal RIE formulas in the additive case . . . . . . . . . . . . . . 160
        D.3.1 Mean squared overlaps . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 160
        D.3.2 Optimal RIE . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 161

E         Conventions, notations and abbreviations                                                   164




                                                    4
1. Introduction

1.1. Motivations. In the present era of “Big Data”, new statistical methods are needed to decipher
large dimensional data sets that are now routinely generated in almost all fields – physics, image
analysis, genomics, epidemiology, engineering, economics and finance, to quote only a few. It
is very natural to try to identify common causes (or factors) that explain the joint dynamics of
N quantities. These quantities might be daily returns of the different stocks of the S&P 500,
temperature variations in different locations around the planet, velocities of individual grains in a
packed granular medium, or different biological indicators (blood pressure, cholesterol, etc.) within
a population, etc., etc. The simplest mathematical object that quantifies the similarities between
these observables is an N × N correlation matrix C. Its eigenvalues and eigenvectors can then
be used to characterize the most important common dynamical “modes”, i.e. linear combinations
of the original variables with the largest variance. This is the well known “Principal Component
Analysis” (or PCA) method. More formally, let us denote by y ∈ RN the set of demeaned and
standardized1 variables which are thought to display some degree of interdependence. Then, one
possible way to quantify the underlying interaction network between these variables is through the
standard, Pearson correlations:
                                                
                                    Cij = E yi yj , i, j ∈ [[1, N ]],                           (1.1)

We will refer to the matrix C as the population correlation matrix throughout the following.
    The major concern in practice is that the expectation value in (1.1) is rarely computable precisely
because the underlying distribution of the vector y is unknown and is what one is struggling to
determine. Empirically, one tries to infer the matrix C by collecting a large number T of realizations
of these N variables that defines the input sample data matrix Y = (y1 , y2 , . . . , yT ) ∈ RN ×T . Then,
in the case of a sufficiently large number of realizations T , one tempting solution to estimate C is
to compute that sample correlation matrix estimator E, defined as:
                                                T
                                          1X              1
                                  Eij ..=       Yit Yjt ≡   (YY∗ )ij ,                                    (1.2)
                                          T t=1           T

where Yit is the realization of the ith observable (i = 1, . . . , N ) at “time” t (t = 1, . . . , T ) that will
be assumed in the following to be demeaned and standardized (see previous footnote).
    Indeed, in the case where N  T , it is well known using result of classical multivariate statistics
that E converges (almost surely) to C [1]. However, when N is large, the simultaneous estimation
of all N (N − 1)/2 the elements of C – or in fact only of its N eigenvalues – becomes problematic
when the total number T of observations is not very large compared to N itself. In the example
of stock returns, T is the total number of trading days in the sampled data; but in the biological
example, T would be the size of the population sample, etc. Hence, in the modern framework of
high-dimensional statistics, the empirical correlation matrix E (i.e. computed on a given realization)
must be carefully distinguished from the “true” correlation matrix C of the underlying statistical
process (that might not even be well defined). In fact, the whole point of the present review is
to characterize the difference between E and C, and discuss how well (or how badly) one may
reconstruct C from the knowledge of E in the case where N and T become very large but with

  1 This apparently innocuous assumption will be discussed in Chapter 3.




                                                       5
their ratio q = N/T not vanishingly small; this is often called the large dimension limit (LDL), or
else the “Kolmogorov regime”.
    There are numerous situations where the estimation of the high-dimensional covariance matrix
is crucial. Let us give some well-known examples:
  (i) Generalized least squares (GLS): Suppose we try to explain the vector y using a linear model

                                               y = Xβ + ε,                                     (1.3)

     where X is a N × k design matrix (k ⩾ 1), β denotes the regression coefficients to these k
     factors, and ε denotes the residual. Typically, one seeks to find β that best explains the data
     and this exactly the purpose of GLS. Assume that E[ε|X] = 0 and V[ε|X] = C the covariance
     matrix of the residuals. Then GLS estimates β as (see [2] for a more detailed discussion):
                                       b = (X ∗ CX)−1 X ∗ C−1 y.
                                       β                                                       (1.4)

      We shall investigate this estimator in Section 7.
 (ii) Generalized methods of moments (GMM): Suppose one wants to calibrate the parameters Θ
      of a model on some data set. The idea is to compute the empirical average of a set of k
      functions (generalized moments) of the data, which should all be zero for the correct values
      of the parameters, Θ = Θ0 . The distance to zero is measured using the covariance of these
      functions. A precise measurement of this k × k covariance matrix increases the efficiency of
      the GMM – see [3]. Note that GLS is a special form of GMM.
(iii) Classification [4]: Suppose that we want to classify the variables y between two Gaussian
      populations with different mean µ1 and µ2 , priors π1 and π2 , but same covariance matrix C.
      The Linear Discriminant Analysis rule classifies y to class 2 if
                                            1
                      x∗ C−1 (µ1 − µ2 ) >     (µ + µ1 )∗ C−1 (µ2 − µ1 ) − log(π2 /π1 )         (1.5)
                                            2 2
(iv) Large portfolio optimization [5]: Suppose we want to invest on a set of financial assets y in
     such a way that the overall risk of the portfolio is minimized, for a given performance target
     ν. According to Markowitz’s theory, the optimal investment strategy is a vector of weights
     w ..= (w1 , . . . , wp )∗ that can be obtained through a quadratic optimization program where
     we minimize the variance of the strategy hw , Cwi subject to a constraint on the expectation
     value hw , gi ⩾ µ, with g a vector of predictors and µ fixed. (Other constraints can also be
     implemented). The optimal strategy reads

                                                       C−1 g
                                              w=ν              .                               (1.6)
                                                      g∗ C−1 g
As we shall see in Chapter 7, a common measure of the “risk” of estimation in high-dimensional
problems like (i) and (iv) above is given by TrE−1 /TrC−1 , which turns out to be very close to
unity T is large enough for a fixed N , i.e. when q = N/T → 0. However, when the number
of observables N is also large, such that the ratio q is not very small, we will find below that
TrE−1 = TrC−1 /(1 − q) for a wide class of processes. In other words, the out-of-sample risk TrE−1
can excess by far the true optimal risk TrC−1 when q > 0, and even diverge when q → 1. Note
that for a similar scenario when Value-at-Risk is minimized in-sample was elicited in [6] and in
[7] for the Expected Shortfall. Typical number in the case of stocks is N = 500 and T = 2500,


                                                  6
corresponding to 10 years of daily data, already quite a long strand compared to the lifetime of
stocks or the expected structural evolution time of markets, but that corresponds to q = 0.2. For
macroeconomic indicators – say inflation, 20 years of monthly data produce a meager T = 240,
whereas the number of sectors of activity for which inflation is recorded is around N = 30, such
that q = 0.125. Clearly, effects induced by a non zero value of q are expected to be highly relevant
in many applications.

1.2. Historical survey. The rapid growth of RMT (Random Matrix Theory) in the last two decades
is due both to the increasing complexity of the data in many fields of science (the “Big Data” phe-
nomenon) and to many new, groundbreaking mathematical results that challenge classical results
of statistics. In particular, RMT has allowed a very precise study of large sample covariance ma-
trices and also the design of estimators that are consistent in the large dimensional limit (LDL)
presented above. The aim of this review is to provide the reader an introduction to the different
RMT inspired techniques that allow one to investigate problems of high-dimensional statistics, with
the estimation of large covariance matrices as the main thread.
    The estimation of covariance matrices is a very old problem in multivariate statistics and one of
the most influential work goes back to 1928 with John Wishart [8] who investigated the distribution
of the sample covariance matrix E in the case of i.i.d Gaussian realizations y1 , y2 , . . . , yT . In
particular, Wishart obtained the following explicit expression for the distribution of E given C [8]:
                                                                  T −N −1
                                                 T N T /2    det(E) 2       T    −1
                            PW (E|C) =       N T /2                 T /2
                                                                         e− 2 TrC E ,                (1.7)
                                            2       ΓN (T /2) det(C)

where ΓN (·) is the multivariate Gamma function with parameter N .2 In Statistics, one says that E
follows a Wishart(N, T, C/T ) distribution and it is often referred to as one of the first result in RMT.
Note that for a finite N and T , the marginal probability density distribution of the eigenvalues is
known [9]:
                                     N −1
                                   1 X        k!        T −N 2 T −N −λ
                         ρN (λ) =                       L      (λ) λ       e ,                        (1.8)
                                   N      T −N +k k
                                             k=0

where we assumed that T > N and Llk are the Laguerre polynomials3 .
    Even though the Wishart distribution gives us many important properties concerning E, the
behavior of the sample estimator as a function of N was understood much later with the pioneering
work of Charles Stein in 1956 [10]. The most important contribution of Stein can be summarized
as follows: when the number of variables N ⩾ 3, there exist combined estimators more accurate in
terms of mean squared error than any method that handles the variables separately (see [11] for an
elementary introduction). This phenomenon is called Stein’s paradox and establishes in particular
that the sample matrix E becomes more and more inaccurate as the dimension of the system N
grows. The idea of “combined” estimators has been made precise with the James-Stein estimator
[12] for the mean of a Gaussian vector that outperforms traditional methods such as maximum
likelihood or least squares whenever N ⩾ 3. To achieve this, the authors used a Bayesian point
of view, i.e. by assuming some prior probability distribution on the parameters that we aim to
estimate. For sample covariance matrices, Stein’s paradox also occurs for N ⩾ 3 as shown by using


  2Γ           N (N −1)/4
                           QN
     N (u) = π                j=1 Γ(u + (1 − j)/2).
               λ     k
  3 Ll (λ) = e     d
                        (e−λ λk+l ).
     k           l
             k!λ dλ   k




                                                         7
properties of the Wishart distribution and the so-called conjugate prior technique (see Chapter 5).
This was first shown for the precision matrix C−1 in [13, 14] and then for the covariance matrix C
in [15] and lead to the famous linear shrinkage estimator

                                       Ξ = αs E + (1 − αs )IN ,                                    (1.9)

where Ξ denotes, here and henceforth, an estimator of C and αs ∈ (0, 1) is the shrinkage intensity
parameter. In [15], Haff proposed to estimate αs using the marginal probability distribution of
the observed matrix Y as advocated in the so-called empirical Bayes framework. We see that this
shrinkage estimator interpolates between the empirical “raw” matrix E (no shrinkage, αs = 1) and
the null hypothesis IN (extreme shrinkage, αs = 0). This example illustrates the idea of a combined
estimator, not based only on the data itself, that offers better performance when the dimension
of the system grows. The improvement made by using the simple estimator (1.9) rather than the
sample covariance matrix E has been precisely quantified much later in 2004 [16] in the asymptotic
regime N → ∞, with an explicit and observable estimator for the shrinkage intensity αs . To
summarize, the Bayesian approach turns out to be a cornerstone in estimating high dimensional
covariance matrices and will be discussed in more details in the Section 5.
    Interestingly, the first result on the behavior of sample covariance matrices in the LDL did not
come from the statistics community. It is due to the seminal work of Marčenko and Pastur in 1967
[17] where they obtained a self-consistent equation for the spectrum of E given C as N goes to
infinity. In particular, the influence of the quality ratio q appears precisely. Indeed, it was shown in
the classical limit T → ∞ and N fixed in 1963 by Anderson that the sample eigenvalues converge to
the population eigenvalues [18], a result indeed recovered by the Marčenko-Pastur formula for q = 0.
However, when q = O(1), the same formula shows that all the sample eigenvalues become noisy
estimators of the “true” (population) ones no matter how large T is. This is also called the curse
of dimensionality. More precisely, the distortion of the spectrum of E compared to the “true” one
becomes more and more substantial as q becomes large (see Figure 1.1). The heuristic behind this
phenomenon is as follows. When the sample size T is very large, each individual coefficient of the
covariance matrix C can be estimated with negligible error (provided one can assume that C itself
does vary with time, i.e. that the observed process is stationary). But if N is also large and of the
order of T , as is often the case in many situations, the sample estimator E becomes “inadmissible”.
More specifically, the large number of simultaneous noisy variables creates important systematic
errors in the computation of the eigenvalues of the matrix.
    The Marčenko-Pastur result had a tremendous impact on the understanding the “curse of di-
mensionality”. Firstly, it was understood in 1995 that this result is to a large degree universal
when N → ∞ and q = O(1), much as the Wigner semi-circle law is universal: the Marčenko-Pastur
equation is valid for a very broad range of random measurement processes and for general popula-
tion covariance matrix C [19, 20, 21]. This property is in fact at the core of RMT which makes this
theory particularly appealing. At the same time, some empirical evidence of the relevance of these
results for sample covariance matrices weres provided in [22, 23] using financial data sets, which are
known to be non-Gaussian [24]. More precisely, these works suggested that most of the eigenvalues
(the bulk ) of financial correlation matrices agrees, to a first approximation, with the null hypothesis
C = I, while a finite number of “spikes” (outliers) reside outside of the bulk. This observation is the
very essence of the spiked covariance matrix model named after the celebrated paper of Johnstone
in 2001 with many applications in principal components analysis (PCA) [25]. Indeed, the author
showed another manifestation of universal properties of RMT, namely the Tracy-Widom distribu-
tion for the top bulk eigenvalues in the spiked covariance matrix [26, 25]. This result suggest that


                                                   8
                             1.0




                             0.8
                                                                    q=0
                                                                    q = 0.25
                                                                    q = 0.5
                             0.6


                      ρ(λ)
                             0.4




                             0.2




                             0.0
                               0.0   0.5    1.0        1.5    2.0        2.5     3.0
                                                       λ

Figure 1.1. Plot of the sample eigenvalues and the corresponding sample eigenvalues density under the
null hypothesis with N = 500. The blue line (q = 0) corresponds to a perfect estimation of the population
eigenvalues. The larger is the observation ratio q, the wider is the sample density. We see that even for
T = 4N , the deviation from the population eigenvalues is significant.



the edge of the bulk of eigenvalues is very rigid in the sense that the position of the edge has very
small fluctuations of order T −2/3 . This provides a very simple recipe to distinguish meaningful
eigenvalues (beyond the edge) from noisy ones (inside the bulk) [27, 23]. This method is known
as “eigenvalue clipping”: all eigenvalues in the bulk of the Marčenko-Pastur spectrum are deemed
as noise and thus replaced by a constant value whereas the principal components outside of the
bulk (the spikes) are left unaltered. This very simple method provides robust out-of-sample per-
formance [28] and emphasizes that the notion of regularization – or cleaning – is very important in
high-dimension.
    Even if the spiked covariance matrix model provides quite satisfactory results in many different
contexts [28], one may want to work without such an assumption on the structure of C using the
Marčenko-Pastur equation to reconstruct numerically the spectrum of C [29]. However, this is
particularly difficult in practice since the Marčenko-Pastur equation is easy to solve in the other
direction, i.e. knowing the spectrum of C, we easily get the spectrum of E. In that respect, many
studies attempting to “invert” the Marčenko-Pastur equation appeared since 2008 [28, 30, 31, 32].
The first one consists in finding a parametric “true” spectral density that fits the data [28]. The
method of [30], further improved in [31], is completely different. Under the assumption that the
spectrum of C consists of a finite number of eigenvalues, an exact analytical estimator of each
population eigenvalue is provided. However, this method requires some very strong assumptions on
the structure of the spectrum of C. The last approach can be considered as a nonparametric method
and seems to be very appealing. Indeed, El Karoui proposed a “consistent” numerical scheme to
invert the Marčenko-Pastur equation using the observed sample eigenvalues [32]. Nevertheless,
while the method is very informative, it turns out that the algorithm also needs prior knowledge
on the location of the true eigenvalues which makes the implementation difficult in practice.


                                                   9
    These inversion schemes thus allow in principle to retrieve the spectrum of C but as far as es-
timating high-dimensional covariance matrices is concerned, merely substituting the sample eigen-
values by the estimated “true” ones does not give a satisfactory answer to our problem. Indeed, the
Marčenko-Pastur equation only describes the spectrum of eigenvalues of large sample covariance
matrices but does not yield any information about the eigenvectors of E. In fact, except for some
work by Jack Silverstein around 1990 [33, 34], most RMT results about sample covariance matrices
were focused on the eigenvalues, as discussed above. The first fundamental result on the eigen-
vectors of E was obtained in [35] in the special case of the spiked covariance matrix model, but is
somehow disappointing for inference purposes. Indeed, Paul noticed that outliers’ eigenvectors obey
a cone concentration phenomenon with respect to the true eigenvectors whereas all other ones re-
tain very little information [35]. Differently said, the eigenvectors of E are not consistent estimators
of the eigenvectors of C in the high-dimensional framework. A few years later, these observations
were generalized to general population covariance matrices C [36, 37, 38, 39, 40]. When dealing
with the estimation of C, information about eigenvectors has to be taken into account somehow
in the inference problem. Clearly, the above “eigenvalue substitution” method cannot be correct
as it proposes to take the best estimates of the eigenvalues of C but in an unknown eigenvalue
basis. Consequently, a different class of estimators flourished very recently that we shall refer to
as rotational invariant estimators 4 (RIE) [36, 37, 38]. In this particular class of estimators, the
main assumption is that any estimator Ξ of C must share the same eigenvectors as E itself. This
hypothesis has a very intuitive interpretation in practice as it amounts to posit that one has no prior
insights on the structure of C, i.e. on the particular directions in which the eigenvectors of C must
point. It is easy to see that the linear shrinkage estimator (1.9) falls into this class of estimators.
Compared to the aforementioned RMT-based methods, RIE explicitly uses the information on the
eigenvectors of E, in particular their average overlap with the true eigenvectors. It turns out that
one can actually obtain an optimal estimator of C in the LDL for any general population covariance
matrix C [38]. Note that the optimal estimator is in perfect agreement with Stein’s paradox, that
is to say, the optimal cleaning recipe takes into account about the information of all eigenvectors
and all eigenvalues of E. The conclusion is therefore that combining all the information’s about E
always provide more accurate prediction than any method that handles the parameters separately
within the modern era of “Big Data”. We summarize the above long journey concerning the esti-
mation of large sample covariance matrices in Figure 1.2, which can be seen as a thumbnail picture
of the present review. Note that a very recent work [40] attempts to incorporate prior information
on the true components. While it remains unclear how to use this framework for the estimation
of correlation, this may allows one to construct “optimal” non-rotational invariant estimators. We
shall address this issue at the end of this review.

1.3. Outline. Our aim is to review several Random Matrix Theory (RMT) results that take ad-
vantage of the high-dimensionality of the problem to estimate covariance matrices consistently,
spanning nearly fifty years of research from the result of Marčenko and Pastur [17] to the very
recent “local” optimal RIE for general population covariance matrices [38]. We emphasize that this
review is not intended to provide detailed proofs (in the mathematical sense) but we will include
references to this mathematical literature as often as possible for those who might be interested.
    In Chapter 2, we begin with a detailed but still incomplete introduction to RMT and some of
the analytical methods available to study the behavior of large random matrices in the asymptotic

  4 This is sometimes called rotation-equivariant estimators




                                                        10
                          5


                                        clipping
                                        linear
                          4
                                        rie



                          3


                      ξ
                          2




                          1




                          0
                              0     1              2        3        4          5
                                                        λ


Figure 1.2. (Color online). Three shrinkage transformations: “cleaned” eigenvalues on the y-axis as a
function of the sample eigenvalues (see Chapter 8 for more details). This figure is a quick summary the
evolution of shrinkage estimators starting with the linear method (green), then the heuristic eigenvalues
clipping method (red) to the optimal RIE (blue).



regime. In fact, most of the computations in Chapter 2 will be performed under very general model
of random matrices and will be used throughout the following. The first method is arguably the
most frequently used in the Physics literature known as the Coulomb gas analogy [41]. This is
particularly useful to deal with invariant ensembles, leading to Boltzmann-like weights that allows
one to recover very easily well-known results such as Wigner’s semicircle law [42] or Marčenko-
Pastur density [17]. This is the main purpose of Section 2.2. The second method is Voiculescu’s
free probability theory which was originally proposed in 1985 to understand a special class of von
Neumann algebras through the concept of freeness [43]. Loosely speaking, two matrices A and B are
mutually free if their eigenbasis are related to one another by a random rotation, or said differently
if the eigenvectors of A and B are almost surely orthogonal. Voiculescu discovered in 1991 [44] that
some random matrices do satisfy asymptotically the freeness relation, which considerably influenced
RMT. We present in Section 2.3 a precise definition of the concept of freeness and then provide
some applications for the computations of the spectral density of a large class of random matrices.
In Section 2.4, we present a more formal tool known as the Replica method in statistical physics of
disordered systems [45, 46]. While being less rigorous, this method turns out to be very powerful
to compute the average behavior of large complex systems (see [47] for a recent review). In our
case, we shall see how this method allows us to compute the resolvent of a large class of random
matrices which will be especially useful to deal with the statistics of eigenvectors.
  In Chapters 3 and 4, we study in details the different properties of large sample covariance
matrices. Chapter 3 is dedicated to the statistics of the eigenvalues of E, and in particular we


                                                       11
propose a very simple derivation of the Marčenko-Pastur equation using tools from free probability
theory. Then, we review different properties that we can learn about C using E such as the moment
generating functions, or the edges of the support of the spectral density of E. We discuss the
properties of the edges of the distribution for finite N and also the outliers. In Chapter 4, we focus
the recent results concerning the eigenvectors of E for a general C. We distinguish two different
cases. The first one is the angle between the true and estimated eigenvectors and we shall see that
the initial results of [35] hold for a general C. The second case is the angle between two independent
sample eigenvectors, a result that allows one to infer interesting properties about the structure of
C.
    After these three relatively technical sections, we then turn on the main theme of this review
which is the estimation of large sample covariance matrices. In Chapter 5, we formalize the Bayesian
method for covariance matrices. We present the class of conjugate prior from which we re-obtain
the linear shrinkage (1.9) initially derived by Haff [15]. Next, we consider the class of Boltzmann-
type, rotational invariant prior distributions. We then relate the Bayes optimal estimator with the
least squares optimal oracle estimator of C. The so-called oracle estimator is the main quantity
of interest in the following Chapter 6. In particular, we show that this estimator converges to
a limiting and – remarkably – fully observable function in the limit of large dimension using the
results on eigenvectors obtained in Chapter 4. Hence, there exists an optimal estimator of large
population covariance C depending only on E inside the class of RIEs. The rest of the Chapter 6
is dedicated to some theoretical and numerical applications of the optimal RIE.
    Chapter 7 concerns the applications of the optimal RIE for Markowitz optimal portfolio. In
particular, we characterize explicitly, under some technical assumptions, the danger of using the
sample covariance matrix E in a large scale and out-of-sample framework. As alluded to above, we
shall see that if E has no exact zero mode (i.e. when q = N/T < 1), the realized risk associated to
this “naive” estimator overestimate the true risk by a factor (1 − q)−1 . Also, we shall see that the
best we can do in order to minimize the out-of-sample risk is actually given by the optimal RIE of
the Chapter 6. Several alternative cleaning “recipes”, proposed in previous work, are also reviewed
in that Chapter.
    Finally, Chapter 8 contains empirical results using real financial data sets. We give further evi-
dence that using a correctly regularized estimator of C is highly recommended in real life situations.
Moreover, we discuss about the implementation of the optimal RIE in the presence of finite size
effects, to wit, when N is large but finite.
    The appendices contain auxiliary results which are mentioned in the paper. The first appendix
copes with the so-called Harish-Chandra–Itzykson-Zuber (HCIZ) integral which routinely appears
in calculations involving sums or products of free random matrices. The HCIZ is an integral over
the group of orthogonal matrices for which explicit and analytical results are scarce. The second
appendix is a reminder on some results of linear algebra which are particularly useful for the study
of eigenvectors. The third appendix is another analytical tool in RMT to establish self-consistent
equations for the resolvent (or the Stieltjes transform) of large random matrices. This technique
is very convenient when working with independent entries and it provides a nice illustration of the
Central Limit Theorem for random matrices. However, the formalism is not as synthetic as the
method provided in Chapter 2 but is now standard in the RMT literature, which is why we relegate
its presentation to an appendix. Finally, we devote a full appendix to the case where the noise in
the matrix is additive, rather than multiplicative for correlation matrices. Although not directly
relevant to the main issue discussed in the present review, the additive noise model is interesting
in itself and finds many applications in different fields of science.


                                                 12
2. Random Matrix Theory: overview and analytical tools

2.1. RMT in a nutshell.
2.1.1. Large dimensional random matrices. As announced in the introduction, the main analytical
tool that we shall review in this article is Random Matrix Theory (RMT). In order to be as self-
contained as possible, we recall in this section some of the basic results and techniques of RMT.
The study of random matrices began with the work of Wishart in 1928, who was interested in
the distribution of the so-called empirical (or sample) covariance matrices, which ultimately lead
to the Marčenko-Pastur distribution in 1967. RMT was also introduced by Wigner in the 1950’s
as a statistical model for the energy levels of heavy nuclei, and lead to the well-known Wigner
semi-circle distribution, as well as Dyson’s Brownian motion (see e.g. [48], [49] for comprehensive
reviews). Branching off from these early physical and statistical applications, RMT has become a
vibrant research field of its own, with scores of beautiful results in the last decades – one of the most
striking being the discovery of the Tracy-Widom distribution of extreme eigenvalues, which turns
out to be related to a large number of topics in statistical mechanics and probability theory [50, 51].
Here, we will only consider the results of RMT that pertain to statistical inference, and leave aside
many topics – see e.g. [49], [52], [53], [54], [55] or [56] for more detailed and rigorous introductions
to RMT. We will also restrict to square, symmetric correlation matrices, even though the more
general problem of rectangular correlation matrices (measuring the correlations between M input
variables and N output variables) is also extremely interesting. This problem leads to the so-called
Canonical Component Analysis [57] and can be dealt with the Singular Value Decomposition, for
which partial results are available, see e.g. [58, 59].
    We begin with a formal definition of “large” random matrices. A common assumption in RMT
is that the matrix under scrutiny is of infinite size. However, this is obviously not a realistic assump-
tion for practical problems where one rather deals with large but finite N dimensional matrices.
Nonetheless, we shall see that working in the N → ∞ limit leads to very precise approximations
of the properties of large but finite matrices. More precisely, it is well known that probability
distributions describing the fluctuations of macroscopic observables often converge to limiting laws
in the limit of large sizes. Hence, we expect that the statistical properties (say the distribution of
eigenvalues) of a random matrix M of dimension N shows, to a certain extent, a deterministic or
self-averaging behavior5 when the dimension N goes to infinity. These deterministic features can be
used to characterize the matrix under scrutiny, provided it is large enough. This is why we consider
the limit N → ∞ from now on.
    The limiting behavior of “large” random matrices is in fact at the heart of RMT, which predicts
that infinite dimensional matrices do display universal features, both at the macroscopic and at
the microscopic levels. To be more precise, we define a N × N random matrix6 M with a certain
probability measure Pβ (M), where β is the Dyson’s threefold way index and specifies the symmetry
properties of the ensemble (β = 1 for Orthogonal, β = 2 for Unitary and β = 4 for Symplectic
ensembles). A property is said to be universal if it does not depend on the specific probability
measure Pβ (M). One well known example of universality pertains to the distribution of the distance
s between two successive eigenvalues (see [60] for an extended discussion).
    The ensemble most relevant for our purpose is the Orthogonal one, which deals with real sym-
metrical matrices. In this case, the matrix M is said to be rotationally invariant if the probability

  5 i.e. independent of the specific realization of the matrix itself
  6 Boldface letters will refer throughout this paper to matrices.




                                                           13
is invariant under the transformation M → ΩMΩ† for any matrix Ω belonging to the Orthogonal
group O(N ), i.e. Pβ (M) = Pβ (ΩMΩ† ), ∀Ω ∈ O(N ). A typical example of invariant measure in
the physics literature is that Pβ (M) is of the form of a Boltzmann distribution:
                                                         βN
                                    Pβ (M)DM ∝ e− 2 TrV (M) DM                                     (2.1)
                                                    QN          QN
with V the so called potential function and DM = i=1 dMii i<j dMij denotes the (Lebesgue) flat
measure. The rotational invariant property is evident since the above parametrization only involves
the trace of powers of M. Already at this stage, it is interesting to notice that the distribution (2.1)
can alternatively be rewritten in terms of the eigenvalues and eigenvectors of M as:
                                                         N                    N
                                                                             Y           
                                       βN PN             Y
                     Pβ (M)DM ∝ e− 2       i=1 V (νi )         |νi − νj |β         dνi     dΩ ,    (2.2)
                                                         i<j                 i=1


where the Vandermonde determinant ( |νi − νj |β )comes from the change of variables (from the
                                         Q
Mij to the νi and Ωij ). This representation is extremely useful, as will be illustrated below.
    What kind of universal properties can be of interest in practice? Let us consider a standard
problem in multivariate statistics. Suppose that we have a very large dataset with correlated vari-
ables. A common technique to deal with this large dataset is to reduce the dimension of the problem
using for instance a principal component analysis (PCA), obtained by diagonalizing the covariance
matrix of the different variables. But one can wonder whether the obtained eigenvalues νi and their
associated eigenvectors are reliable or not (in a statistical sense). Hence, the characterization of
eigenvalues (and eigenvectors) is an example of features that one would like to know a priori. In that
respect, RMT provided (and continues to provide) many groundbreaking results on the eigenvalues
and the eigenvectors of matrices belonging to specific invariant ensembles (Unitary, Orthogonal
and Symplectic). The distribution of the eigenvalues {νi } : i = {1, . . . , N }} can be characterized
through the Empirical Spectral Distribution (ESD) (also known as the “Eigenvalue Distribution”):
                                                         N
                                                 1 X
                                      ρN
                                       M (x) =         δ(x − νi )                                  (2.3)
                                                 N i=1

with δ the Dirac delta function. Note that the symmetry of the considered matrices ensures that
the eigenvalues of M are defined on the real line (complex eigenvalues are beyond the scope of this
review, but see [55, 56, 61] for more on this). One of the most important property of large random
matrices is that one expects the ESD to converge (almost surely in many cases) to a unique and
deterministic limit ρNM → ρM as N → ∞. Note that it is common to refer to this deterministic
density function ρM as the Limiting Spectral Density (LSD), or else the “Eigenvalue Spectrum” of
the matrix. An appealing feature of RMT is the predicted self-averaging (sometimes call ergodicity
or concentration) property of the LSD: when the dimension N becomes very large, a single sample
of M spans the whole eigenvalue density function, independently of the specific realization of M.
The consequence of this self-averaging property is that we can replace the computation of the ESD
(2.3) for a specific M by the average according to the probability measure of M (e.g. over the
measure (2.1)):
                                                            *     N
                                                                               +
                                   N                N         1 X
                   ρM (x) = lim ρM (x), with ρM (x) =               δ(x − νi )   .             (2.4)
                             N →∞                             N i=1
                                                                                              M


                                                    14
    For real life data-sets, it is often useful to distinguish the eigenvalues that lie within the spectrum
of ρM from those that are well separated from it. We will refer to the first category as the bulk of the
eigenvalues with a slight abuse of notation. We will call the second type of eigenvalues outliers or
spikes. Throughout this work, we assume the LSD that describes the bulk of ρM to be a non-negative
continuous function, defined on an unique compact support – denoted supp[ρM ] – meaning that
supp[ρM ] consists of a single “bulk” component (often called the one-cut assumption). Moreover,
we allow the presence of a finite number r  N of outliers, which are of crucial importance in many
fields. Throughout this chapter, we shall denote by ν1 ≥ ν2 ≥ · · · ≥ νN the eigenvalues of M. We
furthermore define the associated eigenvectors by w1 , w2 , . . . , wN . For N that goes to infinity, it
is often convenient to index the eigenvectors by their corresponding eigenvalues, i.e. wi ≡ wνi for
any integer 1 ≤ i ≤ N , and this is the convention that we adopt henceforth.
2.1.2. Various RMT transforms. We end this section with an overview of different transforms that
appear in the RMT literature. These transforms are especially useful to study the spectral properties
of random matrices in the limit of large dimension, and to deal with sums and products of random
matrices.
Resolvent and Stieltjes transform. We start with the resolvent of M which is defined as7

                                           GM (z) := (zIN − M)−1 ,                                               (2.5)

with z ..= x − iη ∈ C− , where C− = {z ∈ C : Im(z) < 0}. We define accordingly C+ = {z ∈ C :
Im(z) > 0}. This quantity displays several interesting properties, making it the relevant object to
manipulate. First, it is a continuous function of z and is easy to differentiate (compared to working
directly on the ESD), providing a well-defined tool for mathematical analysis. Furthermore, it
contains the complete information about the eigenvalues {νi } and the eigenvectors {wi } since it
can be rewritten as:
                                                    N
                                                   X   wi w∗i
                                        GM (z) =              .                                  (2.6)
                                                   i=1
                                                       z − νi

It is easy to see that the number of singularities of the resolvent is equal to the number of eigenvalues
of M. Suppose that z → νi for any i ∈ [[N ]], then the residue of the pole defines a projection operator
onto the eigenspace associated to the eigenvalues νi . We will show in chapter 4 how this property
can be used to study the statistics of the eigenvectors.
     While the statistics of the eigenvectors is an interesting and non-trivial subject in itself, we
focus for now on the statistics of the eigenvalues through the ESD (2.4). For this aim, we define
the normalized trace of Eq. (2.5) as

                                                       1
                                           gN
                                            M (z) :=     Tr [GM (z)] ,                                           (2.7)
                                                       N
We shall skip the index M as soon as there is no confusion about the matrix we are dealing with.
In the limit of large dimension, one has

                                                             ρ(u)
                                                           Z
                             gN (z) ∼ g(z),       g(z) ..=        du.                      (2.8)
                                    N →∞                     z−u

  7 Note that in the mathematical and statistical literature, the resolvent differs from ours by a minus sign.




                                                        15
which is known as the Stieltjes (or Cauchy) transform of ρ. The Stieltjes transform has a lot of
appealing properties. For instance, if the density function ρ does not contain Dirac masses, then
this is the unique solution of the so-called Riemann-Hilbert problem, i.e :
  (i) g(z) is analytic in C+ except on its branch cut on the real axis inside supp[ρM ];
 (ii) lim|z|→∞ zg(z) = 1;
(iii) g(z) is real for z ∈ R\ supp[ρM ];
(iv) When near the branch cut, two different values for g(z) are possible, depending on whether
      the cut is approached from above or from below, i.e.:

                     lim g(x ± iη) = h(x) ∓ iπρ(x),             x ∈ supp[ρ] and ρ(x) ∈ R+ ,     (2.9)
                    η→0+

     where the function h denotes the Hilbert transform of ρ defined by
                                                        ρ(u)
                                               Z
                                      h(x) ..= −              du                              (2.10)
                                                supp[ρ] x − u
          R
     with − denoting Cauchy’s principal value.
It is now immediate to see that if one knows g(z) in the complex plane, the density ρ can be
retrieved by inverting the last property of the Riemann-Hilbert problem:
                                    1
                           ρ(x) ≡      lim Im(g(x − iη)),           x ∈ supp[ρ].              (2.11)
                                    π η→0+

The continuous limit of g(z) in the large N limit thus allows to investigate the distribution of the
eigenvalues that lie in the bulk component.
    Another interesting property is to study the asymptotic expansion of g(z) when z is large (and
outside of Supp[ρ]). Expanding g(z) in powers of z −1 yields:
                                                          ∞  k
                                           1                 u
                                               Z          X
                                    g(z) =         ρ(u)              du.
                                       z→∞ z                    z
                                                          k=0

To leading order, we get, in agreement with property (ii) above:
                                            1              1
                                              Z
                                     g(z) ∼     ρ(u)du ≡ ,
                                            z              z
where the last equality comes from the fact that the ESD is normalized to unity. The other terms
of the expansion are also of particular interest. Indeed, we see that
                                              ∞                      ∞
                                   1   1 X TrMk    1 X ϕ(Mk )
                           g(z) =    +           ≡   +        ,                               (2.12)
                               z→∞ z   N   z k+1   z    z k+1
                                             k=1                    k=1

where we defined the k-th moment of the ESD by ϕ(Mk ) := N −1 TrMk . We see that the Stieltjes
transform is related to the moment generating function of the random matrix M. This is another
illustration of the fact that the Stieltjes transform contains the complete information about the
eigenvalues density. Inversely, if one can measure the moments of the eigenvalues distribution, it is
possible reconstruct a parametric eigenvalues density function that matches the empirical data. This

                                                   16
nice property is an important feature of the Stieltjes transform for statistical inference purposes.
Note that we will sometimes abbreviate ϕ(Mk ) ≡ ϕk when there is no confusion about the matrix
we are studying.
    Last but not least, it is easy to check the following scaling property
                                                     1    z 
                                         gaM (z) =     gM      ,                              (2.13)
                                                     a     a
for any a ∈ R\{0}. Moreover, suppose that M is invertible, then using (2.7) we also have
                                                      !
                                           1        1
                                  zgM (z) + gM−1         = 1,                                 (2.14)
                                           z        z

so that we are able to compute the Stieltjes transform of M−1 given the Stieltjes transform of M.
Blue function and R-transform. There are many other useful RMT transforms, some that will turn
out to be important in the next chapter. We begin with the free cumulant generating function
which is known as the R-transform in the literature [62, 54, 63]. To define this quantity, it is
convenient to introduce the functional inverse of the Stieltjes transform, also known as the Blue
transform [64]
                                          B(g(z)) = z,                                      (2.15)
and the R-transform is simply defined by
                                                            1
                                          R(ω) = B(ω) −       .                               (2.16)
                                                            ω
Note that one may deduce from (2.13) the following property

                                         RaM (ω) = aRM (aω),                                  (2.17)

for any a ∈ R. One very nice property is that the R-transform admits a Taylor expansion in the
limit ω → 0. Indeed, by plugging ω = g(z) into Eq. (2.16), we obtain the formula
                                                      1
                                         R(g(z)) +        = z.                                (2.18)
                                                     g(z)

Then, one can find after expanding the Stieltjes transform in powers of z −1 that R(ω) can be
expanded as
                                           X∞
                                   R(ω) =       κ` (M)ω `−1                             (2.19)
                                               `=1

where the sequence {κ` }`≥0 denotes the free cumulant of order ` which are expressed as a function
of the moments of the matrix. For completeness, we give the first four free cumulants:

                           κ1   =   ϕ1
                           κ2   =   ϕ2 − ϕ21
                           κ3   =   ϕ3 − 3ϕ2 ϕ1 + 2ϕ31
                           κ4   =   ϕ4 − 4ϕ3 ϕ1 − 2ϕ22 + 10ϕ2 ϕ21 − 5ϕ41 .                    (2.20)


                                                 17
Note that the first three cumulants are equivalent to the ‘standard’ cumulants of ordinary random
variables and only differ from ` ⩾ 4. Note for example that when ϕ1 = 0, one finds κ4 = ϕ4 − 2ϕ22 ,
whereas the standard kurtosis would read ϕ4 − 3ϕ22 . It will turn out that the free cumulants of the
sum of independent – in a sense specified below – random matrices are given by the sum of the
cumulants of these random matrices, i.e. κ` (M) = κ` (A) + κ` (B), see section 2.3 below.
Moment generating function and S-transform. The moment generating function of the LSD ρ is
obtained by considering
                                                       duρ(u)u
                                                    Z
                                     .
                               T (z) .= zg(z) − 1 =            ,                       (2.21)
                                                        z−u
frequently known as the T (or sometimes η [54]) transform [39]. Indeed, by taking z → ∞, one
readily finds
                                                ∞
                                                X ϕ(Mk )
                                       TM (z) =          .                             (2.22)
                                                    zk
                                                       k=1
We can then introduce the so-called S-transform as [62]:
                                                          ω+1
                                             S(ω) ..=                                                       (2.23)
                                                         ωT −1 (ω)
where T −1 (ω) is the functional inverse of the T -transform. Using the series expansion of TM (z)
in powers of z −1 and Eq. (2.20), one finds that the S-transform also admits a Taylor series which
reads:
                                 1   ω              ω2
                SM (ω)     =       + 3 (ϕ21 − ϕ2 ) + 5 (2ϕ22 − ϕ2 ϕ21 − ϕ3 ϕ1 ) + O(ω 3 )
                                ϕ1  ϕ1              ϕ1
                                              2
                                1   κ2      2κ − κ1 κ3 2
                           =       − 3ω + 2 5          ω + O(ω 3 ).                                         (2.24)
                                κ1  κ1          κ1
From this last equation, it is not hard to see that the S-transform of a matrix M which has a zero
trace is ill-defined. Hence, the S-transform of a Wigner matrix does not make sense, but it will be
very useful when manipulating positive definite covariance matrices (see Section 2.3.3)
   Note finally that there exists a relation between the R-transform and the S-transform
                                            1                            1
                               R(ω) =             ,          S(ω) =                                         (2.25)
                                         S(ωR(ω))                     R(ωS(ω))
which allows one to deduce R(z) from S(z) and vice versa. Other properties on the R and S
transforms can be found e.g. in [65].
      Let us show the second equality of (2.25) for the sake of completeness. The derivation of the first
      identity is similar and we omit details. Using (2.16) and (2.23), one obtains
                                                                !
                                                        ω+1         T −1 (ω)
                                     R(ωS(ω)) = B        −1
                                                                  −          .                    (2.26)
                                                       T    (ω)      ω+1
      Next, by setting z = T −1 (ω), we can rewrite (2.21) as
                                              ω+1
                                                      = g T −1 (ω) .
                                                                   
                                                                                                   (2.27)
                                             T −1 (ω)
      Hence, we conclude that
                                                             1            ω
                              R(ωS(ω)) = T −1 (ω) −                =            .                (2.28)
                                                        g T −1 (ω)    g T −1 (ω)
      The conclusion then follows from (2.27).


                                                        18
2.2. Coulomb gas analogy. There exists several techniques to compute the limiting value of the
Stieltjes transform: (i) Coulomb gas methods, (ii) method of moments, (iii) Feynman diagrammatic
expansion, (iv) Dyson’s Brownian motion, (v) Replicas, (vi) Free probability, (vii) recursion for-
mulas, (viii) supersymmetry... We devote the rest of this section to provide the reader with a brief
introduction to (i), (v) and (vi). Dyson’s Brownian motion (iv) and the recursion method (vii) are
mentioned in appendices C and D.1.2. We refer to [52] for the moment methods (ii), to [41, 66]
for Feynman diagrams (iii) or to [67] and references therein for summetry applied to RMT. Again,
we emphasize that this presentation is not intended to be rigorous in a mathematical sense, and we
refer to standard RMT textbooks such as [49, 52, 53, 56] for more details.
    We begin with the Coulomb gas analogy that, loosely speaking, consists in considering the
eigenvalues of M as the positions of fictitious charged particles, repelling each other via a 2-d
Coulomb (logarithmic) potential (see [68] for a self-contained introduction or to e.g. [41, 50, 69]
for concrete applications). We shall highlight in this section the strong link between the potential
function and the Stieltjes transform g(z) whenever the probability measure over the matrix ensemble
is rotationally invariant, i.e. of the form Eq. (2.1).
2.2.1. Stieltjes transform and potential function. First, we write from (2.1) the partition function
of the model as                            Z
                                                      βN
                                          Z∝     e− 2 TrV (M) DM,

and this can be used as a starting point to obtain the LSD – or rather its Stieltjes transform –
using a saddle point method. This relation has first been obtained in the seminal paper of Brézin-
Itzykson-Parisi-Zuber [41] and we repeat here the main idea of the derivation (see also [70, Section
2.1]). Let us first express the partition function in terms of the eigenvalues and eigenvectors of M,
using (2.2):                                                                    
                             N                  N
                                                              β
                        Z Y                 X                 X                 
                   Z∝          dνi exp −N         V (νi ) −         log|νi − νj | ,
                                i=1
                                        
                                                i=1
                                                             2N                    
                                                                     i6=j

up to a constant factor that comes from integrating over the Haar measure dΩ. It is then customary
to introduce the action S({νi }) ≡ S(ν1 , ν2 , . . . , νN ) such that we can rewrite the partition function
as:
             N                                                N
                                                           1 X              β X
           Z Y
                            2
      Z∝            dνi e−N S({νi })   with S({νi }) =           V (νi ) −      log|νi − νj |,      (2.29)
              i=1
                                                           N i=1           2N 2
                                                                              i6=j

Note that the action is normalized so that its large N limit is of order 1. The eigenvalues can be
seen as a thermal gas of one-dimensional particles in an external potential V (z) and subject to a
(logarithmic) “electrostatic” repulsive interaction: this is the Coulomb gas analogy. At thermal
equilibrium, the eigenvalues typically gather in potential well(s), but cannot accumulate near the
minimum due to the repulsive force, which keeps them at distance of order O(N −1 ). For instance,
if we take a quadratic potential function V (x) = x2 /2, then all the particles tend to gather around
zero as it is shown in the Fig. 2.1. We recall that we consider only densities which are defined on
an unique compact support (one-cut assumption) and we thus require that the fictitious particles
evolve in a confining convex potential V (z). The class of potential
                                                               P function that we consider is such
that its derivative gives a Laurent polynomial, i.e., V 0 (z) = k ck z k with k integers that can be
negative. Since we can always rewrite V 0 (z) = z −` P (z), with the “order” ` the lowest (negative)

                                                      19
power of V 0 (z) and P (z) a polynomial, we define by d the “degree” of V 0 (z) which corresponds to
the degree of P (z). In particular, if V 0 (z) is a polynomial, then ` = 0.


                             5




                             4



                             3
                      V(x)




                             2



                             1



                             0
                                      -2                            0                     2
                                                                    x



Figure 2.1. Typical configuration of a repulsive Coulomb gas with N = 20 particles (red dots) in the
potential V (x) = x2 /2 as a function of x.



   In the large N limit, the integral over eigenvalues can be computed by the saddle-point method
which yields the following “force equilibrium” condition:8
                                                    N
                                               β    X            1
                                 V 0 (νi ) =                          ,   ∀ i = 1, . . . , N.               (2.30)
                                               N              νi − νj
                                                   j=1;j6=i


It seems hopeless to find the eigenvalues {λi } that solve these N equations. However, we may
expect to find the LSD ρM in the limit N → ∞, corresponding to configuration of the eigenvalues
that satisfies these saddle-point equations. In the case of the one-cut assumption, the result reads
[41]:
                                                  p          p
                             g(z) = V 0 (z) − Q(z) (z − ν+ ) (z − ν− ),                       (2.31)
where ν− < ν+ denote the edges of supp[ρ] and Q(z) is also a Laurent polynomial with degree d − 1
and order `. Therefore, we see that we have d + 1 unknowns to determine, namely the coefficients of
Q(z), ν− and ν+ which are determined using the series expansion (2.12). We shall give a detailed


    8 The reader might wonder why a system in thermal equilibrium ends up being described by simple mechanical

equilibrium, as at zero temperature. It turns out that the system is effectively at very low temperatures and that
entropy effects are of order N −1 compared to interaction effects, see e.g. [69] for a detailed discussion. Entropy
effects start playing a role for extended β ensembles where β = c/N where c is finite, see [71].


                                                               20
illustration of this procedure in Section 2.2.3 below9 .
    We observe that as soon as we can characterize the potential function of V (z) that governs the
entries of M, we are then able to find the corresponding LSD ρM . We will show in the rest of this
section that this Coulomb gas analogy allows one to retrieve some important laws in RMT.


   Let us show how to obtain (2.31). In the following we set β = 1. First, we introduce the normailzed trace of
   the resolvent g(z) in (2.30) by multiplying on both sides by N −1 (z − νi )−1 and summing over all i, which
   yields
                                    N                 N    N
                                 1 X V 0 (νi )    1 X X                  1
                                               = 2                                  .                    (2.32)
                                 N i=1 z − νi    N i=1 j=1;j6=i (z − νi )(νi − νj )

   Notice that this last equation is indeed an analytical function for z ∈ C\Supp[ρM ]. Then, we rewrite the LHS
   using some algebraic manipulations that leads to
                                   N                             N
                                1 X V 0 (νi )                 1 X V 0 (z) − V 0 (νi )
                                              = V 0 (z)g(z) −                         ,
                                N i=1 z − νi                  N i=1     z − νi

   and for the RHS, we obtain
                                   N    N                                             
                               1 X X                    1            1 2        1 0
                                                                   ≡    g (z) +   g (z)  .
                              N 2 i=1 j=1;j6=i (z − νi )(νi − νj )   2          N

   Regrouping these last two equations into the saddle-point equation (2.32) gives
                                                                   N
                                                                1 X V 0 (z) − V 0 (νi )
                                              
                             1 2        1
                                 g (z) + g0 (z) = V 0 (z)g(z) −                         .
                             2          N                       N i=1     z − νi

   Since we are interested in the limit of large N , we thus have to solve for g(z) the following quadratic equation
                                                                 N
                                                            2 X V 0 (z) − V 0 (νi )
                                  g2 (z) − 2V 0 (z)g(z) +                           = 0.                     (2.33)
                                                            N i=1     z − νi

   The most difficult term is the last one because the sum is not explicit. For the sake of simplicity, we consider
   the case where V 0 (z) is a polynomial of degree d > 0 as the extension to Laurent polynomial, i.e. polynomial
   with negative powers, is immediate. For V 0 (z) a polynomial function in z, we have that
                                                            N
                                                       1 X V 0 (z) − V 0 (νi )
                                           P (z) ..=
                                                       N i=1     z − νi

   is also a polynomial but with a degree d − 1 whose coefficients can be determined later by the normalization
   constraint, or by matching some moments. Then, the solution of Eq. (2.33) is such that:
                                                        q
                                        g(z) = V 0 (z) ± V 0 (z)2 − 2P (z).

   The nice property in the one-cut framework (i.e., a unique compact support for ρ) is that the above expression
   can be simplified to (when d ⩾ 1):

                                      g(z) = V 0 (z) ± Q(z) (z − ν+ )(z − ν− )
                                                           p

   where ν− and ν+ denote the edges of supp[ρ] and Q(z) is a polynomial with degree d − 1 and this gives (2.31).



 9 In the case of positive definite covariance matrices, we can use the series (3.23) that corresponds to the limit

z→0


                                                                21
2.2.2. Wigner’s semicircle law. As a warm-up exercise, we begin with Wigner’s semi-circle law [42],
one of the most important result in RMT. Note that this result has first been obtained in the
case of Gaussian matrix with independent and identically distributed entries (while preserving the
symmetry of the matrix). For real entries, we refer to this class of random matrices as the Gaussian
Orthogonal Ensemble (GOE). It has been proved, see e.g. [52], that the semi-circle law can be
extended to a broader class of random matrices, known as the Wigner Ensemble that deals with a
matrix M with independent and identically distributed entries such that:10

                               E Mij = 0, and E M2ij = σ 2 /N.
                                                         
                                                                                              (2.34)

Let us consider here the specific case of a GOE matrix. For Gaussian entries, it is not hard to see
that the associated probability measure Pβ (M) is indeed of the Boltzmann type with a potential
function V (M) = M2 /2σ 2 . From Eq. (2.31), we remark that the unknown polynomial Q(z) is
simply a constant because the derivative of the potential has degree d = 1. To determine this
constant, we enforce the property (ii) of the Riemann-Hilbert problem which enable us to get by
identification: Q(z) = 1, ν± = ±2σ. We thus finally obtain:
                                                 √         √
                                             z − z + 2σ z − 2σ
                                    gW (z) =                      ,                           (2.35)
                                                      2σ 2
       √
where · denotes throughout the following the principal square root, that is the non-negative square
root of a non-negative real number. Equation (2.35) is indeed the Stieltjes transform of Wigner’s
semi-circle law. Note that it is frequent to see the above result written as
                                                    √
                                                z ± z 2 − 4σ 2
                                       gW (z) =                ,
                                                      2σ 2
where the convention “±” refers to the fact that we have to chose the correct sign such that
g(z) ∼ z −1 for large |z| (property (ii) of the Riemann-Hilbert problem). The density function is
then retrieved using the inversion formula (2.11) that yields the celebrated Wigner’s semicircle law :
                                              1 p 2
                                 ρW (x) =         4σ − x2 ,           |x| < 2σ.                            (2.36)
                                            2πσ 2
We plot in Fig 2.2 the density of the semi-circle and compared with the ESD obtained from a
GOE matrix of size N = 500. As stated at the beginning of this section, we see that the limiting
density agrees well with the ESD of the large but finite size matrix. In fact, one can rigorously
estimate the expected difference between the ESD at finite N and the asymptotic LSD for N = ∞,
which vanishes as N −1/4 as soon as the Mij ’s have a finite fourth moment, and as N −2/5 if all the
moments of the Mij are finite (see [75]).
    Due to the relative simplicity of the expression of Eq. (2.35), one can easily invert this expression
to find the Blue transform to find that the R-transform of the semicircle law reads

                                                RW (z) = σ 2 z.                                            (2.37)

Since the average trace ϕ1 is exactly 0, the S-transform of a Wigner matrix is an ill-defined object.

  10 The case where the variance of the matrix elements diverge corresponds to Lévy matrices, introduced in [72].

For a rigorous approach, we refer the readers to [73]. For recent developments, see [74] .


                                                       22
                 0.5

                                                                                        Wigner

                 0.4



                 0.3
          ρ(λ)




                 0.2




                 0.1




                  0
                   -2                   -1                      0                   1                   2
                                                                λ


Figure 2.2. Wigner semi-circle density (2.36) compared with empirical results with N = 500 (histogram)
from one sample, illustrating the convergence of the ESD at finite N to the asymptotic LSD.



2.2.3. The Marčenko-Pastur law. As stated in the introduction, the study of random matrices
began with John Wishart [8]. More precisely, let us consider the N × T matrix Y consisting of T
independent realizations of random centered Gaussian vectors of size N and covariance C, then the
Wishart matrix is defined as the N × N matrix M as M ..= T −1 YY∗ . In multivariate statistics,
this matrix M is better known as the sample covariance matrix (see Chapter 3). For any N and
T > N , Wishart derived the exact PDF of the entries M which reads:
                                                                     T −N −1
                                              1       det(M) 2       T    −1
                           Pw (M|C) = N T /2                      e− 2 TrC M .                              (2.38)
                                     2       ΓN (T /2) det(C)T /2

As alluded in the introduction, we say that M (given C) follows a Wishart(N, T, C/T ) distribution.
In the “isotropic” case, i.e., when C = IN , we can deduce from (2.38)
                                               T −N −1     T           T         T −N −1
                        Pw (M|IN ) ∝ det(M)       2      e− 2 TrM := e− 2 TrM+      2    Tr log M
                                                                                                    ,       (2.39)

which clearly belongs to the class of Boltzmann ensembles (2.1). Throughout the following, we shall
denote by W the N × N matrix whose distribution is given by (2.39). Ignoring sub-leading terms,
the corresponding potential function is given by:

                                     1
                           V (z) =      [z − (1 − q) log z] ,       with       q := N/T.                    (2.40)
                                     2q

                                                           23
It is easy to see that the derivative indeed gives a Laurent polynomial in z as we have
                                                      1
                                         V 0 (z) =       [z − (1 − q)] .
                                                     2qz
Following our convention, V 0 (z) is a Laurent polynomial of degree 1 and order ` = −1 so that
we deduce Q(z) in (2.32) is of the form c/z with c a constant to be determined using (2.12). We
postpone the computation of the Stieltjes transform g(z) to the end of this section. The final result
reads:                                  √       √
                        (z + q − 1) − z − ν− z − ν+                         √
                 g(z) =                                 ,     ν± ..= (1 ± q)2 ,                (2.41)
                                        2qz
and this is the solution found by Marčenko and Pastur in [17] in the special case C = IN . We
can now use the inversion formula (2.11) to find the celebrated Marčenko-Pastur (MP) law (for
q ∈ (0, 1))                       p
                                    4νq − (ν + q − 1)2                 
                        ρMP (ν) =                      ,   ∀ ν ∈ ν− , ν+ .               (2.42)
                                         2qπν
Note that for q ⩾ 1, it is plain to see that M has N − T zero eigenvalues that contribute (1 − q)δ0
to the density Eq. (2.42). Note that the convergence of the ESD towards the asymptotic MP law
occurs, for q < 1, at the same speed as in the Wigner case, i.e. as N −2/5 in the present case where
the random elements of Y are Gaussian (for a full discussion of this issue, see [76]).
    Again, the expression of g(z) is simple enough to obtain a closed formula for the Blue transform,
and deduce from Eq. (2.41) the R-transform of the MP law:
                                                                1
                                              RMP (ω) =             .                                           (2.43)
                                                             1 − qω
One can compute the S-transform of the MP law using the relation (2.25):
                                                                1
                                              SMP (ω) =             .                                           (2.44)
                                                             1 + qω
      We now derive the Stieltjes transform (2.41) through a complete application of the BIPZ formalism
      introduced in Eq. (2.32). As alluded to above, the Stieltjes transform (2.32) for the isotropic Wishart
      matrix has the form                   "          #
                                         1       1−q        cp         p
                                 g(z) =       1−         −      z − ν+ z − ν− ,                        (2.45)
                                         2q        z        z
      and the constants that we have to determine are c, ν+ and ν− . To that end, we use (2.12) that tells
      us that when |z| → ∞
                                                1    ϕ(M)
                                         g(z) = +          + O(z −3 ).                             (2.46)
                                                z      z2
      On the other hand, one finds by taking the limit z → ∞ into (2.45) that
                             "          #    "                            #
                           1       1−q             ν+ + ν−    (ν+ − ν− )2
                   g(z) =     1−          −c 1−             −               + O(z −3 ),            (2.47)
                          2q        z                 2z          8z 2
      Then, by comparing this last equation to (2.46), we may fix c by noticing that we have a leading
      order
                                                     1
                                                        − c = 0,
                                                     2q
      since g(z) behave as O(z −1 ) for very large z and therefore we have
                                                           1
                                                      c=      .                                        (2.48)
                                                           2q


                                                        24
      Next, we find at order O(z −1 ):
                                                  (1 − q)   ν+ + ν−
                                            1=−           +         ,                        (2.49)
                                                     2q        4q
      that is to say
                                               ν+ = 2(1 + q) − ν− .                          (2.50)
      Finally, the last constant is determined with the condition at order O(z −2 ),
                                                       (ν+ − ν− )2
                                              ϕ(M) =               ,                         (2.51)
                                                           16q
      which is equivalent to
                                           p                   √        √
                                ν− = ν+ − 4 qϕ(M) = (1 + q) − 2 q = (1 − q)2 ,               (2.52)
      where we used (2.50) and ϕ(M) = 1 in the third step. Consequently, we deduce from (2.50) that
               √
      ν+ = (1 + q)2 and the result (2.41) follows from the equations (2.48), (2.50) and (2.52).


2.2.4. Inverse Wishart matrix. Another very interesting case is the inverse of a Wishart matrix,
simply named the “inverse Wishart” matrix. The derivation of the corresponding eigenvalue density
is straightforward from the Marčenko-Pastur law (2.42). Indeed, one just needs to make the change
of variable u = ((1 − q)ν)−1 into Eq. (2.42) to obtain:11
                                κ p                                    1       √
                                                                u± ..=
                                                                                       
               ρIMP (u) =           (u+ − u)(u − u− ),                   κ + 1 ± 2κ + 1 ,             (2.53)
                               πu2                                     κ
where the subscript IMP stands for “Inverse Marčenko-Pastur” and κ is related to q through
                                                    1
                                             q=          ∈ (0, 1) .                                   (2.54)
                                                  2κ + 1
In particular, one notices that u± = (1 − q)/ν∓ where ν∓ is defined in Eq. (2.41). We plot in Fig.
2.3 the density of the Marčenko-Pastur (2.42) and of its inverse (2.53) both with parameter q = 0.5.
    In addition to the eigenvalue density (2.53), one can also derive explicit expressions for the
other transforms presented in Section 2.1.2. For the Stieltjes transform, it suffices to apply the
same change of variable u = ((1 − q)z)−1 and to use the properties (2.13) and (2.14) to obtain:
                                                      √         √
                                      u(κ + 1) − κ − κ u − u− u − u+
                            giw (u) =                                     ,                    (2.55)
                                                      u2
where the bounds u± are given in Eq. (2.53). One can easily check with the inversion formula (2.9)
that we indeed retrieve the density of states (2.53) as expected.
   Using the Stieltjes transform (2.55), one can then compute the R-transform of the Inverse
Marčenko-Pastur density to find
                                               p
                                          κ − κ(κ − 2ω)
                             RIMP (ω) =                    ,    κ > 0,                      (2.56)
                                                  ω
and then, from (2.25), the S-transform reads
                                                                ω
                                              SIMP (ω) = 1 −       .                                  (2.57)
                                                                2κ

 11 The factor (1 − q)−1 is introduced to keep the mean at one as will be explained below.




                                                        25
                                                                                      MP
                 1.5                                                                  IMP




                  1
          ρ(λ)




                 0.5




                  0
                       0            1            2                 3          4             5       6
                                                                   λ


Figure 2.3. The red dotted curve corresponds to the Marčenko-Pastur density (2.42) with q = 0.5. We
repeat the experiment with the Inverse Wishart matrix still with q = 0.5 (plain blue curve).



   In statistics, the derivation of the inverse Wishart distribution is slightly different. Let M be
a N × N real symmetric matrix that we assume to be invertible and suppose that M−1 follows
a Wishart(N, T, C−1 ) and C is a N × N real symmetric positive definite “reference” matrix and
T > N − 1. In that case, it turns out that the PDF of M is also explicit. More precisely, we say
that M is distributed according to an Inverse-Wishart(N, T, C) whose PDF is given by [9]:

                                                     1               det(C)T /2         1      −1
                           Piw (M−1 |C) =                                            e− 2 Tr CM .       (2.58)
                                            2N T /2 Γ   N (T /2) det(M) (T +N +1)/2)



In order to get that distribution, one should note that the Jacobian of the transformation M → M−1
is equal to (det M)−N −1 , as can be derived by using the eigenvalue/eigenvector representation of
the measure, see Eq. (2.2). A detailed derivation of this change of variable may be found e.g. in
[77, Eq. (15.15)].
    An important property of the Inverse-Wishart distribution is the following closed formula for
the expectation value:
                                                                  C
                                                 M Piw =               .                                (2.59)
                                                               T −N −1

The derivation of this result can be obtained using the different identities of [78].
   We may now explain the factor (1−q) in the above change of variable. If we consider C = IN /T ,


                                                              26
we deduce from (2.59) that

                                             T            1
                                M Piw =           IN ∼        IN .                             (2.60)
                                          T −N −1   LDL 1 − q


In order to have a normalized spectral density, i.e. N −1 TrM = 1, we see that we need to apply
M̃ = (1 − q)M so that hM̃i = IN . This was exactly the purpose of the change of variable u =
((1 − q)ν)−1 in Eq. (2.53).
    We conclude this section by stating that one can characterize entirely the eigenvalue density
function of a broad class of random matrices M through a potential function. This allows one to
reproduce a large variety of empirical spectral densities by adequately choosing the convex confining
potential.

2.3. Free probability. We saw in the previous two examples that one can derive, from the poten-
tial function, some analytical results about the ESD which can be very interesting for statistical
purposes (e.g. the inverse Wishart density). However, the Coulomb gas method does not allow one
to investigate the spectrum of a matrix that is perturbed by some noise source. This is a classical
problem in Statistics where one is often interested in extracting the “true” signal from noisy obser-
vations. Standard models in statistics deal with either an additive or multiplicative noise (as will
be the case for empirical correlation matrices). Unless one can write down exactly the PDF of the
entries of the corrupted matrix, which is rarely the case, the Coulomb gas analogy is not directly
useful.
    This section is dedicated to a short introduction to free probability theory, which is an alterna-
tive method to study the asymptotic behavior of some large dimensional random matrices. More
precisely, free probability provides a robust way to investigate the LSD of either sums or products
of random matrices with specific symmetry properties. We will only give here the basic notions of
free probability applied to symmetric real random matrices and we refer to e.g. [63] or [65] for a
more exhaustive presentation.
2.3.1. Freeness. Free probability theory was initiated in 1985 by Dan Voiculescu in order to under-
stand special classes of von Neumann algebras [43], by establishing calculus rules for non commu-
tative operators relying on the notion of freeness, defined below for the special case of matrices. A
few years later, Voiculescu [62] and Speicher [79] found that rotationally invariant random matrices
asymptotically satisfy the freeness criteria, and this has had a tremendous impact on RMT.
    Roughly speaking, two matrices A and B are mutually free if their eigenbasis are related to
one another by a random rotation, i.e. when their eigenvectors are almost surely orthogonal. For
random matrices, we rather use the notion of “asymptotic” freeness. The precise statement is as
follows [62]: let A and B be two independent self-adjoint matrices of size N . If the spectral density
of each matrix converges almost surely in the large N limit and if B is invariant under rotation,
then A and B are asymptotically free. This statement can also be found in a different context in
[79].
    The notion of freeness for random matrices is the counterpart of independence for random
variables. Indeed, recall that the normalized trace operator, defined as

                                                    1
                                          ϕ(M) :=     TrM,                                     (2.61)
                                                    N
is equal to the first moment of ρM . Then, provided that ϕ(A) = ϕ(B) = 0, we say that A and B


                                                 27
are free if the so-called freeness property is satisfied, to wit:

   ϕ (An1 Bm1 An2 Bm2 . . . Ank Bmk ) = ϕ(An1 )ϕ(Bm1 )ϕ(An2 )ϕ(Bm2 ) . . . ϕ(Ank )ϕ(Bmk ),       (2.62)

for any integers n1 , . . . , nk and m1 , . . . , mk with k ∈ N+ . Note that if ϕ(A) 6= 0 and ϕ(B) 6= 0,
then it suffices to consider the centered matrices A − ϕ(A)IN and B − ϕ(B)IN .
    Let us explore (2.62) in the simplest case. For any free matrices A and B defined as above, one
has
                                      ϕ ((A − ϕ(A))(B − ϕ(B))) = 0,                              (2.63)
from which we deduce ϕ (AB) = ϕ(A)ϕ(B). Hence, if one thinks of the trace operator (2.61) as the
analogue of the expectation value for non commutative random variables, the freeness property is
the analogue of the moment factorization property. More generally, freeness allows the computation
of mixed moments of products of matrices from the knowledge of the moments of A and B, similar
to classical independence in probability theory. For example, from

                             ϕ ((A − ϕ(A))(B − ϕ(B))(A − ϕ(A))) = 0,                             (2.64)

we can deduce that
                                 ϕ (ABA) = ϕ(A2 B) = ϕ(A2 )ϕ(B).                                 (2.65)
    One typical example of free pairs of matrices is when A is a fixed matrix and when B is a
random matrix belonging to a rotationally invariant ensemble, i.e. B = ΩBdiag Ω∗ , where Bdiag
is diagonal and Ω distributed according to the Haar (flat) measure over the orthogonal group, in
the limit where N is infinitely large. This concept of asymptotic freeness is also related to the
notion of vanishing non-planar diagrams [80]. As we shall see in Chapter 7, the computation of
mixed moments will be used to derive some useful relations for estimating over-fitting for statistical
estimation problems.
2.3.2. Sums of free matrices. In addition to the computation of mixed moments such as Eq. (2.64),
free probability theory allows us to compute the LSD of sums and products of invariant random
matrices, as we discuss now.
    Let us look at the additive case first. Suppose that we observe a matrix M which is built from
the addition of a fixed “signal” matrix A and a noisy (or random) matrix B that we assume to be
invariant under rotation, i.e.,
                                           M = A + ΩBΩ∗ ,
for any N ×N matrix Ω that belongs to the orthogonal group O(N ). A typical question is to evaluate
the LSD of M and estimate the effect of the noise on the signal in terms of the modification of
its eigenvalues. Assuming that the ESD of A and B converge to a well defined limit, the spectral
density of M can be computed using the law of addition for non commutative operators, namely
Voiculescu’s free addition
                                   RM (ω) = RA (ω) + RB (ω).                                 (2.66)
Hence, we can interpret the R-transform (2.16) as the analogue in RMT of the logarithm of the
Fourier transform for standard additive convolution. It is possible to rewrite Eq. (2.66) as a function
of the Stieltjes transform of M that contains all the information about the spectral density of M.
Equation (2.66) is equivalent to

                                       BM (ω) = BA (ω) + RB (ω).


                                                    28
Next, we introduce ω = gM (z) that yields

                                         BA (gM (z)) = z − RB (gM (z)).

It now suffices to apply the function gA on both sides to obtain

                                         gM (z) = gA (z − RB (gM (z))).                                       (2.67)

This last relation establishes the influence of the additive noise coming from the matrix B on the
“signal” (or true) eigenvalues of A.
    To gain more insight on this result, let us assume that the noise matrix B is a simple GOE matrix
with centered elements of variance σ 2 /N. We know from Eq. (2.37) that RB (z) = σB     2
                                                                                          z. Hence, the
spectrum of the sample matrix M is characterized by the following fixed-point equation:12
                                                            2
                                          gM (z) = gA (z − σB gM (z)).                                        (2.68)

This is the Stieltjes transform of the deformed GOE matrix13 which is a well-known model in
statistical physics of disordered systems. Indeed, this model can be seen as a Hamiltonian that
consists of a fixed source subject to an external additive perturbation B [82]. Taking A to be a
                                                          2     2
GOE as well, we find that M is a GOE with variance σA       + σB  , as expected. In a inference theory
context, this model might be useful to describe general linear model where the signal we try to infer
is corrupted by an additive noise.
    Another interesting application is when the matrix B has low rank, frequently named a factor
model. In the example of stocks market, this model can be translated into the fact that there exist
few common factors to all stocks such as global news about the economy for instance. For the
sake of simplicity, we consider the rank-1 case but the following argument can be easily generalized
to a finite rank r  N . Let us denote the unique nontrivial eigenvalue of B as β > 0 and ask
ourselves how adding a (randomly oriented) rank-1 matrix affects the spectrum of M. This problem
can be solved explicitly using free matrix tools in the LDL. Indeed, as we show below, the largest
eigenvalue pops out of the spectrum of A whenever there exists z ∈ R\ supp[ρA ] such that

                                                              1
                                                   gA (z) =     .                                             (2.69)
                                                              β

For instance, if A is a Wigner matrix with variance σ 2 > 0, one can easily check from (2.69) and
(2.37) that the largest eigenvalue ν1 of M is given by
                                         (
                                           β + σ 2 /β if β > σ
                                    ν1 =                                                    (2.70)
                                           2σ          otherwise .

When β > σ, we say that ν1 is an outlier, i.e. it lies outside the spectrum of ρA . Hence, we see
that free probability allows one to find a simple criterion for the possible presence of outliers.

  12 This equation can also be interpreted as the solution of a Burgers equation, that appears within the Dyson

Brownian motion interpretation of the same problem – see Appendix D for more about this.
  13 This result can be generalized to the class of deformed Wigner matrices, i.e. where the noise is given by (2.34)

but not necessarily Gaussian, see e.g. [81].


                                                         29
      Let us now derive the criterion (2.69). First we need to compute the R-transform of the rank one
      matrix B in order to use (2.66). From (2.8), we easily find that
                                                        !         "                #
                                     1   1            1 1       1      1     β
                           gB (u) =           + 1−           =      1+               .           (2.71)
                                    N u−β            N u        u      N 1 − u−1 β

      Using perturbation theory, we can invert this last equation to find the Blue transform, and this yields
      at leading order,
                                                1         β
                                     BB (ω) =     +              + O(N −2 ).                           (2.72)
                                               ω     N (1 − ωβ)
      We may therefore conclude from (2.16) that
                                                         β
                                         RB (ω) =              + O(N −2 ).                             (2.73)
                                                    N (1 − βω)
      Hence, we obtain by applying (2.66) and (2.16) that
                                                               β
                                    BM (ω) = BA (ω) +                + O(N −2 ).                       (2.74)
                                                          N (1 − βω)
      Next, we set ω = gM (z) so that this latter equation becomes
                                                               β
                                   z = BA (gM (z)) +                    + O(N −2 ).                    (2.75)
                                                        N (1 − βgM (z))
      From this equation, we expect the Stieltjes transform of ρM to be of the form
                                                             g1 (z)
                                        gM (z) = g0 (z) +           + O(N −2 ).                        (2.76)
                                                              N
      By plugging this ansatz into (2.75), we see that g0 (z) and g1 (z) satisfies
                                          z    =    BA (g0 (z))
                                                                  β
                                      g1 (z)   =    −    0 (g (z))(1 − g (z)β)
                                                                               .                       (2.77)
                                                        BA   0          0

      It is easy to find that g0 (z) = gA (z) as expected. We now focus on the 1/N correction term and
      using that BA0 (g (z)) = 1/g (z), we conclude that
                       A            A

                                                              βg0A (z)
                                               g1 (z) = −               .                              (2.78)
                                                            1 − gA (z)β
      Finally, we obtained that
                                                                 1 βg0A (z)
                                         gM (z) ≈ gA (z) −                     ,                       (2.79)
                                                                 N 1 − gA (z)β
      and we see that the correction term only survive in the large N limit if gA (z) = β −1 has a non trivial
      solution. Differently said, z is an eigenvalue of M and not of A if there exists z ∈ R\ supp[ρA ] such
      that gA (z) = β −1 and this leads to the criterion (2.69).


2.3.3. Products of free matrices. Similar results are available for free multiplicative convolution.
Before showing how to obtain the LSD of the product of free matrices, we first emphasize that one
has to carefully define the product of free matrices. Indeed, the naive analogue of the free addition
would be to define M = AB. However the product AB is in general not self-adjoint when A and
B are self-adjoint but not commuting. In the case where A is positive definite, we can see that the
product A1/2 BA1/2 makes sense and share the same moments than the product AB. Therefore,
we define the product of free matrices by
                                                √      √
                                           M := AB A.                                          (2.80)

                                                            30
Note that in this case, B need not be necessarily positive definite but must have a trace different
from zero (see the Taylor expansion below). For technical reason, we need the LSD of B to be
well-defined. Under this assumption, the free multiplicative convolution rule for random matrices
is given by
                                    SM (ω) = SA (ω)SB (ω).                                   (2.81)
This is the so-called free multiplication, which has been first obtained by Voiculescu [62] and then
by [83] in a physics formalism.
   Again, if one is interested in the limiting spectral density of M, one would like to write (2.81) in
terms of its Stieltjes transform. Using the very definition of the S-transform, we rewrite (2.81) as

                                            1       SB (ω)
                                                  = −1     .
                                         TM−1 (ω)  TA (ω)

The trick is the same as above so we therefore set ω = TM (z) to find

                                     TA−1 (TM (z)) = zSB (TM (z)).                              (2.82)

It is now immediate to get the analogue of (2.67) for the multiplicative case

                                     TM (z) = TA (zSB (TM (z))) ,                               (2.83)

that gives in terms of the Stieltjes transform

                     zgM (z) = Z(z)gA (Z(z)) ,         Z(z) ..= zSB (zgM (z) − 1).              (2.84)

This is certainly one the most important results of RMT for statistical inference. It allows one to
generalize the Marčenko-Pastur law for sample covariance matrices to arbitrary population covari-
ance matrices C (see next section), and obtain results on the eigenvectors as well. We emphasize
that the literature on free products can be adapted to non Hermitian matrices, see [65] or [84] for
a recent review on the multiplication of random matrices.

2.4. Replica analysis.
2.4.1. Resolvent and the Replica trick. As we noticed above (Eq. 2.6), information about the eigen-
vectors can be studied through the resolvent. However, both the Coulomb gas analogy and free
probability tools are blind to the structure of eigenvectors since these only give information about
the normalized trace of the resolvent. In order to study the resolvent matrix, we need to introduce
other tools, for example one borrowed from statistical physics named the Replica method. To make
it short, the Replica method allows one to rewrite the expectation value of a logarithm in terms of
moments, expressed as expectation values of many copies, named the replicas, of the initial system.
This method has been extremely successful in various contexts, including RMT and disordered sys-
tems, see e.g. [46, 45], or [47] for a more recent review. We stress that even if this method turns out
to be a very powerful heuristic, it is not rigorous mathematically speaking (see below). Therefore,
it is essential to verify the result obtain from the Replica method using other methods, for example
numerical simulations. Note that a rigorous but more difficult way to deal with resolvent is the
recursion technique that uses linear algebra results, as explained in Appendix C. Other available
techniques include Feynman diagrams [66, 85].


                                                  31
   As a warm-up exercise, we present briefly the approach for the Stieltjes transform and then
explain how to extend it to the study of full resolvent. We notice that any Stieltjes transform can
be expressed as
                           N                  N
                           X    1      ∂     Y            ∂
                   g(z) =            =    log (z − νi ) =    log det(zI − M).                   (2.85)
                          i=1
                              z − νi   ∂z    i=1
                                                          ∂z

Then, using the Gaussian representation of det(zI − M)−1/2 , we have that
                                              "       N
                                                                           # N       !
                                                  1 X                       Y dηj
                                        Z
                                 −1/2
           Z(z) ≡ (det(zI − M))       = exp −             ηi (zI − M)ij ηj      √     .         (2.86)
                                                  2 i,j=1                   j=1
                                                                                  2π

Plugging this last equation into (2.85) and assuming that the Stieltjes transform is self-averaging,
we see that we need to compute the average of the logarithm of Z(z):

                                                   ∂
                                       g(z) = −2      E log Z(z),                               (2.87)
                                                   ∂z
where the average is taken over the probability distribution PM . However, it would be easier to
compute the moments EZ n (z) instead of E log Z(z) and this is precisely the purpose of the Replica
trick which was initially formulated as the following identity
                                                     Zn − 1
                                        log Z = lim         ,                                   (2.88)
                                                 n→0   n
so that one formally has
                                                      ∂ EZ n − 1
                                      g(z) = lim                  .                              (2.89)
                                                n→0 ∂z       n
We have thus transformed the problem (2.87) into the computation of n replicas of the system
involved in Z n (z). The non-rigorous part of this method is quite obvious at this stage. While the
integer moments of Z can indeed be expressed as an average of the replicated system, the identity
(2.88) requires vanishingly small, real values of n. Typically, one works with integer n’s and then
perform an analytical continuation of the result to real values of n before taking the limit n → 0
(after, as it turns out, sending the size of the matrix N to infinity!). Therefore, the main concern
of this method is that we assume that the analytical continuation poses no problem, which is not
necessarily the case. It is precisely this last step that could lead to uncontrolled approximations in
some cases [86], which is why numerical (or other) checks are mandatory. Nonetheless, the Replica
trick gives a simple heuristic to compute the Stieltjes transform g(z) which, as shown below, is
exact for the quantities considered in this review.
    For our purposes, we need to extend the above Replica formalism for the entire resolvent and not
only its normalized trace. In that case, we will need a slightly different Replica identity, extending
(2.88), that we shall now present. The starting point is to rewrite the entries of the resolvent matrix
G(z) using the Gaussian integral representation of an inverse matrix
                                 R QN                  n     PN                        o
                                       k=1 dηk ηi ηj exp − 21 k,l=1 ηk (zδkl − Mkl )ηl
                (zIN − M)−1ij =    R QN              n     PN                         o .      (2.90)
                                                           1
                                         k=1 dηk exp − 2       k,l=1 ηk (zδkl − Mkl )ηl



                                                   32
As explained in Appendix C, we expect that (2.90) is self-averaging in the LDL thanks to the
Central Limit Theorem, so that:
                      * Z              !                                      +
                                N                       N
                         1      Y                    1 X                      
       (zIN − M)−1
                 ij =             dη k   ηi η j exp   −   η k (zδkl − M kl )ηl    ,   (2.91)
                        Z                            2                        
                                     k=1                        k,l=1                        PM

where Z is as above the partition function, i.e. the denominator in Eq. (2.90). The replica identity
for resolvent is given by
                         *                 !                                        +
                                Z Y  N                  1 X  N                      
        Gij (z) = lim Z n−1             dηk ηi ηj exp −           ηk (zδkl − Mkl )ηl
                     n→0                                2                           
                                    k=1                     k,l=1                         PM
                                        !        * n                                     +
                             N Y n                               N
                                                             1 X α
                          Z Y                     Y                                      
                 = lim              dηkα ηi1 ηj1      exp −           ηk (zδkl − Mkl )ηlα    . (2.92)
                     n→0                                  2                              
                                k=1 α=1               α=1               k,l=1                        PM

Again, we managed to rewrite the initial problem (2.91) as the computation of n replicas. We
emphasize that (2.92) is valid for any random matrix M, and is useful provided that we are able to
compute the average over the probability density PM . The identity (2.92) is the central tool of this
section. In particular, it allows one to study the asymptotic behavior of the resolvent entry-wise,
which contains more information about the spectral decomposition of M than just the normalized
trace [37]. As will become apparent below, we consider a model of random matrices inspired by
Free Probability theory, i.e. M = A + ΩBΩ∗ and M = A1/2 ΩBΩ∗ A1/2 (see Section 2.3 above for
a more details). We shall focus on the model of free multiplication since the arguments below may
be repeated almost verbatim for the free additive case (see Appendix D).
2.4.2. Matrix multiplication using replicas. We reconsider the model (2.80) and assume without loss
of generality that A is diagonal. In that case, we see that PM is simply the Haar measure over the
orthogonal group O(N ). We specialize the replica identity (2.92) to M = A1/2 ΩBΩ∗ A1/2 so that
we get
                 Z Y  N Y n
                                 !                               n
                                                                                          !
                               α    1 1 − z2
                                             Pn   PN
                                                       (η α 2
                                                            )
                                                                 X
                                                                     α  1/2
                                                                             α 1/2 ∗
   Gij (z) = lim             dηk ηi ηj e      α=1  k=1    k   I1    η A      η A       , B , (2.93)
            n→0
                      k=1 α=1                                           α=1

where                                          Z  h βN              i
                             Iβ (A0 , B) ..=  exp −      Tr A0 ΩBΩ∗ DΩ,                       (2.94)
                                                      2
is the so-called Harish-Chandra–Itzykson-Zuber integral [87, 88]. Explicit results for this integral
are known for Hermitian matrices (β = 2) for any integer dimension N , but not for real orthogonal
matrices. Even the study of (2.94) in the limit N → ∞ is highly non trivial (see Appendix A).
Nevertheless, in the case where A0 is of finite rank, the leading contribution for N → ∞ is known
for any symmetry group. Fortunately, we see that A0 in our case is of rank n and the result is
obtained from Eq. (A.5) in Appendix A:14
                   n
                                                        "    n            N
                                                                                    !#
                 X
                       α 1/2
                              α 1/2 ∗                  N X          1 X α 2
              I1      η A     η A       ,B       ∼ exp          WB           (η ) ai ,        (2.95)
                  α=1
                                               N →∞       2 α=1       N i=1 i


 14 Recall that we work with n as an integer throughout the intermediate steps of the computation.




                                                      33
with
                                                WB0 (.) = RB (.) ,                                            (2.96)
and where we assume that the vectors [η α ]nα=1 are orthogonal to each other, which is generically
true provided n  N . We then plug this result into (2.93) and introduce an auxiliary variable
        PN
pα = N1 i=1 (ηiα )2 ai that we enforce using the exponential representation of a Dirac delta function
                                N
                                                           "             N
                                                                                       #
                         1 X α 2                     1               1
                                                Z                     X            
                  δ pα −      (η ) ai =                 exp iζ α pα −      (η α )2 ai dζ α ,                  (2.97)
                         N i=1 i                     2π               N i=1 i

for each α = 1, . . . , n. This allows to retrieve a Gaussian integral on η α . Renaming ζ α = −2iζ α /N
yields the result
                                         n
                                                     !               "                #
                                                          δij           Nn
                                Z Z     Y
                                               α   α                            α α
                      Gij (z) ∝             dp dζ                 exp −    F0 (p , ζ )            (2.98)
                                        α=1
                                                       z − ζ 1 ai        2

where F0 is the free energy given by
                                        n
                                          "  N
                                                                             #
                           α   α     1X 1 X             α        α α       α
                       F0 (p , ζ ) =           log(z − ζ ak ) + ζ p − WB (p ) .                               (2.99)
                                     n α=1 N
                                                 k=1

Now, one sees that the integral over dpα dζ α involves the exponential of N n/2 times the free energy,
which is of order unity. Provided that n is non-zero, one can estimate this integral via a saddle
point method (but of course n will be sent to zero eventually...). We assume a replica symmetric
ansatz for the saddle point, i.e. pα = p∗ and ζ α = ζ ∗ , ∀α = 1, . . . , n. This is natural since F0
is invariant under the permutation group Pn . Note however that the replica symmetric ansatz
can lead to erroneous results and this phenomenon is known as replica symmetry breaking, see e.g.
[46, 86] or [89] and references therein for a mathematical formalism. The rest of the calculation
relies on a saddle-point analysis whose details we postpone below, and we finally obtain a so-called
“global law” for the resolvent of M:15

                   zGM (z)i,j       ∼   Z(z)GA (Z(z))i,j ,        Z(z) ..= zSB (zgM (z) − 1),               (2.100)
                                N →∞

which is often referred to as a subordination relation between the resolvent of M and A. Taking the
trace of both sides of the above equation, one notices that (2.100) is a generalization of the formula
(2.84) as a matrix. We should emphasize that Eq. (2.100) is self-averaging element by element for
the matrix GM (z), i.e. Gij (z) = hGij (z)i + O(N −1/2 ). The matrix GM (z) taken as a whole cannot
be considered deterministic, for example hGM (z)i2 is in general different from hG2M (z)i. When
considering the whole matrix GM (z) one should rather write:

                     z hGM (z)i     ∼     Z(z)GA (Z(z)),         Z(z) ..= zSB (zgM (z) − 1),                (2.101)
                                   N →∞

Note that the average resolvent hGM (z)i is diagonal in the eigenbasis of A, as expected by symmetry.


  15 The term “global” assumes that the imaginary part of z is much larger than N −1 , in contrast to many different

studies of the resolvent at a “local” scale (see [90] for a detail presentation of this concept for Wigner matrices).


                                                         34
   We can redo the exact same calculations for the free addition model M = A + ΩBΩ∗ , still with
A = diag(a1 , a2 , . . . , aN ) (see Appendix D). Starting from the replica identity (2.92) and then
applying (A.5), we obtain the following expression [37]:
                                       n
                                                  !                                  
                                                        δij              Nn a α α
                               Z Z    Y
                                            α   α
                Gij (z) ∝                 dp dζ                  exp   −   F  (p , ζ )  ,     (2.102)
                                      α=1
                                                    z − ζ 1 − ai          2 0

where the ‘free energy’ F0a is given by
                                            n
                                               "N                                   #
                                        1 X X
                      F0a (p, ζ) ..=                       α              α     α α
                                                  log(z − ζ − ak ) − WB (p ) + p ζ .                         (2.103)
                                       N n α=1
                                                k=1

Invoking once again the replica symmetric ansatz, the subordination for the resolvent under the
free addition model follows from a saddle-point analysis [37]

                       GM (z)i,j       ∼   GA (Za (z))i,j ,     Za (z) ..= z − RB (gM (z)),                  (2.104)
                                   N →∞

which is exactly the result obtained in [91] in a mathematical formalism. Again taking the trace of
both sides of this equation allows one to recover the relation (2.67) between Stieltjes transforms.
2.4.3. Free multiplication: replica saddle-point analysis.
      We now present the derivation of (2.100) from (2.98). We shall that it actually provides an elementary
      derivation of the free multiplication formula (2.81). Under the replica symmetric ansatz, the free
      energy becomes
                                                           N
                                                        1 X
                           F0 (pα , ζ α ) ≡ F0 (p, ζ) =       log(z − ζak ) + ζp − WB (p),
                                                        N k=1
      which needs to be extremized. We first consider the first order condition with respect to p which
      leads to
                                               ζ ∗ = RB (p∗ ).                                   (2.105)
      The other derivative with respect to ζ gives:
                                                                           
                                            1
                                                N
                                                       a        TA R z(p∗ )
                                                         k
                                               X
                                       p∗ = ∗                 =      B
                                                                              .                       (2.106)
                                           ζ N k=1 z/ζ ∗ − ak     RB (p∗ )

      Hence, plugging (2.105) and (2.106) into (2.98), we get in the large N limit and then the limit n → 0
      by
                                                             δij
                                           Gij (z)ij =                 .                             (2.107)
                                                        z − RB (p∗ )ci
      We can find a genuine simplification of the last expression using the connection with the free multi-
      plication convolution. By taking the normalized trace of GM (z), we see that we have
                                                                             z
                               zgM (z) = ZgA (Z), with Z ≡ Z(z) =                  ,                 (2.108)
                                                                          RB (p∗ )
      which can rewrite as
                                                   TM (z) = TA (Z).
      Let us define
                                                 ω = TM (z) = TA (Z).                                 (2.109)
      Using Eq. (2.106), this latter equation implies p∗ = ω/RB (p∗ ). Let us now show how to retrieve the
      free multiplicative convolution (2.81) from (2.108) in the large N limit. Indeed, let us rewrite (2.109)
      as
                                            zTM (z) = ZTA (Z)RB (p∗ ),                                 (2.110)


                                                          35
and it is trivial to see that using (2.109) that this last expression can be rewritten as ωTM−1 (ω) =
   −1
ωTA   (ω)RB (p∗ ). Finally, using the definition of the S-transform (2.23), this yields
                                                           1
                                       SM (ω) = SA (ω)            .                              (2.111)
                                                         RB (p∗ )
Using (2.25), we also have
                                        1
                                              = SB (p∗ RB (p∗ )),                                (2.112)
                                     RB (p∗ )
But recalling that p∗ = ω/RB (p∗ ), we conclude from (2.105), (2.109) and (2.112) that
                                       1
                                         = RB (p∗ ) = SB (TM (z)).                               (2.113)
                                      ζ∗
Going back to (2.111), we see that the spectral density of M is given by Voiculescu’s free multiplication
formula
                                        SM (ω) = SA (ω)SB (ω),                                    (2.114)
confirming that the replica symmetry ansatz is indeed valid in this case. Finally, by plugging (2.113)
into (2.107), we get the result (2.100).




                                                   36
3. Spectrum of large empirical covariance matrices

3.1. Sample covariance matrices.
3.1.1. Setting the stage. After a general introduction to RMT and to some of the many different
analytical tools, we are now ready to handle the main issue of this review, which is the statistics
of sample covariance matrices. As a preliminary remark, note that we assume that the variance
of each variable can be estimated independently with great accuracy given that we have T  1
observations for each of them. Consequently, all variables will be considered to have unit variance
in the following and we will not distinguish further covariances and correlations henceforth.
    As stated in the introduction, the study of correlation matrices has a long history in statistics.
Suppose we consider a (random) vector y = (y1 , y2 , . . . , yN ). One standard way to characterize the
underlying interaction network between these variables is through their correlations. Hence, the
goal is to measure as precisely as possible the true (or population) covariance matrix, defined as
                                                
                                    Cij = E yi yj , i, j ∈ [[1, N ]]                              (3.1)

where we assumed that the {yi }i∈[[1,N ]] have zero mean without loss of generality (see below). It is
obvious from the definition of C that the covariance matrix is symmetric. Throughout the following,
we shall define the spectral decomposition of C as
                                                  N
                                                  X
                                           C =          µi vi v∗i ,                                 (3.2)
                                                  i=1

with µ1 ⩾ µ2 ⩾ . . . ⩾ µN the real eigenvalues and v1 , . . . , vN the corresponding eigenvectors.
    As illustrated in the introduction, the concept of covariance is of crucial importance in a wide
range of applications. For instance, let us consider an example that stems from financial applica-
tions. The probability of a large loss of a diversified portfolio is dominated by the correlated moves
of its different constituents (see section 7.1 for more details). In fact, the very notion of diversifica-
tion depends on the correlations between the assets in the portfolio. Hence, the estimation of the
correlations between the price movements of these assets is at the core of risk management policies.
    The major concern in practice is that the true covariance matrix C is in fact unknown. To
bypass this problem, one often relies on a large number T of independent measurements, namely
the “samples” y1 , . . . , yT , to construct empirical estimates of C. We thus define the N × T matrix
Yit ∈ RN ×T , whose elements are the t-th measurement of the variable yi . Within our example
from finance, the random variable Yit would be the return of the asset i at time t. Eq. (3.1) is then
approximated by an average value over the whole sample data of size T , leading to the sample (or
empirical ) covariance matrix estimator:
                                                       T
                                        1   ∗      1 X
                                   Eij = (YY )ij =        Yit Yjt .                                 (3.3)
                                        T          T τ =1

In the statistical literature, this estimator is known as Pearson estimator and in the RMT com-
munity, the resulting matrix sometimes referred to as the Wishart Ensemble. Whereas the Wigner
Ensemble has been the subject of a large amount of studies in physics [49], results on the Wishart
Ensemble mostly come from mathematics & statistics [17, 55, 92], telecommunication [56] or the fi-
nancial/econophysics literature [23, 28, 66], although some work in the physics literature also exists
[93, 94, 95, 96] – to cite a few.

                                                   37
    In what we call the “classical” statistical limit, i.e. T → ∞ with N fixed, the law of large numbers
tells us that E converges to the true covariance C. However, as recalled in the introduction, in the
present “Big Data” era where scientists are confronted with large data-sets such that the sample
size T and the number of variables N are both very large, specific issues arise when the observation
ratio q = N/T is of order unity. This setting is known in the literature as the high-dimensional limit
or Kolmogorov regime (or more commonly called the Big Data regime). This regime clearly differs
from the traditional large T , fixed N situation (i.e. q → 0), where classical results of multivariate
statistics apply. The setting q ∼ O(1) is precisely where tools from RMT can be helpful to make
precise statements on the empirical covariance matrix (3.3).
    A typical question would be to study the ESD of E in order to quantify its deviation from the
true covariance matrix C. More precisely, does the ESD converges to an explicit LSD? If it does,
can we get a tractable expression for this LSD? In the case where the samples {yt }Tt=1 are given by a
multivariate Gaussian distribution with zero mean and covariance C, the distribution of the matrix
E is exactly known since Wishart [8], and is given by Eq. (2.38) above, with M → E. In the case
where C = T −1 IN , we retrieve the isotropic Wishart matrix above that we fully characterized in the
previous chapter. The aim is now to provide the LSD of E for an arbitrary true covariance matrix
C. More specifically, we shall look at linear models where the data matrix Y can be decomposed as
                                                      √
                                                 Y = CX,                                            (3.4)
where X is a N × T random matrix with uncorrelated entries satisfying
                                                            1
                                                            2
                                     E[Xit ] = 0,        E[Xit.]=                           (3.5)
                                                            T
The above decomposition is always possible for multivariate Gaussian variables. Otherwise, the
above framework assumes that our correlated random variables yi are obtained as linear combi-
nations
√        of uncorrelated random variables. In addition, we also require that the random variables
  T Xit have a bounded 4-th moment, in other words that the distribution cannot be extremely
fat-tailed.
    Next, we introduce the spectral decomposition of E,
                                                 N
                                                 X
                                            E=         λi ui u∗i ,                                 (3.6)
                                                 i=1

with λ1 ⩾ λ2 ⩾ . . . ⩾ λN the eigenvalues and u1 , . . . , uN the corresponding eigenvectors. Let us
now list the main assumptions on the spectrum of E, that we shall suppose to hold throughout this
review:
   (i) The support of ρE consists of r + 1 (connected) components with r ⩾ 0. We call the r largest
       components the outliers and the smallest component the bulk. The boundary points of the
       bulk component are labeled λ− and λ+ (with λ− ⩽ λ+ ).
  (ii) We suppose that the outliers are separated from each other and from the bulk (non-degeneracy).
 (iii) We suppose that the bulk is regular in the sense that the density of ρE vanishes as a square
       root at the boundary points λ− , λ+ .
In this chapter, we will look at the statistics of the eigenvalues of this model and the following one
will be devoted to the eigenvectors.
    We end up this short introduction with two different remarks. The first one comments the
zero-mean assumption made above, while the second one is concerned with the possible fat-tailed
nature of the random variables under scrutiny.


                                                    38
3.1.2. Zero-mean assumption. In real data-sets, sample vectors yt usually have a non-zero mean
(even if the true underlying distribution is of zero mean). One can therefore choose to shift the
sample vectors in such a way that the empirical mean is exactly zero. This leads to the following
definition of the empirical correlation matrix, often found in the literature:
                                    T                                         T
                               1 X                                    1 X
                    Ĕij =             Yit − Yi Yjt − Yj ,         Yi =          Yiτ .            (3.7)
                             T − 1 t=1                                    T τ =1

which is clearly unbiased as for T → ∞ with N fixed. This can be rewritten as:
                          1                                                √
                   Ĕ =       Y (IT − ee∗ ) Y∗ , e ..= (1, 1, . . . , 1)∗ / T ∈ RT .
                        T −1
Still, the asymptotic properties of the eigenvalues (and eigenvectors) of E and of Ĕ are identical, up
to a possible extra outlier eigenvalue located at zero when q > 1. The simplest way to understand
that the outlier has no influence on the asymptotic behavior of the spectrum is when Y is a Gaussian
matrix. In this case, we know that a Gaussian matrix is statistically invariant under rotation so one
can always rotate the vector e in the T dimensional space such that it becomes, say, (1, 0, . . . , 0).
Then one has:
                                                      T
                                                 1 X
                                        Ĕij ∼           Yit Yjt
                                               T − 1 t=2

which means that Ĕ and E share identical statistically properties when N, T → ∞ up to a rank one
perturbation of eigenvalue ∼ T −1 → 0 (see Section 2.3.2 for a related discussion). For q < 1, this
has no influence at all on the spectrum since the corresponding eigenvalue is reabsorbed in the bulk.
The possible spike associated to the rank-one perturbation only survives when N ⩾ T , and it leads
to an extra zero eigenvalue from the last equation. But in the case where q ⩾ 1, we know that there
are (N − T ) additional zero eigenvalues, meaning that the extra spike at the origin is harmless.
The case where Y is not rotationally invariant is harder to tackle and needs more sophisticated
arguments for which we refer the reader to [97, Section 9] for more details. As a consequence, all
the results concerning the statistics of the eigenvalues of E that we shall review below hold for Ĕ
as well. From a practical point of view, it is indifferent to consider raw data or demeaned data.
We will henceforth assume that the samples data (y1 , . . . , yT ) has exactly zero mean and will work
with the corresponding E in the next sections.
3.1.3. Distribution of the data entries. The second remark deals with the distribution of the entries
of the matrix Y given in Eq. (3.5). It is well-known for instance that financial returns are strongly
non-Gaussian, with power-law tails [24], and hence, the condition of a sufficient number of bounded
moments can be seen as restrictive. What can be said in the case of entries that possess extremely
fat tails? This is the main purposes of the theory of robust estimators [98, 99] where the RMT
regime N  T has been subject to a lot studies in the past few years, especially in the case of
elliptical distributions [56, 100, 101, 102]. In particular, the so-called Maronna robust M -estimator
of C is the (unique) solution of the fixed point equation
                                           T
                                         1 X  1 ∗ −1 
                                 M ..=         U  y M yt yt y∗t ,                                 (3.8)
                                         T t=1   N t

where U is a non-increasing function. It was shown recently [103] that the matrix M converges to a
matrix of the form encountered in Eq. (2.80) and thus different from E. However, tractable formula

                                                  39
are scarce except for the multivariate Student distribution where U (x) ∼ x−1 [100, 101, 104, 105].
In that case, we have from [106] that the LSD of M converges (almost surely) to that of standard
Wishart matrix E as N → ∞. Therefore, all the results that we will present below holds for
the robust estimator of C under a multivariate Student framework (see also [100]). We postpone
discussions about other class of distributions to Chapter 9.

3.2. Bulk statistics.
3.2.1. Marčenko-Pastur equation. As we alluded to in the introduction, the fundamental tool to
analyze the spectrum of large sample covariance matrices is the Marčenko-Pastur equation [17].
We actually have already encountered a special case of this equation in Section 2.2.3 where we
consider the LSD of E under the null hypothesis C = IN (isotropic case). In this section, we allow
the population correlation matrix C to be anisotropic, that is to say not proportional to the identity
matrix. As we shall see, the final result is not as simple as Eq. (2.41) but many properties can be
inferred from it.
    The Marčenko-Pastur (MP) equation dates back to their seminal paper [17] which gives an exact
relation between the limiting Stieltjes transforms of E and C. This result is at the heart of many
advances in statistical inference in high dimension (see Chapter 7 for some examples or [92] and
references therein). There are several ways to obtain this result, using e.g. recursion techniques
[107], Feynman diagram expansion [66], replicas (see [21] or Section 2.4 above for a generalization)
or free probability. We will present this last approach, which is perhaps the simplest way to derive
the MP equation.
    The key observation is that, for linear models, we can always rewrite E using Eq. (3.4) as
                                       √      √
                                  E = CW C,            W ..= XX∗ ,

where the matrix X satisfies Eq. (3.5) and is independent from C. The model falls into the model
of free multiplication encountered in Section 2.3 since E is the free multiplicative convolution of C
with a white Wishart kernel for N → ∞ [108]. Therefore, the Stieltjes transform of E is exactly
given by Eq. (2.84) that we specialize to

                zgE (z) = Z(z)gC (Z(z)) ,       with     Z(z) ..= zSW (zgE (z) − 1).             (3.9)

Moreover, the S-transform of W was obtained in Eq. (2.44), i.e. SW (z) = (1 + qz)−1 for any q > 0.
Thus, we can re-express Z(z) as:
                                                      z
                                     Z(z) =                     ,                              (3.10)
                                               1 − q + qzgE (z)
which is exactly the Marčenko-Pastur self-consistent equation which relates the Stieltjes transforms
of E and C. The remarkable thing is that the RHS of Eq. (3.9) is “deterministic” as C is fixed
in this framework. Note that this equation is often written in the mathematical and statistical
literature in an equivalent form as:
                                                   ρC (µ)dµ
                                          Z
                                 gE (z) =                           .                           (3.11)
                                            z − µ(1 − q + qzgE (z))
There are two ways to interpret the above Marčenko-Pastur equation:
  1. the ‘direct’ problem: we know C and we want to compute the expected eigenvalues density
     ρE of the empirical correlation matrix;

                                                 40
  2. the ‘inverse’ problem: we observe E and try to infer the true C that satisfies equation (3.9).

Obviously, the inverse problem is the one of interest for many statistical applications, but is much
more difficult to solve than the direct one as the mapping between gC from gE is numerically
unstable. Still, the work of El-Karoui [32] and, more recently, of Ledoit & Wolf [109] allows one
to make progress in this direction with a numerical scheme that solves a discretized version of
the inverse problem Eq. (3.11). On the other hand, the direct problem leads to a self-consistent
equation, which can be exactly solved numerically and sometimes analytically for some special
forms of gC (see next section).
   Let us finally make a remark that we have not seen in the literature before. Enhancing Z(z) to
Z(z, q) to emphasize its dependence on q, one can check that this object obeys the following simple
PDE [110]:
                                  ∂Z(z, q)                 ∂Z(z, q)
                                q          = (Z(z, q) − z)          ,                          (3.12)
                                    ∂q                       ∂z
with initial condition Z(z, q → 0) = z + qz(1 − zgC (z)). This representation can be given a direct
interpretation but whether it is useful numerically or analytically remains to be seen.
3.2.2. Spectral statistics of the sample covariance matrix. For statistical purposes, the Marčenko-
Pastur equation provides an extremely powerful framework to understand the behavior of large
dimensional sample covariance matrices, despite the fact that the inverse problem is not numerically
stable. As we shall see in this section, one can infer many properties of the spectrum of E knowing
that of C, using the moment generating function. Recall the definition of the T -transform in Eq.
(2.21), it is easy to see that we can rewrite Eq. (3.9) as
                                                                           z
                           TE (z) = TC (Z(z)),            Z(z) =                  .           (3.13)
                                                                      1 + qTE (z)

We know from Eq. (2.22) that the T -transform can be expressed as power series for z → ∞, hence
we have
                                              X∞
                                   TE (z) =      ϕ(Ek )z −k ,                             (3.14)
                                               z→∞
                                                     k=1

where ϕ(.) = N −1 Tr(.) is the normalized trace operator. We thus deduce that
                                                            z
                                 Z(z) =              P∞           k −k
                                                                           .
                                       z→∞ 1 + q
                                                           k=1 ϕ(E )z

Therefore we have for z → ∞
                                         ∞                       ∞
                                                                                   !k
                                         X ϕ(Ck )                X
                         TC (Z(z)) =                       1+q         ϕ(E )z −`
                                                                           `
                                                                                        .     (3.15)
                                   z→∞          zk
                                         k=1                     `=1

All in all, one can thus relate the moments of ρE with the moments of ρC by taking z → ∞ in Eq.
(3.13) which yields
                            ∞           ∞                ∞
                                                                    !k
                           X    ϕ(Ek ) X ϕ(Ck )          X
                                                               ` −`
                                      =            1+q      ϕ(E )z     ,                 (3.16)
                                 zk          zk
                          k=1            k=1                    `=1


                                                     41
which was first obtained in [66]. In particular, we infer from Eq. (3.16) that the first three moments
of ρE satisfy

                                  ϕ(E)     = ϕ(C)             =1
                                     2               2
                                 ϕ(E )     = ϕ(C ) + q
                                 ϕ(E3 )    = ϕ(C3 ) + 3qϕ(C2 ) + q 2 .                             (3.17)

We thus see that the variance of the LSD of E is equal to that of C plus q, i.e. the spectrum of
the sample covariance matrix E is always wider (for q > 0) than the spectrum of the population
covariance matrix C. This is an alternative way to convince ourselves that E is a noisy estimator
of C in the high-dimensional regime.
    Note that we can also express the Marčenko-Pastur equation in terms of a cumulant expansion.
Indeed, we can rewrite Eq. (3.9) in terms of the R-transform (see below for a derivation)
                                                                           
                     ωRE (ω) = ζ(ω)RC (ζ(ω)),       ζ(ω) = ω 1 + qωRE (ω) .                 (3.18)

Using the cumulants expansion of the R-transform, given in Eq. (2.19), we obtain for ω → 0
                                                     ∞
                                                     X
                                         ωRE (ω) =            κ` (E)ω ` ,                          (3.19)
                                                     `=1

and                                                                                       !`
                                          ∞
                                          X                           ∞
                                                                      X
                                                          `                           m
                       ζ(ω)RC (ζ(ω)) =          κ` (C)ω        1+q          κm (E)ω            .   (3.20)
                                          `=1                         m=1

By regrouping these last two equations into Eq. (3.18), the analogue of Eq. (3.16) in terms of free
cumulants reads:                                                        !`
                       X∞            X∞                   ∞
                                                          X
                                  `              `                    m
                           κ` (E)ω =      κ` (C)ω 1 + q       κm (E)ω      ,                (3.21)
                        `=1               `=1                       m=1

which would allow one to express the cumulants of E in terms of the cumulants of C.
    Another interesting expansion is the case where q < 1, meaning that E is invertible. Hence g(z)
for z → 0 is analytic and one can readily find
                                                   ∞
                                                   X
                                    g(z) = −              ϕ(E−k )z k−1 .                           (3.22)
                                           z→0
                                                   k=1

This allows one to study the moment of the LSD of E−1 and this turns out to be an important
quantity many applications (see Chapter 7). Using Eq. (3.9), we can actually relate the moments
of the spectrum E−1 to those of C−1 as one has, for z → 0:
                                                          z
                                 Z(z) =                  P∞          −k k
                                                                              .
                                           1−q−q              k=1 ϕ(E  )z

Hence, we obtain the following expansion for Eq. (3.9) at z → 0 and q ∈ (0, 1):
                ∞                ∞
                                                  !k                            !k
               X
                       −k k
                                X
                                       −k     z                   1
                   ϕ(E )z =         ϕ(C )                    q P∞        −` `
                                                                                   ,               (3.23)
                                             1−q       1 − 1−q   `=1 ϕ(E )z
               k=1              k=1


                                                     42
that is a little bit more cumbersome than the moment generating expansion Eq. (3.16) or the
cumulant expansion (3.21). Still, we get at leading order that
                                    ϕ(C−1 )                           ϕ(C−2 )    qϕ(C−1 )2
                        ϕ(E−1 ) =           ,           ϕ(E−2 ) =              +           .      (3.24)
                                     1−q                              (1 − q)2    (1 − q)3
We will see in Section 7.1 that the first relation (that can be found in [66]) has direct consequences
for the out-of-sample risk of optimized portfolios.
   Let us now give a formal derivation of Eq. (3.18). Let us define
                                             ω = gE (z),        ζ = gC (Z),                     (3.25)
   which allows us to rewrite Eq. (3.9) as
                                                                             BE (ω)
                              ωBE (ω) = ζBC (ζ),        Z ≡ BC (ζ) =                     .      (3.26)
                                                                        1 − q + qωBE (ω)
   Then, using the definition (2.16) of the R-transform, we can rewrite this last equation as
                                                                      1   RE (ω) + 1/ω
                               ωRE (ω) = ζRC (ζ),          RC (ζ) +     =              .        (3.27)
                                                                      ζ   1 + qωRE (ω)
   We deduce that
                                                        RE (ω) + 1/ω  1
                                             RC (ζ) =                − ,                        (3.28)
                                                        1 + qωRE (ω)  ζ
   which yields                                                           !
                                                         RE (ω) + 1/ω   1
                                        ωRE (ω) = ζ                   −    .                    (3.29)
                                                         1 + qωRE (ω)   ζ
   By re-arranging the terms in this last equation, we obtain
                                                                             !
                                                           ζ    ωRE (ω) + 1
                                        ωRE (ω) + 1 =                         ,                 (3.30)
                                                           ω    1 + qωRE (ω)
   that is to say                                                     
                                          ζ ≡ ζ(ω) = ω 1 + qωRE (ω) ,                           (3.31)
   and Eq. (3.18) immediately follows by plugging this last equation into Eq. (3.28).

3.2.3. Dual representation and edges of the spectrum. Although a lot of information about the
spectrum of E can be gathered from the Marčenko-Pastur equation (3.9), the equation itself is not
easy to solve analytically. In particular, what can be said about the edges of the spectrum of E?
We shall see that one can answer some of these questions by using a dual representation of Eq.
(3.9).
    The “dual” representation that we are speaking about comes from studying the T × T matrix
S:
                                              1
                                        S := Y∗ Y ≡ X∗ CX,                                     (3.32)
                                             T
where we used Eq. (3.4) in the last equation. The dual matrix S can also be interpreted as a
correlation matrix. In a financial context, E tells us how similar is the movement of two stocks over
time, while S tells us how similar are two dates in terms of the overall movements of the stocks on
these two particular dates. Using a singular value decomposition, it is not difficult to show that S
and E share the same non-zero eigenvalues – hence the “duality”. In the case where T > N , the
matrix S has a zero eigenvalue with multiplicity T − N in addition to the eigenvalues {λi }i∈[1,N] of
E. Therefore, it is easy to deduce the Stieltjes transform of S:
                               1 T −N                    1−q
                                                    
                                                                             1
                      gS (z) =            + N gE (z) =        + qgE (z) =       .              (3.33)
                               T     z                     z               Z(z)

                                                           43
The introduction of this dual representation of the empirical matrix allows one to get the following
expression from Eq. (3.11):
                                                                  
                                        1               ρC (µ)dµ
                                                     Z
                               gS (z) =     1−q+q                    .
                                        z              1 − µgS (z)

After some manipulations, we can rewrite this last equation as

                                       1             ρC (µ)dµ
                                                Z
                                z=          +q      −1
                                                               .                                 (3.34)
                                     gS (z)        µ − gS (z)

Writing ω = BS (gS (z)) in the above equation, we obtain a characterization of the functional inverse
of gS as
                                               1       ρC (µ)dµ
                                                    Z
                                    BS (ω) :=    +q             ,                              (3.35)
                                               ω       µ−1 − ω
and this is the dual representation of the Marčenko-Pastur equation (3.9). The analytic behavior
of this last equation has been the subject of several studies, especially in [29]. In particular, it was
proved that there exists a unique ω ∈ C+ that solves the equation (3.35). This yields the Stieltjes
transform of S from which we re-obtain the Stieltjes transform of E using Eq. (3.33). We will see in
the next section that the dual representation (3.35) of the Marčenko-Pastur equation is particularly
useful when we will try to solve the direct problem.
    In addition, the position of the edges of the LSD of E can be inferred from Eq. (3.35). Within
a one cut-assumption, the edges of the support of ρE are given by:

                      λE± = BS (ω± )   where ω± ∈ R+ is such that BS0 (ω± ) = 0.                 (3.36)

Indeed, knowing the spectral density of S allows us to get the spectral density of E since from Eq.
(3.33) one gets:
                                  ρS (λ) = qρE (λ) + (1 − q)+ δ0 ,                            (3.37)
for any λ ∈ supp ρS . Next, one easily obtains

                                                          ρS (x)dx
                                                     Z
                                       g0S (z) = −                 < 0,                          (3.38)
                                                          (z − x)2

for any z 6∈ supp[ρS ], meaning that it is strictly decreasing outside of the support. We saw in
Section 2.1.2 that the Stieltjes transform g(z) is analytical and positive for any z ∈ R outside of
the support. Moreover, for z → ∞, we have gS (z) ∼ z −1 + O(z −2 ) so that we deduce gS (z) is a
bijective decreasing function. Its inverse function BS therefore also decreases in those same intervals.
Consequently, the union of intervals where BS (x) is decreasing will lead to the complement of the
support and the edges of the support of ρS are thus given by the critical points of BS , as in Eq.
(3.36) above. If one assumes that there are a finite number r of (non-degenerate) spikes, we can
readily generalize the above arguments and find that there will be 2(r +1) critical points (see Figure
3.1 for an illustration with two non-degenerate spikes).
3.2.4. Solving Marčenko-Pastur equation. In this section, we investigate the direct problem of solv-
ing the Marčenko-Pastur equation Eq. (3.9) for gE given gC . We will discuss briefly the inverse
problem at the end of this section.


                                                         44
Figure 3.1. The function BE (x) with population eigenvalues density given by 0.002 δ15 +0.002 δ8 +0.396 δ3 +
0.3 δ1.5 + 0.3 δ1 . Here T = 1000, N = 500 and we have 3 connected components. The vertical asymptotes
are located at each −x−1 for x ∈ {1, 1.5, 3, 8, 15}. The support of ρS is indicated with thick blue lines on
the vertical axis. The inverse of gS |R\supp ρS is drawn in red.



Exactly solvable cases. As far as we know, there are only a few cases where we can find an explicit
expression for the LSD of E. The first one is trivial: it is when one considers the “classical” limit
in statistics where T → ∞ for a fixed value of N . In this case q = 0 in (3.11), and obviously
gE (z) = gC (z) in this case, as expected.
    However, for any finite observation ratio q > 0, we anticipate from the discussion of Section
3.2.2 above that the LSD of E will be significantly different from that of C. The influence of q can
be well understood in the simple case where C = IN . We know from Section 2.2.3 that this case
is exactly solvable and the LSD of E is the well-known Marčenko-Pastur law (2.42), that we recall
here:
                                        q        q
                             z + 1 − q − z − λmp
                                               −   z − λmp
                                                         +                    √ 2
                   gE (z) =                                  ,    λmp
                                                                   ± = (1 ±    q)              (3.39)
                                           2qz
                                                             √          √
In words, the sample eigenvalues spans the interval [(1 − q)2 , (1 + q)2 ] while the population
eigenvalues are all equal to unity. We therefore deduce that the variance of the sample eigenvalue
distribution is order q, highlighting the systematic bias in the estimation of the eigenvalues using
E when q = O(1). This effect can be visualized using the quantile representation of the spectral
distribution. Indeed, it is known since [97, 111] that the bulk eigenvalues [λi ]i∈[[r+1,N ]] converge in


                                                    45
Figure 3.2. Typical position of the sample eigenvalues under the Marčenko-Pastur law (2.42) with a finite
observation ratio q = 0.25 (red line) and q = 0.5 (blue line). The dotted line corresponds to the locations
of the population eigenvalues and we see a significant deviation.



the high-dimensional regime to their “quantile positions” [γi ]i∈[[r+1,N ]] . More precisely, this reads:
                                               Z γi
                                         i
                       λi ≈ γi , where      =       ρE (λ)dλ,        i ⩾ r + 1.                     (3.40)
                                         N
We plot the γi ’s of the Marčenko-Pastur law in Fig. 3.2 for q = 1/4 and q = 1/2, and observe
systematic and significant deviations from the “classical” positions γiq=0 ≡ 1. This again illustrates
that E is an untrustworthy estimator when the sample size is of the same order of magnitude as
the number of variables.
    Now that the qualitative impact of the observation ratio q is well understood, a natural extension
would be to examine the Marčenko-Pastur equation for a non trivial correlation matrix C. To this
aim, we now consider another interesting solvable case, especially for statistical inference, which is
the case and of an (isotropic) inverse Wishart matrix with hyper-parameter κ > 0. From Section
2.2.4, we recall that
                                                        ω
                                          SC (ω) = 1 −     ,
                                                        2κ
for κ > 0. Then, using the free multiplication formula (2.81), we have SE (ω) = SC (ω)SW (ω) where
SW (ω) is given in (2.44), which yields a quadratic equation in TE (z). This implies that gE reads:
                                       p
                  z(1 + κ) − κ(1 − q) ± (κ(1 − q) − z(1 + κ))2 − z(z + 2qκ)(2κ + 1)
        gE (z) =                                                                        ,       (3.41)
                                              z(z + 2qκ)
from which we can retrieve the edges of the support:
                                1h               p                 i
                         λiw
                          ± =      (1 + q)κ + 1 ± (2κ + 1)(2qκ + 1) .                               (3.42)
                                κ

                                                    46
Figure 3.3. Solution of the Marčenko-Pastur equation for the eigenvalue distribution of E when C is an
inverse Wishart matrix with parameter κ = 1.0 for q = 0.25 (red line) and q = 0.5 (blue line). The black
dotted line corresponds to the LSD ρC .



One can check that the limit κ → ∞ recovers the null hypothesis case C = IN ; the lower κ, the
wider the spectrum of C. We plot in Figure 3.3 the spectral density ρC and ρE for q = 0.25 and
q = 0.5 as a function of the eigenvalues. Again, we see that the spectral density of E puts significant
weights on regions of the real axis which are outside the support of ρC , due to the measurement
noise. From an inference theoretic viewpoint, the interest of the Inverse-Wishart ensemble is to
provide a parametric prior distribution for C where everything can be computed analytically (see
Chapter 5 below for some applications).
   There exist several other examples where the Marčenko-Pastur equation is exactly solvable even though the
   Stieltjes transform is not explicit. For instance, if we consider C to be a Wishart matrix of parameter q0
   independent from W, then we have from (2.81) that
                                                                1
                                            SE (ω) =                      .
                                                       (1 + q0 ω)(1 + qω)
   It is then easy to see from the definition (2.23) that TE (z) ≡ ω(z) is solution of the cubic equation,
                                  z(1 + ω(z))(1 + q0 ω(z))(1 + qω(z)) − ω(z) = 0,                            (3.43)
   from which we obtain gE (z) thanks to (2.21) and by choosing the unique solution of the latter equation in
   C+ (see the following section for details on this point). Another toy example that uses the Marčenko-Pastur
   with the R-transform formalism is when C is a GOE centered around the identity matrix. In this case we
   have
                                                 RC (ω) = 1 + σ 2 ω,                                     (3.44)
   where we add the constraint σ ⩽ 0.5 such that C remains a positive semi-definite matrix. Then, by plugging
   this formula into (3.18), we find that gE (z) = ω is the solution of quartic equation:
                              σ 2 ω 2 (1 + qωRE (ω))2 + ω(1 + qωRE (ω)) − ωRE (ω) = 0,                       (3.45)
   and as above, we take the unique solution in C+ in order to get the right Stieltjes transform.


                                                          47
    The general case: numerical method Apart from the very specific cases discussed above, finding
an explicit expression for gE (z) is very difficult. This means that we have to resort to numerical
schemes in order to solve the Marčenko-Pastur equation. In that respect, the dual representation
(3.35) of Eq. (3.9) comes to be particularly useful. To solve the MP equation for a given z, we seek
a certain g ≡ gS such that16
                                        z = BS (g),     g ∈ C+ ,                              (3.46)

where the expression of BS in terms of ρC is explicit and given in Eq. (3.35). Numerically, the above
equation is easily solved using a simple gradient descent algorithm, i.e. find g ∈ C+ such that
                                            (                   
                                                Re(z) = Re BS (g)
                                                                                             (3.47)
                                                Im(z) = Im BS (g) .

It then suffices to use Eq. (3.33) in order to get gE (z) for any z ∈ C− . Hence, if one wants to
retrieve the eigenvalues density ρE at any point on the real line, we simply have to set z = λ − iε
with λ ∈ Supp(E) and ε an arbitrary small real positive number into Eq. (3.47). Note that in the
case where gC is known, one can rewrite equation (3.35) as
                                                              
                                                1         q    1
                                       BS (x) =    1 − q + gC      ,                           (3.48)
                                                x         x    x

which is obviously more efficient since we avoid to compute the integral over eigenvalues.
    In order to illustrate this numerical scheme, let us consider a covariance matrix whose LSD has
a heavy right tail. One possible parametrization is to assume a power-law distribution of the form
[28]:
                                                sA
                                  ρC (λ) =               Θ(λ − λmin ),                        (3.49)
                                            (λ + λ0 )1+s
where Θ(x) = x+ is the Heaviside step function, s is an exponent that we choose to be s = 2 [28],
and λmin the lower edge of the spectrum below which there R      are no eigenvalues
                                                                               R    of C. A, λmin are
then determined by the two normalization constraints ρC (x)dx = 1 and xρC (x)dx = 1. This
leads to: λmin = (1 − λ0 )/2 and A = (1 − λmin )2 . We restric to λ0 > −11 such that λmin < 1. From
the density Eq. (3.49), one can perform the Stieltjes transform straightaway to find

                                          2(1 − λ0 )       2(1 − λ0 )2        λ0 − z
                                                                                   
                              1
              gC (z) =               +                 +                  log           ,      (3.50)
                         z + 1 − 2λ0   (z + 1 − 2λ0 )2   (z + 1 − 2λ0 )3      1 − λ0

which allows one to solve Eq. (3.48) for gE (z) with only a few iterations. As we observe in Fig. 3.4,
the theoretical value obtained from the numerical scheme (3.47) agrees perfectly with
                                                                                    √ the√empirical
results, obtained by diagonalizing matrices of size N = 500 matrices obtained as CW C, where
W is a Wishart matrix. This illustrates the robustness of the above numerical scheme, even when
the spectrum of C is fat-tailed. In addition, we can notice that the more we add structure in the
true covariance C, the wider is the empirical distribution as in the above case, where the spectrum
of E embraces nearly all the positive real number line.

 16 Recall that S is the T × T equivalent of E defined in Eq. (3.32).




                                                         48
                  1.5

                                  signal          -5
                                             2.8×10
                                  sample
                                                  -5
                                             2.4×10

                   1                              -5
                                             2.0×10


                                                  -5
           ρ(λ)




                                             1.6×10


                                                  -5
                                             1.2×10

                  0.5                                 35    36   37       38   39   40   41   42   43   44




                   0
                        0   1          2          3                   4                  5              6    7
                                                            λ


Figure 3.4. Resolution of the Marčenko-Pastur equation when ρC is given a power law density with
parameter λ0 = 0.3 and a finite observation ratio q = 0.5 and N = 500. The dotted line corresponds to the
LSD of C while the plain line corresponds to the LSD of E. The histogram is the ESD when we compute E
from the definition (3.3). The main figure covers the bulk of the eigenvalues while the inset zooms in the
region of very large eigenvalues.



3.3. Edges and outliers statistics. As we alluded to several times above, the practical usefulness
of the theoretical predictions for the eigenvalue spectra of random matrices is (i) their universality
with respect to the distribution of the underlying random variables and (ii) the appearance of sharp
edges in the spectrum, meaning that the existence of eigenvalues lying outside the allowed region
is a possible indication against simple “null hypothesis” benchmarks. Illustrating the last point,
Fig. 3.5 shows the empirical spectral density of the correlation matrix corresponding to N = 406
and T = 1300 so that q ≈ 0.31, compared to the simplest Marčenko-Pastur spectrum in the null
hypothesis case C = IN . While the bulk of the distribution is roughly accounted for (but see
Section 7.2 for a much better attempt), there seems to exist a finite number of eigenvalues lying
outside the Marčenko-Pastur sea, which may be called outliers or spikes. However, even if there are
no such spikes in the spectrum of C, one expects to see, for finite N some eigenvalues beyond the
Marčenko-Pastur upper edge. The next two subsections are devoted first to a discussion of these
finite size effects, and then to a model with “true” outliers that survive in the large N limit.

3.3.1. The Tracy-Widom region. This existence of sharp edges delimiting a region where one expects
to see a non zero density of eigenvalues from a region where there should be none is only true in
the asymptotic N, T → ∞, and in the absence of “fat-tails” in the distribution of matrix elements
(see [73, 112]). For large but finite N , on the other hand, one expects that the probability to find


                                                       49
                                1.0                         Empirical data
                                                            Marcenko Pastur




                         ρ(λ)
                                0.5




                                0.0
                                      0    1            2          3          4
                                                        λ

Figure 3.5. Test of the null hypothesis on the empirical correlation matrix E using US stocks’ data with
N = 406 and T = 1300.



an eigenvalue beyond the Marčenko-Pastur sea is very small but finite. The width of the transition
region, and the tail of the density of states was investigated already a while ago [113], culminating
in the beautiful results by Tracy & Widom on the distribution of the largest eigenvalue of a random
matrix [26]. The Tracy-Widom result is actually a very nice manifestation of the universality
phenomenon that describes the fluctuations of macroscopic observables in many large dimensional
systems (see the recent paper [114] on this topic). The derivation of the Tracy-Widom distribution
mainly relies on Orthogonal polynomials that we will not discuss in this review (see e.g. [26, 115])
but there also exists an alternative approach [116]. The link between this limiting law and the
largest eigenvalue of large sample covariance matrices has been subject to a large amount of studies
that we will not attempt to cover here (see e.g. [25, 50, 51, 117, 118, 119] for details and references).
    The Tracy-Widom result characterizes precisely the distance between the largest eigenvalue λ1
of E and the upper edge of the spectrum that we denoted by λ+ . This result can be (formally) stated
as follows: the rescaled distribution of λ1 − λ+ converges towards the Tracy-Widom distribution,
usually noted F1 ,
                                                          
                                  P λ1 ⩽ λ+ + γN −2/3 u = F1 (u),                                  (3.51)

where γ is a constant that depends on the problem. For the isotropic Marčenko-Pastur problem,
           √               √ 2/3
λ+ = (1 + q)2 and γ = qλ+ , whereas for the Wigner problem, λ+ = 2 and γ = 1. We stress
that this result holds for a large class of N × N matrices (e.g. symmetric random matrices with
IID elements of a finite fourth moment, see [112, 73]).
   Everything is known about the Tracy-Widom density f1 (u) = F10 (u), in particular its left and


                                                   50
right far tails:
                   ln f1 (u) ∝ −u3/2 ,   (u → +∞);          ln f1 (u) ∝ −|u|3 ,   (u → −∞);                (3.52)
One notices that the left tail is much thinner: pushing the largest eigenvalue inside the allowed
band implies compressing the whole Coulomb gas of repulsive charges, which is difficult. Using this
analogy, the large deviation regime of the Tracy-Widom problem (i.e. for λ1 − λ+ = O(1)) can also
be obtained [50].
   Note that the distribution of the smallest eigenvalue λmin around the lower edge λ− is also
Tracy-Widom, except in the particular case of Marčenko-Pastur matrices with q = 1. In this case,
λ− = 0 which is a ‘hard’ edge since all eigenvalues of the empirical matrix must be non-negative.
This special case is treated in, e.g. [120].
3.3.2. Outlier statistics. Now, there are cases where a finite number of eigenvalues genuinely reside
outside the Marčenko-Pastur sea (or more generally outside of the bulk region) even when N → ∞.
For example, the empirical data shown in Fig. 3.5 indeed suggests the presence of true outliers,
that have a real financial interpretation in terms of economic sectors of activity. Therefore, we need
a framework to describe correlation matrices that contain both a bulk region and a finite number
of spikes. The purpose of this section is to study the statistics of these eigenvalues from an RMT
point of view.
    The standard way to treat outliers is to “blow out” a finite number of eigenvalues of a given
(spikeless) correlation matrix C, that we construct as:
                                N
                                                          (
                               X                            µ0 if i ⩽ r
                          C=       µi vi v∗i , where µi =                                       (3.53)
                               i=1
                                                            µi if i ⩾ r + 1 .

We choose the eigenvalue µ0 within the spectrum of C such that there is no outliers initially. Here
we fix µ0 = µr+1 for simplicity, but any other choice in the set [µi ]i⩾r+1 would do equally well.
Then with this prescription, we may rewrite C as a small rank perturbation of C. Indeed, since
each outlier [µi ]i⩽r are well separated from the bulk by assumption, we may parametrize each spike
µi by a positive real number di for any i ⩽ r as follows:
                           µi = µ0 (1 + di ) ≡ µr+1 (1 + di ),       di > 0 , i ⩽ r.                       (3.54)
Hence, the population covariance matrix C is given by:
                         N
                                                   (
                        X                            µ0 (1 + di )           if i ⩽ r
                   C=       µi vi v∗i , where µi =                                                         (3.55)
                        i=1
                                                     µi                     if i ⩾ r + 1 .

More synthetically, one can write C as:
                                         C = C IN + V(r) DV(r)∗ ,
                                                               
                                                                                                           (3.56)

where V(r) ..= [v1 , . . . , vr ] ∈ RN ×r and D ..= diag(d1 , . . . , dr ) is a diagonal matrix that characterizes
the spikes. We also define a fictitious spikeless sample covariance matrix as E = C1/2 XX∗ C1/2 and
denote by S = X∗ CX the T × T “dual” matrix. As noticed in [38], the statistics of the outliers of
E can be investigated through that of E. Let us consider the rank-one r = 1 case for the sake of
simplicity (see [38] for the general case). Then, we have
        det(zIN − E) = det(zIN − X∗ C(IN + d1 v1 v∗1 )X) = det(zIN − XX∗ C(IN + d1 v1 v∗1 )).


                                                       51
which can be transformed into:

                     det(zIN − E) 