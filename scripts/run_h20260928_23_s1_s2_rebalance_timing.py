"""T-20260928-01: how much of S1's and S2's headline numbers is rebalance-date luck?

H-20260928-01 found that S3's live month-end signal day was the best of 21
possible days in the recent window. This script asks the identical
descriptive question -- reusing the same frozen engine, cost model,
next-open fills and metrics -- for S2 (21 monthly offsets) and S1 (5 weekly
offsets). Purely descriptive: there is no pass condition and no offset is
adopted; the live rule (O00) stays in force either way.

Preregistered in two candidate manifests (the lightweight single-mechanism
iteration gate caps a path at 24 candidates, so S2's 21 and S1's 5 cannot
share one search-space path without a full campaign contract):

  reports/research/iterations/h20260928_23_s1_s2_rebalance_timing/candidate-manifest.json
      (S2, O00..O20)
  reports/research/iterations/h20260928_23_s1_rebalance_timing/candidate-manifest.json
      (S1, O00..O04)

O00 is asserted equal to `salvage.run_cell` for both sleeves (S1: no vol
target; S2: the 2026-09-23 renewal down-only vol target 0.156, S2_TARGET
below, matching scripts/run_h20260927_01_sleeve_combination.py).

Windows: stress 2016-05-02..2023-08-31 for S2, 2017-01-03..2023-08-31 for S1
(252-session lookback needs a year of warmup before it produces picks);
select 2023-09-18..2025-12-31; anchor 2024-01-08..2026-09-16 (frozen gate);
2026-01-02..2026-09-17 reported but flagged contaminated.

    scripts/run_capped.sh --mem 1.8G -- \
        uv run python scripts/run_h20260928_23_s1_s2_rebalance_timing.py

Writes results.json/report.md/trial-ledger.jsonl into both iteration
directories, plus a combined results.json/report.md into the S2 (primary)
directory covering both sleeves, and appends the per-sleeve paths to each
search-space.json's evaluation_report_paths/trial_ledger_paths (already
preregistered there).
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

S2_TARGET = 0.156  # 2026-09-23 renewal, card H-20260922-05 path A
PANEL_START = "2015-01-02"  # requested; matches the S3 script's WARMUP_START fix
# The SIP daily archive's earliest session is 2016-01-04 (confirmed by
# h20260928_01_s3_rebalance_tranching's own results.json panel_first_session),
# so a correctly-warmed-up panel starts there, not at PANEL_START itself. The
# bug this guards against is base.WARMUP_START silently staying at its
# recent-menu default ("2022-06-01"), six years later than the archive start.
PANEL_START_LATEST_ACCEPTABLE = "2016-01-10"

SLEEVES: dict[str, dict[str, Any]] = {
    "s2": {
        "iter_id": "h20260928_23_s1_s2_rebalance_timing",
        "rebal": "monthly",
        "n_offsets": 21,
        "target": S2_TARGET,
        "windows": {
            "stress": ("2016-05-02", "2023-08-31"),
            "select": ("2023-09-18", "2025-12-31"),
            "anchor": (base.ANCHOR_START, base.ANCHOR_END),
            "holdout_2026_contaminated": ("2026-01-02", "2026-09-17"),
        },
        "path_name": "s2_rebalance_timing",
    },
    "s1": {
        "iter_id": "h20260928_23_s1_rebalance_timing",
        "rebal": "weekly",
        "n_offsets": 5,
        "target": None,
        "windows": {
            "stress": ("2017-01-03", "2023-08-31"),
            "select": ("2023-09-18", "2025-12-31"),
            "anchor": (base.ANCHOR_START, base.ANCHOR_END),
            "holdout_2026_contaminated": ("2026-01-02", "2026-09-17"),
        },
        "path_name": "s1_rebalance_timing",
    },
}

PRIMARY_ITER_ID = "h20260928_23_s1_s2_rebalance_timing"


def out_dir_for(iter_id: str) -> Path:
    return ROOT / "reports/research/iterations" / iter_id


def load_manifest_guard(key: str) -> dict[str, Any]:
    cfg = SLEEVES[key]
    manifest_path = out_dir_for(cfg["iter_id"]) / "candidate-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected_ids = [f"O{o:02d}" for o in range(cfg["n_offsets"])]
    ids = [c["candidate_id"] for c in manifest["candidates"]]
    if ids != expected_ids:
        raise SystemExit(f"{key} candidate manifest guard failed: {ids}")
    return manifest


def shifted_signal_dates(index: pd.DatetimeIndex, rebal: str, offset: int) -> list[pd.Timestamp]:
    """Rebalance-cycle signal sessions moved `offset` sessions later."""
    flags = base.rebalance_flags(index, rebal).to_numpy()
    positions = np.flatnonzero(flags) + offset
    return [index[i] for i in positions if i < len(index)]


def sleeve_weights_offset(
    close: pd.DataFrame, key: str, offset: int
) -> tuple[pd.DataFrame, list[pd.Timestamp]]:
    """salvage.sleeve_weights(close, key) with the signal dates shifted."""
    cfg = salvage.SLEEVES[key]
    menu = [s for s in base.MENUS[cfg["menu"]] if s in close.columns]
    cols = sorted(set(menu + [base.CASH]))
    score = base.momentum_score(close, cfg["lookback"])
    cash_score = score[base.CASH]
    signal_dates = shifted_signal_dates(close.index, cfg["rebal"], offset)
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


def offset_effective(
    close: pd.DataFrame,
    leg_open: pd.DataFrame,
    leg_close: pd.DataFrame,
    key: str,
    offset: int,
    target: float | None,
) -> np.ndarray:
    weights, signal_dates = sleeve_weights_offset(close, key, offset)
    gross, _ = salvage.simulate(weights, leg_open, leg_close, np.ones(len(close.index)), 0.0)
    scale = salvage.vol_scale(close.index, signal_dates, gross, target)
    cols = list(weights.columns)
    cash_i = cols.index(base.CASH)
    wb = weights.to_numpy(dtype=float)
    risk = wb.copy()
    risk[:, cash_i] = 0.0
    eff = risk * scale[:, None]
    eff[:, cash_i] = wb[:, cash_i] + (1.0 - scale) * risk.sum(axis=1)
    return eff, cols


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


def window_mask(index: pd.DatetimeIndex, window: tuple[str, str]) -> np.ndarray:
    a, b = window
    return (index >= a) & (index <= b)


def run_sleeve(
    key: str,
    close: pd.DataFrame,
    leg_open: pd.DataFrame,
    leg_close: pd.DataFrame,
    rf: pd.Series,
) -> dict[str, Any]:
    cfg = SLEEVES[key]
    manifest = load_manifest_guard(key)
    target = cfg["target"]

    eff_by_offset: dict[int, np.ndarray] = {}
    cols: list[str] = []
    for o in range(cfg["n_offsets"]):
        eff_by_offset[o], cols = offset_effective(close, leg_open, leg_close, key, o, target)

    ref10, _ = salvage.run_cell(close, leg_open, leg_close, key, target, base.COST_BPS_PRIMARY)
    o00_10, _ = simulate_effective(eff_by_offset[0], cols, leg_open, leg_close, 10.0)
    max_abs = float(np.max(np.abs(ref10.to_numpy() - o00_10.to_numpy())))
    if max_abs > 1e-12:
        raise SystemExit(f"{key} O00 does not reproduce salvage.run_cell: max abs diff {max_abs}")

    candidates_out: dict[str, Any] = {}
    trial_rows: list[dict[str, Any]] = []
    for o in range(cfg["n_offsets"]):
        cid = f"O{o:02d}"
        eff = eff_by_offset[o]
        per_window: dict[str, Any] = {}
        by_cost = {
            "net10": simulate_effective(eff, cols, leg_open, leg_close, base.COST_BPS_PRIMARY),
            "net20": simulate_effective(eff, cols, leg_open, leg_close, base.COST_BPS_STRESS),
        }
        for wname, window in cfg["windows"].items():
            m = window_mask(close.index, window)
            per_window[wname] = {
                label: asdict(base.metrics(r.loc[m], rf, t.loc[m]))
                for label, (r, t) in by_cost.items()
            }
            trial_rows.append({"candidate_id": cid, "window": wname, **per_window[wname]})
        candidates_out[cid] = {"per_window": per_window}

    offset_ids = [f"O{o:02d}" for o in range(cfg["n_offsets"])]
    distribution: dict[str, Any] = {}
    for wname in cfg["windows"]:
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
                "median_pct_below_o00": (
                    float((live - np.median(vals)) / abs(live)) if live not in (0.0,) else None
                ),
            }
        distribution[wname] = dist_w

    # Queue's highlight rule: live top 3 AND median Sharpe > 20% below O00's Sharpe.
    highlight: dict[str, bool] = {}
    for wname, dist_w in distribution.items():
        sh = dist_w["sharpe"]
        highlight[wname] = bool(
            sh["o00_rank_from_best_1_is_best"] <= 3
            and sh["o00"] != 0
            and (sh["o00"] - sh["median"]) / abs(sh["o00"]) > 0.20
        )

    results = {
        "iter_id": cfg["iter_id"],
        "sleeve": key,
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "manifest_candidate_count": manifest["candidate_count"],
        "windows": {k: list(v) for k, v in cfg["windows"].items()},
        "panel_first_session": str(close.index[0].date()),
        "panel_last_session": str(close.index[-1].date()),
        "o00_reproduces_salvage_run_cell_max_abs_diff": max_abs,
        "target": target,
        "candidates": candidates_out,
        "offset_distribution_net10": distribution,
        "highlight_rule_fired": highlight,
        "descriptive_only_no_adoption": True,
    }
    return results


def render_sleeve_report(key: str, results: dict[str, Any]) -> str:
    label = key.upper()
    lines = [
        f"# T-20260928-01 {label} rebalance timing luck (descriptive, no adoption)",
        "",
        f"Panel {results['panel_first_session']}..{results['panel_last_session']}. "
        f"O00 = live rule; Onn = signal moved nn sessions after the {label}'s own rebalance "
        "date. No offset is adopted from this run; O00 stays live regardless of rank.",
        "",
        "## Offset distribution (net 10 bp)",
        "",
        "| window | metric | min | median | max | O00 | O00 rank (1=best) |",
        "|---|---|---|---|---|---|---|",
    ]

    def pct(x: float) -> str:
        return "n/a" if x is None or not np.isfinite(x) else f"{x * 100:.1f}%"

    for wname, dist_w in results["offset_distribution_net10"].items():
        for metric, d in dist_w.items():
            fmt = (lambda v: f"{v:.2f}") if metric == "sharpe" else pct
            lines.append(
                f"| {wname} | {metric} | {fmt(d['min'])} | {fmt(d['median'])} | {fmt(d['max'])}"
                f" | {fmt(d['o00'])} | {d['o00_rank_from_best_1_is_best']} |"
            )
    lines += ["", "## Queue highlight rule (live top 3 AND median Sharpe >20% below O00)", ""]
    for wname, fired in results["highlight_rule_fired"].items():
        tag = "**date-neutral expectation**" if fired else "not triggered"
        lines.append(f"- {wname}: {tag}")
    lines.append("")
    return "\n".join(lines) + "\n"


def write_sleeve_outputs(key: str, results: dict[str, Any]) -> None:
    cfg = SLEEVES[key]
    out_dir = out_dir_for(cfg["iter_id"])
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    trial_path = out_dir / "trial-ledger.jsonl"
    offset_ids = [f"O{o:02d}" for o in range(cfg["n_offsets"])]
    with trial_path.open("w", encoding="utf-8") as fh:
        for cid in offset_ids:
            for wname, per_window in results["candidates"][cid]["per_window"].items():
                fh.write(json.dumps({"candidate_id": cid, "window": wname, **per_window}) + "\n")
    (out_dir / "report.md").write_text(render_sleeve_report(key, results), encoding="utf-8")

    ss_path = out_dir / "search-space.json"
    search_space = json.loads(ss_path.read_text(encoding="utf-8"))
    for key_name, name in (
        ("evaluation_report_paths", "report.md"),
        ("evaluation_report_paths", "results.json"),
        ("trial_ledger_paths", "trial-ledger.jsonl"),
    ):
        rel = f"reports/research/iterations/{cfg['iter_id']}/{name}"
        if rel not in search_space.get(key_name, []):
            search_space.setdefault(key_name, []).append(rel)
    ss_path.write_text(json.dumps(search_space, indent=2) + "\n", encoding="utf-8")


def render_combined_report(all_results: dict[str, dict[str, Any]]) -> str:
    lines = [
        "# T-20260928-01: S1/S2 rebalance-date luck (date-neutral expectations)",
        "",
        "Descriptive only, mirroring H-20260928-01's S3 check with the same frozen engine, cost "
        "model (10 bp primary / 20 bp stress per side, next-open fills) and windows. No offset is "
        "adopted; both sleeves' live rules (O00) stay in force regardless of rank.",
        "",
    ]
    for key in ("s1", "s2"):
        results = all_results[key]
        label = key.upper()
        lines.append(f"## {label} ({results['manifest_candidate_count']} offsets)")
        lines.append("")
        lines.append(
            f"O00 reproduces `salvage.run_cell` (max abs diff "
            f"{results['o00_reproduces_salvage_run_cell_max_abs_diff']:.2e})."
        )
        lines.append("")
        lines.append("| window | metric | min | median | max | O00 | O00 rank (1=best) |")
        lines.append("|---|---|---|---|---|---|---|")

        def pct(x: float) -> str:
            return "n/a" if x is None or not np.isfinite(x) else f"{x * 100:.1f}%"

        for wname, dist_w in results["offset_distribution_net10"].items():
            for metric, d in dist_w.items():
                fmt = (lambda v: f"{v:.2f}") if metric == "sharpe" else pct
                lines.append(
                    f"| {wname} | {metric} | {fmt(d['min'])} | {fmt(d['median'])} | {fmt(d['max'])}"
                    f" | {fmt(d['o00'])} | {d['o00_rank_from_best_1_is_best']} |"
                )
        lines.append("")
        lines.append("Queue highlight rule (live top 3 AND median Sharpe >20% below O00):")
        for wname, fired in results["highlight_rule_fired"].items():
            tag = "**date-neutral expectation**" if fired else "not triggered"
            lines.append(f"- {wname}: {tag}")
        lines.append("")
    lines.append(
        "Per-sleeve preregistration, contracts and full trial ledgers: "
        "`reports/research/iterations/h20260928_23_s1_s2_rebalance_timing/` (S2) and "
        "`reports/research/iterations/h20260928_23_s1_rebalance_timing/` (S1)."
    )
    lines.append("")
    return "\n".join(lines) + "\n"


def assert_panel_covers_stress_window(index: pd.DatetimeIndex) -> None:
    """base.WARMUP_START defaults to "2022-06-01" (recent-menu grid screening).
    The stress windows here (2016-05.. for S2, 2017-01.. for S1) need the full
    panel, exactly like scripts/run_h20260928_01_s3_rebalance_tranching.py
    requires before its own load_panel call. A silently-truncated panel makes
    every "stress" number actually cover only 2022-06..2023-08."""
    if index[0] > pd.Timestamp(PANEL_START_LATEST_ACCEPTABLE):
        raise SystemExit(
            f"panel_first_session {index[0].date()} is later than "
            f"{PANEL_START_LATEST_ACCEPTABLE}; WARMUP_START was not applied before load_panel"
        )


def main() -> int:
    base.WARMUP_START = PANEL_START
    close, open_ = base.load_panel(salvage.symbols())
    assert_panel_covers_stress_window(close.index)
    leg_open, leg_close = salvage.legs(close, open_)
    rf = (close[base.RF] / close[base.RF].shift(1) - 1.0).fillna(0.0)

    all_results: dict[str, dict[str, Any]] = {}
    for key in ("s1", "s2"):
        results = run_sleeve(key, close, leg_open, leg_close, rf)
        write_sleeve_outputs(key, results)
        all_results[key] = results
        print(
            f"{key}: O00 max abs diff {results['o00_reproduces_salvage_run_cell_max_abs_diff']:.2e}"
        )

    combined_dir = out_dir_for(PRIMARY_ITER_ID)
    (combined_dir / "results.json").write_text(
        json.dumps(
            {
                "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
                "s1": all_results["s1"],
                "s2": all_results["s2"],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (combined_dir / "report.md").write_text(render_combined_report(all_results), encoding="utf-8")

    print(
        json.dumps(
            {
                "s1_highlight": all_results["s1"]["highlight_rule_fired"],
                "s2_highlight": all_results["s2"]["highlight_rule_fired"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
