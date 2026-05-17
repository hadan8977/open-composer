from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_CLEAN_TARGETS = ("data_cache", "reports")

PRESERVED_RUNTIME_RELPATHS = frozenset(
    {
        "reports/research/nasdaq_intraday_cycle_reversal_1m-intraday-daily-rotation.json",
        "reports/research/nasdaq_intraday_cycle_reversal_1m-intraday-daily-rotation.md",
        "reports/research/nasdaq_intraday_cycle_reversal_1m_llm-intraday-daily-rotation.json",
        "reports/research/nasdaq_intraday_cycle_reversal_1m_llm-intraday-daily-rotation.md",
        "reports/research/nasdaq_intraday_cycle_reversal_1m_llm-llm-intraday-selection.json",
        "reports/research/nasdaq_intraday_cycle_reversal_1m_llm-llm-intraday-selection.md",
        "reports/research/nasdaq_intraday_cycle_reversal_1m_llm-llm-intraday-selection-prompt.json",
        "reports/research/intraday-product-reflection.md",
    }
)


@dataclass(frozen=True)
class CacheTarget:
    key: str
    relpath: str
    label: str
    category: str
    cleanable: bool
    selected_by_default: bool
    note: str


@dataclass(frozen=True)
class CacheTargetStatus:
    target: CacheTarget
    exists: bool
    bytes_total: int
    file_count: int
    dir_count: int
    cleanable_bytes: int
    cleanable_files: int
    protected_files: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.target.key,
            "path": self.target.relpath,
            "label": self.target.label,
            "category": self.target.category,
            "exists": self.exists,
            "bytes_total": self.bytes_total,
            "size": format_bytes(self.bytes_total),
            "file_count": self.file_count,
            "dir_count": self.dir_count,
            "cleanable": self.target.cleanable,
            "selected_by_default": self.target.selected_by_default,
            "cleanable_bytes": self.cleanable_bytes,
            "cleanable_size": format_bytes(self.cleanable_bytes),
            "cleanable_files": self.cleanable_files,
            "protected_files": self.protected_files,
            "note": self.target.note,
        }


@dataclass(frozen=True)
class CacheCleanTargetResult:
    key: str
    path: str
    dry_run: bool
    files: int
    dirs: int
    bytes_total: int
    protected_files: int
    removed_paths: tuple[str, ...]
    protected_paths: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "path": self.path,
            "dry_run": self.dry_run,
            "files": self.files,
            "dirs": self.dirs,
            "bytes_total": self.bytes_total,
            "size": format_bytes(self.bytes_total),
            "protected_files": self.protected_files,
            "removed_paths": list(self.removed_paths),
            "protected_paths": list(self.protected_paths),
        }


@dataclass(frozen=True)
class CacheCleanResult:
    dry_run: bool
    targets: tuple[CacheCleanTargetResult, ...]

    @property
    def files(self) -> int:
        return sum(item.files for item in self.targets)

    @property
    def dirs(self) -> int:
        return sum(item.dirs for item in self.targets)

    @property
    def bytes_total(self) -> int:
        return sum(item.bytes_total for item in self.targets)

    @property
    def protected_files(self) -> int:
        return sum(item.protected_files for item in self.targets)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dry_run": self.dry_run,
            "files": self.files,
            "dirs": self.dirs,
            "bytes_total": self.bytes_total,
            "size": format_bytes(self.bytes_total),
            "protected_files": self.protected_files,
            "targets": [item.to_dict() for item in self.targets],
        }


RUNTIME_TARGETS = (
    CacheTarget(
        key="python_env",
        relpath=".venv",
        label="Python environment",
        category="dependency",
        cleanable=False,
        selected_by_default=False,
        note="Status only; rebuild intentionally instead of cleaning through oc cache.",
    ),
    CacheTarget(
        key="node_modules",
        relpath="dashboard/node_modules",
        label="Dashboard Node dependencies",
        category="dependency",
        cleanable=False,
        selected_by_default=False,
        note="Status only; rebuild intentionally instead of cleaning through oc cache.",
    ),
    CacheTarget(
        key="data_cache",
        relpath="data/cache",
        label="Market data cache",
        category="cache",
        cleanable=True,
        selected_by_default=True,
        note="Provider CSVs and manifests; live/sample workflows can rebuild them.",
    ),
    CacheTarget(
        key="reports",
        relpath="reports",
        label="Generated reports",
        category="runtime",
        cleanable=True,
        selected_by_default=True,
        note="Generated reports; tracked example research reports are protected.",
    ),
    CacheTarget(
        key="signal_logs",
        relpath="signal_logs",
        label="Signal logs",
        category="runtime_evidence",
        cleanable=True,
        selected_by_default=False,
        note="Evidence logs; clean only when you intentionally reset local runs.",
    ),
    CacheTarget(
        key="feature_logs",
        relpath="feature_logs",
        label="Feature packet logs",
        category="runtime_evidence",
        cleanable=True,
        selected_by_default=False,
        note="Feature evidence; clean only when you intentionally reset local runs.",
    ),
    CacheTarget(
        key="event_logs",
        relpath="event_logs",
        label="Event logs",
        category="runtime_evidence",
        cleanable=True,
        selected_by_default=False,
        note="Event evidence; clean only when you intentionally reset local runs.",
    ),
)

TARGETS_BY_KEY = {target.key: target for target in RUNTIME_TARGETS}


def build_cache_inventory(root: Path) -> list[CacheTargetStatus]:
    tracked = tracked_relpaths(root)
    return [_target_status(root, target, tracked) for target in RUNTIME_TARGETS]


def default_clean_target_keys() -> tuple[str, ...]:
    return DEFAULT_CLEAN_TARGETS


def all_runtime_clean_target_keys() -> tuple[str, ...]:
    return tuple(target.key for target in RUNTIME_TARGETS if target.cleanable)


def resolve_clean_target_keys(
    *,
    data_cache: bool = False,
    reports: bool = False,
    signal_logs: bool = False,
    feature_logs: bool = False,
    event_logs: bool = False,
    all_runtime: bool = False,
) -> tuple[str, ...]:
    if all_runtime:
        return all_runtime_clean_target_keys()
    selected: list[str] = []
    if data_cache:
        selected.append("data_cache")
    if reports:
        selected.append("reports")
    if signal_logs:
        selected.append("signal_logs")
    if feature_logs:
        selected.append("feature_logs")
    if event_logs:
        selected.append("event_logs")
    if selected:
        return tuple(selected)
    return default_clean_target_keys()


def clean_cache_targets(
    root: Path,
    target_keys: tuple[str, ...],
    *,
    dry_run: bool = True,
) -> CacheCleanResult:
    tracked = tracked_relpaths(root)
    results = tuple(
        _clean_target(root, _cleanable_target(key), tracked=tracked, dry_run=dry_run)
        for key in target_keys
    )
    return CacheCleanResult(dry_run=dry_run, targets=results)


def format_bytes(size: int) -> str:
    units = ("B", "KB", "MB", "GB", "TB")
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


def tracked_relpaths(root: Path) -> set[str]:
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z"],
            check=False,
            capture_output=True,
        )
    except (OSError, ValueError):
        return set(PRESERVED_RUNTIME_RELPATHS)
    if completed.returncode != 0:
        return set(PRESERVED_RUNTIME_RELPATHS)
    output = completed.stdout.decode("utf-8", errors="replace")
    paths = {item for item in output.split("\0") if item}
    paths.update(PRESERVED_RUNTIME_RELPATHS)
    return paths


def _target_status(root: Path, target: CacheTarget, tracked: set[str]) -> CacheTargetStatus:
    path = root / target.relpath
    if not path.exists() and not path.is_symlink():
        return CacheTargetStatus(
            target=target,
            exists=False,
            bytes_total=0,
            file_count=0,
            dir_count=0,
            cleanable_bytes=0,
            cleanable_files=0,
            protected_files=0,
        )
    entries = _inventory_entries(path)
    protected = {
        _relpath(item, root) for item in entries.files if _is_protected(item, root, tracked)
    }
    cleanable_files = 0
    cleanable_bytes = 0
    if target.cleanable:
        for file_path in entries.files:
            if _relpath(file_path, root) in protected:
                continue
            cleanable_files += 1
            cleanable_bytes += _entry_size(file_path)
    return CacheTargetStatus(
        target=target,
        exists=True,
        bytes_total=entries.bytes_total,
        file_count=len(entries.files),
        dir_count=len(entries.dirs),
        cleanable_bytes=cleanable_bytes,
        cleanable_files=cleanable_files,
        protected_files=len(protected),
    )


def _clean_target(
    root: Path,
    target: CacheTarget,
    *,
    tracked: set[str],
    dry_run: bool,
) -> CacheCleanTargetResult:
    path = root / target.relpath
    if not path.exists() and not path.is_symlink():
        return CacheCleanTargetResult(
            key=target.key,
            path=target.relpath,
            dry_run=dry_run,
            files=0,
            dirs=0,
            bytes_total=0,
            protected_files=0,
            removed_paths=(),
            protected_paths=(),
        )

    entries = _inventory_entries(path)
    protected_paths = tuple(
        sorted(_relpath(item, root) for item in entries.files if _is_protected(item, root, tracked))
    )
    removed_files: list[Path] = []
    bytes_total = 0
    for file_path in entries.files:
        if _relpath(file_path, root) in protected_paths:
            continue
        removed_files.append(file_path)
        bytes_total += _entry_size(file_path)
        if not dry_run:
            file_path.unlink(missing_ok=True)

    removed_dirs = _removable_dirs(entries.dirs, root, protected_paths)
    if not dry_run:
        for directory in removed_dirs:
            if directory.exists() and not any(directory.iterdir()):
                directory.rmdir()

    removed_paths = tuple(sorted(_relpath(item, root) for item in (*removed_files, *removed_dirs)))
    return CacheCleanTargetResult(
        key=target.key,
        path=target.relpath,
        dry_run=dry_run,
        files=len(removed_files),
        dirs=len(removed_dirs),
        bytes_total=bytes_total,
        protected_files=len(protected_paths),
        removed_paths=removed_paths,
        protected_paths=protected_paths,
    )


@dataclass(frozen=True)
class _InventoryEntries:
    files: tuple[Path, ...]
    dirs: tuple[Path, ...]
    bytes_total: int


def _inventory_entries(path: Path) -> _InventoryEntries:
    if path.is_symlink() or path.is_file():
        return _InventoryEntries(files=(path,), dirs=(), bytes_total=_entry_size(path))
    files: list[Path] = []
    dirs: list[Path] = []
    bytes_total = 0
    for current, dir_names, file_names in os.walk(path, followlinks=False):
        current_path = Path(current)
        for name in file_names:
            file_path = current_path / name
            files.append(file_path)
            bytes_total += _entry_size(file_path)
        for name in dir_names:
            dir_path = current_path / name
            if dir_path.is_symlink():
                files.append(dir_path)
                bytes_total += _entry_size(dir_path)
            else:
                dirs.append(dir_path)
    return _InventoryEntries(
        files=tuple(files),
        dirs=tuple(sorted(dirs, key=lambda item: len(item.parts), reverse=True)),
        bytes_total=bytes_total,
    )


def _removable_dirs(
    dirs: tuple[Path, ...], root: Path, protected_paths: tuple[str, ...]
) -> list[Path]:
    protected = tuple(Path(item) for item in protected_paths)
    removable: list[Path] = []
    for directory in dirs:
        relative_dir = Path(_relpath(directory, root))
        if any(_path_is_relative_to(protected_path, relative_dir) for protected_path in protected):
            continue
        removable.append(directory)
    return removable


def _cleanable_target(key: str) -> CacheTarget:
    target = TARGETS_BY_KEY.get(key)
    if target is None:
        raise ValueError(f"unknown cache target: {key}")
    if not target.cleanable:
        raise ValueError(f"cache target is status-only: {key}")
    return target


def _is_protected(path: Path, root: Path, tracked: set[str]) -> bool:
    return _relpath(path, root) in tracked


def _relpath(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _entry_size(path: Path) -> int:
    try:
        return path.lstat().st_size
    except OSError:
        return 0


def _path_is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True
