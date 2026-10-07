"""End-of-day: reconciliation, per-strategy daily summary, report, IEX-vs-SIP recheck."""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from open_composer.intraday_runner.bars import (
    FrameMinuteProvider,
    MinuteProvider,
    SessionBars,
    session_bounds,
)
from open_composer.intraday_runner.books import EventLog
from open_composer.intraday_runner.engine import RunnerEngine, runner_dir
from open_composer.intraday_runner.plugins import PluginContext, assert_point_in_time, build_plugin
from open_composer.storage import append_jsonl, ensure_dir, write_json


def build_reconcile(engine: RunnerEngine, prices: dict[str, float]) -> dict[str, Any]:
    state = engine.state
    shadow = not engine.submit_orders  # shadow books are reconciled against themselves only
    broker_pos = state.account_positions() if shadow else engine.broker.positions()
    virtual = state.account_positions()
    pos_diffs = [
        {"symbol": s, "broker": broker_pos.get(s, 0.0), "virtual": virtual.get(s, 0.0)}
        for s in sorted(set(broker_pos) | set(virtual))
        if abs(broker_pos.get(s, 0.0) - virtual.get(s, 0.0)) > 1e-6
    ]
    order_diffs = []
    for order in state.orders.values():
        if shadow or order.internal or order.status == "abandoned":
            continue
        info = engine.broker.get_order(order.cid)
        net_alloc = sum(order.alloc.values())
        broker_filled = int(round(info.filled_qty)) if info else 0
        if abs(net_alloc) != broker_filled and info is not None:
            order_diffs.append(
                {"cid": order.cid, "broker_filled": broker_filled, "allocated_net": net_alloc}
            )
    snap = engine.broker.account_snapshot() if not shadow else None
    strategy_pnl = sum(sub.day_pnl(prices) for sub in state.subs.values())
    internal = sum(sub.internal_cost for sub in state.subs.values())
    return {
        "broker_positions_open": {k: v for k, v in broker_pos.items() if v},
        "virtual_positions_open": virtual,
        "position_diffs": pos_diffs,
        "order_fill_diffs": order_diffs,
        "shadow": shadow,
        "broker_equity": snap.equity if snap else None,
        "broker_last_equity": snap.last_equity if snap else None,
        "broker_day_pnl": snap.equity - snap.last_equity if snap else None,
        "sum_strategy_net_pnl": strategy_pnl,
        "pnl_gap_usd": (snap.equity - snap.last_equity) - strategy_pnl if snap else None,
        "internal_cross_cost_usd": internal,
        "pnl_gap_ex_internal_usd": (
            (snap.equity - snap.last_equity) - strategy_pnl - internal if snap else None
        ),
        "ok": not pos_diffs and not order_diffs,
    }


def summary_rows(engine: RunnerEngine, prices: dict[str, float]) -> list[dict[str, Any]]:
    state = engine.state
    rows = []
    for cfg in engine.config.strategies:
        sub = state.subs[cfg.name]
        net = sub.day_pnl(prices)
        cost = sub.fees + sub.slippage_usd + sub.internal_cost
        traded = sub.traded_notional
        rows.append(
            {
                "session": engine.session.isoformat(),
                "account": engine.config.account,
                "strategy": cfg.name,
                "mode": engine.mode,
                "feed": engine.bars.feed,
                "fills": sub.fills,
                "orders_counted": state.intents.get(cfg.name, 0),
                "traded_notional_usd": traded,
                "gross_pnl_usd": net + cost,
                "fees_usd": sub.fees,
                "internal_cross_cost_usd": sub.internal_cost,
                "slippage_usd": sub.slippage_usd,
                "cost_usd": cost,
                "net_pnl_usd": net,
                "slippage_bps": sub.slippage_usd / traded * 1e4 if traded else None,
                "actual_cost_bps": cost / traded * 1e4 if traded else None,
                "assumed_cost_bps": cfg.assumed_cost_bps,
                "assumed_cost_usd": traded * cfg.assumed_cost_bps / 1e4,
                "open_positions": {k: v for k, v in sub.positions.items() if v},
                "halted": f"strategy:{cfg.name}" in state.halts,
                "net_return_on_capital": net / cfg.capital_usd,
            }
        )
    return rows


def finish_session(engine: RunnerEngine, now: datetime) -> dict[str, Any]:
    """Resolve open orders, reconcile, write the summary rows and the day report (once)."""
    engine.start(now)
    engine.sync_orders(now, allow_submit=False)
    for order in engine.state.unresolved():
        engine.broker.cancel(order.cid)
    engine.sync_orders(now, allow_submit=False)
    engine.bars.refresh(engine.close_ts)
    engine.persist_bars()
    prices = engine.bars.last_prices()
    reconcile = build_reconcile(engine, prices)
    rows = summary_rows(engine, prices)
    out_dir = engine.event_dir
    if not engine.state.summarized:
        engine.emit({"type": "reconcile", **reconcile}, now)
        engine.emit({"type": "summary", "rows": rows}, now)
        append_jsonl(runner_dir(engine.root, engine.config.account) / "daily-summary.jsonl", rows)
        _write_carry(engine, out_dir)
    report_path = out_dir / "report.md"
    report_path.write_text(render_day_report(engine, rows, reconcile), encoding="utf-8")
    return {"rows": rows, "reconcile": reconcile, "report": str(report_path)}


def _write_carry(engine: RunnerEngine, out_dir: Path) -> None:
    carry = {
        name: {
            "positions": {k: v for k, v in sub.positions.items() if v},
            "avg_cost": {k: v for k, v in sub.avg_cost.items() if sub.positions.get(k)},
        }
        for name, sub in engine.state.subs.items()
        if any(sub.positions.values())
    }
    write_json(out_dir / "carry.json", {"session": engine.session.isoformat(), "carry": carry})


def _num(value: Any, digits: int = 2) -> str:
    return (
        f"{value:,.{digits}f}" if isinstance(value, int | float) and not math.isnan(value) else "-"
    )


def render_day_report(
    engine: RunnerEngine, rows: list[dict[str, Any]], reconcile: dict[str, Any]
) -> str:
    state = engine.state
    lines = [
        f"# Intraday runner {engine.config.runner_name} -- {engine.session.isoformat()}",
        "",
        f"- account `{engine.config.account}`, mode `{engine.mode}`, "
        f"orders submitted: {engine.submit_orders}, live feed `{engine.bars.feed}`",
        f"- config hash `{engine.config.content_hash[:16]}`, authorization `{engine.auth_id}`",
        f"- halts: {state.halts or 'none'}; broker orders: {state.account_order_count()}",
        "",
        "| strategy | fills | orders | traded $ | gross pnl | fees | slippage $ | net pnl | "
        "slip bp | cost bp | assumed bp |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        lines.append(
            f"| {r['strategy']} | {r['fills']} | {r['orders_counted']} | "
            f"{_num(r['traded_notional_usd'], 0)} | {_num(r['gross_pnl_usd'])} | "
            f"{_num(r['fees_usd'])} | {_num(r['slippage_usd'])} | {_num(r['net_pnl_usd'])} | "
            f"{_num(r['slippage_bps'])} | {_num(r['actual_cost_bps'])} | "
            f"{_num(r['assumed_cost_bps'])} |"
        )
    lines += [
        "",
        "## Reconciliation",
        f"- broker positions open: {reconcile['broker_positions_open'] or 'none'}; "
        f"virtual: {reconcile['virtual_positions_open'] or 'none'}",
        f"- position diffs: {reconcile['position_diffs'] or 'none'}; "
        f"order fill diffs: {reconcile['order_fill_diffs'] or 'none'}",
        f"- sum of strategy net pnl {_num(reconcile['sum_strategy_net_pnl'])} vs broker equity "
        f"change {_num(reconcile['broker_day_pnl'])} (gap {_num(reconcile['pnl_gap_usd'])}; of "
        f"which internal-cross model cost {_num(reconcile['internal_cross_cost_usd'])}, the rest "
        f"{_num(reconcile['pnl_gap_ex_internal_usd'])} = marks at last bar close vs broker marks "
        "plus any non-runner activity)",
        f"- status: {'OK' if reconcile['ok'] else 'DIFFERENCES -- investigate'}",
    ]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# IEX (live) vs SIP (post-close) recheck


def _by_minute(frame: pd.DataFrame, symbol: str) -> pd.DataFrame:
    part = frame[frame["symbol"] == symbol].copy()
    part.index = pd.to_datetime(part["timestamp"], utc=True)
    return part[~part.index.duplicated(keep="last")]


def bar_diff(live: pd.DataFrame, sip: pd.DataFrame) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for symbol in sorted(set(live["symbol"]) | set(sip["symbol"])):
        a = _by_minute(live, symbol)
        b = _by_minute(sip, symbol)
        both = a.index.intersection(b.index)
        entry: dict[str, Any] = {
            "live_minutes": int(len(a)),
            "sip_minutes": int(len(b)),
            "common": int(len(both)),
            "missing_in_live": int(len(b.index.difference(a.index))),
            "missing_in_sip": int(len(a.index.difference(b.index))),
        }
        if len(both):
            la, lb = a.loc[both], b.loc[both]
            close_bps = ((la["close"] - lb["close"]) / lb["close"] * 1e4).abs()
            entry["close_diff_bps_median"] = float(close_bps.median())
            entry["close_diff_bps_p95"] = float(close_bps.quantile(0.95))
            entry["close_diff_bps_max"] = float(close_bps.max())
            denom = lb["volume"].replace(0, float("nan"))
            entry["volume_ratio_live_over_sip_median"] = float((la["volume"] / denom).median())
        out[symbol] = entry
    return out


def decision_diff(
    engine: RunnerEngine, sip_frame: pd.DataFrame, events: list[dict[str, Any]]
) -> dict[str, Any]:
    """Re-run every logged decision on SIP bars with the *logged* inputs (positions and plugin
    state before the decision), so any difference is due to the bars only."""
    sip_bars = SessionBars(
        FrameMinuteProvider(sip_frame, "sip"), engine.config.all_symbols, engine.session
    )
    compared = differing = sign_flips = 0
    details: list[dict[str, Any]] = []
    for event in events:
        if event.get("type") != "signal":
            continue
        cfg = engine.config.strategy(event["strategy"])
        decision_ts = pd.Timestamp(event["tick"])
        sip_bars.refresh(decision_ts)
        prices = sip_bars.last_prices()
        plugin = build_plugin(cfg.plugin, cfg.params, cfg.symbols, cfg.timeframe)
        ctx = PluginContext(
            strategy=cfg.name,
            session=engine.session,
            decision_ts=decision_ts,
            timeframe=cfg.timeframe,
            bars=sip_bars.aggregated(cfg.timeframe, cfg.symbols),
            history=engine._history_for(cfg, plugin),
            positions=event.get("positions_before", {}),
            last_prices={s: prices[s] for s in cfg.symbols if s in prices},
            state=event.get("state_before", {}),
            capital_usd=cfg.capital_usd,
            day_pnl_usd=event.get("day_pnl_usd", 0.0),
        )
        try:
            assert_point_in_time(ctx)
            decided = plugin.decide(ctx)
        except Exception as exc:
            details.append({"tick": event["tick"], "strategy": cfg.name, "error": str(exc)[:120]})
            continue
        for symbol, live_shares in event.get("resolved", {}).items():
            target = decided.targets.get(symbol)
            if target is None:
                sip_shares = None
            elif target.shares is not None:
                sip_shares = int(math.trunc(target.shares))
            else:
                price = prices.get(symbol)
                sip_shares = int(math.trunc(target.notional_usd / price)) if price else None
            compared += 1
            if sip_shares != live_shares:
                differing += 1
                flip = sip_shares is not None and (sip_shares > 0) != (live_shares > 0)
                sign_flips += int(flip and (sip_shares != 0 or live_shares != 0))
                if len(details) < 50:
                    details.append(
                        {
                            "tick": event["tick"],
                            "strategy": cfg.name,
                            "symbol": symbol,
                            "live_shares": live_shares,
                            "sip_shares": sip_shares,
                        }
                    )
    return {
        "decisions_compared": compared,
        "decisions_differing": differing,
        "differing_rate": differing / compared if compared else None,
        "side_changes": sign_flips,
        "examples": details,
    }


def sip_recheck(engine: RunnerEngine, sip_provider: MinuteProvider) -> dict[str, Any]:
    """Post-close: SIP minute bars for the session vs what the runner saw live, and the
    decision-level consequence.  Written to ``sip-recheck.json`` next to the events."""
    open_ts, close_ts = session_bounds(engine.session)
    sip = sip_provider.fetch(engine.config.all_symbols, open_ts, close_ts)
    live_path = engine.event_dir / "bars-live.parquet"
    live = pd.read_parquet(live_path) if live_path.is_file() else engine.bars.minute
    events = EventLog(engine.event_dir / "events.jsonl").read()
    result = {
        "session": engine.session.isoformat(),
        "generated_at": datetime.now(UTC).isoformat(),
        "live_feed": engine.bars.feed,
        "sip_feed": sip_provider.feed,
        "bars": bar_diff(live, sip) if not sip.empty and not live.empty else {},
        "decisions": decision_diff(engine, sip, events) if not sip.empty else {},
        "note": "decisions re-run on SIP bars with the logged positions/state; differences are "
        "attributable to the bars alone",
    }
    ensure_dir(engine.event_dir)
    (engine.event_dir / "sip-recheck.json").write_text(
        json.dumps(result, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )
    return result
