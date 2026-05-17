from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from open_composer.config import ensure_dir, project_root
from open_composer.feature_packets import inspect_feature_packet
from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec
from open_composer.storage import write_json


@dataclass(frozen=True)
class AlternativeDataQualityResult:
    strategy_name: str
    status: str
    report_path: Path
    json_path: Path
    rows: list[dict[str, Any]]
    warnings: list[str]


def build_alternative_data_quality_report(
    spec_path: Path,
    root: Path | None = None,
) -> AlternativeDataQualityResult:
    base = root or project_root()
    spec = load_strategy_spec(spec_path)
    rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    for name, factor in spec.factors.items():
        if factor.source not in {"llm_feature", "feature_packet"}:
            continue
        if not factor.path:
            row = {"factor": name, "source": factor.source, "status": "missing_path"}
            rows.append(row)
            warnings.append(f"{name}:missing_path")
            continue
        path = _resolve_path(base, factor.path)
        inspection = inspect_feature_packet(path, factor.field)
        row = {
            "factor": name,
            "source": factor.source,
            "path": factor.path,
            "field": factor.field,
            "exists": inspection.exists,
            "record_count": inspection.record_count,
            "point_in_time_status": inspection.point_in_time_status,
            "evidence_count": inspection.evidence_count,
            "missing_evidence_count": inspection.missing_evidence_count,
            "sources": inspection.sources,
            "models": inspection.models,
            "input_hashes": inspection.input_hashes,
            "prompt_hashes": inspection.prompt_hashes,
            "warnings": inspection.replay_warnings,
        }
        rows.append(row)
        if inspection.point_in_time_status != "complete":
            warnings.append(f"{name}:pit_{inspection.point_in_time_status}")
        if inspection.missing_evidence_count:
            warnings.append(f"{name}:missing_evidence")
    status = "ok"
    if warnings:
        status = "blocked" if any("pit_" in warning for warning in warnings) else "warning"
    report_path = base / "reports" / "research" / f"{spec.name}-alt-data-quality.md"
    json_path = base / "reports" / "research" / f"{spec.name}-alt-data-quality.json"
    _write_json(json_path, spec, status, rows, warnings)
    _write_markdown(report_path, spec, status, rows, warnings, json_path)
    return AlternativeDataQualityResult(
        strategy_name=spec.name,
        status=status,
        report_path=report_path,
        json_path=json_path,
        rows=rows,
        warnings=warnings,
    )


def _write_json(
    path: Path,
    spec: StrategySpec,
    status: str,
    rows: list[dict[str, Any]],
    warnings: list[str],
) -> Path:
    return write_json(
        path,
        {
            "strategy_name": spec.name,
            "status": status,
            "warnings": warnings,
            "factors": rows,
        },
    )


def _write_markdown(
    path: Path,
    spec: StrategySpec,
    status: str,
    rows: list[dict[str, Any]],
    warnings: list[str],
    json_path: Path,
) -> Path:
    ensure_dir(path.parent)
    lines = [
        f"# Alternative Data Quality: {spec.name}",
        "",
        f"- Status: `{status}`",
        f"- JSON: `{json_path}`",
        "",
        "## Warnings",
        "",
    ]
    lines.extend(f"- `{warning}`" for warning in warnings) if warnings else lines.append("- none")
    lines.extend(["", "## Factors", ""])
    if not rows:
        lines.append("- No LLM or feature packet factors.")
    else:
        for row in rows:
            lines.append(f"- `{row.get('factor')}`: `{row}`")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _resolve_path(root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def alt_data_quality_payload(result: AlternativeDataQualityResult) -> dict[str, Any]:
    return asdict(result) | {
        "report_path": str(result.report_path),
        "json_path": str(result.json_path),
    }
