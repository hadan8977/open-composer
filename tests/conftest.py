from __future__ import annotations

from pathlib import Path
from shutil import copyfile

import pytest


@pytest.fixture()
def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


@pytest.fixture()
def sample_workspace(tmp_path: Path, repo_root: Path) -> Path:
    for relative in [
        "strategy_specs/drafts",
        "strategy_specs/active",
        "data/sample",
        "data/cache",
        "reports/backtests",
        "reports/parity",
        "reports/scans",
        "reports/reviews",
        "reports/paper",
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
    return tmp_path
