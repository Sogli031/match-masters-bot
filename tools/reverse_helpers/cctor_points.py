"""Pull Point(x, y) static arrays out of a .cctor: python cctor_points.py <rva> <size> <class full name>"""
import sys, json, capstone
from pathlib import Path
ROOT = Path(r"C:\Users\PC\Desktop\memory gui")
rva, size, cls = int(sys.argv[1], 16), int(sys.argv[2]), sys.argv[3]
POINT_CTOR = 0x5718ae8
d = json.load(open(ROOT / "data/il2cpp_symbols.json", encoding="utf-8"))
klass = next(c for c in d["classes"] if c["full_name"] == cls)
statics = {f["offset"]: f["name"] for f in klass["fields"] if f["is_static"]}
data = open(ROOT / "Debug/reverse/libil2cpp.so", "rb")
data.seek(rva - 0x4000); code = data.read(size)
md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM); md.detail = True
regs = {}; cur = []; statics_reg = set(); out = {}
for ins in md.disasm(code, rva):
    m, ops = ins.mnemonic, ins.op_str.replace(" ", "").split(",")
    if m in ("mov", "movz", "movn") and len(ops) == 2:
        dst = ops[0]
        if ops[1].startswith("#"):
            regs[dst[1:]] = int(ops[1][1:], 0)
        elif ops[1] in ("wzr", "xzr"):
            regs[dst[1:]] = 0
        else:
            regs.pop(dst[1:], None)
    elif m == "bl":
        tgt = int(ops[0][1:], 16)
        if tgt == POINT_CTOR:
            def sv(v):
                v &= 0xFFFFFFFF
                return v - (1 << 32) if v & 0x80000000 else v
            cur.append((sv(regs.get("1", 999)), sv(regs.get("2", 999))))
        for r in ("0", "1", "2", "3"):
            regs.pop(r, None)
    elif m == "ldr" and len(ops) == 3 and ops[2] == "#0xb8]":
        statics_reg.add(ops[0])
    elif m == "str" and len(ops) >= 2 and ops[1].startswith("[") and ops[1][1:] in statics_reg:
        off = int(ops[2][1:-1], 0) if len(ops) == 3 else 0
        name = statics.get(off, hex(off))
        out[name] = cur; cur = []
for name, pts in out.items():
    print(f"{name:28} {len(pts):3}  {pts}")
