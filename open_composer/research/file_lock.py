"""Exclusive file locks on Linux and native Windows, released on handle close."""

from __future__ import annotations

import os


def lock_file(handle, *, blocking: bool = True) -> None:
    _file_lock(handle, blocking=blocking)


def unlock_file(handle) -> None:
    _file_lock(handle, unlock=True)


def _file_lock(handle, *, blocking: bool = True, unlock: bool = False) -> None:
    if os.name != "nt":
        import fcntl

        flags = fcntl.LOCK_UN if unlock else fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
        fcntl.flock(handle, flags)
        return

    import ctypes
    import msvcrt
    from ctypes import wintypes

    class Overlapped(ctypes.Structure):
        _fields_ = [
            ("Internal", ctypes.c_size_t),
            ("InternalHigh", ctypes.c_size_t),
            ("Offset", wintypes.DWORD),
            ("OffsetHigh", wintypes.DWORD),
            ("hEvent", wintypes.HANDLE),
        ]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    acquire = kernel.UnlockFileEx if unlock else kernel.LockFileEx
    acquire.argtypes = (
        [wintypes.HANDLE] + [wintypes.DWORD] * (3 if unlock else 4) + [ctypes.POINTER(Overlapped)]
    )
    acquire.restype = wintypes.BOOL
    # Fixed offset zero, independent of append mode/EOF. Lock beyond EOF too.
    overlapped = Overlapped()
    flags = 2 | (0 if blocking else 1)
    descriptor = handle if isinstance(handle, int) else handle.fileno()
    arguments = (
        [msvcrt.get_osfhandle(descriptor), 0]
        if unlock
        else [msvcrt.get_osfhandle(descriptor), flags, 0]
    )
    if not acquire(*arguments, 0xFFFFFFFF, 0xFFFFFFFF, ctypes.byref(overlapped)):
        error = ctypes.get_last_error()
        if error == 33:
            raise BlockingIOError(error, "File is locked by another process")
        raise ctypes.WinError(error)
