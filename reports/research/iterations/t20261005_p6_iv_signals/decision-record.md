# Decision Record: t20261005_p6_iv_signals

## Path

option_implied_signal_ic_p6

## Decision

Pivot (not stop). Mechanical status `none_promoted_not_at_depth` (hypotheses.md section 5): no signal reached recent L12 t >= 2 with BH q <= 0.10, and every measurable signal is underpowered, so under the owner's depth rule (plan v2 P-1) this is "not at depth", not a refutation. Reviewed by the 2026-10-07 19:37 UTC lead round (Opus) against `results.json`.

## Verified numbers (results.json `promotion`, recent window, L12, after beta and industry)

- IVRV (IV minus RV21, sign +): CIC(2..22) 0.0045, NW t 0.21, BH q 0.555, MDE 0.120 against the reference effect 0.082 (underpowered). By year (`by_year_recent_L12`): 2024 CIC 0.181 (t 5.99), 2025 -0.063, 2026 -0.078. The sign flips with the market state, so a fixed-sign rule is not supported.
- DIV21: not measurable in the recent window. The vendor field `iv_month_ago` is empty from 2023-Q4; counted as p = 1 in the BH family (reason data_missing).
- DIV5 (sign + fixed on the stress window at 05:56 UTC, before the recent window was read): CIC(2..6) 0.0066, t 0.68, q 0.499, MDE 0.029 against 0.010. Marginal IC over the M0 themes: t 1.92, the only lead in this family.
- IVZ3 (sign -): CIC(2..6) 0.0140, t 1.14, q 0.499; IVZ3 minus HVZ3 -0.0002 (t -0.10), so the implied-move scaling adds nothing over realized volatility.

## Reason

The free DoltHub history gives about 574-590 decision dates with about 573 names, which cannot detect effects of the size the papers report after a realistic discount (MDE 0.12 for IVRV against 0.082 undiscounted). More compute on the standalone IC measurement cannot reach depth with this data. The 2026-07..09 IVRV CIC of -0.278 on about 33 dates is a repeated-look number and is recorded only.

## Next iteration suggestion

- Continue the options line through two cheaper routes: (1) IVRV, DIV5 and IVZ3 enter the multi-signal composite engine as candidate features and are judged on marginal net Sharpe there (cost-aware engine follow-up, P1); (2) the self-stored chains (T-20261005-33) keep accumulating and the P6 stage-0 gate on 2026-11-04 (T-20261006-05) decides when the full surface (skew, kurtosis, convexity, the dimensions Walter-Zimmer-Ulrich 2026 find not spanned by stock factors) can be measured.
- The IVRV sign flip between 2024 and 2025-26 is a state-dependence hypothesis for the regime layer (P2 stage 2), not a test to run now.
- Stop the standalone DoltHub IC measurement: no further standalone runs on this data unless a new data source closes the DIV21 gap or extends the dense history.
