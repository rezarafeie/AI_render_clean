"""Freeze previews ONLY from the dedicated synthetic native integration audit.

Refuses ordinary user projects. A source/component encode and the actual hybrid
browser check must pass; successful screenshots alone cannot promote a resource.
"""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    from creative.motion_graphic import MotionPage
    from creative.shotcraft_native import inspect_output, source_fingerprint, ShotcraftNative
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project",type=Path)
    parser.add_argument("--check-report",type=Path,required=True)
    args=parser.parse_args()
    project=args.project.resolve()
    marker=json.loads((project/"audit-fixture.json").read_text())
    if marker != {"purpose":"native-component-gallery","synthetic":True,"contains_user_media":False,"page_sha256":digest(project/"page.json")}:
        raise ValueError("Only an unchanged dedicated synthetic audit may become public")
    page=MotionPage.model_validate_json((project/"page.json").read_text())
    if page.audio or page.title!="Native component audit" or len(page.shotcraft_components)!=1:
        raise ValueError("Ordinary project/user assets must never enter the public gallery")
    mount=page.shotcraft_components[0]
    source=(project/mount.asset).resolve()
    if not source.is_relative_to(project): raise ValueError("Owned source path escaped")
    receipt=next(r for r in page.resource_receipts if r.get("integration")=="native-shotcraft-code")
    if receipt["artifact_sha256"]!=digest(source) or receipt["source_adapter_sha256"]!=source_fingerprint():
        raise ValueError("Stale or changed native audit source")
    report=json.loads(args.check_report.read_text())
    if not report.get("ok") or report.get("browserSkipped",True):
        raise ValueError("A real hybrid browser check must pass")
    report_file=Path(report.get("saved",{}).get("report",args.check_report)).resolve()
    if not report_file.is_relative_to(project):
        raise ValueError("Hybrid check must belong to this exact synthetic project")
    media=inspect_output(source,*page.size,mount.duration)
    outer=project/"hybrid.mp4"
    encoded=subprocess.run(["ffprobe","-v","error","-show_streams","-show_format","-of","json",str(outer)],
                           check=True,capture_output=True,text=True,timeout=20)
    meta=json.loads(encoded.stdout)
    stream=next(s for s in meta["streams"] if s["codec_type"]=="video")
    if stream["codec_name"]!="h264" or (stream["width"],stream["height"])!=page.size or abs(float(meta["format"]["duration"])-page.duration)>.1:
        raise ValueError("Actual hybrid encode does not match the approved fixture")
    gallery=ROOT/"web/public/creative-previews"
    stem="shotcraft-native-bezier-source-converge-merge"
    poster,video=gallery/(stem+".png"),gallery/(stem+".mp4")
    subprocess.run(["ffmpeg","-v","error","-y","-ss","1.5","-i",str(source),"-frames:v","1",str(poster)],check=True,capture_output=True,timeout=20)
    shutil.copy2(source,video)
    item={"id":mount.spec.resource_id,"name":stem,"status":"native-component-checked","format":page.format,
          "demonstration_only":True,"production_template_ready":True,"source_revision":receipt["source_revision"],
          "encoded_output_verified":True,"hybrid_browser_checked":True,"media":media,
          "source_adapter_sha256":receipt["source_adapter_sha256"],"hybrid_artifact_sha256":digest(outer),"hybrid_check_sha256":digest(args.check_report),
          "poster":"/creative-previews/"+poster.name,"preview_video":"/creative-previews/"+video.name,
          "poster_sha256":digest(poster),"video_sha256":digest(video),"parameters":ShotcraftNative.model_json_schema(),
          "use":"همگرایی چهار منبع تصویری، کارت، کد و صدا به یک خروجی. کد اصلی با متن فارسی، رنگ و آیکن کنترل‌شده اجرا می‌شود. نمونه بی‌صداست؛ صدا همچنان از مسیر فعلی EditorGPT می‌آید. سایر قالب‌های Shotcraft هنوز آمادهٔ تولید نیستند."}
    (gallery/"native-shotcraft.json").write_text(json.dumps({"schema_version":1,"items":{item["id"]:item}},ensure_ascii=False,indent=2))
    # Version every retained image so PWA/static caches cannot keep an older PNG.
    for filename in ["index.json","claude-effects.json","shotcraft.json","lemo.json"]:
        path=gallery/filename
        data=json.loads(path.read_text())
        for row in data["items"].values():
            url=row.get("poster","")
            if re.fullmatch(r"/creative-previews/[a-z0-9-]+\.png",url):
                row["poster_sha256"]=digest(gallery/url.rsplit("/",1)[1])
        path.write_text(json.dumps(data,ensure_ascii=False,indent=2))
    print(json.dumps({"id":item["id"],"status":item["status"],"poster":item["poster"],"video":item["preview_video"]}))


if __name__=="__main__":
    main()
