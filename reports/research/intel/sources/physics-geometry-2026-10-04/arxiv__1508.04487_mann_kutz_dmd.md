source: https://arxiv.org/pdf/1508.04487
fetched_utc: 2026-10-04T18:36:19Z
bytes_raw: 1688510

J. Mann & J. N. Kutz                                                                    DMD for Finance


                                                        Dynamic Mode Decomposition for Financial Trading Strategies
                                                                              Jordan Mann∗ and J. Nathan Kutz‡†

                                            Abstract. We demonstrate the application of an algorithmic trading strategy based upon the recently developed
                                                      dynamic mode decomposition (DMD) on portfolios of financial data. The method is capable of
                                                      characterizing complex dynamical systems, in this case financial market dynamics, in an equation-
                                                      free manner by decomposing the state of the system into low-rank terms whose temporal coefficients
                                                      in time are known. By extracting key temporal coherent structures (portfolios) in its sampling
                                                      window, it provides a regression to a best fit linear dynamical system, allowing for a predictive
                                                      assessment of the market dynamics and informing an investment strategy. The data-driven analytics
                                                      capitalizes on stock market patterns, either real or perceived, to inform buy/sell/hold investment
arXiv:1508.04487v1 [q-fin.CP] 18 Aug 2015




                                                      decisions. Critical to the method is an associated learning algorithm that optimizes the sampling and
                                                      prediction windows of the algorithm by discovering trading hot-spots. The underlying mathematical
                                                      structure of the algorithms is rooted in methods from nonlinear dynamical systems and shows that
                                                      the decomposition is an effective mathematical tool for data-driven discovery of market patterns.

                                            Key words. dynamic mode decomposition, Koopman operator, dynamical systems, financial trading, equation-
                                                      free.

                                            AMS subject classifications. 37E99, 37G99, 37L65


                                                1. Introduction. Algorithmic trading (alg trading) schemes are of growing importance in
                                            modern day financial investment strategies. In 2006, for instance, it was estimated that one
                                            third of all European Union and United States stock, along with 40% of the London Stock
                                            Exchange, were executed by trading algorithms. The advent of high-frequency trading, which
                                            was estimated in 2009 to accounted for 60-73% of all US equity trading volume [1, 2], has only
                                            added to the confluence of automated traders. Alg trading is driven by mathematical models
                                            and modern data-driven analytics which seek to capitalize on stock market patterns, either
                                            real or perceived, to inform buy/sell/hold investment decisions. The underlying mathematical
                                            structure of the algorithms is typically rooted in sophisticated statistical and probabilistic
                                            computational tools, thus providing risk measures and confidence intervals in the decision
                                            making process. We develop a trading scheme based upon ideas from nonlinear dynamical
                                            systems that capitalizes on evanescent signals in financial market data. Specifically, we apply
                                            the dynamic mode decomposition (DMD) [3, 4, 5, 6, 7, 8, 9], which is an emerging data
                                            analysis tool capable of integrating the power of time-series analysis with Principal Component
                                            Analysis (PCA), to financial data and portfolios of holdings. The DMD method extracts key
                                            temporal coherent structures (portfolios) in its sampling window and provides a regression to
                                            a best fit linear dynamical system, allowing for a predictive assessment of the current market
                                            and informing an investment strategy.
                                                The viewpoint advocated here assumes the stock market to be a complex, dynamical
                                            system that exhibits non-stationary, multi-scale phenomenon. But unlike standard dynamical
                                               ∗
                                                Harvard University, Cambridge, MA.
                                               †
                                                Department of Applied Mathematics, University of Washington, Seattle, WA. 98195-2420. ‡ (email:
                                            kutz@uw.edu) Questions, comments, or corrections to this document may be directed to that email address.
                                                                                                  1
J. Mann & J. N. Kutz                                                           DMD for Finance

systems methods, the DMD method does not enforce or prescribe an underlying dynamical
model. Rather, it is an equation-free method whereby the dynamics are reconstructed directly
from the data sampled over a specified window of time. Specifically, the DMD decomposes
stock portfolio data into low-rank features that behave with a prescribed time dynamics. In
the process, the least-square fit linear dynamical system allows one to predict short-time future
states of the system. These short-time predictions can be used to formulate successful trading
strategies by identifying transient, evanescent signals in the financial data. The method is
adaptive, updating its decomposition as the market changes in time. It also uses a learning
(machine learning) algorithm to track optimal sampling and prediction windows as these
change much more slowly in time and in different market sectors. The method is applied to
several markets (e.g. technology, bio tech, transport, banks) and is demonstrated to produce
a robust trading strategy.
    In a broader context, modeling of multi-scale systems, both in time and space, pervade
modern theoretical and computational efforts across the engineering, biological and physical
sciences. Driving innovations are methods and algorithms that circumvent the significant
challenges in efficiently connecting micro-scale to macro-scale effects that are separated po-
tentially by orders of magnitude spatially and/or temporally. As such, the origins of the DMD
method, which arose from pioneering work connecting the Koopman operator to dynamical
systems theory [10, 11], are associated with the fluid dynamics community and the modeling
of complex flows [5, 6]. Its growing success stems from the fact that it is an equation-free, data-
driven method [3] capable of providing accurate assessments of the spatio-temporal coherent
structures in a complex system, or short-time future estimates, thus potentially allowing for
control protocols to be enacted simply from data sampling. In the context of financial data,
the analogy of a spatial structure would be a portfolio of stock holdings.
     The DMD method exhibits many features of ARIMA (autoregressive integrated moving
averages) models and key extensions like SARIMA (Seasonal ARIMA) [12]. However, the
DMD method by construction correlates both temporal and spatial data simultaneously and
extracts low-rank features that a time-series or PCA analysis cannot individually. The DMD
algorithm also allows one to adapt the frequency and duration (sampling window) of the
market data collection to sift out information at different time scales, making different trading
strategies (e.g. high-frequency, daily trading, long-term trading etc) possible. Indeed, one can
use an iterative refinement process to optimize the snapshot sampling window for predicting
the future market. A critical innovation of DMD is its ability to handle transient phenomenon
and non-stationary data, which are typically weaknesses of SVD-based techniques. One can
also build upon recent innovations in multi-resolution DMD for mining for data features at
different timescales [13].
    The paper is outlined as follows: In Sec. 2 the basic DMD theory is outlined with an
emphasis on its dynamical approximation of data. This is followed in Sec. 3 by the development
of the DMD algorithm used in the subsequent applications. The application of the DMD to
trading strategies is outlined in Sec. 4 with various subsections demonstrating the efficacy of
the method. The paper is concluded in Sec. 5 with an outlook of the method as a modern
data tool for financial analysis.

                                                2
J. Mann & J. N. Kutz                                                           DMD for Finance

    2. Dynamic Mode Decomposition: An Equation-Free Architecture. The origins of the
DMD method are associated with the fluid dynamics community and the modeling of complex
flows. As with financial data, complex fluids exhibit dynamics that are difficult for model-
based approaches to accurately predict. Unlike fluids however, financial markets have no
known laws of nature, thus necessitating statistical modeling approaches. DMD is a natural
tool for financial modeling as its growing success stems from the fact that it is an equation-free,
data-driven method capable of providing accurate assessments of spatial-temporal coherent
structures in a given complex system, or short-time future estimates of such a systems, thus
allowing for state reconstruction and control protocols to be enacted simply from sampling.
    To be more precise, one may consider the DMD as an equation-free way to approximate
the nonlinear dynamics of a dynamical or complex system. We can formulate mathematical
framework of DMD by considering the governing set of differential equations:

                                        dx
(2.1)                                      = N (x, t; µ) ,
                                        dt
where x, in the interpretation here, is a portfolio of companies that are selected for evaluation.
The function N (·) is an unknown, dynamical process that is generally nonlinear and time-
dependent. Further, it may depend on a set of bifurcation parameters, µ, that can alter the
underlying dynamics.
    In addition to the governing equations, both measurements of the system, denoted by
G(·),

(2.2)                                     G(x, tk ) = 0 ,

where k = 1, 2, · · · , M for a total of M measurement times, and initial conditions are pre-
scribed

(2.3)                                      x(0) = x0 .

In applications of DMD to engineering and physical sciences, typically x is an n-dimensional
vector (n  1) that arises from either discretization of a complex system, or in the case of
applications such as video streams, it is the total number of pixels in a given frame. The
governing equations and initial condition specify a well-posed initial value problem. The
inclusion of measurements G(x, tk ), let’s say M of them, make the system overdetermined. By
including model error along with noisy measurements, one can formulate an optimal predictive
strategy using the data-assimilation framework and Kalman filtering innovations [3].
    Since in general the solution of governing nonlinear evolution (2.1) is not possible to con-
struct, numerical solutions are used to evolve to future states. In the DMD framework, recall
that the equation-free viewpoint assumes that the right-hand side governing the dynamics,
N (x, t; µ), is unknown. Thus the snapshot measurements and initial conditions alone are
used to approximate the dynamics and predict the future state. The DMD procedure thus
constructs the proxy, approximate linear evolution

                                            dx̃
(2.4)                                           = Ax̃
                                            dt
                                                3
J. Mann & J. N. Kutz                                                         DMD for Finance

with x̃(0) = x̃0 and whose well-known solution [14] is
                                             K
                                             X
(2.5)                              x̃(t) =         bk ψk exp(ωk t)
                                             k=1

where ψk and ωk are the eigenfunctions and eigenvalues of the matrix A. Of particular impor-
tance for finance is the interpretation of this solution. In particular, portfolio (DMD) modes
with a positive real part of ωk are exponentially growing solutions, thus making money, while
those with negative real part are exponentially decreasing and loosing money. Investment
strategies will be based upon the values of ωk achieved in the DMD decomposition.
    The ultimate goal in the DMD algorithm is to optimally construct the matrix A so that
the true and approximate solution remain optimally close in a least-square sense:

(2.6)                                  kx(t) − x̃(t)k  1.

Of course, the optimality of the approximation holds only over the sampling window where
A is constructed, but the approximate solution can be used to not only make future state
predictions, but also decompose the dynamics into various time-scales since the ωk are pre-
scribed. Moreover, the DMD makes use of low-rank structure so that the total number of
modes, K  N , allows for dimensionality reduction of the complex system.
     3. The DMD Decomposition and Algorithm. The DMD method provides a decompo-
sition of data into a set of dynamic modes that are derived from snapshots or measurements
of a given system in time. The mathematics underlying the extraction of dynamic informa-
tion from time-resolved snapshots is closely related to the idea of the Arnoldi algorithm [5],
one of the workhorses of fast computational solvers. The data collection process involves two
parameters:

                          N = number of companies in a given portfolio
                          M = number of data snapshots taken

Originally the algorithm was designed to collect data at regularly spaced intervals of time, e.g.
the daily opening price of a stock. However, new innovations allow for both sparse market [15]
and temporal [16] collection of data as well as irregularly spaced collection times [9]. To
illustrate the algorithm, we consider regularly spaced sampling in time:

(3.2)                      data collection times : tm+1 = tm + ∆t

where the collection time starts at t1 and ends at tM , and the interval between data collection
times is ∆t. In optimizing the method, the total number of snapshots is varied to determine
best performance.
    The data snapshots are arranged into an N × M matrix

(3.3)                         X = [x(t1 ) x(t2 ) x(t3 ) · · · x(tM )]

where the vector x are the N measurements of the state variable of the system of interest at
the data collection points. Specifically, each component of the vector x is a company that
                                                    4
J. Mann & J. N. Kutz                                                        DMD for Finance

comprises the portfolio of companies to be evaluated. The objective is to mine the data matrix
X for important dynamical information. For the purposes of the DMD method, the following
matrix is also defined:

(3.4)                          Xkj = [x(tj ) x(tj+1 ) · · · x(tk )]

Thus this matrix includes columns j through k of the original data matrix.
    The DMD method approximates the modes of the so-called Koopman operator. The
Koopman operator is a linear, infinite-dimensional operator that represents nonlinear, infinite-
dimensional dynamics without linearization [6, 17], and is the adjoint of the Perron-Frobenius
operator. The method can be viewed as computing, from the experimental data, the eigen-
values and eigenvectors (low-dimensional modes) of a linear model that approximates the
underlying dynamics, even if the dynamics is nonlinear. Since the model is assumed to be
linear, the decomposition gives the growth rates and frequencies associated with each mode.
If the underlying model is linear, then the DMD method recovers the leading eigenvalues
and eigenvectors normally computed using standard solution methods for linear differential
equations.
    Mathematically, the Koopman operator A is a linear, time-independent operator A such
that

(3.5)                                     xj+1 = Axj

where j indicates the specific data collection time and A is the linear operator that maps
the data from time tj to tj+1 . The vector xj is an N -dimensional vector of the data points
collected at time j. The computation of the Koopman operator is at the heart of the DMD
methodology. As already stated, the mapping over ∆ is linear even though the underlying
dynamics that generated xj may be nonlinear. It should be noted that this is different than
linearizing the dynamics.
    To construct the appropriate Koopman operator that best represents the data collected,
                −1
the matrix XM 1    is considered:

(3.6)                          X1M −1 = [x1 x2 x3 · · · xM −1 ] .

Making use of (3.5), this matrix reduces to
                             −1
                          XM     = x1 Ax1 A2 x1 · · · AM −2 x1 .
                                                             
(3.7)                      1

Here is where the DMD method connects to Krylov subspaces and the Arnoldi algorithm.
                                 −1
Specifically, the columns of XM1    are each elements in a Krylov space. This matrix attempts
to fit the first M − 1 data collection points using the Koopman operator (matrix) A. In the
DMD technique, the final data point xM is represented, as best as possible, in terms of this
Krylov basis, thus
                                            M
                                            X −1
(3.8)                                xM =           bm xm + r
                                            m=1
                                                5
J. Mann & J. N. Kutz                                                        DMD for Finance

where the bm are the coefficients of the Krylov space vectors and r is the residual (or error)
that lies outside (orthogonal to) the Krylov space. Ultimately, this best fit to the data using
this DMD procedure will be done in an L2 sense using a pseudo-inverse, i.e. the residual r is
minimized in the DMD procedure.
                                                                             −1
    Before proceeding further, it is at this point that the data matrix XM1      in (3.7) should
be considered further. In particular, our dimensionality reduction methods look to take ad-
vantage of any low-dimensional structures in the data. To exploit this, the SVD of (3.7) is
computed [18]:
                                          −1
(3.9)                                  XM
                                        1    = UΣV∗

where ∗ denotes the conjugate transpose, U ∈ CN ×K , Σ ∈ CK×K and V ∈ CM −1×K . Here K
                                                        −1
is the reduced SVD’s approximation to the rank of XM  1    . If the data matrix is full rank and
the data has no suitable low-dimensional structure, then the DMD method fails immediately.
However, if the data matrix can be approximated by a low-rank matrix, then DMD can take
advantage of this low dimensional structure to project a future state of the system. Thus once
again, the SVD plays the critical role in the methodology.
     Armed with the reduction (3.9) to (3.7), we can return to the results of the Koopman
operator and Krylov basis (3.8). In particular, we will consider constructing the matrix A
that gives the best approximation
                                           −1
(3.10)                                 AXM
                                         1    ≈ XM
                                                 2 .

But by using (3.8), the right hand side of this equation can be written in the form
                                         M −1
(3.11)                             XM
                                    2 = X1    S + re∗M −1

where eM −1 is the (M − 1)th unit vector and
                                                              
                                     0 ···          0    b1
                                   1 ...
                                                           
                                                   0    b2 
                                                            
(3.12)                       S =  0 ... ...              ..
                                                            .
                                                           
                                                          .
                                       .. ..               
                                         .   .     0 bM −2 
                                     0 ··· 0        1 bM −1

Recall that the bj are the unknown coefficients in (3.8).
    A key observation is that some of the eigenvalues of A can be determined by a similarity
transformation to the matrix Ã = UAU∗ . Thus we approximate the unknown Koopman
operator A with Ã, making the DMD method similar to the Arnoldi algorithm and its ap-
proximations to the Ritz eigenvalues [5]. Using equation (3.10) with (3.9) gives

(3.13)                                Ã = U∗ XM
                                               2 VΣ
                                                   −1
                                                      .
                                                                           −1
Recall that the matrices U, Σ and V arise from the SVD reduction of XM   1    in (3.9). This
is done in practice since in the fluids literature where DMD was developed, the matrix A is
                                               6
J. Mann & J. N. Kutz                                                             DMD for Finance

extremely high-dimensional and computing it directly is computationally challenging. The
matrix Ã, however, is of reduced dimension and can be computed relatively easily.
    Consider then the eigenvalue problem associated with Ã:

(3.14)                       Ãyk = µk yk             k = 1, 2, · · · , K

where K is the rank of the approximation we are choosing to make. The eigenvalues µk
capture the time dynamics of the discrete Koopman map A as a ∆t step is taken forward in
time. These eigenvalues and eigenvectors can be related back to the similarity transformed
original eigenvalues and eigenvectors of S in order to construct the DMD modes:

(3.15)                                       ψk = Uyk .

With the low-rank approximations of both the eigenvalues and eigenvectors in hand, the
projected future solution can be constructed for all time in the future. By first rewriting for
convenience ωk = ln(µk )/∆t (recall that the Koopman operator time dynamics is linear), then
the approximate solution at all future times, xDMD (t), is given by
                                 K
                                 X
(3.16)              xDMD (t) =         bk (0)ψk (x) exp(ωk t) = Ψdiag(exp(ωt)b
                                 k=1

where bk (0) is the initial amplitude of each mode, Ψ is the matrix whose columns are the
eigenvectors ψk , diag(ωt) is a diagonal matrix whose entries are the eigenvalues exp(ωk t), and
b is a vector of the coefficients bk .
    It only remains to compute the initial coefficient values bk (0). If we consider the initial
snapshot (x1 ) at time zero, let’s say, then (3.16) gives x1 = Ψb. This generically is not a
square matrix so that its solution

(3.17)                                        b = Ψ + x1

can be found using a pseudo-inverse. Indeed, Ψ+ denotes the Moore-Penrose pseudo-inverse
that can be accessed in MATLAB via the pinv command. As already discussed in the
compressive sensing section, the pseudo-inverse is equivalent to finding the best solution b
the in the least-squares (best fit) sense. This is equivalent to how DMD modes were derived
originally.
    Overall then, the DMD algorithm presented here takes advantage of low dimensionality
in the data in order to make a low-rank approximation of the linear mapping that best
approximates the nonlinear dynamics of the data collected for the system. Once this is done,
a prediction of the future state of the system is achieved for all time. Unlike the POD-Galerkin
method, which requires solving a low-rank set of dynamical quantities to predict the future
state, no additional work is required for the future state prediction outside of plugging in the
desired future time into (3.16). Thus the advantages of DMD revolve around the fact that (i)
no equations are needed, and (ii) the future state is known for all time (of course, provided
the DMD approximation holds).
    The algorithm is as follows:

                                                  7
J. Mann & J. N. Kutz                                                         DMD for Finance

(i) Sample data at N prescribed locations M times. The data snapshots should be evenly
spaced in time by a fixed ∆t. This gives the data matrix X.

                                                               −1
(ii) From the data matrix X, construct the two sub-matrices XM
                                                             1    and XM
                                                                       2 .

                                          −1
(iii) Compute the SVD decomposition of XM
                                        1    .

(iv) The matrix S̃ can then be computed and its eigenvalues and eigenvectors found.

(v) Project the initial state of the system onto the DMD modes using the pseudo-inverse.

(vi) Compute the solution at any future time using the DMD modes along with their projec-
tion to the initial conditions and the time dynamics computed using the eigenvalue of Ã.

    Recall that the future projection of step (vi), particularly the growth or demise of a
portfolio, is largely based upon the real part of the eigenvalues ωk computed in step (iv).
One interpretation of DMD is that we ultimately invest in eigenvalue distributions and their
associated DMD modes. The implementation of this algorithm in MATLAB can be found in
Ref. [3].
    4. Financial Trading with DMD. With the DMD theory in hand, we can turn our atten-
tion to building a trading algorithm which capitalizes on the predictions (3.16) of the theory.
The trading algorithm is parametrized by two key (integer) parameters:

                    m = number of past days of market snapshot data taken
                    ` = number of days in the future predicted.

Specifically, we will refer to the DMD prediction (3.16) with the notation

(4.2)                                     xDMD (m, `)

to indicate the past m number of days that are used to predict ` days in the future. This allows
us to specify both the market sampling window and how far in the future we are predicting.
Our objective is to use historical data to determine suitable combinations of (m, `) that give
the best predictive value. In particular, we look for what we term trading hot-spots, or regions
of (m, `) where the predictions are quite good. In the following subsection, we focus on two
key steps: (i) a training step in the algorithm for determining (m, `) and (ii) implementation
of trading based upon the results.
    4.1. Trading Algorithm and Training. The training algorithm allows us to learn more
about which inputs work best with DMD analysis for given sectors. The training alg looks
over a historic time period, whether that is 100 days or 10 years, in order to determine the
best choices of (m, `). We consider all possible combinations of (m, `) and their associated
success (prediction) rates. Since we are using historical data, we can compare the DMD
prediction with known market activity. Specifically, we evaluate if the DMD predicts that
the market increases or decreases, and we compare that to actual market activity. In what
                                               8
J. Mann & J. N. Kutz                                                         DMD for Finance

follows, we focused our attention on daily trading since that data was readily available through
Yahoo! [19]. We set limits that were suitable for the DMD algorithm, letting m = 1, 2, · · · , 25
days and allowing ` = 1, 2, · · · 10 days. As will be shown in the results, these appear to be
reasonable and effective values for determining the best combinations of (m, `).
     When we looked at the training alg over the last 10 years we could see consistent trading
hot-spots across sectors. Most hot-spots would look at the last 8-10 days of prices to make
the best prediction of the price in 4-5 days time. Hot-spots that had success rates greater
than 50% were promising because they would likely make money over time. The information
gathered about hot-spots allowed us to create a trading algorithm that would enter stock
market positions using results from DMD analysis each day and the solution (4.2).
     There were a few trading algorithms that we used throughout the project. However all of
them used the same three basic assumptions: (i) initial capital of $1 million, (ii) transaction
costs of $8 for each position, and (iii) all money would be invested evenly across all companies
in the portfolio. We had the flexibility to use any company, providing they had been publicly
trading for the time frame we were using, and we were able to combine as many companies
as we wished. For illustrative purposes, we tended to use ten companies as a proxy, or
representation, of each sector considered. The initial daily trading alg took given inputs
(m, `) for the sampling window and prediction window, and ran the DMD analysis each day.
Specifically, trading was performed using the DMD hot-spot prediction windows and capital
was divided equally among all companies in the portfolio. After we entered the position for
a given duration, we calculated how much money would have been made or lost by using
historical data. We also re-invested gains over the duration of the trade period. After the
alg had completed we compared our results to buying the benchmark, S&P 500, and also
compared it to buying and holding the individual stocks. Note that effects of slippage, for
instance, have been ignored in the trading scheme. However, the $8 per trade is a conservative
(high) estimate of trading costs that should offset such effects.
     The second trading alg we created did not use any information that one wouldn’t have if
they wanted to trade today; hence it was as realistic as possible. The algorithm would start
trading at day 101 because it would continuously use the previous 100 days to find the optimal
trading inputs from the training alg. Therefore the training alg would be used on a sliding
100 day window prior to the day the trading alg was executed. It would update its results
daily using the previous 100 days. Throughout our research we found that most sectors had
obvious, even prominent, hot-spots. However some sectors didnt have any clear hot-spot, and
they tended to be the sectors that underperformed in the trading alg.
     With this in mind, we created a third trading alg that looked into whether the inputs with
the maximum success rate were within a larger hot-spot region or isolated instances and likely
to have performed well over the last 100 days due to randomness. To do this, the trading
alg found out what inputs had the maximum success rate over the last 100 days, and then it
looked at the surrounding inputs to see if the mean success rate of all 9 neighboring (m, `) were
above a threshold. If a hot-spot region was found, then it would be classified as a hot-spot
and a trade would be executed. Otherwise the trading alg would hold the money until a hot-
spot appeared at a later date. When implementing this strategy, we used a hotspot threshold
of 53% so that we could be confident there truly was a hot-spot. This is perhaps the most
robust of the trading strategies as we demonstrated that markets with hot-spot regions where
                                               9
J. Mann & J. N. Kutz                                                                                                                                                                                  DMD for Finance


          100	
  
                                                                                                                                     0.5	
  
            10	
  
                                                                                                                                                                             ψ1 (x)
   ωj


                1	
  
   P



                                                                                                                                    -­‐0.5	
  
           0.1	
                                                                                                                               0                   5            10	
                    15	
  
   ωk /




                                                                                                                                     0.5	
  
          0.01	
                                                                                                                                                             ψ2 (x)
                      0	
     2	
         4	
      6	
     8	
                10	
     12	
              14	
     16	
     18	
  
                                                                                                                                    -­‐0.5	
  
                                                                                                                  k                            0                   5            10	
                    15	
  
                                                                   4	
  
                                                 ={ωk }                                                                              0.5	
                                   ψ3 (x)
                                                                   2	
  

                                                                                                                                    -­‐0.5	
  
                                                                                                                                           0                       5          10	
                      15	
  
           -­‐2	
                     -­‐1	
                       0	
                           1	
                       2	
  

                                                                                                              <{ωk }                 0.5	
                                   ψ4 (x)
                                                                   -­‐2	
  

                                                                                                                                    -­‐0.5	
  
                                                                   -­‐4	
                                                                    0                     5           10	
               x     15	
  


               0.6	
                                                                                                                                    0.6	
  

               0.4	
                                                                                                                                    0.4	
  

              0.2	
                                                                                                                                     0.2	
  

                      0	
                                                                                                                                  0	
  

            -­‐0.2	
                                                                                                                                -­‐0.2	
  

            -­‐0.4	
                                                                                                                                -­‐0.4	
  
                                                 Company 1                                                                                                             Company 2
                          0                           5                                 10	
                                 15	
                          0             5               10	
           15	
  
                                                                              DMD mode #                                                                                     DMD mode #


      Figure 4.1. DMD decomposition of an 18-day sampling of portfolio data in the biotech and healthcare
sector (17 companies): ’DHI’ ’LEN’ ’PHM’ ’TOL’ ’NVR’ ’HD’ ’LOW’ ’SHW’ ’ONCS’ ’BIIB’ ’AMGN’ ’CELG’
’GILD’ ’REGN’ ’VRTX’ ’ALXN’ ’ILMN’. The top left panel shows,  P on a log scale, the percentage of information
captured in each mode from the SVD decomposition (3.9) (σj / σk where σk are the diagonal elements of Σ).
The data, which is color coded throughout the figure, is shown to be dominated by a few leading modes (colored
red, blue, green and yellow in order of variance contained). The middle left shows the 17 eigenvalues ωk of
each mode used in the solution (3.16). Eigenvalues with <{ωi } > 0 represent growth modes. The 4 top right
panels shows the leading DMD modes (ψk (x)) and their composition from the 17 companies selected. The
first mode (red) shows the “background” portfolio, or average price of stocks, over the sampling window. The
decomposition of the first and second companies on the 17 DMD modes is shown in the bottom two panels where
the first four modes are highlighted.


quite amenable to the DMD strategy. Indeed, all market sectors showing a strong hot-spot
generated significant capital gains with the trading alg.

    4.2. DMD Decomposition in Sectors. To illustrate the DMD decomposition, we con-
sider first a sample of 17 companies over an 18-day trading window from the biotech and
healthcare sectors: ’DHI’ ’LEN’ ’PHM’ ’TOL’ ’NVR’ ’HD’ ’LOW’ ’SHW’ ’ONCS’ ’BIIB’
’AMGN’ ’CELG’ ’GILD’ ’REGN’ ’VRTX’ ’ALXN’ ’ILMN’. Figure 4.1 shows all aspects of
the resulting decomposition. Specifically, the singular values decomposition (3.9) produces a
diagonal matrix whose entries determine the modes of maximal variance. In this case, there
                                                                                                                                                   10
J. Mann & J. N. Kutz                                                                                                                                                                                   DMD for Finance


             100	
  
                                                                                                                                       0.5	
  
                                                                                                                                                                       ψ1 (x)
      ωj
               10	
  
      P


                  1	
                                                                                                                -­‐0.5	
  
              0.1	
                                                                                                                          0                    5              10	
                    15	
  
      ωk /



                                                                                                                                       0.5	
  
             0.01	
                                                                                                                                                    ψ2 (x)
                    0	
         2	
     4	
        6	
     8	
                   10	
     12	
             14	
     16	
      18	
  -­‐0.5	
  
                                                                                                                k                            0                    5              10	
                    15	
  
                                            ={ωk } 4	
                                                                                0.5	
                            ψ3 (x)
                                                                      2	
  
                                                                                                                                     -­‐0.5	
  
                                                                                                                                              0                   5              10	
                   15	
  
                -­‐2	
                  -­‐1	
                0	
                                  1	
                       2	
  
                                                                                                             <{ωk }                    0.5	
                           ψ4 (x)
                                                                      -­‐2	
  
                                                                                                                                     -­‐0.5	
  
                                                                                                                                                                  5              10	
                   15	
  
                                                                      -­‐4	
                                                                  0                                                    x
                0.4	
                                                                                                                                  0.4	
  


                 0.2	
                                                                                                                                 0.2	
  


                     0	
                                                                                                                                  0	
  


               -­‐0.2	
                                                                                                                            -­‐0.2	
  


               -­‐0.4	
                     Company 1                                                                                              -­‐0.4	
           Company 2
                            0                       5                                     10	
                                15	
                          0            5                10	
               15	
  
                                                                              DMD mode #                                                                                        DMD mode #


   Figure 4.2. DMD decomposition of portfolio data in the transport and home construction (18 companies):
’FDX’ ’UNP’ ’KSU’ ’NSC’ ’UPS’ ’CHRW’ ’UAL’ ’DAL’ ’LUV’ ’CSX’ ’DHI’ ’PHM’ ’TOL’ ’NVR’ ’HD’ ’LOW’
’SHW’ ’SPY’. The panels represent the same information as in Fig. 4.1 for these two new sectors.



a low-rank structure to the data as demonstrated in Fig. 4.1. The first mode is particularly
important as is represents the average price across the sampling window. The first four DMD
modes, which are composed of weightings of the 17 companies, are highlighted as they are
the most dominant structures in the data. The distribution of eigenvalues ωk are also illus-
trated, showing the modes which have growth, decay and/or oscillatory behavior. The DMD
scheme takes advantage of identifying the largest growth modes for investment purposes. Fi-
nally, the weighting of each company unto the DMD modes is also illustrated. This is the
information extracted at each pass of the DMD algorithm for a given data sampling window.
Figure 4.2 shows the same decomposition in the transport and home construction sectors
(18 companies): ’FDX’ ’UNP’ ’KSU’ ’NSC’ ’UPS’ ’CHRW’ ’UAL’ ’DAL’ ’LUV’ ’CSX’ ’DHI’
’PHM’ ’TOL’ ’NVR’ ’HD’ ’LOW’ ’SHW’ ’SPY’. Importantly, one can see the difference in the
growth modes between the sectors. This will be important for predicting successful sectors.
    Given the importance of the eigenvalues, we consider the DMD distribution of eigenvalues
(ωk ) over a 10 year period in three key market segments: biotech (’BIIB’ ’AMGN’ ’CELG’
’GILD’ ’REGN’ ’VRTX’ ’ALXN’ ’ILMN’ ’SPY), transportation and home construction (’FDX’
’UNP’ ’KSU’ ’NSC’ ’UPS’ ’CHRW’ ’UAL’ ’DAL’ ’LUV’ ’CSX’ ’DHI’ ’LEN’ ’PHM’ ’TOL’
                                                                                                                                                  11
J. Mann & J. N. Kutz                                                                                                                                                                              DMD for Finance



           Bio	
  Tech	
                                                                                           Transport	
  
                                        ={ωk } 4	
                                                                                           ={ωk } 4	
  

                                                  2	
                                                                                                  2	
  




             -­‐4	
          -­‐2	
               0	
                              2	
           4	
                  -­‐4	
           -­‐2	
          0	
                               2	
          4	
  
                                                                                             <{ωk }                                                                                               <{ωk }
                                                                450	
                                                                                              450	
  
                                                  -­‐2	
                                                                                               -­‐2	
  



                                                                   0	
                                                                                                0	
  
                                                  -­‐4	
                   0	
                             5	
                                                                0	
                              5	
  
                                                                                                                                                       -­‐4	
  
            Banks	
                     ={ωk }                                                                               Best	
   ={ωk }
                                                     4	
                                                                                                4	
  
                                                                                                                             Performers	
  	
  	
  

                                                    2	
                                                                                                 2	
  




               -­‐4	
          -­‐2	
               0	
                              2	
           4	
                -­‐4	
           -­‐2	
           0	
                               2	
          4	
  
                                                                                             <{ωk }                                                                 450	
  
                                                                                                                                                                                                  <{ωk }
                                                                450	
  
                                                     -­‐2	
                                                                                             -­‐2	
  


                                                                    0	
                                                                                                  0	
  
                                                                         0	
                                  5	
                                                                0	
                           5	
  
                                                    -­‐4	
                                                                                              -­‐4	
  




     Figure 4.3. DMD distribution of eigenvalues (ωk ) over a 10 year period in three key market segments:
biotech (’BIIB’ ’AMGN’ ’CELG’ ’GILD’ ’REGN’ ’VRTX’ ’ALXN’ ’ILMN’ ’SPY), transportation and home
construction (’FDX’ ’UNP’ ’KSU’ ’NSC’ ’UPS’ ’CHRW’ ’UAL’ ’DAL’ ’LUV’ ’CSX’ ’DHI’ ’LEN’ ’PHM’
’TOL’ ’NVR’ ’HD’ ’LOW’ ’SHW’ ’SPY ), and banks (’JPM’ ’MS’ ’DB’ ’CS’ ’BAC’ ’C ’BCS’ ’BX’ ’GS’ ’SPY).
Additionally, we have included the best performers in our data set from this 10 year period (’PCYC’ ’REGN’
’GMCR’ ’MDVN’ ’PCLN’ ’NFLX’ ’SPY). Each market segment has a different distribution of eigenvalues
that are clustered along the imaginary axis. Of importance is the distribution of eigenvalues with <{ωi } > 0,
i.e. those segments that represent the largest growth possibilities and/or volatility. The insets of each figure
represent a histogram of the distribution of the magnitude of the eigenvalues for each segment. The histograms
highlight that you cant tell the directionality of markets by looking at the eigenvalue magnitude, however sector
volatility may be possible. Additionally, one can characterize, via the eigenvalues, differences between rapidly
changing sectors versus slower changing sectors. Note that vertical structure in the distribution of eigenvalues
that is generated by the finite sampling window chosen.


’NVR’ ’HD’ ’LOW’ ’SHW’ ’SPY ), and banks (’JPM’ ’MS’ ’DB’ ’CS’ ’BAC’ ’C ’BCS’ ’BX’
’GS’ ’SPY). Figure 4.3 shows these eigenvalues, showing the clustering of eigenvalues along
the imaginary axis. The most important modes are those with the largest real part of the
eigenvalue. For each sector considered, the magnitude of the real part is plotted in a histogram,
showing the potential for growth in each sector.
    4.3. Performance Evaluation. The DMD decomposition can be used for trading by tak-
ing advantage of identifiable hot-spots in xDMD (m, `). As already outlined in the learning
algorithms section, the optimal m and ` can be identified and investments made accordingly.
                                                                                                           12
J. Mann & J. N. Kutz                                                                                                                                                                                                DMD for Finance



                                                                      Algorithm	
  Success	
  Rate:	
  Home	
  Construc6on	
  	
  
                                                                                                                                                                                                                                       0.525	
  
         10	
  
          9                                                                                                                                                                                                                            0.52	
  
          8                                                                                                                                                                                                                            0.515	
  
          7                                                                                                                                                                                                                            0.51	
  
          6                                                                                                                                                                                                                            0.505	
  
          5                                                                                                                                                                                                                            0.5	
  
          4                                                                                                                                                                                                                            0.495	
  
          3                                                                                                                                                                                                                            0.49	
  
          2                                                                                                                                                                                                                            0.485	
  
          1
                  1	
   2	
   3	
   4	
   5	
   6	
   7	
   8	
   9	
   10	
   11	
   12	
   13	
   14	
   15	
  16	
   17	
   18	
   19	
   20	
   21	
   22	
   23	
   24	
  
                                       =	
  Max	
  Accuracy	
                                                   =	
  Non-­‐Maximized	
  Inputs	
                                               =	
  Non-­‐Maximized	
  Inputs	
  

                    Algorithm	
  	
                                                                      Algorithm	
  	
                                                              Algorithm	
  	
  
           600%	
   S&P	
  500	
                                                      600%	
             S&P	
  500	
                                              600%	
             S&P	
  500	
  
           500%	
   Buy	
  and	
  Hold	
                                              500%	
             Buy	
  and	
  Hold	
                                      500%	
             Buy	
  and	
  Hold	
  

           400%	
                                                                     400%	
                                                                       400%	
  
           300%	
                                                                     300%	
                                                                       300%	
  
           200%	
                                                                     200%	
                                                                       200%	
  
           100%	
                                                                     100%	
                                                                       100%	
  
             0%	
                                                                       0%	
                                                                         0%	
  

                  0	
        100	
        200	
   300	
           400	
     500	
                0	
           100	
         200	
   300	
     400	
     500	
                0	
            100	
         200	
   300	
     400	
         500	
  
                                             Weeks	
                                                                           Weeks	
                                                                        Weeks	
  



     Figure 4.4. Success rates achieved using different sampling and prediction windows (m, `) for the DMD
algorithm when back testing. The hot-spot (top panel) shows a success rate of about 52.5% over the last 10
years, meaning that 52.5% of all the trades we executed were correct and made money. The bottom panels show
how much money the algorithm makes if we use different inputs for the DMD in comparison to the S&P 500 as
well as a buy-and-hold on the stocks used in the DMD algorithm. Using the best hot-spot xDMD (11, 5) gives the
best return of 21.48% annualized over 10 years, however using other inputs such as xDMD (11, 1) or xDMD (2, 5)
we still get promising results of 19.22% and 18.59% annualized respectively. When calculating the money we
made we ran the DMD and traded off its signal each day entering a position, either long or short, on every
company in the algorithm. In the case above we used 10 companies that are in the home construction sector
(’DHI’ ’LEN’ ’PHM’ ’TOL’ ’NVR’ ’HD’ ’LOW’ ’SHW’ ’SPY’).


As a specific example, Fig. 4.4 shows the hot-spot generated in the home construction sector.
The hot-spot has a success rate of about 52.5% over the last 10 years, meaning that 52.5% of
all the trades we executed were correct and made money. The bottom panels in this figure
shows how much money the algorithm makes if we use different inputs for the DMD. Using the
best hot-spot xDMD (11, 5) gives the best return of 21.48% annualized over 10 years, however
using other inputs such as xDMD (11, 1) or xDMD (2, 5) we still get promising results of 19.22%
and 18.59% annualized respectively. When calculating the money we made we ran the DMD
and traded off its signal each day entering a position, either long or short, on every company
in the algorithm. In the case above we used 10 companies that are in the home construction
sector (’DHI’ ’LEN’ ’PHM’ ’TOL’ ’NVR’ ’HD’ ’LOW’ ’SHW’ ’SPY’).
     We can expand the performance evaluation to a number of other sectors that exhibit
                                                                                                                                  13
J. Mann & J. N. Kutz                                                                                                                                                                DMD for Finance



                                       Transport	
                                               Home	
  Construc7on	
                                               Retail	
  
        10	
                                                                            10	
                                                 10	
  
                                                                                                                                                                                              0.52	
  
         9                                                                               9                                                    9
         8                                                                               8                                                    8                                               0.515	
  

         7                                                                               7                                                    7                                               0.51	
  
         6                                                                               6                                                    6                                               0.505	
  
         5                                                                               5                                                    5                                               0.50	
  
         4                                                                               4                                                    4
                                                                                                                                                                                              0.495	
  
         3                                                                               3                                                    3
         2                                                                               2                                                    2                                               0.49	
  
         1                                                                               1                                                    1                                               0.485	
  
                              5	
         10	
              15	
     20	
                         5	
         10	
     15	
         20	
               5	
        10	
     15	
      20	
  

           600%	
  
                                Transport	
  
           500%	
               Home	
  Construc7on	
  	
  
                                Retail	
  
                                S&P	
  500	
  
           400%	
  


           300%	
  


           200%	
  


           100%	
  


             0%	
  


                      0	
                          50	
                       100	
                 150	
                200	
               250	
             300	
                350	
      400	
  
                                                                                                                        Weeks	
  



     Figure 4.5. This figure highlights how the algorithm does across sectors with hot-spots vs the benchmark
index, the S&P 500. The adaptive, machine learning, aspect of the trading alg allows for different hot-spots and
it chooses the hot-spots that best fit the historic data. All three sectors in this example have obvious hotspots with
high success rates using different sampling and predictive windows, however they all outperform the benchmark
over the last 8 years. It is especially promising to see the lack of market correlation during the financial
crisis, when the benchmark decreased but all trading algs made money. The three sectors considered are (i)
transportation xDMD (8, 4): ’FDX’ ’UNP’ ’KSU’ ’NSC’ ’UPS’ ’CHRW’ ’UAL’ ’DAL’ ’LUV’ ’CSX’ ’SPY’, (ii)
home construction xDMD (11, 5): ’DHI’ ’LEN’ ’PHM’ ’TOL’ ’NVR’ ’HD’ ’LOW’ ’SHW’ ’SPY’ , (iii) retail
xDMD (8, 5): ’NFLX’ ’KR’ ’AMZN’ ’CVS’ ’WBA’ ’TGT’ ’COST’ ’PCLN’ ’SPY.


clear and identifiable trading hot-spots. Figure 4.5 shows the application of the method to
the transport, home construction, and retail sectors. These three sectors show a clear and
pronounced hot-spot at xDMD (8, 4), xDMD (11, 5) and xDMD (8, 5) respectively. If our trading
strategy is applied in these sectors, the returns are indicated in the bottom panel of this
figure. The hot-spots allow one to beat the S&P 5000 in all cases. In contrast, when no
hot-spots are evident, as demonstrated in Fig. 4.6 for the defense, healthcare and biotech
sectors, there is no longer a guarantee about performance as the algorithm no longer has a
clear trading target (hot-spot) to track. Note that in our third trading alg proposed, a lack of
a clear hot-spot would result in a holding strategy, thus avoiding trading with no clear signals.
    Finally, we consider the adaptation of the trading window as a function of time. In
particular, the sampling and prediction window change over time and it is crucial for the
algorithm to adjust xDMD (m, `) in order to continually optimize performance according to
                                                                                                                       14
J. Mann & J. N. Kutz                                                                                                                                                            DMD for Finance



                                        Defense	
                                                          Healthcare	
                                        Biotech	
  
        10	
                                                                            10	
                                               10	
  
                                                                                                                                                                                          0.515	
  
         9                                                                               9                                                  9
         8                                                                               8                                                  8                                             0.51	
  
         7                                                                               7                                                  7
         6                                                                               6                                                  6                                             0.505	
  

         5                                                                               5                                                  5                                             0.50	
  
         4                                                                               4                                                  4
         3                                                                               3                                                  3                                             0.495	
  
         2                                                                               2                                                  2
                                                                                                                                                                                          0.49	
  
         1                                                                               1                                                  1
                               5	
        10	
              15	
     20	
                        5	
        10	
     15	
        20	
               5	
       10	
     15	
      20	
  

          100%	
  
                               Defense	
  
            80%	
              Healthcare	
  
                               Biotech	
  
                               S&P	
  500	
  
            60%	
  

            40%	
  

            20%	
  

                 0%	
  

          -­‐20%	
  

          -­‐40%	
  


                       0	
                         50	
                       100	
              150	
                200	
               250	
             300	
               350	
       400	
  
                                                                                                                     Weeks	
  



     Figure 4.6.     This figure highlights how the algorithm does across sectors lacking trading hot-spots vs
the benchmark index, the S&P 500. Without a clear hot-spot, it is difficult for the DMD algorithm to find a
consistent sampling window for successful predictions. Indeed, the trading alg does not perform nearly as well
as when a clear hot-spot exists. There is still a low correlation between the alg and the benchmark during times
of crisis, and the alg has a lower volatility as well. The three sectors considered are (i) defense: ’BA’ ’LMT’
’UTX’ ’HON’ ’GD’ ’NOC’ ’RTN’ ’COL’ ’SPY’, (ii) healthcare ’JNJ’ ’PFE’ ’MRK’ ’GILD’ ’AMGN’ ’UNH’
’MDT’ ’BMY’ ’SPY’, (iii) biotech: ’BIIB’ ’AMGN’ ’CELG’ ’GILD’ ’REGN’ ’VRTX’ ’ALXN’ ’ILMN’ ’SPY.



the market data. Figure 4.7 demonstrates the sampling histogram for both the sampling
window and the prediction window. The learning algorithm changes the sampling window
and prediction window by using the last 100 days of data and finding the xDMD (m, `) with the
highest success rate. It then looks to see if it is a hot-spot, by evaluating if the 3x3 square,
with highest success in the center, has a mean of greater than 53%. If there is a hot-spot, it
will trade. Otherwise it holds the position. We chose to do this because, as shown in previous
figures, the alg works significantly better when hot-spots are detected. Under this algorithm,
we traded 83% of the time. The histogram of the sampling input window used for trading
peaks around a 9-day sampling window whereas the prediction window peaks at 5-days. The
histogram generated xDMD (9, 5) is consistent with the findings of Fig. 4.5. This adaptability
is an attractive feature of the method as the method can self-tune in order to improve its
efficacy.

                                                                                                                     15
J. Mann & J. N. Kutz                                                                                                                                                                                     DMD for Finance




                                  Algorithm	
  	
  
                                  S&P	
  500	
  
            100%	
                Buy	
  and	
  Hold	
  



              50%	
  



               0%	
  



             -­‐50%	
  




                          0	
                              50	
                         100	
              150	
              Weeks	
        200	
                 250	
                     300	
                   350	
  

                  35	
                                                                                                            50	
  
                                                                             9	
                                                                                             4	
  
                                                                                                                                  45	
  
                  30	
  
                                                                                                                                  40	
  
                  25	
                                                                                                            35	
  

                                                                                                                                  30	
  
                  20	
  
                                                                                                                                  25	
  
                  15	
  
                                                                                                                                  20	
  

                  10	
                                                                                                            15	
  
                                                                                                                                  10	
  
                    5	
  
                                                                                                                                    5	
  

                    0	
                                                                                                             0	
  
                      0	
                   5	
                     10	
             15	
         20	
               25	
            0	
               2	
     4	
                   6	
         8	
        10	
  



     Figure 4.7. This figure shows how the algorithm does when we change the sampling window and prediction
window as time evolves. In this example the alg looks at the last 100 days and finds the inputs with the highest
success rate. It then looks to see if it is a hotspot, by evaluating if the 3x3 square, with highest success in the
center, has a mean of greater than 53%. If there is a hot-spot, it will trade. Otherwise it holds the position.
We chose to do this because, as shown in previous figures, the alg works significantly better when hot-spots are
detected. Under this algorithm, we traded 83% of the time. The bar graphs on the bottom shows a histogram
of the sampling input window used for trading, and the peaks around a 9-day sampling window. Also shown
is a histogram of the prediction window with a peak 4-days. The xDMD (9, 4) is consistent with the findings of
Fig. 4.5.


    5. Conclusions and Outlook. Data-driven strategies for analyzing complex systems such
as market behaviors and fluctuations are of growing interest in the mathematical sciences.
Indeed, the integration of traditional data modeling methods from statistics and dynamical
systems theory can provide enabling strategies for exploiting patterns of activity in market
data. The dynamic mode decomposition presented here, which has been successfully im-
plemented in many areas of the engineering, physical and biological sciences, provides the
foundation of a robust and adaptive trading strategy that capitalizes on patterns in market
activities.
    Overall, The DMD method provides a decomposition of data into a set of dynamic modes
that are derived from snap shots or measurements of a portfolio over a given time period. The
DMD method approximates the modes of the so-called Koopman operator. The Koopman op-
erator is a linear, infinite-dimensional operator that represents nonlinear, infinite-dimensional
                                                                                                                          16
J. Mann & J. N. Kutz                                                                   DMD for Finance

dynamics without linearization, and is the adjoint of the Perron-Frobenius operator. The
method can be viewed as computing, from the experimental data, the eigenvalues and eigen-
vectors (low-dimensional modes) of a linear model that approximates the underlying dynamics,
even if the dynamics is nonlinear. By interpreting the DMD eigenvalues as corresponding to
prescribed time scale dynamics, one can extract coherent data structures in the data.
     One can envision a number of innovations to augment the proposed DMD strategy for
finance. Many are particularly attractive for applications across the engineering, physical
and biological sciences, and there is no reason to believe they would not also be effective in
financial settings. Such techniques make use of compressive sampling [15] of market data to
facilitate the collection of considerably fewer measurements. This reduction in the number
of measurements may have a broad impact in situations where data acquisition is expensive
and/or prohibitive. A second important direction revolves around recent innovations of the
DMD with control [20], which is capable of disambiguating between the underlying dynamics
and the effects of actuation, or external market drivers, resulting in accurate input-output
models. The method is data-driven in that it does not require knowledge of the underlying
governing equations, only snapshots of state and actuation data from historical, experimental,
or black-box simulations. One can envision developing such input-output models in various
market sectors. Finally, modern tools of statistical analysis and dimensionality-reduction have
become the workhorses for the burgeoning field of machine learning (ML). ML techniques aim
to capitalize on underlying low-dimensional patterns and clustering in data. In the dynamical
applications considered here, one might exploit these patterns, or DMD modes, by building
libraries of low-rank dynamical modes, much like is done with POD modes [21, 22, 23]. Such
DMD libraries for different dynamical regimes partner nicely with compressive sensing strate-
gies. Additionally, Kernel based techniques, which are at the core of support vector machines,
for instance, have already found successful application in the DMD architecture when consid-
ering more accurate, nonlinear dynamical reconstructions [24]. Maximum advantage should
be taken of such techniques when integrating the DMD architecture in applications.

    Acknowledgment. We are especially grateful for discussions with Steven Brunton, Joshua
L. Proctor and Jonathan Tu.


                                              REFERENCES

 [1] Rob Iati. The real story of trading software espionage. AdvancedTrading.com, July 10, 2009.
 [2] The New York Times. Times topics: High-frequency trading. AdvancedTrading.com, December 20, 2012.
 [3] J. N. Kutz. Data-driven modeling and scientific computing: Methods for Integrating Dynamics of Complex
         Systems and Big Data. Oxford Press, 2013.
 [4] P. J. Schmid and J. Sesterhenn. Dynamic mode decomposition of numerical and experimental data. In
         61st Annual Meeting of the APS Division of Fluid Dynamics. American Physical Society, November
         2008.
 [5] P. Schmid. Dynamic mode decomposition of numerical and experimental data. Journal of Fluid Mechan-
         ics, 656:5–28, 2010.
 [6] C. Rowley, I. Mezić, S. Bagheri, P. Schlatter, and D. Henningson. Spectral analysis of nonlinear flows.
         Journal of Fluid Mechanics, 641:115–127, 2009.
 [7] P. Schmid, L. Li, M. Juniper, and O. Pust. Applications of the dynamic mode decomposition. Theoretical
         and Computational Fluid Dynamics, 25(1-4):249–259, 2011.
                                                    17
J. Mann & J. N. Kutz                                                                     DMD for Finance

 [8] K. Chen, J. Tu, and C. Rowley. Variants of Dynamic Mode Decomposition: Boundary Condition, Koop-
         man, and Fourier Analyses. Journal of Nonlinear Science, 22(6):887–915, 2012.
 [9] J. Tu, C. Rowley, D. Luchtenberg, S. Brunton, and J. N. Kutz. On Dynamic Mode Decomposition:
         Theory and Applications. Journal of Computational Dynamics, 1:391–421, 2014.
[10] Igor Mezić and Andrzej Banaszuk. Comparison of systems with complex behavior. Physica D: Nonlinear
         Phenomena, 197(12):101 – 133, 2004.
[11] Igor Mezić. Spectral properties of dynamical systems, model reduction and decompositions. Nonlinear
         Dynamics, 41(1-3):309–325, 2005.
[12] D. B. Percival and A. T. Walden. Spectral analysis for physical applications. Cambridge University Press,
         1993.
[13] J. N. Kutz, X. Fu, and S. L. Brunton. Multi-resolution dynamic mode decomposition. arXiv:1506.00564,
         2015.
[14] W. E. Boyce and R. C. DiPrima. Elementary differential equations, 9th ed. Wiley, 2009.
[15] S. Brunton, J. Proctor, and J. N. Kutz. Compressive sampling and dynamic mode decomposition. Journal
         of Computational Dynamics, to appear (2015).
[16] Jonathan H Tu, Clarence W Rowley, J Nathan Kutz, and Jessica K Shang. Spectral analysis of fluid
         flows using sub-nyquist-rate piv data. Experiments in Fluids, 55(9):1–13, 2014.
[17] I. Mezić. Analysis of Fluid Flows via Spectral Properties of the Koopman Operator. Annual Review of
         Fluid Mechanics, 45:357–378, 2013.
[18] L. N. Trefethen and D. Bau. Numerical Linear Algebra. SIAM, Philadelphia, 1997.
[19] Yahoo! finance. finance.yahoo.com.
[20] J. Proctor, S. Brunton, and J. N. Kutz. Dynamic mode decomposition with control. arXiv:1409.6358,
         2014.
[21] I. Bright, G. Lin, and J. N. Kutz. Compressive sensing based machine learning strategy for characterizing
         the flow around a cylinder with limited pressure measurements. Physics of Fluids, 25:127102, 2013.
[22] S. Brunton, J. Tu, I. Bright, and J. N. Kutz. Compressive sensing and low-rank libraries for classification
         of bifurcation regimes in nonlinear dynamical systems. SIAM App. Dyn. Sys., 13:1716–1732, 2014.
[23] J. L. Proctor, B. Brunton, S. Brunton, and J. N. Kutz. Exploiting sparsity and equation-free architectures
         in complex systems. European Physics Journal Special Topics, 223:2665–2684, 2015.
[24] M. Williams, C. W. Rowley, and I. G. Kevrekidis. A kernel-based approach to data-driven koopman
         spectral analysis. arXiv:1411.2260, 2015.




                                                      18