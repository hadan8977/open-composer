"""Small synthetic repository for the API and HTML contract suites only."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from open_composer.cockpit import api, app
from open_composer.cockpit.data import agents, health, overview, quota
from open_composer.config import project_root

CARD_ID = "H-20240102-01"
AGENT_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
STRATEGY = "synthetic_strategy"


@pytest.fixture
def cockpit_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Use real local readers on fixture files; reject accidental live report reads."""
    live_root = project_root()
    root = tmp_path / "workspace"
    cards = root / "reports/research/hypotheses"
    cards.mkdir(parents=True)
    (cards / f"{CARD_ID}.md").write_text(
        "---\nstatus: proposed\nlane: proposed\n---\n"
        f"# {CARD_ID} Synthetic contract card\n\n"
        "## Acceptance criteria\nSynthetic fixture only.\n",
        encoding="utf-8",
    )
    control = root / "reports/research/control"
    control.mkdir()
    (control / "autonomous-queue.md").write_text("# Synthetic queue\n", encoding="utf-8")
    result_directory = root / "reports/research/iterations/synthetic_result"
    result_directory.mkdir(parents=True)
    (result_directory / "summary.json").write_text(
        json.dumps(
            {"card_id": CARD_ID, "cell_count": 1, "generated_at": "2024-01-02T21:00:00+00:00"}
        ),
        encoding="utf-8",
    )
    paper = root / "reports/paper/rehearsal"
    paper.mkdir(parents=True)
    (paper / f"{STRATEGY}-latest.json").write_text(
        json.dumps(
            {
                "generated_at": "2024-01-02T21:00:00+00:00",
                "session": "2024-01-02",
                "status": "dry_run_unauthorized",
                "equity": 10_000,
                "position_scope": "strategy_ledger",
                "strategy_ledger_positions": {},
                "counts": {},
                "orders": [],
            }
        ),
        encoding="utf-8",
    )
    agent_directory = root / "fixture-agents/workspace"
    agent_directory.mkdir(parents=True)
    now = datetime.now(UTC).isoformat()
    (agent_directory / f"{AGENT_ID}.json").write_text(
        json.dumps(
            {
                "id": AGENT_ID,
                "provider": "claude",
                "cwd": str(root),
                "workspaceId": str(root),
                "title": "Synthetic contract agent",
                "createdAt": now,
                "updatedAt": now,
                "lastActivityAt": now,
                "lastUserMessageAt": now,
                "lastStatus": "idle",
                "config": {"model": "synthetic-model"},
            }
        ),
        encoding="utf-8",
    )
    for module in (app, api, agents, health):
        monkeypatch.setattr(module, "project_root", lambda: root)
    monkeypatch.setattr(agents, "PASEO_AGENTS_DIR", agent_directory.parent)
    monkeypatch.setattr(agents, "_DEFAULT_TOPBAR_AGENTS_CACHE", agents.TopbarAgentsCache())
    monkeypatch.setattr(overview, "_DEFAULT_CACHE", overview.ResearchOverviewCache())
    monkeypatch.setattr(overview, "_DEFAULT_EQUITY_CACHE", overview.PaperEquityCache())
    monkeypatch.setattr(quota, "CODEX_AUTH_PATH", root / "no-auth.json")
    monkeypatch.setattr(health, "read_crontab", lambda: "")
    monkeypatch.setattr(app, "load_heavy_jobs", lambda: ())
    monkeypatch.setattr(api, "load_heavy_jobs", lambda: ())

    # Retain the actual parsers/serializers. A forgotten project_root binding must
    # fail even if a best-effort reader catches the resulting exception.
    original_open = Path.open
    attempted_live_reads: list[str] = []

    def isolated_open(path: Path, *args, **kwargs):
        absolute = path.absolute()
        if any(absolute.is_relative_to(live_root / name) for name in ("reports", "data", "logs")):
            attempted_live_reads.append(str(path))
            raise AssertionError(f"Cockpit contract test attempted a live read: {path}")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", isolated_open)
    yield root
    assert not attempted_live_reads, (
        f"Contract tests must use fixture files: {attempted_live_reads}"
    )


def publish_fixture_overview(root: Path, rows: list[dict]) -> dict:
    """Write a hash-bound synthetic projection through the real read contract."""
    pnl = sum(row["pnl_usd"] for row in rows)
    capital = sum(row["capital_usd"] or 0 for row in rows)
    payload = {
        "schema_version": 1,
        "through_session": "2024-01-02",
        "snapshot": {
            "rows": rows,
            "capital_usd": capital,
            "pnl_usd": pnl,
            "return_pct": pnl / capital * 100,
            "at_start": "2024-01-02T21:00:00+00:00",
            "at_end": "2024-01-02T21:00:03+00:00",
            "pool_readings": [],
            "adjustments": [],
            "adjustment_usd": 0,
            "unassigned_capital_usd": 0,
        },
        "daily": [
            {
                "day": "2024-01-02",
                "pnl_usd": pnl,
                "return_pct": pnl / capital * 100,
                "missing": [],
                "pools": ["synthetic"],
            }
        ],
    }
    path = root / "reports/paper/contract-overview.json"
    raw = json.dumps(payload).encode()
    path.write_bytes(raw)
    config = root / "config"
    config.mkdir(exist_ok=True)
    (config / "paper-overview-dashboard.json").write_text(
        json.dumps(
            {"path": str(path.relative_to(root)), "sha256": hashlib.sha256(raw).hexdigest()}
        ),
        encoding="utf-8",
    )
    return payload
