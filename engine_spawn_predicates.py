"""Field-only equivalents of Square Match spawn checks (engine color space).

Evidence: BoardAnalyzer IsPartOfCombo 0x592a174/0x592a9dc,
IsPartOfPossibleHighrankCombo 0x592c95c/0x592d25c and helper 0x592d454.
The two pattern source literals were resolved from matching 5.817 metadata.
Grid storage is board[y][x]; cells may be color integers or SlotModel dicts.
"""
from __future__ import annotations

from functools import lru_cache


_TEMPLATES = {1: "12\n12\n21\n12", 2: "-12-\n1--2\n1122"}


def _get(board, x, y):
    return board[y][x] if 0 <= y < len(board) and 0 <= x < len(board[y]) else None


def _color(cell):
    return int(cell.get("color", 0)) if isinstance(cell, dict) else int(cell or 0)


def _color2(cell):
    return int(cell.get("color2", 1)) if isinstance(cell, dict) else 1


def _matchable(cell):
    return bool(cell.get("canBeMatched", _color(cell) > 1)) if isinstance(cell, dict) else _color(cell) > 1


def _has_color(cell):
    if cell is None:
        return False
    value = int(cell.get("value", 0)) if isinstance(cell, dict) else 0
    if value == 0 or 4 <= value <= 8 or 11 <= value <= 13 or 17 <= value <= 19:
        return True
    if 23 <= value < 41:
        return value < 34 and bool((0x221800000 >> value) & 1)
    return _color(cell) > 1


def matches_with_color(cell, color):
    """SlotModel.MatchesWithColor, including secondary color and All=12."""
    primary = _color(cell)
    return (_has_color(cell) and color not in (0, 1) and primary not in (0, 1)
            and (primary == color or primary == 12 or _color2(cell) == color))


def _target_colors(cell):
    primary, secondary = _color(cell), _color2(cell)
    return (primary,) if secondary in (0, 1) else (primary, secondary)


def _axis_combo(board, x, y, color, dx, dy):
    # The native method stops as soon as its accumulator reaches three.
    count = 1
    for sign in (1, -1):
        step = 1
        while matches_with_color(_get(board, x + dx * step * sign, y + dy * step * sign), color):
            count += 1
            if count == 3:
                return True
            step += 1
    return False


def is_part_of_square(board, x, y):
    center = _get(board, x, y)
    if not _matchable(center):
        return False
    for color in _target_colors(center):
        for left in (x - 1, x):
            for top in (y - 1, y):
                cells = [_get(board, xx, yy) for yy in (top, top + 1) for xx in (left, left + 1)]
                if all(_matchable(cell) and matches_with_color(cell, color) for cell in cells):
                    return True
    return False


def combo_count_at(board, x, y, *, square=True):
    """Return the spawn comparator's count: 0, 3, or square witness 4.

    Native out-count saturates at 3 for an axis. A square ComboModel has
    at least 4 positions; this function returns the equivalent threshold
    witness 4, not a promised size for overlapping square clusters.
    The spawn caller only tests >3, so that distinction is immaterial there.
    """
    center = _get(board, x, y)
    if not _matchable(center):
        return 0
    for dx, dy in ((0, 1), (1, 0)):
        for color in _target_colors(center):
            if _axis_combo(board, x, y, color, dx, dy):
                return 3
    return 4 if square and is_part_of_square(board, x, y) else 0


def is_part_of_combo(board, x, y, *, square=True):
    return combo_count_at(board, x, y, square=square) > 0


@lru_cache(maxsize=2)
def highrank_patterns(rank):
    """Pattern offsets, including four rotations and every-point anchoring.

    GetPossiblePatterns(template,2,true,true) generates digit groups then
    rotates. BoardAnalyzer subsequently subtracts every member of every
    generated pattern to put each of the four positions at the query cell.
    Cropping translations cancel out in this final anchoring step.
    """
    if rank not in _TEMPLATES:
        return ()
    text = _TEMPLATES[rank].splitlines()
    patterns = []
    for digit in ("1", "2"):
        points = [(x, y) for y, line in enumerate(text) for x, char in enumerate(line) if char == digit]
        for rotation in range(4):
            transformed = points
            for _ in range(rotation):
                transformed = [(-y, x) for x, y in transformed]
            for ax, ay in transformed:
                patterns.append(tuple((px - ax, py - ay) for px, py in transformed))
    return tuple(patterns)


def is_part_of_possible_highrank_combo(board, x, y, rank):
    """rank=1: four-sequence move pattern; rank=2: square move pattern.

    Checks the literal-derived arrangement, not all hypothetical swaps.
    Every pattern cell must exist, canBeMatched, and match the query color.
    No movable test occurs in the native IsPatternMatching helper.
    """
    center = _get(board, x, y)
    for color in _target_colors(center):
        for pattern in highrank_patterns(rank):
            if all(_matchable(cell := _get(board, x + dx, y + dy))
                   and matches_with_color(cell, color) for dx, dy in pattern):
                return True
    return False
