"""Square Match Solo inside Memory GUI: exact refill from live memory.

Before each move the reader's agent returns the match profile (rules, spawn
weights, overrides, engine RNG; tools/matchmasters_board_dump.ts matchProfile)
and the ported RefillSlots (engine_refill) turns it into a model that knows
what drops after every swipe. strategy_lab.planner then searches to the last
move with it, the same search square_solo_gui.py validated on recorded
transitions. Charles plans also model the booster and supported perks.

Every planned move carries its predicted result, and the next board checks
it. A miss on a board the plan actually played turns the planner off for the
rest of the match, so a wrong model can only cost one move.
"""
from __future__ import annotations

import copy
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

PLAN_SECONDS = 6.0
WAITING_FOR_INPUT = -5  # GameLogic.currentGameState at rest
PROFILE_SETTLE_SECONDS = 1.0
BILLIE_DRONE = 14       # move_strategy.SPECIAL_BILLIE_DRONE
# Leave this much of a running turn clock for the swipe itself.
CLOCK_RESERVE_SECONDS = 4.0


def _grid(board) -> list[list[int]]:
    """Plain int rows: the simulator hands back numpy arrays, the reader lists."""
    return [[int(v) for v in row] for row in board]


CHECKMATE_CHARLES = 54
WOOLLY_WORKOUT = 35
FOXY_ROXY_SE = 52
# Boosters the exact plan plays itself (timing, and Woolly's colour): both
# replay exactly. Woolly, Square Match research 2026-11-14 (8 games): 23 of 24
# activations and 80 of 82 swipes exact (refill_monitor.check_transition).
# Foxy Roxy SE (2026-11-17): Color Climb research 20261117_155242, the whole
# game replayed in a chain from the first board (7 activations with their
# cans, 8 sprays, swaps and perks: board, specials, RNG, moves, energy and
# score), engine_foxy.
EXACT_PLAN_BOOSTERS = frozenset((CHECKMATE_CHARLES, WOOLLY_WORKOUT, FOXY_ROXY_SE))
# Boosters planned with Charles's whole-turn policy: a move in hand priced in
# the beam (CHARLES_MOVE_VALUE), the turn clock capping the line and the
# background replan as the per-action search. The booster costs no move for
# both, so a line keeps the moves it frees. Woolly keeps the plain plan.
CHARLES_POLICY_BOOSTERS = frozenset((CHECKMATE_CHARLES, FOXY_ROXY_SE))
# Points one Charles activation brought, measured 2026-11-14: Super Sized
# research 20261114_172725 (7 activations, mean 49) and Square Match
# 20261114_230724 (5, mean 38); an average swap there gave 43 and 36. The
# activation costs no move, so a full meter is worth about one free move.
CHARLES_FIRE_VALUE = 44
# The plan runs before every Charles move; 6 s each made Color Crush moves take
# 10-15 s. 2.5 s finished only the width-1 pass on the recorded Charles boards,
# so the player chose 5 s (2026-11-14); the plan is anytime.
CHARLES_PLAN_SECONDS = 5.0
# Live policy, replayed on the exact simulator 2026-11-15 (research 233705,
# 232927, 230724): a 60 s first plan, then 10 s per action keeping the
# previous line unless beaten, scored 1871 / 1708 / ~1726 against the bot's
# 1227 / 2076 (with two perks) / 1134; 5 s from scratch each action gave
# 626 / 893 / 911. A Solo turn has 1500 s.
# One fresh plan that may hold a full booster (planner booster_hold; it can
# still fire at once, so it covers the at-once lines). tools/plan_width_curve
# 2026-11-15 01:45, 14 Charles games, each width run to the end: at once
# 24708 / 26319 / 29854 at width 10 / 25 / 60, holding 21474 / 29013 / 33170
# (width 60 median 173 s, longest 368 s, 12 processes beside the game). The
# old 60 + 60 s stopped at width 10 (~26090); the player chose 5 minutes,
# then (with the replans every 3 actions, +12.4 %) a shorter wait: 150 s
# still finishes width 25 (live 02:05: widths 1-25 done well inside 300 s),
# and the replans make up the rest.
# Since 2026-11-17 the first plan has no fixed time: it searches until a
# wider pass brings nothing (planner.STOP_RULE) or the turn clock would no
# longer leave time to play its best line (plan_anytime clock); this is only
# the fence against an excessive wait (the player: "as long as it needs, but
# not excessive"). Measured (tools/plan_stop_curve, Debug/plan_stop_curve.txt,
# 41 first boards): the 150 s fence scored 462764 in 3389 s, 300 s +17.5 %
# for +151 s per game; widths keep paying up to 60 (+12 % median), which a
# Charles first board reaches in ~470 s, Foxy Roxy SE in ~35-60 s.
CHARLES_FIRST_SECONDS = 600.0
# The player (2026-11-17): the whole match, every plan and the play, has to
# fit in 15 minutes, or in the challenge turn clock when that ends first.
# Every plan of the Charles-policy boosters (the first one and the background
# replans) searches until it stops paying or until what is left of this time
# would no longer play its best line (LiveSquareSolo._time_left,
# planner.plan_anytime clock); a background replan is no longer cut by its
# own short time, the bot waits for it -- but only as long as the carried
# line still plays to its end after the wait (2026-11-18,
# LiveSquareSolo._start_background).
MATCH_PLAN_SECONDS = 900.0
# The first plan starts at this width: the narrower ones only lose
# (tools/plan_stop_curve 2026-11-17, 41 first boards: 4 beat 1 on 41, 10
# beat 4 on 37, 25 beat 10 on 39, 60 beat 25 on 34; the live first plans
# reached 60 when the time allowed). The player: no need to look at them.
FIRST_START_WIDTH = 60
# 10 s at first; the carried line was kept on 97 of 102 replayed actions and on
# every live action of the first game (2026-11-15 00:06), so the per-move
# search is short: the player found 10 s per move too slow.
CHARLES_NEXT_SECONDS = 2.0
# Every few actions of a carried line, a full search again from the current
# board, kept only if it beats the line. tools/replan_compare 2026-11-15
# 02:55, 16 Charles games, first plan width 60, then width 25 every 3
# actions: 36983 -> 41565 (+12.4 %), 9 games better, none worse; a replan
# took 25-90 s at first, under 1 s near the end (12 processes busy).
# The replan runs in a worker process from the board the carried line
# reaches CHARLES_BG_AHEAD actions later (the refill is exact, so that board
# is known), while the bot plays those actions: the player found a 60 s
# stop every 3 actions too long (2026-11-15 03:20).
# Live 2026-11-15 15:23 and 16:08 (plans of 100-121 actions, a move in hand
# priced): 4 actions ahead and 40 s never finished a pass while the line was
# long (width 25 cut on 14 and 18 replans in a row, the cut line at about
# half the carried score), and the bot waited for them 10 and 18 times (58
# and 126 s). So the replan looks further ahead while the line is long (an
# eighth of it, 4 to CHARLES_BG_AHEAD_MAX actions), searches for the time
# those actions take to play (8 s each in those games) and starts at the
# first plan's own width, the one a pass is known to finish (LiveSquareSolo.
# bg_width). Not measured yet: a time-true replay of the replans is hours.
CHARLES_BG_AHEAD = 4
CHARLES_BG_AHEAD_MAX = 10
CHARLES_BG_ACTION_SECONDS = 7.5


def _bg_ahead(actions_left: int) -> int:
    """How many carried actions ahead the background replan starts."""
    return min(CHARLES_BG_AHEAD_MAX, max(CHARLES_BG_AHEAD, actions_left // 8))
# What a move still in hand counts for when the beam picks its lines
# (planner._rank, rank_move_value). tools/plan_width_curve --move-prices
# 2026-11-15, 23 Charles games, first board, booster held, width 10: price 0
# 36081 points in all, 60 96556, 80 118373, 100 143470, 140 142784. The lines
# keep the moves a booster or a +1 cascade leaves, so the plans grow from 25
# to 112 actions on average (201 at most). Charles only: Woolly is not measured.
CHARLES_MOVE_VALUE = 100
# Such a plan can outlast the turn clock (1500 s; live 2026-11-15 05:25 the
# first board had 1074 s left), so a line gets only the actions the clock
# allows. The cap costs points (--max-steps, same 23 games, price 100, width
# 10: 90 actions 110697, 130 actions 133799, no cap 143470), so the seconds
# per action matter. One action took 8.8 s in that game (36 actions,
# 05:28:13-05:33:31), 2.1 s of it the per-move search, which is now skipped
# while a background replan is pending (it kept the carried line on all 36
# actions there, and on 97 of 102 replayed ones). About 7 s is expected
# then, not measured live yet; every replan reads the clock again, so an
# estimate that is off is corrected within a few actions.
CHARLES_ACTION_SECONDS = 8.5

_BG_POOL = None
# Every finished planner pass, first plan and background replans alike, goes
# to this callable (memory_gui sets the Qt signal's emit; set_pass_listener).
PASS_LISTENER = None


def set_pass_listener(listener):
    global PASS_LISTENER
    PASS_LISTENER = listener


def _tell(info):
    listener = PASS_LISTENER
    if listener is not None:
        try:
            listener(info)
        except Exception:
            pass


def _drain_passes(queue):
    """Main process: the worker's passes, as they finish, to the listener."""
    while True:
        try:
            info = queue.get()
        except Exception:
            return
        if info is None:
            return
        _tell(info)


def _background_pool():
    """One worker process for the background replans, kept across matches.

    Its passes come back through a queue the worker gets at start (a plain
    multiprocessing queue cannot go with each task), read by a daemon thread.
    """
    global _BG_POOL
    if _BG_POOL is None:
        import multiprocessing
        import threading
        from concurrent.futures import ProcessPoolExecutor
        from strategy_lab import planner

        queue = multiprocessing.Queue()
        _BG_POOL = ProcessPoolExecutor(max_workers=1, initializer=planner.set_pass_queue, initargs=(queue,))
        threading.Thread(target=_drain_passes, args=(queue,), name="planner-passes", daemon=True).start()
    return _BG_POOL


def _replay_line(state, actions):
    """The background plan's actions replayed on this process's own state."""
    from strategy_lab import planner
    from strategy_lab.simulation import step

    gains = []
    for action in actions:
        result = step(state, action)
        if not result.get("supported"):
            return None
        state = result["state"]
        gains.append(result.get("score_gain"))
    return planner.Line(state, list(actions), gains)


def _plan_key(state):
    """Match the board and the resources the remaining plan depends on."""
    charge = state.get("booster_state") or {}
    return (str(_grid(state["board"])), str(_grid(state["special_board"])),
            state["engine_refill"].rng.counter, (state.get("turn_state") or {}).get("remaining_moves"),
            charge.get("current"), charge.get("maximum"), _perk_inventory_key(state.get("perks")))


def _same_but_charge(predicted, actual) -> bool:
    """Two _plan_key tuples that differ only in the booster's current charge."""
    if predicted is None or actual is None or len(predicted) != len(actual):
        return False
    return predicted[4] != actual[4] and predicted[:4] == actual[:4] and predicted[5:] == actual[5:]


def _perk_inventory_key(perks):
    return tuple(sorted((perk, count) for perk, count in (perks or {}).items() if count > 0))


def charles_booster(state: dict | None) -> bool:
    """The local player's booster is Checkmate Charles (snapshot state)."""
    return any(p.get("player_type") == 0 and p.get("special_ability_type") == CHECKMATE_CHARLES
               for p in (state or {}).get("players") or [])


def charles_policy_booster(state: dict | None) -> bool:
    """The local player's booster plays Charles's policy (Charles, Foxy Roxy SE)."""
    return any(p.get("player_type") == 0 and p.get("special_ability_type") in CHARLES_POLICY_BOOSTERS
               for p in (state or {}).get("players") or [])


def exact_plan_booster(state: dict | None) -> bool:
    """The local player's booster is one the exact plan plays (Charles, Woolly)."""
    return any(p.get("player_type") == 0 and p.get("special_ability_type") in EXACT_PLAN_BOOSTERS
               for p in (state or {}).get("players") or [])


def charles_eligible(state: dict | None) -> bool:
    """Solo board with Checkmate Charles: the exact plan, any arena.

    Charles moves replay exactly (research 20261114_172725 Super Sized 22 of
    23, the other one a gap; 20261114_230724 Square Match 6 of 6). An arena the
    planner cannot simulate returns no move and the bot's own pick stays.
    """
    rules = (state or {}).get("rules") or {}
    return rules.get("pvp_mode") == 1 and exact_plan_booster(state)


BOOSTER_NAMES = {CHECKMATE_CHARLES: "Checkmate Charles", WOOLLY_WORKOUT: "Woolly Workout",
                 FOXY_ROXY_SE: "Foxy Roxy SE"}


def planner_support(state: dict | None, mode_value: str | None) -> str | None:
    """Why the exact planner cannot plan this match, or None when it can.

    The planner plays a Solo board when our booster's activation is ported
    (EXACT_PLAN_BOOSTERS) and the arena's mode replays exactly
    (strategy_lab.simulation.PREFIX_MODES). The reason names what is missing,
    so a recording can be made for it.
    """
    from strategy_lab.simulation import PREFIX_MODES

    state = state or {}
    rules = state.get("rules") or {}
    missing = []
    if rules.get("pvp_mode") != 1:
        return "planer radi samo u Solo partiji"
    local = next((p for p in state.get("players") or () if p.get("player_type") == 0), None)
    booster = (local or {}).get("special_ability_type")
    if booster not in EXACT_PLAN_BOOSTERS:
        name = (local or {}).get("special_ability_name") or f"tip {booster}"
        missing.append(f"booster {name} nije podrzan")
    if mode_value not in PREFIX_MODES:
        missing.append(f"mod {rules.get('id') or mode_value} nije podrzan")
    return "; ".join(missing) or None


def eligible(rules: dict | None) -> bool:
    rules = rules or {}
    return ((rules.get("id") in ("square-match", "color-crush") and rules.get("pvp_mode") == 1)
            or (rules.get("id") == "rainbow" and rules.get("pvp_mode") == 2))


def _ball_slots(snapshot):
    """Colourless pieces with the colour the slot keeps under them; the board shows only 99.

    Disco balls (26, 28), Foxy Roxy (31), Cleo (32) and the Sweep SE broom (38); EngineRefill keeps the last
    two only where Match & Hatch's random specials are ported."""
    return [{"row": slot["row"], "col": slot["col"], "color": slot["color"], "value": slot["value"]}
            for slot in snapshot.get("slots") or [] if slot.get("value") in (26, 28, 31, 32, 38)]


def _profile_players(snapshot, memory_players=None):
    """The snapshot's players as profile players.

    The periodic snapshot leaves ``spawn_bonus`` null; only the manual dump
    reads it. The Versus refill thresholds need it (versus_adaptive_thresholds),
    so a missing index/score/spawnBonus is taken from the memory profile's own
    players (match_profile reads those fields), matched by engine index. Square
    Match Versus 2026-11-10 02:20: every move fell back to the base thresholds
    while the recorder, on the manual dump, called the formula exact.
    """
    players = ((snapshot.get("state") or {}).get("players")) or []
    memory = {}
    for player in memory_players or ():
        model = (player or {}).get("model") or {}
        if type(model.get("index")) is int:
            memory[model["index"]] = model
    out = []
    for player in players:
        if not isinstance(player, dict):
            continue
        out.append({"player_type": player.get("player_type"),
                    "model": {"index": player.get("index"), "slotType": player.get("slot_type"),
                              "score": player.get("score"), "spawnBonus": player.get("spawn_bonus"),
                              "energy": player.get("energy"),
                              "specialAbilityType": player.get("special_ability_type"),
                              "boardAbilities": None},
                    "board_abilities": []})
        model, known = out[-1]["model"], memory.get(player.get("index"))
        for key in ("score", "spawnBonus"):
            if model[key] is None and known is not None:
                model[key] = known.get(key)
    return out


def _resting_profile(reader, script, snapshot):
    """(profile, reason): the memory profile of this snapshot's board at rest.

    The move waits for this: the engine gets PROFILE_SETTLE_SECONDS to finish
    resolving. A board still not at rest gives None.
    """
    state = snapshot.get("state") or {}
    if (not snapshot.get("stable", True) or state.get("chain_reaction")
            or state.get("game_state") not in (None, WAITING_FOR_INPUT)):
        return None, "tabla jos nije mirna"
    deadline = time.monotonic() + PROFILE_SETTLE_SECONDS
    while True:
        try:
            profile = reader.read_profile(script)
        except Exception as exc:
            return None, f"citanje memorije: {exc}"
        live = profile.get("state") or {}
        if (live.get("moves") == state.get("moves") and not live.get("<ChainReaction>k__BackingField")
                and live.get("currentGameState") in (None, WAITING_FOR_INPUT)):
            return copy.copy(profile), None
        if time.monotonic() >= deadline:
            return None, "igra jos razresava potez"
        time.sleep(0.05)


def _cleo_slots(snapshot):
    return [copy.deepcopy(slot) for slot in snapshot.get("slots") or [] if slot.get("value") == 32]


def cleo_odds_profile(reader, script, snapshot):
    """Memory values for the Cleo odds, independent of the exact refill switch.

    None without a figure on the board, or when the board is not at rest or
    could not be read; the ranking then falls back to the config's PvP values.
    """
    slots = _cleo_slots(snapshot)
    if not slots:
        return None
    profile, _reason = _resting_profile(reader, script, snapshot)
    if profile is not None:
        profile["cleo_slots"] = slots
    return profile


def _solo_snapshot_matches_profile(state, profile):
    """An extra or perk can change the RNG without spending a move."""
    live = profile.get("state") or {}
    players = state.get("players") or []
    live_players = profile.get("players") or []
    checks = [
        (state.get("moves"), live.get("moves")),
        (state.get("moves_made_this_turn"), live.get("<MovesMadeThisTurn>k__BackingField")),
    ]
    if len(players) == len(live_players) == 1:
        captured = live_players[0].get("model") or {}
        checks.extend((players[0].get(key), captured.get(key)) for key in ("score", "energy"))
    return all(before is None or after is None or before == after for before, after in checks)


def exact_refill_session(reader, script, snapshot, board, max_plies=None, *, resting_profile=None,
                         validate_solo_state=False):
    """(session, reason) for the ordinary ranking; session None means plain ranking."""
    from engine_refill import EngineRefill, ExactRefillSession, UnsupportedRefill, color_maps

    state = snapshot.get("state") or {}
    if resting_profile is None:
        profile, reason = _resting_profile(reader, script, snapshot)
        if profile is None:
            return None, reason
    else:
        profile = resting_profile.copy()
    if validate_solo_state and not _solo_snapshot_matches_profile(state, profile):
        return None, "Solo: tabla i profil nisu iz istog poteza"
    profile["players"] = _profile_players(snapshot, profile.get("players"))
    profile["ball_slots"] = _ball_slots(snapshot)
    # Loaded logic / board extraData come from the dynamic profile RPC. The
    # display dump's extraData is a limited string view and cannot replace it.
    profile["raw_slots"] = copy.deepcopy(snapshot.get("slots"))
    profile["cleo_slots"] = _cleo_slots(snapshot)
    try:
        hot = None
        fields = snapshot.get("board_fields") or {}
        if fields.get("currHotColor") is not None:
            _, engine_to_sim = color_maps(profile)
            hot = (engine_to_sim.get(fields["currHotColor"]), engine_to_sim.get(fields.get("nextHotColor")))
        try:
            model = EngineRefill.from_profile(profile)
        except UnsupportedRefill as exc:
            # engine_refill.APPROXIMATE_REFILL: a mode the exact port does not
            # cover still gets the live-RNG drop, marked as a guess.
            model = EngineRefill.from_profile(profile, approximate=True)
            model.unported(str(exc))
            if "Special tile" in str(exc):
                _save_special_tile_config(profile)
        from engine_mixy import MixyPassive
        me_state = next((p for p in state.get("players") or [] if p.get("player_type") == 0), {})
        model.mixy = MixyPassive.from_player(me_state, color_maps(profile)[1], profile)
        if any(int(v) == BILLIE_DRONE for row in snapshot.get("special_board") or [] for v in row):
            from engine_billie import BilliePassive
            try:
                model.billie = BilliePassive.from_record({
                    "profile": profile, "snapshot_state": state,
                    "billie_slots": [slot for slot in snapshot.get("slots") or [] if slot.get("value") == 25]})
            except UnsupportedRefill as exc:
                if model.approximate is None:
                    model.approximate = []
                model.unported(str(exc))
        extra = {} if max_plies is None else {"max_plies": max_plies}
        session = ExactRefillSession(model, board, hot=hot, special_board=snapshot.get("special_board"),
                                     follow_moves=len(state.get("players") or []) <= 1, **extra)
        rules = profile.get("rules") or {}
        # Jelly SE is a booster: its zone and uses-left counter
        # (JellySEUsesLeftKeyPlayer0) sit in extraData in every mode, not only
        # Bullseye Bash (Column Mania, Mighty Mushrooms, 2026-11-09). Without
        # them the refill gave up on every move with a zone on the board.
        from board_source import jelly_zone_state

        jelly = jelly_zone_state(snapshot) or {}
        if jelly.get("cells"):
            session.jelly_uses_left = jelly.get("uses_left")
            session.jelly_cells = frozenset(jelly["cells"])
            # The overlay belongs to this capture. A move that leaves the zone
            # alone keeps it on the same cells (research 2026-11-11: 6 of 6),
            # so up to two such moves are followed (ExactRefillSession.finish
            # stops at a conversion); converted boards are not.
            session.max_plies = 2
        session.moves_left = state.get("moves")
        # Solo only: the move counter is the whole match. In versus the charge
        # carries into later rounds, so the counter says nothing about it.
        session.solo = len(state.get("players") or []) <= 1
        me = next((p for p in state.get("players") or [] if p.get("player_type") == 0), {})
        if me.get("energy_full"):
            session.blue_missing = 0
        elif me.get("energy_to_ability") is not None and me.get("energy") is not None:
            session.blue_missing = max(0, me["energy_to_ability"] - me["energy"])
            # Per-colour charge (memory_gui._charge_scale): the ranking counts
            # charge on the BOOSTER_MAX_CHARGE scale, so the room does too.
            from board_source import charging_weights
            weights = charging_weights(snapshot)
            if weights and any(value != 1 for value in weights.values()) and me["energy_to_ability"]:
                from move_strategy import BOOSTER_MAX_CHARGE
                session.blue_missing *= BOOSTER_MAX_CHARGE / float(me["energy_to_ability"])
        return session, None
    except (UnsupportedRefill, KeyError, TypeError, ValueError) as exc:
        if "Special tile" in str(exc):
            _save_special_tile_config(profile)
        return None, str(exc)


# Solo Challenge Teleport (offline, 152 recorded solo boards, 2026-11-09):
# median +24% of the points still to come, best on the first move it can go
# (92 of 145 plans; holding it gained 2.4 points on average, held for the
# last two moves it fell to +17%). Whether one board's Teleport is worth 10%
# is below the search noise, so it is not judged: it goes first, on the pair
# whose exact line to the end of the match scores best.
TELEPORT_PAIR_SECONDS = 15.0     # Solo Challenge: no clock pressure (player, 2026-11-09)
TELEPORT_PAIR_CANDIDATES = 6
PERK_TELEPORT_ENGINE = 3


def teleport_exact_pair(reader, script, snapshot, *, seconds=TELEPORT_PAIR_SECONDS) -> dict:
    """The Teleport pair to play now, from exact plans to the end of the match.

    Returns {"pair": ((r,c),(r,c)) | None, "note": str}; None leaves the
    choice to the bot's own perk ranking.
    """
    from simulator_capture import decode_dictionary, lab_move
    import board_source

    profile, reason = _resting_profile(reader, script, snapshot)
    if profile is None:
        return {"pair": None, "note": f"bez profila: {reason}"}
    state = snapshot.get("state") or {}
    profile["players"] = _profile_players(snapshot, profile.get("players"))
    profile["ball_slots"] = _ball_slots(snapshot)
    score = decode_dictionary((profile.get("rules") or {}).get("_colorScoreOverride")) or {}
    me = next((p for p in state.get("players", []) if p.get("player_type") == 0), {})
    capture = {"profile": profile, "simulator_input": {
        "board": copy.deepcopy(snapshot["board"]), "special_board": copy.deepcopy(snapshot["special_board"]),
        "froggy_params": me.get("special_ability_params"), "booster_cost": me.get("energy_to_ability"),
        "active_mutations": snapshot.get("active_mutations"),
        "score_rally_values": {str(board_source.slot_color_to_board(k)): v for k, v in score.items()}}}
    try:
        lab = lab_move(capture)
    except Exception as exc:
        return {"pair": None, "note": f"simulator: {type(exc).__name__}: {exc}"}
    return best_teleport_pair(lab, seconds=seconds)


def best_teleport_pair(lab, *, seconds=TELEPORT_PAIR_SECONDS, candidates=TELEPORT_PAIR_CANDIDATES) -> dict:
    """teleport_exact_pair on a ready simulator state (also used offline).

    The ``candidates`` Teleports with the best immediate gain are each played
    out to the end with the exact refill, swipes only after it.
    """
    from strategy_lab import planner, simulation

    with_tp = dict(lab, perks={PERK_TELEPORT_ENGINE: 1})
    # Only the pair is taken from this: every mode the refill covers counts,
    # as in tools/analyze_research.try_transition.
    certified = simulation.PREFIX_MODES
    simulation.PREFIX_MODES = set(certified) | {lab.get("mode")}
    try:
        first_steps = []
        for action in planner.actions(with_tp):
            if action.get("kind") != "teleport":
                continue
            result = simulation.step(with_tp, action)
            if result.get("supported"):
                first_steps.append((result["score_gain"], action, result["state"]))
        first_steps.sort(key=lambda item: item[0], reverse=True)
        best_score, best_action = None, None
        share = seconds / max(1, min(candidates, len(first_steps)))
        for _gain, action, after in first_steps[:candidates]:
            line, _ = planner.plan_anytime(dict(after, perks={}), share)
            if best_score is None or line.score > best_score:
                best_score, best_action = line.score, action
    finally:
        simulation.PREFIX_MODES = certified
    if best_action is None:
        return {"pair": None, "note": "nema podrzanog Teleporta"}
    pair = (tuple(best_action["start"]), tuple(best_action["target"]))
    return {"pair": pair, "note": f"{pair[0]}<->{pair[1]}, plan do kraja {best_score}"}


SPECIAL_TILE_DUMP_DIR = Path(__file__).resolve().parent / "Debug/refill_unsupported"


def _save_special_tile_config(profile) -> None:
    """Once per board model: the special-tile config the refill does not port yet,
    so the next port starts from the game's own numbers, not a guess."""
    try:
        from simulator_capture import decode_dictionary
        board_model = (profile.get("rules") or {}).get("boardModelName")
        target = SPECIAL_TILE_DUMP_DIR / f"special_tiles_board_{board_model}.json"
        if target.exists():
            return
        data = decode_dictionary(profile["spawning"].get("specialTilesData")) or {}
        document = {"boardModelName": board_model,
                    "specialTilesData": {str(k): decode_dictionary(v) if isinstance(v, dict) else v
                                         for k, v in data.items()},
                    "profile": profile}
        SPECIAL_TILE_DUMP_DIR.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(document, ensure_ascii=False, default=str), encoding="utf-8")
    except Exception:  # Diagnostics only; never stop the move.
        pass


@dataclass
class Expectation:
    signature: object
    action: dict
    board: list
    special_board: list
    rng_counter: int
    lab: dict | None = None     # the state planned from, to identify another move
    capture: dict | None = None  # profile + boards planned from, saved on a miss


@dataclass
class LiveSquareSolo:
    """Per-match state; the GUI keeps one and calls reset() between matches."""
    static: dict | None = None          # rules + config of this GameLogic
    logic_key: str | None = None
    disabled_reason: str | None = None
    expectation: Expectation | None = None
    # The last plan, keyed by board + RNG counter. Memory GUI discards and
    # restarts a computation when its plan key moves (the turn clock ticks
    # while the planner runs), so the same board is asked for again at once.
    cached_key: tuple | None = None
    cached_outcome: dict | None = None
    # Checkmate Charles: the rest of the last plan and the state it expects
    # next (board, specials, RNG counter, moves); see plan().
    carry: object | None = None
    carry_key: tuple | None = None
    # Background replan: the future, the board key it planned from and how
    # many plan() calls have passed since it was started.
    bg: object | None = None
    bg_key: tuple | None = None
    bg_deadline: float = 0.0
    bg_calls: int = 0
    bg_ahead: int = CHARLES_BG_AHEAD    # how far ahead the running replan started
    # The width the next background replan starts from: the first plan's
    # widest whole pass, then the widest a replan ran whole. Narrower passes
    # only repeat the carried line's own search (live 2026-11-15 05:25: two
    # replans went through widths 1, 4 and 10 again and found nothing); the
    # next one up does not finish while the line is long (15:23, 16:08).
    bg_width: int = 0
    # The actions the turn clock still allows after the action being played
    # (None: no clock); the replan's board is _bg_ahead actions further.
    bg_steps: int | None = None
    # The dynamic stop (planner.STOP_RULE) holds for the Charles-policy
    # boosters; Woolly's replans keep the plain anytime search.
    dynamic: bool = True
    # When this match's first plan started (MATCH_PLAN_SECONDS counts from it)
    # and the time left for the background replan the next move starts.
    match_started: float | None = None
    bg_left: float | None = None
    # Seconds a pass takes per width and per line action, measured on this
    # match's last whole pass (first plan or replan): what a replan's first
    # width will cost (_bg_start_width). 2026-11-18 width 150: 301 s / 42,
    # 243 s / 43, 144 s / 21 actions (0.036-0.048).
    bg_pace: float | None = None
    stats: dict = field(default_factory=lambda: {"exact": 0, "miss": 0, "other_move": 0})
    # A refill miss since the GUI last looked (it turns the recording on).
    miss_seen: bool = False

    def reset(self):
        self.__init__()

    def _time_left(self, turn_time_left, now=None):
        """Seconds the plans may still count on: MATCH_PLAN_SECONDS from the
        first plan of the match, or the challenge turn clock when it ends
        first, less CLOCK_RESERVE_SECONDS."""
        now = time.monotonic() if now is None else now
        started = self.match_started if self.match_started is not None else now
        left = MATCH_PLAN_SECONDS - (now - started)
        if turn_time_left is not None:
            left = min(left, float(turn_time_left))
        return left - CLOCK_RESERVE_SECONDS

    def _start_background(self, after, actions, baseline=None):
        """Plan from the board _bg_ahead carried actions after this one.

        ``baseline``: the value the carried line reaches (the same line from
        any of its boards)."""
        from strategy_lab import planner
        from strategy_lab.simulation import step

        self.bg = None
        ahead = _bg_ahead(len(actions))
        if len(actions) <= ahead:
            return
        state = after
        for action in actions[:ahead]:
            result = step(state, action)
            if not result.get("supported"):
                return
            state = result["state"]
        seconds = ahead * CHARLES_BG_ACTION_SECONDS
        steps = 300 if self.bg_steps is None else max(1, self.bg_steps - ahead)
        clock = None
        width, first_cost = self.bg_width, None
        if self.dynamic and self.bg_left is not None:
            # No short time of its own: it searches until the gain stops or
            # the match time left would no longer play its line
            # (MATCH_PLAN_SECONDS). But the bot waits for it once the actions
            # ahead are played, and that wait must still leave the carried
            # line the time to play to its end: live 2026-11-18 08:40 a
            # width-150 replan took 243 s, the bot stood 200 s, and the clock
            # cut the 3291 line to 26 actions (2432); the match ended at 1540.
            if self.bg_left - ahead * CHARLES_ACTION_SECONDS < CHARLES_ACTION_SECONDS:
                return
            rest = len(actions) - ahead
            room = self.bg_left - rest * CHARLES_ACTION_SECONDS
            width, first_cost = self._bg_start_width(rest, room)
            if width is None:
                return      # no width finishes in time: the carried line plays on
            seconds, steps = room, 300
            clock = {"left": self.bg_left, "busy": ahead * CHARLES_ACTION_SECONDS,
                     "action_seconds": CHARLES_ACTION_SECONDS}
        try:
            # baseline: the carried line's value; the dynamic stop
            # (planner.STOP_RULE) measures each pass against it.
            self.bg = _background_pool().submit(planner.background_plan, state, seconds, width,
                                                steps, baseline, None if self.dynamic else False, clock,
                                                first_cost)
        except Exception:
            return      # no worker: the carried line and the 2 s checks go on
        self.bg_key, self.bg_calls, self.bg_ahead = _plan_key(state), 0, ahead
        self.bg_deadline = time.monotonic() + seconds

    def _bg_start_width(self, actions, room):
        """The width a background replan starts at, and its expected seconds.

        The widest pass already run whole (bg_width) when, at the measured
        pace (bg_pace, seconds per width and line action), it finishes within
        ``room``; else the widest narrower one that does. None when not even
        the narrowest does. Without a measure, bg_width as before.
        """
        from strategy_lab import planner

        if not self.bg_pace or not self.bg_width:
            return self.bg_width, None
        for width in sorted((w for w in planner.WIDTHS if w <= self.bg_width), reverse=True):
            cost = self.bg_pace * width * max(1, actions)
            if cost <= room:
                return width, cost
        return None, None

    def _measure_pace(self, passes, actions):
        """bg_pace from the last whole pass: seconds per width per line action."""
        whole = [(w, s) for w, s, done in passes or () if done and s and w]
        if whole and actions:
            width, seconds = whole[-1]
            self.bg_pace = seconds / (width * actions)

    def _take_background(self, lab, carried, log, announce, fit=None):
        """The background plan for this board, if it beats the carried line.

        ``fit``: how many actions the clock still plays now (a callable); both
        lines are compared cut to it, as they would be played. Live
        2026-11-18 08:43:59 a 3502 replan beat the 3291 line at full length,
        and then only 26 of its 43 actions fitted."""
        future, self.bg = self.bg, None
        wait = max(0.0, self.bg_deadline - time.monotonic()) + 5.0
        if not future.done() and announce is not None:
            try:
                announce(wait, True)
            except Exception:
                pass
        try:
            result = future.result(timeout=wait)
        except Exception as exc:
            log.append(f"pozadinski plan nije stigao ({type(exc).__name__})")
            return carried
        from strategy_lab import planner

        if result.get("full_width"):
            self.bg_width = result["full_width"]
        passes = planner.describe_passes(result.get("passes"))
        why = f"; stao: {result['stop_reason']}" if result.get("stop_reason") else ""
        passes = f" (prolazi {passes}{why})" if passes else ""
        line = _replay_line(lab, result["actions"]) if result.get("actions") else None
        if line is not None:
            self._measure_pace(result.get("passes"), len(line.actions))
        against = carried
        if line is not None and fit is not None:
            steps = max(1, int(fit()))
            if len(line.actions) > steps:
                line = _replay_line(lab, result["actions"][:steps])
            if len(carried.actions) > steps:
                against = _replay_line(lab, carried.actions[:steps]) or carried
        if line is not None and line.value > against.value:
            log.append(f"pozadinski plan: sirina {result.get('width')}, skor {line.score} "
                       f"umesto {against.score}, prelazim{passes}")
            _tell({"chosen": True, "source": "pozadinski plan", "taken": True, "score": line.score,
                   "width": result.get("width"), "carried": against.score,
                   "first": [planner.describe(a) for a in line.actions[:5]]})
            return line
        log.append(f"pozadinski plan: sirina {result.get('width')}, skor {result.get('score')}, "
                   f"ostaje {carried.score}{passes}")
        _tell({"chosen": True, "source": "pozadinski plan", "taken": False, "score": result.get("score"),
               "width": result.get("width"), "carried": carried.score})
        return carried

    def read_profile(self, script) -> dict:
        profile = script.exports_sync.match_profile(self.static is None)
        if profile.get("logic_key") != self.logic_key or self.static is None:
            if "rules" not in profile:
                profile = script.exports_sync.match_profile(True)
            self.static = {"rules": profile["rules"], "config": profile["config"]}
            self.logic_key = profile.get("logic_key")
            self.disabled_reason = None
            self.expectation = None
        if not profile.get("consistent", False):
            raise RuntimeError("RNG se pomerio tokom citanja")
        return {**profile, **self.static}

    def settled_profile(self, script, timeout=3.0, gap=0.25):
        """A profile read twice in a row with the engine at rest.

        The engine resolves a move step by step with its animation, so a read
        mid-cascade pairs a half-finished RNG with a board that is not final.
        """
        deadline = time.monotonic() + timeout
        previous = self.read_profile(script)
        while True:
            time.sleep(gap)
            current = self.read_profile(script)
            def mark(p):
                st = p.get("state") or {}
                return ((p.get("rng") or {}).get("<counter>k__BackingField"), st.get("moves"),
                        st.get("<ChainReaction>k__BackingField"), st.get("currentGameState"))
            rest = (current.get("state") or {}).get("currentGameState") in (None, WAITING_FOR_INPUT)
            if (mark(previous) == mark(current) and rest
                    and not (current.get("state") or {}).get("<ChainReaction>k__BackingField")):
                return current
            if time.monotonic() > deadline:
                return None
            previous = current

    def check_expectation(self, snapshot, profile) -> str | None:
        """Compare the board the last plan predicted with this one."""
        expected, self.expectation = self.expectation, None
        if expected is None:
            return None
        counter = (profile.get("rng") or {}).get("<counter>k__BackingField")
        same_board = (_grid(snapshot["board"]) == _grid(expected.board)
                      and _grid(snapshot["special_board"]) == _grid(expected.special_board))
        if same_board and counter == expected.rng_counter:
            self.stats["exact"] += 1
            return "dopuna predvidjena tacno"
        # Not the plan's result. If some other swap from the same state gives
        # exactly this board, the bot just played that one and the model is
        # still right; booster/perk turns are not reproduced by swaps.
        played = self._identify_swap(expected.lab, snapshot, counter)
        if played is not None:
            self.stats["other_move"] += 1
            return f"odigran drugi potez ({played}), dopuna i za njega tacna"
        self.stats["miss"] += 1
        # The GUI turns the research recording on (memory_gui, planner_miss).
        self.miss_seen = True
        saved = self._save_miss(expected, snapshot, profile)
        mode_id = (expected.capture or {}).get("profile", {}).get("rules", {}).get("id")
        if mode_id in ("color-crush", "rainbow"):
            self.disabled_reason = f"{mode_id}: ishod se nije poklopio; obican bot do kraja partije"
        return f"potez se ne moze reprodukovati (booster/perk ili greska modela){saved}"

    @staticmethod
    def _save_miss(expected, snapshot, profile):
        """Keep the evidence: profile and boards before, plan, board after."""
        import datetime as dt
        import json
        from pathlib import Path

        try:
            folder = Path(__file__).resolve().parent / "Debug/square_live_misses"
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / (dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f") + ".json")
            path.write_text(json.dumps({
                "before": expected.capture, "planned_action": expected.action,
                "predicted": {"board": _grid(expected.board), "special_board": _grid(expected.special_board),
                              "rng_counter": expected.rng_counter},
                "after": {"profile": profile, "board": _grid(snapshot["board"]),
                          "special_board": _grid(snapshot["special_board"]), "state": snapshot.get("state")},
            }, default=str), encoding="utf-8")
            return f"; snimljeno {path.name}"
        except Exception as exc:
            return f"; snimak nije uspeo: {exc}"

    @staticmethod
    def _identify_swap(lab, snapshot, counter):
        if lab is None:
            return None
        from strategy_lab import planner
        from strategy_lab.simulation import step

        board, special = _grid(snapshot["board"]), _grid(snapshot["special_board"])
        for action in planner.actions(lab):
            if action.get("kind", "swap") != "swap":
                continue
            result = step(lab, action)
            if not result.get("supported"):
                continue
            after = result["state"]
            if (after["engine_refill"].rng.counter == counter and _grid(after["board"]) == board
                    and _grid(after["special_board"]) == special):
                return planner.describe(action)
        return None

    def plan(self, script, snapshot, *, seconds=PLAN_SECONDS, turn_time_left=None,
             announce=None, perks=None) -> dict:
        """Choose the next action for the resting board and remaining resources."""
        from simulator_capture import lab_move, prepare_input  # noqa: F401  (heavy imports, lazy)
        from strategy_lab import planner
        from strategy_lab.simulation import step
        import board_source
        from simulator_capture import decode_dictionary

        log = []
        if self.disabled_reason:
            return {"move": None, "note": f"planer iskljucen: {self.disabled_reason}", "log": log}
        started = time.monotonic()
        state = snapshot.get("state") or {}
        # GameState -5 waits for input; -7 is still resolving the last move
        # (the snapshot's "stable" is true there too).
        if (not snapshot.get("stable", True) or state.get("chain_reaction")
                or state.get("game_state") not in (None, WAITING_FOR_INPUT)):
            return {"move": None, "note": "tabla jos nije mirna", "log": log}
        profile = self.settled_profile(script)
        if profile is None:
            return {"move": None, "note": "igra jos razresava potez", "log": log}
        if not _solo_snapshot_matches_profile(state, profile):
            # The snapshot is from before the last move: this request is stale
            # and the GUI replaces it; the expectation waits for the new board.
            return {"move": None, "note": "tabla i memorija nisu iz istog trenutka", "log": log}
        # Charles and Woolly: the plan owns the booster, perks and replans.
        charles = exact_plan_booster(state)
        perks = dict(perks or {}) if charles else {}
        key = (str(_grid(snapshot["board"])), str(_grid(snapshot["special_board"])),
               (profile.get("rng") or {}).get("<counter>k__BackingField"), state.get("moves"),
               tuple(p.get("energy") for p in state.get("players") or ()),
               _perk_inventory_key(perks))
        if key == self.cached_key and self.cached_outcome is not None:
            return {**self.cached_outcome, "log": []}
        # An inventory change on the same board invalidates the plan without
        # counting the unplayed action as a refill miss.
        note = (self.check_expectation(snapshot, profile)
                if self.cached_key is None or key[:-1] != self.cached_key[:-1] else None)
        if note:
            log.append(note)
            if self.disabled_reason:
                return {"move": None, "note": note, "log": log}
        profile = copy.copy(profile)
        profile["players"] = _profile_players(snapshot, profile.get("players"))
        # The colours under the colourless pieces, as the recorder and the
        # replay (analyze_research) give them. Without them EngineRefill.balls
        # is None: Color Climb 2026-11-17 22:40 (Foxy Roxy SE), the live first
        # plan scored 3276 at width 60 against 49939 from the same board
        # replayed, and lost 4396/7050; on board 021 the booster line
        # (5324) was missing and the plan kept 4358.
        profile["ball_slots"] = _ball_slots(snapshot)
        score = decode_dictionary(profile["rules"].get("_colorScoreOverride")) or {}
        capture = {"profile": profile, "simulator_input": {
            "board": copy.deepcopy(snapshot["board"]), "special_board": copy.deepcopy(snapshot["special_board"]),
            "froggy_params": next((p.get("special_ability_params") for p in state.get("players", [])
                                   if p.get("player_type") == 0), None),
            "booster_cost": next((p.get("energy_to_ability") for p in state.get("players", [])
                                   if p.get("player_type") == 0), None),
            "score_multiplier": next((p.get("score_multiplier") for p in state.get("players", [])
                                      if p.get("player_type") == 0), None),
            "multiplier_colors": (board_source.color_climb_state(snapshot) or {}).get("colors"),
            "score_rally_values": {str(board_source.slot_color_to_board(k)): v for k, v in score.items()}}}
        lit = board_source.lights_up_state(
            dict(snapshot, columns=len(snapshot["board"][0]) if snapshot.get("board") else None))
        if lit is not None:
            capture["simulator_input"]["lights_up_column"] = lit["column"]
        if profile["rules"].get("id") == "the-floor-is-lava":
            # The columns one match from erupting, as tools/analyze_research.capture_from
            # reads them; unread stays None and plan_refusal stops the plan.
            counts = board_source.floor_lava_column_counts(
                dict(snapshot, columns=len(snapshot["board"][0]) if snapshot.get("board") else None))
            if counts:
                capture["simulator_input"]["floor_lava_columns"] = tuple(
                    column for column, count in counts.items() if count == 1)
        lab = lab_move(capture)
        from strategy_lab.simulation import plan_refusal
        refusal = plan_refusal(lab)
        if refusal:
            return {"move": None, "note": refusal, "log": log}
        if profile["rules"].get("id") == "rainbow" and any(
                int(v) == 20 for row in lab["special_board"] for v in row):
            # Do not promote an ordinary exact swap over a potentially better
            # Froggy gather that the exact planner cannot yet price/resolve.
            return {"move": None, "note": "Rainbow lotus: izbor preuzima Froggy strategija", "log": log}
        lab["perks"] = perks
        if charles:
            # Checkmate Charles (ported exactly): the line fires the booster as
            # soon as the meter is full, as the bot does (planner.actions,
            # booster_auto), so the plan sees what the blast and its knights do.
            charge = lab.get("booster_state") or {}
            lab["booster_state"] = {"current": charge.get("current") or 0, "maximum": charge.get("maximum")}
            lab["booster_auto"] = True
        else:
            lab["booster_state"] = {"current": 0, "maximum": None}
        # The rest of the last plan, when this board is the one it predicted
        # (board, specials and RNG): kept unless a new search beats it.
        carried = None
        key_now = _plan_key(lab)
        if charles and self.carry is not None and self.carry.actions:
            if self.carry_key == key_now:
                carried = self.carry
            elif _same_but_charge(self.carry_key, key_now):
                # Only the meter differs from what the line predicted (board,
                # specials, RNG, moves and perks agree): the line is replayed
                # from the real meter instead of a fresh first plan. Bombs Away
                # 2026-11-18 09:02 and 09:05: predicted 6 and 5, the game 7
                # (a knight chain and an Energy Boost bomb; 6 such of 1031
                # recorded Charles moves, tools/measure_exact_charge), and each
                # cost a new first plan of 127 s and 97 s.
                replayed = _replay_line(lab, self.carry.actions)
                if replayed is not None:
                    log.append(f"punjenje boostera {self.carry_key[4]} -> {key_now[4]} "
                               f"(predvidjeno -> u igri): nastavljam plan")
                    carried = replayed
        if charles and self.bg is not None:
            self.bg_calls += 1
            if carried is not None and (self.bg_key == key_now or _same_but_charge(self.bg_key, key_now)):
                fit = None
                if charles_policy_booster(state):
                    def fit():
                        return self._time_left(turn_time_left) / CHARLES_ACTION_SECONDS
                carried = self._take_background(lab, carried, log, announce, fit)
            elif carried is None or self.bg_calls > self.bg_ahead + 1:
                self.bg = None      # a miss or another line: its board will not come
        self.dynamic = charles_policy_booster(state)
        if self.match_started is None:
            self.match_started = started
        if charles:
            seconds = CHARLES_NEXT_SECONDS if carried is not None else CHARLES_FIRST_SECONDS
            if carried is not None and self.bg is not None and charles_policy_booster(state):
                seconds = 0.0   # the background replan is the search; the clock pays per action
            lab["booster_hold"] = True
        budget = seconds - (time.monotonic() - started)
        if turn_time_left is not None:
            budget = min(budget, float(turn_time_left) - CLOCK_RESERVE_SECONDS)
        if budget < 0.5 and carried is None:
            return {"move": None, "note": "nema vremena za plan", "log": log}
        # Charles: a move in hand has a price in the beam, and a line gets
        # only the actions the turn clock allows after this search.
        steps = None
        clock = None
        self.bg_steps = None
        if charles_policy_booster(state):
            lab["rank_move_value"] = CHARLES_MOVE_VALUE
            left = self._time_left(turn_time_left)
            if carried is None:
                # The first plan: no fixed time. Each pass gets the actions
                # the match time leaves after it, and the search ends before
                # it would not leave time to play its best line.
                clock = {"left": left, "action_seconds": CHARLES_ACTION_SECONDS}
                budget = left
            else:
                steps = max(1, int((left - max(budget, 0.0)) / CHARLES_ACTION_SECONDS))
                self.bg_steps = steps - 1
                if carried is not None and len(carried.actions) > steps:
                    # The play ran slower than planned: the clock ends the
                    # carried line early, so it counts only that far.
                    shorter = _replay_line(lab, carried.actions[:steps])
                    if shorter is not None:
                        log.append(f"sat: od {len(carried.actions)} akcija plana staje jos {steps}")
                        carried = shorter
        if budget >= 0.5:
            if announce is not None:
                # The GUI counts down to the move (memory_gui._plan_countdown).
                try:
                    announce(budget, carried is not None)
                except Exception:
                    pass
            # The first plan holds the turn clock: it does not start a width it
            # cannot finish (stop_early). The background replans' time is free.
            # The first plan stops by itself once a wider pass no longer
            # pays (planner.STOP_RULE); its seconds are only the fence. Its
            # passes go to the GUI as they finish (PASS_LISTENER).
            first = carried is None
            best, stats = planner.plan_anytime(
                lab, budget, finish_cut=first, stop_early=first,
                **({} if steps is None else {"max_steps": steps}),
                **({"on_pass": lambda info: _tell(dict(info, source="prvi plan"))} if first else {}),
                **({"rule": planner.STOP_RULE} if first and charles_policy_booster(state) else {}),
                **({} if clock is None else {"clock": clock, "start_width": FIRST_START_WIDTH}))
            if first:
                self.bg_width = stats.get("full_width") or 0
                whole = [p for p in stats.get("pass_info") or () if p.get("complete")]
                if whole:
                    self._measure_pace([(whole[-1]["width"], whole[-1]["seconds"], True)],
                                       whole[-1]["actions"])
                if clock is not None:
                    self.bg_steps = max(1, int(self._time_left(turn_time_left) / CHARLES_ACTION_SECONDS)) - 1
                log.append(f"prvi plan: sirina {stats.get('width')}, skor {best.score} "
                           f"(prolazi {planner.describe_passes(stats.get('passes'))}; "
                           f"stao: {stats.get('stop_reason')})")
        else:
            best = carried
        if carried is not None and carried.value >= best.value:
            best = carried
            log.append("nastavljam prethodni plan")
        self.carry = self.carry_key = None
        if not best.actions:
            return {"move": None, "note": "planer nema podrzan potez", "log": log}
        action = best.actions[0]
        result = step(lab, action)
        if result.get("supported"):
            after = result["state"]
            self.expectation = Expectation(snapshot.get("signature"), action, after["board"],
                                           after["special_board"], after["engine_refill"].rng.counter, lab, capture)
            if charles:
                self.carry = planner.Line(best.state, best.actions[1:], best.gains[1:])
                self.carry_key = _plan_key(after)
                if self.bg is None or best is not carried:
                    self.bg_left = (self._time_left(turn_time_left) - CHARLES_ACTION_SECONDS
                                    if self.dynamic else None)
                    self._start_background(after, self.carry.actions, best.value)
        log.append(f"plan do kraja: skor {best.score} za {len(best.actions)} poteza, "
                   f"prvi {planner.describe(action)} ({time.monotonic() - started:.1f} s)")
        if action.get("kind") == "booster":
            # The bot fires the full booster itself; the plan goes on after it.
            outcome = {"move": None, "booster": True, "booster_color": action.get("color"),
                       "note": f"tacna dopuna: plan {best.score}, prvo booster", "log": log}
            self.cached_key, self.cached_outcome = key, outcome
            return outcome
        outcome = {"move": {"kind": action.get("kind", "swap"),
                            "start": tuple(action["start"]), "target": tuple(action["target"]),
                            "direction": action.get("direction")},
                   "note": f"tacna dopuna: plan {best.score}", "log": log}
        self.cached_key, self.cached_outcome = key, outcome
        return outcome
