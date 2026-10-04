# ruff: noqa: E501
"""Book v1.4 ML composites, Stage B (T-20261004-03): Stage A survivors through the unchanged v1.2
strategy layer (T-25 R6 rule) against M0 restarted from 2019-01-02 (B0r).

Contract: ``reports/research/iterations/t20261004_book_v14_ml/hypotheses.md`` sections 2, 5, 6.

    scripts/run_capped.sh --mem 1.5G -- uv run python scripts/book_v14_ml_eval.py --stage identity
    scripts/run_capped.sh --mem 1.5G -- uv run python scripts/book_v14_ml_eval.py --stage passes
    scripts/run_capped.sh --mem 1.5G -- uv run python scripts/book_v14_ml_eval.py --stage evaluate

Daily series go to ``data/research/book_v14/S_<candidate>_o<k>.parquet`` (outside the hash-guarded
research snapshot).  No account layer, placebo or tier here (Stage C).
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
from open_composer.research.equity_book import optimize as op  # noqa: E402
from scripts import book_v12_account as A  # noqa: E402
from scripts import realism_ladder_book_ls as T25  # noqa: E402

ITER = ROOT / "reports/research/iterations/t20261004_book_v14_ml"
DATA = ROOT / "data/research/book_v14"
PRED = DATA / "predictions.parquet"
OFFSETS = T25.OFFSETS
START_ML = "2019-01-02"
TOL = 1e-12
HYPOTHESES_SHA = "af771470eaab998f0f2152d1f2e3e4cf8e9f45af5875a7bba0f8d71642fe99c0"
WINDOWS = {
    "recent": ("2024-01-08", "2026-09-15"),
    "stress_ml": ("2019-01-02", "2023-08-31"),
    "full_ml": ("2019-01-02", "2026-09-15"),
    "A": ("2024-01-08", "2026-06-30"),
    "B": ("2026-07-01", "2026-09-15"),
}
DECIDING = ("recent", "stress_ml")
ALL_CANDIDATES = ("m2", "m3", "m0m2", "m0m3")
FAMILY_N = 19
SERIES_COLS = ["gross", "cost", "borrow", "turnover", "spy", "hedge_size", "vix_scale", "net"]


# ---------------------------------------------------------------------------
# score source
# ---------------------------------------------------------------------------
class PredictionSource:
    """``src(t, state, universe)`` over a prediction column: rank-normal of the column's values
    at date ``t`` reindexed to ``universe`` (NaN where there is no prediction), optionally
    followed by the same within-date placebo permutation as ``AlphaSource``."""

    def __init__(
        self,
        path: Path | str | pd.DataFrame,
        column: str,
        placebo_seed: int | None = None,
    ) -> None:
        if isinstance(path, pd.DataFrame):
            df = path[["trade_date", "symbol", column]]
        else:
            df = pd.read_parquet(path, columns=["trade_date", "symbol", column])
        df = df.sort_values(["trade_date", "symbol"], kind="stable").reset_index(drop=True)
        self.column = column
        self._dates = pd.DatetimeIndex(df["trade_date"].to_numpy())
        self._sym = df["symbol"].to_numpy()
        self._val = df[column].to_numpy("float64")
        self.available = pd.DatetimeIndex(self._dates.unique())
        self.rng = None
        if placebo_seed is not None:
            from scripts.run_book_v1_stage2 import PLACEBO_SEED_BASE

            self.rng = np.random.default_rng(PLACEBO_SEED_BASE + placebo_seed)

    def __call__(self, t: pd.Timestamp, state, universe: pd.Index) -> pd.Series:
        a = int(self._dates.searchsorted(t, side="left"))
        b = int(self._dates.searchsorted(t, side="right"))
        s = pd.Series(self._val[a:b], index=self._sym[a:b])
        out = op.rank_normal(s.reindex(universe))
        if self.rng is not None:
            from scripts.run_book_v1_stage2 import shuffle_scores

            out = shuffle_scores(out, self.rng)
        return out


# ---------------------------------------------------------------------------
# the v1.2 loop, restarted at ``start`` with an injected source
# ---------------------------------------------------------------------------
def strategy_pass_with_source(
    ctx: T25.Context,
    src,
    flag: str = "in_u3000",
    offset: int = 0,
    start: str = START_ML,
    limit: int | None = None,
) -> pd.DataFrame:
    """Copy of ``book_v12_account.strategy_pass`` with a ``start`` argument and an injected score
    source; plus ``gross_exposure`` = sum|w| of the stock weights at the refresh, carried through
    the block.  Decision positions keep the v1.2 calendar (``pos % 5 == offset``)."""
    px = ctx.px
    first = int(px.dates.searchsorted(pd.Timestamp(start)))
    last_label = px.T - 3
    dec = T25.decision_positions(px.T, first, last_label, T25.WEEK, offset)
    w_state, h_state = np.zeros(px.N), 0.0
    rows: list[pd.DataFrame] = []
    for i, p in enumerate(dec):
        if limit is not None and i >= limit:
            break
        nxt = dec[i + 1] if i + 1 < len(dec) else last_label + 1
        length = nxt - p
        di = A.decision_inputs(ctx, src, flag, p)
        if di is None:
            continue
        tt = A.tranche_from_inputs(ctx, di)
        ret, spy_r = px.returns("close", p, length)
        blk = bv.hold_block(tt.w, ret, spy_r, h0=tt.h)
        d_w = tt.w - w_state
        d_h = tt.h - h_state
        turnover = float(np.abs(d_w).sum())
        cost = T25.real_cost(ctx, di.t, px.symbols, d_w, d_h, di.attrs)
        n = len(blk["pnl"])
        cost_v = np.zeros(n)
        cost_v[0] = cost
        to_v = np.zeros(n)
        to_v[0] = turnover
        bor = blk["short_notional"] * (bv.BORROW_BP_YEAR_T25 / 1e4 / 252.0)
        rows.append(
            pd.DataFrame(
                {
                    "gross": blk["pnl"],
                    "cost": cost_v,
                    "borrow": bor,
                    "turnover": to_v,
                    "spy": spy_r,
                    "hedge_size": np.full(n, tt.h),
                    "vix_scale": np.full(n, tt.vscale),
                    "gross_exposure": np.full(n, float(np.abs(tt.w).sum())),
                },
                index=px.dates[p : p + n],
            )
        )
        w_state, h_state = blk["w_end"], blk["h_end"]
    df = pd.concat(rows)
    df["net"] = df["gross"] - df["cost"] - df["borrow"]
    return df


# ---------------------------------------------------------------------------
# pure helpers (tested on synthetic data)
# ---------------------------------------------------------------------------
def vol_matched_diff(cand: pd.Series, base: pd.Series) -> pd.Series:
    """d_t = cand_t * (sd(base) / sd(cand)) - base_t over the common index (sd over that index)."""
    idx = cand.index.intersection(base.index)
    c, b = cand.loc[idx], base.loc[idx]
    return c * (float(b.std(ddof=1)) / float(c.std(ddof=1))) - b


def count_offsets_improved(cand: list[float], base: list[float]) -> int:
    return int(sum(a > b for a, b in zip(cand, base, strict=True)))


def next_decision_dates_equal(
    ctx: T25.Context, start: str, offset: int, v12_first: str | None = None
) -> bool:
    """Decision positions of the restarted loop equal the v1.2 positions at or after ``start``."""
    px = ctx.px
    first = int(px.dates.searchsorted(pd.Timestamp(start)))
    mine = T25.decision_positions(px.T, first, px.T - 3, T25.WEEK, offset)
    v12 = T25.decision_positions(px.T, 0, px.T - 3, T25.WEEK, offset)
    return mine == [p for p in v12 if p >= first]


def newey_west(x: np.ndarray, lags: int) -> float:
    from scripts.run_t20260930_17_model_family_sweep import newey_west_t

    return newey_west_t(x, lags)


# ---------------------------------------------------------------------------
# stages
# ---------------------------------------------------------------------------
def _r6(offset: int) -> pd.DataFrame:
    return pd.read_parquet(T25.RAW / f"R6_M0_U3000_o{offset}.parquet")


def _spath(name: str, offset: int) -> Path:
    return DATA / f"S_{name}_o{offset}.parquet"


def run_identity(limit: int | None = None) -> dict:
    ctx = T25.Context()
    src_a = A.make_source(ctx, "M0_U3000")
    src_b = PredictionSource(PRED, "m0")
    out: dict = {
        "tolerance": TOL,
        "start": START_ML,
        "cases": {},
        "pass": True,
        "limit": limit,
    }
    for o in OFFSETS:
        a = strategy_pass_with_source(ctx, src_a, "in_u3000", o, START_ML, limit=limit)
        b = strategy_pass_with_source(ctx, src_b, "in_u3000", o, START_ML, limit=limit)
        r6 = _r6(o)
        first_label = a.index[0]
        r6s = r6.loc[first_label : a.index[-1]] if limit else r6.loc[first_label:]
        index_equal = bool(a.index.equals(r6s.index))
        chk_a: dict = {"index_equal": index_equal}
        ok_a = index_equal
        if index_equal:
            for c in ("gross", "borrow", "hedge_size", "vix_scale"):
                d = float((a[c] - r6s[c]).abs().max())
                chk_a[c] = d
                ok_a = ok_a and math.isfinite(d) and d <= TOL
            d_cost = float((a["cost"].iloc[1:] - r6s["cost"].iloc[1:]).abs().max())
            chk_a["cost_except_first_label"] = d_cost
            chk_a["cost_first_label"] = {
                "restarted": float(a["cost"].iloc[0]),
                "r6": float(r6s["cost"].iloc[0]),
            }
            ok_a = ok_a and math.isfinite(d_cost) and d_cost <= TOL
        ok_b = bool(a.index.equals(b.index))
        chk_b: dict = {"index_equal": ok_b}
        if ok_b:
            worst = 0.0
            for c in a.columns:
                d = float((a[c] - b[c]).abs().max())
                chk_b[c] = d
                worst = max(worst, d)
            chk_b["worst"] = worst
            ok_b = math.isfinite(worst) and worst <= TOL
        out["cases"][f"o{o}"] = {
            "first_label_date": str(first_label.date()),
            "rows": len(a),
            "a_alpha_source_vs_r6": chk_a,
            "a_pass": bool(ok_a),
            "b_prediction_m0_vs_a": chk_b,
            "b_pass": bool(ok_b),
        }
        out["pass"] = bool(out["pass"] and ok_a and ok_b)
        print("identity offset", o, "a", ok_a, "b", ok_b, flush=True)
        if limit is None:
            DATA.mkdir(parents=True, exist_ok=True)
            a.to_parquet(_spath("B0r", o))
    return out


def run_passes(only: str | None = None) -> None:
    ctx = T25.Context()
    st = json.loads((ITER / "stage_a.json").read_text())
    if st["mechanical_status_stage_a"] != "stage_b_authorized":
        raise SystemExit("blocked: Stage A did not authorize Stage B")
    for cand in st["stage_a_survivors"]:
        if only is not None and cand != only:
            continue
        src = PredictionSource(PRED, cand)
        for o in OFFSETS:
            path = _spath(cand, o)
            if path.exists():
                print("skip existing", path.name, flush=True)
                continue
            df = strategy_pass_with_source(ctx, src, "in_u3000", o, START_ML)
            df.to_parquet(path)
            print("wrote", path.name, len(df), flush=True)
    # B0r: the identity stage already wrote it from the AlphaSource (a); rebuild only if missing
    src_a = A.make_source(ctx, "M0_U3000")
    for o in OFFSETS:
        path = _spath("B0r", o)
        if not path.exists():
            df = strategy_pass_with_source(ctx, src_a, "in_u3000", o, START_ML)
            df.to_parquet(path)
            print("wrote", path.name, len(df), flush=True)


def window_block(frames: list[pd.DataFrame], w: tuple[str, str]) -> dict:
    from open_composer.research.scorecard_v2 import annual_sharpe

    per = [T25.series_metrics(f, w) for f in frames]
    bl = T25.blend(frames)
    mb = T25.series_metrics(bl, w)

    def net2(f: pd.DataFrame) -> float:
        s = f.loc[w[0] : w[1]]
        return annual_sharpe(s["gross"] - 2.0 * s["cost"] - s["borrow"])

    net2x = [net2(f) for f in frames]
    return {
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
        "gross_exposure_mean": float(
            np.mean([f.loc[w[0] : w[1], "gross_exposure"].mean() for f in frames])
        )
        if "gross_exposure" in frames[0].columns
        else None,
        "net_sharpe_2x_cost_by_offset": net2x,
        "net_sharpe_2x_cost_offset_median": float(np.median(net2x)),
        "net_sharpe_2x_cost_blend": net2(bl),
    }


def _load(name: str) -> list[pd.DataFrame]:
    return [pd.read_parquet(_spath(name, o)) for o in OFFSETS]


def run_evaluate() -> dict:
    st = json.loads((ITER / "stage_a.json").read_text())
    survivors = list(st["stage_a_survivors"])
    perm_pass = bool(st["permutation_check"]["pass"])
    b0_frames = _load("B0r")
    b0_blend = T25.blend(b0_frames)
    b0 = {"windows": {k: window_block(b0_frames, w) for k, w in WINDOWS.items()}}
    # M0 on the v1.2 stress window from the R6 parquets (reported, not used)
    r6 = [_r6(o) for o in OFFSETS]
    v12w = ("2017-10-02", "2023-08-31")
    r6_blk = window_block(r6, v12w)
    b0["v12_stress_2017_10_02__2023_08_31_from_R6"] = {
        k: r6_blk[k]
        for k in (
            "n",
            "net_sharpe_by_offset",
            "net_sharpe_offset_median",
            "gross_sharpe_offset_median",
            "net_sharpe_blend",
            "cost_bp_yr",
            "turnover_one_sided_ann",
            "beta_ols",
            "beta_dimson",
        )
    }
    cands: dict = {}
    for cand in survivors:
        frames = _load(cand)
        for o in OFFSETS:
            assert frames[o].index.equals(b0_frames[o].index), (cand, o)
        blend = T25.blend(frames)
        wins: dict = {}
        delta: dict = {}
        for k, w in WINDOWS.items():
            wb = window_block(frames, w)
            ref = b0["windows"][k]
            diffs = [
                a - b
                for a, b in zip(
                    wb["net_sharpe_by_offset"], ref["net_sharpe_by_offset"], strict=True
                )
            ]
            wb["net_sharpe_diff_by_offset"] = diffs
            wb["delta_offset_median"] = (
                wb["net_sharpe_offset_median"] - ref["net_sharpe_offset_median"]
            )
            wb["offsets_improved"] = count_offsets_improved(
                wb["net_sharpe_by_offset"], ref["net_sharpe_by_offset"]
            )
            wins[k] = wb
            delta[k] = {
                "delta_offset_median": wb["delta_offset_median"],
                "offsets_improved": wb["offsets_improved"],
                "net_sharpe_diff_by_offset": diffs,
                "delta_gross_sharpe_offset_median": wb["gross_sharpe_offset_median"]
                - ref["gross_sharpe_offset_median"],
                "delta_cost_bp_yr": wb["cost_bp_yr"] - ref["cost_bp_yr"],
            }
        nwt: dict = {}
        corr: dict = {}
        for k in ("full_ml", "recent", "stress_ml"):
            w = WINDOWS[k]
            c = blend["net"].loc[w[0] : w[1]]
            b = b0_blend["net"].loc[w[0] : w[1]]
            d = vol_matched_diff(c, b)
            nwt[k] = {
                "t": newey_west(d.to_numpy(), 5),
                "mean_daily": float(d.mean()),
                "n": int(len(d)),
                "lag": 5,
            }
            idx = c.index.intersection(b.index)
            corr[k] = float(np.corrcoef(c.loc[idx], b.loc[idx])[0, 1])
        rc, sc = wins["recent"], wins["stress_ml"]
        e1 = bool(rc["delta_offset_median"] >= 0.10 and sc["delta_offset_median"] >= 0.10)
        e2 = bool(rc["offsets_improved"] >= 4 and sc["offsets_improved"] >= 4)
        e4 = bool(
            all(abs(x["beta_ols"]) <= 0.15 and abs(x["beta_dimson"]) <= 0.15 for x in (rc, sc))
        )
        e5 = perm_pass
        cands[cand] = {
            "windows": wins,
            "delta_vs_b0r": delta,
            "vol_matched_nw_t": nwt,
            "corr_with_b0r": corr,
            "eligibility": {
                "E1": e1,
                "E2": e2,
                "E4": e4,
                "E5": e5,
                "all": bool(e1 and e2 and e4 and e5),
            },
        }
    eligible = [c for c in survivors if cands[c]["eligibility"]["all"]]
    selected = None
    if eligible:
        rec = {c: cands[c]["windows"]["recent"]["net_sharpe_offset_median"] for c in eligible}
        top = max(rec.values())
        tied = [c for c in eligible if top - rec[c] <= 0.01]
        selected = max(
            tied, key=lambda c: cands[c]["windows"]["stress_ml"]["net_sharpe_offset_median"]
        )

    def both_above(name: str) -> bool:
        if name not in cands:
            return False  # stopped at Stage A: counts as not passing
        return all(cands[name]["windows"][k]["delta_offset_median"] > 0 for k in DECIDING)

    res = {
        "contract": {
            "hypotheses_sha256": hashlib.sha256((ITER / "hypotheses.md").read_bytes()).hexdigest(),
            "unchanged": hashlib.sha256((ITER / "hypotheses.md").read_bytes()).hexdigest()
            == HYPOTHESES_SHA,
            "expected_sha256": HYPOTHESES_SHA,
        },
        "identity": json.loads((ITER / "identity.json").read_text()),
        "stage_a_ref": {
            "survivors": survivors,
            "status": st["mechanical_status_stage_a"],
            "permutation_check_pass": perm_pass,
        },
        "windows": {k: list(v) for k, v in WINDOWS.items()},
        "b0r": b0,
        "candidates": cands,
        "selected_candidate": selected,
        "ml_contribution_pass": bool(any(both_above(c) for c in ("m2", "m3"))),
        "ml_additive": bool(any(both_above(c) for c in ("m0m2", "m0m3"))),
        "mechanical_status": "eligible_candidate_selected"
        if selected
        else "no_candidate_eligible_keep_m0",
        "implementation_choices": [
            "Strategy layer = book_v12_account.strategy_pass loop copied with a start argument and injected source; decision positions keep pos % 5 == offset on the v1.2 calendar.",
            "PredictionSource = rank_normal of the prediction column reindexed to the in_u3000 members; same placebo branch as AlphaSource (not used in Stage B).",
            "B0r series were written by the identity stage (AlphaSource path) and reused by the passes stage; the PredictionSource m0 path was checked equal to them to <= 1e-12.",
            "gross_exposure = sum|w| of the stock weights at the refresh (before hedge), carried through the block; reported as the window mean over the 5 offsets.",
            "Blend = T25.blend (mean of the 5 offsets on common label dates); beta_ols/beta_dimson from T25.series_metrics on the blend.",
            "offsets_improved counts strictly greater net Sharpe per offset; ml_contribution_pass/ml_additive use strictly greater offset-median net Sharpe in both recent and stress_ml; a candidate stopped at Stage A counts as not passing.",
            "Vol-matched NW t: d_t = net_cand,t * sd(B0r)/sd(cand) - net_B0r,t on the blended daily net returns, sd over the same window, Newey-West (Bartlett) lag 5 from run_t20260930_17_model_family_sweep.newey_west_t.",
            "2x-cost net Sharpe: gross - 2*cost - borrow on the same paths.",
        ],
        "stage_a_stops": {
            c: {
                "stage_a_gross_offset_median": {
                    k: st["scores"][c]["simplified_gross_sharpe"][k]["offset_median"]
                    for k in DECIDING
                },
                "m0_gross_offset_median": {
                    k: st["scores"]["m0"]["simplified_gross_sharpe"][k]["offset_median"]
                    for k in DECIDING
                },
            }
            for c in ALL_CANDIDATES
            if c not in survivors
        },
    }
    return res


def write_outputs(res: dict) -> None:
    (ITER / "results.json").write_text(json.dumps(res, indent=1, default=float))
    ledger = []
    for c in ALL_CANDIDATES:
        if c in res["candidates"]:
            cc = res["candidates"][c]
            ledger.append(
                {
                    "candidate": f"V14_{c.upper()}",
                    "family_n": FAMILY_N,
                    "reached_stage": "B",
                    "eligibility": cc["eligibility"],
                    "delta_offset_median": {
                        k: cc["delta_vs_b0r"][k]["delta_offset_median"] for k in DECIDING
                    },
                    "offsets_improved": {
                        k: cc["delta_vs_b0r"][k]["offsets_improved"] for k in DECIDING
                    },
                    "selected": res["selected_candidate"] == c,
                }
            )
        else:
            ledger.append(
                {
                    "candidate": f"V14_{c.upper()}",
                    "family_n": FAMILY_N,
                    "reached_stage": "A",
                    "stopped": "Stage A gate: simplified gross Sharpe not above M0 in both recent and stress_ml",
                    "stage_a": res["stage_a_stops"].get(c),
                    "selected": False,
                }
            )
    (ITER / "trial-ledger.json").write_text(json.dumps(ledger, indent=1, default=float))
    lines = [
        "# t20261004_book_v14_ml Stage B report (T-20261004-03)",
        "",
        f"- contract unchanged: {res['contract']['unchanged']} (sha256 {res['contract']['hypotheses_sha256'][:12]}...)",
        f"- identity pass: {res['identity']['pass']}; Stage A status {res['stage_a_ref']['status']}; survivors {res['stage_a_ref']['survivors']}",
        f"- mechanical_status: {res['mechanical_status']}; selected: {res['selected_candidate']}",
        f"- ml_contribution_pass: {res['ml_contribution_pass']}; ml_additive: {res['ml_additive']}",
        "",
        "## Offset-median net Sharpe (B0r restarted from 2019-01-02)",
        "",
        "| series | recent | stress_ml | full_ml | A | B |",
        "|---|---|---|---|---|---|",
    ]

    def row(name: str, wins: dict) -> str:
        return (
            f"| {name} | "
            + " | ".join(
                f"{wins[k]['net_sharpe_offset_median']:.3f}"
                for k in ("recent", "stress_ml", "full_ml", "A", "B")
            )
            + " |"
        )

    lines.append(row("B0r", res["b0r"]["windows"]))
    for c, cc in res["candidates"].items():
        lines.append(row(c, cc["windows"]))
    v = res["b0r"]["v12_stress_2017_10_02__2023_08_31_from_R6"]
    lines += [
        "",
        f"B0 (R6) on the v1.2 stress window 2017-10-02..2023-08-31 (reported only): offset-median net Sharpe {v['net_sharpe_offset_median']:.3f}.",
        "",
        "## Candidates vs B0r",
        "",
        "| cand | d recent | d stress_ml | imp recent | imp stress | beta ols/dimson recent | beta ols/dimson stress | NW t full/recent/stress | corr full | E1 E2 E4 E5 |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for c, cc in res["candidates"].items():
        r, s = cc["windows"]["recent"], cc["windows"]["stress_ml"]
        t = cc["vol_matched_nw_t"]
        e = cc["eligibility"]
        lines.append(
            f"| {c} | {r['delta_offset_median']:+.3f} | {s['delta_offset_median']:+.3f} | {r['offsets_improved']} | {s['offsets_improved']} "
            f"| {r['beta_ols']:+.3f}/{r['beta_dimson']:+.3f} | {s['beta_ols']:+.3f}/{s['beta_dimson']:+.3f} "
            f"| {t['full_ml']['t']:.2f}/{t['recent']['t']:.2f}/{t['stress_ml']['t']:.2f} | {cc['corr_with_b0r']['full_ml']:.3f} "
            f"| {e['E1']} {e['E2']} {e['E4']} {e['E5']} |"
        )
    lines += [
        "",
        "Source: results.json in this folder. Stage A stops (m2, m3): see trial-ledger.json.",
    ]
    (ITER / "report.md").write_text("\n".join(lines) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=("identity", "passes", "evaluate"), required=True)
    ap.add_argument("--candidate", default=None)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    if args.stage == "identity":
        res = run_identity(limit=args.limit)
        if args.limit is None:
            (ITER / "identity.json").write_text(json.dumps(res, indent=1, default=float))
        else:
            print(json.dumps(res, indent=1, default=float))
        print("identity pass", res["pass"])
        if not res["pass"]:
            raise SystemExit(1)
    elif args.stage == "passes":
        run_passes(args.candidate)
    else:
        res = run_evaluate()
        write_outputs(res)
        print("mechanical_status", res["mechanical_status"], "selected", res["selected_candidate"])


if __name__ == "__main__":
    main()
