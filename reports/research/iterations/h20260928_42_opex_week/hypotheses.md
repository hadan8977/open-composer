# Hypotheses: h20260928_42_opex_week

Twenty candidates (8 primary + 12 internal placebo controls), sharing the
same D-frequency calendar-anchored construction and the same falsification
design: compute each candidate under the frozen screen_lane cost/fill
contract, check K1/K2/strong_keep/watch_recent against S3's frozen
reference numbers, then apply the placebo internal-falsification rule to
any primary candidate that would otherwise be kept. No backtest is run
under this dossier; the screening lane consumes candidate-manifest.json and
reports results back into this iteration.

Preregistered judgment (frozen before any result is seen, matching the
queue task's own instructions):
- Primary candidates keep on **K1** (date-neutral Sharpe >= 80% of S3's in
  both anchor >=1.19 and stress >=0.65, positive 20bp CAGR both windows) OR
  **K2** (63-session inverse-vol blend with S3 beats a vol-matched
  k*S3+(1-k)*SHY control by >=0.05 Sharpe both windows).
- **strong_keep**: K2 edge >=0.10 both windows, or K1 Sharpe >= S3's own
  (1.49 anchor / 0.81 stress) both windows.
- **watch_recent**: anchor-window Sharpe >=1.19 but stress does not clear
  its bar -- forward-tracked only, not a keep.
- **Placebo internal falsification**: if a primary candidate would
  otherwise be kept/strong/watch_recent, but ANY of its same-ticker
  placebo (W1/W2/W4) has anchor Sharpe >= that primary's own WEEK-variant
  anchor Sharpe, it is demoted to "not kept (placebo replication)" -- the
  3rd Friday is not shown to be special relative to an arbitrary week.
- DSR is reported for the full 20-candidate family (n_trials=20),
  conservative, per the queue task's own instruction.
- Cost/fill note (not a rule change): this project's frozen contract is
  close-signal -> next-session-open fill, one session later than
  Quantpedia's own Friday-close-to-Friday-close holding period. This is a
  contract constraint applied identically to every screen_lane batch, not
  loosened or tightened to help this candidate family.

## H1 -- At least one OPEX_*_WEEK or OPEX_*_WEEKMON primary candidate clears K1 or K2 and survives placebo falsification

- Hypothesis: at least one of the 8 primary candidates (4 tickers x 2 exit
  variants) has a date-neutral Sharpe within 80% of S3's in both the
  anchor and stress windows (K1), or blends with S3 to beat a vol-matched
  control by 0.05 Sharpe in both windows (K2), because two independent,
  mechanism-grounded academic sources (Stivers & Sun 2013 for the
  expiration week itself; Garcia-Ares & Muravyev 2025, sample through
  2021, for the following-Monday rollover effect) support a real,
  recently-active price-pressure mechanism, and the WEEKMON variant is
  designed specifically to capture the more recent paper's stronger
  Monday-rollover finding that the WEEK-only variant would miss.
- Failure mode: this project's precedent (h20260928_05_batch2.py's
  TOM_SPY and FOMC_DRIFT_SPY, the closest prior analogs -- other
  calendar-anchored D-frequency long/cash switches on SPY under the
  identical cost/fill contract) both failed K1 badly (anchor Sharpe -0.69
  and -0.84 respectively); Quantpedia's own historical Sharpe (0.61,
  1988-2010) is itself below S3's reference bar even before considering
  cost-contract drag, sample-period decay, or the one-session-later fill
  timing this project's frozen contract imposes. Recent-decay
  counter-evidence (quantifiedstrategies.com, fetch-blocked/summary-only)
  is directionally consistent with this failure mode, though not
  independently re-verified.
- Measurement: date-neutral Sharpe (single D-frequency version, no offset
  sweep) in the stress window 2016-05-02..2023-09-15 and the anchor window
  2024-01-08..2026-09-17, at 10bp cost; CAGR at 20bp cost; K2's paired
  vol-matched control per candidate; DSR with n_trials=20 (full family).
- Stop/Pivot criterion: if none of the 8 primary candidates clears K1, K2,
  or watch_recent, or every apparent pass is demoted by the placebo
  falsification rule, dir:option_expiration_week_calendar_effect is
  refuted for this scope; the next round should not re-tune this same
  calendar rule on this same universe without a new, distinct signal
  (e.g. an options-flow or dealer-gamma-positioning feature this repo's
  data does not yet support).

## H2 -- The 3rd-Friday (expiration) week is distinguishable from an arbitrary Friday-anchored week (placebo falsification)

- Hypothesis: if the option-expiration-week mechanism (delta-hedge
  rebalancing, rollover order imbalance) is real and priced, a primary
  candidate's anchor-window Sharpe should exceed its own same-ticker
  1st/2nd/4th-Friday-week placebo's anchor Sharpe, because those placebo
  weeks have no comparable options-driven order-flow event.
- Failure mode: if all four Friday-anchored weeks (1st/2nd/3rd/4th) show
  similar Sharpe on the same ticker, the apparent "expiration week effect"
  would be indistinguishable from generic day-of-month/week-of-month
  seasonality or noise, not a genuine options-driven mechanism -- exactly
  the failure mode the placebo family is designed to catch, per the queue
  task's explicit instruction to add this control "beyond G3."
- Measurement: for each primary candidate that would otherwise clear a
  keep tier, compare its own WEEK-variant anchor Sharpe against its three
  same-ticker placebo candidates' anchor Sharpe (all read directly from
  leaderboard.json).
- Stop/Pivot criterion: any primary candidate beaten by a same-ticker
  placebo on anchor Sharpe is demoted to "not kept (placebo replication)"
  regardless of its own K1/K2 numbers; this is not a soft judgment call,
  it is applied mechanically per candidate.
