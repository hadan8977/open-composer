"""Receive only today's original book reconciliation prices in physical share units.

Runs in the original 22:00 UTC source slot. The canonical daily archive is
updated normally; the minute request is restricted to the original eleven
minute snapshot window and the fixed actual quant1 plan/target/holding union.
No order, account configuration, strategy ledger or schedule is written.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from open_composer.market_sessions import us_equity_session_close  # noqa: E402
from scripts import build_book_prices_file as prices  # noqa: E402
from scripts.fetch_sip_universe import _sip_safe_end  # noqa: E402


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def source_windows(day):
    start, end = prices.ny_day_bounds_utc(day)
    cut = prices.snapshot_time_utc(day)
    return {"daily": (start, end), "minute": (cut - timedelta(minutes=11), cut)}


def request_windows(day):
    """Keep the original bars, bounding the daily request by existing SIP rights."""
    windows = source_windows(day)
    start, end = windows["daily"]
    end = _sip_safe_end(end)
    close = us_equity_session_close(day)
    if close is None or end < datetime.combine(day, close, prices.NEW_YORK).astimezone(UTC):
        raise ValueError("the full regular close is not yet outside the SIP embargo")
    windows["daily"] = (start, end)
    return windows


def observation_directory(source, day, observed_at):
    """Retain a failed observation and put its explicit continuation beside it."""
    evidence = source / "data/book_close_inputs" / str(day)
    receipt = source / "data/sip_reconcile/receipts" / f"{day}.json"
    if receipt.exists():
        raise ValueError("completed execution-date source observation retained")
    if evidence.exists():
        evidence = evidence / "attempts" / observed_at.strftime("%Y%m%dT%H%M%S%fZ")
    evidence.mkdir(parents=True, exist_ok=False)
    return evidence


def real_source_rows(frame, start, end):
    """Use the original complete-schema ghost predicate and strict snapshot bounds."""
    import pandas as pd

    frame = frame.copy()
    stamp = pd.to_datetime(frame.timestamp, utc=True)
    ghost = frame.volume.eq(0) & frame.trade_count.fillna(0).eq(0)
    ghost &= frame.open.eq(frame.high) & frame.high.eq(frame.low) & frame.low.eq(frame.close)
    return frame.loc[stamp.ge(start) & stamp.lt(end) & ~ghost]


def run(args):
    import pandas as pd
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    from dotenv import load_dotenv
    from fetch_sip_universe import _clients
    from forward_refresh_io import disk_admission
    from refresh_equity_book_live import FileLock

    from open_composer.book_paper.accounts import make_trading_client
    from open_composer.book_paper.plan import read_account_state

    load_dotenv(args.credentials_root / ".env", override=False)
    now = datetime.now(UTC)
    day = args.execution_date or now.astimezone(prices.NEW_YORK).date()
    close = us_equity_session_close(day)
    if close is None or now < datetime.combine(day, close, prices.NEW_YORK):
        raise ValueError("receive the actual completed execution day only")
    if args.equity_basis != 300000 or str(day) > "2026-12-31":
        raise ValueError("original quant1 scope is $300000 through 2026-12-31")
    windows = request_windows(day)
    source = args.source_root.resolve()
    raw = source / "data/sip_reconcile"
    config = json.loads((ROOT / "config/equity-book-forward.json").read_text())
    config.update(disk_spill_bound_bytes=0, version_directory="data/book_close_inputs")
    # Original source fetch/rewrite declaration, same reserve; this stage has
    # no DuckDB queries or unrelated feature-tree copies.
    disk_admission(
        source,
        config,
        source_root=source,
        tables=[],
        live=source / "data/live/equity_book",
        stages=[],
        year=day.year,
        fetch=True,
        source_fetch_bound_bytes=2 * 1024**3,
    )
    with FileLock(ROOT / "data/live/.book_close_inputs.lock"):
        if args.update_daily:
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/update_sip_archive.py"),
                    "--kind",
                    "daily",
                    "--out",
                    str(source / "data/sip"),
                ],
                cwd=ROOT,
                check=True,
            )
        plan = args.paper_root / "reports/paper/book/quant1/plans" / f"{day}.json"
        if not plan.exists():
            print(
                json.dumps(
                    {
                        "execution_day": str(day),
                        "status": "no_quant1_plan; no reconciliation-price universe invented",
                    }
                )
            )
            return
        payload = json.loads(plan.read_text())
        if payload["execution_date"] != str(day) or payload["equity_basis"] != 300000:
            raise ValueError("current quant1 plan scope mismatch")
        target = (
            args.paper_root
            / "reports/paper/book/quant1/targets"
            / f"{payload['decision_date']}.json"
        )
        names, origins = prices.collect_symbols([plan, target])
        account = read_account_state(make_trading_client("quant1"))
        names = sorted(set(names) | set(account.positions))
        evidence = observation_directory(source, day, now)
        declaration = {
            "at_utc": now.isoformat(),
            "execution_date": str(day),
            "symbols": names,
            "before_source_requests": True,
            "actual_held": sorted(account.positions),
            "input_files": [{"path": str(p), "sha256": digest(p)} for p in [plan, target]],
            "origins": origins,
        }
        (evidence / "declared.json").write_text(json.dumps(declaration, indent=2) + "\n")
        raw.mkdir(parents=True, exist_ok=True)
        marker = raw / "price-basis.json"
        basis = {"schema_version": 1, "feed": "sip", "adjustment": "raw"}
        if marker.exists() and json.loads(marker.read_text()) != basis:
            raise ValueError("reconciliation cache already declares a different price basis")
        temporary = marker.with_suffix(".tmp")
        temporary.write_text(json.dumps(basis) + "\n")
        os.replace(temporary, marker)
        _, client = _clients()

        def receive(response, *a, **kw):
            if response.request.method != "GET":
                raise ValueError("source reader allows GET only")
            with (evidence / "http.jsonl").open("a") as stream:
                stream.write(
                    json.dumps(
                        {
                            "url": response.url,
                            "status": response.status_code,
                            "at_utc": datetime.now(UTC).isoformat(),
                            "sha256": hashlib.sha256(response.content).hexdigest(),
                        }
                    )
                    + "\n"
                )
            return response

        client._session.hooks["response"] = [receive]
        outputs = []
        for kind, (start, end) in windows.items():
            frames = []
            for i in range(0, len(names), 100):
                req = StockBarsRequest(
                    symbol_or_symbols=names[i : i + 100],
                    timeframe=TimeFrame.Day if kind == "daily" else TimeFrame.Minute,
                    start=start,
                    end=end,
                    feed="sip",
                    adjustment="raw",
                )
                frame = client.get_stock_bars(req).df
                if len(frame):
                    frames.append(frame.reset_index())
            if not frames:
                raise ValueError(f"no actual {kind} source bars for {day}")
            received = pd.concat(frames, ignore_index=True)
            received.to_parquet(evidence / f"{kind}-received.parquet", index=False)
            kept = real_source_rows(received, start, end)
            if kept.empty:
                raise ValueError(f"no real {kind} bars after original ghost rule")
            dest = raw / kind / str(day.year) / f"{day.month:02d}" / f"shard-{day}.parquet"
            dest.parent.mkdir(parents=True, exist_ok=True)
            temporary = dest.with_suffix(".received.tmp")
            kept.to_parquet(temporary, index=False)
            os.replace(temporary, dest)
            outputs.append(
                {
                    "path": str(dest.relative_to(raw)),
                    "sha256": digest(dest),
                    "rows": len(kept),
                    "query_start": start.isoformat(),
                    "query_end_exclusive": end.isoformat(),
                    "missing_names": sorted(set(names) - set(kept.symbol)),
                }
            )
        receipt = {
            "schema_version": 1,
            "feed": "sip",
            "adjustment": "raw",
            "execution_date": str(day),
            "received_at_utc": datetime.now(UTC).isoformat(),
            "outputs": outputs,
            "declared_sha256": digest(evidence / "declared.json"),
            "http_sha256": digest(evidence / "http.jsonl"),
            "no_historical_backfill": args.execution_date is None,
            "explicit_execution_date_source_recovery": args.execution_date is not None,
            "source_observation_directory": str(evidence),
            "broker_writes": 0,
            "native_code_root": str(ROOT),
        }
        dest = raw / "receipts" / f"{day}.json"
        dest.parent.mkdir(exist_ok=True)
        temporary = dest.with_suffix(".tmp")
        temporary.write_text(json.dumps(receipt, indent=2) + "\n")
        os.replace(temporary, dest)
        print(json.dumps(receipt), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--paper-root", type=Path, default=ROOT)
    parser.add_argument("--credentials-root", type=Path, default=ROOT)
    parser.add_argument("--equity-basis", type=float, required=True)
    parser.add_argument("--update-daily", action="store_true")
    parser.add_argument("--execution-date", type=date.fromisoformat,
                        help="Read-only recovery of an actual completed execution day; retain failed observations")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
