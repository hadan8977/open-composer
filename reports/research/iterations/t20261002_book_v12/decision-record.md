# Decision Record: t20261002_book_v12

## Path

simple_construction_equity_book_v12

## Decision

Continue (the stop/pivot criterion of hypotheses.md is not met): proceed to paper incubation per hypotheses.md section 6 with M0_U3000 as the primary variant (quant1 runs F1, quant2 runs F2). Three of four variants reach tier P1; none reaches P2. Only condition 1 of the section 6 start conditions (primary variant at or above P1) is met by this task. Conditions 2-6 (live directory consistency check, production target generator parity to 1e-9, two engine dry-run sessions, checklist to the owner at least one session before the first order, switch and cancel test) are open. The contract text is unchanged since the 05:31 UTC freeze (`hypotheses.md` has no diff against HEAD; its sha256 is in `results.json`) and no parameter was tuned.

## Tier table (evaluation standard v2.0.1, family DSR plus the program-DSR cap)

Source: `results.json` in this directory (T-20261002-26, 2026-10-02).

| variant | tier | family DSR | program DSR (N=111) | R6 recent net Sharpe | placebo net / gross pct | robustness | vetoes | R1a gross signal t (iid / NW5) |
|---|---|---|---|---|---|---|---|---|
| M0_U3000 | P1 | 0.912 | 0.662 | 1.51 | 1.00 / 1.00 | 5 of 6 | none | 2.88 / 2.94 |
| M0_P1000 | none | 0.680 | 0.319 | 0.97 | 1.00 / 0.89 | 4 of 6 | none | 1.20 / 1.21 |
| M1_U3000 | P1 | 0.879 | 0.590 | 1.39 | 1.00 / 1.00 | 5 of 6 | none | 2.31 / 2.49 |
| M1_P1000 | P1 | 0.757 | 0.404 | 1.10 | 1.00 / 0.92 | 4 of 6 | none | 1.27 / 1.33 |

- Family: 10 series (v1 Stage 2a M0/M1 x A/B/C plus the four R6), mean pairwise correlation 0.4858, N_eff 5.628, var_SR 0.2914.
- M0_P1000 misses P1 on the family DSR (0.680 < 0.70). M1_P1000 passes P1 but its program DSR is below 0.50 (it could not enter P2 in any case).
- P2 is missed by every variant on signal t (< 3.0); the U3000 variants also pass every other P2 condition (M0_U3000 DSR 0.912, placebo 1.00 / 1.00, robustness 5).
- Primary variant rule (section 6): highest family DSR among variants at P1 or above, which is M0_U3000 (0.912; next M1_U3000 0.879).

## Account layer (A1, $1M, whole shares, $100 minimum order, Alpaca margin, delisting bound -30% long / 0 short)

- Margin violation sessions: 0 for all 4 variants in both forms (also 0 with equity fixed at E).
- Participation median below 1e-5 of 21-day dollar ADV for every variant.
- F1 overlay (stocks plus SPY hedge, no T-bill, no cash) recent net Sharpe is 0.04-0.10 below the strategy-level R6 value, so the 0.25 rescore rule did not trigger for any variant.
- M0_U3000 recent window: F1 Sharpe over BIL 1.03 (annual excess 5.3%, volatility 5.2%); F2 excess over SPY 4.0% a year, tracking error 2.9%, information ratio 1.36.
- Sensitivities (delisting recorded as 0, borrow 25 bp, cash interest) are in `account-summary.json` and `report.md`.

## Reason

- T-25 showed the R6 construction keeps a recent net Sharpe of 0.97-1.51 at k = 1 but needs about 3x gross. This task showed that the F1 / F2 scaling of hypotheses.md section 3 removes the margin problem and keeps 0.04-0.10 of the Sharpe at the overlay level after whole shares, the $100 rule and the delisting bound.
- The placebo net percentile is 1.00 for every variant but carries no information (random weekly reshuffles turn the book over completely, net placebo Sharpe is -1.9 to -4.7). The gross percentile is informative: 0.89 and 0.92 for the P1000 variants.
- Diagnostics (not tiering): the factor-ETF spanning regression leaves an alpha of 9.4% a year (t 2.14, R-squared 0.57) for M0_U3000. The attribution of the M0_U3000 strategy-level book over the recent window splits into style 9.0% (residual-volatility style 12.7%), industry 1.0%, specific -1.2%, market 0.0% and the SPY hedge leg 9.4% (annual, k = 1). The return is mostly a style premium, not stock selection inside styles.
- Limits as in hypotheses.md section 9: 674 recent sessions, all windows already seen, proxy borrow set, fitted costs.

## Next iteration suggestion

- T-20261002-27 / T-20261002-28 (production target generator, engine hedge leg, live dry-run) must reproduce this module (`open_composer/research/equity_book/book_v12.py`) to 1e-9 on historical dates.
- Forward shadow record from 2026-09-18 once the live data are consistent; monthly re-scoring and the validity date 2026-12-31 as in section 7.
- Watch the residual-volatility style: it carries most of the recent P&L and turned negative in window B (2026-07-01 onward) in the attribution.
