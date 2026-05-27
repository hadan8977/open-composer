from __future__ import annotations

import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from open_composer.cli import app
from open_composer.research.universe_audit import run_universe_audit


def test_universe_audit_flags_current_symbol_universe(sample_workspace: Path) -> None:
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"
    raw = spec_path.read_text(encoding="utf-8").replace("universe: [QQQ]", "universe: [QQQ, SPY]")
    spec_path.write_text(raw, encoding="utf-8")

    result = run_universe_audit(spec_path, sample_workspace)

    assert result.status == "blocked"
    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert payload["status"] == "blocked"
    assert any(item["code"] == "current_symbol_universe_bias" for item in payload["findings"])


def test_universe_audit_accepts_documented_fixed_universe(sample_workspace: Path) -> None:
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"
    payload = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    payload["universe"] = ["QQQ", "TQQQ", "SQQQ"]
    payload["notes"] = {
        **payload.get("notes", {}),
        "universe_audit": {
            "point_in_time_membership": True,
            "selection_timestamp": "2026-05-22T00:00:00Z",
            "delisting_policy": "Fixed ETF instrument set; inception dates checked separately.",
        },
    }
    spec_path.write_text(yaml.safe_dump(payload), encoding="utf-8")

    result = run_universe_audit(spec_path, sample_workspace)

    assert result.status == "warning"
    report = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert report["status"] == "warning"
    assert not any(item["code"] == "current_symbol_universe_bias" for item in report["findings"])


def test_universe_audit_rejects_boolean_only_pit_for_stock_universe(
    sample_workspace: Path,
) -> None:
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"
    payload = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    payload["universe"] = ["QQQ", "AAPL"]
    payload["notes"] = {
        **payload.get("notes", {}),
        "universe_audit": {
            "point_in_time_membership": True,
            "selection_timestamp": "2026-05-22T00:00:00Z",
            "delisting_policy": "Historical constituent changes are handled externally.",
        },
    }
    spec_path.write_text(yaml.safe_dump(payload), encoding="utf-8")

    result = run_universe_audit(spec_path, sample_workspace)

    assert result.status == "blocked"
    report = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert any(item["code"] == "pit_membership_artifact_missing" for item in report["findings"])


def test_universe_audit_accepts_pit_membership_artifact(sample_workspace: Path) -> None:
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"
    pit_path = sample_workspace / "reports" / "research" / "fixture-pit-universe.json"
    pit_path.parent.mkdir(parents=True, exist_ok=True)
    pit_path.write_text(
        json.dumps(
            {
                "schema_version": "1",
                "strategy_name": "fixture_pullback_15m",
                "source_type": "provider_official_docs",
                "source_url": "https://example.com/authorized-pit-universe",
                "as_of": "2026-05-22",
                "selection_timestamp": "2026-05-22T00:00:00Z",
                "delisting_policy": "Rows include effective_to for removed members.",
                "coverage_start": "2010-01-01",
                "coverage_end": "2026-05-22",
                "memberships": [
                    {
                        "symbol": "QQQ",
                        "effective_from": "1999-03-10",
                        "effective_to": None,
                        "source_id": "pit-fixture",
                    },
                    {
                        "symbol": "AAPL",
                        "effective_from": "2010-01-01",
                        "effective_to": None,
                        "source_id": "pit-fixture",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    payload = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    payload["universe"] = ["QQQ", "AAPL"]
    payload["notes"] = {
        **payload.get("notes", {}),
        "universe_audit": {
            "point_in_time_membership": True,
            "pit_membership_path": "reports/research/fixture-pit-universe.json",
            "selection_timestamp": "2026-05-22T00:00:00Z",
            "delisting_policy": "Rows include effective_to for removed members.",
        },
    }
    spec_path.write_text(yaml.safe_dump(payload), encoding="utf-8")

    result = run_universe_audit(spec_path, sample_workspace)

    assert result.status == "warning"
    report = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert any(item["code"] == "pit_membership_artifact_verified" for item in report["findings"])


def test_universe_audit_cli_writes_report(sample_workspace: Path, monkeypatch) -> None:
    monkeypatch.setattr("open_composer.cli.project_root", lambda: sample_workspace)
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"

    result = CliRunner().invoke(
        app,
        ["strategy", "universe-audit", str(spec_path)],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "universe audit complete" in result.output
    assert (
        sample_workspace / "reports" / "research" / "fixture_pullback_15m-universe-audit.json"
    ).exists()
