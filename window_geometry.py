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


# Child window that BlueStacks renders Android into: the game area alone.
RENDER_WINDOW_CLASS = "BlueStacksApp"


def render_rect_for_hwnd(hwnd):
    """Screen rect of the largest visible render child of ``hwnd``, or None."""

    user32 = ctypes.windll.user32
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def child(child_hwnd, _):
        name = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(child_hwnd, name, 64)
        if name.value == RENDER_WINDOW_CLASS and user32.IsWindowVisible(child_hwnd):
            r = wintypes.RECT()
            if user32.GetWindowRect(child_hwnd, ctypes.byref(r)):
                width, height = int(r.right - r.left), int(r.bottom - r.top)
                if width > 0 and height > 0:
                    found.append(WindowRect(int(r.left), int(r.top), width, height))
        return True

    user32.EnumChildWindows(hwnd, child, 0)
    return max(found, key=lambda rect: rect.width * rect.height) if found else None


def client_rect_for_window(window) -> WindowRect:
    """Return the game's drawable rectangle in absolute screen coordinates.

    The BlueStacks render child, not the whole client: in a window the client
    also holds the title bar and the side toolbar. The portrait calibration
    was saved without them (607x1080, exact 9:16), so scaling it to a 539x931
    client with them put the board 2 px per cell too big and shifted: (0, 6)
    landed 21 px right and 20 px above its centre, and a 42 px left swipe
    never left the tile (2026-11-07 20:59, played only in fullscreen).
    """

    hwnd = getattr(window, "_hWnd", None)
    if hwnd:
        try:
            render = render_rect_for_hwnd(hwnd)
        except (AttributeError, OSError):
            render = None
        if render is not None:
            return render
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
