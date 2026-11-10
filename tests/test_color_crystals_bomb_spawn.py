"""Color Crystals (board 16): the refill's bombs skip the players' colours too.

2026-11-10 Solo, Debug/refill_misses 20261110_014626: the bomb tile config
has no excludePlayersColorOnRefill, yet the game shuffled one hole fewer and
put the bomb on the other hole. The rule is the board's, not the default.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

FRAMES = Path(__file__).resolve().parent / "fixtures" / "color_crystals_bomb"


def test_played_four_replays_exactly():
    from tools.analyze_research import capture_from, observed, try_transition
    before = json.loads((FRAMES / "000.json").read_text(encoding="utf-8"))
    after = json.loads((FRAMES / "001.json").read_text(encoding="utf-8"))
    matches, closest, _ = try_transition(capture_from(before), observed(after))
    assert any("red 2 kol 1 -> red 2 kol 2" in move for move, _ in matches), closest


def test_other_boards_keep_the_flag():
    import engine_refill
    assert engine_refill.COLOR_CRYSTALS_BOARD == 16
    assert 16 not in engine_refill.MUSHROOM_BOARDS
