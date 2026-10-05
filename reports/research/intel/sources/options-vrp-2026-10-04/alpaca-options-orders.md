SOURCE: https://docs.alpaca.markets/us/docs/options-orders.md
FETCHED_UTC: 2026-10-04T18:47Z
HTTP: 200
---
---
updatedAt: 2025-09-24T23:31:25.000Z
agentTools:
 siteIndex: https://docs.alpaca.markets/llms.txt
 projectIndex: https://docs.alpaca.markets/us/llms.txt
---
# Options Orders
This page provides examples of valid order payloads
# Tier 1 Orders
## Sell a Covered Call
```
{
 "symbol": "AAPL231201C00195000",
 "qty": "2",
 "side": "sell",
 "type": "limit",
 "limit_price": "1.05",
 "time_in_force": "day"
}
```
Note, the account must have an existing position of 200 shares of AAPL as the order is for 2 contracts, and each option contract is for 100 shares of underlying.
## Sell a Cash-Secured Put
```
{
 "symbol": "AAPL231201P00175000",
 "qty": "1",
 "side": "sell",
 "type": "market",
 "time_in_force": "day"
}
```
Note, the account must have sufficient buying power. The account must have ($175 strike) x (100 shares) x (1 contract) = $17,500 USD buying power available.
# Tier 2 Orders
## Buy a Call
```
{
 "symbol": "AAPL240119C00190000",
 "qty": "1",
 "side": "buy",
 "type": "market",
 "time_in_force": "day"
}
```
The account must have sufficient buying power to afford the call option. If the market order is executed at $5.10, the account must have ($5.10 execution price) x (100 shares) x (1 contract) = $510.00 USD buying power.
## Buy a Put
```
{
 "symbol": "AAPL240119P00170000",
 "qty": "1",
 "side": "buy",
 "type": "market",
 "time_in_force": "day"
}
```
The account must have sufficient buying power to afford purchasing put option. If the market order is executed at $1.04, the account must have ($1.04 execution price) x (100 shares) x (1 contract) = $104.00 USD buying power.