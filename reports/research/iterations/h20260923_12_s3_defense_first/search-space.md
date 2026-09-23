# Search space: h20260923_12_s3_defense_first

One mechanism (the frozen S3 vt40+boost overlay, unchanged) producing a time-varying remainder;
three frozen candidates, written to candidate-manifest.json before any return is computed. The
overlay itself -- 63-session absolute momentum vs SHY, 21-session realized-volatility target (0.40
base, 0.60 dip boost, 1.0 leverage cap), QQQ-oversold dip trigger, monthly rebalance on the last
session, next-open fills -- is inherited unchanged from the live S3 vt40+boost renewal and is not
re-searched. What is searched is only what the resulting remainder (1 minus the risk-sleeve
weight) is held in.

| axis | values |
|---|---|
| candidate id | DF00 (reference, remainder in SHY), DF01, DF02 (fixed set, one path, no ranking) |
| defensive menu | TLT, GLD, DBC, UUP (fixed, all three candidates that use it) |
| momentum score | mean of 1/3/6/12-calendar-month dividend-adjusted return per asset (fixed) |
| rank weights | 40% / 30% / 20% / 10% by rank, highest momentum first (fixed) |
| cash-hurdle instrument | BIL (13-week T-bills); asset momentum < BIL momentum -> slot fails (fixed) |
| failing-slot fallback | n/a (DF00) / SPY (DF01, published) / SHY (DF02, this iteration's own variant) |
| defense-first rebalance | last session of month at close, applied at next open (fixed) |
| S3 momentum lookback | 63 sessions vs SHY (fixed, unchanged from S3) |
| volatility target | 0.40 base / 0.60 dip boost (fixed, unchanged from S3) |
| leverage cap | 1.0, down-only (fixed, unchanged from S3) |
| cost view | 10 bp and 20 bp per side, both reported |

3 candidates, DF00/DF01/DF02, one path (`s3_defense_first_remainder_screen`). No model training,
no mutation, no adaptive expansion, and no selection rule: DF01 and DF02 are scored against the
same fixed adoption rule independently, and neither is picked over the other based on its own
result. The only thing that varies between DF01 and DF02 is the failing-slot fallback asset.

Controls (preregistered, not candidates, not counted in the 3-candidate budget):

- **EW** (1, shared by both DF01 and DF02): static 25/25/25/25 TLT/GLD/DBC/UUP basket, rebalanced
  monthly, no momentum ranking, no cash-hurdle screen, no fallback substitution -- isolates
  diversification into the same four assets from the ranking mechanism. Valid from 2016-05-02 (no
  warmup needed), a known, disclosed head-start over DF01/DF02/RR-k until 2017-02-03.
- **RR-k** (40 per candidate, 80 total): each month, the same cash-hurdle screen, the same 40/30/
  20/10 weights and the same fallback asset as the real candidate, but the rank-to-asset
  assignment is a fresh seeded random permutation (seed = placebo index, advanced monthly) instead
  of a momentum-based rank -- isolates whether the ranking itself carries information. Design
  window only, same warmup as the real candidate.

Fixed simulation budget: 2 new candidate simulations (DF01, DF02) + 1 EW control + 80 RR-k
placebos = 83 simulations. DF00 needs no new simulation -- its numbers are reused from the
existing stress replay (design window) and the authorized 2026-09-23 renewal record (anchor
window).

Adoption rule (all must hold, per candidate, independently): design window (a) Sharpe >= DF00
Sharpe + 0.10, (b) max drawdown no worse than DF00's, (c) Sharpe beats >=36/40 RR-k placebos, (d)
Sharpe > EW's; anchor window at 10 and 20 bp (e) CAGR >=50% and max drawdown >=-35% (gate G1),
do-no-harm only, no holdout claim. Multiple comparisons: 2 candidates, both reported. If neither
passes: "keep SHY".

Diagnostics (not candidates, never ranked, declared as benchmark-family members rather than
manifest rows): DF00 reference, the shared EW control, each candidate's RR-k placebo distribution,
and SPY/SHY buy-and-hold.

Where the exact Defense First rules were pinned from, and where sources differ: the primary SSRN
paper (Carlson 2025, DOI 10.2139/ssrn.5334772) was located this pass but its full text was not
fetchable through the available tooling (only a bibliographic stub rendered). Per this task's own
fallback instruction, the exact rules are pinned from AllocateSmartly's independent, rule-by-rule
replication instead, cross-checked against the author's own LinkedIn summary and the
already-harvested Quantitativo description (registry row dir:defense_first_taa_carlson_concretum).
All three agree on the mechanism shape and the 40/30/20/10 weights and SPY fallback; the one
disclosed disagreement is the commodities ticker -- AllocateSmartly and BestFolio use PDBC, while
the author's own LinkedIn post and Quantitativo both say DBC. This iteration uses DBC, matching
the author's own description and local data availability, per the task's instruction to prefer the
paper's (author-confirmed) version and note the difference.
