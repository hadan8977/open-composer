---
name: backtest-forensics
description: >
  Review lookahead, leakage, overfitting, multiplicity, sample limits and capacity.
  Required for parameter-optimized strategies and before promotion; use for
  parameter_search, PBO, DSR, walk-forward or backtest-validity questions.
---

# Backtest forensics

For a registered batch, start with its Results packet, frozen spec and trial snapshot. Trace a fitted score to a funded fill, compare recent net dollars and exposure to the matched accounts, and remove the largest favourable episode under the frozen definition. For strategy promotion, read the StrategySpec and its reports. Write both `reports/harness/forensics/{strategy}-backtest-forensics.json` and the matching `.md` explanation, using [artifact contracts](../../../harness/artifact_contracts.yaml) and [parameter-search rules](../../../harness/risk_domains.yaml).

## Evidence checks

- Verify inputs were available at the declared decision clock. Close-derived signals cannot fill earlier at that close; bar-close/next-open designs apply features to the next bar. LLM/news/macro availability follows `visible_at`, not merely `published_at`.
- Verify fold-local transforms, label maturity and embargo. Check the declared recent-window weights and preserve seen and sealed classifications.
- Count all tried parameter sets from the ledger, not just survivors. Distinguish selectable configurations, cost/accounting views, null replications and bootstrap draws; check the preregistered correction across selectable hypotheses and explain any effective independent-trial estimate.
- Compute PBO through actual CSCV selection/ranking on the declared common-calendar candidate return matrix. Record partitions, tie handling and the in-sample winner's complementary-sample rank. `1 - success_rate` is not PBO; insufficient inputs mean `N/A`, not zero. Low PBO does not prove profitability.
- Compute DSR as probabilistic Sharpe against a trial-adjusted expected-maximum benchmark, recording sample length, skewness, kurtosis, frequency and trial-count/dispersion assumptions. Disclose serial dependence. `mu + sigma * sqrt(2 ln N)` alone is not DSR; the former `2 * expected max` rejection rule is retired.
- Flag walk-forward/OOS Sharpe degradation above 50% as an overfit warning. Below 252 trading days or 30 trades, write `short_sample_caveat`; below 30 trades also flag `low_trade_count`. Assess regime coverage without making a short sample a scientific refutation.
- Flag `strict_behavior: workflow_only` as `sample_data_caveat` in every referencing promotion report.
- Estimate order size as a fraction of entry ADV; above 1% flags capacity risk. Leveraged ETFs also need opening-auction concentration analysis.

For stock-level SIP inputs, check forward segmentation and split-like breaks under the [project rules](../../../docs/rules.md). This review preserves frozen thresholds and observed-window status.

## Output

```json
{
  "strategy_name": "...",
  "lookahead_check": "pass | warning | fail",
  "future_leak_check": "pass | warning | fail",
  "overfit_risk": "low | medium | high",
  "multiple_testing_count": 0,
  "pbo_proxy": null,
  "dsr_proxy": null,
  "pbo": null,
  "dsr": null,
  "statistical_methods": {},
  "sample_data_caveats": [],
  "trade_count": 0,
  "trading_days": 0,
  "capacity_assessment": "...",
  "short_sample": false,
  "conclusion": "pass | warning | blocked",
  "notes": "..."
}
```

Leave legacy `*_proxy` fields null. Bind real statistics to their method, input matrix, trial inventory and validation scope. A failed lookahead/leakage check, or optimization without a trial ledger, blocks the conclusion. High overfit risk or a short sample warrants `warning` unless a blocking defect also applies.

Method references: [PBO and CSCV](https://escholarship.org/content/qt4w1110bb/qt4w1110bb.pdf) and [DSR, equations 1-2](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf).
