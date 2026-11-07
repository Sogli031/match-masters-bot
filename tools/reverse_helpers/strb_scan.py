import sys, json, bisect, numpy as np
from pathlib import Path
ROOT=Path(r"C:\Users\PC\Desktop\memory gui")
so=np.fromfile(ROOT/"Debug/reverse/libil2cpp.so",dtype='<u4')
off=int(sys.argv[1],16); size=int(sys.argv[2]) if len(sys.argv)>2 else 1  # 1=strb, 4=str w
idx=json.load(open(ROOT/"data/il2cpp_method_index.json",encoding='utf-8'))
pairs=sorted((int(a,16),n) for a,n in idx['entries'])
addrs=[a for a,_ in pairs]
if size==1: pat=0x39000000|(off<<10); 
else: pat=0xB9000000|((off//4)<<10)
hits=np.nonzero((so & 0xFFFFFC00)==pat)[0]
# STRB imm only (op 0x39 with opc=00 store). check Rt != 31 ok
out={}
for h in hits:
    a=int(h)*4+0x4000
    i=bisect.bisect_right(addrs,a)-1
    name=pairs[i][1] if i>=0 else '?'
    out.setdefault(name,[]).append(hex(a))
for k,v in sorted(out.items()): print(k, v[:3], len(v))
