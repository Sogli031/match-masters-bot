"""Billie Boom (41) activation: the drone, then the two sucked colours.

Match3Engine.BillieBoom::Use 0x5a12fd0 ->
  ConvertBillieBoomPiece 0x5a13268   one BillieBoomPiece on the board
  ConvertSlots(ConversionModel(..., 41))
  SuckAndConvertByScoreTarget 0x5a1345c
  SuckAndConvert 0x5a13d20

What the code says (listings in Debug/reverse/billie_boom):

* DronePiecePosition 0x5a127f8 draws nothing: the drone already on the board
  keeps its cell; otherwise Point(x = Rows / 2, y = Columns - 1) when that
  slot is a plain piece, else the first board cell (ForEach + Sort) that is.
  ConvertBillieBoomPiece clones that slot, ToSpecial(25 = BillieBoomPiece) and
  converts it in.
* GetColorGroups 0x5a12bfc adds [Orange 6, Green 3, Yellow 5, Purple 7,
  White 8] in that order and keeps the colours on the board, then every group
  of ColorsToRemoveThisTurn (= ColorsToRemoveByActivation[2]) of them.
* SuckAndConvertByScoreTarget orders those groups by
  |score of destroying the group on a GameLogic clone - Ability::GetScoreTarget|
  and takes the First. The Chance before the pick reads this[0x6c] =
  chanceToPickRandomColors (offset 108), which is -1 in the captured config,
  so it never fires and the score alone decides.
* SuckAndConvert clones every plain piece of the chosen colours, sets its
  value to Normal (0), ConversionType 2, and converts: the pieces are
  destroyed (suckSpecials is false, so specials on those cells stay).

The recorded Solo Super Sized game (2026-11-20 112013, 14 activations) puts
the drone on (7, 4) in 13 of 14 and on (7, 5) once, when (7, 4) was not a
plain piece -- the nearest-cell fallback below.
"""
from __future__ import annotations

from itertools import combinations

from engine_refill import UnsupportedRefill

# Every real SlotColor, in enum order (None 1, Empty 0 and All 12 excluded).
# Measured 2026-11-20 on the Solo Super Sized game: 006->007 sucks Red+Blue and
# 017->018 Red+Orange, both exactly; restricting the list to Orange/Green/
# Yellow/Purple/White (what GetColorGroups' literals first looked like) missed
# every activation, so those literals are not the candidate colours.
BILLIE_COLORS = (2, 3, 4, 5, 6, 7, 8)   # Red, Green, Blue, Yellow, Orange, Purple, White
# Rewritten in SlotValueType: Match3Engine.SlotValue 25 = BillieBoomPiece.
BILLIE_DRONE = 14                    # simulator special for the drone
DRONE_SLOT_VALUE = 25


PVP_MODES = {0: "Versus", 1: "Solo", 2: "Rumble"}


def _pair(entry) -> tuple[str, object] | None:
    """One additionalParams entry (serialized KeyValuePair) as (key, value)."""
    if not isinstance(entry, dict):
        return None
    key = entry.get("<key>k__BackingField")
    return (key, entry.get("<value>k__BackingField")) if key is not None else None


def params(model) -> dict:
    """additionalParams with the match's conditional override applied.

    SpecialAbility..ctor AddRange-s the segments whose Includes() passes, and
    ReadIntListParam takes the first key, so an override wins over the base
    value. Solo's segment raises scoreTarget 16 -> 24 (BillieBoom config); the
    2026-11-20 game is Solo Super Sized, so 24 is the target the pick uses.
    """
    config = (((model.profile.get("ability_detail") or {}).get("fields") or {})
              .get("<Config>k__BackingField") or {}) if model is not None else {}
    out = {}
    for entry in config.get("additionalParams") or ():
        pair = _pair(entry)
        if pair is not None:
            out[pair[0]] = pair[1]
    mode = PVP_MODES.get((model.profile.get("rules") or {}).get("pvpMode"))
    for segment in config.get("conditionalOverrides") or ():
        if not isinstance(segment, dict) or segment.get("pvpMode") != mode:
            continue
        if segment.get("rulesId") or segment.get("modeId") or segment.get("powerupId"):
            continue
        for entry in segment.get("overrides") or ():
            pair = _pair(entry)
            if pair is not None:
                out[pair[0]] = pair[1]
    return out


def drone_position(board, specials):
    """DronePiecePosition 0x5a127f8: (row, col).

    The game keeps the existing drone. Here the drone is created by this
    activation, so the fresh case applies: Point(x = Rows / 2,
    y = Columns - 1) -- for an 8x8 board column 4, row 7 -- when that slot is
    a plain piece; otherwise the nearest such cell (the ForEach + Sort
    fallback, measured on 042->043: (7, 5)).
    """
    height, width = len(board), len(board[0])
    # The game reuses the drone already on the board (BoardModel.Find).
    for c in range(width):
        for r in range(height):
            if int(specials[r][c]) == BILLIE_DRONE:
                return r, c
    row, col = width - 1, height // 2
    if inside(board, specials, row, col):
        return row, col
    cells = [(r, c) for c in range(width) for r in range(height) if inside(board, specials, r, c)]
    if not cells:
        return None
    return min(cells, key=lambda cell: (abs(cell[0] - row) + abs(cell[1] - col), cell[1], cell[0]))


def inside(board, specials, row, col) -> bool:
    """The slot at (row, col) is a plain piece the drone can replace."""
    if not (0 <= row < len(board) and 0 <= col < len(board[0])):
        return False
    return int(board[row][col]) > 0 and not int(specials[row][col])


def colors_to_remove(params, activation=1) -> int:
    """ColorsToRemoveByActivation, clamped like the game's Min(index, Count-1)."""
    values = params.get("colorsToRemoveByActivation") or "2"
    if isinstance(values, str):
        values = [int(v) for v in values.split(",") if v.strip()]
    values = list(values) or [2]
    return int(values[max(0, min(activation - 1, len(values) - 1))])


# GetColorGroups 0x5a12bfc seeds its list with these literals, in this order
# (OrderBy in SuckAndConvertByScoreTarget is stable, so ties keep it).
CONFIG_COLOR_ORDER = (6, 3, 5, 7, 8)


def groups(board, specials, amount) -> list[tuple[int, ...]]:
    """GetColorGroups: groups of `amount` colours from BILLIE_COLORS present on the board.

    The colour list starts with the literals GetColorGroups adds (Orange,
    Green, Yellow, Purple, White) and then every other colour on the board in
    enum order: measured 006->007 sucks Red+Blue and 017->018 Red+Orange, so
    Red and Blue are candidates even though they are not seeded literals.
    """
    present = {int(v) for row in board for v in row}
    seeded = [c for c in CONFIG_COLOR_ORDER if c in present]
    rest = [c for c in BILLIE_COLORS if c in present and c not in CONFIG_COLOR_ORDER]
    colors = seeded + rest
    return list(combinations(colors, max(1, amount)))


def group_cells(board, specials, group) -> list[tuple[int, int]]:
    """The plain pieces of the group: SuckAndConvert's Where(suckSpecials = false)."""
    wanted = set(group)
    return [(r, c) for r, row in enumerate(board) for c, value in enumerate(row)
            if int(value) in wanted and not int(specials[r][c])]


def choose(board, specials, params, evaluate, activation=1):
    """The group whose destruction scores closest to GetScoreTarget.

    ``evaluate(cells)`` settles one candidate on a GameLogic clone and returns
    its score rise, or None. Ties keep the GetColorGroups order (the game's
    OrderBy is stable). Returns (group, cells, scores).
    """
    target = params.get("scoreTarget")
    target = int(target) if target is not None else 16
    best, best_key, best_cells, scores = None, None, None, []
    for group in groups(board, specials, colors_to_remove(params, activation)):
        cells = group_cells(board, specials, group)
        if not cells:
            continue
        score = evaluate(cells)
        if score is None:
            continue
        scores.append((group, score))
        key = abs(int(score) - target)
        if best_key is None or key < best_key:
            best, best_key, best_cells = group, key, cells
    if best is None:
        raise UnsupportedRefill("Billie Boom: no colour group to suck")
    return best, best_cells, scores
