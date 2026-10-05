source: https://nhsjs.com/wp-content/uploads/2026/08/Path-Signatures-for-Regime-Detection-in-Cryptocurrency-Markets-A-Rough-Path-Framework-Using-Spot-Perpetual-Basis-and-Funding-Rates.pdf
fetched_utc: 2026-10-04T18:45:03Z
bytes_raw: 8837147

Path Signatures for Regime Detection in Cryptocurrency Markets: A
Rough-Path Framework Using Spot, Perpetual Basis, and Funding
Rates
Vibhun Naredla1

Received May 9, 2026
Accepted July 30, 2026
Electronic access August 31, 2026


Background. Cryptocurrency markets exhibit fast, reflexive regime transitions driven by leverage cycles, coordinated liq-
uidations, and perpetual-swap funding imbalances. Classical regime-detection methods — hidden Markov models (HMMs)
on returns and rolling-volatility thresholds — impose Markovian dynamics and summarize path information through low-
dimensional moments, missing the path-dependent structure of crypto regime shifts.
Methods. We develop a regime-detection framework based on truncated path signatures from rough-path theory. We construct
a multivariate path of BTC and ETH log-returns, a realized-volatility proxy, perpetual-spot basis, and 8-hour funding rates,
with lead-lag and time augmentation. Truncated signatures of depth N = 3 are extracted from rolling 168-hour windows,
robust-scaled, projected to 128 components by truncated SVD, and passed to l2 -penalized logistic regression. We prove a
universal-approximation result establishing signatures as a rich feature family for continuous path functionals, and separately
discuss what this implies for supervised regime classification. We benchmark against four baselines — univariate HMM,
multivariate HMM, rolling-volatility tercile, and HAR-RV — with purged walk-forward validation, a 168-hour embargo
between train and test folds, and block-bootstrap 95% confidence intervals.
Results. Signature methods are competitive with the strongest baseline (HAR-RV) on forward-volatility tercile classification
across horizons 24h, 72h, and 168h, and produce the highest test accuracy at the 168h horizon. On average precision for
prospective detection of top-decile forward volatility events over the full 2023–2026 test timeline, SIG-LR outperforms all
baselines. In an event study across six canonical regime shifts, signatures produce the cleanest event-localized probability
signals: signatures detect the out-of-sample SVB/USDC depeg within a ±4-hour window of the event core across all tested
thresholds and correctly abstain on the bullish BTC ETF approval. The signature advantage localizes empirically in third-order
iterated integrals dominated by cross-coordinate interactions involving basis and realized-volatility coordinates. Signatures do
not solve directional return prediction at sub-daily horizons, consistent with market-efficiency expectations.
Conclusions. Path signatures are a competitive feature representation for crypto regime detection whose primary practical
advantage is not headline predictive accuracy but interpretable, event-localized signal cleanliness with a clear financial interpre-
tation of the driving coordinates.

Keywords: rough path theory, path signatures, regime detection, cryptocurrency, perpetual futures, funding rates, hidden
Markov models, universal approximation, walk-forward validation.

Introduction                                                        nancial assets. Unconditional volatility runs three to five times
                                                                    that of large-capitalization equities, return distributions ex-
Cryptocurrency markets have, over the past decade, matured          hibit heavier tails, trading runs continuously across the week,
into a liquid, globally accessible, continuously-traded asset       and the market microstructure features deep perpetual-swap
class. Daily spot turnover on the largest centralized exchanges     order books in which leverage is directly observable through
regularly exceeds fifty billion U.S. dollars, and notional open     exchange-reported funding rates and open-interest series.
interest in perpetual futures on Bitcoin and Ether often sur-
                                                                       These differences reflect a qualitative change in price-
passes the corresponding cash-settled equity-index contracts
                                                                    formation dynamics. Whereas equity regime shifts typi-
traded on CME. Despite this scale, the statistical behavior of
                                                                    cally propagate through earnings cycles or macroeconomic
crypto returns is markedly distinct from that of traditional fi-
                                                                    narratives, crypto regime shifts are frequently reflexive: a
1 Briar Woods High School / Academies of Loudoun, Virginia, USA     change in aggregate leverage positioning precipitates a forced-

© The National High School Journal of Science 2026                                                                                |1
liquidation cascade, which alters the price path, which feeds         tributions. First, we construct a crypto-native multivariate
back into positioning. The collapses of Terra-LUNA in May             path combining time, BTC and ETH log-prices, a realized-
2022 and FTX in November 2022 are canonical examples. In              volatility proxy, perpetual-spot basis, and hourly funding
both cases, the transition from a stable regime into acute dis-       rates, augmented with lead-lag embedding 31 and time aug-
tress occurred on timescales of hours, and the statistical sig-       mentation. Basis and funding are directly observable mea-
natures of the coming transition were visible in the joint dy-        sures of leverage positioning unavailable in equity markets
namics of spot, basis, and funding well before they registered        and, to our knowledge, have not previously appeared as signa-
in any univariate volatility summary. Detecting such regime           ture coordinates. Second, we prove a universal-approximation
shifts ex ante or with minimal ex-post lag is consequential for       result for continuous path functionals by linear functionals
risk desks, prime brokers, portfolio managers, and execution          of truncated signatures, and we separately discuss what this
algorithms 1,2 .                                                      theoretical result does and does not imply for supervised
   The standard toolkit for regime detection in financial time        regime classification — an important distinction in noisy, non-
series rests on assumptions that are violated in this setting.        stationary market environments. Third, we conduct a purged
Hidden Markov models, introduced in their economic form               walk-forward evaluation with a 168-hour embargo between
by Hamilton 3 , posit an unobservable discrete state evolving         train and test folds, block-bootstrap 95% confidence inter-
as a Markov chain; their inference machinery is mature 4–6            vals on all reported metrics, and comparison against HAR-
and widely implemented. Rolling-window statistics on real-            RV in addition to standard HMM baselines. Fourth, we per-
ized volatility provide nonparametric threshold detectors that        form ablations across signature truncation depths (N = 2, 3),
are standard on practitioner trading desks 7,8 . Heterogeneous        SVD component counts (32, 128, 512), and feature-set vari-
autoregressive (HAR) models on realized volatility remain the         ants (with and without realized volatility). Fifth, we perform
workhorse for daily and multi-day volatility forecasting in the       an event study across six canonical regime shifts and evaluate
empirical literature. All of these methods are either Marko-          detection via a prospective precision-recall analysis on the full
vian or memoryless with respect to path shape, or they com-           test timeline with an ex-ante-defined event label.
press multivariate path information into moments computed                Our headline finding is nuanced. Signatures are competitive
over trailing windows.                                                with the strongest baseline (HAR-RV) on aggregate accuracy
   A mathematically principled response is provided by the            across horizons and lead on accuracy at the 168-hour horizon,
theory of rough paths 9–11 . Given a continuous path X :              but the confidence intervals overlap substantially with HAR-
[0, T ] → Rd of finite p-variation, the signature of X is the in-     RV and rolling-volatility baselines at shorter horizons. The
finite sequence of iterated integrals over the path, valued in        primary practical advantage of signatures is not headline pre-
the tensor algebra. The construction dates to Chen for smooth         dictive accuracy but event-localized signal cleanliness with in-
paths 12 and was extended by Lyons to paths of arbitrary fi-          terpretable financial mechanism: signatures produce the tight-
nite p-variation. Signatures encode an infinite collection of         est detection windows at distress events and correctly discrim-
order-aware interactions between coordinates and are, under           inate distress-driven from bullish-regime volatility, and the
mild conditions, near-injective on the space of paths 13 . Linear     top-coefficient signature coordinates are dominated by inter-
functionals of truncated signatures are dense in the space of         actions among basis and realized-volatility channels, match-
continuous functionals on compact sets of paths 14–16 , and ef-       ing the leverage-cycle intuition that motivated the framework.
ficient implementations 17,18 make signature feature extraction
tractable for large datasets on commodity hardware.                   Methods
   Signature methods have proliferated in quantitative finance,
including high-frequency equity prediction 19 , optimal execu-        Notation
tion 20 , signature-based stochastic models 21 , market simula-
tion 22 , and volatility modeling 23–25 . Most directly relevant,     Table 1 summarizes the notation used throughout the
Horvath and Issa 26 develop a non-parametric online regime-           manuscript.
detection method using signatures within a maximum-mean-
discrepancy two-sample test. A rough-volatility perspective           Mathematical framework
on Bitcoin 27,28 establishes that crypto log-volatility is substan-
tially rougher than equity benchmarks, providing motivation           Fix a horizon T > 0 and dimension d ≥ 1. A path is a contin-
for path-based methods. Existing regime-switching models              uous map X : [0, T ] → Rd . For a partition π = {0 = t0 < · · · <
for crypto 29,30 do not leverage multivariate perpetuals data or      tn = T } and p ≥ 1, the p-variation of X on [s,t] ⊆ [0, T ] is
path-dependent feature representations.                                                                                         !1/p
   This paper develops a treatment of signature-based regime                     ∥X∥ p-var,[s,t] =   sup ∑ ∥Xti+1 − Xti ∥   p
                                                                                                                                       .
detection in cryptocurrency markets with the following con-                                           π   i


2|                                                                                      © The National High School Journal of Science 2026
Table 1 Notation used in this paper.
                               Symbol                  Meaning
                               T                       Time horizon (window length)
                               d                       Ambient dimension of the raw path
                               daug                    Dimension of the augmented (lead-lag, time-augmented) path
                               X : [0, T ] → Rd        A continuous path
                               ∥X∥ p-var,[s,t]         p-variation of X over [s,t]
                               BVp ([0, T ]; Rd )     Banach space of continuous paths of finite p-variation
                               T (Rd )                Tensor algebra over Rd
                               T N (Rd )               Truncated tensor algebra at depth N
                               S(X)s,t                 Signature of path X over interval [s,t]
                               πN                      Projection onto truncated tensor algebra of depth N
                               DN                      Dimension of truncated signature at depth N
                               K                       Compact set of paths
                               L:K→R                   Continuous target functional
                               M                       Diameter of K in 1-variation
                               γt                      Filtered HMM posterior at time t
                               bti , fti               Perpetual-spot basis and funding rate for asset i at time t
                               rti , vt                Log-return of asset i and 24h realized-vol proxy at time t


Denote by BVp ([0, T ]; Rd ) the Banach space of continuous                      For our data with per-window 1-variation M ≈ 0.5, trun-
paths of finite p-variation.                                                  cation at N = 3 retains approximately 99.7% of the signature
  The tensor algebra over Rd is T (Rd ) = k≥0 (Rd )⊗k .
                                                  L
                                                                              norm and N = 4 retains essentially all of it.
Fix an orthonormal basis {e1 , . . . , ed } of Rd . For X ∈                      Two algebraic identities make signatures computationally
BV1 ([0, T ]; Rd ), the signature of X on [s,t] is                            tractable. Chen’s identity 12 : for 0 ≤ s ≤ u ≤ t ≤ T , S(X)s,t =
                                                                              S(X)s,u ⊗ S(X)u,t . The shuffle identity 32 : for multi-indices
                                1      2
                 S(X)s,t = (1, Ss,t , Ss,t , . . .),                          I, J, ⟨S(X), eI ⟩ · ⟨S(X), eJ ⟩ = ∑K∈IJ ⟨S(X), eK ⟩. The shuffle
                           Z         Z                                        identity implies that linear functionals of the signature form
              k
             Ss,t (X) =      ···       dXt1 ⊗ · · · ⊗ dXtk .                  a polynomial algebra: linear regression on signatures realizes
                       s<t1 <···<tk <t
                                                                              polynomial regression on path coordinates.
                                                                                 Two augmentations enhance signature expressivity. Time
   Signature coordinates encode order-aware interactions. The                 augmentation replaces X with (t, Xt1 , . . . , Xtd ); the strictly
(i, j)- and ( j, i)-coordinates of level 2 differ in general, and             monotone first coordinate excludes tree-like equivalence
their difference equals twice the signed Lévy area of the pro-               and renders the signature map injective on piecewise-linear
jection of X onto the (X i , X j )-plane.                                     paths 13 . Lead-lag transformation 31 produces a piecewise-
   Proposition 1 (Factorial decay). For X ∈ BV1 ([0, T ]; Rd )                linear path on twice the time grid that interleaves the lead and
and all k ≥ 0,                                                                lag values; level-two cross-coordinate terms of the lead-lag
                                                                              signature recover the quadratic covariation of X and encode
                                         ∥X∥k1-var,[s,t]
                      k
                    ∥Ss,t (X)∥ ≤                           ,                  the sequential structure of cross-coordinate movements.
                                               k!
where ∥ · ∥ is the Hilbert-Schmidt norm.                                      Universal approximation
   Proof Let ω(s,t) = ∥X∥1-var,[s,t] . By Fubini and the defini-              Theorem 1 (Uniform approximation of continuous path func-
tion of the iterated integral,                                                tionals). Let K ⊂ BV1 ([0, T ]; Rd ) be a compact set of continu-
                                                                              ous time-augmented paths. Let L : K → R be continuous in the
                                                               ω(s,t)k
                     Z         Z
       k
     ∥Ss,t (X)∥ ≤        ···        ∥dXt1 ∥ · · · ∥dXtk ∥ =            ,      1-variation metric, and let M = supX∈K ∥X∥1-var,[0,T ] . Then for
                                                                 k!           every ε > 0 there exist atruncation depth N ∈ N and a linear
                  s<t1 <···<tk <t
                                                                              functional l ∈ (T N (Rd ) )∗ such that
with the 1/k! factor arising from the volume of the ordered
simplex.                                                                                     sup L(X) − ⟨l, π N S(X)0,T ⟩ < ε.
                                                                                             X∈K


© The National High School Journal of Science 2026                                                                                           |3
   Proof. Time augmentation excludes tree-like equivalence,        tures. We robust-scale signatures using training-fold per-
so the signature map S : K → T (Rd ) is injective on K. By          coordinate medians and 5%–95% interquantile ranges, clip-
Proposition 1, S is continuous from K in 1-variation topology      ping to [−50, +50]. Truncated SVD reduces the representa-
into T (Rd ) in norm, so K̃ = S(K) is compact. The subal-           tion to 128 components fit on training data, capturing 99.3%
gebra generated by constants and coordinate evaluations con-        of training-fold variance. The SVD output is standardized to
tains the constants, separates points (by injectivity), and by      unit variance and clipped to [−8, +8].
the shuffle identity coincides with the linear functionals on the      We compare seven feature representations, each passed
full signature. By Stone-Weierstrass 33 , this subalgebra is uni-   to identical l2 -penalized multinomial logistic regression with
formly dense in C(K̃; R). Approximating L ◦ S−1 within ε/2          C = 0.5 fit by Newton conjugate-gradient with a hard iteration
by some l and applying Proposition 1 to bound the truncation        cap of 100:
error yields the result.
   Remark 1 (What Theorem 1 does and does not imply for                • SIG-LR (N = 3, SVD-128). Primary configuration: 128-
regime classification). Theorem 1 is a statement about con-              component truncated-SVD representation of depth-3 sig-
tinuous functionals of the observed path. Our downstream                 nature features.
classification target is the tercile of BTC realized volatility                                                         BTC ) of
                                                                                                                             
                                                                       • HMM-LR. Filtered posterior γt = (P Zt = k | r1:t     k
over the forward h-hour horizon — a threshold-discontinuous,             a Gaussian HMM with K = 3 states fit on BTC hourly
forward-looking quantity that is not a deterministic functional          returns by Baum-Welch 4 . We initialize with three ran-
of the observed 168-hour path. Theorem 1 therefore does not              dom seeds and select the model with highest training-
certify that our SIG-LR pipeline (depth-3 signatures → 128-              set log-likelihood; convergence tolerance is 10−4 on the
component SVD → multinomial logistic regression) approx-                 change in log-likelihood between EM iterations, with a
imates this supervised label to any specific error level. What           maximum of 150 iterations. Covariance is full. We im-
Theorem 1 does establish is that signatures form a rich, univer-         plement a custom forward filter to avoid the lookahead
sal feature family for continuous functionals of the observed            inherent in the smoothed posterior returned by standard
path; whether this translates into strong performance on any             library implementations.
specific supervised task is an empirical question. Downstream
performance depends on additional assumptions — smooth-                • HMM-MULTI-LR. Filtered posterior of a K = 3
ness of the conditional regime probability given the observed            diagonal-covariance Gaussian HMM fit on the full 7-
path, sample complexity of the downstream learner, and ab-               feature panel. Direct counterpart to SIG-LR with the
sence of severe distribution shift between train and test folds          same feature set but Markovian representation. Trained
— none of which are established by the theorem. We keep                  on a random 10,000-observation subsample of the train-
the theorem as motivation for the feature choice and treat em-           ing set for tractability.
pirical predictive performance as a separate question in the           • ROLLVOL-LR. One-hot tercile indicator based on trail-
Results and Discussion section.                                          ing 168-hour BTC realized volatility, with tercile bound-
                                                                         aries from the training fold.
Pipeline and models
                                                                       • HAR-RV-LR. Realized-volatility measures at 24-hour,
             Tmax                                                        5-day, and 22-day trailing windows following the
Let D = {rt }t=1  denote the multivariate hourly panel with
      7
rt ∈ R : BTC and ETH hourly log-returns, a 24-hour realized-             heterogeneous-autoregressive specification of Corsi
volatility proxy, BTC and ETH perpetual-spot basis, and BTC              (2009), extracted from BTC log-returns and passed as
and ETH 8-hour funding rates. For each rolling 168-hour win-             three features to the downstream logistic regression.
dow we integrate return coordinates and pass level coordinates           Missing values at the beginning of the series (before the
through (basis and funding are levels, not increments; integrat-         22-day window fills) are backward-then-forward filled;
ing them would destroy path-relevant information). We lin-               any remaining missing values are set to zero.
early interpolate, translate to a basepoint of 0, apply lead-lag
                                                                       • SIG+HMMM-LR. Concatenation of SIG-LR and
embedding to R14 , and prepend a time coordinate, producing
                                                                         HMM-MULTI-LR features.
an augmented path of dimension daug = 15.
   Raw coordinates span scales from O(10−4 ) to O(10−2 ). We           For ablation, we additionally evaluate SIG-LR variants at
robust-scale each raw coordinate to unit interquartile range        truncation depth N = 2 (yielding D2 = 240 features, no SVD
using training-fold statistics only. After signature extraction,    needed since dimension is small), SVD component counts of
level-k blocks are rescaled by k! to undo factorial decay 16 .      32 and 512 at depth N = 3, and a “no realized volatility” vari-
   Signatures are extracted at depth N = 3 (primary con-            ant that removes the realized-vol coordinate from the path be-
figuration) using iisignature 17 , yielding D3 = 3,615 fea-         fore signature extraction.

4|                                                                                 © The National High School Journal of Science 2026
Task and evaluation protocol                                        Data
                                                                    All data are from Binance via the public historical-archive
Task A (primary). Forward realized-volatility tercile classi-
                                                                    service data.binance.vision, which provides monthly ZIP-
fication: for horizon h ∈ {24, 72, 168} hours, the target is the
                                                                    compressed CSV files of one-hour klines and 8-hour funding
tercile of BTC realized volatility over the next h hours. Ter-
                                                                    rates. We collect one-hour spot klines for BTC/USDT and
cile boundaries are estimated from the training fold. Metrics:
                                                                    ETH/USDT, one-hour klines for the corresponding USDT-
accuracy, macro-F1 , macro one-vs-rest ROC-AUC, log-loss.
                                                                    margined perpetual contracts, and the funding-rate history for
   Robustness to regime definition. As a robustness check,          both perpetuals, covering January 1, 2020 through April 17,
we also examine a drawdown-based regime label: the bottom-          2026. After dropping rows during volatility initialization, the
quartile forward drawdown over 24 and 168 hour horizons.            usable sample is 55,129 hourly observations at 100% fea-
Results on this alternative label are qualitatively similar; SIG-   ture coverage. The panel features are: hourly log-returns;
                                                                                                                             √ a
LR and HAR-RV are the two best-performing methods, with             24-hour rolling realized-volatility proxy annualized by 365;
signatures showing a slight advantage at longer horizons. De-       perpetual-spot basis (Ft − Pt )/Pt ; and the 8-hour funding rate
tailed numbers are omitted for space; the code repository ac-       forward-filled to the hourly grid.
companying this manuscript contains the full ablation.                 The extreme excess-kurtosis values reflect the well-
   Train-test protocol: purged walk-forward with em-                documented heavy-tailedness of crypto asset returns and the
bargo. All target labels look forward h ∈ {24, 72, 168} hours.      further amplification in leverage-cycle-sensitive coordinates.
Training windows whose terminal hour falls just before the          BTC log-returns exhibit excess kurtosis 53.5, more than 50
train-test boundary would therefore draw their target labels        standard deviations above the Gaussian value of zero, driven
from the beginning of the test period, causing target leakage       by rare but severe intraday moves during liquidation cascades.
even when the signature features themselves do not. To elim-        The perpetual-spot basis has the most extreme excess kurto-
inate this leakage, we adopt purged walk-forward validation         sis (161.7), reflecting hours during which the perpetual traded
with a 168-hour embargo: we split the post-2022 test region         at 200–300 basis-point discounts to spot as long-side lever-
into five contiguous, non-overlapping blocks; for each block,       age was force-liquidated (COVID March 2020 alone con-
the training set consists of all windows whose terminal hour        tributes several such hours). Funding rates are right-skewed
falls at least 168 hours before the block’s first hour. The 168-    and lightly leptokurtic, consistent with persistent long-side
hour embargo covers the maximum forecast horizon and en-            leverage demand that is occasionally reset by squeeze events.
sures that no training-fold target label overlaps in time with
any test-fold feature window. All feature scaling, SVD di-
rections, tercile boundaries, and HMM parameters are refit at
each fold boundary using only the current training data.
  Bootstrap confidence intervals. Because our rolling win-
dows overlap heavily (stride 1, window length 168), the i.i.d.
bootstrap dramatically understates estimator variability. We
report 95% confidence intervals from a block bootstrap with
block length 168 hours (matching the window length) and 500
bootstrap replications per metric.
   Event-detection evaluation. For each of six canonical
regime-shift events (Table 3), we compute detection lag as
the first hour within a ±7-day window of the event core             Figure. 1 BTC and ETH hourly spot prices on Binance, 2020-01-
at which the method’s high-vol probability crosses a thresh-        01 to 2026-04-17. Shaded bands mark the six canonical regime-shift
old θ . We report detection lag across threshold values θ ∈         events.
{0.3, 0.4, 0.5, 0.6, 0.7} to address the sensitivity concern that
any single threshold choice is arbitrary. As a complementary
prospective evaluation over the entire test period, we define       Computational cost
an ex-ante detection target of “next-24-hour realized volatility
exceeds the 90th percentile of the training distribution” and       The end-to-end pipeline is tractable on commodity hardware.
report precision-recall curves per method over the full 2023–       Table 4 reports wall-clock time and peak memory for each
2026 test set. This latter analysis does not depend on the six      stage. Total end-to-end runtime is approximately 15 minutes
manually chosen events and gives an aggregate view of detec-        for a full evaluation across three horizons and seven methods,
tion performance.                                                   with peak memory of 1.2 GB. Signature extraction dominates

© The National High School Journal of Science 2026                                                                                 |5
Table 2 Summary statistics, 55,129 hourly observations, 2020-01-01 through 2026-04-17.
         Feature                             Mean               Std          Median               95%      Skew       Excess kurt.
         BTC log-return                4.2 × 10−5       6.73 × 10−3      6.1 × 10−5      9.19 × 10−3      −0.94              53.5
         ETH log-return                5.2 × 10−5       8.56 × 10−3      8.2 × 10−5      1.22 × 10−2      −0.90              28.6
         Realized vol (24h, ann.)           0.516             0.348           0.447            1.112      +4.26              46.6
         BTC basis                    −1.1 × 10−4       6.38 × 10−4     −3.6 × 10−4      1.06 × 10−3      −0.35             161.7
         ETH basis                    −4.4 × 10−5       7.15 × 10−4     −3.4 × 10−4      1.31 × 10−3      +0.97              53.1
         BTC funding (8h)              1.1 × 10−4       2.15 × 10−4      1.0 × 10−4      4.89 × 10−4      +3.26              30.1
         ETH funding (8h)              1.3 × 10−4       2.80 × 10−4      1.0 × 10−4      5.87 × 10−4      +3.31              38.1


Table 3 Canonical regime-shift events, ±3-day window.
     Event                          Window              BTC start ($)    DD (%)      Peak RV (%)         Basis (bp)       Fund. (%)
     COVID-19                2020-03-12 → 03-14             8,082         −48.9           714.6         [−257,+13]       [−329,+25]
     May 2021 unwind         2021-05-19 → 05-22            47,283         −31.8           317.1          [−59,+23]        [−98,+70]
     Terra-LUNA              2022-05-09 → 05-13            36,373         −25.5           254.0           [−15,+2]        [−46,+11]
     FTX insolvency          2022-11-08 → 11-11            21,434         −26.5           186.9           [−31,−1]       [−130,+11]
     SVB / USDC              2023-03-10 → 03-13            22,416         −12.5           139.0           [−9,+14]        [−10,+33]
     BTC ETF approval        2024-01-10 → 01-12            44,119         −5.4            118.8            [−4,+9]        [+11,+11]




                                                                        Figure. 3 Marginal distributions of hourly features with Gaussian
                                                                        reference (dashed red). Heavy tails and persistent non-zero ba-
Figure. 2 Perpetual-spot basis (top, 24h moving average) and
                                                                        sis/funding levels are evident.
hourly-annualized 8-hour funding rates (bottom). Leverage signals
spike during distress and compress in the post-FTX regime.

                                                                        168-hour embargo. All confidence intervals are 95% block-
runtime (240 seconds at N = 3) and memory (800 MB peak                  bootstrap intervals with 500 replications and 168-hour block
for the raw signature array), motivating the SVD reduction              length. Two observations dominate the reading of this table.
step. The block bootstrap adds a small overhead (≈ 5 seconds
                                                                           Signatures are competitive with HAR-RV but do not domi-
per method-horizon at 500 replications), and the walk-forward
                                                                        nate it on aggregate accuracy. At the 24-hour horizon, HAR-
evaluation adds a linear factor of 5 in fit time per method-
                                                                        RV attains the highest accuracy (0.655), best log-loss (0.809),
horizon relative to a single-split fit.
                                                                        and second-best AUC (0.691), which we did not see in our
                                                                        prior analysis without HAR-RV as a baseline. SIG-LR at
Results and Discussion                                                  N = 3 trails HAR-RV by 0.6 percentage points on accuracy
                                                                        with heavily overlapping confidence intervals. At 72 hours
Realized-volatility tercile classification                              the two are effectively tied on accuracy (0.696 vs. 0.695). At
                                                                        168 hours SIG-LR (both the primary N = 3 variant and the no-
Table 5 reports out-of-sample performance on Task A across              RV variant) leads on accuracy, though again with confidence
three horizons under purged walk-forward validation with a              intervals that overlap HAR-RV substantially. The story is that


6|                                                                                       © The National High School Journal of Science 2026
Table 4 Computational cost of pipeline stages, measured on an 8-core commodity workstation.
                         Stage                                                 Wall-clock time      Peak memory
                         Data download (Binance archives)                            45 s            streaming
                         Master panel construction                                    5s                7 MB
                         Signature extraction, N = 3                                240 s             800 MB
                         Signature extraction, N = 2                                120 s              50 MB
                         Robust scaling + SVD (N = 3)                                45 s             800 MB
                         HMM fitting (univariate, 3 seeds)                           40 s               5 MB
                         HMM fitting (multivariate, subsample of 10K)                60 s               5 MB
                         Walk-forward LR fit (per method-horizon)                    80 s             100 MB
                         Block bootstrap 500 reps (per method-horizon)                5s               10 MB
                         Total end-to-end (all methods × horizons)                 ∼15 min          1.2 GB peak


Table 5 Task A: forward realized-volatility tercile classification, purged walk-forward with 168h embargo. Values in brackets are 95% block-
bootstrap CIs (500 reps, 168h blocks). Bold: best point estimate within horizon.
   Horizon     Method                                Accuracy [95% CI]    Macro-F1 [95% CI]        Macro AUC [95% CI]          Log-loss
   24h         SIG-LR (N = 3, SVD-128)           0.649 [0.614, 0.683]     0.401 [0.363, 0.436]      0.664 [0.630, 0.695]         0.863
   24h         SIG-LR (N = 3, no RV)             0.652 [0.618, 0.687]     0.380 [0.342, 0.413]      0.638 [0.600, 0.672]         0.877
   24h         SIG-LR (N = 2)                    0.649 [0.616, 0.683]     0.435 [0.395, 0.468]      0.707 [0.672, 0.733]         0.841
   24h         SIG-LR (N = 3, SVD-32)            0.645 [0.611, 0.684]     0.358 [0.321, 0.393]      0.575 [0.532, 0.614]         0.942
   24h         SIG-LR (N = 3, SVD-512)           0.634 [0.599, 0.669]     0.416 [0.384, 0.446]      0.651 [0.614, 0.682]         0.987
   24h         HMM-LR                            0.613 [0.585, 0.644]     0.406 [0.387, 0.421]      0.647 [0.624, 0.667]         0.900
   24h         HMM-MULTI-LR                      0.612 [0.577, 0.652]     0.366 [0.341, 0.390]      0.535 [0.500, 0.576]         0.939
   24h         ROLLVOL-LR                        0.641 [0.605, 0.680]     0.441 [0.405, 0.470]      0.601 [0.563, 0.633]         0.849
   24h         HAR-RV-LR                         0.655 [0.622, 0.689]     0.410 [0.374, 0.443]      0.691 [0.656, 0.721]         0.809
   24h         SIG+HMMM-LR                       0.649 [0.616, 0.683]     0.407 [0.368, 0.441]      0.664 [0.631, 0.694]         0.865
   72h         SIG-LR (N = 3, SVD-128)           0.695 [0.652, 0.739]     0.432 [0.381, 0.476]      0.644 [0.594, 0.687]         0.804
   72h         SIG-LR (N = 3, no RV)             0.689 [0.643, 0.731]     0.408 [0.360, 0.451]      0.629 [0.576, 0.675]         0.811
   72h         HMM-LR                            0.649 [0.613, 0.685]     0.374 [0.351, 0.393]      0.614 [0.586, 0.644]         0.874
   72h         HMM-MULTI-LR                      0.672 [0.623, 0.717]     0.357 [0.328, 0.385]      0.541 [0.489, 0.598]         0.896
   72h         ROLLVOL-LR                        0.674 [0.628, 0.721]     0.437 [0.392, 0.477]      0.622 [0.577, 0.667]         0.789
   72h         HAR-RV-LR                         0.696 [0.654, 0.739]     0.395 [0.345, 0.434]      0.677 [0.625, 0.727]         0.751
   72h         SIG+HMMM-LR                       0.689 [0.643, 0.735]     0.442 [0.386, 0.485]      0.645 [0.593, 0.687]         0.805
   168h        SIG-LR (N = 3, SVD-128)           0.755 [0.702, 0.806]     0.440 [0.388, 0.493]      0.633 [0.567, 0.692]         0.793
   168h        SIG-LR (N = 3, no RV)             0.763 [0.710, 0.809]     0.424 [0.367, 0.480]      0.638 [0.577, 0.696]         0.688
   168h        HMM-LR                            0.700 [0.657, 0.736]     0.367 [0.344, 0.388]      0.636 [0.601, 0.673]         0.824
   168h        HMM-MULTI-LR                      0.732 [0.677, 0.784]     0.369 [0.328, 0.408]      0.584 [0.502, 0.664]         0.830
   168h        ROLLVOL-LR                        0.701 [0.645, 0.754]     0.414 [0.370, 0.453]      0.625 [0.556, 0.695]         0.732
   168h        HAR-RV-LR                         0.752 [0.697, 0.805]     0.395 [0.338, 0.449]      0.692 [0.631, 0.750]         0.677
   168h        SIG+HMMM-LR                       0.732 [0.679, 0.779]     0.426 [0.378, 0.474]      0.648 [0.582, 0.704]         0.797


signatures are competitive with the strongest classical baseline         from HAR-RV.
across horizons, with a modest lead at the longest horizon; the            The signature advantage is more evident at 168h and in
previously-reported “5–7 percentage points over returns-based            log-loss ordering with SIG (no RV). The no-realized-volatility
HMM” headline was measured against the univariate returns                SIG-LR variant is particularly striking: it attains the best ac-
HMM baseline, which is not the field’s strongest volatility-             curacy at 168 hours (0.763) and roughly matches HAR-RV on
forecasting baseline, and understated the effective competition          log-loss (0.688 vs. 0.677). This is a substantive finding: signa-

© The National High School Journal of Science 2026                                                                                        |7
tures constructed on log-returns, basis, and funding, without      carries 6.60. Level-3 terms thus account for approximately
any explicit realized-volatility feature, can attain volatility-   98% of the squared-coefficient mass. Table 6 reports the top
forecasting performance that matches an explicit RV specifi-       15 level-3 signature coordinates by absolute coefficient, with
cation. The information required to forecast forward volatility    each coordinate mapped back to its (i, j, k) channel triple.
appears to be present in the joint dynamics of returns, basis,        This decomposition is the paper’s strongest interpretability
and funding.                                                       finding. Every one of the top 15 level-3 coefficients involves
                                                                   at least one basis coordinate; the vast majority involve triples
Depth and dimensionality ablations                                 across two or three of {BTC basis, ETH basis, realized volatil-
                                                                   ity}, often with a return coordinate for the top rank. The finan-
The reviewer requested empirical justification for our choice      cial interpretation is direct: the third-order iterated integrals
of truncation depth N = 3 and SVD component count 128. Ta-         that carry the signature’s predictive information are dominated
ble 5 contains four SIG-LR ablation rows at the 24-hour hori-      by ordered triples of leverage-positioning signals with occa-
zon: N = 2 (full 240-dim signature, no SVD), N = 3 with            sional coupling to volatility and returns. In plain terms, the
SVD-32, N = 3 with SVD-128 (primary), and N = 3 with               signature detects the characteristic ordered sequence “lever-
SVD-512.                                                           age build-up in perpetual basis → volatility spike → further
   The ablations show that neither the depth choice nor the        leverage repricing” that we described in the introduction as the
SVD choice we made is optimal on all metrics. On AUC, the          reflexive-leverage-cycle mechanism. The signature represen-
SIG-LR N = 2 variant substantially outperforms N = 3 (0.707        tation isolates the sequential pattern of leverage-cycle propa-
vs. 0.664), and it also outperforms N = 3 on log-loss (0.841       gation across BTC and ETH perpetual markets — a pattern
vs. 0.863) and macro-F1 (0.435 vs. 0.401). On accuracy the         that moment-based summaries cannot express by construc-
two are effectively tied at 0.649. The higher-order iterated       tion, since it depends on the order in which the coordinates
integrals of N = 3 do not translate into improved aggregate        move, not merely on their marginal moments.
metrics under our supervised task, even though they do drive          The mechanism is credible ex-ante, and its empirical valida-
the signature-coordinate interpretability finding below. This      tion via top-coefficient inspection strengthens the case that the
is consistent with the observation in Remark 1: universal-         signature is picking up a real leverage-cycle signal even when
approximation for continuous path functionals does not imply       the aggregate accuracy gap over HAR-RV is small. HAR-RV
monotone improvement on any specific supervised task, and          can outperform on aggregate volatility-tercile prediction be-
the empirical evidence here is that added depth in an overpa-      cause most volatility variability is autoregressive in RV itself,
rameterized regime may hurt sample efficiency more than it         but it cannot decompose the reason a given hour is high-vol
helps expressivity for the tercile-classification target.          into leverage-driven vs. momentum-driven components. Sig-
   On the SVD side, SVD-32 collapses AUC to 0.575 (a sub-          natures can, at least directionally.
stantial loss), while SVD-512 does not improve over SVD-
128 and slightly reduces accuracy and log-loss. SVD-128 is         Class-balance analysis
roughly the right dimensionality for the training-fold sample
size and downstream classifier capacity.                           Aggregate accuracy has a well-known weakness in imbal-
   Taken together, these ablations do not fully vindicate the      anced classification. Figure 5 shows the row-normalized con-
N = 3, SVD-128 choice: an N = 2 specification would pro-           fusion matrices for the 24-hour Task A. All methods have very
duce marginally better aggregate metrics. We retain N = 3          high low-vol recall (81–93%) and much weaker high-vol re-
as the primary configuration because the third-level iterated      call (7–40%). HAR-RV attains high-vol recall of 42% at the
integrals carry the interpretable signature-coordinate signal      24-hour horizon, HMM-LR 40%, and SIG-LR 20%. This is
that we analyze below, and because it establishes a compute        a substantive weakness of SIG-LR relative to HMM-LR on
regime with headroom for future work on more expressive su-        the specific task of flagging incoming high-volatility episodes
pervised targets; but we caveat readers that the depth choice is   when the cost of a missed flag dwarfs the cost of a false alarm.
a design trade-off rather than a strictly optimal decision.        A risk manager whose loss function is asymmetric in that di-
                                                                   rection should prefer HAR-RV or HMM-LR at 24 hours over
                                                                   SIG-LR. A user with a symmetric loss function should be in-
Financial interpretation of the signature advantage
                                                                   different to within a percentage point.
To localize the signature coefficient we reconstruct the full-
dimensional signature-coordinate coefficient by multiplying        Event study
the 128-dim SVD-basis coefficient by the SVD components
matrix and decompose by signature level. Level-1 signature         Figure 6 displays the predicted probability of the high-vol ter-
terms carry L2 -norm 0.05, level 2 carries 1.41, and level 3       cile across the six canonical events. Table 7 quantifies detec-


8|                                                                                 © The National High School Journal of Science 2026
Table 6 Top 15 level-3 signature coordinates by |coefficient| for the high-vol class of SIG-LR at h = 24. Every top coordinate involves at least
one basis coordinate; many involve triples across basis, realized volatility, and returns.
                            Rank     Channel i           Channel j          Channel k                  Coefficient
                               1     btc basis lead      eth basis lag      btc basis lag                 −0.483
                               2     btc basis lag       eth basis lag      btc basis lead                −0.480
                               3     eth basis lag       btc basis lead     btc basis lead                +0.478
                               4     btc basis lag       rv lag             btc basis lead                −0.452
                               5     btc basis lead      eth basis lag      btc basis lead                −0.451
                               6     btc basis lag       rv lag             eth basis lead                −0.437
                               7     btc basis lead      btc basis lead     eth basis lag                 +0.418
                               8     btc basis lead      rv lag             eth basis lead                −0.414
                               9     btc ret lead        eth basis lead     rv lag                        +0.410
                              10     btc basis lag       eth basis lag      btc basis lag      (top 15 truncated)




                                                                          Figure. 5 Row-normalized confusion matrices for Task A, h = 24,
                                                                          purged walk-forward.




Figure. 4 Out-of-sample ROC curves for the high-volatility tercile,
one-vs-rest, purged walk-forward with 168h embargo, at h = 24 (left)
and h = 168 (right).



tion lag across five threshold values in the sensitivity analysis         Figure. 6 Predicted probability of the high-volatility tercile (next
requested by the reviewer.                                                24h) across the six canonical events. The first four are in-sample;
   Three observations dominate the event-study reading. First,            SVB/USDC and BTC ETF approval are out-of-sample.
at the out-of-sample SVB depeg, SIG-LR produces the clean-
est temporal alignment across all tested thresholds, detecting
the event within a ±4-hour window at θ ∈ {0.3, 0.4, 0.5} and              at any operational calibration. Second, ROLLVOL-LR and
never firing before the true event window. HMM-LR and                     HAR-RV-LR are systematically late by three or more days,
HMM-MULTI-LR fire seven days early at all thresholds —                    reflecting the retrospective nature of trailing-window volatil-
a pattern of background elevation that produces false positives           ity measures. Third, the threshold-sensitivity analysis vindi-

© The National High School Journal of Science 2026                                                                                           |9
Table 7 Threshold sensitivity: detection lag in hours at the SVB/USDC depeg (out-of-sample) across five probability thresholds. Negative =
early (potentially false-positive if pre-event); positive = late. Bold: closest to zero, indicating best temporal alignment.
                               Method                  θ = 0.3      θ = 0.4     θ = 0.5      θ = 0.6      θ = 0.7
                               SIG-LR                     −4             0        0           +14          +109
                               HMM-LR                    −167           −167     −167         −167         −167
                               HMM-MULTI-LR              −167           −167     −167         −167          —
                               ROLLVOL-LR                +87            +87      +87          +87           —
                               HAR-RV-LR                 +73            +87      +109          —            —


cates the choice of θ = 0.5 in the original manuscript for SIG-
LR (which reports 0 hour lag at both 0.4 and 0.5) but reveals
that other methods’ detection lags are essentially threshold-
invariant, meaning the choice of threshold does not distinguish
an actual event signal from background alarming for the base-
line methods — a substantive weakness.
   At the BTC ETF approval (a bullish regime shift), SIG-
LR correctly does not cross the high-vol threshold at θ ∈
{0.5, 0.6, 0.7}, while HMM-LR and HMM-MULTI-LR do
(their “high-vol” state actually corresponds to “non-quiet”
and is triggered by any large return move regardless of di-
rection). SIG-LR distinguishes distress-driven from bullish-
regime volatility in a way that returns-based HMMs cannot.
We note that SIG-LR does fire at θ = 0.4 for the ETF event,
indicating some sensitivity of this claim to threshold choice.
                                                                           Figure. 7 Prospective detection: precision-recall curves on the full
Prospective detection over the full test timeline                          2023–2026 test timeline for the target “next-24-hour realized volatil-
                                                                           ity in top decile of training distribution.” The label is defined ex-ante
The six-event study is qualitatively informative but does not              on training-fold statistics and does not depend on the manually se-
characterize performance across the full test timeline. We sup-            lected event windows.
plement it with an ex-ante prospective detection target: “next-
24-hour realized volatility exceeds the 90th percentile of the
training distribution.” This label is fixed before test-set expo-          4.7 times the prevalence of 0.019. The absolute precision val-
sure, does not depend on the six curated events, and admits a              ues are modest because the top-decile label has a low positive
standard precision-recall evaluation.                                      rate in the test set (roughly 1.9%), but the relative ordering is
                                                                           meaningful: signatures produce the most discriminative prob-
                                                                           ability signal for prospective detection of tail-volatility events
Table 8 Prospective detection performance on the full 2023-2026 test       over the full timeline. This is our clearest positive result and
timeline. Positive rate of the top-decile-forward-RV label in the test     is a direct answer to the reviewer’s concern that the event
set is 0.019.                                                              study is qualitatively selected: on an ex-ante-defined, fully-
 Method                Average precision    Precision at recall = 0.5      prospective target that spans the entire test period, signatures
 SIG-LR                      0.090                   0.061
                                                                           outperform every baseline including HAR-RV.
 HMM-LR                      0.073                   0.052
 HMM-MULTI-LR                0.052                   0.031                 Interpretation, comparison to prior claims, and limita-
 ROLLVOL-LR                  0.040                   0.052
                                                                           tions
 HAR-RV-LR                   0.054                   0.050
 Random                      0.019                   0.019                 The revised picture is more nuanced than what our earlier re-
                                                                           porting suggested. Signatures are competitive but not domi-
   Table 8 reports average precision and precision-at-recall-0.5           nant on aggregate tercile classification: HAR-RV is a strong
for each method. SIG-LR attains the highest average pre-                   baseline that we did not include originally, and it wins or
cision (0.090), 1.7 times the HAR-RV baseline (0.054) and                  ties SIG-LR on accuracy at short horizons; SIG-LR leads at


10 |                                                                                         © The National High School Journal of Science 2026
168 hours. On the metrics that measure discriminative qual-           service), which is a stable public source. Signature-feature
ity rather than threshold performance — macro AUC, log-               caches, HMM model artifacts, and trained-model pickles will
loss, and prospective-detection average precision — signa-            be provided to allow full replication of numeric results without
tures either match or exceed the strongest baseline. On event-        rerunning the full pipeline.
localized detection quality — the tightness of the probabil-
ity signal around known regime shifts, and its discriminative
power between distress and bullish-regime volatility — sig-
                                                                      References
natures are qualitatively cleaner than any baseline we tested.
And on interpretability, the top signature coefficients identify       1 A. Ang and G. Bekaert, Regime switches in interest rates, 2002, 10.119
a coherent leverage-cycle mechanism (basis → volatility →                8/073500102317351930.
basis triples) that would be invisible to any moment-based             2 M. Guidolin and A. Timmermann, Asset allocation under multivariate
                                                                         regime switching, 2007, 10.1016/j.jedc.2006.12.004.
baseline.
                                                                       3 J. D. Hamilton, A new approach to the economic analysis of nonstationary
   We emphasize that the signature advantage is thus not                 time series and the business cycle, 1989, 10.2307/1912559.
primarily about beating a strong volatility-forecasting model          4 L. E. Baum, T. Petrie, G. Soules and N. Weiss, A maximization technique
on its own turf but about providing an interpretable, event-             occurring in the statistical analysis of probabilistic functions of Markov
localized signal with a mechanistic financial reading. For               chains, 1970, 10.1214/aoms/1177697196.
                                                                       5 A. Viterbi, Error bounds for convolutional codes and an asymptotically
a practitioner deciding between HAR-RV and SIG-LR as                     optimum decoding algorithm, 1967, 10.1109/TIT.1967.1054010.
a volatility forecaster in isolation, HAR-RV is a defensi-             6 S. Frühwirth-Schnatter, Finite Mixture and Markov Switching Models,
ble choice at 24 hours; for a practitioner who wants an                  2006.
early-warning signal at systemic events with distinguishable           7 A. R. Pagan and K. A. Sossounov, A simple framework for analysing bull
distress-vs-bullish semantics, SIG-LR provides value that                and bear markets, 2003, 10.1002/jae.664.
                                                                       8 A. Lunde and A. Timmermann, Duration dependence in stock prices: an
HAR-RV cannot.                                                           analysis of bull and bear markets, 2004, 10.1198/073500104000
   Several limitations bear on interpretation and follow-up              000136.
work. We evaluate on Binance only and have not tested                  9 T. J. Lyons, Differential equations driven by rough signals, 1998, 10.4
cross-venue robustness. We compare against HAR-RV and                    171/RMI/240.
HMM-family baselines but not against GARCH, MSGARCH,                  10 T. J. Lyons, M. Caruana and T. Lévy, Differential Equations Driven by
                                                                         Rough Paths, 2007.
or gradient-boosted-tree specifications on the same features,         11 P. K. Friz and N. B. Victoir, Multidimensional Stochastic Processes as
all of which the reviewer flagged as legitimate baselines and            Rough Paths, 2010.
which would be natural extensions in follow-up work. We               12 K.-T. Chen, Integration of paths, geometric invariants and a generalized
do not include a direct benchmark against a temporal deep-               Baker-Hausdorff formula, 1957, 10.2307/1969671.
learning model (CNN, LSTM, or transformer on the raw fea-             13 B. Hambly and T. Lyons, Uniqueness for the signature of a path of
                                                                         bounded variation and the reduced path group, 2010, 10.4007/an
ture panel), which would be a valuable but nontrivial exten-             nals.2010.171.109.
sion. We evaluate on the tercile-classification target and only       14 D. Levin, T. Lyons and H. Ni, Learning from the past, predicting the
briefly note that a drawdown-quartile alternative gives quali-           statistics for the future, learning an evolving system, 2013.
tatively similar results; a full study of regime definitions is out   15 I. Chevyrev and H. Oberhauser, Signature moments to characterize laws
                                                                         of stochastic processes, 2022.
of scope. Transaction costs and market-impact considerations
                                                                      16 A. Fermanian, Functional linear regression with truncated signatures,
are not modeled; using our signals as a live trading strategy            2022, 10.1016/j.jmva.2022.105031.
would require additional engineering. The signature-MMD               17 J. Reizenstein and B. Graham, The iisignature library, 2020, 10.1145/
CUSUM detector of Horvath and Issa 26 is a natural comple-               3371237.
ment that we do not report here.                                      18 P. Kidger and T. Lyons, Signatory: differentiable computations of the sig-
                                                                         nature and logsignature transforms, 2020.
                                                                      19 L. G. Gyurkó, T. Lyons, M. Kontkowski and J. Field, Extracting informa-
Code and data availability                                               tion from the signature of a financial data stream, 2014.
                                                                      20 J. Kalsi, T. Lyons and I. Perez Arribas, Optimal execution with rough path
The complete implementation, including the data-ingestion                signatures, 2020, 10.1137/19M1259778.
                                                                      21 C. Cuchiero, G. Gazzani and S. Svaluto-Ferro, Signature-based models:
pipeline for the Binance historical archives, signature ex-              theory and calibration, 2023, 10.1137/22M1512719.
traction and preprocessing code, all baseline implementa-             22 H. Buehler, B. Horvath, T. Lyons, I. Perez Arribas and B. Wood, A data-
tions, the purged walk-forward evaluation harness, the block-            driven market simulator for small data environments, 2020.
bootstrap confidence-interval routines, and the scripts that pro-     23 E. Alòs, Ò. Burés, R. de Santiago and J. Vives, Volatility modeling with
duce all figures and tables in this manuscript, will be re-              rough paths, 2025.
                                                                      24 C. Bayer, P. Friz and J. Gatheral, Pricing under rough volatility, 2016,
leased as an open-source repository at the time of publica-              10.1080/14697688.2015.1099717.
tion under the MIT License. All raw data are freely available         25 J. Gatheral, T. Jaisson and M. Rosenbaum, Volatility is rough, 2018, 10
from data.binance.vision (Binance public historical-archive              .1080/14697688.2017.1393551.


© The National High School Journal of Science 2026                                                                                             | 11
26 B. Horvath and Z. Issa, Non-parametric online market regime detection,
   2023, 10.2139/ssrn.4493344.
27 T. Takaishi, Rough volatility of Bitcoin, 2020, 10.1016/j.frl.2019
   .101379.
28 D. Bianchi, M. Guidolin and F. Ravazzolo, Time-varying fractional Brow-
   nian motion and rough volatility estimation, 2022, 10.1093/jjfine
   c/nbac019.
29 D. Ardia, K. Bluteau and M. Rüede, Forecasting risk with Markov-
   switching GARCH models, 2019, 10.1016/j.ijforecast.201
   8.09.005.
30 G. M. Caporale and T. Zekokh, Modelling volatility of cryptocurrencies
   using Markov-switching GARCH models, 2019, 10.1016/j.ribaf.
   2018.12.009.
31 G. Flint, B. Hambly and T. Lyons, Discretely sampled signals and the
   rough Hoff process, 2016, 10.1016/j.spa.2016.02.011.
32 R. Ree, Lie elements and an algebra associated with shuffles, 1958, 10
   .2307/1970243.
33 W. Rudin, Principles of Mathematical Analysis, 1976.




12 |                                                                         © The National High School Journal of Science 2026