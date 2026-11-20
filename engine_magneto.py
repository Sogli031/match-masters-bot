"""El Magneto SE (booster 48) activation: four magnets, one colour each.

Port of Match3Engine.ElMagneto.Use 0x5a3c63c and MakeColorSwaps 0x5a3ff08
(pseudocode Debug/reverse/el_magneto2/useC.c, geometry in
docs/booster_logic_from_code.md, section "El Magneto (buster 33)"). Points are
(x, y) = (column, row) as in the engine; the boards are the simulator's
[row][column].

What the code does, in the order it does it:

* the magnets are the middles of the four sides, ``x >> 1`` of the column and
  the row count -- never random cells: (Columns/2, 0), (Columns/2, Rows-1),
  (0, Rows/2), (Columns-1, Rows/2);
* the colour paths are the m-subsets of the colours on the board
  (``GetAllSlotColorCombinations(Min(magnetCount, avail.Count), avail)``),
  filtered by two ``Chance`` branches (the player's colour and the other of
  {blue, red}), shuffled and trimmed to ``maxColorPaths``;
* every candidate is scored on a clone, the winner is applied to the real
  board by ``MakeColorSwaps``, recursing through all magnets, and only then
  does the board resolve like an ordinary move (``ConvertSlots`` at the end).

One magnet (``MakeColorSwaps`` for ``magnetIndex``): every matchable piece of
that colour, sorted stable by ``CubedDistanceTo(magnet)`` (= dx*dx + dy*dy), is
walked one cell at a time onto the free neighbour of the magnet closest to it,
each step a ``BoardModel.Swap``; the cell it lands on then joins
``magnitiedPositions`` and stops being a neighbour. The recorded
``<currentConvertData>`` of the last magnet (its ``sourceToTargetPairs``) is
exactly this sequence of swaps, which is how the geometry below was checked.

Selection is the one part the recordings do not pin down yet: the number of
draws the two ``Shuffle`` calls above the candidate list consume, and which
magnet each colour is paired with, are still open (see the docs section).
``predict`` therefore builds the path the code describes and does **no draws**;
``OVERRIDE_PATH`` lets a measurement replay the path a snapshot recorded
(``tools/magneto_check.py --captured``), so the geometry can be checked apart
from the pick.
"""
from __future__ import annotations


EL_MAGNETO_SE = 48
SIM_EMPTY = 0
# SlotValueTypeExtensions.IsNormalOrClassicSpecial -- the pieces that still
# match; everything else (crystal, mushroom, chest, crosshair, blockers) is a
# BoardSpecial for Participate/MatchesWithColor.
CLASSIC_SPECIALS = frozenset((1, 2, 3, 4, 46))
_ONE = 1 << 32
DIRECTIONS = ((0, 1), (0, -1), (1, 0), (-1, 0))
DEFAULT_CONFIG = {
    "magnetCount": 4, "maxColorPaths": 5, "pickBehavior": "score",
    "scoreTarget": 1, "specialPieceScoreValue": 3, "useAI": False, "aiLevel": 0.5,
    "chanceToPickRed": 25, "chanceToPickBlue": 35, "colorPathsAmountToScan": 5,
    "dynamicallyCreateColorPaths": True,
}
# Set by tools/magneto_check.py --captured: [(magnet (x, y), engine colour)].
OVERRIDE_PATH = None


class UnsupportedMagneto(Exception):
    """The activation needs something this port does not model."""


def config_from_profile(profile):
    fields = ((profile or {}).get("ability_detail") or {}).get("fields") or {}
    config = dict(DEFAULT_CONFIG)
    for key in DEFAULT_CONFIG:
        value = fields.get(key)
        if isinstance(value, (int, float, bool, str)):
            config[key] = value
    config["boosterScoreTargetFactor"] = float(((profile or {}).get("rules") or {})
                                               .get("boosterScoreTargetFactor") or 1)
    return config


def player_slot_types(profile):
    """(blue, red) engine SlotColors: the player's, and the other of {2, 4}."""
    blue = red = None
    for player in (profile or {}).get("players") or ():
        model = player.get("model") or {}
        if player.get("player_type") == 0:
            blue = model.get("slotType")
        elif player.get("player_type") == 1 and red is None:
            red = model.get("slotType")
    if blue is None:
        return None, None
    if red is None:
        red = 4 if blue == 2 else 2
    return blue, red


def magnets_for(rows, columns):
    """The four side middles, in the order the code builds the list."""
    return [(0, rows // 2), (columns - 1, rows // 2),
            (columns // 2, 0), (columns // 2, rows - 1)]


def _in_board(board, x, y):
    return 0 <= y < len(board) and 0 <= x < len(board[0])


def _can_be_matched(special_value):
    value = int(special_value)
    return value == SIM_EMPTY or value in CLASSIC_SPECIALS


def _participates(board, special, x, y):
    """Participate 0x5a411b4: in the board, not a BoardSpecial, hitPoints 1."""
    if not _in_board(board, x, y):
        return False
    return _can_be_matched(special[y][x]) and int(board[y][x]) > 0


def available_colors(board, special, sim_to_engine):
    """GetAvailableColorsOnBoard: distinct colours of matchable pieces, x-major."""
    colors = []
    for x in range(len(board[0])):
        for y in range(len(board)):
            if not _participates(board, special, x, y):
                continue
            color = sim_to_engine.get(int(board[y][x]))
            if color is not None and color not in colors:
                colors.append(color)
    return colors


def combinations(amount, items):
    """GetAllSlotColorCombinations(amount, items): every amount-subset in order."""
    items = list(items)
    if amount <= 0:
        return [[]]
    if amount > len(items):
        return []
    out = []
    for i in range(len(items) - amount + 1):
        for rest in combinations(amount - 1, items[i + 1:]):
            out.append([items[i]] + rest)
    return out


def _distance(a, b):
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2


def _step(current, start, dest):
    """MakeColorSwaps 0x05eb8bc8: one axis step along the line start->dest.

    The axis comes from Fix64 interpolation of the line through dest with the
    fixed slope delta.y/delta.x, evaluated half a column ahead of current.
    """
    dx, dy = dest[0] - start[0], dest[1] - start[1]
    step_x = 1 if dx > 0 else -1
    step_y = 1 if dy >= 1 else -1
    if dx == 0:
        return 0, step_y
    if dy == 0:
        return step_x, 0
    # Q32.32 like Fix64: the quotient rounds to nearest, the product floors,
    # Round goes half to even -- 1/5 lands just under .5, which picks the axis.
    quotient = (abs(dy) * 2 * _ONE // abs(dx) + 1) >> 1
    slope = quotient if (dx > 0) == (dy > 0) else -quotient
    offset = (2 * (current[0] - dest[0]) + (1 if dx > 0 else -1)) * _ONE // 2
    value = (slope * offset >> 32) + dest[1] * _ONE
    whole, frac = value >> 32, value & (_ONE - 1)
    expected = whole + (frac > _ONE // 2 or (frac == _ONE // 2 and whole & 1))
    return (step_x, 0) if expected == current[1] else (0, step_y)


def _swap(board, special, a, b):
    ax, ay = a
    bx, by = b
    board[ay][ax], board[by][bx] = board[by][bx], board[ay][ax]
    special[ay][ax], special[by][bx] = special[by][bx], special[ay][ax]


def _open_around(board, special, cell, magnitied, open_positions):
    for direction in DIRECTIONS:
        p = (cell[0] + direction[0], cell[1] + direction[1])
        if (_participates(board, special, *p) and p not in open_positions
                and p not in magnitied):
            open_positions.append(p)


def make_color_swaps(board, special, magnet, color, magnitied, sim_to_engine):
    """One magnet on ``board``/``special`` in place: [(from (x, y), to (x, y))].

    ``color`` is the engine SlotColor; ``magnitied`` is shared by every magnet
    of the activation (Use passes null and threads it through the recursion).
    """
    matched = [(x, y) for x in range(len(board[0])) for y in range(len(board))
               if _participates(board, special, x, y)
               and sim_to_engine.get(int(board[y][x])) == color]
    matched.sort(key=lambda cell: _distance(cell, magnet))     # stable, board order

    open_positions = []
    if _participates(board, special, *magnet) and magnet not in magnitied:
        open_positions.append(magnet)
    else:
        _open_around(board, special, magnet, magnitied, open_positions)

    swaps = []
    for piece in matched:
        if not open_positions:
            break
        best = min(_distance(cell, magnet) for cell in open_positions)
        dest = min((cell for cell in open_positions if _distance(cell, magnet) == best),
                   key=lambda cell: _distance(piece, cell))
        source = current = piece
        while current != dest:
            step = _step(current, piece, dest)
            following = (current[0] + step[0], current[1] + step[1])
            current = following
            if following in magnitied:
                continue            # the cursor jumps over a magnetised slot, the piece stays
            _swap(board, special, source, following)
            swaps.append((source, following))
            source = following
        open_positions.remove(dest)
        magnitied.add(dest)
        _open_around(board, special, dest, magnitied, open_positions)
    return swaps


def candidates(board, special, model):
    """Use 0x05eb6c9c..0x05eb74dc on ``model.rng``: (magnets, colour combos).

    Every draw the real Use spends before scoring: Chance(blue), Chance(red),
    Shuffle+Take of the combos, the copies when one is left, Shuffle of the
    four side middles, and the second Shuffle+GetRange.
    """
    from engine_refill import color_maps

    config = config_from_profile(model.profile)
    if not config["dynamicallyCreateColorPaths"]:
        # shortcut: the preset pairs/triples branch is not ported, no recorded booster uses it.
        raise UnsupportedMagneto("El Magneto: preset colour paths are not ported")
    rng = model.rng
    sim_to_engine, _ = color_maps(model.profile)
    blue, red = player_slot_types(model.profile)
    colors = available_colors(board, special, sim_to_engine)
    amount = min(int(config["magnetCount"]), len(colors))
    take = int(config["maxColorPaths"])
    combos = combinations(amount, colors)
    if int(config["chanceToPickBlue"]) >= -1 and blue in colors:
        keep = rng.chance(int(config["chanceToPickBlue"]))
        combos = [c for c in combos if (blue in c) == keep]
    if (sum(c not in (2, 4) for c in colors) >= amount and int(config["chanceToPickRed"]) >= -1
            and red in colors):
        keep = rng.chance(int(config["chanceToPickRed"]))
        combos = [c for c in combos if (red in c) == keep]
    combos = rng.shuffled(combos)[:take]
    if len(combos) == 1:
        for _ in range(take):
            combos.append(list(rng.shuffled(list(combos[0]))))
        unique = []
        for combo in combos:            # Distinct: equal orders collapse
            if combo not in unique:
                unique.append(combo)
        combos = unique
    if not combos:
        combos = [colors[:amount]]
    magnets = rng.shuffled(magnets_for(len(board), len(board[0])))[:amount]
    combos = rng.shuffled(combos)[:take]
    return magnets, combos, config


def pick(scored, config):
    """Selection 0x05eb7854..0x05eb7b48 over [(path, score)] in scan order."""
    # Ability.GetScoreTarget 0x5d7f478: Fix64.Round(scoreTarget * boosterScoreTargetFactor).
    target = float(round(int(config["scoreTarget"]) * float(config["boosterScoreTargetFactor"])))
    threshold = round(5 * float(config["boosterScoreTargetFactor"]))
    for path, score in scored:
        if abs(score - target) < threshold:
            return path               # early exit, before the behaviour pick
    behavior = config["pickBehavior"]
    if behavior == "highest":
        return max(scored, key=lambda item: item[1])[0]
    if behavior == "lowest":
        return min(scored, key=lambda item: item[1])[0]
    return min(scored, key=lambda item: abs(item[1] - target))[0]


def activate(board, special, model, path=None, square=False):
    """The whole activation: (converted board, cells touched, path used).

    The board is only rearranged; the caller resolves it as an ordinary move
    (``ConvertSlots`` and the cascade happen after every magnet).
    """
    from engine_refill import color_maps

    if model is None:
        raise UnsupportedMagneto("El Magneto needs the exact engine refill")
    sim_to_engine, _ = color_maps(model.profile)
    used = path if path is not None else OVERRIDE_PATH
    if used is None:
        raise UnsupportedMagneto("El Magneto: the path comes from simulation.magneto_path")
    used = list(used)
    converted = [list(map(int, row)) for row in board]
    converted_special = [list(map(int, row)) for row in special]
    magnitied = set()
    touched = []
    for magnet, color in used:
        magnet = (int(magnet[0]), int(magnet[1]))
        swaps = make_color_swaps(converted, converted_special, magnet, int(color),
                                 magnitied, sim_to_engine)
        touched.extend((y, x) for _, (x, y) in swaps)
    return converted, touched, used
