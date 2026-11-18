"""Foxy Roxy SE activation and its exact plan (engine_foxy).

Color Climb research 20261117_155242 (Solo): every activation of that game
replays with board, specials, cans and RNG counter; the scores of the
booster and of the sprays match the game's.
"""
import json
from pathlib import Path

import pytest

FRAMES = Path(__file__).resolve().parent / "fixtures" / "spray_color_climb"


def _lab(name):
    from simulator_capture import lab_move
    from tools.analyze_research import capture_from
    record = json.loads((FRAMES / f"{name}.json").read_text(encoding="utf-8"))
    lab = lab_move(capture_from(record), thresholds=None)
    lab["perks"] = {}
    return lab


def _want(name):
    from tools.analyze_research import observed
    return observed(json.loads((FRAMES / f"{name}.json").read_text(encoding="utf-8")))


@pytest.mark.parametrize("before, after, cans", [
    # First activation of the turn: two cans; two painted rows join a green
    # column into one blob whose Lightning sits on its first x-major cell.
    ("004", "005", [[0, 1], [6, 3]]),
    ("007", "008", [[6, 6]]),
    # 433 draws: long cascades after the paint.
    ("022", "023", [[5, 5]]),
])
def test_activation_replays_exactly(before, after, cans):
    from strategy_lab import simulation as sim
    from tools.analyze_research import grid
    lab = _lab(before)
    lab["booster_state"] = {"current": 7, "maximum": 7}
    result = sim.step(lab, {"kind": "booster"})
    assert result["supported"], result.get("reason")
    want, state = _want(after), result["state"]
    assert grid(state["board"]) == want["board"]
    assert grid(state["special_board"]) == want["special_board"]
    assert state["engine_refill"].rng.counter == want["rng"]
    placed = [e for e in result["events"] if e.get("type") == "foxy_spray_cans"]
    assert placed and placed[0]["cells"] == cans
    # The booster costs no move, empties the meter and scores like the game
    # (no Color Climb multiplier raise for its combos).
    nxt = _lab(after)
    assert state["turn_state"]["remaining_moves"] == nxt["turn_state"]["remaining_moves"]
    assert state["booster_state"]["current"] == 0
    assert state["score"] == nxt["score"]
    assert state["score_multiplier"] == nxt["score_multiplier"]
    assert state["foxy_activations"] == lab["engine_refill"].profile["cleo_activates_this_turn"] + 1


@pytest.mark.parametrize("before, after, cell, direction, kind", [
    ("005", "006", (6, 3), "up", "energy_boost"),
    ("008", "009", (6, 6), "left", "swap"),
    ("011", "012", (1, 2), "right", "swap"),
    ("019", "020", (0, 3), "down", "swap"),
    ("027", "028", (4, 0), "right", "swap"),
])
def test_spray_scores_its_can(before, after, cell, direction, kind):
    """The can scores one piece at the swipe cascade's multiplier."""
    from strategy_lab import simulation as sim
    lab = _lab(before)
    lab["perks"] = {22: 1}
    result = sim.step(lab, {"kind": kind, "start": list(cell), "target": list(cell), "direction": direction})
    assert result["supported"], result.get("reason")
    nxt = _lab(after)
    assert result["state"]["score"] == nxt["score"]
    assert result["state"]["turn_state"]["remaining_moves"] == nxt["turn_state"]["remaining_moves"]
    assert result["state"]["booster_state"]["current"] == nxt["booster_state"]["current"]


def test_dotnet_dictionary_reuses_the_last_freed_slot():
    import engine_foxy
    d = engine_foxy.NetDictionary()
    a, b, c = ["a"], ["b"], ["c"]
    for key, value in ((1, a), (2, a), (3, b), (4, c)):
        d.set(key, value)
    d.remove(1)
    d.remove(3)
    d.set(5, c)     # takes slot 2 (freed last), then slot 0
    d.set(6, b)
    assert d.distinct_values() == [b, a, c]


def test_params_from_the_live_snapshot_match_the_recorded_fields():
    import engine_foxy
    record = json.loads((FRAMES / "004.json").read_text(encoding="utf-8"))
    params = next(p for p in record["snapshot_state"]["players"] if p.get("player_type") == 0)
    assert (engine_foxy.config_from_profile({}, params["special_ability_params"])
            == engine_foxy.config_from_profile(record["profile"]))


def test_foxy_plays_the_exact_plan_with_charles_policy():
    import square_solo_live as sl
    foxy = {"rules": {"pvp_mode": 1}, "players": [{"player_type": 0, "special_ability_type": 52}]}
    assert sl.charles_eligible(foxy)
    assert sl.charles_policy_booster(foxy)
    assert not sl.charles_policy_booster({"rules": {"pvp_mode": 1},
                                          "players": [{"player_type": 0, "special_ability_type": 35}]})


def test_planner_fires_the_booster_and_plans_sprays():
    from strategy_lab import planner
    lab = _lab("004")
    lab["booster_state"] = {"current": 7, "maximum": 7}
    lab["booster_auto"] = True
    best, _ = planner.plan(lab, width=1, max_steps=4)
    assert best.actions[0] == {"kind": "booster"}
    assert best.score > lab["score"]


def test_planned_spray_keeps_its_direction():
    import types
    import move_strategy as ms
    import runtime

    board = [[1] * 7 for _ in range(7)]
    special = [[0] * 7 for _ in range(7)]
    cand = ms.MoveCandidate((2, 3), (2, 3), ms.Direction("left"), board, special)
    other = types.SimpleNamespace(candidate=ms.MoveCandidate((0, 0), (0, 1), ms.Direction("right"), board, special))
    spray = types.SimpleNamespace(candidate=cand)
    ordered = runtime.promote_engine_plan_move([other, spray], ((2, 3), (2, 3), "right"))
    assert ordered[0] is spray
    played = ms.oriented_swap_candidate(spray)
    assert ms.Direction(played.direction) == ms.Direction.RIGHT
    # Not the planned direction and not its flip: the ranking stays.
    assert runtime.promote_engine_plan_move([other, spray], ((2, 3), (2, 3), "up"))[0] is other


def test_spray_passes_another_can_by():
    """research 20261117_200600 005->006: the ray from (0, 0) to the right
    left the can on (0, 4) as it was and painted (0, 5) and (0, 6) on."""
    from strategy_lab import simulation as sim
    from tools.analyze_research import grid
    lab = _lab("b005")
    result = sim.step(lab, {"kind": "swap", "start": [0, 0], "target": [0, 0], "direction": "right"})
    assert result["supported"], result.get("reason")
    want, state = _want("b006"), result["state"]
    assert grid(state["board"]) == want["board"]
    assert grid(state["special_board"]) == want["special_board"]
    assert state["engine_refill"].rng.counter == want["rng"]
    assert state["score"] == _lab("b006")["score"]


TWO_CANS = Path(__file__).resolve().parent / "fixtures" / "spray_two_cans"


@pytest.mark.parametrize("before, after, cell, direction", [
    ("184", "185", (6, 5), "up"),
    ("243", "244", (6, 1), "right"),
])
def test_spray_with_a_can_above_keeps_that_cans_colour(before, after, cell, direction):
    """Color Climb research 20261117_231127 (4 misses in 246 moves): the
    sprayed can is used up and the can above falls onto its cell with its own
    colour; the simulator gave it the spent can's and the refill after it
    missed. The spray now reports the spent can (EngineRefill.ball_spent)."""
    from simulator_capture import lab_move
    from strategy_lab import simulation as sim
    from tools.analyze_research import capture_from, grid, observed

    record = json.loads((TWO_CANS / f"{before}.json").read_text(encoding="utf-8"))
    lab = lab_move(capture_from(record), thresholds=None)
    result = sim.step(lab, {"start": list(cell), "target": list(cell), "direction": direction})
    assert result["supported"], result.get("reason")
    want = observed(json.loads((TWO_CANS / f"{after}.json").read_text(encoding="utf-8")))
    state = result["state"]
    assert grid(state["board"]) == want["board"]
    assert grid(state["special_board"]) == want["special_board"]
    assert state["engine_refill"].rng.counter == want["rng"]
    nxt = json.loads((TWO_CANS / f"{after}.json").read_text(encoding="utf-8"))
    cans = sorted((s["row"], s["col"], s["color"]) for s in nxt["raw_slots"] if s.get("value") == 31)
    assert sorted(state["engine_refill"].balls) == cans


CRYSTAL = Path(__file__).resolve().parent / "fixtures" / "foxy_crystal_cave"


def test_activation_in_crystal_cave_explodes_the_new_specials_at_once():
    """Crystal Cave research 20261118_014743 (specialsAutoExplode): the Foxy
    paint made a five and two fours, and their specials went off at once
    (fireworks, two columns). The booster's matches now get the mode's
    explode rule as swaps do; before, all 8 activations of the game missed
    (RNG 677 instead of 894 here) and each lost the carried plan."""
    from simulator_capture import lab_move
    from strategy_lab import simulation as sim
    from tools.analyze_research import capture_from, grid, observed

    record = json.loads((CRYSTAL / "004.json").read_text(encoding="utf-8"))
    lab = lab_move(capture_from(record), thresholds=None)
    lab["perks"] = {}
    lab["booster_state"] = {"current": 7, "maximum": 7}
    assert lab["specials_explode_immediately"]
    result = sim.step(lab, {"kind": "booster"})
    assert result["supported"], result.get("reason")
    want = observed(json.loads((CRYSTAL / "005.json").read_text(encoding="utf-8")))
    state = result["state"]
    assert state["engine_refill"].rng.counter == want["rng"] == 894
    assert grid(state["board"]) == want["board"]
    assert grid(state["special_board"]) == want["special_board"]
