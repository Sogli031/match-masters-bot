"""Per decision: what the exact planner would play against what the bot played.

    python tools/planner_vs_bot.py [--pvp 2] [--booster 63] [--width 10]

For every recorded board of the chosen research sessions (Debug/research,
pvp mode and booster from the first record) the planner searches the rest of
the turn twice on the turn clock: from the board itself (its own first
action) and from the board after the bot's recorded action. ``regret`` is the
points the bot's choice lost to the planner's at that width. Each first
action carries what it did in the exact simulator: points, charge, extra
move, lotuses taken, specials made.

Result: Debug/planner_vs_bot/results.jsonl, progress with ETA in
Debug/planner_vs_bot/progress.txt (CLAUDE.md: "dokle je").
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

OUT = ROOT / "Debug" / "planner_vs_bot"
LOTUS = 20     # ms.SPECIAL_FROGGY_LOTUS on the special board


def sessions(pvp, booster):
    out = []
    for folder in sorted((ROOT / "Debug" / "research").iterdir()):
        files = sorted(folder.glob("[0-9][0-9][0-9].json")) if folder.is_dir() else []
        if len(files) < 2:
            continue
        try:
            first = json.loads(files[0].read_text(encoding="utf-8"))
        except Exception:
            continue
        state = first.get("snapshot_state") or {}
        me = next((p for p in state.get("players") or () if p.get("player_type") == 0), {})
        if (state.get("rules") or {}).get("pvp_mode") == pvp and me.get("special_ability_type") == booster:
            out.append(files)
    return out


def _count(grid, value):
    return sum(int(v) == value for row in grid for v in row)


def features(lab, action):
    """What one action did in the exact simulator, or None when unsupported."""
    from strategy_lab.simulation import step

    result = step(lab, action)
    if not result.get("supported"):
        return None, None
    after = result["state"]
    before_charge = (lab.get("booster_state") or {}).get("current") or 0
    after_charge = (after.get("booster_state") or {}).get("current") or 0
    moves_before = lab["turn_state"].get("remaining_moves") or 0
    moves_after = after["turn_state"].get("remaining_moves") or 0
    specials_before = sum(int(v) != 0 for row in lab["special_board"] for v in row)
    specials_after = sum(int(v) != 0 for row in after["special_board"] for v in row)
    return {
        "kind": action.get("kind", "swap"),
        "points": round(result.get("score_gain") or 0),
        "charge": after_charge - before_charge,
        "extra": moves_after >= moves_before and action.get("kind", "swap") == "swap",
        "lotus_taken": _count(lab["special_board"], LOTUS) - _count(after["special_board"], LOTUS),
        "specials_delta": specials_after - specials_before,
    }, after


def work(item):
    path, width = item
    from strategy_lab import planner
    from simulator_capture import capture_mode  # noqa: F401  (start_state needs it loaded)
    from tools.analyze_research import load
    from tools.best_line_search import start_state
    from tools.replay_one_to_one import recorded_action
    from square_solo_live import _timed_after

    path = Path(path)
    nxt = path.with_name(f"{int(path.stem) + 1:03d}.json")
    row = {"session": path.parent.name, "record": path.stem}
    try:
        record, capture = load(path)
        bot, why = recorded_action(json.loads(nxt.read_text(encoding="utf-8")))
        if bot is None:
            return dict(row, skip=why)
        lab = start_state(record, capture)
        if (lab.get("time_left") or 0) <= 0 or (lab["turn_state"].get("remaining_moves") or 0) <= 0:
            return dict(row, skip="kraj poteza")
        charge = lab.get("booster_state") or {}
        row.update(time_left=round(lab["time_left"], 1), moves=lab["turn_state"].get("remaining_moves"),
                   score=lab.get("score"), meter=[charge.get("current"), charge.get("maximum")],
                   perks=lab.get("perks"), lotuses=_count(lab["special_board"], LOTUS))
        bot_f, after = features(lab, bot)
        if bot_f is None:
            return dict(row, skip=f"bot potez nije podrzan: {bot}")
        best, _ = planner.plan(lab, width=width)
        if not best.actions:
            return dict(row, skip="planer nema poteza")
        rest, _ = planner.plan(_timed_after(lab, bot, after), width=width)
        plan_f, _ = features(lab, best.actions[0])
        row.update(bot=dict(bot_f, action=planner.describe(bot), line=rest.score),
                   plan=dict(plan_f, action=planner.describe(best.actions[0]), line=best.score),
                   same=planner.describe(bot) == planner.describe(best.actions[0]),
                   regret=best.score - rest.score)
        return row
    except Exception as exc:     # one bad record must not stop the run
        return dict(row, skip=f"greska: {type(exc).__name__}: {exc}")


def main(argv=None):
    from tools.gentle import gentle_pool

    parser = argparse.ArgumentParser()
    parser.add_argument("--pvp", type=int, default=2)
    parser.add_argument("--booster", type=int, default=63)
    parser.add_argument("--width", type=int, default=10)
    parser.add_argument("--name", default=None)
    parser.add_argument("--workers", type=int, default=None, help="broj jezgara (dok se igra: 2)")
    args = parser.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    name = args.name or f"pvp{args.pvp}_b{args.booster}_w{args.width}"
    results, progress = OUT / f"{name}.jsonl", OUT / f"{name}.progress.txt"
    items = [(str(f), args.width) for files in sessions(args.pvp, args.booster) for f in files[:-1]]
    # Resume: the boards already in the result file are not searched again.
    finished = set()
    if results.exists():
        for line in results.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            finished.add((row["session"], row["record"]))
    total = len(items)
    items = [i for i in items if (Path(i[0]).parent.name, Path(i[0]).stem) not in finished]
    started, before = time.monotonic(), total - len(items)
    with results.open("a", encoding="utf-8") as out, gentle_pool(args.workers) as pool:
        for new, row in enumerate(pool.imap_unordered(work, items), 1):
            done = before + new
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
            out.flush()
            elapsed = time.monotonic() - started
            eta = elapsed / new * (total - done)
            finish = time.strftime("%H:%M", time.localtime(time.time() + eta))
            progress.write_text(f"{done}/{total} ({done * 100 // total}%), proteklo {elapsed:.0f} s, "
                                f"ostalo ~{eta:.0f} s, kraj oko {finish}\n", encoding="utf-8")
    print(f"{total} tabli -> {results}")


if __name__ == "__main__":
    main()
