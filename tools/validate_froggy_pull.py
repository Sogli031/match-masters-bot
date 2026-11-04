"""Check the decoded Froggy Fu pull against recorded games.

`move_strategy.froggy_pull_landing_cells` is a reimplementation of
``UnifiedFroggyFuAttractionPlanner`` read out of `libil2cpp.so`. This proves it
against reality: `Debug/runs/<run>/memory_frames.jsonl` keeps frames captured
*during* the cascade, and a lotus move shows the pulled pieces gathered into a
blob before they are destroyed. The blob is the model's output, observed.

    python .\tools\validate_froggy_pull.py

As of 2026-08-21 this reports 8 of 8 recorded moves reproduced cell for cell.
Any run that differs is printed in full rather than smoothed over.
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
    froggy_blob_special_shape,
    froggy_firing_lotuses,
    froggy_lotus_after_swap,
    froggy_resolve_lotuses,
)
from move_strategy import SPECIAL_FROGGY_LOTUS  # noqa: E402
from tools.measure_froggy_lotus import (  # noqa: E402
    DEFAULT_RUNS,
    gathered_blob,
    DEFAULT_SNAPSHOT,
    _ability_params,
    _largest_blob,
    _load_frames,
    _lotus_event,
)
from move_strategy import froggy_gather_config_from_params  # noqa: E402

DEFAULT_CONFIG = (7, True)


def check_run(run: Path, snapshot: Path | None) -> dict[str, Any] | None:
    event = _lotus_event(run)
    if event is None:
        return None
    frames = _load_frames(run)
    if len(frames) < 2:
        return None
    move_path = run / "move.json"
    try:
        move = json.loads(move_path.read_text(encoding="utf-8")) or {}
    except (OSError, json.JSONDecodeError):
        return None
    best = move.get("best_move") or {}
    start, target = best.get("start"), best.get("target")
    logged = [tuple(cell) for cell in (event.get("lotus_cells") or ()) if len(cell) == 2]
    if not (start and target and logged):
        return None

    # `move.json` carries the board the decision was actually made on. The trace
    # frames must not be used for that: `memory_frames.jsonl` starts at the
    # first *poll*, which -- depending on latency -- may already be past the
    # swap. Reading frame 0 as "before" and applying the swap on top of it
    # undoes a swap that already happened, which is what made this check report
    # 7/8 until 2026-08-21.
    board = [list(row) for row in (move.get("board") or [])]
    if not board:
        return None
    board[start[0]][start[1]], board[target[0]][target[1]] = (
        board[target[0]][target[1]],
        board[start[0]][start[1]],
    )

    # FroggyFu.SyncLotusPositionsForUserSwap: a swap that moves the lotus itself
    # updates where it resolves, so the logged (pre-swap) cell is not where the
    # pull is centred.
    lotus = froggy_lotus_after_swap(logged[0], tuple(start), tuple(target))
    color = int(event["color"])
    config = froggy_gather_config_from_params(_ability_params(frames[0], snapshot))
    radius, uses_chebyshev = config or DEFAULT_CONFIG
    # Two lotuses per activation is the norm (`lotusCountByActivation` is 2), so
    # resolve every one the match sets off, in order, and let the shared
    # alreadyPulled set keep them off each other's cells. Falls back to the
    # bot's own logged lotus when the recording carries no match event.
    special_board = [list(row) for row in (move.get("special_board") or [])]
    if special_board:
        special_board[start[0]][start[1]], special_board[target[0]][target[1]] = (
            special_board[target[0]][target[1]],
            special_board[start[0]][start[1]],
        )
    on_board = [
        (row, col)
        for row, values in enumerate(special_board)
        for col, value in enumerate(values)
        if value == SPECIAL_FROGGY_LOTUS
    ]
    match_cells = next(
        (
            event.get("cells") or ()
            for event in best.get("intent_events") or ()
            if event.get("type") == "match"
        ),
        (),
    )
    firing = froggy_firing_lotuses(on_board, match_cells) if match_cells else []
    if not firing:
        firing = [lotus]
    resolved = froggy_resolve_lotuses(board, firing, color, radius, uses_chebyshev)
    predicted = set().union(*(blob for _, blob in resolved)) if resolved else set()
    # Colour count is conserved by the pull apart from the converted lotus, so
    # that is what identifies the assembled frame -- not "biggest blob", which a
    # fast poll can win with a mid-flight frame (see gathered_blob).
    pre_count = sum(1 for row in board for value in row if value == color)
    observed, _index = gathered_blob(frames[1:], color, pre_count)
    return {
        "run": run.name,
        "color": color,
        "lotus": lotus,
        "firing": firing,
        "shapes": [
            (lot, froggy_blob_special_shape(blob, bool(move.get("allow_square_matches"))))
            for lot, blob in resolved
        ],
        "match": predicted == observed,
        "model_only": sorted(predicted - observed),
        "recording_only": sorted(observed - predicted),
        "predicted": len(predicted),
        "observed": len(observed),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, default=DEFAULT_RUNS)
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    args = parser.parse_args(argv)

    checked = matched = 0
    for run in sorted(args.runs.iterdir()) if args.runs.is_dir() else []:
        if not run.is_dir():
            continue
        record = check_run(run, args.snapshot)
        if record is None:
            continue
        checked += 1
        matched += 1 if record["match"] else 0
        verdict = "OK" if record["match"] else "RAZLIKA"
        print(
            f"{record['run']}  boja {record['color']}  lotus {record['lotus']}  "
            f"{verdict}  model={record['predicted']} snimak={record['observed']}"
            f"  pale: {record['firing']}  oblici: {record['shapes']}"
        )
        if not record["match"]:
            print(f"   samo u modelu: {record['model_only']}")
            print(f"   samo u snimku: {record['recording_only']}")
    print(f"\n{matched}/{checked} poklapanja celija po celiju")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
