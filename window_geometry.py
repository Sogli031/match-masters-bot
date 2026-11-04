"""BlueStacks window geometry helpers used by display calibration.

The bot's board coordinates are screen coordinates.  For portable calibration
we anchor those coordinates to the BlueStacks *client* rectangle (the drawable
area), not to the monitor or to the outer window frame.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass


@dataclass(frozen=True)
class WindowRect:
    left: int
    top: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height

    def to_dict(self) -> dict[str, int]:
        return {
            "left": self.left,
            "top": self.top,
            "width": self.width,
            "height": self.height,
        }


def _is_player_window(window) -> bool:
    title = str(getattr(window, "title", "") or "").strip().lower()
    return "bluestacks" in title and "manager" not in title


def find_bluestacks_window(windows=None):
    """Return the App Player window, never the Multi-instance Manager."""

    if windows is None:
        import pyautogui

        windows = pyautogui.getWindowsWithTitle("BlueStacks")
    candidates = [window for window in windows if _is_player_window(window)]
    if not candidates:
        raise RuntimeError("BlueStacks App Player prozor nije pronadjen")
    visible = [
        window
        for window in candidates
        if int(getattr(window, "width", 0)) > 0
        and int(getattr(window, "height", 0)) > 0
    ]
    return (visible or candidates)[0]


def client_rect_for_window(window) -> WindowRect:
    """Return the drawable client rectangle in absolute screen coordinates."""

    hwnd = getattr(window, "_hWnd", None)
    if hwnd:
        rect = wintypes.RECT()
        origin = wintypes.POINT(0, 0)
        user32 = ctypes.windll.user32
        if user32.GetClientRect(hwnd, ctypes.byref(rect)) and user32.ClientToScreen(
            hwnd, ctypes.byref(origin)
        ):
            width = int(rect.right - rect.left)
            height = int(rect.bottom - rect.top)
            if width > 0 and height > 0:
                return WindowRect(int(origin.x), int(origin.y), width, height)

    # Safe fallback for tests or an unusual window wrapper without a HWND.
    width = int(getattr(window, "width", 0))
    height = int(getattr(window, "height", 0))
    if width <= 0 or height <= 0:
        raise RuntimeError("BlueStacks prozor nema validnu velicinu")
    return WindowRect(
        int(getattr(window, "left", 0)),
        int(getattr(window, "top", 0)),
        width,
        height,
    )


def find_bluestacks_client_rect(windows=None) -> WindowRect:
    return client_rect_for_window(find_bluestacks_window(windows))
