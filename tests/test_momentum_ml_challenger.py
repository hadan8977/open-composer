from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.research.momentum_ml_challenger import (
    FEATURES,
    advisory_prediction,
    evaluate_momentum_ml_eligibility,
    write_momentum_product_status,
)
from open_composer.storage import append_jsonl, write_json
from open_composer.strategy_versions import strategy_content_hash


def test_ml_preflight_blocks_current_empty_forward_evidence(tmp_path: Path) -> None:
    result = evaluate_momentum_ml_eligibility(
        tmp_path / "missing.jsonl", tmp_path / "eligibility.json"
    )

    assert result.status == "blocked"
    assert result.payload["training_invoked"] is False
    assert result.payload["model_factory_invoked"] is False
    assert result.payload["execution_target_control"] is False
    assert "forward_decisions" in result.payload["failed_gates"]


def test_ml_preflight_can_become_eligible_from_complete_forward_fixture(
    tmp_path: Path, repo_root: Path
) -> None:
    spec_path = _write_spec(tmp_path, repo_root)
    ledger = tmp_path / "forward.jsonl"
    append_jsonl(ledger, _complete_rows(spec_path))

    result = evaluate_momentum_ml_eligibility(
        ledger, tmp_path / "eligibility.json", spec_path=spec_path
    )

    assert result.status == "eligible"
    assert result.payload["eligible"] is True
    assert result.payload["contract"]["feature_alignment"] == "index_minus_1"
    assert result.payload["contract"]["search_cap"] == 12
    assert result.payload["contract"]["purge_bars"] == 72
    assert result.payload["contract"]["embargo_bars"] == 72
    assert result.payload["ledger_provenance"]["valid"] is True


def test_ml_preflight_rejects_forged_non_provenance_ledger(tmp_path: Path, repo_root: Path) -> None:
    spec_path = _write_spec(tmp_path, repo_root)
    ledger = tmp_path / "forged.jsonl"
    append_jsonl(ledger, [{"signal_timestamp": "2027-01-02T15:00:00Z"}] * 900)

    try:
        evaluate_momentum_ml_eligibility(ledger, tmp_path / "eligibility.json", spec_path=spec_path)
    except ValueError as exc:
        assert "missing provenance fields" in str(exc)
    else:
        raise AssertionError("forged ML ledger must be rejected")


def test_ml_preflight_rejects_search_and_window_violations(tmp_path: Path) -> None:
    for kwargs, expected in [
        ({"search_combinations": 13}, "1..12"),
        ({"purge_bars": 71}, "purge_bars>=72"),
        ({"embargo_bars": 71}, "embargo_bars>=72"),
    ]:
        try:
            evaluate_momentum_ml_eligibility(
                tmp_path / "missing.jsonl", tmp_path / "eligibility.json", **kwargs
            )
        except ValueError as exc:
            assert expected in str(exc)
        else:
            raise AssertionError("invalid ML challenger contract must be rejected")


def test_advisory_prediction_never_controls_execution_target() -> None:
    features = {name: 0.1 for name in FEATURES}
    success = advisory_prediction(
        baseline_target=0.0,
        features=features,
        predictor=lambda values: 0.9,
    )
    assert success["advisory_target"] == 1.0
    assert success["execution_target"] == 0.0
    assert success["baseline_identical_execution"] is True

    failures = [
        advisory_prediction(baseline_target=1.0, features=features, predictor=None),
        advisory_prediction(
            baseline_target=1.0,
            features=features,
            predictor=lambda values: (_ for _ in ()).throw(RuntimeError("inference failed")),
        ),
        advisory_prediction(
            baseline_target=1.0,
            features={**features, FEATURES[0]: float("nan")},
            predictor=lambda values: 0.9,
        ),
        advisory_prediction(
            baseline_target=1.0,
            features={name: value for name, value in features.items() if name != FEATURES[0]},
            predictor=lambda values: 0.9,
        ),
        advisory_prediction(
            baseline_target=1.0,
            features=features,
            predictor=lambda values: float("nan"),
        ),
    ]
    assert all(row["status"] == "baseline_fallback" for row in failures)
    assert all(row["execution_target"] == 1.0 for row in failures)
    assert all(row["baseline_identical_execution"] is True for row in failures)


def test_final_status_separates_product_completion_from_external_gates(tmp_path: Path) -> None:
    readiness = tmp_path / "readiness.json"
    eligibility = tmp_path / "eligibility.json"
    write_json(
        readiness,
        {
            "report_type": "momentum_shadow_readiness",
            "status": "collecting",
            "operational_interim": {"passed": True},
        },
    )
    write_json(
        eligibility,
        {"report_type": "momentum_ml_challenger_eligibility", "eligible": False},
    )

    payload = write_momentum_product_status(readiness, eligibility, tmp_path / "status.json")

    assert payload["product_capability_complete"] is True
    assert payload["shadow_status"] == "collecting"
    assert payload["ml_eligible"] is False
    assert payload["paper_ready_pass"] is False
    assert payload["paper_authorized"] is False
    assert payload["broker_writes"] is False


def test_final_status_is_not_complete_when_required_artifacts_are_missing(tmp_path: Path) -> None:
    payload = write_momentum_product_status(
        tmp_path / "missing-readiness.json",
        tmp_path / "missing-eligibility.json",
        tmp_path / "status.json",
    )
    assert payload["product_capability_complete"] is False


def _complete_rows(spec_path: Path) -> list[dict[str, object]]:
    spec_hash = strategy_content_hash(load_strategy_spec(spec_path))
    rows = []
    sessions = pd.date_range("2027-01-04", periods=130, freq="B")
    for day_index, day in enumerate(sessions):
        regime = ("low_vol", "trend", "high_vol")[day_index % 3]
        for bar_index in range(13):
            timestamp = pd.Timestamp(day).tz_localize("America/New_York") + pd.Timedelta(
                hours=9, minutes=30 + bar_index * 30
            )
            position = float((day_index + bar_index) % 2)
            rows.append(
                {
                    "evidence_class": "forward_observation",
                    "spec_hash": spec_hash,
                    "observed_at": (
                        timestamp.tz_convert("UTC") + pd.Timedelta(hours=1)
                    ).isoformat(),
                    "signal_timestamp": timestamp.tz_convert("UTC").isoformat(),
                    "effective_timestamp": (
                        timestamp.tz_convert("UTC") + pd.Timedelta(minutes=30)
                    ).isoformat(),
                    "target_weight": position,
                    "order_required_intent": bar_index == 0,
                    "regime": regime,
                    "paper_order_authorization": False,
                    "broker_writes": False,
                }
            )
    return rows


def _write_spec(root: Path, repo_root: Path) -> Path:
    source = repo_root / "strategy_specs/drafts/us_mom_minute_p1_003_frozen.yaml"
    payload = yaml.safe_load(source.read_text(encoding="utf-8"))
    path = root / "strategy_specs/drafts/us_mom_minute_p1_003_frozen.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path
