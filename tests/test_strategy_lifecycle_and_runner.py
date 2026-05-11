from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from open_composer.adapters.broker import alpaca_paper
from open_composer.dashboard import build_dashboard_catalog
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.paper_controls import clear_paper_kill_switch, enable_paper_kill_switch
from open_composer.runner.paper import PaperRunnerError, run_paper_cycle
from open_composer.strategy_lifecycle import activate_strategy, approve_strategy, disable_strategy
from open_composer.strategy_versions import load_strategy_versions


def test_strategy_lifecycle_approve_activate_disable(sample_workspace: Path) -> None:
    draft = sample_workspace / "strategy_specs" / "drafts" / "qqq_pullback_15m.yaml"

    approved = approve_strategy(draft, sample_workspace)
    approved_spec = load_strategy_spec(approved)
    assert approved_spec.lifecycle == "approved"
    assert approved_spec.execution.backend == "python_reference"
    assert approved_spec.execution.mode == "manual_signal"

    active = activate_strategy(
        approved,
        sample_workspace,
        paper_auto=True,
        allow_paper_auto=True,
    )
    active_spec = load_strategy_spec(active)
    assert active_spec.lifecycle == "active"
    assert active_spec.execution.backend == "nautilus_trader"
    assert active_spec.execution.mode == "paper_auto"
    assert active_spec.execution.broker == "alpaca_paper"

    retired = disable_strategy(active_spec.name, sample_workspace)
    retired_spec = load_strategy_spec(retired)
    assert retired_spec.lifecycle == "retired"
    assert retired_spec.execution.backend == "nautilus_trader"
    assert retired_spec.execution.mode == "manual_signal"
    assert not active.exists()
    versions = load_strategy_versions(sample_workspace, "qqq_pullback_15m")
    assert {version.lifecycle for version in versions} >= {"draft", "approved", "active", "retired"}
    assert any(version.parent_version_id is not None for version in versions)


def test_paper_runner_requires_active_strategy(sample_workspace: Path) -> None:
    draft = sample_workspace / "strategy_specs" / "drafts" / "qqq_pullback_15m.yaml"

    try:
        run_paper_cycle(draft, sample_workspace, with_review=False)
    except PaperRunnerError as exc:
        assert "active" in str(exc)
    else:
        raise AssertionError("draft strategy should not run")


def test_paper_runner_manual_approval_then_auto_submit(sample_workspace: Path, monkeypatch) -> None:
    monkeypatch.setenv("ALPACA_API_KEY_ID", "key")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "secret")
    monkeypatch.setenv("ALPACA_PAPER", "true")
    active = activate_strategy(
        sample_workspace / "strategy_specs" / "drafts" / "qqq_pullback_15m.yaml",
        sample_workspace,
        paper_auto=True,
        allow_paper_auto=True,
    )

    preview = run_paper_cycle(active, sample_workspace, with_review=False)
    catalog_after_preview = build_dashboard_catalog(sample_workspace)
    dashboard_paper_run = next(
        run for run in catalog_after_preview.runs if run.run_id == preview.run_id
    )
    assert preview.signals
    assert preview.signals[0].decision == "paper_orders_not_allowed"
    assert preview.version_id is not None
    assert preview.spec_hash is not None
    assert preview.strategy_backend == "nautilus_trader"
    assert preview.execution_backend == "python_reference"
    assert preview.backend_plan_path
    paper_plan_path = Path(preview.backend_plan_path)
    paper_plan = json.loads(paper_plan_path.read_text(encoding="utf-8"))
    assert dashboard_paper_run.kind == "paper"
    assert dashboard_paper_run.version_id == preview.version_id
    assert dashboard_paper_run.spec_hash == preview.spec_hash
    assert dashboard_paper_run.strategy_backend == "nautilus_trader"
    assert dashboard_paper_run.execution_backend == "python_reference"
    assert dashboard_paper_run.backend_plan_path == preview.backend_plan_path
    assert dashboard_paper_run.signals == len(preview.signals)
    assert paper_plan_path.exists()
    assert paper_plan["target_backend"] == "nautilus_paper"
    assert paper_plan["selected_backend"] == "python_reference"
    assert paper_plan["version_id"] == preview.version_id
    assert paper_plan["spec_hash"] == preview.spec_hash
    assert not (sample_workspace / "reports" / "paper" / "orders.jsonl").exists()

    calls = {"count": 0}

    class MockClient:
        def get_account(self) -> SimpleNamespace:
            return SimpleNamespace(equity="10000")

    def fake_submit(client, signal_arg, qty, client_order_id):
        calls["count"] += 1
        return SimpleNamespace(id="order_1", status="accepted")

    monkeypatch.setattr(alpaca_paper, "_submit_market_order", fake_submit)
    submitted = run_paper_cycle(
        active,
        sample_workspace,
        allow_paper_orders=True,
        with_review=False,
        client=MockClient(),
    )
    repeated = run_paper_cycle(
        active,
        sample_workspace,
        allow_paper_orders=True,
        with_review=False,
        client=MockClient(),
    )

    assert submitted.signals[0].decision == "paper_order_submitted"
    assert submitted.signals[0].order_id == "order_1"
    assert submitted.strategy_backend == "nautilus_trader"
    assert submitted.execution_backend == "python_reference"
    assert repeated.signals[0].decision == "paper_order_submitted"
    assert calls["count"] == 1


def test_manual_signal_runner_never_submits_even_with_allow(sample_workspace: Path) -> None:
    active = activate_strategy(
        sample_workspace / "strategy_specs" / "drafts" / "qqq_pullback_15m.yaml",
        sample_workspace,
    )

    cycle = run_paper_cycle(
        active,
        sample_workspace,
        allow_paper_orders=True,
        with_review=False,
    )

    assert cycle.signals
    assert cycle.signals[0].decision == "manual_review"
    assert cycle.strategy_backend == "python_reference"
    assert cycle.execution_backend == "python_reference"
    assert not (sample_workspace / "reports" / "paper" / "orders.jsonl").exists()


def test_paper_runner_blocks_when_kill_switch_enabled(sample_workspace: Path, monkeypatch) -> None:
    monkeypatch.setenv("ALPACA_API_KEY_ID", "key")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "secret")
    monkeypatch.setenv("ALPACA_PAPER", "true")
    active = activate_strategy(
        sample_workspace / "strategy_specs" / "drafts" / "qqq_pullback_15m.yaml",
        sample_workspace,
        paper_auto=True,
        allow_paper_auto=True,
    )
    clear_paper_kill_switch(sample_workspace, updated_by="test")
    enable_paper_kill_switch(sample_workspace, reason="ops hold", updated_by="test")

    cycle = run_paper_cycle(
        active,
        sample_workspace,
        allow_paper_orders=True,
        with_review=False,
    )

    assert cycle.signals
    assert cycle.signals[0].decision == "blocked_by_kill_switch"
    assert "paper kill switch is enabled" in cycle.signals[0].message
    assert not (sample_workspace / "reports" / "paper" / "orders.jsonl").exists()
