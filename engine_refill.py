"""5.817 RefillSlots (FillAllEmptySlots), using engine colors and RNG.

Ported from the last-round branch, verified on Square Match Solo. Other
modes share the same code path; their adaptive (non-last-round) prevention
thresholds are not ported and must be supplied explicitly (tools/verify_refill
tries the candidates from simulator_capture.threshold_hypotheses).

This module fills existing holes; gravity, combo destruction and game flow
belong to the caller. Unsupported rule branches raise rather than silently
falling back to independent uniform draws.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field

from engine_rng import EngineRNG
from engine_spawn_weights import get_colors_priority, create_weights_list_new, pick_color
from engine_spawn_predicates import combo_count_at, is_part_of_combo, is_part_of_possible_highrank_combo
from simulator_capture import decode_dictionary, resolve_refill_overrides


class UnsupportedRefill(ValueError):
    pass


@dataclass
class EngineRefill:
    profile: dict
    rng: EngineRNG
    spawned_colors: dict[int, int] = field(default_factory=dict)
    # match/combo/special_combo/square prevention thresholds; None = the
    # resolved last-round branch.
    thresholds: dict | None = None
    # Present only when the raw drone colour and supported passive config exist.
    billie: object | None = None
    # Disco balls as (row, col, engine colour), from the raw slots. The slot keeps
    # its colour under the ball and CountFillingSlots counts it; None = not read.
    balls: list | None = None

    @classmethod
    def from_profile(cls, profile, *, seed=None, resume=False, thresholds=None):
        if thresholds is None:
            resolved = resolve_refill_overrides(profile)
            if not resolved.get("resolved"):
                raise UnsupportedRefill("Only the final-round branch is ported; adaptive thresholds "
                                        "need an explicit hypothesis")
            thresholds = resolved["prevention_thresholds"]
        config = profile["config"]["spawnEngine"]
        spawning = profile["spawning"]
        if not config.get("newColorPickLogic"):
            raise UnsupportedRefill("Legacy createWeightsList is not the captured branch")
        if spawning.get("<ForceNextCombo>k__BackingField") or spawning.get("<ForceBlueCombo>k__BackingField"):
            raise UnsupportedRefill("Forced-combo spawning requires its separate algorithm")
        special_data = decode_dictionary(spawning.get("specialTilesData")) or {}
        # ProcessSpecialTile is the same for any one tile type; checked on
        # Rainbow Hearts and Hot Color Bombs. Several types at once are not.
        if special_data and (len(special_data) != 1 or next(iter(special_data)) not in ENGINE_SPECIAL_TO_SIM):
            raise UnsupportedRefill("Special tile spawning is not ported for this configuration")
        if special_data:
            tile = decode_dictionary(next(iter(special_data.values())))
            supported_keys = {"excludePlayersColorOnRefill", "initialSpawn", "refillSpawn", "maxSpawn",
                              "spawnChance", "minGuaranteedPieces", "replenishRate"}
            required = {"refillSpawn", "maxSpawn", "spawnChance", "minGuaranteedPieces"}
            if (not required <= tile.keys() or tile.keys() - supported_keys
                    or any(not isinstance(tile[k], int) or tile[k] < 0 for k in required)
                    or tile["spawnChance"] > 100 or tile["minGuaranteedPieces"] > tile["maxSpawn"]):
                raise UnsupportedRefill("Special tile config is outside the ported refill branch")
        if profile["rules"].get("weightsRandomizer") is not None:
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
        balls = None if balls is None else [(s["row"], s["col"], s["color"]) for s in balls]
        return cls(profile, rng, spawned, dict(thresholds), balls=balls)

    def clone(self):
        return type(self)(self.profile, self.rng.clone(), dict(self.spawned_colors), self.thresholds, self.billie,
                          None if self.balls is None else list(self.balls))

    copy = clone

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
        """ProcessSpecialTile/ConvertSlots: Rainbow Hearts, Hot Color Bombs.

        Evidence: simulator_core ARM64 0x5a05550, 0x5a05a7c,
        BoardModel.GetConvertPoints 0x5974140 / GetSlotPrioritize 0x5972158.
        Conversion is limited to newly filled ordinary non-player colors;
        candidates are scanned x-major, shuffled, then chance-tested.
        """
        data = decode_dictionary(self.profile["spawning"].get("specialTilesData")) or {}
        if not data:
            return
        value, raw_config = next(iter(data.items()))
        config = decode_dictionary(raw_config)
        current = sum(slot.get("value", 0) == value for row in slots for slot in row)
        amount = min(config["refillSpawn"], config["maxSpawn"] - current)
        if amount <= 0:
            return
        minimum = max(0, config["minGuaranteedPieces"] - current)
        ignored = decode_dictionary(self.profile["spawning"].get("spawnColorsToIgnore")) or {}
        excluded = set(ignored.get(self.profile["state"]["currentPlayerIndex"], [])) if config.get("excludePlayersColorOnRefill") else set()
        candidates = [(x, y) for x, y in sorted(holes)
                      if slots[y][x].get("value", 0) == 0 and slots[y][x]["color"] not in excluded]
        selected = self.rng.shuffled(candidates)[:max(amount, minimum)]
        for x, y in selected:
            if current >= config["minGuaranteedPieces"] and not self.rng.chance(config["spawnChance"]):
                continue
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
# Color Crystal, and the Square Match crosshair (board_source maps engine 8 to
# SPECIAL_CROSSHAIR).
SIM_SPECIAL_TO_ENGINE = {0: 0, 1: 5, 2: 4, 3: 6, 4: 7, 11: 23, 15: 18, 20: 40, 46: 8}
ENGINE_SPECIAL_TO_SIM = {engine: sim for sim, engine in SIM_SPECIAL_TO_ENGINE.items()}
SIM_DISCO_BALL = 16
BROCCO_PIECE = 28


def fill_simulator_board(model, board, special, chain_combos=0):
    """Fill the simulator board's holes; inputs (lists or numpy) are not mutated."""
    sim_to_engine, engine_to_sim = color_maps(model.profile)
    balls = [(y, x) for y, row in enumerate(special) for x, value in enumerate(row) if int(value) == SIM_DISCO_BALL]
    ball_colors = model.ball_colors_at(balls) if balls else {}
    raw = []
    for y, row in enumerate(board):
        converted = []
        for x, color in enumerate(row):
            color, value = int(color), int(special[y][x])
            if value == SIM_DISCO_BALL:
                converted.append({"color": ball_colors.get((y, x), 1), "value": BROCCO_PIECE,
                                  "canBeMatched": False, "color2": 1})
                continue
            if color == -1 and value == 14:
                if model.billie is None:
                    raise UnsupportedRefill("Billie: raw drone colour and passive configuration required")
                # ConvertBillieBoomPiece clones the original slot and retains
                # its primary colour (0x5a13300); it still affects spawn counts.
                converted.append({"color": model.billie.drone_color, "value": 25,
                                  "canBeMatched": False, "color2": 1, "movable": True})
                continue
            if color == -1 and value == 20:
                # Froggy lotus: an uncolored, fixed obstacle while ordinary
                # swipes resolve. Collecting the lotus is a separate action.
                converted.append({"color": 1, "value": 40, "canBeMatched": False, "color2": 1})
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
    return tuple(tuple(int(v) for v in row) for row in board)


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
            if any("random_outcomes" in e.get("type", "")
                   or e.get("type") == "uncertain_refill_boundary"
                   or (e.get("type") == "special_activation"
                       and e.get("special") in ("lightning", "crosshair", "all_aboard_bandit"))
                   for e in events):
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
        if (result is None or not self.follow_moves or self.line_broken
                or self.ply >= self.max_plies):
            return
        hot = self.hot
        if hot is not None:
            if hot[0] is None:
                return
            if result.cleared_color_counts.get(hot[0]):
                self.current.rng.next()
                self.current.rng.next()
                hot = (hot[1], None)
        self.states.setdefault(self._key(result.board, getattr(result, "special_board", None)),
                               (self.current, hot, self.ply + 1))
        self.followed += 1


# The name from when only Square Match Solo was ported.
SquareRefill = EngineRefill
