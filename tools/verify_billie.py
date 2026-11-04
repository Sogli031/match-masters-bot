"""Offline Billie passive measurement; does not enable the live drone path.

python tools/verify_billie.py Debug/research/20261102_230448_column-mania

Every swap starts with a cloned capture RNG. A hit requires the whole board,
specials AND the complete RNG state to agree. Legacy recordings omit raw drone
slots: reconstruct its colour once from the board immediately before its first
activation, and disclose that provenance. Never infer a colour from the answer.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine_billie import BilliePassive
from engine_refill import UnsupportedRefill, color_maps
from simulator_capture import capture_mode, lab_move
from strategy_lab import planner, simulation
from tools.analyze_research import load, observed, booster_used


def measure(before, capture, after, config, *, energy_boost=False):
    lab = lab_move(capture)
    lab["engine_refill"].billie = config
    if energy_boost:
        lab["perks"] = {22: 1}
    want = observed(after)
    matches, best, reasons = [], None, Counter()
    # The measurement worker may inspect uncertified modes. Restore the set
    # even on error; this does not certify the mode for planning.
    previous = simulation.PREFIX_MODES
    simulation.PREFIX_MODES = previous | {capture_mode(capture["profile"]).value}
    try:
        for action in planner.actions(lab):
            if action.get("kind", "swap") != ("energy_boost" if energy_boost else "swap"):
                continue
            result = simulation.step(lab, action)
            if not result.get("supported"):
                reasons[result.get("reason")] += 1
                continue
            state = result["state"]
            cells = sum(int(v) != want["board"][r][c]
                        for r, row in enumerate(state["board"]) for c, v in enumerate(row))
            specials = sum(int(v) != want["special_board"][r][c]
                           for r, row in enumerate(state["special_board"]) for c, v in enumerate(row))
            rng = state["engine_refill"].rng
            # Captures may carry extra RNG metadata; compare the four fields.
            same_rng = all(after["profile"]["rng"].get(k) == v for k, v in rng.to_capture().items())
            distance = cells + specials + (not same_rng)
            event = next((e for e in result["events"] if e["type"] == "billie_passive"), None)
            if distance == 0:
                matches.append(action)
            if best is None or distance < best["distance"]:
                best = {"distance": distance, "action": action, "cells": cells, "specials": specials,
                        "rng": {"game": want["rng"], "sim": rng.counter, "state_equal": same_rng},
                        "passive": event, "refills": [len(t) for t in result["refills"]]}
    finally:
        simulation.PREFIX_MODES = previous
    return {"matches": matches, "best": best, "reasons": dict(reasons)}


def analyze(folder):
    files = sorted(Path(folder).glob("[0-9][0-9][0-9].json"))
    report = {"folder": str(folder), "experimental": True, "transitions": [], "counts": {}}
    tally = Counter()
    legacy_color, provenance, seed = None, None, None
    for a, b in zip(files, files[1:]):
        before, capture = load(a)
        after, _ = load(b)
        current_seed = before["profile"]["rng"].get("_seed")
        if seed != current_seed:
            legacy_color, provenance, seed = None, None, current_seed
        drones = [(r, c) for r, row in enumerate(before["special_board"]) for c, v in enumerate(row) if v == 14]
        next_drones = [(r, c) for r, row in enumerate(after["special_board"]) for c, v in enumerate(row) if v == 14]
        if not drones and len(next_drones) == 1 and booster_used(before, after):
            r, c = next_drones[0]
            to_engine, _ = color_maps(before["profile"])
            legacy_color = to_engine.get(before["board"][r][c])
            provenance = f"inferred from {a.stem}: colour retained by ConvertBillieBoomPiece at ({r},{c})"
        if not drones:
            continue
        item = {"pair": f"{a.stem}->{b.stem}"}
        if current_seed != after["profile"]["rng"].get("_seed"):
            item["verdict"] = "new_game"
        elif after.get("missed_board_before"):
            item["verdict"] = "gap"
        elif booster_used(before, after):
            item["verdict"] = "booster"
        elif observed(before) == observed(after):
            item["verdict"] = "unchanged"
        else:
            try:
                config = BilliePassive.from_record(before, drone_color=legacy_color)
                item["drone_color"] = config.drone_color
                item["colour_provenance"] = "raw billie_slots" if before.get("billie_slots") else provenance
                item.update(measure(before, capture, after, config))
                owned = next((p for p in before.get("snapshot_state", {}).get("players", [])
                              if p.get("player_type") == 0), {}).get("board_abilities") or []
                if not item["matches"] and any(p.get("type") == 22 for p in owned):
                    perk = measure(before, capture, after, config, energy_boost=True)
                    if perk["matches"]:
                        item.update(perk)
                        item["matched_perk"] = "energy_boost"
                item["verdict"] = "hit" if item["matches"] else "miss"
            except (UnsupportedRefill, KeyError, TypeError, ValueError) as exc:
                item.update(verdict="unsupported", reason=str(exc))
        tally[item["verdict"]] += 1
        report["transitions"].append(item)
    report["counts"] = dict(tally)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = analyze(args.folder)
    for item in report["transitions"]:
        best = item.get("best")
        detail = (f"cells={best['cells']}, specials={best['specials']}, RNG={best['rng']}" if best else item.get("reason", ""))
        print(f"{item['pair']}: {item['verdict']} {detail}")
    print(json.dumps(report["counts"]))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
