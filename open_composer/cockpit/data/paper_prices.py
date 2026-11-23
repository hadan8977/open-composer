"""Read the current stock marks published for the paper dashboard."""

from __future__ import annotations

import json
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from open_composer.market_sessions import NEW_YORK, us_equity_session_close

PACIFIC = ZoneInfo("America/Los_Angeles")


def local_stamp(value: datetime) -> str:
    return value.astimezone(PACIFIC).strftime("%m-%d %H:%M:%S %Z")


def load_paper_prices(root: Path) -> dict:
    try:
        data = json.loads((root / "runtime/paper/position-prices.json").read_text())
    except (OSError, ValueError):
        return {}
    now = datetime.now(UTC)
    ny = now.astimezone(NEW_YORK)
    close = us_equity_session_close(ny.date())
    session_open = close is not None and time(9, 30) <= ny.time() < close
    captured_at = datetime.fromisoformat(data["at"])
    data["session_open"] = session_open
    data["stale"] = session_open and now - captured_at > timedelta(minutes=1)
    data["at"] = local_stamp(captured_at)
    for row in data["rows"]:
        if row["at"]:
            quote_at = datetime.fromisoformat(row["at"])
            row["stale"] = session_open and now - quote_at > timedelta(minutes=3)
            row["at"] = local_stamp(quote_at)
    return data
