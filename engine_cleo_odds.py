"""Which colour a Cleo figure clones, and how likely each outcome is.

The native choice is CleoCadabraPieceLogic.SwapPerformed 0x5ae2600, game 5.817.
It is a priority search over the colours, not a lottery between them:

    RemoveAll(count < minimum)                        b__5  0x5ae4804
    First(!prevent && matches && leaves && d < limit) b__6  0x5ae5084
    First(!prevent && matches && d < limit)           b__7  0x5ae50d8
    First(leaves && d < limit - 1)                    b__8  0x5ae4868
    nothing found, or pickByCount:
        Where(!prevent || !matches).OrderBy(d).First  b__9  0x5ae5124
        OrderBy(d).First                              b__26_10/11

d = |positions - amount| (0x5ae3a8c). "matches" is any isHighRank combo through
a converted cell right after conversion, before anything is destroyed
(GetAllCombos 0x5ae3848, b__26_13 0x5ae4754): a cascade never counts. "leaves"
is GetPossibleSpecialMoves on the settled probe board (0x5ae3a34).

The two draws (0x5ae3464, 0x5ae34f4) go through Chance 0x5af5c4c, whose test is
Next() % 100 <= percent: Chance(p) succeeds (p + 1) times in 100. "15% prevent"
is really 16%, and Chance(0) still succeeds once in 100.

This module holds only that rule. Whoever calls it decides how good its
matches/leaves inputs are: exact in engine_cleo, an estimate without refill in
move_strategy's plain ranking.
"""
from __future__ import annotations

# Read from data/piece_logic_config.json (slotType 32); limit is the constructor
# default 3 at 0x5ae0c58, which no config entry overrides.
MINIMUM_TARGET_PIECES = 4
DIFFERENCE_LIMIT = 3
PICK_BY_COUNT_PERCENT = 0
PREVENT_PERCENT = (15, 40, 60)
NORMAL_AMOUNT = (8, 7, 6)
OWN_COLOUR_AMOUNT = (7, 6, 5)
SPECIAL_AMOUNT = (8, 7, 6, 5)
BOARD_SPECIAL_AMOUNT = (7, 6, 5)
# clonedSpecialPiecesAmountByPieceUse-<piece>: Foxy, Brocco, Sweep, Monkey.
SPECIFIC_SPECIAL_AMOUNT = (3,)


USES_ORIGIN_NAMES = ("Default", "Booster", "Board")
ORIGIN_BOOSTER = 1


def figure_origin(profile, cell):
    for name in ("cleo_slots", "raw_slots"):
        for slot in profile.get(name) or ():
            if slot.get("value") == 32 and (slot.get("row"), slot.get("col")) == tuple(cell):
                return slot.get("origin")
    return None


def figure_params(profile, cell):
    """Loaded values for the figure at ``cell``, or None when they are absent.

    A figure from the booster has its own logic object under the ability
    (BoosterPiecesLogic), not in GameLogic.specialPiecesLogics, and its counter
    key names that origin (get_PieceUsesThisTurnKey 0x5aed204). These values
    differ per match type: Rumble's prevent list is one flat 10.
    The booster wrapper 0x5a20f54 overrides the clone amount with its
    ...ByActivation lists (Min(ActivatesThisTurn - 1, ...), stored at
    0x5a21350). overrideChanceToCreateExtraMove (0xbc) is only ever written.
    """
    from simulator_capture import decode_dictionary

    booster = profile.get("cleo_booster_fields")
    booster = booster if isinstance(booster, dict) else {}
    booster_logic = booster.get("BoosterPiecesLogic")
    board_logic = profile.get("cleo_piece_logic")
    origin = figure_origin(profile, cell)
    if isinstance(booster_logic, dict) and "chanceToPreventExtraMoveOnColorBasedClone" in booster_logic \
            and (origin == ORIGIN_BOOSTER or origin is None or not isinstance(board_logic, dict)):
        fields, origin = booster_logic, ORIGIN_BOOSTER
    elif isinstance(board_logic, dict):
        fields = board_logic
        origin = fields.get("LogicOrigin") if origin is None else origin
    else:
        return None
    params = {"fields": fields, "uses": None}
    if type(origin) is int and 0 <= origin < len(USES_ORIGIN_NAMES):
        try:
            extra = decode_dictionary(profile.get("board_extra_data"))
            key = "CleoCadabraPiece_PieceUsesThisTurnOrigin_" + USES_ORIGIN_NAMES[origin]
            # Missing key reads 0 natively (0x5ae4388); ValidSwapPerformed adds
            # this swipe before SwapPerformed reads it (0x5951120).
            params["uses"] = int(extra.get(key, 0)) + 1 if extra is not None else None
        except (TypeError, ValueError, AttributeError):
            pass
    activates = profile.get("cleo_activates_this_turn")
    if origin == ORIGIN_BOOSTER and type(activates) is int and activates >= 1:
        params["activates"] = activates
        params["activation_amounts"] = {
            "normal": booster.get("clonedNormalPiecesAmountByActivation"),
            "own": booster.get("clonedBluePiecesAmountByActivation"),
            "special": booster.get("clonedSpecialPiecesAmountByActivation"),
            "board": booster.get("clonedBoardSpecialPiecesAmountByActivation"),
        }
    return params


def by_use(values, uses):
    """List lookup at 0x5ae2d0c: Min(uses - 1, Count - 1)."""
    return values[min(max(uses, 1) - 1, len(values) - 1)]


def chance_probability(percent):
    """How often Chance(percent) succeeds; see the module docstring."""
    return max(0.0, min(1.0, (percent + 1) / 100.0))


def choose(results, prevent, pick_by_count, minimum, limit):
    """Native pick from (color, positions, matches, leaves, delta), or None."""
    results = [r for r in results if len(r[1]) >= minimum]
    selected = None
    for predicate in (
        lambda r: not prevent and r[2] and r[3] and r[4] < limit,
        lambda r: not prevent and r[2] and r[4] < limit,
        lambda r: r[3] and r[4] < limit - 1,
    ):
        selected = next((r for r in results if predicate(r)), None)
        if selected is not None:
            break
    if selected is None or pick_by_count:
        permitted = [r for r in results if not prevent or not r[2]]
        # Equal deltas go to the bigger colour, then the first: traced Color
        # Crush 2026-11-13 (research 20261113_171559 007, nothing matching,
        # 5/5/9 pieces against 7) cloned the nine. Every other Cleo swipe
        # recorded that day keeps its outcome.
        selected = min(permitted or results, key=lambda r: (r[4], -len(r[1])), default=None)
    return selected


def distribution(results, *, prevent_percent, pick_percent=PICK_BY_COUNT_PERCENT,
                 minimum=MINIMUM_TARGET_PIECES, limit=DIFFERENCE_LIMIT, draws=None):
    """{colour: probability} over the two draws; None means nothing is cloned.

    ``draws`` is (pick_by_count, prevent) when the RNG is known: the choice then
    has one certain outcome.
    """
    if draws is not None:
        selected = choose(results, draws[1], draws[0], minimum, limit)
        return {selected[0] if selected else None: 1.0}
    prevent_p = chance_probability(prevent_percent)
    pick_p = chance_probability(pick_percent)
    out = {}
    for pick, pick_weight in ((True, pick_p), (False, 1.0 - pick_p)):
        for prevent, prevent_weight in ((True, prevent_p), (False, 1.0 - prevent_p)):
            selected = choose(results, prevent, pick, minimum, limit)
            color = selected[0] if selected else None
            out[color] = out.get(color, 0.0) + pick_weight * prevent_weight
    return {color: weight for color, weight in out.items() if weight > 0.0}
