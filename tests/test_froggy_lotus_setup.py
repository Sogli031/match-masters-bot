"""A standing lotus no move fires: play the move that sets up its collect.

Crazy Columns 2026-11-12 00:16:43-00:16:49 (Debug/runs): the lotus stood at
(1,1) for the last five moves and the bot played plain threes. A lotus fires
only on a match touching it (IsValidFroggyFuLotusSwap -> GetMoveCombosOutcome).
"""
import copy
import json
from pathlib import Path

import move_strategy as ms

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name):
    data = json.loads((FIXTURES / f"froggy_lotus_setup_{name}.json").read_text(encoding="utf-8"))
    context = ms.StrategyContext(**{k: v for k, v in data["strategy_context"].items()
                                    if k in ms.StrategyContext.__dataclass_fields__})
    turn = ms.TurnState(**{k: v for k, v in data["turn_state"].items()
                           if k in ms.TurnState.__dataclass_fields__})
    return data, context, ms.BoosterState(**data["booster_state"]), turn


def _choice(board, data, context, booster, turn):
    ranked = ms.rank_moves(board, data["special_board"], mode=data["mode"], allow_square_matches=True,
                           lookahead_depth=1, strategy_context=context)
    return ranked, ms.froggy_lotus_setup_choice(
        ranked, board, data["special_board"], allow_square_matches=True, mode=data["mode"],
        booster_state=booster, turn_state=turn, strategy_context=context)


def test_move_that_sets_up_the_lotus_beats_a_plain_three():
    data, context, booster, turn = _load("001643")
    board = copy.deepcopy(data["board"])
    board[3][1] = 5  # one piece changed: a swap now leaves a match next to the lotus
    ranked, choice = _choice(board, data, context, booster, turn)
    assert choice is not None
    assert (choice[0].candidate.start, choice[0].candidate.target) == ((3, 2), (3, 3))
    assert (ranked[0].candidate.start, ranked[0].candidate.target) != ((3, 2), (3, 3))
    assert "lotus" in choice[1]


def test_recorded_end_board_had_no_setup_in_visible_pieces():
    data, context, booster, turn = _load("001643")
    assert _choice(data["board"], data, context, booster, turn)[1] is None


def test_no_setup_on_the_last_move_of_the_turn():
    from dataclasses import replace

    data, context, booster, turn = _load("001643")
    board = copy.deepcopy(data["board"])
    board[3][1] = 5
    assert _choice(board, data, context, booster, replace(turn, remaining_moves=1))[1] is None


def test_a_lotus_that_fires_now_is_left_to_the_lotus_gate():
    data, context, booster, turn = _load("001640")
    assert _choice(data["board"], data, context, booster, turn)[1] is None
