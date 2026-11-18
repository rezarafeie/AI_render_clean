import cv2, numpy as np, sys
I='/home/claude/ad/imgs/'; O='/home/claude/ad/app/public/img/'
def cut(src,name,y1=1.0,minfrac=0.0006,x0=0,y0=0,x1=1.0):
    im=cv2.imread(I+src); h,w=im.shape[:2]
    im=im[int(y0*h):int(y1*h), int(x0*w):int(x1*w)]
    h,w=im.shape[:2]
    g=im.astype(np.int16)
    white=((g.min(2)>232)&((g.max(2)-g.min(2))<18)).astype(np.uint8)
    # flood fill background from border through white pixels
    mask=np.zeros((h+2,w+2),np.uint8); bg=np.zeros((h,w),np.uint8)
    ff=white.copy()*255
    for (x,y) in [(0,0),(w-1,0),(0,h-1),(w-1,h-1),(w//2,0),(w//2,h-1),(0,h//2),(w-1,h//2)]:
        if ff[y,x]==255: cv2.floodFill(ff,mask,(x,y),128)
    bg=(ff==128).astype(np.uint8)
    fg=1-bg
    fg=cv2.morphologyEx(fg,cv2.MORPH_OPEN,np.ones((3,3),np.uint8))
    n,lab,stats,_=cv2.connectedComponentsWithStats(fg,8)
    keep=np.zeros_like(fg)
    for i in range(1,n):
        if stats[i,cv2.CC_STAT_AREA]>minfrac*h*w: keep[lab==i]=1
    a=cv2.GaussianBlur(keep.astype(np.float32),(0,0),1.2)
    a=np.clip(a*1.15,0,1)
    ys,xs=np.where(keep>0); pad=10
    yA,yB,xA,xB=max(0,ys.min()-pad),min(h,ys.max()+pad),max(0,xs.min()-pad),min(w,xs.max()+pad)
    rgba=np.dstack([im,(a*255).astype(np.uint8)])[yA:yB,xA:xB]
    s=1200/max(rgba.shape[:2])
    if s<1: rgba=cv2.resize(rgba,None,fx=s,fy=s,interpolation=cv2.INTER_AREA)
    cv2.imwrite(O+name+'.png',rgba); print(name,rgba.shape)
cut('p01.jpg','kit_open')
cut('p08.jpg','kit_closed')
cut('p03.jpg','wrench',y1=0.80)
cut('p02.jpg','hammer',minfrac=0.01)
cut('p04.jpg','grinder',y1=0.72)
cut('p05.jpg','ratchet',y1=0.70)
for s,n in [('p07.jpg','accessories'),('p06.jpg','parts')]:
    im=cv2.imread(I+s); im=cv2.resize(im,(1200,1200),interpolation=cv2.INTER_AREA); cv2.imwrite(O+n+'.jpg',im,[cv2.IMWRITE_JPEG_QUALITY,92]); print(n)
cut('p04.jpg','grinder_only',y1=0.44)
cut('p04.jpg','stones',y0=0.44,y1=0.72)
cut('p05.jpg','ratchet_only',y1=0.47)
cut('p05.jpg','bits',y0=0.47,y1=0.70)
