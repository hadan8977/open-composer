from __future__ import annotations

import json
from pathlib import Path

from open_composer.config import project_root


def equity_series_path(root: Path | None, run_id: str) -> Path:
    base = root or project_root()
    return base / "reports" / "backtests" / f"{run_id}-equity.json"


def load_equity_series(root: Path | None, run_id: str) -> tuple[list[str], list[float]]:
    path = equity_series_path(root, run_id)
    payload = json.loads(path.read_text(encoding="utf-8"))
    timestamps = payload.get("timestamps")
    returns = payload.get("bar_returns")
    if not isinstance(timestamps, list) or not isinstance(returns, list):
        raise ValueError(f"invalid equity series artifact: {path}")
    return [str(item) for item in timestamps], [float(item) for item in returns]


def load_equity_curve(root: Path | None, run_id: str) -> tuple[list[str], list[float]]:
    path = equity_series_path(root, run_id)
    payload = json.loads(path.read_text(encoding="utf-8"))
    timestamps = payload.get("timestamps")
    equity = payload.get("equity")
    if not isinstance(timestamps, list) or not isinstance(equity, list):
        raise ValueError(f"invalid equity series artifact: {path}")
    return [str(item) for item in timestamps], [float(item) for item in equity]
