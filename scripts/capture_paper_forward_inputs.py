"""Capture the read-only inputs one forward paper-projection rebuild needs.

One bounded read per source: three Alpaca Paper accounts (account, positions,
daily portfolio history, activities after the sealed cut-off) and raw daily
bars for the symbols those books held. Nothing here submits an order, mutates
paper state or touches the SIP archive; the receipts are written under a new
diagnostics directory so the sealed history stays untouched.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import socket
from datetime import UTC, datetime
from pathlib import Path

from dotenv import dotenv_values

LEGACY_ENV = Path("/root/codex-test/open-composer/.env")
BOOK_ENV = Path("/root/.config/open-composer/paper-book-accounts.env")
VALIDATION_ENV = Path("/root/.config/open-composer/paper-validation-20261019.env")
ACCOUNTS = {
    "legacy": (LEGACY_ENV, "ALPACA_API_KEY_ID", "ALPACA_API_SECRET_KEY"),
    "quant1": (BOOK_ENV, "ALPACA_QUANT1_API_KEY_ID", "ALPACA_QUANT1_API_SECRET_KEY"),
    "six": (VALIDATION_ENV, "ALPACA_QUANT2_API_KEY_ID", "ALPACA_QUANT2_API_SECRET_KEY"),
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write(path: Path, payload: object) -> dict:
    body = (json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return {"path": str(path), "bytes": len(body), "sha256": digest(body)}


def trading_client(alias: str):
    from open_composer.adapters.broker.alpaca_exchange_compat import (
        ExchangeCompatibleTradingClient as TradingClient,
    )

    env_path, key_var, secret_var = ACCOUNTS[alias]
    values = dotenv_values(env_path)
    missing = [name for name in (key_var, secret_var) if not values.get(name)]
    if missing:
        raise SystemExit(f"{alias}: missing credential variables {missing}")
    return TradingClient(
        api_key=values[key_var], secret_key=values[secret_var], paper=True
    )


def plain(value):
    return json.loads(value.model_dump_json()) if hasattr(value, "model_dump_json") else value


def capture_accounts(out: Path, after: str, manifest: dict) -> None:
    from alpaca.trading.requests import GetPortfolioHistoryRequest

    for alias in ACCOUNTS:
        client = trading_client(alias)
        account = plain(client.get_account())
        positions = [plain(p) for p in client.get_all_positions()]
        history = plain(
            client.get_portfolio_history(
                GetPortfolioHistoryRequest(period="3M", timeframe="1D")
            )
        )
        manifest[f"account/{alias}"] = write(
            out / f"account-{alias}.json",
            dict(
                alias=alias,
                captured_at=datetime.now(UTC).isoformat(),
                account=account,
                positions=positions,
                portfolio_history=history,
            ),
        )
        rows, page_token = [], None
        while True:
            params = {"after": after, "page_size": 100, "direction": "asc"}
            if page_token:
                params["page_token"] = page_token
            page = client.get("/account/activities", data=params)
            rows.extend(page)
            if len(page) < 100:
                break
            page_token = str(page[-1].get("id"))
        manifest[f"activities/{alias}"] = write(
            out / f"activities-{alias}.json",
            dict(
                alias=alias,
                captured_at=datetime.now(UTC).isoformat(),
                after=after,
                rows=rows,
            ),
        )
        print(f"{alias}: account + {len(positions)} positions + {len(rows)} activities")


def capture_bars(out: Path, symbols: list[str], start: str, end: str, manifest: dict) -> None:
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    values = dotenv_values(LEGACY_ENV)
    client = StockHistoricalDataClient(
        values["ALPACA_API_KEY_ID"], values["ALPACA_API_SECRET_KEY"]
    )
    from datetime import time as clock_time

    from zoneinfo import ZoneInfo

    ny = ZoneInfo("America/New_York")
    bars: dict[str, list] = {}
    for offset in range(0, len(symbols), 100):
        batch = symbols[offset : offset + 100]
        request = StockBarsRequest(
            symbol_or_symbols=batch,
            timeframe=TimeFrame.Day,
            start=datetime.fromisoformat(start).replace(tzinfo=UTC),
            end=datetime.fromisoformat(end).replace(tzinfo=UTC),
            feed="sip",
            adjustment="raw",
        )
        frame = client.get_stock_bars(request).df
        if "symbol" not in frame.columns:
            frame = frame.reset_index()
        for row in frame.itertuples(index=False):
            day = row.timestamp.tz_convert(ny).date().isoformat()
            bars.setdefault(str(row.symbol).upper(), []).append(
                dict(day=day, open=float(row.open), close=float(row.close))
            )
    for rows in bars.values():
        rows.sort(key=lambda r: r["day"])
    manifest["bars"] = write(
        out / "bars.json",
        dict(
            captured_at=datetime.now(UTC).isoformat(),
            start=start,
            end=end,
            adjustment="raw",
            feed="sip",
            symbols=bars,
        ),
    )
    print(f"bars: {len(bars)} symbols, {sum(len(v) for v in bars.values())} rows")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--after", required=True, help="Sealed cut-off, e.g. 2026-10-26T00:00:00Z")
    parser.add_argument("--bars-start", required=True)
    parser.add_argument("--bars-end", required=True)
    parser.add_argument("--symbols", type=Path, required=True, help="JSON list of symbols")
    parser.add_argument(
        "--bars-only",
        action="store_true",
        help="Re-capture only the daily bars, keeping the account/activity receipts.",
    )
    args = parser.parse_args()
    socket.setdefaulttimeout(30)
    out = args.out.resolve()
    manifest_path = out / "manifest.json"
    manifest: dict = (
        json.loads(manifest_path.read_text()) if args.bars_only else {}
    ) | {"captured_at": datetime.now(UTC).isoformat()}
    if not args.bars_only:
        capture_accounts(out, args.after, manifest)
    symbols = sorted({str(s).upper() for s in json.loads(args.symbols.read_text())})
    capture_bars(out, symbols, args.bars_start, args.bars_end, manifest)
    write(manifest_path, {k: v for k, v in manifest.items() if k != "manifest"})
    print(json.dumps({"out": str(out), "inputs": sorted(k for k in manifest if k != "manifest")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
