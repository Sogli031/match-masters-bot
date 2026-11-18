"""The powerup ("boosted") Foxy Roxy SE: FoxyRoxySEPowerUpVariant1 patterns,
cans and L sprays (engine_foxy_powerup). Bombs Away research 20261118_091058
replays whole (47 of 47 moves); these are its first activation and spray."""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/foxy_powerup"


def _transition(before, after, describe):
    from simulator_capture import capture_mode, lab_move
    from strategy_lab import planner, simulation
    from tools.analyze_research import grid, load, observed

    record, capture = load(FIXTURE / before)
    want = observed(load(FIXTURE / after)[0])
    certified = simulation.PREFIX_MODES
    simulation.PREFIX_MODES = set(certified) | {capture_mode(capture["profile"]).value}
    try:
        lab = lab_move(capture)
        lab["perks"] = {}
        actions = [a for a in planner.actions(lab) if describe(planner.describe(a))]
        if describe("BOOSTER"):
            cost = (lab.get("booster_state") or {}).get("maximum") or 7
            lab["booster_state"] = {"current": cost, "maximum": cost}
            actions = [{"kind": "booster"}]
        assert actions
        for action in actions:
            result = simulation.step(lab, action)
            if not result.get("supported"):
                continue
            state = result["state"]
            if (grid(state["board"]) == want["board"] and grid(state["special_board"]) == want["special_board"]
                    and state["engine_refill"].rng.counter == want["rng"]):
                return lab, action
        return lab, None
    finally:
        simulation.PREFIX_MODES = certified


def test_the_boosted_foxy_is_recognised():
    import json

    import engine_foxy

    record = json.loads((FIXTURE / "002.json").read_text(encoding="utf-8"))
    local = next(p for p in record["snapshot_state"]["players"] if p.get("player_type") == 0)
    assert engine_foxy.is_powerup_variant(local["special_ability_params"], record["profile"])
    assert not engine_foxy.is_powerup_variant({"piecesPerActivation": "2,1"}, {})


def test_boosted_activation_replays_exactly():
    """002 -> 003: the plain paint draws, the variant's AlternatingRows/Turn90/
    Rectangle patterns replace it, its cans go where TryChooseSprayPositions
    ranks best (board, specials and RNG exact)."""
    from strategy_lab.simulation import plan_refusal

    lab, action = _transition("002.json", "003.json", lambda text: text.startswith("BOOSTER"))
    assert action is not None
    assert plan_refusal(lab) is None



def test_rectangle_second_half_takes_the_far_corner_colour():
    """Bombs Away research 20261118_122847 001 -> 002 (the match's first
    activation): the RectangleTwoColors' second half took the colour of the
    square's far corner (2), not of its own first cell (4, then a pick of 5
    that joined a bomb's row and missed the whole activation)."""
    _, action = _transition("rect_001.json", "rect_002.json", lambda text: text.startswith("BOOSTER"))
    assert action is not None

def test_boosted_spray_paints_an_l():
    """003 -> 004: the can's swipe paints to the edge, then the whole edge
    line (the five the old long-ray rule refused replays exactly)."""
    _, action = _transition("003.json", "004.json", lambda text: text.startswith("SPREJ"))
    assert action is not None and action["start"] == action["target"]


def test_spray_path_is_an_l_shorter_arm_first():
    import engine_foxy_powerup as fp

    bounds = fp._Bounds(7)
    # From (x=2, y=1) up: (2,1) (2,0), then the top row, the left arm (2
    # cells) before the right one (4 cells).
    path = fp.spray_path(bounds, (2, 1), (0, -1))
    assert path == [(2, 1), (2, 0), (1, 0), (0, 0), (3, 0), (4, 0), (5, 0), (6, 0)]
    assert fp.spray_path(bounds, (2, 1), (1, 1)) == []


@pytest.mark.parametrize("step, across", [(1, True), (2, True), (3, False), (4, False), (5, True), (6, True)])
def test_staircase_alternates_two_and_two(step, across):
    """Bombs Away 09:12:19: (0,5) (1,5) (2,5) (2,4) (2,3) (3,3) (4,3)."""
    assert (((step - 1) >> 1) & 1 == 0) is across
