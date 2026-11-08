import base64
import io
from PIL import Image
from brain import lm_gateway as gateway, lm_adapters
from brain.media_provider import get_provider


def test_configured_image_generation_uses_database_gateway_route(monkeypatch,tmp_path):
    monkeypatch.setattr(gateway,'configured',lambda:True)
    monkeypatch.setattr(gateway,'defaults',lambda:{'photorealistic_image':{'enabled':True}})
    image=io.BytesIO();Image.new('RGB',(32,32),'blue').save(image,format='PNG')
    calls=[]
    def complete(route,prompt,**kwargs):
        calls.append((route,prompt,kwargs))
        return {'model':'tested-image','data':[{'b64_json':base64.b64encode(image.getvalue()).decode()}]},{'requested_model':'tested-image','cost':None}
    monkeypatch.setattr(gateway,'complete',complete)
    provider=get_provider('lm_gateway')
    assert provider.name=='lm_gateway'
    result=provider.generate_image('A landscape','9:16',tmp_path)
    assert Image.open(result.file_path).size==(32,32)
    assert calls[0][0]=='photorealistic_image'
    assert calls[0][2]['endpoint']=='image'


def test_media_payload_and_redaction():
    payload=lm_adapters.payload('image','exact-model','prompt',extra={'n':1,'size':'1024x1024'})
    assert payload=={'model':'exact-model','prompt':'prompt','n':1,'size':'1024x1024'}
    assert 'ABCDEF' not in gateway.safe({'b64_json':'ABCDEF'})


def test_tts_uses_gateway_instead_of_direct_transport(monkeypatch,tmp_path):
    from brain.tts import _generate_elevenlabs
    monkeypatch.setattr(gateway,'configured',lambda:True)
    calls=[]
    def speech(route,text,voice):
        calls.append((route,text,voice));return b'tested-audio'
    monkeypatch.setattr(gateway,'speech',speech)
    output=tmp_path/'sample.mp3'
    _generate_elevenlabs('سلام',str(output),voice_id='existing-voice')
    assert output.read_bytes()==b'tested-audio'
    assert calls==[('narration','سلام','existing-voice')]


def test_resume_reuses_owned_job_and_rejects_other_users(monkeypatch,tmp_path):
    import pytest
    from types import SimpleNamespace
    from app import studio_store, studio_orchestrator as o
    from brain import content_creator
    from app.studio_store import repo,run
    monkeypatch.setattr(studio_store,'DB_AVAILABLE',False)
    monkeypatch.setattr(studio_store,'ROOT',tmp_path)
    monkeypatch.setattr(studio_store,'FALLBACK',tmp_path/'studio.json')
    conversation=run(repo.create_conversation('owner'))
    project=run(repo.create_project(conversation['id'],'owner','motion','Existing',{'confirmed':True},'same-job'))
    job=SimpleNamespace(dir=tmp_path,render=SimpleNamespace(status='idle'))
    monkeypatch.setattr(o.jobstore,'get',lambda ref: job if ref=='same-job' else None)
    monkeypatch.setattr(o,'_provider',lambda:'lm_gateway')
    generation={'state':'failed'};calls=[]
    monkeypatch.setattr(content_creator,'get_storyboard_status',lambda _:generation)
    def approve(existing,provider_name,**kwargs):
        assert existing is job
        calls.append(provider_name);generation['state']='generating'
    monkeypatch.setattr(content_creator,'approve_and_generate',approve)
    with pytest.raises(KeyError): o.resume_project(project['id'],'different-user')
    with pytest.raises(ValueError): o.resume_project(project['id'],'owner')
    assert calls==[]
    assert o.resume_project(project['id'],'owner',retry_confirmed=True)['stage']=='generating assets'
    assert o.resume_project(project['id'],'owner')['status']=='running'
    assert calls==['lm_gateway']
    assert run(repo.get_project(project['id'],'owner'))['external_ref']=='same-job'
