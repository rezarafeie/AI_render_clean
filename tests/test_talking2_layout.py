from types import SimpleNamespace

from engine.talking_styles import talking_2, talking_4
from engine.hyperframes.builder import build_visual_beats, _timeline_script


def test_plain_panel_reuse_does_not_invalidate_every_cached_shot(tmp_path):
    import os
    from PIL import Image
    path=talking_2.plain_panel(tmp_path/'plain.png')
    os.utime(path,ns=(1_000_000_000,1_000_000_000))
    talking_2.plain_panel(path)
    assert path.stat().st_mtime_ns == 1_000_000_000
    Image.new('RGB',(8,8),'red').save(path)
    talking_2.plain_panel(path)
    with Image.open(path) as restored:
        assert restored.size == (int(talking_2.W*1.12),int(talking_2.SPLIT_Y*1.12))


def test_check_error_summary_keeps_real_blocker_not_warning_tail(tmp_path):
    import json
    from engine.hyperframes.renderer import check_failure_summary
    folder=tmp_path/'.hyperframes/artifacts/checks';folder.mkdir(parents=True)
    (folder/'report.json').write_text(json.dumps({'lint':{'findings':[
        {'severity':'error','code':'invalid_inline_script_syntax','message':'Unexpected token'},
        {'severity':'warning','code':'nested_structure_needs_subcomposition','message':'Use subcomposition'}]}}))
    summary=check_failure_summary(tmp_path,'warnings only')
    assert 'Unexpected token' in summary and 'Use subcomposition' not in summary


def transcript(count=11):
    sentences = [{'start': i*3., 'end': i*3.+2.8, 'text': f'مفهوم شماره {i} برای سلامتی'} for i in range(count)]
    words = [{'start': i*3., 'end': i*3.+2.8, 'w': 'سلامتی'} for i in range(count)]
    return {'sentences': sentences, 'words': words}


def test_groups_cover_edited_timeline_and_all_sentences():
    t = transcript()
    shots = [SimpleNamespace(src_in=0, src_out=33, out_start=0)]
    plan = SimpleNamespace(continuous_split=True, duration=33, shots=shots, cold_open=0)
    beats = build_visual_beats(plan, {}, t)
    assert [len(b.sentence_indices) for b in beats] == [5, 4, 2]
    assert [i for b in beats for i in b.sentence_indices] == list(range(11))
    assert beats[0].start == 0 and beats[-1].end == 33
    assert all(a.end == b.start for a,b in zip(beats, beats[1:]))
    assert all(b.layout == 'top_panel' and b.spoken for b in beats)
    assert '#speaker-stage' not in _timeline_script(beats)


def test_native_split_fills_bottom_and_keeps_full_width_caption_rail():
    t = transcript(2)
    d = {'captions': {i:s['text'] for i,s in enumerate(t['sentences'])}, 'drop': []}
    plan = talking_2.plan_reel(t, d, [], 6)
    assert plan.shots and all(s.split for s in plan.shots)
    ass = talking_2.build_ass(plan, None)
    assert '960)' in ass  # caption centre at the seam, not inside speaker PiP
    assert '1080' in ass and '101010' in ass
    cw,ch,x,y = talking_2.speaker_crop(plan.shots[0],1080,1920)
    assert abs(cw/ch - 1080/960) < .01
    minimal = talking_4.plan_reel(t,d,[],6)
    assert not minimal.continuous_split and all(not s.split for s in minimal.shots)


def test_talking2_preserves_ass_hook_without_tscaps(tmp_path,monkeypatch):
    seen=[]
    monkeypatch.setattr(talking_2,'render_plain',lambda v,p,o,**kw:seen.append(p) or o)
    p=talking_2.ReelPlan([],hook={'start':0,'end':2,'text':'سلام دنیا'})
    talking_2.render(tmp_path/'v.mp4',p,tmp_path/'o.mp4',work_dir=tmp_path)
    assert seen[0].hook == p.hook


def test_reference_screenshots_are_existing_project_revision(monkeypatch):
    from app.studio_orchestrator import _resolved_intent
    current={'engine':'talking','external_ref':'owned-job'}
    assert _resolved_intent('قاب رو کامل کن با talking 2',[{'kind':'image'}],current)=='modify'
    assert _resolved_intent('صحبتی یک استفاده کن',[],current)=='modify'
    assert _resolved_intent('صحبتی یک',[{'kind':'video'}],current)=='talking'


def test_panel_project_excludes_speaker_and_has_half_canvas(tmp_path, monkeypatch):
    from engine.hyperframes.builder import build_project
    from engine.hyperframes.schema import VisualBeat
    gsap=tmp_path/'gsap.js';gsap.write_text('/* local fixture */')
    monkeypatch.setattr('engine.hyperframes.assets.ensure_gsap',lambda:gsap)
    source=tmp_path/'base.mp4';source.write_bytes(b'test')
    b=VisualBeat(id='beat-0',start=0,end=3,title='سلام',layout='top_panel',custom={
        'html':'<h2>سلام</h2>','css':'#beat-0{background:#123456}',
        'js':'tl.set($("h2"),{opacity:1},T);','speaker':'pip'})
    entry=build_project(tmp_path/'panel',source,[b],duration=3,enable_registry=False,motion_only=True)
    document=entry.read_text()
    assert 'data-height="888"' in document and '<video' not in document
    assert 'tl.to("#speaker-stage"' not in document


def test_actual_native_split_export(tmp_path,monkeypatch):
    import os, subprocess, json
    import pytest
    if os.environ.get('RUN_TALKING2_RENDER_SMOKE') != '1':
        pytest.skip('opt-in actual FFmpeg composition')
    from engine.render_ass import ass_burner_ffmpeg
    ffmpeg=ass_burner_ffmpeg()
    if not ffmpeg:pytest.skip('FFmpeg/libass unavailable')
    source=tmp_path/'source.mp4'
    subprocess.run([ffmpeg,'-hide_banner','-v','error','-y','-f','lavfi','-i',
        'color=c=blue:s=540x960:r=30:d=3','-f','lavfi','-i','sine=frequency=440:duration=3',
        '-c:v','libx264','-preset','ultrafast','-c:a','aac','-shortest',str(source)],check=True)
    monkeypatch.setattr(talking_2,'render_outro',lambda *a,**k:(None,0))
    p=talking_2.ReelPlan([talking_2.Shot(0,3,split=True)],duration=3,
        captions=[{'start':0,'end':3,'lead':'سلامتی','key':'مهم است'}])
    output=tmp_path/'split.mp4'
    talking_2.render(source,p,output,work_dir=tmp_path/'work')
    subprocess.run([ffmpeg,'-v','error','-i',str(output),'-f','null','-'],check=True)
    info=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json',str(output)]))
    assert any(s.get('width')==1080 and s.get('height')==1920 for s in info['streams'])
    assert any(s['codec_type']=='audio' for s in info['streams'])
    subprocess.run([ffmpeg,'-v','error','-y','-ss','1','-i',str(output),'-frames:v','1',str(tmp_path/'split.jpg')],check=True)
    from PIL import Image
    with Image.open(tmp_path/'split.jpg') as im:
        for x in (5,540,1075):
            r,g,b=im.getpixel((x,1500));assert b>r+50  # bottom is full-width, not tiny PiP
        r,g,b=im.getpixel((10,960));assert max(r,g,b)<40  # full-width caption backing


def test_actual_browser_panel_and_native_composite(tmp_path,monkeypatch):
    import os,subprocess
    from pathlib import Path
    import pytest
    if os.environ.get('RUN_TALKING2_HF_SMOKE') != '1':
        pytest.skip('opt-in actual Chromium panel and FFmpeg assembly')
    monkeypatch.setenv('RUN_TALKING2_RENDER_SMOKE','1')
    test_actual_native_split_export(tmp_path,monkeypatch)
    gsap=Path(os.environ['TALKING2_SMOKE_GSAP'])
    monkeypatch.setattr('engine.hyperframes.assets.ensure_gsap',lambda:gsap)
    from engine.hyperframes.builder import build_project
    from engine.hyperframes.schema import VisualBeat
    from engine.hyperframes.renderer import render_project
    b=VisualBeat(id='beat-0',start=0,end=3,title='خواب و سلامتی',layout='top_panel',custom={
        'html':'<div class="proof"><h2>خواب و سلامتی</h2><svg viewBox="0 0 800 200"><path d="M10 180L240 140L500 80L780 20" fill="none" stroke="#55ddaa" stroke-width="15"/></svg></div>',
        'css':'#beat-0{background:#142522} #beat-0 .proof{padding:110px 70px;color:#ffffff;font-family:Ray} #beat-0 h2{font-size:90px;letter-spacing:0} #beat-0 svg{width:800px;height:200px}',
        'js':'tl.fromTo($(".proof"),{opacity:0,y:30},{opacity:1,y:0,duration:.4},T);', 'speaker':'pip'})
    project=tmp_path/'composition'
    build_project(project,tmp_path/'split.mp4',[b],duration=3,enable_registry=False)
    final=render_project(project,tmp_path/'combined.mp4',timeout=180)
    subprocess.run(['ffmpeg','-v','error','-i',str(final),'-f','null','-'],check=True)
    subprocess.run(['ffmpeg','-v','error','-y','-ss','1','-i',str(final),'-frames:v','1',str(tmp_path/'combined.jpg')],check=True)
    from PIL import Image
    with Image.open(tmp_path/'combined.jpg') as im:
        assert im.size==(1080,1920)
        assert im.getpixel((5,1500))[2]>180
        assert max(im.getpixel((10,960)))<40
