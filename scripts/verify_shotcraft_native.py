"""Build a synthetic two-scene native Shotcraft + HyperFrames integration audit.

No AI, voice generation or user media. Uses the existing local renderers.
Run the pinned HyperFrames check/render on the returned project directory.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    from creative import motion_graphic as mg
    from creative.native_motion import NativeMotion
    from creative.shotcraft_native import ShotcraftNative,TextColumnNative,CardFlipNative
    import engine.hyperframes.assets as assets
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project",type=Path)
    parser.add_argument("--gsap",type=Path,required=True)
    parser.add_argument("--component",choices=["convergence","text-column","card-flip"],default="convergence")
    parser.add_argument("--refresh-audit",action="store_true",help="Refresh only an unchanged dedicated synthetic audit, reusing its verified native cache")
    args=parser.parse_args()
    if args.project.exists():
        if not args.refresh_audit:
            raise ValueError("Use a fresh audit directory; existing projects are never overwritten")
        marker=json.loads((args.project/"audit-fixture.json").read_text())
        page_path=args.project/"page.json"
        old=mg.MotionPage.model_validate_json(page_path.read_text())
        if marker!={"purpose":"native-component-gallery","synthetic":True,"contains_user_media":False,
                    "page_sha256":hashlib.sha256(page_path.read_bytes()).hexdigest()} or old.title!="Native component audit" or old.audio:
            raise ValueError("Refusing to overwrite a non-audit or changed project")
    if not args.gsap.is_file() or "GSAP 3.14.2" not in args.gsap.read_text()[:400]:
        raise ValueError("Supply the existing pinned GSAP runtime")
    assets.ensure_gsap=lambda:args.gsap
    args.project.mkdir(parents=True,exist_ok=args.refresh_audit)
    caption="از ایده تا یک روایت روشن"
    plan=mg.MotionPlan(duration=9,title="Native component audit",scenes=[
        mg.ScenePlan(headline=caption,idea="Four media sources merge into a video",start=0,end=6,narration="این یک روایت روشن است.",
            shotcraft_component=ShotcraftNative(resource_id="shotcraft:bezier-source-converge-merge",caption=caption,
                source_icons=("shot","card","code","wave"),output_icon="play")),
        mg.ScenePlan(headline="داستانت را بساز",idea="A single CTA",start=6,end=9,narration="حالا شروع کنیم.",
            native_component=NativeMotion(resource_id="hyperframes:cta-close",text="داستانت را بساز",button_label="شروع کنیم")),
    ])
    if args.component=="text-column":
        caption="روایت روشن"
        plan.format="horizontal"
        plan.scenes[0]=mg.ScenePlan(headline=caption,idea="Features converge into one final phrase",start=0,end=6,narration="یک روایت روشن بسازیم.",
            shotcraft_component=TextColumnNative(resource_id="shotcraft:text-column-converge",caption=caption,
                prefix="یک",features=("ایده","تصویر","صدا"),subtitle="از ایده تا نتیجه"))
        plan.scenes[1].native_component=None
    if args.component=="card-flip":
        caption="سه ویژگی، سه نتیجه"
        plan.format="horizontal"
        plan.duration=13
        cards=[dict(name=name,description=desc,front_lines=lines,before=before,after=after,unit="دقیقه",
                    result_label="زمان آزمایشی",evidence="اعداد مصنوعی برای آزمون فنی؛ ادعای عملکرد واقعی نیست")
               for name,desc,lines,before,after in [
                   ("برنامه‌ریزی","از ایده تا برنامه",["هدف روشن","برنامهٔ مشخص","اجرای منظم"],20,10),
                   ("تدوین","از تصویر تا روایت",["انتخاب تصویر","تنظیم ریتم","خروجی نهایی"],30,15),
                   ("بازبینی","از بررسی تا اصلاح",["بررسی متن","کنترل تصویر","اصلاح نهایی"],12,6)]]
        plan.scenes[0]=mg.ScenePlan(headline=caption,idea="Three abstract feature summaries flip into synthetic numeric comparisons",start=0,end=10,narration="این فقط نمونهٔ آزمایشی است.",
            shotcraft_component=CardFlipNative(resource_id="shotcraft:card-flip-reveal",caption=caption,kicker="نمونهٔ آزمایشی",
                front_label="ویژگی",before_label="قبل",after_label="بعد",cards=cards))
        plan.scenes[1].start=10;plan.scenes[1].end=13;plan.scenes[1].native_component=None
    problems=mg.validate_plan(plan)
    if problems: raise ValueError("Invalid audit plan: "+"; ".join(problems))
    drafts=[mg.author_scene(plan,1,"synthetic integration audit")]
    if args.component in {"text-column","card-flip"}:
        drafts.append(mg.SceneDraft(html='<div style="position:absolute;inset:0;display:grid;place-items:center;background:#08090c;color:#eeeef2;font:60px Ray;line-height:1.5">داستانت را بساز</div>',build_js='tl.to({}, {duration:3}, 0);',timebase="local"))
    else:
        drafts.append(mg.author_scene(plan,2,"synthetic integration audit"))
    page=mg.assemble_scenes(plan,drafts)
    problems=mg.validate_page(page)
    if problems: raise ValueError("Invalid audit page: "+"; ".join(problems))
    mg.write_project(args.project,page,on_component_progress=lambda instance,pct:print(f"{instance}: {pct}%",flush=True))
    (args.project/"audit-fixture.json").write_text(json.dumps({"purpose":"native-component-gallery","synthetic":True,"contains_user_media":False,
        "page_sha256":hashlib.sha256((args.project/"page.json").read_bytes()).hexdigest()}))
    print(json.dumps({"project":str(args.project),"receipts":page.resource_receipts,"silent_synthetic_audit":True},ensure_ascii=False))


if __name__=="__main__":
    main()
