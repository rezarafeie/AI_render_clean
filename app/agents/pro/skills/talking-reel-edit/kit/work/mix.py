import json, subprocess
D=json.load(open('/home/claude/ed/app/src/data.json')); T=D['total']
SFX='/home/claude/ed/app/public/sfx/'
inputs=['-i','voice_raw.wav','-i','music.mp3']
fc=[]
fc.append("[0:a]highpass=f=70,acompressor=threshold=-20dB:ratio=3:attack=5:release=120:makeup=4dB,aformat=sample_rates=48000:channel_layouts=stereo,asplit=2[voice][sc]")
fc.append(f"[1:a]aformat=sample_rates=48000:channel_layouts=stereo,atrim=0:{T},volume=0.18,afade=t=in:d=0.6,afade=t=out:st={T-1.6:.2f}:d=1.6[mus0]")
fc.append("[mus0][sc]sidechaincompress=threshold=0.03:ratio=6:attack=20:release=350:makeup=1[mus]")
labels=[]
for n,s in enumerate(D['sfx']):
    inputs+=['-i',SFX+s['f']+'.mp3']
    idx=n+2; ms=int(s['t']*1000)
    fc.append(f"[{idx}:a]aformat=sample_rates=48000:channel_layouts=stereo,volume={s['v']*0.8:.2f},adelay={ms}|{ms}[s{n}]")
    labels.append(f"[s{n}]")
fc.append("".join(labels)+f"amix=inputs={len(labels)}:normalize=0:dropout_transition=0[sfx]")
fc.append("[voice][mus][sfx]amix=inputs=3:normalize=0:dropout_transition=0,alimiter=limit=0.95[mixed]")
fc.append(f"[mixed]atrim=0:{T},loudnorm=I=-14:TP=-1.2:LRA=9[out]")
open('mix_fc.txt','w').write(';\n'.join(fc))
subprocess.run(['ffmpeg','-v','error','-y',*inputs,'-filter_complex_script','mix_fc.txt','-map','[out]','-ar','48000','mix.wav'],check=True)
print('ok')
