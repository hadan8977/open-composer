"""Refresh only the four existing ETF rehearsal sleeves' consumed daily history.

Reuses the archive's SIP fetch, lock and replacement functions. No broker
client, universe expansion, minute feed or research process is involved.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))
import update_sip_archive as archive  # noqa: E402

from open_composer.market_sessions import (  # noqa: E402
    us_equity_session_close,
    us_equity_session_dates,
)
from open_composer.models.strategy_spec import load_strategy_spec  # noqa: E402
from open_composer.paper_rehearsal import (
    RehearsalError,
    _next_session,
    load_rehearsal_authorization,
)  # noqa: E402


def completed_session(now: datetime):
    days = us_equity_session_dates(now.date() - timedelta(days=12), now.date())
    return max(
        day
        for day in days
        if datetime.combine(day, us_equity_session_close(day), ZoneInfo("America/New_York")) < now
    )


def binding(path: Path) -> dict:
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def authorization(root, name):
    if name not in archive.SLEEVE_SPEC_NAMES:
        raise RehearsalError("Strategy is outside existing ETF resume scope")
    spec = load_strategy_spec(root / f"strategy_specs/drafts/{name}.yaml")
    auth = load_rehearsal_authorization(spec, root)
    session = _next_session(datetime.now(UTC), spec.data_assumptions.timezone)
    opening = datetime.combine(session, time(9, 30), ZoneInfo("America/New_York"))
    if opening >= datetime.fromisoformat(auth.expires_at):
        raise RehearsalError(f"{name}: next execution session exceeds original authorization")
    return auth


def permission(root: Path, strategy=None) -> None:
    hold = json.loads((root / "reports/research/control/owner-compute-hold.json").read_text())
    if not hold.get("existing_paper_operations_allowed") or not hold.get(
        "old_etf_paper_resume_20261023", {}
    ).get("allowed"):
        raise RuntimeError("Existing ETF paper operation is paused")
    if strategy:
        authorization(root, strategy)
        return
    for name in archive.SLEEVE_SPEC_NAMES:
        try:
            authorization(root, name)
            return
        except RehearsalError:
            continue
    raise RuntimeError("No existing ETF sleeve has valid execution authority")


def validate_received(frame, symbols, start, expected):
    sessions = set(us_equity_session_dates(start.date(), expected))
    if set(frame["symbol"]) != set(symbols) or frame.duplicated(["symbol", "timestamp"]).any():
        raise RuntimeError("Daily source symbol inventory or duplicate rows differ")
    for symbol, rows in frame.groupby("symbol"):
        if len(rows) != len(sessions) or set(rows.timestamp.dt.date) != sessions:
            raise RuntimeError(f"Incomplete consumed daily history for {symbol}")
    prices = frame[["open", "high", "low", "close"]]
    if not prices.map(lambda x: math.isfinite(x) and x > 0).all().all():
        raise RuntimeError("Invalid daily OHLC values")
    if not (
        (frame.high >= prices[["open", "close", "low"]].max(axis=1)).all()
        and (frame.low <= prices[["open", "close", "high"]].min(axis=1)).all()
        and ((frame.volume > 0) | (frame.trade_count > 0)).all()
    ):
        raise RuntimeError("Unusable daily OHLC or empty volume")


def check_target(root, strategy, expected):
    if strategy not in archive.SLEEVE_SPEC_NAMES:
        raise RuntimeError("Target strategy is outside existing ETF resume scope")
    target = json.loads((root / f"reports/execution/{strategy}-target-weights.json").read_text())
    summary = target.get("summary", {})
    if not (
        target.get("strategy_name") == strategy
        and summary.get("latest_session") == expected.isoformat()
        and summary.get("sleeve_guard", {}).get("marked_through") == expected.isoformat()
    ):
        raise RuntimeError(f"{strategy}: target weights or stop marks are stale")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--target-strategy")
    parser.add_argument("--strategy")
    args = parser.parse_args()
    if args.target_strategy and not args.check_only:
        parser.error("--target-strategy requires --check-only")
    root = Path.cwd().resolve()
    permission(root, args.strategy or args.target_strategy)
    now = datetime.now(UTC)
    expected = completed_session(now)
    out = root / "data/sip"
    directory = root / "reports/paper/diagnostics/old-etf-resume-20261023/inputs"
    directory.mkdir(parents=True, exist_ok=True)
    pointer = directory / "latest.json"
    symbols = archive.load_sleeve_symbols(root)
    if pointer.exists():
        saved = json.loads(pointer.read_text())
        current = (
            saved.get("status") == "ok"
            and saved.get("through") == expected.isoformat()
            and saved.get("symbols") == symbols
            and all(binding(Path(row["path"])) == row for row in saved["archive_files"])
        )
        if current:
            if args.target_strategy:
                check_target(root, args.target_strategy, expected)
            print(f"ETF daily inputs current through {expected}; {len(symbols)} symbols")
            return 0
    if args.check_only:
        raise RuntimeError(f"ETF daily input refresh required through {expected}")
    load_dotenv(root / ".env", override=False)
    from alpaca.data.historical import StockHistoricalDataClient

    from open_composer.config import alpaca_api_key_id, alpaca_api_secret_key

    client = StockHistoricalDataClient(alpaca_api_key_id(), alpaca_api_secret_key())
    stamp = now.strftime("%Y%m%dT%H%M%S%fZ")
    run = directory / stamp
    run.mkdir()
    with archive._exclusive_lock(out):
        permission(root)
        archive._refuse_if_bulk_fetch_active()
        archive._atomic_write_text(pointer, json.dumps({"status": "refreshing", "run": str(run)}))
        start = datetime(now.year - 2, 1, 1, tzinfo=UTC)
        end = datetime.combine(expected + timedelta(days=1), datetime.min.time(), UTC)
        fetched = archive._as_rows(archive._fetch(client, symbols, start, end, "daily"))
        fetched.to_parquet(run / "received.parquet", index=False)
        validate_received(fetched, symbols, start, expected)
        layout = archive.load_layout(out, "daily")["shard_symbols"]
        mapping = {}
        for year in range(now.year - 2, now.year + 1):
            mapping[year] = {}
            for index, members in layout.items():
                wanted = sorted(set(members) & set(symbols))
                if not wanted:
                    continue
                path = archive.shard_path(out, "daily", year, int(index))
                if not path.exists():
                    raise RuntimeError(f"Existing sleeve shard missing: {path}")
                for symbol in wanted:
                    mapping[year].setdefault(symbol, []).append(path)
            if set(mapping[year]) != set(symbols):
                raise RuntimeError(f"Incomplete existing shard membership for {year}")
        permission(root)
        records = archive._rewrite_batch(
            symbols,
            fetched,
            mapping,
            mode="existing_etf_paper_inputs",
            detected_at=now.isoformat(),
            max_rel_diff={},
        )
        files = sorted(
            {p for per_year in mapping.values() for paths in per_year.values() for p in paths}
        )
        receipt = {
            "status": "ok",
            "generated_at": datetime.now(UTC).isoformat(),
            "through": expected.isoformat(),
            "symbols": symbols,
            "consumed_years": list(mapping),
            "feed": "sip",
            "adjustment": "all",
            "source": binding(run / "received.parquet"),
            "rows": len(fetched),
            "archive_files": [binding(p) for p in files],
            "replacements": records,
            "broker_writes": False,
        }
        archive._atomic_write_text(run / "result.json", json.dumps(receipt, indent=2) + "\n")
        archive._atomic_write_text(pointer, json.dumps(receipt, indent=2) + "\n")
    print(f"Refreshed {len(symbols)} ETF daily histories through {expected}; {len(fetched)} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
