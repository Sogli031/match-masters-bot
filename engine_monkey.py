"""Monkey JooJoo (booster 40) activation and skull refill, game 5.817.

Port of Match3Engine.MonkeyJoojoo.Use 0x5a7b09c -> ChoosePositions 0x5a7b6b0
-> ConvertToSpecialsAndAutoExplode 0x5a7c074 -> ConvertToSpecials 0x5a7c148,
with the passive RefillExplodedSpecials 0x5a7c610 -> ConvertToSpecials.
Listings in Debug/reverse/monkey. Points are (x, y) = (column, row) in the
engine; the boards are the simulator's [row][column].

Use (Solo config: piecesAmount 5, maxTries 5, autoExplodeAmount 3,
scoreTarget 35, skullsPerActivation "4,1", chanceToPickMatchablePiece 20):

* sets itself as the passive ability and WasJustActivated (offset 0x78) to 1;
* maxTries times ChoosePositions(logic, false). With WasJustActivated the
  count is skullsPerActivation[min(ActivatesThisTurn - 1, n - 1)] (the branch
  at 0x5a7b9b4, no subtraction of the skulls already on the board); the
  candidates are the plain pieces (SlotValue 0) of AllowedColors (engine 6, 3,
  5, 7, 8; .cctor 0x5a7c9d0) in x-major Where order, shuffled with one draw
  per candidate, first `count` taken (GetSlotPrioritize 0x5972158 with an
  always-false priority);
* when more than one candidate came back, each is applied to a GameLogic
  clone (GameLogic::Clone 0x5956368: the clone carries its own RNG copy, so
  the evaluation draws do not move the real counter), converted and
  auto-exploded, and scored by the player's score (Use 0x5a7b4d4-0x5a7b50c);
* the pick is the candidate whose score is closest to scoreTarget (lambda
  Use>b__0 0x5a7d148 returns -abs(score - target)); a candidate that hits the
  target ends the search;
* the chosen candidate is converted on the real logic:
  ConvertToSpecialsAndAutoExplode converts every chosen cell to a skull
  (SlotValue 24 / engine 0x18, piece value 24, b__12_1) and destroys
  min(len(positions), autoExplodeAmount) of them -- in the order ChoosePositions
  returned -- then tops the destroyed set up to autoExplodeAmount with the
  other skulls already on the board (BoardModel.Where(IsSkull), x-major,
  `!already taken`), all as one ComboModel(type 10, 0x28). The skulls that
  were not destroyed stay on the board.

EndMoveWithPassiveAbility 0x5a7c650 (after every move, and via
RefillExplodedSpecials in Solo) tops the board back up to the throws' sum:
target = min(sum(skullsPerActivation[min(i, n - 1)] for i in 0..Activates-1),
maxPieces); ChoosePositions(logic, true) with the chance to pick a matchable
piece (Solo 20) -- that part is engine_refill.EngineRefill.joojoo_end_move.

Measured on Super Sized Solo research 20261120_111530 (12 activations): the
skull count on the resting board after throw n is 4, 6, 7, 8, ... 16, so the
sum above is right from the third throw on; see docs/monkey_joojoo.md for the
second throw and what is still open.
"""
from __future__ import annotations

MONKEY_JOOJOO = 40
ABILITY_CLASS = "Match3Engine.MonkeyJoojoo"
# engine SlotValue of a skull on the special board (get_BoosterPieceValueType 0x5a7a7b4)
SKULL_VALUE = 24
# The same skull in the simulator's own special board (move_strategy
# SPECIAL_JOOJOO_SKULL, engine_refill.SIM_JOOJOO_SKULL). Writing the engine value
# here left the surviving skull of a throw unreadable to the refill -- it raised
# "Unported simulator special/color" on most throws, and when it did not the
# skull was inert instead of firing along its colour when matched
# (tools/monkey_trace.py, activation 002->003 of 20261120_111530).
SIM_SKULL = 19
# Both spellings count as "already on the board" when the auto-explode tops up.
SKULL_VALUES = (SIM_SKULL, SKULL_VALUE)
# MonkeyJoojoo.AllowedColors (.cctor 0x5a7c9d0): engine Orange, Green, Yellow, 7, 8.
ALLOWED_COLORS = (6, 3, 5, 7, 8)
BASE_CONFIG = {"piecesAmount": 5, "autoExplodeAmount": 5, "chanceToPickMatchablePiece": 40,
               "scoreTarget": 35, "maxTries": 5, "specialPieceScoreValue": 0,
               "removePreviousPieces": False, "skullsPerActivation": [5, 3, 2]}
# ability_config.json, type 40, Solo (pvpMode 1): the recorded game's params.
SOLO_CONFIG = {"autoExplodeAmount": 3, "chanceToPickMatchablePiece": 20, "skullsPerActivation": [4, 1]}
MAX_PIECES = 99                       # maxPieces read from the live ability (0x80)
# Measured, Solo only: the second throw raised the resting skull count by two
# instead of one (research 20261120_111530; see throw_delta).
SOLO_EXTRA_AFTER_FIRST = 1
NO_SWAP = (-1, -1)                    # strategy_lab.simulation.NO_SWAP_CELL


class UnsupportedMonkey(ValueError):
    pass


def _ints(text):
    return [int(part) for part in str(text).replace("|", ",").split(",") if part.strip()]


def config_from(profile, params=None) -> dict:
    """The ability's memory fields (profile.ability_detail), else the player's
    special_ability_params (strings), else the Solo defaults on a Solo board."""
    config = dict(BASE_CONFIG)
    rules = (profile or {}).get("rules") or {}
    config["solo"] = rules.get("pvpMode") == 1
    if config["solo"]:
        config.update(SOLO_CONFIG)
    detail = (profile or {}).get("ability_detail") or {}
    fields = detail.get("fields") if detail.get("class") == ABILITY_CLASS else None
    params = params if isinstance(params, dict) else {}
    for key in ("piecesAmount", "autoExplodeAmount", "chanceToPickMatchablePiece", "scoreTarget",
                "maxTries", "specialPieceScoreValue"):
        if params.get(key) is not None:
            config[key] = int(params[key])
    if params.get("skullsPerActivation") is not None:
        config["skullsPerActivation"] = _ints(params["skullsPerActivation"])
    if params.get("removePreviousPieces") is not None:
        config["removePreviousPieces"] = str(params["removePreviousPieces"]).lower() == "true"
    for key in ("piecesAmount", "autoExplodeAmount", "chanceToPickMatchablePiece", "scoreTarget",
                "maxTries", "specialPieceScoreValue", "skullsPerActivation", "removePreviousPieces"):
        if fields and fields.get(key) is not None:
            config[key] = fields[key]
    if config["removePreviousPieces"]:
        raise UnsupportedMonkey("Monkey JooJoo: removePreviousPieces is not ported")
    return config


def per_activation(config) -> list[int]:
    values = [int(v) for v in config.get("skullsPerActivation") or ()]
    return values or [0]


def skull_pick(config, activations: int) -> int:
    """skullsPerActivation[min(ActivatesThisTurn - 1, n - 1)]: the skulls one throw places."""
    values = per_activation(config)
    return max(0, int(values[max(0, min(int(activations) - 1, len(values) - 1))]))


def throw_delta(config, skulls_before: int) -> int:
    """How much one throw raises the resting skull count.

    Code: skullsPerActivation[min(ActivatesThisTurn - 1, n - 1)]. Measured on
    Super Sized research 20261120_111530 the resting boards hold 4, 6, 7, 8 ...
    16 for throws 1..12: the first throw sets 4 and every later throw adds one,
    except the second, which added two. The +1 at the second throw is measured
    only -- the throw places one skull per the config, so either the refill ran
    twice there or a second skull came in; cause not found
    (docs/monkey_joojoo.md). Everything else is the recorded board's own count
    plus this delta, so the port does not depend on ActivatesThisTurn, which
    the game also increments for passive refills (record 008 reads 3 after two
    throws).
    """
    values = per_activation(config)
    if skulls_before <= 0:
        return int(values[0])
    delta = int(values[min(1, len(values) - 1)])
    if config.get("solo") and skulls_before == int(values[0]):
        delta += SOLO_EXTRA_AFTER_FIRST
    return delta


def skull_target(config, skulls_before: int) -> int:
    """The resting board's skull count after this throw, at most maxPieces."""
    return min(int(skulls_before) + throw_delta(config, int(skulls_before)), MAX_PIECES)


def plain_cells(board, special, profile) -> list[tuple[int, int]]:
    """Candidates: plain pieces (SlotValue 0) of an allowed colour, x-major Where order."""
    from engine_refill import color_maps

    to_sim = color_maps(profile)[1]
    allowed = {to_sim[c] for c in ALLOWED_COLORS if c in to_sim}
    rows, columns = len(board), len(board[0])
    return [(y, x) for x in range(columns) for y in range(rows)
            if int(board[y][x]) in allowed and int(special[y][x]) == 0]


def get_slot_prioritize(cells, model, amount: int, prioritize=None, ignore=None):
    """BoardModel::GetSlotPrioritize 0x5972158, as ChoosePositions calls it.

    Signature in the game: ``(RandomWrapper random, int amount, Func<int,int,bool>
    prioritize, Func<int,int,bool> ignore)``. It has two passes over the board
    slots:

    * pass 1 keeps the cells where ``prioritize(x, y)`` is true, in board order;
    * pass 2 (``!ignore(x, y)``) is only built when pass 1 is shorter than
      ``amount``; those cells are then **added in board order** and the rest is
      filled from the shuffled pass-2 list, popped from the front
      (0x5972338 shuffle, 0x5972394 the pop loop).

    So the shuffle always runs, but on the list the amount is filled from: when
    pass 1 already has ``amount`` cells it is pass 1 that is shuffled (its board
    order does not survive), otherwise the drawn cells are the shuffled pass 2
    and pass 1 keeps its order. The shuffle costs one draw per cell of that list
    (measured: 40 of 40 on research 20261120_111530, activation 002, N = 40).

    MonkeyJoojoo's own delegates (``_c_ChoosePositions_b__13_1/_5/_7/_9``) all
    compile to ``mov w0, wzr; ret`` -- constant false -- so at present pass 1 is
    always empty and every cell comes from pass 2: this is the plain
    ``shuffled(cells)[:amount]`` the port already did. The shape is kept because
    the predicates are the open question (docs/booster_logic_from_code.md).
    """
    if amount < 1:
        return []
    first = [cell for cell in cells if prioritize(cell)] if prioritize else []
    if len(first) >= amount:
        return model.rng.shuffled(first)[:amount]
    second = [cell for cell in cells if not ignore(cell)] if ignore else list(cells)
    pooled = model.rng.shuffled(second)
    drawn = list(first)
    while pooled and len(drawn) < amount:
        drawn.append(pooled.pop(0))
    return drawn


def draw_candidates(board, special, model, config, count: int, params=None) -> list[list[tuple[int, int]]]:
    """maxTries ChoosePositions(logic, false): one GetSlotPrioritize call per try."""
    if count < 1:
        return []
    cells = plain_cells(board, special, model.profile)
    return [get_slot_prioritize(cells, model, count)
            for _ in range(max(1, int(config["maxTries"])))]


def explode_cells(cells, board, special, config, rng) -> list[tuple[int, int]]:
    """ConvertToSpecialsAndAutoExplode b__0 (0x5f0af1c, build 5.900): the skulls destroyed now.

    The thrown cells are shuffled (ArrayExtensions.Shuffle on logic+0x168, the
    logic's RandomWrapper) and the first min(len, autoExplodeAmount) taken.
    When short, the other skulls on the board (BoardModel::Where, x-major) are
    shuffled the same way, the ones already taken removed, and the rest filled
    from the front.
    """
    amount = max(0, int(config["autoExplodeAmount"]))
    if amount < 1:
        return []
    taken = rng.shuffled(list(cells))[:amount]
    if len(taken) < amount:
        thrown = set(cells)
        skulls = [(y, x) for x in range(len(board[0])) for y in range(len(board))
                  if int(special[y][x]) in SKULL_VALUES or (y, x) in thrown]
        rest = [cell for cell in rng.shuffled(skulls) if cell not in taken]
        taken += rest[:amount - len(taken)]
    return taken


def _candidate_score(board, special, cells, model, config, mode, square) -> float:
    """The clone's settlement score: destroyed cells, the game's Player.Score proxy."""
    import copy

    import move_strategy as ms
    from strategy_lab.simulation import engine_refill

    clone = model.clone()
    board2 = [list(map(int, row)) for row in board]
    special2 = [list(map(int, row)) for row in special]
    for y, x in cells:
        special2[y][x] = SIM_SKULL
    destroy = explode_cells(cells, board2, special2, config, clone.rng)
    if not destroy:
        return 0.0
    candidate = ms.MoveCandidate(NO_SWAP, NO_SWAP, ms.Direction.RIGHT,
                                 board2, copy.deepcopy(special2))
    try:
        with engine_refill(clone):
            result = ms._simulate_booster_effect_cells(
                board2, special2, candidate, set(destroy),
                allow_square_matches=bool(square), mode=mode)
    except Exception:
        return 0.0
    return float(getattr(result, "cleared_cells", 0.0) or 0.0)


def activate(board, special, model, params=None, activations: int = 1, mode: str = "None",
             square: bool = False, candidate_index: int | None = None):
    """Use: (skull cells to destroy now, every chosen skull cell, this throw's count).

    ``candidate_index`` picks one of the maxTries candidates instead of the
    score-selected one; tools/monkey_check.py uses it to see whether the
    placement came out right when the pick rule is the only doubt.
    """
    config = config_from(model.profile, params)
    count = skull_pick(config, activations)
    tries = draw_candidates(board, special, model, config, count, params)
    if not tries:
        return [], [], 0
    if candidate_index is not None:
        chosen = max(0, min(int(candidate_index), len(tries) - 1))
    else:
        scores = [_candidate_score(board, special, cells, model, config, mode, square) for cells in tries]
        target = float(config["scoreTarget"])
        chosen = min(range(len(tries)), key=lambda i: (abs(scores[i] - target), i))
        activate.last_scores = scores
    cells = list(tries[chosen])
    return explode_cells(cells, board, special, config, model.rng), cells, count


def place_skulls(board, special, cells):
    """ConvertToSpecials: the chosen cells become skulls (sim 19), no draw."""
    board = [list(map(int, row)) for row in board]
    special = [list(map(int, row)) for row in special]
    for y, x in cells:
        special[y][x] = SIM_SKULL
    return board, special
