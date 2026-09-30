# Decision Record: t20260930_12_smallcap_gap_auction

## Path

smallcap_premarket_gap_long (C1b): $5-20M dollar-volume gap-down long, K lowest z inside the pool, selected from SIP pre-market minute bars only, open buy / close sell.

## Decision

Stop (closed_unstable, `results.json` `verdict`). X15_K10_EW: main mean -5.37 bp/day (t -1.03), placebo beat 0.40, short -4.15 bp/day; all three continue conditions fail. X0_K10_EW also fails (main -4.80 bp, beat 0.53, short +0.07 bp), so the paid real-time SIP is not the missing ingredient. LA (daily open, C1 caliber) K10_EW main is -3.96 bp/day (< 20), so the failure is not a look-ahead effect but the pool-restricted rule itself. No ledger, no forward shadow task, no paid-plan request.

## Reason

The C1 T1 long +42.17 bp/day came from the 1,535 global-rank extreme gap-downs (median z -3.74) that fall in the $5-20M tier; the other 5,295 picks the pool-restricted top-10 adds average -17.33 bp (`c1_reconciliation.json`, exact reproduction of C1's E_bar). Ten names per day inside the pool dilutes the extreme-event edge to about -4 bp. Additionally only 35% of pool rows have a pre-market bar by 09:11 ET and the selected rows' median pre-market dollar volume is $27.7K on 2 bars.

## Rejected variants

None added after results. X15_K5_EW (+11.4 bp, beat 1.00, t 1.46) and LA_K5_IV (+17.1 bp) are reported only; K5 is not the decision cell and neither reaches the frozen bar. The execution defect found (duplicated month-end rows) was fixed without touching design or gates and disclosed in `report.md`.

## Next iteration suggestion

Do not reopen the pool-restricted top-10 small-cap gap-down long. The extreme-z rare-event object (global top-10 by z over the >= $1M pool, tier cut afterwards, about 2.2 picks/day, E_bar +42 bp with heavy tails and a 2024-2026 contaminated window) would need a new independent preregistration with its own untouched window and a pre-market availability check (most such names may have no pre-09:12 bar); it is a different design from this one and the coordinator decides whether it is worth a slot. ML and AI-information round entry conditions are not met.
