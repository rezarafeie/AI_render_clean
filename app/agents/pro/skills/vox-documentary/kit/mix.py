import json, subprocess
D=json.load(open('app/src/data.json',encoding='utf-8')); T=D['total']
S={s['id']:s for s in D['scenes']}
def c(sid,w,off=0,occ=0):
    s=S[sid]; m=[x for x in s['words'] if x['t']==w or x['t'].startswith(w)]
    return round(s['start']+(m[occ] if len(m)>occ else m[0])['s']+off,3)
def st(sid,off=0): return round(S[sid]['start']+off,3)
FX='app/public/sfx/'
q=[]
for i,s in enumerate(D['scenes'][1:],start=1):
    q.append((s['start']-0.32,'whoosh' if i in (6,12) else ('paper' if i%2 else 'paper2'),0.5))
q+=[(st('01',0.15),'paper2',0.5),(c('01','کفش',-0.15),'pop',0.5),(c('01','یک',-0.1),'typewriter',0.3),(c('01','دلار'),'marker',0.45),(c('01','دلار',0.1),'cashreg',0.45),
(c('02','حتی'),'marker',0.5),(c('02','جفت',-0.1),'stamp',0.7),
(st('03',0.05),'typewriter',0.45),(st('03',0.55),'marker',0.4),(c('03','سان‌فرانسیسکو'),'typewriter',0.3),(c('03','نیک'),'marker',0.35),(c('03','بوت',-0.15),'pop',0.5),(c('03','سایز',0.1),'marker',0.45),(c('03','رنگِ',0.1),'marker',0.45),
(c('04','عجیب'),'pop',0.55),
(st('05',0),'pop',0.45),(c('05','عکس',-0.05),'shutter',0.7),(c('05','اینترنت',-0.2),'paper2',0.45),(c('05','خرید',-0.1),'pop',0.5),(c('05','قیمتِ',-0.15),'cashreg',0.4),
(c('06','انبار'),'marker',0.45),(c('06','موجودی'),'marker',0.45),(c('06','سرمایه‌ی'),'marker',0.45),(c('06','عکس'),'marker',0.4),
(c('07','دراپ‌شیپینگ',-0.25),'stamp',0.8),
(c('08','زاپوس',-0.15),'stamp',0.6),(c('08','ساپاتوس',-0.2),'typewriter',0.4),(c('08','فروخت'),'cashreg',0.4),
(c('09','دو',-0.1),'typewriter',0.45),(c('09','یک‌چهارمِ',-0.3),'marker',0.4),(c('09','گذاشتن',-0.1),'marker',0.5),
(c('10','چند'),'flip',0.5),(c('10','چند',0.35),'flip',0.5),(c('10','چند',0.7),'flip',0.5),(c('10','موجود',-0.1),'stamp',0.7),
(c('11','مدیرعاملِ'),'typewriter',0.3),
(st('12',0.3),'pin',0.5),(c('12','کنتاکی'),'pin',0.6),(c('12','یو‌پی‌اس',-0.3),'whoosh2',0.45),(c('12','ارسالِ',-0.05),'stamp',0.6),(c('12','مرجوعیِ',-0.05),'stamp',0.6),(c('12','عاشقش',-0.1),'marker',0.4),
(st('13',0.05),'typewriter',0.45),(c('13','میلیارد',0.2),'marker',0.45),(c('13','آمازون',-0.2),'paper2',0.5),(c('13','خریدش',-0.05),'stamp',0.7),
(c('14','دراپ‌شیپینگ',-0.2),'paper2',0.5),(c('14','برندها',-0.2),'paper',0.5),(c('14','تجربه‌ی'),'marker',0.45),(T-1.6,'sparkle',0.35)]
inputs=[];fc=[]
for n,(t,f,v) in enumerate(q):
    inputs+=['-i',FX+f+'.mp3']; ms=int(max(0,t)*1000)
    fc.append(f"[{n}:a]aformat=sample_rates=48000:channel_layouts=stereo,volume={v:.2f},adelay={ms}|{ms}[f{n}]")
n=len(q); vin=[]
for s in D['scenes']:
    inputs+=['-i',f"app/public/voice/proc/{s['id']}.wav"]; idx=len(inputs)//2-1; ms=int(s['start']*1000)
    fc.append(f"[{idx}:a]aformat=sample_rates=48000:channel_layouts=stereo,adelay={ms}|{ms}[v{s['id']}]"); vin.append(f"[v{s['id']}]")
inputs+=['-i','music.mp3']; mi=len(inputs)//2-1
fc.append("".join(vin)+f"amix=inputs={len(vin)}:normalize=0,highpass=f=70,acompressor=threshold=-18dB:ratio=3:attack=4:release=100:makeup=3dB,apad=whole_dur={T},asplit=2[voice][sc]")
fc.append(f"[{mi}:a]aformat=sample_rates=48000:channel_layouts=stereo,atrim=0:{T},volume=0.26,afade=t=in:d=0.5,afade=t=out:st={T-2.5:.2f}:d=2.5[mus0]")
fc.append("[mus0][sc]sidechaincompress=threshold=0.04:ratio=4:attack=20:release=350[mus]")
fc.append("".join(f"[f{k}]" for k in range(n))+f"amix=inputs={n}:normalize=0[fx]")
fc.append(f"[voice][mus][fx]amix=inputs=3:normalize=0,atrim=0:{T},alimiter=limit=0.95,loudnorm=I=-14:TP=-1.2:LRA=9[out]")
open('mix_fc.txt','w').write(';\n'.join(fc))
subprocess.run(['ffmpeg','-v','error','-y',*inputs,'-filter_complex_script','mix_fc.txt','-map','[out]','-ar','48000','mix.wav'],check=True)
print('ok',T,len(q))
