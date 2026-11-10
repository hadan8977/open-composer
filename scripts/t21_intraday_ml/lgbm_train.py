"""T-20261006-21: monthly rolling LightGBM fits and predictions (runs on Modal, or locally on small data).

    python3 scripts/modal_run.py --job t21-intraday --cpu 8 --memory-gib 32 --timeout-min 90 --shards 4 \
        --data data/features/t21_train --out data/research/t21/preds/LGBM \
        -- uv run python scripts/t21_intraday_ml/lgbm_train.py --shard {shard} --nshards {nshards}

Training rows: months m-12..m-1 (last trading day dropped = one-session gap), grid t = 11 + 3j,
pool_rank <= N, finite label (clipped at +-5 %).  Fixed hyper-parameters (hypotheses.md section 4).
Output: <out>/N<n>_H<h>/<month>.parquet with columns symbol, d, t, pred (bp).
With --placebo-seed s the label is permuted within each (day, t) cross-section before fitting.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from features import FEATURES  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
TRAIN = ROOT / "data/features/t21_panel"
GRID3 = list(range(11, 77, 3))
COLS = ["symbol", "d", "t", "pool_rank"] + FEATURES + ["y15", "y30", "y60"]
NS, HS = (100, 300, 600), (15, 30, 60)
LABEL_CLIP = 0.05
PARAMS = dict(
    objective="regression",
    num_leaves=31,
    learning_rate=0.05,
    n_estimators=200,
    min_child_samples=1000,
    colsample_bytree=0.8,
    subsample=0.5,
    subsample_freq=1,
    reg_lambda=10.0,
    verbose=-1,
)


def window_months(month: str) -> list[str]:
    p = pd.Period(month, "M")
    return [str(p - i) for i in range(12, 0, -1)]


def load(months: list[str]) -> pd.DataFrame:
    frames = []
    for mo in months:
        f = TRAIN / f"{mo}.parquet"
        if f.exists():
            frames.append(pd.read_parquet(f, columns=COLS, filters=[("t", "in", GRID3)]))
    df = pd.concat(frames, ignore_index=True)
    df["d"] = pd.to_datetime(df["d"])
    return df


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--nshards", type=int, default=1)
    ap.add_argument("--months", nargs="*")
    ap.add_argument("--out", default=str(ROOT / "data/research/t21/preds/LGBM"))
    ap.add_argument("--placebo-seed", type=int, default=None)
    ap.add_argument("--cells", nargs="*", help="e.g. N300_H30; default all nine")
    ap.add_argument("--threads", type=int, default=0)
    a = ap.parse_args()
    months = a.months or sorted(p.stem for p in TRAIN.glob("*.parquet") if p.stem >= "2024-01")
    months = months[a.shard :: a.nshards]
    cells = [(n, h) for n in NS for h in HS if not a.cells or f"N{n}_H{h}" in a.cells]
    out = Path(a.out)
    for mo in months:
        todo = [(n, h) for n, h in cells if not (out / f"N{n}_H{h}" / f"{mo}.parquet").exists()]
        if not todo:
            continue
        t0 = time.time()
        tr = load(window_months(mo))
        last_day = tr["d"].max()
        tr = tr[tr["d"] < last_day]  # one-session gap
        te = load([mo])
        for n, h in todo:
            m = h // 5
            a_tr = tr[(tr["pool_rank"] <= n)].copy()
            y = np.clip(a_tr[f"y{h}"].to_numpy("float64"), -LABEL_CLIP, LABEL_CLIP)
            ok = np.isfinite(y)
            a_tr, y = a_tr[ok], y[ok]
            if a.placebo_seed is not None:
                rng = np.random.default_rng(a.placebo_seed * 1000003 + n * 31 + h)
                grp = a_tr.groupby(["d", "t"]).ngroup().to_numpy()
                y = (
                    pd.Series(y)
                    .groupby(grp)
                    .transform(lambda v: rng.permutation(v.to_numpy()))
                    .to_numpy()
                )
            model = lgb.LGBMRegressor(**PARAMS, n_jobs=a.threads or -1, random_state=20261006)
            model.fit(a_tr[FEATURES].to_numpy("float32"), (y * 1e4).astype("float32"))
            msk = (te["pool_rank"] <= n) & (((te["t"].astype(int) - 11) % m) == 0)
            sub = te.loc[msk, ["symbol", "d", "t"]].copy()
            sub["pred"] = model.predict(te.loc[msk, FEATURES].to_numpy("float32")).astype("float32")
            f = out / f"N{n}_H{h}" / f"{mo}.parquet"
            f.parent.mkdir(parents=True, exist_ok=True)
            sub.to_parquet(f, index=False)
        print(
            f"lgbm {mo} cells={len(todo)} train_rows~{len(tr)} {time.time() - t0:.0f}s", flush=True
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
