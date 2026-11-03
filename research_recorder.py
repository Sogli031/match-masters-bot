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
from pathlib import Path

from square_solo_live import LiveSquareSolo, _ball_slots, _grid, _profile_players

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

    def record(self, script, snapshot=None, enabled=lambda: True, resting_trigger=False) -> str | None:
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

        profile = self._reader.settled_profile(script, timeout=6.0)
        if profile is None:
            return None
        raw = script.exports_sync.dump_board()
        raw = raw.get("snapshot", raw) if isinstance(raw, dict) else raw
        state = raw.get("state") or {}
        if state.get("moves") != profile["state"].get("moves") or state.get("chain_reaction"):
            return None
        board, special, _ = board_source.adapt_memory_snapshot_payload(raw)
        snap = {"board": board, "special_board": special, "state": state}
        key = (str(_grid(board)), str(_grid(special)), profile["rng"].get("<counter>k__BackingField"))
        if key == self.last_key:
            return None
        self.last_key = key
        profile = copy.copy(profile)
        profile["players"] = _profile_players(snap)
        profile["ball_slots"] = _ball_slots(raw)
        missed = bool(resting_trigger and snapshot is not None and _grid(snapshot["board"]) != _grid(board))
        entry = {
            "captured_at": dt.datetime.now().isoformat(),
            "profile": profile, "board": _grid(board), "special_board": _grid(special),
            "snapshot_state": state, "board_fields": raw.get("board_fields"),
            # Adapted BLOCKED loses the drone's primary colour, flags and
            # movability. Keep the original slots for deterministic replay.
            "billie_slots": [copy.deepcopy(slot) for slot in raw.get("slots") or []
                             if slot.get("value") == 25],
            "missed_board_before": missed,
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
