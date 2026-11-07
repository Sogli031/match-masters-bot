"""Read-only, version-bound capture of native code. Never invokes game methods."""
import argparse
import hashlib
import json
from pathlib import Path


def validate_manifest(manifest, runtime):
    keys=('version','module_name','module_size')
    if any(manifest['runtime'].get(k)!=runtime.get(k) for k in keys):
        raise ValueError('Runtime version mismatch: refresh symbols; refusing stale addresses')


def capture(symbols, output, pid, endpoint='127.0.0.1:27042', count=128):
    import frida
    data=json.loads(Path(symbols).read_text(encoding='utf-8'))
    if not 1<=count<=1024:raise ValueError('instruction limit must be 1..1024')
    reference=json.loads(Path(symbols).with_name('frida_live_code.json').read_text(encoding='utf-8'))
    validate_manifest(reference,data['runtime'])
    selected=[dict(owner=c['full_name'],**m) for c in data['classes'] for m in c['methods']
              if m['name'] in ('RefillSlots','CalculateEndGame','get_Random')]
    session=frida.get_device_manager().add_remote_device(endpoint).attach(pid,realm='emulated')
    try:
        script=session.create_script('''rpc.exports={module:function(){let m=Process.getModuleByName("libil2cpp.so");return {base:m.base.toString(),size:m.size};},read:function(rva,n){let m=Process.getModuleByName("libil2cpp.so"),p=m.base.add(rva),a=[];for(let i=0;i<n;i++){if(p.compare(m.base)<0||p.compare(m.base.add(m.size))>=0)throw Error("outside module");let x=Instruction.parse(p);a.push({address:p.toString(),instruction:x.toString(),bytes:Array.from(new Uint8Array(p.readByteArray(x.size)))});p=x.next;if(x.mnemonic==="ret")break;}return a;}};''')
        script.load();module=script.exports_sync.module()
        # Metadata captures are tied to a live build. ASLR base may change;
        # reject a changed mapped module extent rather than reuse stale RVAs.
        if module['size']!=data['runtime']['module_size']:raise ValueError('Module size changed: refresh symbols')
        for method in selected:
            method['live_instructions']=script.exports_sync.read(method['rva'],count)
            trusted=next(m for m in reference['methods'] if m['owner']==method['owner'] and m['name']==method['name'])
            expected=trusted['live_instructions']
            actual=method['live_instructions']
            # Old capture may extend past RET; compare only the bounded function prefix.
            n=min(len(expected),len(actual))
            if not n or any(expected[i]['bytes']!=actual[i]['bytes'] for i in range(n)):
                raise ValueError('Native code changed: refresh the trusted live capture')
            method['capture_limit']=count
            method['complete_control_flow']=False
        result=dict(runtime=data['runtime'],current_mapping=module,methods=selected,
                    symbols_sha256=hashlib.sha256(Path(symbols).read_bytes()).hexdigest(),
                    scope='bounded native instruction windows; not reconstructed refill or terminal semantics')
        Path(output).parent.mkdir(parents=True,exist_ok=True)
        Path(output).write_text(json.dumps(result,indent=2),encoding='utf-8')
        return result
    finally:session.detach()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--symbols',default='Debug/strategy_lab/frida_symbols.json')
    p.add_argument('--output',default='Debug/strategy_lab/native-code-capture.json')
    p.add_argument('--pid',type=int,required=True)
    p.add_argument('--count',type=int,default=128)
    args=p.parse_args()
    result=capture(args.symbols,args.output,args.pid,count=args.count)
    print(json.dumps({'methods':len(result['methods']),'output':args.output}))
