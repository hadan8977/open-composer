URL: https://docs.alpaca.markets/us/docs/historical-stock-data-1.md
FETCHED_UTC: 2026-10-05T07:32Z
HTTP: 200
-----
---
updatedAt: 2026-02-11T05:30:13.000Z
agentTools:
  siteIndex: https://docs.alpaca.markets/llms.txt
  projectIndex: https://docs.alpaca.markets/us/llms.txt
---

# Historical Stock Data

This API provides historical market data for equities. Check the [API Reference](https://docs.alpaca.markets/reference/stockbars) for detailed descriptions of all REST endpoints.

# Data Sources

Alpaca offers market data from various data sources described below. You can use the `feed` parameter on all the stock endpoints to switch between them.

<Table align={["left","left"]}>
  <thead>
    <tr>
      <th>
        Source
      </th>

      <th>
        Description
      </th>
    </tr>
  </thead>

  <tbody>
    <tr>
      <td>
        **iex**
      </td>

      <td>
        IEX ([The Investors Exchange](https://www.iexexchange.io/)) is ideal for initial app testing and situations where precise pricing may not be the primary focus. It's a single US exchange that accounts for approximately ~2.5% of the market volume.

        ℹ️ This is the only feed that can be used without a subscription.
      </td>
    </tr>

    <tr>
      <td>
        **sip**
      </td>

      <td>
        This feed covers all US exchanges, originating directly from exchanges and is consolidated by the Securities Information Processors: [UTP](https://utpplan.com/) (Nasdaq) and [CTA](https://www.nyse.com/data/cta) (NYSE). These SIPs play a crucial role in connecting various U.S. markets, processing and consolidating all bid/ask quotes and trades from multiple trading venues into a single, easily accessible data feed.

        Our data delivery ensures ultra-low latency and high reliability, as the information is transmitted directly to Alpaca's bare metal servers located in New Jersey, situated alongside many market participants.

        SIP data is particularly advantageous for developing your trading app, where precise and up-to-date price information is essential for traders and internal operations. It accounts for 100% of the market volume, providing comprehensive coverage for your trading needs.
      </td>
    </tr>

    <tr>
      <td>
        **boats**
      </td>

      <td>
        [Blue Ocean ATS](https://blueocean-tech.io/) is the first alternative trading system to expand market hours, filling the gap to trade equities continuously throughout US evening hours.
      </td>
    </tr>

    <tr>
      <td>
        **overnight**
      </td>

      <td>
        Our "overnight" feed is Alpaca's derived feed from the original BOATS source. It offers a cheaper, but slightly less accurate alternative for overnight US market data. The trades are 15 minutes delayed and adjusted to fit the bid-ask spread.
      </td>
    </tr>
  </tbody>
</Table>

<br />