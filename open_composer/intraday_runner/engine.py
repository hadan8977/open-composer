"""The runner engine: one ``tick`` = sync orders -> bars -> risk -> plugins -> net -> submit.

Order of effects inside a tick is the audit trail: ``signal`` (also written to
``signal_logs/``) -> ``intent`` -> ``net_order`` (write-ahead, deterministic client order id)
-> ``submit_result`` -> ``fill_sync``.  Anything after a ``net_order`` that never reached
``submit_result`` is re-checked against the broker by client order id on restart.
"""

from __future__ import annotations

import hashlib
import math
import time as _time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from open_composer.intraday_runner import risk
from open_composer.intraday_runner.bars import SessionBars, load_history, session_bounds
from open_composer.intraday_runner.books import (
    EventLog,
    OrderRecord,
    SessionState,
    allocate_increment,
    replay,
)
from open_composer.intraday_runner.broker import Broker, DuplicateClientOrderId, OrderInfo
from open_composer.intraday_runner.config import RunnerConfig, StrategyConfig
from open_composer.intraday_runner.plugins import (
    PluginContext,
    PluginDecision,
    assert_point_in_time,
    build_plugin,
)
from open_composer.market_calendar import NEW_YORK
from open_composer.paper_intraday import _client_order_id, intraday_dir
from open_composer.storage import append_jsonl, ensure_dir

MAX_REJECTS_PER_SYMBOL = 3
CANCEL_OPEN_MIN_AGE_SECONDS = 20.0


def runner_dir(root: Path, account: str) -> Path:
    return intraday_dir(root) / "runner" / account


def _et_minutes(ts: pd.Timestamp) -> int:
    local = ts.tz_convert(NEW_YORK)
    return local.hour * 60 + local.minute


def strategy_due(cfg: StrategyConfig, decision_ts: pd.Timestamp) -> bool:
    offset = _et_minutes(decision_ts) - (9 * 60 + 30)
    return offset > 0 and offset % cfg.minutes == 0


def default_kill_check(root: Path) -> Callable[[], str | None]:
    """Global paper kill switch; a missing or inconsistent control file fails closed."""

    def check() -> str | None:
        from open_composer.paper_controls import load_paper_kill_switch

        try:
            state = load_paper_kill_switch(root, require_control_file=True)
        except Exception as exc:
            return f"kill switch unreadable ({exc.__class__.__name__}): failing closed"
        return f"paper kill switch enabled: {state.reason}" if state.enabled else None

    return check


@dataclass
class TickReport:
    tick: str
    signals: int = 0
    net_orders: int = 0
    submitted: int = 0
    blocked: list[str] = field(default_factory=list)
    flatten: bool = False
    skipped: str | None = None


class RunnerEngine:
    def __init__(
        self,
        config: RunnerConfig,
        root: Path,
        session: date,
        broker: Broker,
        bars: SessionBars,
        history_provider: Any | None = None,
        *,
        submit_orders: bool = True,
        mode: str = "paper",
        auth_id: str = "none",
        kill_check: Callable[[], str | None] | None = None,
        stop_file: Path | None = None,
        sleep: Callable[[float], None] = _time.sleep,
        event_dir: Path | None = None,
        signal_log: Path | None = None,
        poll_attempts: int = 3,
        poll_interval_s: float = 1.0,
        opening: dict[str, Any] | None = None,
    ):
        self.config, self.root, self.session = config, Path(root), session
        self.broker, self.bars, self.history_provider = broker, bars, history_provider
        self.submit_orders, self.mode, self.auth_id = submit_orders, mode, auth_id
        self.kill_check = kill_check or default_kill_check(self.root)
        self.sleep, self.poll_attempts, self.poll_interval_s = sleep, poll_attempts, poll_interval_s
        base = runner_dir(self.root, config.account)
        suffix = "" if submit_orders else "-plan"
        self.event_dir = event_dir or base / f"{session.isoformat()}{suffix}"
        self.stop_file = stop_file or base / "STOP"
        self.signal_log = signal_log or (
            self.root / "signal_logs" / f"paper-intraday-runner-{config.account}.jsonl"
        )
        self.log = EventLog(self.event_dir / "events.jsonl")
        self.state: SessionState = replay(config, session.isoformat(), self.log)
        self.plugins = {
            s.name: build_plugin(s.plugin, s.params, s.symbols, s.timeframe)
            for s in config.strategies
        }
        self._history_all: pd.DataFrame | None = None
        self._asset_cache: dict[str, bool] = {}
        self._signals: dict[tuple[str, str], dict[str, Any]] = {}
        for event in self.log.read():
            if event.get("type") == "signal":
                self._signals[(event["strategy"], event["tick"])] = event
        _, close_ts = session_bounds(session)
        self.close_ts = close_ts
        flat = pd.Timestamp(
            datetime.combine(session, config.flatten_et, tzinfo=NEW_YORK)
        ).tz_convert("UTC")
        self.flatten_ts = min(flat, close_ts - pd.Timedelta(minutes=5))
        self._opening = opening or {}

    # -- events ------------------------------------------------------------------------
    def emit(self, event: dict[str, Any], now: datetime | None = None) -> None:
        event.setdefault("ts", (now or datetime.now(UTC)).isoformat())
        self.log.append(event)
        self.state.apply(event)

    def start(self, now: datetime | None = None) -> None:
        if not self.state.started:
            self.emit(
                {
                    "type": "session_start",
                    "session": self.session.isoformat(),
                    "account": self.config.account,
                    "config_hash": self.config.content_hash,
                    "auth_id": self.auth_id,
                    "mode": self.mode,
                    "submit_orders": self.submit_orders,
                    "feed": self.bars.feed,
                    "opening": self._opening,
                },
                now,
            )

    # -- helpers -----------------------------------------------------------------------
    def _history_for(self, cfg: StrategyConfig, plugin: Any) -> pd.DataFrame:
        """Prior-session minute bars for ``cfg`` (loaded once for all strategies)."""
        days = int(getattr(plugin, "history_days", 0))
        if days <= 0 or self.history_provider is None:
            return pd.DataFrame()
        if self._history_all is None:
            most = max(int(getattr(p, "history_days", 0)) for p in self.plugins.values())
            self._history_all = load_history(
                self.history_provider, self.config.all_symbols, self.session, most
            )
        frame = self._history_all
        if frame.empty:
            return frame
        frame = frame[frame["symbol"].isin(cfg.symbols)]
        local = pd.to_datetime(frame["timestamp"], utc=True).dt.tz_convert(NEW_YORK).dt.date
        keep_days = sorted(local.unique())[-days:]
        return frame[local.isin(keep_days)].reset_index(drop=True)

    def preload(self) -> None:
        """Load prior-session history before the open (the archive scan takes ~30 s)."""
        for cfg in self.config.strategies:
            self._history_for(cfg, self.plugins[cfg.name])

    def _can_short(self, symbol: str) -> bool:
        if symbol not in self._asset_cache:
            try:
                self._asset_cache[symbol] = self.broker.asset(symbol).can_short
            except Exception:
                self._asset_cache[symbol] = False  # unknown -> not shortable (fail closed)
        return self._asset_cache[symbol]

    def _prices(self) -> dict[str, float]:
        return self.bars.last_prices()

    def _rejects(self, symbol: str) -> int:
        return sum(
            1
            for o in self.state.orders.values()
            if o.symbol == symbol and o.broker_status == "rejected"
        )

    # -- order lifecycle ---------------------------------------------------------------
    def _finalize(self, order: OrderRecord, info: OrderInfo, now: datetime) -> None:
        filled = int(round(info.filled_qty))
        incr = filled - int(round(order.filled_cum))
        allocs: list[dict[str, Any]] = []
        avg = info.filled_avg_price or order.avg_cum
        if incr > 0:
            price = (filled * avg - order.filled_cum * order.avg_cum) / incr
            remaining = order.remaining()
            cross = (
                0
                if order.cross_done
                else sum(abs(v) for v in remaining.values() if v * order.sign < 0)
            )
            shares = allocate_increment(
                remaining, order.sign, incr, include_cross=not order.cross_done
            )
            amount = incr + cross
            for strategy, qty in shares.items():
                crossed = abs(qty) if qty * order.sign < 0 else abs(qty) * cross / max(amount, 1)
                allocs.append(
                    {
                        "strategy": strategy,
                        "symbol": order.symbol,
                        "qty": qty,
                        "price": price,
                        "plan_price": order.plan_price,
                        "fee": self.config.fees.fee(qty, price),
                        "internal_qty": crossed,
                        "internal_cost": self._internal_cost(strategy, crossed, price),
                        "internal": False,
                    }
                )
        if incr > 0 or info.terminal or info.status != order.broker_status:
            self.emit(
                {
                    "type": "fill_sync",
                    "cid": order.cid,
                    "status": info.status,
                    "terminal": info.terminal,
                    "filled_cum": filled,
                    "avg_cum": avg,
                    "allocs": allocs,
                },
                now,
            )

    def _internal_cost(self, strategy: str, qty: float, price: float) -> float:
        """Shares crossed inside the account never pay the broker spread, but they are charged
        the strategy's modelled cost (``assumed_cost_bps``), not zero."""
        return qty * price * self.config.strategy(strategy).assumed_cost_bps / 1e4

    def _finalize_internal(self, order: OrderRecord, now: datetime) -> None:
        """Netted to zero: strategies cross against each other at the plan price, no broker call."""
        allocs = [
            {
                "strategy": strategy,
                "symbol": order.symbol,
                "qty": qty,
                "price": order.plan_price,
                "plan_price": order.plan_price,
                "fee": 0.0,
                "internal_qty": abs(qty),
                "internal_cost": self._internal_cost(strategy, abs(qty), order.plan_price),
                "internal": True,
            }
            for strategy, qty in order.parts.items()
            if qty
        ]
        self.emit(
            {
                "type": "fill_sync",
                "cid": order.cid,
                "status": "internal_cross",
                "terminal": True,
                "filled_cum": 0,
                "avg_cum": order.plan_price,
                "allocs": allocs,
            },
            now,
        )

    def _submit(self, order: OrderRecord, now: datetime) -> None:
        blocked = self.kill_check()
        if blocked:
            self.emit({"type": "order_abandoned", "cid": order.cid, "reason": blocked}, now)
            return
        foreign = [
            o
            for o in self.broker.open_orders()
            if o.symbol == order.symbol and o.side != order.side and o.cid not in self.state.orders
        ]
        if foreign:  # not ours: never cancel it, never trade into a wash-trade rejection
            self.emit(
                {
                    "type": "order_abandoned",
                    "cid": order.cid,
                    "reason": "foreign_opposite_open_order",
                },
                now,
            )
            return
        try:
            info = self.broker.submit_market(order.symbol, order.side, order.qty, order.cid)
        except DuplicateClientOrderId:
            info = self.broker.get_order(order.cid)
            if info is None:
                raise
        except Exception as exc:
            self.emit(
                {
                    "type": "submit_result",
                    "cid": order.cid,
                    "status": "rejected",
                    "error": f"{exc.__class__.__name__}: {exc}"[:300],
                },
                now,
            )
            self.emit(
                {
                    "type": "fill_sync",
                    "cid": order.cid,
                    "status": "rejected",
                    "terminal": True,
                    "filled_cum": 0,
                    "avg_cum": 0.0,
                    "allocs": [],
                },
                now,
            )
            return
        self.emit(
            {
                "type": "submit_result",
                "cid": order.cid,
                "broker_order_id": info.broker_order_id,
                "status": info.status,
            },
            now,
        )
        for attempt in range(self.poll_attempts):
            current = self.broker.get_order(order.cid) or info
            self._finalize(order, current, now)
            if order.status == "resolved":
                return
            if attempt + 1 < self.poll_attempts:
                self.sleep(self.poll_interval_s)

    def sync_orders(
        self, now: datetime, *, allow_submit: bool = True, cancel_open: bool = False
    ) -> None:
        """Restart/recovery and per-tick follow-up of every unresolved order.

        ``cancel_open`` (start of every tick): an order of an earlier tick that is still open is
        cancelled and the cancel confirmed *before* anything is planned, so a symbol never has
        an old order of one direction alive when a new order of the other direction goes out
        (Alpaca rejects that as a potential wash trade).  An unconfirmed cancel keeps the symbol
        blocked until it is confirmed."""
        for order in list(self.state.unresolved()):
            created = datetime.fromisoformat(order.created_at)
            age = (now - created).total_seconds()
            if order.status == "planned":
                info = self.broker.get_order(order.cid)
                if info is not None:  # accepted before the crash: adopt, never resubmit
                    self.emit(
                        {
                            "type": "submit_result",
                            "cid": order.cid,
                            "broker_order_id": info.broker_order_id,
                            "status": info.status,
                            "recovered": True,
                        },
                        now,
                    )
                elif not allow_submit:
                    continue  # kill switch: keep the intent, decide again when it is cleared
                elif self.submit_orders and (
                    order.flatten or age <= self.config.max_resubmit_age_seconds
                ):
                    self._submit(order, now)
                    continue
                else:
                    self.emit(
                        {
                            "type": "order_abandoned",
                            "cid": order.cid,
                            "reason": "plan_only" if not self.submit_orders else "stale",
                        },
                        now,
                    )
                    continue
            info = self.broker.get_order(order.cid)
            if info is None:
                continue
            self._finalize(order, info, now)
            due = age > self.config.order_ttl_seconds or (
                cancel_open and age >= CANCEL_OPEN_MIN_AGE_SECONDS
            )
            if order.status != "resolved" and due:
                self._cancel_and_confirm(order, now)

    def _cancel_and_confirm(self, order: OrderRecord, now: datetime) -> bool:
        self.broker.cancel(order.cid)
        for attempt in range(self.poll_attempts):
            after = self.broker.get_order(order.cid)
            if after is not None:
                self._finalize(order, after, now)
            if order.status == "resolved":
                self.emit({"type": "order_cancelled", "cid": order.cid}, now)
                return True
            if attempt + 1 < self.poll_attempts:
                self.sleep(self.poll_interval_s)
        return False  # still pending_cancel: the symbol stays blocked via pending_symbols()

    def persist_bars(self) -> None:
        """Keep the live minute bars on disk: the post-close SIP recheck compares against them."""
        if not self.bars.minute.empty:
            ensure_dir(self.event_dir)
            tmp = self.event_dir / "bars-live.parquet.tmp"
            self.bars.minute.to_parquet(tmp)
            tmp.replace(self.event_dir / "bars-live.parquet")

    # -- the tick ----------------------------------------------------------------------
    def tick(self, decision_ts: pd.Timestamp, now: datetime, *, stale: bool = False) -> TickReport:
        tick_id = decision_ts.isoformat()
        report = TickReport(tick=tick_id)
        self.start(now)
        reason = self.kill_check()
        self.sync_orders(now, allow_submit=not reason, cancel_open=True)
        if reason:
            report.skipped = reason
            self.emit({"type": "blocked", "tick": tick_id, "reason": reason}, now)
            return report
        self.bars.refresh(decision_ts)
        prices = self._prices()
        expected = decision_ts - pd.Timedelta(minutes=1)
        latest = self.bars.latest_minute()
        missing = {s for s in self.config.all_symbols if latest.get(s) != expected}
        self.emit(
            {
                "type": "bars",
                "tick": tick_id,
                "feed": self.bars.feed,
                "counts": self.bars.counts(),
                "missing_latest": sorted(missing),
            },
            now,
        )
        self._update_halts(prices, tick_id, now)
        stop_mode = self.stop_file.exists()
        account_halted = "account:all" in self.state.halts
        flatten_clock = decision_ts >= self.flatten_ts
        broker_pos = (
            self.broker.positions() if self.submit_orders else self.state.account_positions()
        )
        blocked_symbols = self._drift_symbols(broker_pos, now)

        self._check_stops(prices, decision_ts, tick_id, now)
        wants: dict[str, dict[str, tuple[int, str]]] = {}
        done_strategies: list[str] = []
        for cfg in self.config.strategies:
            halted = f"strategy:{cfg.name}" in self.state.halts
            sub = self.state.subs[cfg.name]
            flatten = (
                halted or account_halted or stop_mode or (flatten_clock and not cfg.allow_overnight)
            )
            report.flatten = report.flatten or flatten
            if flatten:
                symbols = set(self.state.standing[cfg.name]) | {
                    s for s, q in sub.positions.items() if q
                }
                wants[cfg.name] = {s: (0, "flat") for s in symbols}
                continue
            plugin = self.plugins[cfg.name]
            targets = {s: (q, "t") for s, q in self.state.standing[cfg.name].items()}
            due = (
                strategy_due(cfg, decision_ts) and (cfg.name, tick_id) not in self.state.ticks_done
            )
            if due and stale:
                self.emit(
                    {"type": "stale_skip", "tick": tick_id, "strategy": cfg.name},
                    now,
                )
                due = False
                done_strategies.append(cfg.name)
            if due:
                resolved = self._run_plugin(cfg, plugin, decision_ts, tick_id, prices, now, report)
                if resolved is not None:
                    targets.update({s: (q, "t") for s, q in resolved.items()})
                    done_strategies.append(cfg.name)
            for key, until in self.state.stops.items():  # stopped symbols stay flat in cooldown
                name, _, symbol = key.partition(":")
                if name == cfg.name and decision_ts < pd.Timestamp(until):
                    targets[symbol] = (0, "flat")
            wants[cfg.name] = targets

        intents = self._risk_and_intents(
            wants, prices, blocked_symbols, tick_id, now, report, missing
        )
        self._net_and_submit(intents, prices, broker_pos, decision_ts, tick_id, now, report)
        for name in done_strategies:
            self.emit({"type": "tick_done", "tick": tick_id, "strategy": name}, now)
        if _et_minutes(decision_ts) % 5 == 0:
            self.persist_bars()
        return report

    # -- halts / drift -----------------------------------------------------------------
    def _update_halts(self, prices: dict[str, float], tick_id: str, now: datetime) -> None:
        total = 0.0
        for cfg in self.config.strategies:
            pnl = self.state.subs[cfg.name].day_pnl(prices)
            total += pnl
            key = f"strategy:{cfg.name}"
            if key not in self.state.halts and risk.daily_loss_breached(
                pnl, cfg.caps.max_daily_loss_usd
            ):
                self.emit(
                    {
                        "type": "halt",
                        "scope": "strategy",
                        "name": cfg.name,
                        "reason": "max_daily_loss_usd",
                        "day_pnl": pnl,
                        "tick": tick_id,
                    },
                    now,
                )
        if "account:all" not in self.state.halts and risk.daily_loss_breached(
            total, self.config.account_caps.max_daily_loss_usd
        ):
            self.emit(
                {
                    "type": "halt",
                    "scope": "account",
                    "name": "all",
                    "reason": "account_max_daily_loss_usd",
                    "day_pnl": total,
                    "tick": tick_id,
                },
                now,
            )

    def _check_stops(
        self, prices: dict[str, float], decision_ts: pd.Timestamp, tick_id: str, now: datetime
    ) -> None:
        """Client-side stop: judged on the latest 1-minute close, executed through the normal
        net-order path (no broker-side stop or bracket orders in multi-strategy mode)."""
        for cfg in self.config.strategies:
            if cfg.stop_loss_pct <= 0:
                continue
            sub = self.state.subs[cfg.name]
            for symbol, qty in sub.positions.items():
                price, avg = prices.get(symbol), sub.avg_cost.get(symbol, 0.0)
                key = f"{cfg.name}:{symbol}"
                active = key in self.state.stops and decision_ts < pd.Timestamp(
                    self.state.stops[key]
                )
                if not qty or not price or avg <= 0 or active:
                    continue
                adverse = (avg - price) / avg * (1.0 if qty > 0 else -1.0)
                if adverse >= cfg.stop_loss_pct:
                    until = decision_ts + pd.Timedelta(minutes=cfg.stop_cooldown_minutes)
                    self.emit(
                        {
                            "type": "stop",
                            "tick": tick_id,
                            "strategy": cfg.name,
                            "symbol": symbol,
                            "adverse_fraction": adverse,
                            "price": price,
                            "avg_cost": avg,
                            "until": until.isoformat(),
                        },
                        now,
                    )

    def _drift_symbols(self, broker_pos: dict[str, float], now: datetime) -> set[str]:
        """Symbols whose broker position is not explained by the sub-accounts: never touched."""
        virtual = self.state.account_positions()
        pending = self.state.pending_symbols()
        blocked: set[str] = set()
        for symbol in set(broker_pos) | set(virtual):
            if symbol in pending:
                continue
            if abs(broker_pos.get(symbol, 0.0) - virtual.get(symbol, 0.0)) > 1e-6:
                blocked.add(symbol)
                if symbol not in self.state.drift_reported:
                    self.emit(
                        {
                            "type": "drift",
                            "symbol": symbol,
                            "broker": broker_pos.get(symbol, 0.0),
                            "virtual": virtual.get(symbol, 0.0),
                        },
                        now,
                    )
        return blocked

    # -- plugin call -------------------------------------------------------------------
    def _run_plugin(
        self,
        cfg: StrategyConfig,
        plugin: Any,
        decision_ts: pd.Timestamp,
        tick_id: str,
        prices: dict[str, float],
        now: datetime,
        report: TickReport,
    ) -> dict[str, int] | None:
        sub = self.state.subs[cfg.name]
        previous = self._signals.get((cfg.name, tick_id))
        if previous is not None:  # crash between signal and tick_done: reuse the decision
            return {k: int(v) for k, v in previous["resolved"].items()}
        ctx = PluginContext(
            strategy=cfg.name,
            session=self.session,
            decision_ts=decision_ts,
            timeframe=cfg.timeframe,
            bars=self.bars.aggregated(cfg.timeframe, cfg.symbols),
            history=self._history_for(cfg, plugin),
            positions={k: v for k, v in sub.positions.items() if v},
            last_prices={s: prices[s] for s in cfg.symbols if s in prices},
            state=dict(self.state.plugin_state.get(cfg.name, {})),
            capital_usd=cfg.capital_usd,
            day_pnl_usd=sub.day_pnl(prices),
        )
        try:
            assert_point_in_time(ctx)
            decision: PluginDecision = plugin.decide(ctx)
        except Exception as exc:
            self.emit(
                {
                    "type": "plugin_error",
                    "tick": tick_id,
                    "strategy": cfg.name,
                    "error": f"{exc.__class__.__name__}: {exc}"[:300],
                },
                now,
            )
            report.blocked.append(f"{cfg.name}:plugin_error")
            return None
        resolved: dict[str, int] = {}
        detail: dict[str, Any] = {}
        for symbol, target in decision.targets.items():
            symbol = symbol.upper()
            price = prices.get(symbol)
            if symbol not in cfg.symbols:
                report.blocked.append(f"{cfg.name}:{symbol}:not_in_universe")
                continue
            if target.shares is not None:
                shares = int(math.trunc(target.shares))
            elif price:
                shares = int(math.trunc(float(target.notional_usd or 0.0) / price))
            else:
                report.blocked.append(f"{cfg.name}:{symbol}:no_price")
                continue
            resolved[symbol] = shares
            detail[symbol] = {
                "shares": shares,
                "notional_usd": target.notional_usd,
                "ref_price": price,
                "reason": target.reason,
            }
        event = {
            "type": "signal",
            "tick": tick_id,
            "strategy": cfg.name,
            "targets": detail,
            "resolved": resolved,
            "state_before": dict(ctx.state),
            "state": decision.state,
            "positions_before": dict(ctx.positions),
            "capital_usd": cfg.capital_usd,
            "day_pnl_usd": ctx.day_pnl_usd,
            "note": decision.note,
            "feed": self.bars.feed,
        }
        self.emit(event, now)
        self._signals[(cfg.name, tick_id)] = event
        report.signals += 1
        append_jsonl(
            self.signal_log,
            [
                {
                    "id": "sig_"
                    + hashlib.sha256(
                        f"{self.config.account}|{cfg.name}|{tick_id}|{symbol}".encode()
                    ).hexdigest()[:16],
                    "strategy_name": cfg.name,
                    "kind": "intraday_runner_target",
                    "symbol": symbol,
                    "session": self.session.isoformat(),
                    "timestamp": tick_id,
                    "action": "target",
                    "target_shares": item["shares"],
                    "reference_price": item["ref_price"],
                    "reason": item["reason"],
                    "feed": self.bars.feed,
                    "config_hash": self.config.content_hash,
                    "paper": True,
                    "created_at": now.isoformat(),
                }
                for symbol, item in detail.items()
            ],
        )
        return resolved

    # -- risk ----------------------------------------------------------------------------
    def _risk_and_intents(
        self,
        wants: dict[str, dict[str, tuple[int, str]]],
        prices: dict[str, float],
        blocked_symbols: set[str],
        tick_id: str,
        now: datetime,
        report: TickReport,
        missing: set[str],
    ) -> dict[str, dict[str, tuple[int, str]]]:
        pending = self.state.pending_symbols()
        out: dict[str, dict[str, tuple[int, str]]] = {}
        for cfg in self.config.strategies:
            sub = self.state.subs[cfg.name]
            approved_standing: dict[str, int] = {}
            for symbol, (wanted, kind) in wants.get(cfg.name, {}).items():
                current = sub.positions.get(symbol, 0.0)
                price = prices.get(symbol, 0.0)
                if kind != "flat" and symbol in missing:  # no bar, no trade (never fill zeros)
                    report.blocked.append(f"{cfg.name}:{symbol}:missing_bar")
                    continue
                if kind == "flat":
                    approved, status, why = 0, "ok", ""
                    approved_standing[symbol] = 0
                else:
                    other = sum(
                        abs(q) * prices.get(s, sub.avg_cost.get(s, 0.0))
                        for s, q in sub.positions.items()
                        if s != symbol
                    )
                    shortable = self._can_short(symbol) if wanted < 0 else None
                    decision = risk.clip_target(
                        cfg,
                        symbol=symbol,
                        wanted=wanted,
                        current=current,
                        price=price,
                        other_gross_usd=other,
                        orders_used=self.state.intents.get(cfg.name, 0),
                        shortable=shortable,
                    )
                    approved, status, why = decision.approved, decision.status, decision.reason
                    approved_standing[symbol] = approved
                if symbol in blocked_symbols or symbol in pending:
                    why = "unattributed_position" if symbol in blocked_symbols else "order_pending"
                    report.blocked.append(f"{cfg.name}:{symbol}:{why}")
                    continue
                if self._rejects(symbol) >= MAX_REJECTS_PER_SYMBOL:
                    report.blocked.append(f"{cfg.name}:{symbol}:rejected_too_often")
                    continue
                delta = approved - int(current)
                if status == "blocked" and delta == 0:
                    if kind != "flat" and wanted != int(current):
                        report.blocked.append(f"{cfg.name}:{symbol}:{why}")
                        self.emit(
                            {
                                "type": "intent",
                                "tick": tick_id,
                                "strategy": cfg.name,
                                "symbol": symbol,
                                "current": current,
                                "wanted": wanted,
                                "approved": approved,
                                "status": "blocked",
                                "reason": why,
                                "counted": False,
                            },
                            now,
                        )
                    continue
                if delta == 0:
                    continue
                counted = kind != "flat"
                self.emit(
                    {
                        "type": "intent",
                        "tick": tick_id,
                        "strategy": cfg.name,
                        "symbol": symbol,
                        "current": current,
                        "wanted": wanted,
                        "approved": approved,
                        "delta": delta,
                        "status": status,
                        "reason": why,
                        "counted": counted and risk.increases_exposure(current, approved),
                    },
                    now,
                )
                out.setdefault(symbol, {})[cfg.name] = (delta, kind)
            merged = {**self.state.standing[cfg.name], **approved_standing}
            merged = {k: v for k, v in merged.items() if v != 0}
            if merged != self.state.standing[cfg.name]:
                self.emit(
                    {"type": "standing", "strategy": cfg.name, "tick": tick_id, "targets": merged},
                    now,
                )
        return out

    # -- netting and submission -----------------------------------------------------------
    def _net_and_submit(
        self,
        intents: dict[str, dict[str, tuple[int, str]]],
        prices: dict[str, float],
        broker_pos: dict[str, float],
        decision_ts: pd.Timestamp,
        tick_id: str,
        now: datetime,
        report: TickReport,
    ) -> None:
        caps = self.config.account_caps
        acct = self.state.account_positions()
        gross = sum(abs(q) * prices.get(s, 0.0) for s, q in acct.items())
        plans = []
        for symbol, by_strategy in intents.items():
            parts = {name: delta for name, (delta, _kind) in by_strategy.items()}
            flatten = all(kind == "flat" for _d, kind in by_strategy.values())
            net = sum(parts.values())
            price = prices.get(symbol, 0.0)
            pos = acct.get(symbol, 0.0)
            if net and pos * net < 0 and abs(net) > abs(pos):  # never flip in one broker order
                parts = risk.shrink_parts(parts, int(-pos))
                net = sum(parts.values())
            reducing = abs(pos + net) < abs(pos)
            plans.append((0 if reducing else 1, symbol, parts, net, price, pos, flatten))
        plans.sort(key=lambda item: (item[0], item[1]))
        local_order_count = self.state.account_order_count()
        for _rank, symbol, parts, net, price, pos, flatten in plans:
            if net and price > 0:
                after = pos + net
                if abs(after) > abs(pos):
                    room = caps.max_gross_notional_usd - (gross - abs(pos) * price)
                    max_abs = math.floor(max(room, 0.0) / price)
                    if abs(after) > max_abs:
                        allowed = max(max_abs, abs(pos))
                        new_net = int(math.copysign(allowed, after) - pos)
                        parts = risk.shrink_parts(parts, new_net)
                        net = sum(parts.values())
                        report.blocked.append(f"account:{symbol}:max_gross_notional")
                    if net and local_order_count >= caps.max_orders_per_day:
                        report.blocked.append(f"account:{symbol}:max_orders_per_day")
                        continue
                gross += (abs(pos + net) - abs(pos)) * price
            parts = {k: v for k, v in parts.items() if v}
            if not parts:
                continue
            side = "buy" if net > 0 else "sell"
            if net == 0:
                side = "buy"
            hhmm = decision_ts.tz_convert(NEW_YORK).strftime("%H%M")
            purpose = f"{'f' if flatten else 't'}{hhmm}"
            cid = _client_order_id(
                f"runner-{self.config.account}",
                self.session,
                symbol,
                side,
                purpose + ("x" if net == 0 else ""),
            )
            if cid in self.state.orders:  # same tick replayed after a crash
                continue
            self.emit(
                {
                    "type": "net_order",
                    "tick": tick_id,
                    "cid": cid,
                    "symbol": symbol,
                    "side": side,
                    "qty": abs(net),
                    "purpose": purpose,
                    "plan_price": price,
                    "parts": parts,
                    "flatten": flatten,
                },
                now,
            )
            report.net_orders += 1
            order = self.state.orders[cid]
            if net == 0:
                self._finalize_internal(order, now)
                continue
            local_order_count += 1
            if not self.submit_orders:  # shadow: model fill, no broker call
                px = price * (1 + order.sign * self.config.shadow_slippage_bps / 1e4)
                self.emit(
                    {"type": "submit_result", "cid": cid, "status": "shadow", "shadow": True}, now
                )
                shadow = OrderInfo(cid, "shadow", "filled", symbol, side, order.qty, order.qty, px)
                self._finalize(order, shadow, now)
                continue
            self._submit(order, now)
            report.submitted += 1
