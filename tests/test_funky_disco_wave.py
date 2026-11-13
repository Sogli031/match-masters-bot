"""Funky Tiles: a disco wipe that destroys a marker fires its blast too.

refill_misses 2026-11-13 131758 and 131900: the disco wiped the colour on a
Funky marker; the game blasted, the simulator used to skip the wave.
"""
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MISSES = ROOT / "Debug" / "refill_misses"


@pytest.mark.parametrize("name", [
    "20261113_131758_161511_funky-tiles",
    "20261113_131900_894272_funky-tiles",
])
def test_disco_wipe_fires_the_funky_marker(name):
    folder = MISSES / name
    if not folder.is_dir():
        pytest.skip("recording not on this machine")
    import refill_monitor

    before = json.loads((folder / "000.json").read_text(encoding="utf-8"))
    after = json.loads((folder / "001.json").read_text(encoding="utf-8"))
    assert refill_monitor.check_transition(before, after)["verdict"] == "ok"
