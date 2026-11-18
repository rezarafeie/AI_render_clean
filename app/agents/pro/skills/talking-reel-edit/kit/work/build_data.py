import json, numpy as np
E=json.load(open('edl.json')); F=json.load(open('faces.json'))
W={w['i']:w for w in E['words']}
def ws(i): return W[i]['s']
def we(i): return W[i]['e']
T=round(E['total']+0.8,3)
# ---- beats: (word index, layout, graphic, zoom)
B=[
 (0,'full',None,1.28),
 (1,'split','service',1.0),
 (10,'full','coins',1.38),
 (12,'graphic','product',None),
 (20,'split','chart',1.0),
 (30,'graphic','two',None),
 (41,'split','phone',1.0),
 (48,'split','course',1.04),
 (54,'full',None,1.15),
 (58,'split','podcast',1.0),
 (68,'full','sparkle',1.32),
 (73,'split','years',1.0),
 (83,'split','boundless',1.04),
 (94,'graphic','saas',None),
 (103,'split','software',1.0),
 (110,'split','flow',1.04),
 (115,'full','coins2',1.36),
]
beats=[]
for k,(i,lay,g,z) in enumerate(B):
    s=0 if k==0 else round(ws(i)-0.06,3)
    beats.append({'w':i,'start':s,'layout':lay,'g':g,'zoom':z})
for k in range(len(beats)): beats[k]['end']=beats[k+1]['start'] if k+1<len(beats) else round(T,3)
# ---- captions: merge short function words with following word
SMALL={'که','به','رو','تو','یا','یه','این','از','هم','ما','اون','یک','as','a','توی','مثل','بهش'}
KEY={'خدمات','ثروت','محصول','بزرگ','scale','level','فیزیکیه','دیجیتاله','گوشی','دوره','آموزشی','پادکست','یوتیوب','جدیدی','دو','ساله','بدون','مرز','SaaS','Software','Service','نرم‌افزاری','بفروشه','دیجیتال','محصولای','می‌فروشی','فروختن'}
MONEY={'ثروت','بفروشه','می‌فروشی'}
ordered=E['words']; caps=[]; buf=[]
for w in ordered:
    buf.append(w)
    txt=w['t'].strip('.،—,')
    if txt in SMALL and len(buf)<2: continue
    caps.append(buf); buf=[]
if buf: caps.append(buf)
C=[]
for k,c in enumerate(caps):
    s=c[0]['s']-0.04; e=c[-1]['e']+0.25
    if k+1<len(caps): e=min(e,caps[k+1][0]['s']-0.04)
    words=[{'t':x['t'].strip('.،—,'),'key':x['t'].strip('.،—,') in KEY,'money':x['t'].strip('.،—,') in MONEY} for x in c]
    C.append({'s':round(s,3),'e':round(max(e,s+0.18),3),'words':words,'i':c[0]['i']})
# ---- sfx cues
S=[]
for k,b in enumerate(beats[1:]):
    S.append({'t':max(0,b['start']-0.12),'f':'whoosh' if k%2==0 else 'whoosh2','v':0.55})
def add(t,f,v=0.7): S.append({'t':round(max(0,t),3),'f':f,'v':v})
add(ws(1)+0.05,'pop'); add(ws(4),'stamp',0.8)
add(ws(10)-0.05,'coins',0.6); add(ws(12),'pop',0.6)
add(ws(21),'swipe',0.5); add(ws(24),'swipe',0.5); add(ws(27),'swipe',0.55)
add(ws(36)-0.05,'pop'); add(ws(39)-0.05,'pop')
add(ws(44)-0.05,'pop'); add(ws(49)-0.05,'pop'); add(ws(58),'pop')
add(ws(70)-0.1,'sparkle',0.6); add(ws(78),'swipe',0.5)
add(ws(88)-0.1,'sparkle',0.55)
add(ws(97)-1.5,'riser',0.5); add(ws(97)-0.02,'impact',0.6); add(ws(97)+0.05,'typing',0.35)
add(ws(99),'swipe',0.45)
add(ws(106),'typing',0.3); add(ws(113),'ding',0.55); add(ws(115)-0.05,'coins',0.6)
S.sort(key=lambda x:x['t'])
# ---- face track mapped to output time
segs=E['segs']
def m(x):
    for s,e,o in segs:
        if s<=x<=e: return o+(x-s)
    return None
pts=[(m(t),x) for t,x,y,w in F if x is not None and m(t) is not None]
pts.sort()
grid=np.arange(0,T+0.2,0.2)
ox=np.array([p[0] for p in pts]); xx=np.array([p[1] for p in pts])
raw=np.interp(grid,ox,xx)
k=np.ones(9)/9; sm=np.convolve(np.pad(raw,4,mode='edge'),k,mode='valid')
data={'total':T,'beats':beats,'caps':C,'sfx':S,'cuts':E['cuts'],'face':[round(v,1) for v in sm],'faceStep':0.2,'faceY':324,
      'kw':{str(i):ws(i) for i in [3,4,10,12,21,24,27,32,36,39,44,49,50,58,60,66,70,75,78,79,86,88,89,97,99,100,101,102,106,108,113,115]}}
json.dump(data,open('/home/claude/ed/app/src/data.json','w'),ensure_ascii=False,indent=1)
print(len(beats),'beats',len(C),'caps',len(S),'sfx'); print([ (b['g'],b['start'],b['end']) for b in beats])
