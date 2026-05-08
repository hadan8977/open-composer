from __future__ import annotations

from pathlib import Path
from shutil import copyfile, copytree

import pytest


@pytest.fixture()
def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


@pytest.fixture()
def sample_workspace(tmp_path: Path, repo_root: Path) -> Path:
    for relative in [
        "strategy_specs/drafts",
        "strategy_specs/active",
        "capabilities",
        "watchlists",
        "data/sample",
        "data/cache",
        "data/fixtures/capabilities",
        "data/raw/events",
        "data/raw/macro",
        "event_logs",
        "reports/backtests",
        "reports/capabilities",
        "reports/context",
        "reports/parity",
        "reports/scans",
        "reports/reviews",
        "reports/paper",
        "reports/runs",
        "reports/research",
        "reports/options",
        "signal_logs",
        "journal",
        "strategies_pine/generated",
    ]:
        (tmp_path / relative).mkdir(parents=True, exist_ok=True)
    copyfile(
        repo_root / "strategy_specs" / "drafts" / "qqq_pullback_15m.yaml",
        tmp_path / "strategy_specs" / "drafts" / "qqq_pullback_15m.yaml",
    )
    copyfile(
        repo_root / "data" / "sample" / "qqq_15m.csv", tmp_path / "data" / "sample" / "qqq_15m.csv"
    )
    copyfile(
        repo_root / "data" / "sample" / "mu_15m.csv", tmp_path / "data" / "sample" / "mu_15m.csv"
    )
    copyfile(
        repo_root / "watchlists" / "memory_storage.yaml",
        tmp_path / "watchlists" / "memory_storage.yaml",
    )
    copytree(repo_root / "capabilities", tmp_path / "capabilities", dirs_exist_ok=True)
    copytree(
        repo_root / "data" / "fixtures" / "capabilities",
        tmp_path / "data" / "fixtures" / "capabilities",
        dirs_exist_ok=True,
    )
    return tmp_path
