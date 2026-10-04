#!/usr/bin/env python3
"""Forward shadow log for h20261004_pm_midterm_odds_leadlag (T-20261004-53).

The preregistered forward sample (hypotheses.md): a daily log from 2026-10-05 through 2026-11-04,
the session after the 2026-11-03 election, under the same frozen definitions as the backtest
(``scripts/run_h20261004_pm_midterm_odds_leadlag.py``, imported, not copied). It places no order
and reads no account: Polymarket CLOB public history (no key) and SIP daily bars, read-only.

Subcommands
  signal   Between 15:40 and 15:55 ET on an NYSE session in the forward window, take the last
           House and Senate Republican Yes price at run time as the 16:00 proxy, compute the
           4pm-to-4pm change dP, the transformed signal (EMA span 5, 60-session percentile rank,
           map to [-1, 1]) and the per-asset positions for the next session, and append one line
           to ``data/features/prediction_markets/midterm_shadow/signals.jsonl``. Append-only and
           idempotent: a session already logged is never written again. Outside the window the
           command prints a message, exits 0 and writes nothing. A session missed by the cron is
           backfilled from the hourly 16:00 price and flagged ``late_backfill``.
  realize  After the SIP refresh, append the realized per-asset and basket returns of every logged
           position whose return session has a SIP bar to ``realized.jsonl``.
  summary  Forward-only statistics, labelled ``forward_only_no_decision``.

The Polymarket history before the forward window comes from
``data/research/prediction_markets/midterms/daily.parquet`` (scripts/build_pm_midterm_data.py).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import build_pm_midterm_data as bd  # noqa: E402
import run_h20261004_pm_midterm_odds_leadlag as rn  # noqa: E402

ET = ZoneInfo("America/New_York")
SHADOW_DIR = ROOT / "data/features/prediction_markets/midterm_shadow"
SIGNALS = "signals.jsonl"
REALIZED = "realized.jsonl"
DAILY_PARQUET = bd.OUT_DIR / "daily.parquet"
WINDOW_START = (15, 40)
WINDOW_END = (15, 55)
FORWARD_START = date(2026, 10, 5)
FORWARD_END = date(2026, 11, 4)
LABEL = "forward_only_no_decision"
MARKETS = {"house": bd.POLY_HOUSE_R_TOKEN, "senate": bd.POLY_SENATE_R_TOKEN}
BASE_SERIES = {"house": "polymarket_house_r", "senate": "polymarket_senate_r"}
RECENT_FIDELITIES = (1, 10, 60)
RECENT_LOOKBACK_S = 6 * 3600
WIDE_LOOKBACK_S = 10 * 86400


# ------------------------------------------------------------------ window guard


def is_session(day: date) -> bool:
    return bool(bd.sessions_between(day, day))


def next_session(day: date) -> date:
    return bd.sessions_between(day + timedelta(days=1), day + timedelta(days=10))[0]


def window_status(now: datetime) -> tuple[bool, date, str]:
    """(in window, session date in ET, message)."""
    local = now.astimezone(ET)
    today = local.date()
    if not is_session(today):
        return False, today, f"{today} is not an NYSE session; no signal window, nothing written"
    if not (FORWARD_START <= today <= FORWARD_END):
        return (
            False,
            today,
            f"{today} is outside the forward window "
            f"{FORWARD_START}..{FORWARD_END}; nothing written",
        )
    hm = (local.hour, local.minute)
    if not (WINDOW_START <= hm < WINDOW_END):
        return (
            False,
            today,
            f"outside the 15:40-15:55 ET window (now {local:%Y-%m-%d %H:%M} ET); nothing written",
        )
    return True, today, f"in window; signal session {today}"


# ------------------------------------------------------------------ small helpers


def code_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=10
        )
        return out.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _clean(value: Any) -> Any:
    if isinstance(value, (np.floating, float)):
        v = float(value)
        return None if not np.isfinite(v) else v
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    return value


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def append_jsonl(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:  # append only, earlier lines untouched
        for row in rows:
            fh.write(json.dumps(_clean(row)) + "\n")


# ------------------------------------------------------------------ prices


def price_at_or_before(http: Any, token: str, end_ts: int) -> tuple[float, int]:
    """Last CLOB point at or before ``end_ts``: minute data, then coarser, then wider."""
    for fidelity in RECENT_FIDELITIES:
        body = http.get(
            f"{bd.CLOB_BASE}/prices-history",
            {
                "market": token,
                "startTs": end_ts - RECENT_LOOKBACK_S,
                "endTs": end_ts,
                "fidelity": fidelity,
            },
            allow_404=True,
        )
        pts = sorted(
            (int(h["t"]), float(h["p"]))
            for h in (body or {}).get("history") or []
            if h["t"] <= end_ts
        )
        if pts:
            return pts[-1][1], pts[-1][0]
    body = http.get(
        f"{bd.CLOB_BASE}/prices-history",
        {
            "market": token,
            "startTs": end_ts - WIDE_LOOKBACK_S,
            "endTs": end_ts,
            "fidelity": 60,
        },
        allow_404=True,
    )
    pts = sorted((int(h["t"]), float(h["p"])) for h in (body or {}).get("history") or [])
    pts = [p for p in pts if p[0] <= end_ts]
    if not pts:
        raise RuntimeError(f"no CLOB price at or before {end_ts} for token {token[:8]}")
    return pts[-1][1], pts[-1][0]


def base_panel(daily_path: Path = DAILY_PARQUET) -> pd.DataFrame:
    daily = pd.read_parquet(daily_path)
    return rn.price_panel(daily, list(BASE_SERIES.values())).rename(
        columns={v: k for k, v in BASE_SERIES.items()}
    )


def panel_with_forward(base: pd.DataFrame, rows: Sequence[dict[str, Any]]) -> pd.DataFrame:
    """Backtest history plus every logged forward price pair (the proxies, as logged)."""
    extra = {
        pd.Timestamp(r["session"]): {"house": r["price_house"], "senate": r["price_senate"]}
        for r in rows
        if r.get("record_type") == "signal" and r["session"] > "2026-10-02"
    }
    if not extra:
        return base.copy()
    forward = pd.DataFrame.from_dict(extra, orient="index")
    out = pd.concat([base[~base.index.isin(forward.index)], forward]).sort_index()
    return out[["house", "senate"]]


# ------------------------------------------------------------------ signal command


def positions_for(signal: float) -> dict[str, float]:
    dirs = rn.direction_vector(bd.ASSETS)
    return {t: float(signal * d) for t, d in zip(bd.ASSETS, dirs, strict=True)}


def signal_row(
    session: date,
    panel: pd.DataFrame,
    prices: dict[str, tuple[float, int]],
    *,
    stamp: str,
    sha: str,
    late: bool,
) -> dict[str, Any]:
    ts = pd.Timestamp(session)
    full = panel.copy()
    full.loc[ts, "house"] = prices["house"][0]
    full.loc[ts, "senate"] = prices["senate"][0]
    full = full.sort_index()
    dp = rn.delta_p(full)
    sig = rn.transform(dp)
    value = sig.loc[ts]
    nxt = next_session(session)
    return {
        "record_type": "signal",
        "session": session,
        "return_session": nxt,
        "logged_at_utc": stamp,
        "late_backfill": late,
        "price_house": prices["house"][0],
        "price_senate": prices["senate"][0],
        "price_ts_house": prices["house"][1],
        "price_ts_senate": prices["senate"][1],
        "dp_pp": dp.loc[ts],
        "signal": None if pd.isna(value) else float(value),
        "n_history_sessions": int(dp.notna().sum()),
        "positions": None if pd.isna(value) else positions_for(float(value)),
        "code_commit": sha,
    }


def run_signal(
    now: datetime,
    http: Any,
    out_dir: Path = SHADOW_DIR,
    *,
    daily_path: Path = DAILY_PARQUET,
    dry_run: bool = False,
    log: Any = print,
) -> dict[str, Any]:
    ok, session, message = window_status(now)
    if not ok:
        log(message)
        return {"written": 0, "message": message}
    rows = read_jsonl(out_dir / SIGNALS)
    if any(r.get("record_type") == "signal" and r["session"] == session.isoformat() for r in rows):
        msg = f"{session} already logged; nothing written"
        log(msg)
        return {"written": 0, "message": msg}
    panel = panel_with_forward(base_panel(daily_path), rows)
    stamp = now.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    sha = code_commit()
    new_rows: list[dict[str, Any]] = []
    # sessions missed by earlier runs are backfilled at their true 16:00 price
    last_known = panel.index[-1].date()
    missing = [
        d for d in bd.sessions_between(last_known + timedelta(days=1), session) if d < session
    ]
    for day in missing:
        if day < FORWARD_START:
            continue
        cut = bd.cut_epoch(day)
        prices = {name: price_at_or_before(http, tok, cut) for name, tok in MARKETS.items()}
        row = signal_row(day, panel, prices, stamp=stamp, sha=sha, late=True)
        new_rows.append(row)
        panel.loc[pd.Timestamp(day), ["house", "senate"]] = [
            prices["house"][0],
            prices["senate"][0],
        ]
        panel = panel.sort_index()
    run_ts = int(now.timestamp())
    prices = {name: price_at_or_before(http, tok, run_ts) for name, tok in MARKETS.items()}
    new_rows.append(signal_row(session, panel, prices, stamp=stamp, sha=sha, late=False))
    if not dry_run:
        append_jsonl(out_dir / SIGNALS, new_rows)
    log(f"{'would write' if dry_run else 'wrote'} {len(new_rows)} line(s) for {session}")
    return {"written": 0 if dry_run else len(new_rows), "rows": new_rows, "message": message}


# ------------------------------------------------------------------ realize command


def realize_rows(
    signals: Sequence[dict[str, Any]],
    bars: dict[str, pd.Series],
    done: set[str],
    *,
    stamp: str,
    sha: str,
) -> tuple[list[dict[str, Any]], list[tuple[str, str]]]:
    sigs = [r for r in signals if r.get("record_type") == "signal"]
    sigs.sort(key=lambda r: r["session"])
    rows, skipped = [], []
    prev_pos: dict[str, float] = {t: 0.0 for t in bd.ASSETS}
    costs = dict(zip(bd.ASSETS, rn.cost_vector(bd.ASSETS), strict=True))
    for r in sigs:
        pos = r.get("positions")
        if pos is None:
            skipped.append((r["session"], "signal not valid (burn-in)"))
            continue
        if r["session"] in done:
            prev_pos = pos
            continue
        t0, t1 = pd.Timestamp(r["session"]), pd.Timestamp(r["return_session"])
        rets: dict[str, float] = {}
        for tk in bd.ASSETS:
            s = bars.get(tk)
            if s is None or t0 not in s.index or t1 not in s.index:
                continue
            rets[tk] = float(s.at[t1] / s.at[t0] - 1.0)
        if len(rets) < len(bd.ASSETS) * bd.MIN_ASSET_COVERAGE:
            skipped.append((r["session"], "return session not yet in SIP daily"))
            continue
        gross = float(np.mean([pos[t] * rets[t] for t in rets]))
        cost = float(
            np.mean([abs(pos[t] - prev_pos.get(t, 0.0)) * costs[t] / 1e4 for t in bd.ASSETS])
        )
        cat_gross = {}
        for cat, tickers in bd.CATEGORIES.items():
            have = [t for t in tickers if t in rets]
            cat_gross[cat] = float(np.mean([pos[t] * rets[t] for t in have])) if have else None
        rows.append(
            {
                "record_type": "realized",
                "session": r["session"],
                "return_session": r["return_session"],
                "late_backfill": r.get("late_backfill", False),
                "n_assets": len(rets),
                "basket_gross": gross,
                "turnover_cost": cost,
                "basket_net": gross - cost,
                "category_gross": cat_gross,
                "returns": rets,
                "logged_at_utc": stamp,
                "code_commit": sha,
            }
        )
        prev_pos = pos
    return rows, skipped


def run_realize(
    bars: dict[str, pd.Series], out_dir: Path = SHADOW_DIR, *, log: Any = print
) -> dict[str, Any]:
    signals = read_jsonl(out_dir / SIGNALS)
    done = {r["session"] for r in read_jsonl(out_dir / REALIZED)}
    stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows, skipped = realize_rows(signals, bars, done, stamp=stamp, sha=code_commit())
    append_jsonl(out_dir / REALIZED, rows)
    for session, why in skipped:
        log(f"{session}: not realized ({why})")
    log(f"realized {len(rows)} session(s)")
    return {"realized": len(rows), "skipped": skipped}


# ------------------------------------------------------------------ summary command


def summarize(out_dir: Path = SHADOW_DIR) -> dict[str, Any]:
    signals = [r for r in read_jsonl(out_dir / SIGNALS) if r.get("record_type") == "signal"]
    realized = [r for r in read_jsonl(out_dir / REALIZED) if r.get("record_type") == "realized"]
    net = np.array([r["basket_net"] for r in realized], dtype=float)
    gross = np.array([r["basket_gross"] for r in realized], dtype=float)
    remaining = [d for d in bd.sessions_between(FORWARD_START, FORWARD_END)]
    logged = {r["session"] for r in signals}
    out: dict[str, Any] = {
        "label": LABEL,
        "window": f"{FORWARD_START}..{FORWARD_END}",
        "signals_logged": len(signals),
        "late_backfills": sum(1 for r in signals if r.get("late_backfill")),
        "sessions_in_window": len(remaining),
        "sessions_not_logged": sum(1 for d in remaining if d.isoformat() not in logged),
        "realized_sessions": len(realized),
        "mean_net_bp": float(net.mean() * 1e4) if len(net) else None,
        "mean_gross_bp": float(gross.mean() * 1e4) if len(gross) else None,
        "cumulative_net_pct": float((np.prod(1 + net) - 1) * 100) if len(net) else None,
        "hit_rate_net": float((net > 0).mean()) if len(net) else None,
        "sharpe_net_annualized": rn.sharpe(net) if len(net) >= 5 else None,
        "nw_t_net": rn.nw_t(net) if len(net) >= 10 else None,
        "note": "forward only, no decision; the verdict rules apply to the backtest "
        "(and, if inconclusive, backtest plus forward on 2026-11-05 by the lead)",
    }
    return out


def format_summary(s: dict[str, Any]) -> str:
    def f(x: Any, nd: int = 2) -> str:
        return "n/a" if x is None else f"{x:.{nd}f}"

    return "\n".join(
        [
            f"Midterm odds forward shadow: {s['label']} ({s['window']})",
            f"signals logged {s['signals_logged']} (late backfills {s['late_backfills']}); "
            f"sessions in window {s['sessions_in_window']}, not logged {s['sessions_not_logged']}",
            f"realized sessions {s['realized_sessions']}: mean net {f(s['mean_net_bp'])} bp/day, "
            f"mean gross {f(s['mean_gross_bp'])} bp/day, "
            f"cumulative net {f(s['cumulative_net_pct'])}%",
            f"hit rate {f(s['hit_rate_net'])}, Sharpe {f(s['sharpe_net_annualized'])} "
            f"(needs 5+ sessions), NW t {f(s['nw_t_net'])} (needs 10+ sessions)",
        ]
    )


# ----------------------------------------------------------------------- main


def _make_http() -> Any:
    import importlib

    module = importlib.import_module("collect_prediction_markets")
    return module.Http(budget_s=110.0)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_sig = sub.add_parser("signal")
    p_sig.add_argument("--now", help="ISO UTC time override (tests / dry runs)")
    p_sig.add_argument("--dry-run", action="store_true", help="compute, print, write nothing")
    p_sig.add_argument("--out-dir", type=Path, default=SHADOW_DIR)
    p_real = sub.add_parser("realize")
    p_real.add_argument("--out-dir", type=Path, default=SHADOW_DIR)
    p_sum = sub.add_parser("summary")
    p_sum.add_argument("--out-dir", type=Path, default=SHADOW_DIR)
    args = parser.parse_args(argv)
    os.chdir(ROOT)
    if args.cmd == "signal":
        now = (
            datetime.fromisoformat(args.now.replace("Z", "+00:00"))
            if args.now
            else datetime.now(UTC)
        )
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        ok, _, message = window_status(now)
        if not ok:  # guard before any network or file access
            print(message)
            return 0
        result = run_signal(now, _make_http(), args.out_dir, dry_run=args.dry_run)
        print(json.dumps({k: v for k, v in result.items() if k != "rows"}))
        return 0
    if args.cmd == "realize":
        sessions = bd.sessions_between(
            FORWARD_START - timedelta(days=5), FORWARD_END + timedelta(days=7)
        )
        bars = bd.load_bars(bd.ASSETS, sessions[0], sessions[-1])
        run_realize(bars, args.out_dir)
        return 0
    print(format_summary(summarize(args.out_dir)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
