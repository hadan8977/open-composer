"""T-20261005-41 (R1005-T41): next-open (O) vs next-close (C) fills for the four ETF sleeves.

Measurement only: no strategy, spec or threshold is changed.  Rerun with

    scripts/run_capped.sh --mem 1.2G -- uv run python \
        reports/research/program/etf-open-close-2026-10-07/compute.py

Definitions (the signal and the target-weight rows are identical in both modes)
* ``eff[t]`` is the target-weight row effective for session t, i.e. decided at the close of
  session t-1 (frozen engines: scripts/run_h20260918_05_recent_menu.py, run_h20260922_05_salvage.py,
  run_h20260928_23_s1_s2_rebalance_timing.py, screen_lane.py; S1/S2/S3 exactly as in
  reports/research/program/etf-dsr-2026-10-08/compute.py, C2 from screen_batches/h20260928_20).
* O (current paper practice: day market order queued after the close, executes at the 09:30 open):
      gross[t] = eff[t-1] . lo[t] + eff[t] . lc[t]   (lo = open/prev_close-1, lc = close/open-1)
  = ``t23.simulate_effective`` (asserted equal to ``salvage.run_cell`` / the stored C2 screen).
* C (the same row traded at the close of session t instead of its open):
      gross[t] = eff[t-1] . (lo[t] + lc[t])
  Same additive decomposition as the frozen engine, so the only difference is which price the
  weight change trades at.  Turnover |eff[t] - eff[t-1]| and the per-side cost are the same.
  Identity (asserted): gross_O - gross_C = (eff[t] - eff[t-1]) . lc[t], the open-to-close return
  of the session on the weight change, so cost cancels exactly when both modes cost the same.
* Sleeves S1/S2/S3: equal-weight mean of 5 rebalance offsets (config offsets_blend); C2 is
  calendar-anchored (one series).  Windows: recent (config recent_window_start) and full
  (2017-01-03, as in the T-31 DSR run), through the last session of the panel.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import run_h20260918_05_recent_menu as base  # noqa: E402
import run_h20260922_05_salvage as salvage  # noqa: E402
import run_h20260928_23_s1_s2_rebalance_timing as t23  # noqa: E402
import screen_batch  # noqa: E402
import screen_lane as lane  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "etf_dsr_compute", ROOT / "reports/research/program/etf-dsr-2026-10-08/compute.py"
)
assert _spec is not None and _spec.loader is not None
t31 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(t31)

from open_composer.research import scorecard_v2 as sc  # noqa: E402

CFG = sc.load_config()
RECENT_START = CFG["recent_window_start"]
FULL_START = t31.FULL_START
N_OFFSETS = 5
COST_BPS = 10.0
BOOT_DRAWS = 2000
BOOT_BLOCK = 21
BOOT_SEED = 20261005
SLEEVES = ("S1", "S2", "S3", "C2")

# Market phases of reports/research/program/regimes-2026-10-01 (data/research/equity_book/regimes/
# phases.json, scripts/analyze_equity_book_regimes.py).  Recent P11 ends at the panel end here.
PHASES = [
    ("P01", "2024-01-08", "2024-07-16", "advance"),
    ("P02", "2024-07-17", "2024-08-05", "correction"),
    ("P03", "2024-08-06", "2024-09-19", "rebound"),
    ("P04", "2024-09-20", "2025-02-19", "advance"),
    ("P05", "2025-02-20", "2025-04-08", "correction"),
    ("P06", "2025-04-09", "2025-06-26", "rebound"),
    ("P07", "2025-06-27", "2026-01-27", "advance"),
    ("P08", "2026-01-28", "2026-03-30", "correction"),
    ("P09", "2026-03-31", "2026-04-14", "rebound"),
    ("P10", "2026-04-15", "2026-06-30", "advance"),
    ("P11", "2026-07-01", "9999-12-31", "advance"),
    ("H01", "2017-10-02", "2018-02-08", "advance"),
    ("H02", "2018-02-09", "2018-08-07", "rebound"),
    ("H03", "2018-08-08", "2018-09-20", "advance"),
    ("H04", "2018-09-21", "2018-12-24", "correction"),
    ("H05", "2018-12-26", "2019-04-12", "rebound"),
    ("H06", "2019-04-15", "2020-02-19", "advance"),
    ("H07", "2020-02-20", "2020-03-23", "correction"),
    ("H08", "2020-03-24", "2020-08-10", "rebound"),
    ("H09", "2020-08-11", "2020-09-02", "advance"),
    ("H10", "2020-09-03", "2020-09-23", "correction"),
    ("H11", "2020-09-24", "2020-11-11", "rebound"),
    ("H12", "2020-11-12", "2022-01-03", "advance"),
    ("H13", "2022-01-04", "2022-10-12", "correction"),
    ("H14", "2022-10-13", "2023-08-31", "rebound"),
]


# --------------------------------------------------------------------------------------------
# simulation
# --------------------------------------------------------------------------------------------
def sim_close(
    eff: np.ndarray,
    cols: list[str],
    leg_open: pd.DataFrame,
    leg_close: pd.DataFrame,
    cost_bps: float,
) -> tuple[pd.Series, pd.Series]:
    """Mode C: the position held during session t is eff[t-1] (opened at the close of t-1);
    the change to eff[t] trades at the close of t."""
    lo = leg_open[cols].to_numpy(dtype=float)
    lc = leg_close[cols].to_numpy(dtype=float)
    prev = np.vstack([np.zeros((1, eff.shape[1])), eff[:-1]])
    gross = (prev * (lo + lc)).sum(axis=1)
    turnover = np.abs(eff - prev).sum(axis=1)
    rets = gross - turnover * cost_bps / 10_000.0
    return pd.Series(rets, index=leg_open.index), pd.Series(turnover, index=leg_open.index)


def gross_open_minus_close(eff: np.ndarray, cols: list[str], leg_close: pd.DataFrame) -> pd.Series:
    prev = np.vstack([np.zeros((1, eff.shape[1])), eff[:-1]])
    lc = leg_close[cols].to_numpy(dtype=float)
    return pd.Series(((eff - prev) * lc).sum(axis=1), index=leg_close.index)


def sleeve_paths(
    close: pd.DataFrame, leg_open: pd.DataFrame, leg_close: pd.DataFrame, sig: np.ndarray
) -> dict[str, dict[str, Any]]:
    """Per sleeve: list of (eff, cols) over the offsets used."""
    boost = salvage.boost_window(sig, t31.BOOST_HOLD_S3)
    out: dict[str, dict[str, Any]] = {}
    for k in ("S1", "S2", "S3"):
        cfg = t31.SPEC_CELL[k]
        items = []
        for o in range(N_OFFSETS):
            if k == "S3":
                items.append(
                    t31.eff_for(
                        close,
                        leg_open,
                        leg_close,
                        cfg,
                        o,
                        t31.BASE_TARGET_S3,
                        boost,
                        t31.BOOST_TARGET_S3,
                    )
                )
            else:
                items.append(t31.eff_for(close, leg_open, leg_close, cfg, o, cfg["target"]))
        # parity: offset 0, O mode, equals the frozen salvage.run_cell (as in T-31)
        if k == "S3":
            ref, _ = salvage.run_cell(
                close,
                leg_open,
                leg_close,
                "s3",
                t31.BASE_TARGET_S3,
                COST_BPS,
                boost=boost,
                boost_target=t31.BOOST_TARGET_S3,
            )
        else:
            ref, _ = salvage.run_cell(
                close, leg_open, leg_close, k.lower(), cfg["target"], COST_BPS
            )
        o0, _ = t23.simulate_effective(items[0][0], items[0][1], leg_open, leg_close, COST_BPS)
        out[k] = {"items": items, "parity_vs_run_cell": float(np.max(np.abs(ref - o0)))}
    mod = screen_batch.load_batch_module("h20260928_20_recent_opt")
    cand = [c for c in screen_batch.candidates_from_module(mod) if c.id == "C2"][0]
    wf, _ = lane.weights_frame(close, cand, 0)
    cols = list(wf.columns)
    eff = wf.to_numpy(dtype=float)
    ref, _ = salvage.simulate(wf, leg_open, leg_close, np.ones(len(close.index)), COST_BPS)
    o0, _ = t23.simulate_effective(eff, cols, leg_open, leg_close, COST_BPS)
    out["C2"] = {"items": [(eff, cols)], "parity_vs_run_cell": float(np.max(np.abs(ref - o0)))}
    return out


def blend_series(
    items: list[tuple[np.ndarray, list[str]]],
    leg_open: pd.DataFrame,
    leg_close: pd.DataFrame,
    mode: str,
    cost_bps: float,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    rets, turns, gaps = [], [], []
    for eff, cols in items:
        if mode == "O":
            r, t = t23.simulate_effective(eff, cols, leg_open, leg_close, cost_bps)
        else:
            r, t = sim_close(eff, cols, leg_open, leg_close, cost_bps)
        rets.append(r)
        turns.append(t)
        gaps.append(gross_open_minus_close(eff, cols, leg_close))
    return (
        pd.concat(rets, axis=1).mean(axis=1),
        pd.concat(turns, axis=1).mean(axis=1),
        pd.concat(gaps, axis=1).mean(axis=1),
    )


# --------------------------------------------------------------------------------------------
# statistics
# --------------------------------------------------------------------------------------------
def stationary_bootstrap_mean(
    x: np.ndarray, draws: int, mean_block: int, rng: np.random.Generator
) -> np.ndarray:
    n = len(x)
    p = 1.0 / mean_block
    out = np.empty(draws)
    pos = np.arange(n)
    for lo in range(0, draws, 250):
        m = min(250, draws - lo)
        new = rng.random((m, n)) < p
        new[:, 0] = True
        starts = rng.integers(n, size=(m, n))
        block_pos = np.maximum.accumulate(np.where(new, pos[None, :], 0), axis=1)
        block_start = np.take_along_axis(starts, block_pos, axis=1)
        idx = (block_start + (pos[None, :] - block_pos)) % n
        out[lo : lo + m] = x[idx].mean(axis=1)
    return out


def ci_mean(x: np.ndarray, rng: np.random.Generator) -> dict[str, float]:
    if len(x) < 30:
        return {"n": int(len(x)), "mean_ann": float("nan")}
    bs = stationary_bootstrap_mean(x, BOOT_DRAWS, BOOT_BLOCK, rng)
    lo, hi = np.percentile(bs, [2.5, 97.5])
    return {
        "n": int(len(x)),
        "mean_daily": float(x.mean()),
        "mean_ann": float(x.mean() * 252),
        "ci95_ann": [float(lo * 252), float(hi * 252)],
        "ci_excludes_0": bool(lo > 0 or hi < 0),
    }


def win(s: pd.Series, name: str) -> pd.Series:
    a = RECENT_START if name == "recent" else FULL_START
    return s.loc[s.index >= pd.Timestamp(a)].dropna()


def mets(r: pd.Series, rf: pd.Series, turn: pd.Series) -> dict[str, float]:
    m = base.metrics(r, rf, turn)
    return {
        "sessions": int(m.days),
        "ann_return": m.cagr,
        "sharpe": m.sharpe,
        "max_drawdown": m.max_dd,
        "ann_vol": m.vol,
        "turnover_ann": m.turnover_yr,
    }


def last_session() -> str:
    con = duckdb.connect()
    con.execute("SET threads=1")
    con.execute("SET memory_limit='300MB'")
    v = con.execute(
        "SELECT max(timestamp::DATE) FROM read_parquet('data/sip/daily/2026/*.parquet') "
        "WHERE symbol='SPY'"
    ).fetchone()[0]
    con.close()
    return str(v)


def main() -> int:
    end = last_session()
    base.WARMUP_START = "2015-01-02"
    base.HOLD_END = end
    mod = screen_batch.load_batch_module("h20260928_20_recent_opt")
    c2 = [c for c in screen_batch.candidates_from_module(mod) if c.id == "C2"][0]
    symbols = sorted(set(salvage.symbols()) | set(c2.universe) | {base.CASH, base.RF})
    close, open_ = base.load_panel(symbols)
    leg_open, leg_close = salvage.legs(close, open_)
    rf = (close[base.RF] / close[base.RF].shift(1) - 1.0).fillna(0.0)
    sig = salvage.dip_signal(close)
    print(f"panel {close.index[0].date()}..{close.index[-1].date()} symbols={close.shape[1]}")
    cc = close.pct_change(fill_method=None).abs()
    glitch = {c: float(cc[c].max()) for c in close.columns if cc[c].max() > 0.5}
    legs_big = {
        c: float(max(leg_open[c].abs().max(), leg_close[c].abs().max()))
        for c in close.columns
        if max(leg_open[c].abs().max(), leg_close[c].abs().max()) > 0.5
    }

    paths = sleeve_paths(close, leg_open, leg_close, sig)
    for k in SLEEVES:
        assert paths[k]["parity_vs_run_cell"] < 1e-9, (k, paths[k]["parity_vs_run_cell"])
    print({k: paths[k]["parity_vs_run_cell"] for k in SLEEVES})

    # C2 O-mode identity against the stored screen series (ends 2026-09-17, other panel start)
    stored = pd.read_parquet(
        ROOT
        / "reports/research/screens/h20260928_20_recent_opt/returns.sip-repaired-20261002.parquet"
    )["C2__o00__net10"]
    stored.index = pd.to_datetime(stored.index)

    rng = np.random.default_rng(BOOT_SEED)
    res: dict[str, Any] = {}
    series: dict[str, dict[str, pd.Series]] = {}
    for k in SLEEVES:
        items = paths[k]["items"]
        rO, tO, gap = blend_series(items, leg_open, leg_close, "O", COST_BPS)
        rC, tC, _ = blend_series(items, leg_open, leg_close, "C", COST_BPS)
        rC5, _, _ = blend_series(items, leg_open, leg_close, "C", 5.0)
        rO20, _, _ = blend_series(items, leg_open, leg_close, "O", 20.0)
        rC20, _, _ = blend_series(items, leg_open, leg_close, "C", 20.0)
        # identity: gross difference == sum (d eff) . lc, costs cancel at equal cost
        diff = rO - rC
        ident = float(np.max(np.abs(diff.to_numpy() - gap.to_numpy())))
        assert ident < 1e-12, (k, ident)
        series[k] = {"O": rO, "C": rC, "C5": rC5, "O20": rO20, "C20": rC20, "gap": gap, "tO": tO}
        res[k] = {"parity_vs_run_cell_max_abs": paths[k]["parity_vs_run_cell"], "windows": {}}
        if k == "C2":
            j = rO.index.intersection(stored.index)
            res[k]["identity_vs_stored_screen_max_abs"] = float(
                np.max(np.abs(rO.loc[j].to_numpy() - stored.loc[j].to_numpy()))
            )
            res[k]["identity_vs_stored_screen_n"] = int(len(j))
        # concentration of the difference (recent window): trade-day count, top days, per-offset
        gw = win(gap, "recent")
        top = gw.reindex(gw.abs().sort_values(ascending=False).index[:3])
        per_off = []
        for eff_o, cols_o in items:
            g = gross_open_minus_close(eff_o, cols_o, leg_close)
            per_off.append(float(win(g, "recent").mean() * 252))
        res[k]["recent_concentration"] = {
            "trade_days_any_offset": int((gw != 0).sum()),
            "top3_abs_days": {str(i.date()): float(v) for i, v in top.items()},
            "mean_ann_without_top1_day": float(gw.drop(top.index[0]).mean() * 252),
            "mean_ann_without_top3_days": float(gw.drop(top.index).mean() * 252),
            "per_offset_mean_ann": per_off,
        }
        # live-rule offset 0 only (reference)
        r0O, t0O = t23.simulate_effective(items[0][0], items[0][1], leg_open, leg_close, COST_BPS)
        r0C, _ = sim_close(items[0][0], items[0][1], leg_open, leg_close, COST_BPS)
        for wname in ("recent", "full"):
            rOw, rCw, tw = win(rO, wname), win(rC, wname), win(tO, wname)
            d = (rOw - rCw).dropna()
            years = len(d) / 252.0
            ann_turn = float(tw.sum() / years)
            gross_diff_ann = float(win(gap, wname).mean() * 252)
            res[k]["windows"][wname] = {
                "span": [str(rOw.index[0].date()), str(rOw.index[-1].date())],
                "O": mets(rOw, rf, tw),
                "C": mets(rCw, rf, tw),
                "O_minus_C_daily": ci_mean(d.to_numpy(), rng),
                "sharpe_diff_O_minus_C": mets(rOw, rf, tw)["sharpe"] - mets(rCw, rf, tw)["sharpe"],
                "ann_return_diff_O_minus_C": mets(rOw, rf, tw)["ann_return"]
                - mets(rCw, rf, tw)["ann_return"],
                "gross_gap_ann_open_to_close_on_weight_change": gross_diff_ann,
                "cost_diff_ann": float(
                    (win(rO - rC, wname).mean() * 252) - gross_diff_ann
                ),  # ~0 by identity
                "breakeven_extra_cost_saving_bp_per_side_for_C": (
                    gross_diff_ann / ann_turn * 1e4 if ann_turn > 0 else float("nan")
                ),
                "sensitivity_C_at_5bp_side": mets(win(rC5, wname), rf, tw),
                "sensitivity_both_at_20bp_side": {
                    "O": mets(win(rO20, wname), rf, tw),
                    "C": mets(win(rC20, wname), rf, tw),
                },
                "live_rule_offset0": {
                    "O": mets(win(r0O, wname), rf, win(t0O, wname)),
                    "C": mets(win(r0C, wname), rf, win(t0O, wname)),
                    "O_minus_C_daily": ci_mean(
                        (win(r0O, wname) - win(r0C, wname)).dropna().to_numpy(), rng
                    ),
                },
            }
        # by phase
        ph: dict[str, Any] = {}
        dfull = (rO - rC).dropna()
        for pid, a, b, lab in PHASES:
            seg = dfull.loc[pd.Timestamp(a) : pd.Timestamp(b)]
            if len(seg) == 0:
                continue
            ph[pid] = {
                "label": lab,
                "span": [str(seg.index[0].date()), str(seg.index[-1].date())],
                "n": int(len(seg)),
                "O_minus_C_mean_ann": float(seg.mean() * 252),
                "O_cum": float((1 + rO.loc[seg.index]).prod() - 1),
                "C_cum": float((1 + rC.loc[seg.index]).prod() - 1),
            }
        res[k]["phases"] = ph
        lab_out: dict[str, Any] = {}
        for grp, prefix in (("recent_P", "P"), ("hist_H", "H")):
            for lab in ("advance", "correction", "rebound"):
                parts = [
                    dfull.loc[pd.Timestamp(a) : pd.Timestamp(b)]
                    for pid, a, b, l2 in PHASES
                    if pid.startswith(prefix) and l2 == lab
                ]
                x = pd.concat(parts).to_numpy()
                lab_out[f"{grp}:{lab}"] = ci_mean(x, rng)
        res[k]["by_phase_label"] = lab_out
        print(
            k, {w: res[k]["windows"][w]["O_minus_C_daily"]["mean_ann"] for w in ("recent", "full")}
        )

    # pilot mix (S3 + C2, plan v2 D7.1 weights), daily fixed weights, for reference
    mix = {}
    for mode in ("O", "C"):
        mix[mode] = 0.642 * series["S3"][mode] + 0.358 * series["C2"][mode]
    mixd = {}
    for wname in ("recent", "full"):
        d = (win(mix["O"], wname) - win(mix["C"], wname)).dropna()
        mixd[wname] = {
            "O": mets(win(mix["O"], wname), rf, win(series["S3"]["tO"], wname)),
            "C": mets(win(mix["C"], wname), rf, win(series["S3"]["tO"], wname)),
            "O_minus_C_daily": ci_mean(d.to_numpy(), rng),
        }
    mixd["note"] = "0.642*S3 + 0.358*C2 daily fixed weights; turnover column is S3's, ignore it"

    out = {
        "task": "T-20261005-41",
        "code": "R1005-T41",
        "config": "config/evaluation-standard-v2.json",
        "panel": [str(close.index[0].date()), str(close.index[-1].date())],
        "windows": {"recent": f"{RECENT_START}..panel end", "full": f"{FULL_START}..panel end"},
        "cost": "10 bp per side both modes (no open/close split measured for ETFs; see report)",
        "bootstrap": {"draws": BOOT_DRAWS, "mean_block": BOOT_BLOCK, "seed": BOOT_SEED},
        "data_checks": {
            "close_to_close_abs_gt_50pct": glitch,
            "leg_abs_gt_50pct": legs_big,
        },
        "results": res,
        "pilot_mix_S3_C2": mixd,
    }
    (OUT / "results.json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print("written", OUT / "results.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
