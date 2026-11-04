"""Read what an action really did, out of a run's recorded memory frames.

`Debug/runs/<run>/memory_frames.jsonl` holds every board the game passed
through while the action resolved -- the settled board alone cannot say it,
because by the time it arrives the refill has already covered the cleared
cells. Each frame carries the raw slots plus score, energy and the move
counter, so the effect is read off rather than inferred:

    python tools/read_memory_frames.py Debug/runs/2026-08-17_02-20-17_435

The engine writes clear and refill into the model in one go, so a slot is
practically never seen Empty. Each step is therefore reported as the number of
cells it rewrote plus the exact score and energy it paid -- measured, not
inferred. `--cells` also prints which cells each step touched.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

SLOT_EMPTY_VALUE = 1


def load_frames(run_dir: Path) -> list[dict]:
    path = run_dir / "memory_frames.jsonl"
    if not path.exists():
        raise SystemExit(f"Nema {path} (Debug zapis mora biti ukljucen dok se igra)")
    frames = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            frames.append(json.loads(line))
    return frames


def _me(frame: dict) -> dict:
    players = frame.get("players") or []
    return players[0] if players else {}


def _empty_cells(frame: dict) -> list[tuple[int, int]]:
    cells = []
    for slot in frame.get("slots") or []:
        if int(slot.get("value", 0)) == SLOT_EMPTY_VALUE:
            cells.append((int(slot["y"]), int(slot["x"])))
    return sorted(cells)


def _specials(frame: dict) -> list[tuple[int, int, int]]:
    found = []
    for slot in frame.get("slots") or []:
        value = int(slot.get("value", 0))
        if value not in (0, SLOT_EMPTY_VALUE):
            found.append((int(slot["y"]), int(slot["x"]), value))
    return sorted(found)


def _changed_cells(before: dict, after: dict) -> list[tuple[int, int]]:
    first, second = before.get("board") or [], after.get("board") or []
    return [
        (row, col)
        for row in range(len(second))
        for col in range(len(second[row]))
        if first and first[row][col] != second[row][col]
    ]


def describe(run_dir: Path, show_cells: bool = False) -> None:
    frames = load_frames(run_dir)
    move_path = run_dir / "move.json"
    if move_path.exists():
        move = json.loads(move_path.read_text(encoding="utf-8"))
        best = move.get("best_move") or {}
        print(f"akcija: {move.get('selected_action')}  mod: {move.get('mode')}")
        if best.get("start"):
            print(
                f"plan: {best['start']} -> {best['target']}  "
                f"poeni {best.get('instant_score')}  plave {best.get('blue_cells')}  "
                f"ocisceno {best.get('cleared_cells')}"
            )
        effects = [
            event["type"]
            for event in best.get("intent_events") or []
            if event.get("type") not in {"match", "special_creation"}
        ]
        if effects:
            print(f"predvidjeni efekti: {effects}")

    # The engine writes each cascade step into the model whole -- the cleared
    # cells are refilled in the same write, so a slot is practically never seen
    # Empty. What a step *did* is therefore read from how many cells it
    # rewrote, together with the exact score and energy it paid.
    print(f"\nkadrova: {len(frames)}")
    print(f"{'korak':>5} {'vreme':>13} {'polja':>6} {'poeni':>6} {'buster':>7} {'potezi':>7} {'spec':>5}")
    previous = None
    steps = 0
    total_cells = 0
    for frame in frames:
        me = _me(frame)
        if previous is None:
            stamp = str(frame.get("captured_at") or "")[11:23]
            print(
                f"{'start':>5} {stamp:>13} {'-':>6} {str(me.get('score')):>6} "
                f"{str(me.get('energy')):>7} {str(frame.get('moves')):>7} "
                f"{len(_specials(frame)):>5}"
            )
            previous = frame
            continue
        changed = _changed_cells(previous, frame)
        before_me = _me(previous)
        score_delta = (me.get("score") or 0) - (before_me.get("score") or 0)
        energy_delta = (me.get("energy") or 0) - (before_me.get("energy") or 0)
        if changed or score_delta or energy_delta:
            steps += 1
            total_cells += len(changed)
            stamp = str(frame.get("captured_at") or "")[11:23]
            print(
                f"{steps:>5} {stamp:>13} {len(changed):>6} {score_delta:>+6} "
                f"{energy_delta:>+7} {str(frame.get('moves')):>7} "
                f"{len(_specials(frame)):>5}"
            )
            if show_cells and changed:
                print(f"        polja: {changed}")
        previous = frame

    if not frames:
        return
    first, last = _me(frames[0]), _me(frames[-1])
    print(f"\nkoraka: {steps}  prepisanih polja ukupno: {total_cells}")
    if first.get("score") is not None and last.get("score") is not None:
        print(f"skor: {first['score']} -> {last['score']}  (+{last['score'] - first['score']})")
    if first.get("energy") is not None and last.get("energy") is not None:
        print(f"buster: {first['energy']} -> {last['energy']}")
    empty = max((_empty_cells(frame) for frame in frames), key=len, default=[])
    if empty:
        print(f"uhvacena prazna polja (redak slucaj): {empty}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path, help="Debug/runs/<run> folder")
    parser.add_argument(
        "--cells",
        action="store_true",
        help="ispisi i koordinate polja koja je svaki korak prepisao",
    )
    arguments = parser.parse_args()
    describe(arguments.run, show_cells=arguments.cells)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
