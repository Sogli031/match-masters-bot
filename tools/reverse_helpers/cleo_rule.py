import sys, json
from pathlib import Path
ROOT = Path(r"C:\Users\PC\Desktop\memory gui")
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT/"tools"))
import cleo_audit as ca, runtime
rows=[]
for run_dir in sorted((ROOT/"Debug"/"runs").iterdir()):
    move=ca._load(run_dir/"move.json"); delta=ca._load(run_dir/"observed_delta.json")
    if not move or not delta or move.get("selected_action")!="move": continue
    if "cleo" not in (move.get("best_move") or {}): continue
    best=ca._current_prediction(move)
    if best is None: continue
    check=runtime._cleo_prediction_check(ca._fill_unmeasured_turn(delta,run_dir,move),best)
    if not check: continue
    colors=best["cleo"]["scenario_colors"]; ex=best["cleo"]["scenario_extra_moves"]
    per={}
    for c,e in zip(colors,ex): per[c]=max(per.get(c,0),e)
    actual=check.get("actual_color_guess"); sure=bool(check.get("actual_color"))
    kept=check.get("observed_kept_the_turn")
    rows.append((run_dir.name, per, actual, sure, kept, move.get("pvp_mode") or (move.get("strategy_context") or {}).get("mode")))
mixed=[r for r in rows if any(v>=1 for v in r[1].values()) and any(v<1 for v in r[1].values())]
print("cleo moves",len(rows),"mixed (some colours extra, some not)",len(mixed))
hit=0;n=0;exp_uniform=0
for name,per,actual,sure,kept,mode in mixed:
    if actual not in per: print(name,"actual",actual,"not in",per); continue
    n+=1; isx=per[actual]>=1; hit+=isx
    exp_uniform+=sum(1 for v in per.values() if v>=1)/len(per)
    print(name, {k:int(v) for k,v in per.items()}, "actual",actual,"sure" if sure else "guess","extra-colour" if isx else "NON-extra", "kept" if kept else ("lost" if kept is False else "?"))
print(f"actual was an extra colour: {hit}/{n}; uniform model expects {exp_uniform:.1f}")
