"""Where the jelly actually is, straight out of the game's memory.

A single manual dump, printed as the board with the infected cells marked. The
point is to check the read against the screen: run it with a jelly match open,
compare the marked cells with the rainbow-outlined area, and the answer is
either "these are the same cells" or "the mapping is transposed" -- which is the
one thing the offline analysis could not settle, because JellySE stores its area
as text under a key the engine formats at runtime.

    python .\tools\probe_jelly.py
    python .\tools\probe_jelly.py --watch      # keep dumping every few seconds
    python .\tools\probe_jelly.py --from-debug # read what a played match recorded

With Debug ticked in the memory GUI nothing needs to be run alongside the game:
the agent switches to trace mode, which is also what turns the engine-decoded
read on, and every move's `move.json` keeps its `jelly_state`. `--from-debug`
walks those afterwards.

`verified` in the output means the points came back from the engine's own
deserialiser (a manual dump asks for it) rather than from the host's parser.
Both are printed when they disagree, which is the whole reason for asking twice.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import board_source  # noqa: E402
import matchmasters_board_reader as reader  # type: ignore # noqa: E402

MARK = "()"


def _board_with_zone(snapshot: dict, cells) -> str:
    """The board as the reader prints it, with the jelly cells in brackets."""
    marked = set(cells or ())
    board = snapshot.get("board") or []
    lines = []
    for row_index, row in enumerate(board):
        cells_text = []
        for col_index, value in enumerate(row):
            label = reader._COLOR_LABELS.get(value, "?")
            if (row_index, col_index) in marked:
                cells_text.append(f"{MARK[0]}{label}{MARK[1]}")
            else:
                cells_text.append(f" {label} ")
        lines.append(f"{row_index}: " + "".join(cells_text))
    header = "   " + "".join(f" {index} " for index in range(len(board[0]) if board else 0))
    return header + "\n" + "\n".join(lines)


def _report(snapshot: dict) -> None:
    state = board_source.jelly_zone_state(snapshot)
    jelly = snapshot.get("jelly")
    extra = snapshot.get("board_extra_data")

    if jelly is None:
        print("JellySE: nema instance u memoriji (nije jelly partija ili jos nije aktiviran)")
    else:
        error = jelly.get("error")
        if error:
            print(f"JellySE: greska pri citanju: {error}")
        keys = jelly.get("keys") or {}
        if keys:
            print("Kljucevi koje engine koristi:")
            for label, key in keys.items():
                print(f"  {label:22} = {key!r}")
        else:
            print("JellySE: kljucevi nisu procitani")
        engine_points = jelly.get("all_infected")
        if engine_points is not None:
            print(f"Engine get_AllInfected: {len(engine_points)} tacaka (x,y) {engine_points}")
        if jelly.get("source_cell"):
            print(f"Izvorna celija: {jelly['source_cell']}")

    if isinstance(extra, dict):
        print(f"\nBoardModel.extraData ({len(extra)} unosa):")
        for key, value in extra.items():
            shown = value if len(value) <= 160 else value[:157] + "..."
            print(f"  {key!r}: {shown!r}")
    else:
        print("\nBoardModel.extraData: nije procitan (prazan recnik ili stari agent)")

    if state is None:
        print("\nZona: host nije prepoznao nijednu jelly zonu (memorija ne kaze).")
        return
    cells = state["cells"]
    if not cells:
        print(
            f"\nZona: memorija kaze da trenutno NEMA jelly-ja "
            f"(verified={state['verified']}, kljuc={state['key']!r})."
        )
        return
    print(
        f"\nZona: {len(cells)} polja, verified={state['verified']}, "
        f"kljuc={state['key']!r}, boja={state['target_color']}, "
        f"faza={state['phase']}, preostalo upotreba={state['uses_left']}"
    )
    print("Celije (red, kolona):", ", ".join(f"({r},{c})" for r, c in cells))
    print()
    print(_board_with_zone(snapshot, cells))
    print()
    print(
        "Uporedi sa ekranom: ako je oznaceno ogledalo prave zone, tacke su (y,x) "
        "a ne (x,y) i treba obrnuti mapiranje u board_source._serialized_points."
    )


def _report_from_debug(runs_dir: Path, limit: int) -> int:
    """What the played match already recorded, newest run last.

    One line per move that saw a jelly, so a whole match reads as a sequence:
    the area should move and shrink as the engine spends the jelly's uses.
    """
    moves = sorted(runs_dir.glob("*/move.json"))
    if not moves:
        print(f"Nema zapisa u {runs_dir}")
        return 1
    seen = 0
    for path in moves:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        state = payload.get("jelly_state")
        cells = payload.get("jelly_zone_cells") or []
        if not state and not cells:
            continue
        seen += 1
        parsed = (state or {}).get("host_parsed") or {}
        agent = (state or {}).get("agent") or {}
        engine = agent.get("all_infected")
        print(
            f"{path.parent.name}: {len(cells)} polja "
            f"verified={parsed.get('verified')} "
            f"boja={parsed.get('target_color')} "
            f"upotreba={parsed.get('uses_left')} "
            f"engine={'-' if engine is None else len(engine)} tacaka"
        )
        if agent.get("keys"):
            print(f"    kljucevi: {agent['keys']}")
        if cells:
            print(f"    celije: {', '.join(f'({r},{c})' for r, c in cells)}")
        if seen >= limit:
            break
    if seen == 0:
        print(
            f"Prosao {len(moves)} poteza, nijedan nije video jelly. "
            "Da li je Debug bio ukljucen i da li je partija bila jelly?"
        )
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", default=None)
    parser.add_argument("--package", default=reader.DEFAULT_PACKAGE)
    parser.add_argument("--agent", type=Path, default=reader.DEFAULT_AGENT)
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Ostani zakacen i dumpuj periodicno umesto jednom",
    )
    parser.add_argument("--interval", type=float, default=5.0)
    parser.add_argument(
        "--from-debug",
        action="store_true",
        help="Ne kaci se na igru; procitaj sta je Debug vec snimio u Debug/runs",
    )
    parser.add_argument(
        "--runs",
        type=Path,
        default=PROJECT_ROOT / "Debug" / "runs",
        help="Folder sa Debug zapisima za --from-debug",
    )
    parser.add_argument("--limit", type=int, default=40)
    args = parser.parse_args(argv)

    if args.from_debug:
        return _report_from_debug(args.runs, max(1, args.limit))

    device = session = script = None
    try:
        adb = reader.find_adb()
        serial = reader.discover_serial(adb, args.serial)
        reader.ensure_frida_server(adb, serial)
        receiver = reader.BoardReader(
            reader.DEFAULT_OUTPUT, reader.DEFAULT_LATEST, quiet=True
        )
        device, session, script, pid = reader.attach_reader(
            adb,
            serial,
            args.package,
            args.agent,
            receiver,
            spawn=False,
            poll_seconds=1.0,
        )
        print(f"Attach uspesan: {args.package} PID={pid} serial={serial}\n", flush=True)
        while True:
            receiver.snapshot_event.clear()
            reader._export_call(script.exports_sync, ("dump_board", "dumpboard"))
            if not receiver.snapshot_event.wait(15.0):
                print("Nije primljen snapshot u roku od 15s")
                return 1
            snapshot = json.loads(
                reader.DEFAULT_LATEST.read_text(encoding="utf-8")
            )["snapshot"]
            print("=" * 72)
            print(f"snapshot {snapshot.get('captured_at')}")
            _report(snapshot)
            if not args.watch:
                return 0
            time.sleep(max(1.0, args.interval))
    except reader.ReaderError as error:
        print(f"GRESKA: {error}")
        return 2
    except KeyboardInterrupt:
        return 0
    finally:
        for closer in (
            lambda: script.unload() if script else None,
            lambda: session.detach() if session else None,
        ):
            try:
                closer()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
