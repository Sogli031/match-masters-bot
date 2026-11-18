"""Foxy Roxy SE powerup ("boosted") variant: FoxyRoxySEPowerUpVariant1, game 5.817.

FoxyRoxy.Use 0x5a43778 first runs the plain paint (engine_foxy.paint, all its
draws), then asks the variant (TryBuildVariantActivationConversions
0x5a44d50 -> TryBuildActivationPatterns 0x5ac47a8). When the variant builds at
least one pattern, its patterns replace the plain sequences: every point of a
pattern that is in bounds and paintable takes the pattern's colour.

Decompiled with Ghidra from libil2cpp.so (Debug/reverse/foxy_slice, fn4/*.c;
listings in Debug/reverse/foxy_powerup). Points are (x, y) = (column, row);
colours here are ENGINE SlotColor values (engine_refill.SIM_TO_ENGINE), the
boards the simulator's [row][column].

Pattern types (FoxyRoxyActivationPatternType): 0 Turn90, 1 SpiralTwoColors,
2 RectangleTwoColors, 3 Staircase, 4 AlternatingRows.
"""
from __future__ import annotations

TURN90, SPIRAL, RECTANGLE, STAIRCASE, ALTERNATING = 0, 1, 2, 3, 4
PATTERN_NAMES = {"Turn90": TURN90, "SpiralTwoColors": SPIRAL, "RectangleTwoColors": RECTANGLE,
                 "Staircase": STAIRCASE, "AlternatingRows": ALTERNATING}
# BoardModel.GetAvailableColorsOnBoard 0x5a7611c drops these engine colours.
NOT_AVAILABLE = (12, 1, 0)
ENGINE_SPECIAL_COLOR = 1   # the lambdas' "!= 1" (no simulator colour)


# ---------------------------------------------------------------- config

def _ints(text):
    return [int(p) for p in str(text).replace("|", ",").split(",") if p.strip() != ""]


def _range_list(text):
    """"5-7" or "5-7,4-6" -> [(5, 7), (4, 6)] (ReadRangeListParam)."""
    out = []
    for part in str(text or "").split(","):
        if "-" in part:
            low, high = part.split("-", 1)
            out.append((int(low), int(high)))
    return out


def _pattern_lists(text):
    """"AlternatingRows,Turn90|RectangleTwoColors" -> [[4, 0], [2]] (ReadActivationPatterns)."""
    out = []
    for group in str(text or "").split("|"):
        names = [n.strip() for n in group.split(",") if n.strip()]
        out.append([PATTERN_NAMES[n] for n in names if n in PATTERN_NAMES])
    return out


def config_from(params=None, profile=None) -> dict:
    """The variant's fields: the memory read (profile ability_detail ActiveVariant)
    where it resolved them, else the player's special_ability_params."""
    params = params if isinstance(params, dict) else {}
    variant = {}
    detail = (profile or {}).get("ability_detail") or {}
    fields = detail.get("fields") or {}
    raw = fields.get("<ActiveVariant>k__BackingField")
    if isinstance(raw, dict):
        variant = raw

    def resolved(key):
        value = variant.get(key)
        if isinstance(value, list) and value and isinstance(value[0], dict) and "unresolved" in value[0]:
            return None
        return value

    config = {
        "combos": resolved("_activationCombosByActivation"),
        "patterns": resolved("_activationPatternsByActivation"),
        "fallback": resolved("_activationFallbackPatternByActivation"),
        "size_range": resolved("_activationPatternSizeRangeByActivation"),
        "spray_energy_range": resolved("_sprayEnergyRangeByActivation"),
        "spray_special_chance": resolved("_sprayChanceToNeighborSpecialByActivation"),
        "neighbor_blues": resolved("_chanceToNeighborBluesByActivation"),
        "allow_edge": variant.get("_allowBoardEdgePositions"),
    }
    if config["combos"] is None and params.get("activationCombosByActivation"):
        config["combos"] = _ints(params["activationCombosByActivation"])
    if config["patterns"] is None and params.get("activationPatternSelectedByActivation"):
        config["patterns"] = _pattern_lists(params["activationPatternSelectedByActivation"])
    if config["fallback"] is None and params.get("activationFallbackPatternsByActivation"):
        config["fallback"] = [x for g in _pattern_lists(params["activationFallbackPatternsByActivation"]) for x in g]
    if config["size_range"] is None and params.get("activationPatternSizeRangeByActivation"):
        config["size_range"] = _range_list(params["activationPatternSizeRangeByActivation"])
    if config["spray_energy_range"] is None and params.get("sprayEnergyRangeByActivation"):
        config["spray_energy_range"] = _range_list(params["sprayEnergyRangeByActivation"])
    if config["spray_special_chance"] is None and params.get("sprayChanceToNeighborSpecialByActivation"):
        config["spray_special_chance"] = _ints(params["sprayChanceToNeighborSpecialByActivation"])
    if config["neighbor_blues"] is None and params.get("chanceToNeighborBluesByActivation"):
        config["neighbor_blues"] = _ints(params["chanceToNeighborBluesByActivation"])
    if config["allow_edge"] is None:
        config["allow_edge"] = str(params.get("allowBoardEdgePositions", "False")).lower() == "true"
    return config


def _by_activation(values, index, default):
    """GetIntByActivation / GetRangeByActivation / GetPatternsByActivation:
    values[clamp(index, 0, n-1)], or the default for an empty list."""
    if not values:
        return default
    return values[max(0, min(index, len(values) - 1))]


# ---------------------------------------------------------------- board view

class Board:
    """What the variant reads: engine colours, paintability, bounds."""

    def __init__(self, sim_board, sim_special, sim_to_engine, paintable):
        self.rows, self.cols = len(sim_board), len(sim_board[0])
        self.width, self.height = self.cols, self.rows
        self.color = [[int(sim_to_engine.get(int(v), int(v))) for v in row] for row in sim_board]
        self._paintable = paintable

    def inside(self, p):
        return 0 <= p[0] < self.width and 0 <= p[1] < self.height

    def paintable(self, p):
        return self.inside(p) and self._paintable(p[0], p[1])

    def color_at(self, p):
        return self.color[p[1]][p[0]]

    def available_colors(self):
        """GetAvailableColorsOnBoard: first-seen order, columns outer."""
        seen = []
        for x in range(self.width):
            for y in range(self.height):
                c = self.color[y][x]
                if c not in seen:
                    seen.append(c)
        return [c for c in seen if c not in NOT_AVAILABLE]


def _add(p, d):
    return (p[0] + d[0], p[1] + d[1])


def _distinct(points):
    out, seen = [], set()
    for p in points:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def _order_by_draw(items, rng):
    """OrderBy(_ => Next() % -1000): keys drawn in order, stable sort."""
    keys = [rng.next() % 1000 for _ in items]
    return [items[i] for i in sorted(range(len(items)), key=lambda i: keys[i])]


def is_connected(points):
    """IsConnectedPath 0x5ac5c40: each point 4-adjacent to the one before."""
    for a, b in zip(points, points[1:]):
        dx, dy = abs(b[0] - a[0]), abs(b[1] - a[1])
        if not ((dx == 1 and dy == 0) or (dx == 0 and dy == 1)):
            return False
    return True


def has_line_of_length(points, n):
    """HasLineOfLength 0x5acccfc: a row or a column with n consecutive points."""
    if len(points) < n:
        return False
    for axis in (1, 0):
        groups = {}
        for p in points:
            groups.setdefault(p[axis], []).append(p[1 - axis])
        for values in groups.values():
            values = sorted(values)
            run = 1
            for a, b in zip(values, values[1:]):
                run = run + 1 if b == a + 1 else 1
                if run >= n:
                    return True
    return False


def would_create_special_with_adjacent(board, points, color):
    """WouldCreateSpecialWithAdjacent 0x5acd7a4: a run of 4, or 3 by 3 crossing,
    counting the pattern and same-coloured neighbours."""
    own = set(points)

    def run(p, d):
        n, q = 0, _add(p, d)
        while board.inside(q) and (q in own or board.color_at(q) == color):
            n += 1
            q = _add(q, d)
        return n

    for p in points:
        h = 1 + run(p, (1, 0)) + run(p, (-1, 0))
        v = 1 + run(p, (0, 1)) + run(p, (0, -1))
        if h > 3 or v > 3 or (h > 2 and v > 2):
            return True
    return False


def validate(board, patterns):
    """ValidatePatternCreatesSpecialPieces 0x5acba34."""
    if not patterns:
        return False
    for points, color in patterns:
        if len(points) >= 4 and (has_line_of_length(points, 4)
                                 or would_create_special_with_adjacent(board, points, color)):
            return True
    return any(len(points) > 2 for points, _ in patterns)


def filter_overlapping(patterns, used):
    """FilterOverlappingPatterns 0x5ac9844: drop used points; keep a pattern
    of more than 2 connected points, and its points become used."""
    if not patterns:
        return False, []
    taken = set(used)
    out = []
    for points, color in patterns:
        if not points:
            continue
        kept = _distinct([p for p in points if p not in taken])
        if len(kept) > 2 and is_connected(kept):
            taken.update(kept)
            out.append((kept, color))
    return bool(out), out


# ---------------------------------------------------------------- builders

TURN90_DIRECTIONS = (((1, 0), (0, 1)), ((1, 0), (0, -1)), ((-1, 0), (0, 1)), ((-1, 0), (0, -1)),
                     ((0, 1), (1, 0)), ((0, 1), (-1, 0)), ((0, -1), (1, 0)), ((0, -1), (-1, 0)))


def build_turn90(board, rng, start, length, color):
    """TryBuildTurn90Pattern 0x5ac9034."""
    total = max(3, length)
    longest = max(2, total - 1)
    first_dir, second_dir = TURN90_DIRECTIONS[rng.range(0, 8)]
    first = rng.range(2, longest + 1)
    second = total - first + 1
    if second < 2:
        return False, []
    points, p = [], start
    for _ in range(first):
        if not board.inside(p):
            break
        if not board.paintable(p):
            return False, []
        points.append(p)
        p = _add(p, first_dir)
    corner = points[-1] if points else start
    for _ in range(max(2, second) - 1):
        corner = _add(corner, second_dir)
        if not board.inside(corner):
            break
        if not board.paintable(corner):
            return False, []
        points.append(corner)
    points = _distinct(points)
    if len(points) < total:
        return False, []
    return True, [(points, color)]


def _clockwise_spiral(board, start, directions, length):
    """BuildClockwiseSpiralPath 0x5ace270."""
    points = []
    if not board.paintable(start):
        return points
    points.append(start)
    if len(points) >= length:
        return points
    p, step, turns, rounds = start, 2, 0, 0
    while rounds != 2000:
        if len(points) >= length:
            break
        for d in directions:
            for _ in range(step):
                if len(points) >= length:
                    break
                p = _add(p, d)
                if board.inside(p):
                    if not board.paintable(p):
                        return []       # 0x5ace598: Clear, then return the empty list
                    points.append(p)
            turns += 1
            if turns > 1:
                step += 2
                turns = 0
            if len(points) >= length:
                break
        rounds += 1
    return points


def build_spiral(board, rng, start, length, color):
    """TryBuildSpiralPattern 0x5acc698: two interleaved spirals, two colours."""
    total = max(3, length)
    other = next((c for c in board.available_colors() if c != color), 0)
    same = other == ENGINE_SPECIAL_COLOR or other == color
    first = _clockwise_spiral(board, start, ((0, 1), (1, 0), (0, -1), (-1, 0)), total)
    offset = _add(start, (1, 1))
    if not board.inside(offset):
        offset = start
    second = _clockwise_spiral(board, offset, ((0, -1), (-1, 0), (0, 1), (1, 0)), total)
    first, second = _distinct(first), _distinct(second)
    if len(first) < total or len(second) < total:
        return False, []
    out = [(first[:total], color)]
    if len(second) > 2 and not same:
        out.append((second[:total], other))
    return True, out


def build_rectangle(board, rng, start, length, color):
    """TryBuildRectangleTwoColorsPattern 0x5ac9fa4: two halves of a square ring."""
    half = (length + 1) // 2 if length + 1 >= 0 else -((-(length + 1)) // 2)
    side = min(max(4, half), min(board.width - start[0], board.height - start[1]))
    if side < 4:
        return False, []
    x0, y0 = start
    x1, y1 = x0 + side - 1, y0 + side - 1
    if not board.inside(start) or not board.inside((x1, y1)):
        return False, []
    first = []
    for x in range(x0, x1 + 1):
        p = (x, y0)
        if not board.inside(p):
            break
        if not board.paintable(p):
            return False, []
        first.append(p)
    for y in range(y0 + 1, y1 + 1):
        p = (x1, y)
        if not board.inside(p):
            break
        if not board.paintable(p):
            return False, []
        first.append(p)
    second = []
    for x in range(x1 - 1, x0 - 1, -1):
        p = (x, y1)
        if not board.inside(p):
            break
        if not board.paintable(p):
            return False, []
        second.append(p)
    for y in range(y1 - 1, y0, -1):
        p = (x0, y)
        if not board.inside(p):
            break
        if not board.paintable(p):
            return False, []
        second.append(p)
    first, second = _distinct(first), _distinct(second)
    if len(first) < 4 or len(second) < 4:
        return False, []
    other = board.color_at(second[0])
    if other == ENGINE_SPECIAL_COLOR or other == color:
        pick = next((c for c in board.available_colors()
                     if c != ENGINE_SPECIAL_COLOR and c != color), 0)
        if pick == ENGINE_SPECIAL_COLOR or pick == 0:
            other = ENGINE_SPECIAL_COLOR
            for p in second:
                other = board.color_at(p)
                if other != ENGINE_SPECIAL_COLOR and other != color:
                    break
        else:
            other = pick
    return True, [(first, color), (second, other)]


STAIRCASE_DIRECTIONS = (((1, 0), (0, 1)), ((1, 0), (0, -1)), ((-1, 0), (0, 1)), ((-1, 0), (0, -1)))


def build_staircase(board, rng, start, length, color):
    """TryBuildStaircasePattern 0x5aca994: steps of one across, one down."""
    total = max(3, length)
    if not board.paintable(start):
        return False, []
    across, down = STAIRCASE_DIRECTIONS[rng.range(0, 4)]
    points, p = [start], start
    for i in range(1, total):
        # Two across, two down, two across...: Bombs Away 2026-11-18 09:12:19
        # (refill_misses 20261118_091219) painted (0,5) (1,5) (2,5) (2,4)
        # (2,3) (3,3) (4,3). Ghidra's reading of the step counter was one off.
        use_across = ((i - 1) >> 1) & 1 == 0
        p = _add(p, across if use_across else down)
        if not board.inside(p):
            break
        if not board.paintable(p):
            return False, []
        points.append(p)
    points = _distinct(points)
    if len(points) < total:
        return False, []
    return True, [(points, color)]


def _row_segment(board, y, x, count, step):
    """BuildRowSegment 0x5ace9d8."""
    out = []
    for _ in range(count):
        p = (x, y)
        if not board.paintable(p):
            return out
        out.append(p)
        x += step
    return out


def build_alternating_rows(board, rng, start, length, color):
    """TryBuildAlternatingRowsPattern 0x5acaf80: three rows, the middle reversed."""
    if not board.inside(start) or board.width <= 2:
        return False, []
    span = min(max(3, length), board.width)
    x, y = start
    if y - 1 < 0 or y + 1 >= board.height:
        return False, []
    left = max(0, min(x - (span - 1) // 2, board.width - span))
    top = _row_segment(board, y - 1, left, span, 1)
    middle = _row_segment(board, y, left + span - 1, span, -1)
    bottom = _row_segment(board, y + 1, left, span, 1)
    if len(top) <= 2 or len(middle) <= 2 or len(bottom) <= 2:
        return False, []
    c_top, c_mid, c_bottom = (board.color_at(top[0]), board.color_at(middle[0]),
                              board.color_at(bottom[0]))
    if c_top == c_mid == c_bottom:
        pick = next((c for c in board.available_colors() if c != c_top), 0)
        if pick != ENGINE_SPECIAL_COLOR and pick != c_top:
            c_mid = pick
    return True, [(top, c_top), (middle, c_mid), (bottom, c_bottom)]


def build_straight_line(board, rng, eligible, used, length):
    """TryBuildStraightLinePattern 0x5acbcb0."""
    run = max(4, min(5, length))
    starts = [p for p in eligible if p not in used]
    if not starts:
        return False, []
    for start in _order_by_draw(starts, rng)[:10]:
        for d in ((1, 0), (0, 1)):
            points, p = [], start
            for _ in range(run):
                if not board.inside(p) or p in used or not board.paintable(p):
                    break
                points.append(p)
                p = _add(p, d)
            if len(points) > 3:
                return True, [(points, board.color_at(start))]
    return False, []


BUILDERS = {TURN90: build_turn90, SPIRAL: build_spiral, RECTANGLE: build_rectangle,
            STAIRCASE: build_staircase, ALTERNATING: build_alternating_rows}


def build_at(board, rng, used, kind, length, start, color, combos_left):
    """TryBuildPatternAtLocation 0x5acb86c. The two-colour patterns (Spiral,
    Rectangle) need two patterns still wanted and both kept after the filter
    (0x5acb94c / 0x5acb9a0): Bombs Away 09:11:38, one wanted, the game
    dropped the spiral and painted its Turn90 fallback."""
    ok, patterns = BUILDERS.get(kind, build_turn90)(board, rng, start, length, color)
    if not ok:
        return False, []
    ok, patterns = filter_overlapping(patterns, used)
    if not ok:
        return False, []
    if kind in (SPIRAL, RECTANGLE) and (combos_left < 2 or len(patterns) < 2):
        return False, []
    return True, patterns


def closest_to_center(board, rng, starts):
    """GetClosestToCenterStart 0x5acb47c: ties broken by a random pick."""
    cx, cy = (board.width - 1) * 0.5, (board.height - 1) * 0.5
    best, ties = 3.4028235e38, []
    for p in starts:
        dist = (p[0] - cx) ** 2 + (p[1] - cy) ** 2
        if dist < best - 0.0001:
            best, ties = dist, [p]
        elif abs(dist - best) <= 0.0001:
            ties.append(p)
    if not ties:
        return starts[0]
    return ties[rng.range(0, len(ties))]


def build_pattern(board, rng, eligible, used, kind, fallback, length, combos_left):
    """TryBuildPattern 0x5ac5740."""
    starts = [p for p in eligible if p not in used]
    if not starts:
        return False, []
    order = _order_by_draw(starts, rng)
    tries = min(len(order), 8)
    for i in range(tries):
        p = order[i]
        if kind == SPIRAL and i == 0:
            p = closest_to_center(board, rng, starts)
        ok, out = build_at(board, rng, used, kind, length, p, board.color_at(p), combos_left)
        if ok and validate(board, out):
            return True, out
    if fallback != kind:
        order = _order_by_draw(starts, rng)
        for i in range(tries):
            p = order[i]
            ok, out = build_at(board, rng, used, fallback, length, p, board.color_at(p), combos_left)
            if ok and validate(board, out):
                return True, out
    ok, out = build_straight_line(board, rng, eligible, used, length)
    if ok and validate(board, out):
        return True, out
    for i in range(tries):
        p = order[i]
        ok, out = build_at(board, rng, used, kind, length, p, board.color_at(p), combos_left)
        if ok:
            return True, out
        if fallback != kind:
            ok, out = build_at(board, rng, used, fallback, length, p, board.color_at(p), combos_left)
            if ok:
                return True, out
    return build_straight_line(board, rng, eligible, used, max(3, length))


def adjacent_candidates(eligible, used, points):
    """GetAdjacentStartCandidates 0x5acdd7c."""
    own = set(points)

    def adjacent(p):
        x, y = p
        return any(q in own for q in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)))

    near = [p for p in eligible if p not in used and adjacent(p)]
    if near:
        return near
    return [p for p in eligible if p not in used]


def build_segment(board, rng, eligible, used, kind, length, candidates, color):
    """TryBuildPatternSegment 0x5acdf98."""
    pool = [p for p in (candidates if candidates else eligible) if p not in used]
    if not pool:
        return False, []
    start = pool[rng.range(0, len(pool))]
    ok, patterns = BUILDERS.get(kind, build_turn90)(board, rng, start, length, color)
    if not ok:
        return False, []
    return filter_overlapping(patterns, used)


def extend_to_min_length(board, rng, eligible, used, kind, size, color, minimum, points):
    """TryExtendPatternToMinLength 0x5ac5d4c."""
    points = list(points)
    tries = 12
    while len(points) < minimum and tries > 0:
        candidates = adjacent_candidates(eligible, used, points)
        if not candidates:
            break
        length = rng.range(size[0], size[1] + 1)
        ok, segments = build_segment(board, rng, eligible, used, kind, length, candidates, color)
        if ok:
            for seg_points, _ in segments:
                if not seg_points:
                    continue
                taken = set(used) | set(points)
                allowed = set(eligible)
                kept = _distinct([p for p in seg_points if p not in taken and p in allowed])
                if len(kept) < 3:
                    continue
                points.extend(kept)
                if len(points) >= minimum:
                    break
        tries -= 1
    return len(points) >= minimum, points


def eligible_points(board):
    """GetEligiblePaintPoints 0x5ac556c: paintable cells, columns outer."""
    return [(x, y) for x in range(board.width) for y in range(board.height) if board.paintable((x, y))]


def activation_patterns(board, rng, config, activations):
    """TryBuildActivationPatterns 0x5ac47a8: [(points, engine colour)]."""
    index = max(0, activations - 1)
    combos = int(_by_activation(config.get("combos"), index, 0))
    if combos < 1:
        return []
    kinds = list(_by_activation(config.get("patterns"), index, []) or []) or [TURN90]
    low, high = _by_activation(config.get("size_range"), index, (3, 4))
    shortest = max(3, low)
    longest = max(shortest, high)
    cap = max(longest, 4)
    eligible = eligible_points(board)
    if not eligible:
        return []
    result, used = [], set()
    kind = kinds[rng.range(0, len(kinds))]
    fallback = int(_by_activation(config.get("fallback"), index, TURN90))
    attempts = 0x50
    while len(result) < combos and attempts > 0:
        length = rng.range(shortest, longest + 1)
        if kind == RECTANGLE:
            minimum = 4
        elif kind == ALTERNATING:
            length = min(length, board.width)
            minimum = min(shortest, board.width)
        else:
            minimum = shortest
        ok, candidates = build_pattern(board, rng, eligible, used, kind, fallback, length,
                                       combos - len(result))
        if ok:
            for points, color in candidates:
                if points is None or len(points) < 3:
                    continue
                allowed = set(eligible)
                kept = _distinct([p for p in points if p in allowed])
                if len(kept) < 3 or not is_connected(kept):
                    continue
                ok2, kept = extend_to_min_length(board, rng, eligible, used, kind, (minimum, longest),
                                                 color, minimum, kept)
                if not ok2:
                    continue
                if len(kept) > cap:
                    kept = kept[:cap]
                if len(kept) < 4:
                    continue
                fresh = set(used)
                final = []
                for p in kept:
                    if p not in fresh:
                        fresh.add(p)
                        final.append(p)
                if len(final) < minimum or not is_connected(final):
                    continue
                result.append((final, color))
                used.update(final)
                if len(result) >= combos:
                    break
        attempts -= 1
    return result


# ---------------------------------------------------------------- spray cans

CARDINAL = ((1, 0), (-1, 0), (0, 1), (0, -1))   # GetCardinalDirections d__22


def spray_path(board, start, direction):
    """TryBuildSprayPath 0x5ac76f0: to the edge, then the whole edge line,
    its shorter arm first."""
    dx, dy = direction
    if (dx, dy) == (0, 0) or (dx and dy):
        return []
    path, seen, main = [], set(), []
    p = start
    while board.inside(p):
        if p not in seen:
            seen.add(p)
            path.append(p)
        main.append(p)
        p = _add(p, direction)
    end = path[-1] if path else start
    perps = ((1, 0), (-1, 0)) if dx == 0 else ((0, 1), (0, -1))
    arms = []
    for d in perps:
        arm, q = [], _add(end, d)
        while board.inside(q):
            arm.append(q)
            q = _add(q, d)
        arms.append(arm)
    first, second = arms
    out, seen = [], set()
    order = main + ((second + first) if len(second) < len(first) else (first + second))
    for q in order:
        if q not in seen:
            seen.add(q)
            out.append(q)
    return out


def count_energy(board, path, energy_colors, skip_first=True):
    """CountEnergyOnPath 0x5ac80bc."""
    return sum(1 for p in path[1 if skip_first else 0:] if board.color_at(p) in energy_colors)


def has_energy_neighbor(board, p, energy_colors):
    """HasEnergyColorNeighbor 0x5ac86b8."""
    return any(board.inside(q) and board.color_at(q) in energy_colors
               for q in (_add(p, d) for d in CARDINAL))


def has_special_neighbor(board, p, specials):
    """HasSpecialNeighbor 0x5ac82f8: a cardinal neighbour holding a special."""
    return any(board.inside(q) and specials(q) for q in (_add(p, d) for d in CARDINAL))


def eligible_spray_positions(board, allow_edge, blocked):
    """GetEligibleSprayPositions 0x5ac755c: plain active cells, columns outer;
    the board edge only when allowed."""
    out = []
    for x in range(board.width):
        for y in range(board.height):
            p = (x, y)
            if blocked(p):
                continue
            if not allow_edge and (x in (0, board.width - 1) or y in (0, board.height - 1)):
                continue
            out.append(p)
    return out


def choose_spray_positions(board, rng, config, activations, amount, energy_colors, blocked, specials):
    """TryChooseSprayPositions 0x5ac6380: (ok, positions)."""
    if amount < 1:
        return False, []
    index = max(0, activations - 1)
    energy = _by_activation(config.get("spray_energy_range"), index, None)
    if energy is None:
        return False, []
    low, high = energy
    special_chance = int(_by_activation(config.get("spray_special_chance"), index, 0))
    want_special = rng.chance(special_chance) if special_chance >= 1 else False
    blue_chance = int(_by_activation(config.get("neighbor_blues"), index, 0))
    want_blue = rng.chance(blue_chance) if blue_chance >= 1 else False
    eligible = eligible_spray_positions(board, bool(config.get("allow_edge")), blocked)
    if not eligible:
        eligible = eligible_spray_positions(board, True, blocked)
        if not eligible:
            return False, []
    scores = []
    for p in eligible:
        zero, most, total, least = 0, 0, 0, 0x7fffffff
        for d in CARDINAL:
            path = spray_path(board, p, d)
            if not path:
                continue
            e = count_energy(board, path, energy_colors)
            over = e - high if e > high else 0
            diff = low - e if low > e else over
            most = max(most, diff)
            total += diff
            least = min(least, diff)
            if diff == 0:
                zero += 1
        least = least if least != 0x7fffffff else most
        near_special = has_special_neighbor(board, p, specials) if want_special else False
        near_energy = has_energy_neighbor(board, p, energy_colors)
        scores.append((p, zero, most, least, total, near_special, near_energy))
    # Sorts are stable (OrderBy / ThenBy); later keys first.
    if not (want_special or want_blue):
        keys = [lambda s: s[4], lambda s: s[2] - s[3], lambda s: s[2], lambda s: -s[1], lambda s: s[6]]
    else:
        keys = [lambda s: s[4], lambda s: s[2] - s[3], lambda s: s[2], lambda s: -s[1],
                lambda s: not s[6], lambda s: not s[5]]
    for key in keys:
        scores.sort(key=key)
    chosen = []
    for s in scores:
        if len(chosen) >= amount:
            break
        chosen.append(s[0])
    if len(chosen) < amount:
        for s in scores:
            if len(chosen) >= amount:
                break
            if s[0] not in chosen:
                chosen.append(s[0])
    return bool(chosen), chosen[:amount]


class _Bounds:
    def __init__(self, size):
        self.width = self.height = size

    def inside(self, p):
        return 0 <= p[0] < self.width and 0 <= p[1] < self.height


def spray_cells(size, first, step):
    """The swipe's painted cells (row, col), from the cell next to the can:
    SwapPerformed asks the variant for its path (slot 2) where the plain can
    enumerates a line; colour (slot 3) and special (slot 4) stay the can's
    own and none (TryResolveSprayColor / TrySelectSprayPathSpecial return
    false)."""
    (row, col), (drow, dcol) = first, step
    path = spray_path(_Bounds(size), (col, row), (dcol, drow))
    return [(y, x) for x, y in path]
