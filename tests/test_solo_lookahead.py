"""Solo lookahead selection reaches planning and survives reopening the GUI."""
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


def test_solo_has_twenty_candidate_default_and_selectable_lighter_presets(window):
    assert window._lookahead_params(True, False, False) == (20, 4, 6)
    assert max(params[0] for params in gui.SOLO_LOOKAHEAD_PARAMS.values()) == 20
    for label, expected in gui.SOLO_LOOKAHEAD_PARAMS.items():
        window.SoloLookaheadCombo.setCurrentText(label)
        assert window._lookahead_params(True, False, False) == expected


def test_solo_selection_is_saved_and_restored(window):
    window.SoloLookaheadCombo.setCurrentText("10/2/3")
    saved = json.loads(gui.TIMING_SETTINGS_PATH.read_text())
    assert saved["solo_lookahead"] == "10/2/3"
    window.SoloLookaheadCombo.blockSignals(True)
    window.SoloLookaheadCombo.setCurrentText("20/4/6")
    window.SoloLookaheadCombo.blockSignals(False)
    window._load_timing_settings()
    assert window._solo_lookahead_params() == (10, 2, 3)


def test_solo_choice_invalidates_plan_and_keeps_timed_choice_separate(window):
    snapshot = {"board": [[1, 2], [3, 4]], "state": {}}
    before = window._auto_plan_key(snapshot)
    window.SoloLookaheadCombo.setCurrentText("6/2/3")
    assert window._auto_plan_key(snapshot) != before
    window.LookaheadCombo.setCurrentText("10/2/3")
    assert window._lookahead_params(False, False, False) == (10, 2, 3)
    assert window._lookahead_params(True, False, False) == (6, 2, 3)
    assert window._lookahead_params(True, False, True) == (10, 2, 3)
