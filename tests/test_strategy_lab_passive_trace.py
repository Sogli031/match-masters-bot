from pathlib import Path
import json
import pytest
from strategy_lab.passive_trace import configuration,record,ROOT


def test_trace_configuration_uses_current_layout_and_distinct_overloads():
    cfg=configuration(ROOT/'Debug/strategy_lab/native-current')
    hooks=cfg['hooks']
    assert len({h['rva'] for h in hooks})==len(hooks)
    assert len([h for h in hooks if h['name']=='Next'])==2
    assert all(len(h['bytes'])==16 for h in hooks)
    assert cfg['rng']==dict(matrix=16,index=24,seed=28,counter=32)
    assert {'Generate','RefillSlots','EndGame','FillAllEmptySlots'} <= {h['name'] for h in hooks}


def test_connection_failure_is_preserved_in_evidence(tmp_path,monkeypatch):
    import frida
    class Manager:
        def add_remote_device(self,endpoint):raise RuntimeError('test disconnected')
    monkeypatch.setattr(frida,'get_device_manager',lambda:Manager())
    path=tmp_path/'trace.jsonl'
    with pytest.raises(RuntimeError,match='disconnected'):record(1,path,.01)
    lines=[json.loads(line) for line in path.read_text().splitlines()]
    assert lines[0]['type']=='manifest'
    assert lines[-1]['type']=='summary'
    assert lines[-1]['errors'][0]['message']=='test disconnected'
    with pytest.raises(FileExistsError):record(1,path,.01)


def test_invalid_duration_cannot_attach(tmp_path):
    with pytest.raises(ValueError):record(1,tmp_path/'no.jsonl',0)
    assert not (tmp_path/'no.jsonl').exists()
