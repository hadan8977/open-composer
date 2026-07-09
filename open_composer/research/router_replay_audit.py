from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from open_composer.config import ensure_dir, project_root
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.research.hybrid_router_core import (
    _effective_lookback,
    hybrid_params_from_label,
)
from open_composer.research.pdr_attribution import (
    DEFAULT_END,
    DEFAULT_FOLDS,
    DEFAULT_SPEC_PATH,
    DEFAULT_START,
    attribute_window,
    simulate_daily_rows,
)
from open_composer.research.research_cache_manifest import (
    verify_longbridge_research_cache_manifest,
)
from open_composer.research.router_common import load_daily_dataset
from open_composer.storage import write_json

DEFAULT_BASELINE = Path("reports/research/control/pdr-router-fold-attribution-20260703.json")
DEFAULT_OUT_DIR = Path("reports/research/control")
DEFAULT_AUDIT_DATE = "20260709"


def run_router_replay_audit(
    *,
    root: Path | None = None,
    spec_path: Path = DEFAULT_SPEC_PATH,
    baseline_path: Path = DEFAULT_BASELINE,
    report_date: str = DEFAULT_AUDIT_DATE,
    out_dir: Path = DEFAULT_OUT_DIR,
    start: str = DEFAULT_START,
    end: str = DEFAULT_END,
) -> dict[str, Any]:
    base = root or project_root()
    manifest = verify_longbridge_research_cache_manifest(base)
    baseline = json.loads(_resolve(base, baseline_path).read_text(encoding="utf-8"))
    spec = load_strategy_spec(_resolve(base, spec_path))
    route_label = spec.portfolio.selected_route_label
    if not route_label:
        raise ValueError("router replay audit requires selected_route_label")
    params = hybrid_params_from_label(route_label)
    dataset = load_daily_dataset(
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
    lookback = _effective_lookback(params)
    rows = simulate_daily_rows(spec, dataset, params, lookback, len(dataset.dates) - 1)
    current = {
        "full_window_attribution": attribute_window(rows),
        "folds": _fold_attribution(rows, baseline.get("folds", [])),
    }
    comparison = compare_replay_to_baseline(current=current, baseline=baseline)
    payload = {
        "report_type": "router_replay_audit",
        "generated_at": datetime.now(UTC).isoformat(),
        "status": "ok" if comparison["passed"] else "drift",
        "strategy_name": spec.name,
        "route_label": route_label,
        "manifest": manifest,
        "baseline_path": str(_resolve(base, baseline_path)),
        "comparison": comparison,
        "caveats": [
            "Replay audit compares the fixed route on the same materialized research cache.",
            "If drift appears, inspect manifest hashes before comparing strategy numbers.",
        ],
    }
    return _write_report(base, out_dir, report_date, payload)


def compare_replay_to_baseline(
    *,
    current: dict[str, Any],
    baseline: dict[str, Any],
) -> dict[str, Any]:
    full_checks = _compare_attr(
        current.get("full_window_attribution", {}),
        baseline.get("full_window_attribution", {}),
        "full_window",
    )
    baseline_folds = {str(row["fold"]): row["attribution"] for row in baseline.get("folds", [])}
    current_folds = current.get("folds", {})
    fold_checks = [
        _compare_attr(current_folds.get(name, {}), expected, name)
        for name, expected in sorted(baseline_folds.items())
    ]
    checks = [full_checks, *fold_checks]
    return {
        "passed": all(item["passed"] for item in checks),
        "checks": checks,
    }


def render_router_replay_audit_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Router Replay Audit",
        "",
        f"- Status: `{payload['status']}`",
        f"- Strategy: `{payload['strategy_name']}`",
        f"- Baseline: `{payload['baseline_path']}`",
        f"- Manifest passed: `{payload['manifest']['passed']}`",
        "",
        "| window | passed | net compound diff | TQQQ diff | transition diff |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in payload["comparison"]["checks"]:
        lines.append(
            f"| {item['window']} | {item['passed']} | "
            f"{item['net_compound_diff']} | {item['tqqq_compound_diff']} | "
            f"{item['state_transition_diff']} |"
        )
    lines.append("")
    return "\n".join(lines)


def _fold_attribution(
    rows: list[dict[str, Any]],
    baseline_folds: list[dict[str, Any]],
) -> dict[str, Any]:
    if baseline_folds:
        return {
            str(fold["fold"]): attribute_window(
                [
                    row
                    for row in rows
                    if str(fold["start_date"]) <= row["date"] <= str(fold["end_date"])
                ]
            )
            for fold in baseline_folds
        }
    return {
        name: attribute_window([row for row in rows if start <= row["date"] <= end])
        for name, start, end in DEFAULT_FOLDS
    }


def _compare_attr(current: dict[str, Any], expected: dict[str, Any], window: str) -> dict[str, Any]:
    net_diff = round(
        float(current.get("net_compound_pct", 0.0)) - float(expected.get("net_compound_pct", 0.0)),
        6,
    )
    tqqq_diff = round(
        float(current.get("tqqq_compound_pct", 0.0))
        - float(expected.get("tqqq_compound_pct", 0.0)),
        6,
    )
    transition_diff = int(current.get("state_transitions", 0)) - int(
        expected.get("state_transitions", 0)
    )
    return {
        "window": window,
        "passed": abs(net_diff) <= 1e-9 and abs(tqqq_diff) <= 1e-9 and transition_diff == 0,
        "net_compound_diff": net_diff,
        "tqqq_compound_diff": tqqq_diff,
        "state_transition_diff": transition_diff,
    }


def _write_report(
    root: Path,
    out_dir: Path,
    report_date: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    resolved = ensure_dir(_resolve(root, out_dir))
    stem = resolved / f"router-replay-audit-{report_date}"
    json_path = stem.with_suffix(".json")
    md_path = stem.with_suffix(".md")
    payload["artifact_paths"] = {"json": str(json_path), "markdown": str(md_path)}
    write_json(json_path, payload)
    md_path.write_text(render_router_replay_audit_markdown(payload), encoding="utf-8")
    return payload


def _resolve(root: Path, path: Path) -> Path:
    return path if path.is_absolute() else root / path
