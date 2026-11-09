"""Cleo booster figure on Score Market (board 20), 2026-11-09 recording.

Frames from Debug/research/20261109_192920_score-market. The board holds
hearts (SlotValue 23), line specials and up to three booster Cleos. A hit
needs the board, specials, every RNG field and the move counter.
"""
import json
from pathlib import Path

import pytest

FRAMES = Path(__file__).resolve().parent / "fixtures" / "cleo_score_market"


def _replay(before, after, start, target):
    from strategy_lab import simulation
    from simulator_capture import lab_move
    from tools.analyze_research import capture_from
    from tools.verify_cleo import cleo_actions, differences
    record = json.loads((FRAMES / f"{before}.json").read_text(encoding="utf-8"))
    want = json.loads((FRAMES / f"{after}.json").read_text(encoding="utf-8"))
    lab = lab_move(capture_from(record))
    action = next(a for a in cleo_actions(record)
                  if a["start"] == list(start) and a["target"] == list(target))
    previous = simulation.PREFIX_MODES
    simulation.PREFIX_MODES = set(previous) | {lab["mode"]}
    try:
        result = simulation.step(lab, action)
    finally:
        simulation.PREFIX_MODES = previous
    return result, (differences(want, result["state"]) if result.get("supported") else None)


@pytest.mark.parametrize("before,after,start,target", [
    # No combo at all: the placeholder still dies, source and target refill.
    ("005", "006", (0, 2), (1, 2)),
    ("005", "006", (1, 2), (0, 2)),
    # A four from the conversion makes a line special; a heart then fires.
    ("023", "024", (5, 0), (6, 0)),
    ("023", "024", (6, 0), (5, 0)),
])
def test_plain_partner_swipe_is_exact(before, after, start, target):
    result, diff = _replay(before, after, start, target)
    assert result.get("supported"), result.get("reason")
    assert diff == {}


@pytest.mark.parametrize("before,after,start,target", [
    # A vertical partner: its clones carry the vertical (a colour-3 heart
    # too), the conversion four's special starts at its first x-major cell.
    ("017", "018", (5, 1), (6, 1)),
    # Prevention drawn at 50% but ignored: not a colour-based clone.
    ("020", "021", (6, 5), (6, 4)),
])
def test_special_partner_swipe_is_exact(before, after, start, target):
    result, diff = _replay(before, after, start, target)
    assert result.get("supported"), result.get("reason")
    assert diff == {}
