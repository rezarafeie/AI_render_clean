"""Measured cgroup-v2 container resources for dedicated one-job Pods.

Never reinterpret shared-VPS/container totals as a single render's usage. GPU
utilization remains unknown until a GPU-specific measured backend is admitted.
"""
import time
from pathlib import Path


class Meter:
    def __init__(self, root=Path('/sys/fs/cgroup'), clock=time.monotonic):
        self.root, self.clock = root, clock
        self.started = clock()
        self.cpu_start = self.cpu()

    def cpu(self):
        try:
            rows = dict(line.split() for line in (self.root/'cpu.stat').read_text().splitlines())
            return int(rows['usage_usec'])/1_000_000
        except (OSError,ValueError,KeyError):
            return None

    def finish(self):
        elapsed = self.clock()-self.started
        current = self.cpu()
        seconds = max(0,current-self.cpu_start) if current is not None and self.cpu_start is not None else None
        try:
            peak = int((self.root/'memory.peak').read_text().strip())
        except (OSError,ValueError):
            peak = None
        return {'cgroup_peak_memory_bytes':peak,'cpu_seconds':seconds,
                'cpu_core_percent':100*seconds/elapsed if seconds is not None and elapsed>0 else None,
                'gpu_utilization_percent':None}
