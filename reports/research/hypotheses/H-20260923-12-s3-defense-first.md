---
card_id: H-20260923-12
status: executed, refuted (keep SHY), 2026-09-23
lane: preregistered
previous: H-20260923-11
direction_id: dir:s3_defense_first_remainder
iteration: h20260923_12_s3_defense_first
brief: reports/research/briefs/B-7-s3-defense-first-2026-09-23.md
criteria:
  - name: design_sharpe_improvement
    threshold: 0.10
    direction: ">="
  - name: design_max_drawdown_delta_vs_df00
    threshold: 0
    direction: ">="
  - name: design_rr_placebo_beat_count_of_40
    threshold: 36
    direction: ">="
  - name: design_sharpe_vs_ew
    threshold: 0
    direction: ">"
  - name: anchor_cagr
    threshold: 0.50
    direction: ">="
  - name: anchor_max_drawdown
    threshold: -0.35
    direction: ">="
---

# H-20260923-12 S3's remainder in a Defense First rotation vs an equal-weight and random-rank control

- Status: **preregistered, not executed** (round 1) -- hypothesis family: levered_rotation_remainder_holding
  -- layer: what the already-sized, already-unchanged remainder is *held in* (S3's own risk-sleeve
  selection and sizing are not re-tested) -- data tier: **tier 3** (OHLCV-derived momentum on TLT,
  GLD, DBC, UUP, plus BIL as the cash-hurdle instrument)
- Previous link: H-20260923-11 (S3 bear-regime gate: four gates that moved S3's *risk* weight to
  SHY on a trend signal all failed their own exposure-matched and circular-shift controls, refuted
  same day, same book; registry row `dir:s3_bear_regime_guard`). That round was a timing claim on
  the risk sleeve; this round is a composition claim on the remainder the risk sleeve already
  leaves idle, so it uses different controls (EW, RR-k) rather than EM-k/CS-k.
- Iteration dossier: `reports/research/iterations/h20260923_12_s3_defense_first/` (direction-review,
  external-brief, candidate-manifest with 3 candidates, search-space, cost-contract,
  data-feasibility; passed `oc research direction-check` and
  `oc research iteration validate --stage pre-backtest`)
- One-line hypothesis: if the part of S3's book that now sits in SHY is held in a Defense First
  rotation instead, does S3's design-window Sharpe rise and its drawdown fall, beyond what
  momentum-free diversification or random rankings give, without breaking the anchor-window return
  bar?

## Why

S3's own machine (63-session absolute momentum vs SHY over TQQQ/SOXL/UPRO/USD/TECL, top 2,
monthly, 21-session realized-vol target 0.40 with a QQQ-oversold dip boost to 0.60, 1.0 leverage
cap) holds a time-varying remainder in SHY whenever it is not fully invested -- the vol-target
shortfall and any slot the absolute-momentum filter empties. The pre-window stress replay (commit
01df33d) shows mean risk exposure over 2016-2023 is about 0.61, so roughly 39% of the book sits
idle in SHY on average. SHY earns close to the risk-free rate; nothing in S3's own design asks
whether that idle fraction could be doing better without adding equity beta or timing risk.

Thomas Carlson's 2025 SSRN preprint "Defense First: A Multi-Asset Tactical Model for Adaptive
Downside Protection" (DOI 10.2139/ssrn.5334772) is a published, purpose-built answer to almost
exactly this question for a *general* portfolio: rank four liquid defensive assets (TLT, GLD, DBC,
UUP) monthly by a blended multi-timeframe momentum score, weight them 40/30/20/10 by rank, and use
an absolute-momentum-vs-cash screen so a weak asset's tier goes to SPY instead. It was already
read once at the Quantitativo blog level before this task was scoped (registry row
`dir:defense_first_taa_carlson_concretum`: author-reported ~1990s-2025 unleveraged CAGR 10.4%,
Sharpe 0.95, max drawdown -19.4%, correlation to equities 0.27, FF3 alpha ~6.8%/yr). This round
opens the primary source directly, finds it exists as a 2025 SSRN preprint but cannot fetch its
full text through available tooling, and instead cross-checks two more independent parties who
read and replicated it -- AllocateSmartly (exact rule-by-rule restatement, tested from 1971) and
the author's own LinkedIn announcement (confirms the DBC ticker) -- landing on a single,
well-triangulated rule set before spending any local compute.

Negative evidence bounds this round tightly. `dir:s3_bear_regime_guard` (refuted, same book, same
day): a *timing* claim on the risk sleeve (when to de-risk) failed its own exposure-matched and
circular-shift controls -- a different mechanism (this round makes no timing claim; the remainder's
*size* is whatever S3's unchanged machine decides, only its *composition* is being tested).
`H-20260918-06` (refuted): mechanical, menu-free cross-sectional relative-strength *selection*
over the whole ETF/fund universe underperformed SPMO buy-and-hold in all 8 preregistered families
-- also a different mechanism (DF01/DF02 select among exactly four named defensive assets, gated
by an absolute-momentum-vs-cash screen, not a broad relative-strength sweep).
`dir:giants_sweep_published_etf_rules` (refuted): 0/24 published rules cleared the G1-G5
standalone-strategy bar; Defense First was not part of that census (checked: no "Defense First" or
"Carlson" hit in `reports/research/intel/I-20260922-03-giants-census.md`), and this round does not
apply the G1-G5 bar in any case -- it applies its own remainder-specific adoption rule.
`dir:recent_window_etf_menu_rotation` (passed, related family): small-menu winner-take-all
rotation can win on raw CAGR while losing to its own equal-weight benchmark on Sharpe/drawdown --
the direct reason EW is a required control here, not an optional one.

## Design

Machine (frozen, not searched, copied unchanged from the live S3 vt40+boost renewal): menu (TQQQ,
SOXL, UPRO, USD, TECL), 63-session momentum lookback, top 2, monthly rebalance, absolute momentum
filter vs SHY, 21-session realized-volatility target (base 0.40, dip-boost 0.60 for 10 sessions
after QQQ closes above its 200-session SMA with Wilder RSI(10) below 30), leverage cap 1.0. What
changes: the remainder (1 minus the risk-sleeve weight, decided solely by the unchanged machine
above) is redirected from SHY into a Defense First sub-allocation. Cost model 10 bp per side
primary / 20 bp per side stress, `sum(|delta w|) x slippage` over the full expanded weight vector,
contract id `cost_v1_10_20bps_next_open_defense_first`. Data: local SIP daily adjusted archive;
cash-hurdle instrument BIL.

Exact Defense First rules pinned this pass (source: AllocateSmartly's independent replication,
cross-checked against the author's own LinkedIn post and Quantitativo; the primary SSRN paper's
full text was not fetchable -- see search-space.md for the full source discussion):
- **Momentum score**: mean of each asset's 1, 3, 6 and 12-*calendar*-month dividend-adjusted
  percent return (not a fixed-session-count approximation), computed from month-end closes.
- **Rank and weight**: rank TLT, GLD, DBC, UUP from highest to lowest momentum score; allocate
  40% / 30% / 20% / 10% by rank.
- **Cash hurdle**: if an asset's momentum score is below BIL's own momentum score (computed the
  same way), that asset's tier weight is redirected to the fallback asset instead.
- **Rebalance timing**: decided on the last trading day of the month at the close, held to the end
  of the following month, rebalanced monthly regardless of whether the target changed; this
  iteration adds an explicit next-open fill (a disclosed addition beyond the source text, for
  consistency with this repo's own execution convention).
- **Failing-slot fallback**: SPY, per the published rule (DF01). DF02 is this iteration's own
  disclosed departure -- SHY instead of SPY -- to keep the remainder free of equity beta, since the
  remainder's whole purpose in S3 is to be the non-risk part of the book.
- **Discrepancy noted**: AllocateSmartly's and BestFolio's replications substitute PDBC for the
  commodities leg; the author's own LinkedIn post and Quantitativo both say DBC. This iteration
  uses DBC (the author's own stated ticker, and what the local archive has).

Candidates (3, exactly as specified, each an independent comparison, no selection among them):
- **DF00** reference: S3 as renewed, remainder in SHY (unchanged).
- **DF01**: remainder in Defense First, published SPY fallback.
- **DF02**: remainder in Defense First, SHY fallback instead of SPY.

Controls (preregistered, not candidates): **EW** (1, shared) -- static 25/25/25/25 TLT/GLD/DBC/UUP,
monthly rebalance, no ranking, no cash-hurdle screen. **RR-k** (40 per candidate, 80 total) -- the
same cash-hurdle screen, weights and fallback as the real candidate, but the rank-to-asset
assignment is a fresh seeded random permutation each month instead of a momentum-based rank.

Windows: design window 2016-01-04..2023-09-15 (S3 itself first holds risk 2016-05-02; the Defense
First momentum score needs 12 completed calendar month-end closes, first fully valid at the
2017-01-31 decision applied from the 2017-02-03 open -- before that date DF01/DF02/RR-k default to
DF00's own behavior, same as BG-series warmup handling in H-20260923-11; EW has no such warmup and
is valid from 2016-05-02, a disclosed ~9-month head start). Frozen anchor 2024-01-08..2026-09-16 is
a do-no-harm check only, at 10 and 20 bp. The 2026 holdout (2026-01-02..2026-09-17) was already
spent evaluating the live S3 book at the 2026-09-23 renewal, so **no holdout claim is made for
either candidate in this round**.

## Gates (adoption rule)

All must hold, per candidate, independently, for a candidate to be recommended:
- **(a)** design-window Sharpe >= DF00 Sharpe + 0.10.
- **(b)** design-window max drawdown no worse than DF00's.
- **(c)** design-window Sharpe beats >= 36 of its 40 RR-k placebos.
- **(d)** design-window Sharpe > EW's.
- **(e)** anchor-window (do-no-harm only) at both 10 and 20 bp: CAGR >= 50% and max drawdown
  >= -35% (the frozen gate G1).

Multiple comparisons: 2 candidates (DF01, DF02); both are reported in full regardless of outcome.
If neither passes all of (a)-(e), the verdict is **"keep SHY"**.

## Placebos

RR-k random-ranking placebos, as defined above under Design/Controls: 40 per candidate, 80 total,
design window only, criterion (c).

## Stop condition

Neither candidate passes all of (a)-(e) -> the direction is refuted for this mechanism; reopen
only with a new defensive-asset set, a new published remainder-allocation rule, or new disclosed
data, not by re-tuning DF01/DF02's windows, weights, or momentum blend, and not by widening the
candidate list. Search budget for the decisive test: 83 simulations (2 candidates + 1 EW control +
80 RR-k placebos), fixed; DF00 needs no new simulation. This is round 1 of this direction.

## Results

Executed 2026-09-23 (`scripts/run_h20260923_12_s3_defense_first.py`; full table in
`reports/research/iterations/h20260923_12_s3_defense_first/report.md`). **Verdict: keep SHY.**

- DF00 (SHY): 30.7% / Sharpe 0.83 / max DD -48.0%. EW: 32.6% / 0.86 / -45.8%.
- DF01 (SPY fallback): 35.3% / 0.90 / -49.1%; fails (a) +0.07, (b), and (c) 34/40.
- DF02 (SHY fallback): 33.9% / 0.88 / -46.9%; fails (a) +0.05; passes (b), (c) 40/40, (d), (e).
- Most of the gain is diversification (EW +0.03); the ranking adds about +0.02 and helps mainly
  in 2022. The 2018-2019 drawdown is not reduced. Direction refuted for this mechanism.
