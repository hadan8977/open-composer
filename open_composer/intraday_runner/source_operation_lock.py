"""Reuse the existing quant2 book and intraday runner locks, without stopping them."""

import fcntl
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def source_account_operation(root: Path):
    from open_composer.book_paper.cli import _submission_lock
    from open_composer.intraday_runner.engine import runner_dir

    with _submission_lock(root, "quant2"):
        directory = runner_dir(root, "quant2")
        directory.mkdir(parents=True, exist_ok=True)
        with (directory / "run.lock").open("a+") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield
