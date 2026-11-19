"""Read-only controls for the existing six paper target maintenance scripts."""

import hashlib
import json
import math
from datetime import UTC, datetime
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
            page = load(checked(page["response"]))
        for kind, rows in page["corporate_actions"].items():
            for row in rows:
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
    original = normalized(retained["current_actions"])
    master = {r["id"]: r for r in original}
    known_alias = {r["id"]: r for r in original if r["economic_date"] is None}
    for event in action_batch(load(OLD / "current-source.json")):
        master[event["id"]] = event
    _, target, baseline = active_baseline()
    if "retained_action_lineage" in target:
        for value in load(checked(target["retained_action_lineage"]))["events"]:
            event = {k: value[k] for k in ["id", "kind", "terms", "economic_date"]}
            master[event["id"]] = event
    frozen = {}
    for event in action_batch(source):
        old = master.get(event["id"])
        day = event["economic_date"]
        terms = event["terms"]
        rate = terms.get("rate")
        cash = (
            event["kind"] == "cash_dividends"
            and isinstance(rate, (int, float))
            and math.isfinite(rate)
            and rate >= 0
        )
        if (
            (old is not None and old != event)
            or (old is None and (not day or day <= baseline["reference_day"] or not cash))
            or (day and reference_day < day <= application_day and not cash)
        ):
            for key in ("symbol", "old_symbol", "new_symbol"):
                if terms.get(key):
                    frozen[terms[key]] = f"unresolved_{event['kind']}"
            continue
        master[event["id"]] = event
    return dict(
        reference_day=reference_day,
        application_day=application_day,
        events=list(master.values()),
        frozen_symbols=frozen,
        current_source=binding(root / "current-source.json"),
        retained_source=binding(T / "input/BASE/output.json"),
        retained_review=binding(T / "independent-current-input-review-BASE.json"),
        accepted_launch_source=binding(OLD / "current-source.json"),
        known_null_aliases=len(known_alias),
        no_economic_time_from_process_date=True,
    )


def receive_action_lineage(root):
    return load(Path(root) / "current-actions.json")["retained_action_lineage"]
