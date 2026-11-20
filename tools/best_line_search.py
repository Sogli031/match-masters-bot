"""Search the best line from a recorded turn start and compare it with what the bot played.

    python tools/best_line_search.py FOLDER [--seconds 600] [--chain-only]

1. Chain check: the bot's recorded actions are replayed one after another from
   the first record (the simulator's own boards, not the recorded ones). The
   final score must equal the game's, or the search below is not 1:1.
2. Search: strategy_lab.planner from the same start on the same turn clock
   (ACTION_SECONDS per action, any number of actions), every swipe, the booster whenever it is full (fired or held) and
   the perks the player brought (Energy Boost, Teleport, Remove Cross).
Progress (pass, seconds, best score) goes to FOLDER/pretraga_napredak.txt.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from simulator_capture import capture_mode, lab_move
from tools.analyze_research import load, local_player
from tools.replay_one_to_one import recorded_action

PERK_TYPES = (22, 3, 18)   # Energy Boost, Teleport, Remove Cross (engine BoardAbility types)
ACTION_SECONDS = {"swap": 3.9, "booster": 8.0, "remove_cross": 6.2, "energy_boost": 4.2, "teleport": 3.9}


def start_state(record, capture):
    from strategy_lab import simulation

    simulation.PREFIX_MODES = set(simulation.PREFIX_MODES) | {capture_mode(capture["profile"]).value}
    lab = lab_move(capture)
    me = local_player(record)
    lab["score"] = me.get("score") or 0
    lab["booster_state"] = {"current": me.get("energy") or 0, "maximum": me.get("energy_to_ability")}
    lab["booster_auto"] = True       # a full meter is offered as an action...
    lab["booster_hold"] = True       # ...and may also wait
    owned = {}
    for ability in me.get("board_abilities") or ():
        if ability.get("type") in PERK_TYPES:
            owned[int(ability["type"])] = owned.get(int(ability["type"]), 0) + 1
    lab["perks"] = owned
    # The turn clock, not the bot's action count, ends the line: seconds per
    # action measured on the game clock of the Froggy Showdown recording
    # 20261120_001230 (medians: swipe 3.9, booster 8.0, Remove Cross 5.4,
    # Energy Boost with its swipe 2.7).
    lab["time_left"] = (record.get("snapshot_state") or {}).get("remaining_time") or 0.0
    lab["action_seconds"] = dict(ACTION_SECONDS)
    return lab


def bot_actions(files):
    out = []
    for path in files[1:]:
        record, _ = load(path)
        action, why = recorded_action(record)
        if action is None:
            raise SystemExit(f"{path.name}: {why}")
        out.append(action)
    return out


def chain(lab, actions):
    from strategy_lab.simulation import step

    state = lab
    for index, action in enumerate(actions, 1):
        result = step(state, action)
        if not result.get("supported"):
            return state, f"akcija {index} ({action}): {result.get('reason')}"
        state = result["state"]
    return state, None


def main(argv=None):
    from strategy_lab import planner

    parser = argparse.ArgumentParser()
    parser.add_argument("folder", type=Path)
    parser.add_argument("--seconds", type=float, default=600.0)
    parser.add_argument("--chain-only", action="store_true")
    args = parser.parse_args(argv)
    files = sorted(args.folder.glob("[0-9][0-9][0-9].json"))
    first, capture = load(files[0])
    final, _ = load(files[-1])
    game_final = local_player(final).get("score") or 0
    actions = bot_actions(files)
    lab = start_state(first, capture)
    report = args.folder / "pretraga.txt"
    progress = args.folder / "pretraga_napredak.txt"

    end, error = chain(lab, actions)
    lines = [f"Pocetak: {lab['score']} poena, akcija bota: {len(actions)}, igra na kraju: {game_final}"]
    lines.append(f"Simulator, potezi bota u nizu: {end.get('score')}" + (f" (stao: {error})" if error else "")
                 + ("  -> 1:1" if not error and end.get("score") == game_final else "  -> RAZLIKA"))
    print("\n".join(lines), flush=True)
    if args.chain_only:
        report.write_text("\n".join(lines), encoding="utf-8")
        return

    started = time.monotonic()

    def on_pass(info):
        if info.get("done"):
            return
        elapsed = time.monotonic() - started
        progress.write_text(
            f"sirina {info.get('width')}, gotov prolaz: {info.get('complete')}, "
            f"najbolji skor {info.get('score')}, proteklo {elapsed:.0f} s od {args.seconds:.0f} s\n",
            encoding="utf-8")

    best, stats = planner.plan_anytime(dict(lab), args.seconds, finish_cut=True,
                                       on_pass=on_pass)
    lines.append(f"Pretraga ({stats.get('width')} sirina, {planner.describe_passes(stats.get('passes'))}): "
                 f"{best.score} poena u {len(best.actions)} akcija")
    lines.append(f"Razlika pretraga - bot: {best.score - (end.get('score') or 0):+}")
    lines.append("")
    lines.append("Najbolja linija:")
    state = lab
    from strategy_lab.simulation import step
    for index, action in enumerate(best.actions, 1):
        result = step(state, action)
        state = result["state"]
        lines.append(f"  {index:2d}. {planner.describe(action):35s} +{result.get('score_gain') or 0:.0f}"
                     f"  = {state.get('score')}")
    lines.append("")
    lines.append("Bot:")
    state = lab
    for index, action in enumerate(actions, 1):
        result = step(state, action)
        state = result["state"]
        lines.append(f"  {index:2d}. {planner.describe(action):35s} +{result.get('score_gain') or 0:.0f}"
                     f"  = {state.get('score')}")
    report.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines[2:5]))


if __name__ == "__main__":
    main()
