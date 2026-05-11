from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

import pandas as pd

from open_composer.adapters.data.alpaca import fetch_alpaca_bars
from open_composer.adapters.data.longbridge import fetch_longbridge_bars, longbridge_cache_path
from open_composer.adapters.data.provenance import cache_manifest_path, write_ohlcv_manifest
from open_composer.adapters.data.sample import normalize_ohlcv
from open_composer.config import data_feed, ensure_dir
from open_composer.storage import write_json


@dataclass(frozen=True)
class OhlcvComparison:
    symbol: str
    timeframe: str
    left_source: str
    right_source: str
    left_feed: str | None
    right_feed: str | None
    left_rows: int
    right_rows: int
    matched_rows: int
    missing_left_rows: int
    missing_right_rows: int
    matched_coverage_pct: float
    max_abs_close_diff: float
    mean_abs_close_diff: float
    max_abs_close_diff_bps: float
    mean_abs_close_diff_bps: float
    max_abs_volume_diff: float
    max_volume_diff_ratio: float
    first_matched_timestamp: str | None
    last_matched_timestamp: str | None
    sample_missing_left_timestamps: list[str]
    sample_missing_right_timestamps: list[str]
    left_manifest_path: str | None
    right_manifest_path: str | None
    caveats: list[str]
    report_json_path: str
    report_markdown_path: str


def compare_ohlcv_sources(
    root: Path,
    symbol: str,
    timeframe: str,
    left_source: str,
    right_source: str,
    left_feed: str | None = None,
    right_feed: str | None = None,
) -> OhlcvComparison:
    left = _load_source_frame(root, symbol, timeframe, left_source, left_feed)
    right = _load_source_frame(root, symbol, timeframe, right_source, right_feed)
    merged = left.merge(
        right,
        on="timestamp",
        how="outer",
        suffixes=("_left", "_right"),
        indicator=True,
    )
    matched = merged[merged["_merge"] == "both"].copy()
    left_only = merged[merged["_merge"] == "left_only"]
    right_only = merged[merged["_merge"] == "right_only"]
    close_diff = (
        (matched["close_left"] - matched["close_right"]).abs()
        if not matched.empty
        else pd.Series(dtype=float)
    )
    close_mid = (
        ((matched["close_left"] + matched["close_right"]) / 2).abs()
        if not matched.empty
        else pd.Series(dtype=float)
    )
    close_diff_bps = (
        (close_diff / close_mid.replace(0, pd.NA) * 10_000).dropna()
        if not matched.empty
        else pd.Series(dtype=float)
    )
    volume_diff = (
        (matched["volume_left"] - matched["volume_right"]).abs()
        if not matched.empty
        else pd.Series(dtype=float)
    )
    volume_max = (
        matched[["volume_left", "volume_right"]].max(axis=1).replace(0, pd.NA)
        if not matched.empty
        else pd.Series(dtype=float)
    )
    volume_diff_ratio = (
        (volume_diff / volume_max).dropna() if not matched.empty else pd.Series(dtype=float)
    )
    max_rows = max(len(left), len(right), 1)
    left_manifest = _manifest_path(root, symbol, timeframe, left_source, left_feed)
    right_manifest = _manifest_path(root, symbol, timeframe, right_source, right_feed)
    report = OhlcvComparison(
        symbol=symbol.upper(),
        timeframe=timeframe,
        left_source=left_source,
        right_source=right_source,
        left_feed=left_feed,
        right_feed=right_feed,
        left_rows=len(left),
        right_rows=len(right),
        matched_rows=len(matched),
        missing_left_rows=len(right_only),
        missing_right_rows=len(left_only),
        matched_coverage_pct=(len(matched) / max_rows) * 100,
        max_abs_close_diff=float(close_diff.max()) if not close_diff.empty else 0.0,
        mean_abs_close_diff=float(close_diff.mean()) if not close_diff.empty else 0.0,
        max_abs_close_diff_bps=float(close_diff_bps.max()) if not close_diff_bps.empty else 0.0,
        mean_abs_close_diff_bps=float(close_diff_bps.mean()) if not close_diff_bps.empty else 0.0,
        max_abs_volume_diff=float(volume_diff.max()) if not volume_diff.empty else 0.0,
        max_volume_diff_ratio=float(volume_diff_ratio.max())
        if not volume_diff_ratio.empty
        else 0.0,
        first_matched_timestamp=(
            matched["timestamp"].min().isoformat() if not matched.empty else None
        ),
        last_matched_timestamp=matched["timestamp"].max().isoformat()
        if not matched.empty
        else None,
        sample_missing_left_timestamps=_timestamp_sample(right_only),
        sample_missing_right_timestamps=_timestamp_sample(left_only),
        left_manifest_path=str(left_manifest) if left_manifest and left_manifest.exists() else None,
        right_manifest_path=str(right_manifest)
        if right_manifest and right_manifest.exists()
        else None,
        caveats=_comparison_caveats(left_source, right_source, left_feed, right_feed),
        report_json_path="",
        report_markdown_path="",
    )
    json_path = (
        root
        / "reports"
        / "data"
        / "comparisons"
        / f"{symbol.lower()}_{timeframe}_{left_source}_vs_{right_source}.json"
    )
    md_path = json_path.with_suffix(".md")
    report = replace(
        report,
        report_json_path=str(json_path),
        report_markdown_path=str(md_path),
    )
    ensure_dir(json_path.parent)
    write_json(json_path, _report_payload(report))
    md_path.write_text(_report_markdown(report), encoding="utf-8")
    return report


def _load_source_frame(
    root: Path,
    symbol: str,
    timeframe: str,
    source: str,
    feed: str | None,
) -> pd.DataFrame:
    source = source.lower()
    if source == "sample":
        path = root / "data" / "sample" / f"{symbol.lower()}_{timeframe}.csv"
        if not path.exists():
            raise FileNotFoundError(f"comparison sample missing: {path}")
        return normalize_ohlcv(pd.read_csv(path))
    if source == "alpaca":
        selected_feed = feed or data_feed()
        cache_path = root / "data" / "cache" / f"{symbol.lower()}_{timeframe}_{selected_feed}.csv"
        if cache_path.exists():
            return fetch_alpaca_bars(
                root=root,
                symbol=symbol,
                timeframe=timeframe,
                start=None,
                end=None,
                feed=selected_feed,
                use_cache=True,
            )
        fixture = _fixture_path(root, source, symbol, timeframe)
        if fixture.exists():
            frame = normalize_ohlcv(pd.read_csv(fixture))
            write_ohlcv_manifest(
                root,
                provider="alpaca",
                feed=selected_feed,
                symbol=symbol,
                timeframe=timeframe,
                cache_path=fixture,
                frame=frame,
                source_mode="fixture",
                caveats=["Fixture replay; refresh against live Alpaca before research use."],
            )
            return frame
        return fetch_alpaca_bars(
            root=root,
            symbol=symbol,
            timeframe=timeframe,
            start=None,
            end=None,
            feed=selected_feed,
            use_cache=True,
        )
    if source == "longbridge":
        selected_feed = feed or "nasdaq_basic"
        cache_path = longbridge_cache_path(root, symbol, timeframe, selected_feed)
        if cache_path.exists():
            return fetch_longbridge_bars(
                root=root,
                symbol=symbol,
                timeframe=timeframe,
                start=None,
                end=None,
                feed=selected_feed,
                use_cache=True,
            )
        fixture = _fixture_path(root, source, symbol, timeframe)
        if fixture.exists():
            frame = normalize_ohlcv(pd.read_csv(fixture))
            write_ohlcv_manifest(
                root,
                provider="longbridge",
                feed=selected_feed,
                symbol=symbol,
                timeframe=timeframe,
                cache_path=fixture,
                frame=frame,
                source_mode="fixture",
                caveats=["Fixture replay; refresh against live Longbridge before research use."],
            )
            return frame
        return fetch_longbridge_bars(
            root=root,
            symbol=symbol,
            timeframe=timeframe,
            start=None,
            end=None,
            feed=selected_feed,
            use_cache=True,
        )
    cache_path = root / "data" / "cache" / f"{symbol.lower()}_{timeframe}_{source}.csv"
    if not cache_path.exists():
        raise FileNotFoundError(f"comparison source cache missing: {cache_path}")
    return normalize_ohlcv(pd.read_csv(cache_path))


def _report_payload(report: OhlcvComparison) -> dict[str, object]:
    return {
        "symbol": report.symbol,
        "timeframe": report.timeframe,
        "left_source": report.left_source,
        "right_source": report.right_source,
        "left_feed": report.left_feed,
        "right_feed": report.right_feed,
        "left_rows": report.left_rows,
        "right_rows": report.right_rows,
        "matched_rows": report.matched_rows,
        "missing_left_rows": report.missing_left_rows,
        "missing_right_rows": report.missing_right_rows,
        "matched_coverage_pct": report.matched_coverage_pct,
        "max_abs_close_diff": report.max_abs_close_diff,
        "mean_abs_close_diff": report.mean_abs_close_diff,
        "max_abs_close_diff_bps": report.max_abs_close_diff_bps,
        "mean_abs_close_diff_bps": report.mean_abs_close_diff_bps,
        "max_abs_volume_diff": report.max_abs_volume_diff,
        "max_volume_diff_ratio": report.max_volume_diff_ratio,
        "first_matched_timestamp": report.first_matched_timestamp,
        "last_matched_timestamp": report.last_matched_timestamp,
        "sample_missing_left_timestamps": report.sample_missing_left_timestamps,
        "sample_missing_right_timestamps": report.sample_missing_right_timestamps,
        "left_manifest_path": report.left_manifest_path,
        "right_manifest_path": report.right_manifest_path,
        "caveats": report.caveats,
        "report_json_path": report.report_json_path,
        "report_markdown_path": report.report_markdown_path,
    }


def _report_markdown(report: OhlcvComparison) -> str:
    return "\n".join(
        [
            f"# OHLCV Comparison: {report.symbol} {report.timeframe}",
            "",
            f"- Left source: `{report.left_source}`",
            f"- Right source: `{report.right_source}`",
            f"- Left feed: `{report.left_feed or 'n/a'}`",
            f"- Right feed: `{report.right_feed or 'n/a'}`",
            f"- Left rows: `{report.left_rows}`",
            f"- Right rows: `{report.right_rows}`",
            f"- Matched rows: `{report.matched_rows}`",
            f"- Missing left rows: `{report.missing_left_rows}`",
            f"- Missing right rows: `{report.missing_right_rows}`",
            f"- Matched coverage: `{report.matched_coverage_pct:.2f}%`",
            f"- Max abs close diff: `{report.max_abs_close_diff:.6f}`",
            f"- Mean abs close diff: `{report.mean_abs_close_diff:.6f}`",
            f"- Max abs close diff bps: `{report.max_abs_close_diff_bps:.2f}`",
            f"- Mean abs close diff bps: `{report.mean_abs_close_diff_bps:.2f}`",
            f"- Max abs volume diff: `{report.max_abs_volume_diff:.6f}`",
            f"- Max volume diff ratio: `{report.max_volume_diff_ratio:.4f}`",
            f"- First matched timestamp: `{report.first_matched_timestamp or 'n/a'}`",
            f"- Last matched timestamp: `{report.last_matched_timestamp or 'n/a'}`",
            f"- Left manifest: `{report.left_manifest_path or 'n/a'}`",
            f"- Right manifest: `{report.right_manifest_path or 'n/a'}`",
            f"- JSON report: `{report.report_json_path}`",
            "",
            "## Missing Timestamp Samples",
            "",
            "- Missing left: "
            + (
                ", ".join(f"`{item}`" for item in report.sample_missing_left_timestamps) or "`none`"
            ),
            "- Missing right: "
            + (
                ", ".join(f"`{item}`" for item in report.sample_missing_right_timestamps)
                or "`none`"
            ),
            "",
            "## Caveats",
            "",
            *[f"- {item}" for item in report.caveats],
        ]
    )


def _timestamp_sample(frame: pd.DataFrame, limit: int = 5) -> list[str]:
    if frame.empty:
        return []
    return [item.isoformat() for item in frame["timestamp"].head(limit)]


def _fixture_path(root: Path, source: str, symbol: str, timeframe: str) -> Path:
    return (
        root
        / "data"
        / "fixtures"
        / "capabilities"
        / f"{source.lower()}_{symbol.lower()}_{timeframe}.csv"
    )


def _manifest_path(
    root: Path,
    symbol: str,
    timeframe: str,
    source: str,
    feed: str | None,
) -> Path | None:
    source = source.lower()
    if source == "alpaca":
        return cache_manifest_path(root, symbol, timeframe, "alpaca", feed or data_feed())
    if source == "longbridge":
        return cache_manifest_path(root, symbol, timeframe, "longbridge", feed or "nasdaq_basic")
    if source == "sample":
        return None
    return cache_manifest_path(root, symbol, timeframe, source, feed)


def _comparison_caveats(
    left_source: str,
    right_source: str,
    left_feed: str | None,
    right_feed: str | None,
) -> list[str]:
    caveats = [
        "OHLCV source comparison is a research data quality check, not execution parity proof.",
        (
            "Timestamp alignment, adjustment policy, extended-hours coverage, and feed "
            "permissions must be reviewed before trusting backtest deltas."
        ),
    ]
    sources = {left_source.lower(), right_source.lower()}
    feeds = {str(left_feed or "").lower(), str(right_feed or "").lower()}
    if "alpaca" in sources and ("iex" in feeds or not left_feed or not right_feed):
        caveats.append("Alpaca IEX is not consolidated SIP market data.")
    if "longbridge" in sources:
        caveats.append("Longbridge free US market data is Nasdaq Basic, not consolidated SIP.")
    return caveats
