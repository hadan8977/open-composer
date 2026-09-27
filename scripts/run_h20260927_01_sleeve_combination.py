"""H-20260927-01: does combining S1/S2/S3 beat delevering S3 alone at matched vol?

T-20260927-01 / candidate-manifest.json for
`reports/research/iterations/h20260927_01_sleeve_combination/`. Seven
candidates, frozen before any combination return is computed:

  M0  S3 alone (vt40 base target + QQQ oversold dip boost to 0.60 for 10
      sessions), unchanged reference -- no combination logic.
  M1  equal-thirds S1/S2/S3, rebalanced at each month-end close, effective
      at the next session open, intra-month weights drift with each
      sleeve's own daily net return.
  M2  0.5 S1 / 0 S2 / 0.5 S3, same rebalance convention.
  M3  trailing-63-session inverse-volatility weight across S1/S2/S3 (equal
      weight before 63 sessions of combination history exist).
  C1/C2/C3  each Mi's paired control: Ci = k*S3 + (1-k)*SHY, with k solved
      by bisection separately in each evaluation window so that
      std(Ci daily return) == std(Mi daily return) over that window (k
      capped at 1.0). Rebalanced daily at the fixed window k, no cost --
      conservative in the control's favor.

Everything about the three underlying sleeves (menu, lookback, vol targets,
dip boost) is inherited unchanged from `scripts/run_h20260922_05_salvage.py`;
the panel, cost model and next-open fill convention are inherited from
`scripts/run_h20260918_05_recent_menu.py`. Only the combination-level weight
rule, month-end rebalance-with-drift mechanics, combo rebalancing cost, and
the volatility-matched control are new in this script.

Windows (see candidate-manifest.json contracts.validation): common start
2017-02-01 (first session all three sleeves hold a non-cash position),
stress 2017-02-01..2023-09-15, select 2023-09-18..2025-12-31, anchor
2024-01-08..2026-09-17 (frozen gate, do-no-harm plus transfer criteria),
2026-01-02..2026-09-17 holdout reported but flagged contaminated (already
spent evaluating the individual sleeves).

    scripts/run_capped.sh --mem 1.8G -- uv run python scripts/run_h20260927_01_sleeve_combination.py

Writes results.json, report.md and trial-ledger.jsonl into the iteration
directory, and appends their paths to search-space.json's
evaluation_report_paths / trial_ledger_paths (already preregistered there).
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_h20260918_05_recent_menu as base  # noqa: E402
import run_h20260922_05_salvage as salvage  # noqa: E402

ITER_ID = "h20260927_01_sleeve_combination"
OUT_DIR = ROOT / "reports/research/iterations" / ITER_ID
MANIFEST_PATH = OUT_DIR / "candidate-manifest.json"

EXPECTED_CANDIDATE_IDS = ["M0", "M1", "M2", "M3", "C1", "C2", "C3"]

S2_TARGET = 0.156
S3_TARGET = 0.40
S3_BOOST_TARGET = 0.60
S3_BOOST_HOLD = 10
INV_VOL_LOOKBACK = 63

WINDOWS = {
    "stress": ("2017-02-01", "2023-09-15"),
    "select": ("2023-09-18", "2025-12-31"),
    "anchor": ("2024-01-08", "2026-09-17"),
    "holdout_2026_contaminated": ("2026-01-02", "2026-09-17"),
}

GATE_G1_CAGR, GATE_G1_MAXDD = 0.50, -0.35
GATE_G1ALT_SHARPE, GATE_G1ALT_CAGR = 2.0, 0.30
SHARPE_EDGE_MIN = 0.10

# Same widened warmup as scripts/stress_s3_pre_window.py: the frozen engine's
# own WARMUP_START (2022-06-01) is far too short to let S1's 252-session
# lookback or S3's 63-session absolute-momentum filter warm up before the
# stress window begins. 2015-01-02 is requested; the local SIP daily archive's
# earliest bar for every symbol in this family is 2016-01-04.
PANEL_START = "2015-01-02"


def load_manifest_guard() -> dict[str, Any]:
    """Refuse to run unless the preregistered candidate set is exactly M0-M3, C1-C3."""
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    ids = [c["candidate_id"] for c in manifest["candidates"]]
    if ids != EXPECTED_CANDIDATE_IDS:
        raise SystemExit(f"candidate manifest guard failed: {ids} != {EXPECTED_CANDIDATE_IDS}")
    return manifest


def common_start(close: pd.DataFrame) -> pd.Timestamp:
    """First session all three sleeves hold a non-cash position."""
    starts = []
    for key in ("s1", "s2", "s3"):
        w, _ = salvage.sleeve_weights(close, key)
        non_cash = [c for c in w.columns if c != base.CASH]
        has_pos = w[non_cash].sum(axis=1) > 0
        if not has_pos.any():
            raise ValueError(f"sleeve {key} never holds a non-cash position")
        starts.append(w.index[has_pos][0])
    return max(starts)


def sleeve_returns(
    close: pd.DataFrame,
    leg_open: pd.DataFrame,
    leg_close: pd.DataFrame,
    cost_bps: float,
) -> dict[str, pd.Series]:
    boost = salvage.boost_window(salvage.dip_signal(close), S3_BOOST_HOLD)
    r1, _ = salvage.run_cell(close, leg_open, leg_close, "s1", None, cost_bps)
    r2, _ = salvage.run_cell(close, leg_open, leg_close, "s2", S2_TARGET, cost_bps)
    r3, _ = salvage.run_cell(
        close,
        leg_open,
        leg_close,
        "s3",
        S3_TARGET,
        cost_bps,
        boost=boost,
        boost_target=S3_BOOST_TARGET,
    )
    return {"s1": r1, "s2": r2, "s3": r3}


def weights_equal_thirds(_rets: dict[str, np.ndarray], _asof: int) -> dict[str, float]:
    return {"s1": 1 / 3, "s2": 1 / 3, "s3": 1 / 3}


def weights_half_s1_s3(_rets: dict[str, np.ndarray], _asof: int) -> dict[str, float]:
    return {"s1": 0.5, "s2": 0.0, "s3": 0.5}


def weights_inverse_vol(
    rets: dict[str, np.ndarray], asof: int, lookback: int = INV_VOL_LOOKBACK
) -> dict[str, float]:
    """Inverse of trailing `lookback`-session daily-return stdev; equal weight
    when fewer than `lookback` sessions of combination history exist yet."""
    keys = ("s1", "s2", "s3")
    start = asof - lookback + 1
    if start < 0:
        return {k: 1 / 3 for k in keys}
    stds = {k: float(np.std(rets[k][start : asof + 1], ddof=1)) for k in keys}
    if any(v <= 0 or not np.isfinite(v) for v in stds.values()):
        return {k: 1 / 3 for k in keys}
    inv = {k: 1.0 / v for k, v in stds.items()}
    total = sum(inv.values())
    return {k: v / total for k, v in inv.items()}


WEIGHT_FNS = {
    "M1": weights_equal_thirds,
    "M2": weights_half_s1_s3,
    "M3": weights_inverse_vol,
}


def combine_portfolio(
    sleeve_rets: dict[str, pd.Series],
    index: pd.DatetimeIndex,
    weight_fn,
    combo_cost_bps: float,
) -> tuple[pd.Series, pd.Series]:
    """Month-end rebalance (signal on close, effective at next open), weights
    drift intra-month with each sleeve's own daily net return. Combo cost =
    combo_cost_bps * sum(abs(delta weight)), charged on the effective session."""
    keys = ("s1", "s2", "s3")
    rets_np = {k: sleeve_rets[k].reindex(index).fillna(0.0).to_numpy() for k in keys}
    r = np.column_stack([rets_np[k] for k in keys])
    n = len(index)
    flags = base.rebalance_flags(index, "monthly").to_numpy()
    signal_positions = np.flatnonzero(flags)
    rebal_effective = {int(i) + 1 for i in signal_positions if i + 1 < n}

    port_ret = np.zeros(n)
    turnover = np.zeros(n)
    w_prev = np.array([weights_dict_to_arr(weight_fn(rets_np, -1), keys)]).flatten()
    for i in range(n):
        if i in rebal_effective:
            target = weights_dict_to_arr(weight_fn(rets_np, i - 1), keys)
            turnover[i] = float(np.abs(target - w_prev).sum())
            w_prev = target
        day_ret = float(np.dot(w_prev, r[i]))
        port_ret[i] = day_ret - turnover[i] * combo_cost_bps / 10_000.0
        grown = w_prev * (1.0 + r[i])
        total = float(grown.sum())
        w_prev = grown / total if total != 0.0 else w_prev
    return pd.Series(port_ret, index=index), pd.Series(turnover, index=index)


def weights_dict_to_arr(d: dict[str, float], keys: tuple[str, ...]) -> np.ndarray:
    return np.array([d[k] for k in keys], dtype=float)


def window_mask(index: pd.DatetimeIndex, window: tuple[str, str]) -> pd.Series:
    a, b = window
    return (index >= a) & (index <= b)


def solve_k(target_vol: float, r_s3: np.ndarray, r_shy: np.ndarray) -> float:
    """Bisection for k in (0, 1] s.t. std(k*r_s3+(1-k)*r_shy) == target_vol.
    Capped at 1.0 (Ci = S3) if S3's own volatility does not reach target_vol."""

    def vol_at(k: float) -> float:
        return float(np.std(k * r_s3 + (1.0 - k) * r_shy, ddof=1))

    if not np.isfinite(target_vol) or target_vol <= 0:
        return 0.0
    if vol_at(1.0) <= target_vol:
        return 1.0
    lo, hi = 0.0, 1.0
    for _ in range(60):
        mid = (lo + hi) / 2.0
        if vol_at(mid) < target_vol:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def control_series(k: float, r_s3: np.ndarray, r_shy: np.ndarray) -> np.ndarray:
    return k * r_s3 + (1.0 - k) * r_shy


def flat_metrics(m: base.Metrics) -> dict[str, float]:
    return asdict(m)


def passes_g1_or_g1alt(cagr: float, max_dd: float, sharpe: float) -> bool:
    g1 = cagr >= GATE_G1_CAGR and max_dd >= GATE_G1_MAXDD
    g1alt = sharpe >= GATE_G1ALT_SHARPE and cagr >= GATE_G1ALT_CAGR
    return bool(g1 or g1alt)


def main() -> int:
    manifest = load_manifest_guard()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    base.WARMUP_START = PANEL_START
    close, open_ = base.load_panel(salvage.symbols())
    leg_open, leg_close = salvage.legs(close, open_)
    rf = (close[base.RF] / close[base.RF].shift(1) - 1.0).fillna(0.0)
    shy = (close[base.CASH] / close[base.CASH].shift(1) - 1.0).fillna(0.0)

    start = common_start(close)
    index_full = close.index
    mask_from_start = index_full >= start
    index = index_full[mask_from_start]

    rets10 = sleeve_returns(close, leg_open, leg_close, base.COST_BPS_PRIMARY)
    rets20 = sleeve_returns(close, leg_open, leg_close, base.COST_BPS_STRESS)
    rets10 = {k: v.loc[index] for k, v in rets10.items()}
    rets20 = {k: v.loc[index] for k, v in rets20.items()}

    # --- correlations, per window, primary-cost sleeve returns ---
    correlations: dict[str, dict[str, float]] = {}
    for wname, window in WINDOWS.items():
        m = window_mask(index, window)
        sub = pd.DataFrame({k: v.loc[m] for k, v in rets10.items()})
        corr = sub.corr()
        correlations[wname] = {
            "s1_s2": float(corr.loc["s1", "s2"]),
            "s1_s3": float(corr.loc["s1", "s3"]),
            "s2_s3": float(corr.loc["s2", "s3"]),
        }

    candidates_out: dict[str, Any] = {}
    trial_rows: list[dict[str, Any]] = []

    def record_series(
        cid: str, ret10: pd.Series, ret20: pd.Series, turn10: pd.Series, turn20: pd.Series
    ):
        per_window: dict[str, Any] = {}
        for wname, window in WINDOWS.items():
            m10 = window_mask(ret10.index, window)
            m20 = window_mask(ret20.index, window)
            met10 = base.metrics(ret10.loc[m10], rf, turn10.loc[m10])
            met20 = base.metrics(ret20.loc[m20], rf, turn20.loc[m20])
            per_window[wname] = {"net10": flat_metrics(met10), "net20": flat_metrics(met20)}
        candidates_out[cid] = {"per_window": per_window}
        for wname, body in per_window.items():
            trial_rows.append({"candidate_id": cid, "window": wname, **body})

    # --- M0: S3 alone, unchanged reference ---
    boost = salvage.boost_window(salvage.dip_signal(close), S3_BOOST_HOLD)
    m0_r10, m0_t10 = salvage.run_cell(
        close,
        leg_open,
        leg_close,
        "s3",
        S3_TARGET,
        base.COST_BPS_PRIMARY,
        boost=boost,
        boost_target=S3_BOOST_TARGET,
    )
    m0_r20, m0_t20 = salvage.run_cell(
        close,
        leg_open,
        leg_close,
        "s3",
        S3_TARGET,
        base.COST_BPS_STRESS,
        boost=boost,
        boost_target=S3_BOOST_TARGET,
    )
    record_series("M0", m0_r10.loc[index], m0_r20.loc[index], m0_t10.loc[index], m0_t20.loc[index])

    # --- M1-M3: combinations ---
    for cid, weight_fn in WEIGHT_FNS.items():
        r10, t10 = combine_portfolio(rets10, index, weight_fn, base.COST_BPS_PRIMARY)
        r20, t20 = combine_portfolio(rets20, index, weight_fn, base.COST_BPS_STRESS)
        record_series(cid, r10, r20, t10, t20)

    # --- C1-C3: vol-matched delevered-S3 controls, k solved per window ---
    pairing = {"C1": "M1", "C2": "M2", "C3": "M3"}
    k_by_window: dict[str, dict[str, float]] = {}
    for cid, mid in pairing.items():
        k_by_window[cid] = {}
        per_window: dict[str, Any] = {}
        for wname, window in WINDOWS.items():
            m = window_mask(index, window)
            # Mi's window-primary-cost return series, recomputed directly (cheap)
            if mid == "M1":
                r_mi_series, _ = combine_portfolio(
                    rets10, index, WEIGHT_FNS["M1"], base.COST_BPS_PRIMARY
                )
            elif mid == "M2":
                r_mi_series, _ = combine_portfolio(
                    rets10, index, WEIGHT_FNS["M2"], base.COST_BPS_PRIMARY
                )
            else:
                r_mi_series, _ = combine_portfolio(
                    rets10, index, WEIGHT_FNS["M3"], base.COST_BPS_PRIMARY
                )
            target_vol = float(r_mi_series.loc[m].std(ddof=1))
            r_s3_win = rets10["s3"].loc[m].to_numpy()
            r_shy_win = shy.loc[index].loc[m].to_numpy()
            k = solve_k(target_vol, r_s3_win, r_shy_win)
            k_by_window[cid][wname] = k
            ci_ret = pd.Series(control_series(k, r_s3_win, r_shy_win), index=index[m])
            zero_turn = pd.Series(0.0, index=ci_ret.index)
            met = base.metrics(ci_ret, rf, zero_turn)
            per_window[wname] = {"net10": flat_metrics(met), "net20": flat_metrics(met)}
        candidates_out[cid] = {"per_window": per_window, "paired_candidate": mid}
        for wname, body in per_window.items():
            trial_rows.append(
                {"candidate_id": cid, "window": wname, "paired_candidate": mid, **body}
            )

    # --- adoption rule ---
    adoption: dict[str, Any] = {}
    for mid, cid in {"M1": "C1", "M2": "C2", "M3": "C3"}.items():
        anchor_m = candidates_out[mid]["per_window"]["anchor"]
        stress_m = candidates_out[mid]["per_window"]["stress"]
        anchor_c = candidates_out[cid]["per_window"]["anchor"]
        stress_c = candidates_out[cid]["per_window"]["stress"]

        a = passes_g1_or_g1alt(
            anchor_m["net10"]["cagr"], anchor_m["net10"]["max_dd"], anchor_m["net10"]["sharpe"]
        )
        b = passes_g1_or_g1alt(
            anchor_m["net20"]["cagr"], anchor_m["net20"]["max_dd"], anchor_m["net20"]["sharpe"]
        )
        edge_anchor = anchor_m["net10"]["sharpe"] - anchor_c["net10"]["sharpe"]
        edge_stress = stress_m["net10"]["sharpe"] - stress_c["net10"]["sharpe"]
        c = bool(edge_anchor >= SHARPE_EDGE_MIN and edge_stress >= SHARPE_EDGE_MIN)
        d = bool(stress_m["net10"]["max_dd"] > stress_c["net10"]["max_dd"])
        adoption[mid] = {
            "paired_candidate": cid,
            "a_g1_or_g1alt_anchor_10bp": a,
            "b_g1_or_g1alt_anchor_20bp": b,
            "c_sharpe_edge_ge_0_10_anchor_and_stress": c,
            "d_stress_max_dd_shallower_than_control": d,
            "sharpe_edge_anchor": edge_anchor,
            "sharpe_edge_stress": edge_stress,
            "mi_stress_max_dd": stress_m["net10"]["max_dd"],
            "ci_stress_max_dd": stress_c["net10"]["max_dd"],
            "pass": bool(a and b and c and d),
        }

    results = {
        "iter_id": ITER_ID,
        "generated_at": pd.Timestamp.utcnow().isoformat(),
        "windows": {k: list(v) for k, v in WINDOWS.items()},
        "common_start": str(start.date()),
        "cost_bps_primary": base.COST_BPS_PRIMARY,
        "cost_bps_stress": base.COST_BPS_STRESS,
        "sleeve_pairwise_correlation": correlations,
        "candidates": candidates_out,
        "k_by_window": k_by_window,
        "adoption": adoption,
        "g3_placebo": "not_applicable_see_candidate_manifest_g3_not_applicable_reason",
        "overall_pass": any(v["pass"] for v in adoption.values()),
    }

    (OUT_DIR / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    with (OUT_DIR / "trial-ledger.jsonl").open("w", encoding="utf-8") as fh:
        for row in trial_rows:
            fh.write(json.dumps(row) + "\n")
    (OUT_DIR / "report.md").write_text(render_report(results, manifest), encoding="utf-8")

    # register the produced artifact paths into search-space.json (already preregistered there)
    ss_path = OUT_DIR / "search-space.json"
    search_space = json.loads(ss_path.read_text(encoding="utf-8"))
    for key, name in (
        ("evaluation_report_paths", "report.md"),
        ("trial_ledger_paths", "trial-ledger.jsonl"),
    ):
        rel = f"reports/research/iterations/{ITER_ID}/{name}"
        if rel not in search_space.get(key, []):
            search_space.setdefault(key, []).append(rel)
    rel_results = f"reports/research/iterations/{ITER_ID}/results.json"
    if rel_results not in search_space.get("evaluation_report_paths", []):
        search_space.setdefault("evaluation_report_paths", []).append(rel_results)
    ss_path.write_text(json.dumps(search_space, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({"overall_pass": results["overall_pass"], "adoption": adoption}, indent=2))
    return 0


def pct(x: float) -> str:
    return "n/a" if x is None or not np.isfinite(x) else f"{x * 100:.1f}%"


def render_report(results: dict[str, Any], manifest: dict[str, Any]) -> str:
    lines = [
        "# H-20260927-01 sleeve combination vs delevered control",
        "",
        f"Common start: {results['common_start']}. Cost {results['cost_bps_primary']:.0f}/"
        f"{results['cost_bps_stress']:.0f} bp primary/stress.",
        "",
        "## Anchor and stress window metrics (net10)",
        "",
        "| candidate | window | CAGR | Sharpe | max DD | turnover/yr |",
        "|---|---|---|---|---|---|",
    ]
    for cid, body in results["candidates"].items():
        for wname in ("stress", "anchor"):
            m = body["per_window"][wname]["net10"]
            lines.append(
                f"| {cid} | {wname} | {pct(m['cagr'])} | {m['sharpe']:.2f} | {pct(m['max_dd'])}"
                f" | {m['turnover_yr']:.2f} |"
            )
    lines += [
        "",
        "## Adoption rule",
        "",
        "| Mi | a | b | c | d | pass |",
        "|---|---|---|---|---|---|",
    ]
    for mid, row in results["adoption"].items():
        lines.append(
            f"| {mid} | {row['a_g1_or_g1alt_anchor_10bp']} | {row['b_g1_or_g1alt_anchor_20bp']} |"
            f" {row['c_sharpe_edge_ge_0_10_anchor_and_stress']} |"
            f" {row['d_stress_max_dd_shallower_than_control']} | {row['pass']} |"
        )
    lines += ["", "## Sleeve pairwise daily-return correlation", ""]
    for wname, corr in results["sleeve_pairwise_correlation"].items():
        lines.append(
            f"- {wname}: s1/s2 {corr['s1_s2']:.2f}, "
            f"s1/s3 {corr['s1_s3']:.2f}, s2/s3 {corr['s2_s3']:.2f}"
        )
    lines += ["", "## k by window", ""]
    for cid, kw in results["k_by_window"].items():
        lines.append(f"- {cid}: " + ", ".join(f"{w}={k:.3f}" for w, k in kw.items()))
    lines += ["", f"Overall pass: {results['overall_pass']}", ""]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
