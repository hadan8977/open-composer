from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from open_composer.dashboard import (
    build_dashboard_catalog,
    write_dashboard_catalog,
    write_dashboard_html,
    write_dashboard_review_markdown,
)
from open_composer.engines.backtest_engine import run_backtest
from open_composer.journal.writer import add_journal_entry
from open_composer.models.paper import PaperOrderRecord
from open_composer.models.review_card import ReviewCard
from open_composer.paper_readiness import (
    assess_paper_strategy_readiness,
    write_paper_readiness_report,
)
from open_composer.storage import append_jsonl, write_json
from open_composer.strategy_lifecycle import activate_strategy, disable_strategy


def test_dashboard_catalog_rebuilds_repo_artifacts(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "open_composer.adapters.execution.nautilus_trader.nautilus_trader_available",
        lambda: True,
    )
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"
    backtest = run_backtest(spec_path, root=sample_workspace)
    signal = backtest.signals[0]

    write_json(
        sample_workspace / "reports" / "reviews" / f"{signal.id}.json",
        ReviewCard(
            signal_id=signal.id,
            strategy_name=signal.strategy_name,
            symbol=signal.symbol,
            timestamp=signal.timestamp.isoformat(),
            verdict="consider",
            confidence=0.5,
            catalyst="test catalyst",
            evidence=["bar-close confirmation"],
            risks=["sample data only"],
            invalidation=["close below entry structure"],
            action_suggestion="observe only",
            model="mock",
            created_at=datetime.now(UTC),
        ),
    )
    write_json(
        sample_workspace / "reports" / "context" / f"{signal.id}.json",
        {
            "signal_id": signal.id,
            "symbol": signal.symbol,
            "generated_at": signal.timestamp.isoformat(),
            "events": [{"id": "evt_1"}],
            "macro": [],
            "news": [],
            "notes": ["test context"],
        },
    )
    add_journal_entry(sample_workspace, signal.id, "watched", "checked", "queued")
    append_jsonl(
        sample_workspace / "reports" / "paper" / "orders.jsonl",
        [
            PaperOrderRecord(
                id="paper_order_1",
                signal_id=signal.id,
                client_order_id="client_order_1",
                strategy_name=signal.strategy_name,
                symbol=signal.symbol,
                side=signal.side,
                qty=1.0,
                status="submitted",
                submitted_at=signal.timestamp,
            )
        ],
    )
    write_json(
        sample_workspace / "reports" / "data" / "comparisons" / "qqq_15m_alpaca_vs_longbridge.json",
        {
            "symbol": "QQQ",
            "timeframe": "15m",
            "left_source": "alpaca",
            "right_source": "longbridge",
            "left_feed": "iex",
            "right_feed": "nasdaq_basic",
            "left_rows": 10,
            "right_rows": 7,
            "matched_rows": 7,
            "missing_left_rows": 0,
            "missing_right_rows": 3,
            "matched_coverage_pct": 70.0,
            "max_abs_close_diff": 0.0,
            "mean_abs_close_diff": 0.0,
            "max_abs_close_diff_bps": 0.0,
            "mean_abs_close_diff_bps": 0.0,
            "max_abs_volume_diff": 0.0,
            "max_volume_diff_ratio": 0.0,
            "first_matched_timestamp": "2026-01-02T14:30:00+00:00",
            "last_matched_timestamp": "2026-01-02T16:00:00+00:00",
            "sample_missing_left_timestamps": [],
            "sample_missing_right_timestamps": ["2026-01-02T16:15:00+00:00"],
            "left_manifest_path": "data/cache/manifests/qqq_15m_alpaca_iex.json",
            "right_manifest_path": "data/cache/manifests/qqq_15m_longbridge_nasdaq_basic.json",
            "caveats": ["fixture replay"],
            "report_json_path": "reports/data/comparisons/qqq_15m_alpaca_vs_longbridge.json",
            "report_markdown_path": "reports/data/comparisons/qqq_15m_alpaca_vs_longbridge.md",
        },
    )
    feature_path = sample_workspace / "feature_logs" / "qqq_llm_features.jsonl"
    feature_path.write_text(
        (
            '{"timestamp":"2026-01-02T14:30:00Z","llm_sentiment_score":0.8,"llm_regime":"risk_on"}\n'
            '{"timestamp":"2026-01-02T14:45:00Z","llm_sentiment_score":0.6,"llm_regime":"risk_on"}\n'
        ),
        encoding="utf-8",
    )
    readiness = assess_paper_strategy_readiness(spec_path, sample_workspace)
    write_paper_readiness_report(readiness, sample_workspace)
    workflow_json = sample_workspace / "reports" / "workflows" / "fixture_pullback_15m.verify.json"
    workflow_md = workflow_json.with_suffix(".md")
    write_json(
        workflow_json,
        {
            "strategy_name": "fixture_pullback_15m",
            "source_path": "strategy_specs/drafts/fixture_pullback_15m.yaml",
            "spec_hash": "abc123",
            "status": "warning",
            "backtest_run_id": backtest.run.run_id,
            "scan_signal_count": 2,
            "paper_readiness_status": "blocked",
            "paper_ready": False,
            "output_paths": [
                "reports/specs/fixture_pullback_15m.validation.json",
                f"reports/backtests/{backtest.run.run_id}.md",
            ],
        },
    )
    workflow_md.write_text("# workflow verification\n", encoding="utf-8")
    write_json(
        sample_workspace / "reports" / "research" / "fixture_pullback_15m-promotion.json",
        {
            "strategy_name": "fixture_pullback_15m",
            "source_spec_path": "strategy_specs/active/fixture_pullback_15m.yaml",
            "status": "ok",
            "ready": True,
            "gate_summary": {
                "workflow_pass": True,
                "research_pass": True,
                "llm_contribution_pass": None,
                "paper_ready_pass": True,
                "blocked_checks": [],
                "warning_checks": [],
                "benchmark_family_complete": True,
            },
            "data_profile": {
                "data_as_of": "2026-01-02T16:00:00+00:00",
                "feed": "iex",
                "source_mode": "cache",
                "cache_fallback": True,
                "warnings": ["cache_data_used"],
            },
            "checks": [
                {"name": "in_sample", "status": "ok", "message": "ok", "details": {}},
                {"name": "strict_data", "status": "ok", "message": "ok", "details": {}},
                {"name": "feature_packets", "status": "ok", "message": "ok", "details": {}},
                {"name": "benchmark_family", "status": "ok", "message": "ok", "details": {}},
            ],
            "benchmark_family": {"complete": True, "missing": [], "benchmarks": {}},
            "full_window": {
                "run_id": "promo_full",
                "bars": 10,
                "signals": 2,
                "trades": 1,
                "total_return_pct": 1.0,
                "annualized_return_pct": 2.0,
                "sharpe_ratio": 1.0,
                "data_sanity_status": "ok",
                "evidence_level": "E1_single_source_research",
            },
        },
    )
    append_jsonl(
        sample_workspace / "reports" / "research" / "index.jsonl",
        [
            {
                "run_id": "research-fixture_pullback_15m-fixture",
                "generated_at": "2026-05-12T10:02:00Z",
                "strategy_name": "fixture_pullback_15m",
                "source_spec_path": "strategy_specs/drafts/fixture_pullback_15m.yaml",
                "spec_hash": "abc123",
                "status": "blocked",
                "kind": "research_report",
                "data_profile": {
                    "source_mode": "sample",
                    "data_as_of": "2026-01-02T16:00:00+00:00",
                },
                "candidate_count": 3,
                "trial_count": 2,
                "runtime_seconds": 1.25,
                "gate_status": "blocked",
                "blocked_items": ["paper_gap"],
                "warning_items": ["sample_data"],
                "report_path": "reports/research/fixture_pullback_15m-research-report.md",
                "json_path": "reports/research/fixture_pullback_15m-research-report.json",
                "contract_path": "reports/research/fixture_pullback_15m-research-contract.json",
                "source_artifacts": {
                    "promotion": "reports/research/fixture_pullback_15m-promotion.json"
                },
            }
        ],
    )
    write_json(
        sample_workspace / "reports" / "readiness" / "readiness.json",
        {
            "generated_at": "2026-05-12T10:00:00Z",
            "source_root": str(sample_workspace),
            "status": "warning",
            "ready": True,
            "checks": [
                {
                    "name": "strategy_capabilities",
                    "status": "warning",
                    "message": "Some strategies have degraded backend capability.",
                    "suggested_actions": [
                        (
                            "uv run oc spec capabilities "
                            "strategy_specs/drafts/fixture_pullback_15m.yaml"
                        )
                    ],
                    "details": {"backend_status_counts": {"partial": 1}},
                }
            ],
        },
    )
    (sample_workspace / "reports" / "readiness" / "readiness.md").write_text(
        "# readiness\n", encoding="utf-8"
    )
    write_json(
        sample_workspace / "reports" / "deployment" / "prepare.json",
        {
            "generated_at": "2026-05-12T10:01:00Z",
            "source_root": str(sample_workspace),
            "status": "warning",
            "ready": True,
            "steps": [
                {
                    "name": "paper_monitor",
                    "status": "warning",
                    "message": "Paper monitor refreshed.",
                    "suggested_actions": ["uv run oc paper monitor --sync-broker"],
                    "output_paths": ["reports/paper/monitor.md"],
                    "details": {"sync_status": "skipped"},
                }
            ],
        },
    )
    (sample_workspace / "reports" / "deployment" / "prepare.md").write_text(
        "# deployment\n", encoding="utf-8"
    )

    catalog = build_dashboard_catalog(sample_workspace)
    artifacts = write_dashboard_catalog(catalog, sample_workspace)
    html_path = write_dashboard_html(catalog, sample_workspace)
    review_path = write_dashboard_review_markdown(catalog, root=sample_workspace)

    assert catalog.summary.strategy_count == 1
    assert catalog.summary.version_count == 1
    assert catalog.summary.run_count == 1
    assert catalog.summary.signal_count == len(backtest.signals)
    assert catalog.summary.review_count == 1
    assert catalog.summary.context_count == 1
    assert catalog.summary.journal_count == 1
    assert catalog.summary.order_count == 1
    assert catalog.summary.audit_count == 2
    assert catalog.summary.data_comparison_count == 1
    assert catalog.summary.feature_packet_count == 1
    assert catalog.summary.workflow_report_count == 1
    assert catalog.summary.research_report_count == 1
    assert catalog.summary.research_run_count == 1
    assert catalog.summary.research_blocked_count == 1
    assert catalog.research_runs[0].run_id == "research-fixture_pullback_15m-fixture"
    assert catalog.research_runs[0].candidate_count == 3
    assert catalog.research_runs[0].trial_count == 2
    assert catalog.research_runs[0].blocked_items == ["paper_gap"]
    write_json(
        sample_workspace / "reports" / "research" / "fixture_pullback_15m-geometry-features.json",
        {
            "strategy_name": "fixture_pullback_15m",
            "kind": "geometry_features",
            "status": "blocked",
            "research_only": True,
            "source_spec_path": "strategy_specs/drafts/fixture_pullback_15m.yaml",
            "data_profile": {"source_mode": "sample"},
            "promotion_blockers": ["research_only_feature_family"],
        },
    )
    geometry_catalog = build_dashboard_catalog(sample_workspace)
    assert any(report.kind == "geometry_features" for report in geometry_catalog.research_reports)
    assert catalog.research_reports[0].data_as_of == "2026-01-02T16:00:00+00:00"
    assert catalog.research_reports[0].data_feed == "iex"
    assert catalog.research_reports[0].data_source_mode == "cache"
    assert catalog.research_reports[0].cache_fallback is True
    assert catalog.research_reports[0].data_warnings == ["cache_data_used"]
    assert catalog.research_reports[0].gate_summary["paper_ready_pass"] is True
    assert catalog.research_reports[0].evidence_strength == "paper_ready"
    assert catalog.research_reports[0].benchmark_family_complete is True
    assert catalog.research_reports[0].paper_readiness_status == "ok"
    assert "Review paper readiness" in catalog.research_reports[0].next_action
    assert catalog.summary.readiness_status == "warning"
    assert catalog.summary.readiness_ready is True
    assert catalog.summary.readiness_warning_count == 1
    assert catalog.summary.deployment_status == "warning"
    assert catalog.summary.deployment_ready is True
    assert catalog.summary.deployment_warning_count == 1
    assert catalog.readiness_report is not None
    assert catalog.readiness_report.path == "reports/readiness/readiness.json"
    assert catalog.readiness_report.checks[0].suggested_actions == [
        "uv run oc spec capabilities strategy_specs/drafts/fixture_pullback_15m.yaml"
    ]
    assert catalog.deployment_report is not None
    assert catalog.deployment_report.path == "reports/deployment/prepare.json"
    assert catalog.deployment_report.steps[0].output_paths == ["reports/paper/monitor.md"]
    assert catalog.workflow_reports[0].strategy_name == "fixture_pullback_15m"
    assert catalog.workflow_reports[0].status == "warning"
    assert catalog.workflow_reports[0].backtest_run_id == backtest.run.run_id
    assert catalog.workflow_reports[0].paper_readiness_status == "blocked"
    assert catalog.workflow_reports[0].path == "reports/workflows/fixture_pullback_15m.verify.json"
    assert catalog.workflow_reports[0].report_markdown_path == (
        "reports/workflows/fixture_pullback_15m.verify.md"
    )
    assert catalog.summary.paper_readiness_count == 1
    assert catalog.summary.paper_readiness_status_counts == {"blocked": 1}
    assert catalog.paper_readiness_reports[0].strategy_name == "fixture_pullback_15m"
    assert catalog.paper_readiness_reports[0].status == "blocked"
    assert "lifecycle" in catalog.paper_readiness_reports[0].blocking_checks
    assert catalog.paper_readiness_reports[0].checks[0].suggested_actions
    assert catalog.feature_packets[0].point_in_time_status == "partial"
    assert (
        "published_at is missing for at least one row" in catalog.feature_packets[0].replay_warnings
    )
    assert (
        "schema_version is missing for at least one row"
        in catalog.feature_packets[0].replay_warnings
    )
    assert catalog.feature_packets[0].has_schema_version is False
    assert catalog.summary.strategy_backend_counts == {"python_reference": 1}
    assert catalog.summary.backend_status_counts == {"partial": 1}
    assert catalog.strategies[0].symbol == "QQQ"
    assert catalog.strategies[0].timeframe == "15m"
    assert catalog.strategies[0].universe == ["QQQ"]
    assert catalog.strategies[0].backend == "python_reference"
    assert catalog.strategies[0].backend_status == "partial"
    assert catalog.versions[0].symbol == "QQQ"
    assert catalog.versions[0].universe == ["QQQ"]
    assert catalog.runs[0].strategy_backend == "python_reference"
    assert catalog.runs[0].execution_backend == "python_reference"
    assert catalog.runs[0].buy_hold_return_pct is not None
    assert catalog.runs[0].alpha_vs_buy_hold_pct is not None
    assert catalog.runs[0].annualized_return_pct is not None
    assert catalog.runs[0].sharpe_ratio is not None
    assert catalog.runs[0].data_sanity_status == "warning"
    assert catalog.runs[0].evidence_level == "E0_sample_smoke"
    assert catalog.runs[0].data_sanity_warnings
    assert catalog.orders[0].strategy_backend == "python_reference"
    assert catalog.orders[0].execution_backend == "python_reference"
    assert artifacts.catalog_path.exists()
    assert artifacts.markdown_path.exists()
    assert html_path == sample_workspace / "reports" / "dashboard" / "index.html"
    assert html_path.exists()
    html = html_path.read_text(encoding="utf-8")
    assert "Open Composer Dashboard" in html
    assert "Buy/Hold" in html
    assert "fixture_pullback_15m" in html
    assert "strategies/fixture_pullback_15m.html" in html
    assert "python_reference" in html
    assert "Annualized" in html
    assert "Sharpe" in html
    assert "Evidence" in html
    assert "E0_sample_smoke" in html
    assert "warnings" in html
    assert "reports/dashboard/catalog.json" in html
    assert "Data Quality" in html
    assert "alpaca / longbridge" in html
    assert "Research Evidence" in html
    assert "research-fixture_pullback_15m-fixture" in html
    assert "paper_gap" in html
    assert "LLM Feature Replay" in html
    assert "qqq_llm_features.jsonl" in html
    assert "Deployment Readiness" in html
    assert "uv run oc paper monitor --sync-broker" in html
    assert "uv run oc spec capabilities strategy_specs/drafts/fixture_pullback_15m.yaml" in html
    detail_path = (
        sample_workspace / "reports" / "dashboard" / "strategies" / "fixture_pullback_15m.html"
    )
    assert detail_path.exists()
    detail_html = detail_path.read_text(encoding="utf-8")
    assert "Strategy Profile" in detail_html
    assert "Backend plan" in detail_html
    assert "E0_sample_smoke" in detail_html
    assert "Research Evidence" in detail_html
    assert backtest.run.run_id in detail_html
    assert signal.id in detail_html
    assert review_path == sample_workspace / "reports" / "dashboard" / "review.md"
    assert review_path.exists()


def test_dashboard_catalog_prefers_current_spec_over_stale_active_version(
    sample_workspace: Path,
) -> None:
    draft = sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"
    activate_strategy(draft, sample_workspace)
    draft.unlink()
    retired = disable_strategy("fixture_pullback_15m", sample_workspace)

    catalog = build_dashboard_catalog(sample_workspace)

    strategy = next(
        item for item in catalog.strategies if item.strategy_name == "fixture_pullback_15m"
    )
    assert retired.exists()
    assert strategy.lifecycle == "retired"
    assert strategy.execution_mode == "manual_signal"
    assert strategy.source_paths[0] == "strategy_specs/retired/fixture_pullback_15m.yaml"
