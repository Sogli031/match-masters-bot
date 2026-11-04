"""Foxy Roxy SE spray activation verifier.

Reads Debug/memory_board/board_snapshots.jsonl, finds pairs of consecutive
stable frames where a spray piece (SPECIAL_SPRAY_SE) disappears, and compares
the cells that actually changed colour against the bot's current ray model
(_spray_se_transformed_candidate paints a straight line from the spray cell to
the board edge). The point is to decide whether the powered-up Roxy still
sprays a ray or the pattern-paint from ability_config's FoxyRoxySE-powerup1
(Turn90/Spiral/Rectangle/Staircase/AlternatingRows, 6-10 cells, two colours,
energy 0-5).

Usage:
    python tools/spray_watch.py            # analyse the whole log
    python tools/spray_watch.py --follow   # tail the log live while you play

Each detected event prints a report and dumps the before/after frames to
Debug/spray_events/ for manual inspection.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

SPECIAL_SPRAY_SE = 29
BLOCKED = -1
EMPTY = 0

COLOR_GLYPHS = {
    -1: "#", 0: ".", 1: "B", 2: "G", 3: "Y", 4: "P", 5: "R", 6: "O",
    7: "W", 8: "C", 99: "*",
}

DIRECTIONS = {
    "LEFT": (0, -1),
    "RIGHT": (0, 1),
    "UP": (-1, 0),
    "DOWN": (1, 0),
}

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LOG = ROOT / "Debug" / "memory_board" / "board_snapshots.jsonl"
EVENTS_DIR = ROOT / "Debug" / "spray_events"


def _glyph(value: int) -> str:
    return COLOR_GLYPHS.get(value, "?")


def _is_board_piece(value: int) -> bool:
    return value not in (BLOCKED, EMPTY)


def _stable_frame(record: dict) -> dict | None:
    snap = record.get("snapshot") or {}
    if not snap.get("stable"):
        return None
    if not snap.get("board") or not snap.get("special_board"):
        return None
    return snap


def _energy_map(snap: dict) -> dict[tuple[int, int], int]:
    energy = {}
    for slot in snap.get("slots") or []:
        try:
            energy[(int(slot["row"]), int(slot["col"]))] = int(slot.get("energy", 1))
        except (KeyError, TypeError, ValueError):
            continue
    return energy


def _spray_cells(snap: dict) -> set[tuple[int, int]]:
    special = snap["special_board"]
    return {
        (row, col)
        for row in range(len(special))
        for col in range(len(special[row]))
        if special[row][col] == SPECIAL_SPRAY_SE
    }


def _ray_cells(board, start, step):
    row, col = start
    row_step, col_step = step
    size = len(board)
    row += row_step
    col += col_step
    cells = []
    while 0 <= row < size and 0 <= col < size:
        if _is_board_piece(board[row][col]):
            cells.append((row, col))
        row += row_step
        col += col_step
    return cells


def _render_diff(before, after, spray_cell, changed):
    lines = []
    for row in range(len(before)):
        glyphs = []
        for col in range(len(before[row])):
            if (row, col) == spray_cell:
                glyphs.append("S")
            elif (row, col) in changed:
                glyphs.append(_glyph(after[row][col]).lower() if after[row][col] == before[row][col] else _glyph(after[row][col]))
            else:
                glyphs.append("·")
        lines.append(" ".join(glyphs))
    return "\n".join(lines)


def _report_event(index: int, prev: dict, snap: dict, spray_cell: tuple[int, int]) -> None:
    before, after = prev["board"], snap["board"]
    size = len(before)
    changed = {
        (row, col)
        for row in range(size)
        for col in range(len(before[row]))
        if before[row][col] != after[row][col]
    }
    total_cells = sum(len(r) for r in before)
    if len(changed) > total_cells * 0.6:
        print(
            f"[event {index}] spray at {spray_cell} disappeared but "
            f"{len(changed)}/{total_cells} cells changed -> looks like a "
            "re-deal/new match, skipping."
        )
        return

    changed_no_self = changed - {spray_cell}
    color_hist: dict[int, int] = {}
    for row, col in changed_no_self:
        color_hist[after[row][col]] = color_hist.get(after[row][col], 0) + 1

    print("=" * 62)
    print(
        f"[event {index}] spray consumed at {spray_cell}  "
        f"({prev.get('captured_at')} -> {snap.get('captured_at')})"
    )
    print(f"changed cells (excl. spray cell): {len(changed_no_self)}")
    print(
        "new-colour histogram: "
        + ", ".join(f"{_glyph(color)}={count}" for color, count in sorted(color_hist.items()))
    )

    print("\nray-model comparison (predicted = straight line to edge):")
    best = None
    for name, step in DIRECTIONS.items():
        predicted = set(_ray_cells(before, spray_cell, step))
        if not predicted:
            continue
        hit = len(predicted & changed_no_self)
        precision = hit / len(predicted)
        recall = hit / len(changed_no_self) if changed_no_self else 0.0
        print(
            f"  {name:<5} predicted={len(predicted):>2}  hit={hit:>2}  "
            f"precision={precision:4.0%}  recall={recall:4.0%}"
        )
        if best is None or hit > best[1]:
            best = (name, hit, precision, recall)
    if best:
        name, hit, precision, recall = best
        verdict = (
            "RAY MODEL FITS"
            if precision >= 0.8 and recall >= 0.8
            else "ray model does NOT explain the paint -> pattern-paint suspected"
        )
        print(f"best direction: {name}  ->  {verdict}")

    energy_before = _energy_map(prev)
    energy_after = _energy_map(snap)
    gained = sorted(
        cell
        for cell in energy_after
        if energy_after[cell] > energy_before.get(cell, energy_after[cell])
    )
    if gained:
        print(f"cells that GAINED energy: {gained}")

    print("\ndiff grid (S=spray cell, letter=new colour, ·=unchanged):")
    print(_render_diff(before, after, spray_cell, changed_no_self))

    EVENTS_DIR.mkdir(parents=True, exist_ok=True)
    for tag, frame in (("before", prev), ("after", snap)):
        path = EVENTS_DIR / f"event_{index:03d}_{tag}.json"
        path.write_text(json.dumps(frame, indent=1), encoding="utf-8")
    print(f"frames dumped to {EVENTS_DIR}\\event_{index:03d}_*.json")
    print("=" * 62)


def _iter_lines(path: Path, follow: bool):
    with path.open(encoding="utf-8") as handle:
        if follow:
            handle.seek(0, 2)
            print(f"tailing {path} -- play a spray move now (Ctrl+C to stop)...")
        while True:
            line = handle.readline()
            if line:
                yield line
            elif follow:
                time.sleep(1.0)
            else:
                return


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("log", nargs="?", default=str(DEFAULT_LOG))
    parser.add_argument("--follow", action="store_true", help="tail the log live")
    args = parser.parse_args()

    log_path = Path(args.log)
    if not log_path.exists():
        sys.exit(f"snapshot log not found: {log_path}")

    prev = None
    event_index = 0
    events_found = 0
    try:
        for line in _iter_lines(log_path, args.follow):
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            snap = _stable_frame(record)
            if snap is None:
                continue
            if prev is not None and len(snap.get("board") or []) == len(prev["board"]):
                vanished = _spray_cells(prev) - _spray_cells(snap)
                for spray_cell in sorted(vanished):
                    event_index += 1
                    events_found += 1
                    _report_event(event_index, prev, snap, spray_cell)
            prev = snap
    except KeyboardInterrupt:
        pass
    if not args.follow:
        print(f"\ndone: {events_found} spray-consumption event(s) found in the log.")


if __name__ == "__main__":
    main()
