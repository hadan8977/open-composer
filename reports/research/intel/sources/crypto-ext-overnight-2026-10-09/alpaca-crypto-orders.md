URL: https://docs.alpaca.markets/us/docs/crypto-orders.md
FETCHED_UTC: 2026-10-05T07:29Z
HTTP: 200
-----
---
updatedAt: 2025-09-24T23:11:20.000Z
agentTools:
  siteIndex: https://docs.alpaca.markets/llms.txt
  projectIndex: https://docs.alpaca.markets/us/llms.txt
---

# Crypto Orders

You can submit crypto orders through the traditional orders API endpoints (`POST/orders`).

* The following order types are supported: `market`, `limit` and `stop_limit`
* The following `time_in_force` values are supported: `gtc`, and `ioc`
* We accept fractional orders as well with either `notional` or `qty` provided

You can submit crypto orders for a any supported crypto pair via API, see the below cURL POST request.

```curl
curl --request POST 'https://paper-api.alpaca.markets/v2/orders' \
--header 'Apca-Api-Key-Id: <KEY>' \
--header 'Apca-Api-Secret-Key: <SECRET>' \
--header 'Content-Type: application/json' \
--data-raw '{
  "symbol": "BTC/USD",
  "qty": "0.0001",
  "side": "buy",
  "type": "market",
  "time_in_force": "gtc"
}'
```

The above request submits a market order via API to buy 0.0001 BTC with USD (BTC/USD pair) that is good till end of day.