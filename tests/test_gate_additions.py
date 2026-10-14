from __future__ import annotations

import json
from pathlib import Path

import pytest

from open_composer.config import project_root
from open_composer.repo_check import _evaluation_standard_changelog_check
from open_composer.research import gate_additions as g

STANDARD = '{"version": "t"}\n'


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _workspace(tmp_path: Path, **config: object) -> Path:
    cfg = {
        "effective_from": "2026-10-06",
        "grandfathered_iterations": [],
        "family_monthly_candidate_quota": 3,
        "similarity": {"threshold": 0.5, "min_difference_chars": 20, "max_refs_reported": 5},
        "evaluation_standard_path": "config/evaluation-standard-v2.json",
        "evaluation_standard_changelog_path": "config/evaluation-standard-changelog.jsonl",
    }
    cfg.update(config)
    _write_json(tmp_path / g.CONFIG_PATH, cfg)
    (tmp_path / "config/evaluation-standard-v2.json").write_text(STANDARD, encoding="utf-8")
    return tmp_path


def _iteration(
    root: Path,
    iter_id: str,
    *,
    registered: str = "2026-10-07T01:00:00+00:00",
    family: str = "gap_fade",
    description: str = "overnight gap fade in small cap stocks after earnings",
    candidates: int = 2,
    **external_extra: object,
) -> Path:
    iter_dir = root / g.ITERATION_ROOT / iter_id
    external: dict[str, object] = {
        "iter_id": iter_id,
        "registered_at": registered,
        "objective": description,
        "mechanism_description": description,
    }
    if family:
        external["mechanism_family"] = family
    external.update(external_extra)
    _write_json(iter_dir / "external-brief.json", external)
    _write_json(
        iter_dir / "candidate-manifest.json",
        {
            "iter_id": iter_id,
            "generated_at": registered,
            "candidates": [
                {"candidate_id": f"{iter_id}_C{i}", "method": "m"} for i in range(candidates)
            ],
        },
    )
    return iter_dir


def _sign_changelog(root: Path, sha: str) -> None:
    row = {
        "sha256": sha,
        "date": "2026-10-07",
        "changed_by": "t",
        "reason": "r",
        "signed_by": "lead",
    }
    path = root / "config/evaluation-standard-changelog.jsonl"
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")


def test_inactive_without_config_and_for_legacy_iterations(tmp_path: Path) -> None:
    iter_dir = _iteration(tmp_path, "t20261007_x", family="")
    assert g.gate_additions_blockers(iter_dir.name, tmp_path, stage="pre-backtest") == ([], {})
    root = _workspace(tmp_path)
    legacy = _iteration(root, "t20261005_old", registered="2026-10-05T23:00:00+00:00", family="")
    _freeze_legacy_contract(root, legacy)
    assert g.gate_additions_blockers(legacy.name, root, stage="pre-backtest")[0] == []
    assert g.gate_additions_blockers(legacy.name, root, stage="final")[0] == []
    undated = root / g.ITERATION_ROOT / "undated"
    _write_json(undated / "external-brief.json", {"iter_id": "undated"})
    assert (
        "evaluation_standard_freeze_missing"
        in g.gate_additions_blockers("undated", root, stage="final")[0]
    )


def _freeze_legacy_contract(root: Path, iter_dir: Path) -> None:
    config_path = root / g.CONFIG_PATH
    config = json.loads(config_path.read_text())
    config.setdefault("legacy_contracts", {})[iter_dir.name] = {
        "frozen_at": "2026-10-05T23:00:00+00:00",
        "source": {"path": "verified-original-contract-fixture"},
        "artifacts": {
            name: g.file_sha256(iter_dir / name)
            for name in ("external-brief.json", "candidate-manifest.json")
        },
    }
    _write_json(config_path, config)


def test_backdated_or_unknown_iteration_cannot_claim_historical_exemption(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    for iter_id in ("t20261013_new", "t20261005_forged_old_id", "undated_new"):
        iter_dir = _iteration(
            root, iter_id, registered="2026-10-05T23:00:00+00:00", family="", description=""
        )
        pre, _ = g.gate_additions_blockers(iter_id, root, stage="pre-backtest")
        final, _ = g.gate_additions_blockers(iter_id, root, stage="final")
        assert "mechanism_family_missing" in pre
        assert "evaluation_standard_freeze_missing" in final
        assert "breakeven_costs_missing" in final
        assert any(row.startswith("trials_not_registered:") for row in final)
        if iter_id == "t20261013_new":
            assert g.iteration_registered_date(iter_dir).isoformat() == "2026-10-13"


def test_unchanged_verified_legacy_contract_retains_its_original_gate(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    legacy = _iteration(root, "t20261005_real", registered="2026-10-05T23:00:00Z", family="")
    _freeze_legacy_contract(root, legacy)
    g.append_trials(root, g.build_trial_rows(legacy))
    ledger_before = (root / g.TRIALS_PATH).read_bytes()
    assert g.gate_additions_blockers(legacy.name, root, stage="final")[0] == []
    assert g.record_prebacktest_gate(legacy.name, root) == {"active": False}
    assert (root / g.TRIALS_PATH).read_bytes() == ledger_before

    manifest_path = legacy / "candidate-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["candidates"].append({"candidate_id": "new_unfrozen_candidate"})
    _write_json(manifest_path, manifest)

    assert (
        "evaluation_standard_freeze_missing"
        in g.gate_additions_blockers(legacy.name, root, stage="final")[0]
    )
    assert (root / g.TRIALS_PATH).read_bytes() == ledger_before


def test_legacy_inventory_cannot_hide_new_scientific_identity_file(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    legacy = _iteration(root, "t20261005_real", registered="2026-10-05T23:00:00Z", family="")
    _freeze_legacy_contract(root, legacy)
    _write_json(legacy / "search-space.json", {"new_definition": True})
    assert g.is_new_iteration(legacy, g.load_gate_config(root))


def test_grandfathered_iteration_is_exempt(tmp_path: Path) -> None:
    root = _workspace(tmp_path, grandfathered_iterations=["t20261007_gf"])
    _iteration(root, "t20261007_gf", family="")
    assert g.gate_additions_blockers("t20261007_gf", root, stage="pre-backtest")[0] == []


def test_bound_grandfathered_exception_retains_only_the_original_version(tmp_path: Path) -> None:
    root = _workspace(tmp_path, grandfathered_iterations=["t20261007_gf"])
    iter_dir = _iteration(root, "t20261007_gf", family="")
    _freeze_legacy_contract(root, iter_dir)
    config_path = root / g.CONFIG_PATH
    config = json.loads(config_path.read_text())
    config["legacy_contracts"][iter_dir.name]["frozen_at"] = "2026-10-08T00:00:00Z"
    _write_json(config_path, config)
    assert g.gate_additions_blockers(iter_dir.name, root, stage="pre-backtest")[0] == []
    external_path = iter_dir / "external-brief.json"
    external = json.loads(external_path.read_text())
    external["objective"] = "a different economic hypothesis under the grandfathered name"
    _write_json(external_path, external)
    assert (
        "mechanism_family_missing"
        in g.gate_additions_blockers(iter_dir.name, root, stage="pre-backtest")[0]
    )


def test_registered_date_uses_iteration_id_when_undated_fields_missing(tmp_path: Path) -> None:
    iter_dir = tmp_path / g.ITERATION_ROOT / "t20261009_z"
    _write_json(iter_dir / "external-brief.json", {"iter_id": "t20261009_z"})
    assert g.iteration_registered_date(iter_dir).isoformat() == "2026-10-09"


def test_mechanism_family_required_for_new_iterations(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    _iteration(root, "t20261007_nofam", family="")
    blocked, _ = g.gate_additions_blockers("t20261007_nofam", root, stage="pre-backtest")
    assert "mechanism_family_missing" in blocked


def test_family_monthly_quota_blocks_and_exception_unblocks(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    first = _iteration(root, "t20261007_a", candidates=2)
    assert g.append_trials(root, g.build_trial_rows(first)) == 2
    second = _iteration(root, "t20261008_b", candidates=2, description="unrelated quota text xyz")
    blocked, _ = g.gate_additions_blockers(second.name, root, stage="pre-backtest")
    assert any(
        item.startswith("family_monthly_quota_exceeded:gap_fade:2026-10:4>3") for item in blocked
    )
    # a different family in the same month is not affected
    other = _iteration(root, "t20261008_c", family="other_family", candidates=2)
    assert not any(
        item.startswith("family_monthly_quota")
        for item in g.gate_additions_blockers(other.name, root, stage="pre-backtest")[0]
    )
    signed = _iteration(
        root,
        "t20261008_d",
        candidates=2,
        description="another distinct mechanism abc",
        family_quota_exception={
            "signed_by": "lead round (主审)",
            "signed_at": "2026-10-08",
            "reason": "bounded follow-up of a passed card, reviewed by the lead round",
        },
    )
    assert not any(
        item.startswith("family_monthly_quota")
        for item in g.gate_additions_blockers(signed.name, root, stage="pre-backtest")[0]
    )
    unsigned = _iteration(
        root,
        "t20261008_e",
        candidates=2,
        description="yet another mechanism def",
        family_quota_exception={
            "signed_by": "executor",
            "signed_at": "2026-10-08",
            "reason": "x" * 30,
        },
    )
    assert any(
        item.startswith("family_monthly_quota")
        for item in g.gate_additions_blockers(unsigned.name, root, stage="pre-backtest")[0]
    )


def test_semantic_duplicate_needs_stated_difference(tmp_path: Path) -> None:
    root = _workspace(tmp_path, family_monthly_candidate_quota=30)
    _iteration(root, "t20261007_a", description="gap fade overnight small cap earnings stocks")
    dup = _iteration(
        root,
        "t20261008_dup",
        description="overnight gap fade small cap earnings stocks",
    )
    blocked, _ = g.gate_additions_blockers(dup.name, root, stage="pre-backtest")
    assert any(
        item.startswith("semantic_duplicate_difference_missing:iteration:t20261007_a")
        for item in blocked
    )
    external = json.loads((dup / "external-brief.json").read_text(encoding="utf-8"))
    external["difference_from_existing"] = [
        {"ref": "iteration:t20261007_a", "difference": "uses auction prints instead of the open"}
    ]
    _write_json(dup / "external-brief.json", external)
    assert g.gate_additions_blockers(dup.name, root, stage="pre-backtest")[0] == []
    external["difference_from_existing"] = [{"ref": "iteration:t20261007_a", "difference": "short"}]
    _write_json(dup / "external-brief.json", external)
    assert g.gate_additions_blockers(dup.name, root, stage="pre-backtest")[0]


def test_semantic_check_uses_directions_registry_and_ignores_unrelated(tmp_path: Path) -> None:
    root = _workspace(tmp_path, family_monthly_candidate_quota=30)
    _write_json(tmp_path / "x", {})
    directions = tmp_path / g.DIRECTIONS_PATH
    directions.parent.mkdir(parents=True, exist_ok=True)
    directions.write_text(
        json.dumps(
            {
                "id": "dir:pead",
                "name": "post earnings announcement drift in large caps",
                "family_key": "event_pead",
                "claim": "drift after earnings surprise",
                "aliases": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    hit = _iteration(
        root, "t20261007_h", description="post earnings announcement drift in large caps"
    )
    unrelated = _iteration(
        root, "t20261007_u", description="volatility term structure carry via vix futures"
    )
    assert any(
        "direction:dir:pead" in b
        for b in g.gate_additions_blockers(hit.name, root, stage="pre-backtest")[0]
    )
    assert g.gate_additions_blockers(unrelated.name, root, stage="pre-backtest")[0] == []


def test_breakeven_cost_formula_and_validation(tmp_path: Path) -> None:
    assert g.breakeven_cost_bps(0.30, 12.0) == pytest.approx(250.0)
    assert g.breakeven_cost_bps(-0.05, 10.0) == pytest.approx(-50.0)
    assert g.breakeven_cost_bps(0.1, 0.0) is None
    root = _workspace(tmp_path)
    iter_dir = _iteration(root, "t20261007_be", candidates=2)
    assert g._breakeven_blockers(iter_dir) == ["breakeven_costs_missing"]
    _write_json(
        iter_dir / g.BREAKEVEN_FILENAME,
        {
            "candidates": {
                "t20261007_be_C0": {
                    "breakeven_cost_bps_per_side": 250.0,
                    "gross_return": 0.30,
                    "one_way_turnover": 12.0,
                },
                "t20261007_be_C1": {"breakeven_cost_bps_per_side": None},
            }
        },
    )
    assert g._breakeven_blockers(iter_dir) == ["breakeven_cost_missing:t20261007_be_C1"]
    payload = json.loads((iter_dir / g.BREAKEVEN_FILENAME).read_text(encoding="utf-8"))
    payload["candidates"]["t20261007_be_C1"] = {
        "breakeven_cost_bps_per_side": None,
        "not_applicable_reason": "zero turnover buy and hold control",
    }
    payload["candidates"]["t20261007_be_C0"]["breakeven_cost_bps_per_side"] = 99.0
    _write_json(iter_dir / g.BREAKEVEN_FILENAME, payload)
    assert g._breakeven_blockers(iter_dir)[0].startswith(
        "breakeven_cost_inconsistent:t20261007_be_C0"
    )
    payload["candidates"]["t20261007_be_C0"]["breakeven_cost_bps_per_side"] = 250.0
    _write_json(iter_dir / g.BREAKEVEN_FILENAME, payload)
    assert g._breakeven_blockers(iter_dir) == []


def test_standard_freeze_changelog_and_final_gate(tmp_path: Path) -> None:
    root = _workspace(tmp_path, family_monthly_candidate_quota=30)
    iter_dir = _iteration(root, "t20261007_fz", candidates=1)
    # final before freeze: blocked
    blocked, _ = g.gate_additions_blockers(iter_dir.name, root, stage="final")
    assert "evaluation_standard_freeze_missing" in blocked
    assert "trials_not_registered:1" in blocked
    result = g.record_prebacktest_gate(iter_dir.name, root)
    assert result["active"] and result["trials_added"] == 1 and result["freeze_written"]
    frozen = json.loads((iter_dir / g.FREEZE_FILENAME).read_text(encoding="utf-8"))
    assert frozen["sha256"] == g.file_sha256(root / "config/evaluation-standard-v2.json")
    # create-only: a changed standard does not rewrite the freeze
    (root / "config/evaluation-standard-v2.json").write_text(
        '{"version": "t2"}\n', encoding="utf-8"
    )
    again = g.record_prebacktest_gate(iter_dir.name, root)
    assert "freeze_written" not in again and again["trials_added"] == 0
    assert json.loads((iter_dir / g.FREEZE_FILENAME).read_text(encoding="utf-8")) == frozen
    _write_json(
        iter_dir / g.BREAKEVEN_FILENAME,
        {"candidates": {"t20261007_fz_C0": {"breakeven_cost_bps_per_side": 12.5}}},
    )
    blocked, info = g.gate_additions_blockers(iter_dir.name, root, stage="final")
    assert any(item.startswith("evaluation_standard_changed_without_changelog") for item in blocked)
    assert info["family"] == "gap_fade" and info["family_cumulative_trials"] == 1
    _sign_changelog(root, g.file_sha256(root / "config/evaluation-standard-v2.json"))
    assert g.gate_additions_blockers(iter_dir.name, root, stage="final")[0] == []


def test_changelog_row_needs_signature(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    sha = g.file_sha256(root / "config/evaluation-standard-v2.json")
    path = root / "config/evaluation-standard-changelog.jsonl"
    path.write_text(
        json.dumps({"sha256": sha, "date": "2026-10-07", "changed_by": "x", "reason": "y"}) + "\n",
        encoding="utf-8",
    )
    assert not g.changelog_covers(root, sha)
    assert _evaluation_standard_changelog_check(root).status == "blocked"
    _sign_changelog(root, sha)
    assert _evaluation_standard_changelog_check(root).status == "ok"


def test_repo_check_ok_when_workspace_has_no_standard(tmp_path: Path) -> None:
    assert _evaluation_standard_changelog_check(tmp_path).status == "ok"


def test_trials_ledger_is_append_only_and_counts_by_family_and_program(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    a = _iteration(root, "t20261007_p4_a", candidates=2)
    b = _iteration(root, "t20261007_p5_b", candidates=3, family="other")
    assert g.append_trials(root, g.build_trial_rows(a)) == 2
    assert g.append_trials(root, g.build_trial_rows(a)) == 0
    assert g.append_trials(root, g.build_trial_rows(b)) == 3
    assert g.count_trials(root)["trials"] == 5
    assert g.count_trials(root, family="gap_fade")["trials"] == 2
    assert g.count_trials(root, program="p5")["trials"] == 3
    rows = g.load_trials(root)
    assert rows[0]["project"] == "P4" and rows[0]["scale_curve_point"] is False
    before = (root / g.TRIALS_PATH).read_text(encoding="utf-8")
    g.append_trials(root, g.build_trial_rows(a))
    assert (root / g.TRIALS_PATH).read_text(encoding="utf-8") == before


def test_backfill_counts_manifest_cells_and_ledger_without_touching_dossiers(
    tmp_path: Path,
) -> None:
    root = _workspace(tmp_path)
    old = root / g.ITERATION_ROOT / "h20260918_cells"
    _write_json(
        old / "candidate-manifest.json",
        {
            "generated_at": "2026-09-18T00:00:00+00:00",
            "cells": [{"cell_id": "c1", "family": "rotation"}, {"cell_id": "c2"}],
        },
    )
    ledger_iter = root / g.ITERATION_ROOT / "mom_ledger"
    ledger_iter.mkdir(parents=True)
    (ledger_iter / "trial-ledger.jsonl").write_text(
        '{"candidate_id": "L1"}\n{"candidate_id": "L1"}\n{"candidate_id": "L2"}\n',
        encoding="utf-8",
    )
    empty = root / g.ITERATION_ROOT / "empty_iter"
    empty.mkdir(parents=True)
    snapshot = (old / "candidate-manifest.json").read_text(encoding="utf-8")
    result = g.backfill_trials(root)
    assert result["candidate_rows"] == 4
    assert result["iterations_without_countable_trials"] == ["empty_iter"]
    assert (old / "candidate-manifest.json").read_text(encoding="utf-8") == snapshot
    assert g.backfill_trials(root)["added"] == 0
    sources = {r["iter_id"]: r["source"] for r in g.load_trials(root)}
    assert sources["mom_ledger"] == "backfill:trial-ledger"


def test_real_repo_standard_is_covered_by_changelog() -> None:
    status = g.evaluation_standard_status(project_root())
    assert status["present"] and status["covered"] and not status["invalid_entries"]
    rows = g.changelog_rows(project_root())
    assert [r["kind"] for r in rows[:2]] == ["initial_registration", "change"]
