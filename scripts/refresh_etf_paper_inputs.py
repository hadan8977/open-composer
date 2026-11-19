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
    ETF_INPUT_STATUS,
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
    frozen = dict.fromkeys(set(symbols) - set(frame.symbol), "missing_daily_history")
    for symbol, rows in frame.groupby("symbol"):
        prices = rows[["open", "high", "low", "close"]]
        if len(rows) != len(sessions) or set(rows.timestamp.dt.date) != sessions:
            frozen[symbol] = "incomplete_daily_history"
        elif not (
            prices.map(lambda x: math.isfinite(x) and x > 0).all().all()
            and (rows.high >= prices[["open", "close", "low"]].max(axis=1)).all()
            and (rows.low <= prices[["open", "close", "high"]].min(axis=1)).all()
            and ((rows.volume > 0) | (rows.trade_count > 0)).all()
        ):
            frozen[symbol] = "invalid_daily_bar"
    if not set(symbols) - frozen.keys():
        raise RuntimeError(f"No usable ETF daily history through {expected}")
    return frozen


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
    pointer = root / ETF_INPUT_STATUS
    directory = pointer.parent
    directory.mkdir(parents=True, exist_ok=True)
    symbols = archive.load_sleeve_symbols(root)
    if pointer.exists():
        saved = json.loads(pointer.read_text())
        current = saved.get("status") == "ok" and saved.get("through") == expected.isoformat()
        if current:
            if args.target_strategy:
                check_target(root, args.target_strategy, expected)
            print(f"ETF daily inputs current through {expected}; {len(symbols)} symbols")
            return 0
    if args.check_only:
        raise RuntimeError(f"ETF daily input refresh required through {expected}")
    load_dotenv(root / ".env", override=False)
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

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
        frozen = validate_received(fetched, symbols, start, expected)
        raw = archive._as_rows(
            client.get_stock_bars(
                StockBarsRequest(
                    symbol_or_symbols=symbols,
                    timeframe=TimeFrame.Day,
                    feed="sip",
                    adjustment="raw",
                    start=end - timedelta(days=1),
                    end=end,
                )
            ).df
        )
        if raw.empty:
            raise RuntimeError(f"No raw ETF close on {expected}")
        raw = raw.loc[~raw.symbol.duplicated(keep=False)].set_index("symbol").close
        last = fetched.loc[fetched.timestamp.dt.date == expected].set_index("symbol").close
        for symbol in set(symbols) - frozen.keys():
            if symbol not in raw or not math.isfinite(raw[symbol]) or raw[symbol] <= 0:
                frozen[symbol] = "missing_raw_close"
            elif abs(raw[symbol] - last[symbol]) > 0.005051:
                frozen[symbol] = "raw_adjusted_unit_mismatch"
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
                    continue
                for symbol in wanted:
                    mapping[year].setdefault(symbol, []).append(path)
            for symbol in set(symbols) - mapping[year].keys():
                frozen[symbol] = f"missing_archive_shard_{year}"
        usable = sorted(set(symbols) - frozen.keys())
        if not usable:
            raise RuntimeError(f"No usable ETF archive histories through {expected}")
        for symbol, reason in sorted(frozen.items()):
            print(f"FROZEN {symbol}: {reason}", flush=True)
        permission(root)
        records = archive._rewrite_batch(
            usable,
            fetched.loc[fetched.symbol.isin(usable)],
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
            "frozen_symbols": frozen,
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
