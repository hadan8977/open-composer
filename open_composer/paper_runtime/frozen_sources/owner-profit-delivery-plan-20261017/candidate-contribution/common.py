# ruff: noqa: E501 -- Frozen task contracts and evidence literals.
"""Task-local identities and exact legacy module isolation; no work on import."""

import contextlib
import hashlib
import importlib.util
import json
import math
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

OUT = Path(__file__).resolve().parent
REPO = OUT.parents[4]
PARENT = REPO / "reports/research/program/return-line-replenishment-20261016"
SEQ = REPO / "reports/research/program/dia-sequential-quote-validation-20261017"
SHARE = REPO / "reports/research/program/share-turnover-information-20261017"
ACCOUNT = PARENT / "dia-shareholder-account-20261017"
COHORT = PARENT / "peer-insider-cohort-transfer-20261016"
TASK = "MONDAY-CANDIDATE-CONTRIBUTION-20261019"
ITERATION = "t20261019_monday_candidate_contribution"
OWNER = "7b109880-ac40-447e-b2a6-f0ed1266ebac"
PEER = "93af0483-230a-4632-8b48-c63cd53a01f7"
POLICIES = [
    "MOM1_SEQUENTIAL",
    "WINNER_HIGH_T_SEQUENTIAL",
    "BASE_NO_INTC_STRESS",
    "RESID_WHOLE_NO_INTC_STRESS",
]


def now():
    return datetime.now(UTC).isoformat()


def load(path):
    return json.loads(Path(path).read_text())


def clean(v):
    if type(v).__module__.startswith("numpy"):
        return clean(v.tolist() if v.ndim else v.item())
    if isinstance(v, float) and not math.isfinite(v):
        return None
    if isinstance(v, dict):
        return {k: clean(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [clean(x) for x in v]
    return v


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + f".tmp-{os.getpid()}")
    temp.write_text(json.dumps(clean(value), indent=2, allow_nan=False, ensure_ascii=False) + "\n")
    temp.replace(path)


def binding(path):
    p = Path(path).absolute()
    assert p.resolve() == p, "Canonical file only: " + str(p)
    with p.open("rb") as f:
        h = hashlib.file_digest(f, "sha256").hexdigest()
    return dict(path=str(p), bytes=p.stat().st_size, sha256=h)


def verify(row):
    assert binding(row["path"]) == row, "Changed bound bytes: " + row["path"]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    sys.modules[name] = result
    spec.loader.exec_module(result)
    return result


@contextlib.contextmanager
def legacy(directory):
    names = ["common", "method", "learning", "execution_scope", "quote_adapter", "quotes"]
    old = {n: sys.modules.pop(n, None) for n in names}
    sys.path.insert(0, str(directory))
    try:
        module("common", directory / "common.py")
        yield
    finally:
        sys.path.pop(0)
        for n in names:
            sys.modules.pop(n, None)
            if old[n] is not None:
                sys.modules[n] = old[n]


def authority():
    hold = load(REPO / "reports/research/control/owner-compute-hold.json")
    assert hold["research_paused"] is False
    assert hold["monday_complete_task_assignments_20261017"]["complete_tasks_authorized"]
    decision = load(OUT.parent / "main-decision.json")
    assert any(
        x["task_id"] == TASK and x["owner"] == OWNER and x["complete_task_authorized"]
        for x in decision["work_packages"]
    )
    assert load(OUT / "current-state.json")["owner"] == OWNER


def resources():
    assert os.sched_getaffinity(0) == {0}
    assert all(os.environ.get(k) == "1" for k in ["OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS"])
    group = Path("/proc/self/cgroup").read_text().strip().split(":")[-1]
    base = Path("/sys/fs/cgroup") / group.lstrip("/")
    return {
        n: (base / n).read_text().strip()
        for n in ["memory.max", "memory.swap.max", "memory.current"]
    }
