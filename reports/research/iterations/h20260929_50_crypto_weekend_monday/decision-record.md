# Decision Record: h20260929_50_crypto_weekend_monday

Verdict: refuted at step 1. The published weekend-crypto effect replicates in the Friday-close to Monday-open gap (priced before a Monday-open fill) and does not appear after the open. No batch is run. Numbers come from `results.json` (cells, `continue_rule`) and `split-table.md`; the gate was frozen in `candidate-manifest.json` before any result was computed.

## P1

- Path: weekend_split_table (3 signal rows: BTC, ETH, EW10 = equal weight of the available coins among 10)
- Decision: stop (refuted; label "predictive power in the gap, priced before the fill")
- Reason:
  - Gap replicates. W<0 minus W>=0 mean gap, grouping neg, QQQ: BTC -50.9 bp (t -4.03) post_luna and -54.8 (t -3.03) anchor; ETH -57.0 (-4.63) and -61.7 (-3.54); EW10 -51.3 (-4.09) and -60.2 (-3.50). SPY is -36 to -45 bp, t -2.7 to -4.4. Placebo share of |t| below the real one is 0.994 to 1.000 in all 12 cells. Full sample 2016-05+: QQQ gap -32.3 to -37.9 bp, t -3.6 to -4.1. The gap is not tradable under the frozen close-signal, next-open fill.
  - After the open there is no effect in the paper's direction. Continue rule (any of 3 signals x QQQ/SPY x oc/o2o with diff<0, |t|>=2, |t|>placebo p90 in both post_luna and anchor): 0 of 12 cells pass. oc differences: QQQ BTC -2.1 (t -0.16) and -2.2 (-0.14), ETH -0.1 and +10.0, EW10 +11.6 and +17.0; SPY BTC +1.3 and +3.3. o2o differences are positive (W<0 group higher), for example QQQ BTC +22.9 (t 1.32) and +13.2 (0.60), ETH +9.4 and +27.7, EW10 +33.7 (t 1.98, placebo share 0.944) and +41.8 (t 2.01, 0.946).
  - Holiday Mondays (24 of 225 post_luna, 12 of 142 anchor weeks) are in the main table; the ex-holiday version is stored per cell and does not change the picture (EW10 QQQ o2o anchor ex-holiday +48.0 bp, t 2.20).
- Caveats: crypto data ends 2026-08-31 (last Monday sample 2026-08-31); 222 post_luna and 139 anchor weeks with W; signals with W<0 have 61 to 106 weeks in the recent samples; abstract-only access to the paper; SIP daily bars are not dividend-adjusted beyond the feed itself. The gate reading (same cell must pass in both recent samples, 12 cells, no multiple-testing relief) is lenient, so the refutation is not caused by strictness.
- Unregistered observation, not a result: after negative weekends the Monday open to Tuesday open segment is higher for every signal (EW10 QQQ +33.7/+41.8 bp, t about 2.0, placebo share 0.94-0.95). This is the opposite sign of the paper and one of many non-gating looks; it is a possible reversal of the gap overshoot, not evidence. Using it would need a new preregistered contract and a fresh sample (crypto and SIP data after 2026-08-31), it does not inherit this iteration.
- Next iteration suggestion: none for this direction. The weekend information is available in the Sunday-evening ES futures and in Alpaca's Sunday 8:00 PM ET overnight session, which is a different fill rule that is out of scope here and unverified; mark that as the only remaining reopen path.
- ML or AI-information round entry conditions: not met, no model involved.
