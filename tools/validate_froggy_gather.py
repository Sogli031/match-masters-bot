"""Settle the board a Froggy Fu pull leaves behind, against the engine's own log.

`tools/validate_froggy_pull.py` proves *where the colour lands* (14/14 cell for
cell). What it cannot prove is where the pull leaves everything it pushed out of
the way, and that is what decides the cascades after a lotus. Comparing against
captured frames does not work and cannot be made to work: `Pull` records every
swap through `AttractionMoveRecorder` and the animation plays those out one step
at a time, so no frame ever holds the settled result -- checked against every
frame of every recorded run, the closest was still 5 of 49 cells wrong.

The engine keeps that log itself. `FroggyFu.attractionMoveData` is a
`List<List<Point>>` the agent now reads into each frame as
`froggy.attraction_moves`, and `AttractionMoveRecorder.Record` shows what it
holds -- **not** a list of swaps:

    chain = data.FirstOrDefault(l => l[1] == a)   # an entry ending at a
    if (chain != null) chain[1] = b               # extend it
    else               data.Add([a, b])

so each entry is one piece as `[where it started, where it ended up]`, and the
whole list is a permutation of the cells the gather touched. Applying it gives
the finished board exactly, which is what this compares `froggy_pull_apply`
against.

    python .\tools\validate_froggy_gather.py

Runs recorded before the agent carried `froggy` have no log and are reported as
such rather than counted as agreement.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from move_strategy import (  # noqa: E402
    froggy_gather_config_from_params,
    froggy_pull_apply,
)
from tools.measure_froggy_lotus import (  # noqa: E402
    DEFAULT_RUNS,
    DEFAULT_SNAPSHOT,
    _ability_params,
    _load_frames,
)
from tools.validate_froggy_pull import DEFAULT_CONFIG, check_run  # noqa: E402


def _cell(point: Any) -> tuple[int, int] | None:
    """A logged ``Point`` as a bot cell.

    The agent reads a struct's fields in declaration order, and ``Point``
    declares x then y -- x being the column and y the row, the same convention
    ``readSlot`` uses when it emits ``row: y``.
    """
    if not isinstance(point, (list, tuple)) or len(point) < 2:
        return None
    return (int(point[1]), int(point[0]))


def _parse_moves(froggy: Any) -> list[tuple[tuple[int, int], tuple[int, int]]]:
    if not isinstance(froggy, dict):
        return []
    entries = froggy.get("attraction_moves")
    if not isinstance(entries, list):
        return []
    moves = []
    for entry in entries:
        if not isinstance(entry, list) or len(entry) < 2:
            continue
        source, destination = _cell(entry[0]), _cell(entry[1])
        if source is None or destination is None:
            continue
        moves.append((source, destination))
    return moves


def recorded_gather(
    frames: list[dict[str, Any]],
) -> list[tuple[tuple[int, int], tuple[int, int]]]:
    """This move's gather log, or nothing.

    `attractionMoveData` survives between moves -- `CleanupState` clears it at
    the end of a resolve -- so simply taking the longest log in the run picks up
    the *previous* lotus often enough to matter: of nine recorded moves it chose
    a stale log five times, and every one of those disagreed with a pull model
    that the other four confirmed exactly.

    The log is therefore taken from the last frame that carries one, and only
    when it is a permutation: every cell it moves a piece out of is a cell it
    moves a piece into. A stale log mixed with the current board is not.
    """
    for frame in reversed(frames):
        moves = _parse_moves(frame.get("froggy"))
        if not moves:
            continue
        sources = [source for source, _ in moves]
        destinations = [destination for _, destination in moves]
        if len(set(sources)) == len(sources) and set(sources) == set(destinations):
            return moves
    return []


def replay(
    board: list[list[int]],
    moves: list[tuple[tuple[int, int], tuple[int, int]]],
) -> list[list[int]]:
    """The board the gather leaves behind.

    Each entry is `[from, to]` for one piece, so the list is applied as a
    permutation against the original board rather than as a sequence.
    """
    result = [list(row) for row in board]
    for (source_row, source_col), (target_row, target_col) in moves:
        result[target_row][target_col] = board[source_row][source_col]
    return result


def check_gather(run: Path, snapshot: Path | None) -> dict[str, Any] | None:
    record = check_run(run, snapshot)
    if record is None or not record["match"] or len(record["firing"]) != 1:
        return None
    frames = _load_frames(run)
    steps = recorded_gather(frames)
    move = json.loads((run / "move.json").read_text(encoding="utf-8")) or {}
    best = move.get("best_move") or {}
    start, target = best.get("start"), best.get("target")
    board = [list(row) for row in (move.get("board") or [])]
    if not board or not start or not target:
        return None
    board[start[0]][start[1]], board[target[0]][target[1]] = (
        board[target[0]][target[1]],
        board[start[0]][start[1]],
    )
    if not steps:
        return {"run": run.name, "steps": 0, "verdict": "nema zapisa"}

    radius, uses_chebyshev = (
        froggy_gather_config_from_params(_ability_params(frames[0], snapshot))
        or DEFAULT_CONFIG
    )
    _landed, modelled, _specials = froggy_pull_apply(
        board, record["firing"][0], record["color"], radius, uses_chebyshev
    )
    engine = replay(board, steps)
    # The model rewrites the lotus cell (RunPullAndConvertLotus); the swap log
    # does not, because that write is not a swap.
    lotus = record["firing"][0]
    engine[lotus[0]][lotus[1]] = record["color"]
    wrong = [
        (row, col, modelled[row][col], engine[row][col])
        for row in range(len(modelled))
        for col in range(len(modelled[row]))
        if modelled[row][col] != engine[row][col]
    ]
    return {
        "run": run.name,
        "steps": len(steps),
        "wrong": wrong,
        "verdict": "OK" if not wrong else "RAZLIKA",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, default=DEFAULT_RUNS)
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    args = parser.parse_args(argv)

    checked = matched = blind = 0
    for run in sorted(args.runs.iterdir()) if args.runs.is_dir() else []:
        if not run.is_dir():
            continue
        record = check_gather(run, args.snapshot)
        if record is None:
            continue
        if record["verdict"] == "nema zapisa":
            blind += 1
            continue
        checked += 1
        matched += 1 if record["verdict"] == "OK" else 0
        print(
            f"{record['run']}  {record['steps']} pomerenih  {record['verdict']}"
            + (f"  pogresnih celija: {len(record['wrong'])}" if record["wrong"] else "")
        )
        for row, col, model_value, engine_value in record["wrong"][:8]:
            print(f"   ({row}, {col}) model={model_value} engine={engine_value}")

    print(f"\n{matched}/{checked} tabli tacno")
    if blind:
        print(
            f"{blind} lotus poteza bez `froggy.attraction_moves` -- snimljeni pre nego"
            " sto je agent citao taj zapis; odigraj jednu Froggy Fu partiju sa"
            " ukljucenim Debug-om pa ponovo pokreni ovo."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
