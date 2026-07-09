from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from open_composer.adapters.data import fetch_ohlcv
from open_composer.adapters.data.sample import normalize_ohlcv
from open_composer.config import ensure_dir, project_root
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.research.hybrid_router_core import (
    _effective_lookback,
    hybrid_params_from_label,
    hybrid_target_weight_snapshot,
)
from open_composer.research.pdr_attribution import (
    DEFAULT_END,
    DEFAULT_SPEC_PATH,
    DEFAULT_START,
    attribute_window,
    simulate_daily_rows,
)
from open_composer.research.research_cache_manifest import (
    DEFAULT_RESEARCH_CACHE_DIR,
    price_csv_stats,
    sha256_file,
    verify_longbridge_research_cache_manifest,
)
from open_composer.research.router_common import (
    RouterFrameDataset,
    backtest_router_params,
    load_daily_dataset,
)
from open_composer.storage import write_json

DEFAULT_ALT_SOURCE = "alpaca"
DEFAULT_ALT_FEED = "iex"
DEFAULT_ALT_DIR = Path("data/research/alpaca_daily")
DEFAULT_OUT_DIR = Path("reports/research/control")
DEFAULT_REPORT_DATE = "20260709"

CRISIS_WINDOWS: tuple[dict[str, str], ...] = (
    {"name": "q4_2018", "start": "2018-10-01", "end": "2018-12-31"},
    {"name": "covid_crash", "start": "2020-02-19", "end": "2020-03-23"},
    {"name": "calendar_2022", "start": "2022-01-03", "end": "2022-12-30"},
)


def materialize_alt_daily_source(
    *,
    root: Path | None = None,
    source: str = DEFAULT_ALT_SOURCE,
    feed: str | None = DEFAULT_ALT_FEED,
    symbols: list[str] | None = None,
    start: str = DEFAULT_START,
    end: str = DEFAULT_END,
    output_dir: Path | None = None,
    refresh_data: bool = False,
) -> dict[str, Any]:
    """Copy a non-primary daily source into an isolated research directory."""
    if source != "alpaca":
        raise ValueError("fetch-alt-daily currently supports --source alpaca only")
    base = root or project_root()
    out_dir = _resolve(base, output_dir or Path(f"data/research/{source}_daily"))
    ensure_dir(out_dir)
    selected_symbols = symbols or _symbols_from_primary_manifest(base)
    rows: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for symbol in selected_symbols:
        path = out_dir / f"{symbol.lower()}_daily_{source}.csv"
        try:
            frame = fetch_ohlcv(
                root=base,
                symbol=symbol,
                timeframe="daily",
                start=_parse_dt(start),
                end=_parse_dt(end),
                source=source,
                feed=feed,
                use_cache=not refresh_data,
                allow_fallback=False,
            )
        except Exception as exc:  # noqa: BLE001 - written into manifest as fetch evidence.
            errors.append({"symbol": symbol, "error": str(exc)})
            continue
        source_mode = str(frame.attrs.get("data_source_mode") or "unknown")
        if "fallback" in source_mode:
            errors.append(
                {
                    "symbol": symbol,
                    "error": f"refusing fallback source_mode={source_mode}",
                }
            )
            continue
        ensure_dir(path.parent)
        normalize_ohlcv(frame).to_csv(path, index=False)
        stats = price_csv_stats(path)
        rows.append(
            {
                "symbol": symbol,
                "path": str(path),
                "records": stats["records"],
                "first_timestamp": stats["first_timestamp"],
                "last_timestamp": stats["last_timestamp"],
                "sha256": sha256_file(path),
                "source_mode": source_mode,
                "source_path": frame.attrs.get("data_source_path"),
            }
        )
    manifest = {
        "report_type": "alt_daily_source_manifest",
        "provider": source,
        "feed": feed,
        "adjusted": False,
        "generated_at": datetime.now(UTC).isoformat(),
        "requested_start": start,
        "requested_end": end,
        "output_dir": str(out_dir),
        "symbols": rows,
        "errors": errors,
        "coverage_required_windows": list(CRISIS_WINDOWS),
        "comparison_discipline": (
            "This alternate source is materialized in a separate directory and must never "
            "overwrite data/research/longbridge_adjusted_daily."
        ),
    }
    write_json(out_dir / "manifest.json", manifest)
    return manifest


def evaluate_route_cross_source_validation(
    *,
    root: Path | None = None,
    spec_path: Path = DEFAULT_SPEC_PATH,
    alt_source: str = DEFAULT_ALT_SOURCE,
    alt_feed: str | None = DEFAULT_ALT_FEED,
    alt_dir: Path | None = None,
    start: str = DEFAULT_START,
    end: str = DEFAULT_END,
    report_date: str = DEFAULT_REPORT_DATE,
    out_dir: Path = DEFAULT_OUT_DIR,
) -> dict[str, Any]:
    base = root or project_root()
    resolved_spec = _resolve(base, spec_path)
    spec = load_strategy_spec(resolved_spec)
    route_label = spec.portfolio.selected_route_label
    if not route_label:
        raise ValueError("route cross-source validation requires selected_route_label")
    params = hybrid_params_from_label(route_label)
    main_manifest = verify_longbridge_research_cache_manifest(base)
    alt_manifest_path = _resolve(base, alt_dir or DEFAULT_ALT_DIR) / "manifest.json"
    alt_manifest = _read_json(alt_manifest_path)
    if alt_manifest is None:
        return _write_report(
            base,
            out_dir,
            report_date,
            _blocked_payload(
                spec_name=spec.name,
                route_label=route_label,
                main_manifest=main_manifest,
                alt_manifest=None,
                reason=f"alternate source manifest missing: {alt_manifest_path}",
            ),
        )
    alt_errors = alt_manifest.get("errors") or []
    if alt_errors:
        return _write_report(
            base,
            out_dir,
            report_date,
            _blocked_payload(
                spec_name=spec.name,
                route_label=route_label,
                main_manifest=main_manifest,
                alt_manifest=alt_manifest,
                reason="alternate source materialization has fetch errors",
            ),
        )
    try:
        main_dataset = load_daily_dataset(
            spec=spec,
            root=base,
            symbols=[item.upper() for item in spec.universe],
            data_source="longbridge",
            feed=None,
            start=start,
            end=end,
            market_symbol="QQQ",
            benchmark_symbol="TQQQ",
        )
        alt_dataset = load_daily_dataset(
            spec=spec,
            root=base,
            symbols=[item.upper() for item in spec.universe],
            data_source=alt_source,
            feed=alt_feed,
            start=start,
            end=end,
            market_symbol="QQQ",
            benchmark_symbol="TQQQ",
            fetcher=_materialized_fetcher(
                _resolve(base, alt_dir or DEFAULT_ALT_DIR), alt_source, alt_feed
            ),
        )
    except Exception as exc:  # noqa: BLE001 - converted into a negative evidence report.
        return _write_report(
            base,
            out_dir,
            report_date,
            _blocked_payload(
                spec_name=spec.name,
                route_label=route_label,
                main_manifest=main_manifest,
                alt_manifest=alt_manifest,
                reason=f"dataset load failed: {exc}",
            ),
        )
    common_dates = sorted(set(main_dataset.dates) & set(alt_dataset.dates))
    lookback = _effective_lookback(params)
    coverage_gaps = _coverage_gaps(common_dates, lookback)
    if coverage_gaps:
        return _write_report(
            base,
            out_dir,
            report_date,
            _blocked_payload(
                spec_name=spec.name,
                route_label=route_label,
                main_manifest=main_manifest,
                alt_manifest=alt_manifest,
                reason="alternate source overlap does not cover required windows",
                extra={
                    "common_date_count": len(common_dates),
                    "common_start": common_dates[0] if common_dates else None,
                    "common_end": common_dates[-1] if common_dates else None,
                    "coverage_gaps": coverage_gaps,
                },
            ),
        )
    aligned_main = _restrict_dataset(main_dataset, common_dates)
    aligned_alt = _restrict_dataset(alt_dataset, common_dates)
    start_index = lookback
    end_index = len(common_dates) - 1
    main_rows = simulate_daily_rows(spec, aligned_main, params, start_index, end_index)
    alt_rows = simulate_daily_rows(spec, aligned_alt, params, start_index, end_index)
    main_metrics = backtest_router_params(
        spec,
        aligned_main,
        params,
        snapshot=hybrid_target_weight_snapshot,
        start_index=start_index,
        end_index=end_index,
    )
    alt_metrics = backtest_router_params(
        spec,
        aligned_alt,
        params,
        snapshot=hybrid_target_weight_snapshot,
        start_index=start_index,
        end_index=end_index,
    )
    gate = judge_route_cross_source(
        main_rows=main_rows,
        alt_rows=alt_rows,
        main_metrics=_metrics_payload(main_metrics),
        alt_metrics=_metrics_payload(alt_metrics),
    )
    payload = {
        "report_type": "route_cross_source_validation",
        "status": "pass" if gate["route_cross_source_pass"] else "fail",
        "route_cross_source_pass": gate["route_cross_source_pass"],
        "strategy_name": spec.name,
        "route_label": route_label,
        "main_source": {
            "provider": "longbridge",
            "manifest": main_manifest,
            "data_profile": main_dataset.data_profile,
        },
        "alternate_source": {
            "provider": alt_source,
            "feed": alt_feed,
            "manifest": alt_manifest,
            "data_profile": alt_dataset.data_profile,
        },
        "overlap_window": {
            "start": common_dates[0],
            "end": common_dates[-1],
            "sessions": len(common_dates),
            "evaluated_start": main_rows[0]["date"] if main_rows else None,
            "evaluated_end": main_rows[-1]["date"] if main_rows else None,
        },
        "main_metrics": _metrics_payload(main_metrics),
        "alternate_metrics": _metrics_payload(alt_metrics),
        "acceptance_gate": gate,
        "caveats": [
            "This validates one fixed route only; it does not search, tune, or promote.",
            "Alpaca IEX is not consolidated SIP data and remains cross-source evidence only.",
            (
                "A false or blocked verdict blocks live start and must not be repaired by "
                "parameter tuning."
            ),
        ],
    }
    return _write_report(base, out_dir, report_date, payload)


def judge_route_cross_source(
    *,
    main_rows: list[dict[str, Any]],
    alt_rows: list[dict[str, Any]],
    main_metrics: dict[str, Any],
    alt_metrics: dict[str, Any],
    crisis_windows: tuple[dict[str, str], ...] = CRISIS_WINDOWS,
) -> dict[str, Any]:
    main_by_date = {str(row["date"]): row for row in main_rows}
    alt_by_date = {str(row["date"]): row for row in alt_rows}
    common_dates = sorted(set(main_by_date) & set(alt_by_date))
    mismatches = [
        {
            "date": date,
            "main_state": main_by_date[date].get("state"),
            "alternate_state": alt_by_date[date].get("state"),
        }
        for date in common_dates
        if main_by_date[date].get("state") != alt_by_date[date].get("state")
    ]
    state_consistency = (
        (len(common_dates) - len(mismatches)) / len(common_dates) * 100 if common_dates else 0.0
    )
    crisis = []
    for window in crisis_windows:
        main_attr = attribute_window(
            [row for row in main_rows if window["start"] <= str(row["date"]) <= window["end"]]
        )
        alt_attr = attribute_window(
            [row for row in alt_rows if window["start"] <= str(row["date"]) <= window["end"]]
        )
        main_beats = main_attr["net_compound_pct"] > main_attr["tqqq_compound_pct"]
        alt_beats = alt_attr["net_compound_pct"] > alt_attr["tqqq_compound_pct"]
        crisis.append(
            {
                "name": window["name"],
                "start": window["start"],
                "end": window["end"],
                "main_net_compound_pct": main_attr["net_compound_pct"],
                "main_tqqq_compound_pct": main_attr["tqqq_compound_pct"],
                "alternate_net_compound_pct": alt_attr["net_compound_pct"],
                "alternate_tqqq_compound_pct": alt_attr["tqqq_compound_pct"],
                "main_route_beats_tqqq": main_beats,
                "alternate_route_beats_tqqq": alt_beats,
                "conclusion_flipped": main_beats != alt_beats,
                "passed": main_beats and alt_beats and main_beats == alt_beats,
            }
        )
    annualized_diff = abs(
        float(main_metrics.get("annualized_return_pct") or 0.0)
        - float(alt_metrics.get("annualized_return_pct") or 0.0)
    )
    maxdd_diff = abs(
        float(main_metrics.get("max_drawdown_pct") or 0.0)
        - float(alt_metrics.get("max_drawdown_pct") or 0.0)
    )
    gates = {
        "crisis_conclusions_do_not_flip": {
            "passed": all(item["passed"] for item in crisis),
            "windows": crisis,
        },
        "annualized_return_diff_lte_5pp": {
            "passed": annualized_diff <= 5.0,
            "actual_pp": round(annualized_diff, 4),
            "threshold_pp": 5.0,
        },
        "max_drawdown_diff_lte_5pp": {
            "passed": maxdd_diff <= 5.0,
            "actual_pp": round(maxdd_diff, 4),
            "threshold_pp": 5.0,
        },
        "state_sequence_consistency_gte_95pct": {
            "passed": state_consistency >= 95.0,
            "actual_pct": round(state_consistency, 4),
            "threshold_pct": 95.0,
            "compared_sessions": len(common_dates),
            "mismatch_count": len(mismatches),
            "mismatches": mismatches,
        },
    }
    return {
        "objective": "route_cross_source_pass",
        "route_cross_source_pass": all(item["passed"] for item in gates.values()),
        "gates": gates,
    }


def _blocked_payload(
    *,
    spec_name: str,
    route_label: str,
    main_manifest: dict[str, Any],
    alt_manifest: dict[str, Any] | None,
    reason: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "report_type": "route_cross_source_validation",
        "status": "blocked",
        "route_cross_source_pass": False,
        "strategy_name": spec_name,
        "route_label": route_label,
        "main_source": {"provider": "longbridge", "manifest": main_manifest},
        "alternate_source": {"manifest": alt_manifest},
        "blocker": reason,
        "acceptance_gate": {
            "objective": "route_cross_source_pass",
            "route_cross_source_pass": False,
            "gates": {},
        },
        "caveats": [
            "Blocked is a valid negative evidence state; do not shorten the window to claim pass.",
            "Live start remains blocked until a full cross-source validation passes.",
        ],
    }
    if extra:
        payload.update(extra)
    return payload


def _write_report(
    root: Path,
    out_dir: Path,
    report_date: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    resolved = ensure_dir(_resolve(root, out_dir))
    stem = resolved / f"route-cross-source-validation-{report_date}"
    json_path = stem.with_suffix(".json")
    md_path = stem.with_suffix(".md")
    payload["artifact_paths"] = {"json": str(json_path), "markdown": str(md_path)}
    write_json(json_path, payload)
    md_path.write_text(render_route_cross_source_markdown(payload), encoding="utf-8")
    return payload


def render_route_cross_source_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Route Cross-Source Validation",
        "",
        f"- Strategy: `{payload.get('strategy_name')}`",
        f"- Status: `{payload.get('status')}`",
        f"- route_cross_source_pass: `{payload.get('route_cross_source_pass')}`",
        f"- Route: `{payload.get('route_label')}`",
        "",
    ]
    if payload.get("status") == "blocked":
        lines.extend(
            [
                "## Blocker",
                "",
                f"- {payload.get('blocker')}",
                "",
            ]
        )
        if payload.get("coverage_gaps"):
            lines.extend(
                [
                    "## Coverage Gaps",
                    "",
                    "| window | start | end | reason |",
                    "| --- | --- | --- | --- |",
                ]
            )
            for gap in payload["coverage_gaps"]:
                lines.append(f"| {gap['name']} | {gap['start']} | {gap['end']} | {gap['reason']} |")
            lines.append("")
        return "\n".join(lines)
    overlap = payload.get("overlap_window", {})
    lines.extend(
        [
            "## Overlap",
            "",
            f"- Sessions: `{overlap.get('sessions')}`",
            f"- Window: `{overlap.get('start')}` -> `{overlap.get('end')}`",
            f"- Evaluated: `{overlap.get('evaluated_start')}` -> `{overlap.get('evaluated_end')}`",
            "",
            "## Full Window Metrics",
            "",
            "| source | total % | annualized % | sharpe | max DD % |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for label, key in (("main", "main_metrics"), ("alternate", "alternate_metrics")):
        metrics = payload.get(key, {})
        lines.append(
            f"| {label} | {_fmt(metrics.get('total_return_pct'))} | "
            f"{_fmt(metrics.get('annualized_return_pct'))} | "
            f"{_fmt(metrics.get('sharpe_ratio'))} | {_fmt(metrics.get('max_drawdown_pct'))} |"
        )
    lines.extend(
        [
            "",
            "## Acceptance Gates",
            "",
            "| gate | passed | actual | threshold |",
            "| --- | --- | --- | --- |",
        ]
    )
    gates = payload.get("acceptance_gate", {}).get("gates", {})
    for name, item in gates.items():
        actual = item.get("actual_pp", item.get("actual_pct", "see details"))
        threshold = item.get("threshold_pp", item.get("threshold_pct", "all crisis windows"))
        lines.append(f"| {name} | {item.get('passed')} | {actual} | {threshold} |")
    crisis = gates.get("crisis_conclusions_do_not_flip", {}).get("windows", [])
    if crisis:
        lines.extend(
            [
                "",
                "## Crisis Windows",
                "",
                "| window | main net % | main TQQQ % | alt net % | alt TQQQ % | passed |",
                "| --- | --- | --- | --- | --- | --- |",
            ]
        )
        for item in crisis:
            lines.append(
                f"| {item['name']} | {item['main_net_compound_pct']} | "
                f"{item['main_tqqq_compound_pct']} | {item['alternate_net_compound_pct']} | "
                f"{item['alternate_tqqq_compound_pct']} | {item['passed']} |"
            )
    mismatches = gates.get("state_sequence_consistency_gte_95pct", {}).get("mismatches", [])
    lines.extend(
        [
            "",
            "## State Mismatches",
            "",
            f"- Count: `{len(mismatches)}`",
        ]
    )
    for item in mismatches[:50]:
        lines.append(
            f"- `{item['date']}`: main `{item['main_state']}` vs alternate "
            f"`{item['alternate_state']}`"
        )
    if len(mismatches) > 50:
        lines.append(f"- ... {len(mismatches) - 50} additional mismatches in JSON")
    lines.append("")
    return "\n".join(lines)


def _symbols_from_primary_manifest(root: Path) -> list[str]:
    manifest_path = root / DEFAULT_RESEARCH_CACHE_DIR / "manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    return [str(row["symbol"]).upper() for row in payload.get("symbols", [])]


def _materialized_fetcher(output_dir: Path, source: str, feed: str | None):
    def fetcher(
        *,
        root: Path,
        symbol: str,
        timeframe: str,
        start: datetime | None,
        end: datetime | None,
        source: str,
        feed: str | None,
        use_cache: bool,
        allow_fallback: bool,
    ) -> pd.DataFrame:
        del root, use_cache, allow_fallback
        if timeframe != "daily":
            raise ValueError("materialized alternate fetcher supports daily only")
        path = output_dir / f"{symbol.lower()}_daily_{source}.csv"
        if not path.exists():
            raise FileNotFoundError(f"alternate daily file missing: {path}")
        frame = normalize_ohlcv(pd.read_csv(path))
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
        if start is not None:
            frame = frame[frame["timestamp"] >= pd.Timestamp(start)]
        if end is not None:
            frame = frame[frame["timestamp"] <= pd.Timestamp(end)]
        frame = frame.reset_index(drop=True)
        frame.attrs.update(
            {
                "data_source_provider": source,
                "data_source_mode": "materialized_alt_daily",
                "data_source_feed": feed,
                "data_source_path": str(path),
            }
        )
        return frame

    return fetcher


def _coverage_gaps(common_dates: list[str], lookback: int) -> list[dict[str, str]]:
    if len(common_dates) <= lookback + 1:
        return [
            {
                "name": "minimum_sessions",
                "start": "",
                "end": "",
                "reason": f"common sessions {len(common_dates)} <= lookback {lookback}",
            }
        ]
    evaluated_dates = common_dates[lookback:-1]
    gaps = []
    for window in CRISIS_WINDOWS:
        rows = [date for date in evaluated_dates if window["start"] <= date <= window["end"]]
        if not rows:
            gaps.append(
                {
                    "name": window["name"],
                    "start": window["start"],
                    "end": window["end"],
                    "reason": "no evaluated sessions in required crisis window",
                }
            )
    return gaps


def _restrict_dataset(dataset: RouterFrameDataset, dates: list[str]) -> RouterFrameDataset:
    selected = dataset.frame[dataset.frame["date"].isin(dates)].copy()
    selected["date"] = selected["date"].astype(str)
    selected = selected.sort_values("date").reset_index(drop=True)
    ordered_dates = [str(item) for item in selected["date"]]
    return RouterFrameDataset(
        symbols=dataset.symbols,
        market_symbol=dataset.market_symbol,
        benchmark_symbol=dataset.benchmark_symbol,
        dates=ordered_dates,
        frame=selected,
        data_profile=dataset.data_profile,
        pit_membership=dataset.pit_membership,
    )


def _metrics_payload(metrics: Any) -> dict[str, Any]:
    payload = asdict(metrics)
    for key, value in list(payload.items()):
        if isinstance(value, float):
            payload[key] = round(value, 6)
    return payload


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    return timestamp.to_pydatetime()


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve(root: Path, path: Path) -> Path:
    return path if path.is_absolute() else root / path


def _fmt(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, int | float):
        return f"{float(value):.2f}"
    return str(value)
