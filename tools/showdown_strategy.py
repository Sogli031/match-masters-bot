"""Play recorded Showdown starts to the end in the simulator with the live race policy.

    python tools/showdown_strategy.py [FOLDER ...] [--out Debug/showdown_strategy]

Every FOLDER (default: every one-player race in Debug/research) starts from its
first record (tools/best_line_search.start_state: score, booster, perks, turn
clock). The race is played as square_solo_live plays it: a first plan on the
clock (RACE_TURN_START_SECONDS, race stop rule), the line carried, a background
replan RACE_BG_AHEAD actions ahead (here run in turn, its seconds not taken off
the game clock, as live), taken when better. The game clock pays the first
plans' seconds and RACE_ACTION_SECONDS per action. Each VARIANT changes one
setting; the final score per race goes to OUT/rezultat.txt, progress
(done/total, elapsed, ETA) to OUT/napredak.txt.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import square_solo_live as live  # noqa: E402
from strategy_lab import planner  # noqa: E402

BASE = {"start_seconds": live.RACE_TURN_START_SECONDS, "bg_ahead": live.RACE_BG_AHEAD,
        "bg_share": live.RACE_BG_SHARE, "bg_max_width": live.BG_MAX_WIDTH,
        "min_width": live.RACE_MIN_WIDTH, "rank_special_value": planner.RANK_SPECIAL_VALUE,
        # live race: quick plan, booster_auto only (square_solo_live plan(): booster_hold is set on the Charles path)
        "booster_hold": False}

VARIANTS = {
    "sada": {},
    "start4": {"start_seconds": 4.0},
    "start12": {"start_seconds": 12.0},
    "sv5": {"rank_special_value": 5},
    "sv10": {"rank_special_value": 10},
    "bg2": {"bg_ahead": 2},
    "bg5": {"bg_ahead": 5},
    "bgshare1": {"bg_share": 1.0},
    "bgw60": {"bg_max_width": 60},
    "cuvanje": {"booster_hold": True},
    "sv0": {"rank_special_value": 0},
    "sv3": {"rank_special_value": 3},
    "sv8": {"rank_special_value": 8},
    "sv5_cuvanje": {"rank_special_value": 5, "booster_hold": True},
    "bgshare085": {"bg_share": 0.85},
    "sv5_bgshare1": {"rank_special_value": 5, "bg_share": 1.0},
}


def race_folders():
    out = []
    for folder in sorted((ROOT / "Debug" / "research").iterdir()):
        first = folder / "000.json"
        if not first.exists() or len(list(folder.glob("[0-9][0-9][0-9].json"))) < 2:
            continue
        snap = json.loads(first.read_text(encoding="utf-8")).get("snapshot_state") or {}
        if len(snap.get("players") or ()) == 1 and 0 < (snap.get("remaining_time") or 0) < 200:
            out.append(folder)
    return out


def play(folder, settings, index=0):
    """Final simulator score of the race from FOLDER's record ``index``."""
    from strategy_lab import planner
    from strategy_lab.simulation import step
    from tools.analyze_research import load
    from tools.best_line_search import start_state

    first, capture = load(sorted(folder.glob("[0-9][0-9][0-9].json"))[index])
    state = start_state(first, capture)
    state["action_seconds"] = dict(live.RACE_ACTION_SECONDS)
    state["booster_hold"] = settings["booster_hold"]
    state["rank_special_value"] = settings["rank_special_value"]
    widths = tuple(w for w in planner.WIDTHS if w <= settings["bg_max_width"])
    carry, bg, bg_width = [], None, 0
    plans = narrow = played = 0
    while state.get("time_left", 0) > 0:
        if not carry:
            began = time.monotonic()
            rule = {"min_width": 0, "min_points": 1, "clock_seconds": state["time_left"]}
            best, stats = planner.plan_anytime(
                dict(state), settings["start_seconds"], finish_cut=True, stop_early=True, rule=rule,
                clock={"left": state["time_left"], "action_seconds": live.RACE_ACTION_SECONDS["swap"]})
            state = dict(state, time_left=state["time_left"] - (time.monotonic() - began))
            plans += 1
            bg_width = stats.get("full_width") or 0
            if not best.actions:
                break
            carry = list(best.actions)
            if (stats.get("width") or 0) < settings["min_width"]:
                narrow += 1     # live: the bot's own pick; here the narrow line's first action
                carry = carry[:1]
            bg = None
        if bg is not None and bg[0] == played:
            line = live._replay_line(state, bg[1]) if bg[1] else None
            current = live._replay_line(state, carry)
            if line is not None and current is not None and line.value > current.value:
                carry = list(bg[1])
            bg = None
        action = carry.pop(0)
        if planner._action_seconds(state, action) > state["time_left"]:
            break
        result = step(state, action)
        if not result.get("supported"):
            carry = []
            continue
        state = live._timed_after(state, action, result["state"])
        played += 1
        ahead = settings["bg_ahead"]
        if bg is None and len(carry) > ahead:
            future, ok = state, True
            for a in carry[:ahead]:
                r = step(future, a)
                if not r.get("supported"):
                    ok = False
                    break
                future = live._timed_after(future, a, r["state"])
            if ok:
                arrives = ahead * live.RACE_ACTION_SECONDS["swap"]
                began = time.monotonic()
                found, bstats = planner.plan_anytime(dict(future), arrives * settings["bg_share"], widths=widths, start_width=bg_width,
                                                     rule=planner.STOP_RULE)
                if bstats.get("full_width"):
                    bg_width = bstats["full_width"]
                # live: a replan not done when its board comes is dropped (_race_take_background)
                late = time.monotonic() - began > arrives
                bg = (played + ahead, [] if late else list(found.actions))
    return {"score": state.get("score") or 0, "actions": played, "plans": plans, "narrow": narrow}


def _work(item):
    name, folder, index = item
    started = time.monotonic()
    try:
        out = play(Path(folder), dict(BASE, **VARIANTS[name]), index)
    except Exception as exc:  # one race must not stop the sweep
        out = {"score": None, "error": repr(exc)}
    return name, f"{Path(folder).name}#{index:03d}", dict(out, seconds=round(time.monotonic() - started))


def main(argv=None):
    from tools.gentle import gentle_pool

    parser = argparse.ArgumentParser()
    parser.add_argument("folders", nargs="*", type=Path)
    parser.add_argument("--out", type=Path, default=ROOT / "Debug" / "showdown_strategy")
    parser.add_argument("--variants", default=",".join(VARIANTS))
    parser.add_argument("--repeat", type=int, default=2, help="runs per race (the clock makes them differ)")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--every", type=int, default=0,
                        help="also start from every N-th record of each race (more boards, shorter races)")
    args = parser.parse_args(argv)
    folders = args.folders or race_folders()
    names = args.variants.split(",")
    starts = []
    for f in folders:
        count = len(list(f.glob("[0-9][0-9][0-9].json")))
        starts += [(str(f), i) for i in (range(0, count - 1, args.every) if args.every else (0,))]
    items = [(n, f, i) for _ in range(args.repeat) for n in names for f, i in starts]
    args.out.mkdir(parents=True, exist_ok=True)
    progress, results = args.out / "napredak.txt", {}
    started = time.time()
    with gentle_pool(args.workers) as pool:
        for done, (name, race, out) in enumerate(pool.imap_unordered(_work, items), 1):
            results.setdefault(name, {}).setdefault(race, []).append(out)
            elapsed = time.time() - started
            eta = elapsed / done * (len(items) - done)
            progress.write_text(f"{done}/{len(items)} ({done * 100 // len(items)}%), proteklo {elapsed:.0f} s, "
                                f"kraj oko {time.strftime('%H:%M', time.localtime(time.time() + eta))}\n",
                                encoding="utf-8")
    (args.out / "rezultat.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
    races = sorted({race for row in results.values() for race in row})
    base = results.get(names[0], {})

    def mean(runs):
        scores = [r["score"] for r in runs if r.get("score") is not None]
        return sum(scores) / len(scores) if scores else 0.0

    lines = ["varijanta     " + "  ".join(f"{r[9:15] + r[-3:]:>9s}" for r in races) + "      zbir  bolje/gore"]
    for name in names:
        row = results.get(name, {})
        means = [mean(row.get(r, [])) for r in races]
        better = sum(m > mean(base.get(r, [])) for m, r in zip(means, races))
        worse = sum(m < mean(base.get(r, [])) for m, r in zip(means, races))
        lines.append(f"{name:12s}  " + "  ".join(f"{m:9.0f}" for m in means) + f" {sum(means):9.0f}  {better}/{worse}")
    (args.out / "rezultat.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
