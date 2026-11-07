"""The approximate Cleo model must never establish an exact RNG continuation."""
from copy import deepcopy

import pytest

import move_strategy as ms
from engine_refill import ExactRefillSession, UnsupportedRefill
from engine_rng import EngineRNG
from strategy_lab import simulation


class Model:
    def __init__(self):
        self.profile = {}
        self.rng = EngineRNG.from_seed(72)
        self.billie = None
        self.random_specials = ()

    def clone(self):
        return deepcopy(self)

    def reset_action(self):
        pass

    def peek_draws(self, count):
        rng = self.rng.clone()
        return [rng.next() for _ in range(count)]

    def ball_spent(self, cell):
        pass

    def random_special(self, cell, color):
        return None


def swipe():
    board = [[99, 2, 3, 4], [3, 4, 5, 6], [5, 6, 1, 2], [1, 2, 3, 4]]
    special = [[0] * 4 for _ in board]
    special[0][0] = ms.SPECIAL_CLEO_BUG
    swapped, specials = ms.swap_cells(board, special, (0, 0), (0, 1))
    return board, special, ms.MoveCandidate((0, 0), (0, 1), ms.Direction.RIGHT, swapped, specials)


def test_a_refill_callback_alone_cannot_make_cleo_exact():
    _, _, candidate = swipe()
    with ms.engine_refill_active(lambda b, s, n=0: (b, s)):
        with pytest.raises(UnsupportedRefill, match="clone/merge adapter"):
            ms._simulate_cleo_candidate(candidate, include_future_value=False)
    assert ms._ENGINE_CLEO_SWAP is None


def test_unsupported_cleo_recomputes_the_plain_candidate_without_following_rng():
    board, specials, candidate = swipe()
    plain = ms._simulate_created_candidate(board, candidate, include_future_value=False)
    model = Model()
    before = model.rng.to_capture()
    session = ExactRefillSession(model, board, special_board=specials)
    with ms.exact_refill_active(session):
        result = ms._simulate_created_candidate_cached(
            board, candidate, False, "None", False, False, {}, {})
    assert result is not None and plain is not None
    assert not result.exact_refill_supported
    assert [list(row) for row in result.board] == [list(row) for row in plain.board]
    assert [list(row) for row in result.special_board] == [list(row) for row in plain.special_board]
    assert session.fallbacks == 1 and session.successful == 0 and session.followed == 0
    assert len(session.states) == 1
    assert model.rng.to_capture() == before
    assert "Cleo:" in session.failure
    assert session.begin(board, specials) and not session.line_broken
    assert ms._ENGINE_REFILL is None and ms._ENGINE_CLEO_SWAP is None


@pytest.mark.parametrize("with_model", [False, True])
def test_lab_rejects_unknown_cleo_instead_of_returning_an_average_board(with_model):
    board, specials, _ = swipe()
    model = Model()
    move = {"mode": "None", "board": board, "special_board": specials,
            "turn_state": {"remaining_moves": 3}}
    if with_model:
        move["engine_refill"] = model
    before = model.rng.to_capture()
    result = simulation.step(move, {"start": [0, 0], "target": [0, 1], "direction": "right"})
    assert result["supported"] is False and "Cleo:" in result["reason"]
    assert "state" not in result
    assert move["turn_state"]["remaining_moves"] == 3
    assert model.rng.to_capture() == before


def test_probability_result_cannot_be_saved_as_an_exact_followed_board():
    board, specials, candidate = swipe()
    result = ms._simulate_created_candidate(board, candidate, include_future_value=False)
    assert result.cleo_scenario_count > 0
    session = ExactRefillSession(Model(), board, special_board=specials)
    assert session.begin(board, specials)
    session.finish(result)
    assert result.exact_refill_supported is False
    assert session.successful == 0 and session.followed == 0 and len(session.states) == 1


def test_nested_refill_context_restores_cleo_adapter():
    callback = lambda *a, **k: None
    with ms.engine_refill_active(lambda b, s: (b, s), cleo_swap=callback):
        assert ms._ENGINE_CLEO_SWAP is callback
        with ms.engine_refill_active(None):
            assert ms._ENGINE_CLEO_SWAP is None
        assert ms._ENGINE_CLEO_SWAP is callback
    assert ms._ENGINE_CLEO_SWAP is None


def test_monitor_cannot_count_a_cleo_board_only_fallback_as_a_hit(monkeypatch):
    import refill_monitor

    board, specials, _ = swipe()
    before = {"board": board, "special_board": specials,
              "profile": {"state": {"moves": 3}, "rng": {"<counter>k__BackingField": 10}}}
    after = deepcopy(before)
    after["special_board"][0][0] = 0
    after["profile"]["rng"]["<counter>k__BackingField"] = 11
    after["profile"]["state"]["moves"] = 2

    def forbidden(*a, **k):
        pytest.fail("Cleo must not use the legacy board-only comparison")

    monkeypatch.setattr(refill_monitor, "_try_with_ufo_eyes", forbidden)
    result = refill_monitor.check_transition(before, after)
    assert result["verdict"] == "unsupported"
    assert "missing capture fields" in result["detail"]
