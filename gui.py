import copy
import json
import os
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import pyautogui
from PyQt5 import QtCore, QtGui, QtWidgets

import capture
import board_source
import matchmasters_launcher
import net_toggle
import perk_detection
import recognition
import runtime
import screen_state_reader
import swipe_recorder
from game_mode_detection import (
    detect_game_mode_from_screen,
    detect_mode_icon,
    mode_icon_region,
    prefer_hot_color_board_detection,
)
from board_profiles import (
    BOARD_PROFILES,
    BoardCalibrationError,
    DEFAULT_PROFILE,
    REGULAR_PROFILE,
    SUPERSIZE_PROFILE,
    save_board_calibration,
    validate_board_calibration,
)
from board_source import (
    BOARD_SOURCE_AUTO,
    BOARD_SOURCE_ML,
    BOARD_SOURCE_OPTIONS,
    normalize_board_source,
)
from capture import (
    AUTO_LATEST_BOARD_FILENAME,
    auto_core_motion_score,
    auto_motion_score,
    auto_visual_fingerprint,
    load_auto_board_image,
)
from ml_recognition_runtime import (
    ML_RECOGNITION_ONLY,
    normalize_ml_recognition_mode,
)
from move_strategy import (
    BLOCKED,
    ENERGIZED_COLOR_LABELS,
    ENERGIZED_SELECTABLE_COLORS,
    GameMode,
    normalize_energized_colors,
    STRATEGY_SOLO_6,
    STRATEGY_VERSUS_2,
    normalize_game_mode,
    strategy_mode_from_showdown,
)
from recognition import (
    GAME_MODE_OPTIONS,
    SPECIAL_PIECE_MODE_AUTO,
    SPECIAL_PIECE_MODE_OPTIONS,
    normalize_special_piece_mode,
)
from runtime import (
    AUTO_BOOSTER_STUCK_TICK_THRESHOLD,
    AUTO_POST_BOOSTER_COOLDOWN_SECONDS,
    AUTO_POST_MOVE_COOLDOWN_SECONDS,
    AUTO_POST_PERK_COOLDOWN_SECONDS,
    AUTO_SCAN_INTERVAL_MS,
    AUTO_UNCHANGED_BOARD_REPLAY_TICK_THRESHOLD,
    BOOSTER_ACTION_NONE,
    BOOSTER_ACTION_OPTIONS,
    BOOSTER_MAX_CHARGE,
    LIVE_LOOKAHEAD_BEAM_WIDTH,
    LIVE_LOOKAHEAD_CANDIDATES,
    LIVE_LOOKAHEAD_DEPTH,
    SOLO_CHALLENGE_LOOKAHEAD_BEAM_WIDTH,
    SOLO_CHALLENGE_LOOKAHEAD_CANDIDATES,
    SOLO_CHALLENGE_LOOKAHEAD_DEPTH,
    MANUAL_RECOGNITION_RETRY_INTERVAL_MS,
    PERK_NONE,
    CheckBestMoveRequest,
    CheckBestMoveResult,
    AutoMoveStability,
    normalize_booster_action_mode,
    run_check_best_move_request,
)
from window_geometry import client_rect_for_window, find_bluestacks_window


RESTART_APP_EXIT_CODE = 73
GUI_STATE_PATH = Path(__file__).resolve().with_name("gui_state.json")
GUI_STATE_VERSION = 1


def _replace_process_in_current_console(script_path):
    script_path = Path(script_path).resolve()
    executable = sys.executable
    # Windows' execv command-line reconstruction can split an unquoted script
    # path at spaces.  Run from the script directory and pass only its basename
    # so the process replacement remains in this console without a spaced path
    # in argv.
    os.chdir(script_path.parent)
    command = [executable, script_path.name, *sys.argv[1:]]
    os.execv(executable, command)


GUI_GAME_MODE_OPTIONS = tuple(
    mode
    for mode in GAME_MODE_OPTIONS
    if mode
    not in {
        GameMode.BOUNTY,
        GameMode.MULTIPLIER_MUSHROOMS,
    }
)
ENERGIZED_NO_COLOR = 0


def fill_energized_color_combo(combo, selected=None):
    """Populate a combo with the Energized-selectable colors ("(nema)" first)."""
    combo.clear()
    combo.addItem("(nema)", ENERGIZED_NO_COLOR)
    for color in ENERGIZED_SELECTABLE_COLORS:
        combo.addItem(ENERGIZED_COLOR_LABELS.get(color, str(color)), int(color))
    index = combo.findData(int(selected) if selected else ENERGIZED_NO_COLOR)
    combo.setCurrentIndex(index if index >= 0 else 0)


class EnergizedColorsDialog(QtWidgets.QDialog):
    """Pick the two colors that fill the booster in Energized."""

    def __init__(self, parent=None, colors=()):
        super().__init__(parent)
        self.setWindowTitle("Energized: boje koje pune booster")
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(
            QtWidgets.QLabel(
                "Izaberi dve boje koje (pored plave) pune booster:", self
            )
        )
        selected = list(normalize_energized_colors(colors))
        selected += [None] * (2 - len(selected))
        self.boxes = []
        for index, label in enumerate(("Boja 1", "Boja 2")):
            row = QtWidgets.QHBoxLayout()
            row.addWidget(QtWidgets.QLabel(label, self))
            combo = QtWidgets.QComboBox(self)
            fill_energized_color_combo(combo, selected[index])
            row.addWidget(combo, 1)
            layout.addLayout(row)
            self.boxes.append(combo)

        def _on_changed(box_idx):
            other_idx = 1 - box_idx
            c1 = self.boxes[box_idx].currentData()
            c2 = self.boxes[other_idx].currentData()
            if c1 and c1 == c2:
                for col in ENERGIZED_SELECTABLE_COLORS:
                    if col != c1:
                        idx = self.boxes[other_idx].findData(int(col))
                        if idx >= 0:
                            self.boxes[other_idx].setCurrentIndex(idx)
                            break

        self.boxes[0].currentIndexChanged.connect(lambda: _on_changed(0))
        self.boxes[1].currentIndexChanged.connect(lambda: _on_changed(1))

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected_colors(self):
        return normalize_energized_colors(
            box.currentData() for box in self.boxes
        )


# Recognition is ML-only. The template/shadow/hybrid/first/off modes were
# removed from the UI; ML only is the single supported mode.
ML_RECOGNITION_OPTIONS = (
    ("ML only", ML_RECOGNITION_ONLY),
)
MANUAL_RECOGNITION_MAX_RETRIES = 6


@dataclass(frozen=True)
class AutoScanRequest:
    mode: object
    special_piece_mode: str
    selected_profile: str
    board_source: str = BOARD_SOURCE_ML
    ml_recognition_mode: str = ML_RECOGNITION_ONLY
    # First scan of a fresh auto session: drop the motion tracker's frame
    # history so motion is not measured against a frame from before the toggle.
    reset_motion: bool = False
    detect_turn_owner: bool = False
    auto_mode_detection: bool = False


@dataclass(frozen=True)
class AutoScanResult:
    game_board: object
    special_game_board: object
    board_image: object
    # Filled by the persistent scan worker so the GUI thread only consumes;
    # None on the legacy/synchronous path, where the handler computes them.
    visual_hash: object = None
    motion_score: object = None
    core_motion_score: object = None
    replay_detection: object = None
    turn_owner: object = None
    mode_detection: object = None
    hot_color_state: object = None
    board_source: str = BOARD_SOURCE_ML
    board_source_fallback_reason: str | None = None
    # Memory source only: True when the engine's GameState says it accepts a
    # swipe right now (MovePlaying), False when it is mid-processing, None when
    # the snapshot cannot say (older agent) or the board came off pixels.
    memory_move_ready: bool | None = None
    # Memory source only: bot colors the live rules say charge the booster
    # (MatchRulesModel.colorComboEnergy/_colorEnergyOverride), None = unknown.
    memory_charge_colors: tuple | None = None


class _CalibrationOverlay(QtWidgets.QWidget):
    """Transparent two-click overlay that leaves the game visible underneath."""

    completed = QtCore.pyqtSignal(object, object)
    cancelled = QtCore.pyqtSignal()

    def __init__(self):
        super().__init__(None)
        self._first_point = None
        self._finished = False
        self.setWindowFlags(
            QtCore.Qt.FramelessWindowHint
            | QtCore.Qt.WindowStaysOnTopHint
            | QtCore.Qt.Tool
        )
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        self.setMouseTracking(True)
        self.setCursor(QtCore.Qt.CrossCursor)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)

        screens = QtWidgets.QApplication.screens()
        geometry = screens[0].geometry()
        for screen in screens[1:]:
            geometry = geometry.united(screen.geometry())
        self.setGeometry(geometry)

    def _instruction(self):
        if self._first_point is None:
            return "Klikni CENTAR GORNJEG LEVOG polja table"
        return "Klikni CENTAR DONJEG DESNOG polja table"

    def paintEvent(self, _event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.fillRect(self.rect(), QtGui.QColor(0, 0, 0, 24))
        banner_width = min(650, max(420, self.width() - 80))
        banner = QtCore.QRect(
            (self.width() - banner_width) // 2,
            35,
            banner_width,
            82,
        )
        painter.setBrush(QtGui.QColor(20, 20, 28, 235))
        painter.setPen(QtGui.QPen(QtGui.QColor(80, 190, 255), 2))
        painter.drawRoundedRect(banner, 12, 12)
        painter.setPen(QtGui.QColor(255, 255, 255))
        font = painter.font()
        font.setPointSize(15)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(banner.adjusted(16, 8, -16, -26), QtCore.Qt.AlignCenter, self._instruction())
        font.setPointSize(10)
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(QtGui.QColor(205, 205, 215))
        painter.drawText(
            banner.adjusted(16, 45, -16, -5),
            QtCore.Qt.AlignCenter,
            "Desni klik ili Esc = odustani; klikovi ne ulaze u igru",
        )

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.RightButton:
            self._cancel()
            return
        if event.button() != QtCore.Qt.LeftButton:
            return
        point = pyautogui.position()
        captured = (int(point.x), int(point.y))
        if self._first_point is None:
            self._first_point = captured
            self.update()
            return
        self._finished = True
        first = self._first_point
        self.close()
        self.completed.emit(first, captured)

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key_Escape:
            self._cancel()
            return
        super().keyPressEvent(event)

    def _cancel(self):
        if self._finished:
            return
        self._finished = True
        self.close()
        self.cancelled.emit()

    def closeEvent(self, event):
        was_finished = self._finished
        self._finished = True
        super().closeEvent(event)
        if not was_finished:
            self.cancelled.emit()


# Inputs for the speculative move-request prep: while the stability gate is one
# confirming scan away, the screen-state OCR and perk detection run in the
# background so the confirmed board can play without redoing them synchronously.
@dataclass(frozen=True)
class AutoPrepRequest:
    auto_state_enabled: bool
    board_profile: object
    special_piece_mode: str
    manual_booster_charge: object
    manual_remaining_moves: object
    showdown: bool
    party: bool
    total_rounds: object
    require_stable_state: bool
    solo_challenge: bool = False
    auto_round_detection: bool = False
    infinite_moves: bool = False


def _accepted_auto_score_signature(auto_read):
    score = getattr(auto_read, "score", None)
    if score is None or not getattr(score, "accepted", False):
        return None
    our_score = getattr(score, "our_score", None)
    opponent_score = getattr(score, "opponent_score", None)
    if our_score is None or opponent_score is None:
        return None
    return int(our_score), int(opponent_score)


def _state_confirmation_region(read):
    """Crop that the second ``Cekaj anim.`` frame has to agree on.

    The move dots are the field that actually animates between reads (the
    booster text and round pip sit still far more often), so their region is the
    one worth watching. Falls back to the booster crop, then to nothing.
    """
    for field_name in ("remaining_moves", "booster_charge"):
        field = getattr(read, field_name, None)
        region = getattr(field, "region", None)
        if (
            isinstance(region, (tuple, list))
            and len(region) == 4
            and all(isinstance(value, (int, float)) for value in region)
            and region[2] > 0
            and region[3] > 0
        ):
            return tuple(int(value) for value in region)
    return None


def _wait_for_state_crop_still(previous_image, region, max_seconds):
    """Wait out the HUD animation by watching it, not by guessing its length.

    Mirrors runtime._wait_until_board_still, which replaced the same kind of flat
    sleep on the board path. Returns once the crop stops changing, or when the
    budget runs out -- so an animating HUD is still given the full old delay,
    while a settled one costs a single poll instead of 80ms.
    """
    if max_seconds <= 0:
        return
    if previous_image is None or region is None:
        # No reference frame: keep the flat wait rather than skipping it, so a
        # miss here can never shorten the animation guard.
        time.sleep(max_seconds)
        return
    left, top, width, height = region
    try:
        previous_crop = previous_image.crop((left, top, left + width, top + height))
    except Exception:
        time.sleep(max_seconds)
        return
    deadline = time.perf_counter() + max_seconds
    while True:
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            return
        time.sleep(min(AUTO_STATE_STILL_POLL_SECONDS, remaining))
        current_crop = capture.capture_debug_screenshot(
            output_path=None,
            region=region,
            write_to_disk=False,
        )
        if current_crop is None:
            return
        if auto_motion_score(previous_crop, current_crop) <= AUTO_STATE_STILL_MOTION_MAX:
            return
        previous_crop = current_crop


def _capture_stable_auto_state(request):
    """Capture visible state; optionally require two matching clear frames.

    Booster, move and round reads become a hard gate only when Cekaj anim. is
    enabled. Score OCR remains useful input but never blocks play.
    """
    recognition.apply_board_profile(request.board_profile)
    require_stable_state = bool(getattr(request, "require_stable_state", False))
    required_frames = AUTO_STATE_CONFIRMATION_FRAMES if require_stable_state else 1
    latest_read = None
    latest_image = None
    score_samples = []
    state_samples = []
    captured_reads = []
    captured_images = []
    consecutive_signature = None
    consecutive_count = 0
    state_reason = ""

    for frame_index in range(required_frames):
        latest_image = capture.capture_debug_screenshot(
            output_path=None,
            region=None,
            write_to_disk=False,
        )
        latest_read = screen_state_reader.read_screen_state(
            latest_image,
            board_profile=request.board_profile,
            special_piece_mode=request.special_piece_mode,
            manual_booster_charge=request.manual_booster_charge,
            manual_remaining_moves=(
                None
                if getattr(request, "infinite_moves", False)
                else request.manual_remaining_moves
            ),
            showdown=request.showdown,
            party=request.party,
            solo_challenge=getattr(request, "solo_challenge", False),
            total_rounds=(
                None
                if getattr(request, "auto_round_detection", False)
                else getattr(request, "total_rounds", None)
            ),
            auto_detect_total_rounds=bool(
                getattr(request, "auto_round_detection", False)
            ),
        )
        captured_reads.append(latest_read)
        captured_images.append(latest_image)
        score_signature = _accepted_auto_score_signature(latest_read)
        if score_signature is not None:
            score_samples.append(score_signature)

        state_signature, state_reason = _required_auto_state_signature(
            latest_read,
            request,
        )
        state_samples.append(state_signature)
        if state_signature is not None and state_signature == consecutive_signature:
            consecutive_count += 1
        elif state_signature is not None:
            consecutive_signature = state_signature
            consecutive_count = 1
        else:
            consecutive_signature = None
            consecutive_count = 0

        if (
            require_stable_state
            and consecutive_count < required_frames
            and len(captured_reads) >= 2
        ):
            confirmed_index = _confirmed_activate_animation_frame(
                captured_reads[-2:],
                request,
            )
            if confirmed_index is not None:
                # ACTIVATE continuously pulses between readable text and a
                # distorted near-full meter. Use the fully readable frame from
                # this same 80 ms pair; never carry a full-booster latch into a
                # later capture or across an activation.
                latest_read = captured_reads[-2:][confirmed_index]
                latest_image = captured_images[-2:][confirmed_index]
                consecutive_signature = _required_auto_state_signature(
                    latest_read,
                    request,
                )[0]
                consecutive_count = required_frames

        if consecutive_count >= required_frames:
            state_reason = ""
            break
        if frame_index + 1 < required_frames:
            _wait_for_state_crop_still(
                latest_image,
                _state_confirmation_region(latest_read),
                AUTO_STATE_CONFIRMATION_DELAY_SECONDS,
            )

    state_stable = bool(
        not require_stable_state or consecutive_count >= AUTO_STATE_CONFIRMATION_FRAMES
    )
    if require_stable_state and not state_stable and not state_reason:
        state_reason = "ocitanja stanja se jos menjaju"
    return (
        latest_read,
        latest_image,
        True,
        tuple(score_samples),
        state_stable,
        tuple(state_samples),
        state_reason,
    )


@dataclass(frozen=True)
class AutoPrepResult:
    auto_read: object
    state_image: object
    perk_detections: tuple
    auto_state_enabled: bool
    created_at: float
    score_stable: bool = True
    score_samples: tuple = ()
    state_stable: bool = True
    state_samples: tuple = ()
    state_reason: str = ""
    stable_state_required: bool = False


def _auto_prep_has_confirmed_score(prep):
    if prep is None:
        return False
    if not prep.auto_state_enabled:
        return True
    # Auto state still has to be captured successfully, but score recognition
    # is no longer a play gate. Board stability is handled separately by
    # AutoMoveStability.
    return prep.auto_read is not None


def _required_auto_state_signature(auto_read, request):
    """Return the visible state signature, or why it is not safe to use yet."""
    if auto_read is None:
        return None, "nema ocitanja stanja"
    infinite_moves = bool(getattr(request, "infinite_moves", False))
    required_fields = [("booster", getattr(auto_read, "booster_charge", None))]
    if not infinite_moves:
        required_fields.append(("potezi", getattr(auto_read, "remaining_moves", None)))
    values = []
    for label, field_read in required_fields:
        if (
            field_read is None
            or not getattr(field_read, "accepted", False)
            or getattr(field_read, "value", None) is None
        ):
            return None, f"{label} nije sigurno vidljiv"
        values.append(int(field_read.value))

    if infinite_moves:
        # Preserve the normal signature shape:
        # (booster, remaining moves, current round, total rounds, booster max).
        values.append(None)

    total_rounds = getattr(request, "total_rounds", None)
    auto_round_detection = bool(
        getattr(request, "auto_round_detection", False)
    )
    rounds_mode = bool(
        not getattr(request, "showdown", False)
        and not getattr(request, "party", False)
        and not getattr(request, "solo_challenge", False)
        and not infinite_moves
        and (
            auto_round_detection
            or (total_rounds is not None and int(total_rounds) >= 2)
        )
    )
    if rounds_mode:
        round_read = getattr(auto_read, "current_round", None)
        if (
            round_read is None
            or not getattr(round_read, "accepted", False)
            or getattr(round_read, "value", None) is None
        ):
            return None, "runda nije sigurno vidljiva"
        values.append(int(round_read.value))
        detected_total = getattr(round_read, "maximum", None)
        if auto_round_detection:
            if (
                detected_total is None
                or int(detected_total) < 2
                or int(detected_total) > screen_state_reader.ROUND_INDICATOR_MAX_ROUNDS
            ):
                return None, "ukupan broj rundi nije sigurno vidljiv"
            values.append(int(detected_total))
        else:
            values.append(int(total_rounds))
    else:
        values.append(None)
        values.append(None)
    booster_field = getattr(auto_read, "booster_charge", None)
    booster_maximum = getattr(booster_field, "maximum", None)
    if not isinstance(booster_maximum, (int, float)) or booster_maximum <= 0:
        booster_maximum = BOOSTER_MAX_CHARGE
    values.append(int(booster_maximum))
    return tuple(values), ""


def _accepted_field_value(auto_read, field_name):
    field_read = getattr(auto_read, field_name, None)
    if (
        field_read is None
        or not getattr(field_read, "accepted", False)
        or getattr(field_read, "value", None) is None
    ):
        return None
    return int(field_read.value)


def _confirmed_activate_animation_frame(read_pair, request):
    """Return the clear frame index for one safe ACTIVATE animation pair.

    A ready booster continuously alternates between readable ACTIVATE text and
    a pulse that the meter reader sees as a low-confidence 5/6. The ordinary
    two-identical-frame rule can therefore never settle. This bridge is local
    to exactly two adjacent captures and still requires one complete, accepted
    state plus compatible visible fields in the pulsing neighbour.
    """
    if len(read_pair) != 2:
        return None

    for clear_index in (0, 1):
        clear_read = read_pair[clear_index]
        pulse_read = read_pair[1 - clear_index]
        clear_signature, _reason = _required_auto_state_signature(clear_read, request)
        clear_booster = getattr(clear_read, "booster_charge", None)
        if (
            clear_signature is None
            or clear_signature[0] != BOOSTER_MAX_CHARGE
            or getattr(clear_booster, "source", "") != "auto_activate"
        ):
            continue

        pulse_booster = getattr(pulse_read, "booster_charge", None)
        pulse_booster_value = getattr(pulse_booster, "value", None)
        pulse_is_compatible = (
            pulse_booster is not None
            and getattr(pulse_booster, "source", "") == "auto_meter"
            and pulse_booster_value is not None
            and int(pulse_booster_value) >= BOOSTER_MAX_CHARGE - 2
        )
        if not pulse_is_compatible:
            continue

        if not bool(getattr(request, "infinite_moves", False)):
            pulse_moves = _accepted_field_value(pulse_read, "remaining_moves")
            if pulse_moves is None or pulse_moves != clear_signature[1]:
                continue

        # The central celebration can cover the round number. Missing is safe
        # here because the clear adjacent frame already confirmed it; a visible
        # conflicting round is not safe and must keep waiting.
        pulse_round = _accepted_field_value(pulse_read, "current_round")
        clear_round = clear_signature[2]
        if clear_round is not None and pulse_round not in (None, clear_round):
            continue
        pulse_round_read = getattr(pulse_read, "current_round", None)
        pulse_total = (
            getattr(pulse_round_read, "maximum", None)
            if pulse_round is not None
            else None
        )
        clear_total = clear_signature[3]
        if clear_total is not None and pulse_total not in (None, clear_total):
            continue
        return clear_index
    return None


# A prep result older than this is discarded: it predates the settle episode it
# was meant to serve (the board, charge or perks likely changed since), so the
# synchronous path runs instead. Prep normally lands well under 0.5s before the
# move that consumes it.
AUTO_PREP_MAX_AGE_SECONDS = 0.8
AUTO_STATE_CONFIRMATION_FRAMES = 2
# Upper bound on the gap between the two ``Cekaj anim.`` state frames. It used to
# be a flat sleep, i.e. a guess at how long the HUD animation lasts; it is now the
# budget for _wait_for_state_crop_still, which watches the pixels instead and
# returns as soon as they stop moving. A calm HUD costs one poll (~15-20ms), an
# animating one still waits the whole 80ms, so the guarantee is unchanged.
AUTO_STATE_CONFIRMATION_DELAY_SECONDS = 0.08
# Poll interval while waiting for the state crop to go still. A screen grab is
# ~6ms, so this keeps the settled case at roughly one poll's latency.
AUTO_STATE_STILL_POLL_SECONDS = 0.015
# Mean absolute grey difference below which the state crop counts as still. Same
# bound the board settle path uses (runtime.AUTO_STILL_CORE_MOTION_MAX): a static
# crop measures ~0, while dots mid-transition measure well above it.
AUTO_STATE_STILL_MOTION_MAX = 0.5

# A single failed screen grab (transient GDI hiccup, screen transition...) must
# not kill an otherwise healthy auto session: retry a few times with a breather
# before giving up. Only this many failures in a row turn auto off.
AUTO_SCAN_FAILURE_LIMIT = 5
AUTO_SCAN_FAILURE_RETRY_DELAY_MS = 300

# Auto watchdog: the loop must NEVER wedge. The per-move escapes (booster-stuck,
# unchanged-after-play) only fire on a recognized board, so a hung worker, a busy
# flag stuck True, or a dropped pending-play can freeze auto indefinitely. Two
# tiers, both measured from the last launched play:
#  - FORCE_PLAY: loop is alive but not playing (board reads but never "settles")
#    -> force a play on the next readable scan instead of waiting forever.
#  - RESTART: a worker/flag is wedged (busy continuously this long) -> tear down
#    and rebuild the auto subsystem, reset flags, and resume scanning.
# Generous vs. normal play (~1-2s/move) so legit animations never trip it; the
# user accepts an occasional early swipe (the game just ignores an invalid one).
AUTO_WATCHDOG_FORCE_PLAY_SECONDS = 6.0
AUTO_WATCHDOG_RESTART_SECONDS = 12.0
# The clean-board force play above cannot fire while every scan keeps returning
# unrecognized cells (npr. lotus/JooJoo animacija stalno prekriva polja) — that
# was the one state with no escape. After this much continuous blockage, up to
# this many unknown cells are treated as BLOCKED and a move is forced on the
# rest of the board (moves touching those cells are automatically excluded).
AUTO_FORCE_PLAY_UNKNOWN_GRACE_SECONDS = 4.0
AUTO_FORCE_PLAY_MAX_UNKNOWN_CELLS = 6
# A real PLAY AGAIN end screen leaves no readable board behind it, so a replay
# detection is only trusted when recognition also failed on at least this many
# cells. Mid-game false positives are real: the froggy-lotus zone glow (hue
# ~140) lands in the detector's blue mask, and a lotus in the bottom-center of
# the board reads as a button (verified score 0.379 vs 0.16 threshold) — that
# used to short-circuit every scan into "replay off" and freeze the loop.
AUTO_REPLAY_MIN_UNKNOWN_CELLS = 8


def set_combobox_popup_width_to_contents(combo_box, padding=40):
    if combo_box.count() == 0:
        return
    longest_item_width = max(
        combo_box.fontMetrics().horizontalAdvance(combo_box.itemText(index))
        for index in range(combo_box.count())
    )
    combo_box.view().setMinimumWidth(max(combo_box.width(), longest_item_width + padding))


def _json_combo_value(combo_box):
    value = combo_box.currentData()
    return getattr(value, "value", value)


def _find_combo_data_index(combo_box, saved_value):
    for index in range(combo_box.count()):
        value = combo_box.itemData(index)
        if value == saved_value or getattr(value, "value", value) == saved_value:
            return index
    return -1


def _set_combo_data(combo_box, saved_value):
    index = _find_combo_data_index(combo_box, saved_value)
    if index >= 0:
        combo_box.setCurrentIndex(index)


def _set_spinbox_value(spin_box, saved_value):
    try:
        spin_box.setValue(int(saved_value))
    except (TypeError, ValueError):
        pass


def _set_double_spinbox_value(spin_box, saved_value):
    try:
        spin_box.setValue(float(saved_value))
    except (TypeError, ValueError):
        pass


def _unknown_perk_detection(slot_number):
    return perk_detection.PerkSlotDetection(
        slot_number,
        perk_detection.PERK_UNKNOWN,
        perk_detection.PERK_STATUS_UNKNOWN,
        0.0,
        None,
    )


def _perk_status_text(detection):
    if detection is None or detection.perk_key == perk_detection.PERK_UNKNOWN:
        return "unknown"
    definition = runtime.PERK_DEFINITIONS.get(detection.perk_key)
    label = definition.label if definition else detection.perk_key
    if detection.status == perk_detection.PERK_STATUS_USED:
        return f"{label} (used)"
    if detection.status == perk_detection.PERK_STATUS_AVAILABLE:
        return label
    return "unknown"


def _set_perk_status_style(label, detection):
    if detection is not None and detection.status == perk_detection.PERK_STATUS_AVAILABLE:
        label.setStyleSheet("color: #0a4a9f; background: #eef6ff; border: 1px solid #9abce8;")
    elif detection is not None and detection.status == perk_detection.PERK_STATUS_USED:
        label.setStyleSheet("color: #555; background: #eeeeee; border: 1px solid #bbbbbb;")
    else:
        label.setStyleSheet("color: #666; background: #f6f6f6; border: 1px solid #cccccc;")


class CheckBestMoveWorker(QtCore.QObject):
    finished = QtCore.pyqtSignal(object)
    failed = QtCore.pyqtSignal(object)

    def __init__(self, request):
        super().__init__()
        self.request = request

    @QtCore.pyqtSlot()
    def run(self):
        try:
            self.finished.emit(run_check_best_move_request(self.request))
        except Exception as exc:
            self.failed.emit(exc)


def run_auto_scan_request(request):
    previous_ml_recognition_mode = recognition.ml_recognition_mode
    recognition.set_ml_recognition_mode(request.ml_recognition_mode)
    try:
        recognition.curr_mode = normalize_game_mode(request.mode)
        recognition.special_piece_mode = normalize_special_piece_mode(request.special_piece_mode)
        recognition.apply_board_profile(request.selected_profile)

        mode_detection = None
        if bool(getattr(request, "auto_mode_detection", False)):
            board_size = BOARD_PROFILES[request.selected_profile]["boardSize"]
            icon_region = mode_icon_region(
                recognition.left,
                recognition.up,
                recognition.squareSize,
                board_size,
            )
            icon_image = capture.capture_debug_screenshot(
                output_path=None,
                region=icon_region,
                write_to_disk=False,
            )
            mode_detection = detect_mode_icon(icon_image, region=icon_region)
            if mode_detection.accepted:
                recognition.curr_mode = mode_detection.mode

        turn_owner = None
        if bool(getattr(request, "detect_turn_owner", False)):
            turn_region = screen_state_reader.turn_banner_region_from_board()
            turn_image = capture.capture_debug_screenshot(
                output_path=None,
                region=turn_region,
                write_to_disk=False,
            )
            turn_owner = screen_state_reader.read_turn_owner_crop(
                turn_image,
                region=turn_region,
            )

        def _read_ml_board():
            ml_board = recognition.create_board()
            ml_special_board = recognition.create_board()
            return recognition.update_board_2(
                ml_board,
                ml_special_board,
                screenshot_path=AUTO_LATEST_BOARD_FILENAME,
                write_screenshot=False,
            )

        source_result = board_source.read_selected_board(
            request.board_source,
            _read_ml_board,
        )
        game_board = source_result.board
        special_game_board = source_result.special_board
        hot_color_state = (
            copy.deepcopy(recognition.last_hot_color_state)
            if source_result.source == BOARD_SOURCE_ML
            else None
        )
        if bool(getattr(request, "auto_mode_detection", False)):
            mode_detection = prefer_hot_color_board_detection(
                mode_detection,
                copy.deepcopy(recognition.last_hot_color_auto_candidate),
            )
            if (
                source_result.source == BOARD_SOURCE_ML
                and
                mode_detection is not None
                and mode_detection.accepted
                and mode_detection.mode is GameMode.HOT_COLOR
            ):
                recognition.curr_mode = GameMode.HOT_COLOR
                # The first board was interpreted under the previously
                # selected mode. Re-scan immediately under Hot Color so its
                # consensus floors and live 3/4/5 state apply in this same Auto
                # cycle instead of waiting for the next timer tick.
                game_board, special_game_board = _read_ml_board()
                hot_color_state = copy.deepcopy(recognition.last_hot_color_state)
                if hot_color_state is None:
                    hot_color_state = copy.deepcopy(
                        recognition.last_hot_color_auto_candidate
                    )
                recognition.last_hot_color_state = copy.deepcopy(hot_color_state)
        board_image = capture.load_auto_board_image()
        if source_result.source != BOARD_SOURCE_ML:
            board_image = capture.capture_debug_screenshot(
                output_path=AUTO_LATEST_BOARD_FILENAME,
                region=(recognition.left, recognition.up, recognition.width, recognition.height),
                write_to_disk=False,
            )
        return AutoScanResult(
            game_board=game_board,
            special_game_board=special_game_board,
            board_image=board_image,
            turn_owner=turn_owner,
            mode_detection=mode_detection,
            hot_color_state=hot_color_state,
            board_source=source_result.source,
            board_source_fallback_reason=source_result.fallback_reason,
            memory_move_ready=(
                board_source.move_ready_state(source_result.snapshot)
                if source_result.source == BOARD_SOURCE_MEMORY
                else None
            ),
            memory_charge_colors=(
                board_source.charging_colors(source_result.snapshot)
                if source_result.source == BOARD_SOURCE_MEMORY
                else None
            ),
        )
    finally:
        recognition.set_ml_recognition_mode(previous_ml_recognition_mode)


def enrich_auto_scan_result(result, motion_tracker, reset_motion=False):
    """Compute the per-scan signals (dt-aware motion scores, visual hash,
    play-again detection) off the GUI thread so the handler only consumes."""
    if reset_motion:
        motion_tracker.reset()
    board_image = result.board_image
    if board_image is not None:
        motion_score, core_motion_score = motion_tracker.observe(
            board_image,
            board_size=len(result.game_board) if result.game_board else None,
        )
    else:
        motion_score, core_motion_score = 0.0, 0.0
    return AutoScanResult(
        game_board=result.game_board,
        special_game_board=result.special_game_board,
        board_image=board_image,
        visual_hash=auto_visual_fingerprint(board_image),
        motion_score=motion_score,
        core_motion_score=core_motion_score,
        replay_detection=runtime.detect_play_again_button(board_image),
        turn_owner=result.turn_owner,
        mode_detection=result.mode_detection,
        hot_color_state=result.hot_color_state,
        board_source=result.board_source,
        board_source_fallback_reason=result.board_source_fallback_reason,
        memory_move_ready=result.memory_move_ready,
        memory_charge_colors=result.memory_charge_colors,
    )


class AutoScanWorker(QtCore.QObject):
    """Persistent background scanner: lives on one thread for the whole session
    (no per-scan QThread churn) and owns the frame history the dt-aware motion
    scores need. Trigger scans by emitting `requested` from the GUI thread."""

    requested = QtCore.pyqtSignal(object)
    finished = QtCore.pyqtSignal(object)
    failed = QtCore.pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self._motion_tracker = capture.AutoMotionTracker()
        self.requested.connect(self.run_request)

    @QtCore.pyqtSlot(object)
    def run_request(self, request):
        try:
            result = run_auto_scan_request(request)
            self.finished.emit(
                enrich_auto_scan_result(
                    result,
                    self._motion_tracker,
                    reset_motion=request.reset_motion,
                )
            )
        except Exception as exc:
            self.failed.emit(exc)


class AutoPrepWorker(QtCore.QObject):
    """Persistent background worker for the non-board inputs of a move request
    (screen-state OCR + perk detection). Both parts swallow their own errors the
    same way the synchronous GUI path did, so a failed capture degrades to the
    manual spin-box values instead of killing auto."""

    requested = QtCore.pyqtSignal(object)
    finished = QtCore.pyqtSignal(object)
    failed = QtCore.pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.requested.connect(self.run_request)

    @QtCore.pyqtSlot(object)
    def run_request(self, request):
        try:
            auto_read = None
            state_image = None
            score_stable = True
            score_samples = ()
            state_stable = True
            state_samples = ()
            state_reason = ""
            if request.auto_state_enabled:
                try:
                    (
                        auto_read,
                        state_image,
                        score_stable,
                        score_samples,
                        state_stable,
                        state_samples,
                        state_reason,
                    ) = _capture_stable_auto_state(
                        request
                    )
                except Exception:
                    auto_read = None
                    state_image = None
                    score_stable = False
                    score_samples = ()
                    state_stable = False
                    state_samples = ()
                    state_reason = "greska pri citanju stanja"
            try:
                perk_detections = tuple(
                    runtime.detect_current_perk_slots(party=request.party)
                )
            except Exception:
                perk_detections = (
                    _unknown_perk_detection(1),
                    _unknown_perk_detection(2),
                )
            self.finished.emit(
                AutoPrepResult(
                    auto_read=auto_read,
                    state_image=state_image,
                    perk_detections=perk_detections,
                    auto_state_enabled=request.auto_state_enabled,
                    created_at=time.monotonic(),
                    score_stable=score_stable,
                    score_samples=score_samples,
                    state_stable=state_stable,
                    state_samples=state_samples,
                    state_reason=state_reason,
                    stable_state_required=bool(request.require_stable_state),
                )
            )
        except Exception as exc:
            self.failed.emit(exc)


class SwipeRecorderWorker(QtCore.QObject):
    """Runs swipe_recorder.record_swipe() off the GUI thread.

    record_swipe busy-waits on GetAsyncKeyState for up to several seconds;
    running it on the Qt main loop would freeze the whole UI (including the
    auto-scan timer). The worker emits the result or None on any failure.
    """

    finished = QtCore.pyqtSignal(object)  # SwipeRecording | None

    @QtCore.pyqtSlot()
    def run(self):
        try:
            self.finished.emit(swipe_recorder.record_swipe())
        except Exception:
            self.finished.emit(None)


class _NetToggleSignals(QtCore.QObject):
    """Bridge so the background net-toggle thread can update the GUI safely.

    Emits ``done(success, requested_enabled, message)`` back on the GUI thread
    (queued, because it's emitted from a worker thread).
    """

    done = QtCore.pyqtSignal(bool, bool, str)


class _MatchMastersLaunchSignals(QtCore.QObject):
    progress = QtCore.pyqtSignal(str)
    done = QtCore.pyqtSignal(object)


class Ui_MainWindow(object):
    def setupUi(self, MainWindow):
        MainWindow.setObjectName("MainWindow")
        # Window opens shorter than the full content so it fits on screen; the
        # central widget is wrapped in a scroll area (see setCentralWidget below),
        # so the bottom groups stay reachable by scrolling instead of being cut off.
        MainWindow.resize(520, 900)
        MainWindow.setAutoFillBackground(False)
        self.centralwidget = QtWidgets.QWidget(MainWindow)
        self.centralwidget.setObjectName("centralwidget")
        # All visible children use absolute geometry. Timing is retained as
        # hidden persisted state, so the visible content ends at StateGroup.
        self.centralwidget.setMinimumSize(QtCore.QSize(500, 920))
        self.ModeBox = QtWidgets.QComboBox(self.centralwidget)
        self.ModeBox.setGeometry(QtCore.QRect(140, 20, 161, 31))
        font = QtGui.QFont()
        font.setPointSize(14)
        self.ModeBox.setFont(font)
        self.ModeBox.setObjectName("ModeBox")
        for mode in GUI_GAME_MODE_OPTIONS:
            self.ModeBox.addItem("")
            self.ModeBox.setItemData(self.ModeBox.count() - 1, mode)
        self.AutoModeCheck = QtWidgets.QCheckBox(self.centralwidget)
        self.AutoModeCheck.setGeometry(QtCore.QRect(10, 60, 125, 31))
        auto_mode_font = QtGui.QFont()
        auto_mode_font.setPointSize(9)
        self.AutoModeCheck.setFont(auto_mode_font)
        self.AutoModeCheck.setChecked(False)
        self.AutoModeCheck.setToolTip(
            "Automatski prepoznaje ikonu moda levo od RULES. Ako prepoznavanje "
            "nije sigurno, ostaje rucno izabrani mod. Mighty Mushrooms i Bombs Away "
            "se racunaju kao None."
        )
        self.AutoModeCheck.setObjectName("AutoModeCheck")
        self.BoardSizeBox = QtWidgets.QComboBox(self.centralwidget)
        self.BoardSizeBox.setGeometry(QtCore.QRect(140, 60, 181, 31))
        self.BoardSizeBox.setFont(font)
        self.BoardSizeBox.setObjectName("BoardSizeBox")
        self.BoardSizeBox.addItem("")
        self.BoardSizeBox.addItem("")
        self.BoardSizeBox.setItemData(0, REGULAR_PROFILE)
        self.BoardSizeBox.setItemData(1, SUPERSIZE_PROFILE)
        self.SquareMatchesCheck = QtWidgets.QCheckBox(self.centralwidget)
        self.SquareMatchesCheck.setGeometry(QtCore.QRect(330, 20, 121, 31))
        square_font = QtGui.QFont()
        square_font.setPointSize(10)
        self.SquareMatchesCheck.setFont(square_font)
        self.SquareMatchesCheck.setObjectName("SquareMatchesCheck")
        self.BoosterActionBox = QtWidgets.QComboBox(self.centralwidget)
        self.BoosterActionBox.setGeometry(QtCore.QRect(330, 60, 151, 31))
        self.BoosterActionBox.setFont(square_font)
        self.BoosterActionBox.setObjectName("BoosterActionBox")
        for label, value in BOOSTER_ACTION_OPTIONS:
            self.BoosterActionBox.addItem("")
            self.BoosterActionBox.setItemData(self.BoosterActionBox.count() - 1, value)
        self.SpecialPieceModeBox = QtWidgets.QComboBox(self.centralwidget)
        self.SpecialPieceModeBox.setGeometry(QtCore.QRect(330, 95, 151, 25))
        self.SpecialPieceModeBox.setFont(square_font)
        self.SpecialPieceModeBox.setObjectName("SpecialPieceModeBox")
        # Figure recognition is permanently automatic. Keep one hidden item so
        # existing request/state plumbing remains compatible without exposing a
        # manual "Booster: Auto" selector in the GUI.
        self.SpecialPieceModeBox.addItem("")
        self.SpecialPieceModeBox.setItemData(0, SPECIAL_PIECE_MODE_AUTO)
        _set_combo_data(self.SpecialPieceModeBox, SPECIAL_PIECE_MODE_AUTO)
        self.SpecialPieceModeBox.setVisible(False)
        self.BoosterImmediateCheck = QtWidgets.QCheckBox(self.centralwidget)
        self.BoosterImmediateCheck.setGeometry(QtCore.QRect(330, 122, 165, 25))
        self.BoosterImmediateCheck.setFont(square_font)
        self.BoosterImmediateCheck.setToolTip(
            "Aktiviraj booster cim je spreman, bez cekanja na extra move poteze"
        )
        self.BoosterImmediateCheck.setObjectName("BoosterImmediateCheck")
        self.SpecialExplodeCheck = QtWidgets.QCheckBox(self.centralwidget)
        self.SpecialExplodeCheck.setGeometry(QtCore.QRect(10, 100, 301, 25))
        self.SpecialExplodeCheck.setFont(square_font)
        self.SpecialExplodeCheck.setObjectName("SpecialExplodeCheck")
        self.ColorCrushCheck = QtWidgets.QCheckBox(self.centralwidget)
        self.ColorCrushCheck.setGeometry(QtCore.QRect(10, 20, 130, 31))
        self.ColorCrushCheck.setFont(square_font)
        self.ColorCrushCheck.setToolTip(
            "Color Crush: kada potez unisti jednu boju, sve figure te boje na tabli "
            "se unistavaju (izuzeta je samo plava - mereno 2026-08-21)"
        )
        self.ColorCrushCheck.setObjectName("ColorCrushCheck")
        self.VerticalMatchesDestroyColorCheck = QtWidgets.QCheckBox(self.centralwidget)
        self.VerticalMatchesDestroyColorCheck.setGeometry(QtCore.QRect(10, 125, 301, 25))
        self.VerticalMatchesDestroyColorCheck.setFont(square_font)
        self.VerticalMatchesDestroyColorCheck.setToolTip(
            "Direktni vertikalni match unistava sve figure svoje boje; "
            "Vinnie SE srce unistava obe svoje boje. Kaskadni match ne aktivira pravilo."
        )
        self.VerticalMatchesDestroyColorCheck.setObjectName(
            "VerticalMatchesDestroyColorCheck"
        )
        # Energized: only shown while that mode is selected, so it is parked
        # below the normally visible content (see _update_energized_controls,
        # which grows the scrolled central widget when it appears).
        self.EnergizedGroup = QtWidgets.QGroupBox(self.centralwidget)
        self.EnergizedGroup.setGeometry(QtCore.QRect(10, 922, 470, 66))
        self.EnergizedGroup.setObjectName("EnergizedGroup")
        self.EnergizedGroup.setVisible(False)
        self.EnergizedFirstLabel = QtWidgets.QLabel(self.EnergizedGroup)
        self.EnergizedFirstLabel.setGeometry(QtCore.QRect(15, 30, 55, 22))
        self.EnergizedFirstLabel.setObjectName("EnergizedFirstLabel")
        self.EnergizedFirstBox = QtWidgets.QComboBox(self.EnergizedGroup)
        self.EnergizedFirstBox.setGeometry(QtCore.QRect(60, 30, 110, 25))
        self.EnergizedFirstBox.setFont(square_font)
        self.EnergizedFirstBox.setObjectName("EnergizedFirstBox")
        self.EnergizedSecondLabel = QtWidgets.QLabel(self.EnergizedGroup)
        self.EnergizedSecondLabel.setGeometry(QtCore.QRect(180, 30, 45, 22))
        self.EnergizedSecondLabel.setObjectName("EnergizedSecondLabel")
        self.EnergizedSecondBox = QtWidgets.QComboBox(self.EnergizedGroup)
        self.EnergizedSecondBox.setGeometry(QtCore.QRect(230, 30, 110, 25))
        self.EnergizedSecondBox.setFont(square_font)
        self.EnergizedSecondBox.setObjectName("EnergizedSecondBox")
        for energized_box in (self.EnergizedFirstBox, self.EnergizedSecondBox):
            fill_energized_color_combo(energized_box)
        self.EnergizedChangeButton = QtWidgets.QPushButton(self.EnergizedGroup)
        self.EnergizedChangeButton.setGeometry(QtCore.QRect(355, 29, 100, 27))
        self.EnergizedChangeButton.setFont(square_font)
        self.EnergizedChangeButton.setObjectName("EnergizedChangeButton")
        self.EnergizedGroup.setToolTip(
            "Energized: pored plave, i ove dve boje pune booster."
        )
        self.ScoreRallyGroup = QtWidgets.QGroupBox(self.centralwidget)
        self.ScoreRallyGroup.setGeometry(QtCore.QRect(10, 150, 470, 111))
        self.ScoreRallyGroup.setObjectName("ScoreRallyGroup")
        self.ScoreRallyCheck = QtWidgets.QCheckBox(self.ScoreRallyGroup)
        self.ScoreRallyCheck.setGeometry(QtCore.QRect(10, 20, 161, 21))
        self.ScoreRallyCheck.setObjectName("ScoreRallyCheck")
        self.ScoreLegendAutoCheck = QtWidgets.QCheckBox(self.ScoreRallyGroup)
        self.ScoreLegendAutoCheck.setGeometry(QtCore.QRect(180, 20, 161, 21))
        self.ScoreLegendAutoCheck.setToolTip(
            "Cita vrednosti iz 'Score legend' trake ispod table pre svakog poteza. "
            "Boju koju ne procita ostavlja na rucno unetoj vrednosti."
        )
        self.ScoreLegendAutoCheck.setObjectName("ScoreLegendAutoCheck")
        self.ScoreLegendStatusLabel = QtWidgets.QLabel(self.ScoreRallyGroup)
        self.ScoreLegendStatusLabel.setGeometry(QtCore.QRect(345, 20, 115, 21))
        self.ScoreLegendStatusLabel.setObjectName("ScoreLegendStatusLabel")
        self.ScoreRallyYellowLabel = QtWidgets.QLabel(self.ScoreRallyGroup)
        self.ScoreRallyYellowLabel.setGeometry(QtCore.QRect(351, 50, 100, 18))
        self.ScoreRallyYellowLabel.setObjectName("ScoreRallyYellowLabel")
        self.ScoreRallyYellow = QtWidgets.QDoubleSpinBox(self.ScoreRallyGroup)
        self.ScoreRallyYellow.setGeometry(QtCore.QRect(351, 71, 61, 22))
        self.ScoreRallyYellow.setDecimals(0)
        self.ScoreRallyYellow.setRange(0.0, 99.0)
        self.ScoreRallyYellow.setSingleStep(1.0)
        self.ScoreRallyYellow.setProperty("value", 5.0)
        self.ScoreRallyYellow.setObjectName("ScoreRallyYellow")
        self.ScoreRallyPurpleLabel = QtWidgets.QLabel(self.ScoreRallyGroup)
        self.ScoreRallyPurpleLabel.setGeometry(QtCore.QRect(239, 50, 100, 18))
        self.ScoreRallyPurpleLabel.setObjectName("ScoreRallyPurpleLabel")
        self.ScoreRallyPurple = QtWidgets.QDoubleSpinBox(self.ScoreRallyGroup)
        self.ScoreRallyPurple.setGeometry(QtCore.QRect(239, 71, 61, 22))
        self.ScoreRallyPurple.setDecimals(0)
        self.ScoreRallyPurple.setRange(0.0, 99.0)
        self.ScoreRallyPurple.setSingleStep(1.0)
        self.ScoreRallyPurple.setProperty("value", 4.0)
        self.ScoreRallyPurple.setObjectName("ScoreRallyPurple")
        self.ScoreRallyGreenLabel = QtWidgets.QLabel(self.ScoreRallyGroup)
        self.ScoreRallyGreenLabel.setGeometry(QtCore.QRect(15, 50, 100, 18))
        self.ScoreRallyGreenLabel.setObjectName("ScoreRallyGreenLabel")
        self.ScoreRallyGreen = QtWidgets.QDoubleSpinBox(self.ScoreRallyGroup)
        self.ScoreRallyGreen.setGeometry(QtCore.QRect(15, 71, 61, 22))
        self.ScoreRallyGreen.setDecimals(0)
        self.ScoreRallyGreen.setRange(0.0, 99.0)
        self.ScoreRallyGreen.setSingleStep(1.0)
        self.ScoreRallyGreen.setProperty("value", 2.0)
        self.ScoreRallyGreen.setObjectName("ScoreRallyGreen")
        self.ScoreRallyBrownLabel = QtWidgets.QLabel(self.ScoreRallyGroup)
        self.ScoreRallyBrownLabel.setGeometry(QtCore.QRect(127, 50, 100, 18))
        self.ScoreRallyBrownLabel.setObjectName("ScoreRallyBrownLabel")
        self.ScoreRallyBrown = QtWidgets.QDoubleSpinBox(self.ScoreRallyGroup)
        self.ScoreRallyBrown.setGeometry(QtCore.QRect(127, 71, 61, 22))
        self.ScoreRallyBrown.setDecimals(0)
        self.ScoreRallyBrown.setRange(0.0, 99.0)
        self.ScoreRallyBrown.setSingleStep(1.0)
        self.ScoreRallyBrown.setProperty("value", 3.0)
        self.ScoreRallyBrown.setObjectName("ScoreRallyBrown")
        self.ScoreRallyInputs = [
            self.ScoreRallyYellow,
            self.ScoreRallyPurple,
            self.ScoreRallyGreen,
            self.ScoreRallyBrown,
        ]
        self.ActiveButton = QtWidgets.QToolButton(self.centralwidget)
        self.ActiveButton.setGeometry(QtCore.QRect(120, 430, 261, 61))
        font = QtGui.QFont()
        font.setPointSize(16)
        self.ActiveButton.setFont(font)
        self.ActiveButton.setObjectName("ActiveButton")
        self.ExtraMoveButton = QtWidgets.QToolButton(self.centralwidget)
        self.ExtraMoveButton.setGeometry(QtCore.QRect(120, 500, 261, 45))
        self.ExtraMoveButton.setFont(font)
        self.ExtraMoveButton.setObjectName("ExtraMoveButton")
        self.HighestPointsButton = QtWidgets.QToolButton(self.centralwidget)
        self.HighestPointsButton.setGeometry(QtCore.QRect(120, 550, 261, 45))
        self.HighestPointsButton.setFont(font)
        self.HighestPointsButton.setToolTip(
            "Maksimizuje ukupan broj poena kroz podeseni lookahead i runde; "
            "booster charge, booster aktivacija i perkovi se potpuno ignorisu."
        )
        self.HighestPointsButton.setObjectName("HighestPointsButton")
        self.AutoButton = QtWidgets.QToolButton(self.centralwidget)
        self.AutoButton.setGeometry(QtCore.QRect(120, 600, 170, 45))
        self.AutoButton.setFont(font)
        self.AutoButton.setCheckable(True)
        self.AutoButton.setObjectName("AutoButton")
        self.AutoReplayCheck = QtWidgets.QCheckBox(self.centralwidget)
        self.AutoReplayCheck.setGeometry(QtCore.QRect(300, 610, 171, 25))
        replay_font = QtGui.QFont()
        replay_font.setPointSize(10)
        self.AutoReplayCheck.setFont(replay_font)
        self.AutoReplayCheck.setChecked(False)
        self.AutoReplayCheck.setToolTip(
            "Kada je Auto ukljucen, klikni PLAY AGAIN posle zavrsene partije"
        )
        self.AutoReplayCheck.setObjectName("AutoReplayCheck")
        self.PerksGroup = QtWidgets.QGroupBox(self.centralwidget)
        self.PerksGroup.setGeometry(QtCore.QRect(10, 695, 470, 85))
        # Checkable title acts as the "use perks" toggle: unchecked means the
        # bot never plays a perk (detection still runs for the status labels).
        self.PerksGroup.setCheckable(True)
        self.PerksGroup.setChecked(True)
        self.PerksGroup.setToolTip(
            "Kada je iskljuceno, bot ne koristi perkove automatski. "
            "Refresh i rucno Koristi i dalje rade."
        )
        self.PerksGroup.setObjectName("PerksGroup")
        # Manual controls are siblings of the checkable group so Qt does not
        # disable them when automatic perk usage is unchecked.
        self.PerksRefreshButton = QtWidgets.QToolButton(self.centralwidget)
        self.PerksRefreshButton.setGeometry(QtCore.QRect(380, 695, 80, 25))
        self.PerksRefreshButton.setToolTip(
            "Ponovo ocitaj perkove sa ekrana i omoguci Koristi za dostupne slotove."
        )
        self.PerksRefreshButton.setObjectName("PerksRefreshButton")
        self.Perk1Label = QtWidgets.QLabel(self.PerksGroup)
        self.Perk1Label.setGeometry(QtCore.QRect(10, 35, 43, 21))
        self.Perk1Label.setObjectName("Perk1Label")
        self.Perk1Status = QtWidgets.QLabel(self.PerksGroup)
        self.Perk1Status.setGeometry(QtCore.QRect(55, 30, 100, 31))
        self.Perk1Status.setFont(square_font)
        self.Perk1Status.setAlignment(QtCore.Qt.AlignCenter)
        self.Perk1Status.setObjectName("Perk1Status")
        self.Perk1UseButton = QtWidgets.QToolButton(self.centralwidget)
        self.Perk1UseButton.setGeometry(QtCore.QRect(170, 725, 65, 31))
        self.Perk1UseButton.setToolTip(
            "Odmah iskoristi perk iz slota 1; metu i nastavak racuna isto kao Auto."
        )
        self.Perk1UseButton.setObjectName("Perk1UseButton")
        self.Perk2Label = QtWidgets.QLabel(self.PerksGroup)
        self.Perk2Label.setGeometry(QtCore.QRect(235, 35, 43, 21))
        self.Perk2Label.setObjectName("Perk2Label")
        self.Perk2Status = QtWidgets.QLabel(self.PerksGroup)
        self.Perk2Status.setGeometry(QtCore.QRect(280, 30, 100, 31))
        self.Perk2Status.setFont(square_font)
        self.Perk2Status.setAlignment(QtCore.Qt.AlignCenter)
        self.Perk2Status.setObjectName("Perk2Status")
        self.Perk2UseButton = QtWidgets.QToolButton(self.centralwidget)
        self.Perk2UseButton.setGeometry(QtCore.QRect(395, 725, 65, 31))
        self.Perk2UseButton.setToolTip(
            "Odmah iskoristi perk iz slota 2; metu i nastavak racuna isto kao Auto."
        )
        self.Perk2UseButton.setObjectName("Perk2UseButton")
        self.BestMove = QtWidgets.QLabel(self.centralwidget)
        self.BestMove.setGeometry(QtCore.QRect(10, 280, 461, 51))
        font = QtGui.QFont()
        font.setPointSize(24)
        self.BestMove.setFont(font)
        self.BestMove.setObjectName("BestMove")
        self.Score = QtWidgets.QLabel(self.centralwidget)
        self.Score.setGeometry(QtCore.QRect(80, 340, 251, 51))
        font = QtGui.QFont()
        font.setPointSize(24)
        self.Score.setFont(font)
        self.Score.setObjectName("Score")
        self.AutoStatus = QtWidgets.QLabel(self.centralwidget)
        self.AutoStatus.setGeometry(QtCore.QRect(130, 395, 251, 25))
        status_font = QtGui.QFont()
        status_font.setPointSize(10)
        self.AutoStatus.setFont(status_font)
        self.AutoStatus.setAlignment(QtCore.Qt.AlignCenter)
        self.AutoStatus.setObjectName("AutoStatus")
        self.DebugModeCheck = QtWidgets.QCheckBox(self.centralwidget)
        self.DebugModeCheck.setGeometry(QtCore.QRect(10, 395, 111, 25))
        self.DebugModeCheck.setFont(status_font)
        self.DebugModeCheck.setChecked(False)
        self.DebugModeCheck.setObjectName("DebugModeCheck")
        self.MLRecognitionModeBox = QtWidgets.QComboBox(self.centralwidget)
        self.MLRecognitionModeBox.setGeometry(QtCore.QRect(10, 425, 100, 25))
        self.MLRecognitionModeBox.setFont(status_font)
        self.MLRecognitionModeBox.setObjectName("MLRecognitionModeBox")
        for _label, value in ML_RECOGNITION_OPTIONS:
            self.MLRecognitionModeBox.addItem("")
            self.MLRecognitionModeBox.setItemData(self.MLRecognitionModeBox.count() - 1, value)
        # Only ML-only mode remains, so there is nothing to pick: keep the box
        # (its currentData() still feeds the request builders) but hide it.
        self.MLRecognitionModeBox.setCurrentIndex(0)
        self.MLRecognitionModeBox.setVisible(False)
        self.BoardSourceBox = QtWidgets.QComboBox(self.centralwidget)
        self.BoardSourceBox.setGeometry(QtCore.QRect(10, 425, 215, 25))
        self.BoardSourceBox.setFont(status_font)
        self.BoardSourceBox.setToolTip(
            "Izvor table. Memorija cita poslednji svezi read-only Frida snapshot; "
            "Auto prvo proba memoriju, pa bezbedno koristi ML ako reader nije dostupan."
        )
        self.BoardSourceBox.setObjectName("BoardSourceBox")
        for _label, value in BOARD_SOURCE_OPTIONS:
            self.BoardSourceBox.addItem("")
            self.BoardSourceBox.setItemData(self.BoardSourceBox.count() - 1, value)
        self.BoardSourceBox.setCurrentIndex(0)
        self.LaunchMatchMastersButton = QtWidgets.QToolButton(self.centralwidget)
        self.LaunchMatchMastersButton.setGeometry(QtCore.QRect(235, 425, 140, 25))
        self.LaunchMatchMastersButton.setFont(status_font)
        self.LaunchMatchMastersButton.setToolTip(
            "Koristi rootovanu BlueStacks instancu koja vec radi (Pie64 ili "
            "Pie64_2, port se cita iz bluestacks.conf), proveri root i "
            "namespace_cleaned=yes, pokreni Match Masters i Frida citac table."
        )
        self.LaunchMatchMastersButton.setObjectName("LaunchMatchMastersButton")
        self.ManualRecognitionStabilityCheck = QtWidgets.QCheckBox(self.centralwidget)
        self.ManualRecognitionStabilityCheck.setGeometry(QtCore.QRect(10, 455, 105, 25))
        self.ManualRecognitionStabilityCheck.setFont(status_font)
        self.ManualRecognitionStabilityCheck.setChecked(True)
        self.ManualRecognitionStabilityCheck.setToolTip(
            "Kada je ukljuceno, ceka dve iste ciste table; Auto uz Auto stanje "
            "dodatno trazi dva ista sigurna ocitanja boostera, poteza i runde."
        )
        self.ManualRecognitionStabilityCheck.setObjectName("ManualRecognitionStabilityCheck")
        self.NewGameButton = QtWidgets.QToolButton(self.centralwidget)
        self.NewGameButton.setGeometry(QtCore.QRect(380, 365, 101, 25))
        self.NewGameButton.setFont(status_font)
        self.NewGameButton.setToolTip(
            "Obelezi novu partiju: debug snimci idu u novi Debug/runs/game_... folder"
        )
        self.NewGameButton.setObjectName("NewGameButton")
        self.NewGameButton.setVisible(False)
        self.ResetGameButton = QtWidgets.QToolButton(self.centralwidget)
        self.ResetGameButton.setGeometry(QtCore.QRect(380, 395, 101, 25))
        self.ResetGameButton.setFont(status_font)
        self.ResetGameButton.setToolTip(
            "Ocisti auto stanje, booster memoriju i cooldown pre nove partije"
        )
        self.ResetGameButton.setObjectName("ResetGameButton")
        self.ResetGameButton.setVisible(False)
        self.DebugCaptureButton = QtWidgets.QToolButton(self.centralwidget)
        self.DebugCaptureButton.setGeometry(QtCore.QRect(385, 425, 96, 25))
        self.DebugCaptureButton.setFont(status_font)
        self.DebugCaptureButton.setToolTip(
            "Sacuvaj jedan Debug/runs snimak bez igranja poteza"
        )
        self.DebugCaptureButton.setObjectName("DebugCaptureButton")
        self.DebugCaptureButton.setVisible(False)
        self.NetKillButton = QtWidgets.QToolButton(self.centralwidget)
        self.NetKillButton.setGeometry(QtCore.QRect(385, 455, 96, 25))
        self.NetKillButton.setFont(status_font)
        self.NetKillButton.setCheckable(True)
        self.NetKillButton.setToolTip(
            "Blokiraj/vrati internet u BlueStacks preko ADB airplane-mode "
            "komande, uz fallback na wifi/data toggle."
        )
        self.NetKillButton.setObjectName("NetKillButton")
        self.NetKillButton.setVisible(False)
        self.RestartAppButton = QtWidgets.QToolButton(self.centralwidget)
        self.RestartAppButton.setGeometry(QtCore.QRect(385, 485, 96, 25))
        self.RestartAppButton.setFont(status_font)
        self.RestartAppButton.setToolTip(
            "Sacuvaj podesavanja i restartuj bota u istoj konzoli, "
            "bez otvaranja novog CMD prozora."
        )
        self.RestartAppButton.setObjectName("RestartAppButton")
        self.StateGroup = QtWidgets.QGroupBox(self.centralwidget)
        self.StateGroup.setGeometry(QtCore.QRect(10, 785, 470, 130))
        self.StateGroup.setObjectName("StateGroup")
        self.BoosterChargeLabel = QtWidgets.QLabel(self.StateGroup)
        self.BoosterChargeLabel.setGeometry(QtCore.QRect(20, 28, 91, 21))
        self.BoosterChargeLabel.setObjectName("BoosterChargeLabel")
        self.BoosterChargeSpin = QtWidgets.QSpinBox(self.StateGroup)
        self.BoosterChargeSpin.setGeometry(QtCore.QRect(115, 24, 61, 27))
        self.BoosterChargeSpin.setRange(0, BOOSTER_MAX_CHARGE)
        self.BoosterChargeSpin.setObjectName("BoosterChargeSpin")
        self.RemainingMovesLabel = QtWidgets.QLabel(self.StateGroup)
        self.RemainingMovesLabel.setGeometry(QtCore.QRect(220, 28, 91, 21))
        self.RemainingMovesLabel.setObjectName("RemainingMovesLabel")
        self.RemainingMovesSpin = QtWidgets.QSpinBox(self.StateGroup)
        self.RemainingMovesSpin.setGeometry(QtCore.QRect(315, 24, 61, 27))
        self.RemainingMovesSpin.setRange(0, 12)
        self.RemainingMovesSpin.setObjectName("RemainingMovesSpin")
        self.AutoStateCheck = QtWidgets.QCheckBox(self.StateGroup)
        self.AutoStateCheck.setGeometry(QtCore.QRect(385, 24, 81, 27))
        self.AutoStateCheck.setObjectName("AutoStateCheck")
        self.ShowdownCheck = QtWidgets.QCheckBox(self.StateGroup)
        self.ShowdownCheck.setGeometry(QtCore.QRect(20, 60, 90, 27))
        self.ShowdownCheck.setChecked(True)
        self.ShowdownCheck.setToolTip(
            "Showdown (solo) mod: 6 zutih prstenova. Iskljuci za PvP mod "
            "gde se broje samo 2 plave tacke (tvoji potezi)."
        )
        self.ShowdownCheck.setObjectName("ShowdownCheck")
        self.PartyCheck = QtWidgets.QCheckBox(self.StateGroup)
        self.PartyCheck.setGeometry(QtCore.QRect(115, 60, 80, 27))
        self.PartyCheck.setToolTip(
            "Party mod: nema protivnika, samo skupljas poene za svoje poteze. "
            "6 plavih prstenova (strogo, animacije se odbacuju), sopstveni skor "
            "se cita iz 'You' plocice na tabeli i siri crop za donja perk dugmad."
        )
        self.PartyCheck.setObjectName("PartyCheck")
        self.SoloChallengeCheck = QtWidgets.QCheckBox(self.StateGroup)
        self.SoloChallengeCheck.setGeometry(QtCore.QRect(200, 60, 130, 27))
        self.SoloChallengeCheck.setToolTip(
            "Solo Challenge: broj preostalih poteza je desno pored plave kugle "
            "(npr. 12); nema rundi niti dot-trackera."
        )
        self.SoloChallengeCheck.setObjectName("SoloChallengeCheck")
        # Rounds (multi-round carry-over / versus modes). Only shown when both
        # Showdown and Party are off. Reads as "Runda <current> / <total>".
        # Booster charge carries across rounds and score is cumulative, so the
        # bot uses total/current to derive moves_left_in_match for charge banking.
        self.RoundsLabel = QtWidgets.QLabel(self.StateGroup)
        self.RoundsLabel.setGeometry(QtCore.QRect(330, 62, 18, 21))
        self.RoundsLabel.setObjectName("RoundsLabel")
        self.CurrentRoundSpin = QtWidgets.QSpinBox(self.StateGroup)
        self.CurrentRoundSpin.setGeometry(QtCore.QRect(348, 58, 36, 27))
        self.CurrentRoundSpin.setRange(1, 9)
        self.CurrentRoundSpin.setValue(1)
        self.CurrentRoundSpin.setToolTip(
            "Trenutna runda (1 = prva). U poslednjoj rundi bot igra kao da nema "
            "prenosa jer charge vise ne ide u sledecu rundu."
        )
        self.CurrentRoundSpin.setObjectName("CurrentRoundSpin")
        self.RoundsSepLabel = QtWidgets.QLabel(self.StateGroup)
        self.RoundsSepLabel.setGeometry(QtCore.QRect(385, 62, 10, 21))
        self.RoundsSepLabel.setObjectName("RoundsSepLabel")
        self.TotalRoundsSpin = QtWidgets.QSpinBox(self.StateGroup)
        self.TotalRoundsSpin.setGeometry(QtCore.QRect(395, 58, 36, 27))
        self.TotalRoundsSpin.setRange(1, 9)
        self.TotalRoundsSpin.setValue(3)
        self.TotalRoundsSpin.setToolTip(
            "Ukupan broj rundi u mecu. Booster charge se prenosi kroz runde, "
            "skor se sabira do kraja - veci ukupni skor pobedjuje."
        )
        self.TotalRoundsSpin.setObjectName("TotalRoundsSpin")
        # Auto round tracking reads every visible round marker plus the enlarged
        # active number below the score. Move-dot refill remains a fallback for
        # layouts where that marker is temporarily unavailable.
        self.AutoRoundCheck = QtWidgets.QCheckBox(self.StateGroup)
        self.AutoRoundCheck.setGeometry(QtCore.QRect(433, 58, 37, 27))
        self.AutoRoundCheck.setChecked(True)
        self.AutoRoundCheck.setToolTip(
            "Automatski procitaj trenutnu i ukupan broj rundi ispod skora "
            "(radi samo uz Auto stanje). Dopuna tackica poteza je samo rezervni "
            "signal. Iskljuci za rucno pracenje."
        )
        self.AutoRoundCheck.setObjectName("AutoRoundCheck")
        # Showdown booster-rush toggle. Lives where the rounds row sits because
        # rounds are versus-only and this is solo-only: _update_rounds_controls
        # shows exactly one of them, so they never overlap on screen.
        self.ShowdownBoosterRushCheck = QtWidgets.QCheckBox(self.StateGroup)
        self.ShowdownBoosterRushCheck.setGeometry(QtCore.QRect(330, 60, 140, 27))
        self.ShowdownBoosterRushCheck.setChecked(True)
        self.ShowdownBoosterRushCheck.setToolTip(
            "Showdown/Party (solo): juri da napuni plavi booster i baci ga sto "
            "pre. Extra potez gubi automatsko prvenstvo i takmici se sa punjenjem "
            "na istoj skali: potez koji kompletira booster ili donosi 3+ plavih "
            "(2+ kad je merac blizu punog) pobedjuje extra, dok se zbog 1-2 "
            "usamljene plave potez ne trosi. Kad plavog nema, extra se igra "
            "normalno. Iskljuci za stari kategorijski extra prioritet."
        )
        self.ShowdownBoosterRushCheck.setObjectName("ShowdownBoosterRushCheck")
        # Retain hidden fixed-value widgets for backwards-compatible state
        # serialization; live lookahead is fixed at 10/2/4, or 10/3/4 in Solo
        # Challenge (see selected_lookahead).
        self.LookaheadLabel = QtWidgets.QLabel(self.StateGroup)
        self.LookaheadLabel.setGeometry(QtCore.QRect(20, 96, 150, 21))
        self.LookaheadLabel.setObjectName("LookaheadLabel")
        self.LookaheadCandSpin = QtWidgets.QSpinBox(self.StateGroup)
        self.LookaheadCandSpin.setGeometry(QtCore.QRect(170, 92, 48, 27))
        self.LookaheadCandSpin.setRange(
            LIVE_LOOKAHEAD_CANDIDATES, LIVE_LOOKAHEAD_CANDIDATES
        )
        self.LookaheadCandSpin.setValue(LIVE_LOOKAHEAD_CANDIDATES)
        self.LookaheadCandSpin.setToolTip(
            "Koliko najboljih poteza dobija dublju analizu (lookahead). "
            f"Default {LIVE_LOOKAHEAD_CANDIDATES}. Raste linearno (jeftino)."
        )
        self.LookaheadCandSpin.setObjectName("LookaheadCandSpin")
        self.LookaheadDepthSpin = QtWidgets.QSpinBox(self.StateGroup)
        self.LookaheadDepthSpin.setGeometry(QtCore.QRect(225, 92, 48, 27))
        # The range spans both live depths so a saved Solo Challenge state can
        # still round-trip through this widget.
        self.LookaheadDepthSpin.setRange(
            min(LIVE_LOOKAHEAD_DEPTH, SOLO_CHALLENGE_LOOKAHEAD_DEPTH),
            max(LIVE_LOOKAHEAD_DEPTH, SOLO_CHALLENGE_LOOKAHEAD_DEPTH),
        )
        self.LookaheadDepthSpin.setValue(LIVE_LOOKAHEAD_DEPTH)
        self.LookaheadDepthSpin.setToolTip(
            "Dubina: koliko poteza unapred gleda (2 = 1 potez unapred, "
            f"3 = 2 poteza). Default {LIVE_LOOKAHEAD_DEPTH}, "
            f"{SOLO_CHALLENGE_LOOKAHEAD_DEPTH} u Solo Challenge. "
            "Raste eksponencijalno."
        )
        self.LookaheadDepthSpin.setObjectName("LookaheadDepthSpin")
        self.LookaheadBeamSpin = QtWidgets.QSpinBox(self.StateGroup)
        self.LookaheadBeamSpin.setGeometry(QtCore.QRect(280, 92, 48, 27))
        self.LookaheadBeamSpin.setRange(
            LIVE_LOOKAHEAD_BEAM_WIDTH, LIVE_LOOKAHEAD_BEAM_WIDTH
        )
        self.LookaheadBeamSpin.setValue(LIVE_LOOKAHEAD_BEAM_WIDTH)
        self.LookaheadBeamSpin.setToolTip(
            "Beam: how many branches to keep at each future level. "
            f"Default {LIVE_LOOKAHEAD_BEAM_WIDTH}."
        )
        self.LookaheadBeamSpin.setObjectName("LookaheadBeamSpin")
        # Multiplier mushrooms: the number printed on a mushroom's cap (green
        # +1, orange +2, purple +3, yellow +4) is what the game pays for it.
        # Off by default -- on a board where mushrooms are plain collectibles a
        # cap-colour preference would be invented, not read.
        self.MushroomMultiplierCheck = QtWidgets.QCheckBox(self.StateGroup)
        self.MushroomMultiplierCheck.setGeometry(QtCore.QRect(20, 92, 250, 27))
        self.MushroomMultiplierCheck.setToolTip(
            "Pecurke nose mnozilac ispisan na klobuku: zelena +1, narandzasta "
            "+2, ljubicasta +3, zuta +4. Ukljuceno, bot bira pecurku po njenoj "
            "vrednosti (a ne 'bilo koju') i racuna ih u svakom modu. "
            "Iskljuceno, vazi staro ravno bodovanje samo u Multiplier "
            "Mushrooms modu."
        )
        self.MushroomMultiplierCheck.setObjectName("MushroomMultiplierCheck")
        for lookahead_widget in (
            self.LookaheadLabel,
            self.LookaheadCandSpin,
            self.LookaheadDepthSpin,
            self.LookaheadBeamSpin,
        ):
            lookahead_widget.setVisible(False)

        # Swipe tuning — live adjustment of runtime swipe timing constants so
        # the user can dial in BlueStacks responsiveness without restarting.
        # Spinbox changes push directly into runtime module globals; runtime.swipe()
        # reads them on every call, so updates take effect on the next swipe.
        self.SwipeTuningGroup = QtWidgets.QGroupBox(self.centralwidget)
        self.SwipeTuningGroup.setGeometry(QtCore.QRect(10, 922, 470, 175))
        self.SwipeTuningGroup.setObjectName("SwipeTuningGroup")
        # Shares the y band with EnergizedGroup, so _update_energized_controls
        # moves it down whenever that group is on screen.
        self.SwipeDurationLabel = QtWidgets.QLabel(self.SwipeTuningGroup)
        self.SwipeDurationLabel.setGeometry(QtCore.QRect(10, 32, 60, 21))
        self.SwipeDurationLabel.setObjectName("SwipeDurationLabel")
        self.SwipeDurationSpin = QtWidgets.QDoubleSpinBox(self.SwipeTuningGroup)
        self.SwipeDurationSpin.setGeometry(QtCore.QRect(70, 30, 60, 24))
        self.SwipeDurationSpin.setDecimals(3)
        self.SwipeDurationSpin.setRange(0.010, 0.500)
        self.SwipeDurationSpin.setSingleStep(0.005)
        self.SwipeDurationSpin.setValue(runtime.SWIPE_DURATION_SECONDS)
        self.SwipeDurationSpin.setSuffix(" s")
        self.SwipeDurationSpin.setToolTip(
            "Trajanje glajda od pocetne do ciljne tacke. Manje = brze, ali "
            "ispod ~0.025s rastu sanse da BlueStacks ne registruje fling."
        )
        self.SwipeDurationSpin.setObjectName("SwipeDurationSpin")
        self.SwipeDistanceLabel = QtWidgets.QLabel(self.SwipeTuningGroup)
        self.SwipeDistanceLabel.setGeometry(QtCore.QRect(140, 32, 60, 21))
        self.SwipeDistanceLabel.setObjectName("SwipeDistanceLabel")
        self.SwipeDistanceSpin = QtWidgets.QSpinBox(self.SwipeTuningGroup)
        self.SwipeDistanceSpin.setGeometry(QtCore.QRect(200, 30, 55, 24))
        self.SwipeDistanceSpin.setRange(20, 120)
        self.SwipeDistanceSpin.setSingleStep(5)
        self.SwipeDistanceSpin.setValue(runtime.SWIPE_DISTANCE_PX)
        self.SwipeDistanceSpin.setSuffix(" px")
        self.SwipeDistanceSpin.setToolTip(
            "Distanca putanje swipea. Veca distanca = veca brzina pri istom "
            "trajanju i sigurnije prelazi Android fling threshold."
        )
        self.SwipeDistanceSpin.setObjectName("SwipeDistanceSpin")
        self.SwipePreHoldLabel = QtWidgets.QLabel(self.SwipeTuningGroup)
        self.SwipePreHoldLabel.setGeometry(QtCore.QRect(265, 32, 32, 21))
        self.SwipePreHoldLabel.setObjectName("SwipePreHoldLabel")
        self.SwipePreHoldSpin = QtWidgets.QDoubleSpinBox(self.SwipeTuningGroup)
        self.SwipePreHoldSpin.setGeometry(QtCore.QRect(297, 30, 60, 24))
        self.SwipePreHoldSpin.setDecimals(3)
        self.SwipePreHoldSpin.setRange(0.000, 0.100)
        self.SwipePreHoldSpin.setSingleStep(0.001)
        self.SwipePreHoldSpin.setValue(runtime.SWIPE_PRE_MOVE_HOLD_SECONDS)
        self.SwipePreHoldSpin.setSuffix(" s")
        self.SwipePreHoldSpin.setToolTip(
            "Pauza posle mouseDown pre prvog pokreta. Pomaze Androidu da "
            "razlikuje press+drift od taptap-a. 0.003-0.005s je dovoljno."
        )
        self.SwipePreHoldSpin.setObjectName("SwipePreHoldSpin")
        self.SwipePostHoldLabel = QtWidgets.QLabel(self.SwipeTuningGroup)
        self.SwipePostHoldLabel.setGeometry(QtCore.QRect(365, 32, 35, 21))
        self.SwipePostHoldLabel.setObjectName("SwipePostHoldLabel")
        self.SwipePostHoldSpin = QtWidgets.QDoubleSpinBox(self.SwipeTuningGroup)
        self.SwipePostHoldSpin.setGeometry(QtCore.QRect(400, 30, 60, 24))
        self.SwipePostHoldSpin.setDecimals(3)
        self.SwipePostHoldSpin.setRange(0.000, 0.100)
        self.SwipePostHoldSpin.setSingleStep(0.001)
        self.SwipePostHoldSpin.setValue(runtime.SWIPE_POST_MOVE_HOLD_SECONDS)
        self.SwipePostHoldSpin.setSuffix(" s")
        self.SwipePostHoldSpin.setToolTip(
            "Pauza posle poslednjeg move pre mouseUp. Daje BlueStacks-u clean "
            "frame da commit-uje fling. Najvazniji za pouzdanost — ako swipe "
            "promasi, prvo podigni ovu vrednost."
        )
        self.SwipePostHoldSpin.setObjectName("SwipePostHoldSpin")

        # Row 2: recorder controls. The button captures one real hand flick,
        # the status label shows whether a profile is loaded, and the checkbox
        # toggles between recorded-profile replay and synthetic spinbox-driven
        # swipe at runtime.
        self.SwipeRecordButton = QtWidgets.QToolButton(self.SwipeTuningGroup)
        self.SwipeRecordButton.setGeometry(QtCore.QRect(10, 65, 110, 28))
        self.SwipeRecordButton.setToolTip(
            "Record a real mouse flick. After clicking, move to "
            "BlueStacks and do a quick swipe — that path becomes "
            "the template for all 4 directions (rotated as needed)."
        )
        self.SwipeRecordButton.setObjectName("SwipeRecordButton")
        self.SwipeProfileStatus = QtWidgets.QLabel(self.SwipeTuningGroup)
        self.SwipeProfileStatus.setGeometry(QtCore.QRect(130, 68, 200, 22))
        status_label_font = QtGui.QFont()
        status_label_font.setPointSize(9)
        self.SwipeProfileStatus.setFont(status_label_font)
        self.SwipeProfileStatus.setObjectName("SwipeProfileStatus")
        self.SwipeUseProfileCheck = QtWidgets.QCheckBox(self.SwipeTuningGroup)
        self.SwipeUseProfileCheck.setGeometry(QtCore.QRect(335, 68, 125, 22))
        self.SwipeUseProfileCheck.setFont(status_label_font)
        self.SwipeUseProfileCheck.setToolTip(
            "When enabled, swipe replays the recording. When disabled, "
            "the spinboxes above are used (synthetic flick). Can be toggled on the fly."
        )
        self.SwipeUseProfileCheck.setObjectName("SwipeUseProfileCheck")
        # Row 4 (y=135, below the auto-timing row): replay speed. Compresses
        # the recorded flick's timeline so the replay is faster than the
        # original hand gesture without re-recording.
        self.SwipeProfileSpeedLabel = QtWidgets.QLabel(self.SwipeTuningGroup)
        self.SwipeProfileSpeedLabel.setGeometry(QtCore.QRect(10, 137, 90, 21))
        self.SwipeProfileSpeedLabel.setFont(status_label_font)
        self.SwipeProfileSpeedLabel.setObjectName("SwipeProfileSpeedLabel")
        self.SwipeProfileSpeedSpin = QtWidgets.QDoubleSpinBox(self.SwipeTuningGroup)
        self.SwipeProfileSpeedSpin.setGeometry(QtCore.QRect(100, 135, 65, 24))
        self.SwipeProfileSpeedSpin.setDecimals(2)
        self.SwipeProfileSpeedSpin.setRange(0.50, 6.00)
        self.SwipeProfileSpeedSpin.setSingleStep(0.25)
        self.SwipeProfileSpeedSpin.setValue(runtime.SWIPE_PROFILE_SPEED)
        self.SwipeProfileSpeedSpin.setSuffix(" x")
        self.SwipeProfileSpeedSpin.setToolTip(
            "Brzina reprodukcije snimljenog swipea: 2x pusta snimak duplo brze "
            "(ista putanja, veca brzina kursora). Igra registruje swipe vec "
            "posle par piksela, pa je ubrzanje bezbedno — samo ispod 1x rizikuje "
            "da fling ne bude prepoznat."
        )
        self.SwipeProfileSpeedSpin.setObjectName("SwipeProfileSpeedSpin")
        self._swipe_recorder_thread = None
        self._swipe_recorder_worker = None

        # Debounced auto-save for tuning controls: each spinbox/checkbox
        # change restarts a 1s single-shot timer; when it expires, we write
        # gui_state.json. Without this, save_gui_state only fires on app
        # aboutToQuit — so a hard kill or crash loses the user's tweaks.
        # 1s is short enough to feel "saved" but long enough to coalesce
        # the burst of valueChanged signals fired while typing into a spinbox.
        self._tuning_save_timer = QtCore.QTimer(MainWindow)
        self._tuning_save_timer.setSingleShot(True)
        self._tuning_save_timer.setInterval(1000)
        self._tuning_save_timer.timeout.connect(self.save_gui_state)

        # Row 3: auto-loop pacing. These are the biggest pauses BETWEEN moves
        # (cooldown after a swipe, cursor-return wait, and the auto-tick poll
        # interval). Exposing them here lets the user trade reliability for
        # speed without editing runtime.py and restarting.
        self.AutoCooldownLabel = QtWidgets.QLabel(self.SwipeTuningGroup)
        self.AutoCooldownLabel.setGeometry(QtCore.QRect(10, 105, 65, 21))
        self.AutoCooldownLabel.setObjectName("AutoCooldownLabel")
        self.AutoCooldownSpin = QtWidgets.QSpinBox(self.SwipeTuningGroup)
        self.AutoCooldownSpin.setGeometry(QtCore.QRect(75, 103, 55, 24))
        self.AutoCooldownSpin.setRange(0, 500)
        self.AutoCooldownSpin.setSingleStep(10)
        self.AutoCooldownSpin.setValue(int(round(runtime.AUTO_POST_MOVE_COOLDOWN_SECONDS * 1000)))
        self.AutoCooldownSpin.setSuffix(" ms")
        self.AutoCooldownSpin.setToolTip(
            "Pause after a regular move before the next scan starts. Gives "
            "the game time to finish the cascade animation — too low and the bot "
            "will see a moving board and potentially make a bad move."
        )
        self.AutoCooldownSpin.setObjectName("AutoCooldownSpin")
        self.CursorReturnDelayLabel = QtWidgets.QLabel(self.SwipeTuningGroup)
        self.CursorReturnDelayLabel.setGeometry(QtCore.QRect(145, 105, 70, 21))
        self.CursorReturnDelayLabel.setObjectName("CursorReturnDelayLabel")
        self.CursorReturnDelaySpin = QtWidgets.QSpinBox(self.SwipeTuningGroup)
        self.CursorReturnDelaySpin.setGeometry(QtCore.QRect(215, 103, 55, 24))
        self.CursorReturnDelaySpin.setRange(0, 200)
        self.CursorReturnDelaySpin.setSingleStep(5)
        self.CursorReturnDelaySpin.setValue(int(round(runtime.CURSOR_RETURN_AFTER_SWIPE_DELAY_SECONDS * 1000)))
        self.CursorReturnDelaySpin.setSuffix(" ms")
        self.CursorReturnDelaySpin.setToolTip(
            "Pause between the end of the swipe and returning the cursor to "
            "its original position. Prevents BlueStacks from interpreting the "
            "sudden cursor return as a new gesture. Can be lowered with a recording."
        )
        self.CursorReturnDelaySpin.setObjectName("CursorReturnDelaySpin")
        self.AutoScanIntervalLabel = QtWidgets.QLabel(self.SwipeTuningGroup)
        self.AutoScanIntervalLabel.setGeometry(QtCore.QRect(285, 105, 65, 21))
        self.AutoScanIntervalLabel.setObjectName("AutoScanIntervalLabel")
        self.AutoScanIntervalSpin = QtWidgets.QSpinBox(self.SwipeTuningGroup)
        self.AutoScanIntervalSpin.setGeometry(QtCore.QRect(350, 103, 55, 24))
        self.AutoScanIntervalSpin.setRange(10, 100)
        self.AutoScanIntervalSpin.setSingleStep(1)
        self.AutoScanIntervalSpin.setValue(runtime.AUTO_SCAN_INTERVAL_MS)
        self.AutoScanIntervalSpin.setSuffix(" ms")
        self.AutoScanIntervalSpin.setToolTip(
            "How often the auto loop checks if it's time for the next scan. "
            "Below 16ms there's no point (60Hz monitor cap). Higher value = less "
            "CPU usage, slower response to board changes."
        )
        self.AutoScanIntervalSpin.setObjectName("AutoScanIntervalSpin")
        # Row 4 continued: settle wall-clock floors. These are the dominant
        # per-move waits — after a cascade the board must read identical for
        # this long before Auto plays. Lowering them plays "as soon as possible";
        # too low and a calm frame between animation phases can pass as settled.
        self.AutoStableMinLabel = QtWidgets.QLabel(self.SwipeTuningGroup)
        self.AutoStableMinLabel.setGeometry(QtCore.QRect(175, 137, 60, 21))
        self.AutoStableMinLabel.setFont(status_label_font)
        self.AutoStableMinLabel.setObjectName("AutoStableMinLabel")
        self.AutoStableMinSpin = QtWidgets.QSpinBox(self.SwipeTuningGroup)
        self.AutoStableMinSpin.setGeometry(QtCore.QRect(235, 135, 60, 24))
        self.AutoStableMinSpin.setRange(0, 500)
        self.AutoStableMinSpin.setSingleStep(10)
        self.AutoStableMinSpin.setValue(int(round(runtime.AUTO_MIN_STABLE_SECONDS * 1000)))
        self.AutoStableMinSpin.setSuffix(" ms")
        self.AutoStableMinSpin.setToolTip(
            "How long the same recognized board must stay stable before Auto "
            "plays a move (with 2-3 identical scans). Lower = move starts sooner; "
            "below ~50ms there's a risk the bot plays between two animation phases."
        )
        self.AutoStableMinSpin.setObjectName("AutoStableMinSpin")
        self.AutoNoMatchSettleLabel = QtWidgets.QLabel(self.SwipeTuningGroup)
        self.AutoNoMatchSettleLabel.setGeometry(QtCore.QRect(305, 137, 70, 21))
        self.AutoNoMatchSettleLabel.setFont(status_label_font)
        self.AutoNoMatchSettleLabel.setObjectName("AutoNoMatchSettleLabel")
        self.AutoNoMatchSettleSpin = QtWidgets.QSpinBox(self.SwipeTuningGroup)
        self.AutoNoMatchSettleSpin.setGeometry(QtCore.QRect(375, 135, 60, 24))
        self.AutoNoMatchSettleSpin.setRange(0, 500)
        self.AutoNoMatchSettleSpin.setSingleStep(10)
        self.AutoNoMatchSettleSpin.setValue(
            int(round(runtime.AUTO_NO_MATCH_SETTLE_SECONDS * 1000))
        )
        self.AutoNoMatchSettleSpin.setSuffix(" ms")
        self.AutoNoMatchSettleSpin.setToolTip(
            "Settle prozor za tablu bez vidljivog matcha uprkos kozmetickoj "
            "animaciji (fitilj bombe, glow). Klampuje se navise na 'Stab. min' "
            "ako je manji od njega."
        )
        self.AutoNoMatchSettleSpin.setObjectName("AutoNoMatchSettleSpin")

        self.auto_stability = AutoMoveStability()
        self.auto_timer = QtCore.QTimer(MainWindow)
        self.auto_timer.setInterval(AUTO_SCAN_INTERVAL_MS)
        self._auto_cooldown_until = 0.0
        self._auto_perk_cooldown_until = 0.0
        self._auto_in_progress = False
        self._auto_scan_thread = None
        self._auto_scan_worker = None
        self._auto_scan_busy = False
        self._auto_scan_reset_motion = True
        self._auto_scan_failure_count = 0
        self._auto_prep_thread = None
        self._auto_prep_worker = None
        self._auto_prep_busy = False
        self._auto_prep_result = None
        self._auto_pending_play = None
        self._check_worker_thread = None
        self._check_worker = None
        self._booster_attempt_signature = None
        self._booster_unchanged_ticks = 0
        self._auto_unchanged_after_play_ticks = 0
        self._booster_attempt_started_at = 0.0
        self._auto_last_action_finished_at = 0.0
        self._force_no_booster_next = False
        self._auto_perk_used_this_run = False
        # Watchdog state: _auto_watchdog_last_progress is the monotonic time of the
        # last launched play; _auto_busy_watch_start is when a busy flag first went
        # True in the current stuck window; _auto_force_play_next asks the next
        # readable scan to play instead of waiting. See AUTO_WATCHDOG_* constants.
        self._auto_watchdog_last_progress = 0.0
        self._auto_busy_watch_start = None
        self._auto_force_play_next = False
        # When scans continuously read unrecognized cells, this is the monotonic
        # time the blockage started; None while the board reads clean.
        self._auto_unrecognized_block_since = None
        # True while a PLAY AGAIN false positive (readable board) is being
        # ignored, so the console notice prints once per streak, not per scan.
        self._auto_replay_fp_active = False
        # True while AutoStatus shows a wait diagnostic ("ceka animaciju" etc.):
        # chained scans fire immediately, so without this flag auto_tick would
        # overwrite the diagnostic with "Auto: skeniram" before anyone reads it.
        self._auto_wait_status_sticky = False
        # Last explicit blue/pink turn banner. A confirmed blue turn may bridge
        # the shrinking Time Left fill, but this latch is cleared after every
        # sent action so a second action always needs a fresh blue confirmation.
        self._auto_turn_owner_latch = None
        # Last accepted auto-read dot count, for round auto-advance. None until
        # the first accepted read of a rounds-mode game (see _track_auto_round).
        self._last_tracked_remaining_moves = None
        # Candidate move count awaiting a second agreeing read, used to debounce
        # implausible drops read mid-animation (see _accept_remaining_moves_read).
        self._pending_remaining_moves_read = None
        self._booster_charge_maximum = BOOSTER_MAX_CHARGE
        self._manual_stability_retry_kwargs = None
        self._manual_stability_retry_label = None
        self._manual_stability_retry_pending = False
        self._manual_stability_retry_count = 0
        # Reuse one timer whose signal connection is created while the GUI is
        # idle. Creating QTimer.singleShot's internal connection from the
        # worker-finished callback can deadlock with PyQt deleting that worker:
        # the GUI thread holds the GIL while waiting for Qt's connection mutex,
        # and the worker holds that mutex while waiting for the GIL.
        self._manual_stability_retry_timer = QtCore.QTimer(MainWindow)
        self._manual_stability_retry_timer.setSingleShot(True)
        self._manual_stability_retry_timer.timeout.connect(
            self._retry_manual_stability_check
        )
        self._detected_perk_slots = [
            _unknown_perk_detection(1),
            _unknown_perk_detection(2),
        ]
        # Wrap the (taller-than-screen) content in a scroll area so nothing gets
        # cut off; widgetResizable lets it stretch to the window width while the
        # minimum height above forces a vertical scrollbar when needed.
        self.scrollArea = QtWidgets.QScrollArea(MainWindow)
        self.scrollArea.setObjectName("scrollArea")
        self.scrollArea.setWidgetResizable(True)
        self.scrollArea.setWidget(self.centralwidget)
        MainWindow.setCentralWidget(self.scrollArea)
        self.menubar = QtWidgets.QMenuBar(MainWindow)
        self.menubar.setGeometry(QtCore.QRect(0, 0, 457, 21))
        self.menubar.setObjectName("menubar")
        MainWindow.setMenuBar(self.menubar)
        self.statusbar = QtWidgets.QStatusBar(MainWindow)
        self.statusbar.setObjectName("statusbar")
        MainWindow.setStatusBar(self.statusbar)

        self.ActiveButton.clicked.connect(self.best_move_clicked)
        self.ExtraMoveButton.clicked.connect(self.extra_move_clicked)
        self.HighestPointsButton.clicked.connect(self.highest_points_clicked)
        self.Perk1UseButton.clicked.connect(
            lambda _checked=False: self.use_perk_slot_clicked(1)
        )
        self.Perk2UseButton.clicked.connect(
            lambda _checked=False: self.use_perk_slot_clicked(2)
        )
        self.PerksRefreshButton.clicked.connect(
            lambda _checked=False: self.refresh_detected_perks()
        )
        self.AutoButton.toggled.connect(self.auto_toggled)
        self.AutoModeCheck.toggled.connect(self._schedule_tuning_save)
        self.MushroomMultiplierCheck.toggled.connect(self._schedule_tuning_save)
        self.ModeBox.currentIndexChanged.connect(self._update_rounds_controls)
        self.ModeBox.currentIndexChanged.connect(self._update_energized_controls)
        # `activated` fires only on a real user pick, so restoring saved state or
        # auto mode detection never pops the color dialog open mid-game.
        self.ModeBox.activated.connect(self._mode_box_activated)
        self.EnergizedFirstBox.currentIndexChanged.connect(self._schedule_tuning_save)
        self.EnergizedSecondBox.currentIndexChanged.connect(self._schedule_tuning_save)
        self.BoardSourceBox.currentIndexChanged.connect(self._schedule_tuning_save)
        self.EnergizedChangeButton.clicked.connect(
            lambda _checked=False: self.prompt_energized_colors()
        )
        self.NewGameButton.clicked.connect(self.new_game_clicked)
        self.ResetGameButton.clicked.connect(self.reset_game_state)
        self.DebugCaptureButton.clicked.connect(self.debug_capture_clicked)
        self._net_signals = _NetToggleSignals()
        self._net_signals.done.connect(self._on_net_toggle_done)
        self._mm_launch_signals = _MatchMastersLaunchSignals()
        self._mm_launch_signals.progress.connect(self._on_match_masters_launch_progress)
        self._mm_launch_signals.done.connect(self._on_match_masters_launch_done)
        self.LaunchMatchMastersButton.clicked.connect(self.launch_match_masters_clicked)
        self.NetKillButton.toggled.connect(self.net_kill_toggled)
        self.RestartAppButton.clicked.connect(self.restart_app_clicked)
        self.auto_timer.timeout.connect(self.auto_tick)
        self.ScoreRallyCheck.toggled.connect(self.set_score_rally_inputs_enabled)
        self.AutoStateCheck.toggled.connect(self._auto_state_display_toggled)
        self.ShowdownCheck.toggled.connect(
            lambda checked: self._state_mode_toggled(self.ShowdownCheck, checked)
        )
        self.PartyCheck.toggled.connect(
            lambda checked: self._state_mode_toggled(self.PartyCheck, checked)
        )
        self.SoloChallengeCheck.toggled.connect(
            lambda checked: self._state_mode_toggled(self.SoloChallengeCheck, checked)
        )
        self.TotalRoundsSpin.valueChanged.connect(self._update_rounds_controls)
        self._update_rounds_controls()
        for swipe_spin in (
            self.SwipeDurationSpin,
            self.SwipeDistanceSpin,
            self.SwipePreHoldSpin,
            self.SwipePostHoldSpin,
            self.SwipeProfileSpeedSpin,
        ):
            swipe_spin.valueChanged.connect(self._apply_swipe_tuning)
        self.SwipeRecordButton.clicked.connect(self.start_swipe_recording)
        self.SwipeUseProfileCheck.toggled.connect(self._on_swipe_use_profile_toggled)
        for timing_spin in (
            self.AutoCooldownSpin,
            self.CursorReturnDelaySpin,
            self.AutoScanIntervalSpin,
            self.AutoStableMinSpin,
            self.AutoNoMatchSettleSpin,
        ):
            timing_spin.valueChanged.connect(self._apply_auto_timing)

        # Load any persisted recording from disk so it survives restarts. The
        # checkbox state (whether to actually USE the profile) comes from
        # gui_state.json later in load_gui_state.
        persisted_profile = swipe_recorder.load_profile()
        if persisted_profile is not None:
            runtime.SWIPE_PROFILE = persisted_profile

        self.retranslateUi(MainWindow)
        self.BoosterChargeSpin.valueChanged.connect(self._refresh_booster_state_label)
        self._refresh_booster_state_label()
        set_combobox_popup_width_to_contents(self.ModeBox)
        set_combobox_popup_width_to_contents(self.SpecialPieceModeBox)
        set_combobox_popup_width_to_contents(self.MLRecognitionModeBox)
        set_combobox_popup_width_to_contents(self.BoardSourceBox)
        self.set_score_rally_inputs_enabled(False)
        self._update_energized_controls()
        self.set_detected_perk_slots(self._detected_perk_slots)
        # Sync the recorder status label and checkbox state with whatever
        # profile we loaded from disk above (or lack thereof).
        self._refresh_swipe_profile_status()
        QtCore.QMetaObject.connectSlotsByName(MainWindow)

    def retranslateUi(self, MainWindow):
        _translate = QtCore.QCoreApplication.translate
        MainWindow.setWindowTitle(_translate("MainWindow", "MainWindow"))
        for index, mode in enumerate(GUI_GAME_MODE_OPTIONS):
            self.ModeBox.setItemText(index, _translate("MainWindow", mode.value))
        self.AutoModeCheck.setText(_translate("MainWindow", "Auto mod"))
        self.BoardSizeBox.setItemText(0, _translate("MainWindow", "Obicna tabla (7x7)"))
        self.BoardSizeBox.setItemText(1, _translate("MainWindow", "Supersize (8x8)"))
        self.SquareMatchesCheck.setText(_translate("MainWindow", "Square matches"))
        self.ColorCrushCheck.setText(_translate("MainWindow", "Color Crush"))
        self.VerticalMatchesDestroyColorCheck.setText(
            _translate("MainWindow", "Vertical matches destroy color")
        )
        self.SpecialExplodeCheck.setText(_translate("MainWindow", "Special pieces explode immediately"))
        self.BoosterImmediateCheck.setText(_translate("MainWindow", "Booster odmah"))
        for index, (label, _value) in enumerate(BOOSTER_ACTION_OPTIONS):
            self.BoosterActionBox.setItemText(index, _translate("MainWindow", label))
        self.SpecialPieceModeBox.setItemText(0, _translate("MainWindow", "Booster: Auto"))
        self.EnergizedGroup.setTitle(
            _translate("MainWindow", "Energized: boje koje pune booster")
        )
        self.EnergizedFirstLabel.setText(_translate("MainWindow", "Boja 1"))
        self.EnergizedSecondLabel.setText(_translate("MainWindow", "Boja 2"))
        self.EnergizedChangeButton.setText(_translate("MainWindow", "Izaberi..."))
        self.ScoreRallyGroup.setTitle(_translate("MainWindow", "Score Rally"))
        self.ScoreRallyCheck.setText(_translate("MainWindow", "Use Score Rally"))
        self.ScoreLegendAutoCheck.setText(_translate("MainWindow", "Auto legenda"))
        self.ScoreLegendStatusLabel.setText(_translate("MainWindow", ""))
        self.ScoreRallyYellowLabel.setText(_translate("MainWindow", "Zuta"))
        self.ScoreRallyPurpleLabel.setText(_translate("MainWindow", "Ljubicasta"))
        self.ScoreRallyGreenLabel.setText(_translate("MainWindow", "Zelena"))
        self.ScoreRallyBrownLabel.setText(_translate("MainWindow", "Braon"))
        self.PerksGroup.setTitle(_translate("MainWindow", "Perks"))
        self.PerksRefreshButton.setText(_translate("MainWindow", "Refresh"))
        self.Perk1Label.setText(_translate("MainWindow", "Perk 1"))
        self.Perk2Label.setText(_translate("MainWindow", "Perk 2"))
        self.Perk1UseButton.setText(_translate("MainWindow", "Koristi"))
        self.Perk2UseButton.setText(_translate("MainWindow", "Koristi"))
        self.Perk1Status.setText(_translate("MainWindow", _perk_status_text(self._detected_perk_slots[0])))
        self.Perk2Status.setText(_translate("MainWindow", _perk_status_text(self._detected_perk_slots[1])))
        self.ActiveButton.setText(_translate("MainWindow", "Najbolji potez"))
        self.ExtraMoveButton.setText(_translate("MainWindow", "Extra move"))
        self.HighestPointsButton.setText(_translate("MainWindow", "Najvise poena"))
        self.AutoButton.setText(_translate("MainWindow", "Auto"))
        self.AutoReplayCheck.setText(_translate("MainWindow", "Replay"))
        self.NewGameButton.setText(_translate("MainWindow", "Nova partija"))
        self.ResetGameButton.setText(_translate("MainWindow", "Reset partije"))
        self.StateGroup.setTitle(_translate("MainWindow", "Stanje"))
        self.BoosterChargeLabel.setText(_translate("MainWindow", "Booster 0/7"))
        self.RemainingMovesLabel.setText(_translate("MainWindow", "Potezi"))
        self.AutoStateCheck.setText(_translate("MainWindow", "Auto stanje"))
        self.ShowdownCheck.setText(_translate("MainWindow", "Showdown"))
        self.PartyCheck.setText(_translate("MainWindow", "Party"))
        self.SoloChallengeCheck.setText(_translate("MainWindow", "Solo Challenge"))
        self.ShowdownBoosterRushCheck.setText(
            _translate("MainWindow", "Juri booster")
        )
        self.RoundsLabel.setText(_translate("MainWindow", "Runda"))
        self.RoundsSepLabel.setText(_translate("MainWindow", "/"))
        self.AutoRoundCheck.setText(_translate("MainWindow", "auto"))
        self.MushroomMultiplierCheck.setText(
            _translate("MainWindow", "Pecurke = mnozilac (+1..+4)")
        )
        self.LookaheadLabel.setText(_translate("MainWindow", "Lookahead C/D/B"))
        self.SwipeDurationLabel.setText(_translate("MainWindow", "Trajanje"))
        self.SwipeDistanceLabel.setText(_translate("MainWindow", "Distanca"))
        self.SwipePreHoldLabel.setText(_translate("MainWindow", "Pre"))
        self.SwipePostHoldLabel.setText(_translate("MainWindow", "Post"))
        self.SwipeRecordButton.setText(_translate("MainWindow", "Snimi swipe"))
        self.SwipeUseProfileCheck.setText(_translate("MainWindow", "Koristi snimak"))
        self.SwipeProfileSpeedLabel.setText(_translate("MainWindow", "Brzina snimka"))
        # Status text is refreshed dynamically from runtime.SWIPE_PROFILE; this
        # initial value is overwritten by _refresh_swipe_profile_status() called
        # from the wrapper after setupUi completes.
        self.SwipeProfileStatus.setText(_translate("MainWindow", "Nema snimka"))
        self.SwipeTuningGroup.setTitle(_translate("MainWindow", "Tajming"))
        self.AutoCooldownLabel.setText(_translate("MainWindow", "Cooldown"))
        self.CursorReturnDelayLabel.setText(_translate("MainWindow", "Ret. delay"))
        self.AutoScanIntervalLabel.setText(_translate("MainWindow", "Scan int."))
        self.AutoStableMinLabel.setText(_translate("MainWindow", "Stab. min"))
        self.AutoNoMatchSettleLabel.setText(_translate("MainWindow", "Settle"))
        self.AutoStatus.setText(_translate("MainWindow", "Auto: OFF"))
        self.DebugModeCheck.setText(_translate("MainWindow", "Debug mode"))
        self.DebugCaptureButton.setText(_translate("MainWindow", "Slikaj debug"))
        self.NetKillButton.setText(_translate("MainWindow", "Blokiraj BS"))
        self.RestartAppButton.setText(_translate("MainWindow", "Restart bota"))
        self.LaunchMatchMastersButton.setText(_translate("MainWindow", "Pokreni Match Masters"))
        self.ManualRecognitionStabilityCheck.setText(_translate("MainWindow", "Cekaj anim."))
        for index, (label, _value) in enumerate(ML_RECOGNITION_OPTIONS):
            self.MLRecognitionModeBox.setItemText(index, _translate("MainWindow", label))
        for index, (label, _value) in enumerate(BOARD_SOURCE_OPTIONS):
            self.BoardSourceBox.setItemText(index, _translate("MainWindow", label))
        self.BestMove.setText(_translate("MainWindow", "Best Move:"))
        self.Score.setText(_translate("MainWindow", "Score: "))

    def set_score_rally_inputs_enabled(self, enabled):
        for score_input in self.ScoreRallyInputs:
            score_input.setEnabled(enabled)

    def _schedule_tuning_save(self):
        # Restart the debounce timer. Multiple rapid changes coalesce into
        # one disk write 1s after the last change.
        if hasattr(self, "_tuning_save_timer"):
            self._tuning_save_timer.start()

    def _apply_swipe_tuning(self, *_):
        # Push GUI spinbox values into runtime module globals. runtime.swipe()
        # reads the constants at call time, so the next swipe uses the new
        # values — no restart, no reload. The *_ swallows the signal's value
        # arg (valueChanged emits the new value, which we don't need here).
        runtime.SWIPE_DURATION_SECONDS = float(self.SwipeDurationSpin.value())
        runtime.SWIPE_DISTANCE_PX = int(self.SwipeDistanceSpin.value())
        runtime.SWIPE_PRE_MOVE_HOLD_SECONDS = float(self.SwipePreHoldSpin.value())
        runtime.SWIPE_POST_MOVE_HOLD_SECONDS = float(self.SwipePostHoldSpin.value())
        runtime.SWIPE_PROFILE_SPEED = float(self.SwipeProfileSpeedSpin.value())
        self._schedule_tuning_save()

    def _apply_auto_timing(self, *_):
        # Cooldown + return delay are read live by their consumers (we made
        # sure of that in the runtime sentinel refactor and the gui.py
        # runtime.AUTO_POST_MOVE_COOLDOWN_SECONDS lookup).
        runtime.AUTO_POST_MOVE_COOLDOWN_SECONDS = self.AutoCooldownSpin.value() / 1000.0
        runtime.CURSOR_RETURN_AFTER_SWIPE_DELAY_SECONDS = (
            self.CursorReturnDelaySpin.value() / 1000.0
        )
        # Scan interval lives in a QTimer that was set once at construction —
        # update the runtime constant AND tell the timer to re-arm with the
        # new interval so the change is visible immediately.
        new_interval_ms = int(self.AutoScanIntervalSpin.value())
        runtime.AUTO_SCAN_INTERVAL_MS = new_interval_ms
        self.auto_timer.setInterval(new_interval_ms)
        # Settle floors: the AutoMoveStability instance captured the defaults
        # at construction, so push the new values onto the live object with the
        # same ordering clamps its __init__ applies (min <= no_match <= force).
        min_stable = self.AutoStableMinSpin.value() / 1000.0
        no_match_settle = max(min_stable, self.AutoNoMatchSettleSpin.value() / 1000.0)
        runtime.AUTO_MIN_STABLE_SECONDS = min_stable
        runtime.AUTO_NO_MATCH_SETTLE_SECONDS = no_match_settle
        self.auto_stability.min_stable_seconds = min_stable
        self.auto_stability.no_match_settle_seconds = no_match_settle
        self.auto_stability.force_settle_seconds = max(
            no_match_settle, runtime.AUTO_FORCE_SETTLE_SECONDS
        )
        self._schedule_tuning_save()

    def _refresh_swipe_profile_status(self):
        recording = runtime.SWIPE_PROFILE
        if recording is None:
            self.SwipeProfileStatus.setText("Nema snimka")
            # Can't replay nothing — force the checkbox off and grey it out
            # so the user can't enable an empty profile by accident.
            self.SwipeUseProfileCheck.setChecked(False)
            self.SwipeUseProfileCheck.setEnabled(False)
        else:
            self.SwipeProfileStatus.setText("Snimak: " + recording.summary())
            self.SwipeUseProfileCheck.setEnabled(True)

    def _on_swipe_use_profile_toggled(self, checked):
        runtime.SWIPE_USE_PROFILE = bool(checked) and runtime.SWIPE_PROFILE is not None
        self._schedule_tuning_save()

    def start_swipe_recording(self):
        if self._swipe_recorder_thread is not None:
            return  # one recording at a time — ignore re-clicks while in progress
        self.SwipeRecordButton.setEnabled(False)
        self.SwipeProfileStatus.setText("Switch to BlueStacks and do a swipe...")
        thread = QtCore.QThread(self.SwipeTuningGroup)
        worker = SwipeRecorderWorker()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_swipe_recording_finished)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        self._swipe_recorder_thread = thread
        self._swipe_recorder_worker = worker
        thread.start()

    def _on_swipe_recording_finished(self, recording):
        self._swipe_recorder_thread = None
        self._swipe_recorder_worker = None
        self.SwipeRecordButton.setEnabled(True)
        if recording is None:
            # Timeout, drained click, or too-short distance — user retries.
            self.SwipeProfileStatus.setText("Snimanje propalo / prekratko")
            return
        try:
            swipe_recorder.save_profile(recording)
        except Exception:
            pass
        runtime.SWIPE_PROFILE = recording
        self._refresh_swipe_profile_status()
        # Auto-enable on successful capture — user just spent effort recording,
        # they almost certainly want to use it immediately. They can untick if not.
        self.SwipeUseProfileCheck.setChecked(True)

    def gui_state_payload(self):
        return {
            "version": GUI_STATE_VERSION,
            "mode": _json_combo_value(self.ModeBox),
            # Persist the picked colors even while another mode is selected,
            # so switching modes and back does not lose them.
            "energized_colors": list(self._energized_combo_colors()),
            "auto_mode_detection": self.AutoModeCheck.isChecked(),
            "board_profile": _json_combo_value(self.BoardSizeBox),
            "booster_action_mode": self.selected_booster_action_mode(),
            "special_piece_mode": self.selected_special_piece_mode(),
            "square_matches": self.SquareMatchesCheck.isChecked(),
            "color_crush": self.ColorCrushCheck.isChecked(),
            "vertical_matches_destroy_color": self.VerticalMatchesDestroyColorCheck.isChecked(),
            "specials_explode_immediately": self.SpecialExplodeCheck.isChecked(),
            "booster_immediately": self.BoosterImmediateCheck.isChecked(),
            "score_rally_enabled": self.ScoreRallyCheck.isChecked(),
            "score_legend_auto": self.ScoreLegendAutoCheck.isChecked(),
            "score_rally": {
                "yellow": self.ScoreRallyYellow.value(),
                "purple": self.ScoreRallyPurple.value(),
                "green": self.ScoreRallyGreen.value(),
                "brown": self.ScoreRallyBrown.value(),
            },
            "debug_mode": self.DebugModeCheck.isChecked(),
            "board_source": self.BoardSourceBox.currentData() or BOARD_SOURCE_ML,
            "ml_recognition_mode": self.MLRecognitionModeBox.currentData() or ML_RECOGNITION_ONLY,
            "manual_recognition_stability": self.ManualRecognitionStabilityCheck.isChecked(),
            "auto_replay": self.AutoReplayCheck.isChecked(),
            "booster_charge": self.BoosterChargeSpin.value(),
            "remaining_moves": self.RemainingMovesSpin.value(),
            "auto_state": self.AutoStateCheck.isChecked(),
            "showdown_mode": self.ShowdownCheck.isChecked(),
            "solo_challenge_mode": self.SoloChallengeCheck.isChecked(),
            "showdown_booster_rush": self.ShowdownBoosterRushCheck.isChecked(),
            "mushroom_multipliers": self.MushroomMultiplierCheck.isChecked(),
            "use_perks": self.PerksGroup.isChecked(),
            "party_mode": self.PartyCheck.isChecked(),
            "total_rounds": self.TotalRoundsSpin.value(),
            "current_round": self.CurrentRoundSpin.value(),
            "auto_round_tracking": self.AutoRoundCheck.isChecked(),
            "lookahead": {
                "candidates": self.LookaheadCandSpin.value(),
                "depth": self.LookaheadDepthSpin.value(),
                "beam_width": self.LookaheadBeamSpin.value(),
            },
            "swipe": {
                "duration": self.SwipeDurationSpin.value(),
                "distance_px": int(self.SwipeDistanceSpin.value()),
                "pre_hold": self.SwipePreHoldSpin.value(),
                "post_hold": self.SwipePostHoldSpin.value(),
                "use_profile": self.SwipeUseProfileCheck.isChecked(),
                "profile_speed": self.SwipeProfileSpeedSpin.value(),
            },
            "auto_timing": {
                "post_move_cooldown_ms": int(self.AutoCooldownSpin.value()),
                "cursor_return_delay_ms": int(self.CursorReturnDelaySpin.value()),
                "scan_interval_ms": int(self.AutoScanIntervalSpin.value()),
                "min_stable_ms": int(self.AutoStableMinSpin.value()),
                "no_match_settle_ms": int(self.AutoNoMatchSettleSpin.value()),
            },
        }

    def save_gui_state(self):
        try:
            GUI_STATE_PATH.write_text(
                json.dumps(self.gui_state_payload(), indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    def load_gui_state(self):
        if not GUI_STATE_PATH.exists():
            return
        try:
            payload = json.loads(GUI_STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return
        if not isinstance(payload, dict):
            return

        _set_combo_data(self.ModeBox, payload.get("mode"))
        energized_colors = payload.get("energized_colors")
        if isinstance(energized_colors, (list, tuple)):
            colors = list(normalize_energized_colors(energized_colors))
            colors += [ENERGIZED_NO_COLOR] * (2 - len(colors))
            for box, color in zip(
                (self.EnergizedFirstBox, self.EnergizedSecondBox), colors
            ):
                _set_combo_data(box, color)
        _set_combo_data(self.BoardSizeBox, payload.get("board_profile"))
        _set_combo_data(
            self.BoosterActionBox,
            normalize_booster_action_mode(
                payload.get("booster_action_mode", payload.get("special_piece_mode"))
            ),
        )
        _set_combo_data(
            self.MLRecognitionModeBox,
            normalize_ml_recognition_mode(payload.get("ml_recognition_mode")),
        )
        _set_combo_data(
            self.BoardSourceBox,
            normalize_board_source(payload.get("board_source")),
        )
        if "booster_action_mode" in payload:
            _set_combo_data(
                self.SpecialPieceModeBox,
                normalize_special_piece_mode(payload.get("special_piece_mode")),
            )

        for checkbox, key in (
            (self.AutoModeCheck, "auto_mode_detection"),
            (self.SquareMatchesCheck, "square_matches"),
            (self.ColorCrushCheck, "color_crush"),
            (
                self.VerticalMatchesDestroyColorCheck,
                "vertical_matches_destroy_color",
            ),
            (self.SpecialExplodeCheck, "specials_explode_immediately"),
            (self.BoosterImmediateCheck, "booster_immediately"),
            (self.ScoreRallyCheck, "score_rally_enabled"),
            (self.ScoreLegendAutoCheck, "score_legend_auto"),
            (self.ManualRecognitionStabilityCheck, "manual_recognition_stability"),
            (self.AutoReplayCheck, "auto_replay"),
            (self.AutoStateCheck, "auto_state"),
            (self.ShowdownCheck, "showdown_mode"),
            (self.SoloChallengeCheck, "solo_challenge_mode"),
            (self.ShowdownBoosterRushCheck, "showdown_booster_rush"),
            (self.MushroomMultiplierCheck, "mushroom_multipliers"),
            (self.PerksGroup, "use_perks"),
            (self.PartyCheck, "party_mode"),
            (self.AutoRoundCheck, "auto_round_tracking"),
        ):
            if key in payload:
                checkbox.setChecked(bool(payload[key]))

        # Party was called Rumble until 2026-08-12; keep old saved states working.
        if "party_mode" not in payload and "rumble_mode" in payload:
            self.PartyCheck.setChecked(bool(payload["rumble_mode"]))

        score_rally = payload.get("score_rally")
        if isinstance(score_rally, dict):
            for score_input, key in (
                (self.ScoreRallyYellow, "yellow"),
                (self.ScoreRallyPurple, "purple"),
                (self.ScoreRallyGreen, "green"),
                (self.ScoreRallyBrown, "brown"),
            ):
                if key in score_rally:
                    _set_double_spinbox_value(score_input, score_rally[key])

        if "booster_charge" in payload:
            _set_spinbox_value(self.BoosterChargeSpin, payload["booster_charge"])
        if "remaining_moves" in payload:
            _set_spinbox_value(self.RemainingMovesSpin, payload["remaining_moves"])
        if "total_rounds" in payload:
            _set_spinbox_value(self.TotalRoundsSpin, payload["total_rounds"])
        if "current_round" in payload:
            _set_spinbox_value(self.CurrentRoundSpin, payload["current_round"])
        lookahead = payload.get("lookahead")
        if isinstance(lookahead, dict):
            if "candidates" in lookahead:
                _set_spinbox_value(self.LookaheadCandSpin, lookahead["candidates"])
            if "depth" in lookahead:
                _set_spinbox_value(self.LookaheadDepthSpin, lookahead["depth"])
            if "beam_width" in lookahead:
                _set_spinbox_value(self.LookaheadBeamSpin, lookahead["beam_width"])
        self._update_rounds_controls()
        debug_mode = bool(payload.get("debug_mode", self.DebugModeCheck.isChecked()))
        self.DebugModeCheck.setChecked(debug_mode)

        swipe = payload.get("swipe")
        if isinstance(swipe, dict):
            if "duration" in swipe:
                _set_double_spinbox_value(self.SwipeDurationSpin, swipe["duration"])
            if "distance_px" in swipe:
                _set_spinbox_value(self.SwipeDistanceSpin, swipe["distance_px"])
            if "pre_hold" in swipe:
                _set_double_spinbox_value(self.SwipePreHoldSpin, swipe["pre_hold"])
            if "post_hold" in swipe:
                _set_double_spinbox_value(self.SwipePostHoldSpin, swipe["post_hold"])
            if "profile_speed" in swipe:
                _set_double_spinbox_value(
                    self.SwipeProfileSpeedSpin, swipe["profile_speed"]
                )
            # The spinbox valueChanged signals already pushed each value into
            # runtime as they fired; this call is belt-and-suspenders in case
            # any of the saved values matched the current spinbox value (no
            # signal emitted) and runtime didn't get updated.
            self._apply_swipe_tuning()
            if "use_profile" in swipe:
                # Only honour the saved 'on' state if a recording is actually
                # loaded; otherwise the toggled handler clamps it to False
                # automatically (runtime never replays a None profile).
                self.SwipeUseProfileCheck.setChecked(
                    bool(swipe["use_profile"]) and runtime.SWIPE_PROFILE is not None
                )

        auto_timing = payload.get("auto_timing")
        if isinstance(auto_timing, dict):
            if "post_move_cooldown_ms" in auto_timing:
                _set_spinbox_value(self.AutoCooldownSpin, auto_timing["post_move_cooldown_ms"])
            if "cursor_return_delay_ms" in auto_timing:
                _set_spinbox_value(self.CursorReturnDelaySpin, auto_timing["cursor_return_delay_ms"])
            if "scan_interval_ms" in auto_timing:
                _set_spinbox_value(self.AutoScanIntervalSpin, auto_timing["scan_interval_ms"])
            if "min_stable_ms" in auto_timing:
                _set_spinbox_value(self.AutoStableMinSpin, auto_timing["min_stable_ms"])
            if "no_match_settle_ms" in auto_timing:
                _set_spinbox_value(
                    self.AutoNoMatchSettleSpin, auto_timing["no_match_settle_ms"]
                )
            # Belt-and-suspenders — see comment in load_gui_state swipe block.
            self._apply_auto_timing()

    def score_rally_values(self):
        if not self.ScoreRallyCheck.isChecked():
            return None
        return {
            3: self.ScoreRallyYellow.value(),
            4: self.ScoreRallyPurple.value(),
            2: self.ScoreRallyGreen.value(),
            6: self.ScoreRallyBrown.value(),
        }

    def _score_legend_inputs(self):
        return {
            3: self.ScoreRallyYellow,
            4: self.ScoreRallyPurple,
            2: self.ScoreRallyGreen,
            6: self.ScoreRallyBrown,
        }

    def refresh_score_legend_values(self, state_image):
        """Fill the Score Rally inputs from the on-screen legend.

        The legend rotates every turn, so typing it by hand is impractical and
        was usually stale. Only the colours the reader is sure about are
        written; the rest keep whatever is in the box.
        """
        if not (
            self.ScoreLegendAutoCheck.isChecked()
            and self.ScoreRallyCheck.isChecked()
            and state_image is not None
        ):
            return
        try:
            read = screen_state_reader.read_score_legend(state_image)
        except Exception:
            self.ScoreLegendStatusLabel.setText("legenda: greska")
            return
        if not read.values:
            self.ScoreLegendStatusLabel.setText("legenda: -")
            return
        inputs = self._score_legend_inputs()
        for color, value in read.values.items():
            spinbox = inputs.get(int(color))
            if spinbox is not None:
                _set_double_spinbox_value(spinbox, float(value))
        self.ScoreLegendStatusLabel.setText(f"legenda: {len(read.values)}/4")

    def selected_perks(self):
        if not self.PerksGroup.isChecked():
            return (PERK_NONE, PERK_NONE)
        return perk_detection.available_perks_for_runtime(
            self._detected_perk_slots,
            slot_count=2,
        )

    def selected_perks_for_request(self, forced_perk_slot=None):
        if forced_perk_slot in (1, 2):
            return perk_detection.available_perks_for_runtime(
                self._detected_perk_slots,
                slot_count=2,
            )
        return self.selected_perks()

    def set_detected_perk_slots(self, detections):
        by_slot = {
            detection.slot_number: detection
            for detection in (detections or [])
        }
        self._detected_perk_slots = [
            by_slot.get(1, _unknown_perk_detection(1)),
            by_slot.get(2, _unknown_perk_detection(2)),
        ]
        for label, detection in (
            (self.Perk1Status, self._detected_perk_slots[0]),
            (self.Perk2Status, self._detected_perk_slots[1]),
        ):
            label.setText(_perk_status_text(detection))
            label.setToolTip(
                f"{detection.perk_key} / {detection.status} / {detection.score:.3f}"
            )
            _set_perk_status_style(label, detection)
        self._update_perk_use_buttons()

    def _update_perk_use_buttons(self, worker_busy=None):
        if worker_busy is None:
            worker_busy = self._check_worker_thread is not None
        for button, detection in (
            (self.Perk1UseButton, self._detected_perk_slots[0]),
            (self.Perk2UseButton, self._detected_perk_slots[1]),
        ):
            button.setEnabled(
                not worker_busy
                and detection.available
                and detection.perk_key in runtime.PERK_DEFINITIONS
            )

    def refresh_detected_perks(self):
        try:
            # Refresh can be pressed immediately after BlueStacks switches
            # between fullscreen and a portrait window. Re-resolve the portable
            # board/UI geometry here instead of inheriting coordinates from the
            # previous scan size.
            if not getattr(self, "_skip_next_perk_profile_refresh", False):
                selected_profile = self.BoardSizeBox.currentData() or DEFAULT_PROFILE
                recognition.apply_board_profile(selected_profile)
            self._skip_next_perk_profile_refresh = False
            if self.PartyCheck.isChecked():
                detections = runtime.detect_current_perk_slots(party=True)
            else:
                detections = runtime.detect_current_perk_slots()
        except Exception:
            detections = [_unknown_perk_detection(1), _unknown_perk_detection(2)]
        self.set_detected_perk_slots(detections)
        return self._detected_perk_slots

    def selected_booster_charge(self):
        return self.BoosterChargeSpin.value()

    def _refresh_booster_state_label(self, _value=None):
        current = int(self.BoosterChargeSpin.value())
        maximum = max(current, int(self._booster_charge_maximum or BOOSTER_MAX_CHARGE))
        self.BoosterChargeLabel.setText(f"Booster {current}/{maximum}")

    def _auto_state_display_toggled(self, checked):
        if not checked:
            self._booster_charge_maximum = BOOSTER_MAX_CHARGE
            self.BoosterChargeSpin.setMaximum(BOOSTER_MAX_CHARGE)
            self._refresh_booster_state_label()

    def selected_booster_action_mode(self):
        return normalize_booster_action_mode(
            self.BoosterActionBox.currentData() or BOOSTER_ACTION_NONE
        )

    def selected_special_piece_mode(self):
        return normalize_special_piece_mode(
            self.SpecialPieceModeBox.currentData() or SPECIAL_PIECE_MODE_AUTO
        )



    def selected_remaining_moves(self):
        if self._infinite_moves_selected():
            return None
        value = self.RemainingMovesSpin.value()
        return value if value > 0 else None

    def _energized_mode_selected(self):
        return (
            normalize_game_mode(self.ModeBox.currentData() or self.ModeBox.currentText())
            is GameMode.ENERGIZED
        )

    def _energized_combo_colors(self):
        """Whatever the two color boxes hold, regardless of the selected mode."""
        return normalize_energized_colors(
            box.currentData()
            for box in (self.EnergizedFirstBox, self.EnergizedSecondBox)
        )

    def selected_energized_colors(self):
        """The two colors that fill the booster, empty unless Energized is on."""
        if not self._energized_mode_selected():
            return ()
        return self._energized_combo_colors()

    def _update_energized_controls(self):
        visible = self._energized_mode_selected()
        self.EnergizedGroup.setVisible(visible)
        # Energized and Tajming share the same y band, so the tuning group sits
        # below Energized when it is on screen and takes its place when it is
        # not. Both live under the regular content, so the scrolled widget has
        # to grow for whatever is showing to stay reachable.
        tuning_y = 996 if visible else 922
        self.SwipeTuningGroup.move(10, tuning_y)
        self.centralwidget.setMinimumSize(
            QtCore.QSize(500, tuning_y + self.SwipeTuningGroup.height() + 10)
        )

    def _mode_box_activated(self, _index=None):
        if self._energized_mode_selected():
            self.prompt_energized_colors()

    def prompt_energized_colors(self):
        dialog = EnergizedColorsDialog(
            self.centralwidget.window(),
            self._energized_combo_colors(),
        )
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        colors = list(dialog.selected_colors())
        colors += [ENERGIZED_NO_COLOR] * (2 - len(colors))
        for box, color in (
            (self.EnergizedFirstBox, colors[0]),
            (self.EnergizedSecondBox, colors[1]),
        ):
            index = box.findData(int(color) if color else ENERGIZED_NO_COLOR)
            box.setCurrentIndex(index if index >= 0 else 0)
        self._schedule_tuning_save()

    def _infinite_moves_selected(self):
        return (
            normalize_game_mode(self.ModeBox.currentData() or self.ModeBox.currentText())
            is GameMode.INFINITE_MOVES
        )

    def selected_rounds(self):
        # Round structure only applies to multi-round carry-over (versus) modes.
        # Showdown, Party and Solo Challenge are single-round, so report no
        # rounds there and collapse the match horizon to the current challenge.
        if (
            self.ShowdownCheck.isChecked()
            or self.PartyCheck.isChecked()
            or self.SoloChallengeCheck.isChecked()
            or self._infinite_moves_selected()
        ):
            return None, None
        return self.TotalRoundsSpin.value(), self.CurrentRoundSpin.value()

    def selected_lookahead(self):
        """Fixed live lookahead (candidates, depth, beam_width).

        Solo Challenge is the one mode with no opponent and no clock, so it gets
        the deeper (and ~107ms slower) third ply; timed play stays at depth 2.
        """
        if self.SoloChallengeCheck.isChecked():
            return (
                SOLO_CHALLENGE_LOOKAHEAD_CANDIDATES,
                SOLO_CHALLENGE_LOOKAHEAD_DEPTH,
                SOLO_CHALLENGE_LOOKAHEAD_BEAM_WIDTH,
            )
        return (
            LIVE_LOOKAHEAD_CANDIDATES,
            LIVE_LOOKAHEAD_DEPTH,
            LIVE_LOOKAHEAD_BEAM_WIDTH,
        )

    def _state_mode_toggled(self, selected, checked):
        if checked:
            for checkbox in (
                self.ShowdownCheck,
                self.PartyCheck,
                self.SoloChallengeCheck,
            ):
                if checkbox is not selected and checkbox.isChecked():
                    checkbox.setChecked(False)
        self._update_rounds_controls()

    def _update_rounds_controls(self):
        challenge_state_mode = (
            self.ShowdownCheck.isChecked()
            or self.PartyCheck.isChecked()
            or self.SoloChallengeCheck.isChecked()
        )
        rounds_mode = not challenge_state_mode and not self._infinite_moves_selected()
        for widget in (
            self.RoundsLabel,
            self.CurrentRoundSpin,
            self.RoundsSepLabel,
            self.TotalRoundsSpin,
            self.AutoRoundCheck,
        ):
            widget.setVisible(rounds_mode)
        # Booster-rush is solo-only and shares the rounds row's screen space, so
        # show it exactly when the rounds controls are hidden.
        self.ShowdownBoosterRushCheck.setVisible(challenge_state_mode)
        if not rounds_mode:
            # Solo dot reads must not look like a versus refill once the user
            # switches back to a rounds mode.
            self._last_tracked_remaining_moves = None
        # Keep the current round within the configured total.
        self.CurrentRoundSpin.setMaximum(max(1, self.TotalRoundsSpin.value()))

    def selected_strategy_mode(self):
        if self.PartyCheck.isChecked() or self.SoloChallengeCheck.isChecked():
            return STRATEGY_SOLO_6
        return strategy_mode_from_showdown(self.ShowdownCheck.isChecked())

    def _apply_mode_detection(self, detection, *, source):
        if (
            not self.AutoModeCheck.isChecked()
            or detection is None
            or not getattr(detection, "accepted", False)
        ):
            return False

        old_mode = normalize_game_mode(
            self.ModeBox.currentData() or self.ModeBox.currentText()
        )
        new_mode = normalize_game_mode(detection.mode)
        _set_combo_data(self.ModeBox, new_mode)
        if old_mode != new_mode:
            self.statusbar.showMessage(f"Auto mod: {new_mode.value}", 3000)
        return True

    def _detect_auto_mode_from_live_crop(self):
        if not self.AutoModeCheck.isChecked():
            return None
        try:
            selected_profile = self.BoardSizeBox.currentData() or DEFAULT_PROFILE
            recognition.apply_board_profile(selected_profile)
            board_size = BOARD_PROFILES[selected_profile]["boardSize"]
            region = mode_icon_region(
                recognition.left,
                recognition.up,
                recognition.squareSize,
                board_size,
            )
            icon_image = capture.capture_debug_screenshot(
                output_path=None,
                region=region,
                write_to_disk=False,
            )
            detection = detect_mode_icon(icon_image, region=region)
            self._apply_mode_detection(detection, source="live")
            return detection
        except Exception:
            return None

    def _detect_auto_mode_from_state_image(self, state_image):
        if not self.AutoModeCheck.isChecked() or state_image is None:
            return None
        try:
            selected_profile = self.BoardSizeBox.currentData() or DEFAULT_PROFILE
            recognition.apply_board_profile(selected_profile)
            board_size = BOARD_PROFILES[selected_profile]["boardSize"]
            detection = detect_game_mode_from_screen(
                state_image,
                board_left=recognition.left,
                board_up=recognition.up,
                square_size=recognition.squareSize,
                board_size=board_size,
            )
            self._apply_mode_detection(detection, source="state")
            return detection
        except Exception:
            return None

    def _capture_auto_state_read(self):
        selected_profile = self.BoardSizeBox.currentData() or DEFAULT_PROFILE
        recognition.apply_board_profile(selected_profile)
        state_image = capture.capture_debug_screenshot(
            output_path=None,
            region=None,
            write_to_disk=False,
        )
        auto_read = screen_state_reader.read_screen_state(
            state_image,
            board_profile=selected_profile,
            special_piece_mode=self.selected_special_piece_mode(),
            manual_booster_charge=self.selected_booster_charge(),
            manual_remaining_moves=self.selected_remaining_moves(),
            showdown=self.ShowdownCheck.isChecked(),
            party=self.PartyCheck.isChecked(),
            solo_challenge=self.SoloChallengeCheck.isChecked(),
            total_rounds=(
                None
                if self._rounds_tracking_active() and self.AutoRoundCheck.isChecked()
                else self.selected_rounds()[0]
            ),
            auto_detect_total_rounds=bool(
                self._rounds_tracking_active() and self.AutoRoundCheck.isChecked()
            ),
        )
        return auto_read, state_image

    def _accept_remaining_moves_read(self, remaining_moves):
        """Debounce move-dot counts that fall further than a move can.

        With ``Cekaj anim.`` off the dots are read while they are still
        animating, and a washed-out crop counts fewer filled rings than there
        really are. A play spends one move, so a drop of two or more in a single
        read is not something the game can do -- it is the animation. Such a
        value is held back until a second read agrees with it, which costs one
        frame of staleness and removes the false counts that were switching the
        booster rush off (Debug/runs 2026-08-15_19-47..19-48: four reads).

        Increases are applied immediately: a round refill or an extra move
        genuinely raises the count, and delaying those would stall the round
        tracker.
        """
        current = self.RemainingMovesSpin.value()
        plausible = remaining_moves >= current - 1
        if plausible:
            self._pending_remaining_moves_read = None
            return True
        if self._pending_remaining_moves_read == remaining_moves:
            # Confirmed by a second read -- the drop is real (e.g. the bot missed
            # a frame while two moves were played).
            self._pending_remaining_moves_read = None
            return True
        self._pending_remaining_moves_read = remaining_moves
        return False

    def _track_auto_round(self, remaining_moves):
        """Fallback: advance "Runda" when the versus dot counter refills.

        Within one of our turns the accepted dot count only ever decreases or
        stays equal (an extra move refills the dot it spent: 1->1, 2->2); it
        increases only after the opponent's turn, i.e. when a new round began.
        Direct round-indicator reads take precedence. This is only reached when
        that marker is unavailable, and only with an accepted move-dot read.
        """
        previous = self._last_tracked_remaining_moves
        self._last_tracked_remaining_moves = remaining_moves
        if not self.AutoRoundCheck.isChecked():
            return
        if previous is None or remaining_moves <= previous:
            return
        current = self.CurrentRoundSpin.value()
        total = self.TotalRoundsSpin.value()
        if current >= total:
            # Already at the final round: a refill here means a new match
            # started without "Nova partija"; clamping silently would hide
            # that, so say it out loud instead of advancing.
            return
        self.CurrentRoundSpin.setValue(current + 1)

    def _rounds_tracking_active(self):
        # Round structure (and thus tracking) only exists in versus modes.
        return not (
            self.ShowdownCheck.isChecked()
            or self.PartyCheck.isChecked()
            or self.SoloChallengeCheck.isChecked()
            or self._infinite_moves_selected()
        )

    def _auto_turn_gate_enabled(self):
        # Regular versus and Showdown have alternating players. Party and Solo
        # Challenge do not expose a live opponent turn to wait for.
        return not (
            self.PartyCheck.isChecked()
            or self.SoloChallengeCheck.isChecked()
            or self._infinite_moves_selected()
        )

    def _state_values_for_request(self):
        manual_booster_charge = self.selected_booster_charge()
        manual_remaining_moves = self.selected_remaining_moves()
        if not self.AutoStateCheck.isChecked():
            self._detect_auto_mode_from_live_crop()
            return manual_booster_charge, manual_remaining_moves, None, None

        try:
            if self.ManualRecognitionStabilityCheck.isChecked():
                total_rounds, _current_round = self.selected_rounds()
                (
                    auto_read,
                    state_image,
                    _score_stable,
                    score_samples,
                    state_stable,
                    state_samples,
                    state_reason,
                ) = _capture_stable_auto_state(
                    AutoPrepRequest(
                        auto_state_enabled=True,
                        board_profile=self.BoardSizeBox.currentData() or DEFAULT_PROFILE,
                        special_piece_mode=self.selected_special_piece_mode(),
                        manual_booster_charge=manual_booster_charge,
                        manual_remaining_moves=manual_remaining_moves,
                        showdown=self.ShowdownCheck.isChecked(),
                        party=self.PartyCheck.isChecked(),
                        total_rounds=total_rounds,
                        require_stable_state=True,
                        solo_challenge=self.SoloChallengeCheck.isChecked(),
                        auto_round_detection=bool(
                            self._rounds_tracking_active()
                            and self.AutoRoundCheck.isChecked()
                        ),
                        infinite_moves=self._infinite_moves_selected(),
                    )
                )
            else:
                auto_read, state_image = self._capture_auto_state_read()
                score_samples = ()
                state_stable = True
                state_samples = ()
                state_reason = ""
        except Exception:
            return manual_booster_charge, manual_remaining_moves, None, None

        booster_charge = auto_read.resolved_booster_charge()
        remaining_moves = (
            None
            if self._infinite_moves_selected()
            else auto_read.resolved_remaining_moves()
        )
        self._detect_auto_mode_from_state_image(state_image)
        self._apply_auto_state_controls(auto_read, track_round=True)
        payload = auto_read.to_debug_payload()
        payload["score_stability"] = {
            "enabled": False,
            "stable": None,
            "required_frames": 0,
            "samples": [list(sample) for sample in score_samples],
        }
        payload["state_stability"] = {
            "enabled": self.ManualRecognitionStabilityCheck.isChecked(),
            "stable": bool(state_stable),
            "required_frames": (
                AUTO_STATE_CONFIRMATION_FRAMES
                if self.ManualRecognitionStabilityCheck.isChecked()
                else 0
            ),
            "samples": [
                list(sample) if sample is not None else None
                for sample in state_samples
            ],
            "reason": state_reason,
        }
        return booster_charge, remaining_moves, payload, state_image

    def _apply_auto_state_controls(self, auto_read, *, track_round):
        """Show accepted auto-state reads as soon as they become available.

        Auto prep captures the screen in a background thread before the move
        request consumes that prep.  Waiting until request construction to
        update these spinboxes leaves the visible ``Stanje`` controls one
        capture behind, even though the saved reader payload already contains
        the correct move/booster values.
        """
        if auto_read is None or not all(
            hasattr(auto_read, name)
            for name in (
                "resolved_booster_charge",
                "resolved_remaining_moves",
                "booster_charge",
                "remaining_moves",
            )
        ):
            return
        booster_charge = auto_read.resolved_booster_charge()
        remaining_moves = (
            None
            if self._infinite_moves_selected()
            else auto_read.resolved_remaining_moves()
        )
        if auto_read.booster_charge.accepted and booster_charge is not None:
            read_maximum = getattr(auto_read.booster_charge, "maximum", None)
            booster_source = getattr(auto_read.booster_charge, "source", "")
            if (
                booster_source == "auto_booster_text"
                and isinstance(read_maximum, (int, float))
                and read_maximum > 0
            ):
                self._booster_charge_maximum = int(read_maximum)
                self.BoosterChargeSpin.setMaximum(
                    max(BOOSTER_MAX_CHARGE, self._booster_charge_maximum)
                )
            displayed_charge = booster_charge
            if booster_source == "auto_activate":
                # ACTIVATE has no numeric fraction of its own.  Preserve the
                # last denominator learned from the preceding X/Y frame so a
                # /4 or /6 booster is shown as full on the pulse frame too.
                displayed_charge = self._booster_charge_maximum
            self.BoosterChargeSpin.setValue(displayed_charge)
            self._refresh_booster_state_label()
        if auto_read.remaining_moves.accepted and remaining_moves is not None:
            if self._accept_remaining_moves_read(remaining_moves):
                self.RemainingMovesSpin.setValue(remaining_moves)
        round_read = getattr(auto_read, "current_round", None)
        direct_round_applied = bool(
            self._rounds_tracking_active()
            and self.AutoRoundCheck.isChecked()
            and round_read is not None
            and round_read.accepted
            and round_read.value is not None
        )
        if direct_round_applied:
            detected_total = getattr(round_read, "maximum", None)
            if (
                isinstance(detected_total, (int, float))
                and 2 <= int(detected_total) <= screen_state_reader.ROUND_INDICATOR_MAX_ROUNDS
            ):
                detected_total = int(detected_total)
                if self.TotalRoundsSpin.value() != detected_total:
                    self.TotalRoundsSpin.setValue(detected_total)
            detected_round = max(
                1,
                min(self.TotalRoundsSpin.value(), int(round_read.value)),
            )
            if detected_round < self.CurrentRoundSpin.value():
                # Rounds only ever climb inside a match, so a lower number means
                # a new match started without "Nova partija".  Without this the
                # score tracker keeps the finished match's totals and vetoes the
                # (correct, much lower) live reads as outliers -- Debug
                # 2026-08-08 held 167-160 across all of round 1 while the screen
                # showed 12-53 climbing to 42-53.
                runtime.reset_runtime_score_tracking()
            self.CurrentRoundSpin.setValue(detected_round)
            if remaining_moves is not None:
                self._last_tracked_remaining_moves = remaining_moves
        elif (
            track_round
            and self._rounds_tracking_active()
            and auto_read.remaining_moves.accepted
            and remaining_moves is not None
        ):
            self._track_auto_round(remaining_moves)

    def _state_values_from_prep(self, prep):
        """Consume the speculative background state read; mirrors
        _state_values_for_request, only the capture+OCR already happened."""
        manual_booster_charge = self.selected_booster_charge()
        manual_remaining_moves = self.selected_remaining_moves()
        if not prep.auto_state_enabled or prep.auto_read is None:
            return manual_booster_charge, manual_remaining_moves, None, None
        auto_read = prep.auto_read
        booster_charge = auto_read.resolved_booster_charge()
        remaining_moves = (
            None
            if self._infinite_moves_selected()
            else auto_read.resolved_remaining_moves()
        )
        self._detect_auto_mode_from_state_image(prep.state_image)
        self._apply_auto_state_controls(auto_read, track_round=True)
        payload = auto_read.to_debug_payload()
        payload["score_stability"] = {
            "enabled": False,
            "stable": None,
            "required_frames": 0,
            "samples": [list(sample) for sample in getattr(prep, "score_samples", ())],
        }
        payload["state_stability"] = {
            "enabled": bool(getattr(prep, "stable_state_required", False)),
            "stable": bool(getattr(prep, "state_stable", True)),
            "required_frames": (
                AUTO_STATE_CONFIRMATION_FRAMES
                if getattr(prep, "stable_state_required", False)
                else 0
            ),
            "samples": [
                list(sample) if sample is not None else None
                for sample in getattr(prep, "state_samples", ())
            ],
            "reason": getattr(prep, "state_reason", ""),
        }
        return booster_charge, remaining_moves, payload, prep.state_image

    def _apply_prep_perk_slots(self, prep):
        self.set_detected_perk_slots(list(prep.perk_detections))
        return self._detected_perk_slots

    def clear_used_perk_slot(self, perk_key):
        if perk_key in (None, PERK_NONE):
            return False
        for detection in self._detected_perk_slots:
            if detection.perk_key != perk_key:
                continue
            updated, changed = perk_detection.mark_perk_slot_used(
                self._detected_perk_slots,
                detection.slot_number,
                perk_key,
            )
            if changed:
                self.set_detected_perk_slots(updated)
            return changed
        return False

    def clear_used_perk_slot_number(self, slot_number, expected_perk_key=None):
        if slot_number not in (1, 2):
            return False
        updated, changed = perk_detection.mark_perk_slot_used(
            self._detected_perk_slots,
            slot_number,
            expected_perk_key,
        )
        if changed:
            self.set_detected_perk_slots(updated)
        return changed

    def button_clicked(self, MainWindow):
        self.best_move_clicked()

    def calibrate_screen_clicked(self, checked=False):
        profile = self.BoardSizeBox.currentData() or DEFAULT_PROFILE
        board_size = BOARD_PROFILES[profile]["boardSize"]
        if self.AutoButton.isChecked():
            self.AutoButton.setChecked(False)
        answer = QtWidgets.QMessageBox.information(
            self.centralwidget,
            "Kalibracija ekrana",
            f"Otvori {board_size}x{board_size} tablu u BlueStacks-u bez popup-a.\n\n"
            "Posle OK, klikni centar GORNJEG LEVOG, pa centar DONJEG DESNOG "
            "polja. Klikovi ce biti uhvaceni preko igre i nece je pomeriti.\n\n"
            "Postojeca kalibracija ostaje sacuvana dok ne potvrdis novi rezultat.",
            QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel,
        )
        if answer != QtWidgets.QMessageBox.Ok:
            return
        try:
            window = find_bluestacks_window()
            if bool(getattr(window, "isMinimized", False)):
                window.restore()
            window.activate()
        except Exception as exc:
            QtWidgets.QMessageBox.warning(
                self.centralwidget,
                "Kalibracija nije pokrenuta",
                f"BlueStacks App Player nije pronadjen:\n{exc}",
            )
            return
        self.statusbar.showMessage("Kalibracija: pripremam dva klika...", 3000)
        QtCore.QTimer.singleShot(250, lambda: self._start_calibration_overlay(profile))

    def _start_calibration_overlay(self, profile):
        try:
            window = find_bluestacks_window()
            client_rect = client_rect_for_window(window)
        except Exception as exc:
            QtWidgets.QMessageBox.warning(
                self.centralwidget,
                "Kalibracija nije pokrenuta",
                f"BlueStacks geometrija nije dostupna:\n{exc}",
            )
            return
        overlay = _CalibrationOverlay()
        self._calibration_overlay = overlay
        overlay.completed.connect(
            lambda first, second: self._finish_screen_calibration(
                profile, client_rect, first, second
            )
        )
        overlay.cancelled.connect(self._cancel_screen_calibration)
        overlay.show()
        overlay.raise_()
        overlay.activateWindow()
        overlay.setFocus(QtCore.Qt.ActiveWindowFocusReason)

    def _cancel_screen_calibration(self):
        self._calibration_overlay = None
        self.statusbar.showMessage("Kalibracija otkazana; stara podesavanja nisu menjana", 5000)

    def _finish_screen_calibration(self, profile, client_rect, first, second):
        self._calibration_overlay = None
        board_size = BOARD_PROFILES[profile]["boardSize"]
        try:
            config = validate_board_calibration(
                first,
                second,
                board_size,
                client_rect,
            )
        except BoardCalibrationError as exc:
            QtWidgets.QMessageBox.warning(
                self.centralwidget,
                "Kalibracija odbijena",
                f"Nista nije promenjeno.\n\n{exc}",
            )
            return

        try:
            preview = pyautogui.screenshot(
                region=(
                    config["left"],
                    config["up"],
                    config["width"],
                    config["height"],
                )
            )
        except Exception as exc:
            QtWidgets.QMessageBox.warning(
                self.centralwidget,
                "Kalibracija odbijena",
                f"Tabla nije mogla bezbedno da se snimi; nista nije promenjeno.\n\n{exc}",
            )
            return
        if preview.size != (config["width"], config["height"]):
            QtWidgets.QMessageBox.warning(
                self.centralwidget,
                "Kalibracija odbijena",
                "Snimljeni region nema ocekivanu velicinu; nista nije promenjeno.",
            )
            return
        brightness_min, brightness_max = preview.convert("L").getextrema()
        if brightness_max - brightness_min < 12:
            QtWidgets.QMessageBox.warning(
                self.centralwidget,
                "Kalibracija odbijena",
                "Izabrani region je skoro jednobojan i ne izgleda kao tabla; "
                "nista nije promenjeno.",
            )
            return

        profile_label = "obicna 7x7" if profile == REGULAR_PROFILE else "Supersize 8x8"
        rgb_preview = preview.convert("RGB")
        preview_bytes = rgb_preview.tobytes("raw", "RGB")
        preview_image = QtGui.QImage(
            preview_bytes,
            rgb_preview.width,
            rgb_preview.height,
            rgb_preview.width * 3,
            QtGui.QImage.Format_RGB888,
        ).copy()
        preview_pixmap = QtGui.QPixmap.fromImage(preview_image).scaled(
            260,
            260,
            QtCore.Qt.KeepAspectRatio,
            QtCore.Qt.SmoothTransformation,
        )
        confirmation = QtWidgets.QMessageBox(self.centralwidget)
        confirmation.setWindowTitle("Potvrdi kalibraciju")
        confirmation.setIconPixmap(preview_pixmap)
        confirmation.setText(
            f"Profil: {profile_label}\n"
            f"Tabla: left={config['left']}, up={config['up']}\n"
            f"Polje: {config['squareSize']} px\n"
            f"Velicina: {config['width']} x {config['height']} px\n\n"
            "Proveri sliku table. Sacuvati? Prethodni JSON ce dobiti .bak kopiju."
        )
        confirmation.setStandardButtons(
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        confirmation.setDefaultButton(QtWidgets.QMessageBox.No)
        answer = confirmation.exec_()
        if answer != QtWidgets.QMessageBox.Yes:
            self.statusbar.showMessage(
                "Nova kalibracija nije sacuvana; stara ostaje aktivna", 5000
            )
            return
        try:
            saved = save_board_calibration(
                profile,
                first,
                second,
                client_rect,
                Path(__file__).resolve().parent,
            )
            recognition.apply_board_profile(profile)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(
                self.centralwidget,
                "Kalibracija nije sacuvana",
                f"Doslo je do greske:\n{exc}\n\nRezervna kopija nije obrisana.",
            )
            return
        self.save_gui_state()
        self.BestMove.setText(
            f"Kalibrisano: {profile_label}, polje {saved['squareSize']} px"
        )
        self.statusbar.showMessage(
            "Kalibracija sacuvana i odmah aktivirana", 8000
        )

    def _clear_auto_prep_state(self):
        self._auto_prep_result = None
        if self._auto_pending_play is not None:
            # The deferral set _auto_in_progress; dropping the pending play
            # must release the loop or auto would stall forever.
            self._auto_pending_play = None
            self._auto_in_progress = False

    def _clear_transient_auto_state(self):
        runtime.clear_booster_ready_latch()
        runtime.clear_mixy_code_latch()
        self.auto_stability.reset()
        self._auto_scan_reset_motion = True
        self._clear_auto_prep_state()
        self._auto_cooldown_until = 0.0
        self._auto_perk_cooldown_until = 0.0
        self._auto_in_progress = False
        self._booster_attempt_signature = None
        self._booster_unchanged_ticks = 0
        self._auto_unchanged_after_play_ticks = 0
        self._booster_attempt_started_at = 0.0
        self._auto_last_action_finished_at = 0.0
        self._force_no_booster_next = False
        self._auto_perk_used_this_run = False
        self._auto_turn_owner_latch = None
        # Clearing transient state (replay, new game...) is forward progress:
        # restart the watchdog clock so the post-action wait isn't mistaken for a
        # freeze.
        self._auto_watchdog_last_progress = time.monotonic()
        self._auto_busy_watch_start = None
        self._auto_force_play_next = False
        self._clear_manual_stability_retry()

    def new_game_clicked(self, checked=False):
        # Optional label so the user can name the game; blank -> timestamp only.
        # Parent must be a real QWidget -- this class is the pyuic Ui_MainWindow,
        # not a widget itself, so use the central widget it owns.
        label, ok = QtWidgets.QInputDialog.getText(
            self.centralwidget,
            "Nova partija",
            "Naziv partije (opciono):",
        )
        if not ok:
            return
        try:
            game_dir = runtime.start_new_game_dir(label=label.strip() or None)
        except OSError as exc:
            self.BestMove.setText(f"Nova partija nije kreirana: {exc}")
            return
        # A new game starts clean: clear transient auto/booster state like Reset,
        # and rewind the round counter — a fresh match always starts at round 1.
        self.reset_game_state()
        self.CurrentRoundSpin.setValue(1)
        self.BestMove.setText(f"Nova partija: {game_dir.name}")

    def reset_game_state(self, checked=False):
        self._clear_transient_auto_state()
        runtime.reset_floor_lava_state()
        runtime.reset_bounty_state()
        # Forget the last seen dot count, NOT the round value: Reset is also
        # used mid-match after a stall, where rewinding the round would lie.
        self._last_tracked_remaining_moves = None
        self._booster_charge_maximum = BOOSTER_MAX_CHARGE
        self.BoosterChargeSpin.setMaximum(BOOSTER_MAX_CHARGE)
        self._refresh_booster_state_label()
        if self.AutoButton.isChecked():
            self.AutoButton.setChecked(False)
        else:
            self.auto_timer.stop()
            self.AutoStatus.setText("Auto: OFF")
        self.BestMove.setText("Best Move:")
        self.Score.setText("Score: ")

    def restart_app_clicked(self, checked=False):
        """Exit Qt cleanly and request a same-console process replacement."""
        if self.AutoButton.isChecked():
            self.AutoButton.setChecked(False)
        # Save before leaving the event loop so the replacement process cannot
        # load stale settings. ``main`` performs os.execv only after Qt's
        # aboutToQuit hooks have had a chance to stop the worker threads.
        self.save_gui_state()
        QtWidgets.QApplication.exit(RESTART_APP_EXIT_CODE)

    def best_move_clicked(self, checked=False):
        candidates, depth, beam_width = self.selected_lookahead()
        self.start_check_best_move(
            include_future_value=True,
            action="highest_points",
            display_label="Najbolji potez",
            lookahead_candidates=candidates,
            lookahead_depth=depth,
            lookahead_beam_width=beam_width,
        )

    # Compatibility for older callers/tests that used the original handler
    # name before the top action was renamed to "Najbolji potez".
    def best_points_clicked(self, checked=False):
        self.best_move_clicked(checked)

    def highest_points_clicked(self, checked=False):
        candidates, depth, beam_width = self.selected_lookahead()
        self.start_check_best_move(
            include_future_value=True,
            action="points_only",
            display_label="Najvise poena",
            points_only=True,
            lookahead_candidates=candidates,
            lookahead_depth=depth,
            lookahead_beam_width=beam_width,
        )

    def use_perk_slot_clicked(self, slot_number):
        if slot_number not in (1, 2):
            return False
        detection = self._detected_perk_slots[slot_number - 1]
        if (
            not detection.available
            or detection.perk_key not in runtime.PERK_DEFINITIONS
        ):
            self.BestMove.setText(f"Perk {slot_number}: nije dostupan")
            return False
        candidates, depth, beam_width = self.selected_lookahead()
        return self.start_check_best_move(
            include_future_value=True,
            action=f"manual_perk_{slot_number}",
            display_label=f"Perk {slot_number}",
            forced_perk_slot=slot_number,
            lookahead_candidates=candidates,
            lookahead_depth=depth,
            lookahead_beam_width=beam_width,
        )

    def extra_move_clicked(self, checked=False):
        self.start_check_best_move(
            include_future_value=False,
            action="extra_move",
            display_label="Extra move",
            extra_move_only=True,
        )

    def debug_capture_clicked(self, checked=False):
        candidates, depth, beam_width = self.selected_lookahead()
        self.start_check_best_move(
            include_future_value=True,
            action="debug_capture",
            display_label="Debug slikaj",
            lookahead_candidates=candidates,
            lookahead_depth=depth,
            lookahead_beam_width=beam_width,
            play_enabled=False,
            debug_enabled=True,
        )

    def net_kill_toggled(self, checked):
        """Block or restore BlueStacks' internet, like pulling/replacing the
        cable just for the emulator. ``checked`` = block engaged.

        The ADB command can still pause while BlueStacks responds, so it runs
        on a daemon thread; the result comes back on the GUI thread via
        :meth:`_on_net_toggle_done`.
        """
        want_blocked = checked  # checked = BlueStacks blokiran
        self.NetKillButton.setEnabled(False)
        self.NetKillButton.setText("...")
        self.statusbar.showMessage(
            "Blokiram BlueStacks..." if want_blocked else "Vracam BlueStacks net..."
        )

        def worker():
            ok, msg = net_toggle.block_bluestacks(want_blocked)
            self._net_signals.done.emit(ok, want_blocked, msg)

        threading.Thread(target=worker, daemon=True).start()

    def launch_match_masters_clicked(self, checked=False):
        self.LaunchMatchMastersButton.setEnabled(False)
        self.LaunchMatchMastersButton.setText("Pokrecem...")
        self.statusbar.showMessage("Trazim rootovanu BlueStacks instancu...")

        def worker():
            result = matchmasters_launcher.launch_match_masters(
                start_reader=True,
                progress=self._mm_launch_signals.progress.emit,
            )
            self._mm_launch_signals.done.emit(result)

        threading.Thread(target=worker, daemon=True).start()

    def _on_match_masters_launch_progress(self, message):
        self.statusbar.showMessage(str(message))

    def _on_match_masters_launch_done(self, result):
        self.LaunchMatchMastersButton.setEnabled(True)
        self.LaunchMatchMastersButton.setText("Pokreni Match Masters")
        if getattr(result, "success", False):
            self.statusbar.showMessage(str(result.message), 10000)
        else:
            self.statusbar.showMessage(
                "Pokretanje nije uspelo: " + str(getattr(result, "message", "nepoznato")),
                15000,
            )

    def _on_net_toggle_done(self, success, requested_blocked, message):
        self.NetKillButton.setEnabled(True)
        # On failure nothing changed, so the real state is the previous one.
        blocked_now = requested_blocked if success else (not requested_blocked)
        if not success:
            # Revert the toggle without re-triggering the handler.
            self.NetKillButton.blockSignals(True)
            self.NetKillButton.setChecked(blocked_now)
            self.NetKillButton.blockSignals(False)
        if blocked_now:
            self.NetKillButton.setText("Vrati BS net")
            self.NetKillButton.setToolTip(
                "BlueStacks je BLOKIRAN preko ADB. Klik = vrati mu internet."
            )
        else:
            self.NetKillButton.setText("Blokiraj BS")
            self.NetKillButton.setToolTip(
                "Klik = blokiraj internet samo za BlueStacks "
                "(kao vadjenje kabla za emulator)."
            )
        if success:
            self.statusbar.showMessage(
                "BlueStacks blokiran" if blocked_now else "BlueStacks net vracen", 4000
            )
        else:
            self.statusbar.showMessage(
                "Promena nije uspela: {}".format(message or "nepoznato"), 8000
            )

    def auto_toggled(self, checked):
        self.auto_stability.reset()
        self._auto_cooldown_until = 0.0
        self._auto_perk_cooldown_until = 0.0
        self._booster_attempt_signature = None
        self._booster_unchanged_ticks = 0
        self._auto_unchanged_after_play_ticks = 0
        self._booster_attempt_started_at = 0.0
        self._auto_last_action_finished_at = 0.0
        self._force_no_booster_next = False
        self._auto_perk_used_this_run = False
        self._auto_turn_owner_latch = None
        self._auto_scan_reset_motion = True
        self._auto_scan_failure_count = 0
        # Pressing the button is the user's own "unstick" action: clear the busy
        # flags too, otherwise a previously-stuck _auto_scan_busy/_auto_in_progress
        # would survive an off/on toggle and keep the loop frozen.
        self._auto_in_progress = False
        self._auto_scan_busy = False
        self._auto_prep_busy = False
        self._auto_pending_play = None
        self._auto_watchdog_last_progress = time.monotonic()
        self._auto_busy_watch_start = None
        self._auto_force_play_next = False
        self._auto_unrecognized_block_since = None
        self._auto_wait_status_sticky = False
        self._clear_auto_prep_state()
        if checked:
            self.AutoStatus.setText("Auto: ceka tablu")
            self.auto_timer.start()
        else:
            self.auto_timer.stop()
            self.AutoStatus.setText("Auto: OFF")

    def _build_auto_scan_request(self):
        reset_motion = self._auto_scan_reset_motion
        self._auto_scan_reset_motion = False
        return AutoScanRequest(
            mode=self.ModeBox.currentData() or self.ModeBox.currentText(),
            special_piece_mode=self.selected_special_piece_mode(),
            selected_profile=self.BoardSizeBox.currentData() or DEFAULT_PROFILE,
            board_source=self.BoardSourceBox.currentData() or BOARD_SOURCE_ML,
            ml_recognition_mode=self.MLRecognitionModeBox.currentData() or ML_RECOGNITION_ONLY,
            reset_motion=reset_motion,
            detect_turn_owner=self._auto_turn_gate_enabled(),
            auto_mode_detection=self.AutoModeCheck.isChecked(),
        )

    def scan_board_for_auto(self):
        result = run_auto_scan_request(self._build_auto_scan_request())
        self._apply_mode_detection(
            getattr(result, "mode_detection", None), source="auto scan"
        )
        return result.game_board, result.special_game_board, result.board_image

    def auto_tick(self):
        # Runs every AUTO_SCAN_INTERVAL_MS even while a busy flag blocks the rest
        # of the tick, so the watchdog gets a heartbeat to detect a wedge and
        # recover. Must stay first, before the early-returns below.
        if self._auto_watchdog_recover_if_stuck():
            return

        if self._auto_in_progress:
            return

        if self._check_worker_thread is not None:
            self.AutoStatus.setText("Auto: racunam")
            return

        if self._auto_scan_busy:
            return

        if time.monotonic() < self._auto_cooldown_until:
            self.AutoStatus.setText("Auto: cooldown")
            return

        # Keep a wait diagnostic ("ceka animaciju", "neprepoznata polja"...) on
        # screen across chained scans instead of flashing "skeniram" over it.
        if not self._auto_wait_status_sticky:
            self.AutoStatus.setText("Auto: skeniram")
        self._start_auto_scan_worker(self._build_auto_scan_request())

    def _auto_watchdog_recover_if_stuck(self):
        """Guarantee the auto loop never freezes.

        Returns True only when it performed a hard recovery this tick (the caller
        then skips the rest of the tick). A soft "force the next play" nudge does
        not stop the tick — it lets normal scanning proceed and play sooner.
        """
        if not self.AutoButton.isChecked():
            self._auto_busy_watch_start = None
            return False

        now = time.monotonic()
        if self._auto_watchdog_last_progress == 0.0:
            self._auto_watchdog_last_progress = now

        busy = (
            self._auto_in_progress
            or self._auto_scan_busy
            or self._auto_prep_busy
            or self._check_worker_thread is not None
        )
        if busy:
            if self._auto_busy_watch_start is None:
                self._auto_busy_watch_start = now
            elif now - self._auto_busy_watch_start >= AUTO_WATCHDOG_RESTART_SECONDS:
                # A worker hung or a flag stuck True: nothing will clear it on its
                # own. Rebuild the subsystem so the loop comes back to life.
                self._auto_recover_auto_subsystem("worker/flag zaglavljen")
                return True
            return False

        # Not busy: the loop is alive (scans complete) but may never decide to
        # play (board reads yet never "settles"). Ask the next readable scan to
        # play instead of waiting indefinitely.
        self._auto_busy_watch_start = None
        if now - self._auto_watchdog_last_progress >= AUTO_WATCHDOG_FORCE_PLAY_SECONDS:
            self._auto_force_play_next = True
        return False

    def _auto_recover_auto_subsystem(self, reason):
        self._teardown_auto_scan_worker()
        self._teardown_auto_prep_worker()
        self._teardown_check_best_move_worker()
        self._auto_in_progress = False
        self._auto_scan_busy = False
        self._auto_prep_busy = False
        self._auto_pending_play = None
        self._auto_prep_result = None
        self._auto_cooldown_until = 0.0
        self._auto_scan_failure_count = 0
        self._auto_busy_watch_start = None
        self._auto_force_play_next = False
        self._auto_unrecognized_block_since = None
        self._auto_wait_status_sticky = False
        self._auto_turn_owner_latch = None
        self._auto_scan_reset_motion = True
        self._clear_auto_prep_state()
        self.auto_stability.reset()
        self._auto_watchdog_last_progress = time.monotonic()
        if self.AutoButton.isChecked():
            self.AutoStatus.setText("Auto: watchdog restart")
            QtCore.QTimer.singleShot(0, self.auto_tick)

    def _stop_qthread(self, thread):
        if thread is None:
            return
        try:
            thread.quit()
            if not thread.wait(300):
                # Blocked in a native call (the event loop can't process quit):
                # force it down so a fresh worker can replace it. Abrupt, but only
                # reached after AUTO_WATCHDOG_RESTART_SECONDS of a genuine wedge.
                thread.terminate()
                thread.wait(300)
        except RuntimeError:
            pass

    def _teardown_auto_scan_worker(self):
        thread = self._auto_scan_thread
        self._auto_scan_thread = None
        self._auto_scan_worker = None
        self._stop_qthread(thread)

    def _teardown_auto_prep_worker(self):
        thread = self._auto_prep_thread
        self._auto_prep_thread = None
        self._auto_prep_worker = None
        self._stop_qthread(thread)

    def _teardown_check_best_move_worker(self):
        thread = self._check_worker_thread
        self._check_worker_thread = None
        self._check_worker = None
        self._stop_qthread(thread)
        self.ActiveButton.setEnabled(True)
        self.ExtraMoveButton.setEnabled(True)
        self.HighestPointsButton.setEnabled(True)
        self._update_perk_use_buttons(worker_busy=False)
        self.DebugCaptureButton.setEnabled(True)
        self.NewGameButton.setEnabled(True)

    def _handle_auto_replay_detection(self, detection):
        if not self.AutoReplayCheck.isChecked():
            self.AutoStatus.setText("Auto: replay off")
            return True

        self.AutoStatus.setText("Auto: play again")
        clicked = runtime.click_play_again_button(detection)
        if not clicked:
            self.AutoStatus.setText("Auto: replay failed")
            return True

        self._clear_transient_auto_state()
        self._auto_cooldown_until = (
            time.monotonic() + runtime.AUTO_POST_PLAY_AGAIN_COOLDOWN_SECONDS
        )
        self.BestMove.setText("Auto: PLAY AGAIN")
        self.Score.setText("Score: replay")
        self.AutoStatus.setText("Auto: play again")
        return True

    def _handle_auto_scan_finished(self, result):
        self._auto_scan_busy = False
        self._auto_scan_failure_count = 0
        # Cleared on every fresh result; the wait branch below re-sets it, so the
        # suppression of "Auto: skeniram" never outlives the state it describes.
        self._auto_wait_status_sticky = False
        if not self.AutoButton.isChecked():
            return

        self._apply_mode_detection(
            getattr(result, "mode_detection", None), source="auto scan"
        )
        game_board = result.game_board
        special_game_board = result.special_game_board
        board_image = result.board_image
        self._auto_hot_color_state = copy.deepcopy(
            getattr(result, "hot_color_state", None)
        )
        # Engine charge table travels with every memory scan; keep the latest
        # non-None reading so the move request can hand it to the simulator.
        scan_charge_colors = getattr(result, "memory_charge_colors", None)
        if scan_charge_colors is not None:
            self._auto_memory_charge_colors = tuple(scan_charge_colors)
        # Results from the persistent worker arrive enriched (motion, hash and
        # replay detection already computed off the GUI thread); the legacy
        # path computes them here. Enriched results also drive scan chaining.
        enriched = result.motion_score is not None
        if enriched:
            replay_detection = result.replay_detection
            visual_hash = result.visual_hash
            motion_score = result.motion_score
            core_motion_score = result.core_motion_score
        else:
            replay_detection = runtime.detect_play_again_button(board_image)
            visual_hash = auto_visual_fingerprint(board_image)
            motion_score = auto_motion_score(self.auto_stability.previous_image, board_image)
            core_motion_score = auto_core_motion_score(
                self.auto_stability.previous_image,
                board_image,
                board_size=len(game_board) if game_board else None,
            )
        if replay_detection.active:
            # Only trust a PLAY AGAIN hit when the board is genuinely unreadable
            # (a real end screen recognizes as mostly zeros). A cleanly-read
            # board with a "button" blob is a mid-game false positive — e.g. a
            # froggy lotus in the bottom-center, whose teal zone glow falls in
            # the detector's blue mask — and must not skip the move handling.
            board_unreadable = (
                not game_board
                or runtime.board_zero_count(game_board) >= AUTO_REPLAY_MIN_UNKNOWN_CELLS
            )
            if board_unreadable:
                self._handle_auto_replay_detection(replay_detection)
                return
            if not self._auto_replay_fp_active:
                self._auto_replay_fp_active = True
        else:
            self._auto_replay_fp_active = False

        turn_owner = getattr(result, "turn_owner", None)
        if self._auto_turn_gate_enabled() and turn_owner is not None:
            accepted_turn = (
                getattr(turn_owner, "value", None)
                if getattr(turn_owner, "accepted", False)
                else None
            )
            if accepted_turn in {
                screen_state_reader.TURN_OWNER_US,
                screen_state_reader.TURN_OWNER_OPPONENT,
            }:
                self._auto_turn_owner_latch = accepted_turn
            effective_turn = accepted_turn
            if (
                effective_turn is None
                and getattr(turn_owner, "source", None)
                == screen_state_reader.TURN_BANNER_SOURCE_DRAINED
            ):
                # The banner is on screen with its timer run down, so the turn
                # did not change hands - it is still whoever the last readable
                # banner named.
                effective_turn = self._auto_turn_owner_latch
            opponent_turn = bool(
                effective_turn == screen_state_reader.TURN_OWNER_OPPONENT
            )
            if opponent_turn:
                # Only a currently visible and accepted opponent banner is a
                # hard wait. An absent/ambiguous banner is not evidence that the
                # opponent is playing, so keep scanning and try the stable board
                # instead of deadlocking on "cekam oznaku poteza".
                self.auto_stability.reset()
                self._clear_auto_prep_state()
                self._auto_force_play_next = False
                self._auto_unchanged_after_play_ticks = 0
                self._auto_watchdog_last_progress = time.monotonic()
                self.AutoStatus.setText("Auto: protivnikov potez")
                self._auto_wait_status_sticky = True
                if enriched:
                    self._schedule_chained_auto_scan()
                return

        board_has_match = runtime.auto_board_has_unresolved_match(
            game_board,
            special_game_board,
            allow_square_matches=self.SquareMatchesCheck.isChecked(),
        )
        should_play = self.auto_stability.observe(
            game_board,
            special_game_board,
            visual_hash=visual_hash,
            motion_score=motion_score,
            core_motion_score=core_motion_score,
            board_has_match=board_has_match,
            # Persistent live-worker results are enriched and use the real
            # monotonic clock. The legacy direct-call path is retained for
            # deterministic unit tests and old integrations.
            observed_at=time.monotonic() if enriched else None,
            # A memory-sourced board is the engine's own model: exact, and
            # settled the moment it is full and match-free. The pixel-based
            # scan-count/motion/wall-clock gates only guard ML misreads, so
            # the observe fast-path skips them for this scan.
            authoritative=(
                getattr(result, "board_source", None)
                == board_source.BOARD_SOURCE_MEMORY
            ),
            # Engine GameState gate: only swipe while the engine reports
            # MovePlaying, i.e. it is actually accepting input.
            engine_move_ready=getattr(result, "memory_move_ready", None),
        )
        if not enriched and board_image is not None:
            self.auto_stability.previous_image = board_image.copy()
        unknown_cells = [
            (row, col)
            for row, row_values in enumerate(game_board or [])
            for col, value in enumerate(row_values)
            if value == 0
        ]
        if not unknown_cells:
            self._auto_unrecognized_block_since = None
        elif self._auto_unrecognized_block_since is None:
            self._auto_unrecognized_block_since = time.monotonic()

        replay_same_board_signature = None
        if not should_play and self._auto_force_play_next and game_board:
            forced = None
            if not unknown_cells:
                # Watchdog soft recovery: the board reads cleanly but the
                # stability gate never released. Play it now (replay the current
                # signature) so the loop keeps moving; an invalid early swipe is
                # harmless.
                forced = (game_board, special_game_board)
            elif (
                len(unknown_cells) <= AUTO_FORCE_PLAY_MAX_UNKNOWN_CELLS
                and time.monotonic() - self._auto_unrecognized_block_since
                >= AUTO_FORCE_PLAY_UNKNOWN_GRACE_SECONDS
            ):
                # Escalation: every scan keeps returning unrecognized cells
                # (npr. animacija stalno prekriva polje), so the clean-board
                # path above can never fire. Treat the unknown cells as BLOCKED
                # (moves touching them are excluded) and play on the rest.
                forced = (
                    [
                        [BLOCKED if value == 0 else value for value in row_values]
                        for row_values in game_board
                    ],
                    [
                        [
                            0 if game_board[row][col] == 0 else special_value
                            for col, special_value in enumerate(row_values)
                        ]
                        for row, row_values in enumerate(special_game_board)
                    ],
                )
            if forced is not None:
                game_board, special_game_board = forced
                forced_signature = runtime.auto_settled_board_signature(
                    game_board, special_game_board
                )
                self.auto_stability.waiting_for_change = False
                self.auto_stability.played_signature = None
                self.auto_stability.last_signature = forced_signature
                self.auto_stability.stable_count = self.auto_stability.required_scans
                replay_same_board_signature = forced_signature
                self._auto_force_play_next = False
                should_play = True
        if not should_play:
            booster_attempt_still_same = False
            if (
                self._booster_attempt_signature is not None
                and self.auto_stability.played_signature == self._booster_attempt_signature
                and self.auto_stability.wait_reason in {"change", "motion", "visual"}
            ):
                current_signature = runtime.auto_settled_board_signature(
                    game_board,
                    special_game_board,
                )
                booster_attempt_still_same = (
                    current_signature == self._booster_attempt_signature
                )

            if booster_attempt_still_same:
                self._booster_unchanged_ticks += 1
                booster_wait_seconds = max(
                    0.0, time.monotonic() - self._booster_attempt_started_at
                )
                if (
                    self._booster_unchanged_ticks >= AUTO_BOOSTER_STUCK_TICK_THRESHOLD
                    and (
                        self._booster_attempt_started_at <= 0.0
                        or booster_wait_seconds + 1e-9
                        >= runtime.AUTO_BOOSTER_STUCK_MIN_SECONDS
                    )
                ):
                    replay_same_board_signature = self.auto_stability.played_signature
                    self._booster_attempt_signature = None
                    self._booster_unchanged_ticks = 0
                    self._booster_attempt_started_at = 0.0
                    self._force_no_booster_next = True
                    self.auto_stability.waiting_for_change = False
                    self.auto_stability.played_signature = None
                    self.auto_stability.last_signature = replay_same_board_signature
                    self.auto_stability.stable_count = self.auto_stability.required_scans
                    self._auto_unchanged_after_play_ticks = 0
                    should_play = True

            if (
                not should_play
                and not booster_attempt_still_same
                and self.auto_stability.wait_reason == "change"
            ):
                self._auto_unchanged_after_play_ticks += 1
                if (
                    self._auto_unchanged_after_play_ticks
                    >= AUTO_UNCHANGED_BOARD_REPLAY_TICK_THRESHOLD
                    and (
                        self._auto_last_action_finished_at <= 0.0
                        or time.monotonic() - self._auto_last_action_finished_at + 1e-9
                        >= runtime.AUTO_UNCHANGED_BOARD_REPLAY_MIN_SECONDS
                    )
                ):
                    replay_same_board_signature = self.auto_stability.played_signature
                    self.auto_stability.waiting_for_change = False
                    self.auto_stability.played_signature = None
                    self.auto_stability.last_signature = replay_same_board_signature
                    self.auto_stability.stable_count = self.auto_stability.required_scans
                    self._auto_unchanged_after_play_ticks = 0
                    should_play = True
            elif not should_play:
                self._auto_unchanged_after_play_ticks = 0

            if not should_play and self.auto_stability.wait_reason == "unrecognized":
                self.AutoStatus.setText(
                    f"Auto: neprepoznata polja ({len(unknown_cells)})"
                )
            elif not should_play and self.auto_stability.wait_reason == "match_pending":
                self.AutoStatus.setText("Auto: ceka kaskadu")
            elif not should_play and self.auto_stability.wait_reason == "engine_busy":
                self.AutoStatus.setText("Auto: engine obradjuje potez")
            elif not should_play and self.auto_stability.wait_reason == "memory_confirm":
                self.AutoStatus.setText("Auto: potvrda memorije")
            elif not should_play and self.auto_stability.wait_reason in {"motion", "visual"}:
                self.AutoStatus.setText("Auto: ceka animaciju")
            elif not should_play and self.auto_stability.waiting_for_change:
                self.AutoStatus.setText("Auto: ceka promenu")
            elif not should_play:
                stable_ms = int(round(self.auto_stability.observed_stable_seconds * 1000))
                required_ms = int(round(self.auto_stability.min_stable_seconds * 1000))
                self.AutoStatus.setText(f"Auto: stabilizuje {stable_ms}/{required_ms} ms")
            if not should_play:
                self._auto_wait_status_sticky = True
                # Live diagnostic (Debug mode only) so the blocking gate is
                # visible while tuning: m=full motion, c=core motion (sparkle-
                # filtered), h=visual hash distance, z=unrecognized cells,
                # r=consecutive identical-signature scans.
                if self.DebugModeCheck.isChecked():
                    hash_distance = self.auto_stability.last_hash_distance
                    self.AutoStatus.setText(
                        self.AutoStatus.text()
                        + f"  [m{motion_score:.1f} c{core_motion_score:.1f}"
                        + f" h{hash_distance if hash_distance is not None else '-'}"
                        + f" z{runtime.board_zero_count(game_board)}"
                        + f" r{self.auto_stability.observed_repeat_count}]"
                    )
                if enriched:
                    # Start the expensive two-frame Auto-state/perk prep on the
                    # first clean, match-free board, even while harmless visual
                    # motion needs another scan. Its cost is then hidden under
                    # the existing board-settle wait instead of delaying play.
                    if not unknown_cells and board_has_match is False:
                        self._maybe_start_auto_prep(allow_visual_tail=True)
                    self._schedule_chained_auto_scan()
                return

        self._auto_unchanged_after_play_ticks = 0
        signature = replay_same_board_signature or self.auto_stability.last_signature
        self._start_auto_play(game_board, special_game_board, signature)

    def _schedule_chained_auto_scan(self):
        # Skip the up-to-25ms wait for the next auto_timer tick: queue the next
        # scan as soon as the event loop drains. The timer keeps running as the
        # fallback that revives the loop after cooldowns and worker handoffs.
        QtCore.QTimer.singleShot(0, self.auto_tick)

    def _start_auto_play(self, game_board, special_game_board, signature):
        prep = self._take_fresh_auto_prep()
        require_stable_prep = self.AutoStateCheck.isChecked()
        if prep is None and (self._auto_prep_busy or require_stable_prep):
            # Auto State may never fall through to the one-frame synchronous
            # reader. Keep the stable board pending until the state prep is
            # confirmed; with Cekaj anim. that means two matching clear reads of
            # booster, moves and round. Score remains best-effort only.
            self._auto_pending_play = (game_board, special_game_board, signature)
            self._auto_in_progress = True
            self.AutoStatus.setText("Auto: pripremam")
            if not self._auto_prep_busy:
                self._ensure_auto_prep_worker()
                self._auto_prep_busy = True
                self._auto_prep_worker.requested.emit(self._build_auto_prep_request())
            return
        self._launch_auto_check(game_board, special_game_board, signature, prep)

    def _launch_auto_check(self, game_board, special_game_board, signature, prep):
        self.AutoStatus.setText("Auto: igra")
        # Launching a play is the definition of forward progress: reset the
        # watchdog clock and drop any pending force-play request.
        self._auto_watchdog_last_progress = time.monotonic()
        self._auto_force_play_next = False
        self._auto_in_progress = True
        candidates, depth, beam_width = self.selected_lookahead()
        kwargs = dict(
            include_future_value=True,
            action="auto_highest_points",
            display_label="Auto",
            pre_scanned_board=game_board,
            pre_scanned_special_board=special_game_board,
            pre_scanned_board_path=AUTO_LATEST_BOARD_FILENAME,
            lookahead_candidates=candidates,
            lookahead_depth=depth,
            lookahead_beam_width=beam_width,
            auto_signature=signature,
        )
        if prep is not None:
            kwargs["auto_prep"] = prep
        started = self.start_check_best_move(**kwargs)
        if not started:
            self._auto_in_progress = False

    def _take_fresh_auto_prep(self):
        prep = self._auto_prep_result
        self._auto_prep_result = None
        if prep is None:
            return None
        if not self._auto_prep_is_usable_now(prep):
            return None
        if time.monotonic() - prep.created_at > AUTO_PREP_MAX_AGE_SECONDS:
            return None
        return prep

    def _auto_prep_is_usable_now(self, prep):
        stable_state_required = bool(
            self.AutoStateCheck.isChecked()
            and self.ManualRecognitionStabilityCheck.isChecked()
        )
        return bool(
            prep is not None
            and prep.auto_state_enabled == self.AutoStateCheck.isChecked()
            and _auto_prep_has_confirmed_score(prep)
            and bool(getattr(prep, "stable_state_required", False))
            == stable_state_required
            and (
                not stable_state_required
                or bool(getattr(prep, "state_stable", False))
            )
        )

    def _maybe_start_auto_prep(self, *, allow_visual_tail=False):
        stability = self.auto_stability
        allowed_reasons = {"stable"}
        if allow_visual_tail:
            allowed_reasons.update({"motion", "visual"})
        if stability.wait_reason not in allowed_reasons:
            return
        if (
            stability.wait_reason == "stable"
            and stability.stable_count < max(1, stability.base_required_scans - 1)
        ):
            return
        if self._auto_prep_busy:
            return
        prep = self._auto_prep_result
        if (
            prep is not None
            and self._auto_prep_is_usable_now(prep)
            and time.monotonic() - prep.created_at <= AUTO_PREP_MAX_AGE_SECONDS
        ):
            return
        self._auto_prep_result = None
        self._ensure_auto_prep_worker()
        self._auto_prep_busy = True
        self._auto_prep_worker.requested.emit(self._build_auto_prep_request())

    def _build_auto_prep_request(self):
        total_rounds, _current_round = self.selected_rounds()
        return AutoPrepRequest(
            auto_state_enabled=self.AutoStateCheck.isChecked(),
            board_profile=self.BoardSizeBox.currentData() or DEFAULT_PROFILE,
            special_piece_mode=self.selected_special_piece_mode(),
            manual_booster_charge=self.selected_booster_charge(),
            manual_remaining_moves=self.selected_remaining_moves(),
            showdown=self.ShowdownCheck.isChecked(),
            party=self.PartyCheck.isChecked(),
            total_rounds=total_rounds,
            require_stable_state=bool(
                self.AutoStateCheck.isChecked()
                and self.ManualRecognitionStabilityCheck.isChecked()
            ),
            solo_challenge=self.SoloChallengeCheck.isChecked(),
            auto_round_detection=bool(
                self._rounds_tracking_active()
                and self.AutoRoundCheck.isChecked()
            ),
            infinite_moves=self._infinite_moves_selected(),
        )

    def _ensure_auto_prep_worker(self):
        if self._auto_prep_thread is not None:
            return
        thread = QtCore.QThread()
        worker = AutoPrepWorker()
        worker.moveToThread(thread)
        worker.finished.connect(self._handle_auto_prep_finished)
        worker.failed.connect(self._handle_auto_prep_failed)
        thread.start()
        app = QtCore.QCoreApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(thread.quit)
        self._auto_prep_thread = thread
        self._auto_prep_worker = worker

    def _handle_auto_prep_finished(self, prep):
        self._auto_prep_busy = False
        pending = self._auto_pending_play
        if not self._auto_prep_is_usable_now(prep):
            self._auto_prep_result = None
            if (
                self.AutoStateCheck.isChecked()
                and self.ManualRecognitionStabilityCheck.isChecked()
                and getattr(prep, "stable_state_required", False)
            ):
                reason = getattr(prep, "state_reason", "")
                self.AutoStatus.setText(
                    "Auto: ceka animaciju stanja"
                    + (f" ({reason})" if reason else "")
                )
            else:
                self.AutoStatus.setText("Auto: ceka stanje")
            if pending is not None and self.AutoButton.isChecked():
                # Keep the already-confirmed board pending and retry the state
                # capture without weakening the separate board-stability gate.
                self._auto_prep_busy = True
                self._auto_prep_worker.requested.emit(self._build_auto_prep_request())
            elif pending is not None:
                self._auto_pending_play = None
                self._auto_in_progress = False
            return
        # The finished signal is delivered on the GUI thread.  Reflect the
        # accepted read immediately instead of keeping Stanje visually one prep
        # behind until a move request happens to consume it.  Round advancement
        # remains tied to actual request consumption below.
        self._apply_auto_state_controls(prep.auto_read, track_round=False)
        self._auto_prep_result = prep
        if pending is None:
            return
        self._auto_pending_play = None
        if not self.AutoButton.isChecked():
            self._auto_in_progress = False
            return
        game_board, special_game_board, signature = pending
        confirmed_prep = self._take_fresh_auto_prep()
        if confirmed_prep is None and self.AutoStateCheck.isChecked():
            self._start_auto_play(game_board, special_game_board, signature)
            return
        self._launch_auto_check(game_board, special_game_board, signature, confirmed_prep)

    def _retry_pending_auto_prep(self):
        if self._auto_pending_play is None:
            return
        if not self.AutoButton.isChecked():
            self._auto_pending_play = None
            self._auto_in_progress = False
            return
        if self._auto_prep_busy:
            return
        self._ensure_auto_prep_worker()
        self._auto_prep_busy = True
        self.AutoStatus.setText("Auto: ponavljam stanje")
        self._auto_prep_worker.requested.emit(self._build_auto_prep_request())

    def _handle_auto_prep_failed(self, exc):
        self._auto_prep_busy = False
        self._auto_prep_result = None
        pending = self._auto_pending_play
        if pending is None:
            return
        if not self.AutoButton.isChecked():
            self._auto_pending_play = None
            self._auto_in_progress = False
            return
        self.AutoStatus.setText("Auto: prep greska, ponavljam")
        QtCore.QTimer.singleShot(
            AUTO_SCAN_FAILURE_RETRY_DELAY_MS,
            self._retry_pending_auto_prep,
        )

    def _handle_auto_scan_failed(self, exc):
        self._auto_scan_busy = False
        self._auto_wait_status_sticky = False
        self._auto_in_progress = False
        self._auto_scan_failure_count += 1
        if (
            self._auto_scan_failure_count < AUTO_SCAN_FAILURE_LIMIT
            and self.AutoButton.isChecked()
        ):
            self.AutoStatus.setText(
                "Auto: scan greska "
                f"{self._auto_scan_failure_count}/{AUTO_SCAN_FAILURE_LIMIT}, ponavljam"
            )
            QtCore.QTimer.singleShot(AUTO_SCAN_FAILURE_RETRY_DELAY_MS, self.auto_tick)
            return
        self._auto_scan_failure_count = 0
        self.AutoButton.setChecked(False)
        self.AutoStatus.setText("Auto: ERROR")

    def _ensure_auto_scan_worker(self):
        if self._auto_scan_thread is not None:
            return
        thread = QtCore.QThread()
        worker = AutoScanWorker()
        worker.moveToThread(thread)
        worker.finished.connect(self._handle_auto_scan_finished)
        worker.failed.connect(self._handle_auto_scan_failed)
        thread.start()
        app = QtCore.QCoreApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(thread.quit)
        self._auto_scan_thread = thread
        self._auto_scan_worker = worker

    def _start_auto_scan_worker(self, request):
        if self._auto_scan_busy:
            return False
        if self._check_worker_thread is not None:
            return False

        self._ensure_auto_scan_worker()
        self._auto_scan_busy = True
        self._auto_scan_worker.requested.emit(request)
        return True

    def _build_check_best_move_request(
        self,
        include_future_value=False,
        action="highest_points",
        display_label="Najvise poena",
        extra_move_only=False,
        points_only=False,
        forced_perk_slot=None,
        pre_scanned_board=None,
        pre_scanned_special_board=None,
        pre_scanned_board_path=None,
        lookahead_candidates=None,
        lookahead_depth=2,
        lookahead_beam_width=LIVE_LOOKAHEAD_BEAM_WIDTH,
        auto_signature=None,
        play_enabled=True,
        debug_enabled=None,
        auto_prep=None,
    ):
        if (pre_scanned_board is None) != (pre_scanned_special_board is None):
            raise ValueError("pre_scanned_board and pre_scanned_special_board must be provided together")
        selected_profile = self.BoardSizeBox.currentData() or DEFAULT_PROFILE
        profile_applied_for_request = False
        if not self.AutoStateCheck.isChecked():
            recognition.apply_board_profile(selected_profile)
            profile_applied_for_request = True
        cursor_position = pyautogui.position()
        if (
            auto_prep is not None
            and auto_prep.auto_state_enabled == self.AutoStateCheck.isChecked()
        ):
            booster_charge, remaining_moves, screen_state_read, screen_state_image = (
                self._state_values_from_prep(auto_prep)
            )
        else:
            booster_charge, remaining_moves, screen_state_read, screen_state_image = (
                self._state_values_for_request()
            )
            profile_applied_for_request = True
        # Read the legend before score_rally_values() below picks the inputs up,
        # so this move already scores with the values now on screen.
        self.refresh_score_legend_values(screen_state_image)
        total_rounds, current_round = self.selected_rounds()
        mode = normalize_game_mode(self.ModeBox.currentData() or self.ModeBox.currentText())
        if mode is GameMode.INFINITE_MOVES:
            remaining_moves = None
            total_rounds = None
            current_round = None
        if auto_prep is not None:
            detected_perk_slots = self._apply_prep_perk_slots(auto_prep)
        else:
            # The request path normally applied the profile above (or while
            # reading automatic screen state). Avoid loading templates twice;
            # the standalone Refresh button still re-resolves after a resize.
            self._skip_next_perk_profile_refresh = profile_applied_for_request
            try:
                detected_perk_slots = self.refresh_detected_perks()
            finally:
                self._skip_next_perk_profile_refresh = False
        request_debug_enabled = (
            self.DebugModeCheck.isChecked()
            if debug_enabled is None
            else bool(debug_enabled)
        )
        activate_booster_immediately = self.BoosterImmediateCheck.isChecked()
        return CheckBestMoveRequest(
            mode=mode,
            special_piece_mode=self.selected_special_piece_mode(),
            selected_profile=selected_profile,
            allow_square_matches=self.SquareMatchesCheck.isChecked(),
            specials_explode_immediately=self.SpecialExplodeCheck.isChecked(),
            score_rally_values=self.score_rally_values(),
            selected_perks=self.selected_perks_for_request(forced_perk_slot),
            detected_perk_slots=tuple(detected_perk_slots),
            cursor_return_position=(cursor_position[0], cursor_position[1]),
            booster_charge=booster_charge,
            booster_maximum=runtime.resolved_booster_maximum(
                (
                    self._booster_charge_maximum
                    if screen_state_read is not None
                    else BOOSTER_MAX_CHARGE
                ),
                screen_state_read,
            ),
            remaining_moves=remaining_moves,
            total_rounds=total_rounds,
            current_round=current_round,
            round_source=(
                "infinite_moves"
                if mode is GameMode.INFINITE_MOVES
                else (
                    "auto_round_tracking"
                    if self.AutoRoundCheck.isChecked() and self.AutoStateCheck.isChecked()
                    else "manual"
                )
            ),
            strategy_mode=self.selected_strategy_mode(),
            include_future_value=include_future_value,
            action=action,
            display_label=display_label,
            extra_move_only=extra_move_only,
            points_only=points_only,
            forced_perk_slot=forced_perk_slot,
            pre_scanned_board=copy.deepcopy(pre_scanned_board) if pre_scanned_board is not None else None,
            pre_scanned_special_board=(
                copy.deepcopy(pre_scanned_special_board)
                if pre_scanned_special_board is not None
                else None
            ),
            pre_scanned_board_path=pre_scanned_board_path,
            lookahead_candidates=lookahead_candidates,
            lookahead_depth=lookahead_depth,
            lookahead_beam_width=lookahead_beam_width,
            auto_signature=auto_signature,
            debug_enabled=request_debug_enabled,
            board_source=self.BoardSourceBox.currentData() or BOARD_SOURCE_ML,
            ml_recognition_mode=self.MLRecognitionModeBox.currentData() or ML_RECOGNITION_ONLY,
            manual_recognition_stability_enabled=self.ManualRecognitionStabilityCheck.isChecked(),
            booster_action_mode=self.selected_booster_action_mode(),
            activate_booster_immediately=activate_booster_immediately,
            showdown_booster_rush=self.ShowdownBoosterRushCheck.isChecked(),
            color_crush=self.ColorCrushCheck.isChecked(),
            energized_colors=self.selected_energized_colors(),
            # Engine's own charge table from the last memory scan; None keeps
            # the blue-charges default when the reader cannot say.
            engine_charge_colors=getattr(self, "_auto_memory_charge_colors", None),
            mushroom_multipliers=self.MushroomMultiplierCheck.isChecked(),
            vertical_matches_destroy_color=(
                self.VerticalMatchesDestroyColorCheck.isChecked()
            ),
            screen_state_read=screen_state_read,
            screen_state_image=screen_state_image,
            force_no_booster=self._force_no_booster_next,
            hot_color_state=(
                copy.deepcopy(getattr(self, "_auto_hot_color_state", None))
                if pre_scanned_board is not None
                else None
            ),
            allow_perk_activation=not (
                auto_signature is not None
                and time.monotonic() < self._auto_perk_cooldown_until
            ),
            play_enabled=play_enabled,
        )

    def _auto_request_hits_opponent_turn(self, request):
        """Drop an auto play whose own state read shows the opponent banner.

        The scan gate gets its banner from an earlier screenshot, so a turn that
        changed hands between scanning and playing slipped straight through and
        the drag went out during the opponent's move (Debug 2026-08-13 replayed
        (5,2)->(6,2) twice against a solid pink banner, board unchanged).
        """

        if not bool(getattr(request, "play_enabled", True)):
            return False
        if getattr(request, "auto_signature", None) is None:
            return False
        if not self._auto_turn_gate_enabled():
            return False
        screen_state_read = getattr(request, "screen_state_read", None)
        turn_owner = getattr(screen_state_read, "turn_owner", None)
        if turn_owner is None or not getattr(turn_owner, "accepted", False):
            return False
        if turn_owner.value != screen_state_reader.TURN_OWNER_OPPONENT:
            return False
        self._auto_turn_owner_latch = screen_state_reader.TURN_OWNER_OPPONENT
        self.auto_stability.reset()
        self._clear_auto_prep_state()
        self._auto_force_play_next = False
        self._auto_watchdog_last_progress = time.monotonic()
        self.AutoStatus.setText("Auto: protivnikov potez")
        self._auto_wait_status_sticky = True
        return True

    def start_check_best_move(self, **kwargs):
        request = self._build_check_best_move_request(**kwargs)
        if self._auto_request_hits_opponent_turn(request):
            return False
        started = self._start_check_best_move_worker(request)
        if started:
            self._remember_manual_stability_retry(request, kwargs)
        return started

    def _start_check_best_move_worker(self, request):
        if self._check_worker_thread is not None:
            return False

        self.ActiveButton.setEnabled(False)
        self.ExtraMoveButton.setEnabled(False)
        self.HighestPointsButton.setEnabled(False)
        self._update_perk_use_buttons(worker_busy=True)
        self.DebugCaptureButton.setEnabled(False)
        self.NewGameButton.setEnabled(False)
        status_text = (
            "slikam debug"
            if not request.play_enabled
            else (
                "skeniram tablu"
                if request.manual_recognition_stability_enabled and request.pre_scanned_board is None
                else "racunam"
            )
        )
        self.BestMove.setText(f"{request.display_label}: {status_text}")
        thread = QtCore.QThread()
        worker = CheckBestMoveWorker(request)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._handle_check_best_move_finished)
        worker.failed.connect(self._handle_check_best_move_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._schedule_check_best_move_cleanup)
        self._check_worker_thread = thread
        self._check_worker = worker
        thread.start()
        return True

    def _schedule_check_best_move_cleanup(self):
        QtCore.QTimer.singleShot(0, self._clear_check_best_move_worker)

    def _clear_check_best_move_worker(self):
        self._check_worker_thread = None
        self._check_worker = None
        self.ActiveButton.setEnabled(True)
        self.ExtraMoveButton.setEnabled(True)
        self.HighestPointsButton.setEnabled(True)
        self._update_perk_use_buttons(worker_busy=False)
        self.DebugCaptureButton.setEnabled(True)
        self.NewGameButton.setEnabled(True)
        # A manual stability retry is deliberately armed only after the old
        # QThread has emitted finished and its worker teardown is out of the
        # result callback. This prevents the cross-thread Qt/GIL lock inversion
        # that used to freeze the whole window at "skeniram tablu".
        self._arm_manual_stability_retry_if_idle()

    def _apply_check_best_move_result(self, result):
        self.BestMove.setText(result.best_move_text)
        self.Score.setText(result.score_text)
        if result.clear_used_perk_slot is not None:
            self.refresh_detected_perks()
        elif result.clear_used_perk_key is not None:
            self.refresh_detected_perks()

    def _remember_manual_stability_retry(self, request, kwargs):
        if (
            request.manual_recognition_stability_enabled
            and request.pre_scanned_board is None
            and request.auto_signature is None
            and not str(request.action).startswith("auto_")
        ):
            if self._manual_stability_retry_kwargs is None:
                self._manual_stability_retry_count = 0
            self._manual_stability_retry_kwargs = copy.deepcopy(kwargs)
            self._manual_stability_retry_label = request.display_label
            self._manual_stability_retry_pending = False
        else:
            self._clear_manual_stability_retry()

    def _clear_manual_stability_retry(self):
        timer = getattr(self, "_manual_stability_retry_timer", None)
        if timer is not None and timer.isActive():
            timer.stop()
        self._manual_stability_retry_kwargs = None
        self._manual_stability_retry_label = None
        self._manual_stability_retry_pending = False
        self._manual_stability_retry_count = 0

    def _arm_manual_stability_retry_if_idle(self):
        if (
            self._manual_stability_retry_kwargs is None
            or not self._manual_stability_retry_pending
            or self._check_worker_thread is not None
        ):
            return False
        if not self._manual_stability_retry_timer.isActive():
            self._manual_stability_retry_timer.start(
                MANUAL_RECOGNITION_RETRY_INTERVAL_MS
            )
        return True

    def _schedule_manual_stability_retry(self):
        if self._manual_stability_retry_kwargs is None:
            return False
        if self._manual_stability_retry_pending:
            return True

        label = self._manual_stability_retry_label or "Najvise poena"
        if self._manual_stability_retry_count >= MANUAL_RECOGNITION_MAX_RETRIES:
            waiting_for_state = self.BestMove.text().endswith(": cekam stanje")
            self._clear_manual_stability_retry()
            if waiting_for_state:
                self.BestMove.setText(f"{label}: stanje nije sigurno vidljivo")
            else:
                self.BestMove.setText(f"{label}: tabla nije prepoznata")
            self.Score.setText("Score: 0")
            return False

        self._manual_stability_retry_count += 1
        self._manual_stability_retry_pending = True
        self.BestMove.setText(f"{label}: skeniram tablu")
        # While the result callback is running, the old worker may still be in
        # QObject destruction on its QThread. Merely remember the retry here;
        # _clear_check_best_move_worker arms the persistent timer after teardown.
        self._arm_manual_stability_retry_if_idle()
        return True

    def _retry_manual_stability_check(self):
        if self._manual_stability_retry_kwargs is None:
            self._manual_stability_retry_pending = False
            return
        if not self.ManualRecognitionStabilityCheck.isChecked():
            self._clear_manual_stability_retry()
            return
        if self._check_worker_thread is not None:
            # Keep the request pending. Worker cleanup will arm the timer again
            # once starting another QThread is safe.
            return

        retry_kwargs = copy.deepcopy(self._manual_stability_retry_kwargs)
        self._manual_stability_retry_pending = False
        self.start_check_best_move(**retry_kwargs)

    def _handle_check_best_move_finished(self, result):
        self._apply_check_best_move_result(result)
        verified_perk = bool(
            result.clear_used_perk_slot is not None
            or result.clear_used_perk_key is not None
        )
        if result.waiting_for_board and not verified_perk:
            self._schedule_manual_stability_retry()
            if result.auto_signature is not None or self._auto_in_progress:
                self._auto_in_progress = False
                if self.AutoButton.isChecked():
                    self.AutoStatus.setText("Auto: skeniram")
            return

        self._clear_manual_stability_retry()
        if result.auto_signature is not None:
            perk_attempt = verified_perk
            now = time.monotonic()
            self._auto_last_action_finished_at = now
            if perk_attempt:
                self._auto_perk_used_this_run = True
                self._auto_perk_cooldown_until = (
                    now + AUTO_POST_PERK_COOLDOWN_SECONDS
                )
            self.auto_stability.mark_played(result.auto_signature)
            if result.turn_consumed:
                # A swipe can hand the turn to the opponent. Even an extra move
                # must visibly confirm the next blue banner before another
                # action is authorized.
                self._auto_turn_owner_latch = None
            # Shuffle, board-changing perks and ordinary booster activation do
            # not spend the move. Keep the confirmed-us latch so an ambiguous
            # post-animation frame cannot deadlock Auto waiting for a new turn
            # banner that the game will not show mid-turn.
            # The move changes the board, the booster charge and possibly the
            # perk slots — any speculative prep captured before it is stale.
            self._clear_auto_prep_state()
            if result.booster_attempt:
                cooldown_seconds = AUTO_POST_BOOSTER_COOLDOWN_SECONDS
                self._booster_attempt_signature = result.auto_signature
                self._booster_unchanged_ticks = 0
                self._auto_unchanged_after_play_ticks = 0
                self._booster_attempt_started_at = now
            elif perk_attempt:
                # The verified executor already waited until the perk effect was
                # visible. Keep only the short *next perk* lock above; do not
                # stall ordinary Auto scans/moves after throwing this perk.
                cooldown_seconds = runtime.AUTO_POST_PERK_MOVE_COOLDOWN_SECONDS
                self._booster_attempt_signature = None
                self._booster_unchanged_ticks = 0
                self._auto_unchanged_after_play_ticks = 0
                self._booster_attempt_started_at = 0.0
                self._force_no_booster_next = False
            else:
                # Read live from runtime so the GUI tuning panel's value
                # takes effect on the next move — the from-import copy at
                # gui.py top is bound at import time and ignores updates.
                cooldown_seconds = runtime.AUTO_POST_MOVE_COOLDOWN_SECONDS
                self._booster_attempt_signature = None
                self._booster_unchanged_ticks = 0
                self._auto_unchanged_after_play_ticks = 0
                self._booster_attempt_started_at = 0.0
                self._force_no_booster_next = False
            self._auto_cooldown_until = now + cooldown_seconds
            self._auto_in_progress = False
            if self.AutoButton.isChecked():
                self.AutoStatus.setText(
                    "Auto: cooldown" if cooldown_seconds > 0 else "Auto: skeniram"
                )

    def _handle_check_best_move_failed(self, exc):
        if self._auto_in_progress:
            self._auto_in_progress = False
            self.AutoButton.setChecked(False)
            self.AutoStatus.setText("Auto: ERROR")
            return
        self._clear_manual_stability_retry()
        self.BestMove.setText("Best Move: error")
        self.Score.setText("Score: 0")

    def check_best_move(
        self,
        include_future_value=False,
        action="highest_points",
        display_label="Najvise poena",
        extra_move_only=False,
        pre_scanned_board=None,
        pre_scanned_special_board=None,
        pre_scanned_board_path=None,
        lookahead_candidates=None,
        lookahead_depth=2,
        lookahead_beam_width=LIVE_LOOKAHEAD_BEAM_WIDTH,
        auto_signature=None,
        play_enabled=True,
        debug_enabled=None,
    ):
        request = self._build_check_best_move_request(
            include_future_value=include_future_value,
            action=action,
            display_label=display_label,
            extra_move_only=extra_move_only,
            pre_scanned_board=pre_scanned_board,
            pre_scanned_special_board=pre_scanned_special_board,
            pre_scanned_board_path=pre_scanned_board_path,
            lookahead_candidates=lookahead_candidates,
            lookahead_depth=lookahead_depth,
            lookahead_beam_width=lookahead_beam_width,
            auto_signature=auto_signature,
            play_enabled=play_enabled,
            debug_enabled=debug_enabled,
        )
        result = run_check_best_move_request(request)
        self._apply_check_best_move_result(result)
        return result


def _bring_window_to_front(window):
    """Make sure the window starts restored and focused.

    Launched from a desktop shortcut (pythonw.exe) Windows often leaves the
    fresh window behind the shell, so ask for the foreground explicitly.
    """
    window.setWindowState(
        (window.windowState() & ~QtCore.Qt.WindowMinimized) | QtCore.Qt.WindowActive
    )
    window.raise_()
    window.activateWindow()
    if sys.platform == "win32":
        try:
            import ctypes

            hwnd = int(window.winId())
            ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            ctypes.windll.user32.SetForegroundWindow(hwnd)
        except Exception:
            pass


def main():
    runtime.initialize_runtime()
    app = QtWidgets.QApplication(sys.argv)
    MainWindow = QtWidgets.QMainWindow()
    ui = Ui_MainWindow()
    ui.setupUi(MainWindow)
    ui.load_gui_state()
    app.aboutToQuit.connect(ui.save_gui_state)
    MainWindow.show()
    _bring_window_to_front(MainWindow)
    exit_code = app.exec_()
    if exit_code == RESTART_APP_EXIT_CODE:
        script_path = Path(__file__).resolve().with_name("test.py")
        try:
            # Replace this Python process instead of spawning a detached child.
            # The original CMD keeps waiting on the same process chain and no
            # CREATE_NEW_CONSOLE window is created.
            _replace_process_in_current_console(script_path)
        except OSError:
            return 1
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
