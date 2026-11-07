"""Measure live Cleo swaps from Debug/runs and separate the two readings of
"create extra move" (docs/cleo_model.md, "Predlog kako da se mapira", tacka 1).

Reading A -- the swap itself hands the turn back: remaining_moves stays the
same between the Cleo run and the next run of the same match. This is the only
signal that may justify raising CLEO_EXTRA_MOVE_CHANCE in move_strategy.py.

Reading B -- the clone leaves a match-4 opportunity on the *next* board: the
next run's ranking contains a move with a guaranteed direct extra. If B is
common while A stays at zero, "chanceToCreateExtraMoveOnClone" means setup
value, and it belongs in the scenario scoring, not in an immediate-extra
probability.

Caveats printed with the results:
  * the remaining_moves counter is read from memory and can lag several
    seconds behind the animation; a run that fires inside that window can
    carry the previous value. Rows where the counter moved by more than 1 or
    the score continuity broke are marked UNRELIABLE and excluded from the
    summary counts.
  * only runs where the bot actually played the Cleo swap are counted
    (selected_action == "move" and the best move carries a `cleo` block).

Usage:
    python tools/measure_cleo_swaps.py [--runs Debug/runs] [--max-gap 120]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import move_strategy as ms  # noqa: E402

# The in-game move counter read from memory trails the animation by roughly
# eight seconds (measured on the Mixy watch, Debug 2026-08). An unchanged
# counter inside that window is not evidence of an extra move.
COUNTER_LAG_SECONDS = 10.0


def _load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _run_time(name: str) -> datetime | None:
    try:
        return datetime.strptime(name[:19], "%Y-%m-%d_%H-%M-%S")
    except ValueError:
        return None


def _color_counts(board) -> Counter:
    counts: Counter = Counter()
    for row in board or []:
        for value in row:
            # 99 is the hidden/blocked cell marker; specials ride a separate
            # grid, so plain small ints are the colours.
            if isinstance(value, int) and 0 < value < 20:
                counts[value] += 1
    return counts


def _next_board_has_direct_extra(move_payload) -> bool | None:
    """True if the following board offers a move with a guaranteed extra."""
    board = move_payload.get("board")
    special_board = move_payload.get("special_board")
    if not board or not special_board:
        return None
    try:
        ranked = ms.rank_moves(board, special_board, include_future_value=False)
    except Exception:
        return None
    return any(evaluation.direct_extra_moves >= 1.0 for evaluation in ranked)


def measure(runs_dir: Path, max_gap_seconds: float) -> int:
    entries = []
    for run_dir in sorted(runs_dir.iterdir()):
        move_path = run_dir / "move.json"
        if not move_path.is_file():
            continue
        stamp = _run_time(run_dir.name)
        if stamp is None:
            continue
        payload = _load_json(move_path)
        if payload is not None:
            entries.append((stamp, run_dir.name, payload))

    swaps = []
    for index, (stamp, name, payload) in enumerate(entries):
        best = payload.get("best_move") or {}
        if payload.get("selected_action") != "move" or "cleo" not in best:
            continue
        follow = None
        for next_stamp, next_name, next_payload in entries[index + 1 :]:
            if (next_stamp - stamp).total_seconds() > max_gap_seconds:
                break
            follow = (next_name, next_payload, (next_stamp - stamp).total_seconds())
            break
        swaps.append((name, payload, follow))

    if not swaps:
        print(f"No played Cleo swaps found under {runs_dir}.")
        return 1

    reliable = 0
    immediate_extra = 0  # reading A
    setup_extra = 0      # reading B
    setup_known = 0

    header = (
        f"{'run':<24} {'moves':>7} {'A:extra':>8} {'B:setup4':>9} "
        f"{'rolled':>7} {'bot_w':>6}  note"
    )
    print(header)
    print("-" * len(header))

    for name, payload, follow in swaps:
        turn = payload.get("turn_state") or {}
        moves_before = turn.get("remaining_moves")
        best = payload.get("best_move") or {}
        cleo = best.get("cleo") or {}

        if follow is None:
            print(f"{name:<24} {str(moves_before):>7} {'?':>8} {'?':>9} "
                  f"{'?':>7} {'':>6}  no follow-up run inside the gap window")
            continue
        next_name, next_payload, gap_seconds = follow
        moves_after = (next_payload.get("turn_state") or {}).get("remaining_moves")

        note = ""
        unreliable = False
        if moves_before is None or moves_after is None:
            unreliable = True
            note = "UNRELIABLE: counter unreadable"
        else:
            delta = moves_before - moves_after
            if delta not in (0, 1):
                unreliable = True
                note = f"UNRELIABLE: counter moved by {delta} (lag?)"
            elif delta == 0 and gap_seconds < COUNTER_LAG_SECONDS:
                # The counter lags several seconds behind the animation; an
                # unchanged value read this early proves nothing. A *dropped*
                # counter is trustworthy at any gap (it can only lag, never
                # run ahead).
                unreliable = True
                note = (
                    f"INCONCLUSIVE: unchanged counter {gap_seconds:.0f}s after "
                    f"the swap (inside the ~{COUNTER_LAG_SECONDS:.0f}s lag)"
                )
        score_before = (payload.get("score_state") or {}).get("our_score")
        next_before = ((next_payload.get("score_state") or {}).get("our_score"))
        if score_before is not None and next_before is not None:
            if next_before < score_before:
                unreliable = True
                note = "UNRELIABLE: score went backwards (new match?)"

        extra = None if unreliable else (moves_before == moves_after)
        setup = _next_board_has_direct_extra(next_payload)

        # Which colour actually got cloned: the colour whose count grew the
        # most between this board and the next one.
        gained = _color_counts(next_payload.get("board")) - _color_counts(
            payload.get("board")
        )
        rolled, bot_weight = "?", ""
        if gained:
            rolled_color, _gain = gained.most_common(1)[0]
            rolled = str(rolled_color)
            colors = list(cleo.get("scenario_colors") or [])
            weights = list(cleo.get("scenario_weights") or [])
            if rolled_color in colors and len(weights) == len(colors):
                bot_weight = f"{weights[colors.index(rolled_color)]:.2f}"

        if not unreliable:
            reliable += 1
            if extra:
                immediate_extra += 1
        if setup is not None:
            setup_known += 1
            if setup:
                setup_extra += 1

        print(
            f"{name:<24} {f'{moves_before}->{moves_after}':>7} "
            f"{('yes' if extra else 'no') if extra is not None else '?':>8} "
            f"{('yes' if setup else 'no') if setup is not None else '?':>9} "
            f"{rolled:>7} {bot_weight:>6}  {note}"
        )

    print()
    print(f"Played Cleo swaps: {len(swaps)} ({reliable} with a reliable counter)")
    if reliable:
        print(
            f"Reading A (swap returned the move):  {immediate_extra}/{reliable}"
            f"  -> measured CLEO_EXTRA_MOVE_CHANCE ~ {immediate_extra / reliable:.2f}"
        )
    if setup_known:
        print(
            f"Reading B (match-4 left on next board): {setup_extra}/{setup_known}"
        )
    print()
    print("Only reading A may move CLEO_EXTRA_MOVE_CHANCE (move_strategy.py).")
    print("Reading B is setup value; it is already priced through the scenario")
    print("scores (uniform over the non-partner colours).")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    default_runs = Path(__file__).resolve().parent.parent / "Debug" / "runs"
    parser.add_argument("--runs", type=Path, default=default_runs)
    parser.add_argument("--max-gap", type=float, default=120.0,
                        help="max seconds to the follow-up run (default 120)")
    args = parser.parse_args()
    if not args.runs.is_dir():
        print(f"Runs directory not found: {args.runs}")
        return 1
    return measure(args.runs, args.max_gap)


if __name__ == "__main__":
    raise SystemExit(main())
