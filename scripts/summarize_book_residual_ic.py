"""Residual-IC summary of the equity book v1 signal library (19:07 lead round, 2026-10-01).

Reads ``data/research/equity_book/alpha/book_v1/formation_ic.parquet`` (monthly Spearman rank IC of
each theme, M0 and M1 against the factor-neutral 21-session forward open-to-open return; see
``scripts/build_book_v1_alpha.py``) and evaluates the program's preregistered stop condition
"M0 residual IC in the anchor window has t < 2" (``docs/research-program.zh.md``, main line 1).

A formation date belongs to a window when its whole target (sessions p + 1 .. p + 22) lies inside
it: stress 2017-10-02..2023-08-31 -> formation dates up to 2023-07-31; anchor 2024-01-08..2026-09-17
-> formation dates 2024-01-31..2026-07-31.  Targets of consecutive formation dates do not overlap,
so the plain t statistic is the main one; a Newey-West (lag 2) t is reported as a check.

    uv run python scripts/summarize_book_residual_ic.py
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data/research/equity_book/alpha/book_v1/formation_ic.parquet"
OUT = ROOT / "reports/research/iterations/t20261001_book_v1/residual-ic-summary.json"
WINDOWS = {
    "stress": ("2017-10-02", "2023-07-31"),
    "anchor": ("2024-01-08", "2026-08-14"),
    "anchor_2026": ("2026-01-01", "2026-08-14"),
}


def nw_t(x: np.ndarray, lags: int = 2) -> float:
    x = x[np.isfinite(x)]
    n = len(x)
    e = x - x.mean()
    s = float(e @ e) / n
    for k in range(1, lags + 1):
        s += 2 * (1 - k / (lags + 1)) * float(e[k:] @ e[:-k]) / n
    return float(x.mean() / np.sqrt(s / n))


def stats(x: np.ndarray) -> dict:
    n = len(x)
    sd = float(x.std(ddof=1))
    return {
        "n": n,
        "mean_ic": round(float(x.mean()), 5),
        "sd_ic": round(sd, 5),
        "t": round(float(x.mean() / sd * np.sqrt(n)), 3),
        "t_nw2": round(nw_t(x), 3),
        "share_positive": round(float((x > 0).mean()), 3),
    }


def main() -> None:
    f = pd.read_parquet(SRC)
    out: dict = {
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "source": str(SRC.relative_to(ROOT)),
        "windows_formation_dates": WINDOWS,
        "series": {},
    }
    for uni in sorted(f["universe"].unique()):
        for s in f["series"].unique():
            sub = f[(f["universe"] == uni) & (f["series"] == s)]
            row = {}
            for w, (a, b) in WINDOWS.items():
                x = sub[(sub["formation_date"] >= a) & (sub["formation_date"] <= b)]["ic"]
                row[w] = stats(x.to_numpy(dtype=float))
            out["series"][f"{uni}/{s}"] = row
    m0 = {u: out["series"][f"{u}/M0"]["anchor"]["t"] for u in ("u3000", "p1000")}
    out["stop_condition_m0_anchor_t_lt_2"] = {"t": m0, "met": all(t < 2 for t in m0.values())}
    a, b = WINDOWS["anchor"]
    p = f[(f["universe"] == "u3000") & (f["formation_date"] >= a) & (f["formation_date"] <= b)]
    p = p.pivot(index="formation_date", columns="series", values="ic").drop(columns=["M0", "M1"])
    out["anchor_u3000_theme_ic_correlation"] = p.corr().round(3).to_dict()
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps(out["stop_condition_m0_anchor_t_lt_2"]))


if __name__ == "__main__":
    main()
