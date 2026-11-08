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


def test_await_result_reports_each_stage_once_and_the_percent_while_rendering(monkeypatch):
    """on_stage fires when the stage changes (not every poll); on_detail carries the stage line and then the pod's own percentage."""
    import json
    import time

    steps = [('provisioning', None), ('preparing', None), ('rendering', 10.0), ('rendering', 40.0), ('rendering', 70.0)]
    cursor = {'i': -1, 'polls': 0}

    class Ledger:
        def get(self, job, user):
            state = steps[max(cursor['i'], 0)][0]
            return {'state': state, 'deadline': time.time() + 999, 'cancel_requested': 0, 'pod_id': 'pod',
                    'details': json.dumps({'storage': {'mailbox_key': 'm', 'control_key': 'c', 'output_key': 'o'}})}

        def snapshot(self, *args, **kwargs):
            pass

        def cancel(self, *args, **kwargs):
            pass

    class Store:
        def read_json(self, key):
            cursor['i'] = min(cursor['i'] + 1, len(steps) - 1)
            state, progress = steps[cursor['i']]
            return {'token': 't' * 40, 'sequence': cursor['i'] + 1, 'history': [state],
                    'observation': {'state': state, 'progress': progress}}

        def write_json(self, *args, **kwargs):
            pass

    def cancelled():
        cursor['polls'] += 1
        return cursor['polls'] > len(steps)

    monkeypatch.setattr(service, 'reconcile', lambda *a, **k: None)
    stages, details, percents = [], [], []
    spec = SimpleNamespace(job_id='j', user_id='1')
    with pytest.raises(InterruptedError):
        service.await_result(spec, 'out.mp4', ledger=Ledger(), store=Store(), provider=None, on_progress=percents.append,
                             on_stage=stages.append, on_detail=details.append, should_cancel=cancelled, sleep=lambda s: None)
    assert stages == ['provisioning', 'preparing', 'rendering']
    assert percents == [10.0, 40.0, 70.0]
    assert details[0] == service.cloud_detail('provisioning') and details[1] == service.cloud_detail('preparing')
    assert any('10٪' in d for d in details) and any('70٪' in d for d in details)
