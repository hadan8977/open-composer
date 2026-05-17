from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from open_composer.config import ensure_dir, project_root
from open_composer.feature_packets import inspect_feature_packet
from open_composer.storage import write_json

StrategyDagNodeType = Literal["quant_signal", "llm_judge", "risk_gate", "execution_gate"]


class StrategyDagNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    type: StrategyDagNodeType
    inputs: list[str] = Field(default_factory=list)
    packet_path: str | None = None
    packet_field: str | None = None
    model: str | None = None
    prompt_hash: str | None = None

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        if not value.replace("_", "").replace("-", "").isalnum():
            raise ValueError("node id must be alphanumeric with underscores or hyphens")
        return value

    @model_validator(mode="after")
    def validate_llm_packet(self) -> StrategyDagNode:
        if self.type == "llm_judge" and (not self.packet_path or not self.packet_field):
            raise ValueError("llm_judge nodes require packet_path and packet_field")
        return self


class StrategyDagSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    strategy_name: str
    version: int = 1
    nodes: list[StrategyDagNode]
    edges: list[tuple[str, str]] = Field(default_factory=list)
    replay_only_backtest: bool = True

    @model_validator(mode="after")
    def validate_edges(self) -> StrategyDagSpec:
        ids = {node.id for node in self.nodes}
        if len(ids) != len(self.nodes):
            raise ValueError("DAG node ids must be unique")
        for node in self.nodes:
            for input_id in node.inputs:
                if input_id not in ids:
                    raise ValueError(f"DAG node {node.id} references unknown input: {input_id}")
        for left, right in self.edges:
            if left not in ids or right not in ids:
                raise ValueError(f"DAG edge references unknown node: {left}->{right}")
        if _has_cycle(ids, self.edges):
            raise ValueError("DAG edges must not contain cycles")
        return self


class LLMDecisionPacket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timestamp: datetime
    visible_at: datetime
    source: str = "llm"
    symbol: str
    decision: str
    confidence: float = Field(ge=0, le=1)
    model: str
    input_hash: str
    prompt_hash: str
    schema_version: str = "1"


class StrategyDagValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    name: str
    strategy_name: str
    status: Literal["ok", "warning", "blocked"]
    node_count: int
    llm_node_count: int
    checks: list[dict[str, object]] = Field(default_factory=list)
    report_json_path: str | None = None
    report_markdown_path: str | None = None


def load_strategy_dag(path: Path) -> StrategyDagSpec:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return StrategyDagSpec.model_validate(raw)


def validate_strategy_dag(
    path: Path,
    root: Path | None = None,
) -> StrategyDagValidationResult:
    base = root or project_root()
    dag = load_strategy_dag(path)
    checks: list[dict[str, object]] = [_structural_check(dag)]
    for node in dag.nodes:
        if node.type != "llm_judge":
            checks.append({"node": node.id, "type": node.type, "status": "ok"})
            continue
        packet_path = _resolve_path(base, node.packet_path or "")
        inspection = inspect_feature_packet(packet_path, node.packet_field)
        status = "ok" if inspection.point_in_time_status == "complete" else "blocked"
        if inspection.missing_evidence_count:
            status = "blocked"
        if (
            inspection.missing_model_count
            or inspection.missing_input_hash_count
            or inspection.missing_prompt_hash_count
        ):
            status = "blocked"
        checks.append(
            {
                "node": node.id,
                "type": node.type,
                "status": status,
                "packet_path": node.packet_path,
                "packet_field": node.packet_field,
                "point_in_time_status": inspection.point_in_time_status,
                "record_count": inspection.record_count,
                "missing_evidence_count": inspection.missing_evidence_count,
                "missing_model_count": inspection.missing_model_count,
                "missing_input_hash_count": inspection.missing_input_hash_count,
                "missing_prompt_hash_count": inspection.missing_prompt_hash_count,
                "warnings": inspection.replay_warnings,
            }
        )
    status = "ok" if all(item["status"] == "ok" for item in checks) else "blocked"
    return StrategyDagValidationResult(
        name=dag.name,
        strategy_name=dag.strategy_name,
        status=status,
        node_count=len(dag.nodes),
        llm_node_count=sum(1 for node in dag.nodes if node.type == "llm_judge"),
        checks=checks,
    )


def _structural_check(dag: StrategyDagSpec) -> dict[str, object]:
    return {
        "node": "__structure__",
        "type": "dag",
        "status": "ok",
        "replay_only_backtest": dag.replay_only_backtest,
        "edge_count": len(dag.edges),
    }


def write_strategy_dag_validation(
    result: StrategyDagValidationResult,
    root: Path | None = None,
) -> tuple[Path, Path]:
    base = root or project_root()
    json_path = base / "reports" / "research" / f"{result.name}-dag-validation.json"
    md_path = json_path.with_suffix(".md")
    result.report_json_path = _relpath(json_path, base)
    result.report_markdown_path = _relpath(md_path, base)
    write_json(json_path, result)
    ensure_dir(md_path.parent)
    lines = [
        f"# Strategy DAG Validation: {result.name}",
        "",
        f"- Status: `{result.status}`",
        f"- Strategy: `{result.strategy_name}`",
        f"- Nodes: `{result.node_count}`",
        f"- LLM nodes: `{result.llm_node_count}`",
        "",
        "## Checks",
        "",
    ]
    lines.extend(f"- `{item.get('node')}`: `{item}`" for item in result.checks)
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def _resolve_path(root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def _has_cycle(ids: set[str], edges: list[tuple[str, str]]) -> bool:
    outgoing: dict[str, list[str]] = {node_id: [] for node_id in ids}
    for left, right in edges:
        outgoing.setdefault(left, []).append(right)
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str) -> bool:
        if node_id in visiting:
            return True
        if node_id in visited:
            return False
        visiting.add(node_id)
        for next_id in outgoing.get(node_id, []):
            if visit(next_id):
                return True
        visiting.remove(node_id)
        visited.add(node_id)
        return False

    return any(visit(node_id) for node_id in ids)


def _relpath(path: Path, base: Path) -> str:
    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path)
