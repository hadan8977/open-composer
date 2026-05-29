from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Literal

from open_composer.config import ensure_dir, project_root
from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec
from open_composer.storage import write_json

UniverseAuditStatus = Literal["ok", "warning", "blocked"]

FIXED_INSTRUMENT_UNIVERSE_SYMBOLS = {
    "QQQ",
    "TQQQ",
    "SQQQ",
    "QLD",
    "PSQ",
    "SMH",
    "SOXX",
    "XLK",
    "IGV",
    "SOXL",
    "SOXS",
    "TECL",
    "TECS",
    "ROM",
    "USD",
    "SPY",
    "UPRO",
    "SH",
    "SPXU",
    "CASH",
}


@dataclass(frozen=True)
class UniverseAuditFinding:
    code: str
    severity: UniverseAuditStatus
    message: str
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class UniverseAuditResult:
    strategy_name: str
    status: UniverseAuditStatus
    findings: list[UniverseAuditFinding]
    json_path: Path
    report_path: Path


def run_universe_audit(
    spec_path: Path,
    root: Path | None = None,
) -> UniverseAuditResult:
    base = root or project_root()
    spec = load_strategy_spec(spec_path)
    return assess_universe_audit(spec, base)


def assess_universe_audit(
    spec: StrategySpec,
    root: Path | None = None,
) -> UniverseAuditResult:
    base = root or project_root()
    findings = _audit_spec_universe(spec, base)
    status: UniverseAuditStatus
    if any(item.severity == "blocked" for item in findings):
        status = "blocked"
    elif any(item.severity == "warning" for item in findings):
        status = "warning"
    else:
        status = "ok"
    json_path = base / "reports" / "research" / f"{spec.name}-universe-audit.json"
    report_path = base / "reports" / "research" / f"{spec.name}-universe-audit.md"
    _write_universe_audit_json(json_path, spec, status, findings)
    _write_universe_audit_markdown(report_path, spec, status, findings)
    return UniverseAuditResult(
        strategy_name=spec.name,
        status=status,
        findings=findings,
        json_path=json_path,
        report_path=report_path,
    )


def _audit_spec_universe(spec: StrategySpec, root: Path) -> list[UniverseAuditFinding]:
    findings: list[UniverseAuditFinding] = []
    universe_metadata = _universe_metadata(spec)
    universe = sorted(set(spec.universe))
    fixed_universe = _is_documented_fixed_universe(universe, universe_metadata)
    pit_findings = (
        [] if fixed_universe else _pit_membership_findings(spec, universe, universe_metadata, root)
    )
    if len(universe) > 1 and pit_findings:
        findings.extend(pit_findings)
    elif len(universe) > 1 and fixed_universe:
        findings.append(
            UniverseAuditFinding(
                code="fixed_universe_documented",
                severity="ok",
                message=(
                    "Universe is documented as a fixed tradable-instrument set; "
                    "historical index-membership PIT evidence is not required."
                ),
                evidence={"symbols": universe, "metadata": universe_metadata},
            )
        )
    elif len(universe) > 1:
        findings.append(
            UniverseAuditFinding(
                code="current_symbol_universe_bias",
                severity="blocked",
                message=(
                    "Multi-symbol universes need point-in-time membership evidence before "
                    "research_pass; a static current-symbol list can leak survivorship."
                ),
                evidence={"symbols": universe, "metadata": universe_metadata},
            )
        )
    if len(universe) > 1 and not universe_metadata.get("selection_timestamp"):
        findings.append(
            UniverseAuditFinding(
                code="missing_universe_selection_timestamp",
                severity="warning",
                message=(
                    "Universe selection should record when the symbol list became known "
                    "to avoid current-list backfills."
                ),
                evidence={"symbols": universe, "metadata": universe_metadata},
            )
        )
    if len(universe) > 1 and not universe_metadata.get("delisting_policy"):
        findings.append(
            UniverseAuditFinding(
                code="missing_delisting_policy",
                severity="warning",
                message=(
                    "Universe audit did not find a delisting policy; scans may overstate "
                    "historical opportunity if failed or delisted names are absent."
                ),
                evidence={"symbols": universe, "metadata": universe_metadata},
            )
        )
    if spec.data.source == "sample":
        findings.append(
            UniverseAuditFinding(
                code="sample_data_not_paper_ready",
                severity="warning",
                message="Sample data can smoke-test logic but cannot support paper readiness.",
                evidence={"data_source": spec.data.source},
            )
        )
    if not findings:
        findings.append(
            UniverseAuditFinding(
                code="universe_audit_passed",
                severity="ok",
                message="No static-universe PIT or survivorship blockers were detected.",
                evidence={"symbols": universe, "metadata": universe_metadata},
            )
        )
    return findings


def _pit_membership_findings(
    spec: StrategySpec,
    universe: list[str],
    metadata: dict[str, Any],
    root: Path,
) -> list[UniverseAuditFinding]:
    if not metadata.get("point_in_time_membership"):
        return []
    path_ref = (
        metadata.get("pit_membership_path")
        or metadata.get("membership_path")
        or metadata.get("artifact_path")
    )
    if not path_ref:
        return [
            UniverseAuditFinding(
                code="pit_membership_artifact_missing",
                severity="blocked",
                message=(
                    "point_in_time_membership requires a PIT membership artifact path; "
                    "a boolean flag alone cannot clear current-symbol bias."
                ),
                evidence={"symbols": universe, "metadata": metadata},
            )
        ]
    path = _resolve_artifact_path(path_ref, root)
    if not path.exists():
        return [
            UniverseAuditFinding(
                code="pit_membership_artifact_missing",
                severity="blocked",
                message="PIT membership artifact was referenced but does not exist.",
                evidence={"path": str(path), "symbols": universe},
            )
        ]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [
            UniverseAuditFinding(
                code="pit_membership_artifact_invalid",
                severity="blocked",
                message="PIT membership artifact is not valid JSON.",
                evidence={"path": str(path), "error": str(exc)},
            )
        ]
    return _validate_pit_payload(spec, universe, path, payload)


def _validate_pit_payload(
    spec: StrategySpec,
    universe: list[str],
    path: Path,
    payload: Any,
) -> list[UniverseAuditFinding]:
    findings: list[UniverseAuditFinding] = []
    if not isinstance(payload, dict):
        return [
            UniverseAuditFinding(
                code="pit_membership_artifact_invalid",
                severity="blocked",
                message="PIT membership artifact must be a JSON object.",
                evidence={"path": str(path)},
            )
        ]
    required = {
        "source_type",
        "source_url",
        "as_of",
        "selection_timestamp",
        "delisting_policy",
        "memberships",
    }
    missing = sorted(name for name in required if not payload.get(name))
    if missing:
        findings.append(
            UniverseAuditFinding(
                code="pit_membership_required_fields_missing",
                severity="blocked",
                message="PIT membership artifact is missing required provenance fields.",
                evidence={"path": str(path), "missing": missing},
            )
        )
    memberships = payload.get("memberships")
    if not isinstance(memberships, list) or not memberships:
        findings.append(
            UniverseAuditFinding(
                code="pit_membership_rows_missing",
                severity="blocked",
                message="PIT membership artifact must contain membership rows.",
                evidence={"path": str(path)},
            )
        )
        return findings
    indexed: dict[str, list[dict[str, Any]]] = {}
    row_errors: list[str] = []
    for idx, row in enumerate(memberships):
        if not isinstance(row, dict):
            row_errors.append(f"row {idx}: not object")
            continue
        symbol = str(row.get("symbol") or "").upper().strip()
        start = row.get("effective_from")
        if not symbol or not start:
            row_errors.append(f"row {idx}: missing symbol/effective_from")
            continue
        if not _valid_date(str(start)):
            row_errors.append(f"row {idx}: invalid effective_from={start}")
            continue
        end = row.get("effective_to")
        if end not in {None, ""} and not _valid_date(str(end)):
            row_errors.append(f"row {idx}: invalid effective_to={end}")
            continue
        indexed.setdefault(symbol, []).append(row)
    if row_errors:
        findings.append(
            UniverseAuditFinding(
                code="pit_membership_rows_invalid",
                severity="blocked",
                message="PIT membership artifact contains invalid membership rows.",
                evidence={"path": str(path), "errors": row_errors[:20]},
            )
        )
    missing_symbols = sorted(symbol for symbol in universe if symbol not in indexed)
    if missing_symbols:
        findings.append(
            UniverseAuditFinding(
                code="pit_membership_symbol_missing",
                severity="blocked",
                message="PIT membership artifact does not cover every StrategySpec symbol.",
                evidence={"path": str(path), "missing_symbols": missing_symbols},
            )
        )
    coverage_start = payload.get("coverage_start") or _min_effective_from(indexed)
    coverage_end = payload.get("coverage_end") or _max_effective_to(indexed)
    coverage_warnings: list[str] = []
    if coverage_start and str(coverage_start) > "2011-02-11":
        coverage_warnings.append(f"coverage_start={coverage_start} is after iter6 history start")
    if not coverage_end:
        coverage_warnings.append("coverage_end is open-ended; refresh before paper activation")
    if coverage_warnings:
        findings.append(
            UniverseAuditFinding(
                code="pit_membership_coverage_warning",
                severity="warning",
                message="PIT membership artifact has coverage caveats that should be reviewed.",
                evidence={"path": str(path), "warnings": coverage_warnings},
            )
        )
    if not any(item.severity == "blocked" for item in findings):
        findings.append(
            UniverseAuditFinding(
                code="pit_membership_artifact_verified",
                severity="ok",
                message="PIT membership artifact exists and covers StrategySpec symbols.",
                evidence={
                    "path": str(path),
                    "source_type": payload.get("source_type"),
                    "source_url": payload.get("source_url"),
                    "coverage_start": coverage_start,
                    "coverage_end": coverage_end,
                    "symbol_count": len(indexed),
                },
            )
        )
    return findings


def _is_documented_fixed_universe(universe: list[str], metadata: dict[str, Any]) -> bool:
    if not universe:
        return False
    documented = metadata.get("fixed_universe") or metadata.get("explicit_fixed_universe")
    has_provenance = bool(metadata.get("selection_timestamp") and metadata.get("delisting_policy"))
    if documented and has_provenance:
        return True
    # Backwards-compatible acceptance for existing fixed ETF drafts. This does not
    # clear stock-universe PIT requirements.
    return bool(
        has_provenance
        and metadata.get("point_in_time_membership")
        and set(universe).issubset(FIXED_INSTRUMENT_UNIVERSE_SYMBOLS)
    )


def _resolve_artifact_path(path_ref: Any, root: Path) -> Path:
    path = Path(str(path_ref)).expanduser()
    if path.is_absolute():
        return path
    return root / path


def _valid_date(value: str) -> bool:
    try:
        date.fromisoformat(value[:10])
    except ValueError:
        return False
    return True


def _min_effective_from(indexed: dict[str, list[dict[str, Any]]]) -> str | None:
    starts = [
        str(row.get("effective_from"))[:10]
        for rows in indexed.values()
        for row in rows
        if row.get("effective_from")
    ]
    return min(starts) if starts else None


def _max_effective_to(indexed: dict[str, list[dict[str, Any]]]) -> str | None:
    ends = [
        str(row.get("effective_to"))[:10]
        for rows in indexed.values()
        for row in rows
        if row.get("effective_to")
    ]
    return max(ends) if ends else None


def _universe_metadata(spec: StrategySpec) -> dict[str, Any]:
    if spec.universe_metadata is not None:
        explicit = spec.universe_metadata.model_dump(mode="json", exclude_none=True)
        if any(value not in ("", [], {}) for value in explicit.values()):
            return explicit
    notes = spec.notes.model_dump(mode="json")
    metadata = notes.get("universe_audit") if isinstance(notes, dict) else None
    if isinstance(metadata, dict):
        return metadata
    research_design = notes.get("research_design") if isinstance(notes, dict) else None
    if isinstance(research_design, dict):
        nested = research_design.get("universe_audit")
        if isinstance(nested, dict):
            return nested
    return {}


def _write_universe_audit_json(
    path: Path,
    spec: StrategySpec,
    status: UniverseAuditStatus,
    findings: list[UniverseAuditFinding],
) -> Path:
    return write_json(
        path,
        {
            "strategy_name": spec.name,
            "status": status,
            "universe": sorted(set(spec.universe)),
            "data_source": spec.data.source,
            "focus": [
                "point_in_time_universe_membership",
                "current_symbol_bias",
                "survivorship_bias",
            ],
            "findings": [
                {
                    "code": item.code,
                    "severity": item.severity,
                    "message": item.message,
                    "evidence": item.evidence,
                }
                for item in findings
            ],
        },
    )


def _write_universe_audit_markdown(
    path: Path,
    spec: StrategySpec,
    status: UniverseAuditStatus,
    findings: list[UniverseAuditFinding],
) -> Path:
    ensure_dir(path.parent)
    lines = [
        f"# Universe Audit: {spec.name}",
        "",
        f"- Status: `{status}`",
        f"- Symbols: `{', '.join(sorted(set(spec.universe)))}`",
        f"- Data source: `{spec.data.source}`",
        "",
        "## Findings",
        "",
    ]
    for item in findings:
        lines.extend(
            [
                f"### {item.code}",
                "",
                f"- Severity: `{item.severity}`",
                f"- Message: {item.message}",
                f"- Evidence: `{json.dumps(item.evidence, sort_keys=True)}`",
                "",
            ]
        )
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path
