"""Passive probe: which method Billie Boom's pair pick calls through the ability's
vtable slot 0x218 (the `w28` term of `value = clone.Score + w28 - live.Score`).

No hooks anywhere: an Interceptor on `SuckAndConvertByScoreTarget` SIGSEGVs
libhoudini on this BlueStacks build (see Debug/booster_inventory/billie_status.md),
so the method pointer is read straight out of memory and then resolved against
the dump of the running build.

How the address is found (from the decompiled pick loop):
    ldr x8, [x22]          ; x22 = ability object -> Il2CppClass*
    ldr x9, [x8, #0x218]   ; virtual invoke data: method pointer
    ldr x2, [x8, #0x220]   ;                  method info
so `[klass + 0x218]` is the entry the pick actually calls on the clone.

Usage (game in a match with Billie Boom equipped, activation NOT needed):

    python strategy_lab/vtable_probe.py            # needs --allow-live
    python strategy_lab/vtable_probe.py --allow-live --json out.json
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

from tools import matchmasters_board_reader as reader  # noqa: E402

SYMBOLS_PATH = PROJECT_ROOT / "data" / "il2cpp_symbols.json"
INDEX_PATH = PROJECT_ROOT / "data" / "il2cpp_method_index.json"
OUTPUT_PATH = PROJECT_ROOT / "Debug" / "booster_inventory" / "billie_vtable.json"


def normalize_rva(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if not text:
        return None
    return int(text, 16) if text.lower().startswith("0x") else int(text)


def load_names(index_path: Path = INDEX_PATH) -> dict[int, list[str]]:
    """rva -> every name the symbol dump gave that address."""
    data = json.loads(index_path.read_text(encoding="utf-8"))
    names: dict[int, list[str]] = {}
    for rva, name in data["entries"]:
        names.setdefault(normalize_rva(rva), []).append(name)
    return names


def load_class_methods(symbols_path: Path = SYMBOLS_PATH, klass: str = "BillieBoom") -> dict[int, str]:
    data = json.loads(symbols_path.read_text(encoding="utf-8"))
    entry = next((c for c in data["classes"] if c["name"] == klass), None)
    if entry is None:
        return {}
    return {normalize_rva(m["rva"]): m["name"] for m in entry["methods"]}


def resolve(rva: int | None, names: dict[int, list[str]]) -> list[str]:
    if rva is None:
        return []
    return sorted(set(names.get(rva, [])))


def attach_and_probe(serial_timeout: float = 20.0) -> dict[str, Any]:
    import frida  # noqa: PLC0415

    adb = reader.find_adb()
    serial = reader.discover_serial(adb)
    pid = reader.game_pid(adb, serial, reader.DEFAULT_PACKAGE)
    if pid is None:
        raise SystemExit("game is not running")
    reader.ensure_frida_server(adb, serial)

    device = frida.get_device_manager().add_remote_device(f"127.0.0.1:{reader.FRIDA_PORT}")
    # The split APK holds ARM64 Unity/IL2CPP code; BlueStacks runs it through its
    # native bridge, so the real process is the emulated realm (same as the reader).
    session = device.attach(pid, realm="emulated")
    ready = threading.Event()
    errors: list[str] = []
    try:
        script = session.create_script(reader.DEFAULT_AGENT.read_text(encoding="utf-8"))

        def on_message(message: Any, _data: Any) -> None:
            if message.get("type") == "error":
                errors.append(str(message.get("description")))
                ready.set()
                return
            payload = message.get("payload") or {}
            if isinstance(payload, dict) and payload.get("type") == "ready":
                ready.set()

        script.on("message", on_message)
        script.load()
        if not ready.wait(serial_timeout):
            raise SystemExit("agent did not report ready: " + (errors[-1] if errors else "timeout"))
        result = reader._export_call(script.exports_sync, ("billieVtable", "billie_vtable"))
    finally:
        session.detach()
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-live", action="store_true", help="required: reads the running game's memory")
    parser.add_argument("--json", type=Path, default=OUTPUT_PATH)
    args = parser.parse_args(argv)
    if not args.allow_live:
        raise SystemExit("refusing to read live memory without --allow-live")
    # Windows consoles default to cp1252 and cannot print the diacritics below.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

    result = attach_and_probe()
    names = load_names()
    methods = load_class_methods()

    print(f"modul:      {result['module_base']}  (klass {result['klass']})")
    print(f"iz meča:    {result['from_match']}   instanci iz heap-a: {result['heap_instances']}")
    factor = result.get("logic_factor")
    if factor is None:
        print("  [logic+0x48]->0x270: nema GameLogic-a (nisi u meču)")
    else:
        print(f"  [logic+0x48]->0x270 = {factor.get('factor')}   (logic {factor.get('logic')}, "
              f"holder {factor.get('holder')}{factor.get('error', '')})")
    records = result.get("records") or []
    if not records:
        print("nema BillieBoom instance: uđi u meč sa Billie Boom-om pa pokreni ponovo.")
    for record in records:
        if "error" in record:
            print(f"  greška: {record['error']}")
            continue
        slot = normalize_rva(record.get("slot_0x218"))
        info = normalize_rva(record.get("info_0x220"))
        print(f"  instanca {record['instance']}  klass {record['klass']}")
        print(f"    [klass+0x218] = {record['slot_0x218']}   [klass+0x220] = {record['info_0x220']}")
        print(f"    [ability+0x20] = {record.get('ability_0x20')}  (Fix64 "
              f"{record.get('ability_0x20_fix64')})")
        found = resolve(slot, names)
        if found:
            for name in found[:8]:
                print(f"      -> {name}")
            if len(found) > 8:
                print(f"      -> (+{len(found) - 8} još imena na istoj adresi)")
        else:
            print("      -> nema imena u simbolima (adresa van indeksa ili u drugom modulu)")
        if info in methods:
            print(f"      BillieBoom::{methods[info]} stoji na 0x220")

    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(
        json.dumps(
            {
                "probe": result,
                "resolved": {
                    record.get("instance"): resolve(normalize_rva(record.get("slot_0x218")), names)
                    for record in records
                    if "error" not in record
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"zapisano: {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
