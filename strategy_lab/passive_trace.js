// Passive observation: no managed calls, writes, argument/return replacement.
let listeners=[], seq=0, limit=10000, seen=new Set(), pending=[], timer=null;
function flush(){if(pending.length){send({kind:'batch',events:pending});pending=[];}}
function emit(e){if(seq>=limit)return;pending.push(Object.assign({seq:++seq,at:Date.now()},e));if(pending.length>=32)flush();}
function rng(p,layout,full){
 let out={pointer:p.toString()};
 try{
  out.seed=p.add(layout.seed).readU32();out.index=p.add(layout.index).readS32();out.counter=p.add(layout.counter).readS32();
  if(full){let a=p.add(layout.matrix).readPointer(),n=a.add(0x18).readU64().toNumber();if(n!==624)throw Error('unexpected RNG matrix length '+n);out.matrix=Array.from(new Uint32Array(a.add(0x20).readByteArray(n*4)));}
 }catch(e){out.error=String(e);}return out;
}
rpc.exports={
 start:function(config){
  let m=Process.getModuleByName('libil2cpp.so');if(m.size!==config.module_size)throw Error('module size mismatch');
  // Validate every entry before attaching any observer.
  for(let h of config.hooks){let a=m.base.add(h.rva),bytes=Array.from(new Uint8Array(a.readByteArray(h.bytes.length)));if(JSON.stringify(bytes)!==JSON.stringify(h.bytes))throw Error('code mismatch or existing interception: '+h.label);}
  limit=config.max_events;
  try{for(let h of config.hooks){listeners.push(Interceptor.attach(m.base.add(h.rva),{
   onEnter:function(args){
    this.recorded=seq<limit;if(!this.recorded)return;
    this.id=seq+1;this.self=args[0];this.h=h;
    let event={phase:'enter',id:this.id,thread:Process.getCurrentThreadId(),method:h.label,self:this.self.toString(),args:[args[1].toString(),args[2].toString()]};
    if(h.rng){let full=h.name==='Generate'||!seen.has(this.self.toString());seen.add(this.self.toString());event.rng=rng(this.self,config.rng,full);}
    emit(event);
   },
   onLeave:function(ret){if(!this.recorded)return;let event={phase:'leave',id:this.id,thread:Process.getCurrentThreadId(),method:h.label,return_raw:ret.toString()};if(h.rng)event.rng=rng(this.self,config.rng,h.name==='Generate');emit(event);}
  }));}timer=setInterval(flush,250);emit({phase:'ready',hooks:config.hooks.length,module_base:m.base.toString()});flush();return {hooks:listeners.length};}
  catch(e){for(let l of listeners)l.detach();listeners=[];throw e;}
 },
 stop:function(){for(let l of listeners)l.detach();listeners=[];if(timer)clearInterval(timer);flush();return {events:seq,limit_reached:seq>=limit};}
};
