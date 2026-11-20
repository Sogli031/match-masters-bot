"""Does pricing a move in hand (planner rank_move_value) help Solo refill plans?

    python tools/solo_move_value_check.py [--prices=0,200,400] OUT.txt RESEARCH_DIR...

Each sampled resting board is planned at width 25 to the end (max 60 actions)
with several move prices; the line is chosen by score as always, the price
only orders the beam. Progress (done/total, elapsed, ETA) goes to OUT.txt.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PRICES = (0, 50, 200)
WIDTH = 25
STEPS = 60
SECONDS = 150.0


def run(job):
    path, price = job
    from simulator_capture import capture_mode, lab_move
    from strategy_lab import planner, simulation
    from tools.analyze_research import load
    from tools.gentle import make_gentle

    make_gentle()
    _record, capture = load(path)
    simulation.PREFIX_MODES = set(simulation.PREFIX_MODES) | {capture_mode(capture["profile"]).value}
    lab = lab_move(capture)
    lab["perks"] = {}
    if price:
        lab["rank_move_value"] = price
    started = time.monotonic()
    best, stats = planner.plan(lab, width=WIDTH, max_steps=STEPS,
                               deadline=time.monotonic() + SECONDS, finish_cut=True)
    return path, price, (best.score or 0) - (lab.get("score") or 0), len(best.actions), time.monotonic() - started


def main(argv=None) -> int:
    from tools.gentle import gentle_pool

    global PRICES
    args = list(argv if argv is not None else sys.argv[1:])
    if args and args[0].startswith("--prices="):
        PRICES = tuple(int(p) for p in args.pop(0).split("=", 1)[1].split(","))
    out = Path(args[0])
    boards = []
    for folder in map(Path, args[1:]):
        frames = sorted(folder.glob("[0-9][0-9][0-9].json"))
        boards += frames[::max(1, len(frames) // 8)][:8]
    jobs = [(str(b), p) for b in boards for p in PRICES]
    results, started = {}, time.monotonic()
    with out.open("w", encoding="utf-8", buffering=1) as log, gentle_pool() as pool:
        for done, (path, price, gain, actions, seconds) in enumerate(pool.imap_unordered(run, jobs), 1):
            results[(path, price)] = gain
            elapsed = time.monotonic() - started
            eta = time.strftime("%H:%M", time.localtime(time.time() + elapsed / done * (len(jobs) - done)))
            log.write(f"{done}/{len(jobs)} {Path(path).parent.name}/{Path(path).name} cena {price}: "
                      f"+{gain} ({actions} akcija, {seconds:.0f} s) | proteklo {elapsed:.0f} s, kraj oko {eta}\n")
        totals = {p: sum(results[(str(b), p)] for b in boards) for p in PRICES}
        wins = {p: sum(results[(str(b), p)] > results[(str(b), 0)] for b in boards) for p in PRICES}
        losses = {p: sum(results[(str(b), p)] < results[(str(b), 0)] for b in boards) for p in PRICES}
        for p in PRICES:
            log.write(f"cena {p}: ukupno +{totals[p]}, bolje {wins[p]}, gore {losses[p]} od {len(boards)}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
