"""Reproduce Cleo ARM64 relocation/literal evidence without running the game.

python tools/reverse_helpers/cleo_evidence.py [--out PATH]
No managed calls or live process attachment. Metadata v39 uses header triples
(offset, byte length, count); encoded IL2CPP usage references use tag + index<<1|1.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from il2cpp_disasm import Elf64


def evidence(library, metadata):
    binary = library.read_bytes()
    blob = metadata.read_bytes()
    elf = Elf64(binary)
    section = elf.sections[".rela.dyn"]
    relocs = {offset: (info, addend) for offset, info, addend in
              struct.iter_unpack("<QQq", elf.read(section.vaddr, section.size))}

    def chain(address):
        info, addend = relocs[address]
        assert info == 0x403, "expected AArch64 RELATIVE relocation"
        encoded, = struct.unpack("<Q", elf.read(addend, 8))
        return {"global_rva": hex(address), "relocation_kind": "R_AARCH64_RELATIVE",
                "relocation_addend": hex(addend), "usage_bytes_hex": elf.read(addend, 8).hex(),
                "encoded_usage": hex(encoded), "usage_tag": encoded >> 29,
                "usage_index": (encoded & 0x1FFFFFFF) >> 1}

    magic, version = struct.unpack_from("<II", blob)
    assert (magic, version) == (0xFAB11BAF, 39)
    offsets, offsets_size, offsets_count = struct.unpack_from("<III", blob, 8)
    strings, strings_size, strings_count = struct.unpack_from("<III", blob, 20)
    assert offsets_count * 4 == offsets_size
    template = chain(0x70993D8)
    assert template["usage_tag"] == 5
    index = template["usage_index"]
    assert 0 <= index < strings_count
    begin, end = struct.unpack_from("<II", blob, offsets + index * 4)
    assert 0 <= begin <= end <= strings_size
    raw = blob[strings + begin:strings + end]
    # Literal offsets include the null terminator at the end of each string.
    text = raw.rstrip(b"\x00").decode("utf-8")
    assert text == "{0}_PieceUsesThisTurnOrigin_{1}", repr(text)
    template.update(literal_index=index, literal_pool_offset=begin,
                    literal_file_offset=strings + begin, literal_bytes_hex=raw.hex(), literal=text)
    methods = {
        "SwapPerformed": (0x5AE2600, 7316),
        "ConvertToPiece": (0x5AE24A8, 192),
        "OverrideCloneAmount": (0x5AE25F0, 8),
        "OverrideChanceToCreateExtraMove": (0x5AE25F8, 8),
        "PieceUsesThisTurnKey": (0x5AED204, 192),
        "Chance": (0x5AF5C4C, 60),
    }
    return {"evidence_type": "static ELF relocation and metadata bytes",
            "library": str(library.resolve()), "library_sha256": hashlib.sha256(binary).hexdigest(),
            "metadata": str(metadata.resolve()), "metadata_sha256": hashlib.sha256(blob).hexdigest(),
            "metadata_version": version,
            "literal_header": {"offsets": offsets, "offsets_size": offsets_size,
                               "offsets_count": offsets_count, "data": strings,
                               "data_size": strings_size, "data_count": strings_count},
            "uses_key_template": template,
            "uses_key_type_arguments": [chain(0x702D1B0), chain(0x70993D0)],
            "selector_predicate_method_references": [chain(a) for a in
                (0x70991B0, 0x70991B8, 0x70991D0, 0x70991D8, 0x70991E0)],
            "method_code": {name: {"rva": hex(address), "size": size,
                                   "sha256": hashlib.sha256(elf.read(address, size)).hexdigest()}
                            for name, (address, size) in methods.items()},
            "limitations": ["Static evidence does not demonstrate gameplay parity.",
                            "Type usage indices require metadata registration to resolve names; typed enum names also come from captured symbols."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--lib", type=Path, default=ROOT / "Debug/strategy_lab/native-current/libil2cpp.so")
    parser.add_argument("--metadata", type=Path, default=ROOT / "Debug/reverse/global-metadata.dat")
    parser.add_argument("--out", type=Path,
                        default=ROOT / "Debug/analysis/cleo_arm64_evidence_20261104.json")
    args = parser.parse_args()
    result = evidence(args.lib, args.metadata)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(args.out), "template": result["uses_key_template"]["literal"],
                      "literal_index": result["uses_key_template"]["literal_index"],
                      "library_sha256": result["library_sha256"]}))


if __name__ == "__main__":
    main()
