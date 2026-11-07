"""Conditional continuation audit over the existing analyzer; never claims full matches."""
import json
import random
import statistics
import time
from pathlib import Path
import turn_analyzer as ta


def compare(run, samples=32, seed=1729, max_steps=24):
    decision=ta.load_decision(Path(run))
    if decision is None: raise ValueError('Missing decision')
    analysis=ta.DecisionAnalysis(decision,seed=seed,max_steps=max_steps)
    actions,_=analysis.sim.legal_actions(analysis.root)
    pairs=[((3,2),(3,3)),((5,3),(6,3))]
    roots=[]
    for start,target in pairs:
        roots.append(next(a for a in actions if a['kind']=='swap' and
            {tuple(a['candidate'].start),tuple(a['candidate'].target)}=={start,target}))
    outcomes=[];started=time.perf_counter()
    for index in range(samples):
        branches=[]
        for first in roots:
            rng=random.Random(seed+index)
            state=analysis.root.copy();points=0.;reason=None;steps=0
            action=first
            while action is not None and steps<max_steps:
                if action['kind']=='booster':reason='unsupported_empirical_booster';break
                result=analysis.sim.step(state,action,rng)
                points+=result.points;steps+=1;state=result.state
                if state.over:reason=state.over;break
                action,_=analysis.sim.choose_action(state)
            branches.append(dict(points=points,steps=steps,stop=reason or 'no_action_or_step_limit',
                                 completed_match=False))
        outcomes.append(branches)
    deltas=[b[1]['points']-b[0]['points'] for b in outcomes]
    mean=statistics.mean(deltas)
    se=statistics.stdev(deltas)/(len(deltas)**.5) if len(deltas)>1 else None
    return dict(scope='conditional continuation from midgame; not full matches or equipment ranking',
        source=str(Path(run).resolve()),samples=samples,seed=seed,seconds=time.perf_counter()-started,
        policy=ta.POLICY_DOC,limitations=analysis.limitations,unverified=sorted(analysis.unverified),
        refill_model='existing turn_analyzer RuleSet; no reconstructed game RNG',
        branch_mean_points=[statistics.mean(b[j]['points'] for b in outcomes) for j in (0,1)],
        difference_mean=mean,conditional_normal_ci95=[mean-1.96*se,mean+1.96*se] if se is not None else None,
        completed_matches=0,outcomes=outcomes)


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--samples',type=int,default=32)
    parser.add_argument('--output',default='Debug/strategy_lab/continuation-audit.json')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    result=compare(root/'Debug/runs/2026-10-31_13-04-40_351',args.samples)
    path=root/args.output;path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='outcomes'},ensure_ascii=True,indent=2))
