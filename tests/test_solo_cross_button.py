"""The Solo Challenge button lights up only on a board with a sure crossing."""
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
    panel._solo_cross_allowed = True
    yield panel
    panel.close()
    panel.deleteLater()
    app.processEvents()


def _snapshot(board=1, score=10, full=False):
    me = {"player_type": 0, "index": 0, "score": score, "energy": 7 if full else 0,
          "energy_to_ability": 7, "energy_full": full, "is_my_turn": True}
    return {"board": [[board]], "special_board": [[0]],
            "state": {"players": [me], "current_player_index": 0}}


def _show(window, snapshot, found=True):
    window._snapshot = snapshot
    window._on_solo_cross(window._solo_cross_key(snapshot), found)


def test_lights_up_only_when_a_crossing_exists(window):
    _show(window, _snapshot(), found=True)
    assert window.SoloCrossButton.isEnabled()
    _show(window, _snapshot(), found=False)
    assert not window.SoloCrossButton.isEnabled()


def test_stays_off_before_any_answer_and_when_the_board_or_score_changes(window):
    window._snapshot = _snapshot()
    window._update_solo_cross_button()
    assert not window.SoloCrossButton.isEnabled()
    _show(window, _snapshot(), found=True)
    window._snapshot = _snapshot(board=2)
    window._update_solo_cross_button()
    assert not window.SoloCrossButton.isEnabled()
    _show(window, _snapshot(), found=True)
    window._snapshot = _snapshot(score=11)
    window._update_solo_cross_button()
    assert not window.SoloCrossButton.isEnabled()


def test_stays_off_with_a_ready_booster(window):
    _show(window, _snapshot(full=True), found=True)
    assert not window.SoloCrossButton.isEnabled()


def test_stays_off_while_actions_are_disabled(window):
    _show(window, _snapshot(), found=True)
    window._set_actions_enabled(False)
    assert not window.SoloCrossButton.isEnabled()


def test_click_asks_for_its_own_action(window, monkeypatch):
    asked = []
    monkeypatch.setattr(window, "_play", lambda action, **kwargs: asked.append(action))
    window.SoloCrossButton.setEnabled(True)
    window.SoloCrossButton.click()
    assert asked == ["solo_cross"]
