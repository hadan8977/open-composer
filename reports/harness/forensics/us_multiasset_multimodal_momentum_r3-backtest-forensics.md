# Backtest Forensics: us_multiasset_multimodal_momentum_r3

- Verdict: `diagnostic_only`
- Candidate budget: `24 registered / 14 completed / 10 dependency-skipped`
- Time contract: all new day/night factors use the prior session; labels use 21 bars with 21-bar purge and embargo across four chronological folds.
- Challenge discipline: the previously exposed six-date historical challenge was not reopened.
- Multiple-testing risk: high; no search expansion is allowed.
- Data limitations: historical current-universe survivorship bias, no real historical text packets, retrospective LLM transforms are not pristine OOS, and costs remain estimates.

The day/night ranker improved aggregate development return from `34.09%` to `35.62%` but won only one fold. The best regime diagnostic reached `48.37%` but won only two folds. No candidate met the preregistered three-of-four stability gate, so no Alpha, LLM-contribution or paper-readiness claim is supported.
