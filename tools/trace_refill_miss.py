"""Replay the move the bot really played on a refill miss, cascade by cascade.

    python tools/trace_refill_miss.py Debug/refill_misses/FOLDER

The miss folder holds two resting boards (000.json before, 001.json after).
Since 2026-11-10 the after board's ``refill_input`` also carries what the bot
played (runtime.refill_input_detail): the swipe, or the perk and its target.
Without it the analysis can only guess the closest swap, which on a long
cascade says nothing. Moves played by hand carry no detail. A booster
activation replays too, against the game's booster trace (kind "booster").
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def played_detail(record, before=None) -> dict | None:
    """The bot's own action between ``before`` and ``record``, or None.

    The marker keeps the bot's last action; a move played by hand does not
    touch it, so the detail only belongs to this move when the bot's action
    counter went up by exactly one in between.
    """
    marker = record.get("refill_input")
    if not (isinstance(marker, (list, tuple)) and len(marker) >= 3 and isinstance(marker[2], dict)):
        return None
    if before is not None:
        previous = before.get("refill_input")
        if not isinstance(previous, (list, tuple)) or not previous or marker[0] - previous[0] != 1:
            return None
    return marker[2]


def _grid(rows):
    return [[int(v) for v in row] for row in rows]


def _point(point):
    """Match3Engine.Point [x, y] -> (row, col)."""
    return (int(point[1]), int(point[0]))


def game_passes(before, trace, result, refilled) -> list[str]:
    """The game's own cascade steps (the agent's swap trace in the after
    record, research_recorder._move_traces) next to the simulator's.

    Each destroy pass: the combo cells, the RNG around it and the board it
    destroys from. Pass k > 1 destroys from the board after refill k - 1, so
    that board is set against the simulator's; the first pass that differs is
    where the replay leaves the game.
    """
    if trace is None:
        return ["  igra: nema traga kaskada (snimak bez swap_traces, pre 2026-11-16)"]
    # Engine colour -> board colour, read off the board before the swap.
    colours = {}
    for cells, board_row in zip(trace.get("grid") or [], before["board"]):
        for cell, value in zip(cells, board_row):
            if cell is not None:
                colours.setdefault(int(cell[0]), int(value))
    sim_layers = [sorted({cell for match in layer for cell in match.cells})
                  for layer in (result.cascade_matches if result is not None else [])]
    lines = [f"  igra: trag poteza, RNG pre {trace.get('before_rng_counter')}"
             + (f", posle Use {trace['use_rng_after']}" if "use_rng_after" in trace else "")]
    passes = [e for e in trace.get("events") or () if e.get("type") == "destroy_pass"]
    first_off = None
    for number, event in enumerate(passes, start=1):
        cells = sorted(_point(p) for p in event.get("positions") or ())
        sim = sim_layers[number - 1] if number - 1 < len(sim_layers) else None
        note = ""
        grid = event.get("grid")
        if grid is not None and number > 1 and number - 2 < len(refilled):
            game_board = [[colours.get(int(c[0]), -1) if c is not None else -1 for c in row] for row in grid]
            off = [(r, c) for r, row in enumerate(game_board) for c, v in enumerate(row)
                   if v != refilled[number - 2][r][c]]
            note += f", tabla pre prolaza: {'ista' if not off else f'{len(off)} polja razlicito {off[:8]}'}"
            if off and first_off is None:
                first_off = number
        if result is not None and sim != cells:  # a booster replays outside simulate(): no layers
            note += f", SIMULATOR {sim}"
            if first_off is None:
                first_off = number
        lines.append(f"    prolaz {number}: {cells} RNG {event.get('rng_before')}->{event.get('rng_after')}{note}")
    for event in trace.get("events") or ():
        if event.get("type") == "piece_area" and event.get("cells"):
            lines.append(f"    oblast {event.get('piece')} na {_point(event['position'])}: "
                         f"{[_point(p) for p in event['cells']]} RNG {event.get('rng_before')}->{event.get('rng_after')}")
    lines.append(f"  prvo razilazenje: prolaz {first_off}" if first_off else "  svi prolazi isti kao simulator")
    return lines


def trace(folder: Path) -> str:
    from simulator_capture import capture_mode, lab_move, resolve_refill_overrides
    from strategy_lab import planner, simulation
    from tools.analyze_research import capture_from, observed

    before = json.loads((folder / "000.json").read_text(encoding="utf-8"))
    after = json.loads((folder / "001.json").read_text(encoding="utf-8"))
    detail = played_detail(after, before)
    lines = [f"{folder.name}"]
    if detail is None:
        return "\n".join(lines + ["  nema zapisanog bot-ovog poteza (potez odigran rucno ili stariji snimak)"])
    lines.append(f"  bot je odigrao: {json.dumps(detail)}")
    booster = detail.get("action") == "activate_booster"
    if not booster and (detail.get("action") != "move" or "start" not in detail):
        return "\n".join(lines + ["  nije swipe ni booster; ovaj alat ponavlja samo to dvoje"])

    capture = capture_from(before)
    want = observed(after)
    simulation.PREFIX_MODES = set(simulation.PREFIX_MODES) | {capture_mode(capture["profile"]).value}
    resolved = resolve_refill_overrides(capture["profile"])
    thresholds = None if resolved.get("resolved") else next(
        iter((resolved.get("threshold_hypotheses") or {None: None}).values()))
    lab = lab_move(capture, thresholds=thresholds)
    lab["perks"] = {}
    traces = after.get("swap_traces") or []
    if booster:
        # shortcut: a booster with a colour choice (Woolly) replays the first colour; the record has no choice.
        action = next((a for a in planner.actions(lab) if a.get("kind") == "booster"), {"kind": "booster"})
        game_trace = next((t for t in traces if t.get("kind") == "booster"), None)
    else:
        start, target = list(detail["start"]), list(detail["target"])
        direction = detail.get("direction")
        action = next((a for a in planner.actions(lab)
                       if a.get("kind", "swap") == "swap"
                       and {tuple(a["start"]), tuple(a["target"])} == {tuple(start), tuple(target)}
                       and list(a["start"]) == start
                       and (direction is None or a.get("direction") == direction)), None)
        wanted = {(start[1], start[0]), (target[1], target[0])}
        game_trace = next((t for t in reversed(traces)
                           if {tuple(t.get("position1") or ()), tuple(t.get("position2") or ())} == wanted), None)
        if action is None:
            return "\n".join(lines + ["  taj swipe nije legalan na snimljenoj tabli pre poteza"])

    captured = {}
    original = simulation.simulate
    import move_strategy as ms
    refilled = []           # the simulator's board after each cascade's refill
    original_refill = ms._drop_and_refill

    def capture_result(move, candidate):
        captured["result"] = original(move, candidate)
        return captured["result"]

    def capture_refill(*args, **kwargs):
        out = original_refill(*args, **kwargs)
        refilled.append(_grid(out[0]))
        return out

    simulation.simulate = capture_result
    ms._drop_and_refill = capture_refill
    try:
        step = simulation.step(lab, action)
    finally:
        simulation.simulate = original
        ms._drop_and_refill = original_refill
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
    lines += game_passes(before, game_trace, result, refilled)
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
