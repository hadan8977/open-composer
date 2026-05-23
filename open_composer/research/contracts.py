from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from open_composer.config import project_root
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.storage import write_json


class ResearchContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    strategy_name: str
    source_spec_path: str
    requirements: dict[str, list[str]]
    status: str = "draft"
    notes: list[str] = Field(default_factory=list)


def build_research_contract(
    spec_path: Path,
    root: Path | None = None,
) -> ResearchContract:
    base = root or project_root()
    spec = load_strategy_spec(spec_path)
    relative_spec = _relpath(spec_path, base)
    return ResearchContract(
        strategy_name=spec.name,
        source_spec_path=relative_spec,
        requirements={
            "workflow": [
                "spec_validation",
                "capability_evaluation",
                "reference_backtest",
                "factor_lab",
                "promotion_report",
                "paper_readiness_summary",
            ],
            "leakage": [
                "bar_close_signal_confirmation",
                "next_bar_open_fill_assumption",
                "feature_packets_replayed_by_visible_at",
                "no_live_llm_calls_inside_backtest",
                "purged_embargo_walk_forward_when_data_allows",
            ],
            "overfit": [
                "bounded_search_space",
                "trial_count_recorded",
                "oos_slice_reported",
                "walk_forward_reported",
                "dsr_pbo_or_proxy_warning_recorded",
            ],
            "live_gap": [
                "execution_reality_status_reported",
                "capacity_curve_reported",
                "cost_sensitivity_reported",
                "paper_readiness_summary_reported",
            ],
            "factor": [
                "factor_lab_status_reported",
                "rank_ic_or_unavailable_reason_reported",
                "factor_correlation_reported",
                "factor_stability_reported",
            ],
            "execution": [
                "dollar_volume_reported",
                "bar_participation_reported",
                "adv_participation_reported",
                "slippage_stress_reported",
            ],
            "alternative_data": [
                "feature_packet_pit_status_reported",
                "feature_packet_evidence_reported",
                "strategy_dag_status_reported_if_present",
            ],
        },
        notes=[
            "Research contracts are evidence gates, not performance guarantees.",
            "Sample, fixture, fallback, and trial-only data cannot satisfy paper readiness.",
        ],
    )


def write_research_contract(
    spec_path: Path,
    root: Path | None = None,
) -> Path:
    base = root or project_root()
    contract = build_research_contract(spec_path, base)
    path = base / "reports" / "research" / f"{contract.strategy_name}-research-contract.json"
    write_json(path, contract)
    return path


def _relpath(path: Path, base: Path) -> str:
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return path.as_posix()
