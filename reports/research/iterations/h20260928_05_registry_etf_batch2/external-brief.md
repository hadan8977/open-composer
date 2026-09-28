# External Brief: h20260928_05_registry_etf_batch2

Ten sourced findings ground this batch-2 registry triage round (full detail in
`external-brief.json`): five paperswithbacktest replications of published
academic papers (Simon 2008 on the BEP covered-call closed-end fund; Caporin,
de Roon & Pelizzon 2009 on tactical mean-reversion allocation; Santos &
Torrent 2022 on Markowitz-plus-trend-following; Todorov 2021 on ETF
rebalancing price impact; Etheber 2014 on moving-average volume effects), a
secondary summary of Graziani (2024, SSRN) on end-of-month reversal, a
practitioner replication of the pre-FOMC drift literature (quantseeker.com,
building on Lucca & Moench 2015), an independent turn-of-month replication
(hulltactical.com), and two primary official sources (the Federal Reserve's
own FOMC calendar pages and BEP's own SEC EDGAR N-CSR liquidation filing).

Three of the five paperswithbacktest rows turned out to be individual-stock
or mixed-universe strategies (16, 26 and 208 positions respectively), not
pure ETF-level rules, and are handed to the stock-level agent rather than
tested in this ETF-only batch. The commodity ETF flow-impact paper's exact
rule is undisclosed on the page and may need flow data we lack, so it is
marked not_executable pending the primary paper. The remaining five
mechanisms (HFEA, turn-of-month, end-of-month reversal, front-running sector
seasonality, and pre-FOMC drift on two tickers) are fully specified,
long-only, and computable from price data alone, and are preregistered as
seven lane candidates in `candidate-manifest.json`.
