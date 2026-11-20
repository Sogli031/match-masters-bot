"""Vinnie SE powerup variant: the pending extra hearts, game 5.817.

CupidSEPowerUpVariant1.EndMoveWithPassiveAbility 0x5abdf40 places the hearts
an activation left pending (board extra data "CupidSEPendingExtraHearts":
"amount,useTwoColors,matchablePlacementChance") at the end of the next move.
Decompiled with Ghidra (Debug/reverse/cupid_powerup, named/*.c). Points are
(x, y) = (column, row); the boards are the simulator's [row][column].

Per heart, FindExtraHeartPlacementByPriority 0x5ac0fd4:
  targets  = Cupid.GatherTargetOptions(logic, allowBlue = energyChance > 0,
             excluded = hearts placed so far): BoardModel.ForEach (x outer)
             of CanBeTarget 0x5a33384 -- canBeMatched, no special value, not
             on the edge (allowBoardEdgePositions False), every cell of its
             plus paintable to its colour;
  three lists, each the intersection with targets: extra-move cells
  (isHighRank combos of GetPossibleMoves), energy cells (combos of a
  charging colour) and matchable cells (every combo); a combo's cells are
  mapped back to before the swap (its origin -> the swap's other cell);
  for each attribute in priority order: chance < 1 skips it; chance < 100
  draws Chance(chance); on success SelectCandidate of its list (empty: none);
  none chosen: SelectCandidate of all targets.
SelectCandidate 0x5ac2d20: Distinct, OrderBy x, ThenBy y, Shuffle (one Next
per element when two or more), first.

shortcut: only the one-colour heart of a pending request is placed (the
recorded configuration, oneColorHeartAfterActivation 1, twoColors 0); a new
activation inside a simulated move leaves no pending request here. Upgrade
when a two-colour request or a planned activation is recorded.
"""
from __future__ import annotations

PENDING_KEY = "CupidSEPendingExtraHearts"
EXTRA_MOVE, ENERGY, MATCHABLE = ("chanceToConvertOnExistingExtraMove",
                                 "chanceToConvertOnExistingMatchableEnergyMove",
                                 "chanceToConvertOnExistingMatchableMove")
PREFIX = "oneColorHeartAfterActivation_"


class UnsupportedCupid(ValueError):
    pass


def pending_requests(extra: dict | None) -> list[tuple[int, bool, int]]:
    """"1,0,100" (several joined by '|' or ';') -> [(amount, two colours, chance)]."""
    raw = str((extra or {}).get(PENDING_KEY) or "").strip()
    out = []
    for part in raw.replace(";", "|").split("|"):
        fields = [f.strip() for f in part.split(",") if f.strip()]
        if len(fields) == 3:
            out.append((int(fields[0]), fields[1] not in ("0", "False", "false"), int(fields[2])))
    return out


def chance_from_list(text, activations: int) -> int:
    """GetChanceFromList 0x5abdb7c: list[clamp(activations - 1, 0, n - 1)], none -> 0."""
    values = [int(v) for v in str(text or "").split(",") if v.strip()]
    if not values:
        return 0
    return values[max(0, min(activations - 1, len(values) - 1))]


def select_candidate(rng, cells):
    """SelectCandidate: (x, y) or None; draws only for two or more."""
    cells = sorted(set(cells))
    if not cells:
        return None
    return rng.shuffled(cells)[0]


def place_pending_hearts(board, special, rng, params, requests, *, heart, matchable, extra_move,
                         energy, can_target, activations=1):
    """Returns a new special board with the hearts (``heart`` value) placed.

    ``matchable`` / ``extra_move`` / ``energy``: the three cell sets (x, y);
    ``can_target(x, y)``: CanBeTarget with allowBlue already decided.
    """
    special = [list(row) for row in special]
    rows, cols = len(board), len(board[0])
    placed = set()
    extra_chance = chance_from_list(params.get(PREFIX + EXTRA_MOVE), activations)
    energy_chance = chance_from_list(params.get(PREFIX + ENERGY), activations)
    priority = [p.strip() for p in str(params.get(PREFIX + "attributePriority") or "").split(",") if p.strip()]
    if not priority:
        priority = [EXTRA_MOVE, ENERGY, MATCHABLE]
    for amount, two_colors, matchable_chance in requests:
        if two_colors:
            raise UnsupportedCupid("Vinnie SE: two-colour pending heart is not ported")
        for _ in range(amount):
            targets = [(x, y) for x in range(cols) for y in range(rows)
                       if (x, y) not in placed and can_target(x, y)]
            if not targets:
                raise UnsupportedCupid("Vinnie SE: fallback target options are not ported")
            options = set(targets)
            lists = {EXTRA_MOVE: (extra_chance, [p for p in extra_move if p in options]),
                     ENERGY: (energy_chance, [p for p in energy if p in options]),
                     MATCHABLE: (matchable_chance, [p for p in matchable if p in options])}
            pick = None
            for name in priority:
                if name not in lists:
                    continue
                chance, cells = lists[name]
                if chance < 1:
                    continue
                if chance >= 100 or rng.chance(chance):
                    pick = select_candidate(rng, cells)
                    if pick is not None:
                        break
            if pick is None:
                pick = select_candidate(rng, targets)
            placed.add(pick)
            x, y = pick
            special[y][x] = heart
    return special


def _combos(board, special):
    """GetPossibleMoves(board, true) combos as (cells mapped before the swap, high rank, colour).

    Columns outer, Down then Right; a same-colour swap or two classic
    specials make no line combo here (tools: the merge and Lightning combos
    lowered the recorded hits, 59 against 63 of 81).
    shortcut: square matches are not counted; add them when a square-match
    Vinnie SE game is recorded.
    """
    n = len(board)
    out = []
    for x in range(n):
        for y in range(n):
            for dx, dy in ((0, 1), (1, 0)):
                a, b = (x, y), (x + dx, y + dy)
                if b[0] >= n or b[1] >= n:
                    continue
                ca, cb = int(board[a[1]][a[0]]), int(board[b[1]][b[0]])
                if ca <= 0 or cb <= 0 or ca == cb:
                    continue
                if int(special[a[1]][a[0]]) in CLASSIC and int(special[b[1]][b[0]]) in CLASSIC:
                    continue
                g = [[int(v) for v in row] for row in board]
                g[a[1]][a[0]], g[b[1]][b[0]] = cb, ca
                for (ex, ey), source in ((a, b), (b, a)):
                    color = g[ey][ex]
                    runs = []
                    for axis in (((-1, 0), (1, 0)), ((0, -1), (0, 1))):
                        line = []
                        for ddx, ddy in axis:
                            xx, yy = ex + ddx, ey + ddy
                            while 0 <= xx < n and 0 <= yy < n and g[yy][xx] == color:
                                line.append((xx, yy))
                                xx, yy = xx + ddx, yy + ddy
                        if len(line) >= 2:
                            runs.append(line)
                    if runs:
                        cells = [c for run in runs for c in run] + [source]
                        out.append((cells, len(runs) == 2 or any(len(r) >= 3 for r in runs), color))
    return out


CLASSIC = (1, 2, 3, 4, 46)


def cell_sets(board, special, energy_colors):
    """(matchable, extra-move, energy) cells, (x, y), first-seen order."""
    matchable, high, energy = {}, {}, {}
    for cells, is_high, color in _combos(board, special):
        for p in cells:
            matchable.setdefault(p, None)
            if is_high:
                high.setdefault(p, None)
            if color in energy_colors:
                energy.setdefault(p, None)
    return list(matchable), list(high), list(energy)


def can_target(board, special):
    """CanBeTarget for the recorded config: inside the border, a plain coloured
    piece whose plus is all pieces (63 of 81 recorded placements exact; a
    neighbour with a special still counts as paintable)."""
    n = len(board)

    def ok(x, y):
        if not (0 < x < n - 1 and 0 < y < n - 1):
            return False
        if int(board[y][x]) <= 0 or int(special[y][x]) != 0:
            return False
        return all(int(board[yy][xx]) > 0 for xx, yy in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)))
    return ok


def end_move(board, special, rng, extra, params, *, heart, energy_colors):
    """The pending hearts of the board extra data placed after a swipe; None when there are none."""
    requests = pending_requests(extra)
    if not requests or str((params or {}).get("oneColorHeartAfterActivation", "0")) in ("0", ""):
        return None
    matchable, high, energy = cell_sets(board, special, energy_colors)
    return place_pending_hearts(board, special, rng, params or {}, requests, heart=heart, matchable=matchable,
                                extra_move=high, energy=energy, can_target=can_target(board, special))
