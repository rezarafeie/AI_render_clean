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


from creative.native_video_checks import inspect_native_frames as inspect_light_fixture_frames


def main():
    from creative.motion_graphic import MotionPage
    from creative.shotcraft_native import inspect_output, source_fingerprint, TextColumnNative,CardFlipNative,BeforeAfterNative,CardStackNative
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
    is_text=isinstance(mount.spec,TextColumnNative)
    is_card=isinstance(mount.spec,CardFlipNative)
    is_compare=isinstance(mount.spec,BeforeAfterNative)
    is_stack=isinstance(mount.spec,CardStackNative)
    if is_compare and receipt.get('input_sha256') != [
        '0d3ba527566871e7ea1cf05998a9d0249818cefee5ec09505523f185f948f711',
        '0819baf414ee2c56b4ac98fe99b55bffdcdd13e31ed9177377a0747d2054d3a6',
    ]:
        raise ValueError('Only the two reviewed synthetic geometric inputs may enter the public comparison gallery')
    if is_stack and receipt.get('input_sha256') != [
        '488201b70cbc174cdcf1fa92d7d1850c27430edebfa56e307c7e5beb86005c70',
        '69f649a7d4a280cf8c2d1dd9e1ae4b133298433dcc934c76fc41e42718d394ba',
        '658947a655d1ca7fddb0d9d325ed2b023f122bbf6bcfde8da281b715b43311f0',
        'a77fa533204271b0cd8c8033361b9488c06121f3b64c2ba5d480dd48b0a30790',
        '5ad86acccf4c1741ecea4f9d876f7d79654d910b32031c619121befb8f7ffe89',
        'd5ea2c4d604e17b47849eacdcc554b8fa1cad74f228f6cbf06dc1da852e7252e',
        '4a22eb73530bb09016832899b980d9dd0ed0a044a031f883d729290b37f309cc',
        'c670aa680f55a979d1e3668c05d792e63f14f566e649e3aa748f00d4fc74a586',
        '0d69275031b2b75b4a850fef7d192ae079bf59b284636c5f6a8b504f4b91093c',
    ]:
        raise ValueError('Only the nine reviewed synthetic geometric inputs may enter the public collection gallery')
    frame_audit=inspect_light_fixture_frames(source,dark_background=is_text or is_card,height=round(288*page.size[1]/page.size[0]))
    card_audit=None
    if is_card:
        from creative.native_video_checks import inspect_card_regions
        card_audit=inspect_card_regions(source,mount.spec,round(mount.duration*30))
    outer=project/"hybrid.mp4"
    encoded=subprocess.run(["ffprobe","-v","error","-show_streams","-show_format","-of","json",str(outer)],
                           check=True,capture_output=True,text=True,timeout=20)
    meta=json.loads(encoded.stdout)
    stream=next(s for s in meta["streams"] if s["codec_type"]=="video")
    if stream["codec_name"]!="h264" or (stream["width"],stream["height"])!=page.size or abs(float(meta["format"]["duration"])-page.duration)>.1:
        raise ValueError("Actual hybrid encode does not match the approved fixture")
    opening_audit=inspect_light_fixture_frames(outer,dark_background=is_text or is_card,height=round(288*page.size[1]/page.size[0]),expected_frames=1,first_frame_only=True)
    gallery=ROOT/"web/public/creative-previews"
    stem="shotcraft-native-"+mount.spec.resource_id.split(":",1)[1]
    poster,video=gallery/(stem+".png"),gallery/(stem+".mp4")
    subprocess.run(["ffmpeg","-v","error","-y","-ss",str(mount.duration-.3 if is_text or is_card or is_compare or is_stack else 1.5),"-i",str(source),"-frames:v","1",str(poster)],check=True,capture_output=True,timeout=20)
    shutil.copy2(source,video)
    item={"id":mount.spec.resource_id,"name":stem,"status":"native-component-checked","format":page.format,
          "demonstration_only":True,"production_template_ready":True,"source_revision":receipt["source_revision"],
          "encoded_output_verified":True,"hybrid_browser_checked":True,"media":media,
          "frame_audit":frame_audit,
          **({"card_region_audit":card_audit} if card_audit else {}),
          **({"input_sha256":receipt['input_sha256']} if is_compare or is_stack else {}),
          "hybrid_opening_audit":opening_audit,
          "source_adapter_sha256":receipt["source_adapter_sha256"],"hybrid_artifact_sha256":digest(outer),"hybrid_check_sha256":digest(args.check_report),
          "poster":"/creative-previews/"+poster.name,"preview_video":"/creative-previews/"+video.name,
          "poster_sha256":digest(poster),"video_sha256":digest(video),"parameters":type(mount.spec).model_json_schema(),
          "use":("نه تصویر واقعیِ ارائه‌شده، ورود پشته‌ای و بازشدن بادبزنی با کد اصلی. کارت پنجم برجسته می‌شود. این نمونه فقط تصاویر هندسی مصنوعی دارد؛ جلد و آمار ساختگی تولید نمی‌شود. چیدمان برای نمای کلی است، نه خواندن هم‌زمان نه کارت. فعلاً افقی و بی‌صدا." if is_stack else
                 "مقایسهٔ دو تصویر واقعیِ ارائه‌شده با اسلایدر کد اصلی. دو تصویر این نمونه هندسی و مصنوعی‌اند؛ هیچ ادعای بهبود یا تخریب ساختگی تصویر اول وجود ندارد. تصاویر کامل حفظ می‌شوند؛ فعلاً فقط افقی و بی‌صدا." if is_compare else
                 "سه کارت ویژگی با چرخش سه‌بعدی و نتیجهٔ عددی. اعداد این نمونه مصنوعی‌اند؛ استفادهٔ واقعی نیازمند داده و مرجع معتبر است. متن با فونت محلی سنجیده می‌شود؛ فعلاً فقط افقی. نمونه بی‌صداست." if is_card else
                 "چرخش ویژگی‌ها و یک بار جمع‌شدن به عبارت نهایی. متن فارسی با عرض واقعی فونت سنجیده می‌شود؛ فعلاً فقط افقی. نمونه بی‌صداست." if is_text else
                 "همگرایی چهار منبع تصویری، کارت، کد و صدا به یک خروجی. کد اصلی با متن فارسی، رنگ و آیکن کنترل‌شده اجرا می‌شود. نمونه بی‌صداست؛ صدا همچنان از مسیر فعلی EditorGPT می‌آید.")}
    manifest_path=gallery/"native-shotcraft.json"
    manifest=json.loads(manifest_path.read_text()) if manifest_path.exists() else {"schema_version":1,"items":{}}
    manifest["items"][item["id"]]=item
    manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
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
