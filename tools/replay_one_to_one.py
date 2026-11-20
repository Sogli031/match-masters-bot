"""Replay a research recording 1:1: the recorded action, board, specials, RNG, points and charge.

    python tools/replay_one_to_one.py [Debug/research/FOLDER]   (bez argumenta: poslednji)

Unlike analyze_research (which searches every swap for one that matches the
board), this plays exactly the action the bot sent (refill_input of the later
record) and compares everything the game shows: board, specials, RNG counter,
score gained and the booster meter. Report: screen and FOLDER/replay_1na1.txt.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from simulator_capture import capture_mode, lab_move, resolve_refill_overrides
from tools.analyze_research import grid, load, local_player, observed

PERK_ACTIONS = {"energy_boost": "energy_boost", "teleport": "teleport"}


def recorded_action(record):
    """The simulator action for the input that led to ``record``, or (None, why)."""
    marker = record.get("refill_input")
    detail = marker[2] if isinstance(marker, (list, tuple)) and len(marker) > 2 else None
    if not isinstance(detail, dict):
        return None, "nema zapisane akcije"
    kind = detail.get("action")
    if kind == "move":
        return {"start": list(detail["start"]), "target": list(detail["target"]),
                "direction": detail["direction"]}, None
    if kind == "activate_booster":
        action = {"kind": "booster"}
        if detail.get("booster_color") is not None:
            action["color"] = int(detail["booster_color"])
        return action, None
    if detail.get("manual"):
        return None, f"rucni {kind} {detail.get('perk') or ''} (bez zapisanog poteza)".strip()
    if kind == "activate_perk" and detail.get("perk") == "remove_cross" and detail.get("perk_target"):
        # follow_up is the swipe planned after the perk: it lands in the next
        # record (both recordings 2026-11-19/20: the perk alone is exact).
        return {"kind": "remove_cross", "cell": list(detail["perk_target"])}, None
    if kind == "activate_perk" and detail.get("perk") in PERK_ACTIONS and detail.get("follow_up"):
        follow = detail["follow_up"]
        start, target = list(follow["start"]), list(follow["target"])
        direction = _direction(start, target)
        return {"kind": PERK_ACTIONS[detail["perk"]], "start": start, "target": target,
                "direction": direction}, None
    return None, f"akcija {kind} {detail.get('perk') or ''} nije u simulatoru".strip()


def _direction(start, target):
    dr, dc = target[0] - start[0], target[1] - start[1]
    return {(0, 1): "right", (0, -1): "left", (1, 0): "down", (-1, 0): "up"}.get((dr, dc), "right")


def replay(rec_a, cap_a, rec_b):
    """dict with the per-field comparison, or {'skip': reason}."""
    from strategy_lab import simulation

    before, after_marker = rec_a.get("refill_input"), rec_b.get("refill_input")
    if (isinstance(before, (list, tuple)) and isinstance(after_marker, (list, tuple))
            and before and after_marker and before[0] == after_marker[0]):
        # The bot's input counter did not move: the opponent's move, or ours by hand.
        theirs = [p for p in (rec_b.get("snapshot_state") or {}).get("players") or ()
                  if p.get("player_type") != 0]
        before_theirs = [p for p in (rec_a.get("snapshot_state") or {}).get("players") or ()
                         if p.get("player_type") != 0]
        if theirs and before_theirs and theirs[0].get("score") != before_theirs[0].get("score"):
            return {"skip": "protivnikov potez"}
        return {"skip": "rucni potez (bot nije slao akciju)"}
    action, why = recorded_action(rec_b)
    if action is None:
        return {"skip": why}
    certified = simulation.PREFIX_MODES
    simulation.PREFIX_MODES = set(certified) | {capture_mode(cap_a["profile"]).value}
    try:
        resolved = resolve_refill_overrides(cap_a["profile"])
        thresholds = None if resolved.get("resolved") else next(
            iter((resolved.get("threshold_hypotheses") or {None: None}).values()))
        lab = lab_move(cap_a, thresholds=thresholds)
        lab["check_cascade_timing"] = True
        gained = 0.0
        for one in action if isinstance(action, list) else [action]:
            if one.get("kind") == simulation.REMOVE_CROSS:
                lab["perks"] = {simulation.PERK_REMOVE_CROSS: 1}
            if one.get("kind") in PERK_ACTIONS.values():
                lab["perks"] = {simulation.PERK_ENERGY_BOOST if one["kind"] == "energy_boost"
                                else simulation.PERK_TELEPORT: 1}
            result = simulation.step(lab, one)
            if not result.get("supported"):
                return {"skip": f"simulator ({one.get('kind', 'swap')}): {result.get('reason')}"}
            gained += result.get("score_gain") or 0
            lab = result["state"]
        result = dict(result, score_gain=gained)
    except Exception as exc:
        return {"skip": f"{type(exc).__name__}: {exc}"}
    finally:
        simulation.PREFIX_MODES = certified
    after = result["state"]
    want = observed(rec_b)
    board, special = grid(after["board"]), grid(after["special_board"])
    me_a, me_b = local_player(rec_a), local_player(rec_b)
    charge = (after.get("booster_state") or {}).get("current")
    return {
        "action": action,
        "cells": sum(board[r][c] != want["board"][r][c] for r in range(len(board)) for c in range(len(board[r]))),
        "specials": sum(special[r][c] != want["special_board"][r][c]
                        for r in range(len(special)) for c in range(len(special[r]))),
        "rng": (want["rng"], after["engine_refill"].rng.counter),
        "points": ((me_b.get("score") or 0) - (me_a.get("score") or 0), result.get("score_gain")),
        "charge": (me_b.get("energy"), charge),
        "moves": (want["moves"], (after.get("turn_state") or {}).get("remaining_moves")),
    }


def analyze(folder: Path) -> str:
    files = sorted(folder.glob("[0-9][0-9][0-9].json"))
    lines = [f"Sesija: {folder.name}, snimaka: {len(files)}"]
    exact = total = 0
    for a, b in zip(files, files[1:]):
        rec_a, cap_a = load(a)
        rec_b, _ = load(b)
        head = f"{a.stem}->{b.stem}"
        got = replay(rec_a, cap_a, rec_b)
        total += 1
        if "skip" in got:
            lines.append(f"{head}: NIJE PROVERENO - {got['skip']}")
            continue
        wrong = [name for name, pair in (("rng", got["rng"]), ("poeni", got["points"]),
                                         ("punjenje", got["charge"]), ("potezi", got["moves"]))
                 if pair[0] is not None and pair[0] != pair[1]]
        if got["cells"]:
            wrong.insert(0, f"tabla {got['cells']} polja")
        if got["specials"]:
            wrong.insert(1, f"specijali {got['specials']}")
        exact += not wrong
        detail = (f"poeni igra/sim {got['points'][0]}/{got['points'][1]}, "
                  f"punjenje {got['charge'][0]}/{got['charge'][1]}, rng {got['rng'][0]}/{got['rng'][1]}, "
                  f"potezi {got['moves'][0]}/{got['moves'][1]}")
        lines.append(f"{head}: {'1:1' if not wrong else 'RAZLIKA: ' + ', '.join(wrong)}  ({detail})")
    lines.append("")
    lines.append(f"UKUPNO: 1:1 u {exact} od {total} prelaza")
    return "\n".join(lines)


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    folder = Path(args[0]) if args else max((ROOT / "Debug/research").iterdir(), key=lambda p: p.name)
    text = analyze(folder)
    (folder / "replay_1na1.txt").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
