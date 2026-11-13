"""A Lightning swapped onto another classic special takes its targets from the engine.

GetMergeSwapOutcome 0x5926284 makes a merged special only for line+line,
bomb+bomb and lightning+lightning (FourthOfJuly 13 -> GetFireworks(24)). A
mixed pair fires each piece's own effect, so a Lightning in it is an ordinary
GetFireworks(12). Both are exact with the engine RNG, and the monitor can then
check the move (Candy World 2026-11-13 14:11:37 was "random target, not ported").
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
    # No three in a row anywhere: (x + 2y) % 6 gives no horizontal or vertical run.
    return [[1 + (x + 2 * y) % 6 for x in range(7)] for y in range(7)]


def swap(start_special, target_special):
    board = board7()
    special = [[0] * 7 for _ in range(7)]
    special[4][4], special[5][4] = start_special, target_special
    return ms.MoveCandidate((4, 4), (5, 4), ms.Direction.DOWN, board, special)


def occupied(board):
    return [(y, x) for x in range(7) for y in range(7) if board[y][x] > 0]


def activations(result, special):
    return [e for e in result.intent_events
            if e.get("type") == "special_activation" and e.get("special") == special]


def test_lightning_with_a_line_is_exact():
    candidate = swap(ms.SPECIAL_HORIZONTAL, ms.SPECIAL_LIGHTNING)
    m = SquareRefill.from_profile(profile(), seed=77)
    with ms.engine_refill_active(fireworks=m.fireworks_targets):
        result = ms._simulate_special_swap_candidate(candidate, max_cascades=1, original_board=candidate.board)
    fired = activations(result, "lightning")
    assert fired and all(e.get("exact_targets") for e in fired)
    effect = [e for e in result.intent_events if e.get("type") == "special_effect" and e["special"] == "lightning"]
    assert effect and all(e["exact_targets"] for e in effect)


def test_two_lightnings_take_24_engine_targets():
    candidate = swap(ms.SPECIAL_LIGHTNING, ms.SPECIAL_LIGHTNING)
    m = SquareRefill.from_profile(profile(), seed=77)
    with ms.engine_refill_active(fireworks=m.fireworks_targets):
        cells = ms._merge_swap_effect_cells(candidate.board, candidate.special_board, candidate,
                                            ms.SPECIAL_LIGHTNING, ms.SPECIAL_LIGHTNING, events := [])
    want = EngineRNG.from_seed(77).shuffled(occupied(candidate.board))[:24]
    assert cells == {(5, 4), *want}
    assert events[-1]["exact_targets"] is True
    assert m.pending_effect_draws == 49


def test_without_the_engine_the_merge_stays_random():
    candidate = swap(ms.SPECIAL_LIGHTNING, ms.SPECIAL_LIGHTNING)
    events = []
    ms._merge_swap_effect_cells(candidate.board, candidate.special_board, candidate,
                                ms.SPECIAL_LIGHTNING, ms.SPECIAL_LIGHTNING, events)
    assert events[-1]["exact_targets"] is False
