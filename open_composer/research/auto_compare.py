"""Cross-thesis factor comparison for auto research runs."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from open_composer.config import ensure_dir, project_root
from open_composer.research.factor_library import get_factor


@dataclass
class FactorAggregate:
    factor_id: str
    family: str = ""
    appearances: int = 0
    selected_count: int = 0
    rank_ics: list[float] = field(default_factory=list)
    irs: list[float] = field(default_factory=list)
    diagnoses: dict[str, int] = field(default_factory=dict)
    theses: list[str] = field(default_factory=list)
    selected_theses: list[str] = field(default_factory=list)


def build_cross_thesis_compare(root: Path | None = None) -> dict[str, Any]:
    base = root or project_root()
    auto_dir = base / "reports" / "research" / "auto"
    aggregates: dict[str, FactorAggregate] = {}
    runs: list[dict[str, Any]] = []
    excluded_runs: list[dict[str, str]] = []
    top3_signatures: Counter[tuple[str, ...]] = Counter()

    for run_dir in sorted(auto_dir.iterdir() if auto_dir.exists() else []):
        if not run_dir.is_dir() or run_dir.name.startswith("_"):
            continue
        ic_path = run_dir / "ic_scores.json"
        selected_path = run_dir / "selected_factors.json"
        thesis_path = run_dir / "thesis.md"
        metadata_path = run_dir / "run_metadata.json"
        if not (ic_path.exists() and thesis_path.exists()):
            continue
        try:
            ic_scores = json.loads(ic_path.read_text(encoding="utf-8"))
            selected = (
                json.loads(selected_path.read_text(encoding="utf-8"))
                if selected_path.exists()
                else []
            )
            thesis = thesis_path.read_text(encoding="utf-8").strip().splitlines()[0]
            metadata = (
                json.loads(metadata_path.read_text(encoding="utf-8"))
                if metadata_path.exists()
                else {}
            )
        except (OSError, json.JSONDecodeError, IndexError):
            continue
        if not isinstance(ic_scores, dict):
            continue
        exclusion_reason = _run_exclusion_reason(metadata)
        if exclusion_reason:
            excluded_runs.append({"run_id": run_dir.name, "reason": exclusion_reason})
            continue
        selected_ids = {str(item) for item in selected if item}
        selected_list = [str(item) for item in selected if item]
        if len(selected_list) >= 3:
            top3_signatures[tuple(selected_list[:3])] += 1
        runs.append(
            {
                "run_id": run_dir.name,
                "thesis": thesis,
                "schema_version": str(metadata.get("schema_version") or ""),
                "primary_symbol": str(metadata.get("primary_symbol") or ""),
                "timeframe": str(metadata.get("timeframe") or ""),
                "data_acquisition_tier": str(metadata.get("data_acquisition_tier") or ""),
                "research_status": str(metadata.get("research_status") or ""),
                "candidates": len(ic_scores),
                "selected": len(selected_ids),
            }
        )
        for factor_id, row in ic_scores.items():
            if not isinstance(row, dict):
                continue
            factor_key = str(factor_id)
            aggregate = aggregates.setdefault(factor_key, FactorAggregate(factor_id=factor_key))
            if not aggregate.family:
                try:
                    aggregate.family = get_factor(factor_key).family
                except KeyError:
                    aggregate.family = "unknown"
            aggregate.appearances += 1
            aggregate.theses.append(thesis[:80])
            if factor_key in selected_ids:
                aggregate.selected_count += 1
                aggregate.selected_theses.append(thesis[:80])
            rank_ic = row.get("rank_ic")
            if isinstance(rank_ic, int | float) and not isinstance(rank_ic, bool):
                aggregate.rank_ics.append(float(rank_ic))
            ir = row.get("ir")
            if isinstance(ir, int | float) and not isinstance(ir, bool):
                aggregate.irs.append(float(ir))
            diagnosis = row.get("rank_ic_diagnosis")
            if diagnosis:
                diagnosis_key = str(diagnosis)
                aggregate.diagnoses[diagnosis_key] = aggregate.diagnoses.get(diagnosis_key, 0) + 1

    factors = [
        _factor_payload(aggregate)
        for aggregate in sorted(
            aggregates.values(),
            key=lambda item: (item.selected_count, item.appearances, item.factor_id),
            reverse=True,
        )
    ]
    total_selected = sum(factor["selected_count"] for factor in factors)
    top_factor = factors[0] if factors else None
    top_signature, top_signature_count = (
        top3_signatures.most_common(1)[0] if top3_signatures else ((), 0)
    )
    concentration = {
        "total_selected_factor_slots": total_selected,
        "top_factor_id": top_factor["factor_id"] if top_factor else None,
        "top_factor_selected_count": top_factor["selected_count"] if top_factor else 0,
        "top_factor_selection_share": (
            (top_factor["selected_count"] / total_selected)
            if top_factor and total_selected
            else 0.0
        ),
        "top3_signature": list(top_signature),
        "top3_signature_count": top_signature_count,
        "top3_signature_run_share": top_signature_count / max(len(runs), 1),
    }
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "total_runs": len(runs),
        "excluded_runs": excluded_runs,
        "excluded_run_count": len(excluded_runs),
        "total_factors_seen": len(aggregates),
        "concentration": concentration,
        "runs": runs,
        "factors": factors,
    }


def write_cross_thesis_compare(root: Path | None = None) -> tuple[Path, Path]:
    base = root or project_root()
    payload = build_cross_thesis_compare(base)
    out_dir = ensure_dir(base / "reports" / "research" / "auto" / "_compare")
    json_path = out_dir / "cross_thesis_compare.json"
    md_path = out_dir / "cross_thesis_compare.md"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=False), encoding="utf-8")
    md_path.write_text(_render_markdown(payload), encoding="utf-8")
    return json_path, md_path


def _factor_payload(aggregate: FactorAggregate) -> dict[str, Any]:
    rank_ics = aggregate.rank_ics
    irs = aggregate.irs
    return {
        "factor_id": aggregate.factor_id,
        "family": aggregate.family,
        "appearances": aggregate.appearances,
        "selected_count": aggregate.selected_count,
        "selection_rate": aggregate.selected_count / max(aggregate.appearances, 1),
        "rank_ic_count": len(rank_ics),
        "rank_ic_mean": sum(rank_ics) / len(rank_ics) if rank_ics else None,
        "rank_ic_min": min(rank_ics) if rank_ics else None,
        "rank_ic_max": max(rank_ics) if rank_ics else None,
        "ir_count": len(irs),
        "ir_mean": sum(irs) / len(irs) if irs else None,
        "ir_min": min(irs) if irs else None,
        "ir_max": max(irs) if irs else None,
        "diagnoses": aggregate.diagnoses,
        "selected_theses": aggregate.selected_theses[:5],
    }


def _run_exclusion_reason(metadata: Any) -> str | None:
    if not isinstance(metadata, dict):
        return "missing_run_metadata"
    if not metadata:
        return "missing_run_metadata"
    if str(metadata.get("schema_version") or "") != "2":
        return "unsupported_schema_version"
    if metadata.get("usable_selection") is not True:
        return "no_usable_selection"
    if str(metadata.get("research_status") or "") == "failed":
        return "failed_research_status"
    for field_name in ["primary_symbol", "timeframe", "data_acquisition_tier"]:
        if not metadata.get(field_name):
            return f"missing_{field_name}"
    return None


def _render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Cross-Thesis Factor Comparison",
        "",
        f"- Generated: `{payload['generated_at']}`",
        f"- total_runs: `{payload['total_runs']}`",
        f"- excluded_runs: `{payload.get('excluded_run_count', 0)}`",
        f"- unique_factors: `{payload['total_factors_seen']}`",
        "",
        "## Concentration",
        "",
        f"- top_factor: `{payload['concentration']['top_factor_id']}` "
        f"({payload['concentration']['top_factor_selected_count']} selections, "
        f"{payload['concentration']['top_factor_selection_share'] * 100:.1f}% of selected slots)",
        "- top3_signature: "
        + ", ".join(f"`{item}`" for item in payload["concentration"]["top3_signature"])
        + f" ({payload['concentration']['top3_signature_count']} runs, "
        f"{payload['concentration']['top3_signature_run_share'] * 100:.1f}% of runs)",
        "",
        "## Runs",
        "",
        "| run_id | thesis | candidates | selected |",
        "|---|---|---:|---:|",
    ]
    for run in payload["runs"]:
        lines.append(
            f"| `{run['run_id']}` | {str(run['thesis'])[:60]} | "
            f"{run['candidates']} | {run['selected']} |"
        )
    lines.extend(
        [
            "",
            "## Factor Performance",
            "",
            (
                "| factor | family | shown | selected | sel% | IC mean | IR mean | "
                "IC min | IC max | IR min | IR max | diagnoses |"
            ),
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for factor in payload["factors"][:50]:
        diagnoses = ", ".join(
            f"{key}:{value}" for key, value in (factor["diagnoses"] or {}).items()
        )[:60]
        lines.append(
            f"| `{factor['factor_id']}` | {factor['family']} | "
            f"{factor['appearances']} | {factor['selected_count']} | "
            f"{factor['selection_rate'] * 100:.0f}% | "
            f"{_fmt(factor['rank_ic_mean'])} | {_fmt(factor['ir_mean'])} | "
            f"{_fmt(factor['rank_ic_min'])} | {_fmt(factor['rank_ic_max'])} | "
            f"{_fmt(factor['ir_min'])} | {_fmt(factor['ir_max'])} | {diagnoses} |"
        )
    return "\n".join(lines).rstrip() + "\n"


def _fmt(value: object) -> str:
    return "n/a" if value is None else f"{float(value):.3f}"
