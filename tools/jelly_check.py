"""Replay active Jelly SE transitions from a completed recording."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import move_strategy as ms
from tools.analyze_research import load, observed, recorded_jelly_active, recorded_jelly_state, try_transition


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    parser.add_argument("--baseline", action="store_true", help="Replay without the Jelly zone.")
    args = parser.parse_args()
    ms.JELLY_EXACT_PORTED = not args.baseline
    files = sorted(args.folder.glob("[0-9][0-9][0-9].json"))
    exact = total = 0
    for first, second in zip(files, files[1:]):
        before, capture = load(first)
        jelly = recorded_jelly_state(before) or {}
        if not recorded_jelly_active(jelly):
            continue
        after, _ = load(second)
        old_input, new_input = before.get("refill_input"), after.get("refill_input")
        if old_input is not None and new_input is not None:
            if new_input[0] != old_input[0] + 1 or new_input[1] != "move":
                continue
        total += 1
        if args.baseline:
            capture["simulator_input"].pop("jelly_zone_cells", None)
        matches, closest, reasons = try_transition(capture, observed(after))
        exact += bool(matches)
        print(first.stem, "TACNO" if matches else "promasaj", matches or closest or dict(reasons))
    print(f"{exact}/{total} tacno")


if __name__ == "__main__":
    main()
