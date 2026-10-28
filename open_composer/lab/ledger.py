"""Durable append-only trial exposure across batches, failures and process exits."""

from __future__ import annotations

import fcntl
import os
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class TrialEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    event: Literal["started", "finished", "prior_exposure"]
    trial_id: str = Field(min_length=1)
    at: str
    batch: str = Field(min_length=1)
    candidate: str = Field(min_length=1)
    counts_as_trial: bool = True
    count: int = Field(default=1, ge=1)
    status: Literal["complete", "failed", "interrupted"] | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    evidence: list[str] = Field(default_factory=list)
    note: str = ""


class TrialLedger:
    """Count starts, not survivors. A start lacking a finish remains consumed exposure.

    ``counts_as_trial=False`` is for declared accounting views/null/diagnostic controls;
    it does not remove their events. Retrying a selectable configuration gets a new id.
    Prior exposure is imported once with its original evidence and explicit count.
    """

    def __init__(self, path: Path):
        self.path = Path(path)

    @contextmanager
    def _file(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a+", encoding="utf-8") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            stream.seek(0)
            yield stream

    @staticmethod
    def _read(stream) -> list[TrialEvent]:
        # Invalid/truncated lines fail closed; no automatic truncation of scientific history.
        return [TrialEvent.model_validate_json(line) for line in stream if line.strip()]

    def events(self) -> list[TrialEvent]:
        with self._file() as stream:
            return self._read(stream)

    @property
    def n_trials(self) -> int:
        return sum(
            e.count
            for e in self.events()
            if e.event in ("started", "prior_exposure") and e.counts_as_trial
        )

    def _append(self, event: TrialEvent) -> None:
        with self._file() as stream:
            rows = self._read(stream)
            same = [e for e in rows if e.trial_id == event.trial_id]
            if event.event == "finished":
                if len(same) != 1 or same[0].event != "started":
                    raise ValueError("Finish requires exactly one unfinished start")
                source = same[0]
                if (source.batch, source.candidate, source.counts_as_trial) != (
                    event.batch,
                    event.candidate,
                    event.counts_as_trial,
                ):
                    raise ValueError("Finish cannot change trial identity or exposure")
            elif same:
                raise ValueError(f"Trial or import id already exists: {event.trial_id}")
            if event.event == "prior_exposure" and not event.evidence:
                raise ValueError("Prior exposure needs original evidence")
            stream.seek(0, os.SEEK_END)
            stream.write(event.model_dump_json() + "\n")
            stream.flush()
            os.fsync(stream.fileno())

    def start(
        self,
        trial_id: str,
        *,
        batch: str,
        candidate: str,
        parameters: dict[str, Any],
        counts_as_trial: bool = True,
        note: str = "",
    ) -> None:
        self._append(
            TrialEvent(
                event="started",
                trial_id=trial_id,
                at=datetime.now(UTC).isoformat(),
                batch=batch,
                candidate=candidate,
                parameters=parameters,
                counts_as_trial=counts_as_trial,
                note=note,
            )
        )

    def finish(
        self,
        trial_id: str,
        *,
        status: Literal["complete", "failed", "interrupted"],
        evidence: list[str],
        note: str = "",
    ) -> None:
        starts = [e for e in self.events() if e.trial_id == trial_id and e.event == "started"]
        if len(starts) != 1:
            raise ValueError("Unknown trial start")
        source = starts[0]
        self._append(
            TrialEvent(
                event="finished",
                trial_id=trial_id,
                at=datetime.now(UTC).isoformat(),
                batch=source.batch,
                candidate=source.candidate,
                counts_as_trial=source.counts_as_trial,
                status=status,
                evidence=evidence,
                note=note,
            )
        )

    def import_prior(self, import_id: str, *, count: int, evidence: list[str], note: str) -> None:
        self._append(
            TrialEvent(
                event="prior_exposure",
                trial_id=import_id,
                at=datetime.now(UTC).isoformat(),
                batch="historical",
                candidate="historical",
                count=count,
                evidence=evidence,
                note=note,
            )
        )

    def snapshot(self, path: Path) -> int:
        """Freeze the inventory used by one summary, with its cumulative selectable count."""
        with self._file() as stream:
            rows = self._read(stream)
            with Path(path).open("x", encoding="utf-8") as output:
                for event in rows:
                    output.write(event.model_dump_json() + "\n")
        return sum(
            e.count for e in rows if e.event in ("started", "prior_exposure") and e.counts_as_trial
        )
