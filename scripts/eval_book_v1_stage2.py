# ruff: noqa: E501, B023
"""Stage 2a evaluation of ``t20261001_book_v1`` (task T-20261001-13).

Turns the 54 raw paths written by ``scripts/run_book_v1_stage2.py`` (T-20261001-08) into every number
required by preregistration sections 5 and 7 and amendment A1 sections 1, 6 and 7, and writes
``results.json`` and ``report.md`` into the iteration directory.  Mechanical booleans only: no verdict.

All metric maths is :mod:`open_composer.research.equity_book.evaluate` (frozen, A1-bound); this script
only reads the raw files, applies the frozen functions window by window and takes medians over the
five rebalance offsets.  It never reruns a backtest.

Usage::

    scripts/run_capped.sh --mem 1.8G -- uv run python scripts/eval_book_v1_stage2.py --stage 2a
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from open_composer.research.equity_book import evaluate as ev  # noqa: E402

ITER_ID = "t20261001_book_v1"
ITER_DIR = ROOT / "reports/research/iterations" / ITER_ID
QUEUE = ROOT / "reports/research/control/autonomous-queue.md"
PHASES = ROOT / "data/research/equity_book/regimes/phases.json"
RISK_META = ROOT / "data/research/equity_book/risk/meta.json"
ETF_DAILY = ROOT / "data/research/equity_book/etf_daily.parquet"

WINDOWS = ev.WINDOWS
JUDGED = ("stress", "anchor")
FULL = ("2017-10-02", "2026-09-17")
BETA_BOUND = 0.15
FAILURE_MEDIAN_MAX = 0.02
FAILURE_ENGINEERING = 0.05
SCS_SHARE_FLAG = 0.01
K2_EDGE = ev.K2_EDGE
K2_EDGE_STRONG = ev.K2_EDGE_STRONG
COST_COLS = ("cost_spread", "cost_impact", "cost_fees", "cost_borrow", "cost_margin")
REPLAYS = ("net_cost2x", "net_fix10", "net_fix20", "net_delist30")
REPLAY_KEY = {
    "net_cost2x": "cost2x",
    "net_fix10": "fix10",
    "net_fix20": "fix20",
    "net_delist30": "delist30",
}
STRESS_PERIODS = {
    "2020-03": ("2020-03-01", "2020-03-31"),
    "2020-11": ("2020-11-01", "2020-11-30"),
    "2025-01-27": ("2025-01-27", "2025-01-27"),
    "2025-04": ("2025-04-01", "2025-04-30"),
    "2025-06..07": ("2025-06-01", "2025-07-31"),
    "2025-10": ("2025-10-01", "2025-10-31"),
    "2026-06..08": ("2026-06-01", "2026-08-31"),
}
THEMES = (
    "earnings",
    "insider",
    "investment",
    "low_risk",
    "momentum",
    "quality",
    "seasonality",
    "short_info",
    "value",
)
TIMING_VARIANTS = ("M0_A", "M0_B", "M0_C")
VARIANTS = ("M0_A", "M0_B", "M0_C", "M1_A", "M1_B", "M1_C")
CHECK_FIELDS = (
    "k1",
    "k2_frozen",
    "k2_cash_aligned",
    "k2_strong",
    "cond1",
    "beta_ok",
    "failure_ok",
    "cost2x_ok",
    "anchor_sharpe_ge_1_19",
    "watch_recent_pre_placebo",
    "needs_placebo",
)


# ------------------------------------------------------------------ pure helpers (unit tested)


def dimson_beta(net: pd.Series, spy: pd.Series, window: tuple[str, str]) -> float:
    """Dimson beta: OLS (with intercept) of daily ``net`` on SPY_t and SPY_{t-1} in ``window``; the
    two slopes are summed.  ``spy`` is the full-calendar SPY return series (lag taken on it)."""
    a, b = window
    sub = net[(net.index >= a) & (net.index <= b)].dropna()
    if len(sub) < 20:
        return float("nan")
    x0 = spy.reindex(sub.index).fillna(0.0).to_numpy()
    x1 = spy.shift(1).reindex(sub.index).fillna(0.0).to_numpy()
    design = np.column_stack([np.ones(len(sub)), x0, x1])
    coef, *_ = np.linalg.lstsq(design, sub.to_numpy(dtype="float64"), rcond=None)
    return float(coef[1] + coef[2])


def load_bil_shy(path: Path = ETF_DAILY) -> tuple[pd.Series, pd.Series]:
    """Daily close-to-close BIL and SHY returns, built exactly as ``evaluate.load_rf_spy``."""
    etf = pd.read_parquet(path, columns=["trade_date", "symbol", "close"])
    c = etf.pivot(index="trade_date", columns="symbol", values="close").sort_index()
    bil = (c["BIL"] / c["BIL"].shift(1) - 1.0).fillna(0.0)
    shy = (c["SHY"] / c["SHY"].shift(1) - 1.0).fillna(0.0)
    return bil, shy


def cash_aligned(net: pd.Series, bil: pd.Series, shy: pd.Series) -> pd.Series:
    """Cash-aligned net series of preregistration section 5: ``net - BIL + SHY``."""
    return net - bil.reindex(net.index).fillna(0.0) + shy.reindex(net.index).fillna(0.0)


def median_nested(items: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Median over a list of identically shaped nested dicts, numeric leaves only (bool, str and
    list leaves are skipped).  Any non-finite value in a leaf makes that leaf NaN (nothing is
    silently dropped).  The median itself is ``evaluate.median_over_offsets``."""
    out: dict[str, Any] = {}
    first = items[0]
    for key, val in first.items():
        if isinstance(val, Mapping):
            sub = [it[key] for it in items if isinstance(it.get(key), Mapping)]
            if len(sub) == len(items):
                out[key] = median_nested(sub)
        elif isinstance(val, (int, float, np.integer, np.floating)) and not isinstance(val, bool):
            vals = [it.get(key) for it in items]
            if all(isinstance(v, (int, float, np.integer, np.floating)) for v in vals):
                arr = [float(v) for v in vals]
                if all(math.isfinite(v) for v in arr):
                    out[key] = ev.median_over_offsets(dict(enumerate(arr)))
                else:
                    out[key] = float("nan")
    return out


def _ge(x: Any, thr: float) -> bool:
    return bool(x is not None and math.isfinite(x) and x >= thr)


def _gt(x: Any, thr: float) -> bool:
    return bool(x is not None and math.isfinite(x) and x > thr)


def _within(x: Any, bound: float) -> bool:
    return bool(x is not None and math.isfinite(x) and -bound <= x <= bound)


def variant_checks(med: Mapping[str, Any]) -> dict[str, bool]:
    """Mechanical conditions of one variant from the offset-median block ``med``.

    ``med`` holds: ``net`` and ``cost2x`` (window -> metrics), ``k2_frozen`` / ``k2_cash_aligned``
    (``edge`` -> window -> value), ``beta`` (``daily`` / ``dimson`` -> window -> value) and
    ``failure`` (``failure_rate``).  Every judgement is on these medians, never a vote over offsets.
    """
    net, c2 = med["net"], med["cost2x"]
    k1 = bool(ev.k1_check(net, c2)["pass"])
    edges_f = med["k2_frozen"]["edge"]
    edges_c = med["k2_cash_aligned"]["edge"]
    k2_frozen = all(_ge(edges_f.get(w), K2_EDGE) for w in JUDGED)
    k2_ca = all(_ge(edges_c.get(w), K2_EDGE) for w in JUDGED)
    k2_strong = all(_ge(edges_f.get(w), K2_EDGE_STRONG) for w in JUDGED) and all(
        _ge(edges_c.get(w), K2_EDGE_STRONG) for w in JUDGED
    )
    cond1 = k1 or (k2_frozen and k2_ca)
    beta_d, beta_m = med["beta"]["daily"], med["beta"]["dimson"]
    beta_ok = all(
        _within(beta_d.get(w), BETA_BOUND) and _within(beta_m.get(w), BETA_BOUND) for w in JUDGED
    )
    failure_ok = bool(
        med["failure"]["failure_rate"] is not None
        and math.isfinite(med["failure"]["failure_rate"])
        and med["failure"]["failure_rate"] < FAILURE_MEDIAN_MAX
    )
    cost2x_ok = all(_gt(c2[w].get("ann_excess_return"), 0.0) for w in JUDGED)
    anchor_ge = _ge(net["anchor"].get("sharpe"), ev.K1_ANCHOR_SHARPE)
    watch = (
        anchor_ge
        and _gt(c2["anchor"].get("ann_excess_return"), 0.0)
        and _within(beta_d.get("anchor"), BETA_BOUND)
        and _within(beta_m.get("anchor"), BETA_BOUND)
        and failure_ok
    )
    return {
        "k1": k1,
        "k2_frozen": k2_frozen,
        "k2_cash_aligned": k2_ca,
        "k2_strong": k2_strong,
        "cond1": cond1,
        "beta_ok": beta_ok,
        "failure_ok": failure_ok,
        "cost2x_ok": cost2x_ok,
        "anchor_sharpe_ge_1_19": anchor_ge,
        "watch_recent_pre_placebo": bool(watch),
        "needs_placebo": needs_placebo(cond1, anchor_ge),
    }


def needs_placebo(cond1: bool, anchor_sharpe_ge_1_19: bool) -> bool:
    """A1 section 6: placebo for variants that pass condition (1) or have anchor median >= 1.19."""
    return bool(cond1 or anchor_sharpe_ge_1_19)


def order_placebo_needed(variants: Mapping[str, Mapping[str, Any]]) -> list[str]:
    """Variants needing a placebo: cond1 first, then anchor median net Sharpe descending."""
    rows = []
    for vid, v in variants.items():
        ck = v["checks"]
        if not ck["needs_placebo"]:
            continue
        s = v["median"]["net"]["anchor"].get("sharpe")
        rows.append((vid, bool(ck["cond1"]), float(s) if s is not None else float("-inf")))
    rows.sort(key=lambda r: (not r[1], -r[2]))
    return [r[0] for r in rows]


def period_stats(net: pd.Series, rf: pd.Series, a: str, b: str) -> dict[str, Any]:
    """Sessions, compounded return and annualised Sharpe (vs BIL) of ``net`` in ``[a, b]``.  Uses
    ``evaluate.window_metrics`` when the window has >= 20 sessions; shorter windows fall back to the
    same formula (``short_sample`` true)."""
    sub = net[(net.index >= a) & (net.index <= b)].dropna()
    n = len(sub)
    out: dict[str, Any] = {
        "sessions": n,
        "cum_return": float((1.0 + sub).prod() - 1.0) if n else None,
    }
    if n >= 20:
        spy_dummy = pd.Series(0.0, index=sub.index)
        m = ev.window_metrics(net, rf, spy_dummy, (a, b))
        out["sharpe"] = m["sharpe"]
        out["short_sample"] = False
    elif n >= 2:
        ex = sub - rf.reindex(sub.index).fillna(0.0)
        sd = float(ex.std(ddof=1))
        out["sharpe"] = float(ex.mean() / sd * math.sqrt(ev.TRADING_DAYS)) if sd > 0 else None
        out["short_sample"] = True
    else:
        out["sharpe"] = None
        out["short_sample"] = True
    return out


def timing_flag(close_gross: float, open_gross: float) -> bool:
    """A1 section 1: open gross Sharpe > 0 and close gross Sharpe < 0.5 x open gross Sharpe."""
    return bool(open_gross > 0 and close_gross < 0.5 * open_gross)


def clean(obj: Any) -> Any:
    """JSON-safe copy: numpy scalars to Python, NaN/inf to None, Timestamps to ISO strings."""
    if isinstance(obj, Mapping):
        return {str(k): clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean(v) for v in obj]
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (float, np.floating)):
        v = float(obj)
        return v if math.isfinite(v) else None
    if isinstance(obj, pd.Timestamp):
        return obj.strftime("%Y-%m-%d")
    return obj


# ------------------------------------------------------------------ step 0


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def queue_status(task: str) -> str:
    """Status line of ``task`` in the queue (only the block of that task is looked at)."""
    inside = False
    for line in QUEUE.read_text().splitlines():
        if line.startswith("### "):
            inside = line.startswith(f"### {task}")
            continue
        if inside and line.startswith("- status:"):
            return line[len("- status:") :].strip()
    return ""


def precondition() -> dict[str, Any]:
    manifest = json.loads((ITER_DIR / "stage2a-manifest.json").read_text())
    status = queue_status("T-20261001-08")
    paths = manifest["paths"]
    binding_manifest = bool(
        manifest.get("all_binding_true")
        and len(paths) == 54
        and all(p["binding_all_true"] and all(p["binding_match"].values()) for p in paths.values())
    )
    # recompute the cached files' hashes against the manifest, and the bound code against meta
    files_ok = True
    bad_files: list[str] = []
    binding_now_ok = True
    bad_binding: list[str] = []
    cur_sha: dict[str, str] = {}
    for pid, p in paths.items():
        for name, info in p["files"].items():
            f = ROOT / info["path"]
            if not f.exists() or sha256(f) != info["sha256"]:
                files_ok = False
                bad_files.append(f"{pid}/{name}")
        meta = json.loads((ROOT / p["dir"] / "meta.json").read_text())
        for rel, want in meta["binding_sha256"].items():
            if rel not in cur_sha:
                cur_sha[rel] = sha256(ROOT / rel)
            if cur_sha[rel] != want:
                binding_now_ok = False
                bad_binding.append(f"{pid}:{rel}")
    return {
        "queue_t08_status": status,
        "queue_t08_done": status.startswith("done"),
        "manifest_n_paths": len(paths),
        "manifest_binding_all_true": binding_manifest,
        "cached_files_match_manifest": files_ok,
        "bad_files": bad_files[:10],
        "bound_code_matches_meta_now": binding_now_ok,
        "bad_binding": bad_binding[:10],
        "manifest": manifest,
    }


# ------------------------------------------------------------------ per path


def _window_costs_bp(daily: pd.DataFrame, window: tuple[str, str]) -> dict[str, float]:
    a, b = window
    d = daily[(daily.index >= a) & (daily.index <= b)]
    n = len(d)
    if n == 0:
        return {}
    out = {c.replace("cost_", ""): float(d[c].sum() / n * ev.TRADING_DAYS * 1e4) for c in COST_COLS}
    out["total"] = float(sum(out.values()))
    return out


def _exposure_summary(rec: pd.DataFrame, factors: list[str], groups: list[str], styles: list[str]):
    if len(rec) == 0:
        return {"n_records": 0}
    n_failed = int(rec["exposures_target"].isna().sum())  # failed rebalances carry no target
    rec = rec[rec["exposures_target"].notna()]
    if len(rec) == 0:
        return {"n_records": 0, "n_failed_records": n_failed}
    arr = np.array([json.loads(x) for x in rec["exposures_target"]], dtype="float64")
    n_g = len(groups)
    market = arr[:, 0]
    sect = arr[:, 1 : 1 + n_g]
    sty = arr[:, 1 + n_g :]
    assert factors[0] == "market" and sty.shape[1] == len(styles)
    g_max = np.abs(sect).max(axis=0)
    out: dict[str, Any] = {
        "n_records": int(len(rec)),
        "n_failed_records": n_failed,
        "market": {"mean": float(market.mean()), "max_abs": float(np.abs(market).max())},
        "sector": {
            "mean_abs": float(np.abs(sect).mean()),
            "max_abs": float(np.abs(sect).max()),
            "max_abs_group": groups[int(g_max.argmax())],
        },
        "styles": {
            s: {"mean": float(sty[:, i].mean()), "max_abs": float(np.abs(sty[:, i]).max())}
            for i, s in enumerate(styles)
        },
        "ex_ante_vol": {
            "mean": float(rec["vol_target"].mean()),
            "max": float(rec["vol_target"].max()),
        },
        "predicted_beta": {
            "mean": float(rec["beta_target"].mean()),
            "min": float(rec["beta_target"].min()),
            "max": float(rec["beta_target"].max()),
            "max_abs": float(rec["beta_target"].abs().max()),
        },
        "forced_exits": int(rec["forced_exits"].sum()),
    }
    return out


def failure_stats(meta: Mapping[str, Any]) -> dict[str, Any]:
    n = int(meta["n_rebalances"])
    rescued = dict(meta.get("rescued_by_step", {}))
    return {
        "n_rebalances": n,
        "n_failed_final": int(meta["n_failed_final"]),
        "failure_rate": meta["n_failed_final"] / n if n else float("nan"),
        "n_failed_first_attempt": int(meta["n_failed_first_attempt"]),
        "first_attempt_failure_rate": meta["n_failed_first_attempt"] / n if n else float("nan"),
        "rescued_by_step": rescued,
        "scs_rescue_share_of_solves": rescued.get("scs", 0) / n if n else float("nan"),
        "failed_by_status": dict(meta.get("failed_by_status", {})),
        "engineering_problem_gt_5pct": bool(n and meta["n_failed_final"] / n > FAILURE_ENGINEERING),
    }


class Context:
    def __init__(self) -> None:
        self.rf, self.spy = ev.load_rf_spy()
        self.bil, self.shy = load_bil_shy()
        assert np.allclose(self.bil.to_numpy(), self.rf.to_numpy()), "BIL series differs from rf"
        self.s3 = ev.load_s3_context()
        meta = json.loads(RISK_META.read_text())
        self.factors = list(meta["factors"])
        self.groups = list(meta["groups"])
        self.styles = list(meta["styles"])


def _k2(net: pd.Series, ctx: Context) -> dict[str, Any]:
    try:
        r = ev.k2_edges(net, ctx.s3)
        r["error"] = None
        return r
    except ValueError as exc:  # session-convention guard
        return {
            "edge": {w: float("nan") for w in JUDGED},
            "pass_0.05": False,
            "pass_0.10": False,
            "error": str(exc)[:200],
        }


def path_metrics(pid: str, info: Mapping[str, Any], ctx: Context, light: bool = False) -> dict:
    base = ROOT / info["dir"]
    meta = json.loads((base / "meta.json").read_text())
    daily = pd.read_parquet(base / "daily.parquet").set_index("trade_date").sort_index()
    net, gross = daily["net"], daily["gross"]
    out: dict[str, Any] = {
        "kind": info["kind"],
        "variant": meta.get("variant"),
        "offset": meta.get("offset"),
        "exec": meta.get("exec"),
        "loo_theme": meta.get("loo_theme"),
        "net": {
            w: ev.window_metrics(net, ctx.rf, ctx.spy, win, daily) for w, win in WINDOWS.items()
        },
        "gross": {w: ev.window_metrics(gross, ctx.rf, ctx.spy, win) for w, win in WINDOWS.items()},
    }
    if light:
        return out
    rep = pd.read_parquet(base / "replays.parquet").set_index("trade_date").sort_index()
    for col in REPLAYS:
        out[REPLAY_KEY[col]] = {
            w: ev.window_metrics(rep[col], ctx.rf, ctx.spy, win) for w, win in WINDOWS.items()
        }
    out["gross_cost2x"] = {
        w: ev.window_metrics(rep["gross_cost2x"], ctx.rf, ctx.spy, win)
        for w, win in WINDOWS.items()
    }
    out["k1_path"] = ev.k1_check(out["net"], out["cost2x"])
    out["k2_frozen"] = _k2(net, ctx)
    net_ca = cash_aligned(net, ctx.bil, ctx.shy)
    out["k2_cash_aligned"] = _k2(net_ca, ctx)
    out["beta"] = {
        "daily": {w: out["net"][w].get("beta_spy") for w in WINDOWS},
        "dimson": {w: dimson_beta(net, ctx.spy, win) for w, win in WINDOWS.items()},
    }
    out["failure"] = failure_stats(meta)
    out["dsr"] = {
        "anchor": ev.deflated_sharpe(net, ctx.rf, WINDOWS["anchor"]),
        "full": ev.deflated_sharpe(net, ctx.rf, FULL),
    }
    out["costs_bp_per_year"] = {w: _window_costs_bp(daily, win) for w, win in WINDOWS.items()}
    out["costs_bp_per_year"]["full"] = _window_costs_bp(daily, FULL)
    reg_t = (daily["long_exp"] + daily["short_exp"].abs() + daily["tbill_exp"]) > 2.02
    out["reg_t_days"] = {
        "full": int(reg_t.sum()),
        **{
            w: int(reg_t[(reg_t.index >= a) & (reg_t.index <= b)].sum())
            for w, (a, b) in WINDOWS.items()
        },
        "meta_reg_t_violation_days": meta.get("run_info", {}).get("reg_t_violation_days"),
    }
    rec = pd.read_parquet(
        base / "records.parquet",
        columns=["date", "exposures_target", "vol_target", "beta_target", "forced_exits"],
    )
    rec["date"] = pd.to_datetime(rec["date"])
    expo: dict[str, Any] = {"full": _exposure_summary(rec, ctx.factors, ctx.groups, ctx.styles)}
    for w, (a, b) in WINDOWS.items():
        expo[w] = _exposure_summary(
            rec[(rec["date"] >= a) & (rec["date"] <= b)], ctx.factors, ctx.groups, ctx.styles
        )
    out["exposures"] = expo
    out["forced_liquidations"] = {
        "bankrupt": meta.get("run_info", {}).get("bankrupt"),
        "delist_exits": meta.get("run_info", {}).get("delist_exits"),
        "forced_exits_total": expo["full"]["forced_exits"],
    }
    out["_daily_net"] = net  # popped by the caller
    return out


# ------------------------------------------------------------------ variant level


def _med_block(recs: list[dict[str, Any]]) -> dict[str, Any]:
    keys = (
        "net",
        "gross",
        "cost2x",
        "gross_cost2x",
        "fix10",
        "fix20",
        "delist30",
        "k2_frozen",
        "k2_cash_aligned",
        "beta",
        "failure",
        "dsr",
        "costs_bp_per_year",
        "reg_t_days",
    )
    sub = [{k: r[k] for k in keys} for r in recs]
    # the error string of k2 is not numeric and is skipped by median_nested
    return median_nested(sub)


def variant_block(
    vid: str, recs: list[dict[str, Any]], nets: list[pd.Series], ctx: Context, phases: Mapping
) -> dict[str, Any]:
    med = _med_block(recs)
    # k2 edge medians must exist even when the error path left NaN
    checks = variant_checks(med)
    failures = [r["failure"]["failure_rate"] for r in recs]
    med["k1_median"] = ev.k1_check(med["net"], med["cost2x"])
    mixed = pd.concat(nets, axis=1).mean(axis=1)
    phases_recent = []
    for p in phases["phases_recent"]:
        st = period_stats(mixed, ctx.rf, p["start"], p["end"])
        phases_recent.append(
            {"id": p["id"], "start": p["start"], "end": p["end"], "label": p["label"], **st}
        )
    phases_hist = []
    for p in phases["phases_hist"]:
        st = period_stats(mixed, ctx.rf, p["start"], p["end"])
        phases_hist.append(
            {"id": p["id"], "start": p["start"], "end": p["end"], "label": p["label"], **st}
        )
    last = mixed[mixed.index <= FULL[1]].iloc[-63:]
    last63 = {
        "start": last.index[0].strftime("%Y-%m-%d"),
        "end": last.index[-1].strftime("%Y-%m-%d"),
        **period_stats(
            mixed, ctx.rf, last.index[0].strftime("%Y-%m-%d"), last.index[-1].strftime("%Y-%m-%d")
        ),
    }
    stress = {}
    for name, (a, b) in STRESS_PERIODS.items():
        st = period_stats(mixed, ctx.rf, a, b)
        sp = ctx.spy[(ctx.spy.index >= a) & (ctx.spy.index <= b)]
        stress[name] = {
            "sessions": st["sessions"],
            "cum_return": st["cum_return"],
            "spy_cum_return": float((1.0 + sp).prod() - 1.0) if len(sp) else None,
        }
    expo_med = median_nested([r["exposures"] for r in recs])
    per_offset = []
    for r in recs:
        per_offset.append(
            {
                "offset": r["offset"],
                "net": {
                    w: {
                        "sharpe": r["net"][w].get("sharpe"),
                        "ann_excess_return": r["net"][w].get("ann_excess_return"),
                    }
                    for w in WINDOWS
                },
                "gross_sharpe": {w: r["gross"][w].get("sharpe") for w in WINDOWS},
                "cost2x": {
                    w: {
                        "sharpe": r["cost2x"][w].get("sharpe"),
                        "ann_excess_return": r["cost2x"][w].get("ann_excess_return"),
                    }
                    for w in WINDOWS
                },
                "k1_path": r["k1_path"],
                "k2_frozen": r["k2_frozen"],
                "k2_cash_aligned": r["k2_cash_aligned"],
                "beta": r["beta"],
                "failure_rate": r["failure"]["failure_rate"],
                "first_attempt_failure_rate": r["failure"]["first_attempt_failure_rate"],
                "dsr": r["dsr"],
            }
        )
    fail = {
        "median_failure_rate": med["failure"]["failure_rate"],
        "max_failure_rate": float(max(failures)),
        "any_offset_gt_5pct_engineering_problem": bool(max(failures) > FAILURE_ENGINEERING),
        "median_first_attempt_failure_rate": med["failure"]["first_attempt_failure_rate"],
        "rescued_by_step_total": {
            k: int(sum(r["failure"]["rescued_by_step"].get(k, 0) for r in recs))
            for k in ("clarabel_max_iter", "clarabel_relaxed", "scs")
        },
        "scs_rescue_share_of_solves_max": float(
            max(r["failure"]["scs_rescue_share_of_solves"] for r in recs)
        ),
        "scs_share_gt_1pct": bool(
            max(r["failure"]["scs_rescue_share_of_solves"] for r in recs) > SCS_SHARE_FLAG
        ),
    }
    return {
        "offsets": [r["offset"] for r in recs],
        "median": med,
        "per_offset": per_offset,
        "checks": checks,
        "failure_summary": fail,
        "phases": {"recent": phases_recent, "hist": phases_hist},
        "last63": last63,
        "stress_periods": stress,
        "exposures": expo_med,
    }


# ------------------------------------------------------------------ report


def f(x: Any, nd: int = 3, pct: bool = False) -> str:
    if x is None:
        return "NA"
    if pct:
        return f"{x * 100:.{nd}f}%"
    return f"{x:.{nd}f}"


def write_report(res: Mapping[str, Any], path: Path) -> None:
    L: list[str] = []
    a = L.append
    a(f"# {res['iter_id']} Stage 2a 评估（机械数字，不含判定）")
    a("")
    a(f"- 生成时间（UTC）：{res['generated_at_utc']}")
    a(
        f"- 窗口：压力期 {WINDOWS['stress'][0]}..{WINDOWS['stress'][1]}；间隔 {WINDOWS['gap'][0]}..{WINDOWS['gap'][1]}；对标窗 {WINDOWS['anchor'][0]}..{WINDOWS['anchor'][1]}"
    )
    a("- 全部数值是 5 个偏移的中位数（收盘口径，A1 主口径）；夏普为对 BIL 的超额收益年化夏普。")
    a(
        f"- A1 绑定核对：manifest 全 true = {res['precondition']['manifest_binding_all_true']}；缓存文件哈希与 manifest 一致 = {res['precondition']['cached_files_match_manifest']}；绑定代码当前哈希与 meta 一致 = {res['precondition']['bound_code_matches_meta_now']}。"
    )
    a("")
    for vid in VARIANTS:
        v = res["variants"][vid]
        m = v["median"]
        a(f"## 变体 {vid}")
        a("")
        a("| 指标 | 压力期 | 间隔 | 对标窗 |")
        a("|---|---|---|---|")

        def row(label, getter, nd=3, pct=False):
            cells = []
            for w in WINDOWS:
                try:
                    cells.append(f(getter(w), nd, pct))
                except (KeyError, TypeError):
                    cells.append("NA")
            a(f"| {label} | " + " | ".join(cells) + " |")

        row("会话数 n", lambda w: m["net"][w]["n"], 0)
        row("净夏普", lambda w: m["net"][w]["sharpe"])
        row("毛夏普", lambda w: m["gross"][w]["sharpe"])
        row("2 倍成本夏普", lambda w: m["cost2x"][w]["sharpe"])
        row("净年化超额", lambda w: m["net"][w]["ann_excess_return"], 2, True)
        row("毛年化超额", lambda w: m["gross"][w]["ann_excess_return"], 2, True)
        row("2 倍成本年化超额", lambda w: m["cost2x"][w]["ann_excess_return"], 2, True)
        row("固定 10 bp 夏普", lambda w: m["fix10"][w]["sharpe"])
        row("固定 20 bp 夏普", lambda w: m["fix20"][w]["sharpe"])
        row("退市额外 -30% 夏普", lambda w: m["delist30"][w]["sharpe"])
        row("K2 边际（冻结口径）", lambda w: m["k2_frozen"]["edge"][w])
        row("K2 边际（现金对齐）", lambda w: m["k2_cash_aligned"]["edge"][w])
        row("日 beta", lambda w: m["beta"]["daily"][w])
        row("Dimson beta", lambda w: m["beta"]["dimson"][w])
        row("净年化波动", lambda w: m["net"][w]["vol"], 2, True)
        row("最大回撤", lambda w: m["net"][w]["max_dd"], 1, True)
        row("换手（年化，单边，占权益）", lambda w: m["net"][w]["turnover"], 1)
        row("成本占比 cost_share", lambda w: m["net"][w]["cost_share"], 2, True)
        for comp in ("spread", "impact", "fees", "borrow", "margin", "total"):
            row(f"成本 {comp}（bp/年）", lambda w, c=comp: m["costs_bp_per_year"][w][c], 1)
        row("多头敞口均值", lambda w: m["net"][w]["avg_long_exp"], 3)
        row("空头敞口均值", lambda w: m["net"][w]["avg_short_exp"], 3)
        row("短债敞口均值", lambda w: m["net"][w]["avg_tbill_exp"], 3)
        row("Reg T 天数（L+S+Q>2.02）", lambda w: m["reg_t_days"][w], 0)
        fs = v["failure_summary"]
        a("")
        a(
            f"- 求解失败率：中位数 {f(fs['median_failure_rate'], 4, True)}，最大 {f(fs['max_failure_rate'], 4, True)}；"
            f"第一次尝试失败率中位数 {f(fs['median_first_attempt_failure_rate'], 4, True)}；"
            f"各级救回合计 {fs['rescued_by_step_total']}；SCS 救回占求解比例最大 {f(fs['scs_rescue_share_of_solves_max'], 4, True)}（>1% 标记 = {fs['scs_share_gt_1pct']}）；"
            f"任一偏移 >5% 标工程问题 = {fs['any_offset_gt_5pct_engineering_problem']}。"
        )
        a(
            f"- DSR（77 次试验，偏移中位数）：对标窗 {f(m['dsr']['anchor'], 4)}，全样本 {f(m['dsr']['full'], 4)}。"
        )
        a(
            "- 各偏移净夏普（压力 / 间隔 / 对标）："
            + "；".join(
                f"o{p['offset']}: {f(p['net']['stress']['sharpe'], 2)} / {f(p['net']['gap']['sharpe'], 2)} / {f(p['net']['anchor']['sharpe'], 2)}"
                for p in v["per_offset"]
            )
        )
        a(f"- 路径级 K1 交叉核对（各偏移）：{[p['k1_path']['pass'] for p in v['per_offset']]}")
        ex = v["exposures"]["full"]
        a(
            f"- 敞口（全样本，偏移中位数；目标权重事后记录）：市场 均值 {f(ex['market']['mean'], 4)} / 最大绝对值 {f(ex['market']['max_abs'], 4)}；"
            f"行业 平均绝对值 {f(ex['sector']['mean_abs'], 4)} / 最大绝对值 {f(ex['sector']['max_abs'], 4)}；"
            f"事前波动 均值 {f(ex['ex_ante_vol']['mean'], 4)} / 最大 {f(ex['ex_ante_vol']['max'], 4)}；"
            f"预测 beta 均值 {f(ex['predicted_beta']['mean'], 4)} / 最大绝对值 {f(ex['predicted_beta']['max_abs'], 4)}；强制平仓 {int(ex['forced_exits'])} 次。"
        )
        a(
            "- 风格暴露（均值 / 最大绝对值）："
            + "；".join(
                f"{s} {f(d['mean'], 3)} / {f(d['max_abs'], 3)}" for s, d in ex["styles"].items()
            )
        )
        a("")
    a("## 条件真假表（偏移中位数口径）")
    a("")
    a("| 条件 | " + " | ".join(VARIANTS) + " |")
    a("|---|" + "---|" * len(VARIANTS))
    for fld in CHECK_FIELDS:
        a(
            f"| {fld} | "
            + " | ".join(str(res["variants"][v]["checks"][fld]) for v in VARIANTS)
            + " |"
        )
    a("")
    a(f"- placebo_needed：{res['placebo_needed']}")
    a(f"- mechanical_status：{res['mechanical_status']}")
    a("")
    a("## 阶段表（phases_recent，5 个偏移等权平均日净收益；夏普对 BIL 超额，会话数 < 20 的段标 *）")
    a("")
    a("| 段 | 起 | 止 | 标签 | 会话 | " + " | ".join(f"{v} 夏普 / 累计" for v in VARIANTS) + " |")
    a("|---|---|---|---|---|" + "---|" * len(VARIANTS))
    ref = res["variants"][VARIANTS[0]]["phases"]["recent"]
    for i, p in enumerate(ref):
        cells = []
        for vid in VARIANTS:
            q = res["variants"][vid]["phases"]["recent"][i]
            star = "*" if q["short_sample"] else ""
            cells.append(f"{f(q['sharpe'], 2)}{star} / {f(q['cum_return'], 1, True)}")
        a(
            f"| {p['id']} | {p['start']} | {p['end']} | {p['label']} | {p['sessions']} | "
            + " | ".join(cells)
            + " |"
        )
    a("")
    a(
        "最近 63 个会话（夏普 / 累计）："
        + "；".join(
            f"{v}: {f(res['variants'][v]['last63']['sharpe'], 2)} / {f(res['variants'][v]['last63']['cum_return'], 1, True)}（{res['variants'][v]['last63']['start']}..{res['variants'][v]['last63']['end']}）"
            for v in VARIANTS
        )
    )
    a("")
    a("## 固定压力期累计收益（偏移等权平均）")
    a("")
    a("| 期间 | 会话 | SPY | " + " | ".join(VARIANTS) + " |")
    a("|---|---|---|" + "---|" * len(VARIANTS))
    for name in STRESS_PERIODS:
        st0 = res["variants"][VARIANTS[0]]["stress_periods"][name]
        a(
            f"| {name} | {st0['sessions']} | {f(st0['spy_cum_return'], 1, True)} | "
            + " | ".join(
                f(res["variants"][v]["stress_periods"][name]["cum_return"], 1, True)
                for v in VARIANTS
            )
            + " |"
        )
    a("")
    a("## 成交时点（M0_A/B/C，偏移中位数；收盘口径 = A1 主口径，开盘口径 = 敏感性）")
    a("")
    a(
        "| 变体 | 窗口 | 收盘毛夏普 | 开盘毛夏普 | 收盘净夏普 | 开盘净夏普 | 对成交时点敏感（该窗） |"
    )
    a("|---|---|---|---|---|---|---|")
    for vid in TIMING_VARIANTS:
        t = res["timing"][vid]
        for w in WINDOWS:
            r = t["windows"][w]
            a(
                f"| {vid} | {w} | {f(r['close_gross_sharpe'], 3)} | {f(r['open_gross_sharpe'], 3)} | {f(r['close_net_sharpe'], 3)} | {f(r['open_net_sharpe'], 3)} | {r['timing_sensitive']} |"
            )
    a("")
    a(
        "timing_sensitive（任一窗）："
        + "；".join(f"{v} = {res['timing'][v]['timing_sensitive']}" for v in TIMING_VARIANTS)
    )
    a("")
    a("## 去掉一个主题（M0_A 偏移 0，诊断，不进判定）：净夏普 / 边际贡献（M0_A_o0_close 减去它）")
    a("")
    a("| 去掉的主题 | 压力期 | 间隔 | 对标窗 |")
    a("|---|---|---|---|")
    a(
        "| （基线 M0_A_o0_close） | "
        + " | ".join(f(res["leave_one_out"]["baseline"][w], 3) for w in WINDOWS)
        + " |"
    )
    for th in THEMES:
        r = res["leave_one_out"]["themes"][th]
        a(
            f"| {th} | "
            + " | ".join(
                f"{f(r[w]['sharpe'], 3)} / {f(r[w]['marginal_contribution'], 3)}" for w in WINDOWS
            )
            + " |"
        )
    a("")
    a("## DSR（77 次试验；偏移中位数；只报告）")
    a("")
    a("| 变体 | 对标窗 | 全样本 |")
    a("|---|---|---|")
    for vid in VARIANTS:
        d = res["variants"][vid]["median"]["dsr"]
        a(f"| {vid} | {f(d['anchor'], 4)} | {f(d['full'], 4)} |")
    a("")
    a("判定待主审。")
    path.write_text("\n".join(L) + "\n")


# ------------------------------------------------------------------ main


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True, choices=["2a"])
    ap.parse_args()

    pre = precondition()
    problems = []
    if not pre["queue_t08_done"]:
        problems.append(f"queue T-20261001-08 status not done: {pre['queue_t08_status'][:80]!r}")
    if pre["manifest_n_paths"] != 54:
        problems.append("manifest does not list 54 paths")
    if not pre["manifest_binding_all_true"]:
        problems.append("manifest binding comparisons not all true")
    if not pre["cached_files_match_manifest"]:
        problems.append(f"cached files differ from manifest: {pre['bad_files']}")
    if problems:
        print("BLOCKED:", "; ".join(problems))
        return 3
    a1_binding_ok = bool(
        pre["manifest_binding_all_true"]
        and pre["cached_files_match_manifest"]
        and pre["bound_code_matches_meta_now"]
    )
    manifest_paths = pre["manifest"]["paths"]
    ctx = Context()
    phases = json.loads(PHASES.read_text())

    paths: dict[str, Any] = {}
    nets: dict[str, pd.Series] = {}
    for i, (pid, info) in enumerate(sorted(manifest_paths.items())):
        light = info["kind"] == "loo"
        r = path_metrics(pid, info, ctx, light=light)
        nets[pid] = r.pop("_daily_net", None) if not light else None
        if light:
            nets[pid] = None
        paths[pid] = r
        print(f"[{i + 1}/54] {pid}", flush=True)

    variants: dict[str, Any] = {}
    for vid in VARIANTS:
        pids = sorted(
            p
            for p, r in paths.items()
            if r["kind"] == "main" and r["variant"] == vid and r["exec"] == "close"
        )
        assert len(pids) == 5, (vid, pids)
        recs = [dict(paths[p], offset=paths[p]["offset"]) for p in pids]
        variants[vid] = variant_block(vid, recs, [nets[p] for p in pids], ctx, phases)

    timing: dict[str, Any] = {}
    for vid in TIMING_VARIANTS:
        per: dict[str, Any] = {}
        for ex_ in ("close", "open"):
            pids = sorted(
                p
                for p, r in paths.items()
                if r["kind"] == "main" and r["variant"] == vid and r["exec"] == ex_
            )
            assert len(pids) == 5, (vid, ex_, pids)
            per[ex_] = {
                w: {
                    "gross": ev.median_over_offsets(
                        {k: paths[p]["gross"][w]["sharpe"] for k, p in enumerate(pids)}
                    ),
                    "net": ev.median_over_offsets(
                        {k: paths[p]["net"][w]["sharpe"] for k, p in enumerate(pids)}
                    ),
                }
                for w in WINDOWS
            }
        wins = {}
        for w in WINDOWS:
            cg, og = per["close"][w]["gross"], per["open"][w]["gross"]
            wins[w] = {
                "close_gross_sharpe": cg,
                "open_gross_sharpe": og,
                "close_net_sharpe": per["close"][w]["net"],
                "open_net_sharpe": per["open"][w]["net"],
                "timing_sensitive": timing_flag(cg, og),
            }
        timing[vid] = {
            "windows": wins,
            "timing_sensitive": any(x["timing_sensitive"] for x in wins.values()),
        }

    base_pid = "M0_A_o0_close"
    loo: dict[str, Any] = {
        "baseline": {w: paths[base_pid]["net"][w]["sharpe"] for w in WINDOWS},
        "themes": {},
    }
    for th in THEMES:
        pid = f"{base_pid}_loo_{th}"
        loo["themes"][th] = {
            w: {
                "sharpe": paths[pid]["net"][w]["sharpe"],
                "marginal_contribution": paths[base_pid]["net"][w]["sharpe"]
                - paths[pid]["net"][w]["sharpe"],
            }
            for w in WINDOWS
        }

    placebo_needed = order_placebo_needed(variants)
    gen = subprocess.run(
        ["date", "-u", "+%Y-%m-%dT%H:%M:%SZ"], capture_output=True, text=True, check=True
    ).stdout.strip()
    pre_out = {k: v for k, v in pre.items() if k != "manifest"}
    res = {
        "iter_id": ITER_ID,
        "stage": "2a",
        "generated_at_utc": gen,
        "a1_binding_ok": a1_binding_ok,
        "precondition": pre_out,
        "windows": {k: list(v) for k, v in WINDOWS.items()} | {"full": list(FULL)},
        "trial_count_dsr": ev.DSR_TRIALS,
        "paths": paths,
        "variants": variants,
        "timing": timing,
        "leave_one_out": loo,
        "placebo_needed": placebo_needed,
        "mechanical_status": "pending_placebo"
        if placebo_needed
        else "no_variant_reaches_cond1_or_anchor_1_19",
    }
    res = clean(res)
    (ITER_DIR / "results.json").write_text(json.dumps(res, indent=1, allow_nan=False) + "\n")
    write_report(res, ITER_DIR / "report.md")
    print("mechanical_status:", res["mechanical_status"], "placebo_needed:", placebo_needed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
