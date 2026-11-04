"""Offline disassembler for Match Masters' compiled IL2CPP methods.

Step two of the reverse-engineering pipeline. Step one
(``tools/dump_il2cpp_symbols.py``) asked the live runtime where each method's
code starts; this script never touches the game. It works on the ``libil2cpp.so``
that ships inside ``split_config.arm64_v8a.apk``, so it runs with BlueStacks
closed and cannot affect anything.

What it does with a raw ARM64 listing, which on its own is unreadable:

* names the function being called at every ``bl`` (from the method index),
* resolves PC-relative literal loads and prints the actual float/int constant --
  this is where the tuning numbers live (thresholds, multipliers, weights),
* labels ``ldr``/``str`` field accesses with the field name, using the class
  layouts captured in step one,
* and prints a summary per method: which methods it calls, which fields it
  touches, which constants it holds.

Typical use::

    python .\\tools\\il2cpp_disasm.py --extract
    python .\\tools\\il2cpp_disasm.py --method "AbilityEffectHelpers::GetAbilityPositions"
    python .\\tools\\il2cpp_disasm.py --grep "Ability.*Effect" --out Debug\\reverse
"""

from __future__ import annotations

import argparse
import json
import re
import struct
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_APK = PROJECT_ROOT / "setup_new_pc" / "payload" / "apk" / "matchmasters" / "split_config.arm64_v8a.apk"
DEFAULT_LIB = PROJECT_ROOT / "Debug" / "reverse" / "libil2cpp.so"
DEFAULT_SYMBOLS = PROJECT_ROOT / "data" / "il2cpp_symbols.json"
DEFAULT_INDEX = PROJECT_ROOT / "data" / "il2cpp_method_index.json"
DEFAULT_OUT = PROJECT_ROOT / "Debug" / "reverse"

LIB_ENTRY = "lib/arm64-v8a/libil2cpp.so"

# A function that runs past this is either a monster or a bad address; either
# way the listing stops being useful long before.
MAX_FUNCTION_BYTES = 0x4000


class DisasmError(RuntimeError):
    pass


# --------------------------------------------------------------------------
# ELF
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Segment:
    vaddr: int
    offset: int
    filesz: int
    memsz: int


@dataclass(frozen=True)
class Section:
    name: str
    vaddr: int
    offset: int
    size: int


class Elf64:
    """Just enough ELF64 to turn a virtual address into a file offset.

    pyelftools would do this too, but it is not a dependency of this project
    and the part that is needed here is a dozen fields of the program header.
    """

    def __init__(self, data: bytes) -> None:
        if data[:4] != b"\x7fELF" or data[4] != 2:
            raise DisasmError("Nije ELF64 fajl")
        self.data = data
        (
            e_phoff,
            e_shoff,
        ) = struct.unpack_from("<QQ", data, 0x20)
        e_phentsize, e_phnum = struct.unpack_from("<HH", data, 0x36)
        e_shentsize, e_shnum, e_shstrndx = struct.unpack_from("<HHH", data, 0x3A)

        self.segments: list[Segment] = []
        for i in range(e_phnum):
            base = e_phoff + i * e_phentsize
            p_type, _flags = struct.unpack_from("<II", data, base)
            if p_type != 1:  # PT_LOAD
                continue
            p_offset, p_vaddr, _p_paddr, p_filesz, p_memsz = struct.unpack_from(
                "<QQQQQ", data, base + 0x08
            )
            self.segments.append(Segment(p_vaddr, p_offset, p_filesz, p_memsz))
        if not self.segments:
            raise DisasmError("ELF nema PT_LOAD segmente")

        self.sections: dict[str, Section] = {}
        if e_shoff and e_shnum:
            shstr_base = e_shoff + e_shstrndx * e_shentsize
            str_off, str_size = struct.unpack_from("<QQ", data, shstr_base + 0x18)
            strtab = data[str_off : str_off + str_size]
            for i in range(e_shnum):
                base = e_shoff + i * e_shentsize
                sh_name, _sh_type = struct.unpack_from("<II", data, base)
                sh_addr, sh_offset, sh_size = struct.unpack_from("<QQQ", data, base + 0x10)
                end = strtab.find(b"\x00", sh_name)
                name = strtab[sh_name:end].decode("utf-8", "replace")
                self.sections[name] = Section(name, sh_addr, sh_offset, sh_size)

    def offset_for(self, vaddr: int) -> int | None:
        for seg in self.segments:
            if seg.vaddr <= vaddr < seg.vaddr + seg.filesz:
                return seg.offset + (vaddr - seg.vaddr)
        return None

    def read(self, vaddr: int, size: int) -> bytes | None:
        offset = self.offset_for(vaddr)
        if offset is None:
            return None
        chunk = self.data[offset : offset + size]
        return chunk if len(chunk) == size else None

    def read_cstring(self, vaddr: int, limit: int = 96) -> str | None:
        # Deliberately a short read rather than `read()`: a string can sit at
        # the very end of a segment, where asking for the full limit fails.
        offset = self.offset_for(vaddr)
        if offset is None:
            return None
        raw = self.data[offset : offset + limit]
        if not raw:
            return None
        end = raw.find(b"\x00")
        if end <= 1:
            return None
        text = raw[:end]
        if not all(0x20 <= b < 0x7F for b in text):
            return None
        return text.decode("ascii")


def extract_library(apk: Path, destination: Path) -> Path:
    if not apk.exists():
        raise DisasmError(f"APK nije pronadjen: {apk}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(apk) as archive:
        try:
            info = archive.getinfo(LIB_ENTRY)
        except KeyError as error:
            raise DisasmError(f"{LIB_ENTRY} ne postoji u {apk.name}") from error
        with archive.open(info) as source, destination.open("wb") as target:
            while True:
                block = source.read(1 << 20)
                if not block:
                    break
                target.write(block)
    return destination


# --------------------------------------------------------------------------
# Symbols
# --------------------------------------------------------------------------


class MethodIndex:
    """Sorted ``rva -> Class::Method`` map from the live dump."""

    def __init__(self, entries: Sequence[tuple[int, str]]) -> None:
        self.addresses = [rva for rva, _ in entries]
        self.names = [name for _, name in entries]
        self.by_name: dict[str, int] = {}
        for rva, name in entries:
            # Overloads share a name; the first address is a fine default and
            # --rva exists for the cases where it matters.
            self.by_name.setdefault(name, rva)

    @classmethod
    def load(cls, path: Path) -> "MethodIndex":
        if not path.exists():
            return cls([])
        payload = json.loads(path.read_text(encoding="utf-8"))
        entries = sorted(
            ((int(rva, 16), name) for rva, name in payload.get("entries", [])),
            key=lambda item: item[0],
        )
        return cls(entries)

    def __len__(self) -> int:
        return len(self.addresses)

    def name_for(self, rva: int) -> str | None:
        import bisect

        position = bisect.bisect_right(self.addresses, rva) - 1
        if position < 0:
            return None
        start = self.addresses[position]
        if start == rva:
            return self.names[position]
        # Inside a known function: say so, with the offset.
        return f"{self.names[position]}+0x{rva - start:x}"

    def exact(self, rva: int) -> str | None:
        import bisect

        position = bisect.bisect_left(self.addresses, rva)
        if position < len(self.addresses) and self.addresses[position] == rva:
            return self.names[position]
        return None

    def next_after(self, rva: int) -> int | None:
        import bisect

        position = bisect.bisect_right(self.addresses, rva)
        return self.addresses[position] if position < len(self.addresses) else None


@dataclass
class Target:
    """One method selected for disassembly."""

    rva: int
    title: str
    #: Short `Class::Method`, used for the output filename. The full signature
    #: makes a 200 character filename that no shell can complete.
    short: str
    is_instance: bool


@dataclass
class MethodSymbol:
    owner: str
    name: str
    rva: int
    signature: str
    is_static: bool = False


class SymbolTable:
    """The detailed class dump: fields with offsets, methods with addresses."""

    def __init__(self, payload: dict) -> None:
        self.classes: list[dict] = payload.get("classes", [])
        self.methods: list[MethodSymbol] = []
        self.field_names: dict[int, set[str]] = {}
        for klass in self.classes:
            owner = klass.get("full_name") or klass.get("name") or "?"
            for method in klass.get("methods") or []:
                parameters = ", ".join(
                    f"{p.get('type')} {p.get('name')}" for p in method.get("parameters") or []
                )
                self.methods.append(
                    MethodSymbol(
                        owner=owner,
                        name=method.get("name") or "?",
                        rva=int(str(method.get("rva")), 16),
                        signature=f"{method.get('return_type')} {owner}::{method.get('name')}({parameters})",
                        is_static=bool(method.get("is_static")),
                    )
                )
            for field_info in klass.get("fields") or []:
                offset = field_info.get("offset")
                if not isinstance(offset, int) or offset < 0:
                    continue
                label = f"{klass.get('name')}.{field_info.get('name')}"
                self.field_names.setdefault(offset, set()).add(label)

    @classmethod
    def load(cls, path: Path) -> "SymbolTable":
        if not path.exists():
            return cls({})
        return cls(json.loads(path.read_text(encoding="utf-8")))

    def find(self, needle: str, *, regex: bool) -> list[MethodSymbol]:
        if regex:
            pattern = re.compile(needle, re.IGNORECASE)
            return [m for m in self.methods if pattern.search(f"{m.owner}::{m.name}")]
        needle_lower = needle.lower()
        exact = [m for m in self.methods if f"{m.owner}::{m.name}".lower() == needle_lower]
        if exact:
            return exact
        return [m for m in self.methods if needle_lower in f"{m.owner}::{m.name}".lower()]

    def layout(self, class_name: str) -> dict[int, str]:
        wanted = class_name.lower()
        for klass in self.classes:
            names = {str(klass.get("name") or "").lower(), str(klass.get("full_name") or "").lower()}
            if wanted in names:
                return {
                    field_info["offset"]: field_info["name"]
                    for field_info in klass.get("fields") or []
                    if isinstance(field_info.get("offset"), int) and field_info["offset"] >= 0
                }
        return {}


# --------------------------------------------------------------------------
# Disassembly
# --------------------------------------------------------------------------


@dataclass
class Listing:
    title: str
    rva: int
    size: int
    lines: list[str] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)
    constants: list[str] = field(default_factory=list)
    fields_touched: list[str] = field(default_factory=list)

    def render(self) -> str:
        out = [f"; {self.title}", f"; rva 0x{self.rva:x}  size {self.size} bytes", ""]
        out.extend(self.lines)
        if self.calls:
            out += ["", "; --- poziva ---"] + [f";   {c}" for c in dict.fromkeys(self.calls)]
        if self.fields_touched:
            out += ["", "; --- polja ---"] + [f";   {f}" for f in dict.fromkeys(self.fields_touched)]
        if self.constants:
            out += ["", "; --- konstante ---"] + [f";   {c}" for c in dict.fromkeys(self.constants)]
        return "\n".join(out) + "\n"


def _format_float(raw: bytes) -> str | None:
    if len(raw) == 4:
        value = struct.unpack("<f", raw)[0]
    elif len(raw) == 8:
        value = struct.unpack("<d", raw)[0]
    else:
        return None
    if value != value or abs(value) in (float("inf"),):
        return None
    if abs(value) > 1e12 or (value != 0 and abs(value) < 1e-9):
        return None
    return f"{value:g}"


class Disassembler:
    def __init__(
        self,
        elf: Elf64,
        index: MethodIndex,
        symbols: SymbolTable,
        *,
        layout: dict[int, str] | None = None,
    ) -> None:
        try:
            import capstone
        except ImportError as error:  # pragma: no cover - dependency missing
            raise DisasmError("Nedostaje paket 'capstone' (pip install capstone)") from error
        self.capstone = capstone
        self.md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)
        self.md.detail = True
        self.elf = elf
        self.index = index
        self.symbols = symbols
        self.layout = layout or {}
        # A `[sp, #0x28]` access is a local variable, never a field.
        self.stack_registers = {
            capstone.arm64.ARM64_REG_SP,
            getattr(capstone.arm64, "ARM64_REG_WSP", capstone.arm64.ARM64_REG_SP),
        }

    def function_bounds(self, rva: int) -> tuple[int, int]:
        end = self.index.next_after(rva)
        if end is None or end - rva > MAX_FUNCTION_BYTES:
            end = rva + MAX_FUNCTION_BYTES
        return rva, end

    def _annotate_literal(self, target: int) -> str | None:
        """A PC-relative load: print the constant that actually gets loaded."""
        raw8 = self.elf.read(target, 8)
        if raw8 is None:
            return None
        as_float = _format_float(raw8[:4])
        as_double = _format_float(raw8)
        as_int = struct.unpack("<q", raw8)[0]
        parts = [f"=0x{as_int & 0xFFFFFFFFFFFFFFFF:x}"]
        if -1 << 31 <= as_int < 1 << 31:
            parts.append(f"({as_int})")
        if as_float is not None:
            parts.append(f"f32={as_float}")
        if as_double is not None:
            parts.append(f"f64={as_double}")
        return " ".join(parts)

    def _track_this(self, insn, this_registers: set[int]) -> None:
        """Follow `this` through register copies, drop it on any other write."""
        capstone = self.capstone
        if insn.mnemonic == "mov" and len(insn.operands) == 2:
            destination, source = insn.operands
            if (
                destination.type == capstone.arm64.ARM64_OP_REG
                and source.type == capstone.arm64.ARM64_OP_REG
            ):
                if source.reg in this_registers:
                    this_registers.add(destination.reg)
                else:
                    this_registers.discard(destination.reg)
                return
        try:
            _read, written = insn.regs_access()
        except Exception:
            # Without register access info the safe move is to forget
            # everything but the entry register.
            return
        for register in written:
            this_registers.discard(register)

    def disassemble(self, rva: int, title: str, *, is_instance: bool = True) -> Listing:
        start, end = self.function_bounds(rva)
        code = self.elf.read(start, end - start)
        if code is None:
            raise DisasmError(f"rva 0x{rva:x} nije unutar ucitanog segmenta")

        listing = Listing(title=title, rva=start, size=len(code))
        capstone = self.capstone
        # adrp target per register, so an `adrp`/`add` pair can be resolved.
        pages: dict[int, int] = {}
        # Registers currently holding `this`. An IL2CPP instance method gets it
        # in x0, and the compiler copies it around. Without tracking this, every
        # `ldr w8, [xN, #0x20]` looked like a field of the class being studied --
        # including loads through unrelated objects and through sp.
        this_registers: set[int] = set()
        if is_instance:
            this_registers.add(capstone.arm64.ARM64_REG_X0)

        for insn in self.md.disasm(code, start):
            note = ""
            mnemonic = insn.mnemonic

            if mnemonic == "adrp" and insn.operands:
                register = insn.operands[0].reg
                pages[register] = insn.operands[1].imm
                note = f"page 0x{insn.operands[1].imm:x}"
            elif mnemonic in {"add", "ldr", "ldrb", "ldrh"} and len(insn.operands) >= 2:
                source = insn.operands[-1]
                base_register = None
                displacement = 0
                if source.type == capstone.arm64.ARM64_OP_MEM:
                    base_register = source.mem.base
                    displacement = source.mem.disp
                elif mnemonic == "add" and source.type == capstone.arm64.ARM64_OP_IMM:
                    base_register = insn.operands[1].reg if len(insn.operands) > 2 else None
                    displacement = source.imm
                if base_register in pages:
                    absolute = pages[base_register] + displacement
                    text = self.elf.read_cstring(absolute)
                    note = f"-> 0x{absolute:x}" + (f' "{text}"' if text else "")
                    if text:
                        listing.constants.append(f'"{text}" @ 0x{absolute:x}')
                elif source.type == capstone.arm64.ARM64_OP_MEM and base_register not in self.stack_registers:
                    if base_register in this_registers and self.layout:
                        name = self.layout.get(displacement)
                        if name:
                            note = f"field {name}"
                            listing.fields_touched.append(f"+0x{displacement:x} {name}")
                    else:
                        # Some other object: offer candidates, never a verdict.
                        guesses = self.symbols.field_names.get(displacement)
                        if guesses and len(guesses) <= 3:
                            note = "maybe " + " / ".join(sorted(guesses))

            # LDR literal is `ldr <reg>, <abs addr>` -- exactly two operands and
            # no memory operand. Post-indexed loads (`ldr x8, [x20], #8`) also
            # end in an immediate, and reading that as an address produced
            # convincing nonsense until this guard was added.
            if (
                mnemonic in {"ldr", "ldrsw"}
                and len(insn.operands) == 2
                and insn.operands[0].type == capstone.arm64.ARM64_OP_REG
                and insn.operands[1].type == capstone.arm64.ARM64_OP_IMM
                and not any(op.type == capstone.arm64.ARM64_OP_MEM for op in insn.operands)
            ):
                annotation = self._annotate_literal(insn.operands[1].imm)
                if annotation:
                    note = annotation
                    listing.constants.append(f"0x{insn.address:x}: {annotation}")

            if mnemonic in {"bl", "b", "blr"} and insn.operands:
                operand = insn.operands[0]
                if operand.type == capstone.arm64.ARM64_OP_IMM:
                    target = operand.imm
                    # Only an exact hit names a call. An interior match would
                    # read as "SomeMethod+0x317260", which is not a fact about
                    # this call, just the nearest symbol below it.
                    name = self.index.exact(target)
                    if name:
                        note = name
                        if mnemonic == "bl":
                            listing.calls.append(name)
                    elif not (start <= target < start + listing.size):
                        note = f"-> 0x{target:x}"
                        if mnemonic == "bl":
                            listing.calls.append(f"0x{target:x} (nepoznato)")

            # Immediates worth collecting: thresholds and counts, not stack
            # frame arithmetic, hence the `sp` exclusion.
            if (
                mnemonic in {"mov", "movz", "movk", "cmp", "add", "sub"}
                and insn.operands
                and "sp" not in insn.op_str
            ):
                last = insn.operands[-1]
                if last.type == capstone.arm64.ARM64_OP_IMM and abs(last.imm) > 8:
                    listing.constants.append(f"0x{insn.address:x}: {mnemonic} #{last.imm} (0x{last.imm:x})")

            self._track_this(insn, this_registers)

            text = f"  0x{insn.address:08x}  {insn.mnemonic:<8} {insn.op_str}"
            listing.lines.append(f"{text:<58} ; {note}" if note else text)

            if mnemonic == "ret" and self.index.exact(insn.address + 4) is not None:
                break

        return listing


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------



def find_callers(elf: Elf64, index: MethodIndex, target: int) -> list[tuple[int, str]]:
    """Every `bl` that lands exactly on `target`.

    IL2CPP has no relocation table for internal calls, so the only way to find
    who calls a method is to sweep the executable segments. A BL is one word
    (`100101` + signed imm26 in units of 4 bytes), so this needs no
    disassembler -- decoding 17 million words directly is a few seconds, while
    running capstone over the same range is minutes.
    """
    import array

    hits: list[tuple[int, str]] = []
    for segment in elf.segments:
        if segment.filesz < 4:
            continue
        words = array.array("I")
        words.frombytes(elf.data[segment.offset : segment.offset + (segment.filesz & ~3)])
        if array.array("I", [1]).tobytes()[0] != 1:  # pragma: no cover - big endian host
            words.byteswap()
        for position, word in enumerate(words):
            if word >> 26 != 0b100101:
                continue
            offset = word & 0x03FFFFFF
            if offset & 0x02000000:
                offset -= 0x04000000
            address = segment.vaddr + position * 4
            if address + offset * 4 == target:
                hits.append((address, index.name_for(address) or "?"))
    return hits


def resolve_targets(
    args: argparse.Namespace, symbols: SymbolTable, index: MethodIndex
) -> list[Target]:
    targets: list[Target] = []
    if args.rva:
        for raw in args.rva:
            rva = int(raw, 16) if raw.lower().startswith("0x") else int(raw)
            # An address given by hand carries no signature, so assume the
            # common case (instance method) for `this` tracking.
            name = index.exact(rva) or f"rva_0x{rva:x}"
            targets.append(Target(rva, name, name, True))
    for needle in args.method or []:
        found = symbols.find(needle, regex=False)
        if not found:
            print(f"UPOZORENJE: metod nije pronadjen: {needle}", file=sys.stderr)
        targets.extend(
            Target(m.rva, m.signature, f"{m.owner}::{m.name}", not m.is_static) for m in found
        )
    for pattern in args.grep or []:
        found = symbols.find(pattern, regex=True)
        if not found:
            print(f"UPOZORENJE: nema poklapanja za: {pattern}", file=sys.stderr)
        targets.extend(
            Target(m.rva, m.signature, f"{m.owner}::{m.name}", not m.is_static) for m in found
        )
    # Same method reached through two selectors is one listing.
    seen: set[int] = set()
    unique: list[Target] = []
    for target in targets:
        if target.rva in seen:
            continue
        seen.add(target.rva)
        unique.append(target)
    return unique


def safe_filename(title: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", title)
    return cleaned[:120].strip("_") or "listing"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apk", type=Path, default=DEFAULT_APK)
    parser.add_argument("--lib", type=Path, default=DEFAULT_LIB)
    parser.add_argument("--symbols", type=Path, default=DEFAULT_SYMBOLS)
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--unique-names", action="store_true", help="Dodaj RVA imenu fajla da overload-i ne prepisuju listing")
    parser.add_argument("--extract", action="store_true", help="Izvuci libil2cpp.so iz APK-a pa izadji")
    parser.add_argument("--method", action="append", help="Naziv metoda, npr. Klasa::Metod")
    parser.add_argument("--grep", action="append", help="Regex nad Klasa::Metod")
    parser.add_argument("--rva", action="append", help="Direktna adresa (hex)")
    parser.add_argument("--layout", default=None, help="Klasa cija imena polja se koriste za anotaciju")
    parser.add_argument("--list", action="store_true", help="Ispisi poznate metode i izadji")
    parser.add_argument(
        "--xrefs",
        default=None,
        help="Nadji sve bl pozive ka metodu (naziv ili hex adresa) pa izadji",
    )
    parser.add_argument("--stdout", action="store_true", help="Ispisi listing umesto snimanja")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.extract:
        try:
            path = extract_library(args.apk, args.lib)
        except DisasmError as error:
            print(f"GRESKA: {error}", file=sys.stderr)
            return 2
        print(f"Izvuceno: {path} ({path.stat().st_size / 1e6:.1f} MB)")
        return 0

    symbols = SymbolTable.load(args.symbols)
    if args.list:
        for method in sorted(symbols.methods, key=lambda m: (m.owner, m.name)):
            print(f"0x{method.rva:08x}  {method.owner}::{method.name}")
        return 0

    if not symbols.methods:
        print(
            f"GRESKA: nema simbola u {args.symbols}; pokreni tools/dump_il2cpp_symbols.py",
            file=sys.stderr,
        )
        return 2
    if not args.lib.exists():
        print(f"GRESKA: nema {args.lib}; pokreni sa --extract", file=sys.stderr)
        return 2

    index = MethodIndex.load(args.index)
    if not len(index):
        print(
            "UPOZORENJE: nema indeksa metoda; granice funkcija i imena poziva su nepoznata "
            "(pokreni dump_il2cpp_symbols.py --index)",
            file=sys.stderr,
        )

    elf = Elf64(args.lib.read_bytes())

    if args.xrefs:
        raw = args.xrefs
        if raw.lower().startswith("0x"):
            target = int(raw, 16)
        else:
            found = symbols.find(raw, regex=False)
            if not found:
                print(f"GRESKA: metod nije pronadjen: {raw}", file=sys.stderr)
                return 2
            target = found[0].rva
            print(f"{found[0].owner}::{found[0].name} @ 0x{target:x}")
        callers = find_callers(elf, index, target)
        if not callers:
            print("Nema pronadjenih poziva (moguce je da se zove virtuelno, kroz blr)")
        for address, name in callers:
            print(f"  0x{address:08x}  {name}")
        return 0

    layout = symbols.layout(args.layout) if args.layout else None
    disassembler = Disassembler(elf, index, symbols, layout=layout)

    targets = resolve_targets(args, symbols, index)
    if not targets:
        print("Nista nije izabrano; koristi --method, --grep ili --rva", file=sys.stderr)
        return 2

    args.out.mkdir(parents=True, exist_ok=True)
    for target in targets:
        try:
            listing = disassembler.disassemble(
                target.rva, target.title, is_instance=target.is_instance
            )
        except DisasmError as error:
            print(f"PRESKOCENO {target.short}: {error}", file=sys.stderr)
            continue
        if args.stdout:
            print(listing.render())
        else:
            suffix = f"__{target.rva:08x}" if args.unique_names else ""
            path = args.out / f"{safe_filename(target.short)}{suffix}.asm"
            path.write_text(listing.render(), encoding="utf-8")
            print(f"{target.short}  ->  {path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
