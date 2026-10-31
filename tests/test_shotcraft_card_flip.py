"""Contract/binding tests. These do not certify rendered pixels or enable the adapter."""
import hashlib
import json
import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError
from creative.shotcraft_card_flip import CardFlipNative

ROOT=Path(__file__).resolve().parents[1]


def values():
    return dict(resource_id="shotcraft:card-flip-reveal",caption="سه نتیجهٔ روشن",kicker="نمونهٔ آزمایشی",
        front_label="ویژگی",before_label="قبل",after_label="بعد",locale="fa-IR",cards=[dict(name="برنامه‌ریزی",description="از ایده تا برنامه",
        front_lines=["ایدهٔ روشن","برنامهٔ مشخص","اجرای منظم"],before=20,after=10,unit="دقیقه",
        result_label="زمان نمونه",evidence="دادهٔ مصنوعی فقط برای آزمون") for _ in range(3)])


def bind(data,frames=300,source=None):
    original=ROOT/'creative/shotcraft_data/demos/transition/card-flip-reveal/CardFlipReveal.tsx'
    script="""const fs=require('fs');const loader=require('./remotion/shotcraft-card-loader.cjs');
    process.stdout.write(loader.call({getOptions:()=>({spec:JSON.parse(process.argv[1]),width:1920,height:1080,frames:Number(process.argv[2])})},process.argv[3]||fs.readFileSync(process.argv[4],'utf8')));"""
    return subprocess.run(['node','-e',script,json.dumps(data),str(frames),source or '',str(original)],
        cwd=ROOT,capture_output=True,text=True,timeout=20)


def test_copy_and_numbers_are_explicit_and_vendor_motion_is_unchanged():
    path=ROOT/'creative/shotcraft_data/demos/transition/card-flip-reveal/CardFlipReveal.tsx'
    before=hashlib.sha256(path.read_bytes()).hexdigest()
    spec=CardFlipNative.model_validate(values())
    assert '\u200c' in spec.cards[0].name
    result=bind(spec.model_dump());assert result.returncode==0,result.stderr
    code=result.stdout
    for original in ['perspective: 1600','const FLIP = 16','const PRE = 4','const STAGGER = 12','const PEAK_DEG = 194','damping: 15, stiffness: 190',"transform: 'scaleY(-1)'"]:
        assert original in code
    for demo in ['Make a 30s launch film','With ${BRAND.short}','faster first cut','text="Three features. Three outcomes."']:
        assert demo not in code
    assert '"bars":[1,0.5]' in code and '"value":"۱۰"' in code
    assert before==hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize('change',[{'cards':[]},{'caption':'<script>'},{'kicker':' '},{'arbitrary_code':'run()'}])
def test_invalid_root_contract(change):
    data=values();data.update(change)
    with pytest.raises(ValidationError):CardFlipNative.model_validate(data)


@pytest.mark.parametrize('change',[{'before':float('nan')},{'after':-1},{'evidence':''},{'front_lines':['a']},{'unit':'x\ny'}])
def test_invalid_card_contract(change):
    data=values();data['cards'][0].update(change)
    with pytest.raises(ValidationError):CardFlipNative.model_validate(data)


def test_loader_fails_closed_on_short_hold_and_changed_source():
    short=bind(values(),120)
    assert short.returncode!=0 and 'reading holds' in short.stderr
    changed=bind(values(),300,'const FEATURES=[];')
    assert changed.returncode!=0 and 'Pinned features changed' in changed.stderr


def test_zero_comparison_never_generates_nonfinite_ratios():
    data=values()
    for card in data['cards']:card.update(before=0,after=0)
    result=bind(data);assert result.returncode==0,result.stderr
    assert '"bars":[0,0]' in result.stdout
    assert 'NaN' not in result.stdout and 'Infinity' not in result.stdout


def test_bound_tsx_transpiles_with_installed_typescript():
    result=bind(values());assert result.returncode==0,result.stderr
    check=subprocess.run(['node','-e',"""const ts=require('./web/node_modules/typescript');
      const fs=require('fs');const result=ts.transpileModule(fs.readFileSync(0,'utf8'),{
        compilerOptions:{jsx:ts.JsxEmit.React,target:ts.ScriptTarget.ES2022},reportDiagnostics:true,fileName:'CardFlip.tsx'});
      const errors=(result.diagnostics||[]).filter(d=>d.category===ts.DiagnosticCategory.Error);
      if(errors.length){console.error(errors.map(d=>ts.flattenDiagnosticMessageText(d.messageText,' ')));process.exit(1)}
    """],input=result.stdout,cwd=ROOT,capture_output=True,text=True,timeout=20)
    assert check.returncode==0,check.stderr


def test_native_union_and_reading_hold_are_enforced_before_execution():
    from creative.shotcraft_native import parse_spec,required_seconds,ShotcraftMount
    from creative.shotcraft_card_flip import reading_frames
    spec=parse_spec(values())
    assert isinstance(spec,CardFlipNative)
    assert required_seconds(spec)==reading_frames(spec)/30
    with pytest.raises(ValidationError):
        ShotcraftMount(spec=spec,instance="s1-shotcraft",start=0,duration=4,format="horizontal")
    with pytest.raises(ValidationError):
        ShotcraftMount(spec=spec,instance="s1-shotcraft",start=0,duration=10,format="vertical")


def test_typed_authoring_does_not_call_a_model_and_keeps_approved_copy():
    from creative import motion_graphic as mg
    scene=mg.ScenePlan(headline=values()['caption'],idea="synthetic",start=0,end=10,narration="نمونهٔ آزمایشی",shotcraft_component=values())
    plan=mg.MotionPlan(format="horizontal",duration=10,scenes=[scene])
    draft=mg.author_scene(plan,1,"synthetic")
    assert isinstance(draft.shotcraft_component,CardFlipNative)
    scene.headline="متن متفاوت"
    with pytest.raises(mg.CreativeUnavailable):mg.author_scene(plan,1,"synthetic")


def test_planner_and_resource_metadata_expose_typed_card_constraints():
    from creative import motion_graphic as mg
    from creative.resources.providers import shotcraft_resources
    request=mg.plan_request("نمونه")
    assert 'shotcraft:card-flip-reveal' in request and 'evidence' in request
    assert len(request)<50_000
    row=next(r for r in shotcraft_resources() if r.id=='shotcraft:card-flip-reveal')
    assert row.integration_status=='native' and not row.capabilities.supports_vertical
    assert next(p for p in row.parameters if p.name=='cards').required


def test_rtl_binding_reverses_card_order_and_preserves_english_layout():
    rtl=bind(values());assert rtl.returncode==0,rtl.stderr
    assert 'X0 + (2-i) * (CW + GAP)' in rtl.stdout and 'right: X0, top: 118' in rtl.stdout
    data=values();data['locale']='en-US'
    ltr=bind(data);assert ltr.returncode==0,ltr.stderr
    assert 'X0 + i * (CW + GAP)' in ltr.stdout and 'left: X0, top: 118' in ltr.stdout


@pytest.mark.parametrize('locale',['fa-IR','en-US'])
def test_per_card_gate_does_not_let_header_hide_a_disappeared_card(monkeypatch,locale):
    from PIL import Image,ImageDraw
    from types import SimpleNamespace
    from creative import native_video_checks as checks
    data=values();data['locale']=locale
    spec=CardFlipNative.model_validate(data)
    image=Image.new('L',(288,162),0);draw=ImageDraw.Draw(image)
    draw.rectangle((20,8,260,25),fill=255)  # Header stays visible even in bad frame.
    for left in [29,108,187]:draw.rectangle((left+10,75,left+25,85),fill=255)
    good=image.tobytes()
    monkeypatch.setattr(checks.subprocess,'run',lambda *a,**k:SimpleNamespace(stdout=good*300))
    assert checks.inspect_card_regions('synthetic',spec,300)['checked_card_frames']>700
    bad=image.copy();ImageDraw.Draw(bad).rectangle((29,53,98,139),fill=0)
    monkeypatch.setattr(checks.subprocess,'run',lambda *a,**k:SimpleNamespace(stdout=good*250+bad.tobytes()+good*49))
    with pytest.raises(ValueError,match='Missing card'):
        checks.inspect_card_regions('synthetic',spec,300)


def test_measured_font_weights_match_the_rendered_copy():
    hook=(ROOT/'remotion/src/shotcraft/useCardMetrics.ts').read_text()
    for check in ['fits(caption,84,1480,760)','fits(c.name,52,400,750)','fits(c.value,120,370,800)','fits(c.label,40,400,550)']:
        assert check in hook
    assert 'document.fonts.ready' in hook and 'cancelRender(e)' in hook


def test_card_region_failure_prevents_page_publication(monkeypatch,tmp_path):
    from creative import motion_graphic as mg,shotcraft_native as native
    import engine.hyperframes.assets as assets
    scene=mg.ScenePlan(headline=values()['caption'],idea="synthetic",start=0,end=10,narration="نمونه",shotcraft_component=values())
    plan=mg.MotionPlan(format="horizontal",duration=10,scenes=[scene])
    page=mg.assemble_scenes(plan,[mg.author_scene(plan,1,"synthetic")])
    runtime=tmp_path/'gsap.js';runtime.write_text('// local synthetic runtime')
    monkeypatch.setattr(assets,'ensure_gsap',lambda:runtime)
    monkeypatch.setattr(native,'materialize',lambda *a,**kw:{'asset':'assets/s1-shotcraft-0123456789abcdef.mp4'})
    monkeypatch.setattr('creative.native_video_checks.inspect_native_frames',lambda *a,**kw:{'mocked':True})
    def reject(*a,**kw):raise ValueError('Missing card 2 at encoded frame 250')
    monkeypatch.setattr('creative.native_video_checks.inspect_card_regions',reject)
    with pytest.raises(ValueError,match='Missing card 2'):mg.write_project(tmp_path/'project',page)
    assert not (tmp_path/'project/index.html').exists()
    assert not page.shotcraft_components[0].asset
