"""Autopilot panel u Memory GUI-ju: Start/Stop, limit partija i AI poziva (igra svaki mod koji igra ponudi).

Veze sa prozorom (MemoryWindow) su namerno tanke:
- reader se kaci (ili mora vec biti zakacen) na serial Pie64_2
  (`window._pinned_serial`), da Auto i Autopilot igraju istu instancu;
- `on_match_state` prima signal readera; na pocetak meca ukljucuje postojeci
  Auto, koji se sam gasi na kraju meca;
- Stop odmah zatvara StopGate (nijedan novi klik) i gasi Auto ako ga je
  Autopilot upalio.
"""
from __future__ import annotations

import threading

from PyQt5 import QtCore, QtWidgets

import autopilot as ap
import autopilot_device as dev
from autopilot_ai import ClaudeAdvisor
from autopilot_screens import ScreenClassifier
from tools import matchmasters_board_reader as reader


class _Signals(QtCore.QObject):
    status = QtCore.pyqtSignal(str)
    resolved = QtCore.pyqtSignal(object, str)  # (adb, serial) ili (None, greska)
    finished = QtCore.pyqtSignal(str)


class AutopilotPanel(QtWidgets.QGroupBox):
    def __init__(self, window):
        super().__init__("Autopilot (Pie64_2)")
        self.window = window
        self.autopilot: ap.Autopilot | None = None
        self.gate = dev.StopGate()
        self._armed_auto = False
        self._pending_start = None
        self._pending_adb = None
        self._signals = _Signals()
        self._signals.status.connect(self._show_status)
        self._signals.resolved.connect(self._on_resolved)
        self._signals.finished.connect(self._on_finished)

        layout = QtWidgets.QGridLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        self.GamesSpin = QtWidgets.QSpinBox()
        self.GamesSpin.setRange(0, 9999)
        self.GamesSpin.setValue(0)
        self.GamesSpin.setPrefix("partija: ")
        self.GamesSpin.setSpecialValueText("partija: bez limita")
        self.GamesSpin.setToolTip("0 = bez limita: igra dok ima boostera (staje sam kad ih nema)")
        self.AiSpin = QtWidgets.QSpinBox()
        self.AiSpin.setRange(0, 20)
        self.AiSpin.setValue(6)
        self.AiSpin.setPrefix("AI/mec: ")
        self.AiSpin.setToolTip("Najvise poziva Claude-a po mecu; 0 = nepoznat ekran odmah pauzira")
        self.StartButton = QtWidgets.QPushButton("Start")
        self.StartButton.clicked.connect(self._start_stop)
        self.StatusLabel = QtWidgets.QLabel("Spreman")
        self.StatusLabel.setWordWrap(True)
        self.StatusLabel.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred)
        layout.addWidget(self.GamesSpin, 1, 0, 1, 2)
        layout.addWidget(self.AiSpin, 1, 2)
        layout.addWidget(self.StartButton, 2, 0, 1, 3)
        layout.addWidget(self.StatusLabel, 3, 0, 1, 3)

    # --- Start / Stop -----------------------------------------------------
    @property
    def running(self) -> bool:
        return self.autopilot is not None and self.autopilot.running

    def _start_stop(self) -> None:
        if self.running or self._pending_start is not None:
            self.stop()
            return
        self.gate.reset()
        self._pending_start = True
        self.StartButton.setText("Stop")
        self._show_status(f"Trazim {dev.INSTANCE_NAME} (ADB port iz BlueStacks konfiguracije)...")

        def worker():
            try:
                adb = reader.find_adb()
                serial = dev.resolve_instance_serial(adb)
            except Exception as exc:  # prikazuje se korisniku
                self._signals.resolved.emit(None, str(exc))
                return
            self._signals.resolved.emit(adb, serial)

        threading.Thread(target=worker, daemon=True).start()

    def _on_resolved(self, adb, serial_or_error: str) -> None:
        if self._pending_start is None or self.gate.stopped:
            return  # Stop je pritisnut u medjuvremenu
        if adb is None:
            self._pending_start = None
            self.StartButton.setText("Start")
            self._show_status(f"Ne mogu da nadjem {dev.INSTANCE_NAME}: {serial_or_error}")
            return
        serial = serial_or_error
        win = self.window
        win._pinned_serial = serial
        attached = getattr(win, "_adb_device", None) if win._reader_session is not None else None
        if attached is not None and attached[1] != serial:
            self._pending_start = None
            self.StartButton.setText("Start")
            self._show_status(f"Reader je zakacen na {attached[1]}, a Autopilot je za {serial}. "
                              "Otkaci reader (pa ce se zakaciti na Pie64_2) i pritisni Start.")
            return
        if win._reader_session is None:
            self._show_status(f"{dev.INSTANCE_NAME} = {serial}; kacim reader na nju...")
            win._reader_signals.attached.connect(self._continue_after_attach)
            if win.ReaderButton.isEnabled():
                win._reader_clicked()
            self._pending_adb = (adb, serial)
            return
        self._launch(adb, serial)

    def _continue_after_attach(self, *_):
        try:
            self.window._reader_signals.attached.disconnect(self._continue_after_attach)
        except TypeError:
            pass
        if self._pending_start is None or self.gate.stopped:
            return
        adb, serial = self._pending_adb
        self._launch(adb, serial)

    def _launch(self, adb: str, serial: str) -> None:
        self._pending_start = None
        try:
            classifier = ScreenClassifier()
        except Exception as exc:
            self.StartButton.setText("Start")
            self._show_status(f"Pravila se ne ucitavaju: {exc}")
            return
        config = ap.AutopilotConfig(games_limit=self.GamesSpin.value(),
                                    ai_calls_per_match=self.AiSpin.value())
        self.autopilot = ap.Autopilot(dev.AdbDevice(adb, serial, self.gate), classifier, ClaudeAdvisor(),
                                      self.gate, config, on_status=self._signals.status.emit)
        if self.window._match_active:
            self.autopilot.notify_match(True)
            self._arm_auto()
        auto = self.autopilot

        def run():
            result = auto.run()
            self._signals.finished.emit(result or "")

        auto._thread = threading.Thread(target=run, name="autopilot", daemon=True)
        auto._thread.start()

    def stop(self) -> None:
        """Odmah: nijedan novi klik Autopilota; Auto se gasi ako ga je Autopilot upalio."""
        self.gate.stop()
        self._pending_start = None
        if self._armed_auto and self.window.AutoButton.isChecked():
            self.window.AutoButton.setChecked(False)
        self._armed_auto = False
        self.StartButton.setText("Start")
        self._show_status("Stop: klikovi blokirani")

    def _on_finished(self, result: str) -> None:
        self.StartButton.setText("Start")
        stats = self.autopilot.stats if self.autopilot else None
        extra = f" (partija {stats.games_done}, AI poziva {stats.ai_calls_total})" if stats else ""
        if result.startswith("paused"):
            self._show_status("PAUZA - " + result.split(":", 1)[1].strip() + extra)
        elif result == "finished":
            self._show_status("Gotovo" + extra)
        else:
            self._show_status("Zaustavljen" + extra)

    # --- reader -------------------------------------------------------------
    def on_match_state(self, active: bool) -> None:
        if not self.running:
            return
        self.autopilot.notify_match(active)
        if active:
            self._arm_auto()
        else:
            self._armed_auto = False

    def _arm_auto(self) -> None:
        if self.gate.stopped:
            return
        button = self.window.AutoButton
        if not button.isChecked():
            button.setChecked(True)
            self._armed_auto = True

    def _show_status(self, message: str) -> None:
        self.StatusLabel.setText(message)
        try:
            self.window._log(f"Autopilot: {message}")
        except Exception:
            pass
