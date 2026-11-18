"""Foxy Roxy SE (booster 52) activation, game 5.817, no powerup variant.

Port of Match3Engine.FoxyRoxy.Use 0x5a43778 (the paint) and
FoxyRoxySE.FoxyUseEnded 0x5a46970 -> CreatingPieces 0x5a46ce0 ->
ChoosePositionsForSprayCans 0x5a46e0c / ChooseNeighbor 0x5a484a4 (the spray
cans). Listings in Debug/reverse/foxy. Points are (x, y) = (column, row) as
in the engine; the boards are the simulator's [row][column].

Paint (FoxyRoxy.Use):

* every point, rows outer and columns inner, shuffled (ArrayExtensions
  0x3c13d70, one Next each);
* for each point p that Participates (not a BoardSpecial, hitPoints 1,
  canBeMatched) and is not Blue or Red: the run to the right and the run
  down from p (Participating cells, p included); each run grows one cell at
  a time and from length 3 on, with valueBySequenceLength[length] >= 0 and
  every cell either free or in a sequence of lower value (b__2), the prefix
  becomes a sequence painted in p's colour; the sequences it overlaps are
  dropped whole first;
* passes over a fresh shuffle repeat while one recorded a sequence;
* maxParticipants = Range(maxParticipantsRange), minSequences =
  Range(minSequencesRange) (upper exclusive; equal ends draw nothing); while
  more cells than maxParticipants are painted and more sequences than
  minSequences remain, a random one (Range(0, count)) is dropped;
* the sequences are a Dictionary<Point, List> (insertion order with freed
  slots reused last-freed first, as .NET does); their distinct values, in
  that order, are the conversions. Then GetAllCombos -> DestroyMatches.

Cans (autoExplodeSpecial is false, so MoveEndEffect draws nothing): one
Chance(chanceToAllowBlueAsTargetPosition), then piecesPerActivation[
min(ActivatesThisTurn - 1, n - 1)] cans, see spray_positions.
"""
from __future__ import annotations

SIM_SPRAY_CAN = 29
SIM_EMPTY = 0
# Normal or classic special (SlotValueTypeExtensions.IsNormalOrClassicSpecial):
# simulator Row, Column, Bomb, Lightning and the crosshair.
CLASSIC_SPECIALS = frozenset((1, 2, 3, 4, 46))
ABILITY_CLASS = "Match3Engine.FoxyRoxySE"
DEFAULT_CONFIG = {
    "maxParticipantsRange": [11, 15], "minSequencesRange": [3, 4],
    "sequenceLengthToValue": {3: 1, 4: 2, 5: 1, 6: 1},
    "piecesPerActivation": [2, 1], "chanceToNeighborBluesByActivation": [40],
    "chanceToAllowBlueAsTargetPosition": 50, "chanceReductionByPiece": 0.5,
    "directions": [(0, 1), (1, 0), (0, -1), (-1, 0)],
}


class NetDictionary:
    """Dictionary<Point, T> enumeration order: entries in slot order, a removed
    slot reused by the next Add (last freed first)."""

    def __init__(self):
        self.keys, self.values, self.free, self.index = [], [], [], {}

    def __contains__(self, key):
        return key in self.index

    def __len__(self):
        return len(self.index)

    def get(self, key):
        return self.values[self.index[key]]

    def set(self, key, value):
        slot = self.index.get(key)
        if slot is not None:
            self.values[slot] = value
            return
        if self.free:
            slot = self.free.pop()
            self.keys[slot], self.values[slot] = key, value
        else:
            slot = len(self.keys)
            self.keys.append(key)
            self.values.append(value)
        self.index[key] = slot

    def remove(self, key):
        slot = self.index.pop(key, None)
        if slot is not None:
            self.keys[slot] = self.values[slot] = None
            self.free.append(slot)

    def distinct_values(self):
        out, seen = [], set()
        for slot, key in enumerate(self.keys):
            if key is None:
                continue
            value = self.values[slot]
            if id(value) not in seen:
                seen.add(id(value))
                out.append(value)
        return out


# The powerup ("boosted") Foxy Roxy SE: FoxyRoxySE.TryGetPowerupVariant gives
# a FoxyRoxySEPowerUpVariant1, which paints patterns (Turn90, SpiralTwoColors,
# RectangleTwoColors, Staircase, AlternatingRows) and builds its own spray
# paths instead of FoxyRoxy.Use and ChoosePositionsForSprayCans. Seen first
# in Bombs Away 2026-11-18 09:10 (research 20261118_091058): every one of 17
# activations missed on the plain port. Its own params name the patterns.
POWERUP_PARAM_KEYS = ("activationPatternOptions", "activationPatternSelectedByActivation",
                      "activationCombosByActivation", "sprayEnergyRangeByActivation")


def is_powerup_variant(params=None, profile=None) -> bool:
    """The local Foxy Roxy SE is the powerup variant (FoxyRoxySEPowerUpVariant1).

    From the memory read of the ability (ActiveVariant set) when recorded,
    else from the player's special_ability_params (the variant's own keys)."""
    detail = (profile or {}).get("ability_detail") or {}
    fields = detail.get("fields") if detail.get("class") == ABILITY_CLASS else None
    if fields and fields.get("<ActiveVariant>k__BackingField") is not None:
        return True
    return isinstance(params, dict) and any(params.get(key) is not None for key in POWERUP_PARAM_KEYS)


def _ints(text):
    return [int(part) for part in str(text).replace("|", ",").split(",") if part.strip()]


def config_from_profile(profile, params=None) -> dict:
    """The ability's fields as read from memory (profile.ability_detail, only
    while "Snimaj svaki potez" records), else the player's
    special_ability_params (the live snapshot, strings), else the Solo
    defaults. chanceReductionByPiece and directions are not in the params."""
    detail = (profile or {}).get("ability_detail") or {}
    fields = detail.get("fields") if detail.get("class") == ABILITY_CLASS else None
    config = dict(DEFAULT_CONFIG)
    if not fields:
        params = params if isinstance(params, dict) else {}
        try:
            for key in ("maxParticipantsRange", "minSequencesRange", "piecesPerActivation",
                        "chanceToNeighborBluesByActivation"):
                if params.get(key) is not None:
                    config[key] = _ints(params[key])
            if params.get("chanceToAllowBlueAsTargetPosition") is not None:
                config["chanceToAllowBlueAsTargetPosition"] = int(params["chanceToAllowBlueAsTargetPosition"])
            if params.get("valueBySequenceLength"):
                pairs = [_ints(pair) for pair in str(params["valueBySequenceLength"]).split("|")]
                config["sequenceLengthToValue"] = {pair[0]: pair[1] for pair in pairs if len(pair) == 2}
        except ValueError:
            return dict(DEFAULT_CONFIG)
        return config
    for key in ("maxParticipantsRange", "minSequencesRange", "piecesPerActivation",
                "chanceToNeighborBluesByActivation", "chanceToAllowBlueAsTargetPosition",
                "chanceReductionByPiece"):
        if fields.get(key) is not None:
            config[key] = fields[key]
    values = (fields.get("sequenceLengthToValue") or {}).get("entries")
    if values:
        config["sequenceLengthToValue"] = {int(e["key"]): int(e["value"]) for e in values}
    if fields.get("directions"):
        config["directions"] = [(int(d["x"]), int(d["y"])) for d in fields["directions"]]
    return config


def _pick(values, index):
    values = list(values or [0])
    return int(values[max(0, min(index, len(values) - 1))])


def _range(rng, bounds):
    low, high = int(bounds[0]), int(bounds[1])
    return low if low == high else rng.range(low, high)


def participates(board, special, x, y) -> bool:
    """FoxyRoxy.Participate: not a BoardSpecial, hitPoints 1, canBeMatched."""
    color, value = int(board[y][x]), int(special[y][x])
    return 1 <= color <= 6 and (value == SIM_EMPTY or value in CLASSIC_SPECIALS)


def paint(board, special, rng, config, blue, red):
    """[(x, y, colour)] in conversion order, drawing as FoxyRoxy.Use does."""
    rows, cols = len(board), len(board[0])
    scores = config["sequenceLengthToValue"]
    sequences = NetDictionary()
    while True:
        points = [(x, y) for y in range(rows) for x in range(cols)]
        if len(points) >= 2:
            keys = [rng.next() for _ in points]
            points = [points[i] for i in sorted(range(len(points)), key=keys.__getitem__)]
        found = False
        for x, y in points:
            if not participates(board, special, x, y) or int(board[y][x]) in (blue, red):
                continue
            down, yy = [], y
            while yy < rows and participates(board, special, x, yy):
                down.append((x, yy))
                yy += 1
            right, xx = [], x
            while xx < cols and participates(board, special, xx, y):
                right.append((xx, y))
                xx += 1
            color = int(board[y][x])
            for run in (right, down):
                current = []
                for point in run:
                    current.append(point)
                    if len(current) < 3:
                        continue
                    score = scores.get(len(current), -1)
                    if score < 0:
                        continue
                    if not all(q not in sequences or scores.get(len(sequences.get(q)[0]), -1) < score
                               for q in current):
                        continue
                    painted = ([], color)
                    for cell in current:
                        if cell in sequences:
                            for old in list(sequences.get(cell)[0]):
                                sequences.remove(old)
                        painted[0].append(cell)
                        sequences.set(cell, painted)
                    found = True
        if not found:
            break
    most = _range(rng, config["maxParticipantsRange"])
    fewest = _range(rng, config["minSequencesRange"])
    chosen = sequences.distinct_values()
    if most >= 1:
        while len(sequences) > most and len(chosen) > fewest:
            dropped = chosen[rng.range(0, len(chosen))]
            for cell in dropped[0]:
                sequences.remove(cell)
            chosen = sequences.distinct_values()
    return [(x, y, color) for cells, color in chosen for x, y in cells]


def spray_positions(board, special, rng, amount, chance_blue, config, blue):
    """ChoosePositionsForSprayCans: up to ``amount`` (x, y) for the new cans."""
    rows, cols = len(board), len(board[0])
    directions = config["directions"]
    reduction = float(config["chanceReductionByPiece"])

    def inside(x, y):
        return 0 <= x < cols and 0 <= y < rows

    def where(keep):
        # BoardModel.Where: columns outer, rows inner.
        return [(x, y) for x in range(cols) for y in range(rows) if keep(x, y)]

    def shuffle(items):
        if len(items) < 2:
            return list(items)
        keys = [rng.next() for _ in items]
        return [items[i] for i in sorted(range(len(items)), key=keys.__getitem__)]

    middle = cols // 2 if cols % 2 == 1 else None
    middle_column = [(middle, y) for y in range(rows)] if middle is not None else []
    result, blocked = [], []
    if middle is not None and any(int(special[y][middle]) == SIM_SPRAY_CAN for y in range(rows)):
        blocked.extend(middle_column)

    def is_blue(x, y):
        return int(board[y][x]) == blue

    def block_around(cell):
        blocked.append(cell)
        blocked.extend((cell[0] + dx, cell[1] + dy) for dx, dy in directions)
        if middle is not None and cell[0] == middle:
            blocked.extend(middle_column)

    def choose_neighbor(origin):
        for dx, dy in shuffle(list(directions)):
            x, y = origin[0] + dx, origin[1] + dy
            if not inside(x, y) or int(special[y][x]) != SIM_EMPTY or (x, y) in blocked or is_blue(x, y):
                continue
            result.append((x, y))
            blocked.append(origin)
            block_around((x, y))
            return True
        return False

    def no_blue_neighbor(x, y):
        return not any(inside(x + dx, y + dy) and is_blue(x + dx, y + dy) for dx, dy in directions)

    ignores = (
        lambda x, y: (int(special[y][x]) != SIM_EMPTY or is_blue(x, y) or (x, y) in blocked
                      or not no_blue_neighbor(x, y)),
        lambda x, y: int(special[y][x]) != SIM_EMPTY or is_blue(x, y),
        lambda x, y: not (int(special[y][x]) == SIM_EMPTY or int(special[y][x]) in CLASSIC_SPECIALS),
        lambda x, y: (x, y) in result or int(special[y][x]) == SIM_SPRAY_CAN,
        lambda x, y: False,
    )
    while len(result) < amount:
        if rng.chance(chance_blue) and len(result) < amount:
            blues = shuffle(where(lambda x, y: is_blue(x, y) and (x, y) not in blocked))
            if blues:
                choose_neighbor(blues[rng.range(0, len(blues))])
                chance_blue = int(reduction * chance_blue)
        if len(result) >= amount:
            continue
        for ignore in ignores:
            candidates = shuffle(where(lambda x, y: not ignore(x, y)))
            if candidates:
                break
        else:
            return result
        block_around(candidates[0])
        result.append(candidates[0])
    return result


def activate(board, special, model, activations, blue, red, params=None):
    """The paint: a recoloured board and the converted cells (row, col) in order.

    ``activations``: ActivatesThisTurn after this Use (one-based).
    """
    config = config_from_profile(model.profile, params)
    painted = paint(board, special, model.rng, config, blue, red)
    if is_powerup_variant(params, model.profile):
        # FoxyRoxy.Use: the plain paint draws first, then the variant's
        # patterns replace its sequences when it builds any (engine_foxy_powerup;
        # 15 of 15 recorded activations exact, tools/check_foxy_powerup).
        import engine_foxy_powerup as powerup
        from engine_refill import color_maps
        sim_to_engine, engine_to_sim = color_maps(model.profile)
        view = powerup.Board(board, special, sim_to_engine,
                             lambda x, y: participates(board, special, x, y))
        patterns = powerup.activation_patterns(view, model.rng, powerup.config_from(params, model.profile),
                                               activations)
        if patterns:
            painted = [(x, y, engine_to_sim.get(color, color)) for points, color in patterns
                       for x, y in points if view.paintable((x, y))]
    converted = [list(map(int, row)) for row in board]
    for x, y, color in painted:
        converted[y][x] = color
    return converted, [(y, x) for x, y, _ in painted]


def place_cans(board, special, model, activations, blue, sim_to_engine, params=None):
    """FoxyUseEnded -> CreatingPieces on the settled board: (board, special) with
    the new cans; their colours join the refill's ball slots."""
    config = config_from_profile(model.profile, params)
    rng = model.rng
    rng.chance(int(config["chanceToAllowBlueAsTargetPosition"]))
    amount = max(1, _pick(config["piecesPerActivation"], activations - 1))
    chance = _pick(config["chanceToNeighborBluesByActivation"], activations - 1)
    cells = None
    if is_powerup_variant(params, model.profile):
        # ChoosePositionsForSprayCans 0x5a470e4: the variant chooses first;
        # an empty choice falls back to the plain one below.
        import engine_foxy_powerup as powerup
        view = powerup.Board(board, special, sim_to_engine, lambda x, y: participates(board, special, x, y))
        energy = {sim_to_engine.get(blue, blue)}

        def blocked(p):
            return int(special[p[1]][p[0]]) != SIM_EMPTY or not (1 <= int(board[p[1]][p[0]]) <= 6)

        def has_special(p):
            return int(special[p[1]][p[0]]) != SIM_EMPTY

        ok, chosen = powerup.choose_spray_positions(
            view, rng, powerup.config_from(params, model.profile), activations, amount, energy,
            blocked, has_special)
        if ok and chosen:
            cells = chosen[:amount]
    if cells is None:
        cells = spray_positions(board, special, rng, amount, chance, config, blue)
    board = [list(map(int, row)) for row in board]
    special = [list(map(int, row)) for row in special]
    for x, y in cells:
        color = board[y][x]
        if model.balls is not None and color in sim_to_engine:
            model.balls.append((y, x, sim_to_engine[color]))
        board[y][x] = 99
        special[y][x] = SIM_SPRAY_CAN
    return board, special, [(y, x) for x, y in cells]
