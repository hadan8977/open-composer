"""Tests for open_composer.models.source_card (P5)."""

from __future__ import annotations

import datetime
import json
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from open_composer.models.source_card import (
    SourceCard,
    check_source_card,
    evaluate_source_cards,
    load_source_cards,
)
from open_composer.research.research_brief import init_research_brief, validate_research_brief

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_cards(root: Path, strategy: str, cards: list[dict]) -> Path:
    path = root / "reports" / "harness" / "source_cards"
    path.mkdir(parents=True, exist_ok=True)
    jsonl = path / f"{strategy}.jsonl"
    jsonl.write_text(
        "\n".join(json.dumps(c) for c in cards),
        encoding="utf-8",
    )
    return jsonl


def _minimal_card(**overrides) -> dict:
    base = {
        "claim_id": "test-claim-001",
        "claim": "Alpaca supports OPG time_in_force",
        "source_url": "https://docs.alpaca.markets/reference/postorder",
        "source_type": "broker_official_docs",
        "accessed_at": "2026-01-01",
        "applies_to": ["my_strategy"],
        "impact_on_spec": "Enables opg_limit order style",
        "limitations": "Must submit before 09:28 ET",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# SourceCard model validation
# ---------------------------------------------------------------------------


class TestSourceCardValidation:
    def test_valid_card_parses(self) -> None:
        card = SourceCard.model_validate(_minimal_card())
        assert card.claim_id == "test-claim-001"
        assert card.source_type == "broker_official_docs"

    def test_invalid_source_type_raises(self) -> None:
        with pytest.raises(ValidationError):
            SourceCard.model_validate(_minimal_card(source_type="made_up_type"))

    def test_invalid_accessed_at_raises(self) -> None:
        with pytest.raises(ValidationError):
            SourceCard.model_validate(_minimal_card(accessed_at="not-a-date"))

    def test_expires_at_none_is_valid(self) -> None:
        card = SourceCard.model_validate(_minimal_card(expires_at=None))
        assert card.expires_at is None

    def test_expires_at_date_string_is_valid(self) -> None:
        card = SourceCard.model_validate(_minimal_card(expires_at="2027-01-01"))
        assert card.expires_at == "2027-01-01"

    def test_expires_at_invalid_raises(self) -> None:
        with pytest.raises(ValidationError):
            SourceCard.model_validate(_minimal_card(expires_at="not-a-date"))

    def test_all_valid_source_types_accepted(self) -> None:
        valid_types = [
            "broker_official_docs",
            "exchange_official_docs",
            "provider_official_docs",
            "regulatory_docs",
            "paper",
            "platform_docs",
            "industry_standard",
            "unverified",
        ]
        for st in valid_types:
            card = SourceCard.model_validate(_minimal_card(source_type=st))
            assert card.source_type == st

    def test_legacy_limitations_list_is_normalized(self) -> None:
        card = SourceCard.model_validate(
            _minimal_card(limitations=["generated placeholder", "refresh before paper_auto"])
        )

        assert card.limitations == "generated placeholder; refresh before paper_auto"


# ---------------------------------------------------------------------------
# load_source_cards
# ---------------------------------------------------------------------------


class TestLoadSourceCards:
    def test_loads_single_card(self, tmp_path: Path) -> None:
        _write_cards(tmp_path, "my_strategy", [_minimal_card()])
        cards = load_source_cards("my_strategy", tmp_path)
        assert len(cards) == 1
        assert cards[0].claim_id == "test-claim-001"

    def test_loads_multiple_cards(self, tmp_path: Path) -> None:
        cards_data = [
            _minimal_card(claim_id="c1"),
            _minimal_card(claim_id="c2"),
            _minimal_card(claim_id="c3"),
        ]
        _write_cards(tmp_path, "my_strategy", cards_data)
        cards = load_source_cards("my_strategy", tmp_path)
        assert len(cards) == 3

    def test_returns_empty_list_when_no_file(self, tmp_path: Path) -> None:
        cards = load_source_cards("nonexistent_strategy", tmp_path)
        assert cards == []

    def test_ignores_blank_lines_and_comments(self, tmp_path: Path) -> None:
        path = tmp_path / "reports" / "harness" / "source_cards"
        path.mkdir(parents=True, exist_ok=True)
        (path / "my_strategy.jsonl").write_text(
            "\n# comment\n\n" + json.dumps(_minimal_card()) + "\n\n",
            encoding="utf-8",
        )
        cards = load_source_cards("my_strategy", tmp_path)
        assert len(cards) == 1

    def test_raises_on_invalid_json(self, tmp_path: Path) -> None:
        path = tmp_path / "reports" / "harness" / "source_cards"
        path.mkdir(parents=True, exist_ok=True)
        (path / "bad.jsonl").write_text("not json at all\n", encoding="utf-8")
        with pytest.raises(ValueError, match="invalid JSON"):
            load_source_cards("bad", tmp_path)


# ---------------------------------------------------------------------------
# check_source_card / staleness
# ---------------------------------------------------------------------------


class TestCheckSourceCard:
    def _card(self, source_type: str, accessed_at: str, expires_at=None) -> SourceCard:
        return SourceCard.model_validate(
            _minimal_card(
                source_type=source_type,
                accessed_at=accessed_at,
                expires_at=expires_at,
            )
        )

    def test_fresh_card_is_not_stale(self, tmp_path: Path) -> None:
        today = datetime.date(2026, 5, 21)
        card = self._card("broker_official_docs", "2026-05-01")  # 20 days old
        status = check_source_card(card, tmp_path, today=today)
        assert not status.stale
        assert not status.expired
        assert status.age_days == 20

    def test_stale_broker_docs(self, tmp_path: Path) -> None:
        today = datetime.date(2026, 5, 21)
        # default broker_official_docs threshold is 90 days; 120 days old → stale
        card = self._card("broker_official_docs", "2026-01-21")
        status = check_source_card(card, tmp_path, today=today)
        assert status.stale

    def test_paper_has_long_threshold(self, tmp_path: Path) -> None:
        today = datetime.date(2026, 5, 21)
        # paper threshold is 730 days; 100 days old → fresh
        card = self._card("paper", "2026-02-10")
        status = check_source_card(card, tmp_path, today=today)
        assert not status.stale

    def test_expired_card_is_stale(self, tmp_path: Path) -> None:
        today = datetime.date(2026, 5, 21)
        card = self._card(
            "broker_official_docs",
            "2026-05-10",  # only 11 days old (fresh by age)
            expires_at="2026-05-01",  # but explicitly expired
        )
        status = check_source_card(card, tmp_path, today=today)
        assert status.stale
        assert status.expired

    def test_uses_source_policy_yaml_threshold(self, tmp_path: Path) -> None:
        """When source_policy.yaml is present it overrides internal defaults."""
        policy = tmp_path / "harness" / "source_policy.yaml"
        policy.parent.mkdir(parents=True, exist_ok=True)
        policy.write_text(
            "staleness_days:\n  broker_official_docs: 5\n",
            encoding="utf-8",
        )
        today = datetime.date(2026, 5, 21)
        card = self._card("broker_official_docs", "2026-05-15")  # 6 days old
        status = check_source_card(card, tmp_path, today=today)
        # Policy says 5 days; 6 > 5 → stale
        assert status.stale


# ---------------------------------------------------------------------------
# evaluate_source_cards
# ---------------------------------------------------------------------------


class TestEvaluateSourceCards:
    def test_evaluate_mixed_freshness(self, tmp_path: Path) -> None:
        today = datetime.date(2026, 5, 21)
        cards = [
            _minimal_card(claim_id="fresh", source_type="paper", accessed_at="2026-01-01"),
            _minimal_card(
                claim_id="stale", source_type="broker_official_docs", accessed_at="2025-01-01"
            ),
        ]
        _write_cards(tmp_path, "my_strategy", cards)
        statuses = evaluate_source_cards("my_strategy", tmp_path, today=today)
        assert len(statuses) == 2
        fresh_status = next(s for s in statuses if s.card.claim_id == "fresh")
        stale_status = next(s for s in statuses if s.card.claim_id == "stale")
        assert not fresh_status.stale
        assert stale_status.stale

    def test_returns_empty_for_missing_strategy(self, tmp_path: Path) -> None:
        statuses = evaluate_source_cards("nonexistent", tmp_path)
        assert statuses == []


def test_research_brief_requires_source_cards_for_method_families(
    sample_workspace: Path,
) -> None:
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"
    raw = spec_path.read_text(encoding="utf-8")
    raw = raw.replace("universe: [QQQ]", "universe: [QQQ, SQQQ]")
    spec_path.write_text(raw, encoding="utf-8")
    init_research_brief(spec_path, sample_workspace, overwrite=True)

    missing = validate_research_brief(spec_path, sample_workspace)

    assert not missing.ok
    assert "source_card_missing_for_method_family:inverse_etf" in missing.blocked

    _write_cards(
        sample_workspace,
        "fixture_pullback_15m",
        [
            _minimal_card(
                claim_id="inverse-etf-path-dependence",
                claim="Inverse ETF daily reset creates path dependence.",
                source_type="paper",
                applies_to=["inverse_etf"],
                method_family="inverse_etf",
            )
        ],
    )
    ok = validate_research_brief(spec_path, sample_workspace)
    assert ok.ok


def test_research_brief_does_not_treat_inverse_volatility_as_inverse_etf(
    sample_workspace: Path,
) -> None:
    fixture = sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "volatility_allocator.yaml"
    raw = yaml.safe_load(fixture.read_text(encoding="utf-8"))
    raw["name"] = "volatility_allocator"
    raw["notes"]["research_design"]["method_variants"] = [
        "inverse_volatility_63",
        "volatility_budget",
    ]
    spec_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")

    json_path, _ = init_research_brief(spec_path, sample_workspace, overwrite=True)
    payload = json.loads(json_path.read_text(encoding="utf-8"))

    assert payload["method_families"] == []
    assert payload["source_cards_required"] == []


def test_research_brief_accepts_short_selling_source_card_alias(
    sample_workspace: Path,
) -> None:
    fixture = sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "short_alias.yaml"
    raw = yaml.safe_load(fixture.read_text(encoding="utf-8"))
    raw["name"] = "short_alias"
    raw["position_direction"] = "long_short"
    spec_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    init_research_brief(spec_path, sample_workspace, overwrite=True)

    missing = validate_research_brief(spec_path, sample_workspace)

    assert not missing.ok
    assert "source_card_missing_for_method_family:shorting" in missing.blocked

    _write_cards(
        sample_workspace,
        "short_alias",
        [
            _minimal_card(
                claim_id="short-selling-locate",
                claim="Short selling requires locate and borrow evidence.",
                applies_to=["short_selling"],
                impact_on_spec="Blocks paper short orders until locate evidence is current.",
            )
        ],
    )
    ok = validate_research_brief(spec_path, sample_workspace)
    assert ok.ok
