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
    assert service.cloud_detail('rendering', None) == 'رندر ابری شروع شد…'


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


def test_worker_rejection_carries_its_finding_and_scrubs_it():
    from app.render_cloud.runner import failure_reason
    from app.render_cloud.service import CloudRenderError, WorkerRejected
    class HyperFramesError(RuntimeError):
        pass
    text = failure_reason(HyperFramesError('HyperFrames check failed: contrast 2.6:1 @#beat-0-group-0-very-long-label-name-x in /work/space/p/index.html https://x.io/a?s=1'))
    assert '#beat-0-group-0-very-long-label-name-x' in text and 'https://' not in text and '/work/space' not in text
    assert isinstance(WorkerRejected('stopped', text), CloudRenderError)
    assert WorkerRejected('stopped', text).reason == text


def _silent_worker(created_ago, startup=420, cancel_after=None):
    import json
    import time

    class Ledger:
        def get(self, job, user):
            return {'state': 'provisioning', 'created': time.time() - created_ago, 'deadline': time.time() + 4000, 'cancel_requested': 0, 'pod_id': 'pod',
                    'details': json.dumps({'storage': {'mailbox_key': 'm', 'control_key': 'c', 'output_key': 'o'}})}

        def snapshot(self, *a, **k):
            pass

        def cancel(self, *a, **k):
            pass

    class Store:
        def read_json(self, key):
            return None                        # the worker never wrote its mailbox

        def write_json(self, *a, **k):
            pass
    polls = {'n': 0}

    def cancelled():
        polls['n'] += 1
        return cancel_after is not None and polls['n'] > cancel_after
    spec = SimpleNamespace(job_id='j', user_id='1')
    return lambda: service.await_result(spec, 'out.mp4', ledger=Ledger(), store=Store(), provider=None, sleep=lambda s: None, startup_seconds=startup, should_cancel=cancelled)


def test_a_worker_that_never_reports_is_given_up_on_after_the_startup_window(monkeypatch):
    monkeypatch.setattr(service, 'reconcile', lambda *a, **k: None)
    with pytest.raises(service.WorkerStartupTimeout):
        _silent_worker(created_ago=500, cancel_after=50)()


def test_a_worker_still_inside_its_startup_window_is_waited_for(monkeypatch):
    monkeypatch.setattr(service, 'reconcile', lambda *a, **k: None)
    with pytest.raises(InterruptedError):                      # only the person's cancel ends the wait
        _silent_worker(created_ago=60, cancel_after=5)()


def test_the_startup_timeout_is_a_cloud_render_error_and_a_setting():
    from app.render_cloud.settings import CloudSettings
    assert issubclass(service.WorkerStartupTimeout, service.CloudRenderError) and CloudSettings().startup_seconds == 900


def test_the_circuit_breaker_counts_only_recent_startup_timeouts(tmp_path):
    from app.render_cloud.ledger import Ledger
    led = Ledger(tmp_path / "l.sqlite")
    assert led.recent_failures('worker_startup_timeout', 3600) == 0
    import sqlite3, json, time
    with led.transaction() as db:
        for i, (state, code, ago) in enumerate([('failed', 'worker_startup_timeout', 100), ('failed', 'worker_startup_timeout', 500), ('failed', 'other', 100), ('failed', 'worker_startup_timeout', 99999), ('completed', None, 50)]):
            db.execute("INSERT INTO cloud_render_executions (id,user_id,fingerprint,state,backend,created,updated,deadline,reservation,details,finished) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                       (f'j{i}', '1', 'f', state, 'runpod_cpu', time.time() - ago, time.time() - ago, time.time() + 99, 0.07, json.dumps({'error_code': code}), time.time() - ago))
    assert led.recent_failures('worker_startup_timeout', 3600) == 2
    from app.render_cloud.settings import CloudSettings
    assert CloudSettings().startup_breaker_count == 2 and CloudSettings().startup_breaker_window_seconds == 2700


def test_a_worker_whose_progress_stops_is_given_up_on_and_one_that_keeps_moving_is_not(monkeypatch):
    import json
    import time as _time
    monkeypatch.setattr(service, 'reconcile', lambda *a, **k: None)
    clock = {'t': _time.time()}
    monkeypatch.setattr(service.time, 'time', lambda: clock['t'])

    def run(progress_for_call, stall=480):
        calls = {'n': 0}

        class Ledger:
            def get(self, job, user):
                return {'state': 'rendering', 'created': clock['t'] - 10, 'deadline': clock['t'] + 99999, 'cancel_requested': 0, 'pod_id': 'pod',
                        'details': json.dumps({'storage': {'mailbox_key': 'm', 'control_key': 'c', 'output_key': 'o'}})}

            def snapshot(self, *a, **k):
                pass

            def cancel(self, *a, **k):
                pass

        class Store:
            def read_json(self, key):
                calls['n'] += 1
                clock['t'] += 100                         # every poll is 100 s later
                return {'token': 't' * 40, 'sequence': calls['n'], 'history': ['rendering'], 'observation': {'state': 'rendering', 'progress': progress_for_call(calls['n'])}}

            def write_json(self, *a, **k):
                pass
        spec = SimpleNamespace(job_id='j', user_id='1')
        return service.await_result(spec, 'o.mp4', ledger=Ledger(), store=Store(), provider=None, sleep=lambda s: None, stall_seconds=stall, should_cancel=lambda: calls['n'] > 12)
    with pytest.raises(service.WorkerStalled):
        run(lambda n: 73.0)                               # stuck at 73 % for 500 s
    with pytest.raises(InterruptedError):
        run(lambda n: float(n))                           # moving every poll: only the cancel ends it
    assert issubclass(service.WorkerStalled, service.WorkerStartupTimeout)


def test_the_breaker_counts_stalled_workers_too(tmp_path):
    import json, time
    from app.render_cloud.ledger import Ledger
    led = Ledger(tmp_path / "l2.sqlite")
    with led.transaction() as db:
        for i, code in enumerate(['worker_stalled', 'worker_startup_timeout', 'something_else']):
            db.execute("INSERT INTO cloud_render_executions (id,user_id,fingerprint,state,backend,created,updated,deadline,reservation,details,finished) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                       (f'k{i}', '1', 'f', 'failed', 'runpod_cpu', time.time(), time.time(), time.time() + 99, 0.07, json.dumps({'error_code': code}), time.time() - 10))
    assert led.recent_failures(('worker_startup_timeout', 'worker_stalled'), 600) == 2 and led.recent_failures('worker_stalled', 600) == 1
