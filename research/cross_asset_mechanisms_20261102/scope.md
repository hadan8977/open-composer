# Proposed economic scope

This branch investigates the retained cross-asset D1 mechanism, alongside the
separate ongoing Martin model question. It is selected because D1 passed its
original standalone K1 test, had lower S3 correlation (about .30 anchor/.27 stress)
and a substantial recent same-risk combination edge. Its original K2 failure
remains intact. Data convenience or the new lab entry is not the economic reason.

Original evidence:
- reports/research/iterations/h20260928_02_cross_asset_sleeve/report.md
- that directory's candidate-manifest.json, search-space.json and source snapshots
- reports/harness/source_cards/h20260928_02_cross_asset_sleeve.jsonl
- scripts/screen_batches/h20260928_02_cross_asset.py
- reports/research/screens/h20260928_02_cross_asset/leaderboard.json
- scripts/run_h20260923_12_s3_defense_first.py and its original results

Read applicable unsuperseded constraints from the archived owner register. The
owner prefers recent whole-account net profit, same-risk comparison and deeper
mechanism work over stopping after one weak comparison. No change to old criteria,
seen-window labels, causal decision clocks, resource limits or paper authority.

The proposed direction budget is 24 materially distinct variants, in six families
of four. Freeze explicit deterministic definitions before new numerical work:
1. Failed-rank capital destination: SHY, BIL, conditional SPY trend, defensive-only
   redistribution, compared with original SPY fallback.
2. Weighting mechanism: equal eligible weights, inverse trailing volatility,
   volatility contribution cap, top-two concentration; no fitted full-window weights.
3. Asset-role removal: exclude TLT, GLD, DBC or UUP individually, preserving all
   other definitions and attributing the effect against the full D1 basket.
4. Information representation: slow momentum only, fast momentum only, omit the
   latest month, scale the original blended momentum by trailing risk.
5. Deployment frequency/turnover mechanism: native monthly, weekly, daily only
   on rank change, and monthly with a no-trade band. Original monthly is a control;
   include a genuinely different hysteresis rule rather than count its repetition.
6. Combine D1 and S3 with causal equal, fixed low D1 share, inverse volatility,
   and capped risk contribution. Separate allocation from signal contribution.

Do not run a Cartesian parameter grid. Reviewer may remove redundant or
ill-defined members and state the economic reason; 20-50 remains the direction
budget. Use a small distinguishing first batch if it can rule out useless family
expansion; plateau means change mechanism. Current scope authorizes no adaptive
optimization beyond these predeclared mechanisms.

Source limitations: the original Carlson preprint was not fully retrieved; old
cards distinguish author/published rules from replications. Verify primary method
claims if the new definitions need them. Local variants are adaptations, not
claimed faithful replications. Preserve SIP daily hygiene and split-trigger
exclusions appropriate to this new branch; don't change the frozen old run.

Use the original causal close signal/next-open accounting and 10/20bp costs.
Original selection ends 2025-12-31, anchor 2024-01-08..2026-09-17, stress ends
2023-09-15. All historical windows are seen. Select in development only; the 2026
window is contaminated reference, not a lockbox. Do not refresh data or open new
unseen windows for this task. Native offset robustness, BIL excess returns and
same-risk S3 controls remain explicit. For claims about $20k deployability,
separate return scaling from whole-share/capacity limits.

Use open_composer.lab for real accounting, costs, cumulative starts and outputs.
The original screen CLI now writes research/<direction>/batches/<run-id>, including
native leaderboard and ledgers. Store new definitions in this direction and the
existing native manifest/spec path as required; validate any revised StrategySpec
before its dependent strategy code. Import actual relevant prior trial exposure
from original ledgers, including preceding defense-first variants; unknown broader
search history must remain explicit. DSR is conditional on that inventory and
cannot grant promotion. Selectable new trials and failed starts count, controls
and old evidence imports do not become new economic variants.

Primary outcome: whole-account net dollars and incremental contribution beside
S3 at matched risk on development, with drawdown, exposure, underwater duration,
turnover and cost-stress attribution. Keep an equal-weight basket and BIL/SHY as
simple controls. Report the old frozen K1/K2 measures separately; never rewrite
those bars to declare an old failure passed. Reject an exact mechanism only on
its evidence; stopping allocation is distinct from refuting all cross-asset trend.

Local jobs must retain 500 MiB reserve; current Martin job has priority and must
not be duplicated or interrupted. The small ETF panel can use a capped sequential
job only after memory admission. Use no new paid provider. One pytest at a time,
only if affected behavior has not already been checked. Final independent Lead
checks raw dollars and counterevidence and chooses the next complete task.

## Correction after the first independent scope review

The review at runs/mechanisms-20261102-1/plan_review/review.md identifies a real
combination-clock defect in the frozen screen calculation. This branch will use
`lab.book_engine` and the existing share/cash `equity_book.run_book` for combined
asset-level target weights. Yesterday's holdings earn the overnight move; today's
new target fills at the open. The old screen/drift result stays historical only.
One nonzero-gap/rotation-cost check is sufficient for this affected behavior.

Primary selection window is exactly 2023-09-18..2025-12-31 (seen development).
All candidates and controls use common valid dates and $20,000 initial capital.
Original anchor, its 2026 portion and old stress are separately labeled diagnostics;
they neither choose candidates, parameters nor offsets. Monthly offset zero is
fixed for the primary account, with the existing offset distribution retained
only as robustness evidence if needed, never selected on anchor.

Mechanisms 1-5 use fixed 50% D1 / 50% source S3 allocation. The new account nets
asset-level targets from both sleeves and charges 10/20bp on actual account orders
at every underlying signal or allocation change. Thus both underlying and
allocation turnover are charged; offsetting internal sleeve trades are netted in
this single account. Report the accounting change against old two-sleeve additive
fees explicitly. Cash residual is SHY unless the mechanism explicitly uses BIL.
The original D1 signal, an equal-weight TLT/GLD/DBC/UUP basket and S3/SHY are controls
under the same new accounting. Mechanism 6 fixes original D1 and changes allocation.

Freeze these 24 variants before numerical evaluation (original rules are extra
nonselectable controls, not counted among the 24):
- F1 SHY fallback; F2 BIL fallback; F3 SPY fallback only when SPY close exceeds its
  trailing 200-session mean, otherwise SHY; F4 redistribute failed-rank weights
  proportionally among passing defensive ranks, or SHY if none passes.
- W1 equal weights over passing defensive assets, retaining original total
  defensive allocation and SPY fallback; W2 inverse trailing 63-session volatility
  over passing assets at the same total defensive weight; W3 W2 with any asset
  capped at 40% of total account, excess to SHY; W4 keep the top two passing ranks,
  renormalize their original rank weights to the original total defensive weight.
- X1/X2/X3/X4 remove TLT/GLD/DBC/UUP respectively, rank remaining assets and
  renormalize the first three original rank weights to one before hurdle/fallback.
- M1 use only 12-calendar-month returns; M2 only 1-calendar-month returns; M3 use
  3/6/12-month returns measured one calendar month before the signal; M4 divide the
  original blended score by trailing 63-session volatility. Apply the identical
  transformation to the BIL hurdle; all lookbacks end no later than signal close.
- T1 weekly Friday signals; T2 daily evaluation but trade only on a change in the
  ranked asset order or pass/fail set; T3 monthly signals with a 10 percentage-point
  maximum asset weight-change threshold (hold all weights when every delta is
  below the threshold); T4 daily rank/pass change confirmed at two consecutive
  closes before trading. Source S3 retains its original timing in every case.
- A1 fixed 25% D1/75% S3; A2 fixed 75% D1/25% S3; A3 inverse trailing 63-session
  standalone sleeve volatility, monthly signal, equal weights during warmup;
  A4 A3 with each sleeve's allocation clipped to [25%,75%]. Standalone histories
  used by A3/A4 are costed and causal; changing either allocation incurs real
  asset-level account turnover. The 50/50 allocation is the common control.

Primary comparisons preserve both practical fixed-control dollars and a clearly
labeled ex-post same-volatility diagnostic. For the latter, choose a constant
S3 share k in [0,1] with SHY remainder to match each development combination's
realized volatility, using the same account engine and cost scenario for each
paired control. This is development normalization, not an executable historical
risk forecast. If the target volatility lies outside the achievable range or
matching fails, report unmatched with its risk gap; don't extrapolate leverage.
Do not select a different k from 2026 or claim that diagnostic control was tradable.

For each pair retain daily net returns, equity, costs, exposure and turnover;
report both dollar profits, increment, volatility, maximum drawdown, longest
underwater duration and number of rebalance/trade sessions at 10 and 20bp.
DSR uses the actual development combination return minus aligned BIL, all known
relevant candidate starts, and native HAC assumptions. A fixed 21-session moving
block bootstrap of the paired development daily return difference reports 95%
uncertainty (1,000 diagnostic draws, seed 20261102); it does not select candidates
or count as 1,000 trials. Unknown earlier exposure limits inferential claims.
Final Lead judges the economic conclusion from these accounts and uncertainty;
no new promotion threshold, paper activation or per-variant review is introduced.
