# Dual Momentum Investing: A Quant's Review -- Robot Wealth (negative-evidence check)

URL: https://robotwealth.com/dual-momentum-review/
Retrieved via WebSearch snippet: 2026-09-29 (WebFetch of the full page was not
separately performed in this session; the finding below is quoted from the
search engine's indexed summary of the page, recorded as such)

## Relevant finding (counter-evidence for relative-strength/rotation switching in general)

"When prices move back and forth without direction, signals whipsaw and the
strategy ends up buying and selling at the wrong time. 2015 was the clearest
example: the strategy lost 6.2% despite global equities being broadly flat."
Also: relative-strength/dual-momentum rotation strategies "tend to
underperform during strong bull regimes or when the market rebounds" and
"can struggle during choppy markets, sharp V-shaped recoveries, and periods
when a single asset class dominates for years" -- cited example:
underperformance vs. global stocks 2015-2019. Momentum is a lagging signal by
design and "doesn't catch bottoms" (example given: 2009 return 11.8% vs.
32.7% for a buy-and-hold global equity benchmark).

## Assessment for this iteration

This is general, well-known negative evidence about relative-strength /
dual-momentum switching mechanisms as a family (not specific to any of this
iteration's six pairs): whipsaw in choppy/sideways markets and lag after
V-shaped recoveries are the standard failure modes. It does not refute the
specific QQQ/SPY-style pair-switch mechanism outright, but it is exactly the
failure mode this iteration's stress window (2016-05-02..2023-09-15,
including the whipsaw-heavy 2015-2020 period and the V-shaped 2020 COVID
recovery) is designed to expose, and it is the economic reason the
preregistered STATIC5050 50/50-blend placebo is run alongside every PAIR
candidate: if switching adds whipsaw cost without a compensating trend-
capture benefit, the STATIC5050 control should match or beat the PAIR
candidate's judged Sharpe, which is exactly what the counter-evidence
downgrade rule in candidate-manifest.json checks for.
