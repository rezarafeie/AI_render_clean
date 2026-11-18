import json, soundfile as sf
W=json.load(open('words.json')); GAP=0.45; t=0.5; sc=[]
for i in range(1,12):
    lid=f'{i:02d}'; d=sf.info(f'voice/{lid}.wav').duration
    words=W[lid]; split=None
    if lid=='11':  # hold after "نقشه‌ست."
        HOLD=1.6; sp=words[2]['e']+0.12; split={'at':round(sp,3),'hold':HOLD}
        words=[dict(w, s=round(w['s']+(HOLD if w['s']>sp else 0),3), e=round(w['e']+(HOLD if w['s']>sp else 0),3)) for w in words]
        d+=HOLD
    sc.append({'id':lid,'start':round(t,3),'dur':round(d,3),'words':words,'split':split}); t+=d+GAP
total=round(t-GAP+2.6,3)
json.dump({'scenes':sc,'total':total},open('app/src/data.json','w'),ensure_ascii=False)
print(total,[s['start'] for s in sc])
