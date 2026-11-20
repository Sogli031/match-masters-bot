"""Inventory of every recorded booster activation in Debug/research.

    python tools/booster_inventory.py [--out Debug/booster_inventory.txt]

For every session folder and every booster, counts the activations that a
replay can use: a consecutive pair NNN -> NNN+1 whose recorded action is
activate_booster, not played by hand, both boards in the same mode the
simulator replays, and no skipped board between them. A pair the simulator
would refuse (see strategy_lab.simulation.step) is counted as skipped with its
reason, so the plan can name what a recording still needs.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

NAMES = {
    40: "Monkey Joojoo", 41: "Billie Boom", 45: "Doctor Color SE", 46: "All Aboard SE",
    47: "Valentine Vinnie SE", 48: "El Magneto SE", 49: "UFO SE", 33: "El Magneto",
}
PORTED = (35, 44, 52, 54, 61, 63)


def local_booster(record):
    for player in (record.get("snapshot_state") or {}).get("players") or ():
        if player.get("player_type") == 0:
            return player.get("special_ability_type")
    return None


def marker_detail(record):
    marker = record.get("refill_input")
    if isinstance(marker, (list, tuple)) and len(marker) > 2 and isinstance(marker[2], dict):
        return marker[2]
    return {}


def mode_text(profile):
    rules = profile.get("rules") or {}
    return f"{profile.get('rules_id') or '?'}/pvp{rules.get('pvpMode')}"


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    out_path = ROOT / "Debug/booster_inventory.txt"
    if "--out" in args:
        out_path = ROOT / args[args.index("--out") + 1]

    rows = defaultdict(lambda: defaultdict(lambda: {"usable": 0, "skipped": [], "modes": set()}))
    lines = []
    for folder in sorted((ROOT / "Debug/research").iterdir()):
        files = sorted(folder.glob("[0-9][0-9][0-9].json"))
        if len(files) < 2:
            continue
        records = [json.loads(path.read_text(encoding="utf-8")) for path in files]
        booster = local_booster(records[0])
        stats = rows[booster][folder.name]
        stats["modes"].add(mode_text(records[0].get("profile") or {}))
        for index in range(len(records) - 1):
            detail = marker_detail(records[index + 1])
            if detail.get("action") != "activate_booster":
                continue
            head = f"{files[index].stem}->{files[index + 1].stem}"
            if local_booster(records[index + 1]) != booster:
                stats["skipped"].append((head, "booster changed"))
                continue
            if detail.get("manual"):
                stats["skipped"].append((head, "played by hand"))
                continue
            same_input = ((records[index].get("refill_input") or [None])[0]
                          == (records[index + 1].get("refill_input") or [None])[0])
            if same_input:
                stats["skipped"].append((head, "no new bot input (hand played or opponent)"))
                continue
            stats["usable"] += 1

    lines.append("Booster inventory, Debug/research (usable = consecutive activate_booster pair)")
    lines.append("")
    for booster in sorted(rows, key=lambda value: (value is None, value)):
        total = sum(stat["usable"] for stat in rows[booster].values())
        skipped = sum(len(stat["skipped"]) for stat in rows[booster].values())
        name = NAMES.get(booster, "?")
        flag = "PORTED" if booster in PORTED else "not ported"
        lines.append(f"{booster}: {name}  ({flag})  usable {total}, skipped {skipped}")
        for session, stat in rows[booster].items():
            modes = ", ".join(sorted(stat["modes"]))
            lines.append(f"    {session}  modes {modes}  usable {stat['usable']}  skipped {len(stat['skipped'])}")
            for head, why in stat["skipped"]:
                lines.append(f"        {head}: {why}")
        lines.append("")
    text = "\n".join(lines)
    out_path.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
