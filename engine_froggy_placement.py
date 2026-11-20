"""Froggy Fu lotus placement and the entrance attempt choice (game 5.817, engine fix 7).

Port of FroggyFuLotusPlacementPlanner (BuildPlacementSelection 0x57580e8,
GetLotusCandidates 0x5758844, AnalyzePossibleMoves 0x5758930,
GreedySelectLotuses 0x57599b0, ScoreCandidateWithBreakdown 0x575bebc and its
helpers) and FroggyFuEntranceAttemptEvaluator (PickBestAttempt 0x5a59c38,
EvaluateAttempt 0x5a59eac, CompareAttempts 0x5a5adf0,
ComputeSeparationDeficitSum 0x5a5ac88). Listings in Debug/reverse/froggy and
Debug/reverse/simulator_all.

Boards are the simulator's [row][column]; a point is (x, y) = (column, row)
as in the engine. Colours given to the planner are native SlotColor values
(2..8); None = 1, Empty = 0.

What the engine does, in short:

* candidates (x-major): plain pieces (value 0) that can be matched, move, take
  damage and have no second colour;
* every possible move (GetPossibleMoves, x-major, Down then Right) and its
  combos (GetValidOutcomes): the move's combo cells, the candidates next to
  them (not the two swapped cells, not a combo cell) and, per such candidate,
  the colours of the combos it touches (the energy colour marks it
  energy-adjacent);
* lotusCount greedy rounds: every free candidate is scored (match adjacency
  through a move whose combo is not claimed yet, separation, not on the edge,
  energy, preferred colour, same colour penalty, swap position penalty) and
  the first best one is taken; the moves it touches claim their combo cells;
* each entrance attempt is simulated on a clone (its pieces destroyed) and
  planned; the attempts are compared lexicographically (placed lotuses,
  match-adjacent ones, distinct colours, energy, separation deficit,
  min-pieces colours, score distance, then the earlier attempt).
"""
from __future__ import annotations

from dataclasses import dataclass, field

NONE_COLOR = 1
EMPTY_COLOR = 0
ALL_COLOR = 12
NOT_A_COLOR = frozenset((EMPTY_COLOR, NONE_COLOR, ALL_COLOR))   # mask 0x1003
LOTUS_VALUE = 40
# FroggyFuLotusPlacementPlanner static directions (cctor 0x575d3b0), (x, y).
DIRECTIONS = ((0, 1), (0, -1), (1, 0), (-1, 0))
# GetCandidatePrimaryColor: a colour missing from the weights ranks 10.
MISSING_COLOR_WEIGHT = 10
WEIGHT_KEYS = ("MatchAdjacent", "Separation", "NonEdge", "EnergyAdjacentBonus",
               "EnergyAdjacentPenalty", "MinPiecesEligibleBonus", "SwapPositionPenalty",
               "SkipSameColorPenalty", "ColorPriorityBonus", "ComboPositionPenalty")
# WeightConfig..ctor 0x57580c4 defaults are not needed: the capture holds the
# server's placementWeights.

# Engine SlotValue of the simulator's classic specials (engine_refill
# SIM_SPECIAL_TO_ENGINE): Row 5, Column 4, Bomb 6, Lightning 7, Crosshair 8
# (canBeMatched, movable, damageable, colour score in every raw slot of
# research 20261119_120537 Multiplier Mushrooms).
SIM_CLASSIC_TO_ENGINE = {1: 5, 2: 4, 3: 6, 4: 7, 46: 8}
LIGHTNING = 7


class UnsupportedPlacement(ValueError):
    pass


@dataclass
class Slot:
    color: int          # native SlotColor
    value: int          # native SlotValueType
    movable: bool
    matchable: bool
    damageable: bool = True
    color2: int = NONE_COLOR

    @property
    def empty(self):
        return self.color == EMPTY_COLOR


def native_grid(board, special, sim_to_engine, *, holes=()):
    """Engine slots for a simulator board. ``holes``: (row, col) emptied cells."""
    holes = set(holes)
    grid = []
    for r, row in enumerate(board):
        out = []
        for c, color in enumerate(row):
            value = int(special[r][c])
            color = int(color)
            if (r, c) in holes or color == 0 and value == 0:
                out.append(Slot(EMPTY_COLOR, 0, False, False, False))
            elif value == 20:
                out.append(Slot(NONE_COLOR, LOTUS_VALUE, False, False))
            elif value == 0 and color in sim_to_engine:
                out.append(Slot(int(sim_to_engine[color]), 0, True, True))
            elif value in SIM_CLASSIC_TO_ENGINE and color in sim_to_engine:
                out.append(Slot(int(sim_to_engine[color]), SIM_CLASSIC_TO_ENGINE[value], True, True))
            elif value == SIM_MUSHROOM and color in sim_to_engine:
                # As entrance_slots: a coloured piece, never a lotus candidate
                # (value != 0). Multiplier Mushrooms 2026-11-18 20:54: without
                # it the booster was unsupported and held full for 18 moves.
                # shortcut: no recorded activation with mushrooms yet; check the first miss.
                out.append(Slot(int(sim_to_engine[color]), MUSHROOM_ENGINE, True, True))
            elif value == SIM_HEART and color in sim_to_engine:
                # A heart (CupidHeart 23) is a coloured piece, as the mushroom.
                # Funky Tiles 2026-11-19 06:48: refused, the meter stayed full
                # all game. shortcut: no recorded activation with a heart yet; check the first miss.
                out.append(Slot(int(sim_to_engine[color]), CUPID_HEART, True, True))
            elif value == SIM_MODE_TARGET and color in sim_to_engine:
                # Dustville's wanted tile: a coloured BoardSpecial (raw slot value
                # 16), never a lotus candidate (research 20261120_085618).
                out.append(Slot(int(sim_to_engine[color]), PURPLE_GEM_ENGINE, True, True))
            elif _sim_gem(value) and color in sim_to_engine:
                # A Gem Grab crystal is a coloured piece, never a lotus candidate.
                out.append(Slot(int(sim_to_engine[color]), PURPLE_GEM_ENGINE, True, True))
            else:
                raise UnsupportedPlacement(f"Froggy placement: piece {color}/{value} not ported")
        grid.append(out)
    return grid


def _at(grid, point):
    x, y = point
    if 0 <= y < len(grid) and 0 <= x < len(grid[y]):
        return grid[y][x]
    return None


def lotus_candidates(grid):
    """GetLotusCandidates 0x5758844: BoardModel.Where (x outer, y inner) of b__15_0."""
    rows, cols = len(grid), len(grid[0])
    return [(x, y) for x in range(cols) for y in range(rows)
            if grid[y][x].value == 0 and grid[y][x].matchable and grid[y][x].movable
            and grid[y][x].damageable and grid[y][x].color2 == NONE_COLOR
            and not grid[y][x].empty]


def _line_cells(grid, point):
    """The line match through ``point`` (horizontal and vertical runs of 3+)."""
    slot = _at(grid, point)
    if slot is None or not slot.matchable or slot.color in NOT_A_COLOR:
        return []
    x, y = point
    cells = []
    for axis in (((-1, 0), (1, 0)), ((0, -1), (0, 1))):
        run = []
        for dx, dy in axis:
            xx, yy = x + dx, y + dy
            while True:
                other = _at(grid, (xx, yy))
                if other is None or not other.matchable or other.color != slot.color:
                    break
                run.append((xx, yy))
                xx, yy = xx + dx, yy + dy
        if len(run) >= 2:
            cells.extend(run)
    return [point] + cells if cells else []


def possible_moves(grid):
    """GetPossibleMoves(board, false) with each move's GetValidOutcomes combos.

    Returns [(source, target, [combo positions, ...]), ...]. Two specials (or
    the Lightning with a piece) merge: one combo of the two swapped cells; the
    Lightning's move also keeps the lines the swap makes.
    """
    rows, cols = len(grid), len(grid[0])
    moves = []
    for x in range(cols):
        for y in range(rows):
            for dx, dy in ((0, 1), (1, 0)):
                a, b = (x, y), (x + dx, y + dy)
                sa, sb = _at(grid, a), _at(grid, b)
                if sa is None or sb is None or not sa.movable or not sb.movable or sa.empty or sb.empty:
                    continue
                if sa.value and sb.value:
                    moves.append((a, b, [[a, b]]))
                    continue
                lightning = LIGHTNING in (sa.value, sb.value)
                if sa.color == sb.color and not lightning:
                    continue
                grid[a[1]][a[0]], grid[b[1]][b[0]] = sb, sa
                combos = [cells for cells in (_line_cells(grid, a), _line_cells(grid, b)) if cells]
                grid[a[1]][a[0]], grid[b[1]][b[0]] = sa, sb
                if lightning:
                    # The line the swapped piece makes counts too: Funky Tiles
                    # research 20261118_115219 019->020, a Blue three made by
                    # swapping a Blue into the Lightning's cell put the lotus
                    # next to it (the energy-adjacent attempt won).
                    # Without a line the swap is no move here: Funky Tiles
                    # refill_misses 20261119_004054 / 004341, the game put the
                    # lotus on the piece next to a Lightning, (5, 1), which the
                    # swap penalty had moved 20 below the first best cell.
                    if combos:
                        moves.append((a, b, [[a, b]] + combos))
                elif combos:
                    moves.append((a, b, combos))
    return moves


def combo_color_unswapped(grid, combo, source, target):
    """GetComboColorFromUnswappedBoard 0x575b94c."""
    for point in combo:
        if point == source or point == target:
            continue
        color = grid[point[1]][point[0]].color
        if color >= 2:
            return color
    return NONE_COLOR


@dataclass
class MoveAnalysis:
    swap_positions: set = field(default_factory=set)        # +0x10
    match_adjacent: set = field(default_factory=set)        # +0x18
    combo_sets: list = field(default_factory=list)          # +0x20, per move
    adjacent_sets: list = field(default_factory=list)       # +0x28, per move
    colors_by_cell: dict = field(default_factory=dict)      # +0x30, point -> [colours]
    energy_adjacent: set = field(default_factory=set)       # +0x38
    combo_cells: set = field(default_factory=set)           # +0x40


def analyze_possible_moves(grid, candidates, energy_color, moves=None):
    """AnalyzePossibleMoves 0x5758930."""
    analysis = MoveAnalysis()
    candidate_set = set(candidates)
    for source, target, combos in (possible_moves(grid) if moves is None else moves):
        analysis.swap_positions.update((source, target))
        cells = []
        for combo in combos:
            for point in combo:
                if point not in cells:
                    cells.append(point)
        cell_set = set(cells)
        adjacent = []
        for point in cells:
            if point == source or point == target:
                continue
            for dx, dy in DIRECTIONS:
                n = (point[0] + dx, point[1] + dy)
                if n in candidate_set and n not in cell_set and n not in adjacent:
                    adjacent.append(n)
        adjacent_set = set(adjacent)
        for combo in combos:
            color = combo_color_unswapped(grid, combo, source, target)
            if color in NOT_A_COLOR:
                continue
            for point in combo:
                if point == source or point == target:
                    continue
                for dx, dy in DIRECTIONS:
                    n = (point[0] + dx, point[1] + dy)
                    if n not in adjacent_set:
                        continue
                    colors = analysis.colors_by_cell.setdefault(n, [])
                    if color not in colors:
                        colors.append(color)
                    if color == energy_color:
                        analysis.energy_adjacent.add(n)
        analysis.combo_sets.append(cell_set)
        analysis.adjacent_sets.append(adjacent_set)
        analysis.match_adjacent.update(adjacent)
        analysis.combo_cells.update(cells)
    return analysis


@dataclass
class PlannerConfig:
    min_separation: int
    color_weights: dict          # native colour -> weight (GetPlacementWeightsForActivation)
    weights: dict                # WeightConfig


def candidate_primary_color(config, point, analysis):
    """GetCandidatePrimaryColor 0x575b428: highest weight, ties to the lower colour."""
    colors = analysis.colors_by_cell.get(point)
    if not colors:
        return NONE_COLOR
    best, chosen = -1, NONE_COLOR
    for color in colors:
        weight = config.color_weights.get(color, MISSING_COLOR_WEIGHT)
        if weight > best:
            best, chosen = weight, color
        elif weight == best and (chosen == NONE_COLOR or color < chosen):
            chosen = color
    return chosen


def effective_primary_color(config, point, analysis, energy_color, prefer_energy):
    """GetEffectivePrimaryColor 0x575bb48."""
    if energy_color != NONE_COLOR and prefer_energy and point in analysis.energy_adjacent:
        return energy_color
    return candidate_primary_color(config, point, analysis)


def has_adjacent_match_color(point, analysis, color):
    """HasAdjacentMatchColor 0x575bc00."""
    return color != NONE_COLOR and color in analysis.colors_by_cell.get(point, ())


def has_unclaimed_match_adjacency(point, analysis, claimed):
    """HasUnclaimedMatchAdjacency 0x575bcb8."""
    if point not in analysis.match_adjacent:
        return False
    return any(point in adjacent and not (combo & claimed)
               for adjacent, combo in zip(analysis.adjacent_sets, analysis.combo_sets))


def claim_combo_for(point, analysis, claimed):
    """ClaimComboFor 0x575c9cc: every move the point touches whose combo is free."""
    for adjacent, combo in zip(analysis.adjacent_sets, analysis.combo_sets):
        if point in adjacent and not (combo & claimed):
            claimed.update(combo)


def _manhattan(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def is_edge(grid, point):
    x, y = point
    return x == 0 or y == 0 or y == len(grid) - 1 or x == len(grid[0]) - 1


def score_candidate(config, rng, point, analysis, used_colors, prefer_energy, chance_skip,
                    min_pieces_colors, energy_color, preferred_color, energy_placed,
                    preferred_placed, unclaimed, separated, edge):
    """ScoreCandidateWithBreakdown 0x575bebc."""
    w = config.weights
    score = w["MatchAdjacent"] if unclaimed else 0
    if separated:
        score += w["Separation"]
    if not edge:
        score += w["NonEdge"]
    in_energy = point in analysis.energy_adjacent
    has_preferred = has_adjacent_match_color(point, analysis, preferred_color)
    energy_bonus = (not energy_placed) and prefer_energy and in_energy
    if in_energy:
        if not prefer_energy:
            score -= w["EnergyAdjacentPenalty"]
        elif energy_bonus:
            score += w["EnergyAdjacentBonus"]
    color = effective_primary_color(config, point, analysis, energy_color, prefer_energy)
    if color != NONE_COLOR:
        if has_preferred and not (energy_bonus or preferred_placed):
            score += w["ColorPriorityBonus"]
        if color in min_pieces_colors:
            score += w["MinPiecesEligibleBonus"]
        # RandomWrapper.Chance always draws (engine_rng.chance).
        if chance_skip >= 1 and color in used_colors and rng.chance(chance_skip):
            score -= w["SkipSameColorPenalty"]
    if point in analysis.swap_positions:
        score -= w["SwapPositionPenalty"]
    if point in analysis.combo_cells:
        score -= w["ComboPositionPenalty"]
    return score


@dataclass
class PlacementSelection:
    positions: list
    match_adjacent: set
    energy_adjacent: set
    colors: dict                 # point -> effective primary colour
    min_pieces_colors: set


def greedy_select(config, grid, rng, candidates, analysis, lotus_count, min_pieces_colors,
                  prefer_energy, chance_skip, energy_color, preferred_color):
    """GreedySelectLotuses 0x57599b0."""
    selected, claimed, used_colors, colors = [], set(), set(), {}
    energy_placed = preferred_placed = False
    for _ in range(max(0, int(lotus_count))):
        best, best_score = None, None
        for point in candidates:
            if point in selected:
                continue
            unclaimed = has_unclaimed_match_adjacency(point, analysis, claimed)
            violates = any(_manhattan(p, point) < config.min_separation for p in selected)
            score = score_candidate(config, rng, point, analysis, used_colors, prefer_energy,
                                    chance_skip, min_pieces_colors, energy_color, preferred_color,
                                    energy_placed, preferred_placed, unclaimed, not violates,
                                    is_edge(grid, point))
            if best_score is None or score > best_score:
                best, best_score = point, score
        if best is None:
            break
        selected.append(best)
        claim_combo_for(best, analysis, claimed)
        in_energy = best in analysis.energy_adjacent
        has_preferred = has_adjacent_match_color(best, analysis, preferred_color)
        color = effective_primary_color(config, best, analysis, energy_color, prefer_energy)
        colors[best] = color
        if color != NONE_COLOR:
            used_colors.add(color)
        newly_energy = in_energy and prefer_energy and not energy_placed
        energy_placed = energy_placed or (in_energy and prefer_energy)
        preferred_placed = preferred_placed or (has_preferred and not newly_energy)
    return selected, colors


def min_pieces_eligible_colors(grid, minimum):
    """GetMinPiecesEligibleColors 0x5758500: colours with at least ``minimum`` plain pieces."""
    if minimum < 2:
        return set()
    counts = {}
    for x in range(len(grid[0])):
        for y in range(len(grid)):
            s = grid[y][x]
            if s.value == 0 and s.matchable and s.movable and s.color not in NOT_A_COLOR:
                counts[s.color] = counts.get(s.color, 0) + 1
    return {color for color, count in counts.items() if count >= minimum}


def build_selection(config, grid, rng, lotus_count, min_pieces, prefer_energy, chance_skip,
                    energy_color, preferred_color):
    """BuildPlacementSelection 0x57580e8 (engine fix 7 path)."""
    min_colors = min_pieces_eligible_colors(grid, min_pieces)
    candidates = lotus_candidates(grid)
    analysis = analyze_possible_moves(grid, candidates, energy_color)
    positions, colors = greedy_select(config, grid, rng, candidates, analysis, lotus_count, min_colors,
                                      prefer_energy, chance_skip, energy_color, preferred_color)
    return PlacementSelection(positions, analysis.match_adjacent, analysis.energy_adjacent,
                              colors, min_colors)


@dataclass
class AttemptEvaluation:
    attempt_number: int          # +0x10, one-based
    targets: list
    positions: list
    placed: int = 0              # +0x2c
    match_adjacent: int = 0      # +0x30
    energy_adjacent: int = 0     # +0x34
    non_edge: int = 0            # +0x38
    distinct_colors: int = 0     # +0x3c
    colored: int = 0             # +0x40
    separation_deficit: int = 0  # +0x44
    min_pieces: int = 0          # +0x48
    energy_satisfied: bool = True  # +0x4f
    score_distance: int = 0      # +0x60


def separation_deficit(positions, min_separation):
    """ComputeSeparationDeficitSum 0x5a5ac88."""
    total = 0
    for i in range(len(positions)):
        for j in range(i + 1, len(positions)):
            total += max(0, min_separation - _manhattan(positions[i], positions[j]))
    return total


def evaluate(selection, attempt_number, targets, grid, min_separation, require_energy,
             enforce_skip, min_pieces, energy_color, moves_on_sim=None):
    """EvaluateAttempt 0x5a59eac, without the score distance (filled by the caller)."""
    e = AttemptEvaluation(attempt_number, targets, list(selection.positions))
    e.placed = len(selection.positions)
    seen = []
    for point in selection.positions:
        if point in selection.match_adjacent:
            e.match_adjacent += 1
        if point in selection.energy_adjacent:
            e.energy_adjacent += 1
        if not is_edge(grid, point):
            e.non_edge += 1
        color = selection.colors.get(point, NONE_COLOR)
        if point in selection.colors and color != NONE_COLOR:
            e.colored += 1
            if color not in seen:
                seen.append(color)
                e.distinct_colors += 1
            if color in selection.min_pieces_colors:
                e.min_pieces += 1
    e.separation_deficit = separation_deficit(e.positions, min_separation)
    e.energy_satisfied = (e.energy_adjacent > 0) if require_energy else True
    if require_energy and not e.energy_satisfied:
        # Any possible move on the simulated board whose combo is the energy colour.
        for source, target, combos in (possible_moves(grid) if moves_on_sim is None else moves_on_sim):
            if any(combo_color_unswapped(grid, combo, source, target) == energy_color for combo in combos):
                e.energy_satisfied = True
                break
    return e


FROGGY_FU = 63
MUSHROOM_ENGINE = 0x13
SIM_MUSHROOM = 17
SIM_HEART = 11      # move_strategy.SPECIAL_HEART
SIM_MODE_TARGET = 9  # move_strategy.SPECIAL_MODE_TARGET
CUPID_HEART = 23    # engine_refill.SIM_SPECIAL_TO_ENGINE
PURPLE_GEM_ENGINE = 16  # Gem Grab crystal: SlotModel.value 16, score = its number


def _sim_gem(value):
    from move_strategy import is_purple_gem_special
    return is_purple_gem_special(value)


def specials_left_score(special, special_value, factor):
    """Ability.GetSpecialsLeftScore 0x5d7f2ec: Round(count * specialPieceScoreValue * factor).

    count = slots with IsSpecial and SlotValue != 23 (lambda b__40_0 0x5d7f584),
    each worth the same. shortcut: only the classic specials are known to be
    IsSpecial; any other special on the board is refused until IsSpecial is read.
    """
    count = 0
    for row in special:
        for value in row:
            value = int(value)
            if value in SIM_CLASSIC_TO_ENGINE:
                count += 1
            elif value:
                raise UnsupportedPlacement(f"Froggy Fu: GetSpecialsLeftScore with special {value} is not ported")
    return int(round(count * special_value * factor))


def entrance_slots(board, special, sim_to_engine, score_values, mode_target=None):
    """SlotModels the entrance draws from (engine_froggy.entrance_attempts).

    A plain piece scores its colour's value (SlotModel.score; research
    20261118_103045: every plain piece of every capture, also on the cells a
    lotus collection stamped). Specials and lotuses are neither normals nor
    mushrooms; a mushroom keeps its colour's score.
    """
    slots = []
    for r, row in enumerate(board):
        for c, color in enumerate(row):
            value, color = int(special[r][c]), int(color)
            if value == 20:
                slots.append(dict(x=c, y=r, value=LOTUS_VALUE, score=0, canBeMatched=False, movable=False))
                continue
            if color not in sim_to_engine:
                raise UnsupportedPlacement(f"Froggy entrance: cell colour {color} not ported")
            engine_value = {0: 0, SIM_MUSHROOM: MUSHROOM_ENGINE, SIM_HEART: CUPID_HEART}.get(
                value, SIM_CLASSIC_TO_ENGINE.get(value))
            score = int(score_values.get(color, 1))
            if engine_value is None and _sim_gem(value):
                # Crystal Cave 20261119_173349: raw slot value 16, score its number.
                engine_value, score = PURPLE_GEM_ENGINE, value - 100
            if engine_value is None and value == SIM_MODE_TARGET and mode_target is not None:
                # Dustville's wanted tile: a coloured BoardSpecial (raw slot value
                # 16, score 1; research 20261120_085618).
                engine_value, score = mode_target
            if engine_value is None:
                raise UnsupportedPlacement(f"Froggy entrance: special {value} not ported")
            slots.append(dict(x=c, y=r, value=engine_value, score=score,
                              canBeMatched=True, movable=True))
    return slots


def config_for(fields, activation):
    from engine_froggy import _activation_value
    from simulator_capture import decode_dictionary
    weights = _activation_value(fields["placementWeightByColorByActivation"], activation, {})
    weights = decode_dictionary(weights) if weights and "entries" in weights else (weights or {})
    return PlannerConfig(int(fields["minLotusSeparation"]), {int(k): int(v) for k, v in weights.items()},
                         {k: int(fields["placementWeights"][k]) for k in WEIGHT_KEYS})


def activate(board, special, model, activation, energy_color, score_values, settle, blocked_cells=()):
    """Use -> BeginNewActivation -> PickEntranceExplosionTargets -> PlaceLotuses.

    ``settle(model, cells)``: the simulator's destroy of ``cells`` with the
    exact refill and every cascade, on ``model`` (its RNG advanced); returns
    (result, points scored). Each attempt is settled on a clone that starts
    from the RNG after the attempt draws (GameLogic.Clone); the winner is
    settled again on ``model`` itself, as the game does. Returns (result,
    lotus cells (row, col), winning attempt index, events).

    ``blocked_cells``: (row, col) the entrance never targets. Funky Tiles
    research 20261118_110443: with the funky cells left out the game's
    entrance is one of the attempts in 15 of 15 activations, none without.

    The clone's whole settle is what the planner reads: research
    20261118_103045 (12 activations) gave every lotus position and the RNG
    counter after the activation; the score distance (|points -
    Round(scoreTarget * boosterScoreTargetFactor)|) picked 11 of 12 winners.
    The 12th (006->007) is open: the game took attempt 0 (62 points by the
    colour values, distance 13) over attempt 2 (71, distance 4), and its
    score rose by 37 and its meter stood at 6 after that activation (as after
    017->018, the other capture whose score fell short).
    """
    from engine_froggy import _activation_value, roll_entrance
    from engine_refill import color_maps

    profile = model.profile
    fields = profile.get("froggy_booster_fields")
    if not fields:
        raise UnsupportedPlacement("Froggy Fu: booster fields missing from capture")
    if any(int(v) == 20 for row in special for v in row):
        # RevertLotuses (PickRevertColor) runs first; not recorded.
        raise UnsupportedPlacement("Froggy Fu: a lotus is still on the board")
    sim_to_engine = color_maps(profile)[0]
    from engine_refill import DUSTVILLE_BOARD
    dustville = (profile.get("rules") or {}).get("boardModelName") == DUSTVILLE_BOARD
    slots = entrance_slots(board, special, sim_to_engine, score_values,
                           (PURPLE_GEM_ENGINE, 1) if dustville else None)
    entrance = roll_entrance(model.rng, fields, profile["spawning"].get("gameColors"), slots,
                             activation=activation, preferred_color_fix=True,
                             blocked_cells=blocked_cells)
    config = config_for(fields, activation)
    lotus_count = int(_activation_value(fields["lotusCountByActivation"], activation))
    min_pieces = int(_activation_value(fields["minimumPiecesToPullByActivation"], activation))
    chance_skip = int(_activation_value(fields["chanceToSkipSameColorMatchByActivation"], activation))
    # Ability.scoreTarget (+0x24) and specialPieceScoreValue (+0x20).
    target_param = int(fields.get("scoreTarget") or 0)
    special_value = int(fields.get("specialPieceScoreValue") or 0)
    use_score = target_param != 0
    factor = float((profile.get("rules") or {}).get("boosterScoreTargetFactor") or 1.0)
    # Fix64 multiply then Fix64.Round, ties to even (Ability.GetScoreTarget 0x59033c4).
    target = int(round(target_param * factor))
    best = None
    for index, cells in enumerate(entrance.attempts):
        clone = model.clone()
        clone.rng = model.rng.clone()
        result, points = settle(clone, [tuple(cell) for cell in cells])
        grid = native_grid(result.board, result.special_board, sim_to_engine)
        selection = build_selection(config, grid, clone.rng, lotus_count, min_pieces,
                                    entrance.prefer_energy_adjacent, chance_skip, energy_color,
                                    entrance.preferred_color)
        evaluation = evaluate(selection, index + 1, cells, grid, config.min_separation,
                              entrance.prefer_energy_adjacent, chance_skip > 0, min_pieces, energy_color)
        # EvaluateAttempt 0x5ed2634-0x5ed2648: |score - (target + playerScore) + getSpecialsLeftScore(clone)|.
        left = specials_left_score(result.special_board, special_value, factor) if special_value else 0
        evaluation.score_distance = abs(int(round(points)) + left - target)
        if best is None or compare_attempts(evaluation, best, entrance.prefer_energy_adjacent,
                                            min_pieces > 1, chance_skip > 0, use_score) >= 1:
            best = evaluation
    if best is None:
        raise UnsupportedPlacement("Froggy Fu: no entrance attempt")
    result, _ = settle(model, [tuple(cell) for cell in best.targets])
    lotuses = [(y, x) for x, y in best.positions]
    events = [{"type": "froggy_entrance", "cells": [list(c) for c in best.targets],
               "attempt": best.attempt_number - 1},
              {"type": "froggy_lotus_placed", "cells": [list(c) for c in lotuses]}]
    return result, lotuses, best.attempt_number - 1, events


def pick_revert_color(grid_color, point, original, game_colors, rng):
    """FroggyFu::PickRevertColor 0x5eccb7c (build 5.900).

    ``grid_color(x, y)`` is the engine colour on the board now (None out of
    bounds). The lotus keeps ``original`` unless a 4-neighbour has it; then one
    RandomWrapper::Range (0x3f40af8) picks among the game colours no neighbour
    has (predicate b__0 0x5ecec78 = !neighbours.Contains).
    """
    if original in NOT_A_COLOR or not game_colors:
        return original
    x, y = point
    neighbours = set()
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        color = grid_color(x + dx, y + dy)
        if color is not None and color not in NOT_A_COLOR:
            neighbours.add(color)
    if original not in neighbours:
        return original
    candidates = [c for c in game_colors if c not in neighbours]
    if not candidates:
        return original
    return candidates[rng.range(0, len(candidates))]


def revert_lotuses(board, special, profile, rng):
    """FroggyFu::RevertLotuses 0x5ec30f4: each lotus of LotusPositions, in order,
    back to a plain piece of PickRevertColor's colour, written at once (a later
    lotus sees the new neighbour). ConvertSlots only: no destroy, no refill.

    shortcut: the lotus colour (color2) and the list come from the capture's
    raw_slots / board_extra_data; a lotus our own plan placed has neither, so it
    stays unsupported until the plan carries them.
    Returns (board, special, events).
    """
    from engine_refill import color_maps

    sim_to_engine, to_sim = color_maps(profile)[:2]
    entries = (profile.get("board_extra_data") or {}).get("entries") or ()
    raw = next((str(e.get("value")) for e in entries if str(e.get("key", "")).startswith("LotusPositions")), "")
    points = [tuple(int(v) for v in item.split(",")) for item in raw.split(";") if item.strip()]
    slots = {(int(s["x"]), int(s["y"])): s for s in profile.get("raw_slots") or ()}
    board = [list(map(int, row)) for row in board]
    special = [list(map(int, row)) for row in special]
    lotus_cells = {(r, c) for r, row in enumerate(special) for c, v in enumerate(row) if int(v) == 20}
    if not lotus_cells <= {(y, x) for x, y in points}:
        raise UnsupportedPlacement("Froggy Fu: lotus list does not match the board")
    # RevertLotuses 0x5ec3304: a listed cell that is no longer a lotus (value 40) is skipped.
    points = [(x, y) for x, y in points if (y, x) in lotus_cells]
    rows, columns = len(board), len(board[0])

    def grid_color(x, y):
        if not (0 <= x < columns and 0 <= y < rows):
            return None
        if int(special[y][x]) == 20:
            return NONE_COLOR
        return int(sim_to_engine.get(int(board[y][x]), NONE_COLOR))

    game_colors = [int(c) for c in (profile.get("spawning") or {}).get("gameColors") or ()]
    events = []
    for x, y in points:
        slot = slots.get((x, y))
        if slot is None or int(slot.get("value", 0)) != LOTUS_VALUE:
            raise UnsupportedPlacement("Froggy Fu: lotus colour missing from capture")
        color, color2 = int(slot["color"]), int(slot["color2"])
        original = color if color2 == NONE_COLOR else color2
        picked = pick_revert_color(grid_color, (x, y), original, game_colors, rng)
        if picked not in to_sim:
            raise UnsupportedPlacement(f"Froggy Fu: revert colour {picked} not ported")
        board[y][x], special[y][x] = int(to_sim[picked]), 0
        events.append({"type": "froggy_revert", "cell": [y, x], "color": picked})
    return board, special, events


def place_lotuses(board, special, lotuses):
    """ConvertSlots(value 40): the simulator's lotus is board -1 / special 20."""
    board = [list(map(int, row)) for row in board]
    special = [list(map(int, row)) for row in special]
    for r, c in lotuses:
        board[r][c], special[r][c] = -1, 20
    return board, special


def compare_attempts(candidate, best, require_energy, enforce_min_pieces, enforce_skip, use_score):
    """CompareAttempts 0x5a5adf0: > 0 when ``candidate`` is better."""
    for diff in (candidate.placed - best.placed, candidate.match_adjacent - best.match_adjacent):
        if diff:
            return diff
    if enforce_skip and candidate.distinct_colors != best.distinct_colors:
        return candidate.distinct_colors - best.distinct_colors
    if require_energy:
        if candidate.energy_adjacent != best.energy_adjacent:
            return candidate.energy_adjacent - best.energy_adjacent
        if candidate.energy_satisfied != best.energy_satisfied:
            return 1 if candidate.energy_satisfied else -1
    if best.separation_deficit != candidate.separation_deficit:
        return best.separation_deficit - candidate.separation_deficit
    if enforce_min_pieces and candidate.min_pieces != best.min_pieces:
        return candidate.min_pieces - best.min_pieces
    if use_score and best.score_distance != candidate.score_distance:
        return best.score_distance - candidate.score_distance
    return best.attempt_number - candidate.attempt_number
