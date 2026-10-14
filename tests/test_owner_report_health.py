import json
from pathlib import Path

from open_composer.reports.owner_health import report_event_health

EVENT = "round-20261014T160000Z"


def write_state(root: Path, state, allowed=True):
    hold = root / "reports/research/control/owner-compute-hold.json"
    hold.parent.mkdir(parents=True, exist_ok=True)
    hold.write_text(json.dumps({"reporting": {"allowed": allowed}}))
    folder = root / "reports/owner"
    folder.mkdir(exist_ok=True)
    (folder / "reporting-state.json").write_text(json.dumps(state))


def test_real_failure_scheduler_success_has_no_business_artifact(tmp_path):
    write_state(
        tmp_path,
        {
            "scheduler_status": "succeeded",
            "completed_event_ids": [],
            "last_report": {"event_id": "round-20261013T080000Z"},
        },
    )
    result = report_event_health(tmp_path, EVENT)
    assert result["status"] == "missing_business_result"
    assert not result["artifact_verified"]


def test_queued_event_is_not_completed_report(tmp_path):
    write_state(
        tmp_path,
        {"reports": [{"event_id": EVENT, "delivery_status": "queued"}], "completed_event_ids": []},
    )
    assert report_event_health(tmp_path, EVENT)["status"] == "artifact_missing"


def test_completion_marker_without_file_does_not_pass(tmp_path):
    write_state(
        tmp_path,
        {
            "last_report": {"event_id": EVENT, "file": "reports/owner/a.md"},
            "completed_event_ids": [EVENT],
        },
    )
    assert report_event_health(tmp_path, EVENT)["status"] == "artifact_missing"


def test_actual_report_passes_without_inventing_delivery(tmp_path):
    write_state(
        tmp_path,
        {
            "last_report": {"event_id": EVENT, "file": "reports/owner/a.md"},
            "completed_event_ids": [EVENT],
        },
    )
    (tmp_path / "reports/owner/a.md").write_text("Verified current research report.")
    result = report_event_health(tmp_path, EVENT)
    assert result["status"] == "written" and result["artifact_verified"]
    assert result["delivery_verified"] is False


def test_genuine_pause_does_not_become_false_missing_report_alarm(tmp_path):
    write_state(tmp_path, {}, allowed=False)
    assert report_event_health(tmp_path, EVENT)["status"] == "not_authorized"


def test_changed_bound_report_is_not_silently_accepted(tmp_path):
    write_state(
        tmp_path,
        {
            "last_report": {"event_id": EVENT, "file": "reports/owner/a.md", "sha256": "0" * 64},
            "completed_event_ids": [EVENT],
        },
    )
    (tmp_path / "reports/owner/a.md").write_text("Changed result.")
    assert report_event_health(tmp_path, EVENT)["status"] == "artifact_changed"
