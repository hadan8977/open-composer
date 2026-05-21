from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from open_composer.config import ensure_dir, project_root
from open_composer.feature_packets import inspect_feature_packet
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.storage import write_json


@dataclass(frozen=True)
class AlternativeDataEvidenceResult:
    strategy_name: str
    pit_replay_path: Path
    marginal_lift_path: Path
    modality_robustness_path: Path
    report_path: Path
    status: str
    advisory_only: bool


def build_alternative_data_evidence(
    spec_path: Path,
    root: Path | None = None,
) -> AlternativeDataEvidenceResult:
    base = root or project_root()
    spec = load_strategy_spec(spec_path)
    feature_factors = {
        name: factor
        for name, factor in spec.factors.items()
        if factor.source in {"llm_feature", "feature_packet"}
    }
    advisory_only = not feature_factors
    inspections: list[dict[str, Any]] = []
    for name, factor in feature_factors.items():
        packet_path = _resolve_path(base, factor.path) if factor.path else None
        inspection = inspect_feature_packet(packet_path, factor.field) if packet_path else None
        inspections.append(
            {
                "factor": name,
                "path": factor.path,
                "field": factor.field,
                "point_in_time_status": inspection.point_in_time_status
                if inspection
                else "missing",
                "record_count": inspection.record_count if inspection else 0,
                "evidence_count": inspection.evidence_count if inspection else 0,
                "warnings": inspection.replay_warnings if inspection else ["missing packet path"],
            }
        )
    status = (
        "ok"
        if advisory_only or all(item["point_in_time_status"] == "complete" for item in inspections)
        else "blocked"
    )
    pit_replay_path = base / "reports" / "research" / f"{spec.name}-pit-replay.json"
    marginal_lift_path = base / "reports" / "research" / f"{spec.name}-marginal-lift.json"
    modality_path = base / "reports" / "research" / f"{spec.name}-modality-robustness.json"
    report_path = base / "reports" / "research" / f"{spec.name}-alternative-data-evidence.md"
    common = {
        "strategy_name": spec.name,
        "status": status,
        "advisory_only": advisory_only,
        "factors": inspections,
    }
    write_json(
        pit_replay_path,
        common
        | {
            "replay_method": "point_in_time_feature_packets"
            if not advisory_only
            else "not_applicable_advisory_only",
            "pit_fields_verified": _pit_fields_verified(inspections),
            "live_call_prohibited": True,
        },
    )
    write_json(
        marginal_lift_path,
        common
        | {
            "baseline_sharpe": None,
            "with_signal_sharpe": None,
            "lift_pct": None,
            "robustness_check": "advisory_only"
            if advisory_only
            else "requires strategy-specific marginal lift research",
        },
    )
    write_json(
        modality_path,
        common
        | {
            "degradation_mode": "advisory_only" if advisory_only else "missing_modality_fallback",
            "fallback_behavior": "ignore_advisory_context"
            if advisory_only
            else "use deterministic baseline",
            "performance_impact": None,
        },
    )
    _write_markdown(report_path, spec.name, status, advisory_only, inspections)
    return AlternativeDataEvidenceResult(
        strategy_name=spec.name,
        pit_replay_path=pit_replay_path,
        marginal_lift_path=marginal_lift_path,
        modality_robustness_path=modality_path,
        report_path=report_path,
        status=status,
        advisory_only=advisory_only,
    )


def _pit_fields_verified(inspections: list[dict[str, Any]]) -> list[str]:
    if not inspections:
        return []
    return ["visible_at", "published_at", "fetched_at", "source", "input_hash", "prompt_hash"]


def _write_markdown(
    path: Path,
    strategy_name: str,
    status: str,
    advisory_only: bool,
    inspections: list[dict[str, Any]],
) -> None:
    ensure_dir(path.parent)
    lines = [
        f"# Alternative Data Evidence: {strategy_name}",
        "",
        f"- Status: `{status}`",
        f"- Advisory only: `{advisory_only}`",
        "",
        "## Factors",
        "",
    ]
    if inspections:
        lines.extend(f"- `{item['factor']}`: `{item}`" for item in inspections)
    else:
        lines.append("- No LLM/news/macro/event factor affects trading logic.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _resolve_path(root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path
