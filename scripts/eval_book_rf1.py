"""RF1 mechanical conditions for the equity book (contract ``t20261001_book_rf1``, sections 4-5).

RF_M0_{A,B,C} and RF_M1_{A,B,C} are T-20261001-08's ``M0_*`` / ``M1_*`` close paths (contract
section 2: not re-run).  For each variant and offset the statistic is min(plain, cash-aligned), then
the median over the 5 offsets (the stricter reading allowed by contract section 8.2).

RF_M0V_* and RF_M0X_* were not run.  The script records, from data, the facts that bound them: VIX
days above 20.60 in window B and the B-window result of the M0 base they modify.  No verdict is
written here; the lead's decision record is ``decision-record.md``.

    scripts/run_capped.sh --mem 1.2G -- uv run python scripts/eval_book_rf1.py
"""

from __future__ import annotations

import csv
import importlib.util
import json
import statistics
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from open_composer.research.equity_book.evaluate import (  # noqa: E402
    deflated_sharpe,
    load_rf_spy,
    window_metrics,
)

_spec = importlib.util.spec_from_file_location(
    "eval_book_v1_stage2", ROOT / "scripts/eval_book_v1_stage2.py"
)
assert _spec is not None and _spec.loader is not None
ev = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ev)

RF1_DIR = ROOT / "reports/research/iterations/t20261001_book_rf1"
V1_DIR = ROOT / "reports/research/iterations/t20261001_book_v1"
CACHE = V1_DIR / "cache/stage2a"
PHASES = ROOT / "data/research/equity_book/regimes/phases.json"
VIX = ROOT / "data/research/vix/VIXCLS.csv"

WINDOWS = {
    "A": ("2024-01-08", "2026-06-30"),
    "B": ("2026-07-01", "2026-09-17"),
    "stress": ("2017-10-02", "2023-08-31"),
    "full": ("2017-10-02", "2026-09-17"),
}
VARIANTS = ("M0_A", "M0_B", "M0_C", "M1_A", "M1_B", "M1_C")
OFFSETS = range(5)
DSR_TRIALS = 83
VIX_THRESHOLD = 20.60
RESEARCH = {"r1": 1.19, "r3": 0.87, "r4": 0.95}
WATCH = {"r1": 0.87, "r3": 0.60, "r4": 0.90}
BETA_BOUND = 0.15
FAILURE_MAX = 0.02
R8_MAX_DD = 0.20
R8_MIN_SHARPE = -0.5


def min_stat(plain: dict[str, float], aligned: dict[str, float], key: str) -> float:
    """Per-offset statistic: the lower of the plain and cash-aligned values."""
    a, b = plain.get(key, float("nan")), aligned.get(key, float("nan"))
    return float(np.nanmin([a, b])) if np.isfinite(a) or np.isfinite(b) else float("nan")


def median(xs: Sequence[float]) -> float:
    vals = [x for x in xs if np.isfinite(x)]
    return float(statistics.median(vals)) if vals else float("nan")


def drop_sessions(series: pd.Series, start: str, end: str) -> pd.Series:
    """``series`` with the sessions in [start, end] set to NaN (window_metrics drops NaNs)."""
    out = series.copy()
    out[(out.index >= start) & (out.index <= end)] = np.nan
    return out


def load_path(variant: str, offset: int) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    hits = sorted(CACHE.glob(f"*/{variant}_o{offset}_close"))
    if len(hits) != 1:
        raise FileNotFoundError(f"{variant}_o{offset}_close: {len(hits)} cache dirs")
    d = hits[0]
    daily = pd.read_parquet(d / "daily.parquet").set_index("trade_date").sort_index()
    rep = pd.read_parquet(d / "replays.parquet").set_index("trade_date").sort_index()
    daily.index = pd.to_datetime(daily.index)
    rep.index = pd.to_datetime(rep.index)
    return daily, rep, json.loads((d / "meta.json").read_text())


def path_block(
    variant: str,
    offset: int,
    rf: pd.Series,
    spy: pd.Series,
    bil: pd.Series,
    shy: pd.Series,
    phases: list[dict[str, Any]],
) -> dict[str, Any]:
    daily, rep, meta = load_path(variant, offset)
    net = daily["net"]
    net_ca = ev.cash_aligned(net, bil, shy)
    c2 = rep["net_cost2x"]
    c2_ca = ev.cash_aligned(c2, bil, shy)
    out: dict[str, Any] = {"path_id": f"{variant}_o{offset}_close", "windows": {}}
    for w, win in WINDOWS.items():
        p = window_metrics(net, rf, spy, win)
        a = window_metrics(net_ca, rf, spy, win)
        g = window_metrics(daily["gross"], rf, spy, win)
        out["windows"][w] = {
            "plain": p,
            "cash_aligned": a,
            "gross_sharpe": g.get("sharpe", float("nan")),
            "sharpe": min_stat(p, a, "sharpe"),
            "ann_excess": min_stat(p, a, "ann_excess_return"),
        }
    a_win = WINDOWS["A"]
    c2p = window_metrics(c2, rf, spy, a_win)
    c2a = window_metrics(c2_ca, rf, spy, a_win)
    out["cost2x_A_ann_excess"] = min_stat(c2p, c2a, "ann_excess_return")
    out["beta_A_ols"] = out["windows"]["A"]["plain"].get("beta_spy", float("nan"))
    out["beta_A_dimson"] = ev.dimson_beta(net, spy, a_win)
    lopo = {}
    for ph in phases:
        p = window_metrics(drop_sessions(net, ph["start"], ph["end"]), rf, spy, a_win)
        a = window_metrics(drop_sessions(net_ca, ph["start"], ph["end"]), rf, spy, a_win)
        lopo[ph["id"]] = min_stat(p, a, "sharpe")
    out["lopo_A_sharpe"] = lopo
    out["failure"] = ev.failure_stats(meta)
    out["stress_max_dd"] = out["windows"]["stress"]["plain"].get("max_dd", float("nan"))
    out["dsr_A"] = deflated_sharpe(net, rf, a_win, trial_count=DSR_TRIALS)
    out["dsr_full"] = deflated_sharpe(net, rf, WINDOWS["full"], trial_count=DSR_TRIALS)
    return out


def variant_status(med: dict[str, Any]) -> dict[str, Any]:
    """Mechanical conditions R1-R8 (R4 only where R1 reaches the watch tier)."""
    r1, r2, r3 = med["r1_A_sharpe"], med["r2_B_ann_excess"], med["r3_lopo_min"]
    r5 = abs(med["beta_A_ols"]) <= BETA_BOUND and abs(med["beta_A_dimson"]) <= BETA_BOUND
    r6 = med["failure_rate"] < FAILURE_MAX
    r7 = med["cost2x_A_ann_excess"] > 0
    r8 = med["stress_max_dd"] < -R8_MAX_DD or med["stress_sharpe"] < R8_MIN_SHARPE
    placebo_required = bool(r1 >= WATCH["r1"])
    common = r2 > 0 and r5 and r6 and r7
    research_pre = r1 >= RESEARCH["r1"] and r3 >= RESEARCH["r3"] and common
    watch_pre = r1 >= WATCH["r1"] and r3 >= WATCH["r3"] and common
    if not watch_pre:
        status = "none"
    else:
        status = "pending_placebo"
    return {
        "R1_A_sharpe_ge_1_19": bool(r1 >= RESEARCH["r1"]),
        "R1_A_sharpe_ge_0_87": bool(r1 >= WATCH["r1"]),
        "R2_B_ann_excess_gt_0": bool(r2 > 0),
        "R3_lopo_ge_0_87": bool(r3 >= RESEARCH["r3"]),
        "R3_lopo_ge_0_60": bool(r3 >= WATCH["r3"]),
        "R4_placebo_required": placebo_required,
        "R5_beta_ok": bool(r5),
        "R6_failure_ok": bool(r6),
        "R7_cost2x_ok": bool(r7),
        "R8_downgrade": bool(r8),
        "research_pre_placebo": bool(research_pre),
        "watch_pre_placebo": bool(watch_pre),
        "status": status,
    }


def vix_facts(start: str, end: str) -> dict[str, Any]:
    rows = list(csv.reader(VIX.open()))
    vals = [(d, float(x)) for d, x in rows[1:] if x not in ("", ".") and start <= d <= end]
    above = [(d, x) for d, x in vals if x > VIX_THRESHOLD]
    return {
        "window": [start, end],
        "n_days": len(vals),
        "max": max(x for _, x in vals),
        "days_above_threshold": [{"date": d, "vix": x} for d, x in above],
    }


def blended_cum(variant: str, start: str, end: str) -> float:
    nets = [load_path(variant, k)[0]["net"] for k in OFFSETS]
    blend = pd.concat(nets, axis=1).mean(axis=1)
    sub = blend[(blend.index >= start) & (blend.index <= end)].dropna()
    return float((1.0 + sub).prod() - 1.0)


def main() -> int:
    rf, spy = load_rf_spy()
    bil, shy = ev.load_bil_shy()
    phase_doc = json.loads(PHASES.read_text())
    phases_a = [p for p in phase_doc["phases_recent"] if p["end"] <= WINDOWS["A"][1]]
    assert [p["id"] for p in phases_a] == [f"P{i:02d}" for i in range(1, 11)], phases_a
    res: dict[str, Any] = {
        "iter_id": "t20261001_book_rf1",
        "source_paths": "T-20261001-08 close paths (cache/stage2a of t20261001_book_v1)",
        "windows": WINDOWS,
        "rule": "per offset min(plain, cash-aligned), then median over 5 offsets",
        "dsr_trials": DSR_TRIALS,
        "paths": {},
        "variants": {},
    }
    for v in VARIANTS:
        blocks = [path_block(v, k, rf, spy, bil, shy, phases_a) for k in OFFSETS]
        for b in blocks:
            res["paths"][b["path_id"]] = b
        lopo_med = {
            ph["id"]: median([b["lopo_A_sharpe"][ph["id"]] for b in blocks]) for ph in phases_a
        }
        med = {
            "r1_A_sharpe": median([b["windows"]["A"]["sharpe"] for b in blocks]),
            "A_gross_sharpe": median([b["windows"]["A"]["gross_sharpe"] for b in blocks]),
            "r2_B_ann_excess": median([b["windows"]["B"]["ann_excess"] for b in blocks]),
            "B_sharpe": median([b["windows"]["B"]["sharpe"] for b in blocks]),
            "r3_lopo_by_phase": lopo_med,
            "r3_lopo_min": min(lopo_med.values()),
            "r3_lopo_argmin": min(lopo_med, key=lopo_med.get),
            "beta_A_ols": median([b["beta_A_ols"] for b in blocks]),
            "beta_A_dimson": median([b["beta_A_dimson"] for b in blocks]),
            "failure_rate": median([b["failure"]["failure_rate"] for b in blocks]),
            "cost2x_A_ann_excess": median([b["cost2x_A_ann_excess"] for b in blocks]),
            "stress_sharpe": median([b["windows"]["stress"]["sharpe"] for b in blocks]),
            "stress_max_dd": median([b["stress_max_dd"] for b in blocks]),
            "dsr_A": median([b["dsr_A"] if b["dsr_A"] is not None else np.nan for b in blocks]),
            "dsr_full": median(
                [b["dsr_full"] if b["dsr_full"] is not None else np.nan for b in blocks]
            ),
        }
        res["variants"]["RF_" + v] = {"median": med, "checks": variant_status(med)}
    b_win = WINDOWS["B"]
    res["not_run"] = {
        "variants": [f"RF_{m}_{u}" for m in ("M0V", "M0X") for u in "ABC"],
        "vix_window_B": vix_facts(*b_win),
        "base_B_blended_cum_return": {f"M0_{u}": blended_cum(f"M0_{u}", *b_win) for u in "ABC"},
        "base_A_r1": {
            f"M0_{u}": res["variants"][f"RF_M0_{u}"]["median"]["r1_A_sharpe"] for u in "ABC"
        },
    }
    res["generated_at_utc"] = subprocess.check_output(
        ["date", "-u", "+%Y-%m-%dT%H:%M:%SZ"], text=True
    ).strip()
    out = RF1_DIR / "results.json"
    out.write_text(json.dumps(ev.clean(res), indent=1, ensure_ascii=False) + "\n")
    for k, v in res["variants"].items():
        m, c = v["median"], v["checks"]
        print(
            f"{k}: R1 {m['r1_A_sharpe']:.3f} R2 {m['r2_B_ann_excess']:+.4f} "
            f"R3 {m['r3_lopo_min']:.3f}({m['r3_lopo_argmin']}) "
            f"beta {m['beta_A_ols']:+.3f}/{m['beta_A_dimson']:+.3f} "
            f"fail {m['failure_rate']:.4f} c2x {m['cost2x_A_ann_excess']:+.4f} "
            f"stress {m['stress_sharpe']:.2f}/{m['stress_max_dd']:.3f} -> {c['status']}"
        )
    print(json.dumps(ev.clean(res["not_run"]), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
