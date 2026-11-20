"""Istrazivacki snimac: svaka mirna tabla + kompletno stanje iz memorije.

Ukljucuje se prekidacem "Snimaj svaki potez" u Memory GUI-ju. Posle svake
promene table (Auto, dugme ili potez odigran rukom), kad igra ceka potez
(GameState -5, RNG miran u dva citanja), snima se tabla iz snapshot-a i
profil iz agenta (pravila, spawn tezine/override-i, RNG, igraci). Fajlovi
idu u Debug/research/<partija>/NNN.json; tools/analyze_research.py posle
proverava svaki prelaz prema simulatoru. Bez uticaja na izbor poteza.
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import threading
import time
from pathlib import Path

from square_solo_live import WAITING_FOR_INPUT, LiveSquareSolo, _ball_slots, _grid, _profile_players

ROOT = Path(__file__).resolve().parent
# Why a record() saved nothing. A board missed after a Foxy Roxy SE booster
# (Crazy Columns research 20261118_215913: 5 of 30 steps held 2-4 inputs) left
# no trace in the log; these go there now. The first two are retried while
# the swipe waits (memory_gui._watch_research_board).
SKIP_NOT_AT_REST = "igra se nije smirila za 6 s"
SKIP_BOARD_MOVING = "tabla se menjala tokom citanja"
SKIP_NEW_INPUT = "odigran nov potez tokom citanja"
RETRY_SKIPS = frozenset((SKIP_NOT_AT_REST, SKIP_BOARD_MOVING))
RESEARCH_DIR = ROOT / "Debug/research"

# The agent's refill snapshot events (matchmasters_board_dump.ts): the board a
# fill starts from with the exact hole list, and the special-tile phase that
# RefillSlots runs after it. Doctor Color's open question (27 or 28 holes before
# RNG 679) is answered by the hole count and the two RNG boundaries.
REFILL_EVENT_TYPES = ("refill_fill", "spawn_specials")


def refill_snapshots(traces) -> list:
    """Every refill event of the given traces, tagged with its trace."""
    out = []
    for trace in traces or []:
        for event in trace.get("events") or []:
            if event.get("type") not in REFILL_EVENT_TYPES:
                continue
            out.append({"trace_kind": trace.get("kind"), "ability": trace.get("ability"),
                        "logic_key": trace.get("logic_key"), **event})
    return out


class ResearchRecorder:
    def __init__(self):
        self.on_capture = None          # refill_monitor: (entry, board_was_missed)
        self._key_lock = threading.Lock()
        self.reset()

    def reset(self):
        self._reader = LiveSquareSolo()   # profile cache + settle check
        self.folder = None
        self.number = 0
        self.last_key = None
        self._mixy_trace_script = None
        self._booster_detail = None     # (script, on) last sent to the agent
        self._resting_capture = None
        self._trace_counter = None      # RNG counter of the last record (_move_traces)
        self.last_skip = None           # why the last record() saved nothing (None: saved or a duplicate)

    def save_final_trace(self, script, folder) -> str | None:
        """At the match's end: keep the agent's last move traces next to its records.

        The match's last move never reaches a resting board, so no record
        carries its swap_trace (Color Climb 2026-11-13 14:48: a heart merge
        played as the last move was lost). Written as kraj_partije_trag.json.
        """
        if script is None or folder is None:
            return None
        try:
            history = script.exports_sync.swap_trace_history()
        except Exception:
            return None     # an agent without the export
        if not (history or {}).get("traces"):
            return None
        path = Path(folder) / "kraj_partije_trag.json"
        path.write_text(json.dumps(history, default=str), encoding="utf-8")
        return str(path)

    def _move_traces(self, script, profile) -> list:
        """The agent's traces of the moves since the previous record.

        Each trace is one played action (swap, perk or Charles): every special
        area, every destroy pass with its RNG counters and the board it
        destroys from, i.e. each cascade step after the refill before it
        (matchmasters_board_dump.ts, swap trace). A trace belongs here when it
        started at or after the previous record's RNG counter and before
        this one's. tools/trace_refill_miss.py prints them next to the
        simulator's cascades.
        """
        counter = (profile.get("rng") or {}).get("<counter>k__BackingField")
        previous, self._trace_counter = self._trace_counter, counter
        if previous is None or counter is None:
            return []
        try:
            history = script.exports_sync.swap_trace_history()
        except Exception:
            return []     # an agent without the export
        return [trace for trace in (history or {}).get("traces") or []
                if isinstance(trace.get("before_rng_counter"), int)
                and previous <= trace["before_rng_counter"] < counter]

    def _arm_booster_detail(self, script, on: bool) -> None:
        """Whole booster state in the profile only while "Snimaj svaki potez" is on.

        The agent then adds ability_detail (the local player's ability with
        every field) and special_pieces_logics (each live piece logic, e.g.
        CupidHeart's allowed merge types) to every profile read.
        """
        if self._booster_detail == (script, on):
            return
        self._booster_detail = (script, on)
        try:
            script.exports_sync.arm_booster_detail(on)
        except Exception:
            # An agent built before this export records without the detail.
            pass

    def matching_profile(self, script, snapshot, input_marker):
        capture = self._resting_capture
        if capture is None:
            return None
        source_script, source_snapshot, source_input, captured_at, profile = capture
        if (script is source_script and snapshot is source_snapshot and input_marker == source_input
                and time.monotonic() - captured_at < 0.25):
            return profile
        return None

    def _new_entry(self, raw, board, special, state, profile, snapshot, missed, input_before):
        """The refill check / research record of one resting board, or None if already taken."""
        snap = {"board": board, "special_board": special, "state": state}
        key = (str(_grid(board)), str(_grid(special)), profile["rng"].get("<counter>k__BackingField"))
        with self._key_lock:
            if key == self.last_key:
                return None
            self.last_key = key
        profile = copy.copy(profile)
        profile["players"] = _profile_players(snap)
        profile["ball_slots"] = _ball_slots(raw)
        # Keep the original field values: the display board loses slot flags
        # and a booster's underlying colour. Never infer a Cleo target colour
        # from the board after the move.
        cleo_slots = [copy.deepcopy(slot) for slot in raw.get("slots") or []
                      if slot.get("value") == 32]
        profile["cleo_slots"] = cleo_slots
        profile["raw_slots"] = copy.deepcopy(raw.get("slots"))
        # match_profile reads the complete typed dictionary. dump_board's
        # legacy string view is bounded to 64 entries: absence there cannot
        # establish a zero PieceUsesThisTurn counter.
        if "board_extra_data" in profile:
            profile["board_extra_data"] = copy.deepcopy(profile["board_extra_data"])
        entry = {
            "captured_at": dt.datetime.now().isoformat(),
            "profile": profile, "board": _grid(board), "special_board": _grid(special),
            "snapshot_state": state, "board_fields": raw.get("board_fields"),
            # Mutations are not rule fields; without them a replay plays another game.
            "active_mutations": copy.deepcopy(
                raw.get("active_mutations") or (snapshot or {}).get("active_mutations")),
            # CellModel.cellType per cell: Funky Tiles' funky cells live here,
            # not on the slots; without them a replay plays another board.
            "cell_types": copy.deepcopy(raw.get("cell_types") or (snapshot or {}).get("cell_types")),
            # Column Mania's per-column multiplier (CellModel.scoreMultiplier).
            "cell_multipliers": copy.deepcopy(
                raw.get("cell_multipliers") or (snapshot or {}).get("cell_multipliers")),
            # Adapted BLOCKED loses the drone's primary colour, flags and
            # movability. Keep the original slots for deterministic replay.
            "billie_slots": [copy.deepcopy(slot) for slot in raw.get("slots") or []
                             if slot.get("value") == 25],
            "cleo_slots": copy.deepcopy(cleo_slots),
            "raw_slots": copy.deepcopy(raw.get("slots")),
            "board_extra_data": copy.deepcopy(profile.get("board_extra_data")),
            "board_extra_data_view": copy.deepcopy(raw.get("board_extra_data")),
            "missed_board_before": missed,
            "refill_input": input_before,
        }
        return entry

    def capture_resting(self, snapshot, profile, input_before) -> bool:
        """Hand the refill check a board the move itself read at rest.

        Outside the Solo Challenge (research off) the swipe does not wait for
        the watcher's read, so Auto's next move kept moving the RNG under it:
        Crazy Columns 2026-11-12 00:46-00:48 gave the check 1 board in 29
        moves (Hot Color with research on: 41). The move's own exact refill
        already read the resting profile of this board; the same key as
        ``record`` drops it when the watcher took the board too.
        """
        if self.on_capture is None or snapshot is None or profile is None:
            return False
        state = snapshot.get("state") or {}
        live = profile.get("state") or {}
        if (live.get("currentGameState") not in (None, WAITING_FOR_INPUT)
                or live.get("<ChainReaction>k__BackingField")
                or (state.get("moves") is not None and live.get("moves") != state.get("moves"))):
            return False
        entry = self._new_entry(snapshot, snapshot["board"], snapshot["special_board"], state,
                                profile, snapshot, False, input_before)
        if entry is None:
            return False
        self.on_capture(entry, False)
        return True

    def record(self, script, snapshot=None, enabled=lambda: True, resting_trigger=False,
               input_marker=None, single_profile=False, on_read=None) -> str | None:
        """Wait for the engine to rest, then read a fresh board + profile.

        ``snapshot`` is only the trigger: a move computation can start on a
        frame from the middle of a cascade, so the board is re-dumped here
        after the RNG has stopped moving. ``on_capture`` gets every new board;
        the file is written only if ``enabled``, asked again right before
        writing: the wait can outlast the toggle being switched off.
        ``resting_trigger``: the snapshot was at rest, so a different board
        means a move was played during the wait and that board was missed.
        """
        import board_source

        self.last_skip = None
        # Short gap: Auto's next move waits for this read.
        input_before = input_marker() if input_marker is not None else None
        self._arm_booster_detail(script, bool(enabled()))
        if enabled() and script is not self._mixy_trace_script:
            self._mixy_trace_script = script
            try:
                script.exports_sync.arm_mixy_trace()
            except Exception:
                # Older agents can still record ordinary research pairs.
                pass
        lightweight = single_profile and resting_trigger and not enabled()
        if lightweight:
            captured_at = time.monotonic()
            profile = self._reader.read_profile(script)
            live = profile.get("state") or {}
            if live.get("currentGameState") != WAITING_FOR_INPUT or live.get("<ChainReaction>k__BackingField"):
                self.last_skip = SKIP_NOT_AT_REST
                return None
        else:
            profile = self._reader.settled_profile(script, timeout=6.0, gap=0.1)
        if profile is None:
            self.last_skip = SKIP_NOT_AT_REST
            return None
        raw = script.exports_sync.dump_board()
        raw = raw.get("snapshot", raw) if isinstance(raw, dict) else raw
        state = raw.get("state") or {}
        if input_marker is not None and input_marker() != input_before:
            self.last_skip = SKIP_NEW_INPUT
            return None
        if (state.get("moves") != profile["state"].get("moves") or state.get("chain_reaction")
                or (lightweight and state.get("game_state") != WAITING_FOR_INPUT)):
            self.last_skip = SKIP_BOARD_MOVING
            return None
        board, special, _ = board_source.adapt_memory_snapshot_payload(raw)
        if on_read is not None:
            # The board and profile are read: the next swipe may go. The swap
            # traces below are picked by RNG counter (before this board's), so
            # the next move's trace never lands in this record.
            on_read()
        if (lightweight and snapshot is not None and snapshot.get("stable")
                and all(snapshot.get(key) is not None and snapshot[key] == raw.get(key)
                        for key in ("signature", "state_signature", "game_logic"))
                and _grid(snapshot["board"]) == _grid(board)
                and _grid(snapshot["special_board"]) == _grid(special)):
            self._resting_capture = (script, snapshot, input_before, captured_at, profile)
        missed = bool(resting_trigger and snapshot is not None and _grid(snapshot["board"]) != _grid(board))
        entry = self._new_entry(raw, board, special, state, profile, snapshot, missed, input_before)
        if entry is None:
            return None
        if enabled():
            entry["swap_traces"] = self._move_traces(script, profile)
            # Also top level: the board before RefillSlots and the exact holes.
            entry["refill_snapshots"] = refill_snapshots(entry["swap_traces"])
        if self.on_capture is not None:
            self.on_capture(entry, missed)
        if not enabled():
            return None
        if self.folder is None:
            rules_id = (profile.get("rules") or {}).get("id") or "unknown"
            self.folder = RESEARCH_DIR / f"{dt.datetime.now():%Y%m%d_%H%M%S}_{rules_id}"
            self.folder.mkdir(parents=True, exist_ok=True)
        path = self.folder / f"{self.number:03d}.json"
        path.write_text(json.dumps(entry, default=str), encoding="utf-8")
        self.number += 1
        return str(path)
