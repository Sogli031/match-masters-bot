"""The exact planner stops by itself once a wider pass no longer pays, and
shows every pass in the GUI (strategy_lab.planner STOP_RULE, plan_anytime
on_pass; square_solo_live.PASS_LISTENER; memory_gui.plan_pass_lines)."""
from __future__ import annotations

import types
from concurrent.futures import Future

import pytest

import square_solo_live as sl
from strategy_lab import planner

RULE = {"min_gain": 0.01, "min_points": 0, "gain_per_second": 0.0, "gain_decay": 1.0, "min_width": 10}


def _fake(monkeypatch, cost, score, complete=None):
    """plan() replaced: each width takes cost[w] seconds and scores score[w]."""
    clock = [0.0]
    calls = []

    def fake_plan(state, width=100, max_steps=300, deadline=None, finish_cut=False):
        calls.append(width)
        clock[0] += cost[width]
        line = planner.Line({"score": score[width], "turn_state": {"remaining_moves": 0}},
                            [{"kind": "booster"}] * 3, [0, 0, 0])
        whole = True if complete is None else complete.get(width, True)
        return line, {"simulated": 1, "complete": whole, "width": width}

    monkeypatch.setattr(planner, "plan", fake_plan)
    monkeypatch.setattr(planner.time, "monotonic", lambda: clock[0])
    return clock, calls


def _passes(*rows):
    return [{"width": w, "seconds": t, "complete": True, "value": v} for w, t, v in rows]


def test_stops_when_the_gain_falls_under_the_threshold(monkeypatch):
    cost = {1: 1, 4: 3, 10: 8, 25: 30, 60: 60, 150: 150, 400: 400, 1000: 1000}
    score = {1: 1000, 4: 1500, 10: 1800, 25: 1805, 60: 5000, 150: 6000, 400: 6000, 1000: 6000}
    clock, calls = _fake(monkeypatch, cost, score)
    best, stats = planner.plan_anytime({}, 600.0, rule=RULE)
    # 25 brought 0.3 % over 10: width 60 does not start.
    assert calls == [1, 4, 10, 25]
    assert best.score == 1805 and stats["width"] == 25
    assert stats["stop_reason"].startswith("dobitak 0.3% < prag 1%")
    assert clock[0] == 42


def test_narrow_passes_do_not_stop_the_first_plan():
    # Width 4 equal to width 1: the narrow passes are noisy, go on to min_width.
    assert planner.stop_reason(_passes((1, 0.5, 900), (4, 2, 900)), 10, rule=RULE) is None
    assert planner.stop_reason(_passes((1, 0.5, 900), (4, 2, 900), (10, 6, 901)), 25, rule=RULE)
    # A loss counts as no gain.
    assert planner.stop_reason(_passes((4, 2, 900), (10, 6, 800)), 25, rule=RULE)
    # Enough gain: the next width runs.
    assert planner.stop_reason(_passes((4, 2, 900), (10, 6, 1000)), 25, rule=RULE) is None


def test_points_threshold_counts_too():
    rule = dict(RULE, min_gain=0.0, min_points=50)
    assert planner.stop_reason(_passes((4, 2, 900), (10, 6, 940)), 25, rule=rule) == "dobitak +40 < prag 50"
    assert planner.stop_reason(_passes((4, 2, 900), (10, 6, 960)), 25, rule=rule) is None


def test_background_replan_is_measured_against_the_carried_line():
    # The first pass of a replan has nothing before it but the carried line.
    passes = _passes((60, 20, 21729))
    assert planner.stop_reason(passes, 150, rule=RULE) is None
    assert "dobitak -0.1%" in planner.stop_reason(passes, 150, baseline=21752, rule=RULE)
    assert planner.stop_reason(_passes((60, 20, 23000)), 150, baseline=21752, rule=RULE) is None


def test_a_pass_that_does_not_pay_for_its_time_does_not_start(monkeypatch):
    rule = dict(RULE, gain_per_second=0.001)    # 0.1 % of the score per second
    # 25 brought 5 %; width 60 would take 30 * 60/25 * 1.3 = 94 s for ~5 %:
    # 0.05 / 94 = 0.0005 per second < 0.001.
    reason = planner.stop_reason(_passes((10, 8, 1000), (25, 30, 1050)), 60, rule=rule)
    assert reason == "sirina 60 (~94 s) za ~5.0% se ne isplati"
    # The same gain from a quick pass pays.
    assert planner.stop_reason(_passes((10, 2, 1000), (25, 5, 1050)), 60, rule=rule) is None

    cost = {1: 1, 4: 3, 10: 8, 25: 30, 60: 60, 150: 150, 400: 400, 1000: 1000}
    score = {1: 1000, 4: 1100, 10: 1200, 25: 1260, 60: 2000, 150: 2000, 400: 2000, 1000: 2000}
    clock, calls = _fake(monkeypatch, cost, score)
    best, stats = planner.plan_anytime({}, 600.0, rule=rule)
    assert calls == [1, 4, 10, 25] and "se ne isplati" in stats["stop_reason"]


def test_the_clock_stays_the_fence(monkeypatch):
    # Gains keep coming, but the turn clock (seconds) cuts the search.
    cost = {1: 1, 4: 3, 10: 10, 25: 40, 60: 120, 150: 300, 400: 800, 1000: 2000}
    score = {1: 100, 4: 200, 10: 400, 25: 800, 60: 1600, 150: 3200, 400: 6400, 1000: 12800}
    clock, calls = _fake(monkeypatch, cost, score)
    best, stats = planner.plan_anytime({}, 150.0, rule=RULE, stop_early=True)
    assert calls == [1, 4, 10, 25] and clock[0] <= 150
    assert stats["stop_reason"].startswith("granica: sirina 60")
    # A pass the deadline cuts ends the search too.
    clock, calls = _fake(monkeypatch, cost, score, complete={60: False})
    best, stats = planner.plan_anytime({}, 150.0, rule=RULE)
    assert calls == [1, 4, 10, 25, 60] and stats["stop_reason"].startswith("isteklo vreme")


def test_every_pass_goes_to_the_listener(monkeypatch):
    cost = {1: 1, 4: 3, 10: 8, 25: 30, 60: 60, 150: 150, 400: 400, 1000: 1000}
    score = {1: 1000, 4: 900, 10: 1800, 25: 1800, 60: 1800, 150: 1800, 400: 1800, 1000: 1800}
    _fake(monkeypatch, cost, score)
    seen = []
    best, stats = planner.plan_anytime({"score": 500, "solo_targets": [400, 1500, 5000]}, 600.0,
                                       rule=RULE, on_pass=seen.append)
    passes = [e for e in seen if not e.get("done")]
    assert [p["width"] for p in passes] == [1, 4, 10, 25]
    assert [p["best"] for p in passes] == [True, False, True, True]
    assert passes[0]["target"] == 1500 and not passes[0]["reaches"] and passes[2]["reaches"]
    assert passes[0]["boosters"] == 3 and passes[0]["actions"] == 3 and passes[0]["first"] == ["BOOSTER"] * 3
    done = seen[-1]
    assert done["done"] and done["width"] == 25 and done["score"] == 1800
    assert done["reason"] == stats["stop_reason"] and len(stats["pass_info"]) == 4
    # A failing listener never stops the search.
    planner.plan_anytime({}, 600.0, rule=RULE, on_pass=lambda info: 1 / 0)


def test_background_plan_sends_passes_through_the_queue(monkeypatch):
    cost = {w: 1 for w in planner.WIDTHS}
    score = {1: 1000, 4: 1000, 10: 1000, 25: 1000, 60: 1000, 150: 1000, 400: 1000, 1000: 1000}
    _fake(monkeypatch, cost, score)
    sent = []
    monkeypatch.setattr(planner, "_PASS_QUEUE", types.SimpleNamespace(put=sent.append))
    result = planner.background_plan({}, 100.0, start_width=25, baseline=1200, rule=RULE)
    assert [e.get("width") for e in sent] == [25, 25]       # the pass, then the end
    assert all(e["source"] == "pozadinski plan" for e in sent)
    assert result["stop_reason"].startswith("dobitak") and len(result["passes"]) == 1
    # rule False: no dynamic stop (Woolly), every width runs.
    sent.clear()
    result = planner.background_plan({}, 100.0, start_width=25, baseline=1200, rule=False)
    # The player's cap (2026-11-18): no pass wider than max_width.
    capped = planner.background_plan({}, 100.0, start_width=25, baseline=1200, rule=False, max_width=60)
    assert [w for w, _, _ in capped["passes"]] == [w for w, _, _ in result["passes"] if w <= 60]
    assert len(result["passes"]) == len([w for w in planner.WIDTHS if w >= 25])


def test_listener_and_queue_reach_the_gui(monkeypatch):
    import queue

    got = []
    monkeypatch.setattr(sl, "PASS_LISTENER", None)
    sl.set_pass_listener(got.append)
    q = queue.Queue()
    q.put({"width": 60})
    q.put(None)
    sl._drain_passes(q)
    assert got == [{"width": 60}]
    sl.set_pass_listener(lambda info: 1 / 0)
    sl._tell({"width": 1})      # a broken listener is ignored


def test_background_choice_is_shown(monkeypatch):
    got = []
    monkeypatch.setattr(sl, "PASS_LISTENER", got.append)
    live = sl.LiveSquareSolo()
    done = Future()
    done.set_result({"actions": [], "value": 0, "score": 0, "width": 60, "full_width": 60,
                     "passes": [(60, 9.5, True)], "stop_reason": "dobitak -0.1% < prag 1%"})
    live.bg, live.bg_deadline = done, 0.0
    log = []
    live._take_background({}, types.SimpleNamespace(value=100, score=100), log, None)
    assert "stao: dobitak -0.1% < prag 1%" in log[-1]
    assert got == [{"chosen": True, "source": "pozadinski plan", "taken": False, "score": 0,
                    "width": 60, "carried": 100}]


def test_plan_pass_lines():
    memory_gui = pytest.importorskip("memory_gui")
    line, = memory_gui.plan_pass_lines({"source": "prvi plan", "width": 25, "seconds": 31.2,
                                        "complete": True, "score": 18866, "actions": 112,
                                        "boosters": 7, "target": 20000, "reaches": False,
                                        "best": True})
    assert line.endswith("prvi plan sirina 25: 31.2 s, skor 18866, 112 akcija, 7 boostera, "
                         "cilj 20000 ne  <- najbolji")
    done = memory_gui.plan_pass_lines({"done": True, "source": "prvi plan", "width": 25, "score": 18866,
                                       "actions": 112, "seconds": 43.0,
                                       "reason": "dobitak 0.4% < prag 1%", "first": ["BOOSTER", "x"]})
    assert "IZABRAN: sirina 25" in done[0] and "stao: dobitak 0.4% < prag 1%" in done[0]
    assert done[1] == "    prvi: BOOSTER; x"
    taken = memory_gui.plan_pass_lines({"chosen": True, "taken": True, "source": "pozadinski plan",
                                        "width": 60, "score": 21752, "carried": 17728})
    assert "PRELAZIM na sirinu 60, skor 21752 (bilo 17728)" in taken[0]
    assert memory_gui.plan_pass_lines(None) == []


def test_gui_passes_arrive_only_through_the_signal():
    memory_gui = pytest.importorskip("memory_gui")
    signals = memory_gui.ReaderSignals
    assert hasattr(signals, "plan_pass")
    shown = []
    window = types.SimpleNamespace(
        PlansGroup=types.SimpleNamespace(show=lambda: shown.append("show")),
        PlansView=types.SimpleNamespace(
            appendPlainText=shown.append,
            verticalScrollBar=lambda: types.SimpleNamespace(setValue=lambda v: None, maximum=lambda: 0)))
    memory_gui.MemoryWindow._on_plan_pass(window, {"source": "prvi plan", "width": 1, "seconds": 0.5,
                                                   "score": 10, "actions": 2, "boosters": 0})
    assert shown[0] == "show" and "sirina 1: 0.5 s" in shown[1]


def test_live_rule_never_stops_below_the_measured_width():
    """tools/plan_stop_curve 2026-11-17: below width 60 a pass that brought
    nothing was followed by a big gain in 12 of 14 cases; only from width 150
    on does a pass with no gain end the search (converged, live 20:12)."""
    rule = planner.STOP_RULE
    assert rule["min_width"] >= 150
    flat = _passes((10, 8, 1000), (25, 30, 1000), (60, 60, 900))
    assert planner.stop_reason(flat, 150, rule=rule) is None
    assert planner.stop_reason(_passes((60, 6, 21752)), 150, baseline=21752, rule=rule) is None
    reason = planner.stop_reason(_passes((60, 6, 21752), (150, 11, 21752)), 400, baseline=21752, rule=rule)
    assert reason == "sirina 150 nije donela nista (+0)"
    assert planner.stop_reason(_passes((60, 6, 21752), (150, 11, 21800)), 400, rule=rule) is None


def test_live_plan_knows_the_colours_under_colourless_pieces(monkeypatch):
    """Color Climb 2026-11-17 22:40 (Foxy Roxy SE): LiveSquareSolo.plan left
    profile ball_slots out, EngineRefill.balls was None and the booster lines
    were lost (live first plan 3276 at width 60, the same board replayed
    49939; the game lost 4396/7050)."""
    from pathlib import Path
    import simulator_capture
    from tools.analyze_research import load

    root = Path(__file__).resolve().parents[1]
    record, capture = load(root / "tests/fixtures/charles_live/000.json")
    live = sl.LiveSquareSolo()
    monkeypatch.setattr(live, "settled_profile", lambda script: capture["profile"])
    seen = {}

    def lab_move(cap):
        seen.update(cap["profile"])
        raise StopIteration

    monkeypatch.setattr(simulator_capture, "lab_move", lab_move)
    foxy = {"row": 2, "col": 3, "x": 3, "y": 2, "color": 4, "value": 31, "status": 0}
    snapshot = {"board": record["board"], "special_board": record["special_board"],
                "slots": [foxy, {"row": 0, "col": 0, "color": 1, "value": 0}],
                "state": {"moves": capture["profile"]["state"]["moves"],
                          "players": record["snapshot_state"]["players"]}}
    with pytest.raises(StopIteration):
        live.plan(None, snapshot, turn_time_left=1074.0)
    assert seen["ball_slots"] == [{"row": 2, "col": 3, "color": 4, "value": 31}]


def test_turn_clock_gives_each_pass_its_actions(monkeypatch):
    """The first plan has no fixed time (2026-11-17): a pass gets the actions
    the turn clock leaves after it, and none starts once the best line found
    would no longer fit."""
    cost = {1: 1, 4: 3, 10: 10, 25: 40, 60: 120, 150: 300, 400: 800, 1000: 2000}
    score = {1: 100, 4: 200, 10: 400, 25: 800, 60: 1600, 150: 3200, 400: 6400, 1000: 12800}
    clock, calls = _fake(monkeypatch, cost, score)
    steps = []
    fake = planner.plan

    def spy(state, width=100, max_steps=300, deadline=None, finish_cut=False):
        steps.append(max_steps)
        line, run = fake(state, width=width, max_steps=max_steps, deadline=deadline, finish_cut=finish_cut)
        line.actions = [{"kind": "booster"}] * 40     # a 40-action line: 340 s to play
        return line, run

    monkeypatch.setattr(planner, "plan", spy)
    best, stats = planner.plan_anytime({}, 600.0, rule=RULE | {"min_width": 1000}, stop_early=True,
                                       clock={"left": 600.0, "action_seconds": 8.5})
    # 60 starts at 54 s with ~125 s ahead: 600 - 54 - 125 = 421 s, 49 actions.
    assert calls == [1, 4, 10, 25, 60]
    assert steps[0] == 70 and steps[-1] == 49 and steps == sorted(steps, reverse=True)
    # 150 would end near 486 s: 114 s left, 13 actions < the 40 of the line.
    assert stats["stop_reason"].startswith("sat: posle sirine 150")


def test_stale_board_waits_for_the_plan_a_few_times():
    """Color Climb 2026-11-17 23:05:26: the plan's swipe was not legal on a
    stale board (row 6 from before the Foxy activation), the bot played its
    own pick and the plan was lost. The move waits for the board instead,
    PLAN_BOARD_WAIT_LIMIT times at most for the same board."""
    import runtime

    runtime._PLAN_BOARD_WAITS.clear()
    board = [[6, 6, 2], [1, 2, 3]]
    pair = ((1, 2), (1, 1))
    waits = [runtime._plan_board_wait(board, pair) for _ in range(runtime.PLAN_BOARD_WAIT_LIMIT + 1)]
    assert waits == [True] * runtime.PLAN_BOARD_WAIT_LIMIT + [False]
    assert runtime._plan_board_wait([[6, 2, 6], [1, 2, 3]], pair)     # a fresh board waits again


def test_match_time_is_the_turn_clock_or_fifteen_minutes(monkeypatch):
    """The challenge turn clock when the mode has one (the player 2026-11-18:
    in a Solo Challenge only the clock to the end counts), else the whole
    match within 15 minutes (2026-11-17)."""
    live = sl.LiveSquareSolo()
    live.match_started = 1000.0
    reserve = sl.CLOCK_RESERVE_SECONDS
    assert live._time_left(None, now=1000.0) == sl.MATCH_PLAN_SECONDS - reserve == 900.0 - reserve
    assert live._time_left(None, now=1300.0) == 600.0 - reserve         # 5 minutes gone
    live.clock_read_at = 1300.0
    assert live._time_left(1199.0, now=1300.0) == 1199.0 - reserve      # the game's clock, not 600
    assert live._time_left(200.0, now=1300.0) == 200.0 - reserve
    live.reset()
    assert live.match_started is None


def test_background_replan_has_no_short_time_of_its_own(monkeypatch):
    """The replan is no longer cut after the actions it looks ahead take to
    play: it gets the match time left, and none starts without time to play."""
    calls = []
    pool = types.SimpleNamespace(submit=lambda *args: calls.append(args) or Future())
    monkeypatch.setattr(sl, "_background_pool", lambda: pool)
    monkeypatch.setattr(sl, "_plan_key", lambda state: "key")
    monkeypatch.setattr("strategy_lab.simulation.step",
                        lambda state, action: {"supported": True, "state": state})
    live = sl.LiveSquareSolo()
    live.bg_left = 500.0
    live._start_background({}, [{"kind": "booster"}] * 30, 1234)
    (_, _, seconds, _, steps, baseline, rule, clock, first_cost, max_width), = calls
    assert max_width == sl.BG_MAX_WIDTH
    ahead = sl._bg_ahead(30)
    assert clock == {"left": 500.0, "busy": ahead * sl.CHARLES_ACTION_SECONDS,
                     "action_seconds": sl.CHARLES_ACTION_SECONDS}
    # It may take what the carried line does not need to play to its end.
    assert seconds == 500.0 - (30 - ahead) * sl.CHARLES_ACTION_SECONDS > ahead * sl.CHARLES_BG_ACTION_SECONDS
    assert baseline == 1234 and rule is None and steps == 300 and first_cost is None
    # Almost no time left: no replan at all.
    calls.clear()
    live.bg_left = ahead * sl.CHARLES_ACTION_SECONDS + 1.0
    live._start_background({}, [{"kind": "booster"}] * 30, 1234)
    assert not calls and live.bg is None
    # Woolly (no dynamic stop): the old short time, no clock.
    live.dynamic, live.bg_left = False, None
    live._start_background({}, [{"kind": "booster"}] * 30, 1234)
    (_, _, seconds, _, _, _, rule, clock, _, _), = calls
    assert clock is None and rule is False and seconds == ahead * sl.CHARLES_BG_ACTION_SECONDS


def test_first_pass_cost_and_overlap_count_on_the_clock(monkeypatch):
    """Live 2026-11-18 08:40: a width-150 replan was given 43 actions as if
    its pass were free, took 243 s, and only 26 still fitted. The caller's
    estimate of the first pass counts now; the actions played meanwhile
    (``busy``) do not count twice."""
    cost = {150: 240, 400: 640, 1000: 1600}
    score = {150: 100, 400: 200, 1000: 300}
    clock, calls = _fake(monkeypatch, cost, score)
    steps = []
    fake = planner.plan

    def spy(state, width=100, max_steps=300, deadline=None, finish_cut=False):
        steps.append(max_steps)
        return fake(state, width=width, max_steps=max_steps, deadline=deadline, finish_cut=finish_cut)

    monkeypatch.setattr(planner, "plan", spy)
    planner.plan_anytime({}, 600.0, start_width=150, rule=RULE,
                         clock={"left": 425.0, "busy": 42.5, "action_seconds": 8.5}, first_cost=240.0)
    assert steps[0] == int((425 - 240) / 8.5) == 21
    # Shorter than the actions ahead: only those are waited for.
    steps.clear()
    clock[0] = 0.0
    planner.plan_anytime({}, 600.0, start_width=150, rule=RULE,
                         clock={"left": 425.0, "busy": 42.5, "action_seconds": 8.5}, first_cost=10.0)
    assert steps[0] == int((425 - 42.5) / 8.5) == 45


def _bg_live(monkeypatch):
    calls = []
    pool = types.SimpleNamespace(submit=lambda *args: calls.append(args) or Future())
    monkeypatch.setattr(sl, "_background_pool", lambda: pool)
    monkeypatch.setattr(sl, "_plan_key", lambda state: "key")
    monkeypatch.setattr("strategy_lab.simulation.step",
                        lambda state, action: {"supported": True, "state": state})
    return sl.LiveSquareSolo(), calls


def test_replan_width_leaves_the_carried_line_its_time(monkeypatch):
    """Bombs Away 2026-11-18 08:40:40: 41 carried actions (3291), ~426 s of
    the match left, the first plan's width 150 at 301 s for 42 actions. Width
    150 (~250 s) would make the bot wait past what the line needs to play;
    the widest width that leaves it room runs instead."""
    live, calls = _bg_live(monkeypatch)
    live.bg_width = 150
    live._measure_pace([(60, 124.1, True), (150, 301.1, True)], 42)
    live.bg_left = 426.0
    actions = [{"kind": "booster"}] * 41
    live._start_background({}, actions, 3291)
    (_, _, seconds, width, _, _, _, clock, first_cost, _), = calls
    ahead = sl._bg_ahead(41)
    room = 426.0 - (41 - ahead) * sl.CHARLES_ACTION_SECONDS
    assert seconds == room and first_cost <= room
    assert width == 60 and first_cost == pytest.approx(301.1 / (150 * 42) * 60 * (41 - ahead))
    # Plenty of time: the width already run whole.
    calls.clear()
    live.bg_left = 900.0
    live._start_background({}, actions, 3291)
    assert calls[0][3] == 150
    # No width fits: no replan, the carried line plays on.
    calls.clear()
    live.bg_left = (41 - ahead) * sl.CHARLES_ACTION_SECONDS + 9.0
    live._measure_pace([(150, 3000.0, True)], 10)
    live._start_background({}, actions, 3291)
    assert not calls and live.bg is None


def test_replan_is_compared_as_the_clock_will_play_it(monkeypatch):
    """08:43:59: the 3502 replan beat the 3291 line at full length, then the
    clock cut it to 26 actions (2432). Both are compared cut to what fits."""
    def replay(state, actions):
        # The replan front-loads nothing: its points come late.
        per = {"r": 10, "c": 80}
        gains = [per[a["id"]] for a in actions]
        return planner.Line({"score": sum(gains), "turn_state": {"remaining_moves": 0}}, list(actions), gains)

    monkeypatch.setattr(sl, "_replay_line", replay)
    live = sl.LiveSquareSolo()
    carried = replay({}, [{"kind": "booster", "id": "c"}] * 41)                      # 3280
    done = Future()
    done.set_result({"actions": [{"kind": "booster", "id": "r"}] * 43, "value": 0, "score": 0, "width": 150,
                     "full_width": 150, "passes": [(150, 243.0, True)]})
    live.bg, live.bg_deadline = done, 0.0
    log = []
    kept = live._take_background({}, carried, log, None, fit=lambda: 26)
    assert kept is carried and "ostaje" in log[-1]
    # Whole lines fit: the better one wins.
    done2 = Future()
    done2.set_result({"actions": [{"kind": "booster", "id": "c"}] * 43, "value": 0, "score": 0, "width": 150,
                      "full_width": 150, "passes": [(150, 243.0, True)]})
    live.bg = done2
    taken = live._take_background({}, carried, log, None, fit=lambda: 60)
    assert len(taken.actions) == 43 and "prelazim" in log[-1]
    assert live.bg_pace == pytest.approx(243.0 / (150 * 43))


def test_only_the_meter_differs_keeps_the_line():
    """Bombs Away 2026-11-18 09:02 / 09:05: the line predicted 6 and 5, the
    game had 7 (board, specials, RNG and moves exact). The line is replayed
    from the real meter instead of a 127 s / 97 s fresh first plan."""
    key = ("board", "special", 849, 6, 6, 7, ())
    assert sl._same_but_charge(key, key[:4] + (7,) + key[5:])
    assert not sl._same_but_charge(key, key)                          # the plain match path
    assert not sl._same_but_charge(key, ("other",) + key[1:4] + (7,) + key[5:])
    assert not sl._same_but_charge(key, key[:3] + (5, 7) + key[5:])   # moves differ too
    assert not sl._same_but_charge(None, key)


@pytest.mark.parametrize("pvp", [0, 2])
def test_showdown_and_versus_plan_briefly(monkeypatch, pvp):
    """The player (2026-11-19): Showdown / Versus get the planner too, but a
    short search (QUICK_PLAN_SECONDS) with no held booster, carried line or
    background replan."""
    import copy
    from pathlib import Path
    from tools.analyze_research import load

    root = Path(__file__).resolve().parents[1]
    record, capture = load(root / "tests/fixtures/charles_live/000.json")
    profile = copy.deepcopy(capture["profile"])
    profile["rules"]["pvp_mode"] = pvp
    live = sl.LiveSquareSolo()
    monkeypatch.setattr(live, "settled_profile", lambda script: profile)
    seen = {}

    def fake_anytime(lab, budget, **kwargs):
        seen.update(budget=budget, hold=lab.get("booster_hold"), clock=kwargs.get("clock"))
        return planner.Line(lab, [], []), {}

    monkeypatch.setattr(planner, "plan_anytime", fake_anytime)
    players = record["snapshot_state"]["players"]
    snapshot = {"board": record["board"], "special_board": record["special_board"], "slots": [],
                "state": {"moves": profile["state"]["moves"], "players": players,
                          "rules": {"pvp_mode": pvp}}}
    live.plan(None, snapshot, seconds=sl.CHARLES_PLAN_SECONDS, turn_time_left=60.0)
    assert 0.5 <= seen["budget"] <= sl.QUICK_PLAN_SECONDS
    assert not seen["hold"] and seen["clock"] is None
    assert live.carry is None and live.bg is None and not live.dynamic


@pytest.mark.parametrize("played, checked", [(1, True), (2, False)])
def test_expectation_is_checked_only_right_after_the_planned_action(monkeypatch, played, checked):
    """Showdown 2026-11-19 12:06:34 / 12:06:59: the bot played its own extras
    after a planned move, and the next plan called the board a refill miss."""
    import copy
    from pathlib import Path
    from tools.analyze_research import load

    root = Path(__file__).resolve().parents[1]
    record, capture = load(root / "tests/fixtures/charles_live/000.json")
    profile = copy.deepcopy(capture["profile"])
    live = sl.LiveSquareSolo()
    monkeypatch.setattr(live, "settled_profile", lambda script: profile)
    calls = []
    monkeypatch.setattr(live, "check_expectation", lambda *a: live.expectation and calls.append(a))
    monkeypatch.setattr(planner, "plan_anytime", lambda lab, budget, **kw: (planner.Line(lab, [], []), {}))
    live.expectation, live.played = object(), played
    snapshot = {"board": record["board"], "special_board": record["special_board"], "slots": [],
                "state": {"moves": profile["state"]["moves"], "players": record["snapshot_state"]["players"],
                          "rules": {"pvp_mode": 2}}}
    live.plan(None, snapshot, turn_time_left=60.0)
    assert bool(calls) is checked
