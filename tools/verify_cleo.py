"""Strict offline Cleo swipe replay, without inferring a colour from the answer.

Unlike cleo_audit.py (extra-move classification only), a hit here requires
all board cells, all specials, all four RNG fields and the move counter.
An unrecorded swipe is searched among adjacent Cleo swaps in both directions;
finding one reproducing the outcome is evidence of a possible explanation,
not proof of which action the player performed.
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

import move_strategy as ms
from engine_refill import UnsupportedRefill
from simulator_capture import lab_move
from strategy_lab import simulation
from tools.analyze_research import capture_from, booster_used

RNG_FIELDS = ("_matrix", "_index", "_seed", "<counter>k__BackingField")


def grid(board):
    return [[int(v) for v in row] for row in board]


def differences(record, state):
    """Every necessary equality, including RNG words when counters agree."""
    out = {}
    for name in ("board", "special_board"):
        want, got = grid(record[name]), grid(state[name])
        if want != got:
            out[name] = True
    want_rng = record.get("profile", {}).get("rng", {})
    got_rng = state["engine_refill"].rng.to_capture()
    for name in RNG_FIELDS:
        if name not in want_rng or want_rng[name] != got_rng.get(name):
            out[f"rng.{name}"] = True
    want_moves = record.get("profile", {}).get("state", {}).get("moves")
    got_moves = state.get("turn_state", {}).get("remaining_moves")
    if want_moves is None or got_moves is None or want_moves != got_moves:
        out["moves"] = True
    return out


def cleo_actions(record):
    """Enumerate directly, without running the old probability model."""
    specials = record["special_board"]
    rows = len(specials)
    for r, row in enumerate(specials):
        for c, special in enumerate(row):
            if special != ms.SPECIAL_CLEO_BUG:
                continue
            for direction, (dy, dx) in ms.DIRECTION_STEPS.items():
                y, x = r + dy, c + dx
                if not (0 <= y < rows and 0 <= x < len(specials[y])):
                    continue
                for start, target, oriented in (((r, c), (y, x), direction),
                        ((y, x), (r, c), ms.OPPOSITE_DIRECTIONS[direction])):
                    yield {"kind": "swap", "start": list(start), "target": list(target),
                           "direction": oriented.value}


def measure(before, after):
    reasons, matches, supported, best = Counter(), [], 0, None
    # Missing fields are genuinely unavailable; never synthesize a default
    # config, use count or hidden colour from this transition's target board.
    profile = before["profile"]
    required = ("cleo_piece_logic", "board_extra_data", "raw_slots")
    missing = [name for name in required if profile.get(name) is None]
    if missing:
        return {"verdict": "unsupported", "matches": [], "supported_candidates": 0,
                "reasons": {"missing capture fields: " + ", ".join(missing): 1}}
    try:
        lab = lab_move(capture_from(before))
    except (UnsupportedRefill, KeyError, TypeError, ValueError) as exc:
        return {"verdict": "unsupported", "matches": [], "supported_candidates": 0,
                "reasons": {str(exc): 1}}
    previous = simulation.PREFIX_MODES
    simulation.PREFIX_MODES = previous | {lab["mode"]}
    try:
        for action in cleo_actions(before):
            result = simulation.step(lab, action)
            if not result.get("supported"):
                reasons[result.get("reason", "unsupported")] += 1
                continue
            supported += 1
            diff = differences(after, result["state"])
            if not diff:
                matches.append(action)
            if best is None or len(diff) < len(best["differences"]):
                best = {"action": action, "differences": list(diff),
                        "rng_counter": result["state"]["engine_refill"].rng.counter}
    finally:
        simulation.PREFIX_MODES = previous
    return {"verdict": "hit" if matches else "miss" if supported else "unsupported",
            "matches": matches, "supported_candidates": supported,
            "best": best, "reasons": dict(reasons)}


def analyze(folders):
    report = {"criterion": "board + specials + complete RNG + moves",
              "action_provenance": "searched adjacent Cleo swaps; no recorded input event",
              "transitions": [], "counts": {}, "inventory": {}}
    tally, inventory = Counter(), Counter()
    for folder in folders:
        files = sorted(Path(folder).glob("[0-9][0-9][0-9].json"))
        records = [(p, json.loads(p.read_text(encoding="utf-8"))) for p in files]
        present = [(p, rec) for p, rec in records
                   if any(ms.SPECIAL_CLEO_BUG in row for row in rec.get("special_board", []))]
        if present:
            report["inventory"][str(folder)] = [p.name for p, _ in present]
            inventory["boards_with_cleo"] += len(present)
        for (a, before), (b, after) in zip(records, records[1:]):
            count_before = sum(row.count(ms.SPECIAL_CLEO_BUG) for row in before["special_board"])
            if not count_before:
                continue
            count_after = sum(row.count(ms.SPECIAL_CLEO_BUG) for row in after["special_board"])
            item = {"folder": str(folder), "pair": f"{a.stem}->{b.stem}",
                    "cleo_before": count_before, "cleo_after": count_after,
                    "cleo_consumed": count_after < count_before}
            if before["profile"]["rng"].get("_seed") != after["profile"]["rng"].get("_seed"):
                item["verdict"] = "new_game"
            elif after.get("missed_board_before"):
                item["verdict"] = "gap"
            elif booster_used(before, after):
                item["verdict"] = "booster"
            elif (before["board"] == after["board"] and before["special_board"] == after["special_board"]
                  and before["profile"]["rng"] == after["profile"]["rng"]):
                item["verdict"] = "unchanged"
            else:
                item.update(measure(before, after))
            tally[item["verdict"]] += 1
            report["transitions"].append(item)
    report["counts"] = dict(tally)
    report["inventory_counts"] = dict(inventory)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folders", nargs="*", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    folders = args.folders or sorted(p for root in (ROOT / "Debug/research", ROOT / "Debug/refill_misses")
                                    if root.is_dir() for p in root.iterdir() if p.is_dir())
    report = analyze(folders)
    print(json.dumps({"counts": report["counts"], "inventory": report["inventory_counts"]}, ensure_ascii=False))
    for item in report["transitions"]:
        print(f"{Path(item['folder']).name} {item['pair']}: {item['verdict']} {item.get('reasons', {})}")
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
