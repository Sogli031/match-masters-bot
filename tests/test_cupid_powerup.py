"""Vinnie SE powerup: the pending heart lands at the end of the next swipe.

Two refill misses of 2026-11-14 (Special-o-Rama 21:52:37, Floor is Lava
22:58:52): the board had CupidSEPendingExtraHearts "1,0,100"; the game put
a one-colour heart after the swipe. Both replay exactly now.
"""
import json
from pathlib import Path

import pytest

import engine_cupid_powerup as cp
from engine_rng import EngineRNG

FRAMES = Path(__file__).resolve().parent / "fixtures" / "cupid_pending"


def _record(name):
    return json.loads((FRAMES / f"{name}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", ["sor", "lava"])
def test_pending_heart_replays(name):
    from refill_monitor import check_transition
    verdict = check_transition(_record(f"{name}_000"), _record(f"{name}_001"))
    assert verdict["verdict"] == "ok", verdict


def test_pending_requests_and_chance_list():
    assert cp.pending_requests({cp.PENDING_KEY: "1,0,100"}) == [(1, False, 100)]
    assert cp.pending_requests({cp.PENDING_KEY: "2,1,50|1,0,100"}) == [(2, True, 50), (1, False, 100)]
    assert cp.pending_requests({}) == []
    assert cp.chance_from_list("20,15", 1) == 20 and cp.chance_from_list("20,15", 5) == 15
    assert cp.chance_from_list("20,15", 0) == 20 and cp.chance_from_list("", 1) == 0


def test_select_candidate_draws_one_per_cell_from_two():
    rng = EngineRNG.from_seed(7)
    assert cp.select_candidate(rng, []) is None and rng.counter == 0
    assert cp.select_candidate(rng, [(2, 3)]) == (2, 3) and rng.counter == 0
    cp.select_candidate(rng, [(3, 1), (1, 1), (1, 1), (2, 2)])
    assert rng.counter == 3            # distinct cells only


def test_two_colour_request_is_refused():
    board = [[1] * 5 for _ in range(5)]
    special = [[0] * 5 for _ in range(5)]
    with pytest.raises(cp.UnsupportedCupid):
        cp.place_pending_hearts(board, special, EngineRNG.from_seed(1), {}, [(1, True, 100)], heart=11,
                                matchable=[], extra_move=[], energy=[], can_target=lambda x, y: True)
