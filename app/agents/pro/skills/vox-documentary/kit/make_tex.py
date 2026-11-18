import numpy as np, cv2, json
rng=np.random.default_rng(3)
W,H=1080,1920
def noise(scale):
    n=rng.standard_normal((H//scale+2,W//scale+2)).astype(np.float32)
    return cv2.resize(n,(W,H),interpolation=cv2.INTER_CUBIC)
def crumple(seed_add=0):
    h=noise(240)*1.0+noise(120)*0.6+noise(48)*0.35+noise(16)*0.15
    # creases: sharp ridges
    cr=np.abs(noise(160))+np.abs(noise(90))*0.6
    h=h-cr*0.9
    gx=cv2.Sobel(h,cv2.CV_32F,1,0,ksize=5); gy=cv2.Sobel(h,cv2.CV_32F,0,1,ksize=5)
    shade=(-gx*0.6-gy*0.8); shade=shade/np.percentile(np.abs(shade),99)
    base=np.array([217,229,238],np.float32) # BGR of #EEE5D9
    img=base[None,None,:]*(1+0.06*shade[...,None])
    fib=rng.random((H,W))<0.004
    img[fib]*=0.9
    grain=rng.standard_normal((H,W)).astype(np.float32)*3.5
    img+=grain[...,None]
    # vignette
    yy,xx=np.mgrid[0:H,0:W]; d=np.sqrt(((xx-W/2)/W)**2+((yy-H/2)/H)**2)
    img*= (1-0.18*np.clip(d-0.25,0,1)[...,None])
    return np.clip(img,0,255).astype(np.uint8)
t=crumple(); cv2.imwrite('app/public/img/paper.jpg',t,[cv2.IMWRITE_JPEG_QUALITY,90])
g=t.copy().astype(np.float32)
for x in range(0,W,54): g[:,x:x+2]*=0.93
for y in range(0,H,54): g[y:y+2,:]*=0.93
cv2.imwrite('app/public/img/grid.jpg',np.clip(g,0,255).astype(np.uint8),[cv2.IMWRITE_JPEG_QUALITY,90])
# US map
d=json.load(open('us.json')); k=19.0; c=np.cos(np.radians(38))
def P(lon,lat): return ((lon+125)*c*k, (50-lat)*k)
paths={}
for f in d['features']:
    nm=f['properties']['name']
    if nm in ('Alaska','Hawaii','Puerto Rico'): continue
    g=f['geometry']; polys=g['coordinates'] if g['type']=='MultiPolygon' else [g['coordinates']]
    s=''
    for poly in polys:
        ring=poly[0]
        pts=[P(*q) for q in ring]
        s+='M'+' L'.join(f'{x:.1f},{y:.1f}' for x,y in pts)+'Z'
    paths[nm]=s
pts={'sf':P(-122.42,37.77),'ky':P(-85.72,37.99),'lv':P(-115.14,36.17)}
json.dump({'paths':paths,'pts':pts,'w':(125-66)*c*k,'h':(50-24)*k},open('app/src/usmap.json','w'))
print('ok',(125-66)*c*k,(50-24)*k,pts)
