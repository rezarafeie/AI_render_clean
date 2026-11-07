"""S3-compatible staging. SDK client and credentials exist only on the VPS.

No public route accepts a filesystem path. The caller must resolve the owned
project root through existing project authorization before calling stage().
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .contracts import RenderSpec


class ObjectStore:
    def __init__(self, client, bucket: str, *, expiry=3600):
        if not bucket or not 60 <= expiry <= 21600:
            raise ValueError('Invalid storage configuration')
        self.client, self.bucket, self.expiry = client, bucket, expiry

    @staticmethod
    def prefix(user: str) -> str:
        return 'render/v1/' + hashlib.sha256(user.encode()).hexdigest() + '/'

    def key(self, user, digest):
        return self.prefix(user) + 'assets/' + digest

    def signed(self, operation, key):
        if operation not in {'get_object', 'put_object'}:
            raise ValueError('Unsupported signing operation')
        return self.client.generate_presigned_url(operation, Params={'Bucket': self.bucket, 'Key': key}, ExpiresIn=self.expiry)

    def stage(self, spec: RenderSpec, root: Path) -> dict:
        from .engines import verify_inputs
        verify_inputs(spec, root)
        downloads = {}
        for asset in spec.assets:
            key = self.key(spec.user_id, asset.sha256)
            try:
                info = self.client.head_object(Bucket=self.bucket, Key=key)
            except Exception as error:
                # A forbidden/throttled/network error is not evidence of absence.
                if getattr(error, 'response', {}).get('Error', {}).get('Code') not in {'404', 'NoSuchKey', 'NotFound'}:
                    raise RuntimeError('Storage metadata unavailable') from None
                info = None
            if info is None:
                with (root / asset.path).open('rb') as source:
                    self.client.upload_fileobj(source, self.bucket, key,
                                               ExtraArgs={'Metadata': {'sha256': asset.sha256}})
            elif info.get('ContentLength') != asset.size or info.get('Metadata', {}).get('sha256') != asset.sha256:
                raise ValueError('Stored content-addressed object mismatch')
            downloads[asset.path] = self.signed('get_object', key)
        output_key = self.prefix(spec.user_id) + f'jobs/{spec.job_id}/candidate.{spec.export_format}'
        return {'downloads': downloads, 'output_put': self.signed('put_object', output_key),
                'output_key': output_key}

    def write_json(self, key, value):
        self.client.put_object(Bucket=self.bucket, Key=key,
                               Body=json.dumps(value).encode(), ContentType='application/json')

    def read_json(self, key, *, limit=16384):
        try:
            result = self.client.get_object(Bucket=self.bucket, Key=key)
        except Exception as error:
            if getattr(error, 'response', {}).get('Error', {}).get('Code') in {'404', 'NoSuchKey', 'NotFound'}:
                return None
            raise RuntimeError('Storage report unavailable') from None
        body = result['Body']
        try:
            data = body.read(limit + 1)
            if len(data) > limit:
                raise ValueError('Storage report too large')
            return json.loads(data)
        finally:
            body.close()

    def bootstrap(self, spec, root, token, deadline, ledger, *, local_output=None):
        """Only the signed bootstrap URL leaves the VPS; no bucket credentials."""
        from .mailbox import Envelope
        staged = self.stage(spec, root)
        prefix = self.prefix(spec.user_id) + f'jobs/{spec.job_id}/'
        mailbox, control, envelope = prefix + 'status.json', prefix + 'control.json', prefix + 'bootstrap.json'
        self.write_json(control, {'cancel': False})
        value = Envelope(spec=spec, downloads=staged['downloads'], output_put=staged['output_put'],
                         mailbox_put=self.signed('put_object', mailbox), control_get=self.signed('get_object', control),
                         token=token, expires_at=deadline)
        self.write_json(envelope, value.model_dump())
        ledger.plan_storage(spec.job_id, spec.user_id, mailbox, control, staged['output_key'],
                            spec=spec.model_dump(), local_output=str(local_output) if local_output else None)
        return self.signed('get_object', envelope)

    def fetch_candidate(self, key, path, *, max_bytes, should_cancel=None):
        """Compatibility bridge for existing FileResponse delivery; streaming, no RAM blob.

        Download through the VPS is currently unavoidable for existing local-file
        output consumers. A future object-native delivery path can omit this step.
        """
        result = self.client.get_object(Bucket=self.bucket, Key=key)
        body, total, digest = result['Body'], 0, hashlib.sha256()
        try:
            if not 0 < int(result.get('ContentLength', 0)) <= max_bytes:
                raise ValueError('Output exceeds allowance')
            with path.open('xb') as output:
                while block := body.read(1024 * 1024):
                    if should_cancel and should_cancel():
                        raise InterruptedError('Output delivery cancelled')
                    total += len(block)
                    if total > max_bytes:
                        raise ValueError('Output exceeds allowance')
                    digest.update(block)
                    output.write(block)
            if total != int(result['ContentLength']):
                raise ValueError('Incomplete output download')
            return {'sha256': digest.hexdigest(), 'size': total, 'object_key': key}
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        finally:
            body.close()
