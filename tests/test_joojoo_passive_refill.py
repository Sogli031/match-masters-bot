"""Monkey JooJoo booster skulls: the refill and the skulls that come back after a move.

Hot Color research 20261112_001019 (booster 40, Solo): the skull count only grows
with a throw; after every move EndMoveWithPassiveAbility -> ChoosePositions tops
it back up on pieces already on the board. 9 of 9 played moves exact (board,
skull cells, RNG; Hot Color's +2 follows).
"""
import copy
import json
from pathlib import Path

import refill_monitor as rm
from engine_refill import ExactRefillSession, EngineRefill, joojoo_passive
from simulator_capture import capture_mode, lab_move
from strategy_lab import planner, simulation
from tools.analyze_research import capture_from

FIXTURES = Path(__file__).parent / "fixtures" / "joojoo_hot_color"


def _load(name):
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def test_monkey_joojoo_booster_is_recognised():
    assert joojoo_passive(_load("004")["profile"])
    assert not joojoo_passive({"players": [{"player_type": 0, "model": {"specialAbilityType": 7}}]})
    assert not joojoo_passive(None)


def test_board_with_booster_skulls_is_simulated(monkeypatch):
    record = _load("004")
    capture = capture_from(record)
    monkeypatch.setattr(simulation, "PREFIX_MODES",
                        set(simulation.PREFIX_MODES) | {capture_mode(capture["profile"]).value})
    lab = lab_move(capture)
    action = next(a for a in planner.actions(lab) if a.get("kind", "swap") == "swap"
                  and {tuple(a["start"]), tuple(a["target"])} == {(3, 1), (3, 2)})
    result = simulation.step(lab, action)
    assert result["supported"], result.get("reason")


def _played(before, after, monkeypatch):
    capture = capture_from(before)
    monkeypatch.setattr(simulation, "PREFIX_MODES",
                        set(simulation.PREFIX_MODES) | {capture_mode(capture["profile"]).value})
    lab = lab_move(capture)
    move = after["refill_input"][2]
    action = next(a for a in planner.actions(lab) if a.get("kind", "swap") == "swap"
                  and (list(a["start"]), list(a["target"])) == (move["start"], move["target"]))
    return simulation.step(lab, action)


def test_exploded_skulls_come_back_on_the_recorded_cells(monkeypatch):
    # 004->005: all 7 skulls explode; 7 come back, 39 draws, then Hot Color's 2.
    before, after = _load("004"), _load("005")
    result = _played(before, after, monkeypatch)
    state = result["state"]
    assert [list(map(int, r)) for r in state["board"]] == after["board"]
    assert [list(map(int, r)) for r in state["special_board"]] == after["special_board"]
    assert state["engine_refill"].rng.counter + 2 == after["profile"]["rng"]["<counter>k__BackingField"]


def test_check_reports_exact_board_and_skulls():
    move = rm.check_transition(_load("004"), _load("005"))
    assert move["verdict"] == "ok"
    # Hot Color's two rotation draws are part of the exact check now
    # (analyze_research.hot_color_rotation_draws), not the "+2" fallback.
    assert move["detail"] == "potezi 5->5, red 3 kol 1 -> red 3 kol 2"


def test_outside_solo_the_returned_skulls_are_only_reported():
    before, after = _load("004"), _load("005")
    for record in (before, after):
        record["profile"]["rules"]["pvpMode"] = 0
    move = rm.check_transition(before, after)
    assert move["verdict"] == "ok"
    assert "JooJoo: 7 novih lobanja" in move["detail"]


def test_board_change_after_booster_without_new_input_is_the_booster():
    move = rm.check_transition(_load("010"), _load("011"))
    assert move["verdict"] == "booster"


def _session(record):
    session = ExactRefillSession(EngineRefill.from_profile(record["profile"]), record["board"],
                                 special_board=record["special_board"], follow_moves=True, max_plies=3)
    assert session.begin(record["board"], record["special_board"])
    return session


def _finish(session, record, events):
    from types import SimpleNamespace

    result = SimpleNamespace(intent_events=events, extra_moves=0, cleo_scenario_count=0,
                             board=record["board"], special_board=record["special_board"],
                             cleared_color_counts={})
    session.finish(result)
    return session.followed


def _without_skulls(record):
    record = copy.deepcopy(record)
    record["special_board"] = [[0 if v == 19 else v for v in row] for row in record["special_board"]]
    return record


def test_board_after_an_exploding_skull_is_followed_with_its_new_skulls():
    record = _load("004")
    skull = [{"type": "special_activation", "special": "joojoo_skull", "cascade": 1}]
    session = _session(record)
    assert _finish(session, _without_skulls(record), skull) == 1
    (_, special), = [key for key in session.states if key != session._key(record["board"], record["special_board"])]
    assert sum(v == 19 for row in special for v in row) == 7


def test_outside_solo_the_board_after_an_exploding_skull_is_not_followed():
    record = _load("004")
    record["profile"]["rules"]["pvpMode"] = 0
    skull = [{"type": "special_activation", "special": "joojoo_skull", "cascade": 1}]
    assert _finish(_session(record), _without_skulls(record), skull) == 0


def test_board_after_a_move_without_skulls_is_followed():
    # 007->008: no skull exploded, no new skull, no extra JooJoo draw.
    record = _load("004")
    match = [{"type": "match", "cascade": 1, "kind": "three"}]
    assert _finish(_session(record), record, match) == 1


def test_skull_count_takes_the_live_numpy_board():
    # The live special board is a numpy array; `special or ()` raised ValueError
    # and failed every move (2026-11-12 00:39:35).
    import numpy as np
    from engine_refill import joojoo_skull_count

    special = np.array(_load("004")["special_board"])
    assert joojoo_skull_count(special) == 7
    assert joojoo_skull_count(None) == 0
