"""Explicit administrator benchmark runner; never installs an approved profile.

Cloud measurement requires --allow-paid plus server canary configuration. A
successful encode is NOT automatic approval of visual/audio parity.
"""
from __future__ import annotations

import argparse
import json
import time
import uuid
import tempfile
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .contracts import RenderSpec
from .coordinator import Limits, provision
from .engines import verify_inputs
from .ledger import Ledger
from .parity import compare, probe
from .provider import RunPod, reconcile
from .service import await_result
from .settings import CloudSettings, object_store
from .supervisor import run

REQUIRED = ('talking_30s','subtitles_60s','hyperframes_60s','remotion_60s',
            'multilayer','gpu_required','4k','concurrent')


def measure(spec, workspace, output, backend, *, allow_paid=False, max_hourly=None):
    verify_inputs(spec, workspace)
    started = time.monotonic()
    report = {'engine':spec.engine,'backend':backend,'job_id':spec.job_id,
              'manifest_sha256':__import__('hashlib').sha256(spec.model_dump_json().encode()).hexdigest(),
              'peak_ram_bytes':None,'cpu_utilization':None,'gpu_utilization':None,
              'approved_for_routing':False}
    if backend == 'local':
        import shutil
        result = run(spec,workspace)
        if result != output:
            shutil.copy2(result,output)
    else:
        config = CloudSettings().effective()
        if not allow_paid or not config.admin(spec.user_id) or not config.isolates(spec.engine) or not max_hourly or max_hourly <= 0:
            raise PermissionError('Explicit paid administrator canary and positive quote ceiling required')
        ledger, store = Ledger(config.ledger), object_store(config)
        provider = RunPod.from_settings(config)
        try:
            clock = time.monotonic()
            provision(spec,ledger=ledger,provider=provider,flags=config.flags(),admin=True,
                      backend=backend,estimate=max_hourly*config.max_wall_seconds/3600,
                      limits=Limits(config.max_cost,config.daily_budget,config.monthly_budget,
                                    config.max_workers,config.max_gpu,config.max_wall_seconds),
                      image=config.image_for(spec.engine),hardware_ids=[(config.cpu_ids if backend=='runpod_cpu' else config.gpu_ids).split(',')[0]],
                      deployment=config.deployment,vcpu=config.vcpu,disk_gb=config.disk_gb,
                      storage_hosts=config.storage_hosts,max_hourly_usd=max_hourly,
                      bootstrap=lambda token:store.bootstrap(spec,workspace,token,time.time()+config.max_wall_seconds,ledger,
                                                              local_output=output.resolve()))
            report['provision_request_seconds'] = time.monotonic()-clock
            await_result(spec,output,ledger=ledger,store=store,provider=provider)
            report['reservation_usd'] = ledger.get(spec.job_id,spec.user_id)['reservation']
            report['worker_stage_seconds'] = json.loads(ledger.get(spec.job_id,spec.user_id)['details']).get('timings',{})
            report['dedicated_container_resources'] = json.loads(ledger.get(spec.job_id,spec.user_id)['details']).get('resources',{})
        except BaseException:
            ledger.finish(spec.job_id,spec.user_id,'failed','benchmark_failed')
            raise
        finally:
            try: report['cleanup'] = reconcile(provider,ledger)
            finally: provider.close()
    report['end_to_end_seconds'] = time.monotonic()-started
    report['media'] = probe(output)
    report['provider_charge_usd'] = None
    report['not_measured'] = ['peak process-tree RAM','CPU utilization','GPU utilization','storage and egress bills']
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('suite',type=Path)
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--backend',choices=['local','runpod_cpu','runpod_gpu'],default='local')
    parser.add_argument('--allow-paid',action='store_true')
    parser.add_argument('--max-hourly-usd',type=float)
    args = parser.parse_args()
    data = json.loads(args.suite.read_text())
    results = []
    def case_report(case):
        manifest = Path(case['manifest']).resolve()
        original = RenderSpec.model_validate_json(manifest.read_text())
        workspace = Path(case['workspace']).resolve()
        verify_inputs(original,workspace)
        with tempfile.TemporaryDirectory(prefix='editorgpt-benchmark-') as temporary:
            prepared = Path(temporary)
            for asset in original.assets:
                target = prepared/asset.path
                target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(workspace/asset.path,target)
            suffix = '.' + original.export_format
            spec = original.model_copy(update={'job_id':uuid.uuid4().hex,'output':'benchmark-'+uuid.uuid4().hex+suffix})
            output = args.report.parent.resolve()/(spec.job_id+suffix)
            report = measure(spec,prepared,output,args.backend,allow_paid=args.allow_paid,max_hourly=args.max_hourly_usd)
            if case.get('reference'):
                report['metadata_comparison'] = compare(probe(Path(case['reference'])),report['media'])
            return report
    for name in REQUIRED:
        case = data.get(name)
        if name == 'concurrent' and case and case.get('jobs'):
            jobs = case['jobs']
            parallel = int(case.get('max_parallel',2))
            if not 2 <= len(jobs) <= 20 or not 2 <= parallel <= 20:
                results.append({'case':name,'status':'invalid_concurrency_fixture'})
                continue
            def one(item):
                try: return {'status':'measured',**case_report(item)}
                except Exception as error: return {'status':'failed','error_type':type(error).__name__}
            started = time.monotonic()
            with ThreadPoolExecutor(max_workers=parallel) as pool:
                reports = list(pool.map(one,jobs))
            results.append({'case':name,'status':'measured' if all(r['status']=='measured' for r in reports) else 'failed',
                            'wall_seconds':time.monotonic()-started,'jobs':reports})
            continue
        if not case or not case.get('manifest'):
            results.append({'case':name,'status':'missing_fixture'})
            continue
        if name == 'gpu_required':
            results.append({'case':name,'status':'no_verified_gpu_required_engine_in_current_contract'})
            continue
        try:
            report = case_report(case)
            results.append({'case':name,'status':'measured',**report})
        except Exception as error:
            results.append({'case':name,'status':'failed','error_type':type(error).__name__})
    args.report.write_text(json.dumps({'results':results,'production_ready':False},indent=2))
    return 1 if any(r['status']!='measured' for r in results) else 0


if __name__=='__main__':
    raise SystemExit(main())
