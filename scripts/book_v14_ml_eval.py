# ruff: noqa: E501
"""Book v1.4 candidate, Stage B (t20261004_book_v14_ml): Stage A survivors through the unchanged v1.2
strategy layer (T-25 R6 rule) against B0r.

Contract: ``reports/research/iterations/t20261004_book_v14_ml/hypotheses.md`` sections 2, 5 and 6
(frozen before any ML composite was trained).  Brief T-20261004-03.

    uv run python scripts/book_v14_ml_eval.py --stage identity   # gate: B0r == R6 and (a) == (b)
    uv run python scripts/book_v14_ml_eval.py --stage passes     # survivors x offsets -> S_<cand>_o<k>.parquet
    uv run python scripts/book_v14_ml_eval.py --stage evaluate   # parquets only -> results.json, report.md, ledger

Daily series go to ``data/research/book_v14/`` (outside the hash-guarded research snapshot).
``identity`` and ``passes`` run on Modal (see the brief); ``--mirror-dir`` copies every file as it is
written so a partial run still returns its output.  ``evaluate`` reads parquets only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from open_composer.research.equity_book import book_v12 as bv  # noqa: E402
from open_composer.research.equity_book import optimize as op  # noqa: E402
from scripts import book_v12_account as acct  # noqa: E402
from scripts import realism_ladder_book_ls as T25  # noqa: E402

ITER = ROOT / "reports/research/iterations/t20261004_book_v14_ml"
OUT_DATA = ROOT / "data/research/book_v14"
PRED = OUT_DATA / "predictions.parquet"
OFFSETS = T25.OFFSETS
START_ML = "2019-01-02"
IDENTITY_TOL = 1e-12
HYPOTHESES_SHA = "af771470eaab998f0f2152d1f2e3e4cf8e9f45af5875a7bba0f8d71642fe99c0"
WINDOWS = {
    "recent": ("2024-01-08", "2026-09-15"),
    "stress_ml": ("2019-01-02", "2023-08-31"),
    "full_ml": ("2019-01-02", "2026-09-15"),
    "A": ("2024-01-08", "2026-06-30"),
    "B": ("2026-07-01", "2026-09-15"),
}
V12_STRESS = ("2017-10-02", "2023-08-31")
DECIDING = ("recent", "stress_ml")
VOL_MATCHED_WINDOWS = ("full_ml", "recent", "stress_ml")
CAND_IDS = {"V14_M2": "m2", "V14_M3": "m3", "V14_M0M2": "m0m2", "V14_M0M3": "m0m3"}
PURE_ML = ("m2", "m3")
BLENDS = ("m0m2", "m0m3")
FAMILY_N = 19
PROJECT_N = 120
SERIES_COLS = ["gross", "cost", "borrow", "turnover", "spy", "hedge_size", "vix_scale", "net"]


# ---------------------------------------------------------------------------
# score source: a column of the predictions parquet as a v1.2 score source
# ---------------------------------------------------------------------------
class PredictionSource:
    """``src(t, state, universe)`` -> rank-normal of one prediction column on the universe members.

    The column is loaded once, date-indexed.  Members without a prediction stay NaN (rank_normal keeps
    NaN).  ``placebo_seed`` adds the within-date permutation of ``AlphaSource`` (same RNG seeding)."""

    def __init__(self, path: Path | str, column: str, placebo_seed: int | None = None) -> None:
        import pyarrow.parquet as pq

        tbl = pq.read_table(str(path), columns=["trade_date", "symbol", column])
        df = tbl.to_pandas(categories=["symbol"])
        dates = df["trade_date"].to_numpy().astype("datetime64[ns]")
        order = np.argsort(dates, kind="stable")
        self._dates = dates[order]
        self._codes = df["symbol"].cat.codes.to_numpy()[order]
        self._cats = df["symbol"].cat.categories
        self._vals = df[column].to_numpy("float64")[order]
        self.column = column
        self.missing_dates: list[str] = []
        self.rng = None
        if placebo_seed is not None:
            from scripts.run_book_v1_stage2 import PLACEBO_SEED_BASE

            self.rng = np.random.default_rng(PLACEBO_SEED_BASE + placebo_seed)

    def __call__(self, t: pd.Timestamp, state: object, universe: pd.Index) -> pd.Series:
        d = np.datetime64(pd.Timestamp(t).to_datetime64(), "ns")
        lo = int(np.searchsorted(self._dates, d, "left"))
        hi = int(np.searchsorted(self._dates, d, "right"))
        if hi == lo:
            self.missing_dates.append(str(pd.Timestamp(t).date()))
        s = pd.Series(self._vals[lo:hi], index=self._cats.take(self._codes[lo:hi]))
        s = s[~s.index.duplicated(keep="first")]
        out = op.rank_normal(s.reindex(universe))
        if self.rng is not None:
            from scripts.run_book_v1_stage2 import shuffle_scores

            out = shuffle_scores(out, self.rng)
        return out


# ---------------------------------------------------------------------------
# the v1.2 loop (copied from book_v12_account.strategy_pass: injected source, start argument,
# gross_exposure column; nothing else changed)
# ---------------------------------------------------------------------------
def restart_positions(
    dates: pd.DatetimeIndex, start: str, last_label: int, offset: int
) -> list[int]:
    """Decision positions of the v1.2 calendar (``pos % WEEK == offset``) from the first date >= start."""
    first = int(dates.searchsorted(pd.Timestamp(start)))
    return T25.decision_positions(len(dates), first, last_label, T25.WEEK, offset)


def strategy_pass_with_source(
    ctx: T25.Context,
    src,
    flag: str = "in_u3000",
    offset: int = 0,
    start: str = START_ML,
    limit: int | None = None,
) -> pd.DataFrame:
    px = ctx.px
    last_label = px.T - 3
    dec = restart_positions(px.dates, start, last_label, offset)
    w_state, h_state = np.zeros(px.N), 0.0
    rows: list[pd.DataFrame] = []
    for i, p in enumerate(dec):
        if limit is not None and i >= limit:
            break
        nxt = dec[i + 1] if i + 1 < len(dec) else last_label + 1
        length = nxt - p
        di = acct.decision_inputs(ctx, src, flag, p)
        if di is None:
            continue
        tt = acct.tranche_from_inputs(ctx, di)
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
    return df[[*SERIES_COLS[:-1], "gross_exposure", "net"]]


# ---------------------------------------------------------------------------
# small pure helpers (tested)
# ---------------------------------------------------------------------------
def vol_matched_diff(cand: pd.Series, base: pd.Series) -> pd.Series:
    """d_t = cand_t * (sd(base) / sd(cand)) - base_t, sd over the same (already sliced) window."""
    c, b = cand.align(base, join="inner")
    return c * (float(b.std(ddof=1)) / float(c.std(ddof=1))) - b


def count_offsets_improved(cand: list[float], base: list[float]) -> tuple[int, list[float]]:
    diffs = [float(a) - float(b) for a, b in zip(cand, base, strict=True)]
    return int(sum(d > 0 for d in diffs)), diffs


def hac_t(d: np.ndarray, lag: int = 5) -> dict:
    """Newey-West (Bartlett) t of the mean of ``d``; same formula as ``newey_west_t`` of the T-17 sweep."""
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


def eligibility(
    delta_recent: float,
    delta_stress: float,
    improved_recent: int,
    improved_stress: int,
    betas: dict[str, dict[str, float]],
    e5: bool,
) -> dict[str, bool]:
    e1 = bool(delta_recent >= 0.10 and delta_stress >= 0.10)
    e2 = bool(improved_recent >= 4 and improved_stress >= 4)
    e4 = bool(all(abs(betas[k][b]) <= 0.15 for k in DECIDING for b in ("beta_ols", "beta_dimson")))
    return {"E1": e1, "E2": e2, "E4": e4, "E5": bool(e5), "all": bool(e1 and e2 and e4 and e5)}


def select_candidate(
    eligible: list[str], recent: dict[str, float], stress: dict[str, float]
) -> str | None:
    """Highest recent offset-median net Sharpe; within 0.01 of the top, the higher stress_ml one."""
    if not eligible:
        return None
    top = max(recent[c] for c in eligible)
    close = [c for c in eligible if recent[c] >= top - 0.01]
    return max(close, key=lambda c: stress[c]) if len(close) > 1 else close[0]


def win_slice(df: pd.DataFrame, w: tuple[str, str]) -> pd.DataFrame:
    return df.loc[w[0] : w[1]]


def window_block(
    frames: list[pd.DataFrame], w: tuple[str, str], with_exposure: bool = True
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
    if with_exposure:
        out["gross_exposure_mean"] = float(
            np.mean([win_slice(f, w)["gross_exposure"].mean() for f in frames])
        )
    return out


# ---------------------------------------------------------------------------
# io
# ---------------------------------------------------------------------------
def s_path(name: str, o: int, base: Path = OUT_DATA) -> Path:
    return base / f"S_{name}_o{o}.parquet"


def jdump(path: Path, obj: object) -> None:
    path.write_text(json.dumps(obj, indent=1, default=float))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def mirror(path: Path, mirror_dir: Path | None) -> None:
    if mirror_dir is not None:
        mirror_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, mirror_dir / path.name)


def stage_a() -> dict:
    return json.loads((ITER / "stage_a.json").read_text())


# ---------------------------------------------------------------------------
# pass tasks (one decision loop = one task; run in-process or in a process pool)
# ---------------------------------------------------------------------------
_CTX: T25.Context | None = None


def _pass_task(
    name: str, o: int, limit: int | None, deadline: float | None
) -> tuple[str, int, pd.DataFrame | None, float, list[str]]:
    """``name`` B0r = AlphaSource M0 (make_source); any other name = column of predictions.parquet."""
    global _CTX
    if deadline is not None and time.time() > deadline:
        return name, o, None, 0.0, []
    t0 = time.time()
    if _CTX is None:
        _CTX = T25.Context()
    ctx = _CTX
    src = acct.make_source(ctx, "M0_U3000") if name == "B0r" else PredictionSource(PRED, name)
    df = strategy_pass_with_source(ctx, src, "in_u3000", o, START_ML, limit)
    missing = sorted(set(getattr(src, "missing_dates", [])))
    return name, o, df, time.time() - t0, missing


def run_tasks(
    tasks: list[tuple[str, int]], workers: int, limit: int | None, deadline: float | None, on_done
) -> None:
    """Run ``tasks`` (name, offset); ``on_done(name, o, df, secs, missing)`` is called in the parent."""
    if workers <= 1:
        for name, o in tasks:
            r = _pass_task(name, o, limit, deadline)
            if r[2] is not None:
                on_done(*r)
        return
    import multiprocessing as mp
    from concurrent.futures import ProcessPoolExecutor, as_completed

    with ProcessPoolExecutor(max_workers=workers, mp_context=mp.get_context("spawn")) as pool:
        futs = [pool.submit(_pass_task, name, o, limit, deadline) for name, o in tasks]
        for f in as_completed(futs):
            r = f.result()
            if r[2] is not None:
                on_done(*r)


# ---------------------------------------------------------------------------
# stage identity
# ---------------------------------------------------------------------------
def compare_identity(
    o: int, a: pd.DataFrame, b: pd.DataFrame, saved: pd.DataFrame, limit: int | None
) -> dict:
    first = a.index[0]
    saved = saved.loc[first:]
    if limit is not None:
        saved = saved.loc[a.index]
    index_equal = bool(a.index.equals(saved.index))
    diffs_r6: dict[str, float] = {}
    for c in ("gross", "borrow", "hedge_size", "vix_scale"):
        diffs_r6[c] = float((a[c] - saved[c]).abs().max()) if index_equal else float("nan")
    tail = a.index[1:]
    diffs_r6["cost_excl_first_decision"] = (
        float((a.loc[tail, "cost"] - saved.loc[tail, "cost"]).abs().max())
        if index_equal
        else float("nan")
    )
    other = (
        {c: float((a.loc[tail, c] - saved.loc[tail, c]).abs().max()) for c in ("spy", "turnover")}
        if index_equal
        else {}
    )
    first_cost = {
        "first_date": str(first.date()),
        "cost_mine": float(a["cost"].iloc[0]),
        "cost_r6": float(saved["cost"].iloc[0]) if index_equal else None,
    }
    b_equal = bool(a.index.equals(b.index))
    diffs_ab = {c: float((a[c] - b[c]).abs().max()) if b_equal else float("nan") for c in a.columns}
    w1 = max(diffs_r6.values())
    w2 = max(diffs_ab.values())
    ok1 = bool(index_equal and math.isfinite(w1) and w1 <= IDENTITY_TOL)
    ok2 = bool(b_equal and math.isfinite(w2) and w2 <= IDENTITY_TOL)
    return {
        "rows_a": len(a),
        "rows_b": len(b),
        "rows_r6_restarted": len(saved),
        "index_equal_r6": index_equal,
        "index_equal_a_b": b_equal,
        "max_abs_diff_a_vs_r6": diffs_r6,
        "max_abs_diff_a_vs_r6_other_columns_excl_first": other,
        "first_decision_cost": first_cost,
        "max_abs_diff_b_vs_a": diffs_ab,
        "worst_a_vs_r6": w1,
        "worst_b_vs_a": w2,
        "check_a_vs_r6": ok1,
        "check_b_vs_a": ok2,
        "pass": bool(ok1 and ok2),
    }


def run_identity(
    mirror_dir: Path | None,
    limit: int | None = None,
    workers: int = 1,
    deadline_min: float | None = None,
) -> dict:
    OUT_DATA.mkdir(parents=True, exist_ok=True)
    deadline = None if deadline_min is None else time.time() + 60.0 * deadline_min
    res: dict[tuple[str, int], pd.DataFrame] = {}
    secs: dict[tuple[str, int], float] = {}
    missing: set[str] = set()

    def on_done(name: str, o: int, df: pd.DataFrame, s: float, miss: list[str]) -> None:
        res[(name, o)] = df
        secs[(name, o)] = round(s, 1)
        missing.update(miss)
        if name == "B0r":
            df.to_parquet(s_path("B0r", o))
            mirror(s_path("B0r", o), mirror_dir)
        print("identity pass", name, "o", o, f"{s:.1f}s", flush=True)

    tasks = [(n, o) for o in OFFSETS for n in ("B0r", "m0")]
    run_tasks(tasks, workers, limit, deadline, on_done)
    out: dict = {
        "tolerance": IDENTITY_TOL,
        "start": START_ML,
        "cases": {},
        "pass": True,
        "limit": limit,
        "workers": workers,
        "note": "a = AlphaSource M0 (make_source M0_U3000, saved as S_B0r); b = PredictionSource(predictions.parquet, m0)",
    }
    for o in OFFSETS:
        if ("B0r", o) not in res or ("m0", o) not in res:
            out["cases"][f"o{o}"] = {"pass": False, "error": "pass not finished (deadline)"}
            out["pass"] = False
            continue
        saved = pd.read_parquet(T25.RAW / f"R6_M0_U3000_o{o}.parquet")
        case = compare_identity(o, res[("B0r", o)], res[("m0", o)], saved, limit)
        case["seconds_a_b"] = [secs[("B0r", o)], secs[("m0", o)]]
        out["cases"][f"o{o}"] = case
        out["pass"] = bool(out["pass"] and case["pass"])
        print("identity offset", o, case["worst_a_vs_r6"], case["worst_b_vs_a"], flush=True)
    out["missing_prediction_dates"] = sorted(missing)
    out["pass"] = bool(out["pass"] and not out["missing_prediction_dates"])
    jdump(ITER / "identity.json", out)
    mirror(ITER / "identity.json", mirror_dir)
    return out


# ---------------------------------------------------------------------------
# stage passes
# ---------------------------------------------------------------------------
def run_passes(
    mirror_dir: Path | None,
    deadline_min: float | None,
    limit: int | None = None,
    candidate: str | None = None,
    workers: int = 1,
) -> dict:
    sa = stage_a()
    if sa["mechanical_status_stage_a"] != "stage_b_authorized":
        raise SystemExit("blocked: Stage A did not authorize Stage B")
    survivors = list(sa["stage_a_survivors"])
    if candidate is not None:
        if candidate not in survivors:
            raise SystemExit(f"blocked: {candidate} did not survive Stage A")
        survivors = [candidate]
    ident = json.loads((ITER / "identity.json").read_text())
    if not ident.get("pass"):
        raise SystemExit("blocked: identity.json pass is false")
    deadline = None if deadline_min is None else time.time() + 60.0 * deadline_min
    tasks: list[tuple[str, int]] = [(c, o) for c in survivors for o in OFFSETS]
    tasks += [("B0r", o) for o in OFFSETS if not s_path("B0r", o).exists()]
    done: list[str] = []

    def on_done(name: str, o: int, df: pd.DataFrame, s: float, miss: list[str]) -> None:
        df.to_parquet(s_path(name, o))
        mirror(s_path(name, o), mirror_dir)
        done.append(f"{name}_o{o}")
        print(f"pass {name} o{o} rows {len(df)} {s:.1f}s missing_dates={len(miss)}", flush=True)

    run_tasks(tasks, workers, limit, deadline, on_done)
    unfinished = [f"{n}_o{o}" for n, o in tasks if f"{n}_o{o}" not in done]
    return {
        "done": sorted(done),
        "unfinished": unfinished,
        "survivors": survivors,
        "stopped_by_deadline": bool(unfinished),
    }


# ---------------------------------------------------------------------------
# stage evaluate (parquets only)
# ---------------------------------------------------------------------------
def load_frames(name: str) -> list[pd.DataFrame]:
    return [pd.read_parquet(s_path(name, o)) for o in OFFSETS]


def run_evaluate() -> dict:
    sa = stage_a()
    survivors = list(sa["stage_a_survivors"])
    ident = json.loads((ITER / "identity.json").read_text())
    assert ident["pass"], "identity.json pass is false"
    e5 = bool(sa["permutation_check"]["pass"])
    b0 = load_frames("B0r")
    b0_blend = T25.blend(b0)
    r6 = [pd.read_parquet(T25.RAW / f"R6_M0_U3000_o{o}.parquet") for o in OFFSETS]
    res: dict = {
        "contract": {
            "hypotheses_sha256": sha256(ITER / "hypotheses.md"),
            "expected_sha256": HYPOTHESES_SHA,
            "unchanged": sha256(ITER / "hypotheses.md") == HYPOTHESES_SHA,
        },
        "identity": {
            "pass": ident["pass"],
            "tolerance": ident["tolerance"],
            "worst_a_vs_r6": max(v["worst_a_vs_r6"] for v in ident["cases"].values()),
            "worst_b_vs_a": max(v["worst_b_vs_a"] for v in ident["cases"].values()),
            "offsets": list(ident["cases"]),
        },
        "stage_a_ref": {
            "survivors": survivors,
            "status": sa["mechanical_status_stage_a"],
            "permutation_check_pass": e5,
        },
        "b0r": {"windows": {k: window_block(b0, w) for k, w in WINDOWS.items()}},
        "b0r_v12_stress_reference_2017_10_02_2023_08_31": {
            "note": "B0r path on the v1.2 stress window, from the R6 parquets; reported, not used.",
            "window": list(V12_STRESS),
            "block": window_block(r6, V12_STRESS, with_exposure=False),
        },
        "candidates": {},
    }
    for name in survivors:
        frames = load_frames(name)
        for o in range(len(OFFSETS)):
            assert frames[o].index.equals(b0[o].index), (name, o)
        blend = T25.blend(frames)
        blk: dict = {"windows": {}, "delta_vs_b0r": {}, "vol_matched_nw_t": {}, "corr_with_b0r": {}}
        for k, w in WINDOWS.items():
            wb = window_block(frames, w)
            ref = res["b0r"]["windows"][k]
            n_imp, diffs = count_offsets_improved(
                wb["net_sharpe_by_offset"], ref["net_sharpe_by_offset"]
            )
            wb["delta_offset_median"] = (
                wb["net_sharpe_offset_median"] - ref["net_sharpe_offset_median"]
            )
            wb["offsets_improved"] = n_imp
            blk["windows"][k] = wb
            blk["delta_vs_b0r"][k] = {
                "delta_offset_median": wb["delta_offset_median"],
                "offsets_improved": n_imp,
                "net_sharpe_diff_by_offset": diffs,
                "delta_gross_sharpe_offset_median": wb["gross_sharpe_offset_median"]
                - ref["gross_sharpe_offset_median"],
                "delta_cost_bp_yr": wb["cost_bp_yr"] - ref["cost_bp_yr"],
                "delta_turnover_one_sided_ann": wb["turnover_one_sided_ann"]
                - ref["turnover_one_sided_ann"],
            }
            c_net, b_net = win_slice(blend, w)["net"], win_slice(b0_blend, w)["net"]
            blk["corr_with_b0r"][k] = float(c_net.corr(b_net))
            if k in VOL_MATCHED_WINDOWS:
                d = vol_matched_diff(c_net, b_net)
                blk["vol_matched_nw_t"][k] = hac_t(d.to_numpy(), 5)
        rc, st = blk["windows"]["recent"], blk["windows"]["stress_ml"]
        blk["eligibility"] = eligibility(
            rc["delta_offset_median"],
            st["delta_offset_median"],
            rc["offsets_improved"],
            st["offsets_improved"],
            {k: blk["windows"][k] for k in DECIDING},
            e5,
        )
        res["candidates"][name] = blk
    elig = [c for c in survivors if res["candidates"][c]["eligibility"]["all"]]
    rec = {
        c: res["candidates"][c]["windows"]["recent"]["net_sharpe_offset_median"] for c in survivors
    }
    stl = {
        c: res["candidates"][c]["windows"]["stress_ml"]["net_sharpe_offset_median"]
        for c in survivors
    }
    res["eligible_candidates"] = elig
    res["selected_candidate"] = select_candidate(elig, rec, stl)

    def beats(c: str) -> bool:
        if c not in res["candidates"]:
            return False
        return bool(
            all(res["candidates"][c]["windows"][k]["delta_offset_median"] > 0 for k in DECIDING)
        )

    res["ml_contribution_pass"] = bool(any(beats(c) for c in PURE_ML))
    res["ml_contribution_detail"] = {
        c: (
            "stopped at Stage A (not run); counts as not passing"
            if c not in survivors
            else {k: res["candidates"][c]["windows"][k]["delta_offset_median"] for k in DECIDING}
        )
        for c in PURE_ML
    }
    res["ml_additive"] = bool(any(beats(c) for c in BLENDS))
    res["ml_additive_detail"] = {
        c: (
            "stopped at Stage A (not run); counts as not passing"
            if c not in survivors
            else {k: res["candidates"][c]["windows"][k]["delta_offset_median"] for k in DECIDING}
        )
        for c in BLENDS
    }
    res["mechanical_status"] = (
        "eligible_candidate_selected"
        if res["selected_candidate"]
        else "no_candidate_eligible_keep_m0"
    )
    res["implementation_choices"] = [
        "Loop = book_v12_account.strategy_pass copied with an injected score source and a start argument (2019-01-02); decision positions keep the v1.2 calendar pos % 5 == offset; gross_exposure = sum|tt.w| at the refresh carried through the block.",
        "B0r = AlphaSource M0 (make_source M0_U3000) through the same loop; saved by the identity stage (S_B0r_o<k>.parquet) and reused by passes; identity (b) PredictionSource(m0) must equal it at 1e-12.",
        "PredictionSource = rank_normal of the predictions.parquet column reindexed on the U3000 members; members without a prediction stay NaN.",
        "identity and passes ran on Modal (4 cpu, 8 GiB, 90 min), evaluate runs locally from parquets; no rule, window, candidate or offset changed.",
        "vol-matched paired t: d_t = net_cand * sd(B0r)/sd(cand) - net_B0r on the blended daily net returns, sd(ddof=1) over the same window, Newey-West Bartlett lag 5 (same formula as run_t20260930_17_model_family_sweep.newey_west_t).",
        "Only Stage A survivors were run; V14_M2 and V14_M3 (pure ML) stopped at Stage A and count as not passing for ml_contribution_pass.",
        "Blended series use the intersection of the 5 offsets' label dates (an offset's first decision date >= 2019-01-02 can be up to 4 sessions later).",
    ]
    return res


def fmt(x: float | None, nd: int = 3) -> str:
    return "n/a" if x is None or not math.isfinite(x) else f"{x:.{nd}f}"


def write_outputs(res: dict) -> None:
    jdump(ITER / "results.json", res)
    sa = stage_a()
    rows = []
    for cid, col in CAND_IDS.items():
        row: dict = {"candidate_id": cid, "column": col, "family_n": FAMILY_N}
        sc = sa["scores"][col]["simplified_gross_sharpe"]
        m0 = sa["scores"]["m0"]["simplified_gross_sharpe"]
        row["stage_a_gross_offset_median"] = {
            k: sc[k]["offset_median"] for k in ("recent", "stress_ml")
        }
        row["stage_a_m0_gross_offset_median"] = {
            k: m0[k]["offset_median"] for k in ("recent", "stress_ml")
        }
        if col in res["candidates"]:
            c = res["candidates"][col]
            row["stage"] = "B"
            row["net_sharpe_offset_median_recent"] = c["windows"]["recent"][
                "net_sharpe_offset_median"
            ]
            row["net_sharpe_offset_median_stress_ml"] = c["windows"]["stress_ml"][
                "net_sharpe_offset_median"
            ]
            row["delta_offset_median_recent"] = c["windows"]["recent"]["delta_offset_median"]
            row["delta_offset_median_stress_ml"] = c["windows"]["stress_ml"]["delta_offset_median"]
            row["eligibility"] = c["eligibility"]
            row["selected"] = res["selected_candidate"] == col
            row["source"] = "results.json"
        else:
            row["stage"] = "A"
            row["stopped"] = "stage_a_gate: simplified gross Sharpe not above M0 in both windows"
            row["eligibility"] = None
            row["selected"] = False
            row["source"] = "stage_a.json"
        rows.append(row)
    jdump(
        ITER / "trial-ledger.json",
        {
            "iteration": "t20261004_book_v14_ml",
            "family_n": FAMILY_N,
            "project_n": PROJECT_N,
            "trials": rows,
            "baseline": "B0r (not a trial)",
        },
    )
    lines = [
        "# t20261004_book_v14_ml Stage B (T-20261004-03)",
        "",
        f"mechanical_status: **{res['mechanical_status']}**; selected_candidate: {res['selected_candidate']}; "
        f"ml_contribution_pass: {res['ml_contribution_pass']}; ml_additive: {res['ml_additive']}.",
        f"Contract hypotheses.md sha256 unchanged: {res['contract']['unchanged']}. "
        f"Identity pass: {res['identity']['pass']} (worst a-vs-R6 {res['identity']['worst_a_vs_r6']:.2e}, b-vs-a {res['identity']['worst_b_vs_a']:.2e}).",
        f"Stage A survivors: {', '.join(res['stage_a_ref']['survivors'])}; E5 (permutation check) {res['stage_a_ref']['permutation_check_pass']}.",
        "",
        "Offset-median net Sharpe (blend net Sharpe in brackets); B0r = M0 through the same loop from 2019-01-02.",
        "",
        "| series | recent | stress_ml | full_ml | A | B |",
        "|---|---|---|---|---|---|",
    ]

    def cell(w: dict) -> str:
        return f"{fmt(w['net_sharpe_offset_median'])} ({fmt(w['net_sharpe_blend'])})"

    lines.append("| B0r | " + " | ".join(cell(res["b0r"]["windows"][k]) for k in WINDOWS) + " |")
    for c, blk in res["candidates"].items():
        lines.append(f"| {c} | " + " | ".join(cell(blk["windows"][k]) for k in WINDOWS) + " |")
    lines += [
        "",
        "| candidate | delta recent | delta stress_ml | improved r/s | beta ols r/s | beta dimson r/s | 2x-cost med r/s | E1 E2 E4 E5 | all |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for c, blk in res["candidates"].items():
        r, s = blk["windows"]["recent"], blk["windows"]["stress_ml"]
        e = blk["eligibility"]
        lines.append(
            f"| {c} | {fmt(r['delta_offset_median'])} | {fmt(s['delta_offset_median'])} | "
            f"{r['offsets_improved']}/{s['offsets_improved']} | {fmt(r['beta_ols'])}/{fmt(s['beta_ols'])} | "
            f"{fmt(r['beta_dimson'])}/{fmt(s['beta_dimson'])} | "
            f"{fmt(r['net_sharpe_2x_cost_offset_median'])}/{fmt(s['net_sharpe_2x_cost_offset_median'])} | "
            f"{e['E1']} {e['E2']} {e['E4']} {e['E5']} | {e['all']} |"
        )
    lines += [
        "",
        "Vol-matched paired NW t (lag 5) and correlation with B0r (daily blended net):",
        "",
        "| candidate | t full_ml | t recent | t stress_ml | corr recent | corr stress_ml | corr full_ml |",
        "|---|---|---|---|---|---|---|",
    ]
    for c, blk in res["candidates"].items():
        t = blk["vol_matched_nw_t"]
        cr = blk["corr_with_b0r"]
        lines.append(
            f"| {c} | {fmt(t['full_ml']['t'], 2)} | {fmt(t['recent']['t'], 2)} | {fmt(t['stress_ml']['t'], 2)} | "
            f"{fmt(cr['recent'])} | {fmt(cr['stress_ml'])} | {fmt(cr['full_ml'])} |"
        )
    lines += [
        "",
        "Cost, turnover, exposure (recent / stress_ml):",
        "",
        "| series | cost bp/yr | one-sided turnover/yr | mean gross exposure |",
        "|---|---|---|---|",
    ]
    for name, blk in [("B0r", res["b0r"]), *res["candidates"].items()]:
        r, s = blk["windows"]["recent"], blk["windows"]["stress_ml"]
        lines.append(
            f"| {name} | {fmt(r['cost_bp_yr'], 1)}/{fmt(s['cost_bp_yr'], 1)} | "
            f"{fmt(r['turnover_one_sided_ann'], 2)}/{fmt(s['turnover_one_sided_ann'], 2)} | "
            f"{fmt(r['gross_exposure_mean'], 2)}/{fmt(s['gross_exposure_mean'], 2)} |"
        )
    ref = res["b0r_v12_stress_reference_2017_10_02_2023_08_31"]["block"]
    lines += [
        "",
        f"Reference (reported, not used): B0r path on the v1.2 stress window 2017-10-02..2023-08-31 from the R6 parquets: offset-median net Sharpe {fmt(ref['net_sharpe_offset_median'])}, blend {fmt(ref['net_sharpe_blend'])}.",
        f"ml_contribution_pass detail: {json.dumps(res['ml_contribution_detail'], default=float)}",
        f"ml_additive detail: {json.dumps(res['ml_additive_detail'], default=float)}",
        "",
        "Source: results.json (this folder); series in data/research/book_v14/S_*_o*.parquet (not committed).",
    ]
    (ITER / "report.md").write_text("\n".join(lines) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True, choices=["identity", "passes", "evaluate"])
    ap.add_argument("--candidate", default=None, help="passes: only this Stage A survivor")
    ap.add_argument("--mirror-dir", default=None)
    ap.add_argument("--deadline-min", type=float, default=None)
    ap.add_argument("--workers", type=int, default=1, help="process pool size (1 = in-process)")
    ap.add_argument("--limit", type=int, default=None, help="smoke test: first N decisions")
    ns = ap.parse_args()
    mdir = Path(ns.mirror_dir) if ns.mirror_dir else None
    if mdir is not None and not mdir.is_absolute():
        mdir = ROOT / mdir
    if ns.stage == "identity":
        r = run_identity(mdir, ns.limit, ns.workers, ns.deadline_min)
        print("identity pass:", r["pass"])
        if not r["pass"]:
            sys.exit(1)
    elif ns.stage == "passes":
        r = run_passes(mdir, ns.deadline_min, ns.limit, ns.candidate, ns.workers)
        print(json.dumps(r))
        if r["stopped_by_deadline"]:
            sys.exit(3)
    else:
        res = run_evaluate()
        write_outputs(res)
        print(res["mechanical_status"], res["selected_candidate"])


if __name__ == "__main__":
    main()
