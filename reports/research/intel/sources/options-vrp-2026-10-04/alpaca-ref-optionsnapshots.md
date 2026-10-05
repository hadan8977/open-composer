SOURCE: https://docs.alpaca.markets/us/reference/optionsnapshots.md
FETCHED_UTC: 2026-10-04T18:47Z
HTTP: 200
---
---
updatedAt: 2026-05-27T17:58:03.000Z
agentTools:
 siteIndex: https://docs.alpaca.markets/llms.txt
 projectIndex: https://docs.alpaca.markets/us/llms.txt
---
# Snapshots
The snapshots endpoint provides the latest trade, latest quote and greeks for each given contract symbol.
# OpenAPI definition
```json
{
 "components": {
 "headers": {
 "ratelimit_limit": {
 "description": "Request limit per minute.",
 "example": 100,
 "schema": {
 "type": "integer"
 }
 },
 "ratelimit_remaining": {
 "description": "Request limit per minute remaining.",
 "example": 90,
 "schema": {
 "type": "integer"
 }
 },
 "ratelimit_reset": {
 "description": "The UNIX epoch when the remaining quota changes.",
 "example": 1674044551,
 "schema": {
 "type": "integer"
 }
 }
 },
 "parameters": {
 "option_feed": {
 "description": "The source feed of the data. `opra` is the official OPRA feed, `indicative` is a free indicative feed where trades are delayed and quotes are modified. Default: `opra` if the user has a subscription, otherwise `indicative`.\n",
 "in": "query",
 "name": "feed",
 "schema": {
 "$ref": "#/components/schemas/option_feed"
 }
 },
 "option_limit": {
 "description": "Number of maximum snapshots to return in a response.\nThe limit applies to the total number of data points, not the number per symbol!\nUse `next_page_token` to fetch the next set of responses.\n",
 "in": "query",
 "name": "limit",
 "schema": {
 "default": 100,
 "maximum": 1000,
 "minimum": 1,
 "type": "integer"
 }
 },
 "option_symbols": {
 "description": "A comma-separated list of contract symbols with a limit of 100.",
 "example": "AAPL241220C00300000,AAPL240315C00225000",
 "in": "query",
 "name": "symbols",
 "required": true,
 "schema": {
 "type": "string"
 }
 },
 "option_updated_since": {
 "description": "Filter to snapshots that were updated since this timestamp, meaning that the timestamp of the trade or the quote is greater than or equal to this value.\nFormat: RFC-3339 or YYYY-MM-DD. If missing, all values are returned.\n",
 "in": "query",
 "name": "updated_since",
 "required": false,
 "schema": {
 "format": "date-time",
 "type": "string"
 }
 },
 "page_token": {
 "description": "The pagination token from which to continue. The value to pass here is returned in specific requests when more data is available, usually because of a response result limit.\n",
 "in": "query",
 "name": "page_token",
 "schema": {
 "type": "string"
 }
 }
 },
 "responses": {
 "400": {
 "description": "One of the request parameters is invalid. See the returned message for details.\n",
 "headers": {
 "X-RateLimit-Limit": {
 "$ref": "#/components/headers/ratelimit_limit"
 },
 "X-RateLimit-Remaining": {
 "$ref": "#/components/headers/ratelimit_remaining"
 },
 "X-RateLimit-Reset": {
 "$ref": "#/components/headers/ratelimit_reset"
 }
 }
 },
 "401": {
 "description": "Authentication headers are missing or invalid. Make sure you authenticate your request with a valid API key.\n"
 },
 "403": {
 "description": "The requested resource is forbidden.\n"
 },
 "429": {
 "description": "Too many requests. You hit the rate limit. Use the X-RateLimit-... response headers to make sure you're under the rate limit.\n",
 "headers": {
 "X-RateLimit-Limit": {
 "$ref": "#/components/headers/ratelimit_limit"
 },
 "X-RateLimit-Remaining": {
 "$ref": "#/components/headers/ratelimit_remaining"
 },
 "X-RateLimit-Reset": {
 "$ref": "#/components/headers/ratelimit_reset"
 }
 }
 },
 "500": {
 "description": "Internal server error. We recommend retrying these later. If the issue persists, please contact us on [Slack](https://alpaca.markets/slack) or on the [Community Forum](https://forum.alpaca.markets/).\n"
 }
 },
 "schemas": {
 "next_page_token": {
 "description": "Pagination token for the next page.",
 "type": [
 "string",
 "null"
 ]
 },
 "option_bar": {
 "description": "OHLC aggregate of all the trades in a given interval.",
 "examples": [
 {
 "c": 0.23,
 "h": 0.28,
 "l": 0.23,
 "n": 26,
 "o": 0.28,
 "t": "2024-01-18T05:00:00Z",
 "v": 224,
 "vw": 0.245045
 }
 ],
 "properties": {
 "c": {
 "description": "Closing price.",
 "format": "double",
 "type": "number"
 },
 "h": {
 "description": "High price.",
 "format": "double",
 "type": "number"
 },
 "l": {
 "description": "Low price.",
 "format": "double",
 "type": "number"
 },
 "n": {
 "description": "Trade count in the bar.",
 "format": "int64",
 "type": "integer"
 },
 "o": {
 "description": "Opening price.",
 "format": "double",
 "type": "number"
 },
 "t": {
 "$ref": "#/components/schemas/timestamp"
 },
 "v": {
 "description": "Bar volume.",
 "format": "int64",
 "type": "integer"
 },
 "vw": {
 "description": "Volume weighted average price.",
 "format": "double",
 "type": "number"
 }
 },
 "required": [
 "t",
 "o",
 "h",
 "l",
 "c",
 "v",
 "n",
 "vw"
 ],
 "type": "object"
 },
 "option_feed": {
 "default": "opra",
 "enum": [
 "opra",
 "indicative"
 ],
 "type": "string"
 },
 "option_greeks": {
 "description": "The greeks for the contract calculated using the Black-Scholes model.",
 "properties": {
 "delta": {
 "format": "double",
 "type": "number"
 },
 "gamma": {
 "format": "double",
 "type": "number"
 },
 "rho": {
 "format": "double",
 "type": "number"
 },
 "theta": {
 "format": "double",
 "type": "number"
 },
 "vega": {
 "format": "double",
 "type": "number"
 }
 },
 "required": [
 "delta",
 "gamma",
 "theta",
 "vega",
 "rho"
 ],
 "type": "object"
 },
 "option_quote": {
 "description": "The best bid and ask information for a given option.\n",
 "examples": [
 {
 "ap": 0.16,
 "as": 669,
 "ax": "w",
 "bp": 0.15,
 "bs": 164,
 "bx": "W",
 "c": "A",
 "t": "2024-02-28T15:30:28.046330624Z"
 }
 ],
 "properties": {
 "ap": {
 "description": "Ask price.",
 "format": "double",
 "type": "number"
 },
 "as": {
 "description": "Ask size.",
 "format": "uint32",
 "type": "integer"
 },
 "ax": {
 "description": "Ask exchange.",
 "type": "string"
 },
 "bp": {
 "description": "Bid price.",
 "format": "double",
 "type": "number"
 },
 "bs": {
 "description": "Bid size.",
 "format": "uint32",
 "type": "integer"
 },
 "bx": {
 "description": "Bid exchange.",
 "type": "string"
 },
 "c": {
 "description": "Quote condition.",
 "type": "string"
 },
 "t": {
 "$ref": "#/components/schemas/timestamp"
 }
 },
 "required": [
 "t",
 "bx",
 "bp",
 "bs",
 "ap",
 "as",
 "ax",
 "c"
 ],
 "type": "object"
 },
 "option_snapshot": {
 "description": "A snapshot provides the latest trade and latest quote.",
 "properties": {
 "dailyBar": {
 "$ref": "#/components/schemas/option_bar"
 },
 "greeks": {
 "$ref": "#/components/schemas/option_greeks"
 },
 "impliedVolatility": {
 "description": "Implied volatility calculated using the Black-Scholes model.",
 "format": "double",
 "type": "number"
 },
 "latestQuote": {
 "$ref": "#/components/schemas/option_quote"
 },
 "latestTrade": {
 "$ref": "#/components/schemas/option_trade"
 },
 "minuteBar": {
 "$ref": "#/components/schemas/option_bar"
 },
 "prevDailyBar": {
 "$ref": "#/components/schemas/option_bar"
 }
 },
 "type": "object"
 },
 "option_snapshots_resp": {
 "properties": {
 "next_page_token": {
 "$ref": "#/components/schemas/next_page_token"
 },
 "snapshots": {
 "additionalProperties": {
 "$ref": "#/components/schemas/option_snapshot"
 },
 "type": "object"
 }
 },
 "required": [
 "snapshots",
 "next_page_token"
 ],
 "type": "object"
 },
 "option_trade": {
 "description": "An option trade.",
 "examples": [
 {
 "c": "I",
 "p": 0.37,
 "s": 1,
 "t": "2024-01-18T15:03:44.56339456Z",
 "x": "B"
 }
 ],
 "properties": {
 "c": {
 "description": "Trade condition.",
 "type": "string"
 },
 "p": {
 "description": "Trade price.",
 "format": "double",
 "type": "number"
 },
 "s": {
 "description": "Trade size.",
 "format": "uint32",
 "type": "integer"
 },
 "t": {
 "$ref": "#/components/schemas/timestamp"
 },
 "x": {
 "type": "string"
 }
 },
 "required": [
 "t",
 "x",
 "p",
 "s",
 "c"
 ],
 "type": "object"
 },
 "timestamp": {
 "description": "Timestamp in RFC-3339 format with nanosecond precision.",
 "format": "date-time",
 "type": "string"
 }
 },
 "securitySchemes": {
 "BasicAuth": {
 "scheme": "basic",
 "type": "http"
 },
 "apiKey": {
 "in": "header",
 "name": "APCA-API-KEY-ID",
 "type": "apiKey"
 },
 "apiSecret": {
 "in": "header",
 "name": "APCA-API-SECRET-KEY",
 "type": "apiKey"
 }
 }
 },
 "info": {
 "contact": {
 "email": "support@alpaca.markets",
 "name": "Alpaca Support",
 "url": "https://alpaca.markets/support"
 },
 "description": "Access real-time and historical market data for US equities, options, crypto, and foreign exchange data through the Alpaca REST and WebSocket APIs. There are APIs for Stock Pricing, Option Pricing, Crypto Pricing, Forex, Logos, Fixed income, Corporate Actions, Screener, and News.\n",
 "license": {
 "name": "Creative Commons Attribution Share Alike 4.0 International",
 "url": "https://spdx.org/licenses/CC-BY-SA-4.0.html"
 },
 "termsOfService": "https://s3.amazonaws.com/files.alpaca.markets/disclosures/library/TermsAndConditions.pdf",
 "title": "Market Data API",
 "version": "1.1"
 },
 "openapi": "3.1.2",
 "paths": {
 "/v1beta1/options/snapshots": {
 "get": {
 "description": "The snapshots endpoint provides the latest trade, latest quote and greeks for each given contract symbol.\n",
 "operationId": "OptionSnapshots",
 "parameters": [
 {
 "$ref": "#/components/parameters/option_symbols"
 },
 {
 "$ref": "#/components/parameters/option_feed"
 },
 {
 "$ref": "#/components/parameters/option_updated_since"
 },
 {
 "$ref": "#/components/parameters/option_limit"
 },
 {
 "$ref": "#/components/parameters/page_token"
 }
 ],
 "responses": {
 "200": {
 "content": {
 "application/json": {
 "examples": {
 "snapshots": {
 "value": {
 "next_page_token": "QUFQTDI0MDYyMTAwMDIyMHwx",
 "snapshots": {
 "AAPL240426C00162500": {
 "greeks": {
 "delta": 0.7521304109871954,
 "gamma": 0.06241426404871288,
 "rho": 0.009910739032549095,
 "theta": -0.2847623059595503,
 "vega": 0.047540520834498785
 },
 "impliedVolatility": 0.3372405712050441,
 "latestQuote": {
 "ap": 4.3,
 "as": 91,
 "ax": "B",
 "bp": 4.15,
 "bs": 16,
 "bx": "C",
 "c": "A",
 "t": "2024-04-22T19:59:59.992734208Z"
 },
 "latestTrade": {
 "c": "I",
 "p": 4.1,
 "s": 1,
 "t": "2024-04-22T19:57:32.589554432Z",
 "x": "A"
 }
 }
 }
 }
 }
 },
 "schema": {
 "$ref": "#/components/schemas/option_snapshots_resp"
 }
 }
 },
 "description": "OK",
 "headers": {
 "X-RateLimit-Limit": {
 "$ref": "#/components/headers/ratelimit_limit"
 },
 "X-RateLimit-Remaining": {
 "$ref": "#/components/headers/ratelimit_remaining"
 },
 "X-RateLimit-Reset": {
 "$ref": "#/components/headers/ratelimit_reset"
 }
 }
 },
 "400": {
 "$ref": "#/components/responses/400"
 },
 "401": {
 "$ref": "#/components/responses/401"
 },
 "403": {
 "$ref": "#/components/responses/403"
 },
 "429": {
 "$ref": "#/components/responses/429"
 },
 "500": {
 "$ref": "#/components/responses/500"
 }
 },
 "security": [
 {
 "apiKey": [],
 "apiSecret": []
 },
 {
 "BasicAuth": []
 }
 ],
 "summary": "Snapshots",
 "tags": [
 "Option"
 ]
 }
 }
 },
 "servers": [
 {
 "description": "Production",
 "url": "https://data.alpaca.markets"
 },
 {
 "description": "Sandbox",
 "url": "https://data.sandbox.alpaca.markets"
 }
 ],
 "tags": [
 {
 "description": "Endpoints for option data.",
 "name": "Option"
 }
 ]
}
```