"""T-20261006-15 group A reproduction: SPY noise band vs Zarattini-Aziz-Barbon 2024 (Tables 2-3).

Shows how the check interval and the stop semantics move the Sharpe, which explains the local 0.30
(every-minute persistent rule) against the paper 0.61 / 1.24 / 1.33. Not a counted trial.
Run: scripts/heavy_run.sh --mem 0.8G -- uv run python scripts/t15_repro_a.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import t15_engine as E  # noqa: E402

OUT = ROOT / "reports/research/iterations/t20261006_15_intraday_rules/repro_a_spy.json"
PAPER = {
    "opp_band_1x": {"irr": 0.062, "vol": 0.109, "sharpe": 0.61},
    "curr_band_vwap_1x": {"irr": 0.097, "vol": 0.077, "sharpe": 1.24},
    "curr_band_vwap_dyn": {"irr": 0.196, "vol": 0.143, "sharpe": 1.33},
    "sample": "2007-05..2024-04, SPY, $0.0035 commission + $0.001 slippage per share",
}


def stats(r: pd.Series) -> dict:
    r = r.dropna()
    eq = (1 + r).cumprod()
    yrs = len(r) / 252
    return {
        "sessions": int(len(r)),
        "cagr": float(eq.iloc[-1] ** (1 / yrs) - 1),
        "mean_ann": float(r.mean() * 252),
        "vol": float(r.std(ddof=1) * np.sqrt(252)),
        "sharpe": float(r.mean() / r.std(ddof=1) * np.sqrt(252)),
        "max_dd": float((eq / eq.cummax() - 1).min()),
    }


def main() -> int:
    p = E.Panel("SPY")
    sig = E.noise_sigma(p, 14)
    lev = E.vol_target_lev(p)
    dates = p.dates
    windows = {
        "paper_overlap_2016_2024-04": (dates >= "2016-01-04") & (dates <= "2024-04-30"),
        "diag_2016_2023": dates <= "2023-12-29",
        "recent_2024-01-08_end": dates >= "2024-01-08",
    }
    rows = []
    for k in (1, 5, 15, 30):
        paths = E.a_position_paths(p, sig, k, [1.0], ["opp", "both", "band", "vwap"])
        for (_m, st), P in paths.items():
            g, c, n, _ = E.a_daily(p, k, P)
            for vt in (0, 1):
                L = lev if vt else np.ones_like(lev)
                net = pd.Series(L * (g - c), index=dates)
                for wn, mask in windows.items():
                    s = stats(net[mask])
                    s.update(
                        {
                            "interval": k,
                            "stop": st,
                            "vt": vt,
                            "window": wn,
                            "entries_per_day": float(np.nanmean(n[mask])),
                            "gross_bp_day": float(
                                np.nanmean(L * g * 1e4)[()]
                                if False
                                else np.nanmean((L * g)[mask]) * 1e4
                            ),
                            "cost_bp_day": float(np.nanmean((L * c)[mask]) * 1e4),
                        }
                    )
                    rows.append(s)
        print("k", k, "done", flush=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"paper": PAPER, "rows": rows}, indent=1) + "\n")
    df = pd.DataFrame(rows)
    sub = df[df.window == "paper_overlap_2016_2024-04"]
    print(
        sub[
            [
                "interval",
                "stop",
                "vt",
                "sharpe",
                "cagr",
                "vol",
                "entries_per_day",
                "gross_bp_day",
                "cost_bp_day",
            ]
        ]
        .round(3)
        .to_string(index=False)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
