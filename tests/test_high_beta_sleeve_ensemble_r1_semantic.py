from __future__ import annotations

import json
import shutil
from pathlib import Path

from open_composer.harness.policy import detect_risk_domains
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.strategy_capabilities import assess_strategy_capabilities
from scripts.prepare_high_beta_sleeve_ensemble_r1 import (
    PRIMARY_SPEC_PATH,
    SEMANTIC_CANDIDATE_IDS,
    SEMANTIC_PACKET_SCHEMA_PATH,
    _write_specs,
)

ROOT = Path(__file__).resolve().parents[1]
SPEC_PATHS = {
    "S1L01": ROOT / "strategy_specs/drafts/us_high_beta_sleeve_ensemble_r1_l01.yaml",
    "S1C01": ROOT / "strategy_specs/drafts/us_high_beta_sleeve_ensemble_r1_c01.yaml",
    "S1P01": ROOT / "strategy_specs/drafts/us_high_beta_sleeve_ensemble_r1_p01.yaml",
    "S1F01": ROOT / "strategy_specs/drafts/us_high_beta_sleeve_ensemble_r1_f01.yaml",
}
PIT_FIELDS = {
    "visible_at",
    "published_at",
    "fetched_at",
    "source",
    "input_hash",
    "prompt_hash",
}


def test_r1_semantic_consumers_declare_forward_packet_capability() -> None:
    assert SEMANTIC_CANDIDATE_IDS == {"S1L01", "S1C01", "S1P01"}
    for candidate_id in sorted(SEMANTIC_CANDIDATE_IDS):
        spec_path = SPEC_PATHS[candidate_id]
        spec = load_strategy_spec(spec_path)
        factor = spec.factors["semantic_direction"]

        assert factor.source == "llm_feature"
        assert factor.field == "direction"
        assert factor.path is not None
        assert factor.path.startswith("data/forward/high_beta_sleeve_ensemble_r1/")
        assert "news.alpaca" in spec.required_capabilities
        assert spec.notes.semantic_stock_budget == 0.0
        assert spec.notes.order_authority is False
        assert spec.notes.broker_writes is False
        assert spec.notes.semantic_packet_contract["historical_packets_available"] is False
        assert spec.notes.semantic_packet_contract["missing_packet_action"] == (
            "exact_quant_fallback_identity"
        )

        report = assess_strategy_capabilities(spec_path)
        assert report.finding("llm_quant_workflow").status == "partial"
        assert report.backend_plan.llm_feature_factor_names == ["semantic_direction"]
        assert "llm_or_news_signal" in detect_risk_domains(spec, ROOT)


def test_r1_spec_generator_preserves_semantic_and_missing_modality_roles(tmp_path: Path) -> None:
    primary_path = tmp_path / PRIMARY_SPEC_PATH
    primary_path.parent.mkdir(parents=True)
    shutil.copy2(ROOT / PRIMARY_SPEC_PATH, primary_path)

    specs = _write_specs(tmp_path)

    for candidate_id in sorted(SEMANTIC_CANDIDATE_IDS):
        spec = specs[candidate_id]
        assert spec.factors["semantic_direction"].source == "llm_feature"
        assert spec.required_capabilities == ["market.alpaca_bars", "news.alpaca"]
        assert spec.notes.semantic_packet_contract["missing_packet_action"] == (
            "exact_quant_fallback_identity"
        )
    fallback = specs["S1F01"]
    assert "semantic_direction" not in fallback.factors
    assert fallback.required_capabilities == ["market.alpaca_bars"]
    assert fallback.notes.semantic_packet_contract["mode"] == "missing_modality_control"


def test_r1_missing_modality_control_is_explicit_and_quant_only() -> None:
    spec_path = SPEC_PATHS["S1F01"]
    spec = load_strategy_spec(spec_path)
    contract = spec.notes.semantic_packet_contract

    assert "semantic_direction" not in spec.factors
    assert "news.alpaca" not in spec.required_capabilities
    assert contract["mode"] == "missing_modality_control"
    assert contract["factor_name"] is None
    assert contract["packet_path"] is None
    assert contract["historical_action"] == "exact_S1M01_target_identity"
    assert contract["missing_packet_action"] == (
        "exact_S1M01_target_identity_then_S1D01_on_model_abstention"
    )
    assert "llm_or_news_signal" not in detect_risk_domains(spec, ROOT)


def test_r1_semantic_packet_schema_requires_pit_and_zero_authority() -> None:
    schema = json.loads((ROOT / SEMANTIC_PACKET_SCHEMA_PATH).read_text(encoding="utf-8"))
    required = set(schema["required"])

    assert PIT_FIELDS <= required
    assert schema["properties"]["source"] == {"const": "news.alpaca"}
    assert schema["properties"]["acquisition_mode"] == {"const": "live_api_forward_only"}
    assert schema["properties"]["semantic_stock_budget"] == {"const": 0.0}
    assert schema["properties"]["order_authority"] == {"const": False}
    assert schema["properties"]["broker_writes"] == {"const": False}
    assert "direction" in schema["properties"]["features"]["required"]


def test_r1_capability_review_generator_preserves_evidence_boundaries() -> None:
    source = (ROOT / "scripts/prepare_high_beta_sleeve_ensemble_r1.py").read_text(encoding="utf-8")

    assert "news.alpaca fixture data validates shape only" in source
    assert '"historical_packet_count": 0' in source
    assert '"counted_forward_packet_count": 0' in source
    assert '"historical_semantic_alpha_authorized": False' in source
    assert '"llm_contribution_pass": False' in source
    assert '"paper_ready_pass": False' in source
