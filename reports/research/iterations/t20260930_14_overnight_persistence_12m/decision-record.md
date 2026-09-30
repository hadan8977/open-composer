# Decision Record: t20260930_14_overnight_persistence_12m

## Path

overnight_persistence_oos_band (C2a-prime): ON252 (trailing 252-night mean close-to-open return) decile long-short, held close to next open only; test A on the unseen dv21 1501-3000 pool, test B official-auction-price check on the P500 trading pool.

## Decision

Stop (lead review, 19:07 UTC round, 2026-09-30). `results.json`: `gate_a` true, `gate_b` false. The preregistered failure reading "B 不过：日线开盘价口径的假象……关闭" applies, so the overnight-persistence line closes and T-20260930-16 is cancelled under the rule written at 13:25 ("任一不过就把 T-16 标 cancelled").

- Test A passed with room: pool B main window +13.69 bp/night (NW t 5.19, n 683, placebo beat 1.00), stress window +17.35 bp (t 12.02, n 1729, placebo beat 1.00). The next-day intraday leg of the same book is -15.72 / -20.74 bp. Overnight persistence is a general cross-sectional feature, not a P500/P1500 artefact.
- Test B failed on the LO leg only: delta_lo20 -5.88 bp/night against a -4 bp bar; delta_ls -2.72 bp passed; missing 0 of 1,958 pairs.

## Reason

The lead re-derived delta_lo20 from `cache/official_pairs.parquet`: day-mean -5.88 bp, standard error across the 20 seed days 2.18 bp, median day -6.56 bp, 13 of 20 days negative. The point estimate misses the bar by less than one standard error, but the bar is frozen and the median day is on the same side.

The gap is real, not a pricing bug. 41 of the 400 LO20 rows have |delta| >= 50 bp and carry 60% of the sum. Spot checks in `cache/official_prices.jsonl` show delayed listing-exchange opens:

- CVNA 2025-04-04: the NYSE official open printed at 09:38:19 ET at $165.00, while the daily bar open (first consolidated print) was $170.00.
- SMR 2026-01-14: the official open printed at 09:32:48 ET at $18.60, while the daily bar open was $18.99.

For the top-20 retail-theme names, the first print sits above the price a seller actually gets a few minutes later. This matches Berkman et al. (2012): opening prices of attention stocks are temporarily high.

Cause of death: execution (the sell leg), not the signal. It also bears on the continuous-market path T-16 would have measured. This account's 137 pre-open market orders filled 88-114 s after 09:30, when half-spreads were 13-17 bp. Those fills also come after the first print, so the paper path would likely meet the same post-open decline (an inference; T-16 would have measured it and is not run).

## Rejected variants

None added after results. The executor's trimmed figure (LO20 delta -2.64 bp after dropping |delta| >= 50 bp) is not preregistered and is not used. It would also discard exactly the delayed-open rows that a real order meets. The LS book passes test B but needs shorting, and its net edge at 2x auction cost is about zero (17.0 - 2.7 - 16 bp), so it is not a fallback either.

## Next iteration suggestion

Close line C's single-stock overnight and intraday paths (program stop condition: "它也不过就关闭日内个股线"). Do not reopen on the same historical windows. A reopening would need new identifiable information: a free source of listing-exchange opening-cross prices together with a pre-open exit path that is shown to beat the official open on unseen dates. Neither exists today. ML entry conditions (the T-17 "refuted" branch that would model overnight features) are not met because this step failed.
