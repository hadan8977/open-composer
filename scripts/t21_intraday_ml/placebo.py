"""T-20261006-21: placebos of evaluation-standard 5b (100 seeds) for one registered variant.

    scripts/heavy_run.sh --mem 0.8G -- uv run python scripts/t21_intraday_ml/placebo.py LIN_N300_H60_K2 [--seeds 100]

gross placebo: shuffle the predicted scores inside every (day, t) cross-section;
net placebo: a day-fixed random name ranking (hash of seed, symbol, day) receives the real sorted scores.
Costs and portfolio rule are those of the variant.  Output: data/research/t21/placebo/<variant>.json
(per-seed recent-window Sharpe of gross and net), resumable per seed block.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import portfolio as P  # noqa: E402
import run_pipeline as RP  # noqa: E402

OUT = RP.OUT / "placebo"
RECENT_START, DATA_END = "2024-01-08", "2026-10-05"


def parse(vid: str) -> dict:
    fam, n, h, k = vid.split("_")
    return {"family": fam, "N": int(n[1:]), "h": int(h[1:]), "k": int(k[1:])}


def day_hash_rank(symbols: pd.Series, days: pd.Series, seed: int) -> np.ndarray:
    key = (symbols.astype(str) + "|" + days.dt.strftime("%Y%m%d") + f"|{seed}").to_numpy()
    return np.array([int(hashlib.md5(k.encode()).hexdigest()[:8], 16) for k in key], dtype=np.int64)


def shuffled_scores(df: pd.DataFrame, rng: np.random.Generator) -> np.ndarray:
    out = df["pred"].to_numpy().copy()
    for _, idx in df.groupby(["d", "t"]).indices.items():
        out[idx] = rng.permutation(out[idx])
    return out


def ranked_scores(df: pd.DataFrame, seed: int) -> np.ndarray:
    hk = day_hash_rank(df["symbol"], df["d"], seed)
    tmp = pd.DataFrame(
        {"g": df.groupby(["d", "t"]).ngroup().to_numpy(), "hk": hk, "pred": df["pred"].to_numpy()}
    )
    tmp["pos"] = np.arange(len(tmp))
    tmp["r"] = (
        tmp.groupby("g")["hk"].rank(method="first", ascending=False).astype(int) - 1
    )  # random rank
    srt = tmp.sort_values(["g", "pred"], ascending=[True, False])
    srt["r_sorted"] = srt.groupby("g").cumcount()
    real = srt.set_index(["g", "r_sorted"])["pred"]
    vals = real.reindex(pd.MultiIndex.from_arrays([tmp["g"], tmp["r"]])).to_numpy()
    return vals


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("variant")
    ap.add_argument("--seeds", type=int, default=100)
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--nshards", type=int, default=1)
    a = ap.parse_args()
    spec = parse(a.variant)
    OUT.mkdir(parents=True, exist_ok=True)
    f = OUT / (f"{a.variant}.json" if a.nshards == 1 else f"{a.variant}.s{a.shard}.json")
    res = json.loads(f.read_text()) if f.exists() else {"gross": {}, "net": {}}
    todo = [s for s in range(a.seeds)][a.shard :: a.nshards]
    todo = [s for s in todo if str(s) not in res["net"]]
    if not todo:
        return 0
    n, h, k = spec["N"], spec["h"], spec["k"]
    cols = RP.SIM_COLS + [f"ret{h}", f"spy{h}"]
    months = [m for m in RP.all_months() if m >= RP.FIRST_OOS]
    gross: dict[int, list] = {s: [] for s in todo}
    net: dict[int, list] = {s: [] for s in todo}
    for mo in months:
        panel = RP.read_panel(mo, cols)
        panel = panel[panel["pool_rank"] <= n]
        pf = RP.OUT / f"preds/{spec['family']}" / f"N{n}_H{h}" / f"{mo}.parquet"
        preds = pd.read_parquet(pf)
        preds["d"] = pd.to_datetime(preds["d"])
        preds["symbol"] = preds["symbol"].astype(str)
        df = panel.merge(preds, on=["symbol", "d", "t"], how="inner")
        df["ret"], df["spy"] = df[f"ret{h}"], df[f"spy{h}"]
        for s in todo:
            rng = np.random.default_rng(s * 7919 + 13)
            g = df.copy()
            g["pred"] = shuffled_scores(df, rng)
            gross[s].append(P.with_net(P.simulate(g, h, k=k))[["d", "gross"]])
            r = df.copy()
            r["pred"] = ranked_scores(df, s)
            net[s].append(P.with_net(P.simulate(r, h, k=k))[["d", "net"]])
        print("placebo", mo, flush=True)
    for s in todo:
        gs = pd.concat(gross[s]).set_index("d")["gross"]
        ns = pd.concat(net[s]).set_index("d")["net"]
        days = pd.DatetimeIndex(json.loads((RP.OUT / "days.json").read_text()))
        days = days[(days >= RECENT_START) & (days <= DATA_END)]
        win = lambda x: x.reindex(days).fillna(0.0)  # noqa: E731
        res["gross"][str(s)] = P.annual_sharpe(win(gs))
        res["net"][str(s)] = P.annual_sharpe(win(ns))
    f.write_text(json.dumps(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
