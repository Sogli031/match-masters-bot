"""Cleo figure's whole-colour selector, ported from game 5.817 ARM64.

SwapPerformed 0x5ae2600, predicates 0x5ae4704..0x5ae514c. This is NOT
CleoCadabra.Use (booster activation). Clone simulation is supplied by caller;
unsupported state must raise UnsupportedRefill rather than score a guess.
Coordinates are simulator (row, col); colours/slot values are engine values.
"""
from dataclasses import dataclass
from copy import deepcopy

from engine_cleo_odds import choose
from engine_refill import UnsupportedRefill
from simulator_capture import decode_dictionary


@dataclass(frozen=True)
class CleoPieceModel:
    fields: dict
    slots: tuple
    uses: int  # includes the swipe being simulated (getter is called after increment)
    player_color: int
    opponent_color: int

    @classmethod
    def from_profile(cls, profile, *, uses=None, slots=None):
        fields = profile.get("cleo_piece_logic")
        slots = profile.get("raw_slots") if slots is None else slots
        if not isinstance(fields, dict) or not isinstance(slots, list) or not slots:
            raise UnsupportedRefill("Cleo: loaded figure fields / raw slots missing")
        required = ("cloneToWholeColor", "cloneToWholeColorMinimumTargetPieces",
                    "chanceToPickColorOnlyByPieceCount", "maxAllowedDifferenceFromDeltaForExtraMoveMatch",
                    "chanceToPreventExtraMoveOnColorBasedClone", "clonedNormalPiecesAmountByPieceUse",
                    "clonedBluePiecesAmountByPieceUse", "maxAllowedClonedPieces", "overrideCloneAmount")
        if any(key not in fields for key in required):
            raise UnsupportedRefill("Cleo: incomplete loaded figure configuration")
        if fields["cloneToWholeColor"] is not True:
            raise UnsupportedRefill("Cleo: non-whole-colour branch is not ported")
        origin = fields.get("LogicOrigin")
        config = fields.get("config")
        # The getter dereferences SpecialPiecesLogic.config (+0x30), then
        # SpecialPieceModel.slotType (+0x10). slotType is not a logic field.
        if (not isinstance(config, dict) or config.get("slotType") != 32
                or fields.get("<PieceType>k__BackingField", 32) != 32
                or type(origin) is not int or origin not in (0, 1, 2)):
            raise UnsupportedRefill("Cleo: raw slotType / LogicOrigin missing or unsupported")
        players = profile.get("players") or []
        current = profile.get("state", {}).get("currentPlayerIndex")
        me = next((p for p in players if (p.get("model") or {}).get("index") == current), None)
        if me is None:
            raise UnsupportedRefill("Cleo: current player index missing")
        player = me.get("model") or {}
        if player.get("specialAbilityType") == 53:
            raise UnsupportedRefill("Cleo: booster swipe wrapper / activation overrides not ported")
        color = player.get("slotType")
        if color not in (2, 4):
            raise UnsupportedRefill("Cleo: unsupported player colour")
        opponent = next((p for p in players if p is not me), None)
        opponent_color = ((opponent or {}).get("model") or {}).get("slotType", 2 if color == 4 else 4)
        if uses is None:
            # get_PieceUsesThisTurnKey 0x5aed204 boxes SlotValueType and
            # SpecialPiecesLogicOrigin enums. Literal 40972, ELF relocation
            # 0x70993d8 -> 0x72f1ba8 -> 0xa0014019, is this exact template.
            key = "CleoCadabraPiece_PieceUsesThisTurnOrigin_" + ("Default", "Booster", "Board")[origin]
            try:
                extra = decode_dictionary(profile.get("board_extra_data"))
                if extra is None or any(not isinstance(k, str) for k in extra):
                    raise ValueError("complete board extraData unavailable")
                raw_uses = extra.get(key, 0)  # native missing-key return, 0x5ae4388
                if type(raw_uses) not in (int, str) or isinstance(raw_uses, bool):
                    raise ValueError("unreadable usage counter")
                uses = int(raw_uses) + 1
            except (KeyError, ValueError, TypeError) as exc:
                raise UnsupportedRefill("Cleo: exact PieceUsesThisTurn counter missing") from exc
        if not isinstance(uses, int) or uses < 1:
            raise UnsupportedRefill("Cleo: exact PieceUsesThisTurn counter missing")
        cells = set()
        for slot in slots:
            if any(key not in slot for key in ("row", "col", "color", "value", "canBeMatched")):
                raise UnsupportedRefill("Cleo: incomplete raw slot flags / colour")
            cell = (slot["row"], slot["col"])
            if cell in cells:
                raise UnsupportedRefill("Cleo: duplicate raw slot")
            cells.add(cell)
            if slot["value"] not in (0, 4, 5, 6, 7, 8, 16, 17, 18, 19, 20, 32):
                raise UnsupportedRefill("Cleo: raw special eligibility branch not ported")
        return cls(deepcopy(fields), tuple(deepcopy(slots)), uses, color, opponent_color)


@dataclass(frozen=True)
class CleoSelection:
    positions: tuple
    color: int | None
    clone_amount: int
    prevent_extra: bool
    pick_by_count: bool


def select_clone(model, candidate, rng, probe, allow_square_matches=False):
    """Select native colour; probe(positions) -> (matches_extra, leaves_extra).

    probe must start a fresh clone of the engine/RNG AFTER the two Chance
    calls, and must reject branches whose full conversion/cascades aren't ported.
    It must not mutate the main RNG. Neither the candidate colour nor a target
    recording's board may be used to seed or repair the selection.
    """
    fields = model.fields
    slots = {(s["row"], s["col"]): dict(s) for s in model.slots}
    start, target = tuple(candidate.start), tuple(candidate.target)
    if start not in slots or target not in slots:
        raise UnsupportedRefill("Cleo: raw swap endpoints missing")
    endpoints = (slots[start], slots[target])
    if sum(s["value"] == 32 for s in endpoints) != 1:
        raise UnsupportedRefill("Cleo: expected exactly one figure in swipe")
    partner = next(s for s in endpoints if s["value"] != 32)
    if partner["value"] != 0 or partner["canBeMatched"] is not True:
        raise UnsupportedRefill("Cleo: special/board-special partner not ported")
    # The callback owns an already-swapped board; raw slots here are PRE-swap.
    slots[start], slots[target] = slots[target], slots[start]
    n = len(candidate.board)
    if set(slots) != {(r, c) for r in range(n) for c in range(n)}:
        raise UnsupportedRefill("Cleo: complete raw square board required")

    def indexed(name):
        values = fields[name]
        if not isinstance(values, (tuple, list)) or not values or any(type(v) is not int for v in values):
            raise UnsupportedRefill("Cleo: invalid loaded " + name)
        return values[min(model.uses - 1, len(values) - 1)]

    amount = indexed("clonedBluePiecesAmountByPieceUse" if partner["color"] == model.player_color
                     else "clonedNormalPiecesAmountByPieceUse")
    override = fields["overrideCloneAmount"]
    if type(override) is not int:
        raise UnsupportedRefill("Cleo: invalid clone override")
    if override >= 1:
        amount = override

    def collect(eligible):
        groups = {}
        for c in range(n):
            for r in range(n):
                # ValidSwapPerformed has already installed Empty at source
                # and MergeSwapPiece at target before invoking the figure.
                # Their colours are Empty/None, outside eligibleColors; do
                # not insert the hidden Cleo/partner colour as an empty group.
                if (r, c) in (start, target):
                    continue
                slot = slots[r, c]
                color = slot["color"]
                if color not in eligible:
                    continue
                # Native creates the colour dictionary entry even for a slot
                # excluded below; empty groups still get a clone probe.
                positions = groups.setdefault(color, [])
                value = slot["value"]
                if 16 <= value <= 20 or value != 0:
                    continue
                if slot["canBeMatched"] is not True:
                    continue
                positions.append((r, c))
        return groups

    eligible = [3, 5, 6, 7, 8, model.opponent_color]
    eligible = [color for color in eligible if color != partner["color"]]
    groups = collect(eligible)
    if not any(groups.values()):
        groups = collect([model.player_color])
    # 0x5ae3464 then 0x5ae34f4: both ALWAYS draw, even Chance(0).
    pick_by_count = rng.chance(fields["chanceToPickColorOnlyByPieceCount"])
    prevent = rng.chance(indexed("chanceToPreventExtraMoveOnColorBasedClone"))
    results = []
    for color, positions in groups.items():
        matches, leaves = probe(tuple(positions))
        results.append((color, positions, bool(matches), bool(leaves), abs(len(positions) - amount)))
    selected = choose(results, prevent, pick_by_count,
                      fields["cloneToWholeColorMinimumTargetPieces"],
                      fields["maxAllowedDifferenceFromDeltaForExtraMoveMatch"])
    if selected is None:
        return CleoSelection((), None, amount, prevent, pick_by_count)
    positions = selected[1]
    cap = fields["maxAllowedClonedPieces"]
    if type(cap) is not int or cap < 0:
        raise UnsupportedRefill("Cleo: invalid clone cap")
    if len(positions) > cap:
        # Generic shuffle 0x3c13d70: OrderBy(_ => random.Next()).ToList();
        # 0x4073ad8 is its captured-RandomWrapper selector. Ties are stable.
        positions = rng.random_key_order(positions, selector="next")[:cap]
    return CleoSelection(tuple(positions), selected[0], amount, prevent, pick_by_count)
