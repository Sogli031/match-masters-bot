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


def test_full_unported_booster_gets_only_a_short_plan(monkeypatch):
    """The booster usually goes first, but an extra move may go before it
    (live 16:19:39): plan, but only QUICK_PLAN_SECONDS."""
    import copy
    from pathlib import Path
    from strategy_lab import planner
    from tools.analyze_research import load

    root = Path(__file__).resolve().parents[1]
    record, capture = load(root / "tests/fixtures/charles_live/000.json")
    profile = copy.deepcopy(capture["profile"])
    profile["rules"]["pvp_mode"] = 0
    live = sl.LiveSquareSolo()
    monkeypatch.setattr(live, "settled_profile", lambda script: profile)
    seen = {}

    def fake_anytime(lab, budget, **kwargs):
        seen["budget"] = budget
        return planner.Line(lab, [], []), {}

    monkeypatch.setattr(planner, "plan_anytime", fake_anytime)
    players = [dict(p, special_ability_type=26, energy=7, energy_to_ability=7) if p.get("player_type") == 0
               else p for p in record["snapshot_state"]["players"]]
    snapshot = {"board": record["board"], "special_board": record["special_board"], "slots": [],
                "state": {"moves": profile["state"]["moves"], "players": players, "rules": {"pvp_mode": 0}}}
    live.plan(None, snapshot, turn_time_left=60.0)
    assert 0.5 <= seen["budget"] <= sl.QUICK_PLAN_SECONDS
