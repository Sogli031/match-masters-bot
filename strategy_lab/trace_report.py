"""Coverage report for passive traces; missing events never count as validation."""
import argparse
from collections import Counter
import json
from pathlib import Path


def summarize(path):
    rows=[];invalid=[]
    for number,line in enumerate(Path(path).read_text(encoding='utf-8').splitlines(),1):
        try:rows.append(json.loads(line))
        except ValueError:invalid.append(number)
    events=[r for r in rows if r.get('type')=='event']
    enters={r['id']:r for r in events if r.get('phase')=='enter'}
    leaves={r['id']:r for r in events if r.get('phase')=='leave'}
    pairs=[(v,leaves[k]) for k,v in enters.items() if k in leaves]
    rng_pairs=[(a,b) for a,b in pairs if 'rng' in a and 'rng' in b]
    methods=Counter(r['method'] for r in enters.values())
    return dict(path=str(Path(path).resolve()),events=len(events),method_calls=dict(methods),
        paired_calls=len(pairs),unclosed_calls=len(set(enters)-set(leaves)),
        orphan_returns=len(set(leaves)-set(enters)),rng_pairs=len(rng_pairs),
        complete_rng_matrices=sum('matrix' in r.get('rng',{}) for r in events),
        memory_read_errors=sum('error' in r.get('rng',{}) for r in events),
        rng_counter_advances=dict(Counter(str(b['rng'].get('counter',0)-a['rng'].get('counter',0)) for a,b in rng_pairs if not a['rng'].get('error') and not b['rng'].get('error'))),
        invalid_json_lines=invalid,finished=any(r.get('type')=='summary' for r in rows),
        summaries=[r for r in rows if r.get('type')=='summary'],
        validated_refill_algorithm=False,validated_rng_algorithm=False,
        limitations=['Calls may include AI simulations; logical match correlation not implemented',
                     'Function hooks alone do not capture before/after board or equipment effects'])


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('trace',type=Path);a=p.parse_args()
    result=summarize(a.trace);a.trace.with_suffix('.summary.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))
