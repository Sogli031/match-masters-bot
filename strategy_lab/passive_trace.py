"""Bounded passive Frida trace, with build/code checks and explicit coverage.

There is deliberately no Billie Boom mode: an Interceptor on
``BillieBoom::SuckAndConvertByScoreTarget``/``SuckAndConvert`` SIGSEGVs
libhoudini (BlueStacks ARM->x86) as soon as the booster is activated -- measured
twice, with 5 hooks and with only those 2, while the same activation without a
trace works. That data has to come from code analysis
(``strategy_lab/vtable_probe.py``) or from recordings instead.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools import matchmasters_board_reader as reader  # noqa: E402

JAVASCRIPT = Path(__file__).with_name("passive_trace.js")
PROOF_PATH = PROJECT_ROOT / "Debug" / "strategy_lab" / "passive" / "code_proof.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "Debug" / "strategy_lab" / "passive" / "trace.jsonl"
LAYOUT = {"seed": 0x14, "matrix": 0x18, "index": 0x14 + 624 * 4, "counter": 0x14 + 624 * 4 + 4}
METHODS = {"Generate": "RandomWrapper.Generate", "Next": "RandomWrapper.Next"}


def load_code_proof() -> list[dict[str, Any]]:
    if not PROOF_PATH.exists():
        raise SystemExit(f"missing code proof {PROOF_PATH}")
    hooks = json.loads(PROOF_PATH.read_text(encoding="utf-8"))
    if not isinstance(hooks, list) or not hooks:
        raise SystemExit(f"{PROOF_PATH} must hold a non-empty list")
    for hook in hooks:
        name = hook.get("name")
        if name not in METHODS:
            raise SystemExit(f"unknown hook {name!r} in {PROOF_PATH}")
        hook.setdefault("label", METHODS[name])
        hook.setdefault("rng", True)
    return hooks


def module_size(serial: str, pid: int) -> int:
    text = reader.adb_shell(reader.find_adb(), serial, f"cat /proc/{pid}/maps")
    for line in text.splitlines():
        if line.rstrip().endswith("/libil2cpp.so"):
            start, end = line.split()[0].split("-")
            return int(end, 16) - int(start, 16)
    raise SystemExit("libil2cpp.so not mapped in the game process")


def configuration(with_rng: bool, max_events: int) -> dict[str, Any]:
    hooks = load_code_proof()
    if not with_rng:
        for hook in hooks:
            hook["rng"] = False
    return {"hooks": hooks, "rng": LAYOUT, "max_events": max_events, "module_size": None}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=10.0, help="how long to observe (<=60)")
    parser.add_argument("--allow-live", action="store_true", help="required: attaches to the running game")
    parser.add_argument("--no-rng", action="store_true", help="skip RNG field reads")
    parser.add_argument("--max-events", type=int, default=2000)
    parser.add_argument("--directory", type=Path, default=None, help="output directory")
    args = parser.parse_args(argv)

    if not args.allow_live:
        raise SystemExit("refusing to attach without --allow-live")
    if not 0 < args.seconds <= 60:
        raise SystemExit("--seconds must be in (0, 60]")

    import frida  # noqa: PLC0415

    adb = reader.find_adb()
    serial = reader.discover_serial(adb)
    pid = reader.game_pid(adb, serial, reader.DEFAULT_PACKAGE)
    if pid is None:
        raise SystemExit("game is not running")
    reader.ensure_frida_server(adb, serial)

    config = configuration(not args.no_rng, args.max_events)
    config["module_size"] = module_size(serial, pid)

    device = frida.get_device_manager().add_remote_device(f"127.0.0.1:{reader.FRIDA_PORT}")
    session = device.attach(pid)
    script = session.create_script(JAVASCRIPT.read_text(encoding="utf-8"))
    events: list[dict[str, Any]] = []

    def on_message(message: Any, data: Any) -> None:
        if message.get("type") == "error":
            events.append({"phase": "error", "error": message.get("description")})
            return
        payload = message.get("payload") or {}
        if isinstance(payload, dict):
            if payload.get("kind") == "batch":
                events.extend(payload["events"])
            else:
                events.append(payload)

    script.on("message", on_message)
    script.load()
    script.exports_sync.start(config)
    try:
        time.sleep(args.seconds)
    finally:
        summary = script.exports_sync.stop()
        session.detach()

    output = (args.directory or DEFAULT_OUTPUT.parent) / DEFAULT_OUTPUT.name
    if output.exists():
        stem, index = output.stem, 1
        while output.exists():
            index += 1
            output = output.with_name(f"{stem}-{index}.jsonl")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")
    print(json.dumps({"output": str(output), "events": len(events), **summary}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
