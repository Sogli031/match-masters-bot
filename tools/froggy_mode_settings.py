"""Froggy Fu: which bot settings pay in which mode (exact simulator).

    python tools/froggy_mode_settings.py [--width 10] [--workers N]

For every recorded Froggy Fu board (Debug/research, every mode and match
kind) where a setting would change the bot's action, the rest of the turn is
searched (strategy_lab.planner, width 10, turn clock) after the bot's recorded
action and after the setting's action; the difference is what the setting
gains there. Settings:

  booster_first      full meter (no lotus on the board): the booster now
                     instead of the bot's swipe (runtime.froggy_race_booster_first)
  remove_cross_first Remove Cross held and the meter not full: Remove Cross now
                     on the cell the bot's own perk ranking picks
                     (runtime.froggy_versus_remove_cross_applies)

Result: Debug/froggy_mode_settings/rows.jsonl and table.txt (per mode and
match kind: boards, sum, better/worse); progress with ETA in progress.txt.
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT = ROOT / "Debug" / "froggy_mode_settings"
FROGGY = 63
REMOVE_CROSS = 18      # engine BoardAbility type (tools.best_line_search.PERK_TYPES)
KIND = {0: "versus", 1: "solo", 2: "race"}


def froggy_records():
    for folder in sorted((ROOT / "Debug" / "research").iterdir()):
        files = sorted(folder.glob("[0-9][0-9][0-9].json")) if folder.is_dir() else []
        if len(files) < 2:
            continue
        try:
            state = json.loads(files[0].read_text(encoding="utf-8")).get("snapshot_state") or {}
        except Exception:
            continue
        me = next((p for p in state.get("players") or () if p.get("player_type") == 0), {})
        if me.get("special_ability_type") == FROGGY:
            yield from files[:-1]


def _remove_cross_cell(record, lab):
    """The cell the bot's own forced Remove Cross ranking picks."""
    import move_strategy as ms
    import runtime

    charge = lab.get("booster_state") or {}
    pvp = ((record.get("snapshot_state") or {}).get("rules") or {}).get("pvp_mode")
    context = ms.StrategyContext("versus_2" if pvp == 0 else "solo_6", solo_challenge=pvp == 1)
    action = runtime._froggy_remove_cross_action(
        lab["board"], lab["special_board"], (runtime.PERK_REMOVE_CROSS, runtime.PERK_NONE), None,
        ms.BoosterState(charge.get("current") or 0, charge.get("maximum") or 7, "memory"),
        ms.TurnState(lab["turn_state"].get("remaining_moves") or 1, "memory"), context)
    return None if action is None or action.target is None else list(action.target)


def work(item):
    path, width = item
    from strategy_lab import planner
    from strategy_lab.simulation import step
    from simulator_capture import capture_mode
    from tools.analyze_research import load
    from tools.best_line_search import start_state
    from tools.replay_one_to_one import recorded_action
    from tools.planner_vs_bot import LOTUS, _count
    from square_solo_live import _timed_after

    path = Path(path)
    row = {"session": path.parent.name, "record": path.stem}
    try:
        record, capture = load(path)
        bot, why = recorded_action(json.loads(path.with_name(f"{int(path.stem) + 1:03d}.json")
                                              .read_text(encoding="utf-8")))
        if bot is None:
            return dict(row, skip=why)
        pvp = ((record.get("snapshot_state") or {}).get("rules") or {}).get("pvp_mode")
        lab = start_state(record, capture)
        if pvp == 1:
            lab.pop("time_left", None)     # Solo Challenge: the move counter ends it
        if (lab["turn_state"].get("remaining_moves") or 0) <= 0 or lab.get("time_left", 1) <= 0:
            return dict(row, skip="kraj poteza")
        row.update(mode=capture_mode(capture["profile"]).value, kind=KIND.get(pvp, str(pvp)))
        charge = lab.get("booster_state") or {}
        full = bool(charge.get("maximum")) and (charge.get("current") or 0) >= charge["maximum"]
        alternatives = {}
        if full and bot.get("kind") != "booster" and _count(lab["special_board"], LOTUS) == 0:
            alternatives["booster_first"] = {"kind": "booster"}
        if not full and (lab.get("perks") or {}).get(REMOVE_CROSS) and bot.get("kind") != "remove_cross":
            cell = _remove_cross_cell(record, lab)
            if cell is not None:
                alternatives["remove_cross_first"] = {"kind": "remove_cross", "cell": cell}
        if not alternatives:
            return dict(row, skip="podesavanje ne menja potez")

        def line_after(action):
            result = step(lab, action)
            if not result.get("supported"):
                return None
            rest, _ = planner.plan(_timed_after(lab, action, result["state"]), width=width)
            return rest.score

        base = line_after(bot)
        if base is None:
            return dict(row, skip=f"bot potez nije podrzan: {bot}")
        for name, action in alternatives.items():
            value = line_after(action)
            if value is not None:
                row[name] = value - base
        return row
    except Exception as exc:
        return dict(row, skip=f"greska: {type(exc).__name__}: {exc}")


def table(rows):
    groups = collections.defaultdict(list)
    for row in rows:
        for name in ("booster_first", "remove_cross_first"):
            if name in row:
                groups[(name, row["kind"], row["mode"])].append(row[name])
    lines = [f"{'podesavanje':20s} {'vrsta':7s} {'mod':32s} {'tabli':>5s} {'zbir':>7s} {'bolje':>5s} {'gore':>5s}  preporuka"]
    for (name, kind, mode), diffs in sorted(groups.items()):
        better, worse = sum(d > 0 for d in diffs), sum(d < 0 for d in diffs)
        verdict = ("UKLJUCI" if sum(diffs) > 0 and better > worse else
                   "ISKLJUCI" if sum(diffs) < 0 and worse > better else "nejasno")
        if len(diffs) < 5:
            verdict += " (malo tabli)"
        lines.append(f"{name:20s} {kind:7s} {mode:32s} {len(diffs):5d} {sum(diffs):+7d} {better:5d} {worse:5d}  {verdict}")
    return "\n".join(lines)


def main(argv=None):
    from tools.gentle import gentle_pool

    parser = argparse.ArgumentParser()
    parser.add_argument("--width", type=int, default=10)
    parser.add_argument("--workers", type=int, default=None)
    args = parser.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    rows_path, progress = OUT / "rows.jsonl", OUT / "progress.txt"
    done_keys = set()
    if rows_path.exists():
        for line in rows_path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            done_keys.add((row["session"], row["record"]))
    items = [(str(f), args.width) for f in froggy_records()]
    total = len(items)
    items = [i for i in items if (Path(i[0]).parent.name, Path(i[0]).stem) not in done_keys]
    before, started = total - len(items), time.monotonic()
    with rows_path.open("a", encoding="utf-8") as out, gentle_pool(args.workers) as pool:
        for new, row in enumerate(pool.imap_unordered(work, items), 1):
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
            out.flush()
            done, elapsed = before + new, time.monotonic() - started
            eta = elapsed / new * (total - done)
            progress.write_text(f"{done}/{total} ({done * 100 // total}%), proteklo {elapsed:.0f} s, "
                                f"ostalo ~{eta:.0f} s, kraj oko "
                                f"{time.strftime('%H:%M', time.localtime(time.time() + eta))}\n", encoding="utf-8")
    rows = [json.loads(l) for l in rows_path.read_text(encoding="utf-8").splitlines()]
    (OUT / "table.txt").write_text(table(rows), encoding="utf-8")
    print(table(rows))


if __name__ == "__main__":
    main()
