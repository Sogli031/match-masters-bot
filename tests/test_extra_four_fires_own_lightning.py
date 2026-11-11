import json
from pathlib import Path

import move_strategy as ms
import runtime
from engine_refill import EngineRefill, ExactRefillSession


# Debug/runs/2026-09-26_19-47-04_273 (Crazy Columns, solo, booster full): the
# yellow three (4,4)<->(4,5) drops a purple four in column 4 whose purple heart
# sets off the lightning at (6,3). The four resolved before the lightning, so
# the extra is real and must hold the ready booster.
BOARD = [
    [1, 6, 5, 1, 5, 1, 4],
    [1, 6, 5, 1, 6, 2, 6],
    [2, 1, 2, 4, 4, 2, 1],
    [4, 2, 5, 1, 4, 5, 4],
    [2, 1, 3, 3, 6, 3, 1],
    [6, 2, 5, 5, 4, 5, 2],
    [3, 6, 3, 4, 4, 6, 6],
]
SPECIALS = [
    [0, 11, 0, 0, 0, 0, 11],
    [0, 0, 0, 0, 0, 0, 11],
    [0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0],
    [0, 4, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 4, 11, 0, 3],
]


def test_four_that_fires_its_own_lightning_keeps_the_extra():
    ranked = ms.rank_moves(
        BOARD,
        SPECIALS,
        mode="Crazy Columns",
        include_future_value=True,
        strategy_context="solo_6",
    )
    move = next(
        item for item in ranked
        if {tuple(item.candidate.start), tuple(item.candidate.target)} == {(4, 4), (4, 5)}
    )
    assert move.extra_moves == 1.0
    assert ms.has_guaranteed_true_extra(move)

    action, chosen, gate = runtime.select_booster_action_with_gate(ranked, True)
    assert action == "move"
    assert gate == "booster_blocked_by_true_extra_gate"
    assert {tuple(chosen.candidate.start), tuple(chosen.candidate.target)} == {(4, 4), (4, 5)}


def test_score_market_exact_drop_finds_yellow_extra_before_ready_booster():
    fixture = Path(__file__).parent / "fixtures" / "solo_extra_before_lightning.json"
    frame = json.loads(fixture.read_text(encoding="utf-8"))
    board, specials = frame["board"], frame["special_board"]
    session = ExactRefillSession(EngineRefill.from_profile(frame["profile"]), board, special_board=specials)
    session.solo = True
    context = ms.StrategyContext("solo_6", solo_challenge=True)
    meter = ms.BoosterState(current=7, maximum=7, source="memory")
    turn = ms.TurnState(remaining_moves=3, source="memory")

    with ms.exact_refill_active(session), ms.mushroom_multipliers_active():
        ranked = ms.rank_moves(board, specials, strategy_context=context, turn_state=turn)
        ranked = ms.prioritize_ranked_moves(
            ranked, booster_state=meter, turn_state=turn, strategy_context=context
        )
        action, chosen, gate = runtime.select_booster_action_with_gate(ranked, True, strategy_context=context)

    assert action == "move"
    assert gate == "booster_blocked_by_true_extra_gate"
    assert {tuple(chosen.candidate.start), tuple(chosen.candidate.target)} == {(4, 2), (5, 2)}
    assert chosen.direct_extra_moves == 0
    assert chosen.extra_moves == 1
    assert ms._move_has_uncertain_cascade(chosen)
