from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from open_composer.research.multiscale_event_r5 import (
    EXPECTED_CANDIDATE_IDS,
    FutureFeatureError,
    _aggregate_15m_to_30m,
    _assert_feature_availability,
    _rank_series,
    _read_bar_frame,
    _selection_returns,
)


def test_candidate_manifest_and_search_space_are_exactly_bound() -> None:
    root = Path("reports/research/iterations/mom_multiscale_event_r5")
    manifest_path = root / "candidate-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    search = json.loads((root / "search-space.json").read_text(encoding="utf-8"))

    assert manifest["generated_before_backtest"] is True
    assert manifest["candidate_count"] == 15
    assert tuple(row["candidate_id"] for row in manifest["candidates"]) == (EXPECTED_CANDIDATE_IDS)
    assert sum(row["path"] == "deterministic_intraday" for row in manifest["candidates"]) == 9
    assert sum(row["path"] == "event_factor" for row in manifest["candidates"]) == 4
    assert sum(row["path"] == "negative_controls" for row in manifest["candidates"]) == 2
    assert search["total_candidate_budget"] == 15
    assert (
        search["preregistration"]["candidate_manifest_sha256"]
        == hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    )


def test_feature_packet_schema_requires_pit_and_grounding_fields() -> None:
    schema = json.loads(
        Path("schemas/multiscale_event_r5_feature_packet.schema.json").read_text(encoding="utf-8")
    )

    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert {
        "published_at",
        "fetched_at",
        "visible_at",
        "source",
        "input_hash",
        "prompt_hash",
        "dedupe_key",
        "evidence_spans",
    }.issubset(schema["required"])
    assert schema["properties"]["evidence_spans"]["minItems"] == 1


def test_read_bar_frame_rejects_duplicate_timestamp(tmp_path: Path) -> None:
    path = tmp_path / "bad.csv"
    path.write_text(
        "timestamp,open,high,low,close,volume\n"
        "2026-01-02T14:30:00Z,10,11,9,10.5,100\n"
        "2026-01-02T14:30:00Z,10,11,9,10.5,100\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate timestamps"):
        _read_bar_frame(path, "BAD")


def test_15m_aggregation_requires_complete_pairs() -> None:
    index = pd.DatetimeIndex(
        [
            "2026-01-05T14:30:00Z",
            "2026-01-05T14:45:00Z",
            "2026-01-05T15:00:00Z",
        ]
    )
    frame = pd.DataFrame(
        {
            "open": [10.0, 10.5, 11.0],
            "high": [10.8, 11.2, 11.3],
            "low": [9.8, 10.4, 10.9],
            "close": [10.6, 11.0, 11.2],
            "volume": [100.0, 150.0, 120.0],
        },
        index=index,
    )

    result = _aggregate_15m_to_30m(frame, "TEST")

    assert list(result.index.strftime("%H:%M")) == ["09:30"]
    assert result.iloc[0]["open"] == pytest.approx(10.0)
    assert result.iloc[0]["high"] == pytest.approx(11.2)
    assert result.iloc[0]["low"] == pytest.approx(9.8)
    assert result.iloc[0]["close"] == pytest.approx(11.0)
    assert result.iloc[0]["volume"] == pytest.approx(250.0)


def test_cross_section_rank_uses_symbol_ascending_tie_break() -> None:
    values = pd.Series({"BBB": 0.5, "AAA": 0.5, "CCC": 0.1})

    ranks = _rank_series(values)

    assert ranks["AAA"] == pytest.approx(1.0)
    assert ranks["BBB"] == pytest.approx(0.5)
    assert ranks["CCC"] == pytest.approx(0.0)


def test_round_trip_cost_is_charged_at_entry_and_exit() -> None:
    sessions = pd.DatetimeIndex(["2026-01-05", "2026-01-06"])
    labels = pd.DataFrame({"AAA": [0.01, 0.02]}, index=sessions)
    selections = {sessions[0]: ("AAA",), sessions[1]: ()}

    net, gross, traded = _selection_returns(selections, labels, cost_bps=10.0)

    assert gross.iloc[0] == pytest.approx(0.01)
    assert net.iloc[0] == pytest.approx(0.008)
    assert net.iloc[1] == pytest.approx(0.0)
    assert traded.tolist() == [True, False]


def test_future_feature_control_fails_closed() -> None:
    decision = pd.Timestamp("2026-01-05T15:30:00Z")

    with pytest.raises(FutureFeatureError):
        _assert_feature_availability(decision + pd.Timedelta(microseconds=1), decision)

    _assert_feature_availability(decision, decision)


def test_frozen_evaluation_accounts_for_every_candidate_and_rejects_promotion() -> None:
    report = json.loads(
        Path(
            "reports/research/iterations/mom_multiscale_event_r5/evaluation-report.json"
        ).read_text(encoding="utf-8")
    )

    assert report["candidate_count"] == 15
    assert report["completed_candidate_count"] == 10
    assert report["dependency_skipped_count"] == 4
    assert report["rejected_control_count"] == 1
    assert report["selected_candidates"] == []
    assert report["forward_observation_candidate_ids"] == []
    assert report["research_pass"] is False
    assert report["paper_ready_pass"] is False
    assert report["multiple_testing"]["quant_score_placebo"]["passed"] is False
    assert report["diagnostic_leader"]["total_return_pct"] < 0
    assert all(
        report["candidate_results"][candidate_id]["status"] == "skipped_dependency"
        for candidate_id in ["E01", "E02", "E03", "E04"]
    )


def test_harness_completeness_does_not_imply_paper_readiness() -> None:
    harness = json.loads(
        Path("reports/harness/verify/us_multiscale_event_momentum_r5.json").read_text(
            encoding="utf-8"
        )
    )
    readiness = json.loads(
        Path(
            "reports/harness/paper/us_multiscale_event_momentum_r5-paper-readiness.json"
        ).read_text(encoding="utf-8")
    )

    assert harness["overall"] == "ok"
    assert readiness["status"] == "blocked"
    assert readiness["ready"] is False
