"""Check *where* the Froggy Fu lotus leaves its special, against recordings.

`tools/validate_froggy_pull.py` proves the gathered blob cell for cell. This is
the step after it: `move_strategy.froggy_blob_special` says which cell of that
blob the new special is created on, decoded from

    FroggyFu.DestroyResolveCluster -> ComputeBlobSpecials -> BuildMegaCombo
    BoardAnalyzer.GetAllCombos -> GetCombosFromTestList -> BlobMatchChecker

The recordings cannot show that cell directly. As measured on 2026-08-21, the
frame in which the blob stands assembled holds no new special at all: the
special is created in the same step that destroys the cluster, and the next
frame already has gravity in it. What survives gravity is the **column** -- a
piece only ever falls straight down -- so that is what is checked here:

    the special must show up in the predicted column, at or below the
    predicted row.

Runs where a frame happens to be caught before the fall also match the cell
exactly; those are counted separately and printed.

    python .\tools\validate_froggy_special.py
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from move_strategy import (  # noqa: E402
    SPECIAL_BOMB,
    SPECIAL_HORIZONTAL,
    SPECIAL_LIGHTNING,
    SPECIAL_VERTICAL,
    froggy_blob_special,
    froggy_gather_config_from_params,
    froggy_resolve_lotuses,
)
from tools.measure_froggy_lotus import (  # noqa: E402
    DEFAULT_RUNS,
    DEFAULT_SNAPSHOT,
    _ability_params,
    _load_frames,
)
from tools.validate_froggy_pull import DEFAULT_CONFIG, check_run  # noqa: E402

# Which piece each combo shape leaves behind. A four can come out as either
# axis, so both count as a hit.
SHAPE_SPECIALS: dict[str, frozenset[int]] = {
    "five": frozenset({SPECIAL_LIGHTNING}),
    "square": frozenset({SPECIAL_LIGHTNING}),
    "l": frozenset({SPECIAL_BOMB}),
    "t_or_cross": frozenset({SPECIAL_BOMB}),
    "four": frozenset({SPECIAL_HORIZONTAL, SPECIAL_VERTICAL}),
}


def _specials_gained(frames: list[dict[str, Any]], wanted: frozenset[int]):
    """Cells holding a special of ``wanted`` in a frame that has more of them.

    Counting by type rather than by cell is deliberate: the pull moves existing
    specials around, so a bomb showing up on a new cell proves nothing unless
    there are more bombs than before.
    """
    base = Counter(
        value
        for row in (frames[0].get("special_board") or [])
        for value in row
        if value in wanted
    )
    cells: set[tuple[int, int]] = set()
    for frame in frames[1:]:
        board = frame.get("special_board") or []
        counts = Counter(
            value for row in board for value in row if value in wanted
        )
        grown = {kind for kind in wanted if counts[kind] > base[kind]}
        if not grown:
            continue
        cells |= {
            (row, col)
            for row, values in enumerate(board)
            for col, value in enumerate(values)
            if value in grown
        }
    return cells


def check_special(run: Path, snapshot: Path | None) -> dict[str, Any] | None:
    record = check_run(run, snapshot)
    if record is None or not record["match"]:
        return None
    frames = _load_frames(run)
    move = json.loads((run / "move.json").read_text(encoding="utf-8")) or {}
    board = [list(row) for row in (move.get("board") or [])]
    best = move.get("best_move") or {}
    start, target = best.get("start"), best.get("target")
    if not board or not start or not target:
        return None
    board[start[0]][start[1]], board[target[0]][target[1]] = (
        board[target[0]][target[1]],
        board[start[0]][start[1]],
    )
    radius, uses_chebyshev = (
        froggy_gather_config_from_params(_ability_params(frames[0], snapshot))
        or DEFAULT_CONFIG
    )
    resolved = froggy_resolve_lotuses(
        board, record["firing"], record["color"], radius, uses_chebyshev
    )
    allow_squares = bool(move.get("allow_square_matches"))
    predicted = [froggy_blob_special(blob, allow_squares) for _, blob in resolved]
    first = next((entry for entry in predicted if entry), None)
    if first is None:
        return {"run": run.name, "predicted": None, "verdict": "bez specijala"}
    cell, shape = first
    observed = _specials_gained(frames, SHAPE_SPECIALS.get(shape, frozenset()))
    column = sorted(
        found
        for found in observed
        if found[1] == cell[1] and found[0] >= cell[0]
    )
    return {
        "run": run.name,
        "predicted": (cell, shape),
        "observed": sorted(observed),
        "column": column,
        "exact": cell in observed,
        "verdict": "OK" if column else ("nema podataka" if not observed else "RAZLIKA"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, default=DEFAULT_RUNS)
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    args = parser.parse_args(argv)

    checked = matched = exact = blind = 0
    for run in sorted(args.runs.iterdir()) if args.runs.is_dir() else []:
        if not run.is_dir():
            continue
        record = check_special(run, args.snapshot)
        if record is None or record["predicted"] is None:
            continue
        checked += 1
        if record["verdict"] == "OK":
            matched += 1
            exact += 1 if record["exact"] else 0
        elif record["verdict"] == "nema podataka":
            blind += 1
        cell, shape = record["predicted"]
        print(
            f"{record['run']}  model {cell} {shape}  {record['verdict']}"
            f"  kolona: {record['column']}  svi: {record['observed']}"
            + ("  (celija tacna)" if record["exact"] else "")
        )
    testable = checked - blind
    print(
        f"\n{matched}/{testable} poklapanja po koloni"
        f" ({exact} od toga i po celiji); {blind} runova bez snimljenog specijala"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
