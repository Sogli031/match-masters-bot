"""Valentine Vinnie SE (47) - are the three targets a scan order or a random pick?

    python tools/vinnie_se_probe.py [Debug/research/FOLDER]

For every clean activation pair prints the recorded targets, whether they are
monotone in row/column order, their rank among plain cells in row-major and
column-major order, and the ranks of the same cells inside a few candidate
filters (plain only / plain without blue / plain without blue and without
special).  Nothing is guessed about the port: this only measures the recording.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.vinnie_se_check import (  # noqa: E402
    load,
    raw_slots,
    recorded_activations,
    score,
    VINNIE_SE,
    booster_type,
)

DEFAULT_FOLDER = ROOT / "Debug" / "research" / "20261120_115017_super-sized"


def targets_of(after: dict):
    fields = (((after.get("profile") or {}).get("ability_detail") or {}).get("fields") or {})
    entries = ((fields.get("sourceCellToColored") or {}).get("entries") or ())
    return [(e["key"]["x"], e["key"]["y"]) for e in entries]


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    folder = Path(argv[0]) if argv else DEFAULT_FOLDER
    lines = []
    for name_a, name_b, before, after in recorded_activations(folder):
        if booster_type(before) != VINNIE_SE:
            continue
        slots = raw_slots(before)
        targets = targets_of(after)
        size = int(((before.get("profile") or {}).get("rules") or {}).get("boardSize") or 8)
        cells = [(x, y) for y in range(size) for x in range(size) if (x, y) in slots]

        def key_of(cell):
            return slots[cell]

        def plain(cell):
            return key_of(cell).get("value") == 0

        def not_blue(cell):
            return key_of(cell).get("color") != 4

        row = sorted(cells, key=lambda c: (c[1], c[0]))
        col = sorted(cells, key=lambda c: (c[0], c[1]))

        def ranks(order, keep):
            seq = [c for c in order if keep(c)]
            return [seq.index(t) if t in seq else None for t in targets]

        gained = None
        sa, _ = score(before)
        sb, _ = score(after)
        if sa is not None and sb is not None:
            gained = sb - sa
        lines.append(
            f"{name_a}->{name_b} score+{gained} targets={targets} "
            f"mono_row={targets == sorted(targets, key=lambda c: (c[1], c[0]))} "
            f"mono_col={targets == sorted(targets, key=lambda c: (c[0], c[1]))} "
            f"rank_row_plain={ranks(row, plain)} "
            f"rank_row_plain_nb={ranks(row, lambda c: plain(c) and not_blue(c))} "
            f"rank_col_plain={ranks(col, plain)} "
            f"n_plain={sum(1 for c in cells if plain(c))} "
            f"colors={[key_of(t).get('color') for t in targets]} "
            f"values={[key_of(t).get('value') for t in targets]}"
        )
    text = "\n".join(lines)
    print(text)
    (folder / "vinnie_se_probe.txt").write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
