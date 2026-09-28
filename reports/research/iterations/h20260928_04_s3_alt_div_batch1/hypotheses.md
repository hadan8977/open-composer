# Hypotheses: h20260928_04_s3_alt_div_batch1

Nineteen candidates, one hypothesis each, all sharing the same falsification
design: compute the candidate under its own published rule, then check K1 and
K2 against S3's frozen reference numbers (date-neutral anchor Sharpe 1.49,
stress Sharpe 0.81). No backtest is run under this dossier; the screening lane
built separately consumes candidate-manifest.json and reports results back
into this iteration.

## H1 -- F1 managed-futures ETFs (DBMF, KMLM, CTA, WTMF, FMF) clear K1 or K2

- Hypothesis: at least one managed-futures ETF's own live NAV return series has
  a date-neutral Sharpe within 80% of S3's in both the anchor and stress
  windows (K1), or blends with S3 at 63-session inverse-vol to beat a
  vol-matched k*S3+(1-k)*SHY control by 0.05 Sharpe in both windows (K2),
  because CTA/trend-following strategies are historically documented to have
  low-to-negative correlation with equities in equity bear markets.
- Failure mode: managed-futures live records are dominated by a small number
  of large trend moves (2008, 2020, 2022); a short live record (CTA since
  2022, KMLM since 2020) may not contain enough of those moves to produce a
  Sharpe comparable to S3's, and the family could simply have lower absolute
  Sharpe than a levered semiconductor-momentum sleeve regardless of
  correlation.
- Measurement: date-neutral Sharpe (median over monthly offsets 0-20 trading
  days) in the stress window 2016-05-02..2023-09-15 and the anchor window
  2024-01-08..2026-09-17, at 10bp cost; CAGR at 20bp cost; K2's paired
  vol-matched control per candidate.
- Stop/Pivot criterion: if none of the 5 clears K1 or K2, the family is
  refuted for this batch and the next round should look at a manager with a
  longer, more diversified live trend record (e.g. WTMF's DTI index, which
  already has the longest history here) before trying anything else in this
  family.

## H2 -- F2 Keller/Antonacci/Faber tactical-allocation rules (9 candidates) clear K1 or K2

- Hypothesis: at least one of VAA-G4, DAA-G12, PAA-CPR, HAA, GPM, GEM, GTAA-5,
  ADM or BAA-Balanced clears K1 or K2, because these rules hold global bonds,
  gold, commodities or defensive equities during equity-momentum bear regimes
  that would also be bad for a levered semiconductor sleeve, which is exactly
  the mechanism K2 is designed to detect even if a candidate's standalone
  Sharpe (K1) is too low on its own.
- Failure mode: these are broad, diversified, historically low-volatility
  tactical-allocation rules; their standalone Sharpe over the stress and
  anchor windows may simply be too low relative to S3's high-Sharpe levered
  momentum profile to clear K1's 80% bar, and if their correlation with S3 in
  bear regimes is not actually low (e.g. because canary/defensive assets like
  TLT or LQD have their own 2022 drawdown coincident with equities), K2 also
  fails. BAA-Balanced and ADM already showed low standalone Sharpe (0.49 and
  0.90 respectively) in the prior giants-sweep run under the old criterion,
  so their K1 pass is a priori unlikely; they are retained only for a fresh
  K2 test.
- Measurement: same date-neutral Sharpe/CAGR protocol as H1, plus each
  candidate's own trailing-63-session inverse-vol blend with S3 for K2.
- Stop/Pivot criterion: if none of the 9 clears K1 or K2, this family is
  refuted for this batch; the next round should look at published rules with
  documented negative correlation specifically during 2022 (bonds sold off
  with equities that year, which is the main risk to this whole family).

## H3 -- F3 other alt-diversifier ETFs (RPAR, UPAR, NTSX, QAI, TRTY) clear K1 or K2

- Hypothesis: at least one of these five multi-asset or hedge-fund-replication
  ETFs clears K1 or K2, because risk-parity and hedge-fund-beta products are
  explicitly designed for lower correlation to concentrated equity bets, and
  QAI's long (2009-) live record in particular spans multiple full market
  cycles including 2020 and 2022.
- Failure mode: RPAR, UPAR and TRTY had a historically bad 2022 (rising rates
  hurt both their bond and equity legs simultaneously), which is exactly the
  regime a semiconductor-momentum sleeve also does badly in, so K2's
  diversification benefit could be small or negative for this family even if
  QAI (lower beta, more hedge-fund-like) does better.
- Measurement: same date-neutral Sharpe/CAGR protocol as H1/H2.
- Stop/Pivot criterion: if none of the 5 clears K1 or K2, this family is
  refuted for this batch; NTSX and UPAR's embedded equity leverage should be
  the first suspects investigated in any follow-up, since they raise both the
  numerator and the correlation to S3's own equity-momentum exposure.
