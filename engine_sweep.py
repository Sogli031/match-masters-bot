"""Sweep It SE (booster 61) activation, game 5.817.

Port of Match3Engine.SweepItSE.Use 0x5a9706c -> SweepIt.Use 0x5a939bc ->
MovePieces 0x5a93d48 -> MakeSwaps 0x5a95044, then SweepItUseEnded ->
CreatingPieces 0x5a97594 -> ChoosePositionsForBrooms 0x5a976b8 ->
ConvertToSpecials 0x5a996a8. Decompiled in Debug/reverse/sweep_booster/fn.
Points are (x, y) = (column, row) as in the engine; boards are [row][column].

MovePieces (no draw on the game's RNG):

* GetAvailableColors: engine [6, 3, 5, 7, 8] (+ the player's colour with
  allowPickingBlues), less the colours no slot matches;
* combos: with colorsAmount 2 every pair i < j in that order; colour k of a
  combo sweeps along useDirections[k] (Right, Left);
* each combo is swept on a GameLogic clone (MakeSwaps(simulate)) and settled;
  moved = target pieces that changed place, gain = the clone's score rise +
  GetSpecialsLeftScore (IsSpecial slots, not 23, x specialPieceScoreValue x
  boosterScoreTargetFactor, Fix64.Round);
* combos with moved >= minPiecesToMove; pickBehavior "closest": MaxBy
  -|gain - Round(scoreTarget x factor)| (the first on a tie). None valid:
  MaxBy -|moved - minPiecesToMove|.
"""
from __future__ import annotations

BASE_COLORS = (6, 3, 5, 7, 8)
ABILITY_CLASS = "Match3Engine.SweepItSE"
SIM_BROOM = 45          # move_strategy.SPECIAL_SWEEP_SE_BROOM
BROOM_BOARD = 99
DIRECTION_NAMES = {(1, 0): "right", (-1, 0): "left", (0, 1): "down", (0, -1): "up"}


class UnsupportedSweep(ValueError):
    pass


def fields_from(profile) -> dict:
    detail = (profile or {}).get("ability_detail") or {}
    if detail.get("class") != ABILITY_CLASS or not detail.get("fields"):
        raise UnsupportedSweep("Sweep It SE: booster fields missing from capture")
    return detail["fields"]


def _round_half_even(value: float) -> int:
    return int(round(value))


def score_target(profile) -> int:
    fields = fields_from(profile)
    factor = float((profile.get("rules") or {}).get("boosterScoreTargetFactor") or 1.0)
    return _round_half_even(int(fields.get("scoreTarget") or 0) * factor)


def _is_special_engine(value: int) -> bool:
    # SlotModel.IsSpecial: the board specials (16..21) are not; Ability's filter drops 23.
    return value not in (0, 23) and not 16 <= value <= 21


def specials_left_score(profile, special) -> int:
    from engine_refill import SIM_SPECIAL_TO_ENGINE
    fields = fields_from(profile)
    factor = float((profile.get("rules") or {}).get("boosterScoreTargetFactor") or 1.0)
    count = 0
    for row in special:
        for v in row:
            v = int(v)
            if v and _is_special_engine(SIM_SPECIAL_TO_ENGINE.get(v, v if v == SIM_BROOM else 99)):
                count += 1
    return _round_half_even(count * int(fields.get("specialPieceScoreValue") or 0) * factor)


def _matches(board, special, y, x, sim_color):
    import move_strategy as ms
    if int(board[y][x]) == sim_color and (int(special[y][x]) == 0
                                          or int(special[y][x]) in ms.SWEEP_MOVABLE_SPECIALS):
        return True
    return False


def available_colors(board, special, sim_to_engine, energy, allow_blue):
    colors = list(BASE_COLORS) + ([energy] if allow_blue else [])
    engine_to_sim = {e: s for s, e in sim_to_engine.items()}
    rows, cols = len(board), len(board[0])
    return [c for c in colors if c in engine_to_sim
            and any(_matches(board, special, y, x, engine_to_sim[c]) for y in range(rows) for x in range(cols))]


def combos(colors, amount):
    if amount == 1:
        return [[c] for c in colors]
    out = []
    n = len(colors)
    for i in range(n):
        k = i
        while k + 1 < n:
            combo = [colors[i]]
            if k + amount <= n:
                combo += colors[k + 1:k + amount]
            if len(combo) == amount:
                out.append(combo)
            k += 1
    return out


def sweep_color(board, special, sim_color, dx, dy):
    """MakeSwaps for one colour along (dx, dy): (board, special, moved,
    conversions). Per line (rows for a horizontal direction) the movable slots
    from the line's start (the side the sweep leaves) take the other pieces
    first, then the colour's; ``conversions`` lists the cells a piece moved to
    (row, col), in that order; ``moved`` counts the colour's pieces that moved."""
    import move_strategy as ms
    board = [[int(v) for v in row] for row in board]
    special = [[int(v) for v in row] for row in special]
    rows, cols = len(board), len(board[0])
    moved, conversions = 0, []
    horizontal = dy == 0
    step = dx if horizontal else dy
    for line in range(rows if horizontal else cols):
        length = cols if horizontal else rows
        along = range(length) if step > 0 else range(length - 1, -1, -1)
        cells = [(line, a) if horizontal else (a, line) for a in along]
        cells = [c for c in cells if int(special[c[0]][c[1]]) not in ms.SWEEP_IMMOVABLE_SPECIALS]
        pieces = [(c, board[c[0]][c[1]], special[c[0]][c[1]]) for c in cells]
        mine = [p for p in pieces if _matches(board, special, p[0][0], p[0][1], sim_color)]
        ordered = [p for p in pieces if p not in mine] + mine
        others = len(pieces) - len(mine)
        new_board = [row[:] for row in board]
        new_special = [row[:] for row in special]
        for slot, (origin, value, spec) in enumerate(ordered):
            target = cells[slot]
            if target != origin:
                conversions.append(target)
                moved += slot >= others
            new_board[target[0]][target[1]] = value
            new_special[target[0]][target[1]] = spec
        board, special = new_board, new_special
    return board, special, moved, conversions


def sweep(board, special, combo, directions, sim_to_engine):
    """MakeSwaps: (board, special, moved, conversions) after every colour of
    ``combo`` (sweep_color per colour, colour k along directions[k])."""
    engine_to_sim = {e: s for s, e in sim_to_engine.items()}
    moved, conversions = 0, []
    for index, color in enumerate(combo):
        d = directions[index] if index < len(directions) else directions[-1]
        board, special, m, conv = sweep_color(board, special, engine_to_sim[color], int(d["x"]), int(d["y"]))
        moved += m
        conversions += conv
    return board, special, moved, conversions


def choose_combo(board, special, model, settle):
    """MovePieces: (combo, evaluations). ``settle(clone_model, board, special)``
    sweeps nothing itself; it settles the swept board on the clone and returns
    the clone's score rise."""
    from engine_refill import color_maps
    profile = model.profile
    fields = fields_from(profile)
    if str(fields.get("pickBehavior")) != "closest":
        raise UnsupportedSweep(f"Sweep It SE: pickBehavior {fields.get('pickBehavior')} is not ported")
    sim_to_engine = color_maps(profile)[0]
    energy = next(int((p.get("model") or {}).get("slotType")) for p in profile.get("players") or ()
                  if p.get("player_type") == 0)
    colors = available_colors(board, special, sim_to_engine, energy, bool(fields.get("allowPickingBlues")))
    directions = fields.get("useDirections") or [{"x": 1, "y": 0}]
    target = score_target(profile)
    minimum = int(fields.get("minPiecesToMove") or 0)
    evaluations = []
    for combo in combos(colors, int(fields.get("colorsAmount") or 1)):
        swept_board, swept_special, moved, conversions = sweep(board, special, combo, directions, sim_to_engine)
        clone = model.clone()
        clone.rng = model.rng.clone()
        gain, settled_special = settle(clone, swept_board, swept_special, conversions)
        gain += specials_left_score(profile, settled_special)
        evaluations.append({"combo": combo, "moved": moved, "gain": gain})
    if not evaluations:
        raise UnsupportedSweep("Sweep It SE: no colour to sweep")
    valid = [e for e in evaluations if e["moved"] >= minimum]
    if valid:
        best = max(valid, key=lambda e: -abs(e["gain"] - target))
    else:
        best = max(evaluations, key=lambda e: -abs(e["moved"] - minimum))
    return best["combo"], evaluations, directions, sim_to_engine


# --- SweepItUseEnded -> CreatingPieces -> ChoosePositionsForBrooms ---------
#
# SweepItUseEnded: allowedColors [3, 6, 7, 5] (+ the opponent's colour), then
# Chance(chanceToAllowBlueAsTargetPosition) adds the player's (one draw).
# NewBoosterPiecesAmount: piecesPerActivation[min(ActivatesThisTurn - 1, n - 1)].
#
# ChoosePositionsForBrooms(amount); a = min(ActivatesThisTurn - 1, n - 1) for
# each ...ByActivation list:
#
# * withExtra = Chance(chanceToBroomWithExtraMoveByActivation[a]) (one draw);
# * with it: board.ForEach (x outer) records each slot's colours (colour and
#   colour2) by x and by y; ColorsWithExtraMoveOption keeps a colour whose
#   sorted coordinates hold four equal or four consecutive values; per
#   NormalOrClassicSpecial slot, extra = the vertical neighbours (0,-1), (0,1)
#   that match an x-colour plus the horizontal ones (-1,0), (1,0) that match a
#   y-colour (b__4: in bounds, movable, not the slot's own colour); a counted
#   neighbour of an energy-charging colour also lists the slot (the "blue"
#   list), which is then de-duplicated and shuffled;
# * per broom with withExtra: r = Range(0, 100); r <= minMax -> k =
#   Range(min, max + 1), the extra value closest to k (the first in ForEach
#   order on a tie), a random valid slot with exactly it; minMax < r <=
#   minMax + blue -> the first of the blue list; otherwise, or when that found
#   nothing, a random valid slot with extra > 0;
# * without one: Chance(chanceToNeighborBlues) (ChooseNeighbor, not ported),
#   then GetSlotPrioritize(1) through five ignore filters. shortcut: only the
#   first three filters are ported; no recorded activation reached them.
INVALID = None
VERTICAL = ((0, -1), (0, 1))
HORIZONTAL = ((-1, 0), (1, 0))
FOUR_NEIGHBOURS = ((0, 1), (1, 0), (0, -1), (-1, 0))


def _by_activation(values, activation):
    values = list(values or [0])
    return int(values[max(0, min(activation - 1, len(values) - 1))])


def _colors_with_extra_move(coords_by_color):
    out = []
    for color, values in coords_by_color.items():
        same = run = 0
        previous = -2
        for value in sorted(values):
            if value == previous:
                same += 1
            else:
                same = 0
                run = run + 1 if value == previous + 1 else 0
            if same >= 3 or run >= 3:
                out.append(color)
                break
            previous = value
    return out


class _View:
    """The settled board as ChoosePositionsForBrooms reads it."""

    def __init__(self, board, special, sim_to_engine, slot_colors=None):
        import move_strategy as ms
        self.board, self.special = board, special
        # Colours the slot keeps under an uncoloured special (a broom: EngineRefill.balls).
        self.slot_colors = slot_colors or {}
        self.rows, self.cols = len(board), len(board[0])
        self.sim_to_engine = sim_to_engine
        self._ms = ms

    def inside(self, x, y):
        return 0 <= x < self.cols and 0 <= y < self.rows

    def colors(self, x, y):
        out = []
        c = self.slot_colors.get((y, x), self.sim_to_engine.get(int(self.board[y][x])))
        if c is not None:
            out.append(c)
        for extra in self._ms._special_match_colors(int(self.special[y][x])):
            e = self.sim_to_engine.get(int(extra))
            if e is not None and e not in out:
                out.append(e)
        return out

    def plain(self, x, y):
        return int(self.special[y][x]) == 0 and 1 <= int(self.board[y][x]) <= 6

    def normal_or_classic(self, x, y):
        s = int(self.special[y][x])
        return self.plain(x, y) or (s in self._ms.SWEEP_MOVABLE_SPECIALS and 1 <= int(self.board[y][x]) <= 6)

    def movable(self, x, y):
        return int(self.special[y][x]) not in self._ms.SWEEP_IMMOVABLE_SPECIALS

    def valid(self, x, y):
        # IsBroomPositionValid: not a live-event piece, at most one layer
        # (no recorded board has either).
        return True


def choose_brooms(view, rng, amount, fields, activation, energy, charging):
    if fields.get("removePreviousPieces"):
        raise UnsupportedSweep("Sweep It SE: removePreviousPieces is not ported")
    neighbour_blue = _by_activation(fields.get("chanceToNeighborBluesByActivation"), activation)
    with_extra = rng.chance(_by_activation(fields.get("chanceToBroomWithExtraMoveByActivation"), activation))
    min_max = _by_activation(fields.get("chanceForMinMaxExtraMoveOptionsByActivation"), activation)
    blue_chance = _by_activation(fields.get("chanceForBlueWithExtraMoveByActivation"), activation)
    extra, blue = {}, []
    if with_extra:
        by_x, by_y = {}, {}
        for x in range(view.cols):
            for y in range(view.rows):
                for c in view.colors(x, y):
                    by_x.setdefault(c, []).append(x)
                    by_y.setdefault(c, []).append(y)
        colors_x, colors_y = _colors_with_extra_move(by_x), _colors_with_extra_move(by_y)

        def count(x, y, colors, directions):
            own = set(view.colors(x, y))
            n = 0
            for dx, dy in directions:
                nx, ny = x + dx, y + dy
                # b__4 reads the neighbour's canBeMatched: a broom (false) never counts.
                if not view.inside(nx, ny) or not view.movable(nx, ny) or (ny, nx) in view.slot_colors:
                    continue
                theirs = view.colors(nx, ny)
                if own & set(theirs) or not any(c in colors for c in theirs):
                    continue
                if any(c in charging for c in theirs):
                    blue.append((x, y))
                n += 1
            return n

        for x in range(view.cols):
            for y in range(view.rows):
                if view.normal_or_classic(x, y):
                    extra[(x, y)] = count(x, y, colors_x, VERTICAL) + count(x, y, colors_y, HORIZONTAL)
        # Distinct before the shuffle (a slot with two blue neighbours is listed once).
        blue = rng.shuffled(list(dict.fromkeys(blue)))
    chosen = []
    while len(chosen) < amount:
        pos = INVALID
        if with_extra:
            r = rng.range(0, 100)
            if r <= min_max:
                k = rng.range(int(fields.get("minExtraMoveOptions") or 0),
                              int(fields.get("maxExtraMoveOptions") or 0) + 1)
                if extra:
                    value = max(extra.values(), key=lambda v: -abs(v - k))
                    cands = [p for p, v in extra.items() if v == value and view.valid(*p)]
                    if cands:
                        pos = rng.choice(cands)
            elif r <= min_max + blue_chance and blue:
                pos = blue[0]
            if pos is INVALID:
                cands = [p for p, v in extra.items() if v > 0 and view.valid(*p)]
                if cands:
                    pos = rng.choice(cands)
            if pos is not INVALID:
                chosen.append(pos)
                extra.pop(pos, None)
                if pos in blue:
                    blue.remove(pos)
                continue
        if rng.chance(neighbour_blue):
            raise UnsupportedSweep("Sweep It SE: ChooseNeighbor is not ported")
        pos = _prioritized(view, rng, chosen, energy)
        if pos is INVALID:
            raise UnsupportedSweep("Sweep It SE: no broom position")
        chosen.append(pos)
        extra.pop(pos, None)
        if pos in blue:
            blue.remove(pos)
    return chosen


def _prioritized(view, rng, chosen, energy):
    """GetSlotPrioritize(1) with an always-false priority: the x-major list of
    the slots the filter keeps, shuffled, the first one."""
    near = set(chosen) | {(x + dx, y + dy) for x, y in chosen for dx, dy in FOUR_NEIGHBOURS}

    def level1(x, y):
        if not view.plain(x, y) or energy in view.colors(x, y) or (x, y) in near or not view.valid(x, y):
            return False
        return not any(view.inside(x + dx, y + dy) and energy in view.colors(x + dx, y + dy)
                       for dx, dy in FOUR_NEIGHBOURS)

    def level2(x, y):
        return view.plain(x, y) and view.valid(x, y) and energy not in view.colors(x, y)

    def level3(x, y):
        return view.normal_or_classic(x, y)

    for keep in (level1, level2, level3):
        cands = [(x, y) for x in range(view.cols) for y in range(view.rows) if keep(x, y)]
        if cands:
            return rng.shuffled(cands)[0]
    return INVALID


def place_brooms(board, special, model, activation):
    """SweepItUseEnded on the settled board: (board, special, cells (row, col))."""
    from engine_refill import color_maps
    profile = model.profile
    fields = fields_from(profile)
    rng = model.rng
    rng.chance(int(fields.get("chanceToAllowBlueAsTargetPosition") or 0))
    amount = _by_activation(fields.get("piecesPerActivation") or [1], activation)
    board = [list(map(int, row)) for row in board]
    special = [list(map(int, row)) for row in special]
    if amount < 1:
        return board, special, []
    sim_to_engine = color_maps(profile)[0]
    energy = next(int((p.get("model") or {}).get("slotType")) for p in profile.get("players") or ()
                  if p.get("player_type") == 0)
    charging = {int(c) for c in ((profile.get("state") or {}).get("energy_charging_colors") or ())} or {energy}
    on_board = [(y, x) for y, row in enumerate(special) for x, v in enumerate(row) if int(v) == SIM_BROOM]
    view = _View(board, special, sim_to_engine, model.ball_colors_at(on_board) if on_board else {})
    cells = choose_brooms(view, rng, amount, fields, activation, energy, charging)
    for x, y in cells:
        # The broom keeps the piece's colour: the game's colour count holds it
        # after every recorded activation (research 20261119_031206: 004, 010, 020).
        color = board[y][x]
        if model.balls is not None and color in sim_to_engine:
            model.balls.append((y, x, sim_to_engine[color]))
        board[y][x], special[y][x] = BROOM_BOARD, SIM_BROOM
    return board, special, [(y, x) for x, y in cells]
