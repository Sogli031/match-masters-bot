"""Checkmate Charles knights: which cells a knight activation destroys, game 5.817.

Port of Match3Engine.CheckmateCharles.GetAreaOfPieceEffect 0x5a1ad10 and
GetNextKnightPosition 0x5a1b4fc (listings in Debug/reverse/charles), reached
through BoardModel.GetAreaOfChessKnightsPieceExplode 0x5975eac.

One activation moves every knight on the board, not only the one hit:

* the knights are BoardModel.Where over the slots, x-major;
* ``visited`` starts as positionsToDestroy (the cells this destroy pass
  already takes) plus the knights; the area starts as the knights;
* moves = knightMovesOnPieceActivation[min(piecesActivatedTimesThisUse, n-1)];
  each move, each knight in turn draws Chance(favorSpecial) then
  Chance(favorBlue), both arrays indexed by min(PieceUsesThisTurn, n-1);
* candidates: the eight L jumps (static list, order below) that are on the
  board, not visited and IsExplodeOnHit; none -> every L jump plus one king
  step (the second static list), same filter; none -> the knight stays;
* candidates are ordered by a random key (one Next each, ArrayExtensions
  0x3c13d70; a single candidate draws nothing), then stably by b__4: a special
  first when the special roll hit, then the charging colour when the blue
  roll hit, then the rest; the first one is the jump;
* the jump is visited, added to the area and becomes the knight's position;
* afterwards PieceUsesThisTurn and piecesActivatedTimesThisUse go up by one.

While CurrentChessMoves is non-empty (the rest of the action) another knight
activation adds no cells. Replayed on Super Sized research 20261114_172725:
the 10 knight activations of the move's first destroy pass give the same
cells in the same order and the same RNG counter (100/100 for the first
activation after a booster, 0/50 for the second).
"""
from __future__ import annotations

from dataclasses import dataclass

SIM_KNIGHT = 12             # move_strategy.SPECIAL_KNIGHT
SIM_BLUE = 1                # the current player's charging colour on the simulator board
ABILITY_CLASS = "Match3Engine.CheckmateCharles"
USES_KEY = "CheckmateCharlesPieceUsesThisTurnPlayer"
ACTIVATIONS_KEY = "piecesActivatedTimesThisUseKey"

# CheckmateCharles..cctor 0x5a1bc34, Point(x, y): the knight jumps, then the
# king steps the fallback adds to each jump.
KNIGHT_JUMPS = ((2, 1), (2, -1), (1, 2), (-1, 2), (-2, 1), (-2, -1), (1, -2), (-1, -2))
KING_STEPS = ((0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1), (-1, 0), (-1, 1))

# The booster config as recorded (Super Sized 2026-11-14, ability_detail).
# The profile carries ability_detail only while "Snimaj svaki potez" is on.
DEFAULT_CONFIG = {
    "knightMovesOnPieceActivation": (4,),
    "knightMoveFavorSpecialChanceByActivation": (100, 0),
    "knightMoveFavorBlueChanceByActivation": (100, 50),
    "piecesPerPieceActivation": (3,),
    "knightMatchableRefillPositionChanceByActivation": (30,),
    "chanceToBlockNeighbors": -1,
}


@dataclass
class KnightState:
    """The counters one simulated line carries between knight activations."""
    moves: tuple
    favor_special: tuple
    favor_blue: tuple
    uses: int                   # PieceUsesThisTurn
    activations: int            # piecesActivatedTimesThisUse
    moved_this_action: bool = False     # CurrentChessMoves non-empty
    pieces: tuple = DEFAULT_CONFIG["piecesPerPieceActivation"]
    refill_chance: tuple = DEFAULT_CONFIG["knightMatchableRefillPositionChanceByActivation"]
    block_neighbors: int = DEFAULT_CONFIG["chanceToBlockNeighbors"]

    def clone(self) -> "KnightState":
        return KnightState(self.moves, self.favor_special, self.favor_blue,
                           self.uses, self.activations, self.moved_this_action,
                           self.pieces, self.refill_chance, self.block_neighbors)


def _pick(values, index):
    return int(values[min(index, len(values) - 1)])


def _local_index(profile) -> int:
    for index, player in enumerate(profile.get("players") or []):
        if player.get("player_type") == 0:
            return index
    return 0


def knight_state(profile, extra) -> KnightState | None:
    """The Charles counters for this profile, or None when no counter is recorded.

    ``extra`` is the decoded board extraData (both counters live there, keyed
    by the local player's index).
    """
    extra = extra or {}
    index = _local_index(profile)
    uses = extra.get(USES_KEY + str(index))
    activations = extra.get(ACTIVATIONS_KEY + str(index))
    if uses is None or activations is None:
        return None
    config = dict(DEFAULT_CONFIG)
    detail = profile.get("ability_detail") or {}
    if detail.get("class") == ABILITY_CLASS:
        fields = detail.get("fields") or {}
        for key, default in DEFAULT_CONFIG.items():
            value = fields.get(key)
            if isinstance(default, tuple) and value:
                config[key] = tuple(value)
            elif not isinstance(default, tuple) and isinstance(value, int):
                config[key] = value
    return KnightState(config["knightMovesOnPieceActivation"],
                       config["knightMoveFavorSpecialChanceByActivation"],
                       config["knightMoveFavorBlueChanceByActivation"],
                       int(uses), int(activations),
                       pieces=config["piecesPerPieceActivation"],
                       refill_chance=config["knightMatchableRefillPositionChanceByActivation"],
                       block_neighbors=int(config["chanceToBlockNeighbors"]))


def knight_area(board, special, rng, state: KnightState, visited, *, explodes, blue=SIM_BLUE):
    """GetAreaOfPieceEffect over the simulator board, (row, col) cells in area order.

    ``visited``: positionsToDestroy. ``explodes(cell)``: SlotModel.IsExplodeOnHit.
    Consumes ``rng`` and advances ``state``. Returns [] when this action's
    knights already moved.
    """
    if state.moved_this_action:
        return []
    rows, columns = len(board), len(board[0])
    knights = [(y, x) for x in range(columns) for y in range(rows) if int(special[y][x]) == SIM_KNIGHT]
    seen = [tuple(cell) for cell in visited] + knights
    seen_set = set(seen)
    area = list(knights)
    current = list(knights)
    moves = _pick(state.moves, state.activations)
    favor_special = _pick(state.favor_special, state.uses)
    favor_blue = _pick(state.favor_blue, state.uses)

    def allowed(cell):
        y, x = cell
        return 0 <= y < rows and 0 <= x < columns and cell not in seen_set and explodes(cell)

    for _move in range(moves):
        for index, (y, x) in enumerate(current):
            prefer_special = rng.chance(favor_special)
            prefer_blue = rng.chance(favor_blue)
            candidates = [c for c in ((y + dy, x + dx) for dx, dy in KNIGHT_JUMPS) if allowed(c)]
            if not candidates:
                candidates = [c for c in ((y + dy + sy, x + dx + sx) for dx, dy in KNIGHT_JUMPS
                                          for sx, sy in KING_STEPS) if allowed(c)]
            if not candidates:
                continue
            if len(candidates) > 1:
                keys = [rng.next() for _ in candidates]
                candidates = [candidates[i] for i in sorted(range(len(candidates)), key=keys.__getitem__)]

            def rank(cell):
                cy, cx = cell
                if prefer_special and int(special[cy][cx]) != 0:
                    return 0
                if prefer_blue and int(board[cy][cx]) == blue:
                    return 1
                return 2

            jump = min(candidates, key=rank)     # stable: the first of the best rank
            current[index] = jump
            seen.append(jump)
            seen_set.add(jump)
            area.append(jump)
    state.uses += 1
    state.activations += 1
    state.moved_this_action = True
    return area


def knight_count(special) -> int:
    if special is None:
        return 0
    return sum(1 for row in special for value in row if int(value) == SIM_KNIGHT)


def _shuffled(rng, items):
    """ArrayExtensions 0x3c13d70: OrderBy(_ => Next()).ToList(); fewer than two draw nothing."""
    if len(items) < 2:
        return list(items)
    keys = [rng.next() for _ in items]
    return [items[i] for i in sorted(range(len(items)), key=keys.__getitem__)]


def knight_end_move(board, special, rng, state: KnightState, colors, matchable_cells):
    """CheckmateCharles.EndMoveWithPassiveAbility 0x5a1b98c -> RefillExplodedSpecials 0x5a1b9b8.

    Tops the board back up to piecesPerPieceActivation[min(piecesActivatedTimesThisUse,
    n-1)] knights on pieces already there (ConvertToSpecials 0x5a1a9cc keeps the
    colour, no draw). The cells: ChoosePositionsForKnights 0x5a1a850 ->
    BoardModel.GetSlotByColorsMatchablesAndNeighbors 0x5972ebc with every colour
    but the player's, chanceToPickMatchablePiece = knightMatchableRefillPosition-
    ChanceByActivation[min(PieceUsesThisTurn-1, n-1)] and chanceToBlockNeighbors:

    * Chance(chanceToBlockNeighbors) first (one draw; -1 never blocks);
    * the matchable list: the pieces of BoardAnalyzer.GetPossibleMoves(board,
      true) (``matchable_cells``, in order) that are plain (no special), in
      ``colors`` -- shuffled, one draw each;
    * for each knight wanted, while that list lasts: Chance(matchable) takes
      its first cell, a miss takes nothing;
    * the rest: every other plain piece in ``colors``, x-major, shuffled; its
      first cells, then what is left of the matchable list.

    Research 20261114_172725: after each of the 10 knight activations the three
    new knights and the RNG counter at rest match (56-58 draws).
    Returns a new special board.
    """
    special = [list(row) for row in special]
    wanted = _pick(state.pieces, state.activations)
    missing = wanted - knight_count(special)
    if missing < 1:
        return special
    if state.block_neighbors >= 0:
        raise ValueError("Knights: chanceToBlockNeighbors >= 0 is not ported")
    chance = _pick(state.refill_chance, max(0, state.uses - 1))
    rows, columns = len(board), len(board[0])

    def plain(cell):
        y, x = cell
        return int(special[y][x]) == 0 and int(board[y][x]) in colors

    rng.chance(state.block_neighbors)
    matchable = _shuffled(rng, [cell for cell in dict.fromkeys(map(tuple, matchable_cells)) if plain(cell)])
    every_matchable = set(matchable)
    picks = []
    for _ in range(missing):
        if not matchable:
            break
        if rng.chance(chance):
            picks.append(matchable.pop(0))
    short = missing - len(picks)
    if short >= 1:
        others = _shuffled(rng, [(y, x) for x in range(columns) for y in range(rows)
                                 if plain((y, x)) and (y, x) not in every_matchable])
        for _ in range(short):
            source = others if others else matchable
            if not source:
                break
            picks.append(source.pop(0))
    for y, x in picks:
        special[y][x] = SIM_KNIGHT
    return special
