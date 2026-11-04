from strategy_lab.continuation_audit import compare
from pathlib import Path

def test_continuation_repeats_identical_seeded_branches():
    root=Path(__file__).resolve().parents[1]
    run=root/'Debug/runs/2026-10-31_13-04-40_351'
    first=compare(run,samples=2,max_steps=4)
    second=compare(run,samples=2,max_steps=4)
    assert first['outcomes']==second['outcomes']
    assert first['completed_matches']==0
    assert all(not branch['completed_match'] for pair in first['outcomes'] for branch in pair)
