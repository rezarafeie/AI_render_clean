import json
import pytest
from brain import lm_direct,transcribe


def test_stt_settings_survive_text_provider_save(monkeypatch,tmp_path):
    monkeypatch.setattr(lm_direct.settings,'JOBS_DIR',str(tmp_path))
    value=lm_direct.save_config(False,[],{'enabled':True,'model':'medium','improve_low_quality':False})
    assert value['stt']['model']=='medium'
    assert lm_direct.save_config(True,[])['stt']==value['stt']
    with pytest.raises(ValueError):lm_direct.save_config(True,[],{'model':'invented'})


def test_whisper_review_preserves_timing_and_runs_once(monkeypatch,tmp_path):
    import brain.correct
    raw={'file_hash':'file','cache_key':'key','engine':'whisper','language':'fa','duration':1,
         'words':[{'w':'کلمه','start':0,'end':1,'prob':.5}],'sentences':[{'text':'کلمه','start':0,'end':1}]}
    (tmp_path/'transcript.json').write_text(json.dumps(raw))
    calls=[]
    def correct(*args):
        calls.append(1)
        return [{'index':0,'old':'کلمه','new':'کلمهٔ','confidence':.95,'type':'replace'}],None
    monkeypatch.setattr(brain.correct,'auto_correct',correct)
    result=transcribe.improve_local_transcript(raw,tmp_path)
    transcribe.improve_local_transcript(raw,tmp_path)
    assert len(calls)==1 and result['words'][0]['w']=='کلمهٔ'
    assert result['words'][0]['start']==0 and result['words'][0]['end']==1


def test_good_or_empty_transcript_does_not_call_ai(monkeypatch,tmp_path):
    import brain.correct
    monkeypatch.setattr(brain.correct,'auto_correct',lambda *a:pytest.fail('No unnecessary AI'))
    for words in [[],[{'w':'clear','prob':.99}]]:
        raw={'words':words};assert transcribe.improve_local_transcript(raw,tmp_path)==raw


def _transcript(video, engine, key):
    return {'engine': engine, 'file_hash': transcribe.file_hash(video), 'requested_language': 'fa', 'cache_key': key,
            'words': [{'w': 'سلام', 'start': 0, 'end': 1, 'prob': .99}], 'sentences': [{'text': 'سلام', 'start': 0, 'end': 1}]}


def test_stt_starts_with_elevenlabs_and_never_repeats_a_paid_call(monkeypatch, tmp_path):
    import brain.transcribe_elevenlabs as providers
    from brain import lm_gateway
    monkeypatch.setattr(lm_gateway, 'configured', lambda: True)
    monkeypatch.setattr(lm_direct.settings, 'JOBS_DIR', str(tmp_path))
    video = tmp_path / 'input.mp4'; video.write_bytes(b'fixture')
    calls = []
    def direct(*a, **kw): calls.append('elevenlabs'); return _transcript(video, 'elevenlabs', 'direct'), 0.0
    def router(*a, provider, **kw): calls.append(provider); raise AssertionError('ElevenLabs answered: the router is not asked')
    monkeypatch.setattr(providers, 'transcribe_elevenlabs', direct)
    monkeypatch.setattr(providers, 'transcribe_gateway', router)
    root = tmp_path / 'job'
    assert transcribe.transcribe(video, root, language='fa', engine='elevenlabs')['engine'] == 'elevenlabs'
    transcribe.transcribe(video, root, language='fa', engine='elevenlabs')           # cached: nothing is paid for twice
    assert calls == ['elevenlabs']


def test_the_router_is_the_second_slot(monkeypatch, tmp_path):
    import brain.transcribe_elevenlabs as providers
    from brain import lm_gateway
    monkeypatch.setattr(lm_gateway, 'configured', lambda: True)
    monkeypatch.setattr(lm_direct.settings, 'JOBS_DIR', str(tmp_path))
    video = tmp_path / 'input.mp4'; video.write_bytes(b'fixture')
    calls = []
    def direct(*a, **kw): calls.append('elevenlabs'); raise RuntimeError('unavailable')
    def router(*a, provider, **kw): calls.append(provider); return _transcript(video, 'elevenlabs_jarvis', 'router'), None
    monkeypatch.setattr(providers, 'transcribe_elevenlabs', direct)
    monkeypatch.setattr(providers, 'transcribe_gateway', router)
    assert transcribe.transcribe(video, tmp_path / 'job', language='fa', engine='elevenlabs')['engine'] == 'elevenlabs_jarvis'
    assert calls == ['elevenlabs', 'jarvis']


def test_local_whisper_runs_only_after_elevenlabs_and_the_router(monkeypatch, tmp_path):
    import brain.transcribe_elevenlabs as providers
    from brain import lm_gateway
    monkeypatch.setattr(lm_gateway, 'configured', lambda: True)
    monkeypatch.setattr(lm_direct.settings, 'JOBS_DIR', str(tmp_path))
    video = tmp_path / 'input.mp4'; video.write_bytes(b'fixture'); calls = []
    def own(*a, **k): calls.append('direct'); raise RuntimeError('unavailable')
    def remote(*a, provider, **k): calls.append(provider); raise RuntimeError('unavailable')
    def local(video, root, digest, model, *args):
        calls.append('whisper')
        assert model == 'small'
        value = {'file_hash': digest, 'cache_key': 'local', 'requested_language': 'fa', 'engine': 'whisper',
                 'words': [{'w': 'سلام', 'start': 0, 'end': 1, 'prob': .99}],
                 'sentences': [{'text': 'سلام', 'start': 0, 'end': 1}]}
        (root / 'transcript.json').write_text(json.dumps(value)); return value
    monkeypatch.setattr(providers, 'transcribe_elevenlabs', own)
    monkeypatch.setattr(providers, 'transcribe_gateway', remote)
    monkeypatch.setattr(transcribe, '_transcribe_whisper', local)
    monkeypatch.setenv('WHISPER_ENABLED', 'true')
    result = transcribe.transcribe(video, tmp_path / 'job', language='fa', engine='elevenlabs')
    assert result['engine'] == 'whisper' and calls == ['direct', 'jarvis', 'whisper']
