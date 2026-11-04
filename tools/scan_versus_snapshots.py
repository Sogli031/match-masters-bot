"""Sazima svaki versus (2 igraca) snapshot iz Debug/memory_board/board_snapshots.jsonl
u mali JSONL (skor, energija, potezi, sat, game_state) za rekonstrukciju meceva.

    python tools/scan_versus_snapshots.py IZLAZ.jsonl
"""
import json
from pathlib import Path
import os
import sys

ROOT = str(Path(__file__).resolve().parent.parent)
SRC = os.path.join(ROOT, "Debug", "memory_board", "board_snapshots.jsonl")
OUT = sys.argv[1]
PK = ("index", "player_type", "score", "energy", "energy_to_ability", "is_my_turn",
      "rounds_won", "special_ability_type", "has_played_this_turn", "turn_score",
      "max_round_score", "energy_full", "booster_activations_left")
n = 0
kept = 0
with open(SRC, "rb") as src, open(OUT, "w", encoding="utf-8") as out:
    for line in src:
        n += 1
        if b'"players"' not in line:
            continue
        try:
            payload = json.loads(line.decode("utf-8"))
        except ValueError:
            continue
        snap = payload.get("snapshot", payload)
        state = snap.get("state") or {}
        players = state.get("players") or []
        if len(players) < 2:
            continue
        rules = state.get("rules") or {}
        ef = rules.get("engine_fields") or {}
        rec = {
            "t": snap.get("captured_at"),
            "reason": snap.get("reason"),
            "sig": snap.get("state_signature"),
            "title": rules.get("title"),
            "rules_id": rules.get("id"),
            "pvp": rules.get("pvp_mode"),
            "tpt": rules.get("time_per_turn"),
            "mpt": rules.get("moves_per_turn"),
            "tpg": rules.get("turns_per_game"),
            "board_model": rules.get("board_model_name"),
            "rounds_total": state.get("rounds_total"),
            "round": state.get("current_round"),
            "turn": state.get("current_turn"),
            "turns_total": state.get("turns_total"),
            "moves": state.get("moves"),
            "time": state.get("remaining_time"),
            "gs": state.get("game_state"),
            "cpi": state.get("current_player_index"),
            "opp": state.get("opponent_index"),
            "single": state.get("is_singleplayer_board"),
            "nblue": sum(1 for row in (snap.get("board") or []) for v in row if v == 1),
            "players": [{k: p.get(k) for k in PK} for p in players],
        }
        out.write(json.dumps(rec, separators=(",", ":")) + "\n")
        kept += 1
print("lines", n, "kept", kept)
