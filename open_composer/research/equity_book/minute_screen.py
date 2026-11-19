"""Replay point-in-time stock candidate days against regular-session SIP RAW bars."""

from __future__ import annotations

import argparse
import json
import logging
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta
from heapq import heappop, heappush
from itertools import batched
from pathlib import Path
from time import perf_counter
from uuid import uuid4

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from open_composer.adapters.data.sip_parquet import load_sip_bars
from open_composer.lab.accounting import turnover_cost
from open_composer.lab.ledger import TrialLedger
from open_composer.market_sessions import NEW_YORK, next_us_equity_session, us_equity_session_close
from open_composer.models.strategy_spec import StrategySpec
from open_composer.research.equity_book.costs import HS_BP_CAP, half_spread_bp
from open_composer.research.equity_book.daily_screen import UNIVERSE, WINDOWS
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
TRADE_COLUMNS = [
    "symbol", "session", "side", "entry_time", "entry_price", "exit_time",
    "exit_price", "shares", "entry_cost_usd", "exit_cost_usd", "cost_usd",
    "pnl_usd", "exit_reason", "exit_above_minute_cap",
]


@dataclass(frozen=True)
class MinuteRule:
    """Opening range or limit entry, fixed RAW stop/target, exchange-local time exit.

    A range rule uses the opposite range edge when stop is omitted.
    hold_sessions counts additional sessions. An overnight hold liquidates
    at the terminal daily close and requires exit_at=None.
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


def _stamp(day: date, clock: time) -> pd.Timestamp:
    return pd.Timestamp(datetime.combine(day, clock, NEW_YORK)).tz_convert("UTC")


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
    return None


@dataclass
class Replay:
    symbol: str
    session: date
    side: int
    entry_time: pd.Timestamp
    entry_price: float
    exit_time: pd.Timestamp
    exit_price: float
    entry_limit: int
    exit_limit: int | None
    entry_spread: float
    exit_spread: float
    reason: str
    marks: list[tuple[date, float]]


def _path(row, bars, daily, rule):
    day, side = row.session, row.side
    if bars is None:
        return "no_regular_minutes", None
    opening = _stamp(day, OPEN)
    close = _stamp(day, us_equity_session_close(day))
    deadline = min(close, _stamp(day, rule.exit_at)) if rule.exit_at else close
    bars = bars.loc[bars.index < deadline]
    t = bars.index
    op, high, low, last, volume = bars[["open", "high", "low", "close", "volume"]].to_numpy().T
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

    hit = _bracket(side, op[i:], high[i:], low[i:], stop, rule.target)
    exit_limit, marks = None, []
    if hit:
        j, price, reason, through_open = hit
        j += i
        exit_time = t[j] if through_open and j > i else t[j] + MINUTE
        spread_at = t[j]
        exit_limit = int(volume[j - 1] * PARTICIPATION) if t[j] == t[j - 1] + MINUTE else 0
    elif rule.hold_sessions:
        marks = [(day, last[-1])]
        previous = day
        for _ in range(rule.hold_sessions):
            current = next_us_equity_session(previous)
            day_bar = daily.loc[current]
            o, h, low_price, c = day_bar[["open", "high", "low", "close"]]
            spread_at = _stamp(current, OPEN)
            exit_time = _stamp(current, us_equity_session_close(current))
            ratio = o / marks[-1][1]
            limit = DEFAULT_MAX_ONE_DAY_PRICE_RATIO
            if not 1 / limit <= ratio <= limit:
                price, reason, exit_time = marks[-1][1], "price_discontinuity", spread_at
                break
            hit = _bracket(
                side, np.array([o]), np.array([h]), np.array([low_price]), stop, rule.target,
            )
            if hit:
                _, price, reason, through_open = hit
                if through_open:
                    exit_time = spread_at
                break
            price, reason = c, "time"
            marks.append((current, c))
            previous = current
        if marks[-1][0] == exit_time.tz_convert(NEW_YORK).date():
            marks.pop()
    else:
        price, exit_time, spread_at = last[-1], deadline, deadline
        reason = "time" if t[-1] + MINUTE == deadline else "stale_time_mark"
        prior = t.get_indexer([deadline - 2 * MINUTE])[0]
        exit_limit = int(volume[prior] * PARTICIPATION) if prior >= 0 else 0
    spread = row.opening_half_spread_bp
    early = _stamp(spread_at.tz_convert(NEW_YORK).date(), OPEN) + 15 * MINUTE
    return reason, Replay(
        row.symbol, day, side, t[i], float(entry), exit_time, float(price), shares, exit_limit,
        spread if t[i] < opening + 15 * MINUTE else 0,
        spread if spread_at < early and exit_time < early + MINUTE else 0,
        reason, marks,
    )


def _replays(candidates, rule):
    counts = {label: Counter() for label in WINDOWS}
    replays, source_versions = [], Counter()
    names = sorted(candidates.symbol.unique())
    for batch, symbols in enumerate(batched(names, 6), start=1):
        requested = candidates[candidates.symbol.isin(symbols)]
        first, last = requested.session.min(), requested.session.max()
        bars = load_sip_bars(
            symbols, frequency="minute", start=_stamp(first, OPEN),
            end=_stamp(last, us_equity_session_close(last)), adjustment="raw",
        )
        daily = {}
        if rule.hold_sessions:
            for _ in range(rule.hold_sessions):
                last = next_us_equity_session(last)
            days = load_sip_bars(
                symbols, start=str(first), end=str(last + timedelta(days=1)), adjustment="raw",
            )
            days["session"] = days.timestamp.dt.tz_convert(NEW_YORK).dt.date
            daily = {sym: f.set_index("session") for sym, f in days.groupby("symbol")}
        # The loader sorts by symbol/time. Slice candidate sessions before copying
        # any columns, since a broad symbol read can contain millions of rows.
        for symbol, sessions in requested.groupby("symbol", sort=False):
            start = bars.symbol.searchsorted(symbol, side="left")
            end = bars.symbol.searchsorted(symbol, side="right")
            timestamps = pd.DatetimeIndex(bars.timestamp.iloc[start:end])
            for row in sessions.itertuples(index=False):
                lo, hi = timestamps.searchsorted([
                    _stamp(row.session, OPEN),
                    _stamp(row.session, us_equity_session_close(row.session)),
                ])
                minutes = (
                    bars.iloc[start + lo:start + hi].set_index("timestamp") if lo < hi else None
                )
                label = _window(row.session)
                counts[label]["candidates"] += 1
                status, replay = _path(row, minutes, daily.get(row.symbol), rule)
                counts[label][status] += 1
                if replay is not None:
                    replays.append(replay)
                    source_versions[minutes.at[replay.entry_time, "source_version"]] += 1
        del bars
        if batch % 10 == 0:
            logging.info("Read %s/%s candidate symbols", batch * 6, len(names))
    return sorted(replays, key=lambda p: (p.entry_time, p.symbol)), counts, dict(source_versions)


def _window(day):
    stamp = day.isoformat()
    return next(
        label for label, (lo, hi) in WINDOWS.items() if stamp >= lo and (hi is None or stamp <= hi)
    )


def _account(paths, bp, initial, ticket):
    equity, locked = initial, 0.0
    active, positions, records = [], set(), []
    daily = defaultdict(float)
    for i, trade in enumerate(paths):
        while active and active[0][0] <= trade.entry_time:
            _, _, reserve, symbol, pnl = heappop(active)
            locked -= reserve
            equity += pnl
            positions.remove(symbol)
        if trade.symbol in positions:
            continue
        entry_unit_cost = turnover_cost(trade.entry_price, bp + trade.entry_spread)
        shares = min(
            trade.entry_limit, int(ticket / trade.entry_price),
            int((equity - locked) / (trade.entry_price + entry_unit_cost)),
        )
        if shares <= 0:
            continue
        entry_cost = shares * entry_unit_cost
        exit_cost = turnover_cost(shares * trade.exit_price, bp + trade.exit_spread)
        pnl = trade.side * shares * (trade.exit_price - trade.entry_price) - entry_cost - exit_cost
        exit_day = trade.exit_time.tz_convert(NEW_YORK).date()
        cumulative = 0.0
        for day, mark in trade.marks:
            value = trade.side * shares * (mark - trade.entry_price) - entry_cost
            daily[day] += value - cumulative
            cumulative = value
        daily[exit_day] += pnl - cumulative
        reserve = shares * trade.entry_price + entry_cost
        locked += reserve
        positions.add(trade.symbol)
        heappush(active, (trade.exit_time, i, reserve, trade.symbol, pnl))
        records.append((
            trade.symbol, trade.session, trade.side, trade.entry_time, trade.entry_price,
            trade.exit_time, trade.exit_price, shares, entry_cost, exit_cost,
            entry_cost + exit_cost,
            pnl, trade.reason, trade.exit_limit is not None and shares > trade.exit_limit,
        ))
    return pd.DataFrame(records, columns=TRADE_COLUMNS), daily


def _summaries(trades, daily, counts, initial):
    by_window = {}
    equity = initial
    for label in WINDOWS:
        marks = np.array([v for day, v in sorted(daily.items()) if _window(day) == label])
        curve = np.r_[equity, equity + marks.cumsum()]
        peak = np.maximum.accumulate(curve)
        pnl = curve[-1] - equity
        in_window = trades.exit_time.map(lambda t: _window(t.tz_convert(NEW_YORK).date())).eq(label)
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
    inputs: dict | None = None,
) -> dict:
    """Replay signed candidate rows with UTC known_at and a modeled opening_half_spread_bp."""
    started = perf_counter()
    trial = f"{batch}-{name}-{uuid4().hex[:8]}"
    parameters = {
        "rule": asdict(rule) | {"exit_at": rule.exit_at.isoformat() if rule.exit_at else None},
        "initial_equity_usd": initial_equity_usd, "ticket_usd": ticket_usd,
        "bp_per_side": COSTS, "entry_participation": PARTICIPATION, "windows": WINDOWS,
        "inputs": inputs or {},
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
        paths, counts, versions = _replays(frame, rule)
        report = {
            "trial": trial, "parameters": parameters,
            "filled_proposals_by_source": versions, "cost_views": {},
        }
        evidence = []
        for bp in COSTS:
            trades, daily = _account(paths, bp, initial_equity_usd, ticket_usd)
            path = ledger.path.parent / f"{trial}-{bp}-trades.csv"
            trades.to_csv(path, index=False)
            evidence.append(str(path))
            report["cost_views"][bp] = {
                "by_window": _summaries(trades, daily, counts, initial_equity_usd),
                "exits_above_minute_cap": int(trades.exit_above_minute_cap.sum()),
                "trade_file": str(path),
            }
        report["seconds"] = perf_counter() - started
        path = ledger.path.parent / f"{trial}.json"
        report["report_file"] = str(path)
        path.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
        evidence.append(str(path))
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
        con.execute(f"""
            CREATE TEMP TABLE chosen AS
            SELECT e.symbol, e.session, sign(e.opening_gap)::INT AS side,
                   e.gap_available_at AS known_at, u.security_id, u.trade_date, u.close
            FROM universe u JOIN events e USING (symbol, session)
            WHERE is_member AND median_dollar_volume_20 >= 20000000
              AND u.known_at < e.gap_available_at {stock_filter}
            QUALIFY row_number() OVER (
                PARTITION BY e.symbol, e.session ORDER BY e.accepted_at, e.accession
            ) = 1
        """)
        frame = con.sql("""
            WITH history AS (
                SELECT u.security_id, trade_date, dollar_volume,
                       adjusted_close / lag(adjusted_close) OVER series - 1 AS ret
                FROM universe u SEMI JOIN chosen USING (security_id)
                WHERE is_member
                WINDOW series AS (PARTITION BY security_id ORDER BY trade_date)
            ), observations AS (
                SELECT security_id, trade_date, avg(dollar_volume) OVER recent AS adv,
                       stddev_samp(ret) OVER recent AS vol
                FROM history
                WINDOW recent AS (PARTITION BY security_id ORDER BY trade_date
                                  ROWS BETWEEN 20 PRECEDING AND CURRENT ROW)
            )
            SELECT c.symbol, c.session, c.side, c.known_at, c.close, o.adv, o.vol
            FROM chosen c JOIN observations o USING (security_id, trade_date)
        """).df()
    good = frame.close.gt(0) & frame.adv.gt(0) & frame.vol.gt(0)
    frame["opening_half_spread_bp"] = HS_BP_CAP
    f = frame.loc[good]
    frame.loc[good, "opening_half_spread_bp"] = half_spread_bp(
        f.close, f.adv, f.vol, frame.loc[good, "session"].dt.year, price_basis="printed",
    )
    return frame, stock_only


def calibrate(universe: Path) -> dict:
    started = perf_counter()
    spec = StrategySpec(
        name="earnings-gap-opening-5m", timeframe="1m", lifecycle="draft",
        description="Fixed SIP RAW minute-screen calibration",
        universe=["liquid-us-earnings"], position_direction="long_short",
        entry={"all": ["earnings_gap_direction_breaks_first_five_minutes"]},
        exit={"any": ["opposite_range_edge", "regular_session_close"]},
        risk={"max_position_weight": .1}, execution={},
        data={"source": "alpaca", "feed": "sip"},
        data_assumptions={
            "source": "sip_parquet", "adjusted": False,
            "inputs": ["earnings_releases", "earnings_gaps", str(universe), "cost_model_v1.json"],
        },
    )
    candidates, stock_only = earnings_candidates(universe)
    print(f"Loaded {len(candidates)} earnings candidates (stock view: {stock_only})", flush=True)
    report = run_minute_screen(
        candidates, MinuteRule(), name=spec.name, batch="calibration",
        ledger=TrialLedger(universe.parent / "daily-screen/trials.jsonl"),
        initial_equity_usd=100_000, ticket_usd=10_000, calibration=True,
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
