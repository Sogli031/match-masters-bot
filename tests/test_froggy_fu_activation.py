"""Froggy Fu activation in the exact simulator (engine_froggy_placement).

Bombs Away research 20261118_103045 (Solo): every one of the 12 activations
replays with the entrance attempt the game chose, its settle (refill and
cascades), the lotuses, the RNG counter, the moves and the score.
"""
import json
from pathlib import Path

import pytest

FRAMES = Path(__file__).resolve().parent / "fixtures" / "froggy_bombs_away"
# (before, after, the game's entrance attempt, lotus cells (row, col)) -- the
# attempt index is the trace's destroy order matched against the attempts.
ACTIVATIONS = [
    ("002", "003", 1, [[2, 1], [5, 3]]),
    # 263 -> the 300 flag: every attempt scored 37 in the game's clone, the
    # distances tied and the first attempt won.
    ("006", "007", 0, [[5, 3], [1, 1]]),
    ("011", "012", 5, [[1, 2]]),
    ("014", "015", 9, [[1, 3]]),
    ("017", "018", 1, [[1, 2]]),
    ("019", "020", 3, [[3, 1]]),
    ("022", "023", 0, [[2, 3]]),
    ("027", "028", 4, [[3, 1]]),
    ("029", "030", 5, [[5, 3]]),
    ("031", "032", 8, [[5, 2]]),
    ("037", "038", 6, [[3, 3]]),
    ("039", "040", 3, [[4, 1]]),
]


def _record(name):
    return json.loads((FRAMES / f"{name}.json").read_text(encoding="utf-8"))


def _lab(name):
    from simulator_capture import lab_move
    from tools.analyze_research import capture_from
    lab = lab_move(capture_from(_record(name)), thresholds=None)
    lab["perks"] = {}
    return lab


@pytest.mark.parametrize("before, after, attempt, lotuses", ACTIVATIONS)
def test_activation_replays_exactly(before, after, attempt, lotuses):
    from strategy_lab import simulation as sim
    from tools.analyze_research import grid, observed
    lab = _lab(before)
    result = sim.step(lab, {"kind": "booster"})
    assert result["supported"], result.get("reason")
    state, want, nxt = result["state"], observed(_record(after)), _lab(after)
    assert grid(state["board"]) == want["board"]
    assert grid(state["special_board"]) == want["special_board"]
    assert state["engine_refill"].rng.counter == want["rng"]
    entrance = next(e for e in result["events"] if e["type"] == "froggy_entrance")
    placed = next(e for e in result["events"] if e["type"] == "froggy_lotus_placed")
    assert entrance["attempt"] == attempt
    assert placed["cells"] == lotuses
    # The booster costs no move and scores like the game (Solo flag included).
    assert state["turn_state"]["remaining_moves"] == nxt["turn_state"]["remaining_moves"]
    assert state["score"] == nxt["score"]
    assert state["booster_state"]["current"] == 0
    assert state["foxy_activations"] == lab["engine_refill"].profile["cleo_activates_this_turn"] + 1


def test_the_entrance_trace_is_the_winning_attempt():
    """The fixture's trace is what the test's attempt index stands for."""
    from engine_froggy import preview_entrance
    for before, after, attempt, _ in ACTIVATIONS:
        record = _record(before)
        trace = next(t for t in _record(after)["swap_traces"] if t.get("kind") == "booster")
        preview = preview_entrance(record["profile"], record["raw_slots"],
                                   activation=ACTIVATIONS.index((before, after, attempt, _)) + 1,
                                   preferred_color_fix=True)
        assert [[c, r] for r, c in preview.attempts[attempt]] == trace["events"][0]["positions"]
        assert preview.rng_after.counter == trace["events"][0]["rng_before"]


def test_a_lotus_left_on_the_board_is_not_ported():
    from strategy_lab import simulation as sim
    lab = _lab("002")
    lab["board"][0][0], lab["special_board"][0][0] = -1, 20
    result = sim.step(lab, {"kind": "booster"})
    assert not result["supported"] and "lotus" in result["reason"]


def test_planner_supports_froggy_fu():
    import move_strategy as ms
    import square_solo_live as sl
    state = {"rules": {"pvp_mode": 1, "id": "bombs-away"},
             "players": [{"player_type": 0, "special_ability_type": 63}]}
    assert sl.planner_support(state, ms.GameMode.NONE.value) is None
    assert sl.charles_policy_booster(state)


def test_compare_attempts_order():
    import engine_froggy_placement as fp
    base = dict(targets=[], positions=[])
    a = fp.AttemptEvaluation(1, placed=2, match_adjacent=2, separation_deficit=1, score_distance=3, **base)
    b = fp.AttemptEvaluation(2, placed=2, match_adjacent=2, separation_deficit=0, score_distance=9, **base)
    # A smaller separation deficit wins before the score distance.
    assert fp.compare_attempts(b, a, False, False, True, True) > 0
    c = fp.AttemptEvaluation(3, placed=2, match_adjacent=2, separation_deficit=0, score_distance=9, **base)
    # A full tie keeps the earlier attempt.
    assert fp.compare_attempts(c, b, False, False, True, True) < 1
    assert fp.separation_deficit([(0, 0), (1, 1), (4, 4)], 5) == 3 + 0 + 0
