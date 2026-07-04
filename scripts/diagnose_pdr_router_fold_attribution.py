from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from open_composer.research.pdr_attribution import (  # noqa: E402
    DEFAULT_DATE_TAG,
    DEFAULT_END,
    DEFAULT_FOLDS,
    DEFAULT_OUT_DIR,
    DEFAULT_SPEC_PATH,
    DEFAULT_START,
    parse_fold_windows,
    run_pdr_router_attribution,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Attribute PDR router state and asset contributions by fold."
    )
    parser.add_argument("--spec", default=str(DEFAULT_SPEC_PATH))
    parser.add_argument("--label", default=None)
    parser.add_argument(
        "--data-source", default="longbridge", choices=["longbridge", "alpaca", "sample"]
    )
    parser.add_argument("--feed", default=None)
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    parser.add_argument(
        "--folds",
        default=None,
        help=(
            "Comma-separated name:start:end windows. "
            f"Default uses {len(DEFAULT_FOLDS)} long-window folds."
        ),
    )
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--date-tag", default=DEFAULT_DATE_TAG)
    args = parser.parse_args()

    payload = run_pdr_router_attribution(
        Path(args.spec),
        root=ROOT,
        label=args.label,
        data_source=args.data_source,
        feed=args.feed,
        start=args.start,
        end=args.end,
        folds=parse_fold_windows(args.folds),
        out_dir=Path(args.out_dir),
        date_tag=args.date_tag,
    )
    print(json.dumps(payload["parity_check"], indent=2, sort_keys=True))
    for label, path in payload["artifact_paths"].items():
        print(f"{label}: {path}")


if __name__ == "__main__":
    main()
