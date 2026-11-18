import subprocess, os, glob, numpy as np
from rembg import new_session, remove
from PIL import Image
W=[(4.70,7.05),(7.90,9.70),(28.85,31.25),(38.85,42.23)]
s=new_session('u2net_human_seg')
for k,(a,b) in enumerate(W):
    d=f'seg/w{k}'; os.makedirs(d+'/in',exist_ok=True); os.makedirs(d+'/out',exist_ok=True)
    subprocess.run(['ffmpeg','-v','error','-y','-ss',str(a),'-i','graded.mp4','-t',str(b-a),'-vf','crop=812:1080:300:0','-start_number','0',d+'/in/%04d.png'],check=True)
    for f in sorted(glob.glob(d+'/in/*.png')):
        o=f.replace('/in/','/out/')
        if os.path.exists(o): continue
        im=Image.open(f).convert('RGB')
        m=remove(im,session=s,only_mask=True,post_process_mask=True)
        rgba=im.copy(); rgba.putalpha(m); rgba.save(o)
    subprocess.run(['ffmpeg','-v','error','-y','-framerate','30','-i',d+'/out/%04d.png','-c:v','libvpx-vp9','-pix_fmt','yuva420p','-b:v','4M','-auto-alt-ref','0',f'seg/fg{k}.webm'],check=True)
    print('done',k,flush=True)
