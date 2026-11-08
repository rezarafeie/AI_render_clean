"""Connect a prepared render to one dedicated Pod, keeping publication on the VPS."""
from __future__ import annotations

import hashlib
import json
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


class CloudRenderError(RuntimeError):
    """Never reinterpret as a creative/layout error or silently start another render."""


def validate_output(spec, path):
    measured = probe(path)
    if (measured['width'], measured['height'], Fraction(measured['fps'])) != (spec.width, spec.height, Fraction(spec.fps)):
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


def await_result(spec, output, *, ledger, store, provider, on_progress=None, on_stage=None,
                 should_cancel=None, sleep=time.sleep):
    row = ledger.get(spec.job_id, spec.user_id)
    storage = json.loads(row['details']).get('storage')
    if not storage:
        raise CloudRenderError('Cloud storage references are missing')
    last_stage = None
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
                report = Snapshot.model_validate(report)
                ledger.snapshot(spec.job_id, spec.user_id, report.token, report.sequence,
                                report.history, report.observation.model_dump(),timings=report.timings,resources=report.resources)
                if report.observation.state in {'failed', 'cancelled'}:
                    raise CloudRenderError('Cloud worker stopped before completion')
                if on_progress and report.observation.progress is not None and report.observation.state == 'rendering':
                    on_progress(report.observation.progress)
                if report.uploaded:
                    if report.observation.state != 'uploading' or not report.sha256 or not report.size:
                        raise CloudRenderError('Invalid cloud upload receipt')
                    candidate = {'sha256': report.sha256, 'size': report.size}
        current = ledger.get(spec.job_id, spec.user_id)
        if on_stage and current['state'] != last_stage:
            on_stage(current['state'])
            last_stage = current['state']
        if candidate:
            if current['state'] != 'completed' and not json.loads(current['details']).get('compute_finished'):
                # Signature-scoped upload is finished. Deleting this dedicated
                # Pod now avoids billing while the VPS fetches/validates output.
                ledger.compute_finished(spec.job_id,spec.user_id,candidate)
                reconcile(provider,ledger)
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
            return _render_prepared(project, output, marker_root=lock_root, **{**kwargs, 'config': config})
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def _render_prepared(project: Path, output: Path, *, user, project_id, engine,
                    duration, width, height, fps=30, timeout=1800, on_progress=None,
                    on_stage=None, should_cancel=None, config=None, entrypoint='index.html',
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
                      storage_hosts=config.storage_hosts,max_hourly_usd=profile.hourly_usd,min_memory_gb=profile.min_memory_gb,
                      bootstrap=lambda token: store.bootstrap(spec, root, token, time.time() + config.max_wall_seconds, ledger,
                                                              local_output=output.resolve()))
            await_result(spec, output, ledger=ledger, store=store, provider=provider,
                         on_progress=on_progress, on_stage=on_stage, should_cancel=should_cancel)
            return True
        except InterruptedError:
            ledger.cancel(spec.job_id, spec.user_id)
            ledger.finish(spec.job_id, spec.user_id, 'cancelled', 'cancelled')
            raise
        except Exception:
            ledger.finish(spec.job_id, spec.user_id, 'failed', 'cloud_execution_failed')
            raise CloudRenderError('Cloud render failed; resource cleanup is tracked separately') from None
        finally:
            try:
                reconcile(provider, ledger)
            except Exception:
                pass  # Independent timer retries; never claim resources released.
            provider.close()
