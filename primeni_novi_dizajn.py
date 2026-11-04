"""Prebaci memory_gui.py na novi dizajn (tema + dinamicni panel stanja).

Pokreni iz foldera "memory gui":

    python primeni_novi_dizajn.py            # primeni
    python primeni_novi_dizajn.py --dry-run  # samo prikazi sta bi promenio
    python primeni_novi_dizajn.py --revert   # vrati backup

Original ide u memory_gui.py.pre-novog-dizajna. Skript je namerno strog: ako
neki od ankera nije nadjen tacno jednom, nista se ne upisuje -- bolje glasna
greska nego pola primenjenog patcha.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
TARGET = HERE / "memory_gui.py"
BACKUP = HERE / "memory_gui.py.pre-novog-dizajna"
MARKER = "MemoryStatePanel"


class PatchError(RuntimeError):
    pass


def _replace_once(text, old, new, what):
    count = text.count(old)
    if count != 1:
        raise PatchError(
            "anker '%s' nadjen %d puta (treba tacno 1)" % (what, count)
        )
    return text.replace(old, new)


def _replace_span(text, start_anchor, end_anchor, new, what):
    """Zameni sve od linije koja pocinje start_anchor do linije end_anchor."""
    lines = text.splitlines(keepends=True)
    starts = [i for i, line in enumerate(lines) if line.startswith(start_anchor)]
    if len(starts) != 1:
        raise PatchError(
            "pocetak '%s' nadjen %d puta (treba 1)" % (what, len(starts))
        )
    start = starts[0]
    ends = [
        i for i, line in enumerate(lines[start:], start) if line.startswith(end_anchor)
    ]
    if not ends:
        raise PatchError("kraj bloka '%s' nije nadjen" % what)
    end = ends[0]
    return "".join(lines[:start]) + new + "".join(lines[end + 1 :])


STATE_PANEL_BLOCK = '''        # Stanje iz memorije: panel sam odlucuje koji redovi postoje za mod
        # koji se igra (gui_state_panel.MemoryStatePanel). Imena labela su
        # ostala ista, pa svaki postojeci setText poziv radi nepromenjen.
        self.StatePanel = MemoryStatePanel()
        self.StateLabel = self.StatePanel.StateLabel
        self.ScoreLabel = self.StatePanel.ScoreLabel
        self.MovesLabel = self.StatePanel.MovesLabel
        self.BoosterLabel = self.StatePanel.BoosterLabel
        self.ModeLabel = self.StatePanel.ModeLabel
        self.PerksLabel = self.StatePanel.PerksLabel
        self.MutationsLabel = self.StatePanel.MutationsLabel
        self.TurnLabel = self.StatePanel.TurnLabel
        self.FreshLabel = self.StatePanel.FreshLabel
        self.LegendLabel = self.StatePanel.LegendLabel
        self.BoosterNameLabel = self.StatePanel.BoosterNameLabel
        layout.addWidget(self.StatePanel)
'''

PATCHES = [
    # 1. uvoz nova dva modula
    (
        "exact",
        "import swipe_recorder\n",
        "import swipe_recorder\nfrom gui_state_panel import MemoryStatePanel\n"
        "from gui_theme import apply_theme\n",
        "uvoz gui_state_panel / gui_theme",
    ),
    # 2. centralni widget: ime za QSS + vazduh oko sadrzaja
    (
        "exact",
        "        central = QtWidgets.QWidget()\n"
        "        layout = QtWidgets.QVBoxLayout(central)\n",
        "        central = QtWidgets.QWidget()\n"
        '        central.setObjectName("Central")\n'
        "        layout = QtWidgets.QVBoxLayout(central)\n"
        "        layout.setContentsMargins(12, 12, 12, 10)\n"
        "        layout.setSpacing(9)\n",
        "centralni widget",
    ),
    # 3. fiksna mreza "Stanje iz memorije" -> dinamicni panel
    (
        "span",
        '        state_box = QtWidgets.QGroupBox("Stanje iz memorije")',
        "        layout.addWidget(state_box)",
        STATE_PANEL_BLOCK,
        "blok Stanje iz memorije",
    ),
    # 4. Booster ime: preselilo se u panel
    (
        "span",
        '        booster_title = QtWidgets.QLabel("Booster:")',
        "        options.addWidget(self.BoosterNameLabel, 3, 1)",
        "        # Booster (ime + punjenje) je sada u MemoryStatePanel.\n",
        "red Booster u options mrezi",
    ),
    # 5. Legenda: preselila se u panel
    (
        "span",
        '        legend_title = QtWidgets.QLabel("Legenda:")',
        "        options.addWidget(self.LegendLabel, 5, 1)",
        "        # Legenda skora je sada u MemoryStatePanel (red se sam sakriva\n"
        "        # kad mod nema posebnu legendu).\n",
        "red Legenda u options mrezi",
    ),
    # 6. celije table: krupnije, zaobljenije
    (
        "exact",
        "                cell.setFixedSize(38, 32)\n"
        '                cell.setFont(QtGui.QFont("Consolas", 8, QtGui.QFont.Bold))\n'
        '                cell.setStyleSheet("background:#20232b;color:#6b7280;border-radius:4px;")\n',
        "                cell.setFixedSize(36, 36)\n"
        '                cell.setFont(QtGui.QFont("Consolas", 9, QtGui.QFont.Bold))\n'
        "                cell.setStyleSheet(\n"
        '                    "background:#20232b;color:#6b7280;border-radius:8px;"\n'
        "                )\n",
        "izgled celije table",
    ),
    (
        "exact",
        "        board_layout.setSpacing(2)\n",
        "        board_layout.setSpacing(3)\n",
        "razmak izmedju celija",
    ),
    # 7. isti radijus i pri svakom renderu + amber prsten za Lights Up
    (
        "exact",
        "                border = (\n"
        '                    "2px solid #f2c94c" if col == lit_column else "2px solid transparent"\n'
        "                )\n"
        "                cell.setStyleSheet(\n"
        '                    f"background:{background};color:{foreground};"\n'
        '                    f"border-radius:4px;border:{border};"\n'
        "                )\n",
        "                border = (\n"
        '                    "2px solid #f59e0b" if col == lit_column else "2px solid transparent"\n'
        "                )\n"
        "                cell.setStyleSheet(\n"
        '                    f"background:{background};color:{foreground};"\n'
        '                    f"border-radius:8px;border:{border};"\n'
        "                )\n",
        "izgled celije pri renderu",
    ),
    # 8. panel dobija kontekst partije na svaki snapshot
    (
        "exact",
        "        self.ModeLabel.setText(\n"
        "            self._mode_label_text(state, rules_id, mode, unmapped, mode_suffix)\n"
        "        )\n",
        "        self.ModeLabel.setText(\n"
        "            self._mode_label_text(state, rules_id, mode, unmapped, mode_suffix)\n"
        "        )\n"
        "        # Naslov moda, bedz tipa partije (Solo Challenge / Party /\n"
        "        # Showdown / 1v1) i koje kartice uopste postoje za ovu partiju.\n"
        "        self.StatePanel.update_match(rules, players, state, me)\n",
        "update_match poziv",
    ),
    # 9. akciona dugmad: imena za QSS (Auto je primarno)
    (
        "exact",
        "        layout.addLayout(actions)\n",
        "        layout.addLayout(actions)\n"
        '        self.AutoButton.setObjectName("AutoButton")\n'
        "        for button in (\n"
        "            self.BestMoveButton,\n"
        "            self.ExtraMoveButton,\n"
        "            self.PointsButton,\n"
        "        ):\n"
        '            button.setProperty("actionButton", True)\n',
        "imena akcione dugmadi",
    ),
    # 10. prozor: isti uski format, malo visi zbog kartica
    (
        "exact",
        "        self.resize(360, 760)\n",
        "        self.resize(360, 820)\n        self.setMinimumWidth(360)\n",
        "velicina prozora",
    ),
    # 11. tema na nivou aplikacije
    (
        "exact",
        "    application = QtWidgets.QApplication(sys.argv)\n"
        "    window = MemoryWindow()\n",
        "    application = QtWidgets.QApplication(sys.argv)\n"
        "    apply_theme(application)\n"
        "    window = MemoryWindow()\n",
        "primena teme u main()",
    ),
]


def revert() -> int:
    if not BACKUP.exists():
        print("Nema backupa (%s)." % BACKUP.name)
        return 1
    shutil.copy2(BACKUP, TARGET)
    print("Vraceno iz %s." % BACKUP.name)
    return 0


def main(argv) -> int:
    if "--revert" in argv:
        return revert()
    dry_run = "--dry-run" in argv

    for name in ("gui_theme.py", "gui_state_panel.py"):
        if not (HERE / name).exists():
            print("Fali %s -- kopiraj oba nova modula pored memory_gui.py." % name)
            return 1
    if not TARGET.exists():
        print("memory_gui.py nije u ovom folderu (%s)." % HERE)
        return 1

    source = TARGET.read_text(encoding="utf-8")
    if MARKER in source:
        print("Patch je vec primenjen (memory_gui.py zna za MemoryStatePanel).")
        return 0

    patched = source
    for patch in PATCHES:
        try:
            if patch[0] == "exact":
                _, old, new, what = patch
                patched = _replace_once(patched, old, new, what)
            else:
                _, start, end, new, what = patch
                patched = _replace_span(patched, start, end, new, what)
        except PatchError as error:
            print("PREKID: %s (%s). Nista nije upisano." % (error, patch[-1]))
            return 2
        print("ok: %s" % patch[-1])

    if dry_run:
        print("\n--dry-run: 11/11 ankera nadjeno, nista nije upisano.")
        return 0

    if not BACKUP.exists():
        shutil.copy2(TARGET, BACKUP)
        print("backup: %s" % BACKUP.name)
    TARGET.write_text(patched, encoding="utf-8")
    print("\nGotovo. Pokreni: python memory_gui.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
