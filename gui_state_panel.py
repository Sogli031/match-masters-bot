"""Mode-aware replacement for the fixed "Stanje iz memorije" grid.

The old panel printed nine rows on every snapshot, whatever the match was: a
Solo Challenge still carried an opponent score row, a mode without mutations
still carried "Mutacije: -". Here a row exists only while it has something to
say, and the match itself is named (Solo Challenge / Party / Showdown / 1v1)
instead of being implied by a rules id.

The label names (``StateLabel``, ``ScoreLabel``, ...) are deliberately the same
as before: every ``self.XLabel.setText(...)`` call site in memory_gui keeps
working, and this panel decides what the text means for the layout.
"""

from __future__ import annotations

import re

from PyQt5 import QtCore, QtGui, QtWidgets

import gui_theme as theme


# Text the old panel used for "nothing to show". A row carrying one of these is
# hidden instead of printing a dash.
PLACEHOLDERS = {"", "-", "None", "nema snapshota", "nema partije", "no snapshot", "no match"}

# MatchRulesModel.rumbleType, as memory_gui.RUMBLE_TYPE_LABELS reads it.
RUMBLE_TYPE_LABELS = {1: "Classic", 2: "Showdown", 3: "Party"}
# MatchRulesModel.pvpMode: PvP=0, Solo=1, Rumble=2.
PVP_MODE_PVP = 0
PVP_MODE_SOLO = 1
PVP_MODE_RUMBLE = 2


def _is_placeholder(text) -> bool:
    return str(text).strip() in PLACEHOLDERS


def _split_value(text):
    """Split "52  (tura 52)  x2" into a headline and the rest.

    The producing code already separates the headline from its detail with two
    spaces, so nothing has to be re-formatted at the call sites.
    """
    parts = [part for part in re.split(r"\s{2,}", str(text).strip()) if part]
    if not parts:
        return "-", ""
    return parts[0], "  ".join(parts[1:])


class _ValueLabel(QtWidgets.QLabel):
    """QLabel that reports every text change back to the panel."""

    def __init__(self, panel, key, parent=None):
        super().__init__("-", parent)
        self._panel = panel
        self._key = key
        self.setObjectName("RowValue")
        self.setWordWrap(True)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred
        )

    def setText(self, text):  # noqa: N802 - Qt naming
        super().setText(text)
        self._panel.value_changed(self._key, text)


class BoosterMeter(QtWidgets.QWidget):
    """The booster charge as one segment per point, not "7/7" in words."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._charge = 0
        self._maximum = 0
        self.setFixedHeight(6)

    def set_charge(self, charge, maximum):
        self._charge = max(0, int(charge or 0))
        self._maximum = max(0, int(maximum or 0))
        self.update()

    def paintEvent(self, event):  # noqa: N802 - Qt naming
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setPen(QtCore.Qt.NoPen)
        total = self._maximum or 7
        gap = 3
        width = (self.width() - gap * (total - 1)) / float(total)
        full = self._maximum and self._charge >= self._maximum
        for index in range(total):
            if index < self._charge:
                color = theme.ACCENT if full else theme.BLUE
            else:
                color = theme.IDLE
            painter.setBrush(QtGui.QColor(color))
            painter.drawRoundedRect(
                QtCore.QRectF(index * (width + gap), 0, width, self.height()), 2, 2
            )


class StatCard(QtWidgets.QFrame):
    """Headline number with a caption above and a detail line below."""

    def __init__(self, caption, accent=False, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(9, 8, 9, 9)
        layout.setSpacing(2)
        self._caption = QtWidgets.QLabel(caption.upper())
        self._caption.setObjectName("StatLabel")
        self._value = QtWidgets.QLabel("-")
        self._value.setObjectName("StatValueAccent" if accent else "StatValue")
        self._note = QtWidgets.QLabel("")
        self._note.setObjectName("StatNote")
        self._note.setWordWrap(True)
        for widget in (self._caption, self._value, self._note):
            widget.setSizePolicy(
                QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred
            )
            layout.addWidget(widget)

    def set_caption(self, caption):
        self._caption.setText(str(caption).upper())

    def set_value(self, value, note=""):
        self._value.setText(str(value))
        self._note.setText(str(note))
        self._note.setVisible(bool(str(note).strip()))


class MemoryStatePanel(QtWidgets.QWidget):
    """Everything the old state group box showed, arranged by what the mode is.

    Rows are keyed; ``value_changed`` routes each incoming text either into a
    stat card, the booster meter, the turn clock, or a caption/value row that
    hides itself when the text is a placeholder.
    """

    ROWS = (
        ("state", "State"),
        ("mode", "Mode"),
        ("legend", "Legend"),
        ("perks", "Perks"),
        ("mutations", "Mutations"),
        ("booster_name", "Booster"),
        ("ufo_eyes", "UFO Eyes"),
        ("snapshot", "Snapshot"),
    )
    # Rows that are part of the match regardless of mode; the rest only show up
    # when the snapshot actually carries them, and get listed as hidden.
    ALWAYS = {"state", "mode"}
    # Booster-specific rows: hidden with every other booster, and not worth a
    # "nema u ovom modu" mention there.
    UNLISTED = {"ufo_eyes"}

    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        # --- empty state --------------------------------------------------
        # Between matches every card below would only carry dashes, so they
        # step aside for one card that says what the panel is waiting for.
        empty = QtWidgets.QFrame()
        empty.setObjectName("Card")
        empty_layout = QtWidgets.QVBoxLayout(empty)
        empty_layout.setContentsMargins(14, 18, 14, 18)
        empty_layout.setSpacing(4)
        empty_title = QtWidgets.QLabel("Waiting for a match")
        empty_title.setObjectName("EmptyTitle")
        empty_title.setAlignment(QtCore.Qt.AlignCenter)
        empty_note = QtWidgets.QLabel(
            "Start a match in BlueStacks. Score, moves and booster appear here "
            "as soon as the reader sees the board."
        )
        empty_note.setObjectName("EmptyNote")
        empty_note.setAlignment(QtCore.Qt.AlignCenter)
        empty_note.setWordWrap(True)
        empty_layout.addWidget(empty_title)
        empty_layout.addWidget(empty_note)
        self._empty_card = empty
        outer.addWidget(empty)

        # --- match header -------------------------------------------------
        header = QtWidgets.QFrame()
        header.setObjectName("Card")
        header_layout = QtWidgets.QVBoxLayout(header)
        header_layout.setContentsMargins(12, 10, 12, 11)
        header_layout.setSpacing(8)
        title_row = QtWidgets.QHBoxLayout()
        title_row.setSpacing(8)
        self.ModeTitle = QtWidgets.QLabel("No Match")
        self.ModeTitle.setObjectName("ModeTitle")
        self.ModeTitle.setSizePolicy(
            QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred
        )
        self.KindBadge = QtWidgets.QLabel("-")
        self.KindBadge.setObjectName("KindBadge")
        title_row.addWidget(self.ModeTitle, 1)
        title_row.addWidget(self.KindBadge, 0, QtCore.Qt.AlignRight)
        header_layout.addLayout(title_row)
        self._tag_row = QtWidgets.QHBoxLayout()
        self._tag_row.setSpacing(5)
        self._tag_row.addStretch(1)
        self._tags = []
        header_layout.addLayout(self._tag_row)
        self._header_card = header
        outer.addWidget(header)

        # --- turn + clock -------------------------------------------------
        turn_card = QtWidgets.QFrame()
        turn_card.setObjectName("Card")
        turn_layout = QtWidgets.QVBoxLayout(turn_card)
        turn_layout.setContentsMargins(12, 9, 12, 11)
        turn_layout.setSpacing(8)
        turn_top = QtWidgets.QHBoxLayout()
        self.TurnLabel = _ValueLabel(self, "turn")
        self.TurnLabel.setObjectName("TurnOwner")
        self.TurnLabel.setWordWrap(False)
        self.TurnLabel.setToolTip(
            "Whose turn it is and how many seconds remain. The time is the "
            "engine's own countdown (GameLogic.RemainingTime), adjusted for "
            "snapshot age, not an estimate from the start of the turn."
        )
        self.TurnClock = QtWidgets.QLabel("-")
        self.TurnClock.setObjectName("TurnClock")
        turn_top.addWidget(self.TurnLabel, 1)
        turn_top.addWidget(self.TurnClock, 0, QtCore.Qt.AlignRight)
        turn_layout.addLayout(turn_top)
        self.TurnBar = QtWidgets.QProgressBar()
        self.TurnBar.setObjectName("TurnBar")
        self.TurnBar.setTextVisible(False)
        self.TurnBar.setRange(0, 100)
        self.TurnBar.setValue(0)
        self.TurnBar.setFixedHeight(4)
        self._style_turn_bar(mine=False)
        turn_layout.addWidget(self.TurnBar)
        self._turn_card = turn_card
        outer.addWidget(turn_card)

        # --- score / moves / rounds --------------------------------------
        self._stats_row = QtWidgets.QWidget()
        stats = QtWidgets.QHBoxLayout(self._stats_row)
        stats.setContentsMargins(0, 0, 0, 0)
        stats.setSpacing(8)
        self.ScoreCard = StatCard("Score", accent=True)
        self.MovesCard = StatCard("Moves")
        self.RoundCard = StatCard("Turn")
        for card in (self.ScoreCard, self.MovesCard, self.RoundCard):
            stats.addWidget(card, 1)
        outer.addWidget(self._stats_row)

        # --- booster ------------------------------------------------------
        booster_card = QtWidgets.QFrame()
        booster_card.setObjectName("Card")
        booster_layout = QtWidgets.QVBoxLayout(booster_card)
        booster_layout.setContentsMargins(12, 9, 12, 11)
        booster_layout.setSpacing(8)
        booster_top = QtWidgets.QHBoxLayout()
        booster_caption = QtWidgets.QLabel("BOOSTER")
        booster_caption.setObjectName("StatLabel")
        booster_caption.setToolTip(
            "Booster is identified from memory (in-game name, then type). "
            "Targeting is enabled only for boosters the bot knows how to aim; "
            "for others, activation proceeds without clicking a target."
        )
        self.BoosterLabel = _ValueLabel(self, "booster")
        self.BoosterLabel.setObjectName("TurnClock")
        self.BoosterLabel.setWordWrap(False)
        booster_top.addWidget(booster_caption, 0)
        booster_top.addStretch(1)
        booster_top.addWidget(self.BoosterLabel, 0, QtCore.Qt.AlignRight)
        booster_layout.addLayout(booster_top)
        self.BoosterMeter = BoosterMeter()
        booster_layout.addWidget(self.BoosterMeter)
        self._booster_card = booster_card
        outer.addWidget(booster_card)

        # --- dynamic rows -------------------------------------------------
        # Retain label sinks for snapshot updates without showing diagnostics.
        rows_card = QtWidgets.QFrame(self)
        rows_card.setObjectName("Card")
        rows_layout = QtWidgets.QGridLayout(rows_card)
        rows_layout.setContentsMargins(12, 10, 12, 10)
        rows_layout.setHorizontalSpacing(8)
        rows_layout.setVerticalSpacing(5)
        rows_layout.setColumnStretch(1, 1)
        self._captions = {}
        self._values = {}
        for index, (key, caption) in enumerate(self.ROWS):
            caption_label = QtWidgets.QLabel(caption)
            caption_label.setObjectName("RowCaption")
            caption_label.setMinimumWidth(62)
            value_label = _ValueLabel(self, key)
            if key == "snapshot":
                value_label.setObjectName("Mono")
            rows_layout.addWidget(caption_label, index, 0, QtCore.Qt.AlignTop)
            rows_layout.addWidget(value_label, index, 1)
            self._captions[key] = caption_label
            self._values[key] = value_label
        self._rows_card = rows_card
        rows_card.hide()

        self.HiddenNote = QtWidgets.QLabel("")
        self.HiddenNote.setObjectName("HiddenNote")
        self.HiddenNote.setWordWrap(True)
        self.HiddenNote.setVisible(False)
        outer.addWidget(self.HiddenNote)

        # Names memory_gui already writes to.
        self.StateLabel = self._values["state"]
        self.ModeLabel = self._values["mode"]
        self.LegendLabel = self._values["legend"]
        self.PerksLabel = self._values["perks"]
        self.MutationsLabel = self._values["mutations"]
        self.BoosterNameLabel = self._values["booster_name"]
        self.UfoEyesLabel = self._values["ufo_eyes"]
        self.FreshLabel = self._values["snapshot"]
        self.ScoreLabel = _ValueLabel(self, "score")
        self.MovesLabel = _ValueLabel(self, "moves")
        for hidden in (self.ScoreLabel, self.MovesLabel):
            hidden.setVisible(False)
            hidden.setParent(self)

        self._time_per_turn = None
        self._turn_mine = False
        self._booster_locked = False
        self._idle = True
        for key, _caption in self.ROWS:
            self._apply_row_visibility(key)
        self._set_idle(True)

    # ------------------------------------------------------------- routing --

    def value_changed(self, key, text):
        text = "" if text is None else str(text)
        if key == "score":
            value, note = _split_value(text)
            self.ScoreCard.set_value(value, note)
            return
        if key == "moves":
            value, note = _split_value(text)
            self.MovesCard.set_value(value, note)
            return
        if key == "booster":
            self._update_booster(text)
            return
        if key == "turn":
            self._update_turn(text)
            return
        self._apply_row_visibility(key)
        self._refresh_hidden_note()

    def _update_booster(self, text):
        match = re.search(r"(\d+)\s*/\s*(\d+)", text)
        if match is None:
            self.BoosterLabel.setVisible(bool(text.strip()))
            self.BoosterMeter.set_charge(0, 0)
            return
        charge, maximum = int(match.group(1)), int(match.group(2))
        self.BoosterMeter.set_charge(charge, maximum)
        full = maximum and charge >= maximum
        self.BoosterLabel.setVisible(True)
        self.BoosterLabel.setStyleSheet(
            "color:%s;" % (theme.ACCENT if full else theme.BLUE_SOFT)
        )

    def _update_turn(self, text):
        mine = text.startswith("moj potez") or text.startswith("my turn")
        self.TurnLabel.setObjectName("TurnOwner" if mine else "TurnOwnerIdle")
        self.TurnLabel.style().unpolish(self.TurnLabel)
        self.TurnLabel.style().polish(self.TurnLabel)
        owner, detail = _split_value(text)
        # Base setText on purpose: routing through _ValueLabel.setText here
        # would call back into this method for the same value.
        QtWidgets.QLabel.setText(self.TurnLabel, owner)
        seconds = re.search(r"([0-9]+(?:\.[0-9])?)\s*s\b", detail)
        if seconds is None:
            self.TurnClock.setText(detail.strip("()") or "-")
            self.TurnBar.setValue(100 if mine else 0)
        else:
            left = float(seconds.group(1))
            self.TurnClock.setText("%.1fs" % left)
            span = float(self._time_per_turn or 0) or max(left, 1.0)
            self.TurnBar.setValue(int(max(0.0, min(1.0, left / span)) * 100))
        self._style_turn_bar(mine)

    def _style_turn_bar(self, mine):
        chunk = theme.OK if mine else theme.INK_MUTED
        self.TurnBar.setStyleSheet(
            "QProgressBar#TurnBar{background:%s;border:none;border-radius:2px;}"
            "QProgressBar#TurnBar::chunk{background:%s;border-radius:2px;}"
            % (theme.IDLE, chunk)
        )
        self._turn_mine = mine

    # ---------------------------------------------------------- visibility --

    def _apply_row_visibility(self, key):
        value = self._values[key]
        visible = not _is_placeholder(value.text())
        value.setVisible(visible)
        self._captions[key].setVisible(visible)
        self._refresh_rows_card()

    def _refresh_rows_card(self):
        # Technical details stay out of the main match controls, including
        # after snapshot updates and transitions back from the empty state.
        self._rows_card.hide()

    def _set_idle(self, idle):
        """Swap the match cards for the empty-state card, or back."""
        self._idle = idle
        self._empty_card.setVisible(idle)
        for widget in (self._header_card, self._turn_card, self._stats_row):
            widget.setVisible(not idle)
        self._booster_card.setVisible(not idle and not self._booster_locked)
        self._refresh_rows_card()
        self._refresh_hidden_note()

    def _refresh_hidden_note(self):
        # Read from the text, not from isVisible(): before the window is shown
        # every child reports itself invisible, which would list every optional
        # row as missing on the first snapshot.
        hidden = [
            caption.lower()
            for key, caption in self.ROWS
            if key not in self.ALWAYS
            and key != "snapshot"
            and key not in self.UNLISTED
            and _is_placeholder(self._values[key].text())
        ]
        # Kept as a tooltip on the rows card instead of a line of its own:
        # useful when checking a mode, noise the rest of the time.
        self.HiddenNote.setVisible(False)
        note = "Not in this mode: " + ", ".join(hidden) if hidden else ""
        self.HiddenNote.setText(note)
        self._rows_card.setToolTip(note)

    # --------------------------------------------------------------- match --

    def match_kind_label(self, rules, players):
        """Name the match the way the engine describes it.

        pvpMode is the only field that says what a match *is* (PvP=0 is a real
        1v1, Solo=1 and Rumble=2 are point races), and rumbleType separates a
        Rumble into Classic/Showdown/Party. A league match reports its stage id
        with a "-master-league" suffix.
        """
        rules = rules or {}
        rules_id = str(rules.get("id") or "")
        if rules_id.endswith("-master-league"):
            return "Master League"
        pvp_mode = rules.get("pvp_mode")
        rumble = rules.get("rumble_type")
        if pvp_mode == PVP_MODE_RUMBLE or rumble in (2, 3):
            return RUMBLE_TYPE_LABELS.get(rumble, "Rumble")
        if pvp_mode == PVP_MODE_SOLO:
            return "Solo Challenge"
        if pvp_mode == PVP_MODE_PVP:
            return "1v1"
        if len(players or ()) > 1:
            return "1v1"
        return "Solo Challenge"

    def update_match(self, rules, players, state, me=None):
        """Title, badge and tags for the match now running."""
        rules = rules or {}
        state = state or {}
        players = list(players or ())
        self._time_per_turn = rules.get("time_per_turn")
        title = rules.get("title") or rules.get("id") or "No Match"
        self.ModeTitle.setText(str(title))
        self.KindBadge.setText(self.match_kind_label(rules, players))
        self.KindBadge.setVisible(True)

        tags = []
        size = rules.get("board_size")
        if size:
            tags.append("%sx%s" % (int(size), int(size)))
        moves_per_turn = rules.get("moves_per_turn")
        if moves_per_turn:
            tags.append("%s moves / turn" % int(moves_per_turn))
        if not rules.get("time_per_turn"):
            tags.append("no timer")
        if len(players) > 2:
            tags.append("%s players" % len(players))
        multiplier = (me or {}).get("score_multiplier")
        try:
            multiplier = int(multiplier)
        except (TypeError, ValueError):
            multiplier = 1
        if multiplier > 1:
            tags.append("x%s score" % multiplier)
        if rules.get("ability_locked"):
            tags.append("booster locked")
        self._set_tags(tags)

        # Third card: turns while a match has several, rounds otherwise. In a
        # single-turn single-round match it carries nothing, so it goes away.
        turns_total = state.get("turns_total")
        rounds_total = state.get("rounds_total")
        if turns_total and int(turns_total) > 1:
            self.RoundCard.set_caption("Turn")
            note = (
                "round %s/%s" % (state.get("rounds"), rounds_total)
                if rounds_total and int(rounds_total) > 1
                else ""
            )
            self.RoundCard.set_value(
                "%s/%s" % (state.get("turns"), turns_total), note
            )
            self.RoundCard.setVisible(True)
        elif rounds_total and int(rounds_total) > 1:
            self.RoundCard.set_caption("Round")
            self.RoundCard.set_value(
                "%s/%s" % (state.get("rounds"), rounds_total), ""
            )
            self.RoundCard.setVisible(True)
        else:
            self.RoundCard.setVisible(False)

        # A locked booster has no meter to show.
        self._booster_locked = bool(rules.get("ability_locked"))
        self._set_idle(False)

    def _set_tags(self, tags):
        for label in self._tags:
            self._tag_row.removeWidget(label)
            label.deleteLater()
        self._tags = []
        for text in tags:
            label = QtWidgets.QLabel(str(text))
            label.setObjectName("Tag")
            self._tag_row.insertWidget(len(self._tags), label)
            self._tags.append(label)

    def reset(self):
        """Back to "no match" without waiting for the next snapshot."""
        self.ModeTitle.setText("No Match")
        self.KindBadge.setText("-")
        self.KindBadge.setVisible(False)
        self._set_tags([])
        self.ScoreCard.set_value("-", "")
        self.MovesCard.set_value("-", "")
        self.RoundCard.setVisible(False)
        self.BoosterMeter.set_charge(0, 0)
        self.BoosterLabel.setText("-")
        QtWidgets.QLabel.setText(self.TurnLabel, "-")
        self.TurnClock.setText("-")
        self.TurnBar.setValue(0)
        for key, _caption in self.ROWS:
            self._values[key].setText("-")
        self._booster_locked = False
        self._set_idle(True)
