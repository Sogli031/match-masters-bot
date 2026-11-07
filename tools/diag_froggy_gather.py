"""Put the model's gather next to the engine's own log, step by step.

`validate_froggy_gather.py` answers whether the settled board matches;
this answers *where* the two stop agreeing, which is what a decoding pass
needs. It prints the board the lotus fires on, the engine's
`attractionMoveData` permutation, and the (piece -> target) sequence the
model performs, so a disagreement can be read back against the disassembly.

    python .\tools\diag_froggy_gather.py --run 2026-08-21_15-26-18_195
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from move_strategy import (  # noqa: E402
    _froggy_pull_run,
    froggy_gather_config_from_params,
)
from tools.measure_froggy_lotus import (  # noqa: E402
    DEFAULT_RUNS,
    DEFAULT_SNAPSHOT,
    _ability_params,
    _load_frames,
)
from tools.validate_froggy_gather import recorded_gather, replay  # noqa: E402
from tools.validate_froggy_pull import DEFAULT_CONFIG, check_run  # noqa: E402


def _show(board: list[list[int]]) -> str:
    return "\n".join("  " + " ".join(f"{value:2d}" for value in row) for row in board)


def diagnose(run: Path, snapshot: Path | None) -> None:
    record = check_run(run, snapshot)
    if record is None or not record["match"] or len(record["firing"]) != 1:
        print(f"{run.name}: nije jedan lotus potez")
        return
    frames = _load_frames(run)
    steps = recorded_gather(frames)
    move = json.loads((run / "move.json").read_text(encoding="utf-8")) or {}
    best = move.get("best_move") or {}
    start, target = best.get("start"), best.get("target")
    board = [list(row) for row in (move.get("board") or [])]
    board[start[0]][start[1]], board[target[0]][target[1]] = (
        board[target[0]][target[1]],
        board[start[0]][start[1]],
    )
    lotus = record["firing"][0]
    color = record["color"]
    radius, uses_chebyshev = (
        froggy_gather_config_from_params(_ability_params(frames[0], snapshot))
        or DEFAULT_CONFIG
    )

    print(f"== {run.name}  lotus={lotus}  boja={color}  r={radius} cheb={uses_chebyshev}")
    print("tabla posle zamene:")
    print(_show(board))

    moves, ring, modelled, _specials = _froggy_pull_run(
        board, lotus, color, radius, uses_chebyshev
    )
    print(f"\nring (ne mrda se): {sorted(ring)}")
    print("model, potez po potez:")
    for index, (piece, cell) in enumerate(moves):
        print(f"  {index:2d}  {piece} -> {cell}")

    print("\nengine zapis (permutacija, odakle -> dokle):")
    engine_moves = {source: destination for source, destination in steps}
    for source, destination in steps:
        print(f"      {source} -> {destination}")

    model_perm = {}
    work = [list(row) for row in board]
    print("\nrazlike u dodeli (samo pomerene plocice):")
    for piece, cell in moves:
        model_perm[piece] = cell
    for source in sorted(set(model_perm) | set(engine_moves)):
        mine = model_perm.get(source)
        theirs = engine_moves.get(source)
        if mine != theirs:
            print(f"      {source}: model -> {mine}   engine -> {theirs}")

    if steps:
        engine_board = replay(board, steps)
        engine_board[lotus[0]][lotus[1]] = color
        modelled[lotus[0]][lotus[1]] = color
        wrong = [
            (row, col)
            for row in range(len(modelled))
            for col in range(len(modelled[row]))
            if modelled[row][col] != engine_board[row][col]
        ]
        print(f"\nmodel ({len(wrong)} pogresnih):")
        print(_show(modelled))
        print("engine:")
        print(_show(engine_board))
        print(f"pogresne celije: {wrong}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, default=DEFAULT_RUNS)
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    parser.add_argument("--run", default=None, help="ime jednog runa")
    args = parser.parse_args(argv)

    for run in sorted(args.runs.iterdir()) if args.runs.is_dir() else []:
        if not run.is_dir():
            continue
        if args.run and run.name != args.run:
            continue
        diagnose(run, args.snapshot)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
