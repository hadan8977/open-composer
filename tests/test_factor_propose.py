from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

from open_composer.cli import app
from open_composer.research.factor_propose import (
    _evaluate_candidate,
    approve_factor_proposal,
    propose_factors,
    reject_factor_proposal,
)


def _sample_frame(root: Path) -> pd.DataFrame:
    frame = pd.read_csv(root / "data" / "sample" / "syn_daily.csv")
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    return frame


def test_factor_propose_writes_research_only_artifact(sample_workspace: Path) -> None:
    payload = propose_factors(
        "Trend continuation on SYN daily.",
        root=sample_workspace,
        max_candidates=3,
        min_abs_rank_ic=0.0,
    )

    path = sample_workspace / payload["path"]
    assert path.exists()
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["proposal_id"] == payload["proposal_id"]
    assert stored["candidates"]
    assert stored["safety_note"].startswith("Proposal artifacts are research-only")


def test_factor_propose_rejects_duplicate_catalog_id(sample_workspace: Path) -> None:
    result = _evaluate_candidate(
        _sample_frame(sample_workspace),
        {
            "id": "alpha101_009_roc_5d",
            "family": "trend",
            "label": "duplicate",
            "expression": "roc(close, 5)",
            "rationale": "duplicate id test",
        },
        root=sample_workspace,
        base_factors=[],
        min_abs_rank_ic=0.0,
        min_abs_ir=0.0,
        max_abs_correlation=0.70,
    )

    assert result["status"] == "rejected"
    assert "duplicate_catalog_id" in result["blockers"]


def test_factor_propose_rejects_unsafe_expression(sample_workspace: Path) -> None:
    result = _evaluate_candidate(
        _sample_frame(sample_workspace),
        {
            "id": "proposal_unsafe",
            "family": "unsafe",
            "label": "unsafe",
            "expression": "__import__('os')",
            "rationale": "unsafe test",
        },
        root=sample_workspace,
        base_factors=[],
        min_abs_rank_ic=0.0,
        min_abs_ir=0.0,
        max_abs_correlation=0.70,
    )

    assert result["status"] == "rejected"
    assert "unsafe_expression" in result["blockers"]


def test_factor_proposal_approve_and_reject_update_artifacts(sample_workspace: Path) -> None:
    payload = propose_factors(
        "Mean reversion buy oversold on SYN daily.",
        root=sample_workspace,
        max_candidates=2,
        min_abs_rank_ic=0.0,
    )

    approved = approve_factor_proposal(payload["proposal_id"], root=sample_workspace, reason="ok")
    rejected = reject_factor_proposal(
        payload["proposal_id"],
        root=sample_workspace,
        reason="later rejected in test",
    )

    assert approved["status"] == "approved"
    assert rejected["status"] == "rejected"
    ledger = sample_workspace / "reports" / "factor_proposals" / "rejected-ledger.jsonl"
    assert ledger.exists()


def test_factor_propose_cli(sample_workspace: Path, monkeypatch) -> None:
    monkeypatch.chdir(sample_workspace)
    result = CliRunner().invoke(
        app,
        [
            "factor",
            "propose",
            "Volatility breakout regime on SYN daily.",
            "--max-candidates",
            "2",
            "--min-abs-rank-ic",
            "0",
        ],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "factor proposal written" in result.output
