# Easy-to-borrow proxy v1 (D7), 2026-10-01

Numbers come from `results.json` in this directory (script `scripts/eval_borrow_proxy.py`,
snapshot `data/research/equity_book/borrow/alpaca_assets_20261001.parquet` from
`scripts/snapshot_alpaca_assets.py`, one read-only `get_all_assets` call on the paper base URL,
active `us_equity`: 14,402 assets, 5,274 `easy_to_borrow`, 5,273 `shortable`).

## Set-up
- Label: Alpaca `easy_to_borrow` on 2026-10-01. Universe: `universe_broad` month_end 2026-08-31,
  adv_rank <= 3000, close >= $5, not a fund/ETF (name heuristic), >= 252 sessions of history.
  This leaves 2,075 names (not 3,000: funds, sub-$5 and short-history names drop out); 1 has no
  Alpaca row, so n = 2,074. Features are as of 2026-09-17 (last session in `daily_broad`).
- The label base rate is already 97.5% ETB (99.1% for adv_rank <= 1000, 97.0% for 1001-2000,
  96.0% for 2001-3000). Only 52 of 2,074 names are not ETB. Precision >= 0.97 is therefore
  nearly free; the useful question is how many of those 52 the rule keeps out.
- Features: adv_rank, price, mcap (price x `sec_fundamentals_daily` shares, 88.9% coverage),
  idio_vol_63, `short_volume_ratio_mean_21`, short interest / shares (FINRA, 88.6% coverage),
  reverse split in 252 sessions, days since first price.

## Rule v1 (the design's SE_t)
adv_rank <= 2000, price >= $10, no reverse split in 252 sessions, short interest / shares not
in the top 5% of the cross-section (where available).

Confusion matrix (positive = proxy says shortable; truth = Alpaca ETB):

|  | ETB | not ETB |
|---|---|---|
| proxy shortable | 1354 | 20 |
| proxy not shortable | 668 | 32 |

Precision 0.9854 (Wilson 95% about 0.979-0.991), recall 0.6696.

| adv_rank band | n | ETB rate | precision | recall | FP |
|---|---|---|---|---|---|
| <= 1000 | 776 | 0.991 | 0.9933 | 0.9584 | 5 |
| 1001-2000 | 700 | 0.970 | 0.9763 | 0.9087 | 15 |
| 2001-3000 | 598 | 0.960 | n/a (nothing selected) | 0.0 | 0 |

The 2001-3000 band has recall 0 by construction (excluded by `adv_rank <= 2000`). Its ETB rate
is 96%, so exclusion is a choice about the reliability of the *flag over time* and borrow cost
tail, not a measured borrow failure; `adv<=2500` would give precision 0.9842, recall 0.8012
(2001-3000 band alone: precision 0.9779, recall 0.4634 above rank 2000).

False positives (20): median adv_rank 1204, median price $40.41, median mcap $10.6B, 0% of them
are `shortable` today. They are mid/large names that Alpaca currently cannot borrow; nothing in
price, volume, short interest or short volume separates them.

## Variants (overall precision / recall; full by-band tables in results.json)
| rule | precision | recall | FP |
|---|---|---|---|
| v1 | 0.9854 | 0.6696 | 20 |
| v1 without SI clause | 0.9852 | 0.6929 | 21 |
| adv<=2000 only | 0.9810 | 0.7161 | 28 |
| adv<=2000, px>=10 | 0.9853 | 0.6939 | 21 |
| v1 + mcap >= $1B | 0.9884 | 0.5920 | 14 |
| v1 + short_volume_ratio_mean_21 <= 0.7 | 0.9846 | 0.6320 | 20 |
| adv<=1000 + v1 clauses | 0.9933 | 0.3645 | 5 |
| adv<=2500 + v1 clauses | 0.9842 | 0.8012 | 26 |

The SI clause removes 1 false positive and 47 true positives (it is available only through the
raw FINRA archive for everything; `data/features/short_interest` covers only the top-1000
universe, 799 names on the last date, so the raw `parsed.parquet` was used). The price floor
removes 7 FPs (28 -> 21). Differences between these variants are 1 to 8 names and within noise.

## Logistic regression (5-fold by symbol, single snapshot)
Out-of-fold AUC 0.713. At p >= 0.97: precision 0.9845, recall 0.8150 (by band precision
0.992 / 0.981 / 0.974 for <=1000 / 1001-2000 / 2001-3000). Threshold chosen on the OOF scores
for precision >= 0.97 with the largest recall (optimistic): 0.9785 gives precision 0.9834,
recall 0.7052. The largest standardized weights are idio_vol_63 (-1.63), adv_rank (-0.56),
price (+0.46), days since first price (+0.27). At matched recall (about 0.67-0.70) its
precision (0.983-0.985) equals v1's. It adds no information beyond the rule, and its recall at
p >= 0.97 is higher only because it trades in the 2001-3000 band, where a plain `adv<=2500`
rule is just as good (0.984). No ML in v1.

## Recommendation
Use **v1 unchanged**: simple, precision 0.985 (every band with a selection >= 0.976), no fitted
parameters, keeps names outside rank 2000 out of the short book. The optional mcap >= $1B
clause gives 0.988 at the cost of 8 points of recall; not worth a new frozen parameter.
Forward (shadow/paper) use the live `easy_to_borrow` flag, not this proxy.

## Reverse split detector: direction deviation
The brief said open / previous close near 1/k. A k-for-1 reverse split multiplies the price by
k, so the unadjusted jump shows as a ratio near **k**, and the repo's panels do carry micro-cap
reverse splits as such jumps (2026: 68 sessions with ratio near k against 34 near 1/k, the
latter mostly crashes and forward-split residue). `borrow.is_reverse_split_ratio(direction="up")`
is the default; `direction="down"` is the literal reading. On this sample it barely matters
(v1 literal: precision 0.9854, recall 0.6691). 0.24% of the universe has a reverse split in the
last 252 sessions; ETB rate given a reverse split is 60% against 97.6% without.

## Caveat: the label is one snapshot dated 2026-10-01
Applying it to history assumes borrow status is stable. What was measured (rule applied at an
earlier date, compared with today's flag; names no longer on Alpaca's active list are excluded,
so these are survivor-only):

| as-of | names not on today's active list (excluded) | share of today's ETB names that met v1 then | share of today's v1 names that met v1 then | precision vs today's flag | recall |
|---|---|---|---|---|---|
| 2025-09-17 | 79 | 0.725 | 0.912 | 0.9830 | 0.6755 |
| 2024-09-17 | 156 | 0.742 | 0.897 | 0.9850 | 0.6667 |
| 2023-09-15 | 235 | 0.743 | 0.879 | 0.9779 | 0.6656 |

So membership is fairly persistent (88-91% of today's v1 names also met the rule 1-3 years ago)
and precision against today's flag holds at 0.978-0.985. This is a *rule persistence* test
against a current label; it cannot see names that were hard to borrow in the past and are
delisted or now fine (the 79/156/235 excluded names are exactly where borrow trouble
concentrates: bankruptcies, SPAC and buyout situations). Treat 2018-2025 short books as
carrying an unmeasured borrow-availability risk; the 25 bp/yr borrow assumption (100 bp stress)
is the only buffer, and squeeze/recall events are not modeled.
