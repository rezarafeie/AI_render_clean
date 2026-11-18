import json, subprocess
D=json.load(open('app/src/data.json',encoding='utf-8')); T=D['total']
S={s['id']:s for s in D['scenes']}
def c(sid,w,occ=0,off=0):
    s=S[sid]; m=[x for x in s['words'] if x['t']==w or x['t'].startswith(w)]
    return round(s['start']+(m[occ] if len(m)>occ else m[0])['s']+off,3)
def st(sid,off=0): return round(S[sid]['start']+off,3)
FX='app/public/sfx/'
cues=[
 (0.18,'metalhit',0.9),(c('01','توی',0,-0.1),'airhiss',0.6),(c('01','توی',0,-0.05),'whoosh',0.5),(c('01','کیف'),'pop',0.6),
 (st('02',-0.1),'whoosh2',0.55),(c('02','نیم',0,-0.05),'clock',0.45),
 (st('03',0),'shatter',0.3),(c('03','بسه',0,-0.12),'boom',0.28),
 (st('04',0),'impact',0.6),(st('04',0.05),'sparkle',0.4),(c('04','هفتاد',0,-0.05),'pop',0.6),
 (st('05',-0.1),'whoosh',0.55),(c('05','چند',0,-0.12),'impactwrench',0.75),(c('05','باز',0,-0.05),'metalhit',0.4),
 (st('06',-0.1),'whoosh2',0.55),(c('06','جاهای',0,-0.1),'swipe',0.5),(c('06','دستت',0,-0.1),'ratchet',0.7),
 (st('07',-0.1),'whoosh',0.55),(st('07',0.3),'grinder',0.6),(c('07','سنباده',0,-0.08),'pop',0.5),(c('07','برش',0,-0.08),'pop',0.5),(c('07','پولیش',0,-0.08),'pop',0.5),
 (st('08',0.18),'metalhit',0.85),(c('08','برای',0,-0.05),'airhammer',0.6),
 (st('09',-0.1),'whoosh2',0.55),(c('09','سری',0,-0.1),'swipe',0.45),(c('09','اتصالاتِ',0,-0.1),'pop',0.55),(c('09','کیفِ',0,-0.1),'pop',0.55),(c('09','مرتب',0,-0.05),'ding',0.5),
 (st('10',-0.1),'whoosh',0.5),(c('10','فولاده',0,-0.15),'pop',0.5),(c('10','سریعه',0,-0.15),'pop',0.5),(c('10','ضمانتِ',0,-0.15),'pop',0.5),(c('10','پول',0,0.1),'ding',0.5),
 (st('11',-0.1),'whoosh2',0.5),(c('11','صد',0,-2.0),'riser',0.45),(c('11','صد',0,-0.12),'impact',0.55),(c('11','صد',0,1.13),'cashreg',0.75),
 (st('12',-0.1),'whoosh',0.5),(c('12','بزن',0,-0.05),'click' if False else 'pop',0.7),(st('12',0.9),'sparkle',0.4),
]
inputs=[]; fc=[]
for k,(t,f,v) in enumerate(cues):
    inputs+=['-i',FX+f+'.mp3']; ms=int(max(0,t)*1000)
    fc.append(f"[{k}:a]aformat=sample_rates=48000:channel_layouts=stereo,volume={v*0.75:.2f},adelay={ms}|{ms}[f{k}]")
n=len(cues)
inputs+=['-i','music.mp3','-i','music.mp3']; mi=n
fc.append(f"[{mi}:a]aformat=sample_rates=48000:channel_layouts=stereo,atrim=0:32.5[ma];[{mi+1}:a]aformat=sample_rates=48000:channel_layouts=stereo,atrim=4:32.5,asetpts=PTS-STARTPTS[mb];[ma][mb]acrossfade=d=1.5[mfull]")
fc.append(f"[mfull]atrim=0:{T},volume=0.24,afade=t=in:d=0.3,afade=t=out:st={T-1.8:.2f}:d=1.8[mus0]")
# voice
vin=[]
for s in D['scenes']:
    inputs+=['-i',f"app/public/voice/proc/{s['id']}.wav"]; idx=len(inputs)//2-1; ms=int(s['start']*1000)
    fc.append(f"[{idx}:a]aformat=sample_rates=48000:channel_layouts=stereo,adelay={ms}|{ms}[v{s['id']}]"); vin.append(f"[v{s['id']}]")
fc.append("".join(vin)+f"amix=inputs={len(vin)}:normalize=0,highpass=f=60,acompressor=threshold=-18dB:ratio=3:attack=4:release=100:makeup=3dB,apad=whole_dur={T},asplit=2[voice][sc]")
fc.append("[mus0][sc]sidechaincompress=threshold=0.04:ratio=5:attack=15:release=300[mus]")
fc.append("".join(f"[f{k}]" for k in range(n))+f"amix=inputs={n}:normalize=0[fx]")
fc.append(f"[voice][mus][fx]amix=inputs=3:normalize=0,atrim=0:{T},alimiter=limit=0.95,loudnorm=I=-13:TP=-1:LRA=8[out]")
open('mix_fc.txt','w').write(';\n'.join(fc))
subprocess.run(['ffmpeg','-v','error','-y',*inputs,'-filter_complex_script','mix_fc.txt','-map','[out]','-ar','48000','mix.wav'],check=True)
print('ok',T)
