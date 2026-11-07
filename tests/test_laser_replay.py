"""Exact refill on the recorded Laser Matches game: lotus swipes and the board shuffle."""
from pathlib import Path

import pytest

from engine_refill import EngineRefill, UnsupportedRefill
import engine_shuffle
from tools.analyze_research import load, observed, try_transition

GAME = Path(__file__).resolve().parents[1] / "Debug" / "research" / "20261104_155626_laser-matches"
RED, GREEN, ORANGE, YELLOW = 2, 3, 4, 5


def transition(index):
    first, second = GAME / f"{index:03d}.json", GAME / f"{index + 1:03d}.json"
    if not (first.exists() and second.exists()):
        pytest.skip("recording not available")
    _, capture = load(first)
    return capture, observed(load(second)[0])


@pytest.mark.parametrize("index", [10, 19, 21, 26, 30, 33, 38])
def test_swipe_that_fires_a_lotus_shoots_no_laser(index):
    capture, want = transition(index)
    matches, _, _ = try_transition(capture, want)
    assert matches


def test_teleport_that_fires_a_lotus_shoots_no_laser():
    capture, want = transition(14)
    assert not try_transition(capture, want)[0]
    assert try_transition(capture, want, {3: 1})[0]


def test_swipe_without_a_lotus_keeps_its_laser():
    capture, want = transition(1)
    assert try_transition(capture, want)[0]


def test_move_that_leaves_no_possible_move_shuffles_the_board():
    capture, want = transition(23)     # 7 rounds of 49 draws after the swipe
    assert try_transition(capture, want)[0]


def checkerboard():
    return [[RED if (row + col) % 2 else GREEN for col in range(7)] for row in range(7)]


def test_possible_moves_see_a_match_but_not_a_special_pair():
    board, special = checkerboard(), [[0] * 7 for _ in range(7)]
    assert engine_shuffle.has_possible_move(board, special)
    four_colors = [[(RED, GREEN, ORANGE, YELLOW)[(row * 2 + col) % 4] for col in range(7)] for row in range(7)]
    assert not engine_shuffle.has_possible_move(four_colors, special)


def test_three_holding_a_special_counts_as_a_special_move():
    special = [[0] * 7 for _ in range(7)]
    board = [[(RED, GREEN, ORANGE, YELLOW)[(row * 2 + col) % 4] for col in range(7)] for row in range(7)]
    board[0][:2] = [YELLOW, YELLOW]
    board[0][3] = GREEN     # the pattern's own yellow here would make it a four
    board[1][2] = YELLOW
    assert engine_shuffle.possible_move_counts(board, special)[1] == 0
    special[0][0] = 3
    assert engine_shuffle.possible_move_counts(board, special)[1] == 1


class _Rng:
    """Reverses the pieces, so a round is known without an engine seed."""
    rounds = 0

    def shuffled(self, pieces):
        self.rounds += 1
        return pieces[::-1]


def test_shuffle_needs_the_wanted_range_and_a_movable_board():
    board = [[(RED, GREEN, ORANGE, YELLOW)[(row * 2 + col) % 4] for col in range(7)] for row in range(7)]
    special = [[0] * 7 for _ in range(7)]
    model = EngineRefill.__new__(EngineRefill)
    model.profile = {"config": {}}
    model.rng = _Rng()
    with pytest.raises(UnsupportedRefill):
        engine_shuffle.shuffle_board(model, board, special)
    model.profile = {"config": {"spawnEngine": {
        "wantedPossibleMatchesMin": 4, "wantedPossibleMatchesMax": 8,
        "wantedPossibleSpecialMatchesMin": 1, "wantedPossibleSpecialMatchesMax": 3}}}
    fixed = [row[:] for row in board]
    fixed[3][3] = -1
    with pytest.raises(UnsupportedRefill):
        engine_shuffle.shuffle_board(model, fixed, special)
    assert model.rng.rounds == 0
    # Never in range: gives up after the engine's 100 ranged attempts.
    engine_shuffle.shuffle_board(model, board, special)
    assert model.rng.rounds == engine_shuffle.MAX_RANGED_ATTEMPTS
