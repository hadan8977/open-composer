SOURCE: https://docs.alpaca.markets/us/docs/real-time-option-data.md
FETCHED_UTC: 2026-10-04T18:47Z
HTTP: 200
---
---
updatedAt: 2025-09-24T23:25:14.000Z
agentTools:
 siteIndex: https://docs.alpaca.markets/llms.txt
 projectIndex: https://docs.alpaca.markets/us/llms.txt
---
# Real-time Option Data
This API provides option market data on a websocket stream. This helps receive the most up to date market information that could help your trading strategy to act upon certain market movements. If you wish to access the latest pricing data, using the stream provides much better accuracy and performance than polling the latest historical endpoints.
You can find the general description of the real-time WebSocket Stream [here](https://docs.alpaca.markets/docs/streaming-market-data). This page focuses on the option stream.
# URL
The URL for the option stream is
```
wss://stream.data.alpaca.markets/v1beta1/{feed}
```
Sandbox URL:
```
wss://stream.data.sandbox.alpaca.markets/v1beta1/{feed}
```
Substitute `indicative` or `opra` for `{feed}` depending on your subscription. The capabilities and differences for the `indicative` and `opra` subscriptions can be found \[[here](https://docs.alpaca.markets/docs/about-market-data-api#options)].
Any attempt to access a data feed not available for your subscription will result in an error during authentication.
# Message format
> 🚧 Msgpack
>
> Unlike the stock and crypto stream, the option stream is only available in [msgpack](https://msgpack.org/index.html) format. The SDKs are using this format automatically. For readability, the examples in the rest of this documentation will still be in json format (because msgpack is binary encoded).
# Channels
## Trades
### Schema
| Attribute | Type | Notes |
| :-------- | :----- | :------------------------------------------------------------------------------------------------------ |
| `T` | string | message type, always “t” |
| `S` | string | symbol |
| `t` | string | [RFC-3339](https://datatracker.ietf.org/doc/html/rfc3339) formatted timestamp with nanosecond precision |
| `p` | number | trade price |
| `s` | int | trade size |
| `x` | string | exchange code where the trade occurred |
| `c` | string | trade condition |
### Example
```json
{
 "T": "t",
 "S": "AAPL240315C00172500",
 "t": "2024-03-11T13:35:35.13312256Z",
 "p": 2.84,
 "s": 1,
 "x": "N",
 "c": "S"
}
```
## Quotes
### Schema
| Attribute | Type | Notes |
| :-------- | :----- | :------------------------------------------------------------------------------------------------------ |
| `T` | string | message type, always “q” |
| `S` | string | symbol |
| `t` | string | [RFC-3339](https://datatracker.ietf.org/doc/html/rfc3339) formatted timestamp with nanosecond precision |
| `bx` | string | bid exchange code |
| `bp` | number | bid price |
| `bs` | int | bid size |
| `ax` | string | ask exchange code |
| `ap` | number | ask price |
| `as` | int | ask size |
| `c` | string | quote condition |
### Example
```json
{
 "T": "q",
 "S": "SPXW240327P04925000",
 "t": "2024-03-12T11:59:38.897261568Z",
 "bx": "C",
 "bp": 9.46,
 "bs": 53,
 "ax": "C",
 "ap": 9.66,
 "as": 38,
 "c": "A"
}
```
# Errors
Other than the [general stream errors](https://docs.alpaca.markets/docs/streaming-market-data#errors), you may receive these option-specific errors during your session:
| Error Message | Description |
| :---------------------------------------------------------------------------------------- | :--------------------------------------------------------------------------------- |
| `[{"T":"error","code":412,"msg":"option messages are only available in MsgPack format"}]` | Use the `Content-Type: application/msgpack` header. |
| `[{"T":"error","code":413,"msg":"star subscription is not allowed for option quotes"}]` | You cannot subscribe to `*` for option quotes (there are simply too many of them). |