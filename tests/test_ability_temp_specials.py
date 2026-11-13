"""AbilityTempSpecial (SlotModel.status & 1): EndTurn turns the leftovers plain.

GameLogic::EndTurn -> ConvertLeftAbilityTempSpecials: a special a booster laid
down for this turn only becomes a plain piece of its colour when the turn
passes, so the opponent never inherits it.
"""
import json
from pathlib import Path

import pytest

import move_strategy as ms

ROOT = Path(__file__).resolve().parents[1]
MISSES = ROOT / "Debug" / "refill_misses"


def _cand(board, special, start, target):
    swapped, swapped_special = ms.swap_cells(board, special, start, target)
    return ms.MoveCandidate(start=start, target=target, direction="up",
                            board=swapped, special_board=swapped_special)


def test_leftover_temporary_special_is_reported_and_reverted():
    board = [[1 + (x + 2 * y) % 6 for x in range(7)] for y in range(7)]
    special = [[0] * 7 for _ in range(7)]
    special[5][5] = ms.SPECIAL_HORIZONTAL
    # Make a three in row 0 by swapping (1,0) up: colours chosen so only it matches.
    board[0][1] = board[0][2] = 3
    board[1][0], board[0][0] = 3, 4
    start, target = (1, 0), (0, 0)
    with ms.ability_temp_specials_active(board, special, [(5, 5)]):
        result = ms.simulate_candidate(_cand(board, special, start, target))
    assert result is not None
    assert result.ability_temp_specials_left == ((5, 5),)
    reverted = ms.revert_ability_temp_specials(result.special_board, result.ability_temp_specials_left)
    assert reverted[5][5] == ms.EMPTY
    # Another board (a simulated one) does not carry the mask.
    other = [row[:] for row in board]
    other[6][6] = 2 if other[6][6] != 2 else 3
    with ms.ability_temp_specials_active(board, special, [(5, 5)]):
        result = ms.simulate_candidate(_cand(other, special, start, target))
    assert result.ability_temp_specials_left == ()


@pytest.mark.parametrize("name", [
    "20261111_181309_117562_multiplier-mushrooms",
    "20261111_181829_090305_multiplier-mushrooms",
])
def test_recorded_turn_end_reverts_the_temporary_special(name):
    folder = MISSES / name
    if not folder.is_dir():
        pytest.skip("recording not on this machine")
    import refill_monitor

    before = json.loads((folder / "000.json").read_text(encoding="utf-8"))
    after = json.loads((folder / "001.json").read_text(encoding="utf-8"))
    assert refill_monitor.check_transition(before, after)["verdict"] == "ok"
