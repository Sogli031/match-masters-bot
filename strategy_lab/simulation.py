"""Conservative deterministic-prefix adapter over existing Match Masters rules.

No sampled refill is invented. A transition ends at the first unknown refill;
it must not be resumed as though the empty cells were a valid whole game.
The one exception is a capture-backed ``engine_refill.SquareRefill`` model in
``move["engine_refill"]``: the ported RefillSlots then fills every cascade.
"""
from contextlib import ExitStack, contextmanager
from copy import deepcopy
from engine_knights import knight_count
import move_strategy as ms
from engine_refill import (CANDY_WORLD_BOARD, CRYSTAL_CAVE_BOARD, FIREWORKS_FESTIVAL_BOARD, JUNGLE_RUMBLE_BOARD,
                           fireworks_rocket_fired, is_dustville, joojoo_passive, joojoo_refill_ported,
                           joojoo_skull_count, rainbow_cascade_unported,
                           spray_five_unported)

PREFIX_MODES = {ms.GameMode.NONE.value, ms.GameMode.COLOR_CRUSH.value,
                ms.GameMode.VERTICAL_RUSH.value, ms.GameMode.BLOW_EM_UP.value,
                ms.GameMode.LIGHTNING_STRIKE.value, ms.GameMode.SHARED_ENERGY.value,
                # Multiplier Mushrooms (board 29), 2026-11-16: 144 of 150 recorded
                # moves give the game's board and RNG (Debug/research, six runs);
                # the multiplier 123 of 123, the score 108 of 123 (0.9% off in
                # all, disco-ball moves and a three with the mushroom in it).
                ms.GameMode.MULTIPLIER_MUSHROOMS.value,
                # Crazy Columns (board 19), research 20261118_215913 (Foxy Roxy
                # SE): board, RNG and moves 24 of 24 checkable moves (the other
                # 5 lost the board between two inputs), score 19 of 24 with the
                # x(column + 1) ramp; the 5 are sprays, at most 16 points short.
                ms.GameMode.CRAZY_COLUMNS.value,
                # Column Mania (board 32), research 20261119_080712 (Brocco
                # Boogie): the multipliers off the live log, see step_move.
                ms.GameMode.COLUMN_MANIA.value,
                # 2026-11-16, Debug/research replayed (tools/analyze_research.py)
                # plus the score against the recorded one:
                # Candy World, four runs: board 99 of 100, score 98 of 99.
                # Special O'Rama, one run: board 20 of 22, score 20 of 20.
                ms.GameMode.CANDY_WORLD.value, ms.GameMode.SPECIAL_O_RAMA.value,
                # Color Climb, eight runs: board 58 of 60, score 57 of 58 with
                # the dealt pair's multiplier (_multiplier_score); step()
                # refuses it while the pair is not read.
                ms.GameMode.COLOR_CLIMB.value,
                # Gem Grab (crystal-cave, board 3), research 20261117_112217:
                # board 24 of 24 with the Energy Boost knight rule
                # (engine_knights.any_colour_charges), score 16 of 16 with the
                # crystals' values.
                ms.GameMode.PURPLE_GEM.value,
                # The Floor Is Lava, research 20261117_114312: board 23 of 23,
                # moves and score 17 of 17 with the Solo flags (_solo_targets).
                ms.GameMode.FLOOR_IS_LAVA.value,
                # Lights Up (board 37), research 20261117_125632: board, RNG,
                # lit column, multiplier and score 32 of 32 (swipes, Charles,
                # Teleport, Energy Boost); step() refuses it while the column
                # is not read.
                ms.GameMode.LIGHTS_UP.value,
                # Funky Tiles, research 20261118_110443 (Froggy Fu): board, RNG,
                # moves and score 49 of 49 (34 swaps, 15 activations: the
                # entrance skips the funky cells, the markers skip a lotus);
                # step() refuses it while the funky cells are not read.
                ms.GameMode.FUNKY_TILES.value}


def plan_refusal(move):
    """Why the exact planner must not plan this state although step() can
    replay it (refill checks still may), or None.

    Mighty Mushrooms (board 30) is planned like Multiplier Mushrooms: research
    20261119_120931 (Foxy Roxy SE, Showdown) replays 6 of 6. Color Climb scores right only with our
    dealt pair read."""
    model = move.get("engine_refill")
    board = model.profile["rules"].get("boardModelName") if model is not None else None
    if move.get("mode") == ms.GameMode.FLOOR_IS_LAVA.value and move.get("floor_lava_columns") is None:
        return "Floor Is Lava: stanje kolona nije procitano"
    if move.get("mode") == ms.GameMode.PURPLE_GEM.value and board != CRYSTAL_CAVE_BOARD:
        return "Purple Gem van Gem Grab table jos nije proveren"
    if move.get("mode") == ms.GameMode.COLUMN_MANIA.value and not move.get("column_multipliers"):
        return "Column Mania: mnozioci kolona nisu procitani"
    if move.get("mode") == ms.GameMode.LIGHTS_UP.value and (
            move.get("lights_up_column") is None or move.get("score_multiplier") is None):
        return "Lights Up: osvetljena kolona nije procitana"
    if move.get("mode") == ms.GameMode.FUNKY_TILES.value and move.get("funky_cells") is None:
        return "Funky Tiles: funky polja nisu procitana"
    if move.get("mode") == ms.GameMode.COLOR_CLIMB.value and (
            not move.get("multiplier_colors") or move.get("score_multiplier") is None):
        return "Color Climb: par boja nije procitan"
    return None


ORDINARY_SPECIALS = {0, ms.SPECIAL_HORIZONTAL, ms.SPECIAL_VERTICAL, ms.SPECIAL_BOMB}
# A resting crosshair or lightning is inert; only its activation picks random
# targets, and step() rejects any transition in which one fires.
RESTING_SPECIALS = ORDINARY_SPECIALS | {ms.SPECIAL_CROSSHAIR, ms.SPECIAL_LIGHTNING, ms.SPECIAL_HEART,
                                        ms.SPECIAL_SWEEP_SE_BROOM,
                                        ms.SPECIAL_FROGGY_LOTUS, ms.SPECIAL_COLOR_CRYSTAL,
                                        ms.SPECIAL_DISCO_BALL, ms.SPECIAL_MUSHROOM, ms.SPECIAL_CLEO_BUG}
RANDOM_TARGET_SPECIALS = {"crosshair", "lightning", "all_aboard_bandit", "cleo_bug", "spray_se", "joojoo_skull"}
# Match & Hatch's random specials: known at rest, their activation is not ported.
HATCHED_SPECIALS = (ms.SPECIAL_ALL_ABOARD_BANDIT, ms.SPECIAL_JOOJOO_SKULL, ms.SPECIAL_SPRAY_SE, ms.SPECIAL_CLEO_BUG)
# Foxy Roxy SE: a resting spray can only falls. Its swipe paints a straight
# ray (2026-11-09 Column Mania, swipes 006/007/014 exact); a ray that makes a
# five is not (spray_five_unported).
SPRAY_EXACT_PORTED = True


@contextmanager
def rules(move):
    mode=move["mode"]
    with ExitStack() as stack:
        stack.enter_context(ms.color_crush_active(mode == ms.GameMode.COLOR_CRUSH.value or bool(move.get("color_crush")),
                              single_player=move.get("single_player_board",(move.get("strategy_context") or {}).get("mode") == "solo_6")))
        stack.enter_context(ms.all_specials_lightning_active(mode == ms.GameMode.LIGHTNING_STRIKE.value or bool(move.get("all_specials_lightning"))))
        stack.enter_context(ms.both_colors_charge_energy_active(mode == ms.GameMode.SHARED_ENERGY.value))
        mania = mode == ms.GameMode.COLUMN_MANIA.value and bool(move.get("column_multipliers"))
        stack.enter_context(ms.crazy_columns_score_active(mode == ms.GameMode.CRAZY_COLUMNS.value or mania))
        if mania:
            stack.enter_context(ms.column_mania_state(move["column_multipliers"]))
        stack.enter_context(ms.charge_colors_active(move.get("energized_colors") or (),move.get("engine_charge_colors")))
        stack.enter_context(ms.vertical_matches_destroy_color_active(bool(move.get("vertical_matches_destroy_color"))))
        stack.enter_context(ms.matches_destroy_color_active(bool(move.get("matches_destroy_color"))))
        stack.enter_context(ms.every_match_is_special_active(bool(move.get("every_match_is_special"))))
        # Funky Tiles cells read from the recording (simulator_capture.lab_move).
        if move.get("funky_cells") is not None:
            stack.enter_context(ms.funky_tile_cells(move["funky_cells"]))
        if move.get("floor_lava_columns") is not None:
            stack.enter_context(ms.floor_lava_checked_columns(move["floor_lava_columns"]))
        if ms.JELLY_EXACT_PORTED:
            stack.enter_context(ms.jelly_zone_cells(move.get("jelly_zone_cells") or ()))
        stack.enter_context(ms.line_destruction_active(*(move.get("line_destruction") or (False,False))))
        if move.get("ability_temp_special_cells"):
            stack.enter_context(ms.ability_temp_specials_active(
                move["board"], move["special_board"], move["ability_temp_special_cells"]))
        gather = ms.froggy_gather_config_from_params(move.get("froggy_params"))
        if gather is not None:
            stack.enter_context(ms.froggy_gather_region_active(*gather))
        yield


def legal_actions(move):
    """The same full native swap enumeration for offline and live supported states.

    It includes legal special activations and combinations. Legality comes
    from the simulated match/effect, never from a positive heuristic score.
    """
    from .policy import native_action
    with rules(move):
        native=[]
        seen=set()
        for candidate in ms.generate_candidates(move["board"],move["special_board"]):
            for oriented in (candidate,ms.flip_swap_candidate(candidate)):
                key=(oriented.start,oriented.target,oriented.direction)
                if key in seen:continue
                seen.add(key)
                result=simulate(move,oriented)
                if result is None or not (result.matches or result.activated_specials or result.cleared_cells):continue
                native.append(ms.evaluate_simulation(result,move["mode"],
                              allow_square_matches=bool(move.get("allow_square_matches")),include_future_value=False))
        return native,[native_action(e) for e in native]


def simulate(move,candidate):
    # This primitive dispatches special+special combos and filters stale matches;
    # simulate_candidate alone only resolves the ordinary-match branch.
    return ms._simulate_created_candidate(move["board"],candidate,mode=move["mode"],
                allow_square_matches=bool(move.get("allow_square_matches")),include_future_value=False,
                explode_created_specials_immediately=bool(move.get("specials_explode_immediately")) or move["mode"]==ms.GameMode.BLOW_EM_UP.value)


@contextmanager
def engine_refill(model):
    """Ported RefillSlots for one action; yields the per-refill hole traces."""
    if model is None:
        yield None
        return
    from engine_refill import simulator_refill
    # PerformSwap resets ChainComboReduction, which clears spawnedColors.
    model.reset_action()
    traces = []
    from engine_cleo_simulation import simulate_swipe
    with ms.engine_refill_active(simulator_refill(model, traces), model.peek_draws, model.ball_spent,
                                 model.random_special,
                                 lambda candidate, **kwargs: simulate_swipe(model, candidate, **kwargs),
                                 model.wanted_shots if is_dustville(model) else None,
                                 model.fireworks_targets):
        yield traces


# DoctorColor.get_ColorPaths order (docs/doctor_color.md): first colour ->
# second, then both -> third. Red and Blue are never recoloured.
DOCTOR_COLOR_PATHS = tuple(tuple(getattr(ms, c) for c in path) for path in (
    ("ORANGE", "GREEN", "YELLOW"), ("ORANGE", "YELLOW", "GREEN"),
    ("ORANGE", "PURPLE", "YELLOW"), ("ORANGE", "YELLOW", "PURPLE"),
    ("GREEN", "YELLOW", "PURPLE"), ("GREEN", "ORANGE", "PURPLE"),
    ("GREEN", "PURPLE", "YELLOW"), ("GREEN", "YELLOW", "ORANGE"),
    ("PURPLE", "ORANGE", "YELLOW"), ("PURPLE", "YELLOW", "ORANGE"),
    ("PURPLE", "GREEN", "YELLOW"), ("PURPLE", "ORANGE", "GREEN"),
    ("YELLOW", "ORANGE", "PURPLE"), ("YELLOW", "PURPLE", "GREEN"),
))
DOCTOR_COLOR_PATHS_MAX = 3  # colorPathsMaxAmount


def doctor_color_pick(board, model):
    """DoctorColor.Use 0x5a38878, consuming the action's engine draws.

    AvailableColorPaths (all three colours on the board) are shuffled with the
    game RNG (one Next per path, stable OrderBy) and the first three kept.
    pickBehavior's Chance and the pick itself each use a *fresh*
    RandomWrapper(seed of the game RNG), so the pick is the first Next of
    that seed modulo the candidate count -- the same index every activation.
    pickHighest/LowestChance are -1 in the captured config, so the scored
    clone simulations never decide; they run on GameLogic clones.
    """
    from engine_rng import EngineRNG

    colors = {int(v) for row in board for v in row}
    paths = [p for p in DOCTOR_COLOR_PATHS if set(p) <= colors]
    if not paths:
        return None
    paths = model.rng.shuffled(paths)[:DOCTOR_COLOR_PATHS_MAX]
    return paths[EngineRNG.from_seed(model.rng.seed).range(0, len(paths))]


def doctor_color_convert(board, special, path):
    """MakeColorSwaps: every piece of path[0] becomes path[1], then all of
    path[1] become path[2]; special types are kept, BoardSpecial excluded."""
    board = [list(map(int, row)) for row in board]
    for source, target in zip(path, path[1:]):
        for r, row in enumerate(board):
            for c, color in enumerate(row):
                if color == source and special[r][c] != ms.SPECIAL_MODE_TARGET:
                    row[c] = target
    return board


WOOLLY_WORKOUT = 35
CHECKMATE_CHARLES = 54
FOXY_ROXY_SE = 52
FROGGY_FU = 63
BROCCO_BOOGIE = 44
SWEEP_IT_SE = 61


def charles_explosion_cells(board, rng):
    """CheckmateCharles.ChoosePositionsForActivateExplosion 0x5a1a488.

    Chance(50): a whole row at Range(0, Rows-1) (GetRow), else a whole column
    at Range(0, Columns-1) (GetColumn) -- Range's upper bound is exclusive, so
    the last row and column are never drawn. Then Chance(50): the diagonal from
    the top-left corner going (+1, +1), else from the top-right corner going
    (-1, +1) (GetAreaOfEffectForDirections). (row, col) cells, line first.
    """
    rows, columns = len(board), len(board[0])
    if rng.chance(50):
        y = rng.range(0, rows - 1)
        line = [(y, x) for x in range(columns)]
    else:
        x = rng.range(0, columns - 1)
        line = [(y, x) for y in range(rows)]
    if rng.chance(50):
        diagonal = [(i, i) for i in range(min(rows, columns))]
    else:
        diagonal = [(i, columns - 1 - i) for i in range(min(rows, columns))]
    cells = [cell for cell in dict.fromkeys(line + diagonal) if ms._is_board_piece(board[cell[0]][cell[1]])]
    return cells


def charles_knights_back_to_normal(model, board, special, square=False):
    """removePreviousPieces: SpecialAbilityWithBoosterPieces.Remove 0x5a8f0e0, in Use.

    Each knight on the board (Where, x-major) goes through
    GameLogic.CreateBoosterPieceBackToNormalConversion 0x595dd78: the colours
    are its own first, then GetAllColorsExcept(own) in gameColors order,
    shuffled (EngineRNG.shuffled, one draw each); colour2 (1 for a knight, not a
    game colour) would add a Chance(50). The first colour that makes no combo
    through that cell (GetAllCombos over it, the board as converted so far) is
    kept, a plain piece. Traced Square Match 20261114_232927 005->006: three
    knights, 15 draws inside Use before the blast.
    """
    from engine_refill import color_maps

    knights = [(r, c) for c in range(len(board[0])) for r in range(len(board))
               if int(special[r][c]) == ms.SPECIAL_KNIGHT]
    if not knights:
        return
    sim_to_engine, engine_to_sim = color_maps(model.profile)
    game_colors = [int(c) for c in (model.profile.get("spawning") or {}).get("gameColors") or []]
    for r, c in knights:
        own = int(board[r][c])
        own_engine = sim_to_engine.get(own)
        others = [engine_to_sim[e] for e in game_colors if e != own_engine and e in engine_to_sim]
        order = [own] + model.rng.shuffled(others)
        special[r][c] = ms.EMPTY
        for color in order:
            board[r][c] = color
            if not any((r, c) in match.cells for match in ms.find_matches(board, square, special)):
                break


def charles_activate(model, board, special, square=False):
    """CheckmateCharles.Use 0x5a1a250 inside the action's refill context.

    Use clears CurrentChessMoves and piecesActivatedTimesThisUse, sets the
    passive ability (the knights come back at the end of the move), and the
    explosion fills CurrentChessMoves, so a knight the blast hits adds no
    jump (engine_knights.knight_area). Recorded counters after an activation:
    both 0 (Super Sized research 20261114_172725 005, 009).
    """
    from engine_knights import DEFAULT_CONFIG, KnightState

    if model.knights is None:
        model.knights = KnightState(DEFAULT_CONFIG["knightMovesOnPieceActivation"],
                                    DEFAULT_CONFIG["knightMoveFavorSpecialChanceByActivation"],
                                    DEFAULT_CONFIG["knightMoveFavorBlueChanceByActivation"], 0, 0)
    model.knights.uses = 0
    model.knights.activations = 0
    model.knights.booster_activations += 1     # Ability.Use: ActivatesThisTurn
    charles_knights_back_to_normal(model, board, special, square)
    cells = charles_explosion_cells(board, model.rng)
    model.knights.moved_this_action = True
    return cells


def woolly_workout_convert(board, special, color, model):
    """WoollyWorkout.Use 0x5ada438, consuming its engine draws.

    Sources: every piece matching the tapped one (Where b__0, MatchesWithSlot),
    trimmed at random only above piecesAmount (99, never on a 7x7 board).
    Chance(chanceForAllDirections) always draws once; at 100 both axes run,
    otherwise Chance(50) (a second draw) picks horizontal or vertical. Each
    source colours its one neighbour per direction unless that cell is a
    source, a BoardSpecial (crystal, mushroom) or already coloured. Converted
    slots keep their special type and take the tapped piece's colour; then
    GetAllCombos -> DestroyMatches (the caller's cascade).
    """
    sources = {(r, c) for r, row in enumerate(board) for c, v in enumerate(row) if int(v) == color}
    if not sources:
        return None
    params = ((getattr(model, "profile", None) or {}).get("players") or [{}])
    chance_all = 100
    for player in params:
        value = ((player.get("model") or {}).get("specialAbilityParams") or {})
        if isinstance(value, dict) and value.get("chanceForAllDirections") is not None:
            chance_all = int(value["chanceForAllDirections"])
    if model.rng.chance(chance_all):
        directions = ((0, -1), (0, 1), (-1, 0), (1, 0))
    elif model.rng.chance(50):
        directions = ((0, -1), (0, 1))
    else:
        directions = ((-1, 0), (1, 0))
    converted = [list(map(int, row)) for row in board]
    colored = []
    size = len(board)
    # orderedDirections 16, 4, 2, 8: left, right, up, down; sources x-major
    # (traced research 20261114_224536 002, sourceCellToColored).
    for dr, dc in directions:
        for r, c in sorted(sources, key=lambda cell: (cell[1], cell[0])):
            nr, nc = r + dr, c + dc
            if not (0 <= nr < size and 0 <= nc < size) or (nr, nc) in sources or (nr, nc) in colored:
                continue
            if special[nr][nc] in ms.WOOLLY_WORKOUT_COLOR_PRESERVING_SPECIALS or not ms._is_board_piece(board[nr][nc]):
                continue
            colored.append((nr, nc))
            converted[nr][nc] = color
    woolly_workout_convert.last_order = tuple(colored)
    return converted


woolly_workout_convert.last_order = ()


def woolly_exact_simulation(model):
    """A move_strategy.woolly_exact_active simulator over this engine model.

    Each colour runs on its own clone of ``model`` (the live RNG): the recolour
    with its Chance draw, then GetAllCombos -> DestroyMatches and the cascades
    on the ported refill, specials on each combo's first recoloured cell
    (6 of 6 recorded activations exact, 2026-11-14). The tapped cell must be
    a plain piece (CanBeTarget); a colour with none is not a target.
    """
    from engine_refill import UnsupportedRefill

    def simulate_colour(board, special, color, allow_square_matches, mode, explode):
        board = [list(map(int, row)) for row in board]
        special = [list(map(int, row)) for row in special]
        plain = [(r, c) for r, row in enumerate(board) for c, v in enumerate(row)
                 if v == color and special[r][c] == ms.EMPTY]
        center = (len(board) - 1) / 2
        target = min(plain, key=lambda cell: ((cell[0] - center) ** 2 + (cell[1] - center) ** 2, cell),
                     default=None)
        if target is None or color not in ms.WOOLLY_WORKOUT_TARGET_COLORS:
            return None
        clone = model.clone()
        converted = woolly_workout_convert(board, special, color, clone)
        if converted is None:
            return None
        order = woolly_workout_convert.last_order
        candidate = ms.MoveCandidate(NO_SWAP_CELL, NO_SWAP_CELL, ms.Direction.RIGHT, converted, deepcopy(special))
        try:
            with engine_refill(clone), ms.booster_converted_order(order):
                result = ms.simulate_candidate(candidate, allow_square_matches=allow_square_matches,
                                               mode=mode, explode_created_specials_immediately=explode)
        except UnsupportedRefill:
            return None     # the approximate model stays
        result.candidate = ms.MoveCandidate(target, target, ms.Direction.RIGHT, converted, special)
        result.exact_refill_supported = True
        result.intent_events.insert(0, {"type": "woolly_workout_conversion", "target_color": int(color),
                                        "converted_cells": [list(cell) for cell in order], "exact": True})
        return result, len(order)

    return simulate_colour


# Board abilities by engine type (PlayerModel.boardAbilities keys).
PERK_ENERGY_BOOST, PERK_TELEPORT = 22, 3
DOCTOR_COLOR = 27
NO_SWAP_CELL = (-1, -1)


JOOJOO_SKULL_ENGINE = 24
ZANY_ZAPPER_ENGINE = 17


def _refill_spawns(model, engine_value) -> bool:
    """Whether this match's refill spawns ``engine_value`` as a special tile."""
    from engine_refill import decode_dictionary
    data = decode_dictionary((getattr(model, "profile", None) or {}).get("spawning", {}).get("specialTilesData")) or {}
    return any(int(key) == engine_value for key in data)


def _dustville_cascade_unported(event) -> bool:
    """A special or a wanted volley past the swipe's own cascade: timing unknown.

    Recorded: 016/028 (cascade rocket) and live misses 2026-11-07 09:08:20 and
    09:08:51 (a figure matched in cascade 2: RNG -24 and +43 against the game).
    """
    return (event.get("type") in ("special_activation", "dustville_wanted_shots")
            and event.get("cascade", 0) > 1)


def _knights_return(model, move, kind, charles_fired, result):
    """Checkmate Charles: EndMoveWithPassiveAbility tops the knights back up
    while GameLogic.moves >= 1 (engine_knights.knight_end_move)."""
    if model is None or getattr(model, "knights", None) is None:
        return False
    if not ((kind != "booster" and knight_count(move["special_board"]) > 0) or charles_fired):
        return False
    remaining = (move.get("turn_state") or {}).get("remaining_moves")
    # The booster spends no move: moves stays as it was (research
    # 20261114_230724 026/029 and 231455 031, one move left: the knights
    # came back; the swipe rule skipped them).
    spent = 0 if charles_fired else 1
    return remaining is None or remaining - spent >= 1 or result.extra_moves > 0


def _solo_goal(move):
    """The Solo flags in force for this state (solo_challenge.SoloGoalState), or None."""
    targets = [int(t) for t in move.get("solo_targets") or ()]
    if not targets or move.get("score") is None or not move.get("solo_flag_rules"):
        return None
    from solo_challenge import SoloGoalState

    rules = move["solo_flag_rules"]
    return SoloGoalState(targets=tuple(targets), score=int(move["score"]),
                         overflow=bool(rules.get("overflow", True)),
                         continue_after_last=bool(rules.get("continue_after_last")))


def _solo_targets(move, after, gain):
    """Solo Challenge flags (rules.soloTargets): the gain the game credits,
    and the moves it gives back. Off unless the rules say so.

    soloOverflowPastTarget false: a move stops at the flag it reaches
    (solo_challenge.SoloGoalState.credited_points). soloRefillMode: reaching
    a flag fills the moves back to movesPerTurn. The Floor Is Lava research
    20261117_114312 009->010: score 134 + 28 -> 150 (the 150 flag), moves 4 -> 6
    with a swipe and no extra; the carried plan was lost at every flag.
    """
    goal = _solo_goal(move)
    if goal is None:
        return gain
    targets = [int(t) for t in move["solo_targets"]]
    score, rules = int(move["score"]), move["solo_flag_rules"]
    credited = goal.credited_points(gain)
    # The last flag gives no moves back: Mutation Lab research 20261114_222505
    # 080->081, 5749 -> 5761 over the 5750 flag, moves 7 -> 6.
    reached = (goal.next_target is not None and goal.next_target != targets[-1]
               and score + credited >= goal.next_target)
    turn = after.get("turn_state") or {}
    if reached and rules.get("refill") and turn.get("max_moves"):
        turn["remaining_moves"] = int(turn["max_moves"])
        turn["owner_after"] = "us"
    return credited


def _vertical_rush_change(result) -> int:
    """VerticalRushBoard.AfterPerformedSwap, the swipe's own combos only (ms._vertical_rush_change)."""
    return ms._vertical_rush_change([
        ms.MatchGroup(frozenset(tuple(c) for c in event.get("cells") or ()), event.get("color"), event.get("kind"))
        for event in result.intent_events or ()
        if event.get("type") == "match" and int(event.get("cascade") or 0) == 1])


def _multiplier_score(move, result, values, after, perk=False, booster=False, can_points=0,
                      ability=False):
    # ``booster``: a Foxy Roxy SE activation raises no Color Climb multiplier
    # (research 20261117_155242: 7 of 7 activations, 2 -> 2 and 4 -> 4).
    # ``can_points``: the spray can itself, scored with the swipe's own
    # cascade (the same research: 8 of 8 sprays, the game's gain is the
    # simulator's plus that cascade's multiplier).
    """Multiplier Mushrooms (board 29): every collected mushroom raises
    PlayerModel.scoreMultiplier by one, and each cascade scores its pieces at
    the multiplier after its own mushrooms (research 20261116_183919: 008->009
    5 x 7 + 26 x 9 = 269, as the game). The new multiplier goes to ``after``."""
    multiplier = int(move["score_multiplier"])
    if move.get("rules_id") == "vertical-rush" and not ability:
        # Vertical Rush (board 23): moved before the move is paid, floor 1, and
        # not at all when a booster or perk was used this move (IsAbilityUsedThisMove).
        # Research 20261119_090048: 9->10 paid 5 x 10, 10->9 paid 16 x 9.
        multiplier = max(1, multiplier + _vertical_rush_change(result))
    pair = move.get("multiplier_colors")
    # A perk move raises nothing for the lit column (research 20261117_125632:
    # 001->002 Teleport and 002->003 Energy Boost, lit combos, multiplier +0).
    lit = None if perk else move.get("lights_up_column")
    raised = {}
    for event in result.intent_events or ():
        cascade = int(event.get("cascade") or 0)
        if pair is None and event.get("type") == "mushroom_collect":
            raised[cascade] = raised.get(cascade, 0) + len(event.get("multipliers") or ())
        elif (pair is not None and not booster and event.get("type") == "match" and event.get("kind") != "auto_explode"
              and int(event.get("tile_count") or 0) >= 3 and int(event.get("color", -1)) in pair):
            # Color Climb (board 35): RainbowMultiplierBoard.BeforeCombosDestroy
            # raises it by one per ordinary combo in our pair, before the pass
            # scores (docs/game_mode_rules.md "Color Climb").
            raised[cascade] = raised.get(cascade, 0) + 1
        elif (lit is not None and cascade == 1 and event.get("type") == "match"
              and event.get("kind") != "auto_explode" and int(event.get("tile_count") or 0) >= 3
              and any(int(cell[1]) == lit for cell in event.get("cells") or ())):
            # Lights Up (board 37): +1 per combo of the swipe itself that
            # touches the lit column; cascade combos there raise nothing
            # (research 20261117_125632: 016 had two lit cascade combos, +0).
            raised[cascade] = raised.get(cascade, 0) + 1
    cap = move.get("max_score_multiplier")
    gain = 0.0
    cascades = list(result.cascade_color_counts or ())
    if not cascades and result.cleared_color_counts:
        cascades = [(max(raised, default=0), result.cleared_color_counts)]
    seen = set()
    for cascade, counts in cascades:
        if cascade not in seen:
            multiplier += raised.get(cascade, 0)
            if cap:
                multiplier = min(multiplier, int(cap))
            seen.add(cascade)
        gain += multiplier * sum(n * values.get(int(c) % 1000, 1) for c, n in counts.items())
        if can_points and len(seen) == 1:
            gain += multiplier * can_points
            can_points = 0
    multiplier += sum(v for c, v in raised.items() if c not in seen)
    if cap:
        multiplier = min(multiplier, int(cap))
    after["score_multiplier"] = multiplier
    return gain


# The powerup Foxy Roxy SE (engine_foxy_powerup): Bombs Away research
# 20261118_091058 replays whole, 47 of 47 moves -- 15 activations (patterns
# and cans) and every L spray -- board, specials and RNG.
FOXY_POWERUP_BOOSTER_PORTED = True
FOXY_POWERUP_SPRAY_PORTED = True


def foxy_powerup(move):
    """The move's Foxy Roxy SE is the powerup variant (engine_foxy.is_powerup_variant)."""
    if move.get("booster_type") != FOXY_ROXY_SE:
        return False
    import engine_foxy
    model = move.get("engine_refill")
    return engine_foxy.is_powerup_variant(move.get("froggy_params"), getattr(model, "profile", None))


def _is_spray_swipe(move, action):
    """A Foxy Roxy SE spray can's swipe (it stays on its own cell)."""
    start, target = action.get("start"), action.get("target")
    if start is None or list(start) != list(target):
        return False
    r, c = start
    return int(move["special_board"][r][c]) == ms.SPECIAL_SPRAY_SE


def column_mania_after(move, result, action):
    """The column multipliers after a swipe: ColumnManiaBoard.onMoveEnd raises
    each column of the swipe's own combos by one, to maxMultiplier.

    Research 20261119_080712 (multipliers off the live log), 11 swipes of 11:
    the swipe's own matches only (every cascade's columns: 4 of 11), and a
    special swap without a match of its own (disco ball, two crosshairs) raises
    the columns of its two cells. A booster raises none (2 of 2).
    """
    if result.has_direct_match_layer:
        direct = ms._direct_swap_layer(result.cascade_matches, result.has_direct_match_layer, result.matches)
        raised = {int(col) for match in direct for _row, col in match.cells}
    else:
        raised = {int(action["start"][1]), int(action["target"][1])}
    cap = int(move.get("column_multiplier_max") or 99)
    return tuple(min(cap, value + 1) if col in raised else value
                 for col, value in enumerate(move["column_multipliers"]))


def _spray_can_points(move, action):
    """What the swiped spray can itself scores: 1 (Color Climb, 8 of 8 sprays),
    on Crazy Columns x (column + 1).

    shortcut: research 20261118_215913 sprays 012/019/023/029/008 were short
    by 0/3/4/8/16 points with it (2-19 before); neither the colour under the
    can nor its fall explains the rest. Upgrade from a spray's swap trace.
    """
    if move.get("mode") != ms.GameMode.CRAZY_COLUMNS.value:
        return 1
    return int(action["start"][1]) + 1


def _score_points(move, result):
    """Points of a settled result by the colour values (step's plain score gain)."""
    values = move.get("score_values") or {}
    return sum(n * values.get(int(c) % 1000, 1) for c, n in result.cleared_color_counts.items())


def _froggy_stamp_points(model, result, values):
    """Froggy Fu's lotus collection: StampScore 0x5a546c8 stamps the gathered
    cells when GetRainbowScore(colour) >= 1, and the game's score rose by
    each gathered cell's colour value once more. Bombs Away research
    20261118_103045: 13 of 13 collections (+18, +45, +40, +20, +36, +45 with
    the stamp; none for Blue and the colour worth 1, whose rainbow score is 0).
    """
    events = [e for e in result.intent_events or () if e.get("type") == ms.FROGGY_LOTUS_GATHER_EVENT]
    fields = (model.profile.get("froggy_booster_fields") or {}) if events else {}
    rainbow = fields.get("rainbowScoreByColor")
    if not events or not rainbow:
        return 0
    from engine_refill import color_maps
    from simulator_capture import decode_dictionary
    rainbow = decode_dictionary(rainbow) if "entries" in rainbow else rainbow
    rainbow = {int(k): int(v) for k, v in rainbow.items()}
    to_engine = color_maps(model.profile)[0]
    points = 0
    for event in events:
        color = event.get("color")
        if color is not None and rainbow.get(to_engine.get(int(color)), 0) >= 1:
            points += len(event.get("cells") or ()) * values.get(int(color), 1)
    return points


def froggy_activate(move, model, board, specials, activation):
    """Froggy Fu (booster 63) inside the action's refill context (engine_froggy_placement.activate).

    Each entrance attempt is destroyed and settled on a model clone under its
    own refill context; the winner settles on ``model`` in the action's one.
    Returns (result, lotus cells, events).
    """
    import engine_froggy_placement as froggy
    from engine_refill import color_maps

    square = bool(move.get("allow_square_matches"))

    def destroy(cells):
        candidate = ms.MoveCandidate(NO_SWAP_CELL, NO_SWAP_CELL, ms.Direction.RIGHT, board, specials)
        result = ms._simulate_booster_effect_cells(board, specials, candidate, set(cells),
                                                   allow_square_matches=square, mode=move["mode"])
        if result is None:
            raise froggy.UnsupportedPlacement("Froggy Fu: empty entrance")
        # The clone's PlayerControl.Score stops at the Solo flag like the
        # game's: research 20261118_103045 006->007 (263, the 300 flag), every
        # attempt scored 37, the distances tied and the first attempt won.
        points = _score_points(move, result)
        if move.get("score_multiplier") is not None:
            # Multiplier Mushrooms: the clone scores at the multiplier its own
            # mushrooms raise. Research 20261118_223923 001->002: every attempt
            # took both mushrooms; plain points picked attempt 2, the game
            # attempt 5 (its board, lotuses and RNG exact with this).
            points = _multiplier_score(move, result, move.get("score_values") or {}, {})
        goal = _solo_goal(move)
        return result, (goal.credited_points(points) if goal is not None else points)

    def settle(target, cells):
        if target is model:
            return destroy(cells)
        with engine_refill(target):
            return destroy(cells)

    energy = next((p.get("model") or {}).get("slotType") for p in model.profile.get("players") or ()
                  if p.get("player_type") == 0)
    sim_to_engine = color_maps(model.profile)[0]
    values = {color: (move.get("score_values") or {}).get(color, 1) for color in sim_to_engine}
    result, lotuses, _, events = froggy.activate(board, specials, model, activation, int(energy),
                                                 values, settle,
                                                 [tuple(c) for c in move.get("funky_cells") or ()])
    return result, lotuses, events


def sweep_activate(move, model, board, specials):
    """Sweep It SE (booster 61) MovePieces inside the action's refill context
    (engine_sweep): every colour combo is swept and settled on a model clone,
    the winner is swept and settled on ``model``. The sweep's ConvertSlots
    order (MakeSwaps) orders the combos; each special sits on its combo's
    first x-major cell (refill_misses 20261119_042300: a combo of three lines,
    the first moved cell put the Lightning in the wrong column).
    Returns (result, combo, evaluations)."""
    import engine_sweep

    square = bool(move.get("allow_square_matches"))

    def settle_swept(swept_board, swept_special, conversions):
        candidate = ms.MoveCandidate(NO_SWAP_CELL, NO_SWAP_CELL, ms.Direction.RIGHT, swept_board, swept_special)
        with ms.booster_converted_order(conversions, special_x_major=True):
            return ms.simulate_candidate(candidate, allow_square_matches=square, mode=move["mode"])

    def settle(clone, swept_board, swept_special, conversions):
        with engine_refill(clone):
            result = settle_swept(swept_board, swept_special, conversions)
        if result is None:
            return 0, swept_special
        points = _score_points(move, result)
        goal = _solo_goal(move)
        return (goal.credited_points(points) if goal is not None else points), result.special_board

    combo, evaluations, directions, sim_to_engine = engine_sweep.choose_combo(board, specials, model, settle)
    swept_board, swept_special, _, conversions = engine_sweep.sweep(board, specials, combo, directions,
                                                                    sim_to_engine)
    return settle_swept(swept_board, swept_special, conversions), combo, evaluations


def booster_energy_weight(model, activation):
    """The activation's energy-tile weight change (BoosterConfig
    energyTileWeightChangeOnActivation[SinglePlayer]): the player's colour
    weight in the refill is multiplied and truncated. Lightning Strike research
    20261119_031206 and 041029 (Sweep It SE): colorWeights[4] 1 -> 0 at the
    first activation; that activation's own refill already uses it (003->004
    replays only so). The profile is copied: clones and the capture keep theirs."""
    profile = model.profile
    config = (((profile.get("ability_detail") or {}).get("fields") or {}).get("<Config>k__BackingField") or {})
    solo = (profile.get("rules") or {}).get("pvpMode") == 1
    factors = config.get("energyTileWeightChangeOnActivationSinglePlayer" if solo
                         else "energyTileWeightChangeOnActivation")
    if not factors:
        return
    factor = float(factors[max(0, min(activation - 1, len(factors) - 1))])
    energy = next(((p.get("model") or {}).get("slotType") for p in profile.get("players") or ()
                   if p.get("player_type") == 0), None)
    spawning = profile.get("spawning") or {}
    entries = (spawning.get("colorWeights") or {}).get("entries")
    if energy is None or not entries or factor == 1.0:
        return
    entries = [dict(e, value=int(e["value"] * factor)) if e["key"] == energy else e for e in entries]
    model.profile = dict(profile, spawning=dict(spawning, colorWeights={"entries": entries}))


def _foxy_activations(move, model):
    """ActivatesThisTurn before this Use: the state's own count, else the
    recorded one (profile cleo_activates_this_turn, the same counter)."""
    if move.get("foxy_activations") is not None:
        return int(move["foxy_activations"])
    return int((getattr(model, "profile", None) or {}).get("cleo_activates_this_turn") or 0)


def _disco_on_plain(specials, action) -> bool:
    """A disco ball swiped with a plain piece (no special on the other cell)."""
    if action.get("start") is None or action.get("target") is None:
        return False
    values = [specials[r][c] for r, c in (action["start"], action["target"])]
    return sorted(int(v) for v in values) == [0, ms.SPECIAL_DISCO_BALL]


def step(move, action):
    """step_move with the powerup Foxy Roxy SE's spray path in force (its swipes
    paint an L, move_strategy.SPRAY_SE_PATH_OVERRIDE)."""
    if move.get("booster_type") == FOXY_ROXY_SE and foxy_powerup(move):
        import engine_foxy_powerup
        previous = ms.SPRAY_SE_PATH_OVERRIDE
        ms.SPRAY_SE_PATH_OVERRIDE = engine_foxy_powerup.spray_cells
        try:
            return step_move(move, action)
        finally:
            ms.SPRAY_SE_PATH_OVERRIDE = previous
    return step_move(move, action)


def step_move(move, action):
    """Return a new state and a narrower measured quantity, never a utility score.

    ``action["kind"]``: "swap" (default), "energy_boost" (Energy Boost then
    this swipe), "teleport" (any two pieces) or "booster" (Doctor Color).
    The last three need a capture-backed engine_refill model.
    """
    if move.get("mode") not in PREFIX_MODES:
        return {"supported": False, "reason": "mode prefix not certified by Strategy Lab"}
    model = move.get("engine_refill")
    jungle_leaves = model is not None and model.profile["rules"].get("boardModelName") == JUNGLE_RUMBLE_BOARD
    fireworks = model is not None and model.profile["rules"].get("boardModelName") == FIREWORKS_FESTIVAL_BOARD
    crystals = model is not None and model.profile["rules"].get("boardModelName") == CRYSTAL_CAVE_BOARD
    candy = model is not None and model.profile["rules"].get("boardModelName") == CANDY_WORLD_BOARD
    billie = getattr(model, "billie", None)
    hatched = HATCHED_SPECIALS if getattr(model, "random_specials", ()) else ()
    # JooJoo skulls the refill spawns as a special tile (Arcade Man), or the
    # Monkey JooJoo booster placed (they fall and explode the same way; in Solo
    # the ones that exploded come back after the move, joojoo_end_move).
    refill_skulls = model is not None and not hatched and (
        _refill_spawns(model, JOOJOO_SKULL_ENGINE) or joojoo_passive(getattr(model, "profile", None)))
    # Zany Zappers the refill spawns as a special tile (Funky Tiles master league).
    refill_zappers = model is not None and _refill_spawns(model, ZANY_ZAPPER_ENGINE)
    # Plunder Pirates' chest: SPECIAL_MODE_TARGET on a CHEST cell, only falls.
    chest = lambda r, c: (move["special_board"][r][c] == ms.SPECIAL_MODE_TARGET
                          and move["board"][r][c] == ms.CHEST and model is not None)
    if any(v not in RESTING_SPECIALS and v not in hatched
           and not (v == ms.SPECIAL_BILLIE_DRONE and billie is not None)
           and not chest(r, c)
           and not (v == ms.SPECIAL_JOOJOO_SKULL and refill_skulls)
           # Checkmate Charles knight: its jumps and the knights that come
           # back after the move use the engine RNG (engine_knights).
           and not (v == ms.SPECIAL_KNIGHT and getattr(model, "knights", None) is not None)
           and not (v in ms.ZANY_ZAPPER_SPECIALS and refill_zappers)
           # Dustville wanted figure: its shots and replenish use the engine RNG.
           and not (v == ms.SPECIAL_MODE_TARGET and (jungle_leaves or is_dustville(model)))
           and not (fireworks and v in ms.DIRECTIONAL_FIREWORK_SPECIALS)
           # Gem Grab crystal: a matchable purple piece that falls; the next
           # move start tops the crystals up (crystal_move_start).
           and not (crystals and ms.is_purple_gem_special(v))
           # Candy World candy: a blue/red piece that falls; the refill tops
           # the candies up (EngineRefill._convert_candies).
           and not (candy and v == ms.SPECIAL_RED_BLUE_TILE)
           # Vinnie SE's two-colour heart: clears two fixed colours, no random
           # target, and the refill carries it as a CupidHeart with color2.
           and not (model is not None and ms.is_vinnie_se_heart_special(v))
           # Foxy Roxy SE's spray can: falls, unmatchable; the refill carries
           # it as SlotValue 31 with the colour its slot keeps.
           and not (v == ms.SPECIAL_SPRAY_SE and model is not None)
           for r, row in enumerate(move["special_board"]) for c, v in enumerate(row)):
        return {"supported": False, "reason": "random or equipment special on board"}
    if hatched and action.get("kind", "swap") == "swap" and any(
            move["special_board"][r][c] in hatched for r, c in (action["start"], action["target"])):
        return {"supported": False, "reason": "random target outcome is not a deterministic prefix"}
    kind = action.get("kind", "swap")
    if move.get("jelly_zone_cells") and (not ms.JELLY_EXACT_PORTED or model is None or kind != "swap"):
        return {"supported": False, "reason": "Jelly SE requires a capture-backed swap"}
    if any(move.get(k) for k in ("funky_tile_cells", "hot_color_state")):
        return {"supported": False, "reason": "additional board layer"}
    if ((kind == "booster" and not FOXY_POWERUP_BOOSTER_PORTED)
            or (_is_spray_swipe(move, action) and not FOXY_POWERUP_SPRAY_PORTED)) and foxy_powerup(move):
        # Its patterns and spray paths are FoxyRoxySEPowerUpVariant1's own.
        return {"supported": False, "reason": "Foxy Roxy SE powerup varijanta jos nije portovana"}
    if billie is not None and kind not in ("swap", "energy_boost"):
        return {"supported": False, "reason": "Billie booster/perk timing is not ported"}
    if (model is not None and move.get("rules_id") == "rainbow"
            and any(v == ms.SPECIAL_FROGGY_LOTUS for row in move["special_board"] for v in row)
            and ms.froggy_gather_config_from_params(move.get("froggy_params")) is None):
        return {"supported": False, "reason": "Rainbow lotus needs captured gather configuration"}
    if kind != "swap" and model is None:
        return {"supported": False, "reason": f"{kind} needs the exact engine refill"}
    if kind in ("energy_boost", "teleport"):
        perk = PERK_ENERGY_BOOST if kind == "energy_boost" else PERK_TELEPORT
        if (move.get("perks") or {}).get(perk, 0) < 1:
            return {"supported": False, "reason": f"no {kind} left"}
    board, specials = deepcopy(move["board"]), deepcopy(move["special_board"])
    model = model.clone() if model is not None else None
    converted_order = ()
    if model is not None and move.get("check_cascade_timing"):
        # The refill check measures branches kept from the planner (engine_cleo_simulation).
        model.measure_only = True
    if kind == "booster":
        if move.get("booster_type") not in (DOCTOR_COLOR, WOOLLY_WORKOUT, CHECKMATE_CHARLES, FOXY_ROXY_SE,
                                            FROGGY_FU, BROCCO_BOOGIE, SWEEP_IT_SE):
            return {"supported": False, "reason": "only Doctor Color, Woolly Workout, Checkmate Charles, "
                                                  "Foxy Roxy SE, Froggy Fu, Brocco Boogie and Sweep It SE "
                                                  "are ported"}
        if move.get("booster_type") in (FROGGY_FU, BROCCO_BOOGIE, SWEEP_IT_SE) and model is None:
            return {"supported": False, "reason": "Froggy Fu / Brocco Boogie / Sweep It SE need the exact "
                                                  "engine refill"}
        charge = move.get("booster_state") or {}
        if charge.get("maximum") is None or (charge.get("current") or 0) < charge["maximum"]:
            return {"supported": False, "reason": "booster is not charged"}
        booster_energy_weight(model, _foxy_activations(move, model) + 1)
        if move.get("booster_type") == WOOLLY_WORKOUT:
            color = action.get("color")
            if color not in ms.WOOLLY_WORKOUT_TARGET_COLORS:
                return {"supported": False, "reason": "Woolly Workout needs a green/yellow/purple/orange target"}
            board = woolly_workout_convert(board, specials, int(color), model)
            if board is None:
                return {"supported": False, "reason": "Woolly Workout: no piece of that colour"}
            converted_order = woolly_workout_convert.last_order
        elif move.get("booster_type") in (CHECKMATE_CHARLES, FROGGY_FU, BROCCO_BOOGIE, SWEEP_IT_SE):
            pass    # drawn inside the refill context (charles_explosion_cells, froggy_activate, engine_brocco)
        elif move.get("booster_type") == FOXY_ROXY_SE:
            import engine_foxy
            foxy_activations = _foxy_activations(move, model) + 1
            board, converted_order = engine_foxy.activate(board, specials, model, foxy_activations,
                                                          ms.BLUE, ms.RED, move.get("froggy_params"))
        else:
            path = doctor_color_pick(board, model)
            if path is None:
                return {"supported": False, "reason": "no Doctor Color path on the board"}
            board = doctor_color_convert(board, specials, path)
        candidate = ms.MoveCandidate(NO_SWAP_CELL, NO_SWAP_CELL, ms.Direction.RIGHT, board, specials)
    else:
        start, target = tuple(action["start"]), tuple(action["target"])
        if (specials[target[0]][target[1]] == ms.SPECIAL_SWEEP_SE_BROOM
                and specials[start[0]][start[1]] != ms.SPECIAL_SWEEP_SE_BROOM and action.get("direction")):
            # A piece dragged onto a broom: the game drags the broom (its trace
            # names the broom as the source; live 2026-11-19 04:27:38).
            start, target = target, start
            action = dict(action, start=list(start), target=list(target),
                          direction=ms.OPPOSITE_DIRECTIONS[ms.Direction(action["direction"])].value)
        r, c = start; y, x = target
        spray = (start == target and specials[r][c] == ms.SPECIAL_SPRAY_SE)
        if spray and not SPRAY_EXACT_PORTED:
            return {"supported": False, "reason": "Foxy Roxy SE spray activation is not ported"}
        if kind != "teleport" and not spray and abs(r-y) + abs(c-x) != 1:
            raise ValueError("not an adjacent swap")
        # A Sweep SE broom is not swapped: the swipe only gives its direction
        # and the colour it sweeps (the partner's), see _sweep_se_target.
        if specials[r][c] != ms.SPECIAL_SWEEP_SE_BROOM:
            board[r][c], board[y][x] = board[y][x], board[r][c]
            specials[r][c], specials[y][x] = specials[y][x], specials[r][c]
        elif model is not None:
            if not ms.SWEEP_EXACT_PORTED:
                return {"supported": False, "reason": "Sweep SE broom swipe is not fully ported"}
            if not ms.sweep_paint_free(model.profile):
                return {"supported": False, "reason": "Sweep SE paint is not ported"}
            for _ in range(ms.SWEEP_PRE_REFILL_DRAWS):
                model.rng.next()
        candidate = ms.MoveCandidate(start, target, ms.Direction(action["direction"]), board, specials)
        if ms._candidate_activates_cleo_swap(candidate):
            if model is None:
                return {"supported": False, "reason": "Cleo: exact engine state is required"}
            if kind != "swap":
                return {"supported": False, "reason": "Cleo: perk/merge timing is not ported"}
    from engine_refill import UnsupportedRefill
    try:
        with (
            ExitStack() as replay_context,
            rules(move),
            ms.exact_jelly_rules(move.get("jelly_uses_left"), candidate, move["mode"]),
            engine_refill(model) as refills,
        ):
            if kind in ("energy_boost", "teleport") and move.get("floor_lava_columns") is not None:
                # A perk move leaves the lava as it was: no column marked, none
                # erupts (the-floor-is-lava 2026-11-17 115126: 000->001 Energy
                # Boost and 001->002 Teleport, both matched, counters stayed 0).
                replay_context.enter_context(ms.floor_lava_perk_move())
            if kind == "swap" and getattr(model, "mixy", None) is not None:
                from engine_mixy import convert_swap, redeal_unsupported
                unconverted = candidate
                candidate = convert_swap(model, candidate, bool(move.get("allow_square_matches")))
                if model.mixy_redealt:
                    return {"supported": False, "reason": redeal_unsupported(model)}
                if candidate is not unconverted:
                    # Any code use: the swipe's specials sit at the conversion origin
                    # (Color Climb 2026-11-12 02:49:10 / 02:49:48, last uses).
                    replay_context.enter_context(ms.mixy_redeal_replay_active())
            if kind == "booster" and move.get("booster_type") == CHECKMATE_CHARLES:
                cells = charles_activate(model, board, specials, bool(move.get("allow_square_matches")))
                result = ms._simulate_booster_effect_cells(
                    board, specials, candidate, set(cells),
                    allow_square_matches=bool(move.get("allow_square_matches")), mode=move["mode"])
                if result is None:
                    return {"supported": False, "reason": "Checkmate Charles: empty explosion"}
            elif kind == "booster" and move.get("booster_type") == BROCCO_BOOGIE:
                import engine_brocco
                try:
                    cells, brocco_allowed = engine_brocco.destroy_cells(board, specials, model,
                                                                        move.get("froggy_params"))
                except engine_brocco.UnsupportedBrocco as exc:
                    return {"supported": False, "reason": str(exc)}
                result = ms._simulate_booster_effect_cells(
                    board, specials, candidate, set(cells),
                    allow_square_matches=bool(move.get("allow_square_matches")), mode=move["mode"])
                if result is None:
                    return {"supported": False, "reason": "Brocco Boogie: empty destroy"}
            elif kind == "booster" and move.get("booster_type") == SWEEP_IT_SE:
                import engine_sweep
                try:
                    result, sweep_combo, sweep_evaluations = sweep_activate(move, model, board, specials)
                except engine_sweep.UnsupportedSweep as exc:
                    return {"supported": False, "reason": str(exc)}
                if result is None:
                    return {"supported": False, "reason": "Sweep It SE: the sweep matched nothing (not recorded)"}
                result.intent_events.append({"type": "sweep_booster_colors", "combo": list(sweep_combo),
                                             "evaluations": sweep_evaluations})
            elif kind == "booster" and move.get("booster_type") == FROGGY_FU:
                from engine_froggy_placement import UnsupportedPlacement
                froggy_activations = _foxy_activations(move, model) + 1
                try:
                    result, froggy_lotuses, froggy_events = froggy_activate(
                        move, model, board, specials, froggy_activations)
                except UnsupportedPlacement as exc:
                    return {"supported": False, "reason": str(exc)}
                if result is None:
                    return {"supported": False, "reason": "Froggy Fu: empty entrance"}
            elif kind == "booster":
                with ms.booster_converted_order(
                        converted_order, special_x_major=move.get("booster_type") == FOXY_ROXY_SE):
                    # The mode's rule holds for the booster's matches too: in
                    # Crystal Cave (specialsAutoExplode) the specials a Foxy
                    # paint creates go off at once (research 20261118_014743,
                    # 6 activations: fireworks and two columns right after
                    # the paint; without it the RNG ran 150-280 draws short).
                    result = ms.simulate_candidate(
                        candidate, allow_square_matches=bool(move.get("allow_square_matches")), mode=move["mode"],
                        explode_created_specials_immediately=(bool(move.get("specials_explode_immediately"))
                                                              or move["mode"] == ms.GameMode.BLOW_EM_UP.value))
            else:
                if kind == "energy_boost" and model is not None:
                    # engine_knights.KnightState.any_colour_charges; the crosshair's too.
                    model.any_colour_charges = True
                    if model.knights is not None:
                        model.knights.any_colour_charges = True
                result = simulate(move,candidate)
    except UnsupportedRefill as exc:
        return {"supported": False, "reason": f"engine refill: {exc}"}
    if result is None:
        return {"supported":False,"reason":"candidate no longer legal"}
    if model is not None and move.get("rules_id") == "rainbow":
        if any(e.get("type") == ms.FROGGY_LOTUS_GATHER_EVENT for e in result.intent_events):
            return {"supported": False, "reason": "Rainbow lotus gather is not certified for exact planning"}
        # A blast over the lotus: the game removes it (refill_misses
        # 2026-11-13 211812 / 212012, 18 and 29 draws more), the simulator
        # keeps it. Not ported.
        if any(e.get("type") in {"special_activation", "special_effect"} and e.get("lotus_hit")
               for e in result.intent_events):
            return {"supported": False, "reason": "Rainbow: a special blast hits the lotus (not ported)"}
        if rainbow_cascade_unported(model.profile, result.intent_events):
            return {"supported": False, "reason": "Rainbow cascade rocket/bomb timing is not ported"}
    # The powerup Foxy's L sprays (an edge line, often a five) replay exactly:
    # Bombs Away research 20261118_091058, every spray (tools/analyze_research).
    if spray_five_unported(result.intent_events, getattr(model, "profile", None)) and not foxy_powerup(move):
        return {"supported": False, "reason": "Foxy Roxy SE: a five from the spray is not ported"}
    # Recorded Color Crush 006->007: cascade special timing is not ported.
    # The RNG counter can agree while both the board and specials differ.
    # The planner keeps this boundary; the refill check measures such moves
    # (``check_cascade_timing``): Color Crush 2026-11-13 15:26:29 (research
    # 20261113_152616 001->002, a cascade row special) was exact, and the
    # 006->007 recording behind the boundary no longer exists.
    if (model is not None and move.get("mode") == ms.GameMode.COLOR_CRUSH.value
            and not move.get("check_cascade_timing")
            and any(e.get("type") == "special_activation" and e.get("cascade", 0) > 1
                    for e in result.intent_events)):
        return {"supported": False, "reason": "Color Crush cascade special timing is not ported"}
    # Recorded Dustville 016->017 and 028->029: a rocket fired in a cascade hits
    # a wanted figure; the RNG agrees, the board does not. Same open timing as above.
    if fireworks and fireworks_rocket_fired(result.intent_events):
        return {"supported": False, "reason": "Fireworks Festival: rocket activation is not ported"}
    if is_dustville(model) and any(_dustville_cascade_unported(e) for e in result.intent_events):
        return {"supported": False, "reason": "Dustville cascade special timing is not ported"}
    # A JooJoo skull fires along fixed directions by its colour
    # (MonkeyJoojooPieceLogic.GetAreaOfPieceExplode); only Match & Hatch's
    # hatched skulls stay out, as before.
    random_specials = RANDOM_TARGET_SPECIALS - ({"joojoo_skull"} if refill_skulls else set())
    if any("random_outcomes" in e.get("type", "")
           or (e.get("type") == "special_activation" and e.get("special") in random_specials
               and not e.get("exact_targets"))
           for e in result.intent_events):
        return {"supported":False,"reason":"random target outcome is not a deterministic prefix"}
    # A recolour that matches nothing is still a played booster.
    if kind != "booster" and not (result.matches or result.activated_specials or result.cleared_cells):
        return {"supported": False, "reason": "candidate no longer legal"}
    if model is not None and (
            any(e.get("type") == "uncertain_refill_boundary" for e in result.intent_events)
            or any(int(v) == ms.EMPTY for row in result.board for v in row)):
        return {"supported": False, "reason": "cascade stopped before the engine refill resolved it"}
    if billie is not None and kind == "swap":
        from engine_billie import finish_passive
        try:
            finish_passive(model, result)
        except UnsupportedRefill as exc:
            return {"supported": False, "reason": str(exc)}
    elif billie is not None and kind == "energy_boost":
        from dataclasses import replace
        model.billie = replace(billie, suppress_once=False)
    if model is not None and kind == "swap" and getattr(model, "mixy", None) is not None:
        # Mixy use #1: RandomizeActiveColors, the swipe's last draws (engine_mixy).
        from engine_mixy import finish_swipe
        finish_swipe(model, result.board)
    final_board, final_specials = result.board, result.special_board
    if kind == "booster" and move.get("booster_type") == FOXY_ROXY_SE:
        # FoxyUseEnded -> CreatingPieces: the cans go on the settled board.
        import engine_foxy
        from engine_refill import color_maps
        final_board, final_specials, cans = engine_foxy.place_cans(
            final_board, final_specials, model, foxy_activations, ms.BLUE, color_maps(model.profile)[0],
            move.get("froggy_params"))
        result.intent_events.append({"type": "foxy_spray_cans", "cells": [list(c) for c in cans]})
    if kind == "booster" and move.get("booster_type") == BROCCO_BOOGIE:
        # CreatingDiscoBalls: the balls go on the settled board.
        import engine_brocco
        brocco_activations = _foxy_activations(move, model) + 1
        final_board, final_specials, discos = engine_brocco.place_discos(
            final_board, final_specials, model, brocco_activations, brocco_allowed, move.get("froggy_params"))
        result.intent_events.append({"type": "brocco_disco_balls", "cells": [list(c) for c in discos]})
    if kind == "booster" and move.get("booster_type") == SWEEP_IT_SE:
        # SweepItUseEnded -> CreatingPieces: the brooms go on the settled board.
        import engine_sweep
        sweep_activations = _foxy_activations(move, model) + 1
        try:
            final_board, final_specials, brooms = engine_sweep.place_brooms(
                final_board, final_specials, model, sweep_activations)
        except engine_sweep.UnsupportedSweep as exc:
            return {"supported": False, "reason": str(exc)}
        result.intent_events.append({"type": "sweep_brooms", "cells": [list(c) for c in brooms]})
    if kind == "booster" and move.get("booster_type") == FROGGY_FU:
        # PlaceLotusesAndContinue: the planned lotuses go on the settled board.
        from engine_froggy_placement import place_lotuses
        final_board, final_specials = place_lotuses(final_board, final_specials, froggy_lotuses)
        result.intent_events.extend(froggy_events)
    charles_fired = kind == "booster" and move.get("booster_type") == CHECKMATE_CHARLES
    # Checkmate Charles: the knights come back before the board is shuffled,
    # and travel with their pieces in it. Square Match 2026-11-15 16:11:21
    # (refill_misses 20261115_161121, a booster that left no move): 42 draws
    # for the knights, then 29 rounds of 49; round 29 is the game's board,
    # knights and RNG counter. Shuffled first, no round gave that board.
    knights_back = False
    if model is not None:
        from engine_shuffle import has_possible_move, shuffle_board
        square = bool(move.get("allow_square_matches"))
        if not has_possible_move(final_board, final_specials, square):
            try:
                if _knights_return(model, move, kind, charles_fired, result):
                    final_specials = model.knight_end_move(final_board, final_specials)
                    knights_back = True
                if not knights_back or not has_possible_move(final_board, final_specials, square):
                    final_board, final_specials = shuffle_board(model, final_board, final_specials, square)
            except UnsupportedRefill as exc:
                return {"supported": False, "reason": f"engine refill: {exc}"}
    if model is not None and joojoo_refill_ported(model.profile) and kind != "booster":
        # Monkey JooJoo: the skulls that exploded come back on pieces already
        # on the board (EngineRefill.joojoo_end_move). Its order against a
        # shuffle is not recorded.
        final_specials = model.joojoo_end_move(final_board, final_specials,
                                               joojoo_skull_count(move["special_board"]))
    if not knights_back and _knights_return(model, move, kind, charles_fired, result):
        try:
            final_specials = model.knight_end_move(final_board, final_specials)
        except UnsupportedRefill as exc:
            return {"supported": False, "reason": f"engine refill: {exc}"}
    funky_after = move.get("funky_cells")
    if funky_after is not None and model is not None:
        fired = {tuple(e["cell"]) for e in result.intent_events or ()
                 if e.get("type") == "funky_tile_activation"}
        funky_after = model.funky_relocate(final_board, final_specials,
                                           [tuple(c) for c in funky_after if tuple(c) not in fired],
                                           relocate=bool(fired))
    if crystals:
        # CrystalCaveBoard.onMoveStart runs before the resting board is read.
        final_specials = model.crystal_move_start(final_board, final_specials)
    after = deepcopy({k: v for k, v in move.items() if k != "engine_refill"})
    if kind == "booster" and move.get("booster_type") == FOXY_ROXY_SE:
        after["foxy_activations"] = foxy_activations
    if kind == "booster" and move.get("booster_type") == FROGGY_FU:
        after["foxy_activations"] = froggy_activations   # the same ActivatesThisTurn counter
    if kind == "booster" and move.get("booster_type") == BROCCO_BOOGIE:
        after["foxy_activations"] = brocco_activations
    if kind == "booster" and move.get("booster_type") == SWEEP_IT_SE:
        after["foxy_activations"] = sweep_activations
    after["board"], after["special_board"] = final_board, final_specials
    if kind == "swap" and move.get("lights_up_column") is not None and model is not None:
        # LightsUpBoard.onMoveEnd (RandomColumnChange): Range(0, size) re-rolled
        # until it differs from the lit column; a booster or perk move keeps it
        # (research 20261117_125632 lights-up: 20 of 20 swipes, column and RNG).
        size, lit = len(final_board), int(move["lights_up_column"])
        rng = model.rng
        new = lit
        while new == lit:
            new = rng.range(0, size)
        after["lights_up_column"] = new
    if kind == "swap" and move.get("floor_lava_columns") is not None:
        _, after["floor_lava_columns"] = ms.floor_lava_transition(
            result.cascade_matches, move["floor_lava_columns"], result.has_direct_match_layer
        )
    if kind in ("swap", "energy_boost") and move.get("column_multipliers"):
        after["column_multipliers"] = column_mania_after(move, result, action)
    if move.get("jelly_zone_cells") and any(
        e.get("type") == ms.JELLY_ZONE_CONVERSION_EVENT for e in result.intent_events
    ):
        after["jelly_zone_cells"] = ()
    if funky_after is not None:
        after["funky_cells"] = funky_after
    turn = after.setdefault("turn_state", {})
    # With the exact refill, cascade fours are known too: the game granted
    # their extra move in every recorded case (and for a square as well).
    extra = bool(result.extra_moves if model is not None else result.direct_extra_moves)
    # Only a swipe costs a move; an extra-move combo adds one. For a swipe
    # that nets to "not consumed". Teleport (ConvertSlots, no swipe) is free
    # and its four gives +1 (player, 2026-11-01); the booster is assumed to
    # follow the same rule, not yet recorded.
    # Energy Boost is free as well: 29 recorded uses (Debug/research) go
    # +1 with an extra (4->5, 7->8, 3->4) and stay without one (1->1, 4->4,
    # 10->10); a cost would have needed +2. Square Match 2026-11-15 02:27:
    # the plan expected 9 moves, the game had 10, and the carried line was
    # dropped for another 5-minute plan.
    costs_move = kind == "swap"
    if kind == "energy_boost" and _disco_on_plain(move["special_board"], action):
        # The disco's "extra" only refunds the swipe, and this swipe is free:
        # 2 of 2 recorded (Lightning Strike 20261119_004552 011 8->8, Vertical
        # Rush 20261119_090048 001 6->6); predicted 7 dropped the line.
        # shortcut: an Xtra Move tile in the same wipe would still give +1, upgrade when recorded.
        extra = False
    if kind == "booster":
        extra = False  # recorded Doctor Color with a four: moves 6 -> 6
    if turn.get("remaining_moves") is not None:
        turn["remaining_moves"] = max(0, turn["remaining_moves"] - costs_move + extra)
        if turn.get("max_moves"):
            turn["remaining_moves"] = min(turn["remaining_moves"], int(turn["max_moves"]))
    charge = after.setdefault("booster_state", {})
    if charge.get("current") is not None and charge.get("maximum") is not None:
        # Energy Boost: every piece of the swipe's own match charges, not only
        # Blue; the cascades after it charge with Blue alone, as always. All 9
        # recorded uses with the swipe on file (Debug/research, 2026-11-15)
        # agree, 4 of them below a full meter; "every destroyed piece" gave 6
        # of 9 (1 of those 4). Square Match 15:26:41 (research 20261115_152355
        # 002 -> 003): a three and a cascade three, no Blue, energy 3 -> 6; the
        # plan expected a full meter, lost its line and searched 150 s again.
        # The booster empties the meter and its cascades do not refill it
        # (recorded energy 7 -> 0, confirmed by the player).
        # The swipe's own pieces are everything it destroys before the first
        # refill (direct_effect_cells: the match plus a funky tile or special
        # it sets off): 38 of 39 recorded uses (Debug/research, 2026-11-18),
        # the match alone 36. Funky Tiles research 20261118_113037 000->001:
        # a three on a funky cell, energy 0 -> 7; the match alone gave 5, the
        # plan lost its line and searched 4 minutes again.
        gained = (result.direct_effect_cells + result.blue_cells - result.direct_effect_blue_cells
                  if kind == "energy_boost" else result.blue_cells)
        if kind == "booster":
            charge["current"] = 0
        else:
            charge["current"] = min(charge["maximum"], charge["current"] + int(round(gained)))
    if kind in ("energy_boost", "teleport"):
        perk = PERK_ENERGY_BOOST if kind == "energy_boost" else PERK_TELEPORT
        after["perks"] = dict(after["perks"])
        after["perks"][perk] -= 1
    turn["owner_after"] = "us" if extra or (turn.get("remaining_moves") or 0) > 0 else "end_of_turn"
    temp_left = result.ability_temp_specials_left
    if temp_left and final_board is result.board:
        if turn["owner_after"] == "end_of_turn":
            # GameLogic.EndTurn -> ConvertLeftAbilityTempSpecials: plain pieces.
            after["special_board"] = ms.revert_ability_temp_specials(after["special_board"], temp_left)
        else:
            after["ability_temp_special_cells"] = list(temp_left)
    elif "ability_temp_special_cells" in after:
        after["ability_temp_special_cells"] = None
    if (model is not None and is_dustville(model)
            and (turn["owner_after"] == "end_of_turn" or model.profile["rules"].get("pvpMode") == 1)):
        # Solo rolls the Wanted replenish after each settled move, including
        # extra moves. Versus rolls it when the turn passes.
        after["special_board"] = model.wanted_turn_start(after["board"], after["special_board"])
    # A count of removed pieces is intentionally separate from game score:
    # historical logs do not reliably supply the multiplier of every mode.
    if model is not None:
        after["engine_refill"] = model
        # Square Solo score = value of every destroyed piece by colour (26 of
        # 26 recorded moves, 2026-11-01, including specials and squares).
        values = move.get("score_values") or {}
        gain = sum(n * values.get(int(c) % 1000, 1) for c, n in result.cleared_color_counts.items())
        spray_can = (_spray_can_points(move, action)
                     if kind in ("swap", "energy_boost") and _is_spray_swipe(move, action) else 0)
        gain += spray_can
        if kind in ("swap", "energy_boost") and action.get("start") is not None:
            (br, bc), (tr, tc) = action["start"], action["target"]
            if move["special_board"][br][bc] == ms.SPECIAL_SWEEP_SE_BROOM:
                # The broom takes the swept colour and is destroyed with it:
                # research 20261119_031206 014->015 (+3) and 042531 / refill_misses
                # 043526 (+1 each), the colour's value every time.
                gain += values.get(int(move["board"][tr][tc]), 1)
        gain += _froggy_stamp_points(model, result, values)
        if model.profile["rules"].get("boardModelName") == CRYSTAL_CAVE_BOARD:
            # Gem Grab: a collected crystal scores the value printed on it
            # (SlotModel.score, mode_targets) on top of the colour scores;
            # research 20261117_112217, 16 of 16 recorded moves exact.
            gain += float(result.mode_targets or 0)
        if move.get("score_multiplier") is not None:
            gain = _multiplier_score(move, result, values, after, perk=kind in ("energy_boost", "teleport"),
                                     booster=kind == "booster" and move.get("booster_type") == FOXY_ROXY_SE,
                                     can_points=int(spray_can),
                                     ability=kind in ("energy_boost", "teleport", "booster"))
        if move.get("score") is not None:
            gain = _solo_targets(move, after, gain)
            after["score"] = move["score"] + int(round(gain))
        return {"supported": True, "metric": "cleared_tiles", "value": float(result.cleared_cells),
                "score_gain": gain, "state": after, "extra": extra, "events": result.intent_events,
                "refills": refills,
                "terminal_reason": "engine_refill: whole action, unverified against a recorded transition"}
    return {"supported": True, "metric": "deterministic_prefix_cleared_tiles",
            "value": float(result.cleared_cells), "state": after,
            "extra": extra, "events": result.intent_events,
            "terminal_reason": "unknown_refill: prefix only, not a whole action or match"}
