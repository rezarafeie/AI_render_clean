import json, subprocess
d=json.load(open('scribe.json'))
ws=[w for w in d['words'] if w['type']=='word']
for i,w in enumerate(ws): w['i']=i
DROP={47,93,76}  # fillers: اِاِاِ x2, خب
DROP|={46}       # "یا" before filler
keep=[w for w in ws if w['i'] not in DROP]
PRE,POST,MAXGAP=0.07,0.10,0.28
segs=[]
for w in keep:
    s=w['start']-PRE; e=w['end']+POST
    if segs and s - segs[-1][1] <= MAXGAP - PRE - POST and w['i']-segs[-1][2]==1:
        segs[-1][1]=max(segs[-1][1],e); segs[-1][2]=w['i']
    elif segs and w['i']-segs[-1][2]==1 and (w['start']-ws[segs[-1][2]]['end'])<=MAXGAP:
        segs[-1][1]=e; segs[-1][2]=w['i']
    else:
        if segs: s=max(s,segs[-1][1])
        segs.append([max(0,s),e,w['i']])
# map
out=[]; t=0
for s,e,_ in segs: out.append((s,e,t)); t+=e-s
total=t
def m(x):
    for s,e,o in out:
        if s-1e-6<=x<=e+1e-6: return o+(x-s)
    best=min(out,key=lambda q:min(abs(x-q[0]),abs(x-q[1]))); s,e,o=best
    return o if abs(x-s)<abs(x-e) else o+(e-s)
words=[{'i':w['i'],'t':w['text'],'s':round(m(w['start']),3),'e':round(m(w['end']),3)} for w in keep]
cuts=[round(o,3) for s,e,o in out[1:]]
json.dump({'total':round(total,3),'segs':[[round(s,3),round(e,3),round(o,3)] for s,e,o in out],'cuts':cuts,'words':words},open('edl.json','w'),ensure_ascii=False,indent=0)
print('segments',len(out),'total',round(total,2),'orig',ws[-1]['end'])
# build filter
SRC='/root/.claude/uploads/779f453d-080b-52f3-8c0f-f1be6cc0c166/46117f85-2.mp4'
fc=[];
for k,(s,e,o) in enumerate(out):
    dur=e-s
    fc.append(f"[0:v]trim={s:.3f}:{e:.3f},setpts=PTS-STARTPTS[v{k}];[0:a]atrim={s:.3f}:{e:.3f},asetpts=PTS-STARTPTS,afade=t=in:d=0.012,afade=t=out:st={max(0,dur-0.015):.3f}:d=0.015[a{k}]")
fc.append(''.join(f"[v{k}][a{k}]" for k in range(len(out)))+f"concat=n={len(out)}:v=1:a=1[v][a]")
open('fc.txt','w').write(';'.join(fc))
subprocess.run(['ffmpeg','-v','error','-y','-i',SRC,'-filter_complex_script','fc.txt','-map','[v]','-map','[a]','-c:v','libx264','-crf','14','-preset','fast','-g','15','-pix_fmt','yuv420p','-c:a','pcm_s16le','-ar','48000','cut.mov'],check=True)
print('ok')
