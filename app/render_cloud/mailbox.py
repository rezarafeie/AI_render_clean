"""Single-job signed object mailboxes. No new internet-facing auth endpoint."""
from __future__ import annotations

import json
import time
import threading
import math

import httpx
from pydantic import Field, field_validator, model_validator

from .contracts import Observation, RenderSpec, Strict
from .transfer import validate_url


class Envelope(Strict):
    spec: RenderSpec
    downloads: dict[str, str]
    output_put: str
    mailbox_put: str
    control_get: str
    token: str = Field(min_length=32, max_length=100)
    expires_at: float


class Snapshot(Strict):
    token: str = Field(min_length=32, max_length=100)
    sequence: int = Field(ge=1, le=100000)
    history: list[str] = Field(min_length=1, max_length=4)
    observation: Observation
    uploaded: bool = False
    sha256: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')
    size: int | None = Field(default=None, ge=1, le=200 * 1024**3)
    timings: dict[str,float] = Field(default_factory=dict)
    resources: dict[str,float | None] = Field(default_factory=dict)

    @model_validator(mode='after')
    def upload_receipt(self):
        if self.uploaded and (self.observation.state!='uploading' or not self.sha256 or not self.size):
            raise ValueError('Uploaded snapshot requires a complete upload receipt')
        return self

    @field_validator('resources')
    @classmethod
    def resource_values(cls,value):
        keys={'cgroup_peak_memory_bytes','cpu_seconds','cpu_core_percent','gpu_utilization_percent'}
        if any(k not in keys or v is not None and (not math.isfinite(v) or v<0) for k,v in value.items()):
            raise ValueError('Invalid resource observation')
        return value

    @field_validator('timings')
    @classmethod
    def measured_phases(cls,value):
        if any(key not in {'preparing','downloading','rendering','uploading'} or not math.isfinite(seconds) or not 0<=seconds<=21600 for key,seconds in value.items()):
            raise ValueError('Invalid stage timing')
        return value


def get_json(url, hosts, *, limit=16 * 1024**2, client=None):
    validate_url(url, hosts)
    owned = client is None
    client = client or httpx.Client(timeout=30, follow_redirects=False, trust_env=False)
    try:
        with client.stream('GET', url) as response:
            if response.status_code != 200:
                raise RuntimeError('Worker object unavailable')
            chunks, size = [], 0
            for block in response.iter_bytes(65536):
                size += len(block)
                if size > limit:
                    raise ValueError('Worker object exceeds limit')
                chunks.append(block)
        return json.loads(b''.join(chunks))
    finally:
        if owned:
            client.close()


def put_json(url, value, hosts, *, client=None):
    validate_url(url, hosts)
    owned = client is None
    client = client or httpx.Client(timeout=30, follow_redirects=False, trust_env=False)
    try:
        result = client.put(url, content=json.dumps(value).encode(), headers={'Content-Type': 'application/json'})
        if not result.is_success:
            raise RuntimeError('Worker report unavailable')
    finally:
        if owned:
            client.close()


class Reporter:
    def __init__(self, envelope: Envelope, hosts, *, get=get_json, put=put_json, clock=time.monotonic):
        self.envelope, self.hosts, self.get, self.put, self.clock = envelope, hosts, get, put, clock
        self.sequence, self.history, self.state, self.progress = 0, [], 'preparing', None
        self.last_report, self.last_control = -100., -100.
        self.cancelled = False
        self.lock = threading.RLock()
        self.phase_started, self.timings = clock(), {}

    def check_cancel(self):
        with self.lock:
            return self._check_cancel()

    def _check_cancel(self):
        if time.time() >= self.envelope.expires_at:
            self.cancelled = True
        if self.clock() - self.last_control >= 3:
            # Failure to reach control is fail-closed: don't continue spending
            # while the application cannot signal cancellation.
            data = self.get(self.envelope.control_get, self.hosts, limit=4096)
            if type(data.get('cancel')) is not bool:
                raise ValueError('Invalid control object')
            self.cancelled |= data['cancel']
            self.last_control = self.clock()
        if self.clock() - self.last_report >= 10:
            self.report(self.state, self.progress)
        return self.cancelled

    def report(self, state, progress=None, *, uploaded=False, sha256=None, size=None, resources=None, reason=None):
        order = ['preparing', 'downloading', 'rendering', 'uploading']
        if state not in {'failed', 'cancelled'}:
            if state not in order or (self.history and state != self.history[-1] and order.index(state) != len(self.history)):
                raise ValueError('Invalid report stage')
            if state not in self.history:
                self.history.append(state)
        now = self.clock()
        if state != self.state:
            self.timings[self.state] = now-self.phase_started
            self.phase_started = now
        self.state, self.progress = state, progress
        self.sequence += 1
        event = Snapshot(token=self.envelope.token, sequence=self.sequence, history=self.history,
                         observation=Observation(state=state, progress=progress,
                                                 error_code='worker_failed' if state == 'failed' else None,
                                                 reason=reason if state == 'failed' else None),
                         uploaded=uploaded, sha256=sha256, size=size,
                         resources=resources or {},
                         timings={**self.timings,**({state:now-self.phase_started} if state in order else {})})
        self.put(self.envelope.mailbox_put, event.model_dump(), self.hosts)
        self.last_report = self.clock()

    def render_progress(self, percent):
        self.progress = percent
        if self.clock() - self.last_report >= 5:
            self.report('rendering', percent)
