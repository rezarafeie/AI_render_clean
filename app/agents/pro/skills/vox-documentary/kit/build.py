import json, re
A=json.load(open('voice_al.json',encoding='utf-8'))
LEAD,GAP,TAIL=0.35,0.22,2.2
ids=sorted(A)
scenes=[]; t=LEAD
for lid in ids:
    a=A[lid]; chars=a['chars']; st=a['starts']
    # words
    words=[]
    for m in re.finditer(r'[^\s]+',chars):
        w=m.group(0)
        if re.fullmatch(r'\[[a-z]+\]',w): continue
        clean=re.sub(r'[\.،,!؟?:…«»]+','',w)
        if not clean: continue
        words.append({'t':clean,'s':st[m.start()],'raw':w})
    for i,w in enumerate(words):
        w['e']=words[i+1]['s'] if i+1<len(words) else a['dur']
    scenes.append({'id':lid,'start':round(t,3),'dur':a['dur'],'words':words})
    t+=a['dur']+GAP
total=round(t-GAP+TAIL,3)
for i,s in enumerate(scenes):
    s['end']=scenes[i+1]['start'] if i+1<len(scenes) else total
json.dump({'total':total,'scenes':scenes},open('app/src/data.json','w'),ensure_ascii=False,indent=1)
print('total',total)
for s in scenes: print(s['id'],s['start'],s['dur'],' '.join(f"{w['t']}@{w['s']:.2f}" for w in s['words']))
