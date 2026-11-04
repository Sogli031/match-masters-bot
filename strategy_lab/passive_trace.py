"""Bounded passive Frida trace, with build/code checks and explicit coverage."""
import argparse
import hashlib
import json
from pathlib import Path
import threading
import time
from tools.il2cpp_disasm import Elf64

ROOT=Path(__file__).resolve().parents[1]
METHODS={'RandomWrapper':{'Next','Generate'},'BoardModel':{'RefillSlots'},
 'SpawningEngine':{'FillAllEmptySlots','SuperFoceCombo','SetScoreAndEnergyOverrides','RandomSpawnSpecialSlots','RandomSpawnLiveEventPieces'},
 'GameLogic':{'CalculateEndGame','EndGame'}}


def configuration(directory,max_events=10000):
    directory=Path(directory);raw=(directory/'symbols.json').read_bytes();symbols=json.loads(raw)
    binary=(directory/'libil2cpp.so').read_bytes();elf=Elf64(binary)
    hooks=[];layout=None
    for cls in symbols['classes']:
        if cls['name']=='RandomWrapper':
            fields={f['name']:f['offset'] for f in cls['fields']}
            layout=dict(matrix=fields['_matrix'],index=fields['_index'],seed=fields['_seed'],counter=fields['<counter>k__BackingField'])
        if cls['name'] not in METHODS:continue
        for method in cls['methods']:
            if method['name'] not in METHODS[cls['name']]:continue
            code=elf.read(int(method['rva'],16),16)
            if code is None or len(code)!=16:raise ValueError('unmapped method')
            hooks.append(dict(label=cls['full_name']+'::'+method['name']+'@'+method['rva'],name=method['name'],
                rva=method['rva'],bytes=list(code),rng=cls['name']=='RandomWrapper'))
    if not layout or not hooks:raise ValueError('Missing required metadata')
    return dict(module_size=symbols['runtime']['module_size'],runtime=symbols['runtime'],hooks=hooks,rng=layout,
                max_events=max_events,symbols_sha256=hashlib.sha256(raw).hexdigest(),binary_sha256=hashlib.sha256(binary).hexdigest())


def record(pid,output,seconds=20,directory=ROOT/'Debug/strategy_lab/native-current',endpoint='127.0.0.1:27042'):
    import frida
    if not 0<seconds<=3600:raise ValueError('duration must be 0..3600 seconds')
    config=configuration(directory);output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    # Never overwrite previous evidence.
    stream=output.open('x',encoding='utf-8');lock=threading.Lock();counts={};errors=[]
    def write(value):
        with lock:stream.write(json.dumps(value,ensure_ascii=True)+'\n');stream.flush()
    def message(msg,data):
        if msg.get('type')=='send':
            for event in msg['payload'].get('events',[]):
                counts[event.get('method',event['phase'])]=counts.get(event.get('method',event['phase']),0)+1
                write(dict(type='event',**event))
        else:errors.append(msg);write(dict(type='agent_error',message=msg))
    session=None;script=None;started=time.monotonic();summary=None
    try:
        write(dict(type='manifest',config=config,pid=pid,duration=seconds,
                   limitations=['Raw args are pointer/integer bits, not decoded boards','No verified initial match or match-id capture yet','Hooks may affect timing; no gameplay actions or managed invocations']))
        session=frida.get_device_manager().add_remote_device(endpoint).attach(pid,realm='emulated')
        script=session.create_script(Path(__file__).with_name('passive_trace.js').read_text(encoding='utf-8-sig'));script.on('message',message);script.load()
        script.exports_sync.start(config)
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:time.sleep(min(.25,max(0,deadline-time.monotonic())))
    except BaseException as exc:
        errors.append(dict(type=type(exc).__name__,message=str(exc)))
        raise
    finally:
        try:
            if script is not None:
                try:summary=script.exports_sync.stop()
                except Exception as exc:errors.append(dict(stage='stop',message=str(exc)))
        finally:
            if session is not None:
                try:session.detach()
                except Exception as exc:errors.append(dict(stage='detach',message=str(exc)))
            write(dict(type='summary',seconds=time.monotonic()-started,counts=counts,errors=errors,agent=summary));stream.close()
    return dict(output=str(output),counts=counts,errors=len(errors),agent=summary)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--pid',type=int,required=True);p.add_argument('--seconds',type=float,default=20)
    p.add_argument('--output',type=Path,default=ROOT/'Debug/strategy_lab/passive'/('trace-'+time.strftime('%Y%m%d-%H%M%S')+'.jsonl'))
    a=p.parse_args()
    p.error('Live hooks disabled after observed game freeze; use offline trace analysis until observer is redesigned and tested')
