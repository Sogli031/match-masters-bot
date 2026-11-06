"""Conservative deterministic-prefix adapter over existing Match Masters rules.

No sampled refill is invented. A transition ends at the first unknown refill;
it must not be resumed as though the empty cells were a valid whole game.
The one exception is a capture-backed ``engine_refill.SquareRefill`` model in
``move["engine_refill"]``: the ported RefillSlots then fills every cascade.
"""
from contextlib import ExitStack, contextmanager
from copy import deepcopy
import move_strategy as ms

PREFIX_MODES = {ms.GameMode.NONE.value, ms.GameMode.COLOR_CRUSH.value,
                ms.GameMode.VERTICAL_RUSH.value, ms.GameMode.BLOW_EM_UP.value,
                ms.GameMode.LIGHTNING_STRIKE.value, ms.GameMode.SHARED_ENERGY.value}
ORDINARY_SPECIALS = {0, ms.SPECIAL_HORIZONTAL, ms.SPECIAL_VERTICAL, ms.SPECIAL_BOMB}
# A resting crosshair or lightning is inert; only its activation picks random
# targets, and step() rejects any transition in which one fires.
RESTING_SPECIALS = ORDINARY_SPECIALS | {ms.SPECIAL_CROSSHAIR, ms.SPECIAL_LIGHTNING, ms.SPECIAL_HEART,
                                        ms.SPECIAL_FROGGY_LOTUS, ms.SPECIAL_COLOR_CRYSTAL,
                                        ms.SPECIAL_DISCO_BALL, ms.SPECIAL_MUSHROOM, ms.SPECIAL_CLEO_BUG}
RANDOM_TARGET_SPECIALS = {"crosshair", "lightning", "all_aboard_bandit", "cleo_bug", "spray_se", "joojoo_skull"}
# Match & Hatch's random specials: known at rest, their activation is not ported.
HATCHED_SPECIALS = (ms.SPECIAL_ALL_ABOARD_BANDIT, ms.SPECIAL_JOOJOO_SKULL, ms.SPECIAL_SPRAY_SE, ms.SPECIAL_CLEO_BUG)


@contextmanager
def rules(move):
    mode=move["mode"]
    with ExitStack() as stack:
        stack.enter_context(ms.color_crush_active(mode == ms.GameMode.COLOR_CRUSH.value or bool(move.get("color_crush")),
                              single_player=move.get("single_player_board",(move.get("strategy_context") or {}).get("mode") == "solo_6")))
        stack.enter_context(ms.all_specials_lightning_active(mode == ms.GameMode.LIGHTNING_STRIKE.value or bool(move.get("all_specials_lightning"))))
        stack.enter_context(ms.both_colors_charge_energy_active(mode == ms.GameMode.SHARED_ENERGY.value))
        stack.enter_context(ms.charge_colors_active(move.get("energized_colors") or (),move.get("engine_charge_colors")))
        stack.enter_context(ms.vertical_matches_destroy_color_active(bool(move.get("vertical_matches_destroy_color"))))
        stack.enter_context(ms.matches_destroy_color_active(bool(move.get("matches_destroy_color"))))
        stack.enter_context(ms.every_match_is_special_active(bool(move.get("every_match_is_special"))))
        stack.enter_context(ms.line_destruction_active(*(move.get("line_destruction") or (False,False))))
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
                                 lambda candidate, **kwargs: simulate_swipe(model, candidate, **kwargs)):
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


# Board abilities by engine type (PlayerModel.boardAbilities keys).
PERK_ENERGY_BOOST, PERK_TELEPORT = 22, 3
DOCTOR_COLOR = 27
NO_SWAP_CELL = (-1, -1)


def step(move, action):
    """Return a new state and a narrower measured quantity, never a utility score.

    ``action["kind"]``: "swap" (default), "energy_boost" (Energy Boost then
    this swipe), "teleport" (any two pieces) or "booster" (Doctor Color).
    The last three need a capture-backed engine_refill model.
    """
    if move.get("mode") not in PREFIX_MODES:
        return {"supported": False, "reason": "mode prefix not certified by Strategy Lab"}
    model = move.get("engine_refill")
    billie = getattr(model, "billie", None)
    hatched = HATCHED_SPECIALS if getattr(model, "random_specials", ()) else ()
    # Plunder Pirates' chest: SPECIAL_MODE_TARGET on a CHEST cell, only falls.
    chest = lambda r, c: (move["special_board"][r][c] == ms.SPECIAL_MODE_TARGET
                          and move["board"][r][c] == ms.CHEST and model is not None)
    if any(v not in RESTING_SPECIALS and v not in hatched
           and not (v == ms.SPECIAL_BILLIE_DRONE and billie is not None)
           and not chest(r, c)
           for r, row in enumerate(move["special_board"]) for c, v in enumerate(row)):
        return {"supported": False, "reason": "random or equipment special on board"}
    if hatched and action.get("kind", "swap") == "swap" and any(
            move["special_board"][r][c] in hatched for r, c in (action["start"], action["target"])):
        return {"supported": False, "reason": "random target outcome is not a deterministic prefix"}
    if any(move.get(k) for k in ("jelly_zone_cells", "funky_tile_cells", "hot_color_state")):
        return {"supported": False, "reason": "additional board layer"}
    kind = action.get("kind", "swap")
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
    if kind == "booster":
        if move.get("booster_type") != DOCTOR_COLOR:
            return {"supported": False, "reason": "only Doctor Color is ported"}
        charge = move.get("booster_state") or {}
        if charge.get("maximum") is None or (charge.get("current") or 0) < charge["maximum"]:
            return {"supported": False, "reason": "booster is not charged"}
        path = doctor_color_pick(board, model)
        if path is None:
            return {"supported": False, "reason": "no Doctor Color path on the board"}
        board = doctor_color_convert(board, specials, path)
        candidate = ms.MoveCandidate(NO_SWAP_CELL, NO_SWAP_CELL, ms.Direction.RIGHT, board, specials)
    else:
        start, target = tuple(action["start"]), tuple(action["target"])
        r, c = start; y, x = target
        if kind != "teleport" and abs(r-y) + abs(c-x) != 1:
            raise ValueError("not an adjacent swap")
        board[r][c], board[y][x] = board[y][x], board[r][c]
        specials[r][c], specials[y][x] = specials[y][x], specials[r][c]
        candidate = ms.MoveCandidate(start, target, ms.Direction(action["direction"]), board, specials)
        if ms._candidate_activates_cleo_swap(candidate):
            if model is None:
                return {"supported": False, "reason": "Cleo: exact engine state is required"}
            if kind != "swap":
                return {"supported": False, "reason": "Cleo: perk/merge timing is not ported"}
    from engine_refill import UnsupportedRefill
    try:
        with rules(move), engine_refill(model) as refills:
            if kind == "booster":
                result = ms.simulate_candidate(
                    candidate, allow_square_matches=bool(move.get("allow_square_matches")), mode=move["mode"])
            else:
                result = simulate(move,candidate)
    except UnsupportedRefill as exc:
        return {"supported": False, "reason": f"engine refill: {exc}"}
    if result is None:
        return {"supported":False,"reason":"candidate no longer legal"}
    if model is not None and move.get("rules_id") == "rainbow":
        if any(e.get("type") == ms.FROGGY_LOTUS_GATHER_EVENT for e in result.intent_events):
            return {"supported": False, "reason": "Rainbow lotus gather is not certified for exact planning"}
        if any(e.get("type") == "special_activation" and e.get("cascade", 0) > 1
               and e.get("special") in ("horizontal", "vertical", "bomb") for e in result.intent_events):
            return {"supported": False, "reason": "Rainbow cascade rocket/bomb timing is not ported"}
    # Recorded Color Crush 006->007: cascade special timing is not ported.
    # The RNG counter can agree while both the board and specials differ.
    if (model is not None and move.get("mode") == ms.GameMode.COLOR_CRUSH.value
            and any(e.get("type") == "special_activation" and e.get("cascade", 0) > 1
                    for e in result.intent_events)):
        return {"supported": False, "reason": "Color Crush cascade special timing is not ported"}
    if any("random_outcomes" in e.get("type", "")
           or (e.get("type") == "special_activation" and e.get("special") in RANDOM_TARGET_SPECIALS)
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
    after = deepcopy({k: v for k, v in move.items() if k != "engine_refill"})
    after["board"], after["special_board"] = result.board, result.special_board
    turn = after.setdefault("turn_state", {})
    # With the exact refill, cascade fours are known too: the game granted
    # their extra move in every recorded case (and for a square as well).
    extra = bool(result.extra_moves if model is not None else result.direct_extra_moves)
    # Only a swipe costs a move; an extra-move combo adds one. For a swipe
    # that nets to "not consumed". Teleport (ConvertSlots, no swipe) is free
    # and its four gives +1 (player, 2026-11-01); the booster is assumed to
    # follow the same rule, not yet recorded.
    costs_move = kind in ("swap", "energy_boost")
    if kind == "booster":
        extra = False  # recorded Doctor Color with a four: moves 6 -> 6
    if turn.get("remaining_moves") is not None:
        turn["remaining_moves"] = max(0, turn["remaining_moves"] - costs_move + extra)
    charge = after.setdefault("booster_state", {})
    if charge.get("current") is not None and charge.get("maximum") is not None:
        # Energy Boost: every destroyed piece charges, not only Blue. The
        # booster empties the meter and its cascades do not refill it
        # (recorded energy 7 -> 0, confirmed by the player).
        gained = result.cleared_cells if kind == "energy_boost" else result.blue_cells
        if kind == "booster":
            charge["current"] = 0
        else:
            charge["current"] = min(charge["maximum"], charge["current"] + int(round(gained)))
    if kind in ("energy_boost", "teleport"):
        perk = PERK_ENERGY_BOOST if kind == "energy_boost" else PERK_TELEPORT
        after["perks"] = dict(after["perks"])
        after["perks"][perk] -= 1
    turn["owner_after"] = "us" if extra or (turn.get("remaining_moves") or 0) > 0 else "end_of_turn"
    # A count of removed pieces is intentionally separate from game score:
    # historical logs do not reliably supply the multiplier of every mode.
    if model is not None:
        after["engine_refill"] = model
        # Square Solo score = value of every destroyed piece by colour (26 of
        # 26 recorded moves, 2026-11-01, including specials and squares).
        values = move.get("score_values") or {}
        gain = sum(n * values.get(int(c) % 1000, 1) for c, n in result.cleared_color_counts.items())
        if move.get("score") is not None:
            after["score"] = move["score"] + int(round(gain))
        return {"supported": True, "metric": "cleared_tiles", "value": float(result.cleared_cells),
                "score_gain": gain, "state": after, "extra": extra, "events": result.intent_events,
                "refills": refills,
                "terminal_reason": "engine_refill: whole action, unverified against a recorded transition"}
    return {"supported": True, "metric": "deterministic_prefix_cleared_tiles",
            "value": float(result.cleared_cells), "state": after,
            "extra": extra, "events": result.intent_events,
            "terminal_reason": "unknown_refill: prefix only, not a whole action or match"}
