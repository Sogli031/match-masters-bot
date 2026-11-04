import sys, json, bisect, numpy as np
from pathlib import Path
ROOT=Path(r"C:\Users\PC\Desktop\memory gui")
so=np.fromfile(ROOT/"Debug/reverse/libil2cpp.so",dtype='<u4')
idx=json.load(open(ROOT/"data/il2cpp_method_index.json",encoding='utf-8'))
pairs=sorted((int(a,16),n) for a,n in idx['entries']); addrs=[a for a,_ in pairs]
start=(0x2898800)//4; end=(0x2898800+0x415de60)//4
code=so[start:end]
pc=(np.arange(start,end,dtype=np.int64)*4+0x4000)
op=code>>26
imm=(code & 0x3FFFFFF).astype(np.int64); imm=np.where(imm & 0x2000000, imm-0x4000000, imm)
tgt=pc+imm*4
for t in sys.argv[1:]:
    t=int(t,16)
    for kind,o in (("b",0b000101),("bl",0b100101)):
        hits=np.nonzero((op==o)&(tgt==t))[0]
        for h in hits:
            a=int(pc[h]); i=bisect.bisect_right(addrs,a)-1
            print(hex(t),kind,hex(a),pairs[i][1],hex(a-pairs[i][0]))
