"""Sazima svaki solo (1 igrac) snapshot -- Showdown / Party / Master League /
Solo Challenge -- iz board_snapshots.jsonl, sa pravilima (solo targeti,
rumbleType, sat, potezi) za rekonstrukciju meceva.

    python tools/scan_solo_snapshots.py IZLAZ.jsonl
"""
import json
from pathlib import Path
import os
import sys

ROOT = str(Path(__file__).resolve().parent.parent)
SRC = os.path.join(ROOT, "Debug", "memory_board", "board_snapshots.jsonl")
OUT = sys.argv[1]
PK = ("index", "player_type", "score", "energy", "energy_to_ability", "is_my_turn",
      "special_ability_type", "turn_score", "energy_full", "booster_activations_left",
      "bonus_tiles_collected", "score_multiplier", "board_abilities")
EF = ("pvpMode", "rumbleType", "soloRefillMode", "soloOverflowPastTarget", "soloUnusedMovesEnergyWorth",
      "soloContinueAfterLastTarget", "soloTargets", "isMutationLab", "movesPerTurn", "turnsPerGame",
      "timePerTurn", "isTimer", "rumblePlayersAmount", "rumbleResetScoreOnTurnStart", "rumbleEliminateAmounts",
      "extraMoveEnabled", "reshuffleEveryTurn", "energyMult", "conditionalTimeBonus")
n = kept = 0
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
        if len(players) != 1:
            continue
        rules = state.get("rules") or {}
        ef = rules.get("engine_fields") or {}
        rec = {
            "t": snap.get("captured_at"), "reason": snap.get("reason"),
            "title": rules.get("title"), "rules_id": rules.get("id"), "pvp": rules.get("pvp_mode"),
            "tpt": rules.get("time_per_turn"), "mpt": rules.get("moves_per_turn"), "tpg": rules.get("turns_per_game"),
            "solo_targets": rules.get("solo_targets"), "board_model": rules.get("board_model_name"),
            "ef": {k: ef.get(k) for k in EF},
            "rounds_total": state.get("rounds_total"), "round": state.get("current_round"),
            "turn": state.get("current_turn"), "turns_total": state.get("turns_total"),
            "moves": state.get("moves"), "time": state.get("remaining_time"), "gs": state.get("game_state"),
            "single": state.get("is_singleplayer_board"), "mmt": state.get("moves_made_this_turn"),
            "acc_turn": state.get("accumulated_turn_score"),
            "nblue": sum(1 for row in (snap.get("board") or []) for v in row if v == 1),
            "nspec": sum(1 for row in (snap.get("special_board") or []) for v in row if v),
            "me": {k: players[0].get(k) for k in PK},
        }
        out.write(json.dumps(rec, separators=(",", ":")) + "\n")
        kept += 1
print("lines", n, "kept", kept)
