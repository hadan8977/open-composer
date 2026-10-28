# ruff: noqa: E501 -- Frozen scientific, provenance and protocol literals.
"""Task-local prospective evidence; imports have no source or economic effects."""

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path

OUT = Path(__file__).resolve().parent
PARENT = OUT.parent
REPO = OUT.parents[4]
BASE = PARENT / "common-factor-residual-momentum-20261017"
SHARE = PARENT / "dia-shareholder-account-20261017"
COHORT = PARENT / "peer-insider-cohort-transfer-20261016"
FUND = REPO / "reports/research/program/fundamental-momentum-model-20261016"
META = REPO / "reports/research/program/fundamental-metadata-attribution-20261016"
TASK = "DIA-PROSPECTIVE-READONLY-20261017"
OWNER = "7b109880-ac40-447e-b2a6-f0ed1266ebac"
ITERATION = "t20261017_dia_prospective_readonly"
POLICIES = ["RESID_STD", "TOTAL_STD", "MOM12_1"]


def now():
    return datetime.now(UTC).isoformat()


def load(path):
    return json.loads(Path(path).read_text())


def binding(path):
    p = Path(path).resolve()
    b = p.read_bytes()
    return dict(path=str(p), bytes=len(b), sha256=hashlib.sha256(b).hexdigest())


def save(path, value):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        raise FileExistsError("Append-only evidence already exists: " + str(p))
    data = (json.dumps(value, indent=2, allow_nan=False, default=str) + "\n").encode()
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())


def authority():
    h = load(REPO / "reports/research/control/owner-compute-hold.json")
    assert h["research_paused"] is False
    r = h["dia_prospective_readonly_assignment_20261017"]
    b = binding(REPO / r["path"])
    assert (
        b["sha256"] == r["sha256"]
        and b["bytes"] == r["bytes"]
        and r["complete_task_continuation_authorized"]
    )
    return b
