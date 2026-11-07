"""Proveri dopunu: Enter -> snimak iz memorije -> poredjenje sa prethodnim snimkom.

GUI nad tools/capture_session.py: svaki Enter je jedan tools/capture_match.py
capture (agent se kaci, cita i odvaja), a uzastopni snimci iste partije se
porede preko tools/verify_refill.py. Mod partije se cita iz memorije (rules id,
board model), isto kao u Memory GUI-ju. Radi u svim modovima; van poslednje
runde probaju se hipoteze pragova sprecavanja i pokazuje koja se poklopila.

Enter radi kad je ovaj prozor u fokusu; F8 radi i dok je igra u fokusu.
"""
from __future__ import annotations

import contextlib
import ctypes
import ctypes.wintypes
import datetime as dt
import io
import sys
import time
import traceback
from collections import Counter
from pathlib import Path

from PyQt5 import QtCore, QtGui, QtWidgets

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import gui_theme as theme

WM_HOTKEY = 0x0312
HOTKEY_ID = 0xB0F8
VK_F8 = 0x77
MOD_NOREPEAT = 0x4000


class Engine(QtCore.QObject):
    log = QtCore.pyqtSignal(str)
    header = QtCore.pyqtSignal(str)
    tally = QtCore.pyqtSignal(str)
    busy = QtCore.pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self.session = None
        self.previous = None
        self.number = 0
        self.results = Counter()      # ("mod", "poklapa"/"ne"/...) -> count
        self.hypotheses = Counter()   # hypothesis name -> transitions it reproduced

    def new_session(self):
        self.session = ROOT / "Debug/match_captures" / ("verify_" + dt.datetime.now().strftime("%Y%m%d_%H%M%S"))
        self.previous = None
        self.number = 0

    @QtCore.pyqtSlot()
    def capture(self):
        from simulator_capture import load_capture
        from tools import capture_match, capture_session, verify_refill

        self.busy.emit(True)
        try:
            if self.session is None:
                self.new_session()
            self.session.mkdir(parents=True, exist_ok=True)
            output = self.session / f"{self.number:02d}_{dt.datetime.now().strftime('%H%M%S')}"
            buffer = io.StringIO()
            started = time.monotonic()
            try:
                with contextlib.redirect_stdout(buffer):
                    code = capture_match.main(["--out", str(output)])
            except Exception as exc:
                self.log.emit(f"Snimak nije uspeo: {exc}\nSacekaj da tabla miruje (Memory GUI zatvoren) pa ponovo.")
                return
            if code not in (0, 2) or not output.is_dir():
                self.log.emit("Snimak nije sacuvan; pokusaj ponovo.\n" + buffer.getvalue().strip())
                return
            capture = load_capture(output)
            info = verify_refill.describe_capture(capture)
            self.header.emit(verify_refill.format_info(info))
            line = f"[{self.number:02d}] snimljeno za {time.monotonic() - started:.1f} s  ({output.name})"
            if code == 2:
                line += "  - ima nerazresenih citanja"
            self.log.emit(line)
            if self.previous is not None:
                summary = capture_session.summarize(self.previous, output)
                self.log.emit(summary)
                self._count(info, summary, self.previous, output)
            self.previous = output
            self.number += 1
        except Exception:
            self.log.emit("Greska:\n" + traceback.format_exc())
        finally:
            self.busy.emit(False)

    def _count(self, info, summary, before, after):
        mode = info["title"] or info["rules_id"] or "?"
        if summary.startswith("POKLAPA SE"):
            outcome = "poklapa"
            for part in summary.split("[pragovi: ")[1:]:
                self.hypotheses[part.split("]")[0]] += 1
        elif summary.startswith("NE POKLAPA"):
            outcome = "ne poklapa"
        elif summary.startswith("nova partija") or summary.startswith("igra nije odigrala"):
            return
        else:
            outcome = "nepodrzano"
        self.results[(mode, outcome)] += 1
        modes = sorted({m for m, _ in self.results})
        lines = []
        for m in modes:
            parts = [f"{o} {self.results[(m, o)]}" for o in ("poklapa", "ne poklapa", "nepodrzano")
                     if self.results[(m, o)]]
            lines.append(f"{m}: " + ", ".join(parts))
        if self.hypotheses:
            lines.append("Pragovi koji su se poklopili: " + ", ".join(
                f"{name} x{count}" for name, count in self.hypotheses.most_common()))
        self.tally.emit("\n".join(lines))


class Window(QtWidgets.QWidget):
    start_capture = QtCore.pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Proveri dopunu")
        self.resize(820, 640)
        self.engine = Engine()
        self.thread = QtCore.QThread(self)
        self.engine.moveToThread(self.thread)
        self.start_capture.connect(self.engine.capture)
        self.thread.start()
        self._busy_now = False

        intro = QtWidgets.QLabel(
            "Udji u partiju (bilo koji mod) i zatvori Memory GUI. Pritisni Enter (ili F8 iz igre) "
            "na pocetku i posle svakog svog poteza, kad tabla miruje.")
        intro.setWordWrap(True)
        self.header = QtWidgets.QLabel("Mod: -")
        self.header.setStyleSheet(f"font-size: 15px; color: {theme.ACCENT_BRIGHT};")
        self.header.setWordWrap(True)
        self.tally = QtWidgets.QLabel("")
        self.tally.setWordWrap(True)
        self.log = QtWidgets.QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(5000)
        self.capture_button = QtWidgets.QPushButton("Snimi (Enter / F8)")
        self.capture_button.setMinimumHeight(44)
        self.new_button = QtWidgets.QPushButton("Nova sesija")
        self.open_button = QtWidgets.QPushButton("Otvori folder")

        controls = QtWidgets.QHBoxLayout()
        controls.addWidget(self.capture_button, 3)
        controls.addWidget(self.new_button, 1)
        controls.addWidget(self.open_button, 1)
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addWidget(self.header)
        layout.addWidget(self.tally)
        layout.addWidget(self.log, 1)
        layout.addLayout(controls)

        self.capture_button.clicked.connect(self._capture)
        self.new_button.clicked.connect(self._new_session)
        self.open_button.clicked.connect(self._open_folder)
        self.engine.log.connect(self._log)
        self.engine.header.connect(self.header.setText)
        self.engine.tally.connect(self.tally.setText)
        self.engine.busy.connect(self._busy)
        for key in ("Return", "Enter"):
            QtWidgets.QShortcut(QtGui.QKeySequence(key), self, activated=self._capture)
        self._hotkey = False
        if sys.platform == "win32":
            self._hotkey = bool(ctypes.windll.user32.RegisterHotKey(
                int(self.winId()), HOTKEY_ID, MOD_NOREPEAT, VK_F8))
        if not self._hotkey:
            self._log("F8 iz igre nije dostupan (zauzet?); koristi Enter u ovom prozoru.")

    def nativeEvent(self, event_type, message):
        if event_type == "windows_generic_MSG":
            msg = ctypes.wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                self._capture()
                return True, 0
        return super().nativeEvent(event_type, message)

    def _capture(self):
        if self._busy_now:
            return
        self._busy(True)
        self.start_capture.emit()

    def _new_session(self):
        if self._busy_now:
            return
        self.engine.new_session()
        self._log(f"Nova sesija: {self.engine.session}")

    def _open_folder(self):
        folder = self.engine.session if self.engine.session and self.engine.session.exists() \
            else ROOT / "Debug/match_captures"
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(folder)))

    def _busy(self, busy):
        self._busy_now = busy
        self.capture_button.setEnabled(not busy)
        self.new_button.setEnabled(not busy)
        self.capture_button.setText("Snimam... ne povlaci poteze" if busy else "Snimi (Enter / F8)")

    def _log(self, text):
        self.log.appendPlainText(f"{time.strftime('%H:%M:%S')}  {text}")
        self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())

    def closeEvent(self, event):
        if self._hotkey:
            ctypes.windll.user32.UnregisterHotKey(int(self.winId()), HOTKEY_ID)
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
