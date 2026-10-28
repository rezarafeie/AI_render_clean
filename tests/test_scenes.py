"""Maintained scene templates reject executable design input at the page boundary."""
import pytest
from pydantic import ValidationError
from engine.hyperframes import VisualBeat, build_project
from creative import motion, motion_graphic


def test_templates_escape_text_and_ignore_legacy_code(tmp_path, monkeypatch):
    gsap = tmp_path / 'gsap.js'; gsap.write_text('local fixture')
    monkeypatch.setattr('engine.hyperframes.assets.ensure_gsap', lambda: gsap)
    base = tmp_path / 'base.mp4'; base.touch()
    beat = VisualBeat(id='beat-0', start=0, end=3, title='سلام ۱۲ <script>', visual_type='kinetic_type',
        custom={'html':'EVIL_HTML', 'css':'EVIL_CSS', 'js':'EVIL_JS'})
    entry = build_project(tmp_path / 'project', base, [beat], duration=3, enable_registry=False)
    page = entry.read_text()
    assert all(code not in page for code in ('EVIL_HTML', 'EVIL_CSS', 'EVIL_JS'))
    assert '&lt;script&gt;' in page and 'سلام ۱۲' in page
    assert 'dir="rtl"' in page and 'ray-extrabold.ttf' in page
    assert 'height:888px' in page and 'letter-spacing:-' not in page
    assert 'custom' not in beat.model_dump()


@pytest.mark.parametrize('field,value', [('id','bad";alert(1)'), ('accent','red; background:url(evil)'), ('visual_type','<script>')])
def test_executable_identifiers_are_rejected(field, value):
    with pytest.raises(ValidationError):
        VisualBeat(**{**dict(id='a', start=0, end=3, title='سلام'), field:value})


def test_fullscreen_requires_explicit_permission(tmp_path, monkeypatch):
    gsap=tmp_path/'gsap.js';gsap.touch()
    monkeypatch.setattr('engine.hyperframes.assets.ensure_gsap',lambda:gsap)
    base=tmp_path/'base.mp4';base.touch()
    beat=VisualBeat(id='a',start=0,end=3,title='سلام',layout='full_frame')
    with pytest.raises(ValueError,match='explicit permission'):
        build_project(tmp_path/'rejected',base,[beat],duration=3)
    assert build_project(tmp_path/'allowed',base,[beat],duration=3,enable_registry=False,allow_full_frame=True).is_file()


def test_legacy_cache_is_never_read_and_no_provider_is_called(tmp_path,monkeypatch):
    monkeypatch.setattr('creative.llm.ask', lambda *a,**k: pytest.fail('provider call'))
    cache=tmp_path/'old.json';cache.write_text('{"scenes":{"html":"EVIL"}}')
    beats=[VisualBeat(id='a',start=0,end=3,title='۱۲ گام')]
    assert motion.compose(beats,None,[],cache=cache) is beats
    assert not motion.enabled() and not hasattr(beats[0],'custom')


@pytest.mark.parametrize('entry', ['author','repair','plan','author_scene','assemble','assemble_scenes','write_project'])
def test_chat_motion_code_entry_points_are_disabled(entry):
    with pytest.raises(Exception,match='در دسترس نیست'):
        getattr(motion_graphic,entry)({'html':'EVIL'})
