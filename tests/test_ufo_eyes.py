"""UFO SE eye ledger: per-turn activation index and the engine's own count."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import memory_gui  # noqa: E402
import move_strategy as ms  # noqa: E402

Tracker = memory_gui.UfoAbductionTracker


def me(energy, score=0, full=None, engine=None):
    frame = {
        "special_ability_type": 49,
        "index": 0,
        "energy": energy,
        "energy_to_ability": 7,
        "energy_full": (energy >= 7) if full is None else full,
        "score": score,
        "active_special_ability_type": 0,
        "special_ability_params": {
            "colorsToPickByActivation": "2,2,1",
            "maxPassiveActivates": "2",
            "allowPickingBlues": "False",
        },
    }
    if engine is not None:
        frame["special_ability_engine"] = engine
    return frame


def state(turn=1, moves=6, made=0, current=0):
    return {"turns": turn, "current_round": 1, "moves": moves,
            "moves_made_this_turn": made, "current_player_index": current}


def activate(tracker, st, score):
    tracker.observe(st, me(7, score))
    tracker.observe(st, me(0, score))


def test_activation_index_restarts_with_the_turn(monkeypatch):
    clock = {"t": 100.0}
    monkeypatch.setattr(memory_gui.time, "monotonic", lambda: clock["t"])
    t = Tracker()
    activate(t, state(turn=1), 10)
    assert t.eyes == 2
    clock["t"] += 20
    activate(t, state(turn=1), 20)
    assert t.eyes == 2
    clock["t"] += 20
    activate(t, state(turn=1), 30)
    assert t.eyes == 1                       # third activation this turn
    # Next turn: the first activation there arms the full two again.
    clock["t"] += 20
    activate(t, state(turn=2), 40)
    assert t.activations == 1
    assert t.eyes == 2


def test_engine_count_overrules_the_ledger_both_ways():
    t = Tracker()
    activate(t, state(), 10)
    assert t.eyes == 2
    # The engine says one eye already fired (the poll missed the move).
    t.observe(state(), me(0, 10, engine={"remaining_hud_eyes": 1, "colors_to_pick": 2,
                                          "colors_picked": 1, "passive_activates": 1}))
    assert t.eyes == 1
    assert t.engine_eyes == 1
    assert "engine" in t.reason
    # ... and the other way: ledger thinks nothing is armed, engine says two.
    t.eyes = 0
    t.observe(state(), me(0, 10, engine={"remaining_hud_eyes": 2, "colors_to_pick": 2,
                                          "colors_picked": 0, "passive_activates": 0}))
    assert t.eyes == 2
    assert t.state(me(0, 10)).eyes == 2


def test_engine_fallback_to_pick_minus_picked_and_passive_cap():
    t = Tracker()
    activate(t, state(), 10)
    t.observe(state(), me(0, 10, engine={"remaining_hud_eyes": None, "colors_to_pick": 2,
                                          "colors_picked": 2, "passive_activates": 2}))
    assert t.eyes == 0
    t.observe(state(), me(0, 10, engine={"remaining_hud_eyes": 1, "colors_to_pick": 2,
                                          "colors_picked": 1, "passive_activates": 2}))
    # Passive fires exhausted: no eye can fire even if one is still drawn.
    assert t.eyes == 0


def fields(passive):
    return {"colorsToPickByActivation": [2, 2, 1], "maxPassiveActivates": 2,
            "isRunningAsPassive": passive}


def test_eyes_are_spent_when_they_fire_not_per_move():
    t = Tracker()
    activate(t, state(), 10)
    assert t.eyes == 2
    # A swipe that matched one pickable colour; the engine's clock moves in
    # two steps and no eye fired yet.
    t.on_move_played(1)
    frame = me(0, 10)
    frame["special_ability_fields"] = fields(False)
    t.observe(state(moves=6, made=1), frame)
    t.observe(state(moves=5, made=1), frame)
    assert t.eyes == 2
    # The abduction animation runs: one eye gone, and it stays gone while the
    # flag is still up.
    frame["special_ability_fields"] = fields(True)
    t.observe(state(moves=5, made=1), frame)
    assert t.eyes == 1
    t.observe(state(moves=5, made=1), frame)
    assert t.eyes == 1
    frame["special_ability_fields"] = fields(False)
    t.observe(state(moves=5, made=1), frame)
    # Second fire, on the next single-colour swipe: none left.
    t.on_move_played(1)
    frame["special_ability_fields"] = fields(True)
    t.observe(state(moves=4, made=2), frame)
    assert t.eyes == 0
    assert "oko pucalo" in t.reason


def test_double_colour_swap_spends_both_eyes_in_one_run():
    # 2026-09-13 01:37:59 UTC: a swap matching orange and green with two eyes
    # armed; the single passive run at 01:38:03 took both colours.
    t = Tracker()
    activate(t, state(), 10)
    t.on_move_played(2)
    frame = me(0, 10)
    frame["special_ability_fields"] = fields(True)
    t.observe(state(moves=4, made=6), frame)
    assert t.eyes == 0


def test_fire_without_a_scored_move_spends_every_eye():
    # 2026-09-13 01:37:42 UTC: the Energy Boost perk's wipe fired both eyes
    # (colours 1 and 6 left together); the GUI never called on_move_played.
    t = Tracker()
    activate(t, state(), 10)
    frame = me(0, 10)
    frame["special_ability_fields"] = fields(True)
    t.observe(state(moves=6, made=1), frame)
    assert t.eyes == 0
    assert t.state(me(0, 10)).eyes == 0


def test_activation_seen_twice_in_a_row_counts_once(monkeypatch):
    clock = {"t": 100.0}
    monkeypatch.setattr(memory_gui.time, "monotonic", lambda: clock["t"])
    t = Tracker()
    t.observe(state(), me(7, 10))
    # Frame 1: the activation animation flag with the meter still full.
    frame = me(7, 10)
    frame["active_special_ability_type"] = 49
    t.observe(state(), frame)
    assert t.activations == 1
    clock["t"] += 0.4
    # Frame 2: the meter emptied -- the same activation.
    t.observe(state(), me(0, 10))
    assert t.activations == 1
    assert t.eyes == 2
    # A real second activation later still counts.
    clock["t"] += 20
    activate(t, state(), 20)
    assert t.activations == 2


def double_colour_swap():
    """Post-swap board: red line through the target (2,2), green column
    through the start (2,3), nothing else matched."""
    Y, P, O, G, R = ms.YELLOW, ms.PURPLE, ms.ORANGE, ms.GREEN, ms.RED
    board = [
        [Y, P, O, G, P],
        [P, O, Y, G, O],
        [R, R, R, G, Y],
        [O, Y, P, O, P],
        [P, O, Y, P, O],
    ]
    specials = [[ms.EMPTY] * 5 for _ in range(5)]
    return ms.MoveCandidate((2, 3), (2, 2), ms.Direction.LEFT, board, specials)


def abduction_events(result):
    return [e for e in result.intent_events if e["type"] == ms.UFO_ABDUCTION_EVENT]


def test_simulation_locks_every_armed_eye_on_the_swap_target_first():
    with ms.ufo_abduction_active(2):
        events = abduction_events(ms.simulate_candidate(double_colour_swap()))
    assert len(events) == 1
    assert events[0]["colors"] == [ms.RED, ms.GREEN]
    assert not events[0].get("ambiguous")


def test_simulation_with_one_eye_takes_only_the_dragged_colour():
    with ms.ufo_abduction_active(1):
        result = ms.simulate_candidate(double_colour_swap())
    events = abduction_events(result)
    assert len(events) == 1
    assert events[0]["colors"] == [ms.RED]
    # Destination order chooses red even though two colours matched.
    assert result.ufo_predicted_extra_moves == 0.0


def test_recorded_manual_extra_finds_purple_lock_then_orange_four():
    import json
    from pathlib import Path
    frame = json.loads((Path(__file__).parent / "fixtures/ufo_purple_orange_extra.json").read_text())
    with ms.ufo_abduction_active(1, False):
        ranked = ms.rank_extra_move_moves(frame["board"], frame["special_board"], mode=frame["mode"])
    assert ranked
    item = ranked[0]
    assert (item.candidate.start, item.candidate.target) == ((1, 0), (1, 1))
    assert item.ufo_directional_predicted_extra_moves == 0
    assert item.ufo_predicted_extra_moves == 0
    assert ms.has_reliable_same_move_extra(item)
    assert item.extra_moves == 1
    assert any(e.get("type") == ms.UFO_ABDUCTION_EVENT and e.get("colors") == [ms.PURPLE]
               for e in item.intent_events)
    assert any(e.get("type") == "match" and e.get("color") == ms.ORANGE and e.get("kind") == "four"
               for e in item.intent_events)
    with ms.ufo_abduction_active(0, False):
        assert not ms.rank_extra_move_moves(frame["board"], frame["special_board"], mode=frame["mode"])
    with ms.ufo_abduction_active(1, False):
        automatic = ms.prioritize_ranked_moves(ms.rank_moves(frame["board"], frame["special_board"]))
        assert automatic[0].candidate.start == (1, 0)
        assert automatic[0].candidate.target == (1, 1)
        board, specials = ms.swap_cells(frame["board"], frame["special_board"], (1, 1), (1, 0))
        reverse = ms.MoveCandidate((1, 1), (1, 0), ms.Direction.LEFT, board, specials)
        result = ms.simulate_candidate(reverse)
        assert abduction_events(result)[0]["colors"] == [ms.GREEN]
        assert result.extra_moves == 0


def test_reader_passes_the_engine_counters_through():
    # 2026-09-15 03:54: the agent read these on every manual dump, but the
    # host allowlist dropped the key, so the ledger kept a phantom eye and held
    # a full booster on the last move of the match.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
    import matchmasters_board_reader as reader

    raw = {"players": [dict(me(7, 90), name="someone", special_ability_engine={
        "remaining_hud_eyes": 0, "colors_to_pick": 2, "colors_picked": 2,
        "passive_activates": 1, "junk": "x", "flag": True})]}
    player = reader._safe_state(raw)["players"][0]
    assert "name" not in player
    assert player["special_ability_engine"] == {
        "remaining_hud_eyes": 0, "colors_to_pick": 2, "colors_picked": 2,
        "passive_activates": 1,
    }
    t = Tracker()
    t.eyes = 1
    t.observe(state(), player)
    assert t.eyes == 0 and t.engine_eyes == 0


def test_armed_eyes_never_hold_a_ready_booster():
    # Player, 2026-09-15: with eyes armed the booster still fires, unless the
    # move gives a guaranteed extra.
    import types
    import runtime

    plain = types.SimpleNamespace(direct_extra_moves=0, extra_moves=0, disco_moves=0,
                                  intent_events=[], cascade_matches=[])
    action, _chosen, gate = runtime.select_booster_action_with_gate([plain], True)
    assert action == "activate_booster"
    assert gate != "ufo_pending_eye_gate"
    extra = types.SimpleNamespace(direct_extra_moves=1, extra_moves=1, disco_moves=0,
                                  intent_events=[], cascade_matches=[])
    action, chosen, _gate = runtime.select_booster_action_with_gate([extra, plain], True)
    assert (action, chosen) == ("move", extra)


def test_status_line_says_where_the_count_came_from():
    t = Tracker()
    activate(t, state(), 10)
    status = memory_gui.MemoryWindow._ufo_eyes_status
    assert status(t, me(0, 10)) == "2 naoruzano  (procena)"
    t.observe(state(), me(0, 10, engine={"remaining_hud_eyes": 0, "colors_to_pick": 2,
                                          "colors_picked": 2, "passive_activates": 1}))
    assert status(t, me(0, 10)) == "0 naoruzano  (iz igre)"
    assert status(t, {"special_ability_type": 59}) == "-"


def test_plain_poll_leaves_the_ledger_alone():
    t = Tracker()
    activate(t, state(), 10)
    t.observe(state(), me(0, 10))
    assert t.eyes == 2
    assert t.engine_eyes is None


def test_engine_placeholder_before_first_use_arms_no_eyes():
    # Real snapshots read remaining_hud_eyes = colors_to_pick = 9 until the
    # first activation; that is not nine eyes, and must not become two.
    t = Tracker()
    placeholder = {"remaining_hud_eyes": 9, "colors_to_pick": 9,
                   "colors_picked": 0, "passive_activates": 0}
    t.observe(state(), me(0, 0, engine=placeholder))
    assert t.eyes == 0
    t.observe(state(), me(4, 10, engine=placeholder))
    assert t.eyes == 0
    # Same placeholder through the colors_to_pick - colors_picked fallback.
    t.observe(state(), me(4, 10, engine={"remaining_hud_eyes": None, "colors_to_pick": 9,
                                          "colors_picked": 0, "passive_activates": 0}))
    assert t.eyes == 0
    # A real activation then arms the two eyes the engine reports.
    activate(t, state(), 20)
    assert t.eyes == 2
    t.observe(state(), me(0, 20, engine={"remaining_hud_eyes": 2, "colors_to_pick": 2,
                                          "colors_picked": 0, "passive_activates": 0}))
    assert t.eyes == 2


def test_passive_eyes_take_blue_in_combo_order():
    """BeforeCombosDestroy + Take(n) do not read allowPickingBlues."""
    assert ms._ufo_abduction_colors([ms.BLUE], set(), 1) == [ms.BLUE]
    assert ms._ufo_abduction_colors([ms.BLUE, ms.RED], set(), 1) == [ms.BLUE]
    assert ms._ufo_abduction_colors([ms.RED, ms.BLUE], set(), 1) == [ms.RED]
    assert ms._ufo_abduction_colors([ms.BLUE, ms.RED], set(), 2) == [ms.BLUE, ms.RED]
    assert ms._ufo_abduction_colors([ms.RED, ms.RED], set(), 2) == [ms.RED]
    assert ms._ufo_abduction_colors([ms.BLUE], {ms.BLUE}, 1) == []


def test_one_eye_obeys_swipe_direction_even_when_destination_is_blue():
    candidate = double_colour_swap()
    board = [[ms.BLUE if value == ms.RED else value for value in row]
             for row in candidate.board]
    forward = ms.MoveCandidate(candidate.start, candidate.target,
                               candidate.direction, board, candidate.special_board)
    reverse = ms.MoveCandidate(candidate.target, candidate.start,
                               ms.Direction.RIGHT, board, candidate.special_board)
    for allow_blues in (False, True):
        with ms.ufo_abduction_active(1, allow_blues):
            assert abduction_events(ms.simulate_candidate(forward))[0]["colors"] == [ms.BLUE]
            assert abduction_events(ms.simulate_candidate(reverse))[0]["colors"] == [ms.GREEN]
        with ms.ufo_abduction_active(2, allow_blues):
            assert abduction_events(ms.simulate_candidate(forward))[0]["colors"] == [ms.BLUE, ms.GREEN]


def test_recorded_blue_destination_fills_the_meter_with_one_eye():
    import json
    cases = json.loads((Path(__file__).parent / "fixtures" /
                        "ufo_blue_destination.json").read_text(encoding="utf-8"))
    for case in cases:
        start, target = tuple(case["start"]), tuple(case["target"])
        board, specials = ms.swap_cells(case["board"], case["special_board"], start, target)
        candidate = ms.MoveCandidate(start, target, ms.Direction(case["direction"]), board, specials)
        with ms.ufo_abduction_active(1, False):
            result = ms.simulate_candidate(
                candidate, mode=case["mode"],
                allow_square_matches=case["allow_square_matches"],
                explode_created_specials_immediately=case["specials_explode_immediately"],
            )
        assert abduction_events(result)[0]["colors"] == [ms.BLUE], case["run"]
        assert min(case["charge_max"], case["charge_before"] + result.blue_cells) == case["charge_after"], case["run"]


def _simulate_fixture(case, eyes):
    start, target = tuple(case["start"]), tuple(case["target"])
    board, specials = ms.swap_cells(case["board"], case["special_board"], start, target)
    candidate = ms.MoveCandidate(start, target, ms.Direction(case["direction"]), board, specials)
    with ms.ufo_abduction_active(eyes):
        return ms.simulate_candidate(
            candidate, mode=case.get("mode", "None"),
            allow_square_matches=case.get("allow_square_matches", False),
            explode_created_specials_immediately=case.get("specials_explode_immediately", False),
        )


def test_recorded_two_eyes_are_spent_in_one_passive_fire():
    cases = json.loads((Path(__file__).parent / "fixtures" /
                        "ufo_two_eye_recorded.json").read_text(encoding="utf-8"))
    for case in cases:
        result = _simulate_fixture(case, case["eyes_before"])
        events = abduction_events(result)
        assert len(events) == case["engine_passive_activates"], case["run"]
        picked = len(events[0]["colors"])
        assert picked == case["engine_colors_picked"], case["run"]
        assert case["eyes_before"] - picked == case["engine_eyes_after"], case["run"]
        assert events[0]["colors"][0] == ms.BLUE


def test_natural_cascade_can_feed_second_eye_before_fire():
    cases = json.loads((Path(__file__).parent / "fixtures" /
                        "ufo_cascade_eye_cases.json").read_text(encoding="utf-8"))
    case = cases["natural_second"]
    result = _simulate_fixture(case, 2)
    locks = [event for event in result.intent_events if event["type"] == "ufo_color_lock"]
    assert [event["source"] for event in locks] == ["swap", "cascade"]
    assert abduction_events(result)[0]["colors"] == case["colors"]
    assert len(case["colors"]) == 2
    # The very same cascade cannot invent a second colour budget with one eye.
    assert abduction_events(_simulate_fixture(case, 1))[0]["colors"] == case["colors"][:1]


def test_abduction_cascades_cannot_feed_the_unspent_second_eye():
    cases = json.loads((Path(__file__).parent / "fixtures" /
                        "ufo_cascade_eye_cases.json").read_text(encoding="utf-8"))
    case = cases["after_fire"]
    result = _simulate_fixture(case, 2)
    assert len(abduction_events(result)) == 1
    assert abduction_events(result)[0]["colors"] == case["colors"]
    fire_index = next(i for i, event in enumerate(result.intent_events)
                      if event["type"] == ms.UFO_ABDUCTION_EVENT)
    following = result.intent_events[fire_index + 1:]
    assert any(event["type"] == "match" and event["color"] not in case["colors"]
               for event in following)
    assert not any(event["type"] == "ufo_color_lock" for event in following)


def test_reader_preserves_bounded_engine_colour_order():
    from tools.matchmasters_board_reader import _safe_player
    # These are native SlotColor enum values, not the simulator colour IDs.
    player = _safe_player({"ufo_colors_exploded_this_move": [4, 3, 5, "private", True, -1, 300]})
    assert player["ufo_colors_exploded_this_move"] == [4, 3, 5]
    assert _safe_player({"ufo_colors_exploded_this_move": None})["ufo_colors_exploded_this_move"] is None


def test_special_swap_second_eye_takes_the_other_special():
    # Recorded boards 212038/006, 231940/005, 234242/002 settle the colours; this
    # fixture only supplies a two-colour bomb swap (dragged 6, other 4).
    cases = json.loads((Path(__file__).parent / "fixtures" /
                        "ufo_cascade_eye_cases.json").read_text(encoding="utf-8"))
    case = cases["special_swap"]
    start, target = tuple(case["start"]), tuple(case["target"])
    board, specials = ms.swap_cells(case["board"], case["special_board"], start, target)
    candidate = ms.MoveCandidate(start, target, ms.Direction(case["direction"]), board, specials)
    with ms.ufo_abduction_active(2):
        result = ms._simulate_special_swap_candidate(candidate, original_board=case["board"])
    assert len(abduction_events(result)) == 1
    assert abduction_events(result)[0]["colors"] == [6, 4]
    assert not any(event["type"] == "ufo_color_lock" and event["source"] == "cascade"
                   for event in result.intent_events)


def test_laser_ray_victim_colours_match_the_recorded_engine_order():
    cases = json.loads((Path(__file__).parent / "fixtures" /
                        "ufo_laser_engine_verified.json").read_text(encoding="utf-8"))
    assert len(cases) == 7
    for case in cases:
        result = _simulate_fixture(case, case["eyes"])
        colours = [colour for event in abduction_events(result)
                   for colour in event["colors"]]
        assert colours == case["expected_colors"], case["run"]
        assert case["eyes"] - len(colours) == case["eyes_after"], case["run"]
        headroom = max(0, case["charge_max"] - case["charge_before"])
        assert min(headroom, result.blue_cells) == case["charge_gained"], case["run"]
        if case["run"] == "2026-10-28_07-51-39_716":
            locks = [event for event in result.intent_events if event["type"] == "ufo_color_lock"]
            assert locks[0]["source"] == "swap_and_laser"
            assert locks[0]["colors"] == [ms.RED, ms.ORANGE]
            assert locks[0]["cascade"] == 1
            assert result.blue_cells == 4
