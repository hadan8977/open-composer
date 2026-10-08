#!/usr/bin/env python3
# ruff: noqa: E501
"""T-20261007-01: export the FC_EW fast composite of P1 stage 0 as a (trade_date, symbol) store.

``scripts/p1_stage0_decay.py`` keeps FC_EW only inside its cache (``C_<year>.npy``, column 0), and that cache
was not copied back from Modal.  This script reruns the *build* stage of the same file into a scratch cache
(unchanged code, unchanged signs rule) and writes the composite exactly as ``build_composites`` computes it
(per date: rank-normal of each of the 60 fast inputs over all signal-store rows of the date, missing = 0,
mean over the 60).  Nothing is measured here.  Only dates <= 2026-09-17 are read by the build.

    python3 scripts/modal_run.py --job t0701-fast-store ... -- uv run python scripts/t0701_fast_store.py \
        --cache-dir /tmp/t0701-cache --out data/research/t0701_store
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import ndtri

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import p1_stage0_decay as p1  # noqa: E402

LAST_DATA = "2026-09-17"


def fc_ew_year(X60: np.ndarray, di: np.ndarray) -> np.ndarray:
    """Copy of the FC_EW column of ``p1_stage0_decay.build_composites`` for one year (rows sorted by date)."""
    out = np.full(len(di), np.nan, dtype="float32")
    cut = np.flatnonzero(np.diff(di)) + 1
    starts = np.concatenate([[0], cut])
    ends = np.concatenate([cut, [len(di)]])
    for a, b in zip(starts, ends, strict=True):
        rk = pd.DataFrame(X60[a:b]).rank(axis=0, method="average", na_option="keep").to_numpy()
        fin = np.isfinite(rk)
        cnt = fin.sum(axis=0)
        with np.errstate(invalid="ignore", divide="ignore"):
            z = np.where(fin, ndtri((rk - 0.5) / np.maximum(cnt, 1)), 0.0)
        out[a:b] = z.mean(axis=1)
    return out


def main(argv: list[str] | None = None) -> None:
    import warnings

    warnings.filterwarnings("ignore", category=RuntimeWarning)
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache-dir", default="/tmp/t0701-cache")
    ap.add_argument("--out", default=str(ROOT / "data/research/t0701_store"))
    a = ap.parse_args(argv)
    cfg = p1.Cfg(cache=Path(a.cache_dir))
    t0 = time.time()
    if not (cfg.cache / "build.done").exists():
        p1.stage_build(cfg)
    ctx = p1.Ctx(cfg)
    signs = p1.load_signs(cfg)
    n_a = len(ctx.meta["lib"])
    frames = []
    for y in ctx.years:
        rows = ctx.rows(y)
        di, si = rows["di"], rows["si"]
        if len(di) == 0:
            continue
        X, _ = p1.year_matrix(cfg, y, signs)
        X60 = np.hstack([X[:, :n_a], X[:, n_a : n_a + len(p1.OBJ_B)]]).astype("float64")
        assert X60.shape[1] == 60, X60.shape
        fc = fc_ew_year(X60, di)
        frames.append(
            pd.DataFrame(
                {
                    "trade_date": ctx.D[di].astype("datetime64[ns]"),
                    "symbol": ctx.symbols[si],
                    "fc_ew": fc,
                }
            )
        )
        print(f"year {y}: {len(di)} rows", flush=True)
        del X, X60
    df = pd.concat(frames, ignore_index=True)
    df = df[df["trade_date"] <= pd.Timestamp(LAST_DATA)]
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out / "fc_ew.parquet", index=False)
    first_valid = str(df.loc[df["fc_ew"].notna(), "trade_date"].min().date())
    meta = {
        "rows": int(len(df)),
        "dates": int(df["trade_date"].nunique()),
        "first_date": str(df["trade_date"].min().date()),
        "last_date": str(df["trade_date"].max().date()),
        "first_valid_date": first_valid,
        "signs": {k: signs[k] for k in ("ON5", "ID5")},
        "elapsed_s": round(time.time() - t0, 1),
    }
    (out / "fc_ew_meta.json").write_text(json.dumps(meta, indent=1, default=str))
    print(json.dumps(meta, default=str), flush=True)


if __name__ == "__main__":
    main()
