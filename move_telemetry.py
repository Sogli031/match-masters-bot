"""One compact line per played move, always on.

The charge economy in ``move_strategy`` is measured rather than guessed
(``tools/measure_charge_value.py``), and until now the only source for that
measurement was a full ``Debug/runs`` recording -- screenshots, overlays, the
board before and after, a directory per move. That is the right tool for
"what exactly did this move do", but it is far too heavy to leave on, so the
calibration data only ever accumulated during a deliberate debugging session.

This is the other half: the handful of numbers the calibration actually reads,
appended to a single JSONL file on every move, with no images and no directory.
About 250 bytes a move -- a thousand moves is a quarter of a megabyte -- so it
can simply stay on and the sample grows by playing.

Each line pairs a move's *prediction* with what the game then did:

* ``before``/``after`` -- booster charge, our score and the move counter, read
  out of the game by the memory path. The "after" of a move is the "before" of
  the next one, so a line is only complete on the following decision; the last
  move of a session is dropped, which is one move per session and costs nothing.
* ``pred`` -- what the simulator thought the move was worth. Comparing the two
  is what turns "this weight feels high" into a number.

Deliberately *not* recorded: anything that identifies the account, anything
about the opponent beyond their score, and the board itself. This file is for
weights, not for replaying matches -- that is what Debug runs are for.
"""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_TELEMETRY_PATH = PROJECT_ROOT / "Debug" / "telemetry" / "moves.jsonl"
# Rotated, not truncated: the old file becomes ``moves.1.jsonl`` and the
# previous rotation is dropped. At ~250 bytes a move this holds a few hundred
# thousand moves before it ever triggers.
MAX_BYTES = 16 * 1024 * 1024

# Decisions that change the game state, and so are worth a line of their own.
# A booster activation is not a move but it is the *only* place the booster's
# score shows up -- without it the log could never say what a full meter buys,
# which is the whole number the calibration is after.
ACTING_DECISIONS = frozenset({"move", "activate_booster", "activate_perk"})

_enabled = True
_path = DEFAULT_TELEMETRY_PATH
# The move waiting for the game's answer: its prediction and the meters as they
# stood before it was played.
_pending: dict | None = None


def configure(path: object = None, enabled: bool | None = None) -> None:
    """Point the log somewhere else, or switch it off."""
    global _path, _enabled, _pending
    if path is not None:
        _path = Path(path)
        _pending = None
    if enabled is not None:
        _enabled = bool(enabled)


def reset() -> None:
    """Forget the move waiting to be closed.

    Called when the match changes: pairing a move from one match with the
    meters of another would invent a delta out of a reset score.
    """
    global _pending
    _pending = None


def _meters(state: object) -> dict | None:
    """The three numbers that matter, out of a resolved screen/memory state."""
    if not isinstance(state, dict):
        return None
    resolved = state.get("resolved")
    if not isinstance(resolved, dict):
        return None
    charge = resolved.get("booster_charge")
    score = resolved.get("our_score")
    if charge is None or score is None:
        # Without both there is no delta to measure, and a half-read line would
        # have to be filtered out by every reader instead.
        return None
    meters = {"charge": int(charge), "score": int(score)}
    for source, target in (
        ("booster_maximum", "max"),
        ("remaining_moves", "moves"),
        ("current_round", "round"),
        ("opponent_score", "opponent"),
    ):
        value = resolved.get(source)
        if value is not None:
            meters[target] = int(value)
    return meters


def _prediction(evaluation: object) -> dict:
    fields = (
        ("instant", "instant_score"),
        ("score", "score"),
        ("blue", "blue_cells"),
        ("blue_pot", "blue_potential"),
        ("jelly_charge", "jelly_charge_cells"),
        ("extra", "extra_moves"),
        ("direct_extra", "direct_extra_moves"),
        ("cascades", "cascade_count"),
        ("cleared", "cleared_cells"),
    )
    prediction: dict = {}
    for label, attribute in fields:
        value = getattr(evaluation, attribute, None)
        if value is None:
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        prediction[label] = round(number, 2)
    return prediction


def _append(line: dict) -> None:
    try:
        _path.parent.mkdir(parents=True, exist_ok=True)
        if _path.exists() and _path.stat().st_size > MAX_BYTES:
            rotated = _path.with_name(_path.stem + ".1" + _path.suffix)
            if rotated.exists():
                rotated.unlink()
            os.replace(_path, rotated)
        with _path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(line, ensure_ascii=False, separators=(",", ":")))
            handle.write("\n")
    except OSError:
        # Telemetry must never be the reason a move does not get played.
        pass


def record(
    *,
    screen_state_read: object,
    evaluation: object = None,
    strategy_mode: object = None,
    game_mode: object = None,
    selected_action: object = None,
    decision_gate: object = None,
) -> None:
    """Close the previous move with these meters, then hold this one open.

    Safe to call on every decision, including ones that play nothing: a blocked
    frame still carries a valid meter reading and so still closes the action
    before it. What it will not do is open a new pending entry for a decision
    that changed nothing, because the next delta would then be attributed to
    something that never happened.
    """
    global _pending
    if not _enabled:
        return
    meters = _meters(screen_state_read)
    if meters is None:
        return

    if _pending is not None:
        line = dict(_pending)
        line["after"] = meters
        _pending = None
        _append(line)

    if str(selected_action) not in ACTING_DECISIONS:
        return
    _pending = {
        "t": dt.datetime.now().isoformat(timespec="seconds"),
        "ctx": _context_name(strategy_mode),
        "mode": None if game_mode is None else str(game_mode),
        "action": None if selected_action is None else str(selected_action),
        "gate": None if decision_gate is None else str(decision_gate),
        "before": meters,
        "pred": {} if evaluation is None else _prediction(evaluation),
    }


def _context_name(strategy_mode: object) -> str | None:
    if strategy_mode is None:
        return None
    mode = getattr(strategy_mode, "mode", strategy_mode)
    return str(mode)
