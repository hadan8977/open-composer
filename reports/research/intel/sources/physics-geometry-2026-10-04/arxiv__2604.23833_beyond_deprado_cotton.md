source: https://arxiv.org/pdf/2604.23833
fetched_utc: 2026-10-04T18:48:33Z
bytes_raw: 1456791

Beyond De Prado and Cotton
                                                Hierarchical and Iterative Methods for General Mean–Variance Portfolios

                                                                              Bernd J. Wuebben
                                                                         AllianceBernstein, New York
                                                                    bernd.wuebben@alliancebernstein.com
arXiv:2604.23833v1 [q-fin.PM] 26 Apr 2026




                                                                                    April 11, 2026


                                                                                       Abstract
                                            Hierarchical Risk Parity [López de Prado, 2016] and the Schur-complement generalisation of
                                            Cotton [2024] are among the most widely adopted regularised portfolio construction methods, yet
                                            both are signal-blind: they solve only the minimum-variance problem and cannot accommodate
                                            an arbitrary expected-return forecast. This paper introduces three methods that incorporate
                                            alpha signals into hierarchical and regularised portfolio construction.
                                            HRP-µ is a hierarchical allocator that accepts an arbitrary signal µ and nests standard HRP
                                            when γ = 0 and µ = 1. It preserves the tree-based structure of HRP while extending it beyond the
                                            minimum-variance setting. HRP-Σµ strengthens this construction by replacing inverse-variance
                                            representatives with recursive local mean–variance optima, thereby using richer within-cluster
                                            covariance information at the same O(N 2 ) asymptotic cost.
                                            CRISP (Correlation-Regularised Iterative Shrinkage Portfolios) is an iterative solver for Pγ w = µ
                                            with Pγ = (1 − γ) diag(Σ) + γΣ, so that γ interpolates between a diagonal portfolio rule and
                                            full Markowitz. At convergence, CRISP is Markowitz applied to a variance-preserving shrunk
                                            covariance—diagonal variances unchanged, off-diagonal correlations shrunk—with γ tuned for
                                            out-of-sample Sharpe rather than covariance-estimation loss.
                                            In Monte Carlo experiments across multiple covariance regimes and estimation ratios, HRP-µ
                                            and HRP-Σµ both outperform plain HRP—not only on general expected-return forecasts, where
                                            HRP is signal-blind, but also on the minimum-variance problem µ = 1 that is HRP’s home
                                            territory—with HRP-Σµ consistently improving on HRP-µ. CRISP at intermediate γ is the
                                            dominant method in both regimes, outperforming HRP, Cotton, Ledoit–Wolf shrinkage, direct
                                            Markowitz, and the signal-aware hierarchical methods at every sample size tested.

                                            Keywords: portfolio optimization, hierarchical risk parity, Schur complement, signal-dependent
                                            allocation, covariance shrinkage, out-of-sample evaluation

                                            JEL Classification: G11, C61, C63, C55

                                            Code: All code, data, and reproduction scripts are available at https://github.com/bwuebben/
                                            beyond_hrp_and_cotton.




                                                                                            1
Contents
1 Introduction                                                                                         5
  1.1 Motivation . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .     5
  1.2 Three methodological contributions . . . . . . . . . . . . . . . . . . . . . . . . . . . .       5
  1.3 Three supporting contributions . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .       6
  1.4 Memory, not speed . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .      7
  1.5 Road map . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .     7
  1.6 Relation to the literature . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .     8

2 Notation and the direction view                                                                       9
  2.1 Notation . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .    9
  2.2 Markowitz as a ray . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .      9
  2.3 Direction error . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .    10
  2.4 Warning: direction error is sign-invariant . . . . . . . . . . . . . . . . . . . . . . . . .     10
  2.5 Correlation conditioning as a difficulty diagnostic . . . . . . . . . . . . . . . . . . . .      10
  2.6 The parallel-direction identity . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .    11
  2.7 Notation summary . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .       12

3 Background: HRP and Cotton                                                                           12
  3.1 Hierarchical Risk Parity . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .     13
  3.2 Cotton’s Schur-complement allocation . . . . . . . . . . . . . . . . . . . . . . . . . .         14
  3.3 Cotton under estimation noise . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .      15
  3.4 Why extend to general µ? . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .       17
  3.5 Method landscape . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .       17

4 Tree-based signal-aware allocation                                                                   18
  4.1 The 2 × 2 between-branch system . . . . . . . . . . . . . . . . . . . . . . . . . . . . .        18
  4.2 Three candidate representatives . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .      19
  4.3 HRP-µ: transparent signal-aware HRP . . . . . . . . . . . . . . . . . . . . . . . . . .          20
      4.3.1 Signed Hierarchical Signal Parity (HSP) . . . . . . . . . . . . . . . . . . . . .          22
      4.3.2 Cost comparison . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .        22
  4.4 HRP-Σµ: recursive MVO with L1 normalisation . . . . . . . . . . . . . . . . . . . .              22
  4.5 Iterating the tree pass diverges . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .     26
  4.6 Pointer to the sum-normalised recursive MVO negative result . . . . . . . . . . . . .            26

5 CRISP: iterative shrinkage solver                                                                    27
  5.1 The shrinkage operator Pγ . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .      27
  5.2 Scalar Gauss–Seidel iteration . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .      28
  5.3 Unconditional convergence . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .      28
  5.4 Correlation conditioning and the convergence-rate theorem . . . . . . . . . . . . . .            29
  5.5 What CRISP does not do . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .         30
  5.6 Factor-model streaming variant . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .       31
  5.7 Shrinkage interpretation and Ledoit–Wolf comparison . . . . . . . . . . . . . . . . .            32
  5.8 Early stopping as implicit spectral regularisation . . . . . . . . . . . . . . . . . . . .       33
  5.9 Wall-clock versus memory . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .       33




                                                   2
6 Perturbation theory and the shrinkage trajectory                                                      34
  6.1 Invariant rays revisited . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .    34
  6.2 Approximation-error identity . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .        35
  6.3 Direction-error bound . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .       35
  6.4 The shrinkage trajectory . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .      36
  6.5 Shrinkage bias vs. convergence slack: the interior γ ⋆ . . . . . . . . . . . . . . . . . .        36

7 The adaptive γ ⋆ rule and three regularisation channels                                               39
  7.1 Bias–variance decomposition . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .         39
  7.2 Approximation loss via Neumann expansion . . . . . . . . . . . . . . . . . . . . . . .            39
  7.3 Estimation loss via Marchenko–Pastur and the information coefficient . . . . . . . .              40
  7.4 First-order γ ⋆ and comparative statics . . . . . . . . . . . . . . . . . . . . . . . . . .       40
  7.5 Calibration: the OOS Sharpe surface is flat . . . . . . . . . . . . . . . . . . . . . . .         41
  7.6 Three regularisation channels . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .       41
  7.7 Information-theoretic reading . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .       43
  7.8 P6 revisited: the clean-signal paradox . . . . . . . . . . . . . . . . . . . . . . . . . .        43

8 Comparative landscape                                                                                 43
  8.1 Method landscape . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .        44
  8.2 Behaviour at the four corners of (γ, µ) . . . . . . . . . . . . . . . . . . . . . . . . . .       44
  8.3 Computational profile . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .       45
  8.4 Key relationships . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .     45
  8.5 Practitioner’s guide . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .    46
  8.6 When not to use a tree . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .      47

9 Constraint handling                                                                                   47
  9.1 QP reference formulation . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .        47
  9.2 Projected CRISP . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .       48
  9.3 Constrained HRP-µ and HRP-Σµ . . . . . . . . . . . . . . . . . . . . . . . . . . . . .            49
  9.4 Worked example: long-only, sector-capped . . . . . . . . . . . . . . . . . . . . . . . .          49
  9.5 Discussion . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .    50

10 Synthetic experiments                                                                                50
   10.1 Setup . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .   50
   10.2 Part A — in-sample direction-error diagnostics . . . . . . . . . . . . . . . . . . . . .        51
        10.2.1 Experiment 1: De Prado recovery at γ = 0, µ = 1 . . . . . . . . . . . . . . . .          51
        10.2.2 Experiment 2: minimum-variance direction error . . . . . . . . . . . . . . . .           51
        10.2.3 Experiment 3: graduated difficulty . . . . . . . . . . . . . . . . . . . . . . . .       52
        10.2.4 Experiment 4: worst-case µ and Lemma 2.3 . . . . . . . . . . . . . . . . . . .           52
        10.2.5 Experiment 5: convergence-rate verification . . . . . . . . . . . . . . . . . . .        53
        10.2.6 Experiment 6: shrinkage trajectory and interior γ ⋆ (p) . . . . . . . . . . . . .        53
   10.3 Part B — out-of-sample Monte Carlo . . . . . . . . . . . . . . . . . . . . . . . . . . .        53
        10.3.1 Experiment 7: sensitivity across µ seeds . . . . . . . . . . . . . . . . . . . . .       54
        10.3.2 Experiment 8: structural sector-tilt µ across T ∈ {60, 120, 240} . . . . . . . .         55
        10.3.3 Experiment 9: minimum variance with Cotton as baseline . . . . . . . . . . .             55
   10.4 Part C — sweep count as regularisation and adaptive γ ⋆ . . . . . . . . . . . . . . . .         57
        10.4.1 Experiment 11: sweep count as regularisation . . . . . . . . . . . . . . . . . .         57
        10.4.2 Experiment 12: adaptive γ ⋆ calibration . . . . . . . . . . . . . . . . . . . . .        59


                                                    3
   10.5 Summary of Section 10 . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 59

11 Discussion                                                                                            60
   11.1 Three regularisation channels revisited . . . . . . . . . . . . . . . . . . . . . . . . . .      60
   11.2 Signed HSP as a standalone method . . . . . . . . . . . . . . . . . . . . . . . . . . .          60
   11.3 Open problems . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .      60
   11.4 Extensions . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .   61
   11.5 Computational considerations . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .       62
   11.6 Limitations . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .    62
   11.7 Broader methodological reflection: direction error as a diagnostic . . . . . . . . . . .         63

12 Conclusion                                                                                            64

A Proofs                                                                                                 65

B Worked examples: HRP, HRP-µ, HRP-Σµ                                                                    72
  B.1 HRP worked example . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .           73
  B.2 HRP-µ worked example . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .           74
  B.3 HRP-Σµ worked example . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .            76
  B.4 Comparison . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .       77

C Sum-normalised recursive MVO and the sign-flip pathology                                               78
  C.1 The A1 construction . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .        79
  C.2 The sign-flip mechanism . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .        79
  C.3 Noiseless evidence . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .       79
  C.4 Evidence under estimation noise . . . . . . . . . . . . . . . . . . . . . . . . . . . . .          80
  C.5 The fix: L1 normalisation . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .        81
  C.6 Why the direction-error metric does not catch this . . . . . . . . . . . . . . . . . . .           82
  C.7 Conclusion . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .       82

D Implementation details and reproducibility                                                             82
  D.1 Tree construction . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .      83
  D.2 Pseudocode . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .       83
  D.3 Numerical stability notes . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .        84
  D.4 Function catalog . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .       86
  D.5 Code and reproducibility . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .       88

E Supplementary tables and robustness                                                                    88
  E.1 Additional covariance regimes . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .        89
  E.2 Sensitivity to ridge regularisation . . . . . . . . . . . . . . . . . . . . . . . . . . . . .      89
  E.3 Sensitivity to tree construction . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .       89
  E.4 Flat-IVP direction error . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .       89
  E.5 HRP-Σµ robustness . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .          90




                                                    4
1     Introduction
1.1   Motivation
Hierarchical Risk Parity [López de Prado, 2016] and the Schur-complement allocator of Cotton
[2024] have become standard regularised portfolio constructions. Both are signal-blind. They solve
only the minimum-variance problem µ = 1 and have no mechanism for an expected-return forecast.
Cotton’s allocator connects HRP to exact minimum variance through a single continuous parameter
γ ∈ [0, 1] and is in that sense a strict generalisation of López de Prado, but it inherits the µ = 1
restriction and costs O(N 3 /6) because a sibling covariance block must be inverted at every internal
tree node.
    This restriction collides with three features of real portfolio construction. The first is signal
integration. Quantitative equity, factor investing, tactical asset allocation, and Black–Litterman
view blending [Black and Litterman, 1992; Grinold and Kahn, 1999; Barroso and Santa-Clara, 2015]
all deliver a heterogeneous µ, and that signal is the object that distinguishes an active portfolio
from a risk-only allocation. Setting µ = 1 is active discarding, not a neutral default. The second is
computational tractability. Universes with N between 103 and 104 , re-optimised on rolling windows,
make O(N 3 ) operations costly; O(N 2 ) is the budget a realistic backtest can absorb. The third is
estimation error. Direct Markowitz inversion [Markowitz, 1952] amplifies noise on low-variance
eigenvectors and produces the extreme weights documented by Michaud [1989], and the standard
remedy is structural shrinkage of the covariance estimator [Stein, 1956; Ledoit and Wolf, 2003, 2004,
2017, 2020; Chen et al., 2010].
    This paper asks a single question. Can the hierarchical-and-shrinkage structure that makes HRP
and the Cotton allocator useful be extended to the general mean–variance problem with arbitrary
µ without giving up its regularisation benefits, and what is the natural iterative counterpart? The
answer is three methods, each controlled by a shrinkage parameter γ ∈ [0, 1] that plays the same role
Cotton [2024] introduced—governing how much cross-asset covariance enters the allocation—and
each accepting an arbitrary signal.

1.2   Three methodological contributions
We present the three methods in order of empirical strength—weakest to strongest—and use the
display names HRP-µ, HRP-Σµ, and CRISP throughout.

Contribution 1: HRP-µ, a transparent signal-aware hierarchical allocator. HRP-µ
walks the same correlation dendrogram as classical HRP. At each internal node its representative
                                                     signed
portfolio is the signed inverse-variance portfolio ŵL,i    ∝ sign(µi )/σii2 , and between-child budgets
are set by the same 2 × 2 mean–variance system that underlies Cotton’s allocator. Because the
representative depends only on the diagonal variances {σii2 } and the signal signs {sign(µi )} inside a
block—never on within-cluster correlations—every leaf weight factors as a sign times a root-to-leaf
product of non-negative budgets, so the hierarchical audit trail that practitioners prize in classical
HRP is preserved. Proposition 4.2 shows that HRP-µ nests De Prado’s HRP exactly at γ = 0,
µ = 1, and the cost is O(N 2 ), a factor N cheaper than Cotton. Even on Cotton’s own µ = 1
problem, HRP-µ at γ > 0 improves on classical HRP out of sample and matches Cotton’s Sharpe at
roughly half Cotton’s γ, while avoiding the Schur-complement instability Cotton exhibits at small
T (Proposition 3.2).




                                                   5
Contribution 2: HRP-Σµ, the strongest tree-based method. HRP-Σµ keeps the HRP
tree and the 2 × 2 between-child split but replaces HRP-µ’s signed inverse-variance representative
with the local mean–variance optimum computed recursively on the sub-tree, using the full within-
cluster covariance ΣLL at every node. The representative is richer than HRP-µ’s—it captures
within-cluster hedging that the signed IVP cannot see—at the cost of the closed-form auditability.
The load-bearing algorithmic detail is the between-child normalisation: sum-to-one normalisation
of the same 2 × 2 system produces a sign-flip pathology (documented as a cautionary negative
result in Appendix C), whereas the L1 normalisation αk ← αkraw /(|αL raw | + |αraw |) is ray-invariant
                                                                               R
and sign-preserving (Lemmas 4.5 and 4.6). The cost is O(N ), matching HRP-µ; classical HRP
                                                             2

is recovered to cosine ≈ 0.992 at γ = 0, µ = 1, and exactly at tree depth ≤ 2 (Proposition 4.8).
In the synthetic Monte Carlo panels of Section 10 HRP-Σµ delivers 20–35% higher out-of-sample
Sharpe than HRP-µ on random signals and up to 180% higher on structural signals with sample
estimation, reaching roughly 90% of CRISP’s performance while staying strictly O(N 2 ).

Contribution 3: CRISP, an iterative shrinkage solver (headline). CRISP runs scalar
Gauss–Seidel on the shrunk mean–variance system Pγ w = µ, where Pγ = (1 − γ)D + γΣ and
D = diag(Σ). The shrinkage parameter interpolates between a pure diagonal solve at γ = 0
(signed inverse-variance weighting) and exact Markowitz at γ = 1. Gauss–Seidel on Pγ converges
unconditionally for every symmetric positive definite Σ and every γ ∈ [0, 1] (Theorem 5.2). The
convergence-rate result is new: at γ = 1 the sweep count required to reach relative direction error
ε is p = O(κ(C) log(1/ε)), controlled by the condition number of the correlation matrix rather
than of the covariance matrix itself, and in general p = O(κ(D−1 Pγ ) log(1/ε)) with κ(D−1 Pγ ) =
[(1 − γ) + γλ1 (C)]/[(1 − γ) + γλN (C)] interpolating monotonically from 1 at γ = 0 to κ(C) at γ = 1;
volatility dispersion does not enter the rate (Theorem 5.3). Correlation conditioning is bounded in
realistic equity universes, so this is what makes CRISP tractable at scale.
    At convergence CRISP produces Pγ−1 µ: Markowitz on the shrunk covariance Pγ . This places
CRISP in the linear-shrinkage family of Ledoit and Wolf [2003, 2004, 2017], with two structural
differences. First, its target is the diagonal D, so Pγ reproduces the variances of Σ exactly for
every γ and only correlations are shrunk—the reliable part of the covariance (per-asset variances,
each estimated from a single time series) is left alone and the unreliable part (pairwise correlations)
is regularised. Classical Ledoit–Wolf targets (scaled identity, single factor, constant correlation)
perturb the diagonal. Second, the shrinkage intensity γ is chosen to maximise out-of-sample portfolio
Sharpe rather than to minimise Frobenius loss on the estimator; Section 6 shows these are different
problems with different optima. In the synthetic Monte Carlo panels of Section 10 CRISP at
γ ∈ [0.3, 0.7] with 100 sweeps delivers 80–94% of oracle Sharpe uniformly across four covariance
regimes and T /N ∈ [0.6, 5], and dominates every benchmark on every panel.

1.3   Three supporting contributions
Adaptive γ ⋆ rule.    A bias–variance decomposition of expected OOS Sharpe yields the closed-form
rule
                                                      1
                                   γ⋆ ≈                           ,
                                           1 + c κ(C)2 N/(T IC2 )
whose comparative statics (Proposition 7.1) are qualitatively correct: γ ⋆ rises with the sample
length T and the information coefficient IC, and falls with conditioning difficulty κ(C) and universe
size N . Calibration on a 48-cell synthetic cube shows that the OOS Sharpe surface is nearly flat in
γ: the plateau of near-optimal values has median width 0.38 on [0, 1]. The formula’s practical value



                                                  6
is therefore explanatory—it rationalises why a fixed default γ ≈ 0.5 is robust and why a single knob
suffices—rather than prescriptive.

Three regularisation channels. CRISP regularises through three distinct channels (Remark 7.2).
Channel 1 is operator shrinkage via γ: the statistical channel that does most of the work. Channel 2
is convergence slack from a finite sweep count, which is a computational artefact rather than a
design choice. Channel 3 is implicit spectral truncation through early stopping, which is statistically
beneficial near γ = 1 because the low-eigenvalue directions of D−1 Pγ converge last and carry
the most estimation noise; in that regime CRISP is an iterative cousin of ridge regression on the
Markowitz system. At the recommended operating point (γ ≈ 0.5, p = 100) only Channel 1 is
materially active.

Out-of-sample evaluation. Every method comparison is out-of-sample. We run a synthetic
Monte Carlo study across four covariance regimes (factor, block, spiked, equicorrelation) and
T /N ∈ [0.6, 5], with both oracle and sample-mean signal treatments, against 1/N [DeMiguel,
Garlappi and Uppal, 2009], HRP, Cotton at several γ, direct Markowitz, and linear and non-linear
Ledoit–Wolf [Ledoit and Wolf, 2004, 2020], in addition to our three methods. Direction error appears
only as an in-sample tracking diagnostic; OOS Sharpe is the primary metric.

1.4   Memory, not speed
It is worth stating early what CRISP does and does not offer at the machine level. On tuned
BLAS—Apple M4 with Accelerate and a Numba-JIT CRISP—direct Cholesky is 48× faster than
CRISP at N = 500 and remains between 9× and 48× faster for N ∈ {500, . . . , 5,000} (Remark 5.7).
Extrapolating the trend on this hardware places the single-solve wall-clock crossover near N ≈ 45,000,
well outside realistic portfolio sizes. We do not claim a wall-clock advantage for CRISP.
    What CRISP offers structurally is memory. A factor-streaming implementation (Algorithm 3)
that never materialises Σ reduces working memory from O(N 2 ) to O(N K), where K is the number
of factors. At N = 30,000 and K = 20 the dense Σ occupies 7.2 GB; the factor stream uses
4.8 MB. Cholesky cannot exploit this reduction because its factorisation needs random access to the
full matrix. The honest case for CRISP is therefore stronger OOS Sharpe together with memory
scalability, not speed.

1.5   Road map
Section 2 fixes notation, sets up the ray view of mean–variance, and introduces the direction-error
diagnostic together with its sign-invariance caveat. Section 3 reviews HRP and the Cotton Schur
allocator and places both in the method landscape, including Cotton’s intermediate-γ instability
under estimation noise. Section 4 develops the two tree-based methods in a single frame—one tree,
two representatives, two methods: HRP-µ with the signed inverse-variance representative, HRP-Σµ
with the recursive local MVO. Section 5 is the headline theoretical section: it presents CRISP, proves
unconditional Gauss–Seidel convergence and the correlation-conditioning rate theorem, records the
early-stopping-as-spectral-truncation remark, describes the factor-streaming variant, and locates
CRISP within the Ledoit–Wolf family. Section 6 develops the perturbation theory of the shrinkage
trajectory, including a non-monotone-trajectory counter-example and an interior-γ ⋆ proposition
under explicit hypotheses. Section 7 derives the adaptive γ ⋆ rule and consolidates the three-channel
taxonomy. Section 8 presents the five-method comparative landscape and a practitioner’s guide.
Section 9 treats linear constraints through a projected CRISP. Section 10 reports the synthetic


                                                  7
Monte Carlo study in three parts: in-sample direction-error diagnostics, out-of-sample Sharpe panels,
and sweep-count and adaptive-γ ⋆ calibration. Section 11 discusses limitations, open problems, and
extensions, and Section 12 concludes. Readers primarily interested in using the methods can skip to
Sections 5, 4, and 10.

1.6   Relation to the literature
The paper connects six strands of research.

Hierarchical portfolio methods. López de Prado [2016] introduces HRP, and López de Prado
and Lewis [2019] develops companion tools for false-strategy detection. Raffinot [2018] studies
broader hierarchical-clustering allocation. Cotton [2024] provides the Schur-complement unification
that connects HRP to exact minimum variance through a single continuous parameter. Our HRP-µ
and HRP-Σµ extend this hierarchical framework to arbitrary µ at the same O(N 2 ) cost, and strictly
dominate HRP on its own µ = 1 problem whenever estimation error is present.

Covariance shrinkage. The Stein estimator [Stein, 1956] and its portfolio-theoretic descendants
[Ledoit and Wolf, 2003, 2004, 2017, 2020; Chen et al., 2010] shrink the sample covariance toward
a structured target to control low-eigenvalue estimation error. CRISP is a member of this family
with target D = diag(Σ), a choice that preserves variances identically and shrinks only correlations,
and with shrinkage intensity tuned for portfolio Sharpe rather than Frobenius loss on the estimator.
Both differences are structural; we develop them in Section 5.

Iterative and parametric portfolio methods. Brandt, Santa-Clara and Valkanov [2009]
parameterise the policy directly as a linear function of asset characteristics. Kozak, Nagel and
Santosh [2020] shrink the cross-section of factor returns through ridge and Bayesian regularisation.
DeMiguel, Garlappi and Uppal [2009] establish the 1/N benchmark that any proposed method must
outperform out of sample. CRISP differs from these methods by solving a shrunk Markowitz system
whose variances are preserved identically at every γ, so no asset is implicitly up- or down-volatilised
by the regulariser.

Signal integration and Bayesian portfolios. Black and Litterman [1992] combine an equilib-
rium prior with investor views through a Bayesian posterior; Grinold and Kahn [1999] formalise the
information-ratio decomposition of active management; and Barroso and Santa-Clara [2015] study
signal-conditioned portfolios in currency markets. We compare CRISP with Black–Litterman as
a candidate Bayesian reading in Section 5: both produce shrunk posterior weights, but CRISP is
driven by the single explicit γ knob rather than by a specified view covariance.

Numerical analysis of iterative methods. The classical iterative-solver literature [Hackbusch,
2016; Saad, 2003; Varga, 2000; Young, 1971; Ostrowski, 1954] supplies the unconditional-convergence
and rate results for symmetric positive definite Gauss–Seidel on which Theorems 5.2 and 5.3 rest.
The contribution of Theorem 5.3 is to extract the correlation-conditioning constant specific to the
portfolio setting and to translate the resulting rate into a concrete sweep count that is independent
of the universe size.




                                                  8
Factor models for covariance. Fama and French [1993] establish the pricing-factor representa-
tion. Fan, Liao and Mincheva [2013] develop POET for structured covariance estimation, Marchenko
and Pastur [1967] provide the spectral baseline for sample covariances, and Ledoit and Wolf [2020]
give the analytical non-linear-shrinkage counterpart. Our factor-streaming variant of CRISP exploits
a factor structure Σ = BΛB ⊤ + Didio to hold working memory at O(N K) without ever forming Σ,
which is what makes the method usable in universes where Cholesky’s random-access requirement is
the binding constraint.
    We do not replace any of these literatures. We supply an O(κ(C) N 2 log ε−1 ) iterative solver
that inherits HRP’s regularisation philosophy through its γ parameter, two signal-aware hierarchical
alternatives for tree-interpretable use cases, and a synthetic out-of-sample evaluation against the
standard benchmarks.


2     Notation and the direction view
This section does four things. It fixes the symbols that appear in the rest of the paper; it replaces
the usual relative-error metric with a scale-invariant direction error and flags the one way in which
that replacement is dangerous; it isolates the correlation conditioning κ(C) as the spectral invariant
that will control both the in-sample direction gap of the cheapest baseline and the sweep count of
CRISP; and it records a parallel-direction identity that exposes a family of signal vectors on which
every method in the paper returns the same ray. The last point is a pruning lemma: it cuts off an
entire class of otherwise plausible worst-case constructions.

2.1   Notation
Let N be the number of assets. The inputs to every method are a symmetric positive definite (SPD)
covariance matrix Σ ∈ RN ×N and an expected-return vector µ ∈ RN . The Markowitz portfolio is

                                            w⋆ = Σ−1 µ.                                            (1)

Write D = diag(Σ) for the diagonal matrix of variances and E = Σ − D for the off-diagonal part, so
Σ = D + E. The correlation matrix is

                                       C = D−1/2 Σ D−1/2 ,                                         (2)

which is SPD with tr(C) = N and eigenvalues λ1 ≥ · · · ≥ λN > 0. Throughout the paper,
interpolation between the diagonal D and the full covariance Σ is carried out by the shrinkage
operator
                            Pγ = (1 − γ) D + γ Σ,       γ ∈ [0, 1].                         (3)
Entrywise, (Pγ )ii = σii and (Pγ )ij = γ σij for i =
                                                   ̸ j: the diagonal is preserved unchanged at every
γ, and only the off-diagonal is shrunk. The endpoints are P0 = D and P1 = Σ. The asymmetry
between diagonal and off-diagonal is deliberate; it is what makes the preconditioned condition
number κ(D−1 Pγ ) tractable in Section 5 and what the adaptive rule of Section 7 exploits.

2.2   Markowitz as a ray
Equation (1) fixes a direction, not a point. Standard normalisations—budget ( i wi = 1), gross
                                                                                   P

(∥w∥1 = 1), fixed-volatility (w⊤ Σw = σ02 )—each pick a different representative of the ray

                                         {α Σ−1 µ : α > 0},                                        (4)

                                                  9
and for almost every downstream question—Sharpe, hedge ratio, relative ranking—it is the ray, not
the representative, that carries the content. A consequence is that the relative error ∥ŵ − w⋆ ∥/∥w⋆ ∥,
the textbook numerical-analysis summary, conflates geometric fidelity to the Markowitz direction
with the incidental choice of normaliser: two estimators that agree perfectly as rays can receive
arbitrarily different relative-error scores because they are rescaled differently. We therefore use a
metric that discards the scale entirely.

2.3   Direction error
Definition 2.1 (Direction error). For nonzero ŵ, w⋆ ∈ RN , let

                                                    (ŵ⊤ w⋆ )2
                              dir(ŵ, w⋆ ) = 1 −                = sin2 θ,                            (5)
                                                   ∥ŵ∥2 ∥w⋆ ∥2

where θ ∈ [0, π/2] is the angle between the lines through ŵ and w⋆ .

    By construction dir(ŵ, w⋆ ) ∈ [0, 1]: zero iff ŵ and w⋆ are collinear, one iff they are orthogonal,
and invariant under rescaling of either argument by any nonzero scalar. Scale invariance is what we
want: it lets us compare methods whose native outputs are budget-normalised, gross-normalised, or
left raw without having to stage an artificial normalisation step first.

2.4   Warning: direction error is sign-invariant
The same property that makes dir robust to normalisation makes it blind to sign. The squared
inner product in (5) gives
                                 dir(ŵ, w⋆ ) = dir(−ŵ, w⋆ ),                            (6)
so any method whose output can flip sign relative to the Markowitz direction will be flattered
by dir: a portfolio that points exactly opposite to w⋆ receives the same score as one that points
exactly along it. For methods whose sign relative to w⋆ is pinned by construction—HRP, Cotton,
HRP-µ, HRP-Σµ, and CRISP all fall in this category—this is harmless. For methods without that
guarantee it is not. The canonical example is the sum-normalised recursive MVO (the Method A1
of Appendix C): on the noiseless recovery problem it appears, on dir, to be tracking w⋆ well, while
in fact half the time it is delivering systematically negative out-of-sample Sharpe.
    For this reason we treat dir as a tracking diagnostic, not a quality metric. It is the right tool for
asking “does my method stay near the Markowitz ray as γ moves or as T grows?” It is the wrong
tool for ranking methods. The primary quality metric for ranking is out-of-sample Sharpe, and
Section 10 is organised around it for this reason.

2.5   Correlation conditioning as a difficulty diagnostic
The condition number κ(Σ) = λmax (Σ)/λmin (Σ) is the standard numerical summary of an SPD
matrix, but it is the wrong summary for the directional problem, because it mixes together two
effects of very different character: volatility dispersion (the spread of the diagonal of Σ), and
correlation conditioning (the spread of the eigenvalues of C). Direction recovery is only sensitive to
the second.

Proposition 2.2 (Correlation similarity). D−1 Σ is similar to C via the change of basis D−1/2 . In
particular,
                                      κ(D−1 Σ) = κ(C).                                          (7)


                                                   10
Proof sketch. A one-line substitution: D−1/2 (D−1 Σ)D1/2 = D−1/2 ΣD−1/2 = C. Similar matrices
share their spectrum, and C is SPD with strictly positive eigenvalues, so the (nonsingular) condition
numbers of D−1 Σ and C coincide. The full argument, including the check that both matrices are
nonsingular and a proper handling of the non-symmetric D−1 Σ, is given in Appendix A.

    Two downstream uses of Proposition 2.2 are worth flagging now. First, the in-sample direction
gap between the cheapest baseline µ/D (entrywise division of µ by the diagonal of Σ, equivalently
P0−1 µ) and the Markowitz target Σ−1 µ is controlled by κ(C) through the spectrum of D−1 Σ.
Second, the Gauss–Seidel sweep count of CRISP at γ = 1 scales as κ(C) up to logarithmic factors
(Theorem 5.3), not as κ(Σ). In both cases the volatility dispersion in D is irrelevant to the hardness
of the problem.
    This has a practical bite. Consider a regime with one high-volatility outlier asset: κ(Σ) can be
inflated by orders of magnitude while κ(C) is unchanged. Any reader who conflates the two will
place “hard” instances in the wrong part of the parameter space and will be surprised when CRISP
converges on them as fast as it does on nominally better-conditioned ones. The experiments of
Section 10 bake this distinction into the regime menagerie explicitly.
    To stratify synthetic experiments by actual difficulty rather than by nominal conditioning, we
define a dimensionless instance-level diagnostic:

                                  dirdiag (Σ, µ) = dir µ/D, Σ−1 µ ,                                 (8)
                                                                   


where µ/D is the entrywise quotient. dirdiag measures how far the cheapest baseline—ignore all
off-diagonal information—sits from the Markowitz direction on the instance (Σ, µ). Small values
mean the instance is essentially diagonal-solvable and every method will agree; large values mean
the off-diagonal carries most of the signal and the choice of method matters. Section 10 uses dirdiag
to stratify the synthetic Monte Carlo so that headline numbers are not dominated by easy cases.

2.6   The parallel-direction identity
For generic (Σ, µ) the curve γ 7→ Pγ−1 µ traces out a genuine path in RN : different values of γ
produce different directions, and one of the main questions of the paper is where on [0, 1] to evaluate
the curve. On one distinguished family of inputs, however, the curve collapses to a single ray. The
following lemma records this; the corollary draws out what it rules out.

Lemma 2.3 (Parallel-direction identity). Let v ∈ RN be an eigenvector of C with eigenvalue λ > 0,
and set µ = D1/2 v. Then for every γ ∈ [0, 1],
                                                    1
                                   Pγ−1 µ =                 D−1 µ.                                  (9)
                                              (1 − γ) + γ λ

    The proof is a direct calculation from the factorisation Pγ = D1/2 (1 − γ)I + γC D1/2 combined
                                                                                     

with Cv = λv, and is carried out in Appendix A. The coefficient [(1 − γ) + γλ]−1 is strictly positive,
so the entire trajectory {Pγ−1 µ : γ ∈ [0, 1]} lies on the common ray through D−1 µ.

Corollary 2.4 (Invariant rays). On inputs of the form µ = D1/2 v with v an eigenvector of C,
every allocation method studied in this paper—HRP, Cotton at every γ ∈ [0, 1], HRP-µ, HRP-Σµ,
CRISP at every γ ∈ [0, 1], and the diagonal solver P0−1 µ—produces a portfolio on the common ray
{α D−1 µ : α > 0}.




                                                  11
                          Table 1: Notation used throughout the paper.

      Symbol             Definition                         Role
      N                  number of assets                   problem size
      Σ                  SPD covariance matrix, N × N       risk model
      D = diag(Σ)        diagonal of Σ (variances)          idiosyncratic risk
      E =Σ−D             off-diagonal part of Σ             cross-asset dependence
      C = D−1/2 ΣD−1/2   correlation matrix, tr(C) = N      scale-free risk structure
      κ(C)               λ1 (C)/λN (C)                      correlation conditioning (difficulty)
      µ ∈ RN             expected-return (signal) vector    input
      w⋆ = Σ−1 µ         Markowitz portfolio                target direction
      Pγ                 (1 − γ)D + γΣ, γ ∈ [0, 1]          shrinkage operator
      dir(ŵ, w⋆ )       1 − (ŵ⊤ w⋆ )2 /(∥ŵ∥2 ∥w⋆ ∥2 )    direction error (tracking)
      dirdiag (Σ, µ)     dir(µ/D, Σ−1 µ)                    instance difficulty diagnostic


    Two caveats deserve underlining. First, Corollary 2.4 is about direction only: the methods agree
on the ray in RN along which the portfolio points, not on its magnitude or normalisation. They
disagree on where on that ray the output sits, and for Sharpe comparisons where budget or gross
normalisation matters, the ray agreement is not the end of the story. Second—and this is what
we will use repeatedly—the corollary forecloses a specific class of worst-case constructions. It is
natural, when looking for inputs on which a shrinkage method fails, to align µ with an eigenvector
of C under the slogan “Σ−1 amplifies small eigenvectors.” But that slogan is a statement about
scale, not direction: Lemma 2.3 says every single-eigenvector µ gives every method in the family the
same direction, so any direction-based worst case must excite at least two eigenspaces of C. We
call the family {D1/2 v : v eigenvector of C} the invariant rays of the shrinkage family; they are
precisely the directions on which γ has no effect at all.

2.7     Notation summary
Table 1 collects the symbols introduced above. The spectral objects C, κ(C), Pγ , dir, and dirdiag
recur in every subsequent section; Lemma 2.3 is invoked in Section 6 to exclude single-eigenvector
constructions from the trajectory analysis and in Section 10 to generate signal vectors that do not
trivially collapse.


3     Background: HRP and Cotton
Every construction in the remainder of this paper is benchmarked against two prior allocators: the
Hierarchical Risk Parity (HRP) algorithm of López de Prado [2016] and the Schur-complementary
allocation of Cotton [2024]. Each is a minimum-variance construction pinned to the signal µ = 1.
We re-present them in the notation of Section 2, isolate the distinctions that tend to get blurred in
applied treatments, and then document a concrete numerical fragility of Cotton’s γ-continuum on
sample covariances. A short motivation for the general-µ lift and a preview of the method landscape
close the section.




                                                 12
3.1   Hierarchical Risk Parity
Inputs and outputs. HRP consumes an estimated covariance Σ ∈ RN ×N and returns a long-only,
fully-invested weight vector w ∈ RN with wi > 0 and i wi = 1. No matrix inversion is performed,
                                                      P

no expected-return vector is consulted, and no hyperparameter is tuned. The dominant cost is the
one-off clustering pass; the recursion on the dendrogram itself is O(N 2 ).

Three steps. The construction factors into a clustering stage, a cosmetic re-ordering, and a
recursive budget split.

1. Correlation-distance clustering. Form the correlation matrix C = D−1/2 Σ D−1/2 with D =
   diag(Σ), set                              q
                                          dij =     1
                                                        1 − Cij ,                                  (10)
                                                               
                                                    2

   and apply an agglomerative linkage (Ward is our default) to produce a binary dendrogram T .
2. Quasi-diagonalisation. Re-index the assets so that leaves co-located in T are contiguous. The
   re-ordering leaves the spectrum of Σ unchanged but arranges correlated names into block-diagonal-
   like neighbourhoods.
3. Recursive bisection. Descend T from the root. At an internal node with children L and R, form
   the flat inverse-variance portfolio (IVP) on each child,

                                                1/Σii
                                     bi = P
                                     w                   ,      i ∈ L,                             (11)
                                               j∈L 1/Σjj

   and compute the scalar cluster variance
                                                  ⊤
                                           vL = w
                                                bL  ΣLL w
                                                        bL ,                                       (12)

   where ΣLL is the |L|×|L| diagonal block. The sibling vR is defined identically. The between-branch
   budget split is inverse cluster variance,

                                           1/vL
                                αL =                ,        αR = 1 − αL ,                         (13)
                                        1/vL + 1/vR

   and the final weight of leaf i is the product of the α-factors encountered on its unique root-to-leaf
   path, starting from unit budget at the root.

  A fully worked four-asset example—explicit vL , vR , αL , and leaf weights—is collected in
Appendix B.

The flat IVP is a scoring device, not an output. A persistent misreading of HRP identifies
the flat weights (11) with the allocator itself inside each sub-tree. They are not. Equation (11)
exists solely to manufacture the scalar vL that feeds (13); it does not appear in the final portfolio.
The weights that do appear are the products of α-factors along root-to-leaf paths, which differ in
general from any flat IVP applied at a single cluster scale. This distinction is load-bearing: the
signal-aware tree methods of Section 4 retain HRP’s between-branch split verbatim and intervene
exclusively on the representative portfolio used to score a cluster.




                                                  13
What HRP is not. Four negatives are worth stating explicitly, because each one motivates a
later contribution.

• Not an optimiser. No explicit quadratic form is minimised. The split rule (13) is a regularisation-
  flavoured heuristic; there is no first-order condition it satisfies.
• Not signal-aware. µ does not appear anywhere in steps 1–3. A practitioner who carries a
  non-trivial return forecast must discard it to use HRP.
• Not cross-branch aware. The cluster variance vL depends only on the diagonal block ΣLL . The
  off-diagonal block ΣLR coupling the two children is simply ignored. This is the information
  Cotton [2024] sets out to reinstate.
• Not an approximation to Markowitz. Even when the correct signal is 1, HRP does not approximate
  Σ−1 1. The gap is structural, not small: on the four-asset reference covariance of Appendix B the
  two portfolios differ by roughly 49% in relative direction.

3.2   Cotton’s Schur-complement allocation
Cotton [2024] rebuilds HRP’s recursion from the block-inversion identity and parameterises the
result by a single scalar γ ∈ [0, 1]. The construction closes HRP’s cross-branch blindness at γ = 1;
the intermediate values are where the trouble lives.

Block inversion. Partition the quasi-diagonalised covariance according to the first binary split of
the dendrogram,                     !
                             A B
                    Σ =               ,    A ∈ RnL ×nL , D ∈ RnR ×nR .                        (14)
                            B⊤ D

The Schur identity factors Σ−1 1 block-by-block,

                         (Ac )−1 bA
                                    !
             Σ−1 1 =                ,       Ac = A − BD−1 B ⊤ ,     Dc = D − B ⊤ A−1 B,            (15)
                         (Dc )−1 bD

with corrected right-hand sides bA = 1nL − BD−1 1nR and bD = 1nR − B ⊤ A−1 1nL . Equation (15) is
a tautology, but it has HRP’s recursive shape: two sub-systems, one per child, coupled only through
the Schur correction.

From block inversion to a recursive split.          Define the quadratic fitness
                                           1
                                                 = b⊤ Q−1 b.                                       (16)
                                         ν(Q, b)

This scalar plays the role that inverse cluster variance 1/vL plays in HRP. The between-branch split
becomes
                                         1/ν(Ac , bA )
                        αL =                                 ,   αR = 1 − αL ,                 (17)
                                1/ν(A , bA ) + 1/ν(Dc , bD )
                                       c

in exact parallel with (13). The recursion then enters each child with the Schur-complemented
block (Ac on the left, Dc on the right) in place of the bare diagonal block, and with the corrected
right-hand side in place of 1. HRP’s flat IVP is replaced, at each internal node, by a full block solve;
the tree scaffolding itself is untouched.



                                                  14
The γ-parameter. Cotton [2024] introduces a continuous scalar γ ∈ [0, 1] that interpolates how
much of the cross-block correction to apply,

                   Ac (γ) = A − γ BD−1 B ⊤ ,          bA (γ) = 1nL − γ BD−1 1nR ,               (18)

with the symmetric definitions Dc (γ), bD (γ). The endpoints are interpretable. At γ = 0, Ac (0) = A
and bA (0) = 1nL : the allocator becomes a hierarchical minimum-variance solver that sees only
within-branch information. At γ = 1, equation (18) reproduces the Schur complement of (15)
exactly, and the full recursion returns Σ−1 1.

Cotton at γ = 0 is not HRP. The tree is the same in both methods; the within-branch scoring
rule is different. HRP uses the flat IVP representative (11) to compute its cluster variance. Cotton
at γ = 0 instead solves A−1 1nL on the undisturbed diagonal block. These coincide if and only
if every sub-block encountered in the recursion is itself diagonal, which is non-generic. On the
four-asset reference covariance of Appendix B the two portfolios differ by roughly 49% in relative
direction. Any claim of the form “Cotton at γ = 0 recovers HRP” should therefore be read as a
structural approximation, not an identity.

Cost. At each internal node Cotton performs a block solve to form D−1 B ⊤ , which is the dominant
work in the Schur augmentation. Summed over a balanced binary tree of depth log2 N , the total
cost is O(N 3 /6), dominated by the top-level complement. This is a constant-factor improvement
over the O(N 3 ) of a dense Σ−1 but has the same asymptotic rate. The numerical behaviour we
document below traces to exactly these nested block solves.

The µ = 1 ceiling. The entire construction (15)–(18) is a block rearrangement of Σ−1 1. The
corrected right-hand side bA = 1 − γBD−1 1 is a corrected all-ones vector, not a generic signal, and
the clean telescoping that produces the recursive split does not survive replacing 1 by a non-trivial
µ without re-deriving the cross-block correction. Cotton [2024] does not attempt this generalisation.
Closing the gap—without paying the full O(N 3 ) cost—is one of the points of Sections 4 and 5.

3.3   Cotton under estimation noise
The two propositions in this subsection separate a mathematical statement about the population
covariance from an empirical statement about sample covariances. The second point is easy to
misread as criticism of Cotton [2024]; it is not. Cotton’s γ-continuum is mathematically elegant,
and the instability documented below is a property of sample-covariance block inversion at small T ,
not a defect of the derivation.
Proposition 3.1 (Cotton is SPD on the population covariance). Let Σ be SPD with the block
partition of (14). Then the augmented Schur block Ac (γ) = A − γ BD−1 B ⊤ is SPD for every
γ ∈ [0, 1].
Proof sketch. Rewrite Ac (γ) = (1 − γ) A + γ (A − BD−1 B ⊤ ). The first summand is a principal
submatrix of the SPD Σ and is therefore SPD. The second summand is the Schur complement of
D in Σ and is SPD by the standard block-inversion identity. A convex combination of two SPD
matrices is SPD. The full argument appears in Appendix A.

    Proposition 3.1 rules out any population-level pathology: at every γ ∈ [0, 1] the augmented
block is SPD and the recursion is well-defined. The difficulty begins when Σ is replaced by a sample
estimate.

                                                 15
Proposition 3.2 (Cotton instability under estimation noise). Let Σ
                                                                 b be an SPD estimate of Σ (for
example, sample covariance plus a small ridge), partitioned as Σ
                                                               b = Ab B
                                                                       ⊤
                                                                         b  at an internal node.
                                                                     B D
                                                                     b   b
Then:

  (i) The condition number of the augmented Schur block satisfies the bound

                                                               λmax (A)
                                                                     b
                                κ Abc (γ) ≤                                                      (19)
                                        
                                                                              ,
                                                λmin (A)     b 2 λmin (D)
                                                                          
                                                      b − γ ∥B∥        b

      whenever the denominator is positive. In particular, κ(Abc (γ)) diverges as γ approaches the
      critical value γcrit = λmin (A)
                                   b λmin (D)   b 2.
                                           b / ∥B∥

  (ii) Because Cotton recurses into each child using Abc (γ) as the new covariance, a worst-case
       error-propagation argument bounds the effective condition number at depth d by the product
                                                         d
                                            κeff (d) ≤         κ Abck (γ) .                      (20)
                                                         Y                

                                                         k=1

      For a balanced tree of depth d = ⌈log2 N ⌉, the right-hand side can grow exponentially with d.
      Equation (20) is a propagation bound, not an algebraic identity; it becomes tight when the
      level-k perturbations align with the poorly conditioned directions of Abck .
 (iii) By contrast, a direct Markowitz solve inverts Σ
                                                     b exactly once, with relative error proportional
       to the single condition number κ(Σ).
                                        b

Proof sketch. Part (i) is Weyl’s inequality: λmin (A−γM
                                                   b      ) ≥ λmin (A)−γ
                                                                    b    ∥M ∥, where M = BbDb −1 B
                                                                                                 b⊤
is PSD with ∥M ∥ ≤ ∥B∥b /λmin (D);
                          2       b λmax is non-increasing as the PSD perturbation grows, supplying
the numerator. Part (ii) is a level-by-level perturbation expansion: a relative error δk at level
k is fed into the (k+1)-st block solve and is amplified by at most κ(Abck+1 ), so errors compound
multiplicatively in the worst case. Part (iii) is the standard one-step Banach perturbation bound.
Full details in Appendix A.

Numerical verification. The bound (20) is not an asymptotic curiosity. On the base-case
covariance used throughout the paper’s Monte Carlo studies (equicorrelated blocks, N = 100), direct
Markowitz at T = 60 gives κ(Σ) b ≈ 1.6 × 104 . The product of Schur-complement condition numbers
that Cotton accumulates across the 99 internal nodes of the tree reaches ∼ 1034 at γ = 0.5—thirty
orders of magnitude worse than the one-shot direct solve. Quadrupling the sample to T = 240
barely helps: the product is ∼ 1031 against a direct κ ≈ 596. The operational consequence is visible
in Table 19: at intermediate γ, Cotton produces realised out-of-sample volatility 10–30× the oracle
minimum-variance level on a non-negligible fraction of Monte Carlo trials, whereas direct Markowitz
on the same samples does not.
    The takeaway is narrow and operational. Cotton’s γ-continuum is a correct interpolation
between a hierarchical regulariser at γ = 0 and the exact minimum-variance portfolio at γ = 1. The
instability at intermediate γ reflects the fact that a recursion of sample-covariance block inversions
accumulates condition-number damage that a single sample inverse does not. In practice, Cotton is
most safely used at its two endpoints; interpolating values do not inherit the numerical robustness
one might naively expect from block-wise regularisation.




                                                    16
3.4   Why extend to general µ?
HRP and Cotton together give a clean story for µ = 1. But that signal is, in applied portfolio
construction, the degenerate corner of the mean–variance problem. Four representative settings
make the point.

Quant equity and factor investing. Cross-sectional factor signals—momentum, value, quality,
earnings revisions, low-volatility—produce heterogeneous expected returns across names, and the
entire point of a factor model is that µ =
                                         ̸ 1. An allocator that ignores µ throws away the primary
input before the optimisation begins.

Multi-signal integration. Modern quant pipelines aggregate many orthogonalised signals into a
composite alpha [Grinold and Kahn, 1999]. The composite is a rich µ; the portfolio stage is asked
to weigh it against covariance risk. A signal-blind allocator is simply inadmissible in this context.

Tactical asset allocation. Multi-asset allocators take views on expected returns at the asset-class
level—equities versus bonds versus commodities versus alternatives—and expect the optimiser to
translate those views into positions. µ is low-dimensional here but highly informative; setting it to
1 is not a simplification, it is a replacement of the problem.

Black–Litterman view integration. The Black–Litterman framework [Black and Litterman,
1992] returns a posterior µ that encodes a prior together with investor views. The value of the
framework is entirely in that posterior; an allocator that discards it is not solving the same problem.
   In each case µ = 1 is not a neutral default. It is an active discarding of the most informative
input, and any method restricted to it is, by construction, inapplicable to the bulk of active portfolio
construction.

3.5   Method landscape
Table 2 previews the methods studied in this paper relative to HRP and Cotton. Two columns
carry most of the discriminatory load: the Signal column (whether the method accepts any µ
or is locked to 1), and the Cost column (the asymptotic work per solve). HRP and Cotton sit
at the “minimum-variance only” end. Direct Markowitz sits at the opposite extreme: general µ,
no regularisation, full O(N 3 ). The contributions of the present paper—HRP-µ, HRP-Σµ, and
CRISP—populate the missing middle of the table.
    HRP-µ occupies the “hierarchical, signal-aware, flat within-cluster” cell. HRP-Σµ upgrades the
within-cluster representative to a full mean–variance solve on the diagonal block, which turns out to
recover most of what direct Markowitz provides at O(N 2 ) cost. CRISP abandons the tree scaffolding
in favour of a preconditioned scalar Gauss–Seidel solver for Pγ w = µ with Pγ = (1 − γ) diag(Σ) + γ Σ;
its per-sweep cost is O(N 2 ) and its sweep count scales with the preconditioned conditioning
κ(diag(Σ)−1 Pγ ), which interpolates between 1 at γ = 0 and κ(C) at γ = 1. Sections 4–5 develop
these three methods in turn; Section 8 returns to the landscape with the full analytical and empirical
picture assembled.




                                                  17
Table 2: Method landscape. HRP and Cotton are minimum-variance-only baselines. HRP-µ and
HRP-Σµ are the tree-based signal-aware contributions; CRISP is the headline iterative contribution.
Direct Markowitz is the dense-inversion baseline. The within-cluster row describes the representative
portfolio used to score a sub-tree, and the cross-branch row describes how, if at all, information
from the off-diagonal block ΣLR enters the between-branch split.

                     HRP           Cotton         HRP-µ          HRP-Σµ          CRISP           Direct
Signal              1 only         1 only           any µ          any µ      any µ            any µ
Tree                 Ward          Ward             Ward           Ward        —                 —
Cross-branch           —           Schur           scalar c       scalar c     —                 —
Within-cluster     flat IVP       full A−1        flat IVP       full ΣLL      —              full Σ−1
Cost                O(N 2 )       O(N 3 /6)        O(N 2 )        O(N 2 )  O κ(C) N 2 log 1ε O(N 3 )
                                                                                            

Role               baseline       baseline      contribution   recommended headline           baseline
                                                                    tree


4     Tree-based signal-aware allocation
Section 3 showed that López de Prado [2016] HRP and the Cotton [2024] Schur allocator share
a single hierarchical skeleton: at every internal node of a correlation dendrogram, the allocator
solves a 2 × 2 between-branch problem to decide how budget is split between the two children, and
then recurses. Under the minimum-variance restriction µ = 1 the two methods are endpoints of a
γ-continuum on that skeleton. The purpose of this section is to extend the same skeleton to an
arbitrary signal µ ∈ RN and to turn the choice of the representative portfolio at each node into the
main design variable of the tree.
    Two allocators emerge from this analysis. HRP-µ (Section 4.3) is the transparent one: it uses a
signed inverse-variance portfolio as the representative, which preserves the block-diagonal recovery of
De Prado HRP at µ = 1 and is provably stable for arbitrary signal vectors. HRP-Σµ (Section 4.4) is
the strongest tree method we know: it uses a recursive mean–variance optimum as the representative
and rescues the natural but sign-pathological recursion of Appendix C by replacing sum-to-one with
L1 normalisation. Both methods cost O(N 2 ), both nest HRP at their γ = 0, µ = 1 limits, and both
carry an explicit signal through the tree in a direction-consistent way.
    The section closes with two short remarks that tie the construction to the rest of the paper:
why iterating the tree pass diverges (which motivates CRISP in Section 5), and how the tree-based
methods relate to the negative result on sum-normalised recursive MVO that is documented in full
in Appendix C.

4.1   The 2 × 2 between-branch system
Fix a correlation dendrogram T on N assets and an internal node with children L, R of sizes |L| and
|R|. A hierarchical allocator assigns scalar budget fractions αL , αR at the node and then recurses
into each child. The final weight placed on leaf i ∈ L is αL · ŵL,i , where ŵL ∈ R|L| is a representative
portfolio for branch L, and symmetrically for R. The representative is the one-dimensional summary
of the branch that the parent node sees; it is the object whose choice we study below.
    Given ŵL and ŵR , the node-level mean–variance problem on the two scalar unknowns (αL , αR )
is                                                 !      !                       !
                                        v
                                            L γc      αL
                                                                          α
                                                                                L
                       min   1
                                 αL αR                       − sL sR                ,                  (21)
                      αL ,αR 2             γc vR      αR                       αR


                                                    18
with scalar cluster statistics
                                         ⊤                                     ⊤                        ⊤
                                  vL = ŵL ΣLL ŵL ,                    sL = ŵL µL ,             c = ŵL ΣLR ŵR ,                            (22)

and their R-analogues. The parameter γ ∈ [0, 1] controls how much of the between-branch covariance
enters the node-level decision: γ = 0 decouples the children (the HRP regime), γ = 1 retains the full
coupling (the Markowitz regime on the two-dimensional subspace spanned by ŵL , ŵR ). Cramer’s
rule gives the closed-form solution
                                                      vR sL − γc sR                               vL sR − γc sL
                                        raw
                                       αL   =                         ,               raw
                                                                                     αR   =                       .                            (23)
                                                       vL vR − γ 2 c2                              vL vR − γ 2 c2

Equations (21)–(23) are the same 2 × 2 system used by every allocator in this section; they differ
only in how the raw budgets are normalised and in how the representative portfolios ŵL , ŵR are
constructed.

The design question. Everything that follows turns on a single choice: what representative
portfolio ŵL should the tree use? The representative decides what a branch looks like to its parent.
A bad choice makes the aggregate signal sL collapse under sign cancellation (destabilising Cramer’s
rule), or loses signal direction during between-branch normalisation, or throws away within-cluster
covariance information that is actually available. A good choice does none of these things. The
next subsection catalogues three candidates; the two subsequent subsections develop the two that
survive.

4.2         Three candidate representatives
Table 3 lists three natural choices for ŵL .
Table 3: Three candidate representative portfolios. Each gives rise to a distinct tree-based allocator via equations (21)–(23). Only (iii) and
(ii-with-L1 ) are robust for general µ.

          Representative ŵL,i                            Within-cluster info                     Resulting allocator
 (i)      Flat IVP: (1/σii2 )  j∈L 1/σjj
                                          2               diagonal only; signal-blind             HRP (Section 3.1), unstable under mixed-sign µ
                            P

 (ii)     Recursive MVO: bottom-up solve        of (23)   full ΣLL                                HRP-Σµ with L1 norm; sum-norm is sign-pathological
 (iii)    Signed IVP: sign(µi ) · (1/σii2 )   j∈L 1/σjj
                                                      2   diagonal only; signal-aware via signs   HRP-µ (Section 4.3)
                                            P




         We discuss each candidate in turn.

(i) Flat IVP. The flat inverse-variance portfolio recovers De Prado HRP at γ = 0, µ = 1, and is
a natural starting point. It fails in general because its aggregate branch signal is not sign-protected.

Proposition 4.1 (Flat IVP instability under mixed-sign µ). The flat-IVP aggregate signal

                                                                                µi /σii2
                                                                           P
                                                                sflat
                                                                 L       = Pi∈L                                                                (24)
                                                                                 j∈L 1/σjj
                                                                                     2


is not bounded away from zero under heterogeneous signals: for every ε > 0 and every variance
profile on L there exists a signal vector µL with maxi |µi | = 1 such that |sflat            flat
                                                                             L | < ε. When |sL | is of
order ε in (23), the numerators are O(ε) while the denominator is O(1), so the normalised budget
αL is driven by numerical noise. Cascaded through log2 N tree levels, the resulting direction error is
uncontrolled: empirically (Appendix E, Table 30) the flat-IVP direction error is 0.84–1.00 uniformly
across regimes, i.e. the output portfolio is essentially orthogonal to the Markowitz direction.

                                                                                19
Proof sketch. For any variance profile, choose µi ∈ {−1, +1} so that the weighted sum i µi /σii2 is
                                                                                          P

as close to zero as the grid of sign patterns allows; density gives the ε bound. Substituting into
Cramer’s rule (23) yields the stated O(ε/1) scaling. The full proof and explicit constructions are in
Appendix A.

    Proposition 4.1 is a clean structural statement: the flat IVP is signal-blind by construction
(it never sees µ), so the only way µ enters the tree pass is through the aggregate signal sL , and
that aggregate collapses whenever positive and negative signals coexist inside a branch. Long-only
problems do not exhibit the failure, which is why it was not visible in López de Prado [2016];
long–short problems do, and they are the rule rather than the exception in practice.

(ii) Recursive MVO. Using a local mean–variance optimum as the representative is the concep-
tually strongest choice: every branch sees its own optimum, using the full within-cluster covariance
ΣLL . The construction is only stable, however, if the between-branch normalisation step preserves
sign. Sum-to-one normalisation (dividing αL raw , αraw by their signed sum) fails: when αraw +αraw < 0,
                                                   R                                     L     R
dividing flips both signs, and these flips cascade through log2 N tree levels. This is the pathology
documented in Appendix C (and recorded there as “method A1”); it produces negative cosine
similarity to the Markowitz direction in 45–52% of draws on the synthetic panels of Section 10.
We do not recommend this construction; we study it in detail in Appendix C because its failure
motivates the L1 fix in HRP-Σµ.

(iii) Signed IVP. The third candidate keeps the inverse-variance magnitudes of (i) but takes the
signs from µ. The aggregate signal becomes

                                                    |µi |/σii2
                                               P
                                   ssigned   = Pi∈L            ≥ 0,
                                                   j∈L 1/σjj
                                    L                     2


a weighted average of |µi | rather than of µi . Sign cancellation cannot drive this quantity to zero.
Candidate (iii) is the representative used by HRP-µ in the next subsection.
     The three candidates cleanly separate the two failure modes that a tree-based signal-aware
allocator must avoid: aggregate-signal collapse (which kills (i)) and between-branch sign flips (which
kill the natural sum-normalised version of (ii)). HRP-µ handles the former by taking absolute values
at the representative level; HRP-Σµ handles the latter by taking absolute values at the normaliser
level.

4.3   HRP-µ: transparent signal-aware HRP
HRP-µ is the tree-based allocator built from candidate (iii). It is the simplest non-trivial extension
of De Prado HRP that carries an explicit signal, and the only one that recovers HRP exactly at
µ = 1.

Definition.    At every internal node, take the representative to be the signed inverse-variance
portfolio,
                               signed                1/σii2
                             ŵL,i    = sign(µi ) P         2 ,       i ∈ L,                      (25)
                                                    j∈L 1/σjj

with the convention sign(0) = +1. Solve the 2 × 2 system (23) and normalise (αL , αR ) to sum to
one (both are non-negative because the signed representative makes sL , sR ≥ 0, so there is no sign



                                                   20
pathology to fix at the between-branch level). At each leaf i, emit the final weight

                                       wi = budgeti · sign(µi ),

where budgeti is the cumulative product of the non-negative α-factors along the root-to-leaf path.
The leaf-level sign multiplication is essential: without it, the allocator is long-only regardless of µ
(because the signed IVP is sign-blind at the branch level).

Properties.

Proposition 4.2 (De Prado recovery). At γ = 0 and µ = 1, HRP-µ produces exactly the López de
Prado [2016] HRP weights.

Proof sketch. At µ = 1, sign(µi ) = +1 everywhere, so the signed IVP (25) reduces to the flat
IVP. At γ = 0 the 2 × 2 system decouples and Cramer’s rule gives αL ∝ 1/vL , αR ∝ 1/vR ; after
normalisation αL = vR /(vL + vR ), the inverse cluster-variance split of De Prado HRP. The leaf-level
sign multiplier is +1, so no direction is added. Full proof in Appendix A.

Proposition 4.3 (Aggregate-signal stability). For every internal node L of the tree,

                                                    |µi |/σii2
                                               P
                                    sHRP-µ   = Pi∈L            ≥ 0,
                                                   j∈L 1/σjj
                                     L                    2


with equality iff µi = 0 for every i ∈ L. Hence the Cramer’s rule denominator in (23) cannot be
driven to zero by sign cancellation in µ.
                                  signed⊤
Proof sketch. The inner product ŵL       µL replaces µi with sign(µi )µi = |µi |. The resulting sum
is a convex combination of non-negative terms. Full proof in Appendix A.

    Proposition 4.3 is the structural counterpart of Proposition 4.1: replacing the flat IVP with the
signed IVP removes the one mechanism by which the aggregate signal could collapse. The price
          signed
is that ŵL      is no longer a portfolio in the ordinary sense (its entries have mixed signs); it is an
object whose role is purely to be the one-dimensional summary that the parent sees.

Proposition 4.4 (Hedging awareness). Fix a branch L and two assets i, j ∈ L with µi > 0 > µj
and Σij > 0. The (i, j) contribution to the cluster variance vLHRP-µ is strictly smaller than the
corresponding contribution to vLflat ; in fact the two have opposite signs. If the branch contains no
compensating structure, vLHRP-µ < vLflat .

Proof sketch. The (i, j) cross term in vLflat is 2 ŵiflat ŵjflat Σij > 0. In vLHRP-µ the same cross term
carries the extra factor sign(µi ) sign(µj ) = −1 and is therefore strictly negative. Diagonal terms are
unchanged because sign(µi )2 = 1. Full proof in Appendix A.

    Proposition 4.4 is the reason HRP-µ deserves to be called hedging-aware. At every internal node
where the signal prescribes an opposite-direction pair on positively correlated assets, the signed IVP
cluster variance automatically exploits the hedge, whereas the flat IVP variance does not. This is
the hierarchical analogue of cash-neutral risk parity.




                                                   21
4.3.1    Signed Hierarchical Signal Parity (HSP)
At γ = 0 the cross-branch term drops out of (23) and the HRP-µ budget split collapses to a scalar
ratio of signal-to-variance statistics,

                                                    sHRP-µ /vLHRP-µ
                               HSP
                              αL   =                 L
                                                                                 .                          (26)
                                          sHRP-µ
                                           L     /vLHRP-µ + sHRP-µ
                                                             R
                                                                     HRP-µ
                                                                   /vR

We call the resulting allocator signed Hierarchical Signal Parity, abbreviated HSP. It is the γ = 0
endpoint of HRP-µ, reduces to De Prado HRP at µ = 1 by Proposition 4.2, and is a drop-in upgrade
for practitioners currently running HRP who now hold a signal: same dendrogram, same O(N 2 )
cost, same block-diagonal interpretation, with the signal carried stably through the tree. We return
to HSP as a standalone construction worth deploying independently of the γ > 0 pass in Section 11.

4.3.2    Cost comparison
HRP-µ’s central cost property is that it compresses the |L| × |R| cross-block covariance ΣLR into a
                    signed⊤       signed
single scalar c = ŵL       ΣLR ŵR      . Table 4 places it beside HRP, Cotton, and HRP-Σµ.

         Table 4: Cost of the hierarchical allocators on a balanced dendrogram over N
         assets. D and B denote the block-diagonal and off-diagonal parts of Σ in the
         Cotton notation of Section 3.2.

          Method                                        Cross-branch information            Cost
          HRP (γ = 0) [López de Prado, 2016]            none (block diagonal)               O(N 2 )
          Cotton (γ > 0) [Cotton, 2024]                 D−1 B ⊤ (block inversion)           O(N 3 /6)
                                                          signed⊤       signed
          HRP-µ (γ > 0, Section 4.3)                    ŵL       ΣLR ŵR      (scalar)     O(N 2 )
          HRP-Σµ (γ > 0, Section 4.4)                     mvo⊤
                                                        ŵL     ΣLR ŵR (scalar)
                                                                      mvo                   O(N 2 )
            HRP-µ and HRP-Σµ share an O(N 2 ) cost at the price of compressing ΣLR into a single
            scalar at every node. They are different γ-continua from Cotton’s, not faster implementations
            of the same object; the approximation gap is documented empirically in Section 10.



4.4     HRP-Σµ: recursive MVO with L1 normalisation
HRP-µ’s signed IVP representative is cheap and stable but uses only the marginal variances σii
within each cluster. The full within-cluster covariance ΣLL is available and, empirically, worth
exploiting. The natural construction is candidate (ii) of Section 4.2: bottom-up recursive MVO,
with each node’s representative set to the output of the solve one level down. The obstacle is that
candidate (ii) is sign-pathological under sum-to-one normalisation (Appendix C). HRP-Σµ resolves
this by replacing sum-to-one normalisation with L1 normalisation at every node. The change is a
single line of code; its consequence is a 0% rather than 45–52% negative-cosine rate on the structural
synthetic panels.

Motivation for L1 . The failure mechanism in Appendix C is precise: when αL           raw + αraw < 0,
                                                                                              R
dividing by the signed sum flips both signs; the flips cascade through O(log N ) tree levels and, by
parity, produce an output portfolio that is either parallel or antiparallel to the “correct” direction
in a fraction of cases that approaches 1/2 under noise. The fix has to keep the normaliser strictly
positive. The minimal modification is to divide by |αL raw | + |αraw | instead.
                                                                 R


                                                       22
Algorithm 1 HRP-Σµ(Σ, µ, T , γ): recursive MVO tree pass with L1 normalisation.
Require: SPD covariance Σ ∈ RN ×N ; signal µ ∈ RN ; binary tree T ; coupling γ ∈ [0, 1].
Ensure: Weight vector w ∈ RN .
 1: function Recurse(node n)
 2:    if n is a leaf (asset i) then
 3:        return (ŵn = 1, vn = σii2 , sn = µi )
 4:    end if
 5:    (ŵL , vL , sL ) ← Recurse(left(n))
 6:    (ŵR , vR , sR ) ← Recurse(right(n))
 7:    c ← ŵL ⊤Σ
                    LR ŵR                                                  ▷ cross-block scalar
 8:    ∆ ← vL vR − γ c    2  2

 9:    αLraw ← (v s − γ c s )/∆                                            ▷ Cramer’s rule (23)
                    R L          R
10:    αRraw ← (v s − γ c s )/∆
                    L R          L
11:    Z ← |αL   raw | + |αraw |                                       ▷ L1 normaliser, cf. (27)
                            R
12:               raw
       αL ← αL /Z; αR ← αR /Z      raw

13:    ŵn ← (αL ŵL , αR ŵR )                                        ▷ stacked representative
14:    vn ← ŵn⊤ Σnn ŵn ; sn ← ŵn⊤ µn
15:    return (ŵn , vn , sn )
16: end function
17: return Recurse(root(T ))



Algorithm. Algorithm 1 states the method in full. It is identical to the natural sum-normalised
recursion except in the normaliser.
   Explicitly, the L1 normalisation step is
                                       raw
                                      αL                               raw
                                                                      αR
                         αL =              raw | ,        αR =             raw | ,                  (27)
                                 |αL | + |αR
                                   raw                           |αL | + |αR
                                                                   raw


so that |αL | + |αR | = 1 at every node (not αL + αR = 1). The output portfolio of the algorithm is
the stacked vector returned at the root. It is not “fully invested” in the classical sum-to-one sense; a
mean–variance portfolio with signed weights has no financial reason to sum to one, and one rescales
by leverage or volatility budget downstream.

L1 lemmas. Two lemmas capture what L1 normalisation does and does not do. The first is a
statement about direction, the second about sign; together with the corollary below, they explain
why the pathology is eliminated completely (not just reduced) by the switch from sum-to-one to L1 .

Lemma 4.5 (Ray invariance under child rescaling). Fix a representative ŵR for branch R and let
k > 0. Replace the left representative ŵL by k ŵL , keeping ŵR fixed. Then the combined node-level
portfolio (αL ŵL , αR ŵR ) produced by (23)–(27) lies on the same ray as before the rescaling, i.e. is
invariant up to a strictly positive scalar. The invariance is a statement about the ray, not about
the individual coordinates: αL   raw and αraw scale differently under ŵ → k ŵ (as 1/k and as 1
                                           R                              L       L
respectively), and the L1 denominator does not absorb the scalar uniformly.

Proof sketch. Under ŵL → k ŵL with ŵR fixed, the cluster statistics scale as vL → k 2 vL , sL → k sL ,
c → k c, while vR , sR are unchanged. Substituting into Cramer’s rule, the determinant vL vR − γ 2 c2
scales by k 2 ; the numerator of αL
                                  raw scales by k and the numerator of αraw by k 2 . Hence αraw → αraw /k
                                                                        R                   L      L
and αR raw → αraw . The stacked vector (αraw · k ŵ , αraw ŵ ) is therefore pointwise invariant before
                  R                           L      L    R  R


                                                     23
normalisation. After normalisation by the positive denominator |αL
                                                                 raw |/k + |αraw |, the direction is
                                                                             R
preserved and the scale changes by that same denominator. Full proof in Appendix A.

Lemma 4.6 (Sign preservation under L1 normalisation). The L1 denominator |αL              raw | + |αraw | is
                                                                                                    R
strictly positive whenever (αL
                             raw , αraw ) ̸= (0, 0). Therefore (27) preserves sign(αraw ) and sign(αraw )
                                    R                                               L                  R
at every node of the tree. In contrast, sum-to-one normalisation divides by αL     raw + αraw , which is
                                                                                            R
negative whenever αL raw + αraw < 0, and so flips both signs in that case.
                            R
         raw | + |αraw | ≥ max(|αraw |, |αraw |) > 0 whenever the pair is nonzero. Dividing a nonzero
Proof. |αL         R              L       R
scalar by a strictly positive one preserves its sign.

Corollary 4.7 (Exact antiparallelism to sum-to-one normalisation). Let wsum and wΣµ denote
the output portfolios of the sum-normalised recursive MVO and of HRP-Σµ on the same inputs
(Σ, µ, T , γ). If an odd number of internal nodes on every root-to-leaf path would experience a
                                       raw + αraw < 0), then w sum = −w Σµ exactly.
sum-to-one sign flip (i.e. would have αL      R

Proof sketch. By Lemma 4.5 both methods produce portfolios on the same ray up to per-leaf signs.
Each sign flip along a root-to-leaf path multiplies the final leaf weight by −1; an odd number of
flips on every path multiplies the whole output vector by −1. Full proof in Appendix A.

    Corollary 4.7 makes quantitative the negative-cosine rate observed empirically: under random
signs of αL
          raw + αraw at each node, about half of all tree configurations have an odd number of flips
                 R
on every path, which gives a ≈ 50% rate of exact antiparallelism under sum-to-one normalisation.
Cotton-like regimes with strong off-diagonal coupling depart slightly from the coin-flip limit;
Appendix C measures 45–52%.

Properties of HRP-Σµ.

Proposition 4.8 (Approximate De Prado recovery). At γ = 0 and µ = 1, HRP-Σµ approximately
recovers López de Prado [2016] HRP. The approximation is exact for trees of depth ≤ 2, and for
balanced trees on N = 100 assets yields cosine similarity cos(wΣµ , wHRP ) ≈ 0.992.

Proof sketch. At µ = 1, the local MVO on a pair of leaves reduces to the inverse-variance portfolio,
so HRP-Σµ and HRP agree exactly at the leaves and at depth-1 nodes. At depth ≥ 2, the recursive
MVO representative differs from the flat IVP by off-diagonal within-cluster terms; at γ = 0 the
cross-block scalar c drops out of (23), but the cluster variances vL , vR are still computed from the
MVO representative rather than the flat IVP, producing a small residual. Empirically, the residual
accumulates to cos ≈ 0.992 on balanced trees at N = 100. Full analysis in Appendix A.

    The 0.8% cosine gap is the price HRP-Σµ pays for using ΣLL at every node. HRP-µ (Proposi-
tion 4.2) recovers HRP exactly because its representative is the flat IVP by construction.

Proposition 4.9 (Generic stability). For generic µ—i.e. for all µ outside a Lebesgue measure-zero
subset of RN —the aggregate signal sL = ŵL
                                          ⊤ µ is nonzero at every internal node L. In particular,
                                             L
the L denominator |αL | + |αR | is strictly positive everywhere in the tree, and Algorithm 1 is
      1               raw      raw

well-defined.

Proof sketch. Fix Σ and T . The representative ŵL at each node is a rational function of µ built
from nested Cramer’s-rule ratios. So is sL = ŵL
                                               ⊤ µ . This rational function is not identically zero (it
                                                   L
is strictly positive at µ = 1 by Proposition 4.8); its zero set is an algebraic variety of codimension
≥ 1 and therefore of Lebesgue measure zero. Full proof in Appendix A.


                                                    24
Proposition 4.10 (Diagonal exactness). If Σ is diagonal, then for any γ ∈ [0, 1] and any tree T ,
HRP-Σµ produces a weight vector proportional to the Markowitz solution Σ−1 µ.
Proof sketch. When Σ is diagonal, every off-diagonal block ΣLR is zero, so c = 0 at every node and
(23) reduces to αL raw = s /v , αraw = s /v (independent of γ). At a two-asset leaf-pair node the
                          L L    R      R R
local MVO is ŵi ∝ µi /σii2 . An induction on tree depth shows the root output is proportional to
(µi /σii2 )N
           i=1 = Σ µ; L normalisation only changes the overall scale. Full proof in Appendix A.
                  −1    1


Proposition 4.11 (O(N 2 ) complexity). On a balanced binary tree over N assets, Algorithm 1 runs
in O(N 2 ) time and O(N 2 ) space, the latter dominated by storing Σ.
Proof sketch. The dominant per-node cost is the cross-block inner product ŵL
                                                                            ⊤Σ
                                                                              LR ŵR , which costs
O(|L| · |R|), and the cluster-variance update, which costs O((|L| + |R|) ). Summing (|L| + |R|)2
                                                                        2

over the nodes of a balanced tree is the standard master-theorem recursion and gives O(N 2 ). Full
proof in Appendix A.

Proposition 4.12 (Relationship to HRP-µ). Let wµ and wΣµ denote the outputs of HRP-µ and
HRP-Σµ on the same inputs (Σ, µ, T , γ).
  (i) At γ = 0, the budget split at every node is driven by sL /vL vs. sR /vR ; the two methods differ
      only through the choice of representative (signed IVP vs. recursive MVO), which changes the
      values of sL and vL .
 (ii) On diagonal Σ, wµ and wΣµ agree up to scalar; both are proportional to Σ−1 µ.
(iii) At γ > 0 on non-diagonal Σ, the methods diverge. The divergence grows with within-cluster
      correlation strength and with γ.
Proof sketch. (i) At γ = 0, c is absent from (23); the ratio sL /vL is the only cluster-dependent
quantity in the split. (ii) By Proposition 4.10 and the diagonal specialisation of HRP-µ, both reduce
to µi /σii2 . (iii) The MVO representative exploits off-diagonal within-cluster terms that the signed
IVP ignores, producing different vL , sL , c at every level. Full proof in Appendix A.

Hierarchy of allocators. Table 5 places HRP-Σµ in the full family of allocators developed in
the paper. It occupies the cell between HRP-µ and CRISP: dendrogram structure like HRP-µ, full
within-cluster covariance like CRISP, O(N 2 ) cost.

 Table 5: Hierarchy of allocators developed in this paper. HRP-Σµ sits between HRP-µ and
 CRISP: it uses the dendrogram like HRP-µ but exploits full within-cluster covariance like CRISP.

  Method                           Representative            Within-cluster Σ    Cost
  HRP [López de Prado, 2016]       flat IVP                  diagonal only       O(N 2 )
  HRP-µ (Section 4.3)              signed IVP                diagonal only       O(N 2 )
  HRP-Σµ (Section 4.4)             recursive MVO (local)     full                O(N 2 )
  CRISP (Section 5)                — (no tree)               full                O(N 2 ) per sweep
  Markowitz [Markowitz, 1952]      —                         full                O(N 3 )



Normalisation comparison. Table 6 compares sum-to-one and L1 normalisation head-to-head.
Both solve the same 2 × 2 system (23); the only difference is the denominator used to rescale
(αL
  raw , αraw ).
         R


                                                 25
      Table 6: Normalisation conventions for the recursive MVO tree pass. Both rows solve
      the same 2 × 2 system (23); they differ only in the normaliser. The negative-cosine rate
      is measured on the structural synthetic panels of Section 10; see Appendix C.

       Method                  Normaliser           Sign preserved?     Sums to 1?      Negative-cos rate
       Sum-to-one (A1)         αLraw + αraw
                                          R              No                 Yes              45–52%
       HRP-Σµ (L1 )            |αLraw | + |αraw |
                                            R            Yes                Noa                0%
       a
           HRP-Σµ satisfies |αL | + |αR | = 1 at every node, not αL + αR = 1. The output is not fully invested
           in the sum-to-one sense; downstream leverage or volatility rescaling is applied as needed.


Empirical highlights. Full results are deferred to Section 10; we record the headline facts here
to motivate the construction. On random Gaussian signals with sample covariance estimation,
HRP-Σµ improves out-of-sample Sharpe ratio over HRP-µ by 20–35% across sample sizes T ∈
{60, 120, 240, 500}. On structural sector-tilt signals the improvement ranges from 20% to 180%,
with the largest gains at high γ where within-cluster covariance matters most. At T = 60—the
T < N regime of severe estimation noise—HRP-Σµ at γ = 1.0 attains oracle Sharpe 0.503, slightly
edging the best CRISP configuration (Sharpe 0.497 at γ = 0.7); this is the only place in the paper
where the tree beats CRISP, and it does so precisely because the dendrogram imposes a hierarchical
regularisation that pays most when the raw covariance is poorly conditioned. The L1 normalisation
eliminates the 45–52% negative-cosine rate of sum-to-one recursive MVO entirely (Appendix C,
Appendix E).

4.5    Iterating the tree pass diverges
It is tempting to iterate: after one bottom-up pass produces weights w(n) , update the representative
at each node to reflect w(n) , re-run the pass, and loop. For an exact block solver this outer iteration
would converge. For HRP-µ and HRP-Σµ it does not. The reason is structural: each tree pass
compresses the |L| × |R| cross-block covariance ΣLR into a single scalar c at every node, and this
compression is an approximation of the exact block inverse, not an exact identity. The outer iteration
amplifies the approximation error rather than correcting it; empirically it diverges on the same
synthetic panels on which a single pass is stable. Recovering convergence would require replacing
the scalar c with the full block inverse, restoring an O(N 3 ) cost per pass with multiple passes on
top—which erases the quadratic-cost advantage that motivated the tree in the first place. The
tension between approximation fidelity and iteration convergence inside the tree is exactly what
CRISP resolves by abandoning the dendrogram altogether and iterating in asset space instead; see
Section 5, Theorem 5.2.

4.6    Pointer to the sum-normalised recursive MVO negative result
The natural recursive MVO with sum-to-one normalisation—the construction our code calls “method
A1” but which we do not name in the main body—is sign-pathological: it produces output portfolios
whose direction is essentially random relative to the Markowitz direction under estimation noise,
and flips sign systematically even on noiseless problems. Appendix C documents this in detail, with
histograms, worked counterexamples, and a quantitative connection to Corollary 4.7. The allocator
is a cautionary negative result, not a method we recommend; its role in the paper is to explain what
goes wrong when a natural construction is not reinforced by a sign-preserving normaliser. HRP-Σµ
is the fix.


                                                         26
5     CRISP: iterative shrinkage solver
Section 4 lifted HRP to general signals through the tree. CRISP takes the complementary route:
forget the tree, keep the covariance, and solve a shrunk Markowitz system by scalar Gauss–Seidel.
The shrunk system is

             Pγ w = µ,         Pγ = (1 − γ) D + γ Σ,          D = diag(Σ),          γ ∈ [0, 1],

and the solver makes no factorisation, no matrix inverse, and no reference to any hierarchy. The
construction is structured shrinkage with a variance-preserving target; γ = 0 returns wi = µi /σii ,
γ = 1 returns exact Markowitz, and the Sharpe-optimal operating point lives strictly between
them. The main technical content of the section is Theorem 5.3: the sweep count is controlled
by a preconditioned condition number κ(D−1 Pγ ) that interpolates from 1 at γ = 0 to κ(C) =
κ(D−1/2 ΣD−1/2 ) at γ = 1. Volatility dispersion never enters. The main operational content is
Algorithm 2 and its factor-streaming cousin Algorithm 3, which reduces working memory from
O(N 2 ) to O(N K) for factor-structured covariances and remains tractable on universes where a
dense Σ cannot be stored.

5.1    The shrinkage operator Pγ
Split Σ = D + E with D = diag(Σ) and Eii = 0, Eij = σij for i ̸= j. The shrinkage operator is

                         Pγ = (1 − γ) D + γ Σ = D + γ E,              γ ∈ [0, 1].                     (28)

Entrywise,
                              (Pγ )ii = σii ,    (Pγ )ij = γ σij    (i ̸= j).                         (29)
The diagonal of Pγ is identically the diagonal of Σ for every γ; only the off-diagonal is attenuated.
The endpoints are P0 = D and P1 = Σ.
Proposition 5.1 (SPD structure of Pγ ). For any SPD Σ and any γ ∈ [0, 1], the matrix Pγ is
symmetric positive definite.
Proof. D is SPD because Σ is SPD. Hence Pγ = (1 − γ)D + γΣ is a convex combination of two SPD
matrices and is therefore SPD. (Full proof in Appendix A.)

Structured linear shrinkage. Equation (29) makes the shrinkage interpretation literal. Pγ is
the linear shrinkage estimator of Σ toward the variance-preserving diagonal target D, with intensity
1 − γ. The diagonal entries are univariate sample variances and converge at the univariate rate
from the diagonal of the sample covariance alone; the off-diagonal entries are cross-moments and
are the dominant source of covariance estimation noise, especially in low-variance eigendirections of
Σ
b where Marchenko–Pastur bias is worst. Pγ preserves the reliable part of the covariance exactly
and regularises the unreliable part.

Contrast with Ledoit–Wolf targets. The classical Ledoit–Wolf targets all move the diagonal.
The scaled identity T = (λ̄/N ) I [Ledoit and Wolf, 2004] replaces each σii by the cross-sectional
mean variance. The constant-correlation target [Ledoit and Wolf, 2003] leaves the diagonal alone but
re-inflates correlations uniformly. The single-factor target [Ledoit and Wolf, 2003; Fama and French,
1993] substitutes βi βj σf2 + δij σε,i
                                   2 , which rewrites both diagonal and off-diagonal simultaneously.

CRISP’s target is D itself, so (Pγ )ii = σii for every γ. Section 5.7 returns to this after the convergence
analysis.

                                                    27
Algorithm 2 CrispGaussSeidel(Σ, µ, γ, pmax , ε)
Require: SPD covariance Σ ∈ RN ×N ; signal µ ∈ RN ; shrinkage γ ∈ [0, 1]; max sweeps pmax ∈ N;
    tolerance ε > 0.
Ensure: Approximate solution w ≈ Pγ−1 µ where Pγ = (1 − γ) diag(Σ) + γΣ.
 1: di ← Σii for i = 1, . . . , N                                              ▷ diagonal cache
 2: wi ← µi /di for i = 1, . . . , N                             ▷ diagonal-solve initial guess
 3: if γ < ε then
 4:     return w                                                 ▷ endpoint shortcut: P0 = D
 5: end if
 6: for p = 1 to pmax do
 7:     wprev ← w
 8:     for i = 1 to N do
            s ← Σi,: w − Σii wi                                     ▷ j̸=i σij wj , latest values
                                                                       P
 9:
10:         wi ← (µi − γ s)/di
11:     end for
12:     if ∥w − wprev ∥ ≤ ε ∥wprev ∥ then
13:         break                                              ▷ relative-change stopping rule
14:     end if
15: end for
16: return w


5.2   Scalar Gauss–Seidel iteration
CRISP solves Pγ w = µ by scalar Gauss–Seidel. For each asset i in a fixed ordering,
                                                                 
                                    1                  (latest) 
                                                                                                (30)
                                              X
                              wi ←     µi − γ      σij wj          ,
                                   σii        j̸=i

where “latest” means the most recent value of wj : entries with j < i use the value just updated
in the current sweep, entries with j > i use the value from the previous sweep. A full sweep costs
O(N 2 ), dominated by one inner product j̸=i σij wj per asset. No Cholesky or LU factorisation
                                           P

is formed; memory traffic is a single streaming pass through Σ per sweep. At γ = 0 the update
reduces to wi ← µi /σii and one sweep returns the diagonal solution D−1 µ exactly. At γ = 1 it is
the classical Gauss–Seidel sweep for Σw = µ and converges to Σ−1 µ.

Starting point. We always initialise with w(0) = D−1 µ. This is free, is exact at γ = 0, and means
the very first sweep already starts from a physically meaningful portfolio—the signal normalised by
idiosyncratic risk. Cross-asset correlations fold in as γ and the sweep index grow.
    Algorithm 2 states the sweep loop formally. The implementation contains four small but
practically important details: a cached diagonal so (30) does no division inside the inner loop, the
D−1 µ starting point, an explicit shortcut when γ < ε so the diagonal solve incurs no iteration
overhead, and a relative-change stopping rule that decides early termination adaptively rather than
always running pmax sweeps.

5.3   Unconditional convergence
Theorem 5.2 (Unconditional convergence). Let Σ be SPD, let γ ∈ [0, 1], and let µ ∈ RN . Then
Algorithm 2 converges to the unique solution ŵ = Pγ−1 µ from any starting point w(0) ∈ RN .

                                                28
Proof sketch. By Proposition 5.1, Pγ is SPD. The Ostrowski–Reich theorem [Ostrowski, 1954]—see
Hackbusch [2016, Thm. 4.6.2] and Varga [2000, Thm. 3.4]—states that scalar Gauss–Seidel on
any SPD linear system converges to the unique solution from any initial vector. Applying this to
Pγ w = µ gives the claim. Full proof in Appendix A.

   In plain language: Algorithm 2 cannot fail. For every SPD Σ—including ill-conditioned ones—
and every γ ∈ [0, 1]—including both endpoints—there is no starting point from which the iteration
diverges or stalls. The only remaining question is rate.

5.4   Correlation conditioning and the convergence-rate theorem
The rate theorem says that the sweep count is controlled by the condition number of the correlation
matrix, not of the covariance matrix. Volatility spread inflates κ(Σ) but is invisible to κ(C) and to
CRISP. Define the Jacobi iteration matrix for Pγ as MγJ = −D−1 (Pγ − D) = −γ D−1 E, and the
Gauss–Seidel iteration matrix as MγGS = −(L + D)−1 U , where Pγ = L + D + U is the strict-lower /
diagonal / strict-upper splitting.

Theorem 5.3 (Convergence rate). Let Σ be SPD with D = diag(Σ), correlation matrix C =
D−1/2 ΣD−1/2 , and eigenvalues λ1 ≥ · · · ≥ λN > 0. Fix γ ∈ [0, 1]. Then:

  (i) The Jacobi iteration matrix satisfies MγJ = −γ D−1 E, is similar to γ(I−C), and has eigenvalues
      {γ(1 − λi (C))}Ni=1 . Its spectral radius is

                                   ρ(MγJ ) = γ max λ1 − 1, 1 − λN .                               (31)
                                                                             


 (ii) The preconditioned condition number of Pγ with Jacobi preconditioner D−1 is

                                                          (1 − γ) + γ λ1
                                      κ D−1 Pγ       =                                            (32)
                                                 
                                                                         ,
                                                          (1 − γ) + γ λN

      monotone-increasing in γ from 1 at γ = 0 to κ(C) = λ1 /λN at γ = 1.

(iii) ρ(MγGS ) < 1 strictly for every γ ∈ [0, 1], and the number of sweeps to reach relative residual ε
      is bounded by                                                  
                                     p(ε, γ) = O κ D−1 Pγ log(1/ε) ,                               (33)
                                                            


      and specialising to γ = 1,
                                       p(ε, 1) = O κ(C) log(1/ε) .                                (34)
                                                                       


Proof sketch. (i). From Pγ = D + γE,

                        MγJ = I − D−1 Pγ = −γ D−1 E = γ I − D−1 Σ .
                                                                                 


By Proposition 2.2, D−1 Σ = D−1/2 C D1/2 is similar to C, so MγJ is similar to γ(I − C) with
eigenvalues {γ(1 − λi )}. Since tr(C) = N forces λ1 ≥ 1 ≥ λN , the spectral radius is (31).
    (ii). D−1 Pγ = (1 − γ)I + γ D−1 Σ has eigenvalues {(1 − γ) + γλi }; their ratio gives (32). The
map γ 7→ [(1 − γ) + γλ1 ]/[(1 − γ) + γλN ] is the Möbius transform x 7→ (a + bx)/(a + cx) in γ with
a = 1, b = λ1 − 1, c = λN − 1, which is monotone because b = ̸ c whenever λ1 > λN ; the endpoints 1
and κ(C) come from substitution.



                                                     29
   (iii). By Theorem 5.2 and Varga [2000, Thm. 3.4], ρ(MγGS ) < 1 strictly. The classical Hackbusch–
Saad rate bound for Gauss–Seidel on an SPD system in the energy norm of the system matrix
is                                                c     p
                             ∥e(p) ∥Pγ ≤ 1 −                ∥e(0) ∥Pγ ,
                                             κ(D Pγ )
                                                  −1

for a constant c > 0 depending on the Jacobi-preconditioning structure of Pγ , not only on its
scale; see Hackbusch [2016, §4.7] and Saad [2003, Thm. 4.8]. Solving for the smallest p that drives
the right-hand side below ε yields (33); setting γ = 1 and using (ii) gives (34). Full proof in
Appendix A.

   Part (ii) is the load-bearing statement. Throughout the paper the preconditioned condition
number κ(D−1 Pγ )—not κ(Pγ ) or κ(Σ)—is the object that governs iterative cost; volatility dispersion
κD = maxi σii / mini σii absorbs into the problem-dependent constant in the big-O of (33) and does
not appear in the leading term. This is the structural consequence of choosing the target D: scaling
the rows and columns of Σ by arbitrary positive weights changes κ(Σ) without bound but leaves
κ(C) and hence the sweep budget invariant.
Remark 5.4 (Why not Stein–Rosenberg). For a matrix whose Jacobi iteration matrix is entrywise
nonnegative—equivalently Σ is an M -matrix with nonpositive off-diagonals—Young’s theorem on
consistently ordered matrices and thepStein–Rosenberg    comparison [Young, 1971], Varga [2000, §3.3],
give the tighter bound p(ε, 1) = O κ(C) log(1/ε) . Realistic equity and factor covariances have
                                                      

positive off-diagonal entries (assets are positively correlated on average) so Σ is not an M -matrix
and the hypothesis of Young’s theorem fails. We therefore quote the universally-applicable SPD
bound (34); this is weaker but holds for every SPD Σ without further sign conditions on E. In the
synthetic experiments of Section 10 the empirical sweep count is well described by the linear-in-κ(C)
rate, as expected.

Corollary 5.5 (Total complexity). The total cost of CRISP to drive the relative residual of Pγ w = µ
below ε is                                                 
                                  O κ D−1 Pγ N 2 log(1/ε) ,                                      (35)
                                               


specialising at γ = 1 to O κ(C) N 2 log(1/ε) . The sweep count is a hidden constant only on problems
                                            

where κ(C) = O(1); on ill-conditioned correlation matrices the sweep budget scales accordingly.

   The directional difficulty diagnostic of Section 2, Equation (8),

                                 dirdiag (Σ, µ) = dir D−1 µ, Σ−1 µ ,
                                                                  


sits next to Corollary 5.5 as the empirical analogue: dirdiag measures how far the γ = 0 iterate is
from the γ = 1 target in direction, and κ(D−1 Pγ ) measures how many sweeps it takes to traverse
that gap.
    Figure 1 plots the two curves that drive (35) together: the closed-form preconditioned condition
number κ(D−1 Pγ ) from (32), and the empirical sweep count of Algorithm 2 on the same test
covariance. Both are monotone in γ and pinned down at the endpoints κ(D−1 P0 ) = 1 and
κ(D−1 P1 ) = κ(C). Correlation conditioning—not volatility dispersion, not κ(Σ)—drives CRISP’s
iteration cost.

5.5   What CRISP does not do
Two clarifying negatives are worth stating explicitly because each has been inferred in conversation.


                                                 30
                             Method B: P = (1   ) D + . Correlation conditioning drives both condition number and sweep count.

                              Preconditioned condition number                                                        Empirical sweep count
                                                   (C) 54.6                                          250
                             (D 1P )                                                                         sweeps to r /         10 6
                 50
                                                                                                     200




                                                                              Gauss--Seidel sweeps
                 40
                                                                                                     150
       (D 1P )



                 30
                                                                                                     100
                 20
                 10                                                                                  50
                        =1
                                                                                                      0
                  0.0          0.2       0.4       0.6        0.8       1.0                            0.0     0.2           0.4          0.6   0.8   1.0


Figure 1: The shrinkage operator Pγ = (1 − γ)D + γΣ and the CRISP convergence rate on a
block-structured 60-asset test covariance with four clusters, within-block correlation 0.65, cross-block
correlation 0.20, and idiosyncratic volatilities uniform on [0.15, 0.40]. Left: the preconditioned
condition number κ(D−1 Pγ ) = [(1 − γ) + γλ1 ]/[(1 − γ) + γλN ] from Theorem 5.3(ii), monotone
from 1 at γ = 0 to κ(C) ≈ 54.6 at γ = 1. Right: empirical sweep count for Algorithm 2 to reach
relative residual ∥Pγ w − µ∥/∥µ∥ ≤ 10−6 on the same matrix with a random signal µ. The empirical
sweep count tracks the condition-number curve, confirming the linear-in-κ(D−1 Pγ ) bound (33).


CRISP does not nest HRP. At γ = 0 Algorithm 2 returns the flat diagonal solution wi = µi /σii —
the signal weighted by inverse idiosyncratic variance—not the HRP weights. HRP is a tree-structured
construction that requires a hierarchical clustering of Σ and a recursive-bisection traversal; at µ = 1
it produces a portfolio whose weights are products of inverse cluster variances along the root-to-leaf
path. The γ = 0 endpoint of CRISP does not know about any tree and, even at µ = 1, returns the
flat inverse-variance portfolio, which generally differs from HRP. The hierarchical nesting of HRP
and the signal-aware nesting that recovers HRP at µ = 1 are the job of HRP-µ (Section 4.3), not
CRISP.

CRISP does not use the tree. The sweep ordering in Algorithm 2 is arbitrary: Theorem 5.2
holds for any fixed ordering, and the big-O in (35) does not depend on it. Empirically, ordering
assets so that strongly correlated ones are visited consecutively—for instance, the leaf ordering of the
HRP quasi-diagonalisation [López de Prado, 2016]—can modestly improve the empirical contraction
factor, a standard Gauss–Seidel phenomenon [Saad, 2003, §4.1]. We use the quasi-diagonalised
ordering in experiments but the theoretical rate does not rely on it.

5.6   Factor-model streaming variant
When Σ = BΛB ⊤ + Didio admits a K-factor decomposition with B ∈ RN ×K , Λ ∈ RK×K SPD, and
Didio ∈ RN the idiosyncratic variances—the structure of essentially every production equity and
fixed-income risk model [Fama and French, 1993; Fan, Liao and Mincheva, 2013]—CRISP can be
implemented without materialising the dense Σ. The trick is to maintain the K-vector aggregate
z = B ⊤ w incrementally so that the row inner product Σi,: w = Bi ΛB ⊤ w + didio,i wi reduces to an
application of Λ to the short vector z plus a scalar correction. Per-asset cost becomes O(K 2 ) and
working memory O(N K) rather than O(N 2 ). Algorithm 3 states the pseudocode.
    The iterates of Algorithm 3 are identical to those of Algorithm 2 run on the dense Σ; this is an
optimisation, not a different method, and all results of Theorem 5.3 carry over unchanged.


                                                                           31
Algorithm 3 CrispFactorStream(B, Λ, didio , µ, γ, pmax , ε)
Require: Factor loadings B ∈ RN ×K ; factor covariance Λ ∈ RK×K SPD; idiosyncratic variances
    didio ∈ RN ; signal µ; shrinkage γ; max sweeps pmax ; tolerance ε.
Ensure: Approximate solution w ≈ Pγ−1 µ with Σ = BΛB ⊤ + diag(didio ).
 1: σi2 ← Bi ΛBi⊤ + didio,i for i = 1, . . . , N                         ▷ diagonal of Σ from factors
 2: wi ← µi /σi for i = 1, . . . , N
                2                                                       ▷ diagonal-solve initial guess
 3: z ← B ⊤ w                                                                   ▷ K-vector aggregate
 4: if γ < ε then
 5:     return w
 6: end if
 7: for p = 1 to pmax do
 8:     for i = 1 to N do
 9:         z\i ← z − Bi wi                                           ▷ remove asset i’s contribution
10:         off ← Bi Λ z\i                                       ▷ (Σw)i − σi2 wi without forming Σ
11:         wi ← (µi − γ off )/σi
              new                    2

12:         z ← z\i + Bi winew                                       ▷ incremental aggregate update
13:         wi ← winew
14:     end for
15: end for
16: return w


Numerical example. At N = 30,000, K = 20: the dense Σ occupies N 2 · 8 B ≈ 7.2 GB; the
factor-streaming working set is N K + K 2 + N ≈ 4.8 MB. Three orders of magnitude separate “needs
a dedicated server” from “fits in L3 cache.” Dense Cholesky cannot exploit the factor structure
because its factorisation needs random access to the full covariance and produces a dense triangular
factor. The Woodbury identity gives O(N K 2 + K 3 ) exact inversion of factor-structured Σ, but it
inverts the raw covariance and so inherits all of the overfitting that CRISP’s shrinkage exists to
prevent.

5.7   Shrinkage interpretation and Ledoit–Wolf comparison
At convergence CRISP returns Pγ−1 µ, which is exactly Markowitz on the linearly shrunk covariance
Pγ = (1 − γ)D + γΣ. CRISP therefore sits inside the Ledoit–Wolf linear-shrinkage family [Ledoit and
Wolf, 2003, 2004, 2017, 2020], and the interest lies not in whether it differs from shrunk Markowitz
in some abstract sense, but in exactly three structural choices:

 (1) Target. CRISP uses D = diag(Σ), which preserves variances exactly—only off-diagonal
     correlations are regularised. Classical Ledoit–Wolf targets (scaled identity, constant-correlation,
     single-factor) all distort the diagonal. The scaled identity replaces σii by the cross-sectional
     mean λ̄/N [Ledoit and Wolf, 2004]; the constant-correlation target keeps σii but imposes a
     single off-diagonal correlation for the target [Ledoit and Wolf, 2003]; the single-factor target
     substitutes βi βj σf2 + δij σε,i
                                  2 , which rewrites both diagonals and off-diagonals at once. The

     CRISP target is the only one that asserts, as a modelling choice, that sample variances do not
     need shrinkage.

 (2) Intensity criterion. Ledoit–Wolf chooses its intensity αLW to minimise the expected Frobenius
     loss E∥Σb LW − Σ∥2 —a statistical criterion on the covariance estimator. CRISP chooses γ to
                        F
     maximise out-of-sample portfolio Sharpe—an operational criterion on the portfolio. Section 6

                                                  32
      makes clear why these need not coincide: a covariance estimator that minimises Frobenius
      distance to Σ can still overweight noise-dominated eigendirections once inverted, and the
      Frobenius loss does not see that downstream effect. The oracle-approximating shrinkage
      (OAS) estimator [Chen et al., 2010] and the nonlinear shrinkage variants [Ledoit and Wolf,
      2017, 2020] refine the intensity estimator under the same statistical criterion.

  (3) Implementation. Ledoit–Wolf forms Σ  b LW explicitly and inverts with dense Cholesky. CRISP
      never forms Pγ ; Algorithm 2 drives Pγ w → µ iteratively in O(κ(D−1 Pγ ) N 2 log(1/ε)) time.
                     −1

      This is an engineering advantage—and it enables the factor-streaming variant of Section 5.6—
      but it is not what makes the portfolio better.

    The philosophy shift, independent of Stein’s original motivation [Stein, 1956], is the first two
items: CRISP regularises exactly the unreliable part of the covariance and selects the regularisation
strength for the downstream application.

Open question. Is there a Ledoit–Wolf target T and intensity rule αLW such that Σ     b −1 µ = P −1
                                                                                        LW      γ⋆ µ
in expectation over a specified sampling distribution, where γ is the Sharpe-optimal CRISP
                                                                 ⋆

intensity? The empirical Monte Carlo of Section 10 is consistent with γ ⋆ ∈ [0.5, 0.7] across panels,
but we do not have a closed-form correspondence. We flag this as an open problem; Ledoit–Wolf is
included as a head-to-head baseline in every out-of-sample experiment.

5.8   Early stopping as implicit spectral regularisation
Remark 5.6 (Early stopping as implicit spectral regularisation). The per-eigendirection content of
Theorem 5.3 has a statistical side-effect when Σ is a finite-sample estimate Σ.  b Gauss–Seidel on
Pγ w = µ converges geometrically in each eigendirection of D−1 Pγ : after p sweeps, the residual on
the k-th eigendirection is O(ρpk ) with ρk bounded by ρ(MγGS ) < 1 and decreasing with the eigenvalue.
Well-conditioned (high-eigenvalue) directions converge exponentially faster than ill-conditioned
(low-eigenvalue) directions. When Σ   b is a sample estimate, the low-eigenvalue directions of D −1 Pbγ
are exactly the directions where Marchenko–Pastur bias [Marchenko and Pastur, 1967] and finite-
sample noise are worst, and the directions direct Markowitz amplifies. Stopping Gauss–Seidel before
convergence therefore implicitly attenuates the portfolio’s exposure to the most noise-contaminated
spectral subspace. The sweep count p plays the role of 1/λ in ridge regression: small p is strong
regularisation (heavy spectral truncation), large p is weak regularisation (recovery of full Pbγ−1 µ).
This is Channel 3 of the three-channel decomposition in Section 7; together with operator shrinkage
(Channel 1, driven by γ) and noise cancellation (Channel 2, driven by the target D), the three
channels act orthogonally on three different spectral regimes of Σ.b


5.9   Wall-clock versus memory
Remark 5.7 (Wall-clock: Cholesky with tuned BLAS is fast). The naïve FLOP crossover between
CRISP at p = 100 sweeps and Cholesky factorisation occurs at N ≈ 600, from 100 · 2N 2 ≈ N 3 /3.
The true wall-clock picture is much less favourable to CRISP because LAPACK Cholesky exploits
BLAS-3 (matrix–matrix) throughput while the inherently sequential Gauss–Seidel sweep—each wi
update depends on wj updated earlier in the sweep—is limited to scalar throughput. On modern
matrix-optimised silicon the gap between these two throughputs is very large.
    We measured this on an Apple M4 with Accelerate-linked LAPACK (NumPy 2.4, SciPy 1.17, ma-
cOS 15.7), comparing scipy.linalg.cho_factor / cho_solve against a Numba-JIT-compiled CRISP
at γ = 0.5, p = 100; single-solve median across trials, full raw output in results/11_bench_crisp_vs_cholesky.txt:

                                                  33
                      N    Cholesky (ms)     CRISP (ms)      ratio (Cholesky faster)
                     500              0.38            18.2                       48×
                   1,000              1.92            76.3                       40×
                   2,000              13.2           313.9                       24×
                   3,000              51.8           712.1                       14×
                   5,000             216.5         1,993.4                        9×

Cholesky is 9–48× faster across the range tested. Fitting the O(N 2 )-versus-O(N 3 ) asymptotics
places the single-solve wall-clock crossover on this hardware near N ≈ 45,000, well beyond realistic
portfolio sizes. On commodity x86 with OpenBLAS the gap is narrower and the crossover shifts
down, but we do not claim a wall-clock advantage for CRISP against tuned-BLAS Cholesky at
realistic N .
    The practical case for CRISP rests on two legs, neither of which is speed:

    (i) Out-of-sample Sharpe. At γ ∈ [0.3, 0.7], CRISP delivers superior OOS Sharpe at every N
        tested—including N = 500 where Cholesky is nearly 50× faster—as reported in Section 10.

    (ii) Memory footprint. Algorithm 3 reduces working memory from O(N 2 ) to O(N K) for factor-
         structured Σ—4.8 MB against 7.2 GB at N = 30,000, K = 20—which dense Cholesky cannot
         match. This is a structural advantage independent of BLAS throughput.

A faster wrong answer is still wrong. The shrunk system Pγ w = µ is the better answer, and CRISP
solves it without ever forming the inverse.
    This closes the algorithmic content of the paper. Sections 6 and 7 analyse the shrinkage trajectory
γ 7→ Pγ−1 µ in detail and derive an adaptive rule for γ ⋆ ; Section 10 verifies both the rate theorem
and the interior-optimum empirically; Sections 8 and 9 place CRISP in the comparative landscape
and extend it to linearly-constrained portfolios.


6      Perturbation theory and the shrinkage trajectory
Sections 4 and 5 introduced the shrinkage operators Pγ = (1 − γ)D + γΣ; this section analyses
them as a one-parameter deformation of Σ by the off-diagonal remainder E = Σ − D. Four results
follow: an exact approximation-error identity (Theorem 6.1), a structural direction-error bound
(Proposition 6.2), the zero locus on invariant rays (Corollary 6.3), and the interior γ ⋆ phenomenon
that governs finite-sweep CRISP (Proposition 6.6). All proof sketches are inline; full proofs live in
Appendix A.

6.1     Invariant rays revisited
The zero-set for every perturbation statement below consists of the invariant rays of the shrinkage
family. Lemma 2.3 of Section 2 identifies these explicitly: if C = D−1/2 ΣD−1/2 has eigenpair (λ, v)
with λ > 0, then for µ = D1/2 v and every γ ∈ [0, 1],
                                                     1
                                    Pγ−1 µ =                D−1 µ,                                  (36)
                                               (1 − γ) + γλ

so the direction of Pγ−1 µ is fixed at D−1 µ (equivalently Σ−1 µ = λ−1 D−1 µ) across the entire shrinkage
interval. On these signals every method in the paper—HRP, Cotton, HRP-µ, HRP-Σµ, CRISP at
any sweep budget, and the trivial diagonal solver—produces the same direction, so the direction

                                                   34
error against w⋆ = Σ−1 µ is identically zero for every γ. Two operational consequences. First,
single-eigenvector signals are useless as adversarial inputs because they cannot separate methods and
cannot produce a nonzero direction error under any shrinkage intensity; adversarial constructions in
Section 10 must mix at least two eigendirections of C with distinct eigenvalues. Second, the standard
slogan that “Σ−1 amplifies low-eigenvalue directions” concerns scale: the prefactor [(1 − γ) + γλ]−1
in (36) diverges as λ ↓ 0, but the direction along an invariant ray is rigid.

6.2   Approximation-error identity
Write w⋆ = Σ−1 µ for the Markowitz direction and ŵ(γ) = Pγ−1 µ for its shrinkage approximant at
intensity γ. Their difference admits an exact closed form.

Theorem 6.1 (Approximation-error identity). Let Σ ∈ RN ×N be SPD with D = diag(Σ) and
E = Σ − D. For every γ ∈ [0, 1],

                       w⋆ − ŵ(γ) = −(1 − γ) Pγ−1 E w⋆ ,         ŵ(γ) = Pγ−1 µ.                   (37)

Proof sketch. Since Pγ = Σ − (1 − γ)E, the Markowitz equation Σw⋆ = µ rewrites as Pγ w⋆ + (1 −
γ)Ew⋆ = µ. Subtracting Pγ ŵ(γ) = µ and applying Pγ−1 yields (37). Full proof in Appendix A.

    Three features of (37) govern everything that follows. The prefactor (1 − γ) forces the residual
to zero as γ ↑ 1 with norm O(1 − γ); the error direction is the specific vector Pγ−1 Ew⋆ , not an
abstract residual; and the identity vanishes whenever Ew⋆ lies in the kernel of the direction metric,
a condition made precise by Corollary 6.3 below.

6.3   Direction-error bound
The quality metric is the direction metric of Definition 2.1, which is scale-invariant. Translating (37)
into direction-error form isolates the geometric content.

Proposition 6.2 (Direction-error bound). Under the hypotheses of Theorem 6.1, for every fixed
γ ∈ [0, 1),
                                                   2   ∥w⋆ ∥2
                  dir ŵ(γ), w⋆ ≤ (1 − γ)2 Pγ−1 E op           G(γ, w⋆ ),                (38)
                               
                                                      ∥ŵ(γ)∥2
where G(γ, w⋆ ) = sin2 ϕ(γ) ∈ [0, 1] is the squared sine of the angle ϕ(γ) between w⋆ and Pγ−1 Ew⋆ .
In particular, G(γ, w⋆ ) = 0 if and only if w⋆ is an eigenvector of Pγ .

Proof sketch. Write ŵ(γ) = w⋆ + (1 − γ) u(γ) with u(γ) = Pγ−1 Ew⋆ . Lagrange’s identity for the
sine of the angle between ŵ(γ) and w⋆ gives sin2 θ = (1 − γ)2 ∥u⊥ (γ)∥2 ∥w⋆ ∥2 /(∥ŵ(γ)∥2 ∥w⋆ ∥2 ),
where u⊥ (γ) = u(γ) − projw⋆ u(γ). Bounding ∥u⊥ (γ)∥2 ≤ ∥u(γ)∥2 ≤ ∥Pγ−1 E∥2op ∥w⋆ ∥2 and defining
G(γ, w⋆ ) = ∥u⊥ (γ)∥2 /∥u(γ)∥2 = sin2 ϕ(γ) yields (38). Full proof in Appendix A.

   Equation (38) is a structural decomposition, not a one-parameter monotonicity theorem. Both
the operator-norm factor ∥Pγ−1 E∥op and the geometric factor G(γ, w⋆ ) depend on γ, and they can
move in opposite directions as γ varies. The prefactor (1 − γ)2 forces the right-hand side to zero at
γ = 1, but does not pin down the trajectory in between. Example 6.4 exhibits a 4 × 4 problem on
which the three factors combine non-monotonically.




                                                  35
6.4   The shrinkage trajectory
The exact identity (37) pins down the endpoint behaviour of the shrinkage trajectory γ 7→ ŵ(γ) =
Pγ−1 µ. As γ ↑ 1, ŵ(γ) → w⋆ with residual norm O(1 − γ), so the direction error tends to zero. On
the invariant rays of (36) the direction error is identically zero for every γ.
Corollary 6.3 (Invariant rays on the trajectory). If µ = D1/2 v with Cv = λv and λ > 0, then
dir Pγ−1 µ, Σ−1 µ = 0 identically for every γ ∈ [0, 1].
Proof sketch. By (36), Pγ−1 µ is a scalar multiple of D−1 µ for every γ, and so is Σ−1 µ = λ−1 D−1 µ.
The direction between the two is therefore fixed at zero on [0, 1]. Full proof in Appendix A.

  Off the invariant rays, the map γ 7→ dir(Pγ−1 µ, Σ−1 µ) is not globally monotone. Example 6.4
makes this concrete.
Example 6.4 (Non-monotone trajectory). Let

                         1.055  0.078 −0.711 −1.874
                                                                                                                  
                                                                                                   −1.695
                        0.078  6.058 −0.379 1.775                                                0.271 
                   Σ =                             ,                                        µ =        ,
                                                                                                       
                       −0.711 −0.379 1.036  2.063                                                0.322 
                        −1.874 1.775  2.063   6.477                                                −0.500

so that κ(C) ≈ 27.4 and µ is not on an invariant ray (its four projections onto the eigenvectors of C
are all nonzero). The direction error dir(Pγ−1 µ, Σ−1 µ) behaves as follows:

             γ           0           0.05       0.10       0.20       0.30        0.50        0.70        0.90       1.00
             dir     0.242           0.243      0.244     0.249      0.253        0.250       0.213   0.085          0.000

The direction error rises from 0.242 at γ = 0 to a peak of 0.253 at γ ≈ 0.30 (a +4.75% bump over
the diagonal anchor) before descending to 0 at γ = 1. Global non-increasing monotonicity in γ
therefore fails.
Remark 6.5 (What the identity does and does not tell us). Theorem 6.1 controls two facts unam-
biguously: the residual norm is O(1 − γ), so ŵ(γ) → w⋆ as γ ↑ 1, and on invariant rays the direction
error is identically zero. Between those two facts, the direction of Pγ−1 Ew⋆ relative to w⋆ is not
sign-controlled by the shrinkage intensity alone, so bumps of the kind exhibited in Example 6.4 are
possible in principle. Empirically, on the correlation regimes studied in Section 10 the trajectory is
typically non-increasing with only mild interior bumps in adversarial regimes, and the practitioner’s
operating point γ ≈ 0.5 sits inside the descending region on every panel we have tested.

6.5   Shrinkage bias vs. convergence slack: the interior γ ⋆
If CRISP produced the exact fixed point ŵ(γ) at every γ, the guidance would be “run at γ = 1”.
In practice CRISP delivers the finite-sweep iterate w(p) (γ) after p Gauss–Seidel sweeps, which
introduces a second γ-dependent term. The total direction error decomposes, in angle, as
                                                                                                              
                 dir w(p) (γ), w⋆               ≲    dir(ŵ(γ), w⋆ )         +        dir w(p) (γ), ŵ(γ)                    (39)
                 |            {z            }        |       {z       }               |          {z              }
                             total                  shrinkage bias, ↓ in γ       convergence slack, ↑ in γ at fixed p

(the precise statement is a squared-sine triangle bound; the additive form is qualitative). The
shrinkage bias is zero at γ = 1 and non-increasing over the regimes studied (Remark 6.5). The

                                                                    36
                                                   Bias--variance curves L( ) with predicted     from the adaptive rule
                                                                                               low NSR: T/N = 0.6, IC = 0.10, (C) = 6
                                         0.05                                                  mid NSR: T/N = 0.6, IC = 0.10, (C) = 61
Sharpe shortfall L( ) = maxSR( ) SR( )

                                                                                               high NSR: T/N = 0.6, IC = 0.05, (C) = 151

                                         0.04

                                         0.03

                                         0.02

                                         0.01

                                         0.00
                                             0.0        0.2                 0.4            0.6                    0.8                  1.0

Figure 2: Bias–variance decomposition of total direction error along the shrinkage axis, illustrat-
ing (39). The shrinkage-bias curve dir(ŵ(γ), w⋆ ) (decreasing in γ, vanishing at γ = 1 by Theorem 6.1)
falls as the shrinkage approximant approaches the Markowitz fixed point. The convergence-slack
curve dir(w(p) (γ), ŵ(γ)) (increasing in γ at fixed sweep budget p, because κ(D−1 Pγ ) grows from 1
at γ = 0 to κ(C) at γ = 1) rises as the Gauss–Seidel iteration slows. Their sum—an upper bound
on the total direction error dir(w(p) (γ), w⋆ )—attains an interior minimum γ ⋆ ∈ (0, 1) under the
hypotheses of Proposition 6.6. The interior γ ⋆ is the CRISP-specific manifestation of the standard
shrinkage trade-off: shrinkage bias downward pressure on γ, convergence slack upward pressure on
γ, interior minimum where marginal pressures balance.


convergence slack is non-decreasing in γ at fixed p: by Proposition 2.2 and Theorem 5.3, the relevant
operator condition number κ(D−1 Pγ ) grows from 1 at γ = 0 to κ(C) at γ = 1, so the per-sweep
residual reduction worsens as γ grows. The sum of a decreasing and an increasing function attains
its minimum in the interior whenever the two derivatives cross inside (0, 1) (Figure 2).

Proposition 6.6 (Interior γ ⋆ at finite sweep budget). Fix p ∈ N and SPD Σ with D = diag(Σ),
C = D−1/2 ΣD−1/2 . Assume:

                       (i) non-invariance: µ is not on an invariant ray of C in the sense of Lemma 2.3;

                (ii) generic alignment: ∂γ dir Pγ−1 µ, w⋆                         < 0;
                                                                        
                                                                            γ=0

         (iii) sweep-budget deficit: dir w(p) (1), Σ−1 µ > dir D−1 µ, Σ−1 µ .
                                                                                                  


Then γ 7→ dir w(p) (γ), w⋆ attains its minimum on [0, 1] at an interior point γ ⋆ ∈ (0, 1).
                                                       


Proof sketch. The map is continuous on the compact interval [0, 1], so the minimum is attained.
Hypothesis (iii) rules out γ = 1: the total error there strictly exceeds the total error at γ = 0,

                                                                                   37
                                                                       Shrinkage trajectory: exact (monotone) vs finite-sweep CRISP (interior optimum at finite p)

                                                         Easy, (C) 9                                            Moderate (base case), (C) 121                                  Hard (worst case), (C) 3824
                          100
                         10 1
1 )




                         10 2
direction error dir(w,




                         10 3
                         10 4
                         10 5
                         10 6         exact P 1                                                    exact P 1                                                   exact P 1
                                      CRISP p = 50                                                 CRISP p = 100                                               CRISP p = 200
                         10 7         CRISP p = 200                                                CRISP p = 500                                               CRISP p = 2, 000
                                      CRISP p = 1, 000                                             CRISP p = 2, 000                                            CRISP p = 10, 000
                         10 8
                                0.0             0.2      0.4     0.6       0.8       1.0     0.0             0.2        0.4       0.6       0.8   1.0    0.0             0.2          0.4       0.6          0.8   1.0



Figure 3: Shrinkage trajectory γ 7→ dir(w(p) (γ), w⋆ ) across three difficulty regimes, N = 200. Left
(easy, κ(C) ≈ 9): even 50 CRISP sweeps converge; no interior optimum. Centre (moderate,
κ(C) ≈ 121, the paper’s base case): a mild interior optimum appears at p = 100 with γ ⋆ ≈ 0.65;
500+ sweeps essentially converge. Right (hard, κ(C) ≈ 3,800, adversarial µ): the interior γ ⋆ (p)
is pronounced and moves rightward with p (Proposition 6.6). Blue curves (exact fixed point
ŵ(γ) = Pγ−1 µ) descend to zero at γ = 1 by Theorem 6.1; finite-sweep curves are U-shaped, with the
minimum shifted toward the interior. A practitioner can compute κ(C) = λmax (C)/λmin (C) from
the correlation matrix of their risk model to locate the panel they are in.


because at γ = 0 the convergence slack vanishes (the diagonal system is solved in one sweep) and
the total error reduces to dir(D−1 µ, Σ−1 µ). Hypothesis (ii) rules out γ = 0: the shrinkage-bias term
has strictly negative derivative at γ = 0 while the convergence-slack term has a bounded derivative
there (Theorem 5.3), so the total derivative is negative in a right neighbourhood of 0. The minimum
therefore lies in (0, 1). Full proof in Appendix A.

Remark 6.7. Hypothesis (i) excludes the degenerate single-eigenvector case (Corollary 6.3), on which
the direction error is identically zero across [0, 1] and the minimum is trivially attained everywhere.
Hypothesis (ii) is generic: the first-variation computation makes ∂γ dir|γ=0 a rational function of the
spectral data of (Σ, µ) that vanishes only on a measure-zero algebraic subvariety of parameter space;
Example 6.4 sits on the complement of this subvariety in the wrong direction and the derivative
is positive there. Hypothesis (iii) is the operationally meaningful one—it says the sweep budget
p is insufficient to overcome the γ = 1 conditioning penalty—and is exactly the regime in which
Figure 3 shows a pronounced interior optimum.
     Proposition 6.6 is the CRISP analogue of the optimal-shrinkage-intensity result of Ledoit
and Wolf [2003], with a computational rather than statistical trade-off. Ledoit–Wolf shrink the
covariance estimator toward a structured target to trade sample-noise variance against target bias.
CRISP shrinks the covariance operator toward its diagonal to trade shrinkage bias against iterative
convergence slack. Both land on the same qualitative recommendation—regularise strictly inside
(0, 1)—but for different reasons. Section 7 recasts the interior optimum in out-of-sample terms,
where the convergence-slack axis is replaced by a finite-sample estimation-loss axis driven by the
concentration rate of Σ̂ − Σ; the closed-form approximation for γ ⋆ derived there is the operational
recommendation of the paper.




                                                                                                                        38
7     The adaptive γ ⋆ rule and three regularisation channels
Section 6 established that fixed-γ CRISP exhibits an interior sweep-count optimum and that the
shrinkage trajectory γ 7→ w(γ) is empirically non-increasing on the regimes studied. This section
closes the analytical loop: we write the expected out-of-sample Sharpe loss as a bias–variance
decomposition, solve for the loss-minimising γ ⋆ in closed form, and reconcile the derivation with the
empirical finding that the OOS Sharpe surface is nearly flat across a wide calibration cube. We
then catalogue the three distinct regularisation channels operating simultaneously inside CRISP
(Remark 7.2) and give the information-theoretic reading of what shrinkage accomplishes.

7.1   Bias–variance decomposition
Let ŵ(γ) = P̂γ−1 µ̂ with P̂γ = (1 − γ) diag(Σ̂) + γ Σ̂. Evaluating SR2OOS (γ) = (w⊤ µ)2 /(w⊤ Σw) at
w = ŵ(γ) under the true (Σ, µ) and expanding to first order in the estimation noise gives

           E SR2oracle − SR2OOS (γ) = SR2oracle − SR2pop (γ) +           V (γ)         + O(N −1 ),   (40)
                                                              
                                        |          {z            }       | {z }
                                            approximation loss       estimation loss


where SR2pop (γ) is the Sharpe-squared of the population weight w(γ) = Pγ−1 µ and V (γ) is the
expected Sharpe loss from substituting (Σ̂, µ̂) for (Σ, µ). The approximation loss pushes toward
γ = 1; the estimation loss pushes toward γ = 0; the interior optimum γ ⋆ is where their marginals
balance.

7.2   Approximation loss via Neumann expansion
Write Pγ = D1/2 [(1 − γ)I + γC]D1/2 with C = D−1/2 ΣD−1/2 , and let µ̃ = D−1/2 µ, ϵ = 1 − γ. The
Neumann identity applied to [C + ϵ(I − C)]−1 around γ = 1 yields

                        [C + ϵ(I − C)]−1 = (1 + ϵ) C −1 − ϵ C −2 + O(ϵ2 ),                           (41)

so
                 Pγ−1 µ = 1 + (1 − γ) w⋆ − (1 − γ) D−1/2 C −2 µ̃ + O (1 − γ)2 ,                      (42)
                                                                                          

where w⋆ = Σ−1 µ. The overall prefactor (1 + (1 − γ)) multiplying w⋆ must be retained: because
Sharpe-squared is scale-invariant it does not propagate into the loss formula, but dropping it
degrades the expansion (42) from O((1 − γ)2 ) to O(1 − γ) and contaminates every downstream
constant. A direct numerical check at ϵ = 10−3 on the base-case (N, κ(C)) = (100, 61) covariance
gives a full-expansion error of 1.7 × 10−4 against a truncated-expansion error of 2.9 × 10−3 , a 17×
difference.
    Substituting (42) into SR2pop and retaining the quadratic term gives

                   SR2oracle − SR2pop (γ) = (1 − γ)2 A + O (1 − γ)3 ,             A ≥ 0,             (43)
                                                                         


where the approximation coefficient A = A(Σ, µ) depends only on the projection of µ̃ onto the
eigenvectors of C −1 . If µ is aligned with leading eigenvectors of C, the diagonal surrogate is nearly
optimal and A is small; if µ has weight on low-eigenvalue directions of C—exactly the directions
shrinkage toward D removes—A is large. Equicorrelation and K-factor special cases are worked out
in Appendix A.




                                                   39
7.3   Estimation loss via Marchenko–Pastur and the information coefficient
Linearising ŵ(γ) around (Σ, µ) gives δw = −Pγ−1 (δPγ )Pγ−1 µ + Pγ−1 δµ with δPγ = γδΣ + (1 −
γ)δD. Both terms are of the form “Pγ−1 applied to noise,” so both inherit the same amplification
factor. Because the downstream Sharpe is scale-invariant, the relevant conditioning is the Jacobi-
preconditioned condition number
                                                       (1 − γ) + γ λmax (C)
                           κeff (γ) := κ(D−1 Pγ ) =                         ,                      (44)
                                                       (1 − γ) + γ λmin (C)

not κ(Pγ ): the congruence Pγ = D1/2 [(1 − γ)I + γC]D1/2 preserves inertia but not eigenvalues, so
κ(Pγ ) mixes volatility dispersion κD with correlation conditioning in a way that is generically a
strict upper bound. The object in (44) interpolates monotonically from 1 at γ = 0 to κ(C) at γ = 1;
volatility dispersion κD does not appear.
    Two ingredients size the noise. First, the Marchenko–Pastur concentration rate [Marchenko and
Pastur, 1967] gives                                      q
                                   ∥Σ̂ − Σ∥op = Op σmax
                                                    2
                                                                                                   (45)
                                                                   
                                                        N/T ,
tight on Gaussian data in the proportional regime N/T → q ∈ (0, 1) [Vershynin, 2012, Thm. 5.39].
Second, modelling the signal estimator as µ̂i = µi + ϵi with IC = Corr(µ̂i , µi ) gives, by independence
of µ and ϵ,
                                                    2 1 − IC
                                                              2
                                     Var(ϵi ) = σµ,i            .                                   (46)
                                                         IC2
For typical active managers IC ∈ [0.02, 0.10], so 1/IC2 ∈ [100, 2500]: signal noise dwarfs signal
magnitude, and the 1/IC2 factor is the dominant term in any realistic estimation-loss calculation.
    Propagating δw through the Sharpe-squared, bounding the covariance channel with (45) and
the signal channel with (46), and pulling the common amplification κeff (γ)2 out front yields the
estimation-loss formula:
                                                          N       1
                                  V (γ) ≈ B · κeff (γ)2 ·    · 2,                                   (47)
                                                           T IC
where B = B(Σ) is an order-one constant depending on the eigenvalue distribution of Σ and on how
the signal projects onto its eigendirections, but not on γ, T , or IC. The volatility dispersion κD
does not appear in κeff ; any problem-dependent scaling it induces is absorbed into B.

7.4   First-order γ ⋆ and comparative statics
Linearising κeff (γ)2 around γ = 0 gives

                                κeff (γ)2 ≈ 1 + 2γ λmin (C) (κC − 1),                              (48)

with κC = κ(C). The factor λmin (C) is non-trivial: for equicorrelation at ρ = 0.6 it equals 1−ρ = 0.4,
so the slope is only 40% of the naive 2(κC − 1). The total expected loss is
                                                                    N
                               L(γ) = (1 − γ)2 A + B κeff (γ)2          .                          (49)
                                                                  T IC2
Setting ∂L/∂γ = 0, solving, and converting the linear FOC to a Padé form that respects γ ⋆ ∈ (0, 1]:

                                           1                 1
                              γ⋆ ≈                =                  ,                             (50)
                                      1 + c · NSR            κ(C)2 N
                                                       1 + c
                                                              IC2 T

                                                  40
where
                                   κ(C)2 N              B λmin (C) (κC − 1)
                         NSR =             ,      c =                       .
                                    IC2 T                       A κ2C
This is the adaptive γ rule. The qualitative content is summarised below.
Proposition 7.1 (Comparative statics of γ ⋆ ). Fix c > 0 and consider (50).
  (i) γ ⋆ is increasing in T /N : more data permits more aggressive use of off-diagonal structure.
 (ii) γ ⋆ is increasing in IC: a stronger signal justifies more aggressive optimisation because the
      signal-noise channel in V (γ) shrinks.
 (iii) γ ⋆ is decreasing in κ(C): worse correlation conditioning amplifies estimation noise on low-
       eigenvalue directions.
 (iv) γ ⋆ → 1 as T /N → ∞ (classical Markowitz recovery); γ ⋆ → 0 as IC → 0 (inverse-variance
      recovery); γ ⋆ = 1 when κ(C) = 1 (uncorrelated assets).
   The proof is immediate from the monotonicity of x 7→ 1/(1 + cx) and is recorded in Appendix A.

7.5     Calibration: the OOS Sharpe surface is flat
We calibrated (50) on a 48-cell synthetic grid (4 covariance regimes: factor, block, spiked, equicorre-
lation; 4 values of T /N ; 3 values of IC), and validated on a disjoint 108-cell grid (results/sec09_
adaptive/; see Section 10.4.2). The headline findings:
• The OOS Sharpe surface is nearly flat in γ: the median width of the plateau of γ values within
  2% of peak Sharpe is 0.38 on [0, 1].
• The empirical γ ⋆ varies by regime but weakly: factor 0.18, spiked 0.20, equicorrelation 0.30, block
  0.44.
• The two-parameter fit of (50) has R2 ≈ −0.11 out-of-sample; the spectral constant c spans 438×
  across regimes.
The practical upshot is that the value of the adaptive formula is explanatory, not prescriptive: it
tells us why a fixed γ = 0.5 is near-optimal—the plateau is wide and γ = 0.5 lies inside every cell’s
plateau—rather than providing an adaptive-intensity prescription that dominates the fixed choice.
The practitioner rule remains γ = 0.5.

7.6     Three regularisation channels
The preceding analysis treated γ as the lone tuning knob, but CRISP with finite sweep count p
contains three distinct mechanisms that damp the amplification of estimation error. We name them
and record which are active at the recommended operating point.
Remark 7.2 (Three regularisation channels in CRISP). Channel 1 — operator shrinkage via γ.
Replacing Σ with Pγ = (1 − γ)D + γΣ reduces the effective conditioning from κ(Σ) to κeff (γ),
damping amplification of estimation noise on low-eigenvalue directions. Statistical, primary, active
at the practitioner’s γ ≈ 0.5.
    Channel 2 — convergence slack from finite p. At finite sweep budget, the Gauss–Seidel iterate
has not reached the fixed point Pγ−1 µ; the residual bias pushes the portfolio toward the diagonal
initialisation D−1 µ. This is a computational artefact that vanishes as p → ∞; it is negligible at
p = 100 for γ ≈ 0.5.

                                                  41
                                   Width of the -insensitive Sharpe plateau (within 2\% of peak)
       fac T/N=0.6 IC=0.02
       fac T/N=0.6 IC=0.05
       fac T/N=0.6 IC=0.10
       fac T/N=1.0 IC=0.02
       fac T/N=1.0 IC=0.05
       fac T/N=1.0 IC=0.10
       fac T/N=2.0 IC=0.02
       fac T/N=2.0 IC=0.05
       fac T/N=2.0 IC=0.10
       fac T/N=5.0 IC=0.02
       fac T/N=5.0 IC=0.05
       fac T/N=5.0 IC=0.10
       blo T/N=0.6 IC=0.02
       blo T/N=0.6 IC=0.05
       blo T/N=0.6 IC=0.10
       blo T/N=1.0 IC=0.02
       blo T/N=1.0 IC=0.05
       blo T/N=1.0 IC=0.10
       blo T/N=2.0 IC=0.02
       blo T/N=2.0 IC=0.05
       blo T/N=2.0 IC=0.10
       blo T/N=5.0 IC=0.02
       blo T/N=5.0 IC=0.05
       blo T/N=5.0 IC=0.10
       spi T/N=0.6 IC=0.02
       spi T/N=0.6 IC=0.05
       spi T/N=0.6 IC=0.10
       spi T/N=1.0 IC=0.02
       spi T/N=1.0 IC=0.05
       spi T/N=1.0 IC=0.10
       spi T/N=2.0 IC=0.02
       spi T/N=2.0 IC=0.05
       spi T/N=2.0 IC=0.10
       spi T/N=5.0 IC=0.02
       spi T/N=5.0 IC=0.05
       spi T/N=5.0 IC=0.10
      equ T/N=0.6 IC=0.02
      equ T/N=0.6 IC=0.05
      equ T/N=0.6 IC=0.10
      equ T/N=1.0 IC=0.02
      equ T/N=1.0 IC=0.05                                                                          factor
      equ T/N=1.0 IC=0.10                                                                          block
      equ T/N=2.0 IC=0.02
      equ T/N=2.0 IC=0.05
      equ T/N=2.0 IC=0.10
                                                                                                   spiked
      equ T/N=5.0 IC=0.02                                                                          equicorr
      equ T/N=5.0 IC=0.05
      equ T/N=5.0 IC=0.10
                                                                                                     = 0.5
                                                                                                    emp

                             0.0        0.2             0.4            0.6             0.8                1.0

Figure 4: Horizontal plateau-width bars per cell (plateau = set of γ within 2% of peak OOS Sharpe),
grouped by covariance regime. The dashed vertical line at γ = 0.5 lies inside every bar. The
wide plateaus rationalise the fixed default: on the regimes studied, γ = 0.5 is within 2% of the
regime-specific empirical optimum.


    Channel 3 — implicit spectral truncation via early stopping. Because Gauss–Seidel converges
high-eigenvalue directions of D−1 Pγ before low-eigenvalue ones (Theorem 5.3), stopping at p sweeps
implicitly projects the portfolio onto the well-estimated spectral subspace. Unlike Channel 2,
Channel 3 has a statistical motivation: reaching the fixed point on noisy Σ̂ would restore exposure
to noise-dominated directions. Active at γ = 1; dormant at γ = 0.5.

Operating-point summary. At the recommended (γ ⋆ ≈ 0.5, p = 100), Channel 1 dominates;
Channels 2 and 3 are essentially dormant because κeff (0.5) is small enough that p = 100 reaches
the Sharpe plateau. At γ = 1 with finite p, all three channels are active, and Channel 3 provides
measurable OOS benefit on noisy Σ̂ (Section 10.4.1). The γ = 1 peak in p is nevertheless dominated
by the interior-γ plateau on every panel tested.




                                                         42
7.7    Information-theoretic reading
The bias–variance decomposition admits a clean information-theoretic restatement. Working in
the correlation basis with eigenvalues λ1 ≥ · · · ≥ λN > 0, tr(C) = N , the shrinkage operator
D−1/2 Pγ D−1/2 = (1 − γ)I + γC has eigenvalues pk (γ) = (1 − γ) + γλk , and the KL divergence from
the true return distribution to the shrunk one (holding µ fixed) is
                                                           N 
                                                               λk
                                                                                                
                  DKL N (µ, Σ) ∥ N (µ, Pγ ) =                             − 1 + ln pk (γ) − ln λk .    (51)
                                                           X
                                                       1
                                               
                                                       2
                                                           k=1
                                                                 pk (γ)

At γ = 1 this is zero (no information discarded); at γ = 0 it equals 12 ln det(C −1 ), the total correlation
information in Σ beyond the diagonal. Shrinkage is therefore controlled information loss: γ is a dial
that deliberately discards correlation content.
    Estimation adds a second source of distortion. The OOS quality depends on a total information
budget
                                DKL (Σ ∥ Pγ )     + E DKL (Pγ ∥ P̂γ ) ,
                                                                         
                                  |      {z        }             |         {z       }
                              shrinkage bias, dec. in γ      estimation noise, inc. in γ

and γ ⋆ is the level at which one additional nat of correlation information retained is exactly offset by
one additional nat of estimation noise introduced. On the base-case covariance (N = 100, κ(C) = 61,
T = 120, oracle µ), the shrinkage KL at the empirical γ ⋆ ≈ 0.30 is 11.6 nats—about 31% of the
37.4 nats of total correlation information—and the OOS Sharpe is 96% of oracle, against 45% at
γ = 1 (estimation dominates) and 64% at γ = 0 (all correlation discarded).

Rate-distortion gloss. The correlation matrix has N2 off-diagonal entries, but with T samples
                                                                      

only O(T ) independent linear functionals are reliably estimated. The “rate” is reliable bits per
covariance entry; the “distortion” is portfolio Sharpe loss. Shrinkage is a coding scheme that
allocates information capacity to the large-eigenvalue directions of C (which survive at γ < 1) and
discards the small-eigenvalue ones (dominated by noise). Channel 1 sets the rate; Channel 3 (early
stopping) reshapes the allocation; Channel 2 is residual at the recommended operating point.

7.8    P6 revisited: the clean-signal paradox
The three-channel picture resolves an otherwise puzzling asymmetry. From results/sec09_sweep/
convergence_table.csv, the OOS Sharpe penalty at γ = 1 is 17× larger under an oracle µ than
under a noisy µ̂: the oracle-µ peak-to-converged gap is 0.253, while the noisy-µ̂ gap is 0.015. Naively,
one might expect noise in µ̂ to worsen the penalty.
     The information-theoretic reading gives the explanation. Under oracle µ, all information flows
through Σ̂, so any corruption from Σ̂−1 amplification at γ = 1 is maximally costly. Under noisy
µ̂, the signal noise already diffuses portfolio direction across eigenvectors—it pre-regularises the
portfolio against Σ̂ noise by blurring the signal’s spectral profile. Early stopping (Channel 3) is
therefore most beneficial exactly when µ has real information worth protecting. This is prediction
P6 in the pre-registered block (Section 10.4.1); the three-channel decomposition of Remark 7.2
predicts both the sign and order of magnitude of the asymmetry.


8     Comparative landscape
Sections 3–7 developed five allocation rules — HRP [López de Prado, 2016], Cotton [Cotton, 2024],
HRP-µ, HRP-Σµ, and CRISP — each a distinct point in the space of hierarchical and iterative

                                                           43
Table 7: Method landscape: signal, structure, and cost. 1 denotes the flat signal; “any µ” means
an arbitrary signed expected-return vector. Tree-based costs assume a depth-O(log N ) hierarchy.
CRISP cost is quoted per target precision ε.

Method    Signal   Uses tree   Cross-branch info                    Cost               Role in paper
HRP       1 only   Yes         None                                 O(N 2 )            Prior baseline
Cotton    1 only   Yes         D−1 B ⊤ via Schur                    O(N 3 /6)          Prior baseline
HRP-µ     Any µ    Yes         Scalar c (diagonal within-cluster)   O(N 2 )            Contribution
HRP-Σµ    Any µ    Yes         Scalar c (full within-cluster)       O(N 2 )            Recommended tree method
CRISP     Any µ    No          Entrywise σij                        O(κN 2 log ε−1 )   Headline contribution

Table 8: Behaviour of each method at the four corners of the (γ, µ) square, with stability profile.
“Any µ” denotes a heterogeneous, possibly mixed-sign signal.

Method    γ=0, µ=1              γ=0, any µ         γ=1, µ=1           γ=1, any µ           Stability
HRP       HRP                   —                  —                  —                    Stable
Cotton    Min-var hierarchy     —                  Exact Σ−1 1        —                    Unstable at small T
HRP-µ     De Prado (exact)      Signed HSP         Tree approx.       Tree approx.         Stable (deterministic)
HRP-Σµ    ≈ De Prado            Recursive MVO      ≈ Σ−1 1            ≈ Σ−1 µ              Stable (generic)
CRISP     µi /σi2               µi /σi2            Exact min-var      Exact Markowitz      Stable


mean-variance constructions. No new machinery is introduced here; the goal is to collapse the
preceding six chapters into four tables and a short practitioner’s guide keyed to γ, µ, and the
correlation condition number κ(C). Empirical claims forward-reference the panels in Section 10.

8.1   Method landscape
Table 7 records, for each method, the admissible signal, whether a clustering tree is required, how
cross-branch information is represented, the per-solve cost, and the role played in the paper. Two
facts stand out. First, HRP and Cotton are the only methods restricted to the flat signal µ = 1;
the three signal-aware methods extend to arbitrary µ with no loss of numerical stability. Second,
only Cotton propagates the full cross-branch sub-covariance through the tree, at O(N 3 /6) total;
the HRP-µ family compresses cross-branch information into a scalar per internal node and runs
in O(N 2 ); CRISP dispenses with the tree entirely and solves Pγ w = µ by flat Gauss–Seidel at
O(κN 2 log ε−1 ) per target precision ε [Stein, 1956; Ledoit and Wolf, 2003].

8.2   Behaviour at the four corners of (γ, µ)
Table 8 reads each method across the four corners of the (γ, µ) square and records its stability
profile. The entries are all direct consequences of results stated in earlier sections: the HRP and
De Prado recoveries come from Section 4, the signed HSP endpoint from Section 4.3.1, the Cotton
γ = 1 limit from Section 3.2, and the two CRISP limits from Section 5. The single qualitative
observation worth promoting out of the table is that only CRISP reaches exact Markowitz at γ = 1
for a general signal µ; every tree-based method terminates at a tree-constrained approximation
there, because the tree itself is a hard constraint on the feasible set of weight vectors.




                                                      44
Table 9: Computational profile. “Factor streaming” indicates whether a method can compute Σi,· · w
on the fly from Σ = BΛB ⊤ + Didio with K factors, reducing per-sweep cost to O(N K 2 ) and working
memory to O(N K). CRISP rows quote p sweeps at target precision ε.

Method                        Per-solve FLOPs   Peak memory (dense)   Factor streaming?   Memory with factors
Direct Markowitz (Cholesky)   O(N 3 )           ∼ 2N 2                No†                 ∼ 2N 2
Ledoit–Wolf + Markowitz       O(N 3 )           ∼ 2N 2                No†                 ∼ 2N 2
HRP                           O(N 2 log N )     ∼ N2                  No                  ∼ N2
Cotton                        O(N 3 /6)         ∼ N2                  No                  ∼ N2
HRP-µ                         O(N 2 log N )     ∼ N2                  No                  ∼ N2
HRP-Σµ                        O(N 2 log N )     ∼ N2                  No                  ∼ N2
CRISP (dense)                 O(pN 2 )          ∼ N2                  n.a.                ∼ N2
CRISP (factor streaming)      O(pN K 2 )        ∼ N2                  Yes                 O(N K)


8.3    Computational profile
Table 9 records per-solve FLOPs, peak working memory for a dense Σ, whether the method can
exploit a factor decomposition Σ = BΛB ⊤ + Didio to stream rows on the fly, and memory in
that factor-streaming regime. The CRISP rows quote p sweeps of the Gauss–Seidel iteration;
p = O(κ(D−1 Pγ ) log ε−1 ) at target precision ε, as established in Theorem 5.3. The practical point
is not wall-clock: CRISP’s numerical advantage at γ ⋆ ≈ 0.5 is bias–variance, not FLOPs, and
at small N direct Cholesky is often faster. The practical point is memory: the factor-streaming
variant reduces the working set from O(N 2 ) to O(N K), which becomes the binding resource at
Russell-all-cap scale.
† The Woodbury identity inverts a factor-structured Σ exactly in O(N K 2 + K 3 ), but the resulting

weight vector is the full Markowitz solution and carries the same out-of-sample penalty as dense
Cholesky; it is a computational optimisation of direct Markowitz, not a competitive allocation rule
[Fan, Liao and Mincheva, 2013; Ledoit and Wolf, 2017].

8.4    Key relationships
Cotton vs. HRP-µ/HRP-Σµ. Cotton and the HRP-µ family share endpoints when µ = 1 — a
tree allocation at γ = 0 and an approximation to Σ−1 1 at γ = 1 — but trace different γ-continua
between them. Cotton modifies the full sub-covariance on each branch via a Schur complement
at O(N 3 /6); HRP-µ and HRP-Σµ compress all cross-branch information into a single scalar per
internal node and run in O(N 2 ). A user comfortable with block inversion on each branch may still
prefer HRP-Σµ for pure speed on large trees.

Cotton vs. CRISP. Cotton and CRISP both reach Σ−1 1 at γ = 1 when µ = 1, via completely
different routes: recursive block inversion on the tree at O(N 3 ) for Cotton, flat Gauss–Seidel
iteration at O(κN 2 log ε−1 ) for CRISP. For a general µ =
                                                         ̸ 1 the comparison ceases to be meaningful
because Cotton is undefined; there is no heterogeneous-signal extension of Cotton’s Schur pass.

Hierarchical methods vs. CRISP. The HRP-µ family and CRISP have incompatible γ = 0
endpoints: HRP-µ collapses to a hierarchical signed HSP construction and HRP-Σµ to a recursive
MVO, while CRISP collapses to the flat diagonal allocator µi /σi2 . They agree only at γ = 1,
and even there the tree methods are tree-constrained approximations while CRISP is the exact
Markowitz solve. Across every out-of-sample Sharpe panel in Section 10, CRISP dominates both



                                                       45
HRP-µ and HRP-Σµ; the reason is not subtle — the tree is a hard constraint, and whenever the
data do not line up with the dendrogram, the tree-constrained solve is worse than the flat one.

Sign-flip pathology. The sum-normalised recursive MVO of Appendix C illustrates why signed
signals demand care: a natural recursive-normalisation scheme can produce portfolios in the wrong
direction, and the sign-invariant direction metric of Section 2 will not see the error. HRP-Σµ fixes
the pathology via L1 child-rescaling (Lemma 4.5); HRP-µ avoids it by carrying leaf signs explicitly.

HRP as common ancestor. Every other method in the table can be read as a departure from
HRP along one or more of three axes: adding cross-branch covariance at γ > 0 (Cotton, HRP-µ),
replacing 1 with a heterogeneous signal µ (HRP-µ, HRP-Σµ, CRISP), and replacing the tree walk
with a flat iterative solve (CRISP). HRP itself sits at the intersection of all three “do-nothing”
choices; the methodological contributions of this paper are the systematic relaxation of each axis in
turn.

8.5   Practitioner’s guide
The six scenarios below are phrased as concrete settings paired with concrete recommendations,
each keyed to a value of γ or to the diagnostic κ(C) = λmax (C)/λmin (C) of the correlation matrix
C = D−1/2 ΣD−1/2 .

1. CRISP at γ ≈ 0.5 — default recommendation. A signal-aware portfolio with any µ,
any N , a moderate-to-high N/T ratio where shrinkage is economically valuable, and a reasonably
well-conditioned correlation matrix. CRISP converges in O(κ log ε−1 ) sweeps at this γ, inherits the
stability of a shrunk operator, and tracks oracle Sharpe closely across the panels in Table 17.

2. CRISP at γ ≈ 0.7 for minimum variance. An exact minimum-variance mandate (µ = 1) in
the regime where a Ledoit–Wolf analytic-shrinkage intensity would land near 0.3 [Ledoit and Wolf,
2003, 2017]. CRISP at the complementary γ ≈ 0.7 recovers 80–92% of oracle minimum-variance
Sharpe across every T in Table 19; this is our production recommendation for pure min-var.

3. HRP-µ / HRP-Σµ for hierarchical interpretability. Signal-aware portfolios where a
decomposition along the cluster tree is itself a deliverable — risk attribution by branch, sector-tilt
reporting, or a governance regime that demands tree-transparent weights. HRP-Σµ is the stronger
of the two (Proposition 4.12) and is the recommended tree-based method; HRP-µ is preferable when
strict deterministic cost with only marginal variances is required. Both are dominated by CRISP on
out-of-sample Sharpe, so the choice should be understood as an interpretability-for-performance
trade.

4. Cotton for pure min-var on well-conditioned Σ. Minimum variance at moderate N
with a shrunk or factor-based covariance, where the O(N 3 /6) Schur pass is affordable and the full
cross-branch continuum is theoretically desirable. Cotton is not recommended for minimum variance
on a sample covariance at small T ; the intermediate-γ instability flagged in Section 3.2 activates
precisely in that regime.




                                                 46
Table 10: Interpreting κ(C): what it means for method choice and CRISP sweep budget. κ(C) is
computed once from the risk model and determines problem difficulty.

    κ(C)   Regime        Example                             CRISP sweeps (p)      Tree methods
   1–10    Easy          Low-correlation factor model        50–100 (any γ)        All similar; tree adds little
 10–150    Moderate      Diversified equity, 5 sectors       100–500 (γ = 0.5)     HRP-Σµ > HRP-µ
150–500    Hard          Concentrated sectors, ρw ≥ 0.7      500–2,000 (γ = 0.5)   HRP-Σµ ≫ HRP-µ
  > 500    Adversarial   Near-equicorrelated + hedge pairs   5,000+ (adaptive γ)   Tree-constrained; prefer CRISP


5. HRP when classical long-only tree-decomposability is required. A strictly non-negative,
tree-decomposable allocation under µ = 1, in a reporting or governance setting where those two
constraints are hard. HRP is beaten by CRISP on min-var Sharpe at every sample size tested,
but remains pedagogically important, trivially transparent, and the correct default when µ = 1 is
genuinely the right assumption.

6. κ(C) as a pre-flight diagnostic. The single most informative pre-flight number a practitioner
can compute is κ(C); this is the condition number of the correlation matrix, not of Σ (which is
inflated by volatility dispersion) and not a determinant. Table 10 reads κ(C) into a regime, a typical
example, a CRISP sweep budget, and a tree-method verdict. The governing theory is Theorem 5.3:
κ(C) controls both the directional difficulty of the portfolio problem and the iteration count of
CRISP.

8.6    When not to use a tree
Two regimes render a tree-based method unattractive. First, when κ(C) is small, every method in
Table 7 produces similar portfolios because the off-diagonal structure a hierarchical splitter exploits
is weak; CRISP at moderate γ remains the cleanest default since it still benefits from shrinkage and
does not require building a dendrogram. Second, when N is very large and Σ is dense, Cotton’s
O(N 3 ) cost is prohibitive; HRP-µ and HRP-Σµ remain O(N 2 ) but are dominated on Sharpe by
CRISP, which is also O(N 2 ) per sweep and, critically, can exploit the factor-streaming variant of
Algorithm 3 to collapse working memory from O(N 2 ) to O(N K). In either regime, CRISP wins
not because hierarchical methods fail but because, in the synthetic experiments of Section 10, it
combines stronger out-of-sample performance with the absence of a dendrogram constraint.


9     Constraint handling
The development so far has been unconstrained: the only requirement on w was that it sum to one.
In practice, portfolio managers impose box bounds, sector caps, factor-exposure limits, and turnover
restrictions. This short section sketches how HRP-µ, HRP-Σµ, and CRISP extend to those settings
without disturbing the direction-metric machinery of Sections 2–6. Constraint handling is not the
main contribution of the paper; a full treatment warrants a separate paper. Our aim here is only to
show that the three methods degrade gracefully.

9.1    QP reference formulation
The textbook constrained mean–variance problem reads
                    1 ⊤       ⊤
              min   2 w Σw − w µ         s.t.   1⊤ w = 1, ℓ ≤ w ≤ u, Aw ≤ b, ∥w − w0 ∥1 ≤ τ.                (52)
             w∈RN


                                                       47
Algorithm 4 Projected CRISP with box and linear constraints
Require: Σ, µ, γ, p, ℓ, u, A, b
Ensure: w with Aw ≤ b, ℓ ≤ w ≤ u, 1⊤ w = 1
 1: D ← diag(Σ); Pγ ← (1 − γ) D + γ Σ
 2: w ← µ/D                                                          ▷ diagonal initialisation
 3: for sweep = 1, . . . , p do
 4:    for i = 1, . . . , N do
          ri ← µi − j̸=i (Pγ )ij wj
                         P
 5:
 6:       wi ← ri /(Pγ )ii
 7:       wi ← max(ℓi , min(wi , ui ))                                     ▷ local box clamp
 8:    end for
 9:    w ← ΠC (w)                                     ▷ project onto {w : Aw ≤ b, 1⊤ w = 1}
10: end for
11: return w


Four constraint families appear. Box bounds ℓi ≤ wi ≤ ui encode per-asset limits; the long-only
special case is ℓi = 0, ui = 1. Sector caps use an indicator matrix G ∈ {0, 1}K×N with Gki = 1 iff
asset i lies in sector k, giving Gw ≤ bsec . Factor-exposure constraints use a loading matrix F ∈ RM ×N
and impose |F w| ≤ bfac , linearised to a pair of inequalities. Turnover against an incumbent w0
is ∥w − w0 ∥1 ≤ τ ; the ℓ1 term is linearised via auxiliaries d±                                  −
                                                                  i ≥ 0 with wi − w0,i = di − di and
                                                                                             +
             −
   i (di + di ) ≤ τ . All four fold into the Aw ≤ b block of (52).
P +

      There is a well-known subtlety. Jagannathan and Ma [2003] show that adding a wrong constraint—
long-only when the true optimum has shorts, say—can nonetheless improve out-of-sample Sharpe,
because the constraint implicitly shrinks the estimated covariance. The implication for this paper is
important: any apparent advantage of constrained over unconstrained QP need not be evidence that
the constraint is optimising; it may be acting as a crude regulariser. CRISP captures that shrinkage
directly, through the Pγ trajectory of Section 6, and separates it from the constraints themselves.
Constraints should therefore be imposed for what the investor actually wants—exposure control,
leverage, liquidity—and the regularisation should be supplied by the shrinkage intensity γ, not
smuggled in through a binding box.

9.2   Projected CRISP
CRISP extends cleanly to (52) through projected Gauss–Seidel. Let C denote the closed convex
feasible set defined by the budget, box, and linear-inequality blocks of (52), and let ΠC be orthogonal
projection onto C. After each coordinate update we clamp to the box; at the end of each sweep we
project onto C. Algorithm 4 states the procedure.
    Convergence. Under the SPD assumption on Pγ that underwrites Theorem 5.2, the unconstrained
Gauss–Seidel map is a contraction in the Pγ -induced norm, and ΠC is nonexpansive in the Euclidean
norm. Composition with a similarity transform gives a contraction onto the constrained minimiser;
the O(N 2 ) per-sweep cost is preserved, with the projection step a lower-order correction in all cases
of practical interest.
    The cost of the projection step depends on C:

  • Pure box + budget. ΠC reduces to a 1D simplex-style renormalisation and re-clamp,
    implementable in O(N log N ).

  • Sector groups. ΠC becomes a small QP in the group dimension (one per group), negligible


                                                  48
      against the O(N 2 ) sweep.
   • Active-set variant. Classify constraints by KKT residuals at the start of each sweep, freeze
     coordinates on the active face, and run the unconstrained sweep on the complement. This
     mirrors standard active-set QP practice while retaining O(N 2 ) per sweep outside the active
     set.

Alternative for practitioners with a QP solver. A cleaner path for anyone who already has
a convex QP solver is to substitute Pγ for Σ
                                           b in the objective of (52):

           min 12 w⊤ Pγ w − w⊤ µ     s.t.   1⊤ w = 1, ℓ ≤ w ≤ u, Aw ≤ b, ∥w − w0 ∥1 ≤ τ,           (53)
             w

and hand the problem to OSQP [Stellato et al., 2020], Clarabel [Goulart and Chen, 2024], MOSEK,
or Gurobi. This captures the statistical contribution—shrink the operator, not the estimator—at
the solver’s native speed, without requiring projected CRISP to be implemented in-house. The
transportable idea for constrained problems is the Pγ target; projected CRISP is an optional
self-contained alternative.

9.3   Constrained HRP-µ and HRP-Σµ
The tree methods accommodate two constraint families cleanly.
    Long-only. At each internal node, project the between-branch split α onto [0, 1]; within-branch
weights are clamped to [0, ∞) at the leaf solve. For HRP-Σµ the node-level 2 × 2 QP is replaced by
its box-constrained variant: if both unconstrained components are nonnegative, accept the interior
optimum; otherwise clamp the negative component to zero and allocate fully to the positive side.
Both variants preserve the recursive O(N log N ) structure.
    Sector caps, tree-aligned. When the hierarchy is sector-aligned, a cap on a sector’s total weight is
a cap on the cumulative budget flowing to the corresponding subtree, enforced by a one-dimensional
clip on the α-products along the root-to-subtree path. Tree-aligned constraints are essentially free.
    Constraints that cut across the tree—arbitrary sector caps not aligned with the hierarchy, factor-
exposure inequalities, turnover against a non-aligned incumbent—do not admit clean recursion. For
such problems, projected CRISP of Section 9.2 is strictly preferable.

9.4   Worked example: long-only, sector-capped
Consider the paper’s base-case universe (N = 100, five sectors of twenty) with the structural signal
µ = (+0.04, −0.04, +0.02, −0.02, 0) tiled across sectors. We impose long-only (wi ≥ 0), a 30% cap
on each sector, and the budget 1⊤ w = 1.
    Projected CRISP at γ = 0.5 produces a portfolio in which the two negative-µ sectors (2 and 4)
receive zero weight—the long-only constraint binds—and sectors 1 and 3 share the budget subject
to the 30% cap, with the residual flowing to the neutral sector 5. Sector 1 (the highest-signal group)
sits at its cap; sector 3 sits strictly below it; sectors 2 and 4 sit at zero. The active set stabilises
within two to three sweeps: zero-weight assets are identified early and frozen, the cap on sector 1
activates on the second sweep, and the remaining coordinates converge on the unconstrained face at
the rate given by Theorem 5.3.
    The shrinkage path still matters under the constraints. At γ = 0 the constrained portfolio
reduces to wi ∝ max(µi , 0)/σi2 —a purely signal-weighted allocation within the feasible sectors. At
γ = 0.5 the operator shrinkage reintroduces cross-asset covariance, reducing concentration within the
positive-signal sectors and producing a more diversified allocation consistent with the unconstrained
behaviour documented in Section 6.

                                                  49
9.5    Discussion
Four caveats are worth making explicit.
    First, constraint handling is not a central contribution of this paper. The role of this section is
to show that the HRP-µ/HRP-Σµ/CRISP machinery degrades gracefully; we do not claim projected
CRISP outperforms a modern QP solver on heavily constrained problems. For problems dominated
by constraint activity—index replication with dozens of active inequalities—a specialised active-set
or interior-point solver remains the right tool. The statistical contribution transports cleanly
through (53).
    Second, the tree methods handle only tree-aligned constraints cleanly. Long-only, box bounds,
and sector caps on aligned subtrees fit the recursion; general linear inequalities that cut across the
hierarchy do not. For heavily constrained problems the tree methods are therefore not the right
tool; the CRISP shrinkage idea—either via (53) or via projected CRISP—is.
    Third, the direction-error analysis of Section 6 does not apply directly to constrained problems.
That analysis rests on the ray invariance of the Pγ family: scaling a solution by a positive constant
preserves direction. A constraint set like ℓ ≤ w ≤ u is not scale-invariant, so a uniformly scaled
direction may lie inside the box at one scale and outside at another. Adapting the direction metric
to the active face of C is an interesting question but non-trivial, and we flag it as future work in
Section 11.
    Fourth, the out-of-sample evaluation in Section 10 is primarily unconstrained; long-short results
isolate the shrinkage-trajectory effect and let us compare direction errors cleanly. Long-only
comparisons using Algorithm 4 are noted but relegated to Appendix E, or to future work.


10     Synthetic experiments
This section presents the empirical heart of the paper in three layers. Part A (Sections 10.2.1–
10.2.6) is an in-sample direction-error diagnostic battery that verifies the theory of Sections 4–6
on known ground truth: method identities at γ = 0, µ = 1, Gauss–Seidel convergence rates, and
the non-monotone shrinkage trajectory. Part B (Sections 10.3.1–10.3.3) is an out-of-sample Monte
Carlo tournament that establishes a method ranking under realistic estimation noise across two
signal families, four sample sizes, and the minimum-variance limit. Part C (Sections 10.4.1–10.4.2)
probes sweep count as a third regularisation channel, runs the eight pre-registered predictions of
Section 7, and calibrates the adaptive γ ⋆ rule. All experiments use the same base universe and seed
protocol described next.

10.1    Setup
Base universe. Unless otherwise stated, N = 100 for Monte Carlo and N = 200 for in-sample
diagnostics. Assets are split into five equal-size sectors of N/5 each. The correlation block structure
is ρw = 0.6 within sector and ρc = 0.15 across sectors; volatilities σi are drawn once from U[0.15, 0.40].
This yields correlation condition number κ(C) ≈ 61 at N = 100 and κ(C) ≈ 121 at N = 200. The
global seed is 42 for reproducibility.

Stress regimes.      Four covariance regimes appear in Part A and Part C:

 (i) Factor model with k = 3 latent factors; κ(C) ≈ 111.
(ii) Hedges + tight blocks (intra-block ρ = 0.8, selected hedge pairs ρ = −0.6); κ(C) ≈ 5.75 × 104 .



                                                   50
Table 11: Experiment 1: recovery of De Prado’s HRP at γ = 0, µ = 1. Base universe, N = 200.
“Rel. diff.” is ∥w − wHRP ∥/∥wHRP ∥ on weights normalised to sum one; “cos” is cos ∠(w, wHRP ).

              Comparison                                    Rel. diff.    cos ∠    Verdict
              Cotton(γ = 0) vs HRP                        4.91 × 10−1     0.881    differ
              Flat IVP(γ = 0, µ = 1) vs HRP               1.62 × 10−16    1.000    match
              Sum-norm MVO(γ = 0, µ = 1) vs HRP           1.36 × 10−1     0.992    differ
              HRP-Σµ(γ = 0, µ = 1) vs HRP                 1.36 × 10−1     0.992    approx


(iii) Numerical worst-case µ, obtained by maximising the direction error of the naive diagonal
      solution µ/ diag(Σ) against Σ−1 µ by L-BFGS-B on the unit sphere.
(iv) Structural µ: tiled sector tilts (+0.04, −0.04, +0.02, −0.02, 0) that are aligned with the block
     structure of C and therefore recoverable only via signal-aware allocation.

Methods. Part A compares Cotton (Schur complementary allocation), flat inverse-variance
portfolio (IVP), the sum-normalised recursive mean–variance allocator (diagnostic only; denoted
“sum-norm MVO” and corresponding to the method_a1 code path), HRP-µ (method_a1_l1), HRP-Σµ
(method_a3), and CRISP (method_b) at a fixed sweep count p = 200 unless otherwise noted. Part B
adds 1/N , De Prado’s HRP, and direct Markowitz w = Σ        b. Part C also benchmarks against
                                                        b −1 µ
Ledoit–Wolf linear [Ledoit and Wolf, 2003] and analytical nonlinear shrinkage [Ledoit and Wolf,
2020]. CRISP in Part B and Part C always runs with p = 100 sweeps.

Monte Carlo replication. Cell-wise replication counts are tuned to the statistic being reported:
40 trials/cell for Experiment 7 (OOS sensitivity across µ seeds), 80 trials/cell for Experiments 8–9,
200 trials/cell for Experiment 11 (sweep regularisation), and 500 trials/cell for Experiment 12
(adaptive calibration). Walk-forward sample sizes sweep T ∈ {60, 120, 240, 500}.

10.2     Part A — in-sample direction-error diagnostics
The purpose of Part A is to verify, on ground-truth covariances, that the method identities and
convergence-rate claims of Sections 3–6 hold numerically. All tables in this part report direction
error dir(w, w⋆ ) = 1 − cos2 ∠(w, w⋆ ) (Definition 2.1) or scale-sensitive relative error ∥w − w⋆ ∥/∥w⋆ ∥
against exact solutions, not out-of-sample Sharpe.

10.2.1    Experiment 1: De Prado recovery at γ = 0, µ = 1
Table 11 reports relative and cosine differences of four allocators against De Prado’s flat HRP on
the N = 200 base universe at γ = 0, µ = 1. Flat IVP matches HRP to machine precision, as
Proposition 4.2 predicts; HRP-Σµ at the signal-blind point agrees with HRP in direction (cosine
0.992) but not in scale, reflecting the L1 normaliser; Cotton and the sum-normalised MVO allocator
differ from HRP in both. This reproduces the algebraic identities of Section 3.1 and 4.3.

10.2.2    Experiment 2: minimum-variance direction error
Table 12 reports dir(w, Σ−1 1) for five γ values at N = 200 on the base universe. Cotton reaches
machine precision (3.33 × 10−16 ) at γ = 1 through direct block Cholesky; CRISP with p = 200
sweeps tracks the ray to within 5 × 10−4 through most of the interior, with a mild upward drift at


                                                   51
Table 12: Experiment 2: minimum-variance direction error dir(w, Σ−1 1) = 1 − cos2 ∠ on the base
universe, N = 200, µ = 1. Cotton reaches 3.33 × 10−16 at γ = 1 (machine precision); CRISP with
p = 200 sweeps tracks the ray to ≤ 5 × 10−4 over γ ∈ [0.3, 0.7].

         γ         Cotton      CRISP(p = 200)         Flat IVP       HRP-µ       Sum-norm MVO
         0.0    8.39 × 10−1      5.06 × 10−1         9.95 × 10−1   9.95 × 10−1      9.96 × 10−1
         0.3   2.42 × 10−1       1.15 × 10−2         9.82 × 10−1   9.82 × 10−1      9.82 × 10−1
         0.5   7.00 × 10−2       2.42 × 10−3         9.38 × 10−1   9.38 × 10−1      9.46 × 10−1
         0.7   2.12 × 10−2       4.72 × 10−4         4.76 × 10−1   4.76 × 10−1      8.44 × 10−1
         1.0   3.33 × 10−16      1.27 × 10−2         2.09 × 10−1   2.09 × 10−1      6.47 × 10−1

Table 13: Experiment 3: graduated-difficulty direction errors dir(w, Σ−1 µ) at γ ∈ {0.0, 1.0}, N = 200.
Sum-norm MVO is the sum-normalised recursive allocator of Appendix C; CRISP runs at p = 200
sweeps. On easy problems (a–b), CRISP achieves six digits; on (d), every method fails at γ < 1 and
only CRISP recovers as γ → 1.

 Panel    Regime                                     Sum-norm MVO (γ=0 → 1)      CRISP(p=200) (γ=0 → 1)
  (a)     Base universe, µ ∼ N (0, 0.022 )                 0.221 → 0.334         1.3 × 10−2 → 5.2 × 10−5
  (b)     Factor k = 3, κ(C) ≈ 111                         0.113 → 0.123         8.1 × 10−2 → 2.2 × 10−7
  (c)     Hedges + tight blocks, κ(C) ≈ 5.75 × 104         0.986 → 0.978              0.866 → 0.168
  (d)     (c) + worst-case µ, dirdiag = 1.000              0.999 → 0.999              1.000 → 0.457


γ → 1 where conditioning grows as Pγ → Σ. Flat IVP and HRP-µ are large at every γ ̸= 1: they
are consistent with the theory but not competitive on the in-sample direction-error metric for this
problem, and are reported only as diagnostic references.

10.2.3       Experiment 3: graduated difficulty
Table 13 sweeps four panels of increasing difficulty against the general-µ target Σ−1 µ at N = 200.
In panel (a), a generic µ ∼ N (0, 0.022 ) on the base universe, CRISP(p = 200) reaches six digits
of direction accuracy at γ = 1 (5.2 × 10−5 ). Panel (b), a k = 3 factor model with κ(C) ≈ 111, is
the most favourable problem in the suite: CRISP achieves 2.2 × 10−7 at γ = 1. In panel (c), the
hedged tight-block covariance with κ(C) ≈ 5.75 × 104 , the signal-blind target µ/ diag(Σ) is already
essentially orthogonal to Σ−1 µ (dirdiag = 0.866), and every method struggles at γ < 1; CRISP alone
falls to 0.168 at γ = 1. Panel (d) combines (c) with the numerical worst-case µ: dirdiag = 1.000,
every allocator fails at γ < 1, and only CRISP recovers, reaching 0.457 at γ = 1 through iterative
refinement.

10.2.4       Experiment 4: worst-case µ and Lemma 2.3
Lemma 2.3 states that the numerical worst case f