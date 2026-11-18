"""Publishing reconciled projections must not rewrite values or lose old bindings."""

import copy
import hashlib
import json
from pathlib import Path

import pytest

from open_composer.cockpit.data.paper_overview import load_paper_overview
from scripts import publish_paper_overview as publisher


def projection():
    return {
        "schema_version": 1,
        "generated_at": "2026-10-27T04:20:10+00:00",
        "through_session": "2026-10-26",
        "snapshot": {
            "at_start": "2026-10-27T04:19:56+00:00",
            "at_end": "2026-10-27T04:20:03+00:00",
            "marks_start": "2026-10-27T04:19:57+00:00",
            "marks_end": "2026-10-27T04:20:06+00:00",
            "capital_usd": 140,
            "pnl_usd": 15.5,
            "return_pct": 15.5 / 140 * 100,
            "adjustment_usd": 0.5,
            "unassigned_capital_usd": 40,
            "missing": [],
            "pools": ["pool"],
            "rows": [
                {
                    "id": "pool/first",
                    "label": "First strategy",
                    "pool": "pool",
                    "status": "实际账本",
                    "first_day": "2026-10-23",
                    "capital_usd": 100,
                    "pnl_usd": 10,
                    "precise_pnl_usd": 10.004,
                    "return_pct": 10.004,
                },
                {
                    "id": "pool/retired",
                    "label": "Retired strategy",
                    "pool": "pool",
                    "status": "已退出",
                    "first_day": "2026-10-23",
                    "capital_usd": None,
                    "pnl_usd": 5,
                    "precise_pnl_usd": 5,
                    "return_pct": None,
                },
            ],
        },
        "daily": [
            {
                "day": "2026-10-23",
                "capital_usd": 140,
                "pnl_usd": 15.5,
                "return_pct": 15.5 / 140 * 100,
                "missing": [],
                "pools": ["pool"],
            },
            {
                "day": "2026-10-26",
                "capital_usd": 140,
                "pnl_usd": None,
                "return_pct": None,
                "missing": ["pool"],
                "pools": ["pool"],
            },
        ],
    }


def write_input(root: Path, data: dict) -> Path:
    path = root / "input.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    return path


def test_publish_preserves_precise_values_gaps_and_existing_reader_contract(tmp_path):
    source = write_input(tmp_path, projection())
    raw = source.read_bytes()
    binding = publisher.publish(tmp_path, source)
    assert binding == {
        "path": f"reports/paper/overview/{hashlib.sha256(raw).hexdigest()}.json",
        "sha256": hashlib.sha256(raw).hexdigest(),
    }
    assert (tmp_path / binding["path"]).read_bytes() == raw
    assert json.loads((tmp_path / "config/paper-overview-dashboard.json").read_text()) == binding
    reading = load_paper_overview(tmp_path)
    assert reading["available"]
    assert reading["snapshot"]["rows"][0]["return_pct"] == 10.004
    assert reading["snapshot"]["rows"][1]["capital_usd"] is None
    assert reading["daily"][-1]["pnl_usd"] is None
    assert reading["charts"]["pnl_usd"]["bars"][-1]["value"] is None


def test_new_strategy_publishes_without_fixed_count_and_preserves_old_artifact(tmp_path):
    data = projection()
    source = write_input(tmp_path, data)
    previous = publisher.publish(tmp_path, source)
    previous_raw = (tmp_path / previous["path"]).read_bytes()
    snapshot = data["snapshot"]
    new = copy.deepcopy(snapshot["rows"][0])
    new.update(
        id="future_strategy/v2", capital_usd=50, pnl_usd=20, precise_pnl_usd=20, return_pct=40
    )
    snapshot["rows"].append(new)
    snapshot.update(capital_usd=190, pnl_usd=35.5, return_pct=35.5 / 190 * 100)
    current = publisher.publish(tmp_path, write_input(tmp_path, data))
    assert current != previous
    assert (tmp_path / previous["path"]).read_bytes() == previous_raw
    assert len(load_paper_overview(tmp_path)["snapshot"]["rows"]) == 3


def test_identical_publication_keeps_immutable_artifact(tmp_path):
    source = write_input(tmp_path, projection())
    binding = publisher.publish(tmp_path, source)
    artifact = tmp_path / binding["path"]
    original_inode = artifact.stat().st_ino
    assert publisher.publish(tmp_path, source) == binding
    assert artifact.stat().st_ino == original_inode


@pytest.mark.parametrize(
    "identity",
    ["../outside", "pool/../x", "/root/x", "a\\b", "a%2Fb", "a//b", "", "_new", "-new", "a" * 241],
)
def test_unsafe_row_identity_rejected_before_publication(tmp_path, identity):
    data = projection()
    data["snapshot"]["rows"][0]["id"] = identity
    with pytest.raises(ValueError, match="safe unique"):
        publisher.publish(tmp_path, write_input(tmp_path, data))
    assert not (tmp_path / "config").exists()
    assert not (tmp_path / "reports").exists()


@pytest.mark.parametrize("identity", ["a.foo:a/bar-b", "a" * 240])
def test_published_ids_are_displayable_with_adapter_convention(tmp_path, identity):
    from open_composer.cockpit.data.paper_dashboard import build_paper_dashboard

    data = projection()
    data["snapshot"]["rows"][0]["id"] = identity
    publisher.publish(tmp_path, write_input(tmp_path, data))
    dashboard = build_paper_dashboard(load_paper_overview(tmp_path))
    assert any(row["id"] == identity for row in dashboard["rows"])


def test_duplicate_row_identity_rejected():
    data = projection()
    data["snapshot"]["rows"][1]["id"] = data["snapshot"]["rows"][0]["id"]
    with pytest.raises(ValueError, match="safe unique"):
        publisher.validate(data)


@pytest.mark.parametrize(
    ("field", "value"),
    [("adjustment_usd", 0.51), ("unassigned_capital_usd", 39.99), ("return_pct", 100)],
)
def test_inconsistent_totals_and_returns_rejected(field, value):
    data = projection()
    data["snapshot"][field] = value
    with pytest.raises(ValueError, match="reconcile"):
        publisher.validate(data)


def test_return_uses_precise_row_pnl_instead_of_rounded_display_value():
    data = projection()
    data["snapshot"]["rows"][0]["return_pct"] = 10
    with pytest.raises(ValueError, match="return_pct does not reconcile"):
        publisher.validate(data)


def test_null_row_pnl_cannot_be_published_as_zero_contribution():
    data = projection()
    data["snapshot"]["rows"][0].update(pnl_usd=None, precise_pnl_usd=None, return_pct=None)
    with pytest.raises(ValueError, match="requires every row"):
        publisher.validate(data)
    data["snapshot"].update(
        pnl_usd=None, return_pct=None, adjustment_usd=None, missing=["pool/first"]
    )
    publisher.validate(data)


def test_missing_capital_keeps_supported_dollars_without_inventing_percent():
    data = projection()
    point = data["daily"][0]
    point.update(capital_usd=None, return_pct=None, capital_missing=["pool"])
    publisher.validate(data)
    point["return_pct"] = 0
    with pytest.raises(ValueError, match="requires PnL and positive capital"):
        publisher.validate(data)


@pytest.mark.parametrize(
    "change", ["empty", "duplicate", "reverse", "invalid", "future", "gap_value"]
)
def test_invalid_daily_sequence_or_filled_gap_rejected(change):
    data = projection()
    if change == "empty":
        data["daily"] = []
    elif change == "duplicate":
        data["daily"][1]["day"] = data["daily"][0]["day"]
    elif change == "reverse":
        data["daily"].reverse()
    elif change == "invalid":
        data["daily"][0]["day"] = "2026-02-30"
    elif change == "future":
        data["daily"][1]["day"] = "2026-10-28"
    else:
        data["daily"][1].update(pnl_usd=0, return_pct=0)
    with pytest.raises(ValueError):
        publisher.validate(data)


@pytest.mark.parametrize("schema", [2, True, "1"])
def test_only_schema_v1_is_accepted(schema):
    data = projection()
    data["schema_version"] = schema
    with pytest.raises(ValueError, match="schema_version"):
        publisher.validate(data)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_values_in_any_field_rejected(tmp_path, value):
    data = projection()
    data["extra_evidence"] = {"nested": [value]}
    with pytest.raises(ValueError, match="finite"):
        publisher.publish(tmp_path, write_input(tmp_path, data))


def test_duplicate_json_keys_rejected(tmp_path):
    source = write_input(tmp_path, projection())
    source.write_text(
        source.read_text().replace(
            '"schema_version": 1,', '"schema_version": 1, "schema_version": 1,'
        )
    )
    with pytest.raises(ValueError, match="duplicate JSON key"):
        publisher.publish(tmp_path, source)


def test_oversize_input_rejected_before_any_output(tmp_path):
    source = tmp_path / "large.json"
    source.write_bytes(b" " * (publisher.MAX_BYTES + 1))
    with pytest.raises(ValueError, match="2 MiB"):
        publisher.publish(tmp_path, source)
    assert not (tmp_path / "config").exists()


def test_rejected_input_preserves_previous_binding(tmp_path):
    source = write_input(tmp_path, projection())
    publisher.publish(tmp_path, source)
    config = tmp_path / "config/paper-overview-dashboard.json"
    previous = config.read_bytes()
    bad = projection()
    bad["snapshot"]["return_pct"] = 999
    with pytest.raises(ValueError):
        publisher.publish(tmp_path, write_input(tmp_path, bad))
    assert config.read_bytes() == previous


def test_failed_binding_swap_preserves_previous_config_and_sealed_snapshots(tmp_path, monkeypatch):
    source = write_input(tmp_path, projection())
    old = publisher.publish(tmp_path, source)
    config = tmp_path / "config/paper-overview-dashboard.json"
    previous = config.read_bytes()
    data = projection()
    data["generated_at"] = "2026-10-27T04:21:10+00:00"

    def fail_replace(*_):
        raise OSError("simulated atomic swap failure")

    monkeypatch.setattr(publisher.os, "replace", fail_replace)
    with pytest.raises(OSError, match="swap failure"):
        publisher.publish(tmp_path, write_input(tmp_path, data))
    assert config.read_bytes() == previous
    assert (tmp_path / old["path"]).exists()
    assert len(list((tmp_path / "reports/paper/overview").glob("*.json"))) == 2
    assert not list(tmp_path.rglob(".paper-overview-*"))


def test_changed_content_addressed_artifact_is_not_overwritten(tmp_path):
    source = write_input(tmp_path, projection())
    binding = publisher.publish(tmp_path, source)
    artifact = tmp_path / binding["path"]
    artifact.write_text("corrupt retained artifact")
    with pytest.raises(ValueError, match="immutable overview"):
        publisher.publish(tmp_path, source)
    assert artifact.read_text() == "corrupt retained artifact"


def test_output_directory_cannot_escape_project(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "reports").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="outside the project"):
        publisher.publish(root, write_input(root, projection()))
    assert not list(outside.iterdir())
