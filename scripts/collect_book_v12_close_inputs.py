"""Receive today's book reconciliation prices (raw SIP, physical share units).

Runs in the original 22:00 UTC source slot. The canonical daily archive is updated normally;
the minute request is restricted to the original eleven-minute snapshot window and the actual
quant1 plan/target/holding names. The bars go to ``<source>/data/sip_reconcile`` with a receipt
that ``build_book_prices_file.py`` reads; a date that already has a receipt is left as is, and the
RAW price-basis marker is written once. No order or ledger is written.
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
    from refresh_equity_book_live import FileLock

    from open_composer.book_paper.accounts import make_trading_client
    from open_composer.book_paper.plan import read_account_state

    load_dotenv(args.credentials_root / ".env", override=False)
    now = datetime.now(UTC)
    day = args.execution_date or now.astimezone(prices.NEW_YORK).date()
    close = us_equity_session_close(day)
    if close is None or now < datetime.combine(day, close, prices.NEW_YORK):
        raise ValueError("receive the actual completed execution day only")
    windows = request_windows(day)
    source = args.source_root.resolve()
    raw = source / "data/sip_reconcile"
    receipt_path = raw / "receipts" / f"{day}.json"
    if receipt_path.exists():
        print(json.dumps({"execution_day": str(day), "status": "already_received"}))
        return
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
            print(json.dumps({"execution_day": str(day), "status": "no_quant1_plan"}))
            return
        decision = json.loads(plan.read_text())["decision_date"]
        target = args.paper_root / "reports/paper/book/quant1/targets" / f"{decision}.json"
        names, _ = prices.collect_symbols([plan, target])
        account = read_account_state(make_trading_client("quant1"))
        names = sorted(set(names) | set(account.positions))
        raw.mkdir(parents=True, exist_ok=True)
        basis = raw / "price-basis.json"
        if not basis.exists():  # this cache is RAW only; the marker is never rewritten
            basis.write_text(
                json.dumps({"schema_version": 1, "feed": "sip", "adjustment": "raw"}) + "\n"
            )
        _, client = _clients()
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
            kept = (
                real_source_rows(pd.concat(frames, ignore_index=True), start, end)
                if frames
                else pd.DataFrame()
            )
            if kept.empty:
                raise ValueError(f"no {kind} source bars for {day}")
            dest = raw / kind / str(day.year) / f"{day.month:02d}" / f"shard-{day}.parquet"
            dest.parent.mkdir(parents=True, exist_ok=True)
            temporary = dest.with_suffix(".received.tmp")
            kept.to_parquet(temporary, index=False)
            os.replace(temporary, dest)
            with dest.open("rb") as stream:
                sha256 = hashlib.file_digest(stream, "sha256").hexdigest()
            outputs.append(
                {
                    "path": str(dest.relative_to(raw)),
                    "sha256": sha256,  # build_book_prices_file matches the files to this receipt
                    "rows": len(kept),
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
        }
        receipt_path.parent.mkdir(exist_ok=True)
        temporary = receipt_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(receipt, indent=2) + "\n")
        os.replace(temporary, receipt_path)
        print(json.dumps(receipt), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--paper-root", type=Path, default=ROOT)
    parser.add_argument("--credentials-root", type=Path, default=ROOT)
    parser.add_argument(
        "--equity-basis", type=float, help="accepted for the existing cron line; not used"
    )
    parser.add_argument("--update-daily", action="store_true")
    parser.add_argument(
        "--execution-date",
        type=date.fromisoformat,
        help="receive an earlier completed execution day again",
    )
    run(parser.parse_args())


if __name__ == "__main__":
    main()
