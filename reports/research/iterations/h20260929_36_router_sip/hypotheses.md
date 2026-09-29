# Hypotheses: h20260929_36_router_sip

## H1: the frozen router route still earns a positive, cost-net, S3-diversifying return on SIP data in 2024-01-08..data end

- Hypothesis: buying, at the 09:32 bar open, the one name among 12 NASDAQ mega-caps with the largest opening loss and relative volume >= 1, on days when QQQ's 10-session prior momentum is negative, and selling at the close, is a liquidity-provision reversal trade (Heston, Korajczyk, Sadka 2010; Baltussen, Da, Soebhag 2025). On the IEX cache it reached Sharpe 1.41 and annualized 35.24 percent (sweep_002 full window). If the mechanism is real, the same frozen route on SIP data keeps K1 (anchor Sharpe at 10 bp >= 1.19, 20 bp anchor CAGR > 0), K2 (combo edge with S3 >= +0.05) and G3 (beats >= 90 percent of 200 random placebos).
- Failure mode: (a) the IEX result was a thin-tape artifact (IEX is about 2.5 percent of volume, so opening returns and relative volume there are noise-selected); (b) the effect was a 2024-2025 sample accident (Longbridge cross-check: out-of-sample Sharpe -0.19); (c) 10 bp per side removes a gross edge of a few bp per trade; (d) a placebo with the same gate and random pick does as well, so the gate rather than the pick carries the result.
- Measurement: results.json windows anchor 2024-01-08..data end, select 2023-09-18..2025-12-31, contaminated holdout 2026-01-02..2026-09-17, new holdout 2026-09-18.. and partial stress 2023-01..2023-08; Sharpe, CAGR, max drawdown, days, hit rate and mean bp per trade at 10 bp, 20 bp and the original 2.5 bp; screen_lane diversifier edge vs S3 offset 0; placebo percentile.
- Benchmark family: B_ew equal-weight intraday long, S3 vol-matched control, random-pick placebos P1-P3 and 200 distribution seeds, recorded IEX numbers.
- Stop/Pivot criterion: refuted if K1 fails; partial if K1 passes and K2 or G3 fails; kept only if K1, K2, G3 all pass. No threshold changes after results.

## H2: the difference between the IEX result and the SIP result is a data effect, not a parameter effect

- Hypothesis: with the parameters unchanged, the route's SIP-tape return differs from the IEX-tape return mainly through which name is picked on the opening bars and through the entry and exit prices.
- Failure mode: no local IEX minute cache exists, so the cause cannot be isolated by replay; only recorded IEX numbers and a Longbridge cross-check are available.
- Measurement: SIP results on the same window 2024-05-31..2026-05-29 at the original 2.5 bp cost vs sweep_002 full-window (Sharpe 1.41, annualized 35.24 percent, 153 traded days) and sweep_003 Longbridge cross-check; SIP bar-count completeness at the entry bars; close-vs-daily cross-check.
- Stop/Pivot criterion: informational, does not gate H1.

## H3: the short leg of this router is structurally empty

- Hypothesis: for selection_style opening_reversal with top_n = 1 the long_short selector ranks shorts with the same score list as longs and skips symbols already used, so R0_short has zero trades and R0 equals R0_long (intraday_daily_rotation.py lines 1012-1026 and 1030-1070). If confirmed, the IEX research_pass never tested a short leg.
- Failure mode: the code path differs from this reading (then R0_short has trades and is reported as is).
- Measurement: R0_short trade count and R0 vs R0_long daily return equality in results.json.
- Stop/Pivot criterion: informational; a real short leg would be a new direction with new preregistration, not a variant of this one.

## Results (appended after the run; numbers in results.json)

- H1: not supported. Anchor 10 bp Sharpe -0.126, 20 bp CAGR -14.15 percent, combo edge vs S3 -0.614, beats 89 percent of 200 placebos. Status refuted.
- H2: partly supported. Same parameters and original cost give +10.33 percent CAGR and Sharpe 0.536 on SIP in the IEX window versus 35.24 percent and 1.41 recorded on IEX; the cause cannot be isolated because no IEX minute cache exists.
- H3: confirmed. R0 equals R0_long and R0_short has 0 trades.
