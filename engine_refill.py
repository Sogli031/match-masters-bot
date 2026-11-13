"""5.817 RefillSlots (FillAllEmptySlots), using engine colors and RNG.

Ported from the fixed branch, verified on Square Match Solo. The adaptive
two-player Versus thresholds are resolved from score, moves and spawn bonuses;
other adaptive branches still need explicit thresholds (tools/verify_refill
tries the candidates from simulator_capture.threshold_hypotheses).

This module fills existing holes; gravity, combo destruction and game flow
belong to the caller. Unsupported rule branches raise rather than silently
falling back to independent uniform draws.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field

import numpy as np

from engine_rng import EngineRNG
from engine_spawn_weights import get_colors_priority, create_weights_list_new, pick_color
from engine_spawn_predicates import combo_count_at, is_part_of_combo, is_part_of_possible_highrank_combo
from simulator_capture import decode_dictionary, resolve_refill_overrides


class UnsupportedRefill(ValueError):
    pass


# rules.boardModelName: Multiplier Mushrooms and Mighty Mushrooms. 30 takes the same
# filter by measurement, not from its code: 20261104_144248 went from 3 to 19 of 19.
MUSHROOM_BOARDS = (29, 30)
# BoardAnalyzer.everyMatchIsSpecialsList (cctor 0x592d764): engine Column, Row,
# Column, Row, Bomb, Fireworks; a plain combo under everyMatchIsSpecial draws one.
EVERY_MATCH_SPECIALS = (4, 5, 4, 5, 6, 7)
COLOR_CRYSTALS_BOARD = 16
ZANY_ZAPPERS_BOARD = 33
ZANY_ZAPPERS_MAX_ROW_FILL = 4   # ZanyZappersBoard.MAX_ROW_FILL: zappers spawn only at y < 4
# FunkyTilesBoard.get_MaxBoardSpecialTiles: a rule parameter, default 3; the
# recorded master league board always holds 2.
FUNKY_MAX_TILES = 2
ZANY_ZAPPER = 17
MUSHROOM_COLORS = (6, 3, 5, 7)      # engine colours

# Match & Hatch: additionalData.specialPiecesWeights name -> simulator special.
RANDOM_SPECIAL_NAMES = {"AllAboardSEBandit": 18, "CupidHeart": 11, "MonkeyJoojooPiece": 19,
                        "FoxyRoxySEPiece": 29, "BroccoBoogiePiece": 16, "CleoCadabraPiece": 13}
# Simulator special -> engine SlotValue. The board shows 99 over the uncoloured
# ones, while the slot keeps the combo's colour (0x592c438) and the refill counts it.
UNCOLORED_RANDOM_SPECIALS = {16: 28, 29: 31, 13: 32}
# Sweep It SE's broom (SlotValue 38): the board shows 99, the slot keeps a
# colour, it falls, cannot be matched or damaged (2026-11-07 Color Crush dump).
SIM_SWEEP_BROOM, ENGINE_SWEEP_BROOM = 45, 38
UNCOLORED_RANDOM_SPECIALS[SIM_SWEEP_BROOM] = ENGINE_SWEEP_BROOM
# Foxy Roxy SE's spray can (SlotValue 31) outside Match & Hatch: the booster
# drops it on the board, which shows 99; the slot keeps its colour, it falls,
# cannot be matched or damaged (2026-11-09 Column Mania recording).
SIM_SPRAY_CAN, ENGINE_SPRAY_CAN = 29, 31
COLORED_RANDOM_SPECIALS = {18: 29, 11: 23, 19: 24}
# Colourless pieces whose raw colour still counts for spawning in any mode. A
# Cleo keeps the slot's colour (dump_board "color"), and it sits on the board in
# every Cleo booster match, not just where Match & Hatch hatches one.
ENGINE_BALL_VALUES = (26, 28, 31, 32, 38)
SIM_CLEO = 13
ENGINE_CLEO = 32


# DustvilleDuelBoard (boardModelName 4). Wanted figure = SlotValue 16 on an orange
# piece (convertToWanted b__26_1 0x59865f4: plain, not wanted, MatchesWithColor(6)).
DUSTVILLE_BOARD = 4
JUNGLE_RUMBLE_BOARD = 7
FIREWORKS_FESTIVAL_BOARD = 9
WANTED_VALUE = 16


def fireworks_rocket_fired(events):
    return any(e.get("type") == "special_activation" and
               str(e.get("special", "")).startswith("firework_") for e in events)
WANTED_COLOR = 6        # engine Orange
# Getter fallbacks when extraData has no key (get_* 0x59853a8..0x59858d0).
DUSTVILLE_DEFAULTS = {"wantedTilesCount": 2, "scoreBonusPerHit": 4, "wantedShoots": 4,
                      "minBluesToPick": 4, "chanceToPickBlue": 0, "replenishRate": 1,
                      "replenishChance": 0.0}
DUSTVILLE_NEUTRALS = (6, 3, 5, 7)   # GetAreaOfBluesAndRedsByMinAndChances colour list
SIM_BLUE, SIM_RED = 1, 5

# Crosshair (engine SlotValue 8, the Square Match special): BoardModel.GetCrosshair
# 0x59718d8 reads MatchRulesModel.additionalData["gemPickThreshold"].
CROSSHAIR_CONFIG_KEY = "gemPickThreshold"
CROSSHAIR_STRATEGIES = ("maxEnergyPieces", "maxMatchingColorPieces", "maxClassicSpecialPieces")
# Simulator specials SlotModel.get_IsClassicSpecial accepts: Row, Column, Bomb,
# Lightning (Fireworks) and the crosshair itself (engine 4..8).
SIM_CLASSIC_SPECIALS = frozenset({1, 2, 3, 4, 46})


# Candy World (CandyWorldBoard, boardModelName 2). A candy is SlotValue 16
# (BoardSpecial) on a blue piece with the red colour in color2; the simulator
# reads it as SPECIAL_RED_BLUE_TILE (board_source._board_special_special).
# RefillSlots 0x597dc40: base BoardModel.RefillSlots, then always one
# Chance(round(ReplenishChance * 100)); on success, while fewer than
# MaxBoardSpecialTiles candies stand, ConvertSlots 0x597d8bc turns
# min(ReplenishRate, missing) of the newly filled slots into candies. Getter
# defaults: get_ReplenishChance 0.6 (float at 0x1331900), get_ReplenishRate 1,
# get_MaxBoardSpecialTiles 2. ConvertSlots: see EngineRefill._convert_candies.
CANDY_WORLD_BOARD = 2
# Gem Grab / Purple Gem (CrystalCaveBoard, boardModelName 3). A crystal is
# SlotValue 16 on a purple piece whose SlotModel.score is its printed number.
# No RefillSlots override: onMoveStart 0x5983b80 tops the crystals up. Getter
# defaults (game_mode_logic_from_code.md): max 1, rate 1, chance 1.0, initial 2.
CRYSTAL_CAVE_BOARD = 3
CRYSTAL_DEFAULTS = {"maxBoardSpecialTiles": 1, "replenishRate": 1, "replenishChance": 1.0,
                    "initialScore": 2}
CRYSTAL_COLOR = 7           # engine Purple (IgnorePosition: MatchesWithColor(7))
CANDY_DEFAULTS = {"replenishChance": 0.6, "replenishRate": 1, "maxBoardSpecialTiles": 2}
SIM_RED_BLUE_TILE = 27      # move_strategy.SPECIAL_RED_BLUE_TILE
CANDY_COLORS = (1, 5)       # simulator BLUE, RED (move_strategy.RED_BLUE_TILE_COLORS)

# APPROXIMATE_REFILL: the fallback when the exact port does not cover a mode or
# a piece. The refill still draws from the live RNG with the live colour
# counts, so most holes get the colour the game will drop; what is not ported
# is replaced by its nearest ported neighbour:
#   * unresolved prevention thresholds -> approximate_thresholds();
#   * an unported special tile type / conversion -> left out (its draws kept
#     where the code is known, e.g. Fireworks / Candy World Chance roll);
#   * an unknown piece on the board -> a plain piece of its colour, or a
#     colourless blocker when it has no colour;
#   * legacy weights, forced combos, live events -> the ported branch.
# The ranking sees such a drop as likely, never as certain:
# result.exact_refill_supported stays False and result.refill_approximate True.


def approximate_thresholds(profile):
    """Prevention thresholds for the approximate refill: the configured
    baseline when there is one, else the override, else the last-round 100s."""
    hypotheses = {}
    try:
        from simulator_capture import threshold_hypotheses
        hypotheses = threshold_hypotheses(profile) or {}
    except (KeyError, TypeError, ValueError, AttributeError):
        pass
    for name in ("spawn baseline", "refillLogicOverride", "poslednja runda (100)"):
        if name in hypotheses:
            return dict(hypotheses[name])
    return {"match": 100, "combo": 100, "special_combo": 100, "square": -1}


def is_dustville(model) -> bool:
    """A refill model of a Dustville Duel board (test doubles have no config)."""
    config = getattr(model, "dustville_config", None)
    return config is not None and config() is not None


# Monkey JooJoo (booster 40). The number of skulls on the board only grows with
# a booster throw (skullsPerActivation, Solo "4,1": 4, then +1 per throw).
# After every move EndMoveWithPassiveAbility 0x5a7c650 -> ChoosePositions
# 0x5a7b6b0 tops the board back up to that number on pieces already there, so
# skulls that exploded come back elsewhere (joojoo_end_move). Hot Color research
# 20261112_001019: 9 of 9 played moves exact (board, skull cells, RNG).
MONKEY_JOOJOO_BOOSTER = 40
SIM_JOOJOO_SKULL = 19            # move_strategy.SPECIAL_JOOJOO_SKULL
# MonkeyJoojoo.AllowedColors (.cctor 0x5a7c9d0): engine Orange, Green, Yellow, 7, 8.
JOOJOO_ALLOWED_COLORS = (6, 3, 5, 7, 8)
# ability_config.json, type 40, Solo override (pvpMode 1). Other modes keep the
# old behaviour: the move is exact, the board after it is not followed.
JOOJOO_SOLO_MATCHABLE_CHANCE = 20


def joojoo_passive(profile) -> bool:
    """The local player's booster is Monkey JooJoo (its skulls are on the board)."""
    for player in (profile or {}).get("players") or ():
        if player.get("player_type") == 0:
            return (player.get("model") or {}).get("specialAbilityType") == MONKEY_JOOJOO_BOOSTER
    return False


def joojoo_refill_ported(profile) -> bool:
    """Monkey JooJoo in Solo: the skulls after a move are simulated (joojoo_end_move)."""
    return joojoo_passive(profile) and ((profile or {}).get("rules") or {}).get("pvpMode") == 1


def joojoo_skull_count(special) -> int:
    # The live board can be a numpy array: `special or ()` raised ValueError
    # (truth value of an array) and failed every move (2026-11-12 00:39:35).
    if special is None:
        return 0
    return sum(int(v) == SIM_JOOJOO_SKULL for row in special for v in row)


def rainbow_cascade_unported(profile, events) -> bool:
    """Rainbow rocket/bomb timing in later cascades: ported, never refused.

    The guard came from one 2026-11-01 swipe (recording since gone). On every
    recording now present, 27 exact replays fire a rocket or bomb past the
    first cascade (Solo and Versus, direct and cascade-made specials and ones
    already on the board), and dropping the guard turned 12 of 37 Rainbow
    refill misses exact with none lost (2026-11-10 02:05: four of four).
    Kept so callers can name the branch if it ever needs refusing again.
    """
    return False


def spray_five_unported(events, profile=None) -> bool:
    """A Foxy Roxy SE ray of six or more cells that makes a five, or any
    spray on a mushroom board.

    2026-11-09 Column Mania: a ray of five (014->015) leaves a resting
    lightning exactly as simulated; a ray of seven (012->013) took 175 draws
    more than that, which is not ported.

    Mighty Mushrooms (board 30) 2026-11-10 06:24 (Debug/research
    20261110_062446): 6 of 6 sprays missed -- rays of 3, 4 and 5, with and
    without a mushroom in them -- the game drawing 35-105 more than the
    simulator, while all 6 ordinary swaps were exact. No single extra-draw
    point before the fill or the special tiles reproduces it."""
    rules = (profile or {}).get("rules") or {}
    if rules.get("boardModelName") in MUSHROOM_BOARDS and any(
            event.get("type") == "spray_se_conversion" for event in events):
        return True
    return any(event.get("type") == "spray_se_conversion"
               and len(event.get("converted_cells") or ()) >= 6 for event in events) and any(
        event.get("type") == "match" and event.get("cascade") == 1 and event.get("kind") == "five"
        for event in events)


def _random_special_table(rules):
    """((simulator special, weight), ...) in dictionary order; () outside this rule."""
    if not rules.get("extraMoveRandomSpecial"):
        return ()
    extra = decode_dictionary(rules.get("additionalData")) or {}
    weights = decode_dictionary(extra.get("specialPiecesWeights")) or {}
    table = tuple((RANDOM_SPECIAL_NAMES.get(name), int(weight)) for name, weight in weights.items() if int(weight) > 0)
    if not table or any(special is None for special, _ in table):
        raise UnsupportedRefill("Random special table is outside the ported pieces")
    return table


@dataclass
class EngineRefill:
    profile: dict
    rng: EngineRNG
    spawned_colors: dict[int, int] = field(default_factory=dict)
    # match/combo/special_combo/square prevention thresholds.
    thresholds: dict | None = None
    # Present only when the raw drone colour and supported passive config exist.
    billie: object | None = None
    # Disco balls as (row, col, engine colour), from the raw slots. The slot keeps
    # its colour under the ball and CountFillingSlots counts it; None = not read.
    balls: list | None = None
    # MatchRulesModel.extraMoveRandomSpecial; empty = ordinary created specials.
    random_specials: tuple = ()
    # engine_mixy.MixyPassive while our Mixy code can trigger, else None.
    mixy: object | None = None
    # The swipe re-dealt the Mixy code (use #1) without the config to predict it.
    mixy_redealt: bool = False
    # None = exact: an unported branch raises UnsupportedRefill. A list = the
    # approximate fallback (APPROXIMATE_REFILL below): the branch is skipped or
    # replaced by its nearest ported neighbour and its reason appended here.
    approximate: list | None = None
    # Special tile types the approximate model leaves out (their shuffle draw stays).
    skipped_special_tiles: frozenset = frozenset()
    # Draws a Lightning's target shuffle took, owed by the next refill.
    pending_effect_draws: int = 0
    # Gem Grab: the score the next crystal gets (extraData nextBoardSpecialScore).
    crystal_next_score: int | None = None

    def unported(self, reason):
        """An unported branch: raise when exact, note it and go on when approximate."""
        if self.approximate is None:
            raise UnsupportedRefill(reason)
        if reason not in self.approximate:
            self.approximate.append(reason)

    @property
    def is_approximate(self) -> bool:
        return bool(self.approximate)

    @classmethod
    def from_profile(cls, profile, *, seed=None, resume=False, thresholds=None, approximate=False):
        """``approximate=True``: the fallback for a configuration the exact port
        does not cover. Every check that would raise is noted in ``approximate``
        instead and the nearest ported behaviour is used (see APPROXIMATE_REFILL)."""
        notes = [] if approximate else None

        def unported(reason):
            if notes is None:
                raise UnsupportedRefill(reason)
            if reason not in notes:
                notes.append(reason)

        if thresholds is None:
            try:
                resolved = resolve_refill_overrides(profile)
            except (KeyError, TypeError, ValueError) as exc:
                if notes is None:
                    raise
                resolved = {"resolved": False, "reason": str(exc)}
            if resolved.get("resolved"):
                thresholds = resolved["prevention_thresholds"]
            else:
                unported("Adaptive thresholds need a complete Versus profile or an explicit hypothesis")
                thresholds = approximate_thresholds(profile)
        config = profile["config"]["spawnEngine"]
        spawning = profile["spawning"]
        if not config.get("newColorPickLogic"):
            unported("Legacy createWeightsList is not the captured branch")
        if spawning.get("<ForceNextCombo>k__BackingField") or spawning.get("<ForceBlueCombo>k__BackingField"):
            unported("Forced-combo spawning requires its separate algorithm")
        special_data = decode_dictionary(spawning.get("specialTilesData")) or {}
        skipped = set()
        # ProcessSpecialTile is the same for any one tile type; checked on
        # Rainbow Hearts and Hot Color Bombs. Several types run one after the
        # other in the dictionary's order (Mighty Mushrooms: 19 then 6).
        unknown = [value for value in special_data if value not in ENGINE_SPECIAL_TO_SIM]
        if unknown:
            unported("Special tile spawning is not ported for this configuration: "
                     f"tile values {sorted(special_data, key=str)}")
            skipped.update(unknown)
        for value, raw_tile in special_data.items():
            if value in skipped:
                continue
            tile = decode_dictionary(raw_tile) or {}
            supported_keys = {"excludePlayersColorOnRefill", "initialSpawn", "refillSpawn", "maxSpawn",
                              "spawnChance", "minGuaranteedPieces", "replenishRate", "replenishAtTurn"}
            # Plunder Pirates' chest config has no minGuaranteedPieces: the
            # engine field then keeps its default 0.
            tile.setdefault("minGuaranteedPieces", 0)
            required = {"refillSpawn", "maxSpawn", "spawnChance", "minGuaranteedPieces"}
            # replenishAtTurn -1 = never; another value is a turn-based branch.
            if tile.get("replenishAtTurn", -1) != -1:
                unported("Special tile replenishAtTurn is not ported")
                skipped.add(value)
            if (not required <= tile.keys() or tile.keys() - supported_keys
                    or any(not isinstance(tile[k], int) or tile[k] < 0 for k in required)
                    or tile["spawnChance"] > 100 or tile["minGuaranteedPieces"] > tile["maxSpawn"]):
                unported("Special tile config is outside the ported refill branch")
                skipped.add(value)
        try:
            random_specials = _random_special_table(profile["rules"])
        except UnsupportedRefill as exc:
            unported(str(exc))
            random_specials = ()
        # GetRandomSpecialPiece 0x59ded68 caches its randomizer here on first use,
        # so a filled field over the same weights is not another configuration.
        randomizer = profile["rules"].get("weightsRandomizer")
        if randomizer is not None:
            cached = decode_dictionary(randomizer.get("_weights")) or {}
            table = {RANDOM_SPECIAL_NAMES.get(name): int(weight) for name, weight in cached.items() if int(weight) > 0}
            if not random_specials or table != dict(random_specials):
                unported("WeightsRandomizer is not empty")
        # RandomSpawnLiveEventPieces returns before any draw when its chance
        # table is null; which table GameLogic picks depends on the mode.
        if any(config.get(k) is not None for k in (
                "liveEventPieceChancesBySpawnedSolo", "liveEventPieceChancesBySpawned",
                "liveEventPieceChancesBySpawnedRumbleParty", "liveEventPieceChancesBySpawnedShowdown")):
            unported("Live event spawning is configured")
        local = [p for p in profile.get("players", []) if p.get("player_type") == 0]
        if len(local) != 1:
            # Not a rule branch: without our player the colours cannot be mapped.
            raise UnsupportedRefill("Simulator color bridge needs exactly one local player")
        rng = EngineRNG.from_capture(profile) if seed is None else EngineRNG.from_seed(seed)
        spawned = decode_dictionary(spawning.get("spawnedColors")) or {} if resume else {}
        balls = profile.get("ball_slots")
        balls = None if balls is None else [(s["row"], s["col"], s["color"]) for s in balls
                                            if random_specials or s.get("value", 28) in ENGINE_BALL_VALUES]
        crystal_next = None
        if profile["rules"].get("boardModelName") == CRYSTAL_CAVE_BOARD:
            extra = decode_dictionary(profile.get("board_extra_data")) or {}
            crystal_next = extra.get("nextBoardSpecialScore")
            if crystal_next is None:
                unported("Gem Grab: nextBoardSpecialScore missing from the recording")
            else:
                crystal_next = int(crystal_next)
        return cls(profile, rng, spawned, dict(thresholds), balls=balls, random_specials=random_specials,
                   approximate=notes, skipped_special_tiles=frozenset(skipped),
                   crystal_next_score=crystal_next)

    def clone(self):
        return type(self)(self.profile, self.rng.clone(), dict(self.spawned_colors), self.thresholds, self.billie,
                          None if self.balls is None else list(self.balls), self.random_specials,
                          self.mixy, self.mixy_redealt,
                          approximate=None if self.approximate is None else list(self.approximate),
                          skipped_special_tiles=self.skipped_special_tiles,
                          pending_effect_draws=self.pending_effect_draws,
                          crystal_next_score=self.crystal_next_score)

    def approximate_clone(self):
        """This model, RNG and all, as the approximate fallback."""
        model = self.clone()
        if model.approximate is None:
            model.approximate = []
        return model

    copy = clone

    # ------------------------------------------------------------ Dustville Duel
    def dustville_config(self):
        """DustvilleDuelBoard getters: extraData over the code defaults; None elsewhere."""
        if self.profile["rules"].get("boardModelName") != DUSTVILLE_BOARD:
            return None
        extra = decode_dictionary(self.profile["rules"].get("_extraData")) or {}
        config = dict(DUSTVILLE_DEFAULTS)
        config.update({k: extra[k] for k in DUSTVILLE_DEFAULTS if k in extra})
        return config

    def wanted_shots(self, board, special, prevent):
        """GetAreaOfBoardSpecialEffect 0x59862e4 -> BoardModel.GetAreaOfBluesAndRedsByMinAndChances
        0x59757b0 (amount wantedShoots, minBlues, chanceToPickBlue, normalsOnly).

        Simulator boards in, simulator cells (row, col) out. Blue and red are the
        current player's and opponent's colours, each scanned then shuffled; the
        neutrals are colours 6, 3, 5, 7 in that order, not shuffled. Cells about
        to be destroyed are left out. Each shot: blue while fewer than minBlues
        were picked, then Chance(chanceToPickBlue) for one more; otherwise red,
        otherwise a neutral. A list runs dry -> the shot is skipped.
        """
        config = self.dustville_config()
        if config is None:
            return []
        sim_to_engine, engine_to_sim = color_maps(self.profile)
        player = sim_to_engine[SIM_BLUE]
        # CurrentOpponent null (solo): Blue <-> Red by the player's slot type.
        opponent = sim_to_engine[SIM_RED] if len(self.profile.get("players", [])) > 1 else (2 if player == 4 else 4)
        prevent = {tuple(cell) for cell in prevent}

        def plain(engine_color):
            want = engine_to_sim.get(engine_color)
            return [(y, x) for y, x in self._where_order(board)
                    if int(board[y][x]) == want and int(special[y][x]) == 0]

        blues = [c for c in self.rng.shuffled(plain(player)) if c not in prevent]
        reds = [c for c in self.rng.shuffled(plain(opponent)) if c not in prevent]
        neutrals = [c for color in DUSTVILLE_NEUTRALS for c in plain(color) if c not in prevent]
        # 0x3c13990 shuffles the colour list after it was used (result unused):
        # four draws, no effect on the order. Recorded 003/022/026/030 need them.
        for _ in DUSTVILLE_NEUTRALS:
            self.rng.next()
        shots, picked_blue = [], 0
        for _ in range(int(config["wantedShoots"])):
            if picked_blue < int(config["minBluesToPick"]) or self.rng.chance(int(config["chanceToPickBlue"])):
                source = blues if blues else None
            else:
                source = None
            if source is blues:
                picked_blue += 1
            elif reds:
                source = reds
            elif neutrals:
                source = neutrals
            else:
                continue
            cell = source[self.rng.range(0, len(source))]
            source.remove(cell)
            shots.append(cell)
        return shots

    @staticmethod
    def _where_order(board):
        """BoardModel.Where order over the simulator board (x-major, like GetSlotPrioritize)."""
        rows, columns = len(board), len(board[0])
        return [(y, x) for x in range(columns) for y in range(rows)]

    def funky_relocate(self, board, special, remaining, *, relocate=True):
        """FunkyTilesBoard.onMoveStart 0x598ff2c: refill the funky markers.

        BeforeCombosDestroy 0x5990870 drops every marker the move destroyed
        and sets ConvertTargetOnMoveStart; the next move start then calls
        GetSlotPrioritize 0x5972158 for MaxBoardSpecialTiles - remaining
        cells. Predicates: priority b__17_0 is always false; b__17_1 excludes
        the border and a cell that is already funky. Where scans x-major and
        the list is shuffled, one draw per candidate.
        """
        remaining = [tuple(c) for c in remaining]
        if not relocate:
            return remaining
        rows, columns = len(board), len(board[0])
        need = FUNKY_MAX_TILES - len(remaining)
        if need <= 0:
            return remaining
        candidates = [(y, x) for y, x in self._where_order(board)
                      if 0 < x < columns - 1 and 0 < y < rows - 1 and (y, x) not in remaining]
        return remaining + self.rng.shuffled(candidates)[:need]

    def joojoo_end_move(self, board, special, target):
        """MonkeyJoojoo.EndMoveWithPassiveAbility 0x5a7c650 -> ChoosePositions(logic, true).

        ``target``: the skulls the throws so far allow (sum of
        skullsPerActivation, at most maxPieces); the resting board before the
        move holds exactly that many. ``count = target - skulls left``; none
        missing draws nothing (a move with no exploding skull).

        Candidates (closures b__6 / b__8 / b__10): a plain piece (SlotValue 0)
        whose colour is in AllowedColors. Matchable cells: every combo cell of
        BoardAnalyzer.GetPossibleMoves(board, true), mapped back to before the
        swap (b__13_4 / b__11 / b__12), the same set engine_billie reads.
        ``count`` Chance(chanceToPickMatchablePiece) draws give k; then three
        GetSlotPrioritize 0x5972158 calls (priority b__13_5/7/9 is always
        false, so: x-major scan, shuffled, one draw per candidate): k from the
        matchable cells, the rest from the others, and whatever is still
        missing from any candidate not taken. Returns a new special board.
        """
        from engine_billie import _possible_pieces

        special = [list(row) for row in special]
        count = int(target) - joojoo_skull_count(special)
        if count < 1:
            return special
        to_sim = color_maps(self.profile)[1]
        allowed = {to_sim[c] for c in JOOJOO_ALLOWED_COLORS if c in to_sim}
        square = bool((decode_dictionary(self.profile["rules"].get("_extraData")) or {}).get("allowSquareMatches"))
        plain = [(y, x) for y, x in self._where_order(board)
                 if int(board[y][x]) in allowed and int(special[y][x]) == 0]
        matchable = set(_possible_pieces([[int(v) for v in row] for row in board], square, special))
        wanted = sum(self.rng.chance(JOOJOO_SOLO_MATCHABLE_CHANCE) for _ in range(count))
        picks = []
        if wanted >= 1:
            picks += self.rng.shuffled([cell for cell in plain if cell in matchable])[:wanted]
        if count - len(picks) >= 1:
            picks += self.rng.shuffled([cell for cell in plain if cell not in matchable])[:count - len(picks)]
        if count - len(picks) >= 1:
            picks += self.rng.shuffled([cell for cell in plain if cell not in picks])[:count - len(picks)]
        for y, x in picks:
            special[y][x] = SIM_JOOJOO_SKULL
        return special

    def crystal_config(self):
        settings = dict(CRYSTAL_DEFAULTS)
        extra = decode_dictionary(self.profile["rules"].get("_extraData")) or {}
        settings.update({k: extra[k] for k in CRYSTAL_DEFAULTS if k in extra})
        return settings

    def crystal_move_start(self, board, special):
        """CrystalCaveBoard.onMoveStart 0x5983b80 + ConvertSlots 0x59836d4.

        Fewer crystals than MaxBoardSpecialTiles -> one
        Chance(round(ReplenishChance * 100)); on success
        ConvertSlots(min(ReplenishRate, missing)). Candidates (b__0 =
        !IgnorePosition 0x59835c8): plain purple pieces, no special, no
        crystal, in Where's x-major order. GetSlotPrioritize 0x5972158 takes
        the topmost row of them (b__1: y == min y) when that row alone covers
        the amount, shuffled; otherwise all of it unshuffled, then the other
        candidates shuffled (one draw each) until the amount is reached. Each
        pick, in that order, gets score nextBoardSpecialScore++ (stored as a
        byte). Returns a new special board.
        """
        import move_strategy as ms

        special = [list(row) for row in special]
        if self.crystal_next_score is None:
            self.unported("Gem Grab: nextBoardSpecialScore missing from the recording")
            return special
        config = self.crystal_config()
        crystals = sum(ms.is_purple_gem_special(v) for row in special for v in row)
        missing = int(config["maxBoardSpecialTiles"]) - crystals
        if missing < 1:
            return special
        if not self.rng.chance(int(round(float(config["replenishChance"]) * 100))):
            return special
        amount = min(int(config["replenishRate"]), missing)
        purple = color_maps(self.profile)[1].get(CRYSTAL_COLOR)
        candidates = [(y, x) for y, x in self._where_order(board)
                      if int(board[y][x]) == purple and int(special[y][x]) == 0]
        if not candidates:
            return special
        top = min(y for y, _ in candidates)
        first = [cell for cell in candidates if cell[0] == top]
        if len(first) >= amount:
            picks = self.rng.shuffled(first)[:amount]
        else:
            rest = [cell for cell in candidates if cell[0] != top]
            picks = first + self.rng.shuffled(rest)[:amount - len(first)]
        for y, x in picks:
            score = self.crystal_next_score & 0xFF
            self.crystal_next_score += 1
            special[y][x] = ms.make_purple_gem_special(score, exact=True)
        return special

    def wanted_turn_start(self, board, special):
        """onTurnStart 0x5986058 + convertToWanted 0x5985cd8, on simulator boards.

        Missing figures -> one Chance(round(replenishChance * 100)); on success
        min(replenishRate, missing) orange plain pieces (GetSlotPrioritize: no
        priority, x-major scan, shuffled) become wanted (SlotValue 16).
        Returns a new special board.
        """
        config = self.dustville_config()
        special = [list(row) for row in special]
        missing = int(config["wantedTilesCount"]) - sum(int(v) == SIM_MODE_TARGET for row in special for v in row)
        if missing < 1:
            return special
        if not self.rng.chance(int(round(float(config["replenishChance"]) * 100))):
            return special
        orange = color_maps(self.profile)[1].get(WANTED_COLOR)
        candidates = [(y, x) for y, x in self._where_order(board)
                      if int(board[y][x]) == orange and int(special[y][x]) == 0]
        for y, x in self.rng.shuffled(candidates)[:min(int(config["replenishRate"]), missing)]:
            special[y][x] = SIM_MODE_TARGET
        return special

    def random_special(self, cell, sim_color, every_match=False):
        """The special this player combo hatches into, or None outside the rule.

        ``every_match``: a plain combo under everyMatchIsSpecial (Special
        O'Rama). MakeSpecialSlotCreated reason 2 (0x592c308) takes
        BoardAnalyzer.everyMatchIsSpecialsList, filled by its cctor 0x592d764
        as Column, Row, Column, Row, Bomb, Fireworks, and picks one with
        RandomWrapper.Range(0, Count) (0x3c12f6c). Every cascade, not only the
        player's own combo. The draw comes before the combo's own placement
        draw: Special O'Rama 2026-11-10 005->006, a cascade three's Column
        on its middle cell, exact only in this order.

        MakeSpecialSlotCreated 0x592c21c: only a player-initiated combo.
        WeightsRandomizer.SelectRandomItem 0x5b04b68: Next() % total weight, the
        first running total above it, in dictionary order.
        """
        if every_match:
            if not self.profile["rules"].get("everyMatchIsSpecial"):
                # Mutation Lab's MatchesCreateSpecials is reason 4, its own
                # odds list: not this one, so the special stays unknown.
                return None
            extra = decode_dictionary(self.profile["rules"].get("_extraData")) or {}
            if extra.get("allowSquareMatches"):
                # MakeSpecialSlotCreated 0x592c338..0x592c3bc: extraData.TryGetValue(
                # "allowSquareMatches") (literal 27200) && Convert.ToBoolean takes the
                # other static list (+0x28, with the Crosshair) -- not ported. Any
                # other key (Candy World's candy settings) keeps this list.
                raise UnsupportedRefill("Every match is special: square-match list not ported")
            engine = EVERY_MATCH_SPECIALS[self.rng.range(0, len(EVERY_MATCH_SPECIALS))]
            return ENGINE_SPECIAL_TO_SIM[engine]
        if not self.random_specials:
            return None
        roll = self.rng.next() % sum(weight for _, weight in self.random_specials)
        for special, weight in self.random_specials:
            roll -= weight
            if roll < 0:
                break
        if special in UNCOLORED_RANDOM_SPECIALS and self.balls is not None:
            self.balls.append((cell[0], cell[1], color_maps(self.profile)[0][sim_color]))
        return special

    def ball_spent(self, cell):
        """This ball fired; a ball falling onto its cell must not take its colour."""
        if self.balls is not None:
            self.balls = [ball for ball in self.balls if (ball[0], ball[1]) != tuple(cell)]

    def ball_colors_at(self, cells):
        """{cell: engine colour} of the balls now on these cells; None = unknown.

        A ball only falls and keeps its order in the column, so each cell, from
        the bottom, takes the lowest unused ball that started at or above it.
        Balls moved to another column by a swap take whatever is left.
        """
        if self.balls is None:
            return {}
        unused = sorted(self.balls, key=lambda ball: ball[0], reverse=True)
        colors, waiting = {}, []
        for row, col in sorted(cells, reverse=True):
            ball = next((b for b in unused if b[1] == col and b[0] <= row), None)
            if ball is None:
                waiting.append((row, col))
                continue
            unused.remove(ball)
            colors[row, col] = ball[2]
        for cell in waiting:
            if unused:
                colors[cell] = unused.pop(0)[2]
        self.balls = [(row, col, color) for (row, col), color in colors.items()]
        return colors

    def reset_action(self):
        """ResetChainComboReduction clears spawnedColors at the start of an action."""
        self.spawned_colors.clear()

    def peek_draws(self, count):
        """The next ``count`` draws, without consuming them."""
        rng = self.rng.clone()
        return [rng.next() for _ in range(count)]

    def fireworks_targets(self, board, ignore, amount, skip=0):
        """BoardModel.GetFireworks 0x5972068 -> GetSlotPrioritize 0x5972158.

        A Lightning (engine Fireworks) picks ``amount`` cells: the cells not in
        ``ignore`` (b__1: the cells already being destroyed), scanned x-major
        and shuffled (one draw each). Its draws follow the cascade's combo
        draws (``skip``) and precede the refill, which takes them afterwards
        (``pending_effect_draws``). The b__0 priority (slot +0x21) is not read:
        on a board of plain pieces every cell is in the same group. For a
        Sweep SE swipe, ignore=None models the occupied slots before clearing,
        including slots already marked for destruction (three Bullseye Bash
        replays: 154641/014, 154641/025, 161238/025).
        """
        rng = self.rng.clone()
        for _ in range(skip + self.pending_effect_draws):
            rng.next()
        before = rng.counter
        cells = self._where_order(board)
        if ignore is None:
            cells = [(row, col) for row, col in cells if board[row][col] > 0]
        else:
            ignored = {tuple(cell) for cell in ignore}
            cells = [cell for cell in cells if cell not in ignored]
        picks = rng.shuffled(cells)[:amount]
        self.pending_effect_draws += rng.counter - before
        return picks

    def crosshair_config(self):
        """additionalData.gemPickThreshold as (total, [(strategy, count), ...]), or None."""
        rules = (self.profile or {}).get("rules") or {}
        try:
            extra = decode_dictionary(rules.get("additionalData")) or {}
            raw = extra.get(CROSSHAIR_CONFIG_KEY)
            config = decode_dictionary(raw) if raw is not None else None
        except ValueError:
            return None     # not read in this capture
        if not config:
            return None
        order = [name.strip() for name in str(config.get("selectionOrder") or "").split(",") if name.strip()]
        try:
            total = int(config["maxTotalPieces"])
            strategies = [(name, int(config[name])) for name in order]
        except (KeyError, TypeError, ValueError) as exc:
            raise UnsupportedRefill(f"Crosshair: gemPickThreshold incomplete ({exc})") from exc
        # The selection strings are the dictionary keys the code looks counts up by.
        unknown = [name for name, _ in strategies if name not in CROSSHAIR_STRATEGIES]
        if unknown:
            raise UnsupportedRefill(f"Crosshair: unknown selection {unknown}")
        return total, strategies

    def crosshair_targets(self, board, special, source, ignore, skip=0):
        """BoardModel.GetCrosshair 0x59718d8 over the simulator board.

        ``total`` = maxTotalPieces cells, in ``selectionOrder``: each strategy
        takes up to its own count (min with what is still missing), then
        <GetCrosshair>b__3 fills from any free piece and b__4 from any piece
        not yet picked, cells already being destroyed included. Every pick is
        AddSelectedPieces 0x5978ef0 -> GetSlotPrioritize 0x5972158 with an
        always-false priority (b__111_1): the Where list (x-major) of
        canBeMatched pieces the condition does not exclude, shuffled (one draw
        each, none for fewer than two), first n taken. A strategy whose n is 0
        draws nothing. AddSelectedPieces first adds the picks so far to the
        caller's ignore list. Base exclusion b__0: in that list or not
        damageable. Strategies: maxEnergyPieces b__6/b__9 (colour in
        GameLogic.CurrentEnergyChargingColors: the current player's colour,
        simulator blue, when the mode has no colorEnergyOverride),
        maxMatchingColorPieces b__7/b__10 (MatchesWithSlot with the crosshair),
        maxClassicSpecialPieces b__5/b__8 (IsClassicSpecial). Draws are
        booked like a Lightning's (``pending_effect_draws``).
        """
        config = self.crosshair_config()
        if config is None:
            return None     # GetCrosshair logs an error here; the caller keeps its own model
        total, strategies = config
        rules = (self.profile or {}).get("rules") or {}
        try:
            override = decode_dictionary(rules.get("_colorEnergyOverride"))
        except ValueError as exc:
            raise UnsupportedRefill("Crosshair: colorEnergyOverride was not read") from exc
        if override:
            raise UnsupportedRefill("Crosshair: colorEnergyOverride charging colours are not ported")
        rng = self.rng.clone()
        for _ in range(skip + self.pending_effect_draws):
            rng.next()
        before = rng.counter
        source = tuple(source)
        crosshair_color = int(board[source[0]][source[1]])
        order = self._where_order(board)

        def piece(cell):
            # canBeMatched and damageable: a coloured piece, plain or a classic special.
            y, x = cell
            value = int(special[y][x])
            if int(board[y][x]) <= 0:
                return False
            if value and value not in SIM_CLASSIC_SPECIALS:
                raise UnsupportedRefill(f"Crosshair: special {value} flags are not ported")
            return True

        ignored = {tuple(cell) for cell in (ignore or ())}
        selected = []

        def add(amount, keep):
            ignored.update(selected)
            amount = min(amount, total - len(selected))
            if amount <= 0:
                return
            candidates = [cell for cell in order if piece(cell) and keep(cell)]
            for cell in rng.shuffled(candidates)[:amount]:
                if cell not in selected:
                    selected.append(cell)

        def free(cell):
            return cell not in ignored

        filters = {
            "maxEnergyPieces": lambda cell: int(board[cell[0]][cell[1]]) == SIM_BLUE,
            "maxMatchingColorPieces": lambda cell: int(board[cell[0]][cell[1]]) == crosshair_color,
            "maxClassicSpecialPieces": lambda cell: int(special[cell[0]][cell[1]]) in SIM_CLASSIC_SPECIALS,
        }
        for name, count in strategies:
            add(count, lambda cell, f=filters[name]: f(cell) and free(cell))
        add(total - len(selected), free)
        add(total - len(selected), lambda cell: cell not in selected)
        self.pending_effect_draws += rng.counter - before
        return selected

    def fill(self, board, chain_combos=0):
        """Return cloned raw slots and a per-hole audit, no mutation of input.

        ARM64: CountFillingSlots scans y then x; FillAllEmptySlots consumes
        four prevention rolls, fair sort keys and one color roll per hole.
        The ordered retry loop stops when its color list is exhausted, even
        if the final color still satisfies a prevention predicate.
        """
        slots = [[dict(s) if isinstance(s, dict) else {"color": int(s), "value": 0, "canBeMatched": True}
                  for s in row] for row in board]
        rows, columns = len(slots), len(slots[0])
        if rows != columns or rows < 4 or any(len(row) != columns for row in slots):
            raise UnsupportedRefill("Expected square board")
        spawning, config = self.profile["spawning"], self.profile["config"]["spawnEngine"]
        colors = spawning["gameColors"]
        weights = decode_dictionary(spawning["colorWeights"])
        counts = dict.fromkeys(colors, 0)
        holes = []
        for y, row in enumerate(slots):
            for x, slot in enumerate(row):
                color = slot["color"]
                if color == 0:
                    holes.append((x, y))
                elif color != 1:
                    counts[color] = counts.get(color, 0) + 1
        if any(color not in weights for color in counts):
            raise UnsupportedRefill("Color outside configured weight dictionary")
        thresholds = self.thresholds
        square = bool(spawning.get("<SquareMatchesAvailable>k__BackingField"))
        # Empirical, source not yet located: each combo destroyed in a cascade
        # (not the player's own match) is followed by one engine draw before
        # this refill. Recorded Square Solo, 2026-11-01: plain moves need 0,
        # one-combo cascades 1, a two-combo cascade (with a row special
        # activation) 2. ``chain_combos`` is that cascade's combo count. The
        # draw places the combo's special (move_strategy._created_special_cell).
        for _ in range(chain_combos):
            self.rng.next()
        # A Lightning's target shuffle came after those combo draws.
        for _ in range(self.pending_effect_draws):
            self.rng.next()
        self.pending_effect_draws = 0
        trace = []
        for x, y in holes:
            before = self.rng.counter
            flags = {name: self.rng.range(0, 100) <= thresholds[name]
                     for name in ("match", "combo", "special_combo", "square")}
            priority = get_colors_priority(counts, self.spawned_colors, self.rng, colors)
            cumulative = create_weights_list_new(priority, counts, weights, rows=rows, columns=columns,
                max_pool_size=config["colorPickmaxPoolSize"], max_pool_unit=config["colorPickMaxPoolUnit"])
            roll = self.rng.range(0, 100)
            color = pick_color(priority, cumulative, roll)
            attempts = [color]

            def assign(candidate):
                slots[y][x] = {"color": candidate, "color2": 1, "value": 0, "originalValue": 0,
                               "canBeMatched": True, "movable": True, "score": 1, "energy": 1}

            def retry():
                # CalculateWhileCondition 0x5a0a370 tests the rolls in the
                # order third, second, first, fourth. The thresholds come from
                # refillLogicOverride +0x14/+0x18/+0x1c/+0x20 (match, combo,
                # special combo, square), so "match" gates the possible
                # four-pattern and "special_combo" the formed 4+ combo.
                if flags["special_combo"] and combo_count_at(slots, x, y, square=square) > 3:
                    return True
                if flags["combo"] and is_part_of_combo(slots, x, y, square=square):
                    return True
                if flags["match"] and is_part_of_possible_highrank_combo(slots, x, y, 1):
                    return True
                return flags["square"] and is_part_of_possible_highrank_combo(slots, x, y, 2)

            assign(color)
            index = 0
            while index < len(priority) and retry():
                color = priority[index]
                index += 1
                attempts.append(color)
                assign(color)
            counts[color] += 1
            self.spawned_colors[color] = self.spawned_colors.get(color, 0) + 1
            trace.append({"x": x, "y": y, "priority": priority, "cumulative": cumulative,
                          "roll": roll, "attempts": attempts, "color": color,
                          "rng_before": before, "rng_after": self.rng.counter,
                          "exhausted": index == len(priority)})
        # SetScoreAndEnergyOverrides runs after filling all holes. Square
        # has scalar per-color scores, no modifier or energy override.
        score = decode_dictionary(self.profile["rules"].get("_colorScoreOverride")) or {}
        energy = decode_dictionary(self.profile["rules"].get("_colorEnergyOverride")) or {}
        for x, y in holes:
            color = slots[y][x]["color"]
            slots[y][x]["score"] = score.get(color, 1)
            slots[y][x]["energy"] = energy.get(color, 1)
        self._spawn_special_tiles(slots, holes, trace)
        rules = self.profile["rules"]
        if rules.get("boardModelName") == FIREWORKS_FESTIVAL_BOARD:
            settings = decode_dictionary(rules.get("_extraData")) or {}
            # Native RefillSlots rolls even when the board already has enough rockets.
            rolled = self.rng.chance(round(100 * float(settings.get("replenishChance", 1))))
            rockets = sum(slot["value"] == WANTED_VALUE for row in slots for slot in row)
            if rolled and holes and min(int(settings.get("replenishRate", 1)),
                                       int(settings.get("maxBoardSpecialTiles", 4)) - rockets) > 0:
                self.unported("Fireworks Festival: rocket conversion is not ported")
        if rules.get("boardModelName") == CANDY_WORLD_BOARD:
            settings = dict(CANDY_DEFAULTS)
            extra = decode_dictionary(rules.get("_extraData")) or {}
            settings.update({k: extra[k] for k in CANDY_DEFAULTS if k in extra})
            # get_ReplenishChance is a float: 100f * chance rounded (Math.Round, to even).
            if self.rng.chance(int(round(100 * float(settings["replenishChance"])))):
                self._convert_candies(slots, trace, settings)
        if rules.get("boardModelName") == JUNGLE_RUMBLE_BOARD:
            settings = decode_dictionary(rules.get("_extraData")) or {}
            frequency = int(settings.get("leafFrequency", 50))
            leaf_score = int(settings.get("leafScore", 2))
            # JungleRumbleBoard.RefillSlots calls CreateLeaves after the base
            # refill. Each newly filled green slot gets one Chance roll.
            for item in trace:
                slot = slots[item["y"]][item["x"]]
                if slot["color"] == 3 and self.rng.chance(frequency):
                    slot.update(value=WANTED_VALUE, score=leaf_score)
                    item["special_value"] = WANTED_VALUE
        return slots, trace

    def _convert_candies(self, slots, trace, settings):
        """CandyWorldBoard.RefillSlots 0x597dc40 after the roll, + ConvertSlots 0x597d8bc.

        Candies on the board: Where(value == SpecialTileValue). The refilled
        points that are not a candy are the available list (FindIndex over the
        candies, b__13_1). Missing = MaxBoardSpecialTiles - candies; with one
        missing and one available, ConvertSlots(min(rate, missing, available)).
        ConvertSlots: GetSlotPrioritize 0x5972158 with priority b__14_0 always
        false (x-major scan, shuffled, one draw per candidate) and exclusion
        b__14_1: a special slot, a point outside the available list, or a colour
        outside BOARD_SPECIAL_COLORS (blue, red). Each pick becomes a candy:
        value 16, color2 the other colour of the pair.
        """
        candy_columns = {x for row in slots for x, slot in enumerate(row)
                         if slot.get("value") == WANTED_VALUE}
        candies = sum(slot.get("value") == WANTED_VALUE for row in slots for slot in row)
        missing = int(settings["maxBoardSpecialTiles"]) - candies
        # b__13_1 0x597ec2c compares only the low word of the Point (its x):
        # a refilled slot in a column that already holds a candy is not
        # available. 20261113_123727 015->016: exact only this way (the game
        # left out the refilled blue under the red candy in column 3).
        available = []
        for item in trace:
            point = (item["y"], item["x"])
            if item["x"] not in candy_columns and point not in available:
                available.append(point)
        if missing <= 0 or not available:
            return
        amount = min(int(settings["replenishRate"]), missing, len(available))
        sim_to_engine = color_maps(self.profile)[0]
        if any(color not in sim_to_engine for color in CANDY_COLORS):
            self.unported("Candy World: blue/red missing from the colour map")
            return
        pair = [sim_to_engine[color] for color in CANDY_COLORS]
        wanted = set(available)
        candidates = [(y, x) for y, x in self._where_order(slots)
                      if (y, x) in wanted and not slots[y][x].get("value")
                      and slots[y][x]["color"] in pair]
        by_point = {(item["y"], item["x"]): item for item in trace}
        for y, x in self.rng.shuffled(candidates)[:amount]:
            slot = slots[y][x]
            slot.update(value=WANTED_VALUE,
                        color2=pair[1] if slot["color"] == pair[0] else pair[0])
            item = by_point.get((y, x))
            if item is not None:
                item["special_value"] = WANTED_VALUE
                item["sim_special"] = SIM_RED_BLUE_TILE

    def _spawn_special_tiles(self, slots, holes, trace):
        """ProcessSpecialTile/ConvertSlots: Rainbow Hearts, Hot Color Bombs, Mighty Mushrooms.

        Evidence: simulator_core ARM64 0x5a05550, 0x5a05a7c,
        BoardModel.GetConvertPoints 0x5974140 / GetSlotPrioritize 0x5972158.
        Conversion is limited to newly filled ordinary non-player colors;
        candidates are scanned x-major, shuffled, then chance-tested.
        """
        data = decode_dictionary(self.profile["spawning"].get("specialTilesData")) or {}
        # RandomSpawnSpecialSlots 0x5a04c2c shuffles the tile types with the
        # game RNG (ArrayExtensions.Shuffle 0x3c137a0, one draw per type, none
        # for a single type) and runs ProcessSpecialTile on each in that
        # order. Mighty Mushrooms (mushroom 19 + bomb 6): 29 of 30 recorded
        # moves exact, 0 without the shuffle (Debug/research
        # 20261107_155618_mighty-mushrooms).
        for value, raw_config in self.rng.shuffled(list(data.items())):
            if value in self.skipped_special_tiles:
                continue    # approximate model: this tile type is not ported
            self._spawn_special_tile(slots, holes, trace, value, decode_dictionary(raw_config))

    def _spawn_special_tile(self, slots, holes, trace, value, config):
        config.setdefault("minGuaranteedPieces", 0)
        current = sum(slot.get("value", 0) == value for row in slots for slot in row)
        amount = min(config["refillSpawn"], config["maxSpawn"] - current)
        if amount <= 0:
            return
        minimum = max(0, config["minGuaranteedPieces"] - current)
        ignored = decode_dictionary(self.profile["spawning"].get("spawnColorsToIgnore")) or {}
        # Color Crystals (board 16): every special tile skips the players'
        # colours, also the bomb whose config omits the flag. 2026-11-10
        # Solo: 9 of 9 misses exact with it (the shuffle drew one candidate
        # fewer); Bombs Away Studio's bombs drop from 72 to 10 exact without
        # the board check, so it is not the default.
        # Zany Zappers (board 33) does the same for its zappers: refill_misses
        # 2026-11-11 143601 exact with it (RNG one draw ahead without), 143528
        # from +17 to +5 draws.
        exclude = (config.get("excludePlayersColorOnRefill")
                   or self.profile["rules"].get("boardModelName") in (COLOR_CRYSTALS_BOARD,
                                                                       ZANY_ZAPPERS_BOARD))
        excluded = set(ignored.get(self.profile["state"]["currentPlayerIndex"], [])) if exclude else set()
        candidates = [(x, y) for x, y in sorted(holes)
                      if slots[y][x].get("value", 0) == 0 and slots[y][x]["color"] not in excluded]
        if self.profile["rules"].get("boardModelName") == ZANY_ZAPPERS_BOARD:
            # ZanyZappersBoard.GetConvertPoints 0x59c9664: allowed colours,
            # then <>c.b__13_1 0x59c99c4 (point.y < 4, MAX_ROW_FILL), then
            # Intersect(availablePoints, ...), which keeps the order of the
            # refill's hole list: row by row, not the x-major board scan.
            # refill_misses 2026-11-11: without the row filter the shuffle drew
            # one key per lower-row candidate too (game 1-3 draws short); with
            # it and x-major 7 of 32 exact, row by row 23 of 32.
            candidates = sorted(((x, y) for x, y in candidates if y < ZANY_ZAPPERS_MAX_ROW_FILL),
                                key=lambda cell: (cell[1], cell[0]))
        if self.profile["rules"].get("boardModelName") in MUSHROOM_BOARDS:
            # MultiplierMushroomsBoard.IgnorePosition 0x59bd204: no side columns,
            # no bottom row, only the colours its ctor 0x59bb1b0 lists. Each
            # candidate is one shuffle draw, so this also moves the RNG.
            rows, columns = len(slots), len(slots[0])
            candidates = [(x, y) for x, y in candidates
                          if 0 < x < columns - 1 and y < rows - 1 and slots[y][x]["color"] in MUSHROOM_COLORS]
        if int(value) == PIRATE_CHEST:
            # Plunder Pirates' chest rolls spawnChance once, before choosing a
            # cell, and the shuffle only follows a hit (research
            # 20261107_233829 008->009: one draw for 3 candidates, no chest;
            # refill_misses 20261109_192641: one draw, chest on the only hole).
            if not candidates or not self.rng.chance(config["spawnChance"]):
                return
            for x, y in self.rng.shuffled(candidates)[:amount]:
                slots[y][x]["value"] = value
                current += 1
                next(item for item in trace if item["x"] == x and item["y"] == y)["special_value"] = value
            return
        selected = self.rng.shuffled(candidates)[:max(amount, minimum)]
        for x, y in selected:
            if current >= config["minGuaranteedPieces"] and not self.rng.chance(config["spawnChance"]):
                continue
            if int(value) == ZANY_ZAPPER:
                # A spawned Zany Zapper takes one more draw of its own (its
                # piece logic on conversion). Funky Tiles master league
                # 2026-11-07: every spawned zapper +1, none for a refused one;
                # with it 24 of 25 recorded moves exact, 16 without.
                self.rng.next()
            slots[y][x]["value"] = value
            current += 1
            next(item for item in trace if item["x"] == x and item["y"] == y)["special_value"] = value


# Unpermuted adapter colors (board_source._SLOT_COLOR_TO_BOARD for 2..8),
# i.e. the local player is engine Blue. color_maps() applies the same
# player-relative permutation board_source used when the capture was adapted.
# Disco (99 / SlotColor.All) and blockers have no ported refill semantics.
SIM_TO_ENGINE = {0: 0, 1: 4, 2: 3, 3: 5, 4: 7, 5: 2, 6: 6, 7: 8}
ENGINE_TO_SIM = {value: key for key, value in SIM_TO_ENGINE.items()}


def color_maps(profile):
    """(simulator -> engine, engine -> simulator) colors for this capture's players."""
    import board_source

    players = [{"index": (p.get("model") or {}).get("index"), "slot_type": (p.get("model") or {}).get("slotType"),
                "player_type": p.get("player_type")} for p in profile.get("players", [])]
    swap = board_source._player_color_swap_for({"players": players})
    engine_to_sim = {engine: ENGINE_TO_SIM[swap.get(engine, engine)] for engine in ENGINE_TO_SIM}
    return {sim: engine for engine, sim in engine_to_sim.items()}, engine_to_sim
# Simulator special -> engine SlotValue: Row, Column, Bomb, Lightning, the
# Color Crystal, the mushroom, and the Square Match crosshair (board_source maps
# engine 8 to SPECIAL_CROSSHAIR).
SIM_SPECIAL_TO_ENGINE = {0: 0, 1: 5, 2: 4, 3: 6, 4: 7, 11: 23, 15: 18, 17: 19, 20: 40, 46: 8,
                         # MonkeyJoojooPiece: Arcade Man spawns it as a special tile.
                         19: 24}
# Zany Zapper (SlotValue 17): the simulator splits it by hit points, 26 with
# two left and 25 with one (board_source). Both are one engine value; a
# freshly spawned one has two (Funky Tiles master league, 2026-11-07).
SIM_SPECIAL_TO_ENGINE.update({25: 17, 26: 17})
ENGINE_SPECIAL_TO_SIM = {engine: sim for sim, engine in SIM_SPECIAL_TO_ENGINE.items()}
ENGINE_SPECIAL_TO_SIM[17] = 26
# Plunder Pirates' PirateChestPiece (SlotValue 20): the adapter shows it as the
# CHEST board value under SPECIAL_MODE_TARGET. Only this direction is global;
# a simulator 9 is converted back only when it sits on a CHEST.
PIRATE_CHEST = 20
SIM_CHEST, SIM_MODE_TARGET = 8, 9
ENGINE_SPECIAL_TO_SIM[PIRATE_CHEST] = SIM_MODE_TARGET
SIM_DISCO_BALL = 16
BROCCO_PIECE = 28
# Vinnie SE two-colour hearts: simulator specials 30..44, one per colour pair
# (move_strategy.VINNIE_SE_HEART_COLOR_PAIRS); the engine keeps them as CupidHeart.
CUPID_HEART = 23
VINNIE_SE_HEART_FIRST, VINNIE_SE_HEART_LAST = 30, 44


def _is_purple_gem(value):
    from move_strategy import is_purple_gem_special
    return is_purple_gem_special(value)


def _gem_base():
    from move_strategy import SPECIAL_PURPLE_GEM_VALUE_BASE
    return SPECIAL_PURPLE_GEM_VALUE_BASE


def _vinnie_se_heart_pair(value):
    from move_strategy import vinnie_se_heart_colors
    return vinnie_se_heart_colors(value)


def fill_simulator_board(model, board, special, chain_combos=0):
    """Fill the simulator board's holes; inputs (lists or numpy) are not mutated."""
    sim_to_engine, engine_to_sim = color_maps(model.profile)
    random_specials = bool(getattr(model, "random_specials", ()))
    uncolored = (UNCOLORED_RANDOM_SPECIALS if random_specials
                 else {SIM_DISCO_BALL: BROCCO_PIECE, SIM_CLEO: ENGINE_CLEO,
                       SIM_SWEEP_BROOM: ENGINE_SWEEP_BROOM, SIM_SPRAY_CAN: ENGINE_SPRAY_CAN})
    colored = COLORED_RANDOM_SPECIALS if random_specials else {}
    approximate = getattr(model, "approximate", None)
    fireworks = model.profile["rules"].get("boardModelName") == FIREWORKS_FESTIVAL_BOARD
    if fireworks:
        from board_source import _FIREWORK_STATUS_TO_SPECIAL
        rocket_status = {special: status for status, special in _FIREWORK_STATUS_TO_SPECIAL.items()}
    balls = [(y, x) for y, row in enumerate(special) for x, value in enumerate(row) if int(value) in uncolored]
    ball_colors = model.ball_colors_at(balls) if balls else {}
    raw = []
    for y, row in enumerate(board):
        converted = []
        for x, color in enumerate(row):
            color, value = int(color), int(special[y][x])
            if value in uncolored:
                # A Foxy or Cleo whose colour nobody read must not guess the counts.
                if value != SIM_DISCO_BALL and (y, x) not in ball_colors:
                    if approximate is None:
                        raise UnsupportedRefill("Random special: raw slot colour missing from recording")
                    if "Random special: raw slot colour missing" not in approximate:
                        approximate.append("Random special: raw slot colour missing")
                converted.append({"color": ball_colors.get((y, x), 1), "value": uncolored[value],
                                  "canBeMatched": False, "color2": 1})
                continue
            if value in colored and color in sim_to_engine:
                converted.append({"color": sim_to_engine[color], "value": colored[value],
                                  "canBeMatched": True, "color2": 1})
                continue
            if color == -1 and value == 14:
                if model.billie is None:
                    if approximate is None:
                        raise UnsupportedRefill("Billie: raw drone colour and passive configuration required")
                    if "Billie: raw drone colour unknown" not in approximate:
                        approximate.append("Billie: raw drone colour unknown")
                    converted.append({"color": 1, "value": 25, "canBeMatched": False, "color2": 1,
                                      "movable": True})
                    continue
                # ConvertBillieBoomPiece clones the original slot and retains
                # its primary colour (0x5a13300); it still affects spawn counts.
                converted.append({"color": model.billie.drone_color, "value": 25,
                                  "canBeMatched": False, "color2": 1, "movable": True})
                continue
            if fireworks and value in rocket_status and color in sim_to_engine:
                converted.append({"color": sim_to_engine[color], "value": WANTED_VALUE,
                                  "status": rocket_status[value], "canBeMatched": True, "color2": 1})
                continue
            if (value == SIM_MODE_TARGET and color in sim_to_engine
                    and model.profile["rules"].get("boardModelName") in
                    (DUSTVILLE_BOARD, JUNGLE_RUMBLE_BOARD)):
                # Dustville wanted figures and Jungle Jam leaves are matchable
                # coloured board specials. Their collection rules differ.
                converted.append({"color": sim_to_engine[color], "value": WANTED_VALUE,
                                  "canBeMatched": True, "color2": 1})
                continue
            if color == SIM_CHEST and value == SIM_MODE_TARGET:
                # Pirate chest: colourless (raw colour 1), unmatchable, falls.
                converted.append({"color": 1, "value": PIRATE_CHEST, "canBeMatched": False,
                                  "color2": 1, "movable": True})
                continue
            if color == -1 and value == 20:
                # Froggy lotus: an uncolored, fixed obstacle while ordinary
                # swipes resolve. Collecting the lotus is a separate action.
                converted.append({"color": 1, "value": 40, "canBeMatched": False, "color2": 1})
                continue
            if VINNIE_SE_HEART_FIRST <= value <= VINNIE_SE_HEART_LAST:
                # Vinnie SE's two-colour heart is a CupidHeart (SlotValue 23):
                # SlotModel.color is the colour on the board, color2 the other
                # of the pair (board_source._heart_special reads it the same
                # way). It falls and counts for spawning like any tile.
                pair = _vinnie_se_heart_pair(value)
                if color not in pair or any(c not in sim_to_engine for c in pair):
                    raise UnsupportedRefill("Vinnie SE heart: board colour outside its pair")
                second = pair[1] if color == pair[0] else pair[0]
                converted.append({"color": sim_to_engine[color], "value": CUPID_HEART,
                                  "canBeMatched": True, "color2": sim_to_engine[second]})
                continue
            if (model.profile["rules"].get("boardModelName") == CRYSTAL_CAVE_BOARD
                    and _is_purple_gem(value) and color in sim_to_engine):
                # Gem Grab crystal: BoardSpecial on its purple piece, its number
                # in SlotModel.score. It falls and counts for spawning.
                converted.append({"color": sim_to_engine[color], "value": WANTED_VALUE,
                                  "canBeMatched": True, "color2": 1,
                                  "score": value - _gem_base()})
                continue
            if value == SIM_RED_BLUE_TILE and color in CANDY_COLORS and all(c in sim_to_engine for c in CANDY_COLORS):
                # Candy World candy: BoardSpecial on its colour, the other of
                # the blue/red pair in color2. It falls and counts like a tile.
                second = CANDY_COLORS[1] if color == CANDY_COLORS[0] else CANDY_COLORS[0]
                converted.append({"color": sim_to_engine[color], "value": WANTED_VALUE,
                                  "canBeMatched": True, "color2": sim_to_engine[second]})
                continue
            if color not in sim_to_engine or value not in SIM_SPECIAL_TO_ENGINE:
                if approximate is None:
                    raise UnsupportedRefill("Unported simulator special/color in refill board")
                note = f"Unported simulator special/color in refill board (special {value}, colour {color})"
                if note not in approximate:
                    approximate.append(note)
                if color in sim_to_engine:
                    # Nearest ported piece: a plain piece of the same colour.
                    converted.append({"color": sim_to_engine[color], "value": 0,
                                      "canBeMatched": True, "color2": 1})
                else:
                    # No colour: a colourless piece the spawn counts skip.
                    converted.append({"color": 1, "value": 40, "canBeMatched": False, "color2": 1})
                continue
            converted.append({"color": sim_to_engine[color], "value": SIM_SPECIAL_TO_ENGINE[value],
                              "canBeMatched": True, "color2": 1})
        raw.append(converted)
    _, trace = model.fill(raw, chain_combos)
    out, specials = copy.deepcopy(board), copy.deepcopy(special)
    for item in trace:
        x, y = item["x"], item["y"]
        out[y][x] = engine_to_sim[item["color"]]
        value = item.get("special_value", 0)
        if "sim_special" in item:
            specials[y][x] = item["sim_special"]
        else:
            specials[y][x] = (SIM_MODE_TARGET if value == WANTED_VALUE
                              else ENGINE_SPECIAL_TO_SIM[value])
        if item.get("special_value") == PIRATE_CHEST:
            out[y][x] = SIM_CHEST
    return out, specials, trace


def simulator_refill(model, trace_sink=None):
    """Callback for move_strategy.engine_refill_active.

    Every RefillSlots call of one action shares ``model`` (RNG and
    spawnedColors); call ``model.reset_action()`` before each new action.
    """
    def refill(board, special, chain_combos=0):
        out, specials, trace = fill_simulator_board(model, board, special, chain_combos)
        if trace_sink is not None:
            trace_sink.append(trace)
        return out, specials
    return refill


def _rows(board):
    return [[int(v) for v in row] for row in board]


# How many moves past the played one are simulated with the exact refill.
MAX_FOLLOWED_PLIES = 3


def _board_key(board):
    return tuple(map(tuple, np.asarray(board, dtype=np.int64).tolist()))


class ExactRefillSession:
    """The ordinary ranking's view of the drop, through the moves it looks ahead.

    Every candidate on the played board starts from the live RNG; a candidate
    on a board some simulated move ended on continues from that move's RNG. A
    refill the port cannot do leaves the holes empty, which is exactly how the
    ranking behaves without this session, and ends the line it was on.

    ``hot``: Hot Color's (current, next) simulator colours. onMoveEnd rotates
    them with two draws when the move cleared the current colour; the colour
    after ``next`` is one of those draws, so a line past it stops being followed.
    ``follow_moves`` is False with other players on the board: their moves
    consume the same RNG.
    """

    def __init__(self, model, board, follow_moves=True, hot=None, max_plies=MAX_FOLLOWED_PLIES, special_board=None):
        self.use_special_keys = special_board is not None
        self.states = {self._key(board, special_board): (model, hot, 0)}
        self.follow_moves = follow_moves
        self.max_plies = max_plies
        self.blue_missing = 99      # what the booster can still take
        self.joojoo_target = 0

        self.current = None
        self.hot = None
        self.ply = 0
        self.line_broken = False
        self.simulations = 0
        self.successful = 0
        self.fallbacks = 0
        self.followed = 0
        self.failure = None
        # APPROXIMATE_REFILL: an unported fill is redone approximately instead
        # of leaving the holes empty. ``approximated`` counts such moves and
        # ``approximation`` keeps the first reason, for the GUI.
        self.approximate_fallback = True
        self.approximated = 0
        self.approximation = getattr(model, "approximate", None) and model.approximate[0] or None

    def _key(self, board, special=None):
        return (_board_key(board), _board_key(special)) if self.use_special_keys else _board_key(board)

    def knows(self, board, special=None) -> bool:
        if self.use_special_keys and special is None:
            return False
        return self._key(board, special) in self.states

    def begin(self, board, special=None) -> bool:
        if self.use_special_keys and special is None:
            return False
        state = self.states.get(self._key(board, special))
        if state is None:
            return False
        self.current = state[0].clone()
        self.hot = state[1]
        self.ply = state[2]
        # Monkey JooJoo: a resting board holds every skull the throws allow.
        self.joojoo_target = joojoo_skull_count(special)
        self.current.reset_action()
        self.line_broken = False
        self.simulations += 1
        return True

    def peek_draws(self, count):
        return self.current.peek_draws(count)

    def ball_spent(self, cell):
        self.current.ball_spent(cell)

    def random_special(self, cell, sim_color, every_match=False):
        return self.current.random_special(cell, sim_color, every_match=every_match)

    def wanted_shots(self, board, special, prevent):
        return self.current.wanted_shots(board, special, prevent)

    def fireworks_targets(self, board, ignore, amount, skip=0):
        return self.current.fireworks_targets(board, ignore, amount, skip)

    def crosshair_targets(self, board, special, source, ignore, skip=0):
        return self.current.crosshair_targets(board, special, source, ignore, skip)

    def cleo_swap(self, candidate, **kwargs):
        from engine_cleo_simulation import simulate_swipe
        if self.ply:
            raise UnsupportedRefill("Cleo: raw slot flags/use counter unavailable on a followed board")
        return simulate_swipe(self.current, candidate, **kwargs)

    def cleo_odds_params(self):
        """What the plain Cleo ranking may know for sure about this board.

        Only the board the live capture describes: a followed board has moved
        the figure and the columns. Each figure's own values are looked up from
        this profile (engine_cleo_odds.figure_params).
        """
        if self.ply or self.current is None:
            return None
        profile = getattr(self.current, "profile", None)
        return {"profile": profile} if profile else None

    def refill(self, board, special, chain_combos=0):
        """An unported branch does not end the line: the same fill is redone
        from the same RNG as the approximate fallback (APPROXIMATE_REFILL)."""
        before = None
        if self.approximate_fallback and hasattr(self.current, "approximate_clone"):
            before = self.current.clone()
        try:
            out, specials, _ = fill_simulator_board(self.current, board, special, chain_combos)
        except UnsupportedRefill as exc:
            if before is None:
                self.failure = f"{type(exc).__name__}: {exc}"
                self.line_broken = True
                return board, special
            self.current = before.approximate_clone()
            self.current.unported(str(exc))
            try:
                out, specials, _ = fill_simulator_board(self.current, board, special, chain_combos)
            except Exception as again:
                self.failure = f"{type(again).__name__}: {again}"
                self.line_broken = True
                return board, special
        except Exception as exc:
            self.failure = f"{type(exc).__name__}: {exc}"
            self.line_broken = True
            return board, special
        return out, specials

    def approximation_reason(self):
        """Why the last line was approximate, or None when it was exact."""
        notes = getattr(self.current, "approximate", None) if self.current is not None else None
        return notes[0] if notes else None

    def finish(self, result, *, follow=True):
        """Remember the RNG the board this move ended on continues from."""
        if result is not None:
            events = getattr(result, "intent_events", ())
            if getattr(result, "cleo_scenario_count", 0):
                self.failure = "Cleo: probability scenarios are not an exact action"
                self.line_broken = True
            if getattr(self.current, "mixy_redealt", False):
                # engine_mixy: a re-deal without its config in the snapshot.
                self.failure = "Mixy code match: the re-deal is not predictable here"
                self.line_broken = True
            if any("random_outcomes" in e.get("type", "")
                   or e.get("type") == "uncertain_refill_boundary"
                   or (e.get("type") == "special_activation"
                       and not e.get("exact_targets")
                       and (e.get("special") in ("lightning", "crosshair", "all_aboard_bandit")
                            or (self.current.random_specials
                                and e.get("special") in ("cleo_bug", "spray_se", "joojoo_skull"))))
                   for e in events):
                self.line_broken = True
            # Dustville: a cascade special's timing is not ported (strategy_lab.simulation.step).
            if is_dustville(self.current) and any(
                    e.get("type") in ("special_activation", "dustville_wanted_shots")
                    and e.get("cascade", 0) > 1 for e in events):
                self.failure = "Dustville: cascade special timing is not ported"
                self.line_broken = True
            rules = getattr(self.current, "profile", {}).get("rules") or {}
            if (rules.get("boardModelName") == FIREWORKS_FESTIVAL_BOARD
                    and fireworks_rocket_fired(events)):
                self.failure = "Fireworks Festival: rocket activation is not ported"
                self.line_broken = True
            if spray_five_unported(events, getattr(self.current, "profile", None)):
                self.failure = "Foxy Roxy SE: a five from the spray is not ported"
                self.line_broken = True
            if rainbow_cascade_unported(getattr(self.current, "profile", {}), events):
                self.failure = "Rainbow cascade rocket/bomb timing is not ported"
                self.line_broken = True
        if result is not None and not self.line_broken and getattr(self.current, "mixy", None) is not None:
            # Mixy use #1: RandomizeActiveColors, the swipe's last draws.
            from engine_mixy import finish_swipe
            finish_swipe(self.current, result.board)
        if result is not None and not self.line_broken and getattr(self.current, "billie", None) is not None:
            from engine_billie import finish_passive
            try:
                finish_passive(self.current, result)
            except UnsupportedRefill as exc:
                self.failure = str(exc)
                self.line_broken = True
        approximate = (result is not None and not self.line_broken
                       and bool(getattr(self.current, "approximate", None)))
        if result is not None:
            result.exact_refill_supported = not self.line_broken and not approximate
            result.refill_approximate = approximate
            if self.line_broken:
                self.fallbacks += 1
            elif approximate:
                self.approximated += 1
                self.approximation = self.approximation or self.approximation_reason()
                # A board reached through a guessed drop is not followed.
                return
            else:
                self.successful += 1
        # With other players on the board their moves use the same RNG -- but
        # not before a move that keeps our turn: its board is ours to play next.
        keeps_turn = result is not None and getattr(result, "extra_moves", 0) > 0
        if (not follow or result is None or not (self.follow_moves or keeps_turn) or self.line_broken
                or self.ply >= self.max_plies):
            return
        # Jelly SE: a conversion spends the zone (or renews it with draws that
        # are not ported), so the board after it is not followed.
        if getattr(self, "jelly_cells", None) and any(
                e.get("type") == "jelly_zone_conversion" for e in getattr(result, "intent_events", ()) or ()):
            return
        # A fired Funky marker moves before the next move (funky_relocate):
        # one draw per interior cell and new marker cells the ranking's fixed
        # funky overlay does not know. This move is exact; the board after it
        # is not followed.
        if any(e.get("type") == "funky_tile_activation"
               for e in getattr(result, "intent_events", ()) or ()):
            return
        special = getattr(result, "special_board", None)
        profile = getattr(self.current, "profile", None)
        if joojoo_passive(profile) and joojoo_skull_count(special) < getattr(self, "joojoo_target", 0):
            if not joojoo_refill_ported(profile) or special is None:
                # Outside Solo the matchable chance is not recorded: this move
                # is exact, the board after it is not followed.
                return
            # Skulls that exploded come back before Hot Color's two draws
            # (research 20261112_001019, 9 of 9 moves).
            special = self.current.joojoo_end_move(result.board, special, self.joojoo_target)
        hot = self.hot
        if hot is not None:
            if hot[0] is None:
                return
            if result.cleared_color_counts.get(hot[0]):
                self.current.rng.next()
                self.current.rng.next()
                hot = (hot[1], None)
        if (special is not None and is_dustville(self.current)
                and (not keeps_turn or rules.get("pvpMode") == 1)):
            # Solo replenishes Wanted after extra moves too.
            special = self.current.wanted_turn_start(result.board, special)
        self.states.setdefault(self._key(result.board, special), (self.current, hot, self.ply + 1))
        self.followed += 1


# The name from when only Square Match Solo was ported.
SquareRefill = EngineRefill
