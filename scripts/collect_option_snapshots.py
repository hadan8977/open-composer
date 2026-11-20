"""Capture Alpaca indicative chains and dated contract open interest after close."""

from datetime import UTC, date, datetime
from pathlib import Path
from time import monotonic, sleep

import duckdb
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from open_composer.market_sessions import NEW_YORK, us_equity_session_close
from open_composer.research.file_lock import lock_file
from scripts.update_sip_raw_daily import alpaca_session

DERIVED = Path(__file__).resolve().parents[2] / "market-data" / "derived"
DEST = DERIVED / "option-snapshots"
CHAINS = "https://data.alpaca.markets/v1beta1/options/snapshots"
CONTRACTS = "https://paper-api.alpaca.markets/v2/options/contracts"
# Index benchmarks, sector rotation, leveraged rotation and the QLD router.
ETF_ROOTS = """
SPY QQQ IWM XLK XLV XLF XLE XLI XLY XLP XLU XLB XLRE XLC TQQQ SOXL UPRO USD TECL QLD
""".split()
GREEKS = ("delta", "gamma", "theta", "vega", "rho")
SCHEMA = pa.schema([
    ("session", pa.date32()), ("underlying", pa.string()), ("contract", pa.string()),
    ("feed", pa.string()), ("universe_session", pa.date32()),
    ("fetched_at", pa.timestamp("us", tz="UTC")),
    ("quote_at", pa.timestamp("ns", tz="UTC")),
    ("trade_at", pa.timestamp("ns", tz="UTC")),
    ("bid", pa.float64()), ("ask", pa.float64()), ("bid_size", pa.int64()),
    ("ask_size", pa.int64()), ("last_trade", pa.float64()), ("iv", pa.float64()),
    ("open_interest", pa.int64()), ("open_interest_date", pa.date32()),
    ("open_interest_fetched_at", pa.timestamp("us", tz="UTC")),
] + [(name, pa.float64()) for name in GREEKS])


def ranked_roots(day, as_of):
    with duckdb.connect(config={"threads": 2}) as db:
        return db.execute("""
            WITH eligible AS (
              SELECT symbol, trade_date::DATE AS universe_session, median_dollar_volume_20,
                     known_at, is_member, security_type, security_type_known_at
              FROM read_parquet(?) WHERE trade_date < ? AND known_at <= ?
            )
            SELECT symbol, universe_session
            FROM eligible
            WHERE universe_session = (SELECT max(universe_session) FROM eligible)
              AND is_member AND security_type IN ('operating', 'adr')
              AND security_type_known_at <= ? AND median_dollar_volume_20 > 0
            GROUP BY symbol, universe_session
            ORDER BY max(median_dollar_volume_20) DESC, symbol
            LIMIT 300
        """, [str(DERIVED / "daily-us-stock-universe.parquet"), day, as_of, as_of]).fetchall()


def pages(client, url, params):
    while True:
        begin = monotonic()
        response = client.get(url, params=params, timeout=(5, 60))
        fetched_at = datetime.now(UTC)
        response.raise_for_status()
        payload = response.json()
        yield payload, fetched_at
        token = payload.get("next_page_token")
        if not token:
            return
        params["page_token"] = token
        sleep(max(0, 0.4 - (monotonic() - begin)))


def capture_root(client, symbol, day, universe_session, path):
    expiry_start = {"expiration_date_gte": day.isoformat()}
    interest = {}
    params = {"underlying_symbols": symbol, "expiration_date_lte": "2099-12-31",
              "limit": 10000, **expiry_start}
    for payload, fetched_at in pages(client, CONTRACTS, params):
        for item in payload["option_contracts"]:
            if item.get("open_interest") is not None:
                interest[item["symbol"]] = {
                    "open_interest": int(item["open_interest"]),
                    "open_interest_date": date.fromisoformat(item["open_interest_date"]),
                    "open_interest_fetched_at": fetched_at,
                }

    pending = path.with_suffix(".tmp")
    with pq.ParquetWriter(pending, SCHEMA, compression="zstd") as writer:
        for payload, fetched_at in pages(client, f"{CHAINS}/{symbol}", {
            "feed": "indicative", "limit": 1000, **expiry_start,
        }):
            rows = []
            for contract, snapshot in (payload["snapshots"] or {}).items():
                quote = snapshot.get("latestQuote") or {}
                trade = snapshot.get("latestTrade") or {}
                greeks = snapshot.get("greeks") or {}
                rows.append({
                    "session": day, "underlying": symbol, "contract": contract,
                    "feed": "indicative", "universe_session": universe_session,
                    "fetched_at": fetched_at,
                    "quote_at": pd.Timestamp(quote["t"]) if quote.get("t") else None,
                    "trade_at": pd.Timestamp(trade["t"]) if trade.get("t") else None,
                    "bid": quote.get("bp"), "ask": quote.get("ap"),
                    "bid_size": quote.get("bs"), "ask_size": quote.get("as"),
                    "last_trade": trade.get("p"), "iv": snapshot.get("impliedVolatility"),
                    **{name: greeks.get(name) for name in GREEKS},
                    **interest.get(contract, {}),
                })
            if rows:
                writer.write_table(pa.Table.from_pylist(rows, schema=SCHEMA))
    pending.replace(path)


def main():
    now = datetime.now(NEW_YORK)
    day = now.date()
    close = us_equity_session_close(day)
    if close is None or now.time() < close:
        print(f"{day}: no completed session", flush=True)
        return

    DEST.mkdir(parents=True, exist_ok=True)
    with (DEST / ".capture.lock").open("ab") as handle:
        lock_file(handle)
        output = DEST / f"{day}.parquet"
        if output.exists():
            print(f"{day}: already captured", flush=True)
            return
        parts = DEST / f".{day}-parts"
        parts.mkdir(exist_ok=True)
        stocks = ranked_roots(day, datetime.combine(day, close, NEW_YORK))
        roots = {**dict.fromkeys(ETF_ROOTS), **dict(stocks)}
        print(f"{day}: {len(roots)} underlyings, stock universe {stocks[0][1]}", flush=True)
        paths = []
        with alpaca_session() as client:
            for index, (symbol, universe_session) in enumerate(roots.items(), 1):
                part = parts / f"{index:03d}-{symbol}.parquet"
                paths.append(part)
                if not part.exists():
                    begin = monotonic()
                    capture_root(client, symbol, day, universe_session, part)
                    sleep(max(0, 0.8 - (monotonic() - begin)))
                if index % 25 == 0:
                    print(f"{index}/{len(roots)} underlyings captured", flush=True)

        pending = output.with_suffix(".tmp")
        empty = []
        with pq.ParquetWriter(pending, SCHEMA, compression="zstd") as writer:
            for symbol, part in zip(roots, paths, strict=True):
                table = pq.read_table(part)
                if table.num_rows:
                    writer.write_table(table)
                else:
                    empty.append(symbol)
        pending.replace(output)
        for part in paths:
            part.unlink()
        parts.rmdir()
        rows = pq.ParquetFile(output).metadata.num_rows
        print(f"{output}: {rows} contracts. No snapshots: {', '.join(empty) or 'none'}", flush=True)


if __name__ == "__main__":
    main()
