source: https://arxiv.org/pdf/2203.05603
fetched_utc: 2026-10-04T18:40:31Z
bytes_raw: 1217592

A persistent-homology-based turbulence index &
                                            some applications of TDA on financial markets
arXiv:2203.05603v3 [q-fin.MF] 7 Jul 2023




                                           Miguel A. Ruiz-Ortiz1 , Jesús Rodrı́guez-Viorato2 , and José Carlos
                                                                   Gómez-Larrañaga3
                                                      1
                                                        Universidad de Guanajuato, Guanajuato 36240, Gto., MÉXICO;
                                                                            miguel.ruiz@cimat.mx
                                                  2
                                                    CIMAT, Jalisco S/N, Col. Valenciana, CP 36023 Guanajuato, Gto, México;
                                                                              jesusr@cimat.mx
                                               3
                                                 CIMAT-Mérida, Carretera Sierra Papacal Chuburna Puerto Km 5, 97302 Sierra
                                                                   Papacal, Yuc., México; jcarlos@cimat.mx


                                                                              July 11, 2023

                                                                                    Abstract
                                                      Topological Data Analysis (TDA) is a modern approach to Data Anal-
                                                  ysis focusing on the topological features of data; it has been widely stud-
                                                  ied in recent years and used extensively in Biology, Physics, and many
                                                  other areas. However, financial markets have been studied slightly through
                                                  TDA. Here we present a quick review of some recent applications of TDA
                                                  on financial markets, including applications in the early detection of tur-
                                                  bulence periods in financial markets and how TDA can help to get new
                                                  insights while investing. Also, we propose a new turbulence index based
                                                  on persistent homology — the fundamental tool for TDA — that seems
                                                  to capture critical transitions in financial data; we tested our index with
                                                  different financial time series (S&P500, Russel 2000, S&P/BMV IPC and
                                                  Nikkei 225) and crash events (Black Monday crash, dot-com crash, 2007-
                                                  08 crash and COVID-19 crash). Furthermore, we include an introduction
                                                  to persistent homology so the reader can understand this paper without
                                                  knowing TDA.
                                               Keywords: TDA, Financial Markets, Time Series, Persistence Homology,
                                                          Persistence Diagrams, Persistence Landscapes


                                           1      Introduction
                                           The main objective of Topological Data Analysis (TDA) is to find the shape of
                                           data, checking if there are connected components, holes, or gaps in a representa-
                                           tion of data in Rd . This has been achieved mainly through persistent homol-
                                           ogy [5, 8], and it deals with the detection of n-dimensional holes, n = 0, 1, 2, . . .,
                                           that are formed by connecting nearby points.


                                                                                      1
    There are at least two good reasons for applying persistent homology to
financial data. First, persistent homology gives us shape features of financial
data, although it is a high-dimensional space. Second, persistent homology is
robust to perturbations of input data, and this robustness is ideal for reliable
prediction of regime shifts in markets [15, 1].
    In this paper, we review what kind of efforts have been made to understand
financial markets via TDA and how TDA could help us control risk while invest-
ing in financial markets. Furthermore, we propose a new persistent-homology-
based turbulence index employing previous ideas [11, 1] and show experiments
results studying this index on different financial datasets during different previ-
ous financial crashes (Black Monday, dot-com, 2007-08 and COVID crashes).
    We found that applications in financial markets are in their early stages of
development at the time this research was done (see [10, 12, 11, 22, 1]). A
common way of studying financial markets is through the time series given by
the prices of financial assets. As can be seen in [17], the application of TDA
to time series is relatively new and deals with areas such as dynamical systems
and signal processing (see [16, 3]).
    In section 2, we find an introduction to persistent homology —the most pop-
ular tool of TDA — together with some theoretical concepts to fully understand
the applications to financial markets explained here. In general, the main appli-
cation of TDA in financial markets has been the study of critical transitions,
which are the applications on which we focus the most here. We mean by a
critical transition an abrupt change in the behavior of a complex system. A
critical transition in financial markets is known as a market crash.
    In section 3, we detail three TDA applications to detect critical transitions
in financial markets [10, 12, 11]. Getting early signs of critical transitions in
financial markets would help gain better control of risk in portfolio construction
(see section 1.1 for more details). This, however, is a challenging task, as [10]
mentions.
    In section 4, the development of investing strategies by [1] derived from a
persistent-homology-based turbulence index (PHTI) is examined. Finally, in
section 5, we propose a modified variation of the PHTI that depends on five
parameters. We selected the parameters that best capture the abrupt change
in S&P500 prices due to the 2020 stock market crash between February 20th
and April 7th, 2020, induced by the COVID-19 pandemic. We finally tested the
selected parameters on different datasets and financial crashes and analyzed the
results.

1.1    Financial markets concepts
A financial asset is an investing vehicle. Some examples of financial assets
are shares of stocks, bonds, foreign currencies, and real estate. The three main
characteristics of financial assets are liquidity (the capacity to convert the asset
into money), profit, and risk. These assets’ prices follow the laws of supply
and demand, so prices fluctuate over time. A portfolio is simply a collection



                                         2
of financial assets. These assets are acquired in the financial markets (stock
market, foreign exchange market, or cryptocurrency market).
    We may buy a financial asset, for example, shares of a company, with the
goal in mind of obtaining a profit. This can be achieved if the price of this
financial asset increases after we have bought it and then we sell it. Transactions
of financial assets have the risk of having losses instead of positive returns (a
return is a change in the price of an asset over time) because the price may
decrease after we have bought it.
    Due to the volatility and uncertainty that often exist in financial markets,
it is important to have risk measures to avoid large losses caused by extreme
market movements. This topic has been widely studied with statistics and
artificial intelligence tools (see [14, 21]).


2     Persistent Homology
This section introduces the TDA concepts necessary to understand this paper.
To go deeper, see [5, 8, 9].

2.1    Simplicial Homology
Definition: A simplicial complex Σ is a collection of non-empty subsets of
a finite set of vertices Σ0 that satisfy

                           α ∈ Σ, β ⊂ α       ⇒   β ∈ Σ.

If α ∈ Σ and k = |α| − 1, α is called a k - simplex, and β ⊂ α is known as a
face of α. We will denote the set of all k -simplices as Σk . The dimension of
Σ is defined as
                           dim(Σ) := max{|α| − 1}.
                                        α∈Σ

These concepts can be visualized in figure 1. In TDA, simplices are used to
study data.




Figure 1: k -simplices for k = 0, 1, 2, 3 (top) and a simplicial complex (bottom).




                                          3
   Let us consider Ck the free abelian group with coefficients in Z generated by
the k-simplices, so each element c ∈ Ck can be expressed as
                                         n
                                         X
                                    c=         ci αi ,
                                         i=1

where the αi are k-simplices and ci ∈ Z, for some n ∈ N.
    Suppose that a total order is imposed on the set of vertices Σ0 . This allows
defining a set of homomorphisms di : Ck → Ck−1 , 0 ≤ i ≤ k, given by their
action on the basis Σk as di (σ) = σ \ {si } for each σ ∈ Σk (i.e., we first define it
on the basis Σk and then extend it linearly to Ck ), where si is the i -th element
of σ. Let us define the boundary homomorphism δk : Ck → Ck−1 given by
                                        k
                                        X
                                 δk =         (−1)i di .
                                        i=0

    Notice that δk ◦δk+1 = 0, so Im(δk+1 ) ⊆ Ker(δk ). This leads to the following
definition.
    Definition: The k-th homology group of Σ is defined as

                           Hk (Σ) = Ker(δk )/Im(δk+1 ).

The k-th Betti number of Σ is defined as

                                βk = rank(Hk (Σ)),

and it is the number of k-dimensional holes on Σ, e.g., β0 is the number of
independent connected components, β1 is the number of loops, β2 is the number
of cavities, and so on.

2.2     Construction of simplicial complexes
Suppose we have a point cloud X = {x1 , x2 , . . . , xN } ⊂ Rd . To study its shape,
we would like to associate X with a simplicial complex. The following are some
different ways to do it.

2.2.1   Ĉech simplicial complex
Definition: The Ĉech complex C(X, ϵ) with parameter ϵ > 0 and with vertices
in X is                      (                          )
                                         \
                    C(X, ϵ) = α ⊂ X :       Bϵ (v) ̸= ∅
                                                 v∈α

where Bϵ (v) is the ball of radius ϵ centered at v. This simplicial complex is
called the nerve of {Bϵ (x)}x∈X .




                                          4
2.2.2   Vietoris-Rips simplicial complex
Definition: The Vietoris-Rips complex V R(X, ϵ) with parameter ϵ > 0 and
with vertices in X is

              V R(X, ϵ) = {α ⊂ X : ||vi − vj || ≤ ϵ, ∀ vi , vj ∈ α} .

    Notice that if Σ(ϵ) is the Ĉech complex or the Vietoris-Rips complex asso-
ciated with ϵ > 0 with vertices at X, we get

                                Σ(ϵ′ ) ⊆ Σ(ϵ),   ∀ ϵ′ ≤ ϵ.

We call this the filtering property. The inclusion map induces a morphism
between the homology groups:

                           Hk (Σ(ϵ′ )) → Hk (Σ(ϵ)),       ∀ ϵ′ ≤ ϵ.

These last two results are helpful for the definition of persistent homology, as
we will see next.

2.3     Persistent homology
2.3.1   Filtration
Definition: Let Σ be a simplicial complex. A filtration of Σ is a mapping
ϵ ∈ (0, ∞) 7→ Σ(ϵ), where Σ(ϵ) ⊆ Σ is a sub-simplicial complex that fulfills the
filtering property:
                           Σ(ϵ′ ) ⊆ Σ(ϵ), ∀ ϵ′ ≤ ϵ.
    Observe that the Vietoris-Rips and Chech complexes are filtrations. We have
already commented that by taking the k-dimensional Homology of a filtration
ϵ 7→ Σ(ϵ) we obtain induced homomorphism:
                       ′
                     hϵk ,ϵ : Hk (Σ(ϵ′ )) → Hk (Σ(ϵ)),       ∀ ϵ′ ≤ ϵ.
                                                      ′
The inclusion Σ(ϵ′ ) ⊂ Σ(ϵ) induces the map hϵk ,ϵ .
                                                                             ′
     Definition: The k-th persistent homology groups are given by Hkϵ ,ϵ =
       ′
Im(hϵk ,ϵ ), ∀ ϵ′ ≤ ϵ.
     Definition: We say that the homology class α ∈ Hk (Σ(b)), b > 0, is born
at b if α ̸∈ Hkb−δ,b for all δ > 0. If α is born at b, we say that dies at d ≥ b if
hb,ϵ                                b,d
  k (α) ̸= 0 for b < ϵ < d, and hk (α) = 0. If α is born and never dies in the
above sense, we say that dies at d = ∞.
     We then have a birth value b(α) = b and a death value d(α) = d for each α
in the homology groups.
     Definition: The persistence, or lifetime, of the homology class α is the
difference
                               pers(α) = d(α) − b(α).


                                            5
    The intuition behind these concepts is that through a “discrete” filtra-
tion of simplicial complexes associated with a finite number of parameters
0 < ϵ1 < ϵ2 < . . . < ϵn we can track the topological characteristics (con-
nected components, holes, etc.) that appear throughout the filtration. Those
generators that have more persistence are the most significant.

2.3.2   Persistence Diagrams
It is possible to find a set of bases, one for each homology group, such that
                                                         ′
the image of a base element σk for Hk (Σ(ϵ)) under hϵ,ϵk   is either a generator of
Hk (Σ(ϵ′ )) or zero.
     Definition: Let us fix a basis for each homology group as explained above.
The k -th persistence diagram (or k -dimensional persistence diagram) of the
filtration ϵ 7→ Σ(ϵ) is defined as the multiset Pk in R2 obtained as follows:
   • Each generator class αk in a k -th homology group is assigned a point
     (bk , dk ) ∈ R2 with multiplicity µk (bk , dk ), where bk = b(αk ) and dk =
     d(αk ) (the birth and death parameters), and the multiplicity is the number
     of generators αk that were born at bk and died at dk .
   • Pk contains all points (x, x) ∈ R2 with x ≥ 0 with infinite multiplicity.
Notice the need for bases in the definition of the persistent diagrams. Fortu-
nately, the resulting persistence diagram is independent of the selected bases.

2.3.3   Distance between persistence diagrams
We can define many distance functions to make the space P of persistence
diagrams a metric space. A very common metric is the following.
   Definition: The Wasserstein distance of degree p, p ∈ N, is defined as
                                                              1/p
                                             X
                   Wp (Pk1 , Pk2 ) = inf        ||q − ϕ(q)||p∞      ,
                                     ϕ
                                         q∈Pk1


where the infimum is taken over all bijections ϕ : Pk1 → Pk2 , and || · ||∞ denotes
the supremum norm at R2 . When p = ∞, the Wasserstein distance W∞ is
known as the bottleneck distance.
    An important property that makes persistent homology suitable for analyz-
ing data with noise is its robustness under small disturbances in the data. That
is if our point cloud changes ‘a little’, then the Wasserstein distance between
the respective persistence diagrams is small (see [7]).

2.4     Persistence landscapes
The metric space (P, Wp ) of persistence diagrams is not complete, so it is unsuit-
able for statistical purposes. This is why persistence landscapes are a preferred
representation of persistence diagrams, they are elements in the Banach space


                                             6
Lp (N×R) (recall that a complete normed vector space is called a Banach space),
in which statistical methods can be used (see [4]).
    Let us consider P a persistence diagram. For each point (bα , dα ) ∈ P asso-
ciated to the birth and death of some homological class α, define
                                  
                                             x ∈ bα , bα +d
                                                                
                                   x − bα ,                      ;
                                                              α
                                                           2
                                  
                  f(bα ,dα ) (x) = −x + dα , x ∈ bα +d
                                                                
                                                       2
                                                         α
                                                           , dα ;
                                  
                                    0,       x ̸∈ (bα , dα ).
                                  

Let λ = (λk )k∈N be a sequence of functions λk : R → [0, ∞) given by

                   λk (x) = k- max{f(bα ,dα ) (x) : (bα , dα ) ∈ P },

where k-max denotes the k -th largest value of a set. When the k -th largest
value does not exist, we set λk (x) = 0.
    Definition: The persistence landscape associated with the persistence dia-
gram P is the sequence of functions λ = (λk )k ∈ Lp (N × R) defined above. λk
is known as the k-th layer of the persistence landscape.
    The norm that we consider in the Banach space Lp (N × R) is given by

                                           ∞
                                                              !1/p
                                           X
                             ||η||p =            ||ηk ||pp              ,
                                           k=1

where η = (ηk )k and || · ||p denotes the norm Lp , i.e.,
                                           Z                1/p
                                                         p
                               ||f ||p =          |f |              .
                                             R


3     Detecting critical transitions
3.1    Correlation graphs of Dow-Jones index
M. Gidea in [10] studied the daily returns of company stocks in the Dow Jones
Industrial Average (DJIA) during the period January 2004 to September 2008
and tracks the change in the topology of the correlation graphs, defined be-
low, as prices approached the 2007-08 financial crisis using persistent homology.
Their objective was to find early signs of such a critical transition —a crash—
in financial markets.
    Let us consider xi (t) the daily return t of the i -th share. The graph G =
(V, E) of correlation at time t of the returns {xi (t)}t,i is a weighted graph
where the stocks of the DJIA are represented by the vertices V , and each pair
of distinct vertices i, j ∈ V are connected by an edge e ∈ E, which is assigned
the weight                             q
                             di,j (t) :=    2(1 − ci,j (t)),



                                             7
where                         Pt
                                 τ =t−T (xi (τ ) − xi )(xj (τ ) − xj )
            ci,j (t) = qP                             qP                          ,
                           t                      2    t                      2
                           τ =t−T (xi (τ ) − xi )      τ =t−T (xj (τ ) − xj )

is the Pearson correlation coefficient between nodes i and j at time t with a
time window T , and xi , xj are the average of the returns of the action i and j
in that time window. The author used T = 15.
    For each t we can compute the persistent homology of the correlation graph
at time t and obtain information about its topology. The author computed
the persistent homology in dimensions 0 and 1. His results showed how there
was less correlation between stocks before the 2008 financial crash, and the
correlation between stocks increased days before the crisis. This was quantified
with the Wasserstein distances between the 0-dimensional persistence diagrams
at time t and at an initial time t0 . In this time series of distances, the author
found greater oscillations days before the crash, thus having signs of the critical
transition.

3.2     Persistence landscapes of financial crashes
M. Gidea and Y. Katz in [12] studied the daily returns of the S&P500, the
DJIA, NASDAQ, and the Russel 2000 —the 4 major financial indices in the
United States— during the technology crash of 2000 and the financial crisis
of 2008. Each 1-dimensional time series together form a 4-dimensional time
series. The authors used persistent homology to detect topological patterns in
this multidimensional time series. Persistence landscapes and their norms Lp ,
p = 1, 2, were used to measure changes in 1-dimensional persistence diagrams.
In their results, they found that the Lp norms have grown considerably days
before the two crashes, while the norms behave calmly when the market is stable.
The methodology they used is described below.
    Let {xkn }n , k = 1, . . . , d, be d time series and let us fix a window size w. For
each time tn , we have a point x(tn ) = (x1n , . . . , xdn ) ∈ Rd . Let us consider the
matrix
                     Xn := [x(tn )T , x(tn+1 )T , . . . , x(tn+w−1 )T ]
of size d × w, which represents a cloud of w points in Rd . Then, we obtain
a filtering of Rips simplicial complexes to obtain the persistence diagram of
dimension 1 and then its associated persistence landscape together with its
norm L1 and L2 . This is done for each time tn , obtaining a time series of the
norms of persistence landscapes that tracks changes in the topological properties
of each point cloud Xn over time.
    The authors applied the methodology described before to the daily log-
returns of the S&P500, the DJIA, the NASDAQ, and the Russel 2000 from
December 23, 1987, to December 8, 2016 (7301 daily data). Their results
showed more persistent 1-cycles emerging in the point clouds when there is
more volatility in the market. To quantify this behavior, the L1 and L2 norms
of the persistence landscapes were computed for each point cloud. The set of


                                             8
values obtained induces a daily time series with these quantities and found these
norms grow when periods of high volatility in the markets approach, such as the
crash of 2000 and 2008. To see the variability of both time series, the author
proceeds to calculate the 500-day moving variance. As expected, the time series
of the moving variance also grows closer to both financial crashes.

3.3    Crashes in cryptocurrency market
In [11], M. Gidea et al. analyzed the time series of four of the most important
cryptocurrencies: Bitcoin, Ethereum, Litecoin, and Ripple —which made up 66
% of the total cryptocurrency market capitalization— using a similar approach
to [12]. The difference between both approaches is that the methodology of
[11] was applied to a specific time series, while in [12] the methodology was
applied to d time series. Furthermore, [11] took into account what they define
as the C 1 norm of persistence landscapes and used the k -means algorithm of
machine learning, which is a clustering algorithm, to identify patterns in prices
and the C 1 norms indicating critical transitions before the cryptocurrency crash
in January 2008, which started with a Bitcoin price drop of 65%.
    The methodology of [11] was the following. Let us consider a time series
X = {x0 , . . . , xN −1 } and set d ∈ N. Let

                           zt := (xt , xt+1 , . . . , xt+d−1 ) ∈ Rd ,

for t ∈ {0, . . . , N − d}. We now have a sequence of point clouds in Rd

          Z t := {zt , zt+1 , . . . , zt+(w−1) },   t ∈ {0, . . . , N − d − w + 1},

where w is the size of a rolling window (the number of points in each cloud).
This association between the time series and the sequence of point clouds is
known as the time-delay coordinate embedding or Takens’ embedding,
which is inspired by Takens’ theorem (see [19]).
    Let us fix t ∈ {0, . . . , N − d − w + 1} and consider the point cloud Z t .
We obtain a filtration of Vietoris-Rips simplicial complexes to obtain the 1-
dimensional persistence diagram, its persistence landscape λt , and the norm L1
of this latter. In this way, we obtain a time series {||λt ||1 }t .
    To detect the cases when ||λt ||1 is large or when there are large jumps be-
tween ||λt ||1 and ||λt−1 ||1 , the authors define the norm C 1 of the persistence
landscape λt as
                       ||λt ||C 1 = ||λt ||1 + |||λt ||1 − ||λt−1 ||1 |,
which is a definition motivated by the C 1 norm of differentiable functions. No-
tice that || · ||C 1 is not a norm but just a quantity to identify the patterns of
||λt ||1 of interest.
     This series of steps were applied to the daily log-returns of Bitcoin, Ethereum,
Litecoin, and Ripple from September 14th, 2017, until the most significant pre-
vious peak to the critical transition in each cryptocurrency. They took d = 4
and w = 50 in their experiments.


                                                9
    The k-means algorithm was applied to the points {(xt , yt )}t , where xt is the
logarithm of the price at time t of a cryptocurrency and yt = ||λt ||C 1 is the
norm C 1 of the persistence landscape λt . Both time series {xt }t and {yt }t were
scaled to the interval [0, 1] prior to this algorithm. k was chosen using the elbow
method q
    A cluster given by the k -means algorithm was defined as a early warning
signal if the cluster contained points (xt , yt ) with yt > 0.5 and the times t
formed an almost contiguous time interval. If most of the points have yt > 0.5,
it was a strong early warning signal; and if only a few points had yt > 0.5,
it was a weak early warning signal.
    For the cryptocurrencies Bitcoin, Ethereum and Ripple, early warning sig-
nals were obtained prior to the crashes of each cryptocurrency, while for Litecoin
the methodology did not work and obtained a false positive. The authors tested
their methodology with 8 other different time series, and only 2 had false posi-
tives. This indicates to us that it would be worthwhile to research further into
the reliability of this methodology to detect early signs of critical transitions in
financial markets.
    This article was published in May 2019 by Elsevier, and the author men-
tioned that [10], [12], and [22] were the few research papers about TDA for
financial data analysis. The major advantage of studying critical transitions in
financial markets with TDA is that it is free of statistical assumptions in the
time series.


4    Investing strategies based on a TDA indicator
In the financial asset management industry, it is known that turbulent periods
in financial markets are characterized by low returns, high volatility, and the
correlation between assets increases. This makes diversification —the golden
rule in investing — not working as it should. Recall that diversification is
an investment strategy made up of a portfolio with a wide variety of distinct
investment vehicles (not putting all the eggs in one basket).
    One way to deal with turbulent periods while investing is the estimation of
the dynamic regime of financial markets —the behavior that the market has
over time— or the creation of risk indicators that predict changes in the market
regime. Both approaches allow us to create investment strategies with low risk
and a higher return compared to the buy-and-hold strategy [1].
    [1] designed three investment strategies via a persistent-homology-based tur-
bulence index (PHTI) they created. In their research, they simulated these
strategies using the PHTI index, the VIX index, and the [6] index based on the
Mahalanobis distance —the two latter being known turbulence indices. The
authors found that the PHTI-based strategies were better according to some
performance measures described later.
    The PHTI is constructed as follows. Let us fix N industrial portfolios and
consider a rolling window of 60 trading days. This leads to a N -dimensional
point cloud of size 60 where each point represents the daily returns of the N


                                        10
industrial portfolios in some day. Then, we obtain the 1-dimensional (or 0-
dimensional) persistence diagram via a Vietoris-Rips simplicial complex filtra-
tion.
    Moving the rolling window, we obtain a set of persistence diagrams {Pt }t ,
and then construct a sequence {Wt }t , where Wt is the Wasserstein distance
between Pt and Pt−1 . {Wt }t is called the PHTI raw index. The sequence
{Wt }t is smoothened with a moving average of 60 days and gives rise to the
PHTI index {wt }t :
                                       59
                                    1 X
                              wt =        Wt−j .
                                   60 j=0

    [1] took into account in the investment strategies the last 60 monthly values
of the PHTI. Depending on which quintile the last value falls into, it was the
total value of equity in the S&P500. The following were the three investment
strategies the authors designed:
  1) Protection against extreme values of the index. Investing of the
     100 % during the following month unless the last value falls into the last
     quintile. In this last case, do not invest anything in that month.

  2) Flexible exposure. If the last value falls in the n -th quintile, n ∈
     {1, 2, . . . , 5}, then invest the (100 − 20(n − 1)) % of equity (100 %, 80 %,
     60 %, 40 % and 20 % for n = 1, 2, 3, 4, 5, respectively).
  3) Exposure with leverage. Leverage allows us to use debt to increase
     the amount of money for investment. If the last value falls into the n -th
     quintile, n ∈ {1, 2, . . . , 5}, then invest the (120 − 5n(n − 1)) % of equity
     (120 %, 110 %, 90 %, 60 % and 20 % for n = 1, 2, 3, 4, 5, respectively).
    [1] called this methodology the 60-60-60 rule because of the rolling window
size, the moving average, and the 60 monthly values of wt considered for the
investment strategies. For the other two turbulence indices, the 60-60-60 rule
was adapted.
    The authors in their simulations used N = 10 and N = 30 industrial portfo-
lios from different sectors to represent the general market situation. We denote
the PHTI that uses the 10 and 30 portfolios as PHTI(10) and PHTI(30), re-
spectively. Analogously with the index of [6], denoted here by Chow(10) and
Chow(30). This leads to 5 different turbulence indices: PHTI(10), PHTI(30),
Chow(10), Chow(30) and VIX. Each of these indices can be used for the 3 dif-
ferent investment strategies described. These strategies were tested from June
1991 to June 2019, encompassing 337 monthly returns of the S&P500, and were
compared to the buy-and-hold strategy as benchmark.
    The authors used, as performance measures for any investment strategy, the
mean annualized return µ, the mean annualized standard deviation of returns σ,
the annualized Sharpe ratio SR (Sharpe ratio, quotient between the two previous
measures), and the maximum drawdown maxDD (maximum drop experienced
in the portfolio since the last maximum until this maximum is exceeded again).


                                       11
                 Protection against extreme index values
           Benchmark PHTI(10) PHTI(30) Chow(10) Chow(30)                  VIX
   µ          8.55         8.94       8.87      7.27      6.35             5.49
   σ         14.18        10.74      10.84     11.92     11.77            10.04
  SR          0.60         0.83       0.82      0.61      0.54             0.55
 maxDD       52.56        33.42      33.42     41.09     44.43            39.47


                              Flexible exposure
           Benchmark     PHTI(10) PHTI(30) Chow(10)          Chow(30)     VIX
   µ          8.55         5.99         5.96     4.58          4.60        5.10
   σ         14.18         8.32         8.53     9.02          8.81        7.98
  SR          0.60         0.72         0.70     0.51          0.52        0.64
 maxDD       52.56        24.75        26.43    35.98         35.97       35.00


                          Exposure with leverage
           Benchmark     PHTI(10) PHTI(30) Chow(10)          Chow(30)     VIX
   µ          8.55         8.12      8.28       6.46           6.31        6.26
   σ         14.18        10.82     11.26      11.82          11.68       10.18
  SR          0.60         0.75      0.74       0.55           0.54        0.62
 maxDD       52.56        33.15     33.28      44.08          45.06       43.52

Table 1: Performance measures of the different investment strategies with the
different indices. PHTI(10) and PHTI(30) are the persistent-homology-based
indices that showed better Sharpe Ratios and lower maximum drawdowns.



    In table 1, the 4 performance measures are reported. We can see that the
PHTI(10) and the PHTI(30) are the indices that showed better Sharpe Ra-
tios and lower maximum drawdowns in the 3 different strategies. In addition,
they also perform better than the benchmark with respect to Sharpe Ratio and
maximum drawdown. So the PHTI has the potential to be a good turbulence
index.




                                     12
                        List of parameter variations
    parameter         d         τ      w           T                   dimension
      values     3, 4, 5, 10 1, 2, 5 30, 60 1, 5, 15, 30, 60              0,1

Table 2: Values given to the different parameters required to compute the tur-
bulence index

5     A new version of Persistent Homology Based
      Index
Combining ideas of [1, 11, 12], we propose another turbulence index based on
persistent homology. The construction is the following. Let {xt }t be a time
series of the log-returns of some financial asset. Through Takens’s embedding,
we obtain a set of d-dimensional points

                      zt := (xt , xt+τ , . . . , xt+τ (d−1) ) ∈ Rd ,

where τ is called the time delay of the embedding. This is a deviation from
[11], the authors only considered τ = 1 and d = 4. We decided to try with more
values, in this case, we tried with τ = 1, 2, 5 and d = 3, 4, 5, 10 (see Table 2 ).
    Because of the time cost of the experiments we could only afford up to five
values per parameter. We tried to keep the values used in [1, 11] plus some
other parameters similar to detect the sensitivity of the parameters, and one or
two other options further away (see Table 2).
    With a window of w trading days, for each t we get a point cloud in Rd

                         Z t := {zt , zt+1 , . . . , zt+(w−1) },

and obtain the 0-dimensional and 1-dimensional persistence diagrams and their
persistence landscapes. Let {λt }t be the time series of persistence landscapes
obtained. Following [1, 11] ideas, we track the L2 -distances between the persis-
tence landscapes λt and λt−T :

                     Mt := ||λt−T − λt ||2 ,      for each t ≥ T.

    In [1, 11], the authors used T = 1, but here we experimented with other
values of T ; we mainly used T = 1, 5, 15, 30, 60 to compare persistence land-
scapes between a trading month or two of difference. We used w = 30, 60 just
to check if moving from a month of data to two months can make the index
more sensitive.
    In summary, we obtain an index I(d,τ,w,T,dim) ({xt }t ) = {Mt : N > t > T }
that depends on five parameters: d, τ, w, T and, the homology dimension dim
(0 or 1); the exact values considered are shown on Table 2.
    We tested our turbulence index on daily log-returns of the following datasets:
    • S&P500: It is a stock market index that tracks the stock performance of
      500 large companies listed on stock exchanges in the United States.


                                           13
Figure 2: The 2-dimensional PCA projection of the 240 turbulence indices near
COVID crash (February 20, 2020). Indices within a cluster are colored the
same; pink dots represent the cluster’s centroids.


   • Russel 2000: It is a small-cap stock market index made up of the smallest
     2,000 stocks in the Russell 3000 Index (benchmark of the entire U.S. stock
     market).
   • S&P/BMV IPC: Weighted measurement index of 35 stocks traded on the
     Bolsa Mexicana de Valores (Mexican stock exchange).
   • Nikkei 225: Stock market index for the Tokyo stock exchange (TSE).

    We decided to analyze S&P500 and Russel 2000 to be able to compare our
results with those in [12]; with the difference that they studied the technology
crash of 2000. Also, as we want our turbulence index to be sensitive in a
more robust way, we decided to include other stock datasets to remove different
biases that working with only one dataset might bring. We included Nikkei and
S&P/BMV IPC to help us remove some bias against location and economy size.
    As we want our turbulence index to be able to detect early warning signals
of financial crashes, we focused first on adjusting the index to the 2020 stock
market crash on February 20, 2020, due to the COVID-19 pandemic, when a
price drop of 33% started until March 23. We computed a total of 240 variations
of the turbulence index

                      {I(d,τ,w,T,dim) (dataset)}(d,τ,w,T,dim)

near COVID-19 market crash (14 months before and 3 months after February 20,
2020), where (d, τ, w, T, dim) varies over each option in Table 2 and dataset can
be any log-returns time series of the four datasets mentioned above (S&P500,
Russel 2000, S&P/BMV IPC, Nikkei 225); a total of 240 × 4 = 960 time-based
indices.
    These indices differ a lot from one another, as it is shown in Figure 2.
These plots were built cropping all indices I(d,τ,w,T,dim) (dataset) to the same
length and normalizing them to compare their shape and finally taking the two-
dimensional PCA projections of the resulting series. As we can observe, some
indices are pretty close, but many are far away. Different parameter configura-
tions create different pattern shapes.


                                        14
Figure 3: The graph of each turbulence-indices cluster’s centroid computed
through K-means. Each color corresponds to a cluster of the same color in
Figure 2. The right y-axis corresponds to the price (graph in green) of the cor-
responding financial time series, while the left y-axis corresponds to the values
of the turbulence index. The red-dotted-vertical lines represent the beginning
of the COVID crash, i.e., February 20, 2020.


    It is natural to ask what parameter configuration better captures the risk of
market crashes. To get a comprehensive description of the possible shapes of
I(d,τ,w,T,dim) (dataset), we computed the K-means algorithm over all the normal-
ized indices. We used the elbow rule for each dataset to decide the number of
clusters to run K-means into. The final clusters are shown in Figure 2; the cen-
troids of the clusters are shown in Figure 3, which serve as a nice representative
index of each cluster.
    We believe that the most desired shape for a turbulence index that detects
a financial crash is one with a prominent peak close to the beginning of the
prices’ fall and that remains stable in non-turbulence times. For each of the
centroids depicted in Figure 3 we chose the one that has that desired shape.
This was the centroid 0 for S&P500, Russel 2000, and Nikkei 225; and the
centroid 3 for S&P/BMV IPC; we call these selections the ‘good’ centroids and
the corresponding clusters the ‘good’ clusters. There were only 14 parameter
configurations c = (d, τ, w, T, dim) such that Ic (dataset) was in the good cluster
for all datasets. For each of them, we computed its distance from the good
centroid; we show the result in Table 3.
    To test if the configurations from Table 3 are good at alerting from possible
crashes in general, we tried them in a completely different set of past crashes.
We worked with the following events:
   • Black Monday crash (see [2] ) that occurred on October 19, 1987.
   • The dot-com bubble from the late 90s when many online companies failed


                                        15
                              Best configurations
  (d, τ, w, T, dim)     S&P500   Russel 2000 S&P/BMV IPC           Nikkei 225
  (4, 2, 60, 5, 0)     0.358248   0.435222        0.422185          0.395897
  (5, 2, 60, 5, 0)     0.325145    0.432211      0.458128           0.391419
  (10, 1, 60, 5, 0)    0.243123    0.394079       0.410875         0.473084
  (3, 1, 60, 5, 0)     0.372211   0.486730        0.393950          0.471953
  (3, 5, 60, 5, 0)     0.264082    0.425575      0.505006           0.365352
  (10, 1, 60, 1, 0)    0.422799    0.415909       0.438392         0.509998
  (10, 2, 60, 1, 0)    0.596849    0.509674       0.551878          0.500585
  (5, 1, 60, 1, 0)     0.620979   0.627667        0.531569          0.607321
  (4, 1, 60, 1, 0)     0.621053    0.637028       0.593142         0.642688
  (5, 2, 60, 1, 0)     0.682100    0.630856       0.569481          0.600423
  (3, 1, 60, 1, 0)     0.696283    0.622632       0.617384          0.652061
  (4, 2, 60, 1, 0)     0.707310    0.660973       0.514964          0.579040
  (3, 2, 60, 1, 0      0.715324    0.617745       0.644957          0.542285
  (3, 5, 60, 1, 0)     0.577607    0.570889      0.754845           0.531487

Table 3: List of parameters c = (d, τ, w, T, dim) such that Ic (dataset) appeared
as part of a good cluster for every dataset. On every column, we show the
distance from Ic (dataset) to the centroid of the corresponding cluster. We
mark in boldface the maximum value among the four distances.

                      Crashes that appear on each dataset
  Dataset/Crash         Black Monday Dot-com Bubble 07–09 Bear Market
  S&P500                      ✓             ✓              ✓
  Russel 2000                                              ✓
  S&P/BMV IPC                 ✓             ✓              ✓
  Nikkei 225                                               ✓

                      Table 4: Crash dates analyzed per dataset


     and shut down (see [13])
   • The United States bear market of 2007–08 is a 17-month period when the
     stock market lost more than 50% of its value.

    All the above crashes are very different in nature than the COVID crash.
Black Monday and dot-com are economic crashes classified as bubbles, while
the 2007-08 crash is a long fall period.
    We computed the fourteen indices given by the parameters from Table 3
on each previous crash. We used the same datasets as before but moved our
attention to a specific crash date. Not all datasets go back to 1987; Table 4
shows what crash dates appear on each dataset.
    To present a general idea of the behavior of these fourteen indices, we com-
puted the average index among the fourteen normalized indices. In Figure 4,
we see the plots of the resulting average index per crash event and dataset from


                                         16
Figure 4: The average index of the fourteen normalized indices given by the
parameters from Table 3 per crash event and dataset from Table 4. The right
y-axis corresponds to the price graph in green of the corresponding financial time
series, while the left y-axis corresponds to the values of the average index in blue.
The red-dotted-vertical lines represent the beginning of the corresponding crash.


Table 4.
    We can observe that for all events except two, the average index shows a
prominent peak after the crash started, being the Black Monday on the S&P500
dataset the one on which the peak fires closer to the actual crash. Observe that,
in general, the position of the peaks is parallel to a sudden drop in prices, which
leads us to believe that the proposed index is sensitive to this behavior.
    Cases like the dot-com crash in S&P500 dataset have a peak that is not as
prominent as the ones that occurred before and after, which can be explained
by the fact that dot-com crash is a slow drop that occurred during two years
[13]. In our experiments, the index only looked at the prices up to two months;
so, if we want to improve the sensitivity to slow drops, we must increase the
sliding window size W . A similar phenomenon can be observed in the 2007-08
crash on all the datasets. The index fires a peak only after a year when a sudden
drop happened.


                                         17
    All code and data we used can be found in a GitHub repository [18].


6     Conclusions
We reviewed some efforts that have been made to understand financial mar-
kets via TDA [10, 12, 11, 1], and proposed a new turbulence index based on
persistence landscapes of 0 and 1-dimensional persistence diagrams. In our ex-
periments, we found that this index shows prominent peaks near sudden price
drops in financial time series caused by market crashes. The calculations of the
persistent homology were done using the TDA Python library Giotto-TDA [20].
Applications of TDA on financial markets were in their early stages of develop-
ment at the time this research was done, as [11] mentioned. Those applications
have been focused on detecting early warning signals of critical transition in
financial markets (crashes of markets). The results are promising and indicate
that there is room for collaboration between academic research and the financial
industry to explore TDA insights into financial markets.


Acknowledgements
This research was undertaken as part of a research fellowship given by CONAH-
CyT through the ‘Sistema Nacional de Investigadores’ sponsored by Profes-
sor José-Carlos Gómez-Larrañaga (CIMAT-Mérida). Professor Jesús Rodrı́guez
Viorato is part of the program Investigadores por México from CONAHCyT.


References
 [1] Eduard Baitinger and Samuel Flegel. The better turbulence index?
     forecasting adverse financial markets regimes with persistent homology.
     Forecasting Adverse Financial Markets Regimes with Persistent Homology
     (November 20, 2019), 2019.
 [2] David S. Bates. The crash of 87: Was it expected? the evidence from
     options markets. The Journal of Finance, 46(3):1009–1044, 1991.

 [3] Jesse Berwald, Marian Gidea, and Mikael Vejdemo-Johansson. Automatic
     recognition and tagging of topologically different regimes in dynamical sys-
     tems. arXiv preprint arXiv:1312.2482, 2013.
 [4] Peter Bubenik. Statistical topological data analysis using persistence land-
     scapes. The Journal of Machine Learning Research, 16(1):77–102, 2015.

 [5] Gunnar Carlsson. Topology and data. Bull. Amer. Math. Soc. (N.S.),
     46(2):255–308, 2009.




                                       18
 [6] George Chow, Eric Jacquier, Mark Kritzman, and Kenneth Lowry. Optimal
     portfolios in good times and bad. Financial Analysts Journal, 55(3):65–73,
     1999.
 [7] David Cohen-Steiner, Herbert Edelsbrunner, and John Harer. Stability of
     persistence diagrams. Discrete & computational geometry, 37(1):103–120,
     2007.
 [8] Herbert Edelsbrunner and John Harer. Persistent homology - A survey.
     Contemporary mathematics, 453:257–282, 2008.
 [9] Herbert Edelsbrunner and John Harer. Computational topology - an intro-
     duction. American Mathematical Soc., 2010.
[10] Marian Gidea. Topological data analysis of critical transitions in financial
     networks. In International Conference and School on Network Science,
     pages 47–59. Springer, 2017.
[11] Marian Gidea, Daniel Goldsmith, Yuri Katz, Pablo Roldan, and Yonah
     Shmalo. Topological recognition of critical transitions in time series of
     cryptocurrencies. Physica A: Statistical Mechanics and its Applications,
     page 123843, 2020.
[12] Marian Gidea and Yuri Katz. Topological data analysis of financial time
     series: Landscapes of crashes. Physica A: Statistical Mechanics and its
     Applications, 491:820–834, 2018.
[13] Nate Lanxon. The greatest defunct web sites and dotcom disasters. CNET,
     2009.
[14] Alexander J McNeil, Rüdiger Frey, and Paul Embrechts. Quantitative risk
     management: concepts, techniques and tools-revised edition. Princeton uni-
     versity press, 2015.
[15] Nina Otter, Mason A Porter, Ulrike Tillmann, Peter Grindrod, and
     Heather A Harrington. A roadmap for the computation of persistent ho-
     mology. EPJ Data Science, 6:1–38, 2017.

[16] Jose A Perea and John Harer. Sliding windows and persistence: An appli-
     cation of topological methods to signal analysis. Foundations of Computa-
     tional Mathematics, 15(3):799–838, 2015.
[17] Nalini Ravishanker and Renjie Chen. Topological data analysis (TDA) for
     time series. arXiv preprint arXiv:1909.10604, 2019.

[18] Miguel Ruiz. Tda financial markets. https://github.com/miguelruor/
     TDA_financial_markets, 2022.
[19] Floris Takens. Detecting strange attractors in turbulence. In Dynamical
     systems and turbulence, Warwick 1980, pages 366–381. Springer, 1981.


                                       19
[20] Guillaume Tauzin, Umberto Lupo, Lewis Tunstall, Julian Burella Pérez,
     Matteo Caorsi, Anibal Medina-Mardones, Alberto Dassatti, and Kathryn
     Hess. giotto-tda: A topological data analysis toolkit for machine learning
     and data exploration, 2020.
[21] Robert R Trippi and Jae K Preface By-Lee. Artificial intelligence in fi-
     nance and investing: state-of-the-art technologies for securities selection
     and portfolio management. McGraw-Hill, Inc., 1995.
[22] Patrick Truong. An exploration of topological properties of high-frequency
     one-dimensional financial time series data using tda, 2017.




                                      20