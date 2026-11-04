"""One-shot field-only LogicModel configuration capture, without heap scans."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.dump_il2cpp_symbols import SymbolCollector, attach, DEFAULT_AGENT
from tools.matchmasters_board_reader import find_adb, discover_serial, ensure_frida_server, DEFAULT_PACKAGE


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "data/engine_config.json")
    parser.add_argument("--serial")
    args = parser.parse_args()
    adb = find_adb()
    serial = discover_serial(adb, args.serial)
    ensure_frida_server(adb, serial)
    collector = SymbolCollector()
    session = script = None
    try:
        _, session, script = attach(adb, serial, DEFAULT_PACKAGE, DEFAULT_AGENT, collector)
        result = script.exports_sync.dump_engine_config()
        document = {"captured_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                    "runtime": collector.meta, **result}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Saved: {args.output}", flush=True)
        print(json.dumps(result.get("spawning_config"), ensure_ascii=False, indent=2), flush=True)
    finally:
        if script is not None:
            script.unload()
        if session is not None:
            session.detach()


if __name__ == "__main__":
    main()
