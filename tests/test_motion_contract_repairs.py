"""Exercise shared renderer admission, app publish gates and delivery QC without providers."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from engine.hyperframes import product_reel
from engine import remotion_renderer, technical_qc


@pytest.fixture
def config(tmp_path):
    (tmp_path/'image.png').write_bytes(b'owned')
    return {'scenes':[{'asset':'image.png','frames':30,'kind':'photo','title':'۱۲ گام'}]}


@pytest.mark.parametrize('entry',['hyperframes','remotion','prepare'])
@pytest.mark.parametrize('invalid',['empty','count','total','scene','float','missing','escape','support','symlink'])
def test_both_renderers_reject_before_spawning(tmp_path,monkeypatch,config,entry,invalid):
    scene=config['scenes'][0]
    outside=tmp_path.parent/'outside.png';outside.write_bytes(b'outside')
    if invalid=='empty':config['scenes']=[]
    if invalid=='count':config['scenes']=[deepcopy(scene) for _ in range(31)]
    if invalid=='total':config['scenes']=[{**scene,'frames':900} for _ in range(4)]
    if invalid=='scene':scene['frames']=901
    if invalid=='float':scene['frames']=30.5
    if invalid=='missing':scene['asset']='missing.png'
    if invalid=='escape':scene['asset']=str(outside)
    if invalid=='support':scene['supporting_assets']=[str(outside)]
    if invalid=='symlink':
        (tmp_path/'escape.png').symlink_to(outside);scene['asset']='escape.png'
    monkeypatch.setattr('subprocess.Popen',lambda *a,**kw:pytest.fail('spawned before admission'))
    monkeypatch.setattr('engine.remotion_renderer._enrich',lambda *a:pytest.fail('prepared before admission'))
    with pytest.raises(ValueError):
        if entry=='hyperframes':product_reel.render(config,tmp_path/'out.mp4',job_dir=tmp_path)
        elif entry=='remotion':remotion_renderer.render(config,tmp_path/'out.mp4',job_dir=tmp_path)
        else:remotion_renderer.prepare_reel_config(config,tmp_path)


@pytest.mark.parametrize('entry',['hyperframes','remotion'])
def test_both_renderers_admit_valid_owned_data(tmp_path,monkeypatch,config,entry):
    config['scenes'][0]['supporting_assets']=['image.png']
    gsap=tmp_path/'gsap.js';gsap.write_text('owned')
    monkeypatch.setattr('engine.hyperframes.assets.ensure_gsap',lambda:gsap)
    monkeypatch.setattr(product_reel,'_run_cli',lambda project,out,**kw:out.write_bytes(b'video'))
    class Process:
        stdout=[]
        def poll(self):return 0
        def wait(self):return 0
    class Lines(list):
        def close(self):pass
    process=Process();process.stdout=Lines()
    monkeypatch.setattr('subprocess.Popen',lambda *a,**k:process)
    prepared=remotion_renderer.prepare_reel_config(config,tmp_path)
    assert prepared['scenes'][0]['supporting_assets']==[str(tmp_path/'image.png')]
    if entry=='hyperframes':product_reel.render(prepared,tmp_path/'out.mp4',job_dir=tmp_path)
    else:remotion_renderer.render(prepared,tmp_path/'out.mp4',job_dir=tmp_path)


@pytest.mark.parametrize('fps,size,accepted',[('30/1',(1080,1920),True),('25/1',(1080,1920),False),('30/1',(540,960),False)])
def test_talking_delivery_technical_qc(tmp_path,monkeypatch,fps,size,accepted):
    monkeypatch.setattr(technical_qc,'probe',lambda _: {'format':{'duration':'3'},'streams':[
        {'codec_type':'video','width':size[0],'height':size[1],'avg_frame_rate':fps,'duration':'3'}]})
    if accepted:assert technical_qc.inspect_talking_export(tmp_path/'out.mp4',duration=3)['fps']=='30/1'
    else:
        with pytest.raises(RuntimeError):technical_qc.inspect_talking_export(tmp_path/'out.mp4',duration=3)


@pytest.fixture
def job_gate(tmp_path,monkeypatch,config):
    from app import jobs
    from brain import planner
    from creative import review
    job=jobs.Job('test',tmp_path)
    plan=NS(style='default',export=NS(crf=20),poster=None,canvas=NS(width=1080,height=1920,fps=30),output_duration=1)
    data={'generation_meta':{'remotion':config,'creative_plan':{'schema_version':2}}}
    monkeypatch.setattr(jobs,'_write_status',lambda _:None)
    monkeypatch.setattr(jobs,'load_plan',lambda _:data)
    monkeypatch.setattr(planner,'refresh_stale_poster_rating',lambda _:False)
    monkeypatch.setattr(jobs,'validate_plan',lambda *a,**k:(plan,[]))
    monkeypatch.setattr(jobs,'build',lambda *a,**k:(tmp_path/'p.mlt',None))
    monkeypatch.setattr(jobs,'build_premiere',lambda *a,**k:None)
    monkeypatch.setattr(jobs,'load_style',lambda _: {})
    monkeypatch.setattr(jobs,'attached_music',lambda _:None)
    def render(config,out,**kwargs):
        out.parent.mkdir(exist_ok=True);out.write_bytes(b'reviewer file')
    monkeypatch.setattr(product_reel,'render',render)
    monkeypatch.setattr(remotion_renderer,'render',render)
    monkeypatch.setattr(technical_qc,'inspect_export',lambda *a,**k:{'warnings':[]})
    monkeypatch.setattr('subprocess.run',lambda *a,**k:NS(returncode=0)) # poster extraction
    monkeypatch.setattr(review,'review_export',lambda *a,**k:{'status':'passed'})
    monkeypatch.setenv('REEL_ENGINE','hyperframes')
    return jobs,job,data


@pytest.mark.parametrize('verdict',['passed','needs_attention','unavailable'])
def test_app_creative_review_is_a_publish_gate(job_gate,monkeypatch,verdict):
    from creative import review
    jobs,job,_=job_gate
    monkeypatch.setattr(review,'review_export',lambda *a,**k:{'status':verdict,'summary':'review verdict'})
    jobs._run_job(job,False)
    assert job.render.status==('done' if verdict=='passed' else 'needs_review')
    assert bool(job.versions)==(verdict=='passed')
    if verdict!='passed':
        assert job.render.output is None
        assert (job.dir/'exports'/job.render.candidate_output).read_bytes()==b'reviewer file'


def test_app_fallback_records_reason_and_holds_candidate(job_gate,monkeypatch):
    jobs,job,_=job_gate
    def fail(*a,**k):raise RuntimeError('fixture browser failure')
    monkeypatch.setattr(product_reel,'render',fail)
    jobs._run_job(job,False)
    assert job.render.status=='needs_review' and not job.versions
    assert job.render.renderer=='remotion'
    assert job.render.technical_qc['renderer_failure']=='fixture browser failure'
    assert (job.dir/'exports'/job.render.candidate_output).is_file()


@pytest.mark.parametrize('serious',[False,True])
def test_app_legacy_motion_qc_blocks_serious_findings(job_gate,monkeypatch,serious):
    from brain import qc_pipeline
    jobs,job,data=job_gate
    data['generation_meta'].pop('creative_plan')
    qc=NS(status='done',message='qc',current_round=1,total_issues=int(serious),fixed_issues=0,
          rounds=[NS(issues=[{'severity':'error'}] if serious else [],changes=[])],started_at=0,finished_at=1)
    monkeypatch.setattr(qc_pipeline,'run_qc',lambda *a,**k:qc)
    jobs._run_job(job,False)
    assert job.render.status==('needs_review' if serious else 'done')
    assert bool(job.versions) is not serious


@pytest.mark.parametrize('verdict',['passed','needs_attention','unavailable','motion_error','technical_error'])
def test_talking2_worker_template_and_publish_gate(tmp_path,monkeypatch,verdict):
    from app import talking_reel as tr
    from engine import native_checkpoint
    from engine.hyperframes import renderer, quality
    from creative import review
    from engine.talking_styles import talking_2
    gsap=tmp_path/'gsap.js';gsap.write_text('local')
    monkeypatch.setattr('engine.hyperframes.assets.ensure_gsap',lambda:gsap)
    transcript={'sentences':[{'start':0,'end':3,'text':'سلام ۱۲ گام'}]}
    plan=NS(duration=3,shots=[NS(src_in=0,src_out=3,out_start=0)],continuous_split=True)
    planned=tr.PlannedReel('talking_2',talking_2,transcript,{}, {},plan,plan,hyperframes=True)
    state=tr.load(tmp_path);state.update(style='talking_2',analysis_ready=True,decisions_2={'hook':'سلام'},creative_plan={'schema_version':2})
    tr.save(tmp_path,state)
    monkeypatch.setattr(tr,'transcript_for',lambda *a:transcript)
    monkeypatch.setattr(tr,'plan_render',lambda *a:planned)
    monkeypatch.setattr(tr,'resolve_music',lambda _:None)
    def native(fn,video,plan,out,**kw):
        out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(b'base')
    monkeypatch.setattr(native_checkpoint,'render_cached',native)
    monkeypatch.setattr('engine.probe.probe',lambda _: {'format':{'duration':'3'}})
    def rendered(project,out,**kw):
        assert 'custom' not in (project/'index.html').read_text()
        out.write_bytes(b'reviewer file')
    monkeypatch.setattr('engine.hyperframes.render_project',rendered)
    monkeypatch.setattr(quality,'review_render',lambda *a:{'passed':verdict!='motion_error','problems':['motion defect'] if verdict=='motion_error' else []})
    def technical(*a,**k):
        if verdict=='technical_error':raise RuntimeError('frame rate mismatch')
        return {'fps':'30/1'}
    monkeypatch.setattr(technical_qc,'inspect_talking_export',technical)
    monkeypatch.setattr(review,'review_export',lambda *a,**kw:{'status':verdict,'summary':'review verdict'})
    monkeypatch.setattr(tr,'_apply_effects',lambda *a:None)
    monkeypatch.setattr(tr,'_record_render_time',lambda *a:None)
    monkeypatch.setattr(tr,'_run',lambda folder,video,**kw:tr._run_split(folder,video,'talking_2',regenerate=False))
    class InlineThread:
        def __init__(self,target,**kw):self.target=target
        def start(self):self.target()
    monkeypatch.setattr(tr.threading,'Thread',InlineThread)
    tr.start(tmp_path,tmp_path/'input.mp4')
    state=tr.load(tmp_path)
    assert state['status']==('done' if verdict=='passed' else 'needs_review')
    assert bool(tr.published_outputs(state))==(verdict=='passed')
    if verdict!='passed':assert (tmp_path/state['candidate_output']).is_file()


def test_disabled_chat_worker_reports_unavailable_without_provider(tmp_path,monkeypatch):
    from app import motion_graphic as mg
    monkeypatch.setattr('creative.llm.ask',lambda *a,**k:pytest.fail('provider called'))
    record=mg.create('conversation','user','موشن بساز')
    directory=mg.folder('user','conversation',record['id'])
    mg.start(directory)
    assert mg.view(directory)['status']=='unavailable'
    assert not mg.view(directory)['active'] and not mg.view(directory)['versions']


def test_held_status_survives_job_summary(job_gate):
    jobs,job,_=job_gate
    job.render.status='needs_review';job.generate.status='done'
    assert jobs._job_status(job)[0]=='needs_review'


def test_reviewer_history_excludes_files_without_publication_receipt(tmp_path,monkeypatch):
    import asyncio
    from app import talking_reel as tr, jobs
    from app.routers import studio
    from fastapi import HTTPException
    job=jobs.Job('history',tmp_path)
    exports=tmp_path/'exports';exports.mkdir()
    for name in ('talking_reel_v1.mp4','talking_reel_v2.mp4'):(exports/name).touch()
    tr.save(tmp_path,{'status':'needs_review','output':None,'candidate_output':'exports/talking_reel_v2.mp4',
                     'published_outputs':['exports/talking_reel_v1.mp4']})
    async def project(*args):return {'engine':'talking','external_ref':job.id}
    monkeypatch.setattr(studio.repo,'get_project',project)
    monkeypatch.setattr(studio,'_user',lambda _: 'user')
    monkeypatch.setattr(studio.jobstore,'get',lambda _:job)
    history=asyncio.run(studio.project_outputs(None,'project'))
    assert [item['file'] for item in history]==['talking_reel_v1.mp4']
    with pytest.raises(HTTPException):
        asyncio.run(studio.project_output(None,'project',file='talking_reel_v2.mp4'))
    candidate=asyncio.run(studio.project_output(None,'project',candidate=True))
    assert Path(candidate.path)==exports/'talking_reel_v2.mp4'
    published=asyncio.run(studio.project_output(None,'project',file='talking_reel_v1.mp4'))
    assert Path(published.path)==exports/'talking_reel_v1.mp4'


@pytest.mark.parametrize('held',[False,True])
def test_studio_sync_preserves_publish_gate_without_auto_retry(job_gate,monkeypatch,held):
    import asyncio
    from app import studio_orchestrator as so
    from brain import content_creator
    jobs,job,_=job_gate
    job.render.status='needs_review' if held else 'done'
    job.render.output=None if held else 'v1.mp4'
    job.render.candidate_output='v1.mp4' if held else None
    job.render.renderer='remotion'
    job.render.technical_qc={'renderer':'remotion','renderer_failure':'browser failed'}
    project={'id':'p','external_ref':job.id,'engine':'motion','status':'running','state':{'confirmed':True}}
    async def conversation(*args):return {'projects':[project]}
    updates=[];events=[]
    async def update(*args,**kwargs):updates.append(kwargs)
    async def emit(*args,**kwargs):events.append(args[1])
    async def no_op(*args,**kwargs):pass
    monkeypatch.setattr(so.repo,'get_conversation',conversation)
    monkeypatch.setattr(so.repo,'update_project',update)
    monkeypatch.setattr(so.repo,'emit',emit)
    monkeypatch.setattr(so.repo,'add_message',no_op)
    monkeypatch.setattr(so,'_sync_motion_messages',no_op)
    monkeypatch.setattr(so.jobstore,'get',lambda _:job)
    monkeypatch.setattr(so.jobstore,'start_render',lambda *a,**k:pytest.fail('automatic retry of held export'))
    monkeypatch.setattr(content_creator,'get_storyboard_status',lambda _:{'state':'ready'})
    asyncio.run(so._sync_conversation_once('conversation','user'))
    assert updates[0]['status']==('awaiting_confirmation' if held else 'done')
    observed=updates[0]['state']['last_observed']
    assert observed['status']==('needs_review' if held else 'done')
    assert bool(observed['output']) is not held
    assert ('render.completed' in events) is not held
    if held:assert updates[0]['state']['technical_qc']['renderer_failure']=='browser failed'


def test_disabled_motion_intent_does_not_gather_sources(monkeypatch):
    from app import studio_orchestrator as so
    messages=[]
    monkeypatch.setattr(so,'_gather_sources',lambda *a,**k:pytest.fail('disabled route gathered sources'))
    monkeypatch.setattr(so,'_assistant',lambda c,u,m:messages.append(m))
    so._start_motion_graphic('conversation','user',{},'موشن بساز')
    assert 'در دسترس نیست' in messages[0]


def test_local_recovery_does_not_promote_held_files(tmp_path):
    from app import jobs, talking_reel as tr
    (tmp_path/'raw').mkdir();(tmp_path/'raw/input.mp4').touch()
    (tmp_path/'exports').mkdir();(tmp_path/'exports/talking_reel_v1.mp4').touch()
    tr.save(tmp_path,{'status':'needs_review','analysis_ready':True,'message':'failed QC',
                     'candidate_output':'exports/talking_reel_v1.mp4'})
    job=jobs._recover_local_folder(tmp_path,'user')
    assert job.render.status=='needs_review' and job.render.candidate_output=='talking_reel_v1.mp4'
    assert job.render.output is None and not job.versions


@pytest.mark.parametrize('verdict,approved',[('passed',True),('needs_attention',False),('unavailable',False)])
def test_legacy_history_uses_review_verdict(verdict,approved):
    from app.talking_reel import published_outputs
    state={'status':'done','output':'exports/talking_reel_v1.mp4','candidate_output':'exports/talking_reel_v1.mp4',
           'creative_review':{'status':verdict}}
    assert bool(published_outputs(state)) is approved
