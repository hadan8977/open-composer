from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import yaml

import open_composer.paper_readiness as paper_readiness
from open_composer.adapters.broker import alpaca_paper
from open_composer.dashboard import build_dashboard_catalog
from open_composer.engines.signal_engine import build_signal
from open_composer.execution_policy import resolve_execution_policy
from open_composer.market_calendar import next_us_equity_session
from open_composer.models.paper import PaperOrderRecord
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.paper_controls import clear_paper_kill_switch, enable_paper_kill_switch
from open_composer.runner.paper import (
    PaperRunnerError,
    _decide_signal,
    _paper_order_window_allows,
    _run_adaptive_intraday_paper_signal_cycle,
    run_paper_cycle,
)
from open_composer.storage import append_jsonl
from open_composer.strategy_lifecycle import activate_strategy, approve_strategy, disable_strategy
from open_composer.strategy_versions import (
    load_strategy_versions,
    strategy_content_hash,
    strategy_version_id,
)


def _context_capable_spec(sample_workspace: Path) -> Path:
    source = sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"
    target = sample_workspace / "strategy_specs" / "drafts" / "qqq_pullback_context_auto.yaml"
    raw = yaml.safe_load(source.read_text(encoding="utf-8"))
    raw["name"] = "qqq_pullback_context_auto"
    raw["description"] = "QQQ pullback strategy with auto context replay packet emission."
    raw["llm_review"] = {"enabled": True, "model": "gpt-5.5"}
    target.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return target


def _write_paper_auto_harness_artifacts(root: Path, strategy_name: str) -> None:
    execution_dir = root / "reports" / "harness" / "execution"
    paper_dir = root / "reports" / "harness" / "paper"
    source_dir = root / "reports" / "harness" / "source_cards"
    execution_dir.mkdir(parents=True, exist_ok=True)
    paper_dir.mkdir(parents=True, exist_ok=True)
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / f"{strategy_name}.jsonl").write_text(
        json.dumps(
            {
                "claim_id": f"{strategy_name}:source-research",
                "claim": (
                    "Paper order support and data assumptions are sourced for the test strategy."
                ),
                "source_url": "https://docs.alpaca.markets/docs/trading/orders/",
                "source_type": "broker_official_docs",
                "accessed_at": "2026-07-09",
                "applies_to": ["paper_auto", "broker_specific"],
                "impact_on_spec": "Allow paper runner tests to exercise order submission.",
                "limitations": "Fixture card; production cards require current source review.",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (execution_dir / f"{strategy_name}-execution-policy.json").write_text(
        json.dumps(
            {
                "strategy_name": strategy_name,
                "policy_id": f"day_market_{strategy_name}_v1",
                "order_style": "day_market",
                "time_in_force": "day",
                "price_protection": {"type": "none"},
                "gap_filter": {"enabled": False},
                "spread_filter": {"enabled": True},
                "participation_cap": {"max_adv_pct": 2.5},
                "fallback_behavior": {"if_rejected": "skip"},
                "tca_plan": {"enabled": True},
                "source_card_ids": [f"{strategy_name}:source-research"],
                "alternatives_compared": ["day_market", "loo_limit"],
                "naked_market_justification": "Fixture uses a liquid paper-only test symbol.",
            }
        ),
        encoding="utf-8",
    )
    (execution_dir / f"{strategy_name}-execution-reality.json").write_text(
        json.dumps(
            {
                "strategy_name": strategy_name,
                "policy_id": f"day_market_{strategy_name}_v1",
                "slippage_scenarios": [],
                "gap_stress": {},
                "capacity_assessment": {},
                "tca_reference_prices": ["arrival_price"],
            }
        ),
        encoding="utf-8",
    )
    spec = load_strategy_spec(root / "strategy_specs" / "active" / f"{strategy_name}.yaml")
    policy = resolve_execution_policy(spec, root)
    promotion_path = root / "reports" / "research" / f"{strategy_name}-promotion.json"
    promotion = json.loads(promotion_path.read_text(encoding="utf-8"))
    (paper_dir / f"{strategy_name}-paper-safety-review.json").write_text(
        json.dumps(
            {
                "strategy_name": strategy_name,
                "lifecycle_status": "active",
                "harness_verify_pass": True,
                "kill_switch_verified": True,
                "order_window": "regular session",
                "duplicate_order_policy": "stable_signal_id",
                "credential_scope": "paper_only",
                "signal_order_linkage": True,
                "spec_hash": strategy_content_hash(spec),
                "execution_policy_id": policy.policy_id if policy else None,
                "execution_policy_hash": policy.content_hash if policy else None,
                "promotion_report_hash": _sha256_file(promotion_path),
                "data_manifest_hash": promotion["research_manifest"]["data_manifest_hash"],
                "overall": "approved",
                "blocking_items": [],
            }
        ),
        encoding="utf-8",
    )
    verify_dir = root / "reports" / "harness" / "verify"
    verify_dir.mkdir(parents=True, exist_ok=True)
    (verify_dir / f"{strategy_name}.json").write_text(
        json.dumps({"strategy_name": strategy_name, "overall": "ok"}),
        encoding="utf-8",
    )


def test_strategy_lifecycle_approve_activate_disable(sample_workspace: Path) -> None:
    draft = sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"

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
    versions = load_strategy_versions(sample_workspace, "fixture_pullback_15m")
    assert {version.lifecycle for version in versions} >= {"draft", "approved", "active", "retired"}
    assert any(version.parent_version_id is not None for version in versions)


def test_paper_runner_requires_active_strategy(sample_workspace: Path) -> None:
    draft = sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"

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
        sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml",
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
    assert preview.paper_readiness_report_path
    assert any(
        "signals were evaluated by the Python reference path" in note for note in preview.notes
    )
    assert any("Paper readiness status=blocked" in note for note in preview.notes)
    paper_plan_path = Path(preview.backend_plan_path)
    paper_readiness_path = Path(preview.paper_readiness_report_path)
    paper_plan = json.loads(paper_plan_path.read_text(encoding="utf-8"))
    assert dashboard_paper_run.kind == "paper"
    assert dashboard_paper_run.version_id == preview.version_id
    assert dashboard_paper_run.spec_hash == preview.spec_hash
    assert dashboard_paper_run.strategy_backend == "nautilus_trader"
    assert dashboard_paper_run.execution_backend == "python_reference"
    assert dashboard_paper_run.backend_plan_path == preview.backend_plan_path
    assert dashboard_paper_run.paper_readiness_report_path == preview.paper_readiness_report_path
    assert dashboard_paper_run.signals == len(preview.signals)
    assert paper_plan_path.exists()
    assert paper_plan["target_backend"] == "nautilus_paper"
    assert paper_plan["selected_backend"] == "python_reference"
    assert paper_plan["version_id"] == preview.version_id
    assert paper_plan["spec_hash"] == preview.spec_hash
    assert paper_readiness_path.exists()
    paper_signal_log = sample_workspace / "signal_logs" / f"{preview.run_id}.jsonl"
    paper_scan_report = sample_workspace / "reports" / "scans" / f"{preview.run_id}.md"
    assert paper_signal_log.exists()
    assert paper_scan_report.exists()
    paper_signal = json.loads(paper_signal_log.read_text(encoding="utf-8").splitlines()[0])
    assert paper_signal["execution_backend"] == "python_reference"
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
    assert submitted.execution_backend == "python_reference"
    assert repeated.signals[0].decision == "blocked_by_readiness"
    assert calls["count"] == 0
    assert not (sample_workspace / "reports" / "paper" / "orders.jsonl").exists()


def test_manual_signal_runner_never_submits_even_with_allow(sample_workspace: Path) -> None:
    active = activate_strategy(
        sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml",
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


def test_paper_runner_submits_when_canary_readiness_passes(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ALPACA_API_KEY_ID", "key")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "secret")
    monkeypatch.setenv("ALPACA_PAPER", "true")
    draft = sample_workspace / "strategy_specs" / "drafts" / "qqq_paper_ready_15m.yaml"
    raw = yaml.safe_load(
        (sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml").read_text(
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
    _write_current_paper_snapshots(sample_workspace)
    contract_path = (
        sample_workspace / "reports" / "research" / "qqq_paper_ready_15m-research-contract.json"
    )
    data_manifest_path = (
        sample_workspace / "reports" / "research" / "qqq_paper_ready_15m-data-manifest.json"
    )
    contract_path.parent.mkdir(parents=True, exist_ok=True)
    contract_path.write_text('{"strategy_name":"qqq_paper_ready_15m"}\n', encoding="utf-8")
    data_manifest_path.write_text(
        '{"strategy_name":"qqq_paper_ready_15m","immutable":true}\n',
        encoding="utf-8",
    )
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
                    "spec_hash": strategy_content_hash(spec),
                    "research_contract_path": str(contract_path.relative_to(sample_workspace)),
                    "research_contract_hash": _sha256_file(contract_path),
                    "data_manifest_path": str(data_manifest_path.relative_to(sample_workspace)),
                    "data_manifest_hash": _sha256_file(data_manifest_path),
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    _write_paper_auto_harness_artifacts(sample_workspace, "qqq_paper_ready_15m")
    _write_paper_validation_days(sample_workspace, active)
    monkeypatch.setattr(
        paper_readiness,
        "_paper_tca_check",
        lambda _spec, _root: paper_readiness.PaperStrategyReadinessCheck(
            name="matched_paper_tca",
            status="ok",
            message="Verified TCA fixture.",
            details={"valid_observation_count": 30, "distinct_session_count": 10},
        ),
    )
    canary_readiness = paper_readiness.PaperStrategyReadinessReport(
        strategy_name=spec.name,
        status="warning",
        ready=False,
        execution_substate="canary_authorized",
    )
    monkeypatch.setattr(
        "open_composer.runner.paper.assess_paper_strategy_readiness",
        lambda _spec, _root: canary_readiness,
    )

    def fake_scan(
        spec_path: Path,
        root: Path | None = None,
        refresh_data: bool = False,
        **_kwargs,
    ):
        assert refresh_data is True
        base = root or sample_workspace
        signal = build_signal(
            spec,
            "scan-ready",
            datetime.now(UTC),
            "entry",
            "scan",
            100.0,
            version_id=strategy_version_id(spec),
            spec_hash=strategy_content_hash(spec),
            target_weight=spec.risk.max_position_weight,
        )
        append_jsonl(base / "signal_logs" / "scan-ready.jsonl", [signal])
        return [signal]

    def fake_submit(signal, spec_arg, root, client=None, qty=None):
        assert qty is None
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

    monkeypatch.setattr("open_composer.runner.paper._run_nautilus_paper_signal_cycle", fake_scan)
    monkeypatch.setattr("open_composer.runner.paper.submit_paper_order", fake_submit)

    cycle = run_paper_cycle(
        active,
        sample_workspace,
        allow_paper_orders=True,
        with_review=False,
    )

    assert cycle.signals[0].decision == "paper_order_submitted"
    assert cycle.signals[0].order_id == "order_ready"


def test_canary_runner_allows_warning_substate_without_quantity_override(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    active = activate_strategy(
        sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml",
        sample_workspace,
        paper_auto=True,
        allow_paper_auto=True,
        data_source="alpaca",
    )
    spec = load_strategy_spec(active)
    signal = build_signal(
        spec,
        "canary-run",
        datetime.now(UTC),
        "entry",
        "test",
        100.0,
        version_id=strategy_version_id(spec),
        spec_hash=strategy_content_hash(spec),
        target_weight=spec.risk.max_position_weight,
    )
    append_jsonl(sample_workspace / "signal_logs" / "canary-run.jsonl", [signal])
    clear_paper_kill_switch(sample_workspace, updated_by="test")
    readiness = paper_readiness.PaperStrategyReadinessReport(
        strategy_name=spec.name,
        status="warning",
        ready=False,
        execution_substate="canary_authorized",
    )
    captured: dict[str, object] = {}

    def fake_submit(signal_arg, spec_arg, root, client=None, qty=None):
        captured.update(
            {
                "signal": signal_arg,
                "spec": spec_arg,
                "root": root,
                "client": client,
                "qty": qty,
            }
        )
        return PaperOrderRecord(
            id="canary-order",
            signal_id=signal_arg.id,
            client_order_id=f"oc-{signal_arg.id}",
            strategy_name=spec_arg.name,
            symbol=signal_arg.symbol,
            side=signal_arg.side,
            qty=1,
            status="accepted",
        )

    monkeypatch.setattr("open_composer.runner.paper._paper_order_window_allows", lambda _spec: True)
    monkeypatch.setattr("open_composer.runner.paper.submit_paper_order", fake_submit)

    result = _decide_signal(
        signal_id=signal.id,
        action=signal.action,
        symbol=signal.symbol,
        price=signal.price,
        spec=spec,
        allow_paper_orders=True,
        require_review_consider=False,
        review_result=None,
        readiness=readiness,
        root=sample_workspace,
        client=object(),
    )

    assert result.decision == "paper_order_submitted"
    assert captured["qty"] is None


def _write_paper_validation_days(root: Path, spec_path: Path, count: int = 20) -> None:
    spec = load_strategy_spec(spec_path)
    policy = resolve_execution_policy(spec, root)
    log_dir = root / "reports" / "paper" / "daily_cycle"
    log_dir.mkdir(parents=True, exist_ok=True)
    day = date(2026, 6, 1)
    for _ in range(count):
        started_at = datetime(day.year, day.month, day.day, 14, tzinfo=UTC)
        account_hash = hashlib.sha256(b"paper-account-test").hexdigest()
        authorization = {
            "strategy_name": spec.name,
            "spec_hash": strategy_content_hash(spec),
            "execution_policy_id": policy.policy_id if policy else None,
            "execution_policy_hash": policy.content_hash if policy else None,
            "authorization_kind": "full",
            "execution_substate": "order_authorized",
            "authorized": True,
            "authorized_at": started_at.isoformat(),
            "authorized_by": "test_operator",
            "order_scope": "alpaca_paper_only",
            "real_money_broker_writes": "out_of_scope",
        }
        authorization["authorization_id"] = (
            "auth_"
            + hashlib.sha256(
                json.dumps(
                    authorization,
                    ensure_ascii=True,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()[:16]
        )
        evidence = {
            "target_weights": {"strategy_name": spec.name, "target_weights": []},
            "review_card": {"strategy": spec.name, "date": day.isoformat()},
            "state_drift": {
                "report_type": "paper_state_drift",
                "date": day.isoformat(),
                "status": "ok",
            },
            "paper_readiness": {
                "strategy_name": spec.name,
                "status": "ok",
                "execution_substate": "order_authorized",
            },
            "broker_sync": {"paper": True, "orders": []},
            "broker_sync_receipt": {
                "receipt_version": 1,
                "receipt_source": "alpaca_paper_sync",
                "paper": True,
                "broker_account_id_hash": account_hash,
            },
            "paper_authorization": authorization,
            "account_snapshot": {
                "paper": True,
                "broker_account_id_hash": account_hash,
            },
            "positions_snapshot": {"paper": True, "positions": []},
            "paper_monitor": {
                "status": "ok",
                "sync_broker": True,
                "sync_status": "ok",
            },
            "paper_cycle": {
                "run_id": f"paper-{day:%Y%m%d}",
                "strategy_name": spec.name,
                "spec_hash": strategy_content_hash(spec),
                "signals": [],
            },
        }
        bindings = []
        for role, evidence_payload in evidence.items():
            evidence_path = root / "paper_evidence" / f"{spec.name}-{day:%Y%m%d}-{role}.json"
            evidence_path.parent.mkdir(parents=True, exist_ok=True)
            evidence_path.write_text(
                json.dumps(evidence_payload, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            bindings.append(
                {
                    "role": role,
                    "path": evidence_path.relative_to(root).as_posix(),
                    "sha256": _sha256_file(evidence_path),
                    "size_bytes": evidence_path.stat().st_size,
                }
            )
        payload = {
            "report_type": "daily_paper_cycle",
            "cycle_receipt_version": 3,
            "date": day.isoformat(),
            "started_at": started_at.isoformat(),
            "ended_at": (started_at + timedelta(minutes=5)).isoformat(),
            "strategy": spec.name,
            "spec_hash": strategy_content_hash(spec),
            "active_spec_hash": strategy_content_hash(spec),
            "active_spec_path": f"strategy_specs/active/{spec.name}.yaml",
            "execution_policy_id": policy.policy_id if policy else None,
            "execution_policy_hash": policy.content_hash if policy else None,
            "status": "ok",
            "paper_order_authorization": True,
            "paper_authorization_substate": "order_authorized",
            "previous_day_remediation_check": {"status": "ok"},
            "steps": [
                {"name": "readiness", "exit_code": 0},
                {"name": "target_weights", "exit_code": 0},
                {"name": "paper_cycle", "exit_code": 0},
                {"name": "paper_monitor", "exit_code": 0},
                {"name": "state_drift", "exit_code": 0},
            ],
            "artifact_paths": {},
            "evidence_bindings": bindings,
        }
        path = log_dir / f"{spec.name}-{day:%Y%m%d}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        day = next_us_equity_session(day)


def _write_current_paper_snapshots(root: Path) -> None:
    generated_at = datetime.now(UTC).isoformat()
    paper_dir = root / "reports" / "paper"
    paper_dir.mkdir(parents=True, exist_ok=True)
    (paper_dir / "account.json").write_text(
        json.dumps(
            {
                "generated_at": generated_at,
                "equity": 10000,
                "cash": 5000,
                "buying_power": 8000,
                "portfolio_value": 10000,
                "broker_account_id_hash": hashlib.sha256(b"paper-account-test").hexdigest(),
                "status": "ACTIVE",
                "paper": True,
            }
        ),
        encoding="utf-8",
    )
    (paper_dir / "positions.json").write_text(
        json.dumps({"generated_at": generated_at, "paper": True, "positions": []}),
        encoding="utf-8",
    )


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_hybrid_open_to_open_paper_orders_require_open_window(sample_workspace: Path) -> None:
    draft = sample_workspace / "strategy_specs" / "drafts" / "hybrid_router_window.yaml"
    raw = yaml.safe_load(
        (sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml").read_text(
            encoding="utf-8"
        )
    )
    raw["name"] = "hybrid_router_window"
    raw["timeframe"] = "1m"
    raw["universe"] = ["AAPL", "MSFT", "NVDA"]
    raw["portfolio"] = {
        "mode": "hybrid_adaptive_router",
        "max_symbols_per_day": 1,
        "gross_exposure_limit": 1.0,
        "max_symbol_weight": 1.0,
        "same_day_flatten": False,
        "duplicate_signal_policy": "stable_signal_id",
        "selected_route_label": "open_to_open:lb20_top1_qsm50_min0_w1",
    }
    raw["risk"]["max_position_weight"] = 1.0
    draft.write_text(yaml.safe_dump(raw), encoding="utf-8")
    active = activate_strategy(
        draft,
        sample_workspace,
        paper_auto=True,
        allow_paper_auto=True,
        data_source="alpaca",
    )
    spec = load_strategy_spec(active)

    assert _paper_order_window_allows(spec, datetime(2026, 5, 19, 13, 25, tzinfo=UTC))
    assert not _paper_order_window_allows(spec, datetime(2026, 5, 19, 4, 14, tzinfo=UTC))


def test_adaptive_intraday_paper_cycle_exits_stale_position(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    draft = sample_workspace / "strategy_specs" / "drafts" / "adaptive_intraday_exit.yaml"
    raw = yaml.safe_load(
        (sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml").read_text(
            encoding="utf-8"
        )
    )
    raw["name"] = "adaptive_intraday_exit"
    raw["timeframe"] = "1m"
    raw["universe"] = ["AAA", "BBB"]
    raw["lifecycle"] = "active"
    raw["risk"] = {
        "max_trades_per_day": 2,
        "max_position_weight": 0.25,
        "stop_loss_pct": 1.0,
        "take_profit_pct": 2.0,
    }
    raw["portfolio"] = {
        "mode": "adaptive_intraday_internal_router",
        "max_symbols_per_day": 1,
        "gross_exposure_limit": 0.25,
        "max_symbol_weight": 0.25,
        "same_day_flatten": True,
        "duplicate_signal_policy": "stable_signal_id",
        "selected_route_label": "open_momentum:lb5_entry1_top1_open0_mom0_rv0.8_none",
    }
    raw["execution"] = {
        "backend": "nautilus_trader",
        "mode": "paper_auto",
        "signal_on": "bar_close",
        "fill_assumption": "next_bar_open",
        "broker": "alpaca_paper",
    }
    raw["data"] = {"source": "alpaca", "symbol": "AAA", "feed": "iex"}
    draft.write_text(yaml.safe_dump(raw), encoding="utf-8")
    spec = load_strategy_spec(draft)

    fake_scan = SimpleNamespace(
        route=SimpleNamespace(label=spec.portfolio.selected_route_label),
        selected_sub_strategy=None,
        signal_plans=[],
        signals=[],
        latest_prices={"AAA": 100.0, "BBB": 50.0},
        date="2026-05-19",
    )

    class MockClient:
        def get_account(self) -> SimpleNamespace:
            return SimpleNamespace(equity="10000")

        def get_all_positions(self) -> list[SimpleNamespace]:
            return [SimpleNamespace(symbol="AAA", qty="10")]

    monkeypatch.setattr(
        "open_composer.runner.paper.run_adaptive_intraday_router_scan",
        lambda *args, **kwargs: fake_scan,
    )
    monkeypatch.setattr(
        "open_composer.runner.paper.sync_paper_orders", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(
        "open_composer.runner.paper.sync_paper_account",
        lambda *args, **kwargs: None,
    )

    signals = _run_adaptive_intraday_paper_signal_cycle(
        draft,
        spec,
        sample_workspace,
        run_id_value="paper-adaptive-test",
        version_id="ver_test",
        spec_hash="hash_test",
        client=MockClient(),
        refresh_data=False,
    )

    assert len(signals) == 1
    assert signals[0].symbol == "AAA"
    assert signals[0].action == "exit"
    assert signals[0].side == "sell"
    assert signals[0].qty == 10
    assert signals[0].target_weight == 0.0
    assert signals[0].execution_backend == "python_reference"


def test_beta_router_paper_orders_require_open_window(sample_workspace: Path) -> None:
    draft = sample_workspace / "strategy_specs" / "drafts" / "beta_router_window.yaml"
    raw = yaml.safe_load(
        (sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml").read_text(
            encoding="utf-8"
        )
    )
    raw["name"] = "beta_router_window"
    raw["timeframe"] = "daily"
    raw["universe"] = ["QQQ", "TQQQ", "SQQQ"]
    raw["portfolio"] = {
        "mode": "beta_exposure_router",
        "max_symbols_per_day": 1,
        "gross_exposure_limit": 0.75,
        "max_symbol_weight": 0.75,
        "same_day_flatten": False,
        "duplicate_signal_policy": "stable_signal_id",
        "selected_route_label": (
            "beta:sma200_mom120_min0_vol20_maxvnone_dd120_maxddnone_"
            "levsma50_levmaxvnone_levdd60_levmaxdd20_"
            "onTQQQ0.75_neuQQQ0.75_offCASH0_vtnone"
        ),
    }
    raw["data"] = {"source": "alpaca", "symbol": "QQQ", "feed": "iex"}
    draft.write_text(yaml.safe_dump(raw), encoding="utf-8")
    active = activate_strategy(
        draft,
        sample_workspace,
        paper_auto=True,
        allow_paper_auto=True,
        data_source="alpaca",
    )
    spec = load_strategy_spec(active)

    assert _paper_order_window_allows(spec, datetime(2026, 5, 19, 13, 25, tzinfo=UTC))
    assert not _paper_order_window_allows(spec, datetime(2026, 5, 19, 13, 35, tzinfo=UTC))
    assert not _paper_order_window_allows(spec, datetime(2026, 5, 23, 13, 25, tzinfo=UTC))


def test_beta_router_paper_runtime_uses_route_symbols(sample_workspace: Path, monkeypatch) -> None:
    draft = sample_workspace / "strategy_specs" / "drafts" / "beta_qld_runtime.yaml"
    raw = yaml.safe_load(
        (sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml").read_text(
            encoding="utf-8"
        )
    )
    raw["name"] = "beta_qld_runtime"
    raw["timeframe"] = "daily"
    raw["universe"] = ["QQQ", "QLD", "QID"]
    raw["portfolio"] = {
        "mode": "beta_exposure_router",
        "max_symbols_per_day": 1,
        "gross_exposure_limit": 1.0,
        "max_symbol_weight": 1.0,
        "same_day_flatten": False,
        "duplicate_signal_policy": "stable_signal_id",
        "selected_route_label": (
            "beta:sma20_mom10_min0_vol10_maxvnone_dd20_maxddnone_"
            "levsmanone_levmaxvnone_levdd20_levmaxddnone_"
            "onQLD1_neuQQQ0.75_offCASH0_vtnone"
        ),
    }
    raw["risk"]["max_position_weight"] = 1.0
    raw["data"] = {"source": "alpaca", "symbol": "QQQ", "feed": "iex"}
    draft.write_text(yaml.safe_dump(raw), encoding="utf-8")
    active = activate_strategy(
        draft,
        sample_workspace,
        paper_auto=True,
        allow_paper_auto=True,
        data_source="alpaca",
    )

    called = {}

    def fake_dataset(**kwargs):
        called.update(kwargs)
        raise RuntimeError("stop after symbol resolution")

    monkeypatch.setattr("open_composer.runner.paper.load_beta_router_dataset", fake_dataset)

    try:
        run_paper_cycle(active, sample_workspace, with_review=False)
    except RuntimeError as exc:
        assert "stop after symbol resolution" in str(exc)
    else:
        raise AssertionError("fake dataset should stop the paper cycle")

    assert called["market_symbol"] == "QQQ"
    assert called["leverage_symbol"] == "QLD"
    assert called["hedge_symbol"] == "QID"


def test_paper_runner_blocks_when_kill_switch_enabled(sample_workspace: Path, monkeypatch) -> None:
    monkeypatch.setenv("ALPACA_API_KEY_ID", "key")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "secret")
    monkeypatch.setenv("ALPACA_PAPER", "true")
    active = activate_strategy(
        sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml",
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
