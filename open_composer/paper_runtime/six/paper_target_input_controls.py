"""Read-only controls for the existing six paper target maintenance scripts."""

import hashlib
import json
import math
from datetime import UTC, date, datetime
from pathlib import Path

from open_composer.paper_runtime.paths import repo_root, runtime_root

REPO = repo_root()
OLD = REPO / "reports/research/program/paper-launch-20min-20261021"
T = (
    REPO
    / "reports/research/program/owner-profit-delivery-plan-20261017/current-paper-science-20261020"
)


def load(path):
    return json.loads(Path(path).read_text())


def binding(path):
    p = Path(path)
    b = p.read_bytes()
    return dict(path=str(p.resolve()), bytes=len(b), sha256=hashlib.sha256(b).hexdigest())


def checked(row):
    assert binding(row["path"]) == row
    return Path(row["path"])


def receive_current_paper_maintenance():
    p = REPO / "reports/research/control/owner-compute-hold.json"
    body = p.read_bytes()
    h = json.loads(body)
    status = str(h.get("status", ""))
    assert not status.startswith("owner_all_work_paused") and status not in [
        "paused",
        "all_work_paused",
    ], "Current owner all-work/paper pause"
    assert h.get("existing_paper_operations_allowed") is True, (
        "Current paper maintenance is not allowed"
    )
    scope = h.get("paper_launch_20min_20261021", {})
    assert scope.get("necessary_current_paper_input_inference_and_repair_allowed") is True
    return dict(
        path=str(p),
        bytes=len(body),
        sha256=hashlib.sha256(body).hexdigest(),
        status=status,
        received_at=datetime.now(UTC).isoformat(),
    )


def normalized(value):
    pairs = (
        [(k, r) for k, rows in value.items() for r in rows]
        if isinstance(value, dict)
        else [(r["kind"], r.get("terms", r.get("raw"))) for r in value]
    )
    result = []
    for kind, raw in pairs:
        assert isinstance(raw, dict) and isinstance(raw["id"], str)
        day = raw.get("ex_date") or raw.get("effective_date")
        result.append(dict(id=raw["id"], kind=kind, terms=raw, economic_date=day))
    return result


def action_batch(source):
    request = next(r for r in source["data"] if r["group"] == "core" and r["key"] == "actions")
    out = {}
    for page in request["pages"]:
        if "response" in page:
            meta = load(checked(page["metadata"]))
            assert meta["response"] == page["response"] and meta["status_code"] == 200
            page = load(checked(page["response"]))
        for kind, rows in page["corporate_actions"].items():
            for row in rows:
                assert row["id"] not in out
                out[row["id"]] = (kind, row)
    return [
        dict(
            id=raw["id"],
            kind=kind,
            terms=raw,
            economic_date=raw.get("ex_date") or raw.get("effective_date"),
        )
        for kind, raw in out.values()
    ]


def active_baseline():
    target = load(runtime_root(REPO) / "targets/LSTM.json")
    source = load(checked(target["source"]))
    folder = Path(target["source"]["path"]).parent
    assert folder == OLD or folder.is_relative_to(REPO / "reports/paper/diagnostics")
    return folder, target, source


def build_action_lineage(root, reference_day, application_day):
    root = Path(root)
    source = load(root / "current-source.json")
    retained = load(T / "input/BASE/output.json")
    proof = load(T / "independent-current-input-review-BASE.json")
    assert proof["independent"] is True and proof["source_linked_controls_accepted"] is True
    assert (
        proof["target"] == proof["derived_control_witness"] == binding(T / "input/BASE/output.json")
    )
    original = normalized(retained["current_actions"])
    master = {r["id"]: r for r in original}
    assert len(master) == len(original)
    # Only the exact original accepted same-CUSIP aliases may lack an economic date.
    known_alias = {r["id"]: r for r in original if r["economic_date"] is None}
    assert len(known_alias) == 3
    for r in known_alias.values():
        raw = r["terms"]
        assert (
            r["kind"] == "name_changes"
            and raw["old_cusip"] == raw["new_cusip"]
            and raw["old_symbol"] != raw["new_symbol"]
        )
    launch = load(OLD / "current-source.json")
    assert load(OLD / "target-production-result.json")["source"] == binding(
        OLD / "current-source.json"
    )
    for event in action_batch(launch):
        if event["id"] in master:
            assert master[event["id"]] == event
        master[event["id"]] = event
    folder, target, baseline = active_baseline()
    if "retained_action_lineage" in target:
        prior = load(checked(target["retained_action_lineage"]))
        for value in prior["events"]:
            event = {k: value[k] for k in ["id", "kind", "terms", "economic_date"]}
            if event["id"] in master:
                assert master[event["id"]] == event
            master[event["id"]] = event
    for event in action_batch(source):
        old = master.get(event["id"])
        day = event["economic_date"]
        if old is not None:
            assert old == event, "Changed previously received action terms"
        else:
            assert day is not None and day > baseline["reference_day"], (
                "New undated/late prior action needs affected reception"
            )
            assert date.fromisoformat(day).isoformat() == day
            assert event["kind"] == "cash_dividends", (
                "Unknown current unit/identity event needs affected reception"
            )
            assert (
                type(event["terms"].get("rate")) in (int, float)
                and math.isfinite(event["terms"]["rate"])
                and event["terms"]["rate"] >= 0
            )
        master[event["id"]] = event
    for event in master.values():
        if event["economic_date"] is None:
            assert event == known_alias.get(event["id"])
        if (
            event["economic_date"] is not None
            and reference_day < event["economic_date"] <= application_day
        ):
            assert event["kind"] == "cash_dividends", "Postreference unit event is unreceived"
    return dict(
        reference_day=reference_day,
        application_day=application_day,
        events=list(master.values()),
        current_source=binding(root / "current-source.json"),
        retained_source=binding(T / "input/BASE/output.json"),
        retained_review=binding(T / "independent-current-input-review-BASE.json"),
        accepted_launch_source=binding(OLD / "current-source.json"),
        known_null_aliases=len(known_alias),
        no_economic_time_from_process_date=True,
    )


def receive_action_lineage(root):
    root = Path(root)
    control = load(root / "current-actions.json")
    row = control["retained_action_lineage"]
    assert checked(row) == root / "action-lineage-QA.json"
    actual = load(row["path"])
    expected = build_action_lineage(root, control["reference_day"], control["application_day"])
    assert actual == expected, "Retained action lineage differs from actual received inputs"
    return row


def require_prior_sequence(root, np):
    root = Path(root)
    qa = load(root / "lstm-input-QA.json")
    prefix = qa["previous_current_sequence"]
    assert prefix["features_bitexact"] is True and prefix["vol_bitexact"] is True, (
        "Prior feature/vol prefix refused"
    )
    assert checked(qa["sequence"]) == root / "current-lstm-sequence.npz"
    with (
        np.load(checked(qa["prior_sequence"]), allow_pickle=False) as prior,
        np.load(root / "current-lstm-sequence.npz", allow_pickle=False) as current,
    ):
        n = len(prior["features"])
        assert n == prefix["rows"] and len(current["features"]) >= n
        assert np.array_equal(current["features"][:n], prior["features"]) and np.array_equal(
            current["vol"][:n], prior["vol"]
        ), "Actual saved prefix differs"
    return qa
