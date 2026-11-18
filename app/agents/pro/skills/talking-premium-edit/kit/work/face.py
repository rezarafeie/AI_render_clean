import cv2, json, sys, numpy as np
cap=cv2.VideoCapture(sys.argv[1]); fps=cap.get(5); n=int(cap.get(7))
fc=cv2.CascadeClassifier("/home/claude/v3/work/haarcascade_frontalface_default.xml")
pc=cv2.CascadeClassifier("/home/claude/v3/work/haarcascade_profileface.xml")
out=[]; i=0; step=int(fps/5)
while True:
    ok=cap.grab()
    if not ok: break
    if i%step==0:
        _,f=cap.retrieve(); g=cv2.cvtColor(cv2.resize(f,(960,540)),cv2.COLOR_BGR2GRAY)
        fs=list(fc.detectMultiScale(g,1.1,5,minSize=(50,50)))
        if not len(fs): fs=list(pc.detectMultiScale(g,1.1,4,minSize=(50,50)))
        if not len(fs): fs=list(pc.detectMultiScale(cv2.flip(g,1),1.1,4,minSize=(50,50))); fs=[(960-x-w,y,w,h) for x,y,w,h in fs]
        if len(fs):
            x,y,w,h=max(fs,key=lambda r:r[2]*r[3]); out.append([i/fps,float(x+w/2)*2,float(y+h/2)*2,float(w)*2])
        else: out.append([i/fps,None,None,None])
    i+=1
json.dump(out,open(sys.argv[2],"w"))
xs=[o[1] for o in out if o[1]]; print(len(out),len(xs),np.percentile(xs,[5,50,95]),np.median([o[2] for o in out if o[2]]),np.median([o[3] for o in out if o[3]]))
