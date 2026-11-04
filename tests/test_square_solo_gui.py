from pathlib import Path

import pytest

SESSION = Path(__file__).resolve().parents[1] / "Debug/match_captures/session_20261101_002122"
pytestmark = pytest.mark.skipif(not SESSION.is_dir(), reason="recorded Square Solo session not present")


class FakeRuntime:
    PERK_PROMPT_DELAY_SECONDS = 0

    def __init__(self):
        self.calls = []

    def play_best_move_with_cursor_restore(self, start, direction, score):
        self.calls.append((start, direction))

    def perk_slot_center(self, slot):
        return (-slot, -slot)

    def board_cell_center(self, cell):
        return cell

    def _memory_booster_click_detection(self, active):
        return {}

    def click_booster_activate(self, detection):
        self.calls.append("booster")


def engine_with(monkeypatch, captures):
    import pyautogui
    import square_solo_gui as gui

    monkeypatch.setattr(gui, "SETTLE_SECONDS", 0)
    engine = gui.Engine()
    fake = FakeRuntime()
    monkeypatch.setattr(pyautogui, "click", lambda *a, **k: fake.calls.append(("click", a)))
    queue = list(captures)
    monkeypatch.setattr(engine, "_capture_once", lambda: queue.pop(0))
    monkeypatch.setattr(engine, "_prepare_input", lambda: fake)
    engine.plan_seconds = 1
    return engine, fake


def test_played_swipe_is_checked_against_the_recorded_result(monkeypatch):
    from strategy_lab.planner import Line

    before, after = sorted(p for p in SESSION.iterdir() if p.is_dir())[:2]
    engine, fake = engine_with(monkeypatch, [before, after])
    engine.capture()
    # The move the player actually made between these two captures.
    action = {"start": [4, 2], "target": [3, 2], "direction": "up"}
    engine.plan_line = Line(engine.current, [action], [0])
    engine.play_next()
    assert fake.calls == [((4, 2), "up")]
    engine.capture(settle=True)
    assert engine.check_prediction() is True


def test_plan_reaches_the_last_move_and_replays_to_the_same_score():
    from simulator_capture import lab_move, load_capture
    from strategy_lab import planner
    from strategy_lab.simulation import step

    state = lab_move(load_capture(sorted(p for p in SESSION.iterdir() if p.is_dir())[0]))
    best, stats = planner.plan(state, width=3)
    assert stats["complete"] and best.moves_left == 0 and best.score > state["score"]
    replay = state
    for action in best.actions:
        replay = step(replay, action)["state"]
    assert replay["score"] == best.score


def test_a_swipe_the_game_ignored_is_played_again(monkeypatch):
    from strategy_lab.planner import Line

    before, after = sorted(p for p in SESSION.iterdir() if p.is_dir())[:2]
    # The first swipe is lost: the next capture still shows the old board.
    engine, fake = engine_with(monkeypatch, [before, before, after])
    engine.capture()
    engine.plan_line = Line(engine.current, [{"start": [4, 2], "target": [3, 2], "direction": "up"}], [0])
    engine.play_and_capture()
    assert fake.calls == [((4, 2), "up")] * 2
    assert engine.check_prediction() is True


BOOSTER_SESSION = SESSION.parent / "solo_gui_20261101_010124"


@pytest.mark.skipif(not BOOSTER_SESSION.is_dir(), reason="recorded booster use not present")
def test_booster_fires_unpredicted_and_waits_for_a_still_board(monkeypatch):
    import square_solo_gui as gui

    full = next(BOOSTER_SESSION.glob("06_*[0-9]"))
    after = next(BOOSTER_SESSION.glob("07_*[0-9]"))
    monkeypatch.setattr(gui, "BOOSTER_SETTLE_SECONDS", 0)
    monkeypatch.setattr(gui, "BOOSTER_STABLE_GAP", 0)
    engine, fake = engine_with(monkeypatch, [full, after, after])
    engine.capture()
    assert engine.booster_ready(engine.current)
    state = engine.fire_booster()
    assert fake.calls == ["booster"]
    assert state["score"] == 210 and not engine.booster_ready(state)
    assert engine.expected is None  # nothing to verify against


def test_auto_stops_when_the_game_did_not_follow_the_simulation(monkeypatch):
    first, second = sorted(p for p in SESSION.iterdir() if p.is_dir())[:2]
    # The planner picks its own move, but the "game" answers with the
    # recorded result of the player's different move.
    engine, fake = engine_with(monkeypatch, [first, second])
    reason = engine.auto()
    assert fake.calls  # one planned action was sent to the game
    assert "nije poklopila" in reason
