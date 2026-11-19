"""Read candidate sessions in quoted units without materializing the minute archive."""

from bisect import bisect_left, bisect_right
from collections import defaultdict
from datetime import date, datetime, time
from functools import cache
from itertools import batched
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from open_composer.adapters.data.sip_parquet import (
    MARKET_DATA,
    REQUIRED_COLUMNS,
    _local_sources,
    _symbol_range,
)
from open_composer.market_sessions import NEW_YORK, us_equity_session_close
from open_composer.research.features.daily_actions import (
    ACTIONS,
    ANCHORS,
    action_factors,
    join_action_bars,
    reconstruct_raw,
)
from open_composer.research.features.panel import _connect

ALL_END = date(2026, 10, 16)
KEYS = ["symbol", "timestamp"]
COLUMNS = list(REQUIRED_COLUMNS)
PRICES = ["open", "high", "low", "close"]


def _daily_scales(universe: Path, symbols) -> pd.DataFrame:
    derived = MARKET_DATA / "derived"  # Retained daily-universe build inputs.
    stage = derived / ".daily-universe-build"
    with _connect("350MB") as con:
        con.execute("SET threads=1")
        for view, path in [
            ("adj", stage / "all-*.parquet"), ("raw", stage / "raw-*.parquet"),
            ("anchors", derived / ANCHORS), ("universe", universe),
        ]:
            con.read_parquet(path.as_posix()).create_view(view)
        asof, = con.sql(
            "SELECT max(trade_date) FROM adj WHERE source_version = 'sip-all'"
        ).fetchone()
        actions, mapped = action_factors(con, derived / ACTIONS, derived / ANCHORS, asof)
        scales = []
        for names in batched(sorted(symbols), 256):
            con.register("names", pd.DataFrame({"symbol": names}))
            join_action_bars(
                con, "b.source_version = 'sip-all' AND b.symbol IN (SELECT symbol FROM names)",
            )
            frame = con.execute("""
                SELECT j.symbol, j.trade_date, j.source_version, j.adjusted_close,
                       j.adjusted_volume, j.close, j.raw_volume,
                       coalesce(u.security_id, j.symbol) AS security_id
                FROM joined j LEFT JOIN (
                    SELECT symbol, trade_date, security_id FROM universe
                    WHERE is_member AND symbol BETWEEN ? AND ?
                ) u USING (symbol, trade_date)
                WHERE j.symbol BETWEEN ? AND ?
                ORDER BY security_id, trade_date
            """, [names[0], names[-1], names[0], names[-1]]).df()
            frame["trade_date"] = frame.trade_date.astype("datetime64[ns]")
            fitted = reconstruct_raw(frame, actions, mapped, scales_only=True)
            keys = pd.MultiIndex.from_frame(frame[["symbol", "trade_date"]])
            scales.append(pd.DataFrame(fitted, index=keys))
    return pd.concat(scales)


@cache
def _bounds(path):
    stat = path.stat()
    return _symbol_range(path, stat.st_mtime_ns, stat.st_size)


def _read_shards(paths, windows, last, *, repair=False):
    symbols = sorted(windows)
    dates = {op.date() for rows in windows.values() for op, _ in rows}
    parts = []
    for path in paths:
        if path.parent.name == "minute" and path.parent.parent.name[:4].isdecimal():
            if date.fromisoformat(path.parent.parent.name) not in dates:
                continue
        bounds = _bounds(path)
        lo, hi = (0, len(symbols)) if bounds is None else (
            bisect_left(symbols, bounds[0]), bisect_right(symbols, bounds[1]),
        )
        if lo == hi:
            continue
        # Monthly partitions of the ALL and recent archives are bar months.
        if not repair and path.parent.name.isdecimal() and len(path.parent.name) == 2:
            month = (int(path.parent.parent.name), int(path.parent.name))
        else:
            month = None
        filters = [
            [("symbol", "=", symbol), ("timestamp", ">=", op), ("timestamp", "<", close)]
            for symbol in symbols[lo:hi] for op, close in windows[symbol]
            if op.date() <= last and (month is None or month == (op.year, op.month))
        ]
        if not filters:
            continue
        table = pq.read_table(path, columns=COLUMNS, filters=filters)
        if table.num_rows:
            parts.append(table)
    if not parts:
        return pd.DataFrame(columns=COLUMNS)
    return pa.concat_tables(parts, promote_options="permissive").to_pandas()


class MinuteBars:
    def __init__(self, universe, symbols):
        self.scales = _daily_scales(universe, symbols)
        self.errors = []
        self.unscaled = 0
        self.repairs = defaultdict(list)
        self.raw = _local_sources("minute", "raw", None, None)
        self.last_session = ALL_END
        for version, paths in self.raw:
            if version == "sip-raw-daily":
                for path in paths:
                    day = date.fromisoformat(path.parent.parent.name)
                    self.last_session = max(self.last_session, day)
            if version not in ("sip-raw-repair", "sip-raw-recent"):
                continue
            for path in paths:
                meta = pq.read_metadata(path)
                if not meta.num_rows:
                    continue
                col = meta.schema.names.index("timestamp")
                times = [
                    meta.row_group(i).column(col).statistics for i in range(meta.num_row_groups)
                ]
                last = max(r.max for r in times).astimezone(NEW_YORK).date()
                self.last_session = max(self.last_session, last)
                if version == "sip-raw-repair":
                    for month in pd.period_range(min(r.min for r in times).date(), last, freq="M"):
                        self.repairs[month].append(path)
        self.following = {}

    def continuation(self, symbol, day):
        key = (symbol, day)
        if key not in self.following:
            sessions = pd.DataFrame([key], columns=["symbol", "session"])
            bars = self.read(sessions, compare=False).get(key)
            self.following[key] = bars
        return self.following[key]

    def read(self, sessions, *, compare=True):
        windows = defaultdict(list)
        first, last = sessions.session.min(), sessions.session.max()
        for symbol, day in sessions.itertuples(index=False, name=None):
            close = us_equity_session_close(day)
            windows[symbol].append((
                pd.Timestamp(datetime.combine(day, time(9, 30), NEW_YORK)).tz_convert("UTC"),
                pd.Timestamp(datetime.combine(day, close, NEW_YORK)).tz_convert("UTC"),
            ))
        start, end = pd.Timestamp(first, tz="UTC"), pd.Timestamp(last, tz="UTC")
        raw = []
        for version, paths in self.raw:
            if version == "sip-raw-repair":
                shards = dict.fromkeys(
                    path for month in pd.period_range(first, last, freq="M")
                    for path in self.repairs[month]
                )
                parts = _read_shards(sorted(shards), windows, last, repair=True)
            else:
                parts = _read_shards(paths, windows, last)
            if not parts.empty:
                raw.append(parts.assign(source_version=version))
        frame = pd.concat(raw, ignore_index=True) if raw else pd.DataFrame(
            columns=[*COLUMNS, "source_version"],
        )
        # Prefer the recent full-market RAW collection after the ALL cutoff.
        if len(frame):
            recent = frame.source_version.eq("sip-raw-recent") & (frame.timestamp.dt.date > ALL_END)
            frame = pd.concat([frame.loc[recent], frame.loc[~recent]], ignore_index=True)
        frame = frame.drop_duplicates(KEYS)
        if first <= ALL_END:
            for version, paths in _local_sources(
                "minute", "all", start, min(end, pd.Timestamp(ALL_END, tz="UTC")),
            ):
                bars = _read_shards(paths, windows, min(last, ALL_END))
                if not bars.empty:
                    bars = bars.loc[bars.timestamp.dt.date <= ALL_END].drop_duplicates(KEYS)
                    bars["source_version"] = version + "-converted"
                    frame = self._combine(frame, bars, compare)
        if frame.empty:
            return {}
        frame["session"] = frame.timestamp.dt.date  # NY regular-session bars share their UTC date.
        frame = frame.sort_values("timestamp").set_index("timestamp")
        return dict(list(frame.groupby(["symbol", "session"], sort=False)))

    def _combine(self, raw, bars, compare):
        days = bars.timestamp.dt.tz_localize(None).dt.normalize().astype("datetime64[ns]")
        scales = self.scales.reindex(pd.MultiIndex.from_arrays([bars.symbol, days])).to_numpy()
        bars[PRICES] = bars[PRICES].to_numpy() * scales[:, :1]
        bars["volume"] = bars.volume.to_numpy() * scales[:, 1]
        if compare and len(raw):
            overlap = bars.merge(raw, on=KEYS, suffixes=("_converted", "_raw"))
            fields = ["close", "volume"]
            converted = overlap[[f"{c}_converted" for c in fields]].to_numpy(dtype=float)
            observed = overlap[[f"{c}_raw" for c in fields]].to_numpy(dtype=float)
            self.errors.append(np.abs(converted / np.where(observed > 0, observed, np.nan) - 1))
        bars = bars.loc[~bars.set_index(KEYS).index.isin(raw.set_index(KEYS).index)]
        scaled = bars.close.notna() & bars.volume.notna()
        if compare:
            self.unscaled += int((~scaled).sum())
        return pd.concat([raw, bars.loc[scaled]], ignore_index=True)

    def overlap_errors(self):
        report = {"unscaled_minutes_without_raw": self.unscaled}
        if self.errors:
            errors = np.concatenate(self.errors)
            report["overlap_minutes"] = len(errors)
            for i, name in enumerate(("close", "volume")):
                values = errors[:, i]
                values = values[np.isfinite(values)]
                report[name + "_absolute_relative_error"] = {
                    "minutes": len(values),
                    "median": float(np.median(values)) if len(values) else None,
                    "p99": float(np.percentile(values, 99)) if len(values) else None,
                }
        return report
