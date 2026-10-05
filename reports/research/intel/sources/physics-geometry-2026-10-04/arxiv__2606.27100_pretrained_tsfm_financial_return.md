source: https://arxiv.org/pdf/2606.27100
fetched_utc: 2026-10-04T18:41:32Z
bytes_raw: 2155661

Pretrained Time-Series Foundation Models for
                                                           Financial Return Forecasting
                                                                Miquel Noguer i Alonso1                  Rodolfo Pereira Franklin1
                                                                             1
                                                                                 Artificial Intelligence Finance Institute

                                                                                             June 26, 2026
arXiv:2606.27100v1 [q-fin.MF] 25 Jun 2026




                                                                                               Abstract
                                                     Financial return forecasting is a difficult test case for time-series foundation models because
                                                 daily equity returns combine low signal-to-noise ratios, structural breaks, heavy tails, and
                                                 weak persistence. This paper benchmarks pretrained time-series foundation models (TSFMs)
                                                 against train-from-scratch neural baselines in a deliberately conservative financial setting. We
                                                 evaluate TimeGPT/TimeGPT-LH, TimesFM-2.5, Moirai-2.0, Chronos, and Chronos-2 against
                                                 NBEATS, NHITS, PatchTST, iTransformer, and KAN on five liquid U.S. equities (AAPL,
                                                 AMZN, GOOG, JPM, and META), using both linear and log returns. All neural models are
                                                 compared under an equalized context budget of L = 512 observations, a rolling-origin protocol,
                                                 and error metrics benchmarked against naive random-walk alternatives. The paper also provides
                                                 a compact theoretical framing of pretraining as an inductive prior, linking PAC-Bayes transfer
                                                 intuition, information-theoretic predictability limits, attention geometry, and score-distribution
                                                 comparisons to the empirical design. This framing clarifies why strong rankings need not imply
                                                 economically meaningful predictability in noisy markets. The main finding is pragmatic rather
                                                 than sensational. Pretrained TSFMs dominate the ranking distribution, accounting for 8 of
                                                 10 task-level wins, with Moirai-2.0 and TimesFM-2.5 achieving the strongest average ranks.
                                                 TimesFM-2.5 leads the AAPL and JPM tasks, Moirai-2.0 leads the GOOG tasks and one AMZN
                                                 task, and Chronos wins the remaining AMZN task. However, the iTransformer baseline wins
                                                 both META tasks, showing that local supervised learning can still outperform generic pretraining
                                                 for specific assets and regimes. More importantly, gains over the random-walk benchmark are
                                                 small and sparse. A one-sided Diebold–Mariano test rejects equal or inferior predictive accuracy
                                                 only for Chronos on AMZN and Moirai-2.0 on GOOG. The evidence therefore supports TSFMs
                                                 as useful practical priors that reduce model-development costs in low-data financial forecasting,
                                                 but not as universal engines of statistically reliable alpha generation or trading performance in
                                                 realistic empirical deployment conditions.

                                            Keywords: Time-series foundation models; financial return forecasting; pretrained forecasting
                                            models; equity returns; rolling-origin evaluation; Diebold–Mariano test; TimeGPT; TimesFM;
                                            Chronos; Moirai; neural forecasting.




                                                                                                    1
Contents
1 Introduction                                                                                        4

2 Related Work                                                                                        4

3 Methodology                                                                                         5
  3.1   Problem Formulation . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .    5
  3.2   Pretraining as an Inductive Prior . . . . . . . . . . . . . . . . . . . . . . . . . . . . .    7
  3.3 A PAC-Bayes Bound for Zero-Shot Transfer . . . . . . . . . . . . . . . . . . . . . . .           8
  3.4   Information-Theoretic Predictability Bounds . . . . . . . . . . . . . . . . . . . . . .        8
  3.5   Causal Capacity and Maximum Trading Utility . . . . . . . . . . . . . . . . . . . . .          9
  3.6   Operator-Theoretic View of Attention . . . . . . . . . . . . . . . . . . . . . . . . . . 10
  3.7   Spectral Gap and Mixing Time of Attention . . . . . . . . . . . . . . . . . . . . . . . 10
  3.8   Signatures and the Theory of Patching . . . . . . . . . . . . . . . . . . . . . . . . . . 11
  3.9   Information Geometry of Pretrained Forecasters . . . . . . . . . . . . . . . . . . . . 12
  3.10 Distribution Geometry of Forecast Scores . . . . . . . . . . . . . . . . . . . . . . . . 12
  3.11 Cross-Modality Reprogramming (Time-LLM) . . . . . . . . . . . . . . . . . . . . . . 13
  3.12 TimeGPT and TimeGPT Long Horizon . . . . . . . . . . . . . . . . . . . . . . . . . 14
  3.13 TimesFM-2.5: Decoder-Only Foundation Model . . . . . . . . . . . . . . . . . . . . . 15
  3.14 Moirai-2.0: Decoder-Only Universal Transformer . . . . . . . . . . . . . . . . . . . . 15
  3.15 NBEATS . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 16
  3.16 NHITS . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 18
  3.17 PatchTST . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 19
  3.18 Chronos . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 19
  3.19 iTransformer . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 20
  3.20 KAN for Time Series . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 21
  3.21 Chronos-2: Time Series as Language Modelling . . . . . . . . . . . . . . . . . . . . . 22

4 Experimental Design                                                                                 22
  4.1   Data, targets, and benchmark scope . . . . . . . . . . . . . . . . . . . . . . . . . . . 22
  4.2   Models evaluated . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 23
  4.3   Context windows, training protocol, and reproducibility . . . . . . . . . . . . . . . . 24
  4.4   Metrics and statistical testing . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 25

5 Results                                                                                             27
  5.1 Aggregate findings . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 27
  5.2 Asset-level winners . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 28
  5.3   Benchmarks against naive baselines . . . . . . . . . . . . . . . . . . . . . . . . . . . . 29


                                                  2
  5.4 What the Diebold–Mariano results actually show . . . . . . . . . . . . . . . . . . . . 29

6 Discussion and Limitations                                                                30

7 Conclusion                                                                                31

A Full benchmark tables                                                                     32

B Reproducibility checklist                                                                 34




                                              3
1    Introduction
Time series analysis has long been a fundamental pillar of stochastic modelling, with its formal
foundations in autoregressive models dating back to Yule and Walker in the 1920s and 1930s,
and taking its modern form with the systematic ARMA framework of Box and Jenkins [1970].
Forecasting financial returns within this tradition is notoriously difficult: signal-to-noise ratios
are low, structural breaks are common, and even modest errors can erase any practical edge once
trading frictions are considered. Recent progress in pretrained sequence models has nevertheless
renewed interest in whether large-scale temporal pretraining can provide a better inductive bias
than training a separate model for each asset.
    This literature now contains two related but distinct strands. One strand adapts text large
language models (LLMs) to time series through reprogramming or prompting, as in Time-LLM [Jin
et al., 2024], LLM4TS [Chang et al., 2024], and PromptCast [Xue and Salim, 2023]. As emphasized
by Brown et al. [2020], LLMs such as GPT-4 [OpenAI, 2023] and Gemini [Team, 2024] exhibit
remarkable transfer-learning capabilities in few-shot and zero-shot settings, motivating the broader
hypothesis that pretrained sequence intelligence may transfer to temporal data. Building on our
previous findings regarding the efficacy of general-purpose Large Language Models adapted for
financial time series through reprogramming techniques [Alonso and Franklin, 2025], this benchmark
aims to extend that inquiry into the emerging class of models natively designed for temporal
data. A second strand develops dedicated time-series foundation models (TSFMs), including
TimeGPT [Garza et al., 2024], TimesFM [Das et al., 2024], Chronos [Ansari et al., 2024], Chronos-2
[Ansari et al., 2025], and Moirai-2.0 [Liu et al., 2025]. The present benchmark belongs much more
clearly to the second strand: most evaluated systems are pretrained time-series models rather than
reprogrammed text LLMs. For that reason, this paper uses the term pretrained TSFM throughout.
   The question studied here is practical. If a practitioner has only one return series per asset,
wants a 20-business-day forecast, and does not want to run heavy per-ticker model development, is
an out-of-the-box TSFM preferable to a train-from-scratch alternative? To answer that question,
we compare six pretrained TSFMs against five strong baselines: NBEATS [Oreshkin et al., 2020],
NHITS [Challu et al., 2022], PatchTST [Nie et al., 2023], iTransformer [Liu et al., 2024], and KAN
[Xu et al., 2024].
    The contribution of the paper is threefold. First, it provides a compact benchmark over two
return representations, five liquid equities, and a rolling-origin protocol, with detailed architectural
exposition of each evaluated model. Second, it reframes the evidence around pretrained time-series
models rather than generic “LLM” claims. Third, it separates statistical distinguishability from
directional superiority when interpreting Diebold–Mariano (DM) results, preventing sign confusion
relative to the random-walk benchmark.


2    Related Work
A related but distinct line of work adapts frozen text LLMs to time-series data through prompting or
reprogramming, as in Time-LLM [Jin et al., 2024], LLM4TS [Chang et al., 2024], and PromptCast
[Xue and Salim, 2023]. This literature motivates the broader hypothesis that sequence pretraining
can transfer across modalities, but it is not the empirical focus of this paper: we do not run a direct
Time-LLM or LLM-reprogramming experiment.
    The pretrained-TSFM literature is closer to the systems evaluated here. TimeGPT [Garza et al.,


                                                   4
2024] emphasizes transfer learning for zero-shot forecasting. TimesFM is a decoder-only foundation
model for time-series forecasting [Das et al., 2024]. Chronos casts forecasting as a language modeling
problem over quantized values [Ansari et al., 2024], while Chronos-2 extends that philosophy to a
broader universal-forecasting setting with multivariate and covariate support [Ansari et al., 2025].
Moirai-2.0 is a decoder-only foundation model built around quantile forecasting and efficiency
improvements [Liu et al., 2025].
    A complementary line of contemporaneous work asks the related but distinct question of how
far generic TSFM pretraining transfers to finance-specific data. Rahimikia et al. [2025] evaluate
zero-shot inference, fine-tuning, and pre-training from scratch for several TSFM families on a
broad global panel of excess-return observations. Their main finding is that off-the-shelf TSFMs
underperform standard ensemble and neural benchmarks in zero-shot and fine-tuning regimes, while
finance-native pretraining closes much of the gap and can produce stronger portfolio performance.
Our benchmark differs in scope—single-asset 20-business-day forecasts on five U.S. equities, rather
than next-day cross-sectional excess returns at the global level—but the two studies are mutually
informative. Theirs argues that domain-specific pretraining matters when the goal is cross-sectional
return prediction and portfolio formation; ours measures how the same off-the-shelf TSFMs fare
against train-from-scratch deep baselines for per-asset forecast error. The qualitative messages are
consistent: gains from generic TSFMs can be useful in a low-data per-asset setting, but they remain
limited and should not be confused with finance-specific economic outperformance.
    Against these pretrained models, the paper uses strong supervised baselines. NBEATS and
NHITS remain influential MLP-style decomposition models [Oreshkin et al., 2020, Challu et al., 2022].
PatchTST and iTransformer are modern transformer baselines that model temporal dependencies
in different ways [Nie et al., 2023, Liu et al., 2024]. KAN brings spline-based Kolmogorov–Arnold
parameterization to time-series prediction [Xu et al., 2024] and proves particularly relevant here
because it is the only train-from-scratch model that consistently breaks into the top tier.


3     Methodology
This section collects the architectural background of the evaluated systems. It begins with a shared
problem formulation, then describes each model individually. The exposition follows the canonical
references for each architecture and is provided to make the benchmark self-contained.


3.1   Problem Formulation

Fix a probability space (Ω, F, P) supporting a real-valued return process (rt )t∈Z adapted to its
natural filtration Ft = σ(rs : s ≤ t). For an asset return at horizon h ≥ 1 we seek a measurable
forecast                                                            
                                      r̂t+h = ft rt−L+1 , . . . , rt ,                        (1)
based on a context window of length L, where ft ranges over a class F of admissible predictors. In
our experiments h runs over 1, . . . , H with H = 20. For a strictly proper loss ℓ : R × R → R≥0 the
population risk and the Bayes-optimal predictor are
                                                    ⋆
                R(f ) = E ℓ ft (Ft ), rt+h        ,   ft,h ∈ arg min E[ℓ(g, rt+h ) | Ft ] .        (2)
                                                                g∈L0 (Ft )

The two losses that organize the analysis below are squared loss and absolute loss, with qualitatively
different optima.

                                                       5
Semimartingale framework. It is convenient to view (rt ) as the sequence of increments of a
                             P
discrete-time process Rt = s≤t rs adapted to (Ft ). By the Doob decomposition, Rt = Mt + At
splits uniquely into an (Ft )-martingale Mt with M0 = 0 and an (Ft−1 )-predictable process At of
locally bounded variation [Williams, 1991]. The martingale-difference hypothesis E[rt+h | Ft ] = 0
corresponds to A ≡ 0, in which case rt = ∆Mt is the increment of a pure martingale. Under this null
the random-walk benchmark introduced below is exactly the Bayes-optimal L2 predictor; departures
from the null—predictable drifts, regime-switching means, calendar effects—are precisely what
any non-trivial forecaster aims to exploit. Throughout this paper we work without imposing the
martingale-difference null on (rt ): the random walk is treated as a benchmark to beat, not as a
maintained hypothesis.

                                                                                            ⋆ (F ) =
Squared loss. For ℓ(r̂, r) = (r̂−r)2 , the Bayes-optimal predictor is the conditional mean ft,h  t
E[rt+h | Ft ], and the minimum risk equals the expected conditional variance E Var(rt+h | Ft ). Most
foundation-model training objectives target this loss, either directly (TimesFM, Moirai’s quantile
head specializes to a mean-like predictor at q = 0.5) or via a quantized likelihood that converges to
it under refinement (Chronos, Chronos-2).

Absolute loss. For ℓ(r̂, r) = |r̂ − r|, the Bayes-optimal predictor is the conditional        median
 ⋆
                                                                                        
ft,h (Ft ) = med(rt+h | Ft ), and the minimum risk equals E |rt+h − med(rt+h | Ft )| . This is the
reference for our reported MAE: any model whose conditional forecasts deviate systematically from
the conditional median pays a penalty in MAE that no amount of mean-targeting can recover.
Because most evaluated systems are trained to minimize a squared- or quantized-likelihood loss
rather than absolute loss, the metric and the training objective are deliberately not aligned, and the
benchmark therefore tests robustness to that misalignment alongside raw predictive skill.

The random-walk benchmark and two coinciding hypotheses. The zero-return random-
                RW ≡ 0 corresponds, on daily liquid-equity data, to two distinct hypotheses that
walk forecast r̂t+h
happen to coincide. First, under the martingale hypothesis E[rt+h | Ft ] = 0 it is Bayes-optimal
under squared loss. Second, when the unconditional median of rt+h is approximately zero (a good
empirical approximation for the assets and window used here) it is the unconditional minimizer of
E|rt+h |. Beating the random walk in MAE therefore requires a model to extract genuine conditional
information beyond the unconditional median: rescaling or recentering forecasts cannot move skill
from negative to positive without conditional signal.

A predictability bound.       The standard variance decomposition
                                                       
                          Var(rt+h ) = Var E[rt+h | Ft ] + E Var(rt+h | Ft )                      (3)
yields the population upper bound
                                                                 
                                         2     Var E[rt+h | Ft ]
                                  sup R (f ) =                   .                                (4)
                                   f              Var(rt+h )

For daily liquid-equity returns this bound is empirically very small: reported out-of-sample R2
values in the cross-sectional return-prediction literature are typically below 1% [Rahimikia et al.,
2025]. Equivalently, the MAE ratio between any feasible predictor and the random walk is bounded
below by a quantity close to one. The skill scores of order 10−3 reported in Section 5 should be
read against this ceiling rather than against an unrestricted benchmark.

                                                  6
Empirical risk minimization. In practice we replace population risk by an empirical analogue.
                         (i)    (i)
For a training sample {(x1:L , y1:H )}ni=1 the standard objective is
                                                  n X H
                                               1 X             (i)       (i) 
                                 R
                                 b n (f ) =              ℓ f (x1:L )h , yh ,                          (5)
                                              nH i=1 h=1

which for the reprogramming framework of Jin et al. [2024] specializes to the squared-error form
Lb = H1 H                2
          h=1 ∥Ŷh − Yh ∥F . For pretrained TSFMs deployed zero-shot, the inner minimization in
        P

Eq. (5) is replaced by direct evaluation at a fixed parameter θ̂pre ; the theoretical implications of
this replacement are the subject of Section 3.2.


3.2   Pretraining as an Inductive Prior

A useful theoretical lens for interpreting the benchmark is to view pretraining as a data-dependent
prior over predictor space. Let FΘ = {fθ : θ ∈ Θ} be a parametric family of forecasters and let
Dpre denote a generic pretraining corpus (in our setting, the diverse multi-domain corpora used
to train TimeGPT, TimesFM-2.5, Moirai-2.0, Chronos, and Chronos-2). A pretrained TSFM
corresponds to a parameter setting θ̂pre obtained by minimizing an empirical risk on Dpre , possibly
with regularization. In a Bayesian reading this defines an informative prior
                                                                            
                                 πpre (θ) ∝ π0 (θ) exp − npre R
                                                              b pre (θ) ;                             (6)

in a frequentist reading it identifies a low-dimensional submanifold of Θ around which the model
class’s effective complexity is much smaller than the nominal parameter count. Either reading
produces the same operational prediction: the variance of the estimator at θ̂pre is controlled by the
prior dispersion rather than by the unrestricted capacity of the architecture.

A small-sample generalization argument. The relevance for our small-data per-asset regime
is summarized by a generalization bound of the form
                                                             s             
                                                                  deff (FΘ ) 
                               R(fˆ) − min R(f ) ≤ O
                                                   e                          ,                      (7)
                                        f ∈FΘ                       nloc

where nloc is the effective number of local samples available for estimating fˆ and deff is an effective
complexity term (Rademacher, VC, or PAC-Bayes complexity, depending on the framing). For
locally trained baselines deff reflects the full capacity of the architecture; for a pretrained TSFM
evaluated zero-shot, deff is governed by the local dispersion of the pretraining prior πpre around θ̂pre ,
rather than by the full nominal parameter count. This dispersion may be much smaller than the
unrestricted complexity of the architecture, but it remains an assumption of the inductive-prior
argument rather than a quantity estimated in this benchmark. When nloc is small relative to the
unrestricted deff , Eq. (7) predicts the pretrained estimator to be favored not because it “knows
finance” but because its prior dispersion is a tighter fit for the available local sample size.

What this argument does not show. Two negative observations follow directly. First, domi-
nance of pretrained TSFMs in this regime does not isolate architectural quality: deff is conflated with
the pretraining prior πpre , so an architectural verdict over locally trained baselines is unwarranted
from rank alone. Second, the same argument predicts that a less financially relevant prior may still

                                                       7
outperform a high-capacity locally-trained model when nloc is small enough; the benchmark therefore
cannot establish that pretraining has captured finance-specific structure. The contemporaneous
evidence of Rahimikia et al. [2025]—that finance-native pre-training delivers substantial gains once
nloc scales to billions of observations—is exactly the regime in which the prior contribution to Eq. (7)
becomes negligible and domain alignment of Dpre becomes the binding constraint.


3.3   A PAC-Bayes Bound for Zero-Shot Transfer

A more refined generalization argument tailored to the pretraining setting is the PAC-Bayes bound
[McAllester, 1999, Catoni, 2007]. Let πpre be the prior over Θ defined in Section 3.2, let Q be a
posterior over Θ inferred from local financial data Dloc of size nloc , and let fˆ be the corresponding
randomized predictor. For a loss ℓ ∈ [0, B] and confidence δ ∈ (0, 1), with probability at least 1 − δ
over the draw of Dloc ,
                                                        s
                                                             B2                     
                                                                   KL Q πpre + log 1δ .
                                                                        
                  Ef ∼Q R(f ) ≤ Ef ∼Q R
                                      b n (f ) +                                                     (8)
                                                            2 nloc

    Two regimes have qualitatively different interpretations of Eq. (8). Pure zero-shot deployment is
best read as the small-variance limit of a posterior concentrated near the pretrained parameter θ̂pre .
In a continuous parameter space, a literal Dirac posterior δθ̂pre is generally singular with respect to a
continuous prior and can yield an infinite KL divergence, so the zero-shot PAC-Bayes interpretation
is heuristic unless one works with a discrete parameter space or an explicitly smoothed posterior such
as Qτ = N (θ̂pre , τ 2 I). Under such a smoothed approximation, the complexity term measures how
concentrated the pretraining prior is around the deployed parameter. Local fine-tuning constructs
Q from πpre via gradient updates on Dloc ; the generalization gap then depends on how far Q is
allowed to move from πpre in KL divergence before the second term dominates the empirical-risk
reduction in the first.
    Eq. (8) formalizes the intuition that fine-tuning on a small per-asset window cannot move Q
very far from πpre without paying an unsustainable generalization penalty: the maximum allowable
KL budget scales as nloc , so the available space of fine-tuned posteriors collapses for small local
samples. This is consistent with the Rahimikia et al. [2025] observation that fine-tuning yields only
marginal improvements over zero-shot inference: the KL constraint is binding. Pre-training from
                                                                                     fin , relaxing the
scratch on financial data, by contrast, replaces πpre with a finance-aligned prior πpre
KL constraint by changing the reference measure. The bound predicts the gap to close exactly
where the empirical evidence reports it closing.


3.4   Information-Theoretic Predictability Bounds

The variance bound of Eq. (4) has an information-theoretic counterpart that does not require finite
second moments and that exposes the small budget of bits available to any predictor on daily
liquid-equity returns. Let I(rt+h ; Ft ) denote the (Shannon) mutual information between the future
return and the past σ-field, and let h(rt+h ) denote the differential entropy of rt+h . The classical
rate–distortion lower bound on minimum mean-squared error [Cover and Thomas, 2006] gives
                                        1
                            MSE⋆ ≥
                                                                         
                                           exp 2 h(rt+h ) − I(rt+h ; Ft ) ,                          (9)
                                       2πe



                                                    8
with equality under jointly Gaussian conditioning. Specializing to the joint-Gaussian case yields the
closed-form ceiling
                                      2                           
                                1 − Rmax   = exp − 2 I(rt+h ; Ft ) ,                             (10)
so an out-of-sample Rmax 2    of 1% corresponds to mutual information of roughly 0.005 nats per
forecast—a small fraction of one bit. This is a quantitative restatement of the difficulty of return
forecasting: the past simply does not carry many bits of information about the future, and any
sufficiently expressive architecture that can recover those bits will perform comparably. Differences
between models in our benchmark are competing for a small information budget rather than for
architectural superiority on a high-information task.
    Two refinements bear on the empirical results. First, returns are heavy-tailed, so the Gaussian
closed form Eq. (10) understates the achievable MSE reduction relative to the general Eq. (9): a
forecaster that recovers non-Gaussian conditional structure—through quantized likelihoods (Chronos,
Chronos-2) or quantile heads (Moirai-2.0)—can in principle exceed the Gaussian ceiling without
violating the information bound. Second, the conditional information I(rt+h ; Ft ) is itself non-
stationary across regimes: returns during volatility shocks plausibly carry more bits about the
immediate future than returns during calm periods, so the rolling-origin protocol used in Section 4.4
probes a moving average over heterogeneous information levels. The cautious interpretation of skill
scores in Section 5 is partly grounded in this regime mixing.


3.5   Causal Capacity and Maximum Trading Utility

The information bound of Section 3.4 sharpens into a statement about achievable economic utility.
Suppose an investor with log utility chooses positions πt in the asset and a risk-free instrument
based on Ft . The Kelly–Cover growth-optimal strategy [Kelly, 1956, Cover and Thomas, 2006]
maximizes the conditional expected log-return,

                            πt⋆ = arg max E log 1 + π(rt+h − rf )
                                                                        
                                                                        Ft ,                       (11)
                                        π

and its asymptotic almost-sure growth rate W ⋆ is the maximum log-wealth achievable by any Ft -
adapted strategy. Algoet and Cover [1988] show W ⋆ is bounded above by an information-theoretic
capacity:
                                                        1
                       W ⋆ ≤ C Ft → rt+h := lim sup I Ftn → rt+h  n 
                                           
                                                                      ,                    (12)
                                                  n→∞ n

where the right-hand side is the directed (causal) information from the conditioning sequence to the
return sequence in the sense of Kramer [1998], Permuter et al. [2011], and reduces to the ordinary
mutual information I(rt+h ; Ft ) when Ft contains no past values of r.
    Eq. (12) ties the small-information regime of Section 3.4 directly to a small economic edge: if the
Shannon mutual information I(rt+h ; Ft ) is on the order of 0.005 nats, the directed-information ceiling
C is bounded by the same order, and the maximum log-growth attainable by any forecaster–strategy
pair before transaction costs is correspondingly small. Statistical-significance claims for one model
over another do not, by themselves, translate into proportionally large trading edges, because
both sides of any such comparison are bounded by the same capacity. The MAE skill scores of
order 10−3 reported in Section 5 are consistent with what Eq. (12) permits; they do not prove an
exploitable trading advantage, and the discussion of investment-utility limitations in Section 6 uses
this argument as theoretical backup.




                                                   9
3.6   Operator-Theoretic View of Attention

Self-attention—the central computational primitive of TimeGPT, TimesFM-2.5, Moirai-2.0, Chronos,
Chronos-2, PatchTST, and iTransformer—admits a clean reading as a kernel integral operator on a
space of token-valued functions. For a sequence of N tokens with embeddings {xi }N         d
                                                                                    i=1 ⊂ R and
learnable projections WQ , WK , WV ∈ Rdk ×d , scaled-dot-product attention produces
                    N                                                                    √ 
                    X                                               exp ⟨WQ xi , WK xj ⟩/ dk
          (Ax)i =         κ(xi , xj ) WV xj ,       κ(xi , xj ) = PN                        √ .   (13)
                    j=1                                            ℓ=1 exp ⟨WQ xi , WK xℓ ⟩/ dk

In the continuum limit N → ∞ with {xi } replaced by a continuous field f : X → Rd and the
empirical sum by an integral against an underlying measure µ on the index set,
                                                Z
                                 (Af )(x) =          κ(x, y) (WV f )(y) µ(dy),                     (14)
                                                X

whose normalized kernel component is row-stochastic. After the value projection, residual connection,
normalization, and feed-forward layers of an actual transformer block, the full block is not itself a
Markov chain; the Markov-kernel language below is therefore an analogy for the attention weights
rather than an exact probabilistic model of the entire network. A transformer block is then the
residual map f 7→ f + σ(Af + b) for a coordinate-wise nonlinearity σ, and a stack of L such blocks
defines a discrete-time flow

                           fℓ+1 = fℓ + σ(Aℓ fℓ + bℓ ),          ℓ = 0, 1, . . . , L − 1,           (15)

which can be interpreted heuristically as an explicit Euler discretization of a non-autonomous flow
f˙ = σ(At f + bt ) on a separable Hilbert space.
    Two consequences bear on the benchmark, provided this operator view is kept heuristic. First,
spectral properties of the input-dependent attention kernels can influence long-range mixing: wider
gaps in the normalized attention kernel correspond to faster token-to-token averaging, while
near-block-diagonal patterns slow information flow across regions of the sequence. Second, the depth-
versus-width tradeoff acquires a numerical-analysis interpretation as a stability-versus-resolution
tradeoff in the underlying ODE: too few blocks under-resolve the flow; too many push the explicit-
Euler discretization toward instability unless residual scaling is adjusted accordingly. PatchTST,
iTransformer, and the foundation-model backbones differ primarily in the choice of A—along the
time axis (PatchTST, decoder-only TSFMs) versus across variates (iTransformer)—and in the
discretization step size implicitly set by residual scaling. None of these design choices is uniformly
optimal, which is consistent with the no-universal-winner pattern of asset-level results in Section 5.


3.7   Spectral Gap and Mixing Time of Attention

The Markov-kernel language of Section 3.6 should be read as a diagnostic analogy, not as a theorem
about the fixed behaviour of the models evaluated here. Actual transformer attention kernels vary by
input, layer, and head; they are generally non-reversible; and the benchmark does not estimate their
spectra. With that caveat, a single attention head for one input sequence defines a row-stochastic
matrix K ∈ RN ×N over tokens. If that matrix is irreducible and aperiodic, it has at least one
stationary distribution µ, and in the reversible idealization its spectral gap controls the mixing
bound
                                                   1         1
                                    tmix (ε) ≤         log        ,                             (16)
                                                1 − λ2     µmin ε

                                                        10
where λ2 is the second-largest eigenvalue in modulus. For non-reversible attention matrices, analogous
statements use singular values, pseudo-spectral quantities, or conductance bounds rather than this
simple eigenvalue expression.
    Under the reversible idealization, Cheeger’s inequality [Lawler and Sokal, 1988] relates the gap
to the conductance of the kernel,
                                                                        Φ(K)2
                                 P
                                           / µ(x) K(x, y)
                                    x∈S, y ∈S
          Φ(K) :=      min                                    ,               ≤ 1 − λ2 ≤ 2 Φ(K).   (17)
                    S:µ(S)≤1/2                 µ(S)                       2
A near-block-diagonal attention pattern has small conductance and therefore slow cross-block
information flow in this simplified model. Conversely, dense global attention permits faster token
mixing. These observations are useful for interpreting why deep decoder-only TSFMs may carry
long-context information more comfortably than shallow locally trained models, but the present
benchmark does not measure attention gaps and therefore cannot use them as causal evidence for
any particular model ranking. The empirical conclusion remains narrower: architectural depth
and long-context machinery may matter less in daily return forecasting than in high-information
domains because the available conditional information in the return series is itself small.

3.8   Signatures and the Theory of Patching

The patching mechanism shared by PatchTST, TimesFM-2.5, and Moirai-2.0 admits a rough-paths
interpretation that clarifies what information patches do and do not encode. Given a continuous
path X : [0, T ] → Rd , the signature of X is the formal series of iterated integrals
                                         Z t            Z                               
                     S[s,t] (X) =    1,         dXu1 ,                 dXu1 ⊗ dXu2 , . . . ,       (18)
                                           s             s<u1 <u2 <t

and the celebrated theorem of Chen [1958] together with the extension of Lyons [1998] establishes that
the signature characterizes X up to tree-like equivalence and that any continuous path-dependent
functional can be approximated arbitrarily well by a linear functional of a sufficiently high-order
signature truncation [Chevyrev and Kormilitzin, 2016].
    A patch of length P on a sampled path is not automatically a path signature. It is a finite
vector of local observations that can be interpreted as a learned summary of path increments and
within-patch shape. A linear patch projection can, in principle, approximate low-order functionals
of those local increments, including quantities reminiscent of truncated signatures, but the model is
not constrained to compute signature coordinates and the benchmark does not test whether it does
so. Likewise, channel independence and instance normalization help stabilize scale and distribution
shift, but they do not by themselves enforce the reparameterization invariance associated with
rough-path signatures. From this viewpoint, patch length P and embedding dimension D control
the amount of local path information made available to the transformer, not a literal signature
truncation level.
    Two practical implications follow at the level of representation design. First, very short patches
expose fine local variation but increase the number of tokens and force the transformer stack
to aggregate local structure through attention. Second, long patches reduce token count but
compress more observations into a single embedding, which can discard within-patch detail when
the embedding capacity is limited. The standard PatchTST default of P = 16 with D = 128 is one
reasonable point in this compression–resolution tradeoff; we use the canonical configuration without
tuning, which is consistent with our as-used framing in Section 3 but should be treated as a design
choice rather than an optimized setting.

                                                         11
3.9    Information Geometry of Pretrained Forecasters

The parameter manifold of any probabilistic forecaster carries a natural Riemannian metric, the
Fisher information metric
                                                ∂ log pθ (y | x) ∂ log pθ (y | x)
                                                                               
                            gij (θ) = Epθ                                         ,                (19)
                                                      ∂θi              ∂θj
which equips (Θ, g) with a Riemannian structure and induces the natural-gradient direction g −1 ∇L
that is invariant under smooth reparameterization [Amari, 1998]. Two specializations are relevant
here.

Categorical likelihoods (Chronos, Chronos-2). For the B-bin quantized likelihood pθ (z = i |
x) = πi (θ; x), the Fisher metric is the multinomial information matrix
                                                     B
                                                     X 1 ∂πk ∂πk
                                      gij (θ) =                         ,                          (20)
                                                     k=1
                                                           πk ∂θi ∂θj

whose curvature concentrates near the boundary of the probability simplex. In practical terms,
models that place near-deterministic mass on a single quantile bin (the regime relevant for tail
forecasts on volatile days) sit in high-curvature regions of (Θ, g) where small parameter perturbations
produce large changes in conditional distribution.

Pinball-based quantile heads (Moirai-2.0). The pinball loss is not a likelihood, but its
second-order behaviour around the conditional q-quantile defines an analogous geometry in which
the local metric is concentrated near the conditional median (q = 0.5) and degrades smoothly
toward the tails. The natural-gradient analogue here is the pre-conditioner defined by the second
derivative of the dual cumulant of the pinball loss; we do not compute it explicitly, but it explains
why quantile-head forecasters are typically well-behaved for central quantiles and progressively less
well-conditioned for extreme ones.

Connection to the inductive-prior view. The pretraining prior πpre (θ) has effective support
concentrated on a low-dimensional submanifold of (Θ, g), and the Fisher-geodesic distance from
θ̂pre to its nearest finance-optimal parameter setting controls how much benefit a small amount
of fine-tuning could in principle deliver. The empirical observation of Rahimikia et al. [2025] that
fine-tuning yields only marginal improvements over zero-shot, while pre-training from scratch on
financial data yields substantial gains, is consistent with the corresponding Fisher-distance picture:
the generic pretrained submanifold is far enough from the finance-optimal submanifold, relative
to the Fisher length scale, that local moves do not bridge it. We do not estimate Fisher distances
for the systems in this benchmark, but the conceptual implication is direct: genuinely improving
zero-shot transfer to finance requires either extending Dpre to include financial data or re-pretraining
from scratch on a finance-aligned corpus. Both operations modify πpre , not the local fine-tuning
step.


3.10    Distribution Geometry of Forecast Scores

The quantile-score discussion for Moirai-2.0 is best expressed as an integrated quantile-loss or CRPS
geometry, with Wasserstein distance used only as a related but distinct comparison metric. For

                                                       12
p ≥ 1, the p-Wasserstein distance between probability measures F, G on R with finite p-th moments
has the one-dimensional quantile form
                                             Z 1
                                                                    p
                                       p
                              Wp (F, G) =          F −1 (q) − G−1 (q) dq.                         (21)
                                               0

When G = δy and p = 1, this becomes W1 (F, δy ) = E|X − y|. CRPS instead subtracts the dispersion
term in Eq. (35); it rewards both calibration and sharpness and is a strictly proper scoring rule for
the full predictive distribution. Thus the benchmark should not describe quantile-head models as
minimizing Wasserstein score in the literal sense. The accurate statement is that finite quantile
training approximates an integrated pinball-loss objective, which is equivalent to CRPS up to the
normalization convention in Eq. (34).
   Wasserstein geometry remains useful as an auxiliary language for comparing forecast distributions.
For example, in Wasserstein-2 space, W2 (R) [Otto, 2001, Villani, 2003], geodesics interpolate
predictive distributions linearly in quantile space:

                        Ft−1 (q) = (1 − t) F0−1 (q) + t F1−1 (q),    t ∈ [0, 1].                  (22)

For Gaussian forecast distributions F = N (µF , σF2 ) and G = N (µG , σG
                                                                       2 ), Eq. (21) specializes to


                              W2 (F, G)2 = (µF − µG )2 + (σF − σG )2 ,                            (23)

which separates location error from scale error. This decomposition is helpful for intuition: point-
forecast baselines mainly target the location component, whereas probabilistic or quantile models
can represent both location and conditional dispersion. It does not imply that the MAE rankings in
this paper are Wasserstein rankings, because the reported benchmark metric is point MAE.
    This distinction matters for interpretation. Moirai-2.0’s wins on GOOG and on the AMZN
log-return task may be consistent with a probabilistic model benefiting from conditional-dispersion
information, but the evidence is suggestive rather than conclusive. Other features of the evaluation
window—idiosyncratic events, volatility clustering, and asset-specific valuation dynamics—may also
explain these results. A direct test of the geometric hypothesis would require evaluating probabilistic
scores such as CRPS, calibration curves, and quantile coverage, none of which is part of the present
MAE-only benchmark.


3.11    Cross-Modality Reprogramming (Time-LLM)

The cross-modality reprogramming approach pioneered by Time-LLM [Jin et al., 2024] leverages
the high-dimensional latent representations of frozen LLMs, such as Llama [Touvron et al., 2023] or
GPT-2 [Radford et al., 2019], and adapts them for temporal sequence analysis. The adaptation
typically consists of three stages:

1. Input transformation and patching. Following the channel-independence strategy [Nie et al.,
   2023], each multivariate series is treated as N independent univariate sequences X (i) ∈ R1×T .
   These sequences undergo normalization (typically RevIN) and are segmented into overlapping
   patches to preserve local temporal dependencies and reduce input dimensionality.

2. Reprogramming with text prototypes. To bridge continuous numerical data and the discrete
   token space of the LLM, a set of learned text prototypes aligns the source temporal modality
   with the target linguistic modality, so that the frozen backbone can “interpret” time-series
   patterns as semantic sequences.

                                                   13
3. Prompt-as-Prefix and frozen backbone. Task-specific instructions in natural language (e.g.
   “forecast the next 20 days of stock returns”) are prepended to the reprogrammed embeddings
   and processed by the pretrained transformer layers, which are kept frozen.

Only the lightweight input transformation layers, the text prototypes, and the output projection head
are updated during training, which makes this approach parameter-efficient but keeps Time-LLM
conceptually adjacent to, rather than part of, the empirical benchmark below.




Figure 1: A concrete Prompt-as-Prefix example that conditions a frozen LLM on task context, instructions,
and summary statistics of the input series [Jin et al., 2024].


3.12    TimeGPT and TimeGPT Long Horizon

TimeGPT [Garza et al., 2024] is a foundation model designed for time-series forecasting that
leverages transfer learning to perform zero-shot inference. It provides a mapping fθ : X 7→ Y with
X = {y[0:t] , x[0:t+h] } (historical values and exogenous covariates) and Y = {y[t+1:t+h] } for forecast
horizon h:
                               P(y[t+1:t+h] | y[0:t] , x[0:t+h] ) = fθ (y[0:t] , x[0:t+h] ).        (24)
The architecture is a Transformer encoder–decoder with self-attention and local positional encoding.
TimeGPT was trained on over 100 billion data points spanning diverse frequencies and domains.
Reported performance is typically scale-independent, using relative Mean Absolute Error (rMAE)
and relative Root Mean Square Error (rRMSE) against a Seasonal Naive baseline:
                                                            v
                      Pn    Ph                              u Pn Ph
                             |yi,t − ŷi,t |                             (yi,t − ŷi,t )2
           rMAE = Pni=1Pht=1                        rRMSE = t Pni=1Pht=1
                                                            u
                                      base
                                             ,                                    base 2
                                                                                          .         (25)
                   i=1  t=1 |yi,t − ŷi,t |                         i=1   t=1 (yi,t − ŷi,t   )

In TimeGPT Long Horizon (TimeGPT-LH) scenarios, uncertainty is quantified through a non-
parametric conformal prediction framework. Rolling forecasts on the latest available data estimate

                                                   14
errors and yield prediction intervals without strict distributional assumptions, which is useful for
the heavy-tailed behaviour common in financial datasets.


3.13    TimesFM-2.5: Decoder-Only Foundation Model

TimesFM [Das et al., 2024] is a decoder-only transformer architecture designed for high-accuracy
zero-shot forecasts. It is pretrained on approximately 100 billion time points, including real-world
data from Google Trends and Wiki Pageviews, and synthetic data from ARMA processes and
seasonal-trend decompositions.
   The model treats time-series segments as tokens via a patching mechanism. Given an input
sequence y1:L , the data are divided into contiguous, non-overlapping patches of length p. The j-th
patch yj = yp(j−1)+1:pj is processed by an input residual block to produce

                          tj = InputResidualBlock(ȳj ⊙ (1 − m̄j )) + P Ej ,                     (26)

where m̄j is a binary padding mask and P Ej is the j-th positional encoding. The output token is
produced by a causal stack,

                          oj = StackedTransformer((t1 , ṁ1 ), . . . , (tj , ṁj )),             (27)

and the subsequent h time points after the j-th patch are generated by an output residual block:

                               ŷpj+1:pj+h = OutputResidualBlock(oj ).                           (28)

Training minimizes the mean squared error across all predicted patches in a mini-batch:
                                        N
                                     1 X
                               L=          MSE(ŷpj+1:pj+h , ypj+1:pj+h ).                       (29)
                                     N j=1

A distinctive feature is that the output patch length h can exceed the input patch length p, reducing
the number of autoregressive steps required at inference for long-horizon forecasting.


3.14    Moirai-2.0: Decoder-Only Universal Transformer

Moirai-2.0 [Liu et al., 2025] transitions from a masked-encoder to a decoder-only architecture. It is
trained on roughly 36 million time series (approximately 295 billion observations) and is optimized
for both probabilistic accuracy and inference efficiency.
    Univariate series are partitioned into T contiguous, non-overlapping patches. To avoid future
information leakage, instance-normalization statistics are computed solely from the first 30% of the
sequence. Each patch x̂i is mapped to a d-dimensional embedding via a residual block with SiLU
activation:
                                  ti = SiLU(W (x̂i ) + b) + x̂i ∈ Rd .                          (30)
A core design choice is the replacement of mixture-distribution outputs with quantile forecasting.
The model predicts nq = 9 quantile levels Q = {0.1, 0.2, . . . , 0.9} by minimizing the pinball loss
                                              
                                              q(y − ŷ (q) )          if yt ≥ ŷt ,
                                                                                    (q)
                                   (q)             t     t
                           lq (yt , ŷt ) =                                                      (31)
                                              (1 − q)(ŷ (q) − yt )        (q)
                                                                       if ŷt     > yt .
                                                             t



                                                        15
The total objective averages this loss across quantiles and time steps H in K predicted patches:
                            H Xh
                       1 X                      (q)                    (q)
                                                                                  i
                 LQ =              q max(yt − ŷt , 0) + (1 − q) max(ŷt − yt , 0) .                    (32)
                      H|Q| t=1 q∈Q

For long horizons, Moirai-2.0 generates forecasts for ntoken future patches simultaneously to reduce
error accumulation. At inference, an autoregressive multi-quantile decoding strategy—conceptually
similar to a beam search of depth two—expands and collapses forecast candidates back into the
target quantile set, preserving uncertainty estimates.

Pinball loss as a strictly proper scoring rule. The pinball loss ℓq (y, ŷ (q) ) = max{q(y −
ŷ (q) ), (q − 1)(y − ŷ (q) )} is, up to affine equivalence, the unique loss function whose population
minimizer over ŷ (q) is the conditional q-quantile of Y [Koenker, 2005]. Pointwise consistency
therefore implies that any forecaster trained to minimize pinball loss at a level q produces, at the
population minimum, the conditional q-quantile of the response.
   When predictions ŷ (q1 ) ≤ · · · ≤ ŷ (qK ) are produced for ordered levels q1 < · · · < qK , the average
pinball loss
                                                         K
                                                      1 X
                                      ℓ̄ y, ŷ (·) =        ℓqk y, ŷ (qk )
                                                                           
                                                                                                         (33)
                                                      K k=1
is a finite-sample approximation to the continuous ranked probability score (CRPS),
                                   Z                                 Z 1
                                                          2
                                                                           ℓq y, F −1 (q) dq,
                                                                                        
                 CRPS(F, y) =           F (z) − 1{z ≥ y} dz = 2                                         (34)
                                    R                                 0

which is a strictly proper scoring rule for one-dimensional predictive distributions [Gneiting and
Raftery, 2007]. CRPS is closely related to the integrated quantile loss, but it is not equal to the
Wasserstein-1 distance from F to a point mass. If X, X ′ ∼ F independently, then
                                       1
                CRPS(F, y) = E|X − y| − E|X − X ′ |,              W1 (F, δy ) = E|X − y|.               (35)
                                       2
The second term in Eq. (35) is the sharpness correction that makes CRPS a proper distributional
score rather than a pure distance to the realized observation. Moirai-2.0’s quantile head is therefore
optimizing a discrete approximation to an integrated quantile/CRPS objective whose population
minimum is achieved by the conditional law of the response. The non-crossing constraint enforced
by the autoregressive multi-quantile decoder is the operational analogue of imposing a monotone
F −1 ; without monotonicity, the predicted quantiles may fail to define a valid predictive distribution.


3.15    NBEATS

Oreshkin et al. [2020] propose a basic building block with a fork architecture. The ℓ-th block accepts
an input xℓ and produces two outputs: x̂ℓ (the backcast) and ŷℓ (the forward forecast).




                                                     16
                                           Figure 2: NBEATS architecture.




                                              Source: Oreshkin et al. [2020].



    The first block in the model takes a history lookback window as its input xℓ , typically of length
2H to 7H. For subsequent blocks the input is the residual output from preceding blocks. Each
block has two parts: a fully connected network that produces forward θℓf and backward θℓb expansion
coefficients, and basis layers gℓf , gℓb that project those coefficients onto basis functions to generate ŷℓ
and x̂ℓ . The first part is described by

                                                 hℓ,1 = FCℓ,1 (xℓ ),
                                                 hℓ,2 = FCℓ,2 (hℓ,1 ),
                                                 hℓ,3 = FCℓ,3 (hℓ,2 ),
                                                 hℓ,4 = FCℓ,4 (hℓ,3 ),
                                                       θℓb = LINEARbℓ (hℓ,4 ),
                                                   θℓf = LINEARfℓ (hℓ,4 ),

where each FC layer applies a ReLU non-linearity. The second part maps the expansion coefficients
to outputs:

                              dim(θℓf )                                              dim(θℓb )
                                           f
                                               vif ,
                                X                                                      X
                                                                                                  b
                      ŷℓ =               θℓ,i                               x̂ℓ =               θℓ,i vib .
                                i=1                                                    i=1




                                                                17
3.16    NHITS

Challu et al. [2022] build upon NBEATS with multi-rate sampling of the input signal and multi-scale
synthesis of the forecast, yielding a hierarchical forecast construction that reduces computational
demands while improving long-horizon accuracy.

                                    Figure 3: N-HiTS architecture.




                                      Source: Challu et al. [2022].



   Like NBEATS, NHITS performs local nonlinear projections onto basis functions across multiple
blocks, each comprising an MLP that generates backcast and forecast coefficients. Blocks are
organized into stacks, each specializing in a distinct characteristic of the data with its own set of
basis functions. A MaxPool layer is introduced at the input of each block ℓ,
                                    (p)
                                   yt−L:t,ℓ = MaxPool(yt−L:t,ℓ , kℓ ),                             (36)

so that larger kernel sizes kℓ remove high-frequency components and force the block to focus on
large-scale, low-frequency content. After subsampling, each block produces a hidden vector hℓ and
forward and backward coefficients:
                                                        (p)
                                          hℓ = MLPℓ (yt−L:t,ℓ ),
                                          θℓf = LINEARf (hℓ ),
                                          θℓb = LINEARb (hℓ ).

To handle long horizons, NHITS uses hierarchical interpolation: the dimensionality of the forward
interpolation coefficients is controlled by an expressiveness ratio rℓ , with |θ|fℓ = ⌈rℓ H⌉. A temporal
interpolation function g recovers the full horizon, and the final forecast sums the outputs of all
blocks while backcast residuals are subtracted from inputs of subsequent hierarchy levels.

                                                   18
3.17    PatchTST

Nie et al. [2023] propose PatchTST for multivariate time-series forecasting with a lookback window
L, using a vanilla Transformer encoder as backbone.

                  Figure 4: PatchTST illustrative multivariate forecasting case study.




                                         Source: Nie et al. [2023].


                                                   (i)
   A univariate series of length L, denoted x1:L for i = 1, . . . , M , is fed into the backbone under
                                                                                 (i)      (i)
a channel-independence scheme and produces prediction results x̂(i) = (x̂L+1 , . . . , x̂L+T ) ∈ R1×T .
Each series is partitioned into (possibly overlapping) patches of length P with stride S, yielding
         (i)
patches xp ∈ RP ×N where N is the number of patches; this reduces the number of input tokens
from L to approximately L/S and enables longer histories to be processed.
   Patches are mapped to the latent dimension D via a trainable linear projection Wp ∈ RD×P
with a learnable additive positional encoding Wpos ∈ RD×N . Multi-head attention then operates on
these tokens:
                                     (i) ⊤
                                       
                                                           (i)    (i)       (i)
                                    Oh       = Attention(Qh , Kh , Vh )
                                                          (i)    (i)⊤
                                                                        !
                                                       Qh Kh                  (i)
                                             = Softmax   √                  Vh .
                                                           dk

The multi-head block uses BatchNorm and a feed-forward network with residual connections,
producing z (i) ∈ RD×N ; a flatten plus linear head produces the final prediction x̂(i) . The training
loss is
                                           M
                                       1 X      (i)
                              L = Ex         ∥x̂L+1:L+T − xL+1:L+T ∥22 .                          (37)
                                      M i=1
An instance-normalization technique zero-means and unit-scales each series before patching, adding
the statistics back to the output to mitigate train–test distribution shift.


3.18    Chronos

Ansari et al. [2024] introduce Chronos, a framework that adapts existing language-model architectures
and training procedures to probabilistic time-series forecasting. The key step is tokenizing real-
valued time series via scaling and quantization. Given x1:C+H = [x1 , . . . , xC+H ], mean scaling gives
x̃i = xi /s with s = C1 C  i=1 |xi |. Quantization with B bin centers c1 < · · · < cB and B − 1 edges bi
                         P




                                                     19
maps scaled values to discrete tokens:
                                     
                                     
                                     
                                     
                                       1      if − ∞ ≤ x < b1 ,
                                     
                                     2
                                     
                                              if b1 ≤ x < b2 ,
                            q(x) =     ..                                    d(j) = cj .             (38)
                                     
                                     
                                     
                                       .
                                     
                                       B      if bB−1 ≤ x < ∞,
                                     


Chronos uses both encoder–decoder (T5) and decoder-only (GPT-2) backbones, adjusting only the
vocabulary size to match B. The categorical objective is

                                  X |V
                                  H+1 Xts |

                       ℓ(θ) = −               1zC+h+1 =i log pθ (zC+h+1 = i | z1:C+h ).              (39)
                                  h=1 i=1

Forecasts are generated by autoregressive sampling, followed by dequantization and inverse scaling.
To address the relative scarcity of high-quality training data, Chronos uses two augmentation
strategies: TSMix, which creates convex combinations of k randomly sampled series with Dirichlet-
sampled weights λi ,
                                                          k
                                                          X          (i)
                                              x̃TSMix
                                                1:l   =         λi x̃1:l ,                           (40)
                                                          i=1

and KernelSynth, which samples synthetic time series from Gaussian processes with composite
kernels built from linear, RBF, and periodic bases.

A rate–distortion view of tokenization. The two-stage encoding—mean scaling followed by
B-level scalar quantization—is a lossy compression map with rate log2 B bits per token. Under
standard high-resolution arguments, quantization with bin width ∆ on a smooth density incurs mean-
squared distortion of order ∆2 /12, so the choice of B trades expressiveness against representational
error: doubling B adds one bit of rate and reduces distortion by a factor of four. For mean-scaled
equity returns, which concentrate near zero with heavy tails, quantization error is small in the
central mass and larger in the tails, where extreme returns map to a few boundary bins and are
forecast only at bin resolution. This asymmetry is one mechanism by which Chronos and Chronos-2
can be ranking-competitive in our benchmark without producing dramatic absolute-error gains:
the conditional categorical distribution over the central bins is well-calibrated, while tail forecasts
collapse onto coarse bin centers and contribute disproportionately to MAE on high-volatility days.


3.19    iTransformer

Liu et al. [2024] introduce iTransformer, an approach for multivariate time-series forecasting that
predicts Y = {xT +1 , . . . , xT +S } ∈ RS×N from historical observations X = {x1 , . . . , xT } ∈ RT ×N .
Unlike most transformer-based models that treat multiple variates at a single time point as tokens,
iTransformer views the entire time series of each variate as a single token. The forecasting pipeline
for variate n is

                                  hn0 = Embedding(X:,n ),
                              Hl+1 = TrmBlock(Hl ),               l = 0, . . . , L − 1,
                               Ŷ:,n = Projection(hnL ),


                                                       20
where H = {h1 , . . . , hN } ∈ RN ×D . Embedding and projection are both implemented as MLPs.
Layer normalization is applied per variate token,
                                              (                                            )
                                                   h − Mean(hn )
                       LayerNorm(H) =                p           n = 1, . . . , N              ,   (41)
                                                       Var(hn )

which mitigates oversmoothing when variates have different distributions. Self-attention operates
across variates,
                               Ai,j = (QK⊤ / dk )i,j ∝ qi⊤ kj ,
                                             p
                                                                                             (42)
so that the model explicitly weights correlated variates. The implementation used in this benchmark
follows Liu et al. [2024].


3.20    KAN for Time Series

Xu et al. [2024] introduce Kolmogorov–Arnold Networks (KAN), grounded in the Kolmogorov–Arnold
representation theorem:                                        
                                                       2n+1
                                                        X            n
                                                                     X
                              f (x1 , . . . , xn ) =          Φq         ϕq,p (xp ) .            (43)
                                                        q=1         p=1

In KAN, traditional linear weights are replaced by spline-parametrized univariate functions, and
activation functions are learned on the edges rather than at the nodes. A KAN layer is

                            Φ = {ϕq,p | p = 1, . . . , nin , q = 1, . . . , nout },                (44)

with deeper architectures obtained by composition:

                              KAN(x) = (ΦL−1 ◦ ΦL−2 ◦ · · · ◦ Φ0 )(x).                             (45)

Two specializations are relevant here. T-KAN handles univariate series with
                                                                                
                                           2n+1
                                            X               n
                                                            X
                                Ŝt+T =            Φq           ϕq,p (St−h+p ) ,                 (46)
                                             q=1          p=1

while MT-KAN extends the framework to multivariate settings:
                                                                                    
                                       2n+1
                                        X              h X
                                                       X m
                            Ŝt+T =           Φq                ϕq,p,k (St−h+p,k ) .             (47)
                                       q=1             p=1 k=1

The adaptive spline parameterization gives KAN a distinctive local-adaptation profile that helps
explain why it remains competitive on some asset-level tasks, although the corrected L = 512 results
no longer make it the leading model for GOOG.

The Kolmogorov–Arnold theorem and approximation rates. The representation underlying
KAN is a constructive theorem of pure mathematics. Kolmogorov [1957], refined by Arnold [1957],
proved that every continuous function f : [0, 1]n → R admits an exact representation
                                                                                    
                                                        2n+1
                                                         X            n
                                                                      X
                             f (x1 , . . . , xn ) =            Φq         ϕq,p (xp ) ,           (48)
                                                        q=1          p=1


                                                          21
for suitable continuous outer functions Φq and inner univariate functions ϕq,p . The remarkable
feature of Eq. (48) is that the depth and the number of univariate components are bounded by a
function of the input dimension alone, independent of the smoothness or complexity of f .
    The theorem is not directly useful as an approximation algorithm: the optimal ϕq,p are typically
nowhere differentiable and cannot be parameterized in any closed form. KAN’s contribution is to
relax the exactness requirement and parameterize each ϕq,p as a low-order spline on a learnable knot
grid, trading the exact-representation guarantee for a flexible smooth approximation amenable to
gradient training. For target functions in the Sobolev space W s,∞ ([0, 1]) with s derivatives, a spline
of order k ≥ s on a uniform grid of resolution G approximates the target at rate

                                     ∥ϕ − ϕ̂∥∞ ≤ Cs G−s ∥ϕ∥W s,∞ ,                                 (49)

for a dimension-free constant Cs depending only on the spline order [de Boor, 2001]. Composing this
rate through the two-layer Kolmogorov–Arnold structure of Eq. (48) yields an overall approximation
rate that is controlled by the product of grid resolution and depth, and that—unlike the corresponding
rate for fully-connected ReLU networks—scales independently of the input dimension.
    Two consequences are relevant for the benchmark. First, dimension-independence of the
approximation rate is one mechanism by which KAN achieves competitive performance with
relatively few parameters; this is consistent with its strong showing on GOOG, but is not by
itself proof that GOOG is the asset on which this advantage should bind. Second, the spline
parameterization concentrates expressiveness exactly where the knot grid has resolution; for daily
equity returns this means KAN is well-positioned to capture local kinks and regime boundaries in
the conditional response, but at the cost of being more sensitive than transformer baselines to the
placement of the training window relative to those regimes. We do not exploit this insight in tuning,
and report only the canonical configuration.


3.21    Chronos-2: Time Series as Language Modelling

Chronos-2 [Ansari et al., 2025] extends the Chronos philosophy to a broader universal-forecasting
setting with multivariate and covariate support. The two-stage tokenization is retained: inputs are
normalized by mean scaling and then quantized into B discrete bins with centres cj and edges bi .
The backbone is a standard Transformer (e.g. T5), with its vocabulary adjusted to match B. The
categorical loss
                                  X |V
                                  H+1 Xts |

                       ℓ(θ) = −               1zC+h+1 =i log pθ (zC+h+1 = i | z1:C+h )             (50)
                                  h=1 i=1

is minimized as in Chronos (v1). Forecasts are obtained by autoregressive sampling followed by
dequantization and inverse scaling. Training uses the same TSMix and KernelSynth augmentations
as the original Chronos framework.


4      Experimental Design
4.1    Data, targets, and benchmark scope

The benchmark uses daily adjusted closing-price histories for GOOG, AAPL, AMZN, JPM, and
META from September 15, 2014, to February 15, 2026, sourced via the Yahoo Finance API. This
period spans approximately 11.5 years of market activity, including the post-pandemic recovery and

                                                       22
the high-volatility, AI-driven valuation cycle of 2024–2026. Prices are converted into two target
representations, linear returns rtlin = Pt /Pt−1 − 1 and log returns rtlog = log Pt − log Pt−1 . The
training segment runs from September 15, 2014, to August 21, 2024, and the evaluation segment
from August 22, 2024, through February 2026. For the rolling origin evaluation we use a forecast
horizon of H = 20 business days, simulating a one-month trading cycle.
    A key design choice is that pretrained models are used in zero-shot mode, whereas neural baselines
are trained separately for each ticker. This makes the study relevant for practical deployment,
but it also means the benchmark should not be read as a pure architecture-only experiment. It
measures as-used performance: broad pretraining plus zero-shot inference on one side, and local
train-from-scratch learning on the other.
    All evaluated neural models receive the same context window of L = 512, so context length is
not used as an advantage for either model family. The comparison therefore removes one important
source of unfairness, but it does not isolate architecture alone: pretrained TSFMs still benefit from
large external corpora and learned priors, whereas train-from-scratch baselines learn only from the
available single-asset history.

                         Table 1: Benchmark protocol and evaluation scope.

Item                   Setting
Assets                 GOOG, AAPL, AMZN, JPM, META
Targets                Linear returns and log returns
Forecast horizon       20 business days
Evaluation protocol    10 rolling-origin windows over the test period
Pretrained models      Zero-shot inference
Neural baselines       Per-ticker supervised training from scratch
Typical lookback       512 points for all models (TSFMs and Baselines)
Benchmarks             Random walk (zero return) and seasonal naive
Primary metric         Mean Absolute Error (MAE)
Relative metrics       Skill score vs. random walk; rMAE vs. seasonal naive
Statistical test       Diebold–Mariano with Harvey–Leybourne–Newbold correction


4.2    Models evaluated

Table 2 groups the eleven evaluated systems into two families: six pretrained TSFMs run in zero-shot
mode and five train-from-scratch baselines fitted separately to each ticker.




                                                 23
                             Table 2: Model families in the benchmark.

Model(s)                    Family                        Mode           Notes
TimeGPT, TimeGPT-LH         Pretrained TSFM               Zero-shot      Transfer-learning forecasting
                                                                         model family [Garza et al.,
                                                                         2024].
TimesFM-2.5                 Pretrained TSFM               Zero-shot      Checkpoint        from      the
                                                                         TimesFM          decoder-only
                                                                         foundation-model         family
                                                                         [Das et al., 2024].
Moirai-2.0                  Pretrained TSFM               Zero-shot      Decoder-only quantile-based
                                                                         forecasting model [Liu et al.,
                                                                         2025].
Chronos (v1), Chronos-2     Pretrained TSFM               Zero-shot      Quantized language-of-time
                                                                         approach and its univer-
                                                                         sal extension [Ansari et al.,
                                                                         2024, 2025].
NBEATS, NHITS               Train-from-scratch baseline   Per ticker     MLP-style decomposition
                                                                         baselines [Oreshkin et al.,
                                                                         2020, Challu et al., 2022].
PatchTST, iTransformer      Train-from-scratch baseline   Per ticker     Transformer baselines [Nie
                                                                         et al., 2023, Liu et al., 2024].
KAN                         Train-from-scratch baseline   Per ticker     Kolmogorov–Arnold           net-
                                                                         work for time series [Xu
                                                                         et al., 2024].


4.3   Context windows, training protocol, and reproducibility

All models share a unified forecast horizon of H = 20 business days and a unified context length of
L = 512. This equalization removes context length as a major confounding variable: both pretrained
TSFMs and train-from-scratch baselines are evaluated with the same historical information budget.
The design therefore makes the comparison fairer than a short-context baseline benchmark, but
it should still be interpreted as an as-used comparison rather than a pure architectural ablation.
Pretrained TSFMs bring large external pretraining corpora, whereas the baselines are estimated
only from the available local equity history.
    The evaluation framework distinguishes two protocols. Pretrained TSFMs (TimeGPT, TimeGPT-
LH, TimesFM-2.5, Moirai-2.0, Chronos (v1), Chronos-2) undergo no fine-tuning on the financial
data used in this study. Train-from-scratch baselines (NBEATS, NHITS, PatchTST, iTransformer,
KAN) are fitted individually for each ticker with a supervised protocol using MSE loss and early
stopping with patience 10, on the 2014–2024 training window. All models are evaluated with a
rolling-origin forecast evaluation (ROFE) over 10 windows, so that reported MAE and skill scores
reflect performance across market regimes in 2024–2026. For probabilistic outputs, the reported
point forecasts use the predictive median when available; quantized or sampled outputs are converted
to the corresponding median or sample-median point forecast before MAE is computed. The exact
software versions, API endpoints, checkpoint identifiers, random seeds, and rolling-origin calendar
anchors should be preserved in the companion code release; the present paper fixes the statistical


                                                24
protocol and tables but does not by itself constitute a complete executable replication package.

                     Table 3: Technical specification of the experimental pipeline.

Parameter               Foundation models                                  Neural baselines
Execution mode          Zero-shot inference                                Train-from-scratch
Context length (L)      512                                                512
Forecast horizon (H)    20                                                 20


4.4   Metrics and statistical testing

Mean absolute error. The primary metric is the mean absolute error on a forecast window of
length H,
                                          H
                                      1 X
                           MAE(f ) =         |ŷt+h − yt+h |.                         (51)
                                      H h=1
The choice of MAE rather than MSE is deliberate: by Section 3.1, absolute loss is the population
analogue of conditional-median estimation, and is therefore robust to the heavy tails of daily equity
returns—a few extreme days do not dominate the comparison the way they would under squared loss.
The cost of this robustness is that MAE is not aligned with the squared- or quantized-likelihood
objectives used to train most of the evaluated systems; the benchmark therefore tests robustness to
loss-function misalignment alongside raw predictive skill.

Skill score. To compare forecasts against the zero-return random-walk benchmark we report the
relative L1 risk reduction
                                                                                  H
                                         MAE(f )                               1 X
                       Skill(f ) = 1 −           ,         MAERW =                   |yt+h |.   (52)
                                         MAERW                                 H h=1

Positive values indicate that f extracts conditional information beyond the unconditional median;
negative values indicate that the forecast underperforms the constant-zero predictor. The score is
bounded above by 1 and unbounded below. When the unconditional median of y is approximately
zero, MAERW → E|y| in population, so Skill(f ) > 0 is equivalent to E|ŷ − y| < E|y|: the benchmark
detects information rather than scale, and rescaling the forecast cannot move skill from negative to
positive without conditional signal.

Relative MAE.       We also retain the relative MAE against a seasonal-naive reference,

                                            MAE(f )                  SN
                             rMAE(f ) =             ,              ŷt+h = yt+h−5 ,             (53)
                                            MAESN

where SN denotes the 5-business-day (weekly) seasonal-naive forecast standard for daily financial
data. Values below one indicate improvement over SN.

Diebold–Mariano test. For two competing forecasts ŷ (1) and ŷ (2) with absolute-loss differentials
                                             (1)               (2)
                                     dt = |ŷt     − yt | − |ŷt     − yt |,                    (54)

                                                      25
the Diebold–Mariano test [Diebold and Mariano, 2002] tests H0 : E[dt ] = 0 versus H1 : E[dt ] ̸= 0.
Under standard short-memory regularity on (dt ), the test statistic is
                                                   n                          h−1
                             d¯                 1
                                           d¯ =
                                                   X                          X
                                                                2
                     DM = p 2     ,                   dt ,    σ̂∞ = γ̂0 + 2         γ̂k ,          (55)
                           σ̂∞ /n               n t=1                         k=1

where γ̂k is the sample autocovariance of dt at lag k and the truncation at lag h − 1 accounts for
the h-step ahead overlap of the loss differentials. Under H0 and the regularity conditions of Diebold
                          d
and Mariano [2002], DM − → N (0, 1).

Harvey–Leybourne–Newbold correction. For finite samples and overlapping multi-step
forecasts the standard normal approximation is optimistic. Harvey et al. [1997] propose the
size-corrected statistic              s
                                        n + 1 − 2h + h(h − 1)/n
                           DM⋆ = DM ·                           ,                      (56)
                                                   n
referred to a tn−1 distribution rather than to a standard normal. With n ≈ 200 and h = 20 the
multiplicative factor in Eq. (56) is approximately 0.90, so the corrected statistic is more conservative
than the naive one and the reference distribution has heavier tails. We apply this correction
throughout.

Sign convention and the directional issue. The sign of d¯ identifies which of the two forecast
                                                           (1)          (2)
streams has lower loss: under our convention dt = |ŷt − yt | − |ŷt − yt |, a positive d¯ means
stream (1) has higher loss and is therefore worse. We employ a one-sided Diebold-Mariano test
(H1 : Model is more accurate than RW). In this framework, a significant p-value directly implies
superior predictive skill, removing the ambiguity of two-sided sign conventions. The results in
Table 7 show that for the majority of cases, we fail to reject the null hypothesis of equal or inferior
accuracy, reinforcing the difficulty of consistently outperforming the random-walk benchmark.

Multiple comparisons. The DM analysis involves a family of comparisons across models, tickers,
and return representations, so individual p-values should be read as raw rather than family-wise
corrected. We use p < 0.05 as the conventional significance threshold, but the significant cases
in Table 7 should be interpreted as exploratory evidence rather than as family-level discoveries.
Applying Bonferroni or Benjamini–Hochberg adjustments would make the inference more conservative
and would not change the main qualitative conclusion: statistically reliable improvement over the
random-walk benchmark is rare. A future large-universe benchmark should report adjusted p-values
or family-level rank tests.

Finite-sample concentration of MAE. The skill scores reported in Section 5 are sample
averages over a finite test window of length n ≈ 200 business days, and as such carry stochastic error.
For dependent loss differentials (dt ) satisfying a strong α-mixing condition with geometric rate, a
Bernstein-type inequality for stationary sequences [Merlevède et al., 2009] gives, for a constant C
depending on the mixing coefficients,
                                                                              !
                                                             n ε2
                          Pr d¯ − E[dt ] > ε     ≤ C exp −     2 + B ε)
                                                                        ,                          (57)
                                                           C (σ∞


                                                   26
where σ∞2 is the long-run variance defined in Eq. (55) and B is an almost-sure bound on |d |. The
                                                                                               t
half-width of a 1 − δ confidence interval for d¯ scales as σ∞ log(1/δ)/n to leading order. For the
                                                              p

empirical magnitudes of σ∞ in our benchmark—of the same order as the MAE itself—the resulting
interval half-width on d¯ is comparable to the size of the differences between top-ranked models in
Tables 8–9. This is a quantitative restatement of the cautious interpretation throughout the paper:
many of the rank-distance differences in our benchmark sit at the noise floor of the test window, and
would require a substantially longer evaluation horizon to distinguish at conventional confidence
levels.


5     Results




Figure 5: Representative actual-versus-predicted trajectories for a single 20-business-day forecast window.
The plot illustrates the core difficulty of return forecasting: even the lowest-error models fail to track the
realized path closely, which is why small MAE differences in the aggregate tables translate into the cautious
overall interpretation of this benchmark.


5.1    Aggregate findings

The aggregate ranking indicates that pretrained TSFMs remain the strongest practical default under
the equalized-context protocol. Across the 10 benchmark tasks, they account for 8 wins, while Moirai-
2.0 and TimesFM-2.5 achieve the best average ranks, 2.9 and 3.1, respectively. Table 4 summarizes


                                                     27
this distribution. The same table also identifies an important boundary case: iTransformer wins
both META tasks, showing that locally trained supervised baselines can remain competitive for
specific assets even when pretrained models dominate the overall ranking.

                       Table 4: Aggregate ranking across all 10 tasks (L = 512).

                  Model            Avg. rank    Wins     Top-3    Positive-skill cases
                  Moirai-2.0          2.9         3        6               4
                  TimesFM-2.5         3.1         4        6               4
                  Chronos (v1)        3.4         1        6               4
                  Chronos-2           3.9         0        6               4
                  iTransformer        4.3         2        2               0
                  KAN                 5.4         0        2               0


    The most significant shift occurs in the META and GOOG tasks. At L = 512, the iTransformer
baseline secures both META wins, while Moirai-2.0 displaces KAN as the leader in GOOG. This
suggests that while foundation models provide a robust prior, well-parameterized supervised baselines
are highly competitive when given sufficient historical context.


5.2   Asset-level winners

Table 5 makes the cross-asset pattern explicit. Under equalized context (L = 512), TimesFM-2.5
leads the AAPL and JPM tasks, while Moirai-2.0 leads the GOOG tasks. The most important
exception to pretrained-model dominance is META, where the iTransformer baseline outperforms all
foundation models. This suggests that pretrained TSFMs are a strong default, but not a universal
winner: for some assets and regimes, local supervised learning can remain superior even under the
same context budget.

Table 5: Winning model by asset and return representation (Corrected: All neural models evaluated at
context L = 512). Note the emergence of iTransformer in META and the shift in GOOG leadership to
Moirai-2.0.

              Return    Ticker     Winner              MAE        Skill    Runner-up
              Linear    AAPL       TimesFM-2.5        0.010440   -0.0319   Chronos (v1)
              Linear    AMZN       Chronos (v1)       0.012907    0.0863   Chronos-2
              Linear    GOOG       Moirai-2.0         0.009888    0.2289   TimesFM-2.5
              Linear    JPM        TimesFM-2.5        0.011412   -0.0466   Chronos-2
              Linear    META       iTransformer       0.017088   -0.0519   KAN
              Log       AAPL       TimesFM-2.5        0.010399   -0.0288   Chronos (v1)
              Log       AMZN       Moirai-2.0         0.012987   0.0824    Chronos-2
              Log       GOOG       Moirai-2.0         0.009886    0.2283   TimesFM-2.5
              Log       JPM        TimesFM-2.5        0.011463   -0.0510   Chronos-2
              Log       META       iTransformer       0.016925   -0.0464   KAN


   Taken together, Table 5 shows that the pretrained advantage is broad but asset-dependent, with
iTransformer providing a clear counterexample to universal TSFM dominance.

                                                  28
5.3    Benchmarks against naive baselines

The skill-score results reinforce the central difficulty of financial return forecasting. Positive skill
against the zero-return random-walk benchmark appears only in a minority of cases, mainly in
the AMZN and GOOG tasks. Across the pretrained TSFM model–asset cases, only 16 exhibit
positive skill, and the train-from-scratch baselines do not consistently improve on the random walk
in absolute-error terms. The results therefore support the interpretation of pretrained TSFMs as
useful practical priors, not as reliable engines of out-of-sample alpha.
    The rMAE summary in Table 6 provides a complementary view. Moirai-2.0 achieves the
strongest seasonal-naive-relative performance on GOOG, while iTransformer remains the best model
for META. This combination is important: the same protocol that favors pretrained TSFMs on
average also preserves asset-level cases in which local supervised learning is preferable.

Table 6: Best reported rMAE values (L = 512 for all neural models). Values represent the error ratio relative
to a weekly seasonal-naive baseline; lower is better, with values below 1.0 indicating superior predictive skill.

                             Ticker     Model               Return type     rMAE
                             AAPL       TimesFM-2.5         Log             0.6271
                             AMZN       Moirai-2.0          Log             0.6402
                             GOOG       Moirai-2.0          Linear          0.5284
                             JPM        TimesFM-2.5         Linear          0.7712
                             META       iTransformer        Log             0.8145


5.4    What the Diebold–Mariano results actually show

The most important statistical correction in this paper concerns the alignment of significance
and predictive superiority. By employing a one-sided Diebold–Mariano test with alternative
H1 : Model is more accurate than RW, the reported p-values are tied directly to improvement over
the random-walk benchmark rather than to a generic two-sided difference. A significant result
should therefore be read as evidence of lower absolute loss within the tested window, subject to the
usual finite-sample and multiple-comparison limitations.
   The results in Table 7 provide a nuanced view of model efficacy. Under equalized context
(L = 512), only two cases achieve statistical significance: Chronos (v1) for AMZN (p = 0.0421)
and Moirai-2.0 for GOOG (p = 0.0421). In these specific instances, the models demonstrate a
robust ability to extract signal from market returns beyond what could be attributed to chance.
   For the majority of other pairs, including those involving top-ranked models like TimesFM-2.5 on
AAPL and JPM, we fail to reject the null hypothesis of equal or inferior accuracy. This reinforces a
primary finding of this benchmark: while pretrained TSFMs act as superior inductive priors compared
to baselines, outperforming the random-walk benchmark in efficient market regimes remains an
exception rather than the rule. The correction from two-sided to one-sided interpretation ensures
that significance is no longer conflated with "difference," but is strictly reserved for "improvement."




                                                       29
Table 7: One-sided Diebold–Mariano test results (H1 : Model is more accurate than RW). All models
are evaluated at context L = 512. The p-value is computed under the null of no improvement relative to
the random-walk benchmark; small values indicate evidence against that null in favor of lower model loss.
Significant results (p < 0.05) are reported as evidence of predictive improvement within this test window.

        Ticker     Model              p-value     Skill       Direction       Status
        AAPL       TimesFM-2.5        0.9999    -0.0319      RW better        Fails to reject H0
        AAPL       iTransformer       0.8458    -0.0246      RW better        Fails to reject H0
        AMZN       Chronos (v1)       0.0421    0.0863     Model better       Significant
        AMZN       iTransformer       0.9126    -0.0280     RW better         Fails to reject H0
        GOOG       Moirai-2.0         0.0421    0.2289     Model better       Significant
        GOOG       iTransformer       0.5950    -0.0056     RW better         Fails to reject H0
        JPM        TimesFM-2.5        0.9999    -0.0466      RW better        Fails to reject H0
        JPM        iTransformer       0.6091    -0.0059      RW better        Fails to reject H0
        META       iTransformer       0.9838    -0.0519      RW better        Fails to reject H0
        META       KAN                0.9784    -0.0549      RW better        Fails to reject H0



6    Discussion and Limitations
The main empirical message is pragmatic. In a small-data, per-asset financial setting, off-the-shelf
pretrained TSFMs are usually preferable to training a modern neural baseline from scratch. This
claim is supported by the ranking distribution: pretrained TSFMs account for 8 of the 10 task wins,
while Moirai-2.0 and TimesFM-2.5 achieve the two best average ranks among the reported models.
At the same time, the META results show that this advantage is not universal: iTransformer wins
both META tasks under the same L = 512 context budget.
    Four limitations should bound the interpretation. First, this is not a clean architecture-only
comparison. Although all neural models receive the same context length, pretrained systems
benefit from large external corpora and fixed learned priors, while the baselines are trained only on
single-asset histories. The benchmark therefore measures practical deployment performance, not
architecture in isolation.
    Second, the evaluation window is limited. The rolling-origin protocol covers multiple market
conditions in 2024–2026, but the number of test windows remains small relative to the noise level
of daily equity returns. Many differences between top-ranked models are therefore close to the
finite-sample noise floor, and the ranking evidence should be interpreted together with the DM
results.
    Third, the benchmark is better described as a TSFM benchmark than as a direct test of generic
LLM methods. Time-LLM and related LLM-reprogramming approaches are important conceptual
references, but they are not evaluated empirically here. A future version aimed specifically at LLM
reprogramming should include direct Time-LLM-style experiments.
    Fourth, the paper evaluates forecast error rather than investment utility. The results should not
be read as evidence of trading alpha. Directional accuracy, calibration, turnover-aware backtests,
transaction costs, and capacity constraints would all be required before making stronger economic
claims.



                                                   30
    Finally, the results are consistent with contemporaneous evidence that generic TSFM pretraining
is useful but not a substitute for finance-native pretraining. Read alongside Rahimikia et al. [2025],
the modest forecast-error advantages reported here are best understood as evidence that pretrained
TSFMs provide a useful inductive prior for low-data, per-asset settings. They do not establish
that generic temporal pretraining captures the finance-specific structure needed for robust portfolio
outperformance.


7    Conclusion
This benchmark supports a clear but measured conclusion. Pretrained time-series foundation models
are strong practical defaults for low-data, per-asset financial return forecasting, but their superiority
is not universal. Moirai-2.0 and TimesFM-2.5 deliver the most consistent aggregate rankings, while
iTransformer’s wins on META show that locally trained supervised baselines can still outperform
foundation models for specific assets under the same context budget.
    The evidence favors large-scale temporal pretraining as a useful inductive prior, especially in
tasks such as GOOG and AMZN where positive skill appears more clearly. However, improvements
over the random-walk benchmark remain sparse and small, and the one-sided Diebold–Mariano
results reject the null of no improvement only in a minority of cases. The appropriate conclusion is
therefore narrow: out-of-the-box TSFMs can reduce model-development costs and provide strong
forecasting baselines, but they do not solve the fundamental difficulty of financial return prediction.




                                                   31
A        Full benchmark tables
The appendix reproduces the full performance tables so that the benchmark remains auditable after
the interpretive changes in the main text.
Table 8: Full benchmark results for log returns. All neural models (baselines and TSFMs) are evaluated
with a context window of L = 512. Traditional statistical baselines [AR(1), EWMA] are included to provide
a benchmark for linear predictability.

Ticker    Model             MAE (mean ± std)       Skill score vs. RW
AAPL      TimesFM-2.5      0.010399 (±0.0071)           -0.0288
AAPL      Chronos (v1)      0.012084 (±0.0080)           0.0048
AAPL      AR(1)             0.012115 (±0.0079)            0.0021
AAPL      EWMA              0.012140 (±0.0081)           -0.0002
AAPL      iTransformer      0.012255 (±0.0080)           -0.0091
AAPL      PatchTST          0.012379 (±0.0081)           -0.0193
AAPL      KAN               0.012689 (±0.0081)           -0.0561
AMZN      Moirai-2.0       0.012987 (±0.0085)           0.0824
AMZN      Chronos (v1)      0.015456 (±0.0117)          0.0007
AMZN      AR(1)             0.015510 (±0.0115)          0.0003
AMZN      TimesFM-2.5       0.015525 (±0.0117)          -0.0038
AMZN      iTransformer      0.015783 (±0.0117)          -0.0205
AMZN      KAN               0.015792 (±0.0116)          -0.0210
GOOG      Moirai-2.0       0.009886 (±0.0055)           0.2283
GOOG      KAN               0.013456 (±0.0075)           0.0057
GOOG      AR(1)             0.013490 (±0.0074)           0.0032
GOOG      Chronos (v1)      0.014104 (±0.0078)          -0.0419
GOOG      iTransformer      0.014234 (±0.0077)          -0.0515
JPM       TimesFM-2.5      0.011463 (±0.0061)           -0.0510
JPM       Chronos-2         0.011554 (±0.0062)           -0.0593
JPM       AR(1)             0.011680 (±0.0060)            0.0042
JPM       Chronos (v1)      0.012085 (±0.0071)            0.0056
JPM       iTransformer      0.012170 (±0.0065)           -0.0013
JPM       NHITS             0.015944 (±0.0055)           -0.3781
META      iTransformer     0.016925 (±0.0060)           -0.0464
META      KAN               0.017033 (±0.0058)           -0.0531
META      PatchTST          0.017267 (±0.0062)           -0.0675
META      AR(1)             0.017410 (±0.0059)           -0.0012
META      Moirai-2.0        0.020853 (±0.0071)           -0.2885
META      Chronos-2         0.021234 (±0.0070)           -0.3120


Table 9: Full benchmark results for linear returns. All models (including neural baselines) are evaluated
with a context window of L = 512. Models are ranked by ascending MAE within each ticker block.

Ticker    Model             MAE (mean ± std)       Skill score vs. RW
AAPL      TimesFM-2.5      0.010440 (±0.0071)           -0.0319
AAPL      Chronos (v1)      0.012093 (±0.0081)           0.0067
AAPL      AR(1)             0.012115 (±0.0080)           0.0021
                                            Continued on next page


                                                   32
              Table 9 – continued from previous page
Ticker   Model             MAE (mean ± std)      Skill score vs. RW
AAPL     iTransformer      0.012351 (±0.0078)          -0.0246
AAPL     KAN               0.012666 (±0.0081)          -0.0514
AAPL     PatchTST          0.012510 (±0.0080)          -0.0345
AMZN     Chronos (v1)    0.012907 (±0.0085)            0.0863
AMZN     Moirai-2.0       0.013002 (±0.0086)            0.0813
AMZN     TimesFM-2.5      0.013110 (±0.0087)           0.0719
AMZN     AR(1)            0.015510 (±0.0115)           0.0003
AMZN     iTransformer     0.016045 (±0.0062)           -0.0280
AMZN     KAN              0.015826 (±0.0059)           -0.0319
GOOG     Moirai-2.0      0.009888 (±0.0055)            0.2289
GOOG     TimesFM-2.5      0.010114 (±0.0056)           0.2110
GOOG     Chronos (v1)     0.010321 (±0.0056)           0.1948
GOOG     AR(1)            0.013490 (±0.0074)           0.0032
GOOG     iTransformer     0.013147 (±0.0045)           -0.0056
GOOG     KAN              0.013471 (±0.0040)           0.0067
JPM      TimesFM-2.5     0.011412 (±0.0058)            -0.0466
JPM      Chronos-2        0.011520 (±0.0059)            -0.0495
JPM      AR(1)            0.011685 (±0.0060)             0.0042
JPM      Chronos (v1)     0.012089 (±0.0047)             0.0045
JPM      iTransformer     0.012708 (±0.0048)            -0.0059
JPM      KAN              0.012136 (±0.0048)             0.0022
META     iTransformer    0.017088 (±0.0060)            -0.0519
META     KAN              0.017136 (±0.0061)            -0.0549
META     PatchTST         0.017390 (±0.0062)            -0.0705
META     AR(1)            0.017420 (±0.0060)            -0.0012
META     Moirai-2.0       0.021101 (±0.0070)            -0.4546
META     Chronos-2        0.021478 (±0.0068)            -0.4806




                                                 33
B      Reproducibility checklist
This appendix separates what is fixed by the manuscript from what must be fixed by the companion
code release for exact replication. The distinction is important because several models are accessed
through external libraries or hosted APIs.

                     Table 10: Minimum reproducibility record for the benchmark.

Item                        Manuscript-level specification
Data source                 Yahoo Finance daily adjusted close histories for GOOG, AAPL, AMZN,
                            JPM, and META.
Date range                  September 15, 2014, through February 15, 2026.
Return formulas             Linear returns Pt /Pt−1 − 1 and log returns log Pt − log Pt−1 .
Train/evaluation split      Training window through August 21, 2024; evaluation window beginning
                            August 22, 2024.
Forecast horizon            H = 20 business days for all models.
Rolling evaluation          Ten rolling-origin forecast windows; reported MAE and skill are arith-
                            metic averages across these windows.
Point forecast extraction   Predictive median where available; sampled or quantized predictive
                            distributions reduced to a median or sample-median point forecast before
                            MAE computation.
Primary baseline            Zero-return random walk for skill scores; 5-business-day seasonal naive
                            for rMAE.
Statistical test            Absolute-loss Diebold–Mariano test with Harvey–Leybourne–Newbold
                            finite-sample correction.


    For full computational reproducibility, the released code should additionally record package
versions, model checkpoints or API version identifiers, random seeds, optimizer settings, early-
stopping split, rolling-origin calendar dates, and any vendor-specific forecast parameters. These
identifiers are not inferable from the manuscript tables alone, so the paper’s numerical results should
be read as an auditable benchmark report rather than as a fully executable artifact unless the
companion code is supplied.


References
Paul H. Algoet and Thomas M. Cover. Asymptotic optimality and asymptotic equipartition
  properties of log-optimum investment. Annals of Probability, 16(2):876–898, 1988.

Miguel Noguer i Alonso and Rodolfo Pereira Franklin. Large language models for financial time
 series forecasting. Artificial Intelligence Finance Institute, March 2025. URL https://papers.
 ssrn.com/sol3/papers.cfm?abstract_id=4988022. Preprint dated March 4, 2025.

Shun-Ichi Amari. Natural gradient works efficiently in learning. Neural Computation, 10(2):251–276,
  1998.

Abdul Fatir Ansari, Lorenzo Stella, Caner Turkmen, Xiyuan Zhang, Pedro Mercado, Huibin
 Shen, Oleksandr Shchur, Syama Sundar Rangapuram, Sebastian Pineda Arango, Shubham


                                                  34
  Kapoor, Jasper Zschiegner, Danielle C. Maddix, Hao Wang, Michael W. Mahoney, Kari Torkkola,
  Andrew Gordon Wilson, Michael Bohlke-Schneider, and Yuyang Wang. Chronos: Learning the
  language of time series, 2024. URL https://arxiv.org/abs/2403.07815.

Abdul Fatir Ansari, Oleksandr Shchur, Jaris Küken, Andreas Auer, Boran Han, Pedro Mercado,
 Syama Sundar Rangapuram, Huibin Shen, Lorenzo Stella, Xiyuan Zhang, Mononito Goswami,
 Shubham Kapoor, Danielle C. Maddix, Pablo Guerron, Tony Hu, Junming Yin, Nick Erickson,
 Prateek Mutalik Desai, Hao Wang, Huzefa Rangwala, George Karypis, Yuyang Wang, and
 Michael Bohlke-Schneider. Chronos-2: From univariate to universal forecasting, 2025. URL
 https://arxiv.org/abs/2510.15821.

Vladimir I. Arnold. On functions of three variables. Doklady Akademii Nauk SSSR, 114:679–681,
  1957.

George E. P. Box and Gwilym M. Jenkins. Time Series Analysis: Forecasting and Control. Holden-
  Day, San Francisco, 1970.

Tom B. Brown, Benjamin Mann, Nick Ryder, Melanie Subbiah, Jared Kaplan, Prafulla Dhariwal,
  Arvind Neelakantan, Pranav Shyam, Girish Sastry, Amanda Askell, Sandhini Agarwal, Ariel
  Herbert-Voss, Gretchen Krueger, Tom Henighan, Rewon Child, Aditya Ramesh, Daniel M.
  Ziegler, Jeffrey Wu, Clemens Winter, Christopher Hesse, Mark Chen, Eric Sigler, Mateusz
  Litwin, Scott Gray, Benjamin Chess, Jack Clark, Christopher Berner, Sam McCandlish, Alec
  Radford, Ilya Sutskever, and Dario Amodei. Language models are few-shot learners, 2020. URL
  https://arxiv.org/abs/2005.14165.

Olivier Catoni. PAC-Bayesian Supervised Classification: The Thermodynamics of Statistical
  Learning, volume 56 of Institute of Mathematical Statistics Lecture Notes – Monograph Series.
  Institute of Mathematical Statistics, 2007.

Cristian Challu, Kin G. Olivares, Boris N. Oreshkin, Federico Garza, Max Mergenthaler-Canseco,
  and Artur Dubrawski. N-hits: Neural hierarchical interpolation for time series forecasting, 2022.
  URL https://arxiv.org/abs/2201.12886.

Ching Chang, Wei-Yao Wang, Wen-Chih Peng, and Tien-Fu Chen. Llm4ts: Aligning pre-trained
 llms as data-efficient time-series forecasters, 2024. URL https://arxiv.org/abs/2308.08469.

Kuo-Tsai Chen. Integration of paths—a faithful representation of paths by noncommutative formal
 power series. Transactions of the American Mathematical Society, 89(2):395–407, 1958.

Ilya Chevyrev and Andrey Kormilitzin. A primer on the signature method in machine learning,
   2016. URL https://arxiv.org/abs/1603.03788.

Thomas M. Cover and Joy A. Thomas. Elements of Information Theory. Wiley-Interscience, 2nd
 edition, 2006.

Abhimanyu Das, Weihao Kong, Rajat Sen, and Yichen Zhou. A decoder-only foundation model for
 time-series forecasting, 2024. URL https://arxiv.org/abs/2310.10688.

Carl de Boor. A Practical Guide to Splines, volume 27 of Applied Mathematical Sciences. Springer,
  revised edition, 2001.

Francis X Diebold and Robert S Mariano. Comparing predictive accuracy. Journal of Business &
  economic statistics, 20(1):134–144, 2002.

                                                35
Azul Garza, Cristian Challu, and Max Mergenthaler-Canseco. Timegpt-1, 2024. URL https:
 //arxiv.org/abs/2310.03589.

Tilmann Gneiting and Adrian E. Raftery. Strictly proper scoring rules, prediction, and estimation.
  Journal of the American Statistical Association, 102(477):359–378, 2007.

David Harvey, Stephen Leybourne, and Paul Newbold. Testing the equality of prediction mean
 squared errors. International Journal of forecasting, 13(2):281–291, 1997.

Ming Jin, Shiyu Wang, Lintao Ma, Zhixuan Chu, James Y. Zhang, Xiaoming Shi, Pin-Yu Chen,
 Yuxuan Liang, Yuan-Fang Li, Shirui Pan, and Qingsong Wen. Time-llm: Time series forecasting
 by reprogramming large language models, 2024. URL https://arxiv.org/abs/2310.01728.

J. L. Kelly. A new interpretation of information rate. Bell System Technical Journal, 35(4):917–926,
   1956.

Roger Koenker. Quantile Regression. Econometric Society Monographs. Cambridge University
 Press, 2005.

Andrey N. Kolmogorov. On the representation of continuous functions of several variables by
 superposition of continuous functions of one variable and addition. Doklady Akademii Nauk SSSR,
 114:953–956, 1957.

Gerhard Kramer. Directed Information for Channels with Feedback. PhD thesis, Swiss Federal
 Institute of Technology (ETH) Zürich, 1998.

Gregory F. Lawler and Alan D. Sokal. Bounds on the L2 spectrum for Markov chains and Markov
  processes: a generalization of Cheeger’s inequality. Transactions of the American Mathematical
 Society, 309(2):557–580, 1988.

Chenghao Liu, Taha Aksu, Juncheng Liu, Xu Liu, Hanshu Yan, Quang Pham, Silvio Savarese,
 Doyen Sahoo, Caiming Xiong, and Junnan Li. Moirai 2.0: When less is more for time series
 forecasting, 2025. URL https://arxiv.org/abs/2511.11698. Version cited in manuscript as
 Moirai 2.0.

Yong Liu, Tengge Hu, Haoran Zhang, Haixu Wu, Shiyu Wang, Lintao Ma, and Mingsheng Long.
  itransformer: Inverted transformers are effective for time series forecasting, 2024. URL https:
  //arxiv.org/abs/2310.06625.

Terry J. Lyons. Differential equations driven by rough signals. Revista Matemática Iberoamericana,
  14(2):215–310, 1998.

David A. McAllester. PAC-Bayesian model averaging. In Proceedings of the Twelfth Annual
 Conference on Computational Learning Theory (COLT), pages 164–170, 1999.

Florence Merlevède, Magda Peligrad, and Emmanuel Rio. Bernstein inequality and moderate
  deviations under strong mixing conditions. High Dimensional Probability V: The Luminy Volume,
  5:273–292, 2009.

Yuqi Nie, Nam H. Nguyen, Phanwadee Sinthong, and Jayant Kalagnanam. A time series is worth
  64 words: Long-term forecasting with transformers, 2023. URL https://arxiv.org/abs/2211.
  14730.


                                                36
OpenAI. GPT-4 technical report, 2023. URL https://arxiv.org/abs/2303.08774.

Boris N. Oreshkin, Dmitri Carpov, Nicolas Chapados, and Yoshua Bengio. N-beats: Neural basis
  expansion analysis for interpretable time series forecasting, 2020. URL https://arxiv.org/abs/
  1905.10437.

Felix Otto. The geometry of dissipative evolution equations: the porous medium equation. Commu-
  nications in Partial Differential Equations, 26(1–2):101–174, 2001.

Haim H. Permuter, Young-Han Kim, and Tsachy Weissman. Interpretations of directed information
  in portfolio theory, data compression, and hypothesis testing. IEEE Transactions on Information
 Theory, 57(6):3248–3259, 2011.

A. Radford, J. Wu, R. Child, D. Luan, D. Amodei, and I. Sutskever. Language models
  are unsupervised multitask learners, 2019. URL https://d4mucfpksywv.cloudfront.net/
  better-language-models/language_models_are_unsupervised_multitask_learners.pdf.

Eghbal Rahimikia, Hao Ni, and Weiguan Wang. Re(Visiting) Time Series Foundation Models in
  Finance. SSRN Electronic Journal, November 2025. URL https://papers.ssrn.com/sol3/
  papers.cfm?abstract_id=5770562. SSRN preprint 5770562.

Gemini Team. Gemini: A family of highly capable multimodal models, 2024. URL https:
 //arxiv.org/abs/2312.11805.

Hugo Touvron, Thibaut Lavril, Gautier Izacard, Xavier Martinet, Marie-Anne Lachaux, Timothée
 Lacroix, Baptiste Rozière, Naman Goyal, Eric Hambro, Faisal Azhar, Aurelien Rodriguez, Armand
 Joulin, Edouard Grave, and Guillaume Lample. Llama: Open and efficient foundation language
 models, 2023. URL https://arxiv.org/abs/2302.13971.

Cédric Villani. Topics in Optimal Transportation, volume 58 of Graduate Studies in Mathematics.
  American Mathematical Society, 2003.

David Williams. Probability with Martingales. Cambridge University Press, 1991.

Kunpeng Xu, Lifei Chen, and Shengrui Wang. Kolmogorov-arnold networks for time series: Bridging
 predictive power and interpretability, 2024. URL https://arxiv.org/abs/2406.02496.

Hao Xue and Flora D. Salim. Promptcast: A new prompt-based learning paradigm for time series
 forecasting, 2023. URL https://arxiv.org/abs/2210.08964.




                                               37