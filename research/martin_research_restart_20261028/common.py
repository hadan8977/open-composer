"""Task paths and actual authority; imports never launch a financial calculation."""

import hashlib
import json
import sys
from datetime import UTC, datetime
from functools import cache
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
PROGRAM = ROOT / "reports/research/program/martin-quantization-plan-20261021"
CONTINUATION = ROOT / "reports/research/program/martin-decision-loop-model-continuation-20261026"
LEGACY = ROOT / "reports/research/program/martin-learned-payoff-state-20261026"
SEQ = PROGRAM / "resume-20261023/owner-prompt-route-reassessment/sequence-context-information"
F1 = PROGRAM / "execution-5pct/f1"
F2 = PROGRAM / "execution-5pct/f2"
OLD = (
    ROOT
    / "reports/research/program/usic-practitioner-research-20261013"
    / "complete-decision-system-20261014/code"
)
INPUTS = LEGACY / "inputs-v3-attempt01"
for directory in (ROOT, CONTINUATION, LEGACY, SEQ, OLD, F2):
    if str(directory) not in sys.path:
        sys.path.append(str(directory))


def stamp():
    return datetime.now(UTC).isoformat()


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, default=str, indent=2) + "\n")
    temporary.replace(path)


def gate(*, new_start=False, financial=False):
    from open_composer.research.agent_workflow import require_research

    if new_start or financial:
        require_research(ROOT)
    else:
        # An intermediate new-start checkpoint must not corrupt a healthy finite account.
        control = json.loads((ROOT / "control.json").read_text())
        hold = json.loads((ROOT / "reports/research/control/owner-compute-hold.json").read_text())
        if control.get("draft") is not False or control.get("research") is not True:
            raise RuntimeError("Research authority inactive")
        if hold.get("research_paused") or hold.get("research_allowed") is False:
            raise RuntimeError("Actual research hold reached a session boundary")
    if any((OUT / name).exists() for name in ("STOP", "STOP.json")):
        raise RuntimeError("Task STOP")
    if new_start or financial:
        receipt = json.loads((OUT / "scope-review.json").read_text())
        if receipt.get("verdict") != "approve_deep_plan" or not receipt.get("financial_go"):
            raise RuntimeError("Independent component scope review has not released accounts")
        if not receipt.get("reviewer") or receipt.get("author_is_reviewer") is not False:
            raise RuntimeError("Review must identify an independent reviewer")
        required = {
            "protocol.md",
            "StrategySpec-B.yaml",
            "StrategySpec-R.yaml",
            "common.py",
            "native_account.py",
            "run.py",
            "evidence.json",
        }
        rows = {row["path"]: row["sha256"] for row in receipt.get("bindings", [])}
        if not required.issubset(rows):
            raise RuntimeError("Review does not bind the actual component package")
        for name, expected in rows.items():
            path = (OUT / name).resolve()
            if not path.is_relative_to(OUT) or digest(path) != expected:
                raise RuntimeError(f"Changed reviewed task input: {name}")
        for row in json.loads((OUT / "evidence.json").read_text())["bindings"]:
            if digest(ROOT / row["path"]) != row["sha256"]:
                raise RuntimeError(f"Changed accepted dependency: {row['path']}")


def active_parameters(arm):
    import yaml

    if arm not in ("B", "R"):
        raise ValueError("Only the two frozen component arms exist")
    obj = yaml.safe_load((OUT / f"StrategySpec-{arm}.yaml").read_text())
    assert obj["lifecycle"] == "draft" and obj["execution"]["broker"] == "none"
    notes = obj["notes"]
    p = notes["decision_system"]
    assert set(p) == set(notes["active_parameter_allowlist"])
    assert p["attempts_per_day"] == obj["risk"]["max_trades_per_day"] == (1 if arm == "B" else 3)
    return dict(p, **notes["native_book_compatibility_nonoperative"])


@cache
def verified_source(path):
    """Receive declared immutable bytes at their actual first use, not a broad scan."""
    path = Path(path).resolve()
    manifest = json.loads((SEQ / "input-manifest.json").read_text())
    row = next(row for row in manifest["bindings"] if Path(row["path"]).resolve() == path)
    assert path.stat().st_size == row["bytes"] and digest(path) == row["sha256"]
    return path


def verify_notices():
    manifest = json.loads((INPUTS / "manifest.json").read_text())
    needed = {INPUTS / month / "notices.jsonl" for month in ("2024-01", "2024-02", "2024-03")}
    for path in needed:
        row = next(row for row in manifest["files"] if (ROOT / row["path"]).resolve() == path)
        assert path.stat().st_size == row["bytes"] and digest(path) == row["sha256"]
