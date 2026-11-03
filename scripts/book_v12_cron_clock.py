"""Select the existing book cron minute using the exchange close and New York DST.

This is only a clock predicate: it never invokes the driver or enables submissions.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from open_composer.market_sessions import NEW_YORK, us_equity_session_close  # noqa: E402

OFFSETS = {"plan": 90, "submit": 40, "retry": 22}


def due(mode: str, now: datetime) -> bool:
    if now.tzinfo is None:
        raise ValueError("clock requires a timezone-aware instant")
    local = now.astimezone(NEW_YORK)
    close = us_equity_session_close(local.date())
    if close is None:
        return False
    expected = datetime.combine(local.date(), close, tzinfo=NEW_YORK) - timedelta(
        minutes=OFFSETS[mode]
    )
    return local.replace(second=0, microsecond=0) == expected


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=OFFSETS)
    args = parser.parse_args(argv)
    return 0 if due(args.mode, datetime.now(UTC)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
