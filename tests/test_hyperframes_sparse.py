import json
import shutil
import subprocess
from pathlib import Path

import pytest

from engine.hyperframes.schema import VisualBeat
from engine.hyperframes.sparse import motion_windows, render_sparse
from engine.probe import probe


def test_windows_are_frame_aligned_and_overlaps_merge():
    beats = [VisualBeat(id='a',start=2,end=3,title='a'),
             VisualBeat(id='b',start=3.1,end=4,title='b')]
    assert motion_windows(beats,300) == [(52,128)]


@pytest.mark.skipif(not shutil.which('ffmpeg'), reason='ffmpeg required')
def test_sparse_identity_preserves_real_video_audio_and_reuses_browser_render(tmp_path, monkeypatch):
    # This fixture has no ASS captions; use the system encoder even on libass-free hosts.
    monkeypatch.setattr('engine.talking_styles.talking_1.ass_burner_ffmpeg', lambda: shutil.which('ffmpeg'))
    source = tmp_path/'native.mp4'
    subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','testsrc2=s=64x96:r=30:d=42',
        '-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=42',
        '-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p','-c:a','aac',str(source)],check=True)
    project = tmp_path/'project'
    (project/'assets').mkdir(parents=True)
    (project/'assets/base.mp4').symlink_to(source)
    (project/'index.html').write_text('owned test composition')
    beats = [VisualBeat(id='a',start=10.1,end=12.2,title='first'),
             VisualBeat(id='b',start=30.1,end=32.2,title='second')]
    (project/'meta.json').write_text(json.dumps({'id':'ai-render-talking-2','duration':42,
        'visual_library':[b.model_dump() for b in beats]}))
    prepared = {}
    def build(path, video, shifted, **kwargs):
        path.mkdir(parents=True,exist_ok=True)
        prepared['source'] = video
        prepared['frames'] = round(kwargs['duration']*30)
        assert shifted[0].start < 1
    monkeypatch.setattr('engine.hyperframes.builder.build_project',build)
    calls=[]
    def browser(path, output):
        calls.append(path)
        shutil.copy2(prepared['source'],output)
    out = tmp_path/'result.mp4'
    assert render_sparse(project,out,browser) == out
    info = probe(out)
    video = next(s for s in info['streams'] if s['codec_type']=='video')
    assert int(video['nb_frames']) == 1260
    assert abs(float(info['format']['duration'])-42) < .12
    assert any(s['codec_type']=='audio' for s in info['streams'])
    assert prepared['frames'] < 180
    # Decode the entire real result, not just an HTTP response or file header.
    subprocess.run(['ffmpeg','-v','error','-i',str(out),'-f','null','-'],check=True)
    import numpy as np
    def frame(path, time):
        result=subprocess.run(['ffmpeg','-v','error','-ss',str(time),'-i',str(path),
            '-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-'],capture_output=True,check=True)
        return np.frombuffer(result.stdout,dtype=np.uint8).astype(float)
    for time in (.5,10.5,12.1,25,31,35,41):
        assert np.abs(frame(source,time)-frame(out,time)).mean() < 9
    def pcm(path):
        result=subprocess.run(['ffmpeg','-v','error','-i',str(path),'-vn','-ac','1','-ar','48000',
            '-f','f32le','-'],capture_output=True,check=True)
        return np.frombuffer(result.stdout,dtype=np.float32)
    original_audio, final_audio = pcm(source), pcm(out)
    for time in (.5,10.5,12.1,25,31,35,41):
        start=round(time*48000)
        assert np.corrcoef(original_audio[start:start+7200],final_audio[start:start+7200])[0,1] > .95
    render_sparse(project,tmp_path/'result2.mp4',browser)
    assert len(calls) == 1
