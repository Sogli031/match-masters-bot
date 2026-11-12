"""Panel "Dopuna": tekstovi stanja i provera u posebnom procesu."""
import json
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from refill_monitor import RefillMonitorClient, RefillTally

ROOT = Path(__file__).resolve().parents[1]
RECORDING = ROOT / "Debug/research/20261102_211420_column-mania"
HOT_RECORDING = ROOT / "Debug/research/20261102_212038_hot-color"
UFO_RECORDING = ROOT / "Debug/research/20261102_225912_hot-color"


def test_usage_says_why_the_bot_is_not_using_the_refill():
    tally = RefillTally()
    assert "cekam" in tally.usage_text()
    assert tally.add({"usage": {"active": True, "reason": None}}) is None
    assert tally.usage_text() == "Dopuna: RADI u ovom potezu (u partiji: sa dopunom 1, bez 0)"
    tally.add({"usage": {"active": False, "reason": "tabla jos nije mirna"}})
    assert tally.usage_text() == ("Dopuna: NE u ovom potezu - memorija nije procitana: "
                                  "tabla jos nije mirna (u partiji: sa dopunom 1, bez 1)")


def test_usage_tells_this_move_from_an_unsupported_mode():
    tally = RefillTally()
    tally.add({"usage": {"active": False, "reason": "ovaj potez je booster"}})
    assert tally.usage_text().startswith("Dopuna: NE u ovom potezu - ovaj potez je booster")
    tally.add({"usage": {"active": False, "reason": "Froggy lotus na tabli: dopuna ne racuna vrednost lotusa"}})
    assert "NE u ovom potezu - Froggy lotus" in tally.usage_text()
    tally.add({"usage": {"active": False, "reason": "Special tile spawning: tile values [19, 41]"}})
    assert tally.usage_text().startswith(
        "Dopuna: NE u ovom potezu - greska u dopuni: specijalna polja u dopuni nisu preneta (polja [19, 41])")
    tally.add({"usage": {"active": False, "reason": "dopuna nije uspela: Dustville cascade special"}})
    assert "NE u ovom potezu - nepredvidiv efekat: Dustville" in tally.usage_text()
    tally.add({"usage": {"active": False, "reason": "iskljuceno prekidacem"}})
    assert tally.usage_text() == "Dopuna: ISKLJUCENA prekidacem"


def test_usage_names_the_approximate_fallback():
    tally = RefillTally()
    tally.add({"usage": {"active": True, "reason": None,
                         "approximate": "Candy World: candy conversion is not ported"}})
    assert tally.usage_text() == ("Dopuna: RADI PRIBLIZNO u ovom potezu - Candy World: nova bombona "
                                  "iz dopune nije preneta (u partiji: sa dopunom 1, bez 0)")
    tally.add({"usage": {"active": True, "reason": None, "approximate": None}})
    assert tally.usage_text().startswith("Dopuna: RADI u ovom potezu")


def test_runtime_names_the_skipped_move():
    import runtime
    from types import SimpleNamespace as NS

    request = NS(points_only=False, solo_cross_only=False)
    reason = runtime.exact_refill_skip_reason
    assert reason("activate_booster", request) == "ovaj potez je booster"
    assert reason("activate_perk", request) == "ovaj potez je perk"
    assert reason("move", request, lotus=True).startswith("Froggy lotus")
    assert reason("move", NS(points_only=True, solo_cross_only=False)).startswith("Least Points")
    assert reason("move", request, mixy=True).startswith("Mixy kod")


class _FakeModel:
    def __init__(self):
        self.resets = 0

    def clone(self):
        return self

    def reset_action(self):
        self.resets += 1


def test_each_candidate_starts_from_the_live_rng_and_only_on_the_root_board():
    from engine_refill import ExactRefillSession

    model = _FakeModel()
    session = ExactRefillSession(model, [[1, 2], [3, 4]])
    assert session.begin([[1, 2], [3, 4]]) and session.begin([[1, 2], [3, 4]])
    assert not session.begin([[9, 2], [3, 4]])
    assert session.simulations == 2 and model.resets == 2


@pytest.fixture(autouse=True)
def _fast_mode_available(monkeypatch):
    # These tests pin the fast mode FULL_EXACT_REFILL_EVERYWHERE can bring back.
    import memory_gui
    monkeypatch.setattr(memory_gui, "FULL_EXACT_REFILL_EVERYWHERE", False)


def _solo_window(refill_on, relaxed=True):
    import memory_gui

    window = SimpleNamespace(_refill_on=refill_on, _relaxed_turn_clock=lambda rules: relaxed)
    window._is_solo_challenge = lambda state: memory_gui.MemoryWindow._is_solo_challenge(window, state)
    window._strategy_mode = memory_gui.MemoryWindow._strategy_mode
    window._full_exact_refill = lambda state: memory_gui.MemoryWindow._full_exact_refill(window, state)
    return window, memory_gui


def test_auto_waits_for_the_board_record_but_not_forever(monkeypatch):
    import memory_gui

    clock = [100.0]
    monkeypatch.setattr(memory_gui.time, "monotonic", lambda: clock[0])
    window = SimpleNamespace(_refill_on=True, _research_on=False, _reader_script=object(),
                             _research_done_signature=None, _record_wait_signature=None, _record_wait_started=0.0,
                             _is_solo_challenge=lambda state: True)
    waits = lambda: memory_gui.MemoryWindow._waits_for_board_record(window, {"signature": "a"})
    assert waits()
    clock[0] += memory_gui.BOARD_RECORD_WAIT_SECONDS
    assert not waits()
    window._record_wait_signature = None
    assert waits()
    window._research_done_signature = "a"
    assert not waits()
    window._research_done_signature, window._refill_on = None, False
    assert not waits()


def test_exact_refill_waits_for_the_settled_board_in_solo_challenge_and_versus():
    solo = {"is_singleplayer_board": True, "players": [{}], "rules": {}}
    window, memory_gui = _solo_window(True)
    assert not memory_gui.MemoryWindow._prepares_ahead(window, solo)
    # Showdown (timed solo board) computes during the animation.
    window, _ = _solo_window(True, relaxed=False)
    assert memory_gui.MemoryWindow._prepares_ahead(window, solo)
    # A 1v1 Versus waits for rest and ranks with the exact refill.
    window, _ = _solo_window(True)
    assert not memory_gui.MemoryWindow._prepares_ahead(window, {**solo, "players": [{}, {}]})
    # Party / Rumble (pvpMode 2) with two boards on screen stays fast.
    rumble = {**solo, "players": [{}, {}], "rules": {"pvp_mode": 2}}
    assert memory_gui.MemoryWindow._prepares_ahead(window, rumble)
    window, _ = _solo_window(False)
    assert memory_gui.MemoryWindow._prepares_ahead(window, solo)


@pytest.mark.parametrize("rumble_type", [1, 2, 3])
def test_timed_races_prepare_ahead_with_full_exact_default(monkeypatch, rumble_type):
    window, memory_gui = _solo_window(True, relaxed=False)
    monkeypatch.setattr(memory_gui, "FULL_EXACT_REFILL_EVERYWHERE", True)
    race = {"is_singleplayer_board": True, "players": [{}],
            "rules": {"pvp_mode": 2, "rumble_type": rumble_type}}
    assert memory_gui.MemoryWindow._fast_refill(window, race)
    assert memory_gui.MemoryWindow._prepares_ahead(window, race)
    versus = {"players": [{}, {}], "rules": {"pvp_mode": 0}}
    assert not memory_gui.MemoryWindow._fast_refill(window, versus)


def test_auto_off_computation_waits_for_the_settled_board_in_solo_challenge():
    import memory_gui

    def waits(prepares, stable, phase_open, cleo=False):
        window = SimpleNamespace(_prepares_ahead=lambda state: prepares,
                                 _engine_move_phase_open=lambda snapshot: phase_open,
                                 _reader_script=object())
        window._cleo_needs_rest = lambda snapshot: memory_gui.MemoryWindow._cleo_needs_rest(window, snapshot)
        special = [[memory_gui.SPECIAL_CLEO_BUG if cleo else 0]]
        return memory_gui.MemoryWindow._waits_for_settled_board(
            window, {"stable": stable, "state": {}, "special_board": special})

    assert waits(False, True, False) and waits(False, False, True)
    assert not waits(False, True, True)
    assert not waits(True, False, False)
    # A Cleo board waits for rest even where the rest is planned ahead: its
    # odds come from memory read at rest (84% mid-animation vs 49%, 2026-11-07).
    assert waits(True, False, False, cleo=True)
    assert not waits(True, True, True, cleo=True)


def _pick(monkeypatch, moves, next_extra=(), blue_missing=99):
    """moves: {name: (extra, blue)}; next_extra: boards that leave an extra."""
    import move_strategy as ms

    def simulate(board, candidate, *args):
        if board == "root":
            extra, blue = moves[candidate.start]
            return SimpleNamespace(extra_moves=extra, blue_cells=blue, board=candidate.start, special_board=None)
        return SimpleNamespace(extra_moves=1 if candidate.start == "next-extra" else 0)

    monkeypatch.setattr(ms, "_simulate_created_candidate_cached", simulate)
    monkeypatch.setattr(ms, "generate_candidates", lambda board, special: [
        SimpleNamespace(start="next-extra" if board in next_extra else "plain", target="t")])
    session = SimpleNamespace(knows=lambda board: True, blue_missing=blue_missing)
    evaluations = [SimpleNamespace(candidate=SimpleNamespace(start=name, target="t")) for name in moves]
    with ms.exact_refill_active(session):
        pick = ms.exact_refill_choice(evaluations, "root", None)
    return None if pick is None else (pick[0].candidate.start, pick[1])


def test_extra_comes_first(monkeypatch):
    assert _pick(monkeypatch, {"a": (0, 6), "b": (1, 0)}) == ("b", "extra")


def test_a_swaps_extra_goes_before_a_balls(monkeypatch):
    import move_strategy as ms

    results = {"ball": SimpleNamespace(extra_moves=1, disco_moves=1, blue_cells=4),
               "swap": SimpleNamespace(extra_moves=1, disco_moves=0, blue_cells=0)}
    monkeypatch.setattr(ms, "_simulate_created_candidate_cached",
                        lambda board, candidate, *args: results[candidate.start])
    session = SimpleNamespace(knows=lambda board: True, blue_missing=99)
    evaluation = lambda name: SimpleNamespace(candidate=SimpleNamespace(start=name, target="t"))
    with ms.exact_refill_active(session):
        pick = ms.exact_refill_choice([evaluation("ball"), evaluation("swap")], "root", None)
        assert (pick[0].candidate.start, pick[1]) == ("swap", "extra")
        pick = ms.exact_refill_choice([evaluation("ball")], "root", None)
        assert (pick[0].candidate.start, pick[1]) == ("ball", "extra")


def test_blue_comes_before_a_setup(monkeypatch):
    assert _pick(monkeypatch, {"a": (0, 0), "b": (0, 4)}, next_extra=("a",)) == ("b", "plave")


def test_setup_breaks_a_blue_tie_and_stands_alone(monkeypatch):
    assert _pick(monkeypatch, {"a": (0, 3), "b": (0, 3)}, next_extra=("b",)) == ("b", "plave i namestanje")
    assert _pick(monkeypatch, {"a": (0, 0), "b": (0, 0)}, next_extra=("b",)) == ("b", "namestanje")


def test_full_booster_ignores_blue_and_nothing_special_keeps_the_bots_pick(monkeypatch):
    assert _pick(monkeypatch, {"a": (0, 0), "b": (0, 5)}, blue_missing=0) is None
    assert _pick(monkeypatch, {"a": (0, 3), "b": (0, 5)}, blue_missing=3) == ("a", "plave")


def test_last_move_plays_for_points_unless_it_gives_an_extra(monkeypatch):
    import move_strategy as ms

    def pick(moves, moves_left):
        monkeypatch.setattr(ms, "_simulate_created_candidate_cached", lambda board, candidate, *args: SimpleNamespace(
            extra_moves=moves[candidate.start][0], blue_cells=moves[candidate.start][1], board="after", special_board=None))
        monkeypatch.setattr(ms, "generate_candidates", lambda board, special: [])
        session = SimpleNamespace(knows=lambda board: True, blue_missing=7, moves_left=moves_left)
        evaluations = [SimpleNamespace(candidate=SimpleNamespace(start=name, target="t")) for name in moves]
        with ms.exact_refill_active(session):
            return ms.exact_refill_choice(evaluations, "root", None)

    assert pick({"a": (0, 0), "b": (0, 5)}, 1) is None
    assert pick({"a": (0, 0), "b": (1, 0)}, 1)[1] == "extra"
    assert pick({"a": (0, 0), "b": (0, 5)}, 2)[1] == "plave"


def test_no_session_means_no_override():
    import move_strategy as ms

    assert ms.exact_refill_choice([object()], [[1]], [[0]]) is None


def test_usage_is_reported_when_the_search_finishes_not_on_the_click():
    from dataclasses import dataclass, field
    import memory_gui

    @dataclass
    class Request:
        wait_for_board: object = None

    reports = []
    window = SimpleNamespace(_report_exact_refill=lambda session, reason: reports.append(reason))
    request, usage = memory_gui.MemoryWindow._report_when_computed(window, Request(lambda: "held"), None, "x")
    assert reports == [] and not usage["reported"]
    assert request.wait_for_board() == "held"
    assert reports == ["x"] and usage["reported"]
    plain, usage = memory_gui.MemoryWindow._report_when_computed(window, Request(), None, "y")
    assert plain.wait_for_board is None and not usage["reported"]


def test_a_search_on_a_moving_board_reports_only_if_its_move_is_played():
    # Hot Color 2026-11-12 00:55:21: the search after a booster was cancelled
    # in its wait, yet counted as a move "without the refill".
    from dataclasses import dataclass
    import memory_gui

    @dataclass
    class Request:
        wait_for_board: object = None

    reports = []
    window = SimpleNamespace(_report_exact_refill=lambda session, reason: reports.append(reason))
    request, usage = memory_gui.MemoryWindow._report_when_computed(
        window, Request(lambda: "held"), None, "tabla jos nije mirna")
    assert request.wait_for_board() == "held"
    assert reports == [] and not usage["reported"]


def _plan_key(left, moves=6):
    import memory_gui

    check = SimpleNamespace(isChecked=lambda: False)
    window = SimpleNamespace(
        turn_time_left=lambda state: left, BoosterImmediateCheck=check, BlueRushCheck=check, PerksCheck=check,
        _used_perk_slots=set(), _booster_action=None, _board_profile=None, _score_legend=None,
        _low_on_turn_time=lambda state: False)
    return memory_gui.MemoryWindow._auto_plan_key(window, {"board": [[1]], "state": {"moves": moves}})


def test_long_clock_does_not_restart_the_search_but_a_short_one_does():
    assert _plan_key(1400.0) == _plan_key(1390.0)
    assert _plan_key(60.0) != _plan_key(50.0)


def test_plan_key_difference_names_what_changed():
    from auto_plan import plan_key_difference

    old = json.dumps({"board": [[1]], "state": {"moves": 5}, "policy": [1]})
    new = json.dumps({"board": [[1]], "state": {"moves": 4}, "policy": [2]})
    assert plan_key_difference(old, new) == ["policy", "state.moves"]
    assert plan_key_difference("x", new) == ["plan ponisten"]


def test_move_worker_names_resolve():
    """The worker closure runs on a thread; a bad name there fails every move."""
    import memory_gui

    code = next(c for c in memory_gui.MemoryWindow._play.__code__.co_consts
                if getattr(c, "co_name", "") == "worker")
    for name in ("exact_refill_active", "run_check_best_move_request", "square_solo_live"):
        assert name in code.co_names and hasattr(memory_gui, name)


def test_failed_refill_leaves_the_holes_like_the_plain_ranking():
    from engine_refill import ExactRefillSession

    session = ExactRefillSession(_FakeModel(), [[1]])
    session.begin([[1]])
    assert session.refill([[0]], [[0]]) == ([[0]], [[0]])
    assert session.failure


def test_moving_board_goes_without_the_refill_and_without_reading_memory():
    from square_solo_live import exact_refill_session

    reader = SimpleNamespace(read_profile=lambda script: pytest.fail("ne sme da cita memoriju"))
    moving = {"stable": True, "state": {"game_state": -6, "chain_reaction": 0}}
    assert exact_refill_session(reader, object(), moving, [[1]]) == (None, "tabla jos nije mirna")


def test_second_eye_reads_the_first_special_right_to_left_from_the_top():
    import move_strategy as ms

    board = [[1, 2, 3], [4, 5, 6], [7, 8, 9]]
    match = SimpleNamespace(cells={(0, 0)})
    events = [
        {"type": "match"},
        {"type": "special_activation", "effect_cells": [(0, 0), (0, 1), (1, 2), (2, 2)]},
        {"type": "special_activation", "effect_cells": [(2, 0)]},
        {"type": "special_activation"},
    ]
    assert ms._ufo_blast_colors(board, events, [match]) == [6, 9, 2, 7]


def test_ufo_player_is_tried_with_each_eye_count():
    import move_strategy as ms
    import refill_monitor

    seen = []

    def attempt(capture, want):
        seen.append(ms.ufo_eyes())
        if ms.ufo_eyes() == 1:
            return [("potez", None)], None, {}
        return [], {"distance": 5}, {}

    record = {"snapshot_state": {"players": [{"player_type": 0, "special_ability_type": 49}]}}
    matches, _, _, eyes = refill_monitor._try_with_ufo_eyes(record, {}, attempt, lambda r: {})
    assert matches and eyes == 1 and seen == [0, 1]
    seen.clear()
    record["snapshot_state"]["players"][0]["special_ability_type"] = 45
    matches, closest, _, eyes = refill_monitor._try_with_ufo_eyes(record, {}, attempt, lambda r: {})
    assert not matches and eyes == 0 and seen == [0] and closest == {"distance": 5}


def test_billie_drone_without_raw_data_keeps_the_plain_ranking():
    from square_solo_live import exact_refill_session

    reader = SimpleNamespace(read_profile=lambda script: {"state": {"moves": 5}})
    snapshot = {"stable": True, "special_board": [[0, 14]], "state": {"game_state": -5, "chain_reaction": 0, "moves": 5}}
    session, reason = exact_refill_session(reader, object(), snapshot, [[1, -1]])
    assert session is None and reason


@pytest.mark.skipif(not HOT_RECORDING.exists(), reason="snimak partije nije na ovom racunaru")
def test_ordinary_ranking_sees_the_drop_on_a_recorded_board():
    import move_strategy as ms
    from engine_refill import EngineRefill, ExactRefillSession

    record = json.loads((HOT_RECORDING / "000.json").read_text(encoding="utf-8"))
    session = ExactRefillSession(EngineRefill.from_profile(record["profile"]), record["board"])
    with ms.exact_refill_active(session):
        ranked = ms.rank_moves(record["board"], record["special_board"], mode="Hot Color", lookahead_depth=3)
    assert ranked and session.simulations and session.failure is None
    assert ms._EXACT_REFILL is None and ms._ENGINE_REFILL is None


def test_tally_counts_only_checkable_moves_as_hits():
    tally = RefillTally()
    assert "cekam" in tally.data_text()
    assert "nema proverljivih" in tally.hit_text()
    data = {"level": "ima", "text": "tacna formula"}
    tally.add({"title": "Column Mania", "data": data, "move": None})
    assert tally.data_text() == "Podaci za Column Mania: IMA (tacna formula)"
    for verdict in ("ok", "ok", "ok", "miss", "booster", "unsupported", "gap"):
        line = tally.add({"data": data, "move": {"verdict": verdict, "detail": "x"}})
        assert line.endswith(": x")
    assert tally.hit_text() == "Pogadja: 3 od 4 (75%), neproverljivih 3"
    assert tally.add({"error": "pao"}) == "provera: pao"


def test_only_a_miss_is_saved(monkeypatch, tmp_path):
    import refill_monitor
    import simulator_capture
    from strategy_lab import simulation

    monkeypatch.setattr(refill_monitor, "MISS_DIR", tmp_path)
    monkeypatch.setattr(simulator_capture, "capture_mode", lambda profile: SimpleNamespace(value="x"))
    monkeypatch.setattr(simulation, "PREFIX_MODES", set())
    monkeypatch.setattr(refill_monitor, "data_state", lambda record: {"level": "ima", "text": ""})
    record = {"profile": {"rules": {"id": "hot-color"}, "rng": {"_seed": 1}}, "board": [[1]]}
    verdicts = iter(({"verdict": "ok", "detail": "a"}, {"verdict": "gap", "detail": ""}, {"verdict": "miss", "detail": "b"}))
    monkeypatch.setattr(refill_monitor, "check_transition", lambda a, b: next(verdicts))
    checker = refill_monitor.TransitionChecker()
    for _ in range(3):
        checker.handle(record)
    assert list(tmp_path.iterdir()) == []
    answer = checker.handle(record)
    assert answer["move"]["detail"].startswith("b, snimljeno ")
    saved = list(tmp_path.iterdir())
    assert len(saved) == 1 and saved[0].name.endswith("_hot-color")
    assert sorted(p.name for p in saved[0].iterdir()) == ["000.json", "001.json"]


def test_special_tile_values_map_to_simulator_specials():
    from engine_refill import ENGINE_SPECIAL_TO_SIM

    assert ENGINE_SPECIAL_TO_SIM[6] == 3 and ENGINE_SPECIAL_TO_SIM[23] == 11 and ENGINE_SPECIAL_TO_SIM[0] == 0


class _CountingModel:
    def __init__(self, counter=0):
        self.counter = counter
        self.rng = self

    def clone(self):
        return _CountingModel(self.counter)

    def reset_action(self):
        pass

    def next(self):
        self.counter += 1


def _result(board, cleared=None):
    return SimpleNamespace(board=board, cleared_color_counts=cleared or {})


def test_line_continues_from_the_move_that_produced_the_board():
    from engine_refill import ExactRefillSession

    session = ExactRefillSession(_CountingModel(5), [[1]])
    assert session.begin([[1]]) and not session.knows([[2]])
    session.current.counter = 9
    session.finish(_result([[2]]))
    assert session.knows([[2]]) and session.begin([[2]]) and session.current.counter == 9


def test_lines_stop_after_max_plies_and_with_other_players():
    from engine_refill import ExactRefillSession

    session = ExactRefillSession(_CountingModel(), [[1]], max_plies=1)
    session.begin([[1]])
    session.finish(_result([[2]]))
    session.begin([[2]])
    session.finish(_result([[3]]))
    assert not session.knows([[3]])
    versus = ExactRefillSession(_CountingModel(), [[1]], follow_moves=False)
    versus.begin([[1]])
    versus.finish(_result([[2]]))
    assert not versus.knows([[2]])


def test_hot_color_rotation_costs_two_draws_and_then_the_colour_is_unknown():
    from engine_refill import ExactRefillSession

    session = ExactRefillSession(_CountingModel(), [[1]], hot=(5, 3), max_plies=9)
    session.begin([[1]])
    session.finish(_result([[2]], {4: 3}))      # hot colour not cleared: no draws
    assert session.states[((2,),)][0].counter == 0 and session.states[((2,),)][1] == (5, 3)
    session.begin([[2]])
    session.finish(_result([[3]], {5: 3}))
    assert session.states[((3,),)][0].counter == 2 and session.states[((3,),)][1] == (3, None)
    session.begin([[3]])
    session.finish(_result([[4]], {3: 3}))
    assert session.states[((4,),)][1] == (None, None)
    session.begin([[4]])
    session.finish(_result([[5]]))
    assert not session.knows([[5]])


@pytest.mark.skipif(not UFO_RECORDING.exists(), reason="snimak partije nije na ovom racunaru")
def test_armed_ufo_eyes_are_predicted(monkeypatch, tmp_path):
    import refill_monitor
    from refill_monitor import TransitionChecker

    monkeypatch.setattr(refill_monitor, "MISS_DIR", tmp_path)
    checker, tally = TransitionChecker(), RefillTally()
    for path in sorted(UFO_RECORDING.glob("[0-9][0-9][0-9].json")):
        tally.add(checker.handle(json.loads(path.read_text(encoding="utf-8"))))
    assert tally.counts["ok"] >= 22
    assert tally.counts["miss"] <= 3


@pytest.mark.skipif(not HOT_RECORDING.exists(), reason="snimak partije nije na ovom racunaru")
def test_hot_color_recording_predicts_boards(monkeypatch, tmp_path):
    import refill_monitor
    from refill_monitor import TransitionChecker

    monkeypatch.setattr(refill_monitor, "MISS_DIR", tmp_path)
    checker, tally = TransitionChecker(), RefillTally()
    for path in sorted(HOT_RECORDING.glob("[0-9][0-9][0-9].json")):
        tally.add(checker.handle(json.loads(path.read_text(encoding="utf-8"))))
    assert tally.data["level"] == "ima"
    assert tally.counts["ok"] == 20     # this match is UFO: 5 moves hit only with the eye, 1 is a Teleport
    assert tally.counts["miss"] == 0


CRYSTAL_RECORDING = RECORDING.parent / "20261103_005008_color-crystals"
DISCO_RECORDING = RECORDING.parent / "20261103_005457_drill-down"


@pytest.mark.skipif(not DISCO_RECORDING.exists(), reason="snimak partije nije na ovom racunaru")
def test_disco_ball_keeps_its_colour_for_the_refill():
    from engine_refill import color_maps
    from refill_monitor import check_transition
    from simulator_capture import capture_mode
    from strategy_lab import simulation

    before = json.loads((DISCO_RECORDING / "002.json").read_text(encoding="utf-8"))
    after = json.loads((DISCO_RECORDING / "003.json").read_text(encoding="utf-8"))
    original = set(simulation.PREFIX_MODES)
    simulation.PREFIX_MODES = original | {capture_mode(before["profile"]).value}
    try:
        assert check_transition(before, after)["verdict"] == "miss"     # colour not read
        to_engine = color_maps(before["profile"])[0]
        before["profile"]["ball_slots"] = [{"row": 1, "col": 4, "color": to_engine[4]},
                                           {"row": 4, "col": 0, "color": to_engine[1]}]
        assert check_transition(before, after)["verdict"] == "ok"
    finally:
        simulation.PREFIX_MODES = original


SPENT_BALL_RECORDING = RECORDING.parent / "20261103_010847_drill-down"
MUSHROOM_RECORDING = RECORDING.parent / "20261103_013455_drill-down"


@pytest.mark.skipif(not MUSHROOM_RECORDING.exists(), reason="snimak partije nije na ovom racunaru")
def test_mushroom_board_has_refill_data():
    from refill_monitor import data_state

    record = json.loads((MUSHROOM_RECORDING / "000.json").read_text(encoding="utf-8"))
    assert data_state(record)["level"] == "ima"


@pytest.mark.skipif(not SPENT_BALL_RECORDING.exists(), reason="snimak partije nije na ovom racunaru")
def test_ball_falling_onto_a_spent_ball_keeps_its_own_colour():
    from refill_monitor import check_transition
    from simulator_capture import capture_mode
    from strategy_lab import simulation

    before = json.loads((SPENT_BALL_RECORDING / "010.json").read_text(encoding="utf-8"))
    after = json.loads((SPENT_BALL_RECORDING / "011.json").read_text(encoding="utf-8"))
    original = set(simulation.PREFIX_MODES)
    simulation.PREFIX_MODES = original | {capture_mode(before["profile"]).value}
    try:
        assert check_transition(before, after)["verdict"] == "ok"
    finally:
        simulation.PREFIX_MODES = original


@pytest.mark.skipif(not SPENT_BALL_RECORDING.exists(), reason="snimak partije nije na ovom racunaru")
def test_ball_dragged_onto_a_special_fires_it_on_its_own_cell():
    from refill_monitor import check_transition
    from simulator_capture import capture_mode
    from strategy_lab import simulation

    before = json.loads((SPENT_BALL_RECORDING / "009.json").read_text(encoding="utf-8"))
    after = json.loads((SPENT_BALL_RECORDING / "010.json").read_text(encoding="utf-8"))
    original = set(simulation.PREFIX_MODES)
    simulation.PREFIX_MODES = original | {capture_mode(before["profile"]).value}
    try:
        assert check_transition(before, after)["verdict"] == "ok"
    finally:
        simulation.PREFIX_MODES = original


@pytest.mark.skipif(not DISCO_RECORDING.exists(), reason="snimak partije nije na ovom racunaru")
def test_disco_ball_drills_its_own_column_in_drillin_down():
    from refill_monitor import check_transition
    from simulator_capture import capture_mode
    from strategy_lab import simulation

    before = json.loads((DISCO_RECORDING / "013.json").read_text(encoding="utf-8"))
    after = json.loads((DISCO_RECORDING / "014.json").read_text(encoding="utf-8"))
    original = set(simulation.PREFIX_MODES)
    simulation.PREFIX_MODES = original | {capture_mode(before["profile"]).value}
    try:
        assert check_transition(before, after)["verdict"] == "ok"
    finally:
        simulation.PREFIX_MODES = original


@pytest.mark.skipif(not CRYSTAL_RECORDING.exists(), reason="snimak partije nije na ovom racunaru")
def test_color_crystals_recording_predicts_boards(monkeypatch, tmp_path):
    import refill_monitor
    from refill_monitor import TransitionChecker

    monkeypatch.setattr(refill_monitor, "MISS_DIR", tmp_path)
    checker, tally = TransitionChecker(), RefillTally()
    for path in sorted(CRYSTAL_RECORDING.glob("[0-9][0-9][0-9].json")):
        tally.add(checker.handle(json.loads(path.read_text(encoding="utf-8"))))
    assert tally.data["level"] == "ima"
    assert tally.counts["miss"] == 1    # 015->016, right after a perk
    assert tally.counts["ok"] == 20     # one is a Teleport


@pytest.mark.skipif(not RECORDING.exists(), reason="snimak partije nije na ovom racunaru")
def test_real_process_replays_a_recorded_match(monkeypatch, tmp_path):
    monkeypatch.setenv("REFILL_MISS_DIR", str(tmp_path))
    answers, done = [], threading.Event()
    files = sorted(RECORDING.glob("[0-9][0-9][0-9].json"))

    def on_answer(answer):
        answers.append(answer)
        if len(answers) == len(files) or answer.get("error"):
            done.set()

    client = RefillMonitorClient(on_answer)
    try:
        for path in files:
            client.send(json.loads(path.read_text(encoding="utf-8")))
        assert done.wait(240)
    finally:
        client.close()
    assert not [a for a in answers if a.get("error")]
    tally = RefillTally()
    for answer in answers:
        tally.add(answer)
    assert tally.data["level"] == "ima"
    # 25 -> 26: a cascade square's crosshair counted clockwise (2026-11-07).
    assert tally.counts["ok"] == 26     # a resting lightning no longer hides the move
    # 021->022: nearest checkable swipe 191 draws off, two random-target
    # swipes on the board -- not checkable rather than a miss (2026-11-06).
    # The last miss (031->032) was a cascade square, fixed 2026-11-07.
    assert tally.counts["miss"] == 0
    assert tally.counts["booster"] == 6
    assert not list(tmp_path.iterdir())


def test_cleo_booster_figure_is_named_not_reported_as_missing_slots():
    """Cleo Cadabra's own figure keeps its logic under the ability; the check
    said "raw slots missing" for every one (2026-11-07 17:19-17:23)."""
    from engine_cleo import CleoPieceModel
    from engine_refill import UnsupportedRefill
    from refill_monitor import _translated

    profile = {"cleo_piece_logic": None, "raw_slots": [{"row": 0, "col": 0}],
               "cleo_booster_fields": {"BoosterPiecesLogic": {"cloneToWholeColor": True}}}
    with pytest.raises(UnsupportedRefill, match="Cleo booster figure") as raised:
        CleoPieceModel.from_profile(profile)
    assert "bot igra po verovatnoci" in _translated(f"engine refill: {raised.value}")


def test_cleo_check_names_the_real_boundary_not_an_illegal_swipe(monkeypatch):
    """17:28: "Cleo: candidate no longer legal" hid the booster-figure reason."""
    import refill_monitor
    from simulator_capture import capture_mode
    from strategy_lab import simulation

    folder = ROOT / "Debug/research/20261107_172113_mutation-lab-solo-mode"
    if not (folder / "015.json").exists():
        pytest.skip("Cleo Cadabra recording is not on this machine")
    before, after = (json.loads((folder / name).read_text(encoding="utf-8")) for name in ("014.json", "015.json"))
    monkeypatch.setattr(simulation, "PREFIX_MODES",
                        set(simulation.PREFIX_MODES) | {capture_mode(before["profile"]).value})
    verdict = refill_monitor.check_transition(before, after)
    assert verdict["verdict"] == "unsupported"
    assert "Cleo figura iz boostera" in verdict["detail"]


def test_opponent_move_is_not_a_refill_miss():
    """Versus: the bot plans only its own moves; 6 of 7 "misses" in the
    Moves Multiplier game of 2026-11-07 18:53-18:55 were the opponent's."""
    from refill_monitor import RefillTally, _opponent_to_move

    waiting = {"snapshot_state": {"players": [{"player_type": 1, "is_my_turn": True},
                                              {"player_type": 0, "is_my_turn": False}]}}
    ours = {"snapshot_state": {"players": [{"player_type": 1, "is_my_turn": False},
                                           {"player_type": 0, "is_my_turn": True}]}}
    solo = {"snapshot_state": {"players": [{"player_type": 0, "is_my_turn": True}]}}
    assert _opponent_to_move(waiting)
    assert not _opponent_to_move(ours) and not _opponent_to_move(solo)
    tally = RefillTally()
    line = tally.add({"move": {"verdict": "opponent", "detail": "potezi 2->2"}})
    assert line.startswith("potez protivnika")
    assert "neproverljivih 1" in tally.hit_text()


def test_record_wait_only_in_solo_challenge_unless_research_is_on():
    import memory_gui

    window = SimpleNamespace(_refill_on=True, _research_on=False, _reader_script=object(),
                             _research_done_signature=None, _record_wait_signature=None, _record_wait_started=0.0,
                             _is_solo_challenge=lambda state: False)
    waits = lambda: memory_gui.MemoryWindow._waits_for_board_record(window, {"signature": "a", "state": {}})
    assert not waits()
    window._research_on = True
    assert waits()


def test_fast_refill_only_outside_solo_challenge():
    import memory_gui

    solo = {"is_singleplayer_board": True, "players": [{}], "rules": {}}
    window, _ = _solo_window(True)
    assert not memory_gui.MemoryWindow._fast_refill(window, solo)
    window, _ = _solo_window(True, relaxed=False)      # Showdown
    assert memory_gui.MemoryWindow._fast_refill(window, solo)
    window, _ = _solo_window(True)                     # Versus: full exact
    assert not memory_gui.MemoryWindow._fast_refill(window, {**solo, "players": [{}, {}]})
    party = {**solo, "players": [{}, {}], "rules": {"pvp_mode": 2}}
    assert memory_gui.MemoryWindow._fast_refill(window, party)
    window, _ = _solo_window(False, relaxed=False)
    assert not memory_gui.MemoryWindow._fast_refill(window, solo)


def test_known_perk_and_multiple_inputs_are_not_refill_misses():
    from refill_monitor import check_transition

    before = {"board": [[1]], "special_board": [[0]],
              "profile": {"rng": {"<counter>k__BackingField": 1}, "state": {"moves": 2}},
              "refill_input": (7, "move")}
    after = {**before, "board": [[2]], "refill_input": (8, "activate_perk")}
    assert check_transition(before, after)["verdict"] == "unsupported"
    assert check_transition(before, {**after, "refill_input": (9, "move")})["verdict"] == "gap"
    assert check_transition(before, {**after, "refill_input": (8, "activate_booster")})["verdict"] == "booster"


def test_jelly_renewal_reports_verified_board_separately():
    from refill_monitor import check_transition
    from tools.analyze_research import load

    folder = ROOT / "Debug/research/20261110_013237_bullseye-bash"
    if not folder.is_dir():
        pytest.skip("Bullseye Jelly SE recording not present")
    before, renewed, consumed = (load(folder / f"{index:03}.json")[0] for index in (5, 6, 7))
    result = check_transition(before, renewed)
    assert result["verdict"] == "unsupported"
    assert "tabla i specijali tacni" in result["detail"]
    assert check_transition(renewed, consumed)["verdict"] == "ok"


def test_jelly_renewal_trace_checks_selected_zone():
    from refill_monitor import check_transition
    from tools.analyze_research import load

    folder = ROOT / "Debug/research/20261110_043451_the-floor-is-lava"
    if not folder.is_dir():
        pytest.skip("Lava Jelly SE renewal trace not present")
    before, after = (load(folder / f"{index:03}.json")[0] for index in (4, 5))
    assert check_transition(before, after)["verdict"] == "ok"
    after["profile"]["jelly_renewal_trace"][-1]["selected_points"].pop()
    assert check_transition(before, after)["verdict"] == "unsupported"


@pytest.mark.parametrize("pvp_mode,rumble_type,expected_plies", [
    (0, 0, 3),
    (2, 1, 2),
    (2, 2, 2),
    (2, 3, 2),
])
def test_late_exact_refill_reads_the_settled_board_with_mode_limit(
    monkeypatch, pvp_mode, rumble_type, expected_plies
):
    import memory_gui

    state = {"moves": 5, "players": [{}, {}],
             "rules": {"pvp_mode": pvp_mode, "rumble_type": rumble_type}}
    planned = {"stable": False, "board": [[1, 2]], "special_board": [[0, 0]], "state": state}
    calls = []

    profile = {"rng": {}}

    def session(reader, script, snapshot, board, max_plies=None, resting_profile=None):
        calls.append((snapshot, board, max_plies, resting_profile))
        return "session", None

    monkeypatch.setattr(memory_gui.square_solo_live, "exact_refill_session", session)
    window = SimpleNamespace(_exact_reader=object(), _snapshot={**planned, "stable": True},
                             _strategy_mode=memory_gui.MemoryWindow._strategy_mode,
                             _research=SimpleNamespace(matching_profile=lambda *args: profile),
                             _refill_input=(0, None), _request_dump=lambda: True)
    window._wait_resting_snapshot = lambda planned: memory_gui.MemoryWindow._wait_resting_snapshot(
        window, planned, timeout=0.05)
    late = lambda: memory_gui.MemoryWindow._late_exact_refill(window, object(), planned, [[1, 2]])
    assert late() == ("session", None)
    assert calls[-1][0]["stable"] and calls[-1][2] == expected_plies
    assert calls[-1][3] is profile
    window._snapshot = {**planned, "board": [[2, 1]]}
    session_, reason = late()
    assert session_ is None and "promenila" in reason and len(calls) == 1


def test_a_mutation_picked_inside_the_move_is_not_a_miss():
    from refill_monitor import _mutation_added
    assert _mutation_added({"active_mutations": [{"type": 26}]}, {"active_mutations": [{"type": 26}, {"type": 10}]})
    assert not _mutation_added({"active_mutations": [{"type": 26}]}, {"active_mutations": [{"type": 26}]})
    assert not _mutation_added({}, {})


MUTATION_MISS = ROOT / "Debug/refill_misses/20261109_130641_651570_mutation-lab-solo-mode"


@pytest.mark.skipif(not MUTATION_MISS.is_dir(), reason="Mutation Lab live miss not present")
def test_three_random_specials_from_a_new_mutation_are_uncheckable():
    """Live 2026-11-09 13:06: mutation 10 added, three hearts placed, board otherwise exact."""
    from refill_monitor import check_transition
    before, after = (json.loads((MUTATION_MISS / n).read_text(encoding="utf-8")) for n in ("000.json", "001.json"))
    assert check_transition(before, after)["verdict"] == "unsupported"


def _moving_then_resting():
    board = {"board": [[1]], "special_board": [[0]]}
    moving = dict(board, stable=False, state={"moves": 5, "game_state": -5})
    resting = dict(board, stable=True, state={"moves": 5, "game_state": -5})
    return board, moving, resting


def test_late_refill_waits_for_the_planned_board_to_rest():
    # 2026-11-11 23:17:11: the newest dump was not yet called stable and the
    # move went without the refill ("tabla jos nije mirna").
    import memory_gui

    board, moving, resting = _moving_then_resting()
    planned = dict(board, state={"moves": 5})
    calls = []
    window = SimpleNamespace(_snapshot=moving)

    def dump():
        calls.append(1)
        if len(calls) >= 2:
            window._snapshot = resting
        return True

    window._request_dump = dump
    got = memory_gui.MemoryWindow._wait_resting_snapshot(window, planned, timeout=1.0)
    assert got is resting


def test_late_refill_wait_is_capped_and_stops_on_another_board():
    import memory_gui

    board, moving, _ = _moving_then_resting()
    planned = dict(board, state={"moves": 5})
    window = SimpleNamespace(_snapshot=moving, _request_dump=lambda: True)
    assert memory_gui.MemoryWindow._wait_resting_snapshot(window, planned, timeout=0.05) is moving
    other = dict(moving, board=[[2]])
    window._snapshot = other
    assert memory_gui.MemoryWindow._wait_resting_snapshot(window, planned, timeout=1.0) is other


def _perk_window(pending=None):
    import memory_gui

    notes, logs = [], []
    window = SimpleNamespace(
        _perk_types=(22, 20), _perk_keys=("energy_boost", "mini_cleo"), _used_perk_slots=set(),
        _used_perk_slot_sources={}, _perk_pending_confirmation=pending, _log=logs.append,
        _note_refill_input=lambda action, detail=None: notes.append((action, detail)))
    return memory_gui, window, notes


def test_a_perk_played_by_hand_reaches_the_refill_check():
    # Color Climb 2026-11-12 01:28:53: Mini Cleo by hand read as a wrong move.
    memory_gui, window, notes = _perk_window()
    memory_gui.MemoryWindow._note_used_board_ability(
        window, {"is_board_ability_used_this_move": True, "board_ability_used_this_move": 20})
    assert notes == [("activate_perk", {"action": "activate_perk", "manual": True, "perk": "mini_cleo"})]


def test_the_bots_own_perk_is_not_noted_twice():
    memory_gui, window, notes = _perk_window(pending=(2, "mini_cleo"))
    memory_gui.MemoryWindow._note_used_board_ability(
        window, {"is_board_ability_used_this_move": True, "board_ability_used_this_move": 20})
    assert notes == [] and window._perk_pending_confirmation is None


def test_a_given_reason_is_not_overwritten_by_the_board_read_before_a_booster():
    import memory_gui

    emitted = []
    window = SimpleNamespace(_reader_signals=SimpleNamespace(
        refill=SimpleNamespace(emit=emitted.append)))
    session = SimpleNamespace(successful=0, approximated=0, failure=None, simulations=0)
    memory_gui.MemoryWindow._report_exact_refill(window, session, "ovaj potez je booster")
    assert emitted[-1]["usage"]["reason"] == "ovaj potez je booster"
    assert not emitted[-1]["usage"]["active"]
