"""Direction registry + search log (``open_composer.research.harvest_registry``).

The registry is the record that stops a later session from searching or
testing the same direction twice, so the rules under test are the ones that
make a row useful later: a closed direction carries its verdict, evidence, and
reopen condition; a confirmed one carries its confirmation; and the repeat
check also finds work recorded only in hypothesis cards or trial families.
"""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from open_composer.cli import app
from open_composer.research.harvest_registry import (
    check_direction,
    load_directions,
    registry_summary,
    validate_registry,
)


def _write(root: Path, name: str, rows: list[dict]) -> None:
    path = root / "reports" / "research" / "harvest" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def _direction(**overrides) -> dict:
    row = {
        "id": "dir:precious_metals_levered_trend",
        "name": "Precious-metals leveraged ETF trend",
        "category": "levered_etf",
        "family_key": "levered_sector_trend",
        "status": "harvested",
        "updated": "2026-09-23",
        "aliases": ["NUGT", "JNUG", "AGQ", "gold miners 2x"],
        "sources": [{"url": "https://example.org/nugt", "kind": "live_record"}],
    }
    row.update(overrides)
    return row


def _refuted(**overrides) -> dict:
    row = _direction(
        id="dir:spy_noise_band_intraday",
        name="SPY noise-band intraday momentum",
        category="intraday",
        family_key="single_etf_intraday_momentum",
        status="refuted",
        aliases=["Zarattini Beat the Market", "VWAP trailing stop"],
        verdict="+2.2%/yr at the paper's own frictions",
        evidence=["reports/research/hypotheses/H-20260922-07-spy-intraday-momentum.md"],
        reopen_if="a cost basis below 0.06 bp/side, or a new exit rule with a public OOS record",
    )
    row.update(overrides)
    return row


def test_valid_registry_has_no_problems(tmp_path: Path) -> None:
    _write(tmp_path, "directions.jsonl", [_direction(), _refuted()])
    _write(
        tmp_path,
        "search-log.jsonl",
        [
            {
                "id": "search:20260923:quantocracy:1",
                "date": "2026-09-23",
                "channel": "quantocracy",
                "tool": "webfetch",
                "query": "leveraged etf trend",
                "new_directions": ["dir:precious_metals_levered_trend"],
            }
        ],
    )
    assert validate_registry(tmp_path) == []


def test_last_row_for_an_id_wins(tmp_path: Path) -> None:
    confirmed = _direction(
        status="queued",
        triage={
            "goal_fit": "uncorrelated second levered bet",
            "executable_subset": "long NUGT/JNUG/AGQ spot",
            "cheapest_test": "frozen protocol + vt40",
            "stop_condition": "fails G1 or placebo > 10%",
        },
    )
    _write(tmp_path, "directions.jsonl", [_direction(), confirmed])
    assert load_directions(tmp_path)["dir:precious_metals_levered_trend"].status == "queued"
    assert validate_registry(tmp_path) == []


def test_closed_direction_needs_verdict_evidence_and_reopen_condition(tmp_path: Path) -> None:
    _write(tmp_path, "directions.jsonl", [_refuted(verdict="", evidence=[], reopen_if="")])
    problems = validate_registry(tmp_path)
    assert any("needs a verdict" in problem for problem in problems)
    assert any("needs evidence" in problem for problem in problems)
    assert any("needs reopen_if" in problem for problem in problems)


def test_confirmed_direction_needs_its_confirmation(tmp_path: Path) -> None:
    _write(tmp_path, "directions.jsonl", [_direction(status="queued")])
    problems = validate_registry(tmp_path)
    assert any("direction confirmation missing" in problem for problem in problems)


def test_schema_errors_and_unknown_references_are_reported(tmp_path: Path) -> None:
    _write(tmp_path, "directions.jsonl", [_direction(id="Not A Valid Id")])
    _write(
        tmp_path,
        "search-log.jsonl",
        [
            {
                "id": "search:1",
                "date": "2026-09-23",
                "channel": "github",
                "tool": "api",
                "query": "alpha factors",
                "new_directions": ["dir:does_not_exist"],
            },
            {
                "id": "search:1",
                "date": "2026-09-23",
                "channel": "github",
                "tool": "api",
                "query": "again",
            },
        ],
    )
    problems = validate_registry(tmp_path)
    assert any(problem.startswith("directions.jsonl:1: id") for problem in problems)
    assert any("not in the registry" in problem for problem in problems)
    assert any("duplicate search id search:1" in problem for problem in problems)


def test_duplicate_must_point_at_a_known_direction(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "directions.jsonl",
        [_direction(id="dir:gold_miners_2x", status="duplicate", duplicate_of="dir:nope")],
    )
    assert any("is unknown" in problem for problem in validate_registry(tmp_path))


def test_check_finds_registry_rows_cards_and_trial_families(tmp_path: Path) -> None:
    _write(tmp_path, "directions.jsonl", [_direction(), _refuted()])
    cards = tmp_path / "reports" / "research" / "hypotheses"
    cards.mkdir(parents=True)
    (cards / "H-20260922-08-cross-sectional-gap-fade.md").write_text(
        "# H-20260922-08 cross-sectional gap fade\nstatus: 已执行；信号保留\n", encoding="utf-8"
    )
    (cards / "trial-families.json").write_text(
        json.dumps(
            {"families": {"insider_form4_gate": {"note": "closed: refuted", "budget_remaining": 0}}}
        ),
        encoding="utf-8",
    )

    by_alias = check_direction(tmp_path, "Zarattini VWAP trailing stop")
    assert by_alias[0].ref == "dir:spy_noise_band_intraday"
    assert by_alias[0].status == "refuted"
    assert by_alias[0].score >= 0.5

    by_card = check_direction(tmp_path, "gap fade")
    assert by_card[0].kind == "hypothesis_card"

    by_family = check_direction(tmp_path, "insider form4")
    assert any(match.kind == "trial_family" for match in by_family)

    assert check_direction(tmp_path, "completely unrelated words") == []


def test_summary_counts_by_category_status_and_channel(tmp_path: Path) -> None:
    _write(tmp_path, "directions.jsonl", [_direction(), _refuted()])
    _write(
        tmp_path,
        "search-log.jsonl",
        [
            {
                "id": "search:a",
                "date": "2026-09-23",
                "channel": "github",
                "tool": "api",
                "query": "alpha factors",
            }
        ],
    )
    summary = registry_summary(tmp_path)
    assert summary["direction_count"] == 2
    assert summary["by_status"] == {"harvested": 1, "refuted": 1}
    assert summary["by_category"]["intraday"] == {"refuted": 1}
    assert summary["searches_by_channel"] == {"github": 1}


def test_cli_check_and_validate(tmp_path: Path, monkeypatch) -> None:
    _write(tmp_path, "directions.jsonl", [_direction(), _refuted()])
    monkeypatch.setenv("OPEN_COMPOSER_ROOT", str(tmp_path))
    runner = CliRunner()

    checked = runner.invoke(app, ["research", "directions", "check", "noise", "band", "SPY"])
    assert checked.exit_code == 0, checked.output
    assert "dir:spy_noise_band_intraday" in checked.output

    validated = runner.invoke(app, ["research", "directions", "validate"])
    assert validated.exit_code == 0, validated.output
    assert '"status": "ok"' in validated.output

    _write(tmp_path, "directions.jsonl", [_refuted(verdict="")])
    blocked = runner.invoke(app, ["research", "directions", "validate"])
    assert blocked.exit_code == 1
