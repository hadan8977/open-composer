"""Publish the balance and current stock marks of an Alpaca Paper account."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from scripts.capture_paper_forward_inputs import ACCOUNTS, ROOT, trading_client
from scripts.publish_paper_forward_projection import atomic_write


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("account", choices=ACCOUNTS)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    client = trading_client(args.account)
    account = client.get_account()
    row = dict(
        account=args.account,
        at=datetime.now(UTC).isoformat(),
        equity_usd=float(account.equity),
        cash_usd=float(account.cash),
    )
    path = args.out or ROOT / f"runtime/paper/account-{args.account}-snapshot.json"
    atomic_write(path, json.dumps(row, allow_nan=False).encode())

    positions = client.get_all_positions()
    marks = {
        position.symbol: position.current_price
        for position in positions
        if position.asset_class.value == "us_equity"
    }
    payload = dict(at=datetime.now(UTC).isoformat(), marks=marks)
    atomic_write(path.with_name(f"account-{args.account}-marks.json"), json.dumps(payload).encode())


if __name__ == "__main__":
    main()
