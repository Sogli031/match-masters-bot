import atexit
import threading
import time
from collections import OrderedDict, deque
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from pathlib import Path

import cv2
import numpy as np
import pyautogui
from PIL import Image

try:
    import mss as _mss_module
except ImportError:
    _mss_module = None

AUTO_LATEST_BOARD_FILENAME = "Debug/auto_latest_board.png"
AUTO_VISUAL_HASH_SIZE = 32
AUTO_VISUAL_HASH_MAX_DISTANCE = 96
AUTO_MOTION_THRESHOLD = 2.0
# After the board settles the game rains small white "reward" stars across the
# cells. They are near-white (high brightness, near-zero saturation) and purely
# cosmetic — recognition reads the gem colors underneath them fine. But they
# move pixels, so auto_core_motion_score used to count them as board motion,
# which kept the stability gate (_can_count_visual_animation in runtime.py)
# resetting and forced the slow 3-scan "suspicious" path. We exclude sparkle
# pixels (near-white in EITHER frame) from the core motion measurement so a
# settled board reads as still. Saturated gems (incl. bright yellow) stay well
# above the saturation cutoff, and a genuinely falling white gem still changes
# the recognized board signature, which is the real guard against acting early.
AUTO_SPARKLE_VALUE_MIN = 230
AUTO_SPARKLE_SATURATION_MAX = 45

_debug_screenshot_writer = ThreadPoolExecutor(max_workers=1, thread_name_prefix="debug-screenshot")
_debug_screenshot_futures = []
# Bounded LRU, not a plain dict: keys are debug paths, and with run recording
# on every move mints fresh ones (Debug/runs/<timestamp>/board.png, ...), each
# holding a full RGB frame copy. Unbounded this was the process' main leak --
# a few hundred KB per move for the whole session (2026-08-23 review). Every
# consumer reads a key back right after writing it (or re-writes a fixed key
# like auto_latest_board.png every scan), so a small LRU keeps the contract.
_LATEST_DEBUG_SCREENSHOT_CAPACITY = 16
_latest_debug_screenshots = OrderedDict()
_latest_debug_screenshots_lock = threading.Lock()


def _remember_latest_screenshot(key, image):
    with _latest_debug_screenshots_lock:
        _latest_debug_screenshots[key] = image
        _latest_debug_screenshots.move_to_end(key)
        while len(_latest_debug_screenshots) > _LATEST_DEBUG_SCREENSHOT_CAPACITY:
            _latest_debug_screenshots.popitem(last=False)


def _get_latest_screenshot(key):
    with _latest_debug_screenshots_lock:
        image = _latest_debug_screenshots.get(key)
        if image is not None:
            # A key that is read repeatedly (the fixed auto-board key between
            # re-captures) must not be the one the eviction picks.
            _latest_debug_screenshots.move_to_end(key)
        return image

def auto_visual_fingerprint(image, hash_size=AUTO_VISUAL_HASH_SIZE):
    if image is None:
        return None

    resample_filter = Image.Resampling.BILINEAR if hasattr(Image, "Resampling") else Image.BILINEAR
    gray = image.convert("L").resize((hash_size, hash_size), resample_filter)
    pixels = np.asarray(gray, dtype=np.float32)
    mean_value = float(pixels.mean())
    fingerprint = 0
    for bit in (pixels >= mean_value).ravel():
        fingerprint = (fingerprint << 1) | int(bit)
    return fingerprint

def auto_visual_hash_distance(previous_hash, current_hash):
    if previous_hash is None or current_hash is None:
        return None
    return int(previous_hash ^ current_hash).bit_count()

def auto_motion_score(previous_image, current_image):
    if previous_image is None or current_image is None:
        return 0.0

    previous_gray = np.asarray(previous_image.convert("L"), dtype=np.uint8)
    current_gray_image = current_image.convert("L")
    if current_gray_image.size != previous_image.size:
        current_gray_image = current_gray_image.resize(previous_image.size)
    current_gray = np.asarray(current_gray_image, dtype=np.uint8)
    return float(cv2.absdiff(previous_gray, current_gray).mean())


def _sparkle_mask(rgb_array):
    """Boolean mask of near-white, low-saturation pixels (the falling reward
    stars). Computed per frame so callers can OR two frames together and drop
    any pixel a sparkle touches in either one."""
    hsv = cv2.cvtColor(rgb_array, cv2.COLOR_RGB2HSV)
    saturation = hsv[:, :, 1]
    value = hsv[:, :, 2]
    return (value >= AUTO_SPARKLE_VALUE_MIN) & (saturation <= AUTO_SPARKLE_SATURATION_MAX)


def auto_core_motion_score(
    previous_image,
    current_image,
    board_size=None,
    core_fraction=0.6,
):
    if previous_image is None or current_image is None:
        return 0.0

    try:
        board_size = int(board_size or 0)
    except (TypeError, ValueError):
        board_size = 0
    if board_size <= 0:
        return auto_motion_score(previous_image, current_image)

    previous_rgb = np.asarray(previous_image.convert("RGB"), dtype=np.uint8)
    current_rgb_image = current_image.convert("RGB")
    if current_rgb_image.size != previous_image.size:
        current_rgb_image = current_rgb_image.resize(previous_image.size)
    current_rgb = np.asarray(current_rgb_image, dtype=np.uint8)

    # RGB2GRAY uses the same ITU-R 601 coefficients as PIL's "L" mode, so the
    # diff scale stays compatible with the existing AUTO_MOTION_THRESHOLD.
    previous_gray = cv2.cvtColor(previous_rgb, cv2.COLOR_RGB2GRAY)
    current_gray = cv2.cvtColor(current_rgb, cv2.COLOR_RGB2GRAY)

    height, width = previous_gray.shape
    mask = np.zeros((height, width), dtype=bool)
    core_fraction = min(1.0, max(0.1, float(core_fraction)))
    margin_fraction = (1.0 - core_fraction) / 2.0
    for row in range(board_size):
        y1 = int(round((row + margin_fraction) * height / board_size))
        y2 = int(round((row + 1 - margin_fraction) * height / board_size))
        for col in range(board_size):
            x1 = int(round((col + margin_fraction) * width / board_size))
            x2 = int(round((col + 1 - margin_fraction) * width / board_size))
            if y2 > y1 and x2 > x1:
                mask[y1:y2, x1:x2] = True
    if not mask.any():
        return auto_motion_score(previous_image, current_image)

    diff = cv2.absdiff(previous_gray, current_gray)
    sparkle = _sparkle_mask(previous_rgb) | _sparkle_mask(current_rgb)
    core_non_sparkle = mask & ~sparkle
    if not core_non_sparkle.any():
        # Core is entirely sparkle this frame (degenerate) — fall back to the
        # raw core mean rather than silently reporting a still board.
        return float(diff[mask].mean())
    return float(diff[core_non_sparkle].mean())


# AUTO_MOTION_THRESHOLD was tuned when auto scans ran ~60-80ms apart. With
# back-to-back scan chaining frames can arrive ~30ms apart, halving the pixel
# displacement an animation produces between two consecutive frames — enough to
# slip under the threshold while tiles are still moving. The tracker therefore
# scores motion against the newest frame that is at least this old, keeping the
# measured magnitude comparable no matter how fast the scan loop runs.
AUTO_MOTION_MIN_FRAME_GAP_SECONDS = 0.045
AUTO_MOTION_MAX_TRACKED_FRAMES = 8


class AutoMotionTracker:
    """Rolling frame history that yields dt-aware motion scores for auto mode."""

    def __init__(
        self,
        min_gap_seconds=AUTO_MOTION_MIN_FRAME_GAP_SECONDS,
        max_frames=AUTO_MOTION_MAX_TRACKED_FRAMES,
        clock=time.monotonic,
    ):
        self._min_gap = float(min_gap_seconds)
        self._clock = clock
        self._frames = deque(maxlen=max(1, int(max_frames)))

    def reset(self):
        self._frames.clear()

    def _reference_frame(self, now):
        for timestamp, frame in reversed(self._frames):
            if now - timestamp >= self._min_gap:
                return frame
        if self._frames:
            # Every stored frame is too fresh; the oldest one is the closest
            # approximation of the wanted gap.
            return self._frames[0][1]
        return None

    def observe(self, image, board_size=None):
        """Record `image` and return (motion_score, core_motion_score) measured
        against the dt-appropriate reference frame (0.0 on the first frame)."""
        now = self._clock()
        reference = self._reference_frame(now)
        motion = auto_motion_score(reference, image)
        core_motion = auto_core_motion_score(reference, image, board_size=board_size)
        self._frames.append((now, image))
        return motion, core_motion


def _debug_screenshot_key(path):
    return str(Path(path))

def _save_debug_screenshot(image, output_path):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path)
    return output_path

def _queue_debug_screenshot_write(image, output_path):
    if output_path is None:
        return None
    image_copy = image.copy()
    output_path = Path(output_path)
    future = _debug_screenshot_writer.submit(_save_debug_screenshot, image_copy, output_path)
    # Prune finished writes while appending the new one: entries were only ever
    # removed by an explicit flush of their own path, so completed futures for
    # never-flushed paths piled up for the whole session. A finished write
    # needs no bookkeeping -- flush exists to wait, and there is nothing left
    # to wait for. A finished FAILED write is dropped too: these are debug
    # artefacts, and a save error must not resurface minutes later under an
    # unrelated flush call.
    _debug_screenshot_futures[:] = [
        entry for entry in _debug_screenshot_futures if not entry[1].done()
    ]
    _debug_screenshot_futures.append((_debug_screenshot_key(output_path), future))
    return future

def get_latest_debug_screenshot(path):
    cached = _get_latest_screenshot(_debug_screenshot_key(path))
    if cached is None:
        return None
    return cached.copy()

def remember_debug_screenshot(path, image):
    _remember_latest_screenshot(_debug_screenshot_key(path), image.copy())

def flush_debug_screenshot_writes(path=None):
    requested_key = _debug_screenshot_key(Path(path)) if path is not None else None
    remaining = []
    error = None
    for key, future in _debug_screenshot_futures:
        if requested_key is None or key == requested_key:
            try:
                future.result()
            except Exception as exc:
                # Keep draining: one failed save must not leave the rest of
                # the queue behind (the list used to stay untouched on a
                # raise, so the same future was re-raised on every flush).
                if error is None:
                    error = exc
        else:
            remaining.append((key, future))
    _debug_screenshot_futures[:] = remaining
    if error is not None:
        raise error

def _shutdown_debug_screenshot_writer():
    flush_debug_screenshot_writes()
    _debug_screenshot_writer.shutdown(wait=True)
    try:
        _screenshot_grab_executor.submit(_close_mss_grabber_on_owner_thread).result(timeout=2.0)
    except Exception:
        pass
    _screenshot_grab_executor.shutdown(wait=False)

# mss grabs only the requested region via the GDI path (~5ms) instead of
# pyautogui's full-screen grab + crop (~17ms). mss keeps its GDI handles
# (screen DC, memory DC, bitmap) in a per-instance threading.local, so an
# instance is only usable -- and only closeable -- on the thread that created
# it. Callers come from many threads (scan worker, prep worker, per-move check
# workers...), and a per-thread instance in a short-lived thread leaks its GDI
# handles forever; enough moves exhaust the process GDI quota and EVERY screen
# grab (and even Qt painting) starts failing. So all mss work funnels through
# one dedicated executor thread that owns the single grabber instance.
_screenshot_grab_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="screen-grab")
_screenshot_grab_executor_lock = threading.Lock()
_mss_grabber = None  # touched only from the executor thread
_MSS_GRAB_TIMEOUT_SECONDS = 2.0


def _mss_grab_on_owner_thread(region):
    global _mss_grabber
    try:
        if _mss_grabber is None:
            _mss_grabber = _mss_module.mss()
        if region is None:
            monitor = _mss_grabber.monitors[1]
        else:
            left, top, width, height = region
            monitor = {
                "left": int(left),
                "top": int(top),
                "width": int(width),
                "height": int(height),
            }
        shot = _mss_grabber.grab(monitor)
        return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
    except Exception:
        # Release the broken grabber's GDI handles before dropping it, or the
        # retry path would slowly leak DCs/bitmaps on every failure.
        try:
            if _mss_grabber is not None:
                _mss_grabber.close()
        except Exception:
            pass
        _mss_grabber = None
        return None


def _close_mss_grabber_on_owner_thread():
    global _mss_grabber
    try:
        if _mss_grabber is not None:
            _mss_grabber.close()
    except Exception:
        pass
    _mss_grabber = None


def _replace_stalled_screenshot_grab_executor(stalled_executor):
    """Swap out a grab worker that did not return before the hard timeout.

    A single-worker executor otherwise keeps every future queued behind the
    stuck grab forever, adding two seconds to every subsequent scan.  Only the
    caller that still observes the same executor performs the replacement.
    """
    global _screenshot_grab_executor, _mss_grabber
    with _screenshot_grab_executor_lock:
        if _screenshot_grab_executor is not stalled_executor:
            return
        _screenshot_grab_executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="screen-grab",
        )
        _mss_grabber = None
    stalled_executor.shutdown(wait=False, cancel_futures=True)


def _mss_grab(region):
    if _mss_module is None:
        return None
    with _screenshot_grab_executor_lock:
        executor = _screenshot_grab_executor
    try:
        future = executor.submit(_mss_grab_on_owner_thread, region)
        return future.result(timeout=_MSS_GRAB_TIMEOUT_SECONDS)
    except FuturesTimeoutError:
        future.cancel()
        _replace_stalled_screenshot_grab_executor(executor)
        return None
    except Exception:
        return None


def capture_debug_screenshot(output_path=None, region=None, latest_key=None, write_to_disk=True):
    image = _mss_grab(region)
    if image is None:
        image = pyautogui.screenshot(region=region)
    for key in (output_path, latest_key):
        if key is not None:
            _remember_latest_screenshot(_debug_screenshot_key(key), image.copy())
    if write_to_disk:
        _queue_debug_screenshot_write(image, output_path)
    return image

def load_auto_board_image(path=AUTO_LATEST_BOARD_FILENAME):
    cached = _get_latest_screenshot(_debug_screenshot_key(path))
    if cached is not None:
        return cached.copy()
    try:
        with Image.open(path) as image:
            return image.convert("RGB")
    except (FileNotFoundError, OSError):
        return None

atexit.register(_shutdown_debug_screenshot_writer)
