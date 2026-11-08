"""What the chat shows while a render runs on RunPod, and the output check that must not reject a clean 30 fps clip."""
from types import SimpleNamespace

import pytest

from app.render_cloud import service


def test_rendering_shows_exact_percent_and_time_left():
    text = service.cloud_detail('rendering', 40.0, 60.0)       # 40% in 60 s: 90 s left
    assert '40٪' in text and '1 دقیقه و 30 ثانیه' in text and 'باقی مانده' in text


def test_the_time_left_waits_for_enough_pace_to_mean_something():
    assert 'در حال محاسبه' in service.cloud_detail('rendering', 1.0, 30.0)
    assert 'در حال محاسبه' in service.cloud_detail('rendering', 50.0, 2.0)
    assert service.cloud_detail('rendering', None) == 'رندر روی RunPod شروع شد…'


@pytest.mark.parametrize('state', ['provisioning', 'preparing', 'downloading', 'uploading', 'delivering'])
def test_every_stage_has_a_persian_line(state):
    assert any('؀' <= ch <= 'ۿ' for ch in service.cloud_detail(state))


def _spec(duration=54.671, fps=30):
    return SimpleNamespace(width=1080, height=1920, fps=fps, duration_seconds=duration, audio_required=True)


def _media(fps='30', frames=1640, duration=54.666333):
    return {'width': 1080, 'height': 1920, 'fps': fps, 'frames': frames, 'duration': duration,
            'video_start': 0.0, 'audio_duration': 54.671, 'audio_start': 0.0}


def test_a_clean_30_fps_clip_reported_as_a_ratio_is_accepted(monkeypatch):
    monkeypatch.setattr(service, 'probe', lambda path: _media(fps='1640000000/54666333'))
    assert service.validate_output(_spec(), 'x.mp4')['frames'] == 1640


def test_a_real_frame_rate_difference_is_still_rejected(monkeypatch):
    monkeypatch.setattr(service, 'probe', lambda path: _media(fps='30000/1001'))
    with pytest.raises(ValueError, match='frame rate'):
        service.validate_output(_spec(), 'x.mp4')
