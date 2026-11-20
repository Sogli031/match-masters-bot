"""Resolve raw addresses from an .asm listing to Class::Method names.

    python tools/sym_at.py 0x3d25af4 0x3d34d04 ...

Uses data/il2cpp_method_index.json (exact rva -> name), the same index
tools/il2cpp_disasm.py names calls with.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    payload = json.loads((ROOT / "data/il2cpp_method_index.json").read_text(encoding="utf-8"))
    table = {}
    for rva, name in payload.get("entries", []):
        table[int(rva, 16)] = name
    for raw in args:
        addr = int(raw, 16) if raw.lower().startswith("0x") else int(raw, 16)
        print(f"{addr:#x}  {table.get(addr, '?')}")


if __name__ == "__main__":
    main()
