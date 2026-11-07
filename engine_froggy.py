"""Known RNG portion of Froggy Fu activation (game 5.817).

BeginNewActivation 0x5a4b338, RollPreferredColorForActivation 0x5a4b604,
PickEntranceExplosionTargets 0x5a4ba10 and PickNormalCandidatesForAttempt
0x5a4dcfc. This produces *all* entrance attempts, not the winning attempt or
lotus positions: the native placement evaluator is not ported yet. Nothing
here may be used as an exact whole-activation prediction.
"""
from dataclasses import dataclass

from engine_rng import EngineRNG
from simulator_capture import decode_dictionary


@dataclass
class FroggyEntrance:
    prefer_energy_adjacent: bool
    mushroom_target: int
    destroy_count: int
    high_score_ratio: int
    preferred_color: int  # Native SlotColor, not the simulator colour.
    attempts: list[list[tuple[int, int]]]  # (row, column), destruction order.
    rng_after: EngineRNG


def _activation_value(values, activation, default=0):
    if not values:
        return default
    return values[max(0, min(int(activation) - 1, len(values) - 1))]


def _roll_range(rng, ranges, activation):
    bounds = _activation_value(ranges, activation, [])
    if not bounds:
        return 0
    minimum = max(0, int(bounds[0]))
    maximum = max(minimum, int(bounds[1])) if len(bounds) > 1 else minimum
    return rng.range(minimum, maximum + 1) if maximum >= 1 else 0


def roll_preferred_color(rng, weights, game_colors):
    """Filter positive weights, OrderBy((byte)Key), then Next(sum).

    The filter is 0x5a567a8 and the sorting selector is 0x5a5625c.
    SlotColor.None (1) is returned without a draw when no weight survives.
    """
    allowed = None if game_colors is None else set(map(int, game_colors))
    decoded = decode_dictionary(weights) if weights and "entries" in weights else (weights or {})
    pool = sorted((int(color), int(weight))
                  for color, weight in decoded.items()
                  if int(weight) > 0 and (allowed is None or int(color) in allowed))
    total = sum(weight for _, weight in pool)
    if total <= 0:
        return 1
    pick = rng.next(total)
    for color, weight in pool:
        pick -= weight
        if pick < 0:
            return color
    raise AssertionError("weighted colour selection exhausted")


def entrance_attempts(rng, slots, *, mushroom_target, destroy_count,
                      high_score_ratio, simulated_runs, blocked_cells=()):
    """Consume the attempt-generation RNG, without evaluating any attempt.

    Caller supplies GetCell == 3 coordinates as blocked_cells; raw SlotModel
    fields alone do not encode that CellModel property. Input slots are never
    mutated. Every attempt starts from the same original candidate pools.
    """
    slots = sorted(slots, key=lambda s: (int(s["x"]), int(s["y"])))
    blocked = set(blocked_cells)
    eligible = [s for s in slots if s["canBeMatched"] and s["movable"]
                and (int(s["y"]), int(s["x"])) not in blocked]
    mushrooms = [(int(s["y"]), int(s["x"])) for s in eligible if int(s["value"]) == 0x13]
    normals = [s for s in eligible if int(s["value"]) == 0]
    ratio = max(0, min(100, int(high_score_ratio)))
    attempts = []
    for _ in range(max(1, int(simulated_runs))):
        take = max(0, min(int(mushroom_target), len(mushrooms)))
        chosen = rng.shuffled(mushrooms)[:take] if take else []
        pool = list(normals)
        weights = [100 + (min(int(s["score"]), 5) - 1) * ratio for s in pool]
        total = sum(weights)
        for _ in range(min(max(0, int(destroy_count) - len(chosen)), len(pool))):
            if total <= 0:
                break
            pick = rng.next(total)
            for i, weight in enumerate(weights):
                pick -= weight
                if pick < 0:
                    slot = pool.pop(i)
                    chosen.append((int(slot["y"]), int(slot["x"])))
                    total -= weights.pop(i)
                    break
        attempts.append(chosen)
    return attempts


def preview_entrance(profile, slots, *, activation, preferred_color_fix,
                     blocked_cells=()):
    """Preview the known part on an RNG clone; never advance the live profile.

    activation is the one-based native ActivatesThisTurn value. Engine fix 7
    must be supplied explicitly rather than guessed from a capture's version.
    """
    fields = profile["froggy_booster_fields"]
    rng = EngineRNG.from_capture(profile)
    # 0x5a4b598: a chance below 1 returns False without drawing.
    chance = int(_activation_value(fields["chanceToPlaceNextToEnergyMatchByActivation"], activation))
    prefer = chance >= 1 and rng.chance(chance)
    ratio = int(_activation_value(fields["highScorePieceRatioByActivation"], activation))
    mushrooms = _roll_range(rng, fields["entranceMushroomCountRangeByActivation"], activation)
    destroy = _roll_range(rng, fields["entranceDestroyCountRangeByActivation"], activation)
    color = 1
    if preferred_color_fix:
        color = roll_preferred_color(rng, _activation_value(
            fields["placementWeightByColorByActivation"], activation, {}),
            profile["spawning"].get("gameColors"))
    attempts = entrance_attempts(
        rng, slots, mushroom_target=mushrooms, destroy_count=destroy,
        high_score_ratio=ratio, simulated_runs=fields["simulatedRuns"],
        blocked_cells=blocked_cells)
    return FroggyEntrance(prefer, mushrooms, destroy, ratio, color, attempts, rng)
