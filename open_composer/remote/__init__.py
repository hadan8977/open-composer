"""Remote compute integrations with explicit, auditable contracts."""

from open_composer.remote.windows_worker import (
    WorkerCommandResult,
    load_worker_contract,
    read_worker_status,
    run_worker_command,
    validate_task_manifest,
    worker_preflight,
)

__all__ = [
    "WorkerCommandResult",
    "load_worker_contract",
    "read_worker_status",
    "run_worker_command",
    "validate_task_manifest",
    "worker_preflight",
]
