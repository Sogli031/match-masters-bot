"""Slika trenutni ekran Pie64_2 preko ADB-a za pravila Autopilota.

    python tools/autopilot_snap.py lobby
    python tools/autopilot_snap.py results__win

Snima u assets/autopilot/screens/<ime>.png. Ne klikce nista.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from autopilot_device import INSTANCE_NAME, AdbDevice, StopGate, resolve_instance_serial  # noqa: E402
from autopilot_screens import SCREENS_DIR, ScreenClassifier  # noqa: E402
from tools import matchmasters_board_reader as reader  # noqa: E402


def main(argv: list[str]) -> int:
    if len(argv) != 1 or not argv[0].replace("_", "").isalnum():
        print(__doc__)
        return 2
    name = argv[0].lower()
    adb = reader.find_adb()
    serial = resolve_instance_serial(adb)
    png = AdbDevice(adb, serial, StopGate()).screenshot_png()
    SCREENS_DIR.mkdir(parents=True, exist_ok=True)
    target = SCREENS_DIR / f"{name}.png"
    if target.exists():
        print(f"{target.name} vec postoji; prepisujem")
    target.write_bytes(png)
    print(f"{INSTANCE_NAME} ({serial}) -> {target}")
    cls = ScreenClassifier().classify(target)
    print(f"Lokalno prepoznato kao: {cls.name or 'nepoznat'} ({cls.score:.2f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
