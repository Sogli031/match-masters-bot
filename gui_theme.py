"""Dark, modern Qt theme for the memory cockpit.

Kept out of :mod:`memory_gui` on purpose: the panel code and the look are
separate concerns, and a stylesheet in its own module can be edited (or
dropped) without touching a single widget.

Fonts degrade instead of failing: "Space Grotesk"/"JetBrains Mono" are used
when installed, otherwise Qt falls back to Segoe UI / Consolas, which every
Windows install has.
"""

from __future__ import annotations

from PyQt5 import QtGui, QtWidgets


# The board cell colours stay exactly as memory_gui.CELL_COLORS defines them --
# they carry meaning (piece colour), so the theme must not touch them.
BG = "#0d0f13"
BG_SUNKEN = "#0a0c10"
CARD = "#14181f"
CARD_LINE = "#222834"
CONTROL = "#151a22"
CONTROL_LINE = "#242c38"
CONTROL_LINE_HOVER = "#2f394a"
INK = "#e8eaee"
INK_SOFT = "#c9d1dc"
INK_MUTED = "#9aa4b2"
INK_DIM = "#8b95a4"
ACCENT = "#f59e0b"
ACCENT_BRIGHT = "#fbbf24"
ACCENT_INK = "#1a1205"
ACCENT_FILL = "#2a2211"
ACCENT_LINE = "#5a4413"
OK = "#22c55e"
OK_SOFT = "#86efac"
BLUE = "#2563eb"
BLUE_SOFT = "#93b4f8"
IDLE = "#1e242e"
DANGER = "#ef4444"
DANGER_SOFT = "#f87171"
DANGER_FILL = "#2a1215"
DANGER_LINE = "#4a1d22"

FONT_UI = '"Space Grotesk", "Segoe UI Variable Text", "Segoe UI", sans-serif'
FONT_MONO = '"JetBrains Mono", Consolas, "Courier New", monospace'

# Qt's stylesheet subset has no letter-spacing / text-transform, so every
# "uppercase label" below is uppercased in the widget text instead.
STYLESHEET = f"""
QWidget {{
    background: {BG};
    color: {INK};
    font-family: {FONT_UI};
    font-size: 12px;
}}
QMainWindow, QWidget#Central, QScrollArea#CentralScroll {{ background: {BG}; }}
QToolTip {{
    background: {CARD};
    color: {INK};
    border: 1px solid {CONTROL_LINE_HOVER};
    padding: 6px;
}}

QGroupBox {{
    background: {CARD};
    border: 1px solid {CARD_LINE};
    border-radius: 10px;
    margin-top: 12px;
    padding: 12px 10px 10px;
    font-size: 11px;
    color: {INK_MUTED};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    top: 1px;
    padding: 0 4px;
    color: {INK_MUTED};
}}

QPushButton {{
    background: {CONTROL};
    border: 1px solid {CONTROL_LINE};
    border-radius: 8px;
    padding: 7px 10px;
    color: {INK_SOFT};
}}
QPushButton:hover {{
    background: #1b212b;
    border-color: {CONTROL_LINE_HOVER};
    color: {INK};
}}
QPushButton:pressed {{ background: #11151c; }}
QPushButton:disabled {{
    background: #11141a;
    border-color: #1c2229;
    color: #5f6875;
}}
QPushButton#AutoButton {{
    font-size: 14px;
    font-weight: 700;
    min-height: 44px;
    border-radius: 10px;
    background: {ACCENT_FILL};
    border-color: {ACCENT_LINE};
    color: {ACCENT_BRIGHT};
}}
QPushButton#AutoButton:hover {{
    background: #33290f;
    border-color: {ACCENT};
}}
QPushButton#AutoButton:disabled {{
    background: #11141a;
    border-color: #1c2229;
    color: #5f6875;
}}
QPushButton#GhostButton {{
    background: transparent;
    border: 1px solid {CONTROL_LINE};
    border-radius: 7px;
    padding: 5px 10px;
    font-size: 11px;
    color: {INK_MUTED};
}}
QPushButton#GhostButton:hover {{
    background: {CONTROL};
    border-color: {CONTROL_LINE_HOVER};
    color: {INK};
}}
QPushButton#DangerButton {{
    background: transparent;
    border: 1px solid {DANGER_LINE};
    border-radius: 7px;
    padding: 5px 10px;
    font-size: 11px;
    color: {DANGER_SOFT};
}}
QPushButton#DangerButton:hover {{
    background: {DANGER_FILL};
    border-color: {DANGER};
    color: #fecaca;
}}
QPushButton#DangerButton:disabled {{
    border-color: #1c2229;
    color: #5f6875;
}}
QPushButton#AutoButton:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
    color: {ACCENT_INK};
}}
QPushButton#AutoButton:checked:hover {{ background: {ACCENT_BRIGHT}; }}
QPushButton#WorstAutoButton:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
    color: {ACCENT_INK};
}}
QPushButton#WorstAutoButton:checked:hover {{ background: {ACCENT_BRIGHT}; }}
QPushButton[actionButton="true"], QPushButton#WorstAutoButton {{ min-height: 34px; }}

QCheckBox {{ spacing: 8px; color: {INK_SOFT}; background: transparent; }}
QCheckBox:disabled {{ color: #5f6875; }}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border-radius: 5px;
    border: 1px solid {CONTROL_LINE_HOVER};
    background: {CONTROL};
}}
QCheckBox::indicator:hover {{ border-color: {ACCENT_LINE}; }}
QCheckBox::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
}}

QComboBox {{
    background: {CONTROL};
    border: 1px solid {CONTROL_LINE};
    border-radius: 7px;
    padding: 4px 8px;
    min-height: 24px;
    color: {INK};
}}
QComboBox:hover {{ border-color: {CONTROL_LINE_HOVER}; }}
QComboBox::drop-down {{ border: none; width: 18px; }}
QComboBox QAbstractItemView {{
    background: {CARD};
    border: 1px solid {CONTROL_LINE};
    selection-background-color: {ACCENT};
    selection-color: {ACCENT_INK};
    outline: none;
}}

QSpinBox, QDoubleSpinBox {{
    background: {CONTROL};
    border: 1px solid {CONTROL_LINE};
    border-radius: 7px;
    padding: 3px 6px;
    min-height: 22px;
    color: {INK};
}}
QSpinBox:hover, QDoubleSpinBox:hover {{ border-color: {CONTROL_LINE_HOVER}; }}

QPlainTextEdit {{
    background: {BG_SUNKEN};
    border: 1px solid #1a1f28;
    border-radius: 9px;
    padding: 6px;
    color: {INK_SOFT};
    font-family: {FONT_MONO};
    font-size: 11px;
}}

QStatusBar {{
    background: {BG_SUNKEN};
    border-top: 1px solid #1a1f28;
    color: {INK_MUTED};
    font-size: 11px;
    padding-left: 6px;
}}
QStatusBar::item {{ border: none; }}

QScrollBar:vertical {{ background: transparent; width: 9px; margin: 0; }}
QScrollBar::handle:vertical {{
    background: {CONTROL_LINE_HOVER};
    border-radius: 4px;
    min-height: 26px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 9px; margin: 0; }}
QScrollBar::handle:horizontal {{
    background: {CONTROL_LINE_HOVER};
    border-radius: 4px;
    min-width: 26px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

QFrame#Card {{
    background: {CARD};
    border: 1px solid {CARD_LINE};
    border-radius: 10px;
}}
QFrame#CardSunken {{
    background: {BG_SUNKEN};
    border: 1px solid #1a1f28;
    border-radius: 10px;
}}

QLabel {{ background: transparent; }}
QLabel#ModeTitle {{ font-size: 18px; font-weight: 700; color: {INK}; }}
QLabel#KindBadge {{
    background: {ACCENT_FILL};
    border: 1px solid {ACCENT_LINE};
    border-radius: 6px;
    padding: 3px 8px;
    font-size: 11px;
    color: {ACCENT_BRIGHT};
}}
QLabel#Tag {{
    background: #1b212b;
    border: 1px solid #262e3a;
    border-radius: 6px;
    padding: 3px 8px;
    font-size: 11px;
    color: #aeb7c4;
}}
QLabel#RowCaption {{ color: {INK_MUTED}; font-size: 11px; }}
QLabel#RowValue {{ color: #dfe4ea; font-size: 12px; }}
QLabel#Mono {{ color: #96a0ae; font-size: 11px; font-family: {FONT_MONO}; }}
QLabel#HiddenNote {{ color: {INK_DIM}; font-size: 11px; }}
QLabel#StatLabel {{ color: {INK_MUTED}; font-size: 11px; }}
QLabel#StatValue {{
    color: {INK};
    font-size: 17px;
    font-weight: 700;
    font-family: {FONT_MONO};
}}
QLabel#StatValueAccent {{
    color: {ACCENT};
    font-size: 17px;
    font-weight: 700;
    font-family: {FONT_MONO};
}}
QLabel#StatNote {{ color: #96a0ae; font-size: 11px; }}
QLabel#TurnOwner {{ color: {OK}; font-size: 13px; font-weight: 500; }}
QLabel#TurnOwnerIdle {{ color: {INK_MUTED}; font-size: 13px; font-weight: 500; }}
QLabel#TurnClock {{ color: {INK}; font-size: 13px; font-family: {FONT_MONO}; }}
QLabel#AppTitle {{ font-size: 15px; font-weight: 700; color: {INK}; }}
QLabel#AppSubtitle {{ font-size: 11px; color: {INK_DIM}; }}
QLabel#SectionLabel {{
    font-size: 10px;
    font-weight: 600;
    color: {INK_DIM};
    padding: 2px 2px 0;
}}
QLabel#ConnPillOk, QLabel#ConnPillIdle, QLabel#ConnPillBusy {{
    border-radius: 9px;
    padding: 3px 9px;
    font-size: 11px;
    font-weight: 600;
}}
QLabel#ConnPillOk {{
    background: #0f2417;
    border: 1px solid #1f5233;
    color: {OK_SOFT};
}}
QLabel#ConnPillBusy {{
    background: {ACCENT_FILL};
    border: 1px solid {ACCENT_LINE};
    color: {ACCENT_BRIGHT};
}}
QLabel#ConnPillIdle {{
    background: {DANGER_FILL};
    border: 1px solid {DANGER_LINE};
    color: {DANGER_SOFT};
}}
QLabel#EmptyTitle {{ font-size: 14px; font-weight: 600; color: {INK_SOFT}; }}
QLabel#EmptyNote {{ font-size: 11px; color: {INK_DIM}; }}
QFrame#Divider {{ background: {CARD_LINE}; border: none; }}
QLabel#StatusPill {{
    background: #0f2417;
    border: 1px solid #1f5233;
    border-radius: 8px;
    padding: 3px 8px;
    font-size: 11px;
    color: {OK_SOFT};
}}
"""


def apply_theme(application: QtWidgets.QApplication) -> None:
    """Fusion + dark palette + the stylesheet above.

    The palette matters even with a stylesheet: menus, tooltips and the native
    dialogs the launcher opens are not covered by QSS, and on the default
    Windows style they would come back white.
    """
    application.setStyle("Fusion")
    palette = QtGui.QPalette()
    palette.setColor(QtGui.QPalette.Window, QtGui.QColor(BG))
    palette.setColor(QtGui.QPalette.WindowText, QtGui.QColor(INK))
    palette.setColor(QtGui.QPalette.Base, QtGui.QColor(BG_SUNKEN))
    palette.setColor(QtGui.QPalette.AlternateBase, QtGui.QColor(CARD))
    palette.setColor(QtGui.QPalette.ToolTipBase, QtGui.QColor(CARD))
    palette.setColor(QtGui.QPalette.ToolTipText, QtGui.QColor(INK))
    palette.setColor(QtGui.QPalette.Text, QtGui.QColor(INK))
    palette.setColor(QtGui.QPalette.Button, QtGui.QColor(CONTROL))
    palette.setColor(QtGui.QPalette.ButtonText, QtGui.QColor(INK))
    palette.setColor(QtGui.QPalette.Highlight, QtGui.QColor(ACCENT))
    palette.setColor(QtGui.QPalette.HighlightedText, QtGui.QColor(ACCENT_INK))
    palette.setColor(
        QtGui.QPalette.Disabled, QtGui.QPalette.Text, QtGui.QColor("#5f6875")
    )
    palette.setColor(
        QtGui.QPalette.Disabled, QtGui.QPalette.ButtonText, QtGui.QColor("#5f6875")
    )
    application.setPalette(palette)
    application.setStyleSheet(STYLESHEET)
