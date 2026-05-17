from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import yaml

from open_composer.adapters.broker import alpaca_paper
from open_composer.dashboard import build_dashboard_catalog
from open_composer.engines.signal_engine import build_signal
from open_composer.models.paper import PaperOrderRecord
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.paper_controls import clear_paper_kill_switch, enable_paper_kill_switch
from open_composer.runner.paper import PaperRunnerError, run_paper_cycle
from open_composer.storage import append_jsonl
from open_composer.strategy_lifecycle import activate_strategy, approve_strategy, disable_strategy
from open_composer.strategy_versions import load_strategy_versions


def _context_capable_spec(sample_workspace: Path) -> Path:
    source = sample_workspace / "strategy_specs" / "drafts" / "qqq_pullback_15m.yaml"
    target = sample_workspace / "strategy_specs" / "drafts" / "qqq_pullback_context_auto.yaml"
    raw = yaml.safe_load(source.read_text(encoding="utf-8"))
    raw["name"] = "qqq_pullback_context_auto"
    raw["description"] = "QQQ pullback strategy with auto context replay packet emission."
    raw["llm_review"] = {"enabled": True, "model": "gpt-5.5"}
    target.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return target


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


def test_paper_runner_preview_then_blocks_unready_auto_submit(
    sample_workspace: Path,
    monkeypatch,
) -> None:
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
    assert preview.execution_backend == "nautilus_paper"
    assert preview.backend_plan_path
    assert preview.paper_readiness_report_path
    assert any(
        "Nautilus paper runtime generated latest-bar signals" in note for note in preview.notes
    )
    assert any("Paper readiness status=blocked" in note for note in preview.notes)
    paper_plan_path = Path(preview.backend_plan_path)
    paper_readiness_path = Path(preview.paper_readiness_report_path)
    paper_plan = json.loads(paper_plan_path.read_text(encoding="utf-8"))
    assert dashboard_paper_run.kind == "paper"
    assert dashboard_paper_run.version_id == preview.version_id
    assert dashboard_paper_run.spec_hash == preview.spec_hash
    assert dashboard_paper_run.strategy_backend == "nautilus_trader"
    assert dashboard_paper_run.execution_backend == "nautilus_paper"
    assert dashboard_paper_run.backend_plan_path == preview.backend_plan_path
    assert dashboard_paper_run.paper_readiness_report_path == preview.paper_readiness_report_path
    assert dashboard_paper_run.signals == len(preview.signals)
    assert paper_plan_path.exists()
    assert paper_plan["target_backend"] == "nautilus_paper"
    assert paper_plan["selected_backend"] == "nautilus_paper"
    assert paper_plan["version_id"] == preview.version_id
    assert paper_plan["spec_hash"] == preview.spec_hash
    assert paper_readiness_path.exists()
    paper_signal_log = sample_workspace / "signal_logs" / f"{preview.run_id}.jsonl"
    paper_scan_report = sample_workspace / "reports" / "scans" / f"{preview.run_id}.md"
    assert paper_signal_log.exists()
    assert paper_scan_report.exists()
    paper_signal = json.loads(paper_signal_log.read_text(encoding="utf-8").splitlines()[0])
    assert paper_signal["execution_backend"] == "nautilus_paper"
    assert paper_signal["version_id"] == preview.version_id
    assert paper_signal["spec_hash"] == preview.spec_hash
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

    assert submitted.signals[0].decision == "blocked_by_readiness"
    assert "data_source" in submitted.signals[0].message
    assert submitted.strategy_backend == "nautilus_trader"
    assert submitted.execution_backend == "nautilus_paper"
    assert repeated.signals[0].decision == "blocked_by_readiness"
    assert calls["count"] == 0
    assert not (sample_workspace / "reports" / "paper" / "orders.jsonl").exists()


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


def test_paper_runner_submits_when_readiness_passes(sample_workspace: Path, monkeypatch) -> None:
    monkeypatch.setenv("ALPACA_API_KEY_ID", "key")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "secret")
    monkeypatch.setenv("ALPACA_PAPER", "true")
    account_path = sample_workspace / "reports" / "paper" / "account.json"
    account_path.parent.mkdir(parents=True, exist_ok=True)
    account_path.write_text(
        (
            '{"generated_at":"2026-05-12T12:00:00Z","equity":10000,"cash":5000,'
            '"buying_power":8000,"portfolio_value":10000,"status":"ACTIVE","paper":true}\n'
        ),
        encoding="utf-8",
    )
    draft = sample_workspace / "strategy_specs" / "drafts" / "qqq_paper_ready_15m.yaml"
    raw = yaml.safe_load(
        (sample_workspace / "strategy_specs" / "drafts" / "qqq_pullback_15m.yaml").read_text(
            encoding="utf-8"
        )
    )
    raw["name"] = "qqq_paper_ready_15m"
    raw["required_capabilities"] = ["market.sample_ohlcv"]
    draft.write_text(yaml.safe_dump(raw), encoding="utf-8")
    active = activate_strategy(
        draft,
        sample_workspace,
        paper_auto=True,
        allow_paper_auto=True,
        data_source="alpaca",
    )
    spec = load_strategy_spec(active)
    promotion_path = (
        sample_workspace / "reports" / "research" / "qqq_paper_ready_15m-promotion.json"
    )
    promotion_path.parent.mkdir(parents=True, exist_ok=True)
    promotion_path.write_text(
        json.dumps(
            {
                "strategy_name": "qqq_paper_ready_15m",
                "source_spec_path": "strategy_specs/active/qqq_paper_ready_15m.yaml",
                "status": "ok",
                "ready": True,
                "gate_summary": {
                    "workflow_pass": True,
                    "research_pass": True,
                    "llm_contribution_pass": None,
                    "paper_ready_pass": True,
                },
                "checks": [
                    {"name": "in_sample", "status": "ok", "message": "ok", "details": {}},
                    {"name": "strict_data", "status": "ok", "message": "ok", "details": {}},
                    {
                        "name": "feature_packets",
                        "status": "ok",
                        "message": "ok",
                        "details": {},
                    },
                    {
                        "name": "benchmark_family",
                        "status": "ok",
                        "message": "ok",
                        "details": {},
                    },
                    {"name": "factor_lab", "status": "ok", "message": "ok", "details": {}},
                    {
                        "name": "execution_reality",
                        "status": "ok",
                        "message": "ok",
                        "details": {},
                    },
                    {
                        "name": "alternative_data",
                        "status": "ok",
                        "message": "ok",
                        "details": {},
                    },
                ],
                "benchmark_family": {"complete": True, "missing": [], "benchmarks": {}},
                "research_manifest": {
                    "research_contract_path": (
                        "reports/research/qqq_paper_ready_15m-research-contract.json"
                    )
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    def fake_scan(spec_path: Path, root: Path | None = None, refresh_data: bool = False):
        assert refresh_data is True
        base = root or sample_workspace
        signal = build_signal(
            spec,
            "scan-ready",
            datetime(2026, 5, 12, 15, 45, tzinfo=UTC),
            "entry",
            "scan",
            100.0,
        )
        append_jsonl(base / "signal_logs" / "scan-ready.jsonl", [signal])
        return [signal]

    def fake_submit(signal, spec_arg, root, client=None):
        return PaperOrderRecord(
            id="order_ready",
            signal_id=signal.id,
            client_order_id=f"oc-{signal.id}",
            strategy_name=spec_arg.name,
            strategy_id=spec_arg.name,
            symbol=signal.symbol,
            side=signal.side,
            qty=1,
            status="accepted",
        )

    monkeypatch.setattr("open_composer.runner.paper.run_scan", fake_scan)
    monkeypatch.setattr("open_composer.runner.paper.submit_paper_order", fake_submit)

    cycle = run_paper_cycle(
        active,
        sample_workspace,
        allow_paper_orders=True,
        with_review=False,
    )

    assert cycle.signals[0].decision == "paper_order_submitted"
    assert cycle.signals[0].order_id == "order_ready"


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


def test_paper_runner_auto_writes_context_feature_packets_for_context_capable_strategy(
    sample_workspace: Path,
) -> None:
    active = activate_strategy(
        _context_capable_spec(sample_workspace),
        sample_workspace,
        paper_auto=True,
        allow_paper_auto=True,
    )

    cycle = run_paper_cycle(
        active,
        sample_workspace,
        allow_paper_orders=False,
        with_review=False,
    )

    assert cycle.signals
    signal_id = cycle.signals[0].signal_id
    path = sample_workspace / "feature_logs" / f"{signal_id}_context_features.jsonl"
    assert path.exists()
    assert any("auto-written for context-capable signals" in note for note in cycle.notes)
