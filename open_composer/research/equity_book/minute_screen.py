"""Replay point-in-time stock candidate days with regular-session SIP bars in quoted units."""

from __future__ import annotations

import argparse
import json
import logging
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import date, datetime, time
from functools import cache
from heapq import heappop, heappush
from pathlib import Path
from time import perf_counter
from uuid import uuid4

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from open_composer.lab.accounting import turnover_cost
from open_composer.lab.ledger import TrialLedger
from open_composer.market_sessions import NEW_YORK, next_us_equity_session, us_equity_session_close
from open_composer.models.strategy_spec import StrategySpec
from open_composer.research.equity_book.costs import HS_BP_CAP
from open_composer.research.equity_book.daily_screen import UNIVERSE, WINDOWS
from open_composer.research.equity_book.minute_bars import ALL_END, MinuteBars
from open_composer.research.features.news_attention import (
    load_earnings_gaps,
    load_earnings_releases,
)
from open_composer.research.features.panel import _connect
from open_composer.research.features.price_hygiene import DEFAULT_MAX_ONE_DAY_PRICE_RATIO

MINUTE = pd.Timedelta(minutes=1)
OPEN = time(9, 30)
COSTS = (10, 20)
PARTICIPATION = .01
SPREAD_TABLE = Path(__file__).with_name("minute_half_spread_v1.json")
TRADE_COLUMNS = [
    "symbol", "session", "side", "entry_time", "entry_price", "exit_time",
    "exit_price", "shares", "entry_cost_usd", "exit_cost_usd", "cost_usd",
    "pnl_usd", "exit_reason", "exit_above_minute_cap", "closed_shares",
]


@dataclass(frozen=True)
class MinuteRule:
    """Opening range or limit entry, fixed RAW stop/target, exchange-local time exit.

    A range rule uses the opposite range edge when stop is omitted.
    hold_sessions counts additional sessions. An overnight hold liquidates
    at the terminal session close and requires exit_at=None.
    """

    range_minutes: int = 5
    limit: float | None = None
    stop: float | None = None
    target: float | None = None
    exit_at: time | None = None
    hold_sessions: int = 0
    price_guard_bp: float = 100.0

    def __post_init__(self):
        if self.range_minutes < 1 or self.hold_sessions < 0 or self.price_guard_bp < 0:
            raise ValueError("Invalid minute rule counts or price guard")
        if self.limit is not None and self.stop is None:
            raise ValueError("Limit entry needs a fixed stop")
        if self.exit_at is not None and (self.exit_at <= OPEN or self.hold_sessions):
            raise ValueError("Clock exit must follow the open and requires an intraday rule")


@cache
def _stamp(day: date, clock: time) -> pd.Timestamp:
    return pd.Timestamp(datetime.combine(day, clock, NEW_YORK)).tz_convert("UTC")


@cache
def _spread_table():
    return json.loads(SPREAD_TABLE.read_text(encoding="utf-8"))


def minute_half_spreads(price, median_dollar_volume):
    """Opening, morning, midday and closing half-spreads from prior observations."""
    if not (0 < price < np.inf and 0 < median_dollar_volume < np.inf):
        return (HS_BP_CAP,) * 4
    table = _spread_table()
    dollars = np.searchsorted(table["median_dollar_volume_20_edges"], median_dollar_volume, side="right")
    price_bin = np.searchsorted(table["printed_price_edges"], price, side="right")
    opening, morning, midday, closing = table["rows"][dollars][price_bin]["half_spread_bp"]
    # Spreads narrow through the session; the five-day morning estimate may not undercut midday.
    return opening, max(morning, midday), midday, closing


def minute_half_spread_at(stamp, spreads):
    clock = stamp.tz_convert(NEW_YORK)
    if clock.time() < time(9, 45):
        return spreads[0]
    if stamp >= _stamp(clock.date(), us_equity_session_close(clock.date())) - 30 * MINUTE:
        return spreads[3]
    return spreads[1 if clock.time() < time(12) else 2]


def _fill_half_spread(stamp, spreads, price):
    # A quoted spread is at least one cent, so half a cent is the floor on cheap stocks.
    return max(minute_half_spread_at(stamp, spreads), 50.0 / price)


def _bracket(side, op, high, low, stop, target):
    """Return the first breach and its gap-aware RAW price."""
    worst = low if side == 1 else high
    best = high if side == 1 else low
    stops = side * (worst - stop) <= 0
    targets = (side * (best - target) >= 0) if target is not None else np.zeros_like(stops)
    hits = np.flatnonzero(stops | targets)
    if len(hits):
        i = hits[0]
        level, reason = (stop, "stop") if stops[i] else (target, "target")
        distance = side * (op[i] - level)
        through_open = distance <= 0 if stops[i] else distance >= 0
        return i, float(op[i] if through_open else level), reason, through_open


@dataclass
class Replay:
    symbol: str
    session: date
    side: int
    entry_time: pd.Timestamp
    entry_price: float
    entry_limit: int
    exit_limit: int
    reason: str
    marks: list[tuple[date, float]]
    fills: list
    last_day: date
    close_mark: float
    reopen: bool
    spreads: tuple[float, ...]


def _path(row, bars, archive, rule):
    day, side = row.session, row.side
    if bars is None:
        return "no_regular_minutes", None
    opening = _stamp(day, OPEN)
    close = _stamp(day, us_equity_session_close(day))
    deadline = min(close, _stamp(day, rule.exit_at)) if rule.exit_at else close
    session_bars = bars.loc[bars.volume > 0]
    bars = session_bars.loc[session_bars.index < deadline]
    t = bars.index
    op, high, low, volume = bars[["open", "high", "low", "volume"]].to_numpy().T
    if rule.limit is None:
        end_range = opening + rule.range_minutes * MINUTE
        in_range = t < end_range
        if in_range.sum() != rule.range_minutes:
            return "incomplete_opening_range", None
        lo, hi = low[in_range].min(), high[in_range].max()
        level = hi if side == 1 else lo
        stop = rule.stop if rule.stop is not None else (lo if side == 1 else hi)
        triggered = (~in_range) & (side * ((high if side == 1 else low) - level) > 0)
    else:
        level, stop = rule.limit, rule.stop
        triggered = side * ((low if side == 1 else high) - level) <= 0
    hits = np.flatnonzero(triggered & (row.known_at < t + MINUTE))
    if not len(hits):
        return "no_trigger", None
    i = hits[0] + 1
    if i == len(t) or t[i] != t[i - 1] + MINUTE:
        status = "no_next_minute" if t[i - 1] + MINUTE < deadline else "entry_cutoff"
        return status, None
    entry = op[i]
    adverse = side * (entry - level)
    guard = turnover_cost(level, rule.price_guard_bp) if rule.limit is None else 0
    if adverse > guard or side * (entry - stop) <= 0 or (
        rule.target is not None and side * (rule.target - entry) <= 0
    ):
        return "price_guard", None
    shares = int(volume[i - 1] * PARTICIPATION)
    if shares < 1:
        return "entry_participation", None

    spreads = row.half_spreads
    marks, fills, current = [], [], day
    entry_time = t[i]
    for holding in range(rule.hold_sessions + 1):
        if holding:
            current = next_us_equity_session(current)
            close = deadline = _stamp(current, us_equity_session_close(current))
            resumed = archive.continuation(row.symbol, current)
            session_bars = bars.iloc[:0] if resumed is None else resumed.loc[resumed.volume > 0]
            bars, i = session_bars, 0
            t = bars.index
            op, high, low, volume = bars[["open", "high", "low", "volume"]].to_numpy().T
            limit = DEFAULT_MAX_ONE_DAY_PRICE_RATIO
            if len(t) and not 1 / limit <= op[0] / mark <= limit:
                reason, exit_limit = "price_discontinuity", shares
                fills.append((t[0], mark, shares, minute_half_spread_at(t[0], spreads)))
                break
        if len(t):
            mark = float(session_bars.close.iat[-1])
        reopen = not len(session_bars) or session_bars.index[-1] + MINUTE != close
        hit = _bracket(side, op[i:], high[i:], low[i:], stop, rule.target)
        if hit:
            j, price, reason, through_open = hit
            j += i
            after = spread_at = t[j]
            exit_time = after if through_open else after + MINUTE
        elif holding < rule.hold_sessions:
            if current == archive.last_session:
                reason, exit_limit = "stale_time_mark", 0
                break
            marks.append((current, mark))
            continue
        else:
            after, spread_at, exit_time = deadline - MINUTE, deadline, deadline
            j = len(t) - 1 if len(t) and t[-1] == after else -1
            price, through_open = (float(bars.close.iat[j]) if j >= 0 else mark), False
            reason = "time" if j >= 0 else "stale_time_mark"
        exit_limit = int(volume[j - 1] * PARTICIPATION) if j > 0 and after - t[j - 1] == MINUTE else 0
        capacity = exit_limit or (shares if through_open and reason == "stop" else 0)
        if capacity:
            fills.append((exit_time, price, capacity, minute_half_spread_at(spread_at, spreads)))
        fills.extend(_exit_minutes(session_bars, after, spreads, shares - capacity, reopen=j < 0))
        reopen |= j < 0
        break
    return reason, Replay(
        row.symbol, day, side, entry_time, float(entry), shares, exit_limit,
        reason, marks, fills, current, mark, reopen, spreads,
    )


def _replays(candidates, rule, archive):
    counts = {label: Counter() for label in WINDOWS}
    replays, source_versions = [], Counter()
    quarters = pd.to_datetime(candidates.session).dt.to_period("Q")
    for quarter, requested in candidates.groupby(quarters):
        minutes = archive.read(requested[["symbol", "session"]])
        for row in requested.itertuples(index=False):
            bars = minutes.get((row.symbol, row.session))
            label = _window(row.session)
            counts[label]["candidates"] += 1
            status, replay = _path(row, bars, archive, rule)
            counts[label][status] += 1
            if replay is not None:
                replays.append(replay)
                source_versions[bars.at[replay.entry_time, "source_version"]] += 1
        logging.info("Read %s (%s candidate sessions)", quarter, len(requested))
    return sorted(replays, key=lambda p: (p.entry_time, p.symbol)), counts, dict(source_versions)


def _window(day):
    stamp = day.isoformat()
    return next(
        label for label, (lo, hi) in WINDOWS.items() if stamp >= lo and (hi is None or stamp <= hi)
    )


def _exit_minutes(bars, after, spreads, shares, *, reopen=False):
    if shares <= 0:
        return []
    t = bars.index
    if reopen:
        i = t.searchsorted(after, side="right")
        return [(t[i], float(bars.open.iat[i]), shares, minute_half_spread_at(t[i], spreads))] if i < len(t) else []
    caps = (bars.volume.to_numpy()[:-1] * PARTICIPATION).astype(int)
    indices = np.flatnonzero((t[1:] > after) & (t[1:] - t[:-1] == MINUTE) & (caps > 0))
    count = np.searchsorted(caps[indices].cumsum(), shares) + 1
    return [
        (t[j + 1], float(bars.open.iat[j + 1]), int(caps[j]), minute_half_spread_at(t[j + 1], spreads))
        for j in indices[:count]
    ]


def _liquidate(trade, shares, archive):
    fills, marks = [], trade.marks.copy()
    minutes, remaining = trade.fills, shares
    day, mark, reopen = trade.last_day, trade.close_mark, trade.reopen
    while True:
        for stamp, price, capacity, spread in minutes:
            qty = min(remaining, capacity)
            fills.append((stamp, price, qty, spread))
            remaining -= qty
            if not remaining:
                return fills, marks, 0
        marks.append((day, mark))
        day = next_us_equity_session(day)
        if day > archive.last_session:
            break
        bars = archive.continuation(trade.symbol, day)
        if bars is not None:
            bars = bars.loc[bars.volume > 0]
        if bars is None or bars.empty:
            reopen = True
            minutes = []
            continue
        mark = float(bars.close.iat[-1])
        minutes = _exit_minutes(
            bars, bars.index[0] - MINUTE, trade.spreads, remaining, reopen=reopen,
        )
        reopen = bars.index[-1] + MINUTE != _stamp(day, us_equity_session_close(day))
    return fills, marks, remaining


def _account(paths, bp, initial, ticket, archive, spread_multiplier):
    equity, locked = initial, 0.0
    active, positions, records = [], set(), []
    daily = defaultdict(float)
    for i, trade in enumerate(paths):
        while active and active[0][0] <= trade.entry_time:
            _, _, reserve, symbol, pnl, done = heappop(active)
            locked -= reserve
            equity += pnl
            if done:
                positions.remove(symbol)
        if trade.symbol in positions:
            continue
        spread = _fill_half_spread(trade.entry_time, trade.spreads, trade.entry_price)
        entry_unit_cost = turnover_cost(trade.entry_price, bp + spread_multiplier * spread)
        unit_reserve = trade.entry_price + entry_unit_cost
        shares = min(
            trade.entry_limit, int(ticket / trade.entry_price),
            int((equity - locked) / unit_reserve),
        )
        if shares <= 0:
            continue
        entry_cost = shares * entry_unit_cost
        fills, marks, remaining = _liquidate(trade, shares, archive)
        locked += shares * unit_reserve
        positions.add(trade.symbol)
        exit_notional, exit_cost = 0.0, 0.0
        pnl = -entry_cost
        daily[trade.session] -= entry_cost
        events = [(day, mark, 0.0, 0) for day, mark in marks]
        for j, (stamp, price, qty, spread) in enumerate(fills):
            fee = turnover_cost(qty * price, bp + spread_multiplier * max(spread, 50.0 / price))
            gain = trade.side * qty * (price - trade.entry_price) - fee
            done = not remaining and j == len(fills) - 1
            realized = gain - qty * entry_unit_cost
            heappush(active, (stamp, i, qty * unit_reserve, trade.symbol, realized, done))
            events.append((stamp.date(), price, fee, qty))
            exit_notional += qty * price
            exit_cost += fee
            pnl += gain
        open_shares, previous_mark = shares, trade.entry_price
        for day, price, fee, qty in sorted(events, key=lambda e: (e[0], e[3] == 0)):
            if qty:
                daily[day] += trade.side * qty * (price - previous_mark) - fee
                open_shares -= qty
            else:
                daily[day] += trade.side * open_shares * (price - previous_mark)
                previous_mark = price
        closed = shares - remaining
        records.append((
            trade.symbol, trade.session, trade.side, trade.entry_time, trade.entry_price,
            fills[-1][0] if not remaining else pd.NaT, exit_notional / closed if closed else np.nan,
            shares, entry_cost, exit_cost, entry_cost + exit_cost, pnl,
            trade.reason, shares > trade.exit_limit, closed,
        ))
    return pd.DataFrame(records, columns=TRADE_COLUMNS), daily


def _summaries(trades, daily, counts, initial):
    by_window = {}
    exit_windows = trades.exit_time.dropna().map(lambda t: _window(t.tz_convert(NEW_YORK).date()))
    equity = initial
    for label in WINDOWS:
        marks = np.array([v for day, v in sorted(daily.items()) if _window(day) == label])
        curve = np.r_[equity, equity + marks.cumsum()]
        peak = np.maximum.accumulate(curve)
        pnl = curve[-1] - equity
        in_window = exit_windows.reindex(trades.index).eq(label)
        winners = trades.loc[in_window & trades.pnl_usd.gt(0), "pnl_usd"]
        closed = int(in_window.sum())
        missing = sum(counts[label][k] for k in (
            "no_regular_minutes", "incomplete_opening_range", "no_next_minute", "stale_time_mark",
        ))
        by_window[label] = {
            **counts[label],
            "candidates": counts[label]["candidates"], "missing_minute_data": missing,
            "opening_equity_usd": float(equity), "after_cost_usd": float(pnl),
            "after_cost_return": float(pnl / equity),
            "drawdown": float((curve / peak - 1).min()), "trade_count": int(closed),
            "top_5_trade_share": float(winners.nlargest(5).sum() / winners.sum())
            if len(winners) else None,
            "profit_without_largest_winner_usd": float(
                pnl - (winners.max() if len(winners) else 0)
            ),
        }
        equity = curve[-1]
    return by_window


def run_minute_screen(
    candidates: pd.DataFrame, rule: MinuteRule, *, name: str, batch: str, ledger: TrialLedger,
    initial_equity_usd: float, ticket_usd: float, calibration: bool = False,
    inputs: dict | None = None, universe: Path = UNIVERSE, spread_multiplier: float = 1.0,
) -> dict:
    """Replay signed candidate rows with UTC known_at and PIT universe liquidity."""
    if not np.isfinite(spread_multiplier) or spread_multiplier <= 0:
        raise ValueError("Spread multiplier must be positive and finite")
    started = perf_counter()
    trial = f"{batch}-{name}-{uuid4().hex[:8]}"
    parameters = {
        "rule": asdict(rule) | {"exit_at": rule.exit_at.isoformat() if rule.exit_at else None},
        "initial_equity_usd": initial_equity_usd, "ticket_usd": ticket_usd,
        "bp_per_side": COSTS, "entry_participation": PARTICIPATION, "windows": WINDOWS,
        "exit_participation": PARTICIPATION, "all_minute_end": ALL_END.isoformat(),
        "inputs": inputs or {}, "half_spread_table": SPREAD_TABLE.name,
        "spread_multiplier": spread_multiplier,
    }
    ledger.start(
        trial, batch=batch, candidate=name, parameters=parameters, counts_as_trial=not calibration,
        note="Fixed calibration; OOS evaluation only" if calibration else "OOS evaluation only",
    )
    try:
        frame = candidates.copy()
        frame["session"] = pd.to_datetime(frame.session).dt.date
        frame["known_at"] = pd.to_datetime(frame.known_at, utc=True)
        frame["symbol"] = frame.symbol.str.strip().str.upper()
        if frame.duplicated(["symbol", "session"]).any() or not frame.side.isin([-1, 1]).all():
            raise ValueError("Expected one candidate per symbol/session with side +1 or -1")
        with _connect("350MB") as con:
            con.register("candidates", frame[["symbol", "session", "known_at"]].assign(
                ordinal=np.arange(len(frame)),
            ))
            liquidity = con.execute("""
                SELECT u.close, u.median_dollar_volume_20
                FROM candidates c LEFT JOIN read_parquet(?) u
                  ON c.symbol = u.symbol AND c.session = u.session
                 AND u.is_member AND u.known_at < c.known_at
                ORDER BY c.ordinal
            """, [str(universe)]).df()
        frame["half_spreads"] = [
            minute_half_spreads(price, dollars)
            for price, dollars in liquidity.itertuples(index=False, name=None)
        ]
        archive = MinuteBars(universe, frame.symbol.unique())
        paths, counts, versions = _replays(frame, rule, archive)
        path = ledger.path.parent / f"{trial}.json"
        report = {
            "trial": trial, "parameters": parameters,
            "filled_proposals_by_source": versions, "raw_overlap_errors": archive.overlap_errors(),
            "cost_views": {}, "report_file": str(path),
        }
        evidence = [str(path)]
        for bp in COSTS:
            trades, daily = _account(paths, bp, initial_equity_usd, ticket_usd, archive, spread_multiplier)
            trade_file = ledger.path.parent / f"{trial}-{bp}-trades.csv"
            trades.to_csv(trade_file, index=False)
            evidence.append(str(trade_file))
            report["cost_views"][bp] = {
                "by_window": _summaries(trades, daily, counts, initial_equity_usd),
                "exits_above_minute_cap": int(trades.exit_above_minute_cap.sum()),
                "open_exits": int(trades.exit_time.isna().sum()),
                "trade_file": str(trade_file),
            }
        report["seconds"] = perf_counter() - started
        path.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    except Exception as exc:
        ledger.finish(trial, status="failed", evidence=[], note=f"{type(exc).__name__}: {exc}")
        raise
    ledger.finish(trial, status="complete", evidence=evidence)
    return report


def earnings_candidates(universe: Path):
    root = universe.parent
    releases = load_earnings_releases(
        root, columns=["cik", "accession", "visible_date", "accepted_at"],
    )
    gaps = load_earnings_gaps(root, columns=[
        "cik", "accession", "bar_symbol", "session_date", "opening_gap", "gap_available_at",
    ])
    events = gaps.merge(releases, on=["cik", "accession"], validate="one_to_one")
    events = events.loc[
        events.visible_date.eq(events.session_date) & events.accepted_at.lt(events.gap_available_at)
        & events.opening_gap.notna() & events.opening_gap.ne(0)
    ].rename(columns={"bar_symbol": "symbol", "session_date": "session"})
    stock_only = "security_type" in pq.read_schema(universe).names
    stock_filter = (
        "AND security_type IN ('operating', 'adr') AND security_type_known_at < e.gap_available_at"
        if stock_only else ""
    )
    with _connect("350MB") as con:
        con.register("events", events)
        con.read_parquet(str(universe)).create_view("universe")
        return con.sql(f"""
            SELECT e.symbol, e.session, sign(e.opening_gap)::INT AS side, e.gap_available_at AS known_at
            FROM universe u JOIN events e USING (symbol, session)
            WHERE is_member AND median_dollar_volume_20 >= 20000000
              AND u.known_at < e.gap_available_at {stock_filter}
            QUALIFY row_number() OVER (
                PARTITION BY e.symbol, e.session ORDER BY e.accepted_at, e.accession
            ) = 1
        """).df(), stock_only


def calibrate(universe: Path) -> dict:
    started = perf_counter()
    spec = StrategySpec(
        name="earnings-gap-opening-5m", timeframe="1m", lifecycle="draft",
        description="Fixed SIP minute-screen calibration in quoted units",
        universe=["liquid-us-earnings"], position_direction="long_short",
        entry={"all": ["earnings_gap_direction_breaks_first_five_minutes"]},
        exit={"any": ["opposite_range_edge", "regular_session_close"]},
        risk={"max_position_weight": .1}, execution={},
        data={"source": "alpaca", "feed": "sip"},
        data_assumptions={
            "source": "sip_parquet", "adjusted": False,
            "inputs": ["earnings_releases", "earnings_gaps", str(universe), SPREAD_TABLE.name],
        },
    )
    candidates, stock_only = earnings_candidates(universe)
    print(f"Loaded {len(candidates)} earnings candidates (stock view: {stock_only})", flush=True)
    report = run_minute_screen(
        candidates, MinuteRule(), name=spec.name, batch="calibration",
        ledger=TrialLedger(universe.parent / "daily-screen/trials.jsonl"),
        initial_equity_usd=100_000, ticket_usd=10_000, calibration=True, universe=universe,
        inputs={
            "spec": spec.model_dump(mode="json", exclude_defaults=True), "stock_only": stock_only,
        },
    )
    report["total_seconds"] = perf_counter() - started
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["calibrate"])
    parser.add_argument("--universe", type=Path, default=UNIVERSE)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    pa.set_cpu_count(2)
    pa.set_io_thread_count(2)
    print(json.dumps(calibrate(args.universe), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
