"""T-20260928-07: forward ("shadow") tracking of kept candidates.

Reads `reports/research/screens/kept.jsonl`, reloads each candidate's rule
from the batch module it was frozen from (by `module` + `candidate_id`), and
recomputes daily net returns with the same engine `scripts/screen_lane.py`
uses (`candidate_returns_for_offset` -> `salvage.simulate`, unedited). Only
the forward period -- sessions strictly after `kept_at` -- is reported. No
new judgment happens here: this is honest bookkeeping against rules that
were already frozen, so a candidate can only be tracked, not re-optimized.

Why a private panel loader: `run_h20260918_05_recent_menu.load_panel` caps
every query at the frozen `HOLD_END` (2026-09-17, the backtest holdout
boundary) -- exactly right for the frozen backtest windows, wrong for
forward tracking, which needs every session the local panel has picked up
since. `load_forward_panel` below is the same query and ghost-bar hygiene as
`base.load_panel`, just without that upper bound; it does not alter
`base.load_panel` itself.

    scripts/run_capped.sh --mem 1.2G -- \\
        uv run python scripts/shadow_forward.py
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_h20260918_05_recent_menu as base  # noqa: E402
import run_h20260922_05_salvage as salvage  # noqa: E402
import screen_batch  # noqa: E402
import screen_lane as lane  # noqa: E402

KEPT_PATH = ROOT / "reports" / "research" / "screens" / "kept.jsonl"
SCREENS_DIR = ROOT / "reports" / "research" / "screens"
BATCH_DIR = ROOT / "scripts" / "screen_batches"
OUT_MD = SCREENS_DIR / "forward.md"
OUT_JSON = SCREENS_DIR / "forward.json"

MIN_SHARPE_SESSIONS = 20  # brief: "if >= 20 sessions, annualized Sharpe ... and max DD"
WATCH_EXIT_MIN_SESSIONS = 63  # ~3 forward months
WATCH_EXIT_SHARPE_MIN = 0.5
WATCH_EXIT_DD_MULT = 1.5
DROPPED_PREFIX = "dropped"


# --------------------------------------------------------------------------
# kept.jsonl / git / module loading
# --------------------------------------------------------------------------


def load_kept_lines(path: Path = KEPT_PATH) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if raw:
            out.append(json.loads(raw))
    return out


def git_file_commit_now(rel_path: str) -> str | None:
    """`git log -1 --format=%H -- <rel_path>`: the most recent commit that
    touched this file, or None if it is untracked/missing from history."""
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%H", "--", rel_path],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        sha = out.stdout.strip()
        return sha or None
    except Exception:  # pragma: no cover - defensive
        return None


def load_candidate_module(module_path: str) -> ModuleType:
    """Accepts both `scripts/screen_batches/<name>.py` batch modules (loaded
    with the exact same loader `scripts/screen_batch.py` uses to run them)
    and plain script paths anywhere else in the repo."""
    p = Path(module_path)
    abs_path = p if p.is_absolute() else (ROOT / p)
    if abs_path.resolve().parent == BATCH_DIR.resolve():
        return screen_batch.load_batch_module(abs_path.stem)
    if not abs_path.exists():
        raise SystemExit(f"module not found: {abs_path}")
    spec = importlib.util.spec_from_file_location(f"shadow_forward_{abs_path.stem}", abs_path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise SystemExit(f"could not load module: {abs_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def find_candidate(module: ModuleType, candidate_id: str) -> lane.ScreenCandidate:
    for c in screen_batch.candidates_from_module(module):
        if c.id == candidate_id:
            return c
    raise SystemExit(f"candidate_id {candidate_id!r} not found in module")


def integrity_status(recorded_commit: str | None, current_commit: str | None) -> str:
    """ "ok" iff the commit recorded at keep time still matches the commit
    `git log -1` reports for the module file now; any mismatch (including an
    untracked/missing file on either side) means the rule may have changed
    since it was frozen."""
    if recorded_commit is None or current_commit is None or recorded_commit != current_commit:
        return "rule changed after freeze"
    return "ok"


# --------------------------------------------------------------------------
# panel loader without the frozen HOLD_END cap
# --------------------------------------------------------------------------


def load_forward_panel(symbols: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Same query and ghost-bar hygiene as `base.load_panel`, starting at
    `screen_lane.PANEL_START`, with no upper date bound -- picks up every
    session the local panel currently has, including ones after the frozen
    `HOLD_END`."""
    import duckdb

    con = duckdb.connect()
    con.execute("SET memory_limit='700MB'")
    con.execute("SET threads=2")
    in_list = ",".join(f"'{s}'" for s in symbols)
    frame = con.execute(
        f"""
        SELECT symbol, timestamp::DATE AS d, open, close, volume, trade_count
        FROM read_parquet('{base.DAILY_GLOB}')
        WHERE symbol IN ({in_list}) AND timestamp::DATE >= DATE '{lane.PANEL_START}'
        ORDER BY symbol, d
        """
    ).df()
    con.close()
    ghost = (frame["volume"].fillna(0) <= 0) & (frame["trade_count"].fillna(0) <= 0)
    frame = frame.loc[~ghost]
    close = frame.pivot(index="d", columns="symbol", values="close").sort_index()
    open_ = frame.pivot(index="d", columns="symbol", values="open").sort_index()
    close.index = pd.to_datetime(close.index)
    open_.index = pd.to_datetime(open_.index)
    return close, open_


# --------------------------------------------------------------------------
# forward metrics
# --------------------------------------------------------------------------


def kept_at_to_ts(kept_at: str) -> pd.Timestamp:
    ts = pd.Timestamp(kept_at)
    if ts.tzinfo is not None:
        ts = ts.tz_convert("UTC").tz_localize(None)
    return ts.normalize()


def window_metrics(ret: pd.Series, turn: pd.Series, rf: pd.Series, mask: pd.Series) -> dict:
    sub_ret = ret.loc[mask]
    n = int(len(sub_ret))
    if n == 0:
        return {"n": 0, "cum_return": None, "sharpe": None, "max_dd": None}
    cum_return = float((1.0 + sub_ret).prod() - 1.0)
    sharpe: float | None = None
    max_dd: float | None = None
    if n >= MIN_SHARPE_SESSIONS:
        sub_turn = turn.loc[mask]
        m = base.metrics(sub_ret, rf.reindex(sub_ret.index).fillna(0.0), sub_turn)
        sharpe = m.sharpe if np.isfinite(m.sharpe) else None
        max_dd = m.max_dd if np.isfinite(m.max_dd) else None
    return {"n": n, "cum_return": cum_return, "sharpe": sharpe, "max_dd": max_dd}


def combine_offsets(per_offset: list[dict]) -> dict:
    """Median across offsets, the same "don't pick the rebalance day" rule
    `screen_lane.offset_summary` applies to the frozen backtest -- applies
    here to the forward window too. `n` is identical across offsets (the
    forward date mask doesn't depend on the rebalance offset), so a plain
    `max` is a defensive fallback only."""
    ns = {d["n"] for d in per_offset}
    n = ns.pop() if len(ns) == 1 else max(d["n"] for d in per_offset)

    def med(key: str) -> float | None:
        vals = [d[key] for d in per_offset if d[key] is not None]
        return float(np.median(vals)) if vals else None

    return {
        "n": n,
        "cum_return": med("cum_return"),
        "sharpe": med("sharpe"),
        "max_dd": med("max_dd"),
    }


def candidate_forward_metrics(
    close: pd.DataFrame,
    leg_open: pd.DataFrame,
    leg_close: pd.DataFrame,
    rf: pd.Series,
    candidate: lane.ScreenCandidate,
    kept_ts: pd.Timestamp,
) -> tuple[dict, pd.DatetimeIndex]:
    offsets = lane.offsets_for_freq(candidate.freq)
    per_offset: list[dict] = []
    forward_index = pd.DatetimeIndex([])
    for o in offsets:
        ret, turn = lane.candidate_returns_for_offset(
            close, leg_open, leg_close, candidate, o, lane.COST_BPS_PRIMARY
        )
        mask = ret.index > kept_ts
        per_offset.append(window_metrics(ret, turn, rf, mask))
        if o == offsets[0]:
            forward_index = ret.index[mask]
    return combine_offsets(per_offset), forward_index


def benchmark_forward_metrics(
    ret: pd.Series, turn: pd.Series, rf: pd.Series, kept_ts: pd.Timestamp
) -> dict:
    mask = ret.index > kept_ts
    return window_metrics(ret, turn, rf, mask)


def anchor_dd_for(module_path: str, candidate_id: str) -> tuple[float | None, str | None]:
    """Anchor-window max DD from the frozen batch leaderboard (the same
    number the `watch_recent` K1 threshold was judged against at keep time),
    used as the reference for the exit rule's 1.5x-DD leg."""
    batch_name = Path(module_path).stem
    leaderboard_path = SCREENS_DIR / batch_name / "leaderboard.json"
    if not leaderboard_path.exists():
        return None, f"leaderboard not found: {leaderboard_path}"
    data = json.loads(leaderboard_path.read_text(encoding="utf-8"))
    for c in data.get("candidates", []):
        if c.get("id") == candidate_id:
            dd = c.get("judged", {}).get("anchor", {}).get("max_dd")
            return (float(dd) if dd is not None else None), None
    return None, f"candidate {candidate_id!r} not found in {leaderboard_path}"


def watch_exit_status(
    tier: str, n: int, sharpe: float | None, max_dd: float | None, anchor_dd: float | None
) -> dict:
    if tier != "watch_recent":
        return {"applicable": False}
    if n < WATCH_EXIT_MIN_SESSIONS:
        return {
            "applicable": True,
            "n_forward_sessions": n,
            "status": "too early",
            "min_sessions_required": WATCH_EXIT_MIN_SESSIONS,
        }
    reasons: list[str] = []
    if sharpe is not None and sharpe < WATCH_EXIT_SHARPE_MIN:
        reasons.append(f"forward sharpe {sharpe:.2f} < {WATCH_EXIT_SHARPE_MIN}")
    if anchor_dd is not None and max_dd is not None:
        threshold = anchor_dd * WATCH_EXIT_DD_MULT  # both <= 0
        if max_dd < threshold:
            reasons.append(
                f"forward max DD {max_dd:.2%} exceeds 1.5x anchor DD "
                f"{anchor_dd:.2%} (threshold {threshold:.2%})"
            )
    status = "exit" if reasons else "hold"
    return {
        "applicable": True,
        "n_forward_sessions": n,
        "status": status,
        "reasons": reasons,
    }


# --------------------------------------------------------------------------
# orchestration
# --------------------------------------------------------------------------


def build_relations(lines: list[dict]) -> dict[str, str]:
    """id -> human-readable relation note, for `replaces`-linked lines. A
    replacement line's `replaces` value is matched against other lines' `id`
    first, then `candidate_id`, since the exact field an optimization
    iteration uses to point back at the base hasn't been fixed yet."""
    by_id = {ln["id"]: ln for ln in lines if "id" in ln}
    relations: dict[str, str] = {}
    for ln in lines:
        target = ln.get("replaces")
        if not target:
            continue
        this_id = ln.get("id", "?")
        base_id = target if target in by_id else None
        if base_id is None:
            for other in lines:
                if other.get("candidate_id") == target and other.get("id") != this_id:
                    base_id = other.get("id")
                    break
        relations[this_id] = f"replacement, replaces {target}"
        if base_id:
            relations[base_id] = f"base, replaced by {this_id}"
        else:
            relations[this_id] += " (base not found in kept.jsonl)"
    return relations


def process(lines: list[dict]) -> tuple[list[dict], list[dict]]:
    relations = build_relations(lines)
    dropped_rows: list[dict] = []
    trackable: list[dict] = []
    for ln in lines:
        tier = ln.get("tier", "")
        if tier.startswith(DROPPED_PREFIX):
            dropped_rows.append(
                {
                    "id": ln.get("id"),
                    "candidate_id": ln.get("candidate_id"),
                    "iteration": ln.get("iteration"),
                    "tier": "dropped",
                    "tier_raw": tier,
                    "dropped_note": ln.get("dropped_note"),
                    "status": "dropped, not tracked",
                }
            )
            continue
        trackable.append(ln)

    if not trackable:
        return [], dropped_rows

    # Load every module/candidate once up front so the panel load covers the
    # union of every candidate's universe in a single pass.
    loaded: list[tuple[dict, ModuleType, lane.ScreenCandidate]] = []
    for ln in trackable:
        module = load_candidate_module(ln["module"])
        candidate = find_candidate(module, ln["candidate_id"])
        loaded.append((ln, module, candidate))

    candidates = [c for _, _, c in loaded]
    symbols = lane.batch_symbols(candidates)
    close, open_ = load_forward_panel(symbols)
    leg_open, leg_close = salvage.legs(close, open_)
    rf = (close[lane.RF] / close[lane.RF].shift(1) - 1.0).fillna(0.0)
    s3_ret, s3_turn = lane.s3_incumbent(close, leg_open, leg_close, lane.COST_BPS_PRIMARY)
    spy_ret = (close["SPY"] / close["SPY"].shift(1) - 1.0).fillna(0.0)
    spy_turn = pd.Series(0.0, index=close.index)

    rows: list[dict] = []
    for ln, _module, candidate in loaded:
        module_path = ln["module"]
        recorded_commit = ln.get("commit")
        current_commit = git_file_commit_now(module_path)
        integrity = integrity_status(recorded_commit, current_commit)

        kept_ts = kept_at_to_ts(ln["kept_at"])
        row: dict = {
            "id": ln.get("id"),
            "candidate_id": ln.get("candidate_id"),
            "iteration": ln.get("iteration"),
            "module": module_path,
            "tier": ln.get("tier"),
            "relation": relations.get(ln.get("id")),
            "kept_at": ln.get("kept_at"),
            "freq": candidate.freq,
            "n_offsets": len(lane.offsets_for_freq(candidate.freq)),
            "commit_recorded": recorded_commit,
            "commit_now": current_commit,
            "integrity": integrity,
        }

        if integrity != "ok":
            row["excluded_from_verdict"] = True
            row["note"] = "rule changed after freeze -- excluded from any verdict"
            row["forward"] = {"n": None, "cum_return": None, "sharpe": None, "max_dd": None}
            row["s3"] = {"n": None, "cum_return": None, "sharpe": None, "max_dd": None}
            row["spy"] = {"n": None, "cum_return": None, "sharpe": None, "max_dd": None}
            row["watch_exit"] = {"applicable": False}
            rows.append(row)
            continue

        fwd, forward_index = candidate_forward_metrics(
            close, leg_open, leg_close, rf, candidate, kept_ts
        )
        row["forward"] = fwd
        row["forward_start"] = str(forward_index.min().date()) if len(forward_index) else None
        row["forward_end"] = str(forward_index.max().date()) if len(forward_index) else None
        row["s3"] = benchmark_forward_metrics(s3_ret, s3_turn, rf, kept_ts)
        row["spy"] = benchmark_forward_metrics(spy_ret, spy_turn, rf, kept_ts)

        anchor_dd, anchor_dd_note = anchor_dd_for(module_path, ln["candidate_id"])
        row["anchor_dd"] = anchor_dd
        if anchor_dd_note:
            row["anchor_dd_note"] = anchor_dd_note
        row["watch_exit"] = watch_exit_status(
            ln.get("tier", ""), fwd["n"], fwd["sharpe"], fwd["max_dd"], anchor_dd
        )
        rows.append(row)

    return rows, dropped_rows


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------


def pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x * 100:.1f}%"


def fmt(x: float | None, nd: int = 2) -> str:
    return "n/a" if x is None else f"{x:.{nd}f}"


def render_md(rows: list[dict], dropped_rows: list[dict], generated_at: str) -> str:
    lines = [
        "# Forward (shadow) tracking of kept candidates",
        "",
        f"Generated {generated_at}. T-20260928-07. Forward period = sessions strictly after"
        " `kept_at`; Sharpe/max DD reported only with >= 20 forward sessions"
        f" (`MIN_SHARPE_SESSIONS={MIN_SHARPE_SESSIONS}`). `watch_recent` exit rule needs >= "
        f"{WATCH_EXIT_MIN_SESSIONS} forward sessions.",
        "",
        "| id | tier | relation | integrity | n_fwd | fwd period | cum ret | sharpe | max DD"
        " | S3 cum ret | S3 sharpe | SPY cum ret | SPY sharpe | watch_exit |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        if r.get("excluded_from_verdict"):
            lines.append(
                f"| {r['id']} | {r['tier']} | {r.get('relation') or ''} |"
                " **rule changed after freeze -- excluded** |"
                " - | - | - | - | - | - | - | - | - | - |"
            )
            continue
        fwd = r["forward"]
        s3 = r["s3"]
        spy = r["spy"]
        period = f"{r.get('forward_start') or '-'}..{r.get('forward_end') or '-'}"
        we = r["watch_exit"]
        we_txt = "n/a"
        if we.get("applicable"):
            we_txt = we["status"]
            if we.get("reasons"):
                we_txt += ": " + "; ".join(we["reasons"])
        lines.append(
            f"| {r['id']} | {r['tier']} | {r.get('relation') or ''} | {r['integrity']} |"
            f" {fwd['n']} | {period} | {pct(fwd['cum_return'])} | {fmt(fwd['sharpe'])} |"
            f" {pct(fwd['max_dd'])} | {pct(s3['cum_return'])} | {fmt(s3['sharpe'])} |"
            f" {pct(spy['cum_return'])} | {fmt(spy['sharpe'])} | {we_txt} |"
        )
    lines += ["", "## Dropped (not tracked)", ""]
    if dropped_rows:
        lines += ["| id | tier_raw | dropped_note |", "|---|---|---|"]
        for d in dropped_rows:
            lines.append(f"| {d['id']} | {d['tier_raw']} | {d.get('dropped_note') or ''} |")
    else:
        lines.append("(none)")
    return "\n".join(lines) + "\n"


def main() -> int:
    lines = load_kept_lines()
    generated_at = pd.Timestamp.now(tz="UTC").isoformat()
    if not lines:
        OUT_MD.write_text(
            f"# Forward (shadow) tracking of kept candidates\n\nGenerated {generated_at}."
            " kept.jsonl is empty -- nothing to track.\n",
            encoding="utf-8",
        )
        OUT_JSON.write_text(
            json.dumps({"generated_at": generated_at, "rows": [], "dropped": []}, indent=2),
            encoding="utf-8",
        )
        print(f"wrote {OUT_MD} and {OUT_JSON} (kept.jsonl empty)")
        return 0

    rows, dropped_rows = process(lines)
    OUT_JSON.write_text(
        json.dumps(
            {"generated_at": generated_at, "rows": rows, "dropped": dropped_rows},
            indent=2,
            default=float,
        ),
        encoding="utf-8",
    )
    OUT_MD.write_text(render_md(rows, dropped_rows, generated_at), encoding="utf-8")
    print(f"wrote {OUT_MD} and {OUT_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
