import json,base64,requests,sys,os
sys.path.insert(0,'.'); from key import key
K=key(); V='wEMHmIPIdyXK6OkgkB03'
os.makedirs('voice',exist_ok=True)
only=sys.argv[1:]
for lid,text in json.load(open('lines.json',encoding='utf-8')):
    if only and lid not in only: continue
    r=requests.post(f'https://api.elevenlabs.io/v1/text-to-speech/{V}/with-timestamps?output_format=mp3_44100_128',
      headers={'xi-api-key':K,'Content-Type':'application/json'},
      json={'text':text,'model_id':'eleven_v3'},timeout=180)
    if r.status_code!=200: print(lid,'ERR',r.status_code,r.text[:200]); continue
    d=r.json(); open(f'voice/{lid}.mp3','wb').write(base64.b64decode(d['audio_base64']))
    json.dump(d.get('alignment'),open(f'voice/{lid}.al.json','w'),ensure_ascii=False)
    print(lid,'ok')
