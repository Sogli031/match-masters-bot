"""Svako pokretanje metle u snimku prema svim potezima (tools/analyze_research.try_transition), port ukljucen.

    python tools/broom_check.py Debug/research/FOLDER
"""
import json, sys, os, io, contextlib
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT)); os.chdir(ROOT)
import move_strategy as ms
import refill_monitor as rm
from tools.analyze_research import capture_from, observed, try_transition
ms.SWEEP_EXACT_PORTED = True
folder = Path(sys.argv[1])
files = sorted(folder.glob("[0-9][0-9][0-9].json"))
recs = [json.loads(f.read_text(encoding="utf-8")) for f in files]
for i in range(len(recs)-1):
    a, b = recs[i], recs[i+1]
    cnt=lambda r: sum(row.count(ms.SPECIAL_SWEEP_SE_BROOM) for row in r["special_board"])
    if not cnt(b) < cnt(a): continue
    want = observed(b)
    with contextlib.redirect_stdout(io.StringIO()):
        matches, closest, reasons = try_transition(capture_from(a), want)
    if matches:
        print(files[i].name, "TACNO", matches[0])
    else:
        c = closest or {}
        print(files[i].name, "promasaj", c.get("action"), "rng igra/sim", c.get("rng"), "polja", c.get("cells"), "spec", c.get("specials"), "| razlozi", dict(reasons) if not closest else "")
