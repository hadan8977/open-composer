"""Post-close prices file of book v1.2 for ``oc book-paper reconcile --prices-file``.

T-20261002-41.

Builds ``{"official_close": {sym: px}, "snapshot_1545": {sym: px}, ...}`` for one execution date D
from the local SIP archives only (no network, no broker, nothing under ``data/`` is written):

* ``official_close``: close of the D daily bar in ``data/sip/daily`` (daily bars are labelled with
  midnight America/New_York).
* ``snapshot_1545``: close of the minute bar labelled 15:44:00 America/New_York in
  ``data/sip/minute/<year>/<month>``.  Alpaca minute bars are labelled by their START time (the
  first regular bar is 09:30 and the closing-auction bar is 15:59), so the bar covering 15:44-15:45
  is the 15:44 bar and its close is the last trade before 15:45:00.  A missing bar falls back to the
  most recent earlier bar that ended within 10 minutes of 15:45 (labels 15:34-15:43), recorded in
  ``snapshot_fallback``; names with no such bar are in ``missing_snapshot``.

Price basis: the archive is fetched with ``adjustment="all"`` (split and dividend adjusted history).
On the evening of D no corporate action effective after D exists yet, so the adjusted close of D
equals the raw print of D.  A later restatement of a symbol (``data/sip/daily/_restatements.jsonl``,
``detected_at`` after D) means that symbol's D prices are no longer the raw print; such symbols are
listed in ``restated_after_execution_date``.

Symbols: the union of target weights / core and hedge symbols and of plan orders and post-trade
quantities (the plan file does not store pre-trade positions; fully sold names are in its orders).
Output: ``reports/paper/book/prices/<D>.json`` under the project root (``--out`` overrides).
Exit codes: 0 ok, 2 data not fresh (no daily bar of D yet, or no minute bar of D at all), 3 no
symbols / unreadable inputs.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable, Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

NEW_YORK = ZoneInfo("America/New_York")
SNAPSHOT_TIME_ET = (15, 45)
SNAPSHOT_FALLBACK_MINUTES = 10
SCHEMA_VERSION = 1
SIP_ROOT = ROOT / "data/sip"
EXIT_OK, EXIT_NOT_FRESH, EXIT_INPUTS = 0, 2, 3
PRICE_BASIS = (
    "alpaca sip adjustment=all (split+dividend adjusted history); built on the evening of the "
    "execution date, so the adjusted close equals the raw print of that day unless the symbol is "
    "listed in restated_after_execution_date"
)
BAR_COLUMNS = ["symbol", "timestamp", "close"]


class DataNotFresh(RuntimeError):
    """The archive holds no bars of the execution date yet."""


class InputsError(RuntimeError):
    """Plan/target input files unreadable or without symbols."""


# --------------------------------------------------------------------------------------
# symbols
# --------------------------------------------------------------------------------------


def symbols_from_payload(payload: dict[str, Any]) -> dict[str, set[str]]:
    """Symbols of a target file and/or plan file payload, by where they come from."""
    found: dict[str, set[str]] = {}

    def add(origin: str, values: Iterable[Any]) -> None:
        names = {str(v).upper() for v in values if v}
        if names:
            found.setdefault(origin, set()).update(names)

    add("target_weights", (payload.get("weights") or {}).keys())
    add("target_core_hedge", [payload.get("core_symbol"), payload.get("hedge_symbol")])
    add("plan_orders", (o.get("symbol") for o in payload.get("orders") or []))
    add("plan_post_trade_qty", (payload.get("post_trade_qty") or {}).keys())
    return found


def collect_symbols(paths: Sequence[Path]) -> tuple[list[str], dict[str, list[str]]]:
    """Union of the symbols of the given plan/target JSON files, and the origin of each name."""
    origin: dict[str, set[str]] = {}
    if not paths:
        raise InputsError("no plan/target files given")
    for path in paths:
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise InputsError(f"cannot read {path}: {exc}") from exc
        if not isinstance(payload, dict):
            raise InputsError(f"{path} is not a JSON object")
        for kind, names in symbols_from_payload(payload).items():
            for name in names:
                origin.setdefault(name, set()).add(f"{kind}:{Path(path).name}")
    if not origin:
        raise InputsError("the given files contain no symbols")
    return sorted(origin), {s: sorted(v) for s, v in sorted(origin.items())}


def discover_inputs(root: Path, execution_date: date) -> list[Path]:
    """Plan files of the execution date and the targets they were built from, both accounts."""
    paths: list[Path] = []
    for account in ("quant1", "quant2"):
        base = Path(root) / "reports" / "paper" / "book" / account
        plan = base / "plans" / f"{execution_date.isoformat()}.json"
        if not plan.is_file():
            continue
        paths.append(plan)
        try:
            decision = json.loads(plan.read_text(encoding="utf-8")).get("decision_date")
        except (OSError, ValueError):
            decision = None
        target = base / "targets" / f"{decision}.json" if decision else None
        if target is not None and target.is_file():
            paths.append(target)
    return paths


# --------------------------------------------------------------------------------------
# archive reads (read only)
# --------------------------------------------------------------------------------------


def _shard_paths(kind_dir: Path, months: Iterable[tuple[int, int]]) -> list[Path]:
    """Whole-year shards first, month shards after, so a month shard (refreshed later) wins."""
    paths: list[Path] = []
    for year in sorted({y for y, _ in months}):
        year_dir = kind_dir / str(year)
        if year_dir.is_dir():
            paths.extend(sorted(year_dir.glob("shard-*.parquet")))
    for year, month in sorted(set(months)):
        month_dir = kind_dir / str(year) / f"{month:02d}"
        if month_dir.is_dir():
            paths.extend(sorted(month_dir.glob("shard-*.parquet")))
    return paths


def read_bars(
    sip_root: Path,
    kind: str,
    symbols: Sequence[str],
    start_utc: datetime,
    end_utc: datetime,
) -> tuple[pd.DataFrame, list[str]]:
    """``symbol, timestamp, close`` of the bars with ``start <= timestamp < end`` (UTC).

    Returns the frame (deduplicated, later shards win) and the shard files that contributed.
    """
    kind_dir = Path(sip_root) / kind
    months: set[tuple[int, int]] = set()
    cursor = start_utc.replace(day=1)
    while cursor < end_utc:
        months.add((cursor.year, cursor.month))
        cursor = (cursor + timedelta(days=32)).replace(day=1)
    wanted = sorted({s.upper() for s in symbols})
    filters = [
        ("symbol", "in", wanted),
        ("timestamp", ">=", pd.Timestamp(start_utc)),
        ("timestamp", "<", pd.Timestamp(end_utc)),
    ]
    parts: list[pd.DataFrame] = []
    used: list[str] = []
    for path in _shard_paths(kind_dir, months):
        table = pq.read_table(path, columns=BAR_COLUMNS, filters=filters)
        if table.num_rows == 0:
            continue
        frame = table.to_pandas()
        frame["symbol"] = frame["symbol"].astype(str).str.upper()
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
        parts.append(frame)
        used.append(str(path))
    if not parts:
        return pd.DataFrame(columns=BAR_COLUMNS), used
    frame = pd.concat(parts, ignore_index=True)
    frame = frame.drop_duplicates(subset=["symbol", "timestamp"], keep="last")
    return frame.sort_values(["symbol", "timestamp"], kind="stable").reset_index(drop=True), used


def ny_day_bounds_utc(day: date) -> tuple[datetime, datetime]:
    start = datetime(day.year, day.month, day.day, tzinfo=NEW_YORK)
    nxt = day + timedelta(days=1)
    end = datetime(nxt.year, nxt.month, nxt.day, tzinfo=NEW_YORK)
    return start.astimezone(UTC), end.astimezone(UTC)


def snapshot_time_utc(day: date) -> datetime:
    hour, minute = SNAPSHOT_TIME_ET
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=NEW_YORK).astimezone(UTC)


# --------------------------------------------------------------------------------------
# prices
# --------------------------------------------------------------------------------------


def official_closes(
    sip_root: Path, symbols: Sequence[str], day: date
) -> tuple[dict[str, float], list[str]]:
    start, end = ny_day_bounds_utc(day)
    frame, used = read_bars(sip_root, "daily", symbols, start, end)
    closes = {
        str(row.symbol): float(row.close)
        for row in frame.itertuples()
        if pd.notna(row.close) and float(row.close) > 0
    }
    return closes, used


def snapshot_closes(
    sip_root: Path, symbols: Sequence[str], day: date
) -> tuple[dict[str, float], dict[str, dict[str, Any]], list[str]]:
    """Close of the bar covering 15:44-15:45 ET; fallback to the latest bar ending within 10 min."""
    cut = snapshot_time_utc(day)
    window_start = cut - timedelta(minutes=SNAPSHOT_FALLBACK_MINUTES + 1)  # oldest label 15:34
    # bars are labelled by start time: bar label L covers [L, L + 1 min); the bar ending at the
    # snapshot has label cut - 1 min; the earliest allowed one ended 10 min before the snapshot.
    frame, used = read_bars(sip_root, "minute", symbols, window_start, cut)
    prices: dict[str, float] = {}
    fallback: dict[str, dict[str, Any]] = {}
    exact_label = cut - timedelta(minutes=1)
    for symbol, part in frame.groupby("symbol", sort=True):
        part = part[part["close"].notna() & (part["close"] > 0)]
        if part.empty:
            continue
        last = part.iloc[-1]
        label = last["timestamp"].to_pydatetime()
        prices[str(symbol)] = float(last["close"])
        if label != exact_label:
            fallback[str(symbol)] = {
                "bar_label_et": label.astimezone(NEW_YORK).strftime("%H:%M"),
                "bar_ends_minutes_before_1545": int(
                    (cut - (label + timedelta(minutes=1))).total_seconds() // 60
                ),
            }
    return prices, fallback, used


def _missing_reasons(
    sip_root: Path, kind: str, symbols: Sequence[str], day: date
) -> dict[str, str]:
    """Why a name has no price: what the archive holds for it around the date."""
    if not symbols:
        return {}
    if kind == "daily":
        start = datetime.combine(day - timedelta(days=45), datetime.min.time(), tzinfo=UTC)
        end = datetime.combine(day + timedelta(days=1), datetime.min.time(), tzinfo=UTC)
        frame, _ = read_bars(sip_root, "daily", symbols, start, end)
        reasons: dict[str, str] = {}
        for symbol in symbols:
            part = frame[frame["symbol"] == symbol]
            if part.empty:
                reasons[symbol] = "no daily bar within 45 days before the date (not in archive)"
            else:
                last = part["timestamp"].iloc[-1].astimezone(NEW_YORK).date()
                reasons[symbol] = f"no daily bar on the date (last bar {last.isoformat()})"
        return reasons
    start, end = ny_day_bounds_utc(day)
    frame, _ = read_bars(sip_root, "minute", symbols, start, end)
    reasons = {}
    for symbol in symbols:
        part = frame[frame["symbol"] == symbol]
        if part.empty:
            reasons[symbol] = "no minute bar on the date"
        else:
            first = part["timestamp"].iloc[0].astimezone(NEW_YORK).strftime("%H:%M")
            last = part["timestamp"].iloc[-1].astimezone(NEW_YORK).strftime("%H:%M")
            reasons[symbol] = (
                f"no minute bar in 15:34-15:44 ET (bars that day {first}-{last} ET, "
                f"{len(part)} bars)"
            )
    return reasons


def restated_after(sip_root: Path, symbols: Sequence[str], day: date) -> list[str]:
    """Symbols whose daily history was rewritten after the end of the execution date."""
    path = Path(sip_root) / "daily" / "_restatements.jsonl"
    if not path.is_file():
        return []
    cutoff = ny_day_bounds_utc(day)[1]
    wanted = set(symbols)
    flagged: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(line)
            detected = pd.Timestamp(record["detected_at"])
            detected = detected.tz_localize("UTC") if detected.tzinfo is None else detected
        except (ValueError, KeyError, TypeError):
            continue
        symbol = str(record.get("symbol", "")).upper()
        if symbol in wanted and detected.to_pydatetime() >= cutoff:
            flagged.add(symbol)
    return sorted(flagged)


def utc_now_text(now: datetime | None = None) -> str:
    return (now or datetime.now(UTC)).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_prices(
    execution_date: date,
    symbols: Sequence[str],
    *,
    sip_root: Path = SIP_ROOT,
    symbol_origin: dict[str, list[str]] | None = None,
    require_minute: bool = True,
    now: datetime | None = None,
) -> dict[str, Any]:
    """The prices payload.  Raises :class:`DataNotFresh` when D has no bars yet."""
    symbols = sorted({s.upper() for s in symbols})
    close, daily_files = official_closes(sip_root, symbols, execution_date)
    if not close:
        raise DataNotFresh(f"data/sip/daily holds no bar of {execution_date} yet")
    snapshot, fallback, minute_files = snapshot_closes(sip_root, symbols, execution_date)
    if require_minute and not snapshot:
        day_start, day_end = ny_day_bounds_utc(execution_date)
        any_minute, _ = read_bars(sip_root, "minute", symbols, day_start, day_end)
        if any_minute.empty:
            raise DataNotFresh(f"data/sip/minute holds no bar of {execution_date} yet")
    missing_close = [s for s in symbols if s not in close]
    missing_snapshot = [s for s in symbols if s not in snapshot]
    return {
        "schema_version": SCHEMA_VERSION,
        "execution_date": execution_date.isoformat(),
        "built_at_utc": utc_now_text(now),
        "price_basis": PRICE_BASIS,
        "snapshot_rule": (
            "close of the minute bar labelled 15:44 ET (bars are labelled by start time); "
            f"fallback: latest earlier bar ending within {SNAPSHOT_FALLBACK_MINUTES} minutes of "
            "15:45 ET, listed in snapshot_fallback"
        ),
        "official_close": {s: close[s] for s in symbols if s in close},
        "snapshot_1545": {s: snapshot[s] for s in symbols if s in snapshot},
        "snapshot_fallback": dict(sorted(fallback.items())),
        "missing_official_close": missing_close,
        "missing_snapshot": missing_snapshot,
        "missing_reasons": {
            "official_close": _missing_reasons(sip_root, "daily", missing_close, execution_date),
            "snapshot_1545": _missing_reasons(sip_root, "minute", missing_snapshot, execution_date),
        },
        "restated_after_execution_date": restated_after(sip_root, symbols, execution_date),
        "symbols": symbols,
        "symbol_origin": symbol_origin or {},
        "sources": {
            "official_close": f"{Path(sip_root) / 'daily'} ({len(daily_files)} shard files read)",
            "snapshot_1545": f"{Path(sip_root) / 'minute'} ({len(minute_files)} shard files read)",
            "network": "none",
        },
    }


def prices_path(root: Path, execution_date: date) -> Path:
    return (
        Path(root) / "reports" / "paper" / "book" / "prices" / f"{execution_date.isoformat()}.json"
    )


def write_prices_file(payload: dict[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)
    return path


def build_and_write(
    execution_date: date,
    *,
    root: Path = ROOT,
    inputs: Sequence[Path] | None = None,
    sip_root: Path | None = None,
    out: Path | None = None,
    require_minute: bool = True,
    now: datetime | None = None,
) -> tuple[Path, dict[str, Any]]:
    """Resolve inputs, build, write.  Raises :class:`DataNotFresh` / :class:`InputsError`."""
    files = list(inputs) if inputs else discover_inputs(root, execution_date)
    symbols, origin = collect_symbols(files)
    payload = build_prices(
        execution_date,
        symbols,
        sip_root=sip_root if sip_root is not None else Path(root) / "data/sip",
        symbol_origin=origin,
        require_minute=require_minute,
        now=now,
    )
    payload["sources"]["symbols_from"] = [str(p) for p in files]
    return write_prices_file(payload, out or prices_path(root, execution_date)), payload


def summary_line(payload: dict[str, Any]) -> str:
    return (
        f"prices {payload['execution_date']}: symbols={len(payload['symbols'])} "
        f"official_close={len(payload['official_close'])} "
        f"missing_close={len(payload['missing_official_close'])} "
        f"snapshot={len(payload['snapshot_1545'])} fallback={len(payload['snapshot_fallback'])} "
        f"missing_snapshot={len(payload['missing_snapshot'])}"
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--execution-date", required=True)
    ap.add_argument(
        "--symbols-from",
        nargs="+",
        default=None,
        help="plan and/or target JSON files (default: the plans of the date and their targets)",
    )
    ap.add_argument("--out", default=None, help="default: reports/paper/book/prices/<D>.json")
    ap.add_argument("--root", default=str(ROOT), help="project root")
    ap.add_argument("--sip-root", default=None, help="default: <root>/data/sip")
    ap.add_argument(
        "--allow-missing-minute",
        action="store_true",
        help="write the file even when the minute archive holds no bar of the date",
    )
    args = ap.parse_args(argv)
    day = date.fromisoformat(args.execution_date)
    try:
        path, payload = build_and_write(
            day,
            root=Path(args.root),
            inputs=[Path(p) for p in args.symbols_from] if args.symbols_from else None,
            sip_root=Path(args.sip_root) if args.sip_root else None,
            out=Path(args.out) if args.out else None,
            require_minute=not args.allow_missing_minute,
        )
    except DataNotFresh as exc:
        print(f"not fresh: {exc}")
        return EXIT_NOT_FRESH
    except InputsError as exc:
        print(f"inputs: {exc}")
        return EXIT_INPUTS
    print(summary_line(payload))
    print(f"wrote {path}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
