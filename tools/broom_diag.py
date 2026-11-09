"""Svaka 4 smera metle za svako pokretanje u snimku: RNG, polja i specijali prema igri.

    python tools/broom_diag.py Debug/research/FOLDER [008 021 ...]

PRE=n menja SWEEP_PRE_REFILL_DRAWS, SEG=1 ukljucuje SWEEP_BROOM_LINE_SEGMENT.
"""
import json, sys, os, io, contextlib
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT)); os.chdir(ROOT)
import move_strategy as ms
from tools.analyze_research import capture_from, observed, grid
from strategy_lab import simulation as sim
from simulator_capture import lab_move, capture_mode
ms.SWEEP_EXACT_PORTED = True
ms.SWEEP_PRE_REFILL_DRAWS = int(os.environ.get("PRE","1"))
ms.SWEEP_BROOM_LINE_SEGMENT = os.environ.get("SEG")=="1"
folder = Path(sys.argv[1]); only = sys.argv[2:] 
files = sorted(folder.glob("[0-9][0-9][0-9].json"))
recs = [json.loads(f.read_text(encoding="utf-8")) for f in files]
B = ms.SPECIAL_SWEEP_SE_BROOM
for i in range(len(recs)-1):
    a, b = recs[i], recs[i+1]
    cnt=lambda r: sum(row.count(B) for row in r["special_board"])
    if not cnt(b) < cnt(a): continue
    if only and files[i].stem not in only: continue
    cap = capture_from(a); want = observed(b)
    sim.PREFIX_MODES = set(sim.PREFIX_MODES) | {capture_mode(cap["profile"]).value}
    lab = lab_move(cap, thresholds=None); lab["perks"] = {}
    brooms = [(r,c) for r,row in enumerate(a["special_board"]) for c,v in enumerate(row) if v==B]
    print(f"== {files[i].name} rng {observed(a)['rng']}->{want['rng']} brooms {brooms} pvpMode {cap['profile']['rules'].get('pvpMode')} specials-before {sorted({v for row in a['special_board'] for v in row if v})}")
    for (r,c) in brooms:
        for d,(dr,dc) in {"up":(-1,0),"down":(1,0),"left":(0,-1),"right":(0,1)}.items():
            t=(r+dr,c+dc)
            if not (0<=t[0]<7 and 0<=t[1]<7): continue
            act={"kind":"swap","start":[r,c],"target":list(t),"direction":d}
            with contextlib.redirect_stdout(io.StringIO()):
                res=sim.step(lab, act)
            if not res.get("supported"): print("  ",d,"unsupported",res.get("reason")); continue
            st=res["state"]; gb=grid(st["board"]); gs=grid(st["special_board"])
            cells=[(y,x,want["board"][y][x],gb[y][x]) for y in range(7) for x in range(7) if want["board"][y][x]!=gb[y][x]]
            sp=[(y,x,want["special_board"][y][x],gs[y][x]) for y in range(7) for x in range(7) if want["special_board"][y][x]!=gs[y][x]]
            ev=[e.get("type")+":"+str(e.get("special",e.get("kind",""))) for e in (res.get("events") or res.get("intent_events") or [])]
            print(f"   {d:5} color {a['board'][t[0]][t[1]]} rng sim {st['engine_refill'].rng.counter} (igra {want['rng']}) polja {len(cells)} spec {len(sp)} {cells[:6]} {sp[:4]}")
