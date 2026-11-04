"""Replay every recorded lotus move through the real simulator.

`validate_froggy_gather.py` proves the board the *pull* leaves behind.
This asks the next question: does `simulate_candidate` -- the thing move
selection actually runs -- now produce that board, destroy the cluster, put the
created special where the engine put it, and hand back the extra move the game
handed back?

Three of the four answers come from the same recordings the gather validator
uses; the fourth, the extra move, comes from `observed_delta.json`'s
`state_delta.kept_the_turn`, which is what the game really did with the turn.

    python .\tools\validate_froggy_simulation.py
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

import move_strategy as strategy  # noqa: E402
from tools.measure_froggy_lotus import (  # noqa: E402
    DEFAULT_RUNS,
    DEFAULT_SNAPSHOT,
    _ability_params,
    _load_frames,
)
from tools.validate_froggy_pull import DEFAULT_CONFIG, check_run  # noqa: E402


def _direction(start: tuple[int, int], target: tuple[int, int]) -> Any:
    row_delta = target[0] - start[0]
    if row_delta:
        return strategy.Direction.DOWN if row_delta > 0 else strategy.Direction.UP
    return (
        strategy.Direction.RIGHT
        if target[1] - start[1] > 0
        else strategy.Direction.LEFT
    )


def check_simulation(run: Path, snapshot: Path | None) -> dict[str, Any] | None:
    record = check_run(run, snapshot)
    if record is None or not record["match"] or len(record["firing"]) != 1:
        return None
    frames = _load_frames(run)
    move = json.loads((run / "move.json").read_text(encoding="utf-8")) or {}
    best = move.get("best_move") or {}
    start, target = best.get("start"), best.get("target")
    board = [list(row) for row in (move.get("board") or [])]
    special_board = [list(row) for row in (move.get("special_board") or [])]
    if not board or not special_board or not start or not target:
        return None
    start, target = tuple(start), tuple(target)
    radius, uses_chebyshev = (
        strategy.froggy_gather_config_from_params(_ability_params(frames[0], snapshot))
        or DEFAULT_CONFIG
    )
    allow_square = bool(move.get("allow_square_matches"))

    swapped, swapped_special = strategy.swap_cells(
        board, special_board, start, target
    )
    candidate = strategy.MoveCandidate(
        start=start,
        target=target,
        direction=_direction(start, target),
        board=swapped,
        special_board=swapped_special,
    )
    with strategy.froggy_gather_region_active(radius, uses_chebyshev):
        result = strategy.simulate_candidate(
            candidate, allow_square_matches=allow_square
        )

    lotus = tuple(record["firing"][0])
    color = record["color"]
    expected_blob = strategy.froggy_pull_landing_cells(
        candidate.board, lotus, color, radius, uses_chebyshev
    )
    expected_special = strategy.froggy_blob_special(expected_blob, allow_square)

    gathered = bool(result.froggy_lotus_gathered)
    blob_match = None
    for match in result.cascade_matches[0] if result.cascade_matches else []:
        if set(match.cells) == set(expected_blob):
            blob_match = match
            break

    created_cells = {
        tuple(event.get("cell", ()))
        for event in result.intent_events
        if event.get("type") == "special_creation" and event.get("cascade") == 1
    }

    observed = run / "observed_delta.json"
    kept_the_turn = None
    if observed.exists():
        kept_the_turn = (
            (json.loads(observed.read_text(encoding="utf-8")).get("state_delta") or {})
        ).get("kept_the_turn")

    problems = []
    if not gathered:
        problems.append("lotus nije opalio u simulaciji")
    if blob_match is None:
        problems.append("blob nije predat rusenju kao jedan combo")
    if expected_special is not None and expected_special[0] not in created_cells:
        problems.append(
            f"specijal nije na {expected_special[0]} (sim: {sorted(created_cells)})"
        )
    if expected_special is None and created_cells:
        problems.append(f"sim pravi specijal a engine ne: {sorted(created_cells)}")
    if kept_the_turn and result.extra_moves < 1:
        problems.append("igra je zadrzala potez, sim ne obecava extra")
    if kept_the_turn is False and result.extra_moves >= 1:
        problems.append("sim obecava extra, igra je izgubila potez")

    return {
        "run": run.name,
        "gathered": gathered,
        "blob": len(expected_blob),
        "cleared": float(result.cleared_cells),
        "blue": float(result.blue_cells),
        "extra": float(result.extra_moves),
        "kept_the_turn": kept_the_turn,
        "special": expected_special[0] if expected_special else None,
        "problems": problems,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, default=DEFAULT_RUNS)
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    args = parser.parse_args(argv)

    checked = clean = 0
    for run in sorted(args.runs.iterdir()) if args.runs.is_dir() else []:
        if not run.is_dir():
            continue
        record = check_simulation(run, args.snapshot)
        if record is None:
            continue
        checked += 1
        clean += 1 if not record["problems"] else 0
        print(
            f"{record['run']}  blob={record['blob']:2}"
            f"  ocisceno={record['cleared']:5.1f}  plavo={record['blue']:4.1f}"
            f"  extra={record['extra']:3.1f}"
            f"  zadrzan potez={record['kept_the_turn']}"
            f"  specijal={record['special']}"
            f"  {'OK' if not record['problems'] else 'PROBLEM'}"
        )
        for problem in record["problems"]:
            print(f"   {problem}")

    print(f"\n{clean}/{checked} lotus poteza simulirano bez zamerke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
