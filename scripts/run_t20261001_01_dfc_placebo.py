"""T-20261001-01: placebo, engine parity, diagnostics and mechanical verdict for
the dash-for-cash settlement window (iteration t20261001_01_dash_for_cash_settlement).

Reads `reports/research/screens/t20261001_01_dash_for_cash/leaderboard.json`
(produced by `scripts/screen_batch.py`), recomputes the five candidates through
the same lane engine (`screen_lane.candidate_returns_for_offset` +
`evaluate_offset_window`), runs 100 random-entry-day placebo seeds per candidate
(`numpy.random.default_rng(20261001 + seed)`), the preregistered diagnostics, and
writes `results.json` and `report.md` next to the preregistration. Rules:
`hypotheses.md` ("预注册全文"). Nothing here changes a preregistered number.

Run: scripts/run_capped.sh --mem 1.5G -- uv run python scripts/run_t20261001_01_dfc_placebo.py
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "screen_batches"))

import screen_batch as sb  # noqa: E402
import screen_lane as lane  # noqa: E402
import t20261001_01_dash_for_cash as dfc  # noqa: E402

ITER = "t20261001_01_dash_for_cash_settlement"
ITER_DIR = ROOT / "reports" / "research" / "iterations" / ITER
SCREEN_DIR = ROOT / "reports" / "research" / "screens" / "t20261001_01_dash_for_cash"
OLD_SCREEN = (
    ROOT / "reports" / "research" / "screens" / "h20260928_20_recent_opt" / "returns.parquet"
)
OLD_RESULTS = (
    ROOT / "reports" / "research" / "iterations" / "h20260928_20_recent_regime_opt" / "results.json"
)

N_SEEDS = 100
BASE_SEED = 20261001
PARITY_TOL = 0.01
WINDOW_NAMES = ("select", "anchor", "stress", "holdout")
PLACEBO_WINDOWS = ("select", "anchor", "stress")
DFC_IDS = ("DFC_U", "DFC_C", "DFC_U_FIX4", "DFC_C_FIX4")
JUDGED_IDS = ("DFC_U", "DFC_C")
CONDITIONAL = {"DFC_U": False, "DFC_C": True, "DFC_U_FIX4": False, "DFC_C_FIX4": True}
ERA_ALIGNED = {"DFC_U": True, "DFC_C": True, "DFC_U_FIX4": False, "DFC_C_FIX4": False}
PROFILE_POSITIONS = list(range(-12, 9))
PROFILE_WINDOWS = ("stress", "select", "anchor")
NW_LAGS = 3


# ---------------------------------------------------------------- pure helpers


def clean(obj):
    if isinstance(obj, dict):
        return {str(k): clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean(v) for v in obj]
    if isinstance(obj, (float, np.floating)):
        return float(obj) if math.isfinite(float(obj)) else None
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    return obj


def hold_series(
    index: pd.DatetimeIndex,
    close: np.ndarray,
    entry_pos: np.ndarray,
    hold_len: np.ndarray,
    conditional: bool,
) -> np.ndarray:
    """Boolean "position held after close d" for one placebo path. A month with
    entry day e holds for d in [e, e + L); overlapping months merge. Conditional
    months need close(e-6) -> close(e) < 0."""
    hold = np.zeros(len(index), dtype=bool)
    for e, length in zip(entry_pos, hold_len, strict=True):
        if conditional:
            if e - dfc.PRE_WINDOW_SESSIONS < 0:
                continue
            if not (close[e] / close[e - dfc.PRE_WINDOW_SESSIONS] - 1.0 < 0.0):
                continue
        hold[e : e + int(length)] = True
    return hold


def placebo_candidate(id_: str, index: pd.DatetimeIndex, hold: np.ndarray) -> lane.ScreenCandidate:
    prev = np.concatenate([[False], hold[:-1]])
    change_dates = [index[i] for i in np.flatnonzero(hold != prev)]
    hold_by_date = {index[i]: bool(hold[i]) for i in range(len(index))}

    def fn(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
        return {"SPY": 1.0} if hold_by_date.get(asof, False) else {}

    return lane.ScreenCandidate(
        id=id_,
        name=id_,
        source_card="placebo",
        universe=("SPY",),
        freq="D",
        weights_fn=fn,
        signal_dates_fn=lambda _idx, d=change_dates: list(d),
    )


def window_sharpes(
    ret: pd.Series, turn: pd.Series, rf: pd.Series, first_valid: pd.Timestamp
) -> dict[str, float]:
    out = {}
    for w in WINDOW_NAMES:
        m, _ = lane.evaluate_offset_window(ret, turn, ret, turn, rf, lane.WINDOWS[w], first_valid)
        out[w] = m["net10"]["sharpe"]
    return out


def hac_dummy_t(y: np.ndarray, d: np.ndarray, lags: int = NW_LAGS) -> tuple[float, float]:
    """OLS y = a + beta*d with Newey-West (Bartlett) HAC; returns (beta, t_beta)."""
    n = len(y)
    x = np.column_stack([np.ones(n), d.astype(float)])
    xtx_inv = np.linalg.inv(x.T @ x)
    beta = xtx_inv @ (x.T @ y)
    u = y - x @ beta
    xu = x * u[:, None]
    s = xu.T @ xu
    for lag in range(1, lags + 1):
        g = xu[lag:].T @ xu[:-lag]
        s += (1.0 - lag / (lags + 1.0)) * (g + g.T)
    cov = xtx_inv @ s @ xtx_inv
    return float(beta[1]), float(beta[1] / math.sqrt(cov[1, 1]))


# ----------------------------------------------------------------- diagnostics


def day_profile(close: pd.Series, schedule: list[dict]) -> dict:
    ret_bp = (close / close.shift(1) - 1.0) * 1e4
    idx = close.index
    out: dict = {}
    for seg in ("pre", "post"):
        out[seg] = {}
        for w in PROFILE_WINDOWS:
            a, b = (pd.Timestamp(x) for x in lane.WINDOWS[w])
            out[seg][w] = {}
            for k in PROFILE_POSITIONS:
                vals = []
                for m in schedule:
                    is_post = m["tau"] >= dfc.REFORM_DATE
                    if (seg == "post") != is_post:
                        continue
                    pos = idx.get_loc(m["tau"]) + k
                    if pos < 1 or pos >= len(idx):
                        continue
                    day = idx[pos]
                    if a <= day <= b and np.isfinite(ret_bp.iloc[pos]):
                        vals.append(float(ret_bp.iloc[pos]))
                n = len(vals)
                arr = np.array(vals)
                out[seg][w][str(k)] = {
                    "mean_bp": float(arr.mean()) if n else None,
                    "se_bp": float(arr.std(ddof=1) / math.sqrt(n)) if n > 1 else None,
                    "n": n,
                }
    return out


def pre_post_corr(close: pd.Series, schedule: list[dict]) -> dict:
    out = {}
    for seg in ("pre", "post"):
        xs, ys = [], []
        for m in schedule:
            if (seg == "post") != (m["tau"] >= dfc.REFORM_DATE) or m["exit"] is None:
                continue
            bp = m["b_pos"]
            if bp - dfc.PRE_WINDOW_SESSIONS < 0:
                continue
            xs.append(close.iloc[bp] / close.iloc[bp - dfc.PRE_WINDOW_SESSIONS] - 1.0)
            ys.append(close.loc[m["exit"]] / close.iloc[bp] - 1.0)
        n = len(xs)
        corr = float(np.corrcoef(xs, ys)[0, 1]) if n > 2 else None
        out[seg] = {"corr": corr, "n_months": n}
    return out


def reform_shift(close: pd.Series, schedule: list[dict]) -> dict:
    ret_bp = (close / close.shift(1) - 1.0) * 1e4
    idx = close.index
    rows = []
    for m in schedule:
        tau = m["tau"]
        if tau.year == 2024 and tau.month == 5:
            continue
        p = idx.get_loc(tau)
        if p - 4 < 1:
            continue
        diff = float(ret_bp.iloc[p - 3] - ret_bp.iloc[p - 4])
        rows.append((tau, diff))
    y = np.array([r[1] for r in rows])
    d = np.array([r[0] >= pd.Timestamp("2024-06-01") for r in rows])
    beta, t = hac_dummy_t(y, d)
    return {
        "post_minus_pre_bp": beta,
        "t_nw": t,
        "n_pre": int((~d).sum()),
        "n_post": int(d.sum()),
        "mean_pre_bp": float(y[~d].mean()),
        "mean_post_bp": float(y[d].mean()),
        "nw_lags": NW_LAGS,
        "note": "OLS of month diff (tau-3 minus tau-4 close-to-close, bp) on post dummy, "
        "Bartlett HAC lag 3; 2024-05 excluded; pre = all months before 2024-05",
    }


def blend_sharpes(parts: dict[str, pd.Series], weights: dict[str, float], rf: pd.Series) -> dict:
    idx = None
    for s in parts.values():
        idx = s.index if idx is None else idx.intersection(s.index)
    ret = sum(w * parts[k].reindex(idx) for k, w in weights.items())
    zero = pd.Series(0.0, index=idx)
    out = {}
    for w in WINDOW_NAMES:
        a, b = (pd.Timestamp(x) for x in lane.WINDOWS[w])
        mask = (idx >= a) & (idx <= b)
        out[w] = lane.base.metrics(ret.loc[mask], rf, zero.loc[mask]).sharpe
    return out


# ------------------------------------------------------------------------ main


def main() -> None:
    module = sb.load_batch_module("t20261001_01_dash_for_cash")
    candidates = sb.candidates_from_module(module)
    by_id = {c.id: c for c in candidates}
    leaderboard_path = SCREEN_DIR / "leaderboard.json"
    lb = json.loads(leaderboard_path.read_text(encoding="utf-8"))
    lb_by_id = {c["id"]: c for c in lb["candidates"]}

    close, _open, leg_open, leg_close, rf = lane.load_batch_panel(
        candidates, getattr(module, "extend_panel", None)
    )
    index = close.index
    spy = close["SPY"]
    spy_np = spy.to_numpy(dtype=float)

    # ---- engine recompute + parity
    first_valid: dict[str, pd.Timestamp] = {}
    engine_sharpes: dict[str, dict[str, float]] = {}
    engine_diffs: dict[str, dict[str, float]] = {}
    for cid, cand in by_id.items():
        ret10, turn10 = lane.candidate_returns_for_offset(
            close, leg_open, leg_close, cand, 0, lane.COST_BPS_PRIMARY
        )
        ret20, turn20 = lane.candidate_returns_for_offset(
            close, leg_open, leg_close, cand, 0, lane.COST_BPS_STRESS
        )
        fv = lane.first_valid_signal_date(close, cand)
        first_valid[cid] = fv
        engine_sharpes[cid] = {}
        engine_diffs[cid] = {}
        for w in WINDOW_NAMES:
            m, _ = lane.evaluate_offset_window(
                ret10, turn10, ret20, turn20, rf, lane.WINDOWS[w], fv
            )
            lbw = lb_by_id[cid]["per_window"][w]["offsets"]["0"]
            engine_sharpes[cid][w] = m["net10"]["sharpe"]
            engine_diffs[cid][f"{w}_10bp"] = abs(m["net10"]["sharpe"] - lbw["net10"]["sharpe"])
            engine_diffs[cid][f"{w}_20bp"] = abs(m["net20"]["sharpe"] - lbw["net20"]["sharpe"])
    engine_ok = all(v <= PARITY_TOL for d in engine_diffs.values() for v in d.values())

    old = json.loads(OLD_RESULTS.read_text(encoding="utf-8"))["candidates"]["E0"]
    e0_target = {
        "select": old["select_10bp_sharpe"],
        "anchor": old["anchor_sharpe"],
        "stress": old["stress_sharpe"],
        "holdout": old["holdout_2026_sharpe"],
    }
    e0_got = {w: lb_by_id["E0_REF"]["judged"][w]["sharpe"] for w in WINDOW_NAMES}
    e0_parity = {w: e0_got[w] for w in WINDOW_NAMES}
    e0_parity["diff"] = {w: abs(e0_got[w] - e0_target[w]) for w in WINDOW_NAMES}
    e0_parity["target"] = e0_target
    e0_parity["ok"] = all(v <= PARITY_TOL for v in e0_parity["diff"].values())
    parity = {
        "e0_ref": e0_parity,
        "engine": {"diffs": engine_diffs, "tol": PARITY_TOL, "ok": engine_ok},
        "all_ok": bool(e0_parity["ok"] and engine_ok),
    }
    print("parity", parity["all_ok"], flush=True)

    # ---- placebo
    month_pos = [
        np.flatnonzero((index.year == y) & (index.month == mo))
        for y, mo in sorted({(d.year, d.month) for d in index})
    ]
    month_len = {}
    for variant_era in (True, False):
        lens = []
        for pos in month_pos:
            month_end_date = index[pos[-1]] + pd.offsets.MonthEnd(0)
            lens.append(dfc.holding_sessions(month_end_date, variant_era))
        month_len[variant_era] = np.array(lens)
    placebo_sharpes: dict[str, dict[str, list[float]]] = {
        cid: {w: [] for w in WINDOW_NAMES} for cid in DFC_IDS
    }
    for seed in range(N_SEEDS):
        rng = np.random.default_rng(BASE_SEED + seed)
        u = rng.random(len(month_pos))
        entry = np.array([int(pos[int(x * len(pos))]) for pos, x in zip(month_pos, u, strict=True)])
        for cid in DFC_IDS:
            hold = hold_series(index, spy_np, entry, month_len[ERA_ALIGNED[cid]], CONDITIONAL[cid])
            pc = placebo_candidate(f"PLC_{cid}_{seed}", index, hold)
            ret10, turn10 = lane.candidate_returns_for_offset(
                close, leg_open, leg_close, pc, 0, lane.COST_BPS_PRIMARY
            )
            sh = window_sharpes(ret10, turn10, rf, first_valid[cid])
            for w in WINDOW_NAMES:
                placebo_sharpes[cid][w].append(sh[w])
        if seed % 10 == 9:
            print(f"placebo seed {seed + 1}/{N_SEEDS}", flush=True)

    def placebo_stats(cid: str, w: str) -> dict:
        seeds = np.array(placebo_sharpes[cid][w], dtype=float)
        seeds = seeds[np.isfinite(seeds)]
        real = lb_by_id[cid]["judged"][w]["sharpe"]
        return {
            "beat": float((real > seeds).mean()) if len(seeds) else None,
            "p50": float(np.percentile(seeds, 50)) if len(seeds) else None,
            "p90": float(np.percentile(seeds, 90)) if len(seeds) else None,
            "n_seeds": int(len(seeds)),
        }

    # ---- candidates block
    cands_out: dict[str, dict] = {}
    for cid in DFC_IDS:
        r = lb_by_id[cid]
        pw = r["per_window"]
        weights, _ = lane.weights_frame(close, by_id[cid], 0)
        a, b = (pd.Timestamp(x) for x in lane.WINDOWS["anchor"])
        wmask = (weights.index >= a) & (weights.index <= b)
        cands_out[cid] = {
            "select_10bp": r["judged"]["select"]["sharpe"],
            "select_20bp": pw["select"]["offsets"]["0"]["net20"]["sharpe"],
            "anchor_10bp": r["judged"]["anchor"]["sharpe"],
            "stress_10bp": r["judged"]["stress"]["sharpe"],
            "holdout_2026_10bp": r["judged"]["holdout"]["sharpe"],
            "anchor_cagr_20bp": pw["anchor"]["offsets"]["0"]["net20"]["cagr"],
            "stress_cagr_20bp": pw["stress"]["offsets"]["0"]["net20"]["cagr"],
            "anchor_20bp_sharpe": pw["anchor"]["offsets"]["0"]["net20"]["sharpe"],
            "stress_20bp_sharpe": pw["stress"]["offsets"]["0"]["net20"]["sharpe"],
            "k2_anchor": r["diversifier"]["anchor"]["judged_edge"],
            "k2_stress": r["diversifier"]["stress"]["judged_edge"],
            "dsr_anchor": r.get("dsr_anchor"),
            "placebo": {w: placebo_stats(cid, w) for w in PLACEBO_WINDOWS},
            "turnover_yr": r["judged"]["anchor"]["turnover_yr"],
            "days_in_market_share": float((weights.loc[wmask, "SPY"] > 0).mean()),
            "first_valid_signal_date": str(first_valid[cid].date()),
        }
    e0r = lb_by_id["E0_REF"]
    e0_ref_out = {
        "select_10bp": e0r["judged"]["select"]["sharpe"],
        "select_20bp": e0r["per_window"]["select"]["offsets"]["0"]["net20"]["sharpe"],
        "anchor_10bp": e0r["judged"]["anchor"]["sharpe"],
        "stress_10bp": e0r["judged"]["stress"]["sharpe"],
        "holdout_2026_10bp": e0r["judged"]["holdout"]["sharpe"],
        "k2_anchor": e0r["diversifier"]["anchor"]["judged_edge"],
        "k2_stress": e0r["diversifier"]["stress"]["judged_edge"],
    }

    # ---- decisions
    e0_select20 = old["select_20bp_sharpe"]
    thr = {
        "a_select_10bp": old["select_10bp_sharpe"] + 0.10,
        "b_holdout_2026": old["holdout_2026_sharpe"] - 0.10,
        "c_select_20bp": e0_select20 + 0.10,
        "d_stress": old["stress_sharpe"],
    }
    replacement, k1, k2 = {}, {}, {}
    for cid in DFC_IDS:
        c = cands_out[cid]
        pl = c["placebo"]
        k1_placebo_ok = bool(
            (pl["anchor"]["beat"] or 0) >= 0.90 and (pl["stress"]["beat"] or 0) >= 0.90
        )
        k1[cid] = {
            "anchor_ge_1.19": bool(c["anchor_10bp"] >= 1.19),
            "stress_ge_0.65": bool(c["stress_10bp"] >= 0.65),
            "cagr20_pos": bool(c["anchor_cagr_20bp"] > 0 and c["stress_cagr_20bp"] > 0),
            "pass": bool(
                c["anchor_10bp"] >= 1.19
                and c["stress_10bp"] >= 0.65
                and c["anchor_cagr_20bp"] > 0
                and c["stress_cagr_20bp"] > 0
            ),
            "placebo_ok": k1_placebo_ok,
        }
        k2[cid] = {
            "pass": bool(c["k2_anchor"] >= 0.05 and c["k2_stress"] >= 0.05),
            "placebo_ok": k1_placebo_ok,
        }
        a_ = bool(c["select_10bp"] >= thr["a_select_10bp"])
        b_ = bool(c["holdout_2026_10bp"] >= thr["b_holdout_2026"])
        c_ = bool(c["select_20bp"] >= thr["c_select_20bp"])
        d_ = bool(c["stress_10bp"] >= thr["d_stress"])
        pok = bool((pl["select"]["beat"] or 0) >= 0.90 and (pl["stress"]["beat"] or 0) >= 0.90)
        replacement[cid] = {
            "a": a_,
            "b": b_,
            "c": c_,
            "d": d_,
            "placebo_ok": pok,
            "pass": bool(a_ and b_ and c_ and d_ and pok),
            "thresholds": thr,
        }
    if not parity["all_ok"]:
        verdict = "parity_failed"
    elif any(replacement[c]["pass"] for c in JUDGED_IDS):
        verdict = "replace_proposal"
    elif any((k1[c]["pass"] or k2[c]["pass"]) and k1[c]["placebo_ok"] for c in JUDGED_IDS):
        verdict = "keep"
    elif any(
        cands_out[c]["anchor_10bp"] >= 1.19
        and cands_out[c]["stress_10bp"] < 0.65
        and (cands_out[c]["placebo"]["anchor"]["beat"] or 0) >= 0.90
        for c in JUDGED_IDS
    ):
        verdict = "watch_recent"
    else:
        verdict = "refuted"

    # ---- diagnostics
    schedule = dfc.month_schedule(index, True)
    diagnostics = {
        "day_profile": day_profile(spy, schedule),
        "pre_post_corr": pre_post_corr(spy, schedule),
        "reform_shift": reform_shift(spy, schedule),
    }
    new_ret = pd.read_parquet(SCREEN_DIR / "returns.parquet")
    old_ret = pd.read_parquet(OLD_SCREEN)
    s0 = old_ret["S0__o00__net10"]
    blend = {}
    for key, ser in (
        ("DFC_U", new_ret["DFC_U__o00__net10"]),
        ("DFC_C", new_ret["DFC_C__o00__net10"]),
        ("E0", old_ret["E0__o00__net10"]),
    ):
        blend[key] = blend_sharpes({"x": ser, "s0": s0}, {"x": 0.5, "s0": 0.5}, rf)
    diagnostics["c2_blend"] = blend
    diagnostics["c2_actual"] = blend_sharpes({"c2": old_ret["C2__o00__net10"]}, {"c2": 1.0}, rf)
    diagnostics["c2_blend_note"] = (
        "daily 50/50 approximation; zero turnover passed to metrics (Sharpe only); "
        f"parquet ends {old_ret.index[-1].date()}"
    )

    results = {
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "iteration": ITER,
        "leaderboard_path": str(leaderboard_path.relative_to(ROOT)),
        "n_seeds": N_SEEDS,
        "base_seed": BASE_SEED,
        "parity": parity,
        "candidates": cands_out,
        "e0_ref": e0_ref_out,
        "replacement": {k: v for k, v in replacement.items()},
        "k1": k1,
        "k2": k2,
        "diagnostics": diagnostics,
        "verdict": verdict,
        "verdict_rule": "preregistered hypotheses.md 判定; FIX4 controls excluded from verdict",
        "n_trials_batch": lb["n_trials"],
        "n_trials_family_cumulative": 13,
    }
    (ITER_DIR / "results.json").write_text(
        json.dumps(clean(results), indent=2, allow_nan=False), encoding="utf-8"
    )
    (ITER_DIR / "report.md").write_text(render_report(clean(results)), encoding="utf-8")
    print("verdict", verdict, flush=True)


def fmt(x, nd: int = 3) -> str:
    return "n/a" if x is None else f"{x:.{nd}f}"


def render_report(r: dict) -> str:
    lines = [
        f"# {r['iteration']}: results (generated {r['generated_at']})",
        "",
        f"verdict (mechanical, preregistered rule): **{r['verdict']}**; "
        f"parity all_ok = {r['parity']['all_ok']}; leaderboard `{r['leaderboard_path']}`.",
        "",
        "| id | select 10bp | select 20bp | anchor | stress | 2026 | K2 anchor | K2 stress "
        "| beat select | beat anchor | beat stress | repl a/b/c/d | repl pass |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for cid, c in r["candidates"].items():
        rep = r["replacement"][cid]
        pl = c["placebo"]
        lines.append(
            f"| {cid} | {fmt(c['select_10bp'])} | {fmt(c['select_20bp'])} | {fmt(c['anchor_10bp'])}"
            f" | {fmt(c['stress_10bp'])} | {fmt(c['holdout_2026_10bp'])} | {fmt(c['k2_anchor'])}"
            f" | {fmt(c['k2_stress'])} | {fmt(pl['select']['beat'], 2)}"
            f" | {fmt(pl['anchor']['beat'], 2)} | {fmt(pl['stress']['beat'], 2)}"
            f" | {int(rep['a'])}{int(rep['b'])}{int(rep['c'])}{int(rep['d'])}"
            f" | {rep['pass']} |"
        )
    e = r["e0_ref"]
    lines.append(
        f"| E0_REF | {fmt(e['select_10bp'])} | {fmt(e['select_20bp'])} | {fmt(e['anchor_10bp'])}"
        f" | {fmt(e['stress_10bp'])} | {fmt(e['holdout_2026_10bp'])} | {fmt(e['k2_anchor'])}"
        f" | {fmt(e['k2_stress'])} | - | - | - | - | - |"
    )
    lines += [
        "",
        "Day-position profile, SPY close-to-close mean (bp), era-aligned tau; n in brackets.",
        "",
    ]
    prof = r["diagnostics"]["day_profile"]
    for seg in ("pre", "post"):
        for w in ("stress", "anchor"):
            cells = prof[seg][w]
            head = "| k | " + " | ".join(str(k) for k in dfc_positions()) + " |"
            sep = "|---|" + "---|" * len(dfc_positions())
            row = (
                f"| {seg}/{w} | "
                + " | ".join(
                    f"{fmt(cells[str(k)]['mean_bp'], 1)} [{cells[str(k)]['n']}]"
                    for k in dfc_positions()
                )
                + " |"
            )
            if (seg, w) == ("pre", "stress"):
                lines += [head, sep]
            lines.append(row)
    d = r["diagnostics"]
    lines += [
        "",
        f"pre/post-window correlation: {json.dumps(d['pre_post_corr'])}",
        f"reform shift: {json.dumps(d['reform_shift'])}",
        f"C2 blend Sharpes: {json.dumps(d['c2_blend'])}; actual C2: {json.dumps(d['c2_actual'])}",
        "",
    ]
    return "\n".join(lines)


def dfc_positions() -> list[int]:
    return PROFILE_POSITIONS


if __name__ == "__main__":
    main()
