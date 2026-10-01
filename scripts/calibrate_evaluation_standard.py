"""Operating characteristics of the evaluation standard v2 (docs/evaluation-standard.zh.md).

Monte Carlo of a strategy family: N correlated variants (pairwise correlation RHO of daily returns),
true annual Sharpe ratios drawn around the family Sharpe, a recent window of T sessions, and the
best variant selected by observed Sharpe (the selection a researcher actually makes).  Reports the
selection bias, pass rates of the deflated-Sharpe tiers (Bailey and Lopez de Prado 2014, N_eff =
1 + (N - 1)(1 - RHO)), the old fixed bar of 1.19, the expected true Sharpe of a passing variant
under a skeptical base rate, and the chance that a good strategy shows a loss in a short window.

    scripts/run_capped.sh --mem 1.2G -- uv run python scripts/calibrate_evaluation_standard.py
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np
from scipy.stats import norm

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/research/program/evaluation-standard-2026-10-01/calibration.json"

SEED = 20261001
T = 676  # recent window 2024-01-08..2026-09-17
N = 12
RHO = 0.6
SD_BETWEEN = 0.2
VOL = 0.06
SIMS = 4000
FAMILIES = (0.0, 0.3, 0.6, 1.0)
BASE_RATE = {0.0: 0.4, 0.3: 0.3, 0.6: 0.2, 1.0: 0.1}  # skeptical prior over in-house families
DSR_TIERS = (0.70, 0.80, 0.95)
EULER = 0.5772156649


def expected_max_null(var_sr: float, n_eff: float) -> float:
    """Expected maximum Sharpe of n_eff independent zero-skill trials (DSR paper, eq. 1)."""
    return float(
        np.sqrt(var_sr)
        * ((1 - EULER) * norm.ppf(1 - 1 / n_eff) + EULER * norm.ppf(1 - 1 / (n_eff * np.e)))
    )


def simulate(fam: float, rng: np.random.Generator) -> np.ndarray:
    """Rows: (observed Sharpe of the selected variant, its true Sharpe, its DSR)."""
    ty = T / 252
    n_eff = 1 + (N - 1) * (1 - RHO)
    sig = VOL / np.sqrt(252)
    rows = np.empty((SIMS, 3))
    for k in range(SIMS):
        true = fam + SD_BETWEEN * rng.standard_normal(N)
        common = rng.standard_normal(T)
        eps = np.sqrt(RHO) * common + np.sqrt(1 - RHO) * rng.standard_normal((N, T))
        r = (true[:, None] / np.sqrt(252)) * sig + sig * eps
        s = r.mean(1) / r.std(1, ddof=1) * np.sqrt(252)
        i = int(np.argmax(s))
        se = np.sqrt((1 + s[i] ** 2 / 2) / ty)  # Lo (2002), iid
        dsr = norm.cdf((s[i] - expected_max_null(float(s.var(ddof=1)), n_eff)) / se)
        rows[k] = (s[i], true[i], dsr)
    return rows


def short_window_loss_probability(true_sr: float, sessions: int) -> float:
    se = np.sqrt((1 + true_sr**2 / 2) / (sessions / 252))
    return float(norm.cdf(-true_sr / se))


def main() -> int:
    rng = np.random.default_rng(SEED)
    res = {f: simulate(f, rng) for f in FAMILIES}
    out: dict = {
        "setup": {
            "T_sessions": T,
            "variants": N,
            "rho": RHO,
            "n_eff": 1 + (N - 1) * (1 - RHO),
            "sd_between": SD_BETWEEN,
            "vol": VOL,
            "sims": SIMS,
            "seed": SEED,
            "base_rate": {str(k): v for k, v in BASE_RATE.items()},
        },
        "families": {},
        "tiers": {},
        "short_window_loss_probability": {},
    }
    for f, a in res.items():
        out["families"][f"{f:.1f}"] = {
            "selection_bias_mean": float(np.mean(a[:, 0] - a[:, 1])),
            "observed_mean": float(a[:, 0].mean()),
            "pass_obs_ge_1_19": float(np.mean(a[:, 0] >= 1.19)),
            **{f"pass_dsr_ge_{t:.2f}": float(np.mean(a[:, 2] >= t)) for t in DSR_TIERS},
        }
    for t in DSR_TIERS:
        den = sum(BASE_RATE[f] * np.mean(res[f][:, 2] >= t) for f in FAMILIES)
        num = sum(
            BASE_RATE[f] * np.sum(res[f][:, 1] * (res[f][:, 2] >= t)) / SIMS for f in FAMILIES
        )
        zero = BASE_RATE[0.0] * np.mean(res[0.0][:, 2] >= t)
        out["tiers"][f"dsr_ge_{t:.2f}"] = {
            "overall_pass": float(den),
            "expected_true_sr_given_pass": float(num / den) if den > 0 else None,
            "share_of_passes_from_zero_skill": float(zero / den) if den > 0 else None,
        }
    for s in (0.5, 0.8, 1.0, 1.5):
        out["short_window_loss_probability"][f"sr_{s}"] = {
            str(n): short_window_loss_probability(s, n) for n in (55, 63, 126, 252)
        }
    out["generated_at_utc"] = subprocess.check_output(
        ["date", "-u", "+%Y-%m-%dT%H:%M:%SZ"], text=True
    ).strip()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
