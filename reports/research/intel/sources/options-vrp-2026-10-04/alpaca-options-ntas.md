SOURCE: https://docs.alpaca.markets/us/docs/non-trade-activities-for-option-events.md
FETCHED_UTC: 2026-10-04T18:47Z
HTTP: 200
---
---
updatedAt: 2025-09-24T23:31:26.000Z
agentTools:
 siteIndex: https://docs.alpaca.markets/llms.txt
 projectIndex: https://docs.alpaca.markets/us/llms.txt
---
# Non-Trade Activities for Option Events
This page provides an overview of new NTAs for options-specific events
# Option Exercise
```
[
 {
 "id": "20190801011955195::5f596936-6f23-4cef-bdf1-3806aae57dbf",
 "activity_type": "OPEXC",
 "date": "2023-07-21",
 "net_amount": "0",
 "description": "Option Exercise",
 "symbol": "AAPL230721C00150000",
 "qty": "-2",
 "status": "executed"
 },
 {
 "id": "20190801011955195::5f596936-6f23-4cef-bdf1-3806aae57dbf",
 "activity_type": "OPTRD",
 "date": "2023-07-21",
 "net_amount": "-30000",
 "description": "Option Trade",
 "symbol": "AAPL",
 "qty": "200",
 "price": "90",
 "status": "executed"
 }
]
```
The exercise event (OPEXC) is applicable to 2 contracts, and the corresponding trade (OPTRD) represents 200 of the underlying shares being purchased at a per-share amount of $150 (strike price).
# Option Assignment
```
[
 {
 "id": "20190801011955195::5f596936-6f23-4cef-bdf1-3806aae57dbf",
 "activity_type": "OPASN",
 "date": "2023-07-01",
 "net_amount": "0",
 "description": "Option Assignment",
 "symbol": "AAPL230721C00150000",
 "qty": "2",
 "status": "executed"
 },
 {
 "activity_type": "OPTRD",
 "id": "20190801011955195::5f596936-6f23-4cef-bdf1-3806aae57dbf",
 "date": "2023-07-01",
 "net_amount": "30000",
 "description": "Option Trade",
 "symbol": "AAPL",
 "qty": "-200",
 "price": "150",
 "status": "executed"
 }
]
```
The assignment event (OPASN) is applicable to 2 contracts, and the corresponding trade (OPTRD) represents 200 of the underlying shares being sold at a per-share amount of $150 (strike price).
# ITM Option Expiry
In the event of an in-the-money (ITM) option reaching expiration without being designated as "Do Not Exercise" (DNE), the Alpaca system will automatically initiate the exercise process on behalf of the user. This process mirrors the Exercise event described earlier. In cases where there is insufficient buying power or underlying positions to facilitate the exercise, the system will generate an automated order for the liquidation of the position.
# OTM Option Expiry
```
[
 {
 "id": "20190801011955195::5f596936-6f23-4cef-bdf1-3806aae57dbf",
 "activity_type": "OPEXP",
 "date": "2023-07-21",
 "net_amount": "0",
 "description": "Option Expiry",
 "symbol": "AAPL230721C00150000",
 "qty": "-2",
 "status": "executed"
 }
]
```
When a contract expires OTM, the Alpaca system will flatten the position and no further action is taken.