"""Whole-turn planner over the exact Square Solo simulator.

From one captured state, beam search tries move sequences with the ported
refill and engine RNG, so every simulated future is the game's own future
for that exact sequence. The search uses deterministic swaps, supported
booster activations and supported perks. A plan stays valid while its
actions are played in order.

    python -m strategy_lab.planner PATH_TO_CAPTURE [--width 100]
"""
from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import move_strategy as ms

from .simulation import PERK_ENERGY_BOOST, PERK_REMOVE_CROSS, PERK_TELEPORT, rules, step


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

    @property
    def value(self):
        """Score plus the booster charge, when the state prices it.

        ``booster_fire_value``: what one activation brings (the bot fires the
        booster itself; the planner plays swaps only). Each full meter is
        banked as one activation (``booster_fired``) and the meter starts
        again; a partial meter counts pro rata. Without the price this is the
        plain score, as before.
        """
        score = self.score
        future = self.state.get("multiplier_value")
        if future and self.state.get("score_multiplier"):
            # ``multiplier_value``: what one point of our score multiplier is
            # worth in the turns still to come (Versus, square_solo_live).
            score += future * int(self.state["score_multiplier"])
        price = self.state.get("booster_fire_value")
        charge = self.state.get("booster_state") or {}
        if not price or not charge.get("maximum"):
            return score
        partial = min(1.0, (charge.get("current") or 0) / charge["maximum"])
        return score + price * ((self.state.get("booster_fired") or 0) + partial)


def _rank(line, steps_left=None):
    """Beam order: the value, plus the moves in hand and the meter.

    Only for keeping lines in the beam; the plan is still chosen by value.

    ``rank_move_value``: points a move still in hand counts for. Lines of one
    step have played the same number of actions but not spent the same number
    of moves (a booster, Energy Boost or a +1 cascade costs none), and by the
    plain score a line that kept a move loses to one that spent it.
    tools/plan_width_curve --move-prices 2026-11-15 05:48 and 06:00, 23
    Charles games, booster held, width 10 (width 4): price 0 36081 (30139),
    20 57023, 40 76906, 60 96556, 80 118373, 100 143470 (76807), 140 142784
    (71918); the plans grow from 25 to 112 actions on average, up to 201.
    On the multiplier boards it is multiplied by the line's score multiplier.
    ``steps_left``: the actions the line may still play (plan(max_steps), the
    turn clock); a move beyond them is worth nothing. A held Teleport,
    Energy Boost or Remove Cross counts as a move in hand (none costs a move).

    ``rank_charge_value``: the meter, a full one at this price. Without it a
    half-charged meter is worth nothing mid-search. Not used live:
    tools/plan_width_curve 2026-11-15 02:29, 14 Charles games, booster held,
    width 60: price 0 33170, 22 30602, 44 31635, 88 27349 (width 25: 29013 /
    24901 / 26839 / 21962). The plain score keeps better lines.
    """
    move = line.state.get("rank_move_value")
    # A held perk (Teleport, Energy Boost, Remove Cross) is an action that
    # costs no move, so it is a move in hand too. Unpriced, the perk line kept
    # its move and beat the same swipe by a whole move price, and the beam
    # threw the perks at the first steps.
    perks = line.state.get("perks") or {}
    hand = line.moves_left + sum(perks.get(p, 0) for p in (PERK_TELEPORT, PERK_ENERGY_BOOST, PERK_REMOVE_CROSS))
    hand = hand if steps_left is None else min(hand, steps_left)
    if "time_left" in line.state:
        # A timed line (the race): only the swipes the clock still allows count.
        swipe = _action_seconds(line.state, {})
        if swipe > 0:
            hand = min(hand, max(0, int(line.state["time_left"] / swipe)))
    if move and line.state.get("score_multiplier"):
        # A move is paid at the line's multiplier (Vertical Rush and the other
        # multiplier boards): Debug/plan_check 2026-11-19 13:30, VR + Sweep,
        # width 25 from the first board 42010 -> 1037806, a third in
        # 318212 -> 1075243 (lines of 300 actions, the moves kept).
        move = move * max(1, int(line.state["score_multiplier"]))
    rank = line.value + (move * hand if move else 0) + _board_value(line.state)
    price = line.state.get("rank_charge_value")
    charge = line.state.get("booster_state") or {}
    if not price or not charge.get("maximum") or line.moves_left <= 0:
        return rank
    return rank + price * min(1.0, (charge.get("current") or 0) / charge["maximum"])


RANKED_SPECIALS = frozenset((ms.SPECIAL_HORIZONTAL, ms.SPECIAL_VERTICAL, ms.SPECIAL_BOMB, ms.SPECIAL_LIGHTNING,
                             ms.SPECIAL_CROSSHAIR, ms.SPECIAL_DISCO_BALL))


# Default ``rank_special_value``: 44 boards (Debug/rank_sweep, width 10) +4.7 %;
# Showdown races played to the end (tools/showdown_strategy, 2026-11-20,
# Debug/showdown_strategy3) +4.8 % against none, 10 too much (-16 %).
RANK_SPECIAL_VALUE = 5


def _board_value(state):
    """What the specials resting on the board are worth to the beam order.

    ``rank_special_value``: points per resting special (rocket, bomb,
    lightning, crosshair, disco); ``rank_pair_value``: more for each pair of
    them side by side (a combo swipe). Both at the line's score multiplier.
    ``rank_special_value`` None or 0 turns it off; never part of Line.value.
    """
    each, pair = state.get("rank_special_value", RANK_SPECIAL_VALUE), state.get("rank_pair_value")
    if (not each and not pair) or "special_board" not in state:
        return 0.0
    special = state["special_board"]
    cells = {(r, c) for r, row in enumerate(special) for c, v in enumerate(row) if v in RANKED_SPECIALS}
    pairs = sum(((r, c + 1) in cells) + ((r + 1, c) in cells) for r, c in cells) if pair else 0
    return ((each or 0) * len(cells) + (pair or 0) * pairs) * max(1, int(state.get("score_multiplier") or 1))


def _diverse(children, width, steps_played, state):
    """The beam's ``width`` lines; in the first ``diverse_steps`` steps no more
    than ``diverse_max`` of them share a first action (slots left over go to
    the next best lines). ``children`` comes sorted best first."""
    steps, most = state.get("diverse_steps"), state.get("diverse_max")
    if not steps or not most or steps_played >= steps or len(children) <= width:
        return children[:width]
    kept, rest, count = [], [], {}
    for line in children:
        first = repr(line.actions[0])
        if count.get(first, 0) < most:
            count[first] = count.get(first, 0) + 1
            kept.append(line)
            if len(kept) == width:
                return kept
        else:
            rest.append(line)
    return kept + rest[:width - len(kept)]


def _action_seconds(state, action):
    """Turn clock an action costs (``action_seconds``: {kind: seconds}, "swap"
    for a swipe). Only states carrying ``time_left`` are timed; without it a
    line ends on the move counter alone, as before."""
    costs = state.get("action_seconds") or {}
    return float(costs.get(action.get("kind", "swap"), costs.get("swap", 0.0)))


def _bank_full_meter(state):
    """A meter the swap filled is fired by the bot: bank it and start again."""
    price = state.get("booster_fire_value")
    charge = state.get("booster_state") or {}
    if not price or not charge.get("maximum") or (charge.get("current") or 0) < charge["maximum"]:
        return state
    state = dict(state, booster_state=dict(charge, current=0),
                 booster_fired=(state.get("booster_fired") or 0) + 1)
    return state


def actions(state):
    """Every swipe in both drag directions (they can differ in special
    placement), the same swipes behind Energy Boost, every Teleport pair that
    can match, and the booster when it is charged."""
    perks = state.get("perks") or {}
    charge = state.get("booster_state") or {}
    full = charge.get("maximum") is not None and (charge.get("current") or 0) >= charge["maximum"]
    if state.get("booster_auto") and full and not state.get("booster_hold"):
        # The bot fires a full booster before any swipe (Checkmate Charles,
        # ported exactly): the line plays it as the bot will.
        return booster_actions(state)
    with rules(state):
        out, seen = [], set()
        # Two plain colours that make no line match nothing: step() refuses them
        # ("candidate no longer legal"), ~90 % of the swipes (answer 23). Not
        # where a no-line swap can still match: a 2x2 square, a candy / two-colour
        # heart beside it, or Mixy's convert_swap.
        skip = (not state.get("allow_square_matches") and not ms._has_color_flexible_specials(state["special_board"])
                and getattr(state.get("engine_refill"), "mixy", None) is None)
        for candidate in ms.generate_candidates(state["board"], state["special_board"],
                                                skip_plain_without_line=skip):
            for oriented in (candidate, ms.flip_swap_candidate(candidate)):
                # A spray's swipe stays on its cell (start == target): the
                # direction is the move, so all four are different actions.
                key = (tuple(oriented.start), tuple(oriented.target),
                       oriented.direction.value if oriented.start == oriented.target else None)
                if key not in seen:
                    seen.add(key)
                    out.append({"start": list(oriented.start), "target": list(oriented.target),
                                "direction": oriented.direction.value})
        if perks.get(PERK_ENERGY_BOOST, 0) > 0 and not full:
            # The game refuses Energy Boost while the booster meter is full
            # (Square Match 2026-11-15 03:3x, a held Charles meter).
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
    if perks.get(PERK_REMOVE_CROSS, 0) > 0:
        # Every cell: its whole row and column (simulation.REMOVE_CROSS).
        out += [{"kind": "remove_cross", "cell": [r, c]}
                for r in range(len(state["board"])) for c in range(len(state["board"][0]))]
    if full and (PLAN_BOOSTER or state.get("booster_auto")):
        # booster_hold: a full meter may wait while swipes go on (charge
        # past the maximum is lost, simulation.step caps it).
        out[:0] = booster_actions(state)
    return out


def booster_actions(state):
    """The booster's actions: one, or for Woolly Workout one per colour it can
    tap (a plain piece of a green/yellow/purple/orange, CanBeTarget)."""
    from .simulation import WOOLLY_WORKOUT

    if state.get("booster_type") != WOOLLY_WORKOUT:
        return [{"kind": "booster"}]
    board, special = state["board"], state["special_board"]
    colors = sorted({int(v) for r, row in enumerate(board) for c, v in enumerate(row)
                     if int(v) in ms.WOOLLY_WORKOUT_TARGET_COLORS and int(special[r][c]) == ms.EMPTY})
    return [{"kind": "booster", "color": color} for color in colors]


# Off until Doctor Color matches a recorded activation: the game resolves
# matches and refills between its recolouring steps, which the simulator
# does not reproduce yet (solo_gui_20261101_010124 06 -> 07).
PLAN_BOOSTER = False


def _key(state):
    model = state["engine_refill"]
    charge = state.get("booster_state") or {}
    return (bytes(int(v) & 0xFF for row in state["board"] for v in row),
            bytes(int(v) & 0xFF for row in state["special_board"] for v in row),
            state.get("score"), state["turn_state"].get("remaining_moves"), model.rng.counter,
            charge.get("current"), state.get("booster_fired"),
            tuple(state.get("column_multipliers") or ()))


def plan(state, width=100, max_steps=300, deadline=None, finish_cut=False, root_actions=None):
    """Return the best Line found and search statistics.

    Lines are ranked by score; a line that runs out of moves (or of
    supported actions) is final and is kept for the comparison.

    ``finish_cut``: a pass the deadline cuts is not dropped. It stops widening
    at once (also in the middle of a step) and its best line is played to the
    end at width 1, so the work done so far still gives a whole-turn line
    (``complete`` stays False). Live 2026-11-15 05:25: the 150 s first plan
    kept width 10 and threw the cut width-25 pass away.

    ``root_actions``: only these first actions (one worker's share of the
    root, PLAN_WORKERS).
    """
    if state.get("engine_refill") is None:
        raise ValueError("planner needs a capture-backed engine_refill model")
    if PLAN_WORKERS > 1 and width >= SPLIT_MIN_WIDTH and root_actions is None:
        return _plan_split(state, width, max_steps, deadline, finish_cut)
    # The mode switches for the whole search: every step inside with the
    # same ones skips setting them again (simulation._rules_key).
    with rules(state, board_layers=False):
        return _plan(state, width, max_steps, deadline, finish_cut, root_actions)


# Root parallelism: plan() splits the first actions over PLAN_WORKERS
# processes, each with its own beam of the full width, and keeps the best.
# 1 = one process, as before (offline tools, tests). square_solo_live sets it.
PLAN_WORKERS = 1
SPLIT_MIN_WIDTH = 10    # narrower passes take well under a second: not worth the pool
SPLIT_LINES = 30        # finished lines each worker sends back (Versus picks among them)
_SPLIT_POOL = None


def _below_normal():
    """Pool workers yield to the GUI and the emulator (as background_plan)."""
    if sys.platform == "win32":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.GetCurrentProcess.restype = ctypes.c_void_p
            kernel32.SetPriorityClass(ctypes.c_void_p(kernel32.GetCurrentProcess()), 0x4000)
        except Exception:
            pass


def _split_pool():
    global _SPLIT_POOL
    if _SPLIT_POOL is None or _SPLIT_POOL._processes != PLAN_WORKERS:
        from multiprocessing import Pool
        if _SPLIT_POOL is not None:
            _SPLIT_POOL.terminate()
        _SPLIT_POOL = Pool(PLAN_WORKERS, initializer=_below_normal)
    return _SPLIT_POOL


def _plan_root(item):
    """One worker's share: plan() from the root over its first actions."""
    state, root, width, max_steps, deadline, finish_cut, modes = item
    from . import simulation
    simulation.PREFIX_MODES = set(modes)   # the caller's certified modes, not the import default
    best, stats = plan(state, width, max_steps, deadline, finish_cut, root_actions=root)
    lines = sorted(stats["lines"], key=lambda l: (l.value, l.moves_left), reverse=True)[:SPLIT_LINES]
    return best, dict(stats, lines=lines)


def _plan_split(state, width, max_steps, deadline, finish_cut):
    from . import simulation
    with rules(state):
        first = actions(state)
    groups = [g for g in (first[i::PLAN_WORKERS] for i in range(PLAN_WORKERS)) if g]
    if len(groups) < 2:
        with rules(state, board_layers=False):
            return _plan(state, width, max_steps, deadline, finish_cut, None)
    modes = tuple(simulation.PREFIX_MODES)
    results = _split_pool().map(_plan_root, [(state, g, width, max_steps, deadline, finish_cut, modes)
                                            for g in groups])
    best = max((b for b, _ in results), key=lambda l: (l.value, l.moves_left))
    runs = [r for _, r in results]
    return best, {"expanded": sum(r["expanded"] for r in runs), "simulated": sum(r["simulated"] for r in runs),
                  "finished": sum(r["finished"] for r in runs), "complete": all(r["complete"] for r in runs),
                  "width": width, "lines": [l for r in runs for l in r["lines"]], "workers": len(groups)}


def _plan(state, width, max_steps, deadline, finish_cut, root_actions=None):
    beam, finished = [Line(state)], []
    expanded = simulated = 0
    complete = True
    for index in range(max_steps):
        if not beam:
            break
        if complete and deadline is not None and time.monotonic() > deadline:
            complete = False
            if not finish_cut:
                break
        children, seen = [], set()
        for line in beam:
            if line.moves_left <= 0 or line.state.get("time_left", 1) <= 0:
                finished.append(line)
                continue
            if finish_cut and deadline is not None and children and (
                    not complete or time.monotonic() > deadline):
                complete = False    # cut: one line goes on, the rest are dropped
                continue
            expanded += 1
            grew = False
            scan_cache = {}     # the parent's board is scanned once for all its children
            mirrored = set()
            for action in (root_actions if index == 0 and root_actions is not None
                           else actions(line.state)):
                if _swipe_cells(action) in mirrored:
                    continue
                result = step(line.state, action, scan_cache)
                simulated += 1
                if not result["supported"]:
                    continue
                if _mirror_same(line.state, action, result):
                    start, target = _swipe_cells(action)[1:]
                    mirrored.add((action.get("kind", "swap"), target, start))
                child_state = _bank_full_meter(result["state"])
                if "time_left" in line.state:
                    child_state = dict(child_state, time_left=line.state["time_left"]
                                       - _action_seconds(line.state, action))
                key = _key(child_state)
                if key in seen:
                    continue
                seen.add(key)
                grew = True
                children.append(Line(child_state, line.actions + [action],
                                     line.gains + [result["score_gain"]]))
            if not grew:
                finished.append(line)
        left = max_steps - index - 1
        children.sort(key=lambda l: (_rank(l, left), l.moves_left), reverse=True)
        beam = _diverse(children, width if complete else 1, index, state)
    finished.extend(beam)
    best = max(finished, key=lambda l: (l.value, l.moves_left), default=Line(state))
    return best, {"expanded": expanded, "simulated": simulated, "finished": len(finished),
                  "complete": complete, "width": width, "lines": finished}


def _swipe_cells(action):
    return (action.get("kind", "swap"), tuple(action.get("start") or ()), tuple(action.get("target") or ()))


def _mirror_same(state, action, result):
    """Whether the same swipe dragged the other way (B -> A) ends in this very
    state, so it need not be simulated (answer 23): two plain pieces, no 4+
    first match (its special's cell), no UFO lock or lotus gather, no Mixy or
    every-match-is-special. Checked on every such swipe of 40 width-10 plans
    (Debug/speed/check_reverse.py, 2026-11-20): 53 432 of 53 432 the same."""
    if action.get("kind", "swap") not in ("swap", "energy_boost"):
        return False
    start, target = action.get("start"), action.get("target")
    special = state["special_board"]
    if (start == target or special[start[0]][start[1]] or special[target[0]][target[1]]
            or state.get("every_match_is_special")
            or getattr(state.get("engine_refill"), "mixy", None) is not None):
        return False
    return not any(e.get("type") in ("ufo_color_lock", "froggy_lotus_gather")
                   or (e.get("type") == "match" and int(e.get("cascade") or 0) == 1
                       and int(e.get("tile_count") or 0) >= 4)
                   for e in result.get("events") or ())


WIDTHS = (1, 4, 10, 25, 60, 150, 400, 1000)


def next_width(width, widths=WIDTHS):
    """The first width above ``width`` (the widest one when there is none)."""
    return next((w for w in widths if w > (width or 0)), widths[-1])


# A pass takes more than its width's share of the one before: live
# 2026-11-15 15:23-16:13, four first plans, width 4 -> 10 (2.5 times wider)
# took 3.3 to 4.7 times as long.
PASS_TIME_GROWTH = 1.3


# Dynamic stop (plan_anytime ``rule``): after each whole pass the gain over
# the best line before it (or over the carried line, ``baseline``) is
# measured; below the threshold the search stops and the best line plays.
#   min_gain:        relative gain (fraction of the line's value) a pass must
#                    bring for the next one to start;
#   min_points:      the same in points (the larger of the two counts);
#   gain_per_second: the next pass's expected relative gain (the last one's
#                    times gain_decay) per second it is expected to take
#                    (seconds of the last pass x width ratio x
#                    PASS_TIME_GROWTH) -- below this it does not pay;
#   min_width:       the first plan does not stop before this width is done
#                    (the narrow passes are noisy and cost little).
# The time limit (turn clock, the caller's seconds) stays as a fence only.
# Measured: tools/plan_stop_curve 2026-11-17 22:34, every width run to the
# end with the live policy (booster held, a move in hand at 100, the clock as
# max_steps) on 41 first boards and 35 boards a third into the game (Charles
# and Foxy Roxy SE research, Debug/plan_stop_curve.txt). The curve does not
# flatten up to width 60: median gain over the width before, first boards
# 4->10 +39 %, 10->25 +50 %, 25->60 +12 % (34 of 41 better); a third in
# +51 %, +13 %, +8 % (32 of 35). After a width that brought nothing or lost
# (14 cases, width 10 to 25), the next one still gained in 12 (median +30 to
# +50 %, up to +222 %), so a stop on the gain below width 60 only loses
# points: every rule that could stop there scored below the old 150 s first
# plan. The search has converged only past it: live 2026-11-17 13:11 and
# 20:12-20:14 widths 150 / 400 / 1000 gave the same line (Foxy Roxy SE,
# near the end). So the stop is: from width 150 on, a pass that brings
# nothing ends the search. The time per pass did not pay for anything either
# way (gain_per_second off): more time always bought points (a 300 s fence:
# +17.5 % on the 41 first boards, +151 s of waiting per game).
STOP_RULE = {"min_gain": 0.0, "min_points": 1, "gain_per_second": 0.0, "gain_decay": 1.0,
             "min_width": 150}


def stop_reason(passes, next_width, baseline=None, rule=None):
    """Why the pass of ``next_width`` should not start, or None to run it.

    ``passes``: dicts with width, seconds, complete and value, in order.
    ``baseline``: the value of a line already in hand (the carried line of a
    background replan); the first pass is then measured against it too.
    """
    rule = STOP_RULE if rule is None else rule
    done = [p for p in passes if p["complete"]]
    if not done:
        return None
    last = done[-1]
    if last["width"] < rule.get("min_width", 0):
        return None
    before = [p["value"] for p in done[:-1]]
    if baseline is not None:
        before.append(baseline)
    if not before:
        return None
    ref = max(before)
    gain = last["value"] - ref
    rel = gain / max(1.0, abs(ref))
    need = max(rule.get("min_points", 0), rule.get("min_gain", 0) * abs(ref))
    if gain < need:
        if rule.get("min_gain"):
            return f"dobitak {rel * 100:.1f}% < prag {rule.get('min_gain', 0) * 100:g}%"
        if rule.get("min_points") == 1:
            return f"sirina {last['width']} nije donela nista ({gain:+.0f})"
        return f"dobitak {gain:+.0f} < prag {rule.get('min_points')}"
    clock_seconds = rule.get("clock_seconds")
    if clock_seconds and last["seconds"] > 0 and last["value"] > 0:
        # The race: a wider pass costs turn clock the line could have played.
        # It runs only while the last widening gained more than that clock is
        # worth at this line's own rate (its points over the turn's seconds).
        cost = last["seconds"] * next_width / last["width"] * PASS_TIME_GROWTH
        worth = last["value"] / float(clock_seconds) * cost
        if gain < worth:
            return (f"sirina {next_width} (~{cost:.0f} s) kosta oko {worth:.0f} poena sata, "
                    f"prosla sirina donela {gain:+.0f}")
    per_second = rule.get("gain_per_second") or 0
    if per_second > 0 and last["seconds"] > 0:
        cost = last["seconds"] * next_width / last["width"] * PASS_TIME_GROWTH
        expected = rel * rule.get("gain_decay", 1.0)
        if expected / cost < per_second:
            return (f"sirina {next_width} (~{cost:.0f} s) za ~{expected * 100:.1f}% "
                    f"se ne isplati")
    return None


def _pass_info(state, line, width, seconds, complete, first=5):
    """What the GUI shows for one finished pass."""
    start = state.get("score") or 0
    targets = [t for t in state.get("solo_targets") or () if t > start]
    return {"width": width, "seconds": seconds, "complete": complete, "score": line.score,
            "value": line.value, "actions": len(line.actions),
            "boosters": sum(a.get("kind") == "booster" for a in line.actions),
            "target": targets[0] if targets else None,
            "reaches": bool(targets) and line.score >= targets[0],
            "first": [describe(a) for a in line.actions[:first]]}


def plan_anytime(state, seconds, widths=WIDTHS, start_width=0, finish_cut=True, max_steps=300,
                 stop_early=False, rule=None, baseline=None, on_pass=None, clock=None, first_cost=None):
    """Full-depth plans of growing width until the gain or the time runs out.

    The narrow first pass reaches the last move quickly, so the answer always
    covers the whole turn; a wider pass replaces it only if it scores at
    least as much. A pass cut by the deadline is finished at width 1
    (plan(finish_cut=True)) and compared like the others.

    ``rule``: the dynamic stop (STOP_RULE, stop_reason): no pass starts once
    the last one brought too little or the next does not pay for its time.
    ``seconds`` is then only the fence.

    ``baseline``: the value of the line the caller already holds (stop_reason).

    ``on_pass``: called with _pass_info of every finished pass (``best``: it
    is the line kept so far) and at the end with ``done`` True, the chosen
    width and the stop reason. Errors in it are ignored.

    ``start_width``: skip the narrower passes (a background replan whose
    carried line already comes from them). The first pass then runs against
    the deadline too, so a wide start cannot overrun it.

    ``max_steps``: the most actions a line may have (what the turn clock still
    allows); a line that reaches it with moves in hand ends there.

    ``stop_early``: do not start a pass that, by the time of the one before,
    cannot finish; the answer comes at once instead of after the deadline.
    For a search that holds the turn clock (the first plan): live 2026-11-15
    15:23-16:13 the cut width-25 pass took 59-84 s of each 150 s first plan
    and never gave the line.

    ``finish_cut=False``: a cut pass is dropped at once, as before (the short
    per-move check beside a carried line must not run over its time).

    ``clock``: {"left": seconds of the turn clock left (reserve taken off),
    "action_seconds": what one action takes to play}. Each pass gets only the
    actions the clock still allows after it (its time estimated from the pass
    before), and no pass starts once that would no longer fit the best line
    already found: the search may take as long as the turn can pay for.
    ``clock["busy"]``: seconds the bot plays anyway before this plan's board
    comes (a background replan runs while the actions ahead are played), so
    only the search time past them costs actions.

    ``first_cost``: the expected seconds of the first pass (the caller's
    measure from earlier passes of this width); without it the clock counts
    the first pass as free. Live 2026-11-18 08:40: a width-150 replan was
    given 43 actions, took 243 s and only 26 still fitted.

    stats: ``width`` of the pass the line comes from, ``full_width`` the
    widest pass that ran to the end uncut, ``passes`` (width, seconds, uncut),
    ``pass_info`` (_pass_info of each) and ``stop_reason``.
    """
    def tell(info):
        if on_pass is not None:
            try:
                on_pass(info)
            except Exception:
                pass

    started = time.monotonic()
    deadline = started + seconds
    widths = [w for w in widths if w >= start_width] or [widths[-1]]
    best = stats = full_width = None
    whole_lines = None
    simulated, passes, infos = 0, [], []
    reason = "sve sirine"
    for width in widths:
        began = time.monotonic()
        if passes and rule is not None:
            why = stop_reason(infos, width, baseline=baseline, rule=rule)
            if why:
                reason = why
                break
        cost = float(first_cost or 0.0)
        if passes:
            last_width, last_seconds, _ = passes[-1]
            cost = last_seconds * width / last_width * PASS_TIME_GROWTH
        if stop_early and passes and cost > deadline - began:
            reason = f"granica: sirina {width} (~{cost:.0f} s) ne stize"
            break
        steps = max_steps
        if clock is not None:
            room = clock["left"] - max((began - started) + cost, clock.get("busy", 0.0))
            steps = min(max_steps, int(room / clock["action_seconds"]))
            if passes and steps < max(1, len(best.actions)):
                reason = (f"sat: posle sirine {width} (~{cost:.0f} s) ne bi stalo "
                          f"{len(best.actions)} akcija plana")
                break
            steps = max(1, steps)
        pass_state = state
        if clock is not None and "time_left" in state:
            # A timed line (the race) loses the clock this search has taken.
            pass_state = dict(state, time_left=float(state["time_left"]) - (began - started) - cost)
        line, run = plan(pass_state, width=width, finish_cut=finish_cut, max_steps=steps,
                         deadline=None if best is None and not start_width else deadline)
        simulated += run["simulated"]
        took = round(time.monotonic() - began, 1)
        passes.append((width, took, run["complete"]))
        info = _pass_info(state, line, width, took, run["complete"])
        infos.append(info)
        if run["complete"]:
            full_width = width
            whole_lines = run.get("lines")
        if best is None or ((run["complete"] or finish_cut) and line.value >= best.value):
            best, stats = line, run
        tell(dict(info, best=best is line))
        if not run["complete"]:
            reason = "isteklo vreme (prolaz prekinut)"
            break
        if time.monotonic() > deadline:
            reason = "isteklo vreme"
            break
    # The widest whole pass's finished lines: a cut pass keeps one line.
    stats = dict(stats, simulated=simulated, full_width=full_width, passes=passes,
                 pass_info=infos, stop_reason=reason, lines=whole_lines or stats.get("lines") or [])
    tell({"done": True, "width": stats.get("width"), "score": best.score, "value": best.value,
          "actions": len(best.actions), "reason": reason,
          "seconds": round(time.monotonic() - started, 1),
          "first": [describe(a) for a in best.actions[:5]]})
    return best, stats


def describe_passes(passes):
    """'1: 1.4 s, 4: 6.2 s, 25: prekinut 128.0 s' for the log."""
    return ", ".join(f"{width}: {'' if whole else 'prekinut '}{seconds} s"
                     for width, seconds, whole in passes or ())


# Set in the background worker process (square_solo_live._background_pool's
# initializer): every finished pass goes to the GUI through it.
_PASS_QUEUE = None


def set_pass_queue(queue):
    global _PASS_QUEUE
    _PASS_QUEUE = queue


def background_plan(state, seconds, start_width=0, max_steps=300, baseline=None, rule=None, clock=None,
                    first_cost=None, max_width=None, stop_early=False):
    """plan_anytime in a worker process (square_solo_live background replan).

    Returns only what the caller needs to rebuild the line on its own state:
    the actions, the value and score, the width the line comes from, the
    widest uncut pass and the time of each pass. ``baseline``: the carried
    line's value; the dynamic stop measures the gain against it. ``rule``
    False: no dynamic stop (Woolly), None: STOP_RULE. ``clock``: as in
    plan_anytime, the match time left from this board. ``max_width``: no
    wider pass.
    ``stop_early``: no pass starts that would
    not finish inside ``seconds`` (answer 23 B: a cut pass is wasted work).
    """
    if sys.platform == "win32":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.GetCurrentProcess.restype = ctypes.c_void_p
            # Below normal: the GUI and the bot's own checks come first.
            kernel32.SetPriorityClass(ctypes.c_void_p(kernel32.GetCurrentProcess()), 0x4000)
        except Exception:
            pass
    queue = _PASS_QUEUE
    on_pass = None if queue is None else (lambda info: queue.put(dict(info, source="pozadinski plan")))
    widths = tuple(w for w in WIDTHS if max_width is None or w <= max_width)
    best, stats = plan_anytime(state, seconds, widths=widths, start_width=start_width, max_steps=max_steps,
                               rule=STOP_RULE if rule is None else (rule or None), baseline=baseline,
                               on_pass=on_pass, clock=clock, first_cost=first_cost, stop_early=stop_early)
    return {"actions": best.actions, "value": best.value, "score": best.score, "width": stats.get("width"),
            "full_width": stats.get("full_width"), "passes": stats.get("passes"),
            "stop_reason": stats.get("stop_reason")}


def describe(action):
    kind = action.get("kind", "swap")
    if kind == "booster":
        return "BOOSTER" if action.get("color") is None else f"BOOSTER boja {action['color']}"
    if kind == "remove_cross":
        return f"REMOVE CROSS red {action['cell'][0]} kol {action['cell'][1]}"
    (r, c), (y, x) = action["start"], action["target"]
    move = f"red {r} kol {c} -> red {y} kol {x}"
    if (r, c) == (y, x) and action.get("direction"):
        move = f"SPREJ red {r} kol {c} {action['direction']}"   # Foxy Roxy SE can
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
