"""Square Solo: snimi partiju, isplaniraj ceo ostatak simulacijom i odigraj sam.

Zaseban od Memory GUI-ja i njegove racunice. Svaki potez:
capture (jednokratni agent, bez stalnog readera) -> provera da je igra uradila
ono sto je simulator predvideo -> planer (beam pretraga nad tacnim
simulatorom dopune i engine RNG-a, do poslednjeg poteza) -> prevlacenje.
Iz Memory GUI-ja se koriste samo kalibracija ekrana i swipe podesavanja.

Mis u gornji levi ugao ekrana prekida pyautogui (failsafe).
"""
from __future__ import annotations

import contextlib
import datetime as dt
import io
import json
import sys
import threading
import time
import traceback
from pathlib import Path

from PyQt5 import QtCore, QtGui, QtWidgets

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import gui_theme as theme

# Simulator colours (board_source) -> swatches; specials -> short labels.
TILE_COLORS = {1: "#2563eb", 2: "#16a34a", 3: "#eab308", 4: "#9333ea", 5: "#dc2626",
               6: "#f97316", 7: "#e5e7eb", 0: "#111318", -1: "#3a3f4a", 99: "#f472b6"}
SPECIAL_LABELS = {1: "↔", 2: "↕", 3: "●", 4: "⚡", 46: "⌖"}
TIMING_PATH = ROOT / "memory_gui_timing.json"
SETTLE_SECONDS = 1.2
CAPTURE_RETRIES = 20
BOOSTER_SETTLE_SECONDS = 4.0
BOOSTER_STABLE_GAP = 1.5


class Stopped(Exception):
    pass


class Engine(QtCore.QObject):
    """Capture / plan / play, run on a worker thread."""

    log = QtCore.pyqtSignal(str)
    state = QtCore.pyqtSignal(object)      # lab state after a capture
    planned = QtCore.pyqtSignal(object)    # (Line, stats, seconds)
    busy = QtCore.pyqtSignal(bool)
    stopped_auto = QtCore.pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.session = ROOT / "Debug/match_captures" / ("solo_gui_" + dt.datetime.now().strftime("%Y%m%d_%H%M%S"))
        self.number = 0
        self.current = None        # lab state of the latest capture
        self.capture_dir = None
        self.plan_line = None      # best Line from self.current
        self.expected = None       # predicted state after the swipe we played
        self.plan_seconds = 40.0
        self.verify = True
        self.auto_booster = True
        self.cancel = threading.Event()
        self._geometry_ready = False

    # ------------------------------------------------------------- capture --
    def _capture_once(self):
        from tools import capture_match

        self.session.mkdir(parents=True, exist_ok=True)
        output = self.session / f"{self.number:02d}_{dt.datetime.now().strftime('%H%M%S')}"
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = capture_match.main(["--out", str(output)])
        if code not in (0, 2) or not output.is_dir():
            raise RuntimeError("snimak nije sacuvan")
        self.number += 1
        return output

    def capture(self, settle=False):
        """Capture until the board is still; returns the new lab state."""
        from simulator_capture import lab_move, load_capture

        if settle:
            self._sleep(SETTLE_SECONDS)
        last = None
        for _ in range(CAPTURE_RETRIES):
            self._check()
            try:
                output = self._capture_once()
                break
            except Exception as exc:  # board moving, agent attach, ...
                last = exc
                self._sleep(0.7)
        else:
            raise RuntimeError(f"snimanje ne uspeva: {last}")
        state = lab_move(load_capture(output))
        self.capture_dir, self.current = output, state
        self.log.emit(f"Snimak {output.name}: skor {state['score']}, poteza {state['turn_state']['remaining_moves']}")
        self.state.emit(state)
        return state

    def check_prediction(self):
        """Compare the fresh capture with what the simulator promised."""
        from simulator_capture import load_capture
        from tools import verify_refill

        if self.expected is None:
            return True
        want = verify_refill.observed(load_capture(self.capture_dir))
        diff = verify_refill.differences(want, verify_refill.predicted({"state": self.expected}))
        self.expected = None
        if diff:
            self.log.emit("NE POKLAPA SE sa predvidjanjem:\n  " + "\n  ".join(diff))
            return False
        self.log.emit("Poklapa se sa predvidjanjem.")
        return True

    # ---------------------------------------------------------------- plan --
    def plan(self):
        from strategy_lab import planner

        state = self.current
        if state is None:
            raise RuntimeError("prvo snimi partiju")
        started = time.monotonic()
        self.log.emit(f"Planiram do kraja ({self.plan_seconds:.0f} s)...")
        best, stats = planner.plan_anytime(state, self.plan_seconds)
        # A remainder of the previous plan is still exact if the game followed
        # it; keep it when the fresh search did not beat it.
        previous = self.plan_line
        if (previous is not None and previous.actions[1:]
                and self._same_state(getattr(previous, "after_first", None), state)
                and previous.score > best.score):
            best = planner.Line(previous.state, previous.actions[1:], previous.gains[1:])
            self.log.emit("Zadrzan ostatak prethodnog plana (bolji od nove pretrage).")
        self.plan_line = best
        seconds = time.monotonic() - started
        self.log.emit(f"Plan: skor {best.score} ({best.score - (state.get('score') or 0):+d}), "
                      f"{len(best.actions)} poteza, sirina {stats['width']}, "
                      f"{stats['simulated']} simulacija, {seconds:.0f} s")
        self.planned.emit((best, stats, seconds))
        return best

    @staticmethod
    def _same_state(a, b):
        if a is None or b is None:
            return False
        flat = lambda s: [int(v) for row in s["board"] for v in row] + [int(v) for row in s["special_board"] for v in row]
        return (flat(a) == flat(b) and a.get("score") == b.get("score")
                and a["engine_refill"].rng.counter == b["engine_refill"].rng.counter)

    # ---------------------------------------------------------------- play --
    def _prepare_input(self):
        import recognition
        import runtime
        import swipe_recorder

        if not self._geometry_ready:
            try:
                timing = json.loads(TIMING_PATH.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                timing = {}
            for key, name, kind in (("swipe_duration", "SWIPE_DURATION_SECONDS", float),
                                    ("swipe_distance_px", "SWIPE_DISTANCE_PX", int),
                                    ("swipe_pre_hold", "SWIPE_PRE_MOVE_HOLD_SECONDS", float),
                                    ("swipe_post_hold", "SWIPE_POST_MOVE_HOLD_SECONDS", float),
                                    ("swipe_profile_speed", "SWIPE_PROFILE_SPEED", float)):
                if isinstance(timing.get(key), (int, float)):
                    setattr(runtime, name, kind(timing[key]))
            runtime.SWIPE_PROFILE = swipe_recorder.load_profile()
            runtime.SWIPE_USE_PROFILE = bool(timing.get("swipe_use_profile")) and runtime.SWIPE_PROFILE is not None
            recognition.set_ml_recognition_mode(runtime.ML_RECOGNITION_ONLY)
            self._geometry_ready = True
        try:
            profile = json.loads((ROOT / "gui_state.json").read_text(encoding="utf-8")).get("board_profile")
        except (OSError, ValueError):
            profile = None
        # Re-anchored every move, like Memory GUI: the window may have moved.
        recognition.apply_board_profile(profile or runtime.DEFAULT_PROFILE)
        return runtime

    def play_and_capture(self, attempts=3):
        """Play the planned action and capture; repeat it while the game did
        not take it (unchanged board, score and RNG), e.g. a missed swipe."""
        before = self.current
        for attempt in range(attempts):
            self.play_next(flip=attempt == attempts - 1)
            state = self.capture(settle=True)
            if not self._same_state(state, before):
                return state
            self.expected = None
            self.log.emit(f"Potez nije prosao (tabla ista), pokusaj {attempt + 2}...")
        raise RuntimeError(f"potez ne prolazi ni posle {attempts} pokusaja")

    def play_next(self, flip=False):
        from strategy_lab.simulation import step

        line, state = self.plan_line, self.current
        if line is None or not line.actions:
            raise RuntimeError("nema plana za odigravanje")
        action = line.actions[0]
        if flip and action.get("kind", "swap") in ("swap", "energy_boost"):
            # The same exchange dragged from the other end, only when the
            # simulator says it leaves the identical board (special placement
            # can depend on which piece was dragged).
            opposite = {"up": "down", "down": "up", "left": "right", "right": "left"}
            flipped = dict(action, start=action["target"], target=action["start"],
                           direction=opposite[action["direction"]])
            a, b = step(state, action), step(state, flipped)
            if a["supported"] and b["supported"] and self._same_state(a["state"], b["state"]):
                action = flipped
        result = step(state, action)
        if not result["supported"]:
            raise RuntimeError(f"potez vise nije podrzan: {result['reason']}")
        runtime = self._prepare_input()
        self._check()
        from strategy_lab.planner import describe
        self.log.emit(f"Igram {describe(action)} (ocekujem +{int(round(result['score_gain']))})")
        self._perform(runtime, state, action)
        self.expected = result["state"]
        line.after_first = result["state"]

    def _perform(self, runtime, state, action):
        """Mouse input for one planned action, with Memory GUI's click points."""
        import pyautogui
        from strategy_lab.simulation import PERK_ENERGY_BOOST, PERK_TELEPORT

        kind = action.get("kind", "swap")
        if kind == "booster":
            runtime.click_booster_activate(runtime._memory_booster_click_detection(True))
            return
        if kind in ("energy_boost", "teleport"):
            perk = PERK_ENERGY_BOOST if kind == "energy_boost" else PERK_TELEPORT
            slot = (state.get("perk_slots") or {}).get(perk)
            if slot is None:
                raise RuntimeError("ne znam na kom je dugmetu perk")
            x, y = runtime.perk_slot_center(slot)
            pyautogui.click(x, y)
            self._sleep(runtime.PERK_PROMPT_DELAY_SECONDS)
        if kind == "teleport":
            for cell in (action["start"], action["target"]):
                x, y = runtime.board_cell_center(tuple(cell))
                pyautogui.click(x, y)
                self._sleep(runtime.PERK_PROMPT_DELAY_SECONDS)
            return
        runtime.play_best_move_with_cursor_restore(tuple(action["start"]), action["direction"], 0)

    def _keeps_moves(self, action):
        from strategy_lab.simulation import step

        result = step(self.current, action)
        moves = self.current["turn_state"].get("remaining_moves") or 0
        return result["supported"] and (result["state"]["turn_state"].get("remaining_moves") or 0) >= moves

    # ------------------------------------------------------------- booster --
    @staticmethod
    def booster_ready(state):
        charge = state.get("booster_state") or {}
        return charge.get("maximum") is not None and (charge.get("current") or 0) >= charge["maximum"]

    def _capture_stable(self):
        """Doctor Color pauses between its recolouring steps, longer than the
        capture's own 0.25 s stillness check: wait for two captures in a row
        that agree on board, score and RNG."""
        previous = self.capture()
        for _ in range(12):
            self._sleep(BOOSTER_STABLE_GAP)
            state = self.capture()
            if self._same_state(previous, state):
                return state
            previous = state
        raise RuntimeError("tabla se ne smiruje posle boostera")

    def fire_booster(self, attempts=3):
        """Fire the booster without a prediction, then continue from the board
        the game actually produced. Doctor Color is not simulated exactly."""
        before = self.current
        for attempt in range(attempts):
            runtime = self._prepare_input()
            self.log.emit("Bacam booster (bez predvidjanja)...")
            self._perform(runtime, before, {"kind": "booster"})
            self.expected = None
            self.plan_line = None
            self._sleep(BOOSTER_SETTLE_SECONDS)
            state = self._capture_stable()
            if not self.booster_ready(state):
                self.log.emit(f"Booster odigran: skor {before['score']} -> {state['score']}")
                return state
            self.log.emit(f"Booster nije aktiviran, pokusaj {attempt + 2}...")
        raise RuntimeError(f"booster se ne aktivira ni posle {attempts} pokusaja")

    # ---------------------------------------------------------------- auto --
    def auto(self):
        self.capture()
        while True:
            self._check()
            if not self.check_prediction() and self.verify:
                return "igra se nije poklopila sa simulatorom"
            # A full meter cannot charge further, so every later Blue would
            # be wasted; the booster costs no move, so it also fires at the end.
            if self.auto_booster and self.booster_ready(self.current):
                # The booster's result is unknown, so first cash every free
                # action the plan already sees (extra-move fours, Teleport).
                line = self.plan()
                if line.actions and self._keeps_moves(line.actions[0]):
                    self.log.emit("Booster je pun: prvo besplatan potez iz plana.")
                    self.play_and_capture()
                    continue
                self.fire_booster()
                continue
            if (self.current["turn_state"].get("remaining_moves") or 0) <= 0:
                return "nema vise poteza"
            line = self.plan()
            if not line.actions:
                return "nema podrzanog poteza (npr. nasumican specijal)"
            self.play_and_capture()

    def _check(self):
        if self.cancel.is_set():
            raise Stopped()

    def _sleep(self, seconds):
        if self.cancel.wait(seconds):
            raise Stopped()

    @QtCore.pyqtSlot(str)
    def run(self, job):
        self.busy.emit(True)
        self.cancel.clear()
        try:
            if job == "capture":
                self.capture()
                self.check_prediction()
                self.plan()
            elif job == "play":
                self.play_and_capture()
                self.check_prediction()
                self.plan()
            elif job == "booster":
                if self.current is None:
                    self.capture()
                self.fire_booster()
                self.plan()
            elif job == "auto":
                reason = self.auto()
                self.stopped_auto.emit(reason)
                self.log.emit(f"Auto stao: {reason}")
        except Stopped:
            self.log.emit("Zaustavljeno.")
            self.stopped_auto.emit("zaustavljeno")
        except Exception as exc:
            self.log.emit(f"Greska: {exc}")
            self.log.emit(traceback.format_exc(limit=3))
            self.stopped_auto.emit(str(exc))
        finally:
            self.busy.emit(False)


class BoardView(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.board = self.special = None
        self.move = None
        self.setMinimumSize(320, 320)

    def show_state(self, board, special, move=None):
        self.board, self.special, self.move = board, special, move
        self.update()

    def paintEvent(self, _):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.fillRect(self.rect(), QtGui.QColor(theme.BG_SUNKEN))
        if not self.board:
            painter.setPen(QtGui.QColor(theme.INK_DIM))
            painter.drawText(self.rect(), QtCore.Qt.AlignCenter, "Snimi partiju")
            return
        n = len(self.board)
        size = min(self.width(), self.height()) / n
        ox, oy = (self.width() - size * n) / 2, (self.height() - size * n) / 2
        font = painter.font()
        font.setPointSizeF(size * 0.32)
        painter.setFont(font)
        for r in range(n):
            for c in range(n):
                cell = QtCore.QRectF(ox + c * size + 3, oy + r * size + 3, size - 6, size - 6)
                painter.setPen(QtCore.Qt.NoPen)
                painter.setBrush(QtGui.QColor(TILE_COLORS.get(int(self.board[r][c]), "#555")))
                painter.drawRoundedRect(cell, 8, 8)
                label = SPECIAL_LABELS.get(int(self.special[r][c]))
                if label:
                    painter.setPen(QtGui.QColor("#0b0b0b"))
                    painter.drawText(cell, QtCore.Qt.AlignCenter, label)
        if self.move and "start" in self.move:
            (r, c), (y, x) = self.move["start"], self.move["target"]
            pen = QtGui.QPen(QtGui.QColor(theme.ACCENT_BRIGHT), 4)
            painter.setPen(pen)
            painter.setBrush(QtCore.Qt.NoBrush)
            for rr, cc in ((r, c), (y, x)):
                painter.drawRoundedRect(QtCore.QRectF(ox + cc * size + 1, oy + rr * size + 1, size - 2, size - 2), 9, 9)
            a = QtCore.QPointF(ox + (c + .5) * size, oy + (r + .5) * size)
            b = QtCore.QPointF(ox + (x + .5) * size, oy + (y + .5) * size)
            painter.drawLine(a, b)


class Window(QtWidgets.QWidget):
    start_job = QtCore.pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Square Solo simulator")
        self.resize(900, 620)
        self.engine = Engine()
        self.thread = QtCore.QThread(self)
        self.engine.moveToThread(self.thread)
        self.start_job.connect(self.engine.run)
        self.thread.start()

        self.board = BoardView()
        self.status = QtWidgets.QLabel("Udji u Square Match Solo, zatvori Memory GUI i pritisni Snimi.")
        self.status.setWordWrap(True)
        self.summary = QtWidgets.QLabel("")
        self.summary.setStyleSheet(f"font-size: 15px; color: {theme.ACCENT_BRIGHT};")
        self.plan_list = QtWidgets.QListWidget()
        self.log = QtWidgets.QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(2000)

        self.capture_button = QtWidgets.QPushButton("Snimi i isplaniraj")
        self.play_button = QtWidgets.QPushButton("Odigraj sledeci")
        self.auto_button = QtWidgets.QPushButton("Auto: igraj sam")
        self.booster_button = QtWidgets.QPushButton("Baci booster")
        self.stop_button = QtWidgets.QPushButton("Stop")
        self.auto_booster = QtWidgets.QCheckBox("Auto baca booster cim je pun")
        self.auto_booster.setChecked(True)
        self.seconds = QtWidgets.QSpinBox()
        self.seconds.setRange(3, 600)
        self.seconds.setValue(40)
        self.seconds.setSuffix(" s po potezu")
        self.verify = QtWidgets.QCheckBox("Stani ako se igra ne poklopi sa simulatorom")
        self.verify.setChecked(True)

        controls = QtWidgets.QHBoxLayout()
        for widget in (self.capture_button, self.play_button, self.booster_button, self.auto_button,
                       self.stop_button):
            controls.addWidget(widget)
        settings = QtWidgets.QHBoxLayout()
        settings.addWidget(QtWidgets.QLabel("Planiranje:"))
        settings.addWidget(self.seconds)
        settings.addWidget(self.verify)
        settings.addWidget(self.auto_booster)
        settings.addStretch(1)
        right = QtWidgets.QVBoxLayout()
        right.addWidget(self.summary)
        right.addWidget(QtWidgets.QLabel("Plan do kraja"))
        right.addWidget(self.plan_list, 2)
        right.addWidget(QtWidgets.QLabel("Dnevnik"))
        right.addWidget(self.log, 3)
        top = QtWidgets.QHBoxLayout()
        top.addWidget(self.board, 3)
        top.addLayout(right, 2)
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.status)
        layout.addLayout(top, 1)
        layout.addLayout(settings)
        layout.addLayout(controls)

        self.capture_button.clicked.connect(lambda: self._start("capture"))
        self.play_button.clicked.connect(lambda: self._start("play"))
        self.auto_button.clicked.connect(lambda: self._start("auto"))
        self.booster_button.clicked.connect(lambda: self._start("booster"))
        self.stop_button.clicked.connect(self.engine.cancel.set)
        self.engine.log.connect(self._log)
        self.engine.state.connect(self._show_state)
        self.engine.planned.connect(self._show_plan)
        self.engine.busy.connect(self._busy)
        self.engine.stopped_auto.connect(lambda reason: self.status.setText(f"Stao: {reason}"))
        QtWidgets.QShortcut(QtGui.QKeySequence("Esc"), self, activated=self.engine.cancel.set)
        self._busy(False)

    def _start(self, job):
        self.engine.plan_seconds = float(self.seconds.value())
        self.engine.verify = self.verify.isChecked()
        self.engine.auto_booster = self.auto_booster.isChecked()
        self.status.setText({"capture": "Snimam i planiram...", "play": "Igram jedan potez...",
                             "booster": "Bacam booster i cekam da se tabla smiri...",
                             "auto": "Auto: igram sam (Stop ili Esc za prekid, mis u gornji levi ugao = hitni prekid)"}[job])
        self.start_job.emit(job)

    def _busy(self, busy):
        for button in (self.capture_button, self.play_button, self.auto_button, self.booster_button):
            button.setEnabled(not busy)
        self.play_button.setEnabled(not busy and self.engine.plan_line is not None and bool(self.engine.plan_line.actions))
        self.stop_button.setEnabled(busy)

    def _log(self, text):
        self.log.appendPlainText(f"{time.strftime('%H:%M:%S')}  {text}")

    def _show_state(self, state):
        self.board.show_state(state["board"], state["special_board"])
        targets = [t for t in state.get("solo_targets") or [] if t > state["score"]]
        self.summary.setText(f"Skor {state['score']}   poteza {state['turn_state']['remaining_moves']}"
                             + (f"   cilj {targets[0]}" if targets else ""))

    def _show_plan(self, payload):
        from strategy_lab.planner import describe

        best, stats, seconds = payload
        state = self.engine.current
        self.board.show_state(state["board"], state["special_board"], best.actions[0] if best.actions else None)
        self.plan_list.clear()
        total = state["score"]
        for number, (action, gain) in enumerate(zip(best.actions, best.gains), 1):
            total += int(round(gain))
            self.plan_list.addItem(f"{number:2d}. {describe(action)}   +{int(round(gain))}  = {total}")
        self.summary.setText(self.summary.text().split("   plan")[0] + f"   plan: {best.score}")

    def closeEvent(self, event):
        self.engine.cancel.set()
        self.thread.quit()
        self.thread.wait(3000)
        super().closeEvent(event)


def main():
    app = QtWidgets.QApplication(sys.argv)
    theme.apply_theme(app)
    window = Window()
    window.show()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
