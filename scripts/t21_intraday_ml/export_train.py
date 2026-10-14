"""Export the training grid (t = 11 + 3j) of each panel month for the Modal LightGBM job.

scripts/heavy_run.sh --mem 0.8G -- uv run python scripts/t21_intraday_ml/export_train.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from features import FEATURES  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "data/features/t21_panel"
DST = ROOT / "data/features/t21_train"


def main() -> int:
    DST.mkdir(parents=True, exist_ok=True)
    cols = ["symbol", "d", "t", "pool_rank"] + FEATURES + ["y15", "y30", "y60"]
    for f in sorted(SRC.glob("*.parquet")):
        out = DST / f.name
        if out.exists():
            continue
        df = pd.read_parquet(f, columns=cols, filters=[("t", "in", list(range(11, 77, 3)))])
        df["symbol"] = df["symbol"].astype(str)
        df.to_parquet(out.with_suffix(".tmp"), index=False, compression="zstd")
        out.with_suffix(".tmp").replace(out)
        print("export", f.stem, len(df), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
