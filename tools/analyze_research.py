"""Analiza istrazivacke sesije: da li simulator reprodukuje svaki odigran potez.

    python tools/analyze_research.py [Debug/research/FOLDER]   (bez argumenta: poslednji)

Za svaki par uzastopnih snimaka (pre i posle jednog poteza) probaju se svi
legalni swap-ovi iz stanja "pre" sa portovanom dopunom (engine_refill); van
poslednje runde i sve hipoteze pragova. Poklapanje mora biti na tabli,
specijalima i RNG brojacu. Izvestaj ide na ekran i u FOLDER/analiza.txt.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine_refill import UnsupportedRefill
from simulator_capture import capture_mode, decode_dictionary, lab_move, resolve_refill_overrides
from tools.verify_refill import describe_capture, format_info


def load(path):
    record = json.loads(Path(path).read_text(encoding="utf-8"))
    return record, capture_from(record)


def capture_from(record):
    profile = record["profile"]
    if record.get("raw_slots"):
        # Recordings made before a piece joined _ball_slots (the Sweep SE
        # broom, 2026-11-07) still carry its colour in the raw slots.
        from square_solo_live import _ball_slots
        profile = dict(profile, ball_slots=_ball_slots({"slots": record["raw_slots"]}))
    import board_source
    score = decode_dictionary((profile.get("rules") or {}).get("_colorScoreOverride")) or {}
    capture = {"profile": profile, "simulator_input": {
        "board": record["board"], "special_board": record["special_board"],
        "froggy_params": local_player(record).get("special_ability_params"),
        "active_mutations": record.get("active_mutations"),
        "cell_types": record.get("cell_types"),
        "booster_cost": local_player(record).get("energy_to_ability"),
        "mixy_player": local_player(record),
        "score_rally_values": {str(board_source.slot_color_to_board(k)): v for k, v in score.items()}}}
    if record.get("billie_slots"):
        from engine_billie import BilliePassive
        try:
            capture["simulator_input"]["billie"] = BilliePassive.from_record(record)
        except UnsupportedRefill:
            pass
    return capture


def grid(board):
    return [[int(v) for v in row] for row in board]


def observed(record):
    return {"board": grid(record["board"]), "special_board": grid(record["special_board"]),
            "rng": record["profile"]["rng"]["<counter>k__BackingField"],
            "rng_state": record["profile"]["rng"],
            "moves": record["profile"]["state"].get("moves")}


def local_player(record):
    players = (record.get("snapshot_state") or {}).get("players") or []
    return next((p for p in players if p.get("player_type") == 0), {})


def booster_used(rec_a, rec_b):
    """The local booster fired between the two boards: full energy spent,
    or the engine's own flag. Returns the booster's name or None."""
    before, after = local_player(rec_a), local_player(rec_b)
    spent = before.get("energy_full") and (after.get("energy") or 0) < (before.get("energy") or 0)
    if not spent and not after.get("is_ability_used_this_move"):
        return None
    import memory_gui
    kind = before.get("special_ability_type")
    return memory_gui.SPECIAL_ABILITY_NAMES.get(kind, f"tip {kind}")


def show_boards(a, b):
    rows = []
    for left, right in zip(a, b):
        rows.append("      " + " ".join(f"{v:2d}" for v in left) + "   |  " + " ".join(f"{v:2d}" for v in right))
    return ["      pre" + " " * 18 + "|  posle"] + rows


def try_transition(before_capture, want, perks=None):
    """(matches, closest) over every swap and threshold hypothesis."""
    from strategy_lab import planner, simulation

    # A measurement may inspect a mode not certified for planning, as
    # refill_monitor and verify_billie do. Restored on the way out.
    certified = simulation.PREFIX_MODES
    simulation.PREFIX_MODES = set(certified) | {capture_mode(before_capture["profile"]).value}
    try:
        return _try_transition(before_capture, want, perks, planner, simulation.step)
    finally:
        simulation.PREFIX_MODES = certified


def _try_transition(before_capture, want, perks, planner, step):
    resolved = resolve_refill_overrides(before_capture["profile"])
    hypotheses = ({None: None} if resolved.get("resolved")
                  else dict(resolved.get("threshold_hypotheses") or {}))
    matches, closest, reasons = [], None, Counter()
    for name, thresholds in hypotheses.items():
        try:
            lab = lab_move(before_capture, thresholds=thresholds)
        except UnsupportedRefill as exc:
            reasons[f"dopuna: {exc}"] += 1
            continue
        lab["perks"] = dict(perks or {})
        for action in planner.actions(lab):
            if action.get("kind", "swap") not in ("swap", "energy_boost", "teleport"):
                continue
            result = step(lab, action)
            if not result.get("supported"):
                reasons[result.get("reason")] += 1
                continue
            after = result["state"]
            got = {"board": grid(after["board"]), "special_board": grid(after["special_board"]),
                   "rng": after["engine_refill"].rng.counter}
            cells = [(r, c, want["board"][r][c], got["board"][r][c])
                     for r in range(len(got["board"])) for c in range(len(got["board"][r]))
                     if want["board"][r][c] != got["board"][r][c]]
            specials = sum(want["special_board"][r][c] != got["special_board"][r][c]
                           for r in range(len(got["board"])) for c in range(len(got["board"][r])))
            cleo = any(lab["special_board"][r][c] == 13
                       for r, c in (action.get("start", (-1, -1)), action.get("target", (-1, -1)))
                       if r >= 0 and c >= 0)
            strict = True
            if cleo:
                rng_state = after["engine_refill"].rng.to_capture()
                strict = (all((want.get("rng_state") or {}).get(k) == v for k, v in rng_state.items())
                          and want.get("moves") is not None
                          and after.get("turn_state", {}).get("remaining_moves") == want["moves"])
            if not cells and not specials and got["rng"] == want["rng"] and strict:
                matches.append((planner.describe(action), name))
                continue
            distance = len(cells) + specials + (got["rng"] != want["rng"])
            if closest is None or distance < closest["distance"]:
                closest = {"distance": distance, "action": planner.describe(action), "hypothesis": name,
                           "rng": (want["rng"], got["rng"]), "cells": cells[:10], "specials": specials,
                           "refills": [len(t) for t in result["refills"]]}
    return matches, closest, reasons


def analyze(folder: Path) -> str:
    files = sorted(folder.glob("[0-9][0-9][0-9].json"))
    if len(files) < 2:
        return f"{folder}: premalo snimaka ({len(files)})"
    lines = []
    first = load(files[0])[1]
    lines.append(f"Sesija: {folder.name}, snimaka: {len(files)}")
    lines.append(format_info(describe_capture(first)))
    tally = Counter()
    hypothesis_hits = Counter()
    for a, b in zip(files, files[1:]):
        rec_a, cap_a = load(a)
        rec_b, _ = load(b)
        want = observed(rec_b)
        head = f"{a.stem}->{b.stem} (potezi {observed(rec_a)['moves']}->{want['moves']}, rng {observed(rec_a)['rng']}->{want['rng']})"
        if rec_a["profile"]["rng"].get("_seed") != rec_b["profile"]["rng"].get("_seed"):
            lines.append(f"{head}: nova partija")
            continue
        if rec_b.get("missed_board_before"):
            tally["preskocen"] += 1
            lines.append(f"{head}: preskocen potez, nema table pre njega")
            continue
        if observed(rec_a)["rng"] == want["rng"] and observed(rec_a)["board"] == want["board"]:
            lines.append(f"{head}: nista se nije desilo")
            continue
        booster = booster_used(rec_a, rec_b)
        if booster is not None:
            tally["booster"] += 1
            lines.append(f"{head}: BOOSTER {booster} - nije portovan u simulator "
                         f"({want['rng'] - observed(rec_a)['rng']} RNG izvlacenja)")
            continue
        matches, closest, reasons = try_transition(cap_a, want)
        if not matches:
            # Perks the player brought (Energy Boost 22, Teleport 3): one use each.
            owned = {int(a["type"]): 1 for a in local_player(rec_a).get("board_abilities") or []
                     if a.get("type") in (22, 3)}
            if owned:
                perk_matches, perk_closest, _ = try_transition(cap_a, want, owned)
                if perk_matches:
                    tally["perk"] += 1
                    lines.append(f"{head}: PERK  {', '.join(sorted({m for m, _ in perk_matches}))} - poklapa se")
                    continue
                if perk_closest and (closest is None or perk_closest["distance"] < closest["distance"]):
                    closest = perk_closest
        if matches:
            tally["poklapa"] += 1
            for _, name in matches:
                if name:
                    hypothesis_hits[name] += 1
            moves = sorted({m for m, _ in matches})
            names = sorted({n for _, n in matches if n})
            lines.append(f"{head}: POKLAPA SE  {', '.join(moves)}" + (f"  [pragovi: {', '.join(names)}]" if names else ""))
        elif closest is None:
            tally["nepodrzano"] += 1
            lines.append(f"{head}: nepodrzano - " + "; ".join(f"{r} x{n}" for r, n in reasons.most_common(3)))
        else:
            tally["ne poklapa"] += 1
            lines.append(f"{head}: NE POKLAPA SE")
            lines.append(f"    najblize: {closest['action']}" + (f" [{closest['hypothesis']}]" if closest['hypothesis'] else "")
                         + f", rng igra/sim {closest['rng']}, dopune {closest['refills']}, "
                         f"razlicitih polja {len(closest['cells'])}+, specijala {closest['specials']}")
            if closest["cells"]:
                lines.append(f"    polja (red, kol, igra, sim): {closest['cells']}")
            lines += show_boards(grid(rec_a["board"]), want["board"])
    lines.append("")
    lines.append("UKUPNO: " + ", ".join(f"{k} {v}" for k, v in tally.most_common()))
    if hypothesis_hits:
        lines.append("Pragovi koji su se poklopili: " + ", ".join(f"{k} x{v}" for k, v in hypothesis_hits.most_common()))
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", nargs="?", type=Path)
    args = parser.parse_args(argv)
    folder = args.folder
    if folder is None:
        sessions = sorted(p for p in (ROOT / "Debug/research").glob("*") if p.is_dir())
        if not sessions:
            print("Nema sesija u Debug/research")
            return 1
        folder = sessions[-1]
    report = analyze(folder)
    (folder / "analiza.txt").write_text(report + "\n", encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
