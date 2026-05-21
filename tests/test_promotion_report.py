from __future__ import annotations

import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from open_composer.cli import app


def test_strategy_promotion_report_writes_promotion_artifacts(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    comparison_path = (
        sample_workspace / "reports" / "data" / "comparisons" / "qqq_15m_alpaca_vs_longbridge.json"
    )
    comparison_path.parent.mkdir(parents=True, exist_ok=True)
    comparison_path.write_text(
        json.dumps(
            {
                "symbol": "QQQ",
                "timeframe": "15m",
                "left_source": "alpaca",
                "right_source": "longbridge",
                "left_feed": "iex",
                "right_feed": "nasdaq_basic",
                "left_rows": 10,
                "right_rows": 10,
                "matched_rows": 10,
                "missing_left_rows": 0,
                "missing_right_rows": 0,
                "matched_coverage_pct": 100.0,
                "max_abs_close_diff": 0.0,
                "mean_abs_close_diff": 0.0,
                "max_abs_close_diff_bps": 0.0,
                "mean_abs_close_diff_bps": 0.0,
                "max_abs_volume_diff": 0.0,
                "max_volume_diff_ratio": 0.0,
                "first_matched_timestamp": "2026-01-02T14:30:00+00:00",
                "last_matched_timestamp": "2026-01-02T16:00:00+00:00",
                "sample_missing_left_timestamps": [],
                "sample_missing_right_timestamps": [],
                "left_manifest_path": "data/cache/manifests/qqq_15m_alpaca_iex.json",
                "right_manifest_path": "data/cache/manifests/qqq_15m_longbridge_nasdaq_basic.json",
                "caveats": ["fixture replay"],
                "report_json_path": "reports/data/comparisons/qqq_15m_alpaca_vs_longbridge.json",
                "report_markdown_path": "reports/data/comparisons/qqq_15m_alpaca_vs_longbridge.md",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("open_composer.cli.project_root", lambda: sample_workspace)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "strategy",
            "promotion-report",
            str(sample_workspace / "strategy_specs" / "drafts" / "qqq_pullback_15m.yaml"),
            "--oos-ratio",
            "0.3",
            "--walk-forward-folds",
            "3",
            "--cost-slippage-bps",
            "0",
            "--cost-slippage-bps",
            "5",
        ],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "Promotion Report" in result.output

    json_path = sample_workspace / "reports" / "research" / "qqq_pullback_15m-promotion.json"
    report_path = sample_workspace / "reports" / "research" / "qqq_pullback_15m-promotion.md"
    assert json_path.exists()
    assert report_path.exists()

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["status"] == "blocked"
    assert payload["ready"] is False
    assert payload["checks"]
    assert {item["name"] for item in payload["checks"]} == {
        "in_sample",
        "out_of_sample",
        "walk_forward",
        "cost_sensitivity",
        "data_comparison",
        "strict_data",
        "feature_packets",
        "factor_lab",
        "execution_reality",
        "alternative_data",
        "benchmark_family",
        "harness_artifacts",
        "research_design",
    }
    assert payload["gate_summary"]["workflow_pass"] is True
    assert payload["gate_summary"]["research_pass"] is False
    assert payload["gate_summary"]["paper_ready_pass"] is False
    assert payload["five_pass_checks"]["workflow_pass"] == "pass"
    assert payload["five_pass_checks"]["research_pass"] == "fail"
    assert payload["five_pass_checks"]["llm_contribution_pass"] == "not_applicable"
    assert payload["five_pass_checks"]["paper_ready_pass"] == "fail"
    assert payload["five_pass_checks"]["expression_safety_pass"] == "pass"
    assert payload["benchmark_family"]["benchmarks"]["same_symbol_buy_hold"]["status"] == "ok"
    assert payload["benchmark_family"]["benchmarks"]["market_proxy"]["status"] == "not_applicable"
    assert payload["data_profile"]["source_mode"] == "sample"
    assert payload["research_manifest"]["trial_count"] >= 1
    assert payload["research_manifest"]["spec_hash"]
    assert payload["research_manifest"]["research_contract_path"]
    assert payload["research_manifest"]["factor_lab_path"]
    assert payload["research_manifest"]["alt_data_quality_path"]
    assert payload["research_run_index_record"]["kind"] == "promotion"
    assert (
        payload["research_run_index_record"]["trial_count"]
        == payload["research_manifest"]["trial_count"]
    )
    index_path = sample_workspace / "reports" / "research" / "index.jsonl"
    assert index_path.exists()
    index_rows = [json.loads(line) for line in index_path.read_text(encoding="utf-8").splitlines()]
    assert index_rows[0]["kind"] == "promotion"
    walk_forward = next(item for item in payload["checks"] if item["name"] == "walk_forward")
    assert walk_forward["details"]["purged"] is True
    assert walk_forward["details"]["embargo_bars"] == 1
    assert payload["data_comparisons"]
    assert payload["out_of_sample"] is not None
    assert "buy_hold_return_pct" in payload["full_window"]
    assert "alpha_vs_buy_hold_pct" in payload["full_window"]
    assert payload["walk_forward"]
    assert payload["cost_sensitivity"]
    text = report_path.read_text(encoding="utf-8")
    assert "## Checks" in text
    assert "## Out Of Sample" in text
    assert "Alpha vs Buy/Hold" in text
    assert "## Walk Forward" in text
    assert "## Cost Sensitivity" in text
    assert "## Data Comparisons" in text
    assert "## Benchmark Family" in text
    assert "## Research Manifest" in text
    assert "workflow_pass" in text
    assert "## Five-Pass Checks" in text
    assert "| research_pass | FAIL `fail`" in text
    assert "| llm_contribution_pass | N/A `not_applicable`" in text


def test_promotion_report_renders_five_pass_table(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr("open_composer.cli.project_root", lambda: sample_workspace)

    result = CliRunner().invoke(
        app,
        [
            "strategy",
            "promotion-report",
            str(sample_workspace / "strategy_specs" / "drafts" / "qqq_pullback_15m.yaml"),
        ],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    report_path = sample_workspace / "reports" / "research" / "qqq_pullback_15m-promotion.md"
    text = report_path.read_text(encoding="utf-8")
    assert "## Five-Pass Checks" in text
    assert "| workflow_pass | PASS `pass`" in text
    assert "| paper_ready_pass | FAIL `fail`" in text


def test_promotion_report_marks_llm_contribution_not_applicable(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr("open_composer.cli.project_root", lambda: sample_workspace)

    result = CliRunner().invoke(
        app,
        [
            "strategy",
            "promotion-report",
            str(sample_workspace / "strategy_specs" / "drafts" / "qqq_pullback_15m.yaml"),
        ],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    json_path = sample_workspace / "reports" / "research" / "qqq_pullback_15m-promotion.json"
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["five_pass_checks"]["llm_contribution_pass"] == "not_applicable"


def test_adaptive_router_promotion_report_uses_router_research_artifacts(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "adaptive_router_promotion.yaml"
    selected_label = (
        "open_reversal:lb10_entry5_top1_open0_mom0_rv0.8_qprior_negative_"
        "reversal_maxopen-0.2_maxmomnone__"
        "open_momentum:lb10_entry5_top1_open0_mom0_rv0.8_qprior_negative"
    )
    raw = yaml.safe_load(
        (sample_workspace / "strategy_specs" / "drafts" / "qqq_pullback_15m.yaml").read_text(
            encoding="utf-8"
        )
    )
    raw["name"] = "adaptive_router_promotion"
    raw["timeframe"] = "1m"
    raw["universe"] = ["AAPL", "MSFT", "NVDA"]
    raw["data"] = {"source": "alpaca", "symbol": "AAPL", "feed": "iex"}
    raw["llm_review"] = {"enabled": True, "model": "gpt-5.5"}
    raw["required_capabilities"] = ["market.alpaca_bars", "news.gdelt"]
    raw["portfolio"] = {
        "mode": "adaptive_intraday_internal_router",
        "max_symbols_per_day": 1,
        "gross_exposure_limit": 0.15,
        "max_symbol_weight": 0.15,
        "same_day_flatten": True,
        "selected_route_label": selected_label,
    }
    raw["factors"] = {
        "news_sentiment_gate": {
            "source": "feature_packet",
            "path": "feature_logs/adaptive_router_promotion_news.jsonl",
            "field": "sentiment_score",
        }
    }
    spec_path.write_text(yaml.safe_dump(raw), encoding="utf-8")

    research_json = (
        sample_workspace
        / "reports"
        / "research"
        / ("adaptive_router_promotion-adaptive-intraday-router.json")
    )
    research_json.write_text(
        json.dumps(
            {
                "data_profile": {
                    "source_mode": "cache",
                    "data_as_of": "2026-05-15T20:00:00+00:00",
                    "warnings": ["cache_data_used", "iex_feed_not_full_market_sip"],
                },
                "pass_status": {
                    "workflow_pass": True,
                    "research_pass": False,
                    "llm_contribution_pass": False,
                    "paper_ready_pass": False,
                },
                "acceptance_gate": {
                    "passed": False,
                    "oos_sharpe_ratio": 1.43,
                    "oos_traded_days": 63,
                    "walk_forward_fold_count": 2,
                    "walk_forward_positive_alpha_folds": 1,
                    "quality_flags": ["does_not_beat_ex_post_best_symbol"],
                },
                "research_cost": {"estimated_total_backtest_passes": 58},
                "candidates": [
                    {
                        "rank": 2,
                        "score": 9.3,
                        "route": {"label": selected_label},
                        "quality_flags": ["does_not_beat_ex_post_best_symbol"],
                        "out_of_sample": {
                            "total_return_pct": 18.7,
                            "annualized_return_pct": 33.5,
                            "sharpe_ratio": 1.43,
                            "max_drawdown_pct": -8.9,
                            "traded_days": 63,
                            "benchmark_symbol": "TQQQ",
                            "benchmark_buy_hold_return_pct": -30.6,
                            "benchmark_intraday_return_pct": -14.0,
                            "universe_equal_weight_buy_hold_pct": 17.4,
                            "alpha_vs_equal_weight_annualized_pct": 41.0,
                            "best_symbol": "AMAT",
                            "best_symbol_buy_hold_pct": 97.8,
                        },
                        "full_window": {
                            "total_return_pct": 37.1,
                            "benchmark_symbol": "TQQQ",
                            "universe_equal_weight_buy_hold_pct": 35.2,
                            "best_symbol": "AMD",
                            "best_symbol_buy_hold_pct": 153.8,
                        },
                    }
                ],
                "walk_forward": [{"fold": 1}, {"fold": 2}],
            }
        ),
        encoding="utf-8",
    )
    llm_json = (
        sample_workspace
        / "reports"
        / "research"
        / ("adaptive_router_promotion-llm-adaptive-router.json")
    )
    llm_json.write_text(
        json.dumps(
            {
                "status": "written",
                "selected": {"route": {"label": selected_label}},
                "choice": {"selected_label": selected_label, "confidence": 0.78},
                "pass_status": {"llm_contribution_pass": True},
                "llm_contribution": {
                    "selected_prompt_rank": 2,
                    "llm_contribution_ok": True,
                },
            }
        ),
        encoding="utf-8",
    )
    feature_path = sample_workspace / "feature_logs" / "adaptive_router_promotion_news.jsonl"
    feature_path.write_text(
        (
            '{"timestamp":"2026-01-02T20:00:00Z","published_at":"2026-01-02T14:20:00Z",'
            '"fetched_at":"2026-01-02T14:25:00Z","visible_at":"2026-01-02T14:25:00Z",'
            '"source":"adaptive_router_news_replay","symbol":"AAPL",'
            '"dedupe_key":"adaptive_news:promotion:2026-01-02:AAPL","schema_version":"1",'
            '"model":"local-rule-news-v1","input_hash":"sha256:abc","prompt_hash":"sha256:def",'
            '"features":{"sentiment_score":0.0},'
            '"evidence":{"single_modality_baseline_metric":"baseline_oos_alpha=198.8",'
            '"marginal_lift_metric":"lift=0.0",'
            '"missing_modality_robustness":"missing_news_oos_alpha=198.8",'
            '"fixture_path":"reports/research/adaptive_router_promotion-llm-adaptive-router.json"}}\n'
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("open_composer.cli.project_root", lambda: sample_workspace)

    result = CliRunner().invoke(
        app,
        ["strategy", "promotion-report", str(spec_path)],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    json_path = (
        sample_workspace / "reports" / "research" / "adaptive_router_promotion-promotion.json"
    )
    report_path = json_path.with_suffix(".md")
    payload = json.loads(json_path.read_text(encoding="utf-8"))

    assert report_path.exists()
    assert payload["mode"] == "adaptive_intraday_router_promotion"
    assert payload["status"] == "blocked"
    assert payload["ready"] is False
    assert payload["selected_route"]["route"]["label"] == selected_label
    assert payload["five_pass_checks"]["workflow_pass"] == "pass"
    assert payload["five_pass_checks"]["llm_contribution_pass"] == "pass"
    assert payload["gate_summary"]["paper_ready_pass"] is False
    check_names = {item["name"] for item in payload["checks"]}
    assert {
        "strict_data",
        "feature_packets",
        "benchmark_family",
        "execution_reality",
    } <= check_names
    assert payload["research_manifest"]["adaptive_router_research_path"].endswith(
        "adaptive_router_promotion-adaptive-intraday-router.json"
    )
    assert "adaptive_intraday_router_promotion" in report_path.read_text(encoding="utf-8")


def test_hybrid_router_promotion_report_uses_hybrid_research_artifacts(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "hybrid_router_promotion.yaml"
    selected_label = "open_to_open:lb20_top1_qsm100_min5_w1"
    raw = yaml.safe_load(
        (sample_workspace / "strategy_specs" / "drafts" / "qqq_pullback_15m.yaml").read_text(
            encoding="utf-8"
        )
    )
    raw["name"] = "hybrid_router_promotion"
    raw["timeframe"] = "1m"
    raw["universe"] = ["AAPL", "MSFT", "NVDA"]
    raw["data"] = {"source": "alpaca", "symbol": "AAPL", "feed": "iex"}
    raw["llm_review"] = {"enabled": True, "model": "gpt-5.5"}
    raw["required_capabilities"] = ["market.alpaca_bars", "news.gdelt"]
    raw["risk"]["max_position_weight"] = 1.0
    raw["portfolio"] = {
        "mode": "hybrid_adaptive_router",
        "max_symbols_per_day": 1,
        "gross_exposure_limit": 1.0,
        "max_symbol_weight": 1.0,
        "same_day_flatten": False,
        "selected_route_label": selected_label,
    }
    raw["factors"] = {
        "news_sentiment_gate": {
            "source": "feature_packet",
            "path": "feature_logs/hybrid_router_promotion_news.jsonl",
            "field": "sentiment_score",
        }
    }
    spec_path.write_text(yaml.safe_dump(raw), encoding="utf-8")

    research_json = (
        sample_workspace
        / "reports"
        / "research"
        / "hybrid_router_promotion-hybrid-adaptive-router.json"
    )
    research_json.parent.mkdir(parents=True, exist_ok=True)
    research_json.write_text(
        json.dumps(
            {
                "data_profile": {
                    "source_mode": "cache",
                    "data_as_of": "2026-05-15T20:00:00+00:00",
                    "warnings": ["cache_data_used", "iex_feed_not_full_market_sip"],
                },
                "pass_status": {
                    "workflow_pass": True,
                    "research_pass": True,
                    "llm_contribution_pass": False,
                    "paper_ready_pass": False,
                },
                "acceptance_gate": {
                    "passed": True,
                    "train_alpha_vs_tqqq_buy_hold_annualized_pct": 103.5,
                    "oos_alpha_vs_tqqq_buy_hold_annualized_pct": 198.8,
                    "full_alpha_vs_tqqq_buy_hold_annualized_pct": 149.2,
                    "oos_sharpe_ratio": 2.15,
                    "oos_traded_days": 105,
                    "oos_max_drawdown_pct": -15.9,
                    "walk_forward_fold_count": 3,
                    "walk_forward_positive_alpha_folds": 3,
                    "quality_flags": [],
                },
                "research_cost": {"estimated_total_backtest_passes": 186},
                "candidates": [
                    {
                        "rank": 1,
                        "score": 200.5,
                        "params": {
                            "holding_mode": "open_to_open",
                            "momentum_lookback_days": 20,
                            "top_n": 1,
                            "market_sma_days": 100,
                            "min_momentum_pct": 5.0,
                            "max_position_weight": 1.0,
                        },
                        "quality_flags": [],
                        "out_of_sample": {
                            "total_return_pct": 74.7,
                            "annualized_return_pct": 157.0,
                            "sharpe_ratio": 2.15,
                            "max_drawdown_pct": -15.9,
                            "traded_days": 105,
                            "benchmark_symbol": "TQQQ",
                            "benchmark_buy_hold_return_pct": -24.0,
                            "benchmark_buy_hold_annualized_pct": -41.7,
                            "alpha_vs_benchmark_buy_hold_annualized_pct": 198.8,
                            "market_symbol": "QQQ",
                            "market_buy_hold_return_pct": 12.0,
                            "alpha_vs_market_buy_hold_annualized_pct": 125.2,
                            "equal_weight_buy_hold_return_pct": 31.0,
                            "alpha_vs_equal_weight_buy_hold_annualized_pct": 70.0,
                            "best_symbol": "AMAT",
                            "best_symbol_buy_hold_pct": 99.9,
                        },
                        "full_window": {
                            "total_return_pct": 335.8,
                            "annualized_return_pct": 154.0,
                            "benchmark_symbol": "TQQQ",
                            "benchmark_buy_hold_return_pct": 9.0,
                            "benchmark_buy_hold_annualized_pct": 4.8,
                            "alpha_vs_benchmark_buy_hold_annualized_pct": 149.2,
                            "market_symbol": "QQQ",
                            "market_buy_hold_return_pct": 40.0,
                            "alpha_vs_market_buy_hold_annualized_pct": 126.5,
                            "equal_weight_buy_hold_return_pct": 80.0,
                            "equal_weight_buy_hold_annualized_pct": 34.0,
                            "best_symbol": "AMD",
                            "best_symbol_buy_hold_pct": 164.9,
                        },
                    }
                ],
                "walk_forward": [{"fold": 1}, {"fold": 2}, {"fold": 3}],
            }
        ),
        encoding="utf-8",
    )
    feature_path = sample_workspace / "feature_logs" / "hybrid_router_promotion_news.jsonl"
    feature_path.write_text(
        (
            '{"timestamp":"2026-01-02T20:00:00Z","published_at":"2026-01-02T14:20:00Z",'
            '"fetched_at":"2026-01-02T14:25:00Z","visible_at":"2026-01-02T14:25:00Z",'
            '"source":"hybrid_router_news_replay","symbol":"AAPL",'
            '"dedupe_key":"hybrid_news:promotion:2026-01-02:AAPL","schema_version":"1",'
            '"model":"local-rule-news-v1","input_hash":"sha256:abc","prompt_hash":"sha256:def",'
            '"features":{"sentiment_score":0.0},'
            '"evidence":{"single_modality_baseline_metric":"baseline_oos_alpha=198.8",'
            '"marginal_lift_metric":"lift=0.0",'
            '"missing_modality_robustness":"missing_news_oos_alpha=198.8",'
            '"fixture_path":"reports/research/hybrid_router_promotion-news-marginal-lift.json"}}\n'
        ),
        encoding="utf-8",
    )
    news_lift_json = (
        sample_workspace
        / "reports"
        / "research"
        / "hybrid_router_promotion-news-marginal-lift.json"
    )
    news_lift_json.write_text(
        json.dumps(
            {
                "marginal_lift": {
                    "llm_contribution_pass": False,
                    "alpha_vs_tqqq_annualized_pct": 0.0,
                    "interpretation": "No independent LLM/news Alpha is evidenced.",
                },
                "feature_packets": {"path": "feature_logs/hybrid_router_promotion_news.jsonl"},
            }
        ),
        encoding="utf-8",
    )
    execution_json = (
        sample_workspace / "reports" / "execution" / "hybrid_router_promotion-target-weights.json"
    )
    execution_json.parent.mkdir(parents=True, exist_ok=True)
    execution_json.write_text(
        json.dumps(
            {
                "summary": {
                    "rebalance_sessions": 398,
                    "target_weight_rows": 1194,
                    "nonzero_target_rows": 303,
                    "max_gross_exposure": 1.0,
                },
                "parity_check": {
                    "status": "pass",
                    "blockers": [],
                    "warnings": ["manual_signal mapping only"],
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("open_composer.cli.project_root", lambda: sample_workspace)

    result = CliRunner().invoke(
        app,
        ["strategy", "promotion-report", str(spec_path)],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    json_path = sample_workspace / "reports" / "research" / "hybrid_router_promotion-promotion.json"
    report_path = json_path.with_suffix(".md")
    payload = json.loads(json_path.read_text(encoding="utf-8"))

    assert report_path.exists()
    assert payload["mode"] == "hybrid_adaptive_router_promotion"
    assert payload["status"] == "blocked"
    assert payload["ready"] is False
    assert payload["selected_route"]["params"]["market_sma_days"] == 100
    assert payload["five_pass_checks"]["workflow_pass"] == "pass"
    assert payload["five_pass_checks"]["llm_contribution_pass"] == "fail"
    assert payload["gate_summary"]["paper_ready_pass"] is False
    check_names = {item["name"] for item in payload["checks"]}
    assert {"hybrid_router_research", "out_of_sample", "benchmark_family"} <= check_names
    llm_check = next(item for item in payload["checks"] if item["name"] == "llm_contribution")
    assert llm_check["status"] == "warning"
    execution_check = next(
        item for item in payload["checks"] if item["name"] == "execution_reality"
    )
    assert execution_check["details"]["target_weight_mapping_status"] == "pass"
    assert (
        "hybrid router needs Nautilus target-weight mapping"
        not in execution_check["details"]["blockers"]
    )
    assert payload["research_manifest"]["hybrid_router_research_path"].endswith(
        "hybrid_router_promotion-hybrid-adaptive-router.json"
    )
    assert "hybrid_adaptive_router_promotion" in report_path.read_text(encoding="utf-8")


def test_beta_router_promotion_report_uses_beta_research_artifacts(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "beta_router_promotion.yaml"
    selected_label = (
        "beta:sma200_mom120_min0_vol20_maxvnone_dd120_maxddnone_"
        "levsma50_levmaxvnone_levdd60_levmaxdd25_onTQQQ1_neuQQQ1_offCASH0_vtnone"
    )
    raw = yaml.safe_load(
        (sample_workspace / "strategy_specs" / "drafts" / "qqq_pullback_15m.yaml").read_text(
            encoding="utf-8"
        )
    )
    raw["name"] = "beta_router_promotion"
    raw["timeframe"] = "daily"
    raw["universe"] = ["QQQ", "TQQQ", "SQQQ"]
    raw["data"] = {"source": "alpaca", "symbol": "QQQ", "feed": "iex"}
    raw["llm_review"] = {"enabled": False, "model": None}
    raw["required_capabilities"] = ["market.alpaca_bars"]
    raw["risk"]["max_position_weight"] = 1.0
    raw["portfolio"] = {
        "mode": "beta_exposure_router",
        "max_symbols_per_day": 1,
        "gross_exposure_limit": 1.0,
        "max_symbol_weight": 1.0,
        "same_day_flatten": False,
        "selected_route_label": selected_label,
    }
    raw["factors"] = {}
    spec_path.write_text(yaml.safe_dump(raw), encoding="utf-8")

    research_json = (
        sample_workspace
        / "reports"
        / "research"
        / ("beta_router_promotion-beta-exposure-router.json")
    )
    research_json.parent.mkdir(parents=True, exist_ok=True)
    research_json.write_text(
        json.dumps(
            {
                "data_profile": {
                    "source_mode": "cache",
                    "data_as_of": "2026-05-15T20:00:00+00:00",
                    "warnings": ["cache_data_used", "iex_feed_not_full_market_sip"],
                },
                "pass_status": {
                    "workflow_pass": True,
                    "research_pass": True,
                    "llm_contribution_pass": False,
                    "paper_ready_pass": False,
                },
                "acceptance_gate": {
                    "passed": True,
                    "train_alpha_vs_qqq_annualized_pct": 25.3,
                    "oos_alpha_vs_qqq_annualized_pct": 30.8,
                    "full_alpha_vs_qqq_annualized_pct": 27.6,
                    "oos_sharpe_ratio": 1.47,
                    "oos_max_drawdown_pct": -28.4,
                    "walk_forward_fold_count": 5,
                    "walk_forward_positive_alpha_folds": 4,
                    "quality_flags": [],
                },
                "research_cost": {"candidate_count": 96},
                "candidates": [
                    {
                        "rank": 1,
                        "score": 44.5,
                        "params": {"label": selected_label},
                        "quality_flags": [],
                        "out_of_sample": {
                            "annualized_return_pct": 60.38,
                            "sharpe_ratio": 1.47,
                            "max_drawdown_pct": -28.38,
                            "market_symbol": "QQQ",
                            "market_buy_hold_return_pct": 48.2,
                            "alpha_vs_market_buy_hold_annualized_pct": 30.8,
                            "leverage_symbol": "TQQQ",
                            "leverage_buy_hold_return_pct": 12.0,
                            "alpha_vs_leverage_buy_hold_annualized_pct": 52.2,
                            "total_return_pct": 98.3,
                        },
                        "full_window": {
                            "annualized_return_pct": 59.47,
                            "sharpe_ratio": 1.45,
                            "max_drawdown_pct": -29.48,
                            "market_symbol": "QQQ",
                            "market_buy_hold_return_pct": 167.1,
                            "market_buy_hold_annualized_pct": 31.9,
                            "alpha_vs_market_buy_hold_annualized_pct": 27.6,
                            "leverage_symbol": "TQQQ",
                            "leverage_buy_hold_return_pct": 250.0,
                            "leverage_buy_hold_annualized_pct": 48.5,
                            "alpha_vs_leverage_buy_hold_annualized_pct": 11.0,
                            "total_return_pct": 420.0,
                        },
                    }
                ],
                "walk_forward": [{"fold": 1}, {"fold": 2}, {"fold": 3}, {"fold": 4}, {"fold": 5}],
            }
        ),
        encoding="utf-8",
    )
    execution_json = (
        sample_workspace
        / "reports"
        / "execution"
        / ("beta_router_promotion-beta-target-weights.json")
    )
    execution_json.parent.mkdir(parents=True, exist_ok=True)
    execution_json.write_text(
        json.dumps(
            {
                "summary": {
                    "rebalance_sessions": 894,
                    "target_weight_rows": 2682,
                    "nonzero_target_rows": 767,
                    "max_gross_exposure": 1.0,
                },
                "parity_check": {
                    "status": "pass",
                    "blockers": [],
                    "warnings": ["manual_signal mapping only"],
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("open_composer.cli.project_root", lambda: sample_workspace)

    result = CliRunner().invoke(
        app,
        ["strategy", "promotion-report", str(spec_path)],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    json_path = sample_workspace / "reports" / "research" / "beta_router_promotion-promotion.json"
    report_path = json_path.with_suffix(".md")
    payload = json.loads(json_path.read_text(encoding="utf-8"))

    assert report_path.exists()
    assert payload["mode"] == "beta_exposure_router_promotion"
    assert payload["status"] == "blocked"
    assert payload["ready"] is False
    assert payload["selected_route"]["params"]["label"] == selected_label
    assert payload["five_pass_checks"]["workflow_pass"] == "pass"
    assert payload["five_pass_checks"]["llm_contribution_pass"] == "not_applicable"
    assert payload["gate_summary"]["paper_ready_pass"] is False
    check_names = {item["name"] for item in payload["checks"]}
    assert {"beta_router_research", "out_of_sample", "benchmark_family"} <= check_names
    execution_check = next(
        item for item in payload["checks"] if item["name"] == "execution_reality"
    )
    assert execution_check["details"]["target_weight_mapping_status"] == "pass"
    assert (
        "beta router needs Nautilus target-weight mapping"
        not in execution_check["details"]["blockers"]
    )
    assert payload["research_manifest"]["beta_router_research_path"].endswith(
        "beta_router_promotion-beta-exposure-router.json"
    )
    assert "beta_exposure_router_promotion" in report_path.read_text(encoding="utf-8")
