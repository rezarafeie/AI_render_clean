import hashlib
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest

from app.render_cloud.contracts import RenderSpec, relative_path
from app.render_cloud.engines import verify_inputs
from app.render_cloud.ledger import Conflict, Ledger
from app.render_cloud.policy import Benchmark, Flags, choose
from app.render_cloud.provider import ProviderError, RunPod, reconcile


def test_offline_guest_exposes_only_job_directory(tmp_path, monkeypatch):
    from app.render_cloud import offline_guest

    root = tmp_path / 'work'
    job = root / 'job'
    job.mkdir(parents=True)
    monkeypatch.setattr(offline_guest, 'WORK_ROOT', root)
    monkeypatch.setattr(offline_guest, 'available', lambda: True)
    command = offline_guest.qemu_command(job)
    assert command[command.index('-nic') + 1] == 'none'
    assert 'readonly=on' in command[command.index('-drive') + 1]
    assert command[command.index('-virtfs') + 1].startswith(f'local,path={job},')
    link = root / 'escape'
    link.symlink_to(tmp_path, target_is_directory=True)
    for invalid in (root, tmp_path, link):
        with pytest.raises(RuntimeError):
            offline_guest.qemu_command(invalid)


def spec():
    return RenderSpec(job_id='render-1', project_id='project', user_id='user',
                      engine='hyperframes_page', entrypoint='index.html',
                      assets=[{'path': 'index.html', 'sha256': hashlib.sha256(b'page').hexdigest(), 'size': 4}],
                      duration_seconds=30, fps=30, width=1080, height=1920,
                      timeout_seconds=900, workspace_bytes=1024**2)


@pytest.mark.parametrize('path', ['/etc/passwd', '../x', 'a/../x', 'a//x', 'a\\x', 'https://host/x', './a', 'a\x00b', 'a\nb'])
def test_reject_paths(path):
    with pytest.raises(ValueError):
        relative_path(path)


def reserve(ledger, job='job', user='u', **kw):
    return ledger.reserve(job, user, 'hash', 'runpod_cpu', estimate=.2, max_cost=1,
                          daily_budget=1, monthly_budget=2, max_workers=2,
                          max_gpu=0, timeout=900, **kw)


def test_lease_and_ownership(tmp_path):
    ledger = Ledger(tmp_path / 'ledger.db')
    reserve(ledger)
    ledger.claim('job', 'u', 'a')
    with pytest.raises(Conflict):
        ledger.claim('job', 'u', 'b')
    with pytest.raises(Conflict):
        reserve(ledger, user='other')
    assert not ledger.cancel('job', 'other')
    ledger.transition('job', 'u', 'a', 'queued', 'provisioning')
    ledger.bind_pod('job', 'u', 'a', 'pod')
    ledger.cancel('job', 'u')
    with pytest.raises(Conflict):
        ledger.transition('job', 'u', 'a', 'provisioning', 'preparing')
    assert ledger.resources_to_reap()[0]['pod_id'] == 'pod'


def test_atomic_concurrency_reservations(tmp_path):
    ledger = Ledger(tmp_path / 'ledger.db')
    def attempt(i):
        try:
            reserve(ledger, job=str(i))
            return True
        except Conflict:
            return False
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(attempt, range(8))) == 2


def test_idempotency_does_not_reserve_twice(tmp_path):
    ledger = Ledger(tmp_path / 'ledger.db')
    assert reserve(ledger) == reserve(ledger)
    with pytest.raises(Conflict):
        ledger.claim('job', 'wrong', 'a')
    ledger.claim('job', 'u', 'a')
    with pytest.raises(Conflict):
        ledger.transition('job', 'u', 'a', 'queued', 'completed')


def test_input_integrity(tmp_path):
    (tmp_path / 'index.html').write_bytes(b'page')
    verify_inputs(spec(), tmp_path)
    (tmp_path / 'index.html').write_bytes(b'evil')
    with pytest.raises(ValueError, match='hash'):
        verify_inputs(spec(), tmp_path)


def test_routing_is_off_and_requires_benchmarks():
    s = spec()
    assert choose(s, [])[0] == 'local'
    flags = Flags(enable_cloud_render=True, enable_runpod_cpu=True)
    assert choose(s, [], flags, admin=True)[0] == 'local'
    p = Benchmark(s.engine, 'runpod_cpu', 1080, 1920, 30, 60, 100, .2, True, IMAGE)
    assert choose(s, [p], flags, admin=True, image_digest=IMAGE)[0] == 'runpod_cpu'
    with pytest.raises(PermissionError):
        choose(s, [p], flags, override='runpod_cpu')
    with pytest.raises(ValueError):
        choose(s, [p], flags, admin=True, override='runpod_gpu', image_digest=IMAGE)


def test_profiles_require_exact_format_features_and_verified_gpu():
    from dataclasses import replace
    s = spec()
    flags = Flags(enable_cloud_render=True, enable_runpod_cpu=True, enable_runpod_gpu=True)
    p = Benchmark(s.engine,'runpod_cpu',1080,1920,30,60,100,.2,True,IMAGE)
    for mismatch in (replace(p,export_format='webm'),replace(p,features=('transparent',)),
                     replace(p,backend='runpod_gpu')):
        assert choose(s,[mismatch],flags,admin=True,image_digest=IMAGE)[0]=='local'
    gpu = replace(p,backend='runpod_gpu',gpu_acceleration_verified=True)
    assert choose(s,[gpu],flags,admin=True,image_digest=IMAGE)[0]=='runpod_gpu'
    assert choose(s.model_copy(update={'gpu_required':True}),[p],flags,admin=True,image_digest=IMAGE)[0]=='local'
    with pytest.raises(ValueError):
        replace(p,hourly_usd=float('nan'))
    with pytest.raises(ValueError):
        replace(p,image_digest='mutable:latest')


def test_provider_redacts_and_never_retries_create():
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(503, json={'error': 'secret'})
    provider = RunPod('private', transport=httpx.MockTransport(handler))
    with pytest.raises(ProviderError, match='runpod_http_503') as error:
        provider.create(name='test', image='image@sha256:' + 'a' * 64, compute='CPU', hardware_ids=['cpu'], env={})
    assert 'secret' not in str(error.value) and len(calls) == 1
    provider.close()


def test_reconciler_keeps_failed_cleanup_pending(tmp_path):
    ledger = Ledger(tmp_path / 'ledger.db')
    reserve(ledger)
    ledger.claim('job', 'u', 'a')
    ledger.transition('job', 'u', 'a', 'queued', 'provisioning')
    ledger.bind_pod('job', 'u', 'a', 'owned-pod')
    ledger.cancel('job', 'u')
    bad = RunPod('key', transport=httpx.MockTransport(lambda r: httpx.Response(503)))
    assert reconcile(bad, ledger) == [{'job_id': 'job', 'deleted': False}]
    assert ledger.resources_to_reap()
    good = RunPod('key', transport=httpx.MockTransport(lambda r: httpx.Response(404)))
    assert reconcile(good, ledger) == [{'job_id': 'job', 'deleted': True}]
    assert not ledger.resources_to_reap()
    bad.close(); good.close()


def test_download_stream_integrity_and_size(tmp_path, monkeypatch):
    from app.render_cloud import transfer
    monkeypatch.setattr(transfer, 'validate_url', lambda *a: None)
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b'page')))
    transfer.download(spec(), {'index.html': 'https://storage.test/signed'}, tmp_path, {'storage.test'}, client=client)
    assert (tmp_path / 'index.html').read_bytes() == b'page'
    client.close()


def test_download_rejects_corruption(tmp_path, monkeypatch):
    from app.render_cloud import transfer
    monkeypatch.setattr(transfer, 'validate_url', lambda *a: None)
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b'oversized')))
    with pytest.raises(ValueError):
        transfer.download(spec(), {'index.html': 'https://storage.test/signed'}, tmp_path, {'storage.test'}, client=client)
    assert not list(tmp_path.iterdir())
    client.close()


@pytest.mark.parametrize('url', ['http://storage.test/x', 'https://evil.test/x', 'https://u:p@storage.test/x', 'https://storage.test:999/x'])
def test_transfer_url_allowlist(url):
    from app.render_cloud.transfer import validate_url
    with pytest.raises(ValueError):
        validate_url(url, {'storage.test'})


def test_transfer_rejects_metadata_network():
    from app.render_cloud.transfer import validate_url
    def resolve(*a, **kw):
        return [(2, 1, 6, '', ('169.254.169.254', 443))]
    with pytest.raises(ValueError):
        validate_url('https://storage.test/x', {'storage.test'}, resolve=resolve)


def test_engine_reuses_existing_entrypoint(tmp_path, monkeypatch):
    from app.render_cloud.engines import execute
    from engine.hyperframes import standalone
    (tmp_path / 'index.html').write_bytes(b'page')
    seen = []
    def render(project, output, **kw):
        seen.append((project, kw['frames']))
        output.write_bytes(b'encoded')
    monkeypatch.setattr(standalone, 'render', render)
    assert execute(spec(), tmp_path).read_bytes() == b'encoded'
    assert seen == [(tmp_path, 900)]


def test_storage_prefix_is_user_scoped():
    from app.render_cloud.storage import ObjectStore
    store = ObjectStore(None, 'private-bucket')
    production = ObjectStore(None, 'private-bucket', namespace='render/production/v1/')
    assert store.prefix('a') != store.prefix('b')
    assert 'alice@example.com' not in store.prefix('alice@example.com')
    assert production.prefix('a').startswith('render/production/v1/')
    assert production.key('a', 'digest') != store.key('a', 'digest')


IMAGE = 'registry/worker@sha256:' + 'a' * 64


def provision_fixture(ledger, provider, token_box, **kwargs):
    from app.render_cloud.coordinator import Limits, provision
    def bootstrap(token):
        token_box.append(token)
        return 'https://storage.test/short-lived-signature'
    return provision(spec(), ledger=ledger, provider=provider,
                     flags=Flags(enable_cloud_render=True, enable_runpod_cpu=True), admin=True,
                     backend='runpod_cpu', estimate=.2, limits=Limits(), image=IMAGE,
                     hardware_ids=['cpu'], deployment='test', bootstrap=bootstrap, **kwargs)


def test_coordinator_persists_intent_before_post_and_never_duplicates(tmp_path):
    ledger = Ledger(tmp_path / 'ledger.db')
    posts, tokens = [], []
    def handler(request):
        row = ledger.get('render-1', 'user')
        assert row['create_attempted'] == 1 and row['cleanup_pending'] == 1
        posts.append(request)
        return httpx.Response(200, json={'id': 'pod1'})
    provider = RunPod('key', transport=httpx.MockTransport(handler))
    assert provision_fixture(ledger, provider, tokens)['pod_id'] == 'pod1'
    assert provision_fixture(ledger, provider, tokens)['pod_id'] == 'pod1'
    assert len(posts) == len(tokens) == 1
    row = ledger.get('render-1', 'user')
    assert tokens[0] not in str(row) and row['pod_name'].startswith('editorgpt-test-')
    provider.close()


def test_uncertain_create_recovered_by_exact_random_name_and_image(tmp_path):
    ledger = Ledger(tmp_path / 'ledger.db')
    calls, tokens = [], []
    def handler(request):
        calls.append(request.method)
        if request.method == 'POST':
            raise httpx.ReadTimeout('private-url', request=request)
        if request.method == 'GET':
            row = ledger.get('render-1', 'user')
            return httpx.Response(200, json=[{'id': 'recover', 'name': row['pod_name'], 'imageName': IMAGE},
                                             {'id': 'unrelated', 'name': 'editorgpt-other', 'imageName': IMAGE}])
        assert request.url.path.endswith('/recover')
        return httpx.Response(204)
    provider = RunPod('key', transport=httpx.MockTransport(handler))
    with pytest.raises(ProviderError, match='reconciliation_required'):
        provision_fixture(ledger, provider, tokens)
    assert provision_fixture(ledger, provider, tokens)['state'] == 'failed'
    assert reconcile(provider, ledger) == [{'job_id': 'render-1', 'deleted': True}]
    assert calls == ['POST', 'GET', 'DELETE']
    assert not ledger.get('render-1', 'user')['cleanup_pending']
    provider.close()


def test_uncertain_create_not_visible_keeps_reservation(tmp_path):
    ledger = Ledger(tmp_path / 'ledger.db')
    provider = RunPod('key', transport=httpx.MockTransport(lambda r: httpx.Response(503) if r.method == 'POST' else httpx.Response(200, json=[])))
    with pytest.raises(ProviderError):
        provision_fixture(ledger, provider, [])
    assert reconcile(provider, ledger)[0]['reason'] == 'create_unresolved'
    assert ledger.get('render-1', 'user')['cleanup_pending'] == 1
    provider.close()


def test_scoped_worker_events_replay_cancellation_and_completion(tmp_path):
    ledger = Ledger(tmp_path / 'ledger.db')
    tokens = []
    provider = RunPod('key', transport=httpx.MockTransport(lambda r: httpx.Response(200, json={'id': 'pod1'})))
    provision_fixture(ledger, provider, tokens)
    token = tokens[0]
    with pytest.raises(Conflict):
        ledger.record_event('render-1', 'other', token, 1, {'state': 'preparing'})
    assert ledger.record_event('render-1', 'user', token, 1, {'state': 'preparing'})
    assert not ledger.record_event('render-1', 'user', token, 1, {'state': 'preparing'})
    with pytest.raises(Conflict):
        ledger.record_event('render-1', 'user', token, 3, {'state': 'rendering'})
    with pytest.raises(Conflict):
        ledger.record_event('render-1', 'user', token, 2, {'state': 'completed'})
    ledger.cancel('render-1', 'user')
    with pytest.raises(Conflict):
        ledger.record_event('render-1', 'user', token, 2, {'state': 'downloading'})
    provider.close()


def test_emergency_and_expiry_reap_only_ledger_pods(tmp_path):
    ledger = Ledger(tmp_path / 'ledger.db')
    deleted = []
    def handler(request):
        if request.method == 'POST':
            return httpx.Response(200, json={'id': 'pod1'})
        if request.method == 'GET':
            return httpx.Response(200, json=[])
        deleted.append(request.url.path)
        return httpx.Response(204)
    provider = RunPod('key', transport=httpx.MockTransport(handler))
    provision_fixture(ledger, provider, [])
    reconcile(provider, ledger, emergency=True)
    assert ledger.get('render-1', 'user')['state'] == 'cancelled'
    assert deleted == ['/v1/pods/pod1']
    provider.close()


def test_supervisor_never_passes_credentials():
    from app.render_cloud.supervisor import child_environment
    env = child_environment({'PATH': '/bin', 'RUNPOD_API_KEY': 'secret', 'AWS_SECRET_ACCESS_KEY': 'secret',
                             'EDITOR_RENDER_BOOTSTRAP_URL': 'signed', 'DATABASE_URL': 'secret',
                             'LMAPI_API_KEY': 'secret'})
    assert env == {'PATH': '/bin', 'PYTHONUNBUFFERED': '1', 'EDITOR_RENDER_CHILD': '1'}


def test_proc_descendants_handle_spaces_and_nested_sessions(tmp_path):
    from app.render_cloud.supervisor import descendants
    for pid, parent in [(100, 1), (101, 100), (102, 101), (103, 1)]:
        directory = tmp_path / str(pid)
        directory.mkdir()
        (directory / 'stat').write_text(f'{pid} (name with ) space) S {parent} 0 0 0')
    assert set(descendants(100, tmp_path)) == {101, 102}


def test_ledger_reopens_with_additive_migration(tmp_path):
    path = tmp_path / 'ledger.db'
    ledger = Ledger(path)
    reserve(ledger)
    reopened = Ledger(path)
    assert reopened.get('job', 'u')['state'] == 'queued'


def test_worker_token_expires_and_cannot_finalize_output(tmp_path, monkeypatch):
    from app.render_cloud import ledger as module
    ledger = Ledger(tmp_path / 'ledger.db')
    provider = RunPod('key', transport=httpx.MockTransport(lambda r: httpx.Response(200, json={'id': 'pod1'})))
    tokens = []
    provision_fixture(ledger, provider, tokens)
    deadline = ledger.get('render-1', 'user')['deadline']
    monkeypatch.setattr(module.time, 'time', lambda: deadline + 1)
    with pytest.raises(Conflict, match='expired'):
        ledger.record_event('render-1', 'user', tokens[0], 1, {'state': 'preparing'})
    provider.close()


def test_project_freezer_preserves_and_rejects_symlinks(tmp_path):
    from app.render_cloud.prepare import freeze
    (tmp_path / 'index.html').write_bytes(b'page')
    fields = spec().model_dump(exclude={'assets'})
    frozen = freeze(tmp_path, ['index.html'], **fields)
    assert frozen.assets == spec().assets
    (tmp_path / 'linked.html').symlink_to(tmp_path / 'index.html')
    with pytest.raises(ValueError, match='Symlink'):
        freeze(tmp_path, ['linked.html'], **{**fields, 'entrypoint': 'linked.html'})
    assert (tmp_path / 'index.html').read_bytes() == b'page'


def test_supervisor_stops_real_process_on_cancel(tmp_path, monkeypatch):
    import subprocess
    import sys
    from app.render_cloud import supervisor
    original = subprocess.Popen
    processes = []
    def start(command, **kw):
        process = original([sys.executable, '-c', 'import time; time.sleep(30)'], **kw)
        processes.append(process)
        return process
    monkeypatch.setattr(supervisor.subprocess, 'Popen', start)
    with pytest.raises(InterruptedError):
        supervisor.run(spec(), tmp_path, should_cancel=lambda: True)
    assert processes[0].poll() is not None
    assert not (tmp_path / '.worker-manifest.json').exists()


def test_supervisor_stops_real_process_on_timeout(tmp_path, monkeypatch):
    import subprocess
    import sys
    from app.render_cloud import supervisor
    original = subprocess.Popen
    processes = []
    def start(command, **kw):
        process = original([sys.executable, '-c', 'import time; time.sleep(30)'], **kw)
        processes.append(process)
        return process
    monkeypatch.setattr(supervisor.subprocess, 'Popen', start)
    with pytest.raises(TimeoutError):
        supervisor.run(spec().model_copy(update={'timeout_seconds': 1}), tmp_path)
    assert processes[0].poll() is not None


def test_real_ffmpeg_metadata_parity_smoke(tmp_path):
    import shutil
    import subprocess
    from app.render_cloud.parity import compare, probe
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        pytest.skip('FFmpeg/FFprobe not installed')
    output = tmp_path / 'smoke.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=blue:s=160x90:r=30:d=1',
                    '-f', 'lavfi', '-i', 'sine=frequency=440:duration=1', '-c:v', 'libx264',
                    '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', str(output)], check=True, timeout=30)
    measured = probe(output)
    assert measured['frames'] == 30 and measured['fps'] == '30'
    assert compare(measured, measured)['metadata_parity']
    assert not compare(measured, {**measured, 'frames': 29})['metadata_parity']


@pytest.mark.parametrize('early_state', ['preparing', 'failed'])
def test_fast_worker_event_before_pod_binding(tmp_path, early_state):
    ledger = Ledger(tmp_path / 'ledger.db')
    tokens = []
    def handler(request):
        assert ledger.record_event('render-1', 'user', tokens[0], 1, {'state': early_state})
        return httpx.Response(200, json={'id': 'fast-pod'})
    provider = RunPod('key', transport=httpx.MockTransport(handler))
    result = provision_fixture(ledger, provider, tokens)
    assert result['state'] == early_state
    assert ledger.get('render-1', 'user')['pod_id'] == 'fast-pod'
    provider.close()


def test_mailbox_snapshot_accepts_missed_progress_not_rollback(tmp_path):
    ledger = Ledger(tmp_path/'ledger.db')
    tokens = []
    provider = RunPod('key', transport=httpx.MockTransport(lambda r: httpx.Response(200, json={'id':'pod1'})))
    provision_fixture(ledger, provider, tokens)
    assert ledger.snapshot('render-1','user',tokens[0],12,['preparing','downloading','rendering'],{'state':'rendering','progress':40})
    assert not ledger.snapshot('render-1','user',tokens[0],12,['preparing','downloading','rendering'],{'state':'rendering','progress':40})
    with pytest.raises(Conflict):
        ledger.snapshot('render-1','user',tokens[0],13,['preparing'],{'state':'preparing'})
    with pytest.raises(Conflict):
        ledger.snapshot('render-1','user','x'*32,13,['preparing','downloading','rendering'],{'state':'rendering'})
    provider.close()


def test_network_runner_uses_isolated_engine_and_uploads_not_completes(tmp_path):
    import time
    from app.render_cloud.mailbox import Envelope, Reporter
    from app.render_cloud.runner import run
    reports = []
    envelope = Envelope(spec=spec(), downloads={'index.html':'signed'}, output_put='output', mailbox_put='status',
                        control_get='control', token='a'*32, expires_at=time.time()+60)
    def factory(env, hosts):
        return Reporter(env, hosts, get=lambda *a, **kw: {'cancel':False}, put=lambda url,value,hosts: reports.append(value))
    def download(s, urls, workspace, hosts, **kw):
        (workspace/'index.html').write_bytes(b'page')
    def render(s, workspace, **kw):
        assert kw['isolate_network'] is True
        output = workspace/s.output
        output.write_bytes(b'encoded')
        return output
    uploads = []
    run(envelope, set(), report_factory=factory, download=download, render=render,
        upload=lambda path,*a,**kw: uploads.append(path.read_bytes()))
    assert uploads == [b'encoded']
    assert [r['observation']['state'] for r in reports] == ['preparing','downloading','rendering','uploading','uploading']
    assert reports[-1]['uploaded'] and reports[-1]['sha256'] == hashlib.sha256(b'encoded').hexdigest()
    assert all(r['observation']['state'] != 'completed' for r in reports)


def test_cloud_disabled_does_not_import_provider_or_touch_project(tmp_path, monkeypatch):
    from app.render_cloud.service import render_prepared
    from app.render_cloud.settings import CloudSettings
    assert not render_prepared(tmp_path, tmp_path/'out.mp4', user='user', config=CloudSettings())
    assert not list(tmp_path.iterdir())


def test_runtime_environment_is_whitelisted():
    with pytest.raises(ValueError):
        spec().model_validate({**spec().model_dump(), 'runtime_env': {'AWS_SECRET_ACCESS_KEY':'secret'}})


def test_signed_mailbox_end_to_end_with_mocked_provider_and_real_media_validation(tmp_path, monkeypatch):
    """No live cloud/AI. Real hashing, ledger, worker protocol, FFmpeg/FFprobe and cache recovery."""
    import io
    import json
    import shutil
    import subprocess
    from urllib.parse import quote, unquote, urlsplit
    from app.render_cloud import service
    from app.render_cloud.mailbox import Envelope, Reporter
    from app.render_cloud.runner import run
    from app.render_cloud.settings import CloudSettings
    from app.render_cloud.storage import ObjectStore
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        pytest.skip('FFmpeg/FFprobe unavailable')
    fixture = tmp_path/'fixture.mp4'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=blue:s=160x90:r=30:d=1',
                    '-c:v','libx264','-pix_fmt','yuv420p',str(fixture)], check=True, timeout=30)
    media = fixture.read_bytes()
    objects = {}
    class Missing(Exception):
        response = {'Error':{'Code':'NoSuchKey'}}
    class SDK:
        def head_object(self, **kw):
            if kw['Key'] not in objects: raise Missing()
            data, metadata = objects[kw['Key']]
            return {'ContentLength':len(data),'Metadata':metadata}
        def upload_fileobj(self, stream, bucket, key, ExtraArgs):
            objects[key] = (stream.read(), ExtraArgs['Metadata'])
        def generate_presigned_url(self, operation, Params, ExpiresIn):
            return 'https://storage.test/' + quote(Params['Key'])
        def put_object(self, **kw):
            objects[kw['Key']] = (kw['Body'], {})
        def get_object(self, **kw):
            if kw['Key'] not in objects: raise Missing()
            value = objects[kw['Key']][0]
            return {'Body':io.BytesIO(value),'ContentLength':len(value)}
    store = ObjectStore(SDK(), 'private-bucket')
    def key(url): return unquote(urlsplit(url).path[1:])
    class Provider:
        creates, deletes = 0, []
        def create(self, **kw):
            self.creates += 1
            envelope = Envelope.model_validate(store.read_json(key(kw['env']['EDITOR_RENDER_BOOTSTRAP_URL']), limit=1024**2))
            def factory(env, hosts):
                return Reporter(env, hosts, get=lambda url,*a,**k: store.read_json(key(url)),
                                put=lambda url,value,*a: store.write_json(key(url), value))
            def download(s, urls, workspace, hosts, **kw):
                for asset in s.assets:
                    target = workspace/asset.path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(objects[key(urls[asset.path])][0])
            def render(s, workspace, **kw):
                assert kw['isolate_network']
                output = workspace/s.output
                output.write_bytes(media)
                return output
            run(envelope, {'storage.test'}, report_factory=factory, download=download, render=render,
                upload=lambda path,url,*a,**kw: objects.__setitem__(key(url),(path.read_bytes(),{})))
            return {'id':'pod1','costPerHr':'.1','memoryInGb':8,'vcpuCount':8}
        def list(self): return []
        def delete(self, pod_id): self.deletes.append(pod_id)
        def close(self): pass
    provider = Provider()
    monkeypatch.setattr(service, 'object_store', lambda cfg: store)
    monkeypatch.setattr(service.RunPod, 'from_settings', lambda config: provider)
    project = tmp_path/'project'
    project.mkdir()
    (project/'index.html').write_bytes(b'page')
    profiles = tmp_path/'benchmarks.json'
    profiles.write_text(json.dumps([{'engine':'hyperframes_page','backend':'runpod_cpu','width':160,'height':90,
                                    'fps':30,'max_duration':30,'end_to_end_seconds':10,'estimated_usd':.01,
                                    'parity_verified':True,'image_digest':IMAGE,'hourly_usd':.1,'hardware_id':'cpu','min_memory_gb':8}]))
    config = CloudSettings(enable_cloud_render=True, enable_runpod_cpu=True, sandbox_verified=True,
                           admin_user_ids='user', image=IMAGE, cpu_ids='cpu', max_wall_seconds=60,
                           ledger=tmp_path/'ledger.db', benchmarks=profiles, runpod_api_key='fake-key')
    output = tmp_path/'delivered.mp4'
    args = dict(user='user', project_id='project', engine='hyperframes_page',duration=1,width=160,height=90,config=config)
    assert not service.render_prepared(project, output, **args)
    assert provider.creates == 0
    args['config'] = config.model_copy(update={'network_namespace_verified': True})
    assert service.render_prepared(project, output, **args)
    assert output.read_bytes() == media
    # Simulate a lost local output after restart: recover the verified object,
    # never create another billable Pod or regenerate any AI asset.
    output.unlink()
    assert service.render_prepared(project, output, **args)
    assert output.read_bytes() == media and provider.creates == 1 and provider.deletes == ['pod1']


def test_real_provider_image_field_is_used_for_orphan_recovery(tmp_path):
    ledger = Ledger(tmp_path/'ledger.db')
    def handler(request):
        if request.method=='POST': raise httpx.ReadTimeout('lost',request=request)
        if request.method=='GET':
            row = ledger.get('render-1','user')
            return httpx.Response(200,json=[{'id':'pod1','name':row['pod_name'],'image':IMAGE}])
        return httpx.Response(204)
    provider = RunPod('key',transport=httpx.MockTransport(handler))
    with pytest.raises(ProviderError): provision_fixture(ledger,provider,[])
    assert reconcile(provider,ledger)[0]['deleted']
    provider.close()


def test_provider_quote_exceeds_ceiling_is_tracked_for_cleanup(tmp_path):
    ledger = Ledger(tmp_path/'ledger.db')
    provider = RunPod('key',transport=httpx.MockTransport(lambda r:httpx.Response(200,json={'id':'pod1','costPerHr':'99'})))
    with pytest.raises(ProviderError,match='quote'):
        provision_fixture(ledger,provider,[],max_hourly_usd=.1)
    row = ledger.get('render-1','user')
    assert row['state']=='failed' and row['cleanup_pending']==1 and row['pod_id']=='pod1'
    provider.close()


def test_actual_billing_buckets_are_not_double_counted(tmp_path):
    from app.render_cloud.provider import sync_billing
    ledger = Ledger(tmp_path/'ledger.db')
    reserve(ledger)
    ledger.claim('job','u','a')
    ledger.transition('job','u','a','queued','provisioning')
    ledger.bind_pod('job','u','a','pod1')
    provider = RunPod('key',transport=httpx.MockTransport(lambda r:httpx.Response(200,json=[
        {'podId':'pod1','amount':.3,'time':'2026-11-07T00:00:00Z'},
        {'podId':'not-owned','amount':100,'time':'2026-11-07T00:00:00Z'}])))
    assert sync_billing(provider,ledger,since='2026-11-07T00:00:00Z')==1
    sync_billing(provider,ledger,since='2026-11-07T00:00:00Z')
    assert ledger.summaries()[0]['provider_charge_usd']==.3
    provider.close()


def test_talking_cinematic_adapter_restores_identity_sets_without_replanning(tmp_path,monkeypatch):
    import dataclasses,json
    from app.render_cloud.engines import execute
    from app.render_cloud.prepare import freeze
    from engine.talking_styles import talking_2,talking_3
    plan=talking_2.ReelPlan(shots=[talking_2.Shot(0,1)],duration=1)
    (tmp_path/'video.mp4').write_bytes(b'fixture')
    (tmp_path/'talking.json').write_text(json.dumps({'style':'talking_3','video':'video.mp4',
        'plan':dataclasses.asdict(plan),'options':{},'titles':[{'text':'سلام'}],
        'full_pictures':[0],'card_pictures':[]}))
    fields=spec().model_dump(exclude={'assets'})
    fields.update(engine='talking_3',entrypoint='talking.json',duration_seconds=1)
    s=freeze(tmp_path,['video.mp4','talking.json'],**fields)
    def render(video,restored,out,**kwargs):
        assert video==tmp_path/'video.mp4'
        assert restored.full_pictures=={id(restored.shots[0])}
        assert restored.card_pictures==set() and restored.titles==[{'text':'سلام'}]
        assert restored.shots[0].src_out==1
        out.write_bytes(b'rendered')
    monkeypatch.setattr(talking_3,'render',render)
    assert execute(s,tmp_path).read_bytes()==b'rendered'


def test_dedicated_cgroup_metrics_do_not_invent_gpu_usage(tmp_path):
    from app.render_cloud.resources import Meter
    (tmp_path/'cpu.stat').write_text('usage_usec 1000000\n')
    times=iter([0,2])
    meter=Meter(tmp_path,clock=lambda:next(times))
    (tmp_path/'cpu.stat').write_text('usage_usec 4000000\n')
    (tmp_path/'memory.peak').write_text('1024')
    measured=meter.finish()
    assert measured['cpu_seconds']==3 and measured['cpu_core_percent']==150
    assert measured['cgroup_peak_memory_bytes']==1024
    assert measured['gpu_utilization_percent'] is None


def test_object_retry_backoff_is_bounded_cancellable_and_never_retries_validation():
    from app.render_cloud.transfer import retry_transfer,TransientTransferError
    attempts,delays=[],[]
    def transient():
        attempts.append(1)
        raise TransientTransferError('temporary')
    with pytest.raises(RuntimeError,match='bounded retries'):
        retry_transfer(transient,sleep=delays.append)
    assert len(attempts)==3 and sum(delays)==pytest.approx(3)
    with pytest.raises(InterruptedError):
        retry_transfer(transient,should_cancel=lambda:True,sleep=delays.append)
    assert len(attempts)==3
    def invalid():
        raise ValueError('integrity failed')
    with pytest.raises(ValueError,match='integrity'):
        retry_transfer(invalid,sleep=lambda _:pytest.fail('validation must not retry'))


def test_reaper_reads_fresh_heartbeat_before_cleanup_and_frees_uploaded_compute(tmp_path):
    import json,time
    from app.render_cloud.reaper import refresh
    ledger=Ledger(tmp_path/'ledger.db')
    tokens,deletes=[],[]
    def handler(request):
        if request.method=='POST': return httpx.Response(200,json={'id':'pod1'})
        if request.method=='GET': return httpx.Response(200,json=[])
        deletes.append(request.url.path)
        return httpx.Response(204)
    provider=RunPod('key',transport=httpx.MockTransport(handler))
    provision_fixture(ledger,provider,tokens)
    with ledger.transaction() as db:
        db.execute('UPDATE cloud_render_executions SET heartbeat=?,details=? WHERE id=?',
                   (time.time()-500,json.dumps({'storage':{'mailbox_key':'status'}}),'render-1'))
    class Store:
        report={'token':tokens[0],'sequence':1,'history':['preparing','downloading','rendering'],
                'observation':{'state':'rendering','progress':30}}
        def read_json(self,key): return self.report
    store=Store()
    assert refresh(ledger,store,provider,recover=False)==[]
    assert reconcile(provider,ledger)==[] and deletes==[]
    assert ledger.get('render-1','user')['state']=='rendering'
    store.report={'token':tokens[0],'sequence':2,'history':['preparing','downloading','rendering','uploading'],
                  'observation':{'state':'uploading','progress':100},'uploaded':True,
                  'sha256':'a'*64,'size':100}
    assert refresh(ledger,store,provider,recover=False)==[]
    assert json.loads(ledger.get('render-1','user')['details'])['compute_finished']
    assert reconcile(provider,ledger)==[{'job_id':'render-1','deleted':True}]
    assert len(deletes)==1
    provider.close()


@pytest.mark.parametrize('receipt',[
    {'uploaded':True,'observation':{'state':'rendering'},'sha256':'a'*64,'size':1},
    {'uploaded':True,'observation':{'state':'uploading'},'size':1},
])
def test_incomplete_upload_snapshot_cannot_release_compute(receipt):
    from app.render_cloud.mailbox import Snapshot
    with pytest.raises(ValueError):
        Snapshot.model_validate({'token':'x'*32,'sequence':1,'history':['preparing'],**receipt})


def test_readonly_preflight_redacts_secrets_and_does_not_create_state(tmp_path,monkeypatch):
    import json
    from app.render_cloud.doctor import inspect
    from app.render_cloud.settings import CloudSettings
    config=CloudSettings(ledger=tmp_path/'absent'/'ledger.sqlite',benchmarks=tmp_path/'profiles.json',
                         runpod_api_key='never-show-this',s3_endpoint='https://private-endpoint.example')
    report=inspect(config)
    assert report['checks']['provider_key'] and not report['local_preflight_passed']
    assert report['live_provider_verified'] is False
    assert not (tmp_path/'absent').exists()
    assert 'never-show-this' not in json.dumps(report) and 'private-endpoint' not in json.dumps(report)
    config.benchmarks.write_text('{"not":"an approved profile list"}')
    assert not inspect(config)['checks']['valid_profile_registry']


def test_canary_preflight_does_not_require_results_from_the_canary(tmp_path, monkeypatch):
    from app.render_cloud import doctor
    from app.render_cloud.settings import CloudSettings
    monkeypatch.setattr(doctor.importlib.util, 'find_spec', lambda name: object())
    config = CloudSettings(ledger=tmp_path/'ledger.sqlite', benchmarks=tmp_path/'absent.json',
                           runpod_api_key='test', s3_bucket='private', storage_hosts='store.example',
                           image='registry.example/worker@sha256:'+'a'*64, admin_user_ids='operator',
                           cpu_ids='cpu')
    canary = doctor.inspect(config, phase='canary')
    assert canary['local_preflight_passed'] and not canary['live_provider_verified']
    assert not canary['checks']['worker_sandbox_certified']
    admission = doctor.inspect(config)
    assert not admission['local_preflight_passed']
    assert 'eligible_measured_profile' in admission['missing']
    assert not config.ledger.exists()


def test_containment_probe_uses_worker_namespace_command_and_no_provider_key(monkeypatch):
    from types import SimpleNamespace
    from app.render_cloud import containment_probe as probe
    monkeypatch.setattr(probe.sys, 'platform', 'linux')
    monkeypatch.setattr(probe.os, 'geteuid', lambda: 10001)
    monkeypatch.setattr(probe.os, 'readlink', lambda path: 'net:[123]')
    monkeypatch.setenv('RUNPOD_API_KEY', 'private')
    def run(command, **kwargs):
        assert command[:6] == ['unshare', '--user', '--map-root-user', '--net', '--', probe.sys.executable]
        assert command[-2:] == ['--child', 'net:[123]']
        assert 'RUNPOD_API_KEY' not in kwargs['env']
        assert kwargs['timeout'] == 10
        return SimpleNamespace(returncode=1)
    monkeypatch.setattr(probe.subprocess, 'run', run)
    assert not probe.inspect()


def test_browser_and_talking_styles_require_verified_namespace(tmp_path):
    from app.render_cloud.settings import CloudSettings
    config = CloudSettings(sandbox_verified=True, ledger=tmp_path/'ledger', benchmarks=tmp_path/'profiles')
    assert config.isolates('mlt')
    split_images = config.model_copy(update={'image': 'mlt-image', 'browser_image': 'browser-image'})
    assert split_images.image_for('mlt') == 'mlt-image'
    assert split_images.image_for('remotion') == 'browser-image'
    assert split_images.model_copy(update={'browser_image': ''}).image_for('remotion') == 'mlt-image'
    for engine in ('hyperframes_page', 'hyperframes_project', 'hyperframes_product', 'remotion',
                   'talking_1', 'talking_2', 'talking_3', 'talking_4'):
        assert not config.isolates(engine)
        assert config.model_copy(update={'network_namespace_verified': True}).isolates(engine)
        assert config.model_copy(update={'browser_guest_verified': True}).isolates(engine)
        assert config.model_copy(update={'native_browser_verified': True}).isolates(engine)
        assert not config.model_copy(update={'sandbox_verified': False, 'browser_guest_verified': True}).isolates(engine)
        assert not config.model_copy(update={'sandbox_verified': False, 'native_browser_verified': True}).isolates(engine)


def test_benchmark_keeps_webm_format(tmp_path, monkeypatch):
    import json
    from app.render_cloud import benchmark
    manifest = tmp_path/'manifest.json'
    manifest.write_text(spec().model_copy(update={'output':'sample.webm','export_format':'webm'}).model_dump_json())
    suite = tmp_path/'suite.json'
    suite.write_text(json.dumps({'talking_30s':{'manifest':str(manifest),'workspace':str(tmp_path)}}))
    report = tmp_path/'report.json'
    monkeypatch.setattr(benchmark, 'verify_inputs', lambda *_: None)
    source = tmp_path/spec().assets[0].path
    source.parent.mkdir(parents=True,exist_ok=True)
    source.write_bytes(b'fixture')
    def measure(prepared, workspace, output, *args, **kwargs):
        assert prepared.export_format == 'webm'
        assert prepared.output.endswith('.webm') and output.suffix == '.webm'
        return {}
    monkeypatch.setattr(benchmark, 'measure', measure)
    monkeypatch.setattr('sys.argv',['benchmark',str(suite),'--report',str(report)])
    assert benchmark.main() == 1  # Other representative fixtures were not supplied.
    assert json.loads(report.read_text())['results'][0]['status'] == 'measured'


def test_reaper_cli_orders_observation_cleanup_delivery_and_signals_recovery_failure(tmp_path,monkeypatch,capsys):
    from app.render_cloud import reaper,settings
    config=settings.CloudSettings(ledger=tmp_path/'ledger.sqlite',s3_bucket='private',runpod_api_key='do-not-log')
    Ledger(config.ledger)
    monkeypatch.setenv('ENABLE_CLOUD_REAPER','1')
    monkeypatch.setattr('sys.argv',['reaper'])
    monkeypatch.setattr(settings,'CloudSettings',lambda:config)
    monkeypatch.setattr(settings,'object_store',lambda c:object())
    calls=[]
    class Provider:
        def close(self): calls.append('close')
    monkeypatch.setattr(reaper.RunPod,'from_settings',lambda config:Provider())
    def refresh(*a,recover=True):
        calls.append('delivery' if recover else 'observe')
        return [{'recovered':False}] if recover else []
    monkeypatch.setattr(reaper,'refresh',refresh)
    monkeypatch.setattr(reaper,'reconcile',lambda *a,**kw:calls.append('cleanup') or [])
    assert reaper.main()==1
    assert calls==['observe','cleanup','delivery','cleanup','close']
    assert 'do-not-log' not in capsys.readouterr().out


def test_private_runpod_image_uses_registry_id_not_credentials():
    import json
    from app.render_cloud.provider import RunPod
    def handle(request):
        body = json.loads(request.content)
        assert body['path'] == 'pods'
        assert body['payload']['containerRegistryAuthId'] == 'registry-test-id'
        assert body['payload']['env'] == {}
        return httpx.Response(200,json={'upstream_status':201,'result':{'id':'pod1'}})
    with pytest.raises(ValueError,match='registry authentication ID'):
        RunPod('key',registry_auth_id='https://not-an-id')
    provider=RunPod('',relay_url='https://example.vercel.app/api/runpod',relay_token='x'*32,
                    registry_auth_id='registry-test-id',transport=httpx.MockTransport(handle))
    try:
        assert provider.create(name='editorgpt-test',image=IMAGE,compute='CPU',
                               hardware_ids=['cpu'],env={})['id']=='pod1'
    finally:
        provider.close()


def test_runpod_relay_uses_separate_token_and_keeps_platform_errors_uncertain():
    from app.render_cloud.provider import ProviderError, ProviderRejected, RunPod
    responses = iter([httpx.Response(200,json={'upstream_status':200,'result':[]}),
                      httpx.Response(404),
                      httpx.Response(200,json={'upstream_status':403,'result':None})])
    def handle(request):
        assert request.url == 'https://example.vercel.app/api/runpod'
        assert request.method == 'POST'
        assert request.headers['Authorization'] == 'Bearer ' + 'x'*32
        assert b'provider-secret' not in request.content
        return next(responses)
    provider = RunPod('provider-secret', relay_url='https://example.vercel.app/api/runpod',
                      relay_token='x'*32, transport=httpx.MockTransport(handle))
    try:
        assert provider.list() == []
        with pytest.raises(ProviderError, match='relay_http_404') as error:
            provider.delete('somepod')
        assert not isinstance(error.value, ProviderRejected)
        with pytest.raises(ProviderRejected, match='runpod_http_403'):
            provider.list()
    finally:
        provider.close()


def test_cloud_admin_routes_reuse_auth_and_enforce_server_ceilings(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.render_cloud import admin as routes
    from app.render_cloud.settings import CloudSettings
    from app.config import settings
    config = CloudSettings(ledger=tmp_path/'ledger.db',runpod_api_key='never-return-this-key')
    monkeypatch.setattr(routes,'CloudSettings',lambda:config)
    monkeypatch.setattr(settings,'AI_ADMIN_USER_IDS','administrator')
    app = FastAPI()
    @app.middleware('http')
    async def identity(request,call_next):
        request.state.user=SimpleNamespace(id=request.headers.get('test-user','ordinary'),email='')
        return await call_next(request)
    app.include_router(routes.router)
    with TestClient(app) as client:
        assert client.get('/admin/render-cloud/status').status_code==403
        headers={'test-user':'administrator'}
        response=client.get('/admin/render-cloud/status',headers=headers)
        assert response.status_code==200 and 'never-return-this-key' not in response.text
        assert client.put('/admin/render-cloud/controls',headers=headers,json={'daily_budget':99999}).status_code==422
        assert client.put('/admin/render-cloud/controls',headers=headers,json={'enable_cloud_render':True}).status_code==422
        saved=client.put('/admin/render-cloud/controls',headers=headers,json={'daily_budget':.5})
        assert saved.status_code==200 and saved.json()['limits']['daily_budget']==.5
        assert config.effective().daily_budget==.5 and not config.effective().enable_cloud_render


def test_mlt_hook_rebases_assets_without_modifying_timeline_or_source(tmp_path,monkeypatch):
    from app.render_cloud import hooks,service
    import xml.etree.ElementTree as ET
    monkeypatch.setenv('RENDER_CLOUD_ENABLE_CLOUD_RENDER','1')
    monkeypatch.setenv('RENDER_CLOUD_ADMIN_USER_IDS','user')
    (tmp_path/'raw.mp4').write_bytes(b'owned-video')
    (tmp_path/'captions.ass').write_text('fixture subtitles')
    markup=f'<mlt><profile width="1080" height="1920" frame_rate_num="30"/><property name="ai-render:burn_ass">captions.ass</property><producer><property name="resource">{tmp_path}/raw.mp4</property></producer><tractor id="main" in="0" out="29"/></mlt>'
    source=tmp_path/'project.mlt'
    source.write_text(markup)
    def render(project,output,**kw):
        tree=ET.parse(project/'project.mlt')
        path=tree.findtext('producer/property')
        assert path.startswith('assets/') and (project/path).read_bytes()==b'owned-video'
        assert tree.find('tractor').get('out')=='29'
        assert kw['width']==540 and kw['height']==960 and kw['duration']==1
        assert set(kw['features']) == {'subtitles', 'preview', 'custom-export', 'mlt-preset:veryfast'}
        return True
    monkeypatch.setattr(service,'render_prepared',render)
    token=hooks.identity.set(('user','job',(tmp_path,)))
    try:
        assert hooks.mlt(source,tmp_path/'out.mp4',preview=True,style_override={'render':{'preview_scale':.5}})
    finally: hooks.identity.reset(token)
    assert source.read_text()==markup


def test_an_exhausted_budget_or_busy_worker_falls_back_to_the_server_instead_of_failing_the_video(tmp_path, monkeypatch):
    """The reservation is refused before any Pod exists: nothing is billed, so the video renders locally (and says why)."""
    import json
    from app.render_cloud import service
    from app.render_cloud.ledger import Conflict
    from app.render_cloud.settings import CloudSettings
    class Provider:
        def close(self): pass
        def list(self): return []
    monkeypatch.setattr(service, 'object_store', lambda cfg: object())
    monkeypatch.setattr(service.RunPod, 'from_settings', lambda config: Provider())
    project = tmp_path/'project'; project.mkdir(); (project/'index.html').write_bytes(b'page')
    profiles = tmp_path/'benchmarks.json'
    profiles.write_text(json.dumps([{'engine':'hyperframes_page','backend':'runpod_cpu','width':160,'height':90,'fps':30,'max_duration':30,'end_to_end_seconds':10,
                                    'estimated_usd':.01,'parity_verified':True,'image_digest':IMAGE,'hourly_usd':.1,'hardware_id':'cpu','min_memory_gb':8}]))
    config = CloudSettings(enable_cloud_render=True, enable_runpod_cpu=True, sandbox_verified=True, network_namespace_verified=True, admin_user_ids='user', image=IMAGE,
                           cpu_ids='cpu', max_wall_seconds=60, ledger=tmp_path/'ledger.db', benchmarks=profiles, runpod_api_key='fake-key')
    stages = []
    args = dict(user='user', project_id='project', engine='hyperframes_page', duration=1, width=160, height=90, config=config, on_stage=lambda *a: stages.append(a))
    for reason in ('Budget limit', 'Concurrency limit'):
        monkeypatch.setattr(service, 'provision', lambda *a, _r=reason, **k: (_ for _ in ()).throw(Conflict(_r)))
        assert service.render_prepared(project, tmp_path/'out.mp4', **args) is False
    assert stages and 'سرور' in stages[-1][1]
    # any other refusal is still a failure; and a fixed 'cloud only' override never silently renders locally
    monkeypatch.setattr(service, 'provision', lambda *a, **k: (_ for _ in ()).throw(Conflict('Idempotency key reused with different input')))
    with pytest.raises(service.CloudRenderError):
        service.render_prepared(project, tmp_path/'out.mp4', **args)
    monkeypatch.setattr(service, 'provision', lambda *a, **k: (_ for _ in ()).throw(Conflict('Budget limit')))
    with pytest.raises(service.CloudRenderError):
        service.render_prepared(project, tmp_path/'out.mp4', **{**args, 'config': config.model_copy(update={'override': 'runpod_cpu'})})
