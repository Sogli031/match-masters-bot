"""Brocco Boogie (booster 44) activation, game 5.817.

Port of Match3Engine.BroccoBoogie.Use 0x5a16cb8 -> CreatingDiscoBalls
0x5a17748 -> ChoosePositions 0x5a17944 -> ConvertToSpecials 0x5a187bc.
Listings in Debug/reverse/simulator_all. Points are (x, y) = (column, row)
as in the engine; the boards are the simulator's [row][column].

Use (scoreTarget < 0, the Solo params):

* allowedColors = [3, 6, 7, 5] (engine colours), plus the current player's
  energy colour when Chance(chanceToAllowBlueAsTargetPosition) hits (one
  draw, always);
* per allowed colour the game destroys it on a GameLogic clone (its own RNG)
  and keeps the points; with scoreTarget < 0 they are never read;
* GetSlotPrioritize(NumOfPiecesToDestroy) with an always-false priority and
  ignore = IsSpecial or value 16: the x-major Where list of plain pieces,
  shuffled (one draw each), first n; destroyed as one ComboModel (type 10).

CreatingDiscoBalls after the settle: piecesPerActivation[min(ActivatesThisTurn
- 1, n - 1)] (at least 1) balls at ChoosePositions:

* colour weights: every cell (x outer, y inner) whose colour is allowed adds
  colorScoreOverride[colour] (1 without it);
* Chance(chanceToNeighborBlue) -> allowBlue;
* candidates, x-major: plain pieces (value 0) of an allowed colour; score =
  the highest weight among the four neighbours' colours, touchesBlue = a
  neighbour matches the energy colour, corner = one of the four corners;
* the candidates are shuffled (one draw each); each ball takes the first of:
  score >= 1 and (allowBlue or not touchesBlue) and not corner; the same
  without the corner rule; score > 0; the first candidate.

ConvertToSpecials converts them to BroccoBoogiePiece (28) with no draw;
removePreviousPieces is false in every recorded config.
"""
from __future__ import annotations

SIM_DISCO = 16          # move_strategy.SPECIAL_DISCO_BALL
DISCO_BOARD = 99
BASE_ALLOWED = (3, 6, 7, 5)
DEFAULT_CONFIG = {"NumOfPiecesToDestroy": 6, "piecesPerActivation": [2], "chanceToNeighborBlue": 12,
                  "chanceToAllowBlueAsTargetPosition": 0, "scoreTarget": -1, "removePreviousPieces": False}
ABILITY_CLASS = "Match3Engine.BroccoBoogie"
DIRECTIONS = ((0, 1), (1, 0), (0, -1), (-1, 0))
# Use's ignore (b__3) is IsSpecial or BoardSpecial (16); IsSpecial is false for
# the other board specials (IsBoardSpecial 15-21), so a mushroom (simulator 17)
# can be destroyed: Multiplier Mushrooms research 20261113_150011 004->005,
# three mushrooms, three draws more. shortcut: crystals, Zany Zappers and chests
# are left out (not recorded with Brocco); add them when a recording shows them.
DESTROYABLE_SPECIALS = frozenset((0, 17))


class UnsupportedBrocco(ValueError):
    pass


def _ints(text):
    return [int(part) for part in str(text).replace("|", ",").split(",") if part.strip()]


def config_from(profile, params=None) -> dict:
    """The ability's memory fields (profile.ability_detail), else the player's
    special_ability_params (strings), else the Solo defaults."""
    config = dict(DEFAULT_CONFIG)
    detail = (profile or {}).get("ability_detail") or {}
    fields = detail.get("fields") if detail.get("class") == ABILITY_CLASS else None
    params = params if isinstance(params, dict) else {}
    if params.get("numOfPiecesToDestroy") is not None:
        config["NumOfPiecesToDestroy"] = int(params["numOfPiecesToDestroy"])
    if params.get("piecesPerActivation") is not None:
        config["piecesPerActivation"] = _ints(params["piecesPerActivation"])
    for key in ("chanceToNeighborBlue", "chanceToAllowBlueAsTargetPosition", "scoreTarget"):
        if params.get(key) is not None:
            config[key] = int(params[key])
    if params.get("removePreviousPieces") is not None:
        config["removePreviousPieces"] = str(params["removePreviousPieces"]).lower() == "true"
    for key in ("NumOfPiecesToDestroy", "piecesPerActivation", "chanceToNeighborBlue",
                "chanceToAllowBlueAsTargetPosition", "removePreviousPieces"):
        if fields and fields.get(key) is not None:
            config[key] = fields[key]
    return config


def _energy_color(profile):
    return next(int((p.get("model") or {}).get("slotType")) for p in profile.get("players") or ()
                if p.get("player_type") == 0)


def destroy_cells(board, special, model, params=None):
    """Use up to the destroy: (row, col) cells and the allowed engine colours.

    Draws Chance(chanceToAllowBlueAsTargetPosition) and the shuffle on model.rng.
    """
    config = config_from(model.profile, params)
    if int(config["scoreTarget"]) >= 0:
        raise UnsupportedBrocco("Brocco Boogie: scoreTarget >= 0 (score-picked colour) is not ported")
    if config["removePreviousPieces"]:
        raise UnsupportedBrocco("Brocco Boogie: removePreviousPieces is not ported")
    allowed = list(BASE_ALLOWED)
    if model.rng.chance(int(config["chanceToAllowBlueAsTargetPosition"])):
        allowed.append(_energy_color(model.profile))
    rows, cols = len(board), len(board[0])
    plain = [(y, x) for x in range(cols) for y in range(rows)
             if 1 <= int(board[y][x]) <= 6 and int(special[y][x]) in DESTROYABLE_SPECIALS]
    # Use: an empty allowed set means EndMove with no destroy (not recorded).
    from engine_refill import color_maps
    sim_to_engine = color_maps(model.profile)[0]
    if not any(sim_to_engine.get(int(board[y][x])) in allowed for y, x in plain):
        raise UnsupportedBrocco("Brocco Boogie: no piece of an allowed colour")
    count = int(config["NumOfPiecesToDestroy"])
    if count < 1:
        return [], allowed
    return model.rng.shuffled(plain)[:count], allowed


def choose_positions(board, special, rng, amount, allowed, energy, chance_blue, sim_to_engine,
                     score_override=None, ball_colors=None):
    """ChoosePositions: up to ``amount`` (x, y) for the new balls.

    ``ball_colors``: {(row, col): engine colour} of the balls on the board;
    the slot keeps that colour under the ball and the game reads it.
    """
    rows, cols = len(board), len(board[0])
    override = score_override or {}
    balls = ball_colors or {}

    def color(x, y):
        if int(special[y][x]) == SIM_DISCO:
            return balls.get((y, x))
        return sim_to_engine.get(int(board[y][x]))

    def matches_energy(x, y):
        # SlotModel.MatchesWithColor: a two-colour piece matches its second colour too.
        if color(x, y) == energy:
            return True
        import move_strategy as ms
        return any(sim_to_engine.get(c) == energy for c in ms._special_match_colors(int(special[y][x])))

    weights = {}
    for x in range(cols):
        for y in range(rows):
            c = color(x, y)
            if c in allowed:
                weights[c] = weights.get(c, 0) + int(override.get(c, 1))
    allow_blue = rng.chance(int(chance_blue))
    candidates = []
    for x in range(cols):
        for y in range(rows):
            if color(x, y) not in allowed or int(special[y][x]) != 0:
                continue
            best, blue = 0, False
            for dx, dy in DIRECTIONS:
                nx, ny = x + dx, y + dy
                if not (0 <= nx < cols and 0 <= ny < rows):
                    continue
                c = color(nx, ny)
                if c in weights and best < weights[c]:
                    best = weights[c]
                blue = blue or matches_energy(nx, ny)
            corner = x in (0, cols - 1) and y in (0, rows - 1)
            candidates.append(((x, y), best, blue, corner))
    order = rng.shuffled(candidates)
    rules = (lambda c: c[1] >= 1 and (allow_blue or not c[2]) and not c[3],
             lambda c: c[1] >= 1 and (allow_blue or not c[2]),
             lambda c: c[1] > 0)
    result = []
    while amount > 0 and order:
        pick = next((c for rule in rules for c in order if rule(c)), order[0])
        result.append(pick[0])
        order.remove(pick)
        amount -= 1
    return result


def place_discos(board, special, model, activations, allowed, params=None):
    """CreatingDiscoBalls on the settled board: (board, special, cells (row, col));
    the balls' colours join the refill's ball slots."""
    import board_source
    from engine_refill import color_maps, decode_dictionary

    config = config_from(model.profile, params)
    per = list(config["piecesPerActivation"] or [0])
    amount = max(1, int(per[max(0, min(activations - 1, len(per) - 1))]))
    sim_to_engine = color_maps(model.profile)[0]
    raw = decode_dictionary((model.profile.get("rules") or {}).get("_colorScoreOverride")) or {}
    # Override keys are SlotColor names or numbers; slot_color_to_board gives the simulator colour.
    override = {}
    for key, value in raw.items():
        sim = board_source.slot_color_to_board(key)
        if sim in sim_to_engine:
            override[sim_to_engine[sim]] = int(value)
    cells = choose_positions(board, special, model.rng, amount, allowed, _energy_color(model.profile),
                             config["chanceToNeighborBlue"], sim_to_engine, override,
                             {(r, c): color for r, c, color in model.balls or ()})
    board = [list(map(int, row)) for row in board]
    special = [list(map(int, row)) for row in special]
    for x, y in cells:
        color = board[y][x]
        if model.balls is not None and color in sim_to_engine:
            model.balls.append((y, x, sim_to_engine[color]))
        board[y][x], special[y][x] = DISCO_BOARD, SIM_DISCO
    return board, special, [(y, x) for x, y in cells]
