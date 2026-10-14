"""Past-only shared context and lower-bar producer; no orders, fills or P&L."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import fields, replace
from datetime import UTC, date, datetime, time, timedelta
from math import isfinite, log
from statistics import fmean

import pandas as pd
from context_producer import ContextProducer
from decision_system import clock_minutes
from geometry import Day, context, ema

from open_composer.market_sessions import NEW_YORK, us_equity_session_close, us_equity_session_dates
from open_composer.research.features.price_hygiene import sanitize_price_matrices

SYMBOLS = ("COIN", "GME", "LMND", "SMCI", "SOFI", "SOUN")


def split_like_trigger(ratio):
    # Same trigger-only predicate as run_t20260929_32_gap_fade_ls.py:251;
    # this never looks at a later close or a holding-window outcome.
    factors = (0.1, 0.2, 0.25, 1 / 3, 0.5, 2 / 3, 1.5, 2, 3, 4, 5, 10)
    return isfinite(ratio) and ratio > 0 and any(abs(log(ratio / f)) < 0.03 for f in factors)


def frame_record(f):
    # Immutable source objects need no recursive deepcopy of timestamps.
    row = {field.name: getattr(f, field.name) for field in fields(f)}
    row["supports"] = [
        {field.name: getattr(s, field.name) for field in fields(s)} for s in f.supports
    ]
    row["anchors"] = [
        {field.name: getattr(a, field.name) for field in fields(a)} for a in f.anchors
    ]
    return row


def vendor_day(day, row):
    # Prior provider daily observations may include extended-hours prints.
    # Give them conservative 20:00 NY availability, never midnight or16:00.
    end = datetime.combine(date.fromisoformat(day), time(20), tzinfo=NEW_YORK).astimezone(UTC)
    return Day(end, row["o"], row["h"], row["l"], row["c"], row["v"], row.get("vw"))


def aggregate(rows, start, end, minute, width):
    if width == 1:
        if len(rows) != 1 or rows[0]["timestamp"] != start or rows[0]["volume"] <= 0:
            return None
        r = rows[0]
        return dict(
            start=start,
            end=end,
            minute=minute,
            duration=1,
            open=r["open"],
            high=r["high"],
            low=r["low"],
            close=r["close"],
            volume=r["volume"],
            vwap=r["vwap"],
            complete=True,
        )
    if len(rows) != width or any(
        r["timestamp"] != start + timedelta(minutes=i) for i, r in enumerate(rows)
    ):
        return None
    volume = sum(r["volume"] for r in rows)
    if volume <= 0:
        return None
    return dict(
        start=start,
        end=end,
        minute=minute,
        duration=width,
        open=rows[0]["open"],
        high=max(r["high"] for r in rows),
        low=min(r["low"] for r in rows),
        close=rows[-1]["close"],
        volume=volume,
        vwap=sum(r["vwap"] * r["volume"] for r in rows) / volume,
        complete=True,
    )


class FrameProducer:
    def __init__(self, parameters, daily_basis, index_records, actions, *, cache_frames=True):
        self.p = parameters
        self.cache_frames = cache_frames
        self.raw_days = daily_basis["raw"]
        self.index_days = defaultdict(dict)
        for r in index_records:
            d = r["timestamp"].astimezone(NEW_YORK).date().isoformat()
            self.index_days[r["symbol"]][d] = dict(
                o=r["open"], h=r["high"], l=r["low"], c=r["close"], v=r["volume"], vw=r["vwap"]
            )
        self.actions = actions
        self.contexts = ContextProducer()
        self.hours = defaultdict(list)
        self.volumes = {s: deque(maxlen=180) for s in SYMBOLS}
        self.calendar = us_equity_session_dates(date(2021, 1, 1), date(2025, 12, 31))
        self.ordinal = {d: i for i, d in enumerate(self.calendar)}
        self.week_sessions = defaultdict(set)
        for d in self.calendar:
            self.week_sessions[d - timedelta(days=d.weekday())].add(d)
        self.daily = {}
        self.indexes = {}
        self.watch = set()
        self.scores = {}
        self.qa = defaultdict(int)
        self.hygiene = {}

    def _daily_history(self, symbol, day):
        original = [
            vendor_day(d, r) for d, r in sorted(self.raw_days[symbol].items()) if d < str(day)
        ]
        days = []
        for row in original[-self.p["warmup_sessions"] :]:
            ratio = 1.0
            prior = row.end.astimezone(NEW_YORK).date().isoformat()
            for a in self.actions:
                r = a["row"]
                if (
                    a["kind"] == "forward_splits"
                    and r["symbol"] == symbol
                    and prior < r["ex_date"] <= str(day)
                ):
                    ratio *= r["new_rate"] / r["old_rate"]
            days.append(
                replace(
                    row,
                    open=row.open / ratio,
                    high=row.high / ratio,
                    low=row.low / ratio,
                    close=row.close / ratio,
                    volume=row.volume * ratio,
                    vwap=row.vwap / ratio if row.vwap is not None else None,
                )
            )
        if not days:
            self.hygiene[symbol] = dict(masked=0, breaks=[])
            return days
        first = days[0].end.astimezone(NEW_YORK).date()
        sessions = [d for d in self.calendar if first <= d < day]
        index = pd.DatetimeIndex(sessions)
        close = pd.DataFrame(float("nan"), index=index, columns=[symbol])
        opened = close.copy()
        for row in days:
            at = pd.Timestamp(row.end.astimezone(NEW_YORK).date())
            if row.volume > 0:
                close.at[at, symbol] = row.close
                opened.at[at, symbol] = row.open
        # Both matrices contain only observations available before this open,
        # in already reconciled split units. Defaults apply to this prefix.
        cleaned, clean_open, report = sanitize_price_matrices(close, opened)
        self.hygiene[symbol] = dict(
            masked=report.price_cells_masked,
            breaks=[
                dict(kind=b.kind, first_after=str(b.first_session_after.date()), masked=b.masked)
                for b in report.breaks
            ],
            as_of=str(day),
        )
        self.qa["stock_daily_hygiene_masked_cells"] += report.price_cells_masked
        return [
            row
            for row in days
            if (
                isfinite(cleaned.at[pd.Timestamp(row.end.astimezone(NEW_YORK).date()), symbol])
                and isfinite(
                    clean_open.at[pd.Timestamp(row.end.astimezone(NEW_YORK).date()), symbol]
                )
            )
        ]

    def begin_session(self, day):
        self.day = day
        self.open = datetime.combine(day, time(9, 30), tzinfo=NEW_YORK).astimezone(UTC)
        self.close = datetime.combine(
            day, us_equity_session_close(day), tzinfo=NEW_YORK
        ).astimezone(UTC)
        self.session = self.ordinal[day]
        self.trigger_eligible = {s: True for s in SYMBOLS}
        effective = []
        for a in self.actions:
            r = a["row"]
            if (
                a["kind"] == "forward_splits"
                and r["ex_date"] == str(day)
                and r["symbol"] in SYMBOLS
            ):
                symbol = r["symbol"]
                ratio = r["new_rate"] / r["old_rate"]
                self.trigger_eligible[symbol] = False
                self.contexts.apply_split(symbol, ratio)
                self.hours[symbol] = [
                    replace(
                        x,
                        open=x.open / ratio,
                        high=x.high / ratio,
                        low=x.low / ratio,
                        close=x.close / ratio,
                        vwap=x.vwap / ratio,
                        volume=x.volume * ratio,
                    )
                    for x in self.hours[symbol]
                ]
                self.volumes[symbol] = deque(
                    ((t, v * ratio) for t, v in self.volumes[symbol]), maxlen=180
                )
                effective.append(dict(kind="forward_split", symbol=symbol, ratio=ratio, id=r["id"]))
            elif (
                a["kind"] == "spin_offs"
                and r["ex_date"] == str(day)
                and r["source_symbol"] in SYMBOLS
            ):
                effective.append(
                    dict(kind="unresolved_right", symbol=r["source_symbol"], id=r["id"], row=r)
                )
        self.histories = {s: self._daily_history(s, day) for s in SYMBOLS}
        self.daily = {}
        for s in SYMBOLS:
            epoch = self.contexts.epochs.get(s)
            frozen = epoch.origin if epoch is not None and not epoch.invalid else None
            invalid = frozenset(self.contexts.invalidated_origins.get(s, set()))
            row = context(
                self.histories[s], self.open, self.p, frozen_origin=frozen, invalid_origins=invalid
            )
            if row.get("base_start"):
                origin_day = row["base_start"].astimezone(NEW_YORK).date()
                row["base_origin_session"] = self.ordinal[origin_day]
            self.daily[s] = row
        self.watch, self.scores = self.contexts.prior_session_update(
            self.daily, self.open, self.session
        )
        self.indexes = {}
        for s in ("QQQ", "IWM"):
            rows = [
                vendor_day(d, r) for d, r in sorted(self.index_days[s].items()) if d < str(day)
            ][-150:]
            if len(rows) < 21 or any(x.close != x.close for x in rows):
                self.qa["index_unavailable"] += 1
                continue
            vals = [x.close for x in rows]
            self.indexes[s] = dict(
                status="observed",
                available_at=rows[-1].end,
                close=vals[-1],
                ema={n: ema(vals, n) for n in (9, 21)},
                previous_ema={n: ema(vals[:-1], n) for n in (9, 21)},
            )
        self.seen = {s: {} for s in SYMBOLS}
        self.day_lows = {s: float("inf") for s in SYMBOLS}
        self.weekly = {s: self._weekly(s) for s in SYMBOLS}
        self.hour_cache = {}
        self.frame_templates = {}
        return effective

    def _weekly(self, symbol):
        byweek = defaultdict(list)
        for row in self.histories[symbol]:
            d = row.end.astimezone(NEW_YORK).date()
            byweek[d - timedelta(days=d.weekday())].append(row)
        weeks = []
        for monday, rows in sorted(byweek.items()):
            friday = monday + timedelta(days=4)
            if friday >= self.day:
                continue
            required = self.week_sessions[monday]
            if {r.end.astimezone(NEW_YORK).date() for r in rows} != set(required):
                continue
            weeks.append(rows[-1])
        if len(weeks) < 9:
            return None
        return dict(
            status="observed",
            available_at=weeks[-1].end,
            ema={n: ema([w.close for w in weeks], n) for n in (9, 21)},
        )

    def complete_minute(self, minute, records, *, serialize=True):
        rows_out = []
        t = self.open + timedelta(minutes=minute)
        for symbol in SYMBOLS:
            r = records.get(symbol)
            if r is not None:
                if not self.seen[symbol]:
                    prior = [d for d in self.raw_days[symbol] if d < str(self.day)]
                    prev = self.raw_days[symbol][max(prior)]["c"] if prior else None
                    # A missing09:30 does not certify a later quote as the open.
                    if minute != 0:
                        self.trigger_eligible[symbol] = False
                    elif prev and split_like_trigger(r["open"] / prev):
                        self.trigger_eligible[symbol] = False
                        self.qa["split_like_trigger_sessions"] += 1
                self.seen[symbol][minute] = r
                self.day_lows[symbol] = min(self.day_lows[symbol], r["low"])
            width = clock_minutes(self.p, minute) or 1
            lo, hi = next(
                ((lo, hi) for lo, hi, w in self.p["entry_clock"] if lo <= minute < hi), (120, 10**9)
            )
            if (minute + 1 - lo) % width == 0 and minute + 1 <= hi:
                start_index = minute + 1 - width
                start = self.open + timedelta(minutes=start_index)
                lower = aggregate(
                    [
                        self.seen[symbol][i]
                        for i in range(start_index, minute + 1)
                        if i in self.seen[symbol]
                    ],
                    start,
                    t + timedelta(minutes=1),
                    start_index,
                    width,
                )
                previous = aggregate(
                    [
                        self.seen[symbol][i]
                        for i in range(start_index - width, start_index)
                        if i in self.seen[symbol]
                    ],
                    start - timedelta(minutes=width),
                    start,
                    start_index - width,
                    width,
                )
                daily = self.daily[symbol]
                hours = (
                    self.hours[symbol][-150:]
                    if width == 1
                    else [h for h in self.hours[symbol] if h.end <= start][-150:]
                )
                if (
                    lower is None
                    or previous is None
                    or daily.get("status") != "observed"
                    or symbol not in self.contexts.epochs
                ):
                    self.qa["incomplete_lower_or_daily"] += 1
                elif len(hours) < 21:
                    self.qa["insufficient_complete_hourly"] += 1
                else:
                    key = (symbol, hours[-1].end)
                    if key not in self.hour_cache:
                        self.hour_cache[key] = dict(
                            status="observed",
                            available_at=hours[-1].end,
                            ema={n: ema([h.close for h in hours], n) for n in (9, 21)},
                        )
                    hourly = self.hour_cache[key]
                    lower["day_low"] = self.day_lows[symbol]
                    vols = (
                        [v for at, v in list(self.volumes[symbol])[-5:]]
                        if width == 1
                        else [v for at, v in self.volumes[symbol] if at < start][-5:]
                    )
                    retest = self.contexts.observe_touch(symbol, daily, lower, self.session)
                    if not self.cache_frames or key not in self.frame_templates:
                        self.frame_templates[key] = self.contexts.compile_frame(
                            symbol=symbol,
                            daily=daily,
                            hourly=hourly,
                            weekly=self.weekly[symbol],
                            indexes=self.indexes,
                            watchlist=self.watch,
                            lower=lower,
                            previous_lower=previous,
                            session=str(self.day),
                            session_index=self.session,
                            anchors=daily["anchors"],
                            past_minute_volume=fmean(vols) if len(vols) == 5 else 0,
                            pause_sessions=0,
                        )
                    f = replace(
                        self.frame_templates[key],
                        start=lower["start"],
                        end=lower["end"],
                        minute=lower["minute"],
                        duration=lower["duration"],
                        close=lower["close"],
                        low=lower["low"],
                        previous_high=previous["high"],
                        previous_low=previous["low"],
                        day_low=lower["day_low"],
                        first_retest=retest,
                        trigger_price_eligible=self.trigger_eligible[symbol],
                        past_minute_volume=fmean(vols) if len(vols) == 5 else 0,
                    )
                    if t + timedelta(minutes=1) == self.close:
                        full = [
                            self.seen[symbol][i]
                            for i in range(minute + 1)
                            if i in self.seen[symbol]
                        ]
                        if len(full) == minute + 1:
                            vals = [h.close for h in self.histories[symbol]] + [r["close"]]
                            f = replace(
                                f, trail_daily_close=r["close"], trail_daily_ema9=ema(vals, 9)
                            )
                    if serialize:
                        rows_out.append(
                            dict(
                                frame=frame_record(f),
                                leadership_score=self.scores.get(symbol, 0),
                                prior_dollar_volume=daily["average_dollar_volume"],
                            )
                        )
            if r is not None:
                self.volumes[symbol].append((t, r["volume"]))
            if (minute + 1) % 60 == 0:
                start = t - timedelta(minutes=59)
                hour = aggregate(
                    [
                        self.seen[symbol][i]
                        for i in range(minute - 59, minute + 1)
                        if i in self.seen[symbol]
                    ],
                    start,
                    t + timedelta(minutes=1),
                    minute - 59,
                    60,
                )
                if hour:
                    self.hours[symbol].append(
                        Day(
                            hour["end"],
                            hour["open"],
                            hour["high"],
                            hour["low"],
                            hour["close"],
                            hour["volume"],
                            hour["vwap"],
                        )
                    )
                    self.hours[symbol] = self.hours[symbol][-150:]
                else:
                    self.qa["incomplete_hourly"] += 1
        return rows_out
