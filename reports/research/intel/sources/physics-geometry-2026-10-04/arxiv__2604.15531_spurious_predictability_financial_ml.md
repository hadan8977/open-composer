source: https://arxiv.org/pdf/2604.15531
fetched_utc: 2026-10-04T18:41:35Z
bytes_raw: 1229302

Spurious Predictability in Financial Machine Learning
                                                                                 Sotirios D. Nikolopoulos∗
                                                          Department of Accounting and Finance, University of Peloponnese, Greece
arXiv:2604.15531v1 [q-fin.ST] 16 Apr 2026




                                                                                                 Abstract
                                                          Adaptive specification search generates statistically significant backtests even under
                                                      martingale-difference nulls. We introduce a falsification audit testing complete predictive
                                                      workflows against synthetic reference classes, including zero-predictability environments and
                                                      microstructure placebos. Workflows generating significant walk-forward evidence in these
                                                      environments are falsified. For passing workflows, we quantify selection-induced performance
                                                      inflation using an absolute magnitude gap linking optimized in-sample evidence to disjoint
                                                      walk-forward realizations, adjusted for effective multiplicity. Simulations validate extreme-value
                                                      scaling under correlated searches and demonstrate detection power under genuine structure.
                                                      Empirical case studies confirm that many apparent findings represent methodological artifacts
                                                      rather than genuine predictability.
                                                      Keywords: backtest inflation, specification search, falsification audit, walk-forward validation,
                                                      data leakage, absolute magnitude gap.
                                                      JEL classifications: C52, C53, C55, G17.


                                            1        Introduction
                                            The integration of machine learning into financial econometrics has expanded the set of predictors,
                                            functional forms, and estimation strategies available in empirical finance. Methods such as random
                                            forests, gradient boosting, and neural networks are now common in applications spanning asset
                                            pricing and macroeconomic forecasting (Gu et al., 2020; Athey, 2019). However, standard machine
                                            learning validation methods assume approximately i.i.d. data and can fail under the temporal
                                            dependence, non-stationarity, and causal ordering constraints of financial time series (Varian, 2014;
                                            Diebold, 2015; Bergmeir et al., 2018). As a result, empirical conclusions can be driven as much by
                                            the evaluation procedure as by the model class.
                                                 Recent evidence highlights both the promise and fragility of ML-based findings in finance. Some
                                            studies report economically positive gains from ML-driven forecasting signals (van Binsbergen et al.,
                                            2023), while subsequent work shows that these gains often disappear once data handling, timing,
                                            and bias controls respect the information available at each decision point (Zhang et al., 2025).
                                            Related evidence suggests that results can be highly specification-dependent, with many variants
                                            failing to outperform appropriate benchmarks once evaluation protocols are standardized (Campbell
                                            et al., 2024). These findings motivate evaluation procedures that explicitly account for adaptive
                                            search and temporal constraints. In particular, the contrast between the gains documented by van
                                            Binsbergen et al. (2023) and the sensitivity to leakage and protocol details emphasized by Zhang
                                            et al. (2025) illustrates how workflow integrity can be a binding constraint for interpreting empirical
                                            performance.
                                                ∗
                                                    Email: s.nikolopoulos@go.uop.gr


                                                                                                      1
    This problem is not unique to machine learning. Empirical finance has long faced challenges
in out-of-sample stability and replication. Harvey et al. (2016) documented the extent of factor
proliferation and emphasized the role of data mining, while Hou et al. (2020) showed that many
published anomalies do not survive replication under more robust testing. Taken together, these
literatures point to two interacting sources of distortion in predictive research: adaptive specification
search and validation protocols that inadvertently leak future information.
    The identification problem is to separate genuine predictability—reflecting a stable relationship
between available information and future outcomes—from spurious predictability generated by
selection bias, information leakage, or violations of temporal ordering. This problem is acute in
finance because signals are weak, dependence is persistent, and structural breaks are common (Engle,
1982; Campbell et al., 1997). Random cross-validation can break the temporal order of observations,
inducing look-ahead bias (Bergmeir et al., 2018). More broadly, these issues relate to inference after
model selection (Belloni et al., 2014; Lee et al., 2016) and to the data-snooping literature (White,
2000; Hansen, 2005; Lopez de Prado, 2018), which examines how repeated evaluation and selection
inflate reported performance under the null.
    We propose an evaluation protocol that treats falsification as a prerequisite for interpreting
backtest performance. The protocol evaluates the complete modeling workflow—including feature
construction, tuning, selection, and portfolio mapping—on induced-null environments that preserve
key features of financial data while removing any conditional mean predictability. Performance is
assessed via strict walk-forward validation that enforces causal ordering. The observed walk-forward
winner statistic is compared to its distribution under the null, estimated by Monte Carlo simulation.
Systematic performance in these environments signals workflow invalidity—such as information
leakage, selection distortion, or timing errors—rather than evidence of predictability.
    We also develop diagnostics to quantify the magnitude of selection-induced inflation.
                                                                                       √        Under a
global martingale-difference null, the optimized in-sample winner statistic grows as log Keff , where
Keff measures the effective number of independent strategies after accounting for correlation. In
contrast, leakage-robust walk-forward evaluation remains stochastically bounded under the same
null. Monte Carlo experiments quantify inflation across correlated strategy families, showing that
effective multiplicity—not the nominal number of specifications—determines the expected in-sample
maximum. To summarize inflation for the selected configuration, we report a stabilized Backtest
Inflation Factor (BIF) and complementary gap-based diagnostics that remain interpretable when
walk-forward evidence is weak.
    Empirical case studies illustrate recurrent confounds. Predictive models can reproduce known
systematic risk premia, generating statistically significant gross returns while delivering zero alpha
after factor adjustment (Fama and French, 1993). Validation choices in volatility forecasting can
mechanically improve reported performance under null settings when random cross-validation is
used instead of strict walk-forward evaluation. These examples illustrate how the audit framework
distinguishes methodological artifacts from genuine predictive content.
    We emphasize that our objective is aligned with the broader goal of promoting credible empirical
finance. For example, Gu et al. (2020) demonstrate the economic value of machine learning in
asset pricing, while Jensen et al. (2023) conclude that factor research exhibits substantial internal
and external validity once inference is grounded in economically appropriate benchmarks and
multiplicity is handled in a dependence-aware manner, supported by transparent code and data.
Our contribution is complementary: rather than re-litigating factor-level replicability, we provide
a workflow-level diagnostic that screens for pipeline invalidity. By “workflow” we mean the full
mapping from raw data to executed positions, encompassing preprocessing, tuning, and timing
alignment. This diagnostic screens for upstream failures (e.g., leakage, temporal misalignment, and
protocol artifacts) that can compromise any inferential framework—Bayesian or frequentist—if left

                                                   2
unchecked.
    The remainder of the paper is organized as follows. Section 2 formalizes mechanisms generating
spurious predictability. Section 3 establishes the asymptotic motivation for the scaling behavior
under global nulls and defines the inflation diagnostics. Section 4 defines the falsification audit
and the induced-null environments used as reference nulls. Section 5 validates the framework
through Monte Carlo simulations. Section 6 presents empirical applications in returns and volatility
forecasting. Section 7 discusses implications, and Section 8 concludes. The Appendices provide
asymptotic derivations, complete specifications of the induced-null environments, and additional
robustness analyses.


2     Mechanisms of Spuriousness in Financial Machine Learning
The core premise of this work is that statistical validation in financial machine learning constitutes
a joint test of two hypotheses: the existence of a predictive signal and the integrity of the research
workflow. Traditional backtesting conflates these, interpreting a high Sharpe ratio as evidence of
the former while ignoring the latter. We organize our taxonomy of failure around the compounding
cascade illustrated in Figure 1. This cascade typically originates with data leakage, is amplified by
selection bias, and is ultimately cemented by specification error.

2.1   The Global Null and Reference Classes
To formalize these failures, we define the Global Null hypothesis (H0 ) as the state where excess asset
returns rt follow a martingale difference sequence (MDS) with respect to the public information set
Ft−1 , such that E[rt | Ft−1 ] = 0 (Campbell et al., 1997). Under H0 , no algorithm should systemati-
cally extract excess returns. However, empirical financial data exhibits stylized facts—volatility
clustering, heavy tails, and leverage effects—that can be exploited by overfitted models to generate
spurious significance even when the conditional mean is zero (Cont, 2001; Mandelbrot, 1963).
    To rigorously test this, we define Induced-Null environments. These include strict martingale
difference reference classes and targeted placebos that preserve zero expected excess return in
the latent efficient returns, yet may embed predictable transient structures (e.g., microstructure
noise or bid–ask bounce) in observed prices. A workflow that generates statistically significant
walk-forward performance on strict MDS reference classes is statistically falsified, demonstrating a
capacity to hallucinate signal. Conversely, performance on targeted placebos (such as the bid-ask
bounce environment in Section 4) constitutes economic falsification, indicating the exploitation of
non-investable artifacts rather than fundamental value.

2.2   The Cascade of Spuriousness
The distinct mechanisms of spuriousness rarely occur in isolation; rather, they interact sequentially.
The process often begins with data leakage, where model development conditions on information that
is not measurable with respect to the filtration Ft−1 , so the feature set implicitly contains signals
that would not have been available at the time of decision. While gross look-ahead bias is rare in
mature workflows, subtler forms are endemic (Lopez de Prado, 2018). These include normalization
leakage, where features are scaled using statistics computed over the full sample rather than an
expanding window; survivorship bias, where the investment universe is conditioned on constituents
surviving to time T ; and cross-validation contamination, where overlapping labeling horizons or
preprocessing choices allow information to bleed across folds. Leakage lowers the effective noise



                                                  3
floor and creates an artificial predictability that is indistinguishable from alpha during in-sample
training.
    This artificial predictability amplifies selection bias. Selection bias occurs when a researcher or
algorithm evaluates K candidate specifications and reports only the specification k ∗ that maximizes
                                                                            ∗ = max |Z
an absolute performance metric, typically the t-statistic, so that ZIS                  k  IS,k |. Under
Gaussian statisticspand independence, the expected maximum absolute statistic under the global null
is approximately 2 ln(2K) up to lower-order terms, so even a modest search (e.g., K ≈ 100) can
generate apparently significant in-sample results by chance (Harvey et al., 2016). When candidates
are correlated, the relevant multiplicity is Keff ≤ K, and redundancy collapses Keff toward unity,
attenuating extreme-value inflation relative to the nominal count K. Even under a true signal,
selection induces a Winner’s Curse: the selected model’s estimated effect size tends to exceed the
population parameter because selection preferentially retains realizations where estimation error
aligns with the signal direction (Bailey and López de Prado, 2014).
    The cascade concludes with specification error, which we treat as an economic interpretation
failure rather than a mere statistical misfit. Inflated statistics produced by leakage and selection
encourage structural narratives that do not survive transport to the walk-forward distribution. A
workflow may be statistically valid yet structurally spurious if it attributes predictive power to alpha
that is in fact compensation for latent risk exposures such as momentum or liquidity, or if it fits
transient regime relationships that are not stable out of sample (Fama and French, 1993; Carhart,
1997). In our framework, these constitute specification errors because the model may describe the
training set but fails to generalize to the target domain or is misidentified as an anomaly rather
than a risk premium.

            Data Leakage        Amplifies      Selection Bias     Emboldens Specification Error
          (Artificial Signal)               (Optimizer Targeting)          (Interpretation Failure)

                                             The optimizer pref-
                                              erentially selects
                                        leaked information, inflating
                                            effective multiplicity.

Figure 1: The Cascade of Spuriousness. Data leakage creates artificial signal-to-noise ratios; adaptive
selection algorithms preferentially target these artifacts, resulting in inflated test statistics that are
subsequently misidentified as structural alpha.


2.3   Relation to Data-Snooping Corrections
This framework complements but remains distinct from post-hoc corrections for data snooping, such
as the Reality Check (White, 2000) or the Superior Predictive Ability (SPA) test (Hansen, 2005).
Those methods adjust the critical values of the test statistic to account for the size of the universe
(K) after the fact. However, they rely on the assumption that the researcher knows the true value
of K. In modern machine learning, K is often implicit, effectively infinite, or obfuscated by the
adaptive nature of the search. Practically, these tools occupy distinct stages in the quantitative
lifecycle. The Falsification Audit (Section 4) serves as a pre-commitment filter during workflow
development, rejecting architectures prone to hallucination. The Inflation Diagnostic (Section
3) is applied during internal validation to quantify the gap between in-sample optimization and
walk-forward reality. In contrast, corrections such as the Reality Check are post-hoc inference tools
appropriate for final external reporting.


                                                       4
3     Selection-Induced Backtest Inflation
The falsification motivation in Section 2 is operationalized in Section 4 as an induced-null audit that
screens for workflow invalidity (leakage, temporal misalignment, microstructure exploitation, and
protocol artifacts). Clearing that gate is necessary but not sufficient for economic signal: even under
a martingale-difference global null, adaptive specification search can still produce apparently strong
optimized in-sample backtests.√This section formalizes the behavior of optimized backtests under the
global null, motivates the Θ( log Keff ) scaling law for selection-induced inflation under correlated
search, and defines inflation diagnostics that translate effective multiplicity into an economically
interpretable correction to reported performance, centered on the absolute magnitude gap ∆Z, with
the stabilized Backtest Inflation Factor (BIF) used only as a supplementary within-study ranking
heuristic. The objective is end-to-end pipeline diagnosis; classical data-snooping inference (e.g.,
Reality Check and SPA) remains the appropriate layer when the object of interest is a search-adjusted
p-value for the best-performing specification.

3.1    Formalizing the Global Null Hypothesis
Consider a time series of asset returns {rt }Tt=1 . We define the global null hypothesis as conditional
unpredictability with respect to the filtration Ft−1 generated by all information available at time
t − 1:
                                       E[rt | Ft−1 ] = 0, ∀t.                                       (1)
This implies {rt } is a martingale difference sequence. A candidate strategy k ∈ {1, . . . , K} produces
a signal xt,k ∈ Ft−1 and the realized strategy return is Rt,k = xt,k rt . Under Equation (1),
E[Rt,k | Ft−1 ] = 0, so {Rt,k } is a martingale difference sequence for each fixed k.
    We distinguish two disjoint phases: an in-sample (selection) phase TIS and a walk-forward
(evaluation) phase TWF , with TIS ∩ TWF = ∅. Disjointness requires that the entire mapping from data
to the selected configuration—preprocessing, feature construction, tuning, and model choice—is
measurable with respect to the in-sample σ-field only.
    Define the sample means R̄IS,k and R̄WF,k in the usual way. In finite samples, and in audit envi-
ronments that intentionally embed microstructure frictions, strategy returns can display conditional
heteroskedasticity and mild serial correlation. We therefore employ a HAC variance estimator with
a Bartlett kernel (Newey and West, 1987). We use the sample-size-based rule-of-thumb bandwidth
Ln = ⌊4(n/100)2/9 ⌋ proposed by Newey and West (1994) and widely adopted as a software default,
where n ∈ {nIS , nWF } denotes the sample size of the relevant phase, satisfying Ln → ∞ and
Ln /n → 0 as n → ∞. The studentized statistics are

                                   R̄IS,k                             R̄WF,k
                       ZIS,k ≡ q                ,       ZWF,k ≡ q                     .             (2)
                                VbHAC (R̄IS,k )                     VbHAC (R̄WF,k )
Under Equation (1) and standard regularity conditions, for any fixed k, ZIS,k ⇒ N (0, 1) and
ZWF,k ⇒ N (0, 1) as T → ∞. However, we explicitly note that HAC t-statistics frequently exhibit
severe size distortions in finite samples. For restricted walk-forward evaluation periods (e.g.,
nWF = 252 days), the empirical distribution of ZWF develops heavier tails than the theoretical
N (0, 1) reference. While rule-of-thumb bandwidth selection mitigates first-order autocorrelation, it
does not strictly eliminate finite-sample over-rejection under the null. Consequently, test statistics
relying on asymptotic approximations are anti-conservative for size control in finite samples, tending
to over-reject under the null. When used as an admission gate in the diagnostic audit, this bias
makes the screen conservative with respect to pipeline acceptance.


                                                    5
3.2    The Multiplicity Problem and Effective Multiplicity
In the selection phase, the researcher evaluates K candidate strategies and chooses the most extreme
in-sample result:

                              ⋆
                             ZIS ≡ max |ZIS,k |,           k ⋆ ≡ arg max |ZIS,k |.                      (3)
                                    1≤k≤K                        1≤k≤K

    When candidates are correlated, the nominal K overstates the effective dimensionality of the
search. Let ZIS ≡ (ZIS,1 , . . . , ZIS,K )⊤ and let Σ denote the correlation matrix of ZIS . We define
effective multiplicity via the spectral participation ratio:
                                                           P
                                                              K
                                                                     2
                                                              i=1 λi
                                                   2
                                              (tr Σ)
                                     Keff =          =                  ,                               (4)
                                               ∥Σ∥2F
                                                             PK     2
                                                               i=1 λi

where λ1 , . . . , λK are the eigenvalues of Σ. Since Σ is a correlation matrix, tr(Σ) = K, so equivalently

                                                        K2
                                              Keff =         .                                          (5)
                                                       ∥Σ∥2F

By construction, Keff = K under independence and decreases toward 1 as configurations become
collinear. In high-dimensional regimes, we apply linear shrinkage toward the identity using the
Schäfer–Strimmer estimator (Schäfer and Strimmer, 2005) to ensure Σ remains well-conditioned;
details are in Appendix C.5.

3.3    The Scaling Law of Selection Bias
Selection-induced inflation is governed by the extreme-value behavior of {ZIS,k } after optimization.
Under two-sided selection, ZIS⋆ depends on the effective number of distinct candidates summarized

by Keff .

Proposition 1. Assume ZIS is approximately mean-zero multivariate Gaussian with correlation
matrix Σ, and define Keff by Equation (4). Suppose dependence is generated by a structured,
high-correlation search geometry, for example an approximate-factor structure within families,
        √          √
ZIS,k = ρ Fc(k) + 1 − ρ εk with ρ ∈ (0, 1), heterogeneous family sizes, and independent (Fc , εk ).
Then, as Keff → ∞,                             p        
                                        ⋆
                                    E[ZIS ] = Θ log Keff .

    While each studentized statistic is asymptotically Gaussian as T → ∞, the finite-sample extreme-
value approximation may underestimate the null benchmark for ZIS   ⋆ —and hence the implied inflation

penalty—under heavy-tailed return innovations, especially when K is large relative to T . We
therefore
   √      verify by simulation that, for the sample sizes and search dimensions studied here, the
Θ( log Keff ) approximation remains accurate even under heavy-tailed Student-t innovations (see
the empirical
           √ robustness sweeps in Appendix C.6).
    The Θ( log Keff ) statement should be read as a consequence of Gaussian maximal inequalities
under search geometries whose canonical-metric packing complexity is of order Keff ; Appendix A.1
formalizes this link (Lemma 3) and clarifies that Keff is not claimed to parameterize extremes for
arbitrary Σ.
    In contrast, performance evaluated via a strict walk-forward protocol remains bounded in
probability under the null, provided the evaluation is truly disjoint.


                                                       6
Lemma 1. Assume: (i) the selection rule k ⋆ = arg maxk |ZIS,k | is measurable with respect to the
in-sample σ-field; (ii) walk-forward blocks are generated by a strictly causal evaluation protocol
disjoint from selection; and (iii) standard HAC regularity conditions for Equation (2) hold on the
walk-forward blocks. Then, conditional on TIS , the index k ⋆ is fixed, and under the global null:
                                       ⋆
                                      ZWF ≡ |ZWF,k⋆ | = Op (1).                                     (6)

    The proof is given in Appendix A.

3.4   Quantifying Inflation: The Absolute Gap and Stabilized BIF
To quantify the divergence between optimized in-sample evidence and realizable walk-forward
evidence, the framework relies primarily on the absolute magnitude gap:
                                                ⋆     ⋆
                                          ∆Z ≡ ZIS − ZWF ,                                          (7)
         ⋆ = max                    ⋆
where ZIS        k≤K |ZIS,k | and ZWF = |ZWF,k⋆ |. Because strictly disjoint walk-forward evaluation
remains bounded in probability under the null, ∆Z provides a linear, mathematically continuous
measurement of the extreme-value bias induced by adaptive specification search. Unlike ratio-based
formulations, ∆Z remains strictly well-defined and analytically consistent across the entire domain
of out-of-sample realizations.
    To provide a supplementary relative measure of this degradation, we define the raw Backtest
Inflation Factor as the ratio of the optimized in-sample winner to its walk-forward counterpart:
                                                         ⋆
                                                       ZIS
                                           BIFraw ≡     ⋆ .                                         (8)
                                                       ZWF
Because this raw ratio is mathematically undefined when ZWF   ⋆    = 0, we introduce the stabilized
Backtest Inflation Factor by enforcing a strict denominator floor:
                                                       ⋆
                                                      ZIS
                                      BIFstab
                                         τ    ≡         ⋆ , τ}.                                     (9)
                                                  max{ZWF

Throughout this paper, we set the stability parameter to τ = 0.5. While BIFstab          τ   coincides
with BIFraw for values above this threshold, it saturates at ZIS   ⋆ /τ for highly degenerate models.

Consequently, BIFstab
                    τ   must be interpreted strictly as a numerically stabilized operational heuristic
rather than a high-resolution degradation measure. Furthermore, because the absolute magnitude
of BIFstab
       τ   is heavily dictated by the choice of τ , the metric lacks cross-study comparability. A
backtest inflation factor generated under τ = 0.5 cannot be quantitatively compared to one derived
under τ = 0.3. Therefore, BIFstab
                                τ   functions exclusively as an internal, intra-study ranking heuristic.
Cross-study evaluations and formal benchmarking should therefore rely on the τ -invariant magnitude
gap ∆Z, rather than on BIFstabτ   .


4     The Falsification Audit Framework
The theoretical results in Section 3 establish that performance inflation is an inherent consequence
of adaptive model selection under a global null. To operationalize these insights, we introduce a
falsification-based audit framework that evaluates machine learning pipelines in controlled synthetic
environments. The audit imposes a necessary condition for methodological validity: a pipeline
must not generate systematic performance when the underlying data-generating process contains no
exploitable mean signal.

                                                   7
4.1    Design Principles
The audit framework is grounded in three principles that align machine learning practice with
econometric validation. First, falsifiability shifts the burden of proof: a pipeline is not validated by
historical performance but is falsified if it extracts statistically significant signal from null data. This
follows the logic of placebo tests in causal inference (Imbens and Rubin, 2015). Second, the audit
evaluates the pipeline end-to-end, including preprocessing, feature engineering, and execution timing.
Spurious predictability typically arises from interactions across stages—such as look-ahead bias in
normalization or misaligned execution lags—rather than from the learning algorithm in isolation.
Third, the audit enforces causal validity by requiring that all signals and portfolio decisions at time
t be measurable with respect to Ft−1 and executed in a manner consistent with the directional flow
of time. Disjointness is interpreted operationally: no preprocessing, tuning, or model choice may
use information from evaluation blocks, directly or indirectly.

4.2    Synthetic Null Environments
We construct five synthetic data-generating processes designed to target distinct failure modes.
Environments A, B, D, and E satisfy the martingale-difference restriction E[rt | Ft−1 ] = 0, while
Environment C is a microstructure placebo that intentionally violates the martingale-difference
restriction in observed returns. Full mathematical specifications and default calibrations for all
environments are detailed in Appendix B.

Environment A: White Noise. Returns are i.i.d. Gaussian with zero√mean. This environment
isolates pure selection bias and provides the canonical setting for the Θ( log Keff ) scaling law.

Environment B: Regime-Switching Volatility. A two-state Markov chain governs conditional
volatility while the conditional mean remains zero. This environment detects predictability arising
from improper normalization or scale-based trading rules that "leak" future volatility states.

Environment C: Friction Placebo (Bid–Ask Bounce). This is not a “no-predictability in
observed returns” null. It is a targeted placebo designed to detect timing, indexing, and execution-lag
mistakes that can masquerade as alpha in real implementations when applied to microstructure-
contaminated prices. We simulate a latent efficient return that satisfies the martingale-difference
restriction, then generate an observed return series with Roll-style bid–ask bounce (an MA(1)
component with negative first-order autocorrelation). The intentional violation of the martingale-
difference restriction in observed returns is the diagnostic feature: a correctly implemented workflow
should not convert this transient friction pattern into persistent walk-forward profitability once
signals are aligned and executed properly.

Environment D: Factor Null (Zero Alpha). Returns are driven by a single mean-zero factor
plus idiosyncratic noise. This environment isolates omitted-risk attribution: any apparent alpha
must reflect systematic factor exposure being misread as skill.

Environment E: GARCH(1,1) Volatility Clustering. Returns exhibit persistent conditional
heteroskedasticity while maintaining a zero conditional mean. This environment stresses the
robustness of HAC-based inference and risk adjustment under realistic volatility dynamics.




                                                     8
4.3     The Two-Stage Audit Protocol
The audit proceeds in two stages. Stage 1 falsifies pipelines that generate implausibly large walk-
forward winner magnitudes under induced-null environments designed to preserve the pipeline’s
mechanics while removing economic signal. Pipelines that are not falsified advance to Stage 2,
where the identical end-to-end workflow is executed on the target dataset under a strict disjoint
in-sample/walk-forward split, producing optimized in-sample and walk-forward winner magnitudes
together with inflation diagnostics.

4.3.1    Stage 1: Falsification under induced nulls
Stage 1 tests whether the full pipeline, held fixed, produces spuriously extreme walk-forward winners
under induced-null environments and targeted placebos that preserve the mechanics of the workflow
while stripping out genuine economic signal. The pipeline is executed across the induced-null
environments in a Monte Carlo experiment. For each environment e and replication m = 1, . . . , M ,
the workflow yields a walk-forward winner magnitude ZWF,e,m⋆       drawn from the induced null of the
adaptive selection procedure. Stage 1 is a conservative gate that controls false discovery across
environments; the operational thresholds and decision rule are specified in Section 4.4.

4.3.2    Stage 2: Target-data evaluation
Stage 2 quantifies selection-induced inflation on the target dataset conditional on passing Stage 1.
Pipelines that are not falsified are executed on the target sample under a strict disjoint in-
sample/walk-forward split, with adaptive selection confined to the in-sample block and evaluation
performed only on disjoint walk-forward blocks. This yields the optimized maximum ZIS        ⋆ and its
                             ⋆
walk-forward counterpart ZWF , together with Keff and the associated inflation diagnostics (including
                                               c
BIFstab
     τ   and auxiliary measures). The null-calibrated thresholds and decision rules used to classify
inflation are specified in Section 4.4.
    We compute the test statistics utilizing HAC standard errors to account for residual dependence.
However, we explicitly note that HAC t-statistics converge to the standard normal distribution
asymptotically and frequently exhibit severe size distortions in finite samples. For restricted walk-
forward evaluation periods (e.g., TWF = 252 days), the empirical distribution of ZWF develops
heavier tails than the theoretical N (0, 1) reference. While rule-of-thumb bandwidth selection
(e.g., Newey-West) mitigates first-order autocorrelation, it does not strictly eliminate finite-sample
over-rejection under the null. Consequently, the falsification thresholds derived from asymptotic
approximations may be inherently conservative, classifying marginal noise as statistically significant
out-of-sample evidence.

4.4     Operational Thresholds and Calibration
Stage 1 (falsification gate) utilizes environment-specific critical values for the walk-forward win-
ner magnitude. For each environment e, let ζe,1−α/5 denote the empirical 1 − α/5 quantile of
   ⋆
{ZWF,e,m  }M                                   ⋆
           m=1 . The pipeline is falsified if ZWF,e,obs > ζe,1−α/5 for any e, utilizing a Bonferroni cor-
rection across the multiple testing environments to control the family-wise error rate. We explicitly
note that while this correction rigorously controls false discoveries under the null, it structurally
reduces statistical power; pipelines may fail a specific environment due to finite-sample variation
rather than systematic leakage.
    Stage 2 (inflation classification) applies null-calibrated thresholds strictly to the absolute mag-
nitude gap (∆Z) computed after adaptive search. For a chosen quantile level q, the operational


                                                   9
threshold is defined as:
                                            εq,∆ ≡ Qq (∆Z).                                           (10)
We flag null-implausible inflation if ∆Z > ε0.99,∆ . The recommended threshold values tabulated in
Appendix C.6.7 are strictly illustrative approximations based on idealized search geometries. In
practice, researchers must simulate their own null distributions given their exact pipeline dimensions,
correlation structures (K
                        ceff ), and sample splits (nIS , nWF ) to generate valid reference cutoffs. When
pipeline-specific null draws are unavailable, researchers must adopt a conservative worst-case
calibration corresponding to maximal effective multiplicity.

4.5    Audit Robustness and Limitations
The falsification audit provides necessary conditions for methodological validity but does not
certify economic truth. In principle, adaptive tuning could be used to satisfy a fixed diagnostic
without improving genuine predictive content, constituting a form of overfitting to the audit
itself. The practical constraint is that the audit is intentionally multi-dimensional: passing requires
robustness across five environments targeting distinct failure channels, including multiplicity, leakage,
microstructure timing errors, factor confounding, and volatility-driven artifacts. Satisfying these
constraints simultaneously reduces effective degrees of freedom and limits the flexibility that typically
generates spurious in-sample success, rendering audit-aware tuning costly and fragile.
    A pipeline that passes the audit has demonstrated robustness to a specified set of structural
artifacts. This does not guarantee that its predictive performance on real data reflects a genuine
economic signal; it may still lack economic significance, exhibit poor concentration-adjusted perfor-
mance, or fail to cover transaction costs. The audit is therefore a stress test, not a certification. To
further limit local overfitting to the audit, we recommend following standard benchmark-design
practices: fix the workflow specification prior to audit execution; randomize audit seeds and report
seed sensitivity; reserve a holdout set of null environments (e.g., unseen parameterizations within
the same null reference classes) for out-of-design validation; and publicly archive the audit code and
seeds to enable independent verification.
    The current framework is developed for return prediction tasks with a well-defined trading lag.
Extensions to classification settings (e.g., default prediction, regime labeling) and to non-trading
contexts (e.g., macroeconomic forecasting) require adaptation of the performance metrics and null
constructions, but the core logic of falsification remains transferable.

4.6    Defending Against Meta-Overfitting: The Blind-Parameter Protocol
The deployment of static falsification environments introduces a critical structural vulnerability:
meta-overfitting. If the exact parameters of the null data-generating processes are globally observable,
algorithmic search spaces can be adversarially optimized to bypass the diagnostic without capturing
genuine economic structure. Consequently, passing a static falsification audit is strictly insufficient
to prove out-of-sample validity.
    To mitigate this vulnerability, the audit must operate under a Blind-Parameter Protocol. Under
this architecture, null environments are defined as continuous distributions over structural parameters
rather than fixed point-estimates (e.g., for the MA(1) placebo draw θ ∼ Uniform[−0.8, −0.2] rather
than fixing θ = −0.5). The auditing entity provides a public set of parameter draws (Θdev ) for
pipeline calibration, while securing a disjoint, privately seeded set (Θaudit ) for the final falsification
gate. This forces the workflow to demonstrate robustness across the parameter family, reducing the
scope for adversarial optimization against the audit itself.



                                                    10
5     Simulation Evidence: Validating the Framework
We subject the theoretical framework to a comprehensive computational audit. The objective is
twofold: first, to quantify the magnitude of spurious predictability generated by standard machine
learning workflows under the global null hypothesis; and second, to illustrate how our diagnostics
behave under known structural alternatives that mimic common backtesting pitfalls.
    All simulations are conducted with N = 1,000 Monte Carlo replications per scenario using the
QuantAudit R package. This library serves as the reference implementation for the framework,
integrating modules for synthetic null generation, strict walk-forward validation, and the estimation of
inflation diagnostics (∆Z, K
                           ceff ). The QuantAudit R package and full replication scripts are prepared
for public release and will be made available via GitHub and CRAN upon journal publication to
facilitate independent replication and standardized auditing. Detailed uncertainty estimates and
robustness checks are deferred to Appendix C.
    We evaluate representative simulation strategies categorized by their underlying mechanism.
The RandomBaseline (White Noise Null) serves as a passive control, generating i.i.d. Gaussian
signals under the global null. The Lookahead strategy (Oracle) has access to future returns rt+1 ,
representing the theoretical upper bound of forward-looking bias. DataMiner performs spurious
selection by choosing the in-sample optimal configuration from K = 100 independent noise predictors,
providing the primary test for selection-induced inflation.
    To evaluate structural failure modes, we define three strategies that interact with specific
data-generating features: Contrarian implements a linear mean-reversion signal St = −θrt−1 ;
RegimeDetector applies threshold nonlinearity via state-dependent switching based on GARCH
volatility estimates; and FactorMimic harvests a persistent structural risk premium to evaluate the
conflation of systematic factor exposure with alpha.
    Finally, to investigate capacity-driven inflation—the systematic in-sample performance ampli-
fication induced by adaptive search over high-capacity learners under the global null—and the
impact of correlated hyperparameter search, we evaluate FeatureMining (orthogonal search) against
HyperparameterTuning (correlated XGBoost grid search) and TrendFollowing (causal control).

5.1   The Scaling Law of Selection Bias
We validate Proposition 1 by simulating a researcher who evaluates K independent strategies in
the White Noise environment (Environment A). The researcher selects the configuration with the
                                          ⋆ = max                                                   ⋆
maximum absolute in-sample statistic, ZIS           k≤K |ZIS,k |, and evaluates the selected index k on
                               ⋆
a disjoint walk-forward set, ZWF   = |ZWF,k⋆ |. Table 1 reports the resulting dynamics, and Figure 2
visualizes the scaling behavior.                                     √
     As predicted, optimized in-sample performance scales with log K. The expected maximum
tracks
p        the extreme-value benchmark for the maximum of 2K signed Gaussians, approximately
   2 log(2K). In finite samples, nominally significant in-sample discoveries become essentially certain
as soon as the search budget is moderate. The winner false positive probability exhibits a sharp
transition, rising quickly with K and saturating near certainty for large search spaces despite the
complete absence of signal.
     Crucially, the walk-forward winner magnitude remains on the null scale. Because selection is
performed on disjoint in-sample data, ZWF   ⋆   behaves like the magnitude ofpa fixed configuration
under the null, with E[ZWF⋆ ] remaining close to the half-normal expectation      2/π ≈ 0.80 regardless
of K. The divergence between in-sample and walk-forward evidence is therefore monotone in K and
is summarized by the Backtest Inflation Factor. At K = 1,000, the median BIF0.5 on the reported
subset is 5.12, indicating that optimized in-sample evidence can exceed realized walk-forward


                                                  11
                                     3
          Average Absolute Z−Score




                                     2




                                     1



                                          1                5           10                      50          100     200           500   1000
                                                                              Search Space Size (K)

                                                   Theoretical Bound            In−Sample (Optimized)       Walk−Forward (Unbiased)



Figure √
       2: The scaling law of selection bias. The optimized in-sample winner magnitude grows on
the O( log K) scale under the global null, while the walk-forward winner magnitude remains on
the null scale when selection is performed on disjoint data.




Table 1: The scaling law of selection bias (Environment A, T = 2,520). Winner FWP is the
familywise false positive probability for the selected winner at the nominal threshold |Z| > 1.96.
BIFstab                                                  ⋆
   0.5 reports the median computed on the subset {|ZWF | ≥ 0.5}.


                                         K            ⋆
                                                Mean ZIS             ⋆
                                                               Mean ZWF               ∆Z       BIFstab
                                                                                                  0.5            Winner FWP (%)
                                         1        0.81                 0.77          0.04           0.65                  5.3
                                         5        1.58                 0.78          0.80           1.50                 22.3
                                         10       1.90                 0.81          1.09           1.80                 40.2
                                         50       2.52                 0.82          1.69           2.36                 92.3
                                         100      2.79                 0.82          1.97           2.60                  99.9
                                         200      3.00                 0.81          2.19           2.88                 100.0
                                         500      3.28                 0.83          2.45           3.18                 100.0
                                         1000     3.48                 0.80          2.68           3.33                 100.0




                                                                                     12
evidence by roughly a factor of five solely due to multiplicity. Monte Carlo uncertainty summaries
for the scaling curve are reported in Appendix C.

5.2     The Redundancy Law: Effective Multiplicity under Correlation
Realistic strategy searches are rarely orthogonal, and they are rarely perfectly collinear. To test
whether K ceff provides a usable proxy for effective search dimensionality under dependence, we
simulate K = 500 candidate strategies under the global null in two regimes. First, we use an
idealized clustered construction that spans perfect redundancy (K ceff ≈ 1) to near-independence
(K
 ceff = 500). Second, we verify robustness under imperfect intra-cluster correlation (ρ < 1) with
heterogeneous cluster sizes.

5.2.1    Clustered dependence benchmark
To test whether K
                ceff provides an operational adjustment for selection-driven inflation when candidates
are redundant, we simulate clustered dependence spanning perfect redundancy to near-independence.
Table 2 compares observed in-sample inflation to extreme-value predictions computed using both
nominal K and K ceff .

Table 2: Redundancy law validation (K = 500). Strategies share nclusters latent factors under the
             ceff is the shrinkage-corrected effective multiplicity. EVT(M ) ≈ aM + γbM is the
global null. K
                                                                          √
extreme-value expectation for M standard normal variables, where aM = 2 ln M − ln ln2√M2+ln(4π)
                                                                                           ln M
                                                                                                 ,
         1
bM = √2 ln  M
              , and γ ≈ 0.5772. The Ratio column compares observed inflation to the K
                                                                                    ceff -based
prediction.

            Dependence Regime        K
                                     ceff        ⋆ |]
                                             E[|ZIS     EVT(2K)     EVT(2K
                                                                         ceff )    Ratio
            Perfectly Correlated      1.00     0.77       3.27          0.75       1.029
            5 Clusters               5.03      1.57       3.27          1.63       0.963
            10 Clusters              10.09     1.90       3.27          1.95       0.974
            25 Clusters              25.46     2.26       3.27          2.31       0.978
            50 Clusters              51.74     2.54       3.27          2.57       0.989
            100 Clusters            106.66     2.78       3.27          2.81       0.990
            Independent             500.00     3.26       3.27          3.27       0.998

    The effective multiplicity estimator captures the compression of the search space induced
by correlation. While nominal K is fixed, the in-sample winner magnitude varies substantially
with dependence. The observed winner statistic aligns closely with the EVT(2K       ceff ) benchmark,
indicating that Kceff provides an operational adjustment for selection-driven inflation under the
clustered dependence structures considered.
    The implications for inflation are summarized in Table 3. Median BIFstab      0.5 rises from ap-
proximately 0.62 under near-perfect redundancy to 3.23 under independence, moving with the
independence proxy (K                                  ceff ≈ 1, median BIFstab can fall below one
                       ceff − 1)/(K − 1). In the limit K
                                                                              0.5
due to finite-sample variation, consistent with the absence of systematic selection inflation. Full
distributional summaries and uncertainty intervals are reported in Appendix C.
    A complementary visualization of how redundancy collapses the search space is provided in
Figure 3, which reports Kceff as a function of the number of latent clusters.




                                                 13
                                                                             ceff − 1)/(K − 1).
Table 3: Inflation implications under redundancy. The Independence Proxy is (K
             stab                             ⋆ | ≥ 0.5}.
Median BIF0.5 is computed on the subset {|ZWF

                  Dependence Regime        Independence Proxy      BIFstab
                                                                      0.5
                                                                                 ⋆ ]
                                                                              E[ZWF
                  Perfectly Correlated             0.000             0.62      0.81
                  5 Clusters                       0.008             1.44      0.84
                  10 Clusters                      0.018             1.79      0.79
                  25 Clusters                      0.049             2.22      0.80
                  50 Clusters                      0.102             2.37      0.84
                  100 Clusters                     0.212             2.69      0.82
                  Independent                      1.000             3.23      0.76


5.2.2    Robustness to imperfect intra-cluster correlation
To test whether the redundancy law is an artifact of idealized collinearity, we simulate K =
500 candidate strategies with imperfect intra-cluster dependence. We vary the correlation ρ ∈
{0.6, 0.8, 0.99} and assign strategies to clusters of heterogeneous sizes. Figure q
                                                                                  4 visualizes that lower
correlation increases K
                      ceff and inflates the winner statistic in line with the log K
                                                                                  ceff scaling. As
shown in Table 4, Kceff provides a robust calibration for the expected maximum, converging tightly
to the EVT prediction as the number of independent clusters grows. The approximation naturally
degrades only at the extreme boundary where the search space is approximately a single, highly
noisy cluster.

5.3     Capacity-Driven Inflation: Saturation vs. Inflation
In this section, we compare three machine learning workflows under the global null: FeatureMining
(orthogonal search over independent candidates), HyperparameterTuning (XGBoost tuning over
a correlated configuration family), and TrendFollowing (causal control with a small parameter
grid). Table 5 reports results at K = 400 under the White Noise null environment, and Figure 5
summarizes how in-sample extremeness and K    ceff evolve with nominal search size.
    FeatureMining exhibits the expected inflation regime: K   ceff ≈ K and in-sample extremeness
grows mechanically with the effective number of independent trials, while walk-forward evidence
remains null-like. HyperparameterTuning exhibits capacity-driven inflation: despite low K     ceff , it
produces materially inflated in-sample winners and high in-sample failure rates. The results indicate
that saturation of a correlation-based redundancy measure does not imply immunity to selection
inflation when the learner can fit sample idiosyncrasies on a correlated manifold. TrendFollowing
lies between these regimes, but its effective search dimension is no longer negligible under causal
execution, reaching K ceff ≈ 5.9 at K = 400. Supplementary tables that separate saturation ratios
and in-sample extremeness trajectories by workflow are reported in Appendix C.

5.4     Mechanism: Threshold Amplification
To explain why a low K  ceff on raw predictions can coincide with substantial in-sample extremeness,
we isolate the role of non-linear signal extraction. We simulate highly correlated prediction scores
(ρ = 0.9) and compare the effective multiplicity of the raw scores to the effective multiplicity of
thresholded trading signals. Table 6 reports results at K = 1,000.



                                                   14
Table 4: Redundancy law validation (K = 500) with imperfect correlation. The K ceff -based EVT
benchmark calibrates the expected winner magnitude once the effective search space contains
multiple independent clusters; in the boundary case where the universe is dominated by a single
noisy cluster (K
               ceff near one), the EVT approximation can understate the observed maximum.


                 ρ        Clusters      K
                                        ceff            ⋆ |]
                                               Obs. E[|ZIS      Pred. (EVT)    Error %
                 0.60           1      2.8               2.56          1.34        91.5
                                5     13.7               2.91          2.07        40.5
                               10     26.9               3.07          2.33        31.4
                               25     63.8               3.14          2.64        18.9
                               50    117.8               3.19          2.84        12.3
                              100    204.7               3.26          3.01         8.4
                              500    500.0               3.29          3.27         0.5
                 0.80           1      1.6               2.07          1.01       104.5
                                5      7.8               2.58          1.83        40.7
                               10     15.4               2.81          2.12        32.6
                               25     37.3               2.96          2.45        20.6
                               50     71.5               3.07          2.68        14.6
                              100    133.0               3.18          2.88        10.6
                              500    500.0               3.28          3.27         0.4
                 0.99           1      1.0               1.07          0.76        41.1
                                5      5.1               1.81          1.64        10.5
                               10     10.1               2.16          1.95        10.8
                               25     24.8               2.46          2.30         6.6
                               50     48.4               2.68          2.54         5.3
                              100     93.0               2.91          2.76         5.3
                              500    500.0               3.27          3.27        -0.2




Table 5: Workflow comparison under White Noise at K = 400 (Boosting). Means over N = 1,000
simulations; BIFstab                                        ⋆
                0.5 is the median computed on the subset {|ZWF | ≥ 0.5}.


Workflow              K
                      b eff         ⋆
                              Mean ZIS               ⋆
                                               Mean ZWF     ∆Z     BIFstab
                                                                      0.5     IS Fail (%)   WF Fail (%)
FeatureMining        400.00      3.21            0.84       2.37    2.91        100.0           6.6
Hyperparameter
                      2.93       2.56            0.79       1.77    2.49         88.2           4.7
Tuning
TrendFollowing        5.86       2.19            0.78       1.41    2.12         64.2           5.0




                                                    15
                                         500




                                         400
           Effective Multiplicity Keff


                                         300




                                         200




                                         100




                                          0

                                               1   5      10               25     50    100   500
                                                       Number of Independent Clusters

                                                               Nominal K        Keff




Figure 3: Effective multiplicity under correlation. The estimated K
                                                                  ceff tracks the actual number of
independent clusters as redundancy increases. The horizontal line denotes the nominal search size
K = 500.


    The structural mechanism driving the divergence between raw predictor redundancy and resultant
signal diversity is defined here as spurious orthogonality. As demonstrated in Figure 6, the
application of non-linear filtering mechanisms induces two distinct decorrelation dynamics. First,
converting continuous predictions to binary states via sign extraction alters the correlation structure
independently of sparsity. Second, and more critically, stringent thresholding induces sparsity
within the signal vectors. This sparsity systematically decorrelates the resulting signal matrix.
Consequently, the effective multiplicity (Keff ) of the thresholded signals is substantially amplified
relative to the highly correlated raw predictions (Panel A and Panel B). Panel C shows that
thresholding is associated with an upward shift in the optimized in-sample extremum: in the ρ = 0.9
regime plotted, both the mean of max|ZIS    ⋆ | and its upper quantiles (as summarized by the 5th–95th

percentile band) increase relative to the unthresholded baseline as K grows, consistent with the
higher Kceff induced by non-linear signal extraction; the panel is descriptive of in-sample optimization
and does not by itself establish any corresponding walk-forward improvement. Panel D shows that
sparsity is a dominant predictor of amplification within the fixed-threshold family at K = 100 and
ρ = 0.9: the amplification factor Kceff (Signal)/Kceff (Pred) increases as the fraction of non-zero signal
entries falls, while remaining above one even when the fraction non-zero is near one, reflecting
a discretization effect from mapping continuous scores to dense sign signals (e.g., thr = 0) that
operates even in the absence of sparsity.
    Although the raw predictions remain nearly one-dimensional in this regime, thresholding materi-
ally increases the effective dimensionality of the realized signals by reducing tail co-movement. At
K = 1,000 and ρ = 0.9, K  ceff (Pred) remains fixed at 1.24 across specifications, whereas K  ceff (Signal)
rises from 1.24 under no thresholding to values between 1.69 and 3.34 under thresholded rules. The
corresponding mean optimized in-sample extremum rises from 1.82 to values between 2.27 and
2.66. The strongest amplification in the reported grid occurs under the fixed-threshold specification
thr = 2.0, with an amplification factor of 2.68, followed closely by adaptive thresholding at q = 0.95,


                                                                 16
                                        3.0
          Expected In-Sample Max |Z|

                                        2.5




                                        2.0




                                        1.5




                                        1.0



                                                        1                                                                              10                                                                             100
                                                                                                                                       Effective Multiplicity ( Keff)


                                                                                                                     Intra-Cluster ρ                              0.6                    0.8                 0.99



Figure 4: Validation of Redundancy Law under imperfect correlation. Observed in-sample winner
magnitudes track the theoretical prediction based on K       ceff across correlation regimes. Lower
correlation increases effective multiplicity and inflates the winner statistic.



                                             Saturation vs inflation in ML workflows (Boosting; White Noise)                                                           Backtest inflation factor by workflow (Boosting; requested K=400)
                                             Correlated tuning saturates; independent mining inflates with K                                                           BIF summarizes in-sample vs walk-forward divergence under White Noise




                                        3
              Mean |ZIS |
          *




                                        2                                                                                                                        7.5




                                        1


                                                 1                         5            10           25         50            100              200   400
                                                                               Nominal search size (requested K)

                                                                                                                                                                 5.0
                                                                                                                                                           BIF




                                                                  Inflation (Independent)    Robustness Check        Saturation (Correlated)


                                             Effective multiplicity evolution (Boosting; White Noise)
                                             Keff grows linearly for independent mining; saturates for correlated tuning




                                       100
                                                                                                                                                                 2.5
          Mean Keff




                                       10




                                        1
                                                 1                         5            10           25         50            100              200   400                             g                           g
                                                                                                                                                                                 inin                         nin                   ing
                                                                                                                                                                              reM                          rTu                 llow
                                                                                                                                                                           atu                          ete                  Fo
                                                                                                                                                                                                                           nd
                                                                                                                                                                         Fe                          ram                Tre
                                                                                                                                                                                                  rpa
                                                                                                                                                                                                pe
                                                                                                                                                                                           Hy
                                                                                       Nominal K (requested)                                                                                               Workflow

                                                                  Inflation (Independent)    Robustness Check        Saturation (Correlated)




Figure 5: Saturation versus inflation in machine learning workflows under a global null. The left
panels summarize in-sample extremeness and the evolution of K ceff with nominal K under White
Noise. The right panel summarizes the distribution of BIF at K = 400 under White Noise; the
dashed horizontal line marks the neutral benchmark BIF = 1.



                                                                                                                                                       17
           The Boosting Paradox: Non-Linearity Amplifies Effective Multiplicity
                                              Panel A: The Multiplicity Gap                                                                                                                   Panel B: Amplification Factor
                                              Prediction Keff saturates vs. Signal Keff grows                                                                                                 Ratio: Signal Keff / Prediction Keff

                                                             Correlation (rho) = 0.6                                       Correlation (rho) = 0.9                                                                   ρ = 0.6                                                  ρ = 0.9
                                                                                                                                                                                          8
                                         10
           Effective Multiplicity Keff




                                                                                                                                                              Amplification Multipliers
                                                                                                                                                                                          6




                                                                                                                                                                                          4




                                                                                                                                                                                          2

                                          1
                                               1              10               100              1000     1                     10            100       1000                                    1               10              100            1000     1            10                     100       1000
                                                                                                Nominal K                                                                                                                                     Nominal K

                                                                                     Stage       Prediction           Signal                                                                                                     q=0.5      q=0.8          q=0.95   thr=0.5             thr=1.5
                                                                                                                                                                                                              Threshold
                                                                                                                                                                                                                                 q=0.7      q=0.9          thr=0    thr=1               thr=2


                                              Panel C: Resulting In-Sample Bias                                                                                                               Panel D: Mechanism (Sparsity)
                                              Higher Keff yields systematically inflated ZIS                                                                                                  Sparsity fraction regressed on Amplification Factor

                                                                                                   ρ = 0.9


                                                                                                                                                                                          5

                                          3




                                                                                                                                                              Amplification Factor
                                                                                                                                                                                          4
           Max | ZIS |




                                          2

                                                                                                                                                                                          3


                                          1
                                                                                                                                                                                          2



                                          0
                                                   1                               10                                    100                         1000                                     0.00                     0.25                     0.50                     0.75                      1.00
                                                                                                Nominal K                                                                                                                            Sparsity (Fraction Non-Zero)

                                                                               Type          adaptive         fixed       none




Figure 6: Threshold amplification and spurious orthogonality. Panel A: Effective multiplicity (Keff )
of raw predictions and realized thresholded signals versus nominal K for ρ ∈ {0.6, 0.9}. Panel B:
Amplification factor Keff (Signal)/Keff (Pred) across threshold stringencies for ρ ∈ {0.6, 0.9}. Panel
                                        ⋆ = max |Z
C: Optimized in-sample extremum ZIS              k   IS,k | (mean with 5th–95th percentile band) at
ρ = 0.9. Panel D: Amplification versus signal sparsity (fraction non-zero) for fixed thresholds at
K = 100, ρ = 0.9, showing amplification even when dense.




Table 6: Threshold amplification at K = 1,000 (N = 1,000). Kceff (Pred) is computed on raw scores;
K
ceff (Signal) is computed on realized trading signals. Amp. Factor is K
                                                                      ceff (Signal)/K
                                                                                    ceff (Pred).


       Threshold Type                                                                  Level                             K
                                                                                                                         ceff (Pred)                          K
                                                                                                                                                              ceff (Signal)                                                           Amp. Factor                                              ⋆ |
                                                                                                                                                                                                                                                                                        Mean |ZIS
       None                                                                            –                                            1.24                                                             1.24                                           1.00                                          1.82
       Fixed                                                                           thr=1.0                                      1.24                                                             1.91                                           1.54                                          2.42
       Fixed                                                                           thr=2.0                                      1.24                                                             3.34                                           2.68                                          2.63
       Adaptive                                                                        q=0.50                                       1.24                                                             1.69                                           1.36                                          2.27
       Adaptive                                                                        q=0.90                                       1.24                                                             2.60                                           2.09                                          2.62
       Adaptive                                                                        q=0.95                                       1.24                                                             3.20                                           2.57                                          2.66




                                                                                                                                                        18
with an amplification factor of 2.57; adaptive thresholding at q = 0.90 remains substantial, with an
amplification factor of 2.09, but is not the maximal case. The mechanism is therefore broader than
adaptive thresholding alone: both discretization and sparsity can transform a highly redundant
prediction manifold into a materially less redundant signal family, thereby inflating optimized in-
sample evidence without producing corresponding walk-forward gains. Full uncertainty summaries
for the threshold-amplification sweep are provided in Appendix C.

5.5   The Linear Control: Regularization-Induced Redundancy
To test whether the saturation pattern under correlated tuning is specific to non-linear learners,
we replicate the null-workflow audit with a regularized linear model (Elastic Net via glmnet). The
tuning workflow searches over α ∈ {0, 0.5, 1} and a dense regularization path in λ, subsampled to a
nominal budget of K configurations. Table 7 reports the effective multiplicity trajectory under the
White Noise null.

Table 7: Effective multiplicity under White Noise (Elastic Net). Mean K
                                                                      ceff across workflows and
nominal search size K.

      Workflow                  K=1    K=5     K=10      K=25      K=50     K=100       K=200       K=400
      Elastic Net Tuning         1      1.91   2.00      1.83       1.74      1.72        1.70       1.73
      FeatureMining              1      5.00   10.00     25.00     50.00     100.00      200.00     400.00
      TrendFollowing             1      1.81    2.52      3.85      4.76      5.38        5.65       5.86

    Correlated regularization-path tuning exhibits substantial redundancy, with the effective search
space compressed far below the nominal grid size. By K = 400, Elastic Net Tuning stabilizes
at Kceff = 1.73, indicating that hundreds of nominal evaluations compress to fewer than two
effectively independent trials. Redundancy limits, but does not eliminate, selection inflation. Table 8
summarizes cross-workflow outcomes at K = 400 and shows that walk-forward evidence remains
null-like while in-sample optimization remains materially inflated.

Table 8: Cross-workflow summary at K = 400 (White Noise, N = 1,000). Results correspond to the
glmnet-based linear-control experiment. Reported values are Monte Carlo means, except BIFstab
                                                                                          0.5 ,
                                          ⋆ | ≥ 0.5}.
which reports the median on the subset {|ZWF

 Workflow              K
                       ceff             ⋆ |
                                 Mean |ZIS            ⋆ |
                                               Mean |ZWF    Mean ∆Z        BIFstab
                                                                              0.5     Fail IS (%)   Fail WF (%)
 FeatureMining        400.000        3.211       0.837           2.374      2.911       100.0           6.6
 Elastic Net Tuning    1.727         1.817       0.808           1.009      1.668       35.8            5.4
 TrendFollowing        5.859         2.188       0.781           1.407      2.117        64.2           5.0


    Confidence intervals for these estimates, reported in Appendix Table C.17, confirm the precision
of the point estimates and the robustness of the saturation pattern.
    The implication is structural: the multiplicity penalty is governed by the effective number of
independent trials rather than the nominal grid size. Correlated tuning families compress the search
volume and cap K  ceff , whereas orthogonal searches preserve Kceff ≈ K and mechanically amplify
optimized in-sample evidence under the null. The full K-sweep demonstrating saturation of K     ceff
and the corresponding plateau in in-sample extremeness is provided in Appendix C.




                                                       19
5.6    Positive Control: The Detection Frontier
A falsification framework must reject workflows under the global null while retaining power when
predictability is real but weak. We therefore introduce a positive control that maps the detection
frontier of the audit as a function of signal strength and event scarcity.
    We simulate a threshold autoregressive process designed to capture the dynamics targeted by
breakout and trend-following rules:

                              rt = ϕrt−1 I(|rt−1 | > θσ) + ϵt ,    ϵt ∼ N (0, σ 2 ),                (11)

where ϕ governs autocorrelation during active regimes and θ governs activation rarity (in standard
deviations). Annualized volatility is fixed at σann = 15%, and the DGP is strictly causal, embedding
genuine predictability when ϕ ̸= 0.
   We vary ϕ ∈ {0.05, 0.10, 0.15, 0.20, 0.25} and θ ∈ {1.0, 1.5, 2.0, 2.5, 3.0} over N = 1,000 Monte
Carlo replications per cell with T = 2,520 trading days and a 60/40 in-sample/walk-forward split.
The adaptive workflow selects the breakout threshold k ⋆ from {0.5, 0.7, . . . , 3.5} by maximizing the
absolute in-sample t-statistic, subject to a minimum of 10 trades in-sample. Walk-forward inference
uses HAC standard errors, and a strategy is classified as detected if |ZWF | > 1.96.
   Table 9 reports detection rates across the grid, and Figure 7 visualizes the detection surface.

Table 9: Detection limits: Pass rate (%) of the falsification audit across signal strength (ϕ) and
activation threshold (θ). Values are based on N = 1,000 simulations per cell with HAC-adjusted
walk-forward inference.

                                    Activation threshold θ (standard deviations)
                       Signal ϕ
                                     1.0      1.5    2.0     2.5             3.0
                       0.05         16.2     12.3    7.1    4.4              4.8
                       0.10         64.0     43.6   20.6     7.5             5.6
                       0.15         96.3     81.1   46.6    12.9             5.4
                       0.20         100.0    96.2   68.8    20.0             5.6
                       0.25         100.0    99.6   84.9    32.0             6.5

     Detectability increases primarily with ϕ and declines with θ through a mechanically smaller
effective sample size in the walk-forward window. For moderate-to-strong signals combined with
non-scarce activation, the audit exhibits high power. However, the simulation demonstrates a severe
power collapse under sparse signal regimes. Specifically, for weak and rare activation parameters
(ϕ = 0.05, θ = 3.0), the detection rate falls to 4.8%, operating strictly at or below the nominal 5% size
of the test. This confirms that the falsification framework possesses effectively zero statistical power
to detect highly sparse, intermittent causal structures. The diagnostic architecture structurally
prioritizes strict Type I error control (rejecting spurious pipelines) over Type II error minimization.
Researchers must concede that while the audit reliably flags structural artifacts, it will systematically
fail to validate genuine predictability if the underlying economic mechanism activates too infrequently
within the walk-forward sample.
     Relative to the global-null simulations in Section 5.1, the positive control confirms asymmetric
diagnostic behavior: under the null, BIF rises systematically with search size because optimized
in-sample extremeness grows while walk-forward evidence remains null-like; under detectable
alternatives, inflation diagnostics remain materially closer to unity because out-of-sample evidence
rises with genuine structure. This establishes that the audit is not a universal rejection device and

                                                      20
                                          Audit Sensitivity Surface
                                          Pass Rate (%) at 95% Confidence ( ZWF > 1.96)



                                   0.25          100            100             85             32    6




                                    0.2          100             96             69             20    6
           Signal Strength (Phi)




                                                                                                         Pass Rate
                                                                                                            100

                                                                                                            75
                                   0.15           96             81             47             13    5
                                                                                                            50

                                                                                                            25

                                                                                                            0
                                    0.1           64             44             21             8     6




                                   0.05           16             12             7              4     5




                                                  1             1.5             2              2.5   3
                                                                DGP Activation Threshold (Z-score)


Figure 7: Detection frontier of the falsification audit. The heatmap shows pass rates (% of simulations
with |ZWF | > 1.96) across the parameter space.


that its stringency concentrates on spurious predictability rather than suppressing real, causally
valid signal.

5.7   Summary of Simulation Evidence
The simulations
       √          support the framework on five dimensions. Optimized in-sample winners grow on
the Θ( log Keff ) scale under the null, while disjoint walk-forward winners remain null-like. Effective
multiplicity K
             ceff provides an operational proxy for search dimensionality under clustered dependence
and aligns observed inflation with extreme-value predictions. The falsification environments separate
leakage and microstructure exploitation from workflows that are merely selection-inflated, while
remaining near-nominal when the null is correctly specified. Correlated search families can exhibit
severe redundancy in K ceff and still generate material selection inflation, with non-linear workflows
particularly susceptible through threshold amplification that increases effective dimensionality during
signal extraction. Finally, the positive control establishes that the audit’s stringency is correctly
targeted: it successfully filters out spurious selection bias without destroying statistical power for
detecting genuine, causally valid economic signals.


6     Empirical Applications: Case Studies
This section applies the two-stage audit protocol of Section 4 to market data to illustrate empirically
relevant failure modes. Stage 1 runs each end-to-end pipeline on the induced-null environments and
records pass/fail using the calibrated thresholds in Section 4.4. Specifications that survive are then
evaluated in Stage 2 on the historical sample under a strict disjoint in-sample/walk-forward design,

                                                                                     21
Table 10: Mechanism Diagnosis (SPY). Activity increases in high volatility as score dispersion
pushes mass away from the decision boundary.

           Metric                                           Calm                High Vol
           Trigger Rate (Activity)                         69.4%                 88.7%
           Boundary Mass (Pr |st − smed | − δ ≤ ε )         0.174                 0.066
           Note: δ and smed calibrated on training data; regime cutoff is the training 80th percentile
           of lagged volatility; ε = 0.01. Alpha vs Buy&Hold: 0.39% (p = 0.931). Returns are gross of
           transaction costs.


with all adaptive selection confined to the in-sample block. We report the resulting in-sample and
walk-forward statistics, the effective multiplicity estimate, the stabilized inflation diagnostics, and
the null-calibrated inflation class. The objective is diagnostic rather than competitive: to determine
whether apparent performance is consistent with robustness to structural nulls, coherent attribution
after controlling for systematic exposures, and strictly time-respecting evaluation.
    These case studies are demonstrations aligned with specific channels targeted by the audit
rather than an estimate of the population prevalence of spurious findings. Evidence on power
and false-positive control is therefore deferred to the simulation section, which maps the detection
frontier under controlled alternatives and null environments.

6.1   Mechanism Diagnosis: Deep Learning on SPY
When evaluated on SPY (S&P 500 ETF proxy) under strict temporal segregation with an internal
pre-2016 validation split and without class rebalancing, the deep learning pipeline exhibits no
out-of-sample evidence of directional predictability. On the post-2015 test window, the annualized
alpha relative to buy-and-hold is 0.39% with p = 0.931, implying that any apparent in-sample edge
does not survive a clean holdout evaluation.
    The dominant empirical pattern is threshold-induced activity clustering. Using decision thresh-
olds calibrated exclusively on the training sample, the position trigger rate increases from 69.4%
in low-volatility states to 88.7% in high-volatility states (Table 10), while the out-of-sample score
distribution exhibits a material reduction in probability mass in a neighborhood of the decision
boundary. Let st denote the model score and let smed be the training-sample median score used
to anchor the symmetric threshold rule with margin δ; the corresponding boundary-mass statistic
Pr! |st − smed | − δ ≤ ε declines across volatility regimes, consistent with high-variance periods
reallocating probability mass away from the decision margin and mechanically increasing trade
activation.
    This reduction indicates that high-volatility periods reallocate probability mass away from
the decision margin and into regions beyond the fixed thresholds, mechanically increasing trade
activation.
    A Monte Carlo falsification on a zero-mean GARCH(1,1) null confirms that this mechanism does
not require any conditional-mean structure. Across N = 30 independent null paths, the identical
pipeline reproduces regime-dependent activity, with a mean calm-regime trigger rate of 68.9% and a
mean high-volatility trigger rate of 79.1% (Table 11).
    In contrast, null performance remains centered near zero (mean annualized alpha −0.17%; mean
gross Z = −0.014), while the empirical distribution exhibits a non-negligible right tail (Figure 8,
Panel B).
    Taken together, the evidence supports a strictly mechanical interpretation: the workflow functions
primarily as a nonlinear volatility-responsive activation rule. Heteroskedastic feature realizations

                                                       22
Table 11: GARCH(1,1) Falsification (Monte Carlo). Mean statistics across N = 30 independent
generator paths.

                                                                     Metric                                            Mean Value
                                                                     Mean Gross Z (Model)                                   -0.014
                                                                     Mean Alpha vs B&H (Ann)                                -0.17%
                                                                     Mean Trigger Rate (Calm)                                68.9%
                                                                     Mean Trigger Rate (High Vol)                            79.1%




                                            Panel A: Deep Learning vs. Buy-and-Hold (SPY)
                                            Alpha vs Buy-and-Hold: 0.38% (p=0.932)
                                      2.5




                                      2.0
          Cumulative Return (Gross)




                                      1.5




                                      1.0




                                      0.5




                                      0.0


                                               2016                    2018            2020                     2022                             2024                              2026


                                                                                           Deep Learning   Buy-and-Hold


                                            Panel B: Distribution of Out-of-Sample Alpha on GARCH Null
                                            Mean Alpha = -0.17% | 30 Paths

                                       5




                                       4




                                       3
          Frequency




                                       2




                                       1




                                       0

                                               -10                     -5              0                           5                              10                                 15
                                                                                            Annualized Alpha (%)
                                                                                                             Results reflect strictly out-of-sample data. Evaluated gross of transaction costs.




Figure 8: Empirical vs. Falsification Performance. Panel A shows the cumulative return of the
deep learning model versus buy-and-hold on the SPY out-of-sample data. Panel B displays the
distribution of annualized alpha generated by the identical pipeline on zero-mean GARCH(1,1) null
paths.




                                                                                                  23
widen the score distribution relative to fixed thresholds calibrated in calmer training conditions,
raising turnover without generating a robust directional signal. Because results are reported gross
of transaction costs, the economic impact of this structural failure is understated.

6.2   Cross-Sectional Machine Learning and the Beta Confound
Cross-sectional machine learning pipelines can generate apparently predictive returns by recon-
structing static exposure to priced risk premia rather than producing abnormal performance. This
beta confound is diagnosed when gross long–short performance is statistically significant but the
factor-adjusted intercept is indistinguishable from zero.
    To evaluate this failure channel, we apply an expanding-window ridge regression (λ = 0.01) to
the Fama–French 25 Portfolios sorted by Size and Book-to-Market. Each month, the model produces
out-of-sample expected returns which are used to construct an extremal long–short portfolio that
goes long the top three and short the bottom three portfolios. Following strict data integrity
protocols, Fama–French sentinel missing values (−99.99) are scrubbed prior to estimation to avoid
injecting artificial outliers into the ridge coefficients.
    The audit applies a Newey–West HAC intercept test in the FF3 regression to separate systematic
exposure from residual performance. As documented in Table 12, the gross long–short strategy
yields a statistically significant Bartlett-HAC Z-score of 3.153 (p = 0.002). In this sample, the
beta-confound pattern does not obtain: when subjected to the FF3 audit regression, the strategy
retains an economically and statistically significant intercept (Zα = 2.708, p = 0.007). Accordingly,
the performance is not mechanically attributable to standard market, size, and value exposures,
and the systematic-risk replication diagnostic does not trigger.
    The tau-floored Backtest Inflation Factor, BIF = |Zgross |/ max(|Zα |, τ ) with τ = 0.5, evaluates to
1.16. This tight diagnostic spread indicates limited attenuation when moving from gross performance
to factor-neutral performance under FF3. Figure 9 provides a visual diagnostic: the factor-neutral
series closely tracks the gross series over the full out-of-sample window.

Table 12: Cross-sectional systematic-risk replication diagnostics. Ridge regression on FF25
out-of-sample performance (1991–2025).

                                     Metric                    Value
                                     Gross Z-Score             3.153
                                     Gross p-value             0.002
                                     Alpha Z-Score (FF3)       2.708
                                     Alpha p-value (FF3)       0.007
                                     BIF (Gross / Alpha)        1.16
                                     OOS Months                 419
                    Note: Alpha statistics computed via Newey-West HAC standard errors.



6.3   Validation Inflation in Volatility Forecasting
Financial time series exhibiting strong serial dependence, such as realized volatility, can be vulnerable
to validation inflation when evaluated using machine learning protocols that ignore temporal ordering.
In principle, random k-fold cross-validation may mix contiguous, highly correlated observations
across training and validation partitions, allowing the model-selection process to exploit local regime
persistence. Whether this distortion is material, however, is ultimately an empirical question.


                                                    24
                                                   Application 2: Factor-Neutral Falsification
                                                   Gross and factor-neutral wealth track closely; the low BIF indicates limited attenuation after FF3 adjustment.



           Cumulative Wealth (Compounded)   750%




                                            500%




                                            250%




                                             0%

                                                   1990                        2000                            2010                         2020




                                                                                         Long-Short Strategy      Three-Factor Alpha




Figure 9: Cross-sectional ridge regression performance. Cumulative wealth of the out-of-sample
long–short strategy that goes long the top three and short the bottom three FF25 portfolios each
month (1991–2025). The dashed line plots the factor-neutral return series obtained by subtracting
the fitted FF3 factor component from the strategy return. The limited divergence between the two
series is consistent with the low Backtest Inflation Factor (BIF = 1.16).


    To assess this issue, we evaluate a daily volatility forecasting task on SPY (log realized volatility).
The feature set includes standard Heterogeneous Autoregressive (HAR) lags (daily, weekly, and
monthly) alongside 20 days of lagged returns. We contrast three specifications: a baseline linear
HAR model, a Lasso regression utilizing standard random k-fold cross-validation, and a strictly
causal expanding-window walk-forward Lasso. To eliminate temporal leakage during walk-forward
refits, internal hyperparameter tuning (λ) is restricted to chronological block cross-validation.
    As documented in Table 13, the baseline HAR model establishes a genuine predictive signal,
achieving an out-of-sample R2 of 23.8% (0.238).

Table 13: Volatility prediction performance. HAR and Walk-Forward metrics reflect true chronolog-
ical holdout performance. The Random CV metrics reflect the internal cross-validated estimate,
allowing comparison between time-inappropriate and time-respecting validation.

                                                             Model                                                    OOS R2           RMSE
                                                             HAR (Baseline)                                            0.238           0.000584
                                                             Lasso + Random CV                                         0.212           0.000446
                                                             Lasso + Walk-Forward (refit=5d)                           0.211           0.000594

    Table 14 summarizes the comparison. The ratio-based diagnostic is now informative, and it
indicates near-equivalence rather than inflation: VIR = 1.006 and ∆R2 = RRandomCV
                                                                           2        −RWF2  = 0.001.
In other words, the random-fold and walk-forward evaluations deliver almost the same estimated
performance for the Lasso specification in this sample.
    The substantive conclusion is therefore different from a volatility-trap narrative. The higher-


                                                                                                    25
                                                               2
Table 14: Validation inflation diagnostics. VIR is defined as RRandomCV   2 . ∆R2 is the absolute
                                                                        /RWF
divergence between the internal estimate and the chronological realization.

                            Metric                                   Value
                            Validation Inflation Ratio (VIR)         1.006
                            Delta R2 (RandomCV - Walk-Forward)       0.001


dimensional Lasso model does not materially outperform under random cross-validation, nor does
it materially deteriorate under strict chronological evaluation; instead, both validation schemes
yield nearly identical results, while the simpler HAR benchmark remains modestly stronger. The
broader methodological lesson remains that temporal causality should be respected in tuning and
evaluation for serially dependent targets, but the empirical magnitude of validation inflation must
be established case by case rather than presumed.

6.4   Unified Interpretation Across Applications
Across the applications, apparent predictive success is shown to be compatible with multiple non-
signal channels that become empirically distinguishable only when the full workflow is treated as
the object under test. The case studies span threshold–volatility interactions that inflate activity
without robust directional content, cross-sectional performance driven by systematic risk replication
versus factor-neutral intercepts, and validation inflation from time-inappropriate fold construction
under volatility clustering.
    These cases motivate a unified auditing discipline. Each pipeline is first subjected to end-to-end
falsification under economically structured null environments, then decomposed via factor attribution,
and finally evaluated under strictly chronological out-of-sample partitions. The simulation positive
control in Section 5.6 confirms that these gates do not sterilize genuine structure: when causal
predictability is present, nontrivial walk-forward power remains detectable.


7     Implications for Research and Practice
The falsification audit framework has direct implications for three stakeholder groups in the financial
machine learning ecosystem: practitioners, academic researchers, and supervisors/policymakers. The
unifying message is practical: in weak-signal, temporally ordered data, reported performance is not
credible unless it survives (i) temporally causal validation, (ii) falsification under structured nulls,
and (iii) explicit adjustment for adaptive specification search. These requirements operationalize
long-standing concerns about data mining and non-replication in empirical finance (Harvey et al.,
2016; Hou et al., 2020) and align with placebo-based falsification principles in econometrics (Imbens
and Rubin, 2015).

7.1   Implications for Practitioners
For asset managers and quantitative research teams, the falsification audit is best treated as a
pre-deployment gate that sits between research backtesting and any form of capital allocation. The
objective is not to suppress exploration, but to prevent investment in strategies whose apparent edge
is mechanically produced by validation artifacts, adaptive selection, or microstructure sensitivity
rather than stable conditional mean structure. In weak-signal, temporally ordered data, the baseline



                                                  26
evidentiary standard is procedural: a claim is not credible unless the entire end-to-end pipeline
respects causal information flow and remains null-like under structured induced-null environments.
    Operationally, strict walk-forward evaluation should be enforced as a workflow invariant, not
as a final reporting choice. Random cross-validation breaks time ordering and can import future
regimes through repeated re-use of observations, which can inflate apparent predictive performance
even when the model class is well-specified; this risk applies to preprocessing, feature construction,
hyperparameter tuning, and model selection, not only to the final fit (Bergmeir et al., 2018).
The audit then provides a direct robustness stress test: running the unchanged pipeline across
martingale-difference reference classes and targeted placebos identifies whether performance survives
when economic predictability is removed by design, thereby diagnosing leakage, timing misalignment,
and protocol-driven uplift.
    Finally, adaptive search should be priced explicitly as model risk. Because selection-induced
inflation is intrinsic to modern ML workflows, practitioners should record inflation diagnostics
alongside headline performance, using the absolute magnitude gap ∆Z as the primary, well-defined
measure and the stabilized BIF together with K  ceff as an internal ranking and governance summary.
This produces a defensible research record in which backtest strength, falsification outcomes, and
search-induced inflation are jointly visible, enabling deployment decisions to be made on realized
evidence rather than optimized in-sample extremeness.


8    Conclusion
This paper formalizes a falsification framework to diagnose spurious predictability in financial
machine learning pipelines. By evaluating complete predictive workflows against synthetic ref-
erence classes—including strict martingale-difference environments and targeted microstructure
placebos—the audit systematically filters out performance driven by data leakage, indexing errors,
and selection bias.
    For workflows that survive the falsification gates, the framework quantifies the multiplicity
penalty using the absolute magnitude gap (∆Z). Because disjoint walk-forward evaluation remains
bounded in probability under the null, ∆Z provides a mathematically continuous, unconfounded
measurement of selection-induced decay. Crucially, we restrict the interpretation of the ratio-based
Backtest Inflation Factor (BIFstab
                                 τ  ) to a bounded statistical heuristic, explicitly acknowledging that
it cannot serve as a strictly linear economic adjustment when out-of-sample evidence collapses
toward zero.
    The empirical applications demonstrate the audit in action by separating mechanical success
from genuine structure across representative failure modes.
    While this framework establishes rigorous bounds for extreme-value bias under clustered search
geometries, significant extensions remain. Currently, the inflation metrics operate as descriptive
statistics evaluated against simulated null thresholds. Future research must formalize the statistical
inference surrounding these measurements. Developing a robust hypothesis testing framework—such
as a pipeline-specific bootstrap test for the magnitude gap—will transition the quantification of
backtest decay from a descriptive diagnostic into a formal inferential standard. Ultimately, shifting
the burden of proof from historical backtest performance to algorithmic robustness against strictly
defined nulls is essential for the maturation of financial machine learning.




                                                  27
References
S. Athey. The impact of machine learning on economics. In The Economics of Artificial Intelligence:
An Agenda, pages 507–547. University of Chicago Press, 2019.

D. H. Bailey and M. López de Prado. The deflated sharpe ratio: Correcting for selection bias,
backtest overfitting, and non-normality. The Journal of Portfolio Management, 40(5):94–107, 2014.

A. Belloni, V. Chernozhukov, and C. Hansen. Inference on treatment effects after selection among
high-dimensional controls. The Review of Economic Studies, 81(2):608–650, 2014.

C. Bergmeir, R. J. Hyndman, and B. Koo. A note on the validity of cross-validation for evaluating
autoregressive time series prediction. Computational Statistics & Data Analysis, 120:70–83, 2018.

J. L. Campbell, H. Ham, Z. Lu, and K. Wood. Expectations matter: When (not) to use machine
learning earnings forecasts. SSRN Electronic Journal, 2024. URL https://papers.ssrn.com/
sol3/papers.cfm?abstract_id=4495297. Working Paper.

J. Y. Campbell, A. W. Lo, and A. C. MacKinlay. The Econometrics of Financial Markets. Princeton
University Press, 1997.

M. M. Carhart. On persistence in mutual fund performance. The Journal of Finance, 52(1):57–82,
1997.

R. Cont. Empirical properties of asset returns: stylized facts and statistical issues. Quantitative
Finance, 1(2):223–236, 2001.

F. X. Diebold. Comparing predictive accuracy, twenty years later: A personal perspective on the
use and abuse of diebold-mariano tests. Journal of Business & Economic Statistics, 33(1):1–1, 2015.
doi: 10.1080/07350015.2014.983236.

R. F. Engle. Autoregressive conditional heteroscedasticity with estimates of the variance of united
kingdom inflation. Econometrica, 50(4):987–1007, 1982.

E. F. Fama and K. R. French. Common risk factors in the returns on stocks and bonds. Journal of
Financial Economics, 33(1):3–56, 1993. doi: 10.1016/0304-405X(93)90023-5.

E. Giné and R. Nickl. Mathematical Foundations of Infinite-Dimensional Statistical Models. Cam-
bridge Series in Statistical and Probabilistic Mathematics. Cambridge University Press, Cambridge,
2016.

S. Gu, B. Kelly, and D. Xiu. Empirical asset pricing via machine learning. The Review of Financial
Studies, 33(5):2223–2273, 2020.

P. R. Hansen. A test for superior predictive ability. Journal of Business & Economic Statistics, 23
(4):365–380, 2005.

C. R. Harvey, Y. Liu, and H. Zhu. ...and the cross-section of expected returns. The Review of
Financial Studies, 29(1):5–68, 2016.

K. Hou, C. Xue, and L. Zhang. Replicating anomalies. The Review of Financial Studies, 33(5):
2019–2133, 2020. doi: 10.1093/rfs/hhy131.



                                                28
G. W. Imbens and D. B. Rubin. Causal Inference in Statistics, Social, and Biomedical Sciences.
Cambridge University Press, 2015.

T. I. Jensen, B. Kelly, and L. H. Pedersen. Is there a replication crisis in finance? The Journal of
Finance, 78(5):2465–2518, 2023.

J. D. Lee, D. L. Sun, Y. Sun, and J. E. Taylor. Exact post-selection inference, with application to
the lasso. The Annals of Statistics, 44(3):907–927, 2016.

M. Lopez de Prado. Advances in Financial Machine Learning. John Wiley & Sons, 2018.

B. Mandelbrot. The variation of certain speculative prices. The Journal of Business, 36(4):394–419,
1963.

W. K. Newey and K. D. West. A simple, positive semi-definite, heteroskedasticity and autocorrelation
consistent covariance matrix. Econometrica, 55(3):703–708, 1987.

W. K. Newey and K. D. West. Automatic lag selection in covariance matrix estimation. The Review
of Economic Studies, 61(4):631–653, 1994.

J. Schäfer and K. Strimmer. A shrinkage approach to large-scale covariance matrix estimation and
implications for functional genomics. Statistical Applications in Genetics and Molecular Biology, 4
(1):Article 32, 2005.

X. Shao. The dependent wild bootstrap. Journal of the American Statistical Association, 105(489):
218–235, 2010.

J. H. van Binsbergen, X. Han, and A. Lopez-Lira. Man versus machine learning: The term structure
of earnings expectations and conditional biases. The Review of Financial Studies, 36(6):2361–2396,
2023.

H. R. Varian. Big data: New tricks for econometrics. Journal of Economic Perspectives, 28(2):3–28,
2014.

M. J. Wainwright. High-Dimensional Statistics: A Non-Asymptotic Viewpoint. Cambridge Series in
Statistical and Probabilistic Mathematics. Cambridge University Press, Cambridge, 2019. ISBN
978-1108498029.

H. White. A reality check for data snooping. Econometrica, 68(5):1097–1126, 2000.

Y. Zhang, Y. Zhu, and J. T. Linnainmaa. Man versus machine learning revisited. The Review of
Financial Studies, 38(12):3768–3790, 2025.




                                                29
Appendices

A     Asymptotic Motivation for Selection-Induced Inflation
This appendix provides the asymptotic motivation for the scaling behavior of in-sample maximization
under the global null and outlines the finite-sample variance dynamics of walk-forward performance.
The mathematical derivations herein represent heuristic limiting cases (where the hypothesis space
K is fixed and T → ∞) intended to illustrate the base mechanisms of selection bias. In the
high-dimensional finite-sample environments typical of machine learning (K ≥ T ), the uniform
Gaussian
       √ approximation is not guaranteed, and we do not rely on it. Consequently, the scaling
law Θ( ln Keff ) is empirically validated by the simulation suite in Section 5, rather than by non-
asymptotic mathematical proof. Throughout, K denotes the number of evaluated strategies and T
the time-series length used to construct the studentized statistics.

A.1    Gaussian maximal inequalities and effective multiplicity
Let Z = (Z1 , . . . , ZK ) be a vector of centered, unit-variance statistics. As an asymptotic limit,
assume that as T → ∞,
                                             Z ⇒ N (0, Σ),
for some correlation matrix Σ. Define the canonical metric on the index set {1, . . . , K} by
                                             q                        q
                              d(i, j) =         E(Zi − Zj )2 =            2(1 − Σij ).

Let N (ε) denote the ε-covering number and M (ε) the ε-packing number of {1, . . . , K} under d.
Define the effective multiplicity (stable rank proxy) by

                                                            (tr Σ)2
                                                 Keff =             .
                                                             ∥Σ∥2F

Lemma 2 (Gaussian maxima are governed by metric entropy). There exist universal constants
0 < c < C < ∞ such that for any centered Gaussian vector Z ∼ N (0, Σ) with unit variances,
           h            i         Z diam q                        h              i             q
          E    max Zk       ≤ C              ln N (ε) dε,       E       max Zk       ≥ c sup ε ln M (ε),
               1≤k≤K               0                                  1≤k≤K              ε>0

where diam = maxi,j d(i, j) ≤ 2. The same bounds hold, up to universal constants, with maxk Zk
replaced by maxk |Zk |.

Derivation. The upper bound is Dudley’s entropy integral inequality for Gaussian processes
(Wainwright, 2019). The lower bound follows p    from Sudakov’s minoration theorem for Gaussian
vectors (Giné and Nickl, 2016): for any ε > 0, ε 2 ln M (ε) ≤ 2E[max1≤k≤K Zk ]. For the extension
to maxk |Zk |, consider the Gaussian process indexed by {(k, +), (k, −)} with values Z(k,+) = Zk and
Z(k,−) = −Zk ; applying the same bounds to max Ze yields the desired result, because maxk |Zk | =
max{maxk Zk , maxk (−Zk )}.                                                                        ■

Lemma 3 (Block-redundancy geometry links entropy and Keff ). Let Z ∼ N (0, Σ) with unit
variances. Suppose Σ is block diagonal with m independent clusters of sizes s1 , . . . , sm and within-
block equicorrelation ρ ∈ (0, 1). Let K = m
                                         P
                                           c=1 sc , and smax = maxc sc .




                                                        30
                     norm satisfies ∥Σ∥2F = m         2                               2  m
                                                                     
                                            c=1 sc + ρ sc (sc − 1) , yielding Keff = K /
                                             P                                              P
  (i) The Frobenius                                                                      c=1 sc +
       2
                   
      ρ sc (sc − 1) . In the strong-redundancy limit ρ ↑ 1, Keff → m under balanced clusters
      (sc = K/m).

                               √ d, choosing one representative index per block yields a packing of
 (ii) Under the canonical metric
      size m at separation
                 p         δ =  2. Hence M (δ) ≥ m. Moreover, each block is contained in a ball of
      radius η = 2(1 − ρ) centered at its representative, so N (ε) ≤ m for any ε ≥ η.
                                                                          √            √     
Consequently, by Lemma 2, the bounds are E[maxk≤K |Zk |] ≤ C η ln K + 2 ln m and
                    √ √
E[maxk≤K |Zk |] ≥ c 2 ln m.

Derivation. Part (i) follows
                          √ by direct trace calculation. For part (ii), the
                                                                          √ distance between distinct
block representatives isp 2 due to orthogonal independence, forming a 2-packing. For any index
k in block c, d(k, ic ) = 2(1 − ρ) = η, establishing
                                               √     the covering bound. Applying Dudley’s integral
                                                                                                √
split at η and Sudakov’s minoration at δ = 2 recovers the specified bounds. The term η ln K
captures the potential inflation from within-cluster noise; when η is √ small (i.e., ρ → 1), this term
is dominated, and the expected maximum scales proportionally√      to  ln m. In the balanced-cluster
regime sc ≡ K/m, as ρ → 1, Keff ≍ m, motivating the Θ( log Keff ) expectation.                       ■

A.2    Finite-Sample Walk-Forward Dynamics and Conditional Persistence
The evaluation of the selected walk-forward sequence requires explicit differentiation between
asymptotic limits and finite-sample conditional mechanics.
    Let the in-sample period end at time TIS and the walk-forward period be TWF = {TIS + 1, . . . , T }.
Let k ⋆ = argmaxk |ZIS,k | be the index selected strictly using in-sample data. Define walk-forward
P&L increments by Yt = xt,k⋆ rt .
    If the underlying returns rt represent a strictly independent and identically distributed (i.i.d.)
martingale difference sequence, then conditional on the selection event, Yt trivially inherits the
unconditional moments. As |TWF | → ∞, standard Central Limit Theorem conditions apply, and a
                                                    ⋆   d
HAC variance estimator Vbn converges, yielding ZWF      −
                                                        → N (0, 1).
    However, financial returns systematically violate strict i.i.d. assumptions, frequently exhibiting
volatility clustering (e.g., GARCH dynamics). Under conditional heteroskedasticity, the maximiza-
tion function k ⋆ can interact with finite-sample variance trajectories. The algorithm evaluates
candidate strategies xt,k whose specific market exposures may have aligned with elevated variance
states preceding TIS .
    Consequently, the initial state of the walk-forward sequence YTIS +1 can be conditioned on an
elevated terminal variance realization. Due to the persistence of conditional variance, this state can
carry over into the finite walk-forward period. This post-selection conditioning creates a documented
risk of finite-sample size distortion for standard HAC estimators. While HAC estimators are
asymptotically consistent for unconditional long-run variance, they can understate variance in finite
samples skewed by transient conditional shocks, leading to artificial inflation of the test statistic
  ⋆
ZWF   and degraded Type I error control.
Operational Inference and Robustness. Because finite-sample size distortions can compromise
asymptotic HAC estimators under conditional heteroskedasticity, standard test statistics should
be interpreted with caution. In this paper, our default operational inference relies directly on the
induced-null simulation reference classes (Section 4), which bypass asymptotic approximations by
empirically calibrating the exact finite-sample distribution under the null. For practitioners who
require standalone inference without simulating a full suite of reference environments, we recommend

                                                  31
incorporating a dependent wild bootstrap or block bootstrap (Shao, 2010) as a robustness layer.
                                                                           ⋆
This resampling procedure approximates the finite-sample distribution of ZWF   while preserving
conditional heteroskedasticity and weak dependence, without relying on the potentially distorted
finite-sample moment assumptions of standard asymptotic estimators.


B     Synthetic Reference Environments: Full Specifications
This section provides the complete mathematical specifications and default parameter values for
the five canonical reference environments used in the falsification audit (Section 4). Unless stated
                 (r)
otherwise, let Ft = σ(r1 , . . . , rt ) denote the natural filtration generated by the observed return
                                                                                                   (r)
process. Environments A, B, D, and E are strict martingale-difference nulls with respect to Ft−1 ,
satisfying
                                                      (r)
                                              E[rt | Ft−1 ] = 0,
so that no exploitable conditional mean dynamics are present by construction. Environment C is a
targeted microstructure placebo: it is deliberately constructed so that the observed return process
fails the martingale-difference restriction, serving as a normative disqualifier for workflows that
inadvertently monetize execution, indexing, or alignment artifacts.

B.1    Environment A: White Noise (Pure Selection Bias)
Data generating process.
                                                             i.i.d.
                                   rt = σdaily ϵt ,        ϵt ∼ N (0, 1).
              (r)
Then E[rt | Ft−1 ] = 0 and Cov(rt , rt−ℓ ) = 0 for all ℓ ≥ 1.

Default calibration.      Annualized volatility target σ ann = 0.20, giving
                                                    0.20
                                          σdaily = √       .
                                                      252

Targeted failure mode. Isolates pure selection bias. Under this environment, any statisti-
cally significant performance must arise from adaptive specification search rather than genuine
predictability.

B.2    Environment B: Regime-Switching Volatility (Markov, Zero Mean)
This environment introduces persistent volatility regimes while maintaining a zero conditional mean.
                                                                            (r)
Let st ∈ {1, 2} be an unobserved two-state Markov chain. Even though Ft−1 is informative about
st through volatility clustering, the conditional mean remains zero because the shock has mean zero
and is independent of the past.

Data generating process.         Let st ∈ {1, 2} be a two-state Markov chain with transition matrix
                                                                      !
                                                 p11   1 − p11
                                       P =                     .
                                               1 − p22   p22
Returns are generated as
                                                            i.i.d.
                                     rt = σst ϵt ,     ϵt ∼ N (0, 1),
                                                                          (r)            (r)
with ϵt independent of σ(su , u ≤ t) and hence independent of Ft−1 . Therefore E[rt | Ft−1 ] = 0.

                                                      32
Default calibration. Low-regime annualized volatility σ ann = 0.10, high-regime volatility multi-
plier m = 3.0, regime persistence p11 = p22 = 0.98. Hence
                                        0.10               0.10 m  0.30
                                   σ1 = √     ,       σ2 = √      =√     .
                                          252                 252    252

Targeted failure mode. Detects predictability arising from improper normalization, regime
leakage, or scale-based trading rules that inadvertently exploit volatility regimes.

B.3    Environment C: Friction Placebo (Bid–Ask Bounce / Roll MA(1))
This environment is a targeted microstructure placebo. A latent efficient return satisfies the
martingale-difference restriction, but the observed return process is constructed to exhibit bid–ask
                                                                            (r)
bounce and hence to violate the martingale-difference restriction under Ft−1 .

Data generating process.            Let the latent efficient return be
                                                             i.i.d.
                                       ut = σϵ ϵt ,      ϵt ∼ N (0, 1),
                                      (u)                                          (u)
and define the latent filtration Ft = σ(u1 , . . . , ut ). Then E[ut | Ft−1 ] = 0. Observed returns are
generated as a Roll-style bounce reduced form

                                        rt = ut + θ ut−1 ,            |θ| < 1,

which is an MA(1) in the latent shocks. The martingale-difference restriction fails for the observed
                                      (r)
returns whenever θ ̸= 0 and ut−1 ∈ Ft−1 is predictable in L2 from past observed returns, which
holds for invertible MA(1) processes. A simple, filtration-free diagnostic is the nonzero lag-one
autocovariance:

                 Cov(rt , rt−1 ) = Cov(ut + θut−1 , ut−1 + θut−2 ) = θ Var(ut−1 ) = θ σϵ2 .
                                                                             (r)
If {rt } were a martingale-difference sequence with respect to Ft−1 , then E[rt rt−1 ] = 0 would follow
               (r)
from E[rt | Ft−1 ] = 0; the above autocovariance therefore certifies the intentional violation when
θ ̸= 0.
    Innovations are scaled to match a target annualised volatility σ ann . Let
                                              σ ann                σdaily
                                     σdaily = √     ,        σϵ = √       ,
                                                252                1 + θ2
                    2
so that Var(rt ) = σdaily .

Default calibration.          Annualised volatility target σ ann = 0.20, MA(1) coefficient θ = −0.5.

Targeted failure mode. Targets timing, indexing, alignment, and execution-lag errors that can
spuriously monetize transient microstructure patterns.

B.4    Environment D: Factor Null (One-Factor, Zero Alpha)
This environment contains systematic risk exposure but no abnormal performance by construction.


                                                        33
Data generating process.
                                                  rt = βft + et ,
with
                             i.i.d.                         i.i.d.
                          ft ∼ N (0, σf2 ),               et ∼ N (0, σe2 ),        ft ⊥ et ,
                                (r)                         (r)
and (ft , et ) independent of Ft−1 . Hence E[rt | Ft−1 ] = 0.

Default calibration.      β = 1.0 and daily volatilities
                                            0.20                          0.10
                                       σf = √     ,                  σe = √    .
                                              252                          252

Targeted failure mode. Isolates omitted-risk attribution. Any apparent “alpha” must reflect
systematic exposure being misread as skill rather than genuine abnormal performance.

B.5    Environment E: Volatility Clustering Null (GARCH(1,1), Zero Mean)
This environment produces volatility clustering while preserving a zero conditional mean.

Data generating process.
                                             p                       i.i.d.
                                      rt =     ht z t ,          zt ∼ N (0, 1),
                                                    2
                                         ht = ω + αrt−1 + βht−1 .
                  (r)                                                               (r)
Conditional on Ft−1 , ht is measurable and E[zt ] = 0, hence E[rt | Ft−1 ] = 0.

Default calibration. Set α = 0.10, β√= 0.85 (so α + β = 0.95 < 1). Choose ω to match the
target daily variance. Let σdaily = σ ann / 252 with σ ann = 0.20. Then
                                                              2
                                             ω = (1 − α − β) σdaily .

Targeted failure mode. Stresses risk adjustment and HAC-based inference under conditional
heteroskedasticity.

B.6    Extended Microstructure Environment (Optional Robustness Check)
In addition to the canonical microstructure placebo (Environment C), we retain an optional
martingale-bar stress test for robustness. Synthetic intraday price bars are generated from a driftless
process and aggregated to bar returns. This extended environment is reported separately when used
and does not alter the canonical five-environment falsification suite. Full specifications are available
in the QuantAudit package documentation.


C      Supplementary Simulation Results and Robustness
This appendix provides comprehensive supplementary results for all simulation experiments reported
in Section 5. We report Monte Carlo uncertainty estimates, complete tables for the falsification
diagnostic matrix, detailed evolution of effective multiplicity and in-sample inflation across search
sizes, exhaustive threshold amplification sweeps, and a battery of robustness checks that confirm the
stability and generality of our findings. All results are based on N = 1,000 Monte Carlo replications
per configuration unless otherwise noted.

                                                            34
Table C.15: Monte Carlo uncertainty for the scaling-law experiment. 95% intervals for key simulation
estimates. Winner FWP denotes the familywise false positive probability for the selected winner at
the nominal threshold |Z| > 1.96. BIF Median is computed on the subset {|ZWF  ⋆ | ≥ 0.5}.


 K        n     IS Mean       IS CI        WF Mean      WF CI         Winner FWP (%)          Winner FWP CI     BIF Median     BIF CI
 1      1000     0.81      [0.77, 0.85]       0.77    [0.73, 0.81]             5.3                [3.9, 6.7]       0.65      [0.03, 2.90]
 5      1000     1.58      [1.54, 1.61]       0.78    [0.74, 0.82]            22.3               [19.7, 24.9]      1.50      [0.45, 3.71]
 10     1000     1.90      [1.86, 1.93]       0.81    [0.77, 0.85]            40.2               [37.2, 43.2]      1.80      [0.62, 4.54]
 50     1000     2.52      [2.49, 2.54]       0.82    [0.78, 0.86]            92.3               [90.6, 94.0]      2.36      [1.02, 5.06]
 100    1000     2.79      [2.77, 2.82]       0.82    [0.78, 0.86]            99.9              [99.7, 100.1]      2.60      [1.09, 5.56]
 200    1000     3.00      [2.98, 3.03]       0.81    [0.78, 0.85]           100.0             [100.0, 100.0]      2.88      [1.17, 5.78]
 500    1000     3.28      [3.25, 3.30]       0.83    [0.79, 0.86]           100.0             [100.0, 100.0]      3.18      [1.26, 6.70]
 1000   1000     3.48      [3.46, 3.50]       0.80    [0.76, 0.84]           100.0             [100.0, 100.0]      3.33      [1.38, 6.76]



C.1       Monte Carlo Uncertainty for Scaling and Redundancy Laws
C.1.1         Scaling law uncertainty
Table C.15 reports 95% confidence intervals for the key statistics underlying the scaling-law ex-
periment (Section 5.1). Estimates are precise throughout the range of K, with confidence-interval
widths for mean |ZIS | consistently below 0.04 absolute units. The winner familywise false positive
probability becomes essentially certain for K ≥ 200, as indicated by confidence bounds rounding to
100%.

C.1.2         Redundancy law uncertainty
Table C.16 provides confidence intervals for the redundancy law experiment (Section 5.2). The
effective multiplicity estimator exhibits remarkable precision, with interval widths less than 0.2 even
in the 100-cluster case. In-sample winner statistics are estimated with similarly high precision.

Table C.16: Monte Carlo uncertainty for the redundancy law experiment. For each dependence
regime, we report the point estimate and 95% confidence interval for effective multiplicity K
                                                                                            ceff , the
                                 ⋆                                          ⋆
in-sample winner magnitude |ZIS |, the walk-forward winner magnitude |ZWF |, and the stabilized
Backtest Inflation Factor BIFstab
                              0.5 .

 Regime                    Keff           Keff CI     IS Mean           IS CI        WF Mean       WF CI        BIF Median     BIF CI
 Perfectly Correlated       1.00     [1.00, 1.00]       0.77         [0.74, 0.81]      0.81      [0.77, 0.85]      0.62      [0.02, 2.53]
 5 Clusters                 5.03     [5.01, 5.04]       1.57         [1.54, 1.61]      0.84      [0.81, 0.88]      1.44      [0.48, 4.02]
 10 Clusters               10.09    [10.06, 10.11]      1.90         [1.86, 1.93]      0.79      [0.75, 0.83]      1.79      [0.67, 4.23]
 25 Clusters               25.46    [25.39, 25.52]      2.26         [2.23, 2.29]      0.80      [0.76, 0.84]      2.22      [0.81, 4.98]
 50 Clusters               51.74    [51.60, 51.87]      2.54         [2.52, 2.57]      0.84      [0.80, 0.88]      2.37      [0.99, 5.83]
 100 Clusters             106.66   [106.39, 106.94]     2.78         [2.75, 2.80]      0.82      [0.78, 0.85]      2.69      [1.10, 5.59]
 Independent              500.00   [499.99, 500.00]     3.26         [3.24, 3.29]      0.76      [0.72, 0.79]      3.23      [1.38, 6.35]




C.1.3         Workflow comparison uncertainty at K = 400 (Elastic Net)
To formalize the dispersion of performance metrics under the global null, Table C.17 reports the 95%
Monte Carlo uncertainty intervals for the linear-control experiment under the White Noise null at the
maximum nominal search size (K = 400). The empirical bounds confirm the structural divergence
between independent and correlated search topologies. For the orthogonal FeatureMining workflow,
the effective dimensionality remains strictly at 400, driving the in-sample rejection rate to 100% with
a median BIFstab0.5 of 2.91. Conversely, Elastic Net Tuning induces strong algorithmic shrinkage,


                                                                      35
                                          ceff ≈ 1.73. Its in-sample extremeness is therefore materially
compressing the effective multiplicity to K
attenuated relative to the independent search benchmark, although its in-sample failure rate remains
35.8%. TrendFollowing occupies an intermediate regime, with K      ceff ≈ 5.86 and an in-sample failure
rate of 64.2%. Across all three workflows, the walk-forward failure rates remain near nominal (about
5–7%), confirming that walk-forward validation filters the spurious in-sample alpha.

Table C.17: Monte Carlo uncertainty for the linear-control experiment under White Noise at
K = 400 (N = 1,000 simulations per workflow). For each metric, we report the mean across
simulations (median for BIFstab
                             0.5 ), together with 95% uncertainty intervals. For continuous statistics,
the intervals are the empirical 2.5% and 97.5% quantiles of the simulation distribution. For failure
rates (in percentage), the intervals are approximate 95% Wald intervals for the proportion. The
BIF summaries are computed on the stability subset {|ZWF  ⋆ | ≥ 0.5}.


Workflow              K
                      ceff          K
                                    ceff Lo    K
                                               ceff Hi      ⋆ |
                                                          |ZIS    IS Lo       IS Hi       ⋆ |
                                                                                        |ZWF      WF Lo     WF Hi     Fail IS (%)     FIS Lo    FIS Hi    Fail WF (%)    FWF Lo   FWF Hi   BIFstab
                                                                                                                                                                                              0.5    BIF Lo   BIF Hi
FeatureMining        400.00         400.00     400.00     3.21       2.62      4.03      0.84      0.04      2.41       100.0         100.00    100.00        6.6         5.06     8.14     2.91      1.23     6.24
Elastic Net Tuning    1.73           1.39       1.99      1.82       0.90      3.28      0.81      0.04      2.32        35.8         32.83      38.77        5.4         4.00     6.80     1.67      0.54     4.28
TrendFollowing        5.86           4.10       8.13      2.19       1.44      3.31      0.78      0.02      2.21        64.2          61.23     67.17        5.0         3.65     6.35     2.12      0.82     4.67




C.1.4            Workflow comparison uncertainty
Table C.18 reports 95% confidence intervals for the key statistics of the capacity-driven inflation ex-
periment under White Noise at K = 400 (Section 5.3), based on N = 1,000 Monte Carlo replications.
For continuous metrics (K    ceff , |ZIS |, |ZWF |, and BIFstab ), the intervals are empirical quantiles; for
                                                           0.5
failure rates, they are asymptotic Wald intervals. Feature Mining exhibits zero uncertainty in K        ceff
by construction, as the independent strategies guarantee Keff = K. Hyperparameter Tuning and
                                                                    c
Trend Following show moderate sampling variability, with K           ceff intervals spanning approximately
[2.5, 3.5] and [4.1, 8.1], respectively.

Table C.18: Monte Carlo uncertainty for workflow comparison under White Noise at K = 400. 95%
empirical bounds for continuous metrics; asymptotic binomial bounds for failure probabilities.
Workflow                     K
                             ceff      K
                                       ceff Lo    K
                                                  ceff Hi      ⋆ |
                                                             |ZIS      IS Lo     IS Hi      ⋆ |
                                                                                          |ZWF     WF Lo     WF Hi      Fail IS (%)    FIS Lo    FIS Hi    Fail WF (%)   FWF Lo   FWF Hi   BIFstab
                                                                                                                                                                                              0.5    BIF Lo   BIF Hi
FeatureMining           400.00         400.00     400.00     3.21      2.62      4.03      0.84      0.04      2.41       100.0        100.00    100.00        6.6         5.06     8.14     2.91     1.23     6.24
HyperparameterTuning         2.93       2.50       3.50      2.56      1.72      3.80      0.79      0.04      2.21        88.2         86.20     90.20        4.7         3.39     6.01     2.49     0.93     5.52
TrendFollowing               5.86       4.10       8.13      2.19      1.44      3.31      0.78      0.02      2.21        64.2         61.23     67.17        5.0         3.65     6.35     2.12     0.82     4.67




C.2         Complete Falsification Diagnostic Matrix
C.2.1            In-sample failure rates
Table C.19 reports in-sample failure rates (percentage of simulations with |ZIS | > 1.96) for the six
canonical pipelines. Two patterns stand out. First, DataMiner and Lookahead exhibit near-certain
in-sample rejection across all environments. Second, Contrarian remains near the nominal level
in the strict null environments but fails in-sample with certainty in the Microstructure placebo.
Comparison with walk-forward failure rates (Table C.20) distinguishes pure selection bias from
genuine workflow invalidity.

C.2.2            Pipeline classification
Table C.21 provides a rule-based diagnosis of each pipeline based on its walk-forward failure
pattern. The classification now identifies four distinct outcomes: severe methodological error in


                                                                                                                36
Table C.19: In-sample failure rates. Percent of simulations with |ZIS | > 1.96 (diagnostic for selection
bias).

          Pipeline             WhiteNoise     RegimeSwitch      Microstructure   FactorNull
          RandomBaseline             6.0              5.1             4.6            4.9
          DataMiner                 99.3             99.2            99.8           99.5
          Contrarian                 5.6              5.1            100.0           4.9
          Lookahead                 100.0            100.0           100.0          100.0
          RegimeDetector             4.9              4.1             2.0            4.3
          FactorMimic                4.6              3.4             2.8            5.1

Table C.20: Walk-forward failure rates. Percent of simulations with |ZWF | > 1.96 (expected ≈ 5%
under the null).

          Pipeline             WhiteNoise     RegimeSwitch      Microstructure   FactorNull
          RandomBaseline             4.6              4.8             6.9            5.3
          DataMiner                  5.5              5.3             6.3            6.2
          Contrarian                 4.1              5.5            100.0           6.5
          Lookahead                 100.0            100.0           100.0          100.0
          RegimeDetector             5.1              5.0             2.5            3.7
          FactorMimic                4.3              4.5             2.1            5.7


Contrarian, selection bias in DataMiner, universal leakage in Lookahead, and robust operation in
RandomBaseline, RegimeDetector, and FactorMimic.

Table C.21: Pipeline classification. Rule-based diagnosis using environment-specific 95th percentiles
from RandomBaseline as falsification thresholds.

    Pipeline          WF Fail (Mean) IS Fail (Mean) Max |Z| (WF) Diagnosis
    Contrarian              29.23            28.90           10.72     Severe Methodological Error
    DataMiner                5.60            99.45           0.82      Selection Bias (IS-only)
    FactorMimic              3.93             3.98            0.81     Robust (Passes WF)
    Lookahead              100.00           100.00           42.43     Universal Failure (WF)
    RandomBaseline           5.00             5.15            0.82     Robust (Passes WF)
    RegimeDetector           3.85             3.83           0.80      Robust (Passes WF)



C.2.3    Per-cell confidence intervals
Table C.22 reports 95% confidence intervals for walk-forward statistics and failure rates for every
pipeline–environment pair. The intervals confirm the classification logic. DataMiner exhibits near-
null walk-forward failure rates across environments despite extreme in-sample rejection, Contrarian
displays a decisive breakdown in the Microstructure placebo, and Lookahead remains universally
invalid with failure-rate intervals concentrated at 100%. Robust pipelines maintain walk-forward
failure-rate intervals that remain close to the nominal level.




                                                     37
Table C.22: Monte Carlo uncertainty for falsification diagnostics. 95% confidence intervals for walk-
forward and in-sample statistics, walk-forward failure rates, and the stabilized Backtest Inflation
Factor (BIFstab
            0.5 ).

 Pipeline         Environment       Walk-forward |Z|               WF Fail %             In-sample |Z|                BIFstab
                                                                                                                         0.5

                                   Mean    Low     High    Rate      Low    High      Mean    Low     High    Median    Low     High
 Contrarian       FactorNull       0.85     0.81    0.88    6.5     5.10     8.20     0.80     0.76    0.84    0.60     0.03    2.58
 Contrarian       Microstructure   10.72   10.67   10.77   100.0    99.60   100.00    13.09   13.04   13.14    1.22     1.01    1.50
 Contrarian       RegimeSwitch      0.81    0.77    0.85    5.5      4.20    7.10      0.79    0.76    0.83    0.60     0.03    2.82
 Contrarian       WhiteNoise       0.80    0.76    0.83     4.1     3.00     5.50     0.82     0.78   0.86     0.65     0.02    2.95
 DataMiner        FactorNull       0.81    0.77    0.85     6.2      4.90      7.90   2.77    2.75    2.79     2.67     1.02    5.55
 DataMiner        Microstructure   0.81    0.77    0.85     6.3      5.00      8.00   2.79    2.76    2.81     2.76     1.08    5.55
 DataMiner        RegimeSwitch     0.82    0.78    0.85     5.3      4.10      6.90   2.76    2.73    2.79     2.77     1.12    5.57
 DataMiner        WhiteNoise       0.80    0.77    0.84     5.5      4.20      7.10   2.77    2.74    2.79     2.69     1.08    5.85
 FactorMimic      FactorNull       0.79    0.76    0.83     5.7      4.40      7.30   0.82    0.78    0.86     0.62     0.03    2.92
 FactorMimic      Microstructure   0.69    0.66    0.73     2.1      1.40      3.20   0.71    0.68    0.74     0.63     0.03    2.64
 FactorMimic      RegimeSwitch     0.81    0.77    0.85     4.5      3.40      6.00   0.74    0.71    0.78     0.54     0.04    2.63
 FactorMimic      WhiteNoise       0.80    0.77    0.84     4.3      3.20      5.70   0.79    0.76    0.83     0.64     0.03    2.74
 Lookahead        FactorNull       42.43   42.30   42.56   100.0    99.60   100.00    51.65   51.52   51.78    1.22     1.08    1.37
 Lookahead        Microstructure   37.99   37.88   38.11   100.0    99.60   100.00    46.23   46.10   46.35    1.21     1.07    1.40
 Lookahead        RegimeSwitch     21.32   21.20   21.44   100.0    99.60   100.00    24.71   24.59   24.82    1.16     0.92    1.43
 Lookahead        WhiteNoise       42.36   42.23   42.49   100.0    99.60   100.00    51.72   51.59   51.86    1.22     1.07    1.38
 RandomBaseline   FactorNull       0.79    0.75    0.83     5.3      4.10      6.90   0.81    0.77    0.85     0.66     0.04    3.00
 RandomBaseline   Microstructure   0.82    0.78    0.86     6.9      5.50      8.60   0.80    0.76    0.83     0.62     0.04    2.79
 RandomBaseline   RegimeSwitch     0.79    0.75    0.83     4.8      3.60      6.30   0.82    0.78    0.85     0.65     0.04    2.99
 RandomBaseline   WhiteNoise       0.79    0.75    0.82     4.6      3.50      6.10   0.83    0.79    0.87     0.65     0.04    3.17
 RegimeDetector   FactorNull       0.79    0.76    0.83     3.7      2.70      5.10   0.77    0.73    0.80     0.65     0.02    2.67
 RegimeDetector   Microstructure   0.65    0.62    0.68     2.5      1.70      3.70   0.67    0.63    0.70     0.60     0.03    2.48
 RegimeDetector   RegimeSwitch     0.80    0.76    0.83     5.0      3.80      6.50   0.81    0.77    0.84     0.60     0.03    2.78
 RegimeDetector   WhiteNoise       0.79    0.75    0.83     5.1      3.90      6.60   0.80    0.76    0.84     0.65     0.04    2.73




                                                             38
C.3     Detailed Results: Capacity-Driven Inflation
C.3.1    Evolution of effective multiplicity across K
Table C.23 reports the evolution of K  ceff with nominal search size K for the three workflows under
White Noise. Feature Mining maintains perfect tracking (K       ceff = K) by construction. Under
Hyperparameter Tuning, K   ceff remains in the low single digits and settles around ≈ 3 by K = 400;
the mild non-monotonicity across intermediate K reflects Monte Carlo variability rather than an
expansion of independent trials. Trend Following exhibits intermediate but non-negligible effective
search dimensionality, rising to Kceff ≈ 5.9 by K = 400.

  Table C.23: Effective multiplicity under White Noise (Boosting). Mean K
                                                                        ceff across workflows.

 Workflow                  K=1    K=5     K = 10        K = 25   K = 50   K = 100   K = 200   K = 400
 Saturation (Correlated)    1     1.69      1.96        2.20     4.19      3.53      3.14      2.93
 Inflation (Independent)    1     5.00     10.00        25.00    50.00    100.00    200.00    400.00
 Robustness Check           1     1.81     2.52         3.85     4.76      5.38      5.65      5.86



C.3.2    Saturation ratio
Table C.24 reports the saturation ratio K
                                        ceff /K. For Hyperparameter Tuning, the ratio declines from
0.34 at K = 5 to 0.01 at K = 400, indicating extreme redundancy. Trend Following also displays
declining saturation ratios, though from a less compressed effective search space. Feature Mining
maintains a ratio of 1.00 by construction.

  Table C.24: Saturation ratio under White Noise (Boosting). Mean ratio K
                                                                        ceff /K by workflow.

 Workflow                  K=1    K=5     K = 10        K = 25   K = 50   K = 100   K = 200   K = 400
 Saturation (Correlated)    1     0.34     0.20          0.09     0.08     0.04      0.02      0.01
 Inflation (Independent)    1     1.00     1.00          1.00     1.00     1.00      1.00      1.00
 Robustness Check           1     0.36     0.25          0.15     0.10     0.05      0.03      0.01



C.3.3    In-sample inflation across K
                                            ⋆ |] with K. Feature Mining follows the
                                                                                    √
Table C.25 documents the growth of E[|ZIS                                             log K scaling
predicted by theory, reaching 3.21 at K = 400. Hyperparameter Tuning shows slower but still
substantial growth, from 1.35 at K = 5 to 2.56 at K = 400. Trend Following also exhibits substantial
inflation, rising from 1.07 at K = 5 to 2.19 at K = 400.

Table C.25: In-sample inflation under White Noise (Boosting). Mean absolute in-sample statistic
    ⋆ |] by workflow and K.
E[|ZIS

 Workflow                  K=1    K=5     K = 10        K = 25   K = 50   K = 100   K = 200   K = 400
 Saturation (Correlated)   0.83   1.35     1.55          1.81     2.16     2.30      2.43      2.56
 Inflation (Independent)   0.85   1.56     1.88          2.28     2.51     2.77      3.02      3.21
 Robustness Check          0.77   1.07     1.26          1.59     1.78     1.97      2.12      2.19




                                                   39
C.4      Threshold Amplification: Full Sweeps
C.4.1      Amplification across threshold rules and correlation levels
Table C.26 provides a comprehensive view of threshold amplification, including 5%–95% envelopes
for the in-sample statistic. Walk-forward performance remains bounded near the null expectation
regardless of thresholding and is reported here only through the mean |ZWF |, while in-sample
extremeness increases systematically with threshold aggressiveness.

Table C.26: Threshold amplification at K = 1,000 under high correlation (ρ = 0.9). K
                                                                                   ceff (Pred) is
computed on raw continuous scores, and Keff (Signal) is computed on realized thresholded trading
                                        c
signals. Amp. Factor is K
                        ceff (Signal)/K
                                      ceff (Pred). Results are based on N = 1,000 independent
simulations per cell.

 Threshold Rule                K
                               ceff (Pred)      K
                                                ceff (Signal)     Amp.      |ZIS | Envelope       |ZWF | Mean
 None                             1.24              1.24          1.00     1.82 (1.07–2.95)              0.80
 Fixed (thr=0.0)                  1.24              1.97          1.59     2.50 (1.75–3.56)              0.79
 Fixed (thr=0.5)                  1.24              1.60          1.28     2.23 (1.51–3.39)              0.79
 Fixed (thr=1.0)                  1.24              1.91          1.54     2.42 (1.69–3.52)              0.79
 Fixed (thr=1.5)                  1.24              2.41          1.93     2.59 (1.88–3.57)              0.80
 Fixed (thr=2.0)                  1.24              3.34          2.68     2.63 (1.98–3.45)              0.86
 Adaptive (q=0.50)                1.24              1.69          1.36     2.27 (1.55–3.30)              0.80
 Adaptive (q=0.70)                1.24              1.94          1.56     2.42 (1.71–3.58)              0.79
 Adaptive (q=0.80)                1.24              2.16          1.74     2.56 (1.82–3.64)              0.77
 Adaptive (q=0.90)                1.24              2.60          2.09     2.62 (1.92–3.64)              0.80
 Adaptive (q=0.95)                1.24              3.20          2.57     2.66 (1.99–3.48)              0.82


C.4.2      Sweep over correlation and K
Tables C.27 and C.28 report in-sample selection bias and walk-forward performance across a grid of
ρ ∈ {0, 0.9} and K ranging from 1 to 1000. The incremental effect of thresholding on in-sample
extremeness is strongest at high correlation: when ρ = 0.9, both fixed and adaptive thresholding
shift E[maxk |ZIS,k |] materially above the no-threshold baseline, whereas under independence (ρ = 0)
the three regimes remain close across the full K sweep. By contrast, walk-forward magnitudes
remain stable near the null benchmark across both ρ and K, indicating that the threshold-induced
increase is an in-sample selection effect rather than a corresponding out-of-sample improvement.

Table C.27: In-sample selection bias sweep across nominal K. Entries report E[maxk |ZIS,k |] under
the null.

 ρ     Regime           K=1     K=2      K=5    K = 10   K = 20   K = 50   K = 100   K = 200   K = 500    K = 1000
 0.0   None             0.79     1.18    1.57    1.91      2.19    2.55     2.79      3.01      3.29        3.51
 0.0   Fixed (1)        0.81     1.17    1.60    1.92      2.21    2.53     2.79      3.01      3.30        3.51
 0.0   Adaptive (0.9)   0.83     1.17    1.57    1.88      2.18    2.51     2.73      2.96      3.23        3.40
 0.9   None             0.82     0.96    1.13    1.25      1.39    1.48     1.58      1.67      1.75        1.82
 0.9   Fixed (1)        0.79     1.03    1.32    1.51      1.72    1.88     2.01      2.16      2.31        2.42
 0.9   Adaptive (0.9)   0.81     1.07    1.40    1.62      1.81    2.04     2.18      2.34      2.52        2.62




                                                           40
Table C.28: Walk-forward performance of the configuration selected in-sample. Entries report
E[|ZWF (k ⋆ )|].

 ρ     Regime           K=1    K=2    K=5    K = 10   K = 20   K = 50   K = 100   K = 200   K = 500   K = 1000
 0.0   None             0.79   0.82   0.83    0.84     0.83     0.80     0.80      0.82      0.77       0.80
 0.0   Fixed (1)        0.80   0.80   0.84    0.82     0.80     0.82     0.85      0.82      0.81       0.80
 0.0   Adaptive (0.9)   0.79   0.76   0.80    0.83     0.80     0.83     0.82      0.82      0.81       0.83
 0.9   None             0.78   0.80   0.82    0.82     0.82     0.82     0.78      0.77      0.84       0.80
 0.9   Fixed (1)        0.82   0.79   0.84    0.76     0.82     0.82     0.80      0.80      0.80       0.79
 0.9   Adaptive (0.9)   0.82   0.82   0.81    0.83     0.79     0.80     0.82      0.81      0.80       0.80



C.5      Effective Multiplicity: Monte Carlo Validation of K
                                                           c
                                                             eff

The effective multiplicity Keff defined in Equation (4) is a key diagnostic for search-space dimen-
sionality. In practice, it must be estimated from a finite sample of strategy returns. When the
number of strategies K approaches or exceeds the sample size T , the sample correlation matrix
becomes ill-conditioned, rendering standard estimators unstable. We therefore apply the shrinkage
estimator of Schäfer and Strimmer (2005) as implemented in corpcor. This appendix validates the
estimator’s finite-sample performance.

Design.      We conduct a Monte Carlo experiment with M = 1, 000 replications across three regimes:

     (i) Independent: K uncorrelated strategies (Σ = I), where the true Keff = K.

 (ii) Factor structure: K = 100 strategies driven by m = 3 common factors plus idiosyncratic
      noise. The true Keff is derived from the population covariance matrix implied by fixed factor
      loadings.

(iii) High-dimensional: Regimes where K ≥ T , specifically K = 500 with T = 250 and T = 500
      under independence.

   For each replication, we compute Kceff using the shrinkage-corrected correlation matrix and, as a
baseline, the raw sample correlation matrix. We report bias, root mean squared error (RMSE), and
the average shrinkage intensity λ.

Results. Table C.29 reports the performance of the shrinkage estimator. For independent
strategies, the estimator is virtually unbiased and exhibits negligible RMSE (≤ 0.02). Under the
factor model, a small positive bias appears when T is small (0.29 at T = 250), but it decays rapidly
as T increases. In the high-dimensional regime (K > T ), the estimator remains stable with a bias
of −0.03 and RMSE of 0.05.
    Table C.30 contrasts the shrinkage estimator with the naive sample estimator. The sample
estimator is unusable when K > T (RMSE > 300), and even when T ≫ K it exhibits substantial
downward bias (e.g., −9.0 at T = 1, 000). Shrinkage uniformly dominates the sample estimator
across all metrics and scenarios, ensuring that Keff remains a conservative and robust diagnostic
even in high-dimensional search spaces.




                                                      41
Table C.29: Performance of K
                           ceff under shrinkage correlation estimation (Monte Carlo, M = 1000).


                    Scenario              K       T      Bias   RMSE       λ
                    Independent          100      250   −0.01      0.02   0.99
                    Independent          100      500    0.00      0.01   0.99
                    Independent          100     1000    0.00      0.01   0.99
                    Factor (m = 3)       100      250   0.29       0.36   0.03
                    Factor (m = 3)       100      500   0.14       0.20   0.02
                    Factor (m = 3)       100     1000   0.07       0.12   0.01
                    High-dim (K > T )    500      250   −0.03      0.05   1.00
                    High-dim (K = T )    500      500   −0.01      0.02   1.00




        Table C.30: Diagnostic Validation: Shrinkage vs. Sample Estimator (M = 1000).

      Scenario             K     T      BiasShrink    RMSEShrink    BiasSample   RMSESample
      Independent         100    250     −0.01           0.02        −28.45         28.46
      Independent         100    500      0.00           0.01        −16.55        16.55
      Independent         100   1000      0.00           0.01         −9.02         9.02
      Factor (m = 3)      100    250     0.29            0.36         −0.10         0.22
      Factor (m = 3)      100    500     0.14            0.20         −0.05         0.15
      Factor (m = 3)      100   1000     0.07            0.12         −0.03         0.10
      High-dim (K > T )   500    250     −0.03           0.05        −333.57       333.57
      High-dim (K = T )   500    500     −0.01           0.02        −250.02       250.02




                                               42
C.6     Robustness Checks
C.6.1    Parameter sweeps across null families
Table C.31 reports results for the null-workflow experiments across five strict null families and
two microstructure placebos, each with two parameterizations. Across the strict null families,
the qualitative pattern remains stable: correlated tuning (HyperparameterTuning) saturates at
low effective multiplicity, whereas independent mining (FeatureMining) continues to inflate in-
sample evidence while leaving walk-forward performance near the null benchmark. In the MA(1)
microstructure placebos, however, HyperparameterTuning is decisively falsified, with walk-forward
failure rates of 100% and mean walk-forward extremeness exceeding the corresponding in-sample
extremeness.
Table C.31: Robustness: parameter sweeps across structural nulls and microstructure placebos.
Comparison of saturation (HyperparameterTuning) versus inflation (FeatureMining) across search
budgets K ∈ {25, 100, 200}. Based on N = 1,000 replications per cell.

                         Panel A: HyperparameterTuning (Correlated Tuning)
 Environment             Workflow                    K   K
                                                         b eff   |ZIS |   |ZWF |    ∆Z     Fail %   BIF
 GARCH(1,1) Persistent   HyperparameterTuning     25     1.77    1.59      0.82     0.77      5.7   1.50
 GARCH(1,1) Persistent   HyperparameterTuning    100     1.74    1.68      0.81     0.87      5.5   1.56
 GARCH(1,1) Persistent   HyperparameterTuning    200     1.74    1.71      0.82     0.89      5.8   1.60
 GARCH(1,1) Volatile     HyperparameterTuning     25     1.75    1.58      0.81     0.77      4.6   1.46
 GARCH(1,1) Volatile     HyperparameterTuning    100     1.72    1.67      0.82     0.84      4.4   1.56
 GARCH(1,1) Volatile     HyperparameterTuning    200     1.72    1.69      0.82     0.87      4.5   1.59
 MA(1) θ = −0.30         HyperparameterTuning     25     1.80    5.23      6.97    -1.74    100.0   0.75
 MA(1) θ = −0.30         HyperparameterTuning    100     1.77    5.32      6.96    -1.64    100.0   0.77
 MA(1) θ = −0.30         HyperparameterTuning    200     1.76    5.34      6.95    -1.61    100.0   0.77
 MA(1) θ = +0.30         HyperparameterTuning     25     1.80    5.13      6.93    -1.80    100.0   0.73
 MA(1) θ = +0.30         HyperparameterTuning    100     1.77    5.21      6.94    -1.73    100.0   0.74
 MA(1) θ = +0.30         HyperparameterTuning    200     1.76    5.24      6.93    -1.70    100.0   0.75
 Regime Stable           HyperparameterTuning     25     1.63    1.53      0.81     0.72      4.7   1.39
 Regime Stable           HyperparameterTuning    100     1.60    1.61      0.81     0.80      4.5   1.46
 Regime Stable           HyperparameterTuning    200     1.59    1.63      0.81     0.83      4.3   1.48
 Regime Unstable         HyperparameterTuning     25     1.80    1.58      0.81     0.77      5.3   1.43
 Regime Unstable         HyperparameterTuning    100     1.77    1.68      0.80     0.88      5.3   1.53
 Regime Unstable         HyperparameterTuning    200     1.77    1.70      0.80     0.90      5.6   1.56
 Student t, df = 5       HyperparameterTuning     25     1.89    1.60      0.78     0.82      3.8   1.50
 Student t, df = 5       HyperparameterTuning    100     1.86    1.69      0.79     0.90      3.6   1.61
 Student t, df = 5       HyperparameterTuning    200     1.86    1.71      0.79     0.92      4.2   1.61
 Student t, df = 10      HyperparameterTuning     25     1.84    1.60      0.80     0.80      4.9   1.44
 Student t, df = 10      HyperparameterTuning    100     1.81    1.70      0.80     0.90      4.9   1.55
 Student t, df = 10      HyperparameterTuning    200     1.80    1.73      0.80     0.92      5.0   1.55
 White Noise High Vol    HyperparameterTuning     25     1.82    1.56      0.79     0.77      4.8   1.47
 White Noise High Vol    HyperparameterTuning    100     1.78    1.66      0.78     0.88      4.5   1.54
 White Noise High Vol    HyperparameterTuning    200     1.78    1.69      0.78     0.91      4.6   1.63
 White Noise Low Vol     HyperparameterTuning     25     1.81    1.61      0.79     0.82      4.8   1.46
 White Noise Low Vol     HyperparameterTuning    100     1.78    1.70      0.79     0.92      4.5   1.58
 White Noise Low Vol     HyperparameterTuning    200     1.78    1.74      0.79     0.95      4.3   1.63
                            Panel B: FeatureMining (Independent Search)
                                                                               Continued on next page


                                                43
                                           Table C.31 (continued)
 Environment                Workflow                    K     Kb eff     |ZIS |   |ZWF |   ∆Z     Fail %   BIF

 Environment                Workflow                       K     K
                                                                 b eff   |ZIS |   |ZWF |   ∆Z     Fail %   BIF
 GARCH(1,1) Persistent      FeatureMining               25      25.00    2.29      0.78    1.51      4.6   2.21
 GARCH(1,1) Persistent      FeatureMining              100     100.00    2.77      0.78    1.99      5.5   2.74
 GARCH(1,1) Persistent      FeatureMining              200     200.00    3.00      0.81    2.19      5.7   2.87
 GARCH(1,1) Volatile        FeatureMining               25      25.00    2.28      0.83    1.46      5.7   2.11
 GARCH(1,1) Volatile        FeatureMining              100     100.00    2.78      0.81    1.97      5.5   2.67
 GARCH(1,1) Volatile        FeatureMining              200     200.00    2.99      0.80    2.19      4.8   2.87
 MA(1) θ = −0.30            FeatureMining               25      25.00    2.25      0.82    1.44      5.4   2.07
 MA(1) θ = −0.30            FeatureMining              100     100.00    2.79      0.79    2.00      4.3   2.66
 MA(1) θ = −0.30            FeatureMining              200     200.00    3.02      0.79    2.23      5.4   3.04
 MA(1) θ = +0.30            FeatureMining               25      25.00    2.26      0.77    1.48      4.4   2.17
 MA(1) θ = +0.30            FeatureMining              100     100.00    2.77      0.84    1.94      4.7   2.68
 MA(1) θ = +0.30            FeatureMining              200     200.00    3.01      0.84    2.16      6.2   2.86
 Regime Stable              FeatureMining               25      25.00    2.28      0.83    1.45      5.4   2.09
 Regime Stable              FeatureMining              100     100.00    2.79      0.80    1.99      5.0   2.71
 Regime Stable              FeatureMining              200     200.00    2.97      0.76    2.21      4.1   2.90
 Regime Unstable            FeatureMining               25      25.00    2.27      0.82    1.45      5.5   2.13
 Regime Unstable            FeatureMining              100     100.00    2.75      0.81    1.94      4.6   2.68
 Regime Unstable            FeatureMining              200     200.00    3.01      0.79    2.22      4.8   2.94
 Student t, df = 5          FeatureMining               25      24.99    2.27      0.81    1.46      5.4   2.17
 Student t, df = 5          FeatureMining              100     100.00    2.76      0.82    1.94      5.7   2.70
 Student t, df = 5          FeatureMining              200     200.00    3.00      0.76    2.24      4.0   2.99
 Student t, df = 10         FeatureMining               25      25.00    2.29      0.80    1.49      5.2   2.18
 Student t, df = 10         FeatureMining              100     100.00    2.80      0.79    2.01      4.5   2.75
 Student t, df = 10         FeatureMining              200     200.00    3.02      0.79    2.23      4.4   2.82
 White Noise High Vol       FeatureMining               25      25.00    2.26      0.78    1.48      4.4   2.18
 White Noise High Vol       FeatureMining              100     100.00    2.75      0.80    1.95      5.8   2.71
 White Noise High Vol       FeatureMining              200     200.00    3.02      0.79    2.23      4.0   2.99
 White Noise Low Vol        FeatureMining               25      25.00    2.28      0.83    1.45      6.0   2.23
 White Noise Low Vol        FeatureMining              100     100.00    2.76      0.81    1.96      5.3   2.71
 White Noise Low Vol        FeatureMining              200     200.00    2.99      0.79    2.20      4.6   2.96


C.6.2    Split sensitivity, grid density, and seed stability
Table C.32 reports robustness to variations in the in-sample/walk-forward split ratio, hyperparameter grid
density, and random seed family for the White Noise / HyperparameterTuning configuration at K = 100.
Point estimates remain stable across split and seed perturbations, while denser hyperparameter grids
mechanically raise effective multiplicity and in-sample extremeness without altering the qualitative conclusion
that walk-forward evidence remains near the null benchmark.

C.6.3    Temporal integrity audit
Table C.33 reports the risk deflation experiment. Shuffled validation underestimates the standard error by
approximately 28%, inflating the apparent Z-statistic from 0.91 to 1.64 and increasing the failure rate from
9.2% to 36.4%.

C.6.4    Architecture generalization
To assess whether the capacity-driven inflation documented in Section 5.3 is specific to sequential gradient
boosting or extends to other non-linear ensembles, we replicate the audit using Random Forests (bagging)


                                                      44
Table C.32: Audit parameter sensitivity under White Noise / HyperparameterTuning (K = 100).
Impact of training split size, grid density, and random seed family on effective multiplicity, in-sample
and walk-forward extremeness, the absolute gap ∆Z, walk-forward failure rates, and stabilized BIF.

 Test          Environment           Variant           K
                                                       b eff     |ZIS |    |ZWF |      ∆Z    Fail %     BIF
 Split Sensitivity
 Split 0.5 White Noise               Dev Set           1.80      1.73       0.81    0.92          5.7   1.62
 Split 0.6 White Noise               Dev Set           1.78      1.70       0.79    0.92          4.5   1.58
 Split 0.7 White Noise               Dev Set           1.78      1.71       0.83    0.89          5.4   1.61
 Grid Density
 Grid      WN Light Grid             Dev Set           1.78      1.70       0.80    0.89          5.2   1.55
 Grid      WN Dense Grid             Dev Set           2.63      2.04       0.83    1.21          6.3   1.91
 Seed Stability
 Seed        White Noise             Dev Set           1.78      1.70       0.79    0.92          4.5   1.58
 Seed        White Noise             Holdout Set       1.79      1.70       0.82    0.87          4.7   1.59

           Table C.33: Temporal integrity audit: walk-forward versus shuffled validation.

        Protocol         Mean |Z|     Fail Rate (%)       Risk Deflation     p-value (H0 : Ratio = 1)
        Walk-Forward        0.91           9.2              1.00 (ref)                    —
        Shuffled Split      1.64           36.4                0.72                    < 10−100


alongside XGBoost (boosting). The protocol enforces strict temporal separation between model fitting,
adaptive selection, and evaluation. Each candidate model is fit on a training set Ttrain , while the winning
configuration is selected by maximizing the absolute HAC statistic on a disjoint development set Tdev . The
selected winner is then evaluated on a strictly disjoint walk-forward set TWF .
     Table C.34 reports the stabilized inflation factor BIF0.5 = |Zdev |/ max(|ZWF |, 0.5) for search budgets
K = 1 and K = 50. At K = 1, the median BIF0.5 remains below unity for both architectures, indicating
no systematic inflation when no adaptive search is performed. As the search budget increases to K = 50,
inflation becomes pronounced, with median BIF0.5 rising to 3.31 for XGBoost and 2.65 for Random Forest.
This confirms that selection bias operates across non-linear ensemble families even when memorization is
mitigated by a disjoint development slice: adaptive search alone is sufficient to amplify apparent evidence
under the White Noise null, with the effect somewhat stronger for boosting than for bagging.

Table C.34: Architecture Generalization. Median stabilized Backtest Inflation Factor (BIF0.5 )
across sequential boosting and parallel bagging algorithms under the global null.

                    Model Architecture                    BIF (K = 1)      BIF (K = 50)
                    Gradient Boosting (XGBoost)                0.87             3.31
                    Random Forest                              0.85             2.65



C.6.5     Metric Stabilization: Ratio vs. Difference
We evaluate the behavior of inflation metrics in the critical limit where walk-forward evidence vanishes
  ⋆
(ZWF → 0). Figure C.10 contrasts the ratio-based BIF against the difference-based ∆Z.


                                                     45
    The legacy ratio (BIFraw ) exhibits a singularity at zero and extreme instability in the gray zone (ZWF
                                                                                                         ⋆
                                                                                                            < τ ).
Table C.35 quantifies this divergence, demonstrating the undefined output (NA) of the raw ratio versus the
bounded behavior of the stabilized metric as walk-forward evidence approaches zero. The stabilized BIF uses
a denominator floor τ purely to prevent degeneracy when walk-forward evidence is near zero. Consequently,
BIF is reported only as an internal ranking heuristic within a study, while our primary inflation diagnostic
is the threshold-free absolute gap ∆Z, which is invariant to τ . We report sensitivity to τ and show that
qualitative conclusions are stable over a broad range of values (see Section C.6.6).
    In contrast, the Absolute Magnitude Gap (∆Z) maintains linearity throughout the noise floor (Right
Panel). Because it avoids division, ∆Z provides a continuous, parameter-free measure of inflation that
remains interpretable even when walk-forward performance is entirely spurious.

                Metric Stabilization                                                                   Implied Deflator (1 / BIF)                                      Absolute Magnitude Gap (ΔZ)
                Gray Zone: Legacy BIF breaks. Stabilized BIF saturates.                                The retention rate applied to IS performance.                   Parameter-free and perfectly linear through the noise floor.

            6                                                                                   100%                                                               3




                                                                                                75%

            4                                                                                                                                                      2
BIF Value




                                                                                     Deflator




                                                                                                                                                              ΔZ
                                                                                                50%




            2                                                                                                                                                      1

                                                                                                25%




                  3                    2                 1                       0
                               Walk − Forward Evidence ( ZWF )                                   0%                                                                0

                                                                                                         3                 2                1            0               3                  2                   1                     0
                       Legacy BIF (Undefined < tau)   Stabilized BIF (Regularized)
                                                                                                                    Walk − Forward Evidence ( ZWF )                                   Walk − Forward Evidence ( ZWF )



Figure C.10: Metric Stabilization Stress Test. Behavior of inflation metrics as walk-forward evidence
          ⋆ = 3.0, τ = 0.5). Left: The legacy BIF (dotted) is undefined in the gray zone (Z ⋆
decays (ZIS                                                                                  WF < τ ),
whereas the stabilized BIF (solid) saturates at the regularization floor. Center: The implied deflator
(1/BIFstab
       τ   ) transitions smoothly into the spurious region, capping the retention rate. Right: The
Absolute Magnitude Gap (∆Z) remains perfectly linear and stable throughout the noise floor,
avoiding the singularity issues of ratio-based metrics.


Table C.35: Stress-test values for raw and stabilized inflation metrics as walk-forward evidence
          ⋆ = 3.0, τ = 0.5). The raw ratio is undefined (NA) when Z ⋆
decays (ZIS                                                             WF < τ . The deflator dτ
represents the retention rate of in-sample performance.

                                                       ⋆
                                                      ZWF              BIFraw                     BIFstab
                                                                                                     τ                   Deflator (dτ )                ∆Z                    Status
                                                      3.00                1.00                         1.00                      1.000                 0.00            Agreement
                                                      2.00                1.50                         1.50                      0.667                 1.00            Agreement
                                                      1.00                3.00                         3.00                      0.333                 2.00            Agreement
                                                      0.50                6.00                         6.00                      0.167                 2.50            Boundary
                                                      0.25                NA                           6.00                      0.167                 2.75            Stabilized
                                                      0.00                NA                           6.00                      0.167                 3.00            Stabilized



C.6.6                       Parameter Sensitivity and Metric Invariance
We assess the structural stability of inflation metrics by sweeping the regularization threshold across a grid
τ ∈ [0.1, 1.5]. Figure C.11 contrasts the behavior of the ratio-based BIFstab against the difference-based ∆Z.


                                                                                                                               46
     The analysis reveals a critical limitation in ratio-based metrics: BIFstab exhibits high sensitivity to the
choice of floor, with the median inflation factor decaying inversely to τ (Panel A). While a local plateau
exists near τ ∈ [0.3, 0.5], the absolute magnitude of the metric remains conditional on an arbitrary parameter
choice.
     In contrast, the Absolute Magnitude Gap (∆Z) demonstrates structural invariance (Panel B). Because
∆Z operates on the linear difference between evidence scales, it does not require a stability floor to prevent
singularities. This parameter independence confirms ∆Z as the more robust standard for benchmarking
falsification audits, while τ = 0.5 is retained merely as a standardized convention for legacy BIF comparisons.

                      Panel A: BIF Sensitivity                                                               Panel B: Delta Z Invariance
                      BIF scales dynamically depending on the selected tau floor.                            Delta Z is structurally invariant to the choice of tau.

                  4                                                                                    2.0




                  3                                                                                    1.5
 Median BIFstab




                                                                                           Median ΔZ
           τ




                                                                                                       1.0
                  2




                                                                                                       0.5
                  1




                      0.0                     0.5                       1.0         1.5                                         0.4                   0.8              1.2
                                                    Operational Floor (τ)                                                                    Operational Floor (τ)



Figure C.11: Metric Sensitivity Stress Test. Comparison of inflation metric stability across varying
regularization thresholds τ . Panel A demonstrates that ratio-based metrics (BIFstab ) are parameter-
sensitive, scaling inversely with the chosen floor even within the stability plateau (green shaded
region). Panel B demonstrates that the Absolute Magnitude Gap (∆Z) is structurally invariant to
the regularization parameter, providing a stable benchmark for falsification.


C.6.7                       Null-calibrated operational thresholds
Table C.36 reports null-calibrated critical values for the absolute magnitude gap (∆Z) together with legacy
ratio-based calibrations derived from the White Noise global null. The reported thresholds correspond to the
95% and 99% empirical quantiles of each metric. Because ∆Z is parameter-invariant and remains well-defined
throughout the noise floor, it serves as the primary threshold for formal inflation classification. By contrast,
                                                                      ⋆
BIF quantiles are reported only on the stability-gated subset {|ZWF      | ≥ τ } with τ = 0.5, and should be
interpreted strictly as secondary within-study heuristics rather than as parameter-free benchmarks. The
table also reports ζ0.99 , the 99% quantile of the walk-forward winner magnitude. Across all calibrations,
ζ0.99 remains in the vicinity of the standard-normal upper tail, consistent with the bounded null behavior of
strictly disjoint walk-forward evaluation.


D                       Transaction Cost Mechanics: Synthetic Validation
This appendix validates the mechanical relationship between signal turnover, gross performance, and transac-
tion costs under the audit’s cost accounting. The objective is to confirm that the break-even cost metric
behaves consistently under strict walk-forward evaluation and a linear per-side cost model. The reported
break-even values are not an empirical robustness claim for any specific asset or strategy in the main text.
    We simulate N = 1,000 independent Monte Carlo paths from a regime-switching process calibrated to
embed a persistent trend component (annual volatility 15%, trend Sharpe 2.0). The price process is indexed


                                                                                          47
Table C.36: Recommended operational thresholds derived from the empirical distribution of the
White Noise global nulls. ∆Z provides the primary formal evaluation threshold. BIF quantiles are
                                          ⋆ | ≥ τ } with τ = 0.5. ζ denotes the 99% quantile of
reported on the stability-gated subset {|ZWF
valid walk-forward winner magnitudes.

 Source               Setting                          ∆Z0.95     ∆Z0.99        τ     BIFgate
                                                                                         τ,0.95   BIFgate
                                                                                                     τ,0.99   ζ0.99
 Scaling law          K=1000 (Indep.)                    3.68      4.12         0.5     6.48        7.29      2.77
 Redundancy law       Clusters=1 (Perfect Corr.)         2.57      3.24         0.5     4.20        5.49      2.56
 Redundancy law       Clusters=500 (Indep.)              3.53      3.94         0.5     6.13        7.05      2.58
 ML Workflows         FeatureMining                      3.44      3.85         0.5     5.88        6.76      2.69
 ML Workflows         HyperparameterTuning               3.08      3.56         0.5     4.94        6.19      2.51
 ML Workflows         TrendFollowing                     2.62      3.14         0.5     4.29        5.60      2.40


on business days to match the 252-day annualization convention.
    For each path, the strategy selects its lookback window using the in-sample period TIS and is then
evaluated on the walk-forward period TWF , with parameters frozen out of sample. Let rtWF denote the gross
walk-forward strategy return and let st ∈ {−1, 0, 1} denote the full continuous signal path. Two-way traded
volume on the walk-forward block is defined as
                                                      X
                                       V2 (TWF ) =        |st − st−1 | ,                               (D.1)
                                                       t∈TWF

so that a flip from +1 to −1 contributes 2 units, consistent with per-side transaction costs. This accounting
includes the transition trade at the TIS /TWF boundary whenever the first walk-forward position differs
from the final in-sample position. The annualized two-way volume is V̄2 = V2 (TWF )/(|TWF |/252), and the
annualized gross mean return is µ̄gross = 252 · E[rtWF ], estimated by the sample mean on TWF .
     Under a linear cost model with cost c per side (in return units), the annualized net mean is µ̄net (c) =
µ̄gross − V̄2 c. The break-even cost is the unique solution to µ̄net (c) = 0, given by

                                           µ̄gross
                                    c⋆ =           ,    c⋆bps = 10,000 · c⋆ .                                 (D.2)
                                             V̄2

We report turnover in one-way units as V̄1 = V̄2 /2 for interpretability, while break-even is computed using
two-way volume, consistent with per-side costs. To align the economic calculation with the walk-forward
significance screen, we compute break-even only for realizations satisfying ZWF ≥ 1.96. The resulting 39.5%
pass rate should be interpreted as empirical power under the signal-bearing DGP rather than as a null
rejection rate; under a no-predictability null, the corresponding one-sided exceedance probability would be
2.5%.
    Table D.37 summarizes the distribution of annualized one-way turnover and break-even costs across the
passing subset. The dispersion in break-even costs reflects path dependence in realized gross performance and
trading intensity; the purpose of this validation is to demonstrate that the accounting framework remains
mechanically consistent across stochastic realizations.

D.1     Replication Materials
All results in the paper are generated by the accompanying replication scripts, which reproduce the simulation
experiments and empirical applications end-to-end, including walk-forward evaluation, induced-null audits,
and inflation diagnostics. The authoritative reference fo