from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from open_composer.storage import append_jsonl, write_json

ProgressStatus = Literal["running", "ok", "warning", "blocked", "failed"]


@dataclass
class ResearchProgressWriter:
    root: Path
    strategy_name: str
    run_id: str
    experiment_run_id: str | None = None
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    latest: dict[str, Any] = field(default_factory=dict)

    @property
    def event_path(self) -> Path:
        return (
            self.root
            / "reports"
            / "research"
            / "runs"
            / f"{self.strategy_name}-{self.run_id}.jsonl"
        )

    @property
    def latest_path(self) -> Path:
        return self.root / "reports" / "research" / "runs" / f"{self.strategy_name}-latest.json"

    def event(
        self,
        *,
        event_type: str,
        stage: str,
        status: ProgressStatus = "running",
        candidate_index: int | None = None,
        candidate_count: int | None = None,
        best_label: str | None = None,
        best_score: float | None = None,
        best_oos_sharpe: float | None = None,
        best_oos_return_pct: float | None = None,
        best_max_drawdown_pct: float | None = None,
        warning_items: list[str] | None = None,
        blocked_items: list[str] | None = None,
        partial: bool = False,
        artifacts: dict[str, str | None] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        ended_at = now.isoformat() if status != "running" else None
        payload: dict[str, Any] = {
            "schema_version": 1,
            "strategy_name": self.strategy_name,
            "run_id": self.run_id,
            "experiment_run_id": self.experiment_run_id or self.run_id,
            "event_type": event_type,
            "stage": stage,
            "status": status,
            "candidate_index": candidate_index,
            "candidate_count": candidate_count,
            "best_label": best_label,
            "best_score": best_score,
            "best_oos_sharpe": best_oos_sharpe,
            "best_oos_return_pct": best_oos_return_pct,
            "best_max_drawdown_pct": best_max_drawdown_pct,
            "warning_items": warning_items or [],
            "blocked_items": blocked_items or [],
            "partial": partial,
            "started_at": self.started_at.isoformat(),
            "ended_at": ended_at,
            "updated_at": now.isoformat(),
            "artifacts": artifacts or {},
        }
        if extra:
            payload.update(extra)
        append_jsonl(self.event_path, [payload])
        self.latest = {
            "schema_version": 1,
            "strategy_name": self.strategy_name,
            "run_id": self.run_id,
            "experiment_run_id": self.experiment_run_id or self.run_id,
            "status": status,
            "stage": stage,
            "event_type": event_type,
            "candidate_index": candidate_index,
            "candidate_count": candidate_count,
            "best_label": best_label,
            "best_score": best_score,
            "best_oos_sharpe": best_oos_sharpe,
            "best_oos_return_pct": best_oos_return_pct,
            "best_max_drawdown_pct": best_max_drawdown_pct,
            "warning_items": warning_items or [],
            "blocked_items": blocked_items or [],
            "partial": partial,
            "started_at": self.started_at.isoformat(),
            "ended_at": ended_at,
            "updated_at": now.isoformat(),
            "event_path": _relpath(self.event_path, self.root),
            "artifacts": artifacts or {},
        }
        write_json(self.latest_path, self.latest)
        return payload


def _relpath(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()
