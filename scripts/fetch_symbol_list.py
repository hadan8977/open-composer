"""Fetch full daily SIP history for an explicit symbol list -- not the live
tradable universe ``fetch_sip_universe.py`` walks, but names supplied on the
command line (typically since-removed S&P 500 constituents, for the
survivorship-bias feasibility check in
docs/plan-goal-first-verification-2026-09-02.zh.md Wave W6).

Writes to a SEPARATE tree (default ``data/sip-delisted/daily/``), never into
``data/sip/``: that archive's shard numbering is keyed to the live tradable
universe (see ``assert_resumable_layout`` in ``fetch_sip_universe.py``), and
mixing an arbitrary symbol list into it would be exactly the silent-shard-
mismatch hazard that guard exists to prevent. This script is small precisely
because it does not need shard resume/layout bookkeeping: a few hundred
symbols' full daily history fits in a handful of parquet files.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_sip_universe import _clients, _fetch_batch  # noqa: E402

DEFAULT_OUT = Path("data/sip-delisted")
BATCH_SIZE = 50


def run(*, symbols: list[str], start: datetime, end: datetime, out: Path) -> int:
    _, data_client = _clients()
    destination_dir = out / "daily"
    destination_dir.mkdir(parents=True, exist_ok=True)
    total_rows = 0
    batches = [symbols[i : i + BATCH_SIZE] for i in range(0, len(symbols), BATCH_SIZE)]
    for index, batch in enumerate(batches):
        frame = _fetch_batch(data_client, batch, start, end, "daily")
        destination = destination_dir / f"batch-{index:03d}.parquet"
        if frame is None or frame.empty:
            print(f"batch {index}: no rows for {batch}")
            continue
        frame.reset_index().to_parquet(destination, compression="zstd", index=False)
        total_rows += len(frame)
        print(f"batch {index + 1}/{len(batches)}: {len(frame)} rows -> {destination}")
    print(f"done: {total_rows:,} rows across {len(batches)} batches")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols-file", type=Path, required=True, help="One ticker per line.")
    parser.add_argument("--start", default="2016-01-01")
    parser.add_argument("--end", default=None, help="Defaults to now.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")
    symbols = [
        line.strip().upper()
        for line in args.symbols_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    start = datetime.fromisoformat(args.start).replace(tzinfo=UTC)
    end = datetime.fromisoformat(args.end).replace(tzinfo=UTC) if args.end else datetime.now(UTC)
    return run(symbols=symbols, start=start, end=end, out=args.out)


if __name__ == "__main__":
    raise SystemExit(main())
