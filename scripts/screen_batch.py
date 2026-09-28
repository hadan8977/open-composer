"""Batch screening runner. See `scripts/screen_lane.py`'s module docstring for
the usage protocol (dossier + manifest first, then the batch module, then run).

    scripts/run_capped.sh --mem 1.8G -- \\
        uv run python scripts/screen_batch.py --batch <name> --iteration <iter_id>
    scripts/run_capped.sh --mem 1.8G -- \\
        uv run python scripts/screen_batch.py --batch smoke_20260928 --smoke
    scripts/run_capped.sh --mem 1.8G -- \\
        uv run python scripts/screen_batch.py --self-check
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_h20260918_05_recent_menu as base  # noqa: E402
import run_h20260922_05_salvage as salvage  # noqa: E402
import run_h20260927_01_sleeve_combination as combo  # noqa: E402
import run_h20260928_01_s3_rebalance_tranching as tranche  # noqa: E402
import screen_lane as lane  # noqa: E402

BATCH_DIR = ROOT / "scripts" / "screen_batches"
SCREENS_DIR = ROOT / "reports" / "research" / "screens"
ITERATIONS_DIR = ROOT / "reports" / "research" / "iterations"

ENGINE_SOURCES = [
    "scripts/run_h20260918_05_recent_menu.py",
    "scripts/run_h20260922_05_salvage.py",
    "scripts/run_h20260927_01_sleeve_combination.py",
    "scripts/run_h20260928_01_s3_rebalance_tranching.py",
    "scripts/screen_lane.py",
]

SELF_CHECK_TOLERANCE = 0.005


def load_batch_module(batch_name: str) -> ModuleType:
    path = BATCH_DIR / f"{batch_name}.py"
    if not path.exists():
        raise SystemExit(f"unknown batch module: {path}")
    spec = importlib.util.spec_from_file_location(f"screen_batches_{batch_name}", path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise SystemExit(f"could not load batch module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_manifest_guard(iteration_dir: Path, candidate_ids: list[str]) -> dict:
    """Refuse to run unless the preregistered manifest lists exactly this
    batch's candidate ids. Copies the guard pattern of `load_manifest_guard`
    in `run_h20260927_01_sleeve_combination.py` / `run_h20260928_01_s3_rebalance_tranching.py`."""
    manifest_path = iteration_dir / "candidate-manifest.json"
    if not manifest_path.exists():
        raise SystemExit(f"missing candidate manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    ids = [c["candidate_id"] for c in manifest["candidates"]]
    if sorted(ids) != sorted(candidate_ids):
        raise SystemExit(f"candidate manifest guard failed: manifest={ids} batch={candidate_ids}")
    return manifest


def git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
        )
        return out.stdout.strip()
    except Exception:  # pragma: no cover - defensive
        return "unknown"


def pct(x: float | None) -> str:
    return "n/a" if x is None or not np.isfinite(x) else f"{x * 100:.1f}%"


def fmt(x: float | None, nd: int = 2) -> str:
    return "n/a" if x is None or not np.isfinite(x) else f"{x:.{nd}f}"


def render_leaderboard_md(leaderboard: dict) -> str:
    lines = [
        f"# Screening lane: {leaderboard['batch']}",
        "",
        f"Generated {leaderboard['generated_at']} at commit {leaderboard['git_commit']}. "
        f"Cost {leaderboard['cost_bps_primary']:.0f}/{leaderboard['cost_bps_stress']:.0f} bp "
        f"primary/stress. n_trials={leaderboard['n_trials']}.",
        "",
        "| id | skipped | anchor Sharpe | select Sharpe | stress Sharpe | anchor CAGR"
        " | anchor DD | G1 pass (anchor) | corr S3 (anchor) | edge anchor | edge stress"
        " | diversifier_pass | DSR anchor |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in leaderboard["candidates"]:
        if r.get("skipped"):
            lines.append(f"| {r['id']} | yes ({r.get('skip_reason', '')}) |" + " n/a |" * 10)
            continue
        judged = r["judged"]
        n_off = len(r["offsets"])
        div = r["diversifier"]
        corr = r["correlation_with_s3"]["anchor"]
        dsr = r.get("dsr_anchor")
        anchor_sharpe = fmt(judged["anchor"]["sharpe"])
        select_sharpe = fmt(judged["select"]["sharpe"])
        stress_sharpe = fmt(judged["stress"]["sharpe"])
        anchor_cagr = pct(judged["anchor"]["cagr"])
        anchor_dd = pct(judged["anchor"]["max_dd"])
        g1_count = r["per_window"]["anchor"]["g1_pass_count_10bp"]
        edge_anchor = fmt(div["anchor"]["judged_edge"])
        edge_stress = fmt(div["stress"]["judged_edge"])
        lines.append(
            f"| {r['id']} | no | {anchor_sharpe} | {select_sharpe} | {stress_sharpe}"
            f" | {anchor_cagr} | {anchor_dd} | {g1_count}/{n_off} | {fmt(corr)}"
            f" | {edge_anchor} | {edge_stress} | {div['pass']} | {fmt(dsr)} |"
        )
    return "\n".join(lines) + "\n"


def run_batch(batch_name: str, *, iteration: str | None, smoke: bool) -> Path:
    module = load_batch_module(batch_name)
    candidates: list[lane.ScreenCandidate] = module.CANDIDATES
    ids = [c.id for c in candidates]
    if len(ids) != len(set(ids)):
        raise SystemExit(f"duplicate candidate ids in batch {batch_name}: {ids}")

    if smoke:
        out_dir = SCREENS_DIR / "smoke"
    else:
        if not iteration:
            raise SystemExit("--iteration is required to run a real (non-smoke) batch")
        load_manifest_guard(ITERATIONS_DIR / iteration, ids)
        out_dir = SCREENS_DIR / batch_name
    out_dir.mkdir(parents=True, exist_ok=True)

    close, _open, leg_open, leg_close, rf = lane.load_batch_panel(candidates)
    shy_ret = (close[lane.CASH] / close[lane.CASH].shift(1) - 1.0).fillna(0.0)
    s3_ret10, _s3_turn10 = lane.s3_incumbent(close, leg_open, leg_close, lane.COST_BPS_PRIMARY)

    n_trials = len(candidates)
    results: list[dict] = []
    returns_cols: dict[str, pd.Series] = {}
    for c in candidates:
        r = lane.evaluate_candidate(
            c,
            close=close,
            leg_open=leg_open,
            leg_close=leg_close,
            rf=rf,
            shy_ret=shy_ret,
            s3_ret10=s3_ret10,
            n_trials=n_trials,
        )
        if not r["skipped"]:
            for o, ser in r.pop("_returns_net10_by_offset").items():
                returns_cols[f"{c.id}__o{o:02d}__net10"] = ser
            for o, ser in r.pop("_returns_net20_by_offset").items():
                returns_cols[f"{c.id}__o{o:02d}__net20"] = ser
        results.append(r)
        print(f"  {c.id} done", flush=True)

    leaderboard = {
        "batch": batch_name,
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "git_commit": git_commit(),
        "engine_source_files": ENGINE_SOURCES,
        "cost_bps_primary": lane.COST_BPS_PRIMARY,
        "cost_bps_stress": lane.COST_BPS_STRESS,
        "windows": {k: list(v) for k, v in lane.WINDOWS.items()},
        "contaminated_windows": sorted(lane.CONTAMINATED_WINDOWS),
        "n_trials": n_trials,
        "smoke": smoke,
        "iteration": iteration,
        "candidates": results,
    }
    (out_dir / "leaderboard.json").write_text(
        json.dumps(leaderboard, indent=2, default=float), encoding="utf-8"
    )
    (out_dir / "leaderboard.md").write_text(render_leaderboard_md(leaderboard), encoding="utf-8")
    if returns_cols:
        pd.DataFrame(returns_cols).to_parquet(out_dir / "returns.parquet")
    else:  # pragma: no cover - only when every candidate was skipped
        pd.DataFrame().to_parquet(out_dir / "returns.parquet")
    return out_dir


def self_check() -> int:
    ok = True
    base.WARMUP_START = "2015-01-02"
    close, open_ = base.load_panel(salvage.symbols())
    leg_open, leg_close = salvage.legs(close, open_)
    rf = (close[base.RF] / close[base.RF].shift(1) - 1.0).fillna(0.0)
    shy = (close[base.CASH] / close[base.CASH].shift(1) - 1.0).fillna(0.0)

    # --- (a) H-20260928-01: O00 anchor Sharpe and the median across 21 offsets ---
    tranch_results = json.loads(
        (ITERATIONS_DIR / "h20260928_01_s3_rebalance_tranching" / "results.json").read_text(
            encoding="utf-8"
        )
    )
    expected_o00 = tranch_results["candidates"]["O00"]["per_window"]["anchor"]["net10"]["sharpe"]
    expected_median = tranch_results["offset_distribution_net10"]["anchor"]["sharpe"]["median"]

    boost = salvage.boost_window(salvage.dip_signal(close), tranche.S3_BOOST_HOLD)
    anchor_window = tranche.WINDOWS["anchor"]
    sharpes: list[float] = []
    for o in tranche.OFFSETS:
        eff, cols = tranche.offset_effective(close, leg_open, leg_close, o, boost)
        ret, turn = tranche.simulate_effective(
            eff, cols, leg_open, leg_close, base.COST_BPS_PRIMARY
        )
        mask = tranche.window_mask(close.index, anchor_window)
        m = base.metrics(ret.loc[mask], rf, turn.loc[mask])
        sharpes.append(m.sharpe)
    got_o00 = sharpes[0]
    got_median = float(np.median(sharpes))

    print("--- self-check (a): H-20260928-01 S3 offsets (anchor window) ---")
    print(f"  O00 anchor sharpe:    expected {expected_o00:.6f}  got {got_o00:.6f}")
    print(f"  median anchor sharpe: expected {expected_median:.6f}  got {got_median:.6f}")
    if abs(got_o00 - expected_o00) > SELF_CHECK_TOLERANCE:
        ok = False
        print("  MISMATCH: O00 anchor sharpe")
    if abs(got_median - expected_median) > SELF_CHECK_TOLERANCE:
        ok = False
        print("  MISMATCH: median anchor sharpe")

    # --- (b) H-20260927-01: M3 Sharpe edges in anchor and stress ---
    combo_results = json.loads(
        (ITERATIONS_DIR / "h20260927_01_sleeve_combination" / "results.json").read_text(
            encoding="utf-8"
        )
    )
    expected_edge_anchor = combo_results["adoption"]["M3"]["sharpe_edge_anchor"]
    expected_edge_stress = combo_results["adoption"]["M3"]["sharpe_edge_stress"]

    start = combo.common_start(close)
    index = close.index[close.index >= start]
    rets10 = combo.sleeve_returns(close, leg_open, leg_close, base.COST_BPS_PRIMARY)
    rets10 = {k: v.loc[index] for k, v in rets10.items()}
    r_m3, t_m3 = combo.combine_portfolio(
        rets10, index, combo.WEIGHT_FNS["M3"], base.COST_BPS_PRIMARY
    )

    got_edges: dict[str, float] = {}
    for wname in ("anchor", "stress"):
        window = combo.WINDOWS[wname]
        m = combo.window_mask(index, window)
        met_m3 = base.metrics(r_m3.loc[m], rf, t_m3.loc[m])
        target_vol = float(r_m3.loc[m].std(ddof=1))
        r_s3_win = rets10["s3"].loc[m].to_numpy()
        r_shy_win = shy.loc[index].loc[m].to_numpy()
        k = combo.solve_k(target_vol, r_s3_win, r_shy_win)
        ci_ret = pd.Series(combo.control_series(k, r_s3_win, r_shy_win), index=index[m])
        zero_turn = pd.Series(0.0, index=ci_ret.index)
        met_c = base.metrics(ci_ret, rf, zero_turn)
        got_edges[wname] = met_m3.sharpe - met_c.sharpe

    print("--- self-check (b): H-20260927-01 M3 sleeve combination ---")
    print(f"  edge anchor: expected {expected_edge_anchor:.6f}  got {got_edges['anchor']:.6f}")
    print(f"  edge stress: expected {expected_edge_stress:.6f}  got {got_edges['stress']:.6f}")
    if abs(got_edges["anchor"] - expected_edge_anchor) > SELF_CHECK_TOLERANCE:
        ok = False
        print("  MISMATCH: edge anchor")
    if abs(got_edges["stress"] - expected_edge_stress) > SELF_CHECK_TOLERANCE:
        ok = False
        print("  MISMATCH: edge stress")

    print("SELF-CHECK " + ("PASSED" if ok else "FAILED"))
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", help="module name under scripts/screen_batches/")
    ap.add_argument("--iteration", help="iteration id with a matching candidate-manifest.json")
    ap.add_argument("--smoke", action="store_true", help="skip the manifest guard")
    ap.add_argument("--self-check", action="store_true", dest="self_check")
    args = ap.parse_args(argv)

    if args.self_check:
        return self_check()

    if not args.batch:
        raise SystemExit("--batch is required unless --self-check is given")

    out_dir = run_batch(args.batch, iteration=args.iteration, smoke=args.smoke)
    print(f"wrote {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
