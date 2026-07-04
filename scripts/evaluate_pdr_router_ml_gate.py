from __future__ import annotations

import argparse
import json
from pathlib import Path

from open_composer.config import project_root
from open_composer.research.pdr_ml_gate_evaluation import (
    DEFAULT_END,
    DEFAULT_START,
    evaluate_pdr_router_ml_gate,
)

DEFAULT_SPEC = "strategy_specs/drafts/nasdaq_tqqq_pdr_router_mlgate_iter1.yaml"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate baseline vs PDR ML-gated route on the same dataset."
    )
    parser.add_argument("--spec", default=DEFAULT_SPEC)
    parser.add_argument(
        "--data-source", default="longbridge", choices=["longbridge", "alpaca", "sample"]
    )
    parser.add_argument("--feed", default=None)
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    parser.add_argument("--report-date", default=None)
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args()

    root = project_root()
    spec_path = Path(args.spec)
    if not spec_path.is_absolute():
        spec_path = root / spec_path
    payload = evaluate_pdr_router_ml_gate(
        spec_path,
        root=root,
        data_source=args.data_source,
        feed=args.feed,
        start=args.start,
        end=args.end,
        report_date=args.report_date,
        output_dir=Path(args.output_dir) if args.output_dir else None,
    )
    print(json.dumps(payload["acceptance_gate"], indent=2, sort_keys=True))
    print(f"json: {payload['artifact_paths']['json']}")
    print(f"markdown: {payload['artifact_paths']['markdown']}")
    if not payload["acceptance_gate"]["ml_gate_beats_fixed_route"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
