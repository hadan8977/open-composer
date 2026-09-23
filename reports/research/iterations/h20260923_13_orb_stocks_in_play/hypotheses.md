# Hypotheses: h20260923_13_orb_stocks_in_play

## Hypothesis H-20260923-13

Individual-stock opening-range breakout filtered by opening relative volume ("Stocks in Play",
Zarattini, Barbon & Aziz, "A Profitable Day Trading Strategy For The U.S. Equity Market", SSRN
4729284): each trading day, rank stocks eligible by price/average-volume/ATR floors by their
first-5-minute volume divided by the trailing-14-day average of the same window's volume; trade
only the top 20 by that ratio; enter with a stop order at the 5-minute opening range's own extreme
in the direction of that range; protective stop at 10% of the 14-day ATR from entry; exit at the
stop or end of day, whichever comes first (no profit target -- the paper's individual-stock section
describes none). SIP01 (long-only, the paper's own eligibility parameters), SIP02 (long-only, a
stricter liquidity floor), and SIP03 (long-short, a non-promotable fidelity diagnostic only) will,
at the next (backtest) step, be tested for whether they clear a preregistered adoption rule beyond
two controls: RD (same selection, random direction) and RL (same mechanics, random non-in-play
liquid stocks). This dossier's own, narrower claim is only that the mechanism's exact rules can be
pinned with quotes from the primary source and reconciled against an independent replication, and
that the minute-data feasibility question the registry already flagged ("feasibility unresolved --
needs a small dev-period check") can be answered concretely enough to either bound a design-window
grid or explicitly defer it -- not that any candidate has been shown to work.

## Failure mode

The single-ETF simplification of this exact author lineage (dir:orb_etf_opening_range_breakout,
H-20260918-02/L-20260918-02) already failed OOS on this project's own data: a random-direction
placebo captured 92.7-92.9% of the real return, and shifting the entry time by 30-60 minutes
matched or beat the real 09:35 entry -- the residual was intraday beta, not an opening-range
signal. The most likely failure mode for Stocks-in-Play is structurally the same trap one level
up: (1) the top-20-by-relative-volume selection could just be picking volatile, high-beta names on
volatile market days, so any apparent edge is generic intraday beta in unusually active names
rather than information in the relative-volume ranking itself -- RL (random non-in-play liquid
stocks, same mechanics) is designed to catch this; (2) the direction call (long if the opening
candle closed up) could carry no information beyond "this name moved a lot today," so RD (random
direction, same selection) is designed to catch that separately. A third, narrower failure mode is
specific to this dossier's own scope: the minute-bar archive this project has may not actually
support a survivorship-bias-free, correctly-priced reconstruction of the paper's universe at all,
in which case the honest outcome of this pass is "feasibility gap identified and bounded, next
step blocked on it" rather than a clean go/no-go on the mechanism itself. A fourth failure mode,
specific to the long-only design constraint: because the published 2.81 Sharpe is a long+short
combined number with no published split, it is entirely possible the edge lives mostly on the short
side (a known pattern in this project -- see dir:cross_sectional_gap_fade, where a related
Concretum mechanism's edge sat in an illiquid short leg) and SIP01/SIP02 (long-only) could show a
materially weaker result than the headline even if the mechanism itself is real.

## Measurement

This pass measures only: (a) whether every rule in candidate-manifest.json is pinned to a direct
quote from the primary paper (or, where the paper and the QuantConnect replication disagree, both
are quoted and the discrepancy is disclosed); (b) whether `oc research direction-check` and
`oc research iteration validate --stage pre-backtest` both return `ok`; (c) a concrete,
evidence-based answer (not a guess) to each of the five data-feasibility questions listed in
data-feasibility.json's `path_gates` reason field -- current-active-asset-snapshot survivorship
risk, the daily-only delisted archive's lack of a minute counterpart, the disclosed staleness of
`data/sip/minute`'s shard index for shards <=316/year, the total absence of a shard index for
`data/sip-hist/minute`, and the adjusted-vs-unadjusted price discrepancy. At the next (backtest)
step, per-candidate measurement will be: design-window (2016-01-04..2022-12-30) CAGR, Sharpe, max
drawdown, hit rate, and RD/RL placebo-beat rate; select-window (2023-09-18..2025-12-31, frozen, the
only ranking window) CAGR and max drawdown at 5/10/20bp plus the commission cross-check, and gate
G1/G3 pass-fail; 2026-01-02..2026-09-17 reported for continuity only, explicitly not a holdout
claim.

## Stop/Pivot criterion

This pass stops here by design (task scope: dossier, data-feasibility check, and engine-design note
only -- no backtest, no engine code). It counts as complete when: `direction-check` returns `ok`,
`iteration validate --stage pre-backtest` returns `ok`, `oc spec validate` passes on the draft
spec, `oc research directions validate` passes after the registry row updates to `queued`, and
engine-design.md states a concrete minute-data loading plan, reuse list from
`scripts/run_h20260918_02_orb_etf.py`, and an expected runtime. If the next step's data-feasibility
work (the cheapest_decisive_test in direction-review.json) cannot bound the survivorship/shard-
index gaps, the direction stays `queued` with that gap named as the explicit blocker, rather than
silently proceeding to a grid on an unverified universe. If, at the backtest step, neither SIP01
nor SIP02 clears the adoption rule in search-space.json's `adoption_rule`, the verdict is "keep
refuted" and `dir:orb_stocks_in_play_relative_volume` is not reopened except with new disclosed
data, a new published selection rule, or a materially resolved feasibility gap -- not by re-tuning
SIP01/SIP02's filters after a partial result. This is round 1 of this direction (previously
`harvested`, not yet triaged into a candidate manifest).
