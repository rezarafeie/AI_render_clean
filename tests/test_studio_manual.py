import asyncio
import copy

import pytest

from app import studio_manual as manual, studio_store
from app.routers.studio import _public_conversation, MessageCreate
from app.studio_orchestrator import process_message, sync_conversation, _answer_manual_checkpoint


@pytest.fixture
def store(tmp_path, monkeypatch):
    from app import jobs
    monkeypatch.setattr(jobs, 'JOBS_ROOT', tmp_path)
    monkeypatch.setattr(studio_store, 'DB_AVAILABLE', False)
    monkeypatch.setattr(studio_store, 'ROOT', tmp_path)
    monkeypatch.setattr(studio_store, 'FALLBACK', tmp_path / 'studio.json')
    return studio_store.repo


def run(coro): return asyncio.run(coro)


def test_legacy_render_gets_plan_without_reapplying_brand_or_starting_jobs(store, monkeypatch, tmp_path):
    from app import studio_orchestrator as o, talking_reel
    from types import SimpleNamespace
    c=run(store.create_conversation('u'))
    p=run(store.create_project(c['id'],'u','talking','old',{},'job'))
    monkeypatch.setattr(o.jobstore,'get',lambda _:SimpleNamespace(dir=tmp_path,raw_name='source.mp4'))
    monkeypatch.setattr(talking_reel,'load',lambda _:{'status':'done','analysis_ready':True,'output':'exports/v1.mp4'})
    monkeypatch.setattr(talking_reel,'public',lambda s:s)
    monkeypatch.setattr(talking_reel,'start',lambda *a,**k:pytest.fail('must not render'))
    monkeypatch.setattr(o,'_apply_brand_defaults',lambda *a:pytest.fail('must preserve existing settings'))
    async def refresh(cid,user,project,job,**kw):
        assert not kw['after_analysis']
        assert project['state']['candidate_output']=='exports/v1.mp4'
        return await store.update_project(project['id'],user,state={**project['state'],'plan':{'versions':[{'id':'legacy'}]}}),True
    monkeypatch.setattr(o,'_refresh_plan',refresh)
    run(o.sync_conversation(c['id'],'u'))
    assert run(store.get_project(p['id'],'u'))['state']['plan']['versions'][0]['id']=='legacy'


def test_logo_replacement_requires_owned_image_before_confirmation(store, monkeypatch):
    from app import studio_orchestrator as o
    c=run(store.create_conversation('u'))
    p=run(store.create_project(c['id'],'u','talking','video',{'attachment_ids':['original']},'job'))
    monkeypatch.setattr(o,'_resolved_intent',lambda *a,**k:pytest.fail('no model needed'))
    process_message(c['id'],'u','m','میخوام لوگو رو تغییر بدم',[])
    session=run(store.get_conversation(c['id'],'u'))['state']['manual_session']
    assert manual.question(session)['key']=='logo_asset'
    with pytest.raises(ValueError, match='تصویر لوگو'):
        manual.answer(c['id'],'u',session,session['question_id'],'attached',[])
    image=run(store.create_attachment(c['id'],'u',kind='image',filename='logo.png',path='/logo',mime_type='image/png',size_bytes=1))
    process_message(c['id'],'u','m2','لوگوی جدید',[image['id']])
    updated=run(store.get_project(p['id'],'u'))
    assert updated['state']['attachment_ids']==['original']
    assert updated['state']['manual_checkpoint']['logo_attachment_id']==image['id']
    assert updated['status']=='awaiting_confirmation'


@pytest.mark.parametrize('text',['رنگ لوگو رو تغییر بده','اندازه لوگو رو عوض کن','لوگو را حذف کن'])
def test_logo_setting_edits_do_not_ask_for_replacement(text):
    assert not manual.requests_logo_replacement(text)


def test_ready_job_applies_attachment_preferences_outside_async_loop(store, monkeypatch, tmp_path):
    from types import SimpleNamespace
    from app import studio_orchestrator as o, talking_reel
    c=run(store.create_conversation('u'))
    p=run(store.create_project(c['id'],'u','talking','test',
        {'manual_answers':{'name':'Mahtab'}, 'auto_render':True},'job'))
    monkeypatch.setattr(o.jobstore,'get',lambda _:SimpleNamespace(dir=tmp_path,raw_name='source.mp4'))
    monkeypatch.setattr(talking_reel,'load',lambda _:{'status':'ready','stage':'','progress':100})
    monkeypatch.setattr(talking_reel,'public',lambda s:s)
    # The real attachment adapter resolves ownership using repo.run().
    monkeypatch.setattr(manual,'apply_talking_preferences',lambda *args:run(asyncio.sleep(0)))
    starts=[]
    monkeypatch.setattr(talking_reel,'start',lambda *args,**kw:starts.append(args))
    refreshed=[]
    async def refresh_plan(cid,user,project,job,**kwargs):
        refreshed.append(project['state'].get('manual_preferences_applied'))
        return await store.update_project(project['id'],user,status='awaiting_confirmation',state=project['state']),True
    monkeypatch.setattr(o,'_refresh_plan',refresh_plan)
    run(o.sync_conversation(c['id'],'u'))
    assert starts==[]  # New versioned approval gate must not auto-render.
    assert refreshed==[True]
    assert run(store.get_project(p['id'],'u'))['state']['manual_preferences_applied'] is True


def test_phase_narration_is_deduplicated_and_never_restarts_render(store, monkeypatch, tmp_path):
    from types import SimpleNamespace
    from app import studio_orchestrator as o, talking_reel
    c=run(store.create_conversation('u'))
    p=run(store.create_project(c['id'],'u','talking','test',{},'job'))
    status={'status':'running','stage':'rendering','progress':40}
    monkeypatch.setattr(o.jobstore,'get',lambda _:SimpleNamespace(dir=tmp_path))
    monkeypatch.setattr(talking_reel,'load',lambda _:status)
    monkeypatch.setattr(talking_reel,'public',lambda s:s)
    monkeypatch.setattr(talking_reel,'start',lambda *a,**k:pytest.fail('must not restart renderer'))
    now=[1000.]
    monkeypatch.setattr(o.time,'time',lambda:now[0])
    run(o.sync_conversation(c['id'],'u'))
    now[0]=1035.
    run(o.sync_conversation(c['id'],'u'))
    run(o.sync_conversation(c['id'],'u'))
    events=run(store.events(c['id'],'u',0))
    notes=[e for e in events if e['type']=='agent.narration']
    assert len(notes)==2
    assert '35' in notes[-1]['data']['message']
    assert run(store.get_project(p['id'],'u'))['state']['activity_phase']['started_at']==1000.


def test_automatic_mode_collects_identity_and_explicit_opt_out(store):
    conv = run(store.create_conversation('u'))
    session = manual.begin(conv['id'], 'u', 'talking', 'edit', [], essentials=True)
    answers = {'style':'talking_1','name':'Mahtab Asgari','tagline':'Co-founder of eatfitapp',
               'logo':'off','cta':'none','reference':'skip'}
    while session.get('question_id'):
        key = manual.question(session)['key']
        assert key not in {'logo_asset','logo_color','look','font','analyze'}
        session = manual.answer(conv['id'],'u',session,session['question_id'],answers[key],[])
    changes = manual.talking_changes(session['answers'], {})
    assert changes['name'] == 'Mahtab Asgari'
    assert changes['title'] == 'Co-founder of eatfitapp'
    assert changes['cta'] == ''
    assert changes['render_settings']['outro_logo']['enabled'] is False


def test_manual_question_is_persisted_and_source_is_not_a_reference(store):
    conv = run(store.create_conversation('u'))
    source = run(store.create_attachment(conv['id'], 'u', kind='video', filename='source.mp4', path='/source', mime_type='video/mp4', size_bytes=1))
    session = manual.begin(conv['id'], 'u', 'talking', 'این را تدوین کن', [source['id']])
    assert len(manual.question(session)['choices']) == 4      # Talking 4 is retired from every picker
    loaded = _public_conversation(run(store.get_conversation(conv['id'], 'u')))
    assert loaded['state']['manual_question']['id'] == session['question_id']
    with pytest.raises(ValueError, match='فعال نیست'):
        manual.answer(conv['id'], 'u', session, 'stale', 'talking_2', [])
    next_session = manual.answer(conv['id'], 'u', session, session['question_id'], 'talking_2', [])
    assert next_session['attachment_ids'] == [source['id']]
    assert next_session['reference_ids'] == []
    with pytest.raises(ValueError, match='تکراری'):
        manual.answer(conv['id'], 'u', session, session['question_id'], 'talking_2', [])


def test_reference_ownership_and_explicit_upload(store):
    c = run(store.create_conversation('u')); other = run(store.create_conversation('other'))
    private = run(store.create_attachment(other['id'], 'other', kind='image', filename='ref.png', path='/private', mime_type='image/png', size_bytes=1))
    s = manual.begin(c['id'], 'u', 'motion', 'تبلیغ', [])
    s = manual.answer(c['id'], 'u', s, s['question_id'], 'minimal', [])
    with pytest.raises(KeyError): manual.answer(c['id'], 'u', s, s['question_id'], 'attached', [private['id']])
    with pytest.raises(ValueError, match='پیوست'):
        manual.answer(c['id'], 'u', s, s['question_id'], 'attached', [])
    s = manual.answer(c['id'], 'u', s, s['question_id'], 'skip', [])
    assert manual.question(s)['key'] == 'analyze'


def test_creating_project_preserves_mode_and_manual_context(store):
    c = run(store.create_conversation('u'))
    run(store.set_conversation(c['id'], 'u', state={'execution_mode':'manual','manual_session': {'id':'saved'}}))
    p = run(store.create_project(c['id'], 'u', 'talking', 't'))
    state = run(store.get_conversation(c['id'], 'u'))['state']
    assert state['execution_mode'] == 'manual' and state['manual_session']['id'] == 'saved'
    assert state['current_project_id'] == p['id']


def test_manual_stops_before_engine_calls(store, monkeypatch):
    from app import studio_orchestrator as o
    c = run(store.create_conversation('u'))
    run(store.set_conversation(c['id'], 'u', state={'execution_mode':'manual'}))
    a = run(store.create_attachment(c['id'], 'u', kind='video', filename='source.mp4', path='/source', mime_type='video/mp4', size_bytes=1))
    m = run(store.add_message(c['id'], 'u', 'user', 'صحبتی دو', [a['id']]))
    monkeypatch.setattr(o, 'execute', lambda *a, **k: pytest.fail('manual must stop before executing engines'))
    process_message(c['id'], 'u', m['id'], m['content'], [a['id']])
    assert run(store.get_conversation(c['id'], 'u'))['state']['manual_session']['engine'] == 'talking'


def test_manual_talking_settings_are_real_engine_settings():
    from app.talking_reel import _clean_render_settings
    change = manual.talking_changes({'look':'warm','font':'Vazirmatn','color':'#FFFFFF','logo':'off','cta':'سایت ما را ببین'}, {})
    settings = _clean_render_settings(change['render_settings'])
    assert settings['grade']['temperature'] == 12
    assert settings['outro_logo']['enabled'] is False
    assert settings['caption_font'] == 'Vazirmatn'
    assert change['cta'] == 'سایت ما را ببین'


def test_checkpoint_is_single_use_and_user_scoped(store):
    c = run(store.create_conversation('u'))
    p = run(store.create_project(c['id'], 'u', 'talking', 't', {'manual_mode':True}))
    assert run(manual.render_checkpoint(c['id'], 'u', p, {'hook':'هوک'}))
    p = run(store.get_project(p['id'], 'u')); qid = p['state']['manual_checkpoint']['id']
    assert run(manual.render_checkpoint(c['id'], 'u', p, {'hook':'هوک'}))
    assert len(run(store.events(c['id'], 'u', 0))) == 1
    with pytest.raises(KeyError): run(store.claim_manual_checkpoint(p['id'], 'other', qid))
    assert run(store.claim_manual_checkpoint(p['id'], 'u', qid))
    assert not run(store.claim_manual_checkpoint(p['id'], 'u', qid))


def test_manual_talking_ready_never_auto_renders(store, monkeypatch, tmp_path):
    """Ready analysis stops at the Creative Plan gate (Auto and Manual alike); nothing renders unapproved."""
    from types import SimpleNamespace
    from app import studio_orchestrator as o, talking_reel
    monkeypatch.setattr(o.jobstore, 'JOBS_ROOT', tmp_path)
    c = run(store.create_conversation('u'))
    p = run(store.create_project(c['id'], 'u', 'talking', 't', {'manual_mode':True,'auto_render':False}, 'job'))
    monkeypatch.setattr(o.jobstore, 'get', lambda ref: SimpleNamespace(dir=tmp_path, raw_name='v.mp4'))
    async def nothing(*args): pass
    monkeypatch.setattr(o, '_sync_motion_messages', nothing)
    state = {'status':'ready','style':'talking_2','render_settings':{}}
    monkeypatch.setattr(talking_reel, 'load', lambda _: state)
    monkeypatch.setattr(talking_reel, 'public', lambda s:s)
    monkeypatch.setattr(talking_reel, 'update', lambda *a:None)
    monkeypatch.setattr(talking_reel, 'start', lambda *a, **k: pytest.fail('unapproved render'))
    monkeypatch.setattr(o, '_talking_context', lambda job: (tmp_path / 'v.mp4', state, [{'start':0,'end':2,'text':'سلام'}]))
    monkeypatch.setattr(o, '_plan_frames', lambda *a: {})
    monkeypatch.setattr(o, 'execute', lambda name, payload: {'duration': 30.0})
    run(sync_conversation(c['id'], 'u'))
    p = run(store.get_project(p['id'], 'u'))
    assert p['status'] == 'awaiting_confirmation'
    assert p['state']['workflow'] == 'awaiting_approval'
    assert p['state']['plan']['versions'][-1]['content']['style']['id'] == 'talking_2'


def test_message_contract_rejects_invalid_modes():
    from pydantic import ValidationError
    with pytest.raises(ValidationError): MessageCreate(content='test', execution_mode='magic')


def test_followup_after_completed_manual_session_is_sent(store, monkeypatch):
    from types import SimpleNamespace
    from app.routers import studio
    c = run(store.create_conversation('u'))
    run(store.set_conversation(c['id'], 'u', state={'execution_mode':'manual',
        'manual_session':{'engine':'talking','index':len(manual.steps('talking')), 'question_id':None}}))
    calls = []
    monkeypatch.setattr(studio, 'dispatch_message', lambda *args: calls.append(args))
    request = SimpleNamespace(state=SimpleNamespace(user=SimpleNamespace(id='u')))
    message = run(studio.send_message(request, c['id'], MessageCreate(content='درستش کن', execution_mode='manual')))
    assert message['content'] == 'درستش کن'
    assert calls[0][-1] is None
    assert calls[0][3] == 'درستش کن'


def test_revision_can_remove_incorrect_speaker_identity():
    from creative.revise import apply_to_talking, RevisionOp
    result = apply_to_talking({'style':'talking_1'}, [RevisionOp(op='clear_identity')], 1)
    assert result.changes['name'] == result.changes['title'] == ''


def test_logo_file_only_message_answers_logo_step(store):
    c = run(store.create_conversation('u'))
    image = run(store.create_attachment(c['id'], 'u', kind='image', filename='logo.png', path='/logo', mime_type='image/png', size_bytes=1))
    s = manual.begin(c['id'], 'u', 'talking', 'تدوین', [])
    s['index'] = next(i for i,v in enumerate(manual.session_steps(s)) if v['key']=='logo_asset')
    manual.save(c['id'], 'u', s)
    s = manual.answer(c['id'], 'u', s, s['question_id'], 'این فایل را بررسی کن و برای تدوین آماده کن', [image['id']])
    assert s['logo_attachment_id'] == image['id']
    assert s['answers']['logo_asset'] == 'attached'


def test_caption_preference_only_changes_captions():
    from engine.caption_preferences import caption_font
    original = 'Style: hook,Ray,50\nStyle: key,Ray,42\nStyle: lead,Ray,40\n'
    result = caption_font(original, {'caption_font':'Vazirmatn'})
    assert 'hook,Ray' in result and 'key,Vazirmatn' in result and 'lead,Vazirmatn' in result
    assert caption_font(original, {}) == original


def test_all_choices_resume_original_source_and_explicit_selected_style(store, monkeypatch):
    from app import studio_orchestrator as o
    c = run(store.create_conversation('u'))
    run(store.set_conversation(c['id'], 'u', state={'execution_mode':'manual'}))
    a = run(store.create_attachment(c['id'], 'u', kind='video', filename='source.mp4', path='/source', mime_type='video/mp4', size_bytes=1))
    s = manual.begin(c['id'], 'u', 'talking', 'تدوین صحبتی دو', [a['id']])
    answers = {'style':'talking_1','name':'Mahtab Asgari','tagline':'Co-founder of eatfitapp','look':'warm','font':'Vazirmatn','color':'#FFFFFF','logo':'off',
               'logo_asset':'existing','logo_color':'original','cta':'none','reference':'skip'}
    while manual.question(s)['key'] != 'analyze':
        s = manual.answer(c['id'], 'u', s, s['question_id'], answers[manual.question(s)['key']], [])
    calls = []
    monkeypatch.setattr(o, 'execute', lambda name, payload: calls.append((name,payload)) or {'external_ref':'test-job'})
    monkeypatch.setattr(o, '_resolved_intent', lambda *a, **k: pytest.fail('must reuse selected engine without another LLM call'))
    m = run(store.add_message(c['id'], 'u', 'user', 'تأیید تحلیل'))
    process_message(c['id'], 'u', m['id'], 'approve', [], s['question_id'])
    assert len(calls) == 1 and calls[0][0] == 'analyze_talking_reel'
    assert calls[0][1]['style'] == 'talking_1' and calls[0][1]['source_path'] == '/source'
    conversation = run(store.get_conversation(c['id'], 'u'))
    assert len(conversation['projects']) == 1
    assert conversation['projects'][0]['state']['auto_render'] is False
    assert conversation['state']['manual_session']['question_id'] is None


def test_resume_cannot_bypass_manual_gate(store):
    from app.studio_orchestrator import resume_project
    c = run(store.create_conversation('u'))
    p = run(store.create_project(c['id'], 'u', 'talking', 't', {'manual_checkpoint':{'id':'q'}}))
    with pytest.raises(ValueError, match='تأیید مرحله'):
        resume_project(p['id'], 'u', retry_confirmed=True)


def test_manual_editing_replaces_requested_revision_without_running_engine(store, monkeypatch):
    from app import studio_orchestrator as o
    c = run(store.create_conversation('u'))
    p = run(store.create_project(c['id'], 'u', 'talking', 't', {'manual_editing':True,
        'manual_checkpoint':{'id':'q','revision_text':'old','summary':'old'}}))
    monkeypatch.setattr(o, '_modify', lambda *args: pytest.fail('must not run until fresh approval'))
    assert _answer_manual_checkpoint(c['id'], 'u', p, 'هوک جدید', 'q')
    q = run(store.get_project(p['id'], 'u'))['state']['manual_checkpoint']
    assert q['id'] != 'q' and q['revision_text'] == 'هوک جدید'


def test_a_damaged_local_store_is_recovered_not_read_as_empty(tmp_path, monkeypatch):
    """Two processes writing at once left valid JSON followed by stray bytes; reading that as empty wiped everything."""
    import json
    monkeypatch.setattr(studio_store, 'DB_AVAILABLE', False)
    monkeypatch.setattr(studio_store, 'ROOT', tmp_path)
    monkeypatch.setattr(studio_store, 'FALLBACK', tmp_path / 'studio.json')
    good = studio_store._empty(); good['conversations']['c1'] = {'id': 'c1', 'user_key': 'u', 'title': 'نگه دار'}
    (tmp_path / 'studio.json').write_text(json.dumps(good) + '\n  ]\n }')
    assert studio_store._read()['conversations']['c1']['title'] == 'نگه دار'
    assert json.loads((tmp_path / 'studio.json').read_text())['conversations']['c1']      # repaired on disk
    assert list(tmp_path.glob('studio.damaged-*.json'))                                    # the damaged copy is kept
    (tmp_path / 'studio.json').write_text('{"conversations": {"x"')                        # nothing intact to recover
    with pytest.raises(RuntimeError):
        studio_store._read()
    assert (tmp_path / 'studio.json').read_text().startswith('{"conversations": {"x"')     # never overwritten with an empty store


def test_concurrent_writers_never_interleave_bytes(tmp_path, monkeypatch):
    import json, threading
    monkeypatch.setattr(studio_store, 'ROOT', tmp_path)
    monkeypatch.setattr(studio_store, 'FALLBACK', tmp_path / 'studio.json')
    sizes = (5, 5000, 50)
    def write(n):
        for _ in range(30):
            data = studio_store._empty(); data['messages']['m'] = ['x' * 300] * n
            studio_store._write(data)
    threads = [threading.Thread(target=write, args=(n,)) for n in sizes]
    [t.start() for t in threads]; [t.join() for t in threads]
    assert json.loads((tmp_path / 'studio.json').read_text())['messages']['m'][0].startswith('x')
