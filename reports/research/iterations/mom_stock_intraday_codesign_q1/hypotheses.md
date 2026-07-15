# Hypotheses: mom_stock_intraday_codesign_q1

## Q-H1

- Hypothesis: Industry-relative, volume-conditioned, or turnover-buffered long-only momentum can improve net stability over frozen 12-1 without relying on more leverage.
- Failure mode: The apparent lift is a current-universe artifact, disappears at cost stress, or is concentrated in one date fold.
- Measurement: Grouped chronological folds, full benchmark family, net return, drawdown, turnover, concentration, and cross-feed/data caveats.
- Stop/Pivot criterion: Stop a standalone method unless it wins at least three of four development folds and does not fail the recent fold or two-times cost stress.

## Q-H2

- Hypothesis: A low-capacity ML-native system that predicts cross-sectional relevance and downside risk can improve the fixed cost-aware portfolio map over both 12-1 and a matched linear model.
- Failure mode: More model capacity wins only on prediction loss, only before costs, or by producing unstable extreme scores.
- Measurement: RankIC, Top-K net return, downside-event rate, calibration or pinball loss, turnover regret, and fold wins on identical features and dates.
- Stop/Pivot criterion: Stop unless the full model beats both deterministic and linear baselines on at least three folds with no placebo-equivalent lift.

## Q-H3

- Hypothesis: Intraday stock momentum contains separable time-slot continuation, opening continuation/reversal, and overnight/intraday effects that can support an independent low-capacity research strategy.
- Failure mode: Results rely on missing-bar fills, IEX volume, one symbol, spread-insensitive execution, or a single market regime.
- Measurement: Session-grid completeness, per-symbol and per-date folds, continuation/reversal matched tests, base/two/four-times costs, and signal delay.
- Stop/Pivot criterion: Keep as diagnostic only unless it survives gap classification, recent folds, cost stress, and later SIP comparison.

## Q-H4

- Hypothesis: Revision-aware SEC/news event packets can add stable information beyond deterministic document-diff and quant-only baselines.
- Failure mode: Historical text was not visible at the decision time, rights are unclear, issuer identity leaks future knowledge, or shuffled/stale text performs similarly.
- Measurement: Text-only, quant-only, combined, missing, delayed, shuffled, stale, and issuer-anonymized ablations with packet provenance.
- Stop/Pivot criterion: Skip rather than impute when real PIT packets are absent; require stable marginal lift before setting `llm_contribution_pass=true`.
