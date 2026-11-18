import json, subprocess, re, os, numpy as np, soundfile as sf
V='app/public/voice'; os.makedirs(V+'/proc',exist_ok=True)
TEMPO=1.15; KEEP=0.13; SR=48000
lines=json.load(open('/home/claude/ad/lines.json',encoding='utf-8'))
out={}
for lid,text in lines:
    wav=f'/tmp/claude-0/-home-claude/779f453d-080b-52f3-8c0f-f1be6cc0c166/scratchpad/{lid}.wav'
    subprocess.run(['ffmpeg','-v','error','-y','-i',f'{V}/{lid}.mp3','-ar',str(SR),'-ac','1',wav],check=True)
    a,_=sf.read(wav)
    log=subprocess.run(['ffmpeg','-i',wav,'-af','silencedetect=n=-40dB:d=0.22','-f','null','-'],capture_output=True,text=True).stderr
    st=[float(x) for x in re.findall(r'silence_start: ([0-9.]+)',log)]; en=[float(x) for x in re.findall(r'silence_end: ([0-9.]+)',log)]
    dur=len(a)/SR
    if len(en)<len(st): en.append(dur)
    # leading silence trim too
    cuts=[]  # (start,end) regions to remove
    for s,e in zip(st,en):
        if s<0.05: cuts.append((0, max(0,e-0.05)))
        elif e>=dur-0.01: cuts.append((s+0.08, dur))
        else:
            k=0.32 if lid in ('01','11') else KEEP
            cuts.append((s+k/2, e-k/2))
    keep=[]; t=0
    for s,e in cuts:
        if s>t: keep.append((t,s))
        t=e
    if t<dur: keep.append((t,dur))
    seg=np.concatenate([a[int(s*SR):int(e*SR)] for s,e in keep])
    # tiny fades at joins
    sf.write(wav.replace('.wav','_t.wav'),seg,SR)
    subprocess.run(['ffmpeg','-v','error','-y','-i',wav.replace('.wav','_t.wav'),'-af',f'atempo={TEMPO}','-ac','2',f'{V}/proc/{lid}.wav'],check=True)
    def m(x):
        o=0
        for s,e in keep:
            if x<s: return o/TEMPO
            if x<=e: return (o+x-s)/TEMPO
            o+=e-s
        return o/TEMPO
    al=json.load(open(f'{V}/{lid}.json',encoding='utf-8'))
    chars=''.join(al['characters']); starts=[round(m(x),3) for x in al['character_start_times_seconds']]
    d=float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0',f'{V}/proc/{lid}.wav']))
    out[lid]={'chars':chars,'starts':starts,'dur':round(d,3),'text':re.sub(r'\[[a-z]+\]\s*','',text)}
    print(lid,round(dur,2),'->',round(d,2))
json.dump(out,open('voice_al.json','w'),ensure_ascii=False)
print('sum',round(sum(v['dur'] for v in out.values()),2))
