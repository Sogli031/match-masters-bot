"""Valentine Vinnie SE (booster 47) — recorded activations, measured one by one.

    python tools/vinnie_se_check.py [Debug/research/FOLDER]

An activation is a pair NNN -> NNN+1 whose action is ``activate_booster``; the
booster picks everything itself (``RequiredPositions`` 0), so the recording needs
no target or colour in ``refill_input`` (checked: every recorded action is
``{"action":"activate_booster","booster_mode":"none"}``).

What the memory profile already gives us, independently of any simulation:

* ``profile.ability_detail.fields.sourceCellToColored`` — the three cells the
  game chose this activation, each with its plus (the area GetExplosionArea
  returns for Cupid SE without the powerup variant);
* ``raw_slots`` — the hearts left on the board: ``value`` 23 (CupidHeart) with
  ``color`` and ``color2``, i.e. the two colours it matches.

The tool checks the invariants that a port must reproduce (3 targets, a plain
off-edge piece whose plus is plain, colour1 == the target cell's colour, the
15 destroyed cells = +15 points) and, if ``engine_cupid.py`` is written,
compares the port's hearts against the recording. Until then it prints
``PORT NIJE NAPISAN`` and the measured facts, so the misses stay explainable.

Report goes to FOLDER/vinnie_se_check.txt as well as the screen.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

VINNIE_SE = 47
HEART_VALUE = 23          # SlotValueType.CupidHeart
PIECES_PER_ACTIVATION = 3  # piecesPerActivation "3"
DESTROYED_PER_HEART = 5   # GetPlus(includeCentre) — the heart's own cell + 4


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def raw_slots(record: dict) -> dict:
    return {(s["x"], s["y"]): s for s in record.get("raw_slots") or ()}


def booster_type(record: dict):
    for player in (record.get("snapshot_state") or {}).get("players") or ():
        if player.get("player_type") == 0:
            return player.get("special_ability_type")
    return None


def action_of(record: dict):
    marker = record.get("refill_input")
    if isinstance(marker, (list, tuple)) and len(marker) > 2 and isinstance(marker[2], dict):
        return marker[2]
    return None


def plus(cell):
    x, y = cell
    return [(x, y), (x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)]


def score(record: dict):
    for player in (record.get("snapshot_state") or {}).get("players") or ():
        if player.get("player_type") == 0:
            return player.get("score"), player.get("energy")
    return None, None


def rng_counter(record: dict):
    return (((record.get("profile") or {}).get("rng") or {}).get("<counter>k__BackingField"))


def recorded_activations(folder: Path):
    """[(before_name, after_name, before, after)] for activate_booster pairs."""
    files = sorted(folder.glob("[0-9][0-9][0-9].json"))
    out = []
    for before, after in zip(files, files[1:]):
        detail = action_of(load(after))
        if not detail or detail.get("action") != "activate_booster":
            continue
        out.append((before.stem, after.stem, load(before), load(after)))
    return out


def port_hearts(before: dict):
    """The port's hearts for this board, or None when engine_cupid is not written."""
    try:
        import engine_cupid
    except ImportError:
        return None, "PORT NIJE NAPISAN (nema engine_cupid.py)"
    try:
        return engine_cupid.predict_activation(before), None
    except Exception as exc:                    # noqa: BLE001 — reported, not hidden
        return None, f"port pao: {type(exc).__name__}: {exc}"


def check_pair(name_a: str, name_b: str, before: dict, after: dict):
    size = int(((before.get("profile") or {}).get("rules") or {}).get("boardSize") or 8)
    fields = (((after.get("profile") or {}).get("ability_detail") or {}).get("fields") or {})
    entries = ((fields.get("sourceCellToColored") or {}).get("entries") or ())
    targets = [(e["key"]["x"], e["key"]["y"]) for e in entries]
    ra, rb = raw_slots(before), raw_slots(after)
    hearts = {p: (s.get("color"), s.get("color2")) for p, s in rb.items() if s.get("value") == HEART_VALUE}
    score_a, energy_a = score(before)
    score_b, energy_b = score(after)
    gained = (score_b - score_a) if None not in (score_a, score_b) else None
    notes = []

    if booster_type(before) != VINNIE_SE:
        notes.append(f"tip {booster_type(before)}")
    if len(targets) != PIECES_PER_ACTIVATION:
        notes.append(f"{len(targets)} ciljeva (ocekivano {PIECES_PER_ACTIVATION})")

    colour_ok = 0
    for cell in targets:
        x, y = cell
        slot = ra.get(cell) or {}
        color = slot.get("color")
        area = plus(cell)
        if slot.get("value") != 0:
            notes.append(f"cilj {cell} nije obicna plocica (value {slot.get('value')})")
        if not (0 < x < size - 1 and 0 < y < size - 1):
            notes.append(f"cilj {cell} je na ivici")
        # The heart keeps the colour of the cell it was created on and falls
        # down the holes its own explosion opened: one row (003->004) or more
        # when another heart's area opened the cell below too (006->007, target
        # (6,1) -> heart at (6,3)). It can also be matched away in the cascade,
        # so a missing heart is not an error by itself.
        hit = None
        for yy in range(y, size):
            p = (x, yy)
            if p in hearts and hearts[p][0] == color and (ra.get(p) or {}).get("value") != HEART_VALUE:
                hit = p
                break
        if hit is not None:
            colour_ok += 1
        elif not hearts:
            notes.append(f"cilj {cell}: nema nijednog srca na tabli posle")

    predicted, port_note = port_hearts(before)
    port_line = ""
    if port_note:
        port_line = " | " + port_note
    elif predicted:
        want = {(c[0], c[1]): c[2:] for c in predicted}
        got = {(p[0], p[1]): h for p, h in hearts.items()}
        wrong = sorted(set(want) ^ set(got)) + sorted(p for p in set(want) & set(got) if want[p] != got[p])
        port_line = " | port TACNO" if not wrong else f" | port promasaj: {wrong[:6]}"

    exact = not notes and colour_ok == len(targets)
    head = f"{name_a}->{name_b}: {'TACNO' if exact else 'RAZLIKA: ' + ', '.join(notes[:4])}"
    detail = (f"ciljevi {sorted(targets)}, srca {[(p, h) for p, h in sorted(hearts.items())]}, "
              f"boja cilja = boja srca {colour_ok}/{len(targets)}, "
              f"poeni {score_a}->{score_b} (+{gained}), punjenje {energy_a}->{energy_b}, "
              f"rng {rng_counter(before)}->{rng_counter(after)}")
    return exact, head + "\n    " + detail + port_line


def analyze(folder: Path) -> str:
    pairs = recorded_activations(folder)
    lines = [f"Sesija: {folder.name}, aktivacija: {len(pairs)}",
             "Invarijante: 3 cilja, obicna plocica van ivice, plus sve obicno, "
             "boja srca = boja cilja, +15 poena (3 x plus 5 polja)."]
    exact = 0
    for name_a, name_b, before, after in pairs:
        ok, text = check_pair(name_a, name_b, before, after)
        exact += ok
        lines.append(text)
    lines.append("")
    lines.append(f"UKUPNO: invarijante tacne u {exact} od {len(pairs)} aktivacija")
    if exact < len(pairs):
        lines.append("Svaki red iznad imenuje sta se razlikuje; cilj i druga boja srca "
                     "traze Cupid::Use (rva 0x5a2c5d4) — vidi docs/booster_logic_from_code.md.")
    return "\n".join(lines)


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    folder = Path(args[0]) if args else ROOT / "tests/fixtures/vinnie_se/20261120_115017_super-sized"
    text = analyze(folder)
    (folder / "vinnie_se_check.txt").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
