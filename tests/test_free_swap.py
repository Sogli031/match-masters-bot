import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import free_swap as fs
from free_swap import FreeSwapGuard, apply_swap, free_swaps_active, plan_free_swaps
from refill_monitor import _free_swap_between


def _no_match(rows, square=True):
    return not any(fs._match_cells_at(rows, r, c, square)
                   for r in range(len(rows)) for c in range(len(rows[0])))


def _stable(seed, n=7, colors=6):
    rnd = random.Random(seed)
    while True:
        board = [[rnd.randint(1, colors) for _ in range(n)] for _ in range(n)]
        if _no_match(board):
            return board


def test_flags_from_engine_fields():
    rules = {"engine_fields": {"anySwapValid": True, "reduceMoveOnMatchOnly": True}}
    assert free_swaps_active(rules)
    assert not free_swaps_active({"engine_fields": {"anySwapValid": True, "reduceMoveOnMatchOnly": False}})
    assert not free_swaps_active({"engine_fields": {"anySwapValid": False, "reduceMoveOnMatchOnly": True}})
    assert not free_swaps_active({})


def test_plan_swaps_never_match_and_end_in_a_better_move():
    values = {1: 1, 2: 2, 3: 5, 4: 4, 5: 1, 6: 3}
    for seed in range(4):
        board = _stable(seed)
        plan = plan_free_swaps(board, None, allow_square_matches=True, color_values=values,
                               time_budget=1.0)
        assert plan.swaps, seed
        rows = board
        for swap in plan.swaps:
            rows = apply_swap(rows, swap)
            assert _no_match(rows), (seed, swap)
        _, cells_a, _, cells_b = fs._try_pair(rows, *plan.final_move, True)
        assert cells_a or cells_b
        assert plan.value > plan.baseline


def test_looks_past_worthless_boards_to_build_a_five():
    # Yellow (3) is worth 5, everything else 1. Yellow tiles are spread out:
    # no single swap gives anything good, a five needs several free swaps.
    board = [
        [3, 1, 2, 4, 1, 2, 3],
        [1, 2, 4, 1, 2, 4, 1],
        [2, 4, 1, 2, 4, 1, 2],
        [3, 1, 2, 4, 1, 2, 3],
        [1, 2, 4, 1, 2, 4, 1],
        [2, 4, 1, 2, 4, 1, 2],
        [4, 3, 6, 5, 6, 5, 6],
    ]
    assert _no_match(board)
    plan = plan_free_swaps(board, None, allow_square_matches=True,
                           color_values={1: 1, 2: 1, 3: 5, 4: 1, 5: 1, 6: 1}, time_budget=2.0)
    rows = board
    for swap in plan.swaps:
        rows = apply_swap(rows, swap)
    color_a, cells_a, color_b, cells_b = fs._try_pair(rows, *plan.final_move, True)
    # Nothing matches now (baseline 0); the plan walks through boards that
    # still match nothing and ends in a five (here five + four in one swap).
    assert plan.baseline == 0
    assert len(plan.swaps) >= 2
    kinds = {fs.classify_cells(cells) for cells in (cells_a, cells_b) if cells}
    assert "five" in kinds


def test_specials_are_never_moved():
    board = _stable(7)
    special = [[0] * 7 for _ in range(7)]
    special[3][3] = 1
    plan = plan_free_swaps(board, special, allow_square_matches=True, time_budget=0.5)
    for a, b in plan.swaps:
        assert (3, 3) not in (tuple(a), tuple(b))


def test_guard_follows_plan_and_stops_on_refusal():
    board = _stable(1)
    plan = plan_free_swaps(board, None, allow_square_matches=True, time_budget=0.5)
    guard = FreeSwapGuard()
    assert guard.observe(board, 10, 1) is None
    guard.keep(board, plan)
    first = guard.next_swap(board)
    assert first == plan.swaps[0]
    guard.played(board, 10, first)
    after = apply_swap(board, first)
    assert guard.observe(after, 10, 1) is None
    if len(plan.swaps) > 1:
        assert guard.next_swap(after) == plan.swaps[1]
    # The game refused the swap: the board did not change.
    guard.played(after, 10, guard.next_swap(after) or first)
    assert guard.observe(after, 10, 1)
    assert guard.allowed() == 0


def test_guard_stops_when_a_free_swap_spends_a_move():
    board = _stable(2)
    guard = FreeSwapGuard()
    guard.observe(board, 10, 1)
    guard.played(board, 10, ((0, 0), (0, 1)))
    assert guard.observe(apply_swap(board, ((0, 0), (0, 1))), 9, 1)


def test_refill_monitor_accepts_a_free_swap():
    board = _stable(3)
    special = [[0] * 7 for _ in range(7)]
    rng = {"rng": {"<counter>k__BackingField": 55}}
    a = {"board": board, "special_board": special, "profile": rng}
    b = {"board": apply_swap(board, ((2, 2), (2, 3))), "special_board": special, "profile": rng}
    assert _free_swap_between(a, b)
    c = {"board": apply_swap(board, ((2, 2), (4, 4))), "special_board": special, "profile": rng}
    assert not _free_swap_between(a, c)


def test_affordable_swaps_follow_the_clock():
    assert fs.affordable_free_swaps(None, 5, None) == fs.MAX_DEPTH
    assert fs.affordable_free_swaps(10.0, 2, 6.5) == 0
    assert fs.affordable_free_swaps(30.0, 2, 6.5) > 0


def test_swap_freely_is_not_infinite_moves():
    from memory_gui import MemoryWindow

    rules = {"engine_fields": {"reduceMoveOnValidSwap": False, "reduceMoveOnMatchOnly": True,
                               "anySwapValid": True}}
    assert not MemoryWindow._unlimited_moves(rules)
    assert MemoryWindow._unlimited_moves({"engine_fields": {"reduceMoveOnValidSwap": False}})
