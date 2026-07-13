from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from open_composer.config import project_root
from open_composer.research.momentum_observation_cycle import run_momentum_observation_cycle


def main() -> int:
    parser = argparse.ArgumentParser(description="Run broker-free momentum observation cycle")
    parser.add_argument(
        "--spec",
        type=Path,
        default=Path("strategy_specs/drafts/us_mom_minute_p1_003_frozen.yaml"),
    )
    parser.add_argument("--as-of")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    as_of = datetime.fromisoformat(args.as_of.replace("Z", "+00:00")) if args.as_of else None
    result = run_momentum_observation_cycle(
        args.spec,
        project_root(),
        as_of=as_of,
        refresh=args.refresh,
        dry_run=args.dry_run,
    )
    print(f"status={result.status} receipt={result.receipt_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
