"""Launch only the approved Pie64 Match Masters instance and memory reader."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from tools import matchmasters_board_reader as reader


BLUESTACKS_PLAYER = Path(r"C:\Program Files\BlueStacks_nxt\HD-Player.exe")
BLUESTACKS_INSTANCE = os.environ.get("MM_BLUESTACKS_INSTANCE", "Pie64")
ADB_SERIAL = reader.DEFAULT_SERIAL
PACKAGE = reader.DEFAULT_PACKAGE
PROJECT_ROOT = Path(__file__).resolve().parent
READER_SCRIPT = PROJECT_ROOT / "tools" / "matchmasters_board_reader.py"
READER_PID_PATH = PROJECT_ROOT / "Debug" / "memory_board" / "reader.pid"
READER_LOG_PATH = PROJECT_ROOT / "Debug" / "memory_board" / "reader.log"

_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


@dataclass(frozen=True)
class MatchMastersLaunchResult:
    success: bool
    message: str
    serial: str = ADB_SERIAL
    game_pid: int | None = None
    namespace_cleaned: bool = False
    reader_pid: int | None = None
    reader_started: bool = False


def _run(args: list[str], *, timeout: float = 15.0) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=_CREATE_NO_WINDOW,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise reader.ReaderError(str(exc)) from exc


def _progress(callback: Callable[[str], None] | None, message: str) -> None:
    if callback is not None:
        callback(message)


def _wait_for_pie64(adb: str, callback: Callable[[str], None] | None) -> None:
    """Find the Pie64 instance and remember the port BlueStacks gave it.

    The port is not stable: BlueStacks hands each running instance the next
    free one (5555, 5556, ...), and a dead transport can keep the old port
    listed as "offline" forever. `reader.discover_serial` identifies the
    instance by what it is -- Android 9, 64-bit, game installed -- so a moved
    port is found instead of reported as a failure.
    """
    global ADB_SERIAL
    _progress(callback, "Trazim Pie64 (ADB port)...")
    # discover_serial owns the waiting (it polls `adb devices` for 45s), so this
    # must not wrap it in a second retry loop: a definitive answer -- "the only
    # thing online is the wrong instance" -- would then be sat on for another
    # minute instead of being shown.
    ADB_SERIAL = reader.discover_serial(adb)
    if ADB_SERIAL != reader.DEFAULT_SERIAL:
        _progress(callback, f"Pie64 je na {ADB_SERIAL} (ne na podrazumevanom portu)")


def _adopt_running_instance(
    adb: str, callback: Callable[[str], None] | None
) -> bool:
    """Use an instance that is already up, instead of starting another one.

    Short timeout on purpose: this only answers "is one online right now?", and
    the full wait belongs to `_wait_for_pie64` after the player is started.
    """
    global ADB_SERIAL
    try:
        ADB_SERIAL = reader.discover_serial(adb, timeout=6.0)
    except Exception:
        # Probing is an optimisation, never a gate: anything that goes wrong
        # here just means "nothing to adopt", and the normal launch path runs.
        return False
    _progress(callback, f"Koristim instancu koja vec radi ({ADB_SERIAL})")
    return True


def _wait_for_boot(adb: str, callback: Callable[[str], None] | None) -> None:
    deadline = time.monotonic() + 60.0
    while time.monotonic() < deadline:
        completed = _run(
            [adb, "-s", ADB_SERIAL, "shell", "getprop", "sys.boot_completed"],
            timeout=10.0,
        )
        if completed.returncode == 0 and (completed.stdout or "").strip() == "1":
            return
        _progress(callback, "Pie64 se podize...")
        time.sleep(1.0)
    raise reader.ReaderError("Pie64 boot nije zavrsen u roku od 60s")


def _wait_for_game_pid(adb: str) -> int:
    deadline = time.monotonic() + 25.0
    while time.monotonic() < deadline:
        pid = reader.game_pid(adb, ADB_SERIAL, PACKAGE)
        if pid is not None:
            return pid
        time.sleep(0.5)
    raise reader.ReaderError(f"Igra {PACKAGE} nije dobila proces u roku od 25s")


def _pid_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _existing_reader_pid() -> int | None:
    try:
        pid = int(READER_PID_PATH.read_text(encoding="ascii").strip())
    except (FileNotFoundError, OSError, ValueError):
        return None
    return pid if _pid_is_running(pid) else None


def start_memory_reader() -> tuple[int, bool]:
    existing = _existing_reader_pid()
    if existing is not None:
        return existing, False
    if not READER_SCRIPT.exists():
        raise reader.ReaderError(f"Nema Frida readera: {READER_SCRIPT}")
    READER_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    log_handle = READER_LOG_PATH.open("a", encoding="utf-8")
    try:
        process = subprocess.Popen(
            [
                sys.executable,
                str(READER_SCRIPT),
                "--serial",
                ADB_SERIAL,
                "--output",
                str(reader.DEFAULT_OUTPUT),
                "--latest",
                str(reader.DEFAULT_LATEST),
                "--poll-seconds",
                "0.25",
                "--quiet",
            ],
            cwd=str(PROJECT_ROOT),
            stdin=subprocess.DEVNULL,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            creationflags=_CREATE_NO_WINDOW,
        )
    finally:
        log_handle.close()
    time.sleep(0.35)
    if process.poll() is not None:
        try:
            tail = READER_LOG_PATH.read_text(encoding="utf-8")[-2000:]
        except OSError:
            tail = ""
        raise reader.ReaderError(f"Frida reader se odmah ugasio: {tail.strip()}")
    READER_PID_PATH.write_text(str(process.pid), encoding="ascii")
    return int(process.pid), True


def launch_match_masters(
    *,
    start_reader: bool = True,
    progress: Callable[[str], None] | None = None,
) -> MatchMastersLaunchResult:
    try:
        adb = reader.find_adb()
    except reader.ReaderError as exc:
        return MatchMastersLaunchResult(False, str(exc))
    if not BLUESTACKS_PLAYER.exists():
        return MatchMastersLaunchResult(False, f"Nema {BLUESTACKS_PLAYER}")
    try:
        # Any already-running instance that passes the identity check is the one
        # to use: starting BLUESTACKS_INSTANCE unconditionally would open a
        # second window next to the instance the user is actually playing on
        # (Pie64_2 got the bypass on 2026-08-20 and is as valid as Pie64).
        if not _adopt_running_instance(adb, progress):
            _progress(progress, f"Pokrecem BlueStacks {BLUESTACKS_INSTANCE}...")
            subprocess.Popen(
                [str(BLUESTACKS_PLAYER), "--instance", BLUESTACKS_INSTANCE],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=_CREATE_NO_WINDOW,
            )
            _wait_for_pie64(adb, progress)
        _wait_for_boot(adb, progress)

        _progress(progress, "Proveravam root modul...")
        root = reader.adb_shell(adb, ADB_SERIAL, "su -c 'id'")
        if "uid=0(root)" not in root:
            raise reader.ReaderError(f"Root nije dostupan na Pie64: {root}")

        _progress(progress, "Pokrecem Match Masters...")
        launched = _run(
            [
                adb,
                "-s",
                ADB_SERIAL,
                "shell",
                "monkey",
                "-p",
                PACKAGE,
                "-c",
                "android.intent.category.LAUNCHER",
                "1",
            ],
            timeout=20.0,
        )
        if launched.returncode != 0:
            raise reader.ReaderError(
                (launched.stderr or launched.stdout or "monkey launch failed").strip()
            )
        game_pid = _wait_for_game_pid(adb)
        _progress(progress, "Proveravam namespace zastitu...")
        reader.verify_namespace_cleaned(adb, ADB_SERIAL, game_pid)

        reader_pid = None
        reader_started = False
        if start_reader:
            _progress(progress, "Pokrecem Frida citac table...")
            reader_pid, reader_started = start_memory_reader()
        message = "Match Masters radi na Pie64; namespace_cleaned=yes"
        if reader_pid is not None:
            message += "; Frida reader " + ("pokrenut" if reader_started else "vec radi")
        return MatchMastersLaunchResult(
            True,
            message,
            game_pid=game_pid,
            namespace_cleaned=True,
            reader_pid=reader_pid,
            reader_started=reader_started,
        )
    except Exception as exc:
        return MatchMastersLaunchResult(False, str(exc))
