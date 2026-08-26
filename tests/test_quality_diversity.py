from __future__ import annotations

from dataclasses import replace
from itertools import permutations

import pytest

from open_composer.research.quality_diversity import (
    AllocationLedger,
    QualityDiversityCandidate,
    QualityDiversityPolicy,
    append_allocation_entry,
    build_quality_diversity_archive,
    validate_allocation_extension,
    validate_allocation_ledger,
)


def _candidate(
    candidate_id: str,
    *,
    branch: str = "trend",
    horizon: str = "monthly",
    construction: str = "ranked",
    quality: float = 1.0,
    visibility_partition: str = "development",
    resource_rung: int = 0,
) -> QualityDiversityCandidate:
    return QualityDiversityCandidate(
        candidate_id=candidate_id,
        hypothesis_id=f"hypothesis-{branch}",
        branch=branch,
        archive_descriptors={"horizon": horizon, "construction": construction},
        quality=quality,
        quality_metric="development_cost_stressed_sharpe",
        visibility_partition=visibility_partition,
        metrics_snapshot_path=f"metrics/{candidate_id}.json",
        metrics_snapshot_sha256="a" * 64,
        partition_contract_path="contracts/development.json",
        partition_contract_sha256="b" * 64,
        promotion_eligible=True,
        resource_rung=resource_rung,
    )


def _policy(*, direction: str = "maximize") -> QualityDiversityPolicy:
    registered_candidate_ids = (
        "B01",
        "B02",
        "C01",
        "C02",
        "C03",
        "R01",
        "T01",
        "T02",
    )
    return QualityDiversityPolicy(
        campaign_id="campaign-01",
        campaign_contract_sha256="f" * 64,
        descriptor_names=("horizon", "construction"),
        quality_direction=direction,  # type: ignore[arg-type]
        quality_metric="development_cost_stressed_sharpe",
        quality_partition_id="development",
        candidate_budget=len(registered_candidate_ids),
        registered_candidate_ids=registered_candidate_ids,
        candidate_hypothesis_ids={
            candidate_id: "hypothesis-reversal" if candidate_id == "R01" else "hypothesis-trend"
            for candidate_id in registered_candidate_ids
        },
        candidate_branch_ids={
            candidate_id: "reversal" if candidate_id == "R01" else "trend"
            for candidate_id in registered_candidate_ids
        },
        candidate_promotion_eligibility={
            candidate_id: True for candidate_id in registered_candidate_ids
        },
        candidate_archive_descriptors={
            candidate_id: {
                "horizon": "weekly" if candidate_id == "R01" else "monthly",
                "construction": "ranked",
            }
            for candidate_id in registered_candidate_ids
        },
        branch_min_quotas={"reversal": 2, "trend": 1},
        branch_max_quotas={"reversal": 3, "trend": 2},
    )


def test_archive_selects_one_elite_per_cell_and_reports_branch_quotas() -> None:
    archive = build_quality_diversity_archive(
        [
            _candidate("T02", quality=1.2),
            _candidate("T01", quality=1.1),
            _candidate(
                "R01",
                branch="reversal",
                horizon="weekly",
                quality=0.8,
                resource_rung=1,
            ),
        ],
        _policy(),
    )

    assert archive.eligible_candidate_count == 3
    assert archive.elite_count == 2
    assert {elite.candidate.candidate_id for elite in archive.elites} == {"R01", "T02"}
    reports = {report.branch: report for report in archive.branch_quotas}
    assert reports["trend"].candidate_count == 2
    assert reports["trend"].elite_count == 1
    assert reports["trend"].minimum_met is True
    assert reports["trend"].maximum_met is True
    assert reports["reversal"].candidate_count == 1
    assert reports["reversal"].minimum_met is False


def test_archive_output_is_independent_of_candidate_input_order() -> None:
    candidates = [
        _candidate("C03", quality=0.7),
        _candidate("C01", quality=0.7),
        _candidate("R01", branch="reversal", horizon="weekly", quality=0.9),
    ]

    outputs = [
        build_quality_diversity_archive(list(order), _policy()).model_dump()
        for order in permutations(candidates)
    ]

    assert all(output == outputs[0] for output in outputs[1:])


@pytest.mark.parametrize(
    ("direction", "qualities", "expected"),
    [
        ("maximize", {"B02": 1.0, "B01": 1.0}, "B01"),
        ("minimize", {"B02": 0.4, "B01": 0.7}, "B02"),
    ],
)
def test_archive_uses_preregistered_quality_and_candidate_id_tie_break(
    direction: str,
    qualities: dict[str, float],
    expected: str,
) -> None:
    archive = build_quality_diversity_archive(
        [_candidate(candidate_id, quality=quality) for candidate_id, quality in qualities.items()],
        _policy(direction=direction),
    )

    assert archive.elites[0].candidate.candidate_id == expected


@pytest.mark.parametrize("partition", ["frozen_oos", "challenge", "forward"])
def test_archive_rejects_forbidden_selection_visibility(partition: str) -> None:
    with pytest.raises(ValueError, match="forbidden selection visibility"):
        build_quality_diversity_archive(
            [_candidate("C01", visibility_partition=partition)],
            _policy(),
        )


@pytest.mark.parametrize("quality", [float("nan"), float("inf"), float("-inf")])
def test_archive_rejects_nonfinite_quality(quality: float) -> None:
    with pytest.raises(ValueError, match="quality must be finite"):
        build_quality_diversity_archive([_candidate("C01", quality=quality)], _policy())


def test_archive_rejects_missing_or_malformed_cell_descriptors() -> None:
    missing = replace(_candidate("C01"), archive_descriptors={"horizon": "monthly"})
    malformed = replace(
        _candidate("C02"),
        archive_descriptors={"horizon": "monthly", "construction": float("nan")},
    )

    with pytest.raises(ValueError, match="missing cell descriptors"):
        build_quality_diversity_archive([missing], _policy())
    with pytest.raises(ValueError, match="finite JSON scalar"):
        build_quality_diversity_archive([malformed], _policy())


def test_archive_rejects_undeclared_descriptor_and_branch() -> None:
    extra_descriptor = replace(
        _candidate("C01"),
        archive_descriptors={
            "horizon": "monthly",
            "construction": "ranked",
            "hidden_oos_bucket": "winner",
        },
    )
    undeclared_branch = _candidate("C02", branch="carry")

    with pytest.raises(ValueError, match="undeclared cell descriptors"):
        build_quality_diversity_archive([extra_descriptor], _policy())
    with pytest.raises(ValueError, match="binding drift"):
        build_quality_diversity_archive([undeclared_branch], _policy())


def test_archive_accepts_explicit_development_partition_ids() -> None:
    policy = replace(
        _policy(),
        quality_partition_id="development_validation",
        selection_visibility_partitions=("development_train", "development_validation"),
    )
    archive = build_quality_diversity_archive(
        [_candidate("C01", visibility_partition="development_validation")],
        policy,
    )

    assert archive.elite_count == 1


def test_archive_rejects_duplicate_candidate_ids() -> None:
    with pytest.raises(ValueError, match="candidate_id values must be unique"):
        build_quality_diversity_archive(
            [_candidate("C01", quality=0.5), _candidate("C01", quality=0.8)],
            _policy(),
        )


def test_archive_rejects_branch_maximum_quota_overrun() -> None:
    with pytest.raises(ValueError, match="branch maximum quota exceeded"):
        build_quality_diversity_archive(
            [_candidate("C01"), _candidate("C02"), _candidate("C03")],
            _policy(),
        )


def test_archive_rejects_unregistered_candidate() -> None:
    with pytest.raises(ValueError, match="outside the preregistered inventory"):
        build_quality_diversity_archive([_candidate("X01")], _policy())


def test_sealed_archive_requires_complete_evaluated_or_excluded_inventory() -> None:
    policy = _policy()
    with pytest.raises(ValueError, match="sealed inventory is incomplete"):
        build_quality_diversity_archive(
            [_candidate("C01")],
            policy,
            require_complete_inventory=True,
        )

    archive = build_quality_diversity_archive(
        [_candidate("C01")],
        policy,
        excluded_candidate_ids=[
            candidate_id
            for candidate_id in policy.registered_candidate_ids
            if candidate_id != "C01"
        ],
        require_complete_inventory=True,
    )

    assert archive.candidates[0].candidate_id == "C01"
    assert set(archive.excluded_candidate_ids) == set(policy.registered_candidate_ids) - {"C01"}


def _empty_ledger(*, exposure_budget: float = 10.0) -> AllocationLedger:
    return AllocationLedger(
        campaign_id="campaign-01",
        campaign_contract_sha256="f" * 64,
        candidate_inventory_sha256="e" * 64,
        registered_candidate_ids=("C01", "C02", "C99"),
        allowed_visibility_partitions=("train", "development"),
        effective_trial_exposure_budget=exposure_budget,
    )


def _ledger_with_two_entries() -> tuple[AllocationLedger, AllocationLedger]:
    empty = _empty_ledger()
    first = append_allocation_entry(
        empty,
        candidate_id="C01",
        decision="allocate",
        resource_used={"candidate_evaluations": 1.0},
        metrics_snapshot_sha256="a" * 64,
        effective_trial_exposure=1.0,
        visibility_partition="train",
    )
    second = append_allocation_entry(
        first,
        candidate_id="C01",
        decision="advance",
        resource_used={"fit_seconds": 4.25},
        metrics_snapshot_sha256="b" * 64,
        effective_trial_exposure=0.5,
        visibility_partition="development",
    )
    return first, second


def test_allocation_ledger_appends_contiguous_hash_chained_entries() -> None:
    first, second = _ledger_with_two_entries()

    validate_allocation_ledger(second, expected_head_sha256=second.head_sha256)
    validate_allocation_extension(first, second)
    assert [entry.sequence for entry in second.entries] == [1, 2]
    assert second.entries[0].previous_entry_sha256 is None
    assert second.entries[1].previous_entry_sha256 == second.entries[0].entry_sha256
    assert second.head_sha256 == second.entries[1].entry_sha256
    assert len(second.head_sha256 or "") == 64


@pytest.mark.parametrize("partition", ["frozen_oos", "challenge", "forward"])
def test_allocation_ledger_rejects_forbidden_selection_visibility(partition: str) -> None:
    with pytest.raises(ValueError, match="forbidden selection visibility"):
        append_allocation_entry(
            _empty_ledger(),
            candidate_id="C01",
            decision="allocate",
            resource_used={"candidate_evaluations": 1.0},
            metrics_snapshot_sha256="a" * 64,
            effective_trial_exposure=1.0,
            visibility_partition=partition,
        )


def test_allocation_ledger_rejects_unregistered_candidate() -> None:
    with pytest.raises(ValueError, match="not preregistered"):
        append_allocation_entry(
            _empty_ledger(),
            candidate_id="X01",
            decision="allocate",
            resource_used={"candidate_evaluations": 1.0},
            metrics_snapshot_sha256="a" * 64,
            effective_trial_exposure=1.0,
            visibility_partition="development",
        )


def test_allocation_ledger_rejects_cumulative_trial_exposure_overrun() -> None:
    ledger = append_allocation_entry(
        _empty_ledger(exposure_budget=1.0),
        candidate_id="C01",
        decision="allocate",
        resource_used={"candidate_evaluations": 1.0},
        metrics_snapshot_sha256="a" * 64,
        effective_trial_exposure=1.0,
        visibility_partition="development",
    )

    with pytest.raises(ValueError, match="trial exposure budget exceeded"):
        append_allocation_entry(
            ledger,
            candidate_id="C02",
            decision="advance",
            resource_used={"candidate_evaluations": 1.0},
            metrics_snapshot_sha256="b" * 64,
            effective_trial_exposure=0.01,
            visibility_partition="development",
        )


def test_allocation_ledger_rejects_entry_mutation_and_bad_previous_hash() -> None:
    _, ledger = _ledger_with_two_entries()
    mutated_first = replace(ledger.entries[0], effective_trial_exposure=99.0)
    mutated = replace(ledger, entries=(mutated_first, ledger.entries[1]))
    bad_previous = replace(
        ledger,
        entries=(ledger.entries[0], replace(ledger.entries[1], previous_entry_sha256="c" * 64)),
    )

    with pytest.raises(ValueError, match="entry hash identity"):
        validate_allocation_ledger(mutated)
    with pytest.raises(ValueError, match="previous-entry hash chain"):
        validate_allocation_ledger(bad_previous)


def test_allocation_ledger_rejects_reorder_and_sequence_gap() -> None:
    _, ledger = _ledger_with_two_entries()
    reordered = replace(ledger, entries=tuple(reversed(ledger.entries)))
    gap = replace(
        ledger,
        entries=(ledger.entries[0], replace(ledger.entries[1], sequence=3)),
    )

    with pytest.raises(ValueError, match="monotonically contiguous"):
        validate_allocation_ledger(reordered)
    with pytest.raises(ValueError, match="monotonically contiguous"):
        validate_allocation_ledger(gap)


def test_allocation_extension_rejects_a_valid_but_rewritten_prefix() -> None:
    first, second = _ledger_with_two_entries()
    rewritten = append_allocation_entry(
        _empty_ledger(),
        candidate_id="C99",
        decision="allocate",
        resource_used={"candidate_evaluations": 1.0},
        metrics_snapshot_sha256="d" * 64,
        effective_trial_exposure=1.0,
        visibility_partition="train",
    )
    rewritten = append_allocation_entry(
        rewritten,
        candidate_id="C01",
        decision="advance",
        resource_used={"fit_seconds": 4.25},
        metrics_snapshot_sha256="b" * 64,
        effective_trial_exposure=0.5,
        visibility_partition="development",
    )

    validate_allocation_ledger(rewritten)
    with pytest.raises(ValueError, match="existing prefix was mutated or reordered"):
        validate_allocation_extension(first, rewritten)
    validate_allocation_extension(first, second)
