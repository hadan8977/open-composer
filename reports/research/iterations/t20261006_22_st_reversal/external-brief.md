# External brief: how others do short-horizon residual reversal, what we copy, what we change

Sources are in `reports/research/intel/sources/st-reversal-2026-10-06/` (index there) and, for the P1 reuse set, `reports/research/intel/sources/mid-frequency-2026-10-04/`. Only sourced facts are listed.

## What others do

- **Avellaneda and Lee (2010)** [`avellaneda-lee-statarb.txt`]: US stocks above 1 bn market cap, daily end-of-day data, 60-day window to fit the residual process, residuals from sector ETFs or a PCA factor model (fixed 15 or a variable number), enter at 1.25 sd, exit at 0.5 sd, slippage 5 bp per trade, dollar-neutral market-neutral book. PCA strategies: Sharpe 1.44 net over 1997-2007 but only 0.9 in 2003-2007; ETF strategies 1.1; signals in "trading time" (volume-adjusted, tilting toward low-volume moves) reach 1.51 in 2003-2007. They state the strategy works better when few eigenvectors explain 50% of variance.
- **Blitz, Huij, Lansdorp, Verbeek (2013)** [abstract only]: residual (Fama-French) reversal earns about twice the risk-adjusted return of conventional reversal and is profitable net of costs even among large caps after 1990. Monthly.
- **Da, Liu, Schaumburg (2014)** [`da-liu-schaumburg-closer-look.txt`]: the part of the return not explained by fundamental news reverses; monthly Sharpe 0.52 (residual-based) vs 0.14; the effect still exists among large stocks in recent years once industry momentum is controlled for.
- **Nagel (2012)** [`nagel-evaporating-liquidity-w17653.txt`]: reversal returns are liquidity-provision compensation, strongly predictable with VIX; conditional Sharpe rises with VIX.
- **Medhat and Schmeling (2022)** [search summary]: reversal among low-turnover stocks, momentum among high-turnover stocks (1963-2018). **Lou, Polk, Skouras (2019)** [search summary + P1 snapshot]: reversal and momentum profits sit overnight or intraday with opposite signs. **Farkas and Neszveda (2024)** [`efma2024-underreaction.txt`]: reversal profit lives in stocks that under-react to industry information.
- **Deep models** (P1 snapshots): DLSA Sharpe half-life about 7 sessions, about 1.5 with multi-day holding (550 stocks, to 2016, 5 bp + 1 bp short fee); Attention Factors 2.3 net with costs in the objective, a simple PCA model about 1.5, the OU-threshold residual rule negative at 5 bp (500 stocks to 2021).
- **Post-publication, independent, recent**: the open-source `equity-statarb` project (CRSP daily 2000-2024, survivorship-free, one-day hold, 7 bp flat): in-sample 2000-2018 gross 0.90 / net 0.34; out-of-sample 2019-2024 gross 0.23 / net -0.15, breakeven 4.2 bp; alpha in short positions and low-priced names; PCA(15) variant no gross edge out-of-sample (-0.07) [`equity-statarb-github-summary.md`, README summary only].
- **Capacity**: Frazzini-Israel-Moskowitz (P1 snapshot): reversal does not survive costs above about 9 bn USD of capital in the US; our size (300,000 USD) is far below.

## What we copy, and what we change

- Copy: residual construction from Avellaneda-Lee (PCA of standardised returns, 252-session window instead of their 60-day fit of the OU process; top 10 components), the beta and industry residuals of Blitz and Da-Liu-Schaumburg, the turnover split of Medhat-Schmeling (low-turnover half), the VIX conditioning of Nagel, 5 bp-class costs replaced by our measured model.
- Change: (a) rank-weighted quintile books held as 1/H overlapping daily batches instead of OU-threshold entries and exits (the threshold rule loses to turnover at 5 bp in the Attention-Factors comparison); (b) costs are the measured half spread by liquidity plus square-root impact plus borrow, not flat; (c) shorts only in an easy-to-borrow proxy (the open-source negative says alpha sits in hard-to-borrow, low-priced shorts); (d) two model rankers (ridge, LightGBM) on residual, turnover, overnight/intraday and news features instead of a transformer.
- What the sources do not give: any daily residual-reversal number for 2024-2026 with measured costs; that is what the dossier measures. The closest recent independent evidence is negative, so the cheapest test is a gross-first screen (Stage A).

## Not found

No 2024+ independent live record or replication of a daily US-equity residual-reversal book; four GitHub-oriented queries returned the one project above and library code (Hudson and Thames ArbitrageLab PCA approach, QuantConnect tutorials) without out-of-sample cost-net results.
