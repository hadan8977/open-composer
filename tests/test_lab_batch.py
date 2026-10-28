import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from open_composer.lab import (
    DSRConfig,
    EngineResult,
    Experiment,
    TrialLedger,
    Variant,
    run_batch,
)
from open_composer.research.agent_workflow import validate_results


def enable(root: Path):
    (root / "control.json").write_text(json.dumps({"draft": False, "research": True}))


def fixture_output():
    returns = pd.Series(
        np.sin(np.arange(40)) * 0.01 + 0.0002,
        index=pd.bdate_range("2024-01-02", periods=40),
    )
    return EngineResult(
        engine="synthetic_accounting_fixture",
        initial_equity_usd=1_000,
        end_equity_usd=1_000 * (1 + returns).prod(),
        net_returns=returns,
        ledger=pd.DataFrame({"net": returns, "cost_bp": 10}),
        native={"fixture": True, "costed_returns": True},
    )


def experiment():
    return Experiment(
        direction="lab_test",
        kind="diagnostic",
        data_and_exposure="Synthetic seen fixture, no economic claim",
        costs="Fixture series already net of declared illustrative costs",
        baseline="Zero-return synthetic cash",
        baseline_net_profit_usd=0,
    )


def test_batches_keep_failed_trials_and_write_engine_results_schema(tmp_path: Path):
    enable(tmp_path)
    old = tmp_path / "old.json"
    old.write_text('{"original_trial_count": 5}')
    ledger = TrialLedger(tmp_path / "research/lab_test/trials.jsonl")
    ledger.import_prior("prior", count=5, evidence=["old.json"], note="Historical seen trials")

    def fail():
        raise ValueError("Intentionally failed fixture")

    benchmark = fixture_output().net_returns * 0
    config = DSRConfig(
        method="campaign_statistics",
        benchmark=benchmark,
        benchmark_note="Synthetic zero cash on matching observed sessions",
        hac_lag=3,
        assumptions="All started/prior trials; HAC 3, fixture only",
    )
    first = run_batch(
        tmp_path,
        experiment=experiment(),
        batch_id="first",
        variants=[Variant("a", {}, fixture_output), Variant("broken", {}, fail)],
        dsr_config=config,
        selected_id="a",
    )
    assert first.n_trials == 7
    assert first.failures == {"broken": "Intentionally failed fixture"}
    old_snapshot = (first.folder / "trials.snapshot.jsonl").read_bytes()
    old_result = first.results["a"].read_bytes()
    result = validate_results(tmp_path, "research/lab_test/results.json", "lab_test")
    assert result.n_trials == 7
    assert result.net_profit_usd == pytest.approx(fixture_output().net_profit_usd)
    assert result.dsr is not None
    assert json.loads(result.dsr_note)["method"] == "campaign_statistics"
    second = run_batch(
        tmp_path,
        experiment=experiment(),
        batch_id="second",
        variants=[Variant("a", {"new_condition": True}, fixture_output)],
        dsr_config=config,
    )
    assert second.n_trials == 8
    assert first.results["a"].read_bytes() == old_result
    assert (first.folder / "trials.snapshot.jsonl").read_bytes() == old_snapshot
    assert ledger.path.read_bytes().startswith(old_snapshot)
    assert (
        validate_results(
            tmp_path, str(second.results["a"].relative_to(tmp_path)), "lab_test"
        ).n_trials
        == 8
    )
    with pytest.raises(FileExistsError):
        run_batch(
            tmp_path,
            experiment=experiment(),
            batch_id="first",
            variants=[Variant("a", {}, fixture_output)],
        )


def test_run_requires_installed_authority_before_creating_trials(tmp_path: Path):
    (tmp_path / "control.json").write_text('{"draft": true, "research": false}')
    with pytest.raises(ValueError, match="enabled"):
        run_batch(
            tmp_path,
            experiment=experiment(),
            batch_id="held",
            variants=[Variant("a", {}, fixture_output)],
        )
    assert not (tmp_path / "research").exists()


def test_interrupted_start_is_counted_and_requires_explicit_recovery(tmp_path: Path):
    enable(tmp_path)
    ledger = TrialLedger(tmp_path / "research/lab_test/trials.jsonl")
    ledger.start("crashed/a", batch="crashed", candidate="a", parameters={})
    with pytest.raises(ValueError, match="unfinished trials"):
        run_batch(
            tmp_path,
            experiment=experiment(),
            batch_id="new",
            variants=[Variant("a", {}, fixture_output)],
        )
    assert ledger.n_trials == 1
    ledger.finish("crashed/a", status="interrupted", evidence=[], note="Confirmed no live job")
    result = run_batch(
        tmp_path,
        experiment=experiment(),
        batch_id="recovered",
        variants=[Variant("a", {}, fixture_output)],
    )
    assert result.n_trials == 2


def test_bad_native_returns_cannot_fabricate_account_pnl():
    output = fixture_output()
    with pytest.raises(ValueError, match="reconcile"):
        EngineResult(
            engine="bad",
            initial_equity_usd=1_000,
            end_equity_usd=2_000,
            native={},
            net_returns=output.net_returns,
        )


def test_working_example_computes_native_costed_diagnostic_results(tmp_path: Path):
    from open_composer.lab.example import run_example

    enable(tmp_path)
    batch = run_example(tmp_path, batch_id="example")
    assert batch.n_trials == 2
    assert not batch.failures
    result = validate_results(tmp_path, "research/lab_example/results.json", "lab_example")
    assert result.kind == "diagnostic"
    assert result.dsr is not None
    assert "Synthetic" in " ".join(result.limitations)
    ledger = pd.read_csv(batch.folder / "weight_60/ledger.csv")
    assert ledger["cost_spread"].sum() > 0
    ablations = json.loads((batch.folder / "ablations.json").read_text())
    assert {row["key"] for row in ablations} == {
        "stop_loss_pct",
        "take_profit_pct",
        "commission_pct",
        "weight",
    }
    assert all(row["changed_observables"] for row in ablations)
