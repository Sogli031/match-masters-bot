"""Dump the IL2CPP symbol table of the running game to JSON.

This is step one of the offline reverse-engineering pipeline. It attaches to
the live game exactly like ``matchmasters_board_reader`` does (same Pie64/root/
namespace preflight, same ``emulated`` realm), asks the runtime where every
method's code lives, writes that down, and detaches. It reads no game state.

The output feeds ``tools/il2cpp_disasm.py``, which then works purely offline on
the shipped ``libil2cpp.so`` -- the game does not need to be running for that
part, and nothing is ever written back into the process.

Usage::

    python .\\tools\\dump_il2cpp_symbols.py --index

``--index`` additionally writes the ~400k entry ``rva -> Class::Method`` map.
It costs a minute and ~40 MB, and without it the disassembler cannot tell where
a function ends or name the functions it calls, so it is worth doing once per
game version.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.matchmasters_board_reader import (  # noqa: E402
    DEFAULT_PACKAGE,
    _export_call,
    FRIDA_PORT,
    ReaderError,
    discover_serial,
    ensure_frida_server,
    find_adb,
    game_pid,
    verify_namespace_cleaned,
)

try:
    import frida
except ImportError:  # pragma: no cover - host without frida installed
    frida = None  # type: ignore[assignment]

DEFAULT_AGENT = Path(__file__).with_name("il2cpp_symbols_dump.js")
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "il2cpp_symbols.json"
DEFAULT_INDEX = PROJECT_ROOT / "data" / "il2cpp_method_index.json"
DEFAULT_ABILITIES = PROJECT_ROOT / "data" / "ability_config.json"

# The classes that decide what a booster, a perk or a special piece actually
# does. Everything else in the image is noise for this project.
# `Match3Engine.` is the engine namespace and holds one class per booster
# (FroggyFu, MixyMeow, Cupid, UFOBeamSE...) plus GameLogic/BoardModel: 1227
# classes, which is small enough to take whole. The rest catch the helpers that
# live outside it, such as AbilityEffectHelpers.
DEFAULT_PATTERNS = [
    r"^Match3Engine\.",
    "Ability",
    "Booster",
    "Powerup",
    "SpecialPiece",
    "MutationLab",
]


class SymbolCollector:
    """Collects the agent's streamed chunks into plain Python structures."""

    def __init__(self) -> None:
        self.ready = threading.Event()
        self.classes_done = threading.Event()
        self.index_done = threading.Event()
        self.abilities_done = threading.Event()
        self.live_done = threading.Event()
        self.pieces_done = threading.Event()
        self.classes: list[dict[str, Any]] = []
        self.index: list[tuple[str, str]] = []
        self.abilities: list[dict[str, Any]] = []
        self.live_abilities: list[dict[str, Any]] = []
        self.piece_logics: list[dict[str, Any]] = []
        self.piece_catalogue: list[dict[str, Any]] = []
        self.meta: dict[str, Any] = {}
        self.errors: list[str] = []
        self.last_error: str | None = None
        self.detached: str | None = None

    def on_detached(self, reason: str, *_: Any) -> None:
        self.detached = str(reason)
        # Unblock every waiter: a detached session will never send again.
        self.ready.set()
        self.classes_done.set()
        self.index_done.set()
        self.abilities_done.set()
        self.live_done.set()
        self.pieces_done.set()

    def on_message(self, message: dict[str, Any], _data: Any) -> None:
        if message.get("type") == "error":
            self.last_error = str(message.get("description") or message)
            self.errors.append(self.last_error)
            return
        payload = message.get("payload")
        if not isinstance(payload, dict):
            return
        kind = payload.get("type")
        if kind == "ready":
            self.meta = {k: v for k, v in payload.items() if k != "type"}
            self.ready.set()
        elif kind == "classes":
            self.classes.extend(payload.get("items") or [])
        elif kind == "classes_done":
            self.classes_done.set()
        elif kind == "index":
            self.index.extend(tuple(item) for item in (payload.get("items") or []))
        elif kind == "index_done":
            self.index_done.set()
        elif kind == "abilities":
            self.abilities.extend(payload.get("items") or [])
        elif kind == "abilities_done":
            self.abilities_done.set()
        elif kind == "live_abilities":
            self.live_abilities.extend(payload.get("items") or [])
        elif kind == "live_abilities_done":
            self.live_done.set()
        elif kind == "piece_catalogue":
            self.piece_catalogue.extend(payload.get("items") or [])
        elif kind == "piece_logics":
            self.piece_logics.extend(payload.get("items") or [])
        elif kind == "piece_logics_done":
            self.pieces_done.set()
        elif kind in {"class_error", "error"}:
            self.errors.append(str(payload.get("message")))
        if self.detached:
            return


def attach(adb: str, serial: str, package: str, agent: Path, collector: SymbolCollector):
    if frida is None:
        raise ReaderError("Python paket frida nije instaliran")
    if not agent.exists():
        raise ReaderError(
            f"Agent nije napravljen: {agent}; pokreni tools/build_board_agent.ps1"
        )
    device = frida.get_device_manager().add_remote_device(f"127.0.0.1:{FRIDA_PORT}")
    pid = game_pid(adb, serial, package)
    if pid is None:
        raise ReaderError(f"Proces {package} nije pokrenut; pokreni igru pa probaj ponovo")
    verify_namespace_cleaned(adb, serial, pid)
    # Same reasoning as the board reader: Pie64 is x86_64, the game is ARM64
    # under the native bridge, and only the emulated realm sees libil2cpp.so.
    session = device.attach(pid, realm="emulated")
    try:
        session.on("detached", collector.on_detached)
        script = session.create_script(agent.read_text(encoding="utf-8"))
        script.on("message", collector.on_message)
        script.load()
        if not collector.ready.wait(30.0):
            raise ReaderError(collector.last_error or "Agent nije poslao ready u roku od 30s")
        if collector.detached:
            raise ReaderError(f"Sesija je prekinuta: {collector.detached}")
        return device, session, script
    except BaseException:
        session.detach()
        raise


def _wait(event: threading.Event, collector: SymbolCollector, timeout: float, label: str) -> None:
    if event.wait(timeout):
        return
    raise ReaderError(
        f"{label} nije zavrsen u roku od {timeout:.0f}s"
        + (f" (poslednja greska: {collector.last_error})" if collector.last_error else "")
    )


def build_symbol_document(collector: SymbolCollector, patterns: list[str]) -> dict[str, Any]:
    classes = sorted(collector.classes, key=lambda item: item.get("full_name") or "")
    methods = sum(len(item.get("methods") or []) for item in classes)
    return {
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "patterns": patterns,
        "runtime": collector.meta,
        "class_count": len(classes),
        "method_count": methods,
        "classes": classes,
    }


def build_index_document(collector: SymbolCollector) -> dict[str, Any]:
    # Sorted by address, which is exactly the order the disassembler needs to
    # derive "this function ends where the next one begins".
    entries = sorted({(rva, name) for rva, name in collector.index}, key=lambda e: int(e[0], 16))
    return {
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "runtime": collector.meta,
        "count": len(entries),
        "entries": [[rva, name] for rva, name in entries],
    }


def build_ability_document(collector: SymbolCollector) -> dict[str, Any]:
    abilities = sorted(collector.abilities, key=lambda item: item.get("type") or 0)
    configured = [a for a in abilities if a.get("additional_params")]
    return {
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "runtime": collector.meta,
        "count": len(abilities),
        # A booster with no params is one the server sent no tuning for; worth
        # knowing at a glance whether the read actually landed on real data.
        "with_params": len(configured),
        "abilities": abilities,
    }


def write_json(path: Path, payload: dict[str, Any], *, compact: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=None if compact else 2)
    path.write_text(text, encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", default=None, help="ADB serial (podrazumevano: autodetekcija Pie64)")
    parser.add_argument("--package", default=DEFAULT_PACKAGE)
    parser.add_argument("--agent", type=Path, default=DEFAULT_AGENT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--index-output", type=Path, default=DEFAULT_INDEX)
    parser.add_argument(
        "--pattern",
        action="append",
        default=None,
        help="Regex za pun naziv klase; moze vise puta (podrazumevano: ability/booster/logic)",
    )
    parser.add_argument("--abilities-output", type=Path, default=DEFAULT_ABILITIES)
    parser.add_argument(
        "--abilities",
        action="store_true",
        help="Snimi konfiguraciju bustera iz LogicModel-a (trazi aktivnu partiju)",
    )
    parser.add_argument("--index", action="store_true", help="Dodatno snimi pun rva->metod indeks")
    parser.add_argument("--index-only", action="store_true", help="Samo indeks, bez opisa klasa")
    parser.add_argument(
        "--abilities-only", action="store_true", help="Samo konfiguracija bustera"
    )
    parser.add_argument(
        "--piece-logics",
        action="store_true",
        help="Parametri figura koje busteri ostavljaju na tabli (trazi aktivnu partiju)",
    )
    parser.add_argument(
        "--live-abilities",
        action="store_true",
        help="Busteri iz tekuce partije, sa efektivnim parametrima",
    )
    parser.add_argument("--timeout", type=float, default=300.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    patterns = args.pattern or DEFAULT_PATTERNS
    skip_classes = (
        args.index_only or args.abilities_only or args.live_abilities or args.piece_logics
    )

    try:
        adb = find_adb()
        serial = args.serial or discover_serial(adb)
        ensure_frida_server(adb, serial)
        collector = SymbolCollector()
        device, session, script = attach(adb, serial, args.package, args.agent, collector)
    except ReaderError as error:
        print(f"GRESKA: {error}", file=sys.stderr)
        return 2

    try:
        print(f"Zakacen: {collector.meta.get('application')} {collector.meta.get('version')}")
        print(f"Modul:   {collector.meta.get('module_name')} @ {collector.meta.get('module_base')}")

        if not skip_classes:
            print(f"Citam klase koje odgovaraju: {', '.join(patterns)}")
            _export_call(script.exports_sync, ("dump_classes", "dumpClasses", "dumpclasses"), patterns, 40)
            _wait(collector.classes_done, collector, args.timeout, "Dump klasa")
            document = build_symbol_document(collector, patterns)
            write_json(args.output, document, compact=False)
            print(
                f"Snimljeno {document['class_count']} klasa / "
                f"{document['method_count']} metoda -> {args.output}"
            )

        if args.abilities or args.abilities_only:
            print("Citam konfiguraciju bustera iz LogicModel.Instance...")
            _export_call(
                script.exports_sync, ("dump_abilities", "dumpAbilities", "dumpabilities"), 5
            )
            _wait(collector.abilities_done, collector, args.timeout, "Dump bustera")
            document = build_ability_document(collector)
            write_json(args.abilities_output, document, compact=False)
            print(
                f"Snimljeno {document['count']} bustera "
                f"({document['with_params']} sa parametrima) -> {args.abilities_output}"
            )

        if args.live_abilities:
            print("Citam bustere iz tekuce partije...")
            _export_call(
                script.exports_sync,
                ("dump_live_abilities", "dumpLiveAbilities", "dumpliveabilities"),
            )
            _wait(collector.live_done, collector, args.timeout, "Dump zivih bustera")
            document = {
                "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "runtime": collector.meta,
                "players": collector.live_abilities,
            }
            path = args.abilities_output.with_name("ability_live.json")
            write_json(path, document, compact=False)
            print(f"Snimljeno {len(collector.live_abilities)} igraca -> {path}")

        if args.piece_logics:
            print("Citam logiku figura sa table...")
            _export_call(
                script.exports_sync,
                ("dump_piece_logics", "dumpPieceLogics", "dumppiecelogics"),
            )
            _wait(collector.pieces_done, collector, args.timeout, "Dump figura")
            document = {
                "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "runtime": collector.meta,
                "catalogue": collector.piece_catalogue,
                "pieces": collector.piece_logics,
            }
            path = args.abilities_output.with_name("piece_logic_config.json")
            write_json(path, document, compact=False)
            print(
                f"Snimljeno {len(collector.piece_catalogue)} figura iz kataloga "
                f"i {len(collector.piece_logics)} zivih instanci -> {path}"
            )

        if args.index or args.index_only:
            print("Citam pun indeks metoda (traje oko minut)...")
            _export_call(script.exports_sync, ("dump_index", "dumpIndex", "dumpindex"), 5000)
            _wait(collector.index_done, collector, max(args.timeout, 600.0), "Dump indeksa")
            document = build_index_document(collector)
            write_json(args.index_output, document, compact=True)
            print(f"Snimljeno {document['count']} adresa -> {args.index_output}")

        if collector.errors:
            print(f"Upozorenja: {len(collector.errors)} klasa preskoceno")
    except ReaderError as error:
        print(f"GRESKA: {error}", file=sys.stderr)
        return 3
    finally:
        try:
            session.detach()
        except Exception:
            pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
