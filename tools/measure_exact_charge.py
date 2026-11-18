"""Booster charge the exact simulator predicts vs the recorded energy.

    python tools/measure_exact_charge.py [OUT]     (default Debug/exact_charge.txt)

For every pair of research snapshots of a Charles-policy booster (Checkmate
Charles, Foxy Roxy SE) the action that reproduces the next board exactly
(board, specials, RNG; analyze_research._try_transition) is stepped once
more and its predicted meter compared with the recorded energy. A miss on
the meter alone makes the live planner drop its carried line (plan key) and
search from scratch: Bombs Away 2026-11-18 09:02 and 09:05, predicted 6 and
5, the game 7 (127 s and 97 s of new first plans). Progress goes to
OUT.progress (done/total, elapsed, ETA).
"""
from __future__ import annotations

import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.analyze_research import booster_used, grid, load, local_player, observed  # noqa: E402

BOOSTERS = {54: "Charles", 52: "Foxy"}


def knight_detail(events):
    """Each knight activation: its cell and whether a match (not an effect) set it off."""
    matched, out = set(), []
    for event in events or ():
        if not isinstance(event, dict):
            continue
        if event.get("type") == "match":
            matched |= {tuple(c) for c in event.get("cells") or ()}
        if event.get("type") == "special_activation" and event.get("special") == "knight":
            cell = tuple(event.get("cell") or ())
            out.append({"cell": list(cell), "in_match": cell in matched})
    return out


def features(events):
    kinds = Counter()
    for event in events or ():
        if isinstance(event, dict) and event.get("type") == "special_activation":
            kinds[event.get("special")] += 1
    return dict(kinds)


def pair(rec_a, cap_a, rec_b):
    from simulator_capture import lab_move
    from strategy_lab import planner, simulation

    want = observed(rec_b)
    energy_a, energy_b = local_player(rec_a).get("energy"), local_player(rec_b).get("energy")
    cost = local_player(rec_a).get("energy_to_ability")
    if energy_a is None or energy_b is None or not cost or booster_used(rec_a, rec_b):
        return None
    certified = simulation.PREFIX_MODES
    from simulator_capture import capture_mode
    simulation.PREFIX_MODES = set(certified) | {capture_mode(cap_a["profile"]).value}
    try:
        lab = lab_move(cap_a)
    except Exception:
        simulation.PREFIX_MODES = certified
        return None
    try:
        lab["check_cascade_timing"] = True
        lab["booster_state"] = {"current": energy_a, "maximum": cost}
        lab["perks"] = {simulation.PERK_ENERGY_BOOST: 1, simulation.PERK_TELEPORT: 1}
        found = []
        for action in planner.actions(lab):
            if action.get("kind", "swap") not in ("swap", "energy_boost", "teleport"):
                continue
            result = simulation.step(lab, action)
            if not result.get("supported"):
                continue
            after = result["state"]
            if (grid(after["board"]) == want["board"] and grid(after["special_board"]) == want["special_board"]
                    and after["engine_refill"].rng.counter == want["rng"]):
                found.append({"action": planner.describe(action), "kind": action.get("kind", "swap"),
                              "before": energy_a, "predicted": after["booster_state"]["current"],
                              "recorded": energy_b, "maximum": cost, "specials": features(result.get("events")),
                              "knights": knight_detail(result.get("events"))})
        # The same board from a plain swipe and from Energy Boost on it (the
        # boost changes only the meter): the one whose meter agrees is it.
        for row in found:
            if row["predicted"] == energy_b:
                return row
        return found[0] if found else None
    finally:
        simulation.PREFIX_MODES = certified
    return None


def main(argv=None):
    out = Path((argv or sys.argv[1:] or [str(ROOT / "Debug/exact_charge.txt")])[0])
    progress = out.with_suffix(".progress")
    folders = []
    for folder in sorted((ROOT / "Debug/research").iterdir()):
        files = sorted(folder.glob("[0-9][0-9][0-9].json"))
        if len(files) < 2:
            continue
        try:
            first = json.loads(files[0].read_text(encoding="utf-8"))
        except Exception:
            continue
        booster = local_player(first).get("special_ability_type")
        if booster in BOOSTERS:
            folders.append((folder, files, BOOSTERS[booster]))
    total = sum(len(files) - 1 for _, files, _ in folders)
    started, done = time.monotonic(), 0
    rows, tally, dump = [], Counter(), []
    for folder, files, name in folders:
        records = [load(path) for path in files]
        for (rec_a, cap_a), (rec_b, _) in zip(records, records[1:]):
            row = None
            try:
                row = pair(rec_a, cap_a, rec_b)
            except Exception as exc:     # a measurement: one odd pair must not stop it
                tally[f"greska {type(exc).__name__}"] += 1
            done += 1
            if row is not None:
                dump.append(dict(row, folder=folder.name, booster=name))
                # Informative only below the cap: a full meter hides the gain.
                capped = row["recorded"] >= row["maximum"] and row["predicted"] >= row["maximum"]
                ok = row["predicted"] == row["recorded"]
                tally[f"{name} {'tacno' if ok else 'PROMASAJ'}"] += 1
                if not ok:
                    rows.append(f"{folder.name} {name} {row['action']}: {row['before']} -> "
                                f"predvidjeno {row['predicted']}, snimljeno {row['recorded']} "
                                f"(max {row['maximum']}) specijali {row['specials']}")
                elif not capped:
                    tally[f"{name} tacno ispod vrha"] += 1
            elapsed = time.monotonic() - started
            eta = elapsed / done * (total - done) if done else 0
            progress.write_text(f"{done}/{total} proteklo {elapsed:.0f} s, ETA {eta:.0f} s\n", encoding="utf-8")
    text = "\n".join([f"{k}: {v}" for k, v in sorted(tally.items())] + [""] + rows)
    out.write_text(text + "\n", encoding="utf-8")
    out.with_suffix(".json").write_text(json.dumps(dump), encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
