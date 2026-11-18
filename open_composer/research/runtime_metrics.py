"""Process resource measurements with the existing Linux units."""

from __future__ import annotations

import os


def process_usage():
    """getrusage(RUSAGE_SELF); on Windows the same ru_maxrss (KiB), ru_utime and ru_stime."""
    if os.name != "nt":
        import resource

        return resource.getrusage(resource.RUSAGE_SELF)
    import ctypes
    from types import SimpleNamespace

    class Counters(ctypes.Structure):  # PROCESS_MEMORY_COUNTERS
        _fields_ = [
            ("cb", ctypes.c_ulong),
            ("PageFaultCount", ctypes.c_ulong),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("Other", ctypes.c_size_t * 7),
        ]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    kernel.K32GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
    counters = Counters(cb=ctypes.sizeof(Counters))
    if not kernel.K32GetProcessMemoryInfo(
        kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    times = os.times()
    return SimpleNamespace(
        ru_maxrss=counters.PeakWorkingSetSize / 1024, ru_utime=times.user, ru_stime=times.system
    )
