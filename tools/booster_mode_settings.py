"""Which bot settings pay for each exact-plan booster, per mode and match kind.

    python tools/booster_mode_settings.py --booster 63 [--kinds versus,race] [--width 10]
                                          [--workers N]

The same method tools/froggy_mode_settings.py used for Froggy Fu, for every
booster square_solo_live.EXACT_PLAN_BOOSTERS supports. For every recorded
board of that booster (Debug/research, every mode and match kind) where a
setting would change the bot's action, the rest of the turn is searched
(strategy_lab.planner, width 10, turn clock) after the bot's recorded action
and after the setting's action; the difference is what the setting gains on
that board.

Settings measured:

  booster_first         full meter: the booster now instead of the bot's swipe
                        (runtime.booster_first_applies)
  remove_cross_first    Remove Cross held and the meter not full: Remove Cross
                        now on the cell the bot's own forced perk ranking picks
                        (runtime.booster_remove_cross_first_applies)
  energy_boost_first    Energy Boost held and the meter not full: Energy Boost
                        now, its follow-up swipe the one the bot played
                        (runtime.booster_energy_boost_first_applies)
  teleport_first        Teleport held: Teleport now on the pair the bot's own
                        forced perk ranking picks
                        (runtime.booster_teleport_first_applies)
  booster_color         Woolly Workout fired: the colour the simulator scores
                        best instead of the one the bot tapped
                        (runtime.booster_color_setting)

Solo Challenge drops the turn clock (time_left): there the move counter ends
the match. `--kinds` picks the match kinds to measure (the player's 2026-11-20
call: Versus and the timed races, Showdown / Party / Rumble; solo is not
measured). A board the simulator cannot play (a Froggy activation over a lotus,
an unported mode) is skipped and counted, never guessed.

Result, per booster: Debug/booster_mode_settings/<id>_<name>/rows.jsonl,
table.txt (per setting, match kind and mode: boards, sum, better/worse and the
recommendation) and progress.txt with the ETA (CLAUDE.md: "dokle je").
--entries prints the runtime.BOOSTER_MODE_SETTINGS entries this run measured.
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

OUT = ROOT / "Debug" / "booster_mode_settings"
BOOSTERS = {54: "checkmate_charles", 35: "woolly_workout", 52: "foxy_roxy_se",
            63: "froggy_fu", 44: "brocco_boogie", 61: "sweep_it_se"}
KIND = {0: "versus", 1: "solo", 2: "race"}
LOTUS = 20                       # ms.SPECIAL_FROGGY_LOTUS on the special board
# runtime perk key -> engine BoardAbility type (tools.best_line_search.PERK_TYPES)
ENGINE_PERK = {"energy_boost": 22, "teleport": 3, "remove_cross": 18}
PERK_SETTINGS = (("remove_cross", "remove_cross_first"),
                 ("energy_boost", "energy_boost_first"),
                 ("teleport", "teleport_first"))
SETTINGS = ("booster_first", "remove_cross_first", "energy_boost_first", "teleport_first",
            "booster_color")
MIN_BOARDS = 5                   # below this a verdict is not drawn


def booster_records(booster, kinds=None):
    """The boards of `booster`: every record whose next one carries the action."""
    for folder in sorted((ROOT / "Debug" / "research").iterdir()):
        files = sorted(folder.glob("[0-9][0-9][0-9].json")) if folder.is_dir() else []
        if len(files) < 2:
            continue
        try:
            state = json.loads(files[0].read_text(encoding="utf-8")).get("snapshot_state") or {}
        except Exception:
            continue
        me = next((p for p in state.get("players") or () if p.get("player_type") == 0), {})
        if me.get("special_ability_type") != booster:
            continue
        kind = KIND.get((state.get("rules") or {}).get("pvp_mode"))
        if kinds and kind not in kinds:
            continue
        yield from files[:-1]


def _count(grid, value):
    return sum(int(v) == value for row in grid for v in row)


def _strategy_context(record):
    import move_strategy as ms

    pvp = ((record.get("snapshot_state") or {}).get("rules") or {}).get("pvp_mode")
    return ms.StrategyContext("versus_2" if pvp == 0 else "solo_6", solo_challenge=pvp == 1)


def _perk_action(record, lab, perk_key, bot):
    """The action of a held perk, taken from the bot's own forced perk ranking.

    Remove Cross and Teleport come straight out of
    runtime._froggy_checkerboard_action (perk forced, force_use), the same
    ranking the bot uses when it throws one by hand. Energy Boost's ranking
    needs the bot's ranked move as its baseline, which only the live ranking
    has: offline its follow-up swipe is the one the bot actually played.
    """
    import move_strategy as ms
    import runtime

    charge = lab.get("booster_state") or {}
    turn = lab.get("turn_state") or {}
    if perk_key == "energy_boost":
        if bot.get("kind") != "swap" or not bot.get("start"):
            return None
        return {"kind": "energy_boost", "start": list(bot["start"]), "target": list(bot["target"]),
                "direction": bot["direction"]}
    action = runtime._froggy_checkerboard_action(
        lab["board"], lab["special_board"], (perk_key, runtime.PERK_NONE), None,
        ms.BoosterState(charge.get("current") or 0, charge.get("maximum") or 7, "memory"),
        ms.TurnState(turn.get("remaining_moves") or 1, "memory"), _strategy_context(record),
        perk=perk_key)
    if action is None:
        return None
    if perk_key == "remove_cross":
        if action.target is None:
            return None
        return {"kind": "remove_cross", "cell": list(action.target)}
    if perk_key == "teleport":
        cells = action.target or ()
        if len(cells) != 2 or tuple(cells[0]) == tuple(cells[1]):
            return None
        start, target = list(cells[0]), list(cells[1])
        return {"kind": "teleport", "start": start, "target": target,
                "direction": _direction(start, target)}
    return None


def _direction(start, target):
    dr, dc = target[0] - start[0], target[1] - start[1]
    return {(0, 1): "right", (0, -1): "left", (1, 0): "down", (-1, 0): "up"}.get((dr, dc), "right")


def work(item):
    path, width, booster = item
    from strategy_lab import planner
    from strategy_lab.simulation import step
    from simulator_capture import capture_mode
    from tools.analyze_research import load
    from tools.best_line_search import start_state
    from tools.replay_one_to_one import recorded_action
    from square_solo_live import _timed_after

    path = Path(path)
    row = {"session": path.parent.name, "record": path.stem}
    try:
        record, capture = load(path)
        bot, why = recorded_action(json.loads(
            path.with_name(f"{int(path.stem) + 1:03d}.json").read_text(encoding="utf-8")))
        if bot is None:
            return dict(row, skip=why)
        pvp = ((record.get("snapshot_state") or {}).get("rules") or {}).get("pvp_mode")
        lab = start_state(record, capture)
        lab.setdefault("booster_type", booster)
        if pvp == 1:
            lab.pop("time_left", None)     # Solo Challenge: the move counter ends it
        if (lab["turn_state"].get("remaining_moves") or 0) <= 0 or lab.get("time_left", 1) <= 0:
            return dict(row, skip="kraj poteza")
        mode = capture_mode(capture["profile"])
        charge = lab.get("booster_state") or {}
        full = bool(charge.get("maximum")) and (charge.get("current") or 0) >= charge["maximum"]
        row.update(mode=mode.name, mode_label=mode.value or "", kind=KIND.get(pvp, str(pvp)),
                   moves=lab["turn_state"].get("remaining_moves"),
                   time_left=None if "time_left" not in lab else round(lab["time_left"], 1),
                   meter=[charge.get("current"), charge.get("maximum")],
                   perks=sorted((k for k, n in (lab.get("perks") or {}).items() if n > 0)))
        alternatives = collections.defaultdict(list)
        if full and bot.get("kind") != "booster":
            if booster == 63 and _count(lab["special_board"], LOTUS):
                row["skipped_booster"] = "lotus (simulator ne pali preko lotusa)"
            else:
                alternatives["booster_first"] = planner.booster_actions(lab)
        if not full:
            for perk_key, setting in PERK_SETTINGS:
                if not (lab.get("perks") or {}).get(ENGINE_PERK[perk_key]) or bot.get("kind") == perk_key:
                    continue
                action = _perk_action(record, lab, perk_key, bot)
                if action is not None:
                    alternatives[setting] = [action]
        if booster == 35 and bot.get("kind") == "booster" and (lab.get("turn_state") or {}).get("remaining_moves"):
            others = [a for a in planner.booster_actions(lab) if a.get("color") != bot.get("color")]
            if others:
                alternatives["booster_color"] = others
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
        for name, actions in alternatives.items():
            values = [v for v in (line_after(a) for a in actions) if v is not None]
            if values:
                row[name] = max(values) - base
            elif name == "booster_first":
                row["skipped_booster"] = "booster se ne moze aktivirati na ovoj tabli"
        return row
    except Exception as exc:
        return dict(row, skip=f"greska: {type(exc).__name__}: {exc}")


def verdict(diffs):
    """ON / OFF / unclear, by the pre-agreed rule (sum, better/worse, boards)."""
    better, worse = sum(d > 0 for d in diffs), sum(d < 0 for d in diffs)
    if len(diffs) < MIN_BOARDS:
        return "nejasno"
    if sum(diffs) > 0 and better > worse:
        return "UKLJUCI"
    if sum(diffs) < 0 and worse > better:
        return "ISKLJUCI"
    return "nejasno"


def groups(rows):
    out = collections.defaultdict(list)
    for row in rows:
        for name in SETTINGS:
            if name in row:
                out[(name, row["kind"], row["mode"])].append(row[name])
    return out


def table(rows, booster):
    grouped = groups(rows)
    lines = [f"{BOOSTERS[booster]} ({booster}) - podesavanja po vrsti i modu",
             f"{'podesavanje':20s} {'vrsta':7s} {'mod':26s} {'tabli':>5s} {'zbir':>7s} {'bolje':>5s} "
             f"{'gore':>5s}  preporuka"]
    for (name, kind, mode), diffs in sorted(grouped.items()):
        better, worse = sum(d > 0 for d in diffs), sum(d < 0 for d in diffs)
        mark = "" if len(diffs) >= MIN_BOARDS else " (malo tabli)"
        lines.append(f"{name:20s} {kind:7s} {mode:26s} {len(diffs):5d} {sum(diffs):+7d} {better:5d} "
                     f"{worse:5d}  {verdict(diffs)}{mark}")
    skips = collections.Counter(row.get("skipped_booster") or row.get("skip") or "ok" for row in rows)
    lines.append("")
    lines.append(f"tabli ukupno: {len(rows)}")
    for reason, count in skips.most_common():
        lines.append(f"  {count:5d}  {reason}")
    return "\n".join(lines)


def entries(rows, booster):
    """runtime.BOOSTER_MODE_SETTINGS entries for this booster.

    A match kind whose boards together say ON gets one entry valid for every
    mode of that kind ("*"); a single mode that says ISKLJUCI on its own
    (>= MIN_BOARDS) gets an explicit entry without the setting, which overrides
    the kind-wide one. Unmeasured combinations stay out of the table, so the
    bot keeps its current behaviour there.
    """
    grouped = groups(rows)
    settings_by_kind = collections.defaultdict(dict)
    for (name, kind, mode), diffs in grouped.items():
        settings_by_kind[kind].setdefault(name, []).extend(diffs)
    out = {}
    for kind, per_setting in settings_by_kind.items():
        on, off_modes = set(), collections.defaultdict(set)
        for name, diffs in per_setting.items():
            if verdict(diffs) == "UKLJUCI":
                on.add(name)
            elif verdict(diffs) == "ISKLJUCI":
                off_modes[name].add("kind")
        per_mode = {(name, mode): diffs for (name, k, mode), diffs in grouped.items() if k == kind}
        for (name, mode), diffs in per_mode.items():
            if verdict(diffs) == "ISKLJUCI":
                off_modes[mode].add(name)
        for name in on:
            out[(booster, kind, "*")] = sorted(on)
        for mode, names in off_modes.items():
            if mode == "kind":
                continue
            kept = sorted(on - names)
            out[(booster, kind, mode)] = kept
    return out


def main(argv=None):
    from tools.gentle import gentle_pool

    parser = argparse.ArgumentParser()
    parser.add_argument("--booster", type=int, required=True)
    parser.add_argument("--kinds", default="versus,race,solo",
                        help="vrste meca koje se mere (versus,race,solo)")
    parser.add_argument("--width", type=int, default=10)
    parser.add_argument("--workers", type=int, default=None, help="broj procesa (dok se igra: 2)")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--entries", action="store_true", help="stampaj stavke za runtime.py")
    args = parser.parse_args(argv)
    booster = args.booster
    if booster not in BOOSTERS:
        raise SystemExit(f"podrzani boosteri: {sorted(BOOSTERS)}")
    out_dir = OUT / f"{booster}_{BOOSTERS[booster]}"
    out_dir.mkdir(parents=True, exist_ok=True)
    rows_path, progress = out_dir / "rows.jsonl", out_dir / "progress.txt"
    done_keys = set()
    if rows_path.exists():
        for line in rows_path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            done_keys.add((row["session"], row["record"]))
    kinds = {kind.strip() for kind in args.kinds.split(",") if kind.strip()}
    items = [(str(f), args.width, booster) for f in booster_records(booster, kinds)]
    items = [i for i in items if (Path(i[0]).parent.name, Path(i[0]).stem) not in done_keys]
    if args.limit:
        items = items[:args.limit]
    total = len(items) + len(done_keys)
    before, started = total - len(items), time.monotonic()
    with rows_path.open("a", encoding="utf-8") as out, gentle_pool(args.workers) as pool:
        for new, row in enumerate(pool.imap_unordered(work, items), 1):
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
            out.flush()
            done, elapsed = before + new, time.monotonic() - started
            eta = elapsed / new * (total - done)
            progress.write_text(
                f"{done}/{total} ({done * 100 // total}%), proteklo {elapsed:.0f} s, "
                f"ostalo ~{eta:.0f} s, kraj oko "
                f"{time.strftime('%H:%M', time.localtime(time.time() + eta))}\n", encoding="utf-8")
    rows = [json.loads(line) for line in rows_path.read_text(encoding="utf-8").splitlines()]
    text = table(rows, booster)
    (out_dir / "table.txt").write_text(text, encoding="utf-8")
    print(text)
    if args.entries:
        for key, names in sorted(entries(rows, booster).items(), key=lambda kv: (kv[0][1], kv[0][2])):
            print(f"    ({key[0]}, \"{key[1]}\", {key[2]}): frozenset({names!r}),")


if __name__ == "__main__":
    main()
