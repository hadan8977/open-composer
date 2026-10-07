"""Forward stop thresholds calibrated for daily (repeated) looks.

Lead round 2026-10-07 19:07 UTC (P4). Follow-up of DXRG discipline 15
(reports/research/program/dxrg-disciplines-2026-10-10.md): a monitor read every
day must be calibrated on the probability of crossing at ANY session of the
monitoring period, not on a single-look quantile.

Monitor 1, forward z: z_t = (sum_{s<=t} r_s - t*mu0) / (sigma0*sqrt(t)), mu0 and
sigma0 from the candidate's DSR-discounted backtest. Under H0 ("the strategy is
as good as its discounted backtest") the crossing law of min_t z_t depends only
on the shape of the innovations (tails, volatility clustering), not on mu0 or
sigma0, so the thresholds are generic. Innovations: iid normal, iid Student t4,
and stationary block bootstraps (mean block 21, as T-58) of the standardized
demeaned excess returns of the ETF sleeves.

Monitor 2, account drawdown of the S3 pilot (k = 0.5 of equity in S3 with the
T-32 10% theme cap, the rest cash): path maximum drawdown over 126 and 252
sessions under T-58 scenario A (DSR-haircut mean). Reproduces T-58 q95/q99 as a
check and adds the 2.5% / 0.5% lines for the two-monitor union rule.

Promotion read: max_t of the same z under SR = 0, quantile 0.90, and its
probabilistic-Sharpe equivalent Phi(c).

Run: scripts/run_capped.sh --mem 600M -- .venv/bin/python <this file>
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
PANEL = ROOT / "reports/research/iterations/t20261005_p4_alloc_v2/cache/panel.parquet"
T58 = ROOT / "reports/research/iterations/t20261005_p4_alloc_v2/results.json"
SEED = 20261007
N_PATHS = 20000
MEAN_BLOCK = 21
T0S = [10, 21]
HORIZONS = [63, 126, 252]
CHECKPOINT = 21
LOWER_Q = [0.05, 0.025, 0.01, 0.005]
K_PILOT = 0.5


def phi(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def stationary_idx(n: int, horizon: int, rng: np.random.Generator) -> np.ndarray:
    new = rng.random((N_PATHS, horizon)) < 1.0 / MEAN_BLOCK
    starts = rng.integers(0, n, size=(N_PATHS, horizon))
    idx = np.empty((N_PATHS, horizon), dtype=np.int64)
    idx[:, 0] = starts[:, 0]
    for t in range(1, horizon):
        idx[:, t] = np.where(new[:, t], starts[:, t], (idx[:, t - 1] + 1) % n)
    return idx


def innovations(kind: str, rng: np.random.Generator, x: np.ndarray | None) -> np.ndarray:
    h = max(HORIZONS)
    if kind == "iid_normal":
        return rng.standard_normal((N_PATHS, h))
    if kind == "iid_t4":
        return rng.standard_t(4, size=(N_PATHS, h)) / math.sqrt(2.0)
    assert x is not None
    e = (x - x.mean()) / x.std(ddof=1)
    return e[stationary_idx(len(e), h, rng)]


def z_paths(e: np.ndarray) -> np.ndarray:
    t = np.arange(1, e.shape[1] + 1, dtype=float)
    return np.cumsum(e, axis=1) / np.sqrt(t)


def summarize_z(z: np.ndarray) -> dict:
    out: dict = {}
    for t0 in T0S:
        for h in HORIZONS:
            seg = z[:, t0 - 1 : h]
            mn = seg.min(axis=1)
            mx = seg.max(axis=1)
            cps = [c for c in range(CHECKPOINT, h + 1, CHECKPOINT)]
            mn_cp = z[:, [c - 1 for c in cps]].min(axis=1)
            mx_cp = z[:, [c - 1 for c in cps]].max(axis=1)
            key = f"t0_{t0}_T_{h}"
            out[key] = {
                "daily_min_z_quantiles": {str(q): float(np.quantile(mn, q)) for q in LOWER_Q},
                "checkpoint_min_z_quantiles": {
                    str(q): float(np.quantile(mn_cp, q)) for q in LOWER_Q
                },
                "p_ever_z_below_-2_daily": float(np.mean(mn < -2.0)),
                "promotion_daily_max_z_q90": float(np.quantile(mx, 0.90)),
                "promotion_daily_psr_equiv": phi(float(np.quantile(mx, 0.90))),
                "promotion_checkpoint_max_z_q90": float(np.quantile(mx_cp, 0.90)),
                "promotion_checkpoint_psr_equiv": phi(float(np.quantile(mx_cp, 0.90))),
                "p_ever_psr_ge_0.9_daily_under_sr0": float(np.mean(mx >= 1.2815515655446004)),
                "checkpoints": cps,
            }
    return out


def dd_lines(ex: np.ndarray, mu: float, rf_bar: float, rng: np.random.Generator) -> dict:
    base = ex - ex.mean() + mu + rf_bar
    out = {}
    for h in [126, 252]:
        r = base[stationary_idx(len(base), h, rng)]
        nav = np.cumprod(1.0 + r, axis=1)
        peak = np.maximum(np.maximum.accumulate(nav, axis=1), 1.0)
        dd = (nav / peak - 1.0).min(axis=1)
        out[str(h)] = {
            f"q{int(round((1 - q) * 1000)) / 10:g}": float(np.quantile(dd, q))
            for q in [0.05, 0.025, 0.01, 0.005]
        }
    return out


def main() -> None:
    t_start = time.time()
    rng = np.random.default_rng(SEED)
    panel = pd.read_parquet(PANEL)
    cash = panel["CASH"]
    sleeves = {
        "S3_pilot_cap10": "L1__S3",
        "S3_orig": "orig__S3",
        "C2": "orig__C2",
        "S2": "orig__S2",
    }
    excess = {}
    for name, col in sleeves.items():
        s = (panel[col] - cash).dropna()
        excess[name] = s
    res: dict = {
        "generated_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "inputs": {
            "panel": str(PANEL.relative_to(ROOT)),
            "panel_sha256": hashlib.sha256(PANEL.read_bytes()).hexdigest(),
            "columns": sleeves,
            "rows": {k: int(len(v)) for k, v in excess.items()},
            "first": str(panel.index[0].date()),
            "last": str(panel.index[-1].date()),
        },
        "params": {
            "seed": SEED,
            "n_paths": N_PATHS,
            "mean_block": MEAN_BLOCK,
            "t0s": T0S,
            "horizons": HORIZONS,
            "checkpoint_every": CHECKPOINT,
        },
        "z_monitor": {},
        "sleeve_shape": {},
    }
    for kind in ["iid_normal", "iid_t4"] + [f"boot_{k}" for k in excess]:
        x = excess[kind[5:]].to_numpy() if kind.startswith("boot_") else None
        e = innovations(kind, rng, x)
        res["z_monitor"][kind] = summarize_z(z_paths(e))
        del e
    for k, v in excess.items():
        a = v.to_numpy()
        m = a - a.mean()
        res["sleeve_shape"][k] = {
            "ann_vol": float(a.std(ddof=1) * math.sqrt(252)),
            "excess_kurtosis": float((m**4).mean() / (m**2).mean() ** 2 - 3.0),
            "abs_ret_acf1": float(np.corrcoef(np.abs(m[1:]), np.abs(m[:-1]))[0, 1]),
        }
    t58 = json.loads(T58.read_text())
    p = t58["deployables"]["50k"]["cash"]["p0_s3"]
    ex_acct = K_PILOT * excess["S3_pilot_cap10"].to_numpy()
    rf_recent = cash.loc["2024-01-08":].dropna()
    rf_bar = float(rf_recent.mean())
    res["dd_monitor_s3_pilot"] = {
        "k": K_PILOT,
        "t58_reference_A": p["dd_sim"]["A"],
        "t58_mu_daily": p["mu_daily"],
        "this_run": {
            scn: dd_lines(ex_acct, float(mu), rf_bar, rng) for scn, mu in p["mu_daily"].items()
        },
        "rf_bar_daily": rf_bar,
    }
    res["runtime_s"] = round(time.time() - t_start, 1)
    (HERE / "results.json").write_text(json.dumps(res, indent=1))
    print(json.dumps({"runtime_s": res["runtime_s"]}))


if __name__ == "__main__":
    main()
