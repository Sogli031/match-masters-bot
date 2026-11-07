"""Flat vs tapered mushroom multiplier-point pricing, on recorded boards.

A mushroom raises `PlayerModel.scoreMultiplier`. `_mushroom_weight` used to pay
a flat 22.0 / 2.5 = 8.8 for one such point whatever the multiplier already
standing; it now pays `max(8.8, MUSHROOM_MULTIPLIER_POINT_VALUE / multiplier)`.

The tool does two things, both off the recorded snapshots:

* **measure** -- reconstructs what a multiplier point was actually worth. For
  every recorded decision it sums the BASE points still to come (each later
  score step divided by the multiplier standing when it landed); that sum
  divided by the current multiplier is the point's value in the ranking's own
  base-point units. This is what `MUSHROOM_MULTIPLIER_POINT_VALUE` is fitted
  to, and re-running it after more games is how to re-fit it.

* **compare** -- replays every recorded mushroom board through both pricings,
  with the live multiplier and move counter that board actually had, and
  reports where the two choose a different move. A recording holds no
  counterfactual, so it reports the observable difference per changed pick:
  instant points, multiplier points collected, booster charge.

    python tools/compare_mushroom_weight.py                 # measure + compare
    python tools/compare_mushroom_weight.py --measure-only
    python tools/compare_mushroom_weight.py --limit 200 --verbose
    python tools/compare_mushroom_weight.py --sweep 8.8,60,116,200

Set MUSHROOM_TAIL_BYTES to scan less of the (very large) snapshot log.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import move_strategy as ms  # noqa: E402

SNAPSHOTS = ROOT / "Debug" / "memory_board" / "board_snapshots.jsonl"
TAIL_BYTES = int(os.environ.get("MUSHROOM_TAIL_BYTES", 400 * 1024 * 1024))
# The board models built out of mushrooms (memory_gui.BOARD_MODEL_TO_MODE).
MUSHROOM_BOARD_MODELS = {29, 30}
# The live in-game lookahead parameters (memory_gui `_fast_lookahead_params`).
LOOKAHEAD_CANDIDATES = 10
LOOKAHEAD_DEPTH = 2
LOOKAHEAD_BEAM = 3

BANDS = ((1, 2, "x1-x2"), (3, 5, "x3-x5"), (6, 10, "x6-x10"), (11, 999, "x11+"))


def band(multiplier):
    for low, high, label in BANDS:
        if low <= multiplier <= high:
            return label
    return BANDS[-1][2]


def flat_mushroom_weight(weights):
    """`_mushroom_weight` as it was before the taper: 8.8 at every multiplier."""
    if not ms.mushroom_multipliers_enabled():
        return weights.get("mushroom", 0.0)
    flat = max(
        weights.get("mushroom", 0.0),
        ms.MODE_WEIGHTS[ms.MULTIPLIER_MUSHROOMS_MODE]["mushroom"],
    )
    return flat / ms.MUSHROOM_MEAN_MULTIPLIER


def tapered_weight_with(constant):
    """Production pricing with MUSHROOM_MULTIPLIER_POINT_VALUE overridden."""

    def weight(weights):
        if not ms.mushroom_multipliers_enabled():
            return weights.get("mushroom", 0.0)
        flat = flat_mushroom_weight(weights)
        return max(flat, constant / max(1.0, ms._SCORE_MULTIPLIER))

    return weight


def read_frames(limit_boards=None):
    """Every recorded mushroom frame, in order, plus the distinct boards."""
    size = SNAPSHOTS.stat().st_size
    handle = SNAPSHOTS.open("rb")
    handle.seek(max(0, size - TAIL_BYTES))
    handle.readline()
    frames = []
    boards = []
    seen = set()
    for line in handle:
        if b'"board_model_name"' not in line:
            continue
        try:
            payload = json.loads(line.decode("utf-8"))
        except ValueError:
            continue
        snapshot = payload.get("snapshot", payload)
        state = snapshot.get("state") or {}
        rules = state.get("rules") or {}
        try:
            model = int(rules.get("board_model_name"))
        except (TypeError, ValueError):
            continue
        if model not in MUSHROOM_BOARD_MODELS:
            continue
        me = next(
            (p for p in (state.get("players") or []) if p.get("player_type") == 0),
            None,
        )
        if me is None:
            continue
        try:
            multiplier = max(1, int(me.get("score_multiplier") or 1))
        except (TypeError, ValueError):
            multiplier = 1
        frames.append(
            {
                "t": snapshot.get("captured_at"),
                "score": me.get("score"),
                "multiplier": multiplier,
                "moves": state.get("moves"),
            }
        )
        board = snapshot.get("board")
        special = snapshot.get("special_board")
        if not board or not special or not state.get("moves"):
            continue
        if not any(cell == ms.SPECIAL_MUSHROOM for row in special for cell in row):
            continue
        if limit_boards is not None and len(boards) >= limit_boards:
            continue
        signature = snapshot.get("state_signature") or json.dumps(
            [board, special], separators=(",", ":")
        )
        if signature in seen:
            continue
        seen.add(signature)
        boards.append(
            {
                "t": snapshot.get("captured_at"),
                "board": board,
                "special": special,
                "multiplier": multiplier,
                "moves": int(state["moves"]),
                "square": bool(rules.get("is_square_match")),
                "explode": bool(rules.get("specials_auto_explode")),
            }
        )
    return frames, boards


def split_runs(frames):
    """Frames grouped per run -- a score that drops is a fresh run."""
    runs = []
    current = []
    previous = None
    for frame in frames:
        if (
            previous is not None
            and frame["score"] is not None
            and previous["score"] is not None
            and frame["score"] < previous["score"] - 5
        ):
            runs.append(current)
            current = []
        current.append(frame)
        previous = frame
    if current:
        runs.append(current)
    return [run for run in runs if len(run) > 20]


def measure(frames):
    """What one multiplier point was actually worth, per multiplier band."""
    samples = []
    for run in split_runs(frames):
        steps = []
        for index in range(1, len(run)):
            before, after = run[index - 1], run[index]
            if before["score"] is None or after["score"] is None:
                continue
            gained = after["score"] - before["score"]
            if gained > 0:
                # Back out the base points from the multiplier that paid them.
                steps.append((index, gained / max(1, before["multiplier"])))
        for index, frame in enumerate(run):
            if not frame["moves"]:
                continue
            base_to_come = sum(base for step, base in steps if step > index)
            samples.append((frame["multiplier"], base_to_come))
    return samples


def report_measurement(samples, constants):
    if not samples:
        print("nema dovoljno snimljenih runova za merenje.")
        return
    print(f"izmereno na {len(samples)} odluka iz snimljenih runova")
    print("(vrednost jednog poena mnozioca = bazni poeni koji tek dolaze / mnozilac)")
    print()
    header = f"{'mnozilac':<9} {'odluka':>7} {'medijana m':>11} {'izmereno':>10}"
    for value in constants:
        header += f" {('C=%g' % value):>9}"
    print(header)
    print("-" * len(header))
    for low, high, label in BANDS:
        subset = [(m, b) for m, b in samples if low <= m <= high]
        if not subset:
            continue
        median_m = statistics.median(m for m, _ in subset)
        measured = statistics.median(b / m for m, b in subset)
        line = f"{label:<9} {len(subset):>7} {median_m:>11.0f} {measured:>10.1f}"
        for value in constants:
            priced = max(
                ms.MODE_WEIGHTS[ms.MULTIPLIER_MUSHROOMS_MODE]["mushroom"]
                / ms.MUSHROOM_MEAN_MULTIPLIER,
                value / max(1.0, median_m),
            )
            line += f" {priced:>9.1f}"
        print(line)
    print("-" * len(header))
    ceilings = []
    for low, high, _ in BANDS:
        subset = [(m, b) for m, b in samples if low <= m <= high]
        if not subset:
            continue
        ceilings.append(
            statistics.median(b / m for m, b in subset)
            * statistics.median(m for m, _ in subset)
        )
    ceiling = min(ceilings) if ceilings else 0.0
    print(
        f"najveci C koji nigde ne prelazi izmerenu vrednost: {ceiling:.0f}  "
        f"(u kodu: {ms.MUSHROOM_MULTIPLIER_POINT_VALUE:g})"
    )


def rank(case, weight_fn):
    """Rank one recorded board with `_mushroom_weight` swapped for weight_fn."""
    original = ms._mushroom_weight
    ms._mushroom_weight = weight_fn
    try:
        with ms.mushroom_multipliers_active(True):
            with ms.score_multiplier_state(case["multiplier"], case["moves"]):
                return ms.rank_moves(
                    case["board"],
                    case["special"],
                    mode=ms.MULTIPLIER_MUSHROOMS_MODE,
                    allow_square_matches=case["square"],
                    explode_created_specials_immediately=case["explode"],
                    lookahead_candidates=LOOKAHEAD_CANDIDATES,
                    lookahead_depth=LOOKAHEAD_DEPTH,
                    lookahead_beam_width=LOOKAHEAD_BEAM,
                    include_future_value=True,
                )
    finally:
        ms._mushroom_weight = original


def compare(boards, weight_fn, label, verbose=False):
    changed = Counter()
    total = Counter()
    deltas = defaultdict(lambda: {"instant": 0.0, "mush": 0.0, "blue": 0.0})
    examples = []
    for case in boards:
        flat_ranked = rank(case, flat_mushroom_weight)
        new_ranked = rank(case, weight_fn)
        if not flat_ranked or not new_ranked:
            continue
        key = band(case["multiplier"])
        total[key] += 1
        old, new = flat_ranked[0], new_ranked[0]
        if old.candidate == new.candidate:
            continue
        changed[key] += 1
        deltas[key]["instant"] += new.instant_score - old.instant_score
        deltas[key]["mush"] += new.multiplier_mushrooms - old.multiplier_mushrooms
        deltas[key]["blue"] += new.blue_cells - old.blue_cells
        examples.append((case, old, new))

    print()
    print(f"{label}: promena izbora u odnosu na ravnu cenu 8.8")
    print("(razlike su prosek PO PROMENJENOM izboru, novo minus ravno)")
    print()
    header = (
        f"{'mnozilac':<9} {'tabli':>6} {'promenjen izbor':>18} "
        f"{'d instant':>11} {'d mnoz.poena':>14} {'d plavih':>10}"
    )
    print(header)
    print("-" * len(header))
    for _, _, key in BANDS:
        count_all = total[key]
        count_changed = changed[key]
        if not count_all:
            continue
        per = max(count_changed, 1)
        delta = deltas[key]
        print(
            f"{key:<9} {count_all:>6} {count_changed:>10} "
            f"({100.0 * count_changed / count_all:>3.0f}%) "
            f"{delta['instant'] / per:>+11.1f} {delta['mush'] / per:>+14.1f} "
            f"{delta['blue'] / per:>+10.1f}"
        )
    count_all = sum(total.values())
    count_changed = sum(changed.values())
    print("-" * len(header))
    print(
        f"{'UKUPNO':<9} {count_all:>6} {count_changed:>10} "
        f"({100.0 * count_changed / max(count_all, 1):>3.0f}%)"
    )

    if verbose and examples:
        print("\ntable gde se izbor promenio:")
        for case, old, new in examples:
            print(f"  {case['t']}  x{case['multiplier']}  poteza={case['moves']}")
            print(
                f"     ravna:  {old.candidate}  instant={old.instant_score:.0f}"
                f"  mnoz.poena={old.multiplier_mushrooms:.0f}"
                f"  plavih={old.blue_cells:.0f}  score={old.score:.1f}"
            )
            print(
                f"     nova:   {new.candidate}  instant={new.instant_score:.0f}"
                f"  mnoz.poena={new.multiplier_mushrooms:.0f}"
                f"  plavih={new.blue_cells:.0f}  score={new.score:.1f}"
            )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=120,
                        help="koliko razlicitih tabli da uporedi (0 = sve)")
    parser.add_argument("--verbose", action="store_true",
                        help="ispisi svaku tablu na kojoj se izbor promenio")
    parser.add_argument("--measure-only", action="store_true",
                        help="samo izmeri vrednost poena, bez poredjenja")
    parser.add_argument("--sweep", default=None,
                        help="zarezom razdvojene vrednosti konstante za probu")
    args = parser.parse_args()

    constants = [ms.MUSHROOM_MULTIPLIER_POINT_VALUE]
    if args.sweep:
        constants = [float(value) for value in args.sweep.split(",")]

    limit = None if not args.limit else args.limit
    frames, boards = read_frames(limit)
    print(f"snimljenih mushroom frejmova: {len(frames)}, "
          f"razlicitih tabli sa pecurkom: {len(boards)}")
    print()
    report_measurement(measure(frames), constants)
    if args.measure_only:
        return
    for value in constants:
        compare(
            boards,
            tapered_weight_with(value),
            f"C={value:g}",
            verbose=args.verbose and len(constants) == 1,
        )


if __name__ == "__main__":
    main()
