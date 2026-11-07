import sys, json, bisect, numpy as np, capstone, collections
from pathlib import Path
ROOT=Path(r"C:\Users\PC\Desktop\memory gui")
raw=open(ROOT/"Debug/reverse/libil2cpp.so","rb").read()
so=np.frombuffer(raw,dtype='<u4')
idx=json.load(open(ROOT/"data/il2cpp_method_index.json",encoding='utf-8'))
pairs=sorted((int(a,16),n) for a,n in idx['entries']); addrs=[a for a,_ in pairs]
start=0x2898800//4; end=(0x2898800+0x415de60)//4
code=so[start:end]; pc=np.arange(start,end,dtype=np.int64)*4+0x4000
op=code>>26; imm=(code&0x3FFFFFF).astype(np.int64); imm=np.where(imm&0x2000000,imm-0x4000000,imm); tgt=pc+imm*4
md=capstone.Cs(capstone.CS_ARCH_ARM64,capstone.CS_MODE_ARM)
want=int(sys.argv[1]) if len(sys.argv)>1 else 1
res=collections.Counter()
for ctor in (0x578acbc,0x578e864,0x579ff44,0x57964d0,0x579ff6c):
    for h in np.nonzero(((op==0b100101)|(op==0b000101))&(tgt==ctor))[0]:
        a=int(pc[h]); back=raw[a-0x4000-64:a-0x4000]
        w1=None
        for ins in md.disasm(back,a-64):
            if ins.op_str.startswith('w1,'):
                w1=ins.op_str.split(',')[1].strip() if ins.mnemonic in('mov','orr') else '?'
        i=bisect.bisect_right(addrs,a)-1
        if w1 in ('#%d'%want, '#0x%x'%want): res[pairs[i][1]]+=1
for k,v in res.most_common(60): print(v,k)
