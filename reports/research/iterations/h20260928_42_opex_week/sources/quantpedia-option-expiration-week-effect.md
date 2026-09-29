# Quantpedia: Option-Expiration Week Effect

URL: https://quantpedia.com/strategies/option-expiration-week-effect
Fetched via WebFetch: 2026-09-29 (this session)
Source paper cited by the page: Stivers & Sun (2013), "Returns and option
activity over the option-expiration week for S&P 100 stocks", Journal of
Banking & Finance.

## Rule
Long-only. Go long S&P 100 stocks during the option-expiration week (the
week containing the month's 3rd Friday, standard monthly options expiry);
stay in cash the rest of the month.

Verbatim (WebFetch extraction of the page's own rule description): "go long
S&P 100 stocks during the option-expiration week and stay in cash during
other days."

## Backtest (1988-2010, per the page)
- Annualized return: 9.3%/yr (combining 6.3% from the 12 expiration weeks
  plus cash returns the rest of the year)
- Sharpe ratio: 0.61
- Volatility: ~8.7% (estimated)
- Max drawdown: -15.14%

## Mechanism
Delta-hedge rebalancing by option market makers: during the expiration
week, market makers reduce net short-stock hedge positions built against
long call positions, providing a mild tailwind to the underlying stocks.

## Disclosed caveats
- No updated or recent-period (post-2010) performance figure on the page.
- No out-of-sample or forward-tracking statement.
- Original sample (1988-2010) predates: the 2010s+ growth of 0DTE/weekly
  options, changes in market-maker inventory management, and the modern
  liquid index-ETF landscape this iteration tests (SPY/QQQ/DIA/IWM).
