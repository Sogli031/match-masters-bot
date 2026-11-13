"""Lightning targets from BoardModel.GetFireworks 0x597204c (engine RNG).

GetSlotPrioritize's priority list (canBeMatched and damageable) does not read
the ignore list: every occupied piece, cells already being destroyed included,
is shuffled with one draw each and the first ``amount`` taken.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import move_strategy as ms
from engine_refill import SquareRefill
from engine_rng import EngineRNG
from tests.test_engine_refill import profile


def board7():
    return [[1 + (x + 2 * y) % 6 for x in range(7)] for y in range(7)]


def occupied(board):
    return [(y, x) for x in range(7) for y in range(7)
            if board[y][x] > 0 and board[y][x] not in ms.NON_MATCHABLE_PIECES]


def test_ignore_list_does_not_shrink_the_priority_list():
    board = board7()
    board[0][0] = ms.EMPTY
    board[2][3] = ms.DISCO_BALL
    ignore = {(3, 3), (3, 4), (3, 5)}
    m = SquareRefill.from_profile(profile(), seed=555)
    picks = m.fireworks_targets(board, ignore, 12)
    want = EngineRNG.from_seed(555).shuffled(occupied(board))[:12]
    assert picks == want
    assert m.pending_effect_draws == 47
    assert m.fireworks_targets(board, None, 12) != []   # the ignore list never matters here


def test_short_priority_list_is_taken_whole_without_draws():
    board = [[ms.EMPTY] * 7 for _ in range(7)]
    board[1][1], board[5][2] = 3, 4
    m = SquareRefill.from_profile(profile(), seed=1)
    assert m.fireworks_targets(board, set(), 12) == [(1, 1), (5, 2)]
    assert m.pending_effect_draws == 0


def test_lightning_is_exact_whenever_the_engine_hook_is_active():
    board = board7()
    m = SquareRefill.from_profile(profile(), seed=555)
    with ms.engine_refill_active(fireworks=m.fireworks_targets):
        assert ms._lightning_targets_exact()
        cells = ms._lightning_effect_cells(board, 3, 3, excluded_cells={(3, 4)})
    want = EngineRNG.from_seed(555).shuffled(occupied(board))[:12]
    assert cells == {(3, 3), *want}
