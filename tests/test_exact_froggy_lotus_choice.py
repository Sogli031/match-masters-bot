"""Lotus collects ranked with the exact drop (exact_froggy_lotus_choice).

refill_misses 20261111_142124 (Mutation Lab): the played lotus collect
(5,3)->(4,3) replays exactly on the engine refill, board and RNG.
"""
import json
from pathlib import Path

import move_strategy as ms
from engine_refill import ExactRefillSession
from simulator_capture import lab_move
from tools.analyze_research import capture_from

FIXTURES = Path(__file__).parent / "fixtures" / "lotus_exact_mutation_lab"


def _setup():
    before = json.loads((FIXTURES / "000.json").read_text(encoding="utf-8"))
    after = json.loads((FIXTURES / "001.json").read_text(encoding="utf-8"))
    lab = lab_move(capture_from(before))
    board, special = lab["board"], lab["special_board"]
    session = ExactRefillSession(lab["engine_refill"], board, special_board=special)
    ranked = ms.rank_moves(board, special, lookahead_depth=1, allow_square_matches=True)
    return board, special, session, ms.rank_froggy_lotus_moves(ranked, board, special), after


def test_played_lotus_collect_replays_exactly_on_the_refill():
    import refill_monitor as rm

    before = json.loads((FIXTURES / "000.json").read_text(encoding="utf-8"))
    after = json.loads((FIXTURES / "001.json").read_text(encoding="utf-8"))
    assert after["refill_input"][2]["start"] == [5, 3]
    assert rm.check_transition(before, after)["verdict"] == "ok"


def test_lotus_choice_uses_the_session():
    board, special, session, lotus, _ = _setup()
    assert ms.exact_froggy_lotus_choice(lotus, board, special, allow_square_matches=True) is None
    with ms.exact_refill_active(session):
        pick = ms.exact_froggy_lotus_choice(lotus, board, special, allow_square_matches=True)
    assert pick is not None and pick[1] == "lotus sa tacnom dopunom"
    assert pick[0].froggy_lotus_collected > 0
