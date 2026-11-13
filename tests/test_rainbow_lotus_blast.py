"""Rainbow: a bomb or line blast that reaches the lotus is not ported.

refill_misses 2026-11-13 211812 (bomb + horizontal swap, the bomb's diagonal
on the lotus) and 212012 (a bomb chain next to the lotus): the game removed
the lotus and drew 18 / 29 more than the simulator, which kept it. Until the
rule is ported the move is refused, like a Rainbow lotus gather, instead of
being planned as exact.
"""
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MISSES = ROOT / "Debug" / "refill_misses"


@pytest.mark.parametrize("name", [
    "20261113_211812_422117_rainbow",
    "20261113_212012_804694_rainbow",
])
def test_blast_on_the_rainbow_lotus_is_refused(name):
    folder = MISSES / name
    if not folder.is_dir():
        pytest.skip("recording not on this machine")
    import refill_monitor

    before = json.loads((folder / "000.json").read_text(encoding="utf-8"))
    after = json.loads((folder / "001.json").read_text(encoding="utf-8"))
    result = refill_monitor.check_transition(before, after)
    assert result["verdict"] == "unsupported", result
