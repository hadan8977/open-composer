from __future__ import annotations

import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from math import ceil
from pathlib import Path
from typing import Any

import pandas as pd

from open_composer.adapters.data import fetch_ohlcv
from open_composer.adapters.data.sample import normalize_ohlcv
from open_composer.config import data_feed, ensure_dir, project_root
from open_composer.market_calendar import (
    NEW_YORK,
    us_equity_session_close,
    validate_us_equity_bar_grid,
)
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
    required_symbol_coverage_threshold: float | None = None,
    max_rth_gap_rate: float = 0.0,
) -> MinuteFeasibilityResult:
    base = root or project_root()
    selected_feed = feed or data_feed()
    selected_symbols = [item.upper() for item in (symbols or DEFAULT_ETF_SYMBOLS)]
    reps = [item.upper() for item in (representative_symbols or DEFAULT_REPRESENTATIVE_SYMBOLS)]
    selected_timeframes = timeframes or DEFAULT_TIMEFRAMES
    coverage_threshold = _required_coverage_threshold(required_symbol_coverage_threshold)
    max_gap_rate = _max_rth_gap_rate(max_rth_gap_rate)
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
                    max_rth_gap_rate=max_gap_rate,
                )
            )
    timeframe_summary = _timeframe_summary(rows, coverage_threshold)
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
        "rth_boundary_session_policy": "drop_partial_first_and_last",
        "overnight_policy": "path-specific; first round must declare flat or hold explicitly",
        "iex_caveat": (
            "Alpaca IEX minute bars are research evidence, not consolidated SIP/full-market "
            "paper-ready market evidence unless account entitlements prove otherwise."
        ),
        "min_history_months_required": MIN_HISTORY_MONTHS,
        "required_symbol_coverage_threshold": coverage_threshold,
        "max_rth_gap_rate": max_gap_rate,
        "rows": rows,
        "timeframe_summary": timeframe_summary,
        "frequency_band_go_no_go": _frequency_band_go_no_go(timeframe_summary),
        "path_suitability": _path_suitability(rows, coverage_threshold),
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
        grid = validate_us_equity_bar_grid([], TIMEFRAME_MINUTES[timeframe])
        return {
            "records": 0,
            "first_timestamp": None,
            "last_timestamp": None,
            "history_months": 0.0,
            "extended_hours_present": False,
            "extended_hours_ratio": 0.0,
            "zero_volume_ratio": 0.0,
            **_grid_quality_fields(grid),
        }
    data = normalize_ohlcv(frame)
    timestamps = pd.to_datetime(data["timestamp"], utc=True)
    grid = validate_us_equity_bar_grid(timestamps, TIMEFRAME_MINUTES[timeframe])
    first = timestamps.min()
    last = timestamps.max()
    history_months = max((last - first).total_seconds() / (86400 * 30.4375), 0.0)
    zero_volume_ratio = float(
        (pd.to_numeric(data["volume"], errors="coerce").fillna(0) == 0).mean()
    )
    extended_ratio = grid["off_session_bar_count"] / len(data)
    return {
        "records": int(len(data)),
        "first_timestamp": first.isoformat(),
        "last_timestamp": last.isoformat(),
        "history_months": round(history_months, 2),
        "extended_hours_present": bool(grid["off_session_bar_count"]),
        "extended_hours_ratio": round(extended_ratio, 6),
        "zero_volume_ratio": round(zero_volume_ratio, 6),
        **_grid_quality_fields(grid),
    }


def _grid_quality_fields(grid: dict[str, Any]) -> dict[str, Any]:
    return {
        "timestamp_label": grid["timestamp_label"],
        "rth_gap_rate": grid["interior_gap_rate"],
        "rth_grid_coverage_ratio": grid["grid_coverage_ratio"],
        "rth_interior_coverage_ratio": grid["interior_coverage_ratio"],
        "rth_expected_bars": grid["expected_bar_count"],
        "rth_interior_expected_bars": grid["interior_expected_bar_count"],
        "rth_matched_bars": grid["matched_bar_count"],
        "rth_missing_bars": grid["missing_bar_count"],
        "rth_missing_interior_bars": grid["missing_interior_bar_count"],
        "rth_missing_boundary_bars": grid["missing_boundary_bar_count"],
        "rth_duplicate_bars": grid["duplicate_bar_count"],
        "off_session_bars": grid["off_session_bar_count"],
        "off_grid_bars": grid["off_grid_bar_count"],
        "rth_days": grid["observed_session_count"],
        "session_grid_quality_status": grid["quality_status"],
        "session_grid_quality_pass": grid["quality_pass"],
        "rth_boundary_session_policy": grid["boundary_session_policy"],
        "rth_quality_sessions": grid["quality_session_count"],
        "rth_dropped_boundary_sessions": grid["dropped_boundary_sessions"],
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
    max_rth_gap_rate: float = 0.0,
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
        history_go = quality["history_months"] >= MIN_HISTORY_MONTHS
        grid_blockers = _grid_go_blockers(quality, max_rth_gap_rate)
        row["history_go"] = history_go
        row["grid_go"] = not grid_blockers
        row["max_rth_gap_rate"] = max_rth_gap_rate
        row["go"] = history_go and row["grid_go"]
        blockers = []
        if not history_go:
            blockers.append(f"history_months<{MIN_HISTORY_MONTHS}")
        blockers.extend(grid_blockers)
        if row["go"]:
            dropped = len(quality["rth_dropped_boundary_sessions"])
            row["go_reason"] = f"history_and_session_grid_pass;boundary_sessions_dropped={dropped}"
        else:
            row["go_reason"] = ";".join(blockers)
        return row
    except Exception as exc:
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "status": "error",
            "error": str(exc),
            "records": 0,
            "history_months": 0.0,
            "timestamp_label": "start",
            "rth_gap_rate": 1.0,
            "rth_duplicate_bars": 0,
            "off_session_bars": 0,
            "off_grid_bars": 0,
            "rth_missing_boundary_bars": 0,
            "rth_days": 0,
            "history_go": False,
            "grid_go": False,
            "max_rth_gap_rate": max_rth_gap_rate,
            "go": False,
            "go_reason": "data_unavailable",
        }


def _grid_go_blockers(quality: dict[str, Any], max_rth_gap_rate: float) -> list[str]:
    blockers = []
    if int(quality["rth_interior_expected_bars"]) == 0:
        blockers.append("no_complete_session_after_boundary_drop")
    for field in ["rth_duplicate_bars", "off_session_bars", "off_grid_bars"]:
        if int(quality[field]) > 0:
            blockers.append(f"{field}>0")
    if float(quality["rth_gap_rate"]) > max_rth_gap_rate:
        blockers.append(f"rth_gap_rate>{max_rth_gap_rate}")
    return blockers


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
    return resample_us_equity_rth(frame, timeframe)


def resample_us_equity_rth(frame: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """Resample RTH bars to start-labelled, session-open-anchored buckets."""
    if timeframe not in TIMEFRAME_MINUTES:
        raise ValueError(f"unsupported minute timeframe: {timeframe}")
    data = normalize_ohlcv(frame)
    data["timestamp"] = pd.to_datetime(data["timestamp"], utc=True)
    local = data["timestamp"].dt.tz_convert(NEW_YORK)
    rth_mask = local.map(_is_rth_timestamp)
    data = data.loc[rth_mask].copy()
    if data.empty:
        return normalize_ohlcv(data[["timestamp", "open", "high", "low", "close", "volume"]])
    local = local.loc[rth_mask]
    data["session_date"] = local.dt.date.to_numpy()
    data["minutes_from_open"] = (local.dt.hour * 60 + local.dt.minute - (9 * 60 + 30)).to_numpy()
    target_minutes = TIMEFRAME_MINUTES[timeframe]
    data["bucket"] = data["minutes_from_open"] // target_minutes
    data = data.sort_values("timestamp")
    grouped = data.groupby(["session_date", "bucket"], sort=True)
    resampled = grouped.agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    )
    resampled = resampled.dropna().reset_index()
    resampled["timestamp"] = [
        pd.Timestamp(session_day, tz=NEW_YORK)
        + pd.Timedelta(hours=9, minutes=30 + int(bucket) * target_minutes)
        for session_day, bucket in zip(resampled["session_date"], resampled["bucket"], strict=True)
    ]
    return normalize_ohlcv(resampled[["timestamp", "open", "high", "low", "close", "volume"]])


def _is_rth_timestamp(timestamp: pd.Timestamp) -> bool:
    close = us_equity_session_close(timestamp.date())
    if close is None:
        return False
    local_time = timestamp.time().replace(tzinfo=None)
    return pd.Timestamp("09:30").time() <= local_time < close


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


def _timeframe_summary(
    rows: list[dict[str, Any]], required_coverage_threshold: float = 1.0
) -> dict[str, dict[str, Any]]:
    required_coverage_threshold = _required_coverage_threshold(required_coverage_threshold)
    summary: dict[str, dict[str, Any]] = {}
    for timeframe in DEFAULT_TIMEFRAMES:
        subset = [row for row in rows if row["timeframe"] == timeframe]
        if not subset:
            continue
        ok_rows = [row for row in subset if row.get("status") == "ok"]
        qualifying_rows = [row for row in ok_rows if row.get("go")]
        max_months = max((float(row.get("history_months") or 0.0) for row in ok_rows), default=0.0)
        min_months = min((float(row.get("history_months") or 0.0) for row in subset), default=0.0)
        checked_symbols = len({str(row["symbol"]) for row in subset})
        qualifying_symbols = len({str(row["symbol"]) for row in qualifying_rows})
        required_symbols = ceil(checked_symbols * required_coverage_threshold)
        coverage_ratio = qualifying_symbols / checked_symbols if checked_symbols else 0.0
        panel_go = checked_symbols > 0 and qualifying_symbols >= required_symbols
        summary[timeframe] = {
            "symbols_checked": checked_symbols,
            "ok_symbols": len(ok_rows),
            "error_symbols": len(subset) - len(ok_rows),
            "qualifying_symbols": qualifying_symbols,
            "required_symbols": required_symbols,
            "required_coverage_threshold": required_coverage_threshold,
            "symbol_coverage_ratio": round(coverage_ratio, 6),
            "max_history_months": round(max_months, 2),
            "min_history_months": round(min_months, 2),
            "go": panel_go,
            "go_reason": (
                f"qualifying_symbols={qualifying_symbols}>=required_symbols={required_symbols}"
                if panel_go
                else f"qualifying_symbols={qualifying_symbols}<required_symbols={required_symbols}"
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


def _path_suitability(
    rows: list[dict[str, Any]], required_coverage_threshold: float = 1.0
) -> dict[str, dict[str, Any]]:
    def ok_symbols(timeframe: str) -> set[str]:
        return {
            str(row["symbol"])
            for row in rows
            if row["timeframe"] == timeframe and row.get("status") == "ok" and row.get("go")
        }

    p1_timeframes = [
        timeframe for timeframe in ["15m", "30m", "1h"] if "QQQ" in ok_symbols(timeframe)
    ]
    p2_timeframes = []
    for timeframe in ["15m", "30m", "1h"]:
        requested = {
            str(row["symbol"])
            for row in rows
            if row["timeframe"] == timeframe and row["symbol"] in DEFAULT_ETF_SYMBOLS
        }
        qualifying = ok_symbols(timeframe).intersection(requested)
        required = ceil(len(requested) * required_coverage_threshold)
        if len(requested) >= 8 and len(qualifying) >= required:
            p2_timeframes.append(timeframe)
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
            "reason": (
                "requires at least 8 requested ETF symbols and the explicit symbol coverage "
                f"threshold ({required_coverage_threshold:.0%}) with >=18 months in one timeframe"
            ),
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


def _required_coverage_threshold(value: float | None) -> float:
    threshold = 1.0 if value is None else float(value)
    if not 0.0 < threshold <= 1.0:
        raise ValueError("required_symbol_coverage_threshold must be in (0, 1]")
    return threshold


def _max_rth_gap_rate(value: float) -> float:
    gap_rate = float(value)
    if not 0.0 <= gap_rate <= 1.0:
        raise ValueError("max_rth_gap_rate must be in [0, 1]")
    return gap_rate


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
