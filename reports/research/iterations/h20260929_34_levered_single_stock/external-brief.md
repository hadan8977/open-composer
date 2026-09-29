# External Brief: h20260929_34_levered_single_stock

T-20260929-34: individual-stock, synthetic-2x-leveraged, concentrated
(top 1-3), point-in-time-megacap-liquidity-menu version of S3's 63-day-
momentum/vt40 mechanism. 9 sources logged in `external-brief.json` and
`reports/harness/source_cards/h20260929_34_levered_single_stock.jsonl`:
FINRA Notice 09-31 and an SEC statement on single-stock ETFs (regulatory
caution on daily-reset leverage), Alpaca's own margin docs (Reg T 2x
overnight, 5.00-6.50%/yr rate, concentration margin rule), three papers
(Daniel & Moskowitz 2016 momentum crashes, Piras SSRN concentrated
momentum, MDPI LETF expected-return methodology), a Quantpedia concentrated-
momentum backtest writeup, and two internal registry rows (unlevered
top-37 concentrated momentum, and the leveraged single-asset SMA trend-gate
family) that are the closest prior local evidence without being an exact
repeat of this design. See `direction-review.json` for the reconciliation
against those two registry rows and the full stop condition.
