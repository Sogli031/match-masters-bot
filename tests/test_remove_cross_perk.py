"""Remove Cross perk: the target's whole row and column, then the board resolves.

Crystal Cave Showdown (research 20261120_001230 009 -> 010): points 81 and
RNG 1520 -> 1737 exact; the recorded follow_up swipe belongs to the next record.
"""
from pathlib import Path

from tools.replay_one_to_one import replay
from tools.analyze_research import load

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "remove_cross"


def test_remove_cross_replays_exactly():
    rec_a, cap_a = load(FIXTURES / "before.json")
    rec_b, _ = load(FIXTURES / "after.json")
    got = replay(rec_a, cap_a, rec_b)
    assert "skip" not in got, got
    assert got["cells"] == 0 and got["specials"] == 0
    assert got["rng"] == (1737, 1737)
    assert got["points"] == (81, 81)
    assert got["moves"][0] == got["moves"][1]


def test_planner_charges_the_turn_clock_per_action():
    from strategy_lab.planner import _action_seconds

    state = {"action_seconds": {"swap": 3.9, "booster": 8.0}}
    assert _action_seconds(state, {"start": [0, 0], "target": [0, 1]}) == 3.9
    assert _action_seconds(state, {"kind": "booster"}) == 8.0
    assert _action_seconds(state, {"kind": "teleport"}) == 3.9   # unpriced kinds cost a swipe
    assert _action_seconds({}, {"kind": "booster"}) == 0.0       # untimed states: unchanged planner


def test_planned_remove_cross_is_played_on_its_tile():
    """Showdown 2026-11-20 01:26: the live plan never got Remove Cross (width 4
    on record 003: 1049 points without it, 1520 with it and Energy Boost)."""
    from types import SimpleNamespace as NS

    import runtime

    request = NS(engine_plan_perk=runtime.PERK_REMOVE_CROSS, allow_perk_activation=True,
                 selected_perks=[runtime.PERK_ENERGY_BOOST, runtime.PERK_REMOVE_CROSS],
                 engine_plan_move=((3, 1), (3, 1)))
    action = runtime.engine_plan_perk_action(request, [])
    assert action.perk_key == runtime.PERK_REMOVE_CROSS
    assert action.target == (3, 1)
    assert runtime._perk_target_click_points(runtime.PERK_DEFINITIONS[runtime.PERK_REMOVE_CROSS], action.target)
