"""Construction-ladder runs of the equity book v1 post-mortem (T-20261001-19).

Reuses ``Context``, ``AlphaSource`` and the output helpers of ``scripts/run_book_v1_stage2.py``
(that file and the A1-bound code are not edited).  A path is one book backtest; no statistic is
computed here.

Path ids ``PM_{L1|L2c|L2a}_{M0_A|M1_C}_o{k}`` (the 30 ladder paths, preregistered) and, for the
identity check only, ``PM_L0_{M0_A|M1_C}_o{k}`` (v1 as run: style cap 0.25, close fills).

    L0   v1 as run: style_cap 0.25 (size 0.10), close fills, close cost snapshot.
    L1   L0 with style_cap=None (every non-size style uncapped; size keeps 0.10).
    L2c  L1 with open fills; the optimiser and the realised costs use the open snapshot.
    L2a  L1 with open fills; optimiser snapshot and realised costs use the close snapshot
         (optimistic bound for an opening-auction fill).

    scripts/run_capped.sh --mem 1.8G -- uv run python scripts/run_book_postmortem.py \
        --paths PM_L0_M0_A_o0 --start 2024-01-02 --end 2024-03-29 --out-dir /tmp/pm
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from open_composer.research.equity_book import optimize as op  # noqa: E402
from open_composer.research.equity_book.backtest import TBILL, run_book  # noqa: E402
from open_composer.research.equity_book.costfn import make_cost_fn, snapshot_for  # noqa: E402
from scripts.run_book_v1_stage2 import (  # noqa: E402
    DEFAULT_END,
    DEFAULT_START,
    INITIAL_EQUITY,
    UNIVERSE_OF,
    AlphaSource,
    Context,
    _jsonable,
    records_frame,
    shard_paths,
    vmhwm_mb,
)

RUNGS = ("L0", "L1", "L2c", "L2a")
LADDER_RUNGS = ("L1", "L2c", "L2a")
PM_VARIANTS = ("M0_A", "M1_C")
OFFSETS = (0, 1, 2, 3, 4)

_PM_RE = re.compile(r"^PM_(?P<rung>L0|L1|L2c|L2a)_(?P<variant>M[01]_[ABC])_o(?P<offset>[0-4])$")


def pm_paths() -> list[str]:
    """The 30 preregistered ladder paths in a fixed order."""
    return [f"PM_{r}_{v}_o{k}" for r in LADDER_RUNGS for v in PM_VARIANTS for k in OFFSETS]


def parse_pm_path(path_id: str) -> dict[str, Any]:
    m = _PM_RE.match(path_id)
    if not m:
        raise ValueError(f"bad post-mortem path id {path_id!r}")
    method, config = m["variant"].split("_")
    return {
        "path_id": path_id,
        "rung": m["rung"],
        "variant": m["variant"],
        "method": method,
        "config": config,
        "offset": int(m["offset"]),
    }


def rung_settings(rung: str) -> dict[str, Any]:
    """``style_cap``, the order-fill price, the optimiser's cost snapshot and the realised-cost
    snapshot of one ladder rung."""
    if rung == "L0":
        return {
            "style_cap": op.OptConfig().style_cap,
            "exec": "close",
            "opt": "close",
            "cost": "close",
        }
    if rung == "L1":
        return {"style_cap": None, "exec": "close", "opt": "close", "cost": "close"}
    if rung == "L2c":
        return {"style_cap": None, "exec": "open", "opt": "open", "cost": "open"}
    if rung == "L2a":
        return {"style_cap": None, "exec": "open", "opt": "close", "cost": "close"}
    raise ValueError(rung)


def build_spec_and_cfg(
    ctx: Context, p: dict[str, Any], start: str, end: str
) -> tuple[op.BookSpec, Any]:
    s = rung_settings(p["rung"])
    spec = op.BookSpec(
        p["config"],
        op.OptConfig(beta_method="ewma", snapshot=s["opt"], style_cap=s["style_cap"]),
    )
    cfg = op.book_config(
        spec,
        ctx.attrs,
        freq="W",
        offset=p["offset"],
        exec_price=s["exec"],
        start=start,
        end=end,
        initial_weights={TBILL: 1.0},
        initial_equity=INITIAL_EQUITY,
        snapshots=False,
    )
    if s["cost"] != snapshot_for(s["exec"]):
        cfg = dataclasses.replace(cfg, cost_fn=make_cost_fn(snapshot_for(s["cost"])))
    return spec, cfg


def run_pm_path(ctx: Context, path_id: str, out_root: Path) -> dict[str, Any]:
    args = ctx.args
    p = parse_pm_path(path_id)
    out = out_root / path_id
    out.mkdir(parents=True, exist_ok=True)
    uni = UNIVERSE_OF[p["config"]]
    src = AlphaSource(ctx.store, ctx.fic, p["method"], uni)
    spec, cfg = build_spec_and_cfg(ctx, p, args.start, args.end)
    decider = op.make_decide(
        src, ctx.rm, spec, attrs=ctx.attrs, etf_risk=ctx.etf, eligibility=ctx.elig
    )
    targets: dict[pd.Timestamp, dict[str, float] | None] = {}

    def decide(t: pd.Timestamp, state: Any) -> dict[str, float] | None:
        ic_val, _n, _prior = ctx.fic.ic_t(uni, p["method"], state.pos)
        decider.spec = op.BookSpec(p["config"], spec.opt.with_(ic=ic_val))
        res_t = decider(t, state)
        targets[pd.Timestamp(t)] = None if res_t is None else dict(res_t)
        return res_t

    t0 = time.time()
    res = run_book(ctx.panel, decide, cfg)
    wall = time.time() - t0
    recs = decider.records
    meta: dict[str, Any] = {
        "path_id": path_id,
        "rung": p["rung"],
        "variant": p["variant"],
        "offset": p["offset"],
        "settings": rung_settings(p["rung"]),
        "universe": uni,
        "start": args.start,
        "end": args.end,
        "n_rebalances": len(targets),
        "n_failed_final": decider.n_failures,
        "n_none_returns": sum(1 for v in targets.values() if v is None),
        "timing_s": {"main_run": wall, "panel_load": ctx.load_s},
        "run_info": dict(res.info),
        "binding_sha256": ctx.sha,
        "rss_peak_mb": vmhwm_mb(),
    }
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
    (out / "meta.json").write_text(json.dumps(meta, indent=1, default=_jsonable))
    if not args.no_etf_flush:
        ctx.etf.flush()
    return meta


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--paths", default=None, help="comma-separated path ids (default: the 30)")
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--nshards", type=int, default=1)
    ap.add_argument("--start", default=DEFAULT_START)
    ap.add_argument("--end", default=DEFAULT_END)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--no-etf-flush", action="store_true")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    paths = (
        args.paths.split(",") if args.paths else shard_paths(pm_paths(), args.shard, args.nshards)
    )
    for pid in paths:
        parse_pm_path(pid)
    out_root = Path(args.out_dir)
    ctx = Context(args)
    for pid in paths:
        if (out_root / pid / "meta.json").exists() and not args.force:
            print(f"{pid}: done, skipped", flush=True)
            continue
        t0 = time.time()
        meta = run_pm_path(ctx, pid, out_root)
        print(
            f"{pid}: {meta['n_rebalances']} rebalances, final fail {meta['n_failed_final']}, "
            f"{time.time() - t0:.0f}s, peak rss {meta['rss_peak_mb']:.0f} MB",
            flush=True,
        )


if __name__ == "__main__":
    main()
