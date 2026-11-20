"""Checkmate Charles: the exact plan prices the booster meter.

The solo plans were switched off 2026-11-10 because they played for points
with the meter at 0 and threw charge away. With Charles the meter keeps its
real charge and a full one is worth an activation (CHARLES_FIRE_VALUE).
"""
import sys
from dataclasses import replace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from strategy_lab import planner
import square_solo_live as sl


def _state(current, fired=0, score=100, price=44):
    return {"score": score, "turn_state": {"remaining_moves": 3},
            "booster_state": {"current": current, "maximum": 7},
            "booster_fire_value": price, "booster_fired": fired}


def test_line_value_counts_charge_pro_rata_and_banked_meters():
    assert planner.Line(_state(0)).value == 100
    assert abs(planner.Line(_state(7 // 2 + 0.5)).value - (100 + 44 * 0.5)) < 1e-9
    assert planner.Line(_state(0, fired=2)).value == 100 + 88


def test_without_a_price_the_value_is_the_score():
    state = _state(5, price=None)
    assert planner.Line(state).value == 100


def test_full_meter_is_banked_and_starts_again():
    banked = planner._bank_full_meter(_state(7))
    assert banked["booster_state"]["current"] == 0 and banked["booster_fired"] == 1
    assert planner._bank_full_meter(_state(6))["booster_fired"] == 0


def test_charles_eligible_in_solo_showdown_and_versus():
    charles = {"rules": {"pvp_mode": 1}, "players": [{"player_type": 0, "special_ability_type": 54}]}
    assert sl.charles_eligible(charles) and not sl.quick_plan(charles)
    # Showdown / Party (2) and Versus (0) plan too, briefly (QUICK_PLAN_SECONDS).
    for pvp in (0, 2):
        other = dict(charles, rules={"pvp_mode": pvp})
        assert sl.charles_eligible(other) and sl.quick_plan(other)
    # Woolly Workout (35) plays the exact plan too; another booster does not.
    assert sl.charles_eligible({"rules": {"pvp_mode": 1},
                                "players": [{"player_type": 0, "special_ability_type": 35}]})
    assert not sl.charles_eligible({"rules": {"pvp_mode": 1},
                                    "players": [{"player_type": 0, "special_ability_type": 27}]})


def test_woolly_booster_is_one_action_per_tappable_colour():
    import move_strategy as ms

    board = [[ms.BLUE] * 7 for _ in range(7)]
    special = [[0] * 7 for _ in range(7)]
    board[0][0], board[1][1], board[2][2] = ms.GREEN, ms.PURPLE, ms.ORANGE
    special[2][2] = ms.SPECIAL_HORIZONTAL      # a special is no Woolly target
    state = {"booster_auto": True, "booster_type": 35, "booster_state": {"current": 7, "maximum": 7},
             "board": board, "special_board": special}
    assert planner.actions(state) == [{"kind": "booster", "color": c}
                                      for c in sorted((ms.GREEN, ms.PURPLE))]
    assert planner.describe({"kind": "booster", "color": ms.GREEN}) == f"BOOSTER boja {ms.GREEN}"


def test_woolly_recorded_game_replays_exactly():
    """research 20261114_225210 004 -> 005 (Woolly, Square Match): the colour
    the bot tapped gives the game's score, moves and charge (all 22 actions of
    that game matched, 2026-11-15)."""
    import json

    from simulator_capture import lab_move
    from strategy_lab import simulation
    from tools.analyze_research import capture_from

    pair = json.loads((Path(__file__).resolve().parent / "fixtures/woolly_plan/004_005.json")
                      .read_text(encoding="utf-8"))
    lab = lab_move(capture_from(pair["before"]))
    lab["perks"], lab["booster_hold"] = {}, True
    result = simulation.step(lab, {"kind": "booster", "color": 3})
    assert result["supported"], result.get("reason")
    assert result["score_gain"] == 135
    assert result["state"]["turn_state"]["remaining_moves"] == 8
    assert result["state"]["booster_state"]["current"] == 0


def test_full_meter_with_booster_auto_offers_only_the_booster():
    state = {"booster_auto": True, "booster_state": {"current": 7, "maximum": 7},
             "board": [[1] * 7 for _ in range(7)], "special_board": [[0] * 7 for _ in range(7)]}
    assert planner.actions(state) == [{"kind": "booster"}]


def test_full_meter_with_booster_hold_also_offers_swipes():
    board = [[(row * 2 + col) % 5 + 1 for col in range(7)] for row in range(7)]
    board[0][:3] = [1, 2, 1]
    board[1][1] = 1
    state = {"mode": "none", "booster_auto": True, "booster_hold": True,
             "booster_state": {"current": 7, "maximum": 7},
             "board": board, "special_board": [[0] * 7 for _ in range(7)]}
    offered = planner.actions(state)
    assert offered[0] == {"kind": "booster"} and len(offered) > 1
    assert planner.actions(dict(state, booster_hold=False)) == [{"kind": "booster"}]
    assert {"kind": "booster"} not in planner.actions(dict(state, booster_state={"current": 6, "maximum": 7}))


def test_charles_first_plan_holds_the_booster_for_five_minutes():
    # tools/plan_width_curve 2026-11-15: holding reaches width 60 (+27 %).
    # 2026-11-17: no fixed time any more, 600 s is only the fence (the plan
    # stops on the gain and the turn clock).
    assert sl.CHARLES_FIRST_SECONDS == 600.0
    assert not hasattr(sl, "CHARLES_HOLD_SECONDS")


def test_carried_plan_key_needs_board_rng_and_moves():
    class Model:
        class rng:
            counter = 5
    state = {"board": [[1, 2], [3, 4]], "special_board": [[0, 0], [0, 0]], "engine_refill": Model,
             "turn_state": {"remaining_moves": 3}}
    other = dict(state, turn_state={"remaining_moves": 2})
    assert sl._plan_key(state) == sl._plan_key(dict(state))
    assert sl._plan_key(state) != sl._plan_key(other)
    assert sl._plan_key(state) == sl._plan_key(dict(state, perks={3: 0}))
    assert sl._plan_key(state) != sl._plan_key(dict(state, perks={3: 1}))
    assert sl._plan_key(state) != sl._plan_key(dict(state, booster_state={"current": 7, "maximum": 7}))


def test_charles_plan_budgets():
    assert sl.CHARLES_FIRST_SECONDS > sl.CHARLES_NEXT_SECONDS > 0


def test_planned_swipe_keeps_its_direction():
    """2026-11-15 00:29:53: the plan's (4,1)->(5,1) was swiped (5,1)->(4,1)."""
    import types
    import move_strategy as ms
    import runtime

    board = [[1] * 7 for _ in range(7)]
    cand = ms.MoveCandidate((5, 1), (4, 1), ms.Direction("up"), board, [[0] * 7 for _ in range(7)])
    evaluation = types.SimpleNamespace(candidate=cand)
    ordered = runtime.promote_engine_plan_move([evaluation], ((4, 1), (5, 1)))
    assert ordered[0] is evaluation
    played = ms.oriented_swap_candidate(evaluation)
    assert tuple(played.start) == (4, 1) and tuple(played.target) == (5, 1)


@pytest.mark.parametrize("kind", ["teleport", "energy_boost", None])
def test_live_runtime_plays_only_the_planned_action(monkeypatch, kind):
    import move_strategy as ms
    import runtime

    board = [[(row * 2 + col) % 5 + 1 for col in range(7)] for row in range(7)]
    board[0][:3] = [1, 2, 1]
    board[1][1] = 1
    calls = []
    monkeypatch.setattr(runtime, "apply_board_profile", lambda profile: None)
    monkeypatch.setattr(runtime, "resolve_ufo_state", lambda *args: None)
    monkeypatch.setattr(runtime, "resolve_mixy_meow_state", lambda *args: None)
    monkeypatch.setattr(runtime.move_telemetry, "record", lambda **kwargs: None)
    monkeypatch.setattr(runtime, "play_best_move_with_cursor_restore",
                        lambda start, direction, score, **kwargs: calls.append((start, direction)))

    def execute(action, slots, **kwargs):
        assert kwargs["planned"]
        assert slots[action.slot_number - 1] == kind
        calls.append(action.target if kind == "teleport" else runtime.oriented_swipe(action.follow_up))
        return True

    monkeypatch.setattr(runtime, "execute_verified_perk_action", execute)
    pair = ((0, 1), (6, 6)) if kind == "teleport" else ((1, 1), (0, 1))
    request = runtime.CheckBestMoveRequest(
        mode=ms.GameMode.NONE, special_piece_mode="auto", selected_profile="regular",
        allow_square_matches=False, specials_explode_immediately=False,
        score_rally_values=None, selected_perks=(runtime.PERK_TELEPORT, runtime.PERK_ENERGY_BOOST),
        pre_scanned_board=board, pre_scanned_special_board=[[0] * 7 for _ in range(7)],
        engine_plan_move=pair, engine_plan_perk=kind, engine_plan_owns_goal=True,
        cursor_return_position=(0, 0), force_no_booster=True, allow_perk_activation=True,
        debug_enabled=False, lookahead_candidates=0, include_future_value=False,
    )
    result = runtime.run_check_best_move_request(request)
    if kind == "teleport":
        assert calls == [[[0, 1], [6, 6]]]
        assert not result.turn_consumed
    else:
        assert calls == [((1, 1), ms.Direction.UP)]
    if kind:
        assert result.clear_used_perk_key == kind
        assert runtime.engine_plan_perk_action(
            replace(request, selected_perks=(runtime.PERK_NONE, runtime.PERK_NONE)), []
        ) is None


def test_plan_countdown_shows_in_the_status_bar():
    """2026-11-15: the wait was only in the Computing label, off the compact panel."""
    import time
    from datetime import datetime, timedelta
    from types import SimpleNamespace
    import memory_gui

    shown, calc = [], []
    window = SimpleNamespace(
        _plan_deadline=time.monotonic() + 95.2, _plan_deadline_clock=datetime(2026, 11, 15, 1, 30, 5),
        _plan_started=time.monotonic() - 12.3,
        _plan_carried=True, _plan_countdown_timer=SimpleNamespace(stop=lambda: None),
        _set_calc_status=calc.append, statusBar=lambda: SimpleNamespace(showMessage=shown.append))
    memory_gui.MemoryWindow._plan_countdown_tick(window)
    assert shown == ["Planer nastavlja plan: najvise jos 96 s (najkasnije 01:30:05)"] and calc
    # The first plan's seconds are the whole game clock: it counts up (2026-11-18).
    window._plan_carried = False
    memory_gui.MemoryWindow._plan_countdown_tick(window)
    assert shown[-1] == "Planer planira celu partiju: radi 12 s (granica sata 01:30:05)"
    window._plan_deadline = time.monotonic() - 1
    memory_gui.MemoryWindow._plan_countdown_tick(window)
    assert shown[-1] == "Planer: gotov, igra potez" and window._plan_deadline is None


def test_teleport_extra_at_max_moves_keeps_the_carried_plan():
    """Square Match 2026-11-15 01:16: a Teleport with an extra at 10 of 10 left
    the game at 10, the simulator at 11, and the carried plan was dropped
    (a second 2-minute plan)."""
    import json
    import move_strategy as ms
    from simulator_capture import lab_move
    from strategy_lab.simulation import step
    from tools.analyze_research import capture_from

    folder = ROOT / "tests/fixtures/teleport_at_max_moves"

    def lab(name, perks):
        state = lab_move(capture_from(json.loads((folder / name).read_text(encoding="utf-8"))))
        charge = state.get("booster_state") or {}
        return dict(state, perks=perks, booster_auto=True,
                    booster_state={"current": charge.get("current") or 0, "maximum": charge.get("maximum")})

    before = lab("before.json", {3: 1, 22: 1})
    action = {"kind": "teleport", "start": [1, 5], "target": [4, 1],
              "direction": ms._teleport_direction((1, 5), (4, 1)).value}
    after = step(before, action)["state"]
    assert after["turn_state"]["remaining_moves"] == 10
    assert sl._plan_key(after) == sl._plan_key(lab("after.json", {22: 1}))


def test_energy_boost_costs_no_move():
    """Square Match 2026-11-15 02:27: Energy Boost without an extra, 10 -> 10
    in the game, 9 in the simulator; the carried plan was dropped."""
    import json
    from simulator_capture import lab_move
    from strategy_lab.simulation import step
    from tools.analyze_research import capture_from

    folder = ROOT / "tests/fixtures/energy_boost_free_move"

    def lab(name, perks):
        state = lab_move(capture_from(json.loads((folder / name).read_text(encoding="utf-8"))))
        charge = state.get("booster_state") or {}
        return dict(state, perks=perks, booster_auto=True, booster_hold=True,
                    booster_state={"current": charge.get("current") or 0, "maximum": charge.get("maximum")})

    after = step(lab("before.json", {3: 1, 22: 1}),
                 {"kind": "energy_boost", "start": [0, 4], "target": [1, 4], "direction": "down"})["state"]
    assert after["turn_state"]["remaining_moves"] == 10
    assert sl._plan_key(after) == sl._plan_key(lab("after.json", {3: 1}))


def test_energy_boost_charges_with_the_swipes_own_match_only():
    """Square Match 2026-11-15 15:26:41 (research 20261115_152355 002 -> 003):
    a three and a cascade three, no Blue, energy 3 -> 6. The simulator charged
    with every destroyed piece (a full meter), the carried plan was dropped
    and the first plan ran 150 s again."""
    import json
    from simulator_capture import lab_move
    from strategy_lab.simulation import step
    from tools.analyze_research import capture_from

    folder = ROOT / "tests/fixtures/energy_boost_own_match"

    def lab(name, perks):
        state = lab_move(capture_from(json.loads((folder / name).read_text(encoding="utf-8"))))
        charge = state.get("booster_state") or {}
        return dict(state, perks=perks, booster_auto=True, booster_hold=True,
                    booster_state={"current": charge.get("current") or 0, "maximum": charge.get("maximum")})

    after = step(lab("before.json", {22: 1}),
                 {"kind": "energy_boost", "start": [2, 2], "target": [2, 3], "direction": "right"})["state"]
    assert after["booster_state"]["current"] == 6
    assert sl._plan_key(after) == sl._plan_key(lab("after.json", {}))


def test_charles_replans_in_the_background():
    # tools/replan_compare 2026-11-15: replans +12.4 %; the player found the
    # 60 s stop too long, so the replan runs while the carried line is played.
    assert sl.CHARLES_BG_AHEAD >= 3
    assert not hasattr(sl, "CHARLES_REPLAN_SECONDS")
    assert sl.LiveSquareSolo().bg is None
    # Live 2026-11-15 15:23 / 16:08 (plans of 100-121 actions): 4 actions and
    # 40 s never finished a pass while the line was long. The replan looks an
    # eighth of the line ahead, 4 to 10 actions, and searches while they play.
    assert [sl._bg_ahead(n) for n in (3, 20, 40, 64, 121)] == [4, 4, 5, 8, 10]
    assert sl.CHARLES_BG_AHEAD_MAX * sl.CHARLES_BG_ACTION_SECONDS <= sl.CHARLES_FIRST_SECONDS


def test_first_plan_does_not_start_a_pass_it_cannot_finish(monkeypatch):
    """Live 2026-11-15 15:26: widths 1, 4, 10 took 2.1, 15.0 and 49.0 s, the
    cut width 25 another 83.9 s of the 150, and the line was width 10's."""
    clock = [0.0]
    cost = {1: 2.1, 4: 15.0, 10: 49.0, 25: 300.0}
    calls = []

    def fake_plan(state, width=100, max_steps=300, deadline=None, finish_cut=False):
        calls.append(width)
        clock[0] += cost[width]
        line = planner.Line({"score": width, "turn_state": {"remaining_moves": 0}}, [{"kind": "booster"}], [0])
        return line, {"simulated": 1, "complete": True, "width": width}

    monkeypatch.setattr(planner, "plan", fake_plan)
    monkeypatch.setattr(planner.time, "monotonic", lambda: clock[0])
    best, stats = planner.plan_anytime({}, 150.0, stop_early=True)
    assert calls == [1, 4, 10] and stats["full_width"] == 10 and clock[0] < 70
    # Without it (a background replan, whose time is free) the pass is tried.
    clock[0], calls[:] = 0.0, []
    planner.plan_anytime({}, 150.0)
    assert calls == [1, 4, 10, 25]


def test_background_plan_is_taken_only_when_better():
    import types
    from concurrent.futures import Future

    live = sl.LiveSquareSolo()
    carried = types.SimpleNamespace(value=100, score=100)
    done = Future()
    done.set_result({"actions": [], "value": 0, "score": 0, "width": 4})
    live.bg, live.bg_deadline = done, 0.0
    log = []
    assert live._take_background({}, carried, log, None) is carried
    assert live.bg is None and "ostaje 100" in log[-1]


def test_background_plan_starts_above_the_widths_already_done(monkeypatch):
    """Live 2026-11-15 05:25: two 40 s replans went through widths 1, 4, 10
    again (the carried line's own) and found nothing."""
    import types
    from concurrent.futures import Future

    assert planner.next_width(10) == 25 and planner.next_width(None) == 1
    assert planner.next_width(1000) == 1000

    calls = []
    pool = types.SimpleNamespace(submit=lambda *args: calls.append(args) or Future())
    monkeypatch.setattr(sl, "_background_pool", lambda: pool)
    monkeypatch.setattr(sl, "_plan_key", lambda state: "key")
    live = sl.LiveSquareSolo()
    live.bg_width = 25
    live._start_background({}, [])      # too few actions left: no replan
    assert not calls
    # The widest pass a replan ran whole is where the next one starts.
    done = Future()
    done.set_result({"actions": [], "value": 0, "score": 0, "width": 60, "full_width": 60,
                     "passes": [(25, 3.0, True), (60, 9.5, True), (150, 27.5, False)]})
    live.bg, live.bg_deadline = done, 0.0
    log = []
    live._take_background({}, types.SimpleNamespace(value=100, score=100), log, None)
    assert live.bg_width == 60 and "150: prekinut 27.5 s" in log[-1]
    # A replan with no whole pass leaves the start where it was.
    cut = Future()
    cut.set_result({"actions": [], "value": 0, "score": 0, "width": 60, "full_width": None})
    live.bg = cut
    live._take_background({}, types.SimpleNamespace(value=100, score=100), log, None)
    assert live.bg_width == 60


def test_cut_pass_is_finished_not_thrown_away():
    """Live 2026-11-15 05:25: the 150 s first plan kept width 10; the width-25
    pass the deadline cut was dropped whole."""
    import time
    from simulator_capture import lab_move, load_capture
    from strategy_lab.simulation import step

    session = ROOT / "Debug/match_captures/session_20261101_002122"
    if not session.is_dir():
        pytest.skip("nema snimka partije")
    state = lab_move(load_capture(sorted(p for p in session.iterdir() if p.is_dir())[0]))
    past = time.monotonic() - 1
    dropped, stats = planner.plan(state, width=3, deadline=past)
    assert not stats["complete"] and not dropped.actions
    best, stats = planner.plan(state, width=3, deadline=past, finish_cut=True)
    assert not stats["complete"] and best.moves_left == 0 and best.score > state["score"]
    replay = state
    for action in best.actions:
        replay = step(replay, action)["state"]
    assert replay["score"] == best.score
    # A replan that starts wide has no time left: one cut pass, still a whole line.
    best, stats = planner.plan_anytime(state, 0, start_width=25)
    assert stats["passes"][0][0] == 25 and len(stats["passes"]) == 1
    assert stats["full_width"] is None and best.moves_left == 0


def test_a_move_in_hand_counts_in_the_beam_up_to_the_actions_left():
    """tools/plan_width_curve --move-prices 2026-11-15, 23 Charles games,
    width 10: 36081 points by the plain score, 143470 with a move at 100."""
    state = dict(_state(0, price=None), rank_move_value=100)
    line = planner.Line(state)
    assert planner._rank(line) == 100 + 3 * 100
    assert planner._rank(line, steps_left=1) == 100 + 100      # the clock allows one more action
    assert planner._rank(planner.Line(dict(state, turn_state={"remaining_moves": 0}))) == 100
    assert planner._rank(planner.Line(_state(0, price=None))) == 100


def test_live_charles_plan_prices_moves_and_stops_at_the_clock(monkeypatch):
    """Square Match 2026-11-15 05:25, the first board (1074 s on the clock)."""
    import types
    from concurrent.futures import Future
    from tools.analyze_research import load

    record, capture = load(ROOT / "tests/fixtures/charles_live/000.json")
    live = sl.LiveSquareSolo()
    monkeypatch.setattr(live, "settled_profile", lambda script: capture["profile"])
    monkeypatch.setattr(sl, "CHARLES_FIRST_SECONDS", 1.0)
    submitted = []
    pool = types.SimpleNamespace(submit=lambda *args: submitted.append(args) or Future())
    monkeypatch.setattr(sl, "_background_pool", lambda: pool)
    seen = {}

    def search(lab, seconds, **kwargs):
        seen.update(kwargs, move=lab.get("rank_move_value"))
        best, stats = planner.plan(lab, width=1, max_steps=8)
        return best, dict(stats, full_width=1, passes=[(1, 0.1, True)])

    monkeypatch.setattr(planner, "plan_anytime", search)
    snapshot = {"board": record["board"], "special_board": record["special_board"],
                "state": {"moves": capture["profile"]["state"]["moves"],
                          "players": record["snapshot_state"]["players"]}}
    outcome = live.plan(None, snapshot, turn_time_left=1074.0)
    assert outcome.get("move") or outcome.get("booster"), outcome
    assert seen["move"] == sl.CHARLES_MOVE_VALUE == 100
    # No fixed number of actions: the first plan reads the time left pass by
    # pass (planner.plan_anytime clock). The mode has a turn clock, so that
    # clock is the limit, not the 15-minute fence (Bombs Away 2026-11-18 16:06
    # ended with 1011 of 1500 s left while the fence cut the plan).
    clock = seen["clock"]
    left = 1074.0 - sl.CLOCK_RESERVE_SECONDS
    assert left > sl.MATCH_PLAN_SECONDS - sl.CLOCK_RESERVE_SECONDS
    # The game's clock stops for animations: an action takes less of it.
    assert clock["action_seconds"] == sl.GAME_CLOCK_ACTION_SECONDS == 4.0
    assert left - 2.0 < clock["left"] <= left
    # It looks FIRST_PLAN_STEPS ahead; the background replans go to the end.
    assert seen["max_steps"] == sl.FIRST_PLAN_STEPS == 50
    assert seen["finish_cut"] is True and seen["stop_early"] is True
    # The narrow widths only lose; the player set the first plan to 25.
    assert seen["widths"] == (sl.FIRST_MAX_WIDTH,) == (25,) and "start_width" not in seen
    # The background replan: width 25, the same price, and its own short fence
    # (the time left less the actions played before its board is only the
    # outer limit).
    (function, state, seconds, width, steps, baseline, rule, bg_clock, first_cost, max_width, stop_early), = submitted
    assert function is planner.background_plan
    # As wide as the first plan, from the first move (2026-11-19).
    assert max_width == sl.BG_MAX_WIDTH == 25
    # The replan stops by itself against the carried line's value.
    assert baseline == live.carry.value and rule is None
    assert seen["rule"] is planner.STOP_RULE and callable(seen["on_pass"])
    expect = left - sl.GAME_CLOCK_ACTION_SECONDS
    ahead = sl._bg_ahead(len(live.carry.actions))
    assert expect - 2.0 < bg_clock["left"] <= expect
    assert bg_clock["busy"] == ahead * sl.GAME_CLOCK_ACTION_SECONDS
    # Its time: what the carried line does not need to play to its end
    # (2026-11-18 08:40, the bot waited 200 s and the clock cut the line),
    # capped at BG_PLAN_SECONDS (the player, 2026-11-20).
    rest = (len(live.carry.actions) - ahead) * sl.GAME_CLOCK_ACTION_SECONDS
    assert bg_clock["left"] - rest > sl.BG_PLAN_SECONDS
    assert seconds == pytest.approx(sl.BG_PLAN_SECONDS) and first_cost is None
    assert bg_clock["action_seconds"] == sl.GAME_CLOCK_ACTION_SECONDS
    # Width 10 first, then 25 while it fits (answer 23 B), and the horizon
    # that fits both passes inside the fence at this pace.
    assert width == sl.BG_START_WIDTH == 10 and sl.BG_MAX_WIDTH == 25
    assert steps == (sl.BG_FALLBACK_STEPS if live.bg_pace is None
                     else max(1, int(seconds / (live.bg_pace * sl._bg_widths_cost()))))
    # The clock's reading ages with the search: 100 s later, 100 s less.
    live.clock_read_at = 0.0
    assert live._time_left(1074.0, now=100.0) == 1074.0 - 100.0 - sl.CLOCK_RESERVE_SECONDS
    assert live._time_left(None, now=live.match_started + 100.0) == pytest.approx(
        sl.MATCH_PLAN_SECONDS - 100.0 - sl.CLOCK_RESERVE_SECONDS)
    assert state["rank_move_value"] == 100
    assert live.carry is not None and live.bg is not None


def test_a_restarted_plan_is_short(monkeypatch):
    """Froggy Fu 2026-11-20: the activation and its lotus replay only
    sometimes, and the board after one starts a fresh plan -- the player sat
    75 s on it ("nekad uspe da pogodi nekad ne zato se resetuje"). Only the
    match's first plan is a whole one; a restart searches briefly."""
    import copy
    import types
    from concurrent.futures import Future
    from tools.analyze_research import load

    record, capture = load(ROOT / "tests/fixtures/charles_live/000.json")
    profile = copy.deepcopy(capture["profile"])
    live = sl.LiveSquareSolo()
    monkeypatch.setattr(live, "settled_profile", lambda script: profile)
    monkeypatch.setattr(sl, "_background_pool",
                        lambda: types.SimpleNamespace(submit=lambda *args: Future()))
    seen = {}

    def search(lab, seconds, **kwargs):
        seen.update(seconds=seconds, **kwargs)
        return planner.Line(lab, [], []), {}

    monkeypatch.setattr(planner, "plan_anytime", search)
    snapshot = {"board": record["board"], "special_board": record["special_board"],
                "state": {"moves": profile["state"]["moves"],
                          "players": record["snapshot_state"]["players"]}}
    # The match's first plan: the whole clock, FIRST_PLAN_STEPS ahead.
    live.plan(None, snapshot, turn_time_left=600.0)
    assert seen["clock"] is not None and seen["max_steps"] == sl.FIRST_PLAN_STEPS
    # The plan is gone (the lotus came out differently): the board restarts.
    live.carry = live.carry_key = live.carry_after = None
    seen.clear()
    live.plan(None, snapshot, turn_time_left=600.0)
    assert "clock" not in seen and "widths" not in seen   # every width that fits
    assert seen["max_steps"] == sl.RESTART_PLAN_STEPS == 20
    assert 0.0 < seen["seconds"] <= sl.RESTART_PLAN_SECONDS == 50.0
    assert seen["finish_cut"] is True and seen["stop_early"] is True


def test_no_energy_boost_while_the_meter_is_full():
    """The game refuses Energy Boost with a full booster (2026-11-15 03:35)."""
    board = [[(row * 2 + col) % 5 + 1 for col in range(7)] for row in range(7)]
    board[0][:3] = [1, 2, 1]
    board[1][1] = 1
    state = {"mode": "none", "booster_auto": True, "booster_hold": True, "perks": {22: 1},
             "booster_state": {"current": 7, "maximum": 7},
             "board": board, "special_board": [[0] * 7 for _ in range(7)]}
    assert not any(a.get("kind") == "energy_boost" for a in planner.actions(state))
    state["booster_state"] = {"current": 6, "maximum": 7}
    assert any(a.get("kind") == "energy_boost" for a in planner.actions(state))
