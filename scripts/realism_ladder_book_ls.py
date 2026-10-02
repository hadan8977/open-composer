"""Realism ladder for the total-return M0/M1 long-short (T-20261002-25, preregistered).

Stage ``r0``: the identity rung -- the regime-analysis M0 long-short rebuilt with the functions of
``scripts/analyze_equity_book_regimes.py`` and compared with its ``results.json`` to 1e-9.
Later stages (R1a, R1 .. R6) are added below the preregistration commit.

    scripts/run_capped.sh --mem 1.8G -- uv run python scripts/realism_ladder_book_ls.py --stage r0
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import analyze_equity_book_regimes as reg  # noqa: E402

OUT = ROOT / "reports/research/program/realism-ladder-2026-10-02"
REG_RESULTS = ROOT / "reports/research/program/regimes-2026-10-01/results.json"
R0_WINDOWS = ("stress", "anchor", "owner_A_2024_01_2026_06", "owner_B_2026_07_now")
R0_TOL = 1e-9


def r0_series() -> tuple[pd.Series, pd.Series]:
    """Daily M0 long-short return and turnover exactly as ``run_signals`` builds them (the signal
    list is empty: only the ``m0_composite`` column is evaluated)."""
    open_, _ = reg.load_etf()
    sessions = open_["SPY"].dropna().index
    spy_open = open_["SPY"]
    f_parts, to_parts = [], []
    cols = ["trade_date", "symbol", "ind_code", "m0_composite", "m0_n_themes"]
    for year in range(2017, 2027):
        sig = pd.read_parquet(reg.DATA / f"signals/{year}.parquet", columns=cols)
        sig = sig[(sig["trade_date"] >= reg.SIGNAL_START) & (sig["trade_date"] <= reg.SIGNAL_END)]
        if sig.empty:
            continue
        ret = reg.year_returns(year, sessions, spy_open)
        df = sig.merge(ret, on=["trade_date", "symbol"], how="inner")
        df = df[np.isfinite(df["e"])]
        del sig, ret
        f, to = reg.ls_returns(df, [], {})
        f_parts.append(f)
        to_parts.append(to)
        print(year, len(df), "rows", flush=True)
        del df
    f = pd.concat(f_parts).sort_index()["m0_composite"]
    to = pd.concat(to_parts).sort_index()["m0_composite"]
    return f, to


def r0_identity() -> dict:
    f, to = r0_series()
    stored = json.loads(REG_RESULTS.read_text())["windows"]
    out: dict = {"tolerance": R0_TOL, "windows": {}, "max_abs_diff": 0.0, "pass": True}
    for k in R0_WINDOWS:
        a, b = reg.WINDOWS[k]
        mine = reg.stats(f.loc[a:b], to)
        ref = stored[k]["m0_composite"]
        diffs = {}
        for key, v in ref.items():
            m = mine.get(key)
            diffs[key] = None if m is None else abs(float(m) - float(v))
        worst = max((d for d in diffs.values() if d is not None), default=float("nan"))
        missing = [key for key, d in diffs.items() if d is None]
        ok = bool(math.isfinite(worst) and worst <= R0_TOL and not missing)
        out["windows"][k] = {
            "mine": mine,
            "stored": ref,
            "abs_diff": diffs,
            "worst": worst,
            "missing_keys": missing,
            "pass": ok,
        }
        out["max_abs_diff"] = max(out["max_abs_diff"], worst if math.isfinite(worst) else 1e99)
        out["pass"] = out["pass"] and ok
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["r0"], required=True)
    a = ap.parse_args()
    if a.stage == "r0":
        res = r0_identity()
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "r0_identity.json").write_text(json.dumps(res, indent=1, default=float))
        print(json.dumps({k: res[k] for k in ("max_abs_diff", "pass")}))


if __name__ == "__main__":
    main()
