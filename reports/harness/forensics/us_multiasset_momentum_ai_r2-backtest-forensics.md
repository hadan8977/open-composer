# Backtest Forensics: us_multiasset_momentum_ai_r2

- Lookahead: `pass`
- Future leak: `pass`
- Overfit risk: `high`
- Candidates: `24` model/ensemble trials over `72` available factors
- Conclusion: `warning`

All inputs are shifted by one session. Each fold uses a 21-bar label purge and a further 21-bar embargo. Feature selection is recomputed from the training frame only.

The current-universe history is survivorship-biased before July 14, 2026, and the historical challenge was already exposed in the previous ML round. AI formulas improved matched models in development, but the deterministic 12-1 route remained superior in the exposed challenge. The AI sleeves are therefore forward diagnostic challengers rather than promoted Alpha.
