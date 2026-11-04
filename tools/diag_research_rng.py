"""Dijagnoza RNG potrosnje za research sesije.

Za svaki par snimaka proba sve legalne poteze kroz simulator za svaku
hipotezu pragova dopune (refillLogicOverride / poslednja runda 100 / -1 ...),
pa prijavljuje:
  - TACNO: tabla + specijali + RNG brojac se poklapaju bez ikakvog offset-a
  - NEPUNO k=...: potez se poklapa kad se pre poteza potrosi k dodatnih izvlacenja
  - najblizu akciju po trosku izvlacenja (koliko sim trosi za najblizi potez)

    python tools/diag_research_rng.py [Debug/research/FOLDER] [--pairs 000,013]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from simulator_capture import lab_move, resolve_refill_overrides, threshold_hypotheses
from strategy_lab import planner
from strategy_lab.simulation import step
from tools.analyze_research import booster_used, load, observed


def grid(board):
    return [[int(v) for v in row] for row in board]


def cells_diff(a, b):
    return [(r, c, a[r][c], b[r][c])
            for r in range(len(a)) for c in range(len(a[0])) if a[r][c] != b[r][c]]


def try_pair(cap_a, want, pre, thresholds):
    lab = lab_move(cap_a, thresholds=thresholds)
    lab["perks"] = {22: 1, 3: 1}   # Energy Boost i Teleport: po jedna upotreba
    total = want["rng"] - pre["rng"]
    hits, costs = [], []
    best = None
    for action in planner.actions(lab):
        result = step(lab, action)
        if not result.get("supported"):
            continue
        after = result["state"]
        draw = after["engine_refill"].rng.counter - pre["rng"]
        costs.append((action, total - draw))
        got = grid(after["board"])
        got_spec = grid(after["special_board"])
        rng_got = after["engine_refill"].rng.counter
        if (got == want["board"] and got_spec == want["special_board"] and rng_got == want["rng"]):
            hits.append({"action": action, "draw": draw, "refills": [len(t) for t in result["refills"]]})
            continue
        distance = len(cells_diff(want["board"], got)) + sum(
            want["special_board"][r][c] != got_spec[r][c]
            for r in range(len(got)) for c in range(len(got[0]))) + (rng_got != want["rng"])
        if best is None or distance < best["distance"]:
            best = {"distance": distance, "action": action, "draw": draw, "k": total - draw,
                    "rng": (want["rng"], rng_got), "refills": [len(t) for t in result["refills"]],
                    "cells": len(cells_diff(want["board"], got))}
    return hits, best, costs


def main(argv=None):
    argp = argparse.ArgumentParser()
    argp.add_argument("folder", nargs="?", type=Path)
    argp.add_argument("--pairs", type=str, default=None, help="npr. 000,013 (od kog snimka)")
    argp.add_argument("--top", type=int, default=3, help="koliko akcija po trosku da prikaze")
    args = argp.parse_args(argv)
    folder = args.folder
    if folder is None:
        sessions = sorted(p for p in (ROOT / "Debug/research").glob("*") if p.is_dir())
        if not sessions:
            print("Nema sesija")
            return 1
        folder = sessions[-1]
    files = sorted(folder.glob("[0-9][0-9][0-9].json"))
    only = {p.strip() for p in args.pairs.split(",")} if args.pairs else None
    for a, b in zip(files, files[1:]):
        if only is not None and a.stem not in only:
            continue
        rec_a, cap_a = load(a)
        rec_b, _ = load(b)
        pre, want = observed(rec_a), observed(rec_b)
        total = want["rng"] - pre["rng"]
        if rec_a["profile"]["rng"].get("_seed") != rec_b["profile"]["rng"].get("_seed"):
            print(f"{a.stem}->{b.stem}: nova partija")
            continue
        if booster_used(rec_a, rec_b):
            print(f"{a.stem}->{b.stem}: booster skip (delta {total})")
            continue
        resolved = resolve_refill_overrides(cap_a["profile"])
        hypotheses = ({None: None} if resolved.get("resolved")
                      else dict(resolved.get("threshold_hypotheses") or {}))
        for name, thresholds in threshold_hypotheses(cap_a["profile"]).items():
            hypotheses.setdefault(name, thresholds)
        for name, thresholds in hypotheses.items():
            hits, best, costs = try_pair(cap_a, want, pre, thresholds)
            if hits:
                for h in hits[:3]:
                    print(f"{a.stem}->{b.stem} [{name}]: TACNO {planner.describe(h['action'])} "
                          f"igra delta={total}, sim trosi={h['draw']}, dopune {h['refills']}")
                continue
            if best:
                label = planner.describe(best["action"])
                print(f"{a.stem}->{b.stem} [{name}]: najblize {label} trosi {best['draw']} "
                      f"(igra {total}, razlika {best['k']:+d}), razl. polja {best['distance']}, dopune {best['refills']}")
            else:
                print(f"{a.stem}->{b.stem} [{name}]: nista podrzano (igra delta {total})")
        # uvek prikazi najblize akcije po trosku (prvom reSuccessu)
        _, _, costs = try_pair(cap_a, want, pre, None)
        close = sorted(costs, key=lambda x: abs(x[1]))[:args.top]
        for action, k in close:
            print(f"    po trosku: k={k:+d}  {planner.describe(action)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
