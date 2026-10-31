"""Typed native binding/cache tests; external rendering is explicitly mocked.

Actual encoded output is verified separately by the retained local render audit.
"""
import hashlib
import json
import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

from creative import shotcraft_native as native


def spec(**overrides):
    return native.ShotcraftNative(resource_id="shotcraft:bezier-source-converge-merge",
        caption="از ایده تا روایت",source_icons=("shot","card","code","wave"),**overrides)


@pytest.mark.parametrize("patch", [
    {"resource_id":"../../secret"},{"caption":"<script>"},{"caption":" "},{"caption":"الف"*50},
    {"source_icons":["shot"]},{"source_icons":["shot","card","code","shell"]},{"accent":"url(secret)"},
    {"output_icon":"<svg>"},{"arbitrary_js":"alert(1)"},
])
def test_invalid_native_arguments_fail_closed(patch):
    values=spec().model_dump();values.update(patch)
    with pytest.raises(ValidationError):
        native.ShotcraftNative.model_validate(values)


def test_original_source_binds_data_without_changing_vendor_bytes():
    source=native.ROOT/"creative/shotcraft_data/demos/ui-entrance/bezier-source-converge-merge/BezierSourceConvergeMerge.tsx"
    before=hashlib.sha256(source.read_bytes()).hexdigest()
    script='''const fs=require('fs');const loader=require('./remotion/shotcraft-content-loader.cjs');
const result=loader.call({getOptions:()=>({spec:JSON.parse(process.argv[1]),width:1080,height:1920,frames:180})},fs.readFileSync(process.argv[2],'utf8'));
process.stdout.write(result);'''
    result=subprocess.run(["node","-e",script,json.dumps(spec().model_dump()),str(source)],cwd=native.ROOT,
                          capture_output=True,text=True,check=True,timeout=20).stdout
    assert '<ShotcraftMark ' not in result
    assert 'const CAP_WORDS = "از ایده تا روایت"' in result
    assert 'const mkPathGeom' in result and 'const GEOMS = SRCS.map' in result
    assert 'const t = 0.2 + 0.8 * Math.min(1, useT()' in result
    assert 'h={853.3333333333334}' in result
    assert before==hashlib.sha256(source.read_bytes()).hexdigest()


def test_render_cache_and_content_invalidation_use_existing_renderer(tmp_path,monkeypatch):
    from engine import remotion_renderer
    calls=[]
    def mocked_render(config,output,**kwargs):
        calls.append(config)
        output.write_bytes(b'mocked encoded bytes, not an actual video')
    monkeypatch.setattr(remotion_renderer,"render",mocked_render)
    monkeypatch.setattr(native,"source_fingerprint",lambda:"pinned-test-source")
    monkeypatch.setattr(native,"inspect_output",lambda p,w,h,s:{"width":w,"height":h,"duration":s,"codec":"mocked"})
    first=native.materialize(tmp_path,spec(),"s1-shotcraft",6,"vertical")
    second=native.materialize(tmp_path,spec(),"s1-shotcraft",6,"vertical")
    assert first==second and len(calls)==1
    assert calls[0]["version"]==3 and calls[0]["scenes"][0]["shotcraft"]["caption"]==spec().caption
    revised=spec().model_copy(update={"caption":"روایت روشن"})
    third=native.materialize(tmp_path,revised,"s1-shotcraft",6,"vertical")
    assert len(calls)==2 and third["asset"]!=first["asset"]


def test_paths_and_dimensions_cannot_escape_owned_project(tmp_path):
    with pytest.raises(ValueError):
        native.materialize(tmp_path,spec(),"../escape",6,"vertical")
    with pytest.raises(ValueError):
        native.materialize(tmp_path,spec(),"s1-shotcraft",600,"vertical")
    outside=tmp_path/"outside";outside.mkdir()
    project=tmp_path/"project";project.mkdir();(project/"assets").symlink_to(outside,target_is_directory=True)
    with pytest.raises(ValueError,match="escapes"):
        native.materialize(project,spec(),"s1-shotcraft",6,"vertical")


def test_source_and_runtime_are_pinned():
    assert len(native.source_fingerprint())==64


def test_caption_reading_hold_is_not_cut_short(tmp_path):
    values=spec().model_dump();values["caption"]="یک دو سه چهار پنج شش هفت هشت"
    long=native.ShotcraftNative.model_validate(values)
    assert native.required_seconds(long)==5.6
    with pytest.raises(ValueError):
        native.materialize(tmp_path,long,"s1-shotcraft",4,"vertical")


@pytest.mark.parametrize("gop,valid", [(30,True),(150,False)])
def test_actual_encoded_keyframe_cadence_is_checked(tmp_path,gop,valid):
    import shutil
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("Native media tools unavailable")
    clip=tmp_path/"cadence.mp4"
    subprocess.run(["ffmpeg","-v","error","-y","-f","lavfi","-i","color=c=blue:s=64x96:r=30:d=2.5",
                    "-c:v","libx264","-pix_fmt","yuv420p","-g",str(gop),"-keyint_min",str(gop),"-sc_threshold","0",str(clip)],
                   capture_output=True,check=True,timeout=20)
    if valid:
        assert native.inspect_output(clip,64,96,2.5)["max_keyframe_interval"]<=1
    else:
        with pytest.raises(ValueError,match="keyframes"):
            native.inspect_output(clip,64,96,2.5)


def sample_page(monkeypatch):
    from creative import motion_graphic as mg
    monkeypatch.setattr(mg.llm,"ask",lambda *a,**kw:pytest.fail("Original native code must not be rewritten by a model"))
    plan=mg.MotionPlan(duration=10,scenes=[
        mg.ScenePlan(headline=spec().caption,idea="converge",start=0,end=6,shotcraft_component=spec()),
        mg.ScenePlan(headline="مرحلهٔ بعد",idea="next",start=6,end=10),
    ])
    first=mg.author_scene(plan,1,"audit")
    second=mg.SceneDraft(html='<h1>مرحلهٔ بعد</h1>',build_js='tl.to({}, {duration:4}, 0);',timebase="local")
    return plan,mg.assemble_scenes(plan,[first,second])


def test_assembly_keeps_video_in_platform_code_not_agent_markup(monkeypatch,tmp_path):
    from creative import motion_graphic as mg
    import engine.hyperframes.assets as assets
    plan,page=sample_page(monkeypatch)
    assert len(page.shotcraft_components)==1 and not page.native_components
    assert '<video' not in page.scenes_html and 's1-shotcraft-slot' in page.scenes_html
    assert not mg.validate_page(page)
    runtime=tmp_path/"gsap.js";runtime.write_text("// test local runtime")
    monkeypatch.setattr(assets,"ensure_gsap",lambda:runtime)
    def mocked_materialize(project,selected,instance,duration,format,**kwargs):
        assert selected==spec() and duration==6 and format=="vertical"
        kwargs["on_progress"](100)
        return {"integration":"native-shotcraft-code","asset":"assets/s1-shotcraft-0123456789abcdef.mp4"}
    monkeypatch.setattr(native,"materialize",mocked_materialize)
    monkeypatch.setattr("creative.native_video_checks.inspect_native_frames",lambda *a,**kw:{"decoded_frames":180,"mocked":True})
    progress=[]
    mg.write_project(tmp_path/"project",page,on_component_progress=lambda instance,pct:progress.append((instance,pct)))
    html=(tmp_path/"project/index.html").read_text()
    assert '<video id="s1-shotcraft-video" class="clip"' in html
    assert 'data-start="0" data-duration="6"' in html
    assert 'tl.set("#s1", {opacity:1}, 0)' in html
    assert 'duration:.001' not in page.build_js
    assert '<video' not in page.scenes_html  # Trusted media is injected only at assembly.
    assert progress==[("s1-shotcraft",100)]
    page.scenes_html+='<video src="https://untrusted.invalid/video.mp4"></video>'
    assert mg.validate_page(page)  # Native references never relax the agent HTML allowlist.


def test_native_mount_cannot_reference_another_instance(monkeypatch):
    from creative import motion_graphic as mg
    _,page=sample_page(monkeypatch)
    page.shotcraft_components=[page.shotcraft_components[0].model_copy(update={"asset":"assets/s2-shotcraft-0123456789abcdef.mp4"})]
    with pytest.raises(ValueError,match="owned artifact"):
        mg.assemble(page)


def test_blank_native_video_cannot_be_published_as_a_page(monkeypatch,tmp_path):
    from creative import motion_graphic as mg
    import engine.hyperframes.assets as assets
    _,page=sample_page(monkeypatch)
    runtime=tmp_path/"gsap.js";runtime.write_text("// local test fixture")
    monkeypatch.setattr(assets,"ensure_gsap",lambda:runtime)
    monkeypatch.setattr(native,"materialize",lambda *a,**kw:{"asset":"assets/s1-shotcraft-0123456789abcdef.mp4"})
    def reject(*a,**kw):raise ValueError("Empty/light or black frame at index 153")
    monkeypatch.setattr("creative.native_video_checks.inspect_native_frames",reject)
    with pytest.raises(ValueError,match="index 153"):
        mg.write_project(tmp_path/"project",page)
    assert not (tmp_path/"project/index.html").exists()
    assert page.shotcraft_components[0].asset is None


def test_native_failure_cannot_be_plain_title_substituted(tmp_path):
    from types import SimpleNamespace
    from app.motion_graphic import _isolate
    with pytest.raises(RuntimeError,match="refusing plain-title"):
        _isolate(tmp_path,tmp_path,None,SimpleNamespace(native_components=[],shotcraft_components=[{}]),["native failure"],[])


def test_approved_handoff_updates_native_caption(monkeypatch):
    from creative import motion_graphic as mg
    plan,_=sample_page(monkeypatch)
    brief='1. (6s) تصویر: منابع | متن روی صفحه: روایت روشن | روایت: یک روایت روشن.\n2. (4s) تصویر: نتیجه | متن روی صفحه: شروع کنیم | روایت: حالا شروع کنیم.\n3. (4s) تصویر: پایان | متن روی صفحه: پایان | روایت: داستان را بسازیم.'
    approved=mg.apply_handoff(plan,brief)
    assert approved.scenes[0].shotcraft_component.caption=="روایت روشن"
    assert approved.scenes[0].shotcraft_component.source_icons==spec().source_icons


def test_registry_promotes_only_the_actual_native_adapter():
    from creative.resources import registry
    from creative.resources.selection import ResourceRequirements,assess_resource
    registry._snapshot.cache_clear()
    row=registry.get_resource("shotcraft:bezier-source-converge-merge")
    assert row["availability"]=="existing-pipeline" and row["integration_status"]=="native"
    icons=next(p for p in row["parameters"] if p["name"]=="source_icons")
    assert icons["value_type"]=="array" and icons["min_items"]==icons["max_items"]==4
    assert assess_resource(row["id"],ResourceRequirements(context="motion-graphic",engine="hyperframes",kind="component",require_rtl=True,require_vertical=True))["eligible"]
    assert registry.get_resource("shotcraft:card-stack")["availability"]=="catalog-only"


def text_spec(**patch):
    data=dict(resource_id="shotcraft:text-column-converge",caption="روایت روشن",prefix="یک",
              features=("ایده","تصویر","صدا"),subtitle="از ایده تا نتیجه")
    return native.parse_spec({**data,**patch})


@pytest.mark.parametrize("patch",[{"caption":"<svg>"},{"prefix":" "},{"features":["تکراری","تکراری"]},
    {"features":["یک"]},{"features":["a"*25,"b"]},{"subtitle":"x\ny"},{"features":["الف ب پ ت","صدا"]},
    {"features":["😀"*13,"صدا"]},{"arbitrary_js":"alert(1)"}])
def test_text_column_rejects_invalid_or_unreadable_copy(patch):
    with pytest.raises(ValidationError):text_spec(**patch)


def test_text_column_uses_typed_union_and_reading_hold(tmp_path):
    value=text_spec()
    assert isinstance(value,native.TextColumnNative)
    assert native.required_seconds(value)>4
    with pytest.raises(ValueError,match="horizontal"):
        native.materialize(tmp_path,value,"s1-shotcraft",6,"vertical")
    with pytest.raises(ValidationError,match="horizontal"):
        native.ShotcraftMount(spec=value,instance="s1-shotcraft",start=0,duration=6,format="square")
    with pytest.raises(ValidationError,match="reading hold"):
        native.ShotcraftMount(spec=value,instance="s1-shotcraft",start=0,duration=4,format="horizontal")


def test_text_column_binds_original_motion_without_demo_copy():
    source=native.ROOT/"creative/shotcraft_data/demos/typography/text-column-converge/TextColumnConverge.tsx"
    script="""const fs=require('fs'),loader=require('./remotion/shotcraft-text-loader.cjs');process.stdout.write(loader.call({getOptions:()=>({spec:JSON.parse(process.argv[1]),width:1920,height:1080,frames:180})},fs.readFileSync(process.argv[2],'utf8')));"""
    result=subprocess.run(["node","-e",script,json.dumps(text_spec().model_dump()),str(source)],cwd=native.ROOT,check=True,capture_output=True,text=True,timeout=20).stdout
    assert "\n            CRAFT THE SHOT.\n" not in result and "word: 'JIANYING EXPORT'" not in result
    assert 'const BRAND_WORD = "روایت روشن"' in result
    assert 'const CONVERGE_DUR = 36;' in result and 'const NEW_LEFT_EDGE = 618;' in result
    assert 'useTextMetrics(' in result and 'right: newLeft' in result and 'const START = 0;' in result
    assert 'export default TextColumnConverge;' in result


def test_text_column_is_discoverable_but_not_vertical():
    from creative.resources import registry
    from creative.resources.selection import ResourceRequirements,assess_resource
    registry._snapshot.cache_clear()
    row=registry.get_resource("shotcraft:text-column-converge")
    assert row["availability"]=="existing-pipeline"
    assert row["capabilities"]["supports_vertical"] is False
    assert not assess_resource(row["id"],ResourceRequirements(context="motion-graphic",engine="hyperframes",kind="component",require_vertical=True))["eligible"]
    assert {p["name"] for p in row["parameters"]}=={"caption","prefix","features","subtitle","locale"}


@pytest.mark.parametrize("version",[1,2])
def test_existing_remotion_versions_keep_their_contract(tmp_path,monkeypatch,version):
    from engine import remotion_renderer as renderer
    deadlines=[]
    class Process:
        stdout=iter(["REMOTION_PROGRESS 50\n"])
        pid=123
        def poll(self):return 0
        def wait(self):return 0
    class Pipe:
        def __iter__(self):return iter(["REMOTION_PROGRESS 50\n"])
        def close(self):pass
    class Timer:
        def __init__(self,seconds,callback):deadlines.append(seconds)
        def start(self):pass
        def cancel(self):pass
    process=Process();process.stdout=Pipe()
    monkeypatch.setattr(renderer.subprocess,"Popen",lambda *a,**kw:process)
    monkeypatch.setattr(renderer.threading,"Timer",Timer)
    monkeypatch.setenv("REMOTION_TIMEOUT_S","5400")
    monkeypatch.setenv("REMOTION_LOOK","classic")
    config={"version":version,"scenes":[{"frames":30}],"width":1080,"height":1920}
    progress=[]
    renderer.render(config,tmp_path/"output.mp4",job_dir=tmp_path,on_progress=progress.append)
    saved=json.loads((tmp_path/"output.remotion.json").read_text())
    assert saved["version"]==version and saved["scenes"]==[{"frames":30,"supporting_assets":[]}]
    assert saved["font"].endswith("RAY-EXTRABLACK.TTF") and deadlines==[5400]
    assert progress==[50] and "look" not in config
