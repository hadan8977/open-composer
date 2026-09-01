"""P1a: effective independent trial counting via return-stream clustering.

Acceptance criteria from
``docs/plan-sip-migration-and-wide-search-2026-09-01.zh.md`` section 4.3.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from open_composer.research.campaign import (
    MAX_FAMILY_EFFECTIVE_TRIAL_COUNT,
    MIN_EFFECTIVE_TRIAL_CORRELATION_THRESHOLD,
    campaign_contract_path,
    family_effective_trial_count_from_returns,
    validate_campaign_contract,
)
from open_composer.research.kernel import effective_independent_trials
from open_composer.research.kernel.effective_trials import (
    DEFAULT_CORRELATION_THRESHOLD,
    EffectiveTrialsReport,
)
from tests.test_research_campaign import _passing_contract, _write_promotion_evidence

ROOT = Path(__file__).resolve().parents[1]
SIP_DAILY_ROOT = ROOT / "data" / "sip" / "daily"
OBSERVATIONS = 512


def _rng(seed: int) -> np.random.Generator:
    return np.random.default_rng(seed)


def _orthogonal_returns(count: int, *, seed: int = 20260901) -> dict[str, list[float]]:
    generator = _rng(seed)
    return {
        f"C{index:03d}": (generator.normal(0.0, 0.01, OBSERVATIONS)).tolist()
        for index in range(count)
    }


def _correlated_groups(
    group_count: int,
    per_group: int,
    *,
    noise: float = 0.2,
    seed: int = 4201,
) -> dict[str, list[float]]:
    generator = _rng(seed)
    streams: dict[str, list[float]] = {}
    for group in range(group_count):
        base = generator.normal(0.0, 0.01, OBSERVATIONS)
        for member in range(per_group):
            perturbed = base + generator.normal(0.0, 0.01 * noise, OBSERVATIONS)
            streams[f"G{group:02d}M{member:03d}"] = perturbed.tolist()
    return streams


def _assert_report_is_complete(report: EffectiveTrialsReport) -> None:
    assert report.method == "hierarchical"
    assert report.linkage_method == "complete"
    assert report.effective_n == len(report.clusters)
    assert report.raw_candidate_count == len(report.candidate_ids)
    assert report.breadth_ratio == pytest.approx(report.effective_n / report.raw_candidate_count)
    assert 0.0 < report.breadth_ratio <= 1.0
    assert report.observation_count >= 2
    members = [member for cluster in report.clusters for member in cluster.members]
    assert sorted(members) == sorted(report.candidate_ids)
    assert len(members) == len(set(members))
    for cluster in report.clusters:
        assert cluster.cluster_id
        assert cluster.members
        # Complete linkage guarantees every pair inside a cluster clears the
        # threshold, which is what makes the cluster count a defensible
        # "one independent trial" claim.
        assert cluster.min_absolute_intra_correlation >= report.correlation_threshold - 1e-12
        assert cluster.mean_absolute_intra_correlation >= cluster.min_absolute_intra_correlation
    payload = report.model_dump()
    assert set(payload) >= {
        "effective_n",
        "raw_candidate_count",
        "breadth_ratio",
        "clusters",
        "correlation_threshold",
    }
    json.dumps(payload)


# --------------------------------------------------------------------------
# 4.3 (1): identical candidates are one trial
# --------------------------------------------------------------------------


@pytest.mark.parametrize("count", [2, 5, 40])
def test_identical_candidates_collapse_to_one_effective_trial(count: int) -> None:
    stream = _rng(11).normal(0.0, 0.01, OBSERVATIONS).tolist()
    report = effective_independent_trials({f"C{index:03d}": list(stream) for index in range(count)})

    assert report.effective_n == 1
    assert report.raw_candidate_count == count
    assert report.breadth_ratio == pytest.approx(1.0 / count)
    assert len(report.clusters) == 1
    assert len(report.clusters[0].members) == count
    _assert_report_is_complete(report)


def test_sign_flipped_duplicate_is_the_same_trial() -> None:
    """A short version of a strategy is not an independent look at the data."""
    stream = _rng(12).normal(0.0, 0.01, OBSERVATIONS).tolist()
    report = effective_independent_trials({"long": stream, "short": [-value for value in stream]})

    assert report.effective_n == 1


# --------------------------------------------------------------------------
# 4.3 (2): orthogonal candidates are N trials
# --------------------------------------------------------------------------


@pytest.mark.parametrize("count", [2, 8, 30])
def test_orthogonal_candidates_stay_independent_trials(count: int) -> None:
    report = effective_independent_trials(_orthogonal_returns(count))

    assert report.effective_n == count
    assert report.raw_candidate_count == count
    assert report.breadth_ratio == pytest.approx(1.0)
    assert report.max_absolute_inter_cluster_correlation < DEFAULT_CORRELATION_THRESHOLD
    _assert_report_is_complete(report)


# --------------------------------------------------------------------------
# 4.3 (3): the fake-breadth case
# --------------------------------------------------------------------------


def test_three_groups_of_one_hundred_near_duplicates_are_three_trials() -> None:
    report = effective_independent_trials(_correlated_groups(3, 100))

    assert report.raw_candidate_count == 300
    assert report.effective_n == 3
    assert report.breadth_ratio == pytest.approx(3 / 300)
    assert sorted(len(cluster.members) for cluster in report.clusters) == [100, 100, 100]
    for cluster in report.clusters:
        prefixes = {member[:3] for member in cluster.members}
        assert len(prefixes) == 1
    _assert_report_is_complete(report)


def test_genuine_breadth_and_fake_breadth_are_distinguishable() -> None:
    fake = effective_independent_trials(_correlated_groups(3, 100))
    genuine = effective_independent_trials(_orthogonal_returns(30))

    assert fake.raw_candidate_count > genuine.raw_candidate_count
    assert fake.effective_n < genuine.effective_n
    assert fake.breadth_ratio < 0.05
    assert genuine.breadth_ratio == pytest.approx(1.0)


# --------------------------------------------------------------------------
# Threshold behaviour and input validation
# --------------------------------------------------------------------------


def test_cluster_count_is_monotonic_in_the_correlation_threshold() -> None:
    streams = _correlated_groups(4, 20, noise=0.9, seed=77)
    counts = [
        effective_independent_trials(streams, correlation_threshold=threshold).effective_n
        for threshold in (0.3, 0.5, 0.7, 0.9)
    ]

    assert counts == sorted(counts)


def test_single_candidate_is_one_trial() -> None:
    report = effective_independent_trials({"only": _rng(3).normal(0, 0.01, 64).tolist()})

    assert report.effective_n == 1
    assert report.breadth_ratio == pytest.approx(1.0)


@pytest.mark.parametrize(
    ("returns", "message"),
    [
        ({}, "at least one candidate"),
        ({"a": [0.1, 0.2], "b": [0.1]}, "one time axis"),
        ({"a": [0.1], "b": [0.2]}, "at least 2 observations"),
        ({"a": [0.1, float("nan")], "b": [0.1, 0.2]}, "non-finite"),
        ({"a": [0.1, 0.1, 0.1], "b": [0.1, 0.2, 0.3]}, "zero-variance"),
    ],
)
def test_malformed_families_are_rejected(returns: dict[str, Any], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        effective_independent_trials(returns)


@pytest.mark.parametrize("threshold", [0.0, 1.0, -0.5, 1.5, float("nan")])
def test_out_of_range_correlation_threshold_is_rejected(threshold: float) -> None:
    with pytest.raises(ValueError, match="correlation_threshold"):
        effective_independent_trials(_orthogonal_returns(3), correlation_threshold=threshold)


def test_unsupported_method_is_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported effective trial clustering method"):
        effective_independent_trials(_orthogonal_returns(3), method="kmeans")  # type: ignore[arg-type]


def test_result_is_independent_of_candidate_insertion_order() -> None:
    streams = _correlated_groups(3, 6)
    reversed_streams = dict(reversed(list(streams.items())))

    first = effective_independent_trials(streams)
    second = effective_independent_trials(reversed_streams)

    assert first.effective_n == second.effective_n
    assert {frozenset(c.members) for c in first.clusters} == {
        frozenset(c.members) for c in second.clusters
    }


# --------------------------------------------------------------------------
# 4.3 (4): the gate rejects a family with more than 32 clusters
# --------------------------------------------------------------------------


def test_family_helper_accepts_a_family_at_the_cluster_cap() -> None:
    report = family_effective_trial_count_from_returns(
        _correlated_groups(MAX_FAMILY_EFFECTIVE_TRIAL_COUNT, 10)
    )

    assert report.effective_n == MAX_FAMILY_EFFECTIVE_TRIAL_COUNT
    assert report.raw_candidate_count == MAX_FAMILY_EFFECTIVE_TRIAL_COUNT * 10


def test_family_helper_rejects_more_clusters_than_the_cap() -> None:
    over_cap = MAX_FAMILY_EFFECTIVE_TRIAL_COUNT + 1
    with pytest.raises(ValueError) as excinfo:
        family_effective_trial_count_from_returns(_orthogonal_returns(over_cap))

    message = str(excinfo.value)
    assert "family effective independent trial count exceeds the hard cap" in message
    assert f"{over_cap}>{MAX_FAMILY_EFFECTIVE_TRIAL_COUNT}" in message
    assert f"raw_candidate_count={over_cap}" in message
    assert "breadth_ratio=1.0000" in message


def test_family_helper_rejects_a_loosened_correlation_threshold() -> None:
    with pytest.raises(ValueError, match="below the floor"):
        family_effective_trial_count_from_returns(
            _orthogonal_returns(4),
            correlation_threshold=MIN_EFFECTIVE_TRIAL_CORRELATION_THRESHOLD - 0.1,
        )


def _wide_search_contract(*, per_branch: int) -> dict[str, Any]:
    """A ``_passing_contract`` widened to ``6 * per_branch`` preregistered candidates."""
    payload = deepcopy(_passing_contract())
    payload["campaign_id"] = "momentum_wide_search_r1"
    buckets = [f"turnover_{index}" for index in range(1, per_branch + 1)]
    payload["candidate_blueprints"] = [
        {
            "candidate_id": f"H{branch}C{candidate:02d}",
            "hypothesis_id": f"H{branch}",
            "branch_id": f"B{branch}",
            "child_iteration_id": f"momentum_branch_r{branch}",
            "method_variant": f"method_{candidate}",
            "factor_variant": f"factor_{candidate}",
            "archive_descriptors": {
                "mechanism_family": f"mechanism_{branch}",
                "turnover_bucket": buckets[candidate - 1],
                "beta_bucket": "control" if branch == 6 else "market",
            },
            "model_training": False,
            "promotion_eligible": branch != 6,
        }
        for branch in range(1, 7)
        for candidate in range(1, per_branch + 1)
    ]
    total = 6 * per_branch
    for quota in payload["branch_quotas"]:
        quota["max_candidates"] = per_branch
    payload["exposure_budgets"] = {
        "candidate_budget": total,
        "cumulative_trial_exposure_budget": total * 3,
        "effective_trial_counting": "return_stream_clusters",
    }
    payload["expensive_resource_rungs"][0]["input_candidate_limit"] = total
    return payload


def _materialize(tmp_path: Path, payload: dict[str, Any], **kwargs: Any) -> Path:
    path = campaign_contract_path(payload["campaign_id"], tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    _write_promotion_evidence(path, payload, **kwargs)
    return path


def _blueprint_ids(payload: dict[str, Any]) -> list[str]:
    return [row["candidate_id"] for row in payload["candidate_blueprints"]]


def test_final_gate_rejects_a_family_above_the_cluster_cap(tmp_path: Path) -> None:
    payload = _wide_search_contract(per_branch=6)
    candidate_ids = _blueprint_ids(payload)
    generator = _rng(915)
    clustering_returns = {
        candidate_id: generator.normal(0.0, 0.01, 1040).tolist() for candidate_id in candidate_ids
    }

    path = _materialize(
        tmp_path,
        payload,
        effective_trial_clustering_returns=clustering_returns,
    )
    report = validate_campaign_contract(path, tmp_path, stage="final")

    cap_blockers = [
        item
        for item in report.blocked
        if item.startswith("statistical_family_effective_trial_clustering_effective_n_above_cap:")
    ]
    assert cap_blockers, report.blocked
    recorded = int(cap_blockers[0].rsplit(":", 2)[1])
    assert recorded > MAX_FAMILY_EFFECTIVE_TRIAL_COUNT
    assert cap_blockers[0].endswith(f":{MAX_FAMILY_EFFECTIVE_TRIAL_COUNT}")
    assert not report.ok


def test_final_gate_accepts_wide_search_that_clusters_under_the_cap(tmp_path: Path) -> None:
    payload = _wide_search_contract(per_branch=6)
    candidate_ids = _blueprint_ids(payload)
    generator = _rng(916)
    bases = [generator.normal(0.0, 0.01, 1040) for _ in range(3)]
    clustering_returns = {
        candidate_id: (bases[index % 3] + generator.normal(0.0, 0.0005, 1040)).tolist()
        for index, candidate_id in enumerate(candidate_ids)
    }

    path = _materialize(
        tmp_path,
        payload,
        effective_trial_clustering_returns=clustering_returns,
    )
    gates = json.loads(
        (path.parent / "artifacts" / "statistical-family-gates.json").read_text(encoding="utf-8")
    )
    clustering = gates["effective_trial_clustering"]

    # 36 backtests, but only a handful of distinct behaviours: both numbers are
    # on the artifact so the ratio is auditable.
    assert clustering["raw_candidate_count"] == 36
    assert gates["effective_trial_count"] == 36
    assert clustering["effective_n"] <= MAX_FAMILY_EFFECTIVE_TRIAL_COUNT
    assert clustering["breadth_ratio"] == pytest.approx(
        clustering["effective_n"] / clustering["raw_candidate_count"]
    )

    report = validate_campaign_contract(path, tmp_path, stage="final")

    assert not [
        item
        for item in report.blocked
        if item.startswith("statistical_family_effective_trial_clustering")
    ], report.blocked
    assert "statistical_family_gates_trial_count_above_exposure_budget" not in " ".join(
        report.blocked
    )
    # The whole point of P1a: 36 backtests clear the family gate because they
    # are only a handful of independent trials, with no threshold loosened.
    assert report.ok, report.blocked


def test_cluster_counting_mode_requires_clustering_evidence(tmp_path: Path) -> None:
    payload = _wide_search_contract(per_branch=3)
    path = _materialize(tmp_path, payload)

    report = validate_campaign_contract(path, tmp_path, stage="final")

    assert "statistical_family_effective_trial_clustering_missing" in report.blocked


def test_clustering_evidence_is_rejected_when_the_mode_was_not_preregistered(
    tmp_path: Path,
) -> None:
    """Cluster accounting must be committed to before the returns are known.

    Otherwise a family that missed the DSR on its raw ledger count could attach
    a clustering block after the fact and collapse the trial count until it
    passes -- exactly the "loosen the gate to let candidates through" failure
    mode section 9.6 of the plan forbids.
    """
    payload = _wide_search_contract(per_branch=3)
    payload["exposure_budgets"]["effective_trial_counting"] = "candidate_count"
    candidate_ids = _blueprint_ids(payload)
    generator = _rng(918)
    base = generator.normal(0.0, 0.01, 1040)
    clustering_returns = {
        candidate_id: (base + generator.normal(0.0, 0.0005, 1040)).tolist()
        for candidate_id in candidate_ids
    }

    path = _materialize(
        tmp_path,
        payload,
        effective_trial_clustering_returns=clustering_returns,
    )
    gates = json.loads(
        (path.parent / "artifacts" / "statistical-family-gates.json").read_text(encoding="utf-8")
    )
    # The block itself is internally consistent and would collapse 18 trials
    # into a handful; it is refused purely because the contract never declared
    # the mode.
    assert gates["effective_trial_count"] == 18
    assert gates["effective_trial_clustering"]["effective_n"] < 18

    report = validate_campaign_contract(path, tmp_path, stage="final")

    assert "statistical_family_effective_trial_clustering_not_preregistered" in report.blocked
    assert not report.ok


def test_gate_rejects_forged_clustering_evidence(tmp_path: Path) -> None:
    payload = _wide_search_contract(per_branch=6)
    candidate_ids = _blueprint_ids(payload)
    generator = _rng(917)
    clustering_returns = {
        candidate_id: generator.normal(0.0, 0.01, 1040).tolist() for candidate_id in candidate_ids
    }
    path = _materialize(
        tmp_path,
        payload,
        effective_trial_clustering_returns=clustering_returns,
    )
    gates_path = path.parent / "artifacts" / "statistical-family-gates.json"
    gates = json.loads(gates_path.read_text(encoding="utf-8"))
    clustering = gates["effective_trial_clustering"]
    clustering["effective_n"] = 2
    clustering["breadth_ratio"] = 2 / clustering["raw_candidate_count"]
    clustering["clusters"] = [
        {"cluster_id": "cluster_001", "members": sorted(clustering["candidate_returns"])[:1]},
        {"cluster_id": "cluster_002", "members": sorted(clustering["candidate_returns"])[1:]},
    ]
    gates_path.write_text(json.dumps(gates), encoding="utf-8")

    report = validate_campaign_contract(path, tmp_path, stage="final")

    assert any(
        item.startswith("statistical_family_effective_trial_clustering_effective_n_mismatch")
        for item in report.blocked
    ), report.blocked
    assert (
        "statistical_family_effective_trial_clustering_cluster_membership_mismatch"
        in report.blocked
    )


def test_gate_rejects_a_lowered_clustering_threshold(tmp_path: Path) -> None:
    payload = _wide_search_contract(per_branch=6)
    candidate_ids = _blueprint_ids(payload)
    generator = _rng(918)
    clustering_returns = {
        candidate_id: generator.normal(0.0, 0.01, 1040).tolist() for candidate_id in candidate_ids
    }
    path = _materialize(
        tmp_path,
        payload,
        effective_trial_clustering_returns=clustering_returns,
    )
    gates_path = path.parent / "artifacts" / "statistical-family-gates.json"
    gates = json.loads(gates_path.read_text(encoding="utf-8"))
    gates["effective_trial_clustering"]["correlation_threshold"] = 0.05
    gates_path.write_text(json.dumps(gates), encoding="utf-8")

    report = validate_campaign_contract(path, tmp_path, stage="final")

    assert any(
        item.startswith(
            "statistical_family_effective_trial_clustering_correlation_threshold_below_floor"
        )
        for item in report.blocked
    ), report.blocked


def test_gate_rejects_clustering_that_drops_counted_trials(tmp_path: Path) -> None:
    payload = _wide_search_contract(per_branch=6)
    candidate_ids = _blueprint_ids(payload)
    generator = _rng(919)
    clustering_returns = {
        candidate_id: generator.normal(0.0, 0.01, 1040).tolist() for candidate_id in candidate_ids
    }
    path = _materialize(
        tmp_path,
        payload,
        effective_trial_clustering_returns=clustering_returns,
    )
    gates_path = path.parent / "artifacts" / "statistical-family-gates.json"
    gates = json.loads(gates_path.read_text(encoding="utf-8"))
    clustering = gates["effective_trial_clustering"]
    keep = ["H1C01", "H2C01", *sorted(clustering["candidate_returns"])[:4]]
    clustering["candidate_returns"] = {
        candidate_id: clustering["candidate_returns"][candidate_id]
        for candidate_id in dict.fromkeys(keep)
    }
    clustering["raw_candidate_count"] = len(clustering["candidate_returns"])
    gates_path.write_text(json.dumps(gates), encoding="utf-8")

    report = validate_campaign_contract(path, tmp_path, stage="final")

    assert any(
        item.startswith(
            "statistical_family_effective_trial_clustering_raw_candidate_count_below_trial_count"
        )
        for item in report.blocked
    ), report.blocked


def test_legacy_candidate_count_campaigns_keep_the_raw_ledger_cap(tmp_path: Path) -> None:
    payload = _wide_search_contract(per_branch=6)
    payload["exposure_budgets"]["effective_trial_counting"] = "candidate_count"
    path = campaign_contract_path(payload["campaign_id"], tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="family effective trial count exceeds the hard cap"):
        _write_promotion_evidence(path, payload)


# --------------------------------------------------------------------------
# 4.3 (5): end to end on real SIP data
# --------------------------------------------------------------------------


def _sip_close_frame(symbols: list[str], years: list[int]):
    pandas = pytest.importorskip("pandas")
    dataset = pytest.importorskip("pyarrow.dataset")

    frames = []
    for year in years:
        year_root = SIP_DAILY_ROOT / str(year)
        if not year_root.is_dir():
            pytest.skip(f"SIP daily data for {year} is not present")
        table = dataset.dataset(str(year_root), format="parquet").to_table(
            filter=dataset.field("symbol").isin(symbols),
            columns=["symbol", "timestamp", "close"],
        )
        frames.append(table.to_pandas())
    frame = pandas.concat(frames, ignore_index=True)
    frame["date"] = pandas.to_datetime(frame["timestamp"], utc=True).dt.date
    wide = frame.pivot_table(index="date", columns="symbol", values="close", aggfunc="last")
    wide = wide.sort_index().dropna(how="any")
    missing = sorted(set(symbols) - set(wide.columns))
    if missing:
        pytest.skip(f"SIP daily data is missing symbols: {missing}")
    return wide


@pytest.mark.skipif(not SIP_DAILY_ROOT.is_dir(), reason="data/sip/daily is not present")
def test_end_to_end_effective_trials_on_real_sip_daily_data() -> None:
    symbols = ["QQQ", "SPY", "TQQQ", "IWM", "XLK"]
    closes = _sip_close_frame(symbols, [2022, 2023, 2024])
    assert len(closes) > 600

    daily_returns = closes.pct_change().fillna(0.0)
    candidates: dict[str, list[float]] = {}
    # Three lookbacks one bar apart on QQQ are the textbook near-duplicate case;
    # the other symbols are genuinely different behaviours.
    for lookback in (50, 51, 52):
        signal = (
            (closes["QQQ"] > closes["QQQ"].rolling(lookback).mean())
            .astype(float)
            .shift(1)
            .fillna(0.0)
        )
        candidates[f"qqq_sma_{lookback}"] = (signal * daily_returns["QQQ"]).tolist()
    for symbol in ("SPY", "IWM", "XLK"):
        signal = (
            (closes[symbol] > closes[symbol].rolling(100).mean()).astype(float).shift(1).fillna(0.0)
        )
        candidates[f"{symbol.lower()}_sma_100"] = (signal * daily_returns[symbol]).tolist()
    candidates["tqqq_buy_and_hold"] = daily_returns["TQQQ"].tolist()

    report = effective_independent_trials(candidates)

    _assert_report_is_complete(report)
    assert report.raw_candidate_count == 7
    assert report.observation_count == len(closes)
    assert 1 <= report.effective_n < report.raw_candidate_count
    assert report.correlation_threshold == DEFAULT_CORRELATION_THRESHOLD
    # The three one-bar-apart QQQ lookbacks must not count as three trials.
    qqq_clusters = {
        cluster.cluster_id
        for cluster in report.clusters
        for member in cluster.members
        if member.startswith("qqq_sma_")
    }
    assert len(qqq_clusters) == 1

    capped = family_effective_trial_count_from_returns(candidates)
    assert capped.effective_n == report.effective_n
    assert capped.breadth_ratio == pytest.approx(report.effective_n / report.raw_candidate_count)
