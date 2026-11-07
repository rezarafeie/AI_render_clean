"""Read-only deployment preflight: no provider calls, secrets, files or Pods created."""
from __future__ import annotations

import importlib.util
import argparse
import json
import os
import re

from .policy import Benchmark
from .settings import CloudSettings


def inspect(config=None, *, phase='admission'):
    if phase not in {'canary', 'admission'}:
        raise ValueError('Unknown preflight phase')
    config = config or CloudSettings()
    checks = {}
    relay = bool(config.runpod_relay_url or config.runpod_relay_token.get_secret_value())
    if relay:
        from .provider import RunPod
        try:
            RunPod.from_settings(config).close()
            checks['provider_relay'] = True
        except ValueError:
            checks['provider_relay'] = False
    else:
        checks['provider_key'] = bool(config.runpod_api_key.get_secret_value())
    checks['storage_destination'] = bool(config.s3_bucket and config.storage_hosts)
    checks['storage_sdk'] = importlib.util.find_spec('boto3') is not None
    checks['immutable_worker_image'] = bool(re.fullmatch(r'[^\s]+@sha256:[0-9a-f]{64}',config.image))
    checks['administrator_canary_allowlist'] = bool(config.admin_user_ids.strip())
    checks['hardware_allowlist'] = bool(config.cpu_ids.strip() or config.gpu_ids.strip())
    checks['worker_sandbox_certified'] = config.sandbox_verified
    # Do not create a directory/database as a side effect of diagnostics.
    parent = config.ledger.parent
    checks['persistent_ledger_directory'] = parent.is_dir() and os.access(parent,os.W_OK | os.X_OK)
    profiles = []
    try:
        if config.benchmarks.stat().st_size > 1024**2:
            raise ValueError('Oversized profile registry')
        raw = json.loads(config.benchmarks.read_text())
        if not isinstance(raw,list) or len(raw)>1000:
            raise ValueError('Invalid profile registry')
        profiles = [Benchmark(**row) for row in raw]
        checks['valid_profile_registry'] = bool(profiles)
    except (OSError,ValueError,TypeError):
        checks['valid_profile_registry'] = False
    checks['eligible_measured_profile'] = any(
        p.parity_verified and config.isolates(p.engine) and p.image_digest==config.image and p.vcpu==config.vcpu
        and p.hourly_usd>0 and p.min_memory_gb>0 and p.estimated_usd>0
        and p.hardware_id in (config.cpu_ids if p.backend=='runpod_cpu' else config.gpu_ids).split(',')
        and (p.backend=='runpod_cpu' or p.backend=='runpod_gpu' and p.gpu_acceleration_verified)
        for p in profiles)
    admission_only = {'worker_sandbox_certified', 'valid_profile_registry', 'eligible_measured_profile'}
    required = {name: ok for name,ok in checks.items()
                if phase=='admission' or name not in admission_only}
    return {'phase':phase,'local_preflight_passed':all(required.values()),'checks':checks,
            'missing':[name for name,ok in required.items() if not ok],
            'cloud_admission_enabled':config.enable_cloud_render,
            'live_provider_verified':False,
            'note':'Read-only configuration checks, not live storage/provider/parity certification.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase',choices=('canary','admission'),default='admission')
    args=parser.parse_args()
    try:
        result=inspect(phase=args.phase)
    except Exception:
        # Pydantic/SDK exceptions may include environment values.
        result={'local_preflight_passed':False,'error':'invalid_server_configuration'}
    print(json.dumps(result))
    return 0 if result['local_preflight_passed'] else 2


if __name__=='__main__':
    raise SystemExit(main())
