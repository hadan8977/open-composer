from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from open_composer.config import ensure_dir, project_root
from open_composer.models.options import OptionsOverlaySpec, OptionsSpec
from open_composer.storage import write_json


@dataclass(frozen=True)
class OptionsResearchResult:
    name: str
    report_path: Path
    json_path: Path
    execution_substate: str
    paper_ready_pass: bool


def build_options_overlay_report(
    overlay_path: Path,
    root: Path | None = None,
) -> OptionsResearchResult:
    base = root or project_root()
    raw = _load_yaml_mapping(overlay_path)
    overlay = OptionsOverlaySpec.model_validate(raw)
    return _write_options_report(
        base=base,
        name=overlay.name,
        spec_path=overlay_path,
        instrument_type="options_overlay",
        payload=overlay.model_dump(mode="json"),
        required_artifacts=[
            "options_chain_source_cards",
            "greeks_profile",
            "roll_schedule",
            "iv_stress_report",
            "overlay_cost_report",
            "assignment_risk_note",
        ],
    )


def build_options_research_report(
    options_path: Path,
    root: Path | None = None,
) -> OptionsResearchResult:
    base = root or project_root()
    raw = _load_yaml_mapping(options_path)
    spec = OptionsSpec.model_validate(raw)
    return _write_options_report(
        base=base,
        name=spec.name,
        spec_path=options_path,
        instrument_type="options",
        payload=spec.model_dump(mode="json"),
        required_artifacts=[
            "options_chain_source_cards",
            "greeks_profile",
            "contract_selection_log",
            "expiry_ladder",
            "iv_stress_report",
            "assignment_risk_note",
        ],
    )


def _write_options_report(
    *,
    base: Path,
    name: str,
    spec_path: Path,
    instrument_type: str,
    payload: dict[str, object],
    required_artifacts: list[str],
) -> OptionsResearchResult:
    json_path = base / "reports" / "options" / f"{name}-research.json"
    report_path = json_path.with_suffix(".md")
    report = {
        "name": name,
        "source_spec_path": _relpath(spec_path, base),
        "instrument_type": instrument_type,
        "status": "warning",
        "execution_substate": "observation_only",
        "paper_ready_pass": False,
        "required_artifacts": required_artifacts,
        "spec": payload,
        "safety_note": (
            "Options research is observation-only in this MVP. Automatic paper orders remain "
            "blocked by product policy."
        ),
    }
    write_json(json_path, report)
    ensure_dir(report_path.parent)
    report_path.write_text(
        "\n".join(
            [
                f"# Options Research: {name}",
                "",
                f"- Instrument type: `{instrument_type}`",
                "- Execution substate: `observation_only`",
                "- Paper ready pass: `false`",
                f"- JSON: `{json_path}`",
                "",
                "## Required Artifacts",
                "",
                *[f"- `{item}`" for item in required_artifacts],
                "",
                "## Safety",
                "",
                "- Options do not enter automatic paper order flow in this MVP.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return OptionsResearchResult(
        name=name,
        report_path=report_path,
        json_path=json_path,
        execution_substate="observation_only",
        paper_ready_pass=False,
    )


def _load_yaml_mapping(path: Path) -> dict[str, object]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return raw


def _relpath(path: Path, base: Path) -> str:
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return path.as_posix()
