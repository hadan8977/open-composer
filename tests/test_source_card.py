"""Tests for open_composer.models.source_card (P5)."""

from __future__ import annotations

import datetime
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from open_composer.models.source_card import (
    SourceCard,
    check_source_card,
    evaluate_source_cards,
    load_source_cards,
)

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
