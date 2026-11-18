"""Native Windows research processes, each in one kernel Job Object.

The job caps the tree's committed (private) memory and has KILL_ON_JOB_CLOSE:
kill(), leaving the context, or the controller dying kills every process in it.
"""

from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
from ctypes import wintypes
from pathlib import Path

_KILL_ON_JOB_CLOSE = 0x2000
_JOB_MEMORY = 0x200
_EXTENDED_LIMIT_INFORMATION = 9
_QUERY_AND_SYNCHRONIZE = 0x1000 | 0x100000


class _ExtendedLimits(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
        *[(f"IoCounter{i}", ctypes.c_uint64) for i in range(6)],
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class _MemoryStatus(ctypes.Structure):
    _fields_ = [("dwLength", wintypes.DWORD), ("dwMemoryLoad", wintypes.DWORD)] + [
        (name, ctypes.c_uint64)
        for name in (
            "TotalPhys",
            "AvailPhys",
            "TotalPageFile",
            "AvailPageFile",
            "TotalVirtual",
            "AvailVirtual",
            "AvailExtendedVirtual",
        )
    ]


if os.name == "nt":
    _kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    _H, _D, _B, _P = wintypes.HANDLE, wintypes.DWORD, wintypes.BOOL, ctypes.c_void_p
    for _name, _args, _result in (
        ("CreateJobObjectW", [_P, wintypes.LPCWSTR], _H),
        ("SetInformationJobObject", [_H, ctypes.c_int, _P, _D], _B),
        ("AssignProcessToJobObject", [_H, _H], _B),
        ("TerminateJobObject", [_H, wintypes.UINT], _B),
        ("CloseHandle", [_H], _B),
        ("OpenProcess", [_D, _B, _D], _H),
        ("GetProcessTimes", [_H, _P, _P, _P, _P], _B),
        ("WaitForSingleObject", [_H, _D], _D),
        ("GlobalMemoryStatusEx", [_P], _B),
    ):
        getattr(_kernel, _name).argtypes = _args
        getattr(_kernel, _name).restype = _result


def _check(result):
    if not result:
        raise ctypes.WinError(ctypes.get_last_error())
    return result


def global_memory() -> dict[str, int]:
    status = _MemoryStatus(dwLength=ctypes.sizeof(_MemoryStatus))
    _check(_kernel.GlobalMemoryStatusEx(ctypes.byref(status)))
    return {
        "total_mb": status.TotalPhys // 1048576,
        "available_mb": status.AvailPhys // 1048576,
        "available_commit_mb": status.AvailPageFile // 1048576,
    }


def process_start(pid: int) -> tuple[int, bool]:
    """Creation time of pid (FILETIME ticks) and whether it is still running."""
    handle = _kernel.OpenProcess(_QUERY_AND_SYNCHRONIZE, False, pid)
    if not handle:
        raise ProcessLookupError(pid)
    try:
        times = [ctypes.c_uint64() for _ in range(4)]
        _check(_kernel.GetProcessTimes(handle, *map(ctypes.byref, times)))
        return times[0].value, _kernel.WaitForSingleObject(handle, 0) != 0
    finally:
        _kernel.CloseHandle(handle)


def executable_argv(argv: list[str]) -> list[str]:
    """Run the npm codex/pi shims through node.exe directly, never through cmd.exe."""
    path = Path(shutil.which(argv[0]) or argv[0])
    name = path.stem.lower()
    if path.suffix.lower() == ".exe" or name not in ("codex", "pi"):
        return [str(path), *argv[1:]]
    if name == "codex":
        node = path.parent / "node.exe"
        script = path.parent / "node_modules/@openai/codex/bin/codex.js"
    else:
        node = Path(os.environ.get("LOCALAPPDATA", "")) / "pi-node/current/node.exe"
        script = path.parent / "pi-launcher.js"
    return [str(node) if node.is_file() else "node.exe", str(script), *argv[1:]]


class WindowsProcess(subprocess.Popen):
    """Popen whose whole process tree runs in one memory-capped kill-on-close job."""

    def __init__(self, argv: list[str], *, memory_bytes: int, **kwargs):
        self._job = _check(_kernel.CreateJobObjectW(None, None))
        limits = _ExtendedLimits(
            LimitFlags=_KILL_ON_JOB_CLOSE | _JOB_MEMORY, JobMemoryLimit=memory_bytes
        )
        try:
            _check(
                _kernel.SetInformationJobObject(
                    self._job,
                    _EXTENDED_LIMIT_INFORMATION,
                    ctypes.byref(limits),
                    ctypes.sizeof(limits),
                )
            )
            super().__init__(executable_argv(argv), **kwargs)
        except BaseException:
            self._close_job()
            raise
        if not _kernel.AssignProcessToJobObject(self._job, int(self._handle)):
            error = ctypes.WinError(ctypes.get_last_error())
            subprocess.Popen.kill(self)
            self.__exit__(None, None, None)
            raise error

    def kill(self):
        """Kill every process in the job, not only the leader."""
        if self._job:
            _check(_kernel.TerminateJobObject(self._job, 1))

    terminate = kill

    def _close_job(self):
        if self._job:
            _kernel.CloseHandle(self._job)
            self._job = None

    def __exit__(self, exc_type, value, traceback):
        try:
            self.kill()  # descendants never outlive the context
            super().__exit__(exc_type, value, traceback)
        finally:
            self._close_job()
