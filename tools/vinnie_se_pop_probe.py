"""Vinnie SE (47): PopRandom models for target picking.

Two models, both from the decompiled code (old RVAs, they match
`Debug/reverse/libil2cpp.so`):

* `ArrangeTargetOptions` (0x5abcc20) rebuilds the candidate list by repeatedly
  calling `PopRandom(list, random)` (0x5abcec4): draw `index =
  random.Range(0, list.Count)`, take and remove.  Before each pop it calls
  `RandomWrapper.Chance(p)` (0x5af5c4c) and stops the loop when it succeeds.
* The pop is taken from one of two groups: candidates that are in
  `matchablePositions` (positions that can form a move) and the rest.

`Cupid::Use` then takes the first element of the rebuilt list.

    python tools/vinnie_se_pop_probe.py [FOLDER]

Prints, for every scheme, how many of the 14 activations reproduce all three
targets in the recorded order and how many reproduce the first target.
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
    raw_slots,
    recorded_activations,
)

DEFAULT_FOLDER = ROOT / "Debug" / "research" / "20261120_115017_super-sized"
BLUE = 4
DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1))


def targets_of(after: dict):
    fields = (((after.get("profile") or {}).get("ability_detail") or {}).get("fields") or {})
    entries = ((fields.get("sourceCellToColored") or {}).get("entries") or ())
    return [(e["key"]["x"], e["key"]["y"]) for e in entries]


def ordered_cells(size: int, order: str):
    cells = [(x, y) for y in range(size) for x in range(size)]
    if order == "col":
        cells.sort(key=lambda c: (c[0], c[1]))
    elif order == "rowrev":
        cells.sort(key=lambda c: (-c[1], -c[0]))
    return cells


def is_plain(slots, cell):
    s = slots.get(cell)
    return s is not None and s.get("value") == 0


def line_length(slots, size, x, y, color, dx, dy):
    total = 1
    for sign in (1, -1):
        step = 1
        while True:
            nx, ny = x + dx * step * sign, y + dy * step * sign
            if not (0 <= nx < size and 0 <= ny < size):
                break
            s = slots.get((nx, ny)) or {}
            if s.get("value") != 0 or s.get("color") != color:
                break
            total += 1
            step += 1
    return total


def creates_match(slots, size, cell, other, color_a, color_b):
    """Does swapping `cell` and `other` create a line of 3 through either?"""
    swapped = dict(slots)
    sa, sb = dict(slots[cell]), dict(slots[other])
    sa["color"], sb["color"] = color_b, color_a
    swapped[cell], swapped[other] = sa, sb
    for pos, color in ((cell, color_b), (other, color_a)):
        x, y = pos
        for dx, dy in ((1, 0), (0, 1)):
            if line_length(swapped, size, x, y, color, dx, dy) >= 3:
                return True
    return False


def matchable_set(size, slots):
    """Positions that can take part in a move (swap that makes a 3-line)."""
    plain = [c for c in ordered_cells(size, "row") if is_plain(slots, c)]
    plain_set = set(plain)
    out = set()
    for cell in plain:
        x, y = cell
        color = slots[cell].get("color")
        for dx, dy in DIRS:
            other = (x + dx, y + dy)
            if other not in plain_set:
                continue
            if creates_match(slots, size, cell, other, color, slots[other].get("color")):
                out.add(cell)
                out.add(other)
    return out


def on_edge(cell, size):
    """BoardModel::Edge (0x596f6c4): border ring of the board."""
    x, y = cell
    return x == 0 or y == 0 or x == size - 1 or y == size - 1


def groups_for(size, slots, order, allow_blue, used, matchable, allow_edge=False):
    group_a, group_b = [], []
    for c in ordered_cells(size, order):
        if not is_plain(slots, c) or c in used:
            continue
        if not allow_edge and on_edge(c, size):
            continue
        if not allow_blue and (slots.get(c) or {}).get("color") == BLUE:
            continue
        (group_a if c in matchable else group_b).append(c)
    return group_a, group_b


def pop_random(rng: EngineRNG, pool: list):
    index = rng.range(0, len(pool))
    index = max(0, min(len(pool) - 1, index))
    return pool.pop(index)


def predict(before: dict, order: str, allow_blue: bool, group_first: str,
            chance: int, count: int = 3, allow_edge: bool = False):
    size = int(((before.get("profile") or {}).get("rules") or {}).get("boardSize") or 8)
    slots = raw_slots(before)
    matchable = matchable_set(size, slots)
    rng = EngineRNG.from_capture((before.get("profile") or {}).get("rng") or {})
    used, picked = set(), []
    for _ in range(count):
        group_a, group_b = groups_for(size, slots, order, allow_blue, used, matchable, allow_edge)
        if not group_a and not group_b:
            break
        out = []
        while group_a or group_b:
            if chance >= 0 and rng.chance(chance):
                break
            if group_first == "matchable":
                pool = group_a if group_a else group_b
            else:
                pool = group_b if group_b else group_a
            out.append(pop_random(rng, pool))
        if not out:                                  # nothing arranged: first option
            out = (group_a or group_b)[:1]
        picked.append(out[0])
        used.add(out[0])
    return picked


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    folder = Path(argv[0]) if argv else DEFAULT_FOLDER
    pairs = [(a, b, before, after) for a, b, before, after in recorded_activations(folder)
             if booster_type(before) == VINNIE_SE]
    lines = []

    # How many plain cells are "matchable" at all, and are the targets in it?
    total_targets = total_matchable = 0
    for _, _, before, after in pairs:
        size = int(((before.get("profile") or {}).get("rules") or {}).get("boardSize") or 8)
        slots = raw_slots(before)
        matchable = matchable_set(size, slots)
        for t in targets_of(after):
            total_targets += 1
            total_matchable += t in matchable
    lines.append(f"targets that are matchable: {total_matchable}/{total_targets}")

    best = []
    for order in ("row", "col"):
        for allow_blue in (False, True):
            for allow_edge in (False, True):
                for group_first in ("matchable", "other"):
                    for chance in (-1, 0, 1, 2, 5, 10, 20, 50, 99):
                        hits, first = 0, 0
                        for _, _, before, after in pairs:
                            want = targets_of(after)
                            got = predict(before, order, allow_blue, group_first, chance,
                                          len(want) or 3, allow_edge)
                            if got == want:
                                hits += 1
                            if got and want and got[0] == want[0]:
                                first += 1
                        lines.append(
                            f"order={order:3s} blue={allow_blue!s:5s} edge={allow_edge!s:5s}"
                            f" first={group_first:9s} chance={chance:3d}"
                            f"  all3={hits}/{len(pairs)}  first={first}/{len(pairs)}"
                        )
                        best.append((hits, first, order, allow_blue, allow_edge, group_first, chance))
    best.sort(reverse=True)
    lines.append("best: " + ", ".join(
        f"all3={h} first={f} order={o} blue={b} edge={e} first={g} chance={c}"
        for h, f, o, b, e, g, c in best[:3]
    ))
    text = "\n".join(lines)
    print(text)
    (folder / "vinnie_se_pop_probe.txt").write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
