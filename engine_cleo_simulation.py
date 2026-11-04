"""Boundary between the Cleo selector and an exact whole-swipe simulation.

The selector in engine_cleo is ported separately. A whole action also needs
the native merge representation: ValidSwapPerformed 0x594fa08 clears source
and installs a MergeSwapPiece at target (0x5950454..0x59504d0). GetSlotCombos
0x5929394 tests its original pieces via MergeSwapData, while DamageSlots
0x596fac8 resolves it using GetSurvivingPiece 0x5932120. Replacing that marker
with the ordinary partner's colour is not a proven equivalent.

The supported subset requires every probe to damage the HP1 marker in an
initial triple, before refill. Other lifecycle/origin branches raise. No
probability model's representative board enters ExactRefillSession or Lab.
"""
from copy import deepcopy

from engine_refill import UnsupportedRefill, color_maps, simulator_refill
from simulator_capture import decode_dictionary


def _reject(reason):
    raise UnsupportedRefill("Cleo: " + reason)


def _ordinary_extra(board, special):
    """GetPossibleSpecialMoves subset with only ordinary, single-colour slots."""
    import move_strategy as ms

    if any(v for row in special for v in row):
        _reject("possible-special-moves with surviving specials not ported")
    for candidate in ms.generate_candidates(board, special):
        matches = ms.find_matches(candidate.board, False, candidate.special_board)
        if any(len(match.cells) >= 4 and
               (candidate.start in match.cells or candidate.target in match.cells)
               for match in matches):
            return True
    return False


def _resolve(model, board, special, positions, target, *, final=False):
    """Only triples that damage the merge marker before any drop/refill.

    Native probes scan conversionPositions (0x5ae3848); final callback scans
    all slots (0x5ae4978). The type-9 forced merge combo is already present in
    final combosToDestroy (0x5950dcc). Here target must be damaged by an
    ordinary triple in either case, making the HP1 marker Empty before refill
    in both representations (DamageSlots 0x596fc1c..0x596fc48).
    """
    import move_strategy as ms

    matches = ms.find_matches(board, False, special)
    if not final:
        matches = [m for m in matches if m.cells.intersection(positions)]
    seen = set()
    for match in matches:
        if (len(match.cells) != 3 or match.kind != "three"
                or (len({p[0] for p in match.cells}) != 1
                    and len({p[1] for p in match.cells}) != 1)):
            _reject("initial high-rank / shaped conversion combo not ported")
        if seen.intersection(match.cells):
            _reject("overlapping conversion combos not ported")
        seen.update(match.cells)
    if target not in seen:
        _reject("native merge placeholder survives initial conversion scan")
    # No first-layer special is created, so conversion-dependent origins do
    # not affect this subset. Source is already Empty. Target's colour is
    # used only to scan matches; its slot is removed before refill.
    sentinel = ms.MoveCandidate((-1, -1), (-1, -1), ms.Direction.RIGHT,
                                deepcopy(board), deepcopy(special))
    with ms.engine_refill_active(simulator_refill(model), model.peek_draws,
                                 model.ball_spent, model.random_special):
        result = ms.simulate_candidate(sentinel, initial_matches=matches, mode="None")
    if any(int(v) <= 0 for row in result.board for v in row):
        _reject("clone cascade did not settle")
    if result.created_specials or result.activated_specials:
        _reject("clone cascade special origin / activation not certified")
    if any("random_outcomes" in e.get("type", "") or
           e.get("type") in ("uncertain_refill_boundary", "special_activation")
           for e in result.intent_events):
        _reject("unported clone cascade effect")
    _ordinary_extra(result.board, result.special_board)
    return result


def simulate_swipe(model, candidate, *, allow_square_matches=False, mode="None", **kwargs):
    """Reject the unported whole action; the live caller uses ordinary ranking.

    Supports ordinary HP1 slots only, when every colour probe destroys target
    in an initial triple. All other merge lifecycles are explicit boundaries.
    Probes and failures leave the caller's RNG/spawn state untouched.
    """
    from engine_cleo import CleoPieceModel, select_clone
    import move_strategy as ms

    config = CleoPieceModel.from_profile(model.profile)
    rules = model.profile.get("rules") or {}
    extra = decode_dictionary(rules.get("_extraData")) or {}
    if (allow_square_matches or mode != "None" or rules.get("boardModelName") != 1
            or any(bool(v) for v in extra.values())
            or any(rules.get(k) for k in ("allSpecialsLightning", "everyMatchIsSpecial",
                                         "specialsAutoExplode", "extraMoveRandomSpecial"))
            or model.billie is not None):
        _reject("board rule layers / square / passive branch not ported")
    slots = {(s["row"], s["col"]): s for s in config.slots}
    n = len(candidate.board)
    if (n < 3 or any(len(row) != n for row in candidate.board)
            or len(candidate.special_board) != n
            or any(len(row) != n for row in candidate.special_board)
            or set(slots) != {(r, c) for r in range(n) for c in range(n)}):
        _reject("raw / candidate dimensions differ")
    start, target = tuple(candidate.start), tuple(candidate.target)
    if start not in slots or target not in slots or abs(start[0]-target[0]) + abs(start[1]-target[1]) != 1:
        _reject("invalid raw swipe endpoints")
    if (sum(s["value"] == 32 for s in slots.values()) != 1
            or sum(slots[p]["value"] == 32 for p in (start, target)) != 1):
        _reject("exactly one Cleo at swipe endpoints required")
    _, to_sim = color_maps(model.profile)
    before = [[to_sim.get(slots[r, c]["color"]) for c in range(n)] for r in range(n)]
    for s in slots.values():
        if s["value"] not in (0, 32):
            _reject("special/board-special slot not ported")
        if s["value"] == 0 and (s.get("hitPoints") != 1 or s.get("movable") is not True
                or s.get("canBeMatched") is not True or s.get("color2") not in (0, 1)
                or s.get("status") != 0 or s.get("skipDestroyTillMoveEnds") is not False):
            _reject("ordinary raw slot flags / HP missing or unsupported")
        if s["color"] not in to_sim:
            _reject("raw primary colour missing")
    expected = deepcopy(before)
    expected[start[0]][start[1]], expected[target[0]][target[1]] = before[target[0]][target[1]], before[start[0]][start[1]]
    expected_special = [[0 for _ in range(n)] for _ in range(n)]
    cleo_after = target if slots[start]["value"] == 32 else start
    expected_special[cleo_after[0]][cleo_after[1]] = ms.SPECIAL_CLEO_BUG
    # Cleo is displayed as 99, while raw slots preserve its underlying colour.
    expected[cleo_after[0]][cleo_after[1]] = 99
    if (list(map(list, candidate.board)) != expected
            or list(map(list, candidate.special_board)) != expected_special):
        _reject("raw slots do not describe this candidate")
    partner = next(slots[p] for p in (start, target) if slots[p]["value"] != 32)
    partner_color = to_sim[partner["color"]]
    working = deepcopy(before)
    working[start[0]][start[1]] = ms.EMPTY
    working[target[0]][target[1]] = partner_color
    special = [[0 for _ in range(n)] for _ in range(n)]
    stable = deepcopy(before)
    original_cleo = start if slots[start]["value"] == 32 else target
    stable[original_cleo[0]][original_cleo[1]] = ms.EMPTY
    if ms.find_matches(stable, False, special):
        _reject("raw board already has unresolved matches")
    action_model = model.clone()

    def converted(positions):
        board = deepcopy(working)
        for r, c in positions:
            board[r][c] = partner_color
        return board

    def probe(positions):
        # select_clone calls this only AFTER its two main Chance draws. Do
        # not reset_action: native Clone preserves the running spawnedColors.
        clone = action_model.clone()
        result = _resolve(clone, converted(positions), special, positions, target)
        return bool(result.extra_moves), _ordinary_extra(result.board, result.special_board)

    selection = select_clone(config, candidate, action_model.rng, probe)
    result = _resolve(action_model, converted(selection.positions), special,
                      selection.positions, target, final=True)
    result.candidate = candidate
    result.intent_events.insert(0, {"type": "cleo_exact_swipe", "color": selection.color,
                                 "positions": [list(p) for p in selection.positions],
                                 "scope": "ordinary_hp1_target_initial_triple"})
    # The old raw slots/uses describe the input board. Do not reuse them for
    # a followed action after the figure and columns have moved.
    action_model.profile = dict(action_model.profile)
    for key in ("raw_slots", "cleo_slots", "cleo_piece_logic"):
        action_model.profile.pop(key, None)
    model.__dict__.update(action_model.__dict__)
    return result
