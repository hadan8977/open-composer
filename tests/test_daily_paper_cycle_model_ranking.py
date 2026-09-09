"""Step 11 Wave C item 5: observation-mode wiring in run_daily_paper_cycle.py
for portfolio.mode=model_ranking_portfolio.

These tests exercise only the new orchestration layer added to
scripts/run_daily_paper_cycle.py (dispatch + safety guards + log writing).
The adapter itself (candidate loading, scoring, sizing) is already covered
end-to-end by tests/test_model_ranking_target_weights.py; here the
`oc strategy target-weights` / `oc paper sync-account` subprocess calls are
faked, matching the existing convention in tests/test_daily_paper_cycle.py
for faking `oc run paper`.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from open_composer.models.strategy_spec import StrategySpec
from scripts.run_daily_paper_cycle import (
    _is_model_ranking_portfolio_spec,
    main,
    run_model_ranking_observation_cycle,
)


def _write_model_ranking_spec(
    root: Path,
    repo_root: Path,
    *,
    name: str = "test_model_ranking_observation",
    lifecycle: str = "draft",
    execution_mode: str = "manual_signal",
    execution_broker: str = "none",
) -> Path:
    fixture = (
        repo_root / "tests" / "fixtures" / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"
    )
    raw = yaml.safe_load(fixture.read_text(encoding="utf-8"))
    raw["name"] = name
    raw["timeframe"] = "daily"
    raw["universe"] = ["AAA", "BBB", "CCC"]
    raw["lifecycle"] = lifecycle
    raw["execution"]["mode"] = execution_mode
    raw["execution"]["broker"] = execution_broker
    raw["portfolio"] = {
        "mode": "model_ranking_portfolio",
        "candidate_artifact_dir": "config/model_ranking_candidates/step11_momentum_placeholder_v1",
        "universe_rule": "pit_adv_top_n",
        "universe_top_n": 1500,
        "feature_set_id": "daily_only",
        "label_horizon_days": 21,
        "top_k": 3,
        "rebalance": "weekly_friday_close_monday_open",
        "weighting": "equal_weight",
        "hedge": "none",
    }
    raw["risk"]["max_position_weight"] = 0.5
    raw["data"]["source"] = "alpaca"
    raw["data"]["path"] = None
    raw["data"]["feed"] = "sip"
    path = root / f"{name}.yaml"
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    StrategySpec.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    return path


def _write_target_weights_output(root: Path, name: str) -> None:
    path = root / "reports" / "execution" / f"{name}-target-weights.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "strategy_name": name,
        "portfolio_mode": "model_ranking_portfolio",
        "summary": {
            "is_new_signal": True,
            "nonzero_target_rows": 3,
            "top_k": 3,
            "hedge": "none",
            "idle_cash": 123.45,
            "idle_cash_fraction": 0.0012,
            "weight_deviation": 0.008,
            "unaffordable": [],
            "candidate_is_placeholder": True,
            "account_equity": 100_000.0,
        },
        "target_weights": [
            {"symbol": "AAA", "target_weight": 0.34, "shares": 12, "selected": True},
            {"symbol": "BBB", "target_weight": 0.33, "shares": 9, "selected": True},
            {"symbol": "CCC", "target_weight": 0.33, "shares": 4, "selected": True},
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


class TestIsModelRankingPortfolioSpec:
    def test_true_for_real_draft_spec(self, repo_root: Path) -> None:
        spec_path = (
            repo_root / "strategy_specs" / "drafts" / "us_model_ranking_portfolio_top50.yaml"
        )
        assert _is_model_ranking_portfolio_spec(repo_root, str(spec_path)) is True

    def test_false_for_non_matching_mode(self, repo_root: Path) -> None:
        spec_path = (
            repo_root
            / "tests"
            / "fixtures"
            / "strategy_specs"
            / "drafts"
            / "fixture_pullback_15m.yaml"
        )
        assert _is_model_ranking_portfolio_spec(repo_root, str(spec_path)) is False

    def test_false_for_missing_file_does_not_raise(self, tmp_path: Path) -> None:
        assert _is_model_ranking_portfolio_spec(tmp_path, "does/not/exist.yaml") is False


class TestRunModelRankingObservationCycle:
    def test_success_writes_log_and_never_invokes_run_paper(
        self, tmp_path: Path, repo_root: Path
    ) -> None:
        spec_path = _write_model_ranking_spec(tmp_path, repo_root)
        commands: list[list[str]] = []

        def fake_run(command, **kwargs):
            commands.append(command)
            if "sync-account" in command:
                account_path = tmp_path / "reports" / "paper" / "account.json"
                account_path.parent.mkdir(parents=True, exist_ok=True)
                account_path.write_text(
                    json.dumps({"equity": 100000.0, "cash": 100000.0}), encoding="utf-8"
                )
            if "target-weights" in command:
                _write_target_weights_output(tmp_path, "test_model_ranking_observation")
            return SimpleNamespace(returncode=0, stdout="ok", stderr="")

        payload = run_model_ranking_observation_cycle(
            root=tmp_path,
            spec=str(spec_path),
            cycle_date=date(2026, 9, 8),
            oc_cmd=["oc"],
            command_runner=fake_run,
        )

        assert payload["status"] == "ok"
        assert payload["paper_order_authorization"] is False
        assert payload["broker_writes"] is False
        assert len(commands) == 2
        # The invariant that actually matters: no step ever shells out to
        # `oc run paper`, the only command capable of submitting orders.
        assert not any("run" in command and "paper" in command for command in commands)

        summary = payload["target_weights_summary"]
        assert summary["nonzero_target_rows"] == 3
        assert summary["idle_cash"] == 123.45
        assert summary["candidate_is_placeholder"] is True

        log_path = (
            tmp_path
            / "reports"
            / "paper"
            / "daily_cycle"
            / "test_model_ranking_observation-observation-20260908.json"
        )
        assert log_path.is_file()
        logged = json.loads(log_path.read_text(encoding="utf-8"))
        assert logged["report_type"] == "daily_paper_cycle_observation_only"
        assert logged["paper_order_authorization"] is False

        # Never touches strategy_specs/active/ -- this cycle never "activates" anything.
        assert not (tmp_path / "strategy_specs" / "active").exists()

    def test_skips_non_trading_day(self, tmp_path: Path, repo_root: Path) -> None:
        spec_path = _write_model_ranking_spec(tmp_path, repo_root)

        def fake_run(command, **kwargs):
            raise AssertionError("weekend should not execute any command")

        payload = run_model_ranking_observation_cycle(
            root=tmp_path,
            spec=str(spec_path),
            cycle_date=date(2026, 9, 6),  # Sunday
            oc_cmd=["oc"],
            command_runner=fake_run,
        )

        assert payload["status"] == "skipped"
        assert payload["skip_reason"] == "non_trading_day_weekend"

    @pytest.mark.parametrize(
        ("lifecycle", "execution_mode", "execution_broker", "match"),
        [
            # lifecycle=active is otherwise a valid StrategySpec on its own --
            # this Wave's own guard is the only thing rejecting it.
            ("active", "manual_signal", "none", "draft"),
            # mode=paper_auto/broker=alpaca_paper is the only execution
            # combination other than manual_signal/none that StrategySpec's
            # own cross-field validator accepts (paper_auto <-> alpaca_paper
            # and manual_signal <-> none are the only two valid pairings),
            # so it is the only reachable way to exercise this guard.
            ("draft", "paper_auto", "alpaca_paper", "manual_signal"),
        ],
    )
    def test_refuses_anything_but_draft_manual_signal_broker_none(
        self,
        tmp_path: Path,
        repo_root: Path,
        lifecycle: str,
        execution_mode: str,
        execution_broker: str,
        match: str,
    ) -> None:
        spec_path = _write_model_ranking_spec(
            tmp_path,
            repo_root,
            lifecycle=lifecycle,
            execution_mode=execution_mode,
            execution_broker=execution_broker,
        )

        def fake_run(command, **kwargs):
            raise AssertionError("guard should reject before any command runs")

        with pytest.raises(ValueError, match=match):
            run_model_ranking_observation_cycle(
                root=tmp_path,
                spec=str(spec_path),
                cycle_date=date(2026, 9, 8),
                oc_cmd=["oc"],
                command_runner=fake_run,
            )

    def test_failed_step_short_circuits_and_records_failure(
        self, tmp_path: Path, repo_root: Path
    ) -> None:
        spec_path = _write_model_ranking_spec(tmp_path, repo_root)

        def fake_run(command, **kwargs):
            return SimpleNamespace(returncode=1, stdout="", stderr="boom")

        payload = run_model_ranking_observation_cycle(
            root=tmp_path,
            spec=str(spec_path),
            cycle_date=date(2026, 9, 8),
            oc_cmd=["oc"],
            command_runner=fake_run,
        )

        assert payload["status"] == "failed"
        assert payload["failed_step"] == "account_sync"


def test_main_dry_run_for_model_ranking_spec_prints_two_step_plan(
    capsys,
    repo_root: Path,
) -> None:
    spec_path = repo_root / "strategy_specs" / "drafts" / "us_model_ranking_portfolio_top50.yaml"
    exit_code = main(
        [
            "--dry-run",
            "--date",
            "2026-09-08",
            "--root",
            str(repo_root),
            "--strategy",
            "us_model_ranking_portfolio_top50",
            "--spec",
            str(spec_path),
        ]
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "sync-account" in output
    assert "target-weights" in output
    assert "run paper" not in output
    assert "--allow-paper-orders" not in output
    assert len(output.strip().splitlines()) == 2
