URL: https://docs.alpaca.markets/us/docs/245-trading-for-trading-api.md
FETCHED_UTC: 2026-10-05T07:30Z
HTTP: 200
-----
---
updatedAt: 2026-07-07T14:20:23.000Z
agentTools:
  siteIndex: https://docs.alpaca.markets/llms.txt
  projectIndex: https://docs.alpaca.markets/us/llms.txt
---

# 24/5 Trading

### What is 24/5 Trading?

Overnight Trading extends market hours to provide a 24-hour, 5-day-a-week trading experience for all NMS securities. The overnight session operates from 8:00 PM ET Sunday to 4:00 AM ET Friday, bridging the gap between one day's post-market session and the next day's pre-market session.

***

### How does the overnight trading session work?

Overnight trade executions and market data are facilitated by the Blue Ocean Alternative Trading System (BOATS). As an Alternative Trading System (ATS), BOATS operates an independent overnight trading session outside of traditional stock exchanges.

***

### What are the hours for the 24/5 trading sessions?

The trading sessions are structured as follows, from Sunday evening to Friday evening:

* **Overnight Session:** 8:00 PM - 4:00 AM ET (technically occurs on the evening before the trade date)
* **Pre-Market Session:** 4:00 AM – 9:30 AM ET
* **Regular Market Session:** 9:30 AM - 4:00 PM ET
* **After-Hours Session:** 4:00 PM - 8:00 PM ET

The overnight session follows the NYSE holiday calendar. For example, if there is a market holiday on a Friday, the overnight session will not run on Thursday evening. However, the overnight session runs for a full 8 hours on market half-days.

***

### How can I enable overnight trading?

Trading API accounts are enabled for 24/5 trading by default. If needed, you can disable trading in the overnight session.

***

### How can I access market data for the overnight session?

Alpaca’s 24/5 trading includes overnight market access, which is powered by two data sources: the Blue Ocean Alternative Trading System (BOATS) and Overnight. Which feed you use depends on your [market data plan](https://alpaca.markets/data).

Overnight market data is available between 8:00 PM and 4:00 AM ET and supports the following data types: Bars, Quotes, Trades, and Snapshots.

**Market data plans and feeds**

Algo Trader Plus Plan

* Use feed=`boats` for:
  * [Latest Quotes](https://docs.alpaca.markets/reference/stocklatestquotes-1)  and [Latest Trades](https://docs.alpaca.markets/reference/stocklatesttrades-1), [Snapshots](https://docs.alpaca.markets/reference/stocksnapshotsingle)
  * [Historical Bars](https://docs.alpaca.markets/reference/stockbarsingle-1), [Quotes](https://docs.alpaca.markets/reference/stockquotes-1), and [Trades](https://docs.alpaca.markets/reference/stocktrades-1)

Free Plan

* Use feed=`overnight` for:
  * [Latest Bars](https://docs.alpaca.markets/reference/stocklatestbars-1),
  * [Latest Quotes](https://docs.alpaca.markets/reference/stocklatestquotes-1)  (real-time indicative),
  * [Latest Trades](https://docs.alpaca.markets/reference/stocklatesttrades-1)  (15-minute delayed),
  * [Snapshots](https://docs.alpaca.markets/reference/stocksnapshots-1)
* Use feed=`boats` for
  * [Historical Bars](https://docs.alpaca.markets/reference/stockbarsingle-1), [Quotes](https://docs.alpaca.markets/reference/stockquotes-1), and [Trades](https://docs.alpaca.markets/reference/stocktrades-1) (all 15-minute delayed BOATS data)

You can select the feed by setting the feed parameter on the Bars, Quotes, Trades, and Snapshots endpoints.

See the [API documentation for “DataFeed”](https://alpaca.markets/sdks/python/api_reference/data/enums.html#alpaca.data.enums.DataFeed) for details.

***

### What securities are available for overnight trading?

All National Market System (NMS) securities are available for trading during the overnight session. Assets tradable in the overnight session can be identified via the `overnight_tradable` attribute in the Assets API. The list may be limited due to compliance or risk procedures, and the best way to validate the available securities is by using our Assets API as outlined above. OTC securities are not part of the NMS and are therefore not available.

***

### What order types and time-in-force (TIF) options are supported?

* **Order Type:** Only `limit` orders are supported during the overnight session.
* **Time-in-Force (TIF):** The only TIF currently supported is `day` and `gtc`.
  * `day` orders placed during the overnight session will remain active through the regular and after-hours sessions of the upcoming trading day. If unfilled, the order is canceled at 8:00 PM ET.
  * `gtc` (Good-Til-Canceled) orders will expire 90 days after the order is placed. In the case of corporate actions events, the `gtc` order will be cancelled prior to the corporate action event.

***

### Is fractional share trading supported?

Yes, fractional share trading is supported during the overnight session and functions the same way as it does during other extended-hours sessions.

***

### Are there restrictions on margin or buying power during the overnight session?

Yes. Day Trading Buying Power (DTBP) does not apply to the overnight session. This means 2x multiplier is the max margin buying power for overnight session trades. If an account uses DTBP for an order during the post market session, the order might be rejected (at 8 PM ET) due to insufficient buying power (if reg\_t or non-DT buying power is insufficient).

***

### What happens to an order that is not filled during the overnight session?

If your `day` order is not filled during the overnight session, it will automatically carry over into the pre-market, regular, and after-hours sessions for that trade date. It remains an active order until it is executed or the market closes at 8:00 PM ET.

***

### How does trade settlement work for overnight trades?

The overnight session marks the beginning of a new trading day. Trades are assigned a date based on their execution time and settle on a T+1 basis from that date.

* **Example:** A trade executed at 9:00 PM ET on a Monday is assigned a trade date of Tuesday and will settle on Wednesday (T+1).

***

### How do corporate actions affect overnight trading?

A security may be halted from trading during the overnight session while a pending corporate action is being processed. Furthermore, due to the way trade dates are assigned, purchasing a stock during the overnight session on its ex-dividend date will not entitle you to that stock's dividend.

***

### What happens when a security is halted during the overnight session?

If an asset is halted overnight (e.g., due to a corporate action or pending news), the halt typically persists for the entire session. Orders submitted for a halted security will be accepted by the system with a status of `accepted` but will be held in a pending state. This ensures your order can be executed as soon as the halt is lifted and trading resumes in the next session.

***

### What API changes were made?

Two new boolean attributes have been added to the Assets API to support 24/5 trading:

When retrieving assets from the Assets API, you’ll see the following new attributes:

* `overnight_tradable`: Indicates whether an asset is eligible for overnight trading.
* `overnight_halted`: Indicates whether an otherwise eligible asset is temporarily halted from overnight trading, such as during a corporate action.

In addition, `boats` and `overnight` data feeds have been introduced in the Market Data API.

***

### How can I identify which assets are tradable overnight via the API?

You can identify eligible assets by calling the `v1/assets` endpoint and filtering for assets where the `overnight_tradable` attribute is `true`.

***

### When is the best time to sync the list of overnight-tradable assets?

We begin syncing our list of tradable assets at 7:05 PM ET and run updates every 10 minutes until 7:45 PM ET. For the most up-to-date list, we recommend syncing your asset list between 7:45 PM and 8:00 PM ET, with 7:55 PM ET being the ideal time.

***

### Can I access delayed historical overnight requests with an overnight subscription?

Yes, you can access delayed historical overnight requests with an overnight subscription, provided that the end parameter in your request is at least 15 minutes old.

**To access delayed historical overnight data, make sure to include the parameter `feed=boats` in your request, `feed=overnight` will give error.**

Example: If you have an overnight subscription and want to request overnight/BOATS data ending at 10:00 PM EST , you can do so any time after 10:15 PM by specifying`feed=boats` in your request.

***

####

#### Disclosures

The content of this article is for general information only and is believed to be accurate as of the posting date, but may be subject to change. Alpaca does not provide investment, tax, or legal advice. Please consult your own independent advisor as to any investment, tax, or legal statements made herein.

Orders placed outside regular trading hours (9:30 a.m. – 4:00 p.m. ET) may experience price fluctuations, partial executions, or delays due to lower liquidity and higher volatility. 

Orders not designated for extended hours execution will be queued for the next trading session.

Additionally, fractional trading may be limited during extended hours. For more details, please review [Alpaca Extended Hours & Overnight Trading Risk Disclosure](https://files.alpaca.markets/disclosures/library/ExtHrsOvernightRisk.pdf).

Fractional share trading allows a customer to buy and sell fractional share quantities and dollar amounts of certain securities. Fractional share trading presents unique risks and is subject to particular limitations that you should be aware of before engaging in such activity. See Alpaca Customer Agreement at [Alpaca - Disclosures and Agreements](https://alpaca.markets/disclosures) for more details.

Margin trading involves significant risk and is not suitable for all investors. Before considering a margin loan, it is crucial that you carefully consider how borrowing fits with your investment objectives and risk tolerance.

When trading on margin, you assume higher market risk, and potential losses can exceed the collateral value in your account. Alpaca may sell any securities in your account, without prior notice, to satisfy a margin call. Alpaca may also change its “house” maintenance margin requirements at any time without advance written notice. You are not entitled to an extension of time on a margin call. Please review the Firm’s [Margin Disclosure Statement](https://files.alpaca.markets/disclosures/library/MarginDiscStmt.pdf) before investing.

All investments involve risk, and the past performance of a security, or financial product does not guarantee future results or returns. There is no guarantee that any investment strategy will achieve its objectives. Please note that diversification does not ensure a profit, or protect against loss. There is always the potential of losing money when you invest in securities, or other financial products. Investors should consider their investment objectives and risks carefully before investing.

Securities brokerage services are provided by Alpaca Securities LLC ("Alpaca Securities"), member [FINRA](https://www.finra.org/)/[SIPC](https://www.sipc.org/), a wholly-owned subsidiary of AlpacaDB, Inc. Technology and services are offered by AlpacaDB, Inc.

Cryptocurrency services are made available by Alpaca Crypto LLC ("Alpaca Crypto"), a FinCEN registered money services business (NMLS # 2160858), and a wholly-owned subsidiary of AlpacaDB, Inc. Alpaca Crypto is not a member of SIPC or FINRA. Cryptocurrencies are not stocks and your cryptocurrency investments are not protected by either FDIC or SIPC. Please see the [Disclosure Library](https://alpaca.markets/disclosures) for more information.

This is not an offer, solicitation of an offer, or advice to buy or sell securities or cryptocurrencies or open a brokerage account or cryptocurrency account in any jurisdiction where Alpaca Securities or Alpaca Crypto, respectively, are not registered or licensed, as applicable.