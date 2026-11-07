"""Whole-turn planner over the exact Square Solo simulator.

From one captured state, beam search tries move sequences with the ported
refill and engine RNG, so every simulated future is the game's own future
for that exact sequence. Only deterministic swaps are searched: boosters,
perks and random-target specials are not ported yet, and a plan is valid
only while it is played exactly in order.

    python -m strategy_lab.planner PATH_TO_CAPTURE [--width 100]
"""
from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import move_strategy as ms

from .simulation import PERK_ENERGY_BOOST, PERK_TELEPORT, rules, step


@dataclass
class Line:
    state: dict
    actions: list = field(default_factory=list)
    gains: list = field(default_factory=list)

    @property
    def score(self):
        return self.state.get("score") or 0

    @property
    def moves_left(self):
        return self.state["turn_state"].get("remaining_moves") or 0


def actions(state):
    """Every swipe in both drag directions (they can differ in special
    placement), the same swipes behind Energy Boost, every Teleport pair that
    can match, and the booster when it is charged."""
    perks = state.get("perks") or {}
    with rules(state):
        out, seen = [], set()
        for candidate in ms.generate_candidates(state["board"], state["special_board"]):
            for oriented in (candidate, ms.flip_swap_candidate(candidate)):
                key = (tuple(oriented.start), tuple(oriented.target))
                if key not in seen:
                    seen.add(key)
                    out.append({"start": list(oriented.start), "target": list(oriented.target),
                                "direction": oriented.direction.value})
        if perks.get(PERK_ENERGY_BOOST, 0) > 0:
            out += [dict(a, kind="energy_boost") for a in out if a.get("kind", "swap") == "swap"]
        if perks.get(PERK_TELEPORT, 0) > 0:
            board = state["board"]
            square = bool(state.get("allow_square_matches"))
            special = state["special_board"]
            for first, second in ms._teleport_candidate_pairs(board, special):
                if ms.SPECIAL_DISCO_BALL in (special[first[0]][first[1]], special[second[0]][second[1]]):
                    continue    # a ball's swap is its own activation, only between neighbours
                if ms._teleport_swap_can_match(board, first, second, square):
                    out.append({"kind": "teleport", "start": list(first), "target": list(second),
                                "direction": ms._teleport_direction(first, second).value})
    charge = state.get("booster_state") or {}
    if (PLAN_BOOSTER and charge.get("maximum") is not None
            and (charge.get("current") or 0) >= charge["maximum"]):
        out.append({"kind": "booster"})
    return out


# Off until Doctor Color matches a recorded activation: the game resolves
# matches and refills between its recolouring steps, which the simulator
# does not reproduce yet (solo_gui_20261101_010124 06 -> 07).
PLAN_BOOSTER = False


def _key(state):
    model = state["engine_refill"]
    return (bytes(int(v) & 0xFF for row in state["board"] for v in row),
            bytes(int(v) & 0xFF for row in state["special_board"] for v in row),
            state.get("score"), state["turn_state"].get("remaining_moves"), model.rng.counter)


def plan(state, width=100, max_steps=40, deadline=None):
    """Return the best Line found and search statistics.

    Lines are ranked by score; a line that runs out of moves (or of
    supported actions) is final and is kept for the comparison.
    """
    if state.get("engine_refill") is None:
        raise ValueError("planner needs a capture-backed engine_refill model")
    beam, finished = [Line(state)], []
    expanded = simulated = 0
    complete = True
    for _ in range(max_steps):
        if not beam:
            break
        if deadline is not None and time.monotonic() > deadline:
            complete = False
            break
        children, seen = [], set()
        for line in beam:
            if line.moves_left <= 0:
                finished.append(line)
                continue
            expanded += 1
            grew = False
            for action in actions(line.state):
                result = step(line.state, action)
                simulated += 1
                if not result["supported"]:
                    continue
                key = _key(result["state"])
                if key in seen:
                    continue
                seen.add(key)
                grew = True
                children.append(Line(result["state"], line.actions + [action],
                                     line.gains + [result["score_gain"]]))
            if not grew:
                finished.append(line)
        children.sort(key=lambda l: (l.score, l.moves_left), reverse=True)
        beam = children[:width]
    finished.extend(beam)
    best = max(finished, key=lambda l: (l.score, l.moves_left), default=Line(state))
    return best, {"expanded": expanded, "simulated": simulated, "finished": len(finished),
                  "complete": complete, "width": width}


def plan_anytime(state, seconds, widths=(1, 4, 10, 25, 60, 150, 400, 1000)):
    """Full-depth plans of growing width until the time runs out.

    The narrow first pass reaches the last move quickly, so the answer always
    covers the whole turn; a wider pass replaces it only if it completes and
    scores at least as much. A pass cut by the deadline is discarded.
    """
    deadline = time.monotonic() + seconds
    best = stats = None
    simulated = 0
    for width in widths:
        line, run = plan(state, width=width, deadline=None if best is None else deadline)
        simulated += run["simulated"]
        if run["complete"] and (best is None or line.score >= best.score):
            best, stats = line, run
        if not run["complete"] or time.monotonic() > deadline:
            break
    stats = dict(stats, simulated=simulated)
    return best, stats


def describe(action):
    kind = action.get("kind", "swap")
    if kind == "booster":
        return "BOOSTER (Doctor Color)"
    (r, c), (y, x) = action["start"], action["target"]
    move = f"red {r} kol {c} -> red {y} kol {x}"
    return {"energy_boost": "ENERGY BOOST + ", "teleport": "TELEPORT "}.get(kind, "") + move


def main(argv=None):
    from simulator_capture import lab_move, load_capture

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("capture", type=Path)
    parser.add_argument("--width", type=int, default=100, help="broj tokova koji se cuvaju po potezu")
    parser.add_argument("--seconds", type=float, default=None, help="vremensko ogranicenje")
    args = parser.parse_args(argv)
    if sys.stdout is not None and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    state = lab_move(load_capture(args.capture))
    started = time.monotonic()
    deadline = started + args.seconds if args.seconds else None
    best, stats = plan(state, width=args.width, deadline=deadline)
    print(report(state, best, stats, time.monotonic() - started))
    return 0


def report(state, best, stats, seconds):
    lines = [f"Skor sada {state.get('score')}, poteza {state['turn_state'].get('remaining_moves')}; "
             f"plan: skor {best.score} ({best.score - (state.get('score') or 0):+d}), "
             f"{len(best.actions)} poteza, {stats['simulated']} simulacija za {seconds:.1f} s"]
    targets = [t for t in state.get("solo_targets") or [] if t > (state.get("score") or 0)]
    if targets:
        lines.append(f"Sledeci cilj {targets[0]}: {'DOSTIZE' if best.score >= targets[0] else 'ne dostize'}")
    for number, (action, gain) in enumerate(zip(best.actions, best.gains), 1):
        lines.append(f"  {number:2d}. {describe(action)}  (+{int(round(gain))})")
    if not best.actions:
        lines.append("  nema podrzanog poteza")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
