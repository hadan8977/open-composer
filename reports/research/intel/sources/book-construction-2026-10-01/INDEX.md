# Source index: book construction (style caps, transfer coefficient, auctions, Alpaca opg/cls)

Coordinator code R1001-1755-T19 (sub-task of T-20261001-19). Collected 2026-10-01 17:55-18:01 UTC by an executor agent. Primary sources only; no backtests. Times below are from `date -u` run at fetch time (to the minute). "Read" means the text itself was opened; "abstract only" means the full text was paywalled or blocked and only an abstract or a secondary description was read.

Access summary
- Fully read: items 6a, 6b, 6c (Alpaca docs and forum threads), 5a (Goyal-Jegadeesh-Wu, Cambridge core reader; abstract, introduction, closing and opening price-impact sections and conclusion read, other sections not), 5b (abstract of Bacidore-Lipson working paper plus intro, read from PDF), 1c (MSCI Research Insight 2012 PDF: abstract, introduction and the Misalignment sections read; the rest only skimmed by keyword).
- Paywalled, NOT read in full: 1a Lee & Stefek 2008 (JPM), 2a Ceria-Saxena-Stubbs 2012 (JPM), 3a Saxena-Stubbs 2013 (J. Risk), 4a Clarke-de Silva-Thorley 2002 (FAJ). pm-research.com returned HTTP 429 then a login redirect; ResearchGate/SSRN/Tandfonline returned 403; Springer returned a client challenge. For those four, only abstracts (from search results) and secondary open-access descriptions were read; the secondary sources are listed under each.

---------------------------------------------------------------------

## 1. Lee & Stefek (2008), "Do risk factors eat alphas?", J. Portfolio Management 34(4):12-25

1a. Primary (PAYWALLED, not read; abstract via search result only)
- URL: https://jpm.pm-research.com/content/34/4/12 (curl gave 429; WebFetch gave a login redirect)
- Query: `Lee Stefek "Do risk factors eat alphas?" Journal of Portfolio Management 2008`; fetch attempt 2026-10-01 17:56 UTC. No snapshot (nothing accessible).
- Abstract as returned by the search tool (paraphrase of publisher text, not verbatim): the optimizer emphasizes the portion of the manager's alpha not captured by risk factors; aligning the risk and alpha models may lead to better portfolios; four remedies are compared.

1b. Accessible secondary of the same claim: Bender, Lee & Stefek (2009) and Menchero et al. are cited in 1c; no standalone MSCI 2008 PDF was found.

1c. MSCI Research Insight, Lee, Ruban, Stefek, Yao (Aug 2012), "Is Your Risk Model Letting Your Optimized Portfolio Down?" (by the same MSCI/Barra authors, includes a section summarizing Lee & Stefek 2008)
- URL: https://www.msci.com/documents/10199/8426a871-688b-4705-ae65-aee7c4c9a0c5
- Query: `Lee Stefek "Do risk factors eat alphas?" ...` (same search); fetched 2026-10-01 17:56 UTC.
- Snapshot: `msci-2012-misalignment-excerpt.txt` (excerpt only; copyrighted PDF not stored).
- Key sentence: "Lee and Stefek (2008) showed that an optimizer will tend to emphasize the part of the alpha that is not shared by the risk factors- the residual alpha- because the risk model believes that part has no systematic risk."
- Scope: US equity, Barra-style factor risk model, long-short and long-only optimized portfolios; momentum 13-month versus 12-month illustration; no sample period or cost figures in this section. The same document says that penalty and custom-factor fixes improve risk forecasts but "the impact on information ratios, however, is mixed".
- Relevance to our design question (a) (do alpha-aligned style caps cut alpha?): The literature says misaligned risk factors let the optimizer over-bet the residual (unspanned) alpha, and that aligning the two "may improve performance, especially when the discrepancy ... does not contain much useful information" (Lee and Stefek via MSCI 2012). It is a statement about aligning the risk model with the alpha, not about hard style caps. It gives no evidence that a style cap aligned with the alpha reduces alpha; the better reading is that caps on risk-model style exposures the alpha loads on are what reduce alpha transfer (see item 4, Clarke et al.).

---------------------------------------------------------------------

## 2. Ceria, Saxena & Stubbs (2012), "Factor alignment problems and quantitative portfolio management", J. Portfolio Management 38(2):29-43 (Axioma)

2a. Primary (PAYWALLED, not read; abstract via search results)
- URL: https://www.pm-research.com/content/iijpormgmt/38/2/29 (curl 429, WebFetch login redirect), abstract page https://jpm.pm-research.com/content/38/2/29.abstract
- Query: `Ceria Saxena Stubbs "Factor alignment problems and quantitative portfolio management"`; fetch attempt 2026-10-01 17:56 UTC. No snapshot.
- Abstract as relayed by the search tool: the paper studies the interaction of the expected-returns model, the risk model, and the constraints used to formulate the portfolio construction problem ("factor alignment problems"), documents their effect on ex post performance of optimized portfolios, and proposes augmented risk models as the remedy.
- Relevance (a): the three-way framing (alpha, risk model, constraints) is the one our design question needs; the abstract does not give numbers on how much alpha is lost to constraints.

2b. Open-access secondary descriptions (read):
- Beheshti (FactSet), Frontiers Appl. Math. Stat. 4:17 (2018), CC-BY, https://www.frontiersin.org/articles/10.3389/fams.2018.00017/pdf , fetched 2026-10-01 17:57 UTC. Snapshot `beheshti-2018-aaf-excerpt.txt`. Key sentence: "Ceria et al. [23] suggest that the proprietary definitions of certain style factors are a potential source of these alignment problems." Scope: 120 simulated portfolios, US/international/emerging, tracking-error caps 6-12%, alpha alignment factor magnitudes 0-40, FactSet GLER/CTEF signals; paper reports AAF improves ex-ante risk forecasts "in nearly every case" and ends with "ultimately improving information ratios" (vendor-authored; no cost-adjusted claim checked).
- Durin (CFM), arXiv:1404.4798 (2014), https://arxiv.org/pdf/1404.4798 , fetched 2026-10-01 17:57 UTC. Snapshot `durin-2014-arxiv-alignment-excerpt.txt`. Key sentence: factor-alignment fixes can be seen "as setting up an explicit constraint on an additional factor dependent on the optimal portfolio" and it notes Ceria et al.'s "difficulty of finding the correct custom risk factor for a long-only constraint". Scope: theory, no empirical sample.
- Relevance (a): constraints (including long-only) create alignment problems; fix is to add a custom/alignment risk factor rather than only loosening caps.

---------------------------------------------------------------------

## 3. Saxena & Stubbs, alpha alignment factor (AAF)

3a. Saxena & Stubbs (2013), "The Alpha Alignment Factor: A Solution to the Underestimation of Risk for Optimized Active Portfolios", J. Risk 15(3):3-37 (Axioma Research Report 022, 2010: "Pushing the Frontier (literally) with the Alpha Alignment Factor"). PAYWALLED, not read.
- URLs tried: https://www.researchgate.net/publication/259384627_... (403), https://papers.ssrn.com (403 for related). Abstract via search tool (2026-10-01 17:56 UTC): develops an optimization technique that adds a dynamic alpha alignment factor to the factor risk model during optimization; uses actual manager backtests to show how pervasive risk underestimation is and that AAF corrects the bias.
- Queries: `Saxena Stubbs "alpha alignment factor" Axioma research paper ...` and `"Pushing the Frontier (literally) with the Alpha Alignment Factor" ...`.
- Author summary (read): Saxena, "The Alignment Trio", LinkedIn, 2023-06-17, https://www.linkedin.com/pulse/alignment-trio-anureet-saxena-ph-d-cfa (via WebFetch summary, fetched 2026-10-01 17:57 UTC, no snapshot). It lists the symptoms as "risk underestimation of optimized portfolios, undesirable exposures to factors with hidden and unaccounted systematic risk, consistent failure in achieving ex-ante performance targets, and inability to harvest high quality alphas into above-average IR."
- Secondary (read): Beheshti 2018 and Durin 2014 as in 2b. Beheshti states the common property: optimized portfolios "possess systematic exposures uncorrelated to the factors of the risk model used to create them."
- Relevance (a): AAF is a risk-forecast fix (it raises estimated risk of the unspanned alpha exposure and so shrinks the over-bet), not a cap on style exposure. The sources claim improved ex-ante/ex-post tracking-error agreement and, vaguely, better information ratios; none of the read texts quantifies net alpha after constraints. Any "alignment cuts alpha" claim is NOT supported by what was read.

---------------------------------------------------------------------

## 4. Clarke, de Silva & Thorley (2002), "Portfolio constraints and the fundamental law of active management", Financial Analysts Journal 58(5):48-66

4a. Primary (not read in full; Tandfonline 403, ResearchGate 403, SSRN landing 403). No snapshot of the primary.
- Query: `Clarke de Silva Thorley "Portfolio constraints and the fundamental law of active management" transfer coefficient`; fetch attempts 2026-10-01 17:56-17:58 UTC.

4b. Secondary texts that state the definition (read):
- Ding (2010), NYU-hosted draft, https://math.nyu.edu/inmemoriam/avellaneda/FundamentalLawFT.pdf , fetched 2026-10-01 17:57 UTC; snapshot `ding-transfer-coefficient-excerpt.txt`. Eq. 59 and surrounding text.
- CFA Digest (May 2005) summary of Clarke, de Silva, Sapra (2004), JPM 31(1):54-63, https://www.hillsdaleinv.com/uploads/Toward_More_Information-Efficient_Portfolios,... , fetched 2026-10-01 17:58 UTC; snapshot `clarke-desilva-sapra-2004-cfa-digest-excerpt.txt`.
- PortfolioConstruction Forum paper (https://obj.portfolioconstructionforum.edu.au/articles_pcc08/PCC08_DDF_PERPETUAL.pdf , 2026-10-01 17:58 UTC, no snapshot) repeats IR = TC x IC x N^0.5.
- Key sentence (Ding): "They define the transfer coefficient as the cross-sectional correlation coefficient between the residual return volatility adjusted active weights and alphas."
- Exact formula in one line (Ding eq. 59 and 60, quoting Clarke et al. 2002): TC = corr(Delta w_i * sigma_ri , alpha_i / sigma_ri) across stocks i, where sigma_ri is the stock's residual volatility; generalized law IR = TC * IC * sqrt(N); with constant IC and diagonal residual covariance, constrained IR = TC * unconstrained optimal IR.
- Is a risk-adjusted TC unambiguous? Yes for the case the paper assumes: weights are scaled by residual volatility (diagonal covariance), forecasts divided by it, and the correlation is cross-sectional. Ding (2010) argues the definition stops giving "constrained IR = TC x unconstrained IR" when the IC varies through time and the residual covariance is not diagonal, and redefines it with the total risk-adjusted weights and alphas (total conditional covariance scaling; exact formula cut off in my extract). Caveat: this reading is from secondary texts, not the primary paper. It is not stated in the read excerpts whether the correlation is centered (Pearson) or uncentered; since active weights sum to zero, treat as Pearson (to be checked against the primary).
- Scope and numbers: Ding repeats Clarke et al.'s simulation range of TC 0.3 to 0.8 for constrained managers. Clarke-de Silva-Sapra (2004), S&P 500 universe, value signal, 4% tracking error, beta-neutral: TC 0.332 with all constraints; 0.347 without the industry constraint, 0.34 without the sector constraint, 0.422 with both removed; 0.298 when the position limit is relaxed; 0.471 without the market-cap constraint; 0.678 without the long-only constraint. No transaction costs in these numbers.
- Relevance (b): definition and formula as above. Relevance (a): this is the only quantitative evidence read on constraint cost; sector/industry neutrality constraints cost little TC in this sample (0.332 -> 0.422 when both removed), long-only and market-cap neutrality cost much more. A style cap is a constraint of the same family, but no style-cap TC number was found.

---------------------------------------------------------------------

## 5. Opening versus closing auction execution costs (US)

5a. Goyal, Jegadeesh & Wu, "Price Impact in Closing Auctions, Opening Auctions, and Continuous Markets: A Benchmark for Cost of Trading on Anomalies", J. Financial and Quantitative Analysis (2026); SSRN 4300417. Relevant sections READ (Cambridge core reader).
- URL: https://www.cambridge.org/core/product/0F72910A79C5B42CF6E85F55164CE846/core-reader
- Query: `Nasdaq opening cross closing cross execution cost comparison ... opening auction versus closing auction empirical study` then `"Price Impact in Closing Auctions, Opening Auctions, and Continuous Markets" ... authors`; fetched 2026-10-01 17:58 UTC.
- Snapshot: `goyal-jegadeesh-wu-auction-excerpt.txt` (excerpt only).
- Key sentence: "The price impact in opening auctions is much larger than in closing auctions though the opening auction sample comprised only stock that had a premarket trade price at 9:28 am, which tend to be the more liquid stocks."
- Scope: NYSE and Nasdaq common stocks (CRSP share codes 10, 11), TAQ plus exchange auction feeds, January 2012 to December 2021; sizes Micro / Small / Large by NYSE market-cap percentiles; square-root price impact model. Closing: price impact lower than in the continuous market except Nasdaq microcaps; example for Large NYSE stocks 3.2 bps (0.5% ADV) and 10.1 bps (5% ADV) in closing auctions versus 6.4 and 20.2 bps continuous; Nasdaq Large 7.2 and 22.7 versus 8.3 and 26.3. Opening: impact measured as open price versus the last 9:27-9:28 premarket trade; premarket prices exist for only 32.8% of the stocks; opening auction volume is about 5%-10% of closing auction volume (about 1.4-1.8% of ADV on average); the paper gives opening coefficients as larger than closing ones (Micro slope 3.34 for opening) but I did not find a table in the extracted text giving the opening cost in bps by size, so the opening-versus-closing basis-point gap is "much larger" (qualitative) rather than a computed number. Annual two-way cost of anomaly long/short portfolios trading in the cheaper mechanism: 17-41 bps/yr (9-21 bps ex-microcaps, closing auctions), 12-29 bps for a USD 100 million portfolio in the conclusion. Fees: maximum USD 0.0027 per share, below 0.69 bps for the average stock.
- Relevance (c): this is the best primary evidence found that the close is cheaper than the open for US stocks and that opening auctions are thin and attract informed flow ("overnight information flow ... opening auctions are likely to attract informed traders"). Caveat: the opening measure is anchored to the 9:28 price, so it measures cost for orders entered before the MOO book closes, which is exactly our next-open fill; microcaps on Nasdaq are the exception where continuous trading is cheaper than the closing auction.

5b. Bacidore & Lipson (draft Jan 2001), "The Effects of Opening and Closing Procedures on the NYSE and Nasdaq". READ (abstract and intro, PDF).
- URL: https://www.darden.virginia.edu/sites/default/files/inline-files/Open_2001_WP.pdf ; same search; fetched 2026-10-01 17:58 UTC; snapshot `bacidore-lipson-2001-abstract.txt`.
- Key sentence: "We find that opening trades on the NYSE are about 20 percent less costly to execute than later comparable trades, while closing trades are slightly more costly. On the Nasdaq, both opening and closing trades are slightly more costly."
- Scope: firms that moved from Nasdaq to NYSE plus size-matched controls, 1990s data, pre-decimalization; old, so not usable for current cost numbers. Relevance (c): opposite ordering to Goyal et al. for NYSE; it is dated and should not override the 2012-2021 evidence.

---------------------------------------------------------------------

## 6. Alpaca documentation and behavior for opg and cls

6a. Placing Orders (time in force)
- URL: https://docs.alpaca.markets/us/docs/orders-at-alpaca ; query `Alpaca docs orders time in force opg cls market on open market on close submission deadline`; fetched 2026-10-01 17:56 UTC (curl, 200). Snapshot: `alpaca-orders-fulltext.txt` (full page text, public docs; navigation noise included).
- Key sentence (verbatim): "OPG orders submitted after 9:28am but before 7:00pm ET will be rejected. OPG orders submitted after 7:00pm will be queued and routed to the following day's opening auction." and for cls: "CLS orders submitted after 3:50pm but before 7:00pm ET will be rejected. CLS orders submitted after 7:00pm will be queued and routed to the following day's closing auction."
- Also: opg is eligible to execute only in the opening auction and unfilled orders are cancelled; "On open/on close orders are routed to the primary exchange"; Order Handling section: Nasdaq cutoff 9:28 for market orders sent to the cross. The page states for crypto that "OPG, fok, day, and CLS are not supported". Scope: Alpaca live brokerage rules for US equities (stocks), no cost numbers.
- Relevance (d): the opg window is 7:00pm ET the previous day (queued) through 9:28am ET; the cls window is until 3:50pm ET; a close-signal-then-open-fill design must submit an OPG order after 7:00pm ET (queued) or before 9:28am ET the next morning; a CLS order must be in by 3:50pm ET, so a signal formed from the 4:00pm close cannot be filled in the same day's closing auction.

6b. Paper Trading
- URL: https://docs.alpaca.markets/us/docs/paper-trading ; fetched 2026-10-01 17:56 UTC; snapshot `alpaca-paper-trading-fulltext.txt`.
- Key sentence: "Instead, the system simulates the order filling based on the real-time quotes." Also: orders fill only when marketable; "Your order quantity is not checked against the NBBO quantities"; partial fills of random size 10% of the time; no dividends simulated; borrow fees listed as "Coming Soon". The page does NOT mention opg or cls at all.
- Relevance (d): the official doc is silent on opg/cls fills in paper; the forum threads below are the only statements found.

6c. Alpaca community forum threads with Alpaca staff statements (fetched via forum JSON 2026-10-01 17:59 UTC; snapshot `alpaca-forum-opg-cls-paper-threads.txt`, per-post text truncated to 1500 chars)
- https://forum.alpaca.markets/t/accurate-opg-and-cls-prices-for-paper-trading/3762 , https://forum.alpaca.markets/t/opg-orders-not-filled-at-open-price-live-trading/14672 , https://forum.alpaca.markets/t/recently-seeing-partial-fills-on-market-opg-order-s-p500-stocks/13906 ; query `Alpaca paper trading market on open opg order fill simulated paper account "opg" ...`.
- Key sentence (Alpaca staff, 2024-03-22): "OPG and CLS ... are simply treated like all other orders ... they fill at the current quote like other orders. They do not fill at the open or close price as one would see in actual live trading." Staff on 2024-05-29: OPG in paper "are simulated exactly like market orders submitted at open except they are cancelled 30 seconds after the open". Staff on 2024-07-20: live OPG fills at "the opening auction price on the primary exchange"; paper OPG "simply fill at the opening quote" and "will not necessarily fill at the auction price in paper trading". Staff 2021-10-18: paper orders always fill at the bid/ask (ask for buys, bid for sells).
- Scope and numbers: user reports, not official studies. 2021-05-18 user test (183 names, 2021-04-06 to 2021-05-12, about 1000 fills, adjusted prices from Tiingo): paper CLS buys filled 12 to 22 bps (99% bootstrap interval) away from the closing price and OPG sells -43 to -31 bps (the user's sign convention; direction is adverse in both cases). Other anecdotes: 0.3% (VIAC), 0.76%, 1.1% (ULTA) gaps; 24-25% of paper orders partially filled over 3 days in May 2024 (Alpaca staff query); partial fill rates above 30% reported on market OPG orders for S&P 500 stocks.
- Relevance (d): paper opg/cls fills are a quote-based market-order simulation, so paper results for an open or close fill model will include half a spread plus quote noise instead of the auction price; this must be modeled before using Alpaca paper fills to validate a 10 bp per side assumption.

---------------------------------------------------------------------

## Left undone / caveats
- The four primary journal papers (1a, 2a, 3a, 4a) were not read; do not cite them for numbers. The formulas and claims attributed to them above are from open secondary sources listed under each.
- The opening-auction cost in bps by size bucket (Goyal et al. Table 5, Figure 5) was not extracted from the page text; only the qualitative statement and the regression slope for microcaps were.
- Beheshti (2018) is vendor-authored; not an independent test of AAF.
