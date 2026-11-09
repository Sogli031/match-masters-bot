"""Jedno pokretanje metle: tabla pre, posle pakovanja, igra, simulator, dogadjaji.

    python tools/broom_show.py Debug/research/FOLDER 30 up
"""
import json, sys, os, io, contextlib
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT)); os.chdir(ROOT)
import move_strategy as ms
from tools.analyze_research import capture_from, observed, grid
from strategy_lab import simulation as sim
from simulator_capture import lab_move, capture_mode
ms.SWEEP_EXACT_PORTED = True
folder=Path(sys.argv[1]); idx=int(sys.argv[2]); d=sys.argv[3]
a=json.loads((folder/f"{idx:03d}.json").read_text(encoding="utf-8")); b=json.loads((folder/f"{idx+1:03d}.json").read_text(encoding="utf-8"))
cap=capture_from(a); want=observed(b)
sim.PREFIX_MODES=set(sim.PREFIX_MODES)|{capture_mode(cap["profile"]).value}
lab=lab_move(cap,thresholds=None); lab["perks"]={}
B=ms.SPECIAL_SWEEP_SE_BROOM
r,c=[(r,c) for r,row in enumerate(a["special_board"]) for c,v in enumerate(row) if v==B][0]
dr,dc={"up":(-1,0),"down":(1,0),"left":(0,-1),"right":(0,1)}[d]
act={"kind":"swap","start":[r,c],"target":[r+dr,c+dc],"direction":d}
cand=ms.MoveCandidate((r,c),(r+dr,c+dc),ms.Direction(d),grid(a["board"]),grid(a["special_board"]))
tr=ms._sweep_se_transformed_candidate(cand)
res=sim.step(lab,act); st=res["state"]
def cell(v,s): return f"{v:>2}"+(f"/{s:<2}" if s else "   ")
P=tr[0]
print("broom",(r,c),d,"target color",tr[2],"swept",tr[1])
print("PRE".ljust(36),"POSLE METLE (sim)".ljust(36),"IGRA".ljust(36),"SIM")
for y in range(7):
    print(" ".join(cell(a["board"][y][x],a["special_board"][y][x]) for x in range(7)).ljust(36),
          " ".join(cell(P.board[y][x],P.special_board[y][x]) for x in range(7)).ljust(36),
          " ".join(cell(want["board"][y][x],want["special_board"][y][x]) for x in range(7)).ljust(36),
          " ".join(cell(int(st["board"][y][x]),int(st["special_board"][y][x])) for x in range(7)))
print("rng pre",observed(a)["rng"],"igra",want["rng"],"sim",st["engine_refill"].rng.counter)
for e in res.get("events") or []: print(" ",{k:v for k,v in e.items() if k in("type","cascade","kind","color","cells","cell","special")})
print("refills",[[ (t["x"],t["y"],t["color"],t["rng_before"],t.get("special_value")) for t in rf] for rf in res["refills"]])
