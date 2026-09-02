"""Kernel promotion gates must be provably preregistered."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from open_composer.research.kernel.gate_contract import (
    REQUIRED_GATE_KEYS,
    GateContractError,
    load_preregistered_gates,
)
from open_composer.research.kernel.mechanism_eval import DEFAULT_PROMOTION_GATES

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT = REPO_ROOT / "config" / "promotion" / "kernel-paper-tier-gates.json"


def _init_repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    return tmp_path


def _payload() -> dict:
    return {
        "rationale": "test contract",
        "gates": dict(DEFAULT_PROMOTION_GATES),
    }


def _write_and_commit(root: Path, relative: str, payload: dict) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    subprocess.run(["git", "add", relative], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "add"], cwd=root, check=True)
    return path


def test_the_repo_contract_loads_and_matches_the_kernel_defaults() -> None:
    gates = load_preregistered_gates(CONTRACT)
    assert gates.values == pytest.approx(dict(DEFAULT_PROMOTION_GATES))
    assert gates.rationale
    assert len(gates.git_blob_sha1) == 40
    assert len(gates.content_sha256) == 64
    assert gates.as_provenance()["gates_provenance"] == "preregistered"


def test_an_untracked_contract_is_refused(tmp_path: Path) -> None:
    root = _init_repo(tmp_path)
    path = root / "gates.json"
    path.write_text(json.dumps(_payload()), encoding="utf-8")
    with pytest.raises(GateContractError, match="not tracked by git"):
        load_preregistered_gates(path, repo_root=root)


def test_a_contract_edited_after_commit_is_refused(tmp_path: Path) -> None:
    """The whole point: a threshold changed after a result is not preregistered."""
    root = _init_repo(tmp_path)
    path = _write_and_commit(root, "gates.json", _payload())
    loosened = _payload()
    loosened["gates"]["dsr_minimum"] = 0.01
    path.write_text(json.dumps(loosened), encoding="utf-8")
    with pytest.raises(GateContractError, match="uncommitted modifications"):
        load_preregistered_gates(path, repo_root=root)


def test_a_contract_missing_a_threshold_is_refused(tmp_path: Path) -> None:
    root = _init_repo(tmp_path)
    payload = _payload()
    del payload["gates"]["dsr_minimum"]
    path = _write_and_commit(root, "gates.json", payload)
    with pytest.raises(GateContractError, match="missing thresholds"):
        load_preregistered_gates(path, repo_root=root)


def test_a_contract_with_an_unknown_threshold_is_refused(tmp_path: Path) -> None:
    root = _init_repo(tmp_path)
    payload = _payload()
    payload["gates"]["invented_minimum"] = 0.0
    path = _write_and_commit(root, "gates.json", payload)
    with pytest.raises(GateContractError, match="unknown thresholds"):
        load_preregistered_gates(path, repo_root=root)


def test_a_contract_without_a_rationale_is_refused(tmp_path: Path) -> None:
    root = _init_repo(tmp_path)
    payload = _payload()
    payload["rationale"] = "   "
    path = _write_and_commit(root, "gates.json", payload)
    with pytest.raises(GateContractError, match="must state a rationale"):
        load_preregistered_gates(path, repo_root=root)


def test_every_required_gate_key_is_a_kernel_default() -> None:
    assert set(REQUIRED_GATE_KEYS) == set(DEFAULT_PROMOTION_GATES)


def test_promotion_eligibility_requires_the_contract_not_just_the_numbers() -> None:
    """Identical thresholds passed inline must not buy promotion eligibility.

    This is the property the whole module exists for: eligibility tracks where
    the bar came from, not what the bar was. A verdict that cleared thresholds
    typed into the call site proves the candidate beat some numbers; it cannot
    prove those numbers predated it.
    """
    import numpy as np
    import pandas as pd

    from open_composer.research.kernel.mechanism_eval import (
        Mechanism,
        evaluate_candidate,
        expand_mechanism,
    )

    index = pd.date_range("2016-01-04", periods=2600, freq="B")
    rng = np.random.default_rng(2)
    returns = pd.Series(rng.normal(0.0020, 0.010, len(index)), index=index)
    benchmarks = {
        "qqq_returns": pd.Series(rng.normal(0.0002, 0.010, len(index)), index=index),
        "tqqq_returns": pd.Series(rng.normal(0.0004, 0.030, len(index)), index=index),
        "bil_returns": pd.Series(rng.normal(0.00002, 0.0002, len(index)), index=index),
    }
    candidate = expand_mechanism(
        Mechanism(family="X", signal_fn=lambda _p: returns, param_space=[{}])
    )[0]
    contract = load_preregistered_gates(CONTRACT)

    preregistered = evaluate_candidate(
        candidate, gates=contract, min_dsr_stream_rows=10, **benchmarks
    )
    inline = evaluate_candidate(
        candidate, gates=dict(contract.values), min_dsr_stream_rows=10, **benchmarks
    )
    defaults = evaluate_candidate(candidate, min_dsr_stream_rows=10, **benchmarks)

    # Same candidate, same thresholds, same gate outcome in all three.
    assert preregistered.all_gates_pass
    assert inline.all_gates_pass == preregistered.all_gates_pass
    assert defaults.all_gates_pass == preregistered.all_gates_pass
    assert inline.gate_results == preregistered.gate_results

    # Only the committed contract confers eligibility.
    assert preregistered.promotion_eligible is True
    assert inline.promotion_eligible is False
    assert defaults.promotion_eligible is False
    assert preregistered.gate_contract["gate_contract_git_blob_sha1"]
    assert inline.gate_contract == {}
