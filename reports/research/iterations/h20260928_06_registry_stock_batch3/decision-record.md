# Decision record: h20260928_06_registry_stock_batch3

## Path

`stock_batch3_screen` -- ten preregistered stock-level candidates (see
`search-space.md`), each judged independently against the owner's 2026-09-28
K1/K2 keep rule versus the live S3 sleeve, no ranking among them.

## Decision

Stop. 0/10 candidates clear K1 or K2 (`results.json`, `report.md`). No
candidate is added to `reports/research/screens/kept.jsonl`. Three rows
(signed_jump_variation, end_of_day_reversal, intraday_reversal_reit_pwb) are
parked as needs_modal for the separate Modal cloud lane rather than answered
here. The remaining 21 rows (17 of the original 25 plus 4 of the 5 forwarded
rows) are not_executable this round for a disclosed data/market/short-leg/
engine-mismatch reason, each recorded in the registry append.

## Reason

Best result: momentum_concentrated_k37 reaches anchor Sharpe 1.03 (10bp) but
misses the K1 anchor bar (>=1.19) and fails stress badly (0.51 vs >=0.65); its
K2 diversifier edge is negative in both windows (-0.143 anchor, -0.071
stress), so it adds no measurable value blended with S3 either. The 13D
activist Item-4 long-horizon holds (6/12/24 months) are the weakest family
(Sharpe 0.04-0.49), consistent with the already-refuted dir:event_13d_drift's
finding that the money is priced in before our earliest entry, at any tested
horizon. overnight_only_spy/qqq is a decisive, expected refutation
(Sharpe -4 to -3): the daily round-trip cost (2x 10/20bp) is far larger than
the ~3.5bp/day overnight edge the literature reports, exactly the
cost-sensitivity warning several of this pass's own sources flagged
(gouravsalottra: costs destroy nearly all of a 240-combination grid at
1-2bp). monday_afternoon_spy/qqq -- our own disclosed close-vs-open proxy
for the paper's intraday 12:00-vs-open signal -- also fails, so this refutes
the adaptation, not the underlying peer-reviewed cross-sectional factor
(which was not itself tested). vam_momentum_k50, a disclosed step-1-only
partial proxy of the newly-verified AEGIS paper (arXiv:2604.09060), also
fails K1/K2 on the ranking step alone; the paper's own value-add (minimax-
correlation diversification, SLSQP Sortino allocation) remains untested,
since building it is portfolio-construction work outside this batch's
score-and-top-k engine.

Of the 21 not_executable rows, three shapes recur: (a) wrong market or
missing data category we do not have and have not evaluated a source for
(European/emerging/frontier/Asia-Pacific equities, listed-options IV, ESG
ratings, proprietary buy-side/vendor data); (b) needs a short leg we cannot
execute, often on top of an already-thin long-only leg; (c) portfolio-
construction/optimization mechanisms (risk_based_portfolio_construction_pwb,
trend_filtered_mean_variance_pwb, and AEGIS's steps 2-3) that this batch's
score-and-top-k engine cannot faithfully represent without new simulator
work the brief restricts against. Three rows are near-duplicates of an
already-decided local mechanism (deep_learning_stat_arb_residual,
ml_implied_risk_premia_pwb, event_8k_item402_restatement_drift) and were not
retested, per the mission's rule to reuse existing negative evidence rather
than re-spend compute.

## Next iteration suggestion

Pivot: none of this batch's ten candidates is worth a follow-up on its own
evidence. The three needs_modal rows (signed_jump_variation,
end_of_day_reversal, intraday_reversal_reit_pwb) are the only ones with a
concrete next step -- hand them to the Modal cloud lane (task T-20260928-12)
once available, with the universe/date-range/memory estimates already
recorded in `results.json`. Before spending any further compute on the three
deferred-pending-primary-source rows (tactical_mean_reversion_multi_asset_pwb,
trend_filtered_mean_variance_pwb, moving_average_volume_heuristic_pwb), open
the underlying papers (Caporin/de Roon/Pelizzon 2009, Santos & Torrent 2022,
Etheber 2014) directly, since the paperswithbacktest pages alone do not
disclose the exact formulas needed to test them faithfully.
