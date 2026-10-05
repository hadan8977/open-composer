SOURCE: https://docs.alpaca.markets/us/docs/options-trading-overview.md
FETCHED_UTC: 2026-10-04T18:47Z
HTTP: 200
---
---
updatedAt: 2026-09-16T18:01:13.000Z
agentTools:
 siteIndex: https://docs.alpaca.markets/llms.txt
 projectIndex: https://docs.alpaca.markets/us/llms.txt
---
# Options Trading Overview
# Initial Options Offering
## Supported
* US listed equities options, all american style
* Level 1-3 options trading
* Fully Disclosed partner relationships
* Automatic account approval process via the API along with SSE events
* Ability for partners to downgrade/disable options trading
* Ability to exercise options via the API
* DNE (do not exercise) via API
* New options specific activities
* Access to options market data (at a cost) or referral to market data partner
## Not supported
* LCT (local currency trading)
* Fractional options
* Extended hours
# Options Enablement
## Enabling Options Trading on a new Account
Per FINRA Rule 2360, each customer account has to be approved for options before the first options trade is made. Once options trading is enabled on a correspondent you can start requesting accounts to be approved for options trading. For existing accounts there will be a few new data points that need to be [patched](https://docs.alpaca.markets/v1.1/reference/patchaccount-1) on the account along with a new options agreement that the customer will need to sign. Below are the new fields that will need to be provided specifically for options.
* Annual Income
* Net Worth
* Liquid Net Worth
* Liquidity Needs
* Investment Experience
* Investment Risk Tolerance
* Investment Objective
* Investment Time Horizon
* Marital Status
* Number of Dependents
Below is an example of a request for opening a new account with options enabled. More details on creating an account can be found [here](https://docs.alpaca.markets/v1.1/reference/createaccount-1)**.**
```json JSON
{
 "enabled_assets": [
 "us_equity",
 "crypto",
 "us_option"
 ],
 "contact": {
 "email_address": "joe+smith+options+25@alpaca.markets",
 "phone_number": "555-666-7788",
 "street_address": [
 "20 N San Mateo Dr"
 ],
 "unit": "Apt 1A",
 "city": "San Mateo",
 "state": "CA",
 "postal_code": "94401",
 "country": "USA"
 },
 "identity": {
 "given_name": "John",
 "middle_name": "Smith",
 "family_name": "Doe",
 "date_of_birth": "1990-01-01",
 "tax_id": "124-55-4321",
 "tax_id_type": "USA_SSN",
 "country_of_citizenship": "USA",
 "country_of_birth": "USA",
 "country_of_tax_residence": "USA",
 "funding_source": [
 "employment_income"
 ],
 "annual_income_min": "10000",
 "annual_income_max": "10000",
 "total_net_worth_min": "10000",
 "total_net_worth_max": "10000",
 "liquid_net_worth_min": "10000",
 "liquid_net_worth_max": "10000",
 "liquidity_needs": "does_not_matter",
 "investment_experience_with_stocks": "over_5_years",
 "investment_experience_with_options": "over_5_years",
 "risk_tolerance": "conservative",
 "investment_objective": "market_speculation",
 "investment_time_horizon": "more_than_10_years",
 "marital_status":"MARRIED",
 "number_of_dependents":5
 },
 "disclosures": {
 "is_control_person": false,
 "is_affiliated_exchange_or_finra": true,
 "is_politically_exposed": false,
 "immediate_family_exposed": false,
 "context": [
 {
 "context_type": "AFFILIATE_FIRM",
 "company_name": "Finra",
 "company_street_address": [
 "1735 K Street, NW"
 ],
 "company_city": "Washington",
 "company_state": "DC",
 "company_country": "USA",
 "company_compliance_email": "compliance@finra.org"
 }
 ]
 },
 "agreements": [
 {
 "agreement": "margin_agreement",
 "signed_at": "2020-09-11T18:09:33Z",
 "ip_address": "185.13.21.99",
 "revision": "16.2021.05"
 },
 {
 "agreement": "account_agreement",
 "signed_at": "2020-09-11T18:13:44Z",
 "ip_address": "185.13.21.99",
 "revision": "16.2021.05"
 },
 {
 "agreement": "customer_agreement",
 "signed_at": "2020-09-11T18:13:44Z",
 "ip_address": "185.13.21.99",
 "revision": "16.2021.05"
 },
 {
 "agreement": "crypto_agreement",
 "signed_at": "2020-09-11T18:13:44Z",
 "ip_address": "185.13.21.99",
 "revision": "04.2021.10"
 },
 {
 "agreement": "options_agreement",
 "signed_at": "2020-09-11T18:13:44Z",
 "ip_address": "185.13.21.99"
 }
 ],
 "documents": [
 {
 "document_type": "identity_verification",
 "document_sub_type": "passport",
 "content": "/9j/Cg==",
 "mime_type": "image/jpeg"
 }
 ],
 "trusted_contact": {
 "given_name": "Jane",
 "family_name": "Doe",
 "email_address": "jane.doe@example.com"
 }
}
```
## Enabling Options Trading on an existing Account
Below are sample requests and responses for enabling options trading on an existing account, using the approval [endpoint](https://docs.alpaca.markets/reference/requestoptionsforaccount).
Example: Account with level 1 requirements requesting for level 1 options trading approval
```json Request
{
 "level": 1 
}
```
```json Response
{
 "id": "43c2f8a9-9e39-48b1-921c-e510dfeeff47",
 "account_id": "492b6297-45fc-4435-abc7-08ab15480b1c",
 "created_at": "2024-05-14T04:34:03.527165162-04:00",
 "updated_at": "2024-05-14T04:34:03.527165162-04:00",
 "requested_level": 1,
 "status": "APPROVED"
}
```
Example: Account with level 1 requirements requesting for level 2 options trading approval
```json Request
{
 "level": 2 
}
```
```json Response
{
 "id": "43c2f8a9-9e39-48b1-921c-e510dfeeff47",
 "account_id": "492b6297-45fc-4435-abc7-08ab15480b1c",
 "created_at": "2024-05-14T04:34:03.527165162-04:00",
 "updated_at": "2024-05-14T04:34:03.527165162-04:00",
 "requested_level": 2,
 "status": "LOWER_LEVEL_APPROVED"
}
```
### Options Approval Statuses
| Status | Description |
| :--------------------- | :--------------------------------------------------------------------------------- |
| `APPROVED` | User has been approved for requested options trading level. |
| `LOWER_LEVEL_APPROVED` | User has been approved for a lower level than the requested options trading level. |
| `PENDING` | Pending manual review |
| `REJECTED` | User has been rejected for requested options trading level. |
### Approval fixtures
Options Approval API supports approval fixtures in the Sandbox environment. You can pass the desired approval level and approval status to test all different scenario of options approval flow (approved, lower\_level\_approved, rejected) to the same approval [endpoint](https://docs.alpaca.markets/reference/requestoptionsforaccount).
Example use cases:
1. Requesting an `APPROVED` status for options trading level 1
```json JSON
{
 "level": 1, 
 "fixtures": {
 "status":"APPROVED"
 }
}
```
2. Requesting an `REJECTED` status for options trading level 2
```json JSON
{
 "level": 2, 
 "fixtures": {
 "status":"REJECTED"
 }
}
```
3. Requesting a `LOWER_LEVEL_APPROVED` status (simulating a flow where level 2 was requested but user is approved for level 2 instead)
```json JSON
{
 "level": 2, 
 "fixtures": {
 "status":"LOWER_LEVEL_APPROVED",
 "level":1
 }
}
```
## Downgrading/disabling Options
Once an account is approved for options trading the customer has the ability to downgrade the options level or disable it altogether. This is done by setting the max\_options\_trading\_level via the trading account configuration [endpoint.](https://docs.alpaca.markets/v1.1/reference/patch-patch-v1-trading-accounts-account_id-account-configurations-1)
Once the max options trading level is set the options trading level on the trading account endpoint will get upgraded to the value set by the user. Note the options trading level will always be the same or lower than the options approved level. Below is an example of a user being approved for level 2 but downgrading to level 1.
```json
{
 ...
 "options_approved_level": 2,
 "options_trading_level": 1,
 ...
}
```
# Trading
## Trading Overview
When placing orders via the [orders api](https://docs.alpaca.markets/v1.1/reference/createorderforaccount-1) for options below is what is supported and what is not supported
### Supported
* Options symbol
* Time in force of day
* Market and limit order types
* Ability to replace and cancel orders
* Level 1 - 3 option strategies
### Not supported
* Extended hours
* Fractional or notional order support
## Trading Levels
Alpaca supports the below options trading levels.
<Table align={["left","left","left"]}>
 <thead>
 <tr>
 <th>
 Level
 </th>
 <th>
 Supported Trades
 </th>
 <th>
 Validation
 </th>
 </tr>
 </thead>
 <tbody>
 <tr>
 <td>
 0
 </td>
 <td>
 - Options trading is disabled
 </td>
 <td>
 - NA
 </td>
 </tr>
 <tr>
 <td>
 1
 </td>
 <td>
 - Sell a covered call
 - Sell cash-secured put
 </td>
 <td>
 - User must own sufficient underlying shares
 - User must have sufficient options buying power
 </td>
 </tr>
 <tr>
 <td>
 2
 </td>
 <td>
 - Level 1 Strategies
 - Buy a call
 - Buy a put
 </td>
 <td>
 - User must have sufficient options buying power
 </td>
 </tr>
 <tr>
 <td>
 3
 </td>
 <td>
 - Level 1 and 2 Strategies
 - Buy a call spread
 - Buy a put spread
 </td>
 <td>
 User must have sufficient options buying power
 </td>
 </tr>
 </tbody>
</Table>
### Trading Level Validation
If a user tries to trade a strategy above their level this will result in an error message. Below is an example of a user who is approved for level 1 trying to place a level 2 options trade.
```json
{
 "code": 40310000,
 "message": "account not eligible for level2 options trading"
}
```
## Asset Master
Similar to the asset master for securities and crypto there is an options contract [endpoint](https://docs.alpaca.markets/v1.1/reference/get-options-contracts-1) which will return all the options contract for an underlying symbol. Below is a sample
```json
{
 "id": "1fb904df-961a-4a07-a924-53a437626db2",
 "symbol": "AAPL240223C00095000",
 "name": "AAPL Feb 23 2024 95 Call",
 "status": "active",
 "tradable": true,
 "expiration_date": "2024-02-23",
 "root_symbol": "AAPL",
 "underlying_symbol": "AAPL",
 "underlying_asset_id": "b0b6dd9d-8b9b-48a9-ba46-b9d54906e415",
 "type": "call",
 "style": "american",
 "strike_price": "95",
 "size": "100",
 "open_interest": "12",
 "open_interest_date": "2024-02-22",
 "close_price": "89.35",
 "close_price_date": "2024-02-22"
 }
```
## Order Examples
**Buying a call**
```json
{ 
 "symbol": "PTON240126C00000500", 
 "qty": "1", 
 "side":"buy", 
 "type": "market", 
 "time_in_force": "day" 
}
```
**Buying a put**
```json
{ 
 "symbol": "TSLA240126P00210000", 
 "qty": "1", 
 "side": "buy", 
 "type": "market", 
 "time_in_force": "day" 
}
```
**Selling a covered call**
```json
{ 
 "symbol": "AAPL240126C00050000", 
 "qty": "1", 
 "side": "sell", 
 "type": "market", 
 "time_in_force": "day" 
}
```
**Selling a cash secured put**
```json
{ 
 "symbol": "QS240126P00006500", 
 "qty": "1", 
 "side": "sell", 
 "type": "market", 
 "time_in_force": "day" 
}
```
## Buying Power Checks
With options we introduce a new field on the[ trading account endpoint](https://docs.alpaca.markets/v1.1/reference/gettradingaccount-1) called options\_buying\_power which is evaluated when trying to open new options positions.
For both **buying a call** or **buying a put** sufficient buying power is necessary to pay for the premium of the contract otherwise an error will occur as shown below.
```json
{
"options_buying_power": "7267.84",
"code": 40310000,
"cost_basis": "38000",
"message": "insufficient options buying power"
}
```
For **Selling Covered Call** you need to have enough stocks as collateral otherwise the order will error out as shown below.
```json
 {
 "available_qty": "0",
 "code": 40310000,
 "message": "insufficient underlying qty available for covered call (required: 100, available: 0)",
 "required_qty": "100",
 "symbol": "AAPL240126C00050000",
 "underlying_asset_id": "b0b6dd9d-8b9b-48a9-ba46-b9d54906e415"
}
```
For **selling cash secured put** you will need enough buying power to pay for the underlying stock minus the premium that would be received otherwise the order will error out as shown below
```json
{
 "buying_power": "9395",
 "code": 40310000,
 "message": "insufficient options buying power for cash-secured put (required: 20310, available: 9395)",
 "required_options_buying_power": "20310"
}
```
# Positions
Option positions will show up like any other position in the positions endpoint. Below is an example of an options position.
```json
{
 "asset_id": "fe4f43e5-60a4-4269-ba4c-3d304444d58b",
 "symbol": "PTON240126C00000500",
 "exchange": "",
 "asset_class": "us_option",
 "asset_marginable": true,
 "qty": "2",
 "avg_entry_price": "6.05",
 "side": "long",
 "market_value": "1068",
 "cost_basis": "1210",
 "unrealized_pl": "-142",
 "unrealized_plpc": "-0.1173553719008264",
 "unrealized_intraday_pl": "-142",
 "unrealized_intraday_plpc": "-0.1173553719008264",
 "current_price": "5.34",
 "lastday_price": "5.34",
 "change_today": "0",
 "qty_available": "2"
}
```
# Post Trade
## Exercising
As the buyer of an option (call or put), the holder has the right, but not the obligation, to buy or sell the option's underlying security at a specified price on or before a specified date in the future. If the holder decides to act on those rights they are choosing to exercise. An option can be exercised via the exercise [endpoint](https://docs.alpaca.markets/v1.1/reference/optionexercise-1) and instructions for DNE (do not exercise) instructions can be supplied via [Do not exercise](https://docs.alpaca.markets/reference/optiondonotexercise-1) endpoint. Note exercise requests will be processed instantly and requests sent outside of market hours will be rejected. When exercising there will be 2 new activities per exercise which are:
* **OPEXC** - removes the options position as a result of exercising
* **OPTRD** - trading activity that is paired with the exercising
### Exercising Call
A long call exercise results in **buying the underlying stock** at the strike price. Below is an example of this.
```json
{
 "id": "20240227000000000::197118f0-afd8-4adb-b154-167f4a87b1f5",
 "account_id": "21c36b57-2304-4e5b-8364-8effbcba853e",
 "activity_type": "OPEXC",
 "date": "2024-02-27",
 "net_amount": "0",
 "description": "Option Exercise",
 "symbol": "QS240301C00006500",
 "qty": "-1",
 "status": "executed"
},
{
 "id": "20240227000000000::aa97cbc4-5163-49ab-b832-682a3a3e85bb",
 "account_id": "21c36b57-2304-4e5b-8364-8effbcba853e",
 "activity_type": "OPTRD",
 "date": "2024-02-27",
 "net_amount": "-650",
 "description": "Option Trade",
 "symbol": "QS",
 "qty": "100",
 "price": "6.5",
 "status": "executed"
}
```
### Exercising Put
A long put exercise results in **selling the underlying stock** at the strike price. Below is an example of this.
```json JSON
{
 "id": "20240227000000000::f62ee8f5-0279-4e81-9bd1-4ef197c7b2f3",
 "account_id": "21c36b57-2304-4e5b-8364-8effbcba853e",
 "activity_type": "OPEXC",
 "date": "2024-02-27",
 "net_amount": "0",
 "description": "Option Exercise",
 "symbol": "QS240301P00006500",
 "qty": "-1",
 "status": "executed"
},
{
 "id": "20240227000000000::74e1db8e-9316-4dcf-b69c-50f51427b7c1",
 "account_id": "21c36b57-2304-4e5b-8364-8effbcba853e",
 "activity_type": "OPTRD",
 "date": "2024-02-27",
 "net_amount": "650",
 "description": "Option Trade",
 "symbol": "QS",
 "qty": "-100",
 "price": "6.5",
 "status": "executed"
}
```
## Assignment
When selling an options contract (call or put) the user collects a premium but in turn takes on the obligation to buy or sell the stock at the agreed upon strike price if assigned. It is important to note that the OCC assigns a random account and sellers of contracts can be assigned overnight. When assigned there will be 2 new activities per assignment which are:
* **OPASN** - removes the options position as a result of assignment
* **OPTRD** - trading activity that is paired with the assignment
### Call Assignment
For call options, the seller takes on the **obligation to sell** the stock at the agreed upon strike price. Below is an example of activities that result as a result of a call assignment
```json
 {
 "id": "20240301000000000::001140db-3947-456b-aefc-253861fb65df",
 "account_id": "21c36b57-2304-4e5b-8364-8effbcba853e",
 "activity_type": "OPASN",
 "date": "2024-03-01",
 "net_amount": "0",
 "description": "",
 "symbol": "QS240301C00004500",
 "qty": "1",
 "status": "executed"
}
{
 "id": "20240301000000000::a88c089f-a8c3-4672-9b68-2f6f2d05e914",
 "account_id": "21c36b57-2304-4e5b-8364-8effbcba853e",
 "activity_type": "OPTRD",
 "date": "2024-03-01",
 "net_amount": "450",
 "description": "Option Trade",
 "symbol": "QS",
 "qty": "-100",
 "price": "4.5",
 "status": "executed"
}
```
### Put Assignment
For put options, the seller takes on the **obligation to buy** the stock at the agreed upon strike price. Below is an example of activities that result as a result of a put assignment
```json
{
 "id": "20240301000000000::fcd92e5c-46e4-4c6e-8866-d56cd7d2bde2",
 "account_id": "21c36b57-2304-4e5b-8364-8effbcba853e",
 "activity_type": "OPASN",
 "date": "2024-03-01",
 "net_amount": "0",
 "description": "",
 "symbol": "QS240301P00009000",
 "qty": "1",
 "status": "executed"
}
{
 "id": "20240301000000000::1e1c2804-ce68-4516-9fa4-62d49b14c334",
 "account_id": "21c36b57-2304-4e5b-8364-8effbcba853e",
 "activity_type": "OPTRD",
 "date": "2024-03-01",
 "net_amount": "-900",
 "description": "Option Trade",
 "symbol": "QS",
 "qty": "100",
 "price": "9",
 "status": "executed"
}
```
## Expiration
Unlike stocks, option contracts have an expiration date. If the user does not close out their position or exercise their options (if they have the buying power to support the exercise), Alpaca will need to potentially take action on it for risk management purposes based on the criteria described below.
* Starting at 3:30 pm EST on the date of expiration, Alpaca continuously evaluates any open positions that expire that day and stops accepting new orders to open/extend any positions.
* If the position for a long call or put **is ITM (in the money)** by .01 or more, Alpaca checks if the account has enough buying power to exercise in the case of a call or enough shares in the case of a put
 * If there is **enough buying power or shares** Alpaca will not liquidate the options and will let the option auto-exercise.
 * If there is **not enough buying power or shares**, then Alpaca will liquidate while it’s still ITM
* If the position **is for a covered call or cash secured put and ITM** by .01 or more **Alpaca will automatically assign after close on date of expiry**
* If the position **is not ITM** in other words it’s **ATM (at the money)** or **OTM (out of the money)**, Alpaca may skip it and it will expire after close as shown in the examples below. (Note that positions slightly OTM may also be liquidated depending on market and underlying conditions. Alpaca will take into consideration fast moving markets and/or fast stocks that may be moving from ITM and OTM throughout the day. There may be instances where OTM positions are also closed out.)
### Call Expiration
```json
{
 "id": "20240301000000000::31ff5d4c-a608-43bb-8e59-678a96a4a42c",
 "account_id": "21c36b57-2304-4e5b-8364-8effbcba853e",
 "activity_type": "OPEXP",
 "date": "2024-03-01",
 "net_amount": "0",
 "description": "Option Expiry",
 "symbol": "QS240301C00010500",
 "qty": "-1",
 "status": "executed"
}
```
### Put Expiration
```json JSON
{
 "id": "20240301000000000::4bd8c683-0b2c-489f-9df9-1243ff621648",
 "account_id": "21c36b57-2304-4e5b-8364-8effbcba853e",
 "activity_type": "OPEXP",
 "date": "2024-03-01",
 "net_amount": "0",
 "description": "Option Expiry",
 "symbol": "QS240301P00000500",
 "qty": "-1",
 "status": "executed"
}
```
# Market Data
Alpaca provides access to options market data (at a cost) in the same user-friendly format it does for stocks and crypto. Additionally, we can refer partners to external data vendors with whom Alpaca has a close relationship if necessary.
| Endpoint | Noteste |
| :----------------------------------------------------------------------------- | :--------------------------------------------------- |
| [Latest Quotes](https://docs.alpaca.markets/v1.1/reference/optionlatestquotes) | Latest quotes. Supports multiple symbols |
| [Latest Trades](https://docs.alpaca.markets/v1.1/reference/optionlatesttrades) | Latest trades. Supports multiple symbols |
| [Historical Trades](https://docs.alpaca.markets/v1.1/reference/optiontrades) | Historical trades. Supports multiple symbols |
| [Snapshots](https://docs.alpaca.markets/v1.1/reference/optionsnapshots) | Combine quotes and trades for multiple symbols |
| [Option chain](https://docs.alpaca.markets/reference/optionchain) | Query option chain by the underlying (stock) symbols |
| [Historical bars](https://docs.alpaca.markets/v1.1/reference/optionbars) | Historical bars.Supports multiple symbol |
# Error Responses
Options order operations (**submit**, **cancel**, **replace**, **exercise**, and **do-not-exercise**) can return the errors listed below. Each error is delivered as a JSON body with a numeric `code` and a `message`, alongside the HTTP status. Example: 
```json
{
 "code": 40310000,
 "message": "insufficient options buying power (required: 20310, available: 9395)"
}
```
<Callout icon="📘" theme="info">
 The `message` strings can change without notice. The numeric `code` and HTTP status are the stable contract. Placeholders in curly braces (`{symbol}`, `{required}`, `{available}`, `{status}`) are substituted at runtime.
</Callout>
The tables below are **options-specific**. Generic order errors (buying power, market closed, malformed JSON, rate-limit, etc.) documented under [Working with /orders](https://docs.alpaca.markets/us/docs/working-with-orders) also apply to options.
<details>
<summary><b>Submit: single-leg</b></summary>
Returned by [Create an Order for an Account](https://docs.alpaca.markets/us/reference/createorderforaccount) when the payload's `symbol` is an option contract.
| HTTP | Code | Message |
| :--: | ---------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| 403 | `40310000` | `account not authorized to trade options` |
| 403 | `40310000` | `account not eligible to trade long option contracts` |
| 403 | `40310000` | `account not eligible to trade options: {symbol}` |
| 403 | `40310000` | `account not eligible to trade spreads or uncovered contracts` |
| 403 | `40310000` | `account not eligible to trade uncovered option contracts` |
| 403 | `40310000` | `active assignment lock on {symbol}, cannot close all long options` |
| 403 | `40310000` | `commission not allowed for account` |
| 403 | `40310000` | `exceeded account limit for contracts expiring today (requested: {q}, held+open: {h}, limit: {l})` |
| 403 | `40310000` | `insufficient options buying power (required: {required}, available: {available})` |
| 403 | `40310000` | `negative commission is prohibited` |
| 422 | `42210000` | `complex orders not supported for options trading` |
| 422 | `42210000` | `contract "{symbol}" expires soon, unable to open new positions` |
| 422 | `42210000` | `contract "{symbol}" is expired` |
| 422 | `42210000` | `contract "{symbol}" is not active` |
| 422 | `42210000` | `contract "{symbol}" is not tradable` |
| 422 | `42210000` | `contract "{symbol}" not found` |
| 422 | `42210000` | `extended hours is not supported for options trading` |
| 422 | `42210000` | `invalid contract` |
| 422 | `42210000` | `invalid option order_type` |
| 422 | `42210000` | `invalid option time_in_force` |
| 422 | `42210000` | `invalid options order_type` |
| 422 | `42210000` | `invalid order type for options trading` |
| 422 | `42210000` | `notional orders are not supported for options trading` |
| 422 | `42210000` | `options market orders are only allowed during market hours` |
| 422 | `42210000` | `options order notional is {n} must be <= {limit}` |
| 422 | `42210000` | `options order qty must be <= {max}` |
| 422 | `42210000` | `order_time_in_force provided not supported for options trading` |
| 422 | `42210000` | `orders for morning-expiration index options cannot be placed after market close when expiration is the next trading day (contract "{symbol}")` |
| 422 | `42210000` | `orders for morning-expiration index options cannot be placed on expiration day (contract "{symbol}")` |
| 422 | `42210000` | `position intent mismatch, inferred: {inferred}, specified: {specified}` |
| 422 | `42210000` | `qty must be integer for options trading` |
| 422 | `42210000` | `swap_fee_bps is not allowed for options trading` |
| 422 | `42210000` | `underlying asset "{symbol}" not found` |
</details>
<details>
<summary><b>Submit: multi-leg (MLeg)</b></summary>
Returned by [`POST /v2/orders`](https://docs.alpaca.markets/us/reference/postorder) when the payload contains an `order_class: "mleg"` and one or more option `legs`. See also [Options Level 3 Trading](https://docs.alpaca.markets/us/docs/options-level-3-trading).
| HTTP | Code | Message |
| :--: | ---------- | ------------------------------------------------------------------------------------ |
| 403 | `40310000` | `submit mleg order is disabled` |
| 422 | `42210000` | `asset not found for {symbol}` |
| 422 | `42210000` | `equity legs are allowed only with a corresponding amount of call contracts` |
| 422 | `42210000` | `European-style option legs in a multi-leg order must have the same expiration date` |
| 422 | `42210000` | `invalid limit price` |
| 422 | `42210000` | `invalid time in force` |
| 422 | `42210000` | `leg.{i} position intent is required` |
| 422 | `42210000` | `limit price is only valid for limit orders` |
| 422 | `42210000` | `limit price is required for limit orders` |
| 422 | `42210000` | `rolling contracts ambiguity` |
| 422 | `42210000` | `underlying asset mismatch: {underlying} != {asset}` |
</details>
<details>
<summary><b>Cancel</b></summary>
Returned by [`DELETE /v2/orders/{order_id}`](https://docs.alpaca.markets/us/reference/deleteorderforaccount).
| HTTP | Code | Message |
| :--: | ---------- | ---------------------------------------- |
| 403 | `40310000` | `cancel mleg order is disabled` |
| 422 | `42210000` | `leg order is already in {status} state` |
</details>
<details>
<summary><b>Replace</b></summary>
Returned by [`PATCH /v2/orders/{order_id}`](https://docs.alpaca.markets/us/reference/replaceorderforaccount).
| HTTP | Code | Message |
| :--: | ---------- | ----------------------------------------- |
| 403 | `40310000` | `replace mleg order is disabled` |
| 422 | `42210000` | `cannot replace order in {status} status` |
| 422 | `42210000` | `order already replaced` |
| 422 | `42210000` | `order chain not fully replaced` |
| 422 | `42210000` | `order parameters are not changed` |
| 422 | `42210000` | `qty must be > filled_qty` |
</details>
<details>
<summary><b>Exercise</b></summary>
Returned by the options exercise endpoint. See [Options Trading Overview → Exercising](https://docs.alpaca.markets/us/docs/options-trading-overview#exercising).
| HTTP | Code | Message |
| :--: | ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 403 | `40310000` | `cannot exercise position marked as do-not-exercise` |
| 403 | `40310000` | `cannot exercise position with dne_qty greater than or equal to position qty (dne_qty: {dne_qty}, position qty: {position_qty})` |
| 403 | `40310000` | `early exercise is not allowed for European-style options` |
| 403 | `40310000` | `exercise requests are not accepted after market close until midnight` |
| 403 | `40310000` | `insufficient cash available (required: {required}, available: {available})` |
| 403 | `40310000` | `insufficient cash available - margin call protection (required: {required}, available: {available})` |
| 403 | `40310000` | `insufficient qty available (requested: {requested_qty}, available: {available_qty})` |
| 403 | `40310000` | `insufficient qty available to exercise after accounting for partial do-not-exercise (requested: {requested_qty}, dne_qty: {dne_qty}, available: {available_qty})` |
| 403 | `40310000` | `insufficient regt buying power (required: {required}, available: {available})` |
| 403 | `40310000` | `insufficient underlying qty available for deliverable: {symbol} (requested: {requested_qty}, available: {available_qty})` |
| 403 | `40310000` | `no qty available to exercise` |
| 403 | `40310000` | `you are attempting to exercise a non-standard option contract, please contact support@alpaca.markets to complete this request` |
| 403 | `40310000` | `you are attempting to exercise an out of the money option contract, please contact support@alpaca.markets to complete this request` |
| 404 | `40410000` | `long position not found: {symbol}` |
| 422 | `42210000` | `exercise commission not allowed for account` |
| 422 | `42210000` | `negative exercise commission is prohibited` |
| 422 | `42210000` | `qty must be > 0` |
| 422 | `42210000` | `symbol missing` |
</details>
<details>
<summary><b>Do Not Exercise (DNE)</b></summary>
Returned by the do-not-exercise endpoint. See [Options Trading Overview → Exercising](https://docs.alpaca.markets/us/docs/options-trading-overview#exercising).
| HTTP | Code | Message |
| :--: | ---------- | ----------------------------------------------------------------------------- |
| 403 | `40310000` | `dne requests are not accepted after {time}` |
| 403 | `40310000` | `dne requests are only accepted on the expiration day of the option contract` |
| 403 | `40310000` | `do-not-exercise is not applicable for European-style options` |
| 404 | `40410000` | `long position not found: {symbol}` |
| 422 | `42210000` | `symbol missing` |
</details>
***
<Callout icon="⚠️" theme="warn">
 Options trading is not suitable for all investors due to its inherent high risk, which can potentially result in significant losses. Please read [Characteristics and Risks of Standardized Options ](https://www.theocc.com/company-information/documents-and-archives/options-disclosure-document)before investing in options.
</Callout>