"""Swipe inside BlueStacks: raw touch events written to its virtual touch device.

The mouse path (runtime.swipe) moves the real Windows cursor, needs the window
in front and depends on BlueStacks turning a mouse drag into a fling. This
writes the same gesture as touch events straight into "BlueStacks Virtual
Touch" over one persistent ``adb shell``: the shell user is in the ``input``
group, so no root is needed, and the cursor never moves.

Event format recorded from BlueStacks itself (2026-11-07, getevent on event4):
TRACKING_ID 0, POSITION_X, POSITION_Y, BTN_TOUCH DOWN, SYN; moves send the
changed axis + SYN; lift is TRACKING_ID -1, BTN_TOUCH UP, SYN. No MT_SLOT.

Axes: the device reports the landscape natural orientation, 0..32767 over the
BlueStacks render area (child window class ``BlueStacksApp``), rotated against
the portrait game: raw_x = (1 - y_frac) * max, raw_y = x_frac * max. Measured
on three hand swipes to within a few raw units.
"""
from __future__ import annotations

import ctypes
import queue
import re
import struct
import subprocess
import sys
import threading
import time
from ctypes import wintypes

EV_SYN, EV_KEY, EV_ABS = 0, 1, 3
SYN_REPORT = 0
BTN_TOUCH = 0x14A
ABS_MT_POSITION_X, ABS_MT_POSITION_Y, ABS_MT_TRACKING_ID = 0x35, 0x36, 0x39
TOUCH_DEVICE_NAME = "BlueStacks Virtual Touch"
RENDER_WINDOW_CLASS = "BlueStacksApp"
# struct input_event on x86_64: timeval (2 x 8 bytes, the kernel stamps it),
# __u16 type, __u16 code, __s32 value.
_EVENT = struct.Struct("<qqHHi")
# Gesture shape, the same as the mouse flick that BlueStacks accepts.
STEPS = 6
DURATION_SECONDS = 0.03
POST_HOLD_SECONDS = 0.03
ACK_TIMEOUT_SECONDS = 2.0
_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


class TouchUnavailable(RuntimeError):
    """Nothing was sent: the caller may play the swipe with the mouse."""


class TouchUncertain(RuntimeError):
    """Sent, but not confirmed: a mouse retry could play the move twice."""


def _event(type_, code, value) -> bytes:
    return _EVENT.pack(0, 0, type_, code, value)


def _print_escape(data: bytes) -> str:
    # mksh's builtin print: \0NNN is one octal byte, and no process per step.
    return "".join(f"\\0{b:03o}" for b in data)


def gesture_events(start, end, steps=STEPS):
    """Raw event groups for one swipe: [down, move..., up], each a bytes blob."""
    (x0, y0), (x1, y1) = start, end
    down = (_event(EV_ABS, ABS_MT_TRACKING_ID, 0) + _event(EV_ABS, ABS_MT_POSITION_X, x0)
            + _event(EV_ABS, ABS_MT_POSITION_Y, y0) + _event(EV_KEY, BTN_TOUCH, 1)
            + _event(EV_SYN, SYN_REPORT, 0))
    moves = []
    for step in range(1, steps + 1):
        f = step / steps
        moves.append(_event(EV_ABS, ABS_MT_POSITION_X, int(round(x0 + (x1 - x0) * f)))
                     + _event(EV_ABS, ABS_MT_POSITION_Y, int(round(y0 + (y1 - y0) * f)))
                     + _event(EV_SYN, SYN_REPORT, 0))
    up = (_event(EV_ABS, ABS_MT_TRACKING_ID, -1) + _event(EV_KEY, BTN_TOUCH, 0)
          + _event(EV_SYN, SYN_REPORT, 0))
    return [down, *moves, up]


def gesture_script(device, start, end, steps=STEPS, duration=DURATION_SECONDS,
                   post_hold=POST_HOLD_SECONDS, token="done"):
    """One shell line: the whole swipe runs on the device, paced there."""
    groups = gesture_events(start, end, steps)
    pause = f"{duration / steps:.4f}"
    parts = [f"print -n '{_print_escape(groups[0])}' >&3"]
    for group in groups[1:-1]:
        parts.append(f"sleep {pause}")
        parts.append(f"print -n '{_print_escape(group)}' >&3")
    parts.append(f"sleep {post_hold:.4f}")
    parts.append(f"print -n '{_print_escape(groups[-1])}' >&3")
    parts.append(f"echo {token}")
    return f"exec 3>{device}; " + "; ".join(parts) + "; exec 3>&-"


def find_touch_device(getevent_output: str):
    """(path, max_x, max_y) of the BlueStacks touch device in ``getevent -pl``."""
    for block in re.split(r"(?=add device \d+:)", getevent_output):
        if TOUCH_DEVICE_NAME not in block:
            continue
        path = re.search(r"add device \d+:\s*(\S+)", block)
        mx = re.search(r"ABS_MT_POSITION_X\s*:.*?max (\d+)", block)
        my = re.search(r"ABS_MT_POSITION_Y\s*:.*?max (\d+)", block)
        if path and mx and my:
            return path.group(1), int(mx.group(1)), int(my.group(1))
    return None


def to_raw(point, rect, max_x, max_y):
    """Screen pixel -> raw touch units, for the BlueStacks render rect."""
    left, top, right, bottom = rect
    x_frac = (point[0] - left) / max(1, right - left)
    y_frac = (point[1] - top) / max(1, bottom - top)
    x_frac, y_frac = min(1.0, max(0.0, x_frac)), min(1.0, max(0.0, y_frac))
    return int(round((1.0 - y_frac) * max_x)), int(round(x_frac * max_y))


def render_rect_at(point):
    """Screen rect of the BlueStacks render window that contains ``point``."""
    if sys.platform != "win32":
        return None
    user32 = ctypes.windll.user32
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def child(hwnd, _):
        name = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hwnd, name, 64)
        if name.value == RENDER_WINDOW_CLASS and user32.IsWindowVisible(hwnd):
            r = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(r))
            if r.left <= point[0] < r.right and r.top <= point[1] < r.bottom:
                found.append((r.left, r.top, r.right, r.bottom))
        return True

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def top(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            user32.EnumChildWindows(hwnd, child, 0)
        return True

    user32.EnumWindows(top, 0)
    return found[0] if found else None


class AdbTouch:
    """One persistent ``adb shell`` that plays swipes into the touch device."""

    def __init__(self, adb: str, serial: str):
        self.adb, self.serial = adb, serial
        self.device = None
        self.max_x = self.max_y = 32767
        self._proc = None
        self._lines: queue.Queue[str] = queue.Queue()
        self._lock = threading.Lock()
        self._count = 0

    def _start(self):
        out = subprocess.run([self.adb, "-s", self.serial, "shell", "getevent", "-pl"],
                             capture_output=True, text=True, timeout=10, creationflags=_NO_WINDOW).stdout
        found = find_touch_device(out)
        if found is None:
            raise TouchUnavailable(f"nema uredjaja '{TOUCH_DEVICE_NAME}'")
        self.device, self.max_x, self.max_y = found
        self._proc = subprocess.Popen(
            [self.adb, "-s", self.serial, "shell"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, bufsize=1, creationflags=_NO_WINDOW)
        threading.Thread(target=self._pump, args=(self._proc,), daemon=True).start()

    def _pump(self, proc):
        for line in proc.stdout:
            self._lines.put(line.rstrip())
        self._lines.put("\0eof")

    def close(self):
        proc, self._proc = self._proc, None
        if proc is not None:
            try:
                proc.kill()
            except OSError:
                pass

    def swipe_screen(self, start, end):
        """Swipe between two screen pixels. Raises TouchUnavailable if not played."""
        rect = render_rect_at(start)
        if rect is None:
            raise TouchUnavailable("BlueStacks prozor nije na toj tacki")
        with self._lock:
            if self._proc is None or self._proc.poll() is not None:
                self._start()
            raw_start = to_raw(start, rect, self.max_x, self.max_y)
            raw_end = to_raw(end, rect, self.max_x, self.max_y)
            self._count += 1
            token = f"swipe_ok_{self._count}"
            while not self._lines.empty():
                self._lines.get_nowait()
            try:
                self._proc.stdin.write(gesture_script(self.device, raw_start, raw_end, token=token) + "\n")
                self._proc.stdin.flush()
            except OSError as exc:
                # A broken pipe means the shell was gone before the line left.
                self.close()
                raise TouchUnavailable(f"adb shell: {exc}") from exc
            deadline = time.monotonic() + ACK_TIMEOUT_SECONDS
            errors = []
            while True:
                left = deadline - time.monotonic()
                if left <= 0:
                    self.close()
                    raise TouchUncertain("adb shell nije potvrdio swipe")
                try:
                    line = self._lines.get(timeout=left)
                except queue.Empty:
                    continue
                if line == token:
                    if errors:
                        raise TouchUncertain("; ".join(errors))
                    return raw_start, raw_end
                if line == "\0eof":
                    self.close()
                    raise TouchUncertain("adb shell se zatvorio")
                if line.strip():
                    errors.append(line.strip())
