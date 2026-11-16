"""RunPod REST v1. Never blindly retry a non-idempotent create after a timeout."""
from __future__ import annotations

import re
import time
from urllib.parse import urlsplit

import httpx


class ProviderError(RuntimeError):
    pass


class ProviderRejected(ProviderError):
    """An explicit validation/auth/payment rejection, not a lost success response."""


class RunPod:
    def __init__(self, api_key: str, *, transport=None, relay_url='', relay_token='', registry_auth_id=''):
        if relay_url or relay_token:
            url = urlsplit(relay_url)
            if (url.scheme != 'https' or not url.hostname or url.username or url.password
                    or url.query or url.fragment or url.path != '/api/runpod' or len(relay_token) < 32):
                raise ValueError('Invalid RunPod relay configuration')
        elif not api_key:
            raise ValueError('RunPod key not configured')
        if registry_auth_id and not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', registry_auth_id):
            raise ValueError('Invalid RunPod registry authentication ID')
        self.relay_url = relay_url
        self.registry_auth_id = registry_auth_id
        self.client = httpx.Client(base_url='https://rest.runpod.io/v1/',
                                   headers={'Authorization': f'Bearer {relay_token if relay_url else api_key}'},
                                   timeout=35, transport=transport, follow_redirects=False,
                                   trust_env=not bool(relay_url))

    @classmethod
    def from_settings(cls, config):
        return cls(config.runpod_api_key.get_secret_value(), relay_url=config.runpod_relay_url,
                   relay_token=config.runpod_relay_token.get_secret_value(),
                   registry_auth_id=config.runpod_registry_auth_id)

    def close(self):
        self.client.close()

    def _request(self, method, path, **kwargs):
        try:
            if self.relay_url:
                response = self.client.post(self.relay_url, json={
                    'method': method, 'path': path,
                    'payload': kwargs.get('json'), 'query': kwargs.get('params'),
                })
                # Only the relay's explicit upstream envelope can establish an
                # upstream rejection; a platform 404/403 cannot settle a create.
                if response.status_code != 200:
                    raise ProviderError(f'runpod_relay_http_{response.status_code}')
                try:
                    envelope = response.json()
                    status = envelope['upstream_status']
                    result = envelope['result']
                    if type(status) is not int or not 100 <= status <= 599:
                        raise ValueError()
                except (ValueError, KeyError, TypeError):
                    raise ProviderError('runpod_relay_invalid_response') from None
            else:
                response = self.client.request(method, path, **kwargs)
                status = response.status_code
        except httpx.HTTPError:
            raise ProviderError('runpod_transport_uncertain') from None
        if status == 404 and method == 'DELETE':
            return None
        if not 200 <= status < 300:
            # Provider body/headers can echo credentials: retain status only.
            error = ProviderRejected if status in {400,401,402,403,404,422} else ProviderError
            raise error(f'runpod_http_{status}')
        if self.relay_url:
            return result
        try:
            return response.json() if response.content else None
        except ValueError:
            raise ProviderError('runpod_invalid_response') from None

    def list(self):
        result = self._request('GET', 'pods')
        if not isinstance(result, list):
            raise ProviderError('runpod_invalid_list')
        return result

    @staticmethod
    def name(deployment: str, job_id: str) -> str:
        if not re.fullmatch(r'[a-z0-9-]{1,30}', deployment) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}', job_id):
            raise ValueError('Invalid managed Pod identity')
        return f'editorgpt-{deployment}-{job_id}'

    def create(self, *, name, image, compute, hardware_ids, env, disk_gb=40, vcpu=8, data_centers=()):
        if (compute not in {'CPU', 'GPU'} or not hardware_ids
                or not re.fullmatch(r'[^\s]+@sha256:[0-9a-f]{64}', image)
                or not re.fullmatch(r'[a-zA-Z0-9_-]{1,200}', name)):
            raise ValueError('Pinned image and explicit resource candidates required')
        if not 10 <= disk_gb <= 200 or not 1 <= vcpu <= 64:
            raise ValueError('Resource bounds exceeded')
        payload = {'name': name, 'imageName': image, 'computeType': compute,
                   'cloudType': 'SECURE', 'interruptible': False,
                   'containerDiskInGb': disk_gb, 'volumeInGb': 0,
                   'ports': [], 'env': env}
        if self.registry_auth_id:
            payload['containerRegistryAuthId'] = self.registry_auth_id
        if data_centers:
            if (not isinstance(data_centers, (list, tuple)) or len(data_centers) > 12
                    or not all(isinstance(d, str) and re.fullmatch(r'[A-Z0-9-]{3,12}', d) for d in data_centers)):
                raise ValueError('Invalid data center list')
            payload['dataCenterIds'] = list(data_centers)
        if compute == 'CPU':
            payload.update(cpuFlavorIds=hardware_ids, vcpuCount=vcpu)
        else:
            payload.update(gpuTypeIds=hardware_ids, gpuCount=1)
        result = self._request('POST', 'pods', json=payload)
        if not isinstance(result, dict) or not result.get('id'):
            raise ProviderError('runpod_create_uncertain')
        return result

    def delete(self, pod_id):
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}', pod_id):
            raise ValueError('Invalid Pod ID')
        self._request('DELETE', f'pods/{pod_id}')

    def billing(self, start_time):
        result = self._request('GET','billing/pods',params={'grouping':'podId','bucketSize':'day','startTime':start_time})
        if not isinstance(result,list):
            raise ProviderError('runpod_invalid_billing_response')
        return result


def sync_billing(provider, ledger, *, since):
    """Measured provider bucket totals; do not pretend these split compute/storage."""
    import math
    pods = ledger.owned_pods()
    count = 0
    for item in provider.billing(since):
        if item.get('podId') not in pods:
            continue
        amount, stamp = item.get('amount'), item.get('time')
        if not isinstance(amount,(int,float)) or not math.isfinite(amount) or amount < 0 or not isinstance(stamp,str):
            raise ProviderError('runpod_invalid_billing_bucket')
        ledger.record_cost(pods[item['podId']], 'runpod', item['podId'] + ':' + stamp,
                           'provider_pod_total', amount, measured=True)
        count += 1
    return count


def reconcile(provider: RunPod, ledger, *, startup_seconds=900, idle_seconds=420, emergency=False) -> list[dict]:
    """Independent crash recovery, not dependent on successful worker callbacks.

    An ambiguous create is matched by its durably stored, random name AND image.
    No prefix sweep, no deletion of unrelated Pods and no automatic second create.
    If the list is empty after an uncertain POST, keep the liability unresolved:
    eventual visibility must not release concurrency/spending reservations early.
    """
    results = []
    inventory = None
    for row in ledger.reconciliation_rows():
        now = time.time()
        import json
        compute_finished = bool(json.loads(row['details']).get('compute_finished'))
        stale = ((row['heartbeat'] is not None and now - row['heartbeat'] > idle_seconds)
                 or (row['create_attempted'] and row['heartbeat'] is None and now - row['updated'] > startup_seconds))
        if compute_finished:
            stale = False
        terminal = row['state'] in {'completed', 'failed', 'cancelled'}
        if not terminal and (emergency or row['cancel_requested'] or now >= row['deadline'] or stale):
            state = 'cancelled' if emergency or row['cancel_requested'] else 'failed'
            ledger.finish(row['id'], row['user_id'], state, 'cancelled' if state == 'cancelled' else 'worker_deadline')
            terminal = True
        if not (terminal or compute_finished) or not row['cleanup_pending']:
            continue
        ids = {row['pod_id']} if row['pod_id'] else set()
        if row['pod_name'] and row['image']:
            try:
                if inventory is None:
                    inventory = provider.list()
            except ProviderError:
                results.append({'job_id': row['id'], 'deleted': False})
                continue
            ids.update(p['id'] for p in inventory if p.get('name') == row['pod_name']
                       and (p.get('image') or p.get('imageName')) == row['image'] and isinstance(p.get('id'), str))
        if not ids:
            results.append({'job_id': row['id'], 'deleted': False, 'reason': 'create_unresolved'})
            continue
        try:
            for pod_id in sorted(ids):
                provider.delete(pod_id)
        except (ProviderError, ValueError):
            results.append({'job_id': row['id'], 'deleted': False})
        else:
            if not row['pod_id']:
                ledger.attach_discovered(row['id'], sorted(ids)[0])
            ledger.cleanup_done(row['id'], row['pod_id'] or sorted(ids)[0])
            results.append({'job_id': row['id'], 'deleted': True})
    return results
