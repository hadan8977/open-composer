"""Observed account marks when a missing strategy plan prevents attribution."""
from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from open_composer.book_paper.accounts import BOOK_ACCOUNTS, make_trading_client


def capture_account_valuation(
    root: Path, account_alias: str, requested_ledger_date: date, *, client: Any | None = None,
) -> Path:
    if account_alias not in BOOK_ACCOUNTS:
        raise ValueError("unknown book account alias")
    client = client or make_trading_client(account_alias)
    started = datetime.now(UTC)
    account = client.get_account()
    clock = client.get_clock()
    finished = datetime.now(UTC)
    payload = {
        "account_alias": account_alias,
        "requested_ledger_date": requested_ledger_date.isoformat(),
        "request_started_at_UTC": started.isoformat(),
        "observed_at_UTC": finished.isoformat(),
        "broker_clock": str(clock.timestamp),
        "basis": "broker_account_mark_as_observed",
        "strategy_attribution": None,
        "missing_plan": True,
        "historical_fills_reconstructed": False,
        "readonly": True,
        "account": {name: str(getattr(account, name, "")) for name in (
            "equity", "last_equity", "cash", "long_market_value", "short_market_value",
            "initial_margin", "maintenance_margin", "buying_power",
        )},
    }
    directory = root / "reports/paper/book" / account_alias / "account-valuations"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (finished.strftime("%Y%m%dT%H%M%S%fZ") + ".json")
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, indent=2) + "\n")
    return path
