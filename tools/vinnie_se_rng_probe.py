"""Vinnie SE (47): try target-pick schemes against the 13 clean activations.

    python tools/vinnie_se_rng_probe.py [FOLDER]

Each scheme rebuilds the candidate list from the board *before* the activation
and draws the three targets in sequence from the pre-activation EngineRNG,
removing a cell once it is used (a heart occupies it).  A scheme only counts
when all three recorded targets come out in the recorded order.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine_rng import EngineRNG  # noqa: E402
from tools.vinnie_se_check import (  # noqa: E402
    VINNIE_SE,
    booster_type,
    load,
    raw_slots,
    recorded_activations,
)

DEFAULT_FOLDER = ROOT / "Debug" / "research" / "20261120_115017_super-sized"
HEART_VALUE = 23


def targets_of(after: dict):
    fields = (((after.get("profile") or {}).get("ability_detail") or {}).get("fields") or {})
    entries = ((fields.get("sourceCellToColored") or {}).get("entries") or ())
    return [(e["key"]["x"], e["key"]["y"]) for e in entries]


def board(before: dict):
    size = int(((before.get("profile") or {}).get("rules") or {}).get("boardSize") or 8)
    slots = raw_slots(before)
    return size, slots


def candidates(size, slots, order, allow_blue, taken):
    cells = [(x, y) for y in range(size) for x in range(size)]
    if order == "row":
        cells.sort(key=lambda c: (c[1], c[0]))
    elif order == "col":
        cells.sort(key=lambda c: (c[0], c[1]))
    elif order == "rowrev":
        cells.sort(key=lambda c: (-c[1], -c[0]))
    out = []
    for c in cells:
        s = slots.get(c)
        if s is None or s.get("value") != 0 or c in taken:
            continue
        if not allow_blue and s.get("color") == 4:
            continue
        out.append(c)
    return out


SCHEMES = []
for order in ("row", "col", "rowrev"):
    for allow_blue in (False, True):
        for draw in ("range", "next", "shuffle", "poprandom"):
            SCHEMES.append((order, allow_blue, draw))


def pick_all(scheme, before, count=3):
    order, allow_blue, draw = scheme
    size, slots = board(before)
    rng = EngineRNG.from_capture((before.get("profile") or {}).get("rng") or {})
    taken, picked = set(), []
    if draw == "shuffle":
        pool = candidates(size, slots, order, allow_blue, taken)
        return rng.shuffled(pool)[:count]
    for _ in range(count):
        pool = candidates(size, slots, order, allow_blue, taken)
        if not pool:
            break
        if draw == "range":
            idx = rng.range(0, len(pool))
        elif draw == "next":
            idx = rng.next(len(pool))
        else:                                   # poprandom: draw, remove, retry
            idx = rng.range(0, len(pool))
        idx = max(0, min(len(pool) - 1, idx))
        cell = pool[idx]
        picked.append(cell)
        taken.add(cell)
    return picked


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    folder = Path(argv[0]) if argv else DEFAULT_FOLDER
    pairs = [(a, b, before, after) for a, b, before, after in recorded_activations(folder)
             if booster_type(before) == VINNIE_SE]
    lines = []
    for scheme in SCHEMES:
        hits = 0
        detail = []
        for name_a, name_b, before, after in pairs:
            want = targets_of(after)
            got = pick_all(scheme, before, len(want) or 3)
            ok = got == want
            hits += ok
            if ok:
                detail.append(name_a)
        lines.append(f"{scheme}: {hits}/{len(pairs)}  {','.join(detail)}")
    text = "\n".join(lines)
    print(text)
    (folder / "vinnie_se_rng_probe.txt").write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
