# Builds src/timing.json from voice clips (voice/NN.mp3 + optional NN.json alignment) or placeholder estimates.
import json, os, subprocess, sys
H=os.path.dirname(os.path.abspath(__file__)); V=os.path.join(H,"public","voice")
lines=json.load(open(os.path.join(H,"lines.json"),encoding="utf-8"))
GAP=0.22; LEAD=0.25; TAIL=2.6; TEMPO=1.12
os.makedirs(os.path.join(V,"proc"),exist_ok=True)
t=LEAD; scenes=[]
for lid,text in lines:
    mp3=os.path.join(V,lid+".mp3"); al=None
    if os.path.exists(mp3):
        pw=os.path.join(V,"proc",lid+".wav")
        subprocess.run(["ffmpeg","-v","error","-y","-i",mp3,"-af",f"atempo={TEMPO}","-ar","48000","-ac","2",pw],check=True)
        dur=float(subprocess.check_output(["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",pw]))
        js=os.path.join(V,lid+".json")
        if os.path.exists(js):
            a=json.load(open(js,encoding="utf-8"))
            if a: al={"chars":"".join(a["characters"]),"starts":[round(x/TEMPO,3) for x in a["character_start_times_seconds"]]}
        if not al and os.path.exists(os.path.join(V,lid+".words.json")):
            al=json.load(open(os.path.join(V,lid+".words.json"),encoding="utf-8"))
    else:
        dur=len(text)/13.5+0.3
    scenes.append({"id":lid,"text":text,"start":round(t,3),"dur":round(dur,3),"audio":os.path.exists(mp3),"al":al})
    t+=dur+GAP
json.dump({"fps":30,"total":round(t+TAIL,3),"scenes":scenes},open(os.path.join(H,"src","timing.json"),"w",encoding="utf-8"),ensure_ascii=False,indent=1)
print("total",round(t+TAIL,2),[ (s["id"],s["dur"]) for s in scenes])
