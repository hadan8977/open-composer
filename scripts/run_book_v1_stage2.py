"""Stage 2a raw runs of the equity book v1 (T-20261001-08; preregistration + amendment A1).

Runs the book backtest for a list of paths and writes the raw outputs per path; it computes no
Sharpe, return statistic, K1/K2 or verdict (evaluation is T-20261001-13).

Path ids
    main     ``{variant}_o{offset}_{exec}`` with variant ``M0_A`` .. ``M1_C`` (method_config), e.g.
             ``M0_A_o0_close``; the open-fill sensitivity ``M0_*_o*_open``; the leave-one-theme-out
             diagnostics ``M0_A_o0_close_loo_<theme>``.  54 paths in a fixed order.
    placebo  ``{variant}_s{seed:02d}_o{seed % 5}_close`` (main run only, no replays); implemented
             and tested, not run in T-20261001-08.

    scripts/run_capped.sh --mem 1.8G -- uv run python scripts/run_book_v1_stage2.py --plan main \
        --paths M0_A_o0_close --out-dir /tmp/out
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import re
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from open_composer.research.equity_book import optimize as op  # noqa: E402
from open_composer.research.equity_book.backtest import TBILL, run_book  # noqa: E402
from open_composer.research.equity_book.costfn import make_cost_fn, snapshot_for  # noqa: E402
from open_composer.research.equity_book.etf_risk import ETFRisk  # noqa: E402
from open_composer.research.equity_book.panel import PanelAttributes, PricePanel  # noqa: E402
from open_composer.research.equity_book.risk import RiskModel  # noqa: E402
from open_composer.research.equity_book.signals import THEMES  # noqa: E402
from scripts.build_book_v1_alpha import (  # noqa: E402
    IC_WINDOW_MAX,
    LAG,
    OUT_DIR,
    THEME_WINDOW_MAX,
    ic_scale,
    m1_weights,
    select_window,
)

DEFAULT_START, DEFAULT_END = "2017-10-02", "2026-09-17"
LOAD_START = "2016-09-01"
INITIAL_EQUITY = 1_000_000.0
VARIANTS = ("M0_A", "M0_B", "M0_C", "M1_A", "M1_B", "M1_C")
OPEN_VARIANTS = ("M0_A", "M0_B", "M0_C")
OFFSETS = (0, 1, 2, 3, 4)
PLACEBO_SEED_BASE = 20261001
UNIVERSE_OF = {"A": "u3000", "B": "u3000", "C": "p1000"}
BOUND_FILES = (
    "open_composer/research/equity_book/risk.py",
    "open_composer/research/equity_book/costs.py",
    "open_composer/research/equity_book/cost_model_v1.json",
    "open_composer/research/equity_book/costfn.py",
    "open_composer/research/equity_book/borrow.py",
    "open_composer/research/equity_book/optimize.py",
    "open_composer/research/equity_book/etf_risk.py",
    "open_composer/research/equity_book/signals.py",
    "open_composer/research/equity_book/backtest.py",
    "open_composer/research/equity_book/evaluate.py",
    "open_composer/research/equity_book/returns.py",
    "open_composer/research/equity_book/panel.py",
    "scripts/build_equity_book_signals.py",
    "data/research/equity_book/risk/meta.json",
)
REPLAY_COLUMNS = ["net_cost2x", "gross_cost2x", "net_fix10", "net_fix20", "net_delist30"]

_MAIN_RE = re.compile(
    r"^(?P<method>M[01])_(?P<config>[ABC])_o(?P<offset>[0-4])_(?P<exec>close|open)"
    r"(?:_loo_(?P<loo>[a-z_]+))?$"
)
_PLACEBO_RE = re.compile(
    r"^(?P<method>M[01])_(?P<config>[ABC])_s(?P<seed>\d{2,3})_o(?P<offset>[0-4])_close$"
)


# ---------------------------------------------------------------------------
# path plans
# ---------------------------------------------------------------------------


def main_paths() -> list[str]:
    paths = [f"{v}_o{k}_close" for v in VARIANTS for k in OFFSETS]
    paths += [f"{v}_o{k}_open" for v in OPEN_VARIANTS for k in OFFSETS]
    paths += [f"M0_A_o0_close_loo_{t}" for t in THEMES]
    return paths


def placebo_paths(seeds: list[int], variants: list[str]) -> list[str]:
    return [f"{v}_s{s:02d}_o{s % 5}_close" for v in variants for s in seeds]


def shard_paths(paths: list[str], shard: int, nshards: int) -> list[str]:
    return paths[shard::nshards]


def parse_seeds(text: str) -> list[int]:
    """``"100"`` -> 0..99; ``"0-19"`` -> 0..19; ``"3,7"`` -> [3, 7]."""
    if "," in text:
        return [int(x) for x in text.split(",")]
    if "-" in text:
        a, b = text.split("-")
        return list(range(int(a), int(b) + 1))
    return list(range(int(text)))


def parse_path(path_id: str) -> dict[str, Any]:
    m = _MAIN_RE.match(path_id)
    if m:
        return {
            "path_id": path_id,
            "kind": "loo" if m["loo"] else "main",
            "variant": f"{m['method']}_{m['config']}",
            "method": m["method"],
            "config": m["config"],
            "offset": int(m["offset"]),
            "exec": m["exec"],
            "loo": m["loo"],
            "seed": None,
        }
    m = _PLACEBO_RE.match(path_id)
    if m:
        seed = int(m["seed"])
        if int(m["offset"]) != seed % 5:
            raise ValueError(f"placebo offset must equal seed % 5: {path_id}")
        return {
            "path_id": path_id,
            "kind": "placebo",
            "variant": f"{m['method']}_{m['config']}",
            "method": m["method"],
            "config": m["config"],
            "offset": int(m["offset"]),
            "exec": "close",
            "loo": None,
            "seed": seed,
        }
    raise ValueError(f"bad path id {path_id!r}")


def shuffle_scores(scores: pd.Series, rng: np.random.Generator) -> pd.Series:
    """Placebo: permute the values over the universe members (the multiset of values, NaNs
    included, is unchanged); one draw per call."""
    vals = scores.to_numpy()
    return pd.Series(vals[rng.permutation(len(vals))], index=scores.index)


# ---------------------------------------------------------------------------
# alpha inputs
# ---------------------------------------------------------------------------


class ThemeStore:
    """Lazy per-year reader of ``alpha/book_v1/themes_<year>.parquet``."""

    def __init__(self, base: Path = OUT_DIR) -> None:
        self.base = Path(base)
        self._year: int | None = None
        self._df: pd.DataFrame | None = None
        self._dates: np.ndarray | None = None

    def at(self, t: pd.Timestamp) -> pd.DataFrame:
        if self._year != t.year:
            df = pd.read_parquet(self.base / f"themes_{t.year}.parquet")
            self._df = df.sort_values(["trade_date", "symbol"], kind="stable").reset_index(
                drop=True
            )
            self._dates = self._df["trade_date"].to_numpy()
            self._year = t.year
        assert self._df is not None and self._dates is not None
        d = np.datetime64(t.to_datetime64())
        lo, hi = np.searchsorted(self._dates, d, "left"), np.searchsorted(self._dates, d, "right")
        return self._df.iloc[lo:hi].set_index("symbol")


class FormationIC:
    """Formation ICs of one method / universe pair and the theme-IC matrix, with the lag rule."""

    def __init__(self, fic: pd.DataFrame, dates: pd.DatetimeIndex) -> None:
        self.dates = dates
        self.fic = fic
        self._series: dict[tuple[str, str], tuple[np.ndarray, np.ndarray]] = {}
        self._themes: dict[str, tuple[np.ndarray, np.ndarray]] = {}

    def _pos(self, d: pd.Series) -> np.ndarray:
        return self.dates.get_indexer(pd.DatetimeIndex(d))

    def series(self, universe: str, name: str) -> tuple[np.ndarray, np.ndarray]:
        key = (universe, name)
        if key not in self._series:
            sub = self.fic[(self.fic["universe"] == universe) & (self.fic["series"] == name)]
            sub = sub.assign(pos=self._pos(sub["formation_date"])).sort_values("pos")
            sub = sub[(sub["pos"] >= 0) & np.isfinite(sub["ic"])]
            self._series[key] = (sub["pos"].to_numpy(), sub["ic"].to_numpy())
        return self._series[key]

    def theme_matrix(self, universe: str) -> tuple[np.ndarray, np.ndarray]:
        if universe not in self._themes:
            sub = self.fic[(self.fic["universe"] == universe) & self.fic["series"].isin(THEMES)]
            wide = sub.pivot(index="formation_date", columns="series", values="ic")[list(THEMES)]
            wide = wide.dropna(how="all")
            pos = self._pos(pd.Series(wide.index))
            order = np.argsort(pos)
            keep = pos[order] >= 0  # formation dates outside the loaded panel cannot be used
            self._themes[universe] = (pos[order][keep], wide.to_numpy()[order][keep])
        return self._themes[universe]

    def ic_t(self, universe: str, method: str, t_pos: int) -> tuple[float, int, bool]:
        pos, ic = self.series(universe, method)
        idx = select_window(pos, t_pos, IC_WINDOW_MAX, LAG)
        val, prior = ic_scale(ic[idx])
        return val, len(idx), prior

    def m1_at(self, universe: str, t_pos: int) -> tuple[np.ndarray, bool, int]:
        pos, mat = self.theme_matrix(universe)
        idx = select_window(pos, t_pos, THEME_WINDOW_MAX, LAG)
        w, fallback = m1_weights(mat[idx] if len(idx) else np.zeros((0, len(THEMES))))
        return w, fallback, len(idx)


class AlphaSource:
    """``alpha_source(t, state, universe)``: theme scores -> weighted composite -> rank-normal
    (-> placebo permutation).  M0 equal weights; M1 reweighted at the first rebalance of each
    calendar month from the lagged formation ICs; ``drop_theme`` removes one theme (the
    leave-one-out diagnostic, equal weights on the other eight)."""

    def __init__(
        self,
        store: ThemeStore,
        fic: FormationIC,
        method: str,
        universe: str,
        *,
        drop_theme: str | None = None,
        placebo_seed: int | None = None,
    ) -> None:
        self.store, self.fic, self.method, self.universe = store, fic, method, universe
        self.drop_theme = drop_theme
        self.rng = (
            None
            if placebo_seed is None
            else np.random.default_rng(PLACEBO_SEED_BASE + placebo_seed)
        )
        self.themes = [t for t in THEMES if t != drop_theme]
        self.weights = np.full(len(self.themes), 1.0 / len(self.themes))
        self._month: tuple[int, int] | None = None
        self.m1_updates: list[dict[str, Any]] = []

    def __call__(self, t: pd.Timestamp, state: Any, universe: pd.Index) -> pd.Series:
        if self.method == "M1" and self._month != (t.year, t.month):
            w, fallback, n_obs = self.fic.m1_at(self.universe, state.pos)
            self.weights = w
            self._month = (t.year, t.month)
            self.m1_updates.append(
                {
                    "date": str(t.date()),
                    "n_obs": n_obs,
                    "fallback_equal": bool(fallback),
                    "weights": {k: float(v) for k, v in zip(THEMES, w, strict=True)},
                }
            )
        th = self.store.at(t).reindex(universe)
        score = th[self.themes].to_numpy("float64") @ self.weights
        s = pd.Series(score, index=universe)
        out = op.rank_normal(s)
        if self.rng is not None:
            out = shuffle_scores(out, self.rng)
        return out


# ---------------------------------------------------------------------------
# run one path
# ---------------------------------------------------------------------------


def vmhwm_mb() -> float:
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith("VmHWM"):
            return float(line.split()[1]) / 1024.0
    return float("nan")


def bound_sha256() -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for f in BOUND_FILES:
        p = ROOT / f
        out[f] = hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None
    return out


def _jsonable(v: Any) -> Any:
    if isinstance(v, np.ndarray):
        return v.tolist()
    if isinstance(v, np.generic):
        return v.item()
    if isinstance(v, pd.Timestamp):
        return str(v)
    raise TypeError(type(v))


def records_frame(records: list[dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for r in records:
        row = {}
        for k, v in r.items():
            if isinstance(v, (list, tuple, dict, np.ndarray)):
                row[k] = json.dumps(v, default=_jsonable)
            else:
                row[k] = v
        rows.append(row)
    return pd.DataFrame(rows)


def double_cost(fn: Callable[..., dict[str, float]]) -> Callable[..., dict[str, float]]:
    def wrapped(trades: pd.DataFrame, state: Any = None) -> dict[str, float]:
        return {k: 2.0 * float(v) for k, v in fn(trades, state).items()}

    return wrapped


def replay(
    panel: PricePanel,
    base_cfg: Any,
    targets: dict[pd.Timestamp, dict[str, float] | None],
    **overrides: Any,
) -> Any:
    """Re-run the accounting on the stored target path (failed dates return None)."""
    dates = sorted(targets)
    cfg = dataclasses.replace(base_cfg, signal_dates=dates, **overrides)

    def decide(t: pd.Timestamp, state: Any) -> dict[str, float] | None:
        return targets[pd.Timestamp(t)]

    return run_book(panel, decide, cfg)


class Context:
    def __init__(self, args: argparse.Namespace) -> None:
        start = pd.Timestamp(args.start)
        load_start = (
            LOAD_START
            if args.start == DEFAULT_START
            else str((start - pd.Timedelta(days=400)).date())
        )
        t0 = time.time()
        self.panel = PricePanel.from_dir(start=load_start, end=args.end)
        self.rm = RiskModel()
        self.attrs = PanelAttributes()
        self.etf = ETFRisk(self.rm)
        self.elig = op.ShortEligibility(self.panel)
        self.store = ThemeStore()
        fic = pd.read_parquet(OUT_DIR / "formation_ic.parquet")
        self.fic = FormationIC(fic, self.panel.dates)
        self.sha = bound_sha256()
        self.load_s = time.time() - t0
        self.args = args


def run_path(ctx: Context, path_id: str, out_root: Path) -> dict[str, Any]:
    args = ctx.args
    p = parse_path(path_id)
    out = out_root / path_id
    out.mkdir(parents=True, exist_ok=True)
    uni = UNIVERSE_OF[p["config"]]
    exec_price = p["exec"]
    method_for_ic = "M0" if p["kind"] == "loo" else p["method"]
    src = AlphaSource(
        ctx.store,
        ctx.fic,
        p["method"],
        uni,
        drop_theme=p["loo"],
        placebo_seed=p["seed"],
    )
    spec = op.BookSpec(p["config"], op.OptConfig(beta_method="ewma", snapshot=exec_price))
    decider = op.make_decide(
        src,
        ctx.rm,
        spec,
        attrs=ctx.attrs,
        etf_risk=ctx.etf,
        eligibility=ctx.elig,
    )
    cfg = op.book_config(
        spec,
        ctx.attrs,
        freq="W",
        offset=p["offset"],
        exec_price=exec_price,
        start=args.start,
        end=args.end,
        initial_weights={TBILL: 1.0},
        initial_equity=INITIAL_EQUITY,
        snapshots=False,
    )
    targets: dict[pd.Timestamp, dict[str, float] | None] = {}
    ic_log: list[dict[str, Any]] = []

    def decide(t: pd.Timestamp, state: Any) -> dict[str, float] | None:
        ic_val, n_used, prior = ctx.fic.ic_t(uni, method_for_ic, state.pos)
        ic_log.append({"date": str(t.date()), "ic_t": ic_val, "n": n_used, "prior": prior})
        decider.spec = op.BookSpec(p["config"], spec.opt.with_(ic=ic_val))
        res_t = decider(t, state)
        targets[pd.Timestamp(t)] = None if res_t is None else dict(res_t)
        return res_t

    t0 = time.time()
    res = run_book(ctx.panel, decide, cfg)
    t_main = time.time() - t0
    recs = decider.records
    wall = [r.get("wall_s", 0.0) for r in recs]
    # attempt statistics
    n_first_fail = sum(1 for r in recs if (not r["ok"]) or r.get("attempt", 0) > 0)
    rescued = {k: 0 for k in ("clarabel_max_iter", "clarabel_relaxed", "scs")}
    for r in recs:
        if r["ok"] and r.get("attempt", 0) > 0:
            rescued[op.SOLVE_ATTEMPTS[r["attempt"]]] += 1
    ics = np.array([x["ic_t"] for x in ic_log], dtype=float)
    meta: dict[str, Any] = {
        "path_id": path_id,
        "kind": p["kind"],
        "variant": p["variant"],
        "offset": p["offset"],
        "exec": exec_price,
        "seed": p["seed"],
        "loo_theme": p["loo"],
        "universe": uni,
        "start": args.start,
        "end": args.end,
        "n_rebalances": len(targets),
        "n_records": len(recs),
        "n_failed_final": decider.n_failures,
        "n_none_returns": sum(1 for v in targets.values() if v is None),
        "n_failed_first_attempt": n_first_fail,
        "failed_by_status": {
            k: sum(1 for r in recs if not r["ok"] and r["status"] == k)
            for k in sorted({r["status"] for r in recs if not r["ok"]})
        },
        "rescued_by_step": rescued,
        "ic_t": {
            "min": float(ics.min()) if len(ics) else None,
            "median": float(np.median(ics)) if len(ics) else None,
            "max": float(ics.max()) if len(ics) else None,
            "n_prior_only": int(sum(1 for x in ic_log if x["prior"])),
        },
        "m1_updates": src.m1_updates,
        "timing_s": {
            "main_run": t_main,
            "decide_wall_mean": float(np.mean(wall)) if wall else None,
            "decide_wall_max": float(np.max(wall)) if wall else None,
            "panel_load": ctx.load_s,
        },
        "run_info": dict(res.info),
        "binding_sha256": ctx.sha,
    }
    do_replays = p["kind"] == "main"
    replays = None
    t0 = time.time()
    if do_replays:
        snap = snapshot_for(exec_price)
        base_borrow = spec.borrow_bp_per_year
        cost1 = make_cost_fn(snap)
        r2 = replay(ctx.panel, cfg, targets, cost_fn=double_cost(cost1), borrow_bp_per_year=100.0)
        r10 = replay(ctx.panel, cfg, targets, cost_fn=None, cost_bp_per_side=10.0)
        r20 = replay(ctx.panel, cfg, targets, cost_fn=None, cost_bp_per_side=20.0)
        rd = replay(ctx.panel, cfg, targets, delist_long_haircut=-0.30)
        replays = pd.DataFrame(
            {
                "net_cost2x": r2.daily["net"],
                "gross_cost2x": r2.daily["gross"],
                "net_fix10": r10.daily["net"],
                "net_fix20": r20.daily["net"],
                "net_delist30": rd.daily["net"],
            }
        )
        meta["replay_borrow_bp_main"] = base_borrow
    meta["timing_s"]["replays"] = time.time() - t0
    if args.replay_identity_check:
        r1 = replay(ctx.panel, cfg, targets)
        diff = float((r1.daily["net"] - res.daily["net"]).abs().max())
        meta["replay_identity_max_abs_diff"] = diff
    meta["rss_peak_mb"] = vmhwm_mb()

    res.daily.reset_index(names="trade_date").to_parquet(out / "daily.parquet", index=False)
    rows = [
        {"decision_date": d, "symbol": s, "weight": float(w)}
        for d, tgt in sorted(targets.items())
        if tgt is not None
        for s, w in tgt.items()
    ]
    pd.DataFrame(rows, columns=["decision_date", "symbol", "weight"]).to_parquet(
        out / "targets.parquet", index=False
    )
    (out / "failed_dates.json").write_text(
        json.dumps([str(d.date()) for d, v in sorted(targets.items()) if v is None])
    )
    records_frame(recs).to_parquet(out / "records.parquet", index=False)
    if replays is not None:
        replays.reset_index(names="trade_date").to_parquet(out / "replays.parquet", index=False)
    (out / "meta.json").write_text(json.dumps(meta, indent=1, default=_jsonable))
    if not args.no_etf_flush:
        ctx.etf.flush()
    return meta


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", choices=["main", "placebo"], default="main")
    ap.add_argument("--paths", default=None, help="comma-separated path ids (default: the plan)")
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--nshards", type=int, default=1)
    ap.add_argument("--start", default=DEFAULT_START)
    ap.add_argument("--end", default=DEFAULT_END)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--placebo-seeds", default="100")
    ap.add_argument("--placebo-variants", default=",".join(VARIANTS))
    ap.add_argument("--replay-identity-check", action="store_true")
    ap.add_argument("--no-etf-flush", action="store_true")
    ap.add_argument("--force", action="store_true", help="rerun paths that already have meta.json")
    args = ap.parse_args()
    if args.plan == "main":
        plan = main_paths()
    else:
        plan = placebo_paths(parse_seeds(args.placebo_seeds), args.placebo_variants.split(","))
    paths = shard_paths(plan, args.shard, args.nshards)
    if args.paths:
        paths = args.paths.split(",")
    for pid in paths:
        parse_path(pid)  # fail early on a bad id
    out_root = Path(args.out_dir)
    ctx = Context(args)
    for pid in paths:
        if (out_root / pid / "meta.json").exists() and not args.force:
            print(f"{pid}: done, skipped", flush=True)
            continue
        t0 = time.time()
        meta = run_path(ctx, pid, out_root)
        extra = (
            f" identity_max_diff {meta['replay_identity_max_abs_diff']:.2e}"
            if "replay_identity_max_abs_diff" in meta
            else ""
        )
        print(
            f"{pid}: {meta['n_rebalances']} rebalances, final fail {meta['n_failed_final']}, "
            f"first-attempt fail {meta['n_failed_first_attempt']}, decide mean "
            f"{meta['timing_s']['decide_wall_mean']:.2f}s, {time.time() - t0:.0f}s, "
            f"peak rss {meta['rss_peak_mb']:.0f} MB{extra}",
            flush=True,
        )


if __name__ == "__main__":
    main()
