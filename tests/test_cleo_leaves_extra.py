"""The faster Cleo extra check answers exactly what the plain definition does."""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import move_strategy as ms  # noqa: E402
from engine_refill import _board_key  # noqa: E402
from engine_rng import EngineRNG  # noqa: E402


def plain_definition(board, special, square):
    for candidate in ms.generate_candidates(board, special):
        through = [
            match
            for match in ms.find_matches(candidate.board, square, candidate.special_board)
            if candidate.start in match.cells or candidate.target in match.cells
        ]
        if ms._count_extra_move_matches(through):
            return True
    return False


def random_board(rng, colors):
    return [[rng.randint(1, colors) for _ in range(7)] for _ in range(7)]


def settled_board(rng, colors):
    while True:
        board = random_board(rng, colors)
        for _ in range(60):
            matches = ms.find_matches(board)
            if not matches:
                return board
            for match in matches:
                for row, col in match.cells:
                    board[row][col] = rng.randint(1, colors)


def test_settled_boards_both_ways():
    rng = random.Random(5)
    answers = set()
    for index in range(1500):
        board = settled_board(rng, rng.choice([4, 5, 6, 6, 6]))
        special = [[0] * 7 for _ in range(7)]
        if index % 3 == 0:
            for _ in range(3):
                special[rng.randrange(7)][rng.randrange(7)] = rng.choice(
                    [ms.SPECIAL_BOMB, ms.SPECIAL_CLEO_BUG, ms.SPECIAL_HORIZONTAL])
        if index % 5 == 0:
            board[rng.randrange(7)][rng.randrange(7)] = rng.choice(
                [ms.EMPTY, ms.BLOCKED, ms.DISCO_BALL, ms.CHEST])
        answer = ms._cleo_leaves_extra(board, special, False)
        assert answer == plain_definition(board, special, False), (board, special)
        answers.add(answer)
    assert answers == {True, False}


def test_boards_that_already_hold_a_match_and_the_slow_rules():
    rng = random.Random(6)
    for index in range(800):
        board = random_board(rng, rng.choice([3, 4, 5, 6]))
        special = [[0] * 7 for _ in range(7)]
        if index % 4 == 0:
            special[rng.randrange(7)][rng.randrange(7)] = rng.choice([
                ms.SPECIAL_SPRAY_SE, ms.SPECIAL_SWEEP_SE_BROOM,
                ms.SPECIAL_RED_BLUE_TILE, ms.SPECIAL_FROGGY_LOTUS])
        square = index % 7 == 0
        assert ms._cleo_leaves_extra(board, special, square) == plain_definition(board, special, square)


def test_three_chests_are_not_a_line():
    board = settled_board(random.Random(7), 6)
    for col in range(4):
        board[0][col] = ms.CHEST
    board[1][4] = ms.CHEST
    special = [[0] * 7 for _ in range(7)]
    assert ms._cleo_leaves_extra(board, special, False) == plain_definition(board, special, False)


def _ranking(board, special):
    random.seed(1)  # Lightning and the like draw their targets.
    results =ms._rank_candidate_results(board, special, "None", False, None, False, {})
    return [(item.candidate.start, item.candidate.target, item.score) for item, _result in results]


def test_skipping_plain_swaps_without_a_line_keeps_the_same_ranking(monkeypatch):
    rng = random.Random(8)
    full = ms.generate_candidates
    for index in range(150):
        board = settled_board(rng, rng.choice([4, 5, 6]))
        special = [[0] * 7 for _ in range(7)]
        for _ in range(index % 5):
            special[rng.randrange(7)][rng.randrange(7)] = rng.choice([
                ms.SPECIAL_BOMB, ms.SPECIAL_CLEO_BUG, ms.SPECIAL_HORIZONTAL, ms.SPECIAL_DISCO_BALL,
                ms.SPECIAL_FROGGY_LOTUS, ms.SPECIAL_XTRA_MOVE_TILE])
        if index % 4 == 0:
            board[rng.randrange(7)][rng.randrange(7)] = rng.choice([ms.BLOCKED, ms.CHEST])
        skipping = _ranking(board, special)
        with monkeypatch.context() as patch:
            patch.setattr(ms, "generate_candidates", lambda b, s, _skip=False: full(b, s))
            assert skipping == _ranking(board, special)


def test_rng_clone_keeps_its_state_and_its_own_matrix():
    rng = EngineRNG.from_seed(12345, counter=7)
    clone = rng.clone()
    assert type(clone) is EngineRNG
    assert (clone.matrix, clone.index, clone.seed, clone.counter) == (
        rng.matrix, rng.index, rng.seed, rng.counter)
    assert clone.matrix is not rng.matrix
    draws = [clone.next() for _ in range(700)]
    assert rng.counter == 7
    assert [rng.next() for _ in range(700)] == draws


def test_board_key_is_plain_ints_whatever_the_grid_type():
    import numpy as np

    expected = ((1, 2), (3, 4))
    assert _board_key([[1, 2], [3, 4]]) == expected
    assert _board_key(np.array([[1, 2], [3, 4]])) == expected
    assert all(type(value) is int for row in _board_key(np.array([[1, 2]])) for value in row)
