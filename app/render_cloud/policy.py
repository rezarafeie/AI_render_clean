"""No hardware guesswork: automatic offload requires an approved measured profile."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Benchmark:
    engine: str
    backend: str
    width: int
    height: int
    fps: int
    max_duration: float
    end_to_end_seconds: float
    estimated_usd: float
    parity_verified: bool
    image_digest: str
    hourly_usd: float = 0  # Must be populated from a measured/verified offer before admission.
    hardware_id: str = ''
    export_format: str = 'mp4'
    features: tuple[str,...] = ()
    vcpu: int = 8
    min_memory_gb: float = 0
    gpu_acceleration_verified: bool = False

    def __post_init__(self):
        import math,re
        if (self.backend not in {'local','runpod_cpu','runpod_gpu'} or self.export_format not in {'mp4','webm'}
                or type(self.parity_verified) is not bool or type(self.gpu_acceleration_verified) is not bool
                or not 1<=self.vcpu<=64 or not 1<=self.fps<=120
                or not 16<=self.width<=7680 or not 16<=self.height<=7680):
            raise ValueError('Invalid measured render profile')
        for value in (self.max_duration,self.end_to_end_seconds,self.estimated_usd,self.hourly_usd,self.min_memory_gb):
            if not math.isfinite(value) or value<0:
                raise ValueError('Non-finite render profile measurement')
        if self.max_duration<=0 or self.end_to_end_seconds<=0 or not re.fullmatch(r'[^\s]+@sha256:[0-9a-f]{64}',self.image_digest):
            raise ValueError('Profile must identify an immutable image and real timings')


@dataclass(frozen=True)
class Flags:
    enable_cloud_render: bool = False
    enable_runpod_cpu: bool = False
    enable_runpod_gpu: bool = False
    enable_runpod_serverless: bool = False
    enable_local_fallback: bool = True


def choose(spec, profiles: list[Benchmark], flags=Flags(), *, admin=False,
           override='auto', max_cost=1.0, image_digest='') -> tuple[str, str]:
    if override not in {'auto', 'local', 'runpod_cpu', 'runpod_gpu'}:
        raise ValueError('Unsupported render override')
    if override != 'auto' and not admin:
        raise PermissionError('Administrator override required')
    if override == 'local':
        return 'local', 'administrator override'
    if not flags.enable_cloud_render or not admin:
        if override.startswith('runpod'):
            raise ValueError('Cloud canary is disabled')
        return 'local', 'cloud disabled or not an administrator canary'
    candidates = [p for p in profiles if p.engine == spec.engine and p.parity_verified
                  and p.export_format==spec.export_format and set(p.features)==set(spec.features)
                  and (not spec.gpu_required or p.backend=='runpod_gpu')
                  and (p.backend!='runpod_gpu' or p.gpu_acceleration_verified)
                  and p.image_digest == image_digest and image_digest
                  and (p.width, p.height, p.fps) == (spec.width, spec.height, spec.fps)
                  and p.max_duration >= spec.duration_seconds and 0 < p.estimated_usd <= max_cost
                  and p.end_to_end_seconds > 0
                  and ((p.backend == 'runpod_cpu' and flags.enable_runpod_cpu)
                       or (p.backend == 'runpod_gpu' and flags.enable_runpod_gpu))]
    if override != 'auto':
        candidates = [p for p in candidates if p.backend == override]
    if not candidates:
        if override != 'auto' or not flags.enable_local_fallback:
            raise ValueError('No verified benchmark profile')
        return 'local', 'no verified benchmark profile'
    picked = min(candidates, key=lambda p: (p.estimated_usd, p.end_to_end_seconds))
    return picked.backend, 'approved measured profile; estimated cost, not provider charge'
