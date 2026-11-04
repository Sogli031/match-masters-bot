"""Square Match Solo inside Memory GUI: exact refill from live memory.

Before each move the reader's agent returns the match profile (rules, spawn
weights, overrides, engine RNG; tools/matchmasters_board_dump.ts matchProfile)
and the ported RefillSlots (engine_refill) turns it into a model that knows
what drops after every swipe. strategy_lab.planner then searches to the last
move with it, the same search square_solo_gui.py validated on recorded
transitions. Only swaps are planned: perks and booster stay with the bot.

Every planned move carries its predicted result, and the next board checks
it. A miss on a board the plan actually played turns the planner off for the
rest of the match, so a wrong model can only cost one move.
"""
from __future__ import annotations

import copy
import time
from dataclasses import dataclass, field

PLAN_SECONDS = 6.0
WAITING_FOR_INPUT = -5  # GameLogic.currentGameState at rest
PROFILE_SETTLE_SECONDS = 1.0
BILLIE_DRONE = 14       # move_strategy.SPECIAL_BILLIE_DRONE
# Leave this much of a running turn clock for the swipe itself.
CLOCK_RESERVE_SECONDS = 4.0


def _grid(board) -> list[list[int]]:
    """Plain int rows: the simulator hands back numpy arrays, the reader lists."""
    return [[int(v) for v in row] for row in board]


def eligible(rules: dict | None) -> bool:
    rules = rules or {}
    return ((rules.get("id") in ("square-match", "color-crush") and rules.get("pvp_mode") == 1)
            or (rules.get("id") == "rainbow" and rules.get("pvp_mode") == 2))


def _ball_slots(snapshot):
    """Colourless pieces with the colour the slot keeps under them; the board shows only 99.

    Disco balls (26, 28), Foxy Roxy (31) and Cleo (32); EngineRefill keeps the last
    two only where Match & Hatch's random specials are ported."""
    return [{"row": slot["row"], "col": slot["col"], "color": slot["color"], "value": slot["value"]}
            for slot in snapshot.get("slots") or [] if slot.get("value") in (26, 28, 31, 32)]


def _profile_players(snapshot):
    players = ((snapshot.get("state") or {}).get("players")) or []
    out = []
    for player in players:
        if not isinstance(player, dict):
            continue
        out.append({"player_type": player.get("player_type"),
                    "model": {"index": player.get("index"), "slotType": player.get("slot_type"),
                              "score": player.get("score"), "energy": player.get("energy"),
                              "specialAbilityType": player.get("special_ability_type"),
                              "boardAbilities": None},
                    "board_abilities": []})
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


def exact_refill_session(reader, script, snapshot, board):
    """(session, reason) for the ordinary ranking; session None means plain ranking."""
    from engine_refill import EngineRefill, ExactRefillSession, UnsupportedRefill, color_maps

    state = snapshot.get("state") or {}
    profile, reason = _resting_profile(reader, script, snapshot)
    if profile is None:
        return None, reason
    profile["players"] = _profile_players(snapshot)
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
        model = EngineRefill.from_profile(profile)
        if any(int(v) == BILLIE_DRONE for row in snapshot.get("special_board") or [] for v in row):
            from engine_billie import BilliePassive
            model.billie = BilliePassive.from_record({
                "profile": profile, "snapshot_state": state,
                "billie_slots": [slot for slot in snapshot.get("slots") or [] if slot.get("value") == 25]})
        session = ExactRefillSession(model, board, hot=hot, special_board=snapshot.get("special_board"),
                                     follow_moves=len(state.get("players") or []) <= 1)
        session.moves_left = state.get("moves")
        me = next((p for p in state.get("players") or [] if p.get("player_type") == 0), {})
        if me.get("energy_full"):
            session.blue_missing = 0
        elif me.get("energy_to_ability") is not None and me.get("energy") is not None:
            session.blue_missing = max(0, me["energy_to_ability"] - me["energy"])
        return session, None
    except (UnsupportedRefill, KeyError, TypeError, ValueError) as exc:
        return None, str(exc)


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

    def plan(self, script, snapshot, *, seconds=PLAN_SECONDS, turn_time_left=None) -> dict:
        """Best swap for this board, or a reason why there is none.

        Returns {"move": {"start","target"} | None, "note": str, "log": [str]}.
        """
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
        if profile["state"].get("moves") != state.get("moves"):
            # The snapshot is from before the last move: this request is stale
            # and the GUI replaces it; the expectation waits for the new board.
            return {"move": None, "note": "tabla i memorija nisu iz istog trenutka", "log": log}
        key = (str(_grid(snapshot["board"])), str(_grid(snapshot["special_board"])),
               (profile.get("rng") or {}).get("<counter>k__BackingField"))
        if key == self.cached_key and self.cached_outcome is not None:
            return {**self.cached_outcome, "log": []}
        note = self.check_expectation(snapshot, profile)
        if note:
            log.append(note)
            if self.disabled_reason:
                return {"move": None, "note": note, "log": log}
        profile = copy.copy(profile)
        profile["players"] = _profile_players(snapshot)
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
        # Swaps only: the bot owns perks and the booster.
        lab["perks"] = {}
        lab["booster_state"] = {"current": 0, "maximum": None}
        budget = seconds - (time.monotonic() - started)
        if turn_time_left is not None:
            budget = min(budget, float(turn_time_left) - CLOCK_RESERVE_SECONDS)
        if budget < 0.5:
            return {"move": None, "note": "nema vremena za plan", "log": log}
        best, stats = planner.plan_anytime(lab, budget)
        if not best.actions:
            return {"move": None, "note": "planer nema podrzan potez", "log": log}
        action = best.actions[0]
        result = step(lab, action)
        if result.get("supported"):
            after = result["state"]
            self.expectation = Expectation(snapshot.get("signature"), action, after["board"],
                                           after["special_board"], after["engine_refill"].rng.counter, lab, capture)
        log.append(f"plan do kraja: skor {best.score} za {len(best.actions)} poteza, "
                   f"prvi {planner.describe(action)} ({time.monotonic() - started:.1f} s)")
        outcome = {"move": {"start": tuple(action["start"]), "target": tuple(action["target"])},
                   "note": f"tacna dopuna: plan {best.score}", "log": log}
        self.cached_key, self.cached_outcome = key, outcome
        return outcome
