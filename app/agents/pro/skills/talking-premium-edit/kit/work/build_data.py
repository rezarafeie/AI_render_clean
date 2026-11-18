import json, numpy as np
E=json.load(open('edl.json')); F=json.load(open('faces.json'))
W={w['i']:w for w in E['words']}
T=round(E['total']+1.0,3)
CH=[([1,2,3],['قبل']),([5,6,7],['وارد']),([8,10,11,12],['اولین','قسمت']),([13,14,15],[]),([16,17,18],['overview']),([19,20,21],[]),
([22,23,24],['پروژه']),([25,26],['__TB']),([27,28,29,30],['اتفاقی']),([31,32,33,34],['اولین','قسمت']),([35,36,37],[]),([38,39,40,41],[]),([42,43],[]),
([44,45],['بدون','مرز']),([46,47,48,49,50],['وجود']),([51,52],['مسیر']),([53,54,55,56],['درد']),([57,58,59],['درستتون']),([60,61,62,63],['پیدا']),
([64,65],['ابزارهایی']),([66,67,68],['انتخاب']),([69,70],[]),([71,72,73],['اتفاقی']),([74,75,76],['خود','من']),([77,78,79],['اتفاقی']),([80,81],['دانش‌پذیرها']),
([82,83,84],['نگرش‌هایی']),([85,86,87],['__TB']),([88,89],[]),([90,91],['ذهن']),([92,93],['پذیرش']),([94,95,96],[]),([97,98,99,100],['قسمت','دوم']),
([101,102,103],[]),([104,105,106],[]),([107,108,109,110],[]),([111,112],['__TB']),([113,114,115],['پروژه'])]
caps=[]
for k,(ids,keys) in enumerate(CH):
    ws=[W[i] for i in ids]
    nxt=W[CH[k+1][0][0]]['s'] if k+1<len(CH) else T
    s=ws[0]['s']-0.05; e=min(ws[-1]['e']+0.35,nxt-0.05)
    words=[{'t':w['t'].strip('.،—,'),'s':w['s'],'key':w['t'].strip('.،—,') in keys} for w in ws]
    caps.append({'s':round(s,3),'e':round(max(e,s+0.3),3),'words':words,'hide':'__TB' in keys,'big':any(x['key'] for x in words)})
def ws_(i): return W[i]['s']
tb=[{'s':4.70,'e':7.05,'kind':'overview'},{'s':7.90,'e':9.70,'kind':'brand'},{'s':28.85,'e':31.25,'kind':'important'},{'s':38.85,'e':T,'kind':'most'}]
topics=[{'s':ws_(44)-0.15,'title':'بدون مرز چطور به وجود اومد','icon':'spark'},{'s':ws_(51)-0.1,'title':'کدوم مسیر به دردت می‌خوره','icon':'fork'},
{'s':ws_(57)-0.1,'title':'چطور مسیر درستت رو پیدا کنی','icon':'compass'},{'s':ws_(64)-0.1,'title':'ابزارهای انتخاب مسیر','icon':'tools'},
{'s':ws_(71)-0.1,'title':'چه اتفاقی برای خودم افتاد','icon':'user'},{'s':ws_(77)-0.1,'title':'نتیجه‌ی دانش‌پذیرها','icon':'group'}]
for i,t in enumerate(topics): t['e']=topics[i+1]['s'] if i+1<len(topics) else ws_(82)-0.1
# face track (faces.json already in output time)
pts=[(t,x) for t,x,y,w in F if x is not None]
grid=np.arange(0,T+0.2,0.2); raw=np.interp(grid,[p[0] for p in pts],[p[1] for p in pts])
sm=np.convolve(np.pad(raw,6,mode='edge'),np.ones(13)/13,mode='valid')
kw={str(i):W[i]['s'] for i in W}
data={'total':T,'cuts':E['cuts'],'caps':caps,'tb':tb,'topics':topics,'face':[round(v,1) for v in sm],'faceStep':0.2,'faceY':424,'kw':kw}
json.dump(data,open('/home/claude/v3/app/src/data.json','w'),ensure_ascii=False,indent=1)
print(T,len(caps),[ (round(t['s'],2),round(t['e'],2)) for t in topics])
