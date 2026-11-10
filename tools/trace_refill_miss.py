"""Replay the move the bot really played on a refill miss, cascade by cascade.

    python tools/trace_refill_miss.py Debug/refill_misses/FOLDER

The miss folder holds two resting boards (000.json before, 001.json after).
Since 2026-11-10 the after board's ``refill_input`` also carries what the bot
played (runtime.refill_input_detail): the swipe, or the perk and its target.
Without it the analysis can only guess the closest swap, which on a long
cascade says nothing. Moves played by hand carry no detail.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def played_detail(record) -> dict | None:
    marker = record.get("refill_input")
    if isinstance(marker, (list, tuple)) and len(marker) >= 3 and isinstance(marker[2], dict):
        return marker[2]
    return None


def _grid(rows):
    return [[int(v) for v in row] for row in rows]


def trace(folder: Path) -> str:
    from simulator_capture import capture_mode, lab_move, resolve_refill_overrides
    from strategy_lab import planner, simulation
    from tools.analyze_research import capture_from, observed

    before = json.loads((folder / "000.json").read_text(encoding="utf-8"))
    after = json.loads((folder / "001.json").read_text(encoding="utf-8"))
    detail = played_detail(after)
    lines = [f"{folder.name}"]
    if detail is None:
        return "\n".join(lines + ["  nema zapisanog poteza (stariji snimak ili potez odigran rucno)"])
    lines.append(f"  bot je odigrao: {json.dumps(detail)}")
    if detail.get("action") != "move" or "start" not in detail:
        return "\n".join(lines + ["  nije obican swipe; ovaj alat ponavlja samo swipe"])

    capture = capture_from(before)
    want = observed(after)
    simulation.PREFIX_MODES = set(simulation.PREFIX_MODES) | {capture_mode(capture["profile"]).value}
    resolved = resolve_refill_overrides(capture["profile"])
    thresholds = None if resolved.get("resolved") else next(
        iter((resolved.get("threshold_hypotheses") or {None: None}).values()))
    lab = lab_move(capture, thresholds=thresholds)
    lab["perks"] = {}
    start, target = list(detail["start"]), list(detail["target"])
    action = next((a for a in planner.actions(lab)
                   if a.get("kind", "swap") == "swap"
                   and {tuple(a["start"]), tuple(a["target"])} == {tuple(start), tuple(target)}
                   and list(a["start"]) == start), None)
    if action is None:
        return "\n".join(lines + ["  taj swipe nije legalan na snimljenoj tabli pre poteza"])

    captured = {}
    original = simulation.simulate

    def capture_result(move, candidate):
        captured["result"] = original(move, candidate)
        return captured["result"]

    simulation.simulate = capture_result
    try:
        step = simulation.step(lab, action)
    finally:
        simulation.simulate = original
    result = captured.get("result")
    if result is not None:
        for number, layer in enumerate(result.cascade_matches, start=1):
            lines.append(f"  sloj {number}: " + ", ".join(
                f"{m.kind} boja {m.color} {sorted(m.cells)}" for m in layer))
        for event in result.intent_events:
            kind = event.get("type", "")
            if kind in ("match", "special_effect"):
                continue
            lines.append("    " + json.dumps({k: event.get(k) for k in
                                              ("type", "special", "cascade", "cell", "cells", "selected")
                                              if k in event}))
    if not step.get("supported"):
        return "\n".join(lines + [f"  simulator: nepodrzano - {step.get('reason')}"])
    state = step["state"]
    got_board, got_special = _grid(state["board"]), _grid(state["special_board"])
    lines.append(f"  dopune (rupa po sloju): {[len(t) for t in step['refills']]}")
    lines.append(f"  RNG igra/sim: {want['rng']} / {state['engine_refill'].rng.counter}")
    n = len(got_board)
    cells = [(r, c, want["board"][r][c], got_board[r][c]) for r in range(n) for c in range(n)
             if want["board"][r][c] != got_board[r][c]]
    specials = [(r, c, want["special_board"][r][c], got_special[r][c]) for r in range(n) for c in range(n)
                if want["special_board"][r][c] != got_special[r][c]]
    lines.append(f"  razlicita polja (red, kol, igra, sim): {cells}")
    lines.append(f"  razliciti specijali (red, kol, igra, sim): {specials}")
    lines.append("      igra                  |  simulator")
    for (wb, ws), (gb, gs) in zip(zip(want["board"], want["special_board"]), zip(got_board, got_special)):
        lines.append("    " + " ".join(f"{v:2d}" for v in wb) + " | " + " ".join(f"{v:2d}" for v in ws)
                     + "   ||   " + " ".join(f"{v:2d}" for v in gb) + " | " + " ".join(f"{v:2d}" for v in gs))
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("folders", nargs="+", type=Path)
    args = parser.parse_args(argv)
    for folder in args.folders:
        print(trace(folder))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
