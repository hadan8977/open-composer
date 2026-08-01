# Research Memory: us_multiscale_low_turnover_r6
- Final status: workflow_pass=false; research_pass=false; paper_ready_pass=false; no selected candidate.
- Data: real Alpaca IEX adjusted daily and 30-minute snapshots through 2026-07-17; no fallback, forward fill, zero-return substitution, event packets, SIP parity, or formal-forward observations.
- Invalid evidence: D01-D04 violate the 0.40 symbol cap. D02-D06 and N01 use non-self-financing constant-target accounting; their returns, exposure, turnover, and costs are audit-only. The equal-weight benchmark is invalid for the same reason.
- D06: 29 rebalance dates versus 30 D05 shared-window fill dates, with one exact overlap; it is not an intraday timing ablation and has no matched D05 benchmark.
- Controls: the future-feature rejection is a direct stub; one shuffled-score path is not a placebo distribution; PBO/DSR are non-authoritative proxies and the 0.95 DSR threshold was not preregistered.
- R7 constraint: never alter R6 parameters or reinterpret raw R6 metrics. Implement self-financing holdings, hard 0.40 caps with residual cash, exact parent schedule reuse, a D05 same-window comparator, implementation hashes, end-to-end future-feature rejection, and frozen DSR/PBO thresholds before running.
- Strategy direction: bounded core/satellite family combining a capped SPY trend anchor and capped residual/persistent sector momentum. Event/LLM factors remain forward-only and dependency-skipped until real PIT packets exist.
- Paper: prohibited until a later round passes historical gates, formal forward evidence, SIP/official-price parity, matched TCA, promotion, and paper-auto safety review.
