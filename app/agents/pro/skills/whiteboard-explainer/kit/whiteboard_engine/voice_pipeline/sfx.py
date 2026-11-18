import requests,sys,os
sys.path.insert(0,'.'); from key import key
K=key(); os.makedirs('sfx',exist_ok=True)
S={'marker1':('dry erase marker writing quickly on a glossy whiteboard, felt tip scratching strokes, close up, no voice',4),
'marker2':('drawing long lines with a whiteboard marker, smooth felt on gloss hiss, continuous, close mic',4),
'squeak':('single short dry erase marker squeak on whiteboard',1),
'cap':('marker cap pulled off with a small click pop',1),
'whoosh':('soft quick air whoosh, camera swipe transition, light',1),
'pop':('soft cartoon bubble pop, short, clean',1),
'ding':('cash register ding, short, bright',1.5),
'magnet':('small magnet snapping onto a metal whiteboard, click',1),
'tick':('positive check mark tick sound, short ui success blip',1)}
for k,(t,d) in S.items():
    if os.path.exists(f'sfx/{k}.mp3'): continue
    r=requests.post('https://api.elevenlabs.io/v1/sound-generation',headers={'xi-api-key':K},json={'text':t,'duration_seconds':d,'prompt_influence':0.6},timeout=120)
    print(k,r.status_code, '' if r.ok else r.text[:150])
    if r.ok: open(f'sfx/{k}.mp3','wb').write(r.content)
