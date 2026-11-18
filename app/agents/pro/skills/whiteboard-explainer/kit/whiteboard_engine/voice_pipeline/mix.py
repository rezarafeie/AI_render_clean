import json, subprocess, numpy as np, soundfile as sf, io
SR=48000
D=json.load(open('app/src/data.json')); TL=json.load(open('timeline.json')); T=TL['total']
N=int(T*SR)+SR
def load(p):
    b=subprocess.run(['ffmpeg','-v','error','-i',p,'-f','wav','-ar',str(SR),'-ac','2','-'],capture_output=True,check=True).stdout
    a,_=sf.read(io.BytesIO(b)); return a.astype(np.float32)
fx={k:load(f'app/public/sfx/{k}.mp3') for k in ['marker1','marker2','squeak','cap','whoosh','pop','ding','magnet','tick']}
def norm(a,peak=0.9): return a/(np.abs(a).max()+1e-9)*peak
for k in fx: fx[k]=norm(fx[k])
voice=np.zeros((N,2),np.float32); sfx=np.zeros((N,2),np.float32)
def add(buf,a,t,g=1.0,pan=0.0):
    i=int(t*SR); 
    if i<0: a=a[-i:]; i=0
    a=a[:N-i]*g; l=np.cos((pan+1)*np.pi/4)*1.41; r=np.sin((pan+1)*np.pi/4)*1.41
    buf[i:i+len(a),0]+=a[:,0]*l; buf[i:i+len(a),1]+=a[:,1]*r
for s in D['scenes']:
    v=load(f"voice/{s['id']}.wav")
    if s['split']:
        cut=int(s['split']['at']*SR); add(voice,v[:cut],s['start']); add(voice,v[cut:],s['start']+s['split']['at']+s['split']['hold'])
    else: add(voice,v,s['start'])
rng=np.random.default_rng(5)
def seg(src,dur):
    L=int(dur*SR); off=rng.integers(0,max(1,len(src)-L))
    a=src[off:off+L].copy()
    if len(a)<L: a=np.pad(a,((0,L-len(a)),(0,0)))
    f=min(int(0.03*SR),L//3); 
    if f>0: a[:f]*=np.linspace(0,1,f)[:,None]; a[-f:]*=np.linspace(1,0,f)[:,None]
    return a
for it in TL['items']:
    if it.get('snd')=='tick':
        add(sfx,fx['tick'],it['t0']+it['dur']*0.6,0.35,rng.uniform(-.2,.2))
    if it.get('snd') is None and it['k']!='text' and it.get('snd')!='marker' and it.get('snd')!='marker2':
        pass
    src=fx['marker1'] if it['k']=='text' else fx['marker2']
    g=0.20 if it['k']=='text' else 0.17
    add(sfx,seg(src,it['dur']+0.04),it['t0'],g,rng.uniform(-.35,.35))
    if it['k']!='text' and it['dur']>0.55 and rng.random()<0.25:
        add(sfx,fx['squeak'],it['t0']+it['dur']*0.5,0.12)
    if it.get('erase') and it['k']=='text':
        add(sfx,seg(fx['marker2'],it.get('erase')['dur']),it.get('erase')['t0'],0.32)
for e in TL['ev']: add(sfx,fx[e['k']],e['t'],e['g']*0.8)
mus=load('music.mp3')[:N]; mus=np.pad(mus,((0,max(0,N-len(mus))),(0,0)))
tt=np.arange(N)/SR
mus*= np.clip(tt/0.6,0,1)[:,None]*np.clip((T-tt)/2.8,0,1)[:,None]
# duck under voice
env=np.abs(voice).mean(1); w=int(0.05*SR); env=np.convolve(env,np.ones(w)/w,'same')
on=(env>0.01).astype(np.float32)
# smooth gate: attack 60ms release 400ms
g=np.zeros_like(on); a1=np.exp(-1/(0.06*SR)); r1=np.exp(-1/(0.4*SR)); x=0.0
for i in range(0,N,48):
    tgt=on[i]; c=a1 if tgt>x else r1; x=tgt+(x-tgt)*c**48; g[i:i+48]=x
musg=10**(-17/20)*(1-0.55*g)
voice=norm(voice,0.85)
mix=voice+sfx*0.55+mus*norm(mus,1.0).max()*musg[:,None]*norm(mus,1)/np.maximum(np.abs(mus).max(),1e-9)*np.abs(mus).max()
mix=voice+sfx*0.55+norm(mus,0.9)*musg[:,None]
mix=mix[:int(T*SR)]
sf.write('mix_raw.wav',mix,SR,subtype='FLOAT')
print('ok',mix.shape, np.abs(mix).max())
