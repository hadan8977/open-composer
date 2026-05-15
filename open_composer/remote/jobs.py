from __future__ import annotations

import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from open_composer.config import ensure_dir
from open_composer.dashboard.commands import (
    DashboardCommandError,
    execute_dashboard_command_plan,
    load_dashboard_command_plan,
)
from open_composer.models.dashboard_command import DashboardCommandPlan
from open_composer.remote.backups import RemoteBackupError, create_remote_backup
from open_composer.remote.schemas import (
    RemoteCommandRunRequest,
    RemoteCommandRunResponse,
    RemoteJobEvent,
    RemoteJobRecord,
    remote_backup_required,
    remote_double_confirmation_phrase,
    remote_risk_level,
)
from open_composer.storage import append_jsonl, write_json


class RemoteJobError(RuntimeError):
    pass


class WorkspaceLockError(RuntimeError):
    pass


class RemoteJobManager:
    def __init__(self, root: Path, *, autostart: bool = True) -> None:
        self.root = root
        self.autostart = autostart
        self._executor = ThreadPoolExecutor(max_workers=1) if autostart else None
        self._submit_lock = threading.Lock()

    def create_command_job(
        self,
        request: RemoteCommandRunRequest,
        *,
        actor: str,
    ) -> RemoteJobRecord:
        plan = self._load_remote_plan(request.plan_path)
        job_id = _new_job_id()
        job_path = self._job_path(job_id)
        request_path = self._request_path(job_id)
        log_path = self._log_path(job_id)
        events_path = self._events_path()
        risk_level = remote_risk_level(plan.action)
        record = RemoteJobRecord(
            job_id=job_id,
            command_id=plan.command_id,
            action=plan.action,
            actor=actor,
            request_id=request.request_id,
            timeout_seconds=request.timeout_seconds,
            risk_level=risk_level,
            plan_path=plan.plan_path
            or _relpath(self._resolve_remote_plan_path(request.plan_path), self.root),
            request_path=_relpath(request_path, self.root),
            job_path=_relpath(job_path, self.root),
            log_path=_relpath(log_path, self.root),
            events_path=_relpath(events_path, self.root),
            message="Queued remote dashboard command job.",
        )
        write_json(request_path, request)
        self._write_job(record)
        self._append_event(record, "Queued remote dashboard command job.")
        if self._executor:
            with self._submit_lock:
                self._executor.submit(self.run_job, job_id)
        return record

    def response_for_job(self, record: RemoteJobRecord) -> RemoteCommandRunResponse:
        return RemoteCommandRunResponse(
            job_id=record.job_id,
            status=record.status,
            action=record.action,
            command_id=record.command_id,
            job_path=record.job_path,
            log_path=record.log_path,
            events_path=record.events_path,
            risk_level=record.risk_level,
            backup_required=remote_backup_required(record.action),
            backup_manifest_path=record.backup_manifest_path,
            message=record.message,
        )

    def run_job(self, job_id: str) -> RemoteJobRecord:
        record = self.load_job(job_id)
        request = self._load_request(record.request_path)
        plan = self._load_remote_plan(record.plan_path)
        if record.status != "queued":
            return record
        record.status = "running"
        record.started_at = datetime.now(UTC)
        record.message = "Remote dashboard command job is running."
        self._write_job(record)
        self._append_event(record, record.message)
        self._write_log(record, record.message)

        try:
            self._validate_confirmation(plan, request)
            if remote_backup_required(plan.action):
                manifest_path = create_remote_backup(
                    self.root,
                    job_id=record.job_id,
                    plan=plan,
                    actor=record.actor,
                )
                record.backup_manifest_path = _relpath(manifest_path, self.root)
                self._write_job(record)
                self._write_log(record, f"backup_manifest={record.backup_manifest_path}")
            with WorkspaceLock(self.root, record.job_id):
                result = execute_dashboard_command_plan(
                    plan,
                    self.root,
                    confirmation=request.confirm,
                    executed_by=request.executed_by,
                )
            record.status = "executed"
            record.result_path = result.result_path
            record.output_paths = result.output_paths
            record.message = result.message
        except DashboardCommandError as exc:
            record.status = "blocked"
            record.error = str(exc)
            record.message = str(exc)
        except (RemoteBackupError, WorkspaceLockError, ValueError) as exc:
            record.status = "blocked"
            record.error = str(exc)
            record.message = str(exc)
        except Exception as exc:  # pragma: no cover - defensive job boundary.
            record.status = "failed"
            record.error = str(exc)
            record.message = f"Remote job failed: {exc}"
        finally:
            if record.started_at and _elapsed_seconds(record.started_at) > record.timeout_seconds:
                record.status = "timed_out"
                record.message = "Remote job exceeded its timeout."
            record.finished_at = datetime.now(UTC)
            self._write_job(record)
            self._append_event(record, record.message)
            self._write_log(record, f"{record.status}: {record.message}")
        return record

    def load_job(self, job_id: str) -> RemoteJobRecord:
        path = self._job_path(job_id)
        if not path.exists():
            raise RemoteJobError(f"remote job not found: {job_id}")
        return RemoteJobRecord.model_validate_json(path.read_text(encoding="utf-8"))

    def list_jobs(self) -> list[RemoteJobRecord]:
        jobs: list[RemoteJobRecord] = []
        for path in sorted(self._jobs_dir().glob("*.json")):
            if path.name.endswith(".request.json"):
                continue
            jobs.append(RemoteJobRecord.model_validate_json(path.read_text(encoding="utf-8")))
        return sorted(jobs, key=lambda job: job.created_at, reverse=True)

    def read_events(self, *, limit: int = 100) -> list[dict[str, object]]:
        path = self._events_path()
        if not path.exists():
            return []
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
        return rows[-limit:]

    def _load_remote_plan(self, plan_path: str) -> DashboardCommandPlan:
        return load_dashboard_command_plan(self._resolve_remote_plan_path(plan_path))

    def _resolve_remote_plan_path(self, plan_path: str) -> Path:
        if not plan_path.strip():
            raise DashboardCommandError("plan_path is required")
        candidate = Path(plan_path)
        if not candidate.is_absolute():
            candidate = self.root / candidate
        resolved = candidate.resolve()
        root_resolved = self.root.resolve()
        if resolved != root_resolved and not resolved.is_relative_to(root_resolved):
            raise DashboardCommandError("plan_path must stay within the current workspace")
        relative = resolved.relative_to(root_resolved)
        allowed_prefix = ("reports", "dashboard", "commands")
        if relative.parts[:3] != allowed_prefix or resolved.suffix != ".json":
            raise DashboardCommandError("remote plan_path must be a dashboard command plan JSON")
        if resolved.name.endswith(".result.json"):
            raise DashboardCommandError("remote plan_path must not point to a command result")
        return resolved

    def _load_request(self, request_path: str) -> RemoteCommandRunRequest:
        path = Path(request_path)
        if not path.is_absolute():
            path = self.root / path
        return RemoteCommandRunRequest.model_validate_json(path.read_text(encoding="utf-8"))

    def _validate_confirmation(
        self,
        plan: DashboardCommandPlan,
        request: RemoteCommandRunRequest,
    ) -> None:
        if request.confirm != plan.confirmation_phrase:
            raise DashboardCommandError(
                "Confirmation phrase did not match; command was not executed."
            )
        expected_double = remote_double_confirmation_phrase(plan.action)
        if expected_double and request.double_confirm != expected_double:
            raise DashboardCommandError("Remote double confirmation phrase did not match.")

    def _write_job(self, record: RemoteJobRecord) -> Path:
        return write_json(self._job_path(record.job_id), record)

    def _append_event(self, record: RemoteJobRecord, message: str) -> Path:
        return append_jsonl(
            self._events_path(),
            [
                RemoteJobEvent(
                    job_id=record.job_id,
                    command_id=record.command_id,
                    action=record.action,
                    status=record.status,
                    actor=record.actor,
                    message=message,
                    request_id=record.request_id,
                    backup_manifest_path=record.backup_manifest_path,
                    result_path=record.result_path,
                )
            ],
        )

    def _write_log(self, record: RemoteJobRecord, line: str) -> None:
        path = self._log_path(record.job_id)
        ensure_dir(path.parent)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"{datetime.now(UTC).isoformat()} {line}\n")

    def _jobs_dir(self) -> Path:
        return self.root / "reports" / "dashboard" / "jobs"

    def _job_path(self, job_id: str) -> Path:
        return self._jobs_dir() / f"{job_id}.json"

    def _request_path(self, job_id: str) -> Path:
        return self._jobs_dir() / f"{job_id}.request.json"

    def _log_path(self, job_id: str) -> Path:
        return self._jobs_dir() / f"{job_id}.log"

    def _events_path(self) -> Path:
        return self._jobs_dir() / "events.jsonl"


class WorkspaceLock:
    def __init__(self, root: Path, job_id: str) -> None:
        self.path = root / "reports" / "dashboard" / "jobs" / "workspace.lock"
        self.job_id = job_id
        self._fd: int | None = None

    def __enter__(self) -> WorkspaceLock:
        ensure_dir(self.path.parent)
        try:
            self._fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise WorkspaceLockError("remote workspace lock is already held") from exc
        os.write(self._fd, f"{self.job_id}\n{datetime.now(UTC).isoformat()}\n".encode())
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass


def _new_job_id() -> str:
    return f"remotejob_{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}_{uuid4().hex[:8]}"


def _elapsed_seconds(started_at: datetime) -> float:
    return (datetime.now(UTC) - started_at).total_seconds()


def _relpath(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()
