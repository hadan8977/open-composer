"""H-20260928-01: does splitting S3 into four staggered tranches reduce drawdown?

T-20260927-02 / candidate-manifest.json for
`reports/research/iterations/h20260928_01_s3_rebalance_tranching/`. 22
candidates, frozen before any return is computed:

  O00..O20  S3 exactly as live (A4_levered menu, 63-session momentum, top 2,
            SHY absolute-momentum filter, vt40 down-only vol target, QQQ
            oversold dip boost to 0.60 for 10 sessions), except that the
            monthly signal close is moved `o` sessions after the last session
            of each month. O00 is the live rule (reference).
  T4        one account split into four equal tranches running O00, O05, O10
            and O15. Each tranche keeps its own picks and its own vol-target
            multiplier; the account holds the average of the four effective
            weight vectors, so trades between tranches net inside the account
            and costs are charged on the netted turnover.

The overlay machinery, cost model, next-open fills and metrics are inherited
unchanged from `scripts/run_h20260922_05_salvage.py` and
`scripts/run_h20260918_05_recent_menu.py`; O00 is asserted to reproduce
`salvage.run_cell` exactly. Only the signal-date shift and the tranche
averaging are new.

Windows: stress 2016-05-02..2023-08-31, select 2023-09-18..2025-12-31, anchor
2024-01-08..2026-09-16 (frozen gate), 2026-01-02..2026-09-17 reported but
flagged contaminated.

    scripts/run_capped.sh --mem 1.8G -- \
        uv run python scripts/run_h20260928_01_s3_rebalance_tranching.py
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

ITER_ID = "h20260928_01_s3_rebalance_tranching"
OUT_DIR = ROOT / "reports/research/iterations" / ITER_ID
MANIFEST_PATH = OUT_DIR / "candidate-manifest.json"

OFFSETS = list(range(21))
TRANCHE_OFFSETS = [0, 5, 10, 15]
EXPECTED_CANDIDATE_IDS = [f"O{o:02d}" for o in OFFSETS] + ["T4"]

S3_TARGET = 0.40
S3_BOOST_TARGET = 0.60
S3_BOOST_HOLD = 10
PANEL_START = "2015-01-02"

WINDOWS = {
    "stress": ("2016-05-02", "2023-08-31"),
    "select": ("2023-09-18", "2025-12-31"),
    "anchor": (base.ANCHOR_START, base.ANCHOR_END),
    "holdout_2026_contaminated": ("2026-01-02", "2026-09-17"),
}

GATE_G1_CAGR, GATE_G1_MAXDD = 0.50, -0.35
GATE_G1ALT_SHARPE, GATE_G1ALT_CAGR = 2.0, 0.30
MAX_SHARPE_GIVEUP = 0.05


def load_manifest_guard() -> dict[str, Any]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    ids = [c["candidate_id"] for c in manifest["candidates"]]
    if ids != EXPECTED_CANDIDATE_IDS:
        raise SystemExit(f"candidate manifest guard failed: {ids}")
    return manifest


def shifted_signal_dates(index: pd.DatetimeIndex, offset: int) -> list[pd.Timestamp]:
    """Month-end signal sessions moved `offset` sessions later."""
    flags = base.rebalance_flags(index, "monthly").to_numpy()
    positions = np.flatnonzero(flags) + offset
    return [index[i] for i in positions if i < len(index)]


def s3_weights(close: pd.DataFrame, offset: int) -> tuple[pd.DataFrame, list[pd.Timestamp]]:
    """salvage.sleeve_weights(close, "s3") with the signal dates shifted."""
    cfg = salvage.SLEEVES["s3"]
    menu = [s for s in base.MENUS[cfg["menu"]] if s in close.columns]
    cols = sorted(set(menu + [base.CASH]))
    score = base.momentum_score(close, cfg["lookback"])
    cash_score = score[base.CASH]
    signal_dates = shifted_signal_dates(close.index, offset)
    picks: dict[pd.Timestamp, list[str]] = {}
    for d in signal_dates:
        row = score.loc[d, menu].dropna()
        if row.empty:
            continue
        chosen = list(row.sort_values(ascending=False).index[: cfg["top_n"]])
        cs = cash_score.loc[d]
        if pd.notna(cs):
            chosen = [s for s in chosen if row[s] > cs]
        picks[d] = chosen
    return base.weights_from_selection(close.index, signal_dates, picks, cols), signal_dates


def effective_weights(weights: pd.DataFrame, scale: np.ndarray) -> np.ndarray:
    """The per-session weight vector salvage.simulate trades to."""
    cols = list(weights.columns)
    cash_i = cols.index(base.CASH)
    wb = weights.to_numpy(dtype=float)
    risk = wb.copy()
    risk[:, cash_i] = 0.0
    eff = risk * scale[:, None]
    eff[:, cash_i] = wb[:, cash_i] + (1.0 - scale) * risk.sum(axis=1)
    return eff


def simulate_effective(
    eff: np.ndarray,
    cols: list[str],
    leg_open: pd.DataFrame,
    leg_close: pd.DataFrame,
    cost_bps: float,
) -> tuple[pd.Series, pd.Series]:
    lo = leg_open[cols].to_numpy(dtype=float)
    lc = leg_close[cols].to_numpy(dtype=float)
    prev = np.vstack([np.zeros((1, eff.shape[1])), eff[:-1]])
    gross = (prev * lo).sum(axis=1) + (eff * lc).sum(axis=1)
    turnover = np.abs(eff - prev).sum(axis=1)
    rets = gross - turnover * cost_bps / 10_000.0
    return pd.Series(rets, index=leg_open.index), pd.Series(turnover, index=leg_open.index)


def offset_effective(
    close: pd.DataFrame,
    leg_open: pd.DataFrame,
    leg_close: pd.DataFrame,
    offset: int,
    boost: np.ndarray,
) -> tuple[np.ndarray, list[str]]:
    weights, signal_dates = s3_weights(close, offset)
    gross, _ = salvage.simulate(weights, leg_open, leg_close, np.ones(len(close.index)), 0.0)
    scale = salvage.vol_scale(close.index, signal_dates, gross, S3_TARGET, boost, S3_BOOST_TARGET)
    return effective_weights(weights, scale), list(weights.columns)


def window_mask(index: pd.DatetimeIndex, window: tuple[str, str]) -> np.ndarray:
    a, b = window
    return (index >= a) & (index <= b)


def passes_g1_or_g1alt(m: dict[str, float]) -> bool:
    g1 = m["cagr"] >= GATE_G1_CAGR and m["max_dd"] >= GATE_G1_MAXDD
    g1alt = m["sharpe"] >= GATE_G1ALT_SHARPE and m["cagr"] >= GATE_G1ALT_CAGR
    return bool(g1 or g1alt)


def main() -> int:
    manifest = load_manifest_guard()
    base.WARMUP_START = PANEL_START
    close, open_ = base.load_panel(salvage.symbols())
    leg_open, leg_close = salvage.legs(close, open_)
    rf = (close[base.RF] / close[base.RF].shift(1) - 1.0).fillna(0.0)
    boost = salvage.boost_window(salvage.dip_signal(close), S3_BOOST_HOLD)

    eff_by_offset: dict[int, np.ndarray] = {}
    cols: list[str] = []
    for o in OFFSETS:
        eff_by_offset[o], cols = offset_effective(close, leg_open, leg_close, o, boost)

    # O00 must be the live engine, bit for bit.
    ref10, _ = salvage.run_cell(
        close,
        leg_open,
        leg_close,
        "s3",
        S3_TARGET,
        base.COST_BPS_PRIMARY,
        boost=boost,
        boost_target=S3_BOOST_TARGET,
    )
    o00_10, _ = simulate_effective(eff_by_offset[0], cols, leg_open, leg_close, 10.0)
    max_abs = float(np.max(np.abs(ref10.to_numpy() - o00_10.to_numpy())))
    if max_abs > 1e-12:
        raise SystemExit(f"O00 does not reproduce salvage.run_cell: max abs diff {max_abs}")

    series: dict[str, np.ndarray] = {f"O{o:02d}": eff_by_offset[o] for o in OFFSETS}
    series["T4"] = np.mean([eff_by_offset[o] for o in TRANCHE_OFFSETS], axis=0)

    candidates_out: dict[str, Any] = {}
    trial_rows: list[dict[str, Any]] = []
    for cid, eff in series.items():
        per_window: dict[str, Any] = {}
        by_cost = {
            "net10": simulate_effective(eff, cols, leg_open, leg_close, base.COST_BPS_PRIMARY),
            "net20": simulate_effective(eff, cols, leg_open, leg_close, base.COST_BPS_STRESS),
        }
        for wname, window in WINDOWS.items():
            m = window_mask(close.index, window)
            per_window[wname] = {
                label: asdict(base.metrics(r.loc[m], rf, t.loc[m]))
                for label, (r, t) in by_cost.items()
            }
            trial_rows.append({"candidate_id": cid, "window": wname, **per_window[wname]})
        candidates_out[cid] = {"per_window": per_window}

    # Descriptive: where does the live month-end rule sit among the 21 offsets?
    offset_ids = [f"O{o:02d}" for o in OFFSETS]
    distribution: dict[str, Any] = {}
    for wname in WINDOWS:
        dist_w: dict[str, Any] = {}
        for metric in ("cagr", "sharpe", "max_dd"):
            vals = np.array(
                [candidates_out[c]["per_window"][wname]["net10"][metric] for c in offset_ids]
            )
            live = vals[0]
            dist_w[metric] = {
                "min": float(vals.min()),
                "median": float(np.median(vals)),
                "max": float(vals.max()),
                "spread": float(vals.max() - vals.min()),
                "o00": float(live),
                "o00_rank_from_best_1_is_best": int((vals > live).sum() + 1),
                "t4": float(candidates_out["T4"]["per_window"][wname]["net10"][metric]),
            }
        distribution[wname] = dist_w

    t4 = candidates_out["T4"]["per_window"]
    o0 = candidates_out["O00"]["per_window"]
    adoption = {
        "a_anchor_max_dd_shallower_than_o00": bool(
            t4["anchor"]["net10"]["max_dd"] > o0["anchor"]["net10"]["max_dd"]
        ),
        "b_stress_max_dd_shallower_than_o00": bool(
            t4["stress"]["net10"]["max_dd"] > o0["stress"]["net10"]["max_dd"]
        ),
        "c_sharpe_giveup_le_0_05_anchor_and_stress": bool(
            t4["anchor"]["net10"]["sharpe"] >= o0["anchor"]["net10"]["sharpe"] - MAX_SHARPE_GIVEUP
            and t4["stress"]["net10"]["sharpe"]
            >= o0["stress"]["net10"]["sharpe"] - MAX_SHARPE_GIVEUP
        ),
        "d_anchor_g1_or_g1alt_at_10_and_20bp": bool(
            passes_g1_or_g1alt(t4["anchor"]["net10"]) and passes_g1_or_g1alt(t4["anchor"]["net20"])
        ),
        "sharpe_delta_anchor": t4["anchor"]["net10"]["sharpe"] - o0["anchor"]["net10"]["sharpe"],
        "sharpe_delta_stress": t4["stress"]["net10"]["sharpe"] - o0["stress"]["net10"]["sharpe"],
        "max_dd_delta_anchor": t4["anchor"]["net10"]["max_dd"] - o0["anchor"]["net10"]["max_dd"],
        "max_dd_delta_stress": t4["stress"]["net10"]["max_dd"] - o0["stress"]["net10"]["max_dd"],
    }
    adoption["pass"] = all(
        adoption[k]
        for k in (
            "a_anchor_max_dd_shallower_than_o00",
            "b_stress_max_dd_shallower_than_o00",
            "c_sharpe_giveup_le_0_05_anchor_and_stress",
            "d_anchor_g1_or_g1alt_at_10_and_20bp",
        )
    )

    results = {
        "iter_id": ITER_ID,
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "manifest_candidate_count": manifest["candidate_count"],
        "windows": {k: list(v) for k, v in WINDOWS.items()},
        "panel_first_session": str(close.index[0].date()),
        "panel_last_session": str(close.index[-1].date()),
        "o00_reproduces_salvage_run_cell_max_abs_diff": max_abs,
        "tranche_offsets": TRANCHE_OFFSETS,
        "candidates": candidates_out,
        "offset_distribution_net10": distribution,
        "adoption": adoption,
        "g3_placebo": "not_applicable_see_candidate_manifest_g3_not_applicable_reason",
        "overall_pass": adoption["pass"],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    with (OUT_DIR / "trial-ledger.jsonl").open("w", encoding="utf-8") as fh:
        for row in trial_rows:
            fh.write(json.dumps(row) + "\n")
    (OUT_DIR / "report.md").write_text(render_report(results), encoding="utf-8")

    ss_path = OUT_DIR / "search-space.json"
    search_space = json.loads(ss_path.read_text(encoding="utf-8"))
    for key, name in (
        ("evaluation_report_paths", "report.md"),
        ("evaluation_report_paths", "results.json"),
        ("trial_ledger_paths", "trial-ledger.jsonl"),
    ):
        rel = f"reports/research/iterations/{ITER_ID}/{name}"
        if rel not in search_space.get(key, []):
            search_space.setdefault(key, []).append(rel)
    ss_path.write_text(json.dumps(search_space, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({"overall_pass": results["overall_pass"], "adoption": adoption}, indent=2))
    return 0


def pct(x: float) -> str:
    return "n/a" if x is None or not np.isfinite(x) else f"{x * 100:.1f}%"


def render_report(results: dict[str, Any]) -> str:
    lines = [
        "# H-20260928-01 S3 rebalance timing luck and four-tranche execution",
        "",
        f"Panel {results['panel_first_session']}..{results['panel_last_session']}. "
        "O00 = live month-end rule; Onn = signal moved nn sessions later; "
        f"T4 = four tranches at offsets {results['tranche_offsets']}.",
        "",
        "## Per-candidate metrics (net 10 bp)",
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
        "## Offset distribution (21 single-date versions, net 10 bp)",
        "",
        "| window | metric | min | median | max | O00 | O00 rank (1=best) | T4 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for wname, dist_w in results["offset_distribution_net10"].items():
        for metric, d in dist_w.items():
            fmt = (lambda v: f"{v:.2f}") if metric == "sharpe" else pct
            lines.append(
                f"| {wname} | {metric} | {fmt(d['min'])} | {fmt(d['median'])} | {fmt(d['max'])}"
                f" | {fmt(d['o00'])} | {d['o00_rank_from_best_1_is_best']} | {fmt(d['t4'])} |"
            )
    a = results["adoption"]
    lines += [
        "",
        "## Adoption rule (T4 vs O00)",
        "",
        f"- (a) anchor max DD shallower: {a['a_anchor_max_dd_shallower_than_o00']}"
        f" (delta {a['max_dd_delta_anchor'] * 100:+.1f} pp)",
        f"- (b) stress max DD shallower: {a['b_stress_max_dd_shallower_than_o00']}"
        f" (delta {a['max_dd_delta_stress'] * 100:+.1f} pp)",
        f"- (c) Sharpe give-up <= 0.05 in anchor and stress:"
        f" {a['c_sharpe_giveup_le_0_05_anchor_and_stress']}"
        f" (anchor {a['sharpe_delta_anchor']:+.3f}, stress {a['sharpe_delta_stress']:+.3f})",
        f"- (d) anchor G1/G1' at 10 and 20 bp: {a['d_anchor_g1_or_g1alt_at_10_and_20bp']}",
        "",
        f"Overall pass: {results['overall_pass']}",
        "",
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
