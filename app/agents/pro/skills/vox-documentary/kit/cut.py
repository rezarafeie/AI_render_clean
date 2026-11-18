import cv2, numpy as np
G='/home/claude/vox/gen/'; O='/home/claude/vox/app/public/img/'
def cell(sheet,r,c):
    im=cv2.imread(G+sheet); h,w=im.shape[:2]; cw,ch=w//3,h//2
    return im[r*ch:(r+1)*ch, c*cw:(c+1)*cw]
def up(im,f=2.5):
    im=cv2.resize(im,None,fx=f,fy=f,interpolation=cv2.INTER_LANCZOS4)
    bl=cv2.GaussianBlur(im,(0,0),1.2); return cv2.addWeighted(im,1.5,bl,-0.5,0)
def gray(im):
    g=cv2.cvtColor(im,cv2.COLOR_BGR2GRAY); g=cv2.convertScaleAbs(g,alpha=1.12,beta=-8); return cv2.cvtColor(g,cv2.COLOR_GRAY2BGR)
def cutout(name,sheet,r,c,border=14,minfrac=0.002):
    im=cell(sheet,r,c); h,w=im.shape[:2]
    g=im.astype(np.int16); white=((g.min(2)>226)).astype(np.uint8)*255
    m=np.zeros((h+2,w+2),np.uint8)
    for p in [(0,0),(w-1,0),(0,h-1),(w-1,h-1),(w//2,0),(w//2,h-1),(0,h//2),(w-1,h//2)]:
        if white[p[1],p[0]]==255: cv2.floodFill(white,m,p,128)
    fg=(white!=128).astype(np.uint8)
    fg=cv2.morphologyEx(fg,cv2.MORPH_CLOSE,np.ones((5,5),np.uint8)); fg=cv2.morphologyEx(fg,cv2.MORPH_OPEN,np.ones((3,3),np.uint8))
    n,lab,st,_=cv2.connectedComponentsWithStats(fg,8); keep=np.zeros_like(fg)
    for i in range(1,n):
        if st[i,4]>minfrac*h*w: keep[lab==i]=1
    # fill holes
    cnts,_=cv2.findContours(keep,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE); keep2=np.zeros_like(keep); cv2.drawContours(keep2,cnts,-1,1,-1)
    keep=keep2
    imu=up(gray(im)); km=cv2.resize(keep*255,(imu.shape[1],imu.shape[0]),interpolation=cv2.INTER_LINEAR)
    km=cv2.GaussianBlur(km,(0,0),1.0)
    b=int(border); dil=cv2.dilate((km>127).astype(np.uint8)*255,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(2*b+1,2*b+1)))
    dil=cv2.GaussianBlur(dil,(0,0),1.2)
    out=np.zeros((imu.shape[0],imu.shape[1],4),np.uint8)
    a=km.astype(np.float32)/255; 
    rgb=imu.astype(np.float32)*a[...,None]+255*(1-a[...,None])
    out[...,:3]=rgb.astype(np.uint8); out[...,3]=dil
    ys,xs=np.where(dil>10); pad=4
    out=out[max(0,ys.min()-pad):ys.max()+pad, max(0,xs.min()-pad):xs.max()+pad]
    cv2.imwrite(O+name+'.png',out); print(name,out.shape)
def photo(name,sheet,r,c):
    im=cell(sheet,r,c); g=cv2.cvtColor(im,cv2.COLOR_BGR2GRAY)
    ys,xs=np.where(g<235); im=im[ys.min():ys.max(),xs.min():xs.max()]
    imu=up(gray(im),2.5); cv2.imwrite(O+name+'.jpg',imu,[cv2.IMWRITE_JPEG_QUALITY,92]); print(name,imu.shape)
cutout('boots','A1.png',0,0); cutout('crt','A1.png',0,1); cutout('camera','A2.png',0,2)
cutout('shoebox','A1.png',1,0); cutout('boxes','A3.png',1,1); cutout('money','A1.png',1,2)
cutout('truck','B1.png',0,2); cutout('plane','B2.png',1,0); cutout('hands_shoe','B1.png',1,1)
cutout('walker','C1.png',0,0); cutout('suit','C1.png',0,1); cutout('crowd','C2.png',0,2); cutout('courier','C1.png',1,0)
photo('store','B2.png',0,0); photo('warehouse','B1.png',0,1); photo('shelf','B1.png',1,2); photo('woman_box','C1.png',1,1); photo('callcenter','C1.png',1,2)
