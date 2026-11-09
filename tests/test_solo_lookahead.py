"""Lookahead is fixed by the kind of match, and the panel says which one is used."""
import json
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5 import QtWidgets
import memory_gui as gui


@pytest.fixture
def window(monkeypatch, tmp_path):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    monkeypatch.setattr(gui, "AUTO_ATTACH_ON_START", False)
    monkeypatch.setattr(gui, "TIMING_SETTINGS_PATH", tmp_path / "timing.json")
    monkeypatch.setattr(gui, "GUI_LOG_PATH", tmp_path / "gui.log")
    panel = gui.MemoryWindow()
    panel._auto_timer.stop()
    panel._freeze_timer.stop()
    yield panel
    panel.close()
    panel.deleteLater()
    app.processEvents()


SOLO_CHALLENGE = {"is_singleplayer_board": True, "players": [{}],
                  "rules": {"is_timer": True, "engine_fields": {"timePerTurn": 1500}}}
RACE = {"is_singleplayer_board": True, "players": [{}],
        "rules": {"is_timer": True, "engine_fields": {"timePerTurn": 65}}}
VERSUS = {"is_singleplayer_board": False, "players": [{}, {}],
          "rules": {"is_timer": True, "engine_fields": {"timePerTurn": 25}}}
INFINITE = {"is_singleplayer_board": True, "players": [{}],
            "rules": {"is_timer": False, "reduce_move_on_valid_swap": False}}


@pytest.mark.parametrize("state,params,kind", [
    (SOLO_CHALLENGE, (20, 3, 6), "Solo Challenge"),
    (RACE, (6, 2, 3), "trka na vreme"),
    (VERSUS, (6, 3, 3), "Versus"),
    (INFINITE, (6, 2, 3), "Infinite Moves"),
])
def test_match_kind_decides_the_search(window, state, params, kind):
    assert window._lookahead_for_state(state) == (params, kind)


@pytest.mark.parametrize("refill_on", [False, True])
def test_refill_does_not_change_the_search(window, refill_on):
    window._refill_on = refill_on
    assert window._lookahead_for_state(SOLO_CHALLENGE)[0] == (20, 3, 6)
    assert window._lookahead_for_state(VERSUS)[0] == (6, 3, 3)


def test_there_is_nothing_left_to_pick(window):
    assert not hasattr(window, "LookaheadCombo")
    assert not hasattr(window, "SoloLookaheadCombo")
    window._save_timing_settings()
    saved = json.loads(gui.TIMING_SETTINGS_PATH.read_text())
    assert "fast_lookahead" not in saved and "solo_lookahead" not in saved


def test_an_old_saved_choice_is_ignored(window):
    gui.TIMING_SETTINGS_PATH.write_text(
        json.dumps({"fast_lookahead": "12/3/4", "solo_lookahead": "6/2/3"})
    )
    window._load_timing_settings()
    assert window._lookahead_for_state(RACE)[0] == (6, 2, 3)
    assert window._lookahead_for_state(SOLO_CHALLENGE)[0] == (20, 3, 6)


def test_label_shows_during_a_match_and_logs_once(window, monkeypatch):
    logs = []
    monkeypatch.setattr(window, "_log", logs.append)
    assert window.LookaheadLabel.isHidden()
    window._match_active = True
    window._on_snapshot({"state": SOLO_CHALLENGE})
    assert not window.LookaheadLabel.isHidden()
    assert window.LookaheadLabel.text() == "Lookahead: 20/3/6 (Solo Challenge)"
    window._on_snapshot({"state": SOLO_CHALLENGE})
    assert logs.count("Lookahead: 20/3/6 (Solo Challenge)") == 1
    window._on_snapshot({"state": VERSUS})
    assert window.LookaheadLabel.text() == "Lookahead: 6/3/3 (Versus)"


def test_label_hides_when_the_match_ends_and_logs_again_next_time(window, monkeypatch):
    logs = []
    monkeypatch.setattr(window, "_log", logs.append)
    window._match_active = True
    window._on_snapshot({"state": RACE})
    window._on_match_state(False, "test")
    assert window.LookaheadLabel.isHidden()
    window._match_active = False
    window._on_snapshot({"state": RACE})
    assert window.LookaheadLabel.isHidden()
    window._match_active = True
    window._on_snapshot({"state": RACE})
    assert logs.count("Lookahead: 6/2/3 (trka na vreme)") == 2
