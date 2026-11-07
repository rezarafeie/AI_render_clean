"""Infrastructure details are administrator-only, using existing EditorGPT auth."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ConfigDict
from typing import Literal

from app.routers.lm_admin import admin
from .ledger import Ledger
from .settings import CloudSettings

router = APIRouter(prefix='/admin/render-cloud', tags=['Render administration'], dependencies=[Depends(admin)])


@router.get('/status')
def status():
    base = CloudSettings()
    config = base.effective()
    return {'enabled':config.enable_cloud_render, 'cpu':config.enable_runpod_cpu,
            'gpu':config.enable_runpod_gpu, 'serverless':False,
            'local_fallback':config.enable_local_fallback, 'sandbox_verified':config.sandbox_verified,
            'network_namespace_verified':config.network_namespace_verified,
            'limits':{'daily_budget':config.daily_budget,'monthly_budget':config.monthly_budget,
                      'max_cost':config.max_cost,'max_workers':config.max_workers,'max_gpu':config.max_gpu},
            'override':config.override,
            'ceilings':{k:getattr(base,k) for k in ('daily_budget','monthly_budget','max_cost','max_workers','max_gpu')},
            'executions':Ledger(config.ledger).summaries() if config.ledger.is_file() else [],
            'cost_note':'Reservations are estimates; null provider charges mean not yet reported. Storage/network breakdown may be unavailable.'}


class Cancel(BaseModel):
    model_config = ConfigDict(extra='forbid')
    job_id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,100}$')


class Controls(BaseModel):
    model_config = ConfigDict(extra='forbid')
    max_cost: float | None = Field(default=None,gt=0,allow_inf_nan=False)
    daily_budget: float | None = Field(default=None,gt=0,allow_inf_nan=False)
    monthly_budget: float | None = Field(default=None,gt=0,allow_inf_nan=False)
    max_workers: int | None = Field(default=None,ge=1,le=20)
    max_gpu: int | None = Field(default=None,ge=0,le=10)
    enable_cloud_render: bool | None = None
    enable_runpod_cpu: bool | None = None
    enable_runpod_gpu: bool | None = None
    override: Literal['auto','local','runpod_cpu','runpod_gpu'] | None = None


@router.put('/controls')
def controls(body: Controls):
    base = CloudSettings()
    values = body.model_dump(exclude_none=True)
    for key in ('max_cost','daily_budget','monthly_budget','max_workers','max_gpu'):
        if key in values and values[key] > getattr(base,key):
            raise HTTPException(422,'Requested limit exceeds the server ceiling')
    for key in ('enable_cloud_render','enable_runpod_cpu','enable_runpod_gpu'):
        if values.get(key) and (not getattr(base,key) or not base.sandbox_verified):
            raise HTTPException(422,'A server-enabled, sandbox-verified canary is required')
    Ledger(base.ledger).update_policy(values)
    return status()


@router.post('/cancel', status_code=202)
def cancel(body: Cancel):
    config = CloudSettings()
    if not config.ledger.is_file():
        raise HTTPException(404,'Cloud execution not found')
    ledger = Ledger(config.ledger)
    row = next((r for r in ledger.reconciliation_rows() if r['id'] == body.job_id),None)
    if not row:
        raise HTTPException(404,'Cloud execution not found')
    return {'cancellation_requested':ledger.cancel(row['id'],row['user_id'])}
