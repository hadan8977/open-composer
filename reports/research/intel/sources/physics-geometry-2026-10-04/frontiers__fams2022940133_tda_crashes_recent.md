source: https://www.frontiersin.org/journals/applied-mathematics-and-statistics/articles/10.3389/fams.2022.940133/pdf
fetched_utc: 2026-10-04T18:37:31Z
bytes_raw: 2748347

ORIGINAL RESEARCH
                                                                                                                                             published: 30 June 2022
                                                                                                                                     doi: 10.3389/fams.2022.940133




                                             Early Warning Signals of Financial
                                             Crises Using Persistent Homology
                                             and Critical Slowing Down: Evidence
                                             From Different Correlation Tests
                                             Mohd Sabri Ismail*, Mohd Salmi Md Noorani, Munira Ismail and Fatimah Abdul Razak

                                             Department of Mathematical Sciences, Faculty of Science and Technology, Universiti Kebangsaan Malaysia, Bangi, Malaysia



                                             In this study, a new market representation from persistence homology, known as the
                                             L1 -norm time series, is used and applied independently with three critical slowing down
                                             indicators [autocorrelation function at lag 1, variance, and mean for power spectrum
                                             (MPS)] to examine two historical financial crises (Dotcom crash and Lehman Brothers
                                             bankruptcy) in the US market. The captured signal is the rising trend in the indicator
                                             time series, which can be determined by Kendall’s tau correlation test. Furthermore, we
                            Edited by:       examined Pearson’s and Spearman’s rho correlation tests as potential substitutes for
                   Mohd Hafiz Mohd,
              Universiti Sains Malaysia      Kendall’s tau correlation. After that, we determined a correlation threshold and predicted
                      (USM), Malaysia        the whole available date. The point of comparison between these correlation tests is to
                         Reviewed by:        determine which test is significant and consistent in classifying the rising trend. The results
                           Majid Khan,
              Universiti Sains Malaysia
                                             of such a comparison will suggest the best test that can classify the observed rising trend
                      (USM), Malaysia        and detect early warning signals (EWSs) of impending financial crises. Our outcome
                          Marian Gidea,      shows that the L1 -norm time series is more likely to increase before the two financial
      Yeshiva University, United States
                                             crises. Kendall’s tau, Pearson’s, and Spearman’s rho correlation tests consistently
                  *Correspondence:
                    Mohd Sabri Ismail        indicate a significant rising trend in the MPS time series before the two financial crises.
             sabrimohd92@gmail.com           Based on the two evaluation scores (the probability of successful anticipation and
                                             probability of erroneous anticipation), by using the L1 -norm time series with MPS, our
                    Specialty section:
          This article was submitted to      result in the whole prediction demonstrated that Spearman’s rho correlation (46.15 and
    Mathematics of Computation and           53.85%) obtains the best score as compared to Kendall’s tau (42.31 and 57.69%) and
                         Data Science,
                                             Pearson’s (40 and 60%) correlations. Therefore, by using Spearman’s rho correlation
                a section of the journal
 Frontiers in Applied Mathematics and        test, L1 -norm time series with MPS is shown to be a better way to detect EWSs of US
                               Statistics    financial crises.
             Received: 10 May 2022
                                             Keywords: topological data analysis, persistent homology, critical transition, critical slowing down, correlation
            Accepted: 07 June 2022
                                             tests, early warning signal, financial crises, complex system
            Published: 30 June 2022
                               Citation:
 Ismail MS, Md Noorani MS, Ismail M          INTRODUCTION
        and Abdul Razak F (2022) Early
    Warning Signals of Financial Crises
                                             Understanding behaviors of financial crises (unexpected and huge declines in the stock market)
       Using Persistent Homology and
Critical Slowing Down: Evidence From
                                             are crucial to explaining the dynamics of the financial market. However, such financial events are
             Different Correlation Tests.    very challenging to study. Among them, the challenges are understanding how the financial market
    Front. Appl. Math. Stat. 8:940133.       behaves before financial crises and developing a method that is capable to detect early warning
      doi: 10.3389/fams.2022.940133          signals (EWSs) of the financial crises. The detection method will become more beneficial if it can



Frontiers in Applied Mathematics and Statistics | www.frontiersin.org             1                                            June 2022 | Volume 8 | Article 940133
Ismail et al.                                                                                                       EWS of FCs Using PH and CSD



accurately distinguish the financial market into two classification         called L1 −norm time series. Since the persistence landscapes
periods, which are EWS periods (indicating a possible huge                  are robust under perturbations of the underlying data, the
downtrend is coming in the market) and safe periods. Such                   L1 -normtime series has the advantage to reflect the loss of
a method helps investors and traders to develop an early                    stability in dynamic states of the original system. When the
precaution strategy and protect their investments from any losses           stock market becomes more volatile, loops in the relevant
due to a financial crisis.                                                  point clouds become much more pronounced and give more
    In practice, the Chicago Board Options Exchange’s CBOE                  significant features within persistence landscapes [25]. At that
Volatility Index or VIX index—a real-time market index                      time, the corresponding L1 -normvalues are more likely to
representing the market’s expectations for volatility over the              jump up, and this behavior is believed to correspond with
coming 30 days—is always used by market participants to alert               an undergoing CSD. Therefore, to test the presence of CSD,
any upcoming financial crisis. The uptrend patterns in the VIX              the CSD indicators are used with the L1 -normtime series,
were observed before financial crises, unfortunately, low-level             where these indicators should alert upcoming financial crises
VIX also reported occurred before financial crises [1, 2]. This             by showing their significant rising trend that can be classified
suggests that the VIX can provide EWSs; however, a reliable                 by Kendall’s tau correlation test. In their work, Gidea and Katz
method to predict financial crises remains a challenge in this              [25] showed that theL1 -normtime series grew substantially before
field. Therefore, extensive studies have been conducted by many             the Dotcom crash and Lehman Brothers bankruptcy in the US
researchers in an attempt to provide other rationales to explain            market. Interestingly, by using CSD indicators and Kendall’s tau
why financial crises occurred and provide any other possible                correlation test on the L1 -normtime series, Gidea and Katz [25]
EWS. Some of those methods are bubble theory [3–5], financial               confirmed that a significant strong rising trend happen in the
stress indicator [6, 7], information-based measures [8, 9],                 MPS time series before those two financial crises. Therefore,
financial network analysis [10–12], and graphical analysis [13].            the method is suggested as a new potential EWS. Later, the
    However, this study is focusing on critical transition theory.          application of PH to financial data analysis has attracted more
This theory viewed the financial market as a complex system                 attention from researchers, especially in detecting EWSs. All
with episodes of critical transitions (abrupt shifts from a current         the articles published in this area are discussed in Section
stable state to another stable state when the system reaches critical       Literature Review.
points) [14, 15]. When approaching a critical point, this theory                In this article, we also used PH and CSD indicators (AC1,
stated that a generic phenomenon happened known as critical                 VAR, and MPS) to detect EWSs of financial crises. Unlike Gidea
slowing down (CSD) because of decreasing stability in the market            and Katz [25], instead of using Kendall’s tau correlation test to
and its recovery rate took longer to preserve the stability. At             indicate the rising trend in the time series of the indicators, we
a critical point, the financial market loses its stability in the           also examined Pearson’s and Spearman’s rho correlation tests
dynamic state and then suddenly causes a market movement into               as a potential substitute for Kendall’s tau correlation. The point
a financial crisis. CSD gives a rising trend in the time series of          of comparison between these correlation tests is to determine
some indicators, such as autocorrelation function at lag 1 (AC1),           which test is significant and consistent in classifying the rising
variance (VAR), and mean for power spectrum (MPS) at low                    trend. The results of such a comparison will suggest the best
frequencies [16–18].                                                        test that can classify the observed rising trend and detect EWSs
    In the traditional method, the rising trend in the time series          of impending financial crises. The remaining portion of this
of CSD indicator that happens before the critical transition                article is organized as follows. Section Literature Review briefly
point is determined using Kendall’s tau correlation test. By using          discusses our literature review, Section Persistent Homology
Kendall’s tau correlation test, previous studies have shown that            introduces PH, Section Data Analysis elaborates on our data,
the observed rising trend can provide EWSs before financial                 Section Methods presents the applied methods, Section Result
crises [19–23]. Despite the successful results obtained, there is           mentions our results and their corresponding discussions, and
a realization that some indicator like AC1 also tends to decline            Section Conclusion wraps our conclusion.
before financial crises. All of these lead to mixing results such
as recorded in Guttal et al. [21] and Diks et al. [23]. However,
as compared to critical transitions, Guttal et al. [21] argued that         LITERATURE REVIEW
financial crises are more likely to follow stochastic transition,
in which variability indicators (VAR and MPS) can signal early              Topological information from financial data obtained using PH
warnings for financial markets. This also points out that abrupt            has been used to study financial problems. In recent times, this
transitions in the financial market are hardly the same as a                topic has attracted attention from many researchers around the
complex system in nature such as the earth’s global climate and             globe. In the finance market, the most application currently
interaction between species in ecology. One of the reasons behind           investigated by PH is financial crises and their EWS detection
this is the financial market is involved with human behaviors that          tools. In a multivariate setting, by begin with examining chaotic
influence the market’s movement [23].                                       time series with noise and a growing variance, Gidea and Katz
    Recently, using persistent homology (PH) (a robust method               [25] showed that PH can exhibit strong growth in its market
to compute topological features of financial data at different              representative time series prior to the critical point. This growth
spatial scales [24]), Gidea and Katz [25] suggested a new                   can be analyzed using CSD indicators (AC1, VAR, and MPS)
market representative obtained from persistence landscapes                  and correlation tests (Kendall’s tau) to indicate corresponding


Frontiers in Applied Mathematics and Statistics | www.frontiersin.org   2                                      June 2022 | Volume 8 | Article 940133
Ismail et al.                                                                                                          EWS of FCs Using PH and CSD



CSD that happen before critical point. After that, Gidea and                PERSISTENT HOMOLOGY
Katz [25] used the pipeline method to examine the Dotcom
crash and Lehman Brothers bankruptcy in the US market as                    Persistent homology is a new quantitative method of topological
mentioned earlier.                                                          data analysis to compute topology features (connected
   After that, Ismail et al. [26] expanded the study of Gidea               components, loops, voids, and others) that persistently
and Katz [25] by using PH and CSD indicators to examine                     emerge across multiple scales. Interestingly, PH is robust to
financial crises in the US, Singapore, and Malaysia markets.                small perturbations of input data, independent of dimensions
Aspects of the method’s robustness and prediction performance               and coordinates and provides a compact representation of the
have been rigorously evaluated in Ismail et al. [26]. Meanwhile,            qualitative features of the input [42–44]. These characteristics
Aromi et al. [27] substantiated that PH reflects changes in                 make PH suitable to analyze complex, non-linear, noisy, and
the underlying multivariate distribution and strong covariance              high-dimensional data like financial data [45].
could nullify the persistence of homologies. On the other                       Later, a summary of PH in the way that it is used in this
hand, [28] also analyzed time-dependent correlation networks                article is provided. We noted that the concepts of PH stated here
using PH to detect early signs of critical transitions in                   can also be found in most books and journals related to PH.
financial data.                                                             To further explore the theories and other concepts of PH, we
   In Guo et al. [29], an EWS based on PH is also built                     recommend Otter et al. [24] and Edelsbrunner and Harer [46]
to detect the critical dates on the financial time series.                  to the interested readers.
Guo et al. [30] also used topological features of complex                       Input data analyzed by PH isncalled point cloud dataset
                                                                                                                                  o (PCD),
networks that were extracted using PH to find critical dates                which can be denoted as X = xi ∈ Rd |i = 1, · · · , n for d ≥ 2.
for financial crises. In addition, dynamics of financial market             Let X be a PCD, a Rips complex at a scale ε > 0 (denoted as
correlations based on topology and geometry are examined                    R (X, ε)) can be constructed as follows:
using PH in Yen et al. [31]. Moreover, Yen and Cheong
[32]also tested PH to analyze Singapore and Taiwan markets.                 • For
                                                                              n each dimensional    o      k = 0, 1, · · · , a k-simplex of X points
The extreme event called flash crash was also explored                         xi1 , · · · , xi(k+1) belongs to a R (X, ε) if and only if for every
in Kim et al. [33] by applying PH and dynamic time                                   
                                                                              pair xir , xis , we have xir − xis ≤ ε for all xir , xis ∈
series analysis.                                                              n                     o
   Furthermore, anomalies detection in the dynamics of a market                xi1 , · · · , xi(k+1) [24].
index also is studied with PH [34]. Katz and Biem [35] also
                                                                            Roughly speaking, a Rips complex is a combination of vertices
showed that early signatures of growing market instabilities can
                                                                            (0-simplex), edges (1-simplex), solid triangles (2-simplex), and
be captured by PH. Besides, Gidea et al. [3] used PH and k-
                                                                            higher dimensional analog, joined according to the above-
means clustering to detect critical transitions in the time series
                                                                            mentioned rule. Figure 1 illustrates 0-simplex until 2-simplex
of cryptocurrencies. For Bitcoin [36], also uses PH and CSD
                                                                            and a two-dimensional Rips complex R (X, ε) ,respectively. In
indicators to detect such transitions and substantiated that PH
                                                                            Figure 1, the scale ε is the diameter of balls around each point
can detect EWSs better than the detrending time-series approach
                                                                            in the different PCDs.
(the most common approach used in previous studies to detect
                                                                                In a real-world application, finding a single ε is impractical
CSD indicators).
                                                                            since the real space behind PCD is mostly unknown. Therefore,
   Other than that, PH also has been developed to improve
                                                                            PH provides a better way to interpret topological information
portfolio investment strategies. Studied ten global indices and
                                                                            regarding the shape behind PCD by varying the scale ε. Let
all their underlying assets, Goel et al. [37] showed that a
                                                                            ε ∈ {ε0 , · · · εm } such that 0 ≤ ε0 < · · · < εm , then filtration
new strategy based on PH leads to more robust portfolios.
                                                                            of Rips complexes is R (X, ε0 ) ⊂ · · · ⊂ R (X, εm ). Figure 2 shows
Baitinger and Flegel [38] also demonstrated that investment
                                                                            a filtration containing six Rips complexes constructed of a PCD
strategies relying on a PH-based turbulence detection outperform
                                                                            at multiple scales.
investment strategies based on other popular turbulence indices.
                                                                                For i = 1, · · · , m, we can compute the k-homology of
In clustering and classification of financial time series, Majumdar
                                                                            each Rips complex R (X, εi ), denoted as Hk (R (X, εi )). Roughly
and Laha [39] showed that PH outperforms other methods in
                                                                            speaking, H0 (R (X, εi )) is the free group generated by the
this task.
                                                                            connected components of R (X, εi ), H1 (R (X, εi )) is the free
   Additionally, PH is applied with machine learning to predict
                                                                            group generated by the loops in R (X, εi ), H2 (R (X, εi )) is the
the movement of financial data. Such a task has been done in
                                                                            free group generated by the voids of R (X, εi ). The Betti numbers
Ismail et al. [40] by using PH and machine learning methods
                                                                            count the number of generators of such homology groups. This
(logistic regression, neural network, support vector machine,
                                                                            number of generators indicates the number of corresponding
and random forest) to predict the next-day direction of the
                                                                            topological features that emerge at each scale.
Kuala Lumpur Composite Index (KLCI). Moreover, Baitinger
                                                                                In addition, information regarding the lifespans of topological
and Flegel [41] also introduced PH to produce microstructural
                                                                            features also can be obtained by using PH. In the PH community,
predictors, where these predictors are combined with machine
                                                                            most believe that a topological feature that has a longer lifespan
learning and statistical factor extraction methods to predict
                                                                            (persists for a bigger range of scales) can be viewed as a more
asset returns.




Frontiers in Applied Mathematics and Statistics | www.frontiersin.org   3                                         June 2022 | Volume 8 | Article 940133
Ismail et al.                                                                                                                   EWS of FCs Using PH and CSD




  FIGURE 1 | (A,B) are 0-simplex, 1-simplex, 2-simplex, and a two-dimensional Rips complex, respectively.




significant one, whereas a feature that has a shorter lifespan                       hand [45]. However, this study used all the obtained lifespan in
(persists for a smaller range) can be viewed as a less significant,                  our computation.
                                                                                           
or a noisy feature. Nevertheless, the theoretical justification                         Let (εb , εd )i |i = 1, · · · , n be a collection of the lifespans of
for this is unclear and may be dependent on the problem at                           topological features such that εb < εd and εb , εd ∈ {ε0 , · · · εm }.



Frontiers in Applied Mathematics and Statistics | www.frontiersin.org            4                                         June 2022 | Volume 8 | Article 940133
Ismail et al.                                                                                                                            EWS of FCs Using PH and CSD




  FIGURE 2 | Filtration of six Rips complexes constructed of a PCD at six different scales.




The simplest tool to present this information is a persistent                             As a result, we obtained a set of n piecewise linear functions
barcode, which is a collection of n half-closed intervals [εb , εd )                       f(εb ,εd )i (x) |i = 1, · · · , n . Later the layer in the persistence
representing the lifespans of topological features, see Figure 3A.                       landscape was obtained for each k ∈ Z, which is a function
Other tools are a persistent diagram and a persistent landscape.                         λk (x): R → [0, ∞)that is defined            as follows λk (x) = k −
A persistent diagram is a finite collection of n birth–death points                      max f(εb ,εd )i (x) |i = 1, · · · , n , where k − max denotes the
(εb , εd ) ∈ R2 that lie along or above a diagonal line. If there are                    kthlargest value of the piecewise linear functions. If the kth largest
redundant birth–death points, then the points will be represented                        value does not exist anymore for k = l, then λk (x) = 0for
as a single point but multiplied by its size to correspond to the                        all remaining k ≥ l. The persistent landscape λ is the infinite
frequency of this point. Figure 3B provides an example of a                              sequence of λk (x), which can be denoted as {λ1 (x) , λ2 (x) , · · · }.
persistent diagram.                                                                      Figures 3C,D presents the persistence landscapes of connected
   On the other hand, the persistence landscape λ is quite a recent                      components and a loop, respectively.
tool introduced by Bubenik and Dłotko [47] and Bubenik [48].                                  In this study, we used persistent landscapes because this
To define the persistent landscape, we transformed each lifespan                         representation can be summarized into a summary point, that is a
into a piecewise linear function f(εb ,εd )i : → [0, ∞), which is                        Lp -norm. This norm is a function k.kp : λ → R, which is defined
defined below:                                                                           as follows:


                                                                                                                                       #1
                             x − εb if x ∈ (εb , (εb + εd )/2 ]
                                                                                                             "∞ Z
                                                                                                              X                          p
                                                                                                                                 p
           f(εb ,εd )i (x) = −x + εd if x ∈ ((εb + εd )/2 , εd ) ,                                 kλkp =                 |λk (x)| dx        for 1 ≤ p < ∞,        (2)
                                   0 if x ∈
                                          / ((εb + εd ))
                            
                                                                                                              k=1
                                                                                                                    sup
           for i = 1, · · · , n.                                               (1)                 and kλk∞ = k,x |λk (x)| for p = ∞.                              (3)


Frontiers in Applied Mathematics and Statistics | www.frontiersin.org                5                                            June 2022 | Volume 8 | Article 940133
Ismail et al.                                                                                                                           EWS of FCs Using PH and CSD




  FIGURE 3 | Refer to the filtration of Rips complexes in Figure 2. By applying PH, compact representations: (A) a persistent barcode, (B) a persistence diagram (note
  that the size for point (0, 2) is enlarged two times bigger than the others to indicate two connected components that share a redundant lifetime), (C) a persistence
  landscape of connected components (note that the third sub-landscape is enlarged two times bigger than the others to indicate two connected components, which
  share a redundant lifetime), and (D) a persistence landscape of a loop are obtained.




   Furthermore, statistical properties of these norm values also                       as discussed in Section Methods. Furthermore, in Figure 4,
can be analyzed. Therefore, the CSD indicators are computed                            the crisis dates for the Dotcom crash and Lehman Brothers
from these norm values, and they are used to detect EWSs of                            bankruptcy are mentioned.
impending financial crises in this study.


SAMPLE DATA                                                                            METHODS
For this study, four main stock indices of the US market                               Pre-crisis Dataset
were collected, which span from 22/12/1987 until 29/12/2017.                           In this study, two pre-crisis datasets were generated. The two
The indices were the Standard and Poor’s 500 (S&P 500), the                            datasets contained closing prices of the four indices (S&P 500,
Dow Jones Industrial Average (DJIA), the Nasdaq Composite                              DJIA, Nasdaq, and Russell 2000) with a length of 1000 before
(Nasdaq), and the Russell 2000 Index (Russell 2000), which                             the crisis date of the Dotcom crash and Lehman Brothers
were derived from the Yahoo Finance. All these indices are                             bankruptcy, respectively. The objective of creating the two pre-
shown in Figure 4. In Figure 4, for illustration purposes, the                         crisis datasets was to study the financial market’s behaviors before
indices are normalized using the max/min
                                       normalization  using                          the financial crises, where the obtained information based on
the formula pnorm = 2 × pt − min / (max − min) , where                                 PH and CSD would be proceeded to form a EWS detection.
pt ,max,and min are the closing price at date t, the maximum                           Later, we predicted and compared the performance for the case
closing price, and the minimum closing price of an index,                              of using different correlation tests: Kendall’s tau, Pearson’s, and
respectively. Such normalization does not involve our method                           Spearman’s rho.


Frontiers in Applied Mathematics and Statistics | www.frontiersin.org              6                                             June 2022 | Volume 8 | Article 940133
Ismail et al.                                                                                                                     EWS of FCs Using PH and CSD




  FIGURE 4 | Indices for the Standard and Poor’s 500 (S&P 500), the Dow Jones Industrial Average (DJIA), the Nasdaq Composite (Nasdaq), and the Russell 2000
  Index (Russell 2000), respectively. The crisis dates for the Dotcom crash and Lehman Brothers bankruptcy also are mentioned.




Persistent Homology                                                                  For each t, as briefed in Section Persistent Homology, PH of Rips
For i = 1, · · · , 4, 1000 closing prices of an index i in the pre-                  filtration that built on PCD X (t) ,the corresponding persistence
crisis were transformed       to daily log returns using the formula                 landscape at the date t and the corresponding L1 -norm value at
rti = ln pit /pit−1 for t = 1, · · · , 1000, where pit is the
                         
                                                                                     the date t were computed, accordingly.   By doing so, we obtained
closing price at date t. As a result, for each pre-crisis dataset,                   L1 -normtime series, denoted by Y= kλk1,t |t = 50, · · · , 1000 ,
we
 obtained     a transformed pre-crisis dataset, denoted           as X =            where kλk1,t is a L1 -norm value at the date t.
  rt ∈ R4 |t = 1, · · · , 1000 , where rt = rt1 , · · · , rt4 is a point of
                                                             

the X at the date t. Xcan be illustrated in matrix form as below:                    Critical Slowing Down Indicators
                                                                                     Consequently,
                                                                                                               the        L1 -normtime            series
                        r11   r12 · · · r14                                          Y= kλk1,t |t = 50, · · · , 1000 was segmented by using the
                                                         
                       r21   r22 · · · r24                                         daily sliding window of the length 500 to obtain sequences of
                    X= .                                                  (4)       500 L1 -norm values. The length 500 was selected based on the
                                              
                                .. ..       .. 
                       ..       .     .     .                                      literature mentioned in Guttal et al. [21], Diks et al.[23], and
                        1     2           4
                       r1000 r1000 · · · r1000                                       Ismail et al. [ 26], which uses half of the length of the pre-crisis
                                                                                     dataset. Each sequence of 500 L1 -norm values at the date t can be
Furthermore, the daily sliding window of length 50 approach                          denoted as below:
was applied to segment the X to obtain PCDs. For financial data                                     
analysis, it had been demonstrated that a length of 50 was enough                            Y (t) = kλk1,((t−500)+1) , · · · , kλk1,((t−500)+500) ,
to extract topological information through PH as reported in the                              for t = 549, · · · , 1000.                                       (6)
previous literature reviews [3, 25, 26, 35]. Consequently, each
respective PCD from X at the date t also can be illustrated in                       For each t ∈ {549, · · · , 1000}, we computed a value based on
matrix form as follows:                                                              the CSD indicators: AC1, VAR, and MPS at low frequencies as
                 1                                                                  accordingly defined below:
                                2
                  r((t−50)+1) r((t−50)+1)          4
                                           · · · r((t−50)+1)
                                                              
                    1
                 r((t−50)+2)   2
                              r((t−50)+2)          4
                                           · · · r((t−50)+2)                        • The AC1 value at trading t is ac1t = ρ1,tvar t , where ρ1,t =
                                                                                             ((t−500)+500)−1
        X (t) =                                              ,
                                                                                                                                              
                       ..           ..     ..          ..                                1          P
                                                                                                             kλk1,j − kλk1,j kλk1,(j+1) − kλk1,j ,
                       .            .         .        .                             500−1
                   1           2                  4                                            j=((t−500)+1)
                 r((t−50)+50) r((t−50)+50) · · · r((t−50)+50)                          [[Mathtype-mtef1-eqn-106.mtf]] is the mean of Y (t) and vart
         for t = 1, · · · , 1000.                                          (5)         is the VAR of Y (t) as defined in the point below.


Frontiers in Applied Mathematics and Statistics | www.frontiersin.org            7                                           June 2022 | Volume 8 | Article 940133
Ismail et al.                                                                                                                           EWS of FCs Using PH and CSD


                                                                                     v                                                                        !2
• The           VAR    value     at    the
                                      date t is vart                    =             u                                        !
                                                                                      u         ((t−250)+250)                           ((t−250)+250)
          ((t−500)+500)−1                                                            t250
                                                                                                     P                     2                 P
      1          P                       2                                                                       (ac1l )          −                    ac1l
    500−1                 kλk1,j − kλk1,j , where kλk1,j                =                       l=((t−250)+1)                           l=((t−250)+1)
              j=((t−500)+1)                                                          v                                 !                          !2 
          ((t−500)+500)
                                                                                     u
                                                                                              ((t−250)+250)                    ((t−250)+250)
     1                                                                                                            2
               P                                                                     u
                   kλk1,j the mean of Y (t ).                                        t250          P                                P
    500                                                                                                       l            −                     l 
          j=((t−500)+1)                                                                       l=((t−250)+1)                    l=((t−250)+1)
                          
• Given Y (t) =             kλk1,((t−500)+1) , · · · , kλk1,((t−500)+500) ,                             6 di2
                                                                                                         P
  we defined its discrete Fourier transformation as Fk,t =                        • pAC1,t = 1 − 250(250  i
                                                                                                             2 −1) , where di is the difference between
  ((t−500)+500)
       P
                kλk1,j · e
                           −2π ikj
                                   500 , where k ∈ {1, · · · , 500}. The            the ranks of the corresponding variables of AC1 (t), and
   j=((t−500)+1)                                                                    {((t − 250) + 1) , · · · , ((t − 250) + 250) }.
                                             2
   power spectrum is PSk,t = Fk,t for k ∈ {1, · · · , 500}. Then,                 As a result, three sets of time series based on Kendall’s tau,
   the MPS value at the date t, denoted as mpst is the mean of all               Pearson’s, and Spearman’s rho correlation values computed
   PSk,t for k ∈ 2, · · · , 18 × 500 .                                           from   AC1 were obtained, which can
                                                                                                                            be denoted as τAC1 =
As a result, we obtained three sets of time series based on                         τAC1,t |t = 798,
                                                                                                    · · · , 1000 , r AC1 =  rAC1,t |t = 798, · · · , 1000 ,
AC1, VAR, and MPS values, which can be denoted as AC1 =                           and pAC1 = pAC1,t |t = 798, · · · , 1000 ., respectively. For, VAR
{ac1t |t = 549, · · · , 1000}, VAR = {vart |t = 549, · · · , 1000}, and          and MPS, the same three sets of time series based on these three
MPS = mpst |t = 549, · · · , 1000 accordingly.                                    correlation values also can be obtained using the above formula.
                                                                                      Note that if any correlation (Kendall’s tau, Pearson’s, or
                                                                                  Spearman’s rho) provides a positive real value at the date t, we
Correlation Tests                                                                 conclude that a rising trend happened in the 250 indicator values
In the study, Kendall’s tau correlation was used to determine                     from the date (t − 250 + 1) to t. In critical transition theory, it
a rising trend in the indicator’s time series (AC1, VAR,                          was expected that these indicators’ time series: AC1, VAR, and
or MPS). Nonetheless, Pearson’s and Spearman’s rho                                MPS are increasing before a financial crisis. In addition, the rising
correlations were included in addition to Kendall’s tau                           trend in the indicators will give rise to a positive real number of
correlation as alternative measures to detect the trend.                          the correlation ahead of a financial crisis.
In brief, Kendall’s tau, Pearson’s, and Spearman’s rho
correlations computed the strength of concordance dependency,
the range of linear relationship, and the degree of the                           Significant and Skewness Tests
association, respectively.                                                        Furthermore, we performed a significance test in this study to
   Daily sliding window of length 250 was used to                                 examine whether the rising trend in the last 125 indicator values
attain sequences containing 125 indicator values. In                              at the date from 750 to 999, which was summarized by the
addition, the length of 250 was chosen as half data of                            correlation value at the date t = 999 (1 day before the financial
the previous sliding window with length of 500. This                              crisis), was statistically significant at level 5%. To conduct the test,
length was considered sufficient to capture rising trend                          we computed the p-value for each of the correlation values at the
in the indicators as shown in Guttal et al. [21] and                              date t = 999. The p-value obtained is a doubled probability of
Ismail et al. [26]. Therefore, three tests based on Kendall’s                     getting the statistical value or a value with even greater evidence
tau, Pearson’s, and Spearman’s rho correlations from                              against H0 .
each sequence containing 250 indicator values were                                   Let us take AC1 as an example; here, H0 represents no
computed. Considering AC1 as an example, each sequence                            monotonic trend (either rising or declining) that happens in the
containing 250 AC1 values at the date t can be denoted as                         time series AC1 (999) . A significance test at level 5% translates to
AC1 (t) = {ac1t |t = ((t − 250) + 1) , · · · , ((t − 250) + 250)},                a requirement p-value less than 0.005 to interpret any monotonic
for t = 798, · · · , 1000. For each t ∈ {798, · · · , 1000}, Kendall’s            trend (rising or decline) in the time series AC1 (999) as significant
tau, Pearson’s, and Spearman’s rho correlations from AC1 (t) are                  or otherwise. The same significant test was also applied to
computed as follow:                                                               VAR and MPS time series, that is, VAR (999) and MPS (999) ,
• τAC1,t      =       (C−D)        , where C is the number                       respectively. This significance test is vital to verify whether PH
                             Z
  of      concordant          pairs    between       AC1 (t)      and             via L1 -normtime series associated with the used indicator (AC1,
  {((t − 250) + 1) , · · · , ((t − 250) + 250)}, D is the number                  VAR, or MPS) can provide a reliable EWS at least 1 day before the
  of discordant pairs between [[Mathtype-mtef1-eqn-                               observed financial crisis.
  136.mtf]] and {((t − 250) + 1) , · · · , ((t − 250) + 250)}.                       In addition, since the Pearson correlation is usually applied
  Z = (250 × (250 − 1))/2 is the total number of different                        to time series whose probability distribution is symmetric, such
  possible pair combinations.                                                     as the normal or Gaussian probability distribution, it is better
                                                                     !
                         ((t−250)+250)
                               P                  ((t−250)+250)
                                                       P                          to consider other association correlation measures (Kendall’s
• rAC1,t =           250               ac1l · l −               ac1l              tau or Spearman’s rho) when the probability distribution for
                         l=((t−250)+1)            l=((t−250)+1)
                     !!                                                          the considered time series is asymmetric. Therefore, we also
     ((t−250)+250)
          P
                   l                                                              employed the skewness test to observe whether the probability
       l=((t−250)+1)                                                              distribution of the last 125 indicator values at the date from 750


Frontiers in Applied Mathematics and Statistics | www.frontiersin.org         8                                                    June 2022 | Volume 8 | Article 940133
Ismail et al.                                                                                                                  EWS of FCs Using PH and CSD



to 999 is asymmetric. As a result, we also computed the skewness            TABLE 1 | The classification matrix used in this study.
value for each of the Pearson correlation at the date t = 999.
                                                                                                                           Does there exist a nearest
    If the skewness value equals zero, the observed series is
                                                                                                                     financial crisis within the duration?
perfectly symmetrical. But a skewness of exactly zero is quite
unlikely for real-world data, so we interpreted the skewness value                                                   Exist                None
as follows:
                                                                            Has the correlation duration     Yes     EWS                    FA
• If skewness is between −1/2 and 1/2, the distribution                     exceeded the threshold?
  can be called approximately symmetric. For this case, the                                                  No       FN                    TN
  Pearson correlation is applicable to detect EWSs of impending
  financial crises.
• Otherwise, the distribution is called skewed, and the Pearson
  correlation is not considered.                                            Evaluation Measures
                                                                            For evaluation measures, the classification matrix used in
Threshold                                                                   our study is as given in Table 1. To evaluate the method’s
In this study, by using the test (Kendall’s tau, Pearson’s,                 performance, we used two classification scores (in percentage),
or Spearman’s rho correlation), if there exist two significant              namely probability of successful anticipation (PSA) and
correlation values, which indicate the significant rising trend             probability of erroneous anticipation (PEA). These two scores
in the observed indicator (AC1, VAR, or MPS) 1 day before                   are defined as follows: let A, B, C, and D be the total number of
the two corresponding observed financial crises (Dotcom crash               EWS, FA, FN, and TN, respectively, then
and Lehman Brothers bankruptcy) in the US, a threshold was
determined by choosing the smaller value of those two values.                            PSA = ((A + D)/(A + B + C + D) ) × 100%                         (7)
Let us assume that T1 and T2 are these two thresholds for the                            PEA = ((B + C)/(A + B + C + D) ) × 100%                         (8)
US market, then T = min {T1 , T1 } is the threshold covering
all available dates. The minimum value was chosen because it                To evaluate, a method that scores the highest PSA and the lowest
corresponded to the most extreme cases, which provided us with              PEA is considered the best EWS detection tool.
the longest period of significant rising trends in the correlation
time series (AC1, VAR, and MPS) before the Dotcom crash and
Lehman Brothers bankruptcy.                                                 RESULT
    After computing the threshold, all available dates were
                                                                            Two pre-crisis datasets were analyzed, whereby each of those
covered, and the likelihood of an indicative period of significant
                                                                            datasets had a length of 1,000 days before a financial crisis. In
rising trends, which lay above the threshold, was determined.
                                                                            the first row of Figure 5, the two pre-crisis datasets before the
The latter was made following the range of time at which the
                                                                            Dotcom crash and Lehman Brothers bankruptcy are presented,
indicative trend could be observed. Finally, all the recorded
                                                                            respectively. For all indices in each pre-crisis dataset, we
events (periods with significant rising trends and breakpoints or
                                                                            computed all its corresponding daily log-return time series and
without that signal) were classified either as EWSs, false alarms
                                                                            then combined all the computed daily log returns to build a high-
(FAs), false negatives (FNs), or true negatives (TNs) as described
                                                                            dimensional time series. Furthermore, the daily sliding window
in the later section.
                                                                            of length 50 was applied to obtain PCDs. Then, we applied PH on
                                                                            each PCD to obtain a corresponding L1 -norm value. As a result,
Classification
                                                                            we acquired a L1 −norm time series. All obtained L1 −norm time
In our practice, we classified any recorded event (a period with
                                                                            series for every pre-crisis dataset is illustrated in the second row
significant rising trends and breakpoints or without that signal)
                                                                            of Figure 5.
as a EWS, an FA, an FN, or a TN and is as follows:
                                                                                Figure 5 demonstrates that the L1 -norm time series exhibits
• If there is a nearest financial crisis that happened within               strong growth toward a primary peak prior to the Dotcom
  a period of continuous significant rising trends with                     crash and Lehman Brothers bankruptcy in the US market. These
  breakpoints, which lies above the threshold, we consider the              results are consistent with Gidea and Katz [25]and Ismail et
  event in this period as an EWS.                                           al. [26]. As stock indices become increasingly volatile when
• If there is no nearest financial crisis that happened within              moving closer to a financial crisis, more peaks appear in its
  a period of continuous significant rising trends with                     corresponding persistent landscape. The latter gives growth in
  breakpoints, which lies above the threshold, the event on this            the L1 -norm values prior to the Dotcom crash and Lehman
  period is considered as an FA.                                            Brothers bankruptcy [26].
• If there is a financial crisis that happened within a period                  Furthermore, the daily sliding window with the length of 500
  without the observed signal, which lies below the threshold,              was applied to each L1 -norm time series as shown in Figure 5,
  we consider the event in this period as an FN.                            and the corresponding time series of three CSD indicators,
• If there is no nearest financial crisis within a period without           including AC1, VAR, and MPS at low frequencies were obtained.
  the observed signal, which lies below the threshold, the event            Furthermore, for each computed CSD indicator’s time series,
  in this period is considered as a TN.                                     we applied the daily sliding window with a length of 250 and


Frontiers in Applied Mathematics and Statistics | www.frontiersin.org   9                                               June 2022 | Volume 8 | Article 940133
Ismail et al.                                                                                                                       EWS of FCs Using PH and CSD




  FIGURE 5 | (A,C) two pre-crisis datasets before the Dotcom crash and Lehman Brothers bankruptcy and (B,D) the two L1 -norm time series for these two datasets,
  respectively.




computed the time series of three tests: Kendall’s tau, Pearson’s,                   the corresponding p-values, and skewness) before the observed
and Spearman’s rho correlations. In addition, we also employed                       financial crises, we considered such method as a EWS detection
a significant test to compute p-values for each correlation test                     tool. It is clearly shown that only the MPS time series of the
1 day before the Dotcom crash and Lehman Brothers bankruptcy.                        L1 -norm time series fulfill this condition, and its significant rising
Figure 6 shows the time series of these CSD indicators (AC1,                         trend can be indicated by Kendall tau, Pearson, and Spearman
VAR, and MPS) and presented the obtained value for Kendall’s                         rho correlation. These because Kendall tau and Spearman rho
tau, Pearson’s, and Spearman’s rho correlations before the                           provide positive values and their corresponding p-values also
financial crises. Moreover, in Figure 6, corresponding p-values                      less than 0.05. For Pearson, this test obtains a positive value,
for Kendall’s tau, Pearson’s, and Spearman’s rho correlations                        its corresponding p-values is less than 0.05, and its skewness
and skewness measure (for the Pearson correlation only) are                          values lie in between −1/2 and 1/2 indicating that the data has
also mentioned. Kendall’s tau correlation, Pearson’s correlation,                    an approximately symmetrical distribution. For the others, they
Spearman’s rho correlation, p-values for Kendall’s tau correlation,                  did not achieve the above-mentioned characteristics, therefore
p-values for Pearson’s correlation, p-values for Spearman’s rho                      not considered as potential EWS detection tools.
correlation, and skewness values in Figure 6 are symbolized with                         In Figure 6, the highlighted values from different correlation
τ , r, p, pτ , pr , pp , and s, respectively.                                        tests (Kendall’s tau, Pearson’s, and Spearman’s rho) are the
     Based on the results presented in Figure 6, for any CSD                         chosen threshold to predict the whole available date. These
indicator of the L1 -normtime series, which consistently exhibits                    values are 0.88, 0.94, and 0.96 for Kendall’s tau, Pearson’s, and
a significant rising trend (indicated by the correlation values,                     Spearman’s rho correlations, respectively. Therefore, we have


Frontiers in Applied Mathematics and Statistics | www.frontiersin.org           10                                            June 2022 | Volume 8 | Article 940133
Ismail et al.                                                                                                                         EWS of FCs Using PH and CSD




  FIGURE 6 | Time series of the CSD indicators (AC1, VAR, and MPS), the obtained value for Kendall’s tau, Pearson’s, and Spearman’s rho correlations, and their
  corresponding p-values 1 day before the financial crises.




Frontiers in Applied Mathematics and Statistics | www.frontiersin.org            11                                             June 2022 | Volume 8 | Article 940133
Ismail et al.                                                                                                                          EWS of FCs Using PH and CSD




  FIGURE 7 | Results obtained from MPS of the L1 -norm time series using Kendall’s tau, Pearson’s, and Spearman’s rho correlations. (A) Kendall’s tau correlations of
  mean for power spectrum at low frequencies of L1 -norms; (B) Pearson’s rho correlations of mean for power spectrum at low frequencies of L1 -norms; (C) Spearman’s
  rho correlations of mean for power spectrum at low frequencies of L1 -norms.




three predictions performed using three different correlations,                        with black numbers and lines. Details on these recorded events
and each correlation is obtained from the MPS time series of                           and their corresponding classification as shown in Figure 7 for
the L1 -normtime series. For each prediction, all individual events                    Kendall’s tau, Pearson’s, and Spearman’s rho correlations are
(periods of continuous significant rising trends or otherwise) are                     provided in tables of Supplementary Material File.
recorded, and these events are then classified whether they are                           By using MPS of the L1 -norm time series, our results reported
EWSs, FAs, FNs, or TNs.                                                                that Spearman’s rho correlation test obtained the total number
   Results obtained from MPS of the L1 -normtime series                                of EWS, FA, FN, TN, PSA, and PEA of 4, 7, 7, 8, 46.15, and
using Kendall’s tau, Pearson’s, and Spearman’s rho correlations,                       53.85%, respectively. Furthermore, Kendall’s tau correlation test
respectively, are illustrated in Figure 7. All periods of continuous                   provided the total number of EWS, FA, FN, TN, PSA, and PEA
significant rising trends in Figure 7 are indicated by blue                            of 3, 8, 7, 8, 42.31, and 57.69%, respectively. In addition, the
numbers and lines, which lie above the threshold. In contrast,                         Pearson correlation test achieved the total number of EWS, FA,
correlation values that lie below the threshold are indicated                          FN, TN, PSA, and PEA of 2, 9, 9, 10, 40, and 60%, respectively.



Frontiers in Applied Mathematics and Statistics | www.frontiersin.org             12                                             June 2022 | Volume 8 | Article 940133
Ismail et al.                                                                                                                           EWS of FCs Using PH and CSD



TABLE 2 | A summary for all obtained results.                                            determined to predict the whole date, and then the classification
                                                                                         performance of our method is evaluated by using PSA and PEA.
Evaluation         Kendall’s tau            Pearson’s            Spearman’s rho
                                                                                             Our result shows that the L1 -norm time series exhibits a
measure           correlation test       correlation test        correlation test
                                                                                         strong growth before Dotcom Crash and Lehman Brothers
EWS                       3                      2                       4               Bankruptcy. This portrays that the L1 -norm time series
FA                        8                      9                       7               has the potential to be a representative to detect EWSs of
FN                        7                      9                       7
                                                                                         major financial crashes in the US market. Moreover, MPS
TN                        8                      10                      8
                                                                                         from the L1 -norm time series is significantly rising before
PSA (%)                42.31                     40                     46.15
                                                                                         these two financial crises. It has also been demonstrated
PEA (%)                57.69                     60                     53.85
                                                                                         that all correlation tests, Kendall’s tau, Pearson’s, and
                                                                                         Spearman’s rho, can indicate the observed significant
                                                                                         rising trend.
                                                                                             Overall, based on PSA and PEA, our results revealed that
All these results obtained are summarized in Table 2, where all                          Spearman’s rho correlation predicts the US market better
the bolded values represent the obtained highest scores for the                          than Kendall’s tau and Pearson’s correlations. Therefore, this
corresponding evaluation measure.                                                        study demonstrates that PH via its L1 -norm time series with
   From Table 2, based on PSA and PEA, Spearman’s rho and                                MPS and Spearman’s rho correlation offers a new potential
Kendall’s tau correlations are showed to obtain a better result                          EWS detection tool for financial crises in the US market.
than the Pearson correlation. This shows that non-parametric                             For future studies, we plan to examine and refine this
rank correlation, which computes statistical associations based                          method of PH to provide more reliable EWSs for upcoming
on the ranks of the data like Spearman’s rho and Kendall’s                               financial crises.
tau correlations is better than the Pearson correlation, which
measures the degree of the linear relationship between related                           DATA AVAILABILITY STATEMENT
variables. However, Spearman’s rho correlation, which measures
the degree of association between two variables is reported and                          Publicly available datasets were analyzed in this study. This data
has a better result as compared to Kendall’s tau correlation, which                      can be found here: https://finance.yahoo.com
measures the strength of dependence between two variables. In
addition, our result in Table 2 clearly shows that Spearman’s rho                        AUTHOR CONTRIBUTIONS
correlation outperforms other correlation tests (Kendall’s tau and
Pearson’s correlations) with the highest score of every evaluation                       MSI: conceptualization, methodology, software, validation,
measure. Therefore, by using MPS of the L1 -norm time series,                            writing–original draft, and writing–review and editing. MM:
our results concluded that Spearman’s rho correlation can detect                         conceptualization, supervision, validation, writing–review and
EWSs better than Kendall’s tau and Pearson’s correlations.                               editing, and funding acquisition. MI: supervision, data curation,
                                                                                         validation, writing–review and editing, funding acquisition. FA:
CONCLUSION                                                                               supervision, validation, writing–review and editing. All authors
                                                                                         contributed to the article and approved the submitted version.
In this study, PH and CSD were proposed to detect EWSs
of major financial crashes in the US market. Preliminarily,                              ACKNOWLEDGMENTS
two financial crises: Dotcom Crash and Lehman Brothers
Bankruptcy that happened in the US market were examined. By                              We would like to express our gratitude to the Universiti
using PH, L1 -norm time series was obtained for each financial                           Kebangsaan Malaysia and the Ministry of Higher Education
crisis and used to compute the CSD indicators: AC1, VAR,                                 Malaysia for their financial support via the provision of
and MPS.                                                                                 two grants with numbers: FRGS/1/2019/STG06/UKM/01/3 and
    By using three different correlation tests, Kendall’s tau,                           GUP-2020-032.
Pearson’s, and Spearman’s rho, the rising trend in these indicators
is observed prior to the financial crises. Furthermore, this study                       SUPPLEMENTARY MATERIAL
applied significance and skewness tests to determine whether
the rising trends in the indicators (AC1, VAR, or MPS) are                               The Supplementary Material for this article can be found
statistically significant. This test aims to conclude that the rising                    online at: https://www.frontiersin.org/articles/10.3389/fams.
trend does not happen by chance. Subsequently, a threshold is                            2022.940133/full#supplementary-material


REFERENCES                                                                               2. Gopalakrishnan EA, Sharma Y, John T, Dutta PS, Sujith RI. Early warning
                                                                                            signals for critical transitions in a thermoacoustic system. Sci Rep. (2016)
 1. D.S. Bates. Jumps and stochastic volatility: exchange rate processes                    6:35310. doi: 10.1038/srep35310
    implicit in deutsche mark options. Rev Financ Stud. (2015) 9:69–                     3. Gidea M, Goldsmith D, Katz Y, Roldan P, Shmalo Y. Topological
    107. doi: 10.1093/rfs/9.1.69                                                            recognition of critical transitions in time series of cryptocurrencies.




Frontiers in Applied Mathematics and Statistics | www.frontiersin.org               13                                            June 2022 | Volume 8 | Article 940133
Ismail et al.                                                                                                                                   EWS of FCs Using PH and CSD



    Physica A Stat Mech Appl. (2020) 548:123843. doi: 10.1016/j.physa.2019.                  26. Ismail MS, Noorani MSM, Ismail M, Razak FA, Alias MA. Early warning
    123843                                                                                       signals of financial crises using persistent homology. Phys A Stat Mech Appl.
 4. Virtanen T, Tölö E, Virén M, Taipalus K. Can bubble theory foresee banking                   (2022) 586:126459. doi: 10.1016/j.physa.2021.126459
    crises? J Financial Stab. (2018) 36:66–81. doi: 10.1016/j.jfs.2018.02.008                27. Aromi LL, Katz YA, Vives J. Topological features of multivariate distributions:
 5. Sornette D, Cauwels P. Financial bubbles: mechanisms and diagnostics. Swiss                  Dependency on the covariance matrix. Commun Nonlinear Sci Numer Simuls.
    Finance Institute Research Paper. (2014). doi: 10.2139/ssrn.2423790                          (2021) 103:105996. doi: 10.1016/j.cnsns.2021.105996
 6. H.J. Edison. Do indicators of financial crises work? An evaluation of an early           28. M. Gidea, Topological Data Analysis of Critical Transitions in Financial
    warning system. Int J Finance Econ. (2003) 8:11–53. doi: 10.1002/ijfe.197                    Networks. In: Shmueli E, Barzel B, Puzis R, (Eds.), 3rd International Winter
 7. Hubrich K, Tetlow RJ. Financial stress and economic dynamics:                                School and Conference on Network Science. Cham: Springer International
    The transmission of crises. J Monet Econ. (2015) 70:100–                                     Publishing (2017). pp. 47–59. doi: 10.1007/978-3-319-55471-6_5
    15. doi: 10.1016/j.jmoneco.2014.09.005                                                   29. Guo H, Xia S, An Q, Zhang X, Sun W, Zhao X. Empirical study of financial
 8. Quax R, Kandhai D, Sloot P. Information dissipation as an early-warning                      crises based on topological data analysis. Phys A Stat Mech Appl. (2020)
    signal for the Lehman Brothers collapse in financial time series. Sci Rep. (2013)            558:124956. doi: 10.1016/j.physa.2020.124956
    3:1–7. doi: 10.1038/srep01898                                                            30. Guo H, Zhao X, Yu H, Zhang X. Analysis of global stock markets’ connections
 9. Gatfaoui H, Peretti PDe. Flickering in information spreading                                 with emphasis on the impact of COVID-19. Phys A Stat Mech Appl. (2021)
    precedes critical transitions in financial markets. Sci Rep. (2019)                          569:125774. doi: 10.1016/j.physa.2021.125774
    9:1–11. doi: 10.1038/s41598-019-42223-9                                                  31. Yen PT, Xia K, Cheong SA. Understanding changes in the topology and
10. Squartini T, Van Lelyveld I, Garlaschelli D. Early-warning signals                           geometry of financial market correlations during a market crash. Entropy.
    of topological collapse in interbank networks. Sci Rep. (2013)                               (2021) 23:1211. doi: 10.3390/e23091211
    3:1–9. doi: 10.1038/srep03357                                                            32. Yen PT, Cheong SA. Using Topological Data Analysis (TDA) and persistent
11. Saracco F, Clemente RDi, Gabrielli A, Squartini T. Detecting early                           homology to analyze the stock markets in Singapore and Taiwan. Front
    signs of the 2007–2008 crisis in the world trade. Sci Rep. (2016) 6:1–                       Physics. (2021) 9:20. doi: 10.3389/fphy.2021.572216
    11. doi: 10.1038/srep30286                                                               33. Kim W, Kim Y-J, Lee G, Kook W. Investigation of flash crash via topological
12. Almog A, Shmueli E. Structural entropy: monitoring correlation-based                         data analysis. Topol Appl. (2021) 301:107523. doi: 10.1016/j.topol.2020.107523
    networks over time with application to financial markets. Sci Rep. (2019)                34. Nguyen NKK, Bui M. Detecting anomalies in the dynamics of a market index
    9:1–13. doi: 10.1038/s41598-019-47210-8                                                      with topological data analysis. Int J Syst Innovation. (2021) 6:37–50.
13. Flood MD, Lemieux VL, Varga M, Wong BW. The application of visual                        35. Katz YA, Biem A. Time-resolved topological data analysis
    analytics to financial stability monitoring. J Financial Stab. (2016) 27:180–                of market instabilities. Phys A Stat Mech Appl. (2021)
    97. doi: 10.1016/j.jfs.2016.01.006                                                           571:125816. doi: 10.1016/j.physa.2021.125816
14. Battiston S, Farmer JD, Flache A, Garlaschelli D, Haldane AG, Heesterbeek                36. Ismail MS, Hussain SI, Noorani MSM. Detecting early warning signals
    H, et al. Complexity theory and financial regulation. Science. (2016) 351:818–               of major financial crashes in bitcoin using persistent homology.
    9. doi: 10.1126/science.aad0299                                                              IEEE Access. (2020) 8:202042–57. doi: 10.1109/ACCESS.2020.303
15. D.     Sornette,     Why      Stock    Markets      Crash:     Critical    Events            6370
    in     Complex      Financial     Systems.   Princeton:       University    Press        37. Goel A, Pasricha P, Mehra A. Topological data analysis in investment
    (2017). doi: 10.23943/princeton/9780691175959.001.0001                                       decisions. Expert Syst Appl. (2020) 147:113222. doi: 10.1016/j.eswa.2020.11
16. Van Nes EH, Scheffer M. Slow recovery from perturbations as a generic                        3222
    indicator of a nearby catastrophic shift. Am Nat. (2007) 169:738–                        38. Baitinger E, Flegel S. The better turbulence index? Forecasting
    47. doi: 10.1086/516845                                                                      adverse financial markets regimes with persistent homology. Financ
17. Dakos V, Carpenter SR, Brock WA, Ellison AM, Guttal V, Ives AR,                              Mark Portf Manag. (2021) 35:277–308. doi: 10.1007/s11408-020-00
    et al. Methods for detecting early warnings of critical transitions in                       377-x
    time series illustrated using simulated ecological data. PLoS ONE. (2012)                39. Majumdar S, Laha AK. Clustering and classification of time series using
    7:e41010. doi: 10.1371/journal.pone.0041010                                                  topological data analysis with applications to finance. Expert Syst Appl. (2020)
18. Veraart AJ, Faassen EJ, Dakos V, van Nes EH, Lürling M, Scheffer M. Recovery                 162:113868. doi: 10.1016/j.eswa.2020.113868
    rates reflect distance to a tipping point in a living system. Nature. (2012)             40. Ismail MS, Md Noorani MS, Ismail M, Abdul Razak F, Alias MA. Predicting
    481:357–9. doi: 10.1038/nature10723                                                          next day direction of stock price movement using machine learning
19. Tan JPL, Cheong SSA. Critical slowing down associated with                                   methods with persistent homology: Evidence from Kuala Lumpur Stock
    regime shifts in the US housing market. Eur Phys J B. (2014)                                 Exchange. Appl Soft Comput. (2020) 93:106422. doi: 10.1016/j.asoc.2020.10
    87:1–10. doi: 10.1140/epjb/e2014-41038-1                                                     6422
20. Tan J, Cheong SA. The regime shift associated with the                                   41. E. Baitinger, and S. Flegel, New Concepts in Financial Forecasting: Network-
    2004–2008 US housing market bubble. PLoS ONE. (2016)                                         Based Information, Topological Data Analysis and their Combination.
    11:e0162140. doi: 10.1371/journal.pone.0162140                                               (2021). doi: 10.2139/ssrn.3962148
21. Guttal V, Raghavendra S, Goel N, Hoarau Q. Lack of critical slowing                      42. V. Robins, Towards computing homology from finite approximations. J Adv
    down suggests that financial meltdowns are not critical transitions,                         Stud Topol. (1999) 24: 503–32. Available online at: http://topology.nipissingu.
    yet rising variability could signal systemic risk. PLoS ONE. (2016)                          ca/tp/reprints/v24/tp24222.pdf
    11:e0144198. doi: 10.1371/journal.pone.0144198                                           43. Edelsbrunner H, Letscher D, Zomorodian A. Topological persistence and
22. Wen H, Ciamarra MP, Cheong SA. How one might miss early                                      simplification. In: Proceedings 41st Annual Symposium on Foundations of
    warning signals of critical transitions in time series data: A                               Computer Science. New York, NY: IEEE (2000). p. 454–63.
    systematic study of two major currency pairs. PLoS ONE. (2018)                           44. Zomorodian A, Carlsson G. Computing persistent homology.
    13:e0191439. doi: 10.1371/journal.pone.0191439                                               Discrete Comput Geom. (2005) 33:249–74. doi: 10.1007/s00454-004-
23. Diks C, Hommes C, Wang J. Critical slowing down as an                                        1146-y
    early warning signal for financial crises? Empir Econ. (2019)                            45. G. Carlsson. Topology and data. Bull New Ser Am Math Soc. (2009) 46:255–
    57:1201–28. doi: 10.1007/s00181-018-1527-3                                                   308. doi: 10.1090/S0273-0979-09-01249-X
24. Otter N, Porter MA, Tillmann U, Grindrod P, Harrington HA, A. roadmap                    46. Edelsbrunner         H,      Harer       JL,     Computational         Topology:
    for the computation of persistent homology. EPJ Data Science. (2017) 6:1–                    An          Introduction.        American          Mathematical          Society
    38. doi: 10.1140/epjds/s13688-017-0109-5                                                     (2022).
25. Gidea M, Katz Y. Topological data analysis of financial time                             47. Bubenik P, Dłotko P, A. persistence landscapes toolbox for topological
    series: Landscapes of crashes. Phys A Stat Mech Appl. (2018)                                 statistics. J Symb Comput. (2017) 78:91–114. doi: 10.1016/j.jsc.2016.
    491:820–34. doi: 10.1016/j.physa.2017.09.028                                                 03.009




Frontiers in Applied Mathematics and Statistics | www.frontiersin.org                   14                                               June 2022 | Volume 8 | Article 940133
Ismail et al.                                                                                                                                    EWS of FCs Using PH and CSD



48. Bubenik P. Statistical topological data analysis using persistence landscapes. J          the publisher, the editors and the reviewers. Any product that may be evaluated in
    Mach Learn Res. (2015) 16:77–102. doi: 10.48550/arXiv.1207.6437                           this article, or claim that may be made by its manufacturer, is not guaranteed or
                                                                                              endorsed by the publisher.
Conflict of Interest: The authors declare that the research was conducted in the
absence of any commercial or financial relationships that could be construed as a             Copyright © 2022 Ismail, Md Noorani, Ismail and Abdul Razak. This is an open-
potential conflict of interest.                                                               access article distributed under the terms of the Creative Commons Attribution
                                                                                              License (CC BY). The use, distribution or reproduction in other forums is permitted,
The handling editor MM declared a past collaboration with the authors.                        provided the original author(s) and the copyright owner(s) are credited and that the
                                                                                              original publication in this journal is cited, in accordance with accepted academic
Publisher’s Note: All claims expressed in this article are solely those of the authors        practice. No use, distribution or reproduction is permitted which does not comply
and do not necessarily represent those of their affiliated organizations, or those of         with these terms.




Frontiers in Applied Mathematics and Statistics | www.frontiersin.org                    15                                               June 2022 | Volume 8 | Article 940133