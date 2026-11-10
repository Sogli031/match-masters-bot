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
import time
from pathlib import Path

from square_solo_live import WAITING_FOR_INPUT, LiveSquareSolo, _ball_slots, _grid, _profile_players

ROOT = Path(__file__).resolve().parent
RESEARCH_DIR = ROOT / "Debug/research"


class ResearchRecorder:
    def __init__(self):
        self.on_capture = None          # refill_monitor: (entry, board_was_missed)
        self.reset()

    def reset(self):
        self._reader = LiveSquareSolo()   # profile cache + settle check
        self.folder = None
        self.number = 0
        self.last_key = None
        self._mixy_trace_script = None
        self._resting_capture = None

    def matching_profile(self, script, snapshot, input_marker):
        capture = self._resting_capture
        if capture is None:
            return None
        source_script, source_snapshot, source_input, captured_at, profile = capture
        if (script is source_script and snapshot is source_snapshot and input_marker == source_input
                and time.monotonic() - captured_at < 0.25):
            return profile
        return None

    def record(self, script, snapshot=None, enabled=lambda: True, resting_trigger=False,
               input_marker=None, single_profile=False) -> str | None:
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

        # Short gap: Auto's next move waits for this read.
        input_before = input_marker() if input_marker is not None else None
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
                return None
        else:
            profile = self._reader.settled_profile(script, timeout=6.0, gap=0.1)
        if profile is None:
            return None
        raw = script.exports_sync.dump_board()
        raw = raw.get("snapshot", raw) if isinstance(raw, dict) else raw
        state = raw.get("state") or {}
        if (state.get("moves") != profile["state"].get("moves") or state.get("chain_reaction")
                or (lightweight and state.get("game_state") != WAITING_FOR_INPUT)
                or (input_marker is not None and input_marker() != input_before)):
            return None
        board, special, _ = board_source.adapt_memory_snapshot_payload(raw)
        if (lightweight and snapshot is not None and snapshot.get("stable")
                and all(snapshot.get(key) is not None and snapshot[key] == raw.get(key)
                        for key in ("signature", "state_signature", "game_logic"))
                and _grid(snapshot["board"]) == _grid(board)
                and _grid(snapshot["special_board"]) == _grid(special)):
            self._resting_capture = (script, snapshot, input_before, captured_at, profile)
        snap = {"board": board, "special_board": special, "state": state}
        key = (str(_grid(board)), str(_grid(special)), profile["rng"].get("<counter>k__BackingField"))
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
        missed = bool(resting_trigger and snapshot is not None and _grid(snapshot["board"]) != _grid(board))
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
