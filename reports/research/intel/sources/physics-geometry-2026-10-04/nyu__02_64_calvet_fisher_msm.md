source: https://archive.nyu.edu/bitstream/2451/26508/2/02-64.pdf
fetched_utc: 2026-10-04T18:42:02Z
bytes_raw: 2828288

Regime-Switching and the Estimation of
               Multifractal Processes∗

                           Laurent Calvet
        Harvard University and NYU Stern School of Business

                           Adlai Fisher
         Faculty of Commerce, University of British Columbia

                       This Version: December 27, 2002
                         First Draft: March 2, 2002




   ∗
     Department of Economics, Littauer Center, Cambridge, MA 02138, and Department of
Finance, NYU Stern School of Business, 44 West Fourth Street, New York, NY 10012, lcal-
vet@aya.yale.edu; Finance Division, Faculty of Commerce, 2053 Main Hall, Vancouver, BC,
Canada V6T 1Z2, adlai.fisher@commerce.ubc.ca. We are grateful to John Campbell, Guido
Kuersteiner and Nour Meddahi for stimulating discussions. We also received helpful comments
from T. Andersen, T. Bollerslev, F. Diebold, R. Engle, J. Hamilton, J. MacKinnon, N. Shephard,
D. Smith, R. Tsay and seminar participants at the University of Chicago, the 2002 NSF-NBER
Time Series Conference, and the 2002 CIRANO Extreme Events in Finance Conference. Ex-
cellent research assistance was provided by Xifeng Diao. We are very appreciative of financial
support provided for this project by the Social Sciences and Humanities Research Council of
Canada under grant 410-2002-0641.
                              Abstract

We propose a discrete-time stochastic volatility model in which regime-
switching serves three purposes. First, changes in regimes capture
low frequency variations, which is their traditional role. Second, they
specify intermediate frequency dynamics that are usually assigned to
smooth autoregressive processes. Finally, high frequency switches gen-
erate substantial outliers. Thus, a single mechanism captures three
important features of the data that are typically addressed as distinct
phenomena in the literature. Maximum likelihood estimation is de-
veloped and shown to perform well in finite sample. We estimate on
exchange rate data a version of the process with four parameters and
more than a thousand states. The estimated model compares favor-
ably to earlier specifications both in- and out-of-sample. Multifractal
forecasts slightly improve on GARCH(1,1) at daily and weekly inter-
vals, and provide considerable gains in accuracy at horizons of 10 to
50 days.



JEL Classification: G0, C5.

Keywords: Forecasting, long memory, Markov regime-switching, max-
imum likelihood estimation, scaling, stochastic volatility, time defor-
mation, volatility component, Vuong test.




                                  2
1. Introduction
Regime-switching models (Hamilton 1989, 1990) have been extremely useful in
capturing the apparent nonstationarity of many macroeconomic and financial se-
ries. Despite the theoretical generality of the state space approach, empirical
applications most often limit its use to low frequency shifts and combine it with
alternative techniques to capture the rich dynamics of economic series.1 For exam-
ple in the volatility literature, the class of Markov-switching ARCH and GARCH
processes separately specifies three types of fluctuations: regime-switches at very
low frequencies, smooth ARCH or GARCH transitions at mid-range frequencies,
and a thick-tailed conditional distribution of returns at high-frequency (Cai, 1994;
Hamilton and Susmel, 1994; Gray, 1996; Klaassen, 2002).2 In contrast, this paper
shows that a pure regime-switching process can eﬀectively capture the dynamics
at all frequencies.
    Previous literature rarely investigates an application with a large number of
regimes. This is partly because a small number of states may seem suﬃcient
to capture low frequency regime switches. For a general formulation, a more
practical limitation is that the number of parameters grows quadratically in the
number of states. A natural solution consists of placing restrictions on the state
parameters and switching probabilities. For example, Bollen, Gray, and Whaley
(2000) use a set of parameter restrictions to more tightly specify a four regime
model.3 In this paper, we consider a pure regime-switching model with a dense
transition matrix by imposing a tight set of restrictions on regime parameters
and switching probabilities to parsimoniously specify volatility dynamics across a
wide range of frequencies. Our approach permits us to routinely estimate good-
performing models with over a thousand states and only four parameters using
   1
     One exception is Dueker (1997), who investigates regime switches in the tail-thickness of
the conditional density of stock returns and finds a highly leptokurtotic regime with duration of
about one week.
   2
     In addition to the Markov-switching GARCH processes considered in this paper, Hamilton’s
model has been extended by letting transition probabilities vary with past returns (Diebold,
Lee, and Weinbach, 1994), state occupation times (Durland and McCurdy, 1994), or exogenous
variates (Filardo, 1994; Perez-Quiros and Timmerman, 2000). See Hamilton and Raj (2002) for
a recent survey of this literature.
   3
     Duration-dependent Markov-switching models also use restrictions on state parameters and
switching probabilities. For example, Maheu and McCurdy (2000) expand a two-state model by
supposing that the volatility level and switching probabilities depend on the occupation time.
This results in a sparse transition matrix, in which the system either progresses in the same
state or switches to the other state.


                                               3
standard maximum likelihood methods.
    This paper builds on Calvet and Fisher (2001), which develops a time-stationary
formulation of multifractal diﬀusions as well as a weakly convergent sequence
of discretizations. Total volatility is specified as the multiplicative product of
a large but finite number of random components. It is assumed for simplicity
that these components are first order Markov and identical except for time scale.
Specifically, the only diﬀerence between components is that each has a diﬀerent
switching probability. The specification is completed by assuming that the pro-
gression of switching probabilities is approximately geometric. This parsimonious
specification delivers long-memory features in volatility and a decomposition into
components with heterogenous decay rates.
    The present paper develops a toolkit of econometric methods that can be used
to estimate and test multifractal processes. Calvet, Fisher, and Mandelbrot (1997)
introduce the multifractal model of asset returns (MMAR), a class of diﬀusions
that capture the outliers, moment-scaling and long memory in volatility exhib-
ited by many financial time series. While providing an excellent fit of the data,
the MMAR is based on a combinatorial construction that is not well-suited to
standard econometric techniques. In particular, regime changes take place at pre-
determined dates making the model non-stationary. Early eﬀorts to estimate the
MMAR have for this reason focused on unconditional moments of returns. More
specifically, the multifractal model implies that the moments of returns vary as
power functions of the frequency of observation, a property exhibited by a large
number of financial series.4 Calvet and Fisher (2002) use this property to build es-
timator and diagnostic tests of the MMAR. Lux (2001) similarly develop a GMM
estimator based on analytical expressions of high-frequency covariances.
    This paper considers instead the pure Markov-switching version of the MMAR.
This permits maximum likelihood (ML) estimation, an innovation which, to the
best of our knowledge, is new to the literature on multifractal measures and pro-
cesses. Our model and estimation techniques are easy to use and extend directly
from the original Hamilton regime-switching formulation. The main innovation
consists of introducing a tight and eﬀective set of restrictions on regimes and
transition probabilities. Monte Carlo simulations demonstrate the eﬀectiveness of
   4
    Financial economists are already familiar with a scaling property in the second moment
through the variance ratio statistic. Calvet, Fisher, and Mandelbrot (1997) and Calvet and
Fisher (2002) find evidence of moment-scaling in powers of the absolute value of returns. Further
evidence is provided by Andersen, Bollerslev, Diebold and Labys (2001) and Barndorﬀ-Nielsen
and Shephard (2003). See also LeBaron (2001) for a discussion of robustness.



                                               4
this technique in typical sample sizes. We apply this method to several exchange
rates and show that the multifractal model performs well in comparison with the
Student-GARCH(1,1) of Bollerslev (1987), and the Markov-switching GARCH
(MS-GARCH) of Klaassen (2002). The choice of these alternative processes is
guided by several considerations. Since the focus of the paper is ML estimation, it
is natural to choose models for which the likelihood function is readily available.
Furthermore, GARCH(1,1) is known to be an excellent contender for volatility
forecasting among the large class of ARCH / stochastic volatility processes (e.g.
Akgiray, 1989; Andersen and Bollerslev, 1998; Hansen and Lunde, 2001; Pagan
and Schwert, 1990; West and Cho, 1998). MS-GARCH processes, on the other
hand, combine regime-switching with the smooth weighting of past shocks. They
represent a potentially appealing compromise between GARCH and pure regime
switching models. Because the original process of Gray (1996) does not conve-
niently permit multistep forecasting, we instead consider the variant formulation
introduced by Klaassen (2002).
    The multifractal process compares favorably with GARCH(1,1) both in- and
out-of-sample. Our model has a higher likelihood in-sample for all currencies. The
statistical significance of this diﬀerence is confirmed by a HAC adjusted version of
the Vuong (1989) test. Furthermore since GARCH(1,1) and the regime-switching
model have the same number of parameters, the multifractal is preferred by stan-
dard selection criteria. Analogous results are obtained out-of-sample. While the
models’ one-day forecasts have similar performances, the multifractal model sub-
stantially outperforms GARCH(1,1) at longer horizons. The diﬀerence is most
pronounced for 20 and 50 days, for which the multifractal substantial outper-
forms GARCH(1,1) for all currencies. For example in the case of the British
Pound, the 50-day forecasting R2 is 27.3% for our model as compared to −2.6% for
GARCH(1,1). Similar improvements are obtained for other currencies. The em-
pirical evidence thus suggests that the multifractal model dominates GARCH(1,1)
both in- and out-of-sample.
    MS-GARCH provides substantially better fit than GARCH(1,1) in-sample.
This property is partly attributable to a larger number of parameters and sug-
gests the possibility of overfitting. Out-of-sample, MS-GARCH roughly matches
the performance of GARCH(1,1) at short horizons, which is consistent with the
findings of Klaassen (2002). At longer horizons, however, MS-GARCH is dom-
inated by GARCH(1,1), and the multifractal therefore appears as the best per-
forming model.
    A pure Markov switching model can thus capture the same dynamics that


                                         5
in previous literature have required not only regime-switching but also linear
GARCH transitions and a thick-tailed conditional distribution of returns. It is
striking that a single mechanism can play all three of these roles so eﬀectively. The
innovation that achieves this surprising economy of modeling technique is based
upon scale-invariance, an approach that has long been championed by Mandel-
brot (1963, 1997). In our regime-switching formulation, scale invariance provides
a specific set of restrictions on the regime parameters and transition probabilities
of a high dimensional state space.
    Section 2 presents the discrete-time model. Section 3 develops the ML esti-
mator and assesses its accuracy in Monte Carlo simulations. Section 4 provides
ML empirical results for four exchange rates. Section 5 compares our model with
alternative processes both in- and out-of-sample. Section 6 concludes. All proofs
are given in the Appendix.

2. The Multifrequency Regime-Switching Model
This section develops a discrete-time Markov process with multi-frequency stochas-
tic volatility. The process has a finite number k of latent volatility state variables,
each of which corresponds to a diﬀerent frequency.

2.1. Stochastic Volatility
We consider an economic series Xt defined in discrete time on the regular grid
t = 0, 1, 2, ..., ∞. In applications, Xt will be the log-price of a financial asset or
exchange rate. Define the innovations xt ≡ Xt − Xt−1 . A common modeling
methodology assumes that every period, the system is hit by a single shock that
progressively phases out over time (e.g. Engle, 1982). We consider instead an
economy with k components M1,t , M2,t , ..., Mk,t , which decay at heterogeneous
frequencies γ 1 , .., γ k . Such a model could be very unwieldy as the number k
becomes very large. We will see, however, that the process can be nonetheless
parsimoniously described by a small set of parameters.
    We model the innovations xt ≡ Xt − Xt−1 by

                            xt = σ(M1,t M2,t ...Mk,t )1/2 εt .                   (2.1)

The parameter σ is a positive constant. The random variables εt are IID standard
Gaussians N (0, 1). The random multipliers or volatility components Mk,t are
persistent, non-negative and satisfy E(Mk,t ) = 1. We consider for simplicity that

                                            6
the multipliers M1,t , M2,t ...Mk,t at a given time t are statistically independent.
The parameter σ is then equal to the unconditional standard deviation of the
innovation xt .
    Equation (2.1) defines a stochastic volatility model xt = σ t εt with the multi-
plicative structure σ t = σ(M1,t M2,t ...Mk,t )1/2 . We conveniently stack the period t
volatility components multipliers into a vector
                                    ¡                      ¢
                               Mt = M1,t , M2,t , ..., Mk,t .
                                                                 Q
For any m = (m1 , .., mk̄ ) ∈ Rk̄ , let g(m) denote the product k̄i=1 mi . Volatility
at time t is then σ t = σ[g (Mt )]1/2 .
    The properties of volatility are driven by the stochastic dynamics of the vector
Mt . We assume for simplicity that Mt is first-order Markov. This facilitates the
construction through time of {xt } and permits maximum likelihood estimation.
It is then natural to call Mt the volatility state vector, and each component Mk,t
a state variable. The econometrician observes the returns xt = σ[g (Mt )]1/2 εt , but
not the vector Mt itself. The vector Mt is therefore latent, and must be inferred
recursively by Bayesian updating.
    Each Mk,t follows a process that is identical except for time scale. Assume
that volatility state variables have been constructed up to date t − 1. For each
k ∈ {1, .., k̄}, the next period multiplier Mk,t is drawn from a fixed distribution
M with probability γ k , and is otherwise equal to its current value: Mk,t = Mk,t−1 .
The dynamics of Mk,t can be summarized as:
           Mk,t drawn from distribution M         with probability γ k
           Mk,t = Mk,t−1                          with probability 1 − γ k .
We assume for simplicity that switches and new draws from M are IID across k
and t. The volatility components Mk,t thus diﬀer in their transition probabilities
γ k but not in their marginal distribution M. These features greatly contribute to
the parsimony of the model.
    The transition probabilities γ ≡ (γ 1 , γ 2 , ..., γ k ) are specified as

                              γ k = 1 − (1 − γ 1 )(b ) ,
                                                    k−1
                                                                                 (2.2)
where γ 1 ∈ (0, 1) and b ∈ (1, ∞). This specification is introduced in Calvet and
Fisher (2001) in connection with the discretization of a Poisson arrival process.
Since 1 − γ k = (1 − γ 1 )(b ) , the logarithms of staying probabilities are exponen-
                            k−1


tially decreasing with k. Consider a process with very persistent components, or

                                          7
equivalently a very small parameter γ 1 . For small values of k, the quantity γ 1 bk−1
remains small and the transition probability satisfies:
                                    γ k ∼ γ 1 bk−1 .
The transition probabilities of low frequency components thus grow approximately
at rate b. At higher frequencies (γ k ∼ 1), the rate of increase slows down and
condition (2.2) guarantees that the parameter γ k remains lower than 1. In em-
pirical applications, it is numerically convenient to estimate parameters with the
same order of magnitude. Since γ 1 < ... < γ k̄ < 1 < b, we therefore use (γ k̄ , b) to
specify the set of transition probabilities.
    The parameter k determines the number of volatility frequencies in the model.
We will take this number as fixed, and view the choice of k as a model selec-
tion problem. This approach is consistent with the methodology employed for
ARMA(p, q) or GARCH(p, q), where estimation is developed for a fixed number
of lags and the determination of p and q is treated as a model selection problem.
The multifractal construction imposes only minimal restrictions on the marginal
distribution of the multipliers: M ≥ 0 and E(M) = 1. While the model allows
flexible parametric or even nonparametric specifications of M, this paper only
considers the most parsimonious setup. We assume that M is drawn from a fam-
ily of unit mean distributions that are specified by a single parameter m0 . Useful
examples include log-normal distributions: ln M ∼ N (m0 , −m20 /2), or binomial
random variables taking values m0 or 2 − m0 with equal probability. The full
parameter vector is then
                              ψ ≡ (m0 , σ, b, γ k̄ ) ∈ R4 ,
where m0 characterizes the distribution of the multipliers, σ is the unconditional
standard deviation of returns, and b and γ k̄ define the set of switching proba-
bilities. In Section 3, we will develop and empirically implement the maximum
likelihood estimation of this vector.
    We find it convenient to call this construct the Markov-Switching Multifrac-
tal (or alternatively Markov-Switching Multifrequency) process. The notation
MSM(k) will refer to versions of the model with k frequencies. Economic intu-
ition and earlier work suggest that the multiplicative structure (2.1) is appealing
to model the high variability and high volatility persistence exhibited by financial
time series. When a low level multiplier changes, volatility varies very discontinu-
ously and has strong degree of persistence. In addition, high frequency multipliers
introduce substantial outliers.

                                           8
2.2. Properties
The MSM construction permits low frequency regime shifts, and thus long volatil-
ity cycles in sample paths. We will see that in exchange rate series, the duration of
the most persistent component, 1/γ 1 , is typically of the same order as the length
of the data. Estimated processes thus tend to generate volatility cycles with peri-
ods proportional to the sample size, a property also apparent in the sample paths
of long memory processes. Long memory is often defined as the hyperbolic decline
in the autocovariance function as the lag goes to infinity. Fractionally integrated
processes generate such patterns by assuming that an innovation linearly aﬀects
future periods at a hyperbolically declining weight. As a result, fractionally in-
tegrated processes tend to be very smooth, and thus do not capture the highly
irregular volatility patterns exhibited by financial series. In contrast, our approach
generates both substantial variability and long cycles in the size of returns. It thus
represents an appealing modeling technique for financial econometrics. Further-
more as k̄ → ∞, the growing number of regime switches in the construction implies
that the limiting continuous time process lies outside the class of Itô diﬀusions.
The sample paths are continuous but exhibit a high degree of heterogeneity in
local behavior, which is characterized by a continuum of local Hölder exponents
in any finite time interval (Calvet and Fisher, 2002).
     In earlier work, we proposed a definition of long memory that applies to con-
tinuous time processes defined on a bounded time domain. This definition is
based on increments over progressively smaller intervals. Our discrete-time pro-
cess can also generate a hyperbolic decline in autocovariances for a range of lags.
For every integer n and every q ≥ 0, the autocovariance in levels is defined as
γ q (n) = Cov(|xt |q , |xt+n |q ). We show in the Appendix:

Proposition. For every n, 1 << n << bk̄ , the autocovariance in levels satisfies
γ q (n) ∝ n2d(q)−1 , where d(q) = logb {E(M q )/[E(M q/2 )]2 }.

Our discrete-time construction thus mimics the hyperbolic autocovariograms ex-
hibited by many financial series (e.g. Dacorogna et al., 1993; Ding and Granger,
1993). The connection between low frequency regime shifts and long memory has
been recently discussed in the literature (e.g. Diebold and Inoue, 2001).
    A representative return series is illustrated in Figure 1. The graph reveals
that multiple switching frequencies help generate large heterogeneity in volatility
levels and substantial outliers. This is notable since the return process has by
construction finite moments of every order. We will see that it is nonetheless

                                          9
suﬃcient to capture the tail properties of the exchange rate data. In Calvet
and Fisher (2001), we introduced Paretian tails by considering IID shocks of the
form εt = Zt Ωt , where {Zt } are IID standard Gaussians and {Ωt } are IID random
variables drawn from a Paretian distribution Ω. The random variable Ω is the limit
distribution of the squared variation of the price process over a fixed horizon, and
is thus fully specified by the vector (σ, m0 , b, γ ∗ ). We find it computationally more
convenient to consider the Gaussian case because the likelihood is then available
in closed-form. The discrete-time process with εt = Zt Ωt is a promising direction
for future research.

3. Maximum Likelihood Estimation
When the multiplier M has a discrete distribution, there exist a finite number of
volatility states. Standard filtering methods then provide the likelihood function
in closed-form.

3.1. Updating the State Vector
We assume in the rest of this¡paper that the multiplier
                                                   ¢        M takes a finite number of
values bm . The vector Mt = M1,t , M2,t , ..., Mk,t can therefore take d = bkm values
m1 , ..., md ∈ Rk . The dynamics of the Markov chain Mt are characterized by the
transition matrix A = (ai,j )1≤i,j≤d with components aij = P(Mt+1 = mj | Mt =
mi ).5
    Let n (.) denote the density of a standard normal. The density of the innovation
xt conditional on Mt is fxt (x |Mt = mi ) = [σg (mi )]−1 n [x/σg (mi )] . Consider the
conditional probabilities
                                      ¡                   ¢
                             Πjt ≡ P Mt = mj |x1 , .., xt
                             1          d
over the unobserved states
                         ¡ m1 , ..., dm¢ . Wed can stack these conditional probabilities
                                                                      d
in the row vector Πt = Πt , .., Πt ∈ R+ . Let ι = (1, ., 1) ∈ R . We know that
Πt ι0 = 1.
                            Qk̄     h                                       i
   5
       We note that aij =     k=1    (1 − γ k ) 1{mi =mj } + γ k P(M = mjk ) , where mik denotes the
                                                 k     k

mth component of vector m , and 1{mi =mj } is the dummy variable equal to 1 if mik = mjk ,
                               i
                                       k   k
and 0 otherwise. In Calvet and Fisher (2001) the transition matrix is diﬀerent because there it
is assumed that an innovation to a lower frequency multiplier causes innovations in all higher
frequency multipliers. Here, we assume that arrival times are independent across frequencies.


                                                  10
   Using Bayes’ rule, we update the new belief Πt+1 from the old belief Πt and
the new innovation xt+1 . Consider the function
                          "                          ¡      ¡ ¢¢ #
                            n (xt /σg (m1 ))        n xt /σg md
                 ω(xt ) =                    , ...,                .
                                σg (m1 )               σg (md )

and let x ∗ y denote the Hadamard product (x1 y1 , .., xd yd ) of any x, y ∈ Rd . We
show in the Appendix that
                                         ω(xt+1 ) ∗ (Πt A)
                             Πt+1 =                           .                  (3.1)
                                       [ω(xt+1 ) ∗ (Πt A)] ι0
This formula expresses the conditional probability Πt+1 as a function of the ob-
servation xt+1 and the probability Πt calculated in period t. These results imply
that we can recursively calculate Πt . Since the multipliers (M1,1 , .., Mk,1 ) are in-
                                                                 Q
dependent, the initial vector Π0 is uniquely determined by Πj0 = kl=1 P(M = mjl )
for all j.

3.2. The Likelihood Function
Having solved the conditioning problem, we show in the Appendix that the log
likelihood function is
                                                X
                                                T
                    ln L (x1 , ..., xT ; ψ) =         ln[ω(xt ) · (Πt−1 A)].
                                                t=1

For a fixed k̄, we know that the maximum likelihood estimator (ML) is consis-
tent and asymptotically eﬃcient as T → ∞. An important diﬀerence between
our model and standard Markov switching models stems from the parsimonious
parameterization of the transition matrix A. This allows us to estimate the model
with reasonable precision even in the presence of a very large state space. While
the Expectation Maximization (EM) algorithm proposed in Hamilton (1990) is
not directly applicable with constrained transition probabilities, we find that nu-
merical optimization of the likelihood function produces good results.

3.3. Small Sample Properties
This section assesses the small sample properties of the ML estimator in Monte
Carlo simulations. The models investigated have k̄ = 8 frequencies, which is large

                                                11
enough to represent specifications that perform well in later empirical sections.
We also restrict attention to the simple binomial specification where the multiplier
M takes values m0 and 2 − m0 with equal probability.
    The four required parameters are thus the binomial value m0 , the unconditional
standard deviation σ, the frequency growth rate b, and the high frequency switch-
ing probability γ k . The choice of the unconditional standard deviation is not con-
sequential since it is simply a normalization of size, and we therefore choose σ = 1.
The remaining parameters are set to values that are representative of empirical
results in later sections. Specifically, all simulations have b = 3 and γ k = 0.95,
and the binomial parameter takes one of three values m0 ∈ {1.3, 1.4, 1.5}. We also
consider three sample lengths T ∈ {T1 , T2 , T3 }, where T1 = 2, 500, T2 = 5, 000,
and T3 = 10, 000.
    Table 1 reports the simulation results. Each of the nine columns is based on a
diﬀerent combination of one of the three values of m0 with one of the three values of
the sample length T . For each column, we simulate 400 independent sample paths
of the corresponding model and sample length. Maximum likelihood estimation
then provides a set of parameter estimates and asymptotic standard errors for
each path.6 The table has four rows corresponding to each parameter. The
first row gives the average point estimate over the simulated paths. The second
row is the standard error of these point estimates, or the finite sample standard
error (FSSE). The third row gives the root mean squared error (RMSE) of the
parameter estimates relative to the true parameter values.7 Finally, the average
asymptotic standard error (AASE) gives the average over the 400 simulations of
the asymptotic standard errors calculated from the information matrix. As sample
size becomes large, we expect that the AASE and the FSSE become close.
    The results of Table 1 show that maximum likelihood estimation works well.
For m0 , σ, and b, the biases are small and become negligible as sample size in-
creases. The parameter m0 has a low standard error relative to its size and is
thus well identified, which is important because this parameter largely determines
the variability of volatility. By contrast, the unconditional standard deviation σ
has standard errors that, although declining as expected with sample length, are
   6
     We start the optimizations at the true parameter values and iterate to convergence once.
Preliminary work considered searching for multiple local optima, and although these occasionally
exist, they do not significantly aﬀect the means or standard deviations of the reported Monte
Carlo results.
   7
     The RMSE will always be greater than or equal to the FSSE, and equal to the FSSE only
when the average point estimate is identical to the true parameter value.



                                              12
roughly ten percent of the true parameter value. We interpret this result as a
strength of the model, as it is consistent with the idea that low-frequency vari-
ations create considerable uncertainty about long-run averages. The parameter
b shows a moderate degree of uncertainty about the amount of spacing between
frequencies. Finally, the high-frequency switching probability γ k̄ is the only pa-
rameter that shows more than a small bias. This disappears quickly as sample
size increases, and the standard errors are not generally large. Overall the Monte
Carlo simulations show that maximum likelihood estimation produces reliable re-
sults given the sample sizes considered in subsequent sections. We also note that
the convenience and eﬃciency of maximum likelihood oﬀers significant advantages
relative to previous moment-based estimators for multifractal processes.

4. Empirical Results
Using a binomial specification for the multiplier M, we apply ML estimation to
four exchange rate series and obtain preferred specifications with a large number
of volatility frequencies.

4.1. Exchange Rate Data
The empirical analysis uses daily exchange rate data for the Deutsche Mark
(DEM), Japanese Yen (JPY), British Pound (GBP), and Canadian Dollar (CAD),
all against the US Dollar. The data consists of daily prices reported at noon by
the Federal Reserve Bank of New York.8 The fixed exchange rate system broke
down in early 1973, and the DEM, JPY and GBP series accordingly begin on 1
June 1973. The CAD series starts a year later (1 June 1974) because the Cana-
dian currency was held essentially at parity with the US Dollar for several months
after the demise of Bretton Woods. The Deutsche Mark was replaced by the Euro
at the beginning of 1999. The DEM data accordingly ends on 31 December 1998,
while the other three series run until 30 June 2002. Overall, the series contains
6,420 observations for the Deutsche Mark, 7,049 observations for the Canadian
Dollar, and 7,299 observations for the Yen and the Pound.
    Figure 2 plots the daily returns of each series. Consistent with earlier studies,
we observe apparent volatility clustering on a range of frequencies. For each
series, Table 2 reports the square root of average squared returns computed over
   8
    More specifically, the data consist of buying rates for wire transfers at 12:00 PM Eastern
time.


                                             13
the entire sample and over four subsamples of equal length. We observe that the
sample standard deviation can vary quite substantially across subperiods, which
is consistent with the low-frequency regime shifts in our model.

4.2. ML Estimation Results
Table 3 reports MLE results for all four currencies. The columns of the table
correspond to the number of frequencies k̄ varying from 1 to 10. The first column
is thus a standard Markov-switching model with only two possible values for
volatility. As k̄ increases, the number of states increases at the rate 2k̄ . There are
thus over one thousand states when k̄ = 10.
    We first examine the DEM data, and note that the multiplier value m̂ tends
to decline with k̄. This is because with a larger number of volatility components,
less variability is required in each individual component to generate the same
aggregate amount of stochastic volatility. The estimates of σ̂ show variability of a
diﬀerent type across k̄, with no particular pattern of increasing or decreasing. This
is again consistent with the idea that the long-run average of volatility is diﬃcult
to identify in a model that permits long volatility cycles. We finally examine the
frequency parameters γ̂ k̄ and b̂. When k̄ = 1, the parameter γ̂ k̄ indicates a switch
in the single multiplier a little less than once every two weeks. As k̄ increases, the
switching probability of the highest frequency multiplier increases until for large
values of k̄ a switch occurs almost every day. At the same time, the estimated
value b̂ decreases steadily with k̄. We can use (2.2) to calculate that when k̄ = 10,
a switch in the lowest frequency multiplier occurs approximately once every ten
years, or about one third the sample size. Thus, as k̄ increases, the range of
frequencies spreads out while the spacing between frequencies becomes tighter.
    The parameter estimates for the other three currencies show many similarities.
In all cases, the value of m̂ tends to decrease with k̄. We also observe that the
values of m̂, and thus the importance of stochastic volatility, are largest for JPY
and GBP and smallest for CAD. Consistent with this, variability across k̄ in
the estimates of σ̂ is also greatest for JPY and GBP and least for CAD. As k̄
increases all currencies also show the highest frequency multiplier switching more
often and the spacing between frequencies becoming tighter. The spacing between
frequencies is widest for JPY and GBP and tightest for CAD. We correspondingly
observe that the duration of the lowest frequency multiplier is longest for JPY at
approximately three times the sample size, and smallest for CAD at approximately
one tenth the sample size. We also note that all asymptotic standard errors are


                                          14
roughly consistent with the magnitudes obtained in our Monte Carlo simulations,
although in the empirical results somewhat smaller for σ̂ and slightly larger for
the frequency location parameters
                           ¡ ¢        γ̂ k̄ and b̂.
     The estimated MSM k̄ processes generate substantial outliers for large values
of k̄ despite the fact that they have finite moments of every order. To confirm this,
for each data set we use the estimated process with k̄ = 10 frequencies to generate
ten thousand paths of the same length as the data. We then compute a Hill tail
index α for each simulated path. Basing the index on 100 order statistics, the
empirical tail index and the average α in the simulated samples are respectively
equal to 4.74 and 4.34 (DEM), 3.91 and 3.75 (JPY), 4.59 and 4.03 (GBP), and
4.40 and 4.79 (CAD). Furthermore, for all currencies we cannot at the 10% level
reject equality of the simulated and empirical tail statistics. This result is caused
by the high frequency variations in volatility in the MSM model. With the highest
frequency multipliers taking new values almost daily, the distribution of returns
is strongly aﬀected by being composed of a mixture of distributions. Even though
this mixture of distributions has finite moments of every order, it is more than
suﬃcient to capture the tail characteristics of the data, even in sample sizes as
large as almost thirty years of daily observations.
     We finally examine the behavior of the log-likelihood function. For each cur-
rency, as we increase the number of frequencies k̄ the likelihood increases substan-
tially when k̄ is low. As k̄ gets larger, the likelihood continues to increase in most
cases, but at a decreasing rate. The only exception to the monotonic increase in
likelihood is the DEM series, for which the likelihood reaches a peak at k̄ = 7.
In all other cases the likelihood reaches a maximum at k̄ = 10. This behavior
of the likelihood confirms one of the main premises of the multifractal approach.
Specifically, volatility fluctuations have a multiplicity of frequencies, and explic-
itly incorporating a larger number of frequencies results in a better fit. The next
section examines the statistical significance of these increases in the likelihood
function.

4.3. Model Selection
This section investigates whether the estimated MSM(k̄) models have significant
diﬀerences in likelihoods. We compare two processes MSM(k̄) and MSM(k̄ 0 ),
k̄ 6= k̄0 , with respective likelihoods f and g. The processes are non-nested and




                                         15
have log-likelihood diﬀerence:

                                          1 X f (xt |x1 , ..., xt−1 )
                                              T
                 √
                  T (ln LfT − ln LgT ) = √      ln                      .
                                           T t=1 g(xt |x1 , ..., xt−1 )

Consider the null hypothesis that the models have identical unconditional ex-
pected log-likelihoods. When the observations {xt } are IID, Vuong (1989) shows
that the diﬀerence ln LfT − ln LgT is asymptotically normal under the null.9 In
addition, the variance of this diﬀerence is consistently estimated by the sample
variance of the addends ln[f (xt |x1 , ..., xt−1 )/g(xt |x1 , ..., xt−1 )]. Because it is a
strong assumption that the conditional likelihoods are IID, we construct in the
Appendix a HAC-adjusted version of the Vuong test. Our discussion is a sim-
plified version of the broader approach recently proposed by Rivers and Vuong
(2002).
    For each k̄ ∈ {1, .., 9}, we test in Table 4 the null hypothesis that MSM(k̄)
and MSM(10) fit the data equally well. Since HAC-adjusted tests tend to perform
poorly in small samples,10 we compute t-ratios and one-sided p values using both
the original and the HAC-adjusted methods. For k̄ ∈ {1, 2, 3}, the log-likelihood
diﬀerence is significant at the 1% level in the non-adjusted case (Table 4A) and at
the 5% level in the HAC case (Table 4B). This is strong evidence that MSM(10)
significantly outperforms models with 1 to 3 frequencies. For k̄ ∈ {4, 5}, we
reject the null at the 5% (non-adjusted) and 20% (HAC-adjusted) levels in almost
all cases. We view these results as rather substantial evidence that MSM(10)
outperforms models with 4 or 5 frequencies. Lower significance levels are obtained
for larger values of k̄, and the overall conclusion is that the MSM model works
better for larger numbers k̄ of frequencies. For this reason and also to maintain
consistency in the remaining analysis, we henceforth focus on the MSM(k̄ = 10)
process for all currencies.

5. Comparison with Alternative Models
This Section compares the multifractal model with GARCH(1,1) and Markov-
switching GARCH (MS-GARCH) both in- and out-of-sample.
   9
    See the Appendix for a more detailed discussion of Vuong tests.
  10
    See for example Andrews (1991), Andrews and Monahan (1992), and den Haan and Levin
(1997).



                                            16
5.1. In-Sample Comparison
                                                                 1/2
We consider alternative processes of the form xt = ht et , where ht is the con-
ditional variance of xt at date t − 1, and {et } are IID Student innovations with
unit variance and ν degrees of freedom (d.f.’s). GARCH(1,1) assumes the re-
cursion ht+1 = ω + αε2t + βht . MS-GARCH combines short-run autoregressive
dynamics with low frequency regime shifts (Gray, 1996; Klaassen, 2002). A latent
state st ∈ {1, 2} follows a first-order Markov process with transition probabilities
pij = P(st+1 = j|st = i). In every period, the econometrician observes the return
xt but not the latent st . For i = {1, 2}, let ht+1 (i) = V art (xt+1 |st+1 = i) de-
note the variance of xt+1 conditional on past returns {xt }ts=1 and st+1 = i. The
quantity ht is latent in every period, and the econometrician can similarly de-
fine Et [ ht (st ) |st+1 = i] , the expectation of ht conditional on st+1 = i and past
returns. Klaassen (2002) assumes the conditional dynamics:

                    ht+1 (i) = ω i + αi ε2t + β i Et [ ht (st ) |st+1 = i] .          (5.1)

The equation conditions volatility on a larger information set than the Gray speci-
fication: ht+1 (i) = ω i +αi ε2t +β i Et−1 ht (st ). We prefer (5.1) for two reasons. First,
Klaassen shows that his model has better forecasting performance on three of the
exchange rates considered in this paper (DEM, JPY and GBP), and attributes
these improvements to finer conditioning. Second, the Klaassen version permits
multi-step forecasting, which will be a key part of the out-of-sample analysis.
    We report in Table 5 the ML estimates of the alternative processes. The
coeﬃcient 1/ν is the inverse of the degrees of freedom in the Student distribution.
This is a convenient renormalization that has been frequently used in the literature
(e.g. Bollerslev, 1987). Each coeﬃcient σ i , i = 1, 2, represents the standard
deviation of returns conditional on the volatility state: σ 2i = ω i /(1 − αi − β i ).
These coeﬃcients are easier to interpret across models than the intercepts ω i . As
shown in Table 6, the multifractal has a higher likelihood than GARCH(1,1) for
all exchange rates in spite of the fact that both processes have the same number
of parameters. In fact, the GARCH(1,1) likelihoods approximately match what
is obtained by MSM with only about 3 or 4 frequencies. The multifractal model
thus gives an improved fit over GARCH(1,1) in-sample.
    The MS-GARCH model raises diﬀerent issues because it uses more parameters
(9) than either the GARCH or MSM model (4). Thus, although MS-GARCH has
higher likelihoods than either GARCH or MSM, we obtain a diﬀerent ordering
when using the Schwarz BIC criterion. In particular, the multifractal model is

                                              17
then indistinguishable from MS-GARCH in the GBP data, and is preferred for
DEM and CAD.
    As suggested by Vuong (1989), we can also test the statistical significance
of diﬀerences in the BIC criterion. The last two columns of Table 6 test the
GARCH and MS-GARCH models against MSM under this metric.11 We again
give p-values for both the original version of the test as well as a HAC adjusted
variant. Under the original version, the in-sample performance of the MSM model
over GARCH(1,1) is highly significant for DEM, JPY and GBP, and somewhat
significant for CAD. The HAC adjustments produce analogous but slightly weaker
results. In comparing the MSM model to MS-GARCH, there is some evidence
that the multifractal model is a better performer for DEM and CAD, but the
significance is marginal at best. Overall, this analysis suggests that in-sample the
multifractal matches the performance MS-GARCH and significantly outperforms
GARCH(1,1).

5.2. Out-of-Sample Forecasts
We now investigate the out-of-sample forecasting performance of the competing
models. We use forecasting horizons ranging from 1 to 50 days. For each currency,
we estimate the three processes on the beginning of the series, and use the last
twelve years of data (or approximately half the sample) for our out-of-sample
forecasting comparison.
    Table 7 reports results of one-day forecasts. The first two columns correspond
to the coeﬃcients γ 0 and γ 1 from the Mincer-Zarnowitz OLS regressions x2t+1 =
γ 0 + γ 1 Et x2t+1 + ut of squared returns on a constant and one-day ahead forecasts.
These regressions are common in the financial econometrics literature (e.g., Pagan
and Schwert, 1990; West and Cho, 1995), and unbiased forecasts would imply
γ 0 = 0 and γ 1 = 1. We adjust the standard errors of γ 0 and γ 1 for parameter
uncertainty as in West and McCracken (1998), and for HAC eﬀects using the
weighting and lag selection methodology of Newey and West (1987, 1994).
    The MSM results show that for each currency, the estimated intercept γ̂ 0 is
slightly positive and the slope γ̂ 1 is slightly lower than 1. These small biases,
however, are not statistically significant. In particular, the hypothesis γ 0 = 0
is accepted at the 5% confidence level for all currencies, and γ 1 = 1 is accepted
at the 5% level for JPY and CAD and at the 1% level for DEM and GBP. The
  11
     Note that a BIC test of GARCH against the multifractal model is identical to a likelihood
test since both have the same number of parameters.


                                             18
Mincer-Zarnowitz regressions thus show little evidence of bias in MSM forecasts.
    The point estimates γ̂ 0 and γ̂ 1 are slightly worse with GARCH(1,1) than with
the multifractal. All intercepts are more positive, and the slopes are further away
from 1 for three currencies. The biases are also statistically significant. The hy-
potheses γ 0 = 0 and γ 1 = 1 are rejected at the 5% level in seven out of eight cases.
Since 0 < γ̂ 1 < 1, these results suggest that GARCH forecasts are too variable
and can be improved by the linear smoothing γ̂ 0 + γ̂ 1 Et x2t+1 . In contrast, Markov-
switching GARCH improves on the out-of-sample performance of GARCH(1,1).
We accept that γ 0 = 0 at the 5% confidence level for all currencies, and that
γ 1 = 1 at the 1% level for DEM, GBP and CAD. Furthermore, the regression
estimates are best with MS-GARCH for two currencies (DEM and GBP), and
with the multifractal for the other two. The two processes thus seem to perform
quite similarly out-of-sample at the one-day horizon. We also report in Table 7
two standard measures of goodness of fit: the Mean Squared Error (MSE) and the
restricted R2 coeﬃcient.12 The multifractal produces the best forecasting R2 for
DEM and JPY. On the other hand, GARCH produces better results for the GBP
and MS-GARCH for the CAD. To summarize the one-day forecast results, the
multifractal model appears to slightly dominate GARCH(1,1) and to give results
comparable to MS-GARCH.
    Multistep forecasts provide sharper evidence of diﬀerences between the three
models. We report in Table 8 the results for 20-day forecasts, which are repre-
sentative of longer horizons. Since our data sets only contains business days, this
frequency corresponds to about a month of calendar time. Following Andersen
and Bollerslev (1998) P and Klaassen (2002), the dependent variable is the sum of
squared daily returns t+19      2
                          s=t xs over the twenty-day period. Because the average
size of returns increases with the sampling interval, the estimated intercepts γ̂ 0
are larger in Table 8 than in Table 7. For each currency, the multifractal produces
point estimates of γ 0 and γ 1 that are closest to their preferred values. We also
accept the hypotheses γ 0 = 0 and γ 1 = 1 in all cases at the 5% confidence level.
By contrast, for the other models each currency gives a strong rejection of either
one hypothesis (MS-GARCH) or both (GARCH) at the 5% confidence level. The
reported MSE and R2 further confirm that the multifractal provides the best 20-
day forecasts for all currencies. The diﬀerence is particularly large in the case of
  12
    The Mean Squared Error (MSE) quantifies forecast errors in the out-of-sample pe-
         PT
riod: L−1 t=T −L+1 (x2t − Et−1 x2t )2 . The coeﬃcient of determination is defined by R2 =
1 − M SE/T SS, where T SS is the out-of-sample variance of squared returns: T SS =
     PT            PT
L−1 t=T −L+1 (x2t − i=T −L+1 x2i /L)2 .


                                           19
the DEM and JPY. The R2 coeﬃcient is 13.5% and 20.5% respectively for DEM
and JPY with the multifractal, while negative values are produced by GARCH
and MS-GARCH.13
    Table 9 reports summary forecasting results and tests of statistical signifi-
cance for horizons of 1, 5, 10, 20 and 50 days. Panel A shows the forecasting
R2 for each model. For the Mark and the Yen, the multifractal model is already
quite dominant at the 5-day horizon, and increasingly outperforms other models
at longer horizons. For the Pound and the Canadian Dollar, the multifractal is
only dominant at horizons of 20 days and higher. Panel B analyzes the statisti-
cal significance of these results. At horizons of 50 days, the multifractal model
outperforms the other models very significantly for DEM, GBP and JPY, and at
moderate or marginal significance levels for CAD. The superior forecasts of the
multifractal are also highly significant at horizons of 10 and 20 days for the DEM,
and somewhat strong at the 20-day horizons for JPY and GBP.
    These results are quite impressive for the multifractal model. Despite the fact
that this is the first forecasting evaluation the MSM, and we have investigated
only the very simplest binomial specification of the model, it compares quite
well with established models. In particular, GARCH(1,1) is often viewed as a
standard benchmark that is very diﬃcult to outperform in forecasting exercises
(e.g. West and Cho, 1995; Andersen and Bollerslev, 1998; Hansen and Lunde,
2001). Nonetheless, our results have shown the multifractal model to match or
slightly outperform GARCH and MS-GARCH at short horizons, and in many
cases to substantially dominate these models at longer horizons. The multifractal
model thus appears to be a serious contender among volatility models, and well-
deserving of both further empirical and theoretical investigation.

6. Conclusion
This paper proposes an expanded role for regime-switching in modeling volatil-
ity. Traditional approaches, such as SWARCH (Cai, 1994; Hamilton and Sus-
mel, 1994) and MS-GARCH (Gray, 1996; Klaassen, 2002), consider separately
three categories of volatility dynamics. High-frequency variation is captured by a
thick-tailed conditional distribution of returns, mid-range frequencies by smooth
  13
    We note that the multifractal yields a higher R2 for 20-day returns than for daily returns.
This
Pt+19stems from the fact that our measure of 20-day volatility is a sum of daily squared returns
        2
  s=t xs . As in Andersen and Bollerslev (1998), the reduction in the noisiness of the volatility
measure leads to an increase in explanatory power.


                                               20
ARCH or GARCH components, and only very low frequencies are modeled with
regime-switching. We suggest an alternative approach based on regime-switching
dynamics at all frequencies. The model is very tightly parameterized in spite of
a high dimensional state space. Using four long series of daily exchange rates,
we find that the process matches or dominates the performance of traditional
models across a range of in-sample and out-of-sample measures of fit. Thus, the
primary contribution of the paper is to show that regime-switching can be used
in a much wider variety of settings than previously envisioned. In particular,
our pure regime switching model provides a viable alternative to traditional ap-
proaches that combine regime-switching, linear volatility dynamics, and flexible
tail distributions.
    Researchers often focus on applications of immediate practical value when
evaluating statistical models. We have similarly shown that our process does well
by several standard measures of performance. Another motivation for statistical
models is that good description is the first step in explanation. If we can find a
statistical model that represents data well among many diﬀerent dimensions, we
can then seek to identify economic mechanisms that might replicate the observed
features. Whereas standard models would require us to explain a triumvirate of
statistical phenomena — regime-switching, linear dynamics, and thick tails — our
model oﬀers the possibility of much more concise explanation. Specifically, our
results invite the theorist to explain the economic mechanism that might cause
a self-similar form of regime-switching to provide such a useful description of
financial data.
    Returning to the more immediate contributions of our work, this is the first
paper to develop and use a comprehensive set of standard econometric tools to
estimate and test multifractal processes. We develop the first maximum likeli-
hood estimator for multifractal processes, based on a straightforward application
of the filter developed by Hamilton (1989). We show that this estimator works
well in Monte Carlo simulations. The application to exchange rates leads to
several observations. First, the likelihood function of the multifractal model de-
creases monotonically as we add volatility components to the model. This finding
is important because it confirms substantial heterogeneity in the persistence of
volatility shocks, which is one of the primary motivations of the multifractal ap-
proach. Consistent with our intuition, we also observe that the spacing of volatility
components across frequencies becomes tighter and the contribution of individual
volatility components becomes smaller as we increase the number of components.
    The multifractal model is then compared with Student GARCH and MS-


                                         21
GARCH. Among the many possibilities, these are chosen because of their demon-
strated good performance with exchange rate data under a variety of metrics. Like
our multifractal model, these models conveniently permit maximum likelihood
estimation and analytical forecasting. The in-sample likelihood is significantly
higher for the multifractal than for GARCH, even though these processes have
the same number of parameters. On the other hand, there is no significant results
in-sample between the multifractal model and MS-GARCH.
    Out-of-sample evidence further validates the multifractal process. MSM matches
or slightly outperform GARCH and MS-GARCH at short horizons, and in many
cases substantially dominates these models at longer horizons. The multifrac-
tal model thus appears to be a serious contender among volatility models, and
well-deserving of both further empirical and theoretical investigation.




                                       22
7. Appendix
7.1. Covariogram
Let K2q (n) = E(|xt |2q |xt+n |2q )/[E(|xt |2q )]2 . Multipliers in diﬀerent stages of the
cascade are statistically independent. Since xt = σ(M1,t M2,t ...Mk,t )1/2 εt and
xt+n = σ(M1,t+n M2,t+n ...Mk,t+n )1/2 εt+n , we infer that
                                                     Y           q    q
                                                              E(Mk,t Mk,t+n )
                                                          k
                                     K2q (n) =                                        .
                                                              [E(M q )]2k
                        q    q
Bayes’ rule implies E(Mk,t Mk,t+n ) = E(M 2q )(1 − γ k )n + [E(M q )]2 [1 − (1 − γ k )n ] or
equivalently
                      q    q
                  E(Mk,t Mk,t+n ) = [E(M q )]2 [1 + aq (1 − γ k )n ],
                                                                                           k−k̄
where aq = V ar(M q )/[E(M q )]2 . Since 1 − γ k = (1 − γ k̄ )b                                   , we obtain

                                               k h
                                               Y                           i
                                                                      k−k̄
                               K2q (n) =          1 + aq (1 − γ k̄ )nb       .
                                               k=1

                                                                                             k−k̄
     We now assume that n = bk̄−l . The quantity (1 − γ k̄ )nb                                      can be rewritten as
 bk−l ln(1−γ
          k̄ ) , and thus
e

                                                    X
                                                    k−l
                                                                                i
                          logb K2q (n) =                      logb [1 + aq eb ln(1−γ k̄ ) ].
                                                   i=−l+1

                                               i
We note that the terms e− ln(1−γ k̄ )b are close to 1 when i ∈ {−l, ..., 0} and negligible
for larger values of i, suggesting that logb K2q (n) ∼ l logb (1 + aq ). This heuristic
argument can be proved by dividing the sum into three parts:
     √                                    √
    X
    − l                                   Xl                                               X
                                                                                           k−l
                                                                                                                          −i
                     ln(1−γ k̄ )bi                                   ln(1−γ k̄ )bi
          logb [1+aq e               ]+            logb [1+aq e                      ]+             logb [1+aq eln(1−γ k̄ )b ].
                                         √                                                  √
i=−l+1                                i=− l+1                                             i= l+1
                                                               √                             −l
We note that the first component is bounded       below   (l −  l) logb [1 + aq eln(1−γ k̄ )b ]
                √                            √
                                            − l
and above by (l− l) logb [1+aq eln(1−γ k̄ )b√ ], and is thus equivalent to l log√  b (1+aq ).
The second term is bounded above by 2 l logb (1+aq ) and is therefore O( l). The

                                                          23
                                P                                       √
third term is bounded above by k−l  √
                                  i= l+1
                                          log b [1 + a  q  eln(1−γ k̄ )b l
                                                                           ] and is therefore
negligible. Hence
                          K2q (n) ∼ (bk̄ /n)logb (1+aq ) .
We also note that 1 + aq = E(M 2q )/[E(M q )]2 > 1, and thus logb (1 + aq ) =
logb E(M 2q ) − 2 logb E(M q ) > 0.
    We can now derive the covariogram of the process. Since γ 2q (n) = K2q (n) −
[E(|xt |2q )]2 and [E(|xt |2q )]2 = σ 4q [E( |εt |2q )]2 [E(M q )]2k , we infer that
                                                                            
                                       Y  k                                 
                                                                  nbk−1
                     γ 2q (n) = cq,k         [1 + aq (1 − γ 1 )         ]−1 .
                                                                            
                                          k=1


                                Y
                                k
                                                      k−1
When 1 << l << k̄, we know that   [1 + aq (1 − γ 1 )nb ] ∼ (bk̄ /n)logb (1+aq ) >> 1
                                            k=1
and thus γ 2q (n) ∼ K2q (n) ∝ nτ θ (2q)−2τ θ (q)−1 .

7.2. Bayesian Updating
Denote the set of past observations It ≡ {xs }ts=1 . We note that the conditional
probability Πjt+1 = P (Mt+1 = mj |It , xt+1 ) satisfies
                     ¡                 ¢ ¡              ¢
       Πjt+1 = fxt+1 xt+1 |Mt+1 = mj P Mt+1 = mj |It /fxt+1 (xt+1 |It ) ,
which can be rewritten as
                                                           ³P             ´
                                                             d
                                    n[xt+1 /σg (mj )]                 i
                                                             i=1 aij Πt
                         Πjt+1 =                                              .              (7.1)
                                           σg (mj ) fxt (xt+1 |It )
                            P        j
This implies (3.1) since          j Πt+1 = 1.


7.3. Likelihood Function
                                            PT
We know that L (x1 , ..., xT ; ψ) =             t=1 ln f (xt |x1 , ..., xt−1 ). Bayes’ rule implies
that
                                   X
                                   d
      f (xt |x1 , ..., xt−1 ) =          P(Mt = mi |x1 , ..., xt−1 )f (xt |Mt = mi )
                                   i=1
                                   Xd                                   µ          ¶
                                                       i        1            x
                            =     P(Mt = m |x1 , ..., xt−1 )          n
                              i=1
                                                             σg (mi )     σg (mi )

                                                  24
and thus f (xt |x1 , ..., xt−1 ) = ω(xt ) · (Πt−1 A).

7.4. HAC-Adjusted Vuong Test
We consider the probability space (Ω, F, P0 ) and a stochastic process {xt }+∞
                                                                             t=−∞ .
Each xt is a random variable taking values on the real line. For every t, it is
convenient to consider the vector of past values Xt−1 = {xs }t−1s=−∞ . The econo-
metrician directly observes a finite number of realizations of xt , but ignores the
true data generating process. She instead considers two competing families of
models specified by their conditional densities Mf = {f (xt |Xt−1 , θ); θ ∈ Θ} and
Mg = {g(xt |Xt−1 , γ); γ ∈ Γ}. These families may or may not contain the true
data generating process. The pseudo true value θ∗ specifies the model in Mf with
the optimal Kullback-Leibler Information Criterion:

                             θ∗ = arg max           E0 [ln f (xt |Xt−1 , θ)].
                                         θ∈Θ

The pseudo true value γ ∗ is similarly defined.
  Consider the log-likelihood functions:

                       X
                       T                                              X
                                                                      T
           LfT (θ) ≡         ln f (xt |Xt−1 , θ),         LgT (γ) ≡          ln g(xt |Xt−1 , γ).
                       t=1                                            t=1


By definition, the MLE estimators θ̂T and γ̂ T maximize the functions LfT (θ) and
LgT (γ). The corresponding FOCs are

                                 ∂LfT                    ∂LgT
                                      (θ̂T ) = 0,             (γ̂ ) = 0.                           (7.2)
                                  ∂θ                      ∂θ T
We now examine the likelihood ratio
                                                               X
                                                               T
                                                                           f (xt |Xt−1 , θ̂T )
              LRT (θ̂T , γ̂ T ) = LfT (θ̂T ) − LgT (γ̂ T ) =          ln                       .
                                                                t=1
                                                                           g(xt |Xt−1 , γ̂ T )

By equation (7.2), a second order expansion of LRT implies that √1T LRT (θ̂T , γ̂ T ) =
√1 LRT (θ ∗ , γ ∗ ) + op (1), and thus
  T


                                        1 X f (xt |Xt−1 , θ∗ )
                                            T
                  1
                 √ LRT (θ̂T , γ̂ T ) = √      ln                  + op (1).
                   T                     T t=1 g(xt |Xt−1 , γ ∗ )

                                                    25
Let at = ln[f (xt |Xt−1 , θ∗ )/g(xt |Xt−1 , γ ∗ )] and ât = ln[f (xt |Xt−1 , θ̂T )/g(xt |Xt−1 , γ̂ T )].
   When the observations xt are IID, the addends at are also IID. If the models
f and g have equal Kullback-Leibler Information criterion, the CLT implies
                                  1                  d
                                 √ LRT (θ̂T , γ̂ T ) → N (0, σ 2∗ ),
                                   T
where σ 2∗ = V ar(at ). The variance is consistently estimated by the sample variance
of {ât }.
    In the non-IID case, we need to adjust for the correlation in the addends at .
Let
                                      1 XX
                                          T   T
                                 2
                               σT =             E(as at ).
                                      T s=1 t=1

We know that √1T LRT (θ̂T , γ̂ T ) = σ T Z + op (1), where Z is a standard Gaussian.
Following Newey-West (1987), we estimate σT by
                                                    mT
                                                    X
                                  σ̂ 2T = Ω̂0 + 2         w(j, m)Ω̂j ,
                                                    j=1

            P
where Ω̂j = Tt=j+1 ât ât−j /T denotes the sample covariance of {ât }, and w(j, m) =
1 − j/(m + 1) is the Bartlett weight. We choose mT using the automatic lag
selection method of Newey and West (1994).




                                                    26
References
 [1] Akgiray, V. (1989), Conditional Heteroskedasticity in Time Series of Stock
     Returns: Evidence and Forecasts, Journal of Business 62, 55-80.

 [2] Andersen, T.G., and Bollerslev, T. (1998), Answering the Skeptics: Yes,
     Standard Volatility Models Do Provide Accurate Forecasts, International
     Economic Review 39, 885-905.

 [3] Andersen, T. G., Bollerslev, T., Diebold, F. X., and Labys, P. (2001), The
     Distribution of Realized Exchange Rate Volatility, Journal of the American
     Statistical Association 96,42-55.

 [4] Andrews, D. W. K. (1991), Heteroskedasticity and Autocorrelation Consis-
     tent Covariance Matrix Estimation, Econometrica 59, 817-854.

 [5] Andrews, D. W. K., and Monahan, J. C. (1992), An Improved Heteroskedas-
     ticity and Autocorrelation Consistent Covariance Matrix Estimator, Econo-
     metrica 60, 953-966.

 [6] Baillie, R. T., (1996), Long Memory Processes and Fractional Integration in
     Econometrics, Journal of Econometrics 73, 5-59.

 [7] Baillie, R. T., Bollerslev, T., and Mikkelsen, H. O. (1996), Fractionally In-
     tegrated Generalized Autoregressive Conditional Heteroskedasticity, Journal
     of Econometrics 74, 3-30.

 [8] Barndorﬀ-Nielsen, O., and Shephard, N. (2003), Realized Power Variation
     and Stochastic Volatility, Bernoulli, forthcoming.

 [9] Bollen, N., Gray, S. and Whaley, R. (2000), Regime Switching in Foreign
     Exchange Rates: Evidence from Currency Option Prices, Journal of Econo-
     metrics 94, 239-276.

[10] Bollerslev, T. (1986), Generalized Autoregressive Conditional Heteroskedas-
     ticity, Journal of Econometrics 31, 307-327.

[11] Bollerslev, T. (1987), A Conditional Heteroskedastic Time Series Model for
     Speculative Prices and Rates of Return, Review of Economics and Statistics
     69, 542-547.


                                       27
[12] Breidt, J., Crato, N., and DeLima, P. (1998), On the Detection and Estima-
     tion of Long-Memory in Stochastic Volatility, Journal of Econometrics 83,
     325-348.
[13] Cai, J. (1994), A Markov Model of Unconditional Variance in ARCH, Journal
     of Business and Economic Statistics 12, 309-316.
[14] Calvet, L. (2001), Incomplete Markets and Volatility, Journal of Economic
     Theory 98, 295-338.
[15] Calvet, L., and Fisher, A. (2001), Forecasting Multifractal Volatility, Journal
     of Econometrics 105, 27-58.
[16] Calvet, L., and Fisher, A. (2002), Multifractality in Asset Returns: Theory
     and Evidence, Review of Economics and Statistics 84, 381-406.
[17] Calvet, L., Fisher, A., and Mandelbrot, B. B. (1997), Cowles Foundation
     Discussion Papers No. 1164-1166, Yale University. Papers available from
     http://www.ssrn.com.
[18] Campbell, J., Lo, A., and MacKinlay, A. C. (1997), The Econometrics of
     Financial Markets, Princeton University Press.
[19] Dacorogna, M., Müller, U., Nagler, R., Olsen, R., and Pictet, O. (1993),
     A Geographical Model for the Daily and Weekly Seasonal Volatility in the
     Foreign Exchange Market, Journal of International Money and Finance 12,
     413-438.
[20] den Haan, W. J., and Levin, A. (1997), “A Practitioner’s Guide to Robust
     Covariance Matrix Estimation”, in G. Maddala and C. Rao Eds., Handbook
     of Statistics: Robust Inference, Vol. 15, New York: Elsevier.
[21] Diebold. F. X., and Inoue, A. (2001), Long Memory and Regime Switching,
     Journal of Econometrics 105, 27-58.
[22] Diebold, F. X., Lee, J. H., and Weinbach, G. C. (1994), Regime Switching
     with Time-Varying Transition Probabilities, in C. Hargreaves ed. Nonstation-
     ary Time Series Analysis and Cointegration, Oxford University Press.
[23] Ding, Z., Granger, C., and Engle, R. (1993), A Long Memory Property of
     Stock Market Returns and a New Model, Journal of Empirical Finance 1,
     83-106.

                                        28
[24] Dueker, M. (1997), Markov Switching in GARCH Processes and Mean Re-
     verting Volatility, Journal of Business and Economic Statistics 15, 26-34.

[25] Durland, J., and McCurdy, T. (1994), Duration-Dependent Transitions in
     a Markov Model of US GNP Growth, Journal of Business and Economic
     Statistics 12, 279-288.

[26] Engle, R. F. (1982), Autoregressive Conditional Heteroscedasticity with Es-
     timates of the Variance of United Kingdom Inflation, Econometrica 50, 987-
     1007.

[27] Filardo, A. J. (1994), Business Cycle Phases and their Transitional Dynamics,
     Journal of Business and Economic Statistics 12, 299-308.

[28] Frisch, U., and Parisi, G. (1985), Fully Developed Turbulence and Intermit-
     tency, in: M. Ghil ed., Turbulence and Predictability in Geophysical Fluid
     Dynamics and Climate Dynamics, 84-88, Amsterdam: North-Holland.

[29] Garcia, R., and Perron, P. (1996), An Analysis of the Real Interest Rate
     under Regime Shifts, Review of Economics and Statistics 78, 111-125.

[30] Ghysels, E., Harvey, A. C., and Renault, E. (1996), Stochastic Volatility, in:
     G. S. Maddala and C. R. Rao Eds., Handbook of Statistics, Vol. 14, 119-191.
     Amsterdam: North-Holland.

[31] Gray, S. (1996), Modeling the Conditional Distribution of Interest Rates as
     a Regime-Switching Process, Journal of Financial Economics 42, 27-62.

[32] Hamilton, J. D. (1989), A New Approach to the Economic Analysis of Non-
     stationary Time Series and the Business Cycle, Econometrica 57, 357-84.

[33] Hamilton, J. D. (1990), Analysis of Time Series Subject to Change in Regime,
     Journal of Econometrics 45, 39-70.

[34] Hamilton, J. D. and B. Raj (2002), New Directions in Business Cycle Re-
     search and Financial Analysis, Empirical Economics 27, 149-162.

[35] Hamilton, J. D. and R. Susmel (1994), Autoregressive Conditional Het-
     eroskedasticity and Changes in Regime, Journal of Econometrics 64, 307-
     333.


                                        29
[36] Hansen, P., and Lunde, A. (2001), “A Forecast Comparison of Volatility
     Models: Does Anything Beat a GARCH(1,1)?”, Working Paper, Brown Uni-
     versity.

[37] Klaassen, F. (2002), Improving GARCH Volatility Forecasts with Regime-
     Switching GARCH, Empirical Economics 27, 363-394.

[38] LeBaron, B. (2001), Stochastic Volatility as a Simple Generator of Apparent
     Financial Power Laws and Long Memory, Quantitative Finance 1, 621-631.

[39] Lux, T. (2001), “The Multifractal Model of Asset Returns: Simple Moment
     and GMM Estimation”, Working Paper, Kiel University.

[40] Maheu, J., and McCurdy, T. (2000), Volatility Dynamics under Duration-
     Dependent Mixing, Journal of Empirical Finance 7, 345-372

[41] Mandelbrot, B. B. (1963), The Variation of Certain Speculative Prices, Jour-
     nal of Business 36, 394-419.

[42] Mandelbrot, B. B. (1997), Fractals and Scaling in Finance: Discontinuity,
     Concentration, Risk, New York: Springer Verlag.

[43] Mariano, R., Schuerman, T., and M. Weeks (1999), Simulation-Based Infer-
     ence in Econometrics, Cambridge University Press.

[44] Newey, W., and West, K. (1987), A Simple, Positive Semi-Definite, Het-
     eroskedasticity and Autocorrelation Consistent Covariance Matrix, Econo-
     metrica 55, 703-708.

[45] Newey, W., and West, K. (1994), Automatic Lag Selection in Covariance
     Matrix Estimation, Review of Economic Studies 61, 631-654.

[46] Pagan, A., and Schwert, W. (1990), Alternative Models for Conditional Stock
     Volatility, Journal of Econometrics 45, 267-290.

[47] Perez-Quiros, G., and Timmerman, A. (2000), Firm Size and Cyclical Vari-
     ations in Stock Returns, Journal of Finance 55, 1229-1262.

[48] Rivers, D., and Vuong, Q. (2002), Model Selection Tests for Nonlinear Dy-
     namic Models, Econometrics Journal 5 (1), 1-39.



                                       30
[49] Stock, J. H. (1987), Measuring Business Cycle Time, Journal of Political
     Economy 95, 1240-1261.

[50] Stock, J. H. (1988), Estimating Continuous-Time Processes Subject to Time
     Deformation, Journal of the American Statistical Association 83, 77-85.

[51] Vuong, Q. (1989), Likelihood Ratio Tests for Model Selection and Non-Nested
     Hypotheses, Econometrica 57, 307-333.

[52] West, K., and Cho, D. (1995), The Predictive Ability of Several Models of
     Exchange Rate Volatility, Journal of Econometrics 69, 367-391.

[53] West, K., and McCracken, M. (1998), Regression-Based Tests of Predictive
     Ability, International Economic Review 39, 817-840.




                                      31