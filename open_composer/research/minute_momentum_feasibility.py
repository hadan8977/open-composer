from __future__ import annotations

import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from open_composer.adapters.data import fetch_ohlcv
from open_composer.adapters.data.sample import normalize_ohlcv
from open_composer.config import data_feed, ensure_dir, project_root
from open_composer.research.research_cache_manifest import sha256_file
from open_composer.storage import write_json

DEFAULT_ETF_SYMBOLS = [
    "QQQ",
    "SPY",
    "IWM",
    "DIA",
    "XLB",
    "XLC",
    "XLE",
    "XLF",
    "XLI",
    "XLK",
    "XLP",
    "XLRE",
    "XLU",
    "XLV",
    "XLY",
    "TQQQ",
    "SQQQ",
    "GLD",
    "TLT",
    "BIL",
]
DEFAULT_STOCK_SYMBOLS = [
    "AAPL",
    "MSFT",
    "NVDA",
    "AMZN",
    "META",
    "GOOGL",
    "AVGO",
    "TSLA",
    "AMD",
    "NFLX",
    "COST",
]
DEFAULT_TIMEFRAMES = ["1m", "5m", "15m", "30m", "1h"]
DEFAULT_REPRESENTATIVE_SYMBOLS = ["QQQ", "SPY", "TQQQ", "XLK", "NVDA"]
TIMEFRAME_MINUTES = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60}
MIN_HISTORY_MONTHS = 18.0


@dataclass(frozen=True)
class MinuteFeasibilityResult:
    json_path: Path
    markdown_path: Path
    manifest_path: Path
    payload: dict[str, Any]


def run_minute_momentum_feasibility(
    root: Path | None = None,
    *,
    symbols: list[str] | None = None,
    representative_symbols: list[str] | None = None,
    timeframes: list[str] | None = None,
    feed: str | None = None,
    start: str | None = None,
    end: str | None = None,
    fetch_missing: bool = False,
    report_date: str | None = None,
    output_dir: Path | None = None,
) -> MinuteFeasibilityResult:
    base = root or project_root()
    selected_feed = feed or data_feed()
    selected_symbols = [item.upper() for item in (symbols or DEFAULT_ETF_SYMBOLS)]
    reps = [item.upper() for item in (representative_symbols or DEFAULT_REPRESENTATIVE_SYMBOLS)]
    selected_timeframes = timeframes or DEFAULT_TIMEFRAMES
    for timeframe in selected_timeframes:
        if timeframe not in TIMEFRAME_MINUTES:
            raise ValueError(f"unsupported minute timeframe: {timeframe}")
    output = output_dir or base / "data" / "research" / "alpaca_minute"
    ensure_dir(output)
    parsed_start = _parse_timestamp(start)
    parsed_end = _parse_timestamp(end)
    generated_at = datetime.now(UTC)
    run_date = report_date or generated_at.strftime("%Y%m%d")
    rows: list[dict[str, Any]] = []
    for timeframe in selected_timeframes:
        timeframe_symbols = selected_symbols
        if timeframe in {"1m", "5m"}:
            timeframe_symbols = [symbol for symbol in reps if symbol in set(selected_symbols)]
        for symbol in timeframe_symbols:
            rows.append(
                _materialize_symbol_timeframe(
                    base,
                    output,
                    symbol,
                    timeframe,
                    selected_feed,
                    parsed_start,
                    parsed_end,
                    fetch_missing=fetch_missing,
                )
            )
    timeframe_summary = _timeframe_summary(rows)
    cost_table = _cost_table()
    payload: dict[str, Any] = {
        "report_type": "minute_momentum_feasibility",
        "generated_at": generated_at.isoformat(),
        "provider": "alpaca",
        "feed": selected_feed,
        "source_mode": "isolated_research_materialization",
        "output_dir": _relpath(output, base),
        "requested_start": parsed_start.isoformat() if parsed_start else None,
        "requested_end": parsed_end.isoformat() if parsed_end else None,
        "fetch_missing": fetch_missing,
        "symbols": selected_symbols,
        "representative_symbols_1m_5m": reps,
        "static_stock_universe_caveat": (
            "Any current large-cap stock subset is static and survivorship-prone; "
            "ETF paths are preferred for mom_minute_r1."
        ),
        "rth_only_assumption": True,
        "overnight_policy": "path-specific; first round must declare flat or hold explicitly",
        "iex_caveat": (
            "Alpaca IEX minute bars are research evidence, not consolidated SIP/full-market "
            "paper-ready market evidence unless account entitlements prove otherwise."
        ),
        "min_history_months_required": MIN_HISTORY_MONTHS,
        "rows": rows,
        "timeframe_summary": timeframe_summary,
        "frequency_band_go_no_go": _frequency_band_go_no_go(timeframe_summary),
        "path_suitability": _path_suitability(rows),
        "cost_table_bps": cost_table,
    }
    control_dir = base / "reports" / "research" / "control"
    ensure_dir(control_dir)
    json_path = control_dir / f"minute-momentum-feasibility-{run_date}.json"
    md_path = control_dir / f"minute-momentum-feasibility-{run_date}.md"
    manifest_path = control_dir / f"minute-momentum-feasibility-{run_date}-manifest.json"
    write_json(json_path, payload)
    write_json(
        manifest_path,
        {
            "report_type": "minute_momentum_materialization_manifest",
            "generated_at": generated_at.isoformat(),
            "provider": "alpaca",
            "feed": selected_feed,
            "output_dir": _relpath(output, base),
            "files": [
                {
                    "symbol": row["symbol"],
                    "timeframe": row["timeframe"],
                    "path": row.get("path"),
                    "sha256": row.get("sha256"),
                    "records": row.get("records"),
                    "status": row.get("status"),
                }
                for row in rows
            ],
        },
    )
    md_path.write_text(_render_markdown(payload, json_path, manifest_path), encoding="utf-8")
    return MinuteFeasibilityResult(
        json_path=json_path,
        markdown_path=md_path,
        manifest_path=manifest_path,
        payload=payload,
    )


def compute_minute_quality(frame: pd.DataFrame, timeframe: str) -> dict[str, Any]:
    if timeframe not in TIMEFRAME_MINUTES:
        raise ValueError(f"unsupported minute timeframe: {timeframe}")
    if frame.empty:
        return {
            "records": 0,
            "first_timestamp": None,
            "last_timestamp": None,
            "history_months": 0.0,
            "extended_hours_present": False,
            "extended_hours_ratio": 0.0,
            "zero_volume_ratio": 0.0,
            "rth_gap_rate": 1.0,
            "rth_days": 0,
        }
    data = normalize_ohlcv(frame)
    timestamps = pd.to_datetime(data["timestamp"], utc=True)
    local = timestamps.dt.tz_convert("America/New_York")
    session_time = local.dt.time
    rth_mask = session_time.map(
        lambda value: pd.Timestamp("09:30").time() <= value < pd.Timestamp("16:00").time()
    )
    rth = data.loc[rth_mask].copy()
    first = timestamps.min()
    last = timestamps.max()
    history_months = max((last - first).total_seconds() / (86400 * 30.4375), 0.0)
    zero_volume_ratio = float(
        (pd.to_numeric(data["volume"], errors="coerce").fillna(0) == 0).mean()
    )
    extended_ratio = float((~rth_mask).mean())
    return {
        "records": int(len(data)),
        "first_timestamp": first.isoformat(),
        "last_timestamp": last.isoformat(),
        "history_months": round(history_months, 2),
        "extended_hours_present": bool((~rth_mask).any()),
        "extended_hours_ratio": round(extended_ratio, 6),
        "zero_volume_ratio": round(zero_volume_ratio, 6),
        "rth_gap_rate": round(_rth_gap_rate(rth, timeframe), 6),
        "rth_days": int(_rth_session_count(rth)),
    }


def _materialize_symbol_timeframe(
    root: Path,
    output_dir: Path,
    symbol: str,
    timeframe: str,
    feed: str,
    start: datetime | None,
    end: datetime | None,
    *,
    fetch_missing: bool,
) -> dict[str, Any]:
    source_mode = "cache_copy"
    try:
        frame = _load_local_cache(root, symbol, timeframe, feed, start, end)
        resampled = _resampled_local_cache(root, symbol, timeframe, feed, start, end)
        if resampled is not None:
            resampled_frame, source_timeframe = resampled
            if frame is None or _history_months(resampled_frame) > _history_months(frame):
                frame = resampled_frame
                source_mode = f"cache_resampled_from_{source_timeframe}"
        if frame is None:
            if not fetch_missing:
                raise FileNotFoundError(f"missing Alpaca cache for {symbol} {timeframe} {feed}")
            frame = _fetch_to_temp_cache(root, symbol, timeframe, feed, start, end)
            source_mode = "live_fetch_isolated_copy"
        if frame.empty:
            raise ValueError(f"empty Alpaca frame for {symbol} {timeframe}")
        ensure_dir(output_dir)
        output_path = output_dir / f"{symbol.lower()}_{timeframe}_alpaca_{feed}.csv"
        frame.to_csv(output_path, index=False)
        quality = compute_minute_quality(frame, timeframe)
        row = {
            "symbol": symbol,
            "timeframe": timeframe,
            "status": "ok",
            "source_mode": source_mode,
            "path": _relpath(output_path, root),
            "sha256": sha256_file(output_path),
            **quality,
        }
        row["go"] = quality["history_months"] >= MIN_HISTORY_MONTHS
        row["go_reason"] = (
            f"history_months>={MIN_HISTORY_MONTHS}"
            if row["go"]
            else f"history_months<{MIN_HISTORY_MONTHS}"
        )
        return row
    except Exception as exc:
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "status": "error",
            "error": str(exc),
            "records": 0,
            "history_months": 0.0,
            "go": False,
            "go_reason": "data_unavailable",
        }


def _load_local_cache(
    root: Path,
    symbol: str,
    timeframe: str,
    feed: str,
    start: datetime | None,
    end: datetime | None,
) -> pd.DataFrame | None:
    cache_path = root / "data" / "cache" / f"{symbol.lower()}_{timeframe}_{feed}.csv"
    if not cache_path.exists():
        return None
    frame = normalize_ohlcv(pd.read_csv(cache_path))
    return _filter_window(frame, start, end)


def _resampled_local_cache(
    root: Path,
    symbol: str,
    timeframe: str,
    feed: str,
    start: datetime | None,
    end: datetime | None,
) -> tuple[pd.DataFrame, str] | None:
    target_minutes = TIMEFRAME_MINUTES[timeframe]
    for source_timeframe in ["1m", "5m", "15m", "30m"]:
        source_minutes = TIMEFRAME_MINUTES[source_timeframe]
        if source_minutes >= target_minutes:
            continue
        source = _load_local_cache(root, symbol, source_timeframe, feed, start, end)
        if source is None or source.empty:
            continue
        return _resample_frame(source, timeframe), source_timeframe
    return None


def _resample_frame(frame: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    data = normalize_ohlcv(frame)
    data["timestamp"] = pd.to_datetime(data["timestamp"], utc=True)
    local = data["timestamp"].dt.tz_convert("America/New_York")
    session_time = local.dt.time
    rth_mask = session_time.map(
        lambda value: pd.Timestamp("09:30").time() <= value < pd.Timestamp("16:00").time()
    )
    data = data.loc[rth_mask].copy()
    local = local.loc[rth_mask]
    data["session_date"] = local.dt.date.astype(str).to_numpy()
    data["minutes_from_open"] = (local.dt.hour * 60 + local.dt.minute - (9 * 60 + 30)).to_numpy()
    target_minutes = TIMEFRAME_MINUTES[timeframe]
    data["bucket"] = data["minutes_from_open"] // target_minutes
    data = data.sort_values("timestamp")
    grouped = data.groupby(["session_date", "bucket"], sort=True)
    resampled = grouped.agg(
        timestamp=("timestamp", "first"),
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    )
    return normalize_ohlcv(resampled.dropna().reset_index())


def _fetch_to_temp_cache(
    root: Path,
    symbol: str,
    timeframe: str,
    feed: str,
    start: datetime | None,
    end: datetime | None,
) -> pd.DataFrame:
    tmp_parent = root / ".tmp"
    ensure_dir(tmp_parent)
    with tempfile.TemporaryDirectory(prefix="alpaca-minute-", dir=tmp_parent) as tmp:
        tmp_root = Path(tmp)
        return fetch_ohlcv(
            root=tmp_root,
            symbol=symbol,
            timeframe=timeframe,
            start=start,
            end=end,
            source="alpaca",
            feed=feed,
            use_cache=False,
            allow_fallback=False,
        )


def _filter_window(
    frame: pd.DataFrame,
    start: datetime | None,
    end: datetime | None,
) -> pd.DataFrame:
    result = frame.copy()
    timestamps = pd.to_datetime(result["timestamp"], utc=True)
    if start is not None:
        result = result.loc[timestamps >= pd.Timestamp(start)]
        timestamps = pd.to_datetime(result["timestamp"], utc=True)
    if end is not None:
        result = result.loc[timestamps <= pd.Timestamp(end)]
    return result.reset_index(drop=True)


def _timeframe_summary(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    summary: dict[str, dict[str, Any]] = {}
    for timeframe in DEFAULT_TIMEFRAMES:
        subset = [row for row in rows if row["timeframe"] == timeframe]
        if not subset:
            continue
        ok_rows = [row for row in subset if row.get("status") == "ok"]
        max_months = max((float(row.get("history_months") or 0.0) for row in ok_rows), default=0.0)
        summary[timeframe] = {
            "symbols_checked": len(subset),
            "ok_symbols": len(ok_rows),
            "error_symbols": len(subset) - len(ok_rows),
            "max_history_months": round(max_months, 2),
            "go": max_months >= MIN_HISTORY_MONTHS,
            "go_reason": (
                f"max_history_months>={MIN_HISTORY_MONTHS}"
                if max_months >= MIN_HISTORY_MONTHS
                else f"max_history_months<{MIN_HISTORY_MONTHS}"
            ),
        }
    return summary


def _history_months(frame: pd.DataFrame) -> float:
    if frame.empty:
        return 0.0
    timestamps = pd.to_datetime(frame["timestamp"], utc=True)
    return max((timestamps.max() - timestamps.min()).total_seconds() / (86400 * 30.4375), 0.0)


def _frequency_band_go_no_go(summary: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    bands = {
        "high_frequency_1m_5m": ["1m", "5m"],
        "medium_frequency_15m_30m": ["15m", "30m"],
        "lower_frequency_1h": ["1h"],
    }
    result: dict[str, dict[str, Any]] = {}
    for band, timeframes in bands.items():
        available = {tf: summary.get(tf, {}) for tf in timeframes}
        go_timeframes = [tf for tf, row in available.items() if row.get("go")]
        result[band] = {
            "go": bool(go_timeframes),
            "go_timeframes": go_timeframes,
            "timeframes": available,
        }
    return result


def _path_suitability(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    def ok_symbols(timeframe: str) -> set[str]:
        return {
            str(row["symbol"])
            for row in rows
            if row["timeframe"] == timeframe and row.get("status") == "ok" and row.get("go")
        }

    p1_timeframes = [
        timeframe for timeframe in ["15m", "30m", "1h"] if "QQQ" in ok_symbols(timeframe)
    ]
    p2_timeframes = [
        timeframe
        for timeframe in ["15m", "30m", "1h"]
        if len(ok_symbols(timeframe).intersection(DEFAULT_ETF_SYMBOLS)) >= 8
    ]
    p3_timeframes = [timeframe for timeframe in ["30m", "1h"] if "QQQ" in ok_symbols(timeframe)]
    return {
        "P1_time_series_etf_momentum": {
            "go": bool(p1_timeframes),
            "go_timeframes": p1_timeframes,
            "reason": "requires QQQ history on 15m/30m/1h",
        },
        "P2_cross_sectional_etf_rotation": {
            "go": bool(p2_timeframes),
            "go_timeframes": p2_timeframes,
            "reason": "requires at least 8 ETF symbols with >=18 months in the same timeframe",
        },
        "P3_overnight_intraday_decomposition": {
            "go": bool(p3_timeframes),
            "go_timeframes": p3_timeframes,
            "reason": "requires QQQ history on 30m/1h plus daily/overnight decomposition",
        },
    }


def _cost_table() -> dict[str, dict[str, float]]:
    base = {"1m": 8.0, "5m": 6.0, "15m": 4.0, "30m": 3.0, "1h": 2.0}
    return {
        timeframe: {"base": bps, "stress_2x": bps * 2, "stress_4x": bps * 4}
        for timeframe, bps in base.items()
    }


def _rth_gap_rate(frame: pd.DataFrame, timeframe: str) -> float:
    if frame.empty:
        return 1.0
    data = frame.copy()
    timestamps = pd.to_datetime(data["timestamp"], utc=True)
    local = timestamps.dt.tz_convert("America/New_York")
    data["session_date"] = local.dt.date.astype(str)
    expected_per_day = max(int(390 / TIMEFRAME_MINUTES[timeframe]), 1)
    total_expected = 0
    total_actual = 0
    for _, group in data.groupby("session_date", sort=True):
        total_expected += expected_per_day
        total_actual += min(len(group), expected_per_day)
    if total_expected == 0:
        return 1.0
    return max((total_expected - total_actual) / total_expected, 0.0)


def _rth_session_count(frame: pd.DataFrame) -> int:
    if frame.empty:
        return 0
    local = pd.to_datetime(frame["timestamp"], utc=True).dt.tz_convert("America/New_York")
    return int(local.dt.date.nunique())


def _render_markdown(payload: dict[str, Any], json_path: Path, manifest_path: Path) -> str:
    lines = [
        "# Minute Momentum Feasibility",
        "",
        f"- Generated at: `{payload['generated_at']}`",
        f"- Provider/feed: `alpaca/{payload['feed']}`",
        f"- JSON: `{json_path}`",
        f"- Manifest: `{manifest_path}`",
        f"- Output dir: `{payload['output_dir']}`",
        f"- Fetch missing: `{payload['fetch_missing']}`",
        f"- Minimum history months: `{payload['min_history_months_required']}`",
        f"- IEX caveat: {payload['iex_caveat']}",
        f"- Static stock caveat: {payload['static_stock_universe_caveat']}",
        "",
        "## Frequency Bands",
        "",
        "| band | go | go timeframes |",
        "|---|---:|---|",
    ]
    for band, row in payload["frequency_band_go_no_go"].items():
        lines.append(f"| `{band}` | `{row['go']}` | {', '.join(row['go_timeframes']) or 'none'} |")
    lines.extend(
        [
            "",
            "## Path Suitability",
            "",
            "| path | go | go timeframes | reason |",
            "|---|---:|---|---|",
        ]
    )
    for path_name, row in payload["path_suitability"].items():
        lines.append(
            f"| `{path_name}` | `{row['go']}` | {', '.join(row['go_timeframes']) or 'none'} | "
            f"{row['reason']} |"
        )
    lines.extend(
        [
            "",
            "## Timeframes",
            "",
            "| timeframe | go | ok/error | max months |",
            "|---|---:|---:|---:|",
        ]
    )
    for timeframe, row in payload["timeframe_summary"].items():
        lines.append(
            f"| `{timeframe}` | `{row['go']}` | {row['ok_symbols']}/{row['error_symbols']} | "
            f"{row['max_history_months']:.2f} |"
        )
    lines.extend(
        ["", "## Cost Table (bps)", "", "| timeframe | base | x2 | x4 |", "|---|---:|---:|---:|"]
    )
    for timeframe, row in payload["cost_table_bps"].items():
        lines.append(
            f"| `{timeframe}` | {row['base']:.1f} | {row['stress_2x']:.1f} | "
            f"{row['stress_4x']:.1f} |"
        )
    lines.extend(
        [
            "",
            "## Symbol Rows",
            "",
            "| symbol | timeframe | status | records | months | go | note |",
            "|---|---|---|---:|---:|---:|---|",
        ]
    )
    for row in payload["rows"]:
        note = row.get("go_reason") or row.get("error", "")
        lines.append(
            f"| `{row['symbol']}` | `{row['timeframe']}` | `{row['status']}` | "
            f"{row.get('records', 0)} | {float(row.get('history_months') or 0.0):.2f} | "
            f"`{row.get('go', False)}` | {note} |"
        )
    return "\n".join(lines).rstrip() + "\n"


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize(UTC)
    else:
        timestamp = timestamp.tz_convert(UTC)
    return timestamp.to_pydatetime()


def _relpath(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)
