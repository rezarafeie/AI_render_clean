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
    from creative.shotcraft_native import ShotcraftNative
    import engine.hyperframes.assets as assets
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project",type=Path)
    parser.add_argument("--gsap",type=Path,required=True)
    args=parser.parse_args()
    if args.project.exists():
        raise ValueError("Use a fresh audit directory; existing projects are never overwritten")
    if not args.gsap.is_file() or "GSAP 3.14.2" not in args.gsap.read_text()[:400]:
        raise ValueError("Supply the existing pinned GSAP runtime")
    assets.ensure_gsap=lambda:args.gsap
    args.project.mkdir(parents=True)
    caption="از ایده تا یک روایت روشن"
    plan=mg.MotionPlan(duration=9,title="Native component audit",scenes=[
        mg.ScenePlan(headline=caption,idea="Four media sources merge into a video",start=0,end=6,narration="این یک روایت روشن است.",
            shotcraft_component=ShotcraftNative(resource_id="shotcraft:bezier-source-converge-merge",caption=caption,
                source_icons=("shot","card","code","wave"),output_icon="play")),
        mg.ScenePlan(headline="داستانت را بساز",idea="A single CTA",start=6,end=9,narration="حالا شروع کنیم.",
            native_component=NativeMotion(resource_id="hyperframes:cta-close",text="داستانت را بساز",button_label="شروع کنیم")),
    ])
    problems=mg.validate_plan(plan)
    if problems: raise ValueError("Invalid audit plan: "+"; ".join(problems))
    page=mg.assemble_scenes(plan,[mg.author_scene(plan,n,"synthetic integration audit") for n in [1,2]])
    problems=mg.validate_page(page)
    if problems: raise ValueError("Invalid audit page: "+"; ".join(problems))
    mg.write_project(args.project,page,on_component_progress=lambda instance,pct:print(f"{instance}: {pct}%",flush=True))
    (args.project/"audit-fixture.json").write_text(json.dumps({"purpose":"native-component-gallery","synthetic":True,"contains_user_media":False,
        "page_sha256":hashlib.sha256((args.project/"page.json").read_bytes()).hexdigest()}))
    print(json.dumps({"project":str(args.project),"receipts":page.resource_receipts,"silent_synthetic_audit":True},ensure_ascii=False))


if __name__=="__main__":
    main()
