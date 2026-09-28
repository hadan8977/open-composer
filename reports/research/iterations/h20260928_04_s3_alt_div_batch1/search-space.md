# Search Space: h20260928_04_s3_alt_div_batch1

One path, `s3_alt_div_batch1_screen`, with 19 fixed candidates and no
parameter search: every candidate implements its source's published rule
with the source's published parameters, so there is nothing to tune and
nothing to optimize. The 19 candidates split into three families -- F1 (5
managed-futures ETFs held outright: DBMF, KMLM, CTA, WTMF, FMF), F2 (9
Keller/Antonacci/Faber tactical-allocation rules computed over public ETF
universes: VAA-G4, DAA-G12, PAA-CPR, HAA, GPM, GEM, GTAA-5, ADM,
BAA-Balanced) and F3 (5 other alt-diversifier ETFs held outright: RPAR, UPAR,
NTSX, QAI, TRTY).

Cost assumptions: 10bp per side primary, 20bp per side stress, signal at the
session close, fill at the next session's open -- identical to the frozen
S1/S2/S3 convention (`cost-contract.json`). Benchmark family: SPY, SHY, BIL
buy-and-hold, plus S3 itself as the fixed reference for K1 and the K2 blend
partner.

This round uses the owner's 2026-09-28 relaxed keep rule, not a Wave 9.2
go/no-go band: a candidate is kept if K1 (its date-neutral Sharpe, median
over rebalance offsets, is at least 80% of S3's in both the anchor and
stress windows, with positive CAGR at 20bp) or K2 (a 63-session
trailing-inverse-vol monthly blend with S3 beats a vol-matched
k*S3+(1-k)*SHY control by at least 0.05 Sharpe in both windows). Total
candidate budget is 19, under the 24-candidate lightweight single-mechanism
exemption threshold, so no campaign contract is bound for this iteration.
