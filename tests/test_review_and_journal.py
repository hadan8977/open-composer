from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from open_composer.engines.backtest_engine import run_backtest
from open_composer.journal.writer import add_journal_entry
from open_composer.models.review_card import ReviewCard
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.review.llm import review_signal_with_llm, review_signal_with_status


class MockResponses:
    def __init__(self, review: ReviewCard) -> None:
        self.review = review

    def parse(self, **kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(
            output=[
                SimpleNamespace(
                    type="message",
                    content=[SimpleNamespace(type="output_text", parsed=self.review)],
                )
            ]
        )


def test_llm_review_mock_writes_card(sample_workspace: Path) -> None:
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "qqq_pullback_15m.yaml"
    artifacts = run_backtest(spec_path, root=sample_workspace)
    signal = artifacts.signals[0]
    spec = load_strategy_spec(spec_path)
    review = ReviewCard(
        signal_id=signal.id,
        strategy_name=signal.strategy_name,
        symbol=signal.symbol,
        timestamp=signal.timestamp.isoformat(),
        verdict="consider",
        confidence=0.6,
        catalyst="technical setup",
        evidence=["bar-close signal"],
        risks=["sample-data only"],
        invalidation=["close below entry setup"],
        primary_risk_source="sample-data only",
        if_wrong_top_3_reasons=["sample data overfit", "execution friction", "regime shift"],
        action_suggestion="paper observe only",
        model="mock",
    )
    client = SimpleNamespace(responses=MockResponses(review))
    result = review_signal_with_llm(
        signal, spec, sample_workspace, client=client, model="mock", force=True
    )
    assert result == review
    assert (sample_workspace / "reports" / "reviews" / f"{signal.id}.json").exists()
    markdown = sample_workspace / "reports" / "reviews" / f"{signal.id}.md"
    assert "Primary risk source: sample-data only" in markdown.read_text(encoding="utf-8")


def test_llm_review_skips_without_key(sample_workspace: Path, monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "qqq_pullback_15m.yaml"
    artifacts = run_backtest(spec_path, root=sample_workspace)
    spec = load_strategy_spec(spec_path)
    assert review_signal_with_llm(artifacts.signals[0], spec, sample_workspace, force=True) is None


def test_llm_review_skips_when_disabled_in_spec(sample_workspace: Path) -> None:
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "qqq_pullback_15m.yaml"
    artifacts = run_backtest(spec_path, root=sample_workspace)
    spec = load_strategy_spec(spec_path)
    assert spec.llm_review.enabled is False
    result = review_signal_with_status(artifacts.signals[0], spec, sample_workspace)
    assert result.review is None
    assert result.status == "disabled"


def test_llm_review_reports_auth_failure(sample_workspace: Path, monkeypatch) -> None:
    class AuthenticationError(Exception):
        status_code = 401

    class MockResponses:
        def parse(self, **kwargs: object) -> None:
            raise AuthenticationError("Incorrect API key provided: redacted-secret")

    monkeypatch.setenv("OPENAI_API_KEY", "redacted-secret")
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "qqq_pullback_15m.yaml"
    artifacts = run_backtest(spec_path, root=sample_workspace)
    spec = load_strategy_spec(spec_path)
    client = SimpleNamespace(responses=MockResponses())

    result = review_signal_with_status(
        artifacts.signals[0], spec, sample_workspace, client=client, model="mock", force=True
    )

    assert result.review is None
    assert result.status == "auth_failed"
    assert "redacted-secret" not in result.message


def test_journal_entry_links_signal(sample_workspace: Path) -> None:
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "qqq_pullback_15m.yaml"
    artifacts = run_backtest(spec_path, root=sample_workspace)
    entry = add_journal_entry(
        sample_workspace, artifacts.signals[0].id, "watched", "note", "pending"
    )
    assert entry.signal_id == artifacts.signals[0].id
    assert list((sample_workspace / "journal").glob("*.json"))
