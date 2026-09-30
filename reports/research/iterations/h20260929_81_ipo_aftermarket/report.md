# h20260929_81_ipo_aftermarket report (T-20260929-81)

Question: after tiered spread and borrow, do the IPO quiet-period-expiry long window (A) or the post-first-week-pop short window (B) still pay in 2016-2026, especially from 2024? Protocol frozen before any return: `protocol-preregistration.md`, `direction-review.json`, `candidate-manifest.json`. All numbers below are from `results.json` (script `scripts/run_h20260929_81_ipo_aftermarket.py`, run under `scripts/run_capped.sh --mem 1.5G`).

Verdict: **IPO aftermarket calendar windows closed.** Neither family passes (`results.json` `family_pass` A false, B false; `gate_checks` lists every condition). research_pass false, workflow_pass true, no ledger beyond the 10 event-study rows, no paper use.

## Sample and the T-21 event-table defect
- T-21 table: 3,916 candidates minus 339 removed by the non-common-stock name filter (preferred, debentures, notes, warrants, rights, TEUs, depositary shares) = 3,577 events (`build_summary.json`). T-21's 20-sample hand check found 6/20 (30%) bad rows before that filter, 6/17 in the first-trade fallback method and not re-checked after it. This task keeps only `424b4_confirmed` and non-de-SPAC: 1,046 events, which removes the fallback method entirely; residual mismatches (ticker renames, unfiltered fund names) are not measured here.
- Additional frozen filters: no first session within 7 calendar days of the 424B4 date -53; first close below $5 -102; median first-10-session dollar volume below $5M or fewer than 5 volume days -492. Eligible events: 399 (by first-session year: {'2016': 12, '2017': 21, '2018': 32, '2019': 40, '2020': 71, '2021': 113, '2022': 10, '2023': 11, '2024': 33, '2025': 43, '2026': 13}). The queue's 2024-2026 count of 278 is before the price and volume filters; after them 89 events have entries from 2024, so the frozen A requirement n >= 100 for 2024+ cannot be met by any pool (88 in the all pool).
- Price hygiene: `sanitize_price_matrices` defaults on the event panel (54 symbols masked, 180 breaks) and on QQQ/IWM (none). Windows with a masked or missing entry/exit price are dropped (1 event in the all-pool A windows, 0 in the ADV pool), which is a survivorship bias: delisted names lose their exit price.

## A family (long QP-3 signal -> QP-2 open -> QP+k close, QQQ/IWM equal-weight adjusted, tiered round-trip cost)
QP = first session on or after first trading day + 26 calendar days. Clusters = IPO date.

| candidate | pooled n | pooled net | t | 2024+ n | 2024+ net | +10 / -10 placebo net | random p95 | frac draws >= real |
|---|---|---|---|---|---|---|---|---|
| A_QP3_k2_all | 398 | -1.40% | -2.21 | 88 | -3.84% | -0.37% / +0.05% | +0.16% | 0.815 |
| A_QP3_k2_adv1500 | 140 | -1.25% | -1.14 | 24 | -3.96% | +0.02% / +0.38% | +1.04% | 0.870 |
| A_QP3_k5_all | 398 | -0.77% | -0.98 | 88 | -3.09% | -1.08% / -1.58% | +0.11% | 0.295 |
| A_QP3_k5_adv1500 | 140 | -1.98% | -1.50 | 24 | -5.42% | +0.44% / +0.07% | +1.34% | 0.920 |
| A_QP2_k2_all_control | 398 | -2.01% | -3.47 | 88 | -4.54% | -0.64% / -0.30% | +0.12% | 1.000 |
| A_QP2_k2_adv1500_control | 138 | -1.52% | -1.48 | 24 | -5.62% | -0.50% / +0.41% | +0.84% | 0.955 |

By entry year (all pool):

| entry year | n | gross CAR | net CAR (k=2 all) | n | net CAR (k=5 all) |
|---|---|---|---|---|---|
| 2016 | 12 | -0.95% | -1.30% | 12 | -0.67% |
| 2017 | 20 | -0.40% | -0.74% | 20 | -4.15% |
| 2018 | 33 | +1.95% | +1.60% | 33 | +3.43% |
| 2019 | 39 | -0.28% | -0.56% | 39 | -2.41% |
| 2020 | 63 | -1.81% | -2.17% | 63 | -1.28% |
| 2021 | 120 | +0.38% | -0.04% | 120 | +2.02% |
| 2022 | 12 | -4.58% | -5.03% | 12 | -6.52% |
| 2023 | 11 | -1.19% | -1.52% | 11 | -4.06% |
| 2024 | 32 | -4.20% | -4.62% | 32 | -3.28% |
| 2025 | 40 | -2.60% | -3.02% | 40 | -2.57% |
| 2026 | 16 | -3.96% | -4.34% | 16 | -4.05% |

All four decision-eligible windows have a negative pooled net mean (-1.40% and -0.77% in the all pool, -1.25% and -1.98% in the ADV top-1,500 pool), clustered t between -2.21 and -0.98. From 2024 the all-pool means are -3.84% (k=2) and -3.09% (k=5) on n=88. The QP-2 control window (one day earlier) is more negative (-2.01% net, t -3.47), and the random-date placebo means are negative too (about -0.9% to -1.1% in the all pool): newly listed stocks drift down against QQQ/IWM in any five-session window, so there is no positive calendar effect to attribute to day 25. The +10 and -10 placebo conditions are vacuous for the windows whose real mean is negative (limit = 0.5 x a negative mean); those candidates fail the pooled mean, t, n and 2024+ conditions regardless. The -60 session placebo is undefined (no events have 62 sessions before QP inside their own history), reported as n 0.

Diagnostic D10 (non-gating; QP10 = first session >= day 11, the FINRA 2241 minimum quiet period, same window as k=2): all pool pooled net +0.67% (t 0.92, n 399), 2024+ +2.10% (t 1.07, n 89); adv1500 pooled -0.23%, 2024+ +0.47%. Not significant and not a candidate; recorded so the next reader knows the rule-consistent date shows nothing either.

Mechanism note (source cards `finra_15_30_quiet_period_10_days`, `bjr_2003_quiet_period_bang`): the mandatory quiet period was 25 days in 1996-2000, 40 days from 2002 and a 10-day minimum from 2015-12-24, so day 25 is no longer a regulatory date in this 2016-2026 sample. We have no local analyst-initiation dates, so whether initiations still cluster at day 25 is unmeasured; the price evidence does not show a return there.

## B family (short after R5 >= +20%; entry open of session 6; raw net = -(exit/entry - 1) - round-trip cost - tiered borrow)
R5 proxy defect: R5 is measured from the first-session open to the fifth-session close because no offer price exists locally; it is not the offer-to-close pop of the literature and excludes the day-one open jump.

| candidate | pooled n | pooled net short | t | 2024+ n | 2024+ net short (raw) | t | hedged | after dropping top-3 winners (2024+) |
|---|---|---|---|---|---|---|---|---|
| B_R5ge20_h20_all | 65 | +0.99% | 0.20 | 13 | +10.55% | 0.70 | +13.57% | -11.75% |
| B_R5ge20_h20_adv1500 | 38 | +4.51% | 0.65 | 6 | +22.30% | 0.96 | +24.43% | -22.49% |
| B_R5ge20_h40_all | 65 | +2.69% | 0.44 | 13 | +16.74% | 0.97 | +22.01% | -3.56% |
| B_R5ge20_h40_adv1500 | 38 | +6.42% | 0.85 | 6 | +27.96% | 1.47 | +33.66% | -6.54% |

The 2024+ point estimates look large (+10.6% all, +22.3% ADV top-1,500, 20-session hold) but rest on 13 and 6 events, the t-statistics are 0.70 and 0.96 (below 2), and removing the three largest winners turns the means to -11.7% and -22.5%. Pooled 2016-2026 the means are +0.99% (t 0.20) and +4.51% (t 0.65), with the 2018 cell dominated by two events averaging -75% raw short result (squeezes). Unconditional baseline (all eligible events shorted 20 sessions from session 6): pooled -1.32% (t -1.03), 2024+ +2.81% (t 0.97). Borrow costs used are 3% and 25% per year by ADV tier; new issues are often unborrowable, so even these flattering estimates are an upper bound.

| mirror C (R5 <= -10%, long) | pooled n | pooled net | 2024+ n | 2024+ net |
|---|---|---|---|---|
| C_mirror_R5le-10_long_h20_all | 70 | -3.79% | 19 | -4.30% |
| C_mirror_R5le-10_long_h20_adv1500 | 34 | -5.00% | 10 | -0.91% |
| C_mirror_R5le-10_long_h40_all | 70 | -4.04% | 19 | -9.32% |
| C_mirror_R5le-10_long_h40_adv1500 | 34 | -5.05% | 10 | -1.61% |

## Gate summary (from results.json gate_checks)
- A: for every decision-eligible candidate the pooled net mean >= +1.0%, pooled t >= 2.5, 2024+ n >= 100 and 2024+ mean >= +1.0% all fail (the +10/-10 placebo checks pass only vacuously where the real mean is negative).
- B: the +3% 2024+ mean condition passes numerically (all +10.55%, ADV top-1,500 +22.30%), the t >= 2 condition fails (0.70, 0.96) and the leave-out-top-3 condition fails (-11.75%, -22.49%).
- Registered candidates: 10 (6 A + 4 B); the queue text says 12, DSR would use 12 trials only if a family passed. It did not, so no DSR, K1/K2 or 20 bp screen was run.

## Defects and caveats
R5 proxy (above); ADV rank uses a median of IPO-week dollar volume against `dollar_adv_21` of the whole panel (inflated by IPO-week volume, so the ADV top-1,500 pool is generous); hedge leg cost not charged; borrow availability for new issues is assumed, not measured; windows with missing exit prices are dropped; T-21 residual mismatches are not remeasured; only 424B4-confirmed IPOs are covered (first-trade fallback events excluded), so small-cap IPOs without a 424B4 match are absent; 2026 events are truncated at the data end (2026-09-17).

## Next
None for this direction. Reopen only with an analyst-initiation date feed (to test whether initiations still cluster at day 25) or offer prices (to measure the pop properly).
