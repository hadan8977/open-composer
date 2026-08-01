from __future__ import annotations

import fcntl
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def paper_submission_lock(root: Path) -> Iterator[None]:
    with _paper_lock(root, ".submission.lock"):
        yield


@contextmanager
def paper_control_lock(root: Path) -> Iterator[None]:
    with _paper_lock(root, ".control.lock"):
        yield


@contextmanager
def _paper_lock(root: Path, name: str) -> Iterator[None]:
    path = root / "reports" / "paper" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
