"""Connect a prepared render to one dedicated Pod, keeping publication on the VPS."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import tempfile
import time
import uuid
from fractions import Fraction
from pathlib import Path

from .coordinator import Limits, provision
from .ledger import Conflict, Ledger
from .mailbox import Snapshot
from .parity import probe
from .policy import Benchmark, choose
from .prepare import freeze
from .provider import RunPod, reconcile
from .settings import CloudSettings, object_store


log = logging.getLogger(__name__)


class CloudRenderError(RuntimeError):
    """Never reinterpret as a creative/layout error or silently start another render."""


def _pod_snapshot(provider, pod_id) -> str:
    """What RunPod says about a pod that never reported (assigned to a machine? running? when did its status change?): the evidence of WHY it was silent. Never raises, never secrets."""
    try:
        for row in provider.list():
            if row.get('id') == pod_id:
                keep = ('desiredStatus', 'lastStatusChange', 'lastStartedAt', 'machineId', 'uptimeSeconds', 'runtime', 'lastError', 'costPerHr', 'cpuFlavorId', 'vcpuCount', 'memoryInGb', 'containerDiskInGb')
                return json.dumps({k: row.get(k) for k in keep if k in row}, default=str)[:700]
        return 'pod not listed (already gone)'
    except Exception as exc:
        return 'snapshot unavailable: ' + type(exc).__name__


import threading as _threading
_STATE = _threading.local()      # per render thread: whether a fresh-pod retry is still allowed / the last attempt ended in a startup timeout


class WorkerStartupTimeout(CloudRenderError):
    """The worker never reported (its pod did not boot or pull its image in time): the pod is deleted, the render may continue on the server."""


class WorkerStalled(WorkerStartupTimeout):
    """The worker reported but its progress stopped for too long (a hung render): the pod is deleted, the render may continue on the server."""


class WorkerRejected(CloudRenderError):
    """The worker stopped on the project itself (for example a HyperFrames check finding). `reason` is its scrubbed finding, so the caller
    that authored the project can repair it; every other cloud failure stays final."""
    def __init__(self, message, reason=''):
        super().__init__(message)
        self.reason = reason


def validate_output(spec, path):
    measured = probe(path)
    # ffprobe reports the average rate as a ratio of frames to duration (1640000000/54666333 for a clean 30 fps clip): compare with a tolerance far
    # smaller than any real rate difference (29.97 vs 30 is 0.03).
    if ((measured['width'], measured['height']) != (spec.width, spec.height)
            or abs(float(Fraction(measured['fps'])) - float(Fraction(spec.fps))) > .005):
        raise ValueError('Cloud output dimensions or frame rate differ')
    if abs(measured['duration'] - spec.duration_seconds) > max(1/spec.fps, .05):
        raise ValueError('Cloud output duration differs')
    if abs(measured['frames'] - round(spec.duration_seconds * spec.fps)) > 1:
        raise ValueError('Cloud output frame count differs')
    if spec.audio_required and measured['audio_duration'] is None:
        raise ValueError('Cloud output audio missing')
    if measured['audio_start'] is not None and (abs(measured['audio_start'] - measured['video_start']) > .1
                                              or abs(measured['audio_duration'] - measured['duration']) > .15):
        raise ValueError('Cloud output audio timing differs')
    return measured


_STAGE_TEXT = {
    'queued': 'در صف رندر ابری…',
    'provisioning': 'در حال راه‌اندازی سرور رندر ابری…',
    'preparing': 'آماده‌سازی محیط رندر ابری…',
    'downloading': 'دریافت فایل‌ها برای رندر ابری…',
    'uploading': 'دریافت ویدیوی آمادهٔ رندر ابری…',
    'delivering': 'دریافت ویدیو از ابر و بررسی نهایی…',
}


def _duration_text(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    minutes, rest = divmod(seconds, 60)
    return f'{minutes} دقیقه و {rest} ثانیه' if minutes else f'{rest} ثانیه'


def cloud_detail(state: str, progress=None, rendering_seconds: float = 0.0) -> str:
    """What the person sees under the progress bar while a render runs in the cloud: the stage, and while rendering the exact percentage and time left
    (estimated from the pace so far, shown once there is enough of it to mean something)."""
    if state == 'rendering' and progress is not None:
        percent = max(0.0, min(100.0, float(progress)))
        text = f'رندر ابری: {percent:.0f}٪'
        if percent >= 3 and rendering_seconds >= 5:
            text += f' · حدود {_duration_text(rendering_seconds * (100 - percent) / percent)} باقی مانده'
        else:
            text += ' · در حال محاسبهٔ زمان باقی‌مانده…'
        return text
    if state == 'rendering':
        return 'رندر ابری شروع شد…'
    return _STAGE_TEXT.get(state, 'در حال انجام در رندر ابری…')



def await_result(spec, output, *, ledger, store, provider, on_progress=None, on_stage=None,
                 should_cancel=None, sleep=time.sleep, on_detail=None, startup_seconds=None, stall_seconds=None):
    row = ledger.get(spec.job_id, spec.user_id)
    storage = json.loads(row['details']).get('storage')
    if not storage:
        raise CloudRenderError('Cloud storage references are missing')
    last_stage = None
    rendering_since = None
    last_detail = None
    heard = False                      # the worker has reported at least once
    progress_mark, progress_since = None, time.time()           # the last progress value and when it last changed

    def detail(state, progress=None):
        nonlocal last_detail
        if on_detail is None:
            return
        text = cloud_detail(state, progress, time.monotonic() - rendering_since if rendering_since else 0.0)
        if text != last_detail:
            last_detail = text
            try:
                on_detail(text)
            except Exception:       # a failing status line never stops a render
                pass

    while row['state'] == 'completed' or time.time() < row['deadline']:
        if should_cancel and should_cancel():
            ledger.cancel(spec.job_id, spec.user_id)
            store.write_json(storage['control_key'], {'cancel': True})
            reconcile(provider, ledger)
            raise InterruptedError('Cloud render cancelled')
        row = ledger.get(spec.job_id, spec.user_id)
        if row['cancel_requested']:
            store.write_json(storage['control_key'], {'cancel': True})
            ledger.finish(spec.job_id, spec.user_id, 'cancelled', 'cancelled')
            raise InterruptedError('Cloud render cancelled')
        if row['state'] in {'failed', 'cancelled'}:
            raise CloudRenderError('Cloud execution failed; retry only after resource cleanup')
        candidate = None
        details = json.loads(row['details'])
        if row['state'] == 'completed':
            candidate = json.loads(row['details']).get('output')
        elif details.get('compute_finished'):
            candidate = details.get('candidate')
        else:
            report = store.read_json(storage['mailbox_key'])
            if report is not None:
                heard = True
                report = Snapshot.model_validate(report)
                ledger.snapshot(spec.job_id, spec.user_id, report.token, report.sequence,
                                report.history, report.observation.model_dump(),timings=report.timings,resources=report.resources)
                if report.observation.state in {'failed', 'cancelled'}:
                    log.warning('cloud worker %s stopped: %s', spec.job_id, report.observation.reason or report.observation.error_code)
                    # The reason (a scrubbed check finding, for example) rides along so a caller can repair what the worker rejected.
                    raise WorkerRejected('Cloud worker stopped before completion', report.observation.reason or '')
                if report.observation.state == 'rendering' and rendering_since is None:
                    rendering_since = time.monotonic()
                if report.observation.state == 'rendering' and report.observation.progress != progress_mark:
                    progress_mark, progress_since = report.observation.progress, time.time()
                if on_progress and report.observation.progress is not None and report.observation.state == 'rendering':
                    on_progress(report.observation.progress)
                if report.observation.state == 'rendering':
                    detail('rendering', report.observation.progress)
                if report.uploaded:
                    if report.observation.state != 'uploading' or not report.sha256 or not report.size:
                        raise CloudRenderError('Invalid cloud upload receipt')
                    candidate = {'sha256': report.sha256, 'size': report.size}
        current = ledger.get(spec.job_id, spec.user_id)
        if (startup_seconds and not heard and current['state'] in {'queued', 'provisioning'} and not candidate
                and time.time() - float(current['created']) > startup_seconds):
            log.warning('cloud worker %s silent for %.0f s; its pod is deleted | pod as RunPod reports it: %s', spec.job_id, time.time() - float(current['created']),
                        _pod_snapshot(provider, current.get('pod_id')))
            raise WorkerStartupTimeout('Cloud worker did not start in time')
        if stall_seconds and rendering_since is not None and not candidate and time.time() - progress_since > stall_seconds:
            log.warning('cloud worker %s made no progress for %.0f s (stuck at %s); its pod is deleted', spec.job_id, time.time() - progress_since, progress_mark)
            raise WorkerStalled('Cloud worker stopped making progress')
        if current['state'] != last_stage:
            if on_stage:
                on_stage(current['state'])
            if current['state'] != 'rendering':          # while rendering the line carries the percentage instead
                detail(current['state'])
            last_stage = current['state']
        if candidate:
            if current['state'] != 'completed' and not json.loads(current['details']).get('compute_finished'):
                # Signature-scoped upload is finished. Deleting this dedicated
                # Pod now avoids billing while the VPS fetches/validates output.
                ledger.compute_finished(spec.job_id,spec.user_id,candidate)
                reconcile(provider,ledger)
            detail('delivering')
            output.parent.mkdir(parents=True, exist_ok=True)
            temporary = output.with_name('.cloud-' + uuid.uuid4().hex + '.mp4')
            try:
                receipt = store.fetch_candidate(storage['output_key'], temporary,
                                                max_bytes=spec.workspace_bytes,
                                                should_cancel=should_cancel)
                if receipt['sha256'] != candidate['sha256'] or receipt['size'] != candidate['size']:
                    raise CloudRenderError('Cloud candidate integrity mismatch')
                receipt['media'] = validate_output(spec, temporary)
                if should_cancel and should_cancel():
                    ledger.cancel(spec.job_id, spec.user_id)
                    raise InterruptedError('Cloud delivery cancelled')
                if row['state'] != 'completed':
                    ledger.complete(spec.job_id, spec.user_id, expected_pod_id=current['pod_id'], output_receipt=receipt)
                os.replace(temporary, output)
                return output
            finally:
                temporary.unlink(missing_ok=True)
        sleep(3)
    ledger.finish(spec.job_id, spec.user_id, 'failed', 'execution_deadline')
    raise CloudRenderError('Cloud execution deadline exceeded')


def render_prepared(project: Path, output: Path, **kwargs):
    config = (kwargs.get('config') or CloudSettings()).effective()
    if os.environ.get('EDITOR_RENDER_CHILD') == '1' or not config.enable_cloud_render or not config.admin(kwargs.get('user')) or config.override=='local':
        return False
    # Filesystem lock is shared across app processes, not merely Python threads.
    # Hold it until output publication/resource cleanup; duplicate coordinators
    # may reconnect later but cannot both create a new execution marker.
    import fcntl
    lock_root = Path(kwargs.pop('lock_root', project))
    if not lock_root.is_dir():
        raise CloudRenderError('Owned render workspace is unavailable')
    with (lock_root/'.cloud-render.lock').open('a') as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise CloudRenderError('This prepared project already has a render coordinator') from None
        try:
            _STATE.retry_allowed, _STATE.timed_out = True, False
            result = _render_prepared(project, output, marker_root=lock_root, **{**kwargs, 'config': config})
            if result is False and _STATE.timed_out and not (kwargs.get('should_cancel') and kwargs['should_cancel']()):
                # A pod that never got a machine is the usual way the cloud fails (capacity differs from pod to pod): one fresh pod is tried before the server renders it.
                # The startup-failure breaker still applies, so two bad attempts in a row keep the next films off the cloud for a while.
                log.warning('cloud worker did not start; trying one fresh pod before rendering on the server')
                _STATE.retry_allowed, _STATE.timed_out = False, False
                result = _render_prepared(project, output, marker_root=lock_root, **{**kwargs, 'config': config})
            return result
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def _render_prepared(project: Path, output: Path, *, user, project_id, engine,
                    duration, width, height, fps=30, timeout=1800, on_progress=None,
                    on_stage=None, should_cancel=None, config=None, entrypoint='index.html', on_detail=None,
                    owned_roots=(), audio_required=False, marker_root=None, mlt_options=None,export_format='mp4',features=()):
    """True if cloud rendered; False means the original renderer must run unchanged.

    Called only with a server-resolved project path, never a client path. Legacy
    non-portable projects keep the local path BEFORE any remote admission.
    """
    if os.environ.get('EDITOR_RENDER_CHILD') == '1':
        return False
    config = config or CloudSettings()
    if not config.enable_cloud_render or not config.admin(user):
        return False
    if not config.sandbox_verified:
        raise CloudRenderError('Worker sandbox canary is not verified')
    if not config.isolates(engine):
        if config.enable_local_fallback and config.override == 'auto':
            return False
        raise CloudRenderError('This engine requires verified browser isolation on the worker')
    if not project.is_dir() or not config.benchmarks.is_file():
        if config.enable_local_fallback and config.override == 'auto':
            return False
        raise CloudRenderError('Prepared project or verified benchmarks are unavailable')
    profiles = [Benchmark(**p) for p in json.loads(config.benchmarks.read_text()) if p.get('vcpu',8)==config.vcpu]
    # The prepared project is frozen separately; no mutation of editable source.
    with tempfile.TemporaryDirectory(prefix='editorgpt-cloud-input-') as directory:
        root = Path(directory)
        paths, total_bytes = [], 0
        try:
            for source in project.rglob('*'):
                name = source.relative_to(project)
                if name.parts[0].startswith('.') or name.parts[0].startswith('work-') or source == output or name.name.endswith('.mp4') and len(name.parts) == 1:
                    continue
                if source.is_symlink():
                    # Only the application may supply additional owned media roots.
                    # A symlink is materialized, never shipped as filesystem indirection.
                    resolved = source.resolve(strict=True)
                    if not source.is_file() or not any(resolved.is_relative_to(Path(r).resolve()) for r in (project, *owned_roots)):
                        raise ValueError('Prepared project links outside authorized roots')
                if source.is_file() and source.stat().st_size:
                    total_bytes += source.stat().st_size
                    if len(paths) >= 20000 or total_bytes > config.disk_gb * 1024**3 // 2 or source.stat().st_size > shutil.disk_usage(root).free - 128 * 1024**2:
                        raise ValueError('Input snapshot exceeds disk allowance')
                    target = root / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
                    paths.append(name.as_posix())
            runtime_env = {k: os.environ[k] for k in ('REMOTION_LOOK', 'REMOTION_CONCURRENCY', 'HYPERFRAMES_WORKERS')
                           if k in os.environ}
            render_features = list(features)
            worker_key = ('REMOTION_CONCURRENCY' if engine == 'remotion' else
                          'HYPERFRAMES_WORKERS' if engine.startswith('hyperframes_') else None)
            if worker_key and config.browser_render_workers is not None:
                runtime_env[worker_key] = str(config.browser_render_workers)
                render_features.append('browser-workers:' + runtime_env[worker_key])
            spec = freeze(root, paths, job_id='pending', user_id=str(user), project_id=str(project_id), engine=engine,
                          entrypoint=entrypoint, duration_seconds=duration, width=width, height=height, fps=fps,
                          timeout_seconds=min(int(timeout), config.max_wall_seconds),
                          workspace_bytes=config.disk_gb * 1024**3 // 2, audio_required=audio_required,
                          mlt_options=mlt_options or {},
                          export_format=export_format,output='output.'+export_format,
                          features=render_features, runtime_env=runtime_env)
        except (ValueError, OSError):
            if config.enable_local_fallback and config.override == 'auto':
                return False
            raise CloudRenderError('Prepared project is not portable') from None
        image = config.image_for(engine)
        backend, _ = choose(spec, profiles, config.flags(), admin=True, override=config.override,
                            max_cost=config.max_cost, image_digest=image)
        if backend == 'local':
            return False
        profile = min((p for p in profiles if p.backend == backend and p.engine == engine and p.image_digest == image
                       and (p.width,p.height,p.fps) == (width,height,fps) and p.parity_verified and p.max_duration >= duration
                       and p.export_format==spec.export_format and set(p.features)==set(spec.features)
                       and (backend!='runpod_gpu' or p.gpu_acceleration_verified)
                       and 0 < p.estimated_usd <= config.max_cost and p.end_to_end_seconds > 0),
                       key=lambda p: (p.estimated_usd, p.end_to_end_seconds))
        if profile.hourly_usd <= 0 or not profile.hardware_id or profile.min_memory_gb<=0:
            raise CloudRenderError('A verified resource price is required')
        allowed_ids = (config.cpu_ids if backend == 'runpod_cpu' else config.gpu_ids).split(',')
        if profile.hardware_id not in allowed_ids:
            raise CloudRenderError('Benchmark hardware is not allowlisted')
        ledger = Ledger(config.ledger)
        if (config.enable_local_fallback and config.override == 'auto'
                and ledger.recent_failures(('worker_startup_timeout', 'worker_stalled'), config.startup_breaker_window_seconds) >= config.startup_breaker_count):
            # The cloud workers have just failed to come up several times in a row: waiting out another startup window for each film helps nobody.
            log.warning('cloud render skipped: %d worker startup timeouts in the last %d s', config.startup_breaker_count, config.startup_breaker_window_seconds)
            if on_stage:
                try:
                    on_stage('cloud unavailable', 'رندر ابری این روزها به‌موقع بالا نمی‌آید؛ این ویدیو مستقیم روی سرور رندر می‌شود')
                except Exception:
                    pass
            return False
        # One data center per Pod, chosen from the configured list by what has worked lately: a Pod that never starts then marks its data center bad
        # and the next Pod (the fresh one tried below, the retries above) goes elsewhere; the timeline says where each Pod was placed.
        listed = [d.strip() for d in config.data_centers.split(',') if d.strip()]
        chosen_dc = ledger.dc_order(listed)[0] if listed else None
        if chosen_dc and on_stage:
            try:
                on_stage('cloud placement', f'کارگر ابری در دیتاسنتر {chosen_dc} ساخته می‌شود')
            except Exception:
                pass
        fingerprint = hashlib.sha256(spec.model_dump_json().encode()).hexdigest()
        marker = (marker_root or project) / '.cloud-render-job.json'
        job_id = None
        try:
            saved = json.loads(marker.read_text())
            if saved['fingerprint'] == fingerprint:
                old = ledger.get(saved['job_id'], str(user))
                if old['state'] not in {'failed', 'cancelled'} or old['cleanup_pending'] or ledger.resume_delivery(old['id'],str(user),config.max_wall_seconds):
                    job_id = saved['job_id']
        except (OSError, ValueError, KeyError, Conflict):
            pass
        spec = spec.model_copy(update={'job_id': job_id or uuid.uuid4().hex})
        temp_marker = marker.with_name('.cloud-marker-' + uuid.uuid4().hex)
        temp_marker.write_text(json.dumps({'fingerprint': fingerprint, 'job_id': spec.job_id}))
        os.replace(temp_marker, marker)
        store = object_store(config)
        provider = RunPod.from_settings(config)
        try:
            limits = Limits(config.max_cost, config.daily_budget, config.monthly_budget,
                            config.max_workers, config.max_gpu, config.max_wall_seconds)
            provision(spec, ledger=ledger, provider=provider, flags=config.flags(), admin=True,
                      backend=backend, estimate=max(profile.estimated_usd, profile.hourly_usd * config.max_wall_seconds / 3600),
                      limits=limits, image=image,
                      hardware_ids=[profile.hardware_id],
                      deployment=config.deployment, vcpu=config.vcpu, disk_gb=config.disk_gb,
                      data_centers=[chosen_dc] if chosen_dc else [],
                      storage_hosts=config.storage_hosts,max_hourly_usd=profile.hourly_usd,min_memory_gb=profile.min_memory_gb,
                      bootstrap=lambda token: store.bootstrap(spec, root, token, time.time() + config.max_wall_seconds, ledger,
                                                              local_output=output.resolve()))
            await_result(spec, output, ledger=ledger, store=store, provider=provider,
                         on_progress=on_progress, on_stage=on_stage, should_cancel=should_cancel, on_detail=on_detail,
                         startup_seconds=config.startup_seconds, stall_seconds=config.stall_seconds)
            if chosen_dc:
                ledger.dc_mark_ok(chosen_dc)
            return True
        except InterruptedError:
            ledger.cancel(spec.job_id, spec.user_id)
            ledger.finish(spec.job_id, spec.user_id, 'cancelled', 'cancelled')
            raise
        except Exception as failure:
            if (isinstance(failure, Conflict) and str(failure) in {'Budget limit', 'Concurrency limit'}
                    and config.enable_local_fallback and config.override == 'auto'):
                # The reservation itself was refused (the daily/monthly budget or the worker limit): nothing was created or billed in the cloud.
                # The video is rendered on the server instead of failing; the person is told why it is slower.
                log.warning('cloud render %s not started (%s); rendering on the server', spec.job_id, failure)
                if on_stage:
                    try:
                        on_stage('cloud budget reached', 'سقف مصرف رندر ابری رسیده است؛ این ویدیو روی سرور رندر می‌شود')
                    except Exception:
                        pass
                return False
            if isinstance(failure, WorkerStartupTimeout) and config.enable_local_fallback and config.override == 'auto':
                ledger.finish(spec.job_id, spec.user_id, 'failed', 'worker_stalled' if isinstance(failure, WorkerStalled) else 'worker_startup_timeout')      # the pod is deleted by the reconcile below; nothing else bills
                will_retry = bool(getattr(_STATE, 'retry_allowed', False)) and not isinstance(failure, WorkerStalled)
                _STATE.timed_out = will_retry
                nxt = None
                if chosen_dc and not isinstance(failure, WorkerStalled):      # only a Pod that never reported blames its data center; a hung render does not
                    ledger.dc_mark_bad(chosen_dc, config.data_center_cooldown_seconds)
                    rest = [d for d in ledger.dc_order(listed) if d != chosen_dc]
                    nxt = rest[0] if rest else None
                where = f' (دیتاسنتر {chosen_dc})' if chosen_dc else ''
                if on_stage:
                    try:
                        on_stage('cloud unavailable', (f'سرور ابری{where} به‌موقع بالا نیامد؛ دیتاسنتر عوض می‌شود و یک سرور تازه در {nxt} امتحان می‌شود' if nxt else f'سرور ابری{where} بالا نیامد؛ یک سرور تازه امتحان می‌شود')
                                 if will_retry else f'سرور رندر ابری{where} به‌موقع بالا نیامد یا متوقف شد؛ این ویدیو روی سرور رندر می‌شود')
                    except Exception:
                        pass
                return False
            ledger.finish(spec.job_id, spec.user_id, 'failed', 'cloud_execution_failed')
            if isinstance(failure, (CloudRenderError, ValueError)):       # our own checks, never a provider response with a URL in it
                log.warning('cloud render %s failed: %s', spec.job_id, str(failure)[:200])
            reason = getattr(failure, 'reason', '')
            raise CloudRenderError('Cloud render failed; resource cleanup is tracked separately' + (f' | {reason}' if reason else '')) from None
        finally:
            try:
                reconcile(provider, ledger)
            except Exception:
                pass  # Independent timer retries; never claim resources released.
            provider.close()
