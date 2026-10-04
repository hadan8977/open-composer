# ruff: noqa: E501
"""Book v1.3 candidate: cost-aware trading rules on the v1.2 primary book (t20261004_book_v13_tc).

Contract: ``reports/research/iterations/t20261004_book_v13_tc/hypotheses.md`` (frozen before any rule was run).

    scripts/run_capped.sh --mem 1.8G -- uv run python scripts/book_v13_trading_rules.py --stage identity
    scripts/run_capped.sh --mem 1.8G -- uv run python scripts/book_v13_trading_rules.py --stage rules --variant M0_U3000
    uv run python scripts/book_v13_trading_rules.py --stage evaluate
    scripts/run_capped.sh --mem 1.8G -- uv run python scripts/book_v13_trading_rules.py --stage diag

Daily series go to ``data/research/book_v13/`` (outside the hash-guarded research snapshot).  A pass with
rule ``B0`` is the ``strategy_pass`` loop of ``scripts/book_v12_account.py`` with the weights and the hedge
taken from ``apply_rule``; several rules share one decision loop (same inputs, one state per rule).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from open_composer.research.equity_book import book_v12 as bv  # noqa: E402
from open_composer.research.equity_book.trading_rules import RULES, apply_rule  # noqa: E402
from scripts import book_v12_account as acct  # noqa: E402
from scripts import realism_ladder_book_ls as T25  # noqa: E402

OUT_DATA = ROOT / "data/research/book_v13"
OUT_REPORT = ROOT / "reports/research/iterations/t20261004_book_v13_tc"
OFFSETS = T25.OFFSETS
START = T25.START
IDENTITY_TOL = 1e-12
WINDOWS = {
    "recent": ("2024-01-08", "2026-09-15"),
    "stress": ("2017-10-02", "2023-08-31"),
    "full": ("2017-10-02", "2026-09-15"),
    "A": ("2024-01-08", "2026-06-30"),
    "B": ("2026-07-01", "2026-09-15"),
}
PRIMARY = "M0_U3000"
CANDIDATES = ("P2", "P3", "P2V", "N25", "N50")
EXTRA_COLS = ("gross_exposure", "drift", "tgt_change", "flip", "refresh")


# ---------------------------------------------------------------------------
# strategy pass: B0 loop of book_v12_account.strategy_pass, weights/hedge from apply_rule
# ---------------------------------------------------------------------------
def dense_eligible(ctx: T25.Context, di: acct.DecisionInputs) -> np.ndarray:
    px = ctx.px
    elig = np.zeros(px.N, dtype=bool)
    idx = px.symbols.get_indexer(di.eligible.index)
    ok = idx >= 0
    elig[idx[ok]] = di.eligible.to_numpy(bool)[ok]
    return elig


def dense_beta(ctx: T25.Context, di: acct.DecisionInputs) -> np.ndarray:
    """EWMA beta vector exactly as ``book_v12.tranche_target`` builds ``b_ewma``."""
    px = ctx.px
    names = di.score.dropna().index
    idx = px.symbols.get_indexer(names)
    keep = idx >= 0
    b = np.ones(px.N)
    ev = di.beta.reindex(names).fillna(1.0).clip(-1.0, 4.0)
    b[idx[keep]] = ev.to_numpy()[keep]
    return b


def rules_pass(
    ctx: T25.Context,
    variant: str,
    offset: int,
    rules: tuple[str, ...],
    limit: int | None = None,
) -> dict[str, pd.DataFrame]:
    px = ctx.px
    flag = acct.variant_flag(variant)
    src = acct.make_source(ctx, variant)
    first = int(px.dates.searchsorted(pd.Timestamp(START)))
    last_label = px.T - 3
    dec = T25.decision_positions(px.T, first, last_label, T25.WEEK, offset)
    st = {r: {"w": np.zeros(px.N), "h": 0.0, "x_prev": np.zeros(px.N), "rows": []} for r in rules}
    s_prev = 1.0
    w_tgt_prev: np.ndarray | None = None
    for i, p in enumerate(dec):
        if limit is not None and i >= limit:
            break
        nxt = dec[i + 1] if i + 1 < len(dec) else last_label + 1
        length = nxt - p
        di = acct.decision_inputs(ctx, src, flag, p)
        if di is None:
            continue
        tt = acct.tranche_from_inputs(ctx, di)
        elig = dense_eligible(ctx, di)
        b_ewma = dense_beta(ctx, di)
        ret, spy_r = px.returns("close", p, length)
        tgt_change = 0.0 if w_tgt_prev is None else float(np.abs(tt.w - w_tgt_prev).sum())
        flip = 0.0 if w_tgt_prev is None else float(tt.vscale != s_prev)
        for r in rules:
            s = st[r]
            x_new = apply_rule(r, s["w"], tt.w, tt.w_unit, tt.vscale, s_prev, elig)
            h_new = float(-np.nansum(x_new * b_ewma))
            blk = bv.hold_block(x_new, ret, spy_r, h0=h_new)
            d_w = x_new - s["w"]
            d_h = h_new - s["h"]
            turnover = float(np.abs(d_w).sum())
            cost = T25.real_cost(ctx, di.t, px.symbols, d_w, d_h, di.attrs)
            n = len(blk["pnl"])
            cost_v = np.zeros(n)
            cost_v[0] = cost
            to_v = np.zeros(n)
            to_v[0] = turnover
            drift_v = np.zeros(n)
            drift_v[0] = float(np.abs(s["w"] - s["x_prev"]).sum())
            tc_v = np.zeros(n)
            tc_v[0] = tgt_change
            flip_v = np.zeros(n)
            flip_v[0] = flip
            ref_v = np.zeros(n)
            ref_v[0] = 1.0
            bor = blk["short_notional"] * (bv.BORROW_BP_YEAR_T25 / 1e4 / 252.0)
            s["rows"].append(
                pd.DataFrame(
                    {
                        "gross": blk["pnl"],
                        "cost": cost_v,
                        "borrow": bor,
                        "turnover": to_v,
                        "spy": spy_r,
                        "hedge_size": np.full(n, h_new),
                        "vix_scale": np.full(n, tt.vscale),
                        "gross_exposure": np.full(n, float(np.abs(x_new).sum())),
                        "drift": drift_v,
                        "tgt_change": tc_v,
                        "flip": flip_v,
                        "refresh": ref_v,
                    },
                    index=px.dates[p : p + n],
                )
            )
            s["x_prev"] = x_new
            s["w"], s["h"] = blk["w_end"], blk["h_end"]
        s_prev = tt.vscale
        w_tgt_prev = tt.w
    out: dict[str, pd.DataFrame] = {}
    for r in rules:
        df = pd.concat(st[r]["rows"])
        df["net"] = df["gross"] - df["cost"] - df["borrow"]
        cols = ["gross", "cost", "borrow", "turnover", "spy", "hedge_size", "vix_scale", "net"]
        out[r] = df[cols + list(EXTRA_COLS)]
    return out


# ---------------------------------------------------------------------------
# stage identity
# ---------------------------------------------------------------------------
def run_identity() -> dict:
    ctx = T25.Context()
    res: dict = {"tolerance": IDENTITY_TOL, "cases": {}, "pass": True, "max_abs_diff": 0.0}
    for o in (0, 3):
        saved = pd.read_parquet(T25.RAW / f"R6_{PRIMARY}_o{o}.parquet")
        mine = rules_pass(ctx, PRIMARY, o, ("B0",))["B0"]
        same_index = bool(mine.index.equals(saved.index))
        diffs = {
            c: float((mine[c] - saved[c]).abs().max()) if same_index else float("nan")
            for c in ("gross", "cost", "borrow", "net")
        }
        other = (
            {
                c: float((mine[c] - saved[c]).abs().max())
                for c in ("turnover", "spy", "hedge_size", "vix_scale")
            }
            if same_index
            else {}
        )
        worst = max(diffs.values())
        ok = bool(math.isfinite(worst) and worst <= IDENTITY_TOL)
        res["cases"][f"{PRIMARY}_o{o}"] = {
            "rows_mine": len(mine),
            "rows_saved": len(saved),
            "index_equal": same_index,
            "max_abs_diff": diffs,
            "max_abs_diff_other_columns": other,
            "worst": worst,
            "pass": ok,
        }
        res["max_abs_diff"] = max(res["max_abs_diff"], worst if math.isfinite(worst) else 1e99)
        res["pass"] = res["pass"] and ok
        print(PRIMARY, o, "worst", worst, flush=True)
    return res


# ---------------------------------------------------------------------------
# stage rules
# ---------------------------------------------------------------------------
def rule_path(variant: str, rule: str, o: int) -> Path:
    return OUT_DATA / f"{variant}_{rule}_o{o}.parquet"


def run_rules(variant: str, rules: tuple[str, ...], limit: int | None = None) -> None:
    OUT_DATA.mkdir(parents=True, exist_ok=True)
    todo = {o: [r for r in rules if not rule_path(variant, r, o).exists()] for o in OFFSETS}
    if limit is None and not any(todo.values()):
        print(variant, "all checkpoints exist, skip", flush=True)
        return
    ctx = T25.Context()
    for o in OFFSETS:
        need = tuple(todo[o])
        if not need:
            continue
        out = rules_pass(ctx, variant, o, need, limit=limit)
        for r, df in out.items():
            saved = pd.read_parquet(T25.RAW / f"R6_{variant}_o{o}.parquet")
            if limit is None:
                assert df.index.equals(saved.index), (variant, r, o, "label dates differ from R6")
                df.to_parquet(rule_path(variant, r, o))
            else:
                df.to_parquet(OUT_DATA / f"debug_{variant}_{r}_o{o}.parquet")
        print(variant, "offset", o, "done", need, flush=True)


# ---------------------------------------------------------------------------
# stage evaluate (parquets only)
# ---------------------------------------------------------------------------
def load_rule(variant: str, rule: str, o: int) -> pd.DataFrame:
    if rule == "B0":
        return pd.read_parquet(T25.RAW / f"R6_{variant}_o{o}.parquet")
    return pd.read_parquet(rule_path(variant, rule, o))


def hac_mean_t(d: np.ndarray, lag: int = 5) -> dict:
    """Newey-West (Bartlett, lag 5) t of the mean of ``d`` (intercept-only regression)."""
    d = np.asarray(d, dtype="float64")
    d = d[np.isfinite(d)]
    n = len(d)
    u = d - d.mean()
    s = float(u @ u) / n
    for k in range(1, lag + 1):
        s += 2.0 * (1.0 - k / (lag + 1.0)) * float(u[k:] @ u[:-k]) / n
    se = math.sqrt(s / n)
    return {
        "mean": float(d.mean()),
        "se": se,
        "t": float(d.mean() / se) if se > 0 else float("nan"),
        "n": n,
    }


def win_slice(df: pd.DataFrame, w: tuple[str, str]) -> pd.DataFrame:
    return df.loc[w[0] : w[1]]


def window_block(
    frames: list[pd.DataFrame], extras: list[pd.DataFrame] | None, w: tuple[str, str]
) -> dict:
    from open_composer.research.scorecard_v2 import annual_sharpe

    per = [T25.series_metrics(f, w) for f in frames]
    bl = T25.blend(frames)
    mb = T25.series_metrics(bl, w)
    net2x = [
        annual_sharpe(
            win_slice(f, w)["gross"] - 2.0 * win_slice(f, w)["cost"] - win_slice(f, w)["borrow"]
        )
        for f in frames
    ]
    out = {
        "n": mb["n"],
        "net_sharpe_by_offset": [m["net_sharpe"] for m in per],
        "gross_sharpe_by_offset": [m["gross_sharpe"] for m in per],
        "net_sharpe_offset_median": float(np.median([m["net_sharpe"] for m in per])),
        "gross_sharpe_offset_median": float(np.median([m["gross_sharpe"] for m in per])),
        "net_sharpe_blend": mb["net_sharpe"],
        "gross_sharpe_blend": mb["gross_sharpe"],
        "cost_bp_yr": mb["trade_cost_bp_yr"],
        "borrow_bp_yr": mb["borrow_bp_yr"],
        "turnover_one_sided_ann": mb["turnover_one_sided_ann"],
        "ann_vol_net_blend": mb["ann_vol_net"],
        "beta_ols": mb["beta_ols"],
        "beta_dimson": mb["beta_dimson"],
        "net_sharpe_2x_cost_by_offset": net2x,
        "net_sharpe_2x_cost_offset_median": float(np.median(net2x)),
    }
    if extras is not None:
        out["gross_exposure_mean"] = float(
            np.mean([win_slice(e, w)["gross_exposure"].mean() for e in extras])
        )
    return out


def run_evaluate() -> dict:
    b0_frames = [load_rule(PRIMARY, "B0", o) for o in OFFSETS]
    b0_ext = [pd.read_parquet(rule_path(PRIMARY, "B0", o)) for o in OFFSETS]
    b0_blend = T25.blend(b0_frames)
    b0 = {"windows": {k: window_block(b0_frames, b0_ext, w) for k, w in WINDOWS.items()}}
    res: dict = {"b0": b0, "rules": {}}
    for rule in CANDIDATES:
        frames = [load_rule(PRIMARY, rule, o) for o in OFFSETS]
        for o, f in enumerate(frames):
            assert f.index.equals(b0_frames[o].index), (rule, o)
        rl_blend = T25.blend(frames)
        blk: dict = {"windows": {}, "delta_vs_b0": {}, "nw_t": {}}
        for k, w in WINDOWS.items():
            wb = window_block(frames, frames, w)
            ref = b0["windows"][k]
            diffs = [
                a - b
                for a, b in zip(
                    wb["net_sharpe_by_offset"], ref["net_sharpe_by_offset"], strict=True
                )
            ]
            wb["delta_offset_median"] = (
                wb["net_sharpe_offset_median"] - ref["net_sharpe_offset_median"]
            )
            wb["delta_median_of_offset_diffs"] = float(np.median(diffs))
            wb["offsets_improved"] = int(sum(d > 0 for d in diffs))
            wb["net_sharpe_diff_by_offset"] = diffs
            blk["windows"][k] = wb
            blk["delta_vs_b0"][k] = {
                "delta_offset_median": wb["delta_offset_median"],
                "delta_median_of_offset_diffs": wb["delta_median_of_offset_diffs"],
                "offsets_improved": wb["offsets_improved"],
                "net_sharpe_diff_by_offset": diffs,
                "delta_gross_sharpe_offset_median": wb["gross_sharpe_offset_median"]
                - ref["gross_sharpe_offset_median"],
                "delta_cost_bp_yr": wb["cost_bp_yr"] - ref["cost_bp_yr"],
            }
            d = (win_slice(rl_blend, w)["net"] - win_slice(b0_blend, w)["net"]).to_numpy()
            blk["nw_t"][k] = hac_mean_t(d, 5)
        blk["nw_t_full"] = blk["nw_t"]["full"]["t"]
        rc, st_, fu = blk["windows"]["recent"], blk["windows"]["stress"], blk["windows"]["full"]
        e1 = bool(rc["delta_offset_median"] >= 0.10 and st_["delta_offset_median"] >= 0.10)
        e2 = bool(rc["offsets_improved"] >= 4 and st_["offsets_improved"] >= 4)
        e3 = bool(blk["nw_t_full"] >= 2.0)
        e4 = bool(
            all(
                abs(blk["windows"][k][b]) <= 0.15
                for k in ("recent", "stress")
                for b in ("beta_ols", "beta_dimson")
            )
        )
        blk["eligibility"] = {
            "E1": e1,
            "E2": e2,
            "E3": e3,
            "E4": e4,
            "all": bool(e1 and e2 and e3 and e4),
        }
        res["rules"][rule] = blk
        del fu
    elig = [r for r in CANDIDATES if res["rules"][r]["eligibility"]["all"]]
    sel = None
    if elig:
        rec = {r: res["rules"][r]["windows"]["recent"] for r in elig}
        top = max(v["net_sharpe_offset_median"] for v in rec.values())
        close = [r for r in elig if rec[r]["net_sharpe_offset_median"] >= top - 0.01]
        sel = (
            min(close, key=lambda r: rec[r]["turnover_one_sided_ann"])
            if len(close) > 1
            else close[0]
        )
    res["eligible_rules"] = elig
    res["selected_rule"] = sel
    res["mechanical_status"] = (
        "r_star_selected_stage2_pending" if sel else "no_rule_eligible_keep_v12"
    )
    return res


def jdump(path: Path, obj: object) -> None:
    path.write_text(json.dumps(obj, indent=1, default=float))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def spearman_rank_corr(a: pd.Series, b: pd.Series) -> float:
    d = pd.concat([a, b], axis=1, join="inner").dropna()
    if len(d) < 30:
        return float("nan")
    return float(d.iloc[:, 0].rank().corr(d.iloc[:, 1].rank()))


def d1_block(variant: str = PRIMARY) -> dict:
    """Turnover sources of B0: VIX-flip refreshes, drift and target change (return-free columns)."""
    frames = [pd.read_parquet(rule_path(variant, "B0", o)) for o in OFFSETS]
    out: dict = {}
    for k in ("recent", "stress"):
        w = WINDOWS[k]
        sub = [win_slice(f, w) for f in frames]
        ref = [s[s["refresh"] > 0] for s in sub]
        tot_to = sum(float(r["turnover"].sum()) for r in ref)
        tot_cost = sum(float(r["cost"].sum()) for r in ref)
        flip_to = sum(float(r.loc[r["flip"] > 0, "turnover"].sum()) for r in ref)
        flip_cost = sum(float(r.loc[r["flip"] > 0, "cost"].sum()) for r in ref)
        n_flip = sum(int((r["flip"] > 0).sum()) for r in ref)
        n_ref = sum(len(r) for r in ref)
        years = [len(s) / 252.0 for s in sub]
        mean_to_flip = flip_to / max(n_flip, 1)
        mean_to_other = (tot_to - flip_to) / max(n_ref - n_flip, 1)
        out[k] = {
            "refreshes": n_ref,
            "flip_refreshes": n_flip,
            "flips_per_tranche_year": float(
                np.mean([int((r["flip"] > 0).sum()) / y for r, y in zip(ref, years, strict=True)])
            ),
            "turnover_share_flip": flip_to / tot_to,
            "cost_share_flip": flip_cost / tot_cost,
            "mean_turnover_flip_refresh": mean_to_flip,
            "mean_turnover_other_refresh": mean_to_other,
            "drift_ann_per_tranche": float(
                np.mean([float(r["drift"].sum()) / y for r, y in zip(ref, years, strict=True)])
            ),
            "target_change_ann_per_tranche": float(
                np.mean([float(r["tgt_change"].sum()) / y for r, y in zip(ref, years, strict=True)])
            ),
            "turnover_ann_per_tranche": float(
                np.mean([float(r["turnover"].sum()) / y for r, y in zip(ref, years, strict=True)])
            ),
        }
    return out


def d2_block() -> dict:
    """Median weekly cross-sectional rank autocorrelation of the 9 themes and the M0 composite
    (offset-0 decision dates, consecutive weeks, ``in_u3000`` members; window by decision date)."""
    from open_composer.research.equity_book.signals import THEMES
    from scripts.run_book_v1_stage2 import AlphaSource, ThemeStore

    cal = pd.DatetimeIndex(pd.read_parquet(T25.EB / "panel/_calendar.parquet")["trade_date"])
    first = int(cal.searchsorted(pd.Timestamp(START)))
    dec = T25.decision_positions(len(cal), first, len(cal) - 3, T25.WEEK, 0)
    store = ThemeStore()
    src = AlphaSource(store, None, "M0", "u3000")
    names = list(THEMES) + ["M0_composite"]
    acs: dict[str, list[tuple[pd.Timestamp, float]]] = {n: [] for n in names}
    prev: dict[str, pd.Series] | None = None
    for p in dec:
        t = cal[p]
        th = store.at(t)
        if th.empty:
            prev = None
            continue
        members = th.index[th["in_u3000"].to_numpy(bool)]
        cur = {n: th.loc[members, n] for n in THEMES}
        cur["M0_composite"] = src(t, type("S", (), {"pos": p})(), members)
        if prev is not None:
            for n in names:
                acs[n].append((t, spearman_rank_corr(prev[n], cur[n])))
        prev = cur
    out: dict = {}
    for n in names:
        s = pd.Series({t: v for t, v in acs[n]}).dropna()
        out[n] = {}
        for k in ("recent", "stress"):
            lo, hi = WINDOWS[k]
            x = s.loc[lo:hi]
            out[n][k] = {
                "median_rank_autocorr": float(x.median()),
                "mean_rank_autocorr": float(x.mean()),
                "weeks": int(len(x)),
            }
    return out


def d3_block() -> dict:
    """2x-cost frontier (report only): offset-median net Sharpe at 1x and 2x cost, cost, turnover."""
    rows: dict = {}
    for rule in RULES:
        frames = [load_rule(PRIMARY, rule, o) for o in OFFSETS]
        exts = [pd.read_parquet(rule_path(PRIMARY, rule, o)) for o in OFFSETS]
        rows[rule] = {
            k: {
                m: window_block(frames, exts, WINDOWS[k])[m]
                for m in (
                    "net_sharpe_offset_median",
                    "net_sharpe_2x_cost_offset_median",
                    "gross_sharpe_offset_median",
                    "cost_bp_yr",
                    "turnover_one_sided_ann",
                    "gross_exposure_mean",
                )
            }
            for k in ("recent", "stress")
        }
    return rows


def run_diag() -> dict:
    res = {"D1": d1_block(), "D2": d2_block(), "D3": d3_block()}
    jdump(OUT_REPORT / "diagnostics.json", res)
    return res


IMPLEMENTATION_CHOICES = [
    "Contract windows (recent 2024-01-08..2026-09-15, stress 2017-10-02..2023-08-31, full 2017-10-02..2026-09-15, A, B) are used, not T25.WINDOWS (whose recent ends 2026-12-31); series_metrics slices label dates.",
    "Several rules share one decision loop per (variant, offset): decision inputs, targets and returns are computed once, each rule keeps its own (w_state, h_state, x_prev); B0 is one of them and was checked against the saved R6 parquets (identity.json: o0 and o3, four columns, max abs diff 0.0; all five offsets also 0.0).",
    "delta_offset_median = median over the 5 offsets of the rule's net Sharpe minus median over the 5 offsets of B0's net Sharpe (E1); the median of the per-offset differences is reported but not used for E1.",
    "E2 counts offsets with a strictly higher net Sharpe than B0 of the same offset in each window; E3 uses the full-window Newey-West t (Bartlett, lag 5, intercept only, no small-sample correction) of the blended daily net difference; E4 uses the OLS and Dimson beta of the blended net series vs SPY in recent and stress.",
    "The Newey-West t is computed by hac_mean_t in the script; cross-check on N50 full: hac_mean_t 1.758 vs book_v12_score.nw_ols intercept t 1.760 with a random regressor (same estimator up to the regressor).",
    "2x cost net = gross - 2 * trade cost - borrow on the same rows (borrow not doubled).",
    "Selection tie rule (within 0.01 of the top recent offset-median net Sharpe, take the lower recent turnover) is implemented but was not needed: no rule met E1-E4.",
    "gross_exposure_mean is the mean over window rows of sum|x_new| held in each block, averaged over the 5 offsets.",
    "D1 drift = sum|x_old - x_prev_new| and target change = sum|w_tgt - w_tgt_prev| at refresh rows (first refresh excluded), summed per window, divided by window years (rows/252), averaged over the 5 offsets; one offset pass is one full book, so values are in units of book equity.",
    "D2 rank autocorrelation: Spearman between consecutive offset-0 decision dates over in_u3000 members with finite values at both dates; weeks with an undefined correlation (constant cross-section) are dropped and the week count is reported per series and window; windows by the later decision date.",
    "Stage 2 (variants, account, placebo, score) was not run because no rule met E1-E4 (stage gate of hypotheses.md section 5).",
]


def fmt(x: float | None, nd: int = 3) -> str:
    return "n/a" if x is None or not math.isfinite(x) else f"{x:.{nd}f}"


def write_final() -> dict:
    ev = json.loads((OUT_DATA / "stage1_eval.json").read_text())
    ident = json.loads((OUT_REPORT / "identity.json").read_text())
    diag = json.loads((OUT_REPORT / "diagnostics.json").read_text())
    hyp = OUT_REPORT / "hypotheses.md"
    res = {
        "contract": {"hypotheses_sha256": sha256(hyp), "unchanged": True},
        "identity": {
            "pass": ident["pass"],
            "max_abs_diff": ident["max_abs_diff"],
            "cases": ident["cases"],
        },
        "stage1": {"rules": ev["rules"], "b0": ev["b0"], "eligible_rules": ev["eligible_rules"]},
        "selected_rule": ev["selected_rule"],
        "stage2": None,
        "mechanical_status": ev["mechanical_status"],
        "implementation_choices": IMPLEMENTATION_CHOICES,
    }
    jdump(OUT_REPORT / "results.json", res)
    ledger = {
        "iteration": "t20261004_book_v13_tc",
        "family_n": 15,
        "trials": [
            {
                "candidate_id": f"V13_{r}",
                "rule": r,
                "net_sharpe_offset_median_recent": ev["rules"][r]["windows"]["recent"][
                    "net_sharpe_offset_median"
                ],
                "net_sharpe_offset_median_stress": ev["rules"][r]["windows"]["stress"][
                    "net_sharpe_offset_median"
                ],
                "delta_offset_median_recent": ev["rules"][r]["windows"]["recent"][
                    "delta_offset_median"
                ],
                "delta_offset_median_stress": ev["rules"][r]["windows"]["stress"][
                    "delta_offset_median"
                ],
                "eligibility": ev["rules"][r]["eligibility"],
                "source": "results.json",
            }
            for r in CANDIDATES
        ],
        "b0_net_sharpe_offset_median_recent": ev["b0"]["windows"]["recent"][
            "net_sharpe_offset_median"
        ],
        "b0_net_sharpe_offset_median_stress": ev["b0"]["windows"]["stress"][
            "net_sharpe_offset_median"
        ],
    }
    jdump(OUT_REPORT / "trial-ledger.json", ledger)
    L: list[str] = []
    L.append(
        "# t20261004_book_v13_tc: cost-aware trading rules on the v1.2 primary book (M0_U3000)\n"
    )
    L.append(
        "Mechanical output of `scripts/book_v13_trading_rules.py`; contract `hypotheses.md` unchanged (sha256 in results.json). No verdict is stated here; the main review decides.\n"
    )
    L.append(
        f"- identity: pass={ident['pass']}, max abs diff {ident['max_abs_diff']}\n- mechanical_status: **{ev['mechanical_status']}**, selected_rule: {ev['selected_rule']}\n- Stage 2 not run (no rule met E1-E4).\n"
    )
    for k in ("recent", "stress", "full", "A", "B"):
        L.append(f"\n## Window {k} ({WINDOWS[k][0]}..{WINDOWS[k][1]})\n")
        L.append(
            "| rule | net SR (offset med) | gross SR | net SR blend | cost bp/yr | one-sided turnover/yr | mean gross exp | OLS beta | Dimson beta | 2x-cost net SR | delta vs B0 | offsets improved |"
        )
        L.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
        rows = [("B0", ev["b0"]["windows"][k], None, None)] + [
            (
                r,
                ev["rules"][r]["windows"][k],
                ev["rules"][r]["windows"][k]["delta_offset_median"],
                ev["rules"][r]["windows"][k]["offsets_improved"],
            )
            for r in CANDIDATES
        ]
        for name, w, dlt, imp in rows:
            L.append(
                f"| {name} | {fmt(w['net_sharpe_offset_median'])} | {fmt(w['gross_sharpe_offset_median'])} | {fmt(w['net_sharpe_blend'])} | {fmt(w['cost_bp_yr'], 1)} | {fmt(w['turnover_one_sided_ann'], 2)} | {fmt(w['gross_exposure_mean'], 3)} | {fmt(w['beta_ols'])} | {fmt(w['beta_dimson'])} | {fmt(w['net_sharpe_2x_cost_offset_median'])} | {fmt(dlt)} | {imp if imp is not None else '-'} |"
            )
    L.append("\n## Newey-West t (lag 5) of the blended daily net difference vs B0\n")
    L.append("| rule | full | recent | stress | A | B |")
    L.append("|---|---|---|---|---|---|")
    for r in CANDIDATES:
        n = ev["rules"][r]["nw_t"]
        L.append(
            f"| {r} | "
            + " | ".join(fmt(n[k]["t"], 2) for k in ("full", "recent", "stress", "A", "B"))
            + " |"
        )
    L.append("\n## Eligibility (hypotheses.md section 5)\n")
    L.append(
        "| rule | E1 +0.10 both windows | E2 >=4/5 offsets both windows | E3 NW t full >= 2 | E4 |beta| <= 0.15 | all |"
    )
    L.append("|---|---|---|---|---|---|")
    for r in CANDIDATES:
        e = ev["rules"][r]["eligibility"]
        L.append(f"| {r} | {e['E1']} | {e['E2']} | {e['E3']} | {e['E4']} | {e['all']} |")
    d1 = diag["D1"]
    L.append("\n## D1 turnover sources of B0 (return-free)\n")
    L.append(
        "| window | flips/tranche-yr | turnover share on flip refreshes | cost share on flip refreshes | mean turnover flip / other refresh | drift /yr | target change /yr | turnover /yr |"
    )
    L.append("|---|---|---|---|---|---|---|---|")
    for k in ("recent", "stress"):
        d = d1[k]
        L.append(
            f"| {k} | {fmt(d['flips_per_tranche_year'], 2)} | {fmt(d['turnover_share_flip'])} | {fmt(d['cost_share_flip'])} | {fmt(d['mean_turnover_flip_refresh'], 2)} / {fmt(d['mean_turnover_other_refresh'], 2)} | {fmt(d['drift_ann_per_tranche'], 2)} | {fmt(d['target_change_ann_per_tranche'], 2)} | {fmt(d['turnover_ann_per_tranche'], 2)} |"
        )
    L.append("\n## D2 median weekly rank autocorrelation (offset-0 decision dates, in_u3000)\n")
    L.append("| series | recent | weeks | stress | weeks |")
    L.append("|---|---|---|---|---|")
    for n, v in diag["D2"].items():
        L.append(
            f"| {n} | {fmt(v['recent']['median_rank_autocorr'])} | {v['recent']['weeks']} | {fmt(v['stress']['median_rank_autocorr'])} | {v['stress']['weeks']} |"
        )
    L.append("\n## D3 2x-cost frontier (offset-median net Sharpe at 1x / 2x cost)\n")
    L.append("| rule | recent 1x | recent 2x | stress 1x | stress 2x |")
    L.append("|---|---|---|---|---|")
    for r, v in diag["D3"].items():
        L.append(
            f"| {r} | {fmt(v['recent']['net_sharpe_offset_median'])} | {fmt(v['recent']['net_sharpe_2x_cost_offset_median'])} | {fmt(v['stress']['net_sharpe_offset_median'])} | {fmt(v['stress']['net_sharpe_2x_cost_offset_median'])} |"
        )
    L.append("\n## Implementation choices\n")
    L += [f"- {c}" for c in IMPLEMENTATION_CHOICES]
    (OUT_REPORT / "report.md").write_text("\n".join(L) + "\n")
    return res


# ---------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--stage",
        choices=[
            "identity",
            "rules",
            "evaluate",
            "diag",
            "final",
            "variants",
            "account",
            "placebo",
            "score",
        ],
        required=True,
    )
    ap.add_argument("--variant", default=PRIMARY)
    ap.add_argument("--rule", default=None)
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()
    if a.stage == "identity":
        res = run_identity()
        OUT_REPORT.mkdir(parents=True, exist_ok=True)
        jdump(OUT_REPORT / "identity.json", res)
        print(json.dumps({k: res[k] for k in ("max_abs_diff", "pass")}))
        if not res["pass"]:
            sys.exit(3)
    elif a.stage == "rules":
        rules = (a.rule,) if a.rule else RULES
        run_rules(a.variant, rules, a.limit)
    elif a.stage == "evaluate":
        res = run_evaluate()
        jdump(OUT_DATA / "stage1_eval.json", res)
        for r in CANDIDATES:
            e = res["rules"][r]
            print(
                r,
                {
                    k: round(e["windows"][k]["net_sharpe_offset_median"], 3)
                    for k in ("recent", "stress")
                },
                {k: round(e["windows"][k]["delta_offset_median"], 3) for k in ("recent", "stress")},
                e["eligibility"],
            )
        print("selected", res["selected_rule"], res["mechanical_status"])
    elif a.stage == "diag":
        run_diag()
    elif a.stage == "final":
        write_final()
    else:
        raise SystemExit(f"stage {a.stage} not implemented yet")


if __name__ == "__main__":
    main()
