"""Color Crush: a special + special swipe that also lines up a four.

refill_misses 2026-11-14 185442: a row rocket dragged onto a bomb inside a
colour-6 four. The game fires the pair (bomb + line, no merge type), wipes
every other 6 on the board (the Color Crush rule on the swipe's own match) and
leaves the four's row rocket on the end cell. The simulator skipped the wipe
and the rocket: 28 draws short, four holes fewer. Now exact.
"""
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MISS = ROOT / "Debug" / "refill_misses" / "20261114_185442_142529_color-crush"


def test_special_swap_four_crushes_its_colour_and_keeps_its_special():
    if not MISS.is_dir():
        pytest.skip("recording not on this machine")
    import refill_monitor

    before = json.loads((MISS / "000.json").read_text(encoding="utf-8"))
    after = json.loads((MISS / "001.json").read_text(encoding="utf-8"))
    result = refill_monitor.check_transition(before, after)
    assert result["verdict"] == "ok", result
