from __future__ import annotations

import json
from dataclasses import dataclass, field
from math import log, sqrt
from pathlib import Path
from statistics import fmean, pstdev
from typing import Any, Literal

from open_composer.config import ensure_dir, project_root
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.storage import write_json

OverfitRiskStatus = Literal["ok", "warning", "blocked", "not_applicable"]


@dataclass(frozen=True)
class OverfitRiskResult:
    strategy_name: str
    status: OverfitRiskStatus
    trial_count: int
    dsr_proxy: float | None
    pbo_proxy: float | None
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    json_path: Path | None = None
    report_path: Path | None = None


def build_overfit_risk_report(
    spec_path: Path,
    root: Path | None = None,
    *,
    trigger_trial_count: int = 100,
) -> OverfitRiskResult:
    base = root or project_root()
    spec = load_strategy_spec(spec_path)
    sweep_path = base / "reports" / "research" / f"{spec.name}-parameter-sweep.json"
    json_path = base / "reports" / "research" / f"{spec.name}-overfit-risk.json"
    report_path = base / "reports" / "research" / f"{spec.name}-overfit-risk.md"
    if not sweep_path.exists():
        result = OverfitRiskResult(
            strategy_name=spec.name,
            status="not_applicable",
            trial_count=0,
            dsr_proxy=None,
            pbo_proxy=None,
            warnings=["parameter_sweep_report_missing"],
            json_path=json_path,
            report_path=report_path,
        )
        _write_overfit_risk_outputs(result, {})
        return result
    payload = _read_json_mapping(sweep_path)
    trial_count = _trial_count(payload)
    scores = _candidate_scores(payload)
    sweep_dsr = _nested(payload, "dsr_inputs", "computed_dsr")
    sweep_pbo = _nested(payload, "dsr_inputs", "computed_pbo")
    dsr_proxy = _float_or_none(sweep_dsr)
    pbo_proxy = _float_or_none(sweep_pbo)
    if dsr_proxy is None:
        dsr_proxy = _compute_dsr_proxy(scores)
    if pbo_proxy is None:
        pbo_proxy = _compute_pbo_proxy(payload)
    blockers: list[str] = []
    warnings: list[str] = []
    if trial_count > trigger_trial_count:
        warnings.append(f"high_trial_count:{trial_count}>{trigger_trial_count}")
    if dsr_proxy is not None and dsr_proxy > 1.0:
        blockers.append(f"dsr_proxy_exceeds_1:{dsr_proxy:.3f}")
    if pbo_proxy is not None and pbo_proxy >= 0.50:
        blockers.append(f"pbo_proxy_high:{pbo_proxy:.3f}")
    elif pbo_proxy is not None and pbo_proxy >= 0.25:
        warnings.append(f"pbo_proxy_elevated:{pbo_proxy:.3f}")
    if trial_count <= trigger_trial_count and not blockers and not warnings:
        status: OverfitRiskStatus = "not_applicable"
    elif blockers:
        status = "blocked"
    elif warnings:
        status = "warning"
    else:
        status = "ok"
    result = OverfitRiskResult(
        strategy_name=spec.name,
        status=status,
        trial_count=trial_count,
        dsr_proxy=dsr_proxy,
        pbo_proxy=pbo_proxy,
        blockers=blockers,
        warnings=warnings,
        json_path=json_path,
        report_path=report_path,
    )
    _write_overfit_risk_outputs(result, {"parameter_sweep_path": str(sweep_path)})
    return result


def _write_overfit_risk_outputs(
    result: OverfitRiskResult,
    source_artifacts: dict[str, str],
) -> None:
    if result.json_path is None or result.report_path is None:
        return
    write_json(
        result.json_path,
        {
            "strategy_name": result.strategy_name,
            "status": result.status,
            "trial_count": result.trial_count,
            "dsr_proxy": result.dsr_proxy,
            "pbo_proxy": result.pbo_proxy,
            "blockers": result.blockers,
            "warnings": result.warnings,
            "source_artifacts": source_artifacts,
            "interpretation": (
                "DSR proxy above 1.0 or PBO proxy at/above 0.50 indicates the selected "
                "candidate may be more consistent with multiple-testing luck than robust alpha."
            ),
        },
    )
    ensure_dir(result.report_path.parent)
    lines = [
        f"# Overfit Risk: {result.strategy_name}",
        "",
        f"- Status: `{result.status}`",
        f"- Trial count: `{result.trial_count}`",
        f"- DSR proxy: `{result.dsr_proxy if result.dsr_proxy is not None else 'n/a'}`",
        f"- PBO proxy: `{result.pbo_proxy if result.pbo_proxy is not None else 'n/a'}`",
        f"- Blockers: `{', '.join(result.blockers) or 'none'}`",
        f"- Warnings: `{', '.join(result.warnings) or 'none'}`",
        "",
        "This is a lightweight proxy, not a full CSCV implementation. It is used to make "
        "large candidate searches visible before promotion or paper readiness.",
    ]
    result.report_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _read_json_mapping(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _trial_count(payload: dict[str, Any]) -> int:
    for key in ["trial_count", "candidate_count"]:
        value = payload.get(key)
        if isinstance(value, int):
            return value
    ledger = payload.get("trial_ledger")
    if isinstance(ledger, dict) and isinstance(ledger.get("trial_count"), int):
        return int(ledger["trial_count"])
    candidates = payload.get("candidates")
    return len(candidates) if isinstance(candidates, list) else 0


def _candidate_scores(payload: dict[str, Any]) -> list[float]:
    candidates = payload.get("candidates")
    if not isinstance(candidates, list):
        return []
    scores: list[float] = []
    for candidate in candidates:
        if isinstance(candidate, dict):
            score = _float_or_none(candidate.get("score"))
            if score is not None:
                scores.append(score)
    return scores


def _compute_dsr_proxy(scores: list[float]) -> float | None:
    if len(scores) <= 1:
        return None
    mean_score = fmean(scores)
    stddev = pstdev(scores)
    if stddev <= 0.0:
        return None
    expected_max = mean_score + stddev * sqrt(2.0 * log(float(len(scores))))
    denominator = expected_max - mean_score
    if denominator <= 0.0:
        return None
    return (max(scores) - mean_score) / denominator


def _compute_pbo_proxy(payload: dict[str, Any]) -> float | None:
    stability = payload.get("stability")
    if isinstance(stability, dict):
        neighbor = _float_or_none(stability.get("neighbor_success_rate"))
        if neighbor is not None:
            return max(0.0, min(1.0, 1.0 - neighbor))
    return None


def _nested(payload: dict[str, Any], *keys: str) -> Any:
    value: Any = payload
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _float_or_none(value: Any) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None
