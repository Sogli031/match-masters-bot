"""Compare the ported refill against two captures of one match: before and after one move.

Offline: reads saved packages only. Without --move every legal action is
tried, so a forgotten move is still found. A match on board, RNG counter and
spawnedColors is evidence for this transition, not certification of the mode.

Any mode: the mode comes from the captured rules (same lookup as Memory GUI).
Outside the last round the engine's adaptive prevention thresholds are not
ported, so every candidate from simulator_capture.threshold_hypotheses is
tried and the ones that reproduce the game are reported.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine_refill import EngineRefill, UnsupportedRefill
from simulator_capture import capture_mode, decode_dictionary, lab_move, load_capture, resolve_refill_overrides
from strategy_lab.simulation import legal_actions, step


def observed(capture):
    profile = capture["profile"]
    return {"board": [[int(v) for v in row] for row in capture["simulator_input"]["board"]],
            "special_board": [[int(v) for v in row] for row in capture["simulator_input"]["special_board"]],
            "rng_counter": profile["rng"]["<counter>k__BackingField"],
            "spawned_colors": decode_dictionary(profile["spawning"].get("spawnedColors")) or {},
            "score": next(p["model"]["score"] for p in profile["players"] if p.get("player_type") == 0),
            "moves": profile["state"]["moves"],
            "energy": next(p["model"]["energy"] for p in profile["players"] if p.get("player_type") == 0),
            "perks": {int(k): v for k, v in (decode_dictionary(next(
                p["model"] for p in profile["players"] if p.get("player_type") == 0).get("boardAbilities")) or {}).items()}}


def predicted(result):
    state = result["state"]
    return {"board": [[int(v) for v in row] for row in state["board"]],
            "special_board": [[int(v) for v in row] for row in state["special_board"]],
            "rng_counter": state["engine_refill"].rng.counter,
            "spawned_colors": dict(state["engine_refill"].spawned_colors),
            "score": state.get("score"),
            "moves": state["turn_state"].get("remaining_moves"),
            "energy": (state.get("booster_state") or {}).get("current"),
            "perks": state.get("perks")}


def differences(want, got):
    # spawnedColors only steers refills inside one action and the game clears
    # it when the next one starts; an empty read is that reset, not a miss.
    out = [f"{key}: igra={want[key]} simulator={got[key]}"
           for key in ("rng_counter", "spawned_colors", "score", "moves", "energy", "perks")
           if want[key] != got[key] and not (key == "spawned_colors" and not want[key])]
    for name in ("board", "special_board"):
        cells = [(r, c, want[name][r][c], got[name][r][c]) for r in range(len(want[name]))
                 for c in range(len(want[name][r])) if want[name][r][c] != got[name][r][c]]
        if cells:
            out.append(f"{name}: {len(cells)} polja (red, kolona, igra, simulator) {cells[:12]}")
    return out


@dataclass
class _ExtraDrawRefill(EngineRefill):
    """Diagnostic only: one unexplained Next() before RefillSlots call `before_call`."""
    before_call: int = -1
    calls: int = 0

    def clone(self):
        return type(self)(self.profile, self.rng.clone(), dict(self.spawned_colors), self.thresholds,
                          before_call=self.before_call)

    def fill(self, board, chain_combos=0):
        if self.calls == self.before_call:
            self.rng.next()
        self.calls += 1
        return super().fill(board, chain_combos)


def explain_extra_draw(before, action, want, refills, thresholds=None):
    """Refill indices before which one extra engine draw reproduces the game exactly."""
    found = []
    for call in range(len(refills) + 1):
        state = lab_move(before, thresholds=thresholds)
        base = state["engine_refill"]
        state["engine_refill"] = _ExtraDrawRefill(base.profile, base.rng, base.spawned_colors, base.thresholds,
                                                  before_call=call)
        result = step(state, action)
        if result["supported"] and not differences(want, predicted(result)):
            found.append(call)
    return found


def describe_capture(capture):
    """Mode and refill branch of one capture, read from its memory profile."""
    profile = capture["profile"]
    rules, state = profile["rules"], profile["state"]
    resolved = resolve_refill_overrides(profile)
    try:
        mode = capture_mode(profile).value
    except Exception as exc:  # memory_gui not importable here
        mode = f"? ({exc})"
    return {"rules_id": rules.get("id"), "title": rules.get("title"), "mode": mode,
            "pvp_mode": rules.get("pvpMode"), "players": len(profile.get("players") or []),
            "turn": state.get("<Turns>k__BackingField"), "turns_total": state.get("<TurnsTotal>k__BackingField"),
            "last_round": resolved.get("last_round"), "branch_resolved": bool(resolved.get("resolved")),
            "refill_branch": resolved.get("branch"),
            "reason": resolved.get("reason"),
            "hypotheses": resolved.get("threshold_hypotheses") or {}}


def _try_actions(state, actions, want):
    report = []
    for action in actions:
        result = step(state, action)
        if not result["supported"]:
            report.append({"action": action, "supported": False, "reason": result["reason"]})
            continue
        diff = differences(want, predicted(result))
        report.append({"action": action, "supported": True, "match": not diff, "differences": diff,
                       "refills": [len(t) for t in result["refills"]]})
    return report


def compare(before_dir, after_dir, move=None, *, hypothesis=None):
    """Report per action. Outside the resolved last-round branch every
    threshold hypothesis is tried; each entry then names its ``hypothesis``.
    ``hypothesis`` limits the run to one of them by name."""
    before, after = load_capture(before_dir), load_capture(after_dir)
    if before["profile"]["rng"]["_seed"] != after["profile"]["rng"]["_seed"]:
        raise ValueError("Snimci nisu iz iste partije (razlicit RNG seed)")
    info = describe_capture(before)
    if info["branch_resolved"]:
        candidates = {None: None}
    else:
        candidates = dict(info["hypotheses"])
        if hypothesis is not None:
            candidates = {hypothesis: candidates[hypothesis]}
        if not candidates:
            raise UnsupportedRefill(f"Grana dopune nije razresena ({info['reason']}) i nema hipoteza pragova")
    want = observed(after)
    report = []
    for name, thresholds in candidates.items():
        state = lab_move(before, thresholds=thresholds)
        if move is not None:
            actions = [move]
        else:
            from strategy_lab.planner import actions as planner_actions
            # Swipes plus every perk / booster use the planner could choose.
            actions = planner_actions(state)
        for entry in _try_actions(state, actions, want):
            entry["hypothesis"] = name
            entry["thresholds"] = thresholds
            report.append(entry)
    if not any(r.get("match") for r in report):
        # Rank by size of the difference; probe only the closest candidates.
        close = sorted((r for r in report if r["supported"]), key=lambda r: _distance(r))[:4]
        for r in close:
            r["extra_draw_before_refill"] = explain_extra_draw(before, r["action"], want, r["refills"],
                                                               r["thresholds"])
    return report


def _distance(entry):
    return sum(int(d.split(": ")[1].split(" ")[0]) if d.startswith(("board", "special")) else 1
               for d in entry["differences"])


def format_info(info):
    branch = ("eksplicitni pragovi (portovano)" if "explicit" in (info.get("refill_branch") or "")
              else "poslednja runda (portovano)" if info["branch_resolved"]
              else f"NIJE poslednja runda -> probam {len(info['hypotheses'])} hipoteza pragova")
    mode = "obican (bez posebne logike)" if info["mode"] == "None" else info["mode"]
    return (f"Mod: {info['title'] or info['rules_id']} [{info['rules_id']}] -> simulator {mode}, "
            f"pvpMode={info['pvp_mode']}, igraca={info['players']}, potez {info['turn']}/{info['turns_total']}\n"
            f"Dopuna: {branch}")


def parse_move(text):
    start, target = ([int(v) for v in part.split(",")] for part in text.split(":"))
    dr, dc = target[0] - start[0], target[1] - start[1]
    direction = {(-1, 0): "up", (1, 0): "down", (0, -1): "left", (0, 1): "right"}[(dr, dc)]
    return {"start": start, "target": target, "direction": direction}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    parser.add_argument("--move", type=parse_move, help="red,kolona:red,kolona (od 0, red 0 je gore)")
    parser.add_argument("--hypothesis", help="samo ova hipoteza pragova (van poslednje runde)")
    args = parser.parse_args()
    print(format_info(describe_capture(load_capture(args.before))))
    report = compare(args.before, args.after, args.move, hypothesis=args.hypothesis)
    matches = [r for r in report if r.get("match")]
    for r in report:
        a = r["action"]
        head = f"{a['start']} -> {a['target']}" + (f" [{r['hypothesis']}]" if r.get("hypothesis") else "")
        if not r["supported"]:
            print(f"{head}: nepodrzano ({r['reason']})")
        elif r["match"]:
            print(f"{head}: POKLAPA SE (dopune: {r['refills']})")
        elif args.move is not None or r.get("extra_draw_before_refill"):
            print(f"{head}: NE POKLAPA SE")
            for line in r["differences"]:
                print("  " + line)
            if r.get("extra_draw_before_refill"):
                print(f"  +1 RNG izvlacenje pre dopune {r['extra_draw_before_refill']} daje tacno poklapanje")
    print(f"Poklapanja: {len(matches)} od {len(report)} provera")
    return 0 if matches else 1


if __name__ == "__main__":
    raise SystemExit(main())
