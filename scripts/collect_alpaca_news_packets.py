"""Step 13 Track L, L0: CLI for open_composer.research.news.collector.

docs/plan-step-13-recent-high-return-ml-and-llm-tracks-2026-09-09.zh.md
section 4.1.

Usage::

    # One-day smoke test before paying for the full 2024-01-01..today pull:
    uv run python scripts/collect_alpaca_news_packets.py --smoke-day 2024-06-03

    # Full historical backfill (resumable -- safe to kill and rerun):
    uv run python scripts/collect_alpaca_news_packets.py --start 2024-01-01

    # Forward mode (daily cron target -- last 3 days, always fresh fetch):
    uv run python scripts/collect_alpaca_news_packets.py --forward

Credentials come from ``.env`` via ``load_dotenv()`` below -- this script
loads it once at startup and never reads or prints its contents; the actual
HTTP calls read ``ALPACA_API_KEY_ID``/``ALPACA_API_SECRET_KEY`` out of
``os.environ`` through ``open_composer.config`` (see collector.py's
docstring).
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

from open_composer.research.news.collector import (  # noqa: E402
    collect_day,
    collect_forward,
    collect_historical_range,
    consolidate_year,
)


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--smoke-day",
        type=_parse_date,
        default=None,
        help="fetch exactly one historical day and print a summary, no consolidation "
        "(cheap correctness check before the full backfill)",
    )
    parser.add_argument(
        "--start",
        type=_parse_date,
        default=date(2024, 1, 1),
        help="historical backfill start date (default 2024-01-01, plan section 4.1)",
    )
    parser.add_argument(
        "--end",
        type=_parse_date,
        default=None,
        help="historical backfill end date (default: today, UTC)",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="re-fetch every day even if its _daily/ file already exists",
    )
    parser.add_argument(
        "--forward",
        action="store_true",
        help="forward mode: re-fetch the last --lookback-days days fresh (cron target)",
    )
    parser.add_argument("--lookback-days", type=int, default=3)
    parser.add_argument(
        "--consolidate-years",
        type=int,
        nargs="*",
        default=None,
        help="after a historical run, consolidate these years into {year}.parquet "
        "(default: every year touched by --start/--end)",
    )
    return parser.parse_args()


def main() -> int:
    load_dotenv(dotenv_path=ROOT / ".env")
    args = _parse_args()

    if args.smoke_day:
        print(
            f"[{time.strftime('%H:%M:%S')}] smoke-testing one day: {args.smoke_day} ...", flush=True
        )
        frame = collect_day(args.smoke_day, historical=True)
        print(f"fetched {len(frame)} articles for {args.smoke_day}", flush=True)
        if not frame.empty:
            print(
                frame[["id", "created_at", "visible_at", "symbols", "headline"]]
                .head(5)
                .to_string(),
                flush=True,
            )
        return 0

    if args.forward:
        print(
            f"[{time.strftime('%H:%M:%S')}] forward collection, last {args.lookback_days} days ...",
            flush=True,
        )
        summary = collect_forward(lookback_days=args.lookback_days)
        print(summary, flush=True)
        years = {date.today().year}
        for year in sorted(years):
            path = consolidate_year(year)
            print(f"consolidated {year} -> {path}", flush=True)
        return 0

    end = args.end or datetime.utcnow().date()
    print(
        f"[{time.strftime('%H:%M:%S')}] historical collection {args.start} .. {end} "
        f"(resume={not args.no_resume}) ...",
        flush=True,
    )

    def _progress(day: date, count: int) -> None:
        print(f"  {day}: {count} articles", flush=True)

    summary = collect_historical_range(
        args.start, end, resume=not args.no_resume, progress=_progress
    )
    print(summary, flush=True)

    years = (
        set(args.consolidate_years)
        if args.consolidate_years
        else set(range(args.start.year, end.year + 1))
    )
    for year in sorted(years):
        path = consolidate_year(year)
        print(f"consolidated {year} -> {path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
