"""Brza igra: Time.timeScale in solo modes, 1x in PvP/unchecked/match ended."""
import threading
from types import SimpleNamespace

import memory_gui as gui


class _Exports:
    def __init__(self):
        self.calls = []
        self.done = threading.Event()

    def set_time_scale(self, scale):
        self.calls.append(scale)
        self.done.set()
        return {"previous": 1.0, "now": scale}


def _window(solo: bool, checked: bool, active: bool = True):
    exports = _Exports()
    obj = SimpleNamespace(
        _reader_script=SimpleNamespace(exports_sync=exports),
        _snapshot={"state": {"is_singleplayer_board": solo}},
        _match_active=active,
        _game_speed=(None, 1.0),
        _speed_failed=False,
        _is_solo_challenge=lambda state: state["solo"],
        SoloSpeedCheck=SimpleNamespace(isChecked=lambda: checked),
        _reader_signals=SimpleNamespace(status=SimpleNamespace(emit=lambda _m: None)),
    )
    obj._wanted_game_speed = lambda: gui.MemoryWindow._wanted_game_speed(obj)
    return obj, exports


def _apply(obj, exports):
    exports.done.clear()
    gui.MemoryWindow._apply_game_speed(obj)
    exports.done.wait(2.0)


def test_speed_is_gentle():
    assert 1.0 < gui.SOLO_GAME_SPEED <= 1.5     # 2x lost swipes and crashed the game


def test_solo_challenge_speeds_up_once_and_resets_at_match_end():
    obj, exports = _window(solo=True, checked=True)
    _apply(obj, exports)
    gui.MemoryWindow._apply_game_speed(obj)          # same speed: no second RPC
    assert exports.calls == [gui.SOLO_GAME_SPEED]
    obj._match_active = False
    _apply(obj, exports)
    assert exports.calls == [gui.SOLO_GAME_SPEED, 1.0]


def test_lost_swipe_drops_the_match_to_normal_speed():
    obj, exports = _window(solo=True, checked=True)
    _apply(obj, exports)
    obj._speed_failed = True
    _apply(obj, exports)
    assert exports.calls == [gui.SOLO_GAME_SPEED, 1.0]


def test_pvp_stays_normal_speed_even_when_checked():
    obj, exports = _window(solo=False, checked=True)
    _apply(obj, exports)
    assert exports.calls == [1.0]


def test_unchecked_stays_normal_speed():
    for solo in (True, False):
        obj, exports = _window(solo=solo, checked=False)
        _apply(obj, exports)
        assert exports.calls == [1.0]


