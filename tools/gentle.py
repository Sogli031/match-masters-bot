"""Pool for heavy offline analyses.

    from tools.gentle import gentle_pool
    with gentle_pool() as pool:
        results = pool.map(work, items)

2026-11-17: the player asked for every core at normal priority (analyses
run while nobody plays). Before that every process ran at Windows IDLE
priority on the last physical core only (2026-11-11: two idle workers made
the game stutter); set FULL_POWER = False to go back to that.
"""
from __future__ import annotations

import os
import sys
from multiprocessing import Pool

FULL_POWER = True
# The last physical core of the machine (Ryzen 5 7600: logical CPUs 10 and
# 11), used only when FULL_POWER is off.
GENTLE_CPUS = (10, 11)
GENTLE_WORKERS = (os.cpu_count() or 1) if FULL_POWER else len(GENTLE_CPUS)

_IDLE_PRIORITY_CLASS = 0x40


def make_gentle() -> None:
    """FULL_POWER: nothing. Otherwise idle priority on the GENTLE_CPUS."""
    if FULL_POWER:
        return
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
    """A multiprocessing Pool: every core (FULL_POWER) or the gentle ones."""
    make_gentle()
    return Pool(min(workers or GENTLE_WORKERS, GENTLE_WORKERS), initializer=make_gentle)
