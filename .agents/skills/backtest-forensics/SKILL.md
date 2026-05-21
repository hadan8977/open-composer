---
name: backtest-forensics
description: >
  Forensic review of backtest methodology: lookahead, future-leak, overfitting,
  multiple-testing risk, short sample, low trade count, and sample data caveats.
  Required for all parameter-optimized strategies and before promotion.
  Use when risk domain parameter_search is active, or user asks about
  overfitting, PBO, DSR, walk-forward, or backtest validity.
---

## Inputs

- StrategySpec (parameters section, execution, capabilities)
- Backtest report(s) from `oc backtest` or promotion report
- Trial ledger (if optimization was run)

## Mandatory output

- `reports/harness/forensics/{strategy}-backtest-forensics.json`
- `reports/harness/forensics/{strategy}-backtest-forensics.md`

## Checklist

### Lookahead bias
- [ ] Signal uses only data available at or before the bar open.
- [ ] Features derived from closing prices are applied to the next bar only.
- [ ] LLM/news/macro inputs use `visible_at` timestamps, not `published_at`.

### Future leak
- [ ] No in-sample parameters (means, stds, betas) computed over the full window and applied to earlier periods.
- [ ] Rolling lookbacks are correctly shifted by 1 bar.
- [ ] Train/test split is chronological, not random.

### Overfit / multiple testing
- [ ] Document `N` = total parameter sets trialed (from trial ledger or estimate).
- [ ] If N > 20, flag multiple-testing risk. PBO proxy: 1 − (success_rate_of_N_alternatives).
- [ ] DSR proxy: expected max Sharpe = μ + σ·√(2·ln N). Flag if selected Sharpe > 2× expected max.
- [ ] Walk-forward or OOS degradation > 50% of in-sample Sharpe = overfit warning.

### Sample adequacy
- [ ] Trading days >= 252 (1 year). If < 252, write `short_sample_caveat`.
- [ ] Trade count >= 30. If < 30, write `short_sample_caveat` and flag `low_trade_count`.
- [ ] Check whether the sample period contains regime diversity (bull, bear, sideways).

### Sample / fixture data
- [ ] If any capability has `strict_behavior: workflow_only`, flag `sample_data_caveat`.
- [ ] Sample data caveats must appear in every promotion report referencing these results.

### Capacity
- [ ] Estimate order size as % of average daily volume (ADV) at entry.
- [ ] If order > 1% ADV, flag capacity risk.
- [ ] For leveraged ETFs, note concentrated open-auction participation risk.

## Output schema (json)

```json
{
  "strategy_name": "...",
  "lookahead_check": "pass | warning | fail",
  "future_leak_check": "pass | warning | fail",
  "overfit_risk": "low | medium | high",
  "multiple_testing_count": 0,
  "pbo_proxy": null,
  "dsr_proxy": null,
  "sample_data_caveats": [],
  "trade_count": 0,
  "trading_days": 0,
  "capacity_assessment": "...",
  "short_sample": false,
  "conclusion": "pass | warning | blocked",
  "notes": "..."
}
```

## Blocking rules

- `conclusion: blocked` if lookahead_check or future_leak_check = fail.
- `conclusion: warning` if overfit_risk = high or short_sample = true.
- Optimized strategies without trial_ledger: `conclusion: blocked`.

## References

- `harness/artifact_contracts.yaml` — backtest_forensics, trial_ledger schemas
- `harness/risk_domains.yaml` — parameter_search blocking rules
- Bailey & López de Prado: Probability of Backtest Overfitting (SSRN 2326253)
- Deflated Sharpe Ratio (SSRN 2460551)
- Almgren-Chriss optimal execution (capacity modeling)
