import json, subprocess, numpy as np, soundfile as sf, io, sys, os
SR=48000
name=sys.argv[1]; music=sys.argv[2]; mgain=float(sys.argv[3]); moff=float(sys.argv[4]) if len(sys.argv)>4 else 0
E=json.load(open('ev.json'))[name]; T=E['dur']; N=int(T*SR)
def load(p):
    b=subprocess.run(['ffmpeg','-v','error','-i',p,'-f','wav','-ar',str(SR),'-ac','2','-'],capture_output=True,check=True).stdout
    a,_=sf.read(io.BytesIO(b)); return a.astype(np.float32)
def norm(a,peak=0.9): return a/(np.abs(a).max()+1e-9)*peak
fx={}
def F(k):
    if k not in fx: fx[k]=norm(load(f'audio/sfx/{k}.mp3'))
    return fx[k]
buf=np.zeros((N+SR*4,2),np.float32)
def add(b,a,t,g=1.0):
    i=int(max(0,t)*SR); a=a[:len(b)-i]*g; b[i:i+len(a)]+=a
for e in E['ev']: add(buf,F(e['k']),e['t'],e.get('g',0.6)*0.7)
voice=np.zeros_like(buf)
for v in E.get('voice',[]): add(voice,load(v['f']),v['t'],1.0)
if E.get('voice'): voice=norm(voice,0.85)
mus=load(music)[int(moff*SR):]; mus=norm(np.pad(mus,((0,max(0,len(buf)-len(mus))),(0,0)))[:len(buf)],0.9)
tt=np.arange(len(buf))/SR
mus*=np.clip(tt/0.15,0,1)[:,None]*np.clip((T-tt)/float(E.get('fade',1.5)),0,1)[:,None]
g=np.ones(len(buf),np.float32)
if E.get('voice'):
    env=np.abs(voice).mean(1); w=int(0.05*SR); env=np.convolve(env,np.ones(w)/w,'same'); on=(env>0.01).astype(np.float32)
    x=0.0; a1=np.exp(-48/(0.06*SR)); r1=np.exp(-48/(0.45*SR))
    for i in range(0,len(buf),48):
        tg=on[i]; c=a1 if tg>x else r1; x=tg+(x-tg)*c; g[i:i+48]=1-0.6*x
mix=(voice+buf*0.6+mus*mgain*g[:,None])[:N]
sf.write(f'audio/{name}_raw.wav',mix,SR,subtype='FLOAT')
log=subprocess.run(['ffmpeg','-hide_banner','-i',f'audio/{name}_raw.wav','-af','loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json','-f','null','-'],capture_output=True,text=True).stderr
j=json.loads(log[log.rindex('{'):])
subprocess.run(['ffmpeg','-v','error','-y','-i',f'audio/{name}_raw.wav','-af',f"loudnorm=I=-14:TP=-1.5:LRA=11:measured_I={j['input_i']}:measured_TP={j['input_tp']}:measured_LRA={j['input_lra']}:measured_thresh={j['input_thresh']}:offset={j['target_offset']}:linear=true,alimiter=limit=0.84:level=false",'-ar','48000',f'audio/{name}.wav'],check=True)
print(name,'in',j['input_i'],'LUFS')
