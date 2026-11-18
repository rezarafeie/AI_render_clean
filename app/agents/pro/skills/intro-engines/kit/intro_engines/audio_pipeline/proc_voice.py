import json, subprocess, re, os, numpy as np, soundfile as sf, sys
OUT='audio/vproc'; os.makedirs(OUT,exist_ok=True)
TEMPO=float(sys.argv[1]) if len(sys.argv)>1 else 1.18; KEEP=0.16; SR=48000
SC='/tmp/claude-0/-home-claude/779f453d-080b-52f3-8c0f-f1be6cc0c166/scratchpad'
tot=0
W={}
for i in ['p1','p2','p3','p4','p5','p6','p7']:
    lid=i; wav=f'{SC}/{lid}.wav'
    subprocess.run(['ffmpeg','-v','error','-y','-i',f'audio/voice/{lid}.mp3','-ar',str(SR),'-ac','1',wav],check=True)
    a,_=sf.read(wav); dur=len(a)/SR
    log=subprocess.run(['ffmpeg','-i',wav,'-af','silencedetect=n=-40dB:d=0.18','-f','null','-'],capture_output=True,text=True).stderr
    st=[float(x) for x in re.findall(r'silence_start: ([0-9.]+)',log)]; en=[float(x) for x in re.findall(r'silence_end: ([0-9.]+)',log)]
    if len(en)<len(st): en.append(dur)
    cuts=[]
    for s,e in zip(st,en):
        if s<0.05: cuts.append((0,max(0,e-0.04)))
        elif e>=dur-0.01: cuts.append((s+0.1,dur))
        else: cuts.append((s+KEEP/2,e-KEEP/2))
    keep=[];t=0
    for s,e in cuts:
        if s>t: keep.append((t,s))
        t=max(t,e)
    if t<dur: keep.append((t,dur))
    import bisect
    cum=[];acc=0
    for s0,e0 in keep: cum.append(acc); acc+=e0-s0
    def mp(t):
        for (s0,e0),c in zip(keep,cum):
            if t<s0: return c/TEMPO
            if t<=e0: return (c+t-s0)/TEMPO
        return acc/TEMPO
    al=json.load(open(f'audio/voice/{lid}.al.json'))
    ch=al['characters'];cs=al['character_start_times_seconds'];ce=al['character_end_times_seconds']
    words=[];cur='';ws=None
    for c,a0,b0 in zip(ch,cs,ce):
        if c.isspace():
            if cur: words.append({'t':cur,'s':round(mp(ws),3),'e':round(mp(we),3)}); cur=''
            continue
        if not cur: ws=a0
        cur+=c; we=b0
    if cur: words.append({'t':cur,'s':round(mp(ws),3),'e':round(mp(we),3)})
    W[lid]=words
    parts=[]
    for s,e in keep:
        seg=a[int(s*SR):int(e*SR)].copy(); f=min(len(seg)//4,int(0.006*SR))
        if f>0: seg[:f]*=np.linspace(0,1,f); seg[-f:]*=np.linspace(1,0,f)
        parts.append(seg)
    seg=np.concatenate(parts); sf.write(f'{SC}/{lid}_t.wav',seg,SR)
    subprocess.run(['ffmpeg','-v','error','-y','-i',f'{SC}/{lid}_t.wav','-af',f'atempo={TEMPO},highpass=f=70,acompressor=threshold=-20dB:ratio=3:attack=5:release=80:makeup=3','-ar',str(SR),f'{OUT}/{lid}.wav'],check=True)
    d=sf.info(f'{OUT}/{lid}.wav').duration; tot+=d; print(lid,round(dur,2),'->',round(d,2))
print('total',round(tot,2))
json.dump(W,open('audio/words.json','w'),ensure_ascii=False)
