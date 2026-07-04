from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from open_composer.cli import app
from open_composer.research.hybrid_router_core import _effective_lookback, hybrid_params_from_label
from open_composer.research.pdr_attribution import (
    build_pdr_attribution_payload,
    simulate_daily_rows,
)
from open_composer.research.research_cache_manifest import (
    verify_longbridge_research_cache_manifest,
    write_longbridge_research_cache_manifest,
)
from tests.test_pdr_router_parity import OVERLAY_LABEL, _fixture_dataset, _spec


def test_pdr_attribution_fixture_payload_includes_state_and_asset_breakdown() -> None:
    spec = _spec()
    dataset = _fixture_dataset()
    params = hybrid_params_from_label(OVERLAY_LABEL)
    lookback = _effective_lookback(params)
    rows = simulate_daily_rows(spec, dataset, params, lookback, len(dataset.dates) - 1)

    payload = build_pdr_attribution_payload(
        spec=spec,
        dataset=dataset,
        params=params,
        route_label=OVERLAY_LABEL,
        rows=rows,
        fold_windows=(("fixture", rows[0]["date"], rows[-1]["date"]),),
        start_index=lookback,
        end_index=len(dataset.dates) - 1,
        router_implementation="source_import",
        source_artifact=None,
    )

    assert payload["report_type"] == "pdr_router_fold_state_asset_attribution"
    assert payload["full_window_attribution"]["days"] == len(rows)
    assert payload["folds"][0]["attribution"]["by_state"]
    assert payload["folds"][0]["attribution"]["by_asset"]


def test_router_gate_eval_cli_returns_nonzero_after_writing_negative_report(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def fake_evaluate(*args, **kwargs):
        return {
            "acceptance_gate": {"ml_gate_beats_fixed_route": False},
            "artifact_paths": {
                "json": str(tmp_path / "eval.json"),
                "markdown": str(tmp_path / "eval.md"),
            },
        }

    monkeypatch.setattr("open_composer.cli.evaluate_pdr_router_ml_gate", fake_evaluate)

    result = CliRunner().invoke(
        app,
        ["strategy", "router-gate-eval", "--output-dir", str(tmp_path)],
    )

    assert result.exit_code == 1
    assert "accepted=False" in result.output


def test_router_productization_cli_help_smoke() -> None:
    runner = CliRunner()

    assert runner.invoke(app, ["strategy", "router-attribution", "--help"]).exit_code == 0
    assert runner.invoke(app, ["strategy", "router-gate-eval", "--help"]).exit_code == 0
    assert runner.invoke(app, ["data", "verify-research-cache", "--help"]).exit_code == 0


def test_longbridge_research_cache_manifest_pass_and_drift(tmp_path: Path) -> None:
    cache_dir = tmp_path / "longbridge_adjusted_daily"
    cache_dir.mkdir()
    csv_path = cache_dir / "qqq_daily_longbridge_adjusted.csv"
    csv_path.write_text(
        "timestamp,open,high,low,close,volume\n"
        "2026-01-02 05:00:00+00:00,1,2,1,2,100\n"
        "2026-01-05 05:00:00+00:00,2,3,2,3,200\n",
        encoding="utf-8",
    )
    manifest = write_longbridge_research_cache_manifest(
        tmp_path,
        output_dir=cache_dir,
        symbols=["QQQ"],
        requested_start="2026-01-02",
        requested_end="2026-01-05",
    )

    passed = verify_longbridge_research_cache_manifest(tmp_path, manifest_path=manifest)

    assert passed["passed"] is True
    assert passed["checked_symbols"] == ["QQQ"]

    csv_path.write_text(
        "timestamp,open,high,low,close,volume\n2026-01-02 05:00:00+00:00,1,2,1,2,100\n",
        encoding="utf-8",
    )
    drift = verify_longbridge_research_cache_manifest(tmp_path, manifest_path=manifest)

    assert drift["passed"] is False
    assert {item["field"] for item in drift["drift"]} >= {"records", "sha256"}
