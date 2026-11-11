"""Heavy offline analyses that never slow BlueStacks down.

    from tools.gentle import gentle_pool
    with gentle_pool() as pool:
        results = pool.map(work, items)

Every process started here (the caller and the pool's workers) runs at Windows
IDLE priority and only on the last physical core (GENTLE_CPUS), so the game and
the bot keep the other cores to themselves. Idle priority alone was not enough
(2026-11-11: two idle workers on any core still made the game stutter -- they
shared physical cores and cache with HD-Player).
"""
from __future__ import annotations

import os
import sys
from multiprocessing import Pool

# The last physical core of the machine: on the Ryzen 5 7600 (6 cores, 12
# threads) logical CPUs 10 and 11. Change here if the machine changes.
GENTLE_CPUS = (10, 11)
GENTLE_WORKERS = len(GENTLE_CPUS)

_IDLE_PRIORITY_CLASS = 0x40


def make_gentle() -> None:
    """Put the current process on idle priority and the GENTLE_CPUS."""
    if sys.platform != "win32":
        try:
            os.nice(19)
        except (AttributeError, OSError):
            pass
        return
    import ctypes

    kernel32 = ctypes.windll.kernel32
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    handle = ctypes.c_void_p(kernel32.GetCurrentProcess())
    kernel32.SetPriorityClass(handle, _IDLE_PRIORITY_CLASS)
    cpus = [cpu for cpu in GENTLE_CPUS if cpu < (os.cpu_count() or 1)]
    if cpus:
        mask = sum(1 << cpu for cpu in cpus)
        kernel32.SetProcessAffinityMask(handle, ctypes.c_size_t(mask))


def gentle_pool(workers: int | None = None) -> Pool:
    """A multiprocessing Pool whose workers are gentle too."""
    make_gentle()
    return Pool(min(workers or GENTLE_WORKERS, GENTLE_WORKERS), initializer=make_gentle)
