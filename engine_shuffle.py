"""GameLogic.ShuffleBoard 0x594ceac: what the engine does when no move is left.

Runs when the possible moves, without special pairs, hold no match. It repeats
BoardModel.Shuffle 0x596eeac until the board has no combo and the possible moves
are inside spawnEngine's wanted ranges, or 100 ranged attempts have passed.
Each Shuffle draws one Next per piece (stable OrderBy), then deals the pieces
back in scan order, y outer and x inner. Specials travel with their piece.

Recorded in Laser Matches 20261104_155626 023->024: 7 rounds, 343 draws.
"""
from __future__ import annotations

from engine_refill import UnsupportedRefill

MAX_RANGED_ATTEMPTS = 100
# Pieces the recording shows moving; anything else may be immovable or need slot
# flags the simulator does not hold, so a shuffle over it is not predicted.
_MOVABLE_SPECIALS = (0, 1, 2, 3, 4, 46)


def _possible_moves(board, special, allow_square_matches):
    """Each possible move's matches, in GetPossibleMoves order, without special pairs."""
    import move_strategy as ms

    size = len(board)
    work = [[int(v) for v in row] for row in board]
    for x in range(size):
        for y in range(size):
            for dy, dx in ((1, 0), (0, 1)):
                other_y, other_x = y + dy, x + dx
                if (other_y >= size or other_x >= size or work[y][x] <= 0 or work[other_y][other_x] <= 0
                        or work[y][x] == work[other_y][other_x]):
                    continue
                # MergeTwoLogic.WithoutPairs: two specials merge, they match nothing.
                if int(special[y][x]) and int(special[other_y][other_x]):
                    continue
                work[y][x], work[other_y][other_x] = work[other_y][other_x], work[y][x]
                ends = {(y, x), (other_y, other_x)}
                matches = [match for match in ms.find_matches(work, allow_square_matches, special)
                           if match.cells & ends]
                work[y][x], work[other_y][other_x] = work[other_y][other_x], work[y][x]
                if matches:
                    yield matches


def possible_move_counts(board, special, allow_square_matches=False):
    """(possible moves, the ones the wanted special range counts).

    The second count reads isHighRank, yet the recorded shuffle stopped on a
    board without a high-rank shape, whose only candidates were threes holding a
    special. So those count too: one recording, not read from the engine.
    """
    import move_strategy as ms

    plain = high = 0
    for matches in _possible_moves(board, special, allow_square_matches):
        plain += 1
        high += any(match.kind in ms.FROGGY_HIGH_RANK_SHAPES
                    or any(int(special[row][col]) for row, col in match.cells)
                    for match in matches)
    return plain, high


def has_possible_move(board, special, allow_square_matches=False):
    return next(_possible_moves(board, special, allow_square_matches), None) is not None


def shuffle_board(model, board, special, allow_square_matches=False):
    """(board, special) after ShuffleBoard, drawing from ``model.rng``."""
    import move_strategy as ms

    spawn = (model.profile.get("config") or {}).get("spawnEngine") or {}
    try:
        low, top = int(spawn["wantedPossibleMatchesMin"]), int(spawn["wantedPossibleMatchesMax"])
        special_low = int(spawn["wantedPossibleSpecialMatchesMin"])
        special_top = int(spawn["wantedPossibleSpecialMatchesMax"])
    except (KeyError, TypeError, ValueError) as exc:
        raise UnsupportedRefill("Shuffle: wanted possible matches missing from capture") from exc
    size = len(board)
    cells = [(y, x) for y in range(size) for x in range(size)]
    pieces = [(int(board[y][x]), int(special[y][x])) for y, x in cells]
    if any(color <= 0 or value not in _MOVABLE_SPECIALS for color, value in pieces):
        raise UnsupportedRefill("Shuffle: fixed or unported piece on the board")
    attempts = 0
    while True:
        pieces = model.rng.shuffled(pieces)
        out = [[0] * size for _ in range(size)]
        out_special = [[0] * size for _ in range(size)]
        for (y, x), (color, value) in zip(cells, pieces):
            out[y][x], out_special[y][x] = color, value
        if ms.find_matches(out, allow_square_matches, out_special):
            continue
        plain, high = possible_move_counts(out, out_special, allow_square_matches)
        attempts += 1
        if (low <= plain <= top and special_low <= high <= special_top) or attempts >= MAX_RANGED_ATTEMPTS:
            return out, out_special
