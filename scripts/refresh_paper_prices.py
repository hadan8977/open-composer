"""Read live stock prices for the positions held by the Paper accounts."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from alpaca.data.requests import StockLatestTradeRequest

from open_composer.market_sessions import NEW_YORK, us_equity_session_close
from scripts.capture_paper_forward_inputs import ACCOUNTS, ROOT, market_data_client
from scripts.publish_paper_forward_projection import atomic_write


def position_marks(directory: Path) -> dict:
    marks = {}
    for alias in ACCOUNTS:
        try:
            captured = json.loads((directory / f"account-{alias}-marks.json").read_text())
        except FileNotFoundError:
            continue
        at = datetime.fromisoformat(captured["at"])
        for symbol, raw_price in captured["marks"].items():
            entry = marks.setdefault(symbol, dict(accounts=[], broker=None))
            entry["accounts"].append(alias)
            if raw_price is not None and float(raw_price) > 0:
                prior = entry["broker"]
                if prior is None or at > prior[0]:
                    entry["broker"] = (at, float(raw_price))
    return marks


def price_row(symbol: str, position: dict, trade, now: datetime) -> dict:
    broker = position["broker"]
    quote_at, price, source = None, None, None
    if trade is not None:
        quote_at, price, source = trade.timestamp, trade.price, "iex"
    if (quote_at is None or now - quote_at > timedelta(seconds=90)) and (
        broker is not None and now - broker[0] <= timedelta(minutes=3)
    ):
        quote_at, price = broker
        source = "broker"
    return dict(
        symbol=symbol,
        accounts=position["accounts"],
        price=price,
        at=None if quote_at is None else quote_at.isoformat(),
        source=source,
    )


def refresh(root: Path) -> None:
    if us_equity_session_close(datetime.now(NEW_YORK).date()) is None:
        return
    directory = root / "runtime/paper"
    marks = position_marks(directory)
    names = sorted(marks)
    trades = {}
    if names:
        client = market_data_client()
        for offset in range(0, len(names), 200):
            request = StockLatestTradeRequest(
                symbol_or_symbols=names[offset : offset + 200], feed="iex"
            )
            trades.update(client.get_stock_latest_trade(request))
    now = datetime.now(UTC)
    rows = [price_row(symbol, marks[symbol], trades.get(symbol), now) for symbol in names]
    raw = json.dumps(dict(at=now.isoformat(), rows=rows), allow_nan=False).encode()
    atomic_write(directory / "position-prices.json", raw)


if __name__ == "__main__":
    refresh(ROOT)
