"""Inventory of booster activations in Debug/research for El Magneto / El Magneto SE.

    python tools/magneto_inventory.py [--booster 48] [--out Debug/magneto_inventory.txt]

For every session folder it lists each NNN -> NNN+1 pair whose action is
activate_booster (or whose target boosters differ), the booster type, the mode,
what refill_input_detail holds and whether the pair is usable.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def booster_of(rec):
    for p in (rec.get("snapshot_state") or {}).get("players") or ():
        if p.get("player_type") == 0:
            return p.get("special_ability_type"), p.get("special_ability_name")
    return None, None


def detail_of(rec):
    marker = rec.get("refill_input")
    if isinstance(marker, (list, tuple)) and len(marker) > 2:
        return marker[2] if isinstance(marker[2], dict) else {}
    return {}


def mode_of(rec):
    prof = rec.get("profile") or {}
    rules = prof.get("rules") or {}
    return (prof.get("rules_id"), rules.get("pvpMode"), rules.get("modeId"))


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    want = {48}
    if "--booster" in args:
        want = {int(args[args.index("--booster") + 1])}
    out = ROOT / "Debug/magneto_inventory.txt"
    if "--out" in args:
        out = ROOT / args[args.index("--out") + 1]
    folders = sorted((ROOT / "Debug/research").iterdir())
    lines = []
    for folder in folders:
        files = sorted(folder.glob("[0-9][0-9][0-9].json"))
        if not files:
            continue
        rows = []
        for a, b in zip(files, files[1:]):
            ra = json.loads(a.read_text(encoding="utf-8"))
            rb = json.loads(b.read_text(encoding="utf-8"))
            det = detail_of(rb)
            kind = det.get("action")
            ba, na = booster_of(ra)
            bb, nb = booster_of(rb)
            if kind != "activate_booster" and ba not in want:
                continue
            rows.append((a.stem, b.stem, ba, na, bb, nb, kind, det))
        if not rows:
            continue
        prof = json.loads(files[0].read_text(encoding="utf-8")).get("profile") or {}
        rules = prof.get("rules") or {}
        lines.append(f"== {folder.name}  ({len(files)} snimaka)  rules_id={prof.get('rules_id')} "
                     f"pvpMode={rules.get('pvpMode')} modeId={rules.get('modeId')}")
        for a, b, ba, na, bb, nb, kind, det in rows:
            keys = sorted(det)
            lines.append(f"  {a}->{b}  tip {ba} {na}  akcija={kind}  polja={keys}")
            lines.append(f"      detail={json.dumps(det, ensure_ascii=False)}")
    text = "\n".join(lines)
    out.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
