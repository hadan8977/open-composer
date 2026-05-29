from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from typing import Any

from open_composer.adapters.data.comparison import OhlcvComparison, compare_ohlcv_sources
from open_composer.config import ensure_dir, project_root
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.storage import write_json


@dataclass(frozen=True)
class StrategyDataCompareResult:
    json_path: Path
    report_path: Path
    status: str
    compared_symbols: list[str]
    blockers: list[str]


def run_strategy_data_compare(
    spec_path: Path,
    root: Path | None = None,
    *,
    primary: str,
    secondary: str,
    symbols: list[str] | None = None,
    max_symbols: int | None = None,
) -> StrategyDataCompareResult:
    base = root or project_root()
    spec = load_strategy_spec(spec_path)
    left_source, left_feed = _parse_side(primary)
    right_source, right_feed = _parse_side(secondary)
    universe = [item.upper() for item in (symbols or spec.universe)]
    if max_symbols is not None:
        universe = universe[: max(max_symbols, 1)]
    rows: list[dict[str, Any]] = []
    comparisons: list[OhlcvComparison] = []
    blockers: list[str] = []
    for symbol in universe:
        try:
            comparison = compare_ohlcv_sources(
                base,
                symbol,
                str(spec.timeframe),
                left_source,
                right_source,
                left_feed,
                right_feed,
            )
        except Exception as exc:  # noqa: BLE001 - artifact must capture provider/config failures.
            blockers.append(f"{symbol}: {type(exc).__name__}: {exc}")
            rows.append({"symbol": symbol, "status": "blocked", "error": str(exc)})
            continue
        comparisons.append(comparison)
        rows.append(_comparison_row(comparison))
    status = _status(comparisons, blockers)
    remediation = _remediation(status, blockers, right_source, right_feed)
    json_path = base / "reports" / "harness" / "data" / f"{spec.name}-data-compare.json"
    report_path = json_path.with_suffix(".md")
    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "strategy_name": spec.name,
        "source_spec_path": _relpath(spec_path, base),
        "primary": {"source": left_source, "feed": left_feed},
        "secondary": {"source": right_source, "feed": right_feed},
        "timeframe": str(spec.timeframe),
        "compared_symbols": [item.symbol for item in comparisons],
        "requested_symbols": universe,
        "compared_window": _compared_window(comparisons),
        "bar_count_primary": sum(item.left_rows for item in comparisons),
        "bar_count_secondary": sum(item.right_rows for item in comparisons),
        "missing_bar_count": sum(
            item.missing_left_rows + item.missing_right_rows for item in comparisons
        ),
        "timestamp_alignment_pct": _mean_or_zero(item.matched_coverage_pct for item in comparisons),
        "close_drift_bps_p50": _mean_or_zero(item.mean_abs_close_diff_bps for item in comparisons),
        "close_drift_bps_p95": max(
            (item.max_abs_close_diff_bps for item in comparisons), default=0.0
        ),
        "close_drift_bps_max": max(
            (item.max_abs_close_diff_bps for item in comparisons), default=0.0
        ),
        "volume_drift_pct_p50": _mean_or_zero(
            item.max_volume_diff_ratio * 100 for item in comparisons
        ),
        "volume_drift_pct_p95": max(
            (item.max_volume_diff_ratio * 100 for item in comparisons), default=0.0
        ),
        "volume_drift_pct_max": max(
            (item.max_volume_diff_ratio * 100 for item in comparisons), default=0.0
        ),
        "strict_data_status": status,
        "blockers": blockers,
        "remediation": remediation,
        "symbol_results": rows,
    }
    write_json(json_path, payload)
    _write_markdown(report_path, payload)
    return StrategyDataCompareResult(
        json_path=json_path,
        report_path=report_path,
        status=status,
        compared_symbols=[item.symbol for item in comparisons],
        blockers=blockers,
    )


def _parse_side(value: str) -> tuple[str, str | None]:
    source, _, feed = value.partition(":")
    return source.strip().lower(), feed.strip().lower() or None


def _comparison_row(report: OhlcvComparison) -> dict[str, Any]:
    return {
        "symbol": report.symbol,
        "status": "ok",
        "bar_count_primary": report.left_rows,
        "bar_count_secondary": report.right_rows,
        "missing_bar_count": report.missing_left_rows + report.missing_right_rows,
        "timestamp_alignment_pct": report.matched_coverage_pct,
        "close_drift_bps_mean": report.mean_abs_close_diff_bps,
        "close_drift_bps_max": report.max_abs_close_diff_bps,
        "volume_drift_pct_max": report.max_volume_diff_ratio * 100,
        "first_matched_timestamp": report.first_matched_timestamp,
        "last_matched_timestamp": report.last_matched_timestamp,
        "source_report_json": report.report_json_path,
    }


def _status(comparisons: list[OhlcvComparison], blockers: list[str]) -> str:
    if blockers or not comparisons:
        return "blocked"
    min_coverage = min(item.matched_coverage_pct for item in comparisons)
    max_close_drift = max(item.max_abs_close_diff_bps for item in comparisons)
    if min_coverage < 99.0 or max_close_drift > 5.0:
        return "warning"
    return "ok"


def _remediation(
    status: str,
    blockers: list[str],
    secondary_source: str,
    secondary_feed: str | None,
) -> list[str]:
    if status == "ok":
        return ["Data comparison passed threshold; keep raw source reports for audit."]
    if blockers:
        return [
            f"Configure or refresh secondary source `{secondary_source}:{secondary_feed or ''}`.",
            "Re-run this command after the secondary cache/provider is available.",
            *blockers[:5],
        ]
    return [
        "Review missing timestamps and drift source reports under reports/data/comparisons.",
        "Use a paper-ready consolidated feed before treating strict_data as passed.",
    ]


def _compared_window(comparisons: list[OhlcvComparison]) -> dict[str, str | None]:
    starts = [item.first_matched_timestamp for item in comparisons if item.first_matched_timestamp]
    ends = [item.last_matched_timestamp for item in comparisons if item.last_matched_timestamp]
    return {"start": min(starts) if starts else None, "end": max(ends) if ends else None}


def _mean_or_zero(values: Any) -> float:
    rows = [float(item) for item in values]
    return mean(rows) if rows else 0.0


def _write_markdown(path: Path, payload: dict[str, Any]) -> Path:
    ensure_dir(path.parent)
    lines = [
        f"# Strategy Data Compare: {payload['strategy_name']}",
        "",
        f"- Status: `{payload['strict_data_status']}`",
        f"- Primary: `{payload['primary']['source']}:{payload['primary']['feed'] or ''}`",
        f"- Secondary: `{payload['secondary']['source']}:{payload['secondary']['feed'] or ''}`",
        f"- Compared symbols: `{', '.join(payload['compared_symbols']) or 'none'}`",
        f"- Timestamp alignment: `{payload['timestamp_alignment_pct']:.2f}%`",
        f"- Close drift p95/max bps: "
        f"`{payload['close_drift_bps_p95']:.2f}/{payload['close_drift_bps_max']:.2f}`",
        f"- Missing bars: `{payload['missing_bar_count']}`",
        "",
        "## Remediation",
        "",
        *[f"- {item}" for item in payload["remediation"]],
        "",
        "## Symbols",
        "",
        "| Symbol | Status | Alignment | Close Drift Max bps | Missing Bars |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in payload["symbol_results"]:
        lines.append(
            f"| {row.get('symbol')} | {row.get('status')} | "
            f"{float(row.get('timestamp_alignment_pct') or 0.0):.2f}% | "
            f"{float(row.get('close_drift_bps_max') or 0.0):.2f} | "
            f"{int(row.get('missing_bar_count') or 0)} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _relpath(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()
