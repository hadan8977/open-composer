# ANN and MPS Signals in a FinRL PPO Agent

This repository evaluates whether a quantum-inspired matrix-product-state
(MPS) prediction signal improves sequential trading decisions relative to a
capacity-recorded artificial neural network (ANN) signal.

The experiment was developed as a follow-up to Dr. Xiao-Yang Liu's
suggestion to test quantum-inspired representations inside a FinRL benchmark,
rather than evaluating them only as prediction models.

## Development history

The initial commit imports an experiment developed before this standalone
repository was published. It includes the first complete research snapshot:
the ANN and MPS models, FinRL integration, saved backtest outputs, integrity
tests, and an initial report. Subsequent commits and pull requests document
repository preparation, reviewer-requested analysis, reproducibility
improvements, and continuing experimental development.

The work progressed through these stages:

1. Compare ANN and quantum-inspired models as stock-return predictors.
2. Add the ANN and MPS predictions separately to the FinRL PPO state.
3. Evaluate the agents out of sample with matched seeds and transaction costs.
4. Report drawdown, turnover, costs, calendar-period results, and uncertainty.
5. Package the experiment as a reproducible repository and technical report.

The expanded work was tracked publicly through issues for the
[ten-seed evaluation](https://github.com/Aarav-Nagar/QINN-FinRL-Evaluation/issues/3),
[bond-dimension sensitivity](https://github.com/Aarav-Nagar/QINN-FinRL-Evaluation/issues/4),
and [temporal robustness](https://github.com/Aarav-Nagar/QINN-FinRL-Evaluation/issues/5).
The completed evidence is now indexed under `results/`.

The expanded SecureFinAI short-paper work is governed by the
[deliverables tracker](docs/PAPER_DELIVERABLES.md) and the prespecified
[experiment protocol](docs/EXPERIMENT_PROTOCOL.md). Daily milestones,
verification, and any protocol deviations are retained in the
[research log](docs/DAILY_LOG.md). Post-pilot choices are preserved in the
[experiment decision log](docs/DECISIONS.md).
The exact non-overlapping shifted-window design is frozen in the
[temporal robustness protocol](docs/ROBUSTNESS_PROTOCOL.md).
The equal-length two-year extension is separately frozen in the
[equal-window protocol](docs/EQUAL_WINDOW_PROTOCOL.md).
The later same-policy cumulative-prefix diagnostic is declared in the
[nested-horizon protocol](docs/NESTED_HORIZON_PROTOCOL.md) and remains
explicitly post hoc.

The first expanded-study result is the matched
[PPO training-budget pilot](results/pilots/2026-07-27/), which selected 20,000
steps for the final ten-seed evaluation while retaining the absence of
established convergence as a limitation.

The boundary-corrected fixed-split evaluation is complete. Across ten matched
PPO seeds, mean Sharpe was 0.821 for ANN and 0.784 for the selected dimension-2
MPS. The mean paired MPS-minus-ANN Sharpe difference was -0.037, with a
paired-seed bootstrap 95% interval of [-0.113, 0.045]. Full per-seed evidence
and provenance are under [`results/final/`](results/final/).

The prespecified shifted 2017--2018 evaluation is also complete. MPS mean
Sharpe was 0.714 versus 0.627 for ANN and was higher in 9/10 seeds, while the
annualized-return block-bootstrap interval included zero. Its evidence is under
[`results/robustness/shifted/`](results/robustness/shifted/). The opposite
window signs support evaluation-window sensitivity, not stable MPS superiority.

The exploratory equal-length panel is also complete. Mean paired MPS-minus-ANN
Sharpe was +0.086, +0.092, and +0.140 in the 2017--2018, 2019--2020, and
2021--2022 two-year evaluations. MPS was higher in 9/10, 7/10, and 6/10
matched seeds, respectively. The two new seed-bootstrap intervals include
zero, and the five-year primary estimate remains negative. This is useful
evidence of horizon and training-window sensitivity, not a stable advantage.
Complete tables, per-seed differences, manifests, and interpretation limits
are under
[`results/robustness/equal_windows/`](results/robustness/equal_windows/).

The post-hoc nested-horizon diagnostic re-scores the same frozen primary
policies over every cumulative one- through five-year prefix. Mean paired
MPS-minus-ANN Sharpe is +0.005, -0.063, -0.082, -0.028, and -0.037; MPS is
higher in 4/10, 2/10, 3/10, 3/10, and 3/10 seeds. Every interval includes
zero. The nearly tied one-year mean and negative two- through five-year means
show that evaluation length alone does not reproduce the positive equal-window
panel when the trained policies and 2019 start are fixed. This is dependent,
post-hoc evidence, not a causal horizon effect. The complete tables and
manifest are under
[`results/robustness/nested_horizons/`](results/robustness/nested_horizons/).

A separate post-hoc market-state audit uses the three non-overlapping
equal-length windows and the saved equal-weight benchmark, without retraining.
MPS-minus-ANN annualized mean-return differences were negative on benchmark
down days in all three windows (-6.63, -0.56, and -2.15 percentage points) and
positive on nonnegative days (+8.56, +4.99, and +9.94 points). This suggests
the exploratory equal-window advantage was concentrated in upside capture,
not downside protection. Every direction-state seed-bootstrap interval
included zero, downside-risk differences were inconsistent, and the audit is
post hoc; it is therefore a failure-analysis clue rather than a new headline
performance claim. The full 27-cell state panel, six calendar years, exact
direction decomposition, and provenance manifest are under
[`results/robustness/market_states/`](results/robustness/market_states/).

## Review guide

For a concise review of the current short-paper study:

1. Read the IEEE-style source in [`paper/main.tex`](paper/main.tex).
2. Review the corrected primary and shifted evidence under
   [`results/final/`](results/final/) and
   [`results/robustness/shifted/`](results/robustness/shifted/), then inspect
   the [`equal-window panel`](results/robustness/equal_windows/) and
   [`nested-horizon diagnostic`](results/robustness/nested_horizons/).
3. Follow every manuscript claim through
   [`paper/CLAIM_TRACEABILITY.md`](paper/CLAIM_TRACEABILITY.md).
4. Use [`REPRODUCIBILITY.md`](REPRODUCIBILITY.md) for exact commands,
   environments, boundaries, and artifact generation.
5. Inspect [`run_experiment.py`](run_experiment.py), the orchestration scripts,
   and the test suite for implementation and integrity checks.

The earlier [reviewer release](https://github.com/Aarav-Nagar/QINN-FinRL-Evaluation/releases/tag/v1.0-atl-evaluation)
and long-form PDF/Word report remain historical reference snapshots; they do
not contain the corrected SecureFinAI ten-seed and shifted-window evidence.

## Research question

When the data, prediction target, PPO configuration, transaction costs, and
random seeds are held constant, does a validation-selected MPS signal improve
out-of-sample FinRL trading performance or temporal robustness relative to an
ANN signal and the standard FinRL state?

## Current SecureFinAI protocol

The frozen short-paper study uses 15 Nasdaq stocks and compares Base FinRL,
an ANN signal, and a classical MPS signal. All three PPO conditions use a
$1,000,000 initial portfolio, a 0.10% transaction cost on each executed buy
or sell, 20,000 training steps, and matched seeds 0--9. The primary PPO fit
period is 2013--2018 and its untouched evaluation period is 2019--2023. The
prespecified shifted analysis fits PPO through 2016 and evaluates on
2017--2018. The exploratory equal-length extension uses three non-overlapping
two-year evaluations, each preceded by the same four-year PPO training span
and three-year encoder-fit plus one-year validation split.

Both encoders use the same 13 inputs, next-day return target, fit/validation
boundaries, and frozen-signal integration. The ANN has 369 trainable
parameters. The selected bond-dimension-2 MPS has 97 parameters; it was chosen
before the final evaluation because its validation MSE was within 1% of the
best tested MPS and it was the smallest eligible model. Bond dimension 4 has
369 parameters and is the exactly parameter-matched sensitivity condition.
Capacity is therefore recorded and tested, but the selected final ANN/MPS pair
is not parameter matched.

Exact tickers, feature lists, temporal boundaries, source-data checksums,
state dimensions, dependencies, and runtime metadata are recorded in
`results/final/run_manifest.json` and
`results/robustness/shifted/run_manifest.json`; the two new complete manifests
and cross-window provenance are under `results/robustness/equal_windows/`.
The compact capacity-pilot inputs are retained under
`results/pilots/2026-07-28/raw/`. The original evidence is frozen by
`results/SCIENTIFIC_RESULTS_FREEZE.json`; the exploratory extension is
separately frozen by
`results/robustness/equal_windows/equal_window_manifest.json`.

## Historical reference protocol

Three PPO conditions were compared:

| Condition | State supplied to PPO | State dimension |
|---|---|---:|
| Base FinRL | Cash, prices, holdings, and 10 indicators per stock | 181 |
| ANN signal | Base state plus one frozen ANN prediction per stock | 196 |
| MPS signal | Base state plus one frozen MPS prediction per stock | 196 |

For the two signal agents, the encoder generated one standardized next-day
return prediction for each of 15 stocks. The resulting 15-value vector was
appended as the final indicator block in the PPO state. The encoder remained
frozen during PPO training.

The ANN and MPS models:

- used the same 13 market inputs and next-day return target;
- contained exactly 369 trainable parameters each;
- were fit on 2013-2017 data and validated on 2018; and
- were evaluated using PPO policies trained on 2013-2018 and tested on the
  unseen 2019-2023 period.

Each PPO condition used seeds 0, 1, and 2, a 5,000-step training budget, a
$1,000,000 initial portfolio, and a 0.10% transaction cost on every executed
buy and sell.

## Historical reference results

The MPS model achieved slightly lower prediction error and higher directional
accuracy, but this did not produce better trading performance.

| Condition | Mean Sharpe | Total return | Maximum drawdown | Annualized turnover |
|---|---:|---:|---:|---:|
| Base FinRL | 0.559 | 73.24% | -40.46% | 26.43% |
| ANN signal | 0.735 | 104.66% | -27.55% | 27.32% |
| MPS signal | 0.694 | 94.27% | -26.79% | 24.14% |
| Equal-weight benchmark | 1.115 | 218.25% | -28.54% | 20.06% |

MPS trailed ANN in all three paired PPO seeds. The annualized mean-return
difference, MPS minus ANN, was -0.92 percentage points. A moving
20-trading-day block bootstrap produced a 95% interval from -4.63 to +2.63
percentage points, which includes zero.

The supported conclusion is limited: under this configuration and historical
split, the MPS signal did not improve trading performance relative to the ANN
signal. This is not a general conclusion about tensor-network methods.

## Reproduce the historical reference run

Use Python 3.12 and install the exact artifact-verification environment:

```powershell
python -m pip install -r requirements-lock.txt
python run_experiment.py `
  --data-dir .cache\data `
  --finrl-dir .cache\FinRL `
  --output-dir results `
  --timesteps 5000 `
  --seeds 0 1 2 `
  --bond-dimension 4 `
  --encoder-device auto
python -m pytest -q test_experiment.py test_smoke_matrix.py
```

The pipeline downloads and checksum-verifies the processed Nasdaq data, checks
out the recorded FinRL commit, trains the ANN and MPS encoders, runs the PPO
conditions, and regenerates the metrics and figures.

Additional reproduction details are documented in
[`REPRODUCIBILITY.md`](REPRODUCIBILITY.md).

## Repository structure

```text
.
|-- README.md
|-- REPRODUCIBILITY.md
|-- run_experiment.py
|-- test_experiment.py
|-- requirements.txt
|-- requirements-lock.txt
|-- docs/
|   |-- Aarav_Nagar_ANN_MPS_FinRL_Technical_Report.pdf
|   |-- Aarav_Nagar_ANN_MPS_FinRL_Technical_Report.docx
|   |-- technical_report.md
|   `-- source_notes.md
`-- results/
    |-- README.md
    |-- run_manifest.json
    |-- signal_metrics.csv
    |-- ppo_backtest_metrics.csv
    |-- annual_period_metrics.csv
    |-- ann_vs_mps_block_bootstrap.csv
    `-- figures/
```

## Historical reference limitations

- The MPS is a classical tensor-network simulation; no quantum hardware was
  used.
- The experiment uses one historical split and a 15-stock Nasdaq subset.
- Three PPO seeds reveal seed sensitivity but do not support broad statistical
  generalization.
- The 5,000-step PPO budget may leave policies undertrained.
- The cost model includes a fixed transaction fee but not spread, slippage,
  market impact, taxes, liquidity limits, or borrow costs.
- Neither signal agent beat the equal-weight benchmark over the full test
  period.

This repository is for research and education and is not financial advice.
