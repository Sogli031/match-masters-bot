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
COLORED_RANDOM_SPECIALS = {18: 29, 11: 23, 19: 24}
# Colourless pieces whose raw colour still counts for spawning in any mode. A
# Cleo keeps the slot's colour (dump_board "color"), and it sits on the board in
# every Cleo booster match, not just where Match & Hatch hatches one.
ENGINE_BALL_VALUES = (26, 28, 32, 38)
SIM_CLEO = 13
ENGINE_CLEO = 32


# DustvilleDuelBoard (boardModelName 4). Wanted figure = SlotValue 16 on an orange
# piece (convertToWanted b__26_1 0x59865f4: plain, not wanted, MatchesWithColor(6)).
DUSTVILLE_BOARD = 4
WANTED_VALUE = 16
WANTED_COLOR = 6        # engine Orange
# Getter fallbacks when extraData has no key (get_* 0x59853a8..0x59858d0).
DUSTVILLE_DEFAULTS = {"wantedTilesCount": 2, "scoreBonusPerHit": 4, "wantedShoots": 4,
                      "minBluesToPick": 4, "chanceToPickBlue": 0, "replenishRate": 1,
                      "replenishChance": 0.0}
DUSTVILLE_NEUTRALS = (6, 3, 5, 7)   # GetAreaOfBluesAndRedsByMinAndChances colour list
SIM_BLUE, SIM_RED = 1, 5


def is_dustville(model) -> bool:
    """A refill model of a Dustville Duel board (test doubles have no config)."""
    config = getattr(model, "dustville_config", None)
    return config is not None and config() is not None


def rainbow_cascade_unported(rules_id, events) -> bool:
    return rules_id == "rainbow" and any(
        event.get("type") == "special_activation"
        and event.get("cascade", 0) > 1
        and event.get("special") in ("horizontal", "vertical", "bomb")
        for event in events
    )


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
    # The swipe re-dealt the Mixy code (use #1): not ported, see engine_mixy.
    mixy_redealt: bool = False

    @classmethod
    def from_profile(cls, profile, *, seed=None, resume=False, thresholds=None):
        if thresholds is None:
            resolved = resolve_refill_overrides(profile)
            if not resolved.get("resolved"):
                raise UnsupportedRefill("Adaptive thresholds need a complete Versus profile or "
                                        "an explicit hypothesis")
            thresholds = resolved["prevention_thresholds"]
        config = profile["config"]["spawnEngine"]
        spawning = profile["spawning"]
        if not config.get("newColorPickLogic"):
            raise UnsupportedRefill("Legacy createWeightsList is not the captured branch")
        if spawning.get("<ForceNextCombo>k__BackingField") or spawning.get("<ForceBlueCombo>k__BackingField"):
            raise UnsupportedRefill("Forced-combo spawning requires its separate algorithm")
        special_data = decode_dictionary(spawning.get("specialTilesData")) or {}
        # ProcessSpecialTile is the same for any one tile type; checked on
        # Rainbow Hearts and Hot Color Bombs. Several types run one after the
        # other in the dictionary's order (Mighty Mushrooms: 19 then 6).
        if any(value not in ENGINE_SPECIAL_TO_SIM for value in special_data):
            raise UnsupportedRefill("Special tile spawning is not ported for this configuration: "
                                    f"tile values {sorted(special_data, key=str)}")
        for raw_tile in special_data.values():
            tile = decode_dictionary(raw_tile)
            supported_keys = {"excludePlayersColorOnRefill", "initialSpawn", "refillSpawn", "maxSpawn",
                              "spawnChance", "minGuaranteedPieces", "replenishRate", "replenishAtTurn"}
            # Plunder Pirates' chest config has no minGuaranteedPieces: the
            # engine field then keeps its default 0.
            tile.setdefault("minGuaranteedPieces", 0)
            required = {"refillSpawn", "maxSpawn", "spawnChance", "minGuaranteedPieces"}
            # replenishAtTurn -1 = never; another value is a turn-based branch.
            if tile.get("replenishAtTurn", -1) != -1:
                raise UnsupportedRefill("Special tile replenishAtTurn is not ported")
            if (not required <= tile.keys() or tile.keys() - supported_keys
                    or any(not isinstance(tile[k], int) or tile[k] < 0 for k in required)
                    or tile["spawnChance"] > 100 or tile["minGuaranteedPieces"] > tile["maxSpawn"]):
                raise UnsupportedRefill("Special tile config is outside the ported refill branch")
        random_specials = _random_special_table(profile["rules"])
        # GetRandomSpecialPiece 0x59ded68 caches its randomizer here on first use,
        # so a filled field over the same weights is not another configuration.
        randomizer = profile["rules"].get("weightsRandomizer")
        if randomizer is not None:
            cached = decode_dictionary(randomizer.get("_weights")) or {}
            table = {RANDOM_SPECIAL_NAMES.get(name): int(weight) for name, weight in cached.items() if int(weight) > 0}
            if not random_specials or table != dict(random_specials):
                raise UnsupportedRefill("WeightsRandomizer is not empty")
        # RandomSpawnLiveEventPieces returns before any draw when its chance
        # table is null; which table GameLogic picks depends on the mode.
        if any(config.get(k) is not None for k in (
                "liveEventPieceChancesBySpawnedSolo", "liveEventPieceChancesBySpawned",
                "liveEventPieceChancesBySpawnedRumbleParty", "liveEventPieceChancesBySpawnedShowdown")):
            raise UnsupportedRefill("Live event spawning is configured")
        local = [p for p in profile.get("players", []) if p.get("player_type") == 0]
        if len(local) != 1:
            raise UnsupportedRefill("Simulator color bridge needs exactly one local player")
        rng = EngineRNG.from_capture(profile) if seed is None else EngineRNG.from_seed(seed)
        spawned = decode_dictionary(spawning.get("spawnedColors")) or {} if resume else {}
        balls = profile.get("ball_slots")
        balls = None if balls is None else [(s["row"], s["col"], s["color"]) for s in balls
                                            if random_specials or s.get("value", 28) in ENGINE_BALL_VALUES]
        return cls(profile, rng, spawned, dict(thresholds), balls=balls, random_specials=random_specials)

    def clone(self):
        return type(self)(self.profile, self.rng.clone(), dict(self.spawned_colors), self.thresholds, self.billie,
                          None if self.balls is None else list(self.balls), self.random_specials,
                          self.mixy, self.mixy_redealt)

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

    def random_special(self, cell, sim_color):
        """The special this player combo hatches into, or None outside the rule.

        MakeSpecialSlotCreated 0x592c21c: only a player-initiated combo.
        WeightsRandomizer.SelectRandomItem 0x5b04b68: Next() % total weight, the
        first running total above it, in dictionary order.
        """
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
        return slots, trace

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
            self._spawn_special_tile(slots, holes, trace, value, decode_dictionary(raw_config))

    def _spawn_special_tile(self, slots, holes, trace, value, config):
        config.setdefault("minGuaranteedPieces", 0)
        current = sum(slot.get("value", 0) == value for row in slots for slot in row)
        amount = min(config["refillSpawn"], config["maxSpawn"] - current)
        if amount <= 0:
            return
        minimum = max(0, config["minGuaranteedPieces"] - current)
        ignored = decode_dictionary(self.profile["spawning"].get("spawnColorsToIgnore")) or {}
        excluded = set(ignored.get(self.profile["state"]["currentPlayerIndex"], [])) if config.get("excludePlayersColorOnRefill") else set()
        candidates = [(x, y) for x, y in sorted(holes)
                      if slots[y][x].get("value", 0) == 0 and slots[y][x]["color"] not in excluded]
        if self.profile["rules"].get("boardModelName") in MUSHROOM_BOARDS:
            # MultiplierMushroomsBoard.IgnorePosition 0x59bd204: no side columns,
            # no bottom row, only the colours its ctor 0x59bb1b0 lists. Each
            # candidate is one shuffle draw, so this also moves the RNG.
            rows, columns = len(slots), len(slots[0])
            candidates = [(x, y) for x, y in candidates
                          if 0 < x < columns - 1 and y < rows - 1 and slots[y][x]["color"] in MUSHROOM_COLORS]
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


def _vinnie_se_heart_pair(value):
    from move_strategy import vinnie_se_heart_colors
    return vinnie_se_heart_colors(value)


def fill_simulator_board(model, board, special, chain_combos=0):
    """Fill the simulator board's holes; inputs (lists or numpy) are not mutated."""
    sim_to_engine, engine_to_sim = color_maps(model.profile)
    random_specials = bool(getattr(model, "random_specials", ()))
    uncolored = (UNCOLORED_RANDOM_SPECIALS if random_specials
                 else {SIM_DISCO_BALL: BROCCO_PIECE, SIM_CLEO: ENGINE_CLEO,
                       SIM_SWEEP_BROOM: ENGINE_SWEEP_BROOM})
    colored = COLORED_RANDOM_SPECIALS if random_specials else {}
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
                    raise UnsupportedRefill("Random special: raw slot colour missing from recording")
                converted.append({"color": ball_colors.get((y, x), 1), "value": uncolored[value],
                                  "canBeMatched": False, "color2": 1})
                continue
            if value in colored and color in sim_to_engine:
                converted.append({"color": sim_to_engine[color], "value": colored[value],
                                  "canBeMatched": True, "color2": 1})
                continue
            if color == -1 and value == 14:
                if model.billie is None:
                    raise UnsupportedRefill("Billie: raw drone colour and passive configuration required")
                # ConvertBillieBoomPiece clones the original slot and retains
                # its primary colour (0x5a13300); it still affects spawn counts.
                converted.append({"color": model.billie.drone_color, "value": 25,
                                  "canBeMatched": False, "color2": 1, "movable": True})
                continue
            if (value == SIM_MODE_TARGET and color in sim_to_engine
                    and model.profile["rules"].get("boardModelName") == DUSTVILLE_BOARD):
                # Dustville wanted figure: an ordinary orange piece flagged 16.
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
            if color not in sim_to_engine or value not in SIM_SPECIAL_TO_ENGINE:
                raise UnsupportedRefill("Unported simulator special/color in refill board")
            converted.append({"color": sim_to_engine[color], "value": SIM_SPECIAL_TO_ENGINE[value],
                              "canBeMatched": True, "color2": 1})
        raw.append(converted)
    _, trace = model.fill(raw, chain_combos)
    out, specials = copy.deepcopy(board), copy.deepcopy(special)
    for item in trace:
        x, y = item["x"], item["y"]
        out[y][x] = engine_to_sim[item["color"]]
        specials[y][x] = ENGINE_SPECIAL_TO_SIM[item.get("special_value", 0)]
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
MAX_FOLLOWED_PLIES = 2


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

        self.current = None
        self.hot = None
        self.ply = 0
        self.line_broken = False
        self.simulations = 0
        self.successful = 0
        self.fallbacks = 0
        self.followed = 0
        self.failure = None

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
        self.current.reset_action()
        self.line_broken = False
        self.simulations += 1
        return True

    def peek_draws(self, count):
        return self.current.peek_draws(count)

    def ball_spent(self, cell):
        self.current.ball_spent(cell)

    def random_special(self, cell, sim_color):
        return self.current.random_special(cell, sim_color)

    def wanted_shots(self, board, special, prevent):
        return self.current.wanted_shots(board, special, prevent)

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
        try:
            out, specials, _ = fill_simulator_board(self.current, board, special, chain_combos)
        except Exception as exc:
            self.failure = f"{type(exc).__name__}: {exc}"
            self.line_broken = True
            return board, special
        return out, specials

    def finish(self, result):
        """Remember the RNG the board this move ended on continues from."""
        if result is not None:
            events = getattr(result, "intent_events", ())
            if getattr(result, "cleo_scenario_count", 0):
                self.failure = "Cleo: probability scenarios are not an exact action"
                self.line_broken = True
            if getattr(self.current, "mixy_redealt", False):
                # engine_mixy: use #1 re-deals the code, which is not ported.
                self.failure = "Mixy code match: the re-deal is not ported"
                self.line_broken = True
            if any("random_outcomes" in e.get("type", "")
                   or e.get("type") == "uncertain_refill_boundary"
                   or (e.get("type") == "special_activation"
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
            if rainbow_cascade_unported(rules.get("id"), events):
                self.failure = "Rainbow cascade rocket/bomb timing is not ported"
                self.line_broken = True
        if result is not None and not self.line_broken and getattr(self.current, "billie", None) is not None:
            from engine_billie import finish_passive
            try:
                finish_passive(self.current, result)
            except UnsupportedRefill as exc:
                self.failure = str(exc)
                self.line_broken = True
        if result is not None:
            result.exact_refill_supported = not self.line_broken
            if self.line_broken:
                self.fallbacks += 1
            else:
                self.successful += 1
        # With other players on the board their moves use the same RNG -- but
        # not before a move that keeps our turn: its board is ours to play next.
        keeps_turn = result is not None and getattr(result, "extra_moves", 0) > 0
        if (result is None or not (self.follow_moves or keeps_turn) or self.line_broken
                or self.ply >= self.max_plies):
            return
        # A fired Funky marker moves before the next move (funky_relocate):
        # one draw per interior cell and new marker cells the ranking's fixed
        # funky overlay does not know. This move is exact; the board after it
        # is not followed.
        if any(e.get("type") == "funky_tile_activation"
               for e in getattr(result, "intent_events", ()) or ()):
            return
        hot = self.hot
        if hot is not None:
            if hot[0] is None:
                return
            if result.cleared_color_counts.get(hot[0]):
                self.current.rng.next()
                self.current.rng.next()
                hot = (hot[1], None)
        special = getattr(result, "special_board", None)
        if special is not None and is_dustville(self.current):
            # The next turn starts by topping the wanted figures back up.
            special = self.current.wanted_turn_start(result.board, special)
        self.states.setdefault(self._key(result.board, special), (self.current, hot, self.ply + 1))
        self.followed += 1


# The name from when only Square Match Solo was ported.
SquareRefill = EngineRefill
