#!/usr/bin/env python3
"""Bounded, public SEC-only Step5 continuation of T03 in an isolated research lane.

OpenCode runs as ``nobody`` in a scratch directory with an empty environment.
Its tools require interactive permission, which this unattended runner never grants.
The original DS failure circuit and output are deliberately left untouched.
"""

from __future__ import annotations

import argparse
import copy
import fcntl
import hashlib
import json
import os
import re
import shutil
import signal
import sqlite3
import subprocess
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import t03_llm_extract as old

TASK_ID = "DAY3-OPENCODE-STEP5-RECOVERY"
MODEL = "opencode/step-5-preview-free"
LANE = old.DATA / "_llm_step5_research"
TASK = old.ROOT / "reports/research/program/day-goal-20261013/opencode-step5-recovery"
SAMPLE = TASK / "quality-v3-sample.json"
SCRATCH = Path("/tmp/t03-step5-public")
INSTALLED = Path("/root/.local/share/opencode-step5/node_modules/opencode-linux-x64/bin/opencode")
OUTPUT_TOKEN_CEILING = 8192
CONFIG = {
    "permission": {"*": "ask"},
    "share": "disabled",
    "autoupdate": False,
    "plugin": [],
    "provider": {
        "opencode": {
            "models": {
                "step-5-preview-free": {
                    "options": {"reasoningEffort": "low"},
                    "limit": {"context": 1000000, "output": OUTPUT_TOKEN_CEILING},
                }
            }
        }
    },
}
PROMPT_VERSION = "t03-step5-grounding-v3"
CLARIFICATIONS = """Grounding reminders for the unchanged schema:
- Decide customer relationships separately from whether a percentage can be filled.
Retain every explicitly named buyer/dependent customer of the supplier or its disclosed segments.
A customer's segment-only percentage does not permit deleting that customer relationship.
If only a segment share is disclosed, retain the exact customer name, set company-total pct=null,
and use only source-supported basis/year attributes. Never convert segment share to group share.
- Fiscal year requires a supported correspondence for the particular reported percentage.
If a percentage clause is truncated or its year correspondence is ambiguous, fiscal_year=null.
An adjacent ordered list of years does not complete missing correspondence in a truncated clause.
Do not use filing dates, prior knowledge, or likely continuations to fill absent text.
- A heading introducing missing table rows is not a customer or collective group share.
Do not create a customer/group from 'the following customers ...:' if actual rows are absent.
- A collective group percentage must be explicitly stated for that group.
Individual thresholds do not establish its combined percentage.
- When an exact percentage is supplied, use it and lower_bound=false,
even if preceding words mention a threshold.
- Only percentages of the company's total revenue/sales belong in pct.
Segment-only percentages do not establish a total-company share. Receivables-only pct must be null.
Unit counts and shares of assets are not total-company monetary revenue/sales percentages.
Keep the customer relationship when supported, but leave ineligible revenue pct=null.
- Quotes must be literal contiguous fragments of these excerpts.
Do not add punctuation or infer names, years, or missing table data.
"""
PROBE_CALLS = 2  # One 403 permission-shape probe and one successful zero-cost probe.
CALL_CAP = 120
QUALITY_CAP = 32
BULK_CAP = 88
PHASE_WALL_CAP = timedelta(minutes=45)
EXTENSION_DECISION = TASK / "root-v3-projection-recovery-decision.json"
PROJECTION_VERSION = "t03-source-verified-receivables-projection-v1"
REQUEST_TIMEOUT_SECONDS = 360


def sha(value: str | bytes) -> str:
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def append(path: Path, obj: dict) -> None:
    with path.open("a") as fh:
        fh.write(json.dumps(obj, ensure_ascii=False) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def phase_deadline(mode: str, now: datetime) -> datetime:
    """Keep all three old clocks; use the one admitted technical recovery clock."""
    decision_bytes = EXTENSION_DECISION.read_bytes()
    decision = json.loads(decision_bytes)
    admission = json.loads((TASK / "projection-admission-verification.json").read_text())
    if admission["decision_sha256"] != sha(decision_bytes) or decision["verdict"] != (
        "correct_failure_classification_repair_existing_schema_projection_and_continue_unfinished_checks"
    ):
        raise ValueError("extension decision does not match verified admission")
    resources = decision["limits"]
    if (
        resources["total_cap_unchanged"] != CALL_CAP
        or resources["quality_cap_including_probes_unchanged"] != QUALITY_CAP
        or resources["bulk_cap_unchanged"] != BULK_CAP
    ):
        raise ValueError("code call allocation differs from Root decision")
    original = json.loads((LANE / "batch-start.json").read_text())
    original_start = datetime.fromisoformat(original["quality"])
    original_deadline = original_start + PHASE_WALL_CAP
    if original["quality"] != "2026-10-13T07:28:00.958259+00:00":
        raise ValueError("original quality clock changed")
    for filename in ("batch-start.json", "quality-extension-clock.json", "quality-v3-clock.json"):
        if (LANE / filename).read_bytes() != (
            TASK / "before-projection-recovery" / filename
        ).read_bytes():
            raise ValueError(f"historical clock changed: {filename}")
    clock_path = LANE / (
        "projection-recovery-clock.json" if mode == "quality" else "bulk-clock.json"
    )
    seconds = (
        resources["additional_technical_and_remaining_quality_window_seconds"]
        if mode == "quality"
        else resources["bulk_window_seconds_unchanged"]
    )
    expected_seconds = 1800 if mode == "quality" else 2700
    if seconds != expected_seconds:
        raise ValueError("unrecognized admitted phase duration")
    if not clock_path.exists():
        old.retry.write_json(
            clock_path,
            {
                "start_utc": now.isoformat(),
                "deadline_utc": (now + timedelta(seconds=seconds)).isoformat(),
                "duration_seconds": seconds,
                "decision_sha256": sha(decision_bytes),
                "original_quality_start_utc": original["quality"],
                "original_quality_deadline_utc": original_deadline.isoformat(),
                "historical_clock_sha256": {
                    name: sha((LANE / name).read_bytes())
                    for name in (
                        "batch-start.json",
                        "quality-extension-clock.json",
                        "quality-v3-clock.json",
                    )
                },
                "prompt_version": PROMPT_VERSION,
            },
        )
    clock = json.loads(clock_path.read_text())
    start = datetime.fromisoformat(clock["start_utc"])
    deadline = datetime.fromisoformat(clock["deadline_utc"])
    if clock["decision_sha256"] != sha(decision_bytes) or deadline - start != timedelta(
        seconds=seconds
    ):
        raise ValueError("persisted phase clock mismatch; no reset allowed")
    return deadline


def setup_scratch() -> str:
    for name in ("config", "data", "cache", "state", "work"):
        (SCRATCH / name).mkdir(parents=True, exist_ok=True)
    binary = SCRATCH / "opencode"
    installed_hash = sha(INSTALLED.read_bytes())
    if not binary.exists() or sha(binary.read_bytes()) != installed_hash:
        shutil.copy2(INSTALLED, binary)
    config = SCRATCH / "config/opencode.json"
    config.write_text(json.dumps(CONFIG) + "\n")
    for path in (SCRATCH, *SCRATCH.rglob("*")):
        os.chown(path, 65534, 65534)
    return installed_hash


def cli(*args: str, timeout: float = 240) -> subprocess.CompletedProcess[str]:
    env = [
        "PATH=/usr/bin:/bin",
        f"XDG_CONFIG_HOME={SCRATCH / 'config'}",
        f"XDG_DATA_HOME={SCRATCH / 'data'}",
        f"XDG_CACHE_HOME={SCRATCH / 'cache'}",
        f"XDG_STATE_HOME={SCRATCH / 'state'}",
        f"OPENCODE_CONFIG={SCRATCH / 'config/opencode.json'}",
    ]
    command = ["runuser", "-u", "nobody", "--", "env", "-i", *env, str(SCRATCH / "opencode"), *args]
    return run_owned_process(command, cwd=SCRATCH / "work", timeout=timeout)


def run_owned_process(
    command: list[str], *, cwd: Path, timeout: float
) -> subprocess.CompletedProcess[str]:
    """Bound and clean only the fresh process group belonging to this invocation."""
    process = subprocess.Popen(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        # This PGID was created by this invocation; never select processes by broad names.
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            stdout, stderr = process.communicate(timeout=1)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            stdout, stderr = process.communicate(timeout=1)
        # A wrapper can exit before a descendant that closed its output pipes.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        raise subprocess.TimeoutExpired(command, timeout, output=stdout, stderr=stderr) from None
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def session_metadata(title: str) -> dict:
    """Read only this public scratch session's native metadata; never expose reasoning text."""
    database = SCRATCH / "data/opencode/opencode.db"
    with sqlite3.connect(f"file:{database}?mode=ro", uri=True, timeout=2) as connection:
        found = connection.execute("select id from session where title=?", (title,)).fetchone()
        if not found:
            return {}
        session_id = found[0]
        messages = [
            json.loads(row[0])
            for row in connection.execute(
                "select data from message where session_id=? order by time_created", (session_id,)
            )
        ]
        assistant = next((m for m in reversed(messages) if m.get("role") == "assistant"), {})
        user = next((m for m in messages if m.get("role") == "user"), {})
        parts = []
        for (data,) in connection.execute(
            "select data from part where session_id=?", (session_id,)
        ):
            part = json.loads(data)
            parts.append(
                {
                    "type": part.get("type"),
                    "time": part.get("time"),
                    "text_chars": len(part.get("text", "")),
                }
            )
        return {
            "session_id": session_id,
            "assistant": {
                k: assistant.get(k)
                for k in ("providerID", "modelID", "time", "finish", "tokens", "cost")
            },
            "user_model": user.get("model"),
            "user_variant": user.get("variant"),
            "parts": parts,
        }


def done_accessions() -> set[str]:
    done = old.done_accessions()
    quarantine_path = TASK / "quality-rejections.json"
    rejected = json.loads(quarantine_path.read_text()) if quarantine_path.exists() else {}
    quarantine = set(rejected.get("accessions", []))
    rejected_calls = set(rejected.get("call_ids", []))
    reclassified = rejected.get("canonical_acceptances", {})
    for row in read_jsonl(LANE / "part_step5.jsonl"):
        call_id = row.get("provenance", {}).get("call_id")
        rejected_row = (
            call_id in rejected_calls if rejected_calls else row["accession"] in quarantine
        )
        accepted_projection = reclassified.get(call_id)
        if (
            accepted_projection
            and row.get("provenance", {}).get("canonical_reclassification")
            and accepted_projection["canonical_sha256"]
            == sha(json.dumps(row.get("parsed"), sort_keys=True))
        ):
            rejected_row = False
        if row.get("parsed") is not None and not rejected_row:
            done.add(row["accession"])
    return done


def candidates(mode: str, selected: list[str] | None = None) -> list[tuple[dict, str]]:
    filings = {}
    for path in sorted(old.SNIP.glob("part_main_*.jsonl")):
        for line in path.read_text().splitlines():
            if line.strip():
                row = json.loads(line)
                row["_source_part"] = str(path.relative_to(old.ROOT))
                row["_source_row_sha256"] = sha(line)
                filings[row["accession"]] = row
    done = done_accessions()
    if mode == "quality":
        frozen = json.loads(SAMPLE.read_text())
        rejections = json.loads((TASK / "quality-rejections.json").read_text())
        rejected_calls = set(rejections.get("call_ids", []))
        reclassified = rejections.get("canonical_acceptances", {})
        completed_v3 = {
            row["accession"]
            for row in read_jsonl(LANE / "part_step5.jsonl")
            if row.get("parsed") is not None
            and row.get("provenance", {}).get("prompt_version") == PROMPT_VERSION
            and (
                row.get("provenance", {}).get("call_id") not in rejected_calls
                or (
                    row.get("provenance", {}).get("canonical_reclassification")
                    and reclassified.get(row["provenance"]["call_id"], {}).get("canonical_sha256")
                    == sha(json.dumps(row["parsed"], sort_keys=True))
                )
            )
        }
        result = []
        cases = frozen["cases"]
        if selected:
            by_accession = {x["accession"]: x for x in cases}
            cases = [by_accession[accession] for accession in selected]
        for item in cases:
            r = filings[item["accession"]]
            text = "\n---\n".join(s for s in r["snippets"] if not old.is_negative(s))[:7000]
            if item.get("quality_only_negative"):
                text = "\n---\n".join(r["snippets"])[:7000]
            if sha(text) != item["input_sha256"]:
                raise ValueError(f"frozen sample changed: {r['accession']}")
            if r["accession"] not in completed_v3:
                result.append((r, text))
        return result
    result = []
    for r in filings.values():
        if r["accession"] in done or r["status"] != "ok" or not r["snippets"]:
            continue
        text = "\n---\n".join(s for s in r["snippets"] if not old.is_negative(s))[:7000]
        if text:
            result.append((r, text))
    return sorted(result, key=lambda pair: pair[0]["filing_date"], reverse=True)


def validate(parsed: dict | None, source: str) -> list[str]:
    if parsed is None:
        return ["unparsable_json"]
    if type(parsed.get("no_major_customer")) is not bool:
        return ["bad_no_major_customer"]
    customers = parsed.get("customers")
    if not isinstance(customers, list) or len(customers) > 15:
        return ["bad_customers"]
    issues = []
    if parsed["no_major_customer"] and customers:
        issues.append("negative_with_customers")
    for index, row in enumerate(customers):
        if not isinstance(row, dict) or set(row) != {
            "name",
            "type",
            "pct",
            "basis",
            "lower_bound",
            "fiscal_year",
            "quote",
        }:
            issues.append(f"row_{index}_schema")
            continue
        if row["type"] not in {"company", "government", "anonymous", "group"}:
            issues.append(f"row_{index}_type")
        if row["basis"] not in {"revenue", "receivables", "unknown"}:
            issues.append(f"row_{index}_basis")
        if row["name"] is not None and (
            not isinstance(row["name"], str) or row["name"] not in source
        ):
            issues.append(f"row_{index}_name_not_exact")
        if type(row["lower_bound"]) is not bool:
            issues.append(f"row_{index}_lower_bound")
        if row["pct"] is not None and (
            type(row["pct"]) not in {float, int} or not 0 <= row["pct"] <= 100
        ):
            issues.append(f"row_{index}_pct")
        if row["basis"] == "receivables" and row["pct"] is not None:
            issues.append(f"row_{index}_receivables_pct")
        if row["fiscal_year"] is not None and (
            type(row["fiscal_year"]) is not int or not 1900 <= row["fiscal_year"] <= 2100
        ):
            issues.append(f"row_{index}_year")
        if (
            not isinstance(row["quote"], str)
            or len(row["quote"]) >= 220
            or row["quote"] not in source
        ):
            issues.append(f"row_{index}_quote_not_exact")
        elif row["quote"].rstrip().endswith(":") or row["quote"].rstrip(".") + ":" in source:
            issues.append(f"row_{index}_header_not_evidence")
        if (
            row["type"] == "group"
            and isinstance(row["name"], str)
            and re.fullmatch(r"(?:the )?following customers", row["name"], re.I)
        ):
            issues.append(f"row_{index}_heading_label_not_group")
    return issues


def receivables_quote_supported(row: dict, source: str) -> bool:
    """Require a literal, unambiguous receivables quote; never fix a false basis."""
    quote = row.get("quote")
    if not isinstance(quote, str) or quote not in source:
        return False
    return bool(
        re.search(r"\b(?:accounts?\s+receivables?|receivables?)\b", quote, re.I)
    ) and not bool(re.search(r"\b(?:revenues?|sales)\b", quote, re.I))


def normalize_reply(parsed: dict | None, source: str) -> tuple[dict | None, list[str]]:
    """Project source-supported receivables shares into the original revenue-only pct."""
    if parsed is None or not isinstance(parsed.get("customers"), list):
        return parsed, []
    value = copy.deepcopy(parsed)
    changes = []
    for index, row in enumerate(value["customers"]):
        if not isinstance(row, dict):
            continue
        if (
            row.get("basis") == "receivables"
            and row.get("pct") is not None
            and receivables_quote_supported(row, source)
            and type(row["pct"]) in {int, float}
            and row["pct"]
            in [
                float(n)
                for n in re.findall(r"(\d+(?:\.\d+)?)\s*(?:%|percent\b)", row["quote"], re.I)
            ]
        ):
            row["pct"] = None
            changes.append(f"row_{index}_receivables_pct_to_null")
    return value, changes


def anchor_quote_fragments(parsed: dict | None, source: str) -> tuple[dict | None, list[str]]:
    """Select an exact source fragment; never repair an entity, number, basis, or year."""
    if parsed is None or not isinstance(parsed.get("customers"), list):
        return parsed, []
    value = copy.deepcopy(parsed)
    changes = []
    for index, row in enumerate(value["customers"]):
        if not isinstance(row, dict):
            continue
        quote = row.get("quote")
        if (
            isinstance(quote, str)
            and quote not in source
            and quote.endswith(".")
            and quote[:-1] in source
        ):
            row["quote"] = quote[:-1]
            changes.append(f"row_{index}_remove_non_source_terminal_period")
        elif (
            isinstance(quote, str)
            and quote
            and quote not in source
            and quote[0].swapcase() + quote[1:] in source
        ):
            row["quote"] = quote[0].swapcase() + quote[1:]
            changes.append(f"row_{index}_anchor_source_initial_letter_case")
    return value, changes


def call_one(row: dict, source: str, mode: str, binary_hash: str, deadline: datetime) -> dict:
    now = datetime.now(UTC)
    call_id = uuid.uuid4().hex
    prompt = (
        old.SYSTEM
        + "\n\n"
        + CLARIFICATIONS
        + "\n"
        + old.INSTRUCTION
        + source
        + "\n\nDo not use tools or access files. Return concise JSON only."
    )
    # The durable reservation is deliberately before network access. A crash counts conservatively.
    append(
        old.LEDGER,
        {
            "t": now.isoformat(),
            "status": "reserved",
            "task_id": TASK_ID,
            "provider": "opencode",
            "model": MODEL,
            "phase": mode,
            "prompt_version": PROMPT_VERSION,
            "decision_sha256": sha(EXTENSION_DECISION.read_bytes()),
            "call_id": call_id,
        },
    )
    error = None
    partial_stdout = ""
    request_timeout = min(
        REQUEST_TIMEOUT_SECONDS, max(1, (deadline - datetime.now(UTC)).total_seconds() - 5)
    )
    try:
        result = cli(
            "run",
            "--pure",
            "--model",
            MODEL,
            "--format",
            "json",
            "--variant",
            "low",
            "--title",
            f"t03-step5-{call_id[:12]}",
            prompt,
            timeout=request_timeout,
        )
        events = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    except (subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        result = None
        events = []
        error = type(exc).__name__
        if isinstance(exc, subprocess.TimeoutExpired) and exc.stdout:
            partial_stdout = (
                exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else exc.stdout
            )
    event_path = LANE / "events" / f"{call_id}.jsonl"
    event_path.write_text(result.stdout if result else partial_stdout)
    if result and result.stderr:
        event_path.with_suffix(".stderr.txt").write_text(result.stderr[:4000])
    if result and result.returncode:
        error = "cli_exit_nonzero"
    text = "".join((e.get("part") or {}).get("text", "") for e in events if e.get("type") == "text")
    finish = next(
        ((e.get("part") or {}) for e in reversed(events) if e.get("type") == "step_finish"), {}
    )
    err_event = next((e.get("error") for e in events if e.get("type") == "error"), None)
    permission_events = [
        e.get("type")
        for e in events
        if "permission" in e.get("type", "") or e.get("type") == "tool_use"
    ]
    if err_event:
        error = (
            err_event.get("name")
            if err_event.get("name") in {"APIError", "PermissionError"}
            else "provider_error"
        )
    error_data = (err_event or {}).get("data", {}) if isinstance(err_event, dict) else {}
    status = error_data.get("statusCode") if isinstance(error_data, dict) else None
    if status is None and finish and result is not None and result.returncode == 0:
        status = 200
    headers = error_data.get("responseHeaders", {}) if isinstance(error_data, dict) else {}
    retry_after = headers.get("retry-after") if isinstance(headers, dict) else None
    recovery_at = None
    if isinstance(retry_after, str):
        parsed_retry = old.retry._header_time(retry_after, datetime.now(UTC), reset=False)
        recovery_at = parsed_retry.isoformat() if parsed_retry else None
    session = next((e.get("sessionID") for e in events if e.get("sessionID")), None)
    actual_model = None
    cost = finish.get("cost")
    tokens = finish.get("tokens")
    native = session_metadata(f"t03-step5-{call_id[:12]}")
    event_path.with_suffix(".session.json").write_text(json.dumps(native) + "\n")
    session = native.get("session_id", session)
    assistant = native.get("assistant", {})
    actual_model = {"provider": assistant.get("providerID"), "model": assistant.get("modelID")}
    if assistant.get("time", {}).get("completed") and assistant.get("finish"):
        cost = assistant.get("cost", cost)
        tokens = assistant.get("tokens", tokens)
    model_parsed = old.parse_reply(text)
    raw_schema_issues = validate(model_parsed, source)
    anchored, quote_changes = anchor_quote_fragments(model_parsed, source)
    parsed, projection_changes = normalize_reply(anchored, source)
    normalizations = quote_changes + projection_changes
    issues = validate(parsed, source)
    if parsed is not None:
        for index, customer in enumerate(parsed.get("customers", [])):
            if (
                isinstance(customer, dict)
                and customer.get("basis") == "receivables"
                and not receivables_quote_supported(customer, source)
            ):
                issues.append(f"row_{index}_receivables_basis_not_grounded")
    completion_reason = assistant.get("finish") or finish.get("reason")
    if completion_reason == "length":
        issues = (
            ["generation_budget_exhausted_before_json"] if not text else ["generation_truncated"]
        )
    if result is None or result.returncode or err_event or permission_events:
        issues.append("provider_or_permission_failure")
    if cost != 0:
        issues.append("nonzero_or_unverified_cost")
    if actual_model != {"provider": "opencode", "model": "step-5-preview-free"}:
        issues.append("actual_model_unverified")
    outcome = {
        "call_id": call_id,
        "t": now.isoformat(),
        "completed_at": datetime.now(UTC).isoformat(),
        "phase": mode,
        "accession": row["accession"],
        "source_part": row["_source_part"],
        "source_row_sha256": row["_source_row_sha256"],
        "source_sha256": sha(source),
        "prompt_sha256": sha(prompt),
        "prompt_version": PROMPT_VERSION,
        "config_sha256": sha(json.dumps(CONFIG, sort_keys=True)),
        "reasoning_variant": "low",
        "output_token_ceiling": OUTPUT_TOKEN_CEILING,
        "base_prompt_sha256": old.prompt_hash(),
        "provider": "opencode",
        "requested_model": MODEL,
        "actual_model": actual_model,
        "immutable_model_version": None,
        "cli_version": "1.19.0",
        "cli_sha256": binary_hash,
        "cli_exit_code": result.returncode if result else None,
        "completion_reason": completion_reason,
        "phase_deadline_utc": deadline.isoformat(),
        "request_timeout_seconds": request_timeout,
        "decision_sha256": sha(EXTENSION_DECISION.read_bytes()),
        "http_status": status,
        "error_class": error,
        "recovery_at": recovery_at,
        "permission_events": permission_events,
        "tokens": tokens,
        "cost_usd_reported": cost,
        "normalizations": normalizations,
        "raw_schema_issues": raw_schema_issues,
        "canonical_schema_issues": issues,
        "projection_version": PROJECTION_VERSION,
        "implementation_sha256": sha(Path(__file__).read_bytes()),
        "raw_answer_sha256": sha(text),
        "canonical_sha256": sha(json.dumps(parsed, sort_keys=True)),
        "issues": issues,
        "session_id": session,
        "event_path": str(event_path.relative_to(old.ROOT)),
    }
    append(LANE / "requests.jsonl", outcome)
    output = {
        "accession": row["accession"],
        "cik": row["cik"],
        "filing_date": row["filing_date"],
        "acceptance_datetime": row["acceptance_datetime"],
        "parsed": parsed if not issues else None,
        "raw": text[:4000] if issues else None,
        "raw_model_parsed": model_parsed,
        "provenance": outcome,
    }
    append(LANE / "part_step5.jsonl", output)
    return outcome


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("quality", "bulk"), required=True)
    parser.add_argument("--limit", type=int, required=True)
    parser.add_argument(
        "--accessions", help="Frozen quality sample IDs in order; permits positive regression"
    )
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("limit must be positive")
    LANE.mkdir(parents=True, exist_ok=True)
    (LANE / "events").mkdir(exist_ok=True)
    with old.LOCK.open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        review_path = TASK / "quality-review.json"
        review = json.loads(review_path.read_text()) if review_path.exists() else {}
        if review.get("prompt_version") != PROMPT_VERSION:
            print("v3 review admission missing; no provider call")
            return 20
        if args.phase == "quality" and review.get("stop_latched"):
            print("quality stopped: source-reviewed semantic failure; no provider call")
            return 20
        if args.phase == "bulk":
            if (
                review.get("decision") != "pass"
                or review.get("prompt_version") != PROMPT_VERSION
                or review.get("passed_cases") != 14
                or review.get("quality_manifest_sha256") != sha(SAMPLE.read_bytes())
                or not review.get("actual_free_model_and_zero_cost_verified")
            ):
                print("bulk blocked: quality review has not passed")
                return 20
        shared = [r for r in read_jsonl(old.LEDGER) if r.get("task_id") == TASK_ID]
        phase_count = sum(r.get("phase") == args.phase for r in shared)
        phase_cap = QUALITY_CAP - PROBE_CALLS if args.phase == "quality" else BULK_CAP
        if len(shared) >= CALL_CAP or phase_count >= phase_cap:
            print("request cap exhausted")
            return 20
        deadline = phase_deadline(args.phase, datetime.now(UTC))
        if datetime.now(UTC) >= deadline:
            print("phase wall cap reached; no setup or provider call", flush=True)
            return 75
        binary_hash = setup_scratch()
        todo = candidates(args.phase, args.accessions.split(",") if args.accessions else None)
        max_calls = min(args.limit, phase_cap - phase_count, CALL_CAP - len(shared))
        print(
            json.dumps(
                {
                    "phase": args.phase,
                    "pending": len(todo),
                    "admitted_calls": max_calls,
                    "old_done": len(old.done_accessions()),
                    "new_done": len(done_accessions() - old.done_accessions()),
                }
            ),
            flush=True,
        )
        completed = 0
        for row, source in todo[:max_calls]:
            now = datetime.now(UTC)
            if (deadline - now).total_seconds() <= 8:
                print("phase wall cap reached", flush=True)
                return 75
            used = old.calls_in_window(now)
            if len(used) >= old.CAP_PER_5H:
                print("shared rolling 880/5h cap reached", flush=True)
                return 75
            outcome = call_one(row, source, args.phase, binary_hash, deadline)
            completed += 1
            print(
                json.dumps(
                    {
                        "n": completed,
                        "accession": row["accession"],
                        "issues": outcome["issues"],
                        "cost": outcome["cost_usd_reported"],
                    }
                ),
                flush=True,
            )
            if outcome["issues"]:
                return 21
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
