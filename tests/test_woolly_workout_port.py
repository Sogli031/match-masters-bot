"""Woolly Workout booster (WoollyWorkout.Use 0x5ada438): the recolour step.

Each piece of the tapped colour colours its four neighbours unless the
neighbour is a source, a BoardSpecial (crystal, mushroom) or already coloured;
specials keep their type. chanceForAllDirections draws once even at 100.
The cascade after it is not yet confirmed against a recording (research
20261114_223640 002->003: colour 3 is closest, 1740 draws against 1784).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import move_strategy as ms
from engine_rng import EngineRNG
from strategy_lab import simulation


class _Model:
    def __init__(self):
        self.rng = EngineRNG.from_seed(1234)
        self.profile = {"players": [{"model": {"specialAbilityParams": {"chanceForAllDirections": "100"}}}]}


def test_one_neighbour_per_direction_and_one_draw():
    board = [[1] * 7 for _ in range(7)]
    board[3][3] = ms.GREEN
    special = [[0] * 7 for _ in range(7)]
    special[2][3] = ms.SPECIAL_MUSHROOM
    model = _Model()
    before = model.rng.counter
    out = simulation.woolly_workout_convert(board, special, ms.GREEN, model)
    assert model.rng.counter == before + 1
    changed = {(r, c) for r in range(7) for c in range(7) if out[r][c] != board[r][c]}
    assert changed == {(4, 3), (3, 2), (3, 4)}


def test_no_piece_of_the_colour_is_refused():
    board = [[1] * 7 for _ in range(7)]
    assert simulation.woolly_workout_convert(board, [[0] * 7 for _ in range(7)], ms.GREEN, _Model()) is None


import json
import pytest

FIXTURES = ROOT / "tests" / "fixtures" / "woolly_workout"


@pytest.mark.parametrize("name", ["224536_001", "224536_008", "223640_013"])
def test_recorded_woolly_activation_is_exact(name):
    """Square Match 2026-11-14: two traced activations (the recolour, the
    specials on each combo's first recoloured cell, the specials firing in
    the combos' order) and one without the tapped colour (found: 4)."""
    from refill_monitor import check_transition

    pair = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    result = check_transition(pair["before"], pair["after"]) or {}
    assert result.get("verdict") == "ok", result


def test_booster_combos_fire_from_their_first_recoloured_cell():
    l_shape = ms.MatchGroup(frozenset({(3, 0), (4, 0), (5, 0), (6, 0), (4, 1), (5, 1)}), 3, "l")
    five = ms.MatchGroup(frozenset({(0, 0), (0, 1), (0, 2), (0, 3), (0, 4), (1, 0), (1, 1)}), 3, "five")
    order = ms._booster_destroy_order([l_shape, five], ((0, 2), (4, 1), (1, 0)))
    assert order[0] == (0, 2)
    assert order.index((4, 1)) == 7 and order.index((4, 0)) < order.index((5, 0))


def test_exact_scoring_reproduces_the_played_colour_on_the_engine():
    """The bot's own Woolly scoring under woolly_exact_active: the colour it
    played (3) scores best on 224536 008, and the exact result is flagged."""
    from simulator_capture import lab_move
    from strategy_lab.simulation import rules, woolly_exact_simulation
    from tools.analyze_research import capture_from

    pair = json.loads((FIXTURES / "224536_008.json").read_text(encoding="utf-8"))
    lab = lab_move(capture_from(pair["before"]))
    kw = dict(mode=lab["mode"], allow_square_matches=bool(lab["allow_square_matches"]))
    with rules(lab), ms.woolly_exact_active(woolly_exact_simulation(lab["engine_refill"])):
        pick = ms.choose_woolly_workout_target(lab["board"], lab["special_board"], **kw)
    assert pick is not None and pick.target_color == 3
    assert lab["special_board"][pick.target_cell[0]][pick.target_cell[1]] == ms.EMPTY


def test_runtime_falls_back_without_an_exact_session():
    import types
    import runtime

    request = types.SimpleNamespace(late_exact_refill=lambda: None)
    with runtime.woolly_exact_context(request, [[1] * 7] * 7, [[0] * 7] * 7):
        assert ms._WOOLLY_EXACT_SIMULATOR is None
