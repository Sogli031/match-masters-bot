"""Offline verification of entrance RNG and candidate destruction/refill.

python tools/validate_froggy_entrance.py

Matching an attempt against the result is an oracle check, NOT a prediction of
which attempt wins. Lotus cells are excluded; placement and cascades are not
implemented here. Generation uses only the BEFORE capture and an explicit
one-based activation index; the AFTER capture is used only for comparison.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import move_strategy as ms
from engine_froggy import preview_entrance
from engine_refill import EngineRefill, simulator_refill

RECORDINGS = {
    "20261104_052333_moves-multiplier": (3, 6, 11, 16),
    "20261104_054022_moves-multiplier": (2, 5, 14, 17),
}


def check_entrance(before, after, activation):
    preview = preview_entrance(before["profile"], before["raw_slots"],
                               activation=activation, preferred_color_fix=True)
    actual = after["profile"]["froggy_booster_fields"]
    settings_match = all((
        preview.prefer_energy_adjacent == actual["preferEnergyAdjacentThisActivation"],
        preview.mushroom_target == actual["entranceMushroomTargetThisActivation"],
        preview.destroy_count == actual["entranceDestroyCountThisActivation"],
        preview.high_score_ratio == actual["highScorePieceRatioThisActivation"],
        preview.preferred_color == actual["rolledPreferredColorThisActivation"],
    ))
    matches = []
    minimum_diff = None
    for i, targets in enumerate(preview.attempts):
        board = [list(map(int, row)) for row in before["board"]]
        special = [list(map(int, row)) for row in before["special_board"]]
        for y, x in targets:
            board[y][x] = ms.EMPTY
            special[y][x] = 0
        origins = [[None] * len(row) for row in board]
        board, special, _ = ms._drop_boards_with_origins(board, special, origins)
        model = EngineRefill.from_profile(before["profile"])
        model.rng = preview.rng_after.clone()
        model.reset_action()
        board, special = simulator_refill(model)(board, special, 0)
        diff = sum(
            int(board[y][x]) != int(value) or int(special[y][x]) != int(after["special_board"][y][x])
            for y, row in enumerate(after["board"]) for x, value in enumerate(row)
            if int(after["special_board"][y][x]) != ms.SPECIAL_FROGGY_LOTUS)
        minimum_diff = diff if minimum_diff is None else min(minimum_diff, diff)
        if diff == 0 and model.rng.to_capture() == after["profile"]["rng"]:
            matches.append(i)
    return {"settings_match": settings_match, "matching_attempts": matches,
            "minimum_cell_diff": minimum_diff,
            "generated_attempts": len(preview.attempts)}


def main():
    settings_ok = boards_ok = total = 0
    for game, transitions in RECORDINGS.items():
        for activation, index in enumerate(transitions, 1):
            paths = [ROOT / "Debug" / "research" / game / f"{i:03}.json"
                     for i in (index, index + 1)]
            if not all(p.exists() for p in paths):
                print(f"{game}/{index:03}: snimak nedostaje")
                continue
            before, after = [json.loads(p.read_text(encoding="utf-8")) for p in paths]
            result = check_entrance(before, after, activation)
            settings_ok += result["settings_match"]
            boards_ok += bool(result["matching_attempts"])
            total += 1
            print(f"{game}/{index:03}: {json.dumps(result)}")
    print(f"Parametri {settings_ok}/{total}; postoji pokusaj sa tacnom tablom i celim RNG stanjem "
          f"{boards_ok}/{total}. Izbor pobednika, postavljanje lotusa i kaskade nisu provereni.")
    return int(total == 0 or settings_ok != total)


if __name__ == "__main__":
    raise SystemExit(main())
