"""Special O'Rama: a plain three draws its special from the engine's list.

Frames from Debug/research/20261110_020934_special-o-rama (Solo). Before the
port a three left CREATED_SPECIAL, which the exact refill cannot carry, so
every move was "unported piece on the board".
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

FRAMES = Path(__file__).resolve().parent / "fixtures" / "special_orama"


@pytest.mark.parametrize("before,after,move", [
    # The player's own three: one Range draw, no placement draw.
    ("000", "001", "red 2 kol 5 -> red 3 kol 5"),
    # A cascade three: the type draw comes before its placement draw.
    ("005", "006", "red 5 kol 4 -> red 6 kol 4"),
])
def test_recorded_move_is_exact(before, after, move):
    from tools.analyze_research import capture_from, observed, try_transition
    rec_a = json.loads((FRAMES / f"{before}.json").read_text(encoding="utf-8"))
    rec_b = json.loads((FRAMES / f"{after}.json").read_text(encoding="utf-8"))
    matches, closest, _ = try_transition(capture_from(rec_a), observed(rec_b))
    assert any(name.startswith(move) for name, _ in matches), closest


def test_list_is_the_engine_cctor_order():
    import engine_refill
    assert engine_refill.EVERY_MATCH_SPECIALS == (4, 5, 4, 5, 6, 7)
