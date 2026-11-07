"""The Cleo panel must show memory values for the board being computed.

Snapshots only arrive when the board changes, so a profile read by the move
worker has to reach the panel directly: waiting for the next snapshot always
compared it with a newer board and the panel kept saying nothing was read.
"""
from unittest.mock import MagicMock

import pytest

memory_gui = pytest.importorskip("memory_gui")
Window = memory_gui.MemoryWindow


def _snapshot():
    board = [
        [2, 3, 4, 5, 6, 2, 3],
        [3, 4, 5, 6, 2, 3, 4],
        [4, 5, 6, 2, 3, 4, 5],
        [5, 6, 2, 99, 4, 5, 6],
        [6, 2, 3, 4, 5, 6, 2],
        [2, 3, 4, 5, 6, 2, 3],
        [3, 4, 5, 6, 2, 3, 4],
    ]
    special = [[0] * 7 for _ in range(7)]
    special[3][3] = memory_gui.SPECIAL_CLEO_BUG
    return {"board": board, "special_board": special}


def _profile():
    logic = {"chanceToPreventExtraMoveOnColorBasedClone": [10], "LogicOrigin": 1}
    return {"cleo_booster_fields": {"BoosterPiecesLogic": logic},
            "board_extra_data": {"entries": []},
            "cleo_slots": [{"row": 3, "col": 3, "value": 32, "origin": 1}]}


def _window():
    window = MagicMock()
    window._cleo_odds_key = None
    window._cleo_profile = (None, None)
    window._cleo_render_args = None
    window._CLEO_DIRECTION_LABELS = Window._CLEO_DIRECTION_LABELS
    window._cleo_color_chip = lambda *a, **k: "x"
    window._render_cleo_odds = lambda *a: Window._render_cleo_odds(window, *a)
    window._redraw_cleo_odds = lambda: Window._redraw_cleo_odds(window)
    return window


def _panel_text(window):
    return window.CleoOddsLabel.setText.call_args[0][0]


def test_worker_values_reach_the_panel_for_the_board_already_drawn():
    window, snapshot = _window(), _snapshot()
    window._render_cleo_odds(snapshot, {})
    assert "PvP pretpostavka" in _panel_text(window)
    Window._remember_cleo_profile(window, snapshot, _profile())
    window._move_signals.cleo_values.emit.assert_called_once_with()
    window._redraw_cleo_odds()
    assert "iz memorije igre" in _panel_text(window)


def test_values_of_an_older_board_are_not_shown_on_a_new_one():
    window, snapshot = _window(), _snapshot()
    Window._remember_cleo_profile(window, snapshot, _profile())
    newer = _snapshot()
    newer["special_board"][3][3] = 0
    newer["special_board"][0][0] = memory_gui.SPECIAL_CLEO_BUG
    newer["board"][0][0] = 99
    newer["board"][3][3] = 2
    window._render_cleo_odds(newer, {})
    # Memory values exist for this game, just not for this layout yet: wait
    # for them instead of a PvP number that drops once the board rests
    # (84% -> 49% on 2026-11-07 17:21).
    assert "Cekam vrednosti iz memorije" in _panel_text(window)
    assert "PvP pretpostavka" not in _panel_text(window)


def test_pvp_fallback_only_before_any_memory_values():
    window = _window()
    window._render_cleo_odds(_snapshot(), {})
    assert "PvP pretpostavka" in _panel_text(window)


def test_nothing_read_does_not_redraw():
    window = _window()
    Window._remember_cleo_profile(window, _snapshot(), None)
    window._move_signals.cleo_values.emit.assert_not_called()
