from __future__ import annotations

from pathlib import Path

from open_composer.config import ensure_dir
from open_composer.models.capability import CapabilityEvaluation


def write_capability_report(path: Path, evaluations: list[CapabilityEvaluation]) -> Path:
    ensure_dir(path.parent)
    lines = ["# Capability Evaluation", ""]
    for evaluation in evaluations:
        status = "PASS" if evaluation.passed else "FAIL"
        lines.extend(
            [
                f"## {evaluation.capability_id}",
                "",
                f"- Status: `{evaluation.status}`",
                f"- Result: `{status}`",
                f"- Records: {evaluation.records}",
                f"- Score: {evaluation.score:.2f}",
                f"- Evaluated at: {evaluation.evaluated_at.isoformat()}",
                "",
            ]
        )
        if evaluation.issues:
            lines.append("Issues:")
            lines.extend(f"- {issue}" for issue in evaluation.issues)
            lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
