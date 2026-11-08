"""Server-only rollout configuration. No credentials are returned to the UI."""
from pathlib import Path
from typing import Literal
from pydantic import Field, SecretStr, AliasChoices, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .policy import Flags


class CloudSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix='RENDER_CLOUD_', extra='ignore',populate_by_name=True)
    enable_cloud_render: bool = False
    enable_runpod_cpu: bool = False
    enable_runpod_gpu: bool = False
    enable_runpod_serverless: bool = False
    enable_local_fallback: bool = True
    # Set only after the worker image's socketless render and resource-limit
    # canaries pass. Browser engines also require verified loopback isolation.
    sandbox_verified: bool = False
    network_namespace_verified: bool = False
    browser_guest_verified: bool = False
    admin_user_ids: str = ''
    image: str = ''
    deployment: str = 'editor'
    cpu_ids: str = ''
    gpu_ids: str = ''
    override: str = 'auto'
    vcpu: int = Field(default=8, ge=1, le=64)
    disk_gb: int = Field(default=40, ge=10, le=200)
    max_workers: int = Field(default=1, ge=1, le=20)
    max_gpu: int = Field(default=0, ge=0, le=10)
    max_wall_seconds: int = Field(default=1800, ge=60, le=21000)
    max_cost: float = Field(default=.5, gt=0, allow_inf_nan=False)
    daily_budget: float = Field(default=5, gt=0, allow_inf_nan=False)
    monthly_budget: float = Field(default=30, gt=0, allow_inf_nan=False)
    ledger: Path = Field(default_factory=lambda: _data_path('ledger.sqlite'))
    benchmarks: Path = Field(default_factory=lambda: _data_path('benchmarks.json'))
    storage_hosts: str = ''
    s3_bucket: str = ''
    s3_endpoint: str = ''
    s3_region: str = 'us-east-1'
    s3_namespace: Literal['render/v1/', 'render/production/v1/'] = 'render/v1/'
    # boto3 uses the normal server credential chain; no key in this model.
    runpod_api_key: SecretStr = Field(default=SecretStr(''),validation_alias=AliasChoices('RENDER_CLOUD_RUNPOD_API_KEY','RUNPOD_API_KEY'))
    runpod_relay_url: str = ''
    runpod_relay_token: SecretStr = SecretStr('')
    runpod_registry_auth_id: str = ''

    @field_validator('ledger','benchmarks')
    @classmethod
    def absolute_path(cls,value):
        if not value.is_absolute():
            raise ValueError('Cloud state paths must be absolute persistent paths')
        return value

    def effective(self):
        if not self.ledger.is_file():
            return self
        from .ledger import Ledger
        values = Ledger(self.ledger).policy()
        merged = {}
        for key in ('max_cost','daily_budget','monthly_budget','max_workers','max_gpu'):
            if key in values:
                merged[key] = min(getattr(self,key),values[key])
        for key in ('enable_cloud_render','enable_runpod_cpu','enable_runpod_gpu'):
            if key in values:
                merged[key] = bool(getattr(self,key) and values[key])
        if values.get('override') in {'auto','local','runpod_cpu','runpod_gpu'}:
            merged['override'] = values['override']
        return self.model_copy(update=merged)

    def flags(self):
        return Flags(**{name: getattr(self, name) for name in Flags.__dataclass_fields__})

    def admin(self, user):
        return bool(user and str(user) in {v.strip() for v in self.admin_user_ids.split(',') if v.strip()})

    def isolates(self, engine):
        from .socketless import ENGINES
        return self.sandbox_verified and (
            engine in ENGINES or self.network_namespace_verified or self.browser_guest_verified
        )


def object_store(config):
    import boto3  # Optional control-plane dependency, not imported on local renders.
    from botocore.config import Config
    from .storage import ObjectStore
    if not config.s3_bucket or not config.storage_hosts:
        raise ValueError('Cloud object storage is not configured')
    client = boto3.client('s3', endpoint_url=config.s3_endpoint or None, region_name=config.s3_region,
                          config=Config(signature_version='s3v4', connect_timeout=10, read_timeout=30,
                                        s3={'addressing_style':'path'},request_checksum_calculation='when_required',
                                        response_checksum_validation='when_required',
                                        retries={'mode': 'standard', 'max_attempts': 3}))
    return ObjectStore(client, config.s3_bucket, expiry=config.max_wall_seconds + 600,
                       namespace=config.s3_namespace)


def _data_path(name):
    from app.config import settings
    return Path(settings.JOBS_DIR).expanduser().resolve()/'cloud-render'/name
