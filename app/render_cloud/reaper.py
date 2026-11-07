"""Independent, bounded reconciliation entrypoint for a timer/cron, not a worker callback."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .ledger import Ledger
from .provider import ProviderError, RunPod, reconcile


def refresh(ledger, store, provider, *, recover=True):
    """Recover progress/candidates after coordinator restart; no AI is called."""
    from .contracts import RenderSpec
    from .mailbox import Snapshot
    from .service import await_result
    outcomes = []
    for row in ledger.reconciliation_rows():
        if row['state'] in {'completed','failed','cancelled'} or row['cancel_requested']:
            continue
        details = json.loads(row['details'])
        storage = details.get('storage')
        if not storage:
            continue
        try:
            data = store.read_json(storage['mailbox_key'])
            if data is None:
                continue
            report = Snapshot.model_validate(data)
            ledger.snapshot(row['id'], row['user_id'], report.token, report.sequence,
                            report.history, report.observation.model_dump(),timings=report.timings,resources=report.resources)
            if report.uploaded:
                # Durable upload receipt permits immediate dedicated-compute
                # release, without waiting for a potentially slow VPS download.
                ledger.compute_finished(row['id'],row['user_id'],{'sha256':report.sha256,'size':report.size})
            if recover and report.uploaded and details.get('local_output') and details.get('render_spec'):
                spec = RenderSpec.model_validate(details['render_spec'])
                await_result(spec, Path(details['local_output']), ledger=ledger, store=store, provider=provider)
                outcomes.append({'job_id': row['id'], 'recovered': True})
        except Exception:
            outcomes.append({'job_id': row['id'], 'recovered': False})
    return outcomes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--emergency', action='store_true', help='Cancel and delete this ledger\'s dedicated Pods only')
    parser.add_argument('--billing', action='store_true', help='Import measured provider buckets after cleanup')
    args = parser.parse_args()
    if os.environ.get('ENABLE_CLOUD_REAPER') != '1':
        raise SystemExit('Cloud reaper is disabled')
    from .settings import CloudSettings, object_store
    config = CloudSettings()
    path = config.ledger
    if not path.is_absolute() or not path.is_file():
        raise SystemExit('An existing persistent execution ledger is required')
    provider = RunPod.from_settings(config)
    try:
        ledger = Ledger(path)
        store = None
        observations = []
        if config.s3_bucket and not args.emergency:
            try:
                store = object_store(config)
                observations = refresh(ledger,store,provider,recover=False)
            except Exception:
                observations = [{'recovered':False}]
        # Resource release must not wait behind a potentially large candidate
        # download/recovery, but first ingest fresh worker heartbeat snapshots.
        results = reconcile(provider, ledger, emergency=args.emergency)
        recovery = []
        if store is not None:
            recovery = refresh(ledger, store, provider)
        results.extend(reconcile(provider, ledger, emergency=args.emergency))
        billing = None
        if args.billing:
            from datetime import datetime, timedelta, timezone
            from .provider import sync_billing
            # Overlap intentionally: provider buckets may arrive late and are upserted.
            since = (datetime.now(timezone.utc)-timedelta(days=35)).isoformat()
            billing = sync_billing(provider, ledger, since=since)
        # IDs and outcomes only, never URLs, env, provider payloads or token material.
        print(json.dumps({'resources': results, 'observations':observations, 'recovery': recovery, 'billing_buckets': billing}))
        return 1 if any(not row['deleted'] for row in results) or any(not row.get('recovered',True) for row in observations+recovery) else 0
    except ProviderError:
        print(json.dumps({'error': 'provider_unavailable'}))
        return 1
    except Exception:
        # SDK/config/IO errors may carry signed URLs: never print their repr.
        print(json.dumps({'error': 'reconciliation_failed'}))
        return 1
    finally:
        provider.close()


if __name__ == '__main__':
    raise SystemExit(main())
