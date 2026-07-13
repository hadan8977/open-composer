# Decision Record: mom_minute_r4_portfolio

- Path: R0, R1, R2, R3, M1, M2
- Decision: continue all six as isolated broker-free virtual Paper diagnostics; stop any promotion or Alpaca multi-strategy order plan.
- Reason: the bounded portfolio satisfies the requested rule, ML, and expanded-momentum coverage while preventing six TQQQ strategies from overwriting one account position. R1-R3 reuse a visible historical window and M1-M2 failed the validation gate, so research_pass remains false.
- Next iteration suggestion: refresh strict QQQ/TQQQ data and append only fresh completed-session observations. Do not retune from the historical comparison, authorize broker writes, or call stale receipts forward validation.

This dossier was completed after the first portfolio command as a remediation
for a workflow violation. Future research rounds must validate before execution.
