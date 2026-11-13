"""Boundary between the Cleo selector and an exact whole-swipe simulation.

The selector in engine_cleo is ported separately. A whole action also needs
the native merge representation: ValidSwapPerformed 0x594fa08 clears source
and installs a MergeSwapPiece at target (0x5950454..0x59504d0). GetSlotCombos
0x5929394 tests its original pieces via MergeSwapData, while DamageSlots
0x596fac8 resolves it using GetSurvivingPiece 0x5932120. Replacing that marker
with the ordinary partner's colour is not a proven equivalent.

The supported subset damages the HP1 marker before refill. It includes
ordinary triples and the booster line-four path with auto-explosion.
An unported probe may proceed only if it cannot change the selected colour.
"""
from copy import deepcopy

from engine_refill import UnsupportedRefill, color_maps, simulator_refill
from simulator_capture import decode_dictionary


SCORE_MARKET_BOARD = 20
COLOR_CRUSH_BOARD = 28


def _reject(reason):
    raise UnsupportedRefill("Cleo: " + reason)


_SQUARE = [False]


def _ordinary_extra(board, special, wide=False):
    """GetPossibleSpecialMoves subset with only ordinary, single-colour slots."""
    import move_strategy as ms

    if any(v for row in special for v in row) and not wide:
        _reject("possible-special-moves with surviving specials not ported")
    # Score Market: coloured specials (hearts, lines) count as pieces of
    # their colour; checked against the 2026-11-09 recording (tests).
    for candidate in ms.generate_candidates(board, special):
        matches = ms.find_matches(candidate.board, _SQUARE[0], candidate.special_board)
        if any(len(match.cells) >= 4 and
               (candidate.start in match.cells or candidate.target in match.cells)
               for match in matches):
            return True
    return False


def _resolve(model, board, special, positions, target, *, final=False, auto_explode=False,
             wide=False, mode="None"):
    """Resolve supported line matches that consume the marker before refill.

    Native probes scan conversionPositions (0x5ae3848); final callback scans
    all slots (0x5ae4978). The type-9 forced merge combo is already present in
    final combosToDestroy (0x5950dcc). Here target must be damaged by an
    supported line match in either case, making the HP1 marker Empty before refill
    in both representations (DamageSlots 0x596fc1c..0x596fc48).
    """
    import move_strategy as ms

    matches = ms.find_matches(board, _SQUARE[0], special)
    if not final:
        matches = [m for m in matches if m.cells.intersection(positions)]
    seen = set()
    for match in matches:
        if not wide and (match.kind not in (("three", "four") if auto_explode else ("three",))
                or (len({p[0] for p in match.cells}) != 1
                    and len({p[1] for p in match.cells}) != 1)):
            _reject("initial high-rank / shaped conversion combo not ported")
        if (not wide and match.kind == "four"
                and max(match.cells, key=lambda p: (p[1], p[0])) == target):
            _reject("conversion special would replace the merge marker")
        if seen.intersection(match.cells):
            _reject("overlapping conversion combos not ported")
        seen.update(match.cells)
    board = deepcopy(board)
    special = deepcopy(special)
    merge_first = bool(wide and special[target[0]][target[1]])
    if target not in seen and wide and special[target[0]][target[1]]:
        # ValidSwapPerformed's forced rank-9 combo destroys a special partner
        # on the target, which fires it like any destroyed special. That combo
        # is queued at swap time, ahead of the conversion's combos, so the
        # partner fires first: Square Match 161938 011->012 (traced) bombs
        # (6,6) before the conversion's (5,1), so crosshair (6,4) draws first.
        matches = [ms.MatchGroup(frozenset({target}), board[target[0]][target[1]], "three")] + list(matches)
        seen.add(target)
    if target not in seen:
        if not wide:
            _reject("native merge placeholder survives initial conversion scan")
        # The forced merge combo destroys the HP1 placeholder even when no
        # conversion line reaches it: Score Market 005->006 (2026-11-09) made
        # no match at all and still refilled both the source and the target.
        board[target[0]][target[1]] = ms.EMPTY
        special[target[0]][target[1]] = ms.EMPTY
    if auto_explode and final and not any(
            match.kind == "four" and target in match.cells for match in matches):
        _reject("final merge outside a line four not ported")
    # Score Market: a conversion combo's special starts at its first x-major
    # cell, the rule spray and jelly conversions use (move_strategy reads it
    # through _SPRAY_NO_SWAP_ACTIVE for cascade 1). 017->018: (6,0), not (6,3).
    previous_no_swap = ms._SPRAY_NO_SWAP_ACTIVE
    previous_first = ms._CHAIN_FIRST_CELLS
    previous_crush = ms._COLOR_CRUSH_SWAP_CELLS
    ms._SPRAY_NO_SWAP_ACTIVE = previous_no_swap or wide
    if merge_first:
        ms._CHAIN_FIRST_CELLS = frozenset({target})
    # Color Crush (traced 2026-11-13 17:15, research 20261113_171559 010):
    # ColorCrushBoard.AfterPerformedSwap crushes a colour only through a combo
    # on the swipe's merge cell; a clone combo elsewhere (a T at (0,1)-(3,1),
    # merge cell (0,5)) clears just its own cells. The forced one-cell merge
    # combo does not count (007: a special partner's merge, no crush).
    ms._COLOR_CRUSH_SWAP_CELLS = frozenset({target})
    try:
        result = _simulate_conversion(model, board, special, matches, auto_explode, mode)
    finally:
        ms._SPRAY_NO_SWAP_ACTIVE = previous_no_swap
        ms._CHAIN_FIRST_CELLS = previous_first
        ms._COLOR_CRUSH_SWAP_CELLS = previous_crush
    return _check_conversion(result, matches, auto_explode, wide)


def _simulate_conversion(model, board, special, matches, auto_explode, mode="None"):
    import move_strategy as ms

    # GetFireworks as in strategy_lab.simulation.engine_refill: a cloned
    # Lightning draws the engine's own targets, not random ones.
    with ms.engine_refill_active(simulator_refill(model), model.peek_draws,
                                 model.ball_spent, model.random_special,
                                 fireworks=model.fireworks_targets):
        if not matches:
            # Only the source and the placeholder are empty: drop and refill
            # them, then the refill's own cascades run as usual.
            origins = [[(r, c) for c in range(len(row))] for r, row in enumerate(board)]
            board, special, _ = ms._drop_and_refill(board, special, origins, chain_combos=0)
            initial = None
        else:
            initial = matches
        # Use combo origins for the conversion lines, with no swap-cell
        # override for a high-rank combo (final callback 0x5ae4a1c).
        sentinel = ms.MoveCandidate((-1, -1), (-1, -1), ms.Direction.RIGHT,
                                    deepcopy(board), deepcopy(special))
        # ``mode``: the board's own match rules for the clone cascade, e.g.
        # Color Crush, where a match crushes its whole colour (2026-11-13
        # research 20261113_153230 004: the clones' colour went board-wide).
        result = ms.simulate_candidate(sentinel, initial_matches=initial, mode=mode,
                                       allow_square_matches=_SQUARE[0],
                                       explode_created_specials_immediately=auto_explode)
    return result


def _check_conversion(result, matches, auto_explode, wide):
    import move_strategy as ms

    if not matches:
        result.cascade_matches.insert(0, [])
        # The figure's cell and the placeholder: a played swipe, not an
        # illegal one, even though nothing matched.
        result.cleared_cells += 2
    if any(int(v) <= 0 for row in result.board for v in row):
        _reject("clone cascade did not settle")
    if not auto_explode and not wide and (result.created_specials or result.activated_specials):
        _reject("clone cascade special origin / activation not certified")
    for event in result.intent_events:
        kind = event.get("type", "")
        if wide:
            # Score Market: line, bomb and heart (clears its colour) specials
            # resolve deterministically with the exact refill; anything
            # random is still refused.
            # A Lightning with the engine's own targets (GetFireworks) is
            # deterministic too: Cleo cloning a Lightning partner (Color
            # Crush 2026-11-13, research 20261113_153230 021/029).
            # A crosshair (Square Match) with GetCrosshair's own targets as
            # well (Square Match 2026-11-13, research 20261113_160012 004->005).
            if ("random_outcomes" in kind or kind == "uncertain_refill_boundary"
                    or (kind == "special_activation"
                        and event["special"] not in ("horizontal", "vertical", "bomb", "heart")
                        and not (event["special"] == "lightning" and ms._lightning_targets_exact())
                        and event["special"] != "crosshair")
                    or (kind == "special_effect" and event.get("special") == "crosshair"
                        and not event.get("exact_targets"))):
                _reject("unported clone cascade effect")
            continue
        if ("random_outcomes" in kind or kind == "uncertain_refill_boundary"
                or (kind == "special_creation" and
                    (event["cascade"] != 1 or event["special"] not in ("horizontal", "vertical")))
                or (kind == "special_activation" and
                    event["special"] not in ("horizontal", "vertical"))):
            _reject("unported clone cascade effect")
    _ordinary_extra(result.board, result.special_board, wide)
    return result


def simulate_swipe(model, candidate, *, allow_square_matches=False, mode="None", **kwargs):
    """Simulate the supported single-figure swipe on ordinary HP1 slots."""
    from engine_cleo import CleoPieceModel, select_clone
    import move_strategy as ms

    config = CleoPieceModel.from_profile(model.profile)
    rules = model.profile.get("rules") or {}
    extra = decode_dictionary(rules.get("_extraData")) or {}
    booster_figure = config.activation_amounts is not None if isinstance(config, CleoPieceModel) else False
    auto_explode = (mode == "Moves Multiplier" and rules.get("boardModelName") == 34
                    and rules.get("specialsAutoExplode") is True
                    and rules.get("specialsAutoExplodeOnMatchOnly") is True
                    and booster_figure)
    # Score Market (board 20) resolves ordinary swipes like board 1; there the
    # Cleo is the booster's figure (2026-11-09 recording, see tests).
    # Color Crush (board 28) resolves a Cleo swipe the same way, a second Cleo
    # and resting specials included (2026-11-13 15:29:06, research
    # 20261113_152834 004->005: board, specials, RNG and moves exact). One
    # recording so far: only the refill check measures it (``measure_only``),
    # the planner keeps the boundary.
    # Since 2026-11-13 17:30 the planner takes it too: the traced 17:15 game
    # replays every Cleo swipe exact (3 of 3), all recorded 8 of 11.
    color_crush = rules.get("boardModelName") == COLOR_CRUSH_BOARD
    ordinary = ((mode == "None" or color_crush) and not rules.get("specialsAutoExplode")
                and (rules.get("boardModelName") == 1 and not booster_figure
                     or rules.get("boardModelName") == SCORE_MARKET_BOARD or color_crush))
    # Square Match (board 0 with square matches) and Super Sized (plain board
    # 0, 8x8) with the booster's Cleo take the wide branch, for the planner
    # too: every Cleo swipe the bot played on 2026-11-13 replays exact (Square
    # Match 18 of 18, special partners included; Super Sized 3 of 3, research
    # 20261113_170250). Color Crush as well (see above).
    square_board = allow_square_matches and rules.get("boardModelName") == 0
    _SQUARE[0] = bool(square_board)
    plain_booster_board = (not allow_square_matches and booster_figure
                           and rules.get("boardModelName") == 0)
    if square_board or plain_booster_board:
        ordinary = not rules.get("specialsAutoExplode")
        color_crush = True  # the same wide branch as Color Crush / Score Market
    if ((allow_square_matches and not square_board) or not (ordinary or auto_explode)
            or any(bool(v) for k, v in extra.items() if not (square_board and k == "allowSquareMatches"))
            or any(rules.get(k) for k in ("allSpecialsLightning", "everyMatchIsSpecial",
                                         "extraMoveRandomSpecial"))
            or model.billie is not None):
        if booster_figure:
            raise UnsupportedRefill("Cleo booster figure: board rule layers / square / passive branch not ported")
        _reject("board rule layers / square / passive branch not ported")
    wide = ordinary and (rules.get("boardModelName") == SCORE_MARKET_BOARD or color_crush)
    cascade_mode = mode if color_crush else "None"
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
    if sum(slots[p]["value"] == 32 for p in (start, target)) != 1:
        _reject("exactly one Cleo at swipe endpoints required")
    from engine_cleo import SPECIAL_PARTNER_VALUES
    partner_cell = start if slots[target]["value"] == 32 else target
    partner_value = slots[partner_cell]["value"]
    if partner_value != 0 and not (wide and partner_value in SPECIAL_PARTNER_VALUES):
        _reject("special partner not ported")
    from engine_refill import ENGINE_SPECIAL_TO_SIM
    partner_special = ENGINE_SPECIAL_TO_SIM[partner_value]
    # The partner's special travels with it; it is placed below.
    resting = {p: ENGINE_SPECIAL_TO_SIM[s["value"]] for p, s in slots.items()
               if s["value"] not in (0, 32) and s["value"] in ENGINE_SPECIAL_TO_SIM
               and p != partner_cell}
    others = {p for p, s in slots.items() if s["value"] == 32 and p not in (start, target)}
    if not wide and others:
        _reject("exactly one Cleo at swipe endpoints required")
    if not wide and resting:
        _reject("special/board-special slot not ported")
    _, to_sim = color_maps(model.profile)
    before = [[to_sim.get(slots[r, c]["color"]) for c in range(n)] for r in range(n)]
    for p, s in slots.items():
        if s["value"] not in (0, 32) and p not in resting and p != partner_cell:
            _reject("special/board-special slot not ported")
        if auto_explode and s["value"] == 32 and (
                s.get("origin") != 1 or s.get("hitPoints") != 1
                or s.get("canBeMatched") is not False or s.get("autoDestruct") is not True):
            _reject("unsupported raw booster figure flags")
        if s["value"] == 0 and (s.get("hitPoints") != 1 or s.get("movable") is not True
                or s.get("canBeMatched") is not True or s.get("color2") not in (0, 1)
                or s.get("status") != 0 or s.get("skipDestroyTillMoveEnds") is not False):
            _reject("ordinary raw slot flags / HP missing or unsupported")
        if s["color"] not in to_sim:
            _reject("raw primary colour missing")
    expected = deepcopy(before)
    expected[start[0]][start[1]], expected[target[0]][target[1]] = before[target[0]][target[1]], before[start[0]][start[1]]
    expected_special = [[0 for _ in range(n)] for _ in range(n)]
    for (r, c), value in resting.items():
        expected_special[r][c] = value
    for r, c in others:
        expected_special[r][c] = ms.SPECIAL_CLEO_BUG
        expected[r][c] = 99
    cleo_after = target if slots[start]["value"] == 32 else start
    partner_after = start if cleo_after == target else target
    expected_special[partner_after[0]][partner_after[1]] = partner_special
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
    for (r, c), value in resting.items():
        special[r][c] = value
    for r, c in others:
        special[r][c] = ms.SPECIAL_CLEO_BUG
        working[r][c] = 99
    # A special partner sits on the merge target with its special.
    special[target[0]][target[1]] = partner_special
    stable = deepcopy(before)
    original_cleo = start if slots[start]["value"] == 32 else target
    stable[original_cleo[0]][original_cleo[1]] = ms.EMPTY
    for r, c in others:
        stable[r][c] = 99
    stable_special = deepcopy(special)
    stable_special[target[0]][target[1]] = 0
    if partner_special:
        stable_special[partner_cell[0]][partner_cell[1]] = partner_special
    if ms.find_matches(stable, _SQUARE[0], stable_special):
        _reject("raw board already has unresolved matches")
    action_model = model.clone()

    def converted(positions):
        """Board and specials after the clone: a special partner's clones
        carry its special too (2026-11-09 Score Market 017->018)."""
        board, specials = deepcopy(working), deepcopy(special)
        for r, c in positions:
            board[r][c] = partner_color
            specials[r][c] = partner_special
        return board, specials

    def probe(positions):
        # select_clone calls this only AFTER its two main Chance draws. Do
        # not reset_action: native Clone preserves the running spawnedColors.
        clone = action_model.clone()
        board, specials = converted(positions)
        # The first predicate only needs the conversion's own combos: any
        # combo above a triple through a converted piece (0x5ae3848).
        initial_scan = [m for m in ms.find_matches(board, _SQUARE[0], specials)
                        if m.cells.intersection(positions)]
        high_rank = any(m.kind != "three" for m in initial_scan)
        try:
            result = _resolve(clone, board, specials, positions, target, auto_explode=auto_explode,
                              wide=wide, mode=cascade_mode)
        except UnsupportedRefill:
            if wide:
                # Score Market: the selector checks both answers for the
                # unknown predicate and refuses the swipe if it could matter.
                return high_rank, None
            if not auto_explode:
                raise
            # The selector checks all truth assignments for these predicates.
            return None, None
        if wide:
            return high_rank, _ordinary_extra(result.board, result.special_board, wide)
        initial = result.cascade_matches[0]
        return any(match.kind == "four" for match in initial), _ordinary_extra(result.board, result.special_board)

    # The swiped figure is used up: a second Cleo falling onto its cell must
    # not take its colour for the spawn counts (Square Match 161938 011->012:
    # the Cleo from (5,6) fell onto the spent one's (6,6), engine colour 7 not 6).
    action_model.ball_spent(original_cleo)
    selection = select_clone(config, candidate, action_model.rng, probe,
                             allow_special_partner=wide,
                             ignore_special_prevent=rules.get("boardModelName") == SCORE_MARKET_BOARD)
    result = _resolve(action_model, *converted(selection.positions),
                      selection.positions, target, final=True, auto_explode=auto_explode,
                      wide=wide, mode=cascade_mode)
    result.candidate = candidate
    result.intent_events.insert(0, {"type": "cleo_exact_swipe", "color": selection.color,
                                 "positions": [list(p) for p in selection.positions],
                                 "scope": ("booster_hp1_target_initial_line_four" if auto_explode
                                           else "ordinary_hp1_target_initial_triple")})
    # The old raw slots/uses describe the input board. Do not reuse them for
    # a followed action after the figure and columns have moved.
    action_model.profile = dict(action_model.profile)
    for key in ("raw_slots", "cleo_slots", "cleo_piece_logic"):
        action_model.profile.pop(key, None)
    model.__dict__.update(action_model.__dict__)
    return result
