SOURCE: https://docs.alpaca.markets/us/docs/regulatory-fees.md
FETCHED_UTC: 2026-10-04T18:47Z
HTTP: 200
---
---
updatedAt: 2025-10-03T17:53:13.000Z
agentTools:
 siteIndex: https://docs.alpaca.markets/llms.txt
 projectIndex: https://docs.alpaca.markets/us/llms.txt
---
# Regulatory Fees
## FEE types and effective rates
The following FEEs are applied to options trades.
| Type | When | Charged By |
| :----------------------------- | :---------------------------------- | :---------------- |
| Trading Activity Fee (TAF) | Sells only | FINRA |
| Options Regulatory Fee (ORF) | Buys and sells | Options Exchanges |
| Options Clearing Corporation | Buys and sells up to 2750 contracts | OCC |
| Consolidated Audit Trail (CAT) | Buys and sells | FINRA-CAT |
The following FEEs are applied to equities.
| Type | When | Charged By |
| :----------------------------- | :------------- | :--------- |
| Trading Activity Fee (TAF) | Sells only | FINRA |
| Consolidated Audit Trail (CAT) | Buys and sells | FINRA-CAT |
For our current effective rates, please refer to our brokerage fee schedule available here: <Anchor label="https://alpaca.markets/disclosures" target="_blank" href="https://alpaca.markets/disclosures"><https://alpaca.markets/disclosures></Anchor>
## How Fees are charged and reflected in account balances
1. Alpaca's trading system keeps track of the accrued FEE amounts intraday and deducts the pending amounts from account balances.
2. At EOD, we charge each account the fees for that trading day
3. We round up total fees based on the currency’s precision to the nearest decimal place.
 For example, USD has a precision of 0.01. If the total fee is calculated as 0.00083, it will be rounded up to 0.01 (i.e., 1 penny).
## Additional resources
* <https://www.finra.org/rules-guidance/rulebooks/industry/trading-activity-fee>
* <https://www.catnmsplan.com/>
* <https://www.sec.gov/newsroom/press-releases/2024-47>