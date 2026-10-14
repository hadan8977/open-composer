"""T-20261006-21 driver: moments -> linear fits/predictions -> simulation of every registered variant.

    scripts/heavy_run.sh --mem 0.8G -- uv run python scripts/t21_intraday_ml/run_pipeline.py moments
    scripts/heavy_run.sh --mem 0.8G -- uv run python scripts/t21_intraday_ml/run_pipeline.py lin [--months 2024-01 ...]
    scripts/heavy_run.sh --mem 0.8G -- uv run python scripts/t21_intraday_ml/run_pipeline.py baselines
    scripts/heavy_run.sh --mem 0.8G -- uv run python scripts/t21_intraday_ml/run_pipeline.py sim --model LIN

Everything is per month and restartable (a month whose output exists is skipped).
Outputs under data/research/t21/: moments/<month>.npz, preds/<MODEL>/N<n>_H<h>/<month>.parquet,
daily/<variant>/x<cm>/<month>.parquet, models/LIN_<month>.json.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lin  # noqa: E402
import portfolio as P  # noqa: E402
from features import FEATURES  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
PANEL = Path(os.environ.get("T21_PANEL", ROOT / "data/features/t21_panel"))
OUT = Path(os.environ.get("T21_OUT", ROOT / "data/research/t21"))
FIRST_OOS = "2024-01"
NS, HS, KS = (100, 300, 600), (15, 30, 60), (0, 1, 2)
CMULTS = (0.5, 1.0, 2.0)
REDO = (
    os.environ.get("T21_REDO") == "1"
)  # rerun only k>0 at cost tiers != 1 into daily_fix (k filter fix)
SIM_COLS = ["symbol", "d", "t", "pool_rank", "px_prev", "adv21", "vol21", "beta"]


def all_months() -> list[str]:
    return sorted(p.stem for p in PANEL.glob("*.parquet"))


def grid3_filter() -> list[int]:
    return list(range(11, 77, 3))


def read_panel(month: str, cols: list[str], grid3: bool = True) -> pd.DataFrame:
    filt = [("t", "in", grid3_filter())] if grid3 else None
    df = pd.read_parquet(PANEL / f"{month}.parquet", columns=cols, filters=filt)
    df["d"] = pd.to_datetime(df["d"])
    df["symbol"] = df["symbol"].astype(str)
    return df


def stage_moments(months: list[str]) -> None:
    (OUT / "moments").mkdir(parents=True, exist_ok=True)
    cols = ["symbol", "d", "t", "pool_rank"] + FEATURES + [f"y{h}" for h in HS]
    for mo in months:
        f = OUT / "moments" / f"{mo}.npz"
        if f.exists():
            continue
        df = read_panel(mo, cols)
        acc = lin.accumulate_month(df)
        np.savez_compressed(f, days=acc["days"].astype("datetime64[D]"), M=acc["M"])
        print("moments", mo, len(df), flush=True)


def window_months(month: str) -> list[str]:
    p = pd.Period(month, "M")
    return [str(p - i) for i in range(12, 0, -1)]


def load_window(month: str) -> tuple[np.ndarray, np.ndarray]:
    """Moment arrays of the 12 prior months, last trading day dropped (one-session gap): (days, M)."""
    days, Ms = [], []
    for mo in window_months(month):
        f = OUT / "moments" / f"{mo}.npz"
        if not f.exists():
            continue
        z = np.load(f)
        days.append(z["days"])
        Ms.append(z["M"])
    d = np.concatenate(days)
    M = np.concatenate(Ms, axis=0)
    return d[:-1], M[:-1]


def stage_lin(months: list[str]) -> None:
    (OUT / "models").mkdir(parents=True, exist_ok=True)
    cols = ["symbol", "d", "t", "pool_rank"] + FEATURES
    for mo in months:
        todo = [
            (n, h)
            for n in NS
            for h in HS
            if not (OUT / "preds/LIN" / f"N{n}_H{h}" / f"{mo}.parquet").exists()
        ]
        if not todo:
            continue
        days, M = load_window(mo)
        if len(days) < 150:
            print("lin", mo, "window too short", len(days), flush=True)
            continue
        df = read_panel(mo, cols)
        x = lin.prep_x(df)
        info = {}
        for n, h in todo:
            ni, hi = lin.NS.index(n), lin.HS.index(h)
            Mw = M[:, ni, hi]
            fit_m, val_m = Mw[: -lin.VAL_DAYS].sum(0), Mw[-lin.VAL_DAYS :].sum(0)
            sel = lin.fit_window(fit_m, val_m)
            model = lin.fit_window(Mw.sum(0), None, sel["kind"], sel["param"])
            msk = (df["pool_rank"].to_numpy() <= n) & (
                ((df["t"].to_numpy().astype(int) - 11) % (h // 5)) == 0
            )
            pred = lin.predict_bp(model, x[msk])
            out = df.loc[msk, ["symbol", "d", "t"]].copy()
            out["pred"] = pred.astype("float32")
            f = OUT / "preds/LIN" / f"N{n}_H{h}" / f"{mo}.parquet"
            f.parent.mkdir(parents=True, exist_ok=True)
            out.to_parquet(f, index=False)
            info[f"N{n}_H{h}"] = {
                "kind": model["kind"],
                "param": model["param"],
                "nz": model["nz"],
                "n_train": model["n"],
            }
        (OUT / "models" / f"LIN_{mo}.json").write_text(json.dumps(info, indent=1))
        print("lin", mo, {k: (v["kind"], v["param"]) for k, v in info.items()}, flush=True)


def variant_specs(model: str | None = None):
    for m in [model] if model else ["LIN", "LGBM"]:
        for n in NS:
            for h in HS:
                for k in KS:
                    yield {"id": f"{m}_N{n}_H{h}_K{k}", "family": m, "N": n, "h": h, "k": k}


def baseline_specs():
    for n in NS:
        yield {"id": f"B1_EODREV_N{n}", "family": "B1", "N": n, "h": 25, "k": 0}
    for fam, tag in (("B2", "B2_HKS"), ("B3", "B3_STR")):
        for n in NS:
            for h in HS:
                yield {"id": f"{tag}_N{n}_H{h}", "family": fam, "N": n, "h": h, "k": 0}


def _run_sim(spec: dict, panel: pd.DataFrame, month: str, preds: pd.DataFrame | None) -> None:
    n, h, k = spec["N"], spec["h"], spec["k"]
    df = panel[panel["pool_rank"] <= n].copy()
    first_t = 11
    if spec["family"] in ("LIN", "LGBM"):
        df = df.merge(preds, on=["symbol", "d", "t"], how="inner")
    elif spec["family"] == "B1":
        df = df[df["t"] == 71].copy()
        df["pred"] = -df["r_open_rel"]
        first_t = 71
    elif spec["family"] == "B2":
        df["pred"] = df[f"b2_{h}"]
    else:
        df["pred"] = -df["r30_rel"]
    df["ret"] = df[f"ret{h}"]
    df["spy"] = df[f"spy{h}"]
    for cm in CMULTS:
        if REDO and (cm == 1.0 or k == 0):
            continue
        f = OUT / ("daily_fix" if REDO else "daily") / spec["id"] / f"x{cm}" / f"{month}.parquet"
        if f.exists():
            continue
        d = P.simulate(df, h, k=k, cmult=cm, first_t=first_t)
        f.parent.mkdir(parents=True, exist_ok=True)
        d.to_parquet(f, index=False)


def stage_sim(months: list[str], model: str | None, baselines: bool) -> None:
    base_cols = SIM_COLS + [f"ret{h}" for h in HS + (25,)] + [f"spy{h}" for h in HS + (25,)]
    extra = ["b2_15", "b2_30", "b2_60", "r30_rel", "r_open_rel"] if baselines else []
    for mo in months:
        panel = read_panel(mo, base_cols + extra)
        for spec in list(baseline_specs()) if baselines else list(variant_specs(model)):
            preds = None
            if not baselines:
                pf = (
                    OUT / f"preds/{spec['family']}" / f"N{spec['N']}_H{spec['h']}" / f"{mo}.parquet"
                )
                if not pf.exists():
                    continue
                preds = pd.read_parquet(pf)
                preds["d"] = pd.to_datetime(preds["d"])
                preds["symbol"] = preds["symbol"].astype(str)
            _run_sim(spec, panel, mo, preds)
        print("sim", mo, flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["moments", "lin", "baselines", "sim"])
    ap.add_argument("--months", nargs="*")
    ap.add_argument("--model", default=None)
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--nshards", type=int, default=1)
    a = ap.parse_args()
    ms = (a.months or all_months())[a.shard :: a.nshards]
    if a.stage == "moments":
        stage_moments(ms)
    elif a.stage == "lin":
        stage_lin([m for m in ms if m >= FIRST_OOS])
    elif a.stage == "baselines":
        stage_sim([m for m in ms if m >= FIRST_OOS], None, True)
    else:
        stage_sim([m for m in ms if m >= FIRST_OOS], a.model, False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
