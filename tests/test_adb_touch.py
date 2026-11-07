import struct
from types import SimpleNamespace

import adb_touch
import runtime

RECT = (834, 63, 1339, 960)   # BlueStacksApp, 2026-11-07


def test_screen_to_raw_matches_recorded_hand_touches():
    # Cursor and the raw position BlueStacks itself reported for it (getevent).
    for point, raw in (((1081, 905), (0x7D9, 0x3E9A)), ((1171, 885), (0xAD8, 0x556A)),
                       ((1095, 749), (0x1E1B, 0x4227))):
        x, y = adb_touch.to_raw(point, RECT, 32767, 32767)
        assert abs(x - raw[0]) < 60 and abs(y - raw[1]) < 60


def test_gesture_is_down_moves_up_like_bluestacks():
    groups = adb_touch.gesture_events((100, 200), (160, 200), steps=3)
    assert len(groups) == 5
    events = lambda blob: [struct.unpack("<qqHHi", blob[i:i + 24])[2:] for i in range(0, len(blob), 24)]
    assert events(groups[0]) == [(3, 0x39, 0), (3, 0x35, 100), (3, 0x36, 200), (1, 0x14A, 1), (0, 0, 0)]
    assert events(groups[3]) == [(3, 0x35, 160), (3, 0x36, 200), (0, 0, 0)]
    assert events(groups[4]) == [(3, 0x39, -1), (1, 0x14A, 0), (0, 0, 0)]


def test_script_uses_builtin_print_and_acks():
    script = adb_touch.gesture_script("/dev/input/event4", (1, 2), (3, 4), steps=2, token="ok7")
    assert script.startswith("exec 3>/dev/input/event4; ")
    assert script.count("print -n '") == 4 and "printf" not in script
    assert "echo ok7" in script and r"\0377" in script     # tracking id -1


def test_find_touch_device_in_getevent():
    text = ('add device 3: /dev/input/event4\n  name:     "BlueStacks Virtual Touch"\n'
            '    ABS (0003): ABS_MT_SLOT : value 0, min 0, max 15\n'
            '                ABS_MT_POSITION_X     : value 0, min 0, max 32767, fuzz 0\n'
            '                ABS_MT_POSITION_Y     : value 0, min 0, max 32000, fuzz 0\n'
            'add device 5: /dev/input/event5\n  name:     "VirtualBox mouse integration"\n')
    assert adb_touch.find_touch_device(text) == ("/dev/input/event4", 32767, 32000)
    assert adb_touch.find_touch_device("add device 1: /dev/input/event6\n name: \"Power\"") is None


def _play(monkeypatch, error=None):
    calls = []

    def swipe_screen(start, end):
        calls.append((start, end))
        if error is not None:
            raise error

    monkeypatch.setattr(runtime, "ADB_TOUCH", SimpleNamespace(swipe_screen=swipe_screen))
    monkeypatch.setattr(runtime, "board_cell_center", lambda cell: (500, 400))
    mouse = []
    monkeypatch.setattr(runtime, "swipe", lambda direction: mouse.append(direction))
    monkeypatch.setattr(runtime.pyautogui, "moveTo", lambda *a, **k: None)
    monkeypatch.setattr(runtime.pyautogui, "position", lambda: (1, 1))
    monkeypatch.setattr(runtime.time, "sleep", lambda s: None)
    monkeypatch.setattr(runtime, "recognition", SimpleNamespace(display_scale=1.0), raising=False)
    assert runtime.play_best_move_with_cursor_restore((2, 3), "up", 1.0)
    return calls, mouse


def test_play_swipes_through_adb_without_the_mouse(monkeypatch):
    calls, mouse = _play(monkeypatch)
    assert calls == [((500, 400), (500, 400 - runtime.SWIPE_DISTANCE_PX))] and mouse == []


def test_unsent_adb_swipe_falls_back_to_the_mouse(monkeypatch):
    calls, mouse = _play(monkeypatch, adb_touch.TouchUnavailable("no window"))
    assert len(calls) == 1 and mouse == ["up"]


def test_unconfirmed_adb_swipe_is_not_played_twice(monkeypatch):
    calls, mouse = _play(monkeypatch, adb_touch.TouchUncertain("no ack"))
    assert len(calls) == 1 and mouse == []
