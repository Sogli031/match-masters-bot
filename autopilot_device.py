"""ADB veza Autopilota za jednu, imenovanu BlueStacks instancu (Pie64_2).

Port se cita iz BlueStacks konfiguracije pri svakom pokretanju
(`bst.instance.<ime>.status.adb_port`), jer ga BlueStacks menja izmedju
restarta (Pie64_2: 5575, 5576, 5577...). Svi screenshotovi i tapovi idu
iskljucivo preko `adb -s <taj serial>`: nema prozora, misa ni ekranskih
koordinata, pa druga instanca ne moze da primi klik.

Svaki tap prolazi kroz `StopGate`: Stop postavlja dogadjaj, a tap ga
proverava neposredno pre slanja komande, pa posle Stop-a ne izlazi nijedan
novi klik.
"""
from __future__ import annotations

import io
import os
import re
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path

from tools import matchmasters_board_reader as reader

INSTANCE_NAME = os.environ.get("MM_AUTOPILOT_INSTANCE", "Pie64_2")
_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class DeviceError(RuntimeError):
    pass


class StopRequested(RuntimeError):
    """Stop je pritisnut: klik nije poslat."""


class StopGate:
    """Jedno mesto koje odlucuje sme li sledeci klik da izadje."""

    def __init__(self):
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def reset(self) -> None:
        self._stop.clear()

    @property
    def stopped(self) -> bool:
        return self._stop.is_set()

    def check(self) -> None:
        if self._stop.is_set():
            raise StopRequested("Stop: klik blokiran")

    def wait(self, seconds: float) -> bool:
        """Spava, ali se budi odmah na Stop. True ako je Stop pritisnut."""
        return self._stop.wait(max(0.0, seconds))


def bluestacks_conf_path() -> Path:
    root = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
    return root / "BlueStacks_nxt" / "bluestacks.conf"


def instance_port(conf_text: str, instance: str = INSTANCE_NAME) -> int | None:
    """ADB port instance iz bluestacks.conf; `status.adb_port` (zivi) ima prednost."""
    values: dict[str, str] = {}
    pattern = re.compile(rf'^bst\.instance\.{re.escape(instance)}\.(status\.adb_port|adb_port)="?(\d+)"?\s*$')
    for line in conf_text.splitlines():
        match = pattern.match(line.strip())
        if match:
            values[match.group(1)] = match.group(2)
    port = values.get("status.adb_port") or values.get("adb_port")
    return int(port) if port else None


def resolve_instance_serial(adb: str, instance: str = INSTANCE_NAME, *, conf_text: str | None = None) -> str:
    """Serial (127.0.0.1:<port>) imenovane instance, proveren preko ADB-a."""
    if conf_text is None:
        try:
            conf_text = bluestacks_conf_path().read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            raise DeviceError(f"Ne mogu da procitam BlueStacks konfiguraciju: {exc}") from exc
    port = instance_port(conf_text, instance)
    if port is None:
        raise DeviceError(f"{instance} nema ADB port u bluestacks.conf (da li je instanca pokrenuta?)")
    serial = f"127.0.0.1:{port}"
    if serial in reader.FORBIDDEN_SERIALS:
        raise DeviceError(f"{instance} -> {serial} je na listi zabranjenih instanci")
    # Druga instanca na istom portu bi znacila zastarelu konfiguraciju.
    for other in re.findall(r'^bst\.instance\.([^.]+)\.status\.adb_port="?(\d+)"?', conf_text, re.M):
        if other[0] != instance and int(other[1]) == port:
            raise DeviceError(f"Port {port} prijavljuju i {instance} i {other[0]}; ne klikcem naslepo")
    reader._adb_connect(adb, serial)
    devices = reader.parse_adb_devices(reader._run([adb, "devices"], timeout=10.0).stdout or "")
    if devices.get(serial) != "device":
        raise DeviceError(f"{instance} ({serial}) nije online u adb devices: {devices or 'prazno'}")
    if not reader.is_pie64_instance(adb, serial):
        raise DeviceError(f"{serial} nije Pie64 instanca sa Match Masters-om")
    return serial


@dataclass
class AdbDevice:
    """Screenshot i tap za tacno jedan serial; tap uvek kroz StopGate."""

    adb: str
    serial: str
    gate: StopGate

    def _run(self, args: list[str], *, timeout: float, text: bool = True):
        try:
            return subprocess.run([self.adb, "-s", self.serial, *args], capture_output=True,
                                  text=text, timeout=timeout, creationflags=_CREATE_NO_WINDOW)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise DeviceError(f"adb {' '.join(args[:2])}: {exc}") from exc

    def screenshot_png(self) -> bytes:
        done = self._run(["exec-out", "screencap", "-p"], timeout=15.0, text=False)
        if done.returncode != 0 or not done.stdout:
            raise DeviceError("screencap nije uspeo: " + (done.stderr or b"").decode(errors="replace"))
        return done.stdout

    def screenshot(self):
        from PIL import Image
        return Image.open(io.BytesIO(self.screenshot_png())).convert("RGB")

    def swipe(self, x1: int, y1: int, x2: int, y2: int, ms: int = 450) -> None:
        """Skrol prstom (npr. kroz listu boostera); i on prolazi kroz StopGate."""
        self.gate.check()
        done = self._run(["shell", "input", "swipe", *(str(int(v)) for v in (x1, y1, x2, y2, ms))],
                         timeout=10.0)
        if done.returncode != 0:
            raise DeviceError(f"swipe nije uspeo: {(done.stderr or done.stdout).strip()}")

    def tap(self, x: int, y: int) -> None:
        self.gate.check()
        done = self._run(["shell", "input", "tap", str(int(x)), str(int(y))], timeout=10.0)
        if done.returncode != 0:
            raise DeviceError(f"tap ({x},{y}) nije uspeo: {(done.stderr or done.stdout).strip()}")
