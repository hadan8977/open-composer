source: https://arxiv.org/pdf/2405.16052
fetched_utc: 2026-10-04T18:37:29Z
bytes_raw: 941540

Identifying Extreme Events in the Stock Market: A Topological Data Analysis
                                                     Anish Rai,1, a) Buddha Nath Sharma,1, b) Salam Rabindrajit Luwang,1, c) Md.Nurujjaman,1, d) and Sushovan
                                                     Majhi2, e)
                                                     1)
                                                          Department of Physics, National Institute of Technology Sikkim, Sikkim, India-737139.
                                                     2)
                                                          Data Science Program, George Washington University, USA, 20052.
                                                     This paper employs Topological Data Analysis (TDA) to detect extreme events (EEs) in the stock market
                                                     at a continental level. Previous approaches, which analyzed stock indices separately, could not detect EEs
                                                     for multiple time series in one go. TDA provides a robust framework for such analysis and identifies the EEs
                                                     during the crashes for different indices. The TDA analysis shows that L1 , L2 norms and Wasserstein distance
                                                     (WD ) of the world leading indices rise abruptly during the crashes, surpassing a threshold of µ + 4 ∗ σ where
                                                     µ and σ are the mean and the standard deviation of norm or WD , respectively. Our study identified the stock
                                                     index crashes of the 2008 financial crisis and the COVID-19 pandemic across continents as EEs. Given that
                                                     different sectors in an index behave differently, a sector-wise analysis was conducted during the COVID-19
arXiv:2405.16052v1 [q-fin.ST] 25 May 2024




                                                     pandemic for the Indian stock market. The sector-wise results show that after the occurrence of EE, we have
                                                     observed strong crashes surpassing µ + 2 ∗ σ for an extended period for the banking sector. While for the
                                                     pharmaceutical sector, no significant spikes were noted. Hence, TDA also proves successful in identifying the
                                                     duration of shocks after the occurrence of EEs. This also indicates that the Banking sector continued to face
                                                     stress and remained volatile even after the crash. This study gives us the applicability of TDA as a powerful
                                                     analytical tool to study EEs in various fields.

                                            Extreme events (EEs) are rare, unexpected occurrences that stand out significantly from normal
                                            happenings. These can include events like floods, heart attacks, power blackouts, and stock market
                                            crashes. For instance, the 2008 financial crisis and the COVID-19 pandemic caused massive stock
                                            market crashes worldwide, leading to significant financial losses for investors. Identifying and analyzing
                                            these extreme events is essential. One effective method for detecting EEs is topological data analysis
                                            (TDA), which can analyze multiple time-series data simultaneously. Using TDA-based norms and
                                            Wasserstein distance, we can identify EEs in stock markets across different continents. Additionally,
                                            we can conduct a sector-wise analysis to understand how various sectors were differently impacted
                                            during the COVID-19 pandemic based on their future outlook.



                                            I.   INTRODUCTION

                                               The stock market has witnessed various crashes starting from the great depression of 1929, the 1987 crash, the tech
                                            bubble of 2000, the 2008 financial crisis, and the latest COVID-19 pandemic1–5 . During these crashes, investors lost
                                            significant capital due to the panic sell-off caused by irrational decisions6–8 . However, the same crashes have provided
                                            opportunities for investors to make huge profits7 . Due to the huge risk and opportunity, the study of crash dynamics
                                            in the stock market is significant.
                                               An extreme event (EE) is identified by the abrupt occurrence of unusual events9,10 . EEs can happen in technological,
                                            social, and natural contexts9 . They could originate naturally or due to human activity11 . Previously, floods, power
                                            blackouts, earthquakes, heart attacks, stock market crashes and upsurges were referred to as EEs.10,12,13 . The study
                                            of EEs in different fields is important as the impact of these events is severe. There has been very limited work in the
                                            stock market in terms of the identification of EEs10,13 .
                                               Mahata et al.10 recognized the stock price crash caused by the COVID-19 pandemic as an EE in different companies
                                            and indices. The analysis of each time series is carried out separately. The author applied the Empirical Mode
                                            Decomposition (EMD) based Hilbert–Huang transform (HHT) to identify EEs. The EMD-based HHT has been
                                            widely used to understand the stock market dynamics14,15 . Further, Rai et al.13 also identified the different factors
                                            leading to positive and negative EEs in different stocks using the EMD-based HHT. In these analyses, the authors
                                            have identified EE considering each stock price time series individually. However, when dealing with multiple time
                                            series, this method becomes impractical. Hence, we need a more convenient approach to analyze several time series
                                            simultaneously. That’s where Topological Data Analysis (TDA) comes into play.


                                            a) Electronic mail: anishrai412@gmail.com
                                            b) Electronic mail: bnsharma09@yahoo.com
                                            c) Electronic mail: salamrabindrajit@gmail.com
                                            d) Electronic mail: md.nurujjaman@nitsikkim.ac.in
                                            e) Electronic mail: s.majhi@email.gwu.edu
                                                                                                                       2

   TDA attempts to solve data science problems using tools from algebraic topology and geometry16,17 . The idea
behind employing TDA in our investigation is to extract the “shape” of a multi-dimensional time-series dataset.
Using a fixed window of time, we first convert the slice of the time series into a Euclidean point cloud. Further,
a topological signature—known as persistent homology—of the point cloud is computed. Now, as the slice moves
along the time series, the evolution of the signature is then studied and analyzed18 . One of the key advantages of
using persistent homology is its robustness under small, random perturbations of the data points. In contrast to
other techniques that consider each time series separately, TDA allows us to analyze multiple time series at once in a
complete and insightful manner—hence providing a more efficient and accurate identification of EEs. TDA has been
successfully applied to problems in a growing number of fields, such as material sciences19,20 , 3D shape analysis21 ,
multivariate time-series analysis22 , biology23 ,medicine24 , chemistry25 , network sensors26 , early warning systems for
flood27 . Recently, TDA has also lent itself to analyzing the stock market crash dynamics. Some of the pivotal and
relevant developments in this direction are discussed below.

    • The study of M. Gidea28 detected early signs of a critical transition by tracking the topological changes when
      approaching a critical transition. The study analyzed the cross-correlation network of daily returns of the
      stocks under the Dow Jones Industrial Average index (DJIA). Likewise in Ref.29 , the evolution of log returns of
      four major stock market indices—S&P 500, DJIA, NASDAQ, and Russell 2000—was studied using persistent
      homology. In particular, it was observed that the Lp -norms of the persistence landscape showed strong growth in
      the vicinity of financial meltdowns. In addition to the four major US indices, Alejandro Aguilar et al.30 studied
      ten ETF sectors between January 2010 and June 2020 using algebraic topology and persistent homology. They
      studied the evolution of the Lp -norms over time to detect critical transitions in the daily log returns. The
      topological structures exhibited a significant change in behavior during the crash period.

    • Guo et al.31 analyzed the L1 and L2 norms during the 2008 crash in different regions. They observed a “high-
      level period” in norms before the crash. The market crash of 2020 in the Straits Times Index and Taiwan
      Capitalization Weighted Stock Index (TAIEX) was studied using TDA by Peter Tsung-Wen Yen et al.32 . They
      studied the changes in the first three Betti numbers: β0 , β1 , and β2 during market crashes. They observed that
      β0 is small at the beginning of a market crash and increases as the market crash progresses. In a related work33 ,
      TDA was used to study the market crash in the Taiwan Stock Exchange (TWSE). The study found that the
      number of simplices grows gradually with increasing filtration parameters six months before the market crash,
      and grows swiftly near the crash.

    • Further, the persistence landscape was applied to perform enhanced indexing34 . Moreover, TDA was applied to
      cluster time-series models by their topological similarity and classification of the simulated dataset. This work
      provided evidence that stock price movements are sector-dependent35 . In addition, a method that combines
      TDA with machine learning was used to understand the dynamics before a critical transition36 . The authors
      applied Taken’s theorem to estimate the persistence landscapes from Bitcoin time-series data. The so-called
      ‘Topological Tail Dependence Theory’ was also proposed to bridge the gap between the mathematical theory
      of persistent homology and the financial stock market theory37 . The study found that incorporating persistent
      homology information systematically improves the forecasting accuracy of models, especially during turbulent
      periods. It also showed that the 2D Wasserstein distance is statistically significant for linear models.

    • Forty indices from forty countries/regions were analyzed through the persistence landscapes and their Lp -
      norms38 . It was found that the connections between the stocks became closer and the norms were at the lower
      levels around the financial crises. In a related study, 100 stocks from the Chinese Stock market were analyzed
      from 2013 to 202039 . Through the strong correlation between the stocks, they found three turbulent periods in
      the time analyzed.

.
   Although a significant amount of study has already been carried out in the stock market using topology-inspired
techniques, no work has yet identified the stock market crashes as an extreme event (EE) using TDA. Moreover, to
the best of our knowledge, our analysis of the impact of different crises across continents and sectors is the first in
the line. In our work, we have analyzed the crashes due to the 2008 financial crisis and COVID-19. These crashes
are identified as EE using the TDA technique. During the COVID-19 pandemic, sectors were impacted differently
based on their future outlook40 . Therefore, sector-wise analysis during the COVID-19 is important to understand
their dynamics. Also, TDA is being applied for the first time for the identification of EEs. Mahata et al.10 and Rai
et al.13 have quantified EE in the stock market when the energy surpasses a particular threshold, i.e., Eµ + 4 ∗ σ. In
our analysis, we have applied the Wasserstein distance (WD ) and the Lp -norms of the persistent homology to detect
the EE. The WD and the Lp -norms show an abrupt rise during stock market crashes. We have defined a threshold
                                                                                                                             3

surpassing which the event is identified as an EE. To further verify the robustness of our results, we have applied the
EMD-based HHT with the results obtained from TDA.
  The structure of our paper is as follows. Section II explains the methodology employed in the paper and Section III
contains the TDA approach to analyzing time series. Section IV contains the data analyzed. In section V we have
discussed our results and Section VI contains the conclusion of the work.


II.   METHODOLOGY

A.    Topological Data Analysis

  Topological data analysis (TDA) allows us to extract robust topological features from noisy datasets. One of the
advantages of using TDA is its robustness, i.e., the output doesn’t change under small perturbations29 . In our work,
we use Persistent homology which is a powerful tool in TDA, that provides a quantitative representation of how the
shape and connectivity of data evolve as the resolution (ε) increases41 .
  Sections II A 1– II A 4 contain the definitions and notations from persistent homology used in the paper.


1.    Vietoris–Rips Complexes

   To apply persistent homology, we start with a point cloud dataset, X, represented by a set of points in the d-
dimensional Euclidean space Rd . For ε > 0, we associate a simplicial complex to the dataset using the Vietoris–Rips
complex (also known as the Rips complex), denoted by R(X, ε). The Vietoris–Rips complex captures the connectivity
of the data points at different ε. Although the Vietoris–Rips complex can be defined in a more general setting, we
introduce the concept here in the context of Euclidean point clouds. A subset {x0 , x1 , . . . , xk } of X with (k + 1) points
forms a k-simplex in R(X, ε) if all pairwise distances ∥xi − xj ∥ are at most ε. Roughly speaking, it represents a set
of (k + 1) data points that are indistinguishable from each other at ε29,37,42 .
   The Vietoris–Rips complexes form a filtration, meaning that as we increase the value of ε, the simplicial complexes
include more and more simplices42,43 . For each complex in the filtration, we can compute its k-dimensional homology
Hk (R(X, ε)) with coefficients in some field. The homology groups capture the different dimensional topological
features present in the dataset at each ε. For example, the 0-dimensional homology group H0 (R(X, ε)) corresponds
to the connected components, the 1-dimensional homology group H1 (R(X, ε)) corresponds to the independent loops,
the 2-dimensional homology group H2 (R(X, ε)) corresponds to the independent voids, and so on.
   For two resolutions 0 < ε1 ≤ ε2 , we can identify the birth and death of k-dimensional topological features by
examining the homomorphism induced by natural inclusion17
                                                              ι∗
                                           Hk (R(X, ε1 )) ,−−−−−→ Hk (R(X, ε2 ))

between the k-th homology groups. A non-trivial homology class in Hk (R(X, ε1 )) may disappear in Hk (R(X, ε2 ));
likewise, a new homology class may appear in the latter that is not carried by the inclusion from the former.


2.    Persistence Diagrams

   The significance of the topological features is understood through their persistence. The features that persist for
a long resolution range are called ‘significant’ and the ones dying within a short resolution range are termed ‘noisy’
features31 . The summary of the birth and death of these features with change in resolution is preserved in a two-
dimensional figure named persistence diagram. It is a plot between the birth and death coordinates, consisting of
two-dimensional points with their multiplicities. Persistence diagram Pk corresponding to the k-dimensional homology
consists of:
      • for each k-dimensional feature that is born at scale b and dies at scale d, a point p = p(b, d) ∈ R2 together with
        its multiplicity µ;
      • Pk also contains all points in the positive diagonal of R2 ; these points represent all trivial homology generators
        that are born and instantly die at every level; each point on the diagonal has infinite multiplicity.
  To develop a better understanding of Vietoris–Rips complexes and persistence diagrams through visualization, let
us consider the following set of four data points, A = {[2, 2], [2, 6], [6, 2], [6, 6]} in the two-dimensional Euclidean space.
                                                                                                                                     4

The Vietoris–Rips filtration for the above point-set are constructed at various ε and shown in Fig. 1. The points
remain isolated for a range of ε from 0 to 3.9 as shown in Figs. 1 (a) & (b). We observe that at ε = 4, all the points get
connected with√each other except the diagonal pairs as shown in Fig. 1 (c). This marks the birth of a 1-dimensional
hole. At ε = 4 2 the diagonal points also get connected forming a full polyhedron on the four points. The formation
of the polyhedron indicates the death of the 1-dimensional hole. The complex at this resolution is shown in Fig. 1
(d). The summary of the birth and death of 0- and 1-dimensional holes is represented in the persistence diagram in
Fig. 2 (a). The Persistence landscape for the 0-dimensional homology group obtained from the persistence diagram
is shown in Fig. 2 (b).




             8                                                                  8

             6                (2,6)              (6,6)                          6                (2,6)              (6,6)
  Y (unit)




                                                                     Y (unit)
             4                                                                  4

             2                (2,2)              (6,2)                          2                (2,2)              (6,2)


             0                                                                  0


                 2   0        2          4       6       8   10                     2   0        2          4       6       8   10
                                      X (unit)                                                           X (unit)

                         (a) Rips Complex at ε=1                                            (b) Rips Complex at ε=3




             8                                                                  8

             6                (2,6)              (6,6)                          6                (2,6)              (6,6)
                                                                     Y (unit)
  Y (unit)




             4                                                                  4

             2                (2,2)              (6,2)                          2                (2,2)              (6,2)


             0                                                                  0


                 2   0        2          4       6       8   10                     2   0        2          4       6       8   10
                                      X (unit)                                                           X (unit)
                                                                                                                 √
                         (c) Rips Complex at ε=4                                        (d) Rips Complex at ε = 4 2


FIG. 1: The plots represent the Vietoris–Rips complexes of a point cloud with four points at different resolutions(ε).
    The disks in blue have been added as reference, to compare the mutual distances with the particular scale.
                                                                                                                                     5




             5

             4
     Death

             3

             2

             1
                                                 H0
             0                                   H1
                 0   1   2      3    4       5
                             Birth
 (a) The plot represents the Persistence diagram. The
     blue and red points correspond to the 0- and                                 (b) Plot represents the Persistence landscape for
1-dimensional holes respectively. Dashed lines (− − −)                        0-dimensional homology group. λ0 , λ1 , λ2 represents the
            represent the positive diagonal.                                       first, second and third landscape respectively.

FIG. 2: Plot (a) represents the Persistence diagram and plot (b) represents the Persistence landscape for the data.


3.   Wasserstein Distance

  The space of persistence diagrams can be endowed with a metric structure. One commonly used metric is the
degree p-Wasserstein distance29 , denoted WD (Pk1 , Pk2 ), where Pk1 and Pk2 are two persistence diagrams at dimension
k. The distance WD (Pk1 , Pk2 ) is defined as:
                                                                                              p1
                                                                              X
                                         WD (Pk1 , Pk2 ) =     min               ∥x − ϕ(x)∥p∞                                    (1)
                                                             ϕ:Pk1 →Pk1
                                                                          x∈Pk1

where ϕ is the bijective mapping from Pk1 to Pk2 and ∥ · ∥∞ is the sup norm. This metric measures the discrepancy
between the two diagrams, taking into account the pairing of points between off-diagonal points and diagonal points.
The Wasserstein distance provides a measure of similarity between persistence diagrams and is useful for comparing
topological features across different datasets or analyzing the stability of features under perturbations.
  A key advantage of persistence homology is its robustness under small perturbations. If the underlying data
changes slightly, the corresponding persistence diagram only moves a small Wasserstein distance from the diagram of
the original data29,44 . This property makes persistence homology a valuable tool for analyzing complex systems.


4.   Persistence Landscapes and their Norms

  The metric space formed by the persistence diagrams when endowed with Wasserstein distance (P, WD ), is not
complete45 . Hence, its statistical treatment becomes inappropriate. To achieve statistical analysis, persistence dia-
grams can be modified to persistence landscapes. It provides an alternative representation of persistence diagrams,
which allows us to embed the space of persistence diagrams into the Banach space Lp (N × R), which is complete45 .
To construct a persistence landscape from a persistence diagram Pk , we associate a sequence of functions λ = (λk ),
where λk : R → [0, 1] is defined as follows:
                                                     
                                     λk (x) = k − max f(bα ,dα ) (x) | (bα , dα ) ∈ Pk .
Here, f(bα ,dα ) is a piecewise linear function defined as:
                                                         
                                                                    if x ∈ bα , bα +d
                                                                                        
                                                         x − bα ,                        ;
                                                                                      α
                                                                                   2
                                                         
                                                                           bα +dα
                                                                                        
                                         f(bα ,dα ) (x) = −x + dα , if x ∈    2    , dα ;
                                                         
                                                         0,        otherwise.
The persistence landscape λ is a sequence of functions that captures the “heights” of the piecewise linear functions
f(bα ,dα ) at each point x along the real line. The k-max denotes the k-th largest value of a function, and λk (x) = 0
                                                                                                                                      6

if the k-th largest value does not exist. Persistence landscapes form a subset of the Banach space Lp (N × R), which
consists of sequences of functions λ = (λk ), where λk : R → R for k ≥ 0. This set has a vector space structure defined
by (λ1 + λ2 )k (x) = λ1k (x) + λ2k (x) and (c · λ)k (x) = c · λk (x) for all x ∈ R and k ≥ 1. It becomes a Banach space when
equipped with the norm ∥λ∥p given by28 :

                                                                        ∞
                                                                                       !1/p
                                                                        X          p
                                                          ∥λ∥p =              ∥λk ∥p                                                (2)
                                                                        k=1

where ∥ · ∥p denotes the Lp -norm with respect to the Lebesgue measure on R. In this study, L1 and L2 norms are
used.


III.     TDA APPROACH TO ANALYZING MULTIPLE TIME SERIES

  The sequence of computational steps used in TDA to obtain Wasserstein Distance (WD ) and Lp -norm from multiple
time series is shown through a flowchart in Fig. 3.

                                                                1. Convert n time-series into point could




                                                                      2. Take sliding window of size w




                                                              3. Construct Rips Complexes for each window




                                                            4. Construct Persistence Diagram for each window




                                                                      5. Analyze Persistence Diagrams




                                                                                7 (a). Construct Persistence Landscape




                                    6. Compute Wasserstein Distance                     7 (b). Compute Lp -norm


                    FIG. 3: The flowchart represents our TDA approach to analyzing multiple time series.

   The detailed description of this flowchart is presented below:
       1. Consider n number of time series, each length l. For the j-th time interval, the n time series form a point
          (X1,j , X2,j , . . . , Xn,j ) in Rn . Considering all such points for j = {1, 2, . . . , l}, we get an n-dimensional Euclidean
          point cloud
                                                                                              l
                                                    D = {(X1,j , X2,j , . . . , Xn,j )}j=1 ⊂ Rn .

       2. We fix a sliding window of size w to consider only a subset of the point cloud D at a time.
       3. For each position of the window, we construct the Vietoris–Rips filtration across various scales (ε).
                                                                                                                                    7

        4. The birth and death of 0- and 1-dimensional holes are recorded in a persistence diagram for each window. We
           get a total of l − w persistence diagrams for different window positions.

        5. The persistence diagrams obtained in the above step can be analyzed using various metrics like WD and Lp -norm.

        6. The WD between consecutive persistence diagrams are calculated using Eq. 1. WD compares the topological
           similarity in two persistence diagrams and its evolution can be studied to understand the dynamics of multiple
           time series considered.

        7. The persistence diagram can be further used in the following way:

               (a) Each persistence diagram is used to construct the persistence landscape.
               (b) The persistence landscape is used to calculate the L1 & L2 norms by using Eq. 2. The norms are calculated
                   for each persistence diagram and its variation with time is studied to comprehend the dynamics of multiple
                   time-series considered.


 IV.      DATA ANALYZED

    We have carried out continent-wise analysis during the 2008 financial crisis and the COVID-19 pandemic. We
 selected four major indices from each continent—North-South America, Europe, Asia, and Oceania—to identify EEs,
 focusing on these highly developed regions. We have also analyzed the impact of COVID-19 on different sectors in
 India. The sectors include pharmaceuticals, banking, metals, automobiles, and fast-moving consumer goods (FMCG).
 We have taken the companies based on their respective Nifty sector indices. We have taken the daily closing price
 from January 1, 2006 to December 31, 2010 to analyze the 2008 financial crisis and to analyze the crash due to
 COVID-19 we have taken the data from January 1, 2019 to December 31, 2022. The time duration has been chosen
 as it captures the whole crash period. The data have been obtained from Yahoo Finance Website46 . The subsequent
 sections present the results of our analysis.


 V.      RESULTS AND DISCUSSION

    This section shows the result of the identification of continent-wise extreme events (EEs) during the 2008 financial
 crisis and the COVID-19 pandemic using TDA. It allows the identification of EEs from multiple stock time series at
 once. Also, a sector-wise impact of the COVID-19 pandemic is analyzed in the Indian stock market.




        0.04


        0.03
Death




        0.02


        0.01

                                                      H0
        0.00                                          H1
               0.00   0.01    0.02      0.03   0.04
                                Birth
   (a) Persistence diagram for the point cloud. The blue
   and red points correspond to the 0- and 1-dimensional                   (b) The persistence landscape for 1-dimensional
    holes respectively. Dashed lines − − − represent the                  homology group. λ0 , λ1 , λ2 , λ3 represents the first,
                      positive diagonal.                                   second, third and fourth landscape respectively.

 FIG. 4: Plot (a) represents the Persistence diagram and plot (b) represents the Persistence landscape for point cloud
                                          obtained for North-South America.
                                                                                                                                    8

A.   Obtaining point cloud from stock price time-series

  In order to apply TDA in the stock market, we construct a point cloud from the stock price time series. We calculate
                                                                             Pi,j
the log-return of n stock price time-series of length l as Ri,j := ln Pi,j−1      , where Pm,k denotes the closing price of the
index m = {1, . . . , n} on day k ∈ {1, . . . , l}.
  By taking the log-return of all time-series on the j-th day, i.e., (R1,j , R2,j , . . . , Rn,j ), a point is formed in Rn . An n-
dimensional Euclidean point cloud {(R1,j , R2,j , . . . , Rn,j )}lj=1 is obtained by taking all such points for j = {1, 2, . . . , l},
After obtaining the point cloud, we have followed the steps discussed in Section III to estimate the WD and Lp -norms.

                            10-4                                                                                    10-5

                      1.2   (a)                                      (c)

                                                                                                                   4
           L1 Norm




                      0.6
                                                                                                                   2




                            10-4                                                                                    10-4

                            (b)                                      (d)
                       7
                                                                                                                   3
            L2 Norm




                      3.5
                                                                                                                   1.5




                                                                                                                   0
                                   Apr 07          Jul 08   Oct 09            Mar 07         May 08       Jul 09
                                            Time (Day)                                 Time (Day)


FIG. 5: Plot (a) and (b) represent the L1 and L2 norms of North-South America and plot (c) and (d) represent the
L1 and L2 norms of Europe continent, respectively. The abrupt rise in the norm values above the threshold during
                                        2008 confirms the occurrence of EE.



B.   EE due to the 2008 Financial crisis

  To identify EE, we define a threshold on WD and Lp -norms above which the event is considered as EE. The threshold
applied is µ + 4 ∗ σ, where µ and σ are the mean and standard deviation of the WD or norm values.
  Figures 4 (a) & (b) represent the Persistence diagram and its 1-dimensional Persistence landscape of North-South
America for a window size of 60. We have estimated the L1 & L2 norms of the persistence landscapes during the
2008 financial crisis. Figs. 5 (a) & (b) represent the L1 and L2 norms, respectively, of North-South America. The
black dashed lines represent the norm values, and the horizontal red and blue lines represent the threshold and the
average value of the norms, respectively. We have defined the threshold at µN + 4 ∗ σ where µN and σ are the mean
and the standard deviation of the norm values, respectively. There is a clear spike in the norm values during late
2008, shown by the green rectangular box, which corresponds with the 2008 financial crisis. Hence, we conclude that
TDA successfully detected the crash during the 2008 financial crisis in North-South America. Also, as the spike in the
norm values exceeds our predefined threshold, the crash in America due to the 2008 financial crisis can be considered
an EE.
  Similarly, Figs. 5 (c) & (d) represent the L1 and L2 norms, respectively, of Europe. A clear spike in both the norm
values is distinctly visible and corresponds with the crash due to the 2008 financial crisis. The norm values during
this period surpass the threshold value which is marked by the red horizontal line. This clearly shows that the crash
                                                                                                                                    9

in Europe due to the 2008 financial crisis is an EE. We have carried out our analysis for Asia and Oceania and we
have obtained similar results showing EE during the 2008 financial crisis.

                     (a)                                                           (b)
               0.5
                                                                            0.6




                                                                           WD
         WD




              0.25                                                          0.3




                           Jan 07          Feb 08          Mar 09                             Dec 07       Dec 08          Dec 09
                                    Time (Day)                                                          Time (Day)


FIG. 6: Plot (a) and (b) represent the Wasserstein distance (WD ) of North-South America and Europe, respectively
     from 2006 to 2010. The spike in the WD above the threshold value coincides with the 2008 financial crisis

   We also estimate the Wasserstein distance (WD ) to analyze the market dynamics during the 2008 financial crisis.
Figs. 6 (a) & (b) represent the WD of North-South America and Europe, respectively. The blue and red lines
represent the average value of the Wasserstein distance (µW ) and the threshold value. The threshold value is defined
as µW + 4∗σ, where σ is the standard deviation of the WD . The abrupt rise in the WD values surpassing the threshold
can be regarded as an EE. The threshold of L1 , L2 norms, and WD for different continents during the 2008 financial
crisis is listed in Table I. This identification of EE using TDA is consistent with the existing literature done in Ref.13 .

                                                    2008 Financial crisis                               COVID-19
                                       1                    2                             1
              Continents             L -norm              L -norm           WD           L -norm          L2 -norm           WD
                                                    −5                −4                           −5                 −4
              America                6.68 × 10            5.02 × 10         0.41         4.27 × 10        3.65 × 10          0.47
                                                    −4                −4                           −5                 −4
              Asia                   1.00 × 10            6.33 × 10         0.65         4.27 × 10        3.70 × 10          0.38
                                                    −5                −4                           −6                 −4
              Europe                 2.84 × 10            2.71 × 10         0.48         9.66 × 10        1.26 × 10          0.43
                                                    −6                −5                           −5                 −4
              Oceania                3.00 × 10            5.41 × 10         0.37         1.17 × 10        1.36 × 10          0.34

TABLE I: Table represents the threshold of L1 norm, L2 norm, and WD of different continents during the crash due
                              to the 2008 financial crisis and COVID-19 pandemic.




C.   EE due to COVID-19 pandemic

  In order to analyze the stock market dynamics during the crash due to the COVID-19 pandemic we have estimated
the L1 & L2 norms. Figs. 7 (a) & (b) represent the L1 and L2 norms, respectively, for Asia. A clear spike is observed
in both the norms during early 2020. The abrupt rise in the norm values is consistent with the stock market crash
due to the COVID-19 pandemic. The blue and red lines represent the average and threshold values, respectively.
As the norms exceed the threshold value, we consider the crash in Asia due to the COVID-19 as an EE. Similarly,
Figs. 7 (c) & (d) represent the L1 and L2 norms obtained for Europe. A spike in the norms is seen which exceeds the
threshold value, hence, we consider the crash in Europe as an EE. We have also carried out the analysis for America
and Oceania which also show similar results. The threshold of L1 and L2 norms for different continents during the
COVID-19 is listed in Table I.
  Further, we estimate the WD to understand the stock market dynamics during the crash due to COVID-19. Fig. 8
(a) & (b) represent the WD of Asia and Europe, respectively. A clear spike in the WD is seen during early 2020 which
corresponds with the actual crash time during COVID-19. As the spike in the WD is greater than the threshold,
shown by the red horizontal line, we consider the crash in Asia and Europe due to COVID-19 as an EE. Analysis
for Oceania also showed similar results. The threshold of WD for various continents during COVID-19 are listed in
Table I. It was seen that during the COVID-19 pandemic, different sectors were impacted differently due to their
                                                                                                                                    10

                          10-4                                                                                               10-5


                           (a)                                        (c)
                                                                                                                            1.2
                    1.2
          L1 Norm



                    0.6                                                                                                     0.6




                          10-3                                                                                               10-4

                          (b)                                         (d)
                                                                                                                            1.4
                     1
         L2 Norm




                    0.5                                                                                                     0.7




                                 Mar 20           May 21    July 22                 Jan 20            Jan 21       Jan 22
                                          Time (Day)                                         Time (Day)

FIG. 7: Plot (a) and (b) represent the L1 and L2 norms of Asia and plot (c) and (d) represent the L1 and L2 norms
   of Europe continent, respectively. The abrupt rise in norm values above the threshold confirms the EE due to
                                                    COVID-19.

                          (a)                                                 (b)
                                                                        0.6
                    0.4
                                                                      WD
         WD




                                                                        0.3
                    0.2




                                 Dec 19          Aug 20    Mar 21                        Dec 19           Aug 20     Mar 21
                                          Time (Day)                                              Time (Day)

FIG. 8: Plot (a) and (b) represent the Wasserstein distance (WD ) of Asia and Europe continents, respectively from
      2019 to 2012. The spike in the WD above the threshold value coincides with the COVID-19 pandemic.


business outlook4,40,47 . Hence, it is important to analyze the sector-wise dynamics during the COVID-19 which is
shown in the subsequent section.


D.   Impact of COVID-19 on different Indian sectors

  We analyze the impact of COVID-19 in different sectors of the Indian stock market such as Banking, Pharmaceutical,
Metal, Automobiles, and fast-moving consumer goods (FMCG). For these sectors, we have taken the companies based
on their respective Nifty sector indices.
  Figs. 9 (a) & (b) represent the L1 and L2 norms obtained from Banking sector. Similarly, Figs. 9 (c) & (d) represent
the L1 and L2 norms obtained from Pharmaceutical sector, respectively. A clear spike in the norms is observed during
                                                                                                                               11

                          10-5                                                                                      10-5

                          (a)                                         (c)                                           6
                      4


            L1 Norm


                      2                                                                                             3




                          10-4                                                                                          10-4

                          (b)                                         (d)
                                                                                                                    4
                      3
         L2 Norm




                   1.5                                                                                              2




                                 Jan 20          Jan 21    Jan 22                Jan 20           Jan 21   Jan 22
                                          Time (Day)                                       Time (Day)

FIG. 9: Plot (a) and (b) represent the L1 and L2 norms of the Banking sector and plot (c) and (d) represent the L1
   and L2 norms of the Pharmaceutical sector, respectively. The abrupt rise in norm values above the threshold
                                        confirms the EE due to COVID-19.




                                                                            COVID-19
                                          Sectors
                                                              L1 -norm       L2 -norm         WD
                                          Bank                3.01 × 10−5    2.72 × 10−4      1.48
                                          Pharmaceutical      3.99 × 10−5    3.38 × 10−4      1.86
                                          Automobile          2.75 × 10−5    2.54 × 10−4      1.17
                                          Metal               5.54 × 10−5    4.14 × 10−4      1.44
                                          FMCG                3.00 × 10−5    2.46 × 10−4      1.37

 TABLE II: Table represents the threshold of the L1 norm, L2 norm and WD of different sectors during the stock
                                   market crash due to COVID-19 pandemic.




the crash in both sectors. This spike in the norms is greater than the threshold values and hence, we consider the
crash in these sectors due to COVID-19 as an EE. Similar results were obtained for the automobile, Metal, and
FMCG sectors. The threshold values of the L1 and L2 norms for these sectors are listed in Table II. However, after
the main crash, there are spikes seen in the Banking sector which are significantly high. No such spikes are observed
in the Pharmaceutical. This shows that the Banking sector was in a stressful period for a longer time than the
Pharmaceutical sector which recovered quickly after the crash due to its positive outlook40,47 .

  Figs. 10 (a) & (b) show the WD of the Banking and Pharmaceutical sectors, respectively. The peak in the WD
corresponds with the crash due to COVID-19 and also surpasses our defined threshold which is marked by the
red horizontal line. Hence, the crash due to COVID-19 is considered an EE. Similar results were obtained for the
automobile, Metal, and FMCG sectors. The threshold values of WD for these sectors are listed in Table II.
                                                                                                                                    12

                  (a)                                                        (b)

            1.6                                                          2


          WD




                                                                    WD
            0.8                                                          1




                            Jan 20          Jan 21        Jan 22                    Jan 20          Jan 21         Jan 22
                                     Time (Day)                                              Time (Day)

  FIG. 10: Plot (a) and (b) represent the Wasserstein distance (WD ) of the Banking and Pharmaceutical sectors,
 respectively from 2019 to 2012. The spike in the WD above the threshold value confirms the occurrence of EE in
                                                  these sectors.


VI.    CONCLUSION

   Our study has proven successful in detecting continent-wise and sector-wise extreme events (EEs) in the stock market
using Topological Data Analysis (TDA). The 2008 financial crisis and the crash due to the COVID-19 pandemic are
identified as EEs in Asia, Europe, North-South America, and Oceania continents. A sector-wise analysis has been
carried out during the COVID-19 pandemic. Earlier work has identified the crash due to COVID-19 as an EE taking
the stock indices of each country separately proving it to be unsuitable for analyzing continent-wise or sector-wise.
However, TDA overcomes this difficulty and we can identify continent-wise & sector-wise EE by analyzing stock prices
of n stocks/indices together.
   We have considered EE as those events where the spike in the L1 and L2 norms are greater than the defined
threshold i.e., µN + 4 ∗ σ. Here µN and σ are the mean and the standard deviation of the norm, respectively. Also,
the Wasserstein distance (WD ) shows an abrupt rise during the EE crossing the threshold of µW + 4 ∗ σ. Here µW
and σ are the mean and standard deviation of the WD . All the above continents show a spike in the norms and WD
surpassing the thresholds during the 2008 financial crisis and the COVID-19. Hence, we consider the stock market
crashes in these continents as EEs. The effect of the COVID-19 was different in different sectors, hence we have also
carried out a sector-wise analysis during the COVID-19. Though the crashes in different sectors are identified as EEs,
the dynamics after the crash show different impacts of COVID-19. Norm values in the Banking sector show significant
spikes comparable to the main spike but no significant spikes are observed in the norm value of the Pharmaceutical
sector. This shows that the Banking sector was under stress even after the crash had occurred and remained volatile.
   Our results are consistent with the empirical mode decomposition-based Hilbert-Huang transform technique used
for the identification of EEs by Mahata et al.10 and Anish et al.13 . Hence, TDA is capable of identifying EEs in
the stock market. In the future, TDA may be applied with machine learning techniques to understand the market
dynamics and also may help in the prediction of stock prices.


VII.   ACKNOWLEDGEMENTS

  We would like to acknowledge NIT Sikkim for allocating doctoral fellowship to Anish Rai, Buddha Nath Sharma
and SR Luwang. We also like to acknowledge the inputs provided by Kundan Mukhia.
1 D. Sornette, Critical market crashes, Physics reports 378 (2003) 1–98.
2 N. Vandewalle, P. Boveroux, A. Minguet, M. Ausloos, The crash of october 1987 seen as a phase transition: amplitude and universality,

  Physica A: Statistical Mechanics and its Applications 255 (1998) 201–210.
3 Y. Choi, R. Douady,    Financial crisis dynamics: attempt to define a market instability indicator, Quantitative Finance 12 (2012)
  1351–1365.
4 M. Mazur, M. Dang, M. Vega, Covid-19 and the march 2020 stock market crash. evidence from s&p1500, Finance research letters 38

  (2021) 101690.
5 A. Rai, A. Mahata, M. Nurujjaman, O. Prakash, Statistical properties of the aftershocks of stock market crashes revisited: Analysis

  based on the 1987 crash, financial-crisis-2008 and covid-19 pandemic, International Journal of Modern Physics C 33 (2022) 2250019.
6 D.-H. Chen, H.-L. Huang, Panic, slash, or crash—do black swans flap in stock markets?, Physica A: Statistical Mechanics and its

  Applications 492 (2018) 1642–1663.
7 T. Kaizoji, D. Sornette, Bubbles and crashes, Encyclopedia of Quantitative Finance (2010).
                                                                                                                                          13

 8 S. Rabindrajit Luwang, A. Rai, M. Nurujjaman, O. Prakash, C. Hens, High-frequency stock market order transitions during the us–china

  trade war 2018: A discrete-time markov chain analysis, Chaos: An Interdisciplinary Journal of Nonlinear Science 34 (2024).
 9 S. Albeverio, V. Jentsch, H. Kantz, Extreme events in nature and society, Springer Science & Business Media, 2006.
10 A. Mahata, A. Rai, M. Nurujjaman, O. Prakash, D. Prasad Bal,            Characteristics of 2020 stock market crash: The covid-19 induced
   extreme event, Chaos: An Interdisciplinary Journal of Nonlinear Science 31 (2021).
11 C. Raymond, R. M. Horton, J. Zscheischler, O. Martius, A. AghaKouchak, J. Balch, S. G. Bowen, S. J. Camargo, J. Hess, K. Kornhuber,

   et al., Understanding and managing connected extreme events, Nature climate change 10 (2020) 611–621.
12 O. Korup, J. J. Clague, Natural hazards, extreme events, and mountain topography, Quaternary Science Reviews 28 (2009) 977–990.
13 A. Rai, S. R. Luwang, M. Nurujjaman, C. Hens, P. Kuila, K. Debnath, Detection and forecasting of extreme events in stock price

   triggered by fundamental, technical, and external factors, Chaos, Solitons & Fractals 173 (2023) 113716.
14 A. Mahata, D. P. Bal, M. Nurujjaman, Identification of short-term and long-term time scales in stock markets and effect of structural

   break, Physica A: Statistical Mechanics and its Applications 545 (2020) 123612.
15 A. Mahata, M. Nurujjaman, Time scales and characteristics of stock markets in different investment horizons, Frontiers in Physics 8

   (2020) 590623.
16 G. E. Carlsson,       Topology and data, Bulletin of the American Mathematical Society 46 (2009) 255–308. URL: https://api.
   semanticscholar.org/CorpusID:1472609.
17 T. K. Dey, Y. Wang, Computational Topology for Data Analysis, Cambridge University Press, 2022.
18 S. Kulkarni, H. K. Pharasi, S. Vijayaraghavan, S. Kumar, A. Chakraborti, A. Samal, Investigation of indian stock markets using

   topological data analysis and geometry-inspired network measures, arXiv preprint arXiv:2311.17016 (2023).
19 M. Kramár, A. Goullet, L. Kondic, K. Mischaikow, Persistence of force networks in compressed granular media, Physical Review E 87

   (2013) 042207.
20 T. Nakamura, Y. Hiraoka, A. Hirata, E. G. Escolar, Y. Nishiura, Persistent homology and many-body atomic structure for medium-range

   order in the glass, Nanotechnology 26 (2015) 304001.
21 K. Turner, S. Mukherjee, D. M. Boyer, Persistent homology transform for modeling shapes and surfaces, Information and Inference: A

   Journal of the IMA 3 (2014) 310–344.
22 L. M. Seversky, S. Davis, M. Berger, On time-series topological data analysis: New data and opportunities, in: Proceedings of the IEEE

   conference on computer vision and pattern recognition workshops, 2016, pp. 59–67.
23 Y. Yao, J. Sun, X. Huang, G. R. Bowman, G. Singh, M. Lesnick, L. J. Guibas, V. S. Pande, G. Carlsson, Topological methods for

   exploring low-density states in biomolecular folding pathways, The Journal of chemical physics 130 (2009).
24 M. Nicolau, A. J. Levine, G. Carlsson, Topology based data analysis identifies a subgroup of breast cancers with a unique mutational

   profile and excellent survival, Proceedings of the National Academy of Sciences 108 (2011) 7265–7270.
25 Y. Lee, S. D. Barthel, P. Dlotko, S. M. Moosavi, K. Hess, B. Smit, Quantifying similarity of pore-geometry in nanoporous materials,

   Nature communications 8 (2017) 15396.
26 V. De Silva, R. Ghrist, et al., Homological sensor networks, Notices of the American mathematical society 54 (2007).
27 S. M. S. Syed Musa, M. S. Md Noorani, F. Abdul Razak, M. Ismail, M. A. Alias, S. I. Hussain, Using persistent homology as preprocessing

   of early warning signals for critical transition in flood, Scientific Reports 11 (2021) 7234.
28 M. Gidea, Topology data analysis of critical transitions in financial networks, arXiv preprint arXiv:1701.06081 (2017).
29 M. Gidea, Y. Katz, Topological data analysis of financial time series: Landscapes of crashes, Physica A: Statistical Mechanics and its

   Applications 491 (2018) 820–834.
30 A. Aguilar, K. Ensor, Topology data analysis using mean persistence landscapes in financial crashes, Journal of Mathematical Finance

   10 (2020) 648–678.
31 H. Guo, S. Xia, Q. An, X. Zhang, W. Sun, X. Zhao, Empirical study of financial crises based on topological data analysis, Physica A:

   Statistical Mechanics and its Applications 558 (2020) 124956.
32 P. T.-W. Yen, S. A. Cheong, Using topological data analysis (tda) and persistent homology to analyze the stock markets in singapore

   and taiwan, Frontiers in Physics 9 (2021) 572216.
33 P. T.-W. Yen, K. Xia, S. A. Cheong, Understanding changes in the topology and geometry of financial market correlations during a

   market crash, Entropy 23 (2021) 1211.
34 A. Goel, P. Pasricha, A. Mehra, Topological data analysis in investment decisions, Expert Systems with Applications 147 (2020) 113222.
35 S. Majumdar, A. K. Laha, Clustering and classification of time series using topological data analysis with applications to finance, Expert

   Systems with Applications 162 (2020) 113868.
36 M. Gidea, D. Goldsmith, Y. Katz, P. Roldan, Y. Shmalo, Topological recognition of critical transitions in time series of cryptocurrencies,

   Physica A: Statistical mechanics and its applications 548 (2020) 123843.
37 H. G. Souto, Topological tail dependence: Evidence from forecasting realized volatility, The Journal of Finance and Data Science 9

   (2023) 100107.
38 H. Guo, X. Zhao, H. Yu, X. Zhang, Analysis of global stock markets’ connections with emphasis on the impact of covid-19, Physica A:

   Statistical Mechanics and its Applications 569 (2021) 125774.
39 H. Guo, H. Yu, Q. An, X. Zhang, Risk analysis of china’s stock markets based on topological data structures, Procedia Computer

   Science 202 (2022) 203–216.
40 A. Mahata, A. Rai, M. Nurujjaman, O. Prakash, Modeling and analysis of the effect of covid-19 on the stock price: V and l-shape

   recovery, Physica A: Statistical Mechanics and its Applications 574 (2021) 126008.
41 D. Gold, K. Karabina, F. C. Motta, An algorithm for persistent homology computation using homomorphic encryption, arXiv preprint

   arXiv:2307.01923 (2023).
42 S. W. Akingbade, M. Gidea, M. Manzi, V. Nateghi, Why topological data analysis detects financial bubbles?, Communications in

   Nonlinear Science and Numerical Simulation 128 (2024) 107665.
43 F. Chazal, B. Michel, An introduction to topological data analysis: fundamental and practical aspects for data scientists, Frontiers in

   artificial intelligence 4 (2021) 108.
44 D. Cohen-Steiner, H. Edelsbrunner, J. Harer, Stability of persistence diagrams, in: Proceedings of the twenty-first annual symposium

   on Computational geometry, 2005, pp. 263–271.
45 P. Bubenik, Statistical topological data analysis using persistence landscapes, Journal of Machine Learning Research 16 (2015) 77–102.

   URL: http://jmlr.org/papers/v16/bubenik15a.html.
                                                                                                                                   14

46 yahoo, Yahoo finance, https://finance.yahoo.com/, 2024.
47 A. Rai, A. Mahata, M. Nurujjaman, S. Majhi, K. Debnath, A sentiment-based modeling and analysis of stock price during the covid-19:

  U-and swoosh-shaped recovery, Physica A: Statistical Mechanics and its Applications 592 (2022) 126810.