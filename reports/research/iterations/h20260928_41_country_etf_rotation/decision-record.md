# Decision Record: h20260928_41_country_etf_rotation

## P1

- Path: country_etf_rotation_screen (8 candidates, `COUNTRY_L{63,252}_N{1,2}_{MO,WK}`,
  cross-sectional momentum rotation across EWJ/EWG/EWU/EWA/EWC/EWZ/INDA/EWY/EWT with an
  absolute-momentum filter vs SHY, reusing `h20260928_40_equity_etf_menus.make_rotation_fn`
  unedited). Numbers from `reports/research/screens/h20260928_41_country_etf_rotation/
  leaderboard.json` and this iteration's own `results.json`.
- Decision: STOP for K1/keep. 0/8 candidates clear K1 (best stress-window Sharpe across all
  8 is 0.0487, all fail the >=0.6447 bar; 5/8 have a negative stress Sharpe) and 0/8 clear K2
  (every stress-window inverse-vol-blend edge vs a vol-matched S3 control is negative). 3/8
  (COUNTRY_L63_N1_MO anchor 1.2131, COUNTRY_L252_N2_MO anchor 1.2107, COUNTRY_L252_N2_WK
  anchor 1.2154) reach `watch_recent` (anchor Sharpe clears the 1.1882 bar, stress does not)
  and are CONTINUE (forward-tracked only, recorded in `kept.jsonl`), not a keep.
- Reason: The mechanism (identical to the sibling h20260928_40 batch's own FACTOR/INDUSTRY
  rotation) shows a strong anchor-window (2024-01-08..2026-09-17)/weak-to-negative
  stress-window (2016-05-02..2023-09-15) split on the country-ETF menu specifically. This is
  directly consistent with the Du & Jiang (2024) decay note quoted on the Quantpedia source
  page itself (see `direction-review.json`): "The efficacy of ETF momentum strategies, while
  robust until around 2010, began to show signs of waning in subsequent years." The owner's
  frozen stress window (2016-2023) falls exactly in the post-decay period the source itself
  flags, so this is a corroborating negative result, not a surprising one.
- Next iteration suggestion: Do not re-tune this lookback/top_n/rebalance grid on this same
  9-ticker menu without a new, distinct signal (e.g. a country-specific macro/flow proxy this
  repo's data does not yet support). The 3 `watch_recent` candidates should be re-checked in a
  future round once more anchor-window data accumulates, to see whether the stress-window
  weakness was a sample artifact or a durable decay; no compute should be spent re-deriving
  this same grid meanwhile.
