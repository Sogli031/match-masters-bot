"""Swap Freely ("Swap freely, no match required"): free swaps before the move.

Engine rules (MatchRulesModel, read from memory in `engine_fields`):
``anySwapValid`` accepts a swap that makes no match -- the two tiles simply
stay swapped -- and ``reduceMoveOnMatchOnly`` spends a move only on a swap that
does match. Together every non-matching swap is free: the board can be
rearranged before the move is paid for. The mode card adds "Square matches are
possible" (``isSquareMatch``) and "Each colour has a different score"
(``_colorScoreOverride``); both already reach the bot through the rules and the
live score legend.

Strategy: look far ahead over free swaps of two plain tiles (no special is
ever moved -- swiping a special fires it) and build the most valuable *paid*
move: colour points of the cleared tiles, plus what the shape leaves behind
(four -> line special, square -> crosshair, L/T -> bomb, five -> disco) and
the extra move a 4+ / square earns. The boards in between are worth nothing
by themselves; the search ranks them by how close the setup is.

The plan is kept and played one swap at a time (`FreeSwapGuard`); it is
replanned only when the board is not the one the plan expected. When no plan
beats the best move already on the board, the ordinary engine plays its move
as always. A free swap never refills, so a plan is exact up to the paid swap.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from move_strategy import BLUE, EMPTY, WHITE, Direction, classify_cells

# Tiles a shape's special clears later, in cells (the special itself is
# random/positional, so this is a mean, not a simulation).
SHAPE_BONUS_CELLS = {"three": 0.0, "four": 6.0, "square": 3.0, "l": 8.0,
                     "t_or_cross": 8.0, "five": 10.0}
EXTRA_MOVE_SHAPES = frozenset({"four", "square", "l", "t_or_cross", "five"})
# An extra move is another whole move; worth about this many average tiles.
EXTRA_MOVE_CELLS = 8.0
# Each free swap costs wall time (swipe + settle); a small tile penalty so a
# shorter plan wins a tie.
SWAP_COST_CELLS = 0.25
# Gain the plan must bring over the best move already on the board, in average
# tiles, before a free swap is played at all.
MIN_GAIN_CELLS = 1.5
# Long look-ahead: a five far away needs many swaps; the clock caps it below.
MAX_DEPTH = 24
# The general (any shape) beam stays short: it is greedy by construction.
SHORT_DEPTH = 3
BEAM_WIDTH = 16
TIME_BUDGET_SECONDS = 3.0
# Free swaps allowed between two paid moves (loop guard).
MAX_FREE_SWAPS_PER_MOVE = 40
# Wall time one free swap takes (swipe, animation, the next memory read).
SECONDS_PER_FREE_SWAP = 1.3


def _flag(rules, *names):
    rules = rules or {}
    engine_fields = rules.get("engine_fields")
    engine_fields = engine_fields if isinstance(engine_fields, dict) else {}
    for source in (rules, engine_fields):
        for name in names:
            value = source.get(name)
            if value is not None:
                return bool(value)
    return None


def spends_moves_on_match_only(rules) -> bool:
    return bool(_flag(rules, "reduce_move_on_match_only", "reduceMoveOnMatchOnly"))


def free_swaps_active(rules) -> bool:
    """anySwapValid and a move spent only on a match: non-matching swaps are free."""
    return bool(_flag(rules, "any_swap_valid", "anySwapValid")) and spends_moves_on_match_only(rules)


@dataclass
class FreeSwapPlan:
    swaps: list = field(default_factory=list)   # [((r, c), (r, c)), ...] free swaps
    final_move: tuple | None = None             # the paid (matching) swap at the end
    value: float = 0.0                          # its value, in points
    baseline: float = 0.0                       # best matching swap on the board now
    baseline_move: tuple | None = None
    expanded: int = 0
    note: str = ""

    @property
    def gain(self) -> float:
        return self.value - self.baseline


def _plain(value) -> bool:
    return BLUE <= value <= WHITE


def _movable(rows, special, r, c) -> bool:
    return _plain(rows[r][c]) and (special is None or special[r][c] == EMPTY)


def _match_cells_at(rows, r, c, square: bool) -> set:
    """Cells of every line (3+) and 2x2 square through (r, c) in its colour."""
    color = rows[r][c]
    if not _plain(color):
        return set()
    size_r, size_c = len(rows), len(rows[0])
    cells = set()
    left = c
    while left > 0 and rows[r][left - 1] == color:
        left -= 1
    right = c
    while right + 1 < size_c and rows[r][right + 1] == color:
        right += 1
    if right - left >= 2:
        cells.update((r, x) for x in range(left, right + 1))
    up = r
    while up > 0 and rows[up - 1][c] == color:
        up -= 1
    down = r
    while down + 1 < size_r and rows[down + 1][c] == color:
        down += 1
    if down - up >= 2:
        cells.update((y, c) for y in range(up, down + 1))
    if square:
        for dr in (-1, 0):
            for dc in (-1, 0):
                top, lft = r + dr, c + dc
                if 0 <= top and top + 1 < size_r and 0 <= lft and lft + 1 < size_c:
                    block = ((top, lft), (top, lft + 1), (top + 1, lft), (top + 1, lft + 1))
                    if all(rows[y][x] == color for y, x in block):
                        cells.update(block)
    return cells


def _swap(rows, a, b):
    rows[a[0]][a[1]], rows[b[0]][b[1]] = rows[b[0]][b[1]], rows[a[0]][a[1]]


def _pairs(size_r, size_c):
    for r in range(size_r):
        for c in range(size_c):
            if c + 1 < size_c:
                yield (r, c), (r, c + 1)
            if r + 1 < size_r:
                yield (r, c), (r + 1, c)


class _Scorer:
    def __init__(self, color_values, extra_moves: bool):
        self.values = {}
        for key, value in (color_values or {}).items():
            try:
                self.values[int(key)] = float(value)
            except (TypeError, ValueError):
                continue
        plain = [self.values.get(color, 1.0) for color in range(BLUE, WHITE)]
        self.avg = max(0.5, sum(plain) / len(plain))
        self.extra_moves = extra_moves

    def group_value(self, color, cells) -> float:
        kind = classify_cells(cells)
        value = len(cells) * self.values.get(color, 1.0)
        value += SHAPE_BONUS_CELLS.get(kind, 0.0) * self.avg
        if self.extra_moves and kind in EXTRA_MOVE_SHAPES:
            value += EXTRA_MOVE_CELLS * self.avg
        return value

    def swap_value(self, color_a, cells_a, color_b, cells_b) -> float:
        return ((self.group_value(color_a, cells_a) if cells_a else 0.0)
                + (self.group_value(color_b, cells_b) if cells_b else 0.0))


def _try_pair(rows, a, b, square):
    """Swap, read the matches through both cells, swap back."""
    _swap(rows, a, b)
    cells_a = _match_cells_at(rows, a[0], a[1], square)
    cells_b = _match_cells_at(rows, b[0], b[1], square)
    color_a, color_b = rows[a[0]][a[1]], rows[b[0]][b[1]]
    _swap(rows, a, b)
    return color_a, cells_a, color_b, cells_b


def _scan(rows, special, square, scorer, last=None):
    """One pass over every movable pair: the best matching swap and the free ones."""
    best_value, best_move, free = 0.0, None, []
    for a, b in _pairs(len(rows), len(rows[0])):
        if rows[a[0]][a[1]] == rows[b[0]][b[1]]:
            continue
        if not (_movable(rows, special, *a) and _movable(rows, special, *b)):
            continue
        color_a, cells_a, color_b, cells_b = _try_pair(rows, a, b, square)
        if cells_a or cells_b:
            value = scorer.swap_value(color_a, cells_a, color_b, cells_b)
            if value > best_value:
                best_value, best_move = value, (a, b)
        elif last is None or {a, b} != last:
            free.append((a, b))
    return best_value, best_move, free


def _color_tiles(rows, special, color):
    return [(r, c) for r in range(len(rows)) for c in range(len(rows[0]))
            if rows[r][c] == color and _movable(rows, special, r, c)]


def _five_targets(rows, special):
    """Every 5-line a five can be built on: (cells, perpendicular neighbours of the gap).

    A five cannot be laid tile by tile -- the third tile in a row is already a
    match -- so the setup is ``c c _ c c`` with one more ``c`` beside the gap;
    the paid swap then drops it in.
    """
    size_r, size_c = len(rows), len(rows[0])
    out = []
    for horizontal in (True, False):
        for r in range(size_r if horizontal else size_r - 4):
            for c in range(size_c - 4 if horizontal else size_c):
                cells = [(r, c + i) if horizontal else (r + i, c) for i in range(5)]
                if not all(_movable(rows, special, *cell) for cell in cells):
                    continue
                mid = cells[2]
                sides = ([(mid[0] - 1, mid[1]), (mid[0] + 1, mid[1])] if horizontal
                         else [(mid[0], mid[1] - 1), (mid[0], mid[1] + 1)])
                sides = [cell for cell in sides if 0 <= cell[0] < size_r
                         and 0 <= cell[1] < size_c and _movable(rows, special, *cell)]
                if sides:
                    out.append((cells, sides))
    return out


def _distance(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _setup_cost(rows, special, color, cells, sides) -> int:
    """Swaps (Manhattan, greedy) still needed for ``c c _ c c`` + ``c`` beside the gap."""
    tiles = _color_tiles(rows, special, color)
    goals = [cells[0], cells[1], cells[3], cells[4]]
    used = {goal for goal in goals if rows[goal[0]][goal[1]] == color}
    cost = 0
    for goal in goals:
        if goal in used:
            continue
        free = [t for t in tiles if t not in used and t not in goals]
        if not free:
            return 10 ** 6
        tile = min(free, key=lambda t: _distance(t, goal))
        used.add(tile)
        cost += _distance(tile, goal)
    best_side = 10 ** 6
    for side in sides:
        if rows[side[0]][side[1]] == color and side not in used:
            best_side = 0
            break
        free = [t for t in tiles if t not in used and t not in goals and t != cells[2]]
        if free:
            best_side = min(best_side, min(_distance(t, side) for t in free))
    return cost + best_side


def _swaps_moving(rows, special, color, square, last):
    """Free swaps that move a tile of ``color``, and the matching ones met on the way."""
    size_r, size_c = len(rows), len(rows[0])
    free, matches, seen = [], [], set()
    for tile in _color_tiles(rows, special, color):
        for dr, dc in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            other = (tile[0] + dr, tile[1] + dc)
            if not (0 <= other[0] < size_r and 0 <= other[1] < size_c):
                continue
            pair = (min(tile, other), max(tile, other))
            if pair in seen or rows[other[0]][other[1]] == color:
                continue
            seen.add(pair)
            if not _movable(rows, special, *other):
                continue
            color_a, cells_a, color_b, cells_b = _try_pair(rows, pair[0], pair[1], square)
            if cells_a or cells_b:
                matches.append((pair, color_a, cells_a, color_b, cells_b))
            elif last is None or set(pair) != last:
                free.append(pair)
    return free, matches


def plan_free_swaps(board, special_board=None, *, allow_square_matches=False,
                    color_values=None, extra_move_enabled=True, max_swaps=MAX_DEPTH,
                    beam_width=BEAM_WIDTH, time_budget=TIME_BUDGET_SECONDS) -> FreeSwapPlan:
    """Free swaps that set up the most valuable paid move; ``swaps`` empty = play now.

    Two searches share the budget. A long, goal-directed one builds a five in
    the colours worth most: it ranks boards by how many swaps the setup still
    needs, not by what they score now, so it walks through boards worth nothing
    until the last swap. A short general beam picks up any shape a few swaps
    away. Every matching swap met on the way is a candidate; the best one,
    less a small cost per free swap, wins.
    """
    started = time.perf_counter()
    budget = max(0.05, time_budget)
    deadline = started + budget
    rows = [[int(v) for v in row] for row in board]
    special = None if special_board is None else [[int(v) for v in row] for row in special_board]
    scorer = _Scorer(color_values, extra_move_enabled is not False)
    square = bool(allow_square_matches)
    base_value, base_move, free = _scan(rows, special, square, scorer)
    plan = FreeSwapPlan(final_move=base_move, value=base_value, baseline=base_value,
                        baseline_move=base_move)
    if max_swaps <= 0:
        plan.note = "nema vremena za slobodne zamene"
        return plan
    best = [base_value]

    def offer(path, move, value):
        score = value - SWAP_COST_CELLS * scorer.avg * len(path)
        if move is not None and path and score > best[0]:
            best[0] = score
            plan.swaps, plan.final_move, plan.value = list(path), move, value

    # Goal-directed: fives, most valuable colour first, cheapest setup first.
    targets = []
    for cells, sides in _five_targets(rows, special):
        for color in range(BLUE, WHITE + 1):
            if len(_color_tiles(rows, special, color)) < 5:
                continue
            cost = _setup_cost(rows, special, color, cells, sides)
            if cost > max_swaps:
                continue
            value = scorer.group_value(color, set(cells))
            targets.append((value - SWAP_COST_CELLS * scorer.avg * cost, cost, color, cells, sides))
    targets.sort(key=lambda item: (-item[0], item[1]))
    long_deadline = started + 0.75 * budget
    for _, _, color, cells, sides in targets[:4]:
        if time.perf_counter() > long_deadline:
            break
        beam = [(_setup_cost(rows, special, color, cells, sides), [], rows, None)]
        seen = {tuple(map(tuple, rows))}
        for _ in range(max_swaps):
            children = []
            for _, path, state, last in beam:
                if time.perf_counter() > long_deadline:
                    break
                moves, matches = _swaps_moving(state, special, color, square, last)
                for pair, color_a, cells_a, color_b, cells_b in matches:
                    offer(path, pair, scorer.swap_value(color_a, cells_a, color_b, cells_b))
                for a, b in moves:
                    child = [row[:] for row in state]
                    _swap(child, a, b)
                    key = tuple(map(tuple, child))
                    if key in seen:
                        continue
                    seen.add(key)
                    plan.expanded += 1
                    children.append((_setup_cost(child, special, color, cells, sides),
                                     path + [(a, b)], child, {a, b}))
            if not children or time.perf_counter() > long_deadline:
                break
            children.sort(key=lambda item: item[0])
            beam = children[:beam_width * 2]

    # Short general beam: any shape, ranked by the best match on the board.
    seen = {tuple(map(tuple, rows))}
    beam = [(base_value, [], rows, free)]
    for _ in range(min(max_swaps, SHORT_DEPTH)):
        children = []
        for _, path, state, state_free in beam:
            for a, b in state_free:
                if time.perf_counter() > deadline:
                    break
                child = [row[:] for row in state]
                _swap(child, a, b)
                key = tuple(map(tuple, child))
                if key in seen:
                    continue
                seen.add(key)
                value, move, child_free = _scan(child, special, square, scorer, last={a, b})
                plan.expanded += 1
                new_path = path + [(a, b)]
                offer(new_path, move, value)
                children.append((value, new_path, child, child_free))
        if not children or time.perf_counter() > deadline:
            break
        children.sort(key=lambda item: item[0], reverse=True)
        beam = children[:beam_width]

    if plan.swaps and plan.value - plan.baseline < MIN_GAIN_CELLS * scorer.avg:
        plan.swaps, plan.final_move, plan.value = [], base_move, base_value
        plan.note = "slobodne zamene ne donose dovoljno"
    return plan


def color_values_from_snapshot(snapshot, fallback=None) -> dict:
    """Points per colour from SlotModel.score of plain tiles (majority per colour).

    "Each colour has a different score" is `_colorScoreOverride`; the engine
    writes the result into every slot's score, so all colours are read here,
    blue and red included (the GUI legend covers only four).
    """
    board = (snapshot or {}).get("board") or []
    votes = {}
    for slot in (snapshot or {}).get("slots") or []:
        try:
            if int(slot.get("value", 0)) != 0:
                continue
            color = int(board[int(slot["y"])][int(slot["x"])])
            score = int(slot["score"])
        except (IndexError, KeyError, TypeError, ValueError):
            continue
        if _plain(color) and score > 0:
            votes.setdefault(color, {}).setdefault(score, 0)
            votes[color][score] += 1
    values = {int(k): float(v) for k, v in (fallback or {}).items()}
    for color, counted in votes.items():
        values[color] = float(max(counted.items(), key=lambda item: item[1])[0])
    return values


def apply_swap(board, swap):
    rows = [[int(v) for v in row] for row in board]
    _swap(rows, swap[0], swap[1])
    return rows


def swap_direction(start, target) -> Direction:
    dr, dc = target[0] - start[0], target[1] - start[1]
    return {(0, 1): Direction.RIGHT, (0, -1): Direction.LEFT,
            (1, 0): Direction.DOWN, (-1, 0): Direction.UP}[(dr, dc)]


def affordable_free_swaps(turn_time_left, remaining_moves, seconds_per_move,
                          reserve_seconds=4.0) -> int:
    """How many free swaps the turn clock still pays for, after the real moves."""
    if turn_time_left is None:
        return MAX_DEPTH
    moves = max(1, int(remaining_moves or 1))
    spare = float(turn_time_left) - moves * float(seconds_per_move or 0.0) - reserve_seconds
    return max(0, min(MAX_DEPTH, int(spare // SECONDS_PER_FREE_SWAP)))


class FreeSwapGuard:
    """Keeps the plan between swaps and stops if the engine disagrees.

    A free swap that left the board as it was (the game refused it) or that
    spent a move means the rules were read wrong; free swaps then stay off for
    the rest of the match.
    """

    def __init__(self):
        self.reset()

    def reset(self):
        self.disabled_reason = None
        self.count = 0
        self._moves_key = None
        self._pending = None      # (board before, moves before, board expected)
        self._plan_rest = []      # swaps still to play
        self._plan_expected = None
        self.plan = None

    def observe(self, board, moves, turn) -> str | None:
        """Call with every board the bot is about to plan on."""
        grid = [[int(v) for v in row] for row in board]
        if self._pending is not None:
            before, moves_before, expected = self._pending
            self._pending = None
            if grid == before:
                self.disabled_reason = "igra nije prihvatila zamenu bez meca"
            elif moves is not None and moves_before is not None and moves < moves_before:
                self.disabled_reason = "zamena bez meca je potrosila potez"
            if grid != expected:
                self._drop_plan()
        key = (moves, turn)
        if key != self._moves_key:
            self._moves_key = key
            self.count = 0
            self._drop_plan()
        return self.disabled_reason

    def _drop_plan(self):
        self._plan_rest, self._plan_expected, self.plan = [], None, None

    def allowed(self) -> int:
        if self.disabled_reason:
            return 0
        return max(0, MAX_FREE_SWAPS_PER_MOVE - self.count)

    def next_swap(self, board):
        """The kept plan's next swap if the board is the one it expects."""
        grid = [[int(v) for v in row] for row in board]
        if self._plan_rest and grid == self._plan_expected:
            return self._plan_rest[0]
        if grid != self._plan_expected:
            self._drop_plan()
        return None

    def final_move(self, board):
        """The paid swap the finished plan was built for, on the board it expects."""
        grid = [[int(v) for v in row] for row in board]
        if self.plan is not None and not self._plan_rest and grid == self._plan_expected:
            return self.plan.final_move
        return None

    def keep(self, board, plan: FreeSwapPlan):
        self.plan = plan
        self._plan_rest = list(plan.swaps)
        self._plan_expected = [[int(v) for v in row] for row in board]

    def played(self, board, moves, swap):
        before = [[int(v) for v in row] for row in board]
        after = apply_swap(before, swap)
        self.count += 1
        self._pending = (before, moves, after)
        if self._plan_rest and tuple(map(tuple, self._plan_rest[0])) == tuple(map(tuple, swap)):
            self._plan_rest = self._plan_rest[1:]
            self._plan_expected = after
        else:
            self._drop_plan()
