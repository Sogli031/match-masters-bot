"""Monkey JooJoo (booster 40): every recorded activation against the port.

    python tools/monkey_check.py [Debug/research/FOLDER] [--candidates]

For each activation (a pair NNN -> NNN+1 whose action is activate_booster) it
plays the ported activation (engine_monkey + strategy_lab.simulation.step) and
compares board, special pieces, RNG counter, points and the booster meter with
the next record. Report: TACNO, or the nearest miss with the per-field diff;
screen and FOLDER/monkey_check.txt.

--candidates plays each of the maxTries ChoosePositions candidates in turn,
so a wrong pick rule can be told apart from wrong placement mechanics: it
prints which candidate index reproduces the game's board and whether any
candidate carries exactly the game's new skull cells.

Progress (done/total, elapsed, ETA, finish time) goes to
FOLDER/monkey_check_progress.txt while the folder is played (CLAUDE.md).
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from simulator_capture import capture_mode, lab_move, resolve_refill_overrides
from tools.analyze_research import grid, load, local_player, observed
from tools.replay_one_to_one import recorded_action


def _skulls(special):
    return {(r, c) for r, row in enumerate(special) for c, v in enumerate(row) if int(v) == 19}


def _play(rec_a, cap_a, index=None):
    """The ported activation from rec_a; returns (state, result) or a skip string."""
    from strategy_lab import simulation

    action = {"kind": "booster"}
    if index is not None:
        action["monkey_candidate"] = index
    # The activation is measured, not planned: step refuses it until the cells
    # converge (simulation.MONKEY_JOOJOO_PORTED).
    simulation.MONKEY_JOOJOO_PORTED = True
    certified = simulation.PREFIX_MODES
    simulation.PREFIX_MODES = set(certified) | {capture_mode(cap_a["profile"]).value}
    try:
        resolved = resolve_refill_overrides(cap_a["profile"])
        thresholds = None if resolved.get("resolved") else next(
            iter((resolved.get("threshold_hypotheses") or {None: None}).values()))
        lab = lab_move(cap_a, thresholds=thresholds)
        lab["booster_type"] = 40
        lab["check_cascade_timing"] = True
        result = simulation.step(lab, action)
    finally:
        simulation.PREFIX_MODES = certified
    if not result.get("supported"):
        return result.get("reason") or "nije podrzano"
    return result


def compare(rec_a, cap_a, rec_b, index=None):
    result = _play(rec_a, cap_a, index)
    if isinstance(result, str):
        return {"skip": result}
    want = observed(rec_b)
    after = result["state"]
    board, special = grid(after["board"]), grid(after["special_board"])
    me_a, me_b = local_player(rec_a), local_player(rec_b)
    charge = (after.get("booster_state") or {}).get("current")
    want_skulls = _skulls(want["special_board"])
    got_skulls = _skulls(special)
    return {
        "candidate": index,
        "cells": sum(board[r][c] != want["board"][r][c] for r in range(len(board))
                     for c in range(len(board[r]))),
        "specials": sum(special[r][c] != want["special_board"][r][c] for r in range(len(special))
                        for c in range(len(special[r]))),
        "rng": (want["rng"], after["engine_refill"].rng.counter),
        "points": ((me_b.get("score") or 0) - (me_a.get("score") or 0), result.get("score_gain")),
        "charge": (me_b.get("energy"), charge),
        "skulls": (sorted(want_skulls), sorted(got_skulls)),
        "moves": (want["moves"], (after.get("turn_state") or {}).get("remaining_moves")),
    }


def exact(row) -> bool:
    return (not row.get("skip") and row["cells"] == 0 and row["specials"] == 0
            and row["rng"][0] == row["rng"][1] and row["points"][0] == row["points"][1]
            and row["charge"][0] == row["charge"][1])


def line(name, row) -> str:
    if row.get("skip"):
        return f"{name}: PRESKOCENO - {row['skip']}"
    if exact(row):
        return (f"{name}: TACNO  (poeni {row['points'][0]}, punjenje {row['charge'][0]}, "
                f"rng {row['rng'][0]})")
    where = "kandidat %s " % row["candidate"] if row.get("candidate") is not None else ""
    return (f"{name}: {where}razlika polja {row['cells']}, specijala {row['specials']}, "
            f"rng igra/sim {row['rng'][0]}/{row['rng'][1]}, poeni igra/sim "
            f"{row['points'][0]}/{row['points'][1]}, punjenje {row['charge'][0]}/{row['charge'][1]}, "
            f"lobanje {len(row['skulls'][0])}/{len(row['skulls'][1])}")


def activations(folder: Path):
    files = sorted(folder.glob("[0-9][0-9][0-9].json"))
    for before, after in zip(files, files[1:]):
        record = load(after)[0]
        action, _ = recorded_action(record)
        if action is not None and action.get("kind") == "booster":
            yield before, after


def main(argv) -> int:
    folders = [Path(a) for a in argv if not a.startswith("-")]
    try_candidates = "--candidates" in argv
    folder = folders[0] if folders else sorted((ROOT / "Debug" / "research").iterdir())[-1]
    out = []
    pairs = list(activations(folder))
    rows = []
    progress = folder / "monkey_check_progress.txt"
    started = time.monotonic()
    for done, (before, after) in enumerate(pairs, 1):
        rec_a, cap_a = load(before)
        rec_b = load(after)[0]
        attempts = [None] if not try_candidates else list(range(5))
        results = []
        for index in attempts:
            row = compare(rec_a, cap_a, rec_b, index)
            results.append(row)
            out.append(line(f"{before.stem}->{after.stem}", row))
        row = next((r for r in results if exact(r)), results[0])
        rows.append(row)
        elapsed = time.monotonic() - started
        eta = elapsed / done * (len(pairs) - done)
        progress.write_text(
            f"{done}/{len(pairs)} ({done * 100 // len(pairs)}%), proteklo {elapsed:.0f} s, "
            f"ostalo ~{eta:.0f} s, kraj oko "
            f"{time.strftime('%H:%M', time.localtime(time.time() + eta))}\n", encoding="utf-8")
        if try_candidates and not exact(row):
            want = set(grid(rec_b["special_board"]) and _skulls(grid(rec_b["special_board"])))
            hits = [r["candidate"] for r in results if not r.get("skip") and r["cells"] == 0
                    and r["specials"] == 0]
            skulls = [r["candidate"] for r in results if not r.get("skip")
                      and set(r["skulls"][1]) == want]
            out.append(f"    kandidati sa tacnom tablom: {hits}; sa tacnim lobanjama: {skulls}")
    good = sum(1 for row in rows if exact(row))
    out.append("")
    out.append(f"UKUPNO: TACNO {good} od {len(rows)} aktivacija u {folder.name}")
    text = "\n".join(out)
    (folder / "monkey_check.txt").write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
