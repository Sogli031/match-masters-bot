"""Measure what a Froggy Fu lotus move actually does to the board.

Step two of the lotus work. Step one decoded the engine's gather region out of
`libil2cpp.so` (see `docs/game_mode_logic_from_code.md`):

    CalcBoardDistance(a, b, chebyshev) = chebyshev ? max(|dx|,|dy|) : |dx|+|dy|
    InGatherRegion(p, lotus, r, cheb)  = CalcBoardDistance(p, lotus, cheb) <= r

What the code cannot say is which *radius* the server ships, and therefore
whether the region restricts anything at all. This tool answers that from
recordings the bot already makes: `Debug/runs/<run>/memory_frames.jsonl` keeps
the frames captured *during* the cascade, and a lotus move shows the pulled
pieces gathered into a blob before they are destroyed -- the pull itself, on
screen, in the data.

Per lotus move it prints:

* the colour that fired and the lotus position after the swap,
* how many pieces of that colour stood on the board before the move,
* how many ended up in the gathered blob,
* how many of the pre-move pieces sat inside the configured gather region,
* and the smallest radius that would explain the blob.

Nothing is sent to the game and no move is played; it only reads recordings.

    python .\\tools\\measure_froggy_lotus.py
    python .\\tools\\measure_froggy_lotus.py --runs Debug\\runs --limit 20
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Iterator

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from move_strategy import (  # noqa: E402
    SPECIAL_FROGGY_LOTUS,
    froggy_gather_config_from_params,
    froggy_in_gather_region,
)

DEFAULT_RUNS = PROJECT_ROOT / "Debug" / "runs"
# SlotValue 1 is Empty and -1 is the bot's BLOCKED marker; neither is a piece.
NON_PIECE = {0, -1}
LOTUS_EVENT = "froggy_lotus_collect"
# The specials a match can leave behind, in the bot's numbering. Mushrooms (19)
# and lotuses (20) are board pieces, not created specials, so they are not here.
CREATED_SPECIALS = {1: "row", 2: "col", 3: "bomb", 4: "lightning", 5: "crosshair"}


def _load_frames(run: Path) -> list[dict[str, Any]]:
    path = run / "memory_frames.jsonl"
    if not path.is_file():
        return []
    frames = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            frames.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return frames


def _lotus_event(run: Path) -> dict[str, Any] | None:
    path = run / "move.json"
    if not path.is_file():
        return None
    try:
        move = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    best = move.get("best_move") or {}
    for event in best.get("intent_events") or ():
        if isinstance(event, dict) and event.get("type") == LOTUS_EVENT:
            return event
    return None


def _lotus_cells(frame: dict[str, Any]) -> list[tuple[int, int]]:
    special = frame.get("special_board") or []
    return [
        (row, col)
        for row, values in enumerate(special)
        for col, value in enumerate(values)
        if value == SPECIAL_FROGGY_LOTUS
    ]


def _color_cells(board: list[list[int]], color: int) -> list[tuple[int, int]]:
    return [
        (row, col)
        for row, values in enumerate(board)
        for col, value in enumerate(values)
        if value == color
    ]


def _largest_blob(board: list[list[int]], color: int) -> set[tuple[int, int]]:
    """The biggest orthogonally connected run of ``color`` on this board.

    The pulled pieces arrive packed around the lotus, so the gathered cluster is
    simply the largest connected component of the colour that fired.
    """
    cells = set(_color_cells(board, color))
    best: set[tuple[int, int]] = set()
    while cells:
        start = cells.pop()
        component = {start}
        stack = [start]
        while stack:
            row, col = stack.pop()
            for step_row, step_col in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                neighbour = (row + step_row, col + step_col)
                if neighbour in cells:
                    cells.discard(neighbour)
                    component.add(neighbour)
                    stack.append(neighbour)
        if len(component) > len(best):
            best = component
    return best


DEFAULT_SNAPSHOT = PROJECT_ROOT / "Debug" / "memory_board" / "latest.json"


def gathered_blob(
    frames: list[dict[str, Any]],
    color: int,
    pre_count: int,
) -> tuple[set[tuple[int, int]], int | None]:
    """The assembled blob and the frame it stands on.

    Picking the frame with the biggest connected component is not safe once the
    trace poll is fast enough to catch mid-flight animation: on 2026-08-21 a
    30 ms poll caught a frame carrying *three* extra pieces of the colour, and
    the frame right after it was back to the real board.

    The pull is swaps, so it conserves the colour exactly, except that the lotus
    converts into it -- ``pre_count + 1``. Frames that do not satisfy that are
    either mid-flight or already past the destruction, and are skipped. Measured
    over 14 recorded lotus moves: 13 hold ``+1`` throughout, and the one that
    does not is the transient described above.
    """
    best: set[tuple[int, int]] = set()
    best_index = None
    for index, frame in enumerate(frames):
        board = frame.get("board") or []
        if sum(1 for row in board for value in row if value == color) != pre_count + 1:
            continue
        candidate = _largest_blob(board, color)
        if len(candidate) > len(best):
            best, best_index = candidate, index
    return best, best_index


def _ability_params(frame: dict[str, Any], fallback: Path | None = None) -> dict[str, Any]:
    """The played booster's tuning params.

    The trace frames carry a reduced player block (no ability config -- it never
    changes mid-move), so the params come from the full snapshot instead. That
    is also why the fallback is a *file*: one read covers every run.
    """
    for player in frame.get("players") or ():
        params = player.get("special_ability_params")
        if isinstance(params, dict) and params:
            return params
    if fallback is None or not fallback.is_file():
        return {}
    try:
        payload = json.loads(fallback.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    snapshot = payload.get("snapshot") if isinstance(payload, dict) else None
    state = (snapshot or payload or {}).get("state") or {}
    for player in state.get("players") or ():
        params = player.get("special_ability_params")
        if isinstance(params, dict) and params:
            return params
    return {}


def _smallest_explaining_radius(
    cells: list[tuple[int, int]],
    lotus: tuple[int, int],
    uses_chebyshev: bool,
) -> int:
    """The radius a region would need for every pulled piece to be inside it."""
    if not cells:
        return 0
    return max(
        (
            max(abs(row - lotus[0]), abs(col - lotus[1]))
            if uses_chebyshev
            else abs(row - lotus[0]) + abs(col - lotus[1])
        )
        for row, col in cells
    )


def measure_run(run: Path, params_fallback: Path | None = None) -> dict[str, Any] | None:
    event = _lotus_event(run)
    if event is None:
        return None
    frames = _load_frames(run)
    if len(frames) < 2:
        return None

    color = event.get("color")
    if color is None:
        return None
    color = int(color)

    before = frames[0]
    board_before = before.get("board") or []
    if not board_before:
        return None

    # The lotus the bot logged is its position *after* the swap; the recording's
    # first frame still shows it where it stood before, so prefer the logged one
    # and fall back to the board when the log did not carry it.
    logged = [tuple(cell) for cell in (event.get("lotus_cells") or ()) if len(cell) == 2]
    lotus = logged[0] if logged else (_lotus_cells(before) or [None])[0]
    if lotus is None:
        return None

    pre_cells = _color_cells(board_before, color)
    # The gathered blob is largest on the frame with the most of that colour
    # standing: after that the cluster is destroyed and refill takes over.
    blob, _blob_index = gathered_blob(frames[1:], color, len(pre_cells))

    # Which frame the blob is complete on, and which one first shows a created
    # special. With a fast enough trace poll these are adjacent, and the gap
    # between them is the frame that says *where* the lotus put its special --
    # the one thing the settled board cannot answer, because gravity has already
    # moved it (see docs/game_mode_logic_from_code.md).
    _blob, blob_offset = gathered_blob(frames[1:], color, len(pre_cells))
    blob_frame = None if blob_offset is None else blob_offset + 1
    seen = {
        (row, col): value
        for row, values in enumerate(before.get("special_board") or [])
        for col, value in enumerate(values)
        if value in CREATED_SPECIALS
    }
    special_frame = None
    special_cells = {}
    for index, frame in enumerate(frames):
        current = {
            (row, col): value
            for row, values in enumerate(frame.get("special_board") or [])
            for col, value in enumerate(values)
            if value in CREATED_SPECIALS
        }
        fresh = {cell: value for cell, value in current.items() if seen.get(cell) != value}
        if fresh and index >= (blob_frame or 0):
            special_frame, special_cells = index, fresh
            break

    params = _ability_params(before, params_fallback)
    config = froggy_gather_config_from_params(params)
    in_region = None
    if config is not None:
        radius, uses_chebyshev = config
        in_region = sum(
            1
            for cell in pre_cells
            if froggy_in_gather_region(cell, lotus, radius, uses_chebyshev)
        )

    uses_chebyshev = True if config is None else config[1]
    return {
        "run": run.name,
        "color": color,
        "lotus": list(lotus),
        "board_size": len(board_before),
        "on_board_before": len(pre_cells),
        "in_gather_region": in_region,
        "blob_size": len(blob),
        "logged_collected": event.get("collected"),
        "config": None if config is None else list(config),
        "radius_needed": _smallest_explaining_radius(pre_cells, lotus, uses_chebyshev),
        "frames": len(frames),
        "blob_frame": blob_frame,
        "special_frame": special_frame,
        "special_cells": {
            f"{cell[0]},{cell[1]}": CREATED_SPECIALS[value]
            for cell, value in special_cells.items()
        },
    }


def iter_runs(root: Path) -> Iterator[Path]:
    if not root.is_dir():
        return
    for run in sorted(root.iterdir()):
        if run.is_dir():
            yield run


def format_record(record: dict[str, Any]) -> str:
    config = record["config"]
    config_text = (
        "nepoznata"
        if config is None
        else f"r={config[0]} {'kvadrat' if config[1] else 'romb'}"
    )
    region = record["in_gather_region"]
    return (
        f"{record['run']}  boja {record['color']} lotus {tuple(record['lotus'])}  "
        f"na tabli {record['on_board_before']}  "
        f"u zoni {'?' if region is None else region}  "
        f"blob {record['blob_size']}  "
        f"log {record['logged_collected']}  "
        f"konfig {config_text}  "
        f"potreban r>={record['radius_needed']}"
        + os.linesep
        + f"      kadrova {record['frames']}  blob u f{record['blob_frame']}  "
        + f"specijal u f{record['special_frame']}: {record['special_cells'] or '-'}"
    )


def summarise(records: list[dict[str, Any]]) -> str:
    if not records:
        return "Nema nijednog lotus poteza u snimcima."
    lines = [f"\n{len(records)} lotus poteza."]
    board_wide = [
        record
        for record in records
        if record["in_gather_region"] is not None
        and record["in_gather_region"] == record["on_board_before"]
    ]
    if board_wide:
        lines.append(
            f"  {len(board_wide)}/{len(records)}: konfigurisana zona pokriva celu "
            "tablu, pa brojanje po zoni i po tabli daju isto."
        )
    mismatched = [
        record
        for record in records
        if record["blob_size"] and record["logged_collected"] not in (None, "")
        # The lotus itself is converted into the colour, so the blob carries one
        # more piece than the pull collected.
        and record["blob_size"] - 1 != int(record["logged_collected"])
    ]
    if mismatched:
        lines.append(f"  {len(mismatched)} poteza gde blob-1 != predvidjeno:")
        for record in mismatched:
            lines.append(f"    {format_record(record)}")
    else:
        lines.append("  Svuda blob-1 == predvidjeno (lotus se i sam pretvara u boju).")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--runs", type=Path, default=DEFAULT_RUNS)
    parser.add_argument("--limit", type=int, default=0, help="0 = sve")
    parser.add_argument(
        "--snapshot",
        type=Path,
        default=DEFAULT_SNAPSHOT,
        help="Snapshot iz kog se citaju parametri bustera",
    )
    parser.add_argument("--json", action="store_true", help="Ispisi sirove zapise")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    records = []
    for run in iter_runs(args.runs):
        record = measure_run(run, args.snapshot)
        if record is None:
            continue
        records.append(record)
        if not args.json:
            print(format_record(record))
        if args.limit and len(records) >= args.limit:
            break
    if args.json:
        print(json.dumps(records, indent=2))
    else:
        print(summarise(records))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
