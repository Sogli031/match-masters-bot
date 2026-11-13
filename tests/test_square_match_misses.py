"""Refill misses from the 2026-11-13 Square Match game (16:09-16:17), now exact.

* 161032_crosshair_heart: a crosshair picks among Vinnie hearts (SlotValue 23,
  canBeMatched and damageable): they are plain pieces to it, not classic
  specials. Nine of the game's twelve misses stopped on this.
* 161713_square_line_cell: a cascade square with one more cell in line (five
  cells) places its crosshair at draw % 5 over the run of three, then the
  other two -- the order the traced combo lists them in.
* cc_153230_035_prevent: Color Crush, Cleo with a horizontal partner and the
  prevention drawn: the prevention holds for a special partner too.

Traced against the engine's swap trace (the order specials fire in decides what
a crosshair may still pick):

* 161003_area_order: a bomb's area runs centre, ring clockwise from the top
  left, then two out; its row special fires before the crosshair beside it.
* 161455_heart_order: a heart's colour wipe walks the board x-major.
* 162046_square_cascade_order: a cascade square lists its cells clockwise.
* 161607_heart_merge_four: a heart dragged into a line special while lining up
  a four: both fire and the four still leaves its column special.
* 160226_crosshair_bomb_merge: a bomb dragged onto a crosshair: both fire from
  the end cell, the bomb first.
* 161938_011_cleo_bomb: Cleo with a bomb partner beside a second Cleo: the
  partner fires first, and the spent figure's colour is gone from the refill.
* super_sized_cleo_plain / _bomb: Super Sized (plain board 0, 8x8) with the
  booster's Cleo, a plain and a bomb partner (research 20261113_170250
  004->005, 010->011); refused as "not ported" before.
* cc_171559_010_no_crush: Color Crush crushes a colour only through a combo
  on the Cleo swipe's merge cell; a clone T elsewhere clears its own cells.
* cc_171559_007_vertical_partner: the forced one-cell merge combo crushes
  nothing, and equal deltas clone the bigger colour (traced).
* cc_153230_029_lightning_partner: a Lightning partner, same crush rule.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FIXTURES = ROOT / "tests" / "fixtures" / "square_match_misses"


@pytest.mark.parametrize("name", ["161032_crosshair_heart", "161713_square_line_cell",
                                  "cc_153230_035_prevent", "161003_area_order",
                                  "161455_heart_order", "162046_square_cascade_order",
                                  "161607_heart_merge_four", "160226_crosshair_bomb_merge",
                                  "161938_011_cleo_bomb", "super_sized_cleo_plain",
                                  "super_sized_cleo_bomb", "cc_171559_007_vertical_partner",
                                  "cc_171559_010_no_crush", "cc_153230_029_lightning_partner"])
def test_recorded_move_is_exact(name):
    from refill_monitor import check_transition

    pair = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    result = check_transition(pair["before"], pair["after"]) or {}
    assert result.get("verdict") == "ok", result


@pytest.mark.parametrize("name,start,target", [
    ("161938_011_cleo_bomb", (6, 5), (6, 6)),
    ("super_sized_cleo_bomb", (6, 1), (7, 1)),
    ("super_sized_cleo_plain", (2, 7), (2, 6)),
    ("cc_171559_007_vertical_partner", (6, 6), (6, 5)),
    ("cc_171559_010_no_crush", (0, 4), (0, 5)),
])
def test_planner_takes_the_exact_cleo_swipe(name, start, target):
    """The planner's own step (no refill-check flag) replays the Cleo swipe exactly."""
    from simulator_capture import lab_move
    from strategy_lab import planner, simulation
    from tools.analyze_research import capture_from
    from tools.verify_cleo import differences

    pair = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    lab = lab_move(capture_from(pair["before"]))
    lab["perks"] = {}
    action = next(a for a in planner.actions(lab) if a.get("kind", "swap") == "swap"
                  and (tuple(a["start"]), tuple(a["target"])) == (start, target))
    result = simulation.step(lab, action)
    assert result.get("supported"), result.get("reason")
    assert result["events"][0]["type"] == "cleo_exact_swipe"
    assert differences(pair["after"], result["state"]) == {}


def test_square_plus_line_lists_the_run_first():
    import move_strategy as ms

    cells = {(5, 3), (5, 4), (5, 5), (6, 4), (6, 5)}
    assert ms._square_plus_line_cells(cells) == [(5, 3), (5, 4), (5, 5), (6, 4), (6, 5)]
    vertical = {(2, 0), (3, 0), (4, 0), (3, 1), (4, 1)}
    assert ms._square_plus_line_cells(vertical) == [(2, 0), (3, 0), (4, 0), (3, 1), (4, 1)]
    assert ms._square_plus_line_cells({(0, 0), (0, 1), (0, 2), (1, 1), (2, 1)}) is None
