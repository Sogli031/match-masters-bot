"""Record a real mouse-flick once, then replay it as the bot's swipe.

The "synthetic" swipe in runtime.swipe() is parameter-tuned (duration, distance,
pre/post hold). It works, but every BlueStacks build classifies gestures slightly
differently and tuning by trial-and-error wastes time. Recording a real hand
flick from the user once gives us a velocity curve, acceleration, and trailing
hold that we *know* BlueStacks accepts — because it accepts the user's own
manual play.

The recorder polls global mouse state via Win32 GetAsyncKeyState (no extra
dependency) and snapshots cursor position at ~5ms intervals while the left
button is held. The captured trajectory is saved as a "right" canonical
recording; runtime rotates it to other directions at replay time so one
recording covers all four cardinal swipes consistently.
"""

from __future__ import annotations

import ctypes
import json
import time
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import pyautogui

# A single sample: (seconds_since_mouse_down, dx_from_start, dy_from_start).
SwipeSample = Tuple[float, int, int]

SWIPE_PROFILE_VERSION = 1
SWIPE_PROFILE_PATH = Path(__file__).resolve().with_name("swipe_profile.json")

# Win32 VK_LBUTTON. GetAsyncKeyState returns a SHORT; high bit set = currently
# pressed. Works globally regardless of which window has focus.
_VK_LBUTTON = 0x01
_HIGH_BIT_MASK = 0x8000

# Recording loop pacing. 5ms = 200Hz sampling, enough for a 30-100ms flick to
# yield 6-20 samples without saturating GetCursorPos calls.
RECORD_POLL_INTERVAL_SECONDS = 0.005
# Hard ceiling so a stuck/forgotten button doesn't lock the recorder forever.
RECORD_MAX_PRESS_DURATION_SECONDS = 3.0
# How long to wait for the user to actually start the swipe after pressing
# the GUI "Record" button before giving up.
RECORD_WAIT_FOR_PRESS_TIMEOUT_SECONDS = 8.0
# Reject as not-a-swipe if total travel is below this — guards against the
# user accidentally just clicking instead of dragging.
RECORD_MIN_DISTANCE_PX = 12


def is_left_button_down() -> bool:
    """True if the physical left mouse button is currently held.

    Uses Win32 GetAsyncKeyState so it works without window focus and without
    pulling in pynput or mouse packages.
    """
    state = ctypes.windll.user32.GetAsyncKeyState(_VK_LBUTTON)
    return bool(state & _HIGH_BIT_MASK)


class SwipeRecording:
    """Result of a single recording session."""

    def __init__(self, samples: Sequence[SwipeSample]):
        self.samples: List[SwipeSample] = [
            (float(t), int(dx), int(dy)) for (t, dx, dy) in samples
        ]

    @property
    def duration_seconds(self) -> float:
        return self.samples[-1][0] if self.samples else 0.0

    @property
    def total_distance_px(self) -> float:
        if not self.samples:
            return 0.0
        # Sum of Euclidean step distances along the recorded path.
        prev_dx, prev_dy = 0, 0
        total = 0.0
        for _, dx, dy in self.samples:
            total += ((dx - prev_dx) ** 2 + (dy - prev_dy) ** 2) ** 0.5
            prev_dx, prev_dy = dx, dy
        return total

    @property
    def endpoint_offset(self) -> Tuple[int, int]:
        if not self.samples:
            return (0, 0)
        _, dx, dy = self.samples[-1]
        return (dx, dy)

    def summary(self) -> str:
        end_dx, end_dy = self.endpoint_offset
        return (
            f"{len(self.samples)} t. · {self.duration_seconds * 1000:.0f}ms · "
            f"end ({end_dx:+d},{end_dy:+d})px"
        )


def record_swipe(
    *,
    wait_timeout: float = RECORD_WAIT_FOR_PRESS_TIMEOUT_SECONDS,
    max_press_duration: float = RECORD_MAX_PRESS_DURATION_SECONDS,
    poll_interval: float = RECORD_POLL_INTERVAL_SECONDS,
) -> Optional[SwipeRecording]:
    """Block until the user does one left-button drag, return the trajectory.

    Caller is expected to spin this in a worker thread — it busy-waits on
    GetAsyncKeyState and would freeze the Qt event loop if run on the GUI
    thread.

    The recorder first drains any currently-held click (so pressing the GUI
    "Record" button itself doesn't count as the start of the swipe), then
    polls for a fresh press, then samples cursor position until release.
    """
    # Drain a click that may still be held (e.g. the click that triggered the
    # recorder). We only want to start once the user has fully released.
    drain_deadline = time.perf_counter() + 1.0
    while is_left_button_down():
        if time.perf_counter() > drain_deadline:
            # Unusual: button still down a full second later. Bail rather
            # than risk capturing the wrong gesture.
            return None
        time.sleep(poll_interval)

    # Wait for the actual swipe press.
    wait_deadline = time.perf_counter() + wait_timeout
    while not is_left_button_down():
        if time.perf_counter() > wait_deadline:
            return None
        time.sleep(poll_interval)

    # Press detected — sample until release.
    press_time = time.perf_counter()
    start_x, start_y = pyautogui.position()
    samples: List[SwipeSample] = [(0.0, 0, 0)]
    press_deadline = press_time + max_press_duration

    while is_left_button_down():
        now = time.perf_counter()
        if now > press_deadline:
            # User held forever — capture what we have and stop. Replay will
            # honour the original timing; an over-long press is still a valid
            # gesture, we just don't want to wait indefinitely.
            break
        cur_x, cur_y = pyautogui.position()
        t = now - press_time
        dx = cur_x - start_x
        dy = cur_y - start_y
        # Skip duplicate samples that share both timestamp resolution and
        # position with the previous one — common when the cursor is stationary.
        last_t, last_dx, last_dy = samples[-1]
        if (dx, dy) != (last_dx, last_dy) or t - last_t > 0.010:
            samples.append((t, dx, dy))
        time.sleep(poll_interval)

    recording = SwipeRecording(samples)
    if recording.total_distance_px < RECORD_MIN_DISTANCE_PX:
        # User probably just clicked without dragging. Don't save a "swipe"
        # that's actually a tap; force them to redo it.
        return None
    return recording


def rotate_samples(
    samples: Sequence[SwipeSample], direction: str
) -> List[SwipeSample]:
    """Map the canonical right-direction recording to one of the 4 cardinals.

    Screen coordinates have +y pointing down, so a clockwise rotation of 90°
    sends (+1, 0) → (0, +1) via (x, y) → (-y, x).
    """
    if direction == "right":
        return [(t, dx, dy) for (t, dx, dy) in samples]
    if direction == "left":
        return [(t, -dx, -dy) for (t, dx, dy) in samples]
    if direction == "down":
        return [(t, -dy, dx) for (t, dx, dy) in samples]
    if direction == "up":
        return [(t, dy, -dx) for (t, dx, dy) in samples]
    raise ValueError(f"Unknown swipe direction: {direction!r}")


def play_recording(
    recording: SwipeRecording,
    direction: str,
    *,
    scale_factor: float = 1.0,
    speed_factor: float = 1.0,
    post_hold_seconds: float = 0.0,
    mouse_down,
    move_to,
    mouse_up,
    sleep,
    perf_counter,
) -> None:
    """Replay a recorded swipe at its original cadence, in any direction.

    The four function args (mouse_down, move_to, mouse_up, sleep, perf_counter)
    are injected so tests can capture event order without touching pyautogui
    or wall-clock time. In production, runtime.swipe() passes pyautogui's real
    handlers and time.sleep / time.perf_counter.

    ``post_hold_seconds`` pauses at the endpoint before the button is lifted.
    A real hand keeps the mouse still for a moment after the flick, and
    BlueStacks computes fling velocity from the trailing events -- replaying
    without that tail measured 5 rejected swipes out of 7 on 2026-08-24, while
    the same recording with a tail had 83 out of 83 accepted.
    """
    rotated = rotate_samples(recording.samples, direction)
    if not rotated:
        return
    resolved_scale = max(0.25, min(4.0, float(scale_factor)))
    # speed_factor compresses the recording's timeline: 2.0 plays the flick in
    # half the original time (positions unchanged, so velocity doubles). Faster
    # is not automatically better -- above ~1.5x the gesture gets short enough
    # that BlueStacks stops classifying it as a fling -- so the recording's own
    # pace is the default and this stays a tuning knob.
    resolved_speed = max(0.25, min(10.0, float(speed_factor)))
    start_x, start_y = pyautogui.position()
    mouse_down(button="left", _pause=False)
    replay_start = perf_counter()
    for t, dx, dy in rotated:
        target_time = replay_start + t / resolved_speed
        wait = target_time - perf_counter()
        if wait > 0:
            sleep(wait)
        scaled_dx = int(round(dx * resolved_scale))
        scaled_dy = int(round(dy * resolved_scale))
        move_to(start_x + scaled_dx, start_y + scaled_dy, duration=0, _pause=False)
    if post_hold_seconds > 0:
        sleep(post_hold_seconds)
    mouse_up(button="left", _pause=False)


def save_profile(recording: SwipeRecording, path: Path = SWIPE_PROFILE_PATH) -> None:
    """Persist a recording so the bot uses it on next launch."""
    payload = {
        "version": SWIPE_PROFILE_VERSION,
        "canonical_direction": "right",
        "samples": [[t, dx, dy] for (t, dx, dy) in recording.samples],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_profile(path: Path = SWIPE_PROFILE_PATH) -> Optional[SwipeRecording]:
    """Read the persisted recording, or None if none exists or it's malformed."""
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    raw_samples = payload.get("samples")
    if not isinstance(raw_samples, list) or not raw_samples:
        return None
    samples: List[SwipeSample] = []
    for entry in raw_samples:
        if not isinstance(entry, (list, tuple)) or len(entry) != 3:
            return None
        try:
            t, dx, dy = float(entry[0]), int(entry[1]), int(entry[2])
        except (TypeError, ValueError):
            return None
        samples.append((t, dx, dy))
    return SwipeRecording(samples)
