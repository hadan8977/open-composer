URL: https://docs.alpaca.markets/us/docs/crypto-pricing-data.md
FETCHED_UTC: 2026-10-05T07:31Z
HTTP: 200
-----
---
updatedAt: 2025-09-24T23:11:21.000Z
agentTools:
  siteIndex: https://docs.alpaca.markets/llms.txt
  projectIndex: https://docs.alpaca.markets/us/llms.txt
---

# Crypto Pricing Data

Alpaca provides free limited crypto data and a more advanced unlimited paid plan.

To request trading pairs data via REST API, see [Crypto Pricing Data REST API](https://docs.alpaca.markets/reference/v1beta2cryptobars) Reference.

The example below requests the latest order book data (bid and asks) for the following three crypto trading pairs: BTC/USD, ETH/BTC and ETH/USD.

```curl
curl --request GET 'https://data.alpaca.markets/v1beta3/crypto/us/latest/orderbooks?symbols=BTC/USD,ETH/BTC,ETH/USD,SOL/USDT' \
--header 'Apca-Api-Key-Id: <KEY>' \
--header 'Apca-Api-Secret-Key: <SECRET>'
```

```
{
    "orderbooks": {
        "BTC/USD": {
            "a": [
                {
                    "p": 27539.494,
                    "s":  0.2632414
                },
                ...
            ],
            "b": [
                {
                    "p": 27511.78083,
                    "s": 0.26265668
                },
                ...
            ],
            "t": "2023-03-18T13:31:44.932988033Z"
        },
        "ETH/USD": { ... },
        "ETH/BTC": { ... },
        "SOL/USDT": { ... }
    }
}
```

# Real-Time Crypto Market Data

Additionally, you can subscribe to real-time crypto data via Websockets. Example below leverages wscat to subscribe to:

* BTC/USD trades.
* ETH/USDT and ETH/USD quotes.
* BTC/USD order books

```
 $ wscat -c wss://stream.data.alpaca.markets/v1beta3/crypto/us
Connected (press CTRL+C to quit)
< [{"T":"success","msg":"connected"}]
> {"action": "auth", "key": "<KEY>", "secret": "<SECRET>"}
< [{"T":"success","msg":"authenticated"}]
> {"action":"subscribe", "trades":["BTC/USD"], "quotes":["ETH/USDT","ETH/USD"], "orderbooks":["BTC/USD"]}
< [{"T":"subscription","trades":["BTC/USD"],"quotes":["ETH/USDT","ETH/USD"],"orderbooks":["BTC/USD"],"updatedBars":[],"dailyBars":[]}]
< [{"T":"o","S":"BTC/USD","t":"2023-03-18T13:51:29.754747009Z","b":[{"p":27485.3445,"s":0.25893365},{"p":27466.92727,"s":0.52351568},...],"a":[{"p":27512.92,"s":0.26137249},{"p":27547.9425,"s":0.52011956},...],"r":true}]
< [{"T":"q","S":"ETH/USDT","bp":1815.55510989,"bs":8.24941727,"ap":1818.4,"as":4.15121428,"t":"2023-03-18T13:51:33.256826818Z"}]
< ...
```