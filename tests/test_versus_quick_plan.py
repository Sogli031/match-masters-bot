"""Versus plans the swipes with any booster; the turn's first move thinks longer (2026-11-19)."""
import square_solo_live as sl


def _state(pvp_mode, booster):
    return {"rules": {"pvp_mode": pvp_mode, "id": "mighty-mushrooms"},
            "players": [{"player_type": 0, "special_ability_type": booster}]}


def test_versus_plans_with_an_unported_booster():
    all_aboard = 26
    assert all_aboard not in sl.EXACT_PLAN_BOOSTERS
    mode = "Multiplier Mushrooms Studio"
    assert sl.planner_support(_state(0, all_aboard), mode) is None
    assert "nije podrzan" in (sl.planner_support(_state(1, all_aboard), mode) or "")


def test_turn_start_thinks_longer_than_a_carried_move():
    assert sl.QUICK_TURN_START_SECONDS > sl.QUICK_PLAN_SECONDS


def test_multiplier_value_counts_our_later_turns():
    from strategy_lab.planner import Line
    assert [sl.versus_turns_after({"current_turn": t}) for t in (7, 5, 3, 1)] == [3, 2, 1, 0]
    line = Line({"score": 100, "score_multiplier": 4, "multiplier_value": 50, "turn_state": {}})
    assert line.value == 100 + 4 * 50
    assert Line({"score": 100, "score_multiplier": 4, "turn_state": {}}).value == 100


def test_full_unported_booster_goes_before_the_plan(monkeypatch):
    live = sl.LiveSquareSolo()
    monkeypatch.setattr(live, "settled_profile", lambda script: {"rules": {}, "players": []})
    snapshot = {"board": [[1]], "special_board": [[0]], "stable": True,
                "state": {"rules": {"pvp_mode": 0}, "game_state": sl.WAITING_FOR_INPUT,
                          "players": [{"player_type": 0, "special_ability_type": 26,
                                       "energy": 7, "energy_to_ability": 7}]}}
    monkeypatch.setattr(sl, "_solo_snapshot_matches_profile", lambda state, profile: True)
    outcome = live.plan(None, snapshot)
    assert outcome["move"] is None and "buster je pun" in outcome["note"]
