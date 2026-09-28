# Hypotheses: h20260928_06_registry_stock_batch3

## Hypothesis

Ten stock-level registry directions, each already given a disclosed long-only
rule and (for the _pwb rows) a paperswithbacktest full-period backtest, clear
the owner's 2026-09-28 keep rule (K1: Sharpe against S3, or K2: diversifier
edge against a vol-matched S3+SHY control) when run through the project's own
frozen signal_card/screen_lane engine at 10bp and 20bp per side, in the
select/anchor/stress/holdout(2026, contaminated) windows.

## Failure mode

Every candidate fails K1 and K2: either the source's high full-period (1990-2026)
CAGR/Sharpe does not survive the project's own recent select/anchor/stress
windows and 10/20bp cost convention, or -- for the diversifier test -- the
candidate's returns are too correlated with S3's own semis-ETF-rotation
mechanism (or too weak on their own) to add measurable Sharpe when blended at
63-day inverse volatility. A secondary failure mode specific to this batch: the
5 forwarded rows and the 3 needs_modal rows never get a number at all, only a
recorded blocker, which is an acceptable (not a failed) outcome for those rows
under this round's brief.

## Measurement

Per candidate, per window: CAGR, Sharpe (RF-excess, BIL), max drawdown, vol, at
10bp and 20bp (base.metrics convention). K1 checked against the owner's own
numbers (Sharpe >=1.19 anchor / >=0.65 stress at 10bp, CAGR>0 at 20bp in both).
K2 checked via `screen_lane.diversifier_edge_for_offset` against a >=0.05
Sharpe-edge bar in both anchor and stress. Correlation with S3 (stress, anchor,
2022) via `screen_lane.correlation_with_s3`. Deflated Sharpe probability on the
judged anchor excess return, `trial_count=10`, `hac_lag=21`.

## Stop/Pivot criterion

Stop (do not carry any candidate into `reports/research/screens/kept.jsonl`) if
none of the ten clears K1 or K2 -- record the batch as a clean negative result,
same as the sleeve-combination and rebalance-tranching rounds before it. Pivot
to the Modal cloud lane for the three needs_modal rows once that lane is
available, rather than re-deriving a same-day-close-only proxy locally that
would test a different (weaker) mechanism than each row's own disclosed rule.
