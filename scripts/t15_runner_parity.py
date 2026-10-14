"""T-20261006-15 follow-up 2: replay the QQQ noise-band plugin through the real intraday runner
(SimBroker, local SIP minute bars) and compare with the research backtest.

Only sessions up to 2026-09-17 are loaded (2026-09-18 onward is the hold-out). The SIP minute
frame is the t15_minute QQQ panel (the same archive, already extracted), served through
FrameMinuteProvider instead of the 25 s archive scan; the runner engine code is unchanged.

  run:  scripts/heavy_run.sh --mem 0.8G -- uv run python scripts/t15_runner_parity.py run START END
  cmp:  uv run python scripts/t15_runner_parity.py compare START END
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
# v1 = first replay (previous close = last history minute close); v2 = plugin with the raw
# official previous close (default)
OUT_ROOT = (
    ROOT
    / "reports/research/control/scratch/t15"
    / os.environ.get("T15_PARITY_ROOT", "runner-parity-v2")
)
ITER = ROOT / "reports/research/iterations/t20261006_15_intraday_rules"
RAW_DAILY = ROOT / "data/features/t15_raw_daily/QQQ.parquet"
CONFIG = ROOT / "config/intraday/runner-quant2.yaml"
HOLDOUT_START = pd.Timestamp("2026-09-18")
NY = "America/New_York"


def qqq_frame() -> pd.DataFrame:
    d = pd.read_parquet(ROOT / "data/features/t15_minute/QQQ.parquet")
    d = d[d["date"] < HOLDOUT_START]
    local = pd.to_datetime(d["date"]).dt.tz_localize(NY) + pd.to_timedelta(d["minute"], unit="min")
    out = pd.DataFrame(
        {
            "symbol": "QQQ",
            "timestamp": local.dt.tz_convert("UTC"),
            "open": d["open"],
            "high": d["high"],
            "low": d["low"],
            "close": d["close"],
            "volume": d["volume"],
            "trade_count": 0.0,
            "vwap": d["vwap"],
        }
    )
    return out.reset_index(drop=True)


def sessions(start: str, end: str) -> list[pd.Timestamp]:
    d = pd.read_parquet(ROOT / "data/features/t15_minute/QQQ.parquet", columns=["date"])
    days = pd.DatetimeIndex(sorted(d["date"].unique()))
    return list(days[(days >= pd.Timestamp(start)) & (days <= pd.Timestamp(end))])


def prev_close_file(day: pd.Timestamp) -> Path:
    """{symbol: official unadjusted close of the previous session} from the research raw dailies."""
    target = OUT_ROOT / "prev_close" / f"{day.date().isoformat()}.json"
    if target.exists():
        return target
    stop = pd.Timestamp(day.date(), tz="UTC")  # hold-out safe: nothing at or after the session
    raw = pd.read_parquet(RAW_DAILY, filters=[("timestamp", "<", stop)])
    local = pd.to_datetime(raw["timestamp"], utc=True).dt.tz_convert(NY).dt.tz_localize(None)
    raw = raw[local.dt.normalize() < day]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"QQQ": float(raw["close"].iloc[-1])}))
    return target


def run(start: str, end: str) -> None:
    from open_composer.intraday_runner import replay
    from open_composer.intraday_runner.bars import FrameMinuteProvider
    from open_composer.intraday_runner.config import load_runner_config

    frame = qqq_frame()
    replay.ArchiveMinuteProvider = lambda _root=None: FrameMinuteProvider(frame, "sip")
    config = load_runner_config(CONFIG)
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    for day in sessions(start, end):
        if day >= HOLDOUT_START:
            raise SystemExit("hold-out session requested")
        target = OUT_ROOT / day.date().isoformat()
        if (target / "done").exists():
            continue
        res = replay.replay_session(
            config,
            day.date(),
            target,
            slippage_bps=0.15,
            degrade_live=False,
            prev_close_file=prev_close_file(day),
        )
        (target).mkdir(parents=True, exist_ok=True)
        (target / "done").write_text(str(res["ticks"]))
        print(day.date(), "ticks", res["ticks"], flush=True)


def reference(start: str, end: str) -> dict:
    """Research backtest of the same spec (k30, M1, stop both, cap 1) per session."""
    import t15_engine as E

    p = E.Panel("QQQ", end=end)
    sig = E.noise_sigma(p, 14)
    P = E.a_position_paths(p, sig, 30, [1.0], ["both"])[(1.0, "both")]
    g, c, n, _ = E.a_daily(p, 30, P)
    lev = np.minimum(1.0, E.vol_target_lev(p))
    ms = E.check_slots(30)
    fills = p.o[:, ms + 1]
    # same position path, flat at the 15:58 open (the runner flatten), not the 15:59 close
    exit_px = p.o[:, 388]
    X = np.concatenate([fills, exit_px[:, None]], axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        seg = X[:, 1:] / X[:, :-1] - 1.0
    g1558 = np.nansum(np.where(np.isfinite(seg), P * seg, 0.0), axis=1)
    out = {}
    for d, day in enumerate(p.dates):
        if not (pd.Timestamp(start) <= day <= pd.Timestamp(end)):
            continue
        prev = 0.0
        ch = []
        for j in range(P.shape[1]):
            if P[d, j] != prev:
                ch.append([int(570 + ms[j] + 1), int(P[d, j])])
                prev = P[d, j]
        out[day.date().isoformat()] = {
            "changes": ch,
            "weight": float(lev[d]),
            "gross_bp_1559": float(lev[d] * g[d] * 1e4),
            "gross_bp_1558": float(lev[d] * g1558[d] * 1e4),
            "cost_bp": float(lev[d] * c[d] * 1e4),
        }
    return out


def runner_day(day: str) -> dict:
    events = []
    for f in (OUT_ROOT / day).rglob("events.jsonl"):
        events += [json.loads(line) for line in f.read_text().splitlines() if line.strip()]
    nets = {e["cid"]: e for e in events if e["type"] == "net_order"}
    pos = 0.0
    changes, flat_tick, pnl, traded = [], None, 0.0, 0.0
    for e in events:
        if e["type"] != "fill_sync":
            continue
        order = nets.get(e["cid"])
        if order is None:
            continue
        for a in e["allocs"]:
            if a["strategy"] != "noiseband_qqq_obs" or not a["qty"]:
                continue
            q, px = float(a["qty"]), float(a["price"])
            pos += q
            pnl -= q * px
            traded += abs(q) * px
        tick = pd.Timestamp(order["tick"]).tz_convert(NY)
        minute = tick.hour * 60 + tick.minute
        if order.get("flatten"):
            flat_tick = minute
        elif e.get("terminal"):
            changes.append([minute, int(np.sign(pos)) if abs(pos) > 0 else 0])
    signals = [e for e in events if e["type"] == "signal" and e.get("resolved")]
    errors = [e for e in events if e["type"] == "plugin_error"]
    halts = [e["reason"] for e in events if e["type"] == "halt"]
    return {
        "halts": halts,
        "changes": changes,
        "flatten_tick": flat_tick,
        "pnl_usd": pnl,
        "end_position": pos,
        "traded_usd": traded,
        "plugin_errors": len(errors),
        "signals": len(signals),
    }


def compare(start: str, end: str) -> None:
    ref = reference(start, end)
    rows, tot_ref, tot_run, hit, sess_ok, dir_ok, dir_n = [], 0, 0, 0, 0, 0, 0
    for day in sorted(ref):
        if not (OUT_ROOT / day / "done").exists():
            continue
        r, u = ref[day], runner_day(day)
        rc = [tuple(x) for x in r["changes"]]
        uc = [tuple(x) for x in u["changes"]]
        matched = len(set(rc) & set(uc))
        tot_ref += len(rc)
        tot_run += len(uc)
        hit += matched
        sess_ok += int(rc == uc)
        # direction of the k-th position change, regardless of time
        for a, b in zip(rc, uc, strict=False):
            dir_n += 1
            dir_ok += int(a[1] == b[1])
        run_bp = u["pnl_usd"] / 100_000.0 * 1e4
        rows.append({
            "date": day, "ref_changes": rc, "runner_changes": uc, "match": rc == uc,
            "ref_weight": r["weight"], "ref_gross_bp_1559": r["gross_bp_1559"],
            "ref_gross_bp_1558": r["gross_bp_1558"], "runner_gross_bp": run_bp,
            "runner_flatten_tick": u["flatten_tick"], "end_position": u["end_position"],
            "plugin_errors": u["plugin_errors"], "halts": u["halts"],
        })  # fmt: skip
    df = pd.DataFrame(rows)
    both = max(tot_ref, tot_run)
    diff = df[~df["match"]]
    unexplained = diff[diff["halts"].map(len) == 0]
    free = df[df["halts"].map(len) == 0]
    d_gross = df["runner_gross_bp"] - df["ref_gross_bp_1559"]
    d_1558 = df["runner_gross_bp"] - df["ref_gross_bp_1558"]
    summary = {
        "root": OUT_ROOT.name,
        "sessions_compared": len(df),
        "first": df["date"].min(), "last": df["date"].max(),
        "position_changes_reference": tot_ref, "position_changes_runner": tot_run,
        "changes_matched_exact_time_and_direction": hit,
        "match_rate_changes": hit / both if both else None,
        "direction_agreement_k_th_change": dir_ok / dir_n if dir_n else None,
        "sessions_with_identical_change_lists": int(df["match"].sum()),
        "session_match_rate": float(df["match"].mean()),
        "sessions_with_runner_loss_halt": int((df["halts"].map(len) > 0).sum()),
        "session_match_rate_excluding_halt_days": float(free["match"].mean()),
        "mismatched_sessions": diff["date"].tolist(),
        "mismatched_sessions_without_halt": unexplained["date"].tolist(),
        "sessions_with_plugin_errors": int((df["plugin_errors"] > 0).sum()),
        "days_runner_not_flat": int((df["end_position"].abs() > 0).sum()),
        "gross_bp_mean_abs_diff_vs_1559": float(d_gross.abs().mean()),
        "gross_bp_mean_abs_diff_vs_1558": float(d_1558.abs().mean()),
        "gross_bp_mean_abs_diff_vs_1558_matched_days": float(d_1558[df["match"]].abs().mean()),
        "gross_bp_corr_vs_1558": float(df["runner_gross_bp"].corr(df["ref_gross_bp_1558"])),
        "mean_gross_bp_runner": float(df["runner_gross_bp"].mean()),
        "mean_gross_bp_ref_1558": float(df["ref_gross_bp_1558"].mean()),
        "mean_gross_bp_ref_1559": float(df["ref_gross_bp_1559"].mean()),
        "flatten_tick_et_minute": {
            str(k): int(v)
            for k, v in df["runner_flatten_tick"].dropna().astype(int).value_counts().items()
        },
    }  # fmt: skip
    (ITER / os.environ.get("T15_PARITY_OUT", "runner-parity.json")).write_text(
        json.dumps({"summary": summary, "sessions": rows}, indent=1, default=str) + "\n"
    )
    print(json.dumps(summary, indent=1, default=str))


def stop_days(start: str, end: str, limit_bp: float = 250.0) -> dict:
    """Days on which the research backtest (no stop) would have touched a daily-loss line.

    Intraday mark to market of the full-weight sleeve: position set at the open of the bar after
    each check, marked on minute closes.  ``close`` = day result below the line, ``intraday`` =
    the worst intraday mark below the line.
    """
    import t15_engine as E

    p = E.Panel("QQQ", end=end)
    sig = E.noise_sigma(p, 14)
    P = E.a_position_paths(p, sig, 30, [1.0], ["both"])[(1.0, "both")]
    lev = np.minimum(1.0, E.vol_target_lev(p))
    ms = E.check_slots(30)
    pos = np.zeros((len(p.dates), E.NSLOT))
    for j, m in enumerate(ms):
        hi = ms[j + 1] + 1 if j + 1 < len(ms) else 388  # held until the 15:58 open
        pos[:, m + 1 : hi] = P[:, [j]]
    prev_c = np.concatenate([p.c[:, :1], p.c[:, :-1]], axis=1)
    prev_pos = np.concatenate([np.zeros((len(p.dates), 1)), pos[:, :-1]], axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        bar = prev_pos * (p.o / prev_c - 1.0) + pos * (p.c / p.o - 1.0)
    cum = np.nancumsum(np.where(np.isfinite(bar), bar, 0.0), axis=1) * lev[:, None] * 1e4
    sel = (p.dates >= pd.Timestamp(start)) & (p.dates <= pd.Timestamp(end))
    worst, last = cum[sel].min(axis=1), cum[sel][:, 388]
    days = p.dates[sel]
    out = {
        "window": [start, end],
        "sessions": int(sel.sum()),
        "line_bp": -limit_bp,
        "days_close_below": [str(d.date()) for d in days[last <= -limit_bp]],
        "days_intraday_below": [str(d.date()) for d in days[worst <= -limit_bp]],
        "worst_intraday_bp": float(worst.min()),
        "worst_close_bp": float(last.min()),
        "p01_intraday_bp": float(np.percentile(worst, 1)),
    }
    (ITER / "runner-parity-stop-days.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps({k: (len(v) if isinstance(v, list) else v) for k, v in out.items()}))
    return out


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "run":
        run(sys.argv[2], sys.argv[3])
    elif cmd == "stop":
        stop_days(sys.argv[2], sys.argv[3])
    elif cmd == "compare":
        compare(sys.argv[2], sys.argv[3])
