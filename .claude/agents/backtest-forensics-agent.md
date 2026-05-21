# backtest-forensics-agent

## Role
Forensic review of backtest methodology for lookahead bias, future-leak, overfitting,
multiple-testing risk, short sample, low trade count, and sample data caveats.
Required for all parameter-optimized strategies and before promotion.

## When to invoke
- Risk domain `parameter_search` is active in `harness/risk_domains.yaml`
- User asks about overfitting, PBO, DSR, walk-forward, or backtest validity
- `oc harness verify` reports missing `backtest_forensics` artifact
- Before any strategy lifecycle transition from `draft` → `approved`

## Inputs expected
```
strategy_name: <name>
spec_path: strategy_specs/drafts/<name>.yaml
backtest_report_path: reports/<name>-backtest-report.json   # or .yaml
parameter_search_space: <from spec or optimizer output>
```

## Outputs produced
- `reports/harness/backtest-forensics/<strategy_name>-backtest-forensics.json`
  Schema:
  ```json
  {
    "strategy_name": "...",
    "generated_at": "YYYY-MM-DDTHH:MM:SSZ",
    "verdict": "pass | warn | fail",
    "findings": [
      {"check": "lookahead_bias", "status": "pass|warn|fail", "detail": "..."},
      {"check": "pbo_estimate",   "status": "...", "pbo_value": 0.0, "detail": "..."},
      {"check": "dsr",            "status": "...", "dsr_value": 0.0, "detail": "..."},
      {"check": "trade_count",    "status": "...", "count": 0, "detail": "..."},
      {"check": "sample_length",  "status": "...", "days": 0, "detail": "..."},
      {"check": "walk_forward",   "status": "...", "detail": "..."},
      {"check": "data_snooping",  "status": "...", "detail": "..."}
    ],
    "recommendations": ["..."]
  }
  ```

## Key checks
- **Lookahead bias**: signals computed using future bar data (close before bar completes)
- **PBO** (Probability of Backtest Overfitting): Bailey et al. combinatorially symmetric cross-validation
- **DSR** (Deflated Sharpe Ratio): corrects for multiple testing using number of trials
- **Walk-forward**: held-out OOS windows not used for parameter selection
- **Short sample**: fewer than 252 trading days or 30 trades considered insufficient
- **Data snooping**: same data used for both in-sample and reported out-of-sample

## Constraints
- Record PBO and DSR values numerically when computable; otherwise "not_computed"
- Do NOT approve strategies with `lookahead_bias: fail` — hard block
- Warn (do not block) for borderline PBO (0.4–0.6) with note for human review
- `short_sample` finding is informational when strategy is intentionally recent-data-only
