"""Preregistered promotion gates for the kernel search path.

The campaign path takes its promotion thresholds from a hash-sealed contract
committed before any result exists. The kernel path took them from a module-level
dict, which anyone can edit after seeing a verdict -- so a kernel verdict carried
no evidence that its bar had been set in advance. That gap is what the review in
``docs/review-kernel-search-2026-09-01.zh.md`` section 3.1 records as structural
rather than incidental.

This module closes it the way config-as-code normally is closed, and the way the
backtest-overfitting literature asks for: **declare the trial count and the
thresholds before you look**. Bailey and Lopez de Prado's deflated Sharpe ratio is
only meaningful if the trial count is honest, and Harvey and Liu make the same
argument for factor discovery -- a threshold chosen after seeing the result is not
a threshold.

The enforcement here is deliberately something a person cannot quietly undo:

* the gates must live in a JSON file that is **tracked by git**;
* that file must have **no uncommitted modifications**;
* the verdict records the file's **git blob SHA-1 and its content SHA-256**.

Editing a threshold after seeing a result therefore either shows up as a dirty
working tree at load time, or as a new commit whose diff is visible in review.
This cannot make dishonesty impossible -- nothing can -- but it makes it leave a
trace, which is the whole of what preregistration buys anywhere else.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

REQUIRED_GATE_KEYS: tuple[str, ...] = (
    "cagr_excess_qqq_minimum",
    "sharpe_excess_bil_minimum",
    "dsr_minimum",
    "max_drawdown_minimum",
    "mar_minimum",
    "minimum_positive_fold_fraction",
    "qqq_capture_ratio_minimum",
    "qqq_downside_capture_maximum",
)

#: Step 10 (docs/plan-step-10-mechanism-supplementation-2026-09-03.zh.md
#: section 3.2): the leveraged-Nasdaq-router gates above compare a candidate's
#: absolute CAGR to un-levered QQQ, which no unlevered strategy family can
#: realistically clear (QQQ's own trailing CAGR is ~20%/yr). Unlevered
#: candidate families (beta exposure, cross-asset trend, liquid cross-
#: sectional momentum, single-ETF intraday, and their preregistered
#: combinations) are instead judged against a volatility-matched benchmark --
#: same structure, three keys renamed, nothing else. A contract declares
#: exactly one of these two key sets, never a mix; ``load_preregistered_gates``
#: rejects unknown or missing keys for whichever set it was asked to enforce.
UNLEVERED_FAMILY_GATE_KEYS: tuple[str, ...] = (
    "cagr_excess_vol_matched_benchmark_minimum",
    "sharpe_excess_bil_minimum",
    "dsr_minimum",
    "max_drawdown_minimum",
    "mar_minimum",
    "minimum_positive_fold_fraction",
    "benchmark_vm_capture_ratio_minimum",
    "benchmark_vm_downside_capture_maximum",
)


class GateContractError(RuntimeError):
    """Raised when promotion gates cannot be proven to predate the result."""


@dataclass(frozen=True)
class PreregisteredGates:
    """Promotion thresholds proven to have been committed before the run."""

    values: dict[str, float]
    source_path: str
    git_blob_sha1: str
    content_sha256: str
    #: Free-text reason the thresholds are what they are, required by the
    #: contract so a bar can never be a bare number with no argument behind it.
    rationale: str

    def as_provenance(self) -> dict[str, str]:
        return {
            "gates_provenance": "preregistered",
            "gate_contract_path": self.source_path,
            "gate_contract_git_blob_sha1": self.git_blob_sha1,
            "gate_contract_sha256": self.content_sha256,
        }


def _git(args: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=False, timeout=60
    )


def load_preregistered_gates(
    path: Path | str,
    *,
    repo_root: Path | None = None,
    required_keys: tuple[str, ...] = REQUIRED_GATE_KEYS,
) -> PreregisteredGates:
    """Load promotion gates, refusing anything that cannot be shown to predate the run.

    ``required_keys`` defaults to the leveraged-Nasdaq-router key set
    (``REQUIRED_GATE_KEYS``) so every existing caller is unaffected. Pass
    ``UNLEVERED_FAMILY_GATE_KEYS`` to load
    ``config/promotion/unlevered-family-paper-tier-gates.json`` instead; the
    contract must declare exactly one of the two key sets, never a mix.
    """
    contract_path = Path(path)
    root = repo_root or Path(__file__).resolve().parents[3]
    if not contract_path.is_file():
        raise GateContractError(f"gate contract not found: {contract_path}")

    try:
        relative = contract_path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise GateContractError(
            f"gate contract must live inside the repository: {contract_path}"
        ) from exc

    tracked = _git(["ls-files", "--error-unmatch", relative], cwd=root)
    if tracked.returncode != 0:
        raise GateContractError(
            f"gate contract {relative} is not tracked by git, so it cannot be shown to "
            "predate this result; commit it before using it to promote anything"
        )
    dirty = _git(["status", "--porcelain", "--", relative], cwd=root)
    if dirty.stdout.strip():
        raise GateContractError(
            f"gate contract {relative} has uncommitted modifications; a threshold edited "
            "after a result is not a preregistered threshold"
        )
    blob = _git(["rev-parse", f"HEAD:{relative}"], cwd=root)
    if blob.returncode != 0:
        raise GateContractError(f"gate contract {relative} is not present in HEAD")

    raw = contract_path.read_bytes()
    payload = json.loads(raw)
    gates = payload.get("gates")
    if not isinstance(gates, dict):
        raise GateContractError(f"gate contract {relative} has no 'gates' object")
    missing = [key for key in required_keys if key not in gates]
    if missing:
        raise GateContractError(
            f"gate contract {relative} is missing thresholds: {', '.join(missing)}"
        )
    extra = [key for key in gates if key not in required_keys]
    if extra:
        raise GateContractError(
            f"gate contract {relative} declares unknown thresholds: {', '.join(sorted(extra))}"
        )
    rationale = str(payload.get("rationale", "")).strip()
    if not rationale:
        raise GateContractError(
            f"gate contract {relative} must state a rationale; a bar with no argument "
            "behind it is a number, not a decision"
        )

    return PreregisteredGates(
        values={key: float(gates[key]) for key in required_keys},
        source_path=relative,
        git_blob_sha1=blob.stdout.strip(),
        content_sha256=hashlib.sha256(raw).hexdigest(),
        rationale=rationale,
    )
