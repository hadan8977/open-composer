# Garcia-Ares & Muravyev (2025), "Option returns: a tale of the expiration rollover day"

URL: https://www.fma.org/assets/docs/Derivatives2025/GarciaAres.pdf
Retrieved: 2026-09-29 (this session) -- WebFetch could not parse the raw PDF
bytes (binary/compressed FlateDecode streams); downloaded directly via curl
and extracted with `pdftotext -layout` instead. Full text was read, not a
search-engine summary.
Version: June 20, 2025. Authors: Pedro A. Garcia-Ares (Notre Dame / ITAM),
Dmitriy Muravyev (UIUC).

## Core finding
Most of the published predictability of DELTA-HEDGED OPTION returns (18
option-return anomalies) is concentrated on just two days each month: the
3rd-Friday expiration itself, and especially the FOLLOWING MONDAY. On these
two "rollover" days, covered-call writers roll expiring positions by selling
new options; this concentrated order flow overwhelms market-maker inventory
capacity, forcing them to lower option prices. Rollover days capture roughly
half of all abnormal option-return-anomaly returns across stocks, and the
ENTIRE predictability for S&P 500 stocks specifically.

Verbatim from the paper's own abstract (pdftotext -layout extraction of the
downloaded PDF): "average option returns are highly negative on the two
rollover days, but are slightly positive during the rest of month."

## Sample
Daily option data May 2005-December 2021 (OptionMetrics/CRSP/PHLX); GEMINI
sub-sample August 2013-December 2021. "The patterns remain largely robust
over the entire sample period" (i.e. no strong decay noted within 2005-2021).

## Scope -- what this paper does and does NOT show
This paper studies DELTA-HEDGED OPTION returns (the anomaly literature's
own dependent variable), not raw STOCK price returns. It does not report a
long-only stock/ETF Sharpe, CAGR or drawdown for a "buy the index during
expiration week" rule. It is used in this iteration only as recent (through
2021), methodologically strong evidence that intermediary/order-imbalance
frictions around the 3rd-Friday-plus-following-Monday window are real and
were still detectable as of the paper's sample end -- i.e. that the
MECHANISM invoked by Stivers & Sun (and by the WEEKMON variant's deferred
exit) has independent, more recent support. It is explicitly NOT used to
confirm Quantpedia's 1988-2010 stock-return Sharpe number, which this
iteration's own backtest (not this paper) is the decisive test of.
