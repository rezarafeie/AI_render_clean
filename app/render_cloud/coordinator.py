"""Pod admission only: never replace Studio orchestration or reinterpret plans.

The application must pass server-authorized specs and a scoped bootstrap URL.
No public route is added here; rollout remains administrator-only and off.
"""
from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass

from .ledger import Conflict
from .policy import Flags
from .provider import ProviderError, ProviderRejected, RunPod


@dataclass(frozen=True)
class Limits:
    max_cost: float = .5
    daily_budget: float = 5
    monthly_budget: float = 30
    max_workers: int = 1
    max_gpu: int = 0
    max_wall_seconds: int = 1800


def provision(spec, *, ledger, provider: RunPod, flags: Flags, admin: bool,
              backend: str, estimate: float, limits: Limits, image: str,
              hardware_ids: list[str], deployment: str, bootstrap, vcpu=8, disk_gb=40, storage_hosts='', max_hourly_usd=None,min_memory_gb=0,data_centers=()):
    """Persist intent, call create ONCE, retain uncertain resources for the reaper.

    bootstrap(token) must persist an expiring private worker envelope and return
    only its signed URL. Do not return the capability token to an ordinary user.
    The caller must already have a parity-verified routing profile.
    """
    allowed = ((backend == 'runpod_cpu' and flags.enable_runpod_cpu)
               or (backend == 'runpod_gpu' and flags.enable_runpod_gpu))
    if not admin or not flags.enable_cloud_render or not allowed:
        raise PermissionError('Cloud administrator canary is disabled')
    if spec.timeout_seconds > limits.max_wall_seconds:
        raise ValueError('Render exceeds wall-time allowance')
    fingerprint = hashlib.sha256(spec.model_dump_json().encode()).hexdigest()
    row = ledger.reserve(spec.job_id, spec.user_id, fingerprint, backend,
                         estimate=estimate, max_cost=limits.max_cost, daily_budget=limits.daily_budget,
                         monthly_budget=limits.monthly_budget, max_workers=limits.max_workers,
                         max_gpu=limits.max_gpu, timeout=limits.max_wall_seconds)
    if row['create_attempted'] or row['state'] != 'queued':
        return {'job_id': spec.job_id, 'state': row['state'], 'pod_id': row['pod_id']}
    owner, token = secrets.token_hex(16), secrets.token_urlsafe(32)
    ledger.claim(spec.job_id, spec.user_id, owner)
    name = RunPod.name(deployment, secrets.token_hex(16))
    try:
        url = bootstrap(token)
        # Credential-free URL validation; allowlist/DNS enforcement belongs to
        # the signed transport policy installed in the worker image.
        from urllib.parse import urlsplit
        parsed = urlsplit(url)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError('HTTPS bootstrap URL required')
    except Exception:
        ledger.finish(spec.job_id, spec.user_id, 'failed', 'bootstrap_failed')
        raise RuntimeError('Worker bootstrap preparation failed') from None
    ledger.begin_create(spec.job_id, spec.user_id, owner, name, image, token)
    try:
        pod = provider.create(name=name, image=image,
                              compute='CPU' if backend == 'runpod_cpu' else 'GPU',
                              hardware_ids=hardware_ids, env={'EDITOR_RENDER_BOOTSTRAP_URL': url, 'RENDER_STORAGE_HOSTS': storage_hosts},
                              vcpu=vcpu, disk_gb=disk_gb, data_centers=data_centers)
    except (ProviderRejected, ValueError) as exc:
        # Keep the provider's HTTP status (runpod_http_400 / _402 / _404 …): the reason of a refusal is otherwise lost (the relay hides the body by design).
        status = str(exc) if str(exc).startswith('runpod_http_') else ''
        ledger.finish(spec.job_id,spec.user_id,'failed','provisioning_rejected' + (':' + status if status else ''))
        ledger.rejected_create(spec.job_id,spec.user_id)
        raise ProviderError('provisioning_rejected') from None
    except ProviderError:
        ledger.finish(spec.job_id, spec.user_id, 'failed', 'provisioning_uncertain')
        # No local fallback while a remote billable resource may exist.
        raise ProviderError('provisioning_uncertain_reconciliation_required') from None
    try:
        ledger.bind_pod(spec.job_id, spec.user_id, owner, pod['id'])
    except Conflict:
        # The durable random name permits recovery even if a coordinator crashed
        # or its lease expired between the provider response and this write.
        raise ProviderError('pod_binding_reconciliation_required') from None
    if max_hourly_usd is not None:
        import math
        try:
            # Both fields are documented provider responses; use the larger
            # quote conservatively rather than assuming a discount is permanent.
            prices = [float(pod[k]) for k in ('costPerHr','adjustedCostPerHr') if pod.get(k) is not None]
            if not prices or not all(math.isfinite(p) and p >= 0 for p in prices) or max(prices) > max_hourly_usd:
                raise ValueError('Unverified quote')
        except (TypeError,ValueError):
            ledger.finish(spec.job_id,spec.user_id,'failed','resource_quote_exceeded')
            raise ProviderError('resource_quote_unverified_or_exceeded') from None
    if min_memory_gb:
        import math
        try:
            memory = float(pod.get('memoryInGb',0))
            if not math.isfinite(memory) or memory < min_memory_gb or int(pod.get('vcpuCount',0)) < vcpu:
                raise ValueError('Insufficient allocation')
        except (TypeError,ValueError):
            ledger.finish(spec.job_id,spec.user_id,'failed','resource_allocation_insufficient')
            raise ProviderError('resource_allocation_insufficient') from None
    return {'job_id': spec.job_id, 'state': ledger.get(spec.job_id, spec.user_id)['state'], 'pod_id': pod['id']}
