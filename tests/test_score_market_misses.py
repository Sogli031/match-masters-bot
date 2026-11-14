"""Score Market refill misses of 2026-11-14.

182926 (Disco Ball swipe): a Lightning in the second cascade had its targets
from the engine RNG, but the special-swap loops still took it as a random
refill boundary and stopped, without a boundary event, so a 6-6-6 stayed on
the "resting" board (game 26 draws more). It now cascades to the end, exact.

183046 (heart swiped onto a row rocket): the game merges the two
(CupidHeartPieceLogic's merge types): the heart's colour first, then the
rocket from the swipe's end cell, as for Vinnie SE's pair heart. The
simulator fired them one by one (12 draws more, two hearts fewer). The plain
heart now takes that merge too, reading its colour where it stands.
"""
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MISSES = ROOT / "Debug" / "refill_misses"


def _check(name):
    folder = MISSES / name
    if not folder.is_dir():
        pytest.skip("recording not on this machine")
    import refill_monitor

    before = json.loads((folder / "000.json").read_text(encoding="utf-8"))
    after = json.loads((folder / "001.json").read_text(encoding="utf-8"))
    return refill_monitor.check_transition(before, after)


def test_disco_swipe_cascades_past_an_engine_lightning():
    result = _check("20261114_182926_976934_score-market")
    assert result["verdict"] == "ok", result


def test_plain_heart_merges_with_a_classic_special():
    result = _check("20261114_183046_538912_score-market")
    assert result["verdict"] == "ok", result
