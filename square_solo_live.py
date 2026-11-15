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
CHARLES_FIRST_SECONDS = 60.0
# 10 s at first; the carried line was kept on 97 of 102 replayed actions and on
# every live action of the first game (2026-11-15 00:06), so the per-move
# search is short: the player found 10 s per move too slow.
CHARLES_NEXT_SECONDS = 2.0
# A second fresh plan that may hold a full booster (planner booster_hold).
# tools/booster_hold_compare 2026-11-15 01:12, 12 Charles games, 60 s each:
# at once 20117, hold 19096; hold won 5 of 12 (up to +889), the better of
# the two per game 21917 (+9 %). So both run and the better line is played.
CHARLES_HOLD_SECONDS = 60.0


def _plan_key(state):
    """Match the board and the resources the remaining plan depends on."""
    charge = state.get("booster_state") or {}
    return (str(_grid(state["board"])), str(_grid(state["special_board"])),
            state["engine_refill"].rng.counter, (state.get("turn_state") or {}).get("remaining_moves"),
            charge.get("current"), charge.get("maximum"), _perk_inventory_key(state.get("perks")))


def _perk_inventory_key(perks):
    return tuple(sorted((perk, count) for perk, count in (perks or {}).items() if count > 0))


def charles_booster(state: dict | None) -> bool:
    """The local player's booster is Checkmate Charles (snapshot state)."""
    return any(p.get("player_type") == 0 and p.get("special_ability_type") == CHECKMATE_CHARLES
               for p in (state or {}).get("players") or [])


def charles_eligible(state: dict | None) -> bool:
    """Solo board with Checkmate Charles: the exact plan, any arena.

    Charles moves replay exactly (research 20261114_172725 Super Sized 22 of
    23, the other one a gap; 20261114_230724 Square Match 6 of 6). An arena the
    planner cannot simulate returns no move and the bot's own pick stays.
    """
    rules = (state or {}).get("rules") or {}
    return rules.get("pvp_mode") == 1 and charles_booster(state)


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
    carry_hold: bool = False    # the carried line may hold a full booster
    stats: dict = field(default_factory=lambda: {"exact": 0, "miss": 0, "other_move": 0})

    def reset(self):
        self.__init__()

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
        charles = charles_booster(state)
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
        score = decode_dictionary(profile["rules"].get("_colorScoreOverride")) or {}
        capture = {"profile": profile, "simulator_input": {
            "board": copy.deepcopy(snapshot["board"]), "special_board": copy.deepcopy(snapshot["special_board"]),
            "froggy_params": next((p.get("special_ability_params") for p in state.get("players", [])
                                   if p.get("player_type") == 0), None),
            "booster_cost": next((p.get("energy_to_ability") for p in state.get("players", [])
                                   if p.get("player_type") == 0), None),
            "score_rally_values": {str(board_source.slot_color_to_board(k)): v for k, v in score.items()}}}
        lab = lab_move(capture)
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
        if charles and self.carry is not None and self.carry_key == _plan_key(lab) and self.carry.actions:
            carried = self.carry
        hold = self.carry_hold if carried is not None else False
        both = charles and carried is None
        if charles:
            seconds = CHARLES_NEXT_SECONDS if carried is not None else CHARLES_FIRST_SECONDS
        budget = seconds - (time.monotonic() - started)
        if turn_time_left is not None:
            budget = min(budget + (CHARLES_HOLD_SECONDS if both else 0.0),
                         float(turn_time_left) - CLOCK_RESERVE_SECONDS)
        elif both:
            budget += CHARLES_HOLD_SECONDS
        if budget < 0.5 and carried is None:
            return {"move": None, "note": "nema vremena za plan", "log": log}
        if budget >= 0.5:
            if announce is not None:
                # The GUI counts down to the move (memory_gui._plan_countdown).
                try:
                    announce(budget, carried is not None)
                except Exception:
                    pass
            if both:
                # Booster at once and booster held, each with its share.
                share = budget * CHARLES_FIRST_SECONDS / (CHARLES_FIRST_SECONDS + CHARLES_HOLD_SECONDS)
                best, stats = planner.plan_anytime(lab, share)
                held, _ = planner.plan_anytime(dict(lab, booster_hold=True), budget - share)
                log.append(f"booster odmah {best.score}, sa cekanjem {held.score}")
                if held.value > best.value:
                    best, hold = held, True
            else:
                best, stats = planner.plan_anytime(dict(lab, booster_hold=hold), budget)
        else:
            best = carried
        if carried is not None and carried.value >= best.value:
            best = carried
            log.append("nastavljam prethodni plan")
        self.carry = self.carry_key = None
        self.carry_hold = hold
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
        log.append(f"plan do kraja: skor {best.score} za {len(best.actions)} poteza, "
                   f"prvi {planner.describe(action)} ({time.monotonic() - started:.1f} s)")
        if action.get("kind") == "booster":
            # The bot fires the full booster itself; the plan goes on after it.
            outcome = {"move": None, "booster": True,
                       "note": f"tacna dopuna: plan {best.score}, prvo booster", "log": log}
            self.cached_key, self.cached_outcome = key, outcome
            return outcome
        outcome = {"move": {"kind": action.get("kind", "swap"),
                            "start": tuple(action["start"]), "target": tuple(action["target"])},
                   "note": f"tacna dopuna: plan {best.score}", "log": log}
        self.cached_key, self.cached_outcome = key, outcome
        return outcome
