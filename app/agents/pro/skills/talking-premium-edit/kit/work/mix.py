import json, subprocess
D=json.load(open('/home/claude/v3/app/src/data.json')); T=D['total']
FX='/home/claude/v3/app/public/sfx/'
cues=[(2.55,'softwhoosh',0.5),(2.7,'chime',0.45),(4.72,'shimmer',0.45),(7.78,'softwhoosh',0.55),(7.98,'hit',0.5),
(9.6,'softwhoosh',0.5),(9.75,'chime',0.45)]
for t in D['topics']: cues+= [(t['s']-0.05,'softwhoosh',0.35),(t['s']+0.05,'tick',0.5)]
cues+=[(27.5,'softwhoosh',0.45),(28.9,'shimmer',0.4),(29.98,'hit',0.45),(31.25,'chime',0.45),(34.45,'softwhoosh',0.45),(34.55,'chime',0.4),
(37.3,'swell',0.5),(38.92,'hit',0.55),(41.25,'shimmer',0.45)]
inputs=[]; fc=[]
for n,(t,f,v) in enumerate(cues):
    inputs+=['-i',FX+f+'.mp3']; ms=int(t*1000)
    fc.append(f"[{n}:a]aformat=sample_rates=48000:channel_layouts=stereo,volume={v:.2f},adelay={ms}|{ms}[f{n}]")
n=len(cues)
inputs+=['-i','voice_raw.wav','-i','music.mp3']
fc.append(f"[{n}:a]highpass=f=80,afftdn=nf=-30,acompressor=threshold=-20dB:ratio=3:attack=5:release=120:makeup=4dB,aformat=sample_rates=48000:channel_layouts=stereo,apad=whole_dur={T},asplit=2[voice][sc]")
fc.append(f"[{n+1}:a]aformat=sample_rates=48000:channel_layouts=stereo,atrim=0:{T},volume=0.20,afade=t=in:d=0.8,afade=t=out:st={T-2:.2f}:d=2[mus0]")
fc.append("[mus0][sc]sidechaincompress=threshold=0.03:ratio=5:attack=20:release=350[mus]")
fc.append("".join(f"[f{k}]" for k in range(n))+f"amix=inputs={n}:normalize=0[fx]")
fc.append(f"[voice][mus][fx]amix=inputs=3:normalize=0,atrim=0:{T},alimiter=limit=0.95,loudnorm=I=-14:TP=-1.2:LRA=9[out]")
open('mix_fc.txt','w').write(';\n'.join(fc))
subprocess.run(['ffmpeg','-v','error','-y',*inputs,'-filter_complex_script','mix_fc.txt','-map','[out]','-ar','48000','mix.wav'],check=True)
print('ok',T)
