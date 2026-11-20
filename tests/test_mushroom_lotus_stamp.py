"""Froggy Fu lotus under a score multiplier (Mighty Mushrooms Versus).

Research 20261120_040308 004 -> 005: a yellow L through the lotus gathers 10
cells, a mushroom (x4) raises the multiplier 7 -> 11. The game paid 583 =
13 pieces x 11 + 10 gathered x rainbow 4 x 11; the stamp was lost before (143).
"""
from pathlib import Path

from tools.analyze_research import load
from tools.replay_one_to_one import replay

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "mushroom_lotus"


def test_lotus_stamp_is_paid_at_the_multiplier():
    rec_a, cap_a = load(FIXTURES / "before.json")
    rec_b, _ = load(FIXTURES / "after.json")
    got = replay(rec_a, cap_a, rec_b)
    assert "skip" not in got, got
    assert got["points"] == (583, 583)
    assert got["cells"] == 0 and got["rng"][0] == got["rng"][1]


def test_round_end_without_a_mushroom_keeps_the_turn_thresholds():
    """Versus research 20261120_040308 006 -> 007: the round's last move took
    no mushroom; the game kept preventing matches in its refills (96 points),
    the turn-end switch made a third cascade (144)."""
    folder = Path(__file__).resolve().parent / "fixtures" / "round_end"
    rec_a, cap_a = load(folder / "before.json")
    rec_b, _ = load(folder / "after.json")
    got = replay(rec_a, cap_a, rec_b)
    assert got["cells"] == 0 and got["specials"] == 0
    assert got["rng"][0] == got["rng"][1] and got["points"] == (96, 96)
