"""Fail-closed quality checks for historical price-adjustment bundles."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

import pandas as pd

from open_composer.storage import write_json

REQUIRED_ADJUSTMENTS = ("raw", "split", "dividend", "all")
ADJUSTED_MODES = ("split", "all")
COMMON_SPLIT_FACTORS = (2.0, 3.0, 4.0, 5.0, 10.0, 20.0, 25.0, 50.0)


def audit_price_adjustment_snapshot(
    root: Path,
    manifest_path: Path,
    *,
    require_complete_adjustments: bool = True,
) -> dict[str, Any]:
    """Audit daily price files without treating provider adjustment labels as proof."""

    base = root.resolve()
    manifest_file = _regular_in_root(base, manifest_path)
    manifest_bytes = manifest_file.read_bytes()
    manifest = _json_object(manifest_bytes, label="price snapshot manifest")
    raw_items = manifest.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        raise ValueError("price snapshot manifest has no items")

    frames: dict[tuple[str, str], pd.DataFrame] = {}
    file_rows: list[dict[str, Any]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            raise ValueError("price snapshot item must be an object")
        timeframe = str(item.get("timeframe") or "daily").lower()
        if timeframe not in {"daily", "1d"}:
            continue
        symbol = str(item.get("symbol") or "").strip().upper()
        adjustment = str(item.get("adjustment") or "").strip().lower()
        if not symbol or adjustment not in REQUIRED_ADJUSTMENTS:
            raise ValueError("daily price snapshot item identity is invalid")
        identity = (symbol, adjustment)
        if identity in frames:
            raise ValueError(f"duplicate daily price snapshot item: {symbol}/{adjustment}")
        output_path = manifest_file.parent / str(item.get("output_path") or "")
        output_file = _regular_in_root(base, output_path)
        output_sha256 = _sha256(output_file)
        expected_sha256 = str(item.get("output_sha256") or "")
        if expected_sha256 and output_sha256 != expected_sha256:
            raise ValueError(f"price snapshot item hash mismatch: {symbol}/{adjustment}")
        frame = _read_daily_price_file(output_file)
        frames[identity] = frame
        file_rows.append(
            {
                "symbol": symbol,
                "adjustment": adjustment,
                "path": output_file.relative_to(base).as_posix(),
                "sha256": output_sha256,
                "row_count": len(frame),
                "first_session": frame.index[0].date().isoformat(),
                "last_session": frame.index[-1].date().isoformat(),
            }
        )
    if not frames:
        raise ValueError("price snapshot has no daily adjustment files")

    symbols = sorted({symbol for symbol, _ in frames})
    blockers: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    series_rows: list[dict[str, Any]] = []
    events_by_identity: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for symbol in symbols:
        available = sorted(mode for candidate, mode in frames if candidate == symbol)
        missing = sorted(set(REQUIRED_ADJUSTMENTS) - set(available))
        if require_complete_adjustments and missing:
            blockers.append(
                {
                    "code": "incomplete_adjustment_bundle",
                    "symbol": symbol,
                    "missing_adjustments": missing,
                    "available_adjustments": available,
                }
            )
        for adjustment in available:
            frame = frames[(symbol, adjustment)]
            events = _extreme_events(frame)
            events_by_identity[(symbol, adjustment)] = events
            close_returns = frame["close"].pct_change().dropna()
            overnight = frame["open"].div(frame["close"].shift(1)).sub(1.0).dropna()
            series_rows.append(
                {
                    "symbol": symbol,
                    "adjustment": adjustment,
                    "row_count": len(frame),
                    "maximum_absolute_close_return": _finite_max_abs(close_returns),
                    "maximum_absolute_overnight_gap": _finite_max_abs(overnight),
                    "extreme_event_count": len(events),
                }
            )

    for symbol in symbols:
        available = {mode for candidate, mode in frames if candidate == symbol}
        complete = set(REQUIRED_ADJUSTMENTS).issubset(available)
        for adjustment in ADJUSTED_MODES:
            for event in events_by_identity.get((symbol, adjustment), []):
                issue = {
                    "symbol": symbol,
                    "adjustment": adjustment,
                    **event,
                }
                if event["split_like_factor"] is not None:
                    blockers.append(
                        {
                            "code": "split_like_discontinuity_in_adjusted_series",
                            **issue,
                        }
                    )
                    continue
                if not complete:
                    blockers.append(
                        {
                            "code": "unreconciled_extreme_move_in_adjusted_series",
                            **issue,
                        }
                    )
                    continue
                comparison = _cross_mode_comparison(frames, symbol, event["session"])
                if comparison["consistent"]:
                    warnings.append(
                        {
                            "code": "cross_mode_consistent_extreme_market_move",
                            **issue,
                            "cross_mode_close_returns": comparison["close_returns"],
                        }
                    )
                else:
                    blockers.append(
                        {
                            "code": "cross_adjustment_discontinuity_mismatch",
                            **issue,
                            "cross_mode_close_returns": comparison["close_returns"],
                        }
                    )

    status = "ok" if not blockers else "blocked"
    return {
        "schema_version": 1,
        "report_type": "historical_price_adjustment_quality",
        "status": status,
        "research_eligible": not blockers,
        "paper_eligible": False,
        "paper_eligibility_reason": "historical price quality is not paper authorization",
        "manifest_path": manifest_file.relative_to(base).as_posix(),
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "snapshot_contract": manifest.get("snapshot_contract"),
        "iter_id": manifest.get("iter_id"),
        "provider": manifest.get("provider"),
        "feed": manifest.get("feed"),
        "required_adjustments": list(REQUIRED_ADJUSTMENTS),
        "require_complete_adjustments": require_complete_adjustments,
        "symbols": symbols,
        "symbol_count": len(symbols),
        "files": sorted(file_rows, key=lambda row: (row["symbol"], row["adjustment"])),
        "series": sorted(series_rows, key=lambda row: (row["symbol"], row["adjustment"])),
        "blocking_issue_count": len(blockers),
        "warning_count": len(warnings),
        "blocking_issues": blockers,
        "warnings": warnings,
        "thresholds": {
            "absolute_overnight_gap": 0.35,
            "absolute_close_return": 0.45,
            "split_factor_relative_tolerance": 0.08,
            "cross_mode_return_tolerance_bps": 50.0,
        },
        "conclusion": (
            "historical_results_using_this snapshot are invalid until the blocking issues "
            "are resolved"
            if blockers
            else "adjustment bundle passed mechanical discontinuity and cross-mode checks"
        ),
        "limitations": [
            "This is a mechanical adjustment-integrity gate, not proof of point-in-time data.",
            "Cross-mode-consistent extreme moves remain warnings and require market-event review.",
            "Corporate-action event lineage is still required before promotion.",
        ],
    }


def write_price_adjustment_quality_report(
    root: Path,
    manifest_path: Path,
    report_path: Path,
    *,
    require_complete_adjustments: bool = True,
    overwrite: bool = False,
) -> Path:
    base = root.resolve()
    output = report_path if report_path.is_absolute() else base / report_path
    try:
        output.resolve().relative_to(base)
    except ValueError as exc:
        raise ValueError("price quality report path escapes the project root") from exc
    if output.exists() and not overwrite:
        raise ValueError(f"price quality report already exists: {output}")
    payload = audit_price_adjustment_snapshot(
        base,
        manifest_path,
        require_complete_adjustments=require_complete_adjustments,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    write_json(output, payload)
    return output


def _read_daily_price_file(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    if not required.issubset(frame.columns):
        raise ValueError(f"daily price file columns are incomplete: {path}")
    timestamps = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
    sessions = pd.DatetimeIndex(
        timestamps.dt.tz_convert("America/New_York").dt.tz_localize(None).dt.normalize()
    )
    if sessions.has_duplicates or not sessions.is_monotonic_increasing:
        raise ValueError(f"daily price sessions are duplicate or unordered: {path}")
    output = frame.loc[:, ["open", "high", "low", "close", "volume"]].apply(
        pd.to_numeric,
        errors="raise",
    )
    output.index = sessions
    if not output.map(lambda value: math.isfinite(float(value))).all().all():
        raise ValueError(f"daily price file contains nonfinite values: {path}")
    if (output[["open", "high", "low", "close"]] <= 0).any().any():
        raise ValueError(f"daily price file contains nonpositive prices: {path}")
    if (output["volume"] < 0).any():
        raise ValueError(f"daily price file contains negative volume: {path}")
    if (output["high"] < output[["open", "close", "low"]].max(axis=1)).any() or (
        output["low"] > output[["open", "close", "high"]].min(axis=1)
    ).any():
        raise ValueError(f"daily price file contains inconsistent OHLC bounds: {path}")
    return output.astype(float)


def _extreme_events(frame: pd.DataFrame) -> list[dict[str, Any]]:
    previous_close = frame["close"].shift(1)
    open_ratio = frame["open"].div(previous_close)
    close_ratio = frame["close"].div(previous_close)
    mask = open_ratio.sub(1.0).abs().ge(0.35) | close_ratio.sub(1.0).abs().ge(0.45)
    rows: list[dict[str, Any]] = []
    for session in frame.index[mask.fillna(False)]:
        open_value = float(open_ratio.loc[session])
        close_value = float(close_ratio.loc[session])
        factor = _split_like_factor(open_value, close_value)
        rows.append(
            {
                "session": session.date().isoformat(),
                "previous_session": frame.index[frame.index.get_loc(session) - 1]
                .date()
                .isoformat(),
                "overnight_gap": open_value - 1.0,
                "close_return": close_value - 1.0,
                "split_like_factor": factor,
            }
        )
    return rows


def _split_like_factor(open_ratio: float, close_ratio: float) -> float | None:
    candidates = (*COMMON_SPLIT_FACTORS, *(1.0 / value for value in COMMON_SPLIT_FACTORS))
    best: tuple[float, float] | None = None
    for observed in (open_ratio, close_ratio):
        for factor in candidates:
            error = abs(observed - factor) / factor
            if best is None or error < best[0]:
                best = (error, factor)
    if best is None or best[0] > 0.08:
        return None
    return float(best[1])


def _cross_mode_comparison(
    frames: dict[tuple[str, str], pd.DataFrame],
    symbol: str,
    session: str,
) -> dict[str, Any]:
    timestamp = pd.Timestamp(session)
    values: dict[str, float] = {}
    for adjustment in REQUIRED_ADJUSTMENTS:
        frame = frames[(symbol, adjustment)]
        if timestamp not in frame.index:
            return {"consistent": False, "close_returns": values}
        location = frame.index.get_loc(timestamp)
        if not isinstance(location, int) or location == 0:
            return {"consistent": False, "close_returns": values}
        values[adjustment] = float(
            frame["close"].iloc[location] / frame["close"].iloc[location - 1] - 1.0
        )
    spread_bps = (max(values.values()) - min(values.values())) * 10_000.0
    return {"consistent": spread_bps <= 50.0 + 1e-12, "close_returns": values}


def _finite_max_abs(values: pd.Series) -> float:
    if values.empty:
        return 0.0
    result = float(values.abs().max())
    if not math.isfinite(result):
        raise ValueError("price return diagnostic is nonfinite")
    return result


def _regular_in_root(root: Path, path: Path) -> Path:
    candidate = path if path.is_absolute() else root / path
    cursor = candidate
    while cursor != root and cursor != cursor.parent:
        if cursor.is_symlink():
            raise ValueError(f"price quality path cannot use symlinks: {candidate}")
        cursor = cursor.parent
    resolved = candidate.resolve(strict=True)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"price quality path escapes the project root: {candidate}") from exc
    if not resolved.is_file():
        raise ValueError(f"price quality path is not a regular file: {candidate}")
    return resolved


def _json_object(raw: bytes, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is invalid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be an object")
    return payload


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
