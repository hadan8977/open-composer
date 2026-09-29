# Search Space: h20260929_02_pre_holiday_etf

One path, `pre_holiday_etf_screen`, 18 candidates total (under the 24-per-path
and 80-total caps): 12 primary `PREHOL_{IWM,IJR,IWC,VB,SPY,QQQ}_H{1,2}`
candidates (4 small/micro-cap target-group tickers x 2 hold lengths, 2
large-cap control-group tickers x 2 hold lengths) plus 6
`PREHOL_{ticker}_RAND` per-ticker frequency-matched internal placebos (never
keep-eligible). Parameters (ticker, hold length {1,2}) are fixed before any
return is computed, taken directly from the source's own market-cap tier
distinction (small vs large) and the two natural hold-length choices (the
pre-holiday session itself, or also the first reopen session) -- not tuned to
this batch's own outcome. Cost assumptions: 10bp primary / 20bp stress per
side, close-signal -> next-open fill, screen_lane's frozen contract, identical
to every other batch this round. Benchmark family: SPY buy-and-hold, SHY
buy-and-hold, and S3 (h20260928_01_s3_rebalance_tranching) as the K1/K2
reference. Keep rule: K1/K2/strong_keep/watch_recent per
`candidate-manifest.json`, primary candidates only, subject to demotion by
their own ticker's RAND placebo. This is a lightweight, single-mechanism
iteration (18 <= 24 candidate budget) exempt from campaign-contract binding
per `single_mechanism_no_campaign_attestation`.
