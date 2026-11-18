import requests,sys,os
sys.path.insert(0,'.'); from key import key
K=key(); os.makedirs('sfx',exist_ok=True)
S={'key':('single soft mechanical keyboard key press, close mic, dry',0.5),
'hit':('deep punchy cinematic impact hit, tight sub thump, short, clean',1),
'thump':('soft rubber ball bounce on wooden floor, single, short',0.6),
'riser':('short airy synth riser whoosh building up, 1.5 seconds',1.6),
'swell':('warm soft pad swell with gentle shimmer, short',2),
'scan':('soft digital scanner sweep, light futuristic ui scanning tone',1.5),
'drop':('small cute cartoon character landing with soft bouncy boing, short',0.8),
'shutter':('camera shutter click, crisp, single',0.5),
'keys':('fast typing on laptop keyboard, close mic, 3 seconds',3),
'room':('quiet room tone at night, soft distant city hum, very calm',8)}
for k,(t,d) in S.items():
    if os.path.exists(f'sfx/{k}.mp3'): continue
    r=requests.post('https://api.elevenlabs.io/v1/sound-generation',headers={'xi-api-key':K},json={'text':t,'duration_seconds':d,'prompt_influence':0.6},timeout=120)
    print(k,r.status_code,'' if r.ok else r.text[:150])
    if r.ok: open(f'sfx/{k}.mp3','wb').write(r.content)
