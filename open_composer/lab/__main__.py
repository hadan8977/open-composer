"""Small offline entry point; native research programs can import the same API."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from open_composer.lab.example import run_example


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["example"])
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--batch", required=True, help="New immutable batch id")
    args = parser.parse_args()
    result = run_example(args.root, batch_id=args.batch)
    print(
        json.dumps(
            {
                "folder": str(result.folder),
                "n_trials": result.n_trials,
                "results": {key: str(path) for key, path in result.results.items()},
                "failures": result.failures,
                "kind": "diagnostic_synthetic_fixture",
                "ablations": str(result.folder / "ablations.json"),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
