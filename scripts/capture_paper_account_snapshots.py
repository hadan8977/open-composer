"""Publish the current balance of an Alpaca Paper account."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, time
from pathlib import Path

from open_composer.market_sessions import NEW_YORK, us_equity_session_close
from scripts.capture_paper_forward_inputs import ACCOUNTS, ROOT, account_activities, trading_client
from scripts.publish_paper_forward_projection import EXTERNAL, atomic_write


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

    local = datetime.now(NEW_YORK)
    close = us_equity_session_close(local.date())
    if close is None or not time(9, 30) <= local.time() < close:
        return
    start = datetime.combine(local.date(), time(), tzinfo=NEW_YORK)
    marks = {}
    if args.account != "quant1":
        marks = {p.symbol: p.current_price for p in client.get_all_positions()}
        row["at"] = datetime.now(UTC).isoformat()
    relevant = EXTERNAL if args.account == "quant1" else {"FILL"}
    activities = account_activities(
        client, start.isoformat(), before=row["at"], activity_types=relevant
    )
    row.update(marks=marks, activities=activities)
    intraday = path.with_name(f"home-{args.account}.json")
    atomic_write(intraday, json.dumps(row, allow_nan=False).encode())


if __name__ == "__main__":
    main()
