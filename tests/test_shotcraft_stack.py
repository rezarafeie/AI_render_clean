import hashlib
import json
import subprocess
from pathlib import Path
import pytest
from pydantic import ValidationError
from creative.shotcraft_stack import CardStackNative,required_seconds

ROOT=Path(__file__).resolve().parents[1]


def data():
    return dict(resource_id='shotcraft:card-stack',caption='مجموعهٔ تصویری',kicker='نمونهٔ آزمایشی',subtitle='نه تصویر، یک مجموعه',
        cards=[dict(title='تصویر '+str(i+1),meta='نمونهٔ هندسی',asset='assets/compare-'+f'{i+1:064x}'+'.png') for i in range(9)],locale='fa-IR')


@pytest.mark.parametrize('kind',['too-few','too-many','duplicate','path','html','multiline','long'])
def test_stack_rejects_incomplete_or_executable_inputs(kind):
    value=data()
    if kind=='too-few':value['cards'].pop()
    if kind=='too-many':value['cards'].append(value['cards'][0])
    if kind=='duplicate':value['cards'][1]['asset']=value['cards'][0]['asset']
    if kind=='path':value['cards'][0]['asset']='../secret.png'
    if kind=='html':value['caption']='<script>'
    if kind=='multiline':value['cards'][0]['meta']='a\nb'
    if kind=='long':value['cards'][0]['title']='x'*13
    with pytest.raises(ValidationError):CardStackNative.model_validate(value)


def test_stack_requires_horizontal_and_readable_final_hold():
    from creative.shotcraft_native import ShotcraftMount
    value=CardStackNative.model_validate(data())
    assert required_seconds(value)==6
    for format,seconds in [('vertical',6),('horizontal',5)]:
        with pytest.raises(ValidationError):ShotcraftMount(spec=value,instance='s1-shotcraft',start=0,duration=seconds,format=format)
    assert ShotcraftMount(spec=value,instance='s1-shotcraft',start=0,duration=6,format='horizontal')


def test_registry_exposes_real_stack_contract_not_generic_cover_generation():
    from creative.resources import registry
    registry._snapshot.cache_clear()
    row=registry.get_resource('shotcraft:card-stack')
    assert row['integration_status']=='native' and row['availability']=='existing-pipeline'
    assert row['capabilities']['supports_vertical'] is False
    assert row['preview_video'].endswith('shotcraft-native-card-stack.mp4')
    cards=next(p for p in row['parameters'] if p['name']=='cards')
    assert cards['min_items']==cards['max_items']==9


def test_missing_owned_images_ask_before_narration_or_scene_generation(tmp_path,monkeypatch):
    from app import motion_graphic as app
    from app import studio_narrator
    from creative import motion_graphic as mg
    plan=mg.MotionPlan(duration=6,format='horizontal',title='Collection',scenes=[mg.ScenePlan(start=0,end=6,headline='مجموعهٔ تصویری',idea='Collection overview',narration='نمونهٔ آزمایشی',shotcraft_component=CardStackNative.model_validate(data()))])
    monkeypatch.setattr(mg,'plan',lambda *args,**kwargs:plan)
    monkeypatch.setattr(mg,'apply_handoff',lambda plan,brief:plan)
    monkeypatch.setattr(app,'_stats',lambda:{'plan_s':1})
    monkeypatch.setattr(app,'_remaining',lambda *args:1)
    monkeypatch.setattr(app,'_progress',lambda *args,**kwargs:None)
    monkeypatch.setattr(app,'_note',lambda *args,**kwargs:None)
    monkeypatch.setattr(app,'_cancelled',lambda *args:False)
    asked=[];monkeypatch.setattr(app,'_ask',lambda directory,record,questions:asked.extend(questions))
    monkeypatch.setattr(app,'_narrate',lambda *args:pytest.fail('Missing inputs must stop before paid narration'))
    monkeypatch.setattr(studio_narrator,'narrate',lambda *args,**kwargs:pytest.fail('Missing inputs must stop before agent narration'))
    record={'conversation_id':'conversation','user_key':'owner','id':'job','image_inputs':[]}
    assert app._plan_and_build(tmp_path,record,'Create collection',[],[]) is None
    assert len(asked)==1 and 'نه تصویر' in asked[0]
    assert not (tmp_path/'plan.json').exists()
    plan.questions=[]
    monkeypatch.setattr(app,'_fingerprint',lambda *args:'cached-fingerprint')
    (tmp_path/'plan.json').write_text(json.dumps({'fp':'cached-fingerprint','plan':plan.model_dump()}))
    monkeypatch.setattr(mg,'plan',lambda *args,**kwargs:pytest.fail('Cached plan must not call AI again'))
    assert app._plan_and_build(tmp_path,record,'Create collection',[],[]) is None
    assert len(asked)==2


def test_preflight_uses_only_owned_catalog_and_checks_comparison_geometry():
    from app.motion_graphic import _image_input_questions
    from creative.shotcraft_compare import BeforeAfterNative
    from types import SimpleNamespace
    value=CardStackNative.model_validate(data())
    rows=[{'asset':c.asset,'width':1920,'height':1080} for c in value.cards]
    plan=SimpleNamespace(scenes=[SimpleNamespace(shotcraft_component=value)])
    assert not _image_input_questions(plan,{'image_inputs':rows})
    spec=BeforeAfterNative(resource_id='shotcraft:before-after-slider-scrub',caption='دو تصویر',before_label='قبل',after_label='بعد',
        before_asset=value.cards[0].asset,after_asset=value.cards[1].asset,comparison_basis='User supplied same-view states')
    plan.scenes[0].shotcraft_component=spec
    assert not _image_input_questions(plan,{'image_inputs':rows})
    rows[1].update(width=3840,height=2160)
    assert 'ابعاد' in _image_input_questions(plan,{'image_inputs':rows})[0]
    assert 'پیوست' in _image_input_questions(plan,{'image_inputs':[]})[0]


def test_pinned_stack_retains_motion_and_removes_every_fictional_cover():
    path=ROOT/'creative/shotcraft_data/demos/ui-entrance/card-stack/CardStack.tsx'
    original=hashlib.sha256(path.read_bytes()).hexdigest()
    script="""const fs=require('fs'); const loader=require('./remotion/shotcraft-stack-loader.cjs');
    process.stdout.write(loader.call({getOptions:()=>({spec:JSON.parse(process.argv[1]),width:1920,height:1080,frames:180})},fs.readFileSync(process.argv[2],'utf8')));"""
    result=subprocess.run(['node','-e',script,json.dumps(data()),str(path)],cwd=ROOT,capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stderr
    for text in ['const N = 9','const FEATURED = 4','stagger(i, N, 40, EASE.out)','springAt(f, 68, { damping: 20, stiffness: 95 })',"transformOrigin: '50% 130%'",'const ly = feat ? -72 * lift : 0','zIndex: i']:
        assert text in result.stdout
    for fake in ['+38%','$2.4M','+12.4%','ShotcraftMark','BRAND.name','Every one ready to render','const Cover:']:
        assert fake not in result.stdout
    assert "objectFit:'contain'" in result.stdout
    assert hashlib.sha256(path.read_bytes()).hexdigest()==original
    compiled=subprocess.run(['node','-e',"const fs=require('fs'),ts=require('./web/node_modules/typescript');const d=ts.transpileModule(fs.readFileSync(0,'utf8'),{fileName:'Stack.tsx',compilerOptions:{jsx:ts.JsxEmit.React},reportDiagnostics:true}).diagnostics||[];if(d.some(v=>v.category===ts.DiagnosticCategory.Error))process.exit(1)"],input=result.stdout,cwd=ROOT,capture_output=True,text=True,timeout=20)
    assert compiled.returncode==0,compiled.stderr


def owned_images(tmp_path):
    from PIL import Image
    from creative.shotcraft_compare import stage_images,restore_inputs
    originals=tmp_path/'attachments';originals.mkdir();attachments=[]
    for i in range(9):
        aid=f'{i+1:032x}';path=originals/(aid+'.png')
        Image.new('RGB',(1920,1080),(i*20,50,100)).save(path)
        attachments.append({'id':aid,'kind':'image','path':str(path)})
    job=tmp_path/'job';job.mkdir();rows=stage_images(job,originals,attachments)
    assert len(rows)==9
    work=job/'work';restore_inputs(job,work,rows)
    value=data()
    for card,row in zip(value['cards'],rows,strict=True):card['asset']=row['asset']
    return work,CardStackNative.model_validate(value),rows


def test_all_nine_owned_images_participate_in_cache_integrity(tmp_path,monkeypatch):
    from creative import shotcraft_native as native
    from engine import remotion_renderer
    work,spec,rows=owned_images(tmp_path);calls=[]
    def render(config,path,**kwargs):calls.append(config);path.write_bytes(b'mocked output, not a video')
    monkeypatch.setattr(remotion_renderer,'render',render)
    monkeypatch.setattr(native,'inspect_output',lambda *args:{'mock':True})
    monkeypatch.setattr(native,'source_fingerprint',lambda:'mocked-adapter')
    receipt=native.materialize(work,spec,'s1-shotcraft',6,'horizontal')
    assert receipt['input_sha256']==[r['sha256'] for r in rows]
    assert calls[0]['scenes'][0]['supporting_assets']==[r['asset'] for r in rows]
    assert native.materialize(work,spec,'s1-shotcraft',6,'horizontal')==receipt and len(calls)==1
    (work/spec.cards[-1].asset).write_bytes(b'tampered last input')
    with pytest.raises(ValueError):native.materialize(work,spec,'s1-shotcraft',6,'horizontal')
    assert len(calls)==1


@pytest.mark.parametrize('version,count',[(1,3),(2,3),(3,9)])
def test_renderer_keeps_legacy_limit_and_all_nine_native_inputs(tmp_path,monkeypatch,version,count):
    from engine import remotion_renderer as renderer
    work,spec,rows=owned_images(tmp_path)
    class Pipe:
        def __iter__(self):return iter([])
        def close(self):pass
    class Process:
        pid=123;stdout=Pipe()
        def poll(self):return 0
        def wait(self):return 0
    monkeypatch.setattr(renderer.subprocess,'Popen',lambda *args,**kwargs:Process())
    monkeypatch.setenv('REMOTION_LOOK','classic')
    config={'version':version,'width':1920,'height':1080,'scenes':[{'frames':180,'shotcraft':spec.model_dump(),'supporting_assets':[r['asset'] for r in rows]}]}
    renderer.render(config,work/'test.mp4',job_dir=work)
    saved=json.loads((work/'test.remotion.json').read_text())
    assert len(saved['scenes'][0]['supporting_assets'])==count
    assert len(config['scenes'][0]['supporting_assets'])==9


def test_renderer_rejects_missing_ninth_or_foreign_input_before_spawn(tmp_path,monkeypatch):
    from engine.remotion_renderer import render
    work,spec,rows=owned_images(tmp_path)
    monkeypatch.setattr(subprocess,'Popen',lambda *args,**kwargs:pytest.fail('Must reject before process starts'))
    config={'version':3,'scenes':[{'frames':180,'shotcraft':spec.model_dump(),'supporting_assets':[r['asset'] for r in rows[:-1]]}]}
    with pytest.raises(ValueError,match='exactly nine'):render(config,work/'test.mp4',job_dir=work)
    config['scenes'][0]['supporting_assets']=[r['asset'] for r in rows[:-1]]+['../secret.png']
    with pytest.raises(ValueError,match='Invalid owned'):render(config,work/'test.mp4',job_dir=work)
